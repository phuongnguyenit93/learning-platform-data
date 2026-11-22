# Kiểm soát cardinality, lấy mẫu và chi phí lưu trữ

> **Chủ đề:** Software Architecture · Microservices · Quan sát hệ thống  
> **Trọng tâm:** Thiết kế metrics, logs và distributed traces đủ hữu ích để phát hiện, điều tra sự cố mà không làm hệ thống quan sát bị quá tải bởi số lượng chuỗi thời gian, khối lượng sự kiện và chi phí lưu trữ.

## 1. Tại sao dữ liệu quan sát cũng cần được thiết kế?

Một kiến trúc microservices có nhiều Pod, service và cuộc gọi liên dịch vụ. Mỗi request có thể sinh:

- Một số **metrics** về lưu lượng, lỗi, độ trễ hoặc tài nguyên.
- Một hoặc nhiều **structured logs** ở từng service.
- Một **distributed trace** gồm nhiều span xuyên Gateway, Order, Inventory, Payment và database.
- Một số **events** bổ sung phục vụ kiểm toán hoặc phân tích.

Nếu mặc định lưu mọi metric dimension, mọi log và mọi span mãi mãi, dữ liệu quan sát có thể tăng nhanh hơn lưu lượng nghiệp vụ. Hậu quả thường gặp: Prometheus nhiều active series, OTel Collector tốn RAM, truy vấn dashboard chậm, remote-write backlog tăng, trace storage phình to hoặc hóa đơn ingest/retention vượt ngân sách.

Ngược lại, giảm dữ liệu quá mức có thể khiến không thấy lỗi hiếm, không lần theo được một giao dịch thất bại, hoặc không chứng minh được SLA/SLO.

**Nguyên tắc:** Quan sát hệ thống là một sản phẩm dữ liệu có ngân sách, schema, vòng đời và mức dịch vụ. Cần chủ động chọn **độ chi tiết nào phải được giữ**, **dữ liệu nào có thể lấy mẫu** và **dữ liệu nào cần lưu lâu hơn**.

## 2. Phân biệt ba loại telemetry và cách chi phí hình thành

| Loại dữ liệu | Đơn vị chính | Khối lượng do đâu? | Rủi ro lớn |
|---|---|---|---|
| **Metrics** | Time series = tên metric + tập labels, với các samples theo thời gian | Số series hoạt động, scrape interval, bucket, số instance, churn | Cardinality explosion, RAM/index/query tăng |
| **Logs** | Một sự kiện gồm timestamp, severity, message, attributes | Events/giây × kích thước trung bình, stack traces, debug spam | Ingest/storage lớn, tìm kiếm và indexing đắt |
| **Traces** | Một trace gồm các spans, mỗi span có attributes/events | Requests/giây × số spans/request × byte/span × tỷ lệ giữ | Lưu quá nhiều span, chi phí collector/backend |
| **Profiles (nếu có)** | Samples CPU/heap, stack profiles | Tần suất profiling và kích thước profile | CPU overhead, dữ liệu liên quan source/stack nhạy cảm |

Metrics dùng cho **xu hướng và cảnh báo**, logs ghi **chi tiết sự kiện**, traces thể hiện **đường đi và thời gian**. Chúng bổ sung nhau; không nên nhồi toàn bộ dữ liệu request vào metric labels để thay cho logs/traces.

Ví dụ cần trả lời “checkout đang lỗi bao nhiêu phần trăm?” thì một counter theo service/route/status là phù hợp. Muốn biết “đơn ORD-1001 lỗi vì sao?” thì dùng traceId, logs có correlation và bản ghi nghiệp vụ đã phân quyền; không tạo metric label **order_id=ORD-1001**.

## 3. Cardinality là gì?

**Cardinality** của một label là số giá trị phân biệt của label đó. **Cardinality của metric** là số tổ hợp label thực sự xuất hiện, mỗi tổ hợp tạo ra một time series độc lập.

Ví dụ:

~~~text
http_requests_total{
  service="order",
  route="/orders/{id}",
  method="GET",
  status_class="2xx",
  environment="prod"
}
~~~

Nếu các label có lần lượt 10 service, 20 route, 4 method, 5 status class và 3 environment, **giới hạn tổ hợp lý thuyết** là:

~~~text
10 × 20 × 4 × 5 × 3 = 12.000 series
~~~

Số thực tế có thể thấp hơn vì không phải tổ hợp nào cũng xuất hiện; nhưng mỗi label mới có thể nhân thêm nhiều tổ hợp. Ví dụ thêm **instance** với 30 giá trị có thể đẩy giới hạn lý thuyết tới 360.000 series. Thêm một **user_id** với 200.000 người dùng tạo nguy cơ tăng cực lớn.

**Cardinality không phải số request.** Một triệu request tới cùng một nhóm label vẫn có thể tăng counter trong một series. Ngược lại, chỉ một request mới mang **request_id** khác nhau cũng đủ tạo một series mới nếu request_id được đưa vào label.

### Cardinality và churn là hai rủi ro liên quan

- **Active series:** số series hiện đang có samples; ảnh hưởng tới bộ nhớ, số samples/s, tính toán và query.
- **Series churn:** các tổ hợp label sinh ra rồi biến mất nhanh, chẳng hạn tên Pod, container ID hoặc ephemeral task ID; tăng công việc tạo/xóa series và index/WAL metadata dù active series tại một thời điểm không quá cao.
- **Historical cardinality:** số chuỗi phân biệt tồn tại trong khoảng tra cứu hoặc retention; tăng chi phí index và truy vấn dài hạn.

Vì vậy dashboard chỉ báo active series có thể bỏ sót trường hợp một service tạo hàng triệu series ngắn hạn trong ngày.

## 4. Những label gây bùng nổ thường gặp

| Label | Có thể dùng làm label metric? | Lý do |
|---|---|---|
| **service**, **environment**, **region** | Thường có | Tập giá trị được quản lý, giới hạn |
| **http.method** | Có, khi chuẩn hóa | Số phương thức hữu hạn |
| **route template**: /orders/{id} | Có, khi danh sách route được quản lý | Không tăng theo mỗi order |
| **status class**: 2xx/4xx/5xx | Có | Tập giá trị nhỏ |
| **operation**: checkout/create_order | Có, khi taxonomy rõ | Nhóm nghiệp vụ hữu hạn |
| **tenant tier**: free/pro/enterprise | Có nếu tập nhỏ | Phân tích cohort mà không tạo một series/tenant |
| **tenant_id** | Thường tránh | Có thể hàng nghìn hoặc tăng không giới hạn |
| **user_id**, **order_id**, **session_id**, **trace_id** | **Không** | Gần như mỗi người/request là một giá trị mới |
| **full URL/path**: /orders/12345 | **Không** | ID trong path làm mỗi URL thành series mới |
| **exception message**, **SQL text** | **Không** | Chuỗi động, có thể chứa dữ liệu nhạy cảm |
| **ip_address**, **email**, **JWT/token** | **Không** | Cardinality cao và rủi ro riêng tư/bảo mật |
| **pod name** | Chỉ khi thực sự cần | Số Pod và churn có thể lớn; thường tập trung ở metrics hạ tầng |

Một label “tưởng như nhỏ” cũng có thể nguy hiểm nếu được lấy từ input không kiểm soát. Ví dụ client được phép tự đặt **X-Feature-Name**, rồi service đưa nguyên giá trị vào label; một client có thể tạo vô hạn series.

**Chiến lược:** Chỉ cho phép giá trị từ một tập đã biết, đưa giá trị lạ vào **unknown/other**, hoặc bỏ dimension đó khỏi metrics và truy vấn chi tiết trong logs/traces.

## 5. Route template thay cho raw path

**Không nên:**

~~~text
http_server_requests_total{uri="/orders/100001",status="200"} 1
http_server_requests_total{uri="/orders/100002",status="200"} 1
http_server_requests_total{uri="/orders/100003",status="200"} 1
~~~

Ba đơn đã tạo ba series khác nhau. Khi có hàng triệu đơn, số series tăng theo business IDs.

**Nên:**

~~~text
http_server_requests_total{route="/orders/{id}",method="GET",status_class="2xx"} 3
~~~

Ở đây **route** là mẫu route của router/framework, không phải đường dẫn thực tế. Nếu hệ thống không có route matched, gán **unmatched** hoặc nhóm giá trị cố định phù hợp thay vì sử dụng raw path làm fallback.

Thông tin order ID cần truy tìm có thể nằm trong log truy cập được phân quyền hoặc trace attribute có kiểm soát, không trở thành metric label. Cũng không nên đưa ID vào metric name như **http_orders_100001_requests_total**.

## 6. Thiết lập ngân sách cardinality trước khi instrument

Đừng chỉ chờ TSDB quá tải rồi mới xóa metric. Với mỗi metric family, cần dự tính:

~~~text
Estimated series ≤ ∏ distinct values for each label
                  × số bucket hoặc sub-series nếu là histogram
                  × số nguồn xuất bản (instance/target nếu có)
~~~

Đây là **upper bound**, không phải số series chắc chắn. Label tương quan có thể khiến tổ hợp thực tế ít hơn. Tuy nhiên nó giúp phát hiện dimension bất hợp lý trước khi phát hành.

Ví dụ một latency histogram classic có:

~~~text
service:       8 giá trị
route:        12 giá trị
method:        4 giá trị
status_class:  5 giá trị
instance:     10 giá trị
le buckets:   12 ranh giới tính cả +Inf
~~~

Giới hạn tổ hợp cho riêng bucket series:

~~~text
8 × 12 × 4 × 5 × 10 × 12 = 230.400 bucket series
~~~

Histogram classic còn có **_sum** và **_count** cho mỗi tổ hợp label, vì vậy tổng series thực tế của metric histogram có thể cao hơn. Không phải mọi route hỗ trợ mọi method/status, nhưng tính toán cho thấy bucket và instance nhân thêm đáng kể.

Đặt **series budget** theo team/service/metric và **org-level quota** có ý nghĩa hơn chỉ đặt một giới hạn tổng không phân quyền. Ngân sách có thể bao gồm:

- Số active series tối đa cho mỗi workload.
- Tốc độ series mới và tốc độ churn tối đa.
- Số unique values tối đa cho từng label có nguy cơ cao.
- Samples/second và bytes ingest/second.
- Số histogram buckets tối đa ở nhóm metric quan trọng.
- Chi phí theo environment/tenant/team hoặc sản phẩm.

### Metric design review ngắn

Trước khi thêm label, trả lời: **Có cần nhóm/alert theo dimension này không? Tập giá trị lớn nhất là bao nhiêu? Ai kiểm soát giá trị? Nó có tăng theo số request/user/order không? Có biến thể ít cardinality hơn không?**

Nếu không trả lời được, label nên nằm ngoài metric cho đến khi có bằng chứng cần thiết.

## 7. Metrics cho microservices: Ít dimension nhưng vẫn đủ SLO

Nên bắt đầu từ các nhóm tín hiệu thiết yếu:

**RED** cho request-serving service:

- **Rate:** tổng số request hoặc request/giây.
- **Errors:** số lỗi/tỷ lệ lỗi theo loại phù hợp.
- **Duration:** phân phối latency, gồm p50/p95/p99 nếu có histogram đủ dữ liệu.

**USE** cho tài nguyên:

- **Utilization:** CPU, memory, connection pool utilization.
- **Saturation:** thread pool/queue backlog, pending requests, database pool waits.
- **Errors:** lỗi socket, timeout, allocation/GC bất thường, dropped messages.

Labels thường hữu ích: **service**, **deployment_environment**, **region**, **route_template**, **method**, **status_class**. Tránh “all dimensions everywhere”: ví dụ metric JVM garbage collection không cần label HTTP route.

Một metric nên đo **một khái niệm**. Đưa 20 labels “để sau này dễ filter” làm tăng chi phí cho mọi series, kể cả khi không ai dùng chúng để ra quyết định.

## 8. Histograms: Chi phí của buckets và độ chính xác

Histograms giúp tính quantile và aggregate nhiều instance. Nhưng **classic histogram** tạo một series cho mỗi bucket boundary (**le**) cùng các series **_count** và **_sum**.

Ví dụ minh họa:

~~~text
checkout_duration_seconds_bucket{service="order",le="0.1"} 120
checkout_duration_seconds_bucket{service="order",le="0.3"} 310
checkout_duration_seconds_bucket{service="order",le="1.0"} 490
checkout_duration_seconds_bucket{service="order",le="+Inf"} 500
checkout_duration_seconds_sum{service="order"} 97.4
checkout_duration_seconds_count{service="order"} 500
~~~

Nếu số ranh giới bucket tăng từ 8 lên 30 trong khi labels giữ nguyên, bucket series tăng gần theo tỷ lệ đó. Chọn buckets **quanh SLO threshold** và vùng latency cần phân tích, tránh đặt quá dày ở mọi giá trị. Một số hệ thống hỗ trợ **native histogram** hoặc định dạng phân phối khác, có thể tối ưu số series/storage trong những tình huống nhất định; cần kiểm tra tính tương thích của exporter, backend và truy vấn trước khi đổi.

**Không ghi latency theo user_id/order_id.** Nếu cần phân tích một giao dịch chậm, trace cung cấp chi tiết mà không gây bùng nổ metric series.

Ví dụ PromQL cho classic histogram, tên metric tùy instrument:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service, route) (
    rate(http_request_duration_seconds_bucket[5m])
  )
)
~~~

Dùng **rate** trên counter bucket trước khi tổng hợp và giữ nhãn **le** khi tính classic histogram quantile. Kết quả p95 là **ước lượng từ buckets**, chất lượng phụ thuộc ranh giới và số mẫu. Đừng coi p95 được tính bằng cách trung bình p95 của từng instance.

## 9. Guardrail khi viết instrumentation trong Spring Boot

Với Spring Boot, Micrometer có thể gắn metric vào Actuator/OpenTelemetry/Prometheus tùy cấu hình. Cần định nghĩa tags lấy từ dữ liệu **đã chuẩn hóa**.

Ví dụ minh họa:

~~~java
enum CheckoutOutcome { SUCCESS, VALIDATION_ERROR, PROVIDER_ERROR, TIMEOUT }

void recordCheckout(MeterRegistry registry, CheckoutOutcome result) {
    Counter.builder("checkout_attempts")
        .description("Number of checkout attempts grouped by bounded outcome")
        .tag("outcome", result.name())
        .register(registry)
        .increment();
}
~~~

Tag **outcome** chỉ có bốn giá trị được định nghĩa trong enum. Trong Prometheus, hệ thống naming/export có thể biểu diễn counter với hậu tố **_total** theo quy tắc exporter.

**Không nên:**

~~~java
Counter.builder("checkout_attempts")
    .tag("order_id", command.orderId().toString())
    .tag("customer_email", command.email())
    .register(registry)
    .increment();
~~~

Nếu cả hai tag thay đổi theo giao dịch, registry tạo nhiều meter/series và còn có rủi ro lộ thông tin cá nhân.

Có thể dùng **MeterFilter.maximumAllowableTags** (theo phiên bản Micrometer được dùng) để đặt trần tag values như một **safety net**:

~~~java
registry.config().meterFilter(
    MeterFilter.maximumAllowableTags(
        "http.server.requests",
        "uri",
        100,
        MeterFilter.deny()
    )
);
~~~

Đây là **mẫu minh họa**, cần kiểm tra tên meter/tag và phiên bản Micrometer thực tế. Guardrail sẽ từ chối meter vượt trần, có thể làm mất một phần khả năng quan sát; nên **chuẩn hóa route ở nguồn trước**, rồi đo số lần vi phạm guardrail. Đừng coi filter là cách sửa root cause.

## 10. Tránh cardinality từ metadata hạ tầng

Kubernetes và service mesh có thể gắn labels như **pod**, **container_id**, **node**, **namespace**, **revision** vào nhiều metric. Những dimension này hữu ích cho debug hạ tầng nhưng có thể làm bùng nổ series khi mỗi deployment sinh Pod mới.

Gợi ý ranh giới:

- **Metric ứng dụng/SLO:** ưu tiên aggregation theo **service, region, environment, route**. Không đòi hỏi pod/container ID cho mọi truy vấn nghiệp vụ.
- **Metric vận hành Pod/node:** giữ pod/node khi cần xử lý capacity và scheduling; TTL ngắn hơn, chỉ số được chọn kỹ.
- **Metric dài hạn:** dùng recording rules tạo chuỗi tổng hợp ít labels; chỉ lưu lâu dữ liệu phục vụ xu hướng/capacity/SLO.
- **Churn metrics:** quan sát series tạo mới qua thời gian, số target biến động và scrape/remote-write samples.
- **Ephemeral batch jobs:** không gắn task UUID/job run UUID vào metric. Có thể dùng job_type, queue_name hoặc worker_pool (bounded) và trace/log cho run riêng lẻ.

Khi thay đổi nhãn do sidecar, discovery hoặc relabeling, phải tính ảnh hưởng đến dashboards và alerts; drop instance/pod trong toàn bộ pipeline có thể làm mất khả năng debug ở tầng Pod.

## 11. Lấy mẫu là gì và không nên lấy mẫu ở đâu?

**Sampling** là chỉ lưu/xử lý một phần dữ liệu theo một chiến lược để giảm volume hoặc overhead. Nhưng mỗi loại telemetry có yêu cầu riêng:

| Tín hiệu | Chiến lược phổ biến | Cảnh báo |
|---|---|---|
| **Metrics counters** | Giữ counters đầy đủ; giảm labels và dùng aggregation | Randomly drop samples làm sai rate/histogram và alert nếu không được thiết kế/ước lượng đúng |
| **Metric time series resolution** | Downsampling trên dữ liệu đã lưu hoặc giảm scrape frequency có kiểm soát | Giảm độ phân giải, mất spike ngắn; không phải sửa high cardinality |
| **Traces** | Head-based, parent-based, tail-based, adaptive sampling | Sample thấp có thể làm mất rare errors hoặc bias latency |
| **Logs** | Severity-based filtering, rate limiting, probabilistic sampling có key | Không lấy mẫu tùy tiện audit/security/business-critical events |
| **Profiles** | Periodic statistical sampling theo công cụ | Phải hiểu overhead và độ chính xác theo workload |

Một metric counter đã aggregate theo service/route có chi phí ổn định và giá trị lớn cho SLO. **Đừng áp dụng sampling log/traces sang metric một cách máy móc**.

Nên chọn retention/aggregation trước, rồi sampling nơi phù hợp. Cần giữ đủ tín hiệu để thấy toàn bộ mẫu số request và tính tỷ lệ lỗi đúng, ngay cả khi traces chỉ giữ một phần.

## 12. Head-based sampling cho distributed traces

**Head sampling** quyết định giữ trace từ lúc request bắt đầu, trước khi biết kết quả cuối. Ví dụ:

~~~text
Request mới → sampler quyết định sampled=true/false
            → propagation qua trace context
            → các service con tôn trọng quyết định theo chính sách
            → collector/backend nhận những span được giữ
~~~

Ưu điểm: giảm overhead sớm, dễ kiểm soát ngân sách, thuận lợi cho sampling nhất quán xuyên service. Nhược điểm: không thể biết trước trace nào sẽ lỗi hoặc chậm.

Một chiến lược probabilistic 10% nghĩa là xác suất giữ mỗi trace khoảng 0,1 theo cơ chế sampler, **không bảo đảm đúng 10% request ở mọi nhóm nhỏ**. Nếu chỉ có 5 lỗi trong ngày, với xác suất 10% có thể không giữ được trace lỗi nào.

Trong hệ phân tán, cần **propagate W3C Trace Context** hoặc cơ chế tương thích xuyên HTTP/messaging. Một service không nên tùy tiện tạo quyết định sampling khác làm trace bị đứt, trừ khi kiến trúc chủ động cho phép và backend hiểu partial traces.

**Parent-based sampling** thường giữ quyết định của parent để hạn chế tình trạng nhiều service tự lấy mẫu độc lập. Nếu upstream không đáng tin cậy, quyết định từ external caller có thể cần chính sách trust boundary riêng; không để một client Internet ép hệ thống ghi vô hạn traces bằng header sampled=true.

## 13. Tail-based sampling giữ trace lỗi và chậm

**Tail sampling** chờ nhận đủ hoặc gần đủ spans của một trace rồi mới quyết định giữ, dựa trên thông tin cuối như lỗi, độ trễ hoặc thuộc tính có kiểm soát.

Ví dụ chính sách:

~~~text
Giữ 100% trace có lỗi 5xx hoặc error status
Giữ 100% trace vượt ngưỡng latency SLO
Giữ 100% một số flow nghiệp vụ trọng yếu trong phạm vi ngân sách
Giữ ngẫu nhiên 5% trace thành công, nhanh
Giới hạn throughput và có chính sách khi vượt budget
~~~

Lợi ích: tăng xác suất có trace hữu ích khi điều tra lỗi hiếm, giảm volume của luồng thành công thông thường.

Đánh đổi:

- Collector phải giữ spans trong bộ nhớ hoặc buffer đủ lâu để quyết định; tăng RAM/CPU và độ trễ xuất trace.
- Nếu một trace có spans đi đến nhiều collectors mà không được route theo traceId nhất quán, sampler có thể không thấy toàn bộ trace.
- Trace quá dài hoặc span đến trễ có thể bị quyết định trước khi hoàn chỉnh.
- Khi collector quá tải/restart, có thể mất trace nếu không có buffer và cơ chế phục hồi phù hợp.
- Một policy "giữ mọi lỗi" vẫn có thể gây quá tải trong đợt outage có hàng triệu request lỗi.

**Tail sampling là giải pháp đánh đổi có điều kiện**, không bảo đảm tự động giữ 100% lỗi trong mọi tình huống vận hành.

## 14. Ví dụ OpenTelemetry sampling policy

Một kiến trúc tham khảo:

~~~text
Service SDKs
  | head sampling + trace-context propagation
  v
Local OTel Collector / Agent
  | batching, resource limits, safe attribute normalization
  v
Trace-aware routing layer
  | group spans by trace ID
  v
Tail-sampling collectors
  | error/latency/business policies + probabilistic baseline
  v
Trace backend
  | retention + access control + storage tiers
~~~

Các bước thiết kế:

1. Xác định **thứ tự sampling**: nếu SDK head-sample quá mạnh, tail sampler không thể khôi phục những trace đã bỏ ở SDK.
2. Xác định traces cần giữ theo **SLO và incident workflows**, không chỉ theo một tỉ lệ.
3. Cấu hình **decision wait**, số traces đệm và giới hạn tài nguyên phù hợp throughput/độ dài trace.
4. Bảo đảm spans của cùng trace đi cùng shard nếu tail sampler yêu cầu.
5. Có **fallback khi collector overloaded**: drop policy rõ ràng, cảnh báo, backpressure hoặc bảo toàn luồng quan trọng.
6. Đo số trace/spans **received, sampled, exported, dropped**, đặc biệt ở thời điểm xảy ra lỗi lớn.

Cú pháp cấu hình processor/policy phụ thuộc phiên bản OpenTelemetry Collector và distro sử dụng. Quy tắc trên là **mô hình thiết kế**, không phải YAML production copy nguyên xi.

## 15. Sampling phải phù hợp mục đích thống kê

### 15.1. Điều gì được tính chính xác?

Nếu **metrics** vẫn đếm mọi request, rate và error rate lấy từ metrics không bị ảnh hưởng bởi tỉ lệ trace sampling. Nhưng nếu dùng **traces đã sample** để đếm tỷ lệ lỗi của toàn hệ thống, cần hiểu mẫu có đại diện không.

Ví dụ trong 10.000 request:

~~~text
9.900 request thành công
100 request lỗi (error rate thực = 1%)

Sampling policy giữ:
  5% success = 495 trace
  100% errors = 100 trace

Traces lưu lại: 595
Tỷ lệ trace lỗi trong backend = 100 / 595 ≈ 16,8%
~~~

**16,8% không phải error rate thật.** Tail sampling ưu tiên lỗi đã làm mẫu bị thiên lệch. Dashboard SLO nên dùng counter metric đếm đầy đủ hoặc hệ thống phân tích có hiệu chỉnh theo xác suất sampling phù hợp.

### 15.2. Rare events có thể biến mất

Nếu một loại lỗi xảy ra 10 lần và sampling ngẫu nhiên giữ 5%, số trace lỗi được giữ kỳ vọng chỉ 0,5; xác suất không giữ trace lỗi nào là:

~~~text
P(miss all 10) = (1 - 0.05)^10 ≈ 59,9%
~~~

Vì thế cần ưu tiên các trace lỗi, các luồng hiếm hoặc tăng sampling tạm thời khi sự cố xảy ra, trong giới hạn ngân sách. **Head sampling tỉ lệ thấp** phù hợp xem bức tranh chung nhưng có thể thiếu chứng cứ cho rare failures.

### 15.3. Không nhầm số request và số span

Một trace có thể chứa 50 span. Giữ 10% traces không có nghĩa lưu đúng 10% spans hoặc 10% dung lượng nếu các trace dài thường liên quan đến lỗi và được giữ nhiều hơn. Cần đo **trung bình/quantile spans per retained trace** và byte/span theo workload.

## 16. Lấy mẫu logs có lựa chọn

Logs khác traces ở chỗ mỗi log là sự kiện riêng lẻ, thường có severity và business meaning.

Gợi ý chính sách:

- **ERROR và sự kiện bảo mật quan trọng:** ưu tiên giữ theo quy định, có rate limit kiểm soát để một lỗi lặp không bão hòa pipeline; không mặc nhiên drop không dấu vết.
- **WARN:** giữ nếu có giá trị vận hành, nhóm/tổng hợp lỗi lặp.
- **INFO:** giữ các sự kiện vòng đời trọng yếu; có thể giảm log success per request vì metrics/traces đã ghi tổng quan.
- **DEBUG/TRACE log level:** chỉ bật có thời hạn cho service/instance/tenant được phép; tự tắt khi hết thời hạn, giới hạn volume.
- **Audit/compliance events:** xác định pipeline riêng với tính toàn vẹn, retention và quyền truy cập; **không sampling ngẫu nhiên** nếu phải ghi đầy đủ.

Một ví dụ **rate limiting log trùng**:

~~~text
Trong 60 giây có 100.000 lỗi "provider timeout" giống nhau:
  lưu log chi tiết ban đầu có correlation
  tổng hợp count theo error category
  lấy một số log đại diện và lưu dấu lượng log bị giảm
  vẫn duy trì metrics đếm đủ số lỗi
~~~

Không chỉ “drop 99.9% ERROR logs” vì như vậy có thể bỏ mất thông tin mới. Nên chuẩn hóa **error class** và áp dụng rate limit theo key đã kiểm soát; giữ được sự kiện đầu/đặc biệt và bộ đếm số sự kiện bị cắt giảm.

### Structured logs

Ví dụ:

~~~json
{
  "time": "2026-11-12T08:00:00Z",
  "severity": "ERROR",
  "service": "payment",
  "environment": "prod",
  "trace_id": "example-trace-id",
  "span_id": "example-span-id",
  "error_type": "PROVIDER_TIMEOUT",
  "message": "payment provider request timed out"
}
~~~

Trace ID trong log giúp tìm đúng request; **trace_id không nên là label của Prometheus metrics**. Tránh đưa bearer token, mật khẩu, PII không cần thiết hoặc request/response body vào logs.

## 17. Log indexing: Lưu trữ và tìm kiếm là hai chi phí khác nhau

Chi phí log không chỉ bằng số byte data ở object storage. Nhiều backend còn tính phí cho:

- **Ingest và parser** để cấu trúc trường.
- **Index** (toàn văn hoặc theo fields) tăng theo số giá trị khác nhau.
- **Hot storage** dành cho tìm kiếm nhanh.
- **Queries** quét nhiều dữ liệu, nhất là query không có giới hạn service/time.
- **Replicas, backup, network egress** và bảo vệ dữ liệu.

Dữ liệu **trace_id, order_id, user_id** có thể cần được tìm trong logs, nhưng **khả năng truy vấn theo field** không đòi hỏi chúng trở thành metric labels hoặc labels được index vô hạn ở mọi log backend. Một số hệ thống phân biệt index labels và payload fields; chính sách phải theo tính năng cụ thể của backend.

Thiết kế log schema nên ưu tiên fields ổn định: **service**, **severity**, **environment**, **timestamp**, **error_type**, **trace_id**. Index những fields dùng thường xuyên theo khả năng chịu chi phí; những trường hiếm có thể chỉ lưu dưới dạng payload/low-cost tier theo nhu cầu.

## 18. Retention: Lưu cái gì trong bao lâu?

Chính sách retention nên phản ánh mục đích sử dụng và nghĩa vụ thực tế, không mặc định mọi telemetry giữ 90 ngày ở hot storage.

Ví dụ một chính sách **minh họa, cần chỉnh theo SLO/quy định**:

| Loại | Hot tier | Warm/aggregate | Long-term |
|---|---|---|---|
| High-resolution service metrics | 7–15 ngày | Recording rules/downsample nhiều tuần | Aggregate theo ngày/tháng nếu cần capacity/SLO |
| Infrastructure per-Pod metrics | 3–7 ngày | Aggregate theo service/node pool | Chỉ dữ liệu trend cần thiết |
| Traces success được sample | 3–7 ngày | Có thể lưu ngắn hơn | Thường không cần lưu từng trace lâu |
| Traces error/high latency | 7–30 ngày | Theo incident need | Chọn lọc sự cố quan trọng |
| INFO/DEBUG logs | 1–7 ngày | Tùy giá trị điều tra | Thường loại bỏ sớm |
| ERROR logs | 7–30 ngày | Archive có kiểm soát khi cần | Theo nhu cầu forensic |
| Audit/security records | Theo chính sách tổ chức/pháp lý | Storage truy cập hạn chế, integrity | Có thể khác hoàn toàn telemetry thông thường |

**Retention không phải chỉ giảm số ngày.** Có thể:

1. Giữ high-resolution metrics ngắn hạn.
2. Tạo aggregate/downsample theo service/region để theo dõi dài hạn.
3. Đưa logs cũ sang tier tìm kiếm chậm hơn nếu vẫn cần điều tra.
4. Giữ incident traces quan trọng có chủ đích, không giữ toàn bộ success traces.
5. Xóa dữ liệu theo vòng đời, chính sách riêng tư và yêu cầu pháp lý.

Cần cân nhắc SLO reporting: nếu cần chứng minh latency/error rate của 90 ngày, phải có aggregate phù hợp với cách tính SLO, tránh chỉ lưu p95 trung bình theo ngày vì không thể dùng trung bình của quantile để tái tạo quantile gốc chính xác.

## 19. Mô hình chi phí cơ bản

Chi phí thường phụ thuộc các thành phần:

~~~text
Total observability cost
≈ ingest charge
+ hot/warm/cold storage
+ index/cardinality overhead
+ query/compute
+ network/replication
+ operational overhead
~~~

Không có một “giá/GB” phổ quát cho mọi backend. Một hệ thống có thể tính theo **active series**, **samples**, **ingested bytes**, **indexed bytes**, **retention**, số spans hoặc query usage. Cần dùng mô hình chi phí của hệ đang chạy.

### 19.1. Ước lượng metrics samples

~~~text
daily_samples ≈ active_series × (86.400 / scrape_interval_seconds)
~~~

Ví dụ 50.000 active series với interval 30 giây:

~~~text
50.000 × (86.400 / 30) = 144.000.000 samples/ngày
~~~

Nếu tăng 5 lần số series do thêm label không cần thiết, daily samples gần tương ứng tăng 5 lần (nếu các series được scrape đều). **Thay interval từ 30 lên 60 giây giảm mẫu theo thời gian**, nhưng không giải quyết RAM/index do cardinality và làm mất độ phân giải các spike ngắn.

Lưu ý: công thức giả định scrape ổn định, không tính series churn, missing samples, native histogram encoding, metadata, index, WAL, replicas hay hành vi của backend. Không nhân trực tiếp với một bytes/sample cố định để tuyên bố hóa đơn thực tế nếu chưa đo.

### 19.2. Ước lượng logs

~~~text
daily_log_bytes ≈ events_per_day × average_event_bytes
retained_bytes ≈ daily_log_bytes × retention_days × effective_overhead_factor
~~~

Giả sử 20 triệu log sự kiện/ngày, trung bình 1 KB/event:

~~~text
20.000.000 × 1 KB ≈ 20 GB/ngày (dùng đơn vị thập phân)
7 ngày ≈ 140 GB log payload trước index, replicas và compression
~~~

Nếu một cấu hình debug làm mỗi request thêm 5 KB log payload, ingest tăng đáng kể ngay cả khi request rate không đổi. Cần đo size distribution, không chỉ kích thước message trung bình.

### 19.3. Ước lượng traces

~~~text
daily_trace_bytes
≈ requests_per_day × spans_per_request × bytes_per_span × retention_fraction
~~~

Ví dụ 1 triệu request/ngày, trung bình 15 spans/request, 800 bytes/span:

~~~text
100% traces: 1.000.000 × 15 × 800 = 12 GB/ngày
10% traces: khoảng 1,2 GB/ngày nếu mẫu đại diện và kích thước không đổi
~~~

Tail sampling ưu tiên trace lỗi/chậm có thể giữ các traces dài hơn trung bình, nên **10% traces không bảo đảm chỉ còn 10% bytes**. Đây là payload ước lượng, chưa tính backend indexing, compression, replica và network.

### 19.4. Tổng chi phí cần đo ở từng điểm

Một pipeline có thể giảm bytes **trước backend ingest** nhưng vẫn tốn CPU/network tại nơi emit hoặc collector. Cần đo:

- Bytes/events/spans sinh tại SDK/service.
- Bytes/events/spans nhận tại collector.
- Số bị filter/sample/drop và lý do.
- Bytes gửi tới backend theo team/service.
- Stored bytes, index bytes, retention và query usage.
- Collector CPU/RAM/network và remote-write backlog.

**Giảm tại nguồn** và **giảm sau khi ingest** có tác động chi phí khác nhau. Một backend có thể tính phí trước hoặc sau một processor theo hợp đồng của nó.

## 20. Ưu tiên tối ưu theo giá trị thông tin

Khi ngân sách bị vượt, không cắt ngẫu nhiên mọi dữ liệu theo cùng một tỷ lệ. Một thứ tự hành động có cơ sở:

1. **Sửa label cardinality không kiểm soát**: raw path, user_id, request_id, UUID động.
2. **Loại bỏ instrumentation trùng** giữa SDK, agent và service mesh nếu cùng thông tin không cần cả ba.
3. **Chuẩn hóa metric scope**: RED theo route/service, resource metrics theo node/pool, tránh mọi dimension cho mọi metric.
4. **Tinh chỉnh histograms**: tập trung buckets có ý nghĩa SLO, kiểm tra native histogram support nếu phù hợp.
5. **Giảm logs vô ích**: thông báo lặp, request success level INFO không cần thiết, payload lớn.
6. **Trace sampling dựa trên giá trị**: giữ lỗi/slow paths và mẫu success hợp lý, có giới hạn chi phí.
7. **Chuyển data cũ sang storage tier rẻ hơn** và giảm retention high-resolution theo nhu cầu điều tra.
8. **Giới hạn quotas theo team/service/tenant**, tránh một workload gây chi phí hoặc sự cố chung.
9. **Tối ưu query và index**, tránh dashboard quét toàn hệ thống không giới hạn.
10. **Đo lại** ingestion, active series, churn, coverage và cost sau mỗi thay đổi.

Đặt cân bằng giữa **khả năng chẩn đoán** và **chi phí**. Đừng tắt những tín hiệu đo SLO quan trọng chỉ vì chiếm volume nhiều hơn những metric trang trí.

## 21. Một kiến trúc quan sát có kiểm soát cho microservices

~~~text
                     +----------------+
                     | API Gateway    |
                     +-------+--------+
                             |
                       trace context
                             |
                  +----------v-----------+
                  | Order / Payment API  |
                  | metrics + logs +     |
                  | instrumented spans  |
                  +----------+-----------+
                             |
                +------------+--------------+
                |                           |
                v                           v
        Metrics pipeline             OTel collector agents
        scrape/receive               batch, redaction, limits
        bounded labels                      |
                |                    trace/log pipelines
                v                           |
        Aggregation/recording         sampling/filtering
        rules / retention                    |
                |                           |
                v                           v
        TSDB + alerts                Trace + log backends
                |                           |
                +-------------+-------------+
                              |
                       Dashboards, SLOs,
                       incident workflow
~~~

**Tại service:** instrument đúng tín hiệu, đặt schema và tags an toàn, propagate trace context, hạn chế PII.

**Tại collector/ingestion:** đặt memory limits, batching, filtering, sampling, routing, alert khi drop và quota theo team/tenant. Collector không phải kho lưu duy nhất cho dữ liệu audit bắt buộc.

**Tại backend:** bảo vệ ingestion/query, duy trì retention tiers, index policy, recording rules và chi phí theo owner.

**Tại vận hành:** dùng metrics để biết có sự cố và phạm vi, dùng exemplar/traceId hoặc logs để drill down, giữ đủ thông tin cho điều tra sau khi incident kết thúc.

## 22. Correlation và exemplars: Đào sâu mà không thêm cardinality

Thay vì metric labels chứa request ID, dùng **correlation** giữa ba loại telemetry:

1. Dashboard biểu diễn error rate theo service/route, nhãn có cardinality thấp.
2. Một số hệ thống metric hỗ trợ **exemplars** gắn trace ID đại diện với điểm đo/histogram; exemplar không nên bị hiểu như thêm label time series cho mọi request.
3. Từ exemplar hoặc log có trace_id, mở distributed trace tương ứng.
4. Trace span có các thuộc tính thích hợp để tra request, dependency, version và lỗi.

Ví dụ:

~~~text
metric:  request_latency_seconds_bucket{service="payment",route="/charge",le="1.0"}
exemplar: trace_id=abc123...  (đại diện có kiểm soát)
trace:   Gateway -> Order -> Payment -> Provider
log:     error_type=PROVIDER_TIMEOUT, trace_id=abc123...
~~~

Không phải mọi request đều có exemplar hoặc retained trace; nếu sampling đã bỏ trace, link exemplar có thể trỏ tới trace không tồn tại. Cần thiết kế exemplar sampling và trace sampling phù hợp.

**Trace ID là khóa tìm kiếm/correlation, không phải dimension để group SLO.** Với hệ thống có dữ liệu nhạy cảm, link còn phải tuân thủ quyền truy cập logs/traces.

## 23. Recording rules, downsampling và báo cáo SLO

**Recording rules** giúp tạo time series aggregate từ metric gốc có nhiều labels. Ví dụ PromQL minh họa:

~~~promql
sum by (service, route, status_class) (
  rate(http_server_requests_total[5m])
)
~~~

Để giảm cardinality cho dashboard dài hạn, có thể tổng hợp bỏ **instance** hoặc **pod** và chỉ giữ **service, region, route**. Nhưng phải phân biệt:

- **Recording rule** tạo thêm series aggregate; nó không tự động xóa series gốc. Nếu cả gốc và aggregate được lưu dài hạn, tổng chi phí có thể tăng.
- **Downsampling** giảm độ phân giải samples; dữ liệu spike ngắn có thể mất.
- **Histogram aggregation** cần giữ buckets hoặc biểu diễn phân phối đủ thông tin. Không lấy trung bình p95 giữa các Pod để ra p95 toàn service.
- **SLO error-rate** nên tính từ counters đầy đủ, được định nghĩa rõ lỗi nào tính vào numerator và tổng request nào là denominator.
- Nếu dùng long-term storage, retention dữ liệu gốc và aggregate cần có chính sách tách biệt, tránh mất khả năng truy vết sai lệch.

Một alert cần thông tin đủ để hành động. Đưa **user_id** vào rule sẽ tạo nhiều alert liên quan cùng một sự cố; nên alert theo service/route/region rồi điều tra trace/log.

## 24. Multi-tenant quotas và trách nhiệm chi phí

Trong tổ chức có nhiều team, mỗi nhóm có thể đẩy telemetry vào cùng backend. Một ứng dụng tạo nhãn request_id vô hạn có thể làm chậm dashboard và alert của tất cả.

Cần các giới hạn:

- **Per-tenant/per-team active series limit**, ingestion rate và series churn threshold.
- **Logs/traces bytes ingest per minute**, giá trị burst cho incidents nhưng không vô hạn.
- **Max attributes/labels per event**, max payload size, giới hạn stack trace/message lớn.
- **Query timeout/concurrency/budget**, để dashboard không lấn át cảnh báo.
- **Retention theo tier và severity**, ownership rõ, chargeback/showback theo service.
- **Circuit breaker hoặc backpressure policy** khi collector/backend bị quá tải.

Khi vi phạm quota, nên có **dropped-data counters và cảnh báo** theo owner. Nếu silent drop, dashboard có thể hiển thị hệ thống “khỏe” chỉ vì telemetry bị loại bỏ.

Cần chính sách riêng cho **audit/security records bắt buộc**. Không được dùng cơ chế sample ngẫu nhiên để lách ngân sách lưu trữ hoặc phá nghĩa vụ lưu vết.

## 25. Quan sát chính observability pipeline

Telemetry pipeline cũng là một hệ phân tán và cần có tín hiệu sức khỏe của chính nó:

| Thành phần | Tín hiệu nên theo dõi |
|---|---|
| **Application SDK** | lỗi export, dropped spans/logs, exporter queue size |
| **Collector** | received/accepted/refused/dropped items, CPU/RAM, queue utilization, send failures |
| **Scraper/TSDB** | scrape duration/failures, active series, samples ingested, WAL/compaction, query latency |
| **Remote write** | backlog, retries, failed samples, egress |
| **Log backend** | bytes ingest, index growth, query latency, retention processing |
| **Trace backend** | spans/trace ingest, tail-sampling decisions, storage usage, trace lookup success |
| **Cost** | cost/service/day, cost per million requests, budget variance |

Ví dụ khi exporter queue bị đầy, một đợt network outage có thể khiến **metrics mới không còn đủ**, trong khi hệ thống nghiệp vụ vẫn có lỗi thực tế. Dashboard phải có tín hiệu về **telemetry coverage/quality**; không nên kết luận “0 errors” nếu nguồn dữ liệu không scrape được.

Cần đặt alert cho **loss of observability**: scrape target missing, dữ liệu không cập nhật, trace spans bị drop nhiều, collector queue gần đầy. Các alert này nên độc lập với một backend duy nhất nếu sự cố của backend có thể làm mất chính cảnh báo.

## 26. Kịch bản sự cố minh họa: Bùng nổ label từ Order API

Một thay đổi code đưa order ID vào metric:

~~~text
order_processing_duration_seconds{
  service="order",
  order_id="ORD-1001",
  status="success"
}
~~~

Khi traffic tăng, mỗi đơn tạo series mới. TSDB có thể tăng bộ nhớ, ingestion và index nhanh; pod workload cũng tạo nhiều meter. Dashboard và cảnh báo bị chậm trong khi **thông số lỗi nghiệp vụ thực tế không tăng**.

**Cách xử lý trong incident:**

1. Xác định metric family/label tăng cardinality qua TSDB stats hoặc query giới hạn theo metric/service.
2. Tìm thay đổi instrumentation và ngăn tiếp tục tạo series mới ở source.
3. Thay **order_id** bằng các dimension bounded như **operation=checkout** và **result=success/failure**.
4. Lưu order_id có kiểm soát trong logs/traces, liên kết bằng traceId.
5. Điều chỉnh metric relabel/filter trước ingestion nếu cần containment khẩn cấp, hiểu rằng mất một số metric sẽ ảnh hưởng dashboard.
6. Theo dõi active series/churn và ingestion ổn định lại; dữ liệu lịch sử cần thời gian/retention để rời index/backend.
7. Bổ sung guardrail/cardinality budget để ngăn lặp.

**Cảnh báo:** Chỉ tăng CPU/RAM TSDB mà không sửa label tạo từ request sẽ tiếp tục tốn chi phí theo số đơn hàng và tăng khả năng gây outage quan sát hệ thống.

## 27. Kịch bản sự cố: Trace sampling làm mất lỗi hiếm

Payment Service có lỗi chỉ xảy ra với 0,01% request. Hệ thống dùng 1% head sampling. Khi điều tra, dashboards metrics thấy lỗi nhưng backend trace không có một trường hợp tương ứng.

Phân tích:

- Metric counter vẫn có thể đo lỗi đầy đủ nếu instrument đúng.
- Head sampling 1% khiến xác suất giữ từng trace lỗi rất thấp.
- Nếu phần lớn lỗi nằm ở flow hiếm, một số tag độc lập của trace có thể cần chính sách ưu tiên, nhưng tại đầu request chưa biết lỗi sẽ xảy ra.
- Tail sampling giữ error/slow traces có thể phù hợp hơn, nhưng đòi hỏi collector capacity và trace-aware routing.
- Log lỗi có traceId không đảm bảo trace được giữ; cần kế hoạch fallback điều tra bằng logs và audit.

Giải pháp có thể là tăng sampling cho payment flow quan trọng, triển khai tail sampler với resource guardrails, giữ sự kiện lỗi có cấu trúc, và kiểm tra **tỷ lệ trace lỗi được giữ**. Không nên lấy tỷ lệ lỗi từ các traces đã sampling ưu tiên lỗi.

## 28. Kiểm thử và kiểm toán ngân sách

| Tình huống kiểm thử | Kết quả mong đợi |
|---|---|
| Gửi 100.000 order IDs khác nhau | Số time series application metrics không tăng theo order_id |
| Gọi /orders/{id} với hàng nghìn URL | Tất cả được group theo route template |
| Một header tùy ý chứa chuỗi ngẫu nhiên | Không đưa header thành metric label |
| Scale từ 5 lên 50 Pod | Chi phí tăng theo target có giới hạn, không có nhãn vô tận |
| 1.000 Pod thay tên sau rollout | Theo dõi churn và giới hạn retention chi tiết Pod |
| Bật 20 histogram buckets cho 100 route | Cardinality dự báo khớp tương đối với thực tế |
| SDK 10% head sampling | Kiểm tra phân phối và trace continuity khi qua nhiều service |
| Tail sampler giữ error traces | Tăng coverage cho lỗi; collector không vượt memory budget |
| Tail sampler thiếu một phần spans | Có tín hiệu incomplete traces, không im lặng coi trace đầy đủ |
| Debug logging bật khi incident | Có thời hạn, rate limit và theo dõi bytes ingest |
| Một service phát 5 KB body per request | Redaction/size guard chặn rò rỉ và chi phí |
| Log/trace backend quá quota | Dropped data được đếm và cảnh báo |
| Backend metrics không nhận scrape | Dashboard cho biết data missing, không hiển thị sai là 0 |
| Retention high-resolution hết hạn | Long-term aggregate vẫn phục vụ báo cáo đã thiết kế |
| Multitenant workload tăng traffic 10 lần | Quota, budget và chargeback làm rõ tác động |
| Audit event xuất hiện | Không bị probabilistic sampling làm mất record bắt buộc |

Kiểm thử cả **load thông thường**, **traffic burst**, **lỗi hàng loạt**, **rollout**, **collector restart** và **backend unavailable**. Chỉ so dung lượng sau một ngày yên bình không cho biết telemetry có chịu được lúc sự cố xảy ra hay không.

## 29. Checklist thiết kế trước khi đưa vào production

1. **Mỗi metric có mục đích rõ không?** Nó phục vụ alert, SLO, capacity hay điều tra?
2. **Label values có bounded không?** Có loại trừ user_id, order_id, raw URL, trace_id và input tùy ý?
3. **Đã tính series budget chưa?** Có tính method/status/instance và histograms buckets?
4. **Có quan sát series churn không?** Đặc biệt với Pod, job và task IDs?
5. **Metrics SLO có được đếm đầy đủ không?** Tránh suy ra tỷ lệ lỗi từ traces biased sampling.
6. **Traces cần head hay tail sampling?** Có mục tiêu giữ lỗi/chậm và bảo vệ collector khi outage?
7. **Có propagate trace context đúng không?** Có policy cho untrusted external sampling headers?
8. **Logs có phân cấp severity không?** Có rate limit, data redaction và phân tách audit?
9. **Có kiểm soát payload, attributes và index không?** Không lưu body/PII mặc định.
10. **Retention hot/warm/cold được định nghĩa chưa?** Có phù hợp SLO và nhu cầu điều tra không?
11. **Có cost model thực đo không?** Samples, active series, ingest bytes, stored bytes, query, replicas?
12. **Có quota theo owner/team/tenant không?** Có báo rõ khi vượt ngưỡng?
13. **Observability pipeline tự được quan sát không?** Có biết bao nhiêu dữ liệu bị drop/sample?
14. **Có quy trình incident thay đổi sampling tạm thời không?** Có thời hạn, quyền và audit?
15. **Đã test cardinality explosion và collector/backend overload chưa?** Có rollback instrumentation được không?

## 30. Kết luận

**Cardinality, sampling và retention là ba nút điều chỉnh khác nhau:**

- **Cardinality control** giữ số lượng series có thể quản lý bằng cách chọn labels bounded, chuẩn hóa route và hạn chế churn.
- **Sampling** giảm khối lượng traces/logs có lựa chọn; phải hiểu thiên lệch thống kê, khả năng mất rare events và giới hạn collector.
- **Retention, aggregation và storage tiers** quyết định dữ liệu nào còn khả dụng sau nhiều ngày/tháng và chi phí truy vấn/lưu trữ tương ứng.

Một hệ thống quan sát tốt không nhất thiết thu thập tất cả dữ liệu. Nó giữ **đủ bằng chứng để xác định có sự cố, tìm phạm vi, khoanh vùng nguyên nhân và đánh giá SLO**, đồng thời có giới hạn rõ để observability không trở thành nguồn gây outage hoặc chi phí không kiểm soát.

**Câu hỏi tự kiểm tra:** *Nếu số lượng user/order tăng 100 lần nhưng số service/route không đổi, chi phí metrics có tăng gần 100 lần không? Nếu xảy ra một lỗi hiếm, chính sách sampling có giữ được chứng cứ cần thiết không? Nếu collector bị quá tải, ai sẽ biết dữ liệu đang bị bỏ?*

Trả lời được ba câu hỏi đó bằng thiết kế, cấu hình và phép đo thực tế là nền tảng của observability bền vững trong microservices.
