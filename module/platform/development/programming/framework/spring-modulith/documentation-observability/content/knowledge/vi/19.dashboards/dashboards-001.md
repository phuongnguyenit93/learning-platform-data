# Dashboard tổng quan tương tác module

## 1. Từ dữ liệu quan sát đến bức tranh vận hành của module

Trong ứng dụng Spring Boot dùng Spring Modulith, các application module có thể phối hợp bằng lời gọi API hoặc domain event. Ví dụ, module ordering quản lý đơn hàng, payment xử lý thanh toán, inventory giữ thông tin tồn kho và notification gửi thông báo. Khi hệ thống chạy, một yêu cầu đặt hàng có thể đi qua nhiều module và phát domain event để các listener tiếp tục xử lý.

Mỗi công cụ quan sát chỉ cho thấy một phần của bức tranh:

- **Module graph** cho biết các module được nhận diện và quan hệ phụ thuộc theo cấu trúc mã nguồn.
- **Event metrics** cho biết domain event được công bố bao nhiêu lần, theo module và loại event.
- **Module-entry spans** cho thấy những lần thực thi đi qua API module được instrument và thời gian của chúng.
- **Application metrics** cho biết lưu lượng request, tỷ lệ lỗi và latency của ứng dụng.
- **Logs** bổ sung thông tin chi tiết theo trace ID, span ID và correlation ID.

Dashboard tổng quan cần ghép các tín hiệu này để trả lời câu hỏi vận hành: module nào đang được gọi nhiều, module nào chậm hoặc lỗi, event nào tăng bất thường, luồng nào bị đứt và cần mở trace nào để điều tra.

Bài học thuộc chương **Dashboard** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module này hướng dẫn dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác trong ứng dụng Spring Boot, bao gồm module graph, Actuator, event metrics, tracing và context propagation.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Thiết kế dashboard tổng quan có cả góc nhìn cấu trúc và runtime.
2. Phân biệt module dependency graph với các tương tác thực sự đã xảy ra.
3. Chọn panel phù hợp cho request rate, error rate, latency và event publication.
4. Kết nối metrics với module-entry spans và logs để điều tra theo trace.
5. Thiết kế biến lọc theo environment, service, module và event type.
6. Nhận biết dữ liệu nào Spring Modulith cung cấp sẵn và dữ liệu nào ứng dụng phải instrument thêm.
7. Viết truy vấn PromQL có aggregation đúng và tránh cardinality cao.
8. Đặt alert theo triệu chứng vận hành và liên kết alert tới dashboard/trace.

## 2. Dashboard không phải là module graph

Trước khi thiết kế panel, cần phân biệt ba loại thông tin:

| Nguồn | Câu hỏi trả lời | Bản chất |
| --- | --- | --- |
| Module graph và tài liệu Spring Modulith | Module nào phụ thuộc module nào? | Cấu trúc tĩnh được nhận diện từ ứng dụng. |
| Module-entry spans/traces | Request cụ thể đã đi qua module nào? | Lịch sử thực thi của một trace được instrument và thu thập. |
| Event metrics | Module nào đã công bố loại event nào, với tốc độ bao nhiêu? | Số lượng publication được instrument. |

Ví dụ, module graph có cạnh `ordering → payment` không có nghĩa mọi request đặt hàng đều gọi payment. Một nhánh xử lý có thể bỏ qua thanh toán, hoặc trace bị sampling loại. Ngược lại, trace có span của `payment` cho biết một lần thực thi đã đi qua điểm vào được instrument của module đó.

**Dashboard nên hiển thị cả hai góc nhìn:** graph để hiểu kiến trúc dự kiến và telemetry để hiểu hành vi thực tế. Không dùng một biểu đồ runtime thay cho kiểm thử kiến trúc.

### 2.1. Module graph từ Spring Modulith

Spring Modulith Actuator cung cấp endpoint `/actuator/modulith` khi observability/Actuator integration phù hợp được thêm vào. Endpoint này cung cấp thông tin application module để người vận hành hoặc công cụ tích hợp xem cấu trúc được nhận diện.

Có thể truy cập trong môi trường local:

~~~bash
curl -s http://localhost:8080/actuator/modulith
~~~

Để tài liệu hóa graph, Spring Modulith còn có cơ chế documenter sinh sơ đồ module và thông tin liên quan. Dashboard có thể đặt link tới tài liệu đã sinh hoặc hiển thị snapshot/ảnh graph theo quy trình release. Không nên giả định endpoint graph cung cấp trực tiếp mọi số liệu runtime hay một ma trận call count.

### 2.2. Runtime module-entry spans

Khi bật observability của Spring Modulith, framework có thể tạo observation/span ở điểm vào Spring component thuộc API module được instrument. Những span này giúp nhìn thấy:

- Module nào được gọi.
- Phương thức nào được thực thi tại điểm vào.
- Kiểu invocation, chẳng hạn bean hoặc event listener.
- Thời gian của vùng thực thi và lỗi nếu được ghi nhận.

Tên và tag cụ thể cần đối chiếu phiên bản Spring Modulith đang dùng. Các thuộc tính phổ biến được công bố gồm `module.identifier`, `module.name`, `module.method` và `module.invocation-type`. Dashboard tracing có thể dùng chúng để lọc và nhóm span.

Không phải mọi method Java đều tự động trở thành module-entry span. Helper private, self-invocation hoặc code không đi qua Spring-managed boundary có thể không được instrument.

## 3. Kiến trúc dữ liệu cho dashboard

Một dashboard tổng quan thường cần nhiều nguồn dữ liệu phối hợp:

~~~mermaid
flowchart TB
    APP["Spring Boot + Spring Modulith"]
    MOD["Module graph / Actuator"]
    OBS["ObservationRegistry"]
    MET["Micrometer metrics"]
    TR["Micrometer Tracing"]
    LOG["Application logs"]
    PROM["Prometheus"]
    TEMPO["Tempo / Jaeger / tracing backend"]
    LOKI["Loki / log backend"]
    G["Grafana dashboard"]
    APP --> MOD
    APP --> OBS
    OBS --> MET
    OBS --> TR
    APP --> LOG
    MET --> PROM
    TR --> TEMPO
    LOG --> LOKI
    MOD --> G
    PROM --> G
    TEMPO --> G
    LOKI --> G
~~~

| Thành phần | Dữ liệu cung cấp | Cách dùng trên dashboard |
| --- | --- | --- |
| Spring Modulith Actuator | Cấu trúc module được nhận diện. | Link hoặc panel kiến trúc tĩnh, kiểm tra module hiện có. |
| Micrometer + Prometheus | Counter, timer, gauge và histogram. | Panel lưu lượng, event rate, error rate, latency. |
| Micrometer Tracing + backend | Trace và spans. | Bảng module invocation, waterfall, truy vết lỗi/chậm. |
| Logging backend | Log records có timestamp, trace/span ID. | Mở log liên quan từ trace hoặc từ alert. |
| Grafana | Lớp trình bày và liên kết datasource. | Dashboard, variables, annotations và alert rules. |

**Không bắt buộc dùng đúng bộ sản phẩm trong sơ đồ.** Có thể thay Prometheus, Tempo hoặc Loki bằng hệ thống tương thích. Điều quan trọng là telemetry phải có schema nhất quán và các datasource có thể liên kết theo service, environment và trace ID.

### 3.1. Một ví dụ dependency cho ứng dụng

Với dự án Spring Boot/Spring Modulith có BOM tương thích, cấu hình minh họa:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")

    // Nếu cần trace export qua OpenTelemetry/OTLP:
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")
}
~~~

Insight Starter cung cấp tích hợp Actuator và observability của Spring Modulith. Prometheus registry phục vụ export metrics; tracing bridge và exporter phục vụ đường xuất trace. Các phiên bản Spring Boot mới có thể cung cấp starter hoặc cách auto-configuration khác, vì vậy cần dùng dependency management đúng dòng phiên bản.

### 3.2. Expose Actuator endpoints

Ví dụ trong môi trường development:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus,modulith"
~~~

Endpoint có thể không tồn tại nếu thiếu dependency tương ứng hoặc chưa bật integration. Cổng management và base path cũng có thể khác. Production cần bảo vệ endpoint quản trị bằng authentication/authorization và network policy; không expose công khai chỉ để dashboard truy cập thuận tiện.

## 4. Thiết kế bố cục dashboard tổng quan

Không nên nhồi mọi dữ liệu vào một màn hình. Một dashboard tổng quan có thể chia thành các hàng theo thứ tự từ tổng quan đến chẩn đoán:

~~~mermaid
flowchart TB
    A["Row 1 — Service health / RED"]
    B["Row 2 — Module topology"]
    C["Row 3 — Runtime module interactions"]
    D["Row 4 — Domain event flow"]
    E["Row 5 — Latency / failures"]
    F["Row 6 — Trace and log drill-down"]
    A --> B --> C --> D --> E --> F
~~~

| Hàng | Panel đề xuất | Câu hỏi chính |
| --- | --- | --- |
| 1. Tổng quan | Request rate, error rate, p95 latency, service status. | Ứng dụng có đang khỏe không? |
| 2. Topology | Module graph và module list. | Những ranh giới nào tồn tại trong ứng dụng? |
| 3. Runtime | Module invocation rate, duration, lỗi; module-to-module flow nếu có dữ liệu. | Request thực tế đang đi qua module nào? |
| 4. Event flow | Published event rate theo module/type. | Event nào đang được phát nhiều hoặc biến động? |
| 5. Điều tra | Latency theo module, event processing age, failures. | Chậm hoặc lỗi bắt đầu ở đâu? |
| 6. Drill-down | Trace list, span waterfall, logs theo trace ID. | Một lần xử lý cụ thể đã xảy ra thế nào? |

Dashboard cần hiển thị khoảng thời gian đang chọn và timezone hiển thị rõ. Thông thường lưu timestamp telemetry theo UTC; Grafana có thể hiển thị theo UTC hoặc timezone người xem. Không trộn các chuỗi timestamp local thiếu offset.

## 5. Row 1 — Sức khỏe tổng thể của service

Đây là hàng đầu tiên người trực nhìn thấy. Nên dùng bốn panel chính:

1. Request rate (requests/second).
2. Error rate (tỷ lệ request lỗi).
3. Latency p95/p99.
4. Service/instance availability hoặc trạng thái health.

### 5.1. Request rate

Spring Boot/Micrometer thường cung cấp timer cho HTTP server requests. Với Prometheus exporter, tên thường được chuẩn hóa thành dạng `http_server_requests_seconds_count`; cần xác nhận tên thực tại `/actuator/prometheus`.

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    application="shop-service"
  }[5m])
)
~~~

Query này là ví dụ; label `application` chỉ tồn tại nếu hệ thống đã gắn label đó. Nếu dùng `service`, `service_name` hoặc resource attribute khác, hãy sửa selector theo dữ liệu thực.

### 5.2. Error rate

Ví dụ đếm các HTTP 5xx:

~~~promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
~~~

Nếu mẫu số bằng 0 hoặc không có series, dashboard cần xử lý trạng thái no data/zero traffic rõ ràng. Không tự diễn giải absent series thành tỷ lệ lỗi 0% nếu chưa xác minh semantics của metric.

HTTP 4xx có thể là lỗi client được dự kiến. Nên tách 4xx và 5xx nếu SLO chỉ quan tâm lỗi server. Với nghiệp vụ thanh toán hoặc event listener, cần metric outcome riêng; HTTP status không bao quát mọi lỗi nghiệp vụ.

### 5.3. Latency p95

Nếu HTTP server request histogram đã được bật và metric bucket tồn tại:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Đây là p95 tổng hợp từ classic histogram. Nếu không có bucket, query không thể tạo p95 từ count/sum đơn thuần. Cần cấu hình histogram phù hợp trong Micrometer/registry và kiểm tra tên metric thực tế.

### 5.4. Service health

Panel health có thể lấy từ Actuator health endpoint hoặc metric health phù hợp với nền tảng. Không nên polling endpoint quản trị quá dày. Nếu dùng health status trong dashboard, xác định rõ trạng thái nào là UP, DEGRADED hoặc DOWN và cách alert khi datasource không truy cập được.

## 6. Row 2 — Topology và module graph

Module graph trả lời “module nào phụ thuộc module nào?” và giúp người vận hành định hướng khi đọc trace.

Ví dụ kiến trúc:

~~~mermaid
flowchart LR
    O["ordering"]
    P["payment"]
    I["inventory"]
    N["notification"]
    R["reporting"]
    O --> P
    O --> I
    O --> N
    P --> R
    I --> R
~~~

Đây là graph minh họa, không phải kết quả được đọc từ dự án. Trong ứng dụng thật, dùng dữ liệu Spring Modulith đã nhận diện và tài liệu graph do Documenter sinh.

### 6.1. Cách đưa graph vào dashboard

Có một số cách:

- Đặt link từ Grafana tới trang tài liệu module graph được publish nội bộ.
- Đính kèm hình graph theo từng release và hiển thị release/version tương ứng.
- Tạo panel hiển thị danh sách module, identifier và trạng thái telemetry gần đây.
- Nếu có integration phù hợp, dựng panel topology từ dữ liệu module đã được cung cấp.

Không nên lấy ảnh graph cũ rồi coi nó là topology runtime hiện hành. Hãy hiển thị commit/version hoặc thời điểm sinh tài liệu để người đọc biết graph thuộc phiên bản nào.

### 6.2. Module graph không phải interaction map

Một cạnh `ordering → payment` trong graph thể hiện phụ thuộc cấu trúc, không cho biết:

- Có bao nhiêu lần gọi trong 5 phút.
- Lần gọi có thành công không.
- Latency trung bình hoặc p95 là bao nhiêu.
- Có request nào bỏ qua module payment hay không.

Những thông tin này cần metrics hoặc traces. Dashboard nên đặt graph cạnh panel runtime để người xem so sánh **thiết kế và thực thi**.

## 7. Row 3 — Runtime module interactions

Đây là hàng quan trọng nhất đối với mục tiêu quan sát tương tác giữa các module.

### 7.1. Bảng module invocation

Một bảng runtime hữu ích có thể gồm:

| Cột | Nguồn dữ liệu |
| --- | --- |
| Module identifier | Span attribute `module.identifier`. |
| Module name | Span attribute `module.name`. |
| Method | Span attribute `module.method` nếu backend nhận được. |
| Invocation type | Span attribute `module.invocation-type`. |
| Calls | Số span phù hợp trong khoảng thời gian. |
| Error count | Span có status ERROR hoặc metric lỗi riêng. |
| Duration | Thời gian span hoặc timer đã instrument. |
| Trace link | Link mở trace chi tiết trong backend. |

Các cột này có thể được dựng từ tracing backend có khả năng tìm kiếm/group span. Không giả định tất cả thuộc tính đều có trên mọi span hoặc mọi backend đều hỗ trợ truy vấn bảng giống nhau.

### 7.2. Module-to-module interaction matrix

Một ma trận tương tác có thể có dạng:

| Caller module | Target module | Calls | Error rate | p95 |
| --- | --- | ---: | ---: | ---: |
| ordering | payment | 1.240 | 1,2% | 180 ms |
| ordering | inventory | 1.240 | 0,1% | 42 ms |
| ordering | notification | 1.180 | 0,0% | 25 ms |

Các số chỉ là ví dụ. Để dựng ma trận này, hệ thống phải có đủ dữ liệu để nhận diện **module gọi** và **module đích** trên quan hệ parent-child giữa spans. Spring Modulith module-entry span có thể cho biết module đích, nhưng không nên giả định framework tự gắn sẵn tag `caller.module` cho mọi trường hợp.

Có thể suy ra caller/target từ trace span tree khi:

1. Span cha và span con đều được instrument.
2. Có thuộc tính module trên cả hai span hoặc có mapping đáng tin cậy từ span operation.
3. Backend hỗ trợ truy vấn quan hệ parent/child hoặc pipeline tạo derived telemetry.

Nếu không có đủ metadata, hãy bắt đầu bằng bảng số lần vào từng module; chỉ xây ma trận caller/target sau khi instrument nguồn dữ liệu cần thiết. Tránh suy ra cạnh từ tên method hoặc package bằng heuristic không được kiểm chứng.

### 7.3. Panel invocation rate theo module

Nếu ứng dụng có timer/counter riêng cho module invocation, có thể nhóm theo module. Ví dụ metric tùy biến giả định:

~~~promql
sum by (module_identifier) (
  rate(module_invocations_total[5m])
)
~~~

`module_invocations_total` là tên **metric do ứng dụng/telemetry pipeline tự cung cấp trong ví dụ**, không khẳng định đây là meter mặc định của Spring Modulith. Nếu chỉ có module-entry spans, dùng tracing backend để thống kê span count hoặc cân nhắc tạo metric low-cardinality phù hợp.

Không tạo metric label từ `traceId`, `spanId`, `orderId` hoặc ID duy nhất. Những giá trị đó phù hợp hơn cho trace/log drill-down.

### 7.4. Panel latency/error theo module

Nếu custom instrumentation tạo timer có tag `module_identifier`, có thể dùng histogram query tương ứng. Nếu chỉ có spans, hãy truy vấn duration và status trực tiếp trên tracing backend. Đừng giả định module-entry observations tự động xuất ra một histogram Prometheus với tên cố định.

## 8. Row 4 — Domain event flow

Spring Modulith cung cấp Micrometer event metrics để theo dõi domain event được công bố. Hai dạng meter quan trọng:

- `module.events.published`: counter tổng hợp, có các tag module và event type.
- `module.events.published.$moduleIdentifier.$simpleEventTypeName`: counter riêng theo module và event type, có thể được làm giàu tag qua `ModulithEventMetricsCustomizer`.

### 8.1. Event rate theo module và loại event

Ví dụ PromQL sau giả định Prometheus exporter chuẩn hóa tên meter và tag thành dạng underscore:

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
)
~~~

Tên metric/label có thể khác theo phiên bản, registry và naming convention. Hãy kiểm tra:

~~~bash
curl -s http://localhost:8080/actuator/metrics/module.events.published
curl -s http://localhost:8080/actuator/prometheus
~~~

Actuator `/metrics` cho biết meter và available tags; `/prometheus` cho biết tên và label thực tế được export. Viết query dựa trên dữ liệu đó thay vì sao chép nguyên tên minh họa.

### 8.2. Top event types

Sau khi xác minh tên metric và label, có thể dùng `topk` để tìm event type có tốc độ publication cao:

~~~promql
topk(
  10,
  sum by (module_identifier, module_event_type) (
    rate(module_events_published_total[5m])
  )
)
~~~

Panel này hữu ích để phát hiện thay đổi lưu lượng. Một event tăng không nhất thiết là lỗi; cần đối chiếu với baseline, lịch sử triển khai và traffic nghiệp vụ.

### 8.3. Event metrics không chứng minh listener thành công

`module.events.published` phản ánh publication được instrument. Nó không tự cho biết:

- Listener đã bắt đầu xử lý chưa.
- Listener hoàn tất hay ném exception.
- Message đã retry bao nhiêu lần.
- Notification đã gửi thành công hay chưa.

Nếu dashboard cần tỷ lệ xử lý thành công, phải có outcome metric riêng tại listener hoặc nguồn trạng thái đáng tin cậy từ Event Publication Registry/monitoring. Không dùng `published - processed` như số event thất lạc nếu chưa định nghĩa semantics, retry và thời điểm đo.

### 8.4. Tag nghiệp vụ trên per-event counter

Nếu cần phân tích `OrderPlaced` theo channel, có thể dùng `ModulithEventMetricsCustomizer` để thêm tag có miền giá trị nhỏ như `channel=web|mobile|pos` vào counter riêng của event. Ví dụ:

~~~java
@Bean
ModulithEventMetricsCustomizer eventMetricsCustomizer() {
    return metrics -> metrics.customize(
        OrderPlaced.class,
        (event, builder) -> builder.tags(
            "channel",
            event.channel().name().toLowerCase(Locale.ROOT)
        )
    );
}
~~~

Đoạn code giả định `OrderPlaced` có enum `channel()`. Hãy xác nhận tag xuất hiện trên **per-event counter** trước khi dựng panel. Không giả định nó tự xuất hiện trên counter tổng hợp `module.events.published`.

## 9. Row 5 — Latency và event processing delay

Một dashboard module cần nhìn được cả thời gian thực thi và thời gian chờ giữa các bước.

### 9.1. Module-entry span duration

Nếu tracing backend nhận module-entry spans, có thể lọc theo `module.identifier` rồi xem:

- Số span trong khoảng thời gian.
- Duration trung vị/p95/p99 theo module.
- Tỷ lệ span có status ERROR.
- Trace mẫu chậm nhất để mở waterfall.

Các truy vấn cụ thể phụ thuộc backend (Tempo, Jaeger hoặc hệ thống khác). Không có PromQL chung để query span nếu trace chưa được chuyển thành metric.

### 9.2. Event age / processing delay

Để đo độ trễ event, cần xác định timestamp semantics:

- `occurredAt`: thời điểm nghiệp vụ xảy ra.
- `publishedAt`: thời điểm publication được ghi nhận nếu có.
- `processingStartedAt`: thời điểm listener bắt đầu.
- `processedAt`: thời điểm listener hoàn tất.

Ví dụ metric custom có thể ghi histogram `module_event_processing_delay_seconds` từ `publishedAt` tới `processingStartedAt`, hoặc `module_event_processing_duration_seconds` cho thời gian listener chạy. Đây là metric do ứng dụng định nghĩa, không phải tên meter mặc định của Spring Modulith.

Nếu các node có clock skew, phép trừ timestamp giữa producer và consumer có thể sai. Đồng bộ đồng hồ, dùng UTC và phân biệt source timestamp/observed timestamp trước khi tin vào event age.

### 9.3. Event Publication Registry

Spring Modulith Event Publication Registry theo dõi publication tới transactional listeners và trạng thái hoàn tất theo cơ chế được cấu hình. Dashboard có thể bổ sung số publication chưa hoàn tất hoặc publication cần phục hồi nếu ứng dụng expose một metric/health indicator phù hợp.

Không giả định mọi phiên bản tự xuất một metric Prometheus có tên cố định cho pending publication. Nếu cần panel này, xác định API/registry state phù hợp và instrument rõ ràng. Tracing cho biết lần xử lý diễn ra thế nào; Publication Registry hỗ trợ theo dõi độ tin cậy của event.

## 10. Variables và filters trong Grafana

Variables giúp một dashboard phục vụ nhiều service, môi trường và module mà không cần tạo bản sao cho từng ứng dụng.

### 10.1. Variables đề xuất

| Variable | Mục đích | Ví dụ |
| --- | --- | --- |
| `$environment` | Chọn môi trường. | `dev`, `staging`, `prod`. |
| `$service` | Chọn service/ứng dụng. | `shop-service`. |
| `$module` | Chọn application module. | `ordering`, `payment`, `notification`. |
| `$eventType` | Lọc domain event. | `OrderPlaced`, `PaymentAuthorized`. |
| `$region` | Chọn vùng triển khai nếu có. | `ap-southeast-1`. |
| `$instance` | Drill-down tới replica/pod khi điều tra. | `shop-7d9...`. |

Chỉ tạo variable dựa trên label thực có trong datasource. Không đưa `traceId`, `orderId` hoặc `customerId` thành variable metric phổ biến vì cardinality và phạm vi truy vấn lớn.

### 10.2. Bộ lọc dùng nhất quán

Nếu metric có label `environment`, query nên lọc:

~~~promql
sum by (module_identifier) (
  rate(module_events_published_total{
    environment=~"$environment"
  }[5m])
)
~~~

Label `environment` trong ví dụ phải được gắn vào meter hoặc resource pipeline. Spring Modulith không tự suy ra môi trường triển khai chỉ từ tên module.

### 10.3. Drill-down có chủ đích

Một luồng điều tra nên đi theo thứ tự:

1. Chọn environment và service.
2. Nhận diện module có rate/error/latency bất thường.
3. Lọc module identifier hoặc event type.
4. Mở trace mẫu có span lỗi hoặc duration cao.
5. Từ trace mở logs theo trace ID/span ID.
6. Nếu liên quan event, đối chiếu message ID/correlation ID và publication status.

Dashboard nên cung cấp link hoặc data link để đi từ panel metrics sang tracing backend. Tránh đưa trace ID vào metric labels chỉ để tạo link; hãy dùng exemplars hoặc cơ chế liên kết của Grafana/backend nếu có.

## 11. Liên kết metrics, traces và logs

### 11.1. Metrics phát hiện vấn đề; traces giải thích một lần thực thi

Metrics tổng hợp tốt để nhận diện xu hướng:

- Event rate tăng gấp nhiều lần.
- Error rate của payment vượt ngưỡng.
- p95 HTTP latency tăng.
- Một module có số invocation tăng bất thường.

Trace giúp hiểu một request cụ thể đã đi qua module nào, span nào chậm và exception xảy ra ở đâu. Logs cung cấp nội dung chẩn đoán chi tiết với trace/span correlation.

### 11.2. Trace ID không nên là metric label

Không gắn `traceId` hoặc `spanId` vào Prometheus labels. Mỗi request có thể tạo ID mới, dẫn tới hàng triệu time series. Giữ các ID này trong trace/log và dùng exemplar hoặc data link để điều hướng.

### 11.3. Ví dụ log có correlation

~~~text
2026-11-27T02:00:00.123Z ERROR traceId=4bf92f... spanId=00f067... module=payment event=PaymentAuthorized - gateway timeout
~~~

Đây là log minh họa. Dashboard log panel có thể lọc theo `traceId` lấy từ trace backend, nhưng phải bảo đảm logger thực sự đưa trace/span fields vào MDC và log pipeline giữ chúng.

### 11.4. Context propagation cho async listener

Nếu `@ApplicationModuleListener` chạy trên executor thread khác, trace context/MDC có thể không tự được giữ. Cần cấu hình context propagation trên executor thực tế (ví dụ `ContextPropagatingTaskDecorator`) và xác minh listener dùng executor đó. Với broker/process boundary, cần inject/extract trace context qua message headers.

Nếu context bị mất, dashboard có thể thấy listener span như một trace mới. Điều này không nhất thiết có nghĩa event không được xử lý; cần kiểm tra propagation và correlation ID.

## 12. Alerting từ dashboard

Alert nên phản ánh điều kiện cần hành động, không chỉ cảnh báo mọi thay đổi.

| Alert | Tín hiệu | Hành động gợi ý |
| --- | --- | --- |
| HTTP server error rate cao | Tỷ lệ 5xx vượt ngưỡng trong thời gian liên tục. | Mở dashboard service và trace lỗi mẫu. |
| Module payment latency cao | p95/p99 của span/timer payment vượt SLO. | Lọc payment module, xem trace chậm và dependency bên ngoài. |
| Event publication spike | Rate một event type tăng bất thường so với baseline. | Kiểm tra producer, deploy và traffic nghiệp vụ. |
| Event processing delay cao | Event age hoặc queue lag vượt ngưỡng. | Kiểm tra executor, consumer, broker và listener. |
| Collector/trace export failure | Export queue/drop hoặc collector errors tăng. | Kiểm tra telemetry pipeline; trace absence có thể do exporter. |
| Module không có telemetry | Không thấy span/metric trong cửa sổ kỳ vọng. | Kiểm tra traffic, instrumentation, sampling và scrape/export. |

Alert về “không có dữ liệu” cần thận trọng: module có thể không được gọi trong khoảng thời gian đó. Dùng expected traffic, lịch vận hành hoặc metric heartbeat nếu muốn phát hiện telemetry pipeline mất kết nối.

### 12.1. Ví dụ PromQL cho alert 5xx

~~~promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
> 0.05
~~~

Ngưỡng `5%` chỉ là ví dụ. Trong production cần dùng SLO, traffic floor và `for` duration phù hợp; lọc theo service/environment để tránh trộn staging với production.

### 12.2. Alert event rate bất thường

Có thể dùng recording rule hoặc baseline so sánh theo thời gian cho event publication. Không đặt alert chỉ vì `OrderPlaced` tăng: campaign, giờ cao điểm hoặc batch import có thể tạo spike hợp lệ. Kết hợp event rate với error rate, processing delay hoặc business KPI.

## 13. Những hiểu lầm cần tránh

**“Có module graph là biết runtime đang gọi module nào.”** Không. Graph là cấu trúc phụ thuộc; runtime cần spans/metrics.

**“Có event counter là listener đã xử lý thành công.”** Không. Counter đo publication; cần outcome metric hoặc trạng thái publication.

**“Một module không có span nghĩa là module không được gọi.”** Chưa chắc. Có thể không đi qua điểm instrument, bị sampling loại, hoặc exporter/backend không nhận span.

**“Có module-entry spans thì có sẵn ma trận caller-target.”** Không nhất thiết. Muốn biết caller và target cần quan hệ span parent-child cùng metadata module phù hợp; đôi khi phải instrument bổ sung.

**“Có p95 trên dashboard thì không cần histogram config.”** Sai. Cần histogram buckets hoặc dữ liệu quantile phù hợp; timer chỉ có count/sum không đủ tính p95.

**“Gộp tất cả event types giúp dashboard đơn giản hơn.”** Có thể che sự cố của một event hiếm. Nên có cả tổng theo module và chi tiết theo event type.

**“Trace ID là một label tốt để click từ metrics.”** Không. Trace ID có cardinality cao; dùng exemplars hoặc data links từ trace/log backend.

## 14. Quy trình xây dashboard từng bước

1. **Xác định người dùng dashboard:** developer, on-call, platform team hay product operations.
2. **Chốt câu hỏi:** service có khỏe không, module nào có vấn đề, event nào bất thường, trace nào cần mở.
3. **Kiểm tra nguồn dữ liệu:** Actuator endpoints, meter names/tags, module-entry spans, tracing backend và log correlation.
4. **Đặt schema labels:** thống nhất service/environment/module/event type; không thêm ID duy nhất vào metrics.
5. **Dựng hàng tổng quan:** request rate, error rate, latency và health.
6. **Thêm topology:** graph được sinh từ phiên bản ứng dụng đang triển khai.
7. **Thêm runtime module panels:** span count/duration/status theo module; chỉ dựng caller-target matrix khi metadata đủ.
8. **Thêm event panels:** publication rate theo module/event type và per-event custom tags khi cần.
9. **Thêm drill-down:** links tới traces và logs, lọc theo trace ID ở datasource phù hợp.
10. **Thêm variables:** environment, service, module, event type và region nếu có.
11. **Thiết kế alert:** dựa trên SLO và tín hiệu có thể hành động.
12. **Kiểm thử dashboard:** tạo request thành công, lỗi, event async và latency cao; xác minh panel phản ánh đúng.
13. **Gắn version:** lưu dashboard provisioning cùng release/commit hoặc version schema metric.
14. **Rà soát quyền truy cập:** bảo vệ Actuator, Grafana và tracing backend.

## 15. Bài tập thực hành

### Bài 1 — Dashboard service overview

Tạo bốn panel: request rate, 5xx error rate, p95 latency và health status. Kiểm tra tên metric thực từ `/actuator/prometheus`; không giả định label `application` hoặc `environment` tồn tại nếu ứng dụng chưa gắn.

### Bài 2 — Module graph và runtime

Lấy module graph từ Spring Modulith Documenter hoặc `/actuator/modulith`. Sau đó tạo request gọi qua `ordering → payment`. So sánh cạnh graph với module-entry spans của trace. Giải thích vì sao graph có cạnh nhưng không phải request nào cũng có span payment.

### Bài 3 — Event publication dashboard

Tạo panel event rate theo `module.identifier` và event type. Gửi `OrderPlaced` và `OrderCancelled` với số lượng khác nhau. Quan sát khi gộp event type thì xu hướng nào bị che khuất.

### Bài 4 — Event processing delay

Thêm metric custom đo khoảng cách từ `publishedAt` tới `processingStartedAt` và duration listener. Đưa hai metric lên dashboard. Giải thích vì sao chúng đo hai khía cạnh khác nhau và vì sao clock synchronization quan trọng.

### Bài 5 — Trace/log drill-down

Bật Micrometer Tracing, đưa `traceId` và `spanId` vào MDC. Tạo một lỗi tại module payment, mở trace và logs tương ứng từ dashboard. Không thêm trace ID làm Prometheus label.

### Bài 6 — Alert có ngữ cảnh

Tạo alert khi 5xx rate vượt ngưỡng và khi event processing delay vượt SLO. Đính kèm link dashboard/trace và xác định người nhận alert. Kiểm tra tình huống no traffic để tránh alert giả.

### Câu hỏi tự kiểm tra

**Câu 1.** Module graph và runtime interaction dashboard khác nhau thế nào?

**Đáp án:** Module graph biểu diễn quan hệ phụ thuộc cấu trúc; runtime dashboard dựa trên spans/metrics của những lần thực thi thực sự được instrument và thu thập.

**Câu 2.** Counter `module.events.published` có chứng minh listener hoàn tất không?

**Đáp án:** Không. Nó đo event publication; cần outcome metric hoặc trạng thái từ cơ chế theo dõi publication.

**Câu 3.** Khi nào có thể tạo module-to-module interaction matrix?

**Đáp án:** Khi trace có span cha/con và metadata module đủ để xác định caller và target; nếu không cần instrument bổ sung.

**Câu 4.** Vì sao không dùng trace ID làm Prometheus label?

**Đáp án:** Trace ID gần như duy nhất theo request, làm cardinality tăng rất cao; nên giữ trong traces/logs và dùng exemplar/data link.

**Câu 5.** Vì sao dashboard p95 cần histogram bucket?

**Đáp án:** p95 cần phân bố latency; classic histogram dùng bucket `le`. Count/sum đơn thuần chỉ đủ tính average, không đủ suy ra quantile.

**Câu 6.** Nếu dashboard không có module span, có thể kết luận module không chạy không?

**Đáp án:** Không. Cần kiểm tra instrumentation, sampling, đường gọi qua Spring proxy, exporter và backend trước khi kết luận.

## 16. Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Insight Starter, module-entry spans và event metrics.
- [Spring Modulith — Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html): nhận diện application module và cấu trúc module.
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html): sinh tài liệu và sơ đồ module.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer metrics và endpoint.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing, sampling và correlation.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): ObservationRegistry, conventions và handlers.
- [Prometheus — Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/): PromQL và truy vấn dữ liệu time series.
- [Prometheus — Histograms](https://prometheus.io/docs/practices/histograms/): histogram aggregation và quantiles.
- [Grafana — Dashboards](https://grafana.com/docs/grafana/latest/dashboards/): panels, variables, links và dashboard design.
- [Grafana — Data links](https://grafana.com/docs/grafana/latest/panels-visualizations/configure-data-links/): liên kết từ panel sang trace/log hoặc trang điều tra.

**Ghi nhớ:** dashboard tổng quan tương tác module cần ghép module graph tĩnh, module-entry traces, event publication metrics và tín hiệu sức khỏe của service. Hãy giữ rõ ngữ nghĩa của từng nguồn: graph cho biết phụ thuộc, spans cho biết lần thực thi, event counters cho biết publication, logs cho biết chi tiết. Thiết kế panel theo câu hỏi vận hành, dùng nhãn có cardinality thấp và tạo đường drill-down từ metrics sang trace/log để điều tra.
