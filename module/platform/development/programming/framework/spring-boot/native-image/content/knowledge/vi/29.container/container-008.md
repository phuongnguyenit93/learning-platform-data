# Giới hạn CPU, RAM, health check và tín hiệu kết thúc

## Mục tiêu bài học

Một Spring Boot application đã được biên dịch thành **GraalVM Native Image** vẫn cần chạy trong giới hạn tài nguyên và vòng đời của container. Native executable có thể khởi động nhanh, nhưng khi container bị giới hạn CPU hoặc RAM, ứng dụng vẫn có thể khởi động chậm, bị throttling, bị OOM kill hoặc không hoàn tất request khi container dừng.

Để vận hành ổn định, cần phối hợp ba lớp:

- **Container runtime/orchestrator:** giới hạn CPU, RAM, PID, thời gian dừng và cách gửi tín hiệu.
- **Spring Boot:** health groups, graceful shutdown, lifecycle của web server, executor và connection pool.
- **Native executable:** quản lý heap/runtime memory, thread, native library và các giới hạn riêng của target platform.

Bài học này giúp bạn:

- Đặt CPU/memory request và limit phù hợp cho native container.
- Phân biệt heap với RSS và memory accounting của cgroup.
- Thiết kế startup, readiness và liveness health check đúng mục đích.
- Cấu hình graceful shutdown và xử lý SIGTERM/SIGKILL.
- Tránh lỗi do PID 1, entrypoint shell và thời gian dừng quá ngắn.
- Kiểm thử container dưới giới hạn tài nguyên và khi bị terminate.

## 1. Container không làm ứng dụng miễn nhiễm với giới hạn tài nguyên

### 1.1. Native Image vẫn tiêu thụ CPU và memory

Native executable không cần JVM để chạy, nhưng vẫn có:

- Heap được quản lý bởi Native Image runtime.
- Object, stack của thread và cấu trúc runtime.
- Machine code, metadata, thư viện được map vào process.
- Direct/native memory do thư viện sử dụng.
- Buffer mạng, TLS, database driver, cache và payload đang xử lý.

Vì vậy, **heap không phải toàn bộ memory footprint**. Khi container bị giới hạn RAM, kernel tính memory theo cgroup/container accounting. RSS và memory usage của container có thể lớn hơn phần heap đang dùng.

Một ứng dụng có heap còn trống vẫn có thể chạm memory limit do thread stack, direct buffer, native library hoặc memory mapping.

### 1.2. CPU limit ảnh hưởng cả startup và runtime

Khi container chỉ được cấp một phần CPU, các tác vụ sau đều chịu ảnh hưởng:

- Spring ApplicationContext initialization.
- Class loading, initialization và các tác vụ bootstrap.
- Kết nối database/cache và health check.
- Request processing, serialization và cryptography.
- GC và các tác vụ nền.

Native Image thường có cold start ngắn hơn JVM trong nhiều workload, nhưng CPU quota thấp vẫn có thể kéo dài thời gian readiness. Hãy đo trong đúng giới hạn CPU sẽ dùng ở production.

### 1.3. Ba loại lỗi cần phân biệt

| Hiện tượng | Dấu hiệu | Nguyên nhân có thể |
|---|---|---|
| CPU throttling | Process còn sống nhưng latency tăng, CPU bị giới hạn theo quota | CPU limit thấp hoặc workload burst |
| Memory pressure/OOM | Container bị kill, exit code thường là 137, Kubernetes báo `OOMKilled` | Tổng memory vượt cgroup limit |
| Probe failure | Orchestrator đánh dấu unhealthy, restart hoặc loại pod khỏi traffic | Probe sai path/port, timeout quá ngắn hoặc ứng dụng chưa sẵn sàng |

Không xử lý cả ba bằng cách tăng memory. Hãy xác định container đang bị giới hạn CPU, bị OOM hay health probe đang đánh giá sai.

## 2. Đặt CPU limit và request

### 2.1. Docker CPU options

Docker hỗ trợ giới hạn CPU qua các tùy chọn như:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--cpus` | Giới hạn lượng CPU quota, ví dụ `1.5` CPU |
| `--cpu-shares` | Trọng số CPU tương đối khi có tranh chấp; không phải hard limit độc lập |
| `--cpuset-cpus` | Giới hạn process chỉ chạy trên các CPU được chỉ định |

Ví dụ chạy native container với khoảng 1.5 CPU:

```bash
docker run --rm \
  --name payment-native \
  --cpus="1.5" \
  -p 8080:8080 \
  payment-service:native
```

Để đo hiệu năng, ghi lại CPU quota thực tế. `--cpu-shares` không tương đương `--cpus`: shares chủ yếu quyết định mức ưu tiên tương đối khi nhiều container tranh CPU.

### 2.2. Kubernetes requests và limits

Trong Kubernetes:

- `requests.cpu` dùng cho scheduler đặt pod lên node và là cơ sở cho một số cơ chế phân bổ CPU.
- `limits.cpu` đặt mức CPU tối đa container có thể sử dụng; khi vượt quota, container có thể bị throttling.
- `requests.memory` là lượng memory scheduler dùng để tính khả năng đặt pod.
- `limits.memory` là giới hạn memory; khi container vượt giới hạn, kernel có thể OOM kill process trong container.

Ví dụ:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "256Mi"
  limits:
    cpu: "1500m"
    memory: "512Mi"
```

Đây chỉ là giá trị minh họa. Chọn requests/limits từ số liệu đo dưới workload đại diện, có tính tới peak memory, startup burst, concurrency và số thread.

### 2.3. CPU request không phải CPU dành riêng

Một pod có request `500m` không có nghĩa luôn có nửa core riêng biệt. Scheduler dùng request để placement và node có thể chạy nhiều workload cùng lúc. Khi đặt CPU limit thấp, ứng dụng có thể bị throttling dù node vẫn còn CPU rảnh tùy cơ chế quota/cgroup.

Nếu startup probe thất bại trong lúc node bận hoặc CPU quota quá thấp, kiểm tra CPU throttling trước khi nới probe timeout một cách tùy tiện.

### 2.4. Đo CPU throttling

Trong môi trường Linux/cgroup, có thể quan sát số lần và thời gian throttling qua cgroup CPU statistics hoặc metrics của container runtime/Prometheus. Tên metric phụ thuộc cAdvisor/runtime/version, thường có các metric liên quan throttled periods và throttled seconds.

Đối chiếu:

- CPU usage thực tế.
- CPU limit/quota.
- Thời gian throttled.
- Request latency và readiness duration.
- Node CPU contention.

Nếu throttling tăng cùng lúc p95/readiness tăng, thử tăng CPU limit trong một lượt benchmark có kiểm soát để xác nhận mối liên hệ.

## 3. Đặt memory limit cho Native Image

### 3.1. Đừng lấy heap làm memory limit

Memory limit của container phải đủ cho toàn bộ process và các tiến trình phụ trợ được tính vào cgroup. Với native executable, cần dự trù:

- Native Image managed heap.
- Thread stacks và số lượng thread tối đa.
- Direct buffers và native allocations.
- Shared libraries và memory-mapped files.
- TLS, database/cache clients và serialization buffers.
- Runtime metadata và overhead của process.

Nếu giới hạn container là `512Mi`, không nên mặc định cho managed heap dùng hết `512Mi`. Hãy dành headroom cho memory ngoài heap và các đợt tăng tải.

### 3.2. Chọn heap cap có khoảng dự phòng

Native Image hỗ trợ một số runtime options tương tự `-Xms`/`-Xmx` để điều chỉnh managed heap; cách hỗ trợ và tên option cần xác nhận theo GraalVM version và binary đã build. Nếu đặt max heap, giá trị đó chỉ giới hạn managed heap, không giới hạn toàn bộ RSS.

Nguyên tắc:

1. Đo RSS/container memory tại readiness, steady-state và peak.
2. Xác định phần memory ngoài managed heap.
3. Đặt heap cap đủ cho workload nhưng vẫn để headroom.
4. Chạy burst/soak test dưới memory limit production.
5. Kiểm tra GC pressure, allocation failure và OOM.

Không dùng `JAVA_TOOL_OPTIONS` hoặc `JAVA_OPTS` như thể native executable là JVM. Những biến này là cơ chế cấu hình Java launcher/JVM; native executable không tự động đọc chúng. Truyền runtime arguments theo cách mà native binary và container entrypoint hỗ trợ.

### 3.3. Nhận diện OOM

Khi container vượt memory limit, kernel có thể gửi SIGKILL. Process không có cơ hội chạy shutdown hook hoặc ghi log cuối cùng.

Dấu hiệu thường gặp:

- Docker container kết thúc với exit code `137`.
- Kubernetes container state có `reason: OOMKilled`.
- Kernel/cgroup memory events ghi nhận OOM.
- Log ứng dụng dừng đột ngột, không có graceful shutdown message.

Exit code 137 cũng có thể xuất hiện khi process bị SIGKILL vì lý do khác; cần đối chiếu container state và kernel events trước khi kết luận OOM.

### 3.4. Đọc memory theo cùng một định nghĩa

| Chỉ số | Dùng để trả lời |
|---|---|
| Managed heap used | Ứng dụng đang giữ bao nhiêu object trong heap |
| Managed heap committed/max | Runtime đã cấp hoặc cho phép heap tăng tới đâu |
| Process RSS | Bao nhiêu trang bộ nhớ process đang cư trú |
| Container memory/cgroup usage | Container đang tiêu thụ bao nhiêu memory theo accounting của kernel |
| Peak container memory | Mức cao nhất trong khoảng benchmark |

Khi mục tiêu là tránh OOM hoặc tăng mật độ pod, ưu tiên theo dõi container memory và peak. Heap metrics vẫn hữu ích để tìm allocation/GC pressure, nhưng không đại diện toàn bộ container.

## 4. Thiết kế health check đúng mục đích

### 4.1. Phân biệt startup, readiness và liveness

Ba probe trả lời ba câu hỏi khác nhau:

| Probe | Câu hỏi | Khi thất bại |
|---|---|---|
| Startup | Ứng dụng đã hoàn tất giai đoạn khởi động cần thiết chưa? | Orchestrator tiếp tục chờ trong giới hạn startup probe; nếu hết ngưỡng, container bị restart |
| Readiness | Instance có thể nhận traffic mới không? | Instance bị loại khỏi Service/endpoints, process vẫn chạy |
| Liveness | Process còn hoạt động và có khả năng tiếp tục phục vụ không? | Orchestrator restart container |

Không dùng một endpoint duy nhất với cùng ý nghĩa cho cả ba probe. Startup bảo vệ ứng dụng có thời gian khởi động dài; readiness kiểm soát nhận traffic; liveness phát hiện process bị treo hoặc không thể phục hồi.

### 4.2. Bật health groups của Spring Boot Actuator

Thêm Spring Boot Actuator và cấu hình:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.show-details=never
management.endpoints.web.exposure.include=health
```

Khi probe support được bật, Spring Boot cung cấp các health group:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Liveness state và readiness state phản ánh các giai đoạn vòng đời của ứng dụng. Readiness chuyển sang trạng thái sẵn sàng sau khi ứng dụng đạt giai đoạn tương ứng; khi context đóng hoặc readiness bị đánh dấu REFUSING_TRAFFIC, endpoint có thể trả trạng thái không sẵn sàng.

Chỉ expose các Actuator endpoint cần thiết. Không expose toàn bộ management endpoints ra public network chỉ để Kubernetes đọc health.

### 4.3. Liveness không nên phụ thuộc dịch vụ ngoài

Không nên đưa database, Redis hoặc message broker vào liveness group một cách mặc định. Nếu database tạm thời lỗi, liveness của mọi pod cùng fail có thể khiến Kubernetes restart đồng loạt, làm tăng tải lên dependency đang gặp sự cố.

Liveness nên tập trung vào trạng thái nội bộ cho biết process có thể tiếp tục hoạt động hay không. Nếu một dependency khiến instance không thể nhận request, cân nhắc readiness để tạm ngừng nhận traffic.

Readiness cũng cần được thiết kế có chọn lọc. Nếu mọi dependency tùy chọn đều nằm trong readiness, một sự cố ở dịch vụ phụ có thể làm toàn bộ service rời khỏi traffic dù một phần chức năng vẫn hoạt động.

### 4.4. Health endpoint nên chạy trên cổng ứng dụng

Ưu tiên để health endpoint được kiểm tra qua cùng server port mà traffic thực sử dụng. Nếu Actuator chạy trên management port riêng, management server có thể trả healthy trong khi web server chính không nhận được request.

Nếu bắt buộc dùng management port riêng, bổ sung kiểm tra phù hợp cho cổng ứng dụng và kiểm thử trường hợp web server chính bị lỗi.

### 4.5. Custom health indicator

Khi cần kiểm tra một dependency quan trọng, có thể viết `HealthIndicator` và quyết định đưa nó vào readiness group:

```java
@Component
class PaymentProviderHealthIndicator implements HealthIndicator {

    private final PaymentProviderClient client;

    PaymentProviderHealthIndicator(PaymentProviderClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        if (client.isAvailable()) {
            return Health.up().build();
        }
        return Health.down()
                .withDetail("provider", "unavailable")
                .build();
    }
}
```

Chỉ dùng health check nhanh, có timeout và không tạo tải lớn lên dependency. Không thực hiện truy vấn nặng hoặc gọi nhiều API ngoài mỗi vài giây. Cấu hình nhóm readiness rõ ràng nếu chỉ muốn indicator này ảnh hưởng readiness.

Ví dụ đưa indicator có tên bean `paymentProviderHealthIndicator` vào readiness group:

```properties
management.endpoint.health.group.readiness.include=readinessState,paymentProvider
```

`paymentProvider` là contributor ID được suy ra từ bean tên `paymentProviderHealthIndicator` theo quy ước đặt tên health indicator. Xác nhận ID thực tế qua endpoint health trong môi trường thử nghiệm trước khi áp dụng.

## 5. Cấu hình Kubernetes probes

### 5.1. Startup probe

Startup probe cho ứng dụng đủ thời gian hoàn tất bootstrap trước khi liveness/readiness bắt đầu có hiệu lực. Ví dụ:

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 24
```

Với ví dụ này, Kubernetes cho phép một khoảng khởi động tối đa xấp xỉ 120 giây trước khi startup probe thất bại (24 lần, mỗi lần cách nhau 5 giây; thời gian thực tế còn phụ thuộc thời điểm probe và timeout). Điều chỉnh theo phân bố startup thực tế dưới CPU limit production.

Khi startup probe đã thành công, Kubernetes ngừng dùng startup probe và bắt đầu áp dụng liveness/readiness probes.

### 5.2. Readiness và liveness

Ví dụ tiếp tục trong cùng container spec:

```yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
```

Các giá trị trên chỉ là điểm bắt đầu. Timeout phải lớn hơn thời gian phản hồi bình thường có thể dự đoán; failure threshold phải cân bằng giữa phát hiện lỗi và tránh restart do một lần chậm ngắn hạn.

### 5.3. Manifest Deployment minh họa

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: payment-service
          image: registry.example.com/payment-service:native
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "256Mi"
            limits:
              cpu: "1500m"
              memory: "512Mi"
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 24
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
```

Thay image, port và tài nguyên theo service thực tế. Manifest này minh họa cấu trúc; cần bổ sung security context, service account, environment/secret và policy triển khai của môi trường.

### 5.4. Đọc hành vi khi probe fail

- Startup probe fail quá số lần cho phép: container bị restart vì ứng dụng không hoàn tất startup trong cửa sổ đã cấu hình.
- Readiness probe fail: pod không nhận traffic mới qua Service, nhưng process không bị restart chỉ vì readiness.
- Liveness probe fail: kubelet restart container sau khi đạt failure threshold.

Probe HTTP timeout cũng tiêu thụ tài nguyên. Health endpoint không nên chờ một truy vấn database không giới hạn hoặc khóa dài.

## 6. Health check với Docker

### 6.1. HEALTHCHECK là trạng thái container

Dockerfile có thể khai báo `HEALTHCHECK` để Docker đánh dấu container healthy/unhealthy. Ví dụ nếu image có sẵn `curl`:

```dockerfile
HEALTHCHECK --interval=10s --timeout=2s --start-period=30s --retries=3 \
  CMD curl --fail --silent http://127.0.0.1:8080/actuator/health/readiness || exit 1
```

Image tối giản/distroless thường không có shell, `curl` hoặc `wget`. Không copy một bộ công cụ lớn vào production image chỉ để chạy health check nếu orchestrator đã thực hiện HTTP probe từ bên ngoài container.

Docker đánh dấu trạng thái unhealthy nhưng bản thân `HEALTHCHECK` không bảo đảm Docker tự restart container. Hành vi restart phụ thuộc restart policy hoặc orchestrator.

### 6.2. Chọn đúng endpoint

Với service nhận traffic, readiness thường phù hợp cho health check của load balancer. Liveness dùng để phát hiện process không còn tiến triển. Không dùng endpoint chỉ kiểm tra PID hoặc port mở vì nó có thể báo healthy khi ứng dụng chưa xử lý request được.

### 6.3. Không làm health check trở thành tải nền lớn

Health check chạy lặp lại. Giữ endpoint nhẹ, có timeout và không gọi nhiều downstream service liên tục. Nếu cần kiểm tra sâu dependency, cân nhắc tần suất và phạm vi riêng thay vì đưa tất cả vào liveness.

## 7. Xử lý tín hiệu kết thúc và graceful shutdown

### 7.1. Container thường dừng bằng SIGTERM trước

Khi yêu cầu dừng container:

- Docker gửi SIGTERM tới process chính, chờ trong khoảng stop timeout, rồi gửi SIGKILL nếu process chưa thoát.
- Kubernetes bắt đầu termination grace period. Nếu có `preStop` hook, kubelet chạy hook đó trước; sau đó gửi SIGTERM tới process trong container. Nếu hết grace period mà process chưa dừng, container bị SIGKILL.

SIGTERM cho ứng dụng cơ hội ngừng nhận công việc mới, hoàn tất request đang chạy, đóng connection và flush dữ liệu cần thiết. SIGKILL không thể được ứng dụng bắt hoặc xử lý bằng shutdown hook.

### 7.2. Cấu hình graceful shutdown của Spring Boot

Có thể cấu hình rõ trong `application.properties`:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Khi ApplicationContext đóng, web server graceful shutdown ngừng nhận request mới và cho các request đang xử lý hoàn tất trong thời gian cho phép. Spring cũng đóng các bean theo lifecycle, gồm executor và các resource được quản lý bởi container.

`spring.lifecycle.timeout-per-shutdown-phase` là thời gian chờ cho mỗi lifecycle phase. Nếu ứng dụng có nhiều `SmartLifecycle` phase hoặc task shutdown dài, tổng thời gian đóng context có thể lớn hơn một giá trị phase. Hãy tính tổng thời gian cần thiết và dành thêm headroom cho orchestrator.

### 7.3. Phối hợp timeout của Spring và Kubernetes

Ví dụ:

```yaml
spec:
  terminationGracePeriodSeconds: 45
```

Với Spring lifecycle timeout 20 giây, grace period 45 giây chỉ là ví dụ. Hãy tính:

1. Thời gian `preStop` hook nếu có.
2. Thời gian ngừng nhận traffic và drain request đang chạy.
3. Thời gian hoàn tất các lifecycle phase và đóng executor/client.
4. Khoảng dự phòng trước khi kubelet gửi SIGKILL.

Grace period phải lớn hơn tổng thời gian cần thiết, không chỉ lớn hơn timeout của một phase. Nếu thời gian dừng thường xuyên vượt ngân sách, hãy tìm task treo hoặc downstream call không có timeout thay vì chỉ tăng grace period vô hạn.

### 7.4. Đảm bảo native executable nhận được signal

Ưu tiên Docker exec form:

```dockerfile
ENTRYPOINT ["/app/payment-service"]
```

Exec form chạy native binary trực tiếp làm process chính. Tránh shell wrapper không forward signal:

```dockerfile
# Tranh cach viet nay neu shell khong forward signal
ENTRYPOINT sh -c "/app/payment-service"
```

Nếu bắt buộc dùng script entrypoint, dùng `exec` để thay process shell bằng native binary:

```sh
#!/bin/sh
set -eu

# Thuc hien setup nho neu can
exec /app/payment-service "$@"
```

Khi ứng dụng tạo subprocess, cân nhắc init process nhỏ như `tini` hoặc tùy chọn init của Docker để forward signal và reap child process. Không thêm init process nếu ứng dụng không cần quản lý subprocess.

### 7.5. Không dựa vào shutdown hook để bảo đảm dữ liệu bền vững

Graceful shutdown chỉ tạo cơ hội hoàn tất công việc trong thời gian hữu hạn. Process vẫn có thể bị OOM kill, node mất điện, container runtime crash hoặc hết grace period.

Với message/payment/order cần bảo đảm không mất:

- Ghi trạng thái hoặc outbox record trong transaction bền vững.
- Dùng message broker/queue có acknowledgment.
- Thiết kế consumer idempotent để xử lý lại khi retry.
- Chỉ acknowledge sau khi side effect đã được lưu bền vững.
- Dùng timeout cho downstream request và đóng connection có kiểm soát.

Không giữ công việc quan trọng duy nhất trong memory và trông chờ shutdown hook sẽ luôn chạy.

## 8. Xử lý preStop và drain traffic

### 8.1. Khi nào cần preStop?

Kubernetes đã cập nhật endpoint/Service để pod terminating không nhận traffic mới, nhưng hệ thống load balancer hoặc service mesh bên ngoài có thể cần thêm thời gian để nhận trạng thái deregistration.

Chỉ dùng `preStop` khi có bước deregister/drain cụ thể. Hook chạy trong cùng termination grace period; thời gian hook tiêu thụ làm giảm thời gian còn lại cho ứng dụng graceful shutdown.

Không thêm lệnh sleep dài chỉ để “chờ cho chắc” nếu chưa đo được độ trễ cập nhật endpoint. Hãy đo quá trình drain và đặt thời gian dự phòng có căn cứ.

### 8.2. Readiness khi bắt đầu shutdown

Khi Spring context đóng, readiness state có thể chuyển sang refusing traffic. Điều này giúp endpoint health báo không sẵn sàng trong giai đoạn dừng.

Không giả định readiness probe là cơ chế drain duy nhất. Orchestrator, Service, ingress và load balancer có thời gian cập nhật riêng; kiểm thử toàn tuyến để xác nhận request mới không còn được gửi tới pod đang terminate.

### 8.3. Request đang chạy

Đặt giới hạn thời gian request phù hợp với shutdown budget. Nếu request có thể chạy lâu hơn termination grace period, cần:

- Giới hạn request timeout hoặc thời gian xử lý.
- Dùng job/message bền vững cho tác vụ dài.
- Trả trạng thái chấp nhận công việc và xử lý qua worker durable.
- Tính thời gian drain vào cấu hình triển khai.

Graceful shutdown không phải cơ chế vô hạn để chờ mọi request hoàn thành.

## 9. Dockerfile cho native executable

### 9.1. Image runtime tối giản

Một Dockerfile đơn giản cho binary đã được build:

```dockerfile
FROM <compatible-runtime-base>

WORKDIR /app
COPY --chown=10001:10001 payment-service /app/payment-service

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["/app/payment-service"]
```

`<compatible-runtime-base>` là placeholder. Chọn base image tương thích với cách native binary được link, ví dụ glibc hay musl và các shared libraries cần thiết. Binary build trên một hệ điều hành/ABI không thể mặc định chạy trên mọi image khác.

Chạy non-root khi ứng dụng không cần quyền đặc biệt. Đảm bảo thư mục làm việc, thư mục temp và các mount cần thiết có quyền phù hợp.

### 9.2. Không dùng shell form làm process chính

Exec form giúp native binary nhận SIGTERM trực tiếp và có exit code rõ ràng. Nếu dùng shell script, kết thúc script bằng `exec` như ví dụ ở phần trước.

### 9.3. Read-only filesystem và writable paths

Nếu bật read-only root filesystem, xác định rõ ứng dụng có cần ghi:

- `/tmp` hoặc thư mục temp.
- Log file nếu không ghi stdout/stderr.
- File upload hoặc export.
- Cache local hoặc file runtime.
- Certificate/trust store được mount.

Ưu tiên ghi log ra stdout/stderr và dùng volume/mount riêng cho dữ liệu cần ghi. Không lưu dữ liệu bền vững trong writable layer của container.

### 9.4. Kiểm tra binary và shared library

Trước khi deploy, xác nhận:

- OS và CPU architecture của image khớp binary.
- glibc/musl và shared library dependencies tương thích.
- CA certificates có mặt nếu gọi HTTPS.
- DNS, timezone và locale data phù hợp yêu cầu.
- User không root có quyền đọc binary và các file cần thiết.
- Port không yêu cầu privileged capability.

Native executable không tự mang theo mọi thư viện hệ điều hành. Base image quá tối giản có thể khiến binary không load được dù build đã thành công.

## 10. Kiểm thử giới hạn tài nguyên và vòng đời

### 10.1. Kiểm thử CPU và memory bằng Docker

Ví dụ:

```bash
docker run --rm \
  --name payment-native-limited \
  --cpus="1.0" \
  --memory="512m" \
  --pids-limit=256 \
  --stop-timeout=45 \
  -p 8080:8080 \
  payment-service:native
```

Chạy workload đại diện trong lúc container bị giới hạn. Theo dõi:

- Readiness time và first request latency.
- CPU throttling và CPU usage.
- Container memory, peak RSS và OOM events.
- Thread count, PID usage và executor queue.
- Error rate, p95/p99 và throughput.

Giá trị trên chỉ minh họa. Nếu container chạm memory limit, không tăng heap trước khi biết phần memory nào tăng.

### 10.2. Kiểm thử graceful stop

Trong khi gửi request liên tục:

```bash
docker stop --time 45 payment-native-limited
```

Xác nhận:

1. Process nhận SIGTERM và bắt đầu shutdown.
2. Readiness chuyển sang không sẵn sàng.
3. Request mới không còn được gửi tới instance đang dừng.
4. Request đang chạy được hoàn tất trong ngân sách.
5. Executor, connection pool và client được đóng.
6. Container thoát trước timeout, không bị SIGKILL.

### 10.3. Kiểm thử trong Kubernetes

Thử xóa pod khi đang có traffic:

```bash
kubectl delete pod <pod-name> --grace-period=45
```

Quan sát:

- Pod chuyển sang Terminating.
- Endpoint không còn được chọn cho traffic mới.
- Log thể hiện graceful shutdown bắt đầu và hoàn tất.
- Container exit trước grace period.
- Replica còn lại tiếp tục phục vụ và không bị quá tải.

Sau đó thử một kịch bản có request kéo dài gần shutdown budget để xác nhận timeout và hành vi drain.

### 10.4. Kiểm thử OOM có kiểm soát

Trong môi trường test, tạo tải hoặc cấu hình memory limit thấp để xác nhận monitoring phát hiện OOM. Không thực hiện phép thử phá hủy trên production.

Xác minh:

- Container state và exit reason.
- Cgroup/kernel OOM events.
- Alert được phát.
- Orchestrator restart theo policy.
- Ứng dụng khởi động lại và readiness phục hồi.

Đừng mong có graceful shutdown log trong trường hợp SIGKILL do OOM.

## 11. Cấu hình vận hành hoàn chỉnh

### 11.1. Application properties

Một cấu hình minh họa:

```properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s

management.endpoint.health.probes.enabled=true
management.endpoint.health.show-details=never
management.endpoints.web.exposure.include=health
```

Các giá trị timeout cần khớp với request duration và termination grace period. Nếu có nhiều lifecycle phase, tính tổng thời gian cần thiết thay vì coi timeout mỗi phase là toàn bộ thời gian shutdown.

### 11.2. Security context cho Kubernetes

Nếu binary và ứng dụng không cần quyền root, có thể chạy container với user không đặc quyền:

```yaml
containers:
  - name: payment-service
    securityContext:
      runAsNonRoot: true
      runAsUser: 10001
      runAsGroup: 10001
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop:
          - ALL
```

Khi bật read-only root filesystem, mount writable volume cho các đường dẫn thực sự cần ghi, chẳng hạn `/tmp`. Kiểm tra ứng dụng không cố ghi log, file upload hoặc cache vào root filesystem.

### 11.3. Docker stop timeout

Docker có thể đặt stop timeout khi chạy container:

```bash
docker run -d --rm \
  --name payment-native \
  --stop-timeout=45 \
  --cpus="1.5" \
  --memory="512m" \
  -p 8080:8080 \
  payment-service:native
```

Timeout này là thời gian Docker chờ process sau SIGTERM trước khi gửi SIGKILL. Nó cần phù hợp với thời gian Spring shutdown và thời gian drain request.

### 11.4. Các biến môi trường runtime

CPU/memory limits và probe config thuộc deployment. Các giá trị ứng dụng như server port, database URL, cache endpoint và timeout có thể truyền qua environment hoặc secret/config management.

Không đưa credential vào Dockerfile, build argument có thể lưu trong image history hoặc native binary. Cấp secret khi deploy và kiểm soát quyền truy cập.

## 12. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Startup probe liên tục fail | CPU limit thấp, timeout ngắn, endpoint sai hoặc dependency startup chậm | Xem startup log, CPU throttling, probe path/port và thời gian readiness |
| Readiness fail nhưng liveness pass | Ứng dụng chưa sẵn sàng hoặc dependency bắt buộc chưa đáp ứng | Xem readiness group và trạng thái dependency |
| Liveness fail rồi restart loop | Process treo, health endpoint không phản hồi hoặc liveness kiểm tra quá nhiều dependency | Giữ liveness nhẹ, xem thread dump/metrics và log trước restart |
| Container exit 137 | SIGKILL do OOM hoặc hết stop timeout | Kiểm tra OOMKilled/cgroup events và termination events |
| Container bị OOM dù heap còn trống | Thread stack, direct/native memory, mmap hoặc memory khác làm RSS tăng | Đo container memory/RSS, thread count và native allocations |
| Native binary không chạy trong image tối giản | Sai ABI, thiếu shared library, CA cert hoặc quyền file | Kiểm tra target OS/CPU, glibc/musl, library và user permissions |
| Shutdown không có log hoàn tất | Process bị SIGKILL hoặc signal không tới binary | Kiểm tra PID 1, exec-form entrypoint, stop timeout và grace period |
| Request bị cắt khi rollout | Grace period ngắn, drain chưa xong hoặc request timeout quá dài | Đo request duration, endpoint removal và shutdown phases |
| Async task bị mất khi restart | Task chỉ nằm trong memory executor | Dùng durable queue/outbox và retry idempotent |

## 13. Quy trình triển khai và kiểm chứng

### Bước 1 — Đo baseline dưới giới hạn thực tế

Chạy native executable với CPU/memory limits dự kiến. Đo readiness, RSS/container memory, CPU throttling, throughput, p95/p99 và peak memory.

### Bước 2 — Cấu hình probes

Bật Actuator health groups. Chọn startup/readiness/liveness path, kiểm tra endpoint trên cùng server port và xác nhận liveness không phụ thuộc dependency ngoài không cần thiết.

### Bước 3 — Cấu hình graceful shutdown

Đặt `server.shutdown=graceful`, timeout cho lifecycle phase và termination grace period. Dùng exec-form entrypoint để native binary nhận SIGTERM.

### Bước 4 — Kiểm thử rollout

Gửi request liên tục trong khi xóa pod hoặc chạy `docker stop`. Xác nhận request mới được drain, request đang chạy hoàn tất trong ngân sách và process thoát trước SIGKILL.

### Bước 5 — Kiểm thử giới hạn

Chạy burst/soak dưới CPU quota và memory limit. Theo dõi throttling, peak RSS, OOM events, thread/PID usage và executor queue.

### Bước 6 — Đưa vào vận hành

Đặt alert cho OOMKilled, restart count, probe failures, CPU throttling, memory saturation và shutdown timeout. Lưu lại cấu hình limits/probes/grace period cùng phiên bản image để có thể truy nguyên.

## 14. Bài thực hành

### Bài 1 — CPU và memory

Chạy cùng một native image với hai cấu hình CPU quota và hai memory limits khác nhau. Ghi readiness time, throughput, p95 latency, CPU throttling và peak container memory. Giải thích vì sao heap usage không đại diện toàn bộ RSS.

### Bài 2 — Health probes

Bật Actuator liveness/readiness groups. Tạo một tình huống dependency bắt buộc tạm thời không sẵn sàng và quan sát readiness. Sau đó mô phỏng process không phản hồi để quan sát liveness. Xác nhận hai trạng thái dẫn tới hành vi orchestrator khác nhau.

### Bài 3 — Graceful shutdown

Gửi request có thời gian xử lý đã biết, sau đó dừng container bằng SIGTERM. Thử nhiều termination timeout. Ghi request hoàn tất, request bị cắt, thời gian shutdown và trạng thái exit.

### Bài 4 — PID 1 và entrypoint

So sánh exec-form entrypoint với shell wrapper không dùng `exec`. Quan sát signal delivery và thời gian process thoát. Chuyển wrapper sang `exec` rồi lặp lại.

### Câu hỏi tự kiểm tra

1. Vì sao native executable vẫn có thể bị OOM kill dù managed heap chưa đạt max?
2. CPU request khác CPU limit trong Kubernetes như thế nào?
3. Vì sao liveness không nên phụ thuộc trực tiếp vào database hoặc Redis?
4. Khi nào startup probe hữu ích hơn việc tăng liveness failure threshold?
5. Readiness fail có tự restart container không?
6. Docker và Kubernetes xử lý SIGTERM/SIGKILL như thế nào?
7. Vì sao termination grace period phải tính cả preStop hook và lifecycle shutdown?
8. Vì sao Docker exec-form ENTRYPOINT giúp graceful shutdown đáng tin cậy hơn?
9. Vì sao shutdown hook không thể bảo đảm message hoặc payment không bị mất?

**Ghi nhớ:** giới hạn CPU ảnh hưởng startup và latency; memory limit áp dụng cho toàn bộ process/container chứ không riêng heap. Startup, readiness và liveness có mục đích khác nhau. Khi dừng, hãy để native binary nhận SIGTERM trực tiếp, cho Spring đủ thời gian drain request và đóng tài nguyên, đồng thời dùng queue/outbox cho công việc cần độ bền. Kiểm thử dưới đúng limits, probes và termination timeout trước khi đưa image vào production.

