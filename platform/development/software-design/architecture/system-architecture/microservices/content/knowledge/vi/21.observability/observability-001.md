# Phân biệt nhật ký, chỉ số và dấu vết phân tán trong Microservices

Trong microservices, một thao tác đơn giản như “đặt hàng” có thể đi qua API Gateway, Order Service, Inventory Service, Payment Service, message broker và Notification Service. Khi người dùng báo yêu cầu chậm hoặc thất bại, đội vận hành phải trả lời nhiều câu hỏi: hệ thống đang bị ảnh hưởng đến mức nào, bước nào chậm, và điều gì đã xảy ra trong một yêu cầu cụ thể?

Ba loại dữ liệu quan sát cốt lõi là **logs (nhật ký)**, **metrics (chỉ số)** và **distributed traces (dấu vết phân tán)**. Chúng bổ sung cho nhau:

- **Metrics:** xu hướng và mức độ — có bao nhiêu yêu cầu, lỗi tăng từ khi nào, p95 latency thay đổi ra sao, service nào gần cạn tài nguyên.
- **Traces:** hành trình và mối quan hệ — một yêu cầu đã đi qua những service/span nào, khoảng thời gian dành cho từng bước, phụ thuộc nào trở thành nút thắt.
- **Logs:** chi tiết sự kiện — tại một thời điểm service đã ghi nhận trạng thái, quyết định, ngoại lệ hoặc sự kiện nghiệp vụ gì.

Không loại dữ liệu nào thay thế hoàn toàn hai loại còn lại. Quan sát hệ thống tốt cho phép bắt đầu từ tín hiệu tổng quan, thu hẹp đến yêu cầu bất thường và tìm được chi tiết đủ để xử lý sự cố.

## 1. Observability là gì và khác monitoring như thế nào?

**Monitoring** thường trả lời các câu hỏi đã được xác định trước: CPU có vượt ngưỡng không, API có còn chạy không, tỷ lệ lỗi có tăng không? **Observability** chú trọng khả năng suy ra trạng thái bên trong của một hệ thống từ tín hiệu mà hệ thống phát ra, kể cả khi câu hỏi phát sinh trong một tình huống chưa từng dự đoán.

Ví dụ:

- Monitoring phát cảnh báo: tỷ lệ lỗi đặt hàng tăng trong 5 phút.
- Metrics cho biết lỗi tập trung ở endpoint tạo đơn, tại khu vực triển khai cụ thể.
- Trace cho thấy đa số yêu cầu lỗi đều chậm ở lời gọi Inventory Service.
- Log có trace ID tương ứng ghi nhận timeout khi chờ cơ sở dữ liệu hoặc việc giữ hàng bị từ chối theo quy tắc nghiệp vụ.

Observability không phải việc “thu thập thật nhiều dữ liệu”. Cần xây các tín hiệu có **ngữ nghĩa, phạm vi, liên kết, độ tin cậy và thời gian lưu** phù hợp để điều tra có thể lặp lại.

Một yêu cầu kỹ thuật quan trọng: cần thống nhất định danh service, môi trường, phiên bản triển khai, tên hoạt động và quy tắc gắn trace ID, span ID hoặc correlation ID. Không có ngữ cảnh chung, ba kho dữ liệu dễ trở thành ba hệ thống rời rạc.

## 2. Nhìn nhanh: logs, metrics và traces khác nhau ở đâu?

| Góc nhìn | Logs — nhật ký | Metrics — chỉ số | Traces — dấu vết phân tán |
| --- | --- | --- | --- |
| Đơn vị cơ bản | Một bản ghi sự kiện | Một giá trị số có timestamp và tập nhãn | Một trace gồm các span liên quan đến một luồng xử lý |
| Câu hỏi mạnh nhất | Điều gì đã xảy ra tại đây? | Tình trạng xảy ra bao nhiêu, thường xuyên và thay đổi thế nào? | Yêu cầu này đã đi qua đâu, bước nào tốn thời gian? |
| Ví dụ | “Không giữ được hàng vì hết tồn kho” | Tỷ lệ lỗi, request/s, CPU, độ trễ p95 | Gateway → Order → Inventory → DB |
| Ngữ cảnh | Message, severity, fields, error code, trace ID | Metric name, đơn vị, nhãn, giá trị | Trace ID, span ID, parent/link, duration, attributes, events |
| Phân tích phù hợp | Tìm sự kiện và nguyên nhân cụ thể | Dashboard, SLI/SLO, trend và cảnh báo | Phân tích đường đi, critical path, dependency, waterfall |
| Chi phí/rủi ro thường gặp | Lượng lớn, dữ liệu nhạy cảm trong message | Cardinality nhãn bùng nổ | Lưu lượng span lớn, sampling làm thiếu request |
| Giới hạn | Khó suy ra toàn cảnh nếu log thiếu hoặc không chuẩn | Không thấy đầy đủ chi tiết từng request | Không phải mọi span đều được lưu; thiếu ngữ nghĩa nghiệp vụ nếu instrumentation kém |

Cách ghi nhớ thực tế: **metrics cho biết có vấn đề và ảnh hưởng ra sao; traces giúp khoanh vùng đường đi; logs mô tả sự kiện cụ thể để giải thích và xử lý**. Trong thực tế có thể bắt đầu từ log hoặc trace tùy tín hiệu ban đầu, không bắt buộc một quy trình cứng.

## 3. Logs: bản ghi các sự kiện và quyết định

Một log là sự kiện được ghi bởi ứng dụng hoặc hạ tầng tại một thời điểm. Log hữu ích khi thông tin cần giữ lại không thể biểu diễn đầy đủ bằng một con số.

Ví dụ trong Order Service:

~~~json
{
  "timestamp": "2026-11-12T02:10:15.421Z",
  "level": "WARN",
  "service": "order-service",
  "environment": "production",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "event": "inventory_reservation_failed",
  "order_ref": "safe-non-sensitive-reference",
  "dependency": "inventory-service",
  "error_code": "RESERVATION_TIMEOUT",
  "elapsed_ms": 210,
  "message": "Inventory reservation did not complete within deadline"
}
~~~

Đây là **structured logging**: một bản ghi có trường ổn định, máy có thể phân tích. Nó hữu ích hơn việc ghép tất cả dữ liệu vào một chuỗi văn bản tùy ý, vì có thể lọc theo service, error_code, trace_id và khoảng thời gian.

Các trường thường có ích:

- Timestamp thống nhất (ưu tiên UTC với độ chính xác phù hợp); môi trường, tên service, instance/host khi cần.
- Severity: TRACE/DEBUG/INFO/WARN/ERROR theo quy ước đội phát triển.
- Tên sự kiện hoặc error code **ổn định**, không phụ thuộc câu chữ message.
- Trace ID, span ID; request/correlation ID nếu kiến trúc có định danh riêng.
- Tên dependency, operation, kết quả, thời gian đã dùng, số lần retry khi thật sự liên quan.
- Thông tin phiên bản phát hành, vùng triển khai và tenant dạng đã kiểm soát quyền nếu cần điều tra.

### 3.1. Khi nào nên ghi log?

Ghi log ở các ranh giới có giá trị điều tra: nhận/hoàn tất thao tác quan trọng, quyết định nghiệp vụ bất thường, chuyển trạng thái, retry đã thực hiện, timeout, exception, fallback, giao dịch chưa rõ kết quả, từ chối truy cập cần audit. Có thể log INFO cho các mốc đáng chú ý, WARN cho sự cố có thể phục hồi và ERROR cho lỗi ảnh hưởng kết quả hoặc cần xử lý.

Không nên ghi một dòng INFO cho mọi vòng lặp, mỗi lần truy cập getter hay mọi thao tác nội bộ ở tần suất cao; điều đó có thể làm tăng chi phí, che tín hiệu cần thiết và ảnh hưởng hiệu năng.

**Phân biệt application log và audit log.** Application log phục vụ vận hành, thường có mức chi tiết thay đổi theo cấu hình. Audit log phục vụ truy vết ai làm gì, thời gian nào, đối tượng nào, kết quả nào; thường cần bảo toàn tính toàn vẹn, chính sách truy cập và thời hạn lưu riêng. Không mặc định log ứng dụng có thể thay thế audit trail.

### 3.2. Ghi cấu trúc và tránh dữ liệu nhạy cảm

Không ghi mật khẩu, access token, Authorization header, session cookie, private key, số thẻ, dữ liệu định danh cá nhân không cần thiết, nội dung request/response nhạy cảm hoặc SQL có chứa bí mật. Lỗi HTTP đôi khi vô tình log URL query string hoặc payload; cần có chính sách masking/redaction ngay ở điểm sinh log và tại pipeline thu thập.

Log có thể chứa dữ liệu do người dùng nhập. Khi hiển thị trong hệ thống tra cứu, phải xử lý an toàn việc xuống dòng, ký tự điều khiển, log forging hoặc nội dung có thể gây hiểu lầm. Trace ID là mã tương quan, **không phải bằng chứng người gọi đã được phân quyền**.

### 3.3. Tại sao chỉ dựa vào log thường chưa đủ?

- Có thể phải truy vấn hàng triệu bản ghi để thấy một thay đổi nhỏ trong tỷ lệ lỗi.
- Một yêu cầu xuyên service sẽ tạo log ở nhiều nơi; thiếu trace ID hoặc time sync khiến việc ghép thủ công khó khăn.
- Log có thể bị mất khi ứng dụng crash, buffer chưa flush, pipeline nghẽn hoặc hệ thống cắt giảm tải.
- Không thể dễ dàng tính percentile latency chính xác nếu log không có cấu trúc hoặc thiếu dữ liệu.
- Log message tự do thay đổi khi refactor, làm dashboard và rule truy vấn dựa trên câu chữ dễ hỏng.

Bởi vậy logs phù hợp để giữ **sự kiện có ý nghĩa**, còn metrics và traces bổ sung góc nhìn khác.

## 4. Metrics: đo sức khỏe và biến động theo thời gian

Metric là giá trị số được hệ thống đo tại các thời điểm hoặc khoảng thời gian. Chỉ số có thể thu thập từ ứng dụng, runtime, cơ sở dữ liệu, queue, OS và hạ tầng.

Ví dụ:

~~~text
http_requests_total{service="order",route="/orders",method="POST",status_class="5xx"} 93
http_request_duration_seconds_bucket{service="order",route="/orders",le="0.25"} 18247
jvm_memory_used_bytes{service="order",area="heap"} 378535936
queue_messages_ready{service="notification"} 421
~~~

Tên và nhãn chỉ là **ví dụ minh họa**; mỗi framework/exporter có thể đặt tên khác nhau. Các giá trị trên cần được diễn giải cùng loại metric, đơn vị, nhãn và thời gian thu thập.

### 4.1. Những loại metric cơ bản

**Counter:** tổng tích lũy đơn điệu trong vòng đời một process, như số request, số lỗi, số retry, số job hoàn tất. Trong hệ thống giám sát, thường xem tốc độ tăng theo khoảng thời gian vì counter có thể reset khi process restart.

**Gauge:** giá trị có thể tăng hoặc giảm, như số kết nối đang hoạt động, độ dài queue, bộ nhớ đang dùng, số worker đang xử lý.

**Histogram:** đếm số lần quan sát nằm trong các bucket, thường dùng cho độ trễ hoặc kích thước payload. Có thể tính tỷ lệ dưới ngưỡng và ước lượng percentile từ histogram tương thích.

**Summary hoặc các dạng phân phối khác:** cung cấp thống kê tùy hệ thống đo. Quantile tính ở client không thể luôn gộp trực tiếp giữa các instance; cần nắm khả năng và giới hạn của kiểu dữ liệu trước khi tổng hợp.

Đơn vị phải rõ: second so với millisecond, byte so với kilobyte, counter tích lũy so với rate. Nếu đổi đơn vị mà không đổi quy ước, biểu đồ sẽ cho kết quả sai.

### 4.2. Bốn tín hiệu vàng và hai mô hình phổ biến

Đối với dịch vụ cung cấp API, có thể bắt đầu từ **four golden signals**:

1. **Latency:** thời gian phục vụ yêu cầu; nên phân biệt các yêu cầu thành công và thất bại khi có ý nghĩa.
2. **Traffic:** lượng nhu cầu như request/s, message/s hoặc transaction/s.
3. **Errors:** tỷ lệ thao tác không đáp ứng hợp đồng thành công của dịch vụ.
4. **Saturation:** mức độ tài nguyên hoặc hàng đợi tiến sát giới hạn, ví dụ thread pool, CPU, connection pool, queue depth.

Mô hình **RED** cho service/request: *Rate, Errors, Duration*. Mô hình **USE** cho tài nguyên: *Utilization, Saturation, Errors*. Đây là khung khởi đầu, không thay thế chỉ số nghiệp vụ.

Ví dụ checkout có tỷ lệ HTTP 200 cao nhưng số thanh toán ở trạng thái PENDING tăng: chỉ nhìn request rate và HTTP error rate chưa đủ; cần metric cho kết quả nghiệp vụ như checkout_completed_total, payment_pending_total và tuổi tác vụ chờ.

### 4.3. Các nhãn metric và bẫy cardinality

Một time series được xác định bởi **tên metric + tổ hợp giá trị nhãn**. Nếu gắn user_id, order_id, trace_id hoặc URL path chứa ID cụ thể vào metric, số time series có thể tăng theo từng người dùng hoặc từng request.

Ví dụ không nên:

~~~text
request_total{user_id="u-928821",order_id="o-123456789",path="/orders/123456789"} 1
~~~

Ví dụ phù hợp hơn:

~~~text
request_total{service="order",route="/orders/{id}",method="GET",status_class="2xx"} 18200
~~~

Các nhãn thường an toàn hơn khi có tập giá trị hữu hạn: service, environment, route template, method, status class, dependency, outcome. Tuy nhiên **tích số lượng giá trị trên tất cả nhãn** vẫn có thể lớn; phải đánh giá cardinality tổng thể.

Trace ID hoặc ID nghiệp vụ cụ thể phù hợp để tìm log/trace của một yêu cầu, nhưng thường không phù hợp làm metric label. Khi cần đo theo tenant với số lượng rất lớn, cân nhắc các nhóm được kiểm soát hoặc kỹ thuật tổng hợp khác.

### 4.4. Đọc metric đúng cách

- Counter tổng số request tăng tự nhiên; để đánh giá lưu lượng, dùng rate hoặc delta với cơ chế xử lý reset.
- p95 latency nghĩa là khoảng 95% quan sát không vượt ngưỡng percentile đã ước tính trong cửa sổ và tập dữ liệu đang xét; nó không phải “95% requests đều nhanh như trung bình”.
- Giá trị trung bình có thể che đuôi phân phối; quan sát p50, p95, p99 hoặc tỷ lệ đạt ngưỡng tùy SLI.
- Không lấy trung bình đơn giản các giá trị p95 của từng instance rồi gọi đó là p95 toàn hệ thống. Nếu có histogram bucket tương thích, tổng hợp bucket rồi mới tính percentile.
- Một tỷ lệ lỗi bằng 0 với chỉ vài request có độ tin cậy và mức ưu tiên khác một tỷ lệ lỗi bằng 0 với hàng triệu request.
- Metrics đã tổng hợp thành công có thể che phân khúc bị lỗi: cần phân nhóm hợp lý theo route, region, release, dependency mà vẫn kiểm soát cardinality.

### 4.5. Truy vấn PromQL minh họa

Nếu exporter cung cấp counter và histogram theo tên như bên dưới, có thể tính request rate:

~~~promql
sum by (service, route) (
  rate(http_requests_total[5m])
)
~~~

Tính tỷ lệ server error, với điều kiện metric dùng nhãn status_class như ví dụ:

~~~promql
sum(rate(http_requests_total{service="order",status_class="5xx"}[5m]))
/
clamp_min(
  sum(rate(http_requests_total{service="order"}[5m])),
  1e-9
)
~~~

Ước lượng p95 latency theo route khi có histogram bucket:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, route) (
    rate(http_request_duration_seconds_bucket{service="order"}[5m])
  )
)
~~~

Đây là mẫu cú pháp theo **histogram bucket kiểu Prometheus truyền thống**, không phải câu truy vấn áp dụng nguyên xi cho mọi loại histogram hoặc exporter. Các bucket phải tương thích và phép tổng hợp phải giữ nhãn le. Kích thước cửa sổ, cách xử lý thiếu dữ liệu và định nghĩa lỗi cần phù hợp lưu lượng thực.

## 5. Distributed traces: lần theo hành trình của một yêu cầu

Một **trace** thể hiện đường đi của một luồng xử lý logic. Trace thường gồm nhiều **span**. Mỗi span biểu diễn một thao tác có thời điểm bắt đầu/kết thúc, duration, thuộc tính và quan hệ với span khác.

- **Trace ID:** nhận diện một trace, giúp liên kết các span trong nhiều service.
- **Span ID:** nhận diện một span cụ thể.
- **Parent span ID:** cho biết span nào trực tiếp gọi hoặc bao trùm span hiện tại trong quan hệ cha–con.
- **Span attributes:** ngữ cảnh có cấu trúc như service.name, HTTP method, route template, db.system, messaging operation.
- **Span events/status:** các mốc và kết quả quan trọng, lỗi hoặc exception được ghi nhận phù hợp.

Một trace checkout có thể nhìn như sau:

~~~text
Trace: checkout request (tổng 780 ms)

API Gateway: POST /orders                  [============================] 780 ms
  Order Service: createOrder                  [=========================] 720 ms
    Inventory Client: reserve                 [=========]               240 ms
      Inventory Service: reserve                [=======]               205 ms
        Inventory DB: update                     [=====]                150 ms
    Payment Client: authorize                                [========] 280 ms
      Payment Service: authorize                                [=====] 215 ms
    Order DB: save                                                [===] 90 ms
  Response mapping                                                         20 ms
~~~

Các số chỉ minh họa và không nhằm thể hiện tính chính xác của một waterfall thật. Một trace thực tế có thể chứa span chạy **song song**, overhead mạng, xử lý không có span và thời gian chờ giữa các bước.

Trace giúp điều tra “200 ms này nằm ở client hay server?”, “Có retry khiến Payment được gọi nhiều lần không?”, “Inventory DB là nút thắt hay queueing trước khi gọi?”, “Một release mới có làm tăng số lần gọi chéo service không?”.

### 5.1. Trace context đi qua service thế nào?

Để ghép span giữa nhiều service, các thành phần phải **truyền context**, không chỉ tạo span cục bộ. Với HTTP, chuẩn W3C Trace Context có header traceparent và có thể có tracestate. Một traceparent minh họa:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Một HTTP client đã được instrument có thể chèn trace context vào request outbound; server nhận context để tạo span con. Trong cùng process, context cần đi qua thread pool, asynchronous callback hoặc execution context tương ứng.

Không tự tạo một trace ID mới tại **mỗi service** rồi kỳ vọng tracing tự ghép được. Nếu context không truyền sang dịch vụ tiếp theo, trace có thể bị tách rời.

Không nhầm trace context với cơ chế xác thực: **traceparent không phải token phân quyền**. Tại biên Internet cần kiểm soát trust boundary, giới hạn header và cách tiếp nhận/truyền context từ bên ngoài; không dùng trace ID do client cung cấp làm bằng chứng danh tính.

### 5.2. Tracing với message broker và tác vụ bất đồng bộ

Trong microservices, luồng xử lý không chỉ có HTTP request trực tiếp. Order Service có thể publish OrderCreated qua Kafka/RabbitMQ; Notification Service xử lý vài giây sau.

~~~text
HTTP POST /orders
   └── Order Service: persist order
       └── Producer: publish OrderCreated
             ... broker / queue / delay ...
                 Consumer: handle OrderCreated
                   └── Notification: send
~~~

Nếu công cụ hỗ trợ, producer đưa trace context vào **message headers**; consumer lấy context và tạo span phù hợp. Với batch, fan-in/fan-out hoặc consumer xử lý theo lịch, mô hình **span links** có thể phù hợp hơn áp một parent giả; không nhất thiết mọi tác vụ async phải là một cây cha–con duy nhất.

Cần quan sát cả **queueing delay**, thời gian xử lý, số lần retry, DLQ, consumer lag và trạng thái ack. Chỉ nhìn latency HTTP có thể bỏ sót thời gian ở hàng đợi.

### 5.3. Sampling và những điều trace không thể khẳng định

Lưu mọi span trong hệ thống lớn có thể tốn tài nguyên và chi phí. Một số chiến lược:

- **Head-based sampling:** quyết định có lấy mẫu gần lúc trace bắt đầu, chi phí thường dễ kiểm soát hơn nhưng có thể bỏ lỡ request lỗi hiếm.
- **Tail-based sampling:** xem kết quả/đặc điểm trace rồi mới quyết định giữ, giúp ưu tiên trace chậm hoặc lỗi nhưng cần buffering, bộ xử lý và tài nguyên phù hợp.
- **Policy sampling:** giữ trace quan trọng theo lỗi, latency, route hoặc nghiệp vụ, đồng thời lấy mẫu một phần lưu lượng bình thường.

Với trace đã được sample, **không lấy số trace quan sát được làm số request thực tế** nếu chưa hiểu chính sách lấy mẫu. Metrics đo độc lập là nguồn phù hợp hơn để tính rate/error rate tổng thể. Không có trace trong kho lưu trữ không chứng minh request đó chưa từng xảy ra.

Tracing phụ thuộc instrumentation. Một span bị thiếu có thể là do chưa instrument, context bị mất hoặc sampling, không nhất thiết service đã bỏ qua thao tác.

## 6. Ba tín hiệu cùng một sự cố: ví dụ checkout

Giả sử 09:00 hệ thống hoạt động bình thường; 09:10 phiên bản Inventory Service mới được triển khai; 09:13 người dùng bắt đầu báo checkout chậm.

**Metric phát hiện vấn đề:**

~~~text
checkout_requests_total rate: gần như không đổi
checkout_errors_total rate: tăng mạnh ở một region
checkout_duration p95: từ 320 ms lên khoảng 2.1 s
inventory_client_timeout_total: tăng
inventory_database_connection_active: gần ngưỡng pool
~~~

Thông tin này cho biết **phạm vi và thời gian** sự cố; chưa đủ để khẳng định nguyên nhân gốc.

**Trace thu hẹp nút thắt:**

~~~text
gateway POST /checkout                2130 ms
  order.validate                       25 ms
  inventory.reserve                  1800 ms
    inventory.db.acquire_connection  1420 ms
    inventory.db.update               280 ms
  order.map_error                      10 ms
~~~

Trace cho thấy phần lớn thời gian nằm ở việc chờ lấy connection trong Inventory, khác với suy đoán “database query chạy chậm”.

**Log giải thích chi tiết:**

~~~json
{
  "level": "WARN",
  "service": "inventory-service",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "event": "db_pool_acquire_timeout",
  "pool": "inventory-writer",
  "wait_ms": 1400,
  "error_code": "DB_POOL_EXHAUSTED"
}
~~~

Khi nối ba loại dữ liệu, nhóm điều tra có căn cứ để kiểm tra thay đổi connection pool, giao dịch kéo dài và số lượng truy vấn đồng thời của phiên bản vừa triển khai. Chỉ dựa vào một log “timeout” thì dễ kết luận sai rằng lỗi nằm ở mạng hoặc Inventory server bị chết.

## 7. Thiết kế tương quan giữa logs, metrics và traces

Mục tiêu là đi từ một dashboard đến trace cụ thể, rồi tới log của các span quan trọng mà không phải đoán theo thời gian.

### 7.1. Danh tính và metadata chung

Các trường thường xuyên dùng xuyên pipeline:

| Trường | Dùng để làm gì? | Lưu ý |
| --- | --- | --- |
| service.name | Xác định service phát telemetry | Thống nhất naming giữa log, metric và trace |
| deployment.environment | Tách production/staging | Không trộn kết quả SLO của các môi trường |
| service.version / release | Liên hệ với lần triển khai | Giúp so sánh trước/sau rollout |
| trace_id | Ghép log với trace của yêu cầu | Tránh dùng làm metric label |
| span_id | Liên hệ log với thao tác trong trace | Không phải ID bảo mật |
| route template | Tổng hợp metric theo chức năng | Dùng /orders/{id}, tránh URL chứa ID thật |
| dependency / outcome | Xác định lỗi ở ranh giới nào | Quy ước error code, status, fallback rõ |

Resource attributes và semantic conventions trong hệ sinh thái telemetry giúp có tên trường nhất quán; các công cụ và phiên bản có thể khác nhau nên cần quy ước xuất dữ liệu cụ thể trong dự án.

### 7.2. Correlation ID và trace ID

**Correlation ID/request ID** có thể được hệ thống tự định nghĩa để theo dõi yêu cầu nghiệp vụ hoặc một interaction xuyên hệ thống. **Trace ID** thuộc hệ thống distributed tracing. Chúng đôi khi trùng vai trò trong HTTP đồng bộ, nhưng không nên xem là đồng nhất mặc định.

Ví dụ một đơn hàng có thể được xử lý qua nhiều request, nhiều retry hoặc nhiều trace async. Business order ID giúp liên hệ các thao tác nghiệp vụ theo chính sách bảo mật; trace ID giúp nối các span trong một luồng thực thi; correlation ID có thể đại diện một workflow rộng hơn. Nếu định danh nghiệp vụ nhạy cảm, phải cân nhắc masking, quyền tra cứu và retention.

### 7.3. Clock và thời gian

Các máy cần đồng bộ thời gian đủ tốt bằng dịch vụ thời gian đáng tin cậy. Timestamp log sai lệch có thể làm sự kiện xuất hiện không đúng thứ tự; span duration thường nên được đo bằng đồng hồ phù hợp với khoảng thời gian trong process. Chỉ kết luận thứ tự giữa các dịch vụ khi đã xét độ lệch đồng hồ và tính chất xử lý async.

### 7.4. Tính nhất quán khi propagating context

Các điểm dễ làm mất trace context:

- Executor/thread pool tự tạo mà không truyền execution context.
- CompletableFuture, callback, scheduled task hoặc reactive pipeline không dùng instrumentation phù hợp.
- HTTP client khác loại chưa được auto-instrument.
- Message producer/consumer bỏ qua headers.
- Proxy/gateway xóa hoặc thay header context.
- Retry hoặc fallback tạo operation ngoài span gốc mà không liên kết.

Không ép mọi thông tin vào một ThreadLocal dùng chung; với asynchronous/reactive execution, context phải được truyền theo cơ chế đúng của framework.

## 8. Kiến trúc thu thập telemetry trong microservices

Một pipeline tham khảo:

~~~text
                          +--> Metrics backend --> Dashboards / alerts
Application services -----|
  - structured logs       +--> Log backend -----> Search / retention
  - counters/histograms   |
  - instrumented spans    +--> Trace backend ---> Service map / waterfall
           |
   SDK / agents / exporters
           |
      OpenTelemetry Collector
      (receivers, processors, exporters)
           |
  Filtering / batching / sampling /
  resource metadata / redaction
~~~

Sơ đồ là kiến trúc logic. Trong triển khai thực tế, logs có thể đi qua stdout/agent riêng, metrics được scrape bằng Prometheus, traces được gửi OTLP và Collector có nhiều instance. Không cần ép mọi tín hiệu vào một đường truyền nếu mục tiêu độ tin cậy, chi phí hoặc công cụ yêu cầu khác.

**OpenTelemetry (OTel)** cung cấp hệ sinh thái API, SDK, instrumentation và giao thức thu thập telemetry, giúp giảm phụ thuộc vào một backend cụ thể. OTel không tự động tạo ra câu trả lời nghiệp vụ: đội phát triển vẫn phải đặt tên operation, chọn nhãn, giới hạn dữ liệu nhạy cảm và định nghĩa SLI/SLO.

### 8.1. Các lớp chịu trách nhiệm

**Ứng dụng/instrumentation:** định nghĩa sự kiện và operation có nghĩa, thu thập HTTP client/server, DB và message broker, phát log có correlation context.

**Collector/agent:** nhận, lọc, batch, thêm metadata, định tuyến và xuất dữ liệu; cần cấu hình giới hạn bộ nhớ, queue, retry và sampling phù hợp.

**Backend:** lưu trữ, lập chỉ mục, truy vấn, retention, tổ chức quyền truy cập và dashboard.

**Alerting/on-call:** biến tín hiệu thành cảnh báo có hành động, có người chịu trách nhiệm và runbook.

Pipeline telemetry cũng là một phần hệ thống phân tán: có thể bị nghẽn, drop, retry hoặc ngừng hoạt động. Cần giám sát **chính pipeline đó**, ví dụ queue độ sâu, tỷ lệ dữ liệu bị drop, export failure và ingestion lag.

### 8.2. Thu thập không làm ảnh hưởng đường nghiệp vụ

Instrumentation phải giới hạn chi phí. Tránh gửi log hoặc span đồng bộ qua mạng trên critical path của từng request. Dùng batching, backpressure, sampling, rate limit và chính sách drop hợp lý; hiểu rõ nếu phải đánh đổi giữa độ đầy đủ telemetry và sự ổn định của dịch vụ.

Một tác vụ thanh toán không được coi là thành công chỉ vì đã gửi một trace; ngược lại, lỗi collector không nên làm dừng việc lưu giao dịch hợp lệ. Riêng audit event bắt buộc có yêu cầu bền vững riêng và phải thiết kế luồng đó độc lập với log ứng dụng “best effort”.

## 9. Triển khai trong Java / Spring Boot

Trong hệ sinh thái Spring Boot, **Micrometer** thường dùng để phát metrics, còn **Micrometer Observation** có thể tạo điểm quan sát giúp phối hợp metrics/tracing khi được cấu hình các handler tương ứng. OpenTelemetry SDK/agent/instrumentation có thể được dùng cho trace và export tùy cấu hình. Chi tiết dependency hoặc tên metric phụ thuộc phiên bản và runtime; cần kiểm tra tài liệu và cấu hình của hệ thống đang chạy.

### 9.1. Ví dụ business instrumentation bằng Observation

Ví dụ dùng một operation business có tên ổn định và nhãn ít cardinality:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public final class CheckoutService {
    private final ObservationRegistry observations;
    private final OrderProcessor processor;

    public CheckoutService(
        ObservationRegistry observations,
        OrderProcessor processor
    ) {
        this.observations = observations;
        this.processor = processor;
    }

    public CheckoutResult place(CheckoutCommand command) {
        return Observation
            .createNotStarted("checkout.place", observations)
            .lowCardinalityKeyValue("channel", "web")
            .observe(() -> processor.process(command));
    }
}
~~~

Ở đây, OrderProcessor và các record nghiệp vụ là các thành phần minh họa đã được cung cấp bởi ứng dụng. Observation bao quanh thao tác cần theo dõi. Với cấu hình phù hợp, operation có thể đóng góp dữ liệu metrics và trace; **không giả định chỉ khai báo ObservationRegistry là tự có đầy đủ pipeline/exporter**.

Tránh đưa customer ID, order ID, email hay token làm low-cardinality key. Nếu cần tìm một đơn hàng cụ thể, hãy dùng log/trace có kiểm soát quyền hoặc id liên hệ được phép.

### 9.2. Ví dụ metric riêng cho kết quả nghiệp vụ

Giả sử muốn đếm checkout theo kết quả với tập nhãn cố định:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public final class CheckoutMetrics {
    private final Counter completed;
    private final Counter rejected;
    private final Counter pending;

    public CheckoutMetrics(MeterRegistry registry) {
        completed = Counter.builder("checkout_result_total")
            .tag("outcome", "completed")
            .register(registry);
        rejected = Counter.builder("checkout_result_total")
            .tag("outcome", "rejected")
            .register(registry);
        pending = Counter.builder("checkout_result_total")
            .tag("outcome", "pending")
            .register(registry);
    }

    public void record(String outcome) {
        switch (outcome) {
            case "completed" -> completed.increment();
            case "rejected" -> rejected.increment();
            case "pending" -> pending.increment();
            default -> throw new IllegalArgumentException("Unknown outcome");
        }
    }
}
~~~

Metric này mô tả **kết quả nghiệp vụ**, không thay thế số lượng HTTP status code. Một response HTTP 202 có thể chứa checkout PENDING; ứng dụng cần đo riêng và giải thích trạng thái đó.

### 9.3. Log có ngữ cảnh trace

Nhiều giải pháp tracing tích hợp trace ID/span ID vào MDC hoặc logger context. Khi có cấu hình đó, log structured có thể tự thêm trường để tra cứu. Nếu tự thêm MDC ở một đoạn đồng bộ, luôn dọn trạng thái cũ:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

final class PaymentAttemptLogger {
    private static final Logger LOG =
        LoggerFactory.getLogger(PaymentAttemptLogger.class);

    void logTimeout(String safeCorrelationId, long elapsedMs) {
        try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("correlation_id", safeCorrelationId)) {
            LOG.warn(
                "event=payment_timeout elapsed_ms={}",
                elapsedMs
            );
        }
    }
}
~~~

Ví dụ này chỉ minh họa scope MDC và một sự kiện vận hành; nó **không tự tạo distributed trace**. Với thread pool hoặc reactive execution, MDC dạng ThreadLocal có thể không tự đi qua callback; cần tích hợp theo cơ chế context propagation của framework. Không đưa payload thanh toán hoặc credential vào MDC/message.

### 9.4. Instrumentation tự động và thủ công

Auto-instrumentation thường theo dõi server/client HTTP, JDBC, một số messaging framework và runtime với mức chi tiết phụ thuộc công cụ. Manual instrumentation bổ sung tên operation, sự kiện nghiệp vụ và ranh giới không được công cụ tự động hiểu.

Không tạo span cho mỗi dòng code. Span nên biểu diễn thao tác đủ ý nghĩa để phát hiện nút thắt hoặc quan hệ phụ thuộc: gọi một service, xử lý một command, truy cập DB đáng kể, publish/consume một message, thực hiện bước quan trọng trong workflow.

## 10. Từ yêu cầu nghiệp vụ đến dashboard và SLO

Dashboard chỉ hữu ích nếu trả lời câu hỏi về trải nghiệm người dùng và năng lực vận hành. Một trang overview cho Order Service có thể gồm:

| Khối dashboard | Tín hiệu | Hành động hỗ trợ |
| --- | --- | --- |
| Request rate | Số yêu cầu/s theo route | Nhận biết tăng tải hoặc sụt traffic |
| Error rate | Tỷ lệ lỗi theo SLI, route, region | Xác định ảnh hưởng người dùng |
| Latency | p50, p95, p99 hoặc tỷ lệ dưới ngưỡng | Định vị suy giảm hiệu năng |
| Saturation | DB connections, thread pool, CPU, queue | Phát hiện cạn tài nguyên |
| Dependency | Lỗi/timeout/latency khi gọi Inventory, Payment | Khoanh vùng phụ thuộc |
| Business | Tỷ lệ đơn hoàn tất, chờ xử lý, thất bại | Đo kết quả thực thay vì chỉ HTTP |
| Release | Phiên bản và thời điểm deploy | Liên hệ biến động với rollout |

### 10.1. SLI, SLO và error budget

**SLI (Service Level Indicator)** là phép đo chất lượng từ góc nhìn dịch vụ/người dùng, ví dụ phần trăm checkout hợp lệ hoàn thành đúng trong 2 giây. **SLO (Service Level Objective)** là mục tiêu chất lượng trong một cửa sổ, ví dụ một tỷ lệ phần trăm cam kết nội bộ; **error budget** là phần sai lệch cho phép theo mục tiêu đó.

Định nghĩa phải nêu cụ thể:

- Những sự kiện nào thuộc mẫu số: mọi request, hay chỉ request hợp lệ/được phép?
- Thành công nghĩa là HTTP status, kết quả nghiệp vụ hay hoàn thành async?
- Thời gian đo từ đâu đến đâu?
- Trường hợp từ chối nghiệp vụ hợp lệ (hết hàng, input sai) có tính lỗi hệ thống không?
- Phân vùng, nhóm khách hàng và tính năng có cùng SLO hay không?
- Khoảng thời gian đo, dữ liệu thiếu, sampling và độ trễ ingestion được xử lý ra sao?

Ví dụ lỗi do hết hàng theo hợp đồng thông thường có thể là kết quả nghiệp vụ hợp lệ, không phải sự cố hệ thống; Payment Service timeout gây trạng thái không xác định có thể làm người dùng thất bại dù API trả 202. Không định nghĩa SLO chỉ dựa vào mã HTTP mà bỏ qua hành vi nghiệp vụ.

### 10.2. Alert theo tác động

Tránh cảnh báo một CPU spike ngắn khi người dùng không bị ảnh hưởng, trong khi bỏ lỡ lỗi checkout kéo dài. Các cảnh báo nên ưu tiên **SLO burn rate, error rate, latency, backlog và tỷ lệ hoàn tất nghiệp vụ** với thời gian quan sát và ngưỡng hợp lý; cảnh báo hạ tầng đóng vai trò gợi ý nguyên nhân hoặc phòng ngừa quá tải.

Một alert tốt cung cấp service, môi trường, vùng, cửa sổ thời gian, biểu đồ, trace/log entry point và runbook. Không yêu cầu người trực phải bắt đầu điều tra từ một chuỗi lỗi không có ngữ cảnh.

## 11. Quy trình điều tra sự cố theo ba loại telemetry

Giả sử một khách hàng thông báo “đặt đơn lúc 10:30 nhưng ứng dụng quay mãi”.

1. **Xác nhận thời gian và phạm vi.** Xem traffic, lỗi, latency và số lượng checkout pending theo khoảng thời gian liên quan; kiểm tra có nhiều khách bị ảnh hưởng hay chỉ một trường hợp.
2. **Phân nhóm.** Kiểm tra route, phiên bản mới triển khai, region và dependency để tìm nơi biến động rõ.
3. **Tìm trace.** Dùng trace ID từ response/support context nếu được cung cấp hoặc tìm trace chậm/lỗi trong khoảng thời gian; nhớ giới hạn sampling.
4. **Đọc waterfall.** Tách thời gian client, server, DB, messaging, retry, chờ pool; kiểm tra span lỗi/attributes.
5. **Mở log liên quan.** Lọc theo trace ID/span ID/service và thời gian; tìm error code, retry decision, queue event và kết quả nghiệp vụ, bảo đảm người điều tra có quyền truy cập.
6. **Đối chiếu các giả thuyết.** Có phải dependency chậm, pool bão hòa, khóa DB, retry storm, deploy mới hay kết quả thanh toán chưa được xác nhận?
7. **Khắc phục và đo lại.** Sau can thiệp, theo dõi tỷ lệ hoàn tất, p95/p99, queue, error rate và lượng fallback; xác nhận dịch vụ phục hồi.
8. **Ghi lại bài học.** Cập nhật dashboard, alert, instrumentation và runbook nếu đã thiếu dấu vết quan trọng.

Không kết luận “đã xử lý xong” chỉ vì error log dừng xuất hiện. Có thể log pipeline bị ngắt, hoặc service dừng nhận request. Phải đối chiếu cả lượng traffic và kết quả người dùng.

## 12. Ví dụ phân biệt những trường hợp dễ nhầm

### Tình huống A: 5xx tăng mạnh trên mọi request

**Metrics:** HTTP 5xx rate tăng ở Order Service, traffic không giảm đáng kể.  
**Traces:** nhiều trace có lỗi ở lời gọi Inventory.  
**Logs:** lỗi kết nối DB hoặc exception liên quan đến reservation.

Cách giải thích: metrics xác nhận mức độ, traces xác định bước, logs bổ sung thông tin đủ để lập giả thuyết và sửa lỗi.

### Tình huống B: Latency tăng nhưng HTTP 200 vẫn cao

**Metrics:** p99 checkout duration tăng, connection pool usage gần tối đa.  
**Traces:** span chờ DB connection chiếm nhiều thời gian, server vẫn trả 200 sau khi chờ.  
**Logs:** có thể không có ERROR; chỉ warning slow-acquisition nếu được ghi.

Cách giải thích: thiếu ERROR log không có nghĩa hệ thống khỏe. Metrics và traces nhận biết vấn đề hiệu năng trước khi chuyển thành lỗi.

### Tình huống C: Người dùng không nhận được email

**Metrics:** số order thành công bình thường nhưng notification queue lag và dead-letter count tăng.  
**Traces:** nếu context được truyền, trace asynchronous có span consumer hoặc span link đến producer.  
**Logs:** template rendering failure hoặc nhà cung cấp email trả lỗi đã được phân loại.

Cách giải thích: request tạo đơn không nhất thiết lỗi; phải theo dõi công việc bất đồng bộ qua broker và consumer.

### Tình huống D: Không tìm thấy một trace dù khách hàng có mã yêu cầu

**Metrics:** xác nhận có traffic và lỗi trong thời gian đó.  
**Traces:** trace có thể không được sample, header context bị mất hoặc instrumentation chưa bao phủ.  
**Logs:** nếu có correlation ID khác, có thể tra cứu sự kiện nghiệp vụ theo quyền.

Cách giải thích: thiếu trace không đủ để chứng minh yêu cầu không xảy ra; cần đánh giá sampling và độ đầy đủ telemetry.

### Tình huống E: Ứng dụng lỗi nhưng dashboard chỉ xanh

**Metrics:** chỉ đo liveness/CPU, bỏ qua kết quả nghiệp vụ và phân khúc.  
**Traces:** có thể thấy fallback làm giảm chức năng hoặc workflow dừng sớm.  
**Logs:** ghi sự kiện fallback hoặc từ chối theo business outcome.

Cách giải thích: health endpoint trả 200 không bảo đảm người dùng nhận đầy đủ chức năng. Bổ sung SLI người dùng và metric cho degraded mode.

## 13. Chi phí, thời gian lưu và tính riêng tư

Telemetry có ích nhưng có thể trở thành nguồn chi phí và rủi ro bảo mật nếu thu thập không kiểm soát.

### 13.1. Chi phí theo từng tín hiệu

- **Logs:** số bản ghi, kích thước, indexing, truy vấn, retention; hạn chế DEBUG ở đường nóng và payload lớn.
- **Metrics:** số time series (cardinality), scrape interval, số phép tính và thời gian lưu; nhãn có cardinality cao gây tăng đột biến.
- **Traces:** số span trên một request, kích thước attributes/events, tỷ lệ sampling, bộ nhớ xử lý và chi phí lưu/query; span theo từng vòng lặp hoặc từng dòng code thường không hữu ích.

Có thể dùng retention nhiều tầng, giảm độ chi tiết dữ liệu cũ, chọn sampling, loại bỏ trường nhạy cảm và lọc dữ liệu không có giá trị. Cần tránh tối ưu chi phí bằng cách mất toàn bộ dấu vết của những sự cố hiếm nhưng nghiêm trọng.

### 13.2. Quyền truy cập và ranh giới dữ liệu

Logs/traces có thể chứa tài sản nhạy cảm hoặc thông tin nhận dạng, kể cả khi không ghi toàn bộ request body: URL, DB statement, HTTP attributes, exception text, messaging headers và span events đều cần đánh giá.

Áp dụng quyền theo service/team/environment, phân tách tenant, masking/redaction, bảo vệ truyền và lưu trữ, audit truy cập, retention, xóa theo chính sách và giới hạn xuất dữ liệu. Không coi hệ thống logging là kho dữ liệu cá nhân có thể truy cập tùy ý.

**Trace ID/correlation ID không phải secret nhưng có thể làm lộ liên hệ giữa các sự kiện nếu không kiểm soát.** Không đưa chúng vào nhãn metric có cardinality cao, cũng không dùng làm quyền truy cập dữ liệu của khách hàng.

### 13.3. Chất lượng pipeline

Giám sát tốc độ ingestion, export failures, bộ nhớ/queue của collector, độ trễ từ sự kiện đến dashboard và tỷ lệ dropped telemetry. Một dashboard trống có thể là vì không có request, vì lỗi exporter hoặc vì query sai. Thiết kế cơ chế nhận biết sự khác biệt này.

## 14. Những sai lầm thường gặp

**“Có log là đủ để observability.”** Log thiếu tổng quan xu hướng và có thể rất đắt để phân tích số lượng lớn. Cần metrics cho tác động và tracing cho quan hệ nhân quả ở mức đường đi.

**“Có metric là biết nguyên nhân.”** Tỷ lệ timeout tăng chỉ nói triệu chứng; trace và log còn cần để phân biệt network, DB pool, retry, code hoặc dependency.

**“Mọi span đều phải được lưu.”** Thu thập tất cả có thể tạo chi phí và quá tải. Thiết kế sampling theo khả năng điều tra và mức độ rủi ro; giữ metric độc lập để không bỏ mất mẫu số.

**“Một trace ID đại diện cả đời đơn hàng.”** Một workflow có thể kéo dài qua nhiều request và message. Dùng business correlation được kiểm soát và span links theo mô hình phù hợp, không ép cùng trace sống vô hạn.

**“Gắn orderId/userId vào mọi metric để dễ tìm.”** Điều này tạo cardinality rất cao. Hãy dùng trace/log với kiểm soát quyền cho trường hợp cụ thể.

**“Log toàn bộ body để debug nhanh.”** Có thể lộ dữ liệu cá nhân, thanh toán và credential. Chỉ ghi metadata an toàn, error code và thông tin tối thiểu đủ vận hành.

**“Mã HTTP 200 nghĩa là thành công.”** HTTP 200/202 có thể che việc người dùng chờ xử lý, mất chức năng tùy chọn hoặc tác vụ downstream lỗi. Cần đo kết quả nghiệp vụ.

**“Không có log lỗi nghĩa là không có lỗi.”** Log bị drop, service crash, exception không được ghi hoặc thao tác chậm nhưng không throw vẫn có thể gây sự cố.

**“Mọi span chậm đều là nguyên nhân.”** Span dài có thể là cha của nhiều span con hoặc bao gồm thời gian chờ; cần xem critical path, mức đồng thời và dữ liệu phụ thuộc trước khi kết luận.

**“Cứ đặt alert cho mọi metric.”** Cảnh báo quá nhiều dẫn tới nhiễu. Chọn alert dựa trên tác động, hành động cụ thể và ngưỡng được hiệu chỉnh.

## 15. Bài tập thực hành: đặt hàng liên quan nhiều service

Một hệ thống xử lý yêu cầu:

~~~text
Client -> Gateway -> Order -> Inventory -> DB
                    |
                    +--> Payment
                    |
                    +--> Broker -> Notification
~~~

Trong một giờ cao điểm, đội hỗ trợ nhận ba phản ánh: đơn hàng tạo chậm, một số đơn ở trạng thái đang xử lý, và email xác nhận đến trễ.

Hãy thiết kế một bộ observability tối thiểu:

1. **Metrics:** chọn các chỉ số và nhãn phục vụ traffic, error rate, p95 latency, dependency timeout, payment pending, queue lag và số đơn hoàn tất. Loại bỏ nhãn có cardinality quá cao.
2. **Traces:** xác định span quan trọng ở Gateway, Order, Inventory, Payment, DB, producer/consumer message; chỉ rõ cần truyền context qua ranh giới nào.
3. **Logs:** quyết định sự kiện nào cần ghi (ví dụ payment state UNKNOWN, inventory reserve failure, notification retry), trường nào an toàn và cách gắn trace/correlation ID.
4. **Dashboard/alert:** xác định đâu là tín hiệu trải nghiệm người dùng, đâu là tín hiệu hạ tầng, alert nào cần trực ca xử lý ngay.
5. **Điều tra:** mô tả cách lần từ cảnh báo latency tới trace chậm, tìm log xác nhận nguyên nhân, rồi kiểm chứng sau khi sửa.
6. **Kiểm thử:** mô phỏng Inventory chậm, Payment timeout sau khi nhận lệnh, consumer Notification ngừng xử lý và exporter telemetry lỗi; kiểm tra telemetry có cho thấy đúng hiện tượng không.

**Hướng triển khai gợi ý:**

- Metrics cho request rate/error/latency theo route và trạng thái nghiệp vụ, thêm connection pool và queue lag để nhìn bottleneck.
- Trace bám các lời gọi HTTP, DB và publish/consume; đưa context vào header thích hợp, dùng span link khi một message liên quan nhiều luồng xử lý.
- Structured log giữ error code, service, trace_id/span_id, trạng thái và thời gian, không chứa token, số thẻ hoặc payload nhạy cảm.
- Dashboard ưu tiên tỷ lệ hoàn tất đơn hàng, tỷ lệ chờ thanh toán và thời gian gửi thông báo; alert theo ảnh hưởng thực và SLO.
- Khi pipeline telemetry lỗi, phải có tín hiệu riêng về exporter/collector để phân biệt “không thấy dữ liệu” với “dịch vụ không còn traffic”.

## 16. Quy trình áp dụng cho một microservice mới

Trước khi triển khai production, có thể thực hiện tuần tự:

1. **Xác định hành vi quan trọng:** API, consumer, background job và kết quả nghiệp vụ ảnh hưởng người dùng.
2. **Định nghĩa SLI/metrics:** request/error/duration, kết quả nghiệp vụ, queue và tài nguyên phù hợp.
3. **Chuẩn hóa logs:** event code, severity, structured fields, policy dữ liệu nhạy cảm và correlation fields.
4. **Instrument traces:** inbound/outbound HTTP, DB, message broker và các operation nghiệp vụ quan trọng.
5. **Truyền context:** qua HTTP, async executor, message headers và ranh giới runtime.
6. **Thiết kế pipeline:** collector/exporter, sampling, batch, retention, truy cập và giới hạn tài nguyên.
7. **Tạo dashboard và alert:** dựa vào trải nghiệm người dùng, SLO và dependency; liên kết tới trace/log khi khả dụng.
8. **Kiểm thử sự cố:** timeout, retry, cạn pool, queue lag, mất context và collector failure.
9. **Đánh giá sau vận hành:** giảm telemetry nhiễu, bổ sung khoảng trống instrumentation và cập nhật runbook.

---

**Điều cốt lõi:** **Metrics** thể hiện sức khỏe, xu hướng và mức độ ảnh hưởng; **traces** nối các thao tác trong hệ phân tán và cho thấy thời gian bị tiêu tốn ở đâu; **logs** ghi lại sự kiện, quyết định và lỗi cần điều tra. Giá trị lớn nhất xuất hiện khi cả ba có cùng ngữ cảnh service, thời gian và trace/correlation, giúp chuyển từ “có sự cố” sang “sự cố nằm ở đâu, vì sao xảy ra và đã phục hồi chưa”.
