# Lấy mẫu truy vết, giới hạn số lượng nhãn và chi phí lưu trữ

## 1. Quan sát được hệ thống không có nghĩa phải lưu mọi thứ

Một REST API có 300 request/giây, trung bình mỗi request tạo 12 span. Nếu thu toàn bộ trace trong một ngày, hệ thống tạo ra:

\[
300\ \text{request/s}\times12\ \text{span/request}\times86\,400\ \text{s/day}
=311\,040\,000\ \text{span/day}.
\]

Con số này chưa bao gồm log, metric, kích thước span attributes, network transmission, index, replication hay retention. Cùng lúc, nếu metric `http.server.requests` gắn nhãn `userId` cho 100.000 người dùng, số time series có thể tăng hàng trăm nghìn đến hàng triệu dù chỉ có vài route. Telemetry “chi tiết hơn” có thể làm **hệ quan sát quá tải và tốn tiền**, thậm chí khiến ứng dụng chậm theo.

Bài thuộc chương **Quan sát hệ thống** của module **INTEGRATION_API_REST**: thiết kế REST theo resource, URI, HTTP methods/status, hợp đồng dữ liệu, phân trang, cache, idempotency, OpenAPI, xác thực/phân quyền, lỗi và kiểm thử với Java/Spring hoặc công nghệ tương đương. Trọng tâm không phải cách mở dashboard mà là **cân bằng khả năng chẩn đoán, độ chính xác, bảo mật và chi phí telemetry**.

Sau bài học, bạn sẽ có thể:

1. Phân biệt **trace sampling**, **metric label cardinality** và **log retention**.
2. Chọn **head/parent-based/tail sampling** theo loại lỗi và cấu trúc request phân tán.
3. Dùng **HTTP route template** thay cho raw URI, đặt ngân sách nhãn và chống rò PII.
4. Cấu hình **Spring Boot/Micrometer/OpenTelemetry/Collector** ở mức minh họa, kiểm thử quyết định sampling và số series.
5. Ước lượng chi phí, phát hiện telemetry mất cân bằng và vận hành chính sách khi sự cố xảy ra.

**Nguyên tắc nền:** quan sát hệ thống là một sản phẩm có **SLO, chính sách dữ liệu, chi phí và failure mode**. Không được để collector/backend hỏng khiến mọi request API production thất bại; cũng không nên giảm sampling đến mức mất hết bằng chứng của sự cố quan trọng.

## 2. Metrics, traces và logs có những giới hạn khác nhau

| Tín hiệu | Đơn vị phổ biến | Giá trị đối với REST API | Điều thường gây tăng chi phí |
|---|---|---|---|
| **Metrics** | Time series theo metric name + bộ label | Request rate, error rate, latency histogram, saturation, SLO | **Nhãn nhiều giá trị**, histogram buckets, nhiều instance/region |
| **Traces** | Trace gồm nhiều spans có quan hệ cha–con | Tìm chặng chậm/error xuyên gateway → API → DB → downstream | Số request được ghi, spans/trace, attributes, retention/search indexing |
| **Logs** | Event có message/fields/timestamp | Thông tin domain, audit đã kiểm soát, lỗi có ngữ cảnh | Volume, body/stack trace dài, indexing mọi field, retention |

**Một trace ID có thể xuất hiện trong log** để giúp đối chiếu, nhưng trace ID đó **không chứng minh backend đang lưu trace**: head sampling có thể đã loại trace, exporter có thể lỗi hoặc retention đã hết. Metric lấy từ **request được quan sát thực** thường phải đếm **tất cả request phù hợp**; nếu đếm trên tập sampled spans mà không hiệu chỉnh, request rate/error rate sẽ bị sai và mất đỉnh tải.

Các thuộc tính cũng khác nhau:

- **Metric label/tag** tạo series khác nhau khi giá trị thay đổi. `route="/v1/orders/{id}"` có ít giá trị; `orderId="o-123"` có thể có hàng triệu.
- **Span attribute** thường không tạo *time series Prometheus* trực tiếp, nhưng vẫn làm tăng dung lượng trace, index và rủi ro PII; không vì vậy mà cho phép gắn raw token.
- **Log field** có thể bị indexing/cấp quyền riêng; log theo `requestId` hỗ trợ điều tra nhưng raw request body/JWT là rò dữ liệu.
- **Exemplar** có thể liên kết một sample metric với trace ID được giữ lại; exemplar cũng phải theo chính sách cardinality, retention và quyền truy cập, không dùng làm kho toàn bộ request IDs.

### 2.1. Dùng tín hiệu đúng câu hỏi

Ví dụ sau deploy, p99 latency của `GET /v1/orders/{id}` tăng:

1. **Metric** phát hiện latency/error tăng và phân loại theo route/method/status class, region.
2. **Trace** của một số request chậm cho thấy 80% thời gian nằm ở truy vấn DB hoặc gọi đối tác.
3. **Log** của request/operation được điều tra bổ sung mã lỗi nghiệp vụ hoặc quyết định fallback mà không lộ payload nhạy cảm.

Nếu log toàn bộ body mọi request chỉ để tính p95 latency, đó là chọn sai tín hiệu. Nếu chỉ có trace sampled 1% để đếm số request mỗi phút, kết quả cũng sai. **SLO metrics và trace sampling phải độc lập về định nghĩa**, dù cùng dùng một hệ instrumentation.

### 2.2. Ngân sách observability là một yêu cầu phi chức năng

Một policy vận hành nên ghi rõ: số active series tối đa, trace spans/s và bytes/s, log bytes/s, tỷ lệ sampled traces, retention nóng/lạnh, ngân sách indexing và mức mất dữ liệu có thể chấp nhận khi exporter/collector hỏng. **Đưa ngân sách vào kiểm thử và alert** thay vì chỉ xem hóa đơn cuối tháng.

Không có tỷ lệ sampling “chuẩn cho mọi hệ thống”. REST API 20 RPS có thể giữ 100% traces với chi phí thấp; dịch vụ 50.000 RPS cần chiến lược khác, đặc biệt khi mỗi request gọi nhiều downstream.

## 3. Lấy mẫu trace: xác suất, quyết định cha và thông tin sau khi kết thúc

Một trace phân tán có thể gồm `gateway` → `orders-api` → `inventory-api` → `database`. Nếu các service quyết định hoàn toàn độc lập, backend có thể nhận **trace thiếu parent hoặc thiếu một nhánh**. Sampling cần được thiết kế cùng **context propagation**.

### 3.1. Head sampling

**Head sampling** quyết định rất sớm khi bắt đầu trace/span, trước khi biết latency hoặc HTTP status cuối:

~~~text
Request đến API
     |
     +-- chọn trace ID và sampling decision (ví dụ 10%)
     |         |
     |         +-- sampled: record/export spans
     |         +-- not sampled: vẫn có thể propagate trace context
     |
     +-- xử lý request → response
~~~

Ưu điểm: ít memory, hạn chế CPU/network ngay tại SDK và quy mô dễ dự đoán khi traffic đều. Nhược điểm: **một trace lỗi hoặc latency rất cao có thể bị loại** trước khi biết nó có vấn đề. `traceIdRatioBased(0.10)` là **xác suất 10%**, không có nghĩa chính xác cứ 10 requests thì giữ 1; quan sát ngắn có sai số thống kê, và lưu lượng các nhóm traffic có thể không đồng nhất.

**Không dùng một mẫu sampled traces để suy trực tiếp số lượng HTTP 500.** Nếu 1% trace được giữ, 0 lỗi trong mẫu nhỏ không chứng minh hệ thống không có lỗi. Metrics không sampling mới là nguồn tin cậy cho số lượng/SLO.

### 3.2. Parent-based sampling và traceparent

Trong W3C Trace Context, `traceparent` mang trace ID, parent ID và trace flags. Bit sampled (low-order bit) thể hiện ý định sampling được truyền cho downstream.

~~~http
GET /v1/orders/o-42 HTTP/1.1
Host: api.example.com
Authorization: Bearer <redacted>
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Ví dụ `01` có sampled bit bật. **Bit này là tín hiệu trong trace context, không phải chứng thực identity, không phải bảo đảm backend đã lưu span.** Caller bên ngoài có thể tự gửi traceparent; API **không được** dùng trace ID/sampled flag để cấp quyền hoặc bật debug ghi body/secret. Đặt giới hạn kích thước/độ tin cậy context ở ingress; tại trust boundary có thể quyết định sampling policy mới để tránh client tự ép giữ tất cả traces.

**Parent-based sampler** thường tuân theo quyết định sampling của parent đã được nhận, kết hợp chính sách cho root traces. Ví dụ root chọn 10%, downstream kế thừa sampled decision để có trace thống nhất hơn. Trong thực tế cần cấu hình cho remote/local parent, W3C propagation, gateway và background worker đúng; **nếu parent không được thu, một service vẫn có thể lưu span riêng theo policy khác**, gây trace không đầy đủ.

### 3.3. Tail sampling

**Tail sampling** giữ quyết định đến khi collector đã nhận đủ (hoặc phần lớn) spans của trace trong một khoảng chờ, rồi mới xét:

- status/error của span;
- tổng thời gian/latency threshold;
- service/route/operation hoặc thuộc tính được phép;
- một tỷ lệ probabilistic cho traffic bình thường.

~~~mermaid
flowchart LR
    A["SDK ghi spans đủ để gửi"] --> B["Collector gom theo trace ID"]
    B --> C{"Trace lỗi/chậm/critical?"}
    C -->|Có| D["Giữ trace theo policy"]
    C -->|Không| E{"Random normal sampling?"}
    E -->|Chọn| D
    E -->|Không| F["Drop trước backend lưu trữ"]
~~~

Ưu điểm: giữ được nhiều dấu vết lỗi/chậm hơn head sampling thuần. Nhược điểm: **đã tốn chi phí tạo, truyền, buffer spans trước khi quyết định**; phải cấp RAM, `decision_wait`, trace budget và xử lý trace đến muộn. Trace kéo dài hàng phút hoặc các nhánh đến từ nhiều collectors có thể bị quyết định khi **chưa đủ dữ liệu**; tail sampling không bảo đảm mọi trace lỗi đều được giữ.

Nếu tất cả spans của một trace không cùng đến một collector hoặc một nhóm có phối hợp, tail sampler có thể **không thấy toàn bộ trace**. Hệ collector nhiều replica thường cần **trace-ID-aware load balancing/routing**; round robin ngẫu nhiên trên mỗi span là phản mẫu. Giới hạn **num_traces/memory** và theo dõi spans/traces dropped, late spans, OOM, decision latency.

### 3.4. Adaptive/policy-based và vấn đề thiên lệch

Có thể tăng sampling lúc error rate tăng, ưu tiên payment/checkout hoặc giảm sampling của health check. Nhưng **thiên lệch mẫu** khiến backend có tỷ lệ error traces cao hơn thực tế nếu cố ý giữ mọi lỗi và chỉ 1% successes. Hãy gắn metadata về policy/probability và **không dùng tỷ lệ “lỗi trong traces đã thu” làm error rate thực**.

Nếu cần suy ra số lượng từ mẫu xác suất, phải hiểu phương pháp điều chỉnh thống kê và điều kiện lấy mẫu; với tail policy phụ thuộc outcome, một hệ số nhân đơn giản `1/p` thường không đúng. Metrics toàn bộ request vẫn là chuẩn cho vận hành/SLO.

## 4. Số lượng nhãn: một dimension nhỏ có thể nhân toàn bộ series

Trong hệ time-series như Prometheus, một **series** là một metric name kết hợp **một tập giá trị label cụ thể**. Số series tiềm năng tăng theo tích số giá trị của các dimension có thể kết hợp.

Ví dụ metric request rate có 12 route templates, 5 status classes, 4 HTTP methods, 3 regions, 2 outcomes:

\[
N_{\text{series}}\leq 12\times5\times4\times3\times2=1\,440.
\]

Đây là **upper bound khi tất cả tổ hợp xuất hiện**, không phải số series chắc chắn đã tạo. Nếu thêm `tenantId` có 4.000 giá trị và mỗi tenant sinh đủ mọi tổ hợp, số tiềm năng thành **5.760.000 series**. Với nhiều metric khác, instance/pod labels, histogram buckets và time-series churn, chi phí còn lớn hơn.

### 4.1. Route template, không phải path/raw query

| Nhãn | Ví dụ | Đánh giá |
|---|---|---|
| `http.route` | `/v1/orders/{id}` | Tốt: giá trị hữu hạn và phản ánh operation |
| `http.request.method` | `GET`, `POST` | Tốt: tập nhỏ, xác nhận method chuẩn |
| `http.response.status_code` | `200`, `404`, `500` | Thường hữu hạn; có thể dùng `status_class` để giảm cardinality |
| `deployment.environment` | `production`/`staging` | Tốt nếu allowlist |
| `region` | `ap-southeast-1` | Tốt nếu số region hữu hạn |
| `tenant.id` | `t-8831` | Không nên là metric label rộng rãi |
| `user.id`/`order.id` | ID duy nhất theo user/order | **Rất cao**, có nguy cơ PII và cardinality explosion |
| `url.full` / `http.target` | `/v1/orders/o-42?email=...` | **Rủi ro**: nhiều giá trị, chứa token/PII trong query |
| `error.message`/`exception.stacktrace` | Text biến động từng lỗi | Không dùng làm label; dùng error code đã chuẩn hóa |
| `trace_id` / `request_id` | 128-bit/UUID gần duy nhất | Không dùng làm metric label; dành cho trace/log correlation |

Một `GET /v1/orders/o-42` và `GET /v1/orders/o-43` phải có chung `http.route="/v1/orders/{id}"` trong metric request theo route. Không tự thay chuỗi bằng regex yếu như “mọi số là `{id}`”: URL có slug, UUID, encoded slash hoặc route chưa match; dùng **handler mapping/route template được framework xác định** và fallback `UNKNOWN` cho URI không match.

**Lưu ý security:** route template do server cấu hình ít rủi ro hơn URI người gọi gửi, nhưng tên route/operation nội bộ cũng có thể cần ẩn; cân nhắc mục tiêu dashboard và quyền xem telemetry. Không dùng raw query params, bearer, cookie, customer email hay order ID làm metric labels.

### 4.2. Histogram tạo nhiều series hơn counter đơn

Một latency histogram cổ điển kiểu Prometheus với `B` **finite bucket boundaries** thường tạo `B+3` time series cho mỗi tổ hợp labels (thêm bucket `+Inf`, `_sum` và `_count`). Với 10 finite bucket boundaries, 1.440 tổ hợp có thể tạo khoảng **18.720 series**, chưa kể instance/job labels. Cách native histogram và backend khác có encoding riêng; không lấy công thức classical histogram làm định luật chung.

Không xóa hết bucket để “giảm giá”: latency SLO cần phân phối, p95/p99 từ histogram có sai số phụ thuộc bucket. Chọn bucket boundaries quanh SLO quan trọng, cân đối độ phân giải, số series và lưu lượng; dùng recording rules/aggregation để dashboard truy vấn hiệu quả hơn.

### 4.3. Active cardinality và churn là hai rủi ro khác nhau

- **Active series:** số bộ nhãn đang có data trong cửa sổ hiện tại, ảnh hưởng RAM/index/ingestion.
- **Series churn:** số bộ nhãn mới sinh theo thời gian, ví dụ gắn `request_id` khiến mỗi request tạo series mới; dù từng series tồn tại ngắn, index và metadata vẫn tăng nhanh.
- **Histograms + exemplars:** histogram labels phải bounded; exemplar có trace linkage nhưng không nên lạm dụng hay giữ vô hạn.

**Cardinality budget nên áp theo metric/dimension, không chỉ tổng hệ thống:** ví dụ `http.route` tối đa 200 giá trị đã duyệt, `error_code` tối đa 80 mã ổn định. Nếu `route=UNKNOWN` xuất hiện tăng, đó có thể là endpoint chưa instrument đúng hoặc traffic tấn công, không nên tự mở label theo URI thô để “xem cho rõ”.

### 4.4. “Top N tenant” có thể cần thiết nhưng không được mở nhãn tùy ý

Đội sản phẩm có thể muốn xem tenant nào gây tải. Không nên đưa toàn bộ tenant ID vào mọi metric request. Thay vào đó:

1. Aggregate theo **gói dịch vụ/tenant tier** có giá trị hữu hạn để đo fairness.
2. Dùng **billing/usage events** hoặc bảng thống kê có phân quyền riêng khi cần số request theo tenant.
3. Với điều tra ngắn hạn, query logs/traces đã được cấp quyền theo tenant ID và retention kiểm soát.
4. Nếu dùng exemplar/top-K hoặc một metric tenant riêng, áp allowlist, giới hạn N, TTL và tính riêng ngân sách/cardinality.

Việc **hash tenant ID rồi đưa vào label** chỉ che chuỗi gốc, **không giảm cardinality**: 100.000 hash khác nhau vẫn tạo tới 100.000 nhãn.

## 5. Chiến lược sampling theo ưu tiên chẩn đoán

Sampling rate là biến điều chỉnh **khối lượng traces**, không phải giải pháp duy nhất. Một chính sách cân bằng cho REST API có thể:

| Lớp traffic | Mục tiêu | Policy ví dụ (minh họa) |
|---|---|---|
| GET catalog bình thường | Quan sát latency phân tán | Head 5–10% |
| POST checkout/payment | Dễ điều tra side effect | Head cao hơn hoặc tail ưu tiên lỗi/chậm |
| HTTP 5xx, timeout downstream | Debug incident | Tail policy giữ error traces khi ngân sách cho phép |
| Request chậm trên SLO | Tìm bottleneck | Tail giữ traces vượt threshold |
| Health/readiness | Tránh noise | Tỷ lệ thấp hoặc không export trace, vẫn giữ health metrics |
| Background job/webhook | Quan sát async chain | Propagate/link context và sampling theo operation |

Các tỷ lệ trên **không phải khuyến nghị mặc định**. Cần đo RPS, spans/request, tail latency, chi phí ingest, tỷ lệ error và nhu cầu phân tích. Nếu lỗi rất hiếm nhưng cực quan trọng, head 1% có thể bỏ sót đúng trace lỗi; nếu error storm tạo hàng triệu 5xx, tail “giữ 100% lỗi” lại có thể làm backend sụp. Cần **budget cap/adaptive shedding**, ưu tiên theo severity và giữ metrics/logs tối thiểu.

### 5.1. Tránh “kết hợp head 1% rồi tail giữ mọi lỗi” một cách hiểu sai

Nếu SDK **head drop 99%** trước khi gửi spans, tail sampler trong collector **không thể cứu 99% traces đã bị drop**. Muốn tail quyết định dựa trên lỗi, upstream phải gửi đủ spans/metadata cần thiết tới tail sampler; có thể dùng head sampled cao cho một số tuyến quan trọng, hoặc kiến trúc instrumentation phù hợp. Nhớ rằng tăng ingest vào collector vẫn tốn network/CPU dù backend chỉ lưu 5%.

**Không dùng trace flags từ client như cơ chế nâng mức debug:** attacker có thể đặt sampled bit = 1 rồi ép tốn tài nguyên nếu edge luôn tin. Tại ingress cần policy quota/trust boundary; giữ tiếp parent sampled khi là traffic nội bộ tin cậy, áp sampling policy cho untrusted external roots theo thiết kế.

### 5.2. Sampling decision qua service và worker

~~~text
Gateway (root) ----> Orders API ----> Inventory API
        \                  |
         \                 +----> DB span
          \
           ----> Queue producer ----> Consumer (xử lý bất đồng bộ)
~~~

Trong HTTP, instrumenter thường inject/extract W3C `traceparent` và `tracestate`. Với message broker, propagate context trong message headers khi hỗ trợ, hoặc tạo span links giữa producer/consumer theo semantics của hệ queue. **Retry, batch và async delivery** có thể không có một cây parent–child đơn giản; span links giúp giữ quan hệ mà không tạo parent sai.

Không nhét bearer token, customer data hay raw message body vào `baggage` để “truyền context”; baggage có thể được gửi tới downstream ngoài trust boundary, không thay quyền truy cập. Khi dùng span links, vẫn phải kiểm trace-ID routing ở collector để tail sampler thấy các nhánh cần quyết định.

### 5.3. Nên tách “sampled traces” và “error diagnostics”

Khi trace của một 500 bị drop, response vẫn có HTTP 500; metric error counter/histogram và một **error code đã chuẩn hóa** trong log an toàn có thể tồn tại độc lập. Thiết kế chiến lược observability gồm:

- Metrics từ mọi request qua middleware, không dựa vào số sampled traces.
- Logs có correlation ID, mã lỗi, route template, nhưng không raw token/body.
- Trace samples giúp xem dependency path chi tiết khi mẫu được giữ.
- Trong incident, cơ chế **tăng sampling tạm thời** có owner, TTL, giới hạn bytes/s và rollback.

Đây là lý do phải định nghĩa **độ bao phủ (coverage)** và **mức tin cậy** của từng tín hiệu, không xây báo cáo “tỷ lệ lỗi = số trace lỗi / tổng trace” khi sampling phụ thuộc outcome.

## 6. Spring Boot/Java: cấu hình trace và metric nhãn an toàn

Ví dụ dùng **Java 17+, Spring Boot 3.x, Micrometer Observation/Tracing và OpenTelemetry**. Version cụ thể và cơ chế xuất telemetry phải được xác nhận với BOM của Spring Boot đang dùng; một ứng dụng không nên tự khởi tạo thêm tracer provider khi Boot đã auto-configure một provider khác, vì dễ tạo **hai pipeline hoặc context không liên thông**.

### 6.1. Dependencies và cấu hình head sampling

Với Maven có Spring Boot BOM/parent tương thích:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
  </dependency>
  <dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
  </dependency>
  <dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
  </dependency>
  <dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
  </dependency>
</dependencies>
~~~

~~~yaml
# application.yml — ví dụ Spring Boot 3.x
spring:
  application:
    name: orders-api
management:
  tracing:
    sampling:
      probability: 0.10  # head sampling 10% cho root theo cấu hình Boot
  otlp:
    tracing:
      endpoint: http://otel-collector.internal:4318/v1/traces
  endpoints:
    web:
      exposure:
        include: health,prometheus
~~~

Đây là **cấu hình minh họa cho môi trường mạng nội bộ có kiểm soát**. Production phải bảo vệ kết nối exporter (TLS/mTLS theo topology), xác thực collector và giới hạn ai được truy cập Actuator/`/actuator/prometheus`; không phơi metric có thông tin nhạy cảm lên Internet. Tracing sampling probability và các thuộc tính/exporter có thể thay đổi theo phiên bản/bridge; **kiểm dependency tree và integration test kết quả export**, không chỉ tin YAML có hiệu lực.

Một yêu cầu GET có thể tạo HTTP server observation, span DB và downstream client spans khi các thư viện đã được instrument. Không cần tự tạo span cho mọi method getter nhỏ; **đặt custom span ở chặng nghiệp vụ có giá trị**, tránh nhân số span một cách vô ích.

### 6.2. Custom Observation không đưa ID nhạy cảm vào metric tags

~~~java
@Service
class OrderService {
    private final ObservationRegistry observations;
    private final OrderRepository repository;

    OrderService(ObservationRegistry observations,
                 OrderRepository repository) {
        this.observations = observations;
        this.repository = repository;
    }

    OrderView create(Actor actor, CreateOrderCommand cmd) {
        return Observation.createNotStarted("orders.create", observations)
            .lowCardinalityKeyValue("operation", "orders.create")
            .lowCardinalityKeyValue("outcome_group", "write")
            .observe(() -> {
                OrderEntity saved = repository.insertScoped(actor, cmd);
                return OrderView.from(saved);
            });
    }
}
~~~

`Actor`, `OrderRepository`, `OrderEntity`, `CreateOrderCommand`, `OrderView` là kiểu ví dụ của ứng dụng. **Low-cardinality key-values** có thể được dùng làm nhãn metric; vì thế `operation`/`outcome_group` phải là giá trị bounded. Không gắn `orderId`, `userId`, email, bearer token hay request body bằng `lowCardinalityKeyValue`.

**High-cardinality key-values** của Micrometer được định hướng cho trace thay vì metric; nhưng vẫn phải được phép theo chính sách dữ liệu, giới hạn kích thước/retention và khả năng truy cập backend. Đừng biến lời nhắc “high cardinality không thành metric label” thành giấy phép gửi PII vào trace. Nếu cần liên kết order để điều tra, có thể dùng **correlation ID không chứa secret** và tra cứu audit/business DB với quyền riêng thay vì index order ID trên mọi span.

Việc tạo observation trực tiếp chỉ hoạt động đúng khi registry có observation handlers/tracing integration phù hợp. Code mẫu không tự cấu hình transaction, authorization, retry hoặc exporter; có thể tách observation bao quanh service use case nhưng không ghi full entity vào attribute.

### 6.3. Nếu tự dùng OpenTelemetry SDK, chọn sampler có kế thừa

Trong ứng dụng Java không để Boot quản lý tracer provider, API SDK có thể cấu hình:

~~~java
Sampler sampler = Sampler.parentBased(
    Sampler.traceIdRatioBased(0.10));

SdkTracerProvider provider = SdkTracerProvider.builder()
    .setSampler(sampler)
    // Production: cấu hình span processors/exporters đúng vòng đời.
    .build();
~~~

Đây là **minh họa cấu hình sampler**, không tự gửi traces vì chưa thêm exporter/span processor. Đừng dùng đoạn này để tạo thêm provider thứ hai trong Spring Boot đã có autoconfiguration. Parent-based + root probability giúp quyết định sampling xuyên service nhất quán hơn, nhưng **external traceparent không đáng tin tuyệt đối**. Nếu ingress reset policy, phải kiểm chứng bằng test distributed trace qua gateway/worker.

### 6.4. Metric custom có allowlist nhãn

Ứng dụng thường đã có `http.server.requests` qua framework instrumentation; **đừng tạo thêm timer custom giống hệt** chỉ để đo cùng request, vì dễ đếm trùng và tốn storage. Nếu có một metric **chuyên dụng cho tác vụ xuất báo cáo**, có thể đóng bộ labels:

~~~java
@Component
class ExportMetrics {
    private static final Set<String> OPERATIONS =
        Set.of("reports.create", "reports.download", "reports.cancel");
    private final MeterRegistry meters;

    ExportMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    void record(String operation, String outcome, Duration duration) {
        String safeOperation = OPERATIONS.contains(operation)
            ? operation : "UNKNOWN";
        String safeOutcome = switch (outcome) {
            case "success", "failure", "cancelled" -> outcome;
            default -> "other";
        };

        Timer.builder("api.report.operation.duration")
            .description("Thời gian xử lý operation nhóm báo cáo")
            .tag("operation", safeOperation)
            .tag("outcome", safeOutcome)
            .register(meters)
            .record(duration);
    }
}
~~~

Ở đây số tổ hợp `operation×outcome` có **upper bound 3×3 + UNKNOWN/other fallback** (chính xác tối đa 4×4 = 16 theo implementation), không phụ thuộc số `reportId` hoặc `tenantId`. Đoạn code ghi Duration theo Micrometer Timer; metric này đo **operation được instrument cụ thể**, không phải thay thế latency HTTP từ tất cả requests.

**Với HTTP server metrics**, dùng route template do Spring MVC `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` hoặc convention mặc định của framework, **không gắn `request.getRequestURI()` hay `request.getQueryString()` vào metric tag**. Nếu hệ instrumentation đã chuẩn hóa route, đừng viết wrapper làm phá normalization.

### 6.5. Log correlation mà không “chứa cả request”

~~~text
INFO operation=orders.create http.route=/v1/orders
     http.method=POST http.status=201 duration_ms=42
     trace_id=<opaque-trace-id> request_id=<opaque-request-id>

KHÔNG GHI:
  Authorization / Cookie / Set-Cookie / Idempotency-Key
  raw URL có access_token query / JSON body có PII
  SQL bind values, customer email, private JWT claims
~~~

Sử dụng SLF4J/MDC với đúng scope thread trong Spring MVC, và trace context/Reactor Context cho WebFlux; **không copy MDC tùy tiện qua async threads** vì có thể ghép nhầm user hoặc request. Trace ID và request ID là **correlation data**, không xác thực người gọi và không tự cho phép truy vấn dữ liệu nhạy cảm.

## 7. OpenTelemetry Collector: tail sampling có ngân sách và topology

Collector có thể nhận OTLP từ API và lưu trữ vào tracing backend. Khi dùng **tail sampling**, nên đặt ở một pipeline trace riêng và để **các spans cùng trace ID đến cùng điểm quyết định**. Một ví dụ cấu hình cho **OpenTelemetry Collector Contrib**:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 2048
    spike_limit_mib: 512
  tail_sampling:
    decision_wait: 15s
    num_traces: 50000
    expected_new_traces_per_sec: 3000
    policies:
      - name: error-spans
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: slow-traces
        type: latency
        latency:
          threshold_ms: 2000
      - name: normal-traffic
        type: probabilistic
        probabilistic:
          sampling_percentage: 10
  batch:
    timeout: 5s
    send_batch_size: 8192

exporters:
  otlp:
    endpoint: tracing-backend.internal:4317
    tls:
      insecure: false

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [otlp]
~~~

**Cảnh báo triển khai:** cấu hình trên là **minh họa cấu trúc**, không phải manifest cắm vào production nguyên xi. Phải cấp network policy, mTLS/CA và authentication khi cần, kiểm khả năng hỗ trợ processor trong bản Collector Contrib tương ứng, kiểm thông số/tài nguyên thực tế và tránh bind receiver công khai tới Internet. `0.0.0.0` chỉ nên nằm trong vùng mạng được bảo vệ. Backend TLS `insecure:false` phải có chứng chỉ/CA hợp lệ; một số topology cần thêm auth.

Các policy trong ví dụ chọn trace khi có span status `ERROR`, latency vượt 2 giây hoặc được chọn ngẫu nhiên 10%; **latency/error policy phụ thuộc dữ liệu span SDK thật sự emit**. Nếu server trả `500` mà instrumentation không đặt span status ERROR, chính sách `status_code` có thể không giữ trace đó. Khi cần phân loại theo HTTP status, phải xác minh semantic attributes và chính sách điều kiện phù hợp bản Collector.

### 7.1. Một collector không đủ nếu spans bị chia ngẫu nhiên

~~~text
                    [OTLP agents / gateways]
                              |
                Load balancer theo TRACE ID
                   /                   \
         Tail sampler A             Tail sampler B
         (trace IDs nhóm A)         (trace IDs nhóm B)
                   \                   /
                      Tracing backend
~~~

Nếu load balancer dùng **round robin theo span**, trace nhiều services có thể đến hai sampler, mỗi nơi chỉ thấy một phần và quyết định khác nhau. Dùng routing theo trace ID hoặc lớp phân vùng phù hợp; khi scale out/rebalance, đánh giá trace đang in-flight và late spans. **Sticky routing không tự tạo khả năng vô hạn:** một sampler vẫn có memory/buffer giới hạn, có thể drop trace dưới tải cao.

### 7.2. Đo overhead của tail sampling trước khi bật rộng

Trong chế độ tail, **SDK upstream cần gửi đủ spans để xét policy**, ví dụ root sampler giữ nhiều/100% trước collector; nếu vẫn head sample 10% như Mục 6 thì tail sampler không nhìn thấy 90% traces đã loại. Nhưng gửi nhiều hơn tạo **ingress/network/collector CPU/RAM** dù chỉ export số ít về backend. Phải đo:

- traces/spans nhận, giữ, loại và drop do memory/backpressure;
- thời gian chờ quyết định; trace đến muộn và trace thiếu spans;
- kích thước buffer, RSS/heap và queue/export retry;
- chi phí egress tới collector, backend ingest và retention.

Lựa chọn **head sampling ở SDK** hợp lý nếu mục tiêu chính là giảm overhead end-to-end. **Tail sampling** hợp lý khi ưu tiên giữ trace lỗi/chậm và chấp nhận ingest/buffer nhiều hơn. Một hệ lớn có thể **phân lớp**: endpoints critical đi pipeline tail với quota riêng; traffic bình thường head-sampled từ nguồn. Cần bảo đảm link giữa các trace khi chúng đi các pipeline khác nhau.

### 7.3. Collector không thay thế bộ đếm request đầy đủ

Đừng tạo SLO dashboard chỉ từ spanmetrics chạy **sau tail sampling** rồi coi đó là tất cả requests: trace đã bị drop trước processor sẽ không đóng góp vào count. Hãy thu server-side HTTP metrics độc lập hoặc cấu hình processor trước sampling với semantics và tài nguyên được kiểm chứng; tránh **đếm hai lần** do pipeline fan-out/duplicated instrumentation.

## 8. Mô hình chi phí: từ RPS đến bytes/ngày và retention

Với `R` request/giây, `S` spans/request, `p` xác suất giữ trace và `B` bytes trung bình mỗi span được lưu, một ước lượng ban đầu:

\[
\operatorname{spans/day}=R\times S\times p\times86\,400
\]

\[
\operatorname{raw\ bytes/day}\approx
R\times S\times p\times86\,400\times B.
\]

Ví dụ `R=300`, `S=12`, `p=0,10` và `B=700` bytes/span:

| Chỉ số ước lượng | Kết quả |
|---|---:|
| Tổng spans trước sampling | 311.040.000 spans/ngày |
| Spans được giữ ở mức 10% | 31.104.000 spans/ngày |
| Payload thô được giữ | ~21,8 GB/ngày (decimal GB) |
| Giữ 7 ngày | ~152,4 GB payload thô |
| Nếu giữ 100% | ~217,7 GB payload thô/ngày |

**Đây không phải hóa đơn storage thực.** Backend còn có compression, index, replicas, WAL, metadata, trace search, object-store overhead, các bản sao/truy vấn/tier lưu trữ; có hệ nén rất tốt, có hệ tốn index nhiều. Với **tail sampling**, dù lưu ~21,8 GB/ngày trong ví dụ, có thể vẫn phải **nhận ~217,7 GB/ngày qua collector** nếu upstream gửi 100% spans trước quyết định.

### 8.1. Retention phải được chọn theo trường hợp sử dụng

| Loại dữ liệu | Retention ví dụ | Mục tiêu |
|---|---|---|
| Trace chi tiết của request thông thường | 3–7 ngày | Debug nhanh sự cố gần đây |
| Trace lỗi/checkout quan trọng | Có thể lâu hơn với ngân sách riêng | Phân tích incident, đối soát kỹ thuật |
| Aggregate metrics/recording rules | 30–90 ngày hoặc theo SLO | So sánh xu hướng/seasonality |
| Logs vận hành | Theo incident/SRE policy | Debug với access control |
| Security/audit logs | Theo chính sách an ninh/pháp lý riêng | Điều tra tuân thủ, không dựa vào trace sampling |

Các khoảng này **chỉ minh họa**, không phải chính sách phù hợp mọi doanh nghiệp. Audit yêu cầu tính đầy đủ và chống sửa đổi có thể không dùng cùng pipeline lấy mẫu với traces; dữ liệu thanh toán/PII phải theo retention, residency và quyền truy cập được phê duyệt.

### 8.2. Chi phí metrics: series, samples và truy vấn

Nếu có 200.000 active series và thu **một sample mỗi 15 giây**, sẽ có gần:

\[
200\,000\times(86\,400/15)=1\,152\,000\,000\ \text{samples/day}.
\]

Không thể chuyển thẳng số samples thành GB bằng một kích thước cố định: TSDB có nén, chunks, WAL, index, native/classic histograms và billing khác nhau. **Theo dõi active series, series created/churn, samples ingested, query latency, retention và storage bytes**. Nếu một label mới nhân số series gấp 100, giảm sampling traces **không làm giảm** cardinality metric đó.

### 8.3. Bài toán log “mỗi request một dòng”

Nếu 5.000 requests/s và mỗi request tạo trung bình 1 KB log, volume thô khoảng **432 GB/ngày** trước nén/index. Cắt stack trace và body logging tự do, dùng log levels, sampling có chính sách cho **log thông thường**, nhưng giữ **security audit** theo yêu cầu không mất sự kiện. Với request có `Authorization`/PII, quan trọng hơn cả giảm volume là **không thu dữ liệu không nên lưu ngay từ đầu**.

### 8.4. Dự toán ngân sách theo ba tầng

~~~text
Tại SDK:
  spans/request x RPS x head sampling x span attributes bytes
         |
         v
Collector:
  ingestion throughput + tail buffering/CPU/memory + export retry
         |
         v
Backend:
  stored spans/samples/logs x retention x replication/index/query
~~~

Giảm backend retention không giảm chi phí CPU tại SDK. Giảm head sampling giảm network/collector nhưng mất trace lỗi có thể cần. Giảm cardinality label giảm metric series/index nhưng không làm traces ít hơn. **Xác định đúng tầng sinh chi phí trước khi tối ưu**; dùng dashboards theo ba tầng thay vì chỉ nhìn tổng storage.

## 9. Bảo mật observability: sampling không được dùng để che rò dữ liệu

Trace được giữ 1% vẫn có thể chứa mật khẩu hoặc bearer token của **một người thật**. Sampling không thay masking, access control và data minimization. Một số vị trí dễ vô tình lộ dữ liệu trong REST API:

| Nguồn dữ liệu | Lỗi instrumentation | Biện pháp |
|---|---|---|
| `Authorization`/`Cookie`/API key headers | Tự động capture tất cả request headers | **Deny by default**, allowlist an toàn, test export thực |
| URL với query `token=...` hoặc email | Span `url.full`/`http.target` chứa raw URI | Dùng route template; sanitize/redact query ở mọi pipeline |
| JSON request/response | Debug/body logging hoặc đặt body làm span event | Không thu body thông thường; nếu thật cần, có phê duyệt/policy |
| User/tenant/order ID | Dùng làm metric label hoặc searchable trace attributes không kiểm soát | Pseudonymization/ACL/limited use; không tạo label nhiều giá trị |
| SQL query | Capture bind parameters chứa PII | Query shape đã chuẩn hóa, không ghi values |
| `error.message` | Chứa rejected input, host nội bộ, stack trace có secret | Stable error codes; tách audit/stack an toàn |
| `baggage`/tracestate | Propagate metadata nhạy cảm sang đối tác | Filter theo trust boundary, không chứa credentials |
| Exemplar trace link | Lộ trace của tenant khác qua dashboard | RBAC ở tracing backend và multi-tenant query isolation |

**Đừng cho client lựa chọn telemetry policy có quyền cao:** query `?debug=true` hoặc header `X-Debug-Trace: all` không được tự bật full payload logging. Nếu có cơ chế debug tạm thời, phải có **xác thực quản trị**, allowlist service/operation, TTL, budget, audit và quy trình tắt; không cho người dùng thường yêu cầu collector giữ 100% traces.

### 9.1. Redact ở đâu?

- **Instrumenter/SDK:** tốt nhất là **không tạo** attribute nhạy cảm ngay từ đầu.
- **Collector:** lớp phòng thủ thứ hai để filter/hash/drop fields trước backend; có thể bỏ sót exporter bypass hoặc logs không qua collector.
- **Backend/UI:** RBAC, tenancy, query scopes, retention, audit exports; **không** xem UI masking là đủ khi dữ liệu gốc đã được index.

Nếu Collector dùng attribute transform/filter, cần kiểm thứ tự processor trước exporter và không biến hash có thể đảo/đoán thành “ẩn danh hóa”. **Hashing ID không làm giảm số giá trị distinct** và với dữ liệu ít entropy vẫn có thể bị dò. Một raw trace link có thể đưa người không có quyền đến trace chứa dữ liệu tenant khác nếu backend không kiểm access.

### 9.2. Sampling và bảo mật có thể mâu thuẫn trong incident

Khi sự cố 5xx tăng, tail policy giữ nhiều lỗi hơn đúng lúc error messages có thể chứa input nhạy cảm nhất. Trước khi tăng sampling, kiểm **redaction coverage, backend RBAC, retention và transfer region**. Không dùng trace samples thay thế **audit đầy đủ** nếu compliance yêu cầu lưu mọi quyết định bảo mật; audit là luồng riêng có integrity/retention phù hợp.

## 10. Kiểm thử sampling và giới hạn series bằng Java/Spring

### 10.1. Ma trận kiểm thử nên có

| Ca | Dữ liệu/điều kiện | Assertion |
|---|---|---|
| O01 | GET `/v1/orders/o-1` và `/v1/orders/o-999` | Cùng metric label `http.route=/v1/orders/{id}` |
| O02 | 10.000 IDs khác nhau đưa vào custom operation metric | Số series bounded, không tăng tuyến tính |
| O03 | URI query có token/email | Không có query/token trong metric label, trace attribute, log |
| O04 | User A và B khác tenant | Không tạo nhãn `tenantId` raw, trace/search có quyền tương ứng |
| O05 | Head sampling 10% trên 10.000 root traces | Tỷ lệ gần 10% trong biên thống kê, **không assert đúng 1.000** |
| O06 | Parent sampled và downstream được instrument | Trace context propagated, spans ghép đúng trace khi policy yêu cầu |
| O07 | Parent không sampled | Không ép downstream emit mọi span nếu không có policy riêng |
| O08 | Tail nhận trace có span `ERROR` | Giữ trace khi policy lỗi match và còn capacity |
| O09 | Tail nhận trace chậm hơn threshold | Giữ trace khi policy latency match và đủ spans đến trong cửa sổ |
| O10 | Spans cùng trace đến hai collectors do round robin | Test phát hiện trace thiếu spans; cần trace-ID routing |
| O11 | Collector memory/external backend outage | API vẫn chạy; telemetry drop/retry theo ngân sách, có metric cảnh báo |
| O12 | Metric traffic 429/5xx nhưng trace sampling thấp | HTTP count/SLO metric vẫn đúng vì không tính từ sampled trace |
| O13 | Thêm tag mới là raw `requestId` | CI/cardinality guard từ chối |
| O14 | Tăng sampling tạm thời khi incident | Có giới hạn RPS/bytes, TTL và tự trở về policy bình thường |

### 10.2. Unit test bắt metric high cardinality trước khi merge

Với `ExportMetrics` ở Mục 6 và Micrometer `SimpleMeterRegistry`:

~~~java
@Test
void customMetricsUseOnlyAllowedDimensions() {
    try (var registry = new SimpleMeterRegistry()) {
        var metrics = new ExportMetrics(registry);

        for (int i = 0; i < 10_000; i++) {
            // Dữ liệu ngoài allowlist phải về một bucket UNKNOWN.
            metrics.record("report-id-" + i,
                "some-client-value-" + i, Duration.ofMillis(8));
        }

        metrics.record(
            "reports.create", "success", Duration.ofMillis(30));
        metrics.record(
            "reports.download", "failure", Duration.ofMillis(40));

        var timers = registry.find("api.report.operation.duration")
            .timers();
        assertEquals(3, timers.size()); // UNKNOWN+other và 2 mẫu hợp lệ
        assertTrue(timers.stream().noneMatch(t ->
            t.getId().getTags().stream().anyMatch(tag ->
                tag.getValue().startsWith("report-id-")
                    || tag.getValue().startsWith("some-client-value-"))));
    }
}
~~~

Code minh họa dùng JUnit 5, `io.micrometer.core.instrument.simple.SimpleMeterRegistry`, `java.time.Duration` và assertions. **Đừng chỉ test số series sau 10 request**: các ID động thực thường xuất hiện ở traffic lớn. Đối với middleware HTTP, thêm integration test Spring Boot với nhiều path IDs và inspect metric export `http.server.requests`, bảo đảm route được normalize. Nếu route chưa match và framework ghi `UNKNOWN`, đó là chấp nhận được nếu có metric đếm unknown/404 riêng mà không sinh series theo raw URI.

### 10.3. Integration test trace sampling là test xác suất và propagation

Head sampling `p=0,10` không thể được kiểm bằng assert “request thứ 10 phải có trace”; decision dựa trên trace ID và sampler. Cách thử:

1. Tạo nhiều **root traces độc lập** có trace IDs được tạo theo cơ chế SDK; ghi nhận quyết định lấy mẫu.
2. Kiểm tỷ lệ nằm trong **khoảng sai số thống kê** với N đủ lớn, hoặc dùng sampler deterministic/known IDs khi test API sampler.
3. Tạo request có incoming `traceparent` sampled/unsampled và downstream được instrument; xác nhận **trace ID và parent span IDs** phù hợp, không nhầm caller header là authentication.
4. Ở môi trường tích hợp Collector, dùng backend nhận traces giả lập và assert đủ spans theo flow; không test bằng `MockMvc` đơn thuần rồi cho là đã kiểm propagation qua mạng.

Khi kiểm tail sampler, **không dùng head sampler 10% upstream** mà kỳ vọng Collector giữ mọi lỗi. Phải gửi đủ traces theo thiết kế, đánh dấu span status hoặc HTTP attribute đúng, chờ hết `decision_wait` có deadline và xác minh trace thực được export. Test riêng **late spans, collector restart, memory pressure và nhiều replicas**.

### 10.4. Kiểm trực tiếp trên HTTP và log

~~~http
GET /v1/orders/o-42?debug=false HTTP/1.1
Host: api.example.com
Authorization: Bearer <redacted>
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{"id":"o-42","status":"CREATED"}
~~~

Test bằng một **sentinel giả lập** trong query/header, không dùng credential thật. Sau request, tìm sentinel trong **telemetry đã export** (backend test, không chỉ log của controller); assert nó không xuất hiện ở metric label, trace attribute, log hoặc body lỗi. Quyền đọc trace backend phải được test bằng hai tenant/principals; thành công HTTP `200` không chứng minh telemetry an toàn.

## 11. Giám sát chính hệ quan sát và runbook khi vượt ngân sách

### 11.1. Dashboard tối thiểu

| Nhóm | Metric/tín hiệu nên theo dõi | Hành động khi bất thường |
|---|---|---|
| **Tracing SDK** | Spans created/sampled/exported, exporter failures, queue depth | Kiểm sampler, exporter deadline và instrumenter |
| **Collector** | Receivers accepted/refused, dropped spans, memory limiter, pipeline latency | Kiểm RAM, backpressure, trace-ID routing, tail buffer |
| **Backend** | Ingest bytes/s, stored spans, search/query latency, retention, cost | Giảm indexing/retention hoặc điều chỉnh policy có trách nhiệm |
| **Metrics TSDB** | Active series, new series/churn, samples/s, write failures, query memory | Truy metric/label mới gây bùng nổ, chặn allowlist |
| **Logs** | Bytes/s, indexed fields, exporter errors, PII sentinel scan | Tắt raw body logging, giảm verbosity có policy |
| **SLO nguồn** | API request rate, 5xx/429, latency, checkout success | Đảm bảo tín hiệu chính không lệch theo sampling |

Không chỉ alert trên `trace_export_success=0` ở một pod nếu vẫn có collectors khác; liên hệ **coverage toàn service** và SLO của công cụ observability. Ngược lại, việc dashboards có dữ liệu không chứng minh mọi dịch vụ được instrument hoặc không mất trace critical.

### 11.2. Quy trình khi một label làm nổ series

Giả sử deploy phiên bản mới và số active series tăng 50 lần vì `http.target` chứa order ID:

1. **Phát hiện:** đối chiếu series/churn với deploy change, metric name, label cardinality; không query và xuất toàn bộ raw labels có PII ra kênh chung.
2. **Khoanh vùng:** rollback instrumentation, tắt metric/attribute sai qua feature flag hoặc `MeterFilter` có policy; không xóa/disable toàn bộ metrics HTTP quan trọng nếu còn phương án chọn lọc.
3. **Bảo vệ backend:** áp per-tenant/service ingest quota/cardinality guard và điều chỉnh scrape/drop rule theo khả năng; thận trọng vì drop không đúng có thể làm SLO dashboard mất dữ liệu.
4. **Sửa gốc:** dùng route template/allowlist, thêm unit test 10.000 IDs, đảm bảo unknown route gộp đúng, kiểm downstream recording rule và trace span metrics.
5. **Phục hồi:** quan sát active/churn giảm sau khi series cũ hết retention/staleness; kiểm request-rate/latency dashboards vẫn đúng và hóa đơn ingestion trở về ngưỡng.

**Không chỉ tăng giới hạn Prometheus/backend** để “hết lỗi”: nguồn label cardinality không bounded sẽ tiếp tục nhân chi phí. Cũng không khắc phục metric explosion bằng cách giảm trace sampling vì hai pipeline khác nhau.

### 11.3. Khi Collector lỗi, API không được chết theo

Traces/logs thường là **best effort với giới hạn tài nguyên**: bounded batch queue, export timeout, retry có giới hạn, circuit breaker hoặc drop telemetry theo policy khi collector/backend không phản hồi. Đừng cấu hình synchronous export blocking trên request path gây thêm hàng giây latency hoặc chặn thread pool.

Nếu bắt buộc **security audit event** phải bền vững trước khi thực hiện một lệnh nhạy cảm, hãy thiết kế kênh audit/outbox chuyên biệt có transaction/reliability semantics rõ; **không trộn audit bắt buộc vào một trace sampler có thể drop**. Metric request/error vẫn nên được thu ở middleware không lệ thuộc vào backend trace.

### 11.4. Thay đổi sampling có kiểm soát

~~~text
Trước thay đổi:
  Đo RPS, spans/request, trace ingest, error coverage,
  active metric series, collector RAM và tracing spend.

Rollout:
  Canary trên service/operation đã duyệt, TTL policy,
  budget bytes/s & num_traces, đặc biệt tail sampler.

Xác minh:
  HTTP/SLO metrics không đổi bất thường, traces sampled
  có parent/spans đủ, no-PII, backend không quá tải.

Rollback:
  Tự trả về sampling thường sau incident,
  giữ dấu vết cấu hình/version và chi phí phát sinh.
~~~

**Telemetry có thể là đường tấn công DoS:** attacker gửi rất nhiều request, tạo hàng nghìn distinct paths hoặc 5xx để buộc tail sampler “giữ mọi lỗi”. Giới hạn RPS ở edge, route labels theo template, cap sampling budgets và tuyệt đối không dùng request headers chưa xác thực để tăng quyền instrument.

## 12. Bài tập thiết kế và checklist

### 12.1. Bài tập: tối ưu telemetry cho Orders API

Một REST API có lưu lượng trung bình **1.500 RPS**, mỗi request tạo **8 spans**, kích thước lưu thô **600 bytes/span**. Hiện team muốn giữ **5% trace bằng head sampling** trong 14 ngày. Metric latency có 20 route templates, 5 status classes, 4 HTTP methods, 3 regions và 8 finite histogram boundaries. Một đề xuất thêm `tenantId` vào tất cả metric labels, hiện có 3.000 tenants.

**Yêu cầu:**

1. Tính spans/ngày và raw trace storage/ngày với head sampling 5%, và 14 ngày (bỏ qua compression/index/replication).
2. Tính số series tối đa khi dùng classic histogram, trước và sau khi thêm 3.000 tenant labels.
3. Nếu muốn **tail giữ các traces lỗi** thay vì head 5%, chi phí nào có thể tăng **trước bước quyết định**?
4. Thiết kế chính sách để bảo vệ checkout errors, vẫn giữ SLO metrics chính xác, không lộ token/tenant PII.

### 12.2. Lời giải tham khảo

\[
1\,500\times8\times86\,400\times0{,}05
=51\,840\,000\ \text{spans/day}.
\]

Ở 600 bytes/span, payload thô khoảng **31,1 GB/ngày**, tương đương **435,5 GB trong 14 ngày** trước mọi overhead. Với 20×5×4×3 = **1.200 tổ hợp labels**, classic histogram 8 finite boundaries cần `8+3=11` series mỗi tổ hợp, tức **13.200 series** nếu tất cả tổ hợp xuất hiện. Thêm 3.000 tenant labels và tất cả kết hợp có thể thành **39.600.000 series** (3.000×13.200); con số thực phụ thuộc những tổ hợp thật sự có traffic.

Khi chuyển sang tail sampling có upstream gửi 100% spans, collector có thể phải nhận:

\[
1\,500\times8\times86\,400\times600
\approx622{,}1\ \text{GB raw/day}
\]

trước bước drop/giữ trace, dù backend cuối cùng lưu ít hơn nhiều. Chọn **head sampling cho traffic bình thường**, ưu tiên phân tích checkout/error với pipeline/budget riêng nếu cần, bounded tail sampling, metrics request/error toàn bộ không sampled, label theo route template, không thêm tenant ID vào mọi metric. Dùng audit/query với RBAC nếu cần phân tích theo tenant, thay vì tăng series toàn hệ.

### 12.3. Checklist review trước production

- [ ] Phân biệt **metric**, **trace**, **log** và đảm bảo HTTP error/latency SLO không được suy từ sampled traces.
- [ ] Đã nêu mục tiêu và budget sampling: head %, tail policy, trace coverage, error/slow paths, retained bytes/s.
- [ ] Có propagation W3C `traceparent`/context qua HTTP và async; ingress không tin sampled bit từ client để cấp quyền/debug.
- [ ] Tail sampling chỉ nhận spans cần thiết, có trace-ID routing, bounded buffer, decision wait và dropped-span metrics.
- [ ] Metric label là **route template, method/status class và dimension hữu hạn**; không có raw URL, user/tenant/order ID, token hoặc request ID.
- [ ] Đã kiểm upper bound **series × histogram buckets × regions/instances** và churn, có guard trong CI/canary.
- [ ] Không gửi secret/PII trong trace attributes, baggage, log body, query string; test sentinel ở backend đã export.
- [ ] Prometheus/Actuator, collector và tracing backend được bảo vệ bằng network/TLS/RBAC/retention đúng môi trường.
- [ ] Biết chi phí **SDK, collector, backend storage/index/query**; áp retention khác nhau theo loại telemetry và audit.
- [ ] Có dashboard cho accepted/dropped telemetry, memory pressure, active series/churn, trace coverage, cost và SLO nguồn.
- [ ] Collector/backend lỗi không chặn API; audit bắt buộc được xử lý bằng kênh độ tin cậy thích hợp.
- [ ] Có runbook tăng/giảm sampling an toàn với owner, TTL, cap và rollback.

**Tài liệu tham khảo chính:** [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/), [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/), [OpenTelemetry Collector Contrib — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor), [OpenTelemetry Semantic Conventions for HTTP](https://opentelemetry.io/docs/specs/semconv/http/), [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html), [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html), [Prometheus — Metric and Label Naming](https://prometheus.io/docs/practices/naming/), [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/), [W3C Trace Context](https://www.w3.org/TR/trace-context/).

**Kết luận:** quan sát REST API tốt không phải thu **100% traces và mọi ID thành metric label**. Hãy đo SLO bằng metrics đúng phạm vi, lấy mẫu traces có chiến lược để chẩn đoán, kiểm soát cardinality từ instrumenter, giữ log/trace an toàn và tính chi phí xuyên **SDK → Collector → backend**. Sampling, retention, label budgets và khả năng phục hồi của telemetry đều cần được thiết kế, đo và kiểm thử như những phần của hợp đồng vận hành API.
