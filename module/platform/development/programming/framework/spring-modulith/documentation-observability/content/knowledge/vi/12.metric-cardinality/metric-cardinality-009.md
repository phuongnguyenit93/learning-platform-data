# Giới hạn số series trong hệ thống metrics

> **Chương:** Cardinality  
> **Module học tập:** `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`  
> **Định hướng:** Dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Học module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.
>
> **Trọng tâm:** Giới hạn số metric time series bằng thiết kế nhãn, dự toán cardinality, kiểm soát Micrometer registry và theo dõi hệ thống xuất/lưu metrics — mà không làm mất các bằng chứng vận hành thiết yếu.

## 1. Bài toán: số event ít, số series vẫn có thể rất lớn

Một ứng dụng Spring Boot có các application modules `order`, `payment`, `inventory` và `notification`. Khi bật Spring Modulith observability, các sự kiện được phát có thể được ghi thành Micrometer counters. Nếu thêm nhãn để phân tích từng loại event, một số nhóm có nhu cầu:

- Xem số `OrderCompleted` phát theo kênh bán hàng và khu vực.
- Phân biệt số lần phát `PaymentCaptured` giữa các phương thức thanh toán.
- Nhận cảnh báo khi một module ngừng phát event trong giờ có lưu lượng.
- Quan sát tương tác module qua metrics, tracing và Actuator.

Những mục tiêu này hợp lý. Vấn đề xuất hiện khi nhóm thêm giá trị **riêng cho từng giao dịch** vào nhãn, chẳng hạn `orderId`, `customerId`, `eventId` hoặc URL đầy đủ `/orders/123456`. Thay vì dùng một số chuỗi đo hữu hạn, hệ thống có thể tạo một meter/time series mới cho gần như mỗi request.

**Giới hạn số series không có nghĩa chỉ “đặt một ngưỡng rồi chặn hết”.** Cách đúng là chọn thông tin được phép trở thành tag, đặt ngân sách số series, phát hiện sự tăng bất thường, sau đó dùng giới hạn kỹ thuật làm lớp bảo vệ cuối cùng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cardinality và phân biệt **Micrometer meter ID** với **time series ở backend**.
2. Ước tính ngân sách series khi các nhãn có nhiều giá trị, nhiều instance hoặc histogram.
3. Nhận diện tag nguy hiểm trong Spring Modulith event metrics, HTTP metrics và custom observations.
4. Thiết kế nhãn hữu hạn từ domain event với `ModulithEventMetricsCustomizer`.
5. Sử dụng `MeterFilter` và `HighCardinalityTagsDetector` đúng chức năng, không làm méo ý nghĩa metrics.
6. Kiểm tra qua Actuator, Prometheus/backend và thử nghiệm nhiều giá trị giả lập.
7. Giải thích sự khác biệt giữa giảm series, giảm sampling trace và kiểm chứng hành vi nghiệp vụ.

## 2. Series là gì? Đếm ở tầng nào?

### 2.1. Meter trong Micrometer

Trong Micrometer, một `Meter` có định danh gồm **meter name** và các **tags** (cùng thông tin loại/định nghĩa meter tương ứng). Hai counter cùng tên nhưng khác tổ hợp tag là hai meter phân biệt.

Ví dụ:

~~~text
orders.completed{channel="WEB", result="SUCCESS"}
orders.completed{channel="MOBILE", result="SUCCESS"}
orders.completed{channel="WEB", result="FAILED"}
~~~

Ba tổ hợp khác nhau tương ứng ba meter/label sets ở mức ứng dụng. Đừng nhầm “counter đã tăng 1.000 lần” với “đã tạo 1.000 series”: **nếu 1.000 lượt cập nhật cùng một tổ hợp nhãn, counter vẫn là một meter**.

### 2.2. Time series trong Prometheus hoặc backend khác

Với hệ thống kiểu Prometheus, một time series được nhận diện bởi **tên metric xuất ra cùng một tập nhãn**. Backend có thể bổ sung nhãn như `job`, `instance`, `cluster`, `namespace` hoặc `pod`.

Một meter logic từ một instance có thể được chuyển thành một hay nhiều series tùy loại meter và cấu hình export:

| Micrometer meter | Dạng xuất phổ biến trong Prometheus | Lưu ý |
|---|---|---|
| Counter | Series counter tích lũy, thường tên kết thúc `_total` | Tên logic có thể được chuẩn hóa |
| Gauge | Series gauge | Giá trị có thể lên/xuống |
| Timer | `_count`, `_sum`; có thể thêm `_bucket` khi bật histogram | Một tập tag có thể phát sinh nhiều series |
| DistributionSummary | Count, sum và các series phân bố nếu cấu hình | Cardinality chịu ảnh hưởng histogram/percentiles |
| Long task timer | Các thành phần đo tùy registry | Không giả định nó tương đương counter |

Vì vậy, **số meter trong JVM không nhất thiết bằng số series do exporter tạo ra hoặc backend đang lưu**.

### 2.3. Active series, historical series và tốc độ sinh series

Ba câu hỏi khác nhau:

- **Active series:** hiện có bao nhiêu chuỗi đang được thu thập/sử dụng trong một cửa sổ vận hành?
- **Historical series:** trong khoảng lưu trữ, bao nhiêu tổ hợp label đã từng xuất hiện, kể cả sau khi pod bị hủy?
- **Churn:** hệ thống tạo rồi ngừng tạo bao nhiêu series mới theo thời gian, ví dụ do pod ID, request ID hoặc event ID thay đổi?

Một hệ thống có 1.000 active series tương đối ổn định có thể khác hoàn toàn hệ thống tạo 1.000 series mới **mỗi phút** rồi để chúng biến mất. Cả số lượng và tốc độ thay đổi đều quan trọng đối với bộ nhớ, index và lưu trữ backend.

## 3. Cách dự toán cardinality trước khi viết code

Với một metric có các tag `t1, t2, ..., tk`, một ước lượng giới hạn trên thô cho số tổ hợp là:

\[
S_{\text{meter}} \lesssim \prod_{i=1}^{k} |V(t_i)|
\]

Trong đó `|V(t_i)|` là số giá trị có thể xuất hiện của tag `t_i`. Dấu “nhỏ hơn hoặc xấp xỉ” phản ánh rằng **không phải mọi tổ hợp đều thật sự được tạo**. Tuy nhiên, nếu giá trị tag không giới hạn thì tích này có thể tăng rất nhanh.

Ví dụ event `OrderCompleted` được phân nhóm bằng:

| Tag | Số giá trị dự kiến |
|---|---:|
| `sales.channel` | 3 (WEB, MOBILE, PARTNER) |
| `sales.region` | 5 |
| `sales.fulfillment` | 2 (SHIP, PICKUP) |
| **Tổ hợp tối đa trong một JVM, một counter name** | **3 × 5 × 2 = 30** |

Nếu có **8 instance độc lập**, backend có thể thấy tối đa khoảng **30 × 8 = 240 chuỗi** cho loại counter này khi mỗi instance ghi nhận đủ các tổ hợp và mỗi instance được gắn nhãn phân biệt. Đây chỉ là **dự toán cho một metric family với một series xuất ra trên mỗi tổ hợp**.

### 3.1. Nhân thêm hệ số export/histogram

Nếu cùng một tập tags được dùng trong một `Timer` có histogram, series tăng theo số bucket và các chuỗi count/sum tương ứng.

Một cách hoạch định sơ bộ:

\[
S_{\text{backend}} \approx S_{\text{tổ hợp tag}} \times N_{\text{instance}} \times N_{\text{series mỗi tổ hợp}}
\]

Ví dụ giả định exporter có **12 series/tổ hợp** cho một timer đã bật histogram, thì 30 tổ hợp trên 8 instance có thể sinh khoảng **30 × 8 × 12 = 2.880 series**. Con số 12 chỉ là giả định minh họa; số bucket, các series bổ sung và quy tắc export phải kiểm tra trên hệ thống thật.

### 3.2. Bốn lỗi dự toán thường gặp

1. **Chỉ đếm số tag**, không nhân số giá trị của từng tag.
2. **Quên các tag chung và nhãn hạ tầng**, ví dụ instance, namespace hoặc môi trường.
3. **Quên histogram/percentile/SLO buckets**, làm series nhiều hơn một counter.
4. **Quên việc sinh tên metric động** như `order.latency.12345`: detector theo một meter name có thể không phát hiện kiểu tăng này.

### 3.3. Nhãn có tương quan không làm phép nhân biến mất hoàn toàn

Nếu `region=APAC` chỉ xuất hiện với `channel=MOBILE`, số tổ hợp quan sát được sẽ nhỏ hơn tích lý thuyết. Nhưng chỉ dựa vào dữ liệu một ngày để cho rằng ngân sách luôn nhỏ có thể sai: một phiên bản mới hoặc thị trường mới sẽ kích hoạt các tổ hợp trước đó chưa tồn tại.

**Ngân sách series nên dựa trên tập giá trị được phép và kịch bản tăng trưởng**, không chỉ snapshot đang có.

## 4. Tag tốt, tag xấu và nơi lưu dữ liệu chi tiết

| Dữ liệu/nhãn | Cardinality | Khuyến nghị |
|---|---|---|
| `module.identifier` | Hữu hạn theo số application modules | Thường giữ; đã được Spring Modulith cung cấp |
| `module.event.type` | Hữu hạn theo số domain event classes được nhận diện | Thường giữ; kiểm soát số event types |
| `sales.channel=WEB/MOBILE/PARTNER` | 3 giá trị | Hợp lý nếu dashboard cần phân nhóm |
| `payment.method=CARD/CASH/TRANSFER` | 3 giá trị | Có thể dùng nếu có ý nghĩa nghiệp vụ |
| `region=APAC/EMEA/AMER` | 3 nhóm | Hợp lý khi phân nhóm nhất quán |
| `result=SUCCESS/FAILURE` | 2 giá trị | Chỉ gắn ở giai đoạn đã **biết** outcome đó |
| `orderId`, `eventId`, `traceId` | Tăng theo từng giao dịch | **Không dùng làm metric tags** |
| `customerId`, email, số điện thoại | Rất cao; còn nhạy cảm | **Không dùng làm metric tags** |
| `uri=/orders/283771` | Theo số path thực tế | Dùng route template `/orders/{id}` |
| Nội dung exception/message tự do | Không giới hạn | Nhóm theo loại lỗi đã chuẩn hóa |
| `amount=123.45` | Liên tục và nhiều giá trị | Dùng histogram/distribution hoặc bucket nếu cần |
| `productSku` có hàng trăm nghìn giá trị | Cao | Dùng hệ thống phân tích nghiệp vụ hoặc nhóm hàng |
| `podName` ở common tag | Hữu hạn tại mỗi thời điểm nhưng churn cao | Xác định sự cần thiết và cách tổng hợp tại backend |

### 4.1. Tách metric và trace/log

Với cùng một nghiệp vụ:

- **Metric:** “Tốc độ `OrderCompleted` theo `sales.channel` có giảm không?”
- **Trace:** “Request của một đơn cụ thể đã đi qua `order`, `inventory`, `payment` thế nào?”
- **Log:** “Event có correlation ID cụ thể gặp exception nào?”
- **Event Publication Registry:** “Publication đến transactional listener đã hoàn tất, thất bại hay chờ xử lý?” nếu có registry/backend được cấu hình.
- **Dữ liệu nghiệp vụ:** “Đơn có commit, kho có thực sự thay đổi đúng không?”

Micrometer Observation API phân biệt **low-cardinality key-values** (phù hợp metrics) với **high-cardinality key-values** (hữu ích hơn cho trace/log khi thích hợp). Ví dụ:

~~~java
Observation.createNotStarted("checkout.process", observationRegistry)
        .lowCardinalityKeyValue("sales.channel", "WEB")
        .highCardinalityKeyValue("order.id", orderId.toString())
        .observe(() -> checkoutService.process(orderId));
~~~

Đoạn minh họa giả định `observationRegistry` và `checkoutService` là dependency đã có. High-cardinality key-value vẫn phải tuân thủ chính sách bảo vệ dữ liệu và không nên chứa bí mật. **Không biến high-cardinality context thành metric tag** qua một custom handler thiếu kiểm soát.

## 5. Những metric nào do Spring Modulith đăng ký?

Theo tài liệu Spring Modulith, phần hỗ trợ event observability cung cấp hai counter:

| Tên metric logic | Ý nghĩa | Đặc điểm nhãn |
|---|---|---|
| `module.events.published` | Tổng hợp event publication được instrument | `module.event.type`, `module.identifier`, `module.name` |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter riêng cho module và loại event | `module.identifier`, `module.name`, có thể thêm tag domain-specific |

Trong một ứng dụng với module `order` và event `OrderCompleted`:

~~~text
module.events.published
module.events.published.order.OrderCompleted
~~~

**Cả hai metric có thể tăng cho cùng một lượt publish.** Chúng biểu diễn hai cách phân loại của hành vi phát event; không cộng chúng lại để báo số event.

### 5.1. Rủi ro cardinality ở counter tổng hợp

Số chuỗi của `module.events.published` có thể tăng theo tổ hợp module identifier và event type được instrument. Nếu hệ thống có số loại event hữu hạn và tên module ổn định, đó thường là tập giá trị hợp lý. Tuy nhiên, khi mỗi module sinh rất nhiều event class từ mã được generate, hoặc các loại event không được kiểm soát, số lượng nhãn có thể tăng đáng kể.

Đừng loại bỏ mù quáng `module.event.type` chỉ để giảm số series: nhãn đó có giá trị chẩn đoán. Hãy kiểm tra mức tăng thực tế, số event classes và loại câu hỏi dashboard cần trả lời.

### 5.2. Rủi ro ở counter riêng sau khi customizer thêm tags

Spring Modulith cho phép tùy biến counter riêng theo loại event bằng `ModulithEventMetricsCustomizer`. Đây là nơi dễ mắc sai lầm:

~~~java
// Ví dụ phản diện: không dùng ID riêng của từng đơn làm tag.
metrics.customize(OrderCompleted.class, (event, builder) -> {
    builder.tags("order.id", event.orderId().toString());
});
~~~

Với 100.000 đơn duy nhất, riêng tag `order.id` có thể tạo khoảng 100.000 meter combinations cho một counter name ở những điều kiện tương ứng, chưa kể nhãn backend. Nó làm biến mất lợi thế tổng hợp của metrics.

**Phương án tốt hơn:** phân nhóm theo enum hữu hạn như kênh bán hàng, trạng thái tổng quát hoặc nhóm vùng, và chỉ thêm khi có câu hỏi vận hành thực sự sử dụng.

## 6. Thiết kế event metrics có cardinality hữu hạn

Giả sử event có ID cho correlation và kênh bán hàng để phân nhóm:

~~~java
// src/main/java/com/acme/shop/order/OrderCompleted.java
package com.acme.shop.order;

import java.util.UUID;

public record OrderCompleted(
        UUID orderId,
        SalesChannel channel
) {
    public enum SalesChannel {
        WEB, MOBILE, PARTNER
    }
}
~~~

Ở ví dụ này, kênh thuộc enum ba giá trị. `orderId` vẫn là dữ liệu quan trọng cho ứng dụng và log/trace, nhưng **không được dùng làm tag**.

### 6.1. Dependency minh họa

Dự án giả định đã có Spring Boot/Spring Modulith BOM tương thích. Với Gradle:

~~~groovy
dependencies {
    // Hỗ trợ Modulith Actuator và observability ở runtime.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // API để mã nguồn ứng dụng dùng ModulithEventMetricsCustomizer.
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
}
~~~

Nếu dự án có các starter khác đã chứa Micrometer, không khai báo trùng không cần thiết. Tên artifact và BOM phải đối chiếu theo version thực tế (ví dụ dòng Spring Modulith 2.2). Những đoạn code Java trong bài giả định các API tương ứng có trong compile classpath.

### 6.2. Customizer chỉ thêm tag có giá trị hữu hạn

~~~java
package com.acme.shop.observability;

import com.acme.shop.order.OrderCompleted;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration(proxyBeanMethods = false)
class EventMetricConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {

        return metrics -> metrics.customize(
                OrderCompleted.class,
                (event, builder) -> {
                    builder.tags(
                            "sales.channel",
                            event.channel().name()
                    );
                }
        );
    }
}
~~~

Mục đích:

- Counter vẫn có cùng ý nghĩa: số lượt `OrderCompleted` được instrument khi publish.
- Tag `sales.channel` chỉ có tối đa ba giá trị.
- Mỗi channel được xem ở một series riêng nếu xuất hiện.
- Không có nhãn theo `orderId`; dùng log/trace cho từng đơn.

Nếu dữ liệu channel đến từ người dùng và là chuỗi tự do, **không gắn trực tiếp**. Chuyển nó về một enum hoặc hàm chuẩn hóa có tập kết quả hữu hạn (kèm `UNKNOWN` hoặc `OTHER`) trước khi tạo event/metric.

### 6.3. Chuẩn hóa input không tin cậy

~~~java
static String normalizeChannel(String input) {

    if (input == null || input.isBlank()) {
        return "UNKNOWN";
    }

    return switch (input.trim().toUpperCase(java.util.Locale.ROOT)) {
        case "WEB" -> "WEB";
        case "MOBILE" -> "MOBILE";
        case "PARTNER" -> "PARTNER";
        default -> "OTHER";
    };
}
~~~

Hàm này bảo đảm tập kết quả tối đa 5 giá trị: WEB/MOBILE/PARTNER/UNKNOWN/OTHER. Nó là ví dụ chuẩn hóa **ở nguồn dữ liệu**; nếu event đã dùng enum không nullable với ba giá trị thì không cần chuyển đổi lặp lại trong customizer.

**Tránh một lỗi tinh vi:** giữ nguyên `input` trong nhánh `default` sẽ biến giá trị tự do thành nhãn vô hạn, dù bình thường dữ liệu trông có vẻ hợp lệ.

## 7. Giới hạn bằng MeterFilter ở tầng Micrometer

### 7.1. Cơ chế MeterFilter

`io.micrometer.core.instrument.config.MeterFilter` có thể:

1. Cho phép hoặc từ chối đăng ký meter.
2. Biến đổi meter ID: đổi tên, bỏ/đổi tag, thêm common tags.
3. Tùy chỉnh distribution statistics cho Timer/DistributionSummary.

Các filter áp dụng trong quá trình đăng ký meter; thứ tự filter và nhánh `ACCEPT`/`DENY` ảnh hưởng kết quả.

Nếu filter trả `DENY`, registry trả một **no-op meter** (ví dụ `NoopCounter`). Code gọi `increment()` vẫn chạy, nhưng giá trị **không được lưu/ghi nhận** vào metric hữu hiệu. Vì vậy bộ lọc bảo vệ hệ thống nhưng có thể **làm mất dữ liệu đo**, không phải tự động gộp các giá trị bị chặn vào nhóm OTHER.

### 7.2. Giới hạn số giá trị của một tag trên nhóm meter

Spring Boot có thể áp dụng các bean `MeterFilter` cho registry do Boot quản lý. Ví dụ giới hạn tag `sales.channel` của counter riêng:

~~~java
package com.acme.shop.observability;

import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricGuardrails {

    @Bean
    MeterFilter boundOrderCompletedChannels() {

        return MeterFilter.maximumAllowableTags(
                "module.events.published.order.OrderCompleted",
                "sales.channel",
                5,
                MeterFilter.deny()
        );
    }
}
~~~

Cấu hình minh họa cho phép tối đa **5 giá trị phân biệt của tag `sales.channel`** trong phạm vi meter names khớp prefix. Ngưỡng 5 là dự phòng cho một hệ thống dự kiến chỉ có vài giá trị; không phải “giới hạn toàn hệ thống còn 5 series”.

**Quan trọng:**

- `maximumAllowableTags(...)` giới hạn số **giá trị khác nhau của tag key được chọn**, không phải tổng số tổ hợp của mọi tag.
- Nếu có các tag khác như `region` và `result`, số series vẫn có thể lớn.
- Vì tham số đầu là **meter name prefix**, cần chọn prefix đủ hẹp để không ảnh hưởng ngoài ý muốn.
- Khi giá trị mới vượt ngưỡng, `MeterFilter.deny()` có thể từ chối đăng ký meter mới; giá trị cho event đó **không được ghi vào counter bị từ chối**.
- Bộ lọc nên có hiệu lực **trước khi meter được đăng ký**. Nó không phải công cụ xóa các meter đã tồn tại hoặc sửa dữ liệu lịch sử.

Đây là **hàng rào cuối** để hạn chế thiệt hại. Với dữ liệu đầu vào mà mình kiểm soát, nên sửa trực tiếp `sales.channel` về enum/bucket trước.

### 7.3. Giới hạn tổng số meter trong registry

Micrometer có `MeterFilter.maximumAllowableMetrics(int)`, đặt giới hạn số meter IDs được phép đăng ký trong một registry.

~~~java
// Ví dụ minh họa, không nên sao chép ngưỡng vào production.
registry.config()
        .meterFilter(MeterFilter.maximumAllowableMetrics(10_000));
~~~

Cách này là **phương án cứu hộ tổng thể**: nếu các metrics thiết yếu được đăng ký sau khi registry chạm ngưỡng, chúng có thể bị loại. Do vậy không được chọn một con số tùy ý rồi coi như đã giải quyết cardinality. Hãy ưu tiên budget **theo nhóm metric**, sửa tag nguồn và kiểm chứng các SLI/SLO quan trọng vẫn có dữ liệu.

### 7.4. Bỏ tag hoặc thay giá trị tag

Khi không sửa ngay được thư viện instrument, Micrometer có các helper:

~~~java
// Chặn một tag nhiều giá trị ở tầng MeterRegistry:
registry.config().meterFilter(
        MeterFilter.ignoreTags("request.userId")
);

// Chuẩn hóa giá trị một tag về tập hữu hạn:
registry.config().meterFilter(
        MeterFilter.replaceTagValues(
                "uri",
                value -> value.startsWith("/orders/")
                        ? "/orders/{id}"
                        : value
        )
);
~~~

Hai ví dụ đều cần đặt đúng **trước khi meter tạo**, và phải xem xét toàn bộ những metric đang dùng tag đó. `ignoreTags` áp dụng với tag key được chọn trên registry; nếu tên tag chỉ gây vấn đề ở một meter, nên hạn chế tác dụng bằng `MeterFilter.forMeters(...)` (theo version API tương ứng) hoặc sửa ở nguồn.

**Cẩn trọng:** Hàm biến đổi `uri` minh họa ở trên cố ý đơn giản để giải thích. Trong ứng dụng thật, phải dùng **route template do Spring MVC/WebFlux cung cấp** hoặc bộ chuẩn hóa route an toàn, tránh gom nhầm các endpoint khác nhau có cùng prefix.

### 7.5. Đừng sửa MeterFilter bằng lookup động

Micrometer khuyến nghị `MeterFilter.map(Meter.Id)` mang tính tĩnh, dựa vào meter ID. Đừng đặt truy vấn DB, truy cập HTTP, hoặc sử dụng request context có thể đổi theo từng lần trong `map`. Nếu cần gắn nhãn từ một domain event, dùng instrumentation/customizer tại nơi có **event thực**, không biến MeterFilter thành nơi xử lý nghiệp vụ.

## 8. Phát hiện cardinality tăng trước khi hệ thống quá tải

### 8.1. HighCardinalityTagsDetector

Micrometer có `HighCardinalityTagsDetector` giúp phát hiện **nhiều meter cùng một tên**. Khi số meter cho một meter name vượt ngưỡng, đó là dấu hiệu có quá nhiều tổ hợp tag.

Ở các phiên bản Micrometer hỗ trợ API liên quan, có thể bật detector cho registry:

~~~java
// Ví dụ API Micrometer 1.18; kiểm tra version dự án.
registry.config().withHighCardinalityTagsDetector();
~~~

Hoặc thực hiện một kiểm tra một lần:

~~~java
import io.micrometer.core.instrument.HighCardinalityTagsDetector;
import io.micrometer.core.instrument.MeterRegistry;

void inspectHighCardinality(MeterRegistry registry) {

    try (HighCardinalityTagsDetector detector =
            new HighCardinalityTagsDetector.Builder(registry)
                    .threshold(100)
                    .build()) {

        detector.findFirst().ifPresent(name ->
                System.out.println("Potential high cardinality: " + name)
        );
    }
}
~~~

Đoạn này minh họa quy trình và **không phải khuyến nghị log thường trực vào stdout trong production**. Có thể thay bằng logging/alert có giới hạn. API cấu hình detector khác nhau theo phiên bản Micrometer, nên cần đối chiếu với Javadoc thực tế.

**Giới hạn của detector:**

- Nó tìm **meter name có quá nhiều meter IDs**, không phải bộ phân tích mọi loại memory leak.
- Nếu code sinh **tên meter động** như `order.event.<UUID>`, mỗi tên chỉ có một meter thì detector theo tên có thể không báo động.
- Threshold là heuristic, không phải giới hạn series toàn hệ thống.
- Nếu có nhiều metric families bị lỗi, một kiểm tra đầu tiên có thể chỉ giúp chỉ ra trường hợp đầu; cần tiếp tục rà soát.

### 8.2. Các tín hiệu khác nên giám sát

| Tín hiệu | Ý nghĩa cần điều tra |
|---|---|
| Số meter IDs trong ứng dụng tăng đều theo thời gian | Nghi tag động hoặc tên meter động |
| Số active series ở Prometheus/backend tăng sau deploy | Thay đổi nhãn hoặc số instance/bucket |
| Tốc độ series churn tăng | Nhãn pod/request/event ID thay đổi liên tục |
| Scrape payload lớn hơn bất thường | Có thêm series hoặc histogram buckets |
| Backend query chậm, RAM/index tăng | Cardinality hoặc khối lượng lưu trữ tăng |
| MeterFilter bắt đầu deny nhiều meter | Hàng rào kỹ thuật đang che mất các phép đo mới |
| SLI quan trọng mất dữ liệu | Guardrail quá rộng hoặc instrumentation/registry có lỗi |

Không nhầm số counter `COUNT` tăng (nghiệp vụ có nhiều event) với số **series** tăng (có nhiều tổ hợp nhãn). Hai số đo khác nhau.

## 9. Dùng Actuator và Prometheus để kiểm tra đúng tầng

### 9.1. Actuator của Spring Boot

Trong môi trường thử nghiệm, nếu Actuator và quyền truy cập phù hợp:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,modulith,prometheus"
~~~

**Lưu ý:** `/actuator/prometheus` yêu cầu Prometheus registry tương ứng (thường dependency `io.micrometer:micrometer-registry-prometheus`) và cấu hình phù hợp. Insight starter không tự cài Prometheus server hoặc registry export cho mọi hệ thống.

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/module.events.published
curl -s http://localhost:8080/actuator/metrics/module.events.published.order.OrderCompleted
curl -s http://localhost:8080/actuator/prometheus
~~~

Ý nghĩa:

- `/actuator/metrics` liệt kê **meter names** và các phép đo có sẵn.
- `/actuator/metrics/{name}` có thể trả `availableTags` để biết các **giá trị tag đã xuất hiện**.
- `/actuator/prometheus` cho xem **tên/label thực được export**, kể cả biến thể `_total`, `_sum` và `_bucket` nếu được hỗ trợ.
- `/actuator/modulith` cung cấp **metadata module**, không phải số series hoặc lịch sử event.

**Không chỉ đếm số tên trong `/actuator/metrics`** rồi kết luận đó là tổng số series: một tên có thể tương ứng hàng nghìn tổ hợp tags.

### 9.2. PromQL để đếm series trong backend

Ví dụ giả định backend Prometheus có label `job="shop"`. Chỉ truy vấn một họ metric đã xác định:

~~~promql
count by (__name__) (
  {job="shop", __name__=~"module_events_published.*"}
)
~~~

Câu lệnh này đếm các series **khớp bộ lọc tại thời điểm truy vấn**, nhóm theo tên metric. Cần kiểm tra tên sau khi exporter chuẩn hóa; không giả định một tên Prometheus duy nhất áp dụng cho mọi version.

Nếu muốn xem số series theo module:

~~~promql
count by (module_identifier) (
  {job="shop", __name__=~"module_events_published.*"}
)
~~~

`module_identifier` là ví dụ nhãn theo quy ước chuẩn hóa; hãy đối chiếu label thực ở output export. Nếu query không trả dữ liệu, cần xem namespace/job/label, dấu gạch dưới, backend relabeling hoặc đúng khoảng thời gian.

**Cảnh báo hiệu năng:** Tránh áp dụng selector quá rộng trên toàn bộ backend lớn chỉ để tìm cardinality. Ưu tiên giới hạn `job`, `namespace` và metric family, hoặc dùng dashboards/API quản trị series count của hệ thống đang vận hành.

### 9.3. Phân biệt hạn chế ở app và ở collector

- **Sửa tag tại nguồn/đăng ký MeterFilter:** ngăn hoặc giảm số meter được tạo trong ứng dụng và số metrics xuất đi.
- **Collector relabel/drop:** giảm dữ liệu đi sâu vào hệ thống lưu trữ nhưng ứng dụng có thể vẫn tốn chi phí tạo/export payload ban đầu.
- **Backend retention/aggregation:** quản lý chi phí lưu trữ/lịch sử nhưng không xóa nguyên nhân app tạo quá nhiều tổ hợp.

Vì vậy phương án bền vững là giảm cardinality **càng gần nguồn phát telemetry càng tốt**, rồi tiếp tục giám sát ở backend.

## 10. Budget theo nhóm metric và theo module

Không có một ngưỡng series “đúng cho mọi tổ chức”. Ngân sách phải dựa trên chi phí, giới hạn backend, số instance, loại meter, SLO và nhu cầu phân tích.

Một bảng review mẫu:

| Nhóm metric | Giá trị quản trị | Quy tắc |
|---|---|---|
| HTTP server metrics | Giữ latency/status/route template | Không xuất raw URI có ID; kiểm soát histogram buckets |
| Spring Modulith event summary | Theo module và event type | Không thêm tag cá thể; xem số event classes |
| Counter event riêng | Theo một vài nhóm nghiệp vụ hữu hạn | Gắn tag thông qua customizer; dự toán tổ hợp |
| DB/HTTP client metrics | Theo pool/client/operation đã kiểm soát | Không dùng query SQL/raw URL như tag |
| Custom business timer | Chỉ cho bước quan trọng | Kiểm soát tag và phân phối/histogram |
| JVM/system metrics | Đảm bảo giữ các meter thiết yếu | Không dùng cap tổng thiếu phân biệt khiến chúng bị deny |

### 10.1. Cách dựng ngân sách có thể kiểm toán

1. **Liệt kê metric families** thực tế trong ứng dụng.
2. **Ghi mục tiêu vận hành** của từng family: dashboard, alert, capacity hoặc diagnosis.
3. **Liệt kê tất cả dimensions**: application tags, common tags, exporter/target labels.
4. **Ước tính tối đa số giá trị** của mỗi dimension ở hiện tại và khi tăng trưởng.
5. **Nhân theo instance và kiểu export** (counter, gauge, histogram).
6. **Gắn ngân sách với nhóm chịu trách nhiệm** và ngưỡng cảnh báo; phân biệt “cảnh báo” với “deny meter”.
7. **Theo dõi số series thực tế sau deploy**, kiểm tra thay đổi tên/tag so với baseline.
8. **Ưu tiên giữ tín hiệu quan trọng**, không chặn các SLI cốt lõi chỉ vì app đạt một ngưỡng chung.

Một ví dụ bảng ngân sách cho hệ thống mẫu:

| Phân loại | Giả định | Series ước lượng |
|---|---|---:|
| `OrderCompleted` counter riêng | 3 channels × 5 regions × 2 fulfillment × 8 instances | 240 |
| `PaymentCaptured` counter riêng | 3 payment methods × 4 outcomes × 8 instances | 96 |
| Một timer nghiệp vụ | 5 operations × 3 statuses × 8 instances × 12 series per label set | 1.440 |
| **Tổng ba nhóm ví dụ** | Không gồm metric khác hoặc series lịch sử | **1.776** |

Các số là **minh họa lập ngân sách**, không phải đo từ ứng dụng thật. Cần đo thực tế trước khi chọn guardrail.

## 11. Case study: sau deploy số series tăng mạnh

Trước deploy, dashboard HTTP server có khoảng vài trăm series; sau deploy, backend báo số series tăng liên tục. Code mới ghi tag:

~~~java
// Ví dụ phản diện.
registry.counter(
        "orders.lookup.requests",
        "uri", "/orders/" + orderId,
        "status", status
).increment();
~~~

Với `orderId` riêng cho từng đơn, mỗi URI tạo một label value mới. Cùng lúc nhóm khác gắn `order.id` vào counter `OrderCompleted`. Hai nguồn tăng số series đồng thời.

### Quy trình điều tra

**Bước 1 – Xác nhận phạm vi.** Kiểm tra thời điểm deploy, số instance, thay đổi histogram/scrape, chứ không vội gán nguyên nhân duy nhất cho code.

**Bước 2 – Tìm metric family có nhiều series.** Xem danh sách meter names ở Actuator và số series theo name ở backend.

**Bước 3 – Xem các label gây tăng.** Phát hiện `uri` chứa ID và `order.id` gần như duy nhất.

**Bước 4 – Sửa gốc.** Với HTTP, dùng route template do framework xác định, ví dụ `/orders/{id}`. Với domain event, bỏ tag `order.id`; chỉ giữ `sales.channel` nếu dashboard thật sự cần.

**Bước 5 – Bảo vệ trong lúc chuyển đổi.** Nếu thư viện không sửa ngay được, áp `MeterFilter.ignoreTags`/`replaceTagValues` có phạm vi phù hợp hoặc `maximumAllowableTags` như hàng rào cuối. Ghi nhận rõ những series bị deny có thể làm telemetry thiếu dữ liệu.

**Bước 6 – Kiểm chứng.** Chạy một kịch bản tạo nhiều order IDs khác nhau nhưng cùng channel; số meter combinations **không còn tỷ lệ với số order IDs**. Kiểm tra event count vẫn tăng đúng khi cùng tổ hợp tags được tái sử dụng.

**Bước 7 – Theo dõi backend.** Active series có thể giảm sau khi dữ liệu mới không còn nhãn ID; dữ liệu lịch sử/retention không mất tức thì. Đừng nhầm việc series cũ còn trong backend với việc bản ứng dụng mới vẫn tạo chúng.

### Sơ đồ trước và sau

~~~mermaid
flowchart LR
    subgraph Bad["Trước: unbounded labels"]
        E1["OrderCompleted(UUID)"] --> C1["Counter với tag orderId"]
        C1 --> S1["Hàng nghìn meter / time series"]
    end
    subgraph Good["Sau: bounded labels"]
        E2["OrderCompleted(UUID, channel)"] --> C2["Counter với tag channel"]
        C2 --> S2["Tối đa vài nhóm cho mỗi event type"]
        E2 -.-> T["Trace/log chứa correlation ID"]
    end
~~~

Bỏ tag ID không làm mất quyền sử dụng ID trong hệ thống nghiệp vụ. Nó chỉ **đặt ID ở kênh telemetry đúng bản chất**.

## 12. Thực hành: mô phỏng số meter theo tag

Một bài test nhỏ với `SimpleMeterRegistry` chứng minh **số lần ghi counter khác với số meter IDs**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MetricCardinalityTests {

    @Test
    void boundedChannelKeepsMeterCountSmall() {

        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {

            String[] channels = {"WEB", "MOBILE", "PARTNER"};

            for (int i = 0; i < 1_000; i++) {
                registry.counter(
                        "orders.completed",
                        "sales.channel",
                        channels[i % channels.length]
                ).increment();
            }

            assertEquals(
                    3,
                    registry.find("orders.completed").meters().size()
            );
        }
    }
}
~~~

**Kết luận thử nghiệm:** 1.000 lượt `increment()` có thể vẫn chỉ sử dụng ba meter IDs khi tập giá trị `sales.channel` gồm đúng ba nhóm.

### 12.1. Thử giới hạn giá trị tag bằng filter

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.micrometer.core.instrument.config.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MeterFilterLimitTests {

    @Test
    void aNewTagValueIsDeniedAfterTheBound() {

        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {

            registry.config().meterFilter(
                    MeterFilter.maximumAllowableTags(
                            "orders.completed",
                            "sales.channel",
                            3,
                            MeterFilter.deny()
                    )
            );

            registry.counter("orders.completed", "sales.channel", "WEB")
                    .increment();

            registry.counter("orders.completed", "sales.channel", "MOBILE")
                    .increment();

            registry.counter("orders.completed", "sales.channel", "PARTNER")
                    .increment();

            // Giá trị thứ tư vượt ngưỡng; counter mới có thể là no-op.
            registry.counter("orders.completed", "sales.channel", "UNKNOWN")
                    .increment();

            assertEquals(
                    3,
                    registry.find("orders.completed").meters().size()
            );
        }
    }
}
~~~

Test mô tả cơ chế của filter khi registry có ba giá trị tag đã được đăng ký và một giá trị mới bị deny. **Không sao chép cơ chế deny này để thay thế việc chuẩn hóa `UNKNOWN` thành một nhóm được phép**: trong production, nếu UNKNOWN là giá trị có ý nghĩa vận hành thì phải thiết kế ngưỡng/mapping để không làm mất dữ liệu đó.

Không thực hiện các test trên trực tiếp trong bước biên soạn bài; đây là nội dung mẫu cho người học kiểm chứng với Micrometer version của dự án.

### 12.2. Bài tập mở rộng

Thử ba biến thể và so `registry.getMeters().size()`:

1. 1.000 lượt publish với tag chỉ `sales.channel` có ba nhóm.
2. 1.000 lượt publish với cả `sales.channel` và `region` có năm nhóm.
3. 1.000 lượt publish với tag `orderId` mang 1.000 UUID khác nhau.

**Dự đoán:** biến thể thứ ba làm số meter IDs tăng theo số UUID; hai biến thể đầu có giới hạn bởi số tổ hợp nhãn. Khi kiểm tra, phân biệt số meter trong JVM với series exporter/backend thực.

## 13. Các lỗi vận hành dễ nhầm với cardinality

| Triệu chứng | Giải thích khả dĩ | Bằng chứng cần kiểm tra |
|---|---|---|
| `module.events.published` tăng nhanh | Có nhiều lượt publish, chưa chắc có nhiều series | Xem COUNT và số bộ tags riêng |
| Số meter tăng dù traffic gần như không đổi | Giá trị tag động hoặc tên metric động | Danh sách meter IDs và code instrument |
| Mất một phần metric sau khi đặt cap | `MeterFilter.deny()` đã từ chối meter | Kiểm tra rule, log và giá trị bị vượt |
| `/actuator/metrics` chỉ có vài tên | Một tên có thể mang nhiều bộ tags | `availableTags`, registry meter IDs |
| Prometheus có nhiều series hơn app meters | Histogram/target labels/instance labels | Output scrape và query backend |
| Backend vẫn có series tag ID sau khi sửa | Series lịch sử chưa hết retention hoặc pod cũ còn chạy | Build IDs, target instances, thời gian |
| HighCardinalityTagsDetector không báo | Tên meter động, chưa chạm threshold hoặc chỉ có lỗi ở backend labels | Kiểm tra tên metric và label sources khác |
| Trace thiếu span khi dùng ObservationPredicate | Predicate ảnh hưởng observation; không phải chỉ metrics | Quan sát handler/sampler và context |
| Event counter published tăng nhưng listener chưa cập nhật kho | Publish không đồng nghĩa consume thành công | Registry, trace/log, DB |
| Alert đột nhiên giảm về 0 khi giới hạn meter | Metric đã bị deny hoặc label/query thay đổi | Tách kiểm tra telemetry khỏi business |
| Số active series tăng theo số pod | Scale-out làm nhân label instance | Số targets/pods, metric families |
| Sau khi bật histogram series tăng | Mỗi label set xuất nhiều bucket/count/sum | Cấu hình histogram và scrape output |

Hãy tránh giải pháp “tắt tất cả metrics” chỉ để đưa số series về nhỏ. Mục tiêu quan trọng là **độ bao phủ của telemetry thiết yếu trên một chi phí kiểm soát được**.

## 14. Checklist trước khi đưa metric mới vào production

- [ ] Metric có tên, đơn vị, loại meter và ngữ nghĩa rõ ràng.
- [ ] Có câu hỏi vận hành hoặc SLO/dashboard/alert thực sự cần metric này.
- [ ] Không tạo metric name động từ ID hoặc input tự do.
- [ ] Mỗi tag key có tập giá trị được liệt kê hoặc có quy tắc chuẩn hóa hữu hạn.
- [ ] Không đặt `orderId`, `customerId`, `traceId`, email, token, query string hoặc raw URL vào metric tags.
- [ ] Đã tính tích các tổ hợp nhãn cộng nhãn hạ tầng và số instance.
- [ ] Đã xét Timer/histogram làm nhân số series trên mỗi tổ hợp.
- [ ] Nếu dùng `ModulithEventMetricsCustomizer`, chỉ thêm tag từ enum/bucket có ý nghĩa tại thời điểm publish.
- [ ] Đã kiểm tra metric tổng hợp và metric riêng của Modulith không bị cộng trùng.
- [ ] Đã thử kịch bản 100/1.000 giá trị ID khác nhau mà số meter vẫn nằm trong budget.
- [ ] Có baseline trước deploy và giám sát số series/churn sau deploy.
- [ ] `MeterFilter` được xem là guardrail, không thay nguồn dữ liệu chuẩn hóa.
- [ ] Nếu dùng hard cap, đã kiểm tra những metric quan trọng không bị deny.
- [ ] Có kế hoạch giữ correlation ở trace/log và publication state riêng.
- [ ] Có owner cho mỗi metric family, hợp đồng nhãn và quy trình review thay đổi.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Một counter được tăng 10.000 lần nhưng luôn dùng cùng tên và tag set. Có 10.000 series không?

**Đáp án:** Không. Trong một registry, cùng meter ID được tái sử dụng; số lần tăng khác với số meter/series. Số series backend còn phụ thuộc instance/exporter labels.

**Câu 2.** Counter có ba tag với 4, 5 và 6 giá trị. Có thể có tối đa bao nhiêu tổ hợp trong một instance?

**Đáp án:** Tối đa **4 × 5 × 6 = 120** tổ hợp, nếu mọi kết hợp đều xuất hiện. Với nhiều instance, backend có thể có nhiều series hơn.

**Câu 3.** Tại sao việc thêm `orderId` vào event counter nguy hiểm?

**Đáp án:** Số order IDs tăng liên tục khiến meter combinations/time series tăng gần theo số đơn, gây tốn bộ nhớ, lưu trữ và chi phí truy vấn.

**Câu 4.** `MeterFilter.maximumAllowableTags(..., "sales.channel", 5, ...)` có giới hạn toàn bộ registry ở năm series không?

**Đáp án:** Không. Nó chặn **giá trị phân biệt thứ sáu** của một tag trong phạm vi tên meter được chọn; các tag khác vẫn có thể nhân số series.

**Câu 5.** Nếu filter deny một counter mới, code gọi `increment()` có dừng nghiệp vụ không?

**Đáp án:** Không. Registry có thể trả no-op counter; phép ghi metric bị bỏ, business code vẫn tiếp tục.

**Câu 6.** Vì sao một timer histogram có thể dùng nhiều series hơn một counter với cùng nhãn?

**Đáp án:** Exporter có thể tạo các chuỗi bucket, count và sum cho từng tổ hợp nhãn.

**Câu 7.** `HighCardinalityTagsDetector` có phát hiện mọi trường hợp tên metric động không?

**Đáp án:** Không. Detector dựa vào số meter có **cùng tên**, nên metric names khác nhau theo UUID có thể không bị cảnh báo.

**Câu 8.** Event publish counter tăng, nhưng listener inventory thất bại. Đó có phải lỗi cardinality không?

**Đáp án:** Không. Đây là khác biệt giữa hành vi publish và xử lý. Cần điều tra registry, tracing, log và kết quả nghiệp vụ; cardinality là vấn đề số tổ hợp nhãn.

## 16. Tổng kết

**Giới hạn số series hiệu quả bắt đầu từ thiết kế dữ liệu đo, không bắt đầu từ việc từ chối metric ở ngưỡng cuối cùng.**

- Một meter/time series được phân biệt bởi **tổ hợp tên và tags**, không phải số lần event xảy ra.
- **Số tổ hợp tags nhân với số instance và các thành phần export như histogram** tạo ngân sách series ở backend.
- Trong Spring Modulith, counter event tổng hợp và counter riêng có mục đích rõ; chỉ thêm các tag nghiệp vụ hữu hạn bằng `ModulithEventMetricsCustomizer`.
- **Giữ ID/correlation chi tiết ở log/trace**, không phải trong metric tags.
- Ưu tiên enum, chuẩn hóa input, route template và loại bỏ tag thừa **ở nguồn**.
- Dùng `HighCardinalityTagsDetector` để cảnh báo sớm và `MeterFilter` làm hàng rào có kiểm soát; hiểu rằng meter bị deny đồng nghĩa **mất phép đo đó**.
- Kiểm chứng đồng thời **số meter trong app**, **series đã export**, **active/churn series tại backend** và **tác động đến dashboard/SLO**.
- Đừng đánh đồng việc giảm số series với việc hệ thống vận hành đúng: module graph, Actuator, metrics, tracing và Event Publication Registry vẫn cung cấp các loại bằng chứng khác nhau.

## Tài liệu tham khảo

1. [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html) — Phát hiện, hạn chế và lưu ý khi số meter cùng tên tăng bất thường.
2. [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html) — `maximumAllowableTags`, `maximumAllowableMetrics`, `ignoreTags` và `replaceTagValues`.
3. [Micrometer — Meters](https://docs.micrometer.io/micrometer/reference/concepts/meters.html) — Định danh meter, tên và tags.
4. [Prometheus — Metric and Label Naming](https://prometheus.io/docs/practices/naming/) — Cảnh báo về một time series cho mỗi tổ hợp nhãn và dữ liệu high cardinality.
5. [Prometheus — Instrumentation Best Practices](https://prometheus.io/docs/practices/instrumentation.html) — Chọn nhãn, tránh cardinality tăng không kiểm soát.
6. [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/2.2/production-ready.html) — Domain event counters, low-cardinality keys và customizer.
7. [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html) — Listener và Event Publication Registry.
8. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Actuator metrics, MeterRegistry và exporters.
9. [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html) — Exposure, quyền truy cập và management endpoints.

