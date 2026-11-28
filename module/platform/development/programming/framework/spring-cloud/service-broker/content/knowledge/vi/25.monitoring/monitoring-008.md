# Cảnh báo thất bại kéo dài, luân chuyển credentials lỗi và cạn tài nguyên

Service broker vận hành một chuỗi công việc từ lúc platform gửi request OSB đến khi backend tạo, cập nhật, thu hồi hoặc binding tài nguyên. Một request có thể được chấp nhận nhanh nhưng provider mất nhiều phút để hoàn tất; credential có thể vẫn hoạt động trong khi rotation đã thất bại; cluster có thể chưa down nhưng quota, connection pool hoặc queue sắp cạn. Nếu chỉ theo dõi HTTP status và CPU, broker sẽ phát hiện sự cố muộn hoặc bỏ sót rủi ro quan trọng.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, cần xây dựng cảnh báo cho ba nhóm: **thất bại kéo dài**, **luân chuyển credentials lỗi** và **cạn tài nguyên**. Cảnh báo phải phản ánh tác động tới service instance, binding và operation; có ngưỡng dựa trên SLO/capacity; phát ra khi có hành động vận hành rõ ràng; và đi kèm runbook để người trực xác minh, giảm tác động và phục hồi.

## 1. Ba nhóm rủi ro cần quan sát

| Nhóm | Dấu hiệu chính | Tác động |
|---|---|---|
| Thất bại kéo dài | Operation ở IN_PROGRESS quá lâu, tỷ lệ lỗi tăng, retry liên tục hoặc lỗi terminal | Platform không nhận được tài nguyên đúng hạn; instance bị kẹt |
| Credential rotation lỗi | Không tạo/kiểm tra credential mới, không chuyển traffic, credential cũ sắp hết hạn hoặc provider từ chối xác thực | Broker có thể mất quyền gọi provider hoặc dùng credential hết hạn |
| Cạn tài nguyên | Quota provider gần hết, queue backlog tăng, connection pool/worker/disk/memory đạt giới hạn | Provision chậm, request bị từ chối, worker timeout hoặc broker ngừng hoạt động |

Ba nhóm này có thể liên quan nhau. Provider quota cạn có thể làm provision thất bại kéo dài; queue backlog tăng làm operation vượt thời hạn; rotation lỗi khiến request provider trả 401/403. Alert cần mang theo component, provider, operation type và môi trường để người trực liên kết triệu chứng với nguyên nhân.

Không tạo một alert chung BROKER_ERROR cho mọi lỗi. Validation do consumer gửi sai parameters khác với provider outage; một lần retry thành công khác với operation bị kẹt; rotation retry thất bại trong khi credential cũ còn hiệu lực khác với tình huống cả credential cũ lẫn mới đều không dùng được.

## 2. Mô hình quan sát cho broker

Kết hợp metrics, logs, traces và event/state của operation:

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Metrics | Sự cố xảy ra bao nhiêu, kéo dài bao lâu, còn bao nhiêu capacity? | Failure rate, oldest operation age, queue depth |
| Logs | Bước xử lý nào thất bại và vì sao? | Provider timeout, token refresh rejected |
| Traces | Độ trễ nằm ở broker, database hay provider? | Provision trace gồm validate, persist, provider API |
| Domain events/state | Operation, rotation và resource đang ở giai đoạn nào? | IN_PROGRESS, VERIFYING_NEW_CREDENTIAL, SUCCEEDED |
| Health/readiness | Thành phần có thể nhận việc mới không? | Database unavailable, provider client misconfigured |

Metrics có thể được phát qua Micrometer và Spring Boot Actuator. Prometheus scrape endpoint metrics; Alertmanager nhóm, định tuyến và gửi cảnh báo. OpenTelemetry bổ sung distributed tracing và export telemetry tùy kiến trúc.

Health indicator trả lời thành phần có hoạt động được hay không; nó không thay thế alert dựa trên hành vi nghiệp vụ. Broker có thể health UP nhưng vẫn có hàng nghìn operation bị kẹt hoặc provider quota còn 2%. Ngược lại, provider tạm thời không truy cập được có thể không nên làm readiness của toàn broker chuyển DOWN nếu broker vẫn phục vụ catalog và các thao tác không phụ thuộc provider đó.

## 3. Định nghĩa operation kéo dài và thất bại

OSB cho phép broker xử lý asynchronous operation. Broker có thể trả HTTP 202 khi đã chấp nhận công việc; platform tiếp tục polling last operation cho đến khi trạng thái terminal. Vì vậy, cần theo dõi thời gian từ lúc operation được tạo đến khi có kết quả cuối cùng.

Các trạng thái nội bộ có thể gồm:

- ACCEPTED: request đã được xác thực và ghi nhận.
- QUEUED: chờ worker.
- IN_PROGRESS: worker đang thực hiện.
- RETRY_WAIT: chờ lần thử tiếp theo.
- SUCCEEDED: hoàn tất thành công.
- FAILED: kết thúc thất bại.
- CANCELLED: bị hủy theo workflow được hỗ trợ.
- RECONCILIATION_REQUIRED: kết quả provider chưa xác định, cần đối soát.

Không gộp RETRY_WAIT vào FAILED nếu operation vẫn có khả năng phục hồi. Cũng không giữ IN_PROGRESS vô hạn khi worker đã chết. Dùng heartbeat hoặc lease để phát hiện operation mất chủ xử lý.

### Xác định ngưỡng thời gian

Không dùng một timeout chung cho mọi operation. Provision database có thể lâu hơn bind credential; deprovision có thể chờ provider xóa tài nguyên; update có thể cần restart hoặc migration.

Xác định ngưỡng theo operation type, service/plan tier, provider/region, percentile lịch sử, SLO và retry policy. Ví dụ ngưỡng khởi đầu để minh họa:

| Operation | Warning | Critical |
|---|---:|---:|
| Bind credential | 2 phút | 5 phút |
| Provision service | 10 phút | 25 phút |
| Update service | 10 phút | 30 phút |
| Deprovision | 10 phút | 30 phút |
| Unbind | 2 phút | 10 phút |

Đây không phải giá trị mặc định cho mọi broker. Hiệu chỉnh bằng dữ liệu production, plan SLA và cam kết của provider. Một operation vẫn trong giới hạn không nên cảnh báo chỉ vì một lần poll chậm.

### Phân biệt lỗi terminal và lỗi tạm thời

| Loại lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Validation/permanent | Plan không hỗ trợ field, region sai, request malformed | Kết thúc FAILED, không retry tự động |
| Authorization/configuration | Provider trả 401/403 do credential hoặc permission | Cảnh báo cấu hình/credential, retry sau khi khắc phục theo policy |
| Capacity/quota | Provider báo quota hoặc capacity exhausted | Thử target khác nếu policy cho phép; nếu không, chờ hoặc fail có kiểm soát |
| Transient | Timeout, 429, 5xx, connection reset | Retry có backoff, jitter và giới hạn |
| Unknown outcome | Timeout sau khi gửi create nhưng không nhận response | Reconcile trước khi gửi create lần nữa |

Alert nên tính theo operation cuối cùng và trạng thái hiện tại, không đếm mỗi lần retry thành một lỗi độc lập rồi tạo hàng trăm cảnh báo cho cùng một instance.

## 4. Metrics cho vòng đời operation

Một bộ metric có thể dùng:

| Metric | Loại | Mục đích |
|---|---|---|
| broker_operations_total | Counter | Tổng operation theo type/result |
| broker_operation_duration_seconds | Timer/Histogram | Thời gian hoàn tất operation |
| broker_operations_in_progress | Gauge | Số operation đang chạy |
| broker_oldest_in_progress_operation_age_seconds | Gauge | Tuổi operation lâu nhất theo nhóm |
| broker_operation_retries_total | Counter | Tổng retry theo type/reason |
| broker_operation_reconciliation_total | Counter | Số lần cần đối soát |
| broker_worker_heartbeat_timestamp_seconds | Gauge | Thời điểm heartbeat gần nhất |
| broker_worker_queue_depth | Gauge | Số job đang chờ |
| broker_last_operation_poll_total | Counter | Lưu lượng polling và kết quả |

Ví dụ metric exposition:

~~~text
broker_operations_total{operation_type="provision",result="failed",provider="provider-a"} 12
broker_operations_in_progress{operation_type="provision",provider="provider-a"} 4
broker_oldest_in_progress_operation_age_seconds{operation_type="provision",provider="provider-a"} 1280
broker_operation_retries_total{operation_type="provision",reason="timeout",provider="provider-a"} 37
~~~

Labels cần có tập giá trị giới hạn. operation_type, result, provider, region và plan_tier có thể phù hợp nếu danh mục được kiểm soát. Không đưa instance ID, binding ID, tenant ID, operation ID, email hoặc raw error message vào label vì cardinality tăng theo số lượng tài nguyên.

Chi tiết định danh nên nằm trong log/traces có correlation ID, được bảo vệ và có retention policy. Metrics giúp biết nhóm nào đang lỗi mà không tạo một time series riêng cho từng khách hàng.

### Tính tuổi operation

Worker hoặc metrics collector có thể xuất gauge tổng hợp như oldest age theo operation type/provider. Nếu cần xác định tuổi từng operation để điều tra, truy vấn state store hoặc log bằng operation ID; không cần biến mọi operation ID thành metric label.

Nếu dùng heartbeat, lưu thời điểm heartbeat và lease expiry. Operation chỉ được xem là stale khi không có heartbeat vượt quá ngưỡng cộng với khoảng trễ an toàn. Worker restart hoặc scheduler pause ngắn không nên lập tức tạo alert critical.

## 5. Cảnh báo tỷ lệ thất bại và operation bị kẹt

Nên có hai kiểu alert chính:

1. **Failure rate:** tỷ lệ operation kết thúc FAILED tăng trong một cửa sổ thời gian.
2. **Long-running/stuck:** operation chưa terminal vượt ngưỡng hoặc worker heartbeat mất.

Ví dụ Prometheus rule:

~~~yaml
groups:
  - name: broker-operation-alerts
    rules:
      - alert: BrokerProvisionFailureRateHigh
        expr: |
          (
            sum by (provider) (
              rate(broker_operations_total{
                operation_type="provision",
                result="failed"
              }[10m])
            )
            /
            clamp_min(
              sum by (provider) (
                rate(broker_operations_total{
                  operation_type="provision"
                }[10m])
              ),
              0.001
            )
          ) > 0.05
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Provision failure rate is elevated"
          description: "Provision failures exceed 5% for provider {{ $labels.provider }}."
          runbook: "https://runbooks.example/broker/provision-failure"

      - alert: BrokerProvisionOperationTooOld
        expr: |
          broker_oldest_in_progress_operation_age_seconds{
            operation_type="provision"
          } > 1500
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Provision operation has exceeded its time budget"
          description: "The oldest provision operation is older than 25 minutes."
          runbook: "https://runbooks.example/broker/operation-stuck"
~~~

Đây là rule minh họa. Ngưỡng 5%, 10 phút và 25 phút cần điều chỉnh theo volume và SLO. Với lưu lượng thấp, một lỗi có thể làm tỷ lệ vượt 100%; nên kết hợp minimum request count hoặc alert theo số lượng lỗi tuyệt đối. Kiểm tra metric name/label thực tế do ứng dụng export.

Alert theo oldest age chỉ hoạt động nếu gauge được cập nhật liên tục. Nếu operation bị mất khỏi state store hoặc metrics exporter ngừng scrape, cần alert riêng cho heartbeat và telemetry missing.

### Không cảnh báo theo mỗi HTTP 202

HTTP 202 nghĩa là broker đã chấp nhận xử lý bất đồng bộ, không phải backend đã thành công. Không tạo alert thành công/thất bại từ response HTTP ban đầu. Theo dõi state machine và terminal result trong operation store.

Last operation polling có thể tăng mạnh do platform poll thường xuyên. Đây là traffic dự kiến, không phải lỗi; cần tách poll count khỏi provider operation count.

## 6. Phát hiện worker chết hoặc queue backlog

Operation bị kẹt có thể do worker không nhận job, queue không tiêu thụ, consumer crash hoặc lease không được gia hạn.

Metrics nên theo dõi queue depth, oldest message age, consumer count, processing rate, enqueue rate, retry queue/dead-letter queue depth, worker heartbeat, lease renewal failures và job vượt max attempts.

Queue depth đơn lẻ chưa đủ. Nếu enqueue rate thấp, depth 100 có thể nghiêm trọng; nếu hệ thống xử lý 10.000 job/phút, depth 100 có thể bình thường. Oldest message age và tỷ lệ tiêu thụ thường phản ánh tác động tốt hơn.

Ví dụ:

~~~yaml
- alert: BrokerQueueBacklogGrowing
  expr: |
    broker_queue_oldest_message_age_seconds > 300
    and broker_queue_depth > 100
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Broker worker queue is not draining"
    description: "Oldest queued operation is older than five minutes."

- alert: BrokerWorkerHeartbeatMissing
  expr: |
    time() - broker_worker_heartbeat_timestamp_seconds > 120
  for: 3m
  labels:
    severity: critical
  annotations:
    summary: "Broker worker heartbeat is stale"
    description: "No worker heartbeat has been observed within the expected interval."
~~~

Các ngưỡng trên chỉ minh họa. Với nhiều worker, metric heartbeat nên có label worker_pool/region có tập giá trị giới hạn; alert cần kiểm tra số worker healthy hoặc phần trăm worker mất heartbeat thay vì báo một worker bảo trì đơn lẻ.

## 7. Theo dõi vòng đời credential rotation

Provider credential có thể là client secret, API key, certificate, service account token hoặc credential truy cập cloud account. Rotation cần được xem như một workflow có trạng thái, không phải một thao tác cập nhật secret đơn giản.

Một quy trình rotation an toàn thường gồm:

~~~mermaid
flowchart TD
    A["Rotation due / requested"] --> B["Create candidate credential"]
    B --> C["Validate candidate against provider"]
    C -->|Valid| D["Install candidate in broker secret store"]
    C -->|Invalid| X["Rotation failed"]
    D --> E["Switch new requests to candidate"]
    E --> F["Verify provider calls with candidate"]
    F -->|Success| G["Revoke old credential"]
    F -->|Failure| R["Rollback to old credential if valid"]
    R --> X
    G --> H["Confirm old credential revoked"]
    H --> I["Rotation succeeded"]
~~~

Một rotation record nên lưu provider/account reference đã chuẩn hóa, credential version hoặc secret reference, thời điểm bắt đầu và hạn credential cũ, stage hiện tại, kết quả validate candidate, thời điểm switch, kết quả xác minh request sau switch, kết quả revoke credential cũ, rotation attempt ID và policy version.

Không log credential value hoặc đưa nó vào metric. Secret store giữ secret; database operation chỉ lưu reference/version và trạng thái workflow.

### Tách lỗi rotation theo giai đoạn

| Giai đoạn | Lỗi có thể gặp | Tác động |
|---|---|---|
| Create candidate | API provider không cấp được key mới | Không có credential mới |
| Validate candidate | Sai scope, key chưa active, permission thiếu | Không thể chuyển traffic |
| Install | Secret manager lỗi hoặc version chưa publish | Worker khác vẫn dùng secret cũ |
| Switch | Cache/client pool không reload | Request dùng credential không đồng nhất |
| Verify | Provider trả 401/403/5xx | Chưa xác nhận credential mới |
| Revoke old | Provider không thu hồi key cũ | Rủi ro tồn tại credential thừa |
| Confirm revoke | Không đọc được trạng thái key cũ | Rotation chưa hoàn tất về mặt kiểm soát |

Không đánh dấu rotation SUCCEEDED chỉ vì secret mới đã được tạo. Cần xác minh client thực tế dùng secret mới và credential cũ đã được revoke hoặc có quyết định giữ lại được phê duyệt.

## 8. Metrics và alert cho credential rotation

Có thể export:

| Metric | Loại | Ý nghĩa |
|---|---|---|
| broker_credential_rotation_total | Counter | Số lần rotation theo provider/stage/result |
| broker_credential_rotation_duration_seconds | Histogram | Thời gian hoàn tất rotation |
| broker_credential_rotation_in_progress | Gauge | Số rotation đang chạy |
| broker_credential_expiry_timestamp_seconds | Gauge | Unix timestamp hết hạn credential đang active |
| broker_provider_auth_failures_total | Counter | Số lỗi authentication khi gọi provider |
| broker_credential_last_successful_rotation_timestamp_seconds | Gauge | Thời điểm rotation thành công gần nhất |
| broker_credential_validation_total | Counter | Kết quả validate candidate |

Ví dụ:

~~~text
broker_credential_rotation_total{provider="provider-a",stage="verify",result="failure"} 3
broker_credential_rotation_in_progress{provider="provider-a"} 1
broker_credential_expiry_timestamp_seconds{provider="provider-a",account="production"} 1790000000
broker_provider_auth_failures_total{provider="provider-a",reason="unauthorized"} 8
~~~

Label account chỉ nên dùng nếu account alias là tập giá trị nhỏ, không chứa số tài khoản nhạy cảm hoặc secret. Nếu số account lớn, đưa account identity vào log/event thay vì metric label.

Alert khi rotation thất bại:

~~~yaml
- alert: BrokerCredentialRotationFailed
  expr: |
    increase(broker_credential_rotation_total{
      result="failure"
    }[15m]) > 0
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "Provider credential rotation failed"
    description: "A credential rotation stage failed for provider {{ $labels.provider }}."

- alert: BrokerCredentialExpiresSoon
  expr: |
    broker_credential_expiry_timestamp_seconds - time() < 7 * 24 * 3600
  for: 15m
  labels:
    severity: warning
  annotations:
    summary: "Provider credential is approaching expiry"
    description: "The active provider credential expires within seven days."
~~~

Cần alert critical nếu credential active đã hết hạn hoặc provider auth failure tăng trên diện rộng. Nếu rotation thất bại nhưng credential cũ còn hiệu lực đủ lâu, severity có thể là warning để vận hành sửa trước hạn. Nếu credential cũ đã hết hạn và candidate chưa hoạt động, đây là outage có tác động trực tiếp đến provision/update/deprovision.

### Theo dõi thời hạn bằng timestamp

Gauge expiry nên chứa Unix timestamp của credential đang được sử dụng, không phải số ngày được tính từ lúc process khởi động. Prometheus expression dùng time() để tính thời gian còn lại.

Nếu provider không cung cấp expiry hoặc credential không hết hạn tự động, metric có thể không tồn tại; thay vào đó, theo dõi rotation age theo policy nội bộ. Không phát alert expiry dựa trên timestamp bằng 0 hoặc dữ liệu chưa đồng bộ; cần alert telemetry/config missing riêng để tránh cảnh báo sai.

## 9. Cảnh báo provider authentication failures

Rotation có thể báo thành công nhưng ứng dụng vẫn gọi provider bằng credential cũ do cache, secret mount hoặc connection pool chưa reload. Vì vậy cần theo dõi kết quả authentication của request provider thực tế.

Phân loại lỗi:

- 401/unauthorized: credential không hợp lệ, hết hạn hoặc gửi sai audience.
- 403/forbidden: credential được nhận diện nhưng thiếu quyền.
- TLS handshake/certificate error: certificate, trust chain hoặc thời hạn chứng thư có vấn đề.
- 429: rate limit; không tự kết luận credential sai.
- 5xx/timeout: provider unavailable hoặc network issue, không đồng nhất với auth failure.

Alert ví dụ:

~~~yaml
- alert: BrokerProviderAuthenticationFailures
  expr: |
    sum by (provider) (
      increase(broker_provider_auth_failures_total[10m])
    ) >= 5
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Provider authentication failures are recurring"
    description: "Provider calls are repeatedly rejected; verify credential version and permissions."
~~~

Chỉ tăng metric auth failure khi response thực sự là authentication/authorization failure đã phân loại. Không tính mọi HTTP 4xx vào cùng metric này.

Nếu một provider account dùng chung cho nhiều service, một credential lỗi có thể ảnh hưởng nhiều plan. Dashboard nên cho thấy provider, account alias, credential version và service operation chịu ảnh hưởng để người trực xác định blast radius.

## 10. Cạn tài nguyên: nhìn vào headroom và saturation

Cạn tài nguyên không chỉ là CPU 100%. Broker có nhiều lớp tài nguyên:

| Lớp | Tài nguyên | Dấu hiệu cạn |
|---|---|---|
| Provider | Quota instance, vCPU, storage, IP, database connection, API quota | Create bị từ chối, quota response, capacity unavailable |
| Worker | Worker slot, thread, CPU, memory | Queue backlog, processing rate giảm |
| Queue | Message capacity, partition, consumer | Oldest message age tăng, DLQ tăng |
| Broker database | Connection pool, storage, transaction/lock | Connection timeout, disk gần đầy, query latency tăng |
| Runtime | Heap, direct memory, file descriptor | GC pause, OOM, connection failures |
| Network | Egress, DNS, connection limit | Timeout, retry và latency tăng |
| Kubernetes | Pod quota, node capacity, PVC, ephemeral storage | Pending pod, PVC Pending, eviction |
| Tenant/service | Quota instance, binding, storage hoặc request rate | Tenant không thể provision thêm |

Đối với mỗi tài nguyên, theo dõi usage, limit và remaining headroom. Usage cao chưa chắc là vấn đề nếu capacity còn dư; usage thấp vẫn có thể nguy hiểm nếu limit vừa bị giảm.

~~~text
capacity_utilization_ratio = used / limit
capacity_headroom_ratio = (limit - used) / limit
~~~

Alert nên dựa trên headroom hoặc saturation trong một khoảng thời gian, kết hợp tốc độ tăng và nhu cầu dự kiến.

## 11. Theo dõi provider quota và capacity

Provider thường có quota theo account, region hoặc loại resource. Broker cần đo quota đã dùng, quota còn lại và request đang reserve để tránh nhiều provision đồng thời cùng vượt giới hạn.

Ví dụ metric:

~~~text
broker_provider_quota_used{provider="provider-a",region="ap-southeast-1",resource="database"} 82
broker_provider_quota_limit{provider="provider-a",region="ap-southeast-1",resource="database"} 100
broker_provider_quota_reserved{provider="provider-a",region="ap-southeast-1",resource="database"} 7
~~~

Effective headroom phải tính cả reservation chưa hoàn tất:

~~~text
available = limit - used - reserved
~~~

Alert khi available thấp hơn ngưỡng cần thiết cho nhu cầu bình thường:

~~~yaml
- alert: BrokerProviderQuotaHeadroomLow
  expr: |
    (
      broker_provider_quota_limit
      - broker_provider_quota_used
      - broker_provider_quota_reserved
    ) / clamp_min(broker_provider_quota_limit, 1) < 0.10
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Provider quota headroom is below 10%"
    description: "Review quota, reservations and placement options before provisioning is blocked."
~~~

Nếu quota provider chỉ có thể đọc bằng API định kỳ, exporter cần ghi timestamp lần scrape thành công. Dữ liệu quota cũ không nên được coi là chính xác. Tạo alert riêng nếu quota telemetry stale.

Không tăng quota tự động khi chưa có policy và approval. Có thể chọn target khác nếu tenant, data residency, encryption và plan capability vẫn được đáp ứng; không chuyển workload sang region không được phép chỉ để tránh quota.

## 12. Theo dõi queue, connection pool và database capacity

### Queue

Theo dõi depth, oldest message age, consumer lag, processing rate, retry queue và dead-letter queue. Nếu backlog tăng liên tục dù worker healthy, có thể worker throughput thấp hơn tốc độ enqueue hoặc provider đang throttling.

### Database connection pool

Với HikariCP hoặc pool tương ứng, theo dõi active, idle, pending threads, acquisition timeout và max connections. Alert khi pending tăng kéo dài và active gần max; một spike ngắn không nhất thiết là outage.

Metric khái niệm:

~~~text
broker_db_connections_active 28
broker_db_connections_max 30
broker_db_connections_pending 12
~~~

Nếu active đạt max và pending tăng, request có thể chờ connection rồi timeout. Xác minh query chậm, transaction giữ connection lâu, pool size hoặc database connection limit trước khi tăng pool. Tăng pool quá mức có thể làm database quá tải hơn.

### Database storage và lock

Theo dõi dung lượng disk, transaction log/WAL, replication lag, lock wait, deadlock và query latency. Disk đầy có thể làm broker không ghi operation state; đây là lỗi có thể ảnh hưởng trực tiếp tới idempotency và lifecycle.

### Worker/runtime

Theo dõi worker active, queue assignment, thread pool saturation, heap, GC pause, direct memory và file descriptors. Không chỉ alert CPU cao; deadlock hoặc pool exhausted có thể xảy ra khi CPU thấp.

## 13. Theo dõi Kubernetes capacity nếu broker chạy trên Kubernetes

Nếu broker hoặc provider adapter chạy trong Kubernetes, cần theo dõi pod restart và CrashLoopBackOff; pod Pending do thiếu CPU/memory hoặc quota; container CPU throttling và memory working set; node allocatable headroom; PVC Pending và filesystem usage; ephemeral storage pressure; HPA desired/current replicas; deployment available replicas; network policy/DNS/service endpoint failures.

Ví dụ alert:

~~~yaml
- alert: BrokerPodsUnavailable
  expr: |
    kube_deployment_status_replicas_available{
      deployment="service-broker"
    } < 2
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Service broker has insufficient available replicas"
    description: "Check pod scheduling, readiness, node capacity and recent restarts."

- alert: BrokerContainerMemoryNearLimit
  expr: |
    container_memory_working_set_bytes{
      container="service-broker"
    }
    /
    container_spec_memory_limit_bytes{
      container="service-broker"
    } > 0.90
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Broker container memory is near its limit"
    description: "Review heap, direct memory, workload and pod limits."
~~~

Các metric Kubernetes phụ thuộc kube-state-metrics/cAdvisor và cấu hình scrape. Cần lọc đúng namespace/pod/container; tránh query match container rỗng hoặc pause container. Ngưỡng replica phải khớp deployment thực tế và mức availability yêu cầu.

## 14. Theo dõi tài nguyên theo tenant và plan mà không lộ dữ liệu

Broker cần quota theo tenant nhưng không nên đưa tenant ID vào mọi metric label. Có thể dùng hai lớp telemetry:

- Metrics tổng hợp theo service, plan tier, region hoặc provider để alert hạ tầng.
- Audit/log có kiểm soát để truy ra tenant cụ thể khi điều tra.
- Dashboard nội bộ có truy vấn scoped theo tenant khi người xem được phép.
- Quota service lưu usage/reservation chính xác trong database.

Nếu cần metric tenant-level cho một tập khách hàng nhỏ, dùng alias không nhạy cảm, giới hạn cardinality và retention. Với số tenant lớn, xuất top-N hoặc nhóm quota utilization thay vì một time series vô hạn.

Quota tenant cần tính reservation đang chờ, không chỉ instance đã ACTIVE. Khi provision được chấp nhận, broker nên reserve capacity/quota nguyên tử; khi operation thất bại hoặc deprovision hoàn tất, giải phóng reservation theo state transition. Alert quota tenant gần đầy nên đi kèm service/plan scope và quy trình nâng quota, nhưng không công khai dữ liệu một tenant cho tenant khác.

## 15. Phân cấp severity và tác động

Không phải mọi alert đều cần đánh thức người trực ngoài giờ. Hãy định nghĩa severity theo tác động và thời gian xử lý còn lại.

| Severity | Khi dùng | Hành động |
|---|---|---|
| Critical / P1 | Provision/deprovision diện rộng gián đoạn; credential active không dùng được; broker không ghi state; capacity hết và dịch vụ ngừng | On-call phản hồi ngay, incident workflow |
| Warning / P2 | Failure rate cao ở một provider/region; rotation lỗi nhưng credential cũ còn hiệu lực; quota headroom thấp | Điều tra trong ca trực, lập kế hoạch khắc phục |
| Info / ticket | Rotation sắp đến hạn; quota trend tăng; operation latency p95 tăng nhưng vẫn trong SLO | Tạo công việc chủ động, chưa cần page |
| Resolved | Điều kiện alert đã hồi phục đủ thời gian | Gửi thông báo khôi phục và đóng incident theo quy trình |

Severity phải xét blast radius. Credential dùng chung cho toàn provider có thể ảnh hưởng nhiều tenant; quota của một plan thử nghiệm có thể chỉ ảnh hưởng nhóm nhỏ. Không dùng cùng severity chỉ vì metric vượt cùng tỷ lệ.

### Kết hợp symptom và cause

Alert symptom cho biết người dùng đang bị ảnh hưởng, ví dụ provision success rate giảm. Alert cause giúp xác định lý do, ví dụ provider auth failures tăng hoặc quota headroom thấp. Alertmanager có thể group/inhibit để tránh page nhiều lần cho cùng incident, nhưng vẫn giữ từng alert trong dashboard.

## 16. Prometheus rule tổng hợp cho ba nhóm cảnh báo

Ví dụ cấu hình rút gọn:

~~~yaml
groups:
  - name: broker-risk-alerts
    rules:
      - alert: BrokerOperationsFailing
        expr: |
          sum by (provider, operation_type) (
            increase(broker_operations_total{result="failed"}[10m])
          ) >= 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Broker operations are failing repeatedly"
          runbook: "https://runbooks.example/broker/operation-failures"

      - alert: BrokerCredentialRotationStalled
        expr: |
          broker_credential_rotation_in_progress > 0
          and broker_credential_rotation_oldest_age_seconds > 900
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Credential rotation is stalled"
          runbook: "https://runbooks.example/broker/credential-rotation"

      - alert: BrokerCredentialExpired
        expr: |
          broker_credential_expiry_timestamp_seconds < time()
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Active provider credential has expired"
          runbook: "https://runbooks.example/broker/credential-expiry"

      - alert: BrokerProviderCapacityCritical
        expr: |
          broker_provider_capacity_headroom_ratio < 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Provider capacity headroom is critically low"
          runbook: "https://runbooks.example/broker/provider-capacity"

      - alert: BrokerDatabasePoolSaturated
        expr: |
          broker_db_connections_pending > 0
          and broker_db_connections_active
              / clamp_min(broker_db_connections_max, 1) > 0.90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Broker database connection pool is saturated"
          runbook: "https://runbooks.example/broker/database-pool"
~~~

Metric trong ví dụ là metric ứng dụng tự định nghĩa; không có sẵn chỉ vì cài Spring Boot Actuator. Cần instrument và export đúng type/label. Với gauge tuổi rotation, exporter phải tính từ rotation record đang active. Với headroom ratio, exporter phải xử lý trường hợp limit bằng 0 hoặc chưa có dữ liệu.

Rule thực tế nên bổ sung thời gian giữ điều kiện firing, label team/environment và annotation chứa dashboard/runbook. Test rule bằng promtool và dữ liệu mẫu trước khi triển khai.

## 17. Thiết kế Alertmanager để giảm nhiễu

Alertmanager giúp group, route, silence và inhibit alert. Cấu hình cần bảo đảm:

- Group theo environment, provider, region, service hoặc incident key.
- Route critical đến on-call; warning đến nhóm vận hành phù hợp; info thành ticket.
- Inhibit alert symptom khi cause alert tương ứng đang firing, nếu quan hệ nguyên nhân rõ ràng.
- Deduplicate cùng một incident từ nhiều replica.
- Có repeat interval phù hợp với thời gian phản hồi.
- Có thời hạn silence và người chịu trách nhiệm.
- Không silence vô thời hạn các alert về credential expiry hoặc quota exhaustion.

Ví dụ cấu trúc route:

~~~yaml
route:
  receiver: broker-operations
  group_by: ["alertname", "environment", "provider"]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 2h
  routes:
    - matchers:
        - severity="critical"
      receiver: broker-oncall
    - matchers:
        - severity="warning"
      receiver: broker-operations

receivers:
  - name: broker-oncall
  - name: broker-operations
~~~

Tên receiver chỉ minh họa. Cấu hình thật cần tích hợp hệ thống incident của tổ chức. Không gửi secret, token hoặc raw provider response vào notification.

## 18. Runbook cho operation thất bại kéo dài

Khi alert operation quá lâu hoặc failure rate cao:

1. Xác định provider, region, operation type và thời điểm bắt đầu.
2. Mở dashboard operation để xem ACCEPTED, QUEUED, IN_PROGRESS, RETRY_WAIT hoặc RECONCILIATION_REQUIRED.
3. Kiểm tra queue oldest age, worker heartbeat, active consumer và DLQ.
4. Tra log/trace bằng correlation ID; phân biệt validation, auth, quota, rate limit, timeout và provider 5xx.
5. Kiểm tra provider operation ID hoặc correlation tag để biết resource có thể đã được tạo hay chưa.
6. Nếu unknown outcome, reconcile trước khi retry create.
7. Nếu worker chết, xác minh lease và state store trước khi khởi động lại consumer.
8. Nếu lỗi ảnh hưởng diện rộng, áp dụng circuit breaker hoặc giới hạn nhận job mới theo policy.
9. Cập nhật operation state và thông tin platform polling nhất quán.
10. Ghi incident timeline và nguyên nhân sau khi phục hồi.

Không xóa operation record chỉ để làm alert biến mất. Không chạy lại deprovision/provision bằng tay nếu chưa xác minh idempotency và ownership.

## 19. Runbook cho credential rotation lỗi

Khi rotation thất bại:

1. Xác định provider/account alias và rotation stage thất bại.
2. Xem credential version đang active và expiry timestamp; không đọc secret value vào terminal/log.
3. Xác minh credential cũ còn hiệu lực và request provider hiện tại có thành công không.
4. Kiểm tra candidate secret đã được tạo, validate và publish chưa.
5. Kiểm tra worker/client pool có reload version mới hay vẫn dùng version cũ.
6. Xác minh quyền của candidate bằng một API read-only phù hợp.
7. Nếu candidate sai, giữ credential cũ còn hợp lệ và rollback theo quy trình.
8. Nếu credential cũ đã hết hạn, dùng quy trình recovery/break-glass đã phê duyệt.
9. Chỉ revoke credential cũ sau khi request dùng credential mới đã được xác minh.
10. Sau rotation, kiểm tra provider auth failure rate và audit record.

Không copy secret vào chat, ticket hoặc alert. Không revoke credential cũ trước khi xác nhận candidate hoạt động nếu provider cho phép overlap. Nếu provider không hỗ trợ overlap, phải có maintenance plan và rollback strategy phù hợp.

## 20. Runbook cho cạn tài nguyên

Khi quota, queue, database hoặc runtime gần cạn:

1. Xác định tài nguyên và scope: provider/region, broker cluster, queue, database hay tenant quota.
2. Xem usage, limit, reservation, headroom và tốc độ tiêu thụ.
3. Kiểm tra backlog và processing rate để xác định demand tăng hay worker giảm throughput.
4. Xem lỗi gần nhất: quota exceeded, capacity unavailable, connection timeout, disk pressure hoặc OOM.
5. Tạm giới hạn nhận request hoặc rate theo tenant/provider nếu cần bảo vệ broker.
6. Chọn target khác chỉ khi policy, region, security và plan capability cho phép.
7. Giải phóng reservation mồ côi sau khi xác minh operation terminal và backend state.
8. Tăng worker/replica hoặc pool có kiểm soát; xác minh dependency có thể chịu tải.
9. Yêu cầu provider nâng quota hoặc mở rộng capacity theo quy trình.
10. Theo dõi headroom và queue age đến khi ổn định, sau đó gỡ throttling.

Không tăng thread pool, connection pool hoặc replica một cách mù quáng. Nếu bottleneck nằm ở provider quota hoặc database max connection, tăng worker có thể làm tình hình tệ hơn.

## 21. Dashboard vận hành cần có

Một dashboard broker nên có các khu vực:

### Operation health

- Request rate theo operation type.
- Success/failure rate.
- p50/p95/p99 duration.
- Oldest in-progress operation age.
- Retry và reconciliation count.
- IN_PROGRESS/RETRY_WAIT/FAILED count.
- Last operation polling latency.

### Credential health

- Credential expiry countdown theo provider/account alias.
- Rotation stage và duration.
- Last successful rotation.
- Rotation failure count.
- Provider 401/403 rate.
- Active credential version và candidate version dưới dạng reference/version, không phải secret.

### Capacity health

- Provider quota used/reserved/limit/headroom.
- Queue depth và oldest message age.
- Worker count, throughput và heartbeat.
- Database pool active/pending/max.
- Database disk/transaction log headroom.
- JVM heap, GC pause, thread và file descriptor.
- Kubernetes replicas, pod pending, memory/CPU throttling và PVC usage nếu áp dụng.

Dashboard phải liên kết alert với runbook và truy vấn log/trace. Dữ liệu hiển thị theo tenant cần tuân theo authorization; dashboard vận hành nội bộ có thể dùng alias hoặc nhóm thay vì công khai ID nhạy cảm.

## 22. Kiểm thử alert và telemetry

Alert không nên chỉ được triển khai rồi chờ sự cố thật mới biết có hoạt động. Kiểm thử metric instrumentation, rule expression và notification route.

| Kiểm thử | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Operation success | Tạo operation fixture thành công | Counter success tăng, failure alert không firing |
| Terminal failure | Cho provider fake trả lỗi permanent | Failure counter tăng, operation FAILED |
| Long-running operation | Giữ operation IN_PROGRESS vượt ngưỡng | Alert age firing sau thời gian giữ điều kiện |
| Retry transient | Provider fake trả 503 rồi thành công | Retry metric tăng, không đánh đồng với terminal failure |
| Worker mất heartbeat | Dừng heartbeat trong test | Stale heartbeat alert firing |
| Rotation candidate invalid | Provider fake từ chối credential mới | Rotation failure theo stage, credential cũ vẫn active nếu policy |
| Credential sắp hết hạn | Đặt expiry timestamp gần hiện tại | Expiry warning firing |
| Credential hết hạn | Đặt expiry trong quá khứ | Critical alert firing |
| Quota thấp | Giảm available headroom | Capacity alert firing |
| Queue backlog | Tăng oldest message age và depth | Queue alert firing |
| Pool saturation | Active gần max và pending tăng | Database pool alert firing |
| Telemetry missing | Ngừng scrape/exporter | Alert target down hoặc metric absent |
| Alert recovery | Khôi phục metric bình thường | Alert resolved sau thời gian ổn định |
| Duplicate events | Gửi cùng event nhiều lần | Metric/state không đếm side effect sai |
| Cardinality | Tạo nhiều instance/tenant | Không sinh label theo resource ID |

Có thể dùng unit test cho Micrometer instrumentation, integration test với fake provider/state store, Prometheus rule unit test bằng promtool, Alertmanager config validation, synthetic operation định kỳ và chaos/failure injection có kiểm soát cho timeout, 401/403, 429, 5xx và worker crash.

Synthetic test phải dùng tài nguyên và tenant thử nghiệm riêng, có cleanup, quota giới hạn và không gây chi phí bất ngờ.

## 23. Quản lý alert noise và thay đổi ngưỡng

Cảnh báo quá nhiều khiến người trực bỏ qua cảnh báo thật. Review định kỳ:

- Tỷ lệ alert được xác nhận có hành động.
- Số alert tự resolve trước khi có người xử lý.
- Số alert trùng cùng incident.
- Thời gian từ firing đến acknowledge/resolve.
- Số alert false positive do scrape gap hoặc deployment.
- Alert không có runbook hoặc owner.
- Alert threshold không còn phù hợp sau khi tăng tải.

Ngưỡng nên thay đổi theo dữ liệu thực tế và SLO. Có thể dùng baseline theo giờ/ngày cho workload có tính chu kỳ, nhưng không để adaptive threshold che giấu suy giảm kéo dài. Mọi thay đổi rule cần review, version control và kiểm thử bằng dữ liệu lịch sử nếu có.

Khi deploy broker mới, có thể bắt đầu ở chế độ quan sát hoặc severity thấp cho rule chưa được hiệu chỉnh; sau khi xác nhận false positive/coverage, mới bật paging. Các alert về credential sắp hết hạn và mất khả năng xác thực cần có thời gian xử lý đủ dài, không đợi đến khi hết hạn mới báo.

## 24. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ alert HTTP 5xx | Bỏ sót operation bị kẹt sau HTTP 202 | Theo dõi operation state và age |
| Alert mỗi lần retry | Nhiễu và đếm trùng cùng sự cố | Phân biệt attempt với terminal operation |
| Dùng một timeout cho mọi plan | False positive hoặc phát hiện quá muộn | Ngưỡng theo operation/provider/plan và SLO |
| Rotation success ngay khi tạo secret mới | Request thực tế vẫn dùng secret cũ hoặc secret mới sai quyền | Validate, switch, verify và revoke theo stage |
| Revoke credential cũ quá sớm | Provider call outage | Chỉ revoke sau khi candidate hoạt động |
| Log secret để debug rotation | Rò rỉ credential | Log version/reference và reason code đã lọc |
| Chỉ theo dõi CPU | Bỏ sót quota, queue, pool và disk | Theo dõi headroom/saturation theo từng lớp |
| Alert quota dựa trên used, bỏ qua reserved | Nhận thêm request vượt quota | Tính used + reserved |
| Queue depth không có message age | Không biết backlog có bị kẹt hay không | Theo dõi oldest age và throughput |
| Tăng pool/worker vô hạn | Làm dependency quá tải | Tìm bottleneck và giới hạn concurrency |
| Dùng resource ID làm metric label | Cardinality cao và tốn storage | Đưa định danh vào logs/traces |
| Cache quota/expiry stale | Quyết định capacity sai | Theo dõi freshness của telemetry |
| Không có runbook | Người trực mất thời gian tìm cách xử lý | Gắn runbook, owner và dashboard vào alert |
| Silence alert không thời hạn | Bỏ lỡ sự cố thật | Silence có thời hạn, owner và lý do |

## 25. Nguyên tắc cần ghi nhớ

Cảnh báo cho service broker phải phản ánh trạng thái nghiệp vụ và capacity thực tế, không chỉ trạng thái của HTTP server. Operation kéo dài cần được phát hiện qua age, heartbeat, queue và terminal failure; credential rotation cần được theo dõi theo từng stage và xác minh credential đang được dùng; cạn tài nguyên cần được đo bằng headroom, reservation và saturation ở provider lẫn broker runtime.

Khi triển khai **SPRING_CLOUD_SERVICE_BROKER**, hãy áp dụng các nguyên tắc:

- Định nghĩa SLO và time budget theo operation type, service plan và provider.
- Phân biệt retryable failure, terminal failure và unknown outcome.
- Theo dõi operation state, oldest age, retry, reconciliation và worker heartbeat.
- Không coi HTTP 202 là hoàn tất backend.
- Instrument credential rotation theo stage, expiry, active version và provider auth result.
- Không ghi secret vào metric, log, trace hoặc alert notification.
- Theo dõi quota used, reserved, limit và headroom.
- Giám sát queue age, connection pool, database storage, runtime và Kubernetes capacity.
- Dùng labels có cardinality giới hạn; tra cứu resource cụ thể qua log/trace có kiểm soát.
- Phân cấp severity theo blast radius và thời gian còn lại để xử lý.
- Gắn runbook, dashboard, owner và routing cho từng alert.
- Kiểm thử rule, notification, recovery và telemetry missing trước khi đưa vào paging.

Một hệ thống cảnh báo tốt giúp đội vận hành phát hiện sự cố trước khi platform và người dùng bị ảnh hưởng diện rộng, xác định đúng lớp đang hỏng và phục hồi có kiểm soát mà không tạo thêm tài nguyên trùng, làm lộ credential hoặc khiến broker quá tải hơn.

