# Tránh dashboard dùng tag cardinality cao

## 1. Vì sao dashboard cần quan tâm đến cardinality?

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, các application module như **orders**, **payments**, **inventory** và **notifications** có thể phát domain event, gọi API của module khác và xử lý công việc bất đồng bộ. Nhóm vận hành thường xây dựng dashboard để theo dõi số event được công bố, thời lượng xử lý, tỷ lệ lỗi và các module đang hoạt động.

Một dashboard hữu ích phải trả lời câu hỏi vận hành nhanh:

- Module nào đang phát nhiều event nhất?
- Loại event nào tăng bất thường sau lần triển khai gần nhất?
- Tỷ lệ lỗi và thời lượng xử lý của các module thay đổi thế nào?
- Khi một chỉ số bất thường, có thể mở trace hoặc log liên quan để điều tra không?

Một sai lầm thường gặp là thêm **user ID, order ID, request ID hoặc trace ID** làm metric tag/label, sau đó tạo biến dashboard để lọc theo các giá trị đó. Cách làm này khiến mỗi giá trị mới có thể tạo thêm một time series. Khi số người dùng và giao dịch tăng, số series tăng theo, gây tốn bộ nhớ, dung lượng lưu trữ, thời gian truy vấn và chi phí monitoring.

Bài **“Tránh dashboard dùng tag cardinality cao”** thuộc chương **Dashboard** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Mục tiêu là thiết kế dashboard theo các chiều đo có tập giá trị giới hạn, nhận diện truy vấn và biến dashboard gây tải, rồi dùng logs/traces để drill-down khi cần điều tra một giao dịch cụ thể.

Sau bài học, bạn có thể:

- Giải thích metric label, time series và cardinality.
- Phân biệt cardinality do instrumentation tạo ra với số kết quả một dashboard panel hiển thị.
- Thiết kế dashboard Spring Modulith theo module, event type, outcome và môi trường.
- Viết PromQL và Grafana variables dùng các chiều đo có giới hạn.
- Nhận diện các mẫu truy vấn nguy hiểm như liệt kê mọi user ID hoặc group theo request ID.
- Kết hợp metrics, traces, logs và exemplars để chuyển từ biểu đồ tổng hợp sang một trường hợp cụ thể.
- Đặt guardrail tại Micrometer, Prometheus và quy trình review dashboard.

## 2. Metric label và time series

Một metric thường có tên và một tập nhãn dạng key-value. Trong Micrometer, nhãn thường được gọi là **tag**; khi export sang Prometheus, chúng trở thành **labels**.

Ví dụ counter ghi nhận domain event publication:

~~~text
module_events_published_total{
  module_identifier="orders",
  module_event_type="OrderPlaced",
  channel="web"
}
~~~

Tên metric và tập label xác định một time series. Khi giá trị của counter tăng, dữ liệu mới được ghi vào chính series đó. Nếu một label thay đổi giá trị, tổ hợp mới có thể tạo một series khác.

**Cardinality** là số tổ hợp giá trị khác nhau có thể xuất hiện cho một metric. Với các label có tập giá trị lần lượt là V1, V2, ..., Vk, giới hạn trên lý thuyết là:

\[
N_{\text{series}} \leq \prod_{i=1}^{k} V_i
\]

Ví dụ:

| Label | Số giá trị có thể có |
| --- | ---: |
| module_identifier | 5 |
| module_event_type | 8 |
| channel | 3 |
| outcome | 2 |
| Tổng tổ hợp lý thuyết | 240 |

Con số 240 là giới hạn trên trước khi xét các ràng buộc thực tế. Không phải mọi event type đều được phát từ mọi module hoặc mọi channel.

Nếu thêm label user_id với 100.000 người dùng, giới hạn trên tăng thành 24 triệu tổ hợp. Nếu request_id thay đổi gần như ở mỗi request, số series có thể tăng theo lượng traffic thay vì theo quy mô kiến trúc.

### 2.1. Những label thường có cardinality cao

| Label | Ví dụ giá trị | Vì sao nguy hiểm? |
| --- | --- | --- |
| user_id | UUID hoặc mã tài khoản | Tập giá trị tăng theo số người dùng. |
| order_id | Mã đơn hàng | Gần như mỗi giao dịch có một giá trị mới. |
| request_id | UUID mỗi request | Tăng theo số request. |
| trace_id, span_id | ID tracing | Mỗi trace/span có định danh riêng. |
| Email, số điện thoại | Giá trị liên hệ | Vừa có cardinality cao vừa có nguy cơ lộ dữ liệu cá nhân. |
| URL thô | /orders/10001, /orders/10002 | Mỗi path parameter có thể tạo label khác. |
| Exception message | Nội dung message chứa dữ liệu động | Vô số chuỗi khác nhau. |
| SQL statement thô | Câu lệnh có literal động | Mỗi giá trị tham số có thể tạo chuỗi mới. |
| File name hoặc session ID | Tên file/session riêng | Giá trị phát sinh liên tục. |

Những label thường có thể kiểm soát tốt hơn:

- module_identifier: tên module được khai báo trong ứng dụng.
- module_event_type: tên một tập event class đã biết.
- outcome: success, failure, unknown.
- channel: web, mobile, store.
- environment: dev, staging, prod.
- region: danh sách region đã cấu hình.
- http_method: GET, POST, PUT, DELETE.
- http_route: route template như /orders/{orderId}, không phải URL có ID cụ thể.

Một label có vẻ ít giá trị trong môi trường dev vẫn có thể tăng mạnh trong production. Hãy đánh giá **tập giá trị tối đa và tốc độ tăng trưởng**, không chỉ nhìn vào vài dòng dữ liệu thử.

## 3. Dashboard có thể làm vấn đề nặng hơn ra sao?

Cần phân biệt hai vấn đề:

1. **Cardinality ở nguồn metric:** instrumentation tạo nhiều series vì label có quá nhiều giá trị. Đây là nguyên nhân gốc làm tăng chi phí ingest và lưu trữ.
2. **Chi phí truy vấn/dashboard:** panel, biến và bộ lọc truy vấn quá nhiều series hoặc trả về quá nhiều kết quả. Dashboard có thể làm Prometheus/backend chậm hơn, dù bản thân dashboard không tạo ra label mới.

Ví dụ biến Grafana liệt kê toàn bộ user ID:

~~~text
Variable: user_id
Query: label_values(module_events_published_total, user_id)
~~~

Nếu metric có hàng trăm nghìn user ID, dropdown phải lấy và xử lý tập giá trị rất lớn. Panel dùng biến này còn phải truy vấn theo một chiều dữ liệu có cardinality cao. Người vận hành khó chọn giá trị, dashboard tải chậm và backend phải thực hiện thêm nhiều truy vấn.

Một panel như sau cũng không phù hợp:

~~~promql
sum by (user_id) (
  rate(module_events_published_total[5m])
)
~~~

Truy vấn yêu cầu backend tổng hợp và trả về chuỗi theo từng user. topk(10, ...) có thể giới hạn số dòng hiển thị nhưng **không xóa các series đã được ingest**, không giảm chi phí lưu trữ và không biến label thành low-cardinality.

### 3.1. Những mẫu dashboard nên tránh

- Biến dropdown liệt kê mọi user_id, order_id, request_id hoặc trace_id.
- Panel có một dòng cho mỗi khách hàng/giao dịch khi mục tiêu là theo dõi sức khỏe hệ thống.
- group by trên ID duy nhất của request, order hoặc session.
- Bộ lọc regex rộng khớp tất cả giá trị của một label high-cardinality.
- Bảng hiển thị toàn bộ series thô trong một khoảng thời gian dài.
- Nhiều panel cùng truy vấn một metric high-cardinality với các tổ hợp label khác nhau.
- Dùng exception message hoặc URL thô làm legend.
- Dùng label user_id làm biến dashboard mặc định rồi để lựa chọn All khớp toàn bộ người dùng.

Dashboard không nên trở thành công cụ truy vấn dữ liệu nghiệp vụ theo từng bản ghi. Nếu cần xem một đơn hàng hoặc một request, dùng trace/log search hoặc màn hình nghiệp vụ có phân quyền.

## 4. Thiết kế dashboard theo câu hỏi vận hành

Trước khi tạo panel, viết ra câu hỏi mà panel cần trả lời. Sau đó chọn metric và label có tập giá trị giới hạn.

| Câu hỏi | Metric/nguồn dữ liệu | Dimension nên dùng |
| --- | --- | --- |
| Module nào phát event nhiều nhất? | Spring Modulith event publication counter | module, event type |
| Kênh nào có lượng event tăng bất thường? | Counter có custom channel tag | channel, module |
| Module nào có nhiều lỗi xử lý? | Consumer outcome/error metric được instrument | module, outcome, event type |
| Request HTTP đang chậm ở route nào? | HTTP server request timer | service, method, route template, status |
| Module nào có thời lượng xử lý cao? | Module observation timer nếu registry xuất meter tương ứng | module, invocation type |
| Một request cụ thể đi qua những module nào? | Trace backend | trace ID trong công cụ tracing |
| Exception nào xảy ra trong một request? | Logs liên kết trace/span | trace ID, span ID trong log search |

### 4.1. Bố cục dashboard gợi ý

Một dashboard tổng quan cho Spring Modulith có thể chia thành các hàng:

| Hàng | Panel | Mục đích |
| --- | --- | --- |
| Tổng quan | Request rate, error rate, latency p95 | Nhận biết sức khỏe dịch vụ |
| Module | Event publication rate theo module | So sánh hoạt động giữa module |
| Event | Event type phổ biến theo module | Nhận biết luồng event bất thường |
| Processing | Listener success/failure và duration | Theo dõi kết quả xử lý nếu ứng dụng đã instrument metric consumer |
| Tracing | Link từ exemplar hoặc panel sang trace | Điều tra một mẫu cụ thể |
| Kiến trúc | Link tới module graph hoặc /actuator/modulith | Đối chiếu dependency cấu trúc |

Các panel tổng quan nên ưu tiên số liệu theo module, event type, route template, outcome và environment. Một dashboard dành cho on-call cần trả lời nhanh “hệ thống nào/module nào đang bất thường?” trước khi mở công cụ tìm kiếm log/trace chi tiết.

## 5. Dùng Spring Modulith event metrics mà không tạo tag động

Spring Modulith cung cấp metrics cho domain event publication. Các meter có thể gồm counter tổng hợp module.events.published và counter riêng cho module/event type. Các tag mặc định mô tả module và event type, là những chiều có thể kiểm soát theo mô hình ứng dụng.

Nếu cần bổ sung chiều nghiệp vụ, hãy dùng tập giá trị nhỏ đã được định nghĩa, ví dụ channel=web|mobile|store hoặc outcome=success|failure. Không thêm user ID, order ID hay trace ID vào counter.

Ví dụ customizer an toàn cho event type OrderPlaced:

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration(proxyBeanMethods = false)
class EventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer orderChannelCustomizer() {
        return metrics -> metrics.customize(OrderPlaced.class,
            (event, counter) -> counter.tag(
                "channel",
                event.channel().name().toLowerCase(Locale.ROOT)
            ));
    }
}
~~~

Ví dụ giả định OrderPlaced có trường channel là enum với tập giá trị cố định. Cần kiểm tra null hoặc chuẩn hóa dữ liệu trước khi phát event. Customizer tác động đến counter riêng của event theo API Spring Modulith; không mặc định rằng tag mới sẽ xuất hiện trên mọi counter tổng hợp.

Ví dụ dashboard nên nhóm theo module và event type:

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
)
~~~

Tên metric và label trong Prometheus có thể được chuẩn hóa từ Micrometer name/tag. Hãy kiểm tra /actuator/prometheus để xác nhận tên thật trong ứng dụng trước khi đưa query vào dashboard. Nếu phiên bản hoặc registry dùng tên khác, thay bằng tên/label đã quan sát được.

### 5.1. Đo lường listener là một câu hỏi riêng

Counter publication cho biết event đã được công bố; nó không khẳng định mọi listener đã xử lý thành công. Nếu dashboard cần success/failure của consumer, hãy instrument riêng ở điểm xử lý listener bằng counter/timer với tag giới hạn, ví dụ:

- module_identifier
- event_type
- outcome
- listener_group nếu tập nhóm được khai báo cố định

Không gắn event_id, user_id, order_id hoặc exception message vào tag consumer metric. Dùng logs/traces để xem chi tiết một lần xử lý.

## 6. Viết PromQL có giới hạn đầu ra

Ví dụ các query tổng hợp cho dashboard:

### 6.1. Tốc độ event publication theo module

~~~promql
sum by (module_identifier) (
  rate(module_events_published_total[5m])
)
~~~

Panel này có một chuỗi cho mỗi module thay vì một chuỗi cho mỗi event/user. Nếu muốn so sánh event type, có thể thêm module_event_type khi đó là tập event đã biết và có giới hạn.

### 6.2. Số event trong một giờ theo module

~~~promql
sum by (module_identifier) (
  increase(module_events_published_total[1h])
)
~~~

increase ước lượng mức tăng counter trong cửa sổ thời gian. Dùng để hiển thị số event theo giờ; không cộng thêm counter tổng và counter per-event nếu chúng đại diện cùng một publication, tránh đếm trùng.

### 6.3. Tỷ lệ lỗi HTTP theo route template

~~~promql
sum by (uri) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
/
sum by (uri) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Đây là ví dụ theo tên metric Prometheus thường gặp của Spring Boot; label route ở metric HTTP mặc định thường có tên uri. Giá trị uri phải là route template có giới hạn, không phải URL chứa path ID. Nếu ứng dụng đã chuẩn hóa route thành label http_route riêng, thay uri bằng key đó. Cần xử lý trường hợp mẫu số bằng 0 khi triển khai panel thực tế.

### 6.4. p95 HTTP latency theo route

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Query này yêu cầu histogram bucket và uri label tương ứng đã được xuất. Nó cho p95 theo route template; không group theo request_id hoặc user_id.

### 6.5. Giới hạn kết quả khi cần top module

~~~promql
topk(
  10,
  sum by (module_identifier) (
    rate(module_events_published_total[5m])
  )
)
~~~

topk hữu ích để giới hạn số module hiển thị khi có nhiều module. Tuy nhiên, đây chỉ là giới hạn kết quả panel; nó **không phải biện pháp xử lý cardinality ở nguồn**. Nếu metric đã có hàng triệu series do user ID, topk không làm mất chi phí ingest và lưu trữ đó.

## 7. Thiết kế Grafana variables an toàn

Dashboard thường dùng variables để lọc theo môi trường, service hoặc module. Hãy chọn các chiều có tập giá trị nhỏ và ổn định.

| Variable | Query gợi ý | Có nên dùng? |
| --- | --- | --- |
| environment | label_values(up, environment) | Có, nếu environment là tập cấu hình cố định |
| service | label_values(up, job) hoặc label service đã chuẩn hóa | Có, nếu số service có kiểm soát |
| module | label_values(module_events_published_total, module_identifier) | Có, nếu chỉ gồm module đã khai báo |
| event_type | label_values(module_events_published_total, module_event_type) | Có, nếu tập event type hữu hạn |
| channel | label_values(module_events_published_total, channel) | Có, nếu là enum/allowlist |
| user_id | label_values(metric, user_id) | Không |
| request_id | label_values(metric, request_id) | Không |
| trace_id | label_values(metric, trace_id) | Không |

Trong Grafana, tạo query variable cho module có thể dùng truy vấn dạng:

~~~text
label_values(module_events_published_total, module_identifier)
~~~

Cú pháp cụ thể phụ thuộc phiên bản Grafana và chế độ query variable. Xác nhận label có tồn tại trên metric thực tế trước khi lưu dashboard.

### 7.1. Cẩn thận với lựa chọn All và regex

Nếu variable cho phép All, Grafana có thể thay thế bằng regex rộng như .* . Với label có cardinality cao, lựa chọn này có thể khiến panel truy vấn toàn bộ series. Ngay cả với label ít giá trị, nhiều biến multi-select kết hợp có thể tạo truy vấn lớn.

Một số nguyên tắc:

- Chỉ bật multi-value khi người dùng thực sự cần so sánh nhiều module/event.
- Dùng custom All value phù hợp với truy vấn, không mặc định mở rộng sang các chiều không cần thiết.
- Đặt time range hợp lý; panel không cần dữ liệu thô của nhiều tháng để hiển thị xu hướng 5 phút gần nhất.
- Dùng refresh interval phù hợp với tần suất cập nhật metric; không refresh quá nhanh chỉ để dashboard trông realtime.
- Tránh tạo biến phụ thuộc vào biến high-cardinality khác.
- Không dùng ad hoc filter trên user_id, request_id, order_id trong dashboard metrics chung.

### 7.2. Dashboard không phải công cụ tìm mọi ID

Nếu người vận hành cần tìm một request cụ thể, nên dùng:

- Trace UI để tìm theo trace ID hoặc điều kiện span.
- Log search để lọc theo trace ID/span ID và nội dung exception.
- Màn hình/API nghiệp vụ có phân quyền để tra cứu order/user.
- Link từ metric exemplar sang trace nếu metrics pipeline và backend hỗ trợ.

Không tạo metric variable cho hàng triệu ID chỉ để cung cấp một ô tìm kiếm. Công cụ log/trace được thiết kế cho truy vấn chi tiết đó.

## 8. Kết nối dashboard metrics với trace bằng exemplars

**Exemplar** là một mẫu tham chiếu gắn với một quan sát metric, thường chứa trace ID để người vận hành chuyển từ biểu đồ tổng hợp sang trace cụ thể. Exemplar không phải label thông thường và không tạo một time series cho mỗi trace ID theo cách gắn trace ID vào metric tag.

Một luồng điều tra có thể là:

~~~mermaid
flowchart LR
    A["Dashboard: p95 latency tăng"] --> B["Chọn điểm dữ liệu / exemplar"]
    B --> C["Mở trace có traceId"]
    C --> D["Xem module entry spans"]
    D --> E["Tìm log theo traceId/spanId"]
    E --> F["Đối chiếu trạng thái nghiệp vụ"]
~~~

Điều kiện để dùng exemplar:

- Registry/exporter và backend metrics hỗ trợ exemplar.
- Tracing được cấu hình để tạo trace ID tương ứng.
- Dashboard data source có cấu hình trace datasource và exemplar link.
- Trace còn tồn tại trong backend; sampling/retention có thể khiến exemplar trỏ tới trace không còn truy vấn được.

Không phải mọi metric hoặc mọi điểm histogram đều có exemplar. Cần kiểm tra cấu hình cụ thể của Micrometer registry, Prometheus và Grafana đang dùng.

## 9. Nhận diện cardinality cao trong hệ thống

### 9.1. Kiểm tra ở ứng dụng

Nếu dùng Spring Boot Actuator, có thể kiểm tra danh sách meter và tag values:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/module.events.published
~~~

Endpoint metrics có thể hiển thị các tag keys và những giá trị có sẵn cho meter. Đây là điểm bắt đầu để xác định tag nào đang có tập giá trị lớn. Kết quả phụ thuộc registry, meter đã được tạo và cấu hình endpoint.

Nếu dùng Prometheus registry, kiểm tra output:

~~~bash
curl -s http://localhost:8080/actuator/prometheus
~~~

Chỉ expose endpoint cần thiết và giới hạn quyền truy cập/mạng quản trị trong production.

### 9.2. Kiểm tra số series ở Prometheus

Prometheus có metric nội bộ prometheus_tsdb_head_series cho số series hiện có trong head block. Có thể theo dõi xu hướng tổng series và so sánh với số lần deploy hoặc thay đổi instrumentation.

Để đếm series của một nhóm metric, ví dụ:

~~~promql
count({__name__=~"module_events_published.*"})
~~~

Để xem số series theo module nếu label tồn tại:

~~~promql
count by (module_identifier) (
  {__name__=~"module_events_published.*"}
)
~~~

Các query chẩn đoán cần được chạy có giới hạn và không nên đặt làm panel refresh liên tục nếu chính truy vấn đó tốn tài nguyên. Nếu nghi ngờ label high-cardinality cụ thể, kiểm tra metric/label trong Prometheus TSDB status hoặc công cụ cardinality analysis của nền tảng. Không tạo dashboard lâu dài group-by theo label xấu chỉ để giám sát nó.

### 9.3. Dấu hiệu bất thường

- Số series tăng mạnh sau khi thêm customizer hoặc instrumentation mới.
- prometheus_tsdb_head_series tăng đều dù số module/event type không đổi.
- Dashboard variable mất nhiều thời gian tải giá trị.
- Panel có quá nhiều legend hoặc bảng hàng nghìn dòng.
- Query timeout hoặc backend trả về quá nhiều samples.
- Bộ nhớ ứng dụng tăng do registry giữ nhiều meter ID.
- Ingest, retention hoặc chi phí lưu trữ tăng mà traffic không tăng tương ứng.

## 10. Guardrail tại Micrometer

Thiết kế dashboard tốt cần bắt đầu từ instrumentation. Không thêm tag high-cardinality rồi hy vọng dashboard sẽ lọc nó đi.

### 10.1. Loại bỏ tag không phù hợp

Micrometer có MeterFilter.ignoreTags(...) để bỏ tag theo key trước khi meter được đăng ký:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricTagGuardConfiguration {

    @Bean
    MeterFilter ignoreIdentityTags() {
        return MeterFilter.ignoreTags("userId", "requestId", "traceId");
    }
}
~~~

Đây là lớp bảo vệ bổ sung. Cần sửa nguồn instrumentation/customizer trước, vì filter toàn cục có thể ảnh hưởng meter khác và tên key phải khớp chính xác với tag thực tế (ví dụ user_id).

### 10.2. Giới hạn tập giá trị của một tag

Với tag có cardinality dự kiến nhỏ, có thể dùng MeterFilter.maximumAllowableTags(...):

~~~java
@Bean
MeterFilter limitChannelValues() {
    return MeterFilter.maximumAllowableTags(
        "module.events.published.",
        "channel",
        4,
        MeterFilter.deny()
    );
}
~~~

Ví dụ giới hạn tối đa bốn giá trị channel trên các meter có prefix tương ứng. Khi vượt giới hạn, meter mới có tag value ngoài ngưỡng có thể bị từ chối theo filter. Dữ liệu bị từ chối sẽ không được đo; vì vậy phải có log/cảnh báo và chọn ngưỡng phù hợp với allowlist nghiệp vụ.

Filter không thay thế việc thiết kế tag đúng. Đừng dùng giới hạn cao tùy tiện để hợp thức hóa tag user_id.

## 11. Quy tắc đặt tên và thiết kế panel

| Thành phần | Nên làm | Tránh |
| --- | --- | --- |
| Metric name | Tên ổn định theo ý nghĩa đo | Nhúng user/order/request ID vào tên |
| Label/tag | Module, event type, outcome, channel | ID duy nhất, URL thô, message động |
| Legend | Hiển thị module hoặc route template | Hiển thị mọi user ID |
| Variable | Environment, service, module, event type | User ID, trace ID, session ID |
| Panel | Tổng hợp theo chiều nghiệp vụ có giới hạn | Một hàng/series cho mỗi giao dịch |
| Time range | Phù hợp với mục đích dashboard | Quét dữ liệu dài hạn không cần thiết |
| Drill-down | Link exemplar, trace hoặc log search | Thêm mọi định danh vào metric label |
| Alert | Ngưỡng trên rate, ratio, latency hoặc error | Alert riêng cho từng user/order |

Dashboard on-call nên ít panel nhưng rõ mục tiêu. Một panel tốt có tiêu đề cho biết metric, đơn vị, nhóm chiều đo và khoảng thời gian. Legend nên giúp so sánh các module; không nên buộc người xem xử lý hàng nghìn chuỗi.

## 12. Quy trình refactor dashboard đang dùng tag cardinality cao

Nếu phát hiện dashboard có biến user_id hoặc panel group-by request_id, xử lý theo thứ tự:

1. **Tìm nguồn tag:** xác định metric nào chứa label đó và customizer/instrumentation nào tạo ra nó.
2. **Đo tác động:** kiểm tra số series, memory, scrape samples, query latency và thời điểm bắt đầu tăng.
3. **Sửa instrumentation:** bỏ ID động khỏi metric tag/name; thay bằng enum hoặc nhóm nghiệp vụ có giới hạn nếu có câu hỏi tổng hợp phù hợp.
4. **Sửa query:** aggregate theo module, event type, outcome hoặc channel.
5. **Sửa dashboard variables:** xóa biến liệt kê ID động; chỉ giữ biến có tập giá trị nhỏ.
6. **Chuyển nhu cầu drill-down:** dùng trace/log search hoặc màn hình nghiệp vụ có phân quyền.
7. **Xác minh dữ liệu mới:** kiểm tra /actuator/metrics, /actuator/prometheus, số series và panel sau deploy.
8. **Xử lý dữ liệu lịch sử:** retention và xóa series cũ phụ thuộc backend; bỏ label trong code không tự xóa dữ liệu đã lưu.
9. **Bổ sung review:** yêu cầu khai báo cardinality dự kiến cho metric tag mới và review dashboard query/variables.

## 13. Ví dụ một dashboard tổng quan cho Spring Modulith

Một thiết kế có thể dùng các variables giới hạn:

~~~text
environment: dev | staging | prod
service: shop-backend | payment-worker
module: orders | payments | inventory | notifications
event_type: OrderPlaced | PaymentAuthorized | StockReserved
channel: web | mobile | store
~~~

Các panel:

| Panel | Query/nguồn | Legend |
| --- | --- | --- |
| Event publication rate | rate của counter publication | module |
| Event type distribution | sum by (module_identifier, module_event_type) | module + event type |
| HTTP error ratio | HTTP request metrics | route template |
| HTTP p95 latency | HTTP timer histogram | route template |
| Listener outcomes | Consumer metrics nếu đã instrument | module + outcome |
| Module invocation duration | Observation timer nếu registry xuất meter tương ứng | module |
| Trace drill-down | Exemplar/trace datasource | trace mở trong backend |

Bảng trên là mẫu thiết kế. Tên metric/label chính xác phải xác minh từ registry và phiên bản Spring Boot/Spring Modulith. Không giả định mọi dự án đều tự có consumer outcome metric hoặc module duration histogram; nếu cần, hãy instrument riêng bằng tag giới hạn.

Module graph có thể được mở ở /actuator/modulith khi endpoint và integration tương ứng được cấu hình. Dashboard có thể đặt link tới endpoint hoặc tài liệu module graph để người vận hành đối chiếu cấu trúc với các module đang xuất hiện trong metrics/traces.

## 14. Checklist trước khi publish dashboard

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| Panel đang trả lời câu hỏi vận hành nào? | Mỗi panel có mục tiêu rõ ràng |
| Các label có tập giá trị giới hạn? | Có enum, allowlist hoặc giới hạn kiến trúc |
| Có ID duy nhất trong metric tag/name? | Không có user/order/request/trace/session ID |
| URL có được chuẩn hóa? | Dùng route template thay path động |
| Variables có liệt kê quá nhiều giá trị? | Chỉ dùng environment/service/module/event/channel |
| Multi-select và All có mở rộng query quá mức? | Có giới hạn và time range phù hợp |
| Query có group-by trên high-cardinality label? | Không |
| topk có bị hiểu nhầm là giải pháp cardinality? | Đã phân biệt giới hạn hiển thị với số series nguồn |
| Có link drill-down? | Dùng trace/log/exemplar cho trường hợp cụ thể |
| Có kiểm tra số series và query latency? | Đã xem xu hướng trước/sau thay đổi |
| Có kiểm soát dữ liệu nhạy cảm? | Không lộ PII/token qua labels, logs hoặc dashboard |
| Có kiểm tra endpoint? | Actuator/Prometheus chỉ mở cho người và mạng được phép |

## 15. Ghi nhớ

**Dashboard tốt dùng các chiều đo có cardinality thấp để tổng hợp sức khỏe hệ thống.** Trong Spring Modulith, module identifier, event type, outcome và channel là những chiều hữu ích khi tập giá trị được kiểm soát. User ID, order ID, request ID, trace ID, session ID và chuỗi động không nên trở thành metric tags hoặc dashboard variables.

Dashboard có thể làm truy vấn nặng hơn nếu liệt kê quá nhiều giá trị hoặc group-by trên label high-cardinality, nhưng nguyên nhân gốc thường nằm ở instrumentation tạo quá nhiều series. topk chỉ giới hạn số kết quả hiển thị; nó không xóa series đã được ingest. Hãy sửa nguồn metric, giới hạn variables và tổng hợp theo module/event type.

Khi cần điều tra một request hoặc user cụ thể, chuyển từ dashboard sang trace/log search hoặc dữ liệu nghiệp vụ có phân quyền. Kết hợp event metrics, module spans, exemplars và module graph sẽ giúp vừa theo dõi được xu hướng toàn hệ thống, vừa đi sâu vào một hành trình cụ thể mà không làm metric backend phải lưu một series cho từng định danh.

## Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): event publication metrics, module observations và metadata module.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer registry, Actuator metrics và export.
- [Micrometer — Meter Concepts](https://docs.micrometer.io/micrometer/reference/concepts/meters.html): meter ID, tags và cardinality.
- [Micrometer — Meter Filters](https://docs.micrometer.io/micrometer/reference/concepts/meter-filters.html): ignoreTags và maximumAllowableTags.
- [Prometheus — Data Model](https://prometheus.io/docs/concepts/data_model/): time series được xác định bằng metric name và label set.
- [Prometheus — Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/): selector, aggregation và PromQL.
- [Grafana — Prometheus template variables](https://grafana.com/docs/grafana/latest/datasources/prometheus/template-variables/): query variables và label values.
- [Grafana — Prometheus exemplars](https://grafana.com/docs/grafana/latest/fundamentals/exemplars/): liên kết metric sample với trace.

> **Giới hạn:** Tên metric và label trong ví dụ PromQL là tên minh họa theo dạng Prometheus phổ biến; phải xác minh output thực tế của /actuator/prometheus trước khi dùng. Khả năng exemplar, variable query và endpoint Actuator phụ thuộc registry, backend và phiên bản. Bài thuộc STEP 4; đánh giá chuyên môn và refactor nội dung sẽ được thực hiện ở bước QA tiếp theo.
