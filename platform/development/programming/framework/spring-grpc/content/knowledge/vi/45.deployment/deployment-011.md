# Cấu hình resource container

## 1. Vì sao cấu hình resource ảnh hưởng trực tiếp đến gRPC?

Trong **SPRING_GRPC**, mỗi pod/container có giới hạn CPU, memory và có thể cả ephemeral storage. Ứng dụng Spring Boot chạy gRPC đồng thời dùng JVM heap, thread stacks, Netty event loops, direct buffers, connection pool, serializer và các worker xử lý database/downstream.

Nếu đặt memory limit quá thấp, container có thể bị OOMKilled dù heap chưa đầy. Nếu CPU limit quá chặt, JVM và Netty bị CPU throttling, làm tăng latency p95/p99 và khiến deadline hết. Nếu chỉ tăng limit mà không giới hạn concurrency, số RPC đồng thời có thể tăng đến mức database pool hoặc downstream bị quá tải.

Cấu hình resource cần cân bằng ba điều:

- Scheduler có đủ thông tin để đặt pod lên node phù hợp.
- Container có capacity đủ cho heap, native memory, thread và tải đồng thời.
- Ứng dụng giới hạn công việc để không tiêu thụ vượt capacity của pod và dependency.

Bài tập trung vào Kubernetes requests/limits, JVM container awareness, Netty/gRPC resources, database pool, streaming buffers, probes, graceful shutdown, autoscaling và kiểm thử dưới tải.

## 2. Phân biệt requests và limits

Trong Kubernetes:

- **requests** là lượng resource scheduler dùng để quyết định placement và là cơ sở cho một số thuật toán autoscaling.
- **limits** là giới hạn sử dụng mà runtime/kernel thực thi theo loại resource.
- CPU limit được áp dụng bằng quota/throttling; container có thể bị hạn chế thời gian CPU trong chu kỳ.
- Memory limit thường được thực thi bằng cơ chế OOM của kernel; tiến trình có thể bị kill khi vượt giới hạn.
- Ephemeral storage limit kiểm soát dung lượng writable layer, logs và emptyDir thuộc phạm vi container/pod theo cấu hình.

Ví dụ:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "768Mi"
    ephemeral-storage: "256Mi"
  limits:
    cpu: "2"
    memory: "1536Mi"
    ephemeral-storage: "1Gi"
```

Đây chỉ là điểm bắt đầu minh họa. Không sao chép con số vào production mà chưa đo heap, native memory, thread count, traffic profile và sidecar overhead.

Request CPU 500m tương đương nửa CPU core theo đơn vị Kubernetes. Limit CPU 2 cho phép tối đa khoảng hai core trong điều kiện quota. Memory request/limit được tính theo byte; Mi là mebibyte, Gi là gibibyte.

## 3. Đo toàn bộ memory, không chỉ heap

Memory limit của container áp dụng cho memory mà tiến trình/container sử dụng, không chỉ Java heap. Một JVM gRPC có thể tiêu thụ:

- Heap: object, Protobuf message, application state và cache.
- Metaspace: class metadata.
- Code cache: mã JIT đã biên dịch.
- Thread stacks: mỗi platform thread có stack riêng.
- Direct/native buffers: Netty và thư viện native.
- TLS/crypto buffers, allocator và native library.
- Memory-mapped files và các vùng native khác.

Một cách lập ngân sách:

```text
Container memory limit
  >= JVM heap budget
   + metaspace and code cache
   + thread stacks
   + Netty/direct/native buffers
   + TLS and library overhead
   + safety margin
```

Nếu đặt **-Xmx** gần bằng memory limit, phần native còn lại có thể đẩy container tới OOM trước khi heap báo OutOfMemoryError. Hãy để khoảng dự phòng đủ lớn dựa trên đo đạc thực tế.

Dùng container memory metrics, process RSS, Native Memory Tracking (khi phù hợp), heap metrics và GC logs để phân biệt heap pressure với native memory growth. Heap dump không cho thấy toàn bộ direct/native memory.

## 4. Để JVM nhận biết container limits

Các JDK hiện đại có khả năng nhận diện container/cgroup limits và dùng chúng khi tính ergonomics của JVM. Tuy nhiên, hành vi phụ thuộc JDK version, vendor và flags. Kiểm tra runtime thực tế thay vì giả định JVM luôn thấy đúng số CPU/RAM của node.

Có thể đặt heap theo tỷ lệ memory khả dụng:

```dockerfile
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=60.0"
```

**MaxRAMPercentage** là ví dụ; tỷ lệ phù hợp phụ thuộc lượng direct memory, thread, metaspace và thư viện. Nếu container memory limit là 1.5 GiB, heap tối đa theo 60% chỉ là một phần ngân sách; phần còn lại vẫn phải đủ cho native memory và overhead.

Khi cần heap cố định, có thể dùng **-Xms** và **-Xmx**, nhưng phải bảo đảm tổng memory của tiến trình nằm trong container limit ở tải đỉnh. Không đặt -Xms quá lớn nếu pod cần khởi động nhiều replica đồng thời trên node có memory hạn chế.

Kiểm tra flags/runtime trong container bằng công cụ JVM phù hợp với JDK đang dùng, và ghi nhận cấu hình thực tế trong startup diagnostics.

## 5. Quản lý Netty direct memory và gRPC message buffers

gRPC Java trên Netty có thể dùng direct buffers để giảm copy giữa JVM heap và native I/O. Các buffer này không nằm trong heap theo cách thông thường nhưng vẫn tiêu thụ memory của container.

Các yếu tố làm tăng direct/native memory:

- Số connection và concurrent RPC.
- Kích thước request/response Protobuf.
- Streaming message và lượng dữ liệu đang in-flight.
- TLS encryption/decryption buffers.
- Allocator pooling và thời gian buffer được giải phóng.
- Queue chứa message chờ xử lý.

Không dùng heap usage làm đại diện duy nhất cho memory. Nếu heap ổn định nhưng container RSS tăng, kiểm tra direct buffer pool, Netty allocator, native memory và thread count.

Có thể đặt giới hạn direct memory qua **-XX:MaxDirectMemorySize**, nhưng không chọn tùy tiện. Giới hạn quá thấp có thể gây lỗi cấp phát direct buffer khi tải tăng; không đặt giới hạn cũng không có nghĩa direct memory miễn phí. Hãy benchmark và quan sát theo JDK/Netty version đang chạy.

Đặt inbound message size và application payload limits phù hợp để một RPC không thể buộc pod giữ một message quá lớn trong memory.

## 6. CPU limits và tác động tới latency

CPU request giúp scheduler đặt pod lên node có đủ capacity. CPU limit đặt trần CPU time mà container được dùng trong chu kỳ quota. Khi workload cần nhiều CPU hơn limit, Linux throttles container.

Với gRPC, CPU throttling có thể kéo dài:

- Protobuf serialization/deserialization.
- TLS handshake và record processing.
- Event-loop callbacks.
- Business logic và mapping response.
- GC/JIT và background maintenance.

Dưới tải, throttling làm latency tăng đột ngột dù CPU usage trung bình nhìn có vẻ không cao. Quan sát CPU throttled time/throttled periods cùng RPC latency và deadline exceeded.

Không đặt CPU limit quá thấp chỉ để tiết kiệm node nếu service nhạy latency. Một số tổ chức chọn request rõ ràng và limit đủ rộng hoặc không đặt CPU limit theo policy cluster; quyết định phải phù hợp quota, fairness và multi-tenant isolation của môi trường.

## 7. Thread pools phải nằm trong resource budget

Một pod có thể có nhiều nhóm thread:

- Netty event loops.
- gRPC application call executor.
- Worker pool cho JDBC/blocking HTTP.
- Scheduler, application task executor và background worker.
- JVM GC, JIT và runtime threads.

Mỗi platform thread tiêu thụ native stack và scheduler overhead. Tăng thread pool không làm database hoặc downstream xử lý nhanh hơn. Nếu 100 worker cùng chờ 20 database connections, phần lớn thread chỉ giữ stack và chờ pool.

Giới hạn worker concurrency theo dependency capacity. Dùng bounded queue và rejection/load shedding thay vì queue vô hạn. Tránh CallerRunsPolicy nếu task có thể bị chạy trên transport/event-loop thread.

CPU sizing cũng cần xem số replica. 8 thread CPU-heavy trên mỗi pod nhân với 20 pod có thể tạo 160 runnable tasks cạnh tranh trên cluster.

## 8. Đồng bộ gRPC concurrency với database connection pool

Ví dụ mỗi pod có HikariCP maximumPoolSize = 20 và deployment chạy tối đa 10 replicas. Database có thể phải phục vụ tối đa khoảng 200 connections chỉ từ service này, chưa tính các consumer khác, migration và admin tools.

Ngân sách tổng:

```text
maximum application DB connections
  = max replicas × pool maximum size
```

Không chỉ cấu hình pool theo nhu cầu một pod. Tính tổng theo autoscaling maximumReplicas và capacity database.

Nếu gRPC nhận nhiều request hơn số DB connections, request sẽ chờ acquisition. Điều đó có thể giữ call executor và làm deadline hết trước khi query bắt đầu. Cần:

- Giới hạn concurrent database work.
- Đặt connection acquisition timeout phù hợp remaining deadline.
- Giữ transaction ngắn.
- Giới hạn HPA max replicas theo database connection budget.
- Theo dõi active/idle/pending connections và acquisition latency.

Tăng replica có thể làm ứng dụng nhận thêm RPC nhưng cũng tăng tổng pool connections. Autoscaling cần xét downstream capacity, không chỉ CPU.

## 9. Streaming và buffer là một phần của memory sizing

Một stream có thể sống lâu và giữ state, observer, queue hoặc chunk buffers. Nếu mỗi stream giữ 1 MiB dữ liệu và pod có 500 stream đồng thời, riêng phần đó đã có thể chiếm khoảng 500 MiB, chưa tính object overhead và transport buffers.

Với streaming RPC:

- Đặt giới hạn message/chunk size.
- Dùng backpressure và chỉ tạo message khi downstream sẵn sàng.
- Giới hạn số stream đồng thời theo tenant và pod.
- Dùng bounded queue thay vì giữ toàn bộ stream trong memory.
- Không gom file lớn vào ByteArrayOutputStream hoặc một List.
- Hủy producer khi client cancel/deadline hết.
- Đặt maximum stream duration/idle timeout nếu contract cần.
- Dùng checkpoint/resume thay vì giữ session vô hạn.

Memory capacity phải được test với số stream đồng thời thực tế, slow consumers và network interruption.

## 10. Cấu hình Kubernetes cho Spring gRPC

Một deployment mẫu:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: spring-grpc
spec:
  replicas: 3
  selector:
    matchLabels:
      app: spring-grpc
  template:
    metadata:
      labels:
        app: spring-grpc
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          image: example/spring-grpc:1.0.0
          ports:
            - name: grpc
              containerPort: 8443
              protocol: TCP
          resources:
            requests:
              cpu: "500m"
              memory: "768Mi"
            limits:
              cpu: "2"
              memory: "1536Mi"
```

Manifest chỉ minh họa resource và port. Production cần bổ sung image policy, security context, secret/TLS mounts, probes, service account, network policy và rollout strategy theo nền tảng.

Nếu pod có service-mesh sidecar hoặc log/telemetry sidecar, tính resource của các container đó vào pod/node capacity. Không coi application container là toàn bộ chi phí của pod.

## 11. Readiness, liveness và startup probe

Probe ảnh hưởng cách Kubernetes gửi traffic và restart container:

- **Startup probe:** cho phép ứng dụng có thời gian khởi động; liveness chưa đánh giá cho tới khi startup thành công.
- **Readiness probe:** pod chỉ nhận traffic khi có thể phục vụ RPC.
- **Liveness probe:** phát hiện process bị kẹt không thể tự phục hồi và cần restart.

gRPC health checking có thể dùng health service chuẩn. Ví dụ probe:

```yaml
startupProbe:
  grpc:
    port: 8443
  periodSeconds: 5
  failureThreshold: 24

readinessProbe:
  grpc:
    port: 8443
    service: ""
  periodSeconds: 5
  failureThreshold: 3

livenessProbe:
  grpc:
    port: 8443
  periodSeconds: 10
  failureThreshold: 3
```

Kubernetes gRPC probe cần listener/health service tương thích và port số; kiểm tra TLS/proxy topology vì probe native có giới hạn cấu hình so với một client gRPC đầy đủ. Nếu server yêu cầu TLS/mTLS ở port health, cần chọn probe mechanism phù hợp thay vì giả định probe mặc định mang certificate client.

Readiness nên phản ánh service có thể nhận RPC theo policy. Không nhất thiết fail readiness chỉ vì một dependency phụ tạm thời lỗi nếu service vẫn có thể phục vụ một phần request. Liveness không nên phụ thuộc trực tiếp vào database health; database outage không phải lý do restart mọi pod liên tục.

## 12. Graceful shutdown và termination grace period

Khi rollout hoặc scale down, Kubernetes gửi SIGTERM rồi chờ terminationGracePeriodSeconds trước khi force kill. gRPC server cần ngừng nhận RPC mới và cho call đang chạy có thời gian hoàn tất.

Một shutdown sequence hợp lý:

1. Đánh dấu instance không readiness để ngừng nhận traffic mới.
2. Bắt đầu graceful shutdown server/channel theo lifecycle Spring.
3. Cho unary RPC và stream đang chạy hoàn tất trong grace period.
4. Hủy hoặc kết thúc call còn lại theo policy khi hết thời gian.
5. Đóng executor, database pool và resource khác.
6. Thoát process trước khi Kubernetes force kill.

Streaming có thể tồn tại lâu hơn grace period. API cần giới hạn stream duration hoặc hỗ trợ reconnect/resume; nếu không, rollout có thể thường xuyên cắt stream. preStop hook có thể giúp phối hợp drain nhưng cũng tiêu thụ termination grace period.

Không đóng database pool trước khi application service đã ngừng nhận và drain các request đang cần database.

## 13. Autoscaling phải tính cả downstream capacity

HPA thường scale theo CPU hoặc custom metrics. CPU utilization percentage thường được tính tương quan với CPU request; nếu không khai báo request phù hợp, metric utilization có thể không hoạt động như mong đợi.

CPU-only scaling có thể bỏ qua các bottleneck như:

- RPC queue depth tăng nhưng CPU thấp do thread đang chờ I/O.
- Hikari pending connections tăng.
- gRPC in-flight calls và deadline exceeded tăng.
- Streaming sessions giữ memory.
- Downstream latency hoặc broker backlog tăng.

Có thể bổ sung custom/external metrics như in-flight RPC, queue depth, request rate hoặc pending DB acquisition. Metric phải ổn định, có smoothing và ngưỡng tránh scale oscillation.

Đặt maxReplicas theo tổng budget của database, broker, downstream API và node capacity. Nếu HPA tăng pod vượt khả năng database, service có thể tự tạo connection storm và làm outage lan rộng.

## 14. Quan sát resource trong production

Theo dõi ở cả container, JVM, gRPC và dependency:

| Nhóm | Metrics cần quan sát |
| --- | --- |
| Container | CPU usage/throttling, memory working set/RSS, OOMKilled, ephemeral storage |
| JVM | Heap used/committed, GC pause, allocation rate, metaspace, thread count |
| Netty | Direct buffer usage, event-loop lag, connection/subchannel và transport errors |
| gRPC | In-flight RPC, request rate, latency p50/p95/p99, status code, stream count |
| Executor | Active threads, queue depth, queue wait, rejected tasks |
| Database | Pool active/idle/pending, acquisition time, query/lock latency |
| Kubernetes | Restarts, readiness, scheduling failures, HPA replicas và rollout status |

Khi OOMKilled, kiểm tra container memory limit và RSS trước khi chỉ tăng -Xmx. Khi deadline tăng cùng CPU throttling, đánh giá CPU quota. Khi pending DB connections tăng, không nhất thiết cần thêm pod; có thể database đã chạm capacity.

Đặt alert theo trend và saturation, không chỉ theo một ngưỡng usage đơn lẻ. Kết hợp trace theo RPC method với resource metrics để xác định loại request gây áp lực.

## 15. Kiểm thử capacity và resource limit

Trước production, chạy load test trên container có resource requests/limits tương tự môi trường thật:

- Tải unary RPC ở concurrency tăng dần.
- Nhiều request/response gần message size limit.
- Streaming dài, slow consumer và cancellation.
- Database latency/lock contention và pool saturation.
- TLS handshake/reconnect và certificate rotation.
- CPU throttling có chủ đích.
- Memory pressure và direct buffer growth.
- Rolling deployment trong khi RPC/stream đang hoạt động.
- HPA scale out/in ở các mức tải khác nhau.

Ghi nhận throughput, p95/p99, deadline exceeded, OOM, GC pause, CPU throttling và queue depth. Xác định điểm saturation trước khi capacity tăng không còn cải thiện throughput.

Test container local không hoàn toàn mô phỏng Kubernetes cgroup, sidecar và node contention. Dùng staging/cluster test để xác minh hành vi scheduler, HPA, probes và termination.

## 16. Checklist review

- Requests/limits CPU, memory và ephemeral storage được đặt theo số liệu.
- Tổng memory budget bao gồm heap, metaspace, stacks, direct/native buffers và safety margin.
- JVM container awareness được xác minh theo JDK thực tế.
- MaxRAMPercentage, -Xmx và direct memory không vượt container budget.
- CPU throttling được theo dõi cùng RPC latency.
- Netty/gRPC event loops, call executor và worker pools có concurrency/queue giới hạn.
- Hikari pool size được tính theo max replicas và database capacity.
- Streaming có message/chunk cap, backpressure và concurrent stream limit.
- Readiness, liveness và startup probe phản ánh đúng lifecycle.
- Graceful shutdown có drain và termination grace period đủ dài.
- HPA xem cả downstream/database capacity, không chỉ CPU.
- Sidecar resource được tính trong pod budget.
- Metrics container/JVM/gRPC/executor/database được liên kết.
- Load test chạy với resource limit và rollout gần production.

Trong **SPRING_GRPC**, cấu hình resource container phải phản ánh toàn bộ chi phí của JVM, Netty, RPC concurrency, streaming buffers và dependency pools. Đặt requests để scheduler lập kế hoạch đúng, limits đủ cho tải mục tiêu, đồng thời giới hạn worker, queue và stream để giữ memory/CPU trong budget. Kết hợp probes, graceful shutdown, autoscaling có xét database capacity và load tests để tránh OOM, CPU throttling cùng deadline failure dưới tải.
