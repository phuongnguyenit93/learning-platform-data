# Kiểm soát rủi ro số chuỗi tăng theo dữ liệu người dùng

Metrics giúp quan sát hành vi của ứng dụng qua các đại lượng như số request, thời gian xử lý, tỷ lệ lỗi và độ sâu queue. Nhưng nếu đưa dữ liệu do người dùng kiểm soát trực tiếp vào metric name hoặc tag value, mỗi request có thể tạo thêm một tổ hợp nhãn mới. Số time series tăng nhanh làm tăng bộ nhớ, CPU, lưu lượng export và chi phí lưu trữ; trong trường hợp bị khai thác có chủ đích, đây còn là một cách gây cạn tài nguyên cho ứng dụng và monitoring backend.

Metric labels cũng là một đường dữ liệu đi ra khỏi ứng dụng. User ID, email, số điện thoại, token, URL đầy đủ hoặc nội dung lỗi có thể bị lưu lâu dài trong hệ thống metrics, được sao chép sang nhiều backend và hiển thị cho người có quyền đọc dashboard. Vì vậy, kiểm soát cardinality đồng thời là biện pháp bảo vệ tính sẵn sàng và giảm nguy cơ lộ dữ liệu.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, bài này tập trung vào việc kiểm soát rủi ro số chuỗi tăng theo dữ liệu người dùng: nhận diện dữ liệu không an toàn trong tag, thiết kế nhãn có tập giá trị hữu hạn, ước lượng ngân sách time series, đặt giới hạn bằng MeterFilter, bảo vệ endpoint metrics và xử lý sự cố cardinality.

## 1. Vì sao dữ liệu người dùng có thể làm tăng số time series?

Micrometer định danh một meter bằng tên và tập tag. Khi một tag value thay đổi, registry có thể đăng ký một meter riêng cho tổ hợp mới. Khi metrics được scrape hoặc export, mỗi tổ hợp label khác nhau thường trở thành một time series riêng ở backend.

Ví dụ:

~~~java
registry.counter(
        "checkout.requests",
        "channel", "web"
).increment();

registry.counter(
        "checkout.requests",
        "channel", "mobile"
).increment();
~~~

Hai lần ghi trên dùng cùng tên meter nhưng có hai giá trị channel khác nhau, nên tạo hai meter identity khác nhau.

Nếu đưa user ID vào tag:

~~~java
registry.counter(
        "checkout.requests",
        "user.id", userId
).increment();
~~~

mỗi user có thể tạo một chuỗi mới. Nếu đưa request ID vào tag, gần như mỗi request tạo một chuỗi mới. Số meter không còn bị giới hạn bởi số loại nghiệp vụ mà tăng theo lượng dữ liệu đầu vào.

Một metric có thể được ghi hàng triệu lần mà vẫn dùng một time series nếu name và label set ổn định. Ngược lại, chỉ vài nghìn request với các ID khác nhau cũng có thể tạo ra vài nghìn series mới.

## 2. Dữ liệu nào không nên trở thành metric label?

Không dùng dữ liệu định danh hoặc nội dung tự do làm metric tag:

| Dữ liệu đầu vào | Rủi ro | Nơi phù hợp hơn |
|---|---|---|
| user ID, customer ID | Cardinality cao; có thể là dữ liệu cá nhân | Trace hoặc log có kiểm soát truy cập |
| Email, số điện thoại, địa chỉ | Lộ thông tin cá nhân; giá trị gần như không giới hạn | Hệ thống nghiệp vụ được bảo vệ |
| request ID, correlation ID, trace ID | Mỗi request có giá trị riêng | Trace context, log và exemplar |
| session ID, device ID | Tăng theo số phiên hoặc thiết bị | Log/trace hoặc phân tích chuyên dụng |
| order ID, payment ID, transaction ID | Tăng theo số giao dịch | Trace/log và kho dữ liệu nghiệp vụ |
| URL đầy đủ, query string | Có thể chứa ID, search term hoặc token | Route template đã chuẩn hóa |
| User-Agent, Referer, header tùy ý | Giá trị tự do và có thể bị giả mạo | Log đã lọc hoặc nhóm category |
| Exception message, SQL có literal | Nội dung biến thiên, đôi khi chứa dữ liệu nhạy cảm | Log/trace đã redaction |

Một tag có vẻ kỹ thuật vẫn có thể chứa dữ liệu do client kiểm soát. Ví dụ path, query, header, tenant, region, client.name hoặc error cần được kiểm tra nguồn tạo và tập giá trị trước khi đưa vào metrics.

Không coi việc một trường có tên "technical" là bằng chứng nó an toàn. Hãy xác định ai có thể gửi giá trị đó, giá trị có thể thay đổi bao nhiêu và liệu nó có chứa thông tin nhạy cảm hay không.

## 3. Hai nhóm rủi ro: cạn tài nguyên và rò rỉ dữ liệu

High cardinality tạo ra hai nhóm rủi ro độc lập:

**Rủi ro sẵn sàng hệ thống**

- Registry giữ thêm meter, tag và trạng thái thống kê trong heap.
- Đăng ký và tra cứu meter tốn CPU.
- Garbage collection chịu thêm áp lực khi liên tục tạo object.
- Scrape/push payload lớn hơn, tăng thời gian export và băng thông.
- Backend phải index và lưu nhiều series hơn.
- Dashboard, query, recording rule và alert có thể chậm hoặc vượt giới hạn backend.

**Rủi ro bảo mật và quyền riêng tư**

- Metric labels có thể chứa user ID, email, token hoặc dữ liệu nghiệp vụ.
- Endpoint metrics có thể để lộ tên service, route nội bộ, dependency, exception class và trạng thái hệ thống.
- Dữ liệu metrics thường được giữ lâu và sao chép sang nhiều môi trường.
- Người có quyền đọc metrics có thể không có quyền đọc dữ liệu nghiệp vụ gốc.
- Một giá trị do client gửi có thể được lưu trong hệ thống observability của bên thứ ba.

Việc loại bỏ PII khỏi metrics không thay thế kiểm soát truy cập. Ngược lại, bảo vệ endpoint không làm cho tag cardinality cao trở nên an toàn về tài nguyên.

## 4. Kẻ tấn công có thể tạo cardinality bằng cách nào?

Một endpoint công khai có thể nhận request với đường dẫn, query parameter hoặc header tùy ý. Nếu instrumentation đưa các giá trị đó vào tag, client có thể chủ động tạo nhiều label set khác nhau.

Ví dụ đường dẫn động:

~~~text
GET /orders/8b9d...
GET /orders/41c2...
GET /orders/f7a1...
~~~

Nếu metric tag dùng request.getRequestURI(), mỗi order ID có thể tạo một giá trị route riêng.

Ví dụ header do client điều khiển:

~~~text
X-Client-Name: client-000001
X-Client-Name: client-000002
X-Client-Name: client-000003
~~~

Nếu header được đưa thẳng vào tag, client có thể tạo series mới mà không cần tạo tài khoản mới hoặc thực hiện giao dịch thành công.

Các kiểu khai thác thường gặp:

- Gửi nhiều URL ngẫu nhiên hoặc path chứa UUID.
- Gửi query parameter có giá trị ngẫu nhiên.
- Thay đổi header hoặc User-Agent ở mỗi request.
- Tạo nhiều tenant hoặc identifier giả nếu hệ thống cho phép.
- Kích hoạt exception có message chứa dữ liệu đầu vào.
- Gửi tên operation hoặc metric name được ghép từ dữ liệu client.

Cardinality exhaustion có thể xảy ra do bug hoặc cấu hình sai, không nhất thiết cần có hành vi tấn công. Hãy coi mọi dữ liệu ngoài phạm vi kiểm soát của ứng dụng là không đáng tin khi thiết kế metric labels.

## 5. Ước lượng ngân sách time series

Với một metric family, số tổ hợp label tối đa có thể ước lượng bằng tích cardinality của từng label:

\[
S_{\text{per target}} \approx \prod_{i=1}^{n} C_i
\]

Trong đó C_i là số giá trị dự kiến của label thứ i. Tổng số series còn bị nhân theo số instance/target và các chiều do hệ thống scrape thêm như job hoặc instance.

Ví dụ:

| Label | Số giá trị dự kiến |
|---|---:|
| route template | 30 |
| method | 5 |
| status class | 5 |
| region | 3 |

Số tổ hợp trên một instance:

\[
30 \times 5 \times 5 \times 3 = 2.250
\]

Nếu có 12 instance, có thể có khoảng 27.000 series cho metric family đó, trước khi tính thêm các series được sinh bởi histogram hoặc các dimension khác.

Nếu thêm user.id với 100.000 giá trị, giới hạn lý thuyết tăng lên:

\[
2.250 \times 100.000 \times 12
= 2.700.000.000
\]

Đây là ước lượng upper bound; số thực tế phụ thuộc tổ hợp nào xuất hiện. Tuy nhiên, chỉ riêng phép tính cho thấy user ID không phù hợp với một label của metrics tổng hợp.

## 6. Histogram làm tăng số series theo mỗi label set

Timer hoặc DistributionSummary có histogram có thể xuất nhiều series cho cùng một tổ hợp tag. Với Prometheus classic histogram, mỗi label set tạo các bucket series, gồm các bucket hữu hạn và bucket +Inf, cùng _sum và _count.

Nếu histogram có 10 ranh giới bucket hữu hạn, một label set có thể tạo khoảng 13 series: 11 bucket (10 ranh giới và +Inf), _sum và _count. Số cụ thể phụ thuộc registry, cấu hình histogram và exporter.

Quay lại ví dụ có 27.000 label set trên 12 instance:

\[
27.000 \times 13 = 351.000
\]

Một histogram có thể làm số series lớn hơn nhiều so với số meter logic. Vì vậy, ngân sách cardinality cần tính cả label set và loại meter, không chỉ đếm số meter trong JVM.

Tránh bật percentile/histogram cho một metric đã có nhiều chiều tag mà chưa đánh giá số bucket, số instance và giới hạn backend.

## 7. Thiết kế metric name ổn định và tag có allowlist

Metric name nên mô tả đại lượng đo; tag nên là những chiều phân loại có tập giá trị hữu hạn.

Ví dụ với đơn hàng:

~~~java
private static final Set<String> ALLOWED_CHANNELS =
        Set.of("web", "mobile", "partner");

private String normalizeChannel(String rawChannel) {
    if (rawChannel == null) {
        return "other";
    }

    return ALLOWED_CHANNELS.contains(rawChannel)
            ? rawChannel
            : "other";
}

public void recordOrder(
        MeterRegistry registry,
        String rawChannel,
        String rawUserId) {

    String channel = normalizeChannel(rawChannel);

    registry.counter(
            "orders.created",
            "channel", channel
    ).increment();

    // rawUserId có thể được ghi vào trace/log đã được bảo vệ,
    // nhưng không đưa vào metric tag.
}
~~~

Các request có channel không hợp lệ được gom vào other. Dữ liệu user ID không tham gia meter identity. Tập giá trị channel được định nghĩa bởi ứng dụng, nên số series có thể dự đoán.

Không dùng String.valueOf(rawValue) như một cách chuẩn hóa. Việc chuyển dữ liệu sang chuỗi không giới hạn cardinality của nó.

## 8. Dùng route template thay cho request URI

Trong Spring MVC, có thể lấy route pattern đã được framework match thay vì URI thực tế:

~~~java
Object pattern = request.getAttribute(
        HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE
);

String route = pattern != null
        ? pattern.toString()
        : "unmatched";
~~~

Ví dụ:

| Request URI | Route template |
|---|---|
| /orders/10001 | /orders/{id} |
| /orders/10002 | /orders/{id} |
| /customers/abc-123/profile | /customers/{id}/profile |

Cả hai request order sẽ dùng cùng route label. Điều này giữ được phân tích theo endpoint mà không tạo một series cho từng order.

Nếu framework không cung cấp route template, hãy ánh xạ URI vào một tập route đã biết. Với đường dẫn không khớp, gom về unmatched hoặc other; không dùng raw path làm fallback.

Với WebFlux, dùng route pattern hoặc observation convention do framework cung cấp. Không lấy raw URI hay query string rồi đưa vào tag chỉ vì nó có sẵn trong request object.

## 9. Chuẩn hóa outcome và error category

Không dùng exception message hoặc nội dung lỗi từ downstream làm tag:

~~~java
// Không an toàn: message có thể chứa URL, ID hoặc dữ liệu request.
registry.counter(
        "payment.failures",
        "error", exception.getMessage()
).increment();
~~~

Thay vào đó, ánh xạ về category hữu hạn:

~~~java
private String errorCategory(Throwable error) {
    if (error instanceof java.net.SocketTimeoutException) {
        return "timeout";
    }
    if (error instanceof java.net.ConnectException) {
        return "connection";
    }
    if (error instanceof IllegalArgumentException) {
        return "invalid_input";
    }
    return "other";
}
~~~

Nếu cần giữ exception class để phân tích, cân nhắc dùng class name sau khi kiểm soát tập loại exception có thể xuất hiện. Một thư viện hoặc plugin có thể bổ sung class mới, vì vậy class name cũng cần được xem xét như một dimension có cardinality hữu hạn nhưng có thể tăng theo version.

Không gộp tất cả lỗi nghiệp vụ và lỗi kỹ thuật thành một giá trị nếu dashboard cần phân biệt chúng. Hãy thiết kế category vừa đủ cho câu hỏi vận hành và tránh đưa nội dung tự do vào tag.

## 10. Không ghép dữ liệu đầu vào vào metric name

Metric name động cũng có thể tạo cardinality cao, ngay cả khi tag set rỗng:

~~~java
// Không dùng dữ liệu đầu vào để tạo metric name.
registry.counter("user." + userId + ".login").increment();
~~~

Tên meter nên ổn định:

~~~java
registry.counter(
        "user.login",
        "method", normalizeLoginMethod(method)
).increment();
~~~

Một metric name động còn làm detector theo tên khó phát hiện, vì mỗi meter có thể nằm dưới một tên khác nhau. Hãy giữ tên meter là hằng số hoặc được tạo từ một tập operation đã định nghĩa trong code.

## 11. Dùng Observation để tách metric dimension và dữ liệu chi tiết

Observation hỗ trợ hai nhóm key-value:

- Low-cardinality key-value: phù hợp làm metric tags và metadata tracing.
- High-cardinality key-value: dành cho handler có thể xử lý dữ liệu chi tiết, thường là tracing hoặc logging.

Ví dụ:

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

DefaultMeterObservationHandler dùng low-cardinality key-value để tạo metric tags và bỏ qua high-cardinality key-value. Nhờ đó, metric vẫn có thể phân tích theo loại đơn hàng và kết quả mà không tạo series cho từng order/customer.

Tuy nhiên, high-cardinality không có nghĩa là dữ liệu đó tự động an toàn. Tracing handler có thể export các giá trị này sang tracing backend. Không đưa email, token, số điện thoại hoặc dữ liệu nhạy cảm vào high-cardinality field nếu chưa có chính sách redaction, quyền truy cập và retention phù hợp.

## 12. Dùng exemplar thay vì trace ID làm label

Khi cần chuyển từ một metric sample đến trace cụ thể, exemplar là cơ chế phù hợp hơn việc thêm trace ID vào metric tag.

Exemplar có thể gắn một trace reference với một sample mà không biến trace ID thành dimension của time series. Khả năng này phụ thuộc registry, exporter, backend và cấu hình tracing.

Ví dụ tư duy:

~~~text
Metric:
http.server.request.duration
  route="/orders/{id}"
  method="GET"
  status="2xx"

Exemplar:
  trace_id="..."
~~~

Metric giữ label set ổn định. Exemplar cho phép người vận hành mở trace đại diện để xem chi tiết request mà không tạo một time series riêng cho từng trace.

Không phải mọi backend đều hỗ trợ exemplar theo cùng cách. Nếu chưa có exemplar, giữ trace ID trong tracing/logging và liên kết bằng công cụ phù hợp; không đưa nó thành metric tag để thay thế.

## 13. Dùng MeterFilter làm hàng rào bảo vệ

Chuẩn hóa đầu vào trong code là biện pháp chính. MeterFilter cung cấp thêm hàng rào ở registry để bỏ tag hoặc từ chối meter vượt giới hạn.

Loại bỏ tag không được phép:

~~~java
registry.config()
        .meterFilter(MeterFilter.ignoreTags(
                "user.id",
                "request.id",
                "session.id",
                "email"
        ));
~~~

Giới hạn số giá trị của một tag key:

~~~java
registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
                "orders.created",
                "channel",
                4,
                MeterFilter.deny()
        )
);
~~~

Giới hạn tổng số meter trong registry:

~~~java
registry.config().meterFilter(
        MeterFilter.maximumAllowableMetrics(10_000)
);
~~~

Các filter nên được cấu hình trước khi meter được đăng ký. Filter không tự xóa những meter đã tồn tại trước đó.

maximumAllowableTags chỉ giới hạn một tag key cho các meter name khớp prefix; nó không chứng minh mọi tổ hợp tag khác đều an toàn. maximumAllowableMetrics là giới hạn tổng ở registry, không phải ngân sách riêng cho từng nghiệp vụ.

Khi filter từ chối meter, instrumentation có thể nhận một meter no-op và dữ liệu tương ứng không được ghi. Vì vậy, giới hạn quá thấp có thể làm mất metrics quan trọng. Hãy chọn ngưỡng dựa trên ngân sách đã tính, theo dõi tình trạng bị từ chối và kiểm thử hành vi khi đạt giới hạn.

## 14. Bảo vệ endpoint metrics

Endpoint như /actuator/prometheus thường chứa nhiều thông tin vận hành: tên meter, label values, route, trạng thái dependency và một phần cấu trúc nội bộ của ứng dụng. Dù endpoint chỉ đọc, nó vẫn có thể tiết lộ thông tin hữu ích cho người không được phép.

Các biện pháp cần áp dụng:

- Chỉ expose endpoint metrics thực sự cần thiết.
- Đặt endpoint trong mạng quản trị hoặc mạng scrape nội bộ.
- Dùng authentication và authorization để chỉ scraper/monitoring agent được phép truy cập.
- Dùng TLS khi metrics đi qua mạng không hoàn toàn tin cậy.
- Không mở endpoint metrics trực tiếp ra Internet nếu không có lý do và lớp bảo vệ phù hợp.
- Giới hạn quyền đọc dashboard, query API và dữ liệu lưu trữ metrics.
- Tách quyền đọc metrics khỏi quyền truy cập log, trace và dữ liệu nghiệp vụ nếu chính sách yêu cầu.

Ví dụ giới hạn các endpoint được expose trong Spring Boot:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Cấu hình exposure chỉ quyết định endpoint nào được đưa ra web layer; nó không tự thay thế authentication, authorization, firewall hoặc network policy. Cần cấu hình Spring Security và hạ tầng triển khai để bảo vệ endpoint theo đúng mô hình truy cập.

Không đặt credential, token hoặc dữ liệu bí mật trong metric label với giả định endpoint nội bộ sẽ luôn an toàn. Metrics có thể được chuyển qua remote write, collector, SaaS backend, dashboard export và hệ thống lưu trữ khác.

## 15. Dữ liệu metrics cần tuân theo chính sách dữ liệu

Trước khi thêm một label, xác định:

1. Dữ liệu đến từ code nội bộ, cấu hình hay request bên ngoài?
2. Người dùng có thể tự chọn hoặc thay đổi giá trị không?
3. Giá trị có phải dữ liệu cá nhân, bí mật xác thực hoặc thông tin nghiệp vụ nhạy cảm không?
4. Tập giá trị có giới hạn và có thể dự đoán không?
5. Monitoring backend nào sẽ nhận dữ liệu và ai có quyền đọc?
6. Dữ liệu được giữ trong bao lâu và có được sao chép sang bên thứ ba không?

Metric labels thường có vòng đời khác với log và trace. Chúng được index để truy vấn nhanh, nên một label chứa PII vừa làm tăng cardinality vừa tạo bản sao dữ liệu cá nhân trong hệ thống observability.

Hãy áp dụng data minimization: chỉ thu thập dimension cần thiết để trả lời câu hỏi vận hành. Nếu dashboard chỉ cần biết request thành công hay lỗi, không cần lưu user ID. Nếu cần điều tra một user cụ thể, dùng hệ thống có quyền truy cập và retention phù hợp.

## 16. Đo và cảnh báo cardinality

Nên theo dõi cả phía ứng dụng lẫn monitoring backend.

| Vị trí | Tín hiệu cần quan sát | Ý nghĩa |
|---|---|---|
| MeterRegistry | Số meter đã đăng ký, meter mới theo thời gian | Phát hiện instrumentation tạo identity mới |
| HighCardinalityTagsDetector | Tên meter có nhiều tổ hợp tag | Tìm tag value tăng bất thường |
| Prometheus/backend | Active series và series mới | Theo dõi chi phí lưu trữ thực tế |
| Scrape target | Scrape duration, response size, scrape errors | Phát hiện payload lớn hoặc endpoint chậm |
| Remote write/collector | Queue, retry, dropped samples, export failures | Phát hiện áp lực chuyển tiếp dữ liệu |
| JVM | Heap, allocation rate, GC pause | Nhận biết tác động trong ứng dụng |

Có thể dùng HighCardinalityTagsDetector để phát hiện nhiều meter cùng tên có tag set khác nhau:

~~~java
import java.time.Duration;

import io.micrometer.core.instrument.HighCardinalityTagsDetector;

registry.config().withHighCardinalityTagsDetector(r ->
        new HighCardinalityTagsDetector.Builder(r)
                .threshold(1_000)
                .delay(Duration.ofMinutes(5))
                .build()
);
~~~

Ngưỡng 1.000 chỉ là ví dụ. Detector giúp phát hiện meter cùng tên có quá nhiều tổ hợp tag; nó không tự chặn meter và không phát hiện tốt trường hợp metric name bị tạo động. Kết hợp detector với kiểm tra tổng meter count và backend active series.

Cảnh báo nên dựa trên baseline và tốc độ tăng, không chỉ một con số tuyệt đối. Ví dụ, cảnh báo khi active series tăng nhiều lần so với baseline trong thời gian ngắn hoặc scrape duration liên tục tiến sát timeout.

## 17. Kiểm thử để chứng minh dữ liệu đầu vào không tạo series mới

Có thể viết unit test xác nhận hàng nghìn user ID không làm tăng số meter vì user ID không được dùng làm tag:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Set;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class UserDataCardinalityTest {

    private static final Set<String> ALLOWED_CHANNELS =
            Set.of("web", "mobile", "partner");

    private String normalizeChannel(String raw) {
        return raw != null && ALLOWED_CHANNELS.contains(raw)
                ? raw
                : "other";
    }

    private void recordOrder(
            MeterRegistry registry,
            String rawChannel,
            String userId) {
        String channel = normalizeChannel(rawChannel);
        registry.counter(
                "orders.created",
                "channel", channel
        ).increment();

        // userId vẫn có thể phục vụ nghiệp vụ hoặc trace đã được bảo vệ,
        // nhưng không tham gia metric identity.
    }

    @Test
    void userIdentifiersDoNotCreateAdditionalMeters() {
        MeterRegistry registry = new SimpleMeterRegistry();

        try {
            for (int i = 0; i < 1_000; i++) {
                String userId = "user-" + i;
                recordOrder(registry, "web", userId);
            }

            assertThat(registry.getMeters()).hasSize(1);
            assertThat(registry.get("orders.created")
                    .tag("channel", "web")
                    .counter()
                    .count()).isEqualTo(1_000.0);
        }
        finally {
            registry.close();
        }
    }
}
~~~

Test kiểm tra rằng số meter không phụ thuộc số user ID. Trong dự án thực tế, không cần assert nội dung user ID; thay vào đó, truyền các giá trị khác nhau qua instrumentation public method và xác nhận chúng không xuất hiện trong meter tags.

Kiểm thử thêm:

- Các route có ID khác nhau cùng ánh xạ về một route template.
- Channel không nằm trong allowlist được gom thành other.
- Query string và header tùy ý không xuất hiện trong meter ID.
- MeterFilter.maximumAllowableTags từ chối giá trị vượt giới hạn.
- maximumAllowableMetrics không làm mất meter thiết yếu khi ứng dụng khởi động.
- Endpoint metrics yêu cầu đúng quyền truy cập.
- Metrics export không chứa email, token hoặc dữ liệu cá nhân đã bị cấm.

## 18. Ví dụ kiểm thử MeterFilter giới hạn tag

Một test khác xác nhận registry từ chối tag value mới sau khi đạt ngưỡng:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.MeterFilter;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MeterTagLimitTest {

    @Test
    void deniesNewTagValuesAfterLimit() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();

        try {
            registry.config().meterFilter(
                    MeterFilter.maximumAllowableTags(
                            "orders.created",
                            "channel",
                            3,
                            MeterFilter.deny()
                    )
            );

            registry.counter(
                    "orders.created", "channel", "web").increment();
            registry.counter(
                    "orders.created", "channel", "mobile").increment();
            registry.counter(
                    "orders.created", "channel", "partner").increment();
            registry.counter(
                    "orders.created", "channel", "unexpected").increment();

            assertThat(registry.getMeters()).hasSize(3);
        }
        finally {
            registry.close();
        }
    }
}
~~~

Test xác nhận meter thứ tư không được đăng ký sau khi có ba giá trị channel. Trong code production, hãy ghi nhận và cảnh báo khi guardrail bị kích hoạt theo cơ chế không tạo thêm log flood. Không dựa vào việc từ chối meter như cách chuẩn hóa dữ liệu; giá trị ngoài allowlist vẫn cần được ánh xạ về other trước khi gọi registry.

## 19. Ứng phó khi cardinality tăng đột biến

Khi active series, meter count hoặc scrape payload tăng bất thường:

1. Xác định metric family hoặc meter name tăng nhanh nhất.
2. Xem label keys và các label values mới xuất hiện.
3. Kiểm tra request path, query, header, user/tenant ID và exception message có được đưa vào tag hay không.
4. Kiểm tra metric name có được ghép từ dữ liệu đầu vào không.
5. Tạm thời áp dụng filter hoặc giới hạn tag phù hợp nếu cần giảm tác động.
6. Sửa instrumentation để dùng route template, category và allowlist.
7. Chuyển dữ liệu định danh cần điều tra sang trace/log đã được bảo vệ và redaction.
8. Kiểm tra endpoint metrics có bị truy cập ngoài mạng scrape dự kiến không.
9. Theo dõi meter count, active series, scrape duration, heap và GC sau khi triển khai sửa lỗi.
10. Xem xét dữ liệu đã được gửi tới backend; áp dụng quy trình retention/deletion của tổ chức nếu phát hiện PII hoặc secret.

Nếu dữ liệu nhạy cảm đã được export, việc sửa code chỉ ngăn dữ liệu mới. Cần đánh giá các bản sao đã tồn tại trong collector, remote write, TSDB, dashboard export và backup theo chính sách incident/data governance.

## 20. Checklist bảo mật và vận hành

Trước khi đưa metrics vào production, xác nhận:

- Metric name không chứa dữ liệu request hoặc entity.
- Không có user ID, email, phone, token, session ID hoặc trace ID trong metric tags.
- Route dùng template; query string và raw URL không được export thành tag.
- Mọi giá trị do client điều khiển được chuẩn hóa qua allowlist hoặc category hữu hạn.
- Exception message và nội dung SQL không được dùng làm tag.
- Đã tính cardinality theo tổ hợp label, số instance và histogram buckets.
- Đã đặt ngân sách active series phù hợp với backend.
- MeterFilter giới hạn tag và tổng meter được cấu hình như guardrail.
- HighCardinalityTagsDetector hoặc cơ chế tương đương được bật để phát hiện bất thường.
- Endpoint metrics chỉ expose phần cần thiết và được bảo vệ bằng network policy, authentication, authorization và TLS phù hợp.
- Dashboard/query API có quyền truy cập theo vai trò.
- Tracing/logging có redaction và retention riêng cho dữ liệu định danh.
- Exemplar được cân nhắc nếu cần liên kết metric sample với trace.
- Test xác nhận user input không làm tăng meter count ngoài dự kiến.
- Có cảnh báo cho active series, series churn, scrape duration, export backlog và heap/GC.

Số time series tăng theo dữ liệu người dùng là vấn đề vừa về hiệu năng vừa về bảo mật. Giữ metric name ổn định, chỉ dùng tag có tập giá trị hữu hạn, tách ID khỏi metrics, giới hạn registry và bảo vệ endpoint sẽ giảm nguy cơ cardinality exhaustion cũng như rò rỉ dữ liệu. Khi cần điều tra một request cụ thể, dùng trace/log được kiểm soát thay vì biến định danh của request thành một phần của metric identity.

## Tài liệu tham khảo

- [Micrometer - Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html)
- [Micrometer - High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html)
- [Micrometer - Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Spring Boot - Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot - Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Prometheus - Data Model](https://prometheus.io/docs/concepts/data_model/)
- [Prometheus - Histograms and Summaries](https://prometheus.io/docs/practices/histograms/)
