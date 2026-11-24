# Low-cardinality key values và high-cardinality key values

Micrometer Observation cho phép gắn key-value vào context của một operation. Các key-value được chia thành hai nhóm: low-cardinality và high-cardinality. Sự phân biệt này quyết định dữ liệu nào phù hợp để tạo metrics và dữ liệu nào chỉ nên dùng trong tracing.

Low-cardinality key-values có số lượng giá trị khác nhau được kiểm soát và có thể trở thành tag của metrics. High-cardinality key-values có thể chứa nhiều giá trị riêng biệt, hữu ích khi điều tra một request hoặc một giao dịch cụ thể; chúng thường chỉ được đưa vào span của tracing. Chọn sai nhóm có thể làm số time series tăng đột biến, tăng chi phí lưu trữ và truy vấn, hoặc làm lộ dữ liệu nhạy cảm.

## 1. Key-value trong Observation

Một Observation đại diện cho một lần thực thi, ví dụ xử lý HTTP request, tìm sản phẩm, xác thực thanh toán hoặc gửi message. Context của Observation có thể mang thêm thuộc tính mô tả lần thực thi đó.

Ví dụ:

~~~java
Observation.createNotStarted("payment.authorize", registry)
    .lowCardinalityKeyValue("provider", "primary")
    .lowCardinalityKeyValue("outcome", "success")
    .highCardinalityKeyValue("payment.reference", paymentReference)
    .observe(() -> paymentService.authorize(command));
~~~

Trong ví dụ:

- provider mô tả nhóm nhà cung cấp có tập giá trị nhỏ.
- outcome mô tả kết quả trong một tập hữu hạn như success, failure hoặc rejected.
- payment.reference định danh một giao dịch cụ thể và có thể khác nhau ở mỗi lần gọi.

Cả hai nhóm đều là metadata gắn với Observation. Khác biệt nằm ở mục đích và cách các handler sử dụng chúng.

## 2. Low-cardinality key-values

Low-cardinality key-value là thuộc tính có tập giá trị khác nhau nhỏ, ổn định và có thể dự đoán. Đây là nhóm phù hợp để chuyển thành tag của metrics.

Ví dụ thường phù hợp:

| Key | Giá trị ví dụ | Lý do |
|---|---|---|
| method | GET, POST, PUT, DELETE | Tập HTTP method hữu hạn |
| route | /orders/{id}, /products/search | Route template ổn định |
| outcome | success, failure, rejected | Tập kết quả đã chuẩn hóa |
| status | 2xx, 4xx, 5xx | Nhóm trạng thái hữu hạn |
| payment.method | card, bank_transfer, wallet | Các phương thức được hỗ trợ |
| provider | primary, secondary | Danh sách provider cấu hình trước |
| region | ap-southeast-1, eu-west-1 | Tập region triển khai hữu hạn |

Low-cardinality không có nghĩa là chỉ có hai hoặc ba giá trị. Điều quan trọng là tập giá trị có giới hạn, được kiểm soát và không tăng theo từng request hoặc từng thực thể nghiệp vụ.

Có thể thêm low-cardinality values vào Observation:

~~~java
Observation observation = Observation.createNotStarted(
        "http.server.request",
        registry
    )
    .lowCardinalityKeyValue("method", request.method())
    .lowCardinalityKeyValue("route", routeTemplate)
    .lowCardinalityKeyValue("status", statusGroup);
~~~

Ở đây routeTemplate phải là route pattern do framework cung cấp, ví dụ /orders/{id}, thay vì URL thực tế /orders/983742. Giá trị route template gom nhiều request vào cùng một nhóm.

## 3. High-cardinality key-values

High-cardinality key-value là thuộc tính có thể có rất nhiều giá trị khác nhau. Nó hữu ích khi cần tìm một lần thực thi cụ thể trong trace hoặc điều tra sự cố.

Ví dụ:

- request.id: ID của request.
- order.id: ID của đơn hàng.
- payment.reference: mã tham chiếu giao dịch.
- customer.id: mã khách hàng nội bộ.
- message.id: ID của message trong broker.
- full.url: URL đầy đủ nếu chính sách dữ liệu cho phép và có nhu cầu chẩn đoán.

Các giá trị này thường không phù hợp làm metric tag vì mỗi giá trị mới có thể tạo một time series mới.

~~~java
Observation.createNotStarted("order.process", registry)
    .lowCardinalityKeyValue("operation", "process")
    .lowCardinalityKeyValue("outcome", "success")
    .highCardinalityKeyValue("order.id", orderId)
    .highCardinalityKeyValue("request.id", requestId)
    .observe(() -> orderService.process(orderId));
~~~

Handler metrics thường chỉ sử dụng low-cardinality values. Handler tracing có thể đưa cả low-cardinality và high-cardinality values vào span attributes để người vận hành tìm trace theo request hoặc order cụ thể.

High-cardinality không đồng nghĩa với dữ liệu được phép thu thập vô điều kiện. ID khách hàng, email, số điện thoại, token hoặc thông tin thanh toán vẫn có thể là dữ liệu nhạy cảm. Chỉ thêm dữ liệu thực sự cần cho điều tra, đã được phê duyệt và có retention/access policy phù hợp.

## 4. Handler sử dụng hai nhóm khác nhau

Observation không tự quyết định một key-value sẽ được lưu ở backend nào. ObservationHandler và các integration handler quyết định cách chuyển context thành tín hiệu.

| Thành phần | Low-cardinality values | High-cardinality values |
|---|---|---|
| Metrics handler | Dùng làm meter tag | Thông thường không đưa vào meter tag |
| Tracing handler | Có thể thêm vào span | Có thể thêm vào span |
| Logging handler | Có thể ghi nếu hữu ích | Chỉ ghi khi cần và được phép |
| Custom handler | Theo chính sách handler | Theo chính sách handler |

Ví dụ, một Observation có thể tạo Timer với các tag method, route và outcome. Cùng Observation đó tạo span có thêm request.id và order.id. Dashboard metrics có thể nhóm theo route và outcome; tracing có thể tìm chính xác request bị chậm.

Không giả định mọi handler đều xử lý hai nhóm giống nhau. Hãy kiểm tra handler và bridge đang dùng, bởi một custom handler có thể đưa high-cardinality values vào metrics nếu được viết không cẩn thận.

## 5. Tại sao high-cardinality làm metrics tốn kém?

Trong hệ thống time series, một tổ hợp metric name và tag values tạo thành một series riêng. Khi một tag có nhiều giá trị, số series tăng theo số tổ hợp.

Giả sử một HTTP metric có:

- 5 giá trị method.
- 40 route template.
- 3 giá trị outcome.
- 4 giá trị region.

Số tổ hợp tối đa là:

~~~text
5 × 40 × 3 × 4 = 2.400 series
~~~

Nếu thêm request.id với 100.000 giá trị trong cùng khoảng thời gian, số series có thể tăng theo số request và vượt xa ngân sách ban đầu.

Với histogram, mỗi tổ hợp tag còn có thể tạo nhiều bucket series, cùng count và sum. Nếu có 20 bucket, 2.400 tổ hợp có thể tạo khoảng 48.000 bucket series cho một metric histogram, chưa tính các series bổ sung và số instance.

Đó là lý do không đưa request ID, user ID hoặc order ID vào low-cardinality key-values. Chúng làm tăng chi phí ingest, RAM, storage, index và truy vấn của backend metrics.

## 6. Chọn key-value cho HTTP request

HTTP instrumentation là ví dụ rõ ràng nhất để phân biệt hai nhóm.

~~~java
Observation.createNotStarted("http.server.request", registry)
    .lowCardinalityKeyValue("method", request.getMethod())
    .lowCardinalityKeyValue("route", routeTemplate)
    .lowCardinalityKeyValue("status", statusGroup)
    .highCardinalityKeyValue("request.id", requestId)
    .observe(() -> dispatcher.dispatch(request));
~~~

Nên dùng:

- method: GET, POST, PUT, DELETE.
- route: route template như /customers/{id}.
- status: 2xx, 4xx, 5xx hoặc một tập trạng thái đã chọn.
- request.id: high-cardinality để tìm trace cụ thể nếu được phép.

Không dùng raw path làm route tag. Ví dụ /customers/1001 và /customers/1002 phải được chuẩn hóa về /customers/{id}. Nếu dùng path thực, số series sẽ tăng theo số khách hàng.

Query string thường chứa filter, token hoặc dữ liệu người dùng. Không đưa toàn bộ URL vào metrics tag; nếu tracing cần một phần URL, hãy loại bỏ query nhạy cảm và áp dụng quy tắc redaction.

## 7. Chọn key-value cho business operation

Với nghiệp vụ thanh toán, một bộ low-cardinality hữu ích có thể gồm:

- operation: authorize, capture, refund.
- provider: primary, secondary.
- payment_method: card, wallet, bank_transfer.
- outcome: success, rejected, failure.

Các ID cụ thể nên thuộc nhóm high-cardinality nếu được phép thu thập:

- payment.reference.
- order.id.
- request.id.

Ví dụ:

~~~java
Observation.createNotStarted("payment.operation", registry)
    .lowCardinalityKeyValue("operation", "authorize")
    .lowCardinalityKeyValue("provider", providerCode)
    .lowCardinalityKeyValue("payment_method", method.metricValue())
    .lowCardinalityKeyValue("outcome", outcome.metricValue())
    .highCardinalityKeyValue("payment.reference", paymentReference)
    .observe(() -> paymentGateway.authorize(payment));
~~~

Các giá trị provider, method và outcome phải được chuẩn hóa về enum hoặc danh sách cho phép. Không dùng chuỗi tự do do client gửi trực tiếp làm low-cardinality value.

Nếu cần phân tích theo tenant, hãy đánh giá số tenant và nhu cầu dashboard. Một hệ thống có hàng trăm nghìn tenant không nên mặc định đưa tenant ID vào metrics. Có thể nhóm theo tier, region hoặc tenant class nếu các nhóm này hữu hạn.

## 8. Chuẩn hóa giá trị trước khi gắn vào Observation

Chuẩn hóa giúp đảm bảo low-cardinality key-values luôn nằm trong tập giá trị dự kiến.

~~~java
enum Outcome {
    SUCCESS("success"),
    REJECTED("rejected"),
    FAILURE("failure");

    private final String metricValue;

    Outcome(String metricValue) {
        this.metricValue = metricValue;
    }

    String metricValue() {
        return metricValue;
    }
}
~~~

Nếu đầu vào là chuỗi bên ngoài:

~~~java
String normalizeProvider(String rawProvider) {
    return switch (rawProvider) {
        case "primary", "secondary" -> rawProvider;
        default -> "other";
    };
}
~~~

Khi đó, giá trị lạ được gom về other thay vì tạo tag mới. Tập giá trị của key provider vẫn hữu hạn.

Không nên dùng hash của ID để biến high-cardinality thành low-cardinality. Hash chỉ thay đổi hình thức của giá trị, không giảm số lượng giá trị phân biệt. Nếu cần nhóm dữ liệu, phải ánh xạ sang một phân loại nghiệp vụ hữu hạn.

## 9. Tên key và schema nhất quán

Tên key nên mô tả rõ ý nghĩa và được dùng nhất quán trên các service. Ví dụ:

| Khuyến nghị | Tránh |
|---|---|
| http.method | methodName ở service khác |
| http.route | url, path, uri dùng lẫn lộn |
| outcome | result, statusText không thống nhất |
| payment.provider | providerName, gateway tùy ý |
| request.id | requestId, req_id không thống nhất |

Một schema thống nhất giúp dashboard và query có thể dùng lại. Khi đổi tên key, hãy xem đó là thay đổi hợp đồng telemetry và kiểm tra ảnh hưởng tới metrics, traces, alert và dashboard.

Không dùng cùng một key cho hai ý nghĩa khác nhau. Ví dụ status có thể là HTTP status code hoặc trạng thái nghiệp vụ; nếu cần cả hai, dùng http.status_group và payment.outcome.

## 10. Bảo vệ privacy và dữ liệu nhạy cảm

High-cardinality values thường chứa định danh cụ thể nên cần kiểm soát chặt. Trước khi thêm vào Observation, hãy tự hỏi:

- Có cần giá trị này để điều tra sự cố không?
- Có thể dùng correlation ID đã được thiết kế cho telemetry không?
- Giá trị có chứa PII, secret hoặc dữ liệu thanh toán không?
- Backend tracing có access control và retention phù hợp không?
- Có thể redaction hoặc pseudonymize trước khi xuất không?

Không đưa các dữ liệu sau vào telemetry nếu không có cơ sở và kiểm soát rõ ràng:

- Access token, API key, session cookie.
- Password hoặc dữ liệu xác thực.
- Email, số điện thoại, địa chỉ.
- Số thẻ hoặc thông tin tài khoản ngân hàng.
- Nội dung request/response có dữ liệu cá nhân.

Hash hoặc mã hóa không tự động làm dữ liệu trở nên vô hại. Giá trị có thể vẫn liên kết được với một cá nhân hoặc được dò ngược nếu không gian đầu vào nhỏ. Ưu tiên correlation ID ngẫu nhiên, có vòng đời và quyền truy cập phù hợp.

## 11. Kiểm tra key-values trong Observation

Có thể kiểm tra rằng code gắn đúng loại key-value bằng một helper nhỏ để tập trung schema:

~~~java
import io.micrometer.observation.Observation;

public final class OrderObservationValues {
    private OrderObservationValues() {}

    public static Observation addValues(
            Observation observation,
            Order order,
            String requestId) {
        return observation
            .lowCardinalityKeyValue(
                "channel",
                order.channel().metricValue()
            )
            .lowCardinalityKeyValue(
                "outcome",
                "success"
            )
            .highCardinalityKeyValue(
                "request.id",
                requestId
            );
    }
}
~~~

Helper không tự đảm bảo cardinality thấp; trách nhiệm đó vẫn nằm ở cách tạo giá trị. Ví dụ channel phải là enum hoặc tập giá trị đã chuẩn hóa.

Trong test, nên xác minh:

- Các key phân loại như channel và outcome chỉ nhận giá trị cho phép.
- Request ID không được đưa vào low-cardinality collection.
- Observation name không chứa ID.
- Custom metrics handler không xuất high-cardinality values thành tag.
- Tracing handler chỉ nhận các thuộc tính high-cardinality được cho phép.

Có thể viết test cho hàm chuẩn hóa để mọi input không hợp lệ đều trở thành other. Với integration test, kiểm tra meter đã đăng ký chỉ chứa các tag được định nghĩa trong schema.

## 12. Các lỗi thường gặp

- **Đưa request ID vào low-cardinality:** mỗi request có thể tạo một time series.
- **Dùng URL thực thay cho route template:** path chứa ID làm số series tăng theo tài nguyên.
- **Cho rằng high-cardinality không có chi phí:** span attributes vẫn làm tăng kích thước trace và chi phí lưu trữ.
- **Đưa PII vào high-cardinality:** tracing vẫn là telemetry và cần chính sách bảo vệ dữ liệu.
- **Hash ID để giảm cardinality:** số lượng giá trị khác nhau không giảm.
- **Dùng raw input làm tag:** dữ liệu ngoài có thể tạo giá trị không giới hạn.
- **Không thống nhất tên key:** query và dashboard khó dùng chung.
- **Dùng một key cho nhiều ý nghĩa:** dữ liệu khó diễn giải.
- **Cho rằng mọi handler tự phân loại đúng:** custom handler có thể xuất nhầm high-cardinality vào metrics.
- **Không tính tích số tag và histogram bucket:** ngân sách series bị đánh giá thấp.
- **Đưa exception message vào tag:** message có thể chứa ID và dữ liệu đầu vào.

## 13. Checklist lựa chọn low và high cardinality

- [ ] Xác định câu hỏi vận hành mà mỗi key-value cần trả lời.
- [ ] Chỉ đưa tập giá trị nhỏ, ổn định vào low-cardinality.
- [ ] Dùng route template thay cho URL hoặc path thực.
- [ ] Dùng enum hoặc allowlist cho outcome, provider, channel và method.
- [ ] Đưa ID riêng của request/giao dịch vào high-cardinality chỉ khi thật sự cần.
- [ ] Không đưa secret hoặc PII vào metrics hay tracing.
- [ ] Tính cardinality theo tích số của các tag.
- [ ] Tính thêm histogram bucket và số instance.
- [ ] Kiểm tra custom handler không xuất high-cardinality thành meter tag.
- [ ] Dùng schema key thống nhất giữa các service.
- [ ] Test hàm chuẩn hóa và tập giá trị được phép.
- [ ] Theo dõi số series và kích thước trace sau triển khai.

Low-cardinality key-values giúp metrics giữ số series trong giới hạn và hỗ trợ phân nhóm vận hành. High-cardinality key-values bổ sung chi tiết để tìm một lần thực thi cụ thể trong tracing khi có nhu cầu và được phép. Hãy phân loại ngay tại nơi tạo Observation, chuẩn hóa giá trị, kiểm soát privacy và xác minh từng handler để một thuộc tính chi tiết không vô tình trở thành hàng loạt time series.

