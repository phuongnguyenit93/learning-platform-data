# Tag theo tenant, request và dữ liệu nghiệp vụ

Trong ứng dụng Spring Boot được chia thành các **application module** bằng Spring Modulith, telemetry thường cần trả lời đồng thời ba câu hỏi: **module nào** đang xử lý, **yêu cầu nào** bị chậm và **nhóm khách hàng/nghiệp vụ nào** chịu ảnh hưởng? Các tag (nhãn) của Micrometer metrics rất hữu ích để nhóm số liệu theo những chiều như `application.module`, `tenant.tier` hoặc `http.route`. Tuy nhiên, nếu thêm trực tiếp `tenantId`, `requestId` hay `orderId` vào tag, số chuỗi thời gian có thể tăng theo lượng khách hàng và yêu cầu, gây tốn bộ nhớ, chi phí lưu trữ và làm dashboard khó sử dụng.

Bài thuộc chương **Cardinality** của chủ đề `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Ta sẽ lựa chọn tag theo **tenant, request và dữ liệu nghiệp vụ**, xác định khi nào nên giữ thuộc tính để truy vết ở trace/log thay vì metric, rồi kiểm chứng bằng Spring Boot Actuator và backend Prometheus. Trọng tâm không phải “thêm được nhiều nhãn”, mà là **tạo tín hiệu đủ hữu ích để kiểm chứng module graph, tương tác module và event processing mà vẫn kiểm soát được chi phí quan sát**.

> **Phạm vi phiên bản:** Mã minh họa dùng Spring Boot 3.x, Micrometer Observation và các phiên bản Spring Modulith tương thích. Tên meter/span hoặc tag tự động của các thư viện có thể khác theo phiên bản và cấu hình. Các tên như `tenant.tier`, `shop.order.process` là **quy ước do ví dụ tự đặt**, không phải mặc định được Spring Modulith bảo đảm tạo.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **cardinality** của một label, tổ hợp labels và số **time series**.
2. Phân loại các trường tenant, request và nghiệp vụ theo mức độ an toàn khi dùng làm metric tags.
3. Chọn nhãn tenant dạng **nhóm hữu hạn** thay cho tenant ID không kiểm soát.
4. Dùng **HTTP route template** thay vì raw URL chứa ID trong metric.
5. Phân biệt low-cardinality metric labels với high-cardinality trace attributes, logs và định danh nghiệp vụ.
6. Ước lượng ngân sách số series dựa trên số giá trị của từng chiều và số instance.
7. Viết observation với tag chuẩn hóa, thêm guardrail Micrometer và kiểm tra kết quả tại Actuator/Prometheus.
8. Xác định tác động của asynchronous events, retry và context propagation đến nhãn và việc đọc dữ liệu.

## 2. Tag, cardinality và time series

Trong Micrometer, một meter được phân biệt bởi **tên meter** và **bộ key–value tags**. Hai meter cùng tên nhưng khác một giá trị tag thường tương ứng với hai series riêng khi xuất ra backend metrics.

Ví dụ một timer đo thời gian xử lý đơn:

~~~text
shop.order.process{application.module="order", tenant.tier="standard"}
shop.order.process{application.module="order", tenant.tier="premium"}
shop.order.process{application.module="order", tenant.tier="enterprise"}
~~~

Đây là ký hiệu **khái niệm**, không phải văn bản Prometheus xuất nguyên dạng này. Micrometer và Prometheus thường chuẩn hóa dấu chấm, hậu tố timer và tên nhãn.

**Cardinality của một tag** là số giá trị khác nhau có thể xuất hiện ở tag ấy trong phạm vi dữ liệu đang xét.

| Tag | Tập giá trị ví dụ | Cardinality | Đánh giá |
| --- | --- | ---: | --- |
| `application.module` | `order`, `inventory`, `billing` | 3 | Thấp, nếu kiến trúc được quản lý |
| `tenant.tier` | `standard`, `premium`, `enterprise` | 3 | Thấp, nếu tier được chuẩn hóa |
| `order.channel` | `web`, `mobile`, `partner` | 3 | Thấp |
| `outcome` | `success`, `business_error`, `technical_error` | 3 | Thấp |
| `http.route` | `/orders/{id}`, `/inventory/{sku}`, ... | Tùy số tuyến | Có thể thấp nếu route template hữu hạn |
| `tenant.id` | ID của mỗi tổ chức sử dụng hệ thống | Có thể hàng chục nghìn | Cao trong hệ thống SaaS nhiều tenant |
| `request.id` | UUID cho từng HTTP request | Gần theo số request | Rất cao |
| `order.id` | UUID/mã đơn hàng | Gần theo số đơn | Rất cao |
| `exception.message` | Nội dung lỗi tự do | Khó giới hạn | Cao, không ổn định |

**Low cardinality không phụ thuộc độ dài chuỗi.** Một ID chỉ gồm bốn ký tự vẫn nguy hiểm nếu có hàng nghìn biến thể; một tên nhóm dài nhưng chỉ có ba giá trị lại có thể an toàn.

### Vì sao nhiều tag ít giá trị vẫn gây nhiều series?

Giả sử một metric có:

- 3 giá trị của `tenant.tier`;
- 5 HTTP route templates;
- 3 loại `outcome`;
- 4 application instances.

Tối đa số tổ hợp khi các chiều độc lập và mọi tổ hợp xuất hiện:

\[
N_{\text{series}} \leq 3 \times 5 \times 3 \times 4 = 180.
\]

Đây là **ước lượng trần cho một tên metric và bộ chiều đã xét**, không phải luôn có đúng 180 series. Backend có thể thêm những nhãn khác như `job`, `instance`, `environment`; timer/histogram cũng có nhiều series thành phần. Với hàng chục metric names và nhiều versions deploy, tổng ngân sách tiếp tục tăng.

Thay `tenant.tier` bằng `tenant.id` có 20.000 giá trị, trần tăng thành:

\[
20{,}000 \times 5 \times 3 \times 4 = 1{,}200{,}000.
\]

Sự khác biệt không nằm ở số request đến hệ thống, mà ở việc mỗi giá trị tag mới **định nghĩa một bộ meter/series mới**. Một counter có một tỷ lần tăng vẫn có thể chỉ là một series; một triệu tag combinations có thể tạo một triệu series dù mỗi series chỉ ghi một lần.

~~~mermaid
flowchart LR
    Event["Lượng request tăng"] --> Counter["Counter value tăng"]
    Label["Nhãn chứa tenantId/requestId"] --> Values["Số giá trị tag tăng"]
    Values --> Meters["Số meter/time series tăng"]
    Meters --> Cost["RAM, scrape, lưu trữ và query tốn kém"]
~~~

## 3. Tag theo tenant: phân biệt tenant ID và nhóm tenant

Trong hệ thống multi-tenant, một **tenant** thường đại diện cho tổ chức hoặc khách hàng sử dụng ứng dụng. Tenant ID hữu ích cho phân quyền, cô lập dữ liệu và truy vết sự cố của từng khách; nhưng không mặc nhiên phù hợp làm metric tag.

### Ba cấp nhu cầu quan sát tenant

| Nhu cầu | Thiết kế phù hợp | Điều cần tránh |
| --- | --- | --- |
| Biết nhóm khách nào đang có tỷ lệ lỗi cao | Metric với `tenant.tier`, `tenant.segment` hoặc nhóm nhỏ có kiểm soát | Đưa mọi tenant ID vào mọi metric |
| Biết một tenant cụ thể đã gặp lỗi gì | Traces/logs và dữ liệu nghiệp vụ có quyền truy cập theo tenant | Đưa raw tenant ID vào mọi timer/counter |
| Đo SLA riêng cho một tập tenant hợp đồng đặc biệt | Pipeline/metric riêng có **danh sách tenant hữu hạn**, quota và phân quyền rõ | Tự động mở rộng allowlist theo mỗi tenant mới |

Trong SaaS có vài chục tenant cố định và SLA bắt buộc theo từng tenant, một nhãn tenant ID **có thể** được chấp nhận nếu đã tính ngân sách, bảo mật và lộ trình tăng trưởng. Quy tắc không phải “mọi tenant ID luôn bị cấm”, mà là **không dùng ID có số lượng tăng không kiểm soát như label mặc định của mọi metric**.

### Nên gắn nhãn theo thông tin tin cậy nào?

Giả sử hệ thống có các tier `standard`, `premium` và `enterprise`. Tên tier cần xuất phát từ **mapping phía server** sau khi xác thực tenant, không lấy thẳng từ HTTP header hoặc query parameter do client tự điền.

**Sai:**

~~~java
// Không dùng trực tiếp đầu vào do client tùy ý gửi làm metric tag.
String tenantTag = request.getHeader("X-Tenant-Id");
counter.tag("tenant.id", tenantTag);
~~~

Đoạn trên vừa tạo cardinality không kiểm soát, vừa cho phép client tự gắn nhãn sai về tenant. Trong hệ thống nhiều tenant, đây còn có thể làm sai báo cáo vận hành và lộ thông tin giữa khách hàng.

**Đúng hướng:** lấy tenant identity từ cơ chế xác thực/ủy quyền đáng tin cậy; chuyển thành một **nhóm hữu hạn** bằng cấu hình server-side; chỉ đưa nhóm ấy vào metric. Tenant ID nếu cần điều tra riêng phải được truy vấn trong hệ thống log/trace/nghiệp vụ với phân quyền phù hợp.

## 4. Tag theo request: route template, method và status

Request thường có các trường:

~~~text
GET /orders/8e53b48f-0f0d-4f75-b985-1a1c5c36d419?customer=42
X-Request-Id: 7a92...
X-Tenant-Id: t_10283
~~~

Nếu coi toàn bộ raw path/query/header là metric tags, mỗi yêu cầu có thể sinh một tổ hợp mới. Thay vào đó, với HTTP server metrics, nên ưu tiên các trường đã được **chuẩn hóa**:

| Trường | Ví dụ an toàn | Cần tránh |
| --- | --- | --- |
| HTTP method | `GET`, `POST`, `PUT` | Giá trị tự do không được chuẩn hóa |
| Route template | `/orders/{id}` | `/orders/8e53b...` chứa ID thật |
| Status code/family | `200`, `404`, `5xx` | Body message làm nhãn |
| Outcome | `SUCCESS`, `CLIENT_ERROR`, `SERVER_ERROR` | Exception message hoặc request ID |
| Server endpoint/group | Nhóm route hữu hạn | URL đầy đủ có query string |
| Request ID | **Không dùng làm tag metrics** | Mỗi request ID là một label value |

Trong Spring Boot/Micrometer, một HTTP server observation thường có thể dùng thông tin **route đã được framework nhận diện**, chứ không nhất thiết raw request URI. Tên/key của thuộc tính, cách xử lý route không match và ngoại lệ tùy phiên bản: phải **xem meter thật** từ `/actuator/metrics`. Nếu bạn tự instrument HTTP request, đừng làm mất quy tắc route-template của framework.

Ví dụ:

~~~text
Hai request thực:
GET /orders/111
GET /orders/222

Một route template:
/orders/{id}
~~~

Hai request tăng giá trị của cùng một nhóm metric, thay vì tạo hai series theo mã đơn.

### Một cảnh báo về 404 và fallback

Không phải mọi URL đều match controller. Khi đó instrumentation có thể dùng giá trị chung như `UNKNOWN` hoặc một nhóm không xác định, tùy phiên bản. Không sửa thành raw URL của request bị 404 để “đầy đủ hơn”: bot hoặc scanner có thể gửi vô số path khác nhau, làm cardinality tăng đột biến.

Để điều tra URL cụ thể gây 404, dùng access log có kiểm soát hoặc truy dấu; log phải áp dụng chính sách bảo mật và lọc dữ liệu nhạy cảm.

## 5. Tag theo dữ liệu nghiệp vụ: nhóm kết quả, không phải ID bản ghi

Ứng dụng Spring Modulith thường có các sự kiện như `OrderPlaced`, `PaymentAuthorized` hoặc `InventoryReservationFailed`. Những event này chứa nhiều trường nghiệp vụ; không phải trường nào cũng là nhãn metric tốt.

| Trường nghiệp vụ | Mục đích | Cách đo nên cân nhắc |
| --- | --- | --- |
| `order.type` | Phân nhóm đơn thường/gấp | Enum hữu hạn: `normal`, `express` |
| `order.channel` | Theo dõi kênh phát sinh | `web`, `mobile`, `partner` |
| `payment.method` | Tỷ trọng phương thức thanh toán | Nhóm nhỏ `card`, `transfer`, `wallet` |
| `result` | Tỷ lệ thành công/thất bại | Chuẩn hóa theo nhóm `success`, `business_rejected`, `technical_failure` |
| `order.amount` | Phân bố giá trị giao dịch | Dùng DistributionSummary hoặc nhóm khoảng giá trị hữu hạn khi cần |
| `order.id` | Tra đơn hàng cụ thể | Không dùng làm metric tag; dùng log/trace/dữ liệu nghiệp vụ |
| `customer.id` | Tra khách hoặc liên kết nghiệp vụ | Không dùng làm metric tag |
| `sku` | Tra sản phẩm | Thường rất nhiều giá trị; chỉ dùng nhóm sản phẩm hữu hạn nếu phù hợp |
| `exception.message` | Phân tích lỗi cụ thể | Không dùng làm metric tag; gắn một `error.category` được kiểm soát |

Đối với một số thuộc tính như `product.category` hoặc mã quốc gia, tập giá trị tuy **hữu hạn về lý thuyết** nhưng vẫn có thể quá lớn hoặc tiếp tục mở rộng. Hãy tính tổng số tổ hợp với các chiều khác trước khi thêm.

### Đừng làm méo dữ liệu chỉ để giảm số tag

Nếu một lỗi đặc biệt có ý nghĩa nghiệp vụ mà nhóm `other` trở nên quá lớn, cần đánh giá lại phân loại nghiệp vụ, tăng mức chi tiết của logs/traces hoặc tạo một metric chuyên biệt. Không nên tạo hàng trăm giá trị `error.message` để “thay thế” việc điều tra log.

## 6. Chọn nơi lưu một thông tin: metric, trace, log hay dữ liệu nghiệp vụ?

Mỗi tín hiệu phù hợp một loại truy vấn:

| Câu hỏi | Nguồn dữ liệu phù hợp | Tại sao |
| --- | --- | --- |
| P95 độ trễ theo module và tenant tier? | Metrics với tags hữu hạn và histogram thích hợp | Truy vấn xu hướng/tổng hợp |
| Một request cụ thể đi qua những module nào? | Distributed trace, spans, trace ID | Phân tích đường đi một lần thực thi |
| Event `E-123` có được xử lý sau commit không? | Publication state, log có correlation ID, dữ liệu nghiệp vụ | Cần trạng thái một event cụ thể |
| Tenant `T-918` bị lỗi nào lúc 10:12? | Logs/traces với phân quyền theo tenant; dữ liệu nghiệp vụ | Cần điều tra chi tiết, không phải metric tổng hợp |
| Đơn nào không giữ được tồn kho? | Dữ liệu trạng thái đơn + sự kiện và logs | Bằng chứng nghiệp vụ |
| Tỷ lệ lỗi của mọi tenant premium tăng từ bao giờ? | Metrics theo `tenant.tier=premium` | Nhóm nhỏ, đủ để cảnh báo |

Micrometer Observation phân biệt **low-cardinality key values** — thường phù hợp cho metric labels — và **high-cardinality key values** — có thể dùng trong tracing khi phù hợp. Phân biệt này không có nghĩa mọi ID đều nên được ghi vào trace. ID khách hàng, tenant và đơn hàng cần xem xét **chính sách riêng tư, lưu giữ, mã hóa, phân quyền, sampling và yêu cầu hợp đồng**.

Đặc biệt, một trace ID dùng để nối spans không phải idempotency key, và tenant ID dùng cho phân quyền không phải metric label bắt buộc.

## 7. Luồng quan sát trong Spring Modulith

Xét modular monolith bán hàng gồm các module `order`, `inventory` và `billing`:

~~~mermaid
flowchart LR
    Client["Client / tenant"] --> HTTP["HTTP GET /orders/{id}"]
    HTTP --> Order["Application module: order"]
    Order --> Inv["API module: inventory"]
    Order --> Event["Publish OrderPlaced"]
    Event --> Billing["Async listener: billing"]
    Order -. "Observation" .-> Meter["Metric: module + tier + outcome"]
    Inv -. "Observation" .-> Meter
    Billing -. "Consumer metrics" .-> Meter
    Order -. "Tracing" .-> Trace["Span + traceId"]
    Billing -. "Nếu có context propagation" .-> Trace
~~~

**Module graph** mô tả các phụ thuộc tĩnh. **Module spans** và metrics mô tả những công việc **thực sự được instrument** lúc chạy. Thông tin tenant tier có thể giúp nhóm hiệu năng theo khách hàng mà không làm nổ số series. Tuy nhiên:

- Module `order`, `inventory` và `billing` thường cùng một ứng dụng Spring Boot, nên không mặc định mỗi module có một `service.name` khác nhau.
- Một HTTP span phản ánh request HTTP; một module span phản ánh đoạn công việc gắn module khi integration hỗ trợ. Các span có thể lồng nhau: **không cộng trực tiếp durations**.
- Event consumer chạy sau commit có thể thất bại dù HTTP trả `201`. Publication counter không tương đương consumer success count.
- Context propagation nối các nhánh telemetry; nó **không** chuyển transaction hoặc bảo đảm exactly-once.

### Mỗi loại metric nên có bộ tag riêng

| Metric logic | Tags hữu ích | Không nên gắn |
| --- | --- | --- |
| HTTP latency | method, route template, status/outcome | Raw URL, request ID, tenant ID tự do |
| Module operation latency | module identifier, operation có giới hạn, tenant tier nếu xác minh được | Order ID, user ID, exception message |
| Event publication count | module, event type, channel đã chuẩn hóa | Event ID, order ID |
| Event consumer attempts | consumer module, event type, success/failure | Trace ID, ID riêng mỗi lần retry |
| Job queue depth | queue/group có số lượng xác định | Task ID sinh theo từng công việc |

Không cần “một bộ tags dùng cho mọi meter”. Mỗi metric cần tags phục vụ **một câu hỏi vận hành cụ thể**.

## 8. Ví dụ Java: gắn tier và kênh nghiệp vụ có giới hạn

Ta có các enum được xác định bởi hệ thống:

~~~java
package com.example.shop.order;

public enum TenantTier {
    STANDARD("standard"),
    PREMIUM("premium"),
    ENTERPRISE("enterprise");

    private final String metricValue;

    TenantTier(String metricValue) {
        this.metricValue = metricValue;
    }

    public String metricValue() {
        return metricValue;
    }
}
~~~

~~~java
package com.example.shop.order;

public enum OrderChannel {
    WEB("web"),
    MOBILE("mobile"),
    PARTNER("partner");

    private final String metricValue;

    OrderChannel(String metricValue) {
        this.metricValue = metricValue;
    }

    public String metricValue() {
        return metricValue;
    }
}
~~~

Sau đó module `order` tạo một observation tại điểm nghiệp vụ cần đo:

~~~java
package com.example.shop.order;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

import java.util.Objects;
import java.util.UUID;

@Service
public class OrderProcessingService {

    private final ObservationRegistry observations;

    public OrderProcessingService(ObservationRegistry observations) {
        this.observations = observations;
    }

    public void process(
            UUID orderId,
            TenantTier trustedTenantTier,
            OrderChannel channel) {

        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(trustedTenantTier, "trustedTenantTier");
        Objects.requireNonNull(channel, "channel");

        Observation.createNotStarted("shop.order.process", observations)
                .lowCardinalityKeyValue("application.module", "order")
                .lowCardinalityKeyValue(
                        "tenant.tier", trustedTenantTier.metricValue())
                .lowCardinalityKeyValue(
                        "order.channel", channel.metricValue())
                .observe(() -> persistOrder(orderId));
    }

    private void persistOrder(UUID orderId) {
        // Thay bằng lưu đơn, transaction và logic nghiệp vụ thực.
    }
}
~~~

**Điểm quan trọng trong đoạn mã:**

1. `trustedTenantTier` phải được tính từ tenant đã xác thực **ở phía server**. Không lấy raw tier do client tự khai báo rồi tin tưởng.
2. `TenantTier` chỉ có ba giá trị; `OrderChannel` cũng chỉ có ba giá trị. Một observation có tối đa **9 tổ hợp** của hai tag này trước các chiều khác.
3. `orderId` dùng trong logic nghiệp vụ nhưng **không đưa vào metric tags**.
4. `application.module=order` là **nhãn do ví dụ tự định nghĩa**. Nếu Spring Modulith hoặc một convention khác đã cung cấp thông tin module tương đương, cần tránh tạo tag trùng ngữ nghĩa hoặc đặt tên thiếu nhất quán.
5. `observe(...)` bao quanh công việc. Timer/span chỉ xuất hiện nếu các observation handlers tương ứng được cấu hình và instrumentation được thực thi.

Một số Spring Modulith integrations đã tạo observation cho tương tác module. **Không bọc trùng mọi phương thức**: hãy xem trace và meter hiện có rồi mới quyết định nơi cần thêm một business observation riêng.

### Nếu muốn đo thất bại?

Đừng gắn exception message nguyên văn. Có thể tạo counter riêng cho các nhóm kết quả có giới hạn, ví dụ `business_rejected`, `technical_failure`, `success`, hoặc sử dụng conventions/handlers đang có. Nếu logic có retry, phân biệt **số lần thử (attempts)** và **số giao dịch duy nhất**, tránh dùng một metric tên chung cho hai ngữ nghĩa.

## 9. Quan sát tenant qua event: chú ý nguồn xác thực

Giả sử module `order` phát `OrderPlaced` và module `billing` xử lý qua listener sau commit:

~~~text
HTTP request của tenant T-123
    ↓ (authentication/authorization)
order: tier=premium
    ↓ publish OrderPlaced
billing: listener chạy trên executor khác
~~~

Với lời gọi HTTP, tier có thể được suy ra từ **principal/token đã xác minh** hoặc từ kho dữ liệu tenant phía server. Nhưng tại listener bất đồng bộ, HTTP request context có thể không còn; **không được giả định thread-local tenant context sẽ tự lan truyền**.

Hướng triển khai an toàn:

- Định nghĩa rõ dữ liệu event nào cần để xử lý nghiệp vụ và ai là nguồn tin cậy của dữ liệu ấy.
- Nếu listener cần tier cho metric, lấy từ metadata event do server kiểm soát hoặc tra lại nguồn dữ liệu tenant được ủy quyền; không dùng chuỗi tenant tự do từ request không xác thực.
- Nếu tier có thể thay đổi theo thời gian, định nghĩa metric phản ánh tier **tại thời điểm publish** hay **tại thời điểm consume**; tránh trộn hai nghĩa.
- Nếu context propagation được bật cho tracing, vẫn phải đánh giá riêng sự lan truyền của **security/tenant context** và giao dịch; tracing context không tự chứng minh quyền truy cập tenant.
- Không ghi tenant ID tùy ý vào tags của listener chỉ để nối event với request gốc. Dùng event ID/correlation ID trong log/trace có kiểm soát và trạng thái publication/nghiệp vụ.

Counter publication của Spring Modulith, nếu được bật, chủ yếu phản ánh **sự kiện được publish**. Counter tự viết cho listener phản ánh **lượt chạy consumer**; retry có thể làm số lượt consumer lớn hơn số publication. Khi customizer thêm tags cho event publication, cũng áp dụng quy tắc low cardinality như với observation nghiệp vụ.

## 10. Giải pháp cho nhu cầu “metric theo từng tenant”

“Muốn xem latency của từng tenant” là một yêu cầu hợp lệ trong nhiều hệ thống SaaS, nhưng cách thực hiện cần phụ thuộc số tenant và mức độ chi tiết:

| Tình huống | Cân nhắc kiến trúc |
| --- | --- |
| 10 tenant cố định, SLA riêng và nhu cầu metric bắt buộc | Có thể chọn per-tenant labels nếu **đã tính số series**, có quy tắc định danh ổn định và quyền truy cập |
| 20.000 tenant và số lượng tiếp tục tăng | Không dùng `tenant.id` như label mặc định trên mọi HTTP/module timer |
| Chỉ cần theo dõi tenant enterprise | Group theo `tenant.tier=enterprise` hoặc allowlist nhỏ, rõ thời gian tồn tại |
| Cần tìm request của một tenant cụ thể | Query logs/traces với tenant correlation và kiểm soát truy cập |
| Cần báo cáo SLA từng tenant ở quy mô lớn | Xem xét hệ thống tổng hợp riêng, phân vùng dữ liệu, quy trình batch hoặc backend chuyên phục vụ truy vấn đa tenant |
| Hệ thống có nghĩa vụ cô lập dữ liệu giữa tenant | Thiết kế RBAC/ABAC, tách namespace hoặc tenancy trong backend, không coi metrics label là security boundary |

Nếu dùng allowlist `tenant.id` cho một vài tenant, **không tự động thêm tenant mới vào allowlist khi thấy trong request**. Hãy đưa tenant ngoài danh sách vào một nhóm `other` có ngữ nghĩa rõ ràng, hoặc gửi dữ liệu chi tiết sang kênh phù hợp. Cần nêu rõ rằng nhóm `other` đã gộp nhiều tenant, **không thể suy ngược kết quả từng tenant** từ metric tổng hợp.

### Đừng làm rò tenant IDs qua dashboard

Ngay cả khi số tenant chưa lớn, tenant identifier trong labels có thể lộ cấu trúc tài khoản, tên tổ chức hoặc hoạt động kinh doanh. Dashboard dùng chung, query API và alert payload đều có thể sao chép nhãn ra nơi khác. Một tag “có cardinality thấp” **không tự động an toàn về quyền riêng tư**.

## 11. Guardrail bằng Micrometer MeterFilter

Một lớp bảo vệ thứ hai là giới hạn số giá trị tag được chấp nhận cho một nhóm meter. Micrometer cung cấp `MeterFilter.maximumAllowableTags(...)` để áp dụng giới hạn:

~~~java
package com.example.shop;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MetricGuardrailConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> limitTenantTierSeries() {
        return registry -> registry.config().meterFilter(
                MeterFilter.maximumAllowableTags(
                        "shop.order.process",
                        "tenant.tier",
                        4,
                        MeterFilter.deny()));
    }
}
~~~

Ý nghĩa: với những meter có tên bắt đầu bằng `shop.order.process`, filter cố hạn chế số **giá trị khác nhau** của tag `tenant.tier` ở mức 4. Trong ví dụ, enum chỉ có ba giá trị, còn một vị trí để phát hiện trường hợp bổ sung ngoài mong đợi.

**Giới hạn của guardrail:**

- `MeterFilter.deny()` có thể khiến meter mới bị **từ chối**, làm mất một phần dữ liệu quan sát. Không nên xem giới hạn này như cách “tự động gộp” những tenant thừa vào `other`.
- Giới hạn cho **một tag** không giới hạn tích số của nhiều tag khác. Nếu `tenant.tier` có 3 giá trị nhưng `order.id` vẫn tăng vô hạn, hệ thống vẫn có thể nổ series.
- Filter cần được đăng ký đủ sớm trước khi meter liên quan được tạo. Cần kiểm tra thứ tự khởi tạo và có test xác nhận trong phiên bản Micrometer/Spring Boot dự án đang dùng.
- Giải pháp chính vẫn là **kiểm soát dữ liệu tại nguồn**, chuẩn hóa tag values và theo dõi tổng số active series.

## 12. Kiểm tra tags và số series bằng Actuator/Prometheus

Trong môi trường phát triển, có thể bật các endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Để `/actuator/prometheus` hoạt động, cần có Prometheus MeterRegistry tương ứng (ví dụ artifact `micrometer-registry-prometheus`) và endpoint được expose. Bảo vệ endpoint quản trị khi triển khai thật; không mở công khai chỉ để debug.

### Bước 1 — Xác nhận meter đã xuất hiện

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/metrics/shop.order.process
~~~

Lệnh thứ ba chỉ có ý nghĩa sau khi ứng dụng đã chạy đoạn `OrderProcessingService.process(...)` và metric handler phù hợp đã được đăng ký. Nếu `404`, có thể meter chưa được tạo, tên khác, handler chưa bật, endpoint không expose hoặc URL sai.

Tra giá trị theo tag, nếu endpoint hỗ trợ định dạng này:

~~~bash
curl -G --data-urlencode "tag=tenant.tier:premium" \
  http://localhost:8080/actuator/metrics/shop.order.process
~~~

Mục tiêu là xác nhận số đo thay đổi cho `premium` sau khi gọi nghiệp vụ có `trustedTenantTier=PREMIUM`. Nếu tên tag trong response khác do version/convention, dùng tên thật đã được ứng dụng ghi nhận.

### Bước 2 — Kiểm tra định dạng Prometheus

~~~bash
curl -i http://localhost:8080/actuator/prometheus
~~~

Prometheus thường scrape (pull) endpoint này theo chu kỳ. Tên timer logic `shop.order.process` có thể được đổi sang các series với suffix như `_seconds_count` và `_seconds_sum`; tên tag có dấu chấm thường được chuyển thành dạng phù hợp chuẩn Prometheus. **Không đoán chính xác tên series** trước khi xem exposition thật.

Giả sử output thực tế có `shop_order_process_seconds_count` và nhãn `tenant_tier`, có thể tra tốc độ xử lý:

~~~promql
sum by (tenant_tier) (
  rate(shop_order_process_seconds_count[5m])
)
~~~

Ví dụ PromQL trên là **minh họa**; metric name và label phải được thay bằng những tên thực tế từ exposition. Muốn tính p95 bằng `histogram_quantile` cần bật histogram buckets tương ứng; timer thông thường chưa chắc cung cấp bucket.

### Bước 3 — Kiểm tra cardinality thực tế

Tạo 100 request với các order IDs khác nhau nhưng chỉ cùng một tier, route và operation. Sau khi các meter được khởi tạo, **số series cho nhóm tag ấy phải ổn định**, trong khi giá trị timer count tăng.

Quan sát ba chiều:

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| Số lượt request tăng | Counter/timer count tăng |
| Thêm order ID mới | Không tạo tag value `order.id` mới, vì không dùng ID trong metric |
| Thêm tenant cùng tier | Không tạo `tenant.id` series mới |
| Thêm tier đã được định nghĩa | Có thể tạo thêm một tổ hợp series hữu hạn |
| Gọi URL khác ID nhưng cùng route template | Vẫn nhóm theo route template |

Backend metrics như Prometheus có công cụ kiểm tra active series và nhãn. Tên query và chức năng xem cardinality tùy backend. Với dữ liệu từ `/actuator/metrics`, có thể dùng `availableTags` để xác nhận các giá trị nhãn đúng và **không chứa ID động**; đừng dùng endpoint Actuator làm công cụ duy nhất đánh giá cardinality ở cả cluster.

## 13. Kiểm thử guardrail và chi phí trước khi triển khai

Một kế hoạch test tốt phải kiểm tra cả **tính đúng đắn của phép đo** lẫn **ngân sách series**:

1. Gửi lặp lại cùng thao tác với 100 order IDs khác nhau.
2. Lấy danh sách meter/tags sau lần đầu và sau lần cuối; số tổ hợp phải không tăng theo order ID.
3. Gửi các giá trị `tenant.tier` hợp lệ; đối chiếu tập label values với enum.
4. Thử dữ liệu tenant chưa hợp lệ qua boundary xác thực; xác nhận request bị từ chối hoặc được chuẩn hóa đúng quy tắc, **không** tạo tag tự do.
5. Kiểm tra HTTP requests có ID khác nhau nhưng cùng route template; metric không nên chia theo path động.
6. Kích hoạt lỗi nghiệp vụ có kiểm soát; giá trị `outcome` vẫn nằm trong tập đã quy định, không chứa exception message.
7. Kiểm tra khi `MeterFilter` chặn meter mới, dashboard không hiện đủ dữ liệu. Đây là tín hiệu cần khắc phục nguồn label, không phải trạng thái bình thường.
8. Nếu có listener bất đồng bộ, kiểm tra consumer lấy tenant tier từ nguồn tin cậy và không phụ thuộc HTTP thread-local context đã mất.

### Theo dõi series count trong registry

Trong test tích hợp đã có `MeterRegistry registry` được inject, có thể kiểm tra các meter thuộc metric family:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;

// registry là MeterRegistry lấy từ Spring test context.
long uniqueOrderMeters = registry.getMeters().stream()
        .map(Meter::getId)
        .filter(id -> id.getName().equals("shop.order.process"))
        .count();

boolean hasUnsafeTag = registry.getMeters().stream()
        .map(Meter::getId)
        .filter(id -> id.getName().equals("shop.order.process"))
        .anyMatch(id -> id.getTag("order.id") != null
                || id.getTag("tenant.id") != null
                || id.getTag("request.id") != null);

System.out.println("Order meter IDs: " + uniqueOrderMeters);
System.out.println("Unsafe ID tag present: " + hasUnsafeTag);
~~~

Đây là đoạn mã **chẩn đoán trong test**, không phải chương trình độc lập. Nó kiểm tra cardinality trong registry của **một application instance**, chưa bao gồm nhãn `instance`, `job` hoặc thông tin được backend thêm. Một test tốt cần chạy các trường hợp có handler metrics thật, vì observation chưa được chuyển thành meter nếu thiếu handler phù hợp.

## 14. Tình huống thực tế: dashboard tăng chi phí sau khi thêm tenant ID

Một nhóm triển khai tính năng “latency theo tenant” bằng cách gắn `tenant.id` vào tất cả HTTP timers. Sau vài tuần, số tenant tăng mạnh. Dù tỷ lệ lỗi không tăng, chi phí và độ trễ query metrics tăng đáng kể.

### Điều tra

1. Xác định metric family có số series tăng cao nhất.
2. Xem tag keys mới trong bản deploy gần đây; tìm `tenant.id` hoặc raw `http.path`.
3. So số giá trị khác nhau của `tenant.id` với số tenant mới tạo.
4. Kiểm tra việc cardinality tăng đã xảy ra **trong MeterRegistry của ứng dụng** hay chỉ ở bước backend thêm nhãn.
5. Đánh giá dashboard có thực sự cần phân biệt mọi tenant không, hay chỉ cần theo `tenant.tier` và nhóm nghiệp vụ.

### Khắc phục

- Thay nhãn ID động bằng `tenant.tier` hoặc tập nhỏ nhóm SLA đã được kiểm soát.
- Nếu hợp đồng bắt buộc xem per-tenant SLA, cân nhắc pipeline báo cáo riêng hoặc metric hữu hạn cho những tenant có chính sách rõ ràng.
- Cập nhật dashboard/alert theo tên tag mới, kiểm tra cả giai đoạn dữ liệu mang nhãn cũ và mới.
- Xác nhận backend không tiếp tục nhận series mới theo tenant ID. **Dữ liệu lịch sử không tự biến mất ngay** sau khi thay code.
- Bổ sung kiểm thử để tránh tag ID quay lại trong lần refactor sau.

Điểm đáng nhớ: không nên giới hạn cardinality bằng cách “chỉ đổi tên metric”. Nếu mỗi tên metric có tenant ID, bạn vẫn tạo nhiều series, chỉ chuyển nguyên nhân từ **tag values** sang **meter names**.

## 15. Phân biệt thiếu metric với lỗi nghiệp vụ

Trong một hệ thống quan sát mô-đun, metric không xuất hiện hoặc bị thiếu dữ liệu có thể do:

| Dấu hiệu | Khả năng |
| --- | --- |
| Bean nghiệp vụ chạy nhưng không có meter | Chưa instrument, Observation handler không đăng ký hoặc logic chưa đi qua điểm đo |
| Có meter trong ứng dụng nhưng Prometheus không thấy | Endpoint chưa expose, registry thiếu, scrape target lỗi hoặc query sai tên |
| Có timer nhưng thiếu series cho tenant tier mới | Giá trị chưa từng xuất hiện, bị filter từ chối, hoặc đã được chuẩn hóa sang nhóm khác |
| Có HTTP span nhưng không thấy module span | Spring Modulith Insight chưa instrument điểm gọi, module discovery sai hoặc sampling/export |
| Event publication metric tăng nhưng consumer thất bại | Publication và consumption là hai giai đoạn khác nhau; cần metric/log/trạng thái consumer |
| Log listener không có tenant context | Async executor không truyền security/business context hoặc event thiếu metadata cần thiết |
| Tracing backend trống nhưng metrics vẫn tăng | Thiếu tracing bridge/exporter, sampler loại trace hoặc backend/Collector lỗi |

Khi điều tra, hãy đi theo chuỗi **source → instrumentation → MeterRegistry → endpoint/exporter → collector/backend → dashboard**. Việc `MeterFilter` từ chối series để bảo vệ hệ thống có thể khiến dashboard trông “tốt hơn” thực tế; cần kiểm tra thông tin bị mất trước khi kết luận hệ thống ổn định.

## 16. Bài thực hành: thiết kế tags cho hệ thống 1.000 tenant

Giả sử ứng dụng Spring Boot/Modulith có 1.000 tenant, 4 application modules, 10 routes, 3 tenant tiers, 3 outcomes và 5 application instances. Một nhóm muốn thêm tag `tenant.id` vào timer ở mọi route.

**Yêu cầu thực hành:**

1. Tính số tổ hợp series tối đa nếu dùng `tenant.id` cùng route, module, outcome, instance. So với phương án dùng `tenant.tier` thay thế.
2. Chọn một bộ tags cho HTTP latency, một bộ tags cho module operation latency và một bộ tags cho event consumer attempts.
3. Giải thích vì sao `request.id`, `order.id` và `tenant.id` không phù hợp làm labels đại trà.
4. Dùng mã `OrderProcessingService` ở phần 8 để tạo 100 yêu cầu có order IDs khác nhau và xác minh số meter không tăng theo ID.
5. Tạo một event được xử lý bất đồng bộ, kiểm tra tier tại consumer và đề xuất cách xác thực nguồn dữ liệu.
6. Viết một PromQL query cho tỷ lệ xử lý theo `tenant.tier` bằng tên series thật đã export.
7. Đề xuất cơ chế điều tra cho một tenant cụ thể mà không phải tạo metric cho mọi tenant.
8. Ghi ngân sách series, số active series quan sát và chính sách phát hiện tag mới.

### Gợi ý tính toán

Nếu **mọi tổ hợp đều xuất hiện**, và giả sử chỉ xét một tên metric:

\[
\begin{aligned}
N_{\text{tenant-id}} &\leq 1000 \times 4 \times 10 \times 3 \times 5
= 600{,}000,\\
N_{\text{tenant-tier}} &\leq 3 \times 4 \times 10 \times 3 \times 5
= 1{,}800.
\end{aligned}
\]

Đây là **trần giả định**, chưa tính histogram bucket hoặc nhãn được backend thêm. Không phải mọi route đều được mọi module phục vụ, nên số active series thực có thể thấp hơn. Tuy nhiên, chênh lệch trần cho thấy tại sao việc chọn tag cần được thiết kế từ đầu.

### Mẫu bảng quyết định

| Metric | Tag key | Số giá trị dự kiến | Mục đích | Quyết định |
| --- | --- | ---: | --- | --- |
| HTTP latency | `http.route` | 10 | Xác định endpoint chậm | Giữ route template |
| Module latency | `application.module` | 4 | So độ trễ giữa các module | Giữ |
| Module latency | `tenant.tier` | 3 | Phát hiện nhóm SLA chịu ảnh hưởng | Giữ sau khi xác minh nguồn tier |
| Module latency | `tenant.id` | 1.000+ | Truy chi tiết theo khách | Không gắn đại trà |
| Event attempts | `outcome` | 3 | Tỷ lệ retry/lỗi | Giữ nhóm kết quả có giới hạn |
| Event attempts | `event.id` | Theo số event | Điều tra một sự kiện | Chuyển sang log/trace/publication state |

### Câu hỏi tự kiểm tra

1. Vì sao `tenant.id` có thể được dùng trong một hệ thống 10 tenant cố định, nhưng không nên là default label trong SaaS hàng chục nghìn tenant?
2. Hai URL `/orders/1` và `/orders/2` nên được nhóm dưới nhãn route nào?
3. Nếu thêm tag `tenant.tier` có ba giá trị vào metric vốn có 40 tổ hợp, số tổ hợp lý thuyết có thể thành bao nhiêu?
4. Gắn `request.id` vào counter có giúp đếm request chính xác hơn không? Vì sao?
5. Tại sao `exception.message` và raw SKU cũng có rủi ro cardinality cao?
6. Một listener xử lý `OrderPlaced` chạy trên thread khác nên lấy tenant tier từ đâu để gắn nhãn đúng và an toàn?
7. `MeterFilter.maximumAllowableTags` có tự động gộp những giá trị bị chặn vào `other` không?
8. Metric có tag `tenant.tier=premium` chứng minh điều gì? Nó không cho biết chi tiết nào về một tenant cụ thể?
9. Vì sao nhãn module giúp kiểm chứng tương tác trong Spring Modulith nhưng không biến mỗi module thành một microservice?
10. Một request tạo đơn trả `201` nhưng listener thất bại sau commit. Cần kết hợp những tín hiệu nào thay vì chỉ xem HTTP timer?

## 17. Tổng kết

Khi đo một ứng dụng Spring Modulith có nhiều tenant, **tag phải mô tả các nhóm giá trị hữu hạn, ổn định và có ích cho việc tổng hợp**. Đối với tenant, nên ưu tiên tier/segment; đối với request, ưu tiên method, route template và status/outcome; đối với dữ liệu nghiệp vụ, ưu tiên loại event, channel và nhóm kết quả. Tenant ID, request ID, order ID, email hoặc exception message không phù hợp làm metric labels đại trà.

Micrometer Observation, Actuator và Prometheus giúp xác minh metric thật sự thay đổi theo thao tác, còn **traces, logs, publication state và dữ liệu nghiệp vụ** cung cấp sự chi tiết khi cần điều tra một request hoặc event. Bằng cách tính ngân sách series, chuẩn hóa tags từ dữ liệu đã xác thực và kiểm tra context propagation ở listener bất đồng bộ, ta giữ được tính quan sát của kiến trúc mô-đun mà không đánh đổi độ ổn định vận hành.

## Tài liệu tham khảo

- [Micrometer — Concepts: Meters and naming](https://docs.micrometer.io/micrometer/reference/concepts.html).
- [Micrometer — Observation: Low and high cardinality](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Spring Modulith — Production-ready Features and Observability](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Prometheus — Data model and labels](https://prometheus.io/docs/concepts/data_model/).
