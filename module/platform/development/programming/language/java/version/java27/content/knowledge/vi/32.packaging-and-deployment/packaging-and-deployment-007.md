# Theo dõi sau triển khai, rollout và khôi phục phiên bản trong Java 27

Trong chương **Đóng gói và triển khai** của lộ trình **Java 27**, một lần build thành công hoặc một container đạt trạng thái `Running` chưa có nghĩa release đã an toàn. Lỗi chỉ xuất hiện dưới lưu lượng thật có thể nằm ở database, tài nguyên JVM, giao thức message, logic nghiệp vụ hoặc sự tương tác giữa phiên bản cũ và mới.

Một quy trình phát hành tốt phải làm được ba việc liên tục: **quan sát tác động sau triển khai**, **đưa phiên bản mới vào sử dụng có kiểm soát (rollout)** và **khôi phục dịch vụ khi có lỗi (rollback hoặc roll-forward)**. Các quyết định này dựa trên bằng chứng cụ thể, không dựa riêng vào việc lệnh deploy trả exit code `0`.

Java 27 cung cấp các công cụ hiện hành như **Java Flight Recorder (JFR)**, **`jcmd`**, **Unified JVM Logging**, **JMX/MXBeans**, cùng hệ sinh thái telemetry gồm metrics, logs và distributed traces. Ở tầng hạ tầng, có thể dùng rolling update, canary, blue-green hoặc feature flags. Bài này sử dụng Kubernetes để minh họa một số lệnh vận hành nhưng **không bắt buộc ứng dụng Java chạy trên Kubernetes**.

> **Nguyên tắc quan trọng:** quay lại image hoặc JAR cũ **không tự hoàn tác database schema, dữ liệu đã sửa, message đã phát, giao dịch đã thực hiện hay secrets/configuration ngoài ứng dụng**. Kế hoạch rollback phải được lập trước khi rollout.

## 1. Phân biệt build, artifact, release, deploy và rollout

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Build** | Chuyển source thành kết quả có thể phân phối | `orders.jar`, modular JAR hoặc image |
| **Artifact** | Đơn vị có thể triển khai, định danh bằng version/hash | Image có SHA-256 digest |
| **Release** | Phiên bản được quyết định đưa vào môi trường | Release `2.4.0` |
| **Deploy** | Đưa artifact/config vào môi trường thực thi | Pod mới đã được tạo |
| **Rollout** | Tăng dần số instance hoặc traffic sử dụng release | 5% → 25% → 100% |
| **Rollback** | Trở về trạng thái ứng dụng/traffic tương thích trước | Quay routing về bản stable |
| **Roll-forward** | Đưa bản sửa mới thay vì trở về bản trước | Hotfix `2.4.1` |

Một Deployment có thể báo các Pods `Ready` nhưng vẫn có lỗi nghiệp vụ như ghi trùng đơn hàng. Ngược lại, một lần deploy thất bại chưa chắc có ảnh hưởng người dùng nếu traffic chưa từng được chuyển sang phiên bản đó.

### 1.1. Vòng đời phát hành có các cổng kiểm tra

```text
Commit + kiểm thử
       |
       v
Build artifact bất biến + scan
       |
       v
Staging: smoke, contract, migration
       |
       v
Stable A  <--------- Canary B (traffic nhỏ)
       |                     |
       |               Đo metrics và kiểm thử
       |                     |
       |              +------+------+
       |              |             |
       |            FAIL           PASS
       |              |             |
       v              v             v
   Giữ A         Dừng B          Tăng traffic B
                                       |
                                       v
                                100% + soak
                                       |
                                       v
                                 Ghi release evidence
```

Quy trình phải có cơ chế **tạm dừng**; không được mặc định tăng traffic chỉ vì hết một khoảng thời gian cố định.

## 2. Định nghĩa thành công bằng SLI, SLO và tác động nghiệp vụ

- **SLI:** đại lượng quan sát được, ví dụ tỷ lệ request thành công theo tiêu chí nghiệp vụ.
- **SLO:** mục tiêu của SLI trên một cửa sổ thời gian xác định.
- **Error budget:** mức sai lệch có thể chấp nhận so với SLO, giúp cân bằng rủi ro release và độ tin cậy.

Một công thức đơn giản:

\[
\text{Success rate} =
\frac{\text{Số thao tác đáp ứng hợp đồng thành công}}
{\text{Tổng thao tác hợp lệ được tiếp nhận}}
\]

Không phải mọi HTTP `4xx` đều là lỗi hệ thống; `400` do input sai có thể là kết quả đúng. Đồng thời, một HTTP `200` chứa tổng tiền sai vẫn là **lỗi nghiêm trọng** dù không tăng tỷ lệ `5xx`.

| Loại dịch vụ | Chỉ số nghiệp vụ | Chỉ số kỹ thuật |
| --- | --- | --- |
| REST API | Tạo đơn hàng đúng, không trùng | 5xx, timeout, p95/p99 |
| Thanh toán | Giao dịch không nhân đôi, đối soát đúng | Gateway failure, timeout, pending |
| Worker queue | Message hoàn tất đúng và không mất | Queue age, lag, retry, DLQ |
| Batch job | Kết quả đúng trước deadline | Duration, exit code, resource use |
| Streaming | Session liên tục, reconnect đúng | Disconnect rate, backpressure |

**Không có một ngưỡng rollback cố định cho mọi hệ thống.** Release plan cần ghi các chỉ số và ngưỡng được chấp thuận theo mức rủi ro và baseline thật.

## 3. Bốn tín hiệu vàng và metric JVM

Bốn nhóm quan sát nền tảng:

| Tín hiệu | Ví dụ | Điều cần biết |
| --- | --- | --- |
| **Traffic** | Requests/s, operations/s | Có đủ lưu lượng để đánh giá không? |
| **Errors** | HTTP 5xx, business errors | Bản mới có tăng lỗi không? |
| **Latency** | p50/p95/p99 | Người dùng có chờ lâu hơn? |
| **Saturation** | Queue depth, CPU, DB-pool pending | Có tài nguyên nào sắp cạn? |

Với Java 27, cần đối chiếu thêm:

- **Heap used sau GC**, allocation rate, số lần và độ trễ GC.
- **RSS/process memory** và native resources, không chỉ `-Xmx`.
- **CPU JVM, GC và compiler threads**, CPU throttling trong container.
- **Active tasks và virtual threads** theo công cụ phù hợp.
- **Connection pool**: active, idle, pending và thời gian giữ connection.
- **Executor queue**, số task đang chạy/chờ, số task bị reject.
- **JIT code cache, metaspace, direct buffers, file descriptors** khi cần.
- **Startup/readiness duration**, số lần restart/OOM-kill.
- **Thông lượng worker và queue age** nếu service không phục vụ HTTP.

### 3.1. Hiểu đúng heap và memory limit

Java heap không phải toàn bộ bộ nhớ process. Metaspace, code cache, thread stacks, direct buffers và native libraries có footprint riêng. Nếu đặt `-Xmx` sát giới hạn RAM của container, process có thể bị **OOM-kill** dù Java heap chưa vượt `-Xmx`.

Heap tăng ngay sau startup có thể là warm-up cache hợp lệ. Muốn nghi memory leak, cần quan sát **live set sau GC** qua nhiều chu kỳ và object retention, không chỉ một ảnh chụp.

### 3.2. Snapshot heap bằng API quản lý chuẩn

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

public class HeapSnapshot {
    public static void main(String[] args) {
        MemoryUsage heap =
            ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();

        System.out.println("used = " + heap.getUsed());
        System.out.println("committed = " + heap.getCommitted());
        System.out.println("max = " + heap.getMax());
    }
}
```

Giá trị `max` có thể bằng `-1` theo contract khi không xác định được. Với JPMS cần `requires java.management;`. Đoạn này chỉ đọc snapshot; trong production thường xuất telemetry bằng JMX, exporter hoặc instrumentation framework có kiểm soát.

## 4. Logs, metrics, traces: gắn với phiên bản phát hành

Ba kênh tín hiệu có mục tiêu khác nhau:

| Loại | Câu hỏi |
| --- | --- |
| **Metrics** | Lỗi, latency, saturation đang thay đổi bao nhiêu? |
| **Structured logs** | Lỗi xảy ra ở bước nào, với nguyên nhân gì? |
| **Distributed traces** | Thời gian bị tiêu tốn tại service/span nào? |
| **JFR** | JVM đang dùng CPU, cấp phát hoặc chờ lock ở đâu? |

Mỗi dữ liệu cần có khả năng liên kết tới **artifact thực sự đang chạy**:

```text
service.name = orders
service.version = 2.4.0
deployment.environment = production
release.id = release-20261127-01
image.digest = sha256:...
```

Có thể dùng **OpenTelemetry Java** để liên kết traces, metrics và logs theo resource attributes và semantic conventions phù hợp. Đừng trộn nhãn tùy ý của ứng dụng với một chuẩn mà chưa kiểm tra ý nghĩa thực tế.

### 4.1. Ví dụ log có cấu trúc

```json
{
  "time": "2026-11-27T13:40:00Z",
  "level": "ERROR",
  "service": "orders",
  "version": "2.4.0",
  "operation": "createOrder",
  "trace_id": "example-trace-id",
  "error_type": "DownstreamTimeout"
}
```

Không ghi access token, mật khẩu, dữ liệu thẻ hoặc payload nhạy cảm vào log. Trace ID giúp liên kết nhưng không phải credential.

### 4.2. Tránh metric cardinality vô hạn

Metric như:

```text
http_requests_total{release="2.4.0",route="/orders",status="500"}
```

có thể hữu ích khi nhãn có tập giá trị giới hạn. Ngược lại, `request_id`, `user_id` hay URL đầy đủ mang UUID làm nhãn có thể tạo vô số series, tăng chi phí hoặc làm hệ thống metrics quá tải. Để định danh từng request trong logs/traces được cấp quyền.

## 5. Baseline và cách so sánh canary đúng

Trước khi mở traffic bản B, ghi lại:
1. SLI/SLO ở bản A trong khoảng thời gian tương đương.
2. Traffic mix theo route, tenant, vùng hoặc loại request quan trọng.
3. Những cảnh báo đang tồn tại và thay đổi downstream độc lập.
4. Version/config/schema đang chạy và thời điểm deploy.
5. Các thay đổi cùng giờ: chiến dịch, batch, DB maintenance, autoscaling.

Nếu B chỉ nhận 5% traffic, chỉ số lỗi toàn service có thể vẫn thấp dù B bị lỗi nặng. Cần so sánh **A và B theo cohort tương đương**.

```text
Stable A                 Canary B
route=/orders            route=/orders
error rate               error rate
p95/p99                  p95/p99
DB-pool pending          DB-pool pending
GC pause                 GC pause
```

Các cohort vẫn có thể lệch nhau về cache warmness hoặc dữ liệu khách hàng. Không đồng nhất correlation với causation; ghi lại traffic assignment và kiểm tra thêm trace.

**Với ít request**, một lỗi đơn lẻ có thể tạo tỷ lệ 100%. Release gate cần điều kiện **số mẫu tối thiểu**, quan sát đủ lâu và smoke/synthetic tests thay thế khi traffic quá ít.

## 6. Startup, liveness và readiness không phải một

Kubernetes và nhiều nền tảng orchestrator hỗ trợ các khái niệm:

| Probe | Ý nghĩa | Hành động thông thường nếu thất bại |
| --- | --- | --- |
| **Startup** | Ứng dụng đã hoàn thành giai đoạn khởi động? | Cho thêm thời gian hoặc restart nếu quá giới hạn |
| **Liveness** | Process có đang ở trạng thái cần restart để phục hồi? | Restart khi liên tục fail |
| **Readiness** | Instance có thể nhận traffic mới an toàn không? | Tạm rút khỏi tập endpoint của service |

**Không nên dùng liveness để truy vấn nặng mọi dependency.** Database chập chờn có thể khiến toàn bộ Pods bị restart theo dây chuyền. Readiness cũng không phải “kiểm tra sâu tất cả hệ thống ngoài mỗi vài giây”; nó phải phản ánh **khả năng phục vụ hiện tại** và tránh flapping vô ích.

Ví dụ logic:
- Chưa đọc xong cấu hình bắt buộc: not ready.
- Listener không hoạt động: not ready hoặc startup failure.
- Recommendation service tùy chọn bị lỗi nhưng core API vẫn hoạt động: có thể ready ở chế độ degraded.
- App đang draining khi shutdown: ngừng nhận công việc mới.

### 6.1. Ví dụ chạy được: health endpoints bằng Java 27

Mẫu tối giản dùng module JDK `jdk.httpserver`. **Đây là demo**, không thay thế HTTP framework hoặc quản lý shutdown của service sản xuất.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ProbeDemo {
    private static final AtomicBoolean READY = new AtomicBoolean();

    private static void reply(
            HttpExchange exchange, int code, String message)
            throws IOException {
        byte[] body = message.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=UTF-8"
        );
        exchange.sendResponseHeaders(code, body.length);
        try (var out = exchange.getResponseBody()) {
            out.write(body);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 8080), 0
        );

        server.createContext("/livez",
            exchange -> reply(exchange, 200, "alive"));

        server.createContext("/readyz", exchange -> {
            boolean ready = READY.get();
            reply(exchange, ready ? 200 : 503,
                ready ? "ready" : "not-ready");
        });

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            READY.set(false);
            server.stop(5);
        }, "probe-shutdown"));

        server.start();
        // Trong production: chỉ set true sau các bước init bắt buộc.
        READY.set(true);

        System.out.println("http://127.0.0.1:8080/readyz");
    }
}
```

Lệnh thử:

```text
javac --add-modules jdk.httpserver ProbeDemo.java
java --add-modules jdk.httpserver ProbeDemo
```

Trong terminal khác:

```text
curl -i http://127.0.0.1:8080/livez
curl -i http://127.0.0.1:8080/readyz
```

Ví dụ bind loopback nên **không thể được kubelet/container khác truy cập qua Pod IP**. Khi triển khai thật phải bind port/interface phù hợp và bảo vệ management endpoints bằng policy mạng. Ngoài ra, `HttpServer.stop(5)` là minh họa best-effort, không bảo đảm drain mọi loại connection hoặc request.

## 7. Artifact bất biến: điều kiện cần cho rollback tái hiện được

Một tag như `latest` có thể được ghi đè. Nếu rollback bằng một tag không cố định, có thể nhận artifact khác với bản từng chạy ổn định.

Hồ sơ release nên ghi:

```text
releaseId       = release-20261127-01
appVersion      = 2.4.0
gitCommit       = <full-commit>
artifactSha256  = <sha256>
imageDigest     = sha256:<digest>
javaRuntime     = <exact-vendor-and-build>
configRevision  = <revision>
schemaRange     = <compatibility-contract>
```

Đây là dữ liệu minh họa, không phải format chuẩn của công cụ cụ thể.

### 7.1. Những gì cần giữ cùng release

- Artifact/JAR/container image **có digest được xác minh**.
- Thông tin build và dependency/SBOM theo policy.
- Phiên bản JDK, kiến trúc CPU/OS và build của runtime.
- Version config, feature flags và cách tra cứu secrets **không lưu secret raw**.
- Release notes, changelog, thay đổi schema/message và lịch sử rollback.
- Test evidence và tiêu chí gate đã đạt.

### 7.2. Nếu dùng `jlink` hoặc `jpackage`

Java 27 có `jlink` để tạo runtime image theo tập module và `jpackage` để tạo application package theo nền tảng. Nếu release đi cùng **custom runtime**, rollback đáng tin phải phục hồi **cả mã ứng dụng lẫn runtime tương thích**. Không mặc định JAR cũ sẽ chạy được trên bất kỳ custom runtime mới nào nếu thiếu module, provider hoặc native dependency.

Artifact bất biến cũng **không phải lý do trì hoãn cập nhật lỗ hổng bảo mật**. Phải có chính sách rebuild/rotation/supported versions.

## 8. Bốn chiến lược rollout

### 8.1. Rolling update

Thay các instance cũ A bằng B từng bước:

```text
A A A A
A A A B
A A B B
A B B B
B B B B
```

Đặc điểm:
- A/B cùng chạy tạm thời; cần tương thích data/schema/message.
- Readiness quyết định instance mới được phục vụ khi nào.
- Cần capacity cho `maxSurge` nếu không muốn giảm availability.
- **Không tự cung cấp 5% traffic weighted routing chuẩn**.

### 8.2. Canary

Phân traffic theo tỷ lệ hoặc cohort:

```text
Stable A 95%    <--- gateway/router ---> Users
Canary B  5%           |
                      v
                 Compare metrics
                 PASS -> 25% -> 50% -> 100%
                 FAIL -> ngừng B, giữ A
```

Thường cần gateway/ingress/service mesh hoặc cơ chế routing hỗ trợ phân phối. Không coi `replicas: 1` cạnh `replicas: 19` là bảo đảm chính xác 5% request tới B.

### 8.3. Blue-green

Chuẩn bị cả môi trường A và B rồi chuyển tuyến traffic:

```text
Blue:  A (production traffic)
Green: B (ready + smoke tests)

Sau cutover:
Blue:  A (standby)
Green: B (production traffic)
```

Phù hợp khi có đủ tài nguyên và yêu cầu chuyển nhanh. Vẫn phải xử lý in-flight requests, WebSocket sessions, shared database và sự tương thích dữ liệu.

### 8.4. Recreate

Dừng A trước khi chạy B. Có thể cần khi không cho phép mixed versions, single-writer constraint hoặc cần một maintenance window, nhưng **có thể gây downtime**.

| Chiến lược | Lợi thế | Điều phải kiểm soát |
| --- | --- | --- |
| Rolling | Thay thế từ từ, dùng hạ tầng sẵn | Mixed versions, readiness |
| Canary | Giới hạn blast radius | Traffic weights, sample size, gates |
| Blue-green | Cutover/revert traffic nhanh | Double capacity, shared state |
| Recreate | Không chạy hai version đồng thời | Downtime, phục hồi |
| Feature flag | Tắt một chức năng mà không đổi image | Flag state, dữ liệu đã ghi, vòng đời flag |

Feature flag có thể giảm ảnh hưởng của tính năng mới, nhưng **không thay thế rollback** khi JVM crash, schema không tương thích hoặc service đã ghi dữ liệu sai.

## 9. Ví dụ Deployment Kubernetes có kiểm soát readiness

Manifest này là **ví dụ học tập**; cần thay digest thật, namespace, probes, resource sizing và security context theo hệ thống. `ProbeDemo` ở mục 6 bind loopback nên **không phù hợp trực tiếp** với HTTP probe qua Pod IP.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  labels:
    app: orders
spec:
  replicas: 3
  revisionHistoryLimit: 10
  minReadySeconds: 10
  progressDeadlineSeconds: 600
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
        app.kubernetes.io/version: "2.4.0"
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: orders
          image: registry.example.invalid/orders@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            failureThreshold: 24
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            failureThreshold: 3
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
```

`REPLACE_WITH_REAL_DIGEST` là placeholder, **không phải digest có thể triển khai**.

Các ý nghĩa cần hiểu:
- `maxSurge: 1`: có thể tạo thêm một Pod khi rollout.
- `maxUnavailable: 0`: không chủ động giảm số replica khả dụng trong rolling update; vẫn cần capacity và chính sách phù hợp.
- `minReadySeconds: 10`: đòi Pod ready liên tục đủ khoảng trước khi tính Available.
- `progressDeadlineSeconds: 600`: báo rollout không tiến triển đúng thời hạn, **không tự rollback**.
- Startup probe cho ứng dụng thêm thời gian init; liveness/readiness bắt đầu sau khi startup thành công.
- Probe không tự kiểm tra mọi đường nghiệp vụ.
- `terminationGracePeriodSeconds` là ngân sách shutdown của container, không phải thời gian không giới hạn.

Các giá trị 5, 10, 24, 45 hay 600 giây chỉ minh họa. Cần đo **startup duration, request deadlines, capacity, CPU throttling** trước khi chọn.

## 10. Release gates cho từng giai đoạn

Một kế hoạch canary có thể được biểu diễn như sau:

| Bước | Traffic B | Điều kiện trước khi tăng |
| --- | ---: | --- |
| Preflight | 0% | Artifact, config, schema compatibility và baseline PASS |
| Smoke | Chỉ nội bộ | Startup, API quan trọng, auth, DB/messaging PASS |
| Canary đầu | 5% | Lỗi, latency và nghiệp vụ không vượt guardrails |
| Canary giữa | 25% | Đủ mẫu, GC/memory/DB pool ổn, không backlog |
| Canary rộng | 50% | SLO và dữ liệu ổn dưới tải thực |
| Full rollout | 100% | Gates + người chịu trách nhiệm xác nhận |
| Soak | 100% | Theo dõi thêm đủ chu kỳ tải/nghiệp vụ |

**Không dùng 5 phút cố định cho mọi hệ thống.** Một batch job chỉ chạy mỗi giờ cần theo dõi lâu hơn, còn API có hàng nghìn request mỗi giây có thể sớm có mẫu đủ lớn.

### 10.1. Gate tự động cần có điều kiện bảo vệ

Một policy có thể kiểm tra:
1. Tối thiểu số request/operations theo workload.
2. Error rate/latency canary không vượt ngưỡng đã duyệt so với stable.
3. Không có crash loop, OOM-kill, DB-pool saturation vượt guardrail.
4. Không có lỗi nghiệp vụ nghiêm trọng: ghi sai tiền, mất message, lộ tenant data.
5. Không có cảnh báo phát hành đang mở chưa được giải thích.

Khi đã xác nhận **sai dữ liệu, lộ thông tin hoặc side effect tài chính không thể đảo**, phải **dừng mở rộng ngay** theo runbook, không chờ đủ số request để qua cổng thống kê.

## 11. JDK 27: phân tích warm-up và resource regression

Một JVM mới khởi động có thể dành CPU cho class loading, JIT compilation và cache warming. Vì vậy metric ngay sau deploy có thể khác so với instance A đã chạy nhiều giờ.

| Hiện tượng | Có thể bình thường | Khi nào đáng điều tra |
| --- | --- | --- |
| CPU tăng khi khởi động | JIT, class initialization | Không giảm, request timeout |
| Heap used tăng | Cache ban đầu | Live set sau GC tăng tiếp |
| Code cache tăng | JIT tạo machine code | Gần đầy hoặc compilation bị hạn chế |
| GC tăng | Allocation tăng theo load | Pause hoặc throughput vượt ngưỡng |
| Virtual threads đông | I/O tasks đồng thời | Nhiều task không kết thúc, downstream backlog |
| RSS tăng, heap ổn | Native memory khác heap | Đến sát container memory limit |
| Ready chậm | Warm-up hoặc init dependencies | Vượt startup budget hoặc lỗi init |

Cần đo **cùng workload**, so sánh release A/B và kết hợp health/latency. Không tự kết luận “Java 27 có memory leak” từ một ảnh chụp heap ngay sau khởi động.

## 12. Graceful shutdown khi thay phiên bản

Orchestrator có thể yêu cầu một Pod ngừng hoạt động. Ứng dụng Java cần:
1. Không nhận thêm request/job mới hoặc rút readiness khi draining.
2. Hoàn tất hoặc hủy các in-flight tasks theo deadline.
3. Đảm bảo transaction commit/rollback theo contract.
4. Ack/nack/requeue message đúng để không mất/nhân đôi.
5. Đóng HTTP client, JDBC pool, executor, streams và những tài nguyên có owner.
6. Kết thúc trong thời hạn orchestrator cho phép.

Java hỗ trợ shutdown hook:

```java
Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    // Chuyển trạng thái sang draining.
    // Ngừng nhận task mới.
    // Đợi hoặc hủy in-flight work theo policy.
    // Đóng các tài nguyên do application sở hữu.
}));
```

**Shutdown hook không chạy trong mọi trường hợp**, chẳng hạn bị `SIGKILL`, mất điện hoặc kernel OOM-kill. Nó không thay thế idempotency và transaction design.

### 12.1. `preStop` không cho thêm thời gian miễn phí

Trong Kubernetes, thời gian chạy `preStop` **nằm trong** `terminationGracePeriodSeconds`. Một hook kéo dài gần hết grace period có thể khiến process không đủ thời gian hoàn tất shutdown sau khi nhận TERM.

Thiết kế draining phải xét:
- Deadline của request/streaming sessions.
- Message visibility timeout/checkpoints.
- Load balancer endpoint propagation.
- DB transaction/lease lifecycle.
- Sức chứa của những instance còn lại.

Không dùng `sleep` dài trong `preStop` như một giải pháp mặc định nếu chưa xác minh lý do và ngân sách thời gian.

## 13. Quan sát sâu với `jcmd`, JFR và GC logs
Khi có regression, sử dụng công cụ đúng với triệu chứng, không thu thập dữ liệu nặng chỉ vì dashboard có cảnh báo.

### 13.1. Xác định đúng JVM

```text
java --version
jcmd -l
jcmd <pid> VM.version
jcmd <pid> VM.command_line
```

Trong container, PID và quyền attach phụ thuộc namespace/cấu hình. Chỉ thao tác với JVM đích đã được phép, tránh thu nhầm dữ liệu của dịch vụ khác.

### 13.2. Java Flight Recorder (JFR)

Có thể bật một recording có thời hạn khi điều tra:

```text
jcmd <pid> JFR.start name=PostDeploy settings=profile duration=60s filename=post-deploy.jfr
jcmd <pid> JFR.check
```

JFR hỗ trợ quan sát CPU samples, object allocation, GC, thread contention và I/O tùy event settings. Dùng Java Mission Control hoặc công cụ tương thích để liên hệ sự kiện với thời điểm rollout.

Không mặc định recording `settings=profile` bật mọi event ở mức chi tiết tối đa. Kiểm tra cấu hình JFR thực tế nếu không tìm thấy sự kiện mong muốn. File `.jfr` có thể chứa thông tin nhạy cảm; đặt quyền truy cập, kích thước và retention thích hợp.

### 13.3. Thread dumps

```text
jcmd <pid> Thread.print -l
jcmd <pid> Thread.dump_to_file -format=json threads.json
```

Trong Java 27, `Thread.dump_to_file` là lựa chọn phù hợp khi cần quan sát **nhiều virtual threads**, bao gồm những virtual threads không thể hiện đầy đủ trong dump truyền thống. Nó không tự khẳng định deadlock và không phải một snapshot tuyệt đối đồng nhất giữa mọi thread.

Nhìn thấy nhiều threads `WAITING` **chưa đủ** để kết luận hệ thống bị kẹt: worker có thể đang chờ queue hợp lệ. Đối chiếu **nhiều dumps**, các stack, tài nguyên đang chờ và metrics pool/queue để dựng giả thuyết.

### 13.4. Heap và GC logging

```text
jcmd <pid> GC.heap_info
```

Khi khởi chạy một runnable JAR, có thể cấu hình Unified Logging:

```text
java -Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags -jar orders.jar
```

Lệnh trên chỉ minh họa **cấu hình khởi động**, không áp dụng nguyên vẹn cho một process đang chạy. Khi muốn thay đổi logging ở runtime, xác minh diagnostic commands mà JVM đích hỗ trợ và đánh giá impact.

**Không lấy heap dump theo phản xạ** khi lỗi chính là request timeout: heap dump có thể dừng ứng dụng đáng kể, tốn dung lượng và chứa dữ liệu nhạy cảm. Thu thập theo quyền được cấp và theo mức độ cần thiết.

### 13.5. Khi nào ưu tiên công cụ nào?

| Triệu chứng | Điều cần quan sát |
| --- | --- |
| p99 tăng và CPU cao | JFR CPU/execution samples; GC, compiler, ứng dụng |
| DB pool pending tăng | Connection checkout duration, slow queries, thread stacks |
| RSS tăng nhưng heap ổn | Native memory, direct buffers, metaspace, thread stacks |
| Heap live set tăng | GC statistics, allocation profiling, retention |
| Nhiều virtual threads không hoàn tất | `Thread.dump_to_file`, task metrics và downstream |
| Readiness thất bại khi startup | Init logs, configuration, module/runtime và dependency readiness |
| `OOMKilled` | Container memory limit, RSS, heap/native memory, traffic mix |
| `CrashLoopBackOff` | Container exit code, startup logs, probes, config/secrets |

## 14. Tình huống giả định: canary gây tắc nghẽn database

Giả sử có hai phiên bản:

- Stable `orders:2.3.9`, đang phục vụ 90% traffic.
- Canary `orders:2.4.0`, đang phục vụ 10% traffic.

Sau một khoảng quan sát, có số liệu **minh họa**:

| Chỉ số | Stable | Canary |
| --- | ---: | ---: |
| Requests/s | 450 | 50 |
| HTTP 5xx | 0,2% | 4,5% |
| p95 latency | 180 ms | 650 ms |
| Pending JDBC connections | 1–3 | 35 |
| Heap used sau GC | ~380 MiB | ~390 MiB |
| Container restarts | 0 | 0 |

**Cách suy luận hợp lý:** canary có lỗi/latency tăng mạnh, DB pool chờ nhiều hơn; chưa có bằng chứng rõ về memory leak vì heap sau GC tương đương. Có thể bản mới tạo SQL chậm, giữ transaction dài hoặc gọi DB nhiều lần hơn.

Quy trình:

1. **Dừng mở rộng canary**.
2. Xác minh traffic mix/cohort của hai version.
3. Mở distributed traces của request bị chậm để tìm span JDBC.
4. Xem active/pending connections, checkout duration, slow queries và DB locks.
5. Thu JFR hoặc thread dump nếu cần kiểm tra nơi tasks đang chờ.
6. Nếu lỗi gắn với release mới và vượt gate, **chuyển traffic về stable** theo runbook.
7. Kiểm thử SQL/transaction fix trên staging rồi rollout lại với gate rõ ràng.

**Không kết luận “JVM Java 27 có memory leak”** chỉ dựa vào số requests treo hoặc một số đo heap nhất thời.

## 15. Theo dõi và rollback Deployment trong Kubernetes

Khi có quyền vận hành và đúng namespace, quan sát:

```text
kubectl -n production get deployment orders
kubectl -n production describe deployment orders
kubectl -n production rollout status deployment/orders
kubectl -n production rollout history deployment/orders
```

Nếu cần chọn một revision được xác nhận ổn định:

```text
kubectl -n production rollout undo deployment/orders --to-revision=<known-good-revision>
kubectl -n production rollout status deployment/orders --timeout=180s
```

`<known-good-revision>` là placeholder phải thay bằng revision có trong history và đã xác minh. Đây là **runbook mẫu, không phải lệnh đã thực thi trên hệ thống nào**.

### 15.1. Phạm vi thực tế của `rollout undo`

Kubernetes Deployment revision lưu thay đổi ở **Pod template**. Quay lại một revision không tự:

- Khôi phục SQL schema hoặc dữ liệu đã ghi.
- Đưa ConfigMap/Secret đã sửa độc lập về nội dung cũ.
- Hoàn tác message đã publish/consume.
- Hoàn tác email hay thanh toán đã gửi.
- Khôi phục file/object storage bị ghi đè.
- Thay đổi gateway routing độc lập với Deployment.
- Bảo đảm custom runtime image cũ còn nằm trong registry.

`kubectl rollout undo` báo thành công chỉ là **một bước** của khôi phục service; vẫn phải đo traffic, errors, latency, dữ liệu và background workers.

### 15.2. `revisionHistoryLimit` và artifact retention

Nếu Kubernetes đã xóa ReplicaSet cũ do giới hạn lịch sử, có thể không còn revision cần dùng cho `undo`. Phải giữ **artifact digest** và metadata ổn định tại registry theo retention policy, giúp triển khai lại image cũ đã kiểm tra dù lịch sử Deployment không còn.

Nếu quay lại tag mà tag đã bị ghi đè, có thể nhận một artifact khác. Đây là lý do phải pin version bằng digest.

### 15.3. Với canary hoặc blue-green, hoàn nguyên ở đúng tầng

Nếu traffic được phân bằng gateway hoặc service mesh, hành động khôi phục chính có thể là **đặt weight canary về 0%** hoặc đổi route lại blue pool. Chỉ rollback image mà không chỉnh traffic routing có thể không đủ.

Sau khi chuyển:
- Stable có đủ capacity tiếp nhận traffic không?
- Các request đang chạy còn được phục vụ hoặc hủy đúng contract không?
- Worker/job bản lỗi có còn thực hiện side effect không?
- Các route/region/tenant đã chuyển về stable đúng chưa?

## 16. Rollback ứng dụng không đồng nghĩa rollback dữ liệu

Một release thay code, configuration, database schema, message format và external effects. Các thành phần này có vòng đời độc lập:

```text
Application A  -> Schema S1
      |
      +--> Deploy B + Schema S2
                  |
                  v
          B ghi dữ liệu mới
                  |
            B phát sinh lỗi
                  |
             Rollback code về A
                  |
                  v
       A đọc S2 và dữ liệu B được không?
```

Nếu câu trả lời cuối là **không**, rollback JAR/image về A có thể gây lỗi nghiêm trọng hơn.

Trước release cần có **ma trận tương thích**:

| Thành phần | A + trạng thái cũ | A + trạng thái mới | B + trạng thái cũ | B + trạng thái mới |
| --- | --- | --- | --- | --- |
| DB schema | Phải biết | Phải kiểm thử | Phải kiểm thử | Phải biết |
| Message payload | Phải biết | Phải kiểm thử | Phải kiểm thử | Phải biết |
| Cache content | Phải biết | Phải kiểm thử | Phải kiểm thử | Phải biết |
| Config/secret | Phải biết | Phải kiểm thử | Phải kiểm thử | Phải biết |

Không phải ô nào cũng cần được hỗ trợ vĩnh viễn, nhưng **khoảng thời gian rollout và rollback** phải được định nghĩa rõ.

## 17. Database migration theo expand–migrate–contract

Giả sử bản A sử dụng cột `display_name`, bản B muốn đổi sang `full_name`.

Nếu migration xóa `display_name` ngay, bản A có thể không chạy được trong lúc rolling hoặc rollback.

Một cách an toàn hơn:

```text
A đọc/ghi display_name
          |
          v
EXPAND: thêm full_name, giữ display_name
          |
          v
MIGRATE: backfill dữ liệu, định nghĩa đọc/ghi tương thích
          |
          v
B hỗ trợ giai đoạn chuyển đổi
          |
          +--> Nếu rollback: A vẫn đọc được S2
          |
          v
CONTRACT: xóa display_name khi không còn A/caller phụ thuộc
```

### 17.1. Cần tính trước chi phí backfill

Thay đổi schema có thể ảnh hưởng:
- Duration của migration và database locks.
- Index creation, disk I/O, replication lag.
- Dữ liệu được cập nhật đồng thời với backfill.
- Transaction size, deadlocks và consistency.
- Cách khôi phục khi migration hoàn thành một phần.

Không mặc định mọi migration **có thể down** bằng lệnh SQL đảo ngược. Sau khi drop dữ liệu, `ADD COLUMN` không tự khôi phục nội dung cũ. Backup/restore cũng có RPO/RTO và có thể làm mất những cập nhật hợp lệ sau thời điểm backup.

### 17.2. Thời điểm bỏ cột cũ phải được kiểm soát

Chỉ contract cleanup khi:
1. Tất cả ứng dụng và consumer còn cần quay lại đã được xác định.
2. Không còn version cũ đang chạy.
3. Cửa sổ rollback đã kết thúc hoặc phương án tương thích khác đã sẵn sàng.
4. Dữ liệu mới được đối soát.
5. Migration được thử trên dữ liệu tương đương và có rollback/restore plan phù hợp.

**Không dùng một lần deploy “thành công” làm điều kiện duy nhất để xóa cột cũ.**

## 18. Message, background worker và side effects

Với queue/Kafka/batch, HTTP health và Deployment readiness không đủ để chứng minh nghiệp vụ đúng.

Những metric cần theo dõi:

| Workload | SLI/metric sau phát hành |
| --- | --- |
| Kafka/queue consumer | Lag, queue age, retries, DLQ, processing duration |
| Job scheduler | Job success, schedule delay, duplicate executions |
| File processor | File checksum, xử lý trùng, output integrity |
| Thanh toán | Settlement, idempotency conflicts, sự kiện bù trừ |
| Streaming worker | Checkpoint, state compatibility, backpressure |

### 18.1. Rủi ro khi rollback consumer

Ví dụ B đã publish một message schema mới; A sau rollback nhận message đó nhưng không parse được. Hoặc B đã ghi database rồi crash trước khi ack; A xử lý lại và phát sinh side effect lần hai.

Cần quy định rõ:
- Forward/backward compatibility của message.
- Schema version và cách xử lý unknown fields.
- Idempotency keys, deduplication.
- Ack/nack, checkpoint, retry và poison-message policy.
- Có thể pause consumer của B mà không làm queue mất dữ liệu không?
- A có đọc state/checkpoint của B được không?

**Rollback worker không tự hoàn tác giao dịch đã được worker thực thi.** Có thể phải đối soát hoặc thực hiện nghiệp vụ bù trừ (*compensating action*).

### 18.2. Virtual threads không giải quyết thiếu tài nguyên downstream

Trong Java 27, virtual threads hữu ích với nhiều tác vụ chờ I/O, nhưng không biến database thành nguồn connection vô hạn. Khi số virtual thread tăng mà DB pool chỉ có vài chục connection, tasks có thể cùng chờ pool.

Đo **số tác vụ chờ, DB pool pending, timeout và queue age**. Không tự giới hạn số virtual thread bằng một pool nhỏ để thay thế giới hạn tài nguyên thực; dùng connection pool, semaphore hoặc rate limiting phù hợp.

## 19. Khi nào chọn rollback, roll-forward hay tắt feature?

| Tình huống | Hành động thường đáng cân nhắc |
| --- | --- |
| Tính năng mới lỗi, có feature flag an toàn | Tắt feature trước để giảm ảnh hưởng |
| Code B lỗi, A vẫn tương thích data/config | Rollback traffic/image về A |
| Schema B phá tương thích với A | Roll-forward/hotfix hoặc phương án dữ liệu đã duyệt |
| B đã thực hiện side effect sai | Kill switch + đối soát/compensation; không chỉ rollback |
| Secret/key đã rotate | Xác minh A có dùng credential hiện tại được không |
| A chứa lỗ hổng bảo mật nghiêm trọng đã thu hồi | Không tự rollback về A; tìm hướng sửa an toàn |
| Registry không còn artifact cũ | Dùng bản đã lưu/khôi phục qua pipeline được phép |
| DB/downstream đang sự cố độc lập | Không đổ lỗi cho B nếu chưa có bằng chứng |

Đây là gợi ý suy luận, không phải phép quyết định hoàn toàn tự động. Quyền phê duyệt và mức ảnh hưởng quyết định quy trình thực tế.

### 19.1. Không giải quyết incident bằng việc đổi nhiều biến cùng lúc

Nếu một release đồng thời thay Java runtime, database schema, container resources và code nghiệp vụ, rất khó tách nguyên nhân. Khi có thể, hãy phân giai đoạn những thay đổi có rủi ro, giữ provenance rõ ràng và sử dụng feature flags/canary để giảm blast radius.

## 20. Alerting và trách nhiệm on-call

Một release cần có người hoặc hệ thống chịu trách nhiệm rõ:
- Ai có quyền **pause rollout** và chuyển traffic?
- Ai quyết định rollback so với roll-forward?
- Ai kiểm tra DB migration và message compatibility?
- Ai xử lý side effects có thể gây mất tiền/dữ liệu?
- Ai xác nhận khi soak window đã hoàn tất?

Ví dụ mẫu alert (số liệu minh họa):

```text
[ALERT] orders release=2.4.0 canary
Window: 10 minutes
Impact: errors and p99 above approved release gates
Canary 5xx: 3.5% ; Stable 5xx: 0.2%
Additional: DB pool pending increased
Action: pause promotion; validate safe traffic rollback
Owner: release on-call
```

Đừng alert liên tục cho mỗi request `500` đơn lẻ. Cần ngưỡng phù hợp với lưu lượng, các cửa sổ đo khác nhau và mức nghiêm trọng. Tuy nhiên lỗi **mất dữ liệu, lộ thông tin hay giao dịch tài chính sai** có thể yêu cầu cảnh báo ngay, không chờ đủ mẫu.

### 20.1. Bảo mật dữ liệu chẩn đoán

Logs, traces, JFR và heap dumps có thể chứa thông tin nhạy cảm. Đặt access controls, retention, che dữ liệu bí mật, tránh đăng raw dump lên hệ thống công khai hoặc chia sẻ ngoài phạm vi được phép.

## 21. Runbook triển khai an toàn

### 21.1. Trước khi mở traffic

1. Khóa artifact: version, digest, build commit, exact JDK/runtime.
2. Xác minh test, scan, provenance và SBOM theo policy.
3. Có baseline SLO, dashboards, alerts, traces/JVM telemetry sẵn sàng.
4. Đánh giá migration/schema/message compatibility giữa A/B.
5. Chuẩn bị rollback artifact và xác định revision/config ổn định.
6. Định nghĩa release owner, approver, on-call và escalation path.
7. Xác nhận surge capacity, DB pool/queue limits, downstream budgets.
8. Chạy smoke/contract tests trong môi trường phù hợp.
9. Kiểm tra readiness/startup/liveness và grace period.
10. Chuẩn bị kill switch/feature flag cho tính năng nguy hiểm nếu có.

### 21.2. Trong mỗi giai đoạn rollout

1. Đưa B vào phục vụ một nhóm nhỏ theo plan.
2. Xác minh artifact **đang chạy thật** là đúng digest/version.
3. Chờ startup/readiness thành công và ổn định.
4. Chạy smoke kiểm tra các đường nghiệp vụ trọng yếu.
5. So sánh SLI của B với A theo cohort/route; xem errors, p95/p99, saturation.
6. Kiểm tra JVM heap/GC/CPU và DB/queue/downstream.
7. Đảm bảo có đủ traffic mẫu hoặc synthetic evidence.
8. Nếu PASS, tăng B; nếu FAIL, pause và xét khôi phục.
9. Ghi thời điểm từng bước để correlation với logs/traces.

### 21.3. Khi đạt 100%

1. Giữ **soak period** đủ để đi qua các chu kỳ tải/batch quan trọng.
2. Xác nhận không còn instance/worker bản lỗi hoạt động không chủ ý.
3. Kiểm tra queue backlog, message retries, dữ liệu và downstream.
4. Ghi lại evidence, thay đổi metric và các sự cố phát sinh.
5. Chỉ dọn schema/flags/artifacts cũ khi hết **cửa sổ rollback** và đạt compatibility conditions.

## 22. Runbook khôi phục phiên bản khi phát hiện lỗi

### 22.1. Bước A — Giới hạn tác động

1. Dừng promotion ngay.
2. Đưa canary traffic về mức an toàn hoặc tắt feature flag theo quyền.
3. Dừng/pause những background jobs có thể gây side effect sai.
4. Ghi release ID, digest, config/schema versions và thời điểm xuất hiện lỗi.
5. Lưu metrics/traces/logs liên quan mà không làm lộ dữ liệu.

### 22.2. Bước B — Xác minh có thể rollback

1. Old artifact có được lưu và xác minh không?
2. Old app có đọc được **schema/data hiện tại** không?
3. Có message do bản mới phát mà bản cũ không xử lý được không?
4. Có giao dịch hoặc dữ liệu cần compensation không?
5. Stable pool có đủ capacity khi traffic trở lại không?
6. Việc rollback có vi phạm security policy hoặc làm sống lại lỗ hổng không?
7. Ai cần phê duyệt và phối hợp?

Nếu rollback code phá tương thích hoặc làm mất dữ liệu, cần theo **phương án roll-forward/mitigation** đã kiểm tra thay vì mù quáng đổi image.

### 22.3. Bước C — Hoàn nguyên đúng thành phần

- Canary/blue-green: chuyển route/traffic về tập stable.
- Rolling Deployment: đưa Pod template về digest/revision known good.
- Feature flag: tắt behavior gây lỗi và giám sát hiệu lực.
- Worker: pause/resume consumer, cân nhắc checkpoint/replay.
- Schema/data: theo backup/restore hoặc compensating action đã duyệt.
- Config/secrets: khôi phục revision riêng nếu cần và còn an toàn.

### 22.4. Bước D — Xác nhận hệ thống hồi phục

1. Routing và artifact thực tế đã đúng stable version chưa?
2. Số instance available và readiness đạt yêu cầu chưa?
3. Error rate, latency, queue age, pool pending trở lại baseline chưa?
4. Không còn bản lỗi chạy scheduled job/consumer ngoài ý muốn?
5. Side effects/dữ liệu cần đối soát đã được xử lý?
6. Có theo dõi đủ lâu sau rollback?
7. Incident review đã lập danh sách regression test và hành động ngăn tái diễn?

**Lệnh rollback báo thành công chưa phải là kết thúc sự cố.** Trạng thái người dùng, dữ liệu và downstream mới quyết định khi nào đóng incident.

## 23. Diễn tập rollback trước khi cần khẩn cấp

Một kế hoạch đáng tin là kế hoạch đã được **thử trong môi trường được phép**.

Các tình huống nên diễn tập:

- Canary 5% bị lỗi rồi traffic B trở về 0%.
- Đang rolling update thì instance mới không đạt readiness.
- DB đã chạy expand migration nhưng code quay về bản A.
- Message schema v2 được publish rồi consumer v1 nhận lại.
- Worker ghi một giao dịch nhưng chưa ack message và bị restart.
- Secret/configuration mới không tương thích với bản cũ.
- Shutdown có request dài, tới hạn grace period.
- Artifact stable không còn trong cache node và phải kéo từ registry.
- Một downstream service lỗi ngay giữa rollout.
- Người phê duyệt chính vắng mặt, runbook vẫn vận hành được.

Mỗi cuộc diễn tập cần **pass/fail criteria**, bằng chứng về thời gian khôi phục và các dữ liệu có thể bị ảnh hưởng. Với hệ thống quan trọng, diễn tập backup/restore và đối soát dữ liệu riêng, không chỉ lệnh `rollout undo`.

## 24. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Deployment báo Ready = release thành công | Probe không kiểm mọi nghiệp vụ | SLI/metrics, smoke và contract tests |
| Chỉ xem tổng HTTP error của service | Canary nhỏ dễ bị che khuất | So sánh theo version/cohort |
| Không cần baseline | Không phân biệt sự cố mới/cũ | Thu số liệu trước deploy |
| Có tag `latest` là đủ rollback | Tag có thể đổi nội dung | Giữ image digest |
| `kubectl rollout undo` tự rollback DB | Deployment chỉ quản lý Pod template revision | Schema compatibility/backup plan |
| Rename/drop cột ngay trong release | Old app có thể không đọc được | Expand–migrate–contract |
| Readiness luôn trả 200 | Pod nhận traffic khi chưa sẵn sàng | Readiness theo trạng thái phục vụ |
| Liveness gọi mọi dependency | Sự cố downstream gây restart hàng loạt | Liveness nhẹ, degraded mode |
| `progressDeadlineSeconds` tự rollback | Chỉ báo tình trạng tiến triển | Controller/human có chính sách xử lý |
| Rolling update là canary weighted | Không tự điều khiển tỷ lệ request chuẩn | Gateway/service mesh/cohorts |
| Virtual threads cho phép vô hạn DB calls | Pool/downstream vẫn hữu hạn | Resource limits, timeouts |
| `-Xmx` là toàn bộ RAM JVM | Native memory nằm ngoài heap | RSS, NMT, direct buffer, stacks |
| Thấy heap tăng = memory leak | Có thể là warm-up/cache | Live set sau GC, retention |
| Rollback không cần tính tương thích schema | A có thể không đọc được data của B | Compatibility matrix |
| Tăng mọi timeout để tránh rollback | Có thể che tắc nghẽn | Tìm root cause, deadline phù hợp |
| PreStop ngủ rất lâu là drain an toàn | Ăn hết thời gian grace | Lifecycle/draining có kiểm chứng |
| Một số ít request đủ qua mọi gate | Dữ liệu thống kê chưa đáng tin | Min samples, soak, synthetic tests |
| Chỉ rollback HTTP Pods | Workers/jobs còn gây side effect | Kiểm soát toàn bộ consumers |
| Cứ rollback về bản cũ bất chấp bảo mật | Có thể tái tạo lỗ hổng nghiêm trọng | Approved known-good versions |

## 25. Checklist release và khôi phục cho Java 27

Trước khi xác nhận release đã ổn định:

1. [ ] Artifact có version, git commit, digest và exact Java runtime?
2. [ ] Đã xác minh đúng artifact được triển khai thực tế?
3. [ ] Có baseline SLO/SLI, dashboard và alert từ trước rollout?
4. [ ] Có errors, latency, traffic, saturation theo version/cohort?
5. [ ] Có metric nghiệp vụ phát hiện ghi trùng, sai dữ liệu, backlog?
6. [ ] Startup, readiness và liveness phản ánh đúng contract?
7. [ ] Có giám sát heap sau GC, GC pause, RSS, CPU và pool/queue?
8. [ ] JFR/`jcmd` có thể dùng khi cần với quyền/retention an toàn?
9. [ ] Chiến lược rolling/canary/blue-green phù hợp trạng thái dữ liệu?
10. [ ] Mỗi giai đoạn rollout có gate và owner xác định?
11. [ ] Phiên bản A/B tương thích schema/message/cache trong cửa sổ chuyển đổi?
12. [ ] Database migration có kế hoạch expand–migrate–contract hoặc tương đương?
13. [ ] Side effects quan trọng có idempotency/deduplication hoặc compensation?
14. [ ] Graceful shutdown và connection draining đã được thử?
15. [ ] Có kill switch/feature flag khi thích hợp?
16. [ ] Artifact/revision known-good còn được lưu, không dựa vào `latest`?
17. [ ] Có hướng dẫn rollback từng tầng: traffic, code, config, data, workers?
18. [ ] Đã diễn tập ít nhất một tình huống khôi phục và đo thời gian?
19. [ ] Không rollback về artifact bị thu hồi vì security vulnerability?
20. [ ] Sau đạt 100%, metrics vẫn ổn qua soak window?
21. [ ] Biên bản release và hành động follow-up được lưu theo quy trình?

**Kết luận:** phát hành một ứng dụng Java 27 không kết thúc ở `java -jar` hay khi Deployment báo Available. Một release chỉ thực sự đạt khi **người dùng tiếp tục được phục vụ đúng**, hệ thống được quan sát bằng bằng chứng tin cậy, và đội vận hành có thể **ngừng mở rộng lỗi, quay lại trạng thái tương thích hoặc sửa tiếp** mà không phá dữ liệu hay tác vụ đang thực hiện.

## Tài liệu tham khảo

- [Oracle Java SE 27 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html): JFR, `jcmd`, thread/GC/heap diagnostics.
- [Oracle Java SE 27 — Virtual Threads](https://docs.oracle.com/en/java/javase/27/core/virtual-threads.html): quan sát virtual threads và scheduler.
- [Oracle Java SE 27 — `jcmd`](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html): diagnostic commands và JFR.
- [Oracle Java SE 27 — `java` Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): Unified Logging và JVM flags.
- [Oracle Java SE 27 — `jlink`](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jlink.html): tạo custom runtime image.
- [Oracle Java SE 27 — `jpackage`](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jpackage.html): đóng gói application.
- [Java SE 27 API — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/27/docs/api/java.management/java/lang/management/MemoryMXBean.html): quản lý heap/non-heap memory.
- [OpenTelemetry — Java](https://opentelemetry.io/docs/languages/java/): metrics, traces, logs và resource attributes.
- [OpenTelemetry — Java Instrumentation](https://opentelemetry.io/docs/languages/java/instrumentation/): Java agent, context propagation và JMX.
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): rolling update, revision history và tiến độ rollout.
- [Kubernetes — Update a Deployment Without Downtime](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/): rollout status, pause/resume và undo.
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/): vai trò của các probes.
- [Kubernetes — Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/): SIGTERM, grace period, preStop và draining.
- [Kubernetes — `kubectl rollout undo`](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/kubectl_rollout_undo/): lệnh rollback revision.
