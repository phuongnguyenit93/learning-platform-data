# Triển khai thử trên một phần lưu lượng và theo dõi chất lượng

Đưa ứng dụng Java dùng CRaC vào production không nên bắt đầu bằng việc chuyển toàn bộ traffic sang các tiến trình vừa restore. Dù checkpoint và restore đã chạy thành công trong môi trường thử nghiệm, production còn có tải thực, dữ liệu người dùng, backend dùng chung, session kéo dài, cache thay đổi và các đợt scale-out đồng thời. Cách triển khai an toàn là đưa một nhóm instance được restore vào phục vụ một phần lưu lượng, giữ nhóm khởi động bình thường làm đối chứng, theo dõi chất lượng trong một khoảng thời gian đủ dài rồi mới tăng tỷ lệ.

Đây là một dạng canary rollout. Nhóm canary sử dụng checkpoint image và quy trình restore; nhóm control tiếp tục cold start theo cách triển khai hiện tại. Hai nhóm phục vụ cùng phiên bản ứng dụng và cùng hợp đồng API để có thể so sánh. Nếu canary cho kết quả tốt và không làm xấu SLO, có thể tăng dần tỷ lệ traffic. Nếu chất lượng giảm, bộ điều phối chuyển traffic về nhóm control và dừng mở rộng.

Canary không chỉ đo thời gian restore. Cần theo dõi time-to-readiness, first-request latency, lỗi request, p95/p99, dependency recovery, memory/CPU, cache freshness và các chỉ số nghiệp vụ. Mục tiêu là chứng minh tiến trình vừa restore phục vụ đúng và ổn định dưới tải thật, đồng thời có đường quay lại rõ ràng.

## 1. Mô hình canary cho CRaC

Trong mô hình đơn giản, có hai cohort:

- **Control:** instance được tạo từ image/container bình thường và khởi động JVM từ đầu.
- **Canary:** instance được tạo bằng cách restore từ checkpoint image đã chuẩn bị.

Cả hai nhóm nên dùng cùng application release, cấu hình nghiệp vụ, dependency và giới hạn tài nguyên. Khác biệt chính cần đo là cách tiến trình được đưa tới trạng thái phục vụ. Nếu nhóm canary dùng JDK mới hơn, CPU khác, heap khác hoặc backend khác, kết quả sẽ không còn phản ánh riêng tác động của CRaC.

~~~mermaid
flowchart TD
    U[Client traffic] --> G[Ingress / gateway / service mesh]
    G -->|Control weight| C[Cold-start Deployment]
    G -->|Canary weight| R[CRaC restore Deployment]
    C --> DB[(Shared dependencies)]
    R --> DB
    C --> M[Metrics and traces]
    R --> M
    M --> D[Dashboard and rollout gates]
    D -->|Healthy: increase weight| G
    D -->|Unhealthy: rollback| G
~~~

Traffic được chia ở ingress, gateway hoặc service mesh. Cách chia cụ thể phụ thuộc nền tảng; điều quan trọng là xác định được request nào thuộc cohort nào và có thể thay đổi tỷ lệ mà không phải sửa logic nghiệp vụ.

### 1.1. Phân biệt canary rollout và benchmark

Benchmark thường cố định workload và môi trường để so sánh hiệu năng. Canary rollout đưa một nhóm nhỏ vào production để kiểm tra hành vi với traffic, dữ liệu và dependency thật. Hai hoạt động bổ sung cho nhau:

- Benchmark giúp biết restore nhanh hơn cold start bao nhiêu và xác định giới hạn kỹ thuật.
- Canary giúp xác nhận chất lượng thực tế, bao gồm các lỗi hiếm, cache stale, reconnect, session và tải backend.

Không dùng canary làm lần kiểm thử đầu tiên cho một checkpoint image chưa từng restore thành công. Trước đó phải có kiểm thử image thật trong môi trường tương thích, smoke test và quy trình rollback đã diễn tập.

## 2. Điều kiện cần có trước khi đưa canary vào production

Trước khi chia traffic, cần chuẩn bị các thành phần sau:

1. **Checkpoint image có định danh:** biết image được tạo từ application release, JDK, OS, CPU profile, native library và cấu hình nào.
2. **Quy trình restore lặp lại được:** có thể tạo thêm instance từ image, kiểm tra callback và xác định trạng thái thất bại.
3. **Readiness đúng nghĩa:** instance chỉ nhận traffic sau khi Resource bắt buộc đã phục hồi và dependency cần thiết đã được xác minh.
4. **Control cohort:** vẫn có thể tạo instance cold start từ cùng application release để làm đối chứng.
5. **Traffic routing có thể điều chỉnh:** thay đổi weight hoặc tắt canary mà không cần thay đổi client.
6. **Observability:** metric, log và trace có nhãn cohort, release, checkpoint ID và instance ID.
7. **Capacity dự phòng:** đủ tài nguyên để control cohort tiếp tục phục vụ nếu canary bị rút khỏi traffic.
8. **Rollback đã thử:** biết cách đưa traffic về control và xử lý các instance canary đang chạy.

Nếu một trong các điều kiện này chưa có, rollout sẽ khó phân biệt lỗi do CRaC với lỗi của ứng dụng hoặc hạ tầng.

### 2.1. Dùng cùng một application release

Canary và control nên chạy cùng application artifact, cấu hình nghiệp vụ và schema tương thích. Nếu canary chạy bản code mới đồng thời dùng CRaC, còn control chạy bản cũ, một lỗi có thể xuất phát từ thay đổi code thay vì restore.

Khi cần kiểm tra cả release mới lẫn CRaC, hãy tách thành hai thay đổi có thể đo riêng:

- Trước tiên triển khai release mới bằng cold start và xác nhận chất lượng.
- Sau đó tạo checkpoint từ chính release đó và canary cách khởi chạy bằng CRaC.

Nếu bắt buộc thử đồng thời, cần có ma trận cohort riêng để phân biệt biến số release và biến số restore.

### 2.2. Xác định checkpoint image và thời hạn sử dụng

Checkpoint image nên được xem là artifact gắn với một runtime profile. Metadata nên ghi ít nhất:

- Application version hoặc commit/build ID.
- JDK vendor, version, build và JVM flags.
- OS/kernel và checkpoint engine/CRIU version theo môi trường tạo image.
- CPU architecture và feature baseline.
- Native libraries, Java agents và profiler versions.
- Cấu hình quan trọng, schema version và loại dependency.
- Thời điểm tạo image và thời gian warm-up.
- Phiên bản quy trình Resource callback.

Không dùng image cũ sau khi application, JDK, native dependency hoặc CPU profile thay đổi mà chưa xác nhận tương thích. Đặt chính sách hết hạn image; image quá cũ có thể chứa cache, credential hoặc trạng thái runtime không còn phù hợp.

## 3. Chọn traffic cohort và cách chia lưu lượng

Traffic split có thể thực hiện theo tỷ lệ ngẫu nhiên, hash ổn định theo người dùng/tenant hoặc quy tắc theo loại request. Chọn cách chia theo đặc tính của ứng dụng.

### 3.1. Chia theo tỷ lệ ở gateway

Đây là cách đơn giản khi request độc lập và không cần giữ session affinity. Ví dụ, 95% traffic vào control và 5% vào canary. Gateway/service mesh quyết định đích đến theo weight.

Ưu điểm:

- Có thể tăng/giảm tỷ lệ mà không sửa client.
- Có thể rút canary khỏi traffic nhanh khi phát hiện lỗi.
- Dễ quan sát tỷ lệ request thực tế giữa hai cohort.

Hạn chế:

- Một user có thể lần lượt đi qua cả hai cohort nếu routing không sticky.
- Session lưu trong memory của instance có thể không tồn tại ở cohort còn lại.
- Các request phụ thuộc cùng một chuỗi nghiệp vụ có thể bị chia sang hai nhóm.

### 3.2. Hash ổn định theo user hoặc tenant

Với ứng dụng có session hoặc workflow nhiều bước, có thể hash theo user ID, tenant ID hoặc một key ổn định để cùng một nhóm người dùng luôn vào cùng cohort trong thời gian thử nghiệm.

Ví dụ, 5% tenant được đưa vào canary và phần còn lại ở control. Cách này giúp giảm việc một phiên làm việc đổi instance giữa chừng. Tuy nhiên, phải bảo đảm:

- Key dùng để hash ổn định và không chứa dữ liệu nhạy cảm trong log.
- Phân bố tenant đủ cân bằng; một tenant lớn không làm canary nhận tải bất thường.
- Có thể chuyển nhóm người dùng về control khi rollback.
- Session state và dữ liệu ghi vẫn tương thích giữa hai cohort.

Không dùng hash ổn định nếu nó khiến một nhóm khách hàng quan trọng chịu toàn bộ rủi ro canary mà không có giới hạn tải.

### 3.3. Chọn loại traffic phù hợp

Trong giai đoạn đầu, có thể chọn request đọc, không có side effect hoặc một nhóm endpoint ít rủi ro. Sau khi chất lượng ổn định, mở rộng sang các luồng phức tạp hơn.

| Loại traffic | Cách tiếp cận |
|---|---|
| Read-only request | Thường phù hợp để bắt đầu, nhưng vẫn phải kiểm tra cache freshness và consistency. |
| Request ghi dữ liệu | Chỉ đưa vào khi schema, idempotency, retry và rollback đã rõ. |
| Workflow nhiều bước | Dùng sticky routing hoặc bảo đảm session/state dùng chung. |
| WebSocket/SSE/streaming | Kiểm tra reconnect/resume và thời gian sống của kết nối; không chỉ dựa vào request weight. |
| Background consumer | Không chia cùng message cho hai consumer group chỉ để tạo traffic split; cần partition/ownership rõ ràng. |
| Scheduled job | Chỉ một cohort nên giữ quyền chạy job ghi tại một thời điểm, trừ khi job được thiết kế idempotent và có leader election. |

### 3.4. Không tạo duplicate work khi chia message

Traffic HTTP có thể được route theo request, nhưng message consumer và scheduled job có semantics khác. Nếu control và canary cùng subscribe một topic bằng hai consumer group riêng, cả hai có thể xử lý cùng một message và tạo side effect hai lần.

Với worker nền, hãy chọn một trong các cách:

- Chỉ control xử lý message trong giai đoạn canary HTTP ban đầu.
- Dùng partition assignment để phân chia message độc quyền.
- Dùng consumer group và cơ chế handoff được thiết kế rõ.
- Dùng idempotency key và storage chống xử lý lặp nếu nghiệp vụ cho phép.
- Tắt scheduled job trên canary cho tới khi được chuyển quyền.

Không coi việc giảm HTTP traffic weight là đủ để cô lập mọi side effect của canary.

## 4. Triển khai hai cohort trong Kubernetes

Một mẫu triển khai là tạo hai Deployment từ cùng application image:

- **orders-control:** chạy lệnh Java khởi động bình thường.
- **orders-crac:** khôi phục từ checkpoint image đã chuẩn bị.

Hai Deployment có thể dùng chung Service phụ thuộc và cùng application release. Chúng có nhãn cohort khác nhau để metric và log phân biệt.

Ví dụ rút gọn về Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-control
spec:
  replicas: 9
  selector:
    matchLabels:
      app: orders
      cohort: control
  template:
    metadata:
      labels:
        app: orders
        cohort: control
        release: "2026.11.13"
    spec:
      containers:
        - name: app
          image: example/orders:2026.11.13
          command: ["java", "-jar", "/app/orders.jar"]
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            periodSeconds: 5
            failureThreshold: 3
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-crac
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders
      cohort: crac
  template:
    metadata:
      labels:
        app: orders
        cohort: crac
        release: "2026.11.13"
    spec:
      containers:
        - name: app
          image: example/orders-crac:2026.11.13
          command: ["/opt/crac/restore-entrypoint"]
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            periodSeconds: 5
            failureThreshold: 3
~~~

**restore-entrypoint** chỉ là placeholder cho cách restore của nền tảng, không phải lệnh chuẩn của CRaC. Trong thực tế, checkpoint/restore có thể do container runtime, CRIU integration hoặc một controller chuyên dụng thực hiện. Không thay command của container bằng một script giả định nếu runtime yêu cầu khởi động/restore theo cách khác.

### 4.1. Tách Service theo cohort

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-control
spec:
  selector:
    app: orders
    cohort: control
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: v1
kind: Service
metadata:
  name: orders-crac
spec:
  selector:
    app: orders
    cohort: crac
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Service riêng giúp gateway định tuyến rõ cohort. Readiness probe phải phản ánh khả năng phục vụ thật; Pod chưa ready sẽ không được endpoint routing thông thường đưa vào Service.

### 4.2. Ví dụ chia traffic bằng Istio

Nếu cluster dùng Istio, VirtualService có thể chia weight giữa hai Service:

~~~yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: orders
spec:
  hosts:
    - orders.example.internal
  http:
    - route:
        - destination:
            host: orders-control
            port:
              number: 80
          weight: 95
        - destination:
            host: orders-crac
            port:
              number: 80
          weight: 5
~~~

Đây là ví dụ cấu hình Istio; cluster cần có Istio Gateway/route phù hợp và hai Service phải tồn tại. Weight là tỷ lệ định tuyến mục tiêu, không đảm bảo đúng tuyệt đối trong mọi cửa sổ nhỏ do số request thấp hoặc cách proxy phân phối. Kiểm tra tỷ lệ thực tế từ metric phía server.

Nếu dùng NGINX Ingress, Gateway API, Argo Rollouts hoặc nền tảng khác, hãy dùng cơ chế traffic splitting tương ứng. Không cần thay đổi ứng dụng để triển khai canary nếu tầng routing đã hỗ trợ.

## 5. Readiness và liveness sau restore

Một Pod vừa restore có thể đã có process nhưng vẫn chưa đủ điều kiện nhận traffic. Readiness phải phản ánh trạng thái recovery của ứng dụng.

### 5.1. Readiness theo capability bắt buộc

Readiness endpoint nên kiểm tra những dependency bắt buộc để phục vụ request chính, ví dụ:

- Resource callback đã hoàn tất.
- Database pool có thể cấp connection và truy vấn kiểm tra thành công.
- Cache bắt buộc có dữ liệu hợp lệ hoặc có fallback.
- HTTP client/service discovery hoạt động.
- Message consumer hoặc worker chỉ được start khi cần.
- Recovery gate đã mở cho các capability được route.

Không nhất thiết mọi dependency tùy chọn phải sẵn sàng mới bật toàn bộ ứng dụng. Có thể biểu diễn readiness theo capability hoặc tắt route tới chức năng đang degraded. Tuy nhiên, nếu readiness endpoint chỉ trả 200 khi JVM còn sống, gateway có thể gửi traffic quá sớm.

### 5.2. Phân biệt readiness và liveness

- **Liveness** trả lời tiến trình có còn sống và có thể tiếp tục không. Liveness không nên fail chỉ vì database tạm thời mất kết nối, nếu ứng dụng có thể phục hồi.
- **Readiness** trả lời instance có thể nhận traffic hay chưa. Trong thời gian RESTORING, readiness nên false.
- **Startup probe** có thể bảo vệ ứng dụng có startup/recovery kéo dài, tránh liveness probe khởi động quá sớm rồi restart nhầm.

Khi readiness false, cần bảo đảm gateway không route request mới tới Pod đó. Nếu hệ thống dùng sidecar hoặc custom proxy, kiểm tra hành vi thực tế của nó.

### 5.3. Không mở readiness quá sớm

Một lỗi thường gặp là callback afterRestore tạo object client thành công rồi lập tức đánh dấu ready, dù kết nối tới server chưa được kiểm tra. Hãy phân biệt “client object đã tạo” với “dependency có thể phục vụ request”. Có thể thực hiện health check nhẹ có timeout trước khi mở gate.

Đừng chạy health check gây side effect. Kiểm tra database nên dùng truy vấn đọc an toàn; kiểm tra broker nên xác minh kết nối/metadata mà không tạo message nghiệp vụ.

## 6. Theo dõi chất lượng: SLI, SLO và metric CRaC

Canary cần một dashboard có thể so sánh hai cohort trên cùng khoảng thời gian và workload. Nên tổ chức metric thành bốn nhóm.

### 6.1. Chất lượng request

- Request rate theo cohort.
- Error rate theo status class và loại exception.
- Timeout, connection reset và retry rate.
- Latency p50, p95, p99.
- First-request latency sau khi readiness bật.
- Tỷ lệ request thành công theo endpoint/capability.

### 6.2. Chất lượng restore

- Số lần restore thành công/thất bại.
- Thời gian restore engine nếu nền tảng cung cấp.
- Thời gian từng afterRestore callback.
- Restore-to-ready duration.
- Checkpoint image age và image version.
- Tỷ lệ instance phải fallback sang cold start.
- Lỗi native library, file descriptor, socket hoặc CPU/runtime compatibility.

### 6.3. Tài nguyên và dependency

- CPU usage, throttling và load.
- Heap used/committed, GC pause và allocation rate.
- RSS, native memory và container memory peak.
- Thread count, executor queue depth và scheduler lag.
- Connection pool active/idle/pending và connection creation rate.
- Database latency, saturation, connection count.
- Cache hit/miss, refresh duration và stale entry count.
- Broker lag, consumer rebalance và processing delay.

### 6.4. Chất lượng nghiệp vụ

- Tỷ lệ giao dịch hoàn tất.
- Tỷ lệ duplicate hoặc idempotency conflict.
- Số message xử lý lặp hoặc bị bỏ sót.
- Kết quả kiểm tra dữ liệu sau ghi.
- Tỷ lệ workflow bị gián đoạn.
- Các metric đặc thù sản phẩm như thanh toán, đặt hàng hoặc xác thực.

Một canary có HTTP 200 rate tốt nhưng tạo duplicate message hoặc trả dữ liệu cache cũ vẫn là canary không đạt chất lượng.

## 7. Gắn nhãn cohort vào metric, log và trace

Mọi metric quan trọng nên có nhãn để phân biệt control và crac. Các nhãn thường hữu ích:

- **cohort:** control hoặc crac.
- **release:** application release/build ID.
- **checkpoint_id:** image identifier hoặc version, nếu cardinality được kiểm soát.
- **restore_attempt:** ID của lần restore hoặc instance.
- **instance:** pod/instance ID.
- **region/zone:** vùng triển khai nếu cần so sánh.

Không thêm user ID, session ID hoặc checkpoint ID có cardinality không giới hạn vào mọi metric label. Dùng trace/log để lưu định danh chi tiết; metric nên dùng tập nhãn có kiểm soát.

Ví dụ structured log:

~~~json
{
  "event": "application.ready",
  "cohort": "crac",
  "release": "2026.11.13",
  "checkpointId": "orders-2026-11-13-a17",
  "instance": "orders-crac-7d8c9",
  "restoreToReadyMs": 1240
}
~~~

Đây là dữ liệu minh họa. Không ghi credential, request body hoặc dữ liệu cá nhân vào log canary.

## 8. Ví dụ Prometheus query để so sánh cohort

Tên metric dưới đây là ví dụ cho instrumentation của ứng dụng. Hãy thay bằng tên metric thực tế của hệ thống.

### 8.1. Error ratio theo cohort

~~~promql
sum by (cohort) (
  rate(http_server_requests_total{status=~"5.."}[5m])
)
/
sum by (cohort) (
  rate(http_server_requests_total[5m])
)
~~~

Nếu canary có error ratio cao hơn control, cần phân tích theo endpoint, status code và exception trước khi quyết định rollback. Với traffic rất thấp, một lỗi đơn lẻ có thể làm tỷ lệ dao động mạnh; hãy kết hợp số lượng request tuyệt đối và thời gian quan sát.

### 8.2. p95 latency theo cohort

~~~promql
histogram_quantile(
  0.95,
  sum by (le, cohort) (
    rate(http_server_request_duration_seconds_bucket[5m])
  )
)
~~~

Có thể dùng 0.99 để xem p99 nếu histogram có đủ bucket và số lượng mẫu đủ lớn. So sánh cùng endpoint hoặc cùng nhóm request; trộn các endpoint có latency khác nhau có thể tạo kết luận sai.

### 8.3. Restore-to-ready duration

~~~promql
histogram_quantile(
  0.95,
  sum by (le, cohort) (
    rate(application_restore_to_ready_seconds_bucket[15m])
  )
)
~~~

Metric này thường chỉ có ở cohort CRaC. Có thể theo dõi p50/p95 theo release hoặc image profile, nhưng không cần gắn image ID có cardinality cao vào mọi series nếu hệ thống có nhiều image.

### 8.4. Restore failure rate

~~~promql
sum by (cohort) (
  rate(application_restore_failures_total[15m])
)
~~~

Đây là tốc độ lỗi, không phải tỷ lệ thất bại trên tổng số lần restore. Để có failure ratio, cần thêm counter tổng số restore attempts và chia hai metric theo cùng label/window.

### 8.5. CPU và memory

Theo dõi CPU usage, CPU throttling, container memory working set, JVM heap và GC theo cohort. Nếu canary dùng ít replica hơn control, hãy chuẩn hóa theo request rate hoặc request count để tránh kết luận từ tổng CPU tuyệt đối.

## 9. Đặt rollout gate trước khi tăng traffic

Không nên tăng traffic chỉ vì canary đã chạy đủ một khoảng thời gian. Cần có điều kiện rõ ràng về chất lượng và lượng mẫu.

Một gate thường gồm:

- Error rate không vượt ngưỡng tuyệt đối và không xấu hơn control quá mức cho phép.
- p95/p99 không vượt SLO hoặc regression budget.
- Không có lỗi restore/callback nghiêm trọng.
- Restore-to-ready nằm trong mục tiêu vận hành.
- Không có OOM, restart loop hoặc CPU throttling bất thường.
- Dependency saturation không tăng ngoài dự kiến.
- Metric nghiệp vụ không xuất hiện duplicate, loss hoặc inconsistency.
- Đã có đủ request và thời gian quan sát để kết luận.

Ví dụ bảng gate; các giá trị cần được đặt theo SLO thực tế, không phải ngưỡng chuẩn chung:

| Chỉ số | Điều kiện tăng traffic | Điều kiện dừng/rollback |
|---|---|---|
| HTTP 5xx ratio | Không cao hơn control vượt regression budget. | Vượt error budget hoặc tăng liên tục qua các cửa sổ. |
| p95/p99 latency | Nằm trong SLO và không regression đáng kể. | Vượt SLO hoặc tail latency tăng bền vững. |
| Restore success | Tất cả lần thử trong giai đoạn đạt mục tiêu đã đặt. | Restore/callback failure vượt ngưỡng hoặc có lỗi nghiêm trọng. |
| Time-to-ready | Nằm trong mục tiêu startup/scale-out. | Quá deadline hoặc có xu hướng tăng theo image age. |
| Memory/CPU | Có headroom và không tăng bất thường. | OOM, eviction, throttling hoặc saturation. |
| Business correctness | Không tăng duplicate/loss hoặc sai lệch dữ liệu. | Bất kỳ lỗi correctness nghiêm trọng nào. |

Với các lỗi correctness như ghi trùng, mất dữ liệu hoặc sai quyền truy cập, không cần đợi đủ thời gian soak mới rollback.

## 10. Tăng traffic theo từng nấc

Một lộ trình minh họa:

| Giai đoạn | Traffic vào CRaC cohort | Mục tiêu |
|---|---:|---|
| Baseline | 0% | Thu thập control metrics và xác nhận dashboard. |
| Canary 1 | 1% | Xác nhận routing, readiness và lỗi cơ bản. |
| Canary 2 | 5% | Quan sát first-request, callback và dependency dưới tải nhỏ. |
| Canary 3 | 10% | Kiểm tra latency/error và tải backend. |
| Canary 4 | 25% | Xác nhận hành vi ở tải đủ lớn và nhiều loại request. |
| Canary 5 | 50% | So sánh cân bằng hai cohort trong cùng điều kiện. |
| Rollout | 100% | Chỉ sau khi các gate và thời gian soak đều đạt. |

Đây là ví dụ, không phải lịch bắt buộc. Với hệ thống ít traffic, 1% có thể chỉ tạo vài request và không đủ bằng chứng. Khi đó có thể dùng tỷ lệ lớn hơn trong một nhóm tenant nội bộ hoặc kéo dài thời gian quan sát. Với hệ thống có tải lớn, bắt đầu nhỏ hơn để giới hạn blast radius.

### 10.1. Soak time và sample size

Mỗi nấc cần đủ thời gian để quan sát:

- Request trong giờ cao điểm và thấp điểm nếu tải thay đổi theo thời gian.
- Cache refresh và TTL cycle.
- Scheduled task có chu kỳ dài.
- Token refresh, connection rotation hoặc certificate reload.
- Worker/consumer rebalance.
- Các luồng nghiệp vụ không xuất hiện liên tục.

Không dùng một cửa sổ 5 phút để kết luận về lỗi chỉ xảy ra mỗi giờ hoặc mỗi ngày. Soak time nên dựa trên chu kỳ hoạt động của hệ thống và rủi ro cần kiểm tra.

### 10.2. Không tăng traffic khi canary thiếu tải

Nếu canary nhận quá ít request, các percentile và error ratio không đáng tin cậy. Có thể bổ sung synthetic probe hoặc replay workload đã ẩn danh để kiểm tra chức năng, nhưng không trộn kết quả synthetic với production metrics mà không gắn nhãn riêng.

## 11. Theo dõi chất lượng sau restore theo từng giai đoạn

Nên chia dashboard thành ba cửa sổ: ngay sau restore, trong giai đoạn ổn định và steady state.

### 11.1. Ngay sau restore

Theo dõi:

- Restore success/failure và duration.
- afterRestore callback duration theo Resource.
- Thời gian tới readiness.
- Connection creation, TLS handshake và authentication failures.
- Cache validation/refresh và số entry bị loại.
- First-request latency và error.
- CPU/memory peak trong lúc recovery.

Đây là giai đoạn dễ bộc lộ stale socket, credential hết hạn, cache cũ hoặc readiness mở quá sớm.

### 11.2. Giai đoạn soak

Theo dõi các chu kỳ kéo dài hơn:

- Memory leak hoặc RSS tăng dần.
- Scheduler/task chạy trùng.
- Retry storm và circuit breaker mở liên tục.
- Connection pool leak hoặc pending queue tăng.
- Cache stampede và refresh bất thường.
- Message lag hoặc duplicate processing.
- Log/telemetry exporter không reconnect.

### 11.3. Steady state

Khi canary đã ổn định, so sánh p50/p95/p99, throughput, CPU/request, allocation, GC, error ratio và business metrics với control. Nếu restore giúp startup nhanh nhưng steady-state latency hoặc resource usage xấu hơn, cần xác định nguyên nhân trước khi rollout rộng.

## 12. Rollback và fallback

Rollback phải được chuẩn bị trước khi bật traffic canary. Mục tiêu đầu tiên là ngừng đưa request mới vào nhóm restore và bảo đảm nhóm control còn đủ capacity.

Quy trình cơ bản:

1. Đặt traffic weight của canary về 0% tại gateway/service mesh.
2. Xác nhận request mới chỉ đi vào control.
3. Giữ readiness và liveness đúng trạng thái; không restart hàng loạt nếu chưa cần.
4. Dừng tạo thêm instance từ checkpoint image đang nghi ngờ.
5. Thu thập log, trace, metric và metadata của image để điều tra.
6. Nếu cần, drain canary instance đang phục vụ và kết thúc chúng theo quy trình an toàn.
7. Chuyển scale/capacity về nhóm cold start để đáp ứng traffic.
8. Chỉ bật lại canary sau khi có image hoặc bản sửa đã kiểm thử.

### 12.1. Fallback sang cold start

Một số nền tảng có thể tự động thử restore rồi fallback sang cold start nếu restore thất bại. Nếu dùng cơ chế này, cần ghi metric riêng:

- Restore attempt.
- Restore failure reason.
- Cold-start fallback count.
- Time-to-ready sau fallback.

Nếu không tách metric, dashboard có thể cho thấy instance cuối cùng vẫn ready và che mất tỷ lệ restore thất bại. Fallback cũng có thể làm tăng tải CPU và kéo dài startup, vì vậy cần capacity dự phòng.

### 12.2. Rollback code và dữ liệu dùng chung

Hai cohort thường dùng chung database và backend. Nếu canary đã ghi dữ liệu, chuyển traffic về control không tự hoàn tác các thay đổi đó. Vì vậy:

- Schema migration cần tương thích ngược trong thời gian rollout.
- API và event format phải tương thích giữa hai cohort.
- Thao tác ghi cần idempotency và audit.
- Không để canary chạy job nền có thể gây side effect ngoài traffic routing.
- Có kế hoạch xử lý message hoặc workflow đang dở.

Rollback traffic là thao tác định tuyến, không phải rollback dữ liệu nghiệp vụ.

## 13. Phân tích sự cố theo cohort

Khi canary xấu hơn control, hãy phân loại theo symptom:

| Dấu hiệu | Nguyên nhân cần kiểm tra |
|---|---|
| Restore-to-ready tăng | Image distribution chậm, callback lâu, dependency reconnect hoặc readiness check quá nặng. |
| First-request latency cao | Lazy initialization, cache miss, pool chưa warm hoặc code path chưa JIT. |
| 5xx tăng ngay sau restore | Stale connection, credential/TLS, Resource callback hoặc readiness mở sớm. |
| p99 tăng nhưng p50 bình thường | Một số dependency timeout, pool queue, GC pause hoặc tail request. |
| CPU tăng trong canary | Recovery/warm-up chạy lại, retry storm, compilation hoặc container throttling. |
| RSS cao hơn control | Heap state được giữ, native memory, thread count hoặc memory mapping. |
| Duplicate job/message | Consumer hoặc scheduler chạy đồng thời ở hai cohort. |
| Cache trả dữ liệu cũ | Cache freshness/version không được kiểm tra sau restore. |
| Restore failure nhưng Pod vẫn ready | Fallback che giấu lỗi hoặc readiness không phản ánh restore outcome. |
| Chỉ lỗi trên một node | CPU/kernel/CRIU/runtime/storage profile khác node còn lại. |

So sánh log và metric theo cohort, release, checkpoint_id, node và instance. Nếu lỗi chỉ xuất hiện trên một nhóm node, kiểm tra runtime fingerprint trước khi sửa code ứng dụng.

## 14. Ví dụ runbook quyết định rollout

Một runbook đơn giản có thể dùng các quyết định sau:

| Tình huống | Hành động |
|---|---|
| Restore thành công, readiness đạt, SLO ổn định, đủ sample | Giữ soak rồi tăng weight một nấc. |
| Restore chậm nhưng request quality tốt | Giữ nguyên weight, điều tra callback/image distribution trước khi tăng. |
| Restore failure nhưng fallback cold start thành công | Giữ traffic thấp hoặc 0%; phân tích failure rate và fallback capacity. |
| 5xx hoặc p99 vượt ngưỡng trong nhiều cửa sổ | Đưa canary weight về 0%, giữ artifact và điều tra. |
| Lỗi correctness hoặc security | Rollback ngay, không đợi hết soak window. |
| Dependency backend bị saturation do restore đồng loạt | Giảm restore concurrency, giảm canary weight và điều chỉnh reconnect backoff. |
| Chỉ một CPU/node profile lỗi | Ngừng scheduling canary lên profile đó và kiểm tra compatibility. |
| Metric không đủ hoặc dashboard mất nhãn cohort | Không tăng traffic cho tới khi observability được sửa. |

Mỗi hành động cần có owner, thời điểm, lý do và checkpoint/image ID liên quan để audit sau sự cố.

## 15. Bảo vệ control cohort và backend trong lúc canary

Canary có thể làm tăng tải tổng thể thay vì chỉ chuyển một phần traffic, đặc biệt khi restore kích hoạt reconnect đồng loạt.

Hãy kiểm soát:

- Số instance restore đồng thời.
- Số connection mới mỗi giây tới database/broker.
- Warm-up hoặc cache refresh concurrency.
- Retry backoff và jitter.
- CPU/memory headroom trên node.
- Image distribution throughput.
- Control capacity nếu canary bị rút khỏi traffic.

Không tăng số replica canary và traffic weight cùng lúc nếu chưa biết tác động của từng thay đổi. Có thể trước tiên giữ số replica ổn định và chỉ đổi routing weight, sau đó mới thử scale-out.

## 16. Báo cáo kết quả canary

Sau mỗi giai đoạn, lưu một báo cáo ngắn có thể so sánh:

- Release và checkpoint image ID.
- Thời gian bắt đầu/kết thúc, cluster/region và node profile.
- Traffic weight và số request thực tế từng cohort.
- Restore success/failure và fallback count.
- Restore-to-ready, first-request p50/p95/p99.
- Request error ratio và throughput.
- CPU, memory, GC, connection pool và backend saturation.
- Business correctness metrics.
- SLO impact và error budget consumed.
- Quyết định: giữ, tăng weight, dừng hoặc rollback.
- Các issue còn mở và người phụ trách.

Không chỉ báo cáo phần trăm traffic đã chuyển. Cần có số request, số instance và thời gian quan sát để người đọc hiểu độ tin cậy của kết luận.

## 17. Những lỗi triển khai canary thường gặp

**Chuyển 100% traffic ngay sau một lần restore thành công.** Một lần thành công không kiểm tra được tải thật, cache TTL, token refresh hoặc các job chạy theo chu kỳ. Hãy tăng theo nấc và có soak time.

**Canary và control chạy hai release khác nhau.** Khi có lỗi, không thể phân biệt tác động của CRaC với thay đổi code. Giữ release giống nhau trong thử nghiệm này.

**Không gắn nhãn cohort vào metric.** Dashboard trộn hai nhóm và che mất regression. Thêm nhãn cohort/release/image có cardinality kiểm soát.

**Chỉ theo dõi restore engine duration.** Người dùng quan tâm lúc instance nhận traffic. Đo restore-to-ready và first-request latency.

**Readiness chỉ kiểm tra process sống.** Gateway route request trước khi database/cache/client sẵn sàng. Dùng readiness theo dependency bắt buộc.

**Chia message consumer giống HTTP request.** Hai consumer group có thể xử lý cùng message. Quản lý partition ownership hoặc chỉ bật một cohort.

**Rollback traffic nhưng quên job nền.** Scheduled job hoặc consumer ở canary vẫn có thể ghi dữ liệu. Dừng hoặc chuyển quyền các worker nền riêng.

**Fallback cold start che giấu restore failure.** Theo dõi restore failure và fallback count riêng, không chỉ nhìn Pod ready.

**Tăng canary khi backend đang quá tải.** Reconnect hoặc cache warm-up có thể tạo tải đột biến. Giới hạn concurrency và theo dõi dependency saturation.

**Không kiểm tra checkpoint age.** Image cũ có thể chứa cache/credential không còn phù hợp. Đặt TTL và chính sách tái tạo image.

## 18. Checklist triển khai thử trên một phần lưu lượng

- [ ] Control và canary chạy cùng application release và cấu hình nghiệp vụ.
- [ ] Checkpoint image có ID, version, runtime fingerprint và thời hạn sử dụng.
- [ ] Restore image thật đã được kiểm thử trước khi vào production.
- [ ] Có đủ capacity control để phục vụ nếu canary bị rollback.
- [ ] Traffic routing có thể tăng/giảm weight nhanh.
- [ ] Cohort được gắn nhãn trong metric, log và trace.
- [ ] Readiness false trong khi Resource bắt buộc chưa phục hồi.
- [ ] Liveness không restart nhầm chỉ vì dependency tạm thời chưa sẵn sàng.
- [ ] Session, sticky routing và workflow nhiều bước được xử lý rõ.
- [ ] Message consumer và scheduled job không chạy trùng giữa hai cohort.
- [ ] Có SLI/SLO và rollout gate cho error rate, latency, restore success và correctness.
- [ ] Có đủ sample size và soak time cho các chu kỳ dài.
- [ ] Theo dõi first-request, callback duration, restore-to-ready và steady state riêng.
- [ ] Theo dõi CPU, memory, GC, pool, cache và backend saturation.
- [ ] Có metric fallback cold start riêng nếu cơ chế đó được sử dụng.
- [ ] Rollback traffic về 0% canary đã được diễn tập.
- [ ] Có kế hoạch xử lý side effect và dữ liệu đã ghi trong thời gian canary.
- [ ] Không tăng weight khi observability thiếu hoặc metric chưa đủ.
- [ ] Lưu báo cáo và checkpoint image ID cho từng nấc rollout.

## 19. Thuật ngữ cần nhớ

- **Canary rollout:** triển khai một phiên bản/cách khởi chạy cho một phần nhỏ traffic trước khi mở rộng.
- **Control cohort:** nhóm đối chứng tiếp tục chạy theo cách hiện tại, trong bài này là cold start.
- **Treatment cohort:** nhóm được thử nghiệm, trong bài này là tiến trình restore từ checkpoint.
- **Traffic weight:** tỷ lệ traffic gateway dự kiến gửi tới từng cohort.
- **Sticky routing:** giữ các request liên quan của cùng user/session/tenant đi vào cùng nhóm.
- **SLI:** chỉ số đo chất lượng dịch vụ như availability, latency hoặc error rate.
- **SLO:** mục tiêu chất lượng đặt ra cho SLI trong một khoảng thời gian.
- **Soak time:** khoảng thời gian giữ một tỷ lệ canary để quan sát lỗi và hành vi theo chu kỳ.
- **Blast radius:** phạm vi người dùng hoặc workload bị ảnh hưởng nếu canary gặp lỗi.
- **Readiness:** trạng thái instance có thể nhận traffic.
- **Fallback:** chuyển sang cách khởi động dự phòng, ví dụ cold start khi restore thất bại.
- **Checkpoint age:** thời gian từ lúc tạo checkpoint image tới lúc sử dụng restore.
- **Cohort label:** nhãn dùng để phân biệt control và canary trong telemetry.
- **Rollback:** dừng rollout và chuyển traffic về nhóm ổn định.

Triển khai CRaC trên một phần lưu lượng là cách kiểm chứng restore trong điều kiện production với blast radius được giới hạn. Hãy giữ control cohort làm đối chứng, route canary theo tỷ lệ có thể điều chỉnh, chỉ mở readiness sau khi recovery hoàn tất và theo dõi cả chất lượng request lẫn tính đúng đắn nghiệp vụ. Tăng traffic theo từng nấc khi đủ sample và SLO ổn định; nếu có lỗi correctness, restore hoặc dependency nghiêm trọng, rút canary khỏi traffic và quay về cold-start cohort trong khi giữ lại bằng chứng để điều tra.

## Tài liệu tham khảo

- [CRaC — Checkpoint and restore](https://crac.org/use/checkpoint-and-restore/): quy trình tạo checkpoint và restore trong môi trường triển khai.
- [CRaC — Best practices](https://crac.org/reference/best-practices/): quản lý Resource, dependency và trạng thái ứng dụng quanh checkpoint/restore.
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): phân biệt probe và điều kiện đưa Pod vào phục vụ.
- [Istio — Traffic Shifting](https://istio.io/latest/docs/tasks/traffic-management/traffic-shifting/): chia traffic theo weight giữa các phiên bản/service.
- [Google SRE Workbook — Canarying Releases](https://sre.google/workbook/canarying-releases/): nguyên tắc canary, chỉ số chất lượng và rollout decision.
