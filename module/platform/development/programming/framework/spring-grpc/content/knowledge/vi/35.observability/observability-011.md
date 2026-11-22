# Dashboard theo client, server và dependency

## 1. Một RPC cần được nhìn từ ba phía

Trong **Spring gRPC**, một request có thể đi qua client, gateway, server nhận RPC và nhiều dependency như database, HTTP service hoặc một gRPC service khác. Mỗi phía nhìn thấy một phần khác nhau của cùng thao tác. Nếu chỉ có một dashboard tổng hợp, đội vận hành khó xác định latency đến từ mạng, server handler, retry hay dependency.

Một hệ thống dashboard hữu ích nên có ba góc nhìn liên kết:

- **Client dashboard:** caller quan sát được điều gì? Theo dõi logical RPC, final status, thời gian caller chờ, retry và deadline.
- **Server dashboard:** service nhận và xử lý bao nhiêu RPC? Theo dõi request rate, server status, processing duration, in-flight calls và saturation.
- **Dependency dashboard:** thời gian và lỗi phát sinh ở đâu bên dưới service? Theo dõi outbound call, database, HTTP/gRPC dependency, connection pool và retry.

Ba góc nhìn không được cộng hoặc so sánh như thể chúng đo cùng một event. Một logical call ở client có thể tạo nhiều attempt ở server; một server call có thể tạo nhiều dependency call. Dashboard cần thể hiện rõ phạm vi đo.

## 2. Luồng request và phạm vi đo

~~~mermaid
flowchart LR
    C[Client application] -->|Logical RPC| S[Spring gRPC server]
    S -->|Outbound call| D1[Database]
    S -->|Outbound RPC| D2[Downstream gRPC service]
    C -.-> MC[Client metrics]
    S -.-> MS[Server metrics]
    D1 -.-> MD[Dependency metrics]
    D2 -.-> MD
~~~

Ví dụ client gọi một RPC, lần đầu nhận UNAVAILABLE rồi retry và lần sau thành công:

| Góc nhìn | Số event có thể quan sát |
| --- | ---: |
| Client logical call | 1 |
| Client attempts | 2 |
| Server received RPCs | 1 hoặc 2, tùy attempt nào tới server |
| Dependency calls | 0 hoặc nhiều, tùy handler có chạy và gọi dependency hay không |

Vì vậy:

- Client call count đo thao tác logic mà caller bắt đầu/kết thúc.
- Attempt count đo số lần thực thi transport/RPC nếu instrumentation có hỗ trợ.
- Server call count đo RPC thực sự tới server application.
- Dependency call count đo từng lần service gọi hệ thống phụ thuộc.

Không suy ra số retry bằng cách lấy server calls trừ client calls. Attempt có thể thất bại trước khi tới server; gateway cũng có thể tạo retry riêng.

## 3. Chuẩn hóa metric trước khi dựng dashboard

Trước khi viết panel, thống nhất metric contract: tên, loại metric, thời điểm bắt đầu/kết thúc, label và đơn vị. Ví dụ dưới đây dùng tên metric chuẩn hóa của ứng dụng với prefix app_grpc. Đây là quy ước minh họa; không phải tên bắt buộc mà mọi phiên bản gRPC/OpenTelemetry tự động xuất ra.

| Metric | Loại | Phạm vi |
| --- | --- | --- |
| app_grpc_client_calls_completed_total | Counter | Một lần hoàn tất logical RPC ở client, gắn final status |
| app_grpc_client_call_duration_seconds | Histogram | Thời gian từ lúc client bắt đầu logical call tới terminal result |
| app_grpc_client_attempts_completed_total | Counter | Mỗi attempt client đã kết thúc, gồm cả attempt đầu và retry |
| app_grpc_client_retry_recovered_total | Counter | Logical call cuối cùng OK sau ít nhất một retry |
| app_grpc_server_calls_started_total | Counter | RPC được server application nhận |
| app_grpc_server_calls_completed_total | Counter | RPC server đã đóng, gắn status cuối |
| app_grpc_server_call_duration_seconds | Histogram | Thời gian từ lúc server nhận call tới lúc đóng call |
| app_grpc_server_inflight | Gauge | Số RPC server đang hoạt động |
| app_grpc_dependency_calls_completed_total | Counter | Mỗi outbound call tới dependency đã kết thúc |
| app_grpc_dependency_call_duration_seconds | Histogram | Thời gian của outbound dependency call |
| app_grpc_executor_active_threads | Gauge | Số worker đang chạy theo pool |
| app_grpc_executor_max_threads | Gauge | Giới hạn worker tối đa theo pool |
| app_grpc_executor_queue_size | Gauge | Số task đang chờ theo pool |
| app_grpc_executor_queue_capacity | Gauge | Capacity cấu hình của queue |
| app_grpc_executor_queue_wait_seconds | Histogram | Thời gian task chờ từ submit tới lúc bắt đầu chạy |
| app_grpc_executor_rejected_total | Counter | Số task bị executor từ chối |

Các histogram cần có bucket phù hợp với latency mục tiêu của service. Dùng giây làm đơn vị nhất quán; không trộn milliseconds và seconds trong cùng metric family.

Nếu gRPC/OpenTelemetry instrumentation hoặc Spring/Micrometer integration đã cung cấp metric có cùng ý nghĩa, ưu tiên dùng metric đó và kiểm tra semantic convention của phiên bản đang chạy. Không phát metric trùng chỉ vì muốn đổi tên. Chỉ tạo metric app_grpc riêng cho phần instrumentation chưa có hoặc khi cần một contract ổn định giữa các service.

## 4. Label: đủ để lọc, không tạo cardinality cao

Các label hữu ích thường có tập giá trị hữu hạn:

| Label | Ví dụ | Ghi chú |
| --- | --- | --- |
| service | catalog-service | Tên service đang quan sát |
| target | catalog.internal | Đích client gọi |
| method | catalog.v1.CatalogService/GetItem | Full gRPC method |
| grpc_status | OK, UNAVAILABLE, DEADLINE_EXCEEDED | Final status hoặc status của attempt, phải đặt tên rõ |
| dependency | inventory-db, pricing-service | Tên dependency từ allowlist |
| operation | query-item, GetPrice | Tên operation có giới hạn |
| pool | grpc-callback, database-worker | Tên executor cố định |
| environment | staging, production | Môi trường triển khai |

Không dùng request ID, trace ID, user ID, tenant ID, order ID, token hoặc exception message làm metric label. Những giá trị có cardinality cao phù hợp hơn với log/trace. Dùng method và dependency đã chuẩn hóa, tránh label lấy trực tiếp từ URL, SQL, tên host động hoặc nội dung request.

Với histogram có nhiều label, số time series tăng theo tích các giá trị label và bucket. Hãy bắt đầu với tập label nhỏ, đo số series thực tế và chỉ thêm chiều phân tích khi có câu hỏi vận hành cụ thể.

## 5. Client dashboard: caller đang trải nghiệm gì?

Client dashboard trả lời câu hỏi: từ góc nhìn ứng dụng gọi, RPC có nhanh và đáng tin cậy không?

Các panel chính:

| Panel | Hiển thị | Câu hỏi vận hành |
| --- | --- | --- |
| Logical call rate | Calls/second theo target và method | Caller đang tạo bao nhiêu thao tác? |
| Final status rate | Tỷ lệ OK và từng gRPC status | Caller nhận lỗi nào? |
| Client latency p50/p95/p99 | Thời gian logical call | Caller phải chờ bao lâu? |
| Attempts per logical call | Số attempt trung bình/phân phối | Retry có đang khuếch đại tải? |
| Retry recovery | Call cuối cùng thành công sau retry | Retry có cứu được lỗi tạm thời? |
| Deadline exceeded | Số và tỷ lệ DEADLINE_EXCEEDED | Deadline có quá chặt hoặc dependency chậm? |
| Cancellation | Số call bị CANCELLED | Caller hủy hay upstream mất kết nối? |

Client latency bao gồm nhiều thành phần: client-side queueing, transport, network, gateway, server processing và thời gian chờ retry/backoff. Không kết luận server chậm chỉ từ client p99; cần đối chiếu server và dependency dashboard.

## 6. PromQL cho client dashboard

Các truy vấn sau giả định metric contract ở mục 3 và label grpc_status biểu diễn final status của logical call.

Call rate theo target và method:

~~~promql
sum by (target, method) (
  rate(app_grpc_client_calls_completed_total[5m])
)
~~~

Tỷ lệ logical call lỗi:

~~~promql
sum by (target, method) (
  rate(app_grpc_client_calls_completed_total{grpc_status!="OK"}[5m])
)
/
clamp_min(
  sum by (target, method) (
    rate(app_grpc_client_calls_completed_total[5m])
  ),
  1e-9
)
~~~

Client p95 latency:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, target, method) (
    rate(app_grpc_client_call_duration_seconds_bucket[5m])
  )
)
~~~

Số attempt trung bình trên một logical call:

~~~promql
sum by (target, method) (
  rate(app_grpc_client_attempts_completed_total[5m])
)
/
clamp_min(
  sum by (target, method) (
    rate(app_grpc_client_calls_completed_total[5m])
  ),
  1e-9
)
~~~

Metric attempts phải tăng một lần cho mỗi attempt, kể cả attempt đầu. Nếu instrumentation chỉ đếm retry bổ sung, công thức phải đổi thành 1 + retries/logical call. Ghi rõ semantics trong metric description để dashboard không diễn giải sai.

Tỷ lệ logical call thành công nhờ retry, trên tổng logical call thành công:

~~~promql
sum by (target, method) (
  rate(app_grpc_client_retry_recovered_total[5m])
)
/
clamp_min(
  sum by (target, method) (
    rate(app_grpc_client_calls_completed_total{grpc_status="OK"}[5m])
  ),
  1e-9
)
~~~

## 7. Server dashboard: service đang xử lý ra sao?

Server dashboard tập trung vào tải mà application thực sự nhận và khả năng hoàn tất RPC:

| Panel | Hiển thị | Câu hỏi vận hành |
| --- | --- | --- |
| Received RPC rate | Calls/second theo method | Service đang nhận bao nhiêu request? |
| Server status rate | OK và từng gRPC status | Handler đang trả loại lỗi nào? |
| Server latency p50/p95/p99 | Thời gian nhận tới close | Thời gian xử lý phía server tăng ở method nào? |
| In-flight RPC | Call đang mở | Có call treo hoặc stream dài bất thường? |
| Executor active/queue | Worker và backlog | Callback hoặc business pool có saturation? |
| Rejected tasks | Task bị từ chối | Server đã chạm giới hạn capacity? |
| Deadline/cancellation observed | Call kết thúc do timeout/cancel | Công việc có bị caller bỏ hoặc deadline quá ngắn? |

Server duration không nhất thiết bằng thời gian CPU thực thi handler. Với streaming RPC, thời lượng call có thể bao gồm toàn bộ khoảng stream mở; hãy tách panel theo RPC type nếu unary và stream có đặc tính khác nhau.

## 8. PromQL cho server dashboard

Server request rate:

~~~promql
sum by (method) (
  rate(app_grpc_server_calls_started_total[5m])
)
~~~

Tỷ lệ server call không kết thúc bằng OK:

~~~promql
sum by (method) (
  rate(app_grpc_server_calls_completed_total{grpc_status!="OK"}[5m])
)
/
clamp_min(
  sum by (method) (
    rate(app_grpc_server_calls_completed_total[5m])
  ),
  1e-9
)
~~~

Server p95 duration:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, method) (
    rate(app_grpc_server_call_duration_seconds_bucket[5m])
  )
)
~~~

Tỷ lệ sử dụng queue của executor:

~~~promql
app_grpc_executor_queue_size
/
clamp_min(app_grpc_executor_queue_capacity, 1)
~~~

Rejection rate theo pool:

~~~promql
sum by (pool) (
  rate(app_grpc_executor_rejected_total[5m])
)
~~~

Queue occupancy cần được đọc cùng active threads, max pool size, queue wait duration và request latency. Queue thấp không luôn có nghĩa service khỏe; pool có thể bị block ở dependency hoặc bị giới hạn concurrency ở tầng khác.

## 9. Dependency dashboard: bottleneck nằm ở đâu?

Một RPC server thường gọi nhiều dependency. Dashboard cần phân biệt từng dependency và operation để trả lời service nào làm tăng latency hoặc lỗi.

| Panel | Hiển thị | Ý nghĩa |
| --- | --- | --- |
| Dependency call rate | Outbound calls/second | Service gọi dependency nhiều tới mức nào? |
| Dependency error rate | Status/error theo dependency | Dependency nào đang lỗi? |
| Dependency latency p95/p99 | Thời gian outbound call | Độ trễ nằm ở DB, HTTP hay downstream gRPC? |
| Connection pool usage | Active/idle/pending connection | Có chờ connection không? |
| Dependency retries | Attempts và recovery | Retry ở service có làm tăng tải downstream? |
| Circuit breaker state | Closed/open/half-open | Dependency đang bị cô lập? |
| Timeout/cancel | Timeout và call bị hủy | Deadline/cancellation có truyền tới dependency? |

Đối với database, nên bổ sung query duration, connection acquisition wait, active connection, pending acquisition và pool timeout. Đối với HTTP/gRPC dependency, theo dõi connection pool, DNS/connect/TLS handshake nếu instrumentation hỗ trợ, status và retry attempts.

## 10. PromQL cho dependency dashboard

Dependency call rate:

~~~promql
sum by (dependency, operation) (
  rate(app_grpc_dependency_calls_completed_total[5m])
)
~~~

Dependency error rate (ví dụ cho gRPC dependency có label grpc_status):

~~~promql
sum by (dependency, operation) (
  rate(app_grpc_dependency_calls_completed_total{grpc_status!="OK"}[5m])
)
/
clamp_min(
  sum by (dependency, operation) (
    rate(app_grpc_dependency_calls_completed_total[5m])
  ),
  1e-9
)
~~~

Dependency p95 latency:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, dependency, operation) (
    rate(app_grpc_dependency_call_duration_seconds_bucket[5m])
  )
)
~~~

Nếu một dependency không phải gRPC, không ép status của nó vào grpc_status. Dùng outcome/status label phù hợp với protocol, rồi chuẩn hóa ở dashboard nếu cần so sánh. Ví dụ HTTP có status code; database có outcome như success, timeout hoặc connection_error. Tương tự, nếu cần call-start rate thay vì completion throughput, instrument một counter started riêng.

## 11. Nối ba dashboard để tìm nguyên nhân

Khi client p99 tăng, lần lượt so sánh cùng khoảng thời gian:

| Quan sát | Khả năng cần điều tra |
| --- | --- |
| Client p95 tăng, server p95 ổn định | Network, gateway, client queue hoặc retry backoff |
| Client và server p95 cùng tăng | Server processing hoặc tài nguyên dùng chung |
| Server p95 tăng, dependency p95 tăng cùng lúc | Dependency có thể là bottleneck |
| Server p95 tăng, dependency ổn định, executor queue tăng | Thread pool saturation hoặc CPU/lock contention |
| Client attempts/logical call tăng | Retry amplification hoặc lỗi transport tạm thời |
| Dependency call rate tăng nhanh hơn server RPC rate | Một RPC gọi dependency nhiều lần hoặc retry ở service |
| Server in-flight tăng nhưng request rate ổn định | Call duration tăng, stream kéo dài hoặc handler bị kẹt |

Dashboard giúp khoanh vùng, còn trace giúp xác định một request cụ thể. Dùng trace ID để mở trace tương ứng; kiểm tra span client, server và dependency theo cùng trace. Log nên chứa trace_id, span_id và correlation ID ở dạng đã kiểm soát, không chứa credential hoặc payload nhạy cảm.

## 12. Bố cục Grafana và drill-down

Một dashboard tổng quan có thể chia thành ba hàng:

1. **Client:** call rate, final error rate, p95/p99, attempts per call.
2. **Server:** received rate, status, server duration, in-flight, executor saturation.
3. **Dependency:** call rate, error rate, p95/p99, connection pool và retry.

Tạo dashboard variables có cardinality hữu hạn:

- environment
- cluster/namespace
- service
- method
- target hoặc dependency

Dùng link từ panel method sang dashboard server/dependency với cùng time range và filter. Từ panel có thể mở Explore hoặc trace view nếu exemplar/trace correlation được cấu hình.

Không đưa request ID thành dashboard variable mặc định vì nó không phù hợp để tổng hợp metric. Tìm request riêng bằng trace/log search.

## 13. SLO và cảnh báo

Alert nên dựa trên SLO và tác động người dùng, không chỉ dựa trên một metric đơn lẻ:

| Alert | Điều kiện cần quan sát | Phản ứng |
| --- | --- | --- |
| Client error budget burn | Final error ratio vượt ngưỡng trong nhiều cửa sổ | Kiểm tra target, status và retry |
| Client latency SLO burn | p95/p99 vượt mục tiêu kèm traffic thực | Drill-down server/dependency |
| Server saturation | Queue gần capacity, active workers chạm max và latency tăng | Giảm tải, scale hoặc xử lý bottleneck |
| Dependency degradation | Error/latency dependency tăng và ảnh hưởng RPC | Kiểm tra downstream, pool và circuit breaker |
| Retry amplification | Attempts/logical call tăng bất thường | Kiểm tra lỗi gốc và retry policy |
| In-flight RPC leak | In-flight tăng kéo dài dù traffic không tăng | Tìm stream/call không kết thúc |

Ngưỡng cụ thể phụ thuộc SLO, baseline và traffic. Không cảnh báo chỉ vì p99 cao trong một cửa sổ có vài request; kết hợp volume, duration, error ratio và multi-window burn rate để giảm false positive.

## 14. Những lỗi thường gặp khi dựng dashboard

1. **Gộp client calls và server calls.** Hai metric có phạm vi đo khác nhau, đặc biệt khi retry hoặc gateway có retry.
2. **Chỉ dùng average latency.** Average có thể che giấu tail latency; cần histogram và p95/p99.
3. **Không định nghĩa timing boundary.** Client duration, server duration và dependency duration không thể so sánh nếu cách đo khác nhau.
4. **Gắn ID động vào label.** Cardinality có thể làm monitoring backend quá tải.
5. **Coi mọi non-OK status là cùng một lỗi.** UNAVAILABLE, DEADLINE_EXCEEDED, CANCELLED và PERMISSION_DENIED có nguyên nhân khác nhau.
6. **Không đo retry attempts.** Final success rate có thể che giấu retry amplification.
7. **Chỉ nhìn server latency.** Client có thể chậm vì network, gateway hoặc backoff.
8. **Chỉ nhìn dependency latency.** Queue wait và executor saturation có thể làm request chậm dù dependency khỏe.
9. **Không kiểm tra histogram buckets.** Bucket không phù hợp làm p95/p99 thiếu chính xác.
10. **Dùng dashboard làm bằng chứng nhân quả.** Dashboard khoanh vùng; trace, log và kiểm tra hệ thống mới xác nhận nguyên nhân.

## 15. Kiểm thử dashboard và metric contract

Trước khi đưa dashboard vào vận hành, tạo các tình huống có thể dự đoán:

| Tình huống thử | Kỳ vọng trên dashboard |
| --- | --- |
| RPC thành công bình thường | Client completed OK, server started/completed, dependency call tương ứng |
| Server trả UNAVAILABLE | Client/server status phản ánh đúng phạm vi đo |
| Client retry rồi thành công | Một logical call, nhiều attempts, final status OK |
| Dependency chậm | Dependency p95 tăng; server/client latency có thể tăng theo |
| Executor queue đầy | Queue occupancy/rejection tăng và server status phản ánh overload |
| Deadline hết | Client deadline error; server/dependency có thể thấy cancellation |
| Caller hủy stream | Client cancellation và server in-flight giảm sau cleanup |
| Không có traffic | Rate bằng hoặc gần 0; error ratio không tạo cảnh báo chia cho 0 |

Xác minh metric description, label, unit và histogram buckets. So sánh counter với log/trace trong một khoảng test ngắn để phát hiện đếm trùng hoặc thiếu event. Kiểm tra dashboard không hiển thị token, payload hoặc ID nhạy cảm.

## 16. Bài tập vận dụng

Với CatalogService gọi InventoryService và database:

1. Định nghĩa metric contract cho client logical call completion, client attempt completion, server call start/completion và dependency call completion.
2. Tạo ba dashboard hoặc ba hàng panel theo client, server và dependency.
3. Thêm call rate, final status ratio, p95/p99 và attempts per logical call.
4. Thêm server in-flight, executor active threads, queue size/capacity và rejected tasks.
5. Thêm dependency latency, error rate, connection pool wait và retry.
6. Dựng PromQL query tương ứng với metric contract và xác minh label cardinality.
7. Mô phỏng retry, dependency latency, executor saturation và deadline expiry.
8. Dùng trace để drill-down từ client call sang server span và dependency span.
9. Đề xuất alert dựa trên SLO và kiểm tra false positive khi traffic thấp.

**Tiêu chí hoàn thành:** người học phân biệt được client logical call, server received RPC và dependency call; thiết kế metric có timing boundary/label rõ ràng; dựng dashboard RED và saturation theo ba góc nhìn; viết truy vấn p95/error/retry; và dùng trace để xác định nguyên nhân thay vì suy luận chỉ từ một panel.

### Tài liệu tham khảo

- [gRPC OpenTelemetry Metrics](https://grpc.io/docs/guides/opentelemetry-metrics/): metric quan sát client/server gRPC.
- [OpenTelemetry Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/): counter, histogram, gauge và metric attributes.
- [Prometheus Querying](https://prometheus.io/docs/prometheus/latest/querying/basics/): PromQL và truy vấn time series.
- [Prometheus Histograms](https://prometheus.io/docs/practices/histograms/): histogram bucket và percentile.
- [Grafana Dashboards](https://grafana.com/docs/grafana/latest/dashboards/): dashboard variables, panels và drill-down.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.
