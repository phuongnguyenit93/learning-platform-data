# Chẩn đoán Cloud Run timeout, cold start và thiếu bộ nhớ

Một dịch vụ Java/Spring trên Cloud Run có thể hoạt động bình thường trong giờ thấp điểm, nhưng khi traffic tăng lại xuất hiện HTTP 504, thời gian phản hồi p99 tăng mạnh hoặc instance bị khởi động lại. Sau một đợt deploy, request đầu tiên của revision mới còn chậm hơn những request tiếp theo. Một số log có thể chỉ ghi nhận request timeout, trong khi nguyên nhân thực sự là JVM khởi động lâu, database connection pool cạn hoặc container vượt giới hạn memory.

Ba nhóm sự cố này có biểu hiện gần nhau nhưng cần cách điều tra khác nhau:

- **Timeout:** request không hoàn tất trong deadline ở một tầng nào đó; cần tìm thời gian bị tiêu tốn và phân biệt timeout của client, Cloud Run, ứng dụng hay dependency.
- **Cold start:** Cloud Run phải tạo instance mới, tải image và khởi tạo container/application trước khi phục vụ request; cần giảm startup latency hoặc duy trì capacity ấm.
- **Out of memory (OOM):** tiến trình hoặc container vượt ngân sách memory, có thể gây lỗi JVM, container termination, restart và request thất bại.

Trong module **CLOUD_PROVIDERS_GCP**, bài học liên hệ Cloud Run với Java/Spring, IAM, VPC, Cloud SQL, autoscaling, Cloud Monitoring và SRE. Mục tiêu là xây một quy trình chẩn đoán dựa trên metrics, request logs, system logs và traces, sau đó thay đổi timeout, concurrency, CPU, memory hoặc startup policy theo bằng chứng.

Sau bài học, bạn có thể:

- Phân biệt HTTP 504 do Cloud Run request timeout với timeout trong ứng dụng hoặc dependency.
- Đọc request logs, container logs, system logs và các Cloud Run metrics quan trọng.
- Tìm nguyên nhân cold start từ image, JVM, Spring context, dependency initialization và network.
- Sử dụng minimum instances, startup CPU boost, startup probe và concurrency đúng mục đích.
- Chẩn đoán memory pressure, JVM heap OOM và container memory limit exceeded.
- Đặt JVM heap dưới container memory limit và tính cả native/direct memory, thread stack, cache và file tạm.
- Thiết kế timeout budget, retry, idempotency và background processing an toàn.
- Xây runbook xử lý sự cố và kiểm chứng cải thiện bằng SLO cùng chi phí.

## 1. Nhận diện triệu chứng trước khi thay đổi cấu hình

Không nên tăng timeout, memory và CPU cùng lúc ngay khi thấy 504. Trước tiên, phân loại triệu chứng:

| Triệu chứng quan sát | Nhóm nguyên nhân cần kiểm tra |
|---|---|
| HTTP 504 sau một khoảng thời gian khá ổn định | Cloud Run request timeout, proxy/client deadline hoặc dependency timeout |
| Request đầu sau khi idle/deploy chậm, request tiếp theo nhanh | Cold start, JVM/Spring initialization, image pull hoặc connection warm-up |
| Instance restart, system log báo memory limit exceeded | Container vượt memory limit |
| Log Java có \`java.lang.OutOfMemoryError\`, nhưng instance chưa bị Cloud Run kill | JVM heap/native memory pressure ở cấp ứng dụng |
| CPU cao, p95 tăng, memory bình thường | CPU-bound code, serialization, query hoặc concurrency quá cao |
| CPU thấp, request vẫn chờ lâu | Pool exhaustion, database/network wait, lock contention hoặc downstream timeout |
| Chỉ một revision lỗi sau deploy | Khác biệt image, environment, JVM flags, traffic split hoặc cấu hình mới |
| Chỉ peak traffic lỗi | Max instances, concurrency, connection pool, quota hoặc dependency capacity |

### Ba câu hỏi đầu tiên

1. **Request có tới container không?** Nếu không, xem ingress, scaling, startup và request log.
2. **Container có bắt đầu xử lý và ghi log không?** Nếu có, tìm span hoặc log cuối cùng trước khi timeout.
3. **Instance còn sống sau lỗi không?** Nếu restart, kiểm tra system logs, memory và startup probe; nếu vẫn sống, kiểm tra request còn chạy sau khi client đã nhận lỗi.

Một HTTP 504 chỉ cho biết request không hoàn tất trong deadline được áp dụng. Nó không tự chứng minh database chậm, JVM hết memory hay Cloud Run gặp lỗi nền tảng.

## 2. Cloud Run có nhiều loại timeout

Một request đi qua nhiều tầng:

~~~mermaid
flowchart LR
    C[Client / mobile / browser] --> G[Gateway / load balancer]
    G --> R[Cloud Run request timeout]
    R --> A[Spring request handler]
    A --> P[Connection pool]
    P --> D[Cloud SQL / API / cache]
~~~

Mỗi tầng có thể có deadline riêng:

| Tầng | Ví dụ | Câu hỏi điều tra |
|---|---|---|
| Client | HTTP client timeout, mobile network | Client có đóng kết nối trước server không? |
| Gateway | API Gateway, external load balancer | Timeout gateway có ngắn hơn Cloud Run không? |
| Cloud Run | Request timeout của revision | Request có vượt cấu hình timeout không? |
| Application | Spring MVC/WebFlux, servlet container | Thread có bị block, deadlock hay queue không? |
| Database/client | Hikari checkout, JDBC query timeout | Đang chờ connection, query hay lock? |
| External API | Payment, shipping, identity | Downstream có retry hoặc timeout lồng nhau không? |

### Timeout mặc định và giới hạn Cloud Run

Cloud Run service mặc định có request timeout **300 giây (5 phút)** và cho phép cấu hình tối đa **3.600 giây (60 phút)**. Khi vượt giới hạn, Cloud Run đóng kết nối và trả HTTP 504. Container instance **không tự động bị terminate** chỉ vì một request timeout; mã ứng dụng có thể tiếp tục chạy phần xử lý còn lại. Điều này có thể khiến instance tiếp tục tiêu thụ CPU, connection và memory dù client đã nhận 504.

Vì vậy, tăng timeout chỉ là một lựa chọn khi workload thực sự cần thời gian dài hơn và có khả năng phục hồi. Nếu handler tiếp tục ghi dữ liệu sau khi client đã timeout, client retry có thể tạo thao tác trùng. Cần idempotency key, durable job state hoặc cơ chế kiểm tra trạng thái trước khi thực hiện lại.

### Đặt timeout bằng gcloud

~~~bash
gcloud run services update orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --timeout=45s
~~~

Mỗi thay đổi cấu hình service tạo revision mới. Lệnh trên minh họa thay timeout; trước khi áp dụng production cần xác minh timeout mới nằm trong deadline của gateway/client và không che một dependency bị treo.

Kiểm tra cấu hình đang chạy:

~~~bash
gcloud run services describe orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format=yaml
~~~

### Xây timeout budget từ ngoài vào trong

Giả sử API có ngân sách 5 giây:

| Thành phần | Deadline minh họa |
|---|---:|
| Cloud Run request | 5.000 ms |
| Application handler | 4.500 ms |
| External API | 1.500 ms |
| JDBC query | 1.000 ms |
| Connection pool checkout | 300 ms |

Các ngân sách có thể chạy tuần tự hoặc song song; không cộng máy móc nếu chúng nằm trên các nhánh đồng thời. Mỗi dependency phải kết thúc trước deadline tổng để ứng dụng có thời gian xử lý lỗi và trả response. Không đặt pool timeout hoặc SQL timeout dài hơn toàn bộ request deadline.

Đối với HTTP client trong Java, truyền deadline hoặc timeout rõ ràng, tránh để thư viện mặc định chờ quá lâu. Nếu dùng retry, tổng thời gian của tất cả attempts và backoff phải nằm trong ngân sách request.

## 3. Timeout không đồng nghĩa request đã bị hủy

Cloud Run trả 504 khi request timeout, nhưng container có thể tiếp tục xử lý. Hãy xem tình huống:

1. Client gửi \`POST /orders\`.
2. Server ghi đơn hàng và gọi payment.
3. Request timeout trước khi server trả response.
4. Client thấy 504 và gửi lại request.
5. Server xử lý lần hai vì lần đầu vẫn đang chạy.

Nếu endpoint không idempotent, hệ thống có thể tạo hai đơn hoặc thu tiền hai lần.

### Các biện pháp bắt buộc cho thao tác ghi

- Nhận idempotency key ổn định từ client hoặc sinh từ business request.
- Lưu trạng thái xử lý và kết quả theo key trong database.
- Dùng transaction/unique constraint để chống hai request cùng tạo side effect.
- Khi client retry, trả lại kết quả cũ hoặc trạng thái IN_PROGRESS.
- Đặt timeout cho dependency và dừng công việc khi không còn đủ deadline.
- Với tác vụ dài, chuyển sang job/queue và trả HTTP 202 cùng operation ID.

### Khi nào nên chuyển sang xử lý bất đồng bộ?

Nếu xử lý thường xuyên vượt deadline request, không nên kéo timeout lên mức tối đa để giữ kết nối lâu. Có thể:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Cloud Run API
    participant Q as Pub/Sub / Cloud Tasks
    participant W as Worker / Cloud Run Job
    participant D as Database
    C->>R: POST /exports
    R->>D: Tạo operation PENDING
    R->>Q: Enqueue operation_id
    R-->>C: 202 Accepted + operation_id
    Q->>W: Thực thi job
    W->>D: Cập nhật RUNNING / SUCCEEDED / FAILED
    C->>R: GET /operations/{id}
    R->>D: Đọc trạng thái
    R-->>C: 200 + operation status
~~~

Cloud Tasks phù hợp với việc gọi endpoint theo lịch, retry có kiểm soát và điều tiết tốc độ; Pub/Sub phù hợp phát sự kiện và fan-out; Cloud Run Jobs phù hợp tác vụ batch chạy đến khi hoàn tất. Chọn theo semantics, không chỉ theo độ dài request.

## 4. Đọc Cloud Run request logs, container logs và system logs

Cloud Run cung cấp ba nhóm log:

- **Request logs:** thông tin HTTP request, latency, status, revision và các thuộc tính request.
- **Container logs:** log do ứng dụng ghi ra stdout/stderr hoặc logging agent được hỗ trợ.
- **System logs:** sự kiện nền tảng như container startup, shutdown, health check và lỗi instance.

Khi điều tra 504 hoặc OOM, cần xem cả ba nhóm. Chỉ đọc application logs có thể bỏ sót lý do Cloud Run terminate container.

### Xem log bằng gcloud

~~~bash
gcloud run services logs read orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --limit=100
~~~

Hoặc truy vấn Cloud Logging:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
timestamp >= "2026-11-19T00:00:00Z"
~~~

Để lọc lỗi:

~~~text
resource.type="cloud_run_revision"
resource.labels.service_name="orders-api"
severity>=ERROR
~~~

Trong Logs Explorer, lọc theo revision, trace ID, request ID và time range. Dùng timestamp UTC khi đối chiếu log giữa Cloud Run, database và hệ thống ngoài.

### Log có cấu trúc

Ứng dụng nên ghi JSON với các trường:

~~~json
{
  "severity": "WARNING",
  "message": "downstream request exceeded budget",
  "service": "orders-api",
  "revision": "orders-api-00042-abc",
  "request_id": "req-8c3e",
  "trace_id": "TRACE_ID",
  "route": "POST /orders",
  "dependency": "inventory",
  "duration_ms": 1400,
  "remaining_deadline_ms": 500
}
~~~

Đây là ví dụ cấu trúc log. Không ghi access token, session cookie, password, payload thanh toán, PII hoặc nội dung bí mật vào log. Nếu cần gắn trace, dùng định dạng tương thích Cloud Trace và correlation ID ổn định.

## 5. Các Cloud Run metrics cần quan sát

Cloud Monitoring có metric cho Cloud Run services và revisions. Những metric quan trọng:

| Metric / nhóm | Cách sử dụng |
|---|---|
| Request count | Traffic theo status, revision và service |
| Request latencies | p50/p95/p99, nhận diện tail latency |
| Container startup latency | Thời gian khởi động instance mới |
| Container CPU utilization | Mức dùng CPU so với allocation |
| Container memory utilization | Memory pressure theo instance/container |
| Container instance count | Số instance đang hoạt động, xem scale-out/scale-in |
| Maximum concurrent requests | Concurrency quan sát được trên instance |
| Billable container instance time | Hiểu thời gian instance được tính phí |
| Container CPU/memory allocation | Đối chiếu mức cấp phát với mức dùng |

Tên metric cụ thể có thể thay đổi theo loại tài nguyên và cấu hình; chọn metric từ Cloud Monitoring Metrics Explorer theo resource type \`Cloud Run Revision (cloud_run_revision)\` hoặc \`Cloud Run Instance (cloud_run_instance)\`.

### Biểu đồ chẩn đoán kết hợp

Trong cùng một time range, hiển thị:

1. Request latency p95/p99.
2. Request count và 5xx/504 count.
3. Container startup latency.
4. Instance count và maximum concurrent requests.
5. CPU utilization.
6. Memory utilization.
7. Database connection pool active/pending và query latency.

Nếu p99 tăng cùng memory gần 100% và instance restart, nghi ngờ memory pressure. Nếu p99 tăng cùng concurrency và CPU sát allocation, xem xét CPU/concurrency. Nếu startup latency tăng cùng cold start count, xem image, initialization và min instances.

### Phân biệt service average với instance hot spot

Metric trung bình service có thể che một instance bị nóng. Nếu một instance nhận request có payload lớn hoặc cache phình, memory trung bình của revision có thể chưa cao. Khi có thể, drill-down theo instance/revision và đối chiếu request logs, container logs cùng thời điểm.

## 6. Chẩn đoán cold start

Cold start xảy ra khi Cloud Run phải tạo instance mới để phục vụ request hoặc revision. Startup latency có thể gồm:

- Provisioning instance và tải image layers.
- Khởi động container và JVM.
- Class loading, dependency injection và Spring application context.
- Khởi tạo connection pool, DNS, TLS và client libraries.
- Đọc cấu hình/secret, warm cache hoặc nạp model.
- Startup probes và sidecar initialization nếu có.

### Đo cold start thay vì đoán

Theo dõi container startup latency và request latency trên cùng biểu đồ. So sánh:

- Request đầu tiên sau khi scale từ zero.
- Request đầu tiên sau deploy revision.
- Request tiếp theo trên instance đã warm.
- Request trên instance mới được scale-out khi peak traffic.

Nếu startup latency cao nhưng thời gian xử lý request sau startup thấp, tập trung tối ưu boot. Nếu startup nhanh mà mọi request đều chậm, đó không phải cold start; xem query, network, CPU và concurrency.

### Các nguyên nhân phổ biến

| Nguyên nhân | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Image lớn | Startup kéo dài khi tạo instance mới | Multi-stage build, image gọn, bỏ file không cần |
| Spring context nặng | Log initialization dài, nhiều bean scan | Giảm component scan, lazy init có chọn lọc, tối ưu bean |
| JIT/class loading | Request đầu sau startup chậm | Warm-up endpoint hoặc compile/AOT phù hợp |
| Khởi tạo database connection | Instance mới chờ DB hoặc pool | Tạo pool nhỏ, lazy connection, giới hạn concurrency |
| Secret/config fetch đồng bộ | Startup phụ thuộc service ngoài | Cache config hợp lệ, timeout và fallback có kiểm soát |
| DNS/TLS handshake | Request đầu gọi dependency chậm | Reuse HTTP clients, connection pooling, keep-alive |
| VPC egress/network | Chỉ chậm khi dùng private dependency | Kiểm tra Direct VPC egress/connector, route và DNS |
| Sidecar | Instance đợi container phụ khởi động | Giảm startup work, xem startup probe và dependency order |

## 7. Giảm cold start bằng cấu hình Cloud Run

### Minimum instances

Cloud Run mặc định có thể scale về zero khi không có traffic. Cấu hình minimum instances giữ một số instance sẵn sàng để giảm xác suất request phải chờ startup:

~~~bash
gcloud run services update orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --min=1
~~~

Minimum instances có chi phí ngay cả khi instance idle theo billing mode áp dụng. Đây là **best-effort floor**, không phải cam kết instance luôn sống; instance vẫn có thể restart, bị ảnh hưởng bởi quota/capacity hoặc lỗi ứng dụng. Nếu cần availability cao, phải kết hợp nhiều instance, region/architecture phù hợp và SLO.

### Startup CPU boost

Startup CPU boost cấp thêm CPU tạm thời trong giai đoạn startup và 10 giây sau khi instance bắt đầu. Có thể bật:

~~~bash
gcloud run services update orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --cpu-boost
~~~

Tính năng này có thể giảm startup time khi ứng dụng CPU-bound lúc khởi tạo, nhưng **không** sửa một dependency bị timeout, database không truy cập được hoặc memory leak. CPU được cấp thêm trong thời gian boost có thể ảnh hưởng chi phí; đo trước/sau thay đổi.

### Tối ưu image và Spring Boot startup

- Dùng base image phù hợp và chỉ giữ runtime dependencies.
- Pin dependency và cache build layers hợp lý.
- Tránh tải model hoặc dataset lớn đồng bộ ở startup nếu có thể lazy-load an toàn.
- Không chạy migration schema nặng trong mỗi instance startup.
- Tái sử dụng HTTP client, SDK client và connection pools thay vì tạo lại theo request.
- Giảm component scan và auto-configuration không cần thiết.
- Kiểm tra classpath và startup logs; bật Spring startup metrics trong môi trường phù hợp.
- Thử CDS/AOT hoặc native image chỉ khi benchmark cho thấy lợi ích bù được chi phí build và tương thích.

Không dùng lazy initialization để trì hoãn mọi lỗi sang request đầu tiên; những dependency bắt buộc phải hoạt động nên được xác minh trước khi nhận traffic.

## 8. Startup probe và liveness probe

Cloud Run hỗ trợ startup và liveness probes cho container. Startup probe xác định ứng dụng đã khởi động; liveness probe phát hiện tiến trình không còn hoạt động đúng. Startup probe thành công trước khi liveness probe bắt đầu kiểm tra.

Ví dụ cấu hình service YAML:

~~~yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: orders-api
spec:
  template:
    spec:
      containers:
      - image: REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:VERSION
        ports:
        - containerPort: 8080
        startupProbe:
          httpGet:
            path: /startupz
            port: 8080
          periodSeconds: 2
          timeoutSeconds: 1
          failureThreshold: 15
        livenessProbe:
          httpGet:
            path: /livez
            port: 8080
          periodSeconds: 10
          timeoutSeconds: 2
          failureThreshold: 3
~~~

Đây là ví dụ minh họa manifest; thay image và project thực tế. Endpoint \`/startupz\` nên trả thành công khi ứng dụng đã sẵn sàng nhận request. \`/livez\` nên kiểm tra tiến trình còn sống, không nên gọi một chuỗi dependency bên ngoài dài khiến mọi instance bị restart cùng lúc khi database gặp sự cố.

### Liveness không phải readiness

Cloud Run service hỗ trợ startup/liveness probe theo contract của nền tảng; không nên sao chép nguyên Kubernetes readiness probe vào Cloud Run và giả định semantics giống hệt GKE. Ở tầng ứng dụng, có thể vẫn có health group readiness cho orchestration nội bộ, nhưng phải xác minh cách Cloud Run nhận traffic.

Probe quá nghiêm ngặt gây restart loop; probe quá lỏng có thể giữ instance bị treo. Đặt timeout/failure threshold dựa trên thời gian startup và sự cố thực tế. Không dùng liveness để thay monitoring của dependency.

## 9. Chẩn đoán thiếu bộ nhớ: container limit và JVM heap

Cloud Run terminate instance khi memory vượt giới hạn được cấp. Memory cần đủ cho executable, heap và non-heap của ứng dụng, native memory, thread stacks, buffer, sidecar phù hợp và file được ghi vào filesystem.

Với Java, **heap không bằng tổng memory của container**. Một tiến trình JVM còn có:

- Metaspace và class metadata.
- JIT code cache.
- Direct byte buffers/NIO.
- Thread stacks.
- Native libraries, TLS/HTTP clients và compression buffers.
- Memory mapping và agent/profiler.
- Cache trong ứng dụng, object allocation và các vùng runtime khác.

Nếu container có 1 GiB nhưng đặt \`-Xmx1g\`, JVM có thể bị Cloud Run kill trước khi heap chạm Xmx. Cần để khoảng headroom dựa trên đo lường.

### Phân biệt hai dạng OOM

**JVM heap OOM:** log ứng dụng có thể ghi \`java.lang.OutOfMemoryError: Java heap space\`, \`GC overhead limit exceeded\` hoặc lỗi direct buffer. Container có thể vẫn tồn tại nếu process không thoát và memory chưa vượt container limit; request có thể tiếp tục treo hoặc lỗi.

**Container memory limit exceeded:** tổng memory vượt giới hạn container; Cloud Run terminate instance. Có thể thấy system log hoặc instance termination, request đang xử lý thất bại và instance mới được tạo.

Không chỉ dựa vào exit code 137 để kết luận OOM; SIGKILL cũng có thể xuất phát từ nguyên nhân khác. Đối chiếu system logs, memory utilization, JVM logs và thời điểm restart.

## 10. Ước lượng memory cho Java/Spring

Một mô hình ngân sách:

\[
M_{container} \ge M_{heap} + M_{metaspace} + M_{direct} +
M_{threads} + M_{native} + M_{filesystem} + M_{headroom}
\]

Các thành phần không hoàn toàn độc lập và thay đổi theo runtime. Dùng công thức như checklist, không phải phép đo chính xác.

Ví dụ container limit 1 GiB:

| Thành phần | Ngân sách minh họa |
|---|---:|
| Java heap | 600 MiB |
| Metaspace/code cache | 100 MiB |
| Direct buffers/native | 80 MiB |
| Thread stacks | 60 MiB |
| File tạm/cache ngoài heap | 40 MiB |
| Headroom | 144 MiB |
| **Tổng** | **1.024 MiB** |

Đây chỉ là phân bổ minh họa; phải dùng memory profile thật. Nếu workload dùng nhiều threads, direct buffers hoặc large JSON, các thành phần đó có thể cao hơn đáng kể.

### Giới hạn heap bằng JVM flags

Ví dụ đặt max heap theo tỷ lệ memory container:

~~~dockerfile
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0 -XX:+ExitOnOutOfMemoryError"
~~~

JVM hiện đại có khả năng nhận biết container limits; tuy nhiên, tỷ lệ phù hợp phụ thuộc JDK, memory limit, native libraries, thread count và workload. \`60%\` là giá trị **minh họa**, không phải chuẩn chung. \`ExitOnOutOfMemoryError\` khiến process thoát khi gặp OOM để nền tảng khởi tạo instance mới, nhưng cũng có thể làm request đang xử lý thất bại; chỉ dùng cùng idempotency, health checks và recovery strategy.

Có thể đặt \`-Xmx\` rõ ràng khi muốn kiểm soát chặt, nhưng không đặt bằng toàn bộ memory limit. Nếu có nhiều container/sidecars, kiểm tra từng container memory allocation theo cấu hình Cloud Run.

### Filesystem cũng dùng memory

Filesystem ghi được trong container Cloud Run thường là in-memory writable filesystem; file lớn có thể làm tăng memory usage. Không ghi file upload, report, cache lớn hoặc heap dump vào \`/tmp\` mà không tính ngân sách. Dùng Cloud Storage cho file bền vững và streaming để tránh buffer toàn bộ nội dung trong heap.

## 11. Tìm memory leak và allocation spike

Một lần OOM có thể do spike tải hoặc do memory tăng dần theo thời gian. Hãy phân biệt:

| Mẫu metric | Giả thuyết |
|---|---|
| Memory tăng dần qua nhiều giờ, không giảm sau GC | Object leak, cache không giới hạn hoặc retained references |
| Memory tăng theo số request đồng thời rồi giảm | Working set/buffer lớn, concurrency cao |
| Heap ổn định nhưng container memory tăng | Native/direct memory, threads, mmap hoặc filesystem |
| OOM chỉ với payload lớn | Đọc toàn bộ body/file vào memory, JSON object graph lớn |
| Memory cao sau deploy mới | Dependency, cache, classloader hoặc agent mới |
| Memory cao khi DB chậm | Request giữ object/connection/thread lâu, queue tích tụ |

### Công cụ quan sát JVM

- Java Flight Recorder (JFR) để phân tích allocation, GC pauses, thread và lock.
- Java heap usage/GC metrics qua Micrometer hoặc JMX exporter được cấu hình an toàn.
- Thread dumps khi nghi ngờ thread pool bị kẹt.
- Heap dump trong môi trường staging hoặc qua quy trình bảo mật riêng nếu cần phân tích object retention.
- Native Memory Tracking khi cần phân tích native allocation và đã chấp nhận overhead.

Heap dump có thể chứa dữ liệu người dùng và rất lớn. Không bật tự động ghi heap dump vào filesystem in-memory của Cloud Run mà chưa đánh giá; lưu vào vị trí bảo mật có retention rõ ràng và quyền truy cập hạn chế.

### Một số nguyên nhân Java/Spring phổ biến

- Cache dùng Map không có eviction hoặc TTL.
- HTTP response body được buffer toàn bộ.
- JDBC result set quá lớn hoặc thiếu pagination.
- Thread pool queue không giới hạn.
- Async tasks giữ context/request objects lâu.
- Logging toàn bộ payload lớn.
- Direct ByteBuffer hoặc Netty pool không được giải phóng theo kỳ vọng.
- Mỗi request tạo SDK client hoặc connection pool mới.
- Hibernate persistence context giữ quá nhiều entities trong batch.

Giải pháp thường là streaming, pagination, giới hạn queue, eviction policy, đóng tài nguyên và batch size hợp lý.

## 12. Concurrency, CPU và memory liên hệ với nhau

Cloud Run có thể phục vụ nhiều request đồng thời trên một instance. Tăng concurrency giúp giảm số instance nhưng làm nhiều request cùng chia CPU, memory và connection pool. Nếu mỗi request tạo một object graph lớn, peak memory có thể gần tỷ lệ concurrency.

### Ví dụ cấu hình concurrency

~~~bash
gcloud run services update orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --concurrency=20 \
  --max=30
~~~

Đây là cấu hình minh họa: tối đa 20 request đồng thời trên instance và giới hạn số instance ở 30 theo flag gcloud hiện hành. Kiểm tra \`gcloud run services update --help\` nếu phiên bản CLI sử dụng tên flag khác hoặc thay đổi. Giới hạn max instances có thể làm request chờ khi đạt trần; phải kiểm tra queueing và dependency capacity.

### Cách chọn concurrency

1. Bắt đầu từ mức hiện tại và workload đại diện.
2. Đo CPU, memory, request latency và database pool pending.
3. Giảm concurrency nếu memory/CPU mỗi instance tăng hoặc tail latency xấu.
4. Tăng concurrency khi request chủ yếu chờ I/O và memory headroom còn đủ.
5. Tính max instance × concurrency để ước lượng tải tối đa lên database và external APIs.
6. Kiểm thử burst, cold start và scale-out trong staging.

Concurrency thấp hơn có thể tăng số instance và startup/cost; concurrency cao hơn có thể tăng memory pressure và latency. Không có giá trị tối ưu chung cho mọi service.

## 13. CPU allocation và tác vụ nền

Cloud Run có billing/CPU allocation modes khác nhau. Với request-based CPU allocation, CPU chủ yếu được cấp trong khi instance xử lý request; không nên dựa vào background thread sau khi response hoàn tất để thực hiện công việc quan trọng. Nếu cần xử lý nền bền vững, dùng Pub/Sub, Cloud Tasks, Cloud Run Jobs hoặc instance-based billing theo nhu cầu.

Một request CPU-bound có thể bị chậm khi CPU allocation thấp; một request I/O-bound có thể không cải thiện nhiều khi tăng vCPU. Đo CPU utilization và thread profiles trước khi scale.

### Startup CPU boost không phải CPU boost liên tục

Startup CPU boost chỉ hỗ trợ giai đoạn khởi tạo và một khoảng ngắn sau khi instance bắt đầu. Nó không tăng CPU cho mọi request lâu dài. Nếu p99 vẫn cao sau startup, cần xem CPU allocation bình thường, concurrency, query và dependency.

## 14. Network và dependency cũng có thể gây cold start/timeout

Một service khởi động nhanh nhưng không thể kết nối Cloud SQL hoặc Secret Manager vẫn có thể trông như cold start. Kiểm tra:

- Cloud Run và database có ở region phù hợp không.
- Direct VPC egress hoặc Serverless VPC Access connector có đúng subnet/route/firewall không.
- DNS resolution, NAT, private IP và connection establishment.
- Cloud SQL connector/Auth Proxy có được khởi tạo một lần và tái sử dụng không.
- Connection pool có mở quá nhiều connections khi scale-out không.
- External API có throttling hoặc TLS handshake chậm không.
- Retry có khuếch đại sự cố khi dependency đã quá tải không.

Không tạo database connection trong mỗi request. Tạo client/pool ở phạm vi instance và tái sử dụng, đồng thời xử lý connection chết, pool timeout và graceful close phù hợp.

## 15. Java/Spring: timeout và pool configuration minh họa

Ví dụ cấu hình HikariCP:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://DB_HOST:5432/orders
    username: orders_app
    hikari:
      maximum-pool-size: 8
      minimum-idle: 1
      connection-timeout: 500
      validation-timeout: 1000
      max-lifetime: 1800000
      pool-name: orders-db-pool
  mvc:
    async:
      request-timeout: 4000
~~~

Các giá trị milliseconds trong ví dụ cần điều chỉnh theo driver, database và request deadline. \`connection-timeout\` của Hikari giới hạn thời gian chờ lấy connection từ pool; nó không phải SQL execution timeout và cũng không phải Cloud Run request timeout.

### Tổng connection budget

Nếu service có tối đa 30 instances, mỗi instance pool tối đa 8 connections, số connections lý thuyết từ service này có thể lên tới:

\[
30 \times 8 = 240\ connections
\]

Cộng thêm các service khác, migration, monitoring, admin và failover. Database có thể bị quá tải dù từng instance chỉ mở một pool nhỏ.

### Timeout khi gọi dependency

Ví dụ Java HTTP client:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofMillis(500))
    .build();

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create(inventoryUrl))
    .timeout(Duration.ofSeconds(2))
    .GET()
    .build();

HttpResponse<String> response = client.send(
    request, HttpResponse.BodyHandlers.ofString());
~~~

Ví dụ cần import \`java.net.http.*\` và \`java.time.Duration\`. Tạo và tái sử dụng client ở phạm vi bean/service thay vì tạo mới mỗi request. Với async/reactive code, sử dụng timeout operators và cancellation semantics phù hợp.

### Không retry mọi lỗi

- Retry 429/503 hoặc network transient khi thao tác idempotent và còn deadline.
- Không retry 400/401/403/404/422 một cách mù quáng.
- Với POST ghi dữ liệu, dùng idempotency key và kiểm tra trạng thái.
- Dùng exponential backoff có jitter, giới hạn attempts.
- Tránh retry đồng thời ở client, application, service mesh và downstream SDK mà không có retry budget chung.

## 16. Quy trình điều tra HTTP 504

~~~mermaid
flowchart TD
    A[Nhận 504] --> B{Có request log Cloud Run?}
    B -->|Không| C[Kiểm tra client, gateway, ingress và DNS]
    B -->|Có| D{Container đã log bắt đầu request?}
    D -->|Không| E[Kiểm tra cold start, scaling, startup và capacity]
    D -->|Có| F[Đọc trace/span và log cuối]
    F --> G{Đang chờ dependency?}
    G -->|Có| H[Kiểm tra pool, SQL, network và timeout downstream]
    G -->|Không| I[Kiểm tra CPU, lock, thread và xử lý payload]
    E --> J{Memory gần limit hoặc instance restart?}
    H --> K[Đặt deadline/retry/idempotency phù hợp]
    I --> K
    J -->|Có| L[Phân tích OOM và memory]
    J -->|Không| M[Kiểm tra image, JVM và probe]
    L --> K
    M --> K
    C --> K
~~~

### Checklist điều tra trong 10 phút đầu

1. Ghi nhận request ID, trace ID, timestamp UTC, revision và route.
2. Kiểm tra 504 có đến từ Cloud Run request timeout hay gateway/client.
3. So sánh request latency với timeout cấu hình.
4. Kiểm tra instance count, startup latency và concurrency.
5. Xem CPU/memory utilization, container restart và system logs.
6. Tìm span chậm nhất: database, external API, DNS, connection pool hay code.
7. Kiểm tra deployment/revision mới, traffic split và cấu hình vừa đổi.
8. Nếu request ghi dữ liệu, xác minh idempotency trước khi retry thủ công.

## 17. Quy trình điều tra cold start

1. Lọc request đầu tiên của revision mới hoặc sau giai đoạn idle.
2. So sánh container startup latency với thời gian xử lý sau startup.
3. Đọc system/container logs để xem thời điểm process listen trên port.
4. Kiểm tra image size, download layers và startup dependencies.
5. Phân tích Spring startup logs, bean initialization và JVM warm-up.
6. Đo thời gian kết nối database/secret/network.
7. Thử minimum instances hoặc startup CPU boost trên revision thử nghiệm.
8. So sánh p95/p99, billable instance time và cost trước/sau.

Không bật min instances vô hạn chỉ để che một startup sequence nặng. Nếu chỉ một endpoint cần latency thấp, cân nhắc tách service nhỏ hoặc warm-up có mục tiêu.

## 18. Quy trình điều tra OOM

1. Kiểm tra system logs có memory limit exceeded/instance termination không.
2. Đọc container logs tìm \`OutOfMemoryError\`, GC overhead hoặc direct buffer errors.
3. So sánh memory utilization theo thời gian với request count/concurrency.
4. Kiểm tra container memory limit và JVM max heap flags của revision lỗi.
5. Kiểm tra file writes, request/response buffering, cache, thread pool và batch size.
6. Nếu heap OOM, lấy heap/JFR profile trong môi trường bảo mật phù hợp.
7. Nếu native memory tăng, kiểm tra direct buffers, threads, JNI và agent.
8. Giảm concurrency hoặc giới hạn payload để giảm peak trong khi tìm root cause.
9. Chỉ tăng memory sau khi biết mức dùng thực và tác động chi phí.
10. Roll out revision mới và quan sát memory slope, OOM rate, p99 cùng instance restarts.

### Kiểm tra memory limit đang triển khai

~~~bash
gcloud run services describe orders-api \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format="yaml(spec.template.spec.containers)"
~~~

Xác minh \`resources.limits.memory\`, CPU và mọi sidecar nếu có. Cấu hình của revision đang nhận traffic mới là nguồn kiểm tra; không suy từ file YAML trong Git nếu chưa chắc revision đã triển khai.

## 19. Runbook giảm tác động khi sự cố đang diễn ra

### Timeout tăng nhưng chưa có OOM

- Giảm tải hoặc concurrency tạm thời nếu database/dependency đang bị quá tải.
- Tắt feature nặng hoặc chuyển batch/report sang queue.
- Giới hạn retry để không khuếch đại traffic.
- Tăng request timeout chỉ khi công việc cần thời gian dài hơn và có idempotency.
- Nếu revision mới gây lỗi, rollback traffic về revision ổn định.

### Cold start sau deploy

- Kiểm tra revision startup health và log.
- Giữ một số minimum instances phù hợp nếu latency mục tiêu cần.
- Bật startup CPU boost nếu startup CPU-bound.
- Giảm image/initialization cost và tránh startup dependency chain dài.
- Theo dõi chi phí idle instance và request latency sau deploy.

### OOM/restart loop

- Giảm concurrency hoặc tạm giới hạn max instances để tránh tạo tải vượt database.
- Nếu có memory leak trong revision mới, rollback revision.
- Tăng memory tạm thời chỉ sau khi xác nhận cấu hình và quota; ghi rõ đây là mitigation.
- Đảm bảo JVM không có heap max bằng container limit.
- Không chạy heap dump lớn vào filesystem in-memory khi container đang sát giới hạn.
- Lập kế hoạch sửa leak/buffer và benchmark trước khi mở lại traffic.

## 20. SLO, cảnh báo và ngăn tái diễn

Các SLI gợi ý:

| SLI | Cách đo | Mục tiêu ví dụ |
|---|---|---|
| Request success rate | Request hợp lệ không trả 5xx/timeout | 99,9% theo cửa sổ 28 ngày |
| p95/p99 latency | Request latency theo route | p95 dưới 500 ms cho API đọc |
| Cold start latency | Container startup latency | p95 dưới ngưỡng do sản phẩm xác định |
| Memory headroom | 1 - memory utilization | Duy trì headroom phù hợp ở peak |
| OOM/restart rate | Instance termination do memory | Không có OOM trong tải dự kiến |
| Pool wait | Hikari pending/checkout time | p95 thấp hơn ngân sách request |
| Dependency latency | Span theo downstream | Mỗi dependency nằm trong budget |

Các số mục tiêu chỉ minh họa; phải điều chỉnh theo sản phẩm và error budget. Không cảnh báo chỉ theo CPU trung bình hoặc memory trung bình; dùng p95/p99, max/instance view và tỷ lệ lỗi để tránh bỏ sót hot instance.

### Alert nên có

- 5xx/504 tăng vượt baseline trong một cửa sổ ngắn.
- p95/p99 latency vượt SLO.
- Container startup latency tăng hoặc revision không scale đủ.
- Memory utilization tiến gần giới hạn kéo dài.
- Instance restart/OOM xuất hiện.
- Concurrency đạt trần hoặc max instances chạm giới hạn.
- Hikari pending connections tăng, DB pool gần cạn.
- Dependency timeout/error rate tăng.

Kết hợp alert với runbook và owner/on-call. Alert không có hành động cụ thể sẽ tạo nhiễu vận hành.

## 21. Bài thực hành: chẩn đoán ba sự cố

### Lab A: timeout do dependency

**Tình huống:** API \`POST /orders\` trả 504 gần đúng request timeout. Application log cho thấy đã bắt đầu xử lý nhưng không có log hoàn tất; trace cho thấy span gọi inventory kéo dài.

**Thực hiện:**

1. Ghi request ID và tìm request log.
2. Xem trace, đo thời gian chờ connection và thời gian gọi inventory.
3. Kiểm tra client timeout, Cloud Run timeout và dependency deadline.
4. Thử một timeout ngắn hơn ở downstream, trả lỗi có kiểm soát trước deadline.
5. Gửi cùng idempotency key hai lần và xác minh không tạo reservation trùng.

**Kết quả cần đạt:** biết tầng gây chậm và có response/error path trước khi Cloud Run timeout.

### Lab B: cold start Java/Spring

**Tình huống:** request đầu sau 10 phút không traffic mất 3 giây, các request tiếp theo mất 150 ms.

**Thực hiện:**

1. So sánh container startup latency với request latency.
2. Đọc Spring startup logs và thời gian tạo database client/pool.
3. Bật startup CPU boost trên revision thử nghiệm.
4. Đặt minimum instances = 1 trong một khoảng đo.
5. So sánh p95/p99 và chi phí billable instance time.

**Kết quả cần đạt:** biết phần nào giảm cold start và chi phí idle capacity tăng bao nhiêu.

### Lab C: memory pressure

**Tình huống:** API upload JSON lớn, memory utilization tăng theo concurrency và instance thỉnh thoảng restart.

**Thực hiện:**

1. Kiểm tra system logs và memory utilization theo revision.
2. Kiểm tra JVM \`-Xmx\`, direct memory, thread count và file tạm.
3. Hạ concurrency từ 80 xuống 20 trên revision thử nghiệm.
4. Chuyển xử lý payload sang streaming thay vì buffer toàn bộ.
5. Đo memory peak, throughput, p99 và số instance.

**Kết quả cần đạt:** giảm memory peak mà vẫn đạt throughput/SLO và không tăng chi phí quá mức.

## 22. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân có thể | Hành động |
|---|---|---|
| 504 đúng một mốc thời gian lặp lại | Cloud Run request timeout hoặc client deadline | Kiểm tra timeout ở mọi tầng, trace |
| 504 nhưng instance vẫn xử lý | Cloud Run đóng connection, request không tự bị kill | Idempotency, cancellation/deadline và async job |
| 504 chỉ sau deploy | Cold start hoặc dependency initialization | Startup latency, image, Spring logs, probes |
| Request đầu chậm, sau đó nhanh | Cold start/JIT/cache/connection warm-up | Min instances, CPU boost, warm-up có kiểm soát |
| Container bị kill, system log memory limit | Container OOM | Tính memory budget, giảm concurrency/buffer hoặc tăng memory |
| JVM heap OOM nhưng không restart | App-level OutOfMemoryError chưa vượt container limit | JFR/heap profile, xử lý OOM và liveness strategy |
| CPU thấp, pool wait cao | Connection pool cạn hoặc connection giữ quá lâu | Hikari active/pending, transaction duration |
| CPU cao, latency cao | CPU-bound code hoặc concurrency quá cao | Profiler, giảm concurrency hoặc tăng CPU sau đo |
| Min instances không loại hết cold start | Instance restart, capacity/quota hoặc deploy | Xem startup logs, quota và min instances best-effort |
| Startup probe liên tục fail | Endpoint sai hoặc initialization chưa xong | Kiểm tra port/path/deadline, không nới vô hạn |
| Tăng memory nhưng vẫn OOM | Leak, direct/native memory hoặc file buffering | Phân tích non-heap, filesystem và thread pools |
| Tăng timeout làm chi phí tăng | Request tiếp tục chạy sau client timeout | Deadline propagation, cancellation, queue/job |

## 23. Checklist trước khi kết thúc incident

- [ ] Xác định timeout phát sinh ở client, gateway, Cloud Run, ứng dụng hay dependency.
- [ ] Đã xem request, container và system logs cùng trace.
- [ ] Đã đối chiếu request latency, startup latency, CPU, memory, concurrency và instance count.
- [ ] Đã xác minh timeout revision đang chạy và timeout của từng dependency.
- [ ] Các thao tác ghi có idempotency khi client retry hoặc request timeout.
- [ ] Tác vụ dài đã có phương án queue/job và trạng thái operation.
- [ ] Cold start được phân tích theo image, JVM/Spring, network và initialization.
- [ ] Min instances/CPU boost được đo hiệu quả và chi phí.
- [ ] Startup/liveness probes không gây restart loop.
- [ ] JVM heap có headroom cho native, direct buffers, threads và filesystem.
- [ ] Đã xác định JVM heap OOM hay container memory limit exceeded.
- [ ] Concurrency và max instances phù hợp capacity của database/dependencies.
- [ ] Đã rollback/mitigate an toàn và quan sát SLO sau thay đổi.
- [ ] Có action item, owner, dashboard, alert và runbook để ngăn tái diễn.

## 24. Kết luận

Cloud Run timeout, cold start và thiếu bộ nhớ thường cùng biểu hiện bằng request chậm hoặc lỗi 5xx, nhưng root cause khác nhau. Timeout cần phân tích deadline xuyên các tầng và xử lý unknown outcome; cold start cần đo container startup latency và tối ưu image/JVM/dependency initialization; OOM cần phân biệt heap với tổng memory container và kiểm tra cả native memory, concurrency cùng file tạm.

Quy trình hiệu quả là **xác định revision và request → đọc logs/traces → đối chiếu metrics → khoanh vùng tầng nghẽn → thử một thay đổi có kiểm soát → đo lại SLO và cost**. Chỉ tăng timeout, CPU hay memory khi số liệu chứng minh đó là nút thắt. Với ứng dụng Java/Spring, connection pooling, thread/concurrency, JVM heap và hành vi retry phải được thiết kế cùng cấu hình Cloud Run để hệ thống phục vụ ổn định khi scale.

## Tài liệu tham khảo

- [Cloud Run troubleshooting](https://docs.cloud.google.com/run/docs/troubleshooting)
- [Configure request timeout for services](https://docs.cloud.google.com/run/docs/configuring/request-timeout)
- [Monitor health and performance](https://docs.cloud.google.com/run/docs/monitoring)
- [Cloud Run logging](https://docs.cloud.google.com/run/docs/logging)
- [Configure memory limits for services](https://docs.cloud.google.com/run/docs/configuring/services/memory-limits)
- [Configure CPU limits and startup CPU boost](https://docs.cloud.google.com/run/docs/configuring/services/cpu)
- [Set minimum instances for services](https://docs.cloud.google.com/run/docs/configuring/min-instances)
- [Container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
- [General development tips for Cloud Run](https://docs.cloud.google.com/run/docs/tips/general)
- [Cloud Run quotas and limits](https://docs.cloud.google.com/run/quotas)
- [Cloud Monitoring overview](https://docs.cloud.google.com/monitoring/docs)
- [Spring Boot Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Java Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api.html)
