# Cardinality tăng đột biến

## 1. Bối cảnh: hệ thống vẫn chạy nhưng observability quá tải

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, các application module có thể giao tiếp qua lời gọi đồng bộ hoặc domain event. Nhóm phát triển dùng module graph, Actuator, event metrics, tracing và context propagation để xem ranh giới kiến trúc có đúng như thiết kế, đồng thời quan sát lỗi khi hệ thống vận hành.

Một sự cố thường gặp là số lượng **time series** trong hệ thống metrics tăng đột ngột sau một lần triển khai, mặc dù lượng truy cập chỉ tăng nhẹ. Prometheus bắt đầu dùng nhiều RAM, truy vấn dashboard chậm, remote-write tồn đọng và chi phí lưu trữ tăng. Ở ứng dụng Java, số lượng meter động cũng có thể làm `MeterRegistry` lớn dần, tăng áp lực bộ nhớ.

Nguyên nhân có thể là một instrumentation mới gắn `orderId`, `eventId`, `traceId`, email hoặc URL đầy đủ làm **metric tag**. Mỗi giá trị khác nhau tạo ra một tổ hợp nhãn mới, khiến hệ thống không còn chỉ theo dõi “số lần xử lý sự kiện”, mà vô tình tạo một chuỗi metrics riêng cho từng đơn hàng hoặc từng sự kiện.

Chủ đề **“Cardinality tăng đột biến”** thuộc chương **Chẩn đoán lỗi** tập trung vào cách phân biệt cardinality cao với lượng event lớn, khoanh vùng nguyên nhân ở Spring Modulith/Micrometer/Actuator và xử lý sao cho giữ được thông tin vận hành cần thiết.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích cardinality theo định nghĩa tập nhãn của metric, phân biệt active series và series churn.
2. Tìm nhãn hoặc metric gây tăng số chuỗi, từ dấu hiệu Prometheus đến instrumentation trong ứng dụng.
3. Thiết kế nhãn an toàn cho module, operation, event type, outcome và đường HTTP đã chuẩn hóa.
4. Áp dụng cách khắc phục trong Micrometer, kiểm soát độ nhạy của dữ liệu và đánh giá ảnh hưởng tới tracing.
5. Xác nhận sau sửa rằng thời gian xử lý, event publication, module graph và các cảnh báo vận hành vẫn có ý nghĩa.

## 2. Cardinality là gì?

Một chuỗi metric được định danh bởi **tên metric + toàn bộ tổ hợp giá trị label/tag**. Ví dụ:

~~~text
shop_module_event_processed_total{
  module="notification",
  event_type="OrderPlaced",
  outcome="success"
} 5480

shop_module_event_processed_total{
  module="notification",
  event_type="OrderPlaced",
  outcome="failure"
} 17
~~~

Đây là **metric và tên label minh họa do ứng dụng tự định nghĩa**, không phải lời khẳng định Spring Modulith luôn tự sinh metric này.

Hai dòng trên là hai time series khác nhau vì giá trị `outcome` khác nhau. Với một metric có các tập giá trị độc lập, số tổ hợp tiềm năng xấp xỉ:

\[
N_{\text{series}} \approx |L_1| \times |L_2| \times \cdots \times |L_n|
\]

Đây là **ước lượng cận trên theo tích Descartes** khi mọi tổ hợp có thể xuất hiện, không phải quy tắc bảo đảm hệ thống thực sự sinh đủ các tổ hợp. Số series còn chịu ảnh hưởng bởi tên metric, histogram, instance/pod, nhãn từ hệ thu thập và thời điểm ghi nhận.

Ví dụ trong cùng một ứng dụng:

| Nhãn | Số giá trị khác nhau |
| --- | ---: |
| `module` | 8 |
| `event_type` | 12 |
| `outcome` | 3 |
| `instance` | 6 |
| Tổng tổ hợp có thể | 8 × 12 × 3 × 6 = **1.728** |

Nếu thêm `order_id` có **50.000 giá trị**, số tổ hợp về lý thuyết có thể tăng lên đến **86.400.000**. Trong thực tế không phải mọi đơn hàng đều đi qua mọi module, event và instance, nhưng chỉ cần một phần nhỏ cũng đủ gây ra hàng trăm nghìn hoặc hàng triệu series.

### High cardinality khác với số lượng event lớn

- **Traffic lớn:** một counter `event_type="OrderPlaced"` được tăng một triệu lần, nhưng vẫn là một series cho cùng tổ hợp nhãn.
- **Cardinality lớn:** một triệu event tạo một triệu giá trị `event_id` khác nhau, có thể sinh một triệu series dù mỗi series chỉ tăng một lần.
- **Series churn lớn:** có nhiều series mới được tạo và biến mất liên tục, ví dụ dùng UUID làm nhãn. Churn gây áp lực lên bộ nhớ, index, WAL và remote-write kể cả khi số series đang hoạt động tại một thời điểm không quá cao.

Một lần “bùng nổ cardinality” cũng có thể do thêm nhiều buckets histogram/SLO, thêm histogram cho nhiều route hoặc đưa một dimension mới vào một metric đã có nhiều nhãn. Khi bật histogram, một tập nhãn nghiệp vụ có thể tương ứng nhiều chuỗi `_bucket`, `_sum`, `_count`; hệ số nhân phụ thuộc cấu hình bucket và exporter.

## 3. Dấu hiệu và mức độ ảnh hưởng

| Dấu hiệu | Điều có thể suy ra | Điều cần xác minh |
| --- | --- | --- |
| Prometheus `head series` tăng mạnh | Số series lưu tại TSDB tăng | Xảy ra sau deploy nào, target/job nào tăng? |
| Series created tăng nhanh dù QPS ổn định | Nhãn động hoặc target churn | Có thêm tag theo event/request/ID? |
| RAM của Prometheus tăng, query timeout | Index và tập series lớn | Chi phí query, retention, tải thực tế |
| Remote-write queue hoặc bytes tăng | Số mẫu/series gửi ra backend lớn | Metric/nhãn nào chịu trách nhiệm? |
| Ingest quota/billing tăng | Cardinality gây chi phí vận hành | Series từ ứng dụng, exporter hay service khác? |
| Heap hoặc `MeterRegistry` ứng dụng tăng | Meter được đăng ký theo giá trị tag động | Dùng code/instrumentation nào tạo meter mới? |
| Dashboard thiếu số liệu sau khi bật filter | Filter chặn cả dữ liệu cần thiết | Metric nào bị deny, ngưỡng có hợp lý? |
| Trace volume tăng | Có thể do sampling/span count, không nhất thiết do metric cardinality | Trace attributes có bị đưa sang metric labels không? |

Không nên kết luận ngay “do Spring Modulith” chỉ vì sự cố xảy ra sau khi bật hỗ trợ module observability. Các nguồn khác như HTTP server metrics, JVM metrics, Kafka client, database instrumentation, custom metric, OpenTelemetry Collector hoặc service discovery cũng có thể gây tăng chuỗi.

## 4. Tình huống minh họa ở hệ thống nhiều module

Một cửa hàng có bốn module:

~~~text
shop
├── ordering      -> tạo OrderPlaced
├── inventory     -> trừ tồn kho
├── payment       -> thu tiền
└── notification  -> gửi thông báo
~~~

Instrumentation cũ chỉ theo dõi `module`, `event_type` và `outcome`. Một thay đổi mới thêm `event_id`:

~~~java
// Ví dụ sai: mỗi event có một tag duy nhất
Counter.builder("shop.module.event.processed")
    .tag("module", "notification")
    .tag("event.type", "OrderPlaced")
    .tag("event.id", event.id().toString())
    .register(meterRegistry)
    .increment();
~~~

Mỗi giá trị `event.id()` tạo một meter khác nhau. Cứ 100.000 sự kiện mới có thể tạo thêm 100.000 tổ hợp nhãn. Đội vận hành thấy số series tăng theo tốc độ event và nhầm rằng “listener bị chạy lặp vô hạn”. Trong khi đó business event rate vẫn bình thường.

Cách sửa là để metric mô tả nhóm hành vi, còn thông tin theo từng event chỉ được giữ ở những nơi thực sự cần thiết và được bảo vệ:

~~~java
// Ví dụ tốt hơn: tập nhãn nhỏ, ổn định
Counter.builder("shop.module.event.processed")
    .tag("module", "notification")
    .tag("event.type", "OrderPlaced")
    .tag("outcome", "success")
    .register(meterRegistry)
    .increment();
~~~

Nếu cần tra cứu một sự kiện cụ thể, có thể sử dụng log có quyền truy cập phù hợp hoặc truy vấn event publication registry theo nghiệp vụ. Không đưa ID sự kiện vào metric label để phục vụ tìm kiếm từng bản ghi.

## 5. Phân biệt ba loại dữ liệu quan sát

Trong hệ kết hợp Spring Modulith và Micrometer, ba luồng dữ liệu phục vụ các mục đích khác nhau:

| Loại | Dùng để làm gì? | Cardinality và dữ liệu nhạy cảm |
| --- | --- | --- |
| **Metric** | Tổng hợp tần suất, tỷ lệ lỗi, latency theo nhóm | Label phải có số giá trị thấp, ổn định |
| **Trace** | Xem các bước của một request hoặc event, độ trễ và quan hệ nhân quả | Thuộc tính có thể chi tiết hơn metric nhưng vẫn phải kiểm soát PII/secret và chi phí |
| **Log / event registry** | Điều tra một ca cụ thể, audit hoặc trạng thái event publication | Có thể chứa dữ liệu chi tiết nếu chính sách cho phép, cần kiểm soát quyền và retention |

Trong Micrometer Observation, **low-cardinality key values** thường được dùng cho metric tags, còn **high-cardinality key values** có thể được dùng cho trace context/attributes khi observation handler tương ứng xử lý. Việc đánh dấu high-cardinality không biến một giá trị bí mật thành an toàn; cần kiểm tra nó có được xuất ra backend nào và có thực sự cần thu thập không.

Quan trọng: nhiều giá trị khác nhau trong trace attributes **không tự động làm tăng Prometheus time series**. Vấn đề xảy ra khi chúng được chuyển thành nhãn metrics, ví dụ thông qua custom convention, span-to-metrics processor hoặc connector tạo metrics từ traces. Đừng xử lý sự cố nhãn Prometheus bằng cách tắt mọi tracing trước khi xác minh đường chuyển dữ liệu.

## 6. Quy trình chẩn đoán theo từng tầng

Một sơ đồ định hướng:

~~~mermaid
flowchart TD
    A["Cảnh báo series tăng / TSDB quá tải"] --> B["Xác định khoảng thời gian và job"]
    B --> C["Tìm metric tăng series"]
    C --> D["Tìm label có nhiều giá trị"]
    D --> E{"Nguồn tạo label?"}
    E --> F["HTTP / custom meter"]
    E --> G["Event / module observation"]
    E --> H["Collector / relabel / spanmetrics"]
    F --> I["Sửa tag schema và thêm giới hạn"]
    G --> I
    H --> I
    I --> J["Kiểm tra traffic, latency, lỗi và series sau rollout"]
    J --> K["Lưu regression test và dashboard an toàn"]
~~~

Nên thực hiện theo thứ tự để tránh tốn thời gian tìm ở listener khi nguyên nhân thực tế nằm trong exporter hoặc reverse proxy.

### Bước 1 — Ghi phạm vi sự cố

Ghi lại thời điểm bắt đầu, service/job/pod bị ảnh hưởng, phiên bản ứng dụng, thay đổi cấu hình, thay đổi sampling/histogram và số lượng target scrape. So sánh QPS và số event processed với tốc độ tạo series. Nếu hệ thống tăng số instance gấp đôi thì số series có thể tăng theo số instance, nhưng vẫn cần kiểm tra liệu mức tăng có phù hợp hay vượt xa mức đó.

Đặt câu hỏi: có vừa thêm tag, chuyển từ URL template sang URL đầy đủ, kích hoạt telemetry cho một module, tăng số loại event hay thay đổi collector processor không?

### Bước 2 — Quan sát sức khỏe TSDB trước

Với Prometheus tự vận hành, có thể xem các chỉ số nội bộ như:

~~~promql
prometheus_tsdb_head_series
~~~

Và tốc độ tạo series:

~~~promql
rate(prometheus_tsdb_head_series_created_total[5m])
~~~

Tên metric nội bộ và availability phụ thuộc phiên bản/kiểu backend. Đây là tín hiệu **cấp Prometheus server**, không tự phân chia nguyên nhân theo application module. Với dịch vụ metrics managed, dùng dashboard series/head/ingestion do nhà cung cấp hỗ trợ.

Đồng thời kiểm tra số target scrape, tốc độ mẫu, remote-write backlog, CPU/RAM và query latency. Một sự cố có thể kết hợp tăng số series với tăng số mẫu do scrape interval thay đổi.

### Bước 3 — Tìm job và metric gây tăng series

Giới hạn câu truy vấn vào job nghi ngờ, ví dụ `job="shop-service"`:

~~~promql
count({job="shop-service"})
~~~

Đây là số chuỗi hiện diện theo selector tại thời điểm truy vấn, không đo tất cả series lịch sử đã bị xóa. Để tìm tên metric có nhiều series, có thể dùng:

~~~promql
topk(
  20,
  count by (__name__) ({job="shop-service"})
)
~~~

Kết quả là danh sách tên metric và số series theo tên. Trên Prometheus lớn, truy vấn quét nhiều series có thể nặng; nên lọc thêm `namespace`, `instance` hoặc prefix metric, sử dụng công cụ cardinality analysis của backend khi có, và chạy ngoài lúc hệ thống quá tải.

Sau khi đã tìm được metric nghi ngờ (giả sử tên metric Prometheus là `shop_module_event_processed_total`), tiếp tục khoanh vùng label:

~~~promql
count by (module) (
  shop_module_event_processed_total{job="shop-service"}
)
~~~

~~~promql
count by (event_type) (
  shop_module_event_processed_total{job="shop-service"}
)
~~~

Các truy vấn trên đếm **số series thuộc mỗi giá trị label**, không đếm số event. Nếu `module` chỉ có 8 giá trị nhưng `event_type` có 40.000 giá trị, xem xét một loại event đang bị gắn trực tiếp tên động hay payload làm event type.

Để ước lượng số giá trị `event_type` khác nhau trong những series hiện diện:

~~~promql
count(
  count by (event_type) (
    shop_module_event_processed_total{job="shop-service"}
  )
)
~~~

Không phải metric nào cũng có label `event_type`; trước tiên cần đọc tên label thực tế của tập series nghi ngờ. Nếu nhãn vắng mặt, kết quả có thể gây hiểu nhầm. Dùng query tương ứng với tên nhãn trong exporter.

### Bước 4 — Kiểm tra HTTP metric và route

Một nguồn gây cardinality rất phổ biến là đường dẫn HTTP đầy đủ:

~~~text
Tốt:
  uri="/orders/{orderId}"

Không tốt:
  uri="/orders/ORD-000001"
  uri="/orders/ORD-000002"
  uri="/orders/ORD-000003"
~~~

Với Micrometer, tên Java meter thường là `http.server.requests`, còn khi xuất sang Prometheus, tên có thể thành họ metric như `http_server_requests_seconds_count` tùy cấu hình và phiên bản. Một truy vấn tham khảo:

~~~promql
count by (uri) (
  http_server_requests_seconds_count{job="shop-service"}
)
~~~

Nếu kết quả hiển thị quá nhiều path có ID cụ thể, cần kiểm tra cách tạo `uri` tag, route mapping, custom `ObservationConvention` hoặc filter thêm tag. Khi framework không nhận diện được route, một fallback path hoặc giá trị `UNKNOWN` có thể xuất hiện; phải kiểm tra cấu hình thực tế trước khi tự sửa.

Dùng route pattern ổn định (ví dụ `/orders/{orderId}`). Không sao chép URL chứa query string, JWT hoặc customer identifier vào `uri` tag.

### Bước 5 — Từ metric quay về mã nguồn instrumentation

Khi đã xác định tên metric và label, tìm nơi đăng ký meter, thêm tag hoặc chuyển observation thành metric. Những điểm cần kiểm tra trong mã ứng dụng:

- `Counter.builder(...)`, `Timer.builder(...)`, `Gauge.builder(...)`, `DistributionSummary.builder(...)`.
- `meterRegistry.counter(name, tags...)` hoặc `Timer.Sample.stop(...)` với tags động.
- `Observation.createNotStarted(...)` và các convention gắn low-cardinality key values.
- Annotation metrics/observation với tham số làm metric tag.
- HTTP instrumentation, scheduler, messaging, database client hoặc custom interceptor.
- Processor trong collector chuyển span attribute/event attribute thành label metric.

Không chỉ tìm chữ `eventId`: tag có thể mang tên `key`, `identifier`, `entity`, `name`, `uri`, `exception` hoặc `operation` nhưng giá trị được sinh động từ input. Cần đọc cách **tạo giá trị** của label, không chỉ tên label.

## 7. Các nguồn cardinality thường gặp trong Spring Modulith

### 7.1. Gắn ID của domain event vào metric

Ví dụ sai:

~~~java
Timer.builder("shop.module.event.duration")
    .tag("module", "notification")
    .tag("event.type", "OrderPlaced")
    .tag("event.id", event.id().toString())
    .register(meterRegistry);
~~~

Nếu mỗi event có ID khác nhau, mỗi lần gọi `register` với ID khác tạo ra một meter identity mới.

Sửa bằng cách loại `event.id` khỏi metric tags và giữ các chiều có tập giá trị đã biết: module, event type, outcome. Nếu cần time correlation, dùng trace ID do hệ tracing cấp và chỉ đưa vào log/traces phù hợp; không biến trace ID thành metric tag.

### 7.2. Dùng tên class động hoặc nội dung `toString()` làm event type

Không nên:

~~~java
String eventType = event.toString(); // Có thể chứa orderId, email, dữ liệu động
counter.tag("event.type", eventType);
~~~

Tốt hơn là chọn một tên event type ổn định từ danh mục đã kiểm soát, ví dụ `OrderPlaced`, `PaymentAuthorized`, `StockLow`; không sử dụng nguyên payload hoặc tên class tạo động từ dữ liệu người dùng.

Nếu module xử lý nhiều loại event do plugin phát sinh, cần đưa chúng vào taxonomy có giới hạn và nhóm ngoại lệ về `other` sau khi thống nhất phạm vi quan sát.

### 7.3. Gắn tên module hoặc operation không ổn định

Tên module trong Spring Modulith thường là tập nhỏ do ứng dụng phát hiện. Tuy nhiên, nếu instrumentation tạo tag `module` từ input như `tenantId`, `documentName` hoặc `orderId`, nhãn này không còn là tên module thật.

Đối với operation, dùng tên logic ổn định `placeOrder`, `reserveStock`, `publishEvent`, không dùng `operation=process-order-12345`.

### 7.4. Gắn email hoặc user ID vào metrics

Một nhãn vừa nhiều giá trị vừa có nguy cơ lộ thông tin:

~~~java
Counter.builder("shop.module.error")
    .tag("customer.email", customerEmail)
    .tag("order.id", orderId)
    .register(meterRegistry)
    .increment();
~~~

Sửa bằng `error.category=validation` hoặc `integration=payment`, `outcome=failure`. Nếu cần phân tích theo khách hàng, thực hiện ở hệ thống truy vấn nghiệp vụ có kiểm soát quyền và dữ liệu, không dùng metrics time series làm kho tìm kiếm khách hàng.

### 7.5. Bật histogram quá rộng

Sau khi một Timer/DistributionSummary bật percentile histogram hoặc nhiều SLO buckets, số series có thể tăng đáng kể ngay cả khi tập label không đổi. Kiểm tra cấu hình phân phối, loại metric và số buckets. Histogram là lựa chọn có ích để tính percentiles hoặc SLO tổng hợp; không cần tắt toàn bộ mà nên xác định operation cần đo và bộ buckets phù hợp.

### 7.6. Collector tạo metrics từ trace

Một collector có thể sinh latency/call-count metrics từ spans. Nếu processor lấy `span.name` hoặc một span attribute chứa URL đầy đủ, event ID hoặc user ID làm label, metric cardinality tăng dù mã Spring không gọi `Counter.builder`. Cần xem cấu hình processor và metric exporter trong tuyến telemetry đang dùng.

Module graph hoặc Actuator không tự biến dependency thành một chuỗi metrics cho mỗi request. Số module hữu hạn thường không gây bùng nổ; **tag động** trên các tương tác mới là nguyên nhân cần tìm.

## 8. Thiết kế bộ nhãn chuẩn cho observability module

Một schema nhãn metric cho tương tác application module nên có tập giá trị hữu hạn:

| Nhãn | Ví dụ | Lý do hữu ích |
| --- | --- | --- |
| `module` | `ordering`, `payment` | Theo dõi nguồn/tác nhân trong kiến trúc module |
| `target_module` | `inventory`, `notification` | So sánh đường tương tác đã được thiết kế |
| `event.type` | `OrderPlaced`, `StockLow` | Phân loại luồng event |
| `operation` | `reserveStock`, `charge` | Theo dõi operation ổn định |
| `outcome` | `success`, `failure` | Tính tỷ lệ lỗi |
| `error.category` | `timeout`, `validation`, `other` | Chẩn đoán nhóm lỗi |
| `environment` | `prod`, `staging` | So sánh môi trường nếu backend thu nhiều môi trường |

Không phải metric nào cũng cần đủ bảy nhãn. Bắt đầu bằng ít nhãn nhất đáp ứng câu hỏi giám sát. Mỗi nhãn bổ sung làm tăng số tổ hợp có thể; cần kiểm tra khi thêm một dimension.

Những giá trị **không nên** trở thành tag: `eventId`, `orderId`, `requestId`, `traceId`, `customerEmail`, `jwt`, session token, IP người dùng, path URL đầy đủ có ID, exception message có tham số, raw SQL và nội dung payload.

### Ngân sách cardinality

Một nhóm có thể đặt ngân sách định tính rồi đo bằng dữ liệu thật. Ví dụ bảng ngân sách *minh họa*:

| Metric | Nhãn được phép | Giới hạn cần giám sát |
| --- | --- | --- |
| Event processed | `module`, `event.type`, `outcome` | Tập module và event type đã đăng ký |
| HTTP request duration | `method`, `uri` dạng route, `status` | Số route có kiểm soát |
| Module call duration | `source.module`, `target.module`, `operation`, `outcome` | Không vượt số module/operation trong kiến trúc |
| Event publication backlog | `module`, `event.type`, `state` | Tránh label theo publication ID |

Các con số budget cụ thể phải xác định từ kích thước hệ thống, số replica, số buckets và chi phí backend. Nếu thêm module mới, một số label value mới là hợp lệ; nếu thêm event ID mới mỗi request thì mức tăng không bị chặn bởi catalog đó.

## 9. Instrumentation bằng Micrometer không tạo tag động

Một ví dụ cho thời gian xử lý event, giả định `meterRegistry` được inject và `handleBusinessEvent` xử lý nghiệp vụ:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

void onOrderPlaced(OrderPlaced event) {
    long started = System.nanoTime();
    String outcome = "success";

    try {
        handleBusinessEvent(event);
    } catch (RuntimeException ex) {
        outcome = "failure";
        throw ex;
    } finally {
        long elapsed = System.nanoTime() - started;

        Timer.builder("shop.module.event.duration")
            .description("Event handler duration")
            .tag("module", "notification")
            .tag("event.type", "OrderPlaced")
            .tag("outcome", outcome)
            .register(meterRegistry)
            .record(elapsed, TimeUnit.NANOSECONDS);
    }
}
~~~

`OrderPlaced`, `handleBusinessEvent` và `meterRegistry` là các thành phần minh họa của dự án; đây là phần method chứ không phải một class Java độc lập. Các giá trị tag cố định hoặc thuộc enum nhỏ, vì thế mỗi tổ hợp được dùng lại để cập nhật cùng meter.

Không dùng exception message hoặc `ex.getMessage()` làm `error.category`. Nếu cần phân loại, ánh xạ exception thành một tập mã ổn định như `timeout`, `validation`, `dependency_failure`, `other`.

### Nếu cần quan sát qua Observation API

Có thể dùng low-cardinality key values với một tập khóa/value có chủ đích:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

void observeOrderPlaced(ObservationRegistry registry,
                        Runnable work) {
    Observation.createNotStarted(
            "shop.module.event", registry)
        .lowCardinalityKeyValue("module", "notification")
        .lowCardinalityKeyValue("event.type", "OrderPlaced")
        .observe(work);
}
~~~

Instrumentation cụ thể có tạo meter hoặc span hay không còn phụ thuộc các ObservationHandlers được cấu hình. Nếu kết hợp cả manual Timer và một Observation tạo timer cho cùng thao tác, cần kiểm tra tránh double-count. Không đưa `event.id()` vào low-cardinality key values.

## 10. Sử dụng `MeterFilter` như lớp bảo vệ bổ sung

Sửa giá trị tag tại nguồn vẫn là ưu tiên đầu tiên. Trong lúc khắc phục sự cố hoặc bảo vệ tránh hồi quy, Micrometer hỗ trợ `MeterFilter` để lọc/giới hạn meter được đăng ký.

### 10.1. Xóa tag nguy hiểm khỏi một số metric

Một ví dụ filter bảo vệ ở mức registry:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricsGuardConfiguration {

    @Bean
    MeterFilter removeUnsafeTags() {
        return MeterFilter.ignoreTags(
            "order.id",
            "event.id",
            "customer.email",
            "trace.id");
    }
}
~~~

`ignoreTags` áp dụng ở mức registry, nên có thể ảnh hưởng nhiều metric. Nó chỉ hữu ích khi nhóm đã thống nhất rằng các tag ấy không nên có trong bất kỳ metric nào được quản lý bởi registry đó. Nếu tên tag thực tế khác, filter sẽ không chặn được; cần đọc mẫu metric đã xuất.

### 10.2. Giới hạn số giá trị tag

Ví dụ thêm một ngưỡng để tránh event type tăng vô hạn:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;

@Bean
MeterFilter capEventTypeValues() {
    return MeterFilter.maximumAllowableTags(
        "shop.module.event",
        "event.type",
        50,
        MeterFilter.deny());
}
~~~

Ý tưởng là khi số giá trị tag `event.type` vượt ngưỡng 50 cho các meter có prefix chỉ định, những meter mới vượt ngưỡng bị từ chối đăng ký. Đây là **cầu chì an toàn**, không phải cách sửa tận gốc. Một event type hợp lệ xuất hiện sau khi đã hết ngân sách có thể bị mất metric; phải có cảnh báo, log an toàn hoặc quy trình điều tra riêng cho việc bị deny.

Những điểm cần nhớ:

- Chọn prefix metric và tên tag chính xác, xác định ngưỡng dựa trên ngân sách đã thống nhất.
- Filter không retroactively xóa mọi meter đã tồn tại trong registry.
- Đặt filter sớm trong vòng đời ứng dụng trước khi instrumentation đăng ký nhiều meter.
- Kiểm tra thứ tự tương tác giữa các filter và liệu metrics auto-config/custom registry có nhận filter.
- Không dùng filter để hợp thức hóa việc đưa dữ liệu cá nhân vào metric trong một khoảng ngắn; dữ liệu có thể đã được xuất trước khi bị chặn.

### 10.3. Không đưa user input thành nhãn `uri`

Một filter generic không phải lúc nào cũng có thể biến `/orders/123` thành `/orders/{id}` chính xác. Tốt nhất là sửa nơi tạo HTTP observation để lấy route template đã được framework nhận diện, hoặc viết quy tắc chuẩn hóa có kiểm thử. Regex cắt bừa path có thể trộn nhiều endpoint quan trọng hoặc vẫn bỏ sót các ID mới.

## 11. Vai trò của Actuator và module graph trong quá trình khoanh vùng

Actuator là bề mặt hữu ích để xem meter registry và dữ liệu quản trị. Ví dụ, nếu ứng dụng expose metrics endpoint cho nhóm vận hành đã xác thực, có thể kiểm tra tên meter:

~~~text
GET /actuator/metrics
GET /actuator/metrics/http.server.requests
~~~

Endpoint metrics của Spring Boot có thể hiển thị `availableTags` và số đo của một meter tùy tên meter/phiên bản. Nó giúp thấy tag key và một phần tag values **trong registry ứng dụng**, nhưng không thay thế phân tích toàn bộ TSDB vì Prometheus thêm target labels, có retention và có thể thu dữ liệu từ nhiều replica.

Nếu ứng dụng cấu hình endpoint Prometheus:

~~~text
GET /actuator/prometheus
~~~

Chỉ truy cập từ mạng/role vận hành đã được cho phép. Việc expose metrics có thể làm lộ tên endpoint, tên module hoặc tag nhạy cảm đã lỡ ghi; đừng mở công khai để debug cardinality.

### Dùng module graph để tìm phạm vi tương tác

Tài liệu tạo từ Spring Modulith `Documenter` và mô hình `ApplicationModules` có thể cho biết module nào có nhiều dependency, event listener nào thuộc module nào và các đường đi tiềm năng cần xem xét. Chẳng hạn, nếu `notification` vừa được thêm listener cho nhiều event của `ordering`, bắt đầu kiểm tra timer/counter của module đó.

Tuy nhiên **module graph là hình ảnh phụ thuộc kiến trúc**, không phải thống kê số time series. Nó không tự chỉ ra nhãn `event.id` bị tạo động. Để khoanh vùng đầy đủ, phải đối chiếu graph với metric name, label set, traces và thay đổi instrumentation.

## 12. Sự cố giả lập: sau triển khai, Prometheus tăng 20 lần

**Bối cảnh.** Ứng dụng có 6 application module. Nhóm vừa bật observability cho các event listener trong `notification` và triển khai một collector mới. Sau 30 phút:

- Số head series tăng mạnh.
- Tốc độ request HTTP và số đơn hàng xử lý chỉ tăng nhẹ.
- Dashboard event duration load chậm, remote-write queue xuất hiện độ trễ.

**Bước xác định nguồn.** Truy vấn số series theo tên metric cho `job="shop-service"` cho thấy `shop_module_event_duration_seconds_bucket` nằm đầu danh sách. Kiểm tra metric tags thấy có label `event_id`. Đây là nhãn mới xuất hiện cùng lần triển khai.

**Nguyên nhân.** Mỗi sự kiện `OrderPlaced` có một UUID riêng. Timer được đăng ký theo UUID rồi exporter còn tạo nhiều bucket histogram cho mỗi tổ hợp tag. Cardinality tăng theo **số sự kiện duy nhất × số buckets × các dimension khác**, chứ không theo số loại nghiệp vụ.

**Khắc phục.** Loại `event_id` khỏi metric, giữ `module`, `event_type` và `outcome`. Chỉ bật histogram cho operation thật sự cần tính latency distribution; xem lại bucket config. Tạo filter làm cầu chì an toàn cho số tag values.

**Xác nhận.** Sau khi rollout, tốc độ tạo series mới giảm. Việc Prometheus `head_series` không lập tức trở về mức trước không đồng nghĩa bản sửa thất bại: các series cũ có thể còn trong TSDB và các meter cũ có thể tồn tại cho đến khi pod cũ được thay thế. Theo dõi qua nhiều scrape interval, quy tắc staleness/retention và số series mới, đồng thời xác nhận tỷ lệ event processing, lỗi và latency còn đầy đủ.

Nếu sau sửa số series tiếp tục tăng, kiểm tra collector span-to-metrics hoặc các replica chưa cập nhật. Một ứng dụng đã sửa code nhưng collector vẫn chuyển `traceId` thành label có thể tiếp tục gặp cùng triệu chứng.

## 13. Phương án ứng phó khi production đang quá tải

Khi sức khỏe của metrics backend đang bị ảnh hưởng, cân nhắc ưu tiên theo mức độ:

1. **Chặn nguồn tạo nhãn động** ở service/collector bằng cấu hình đã kiểm tra hoặc bản sửa instrumentation.
2. **Giới hạn ingestion của metric gây hại** theo chính sách backend, cân nhắc drop riêng metric hoặc series nguy hiểm. Ghi rõ dashboard/alert nào tạm bị ảnh hưởng.
3. **Kiểm soát khả năng hiển thị telemetry**; không lưu raw event payload, credential hoặc customer ID vào log/trace để thay thế metrics.
4. **Giảm query tốn tài nguyên** và kiểm tra remote-write/TSDB. Không chạy truy vấn toàn bộ series lặp đi lặp lại khi Prometheus đang mất ổn định.
5. **Phục hồi instrumentation có nhãn cố định**, triển khai theo nhóm nhỏ nếu cần, theo dõi series creation rate, memory, scrape samples và nghiệp vụ.
6. **Khôi phục cảnh báo và dashboard** sau khi bảo đảm các label chủ chốt vẫn được xuất đầy đủ.

Tăng RAM hoặc giới hạn retention có thể giúp backend tồn tại tạm thời nhưng không xử lý nguyên nhân nếu ứng dụng vẫn phát hành hàng nghìn nhãn mới mỗi phút.

Đặt ngưỡng cảnh báo theo baseline thật của hệ thống; một thay đổi hợp lệ như thêm module hoặc tăng replica vẫn tạo thêm series. Cần theo dõi cả **mức tuyệt đối** và **tốc độ tạo series** thay vì chỉ một ngưỡng cố định.

## 14. Kiểm chứng sau sửa: đừng chỉ nhìn biểu đồ series

Một bản sửa tốt vừa giảm cardinality vừa giữ khả năng chẩn đoán hệ thống:

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Prometheus head series | Ngừng tăng bất thường, dần ổn định theo lifecycle |
| Series creation rate | Giảm rõ so với giai đoạn gặp sự cố |
| Metrics theo module/event type | Vẫn có giá trị hợp lệ, không bị filter chặn hết |
| Counter event processed | Tổng tăng phù hợp lượng event thực tế |
| Timer event latency | Ghi được duration cần thiết, bucket hợp lý |
| Actuator metrics | Tên meter và tag keys khớp schema đã duyệt |
| Traces | Vẫn liên kết được request và listener khi cấu hình propagation cho phép |
| Dữ liệu nhạy cảm | Không có ID cá nhân, payload, token trong metric tags |
| Module graph / kiểm tra ranh giới | Không thay đổi thiết kế module ngoài phạm vi sửa |
| Ứng dụng Java | MeterRegistry/heap không còn lớn lên theo số request/event duy nhất |

Nếu đang có hệ thống trace hoặc event publication registry, nên kiểm tra riêng một case lỗi retry và một case xử lý bất đồng bộ. Việc bỏ `eventId` khỏi metric không nên làm mất event delivery, module correlation hay thông tin lỗi nghiệp vụ vì các cơ chế đó độc lập với tập nhãn metrics.

### Thử nghiệm phát hiện cardinality regression

Một integration test có thể tạo nhiều event khác ID nhưng cùng event type, sau đó kiểm tra số meter identity của metric ứng dụng không tăng theo số event. Ý tưởng:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import static org.assertj.core.api.Assertions.assertThat;

@Test
void eventIdsDoNotCreateNewMetricSeries() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    EventMetrics metrics = new EventMetrics(registry);

    for (int i = 0; i < 1_000; i++) {
        metrics.recordProcessed(
            "notification",
            "OrderPlaced",
            "success",
            "event-" + i);
    }

    long distinctMeters = registry.getMeters().stream()
        .filter(m -> m.getId().getName()
                .equals("shop.module.event.processed"))
        .count();

    assertThat(distinctMeters).isEqualTo(1);
}
~~~

`EventMetrics` ở đây là **class minh họa cần được triển khai**; method `recordProcessed` nhận ID để test chứng minh instrumentation không dùng nó làm tag. Giả định method tăng một counter duy nhất và không tạo thêm meter khác cùng tên. Test này kiểm tra cấu trúc metric identity trong Micrometer, không cần chạy Prometheus và không kiểm tra tất cả processor ở collector.

Có thể bổ sung contract test cho low-cardinality labels, lint/tag allowlist và kiểm thử smoke kiểm tra export sau một tập request đại diện. Không nên dùng một test chỉ phản chiếu cách xây tags hiện tại; hãy khẳng định **giới hạn có ý nghĩa**, ví dụ 1.000 event IDs không tạo thêm 1.000 meter identities.

## 15. Lưu ý khi có tracing và context propagation

Khi một HTTP request kích hoạt domain event bất đồng bộ, correlation giữa `ordering` và `notification` có thể cần context propagation. Tình trạng thiếu trace liên kết và tăng cardinality có thể xuất hiện cùng lúc sau khi thay đổi instrumentation nhưng có nguyên nhân khác nhau.

Ví dụ:

~~~text
trace A
  HTTP POST /checkout
    ordering.placeOrder
      publish OrderPlaced
        notification.onOrderPlaced
~~~

Có thể giữ `traceId` trong hệ tracing để đối chiếu span với log an toàn. Nhưng **không** gắn `traceId` thành tag của Timer/Counter, vì mỗi trace thường mang một ID khác. Tương tự, request ID trong MDC nên được giới hạn ở log/trace nếu phù hợp, không tự chuyển sang metric dimensions.

Baggage có thể được truyền tới thread hoặc service khác theo cấu hình; nếu baggage chứa user ID, tenant ID hoặc dữ liệu cá nhân rồi một ObservationConvention lấy baggage làm low-cardinality tag, cardinality và rủi ro lộ dữ liệu sẽ tăng cùng lúc. Rà soát các convention và processor chuyển thuộc tính từ tracing sang metrics.

Mỗi hệ telemetry có quy tắc sampling và retention riêng. Giảm trace sampling không tự làm giảm series từ một `Counter.builder` gắn ID động; phải sửa chính đường tạo label.

## 16. Kiểm soát thay đổi dài hạn

Sau khi phục hồi hệ thống, nên đưa một số nguyên tắc thành quy ước phát triển:

- Mỗi metric mới phải có tài liệu về tên, mục đích, đơn vị, các nhãn cho phép, số giá trị dự kiến và nguồn dữ liệu.
- Mỗi nhãn mới phải được review: giá trị là tập enum/route ổn định hay được sinh theo user/event/request?
- Cấm thông tin cá nhân, token, secret, payload và ID duy nhất trong metric tags.
- Kiểm tra các custom `MeterFilter`, histogram config và collector processor khi thay Spring Boot, Spring Modulith, Micrometer hoặc exporter.
- Với `@Observed` và các ObservationConvention tự viết, phân biệt low/high cardinality và kiểm tra output metrics thực tế.
- Định kỳ review dashboard để phát hiện metric có series lớn dù không còn hữu ích.
- Đối chiếu module graph với catalog các nhãn `module` và `event_type`; loại bỏ nhãn module được tạo từ input động.
- Khi thêm metric event publication, không dùng publication ID làm tag dù muốn dễ tra cứu từng event.
- Đặt cảnh báo cho series creation rate, active series, ingestion quota và độ trễ remote-write.

Một nhóm tốt sẽ đo được module nào thường lỗi, listener nào chậm và luồng nào liên quan qua traces, **mà không tạo một time series cho mỗi đơn hàng**.

## 17. Bài thực hành có hướng dẫn

Giả sử một ứng dụng Spring Boot tích hợp Spring Modulith với `inventory` và `ordering`. Một metric tùy biến đang được đăng ký:

~~~java
Counter.builder("shop.order.processed")
    .tag("module", "ordering")
    .tag("order.id", orderId)
    .tag("outcome", "success")
    .register(registry)
    .increment();
~~~

### Nhiệm vụ

1. Giải thích vì sao `order.id` làm cardinality tăng khi mỗi request tạo order mới.
2. Dùng `SimpleMeterRegistry` gửi thử 100, 1.000 và 10.000 order ID giả rồi đo số `Meter.Id` của `shop.order.processed`. Chỉ dùng dữ liệu giả và môi trường test.
3. Sửa instrumentation để chỉ dùng `module`, `operation`, `outcome`; chạy lại và giải thích vì sao counter tăng giá trị nhưng số meter không tăng theo order.
4. Tạo một metric latency với Timer. Thử bật histogram trong môi trường test và so sánh số series khi xuất Prometheus với không bật histogram.
5. Đặt `MeterFilter` giới hạn tag values cho một metric tùy biến; xác minh khi vượt ngưỡng, thông tin nào bị mất.
6. Nếu có Prometheus thử nghiệm, sử dụng các truy vấn `count by (__name__)` và `count by (uri)` để tìm metric/tags nhiều giá trị.
7. Cho một event chuyển từ `ordering` sang `inventory`, kiểm tra trace liên kết giữa module. Xác nhận trace ID không bị dùng làm metric label.
8. Ghi lại kết quả: series trước/sau, tốc độ tạo series, mức heap ứng dụng, độ đầy đủ của dashboard và những trường telemetry không nên thu.

### Câu hỏi tự đánh giá

- Vì sao 100.000 event không nhất thiết tạo 100.000 time series?
- Khi thêm `orderId` vào một Timer có histogram, ảnh hưởng có thể lớn hơn thêm vào Counter như thế nào?
- Vì sao `prometheus_tsdb_head_series` tăng không đủ để xác định lỗi nằm ở module nào?
- Khi nào cần xem collector thay vì sửa mã Spring?
- `MeterFilter.deny()` có thể gây tác dụng phụ gì nếu quá nhiều loại event hợp lệ xuất hiện?
- Vì sao high-cardinality trace attribute không giống metric label và vẫn có rủi ro bảo mật riêng?

## 18. Checklist xử lý sự cố và tiêu chí hoàn thành

- [ ] Xác định thời điểm cardinality tăng, deployment và các target/job liên quan.
- [ ] So sánh traffic, event rate, active series và tốc độ tạo series để phân biệt nguyên nhân.
- [ ] Tìm được tên metric và label có số giá trị tăng bất thường.
- [ ] Truy ngược được nguồn tạo label: ứng dụng, HTTP instrumentation, module observation hay collector.
- [ ] Loại ID động, email, token, payload và raw URL khỏi metric dimensions.
- [ ] Nhãn `module`, `event_type`, `operation`, `outcome` có catalog ổn định.
- [ ] Đã đánh giá histogram/buckets, số instance và tag bổ sung từ backend.
- [ ] Đã kiểm tra `MeterFilter` như lớp dự phòng, có theo dõi metric bị từ chối.
- [ ] Còn đủ counter, duration, error rate cho các module và listener quan trọng.
- [ ] Trace/context propagation vẫn hoạt động và không rò dữ liệu nhạy cảm sang metrics.
- [ ] Đã theo dõi nhiều chu kỳ scrape và xác nhận series creation rate giảm sau rollout.
- [ ] Có test hoặc quy trình review chặn việc thêm nhãn theo từng user/order/event sau này.

**Tiêu chí xác nhận:** Sự cố được giải quyết khi nguồn tạo nhãn động đã bị loại bỏ hoặc giới hạn có kiểm soát, các series mới không còn tăng bất thường và các tín hiệu quan sát cần thiết cho Spring Modulith vẫn chính xác. Chỉ tăng dung lượng Prometheus hoặc giảm sampling khi chưa tìm nhãn gây lỗi là chưa xử lý nguyên nhân.
