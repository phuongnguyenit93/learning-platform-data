# Health check cho orchestrator

## 1. Mục tiêu

Khi triển khai Spring gRPC trên Kubernetes hoặc một orchestrator khác, hệ thống cần biết lúc nào process đã khởi động, lúc nào instance có thể nhận traffic và khi nào process không còn hoạt động bình thường. Một TCP port mở chưa trả lời được các câu hỏi đó. Với gRPC, tín hiệu phù hợp là health service theo chuẩn gRPC Health Checking protocol, được nối với lifecycle và readiness state của ứng dụng.

**Health check cho orchestrator** là cách để nền tảng triển khai chủ động kiểm tra trạng thái service và thực hiện hành động phù hợp. Kubernetes hỗ trợ startup, liveness và readiness probe; với gRPC, native gRPC probe gọi method Health/Check của service chuẩn grpc.health.v1.

Sau bài học, bạn có thể:

- Phân biệt startup, liveness và readiness probe.
- Triển khai gRPC Health Checking service cho Spring gRPC server.
- Cấu hình Kubernetes gRPC probes với service name phù hợp.
- Đồng bộ health status với startup, dependency readiness và shutdown.
- Chọn native gRPC probe hay exec probe khi cần TLS/auth.
- Điều chỉnh timeout, period và failure threshold để tránh restart storm.
- Kiểm thử probe từ góc nhìn orchestrator.

## 2. Ba loại probe có ba nhiệm vụ khác nhau

Kubernetes dùng ba loại probe để điều khiển vòng đời container:

| Probe | Câu hỏi | Khi probe thất bại |
|---|---|---|
| Startup | Ứng dụng đã hoàn tất giai đoạn khởi động chưa? | Container bị restart sau khi vượt failure threshold |
| Liveness | Process còn sống và có khả năng tiếp tục chạy không? | Kubelet restart container |
| Readiness | Instance đã đủ điều kiện nhận traffic chưa? | Pod bị đánh dấu not ready và bị loại khỏi endpoint phục vụ traffic |

Startup probe bảo vệ ứng dụng khởi động chậm. Khi startup probe chưa thành công, Kubernetes chưa chạy liveness và readiness probe. Sau khi startup probe thành công, hai probe còn lại bắt đầu hoạt động theo cấu hình.

Liveness phát hiện process bị kẹt hoặc trạng thái nội bộ không thể tự phục hồi. Không đưa mọi dependency vào liveness. Nếu database tạm thời mất kết nối mà liveness cũng fail, orchestrator có thể restart hàng loạt instance, khiến database đang quá tải càng khó phục hồi.

Readiness trả lời instance có nên nhận request mới không. Nó có thể phụ thuộc database hoặc dependency bắt buộc. Khi readiness fail, Kubernetes ngừng route traffic mới tới pod; container vẫn chạy để có thể phục hồi.

## 3. gRPC Health Checking protocol

gRPC định nghĩa service chuẩn trong package `grpc.health.v1`:

- `Health/Check` là unary RPC trả trạng thái hiện tại của service.
- `Health/Watch` là server-streaming RPC gửi trạng thái hiện tại và các lần thay đổi tiếp theo.

Kubernetes native gRPC probe gọi `Health/Check`. Nó không dùng `Watch`.

Request chứa tên service cần kiểm tra. Quy ước:

- Service name rỗng `""` biểu diễn trạng thái tổng thể của server.
- Service name cụ thể, ví dụ `catalog.v1.CatalogService`, biểu diễn một gRPC service.

Tên service phải khớp Protobuf package và service name, không nhất thiết khớp Java package. Nếu Kubernetes hỏi một service name mà health server không biết, probe sẽ thất bại.

Các trạng thái chuẩn:

| Status | Ý nghĩa |
|---|---|
| `UNKNOWN` | Chưa xác định trạng thái |
| `SERVING` | Service sẵn sàng phục vụ |
| `NOT_SERVING` | Service chưa sẵn sàng hoặc đang dừng |
| `SERVICE_UNKNOWN` | Service name không được quản lý; thường xuất hiện trong Watch |

Với `Check`, service không được đăng ký thường trả gRPC status `NOT_FOUND`. Orchestrator chỉ nên xem probe thành công khi nhận được health response hợp lệ với status `SERVING`.

## 4. Cung cấp health service trong Spring gRPC

gRPC Java cung cấp `HealthStatusManager` trong artifact `grpc-services`. Manager giữ trạng thái cho từng service name và cung cấp implementation health service chuẩn.

Dependency cần dùng cùng release line với các artifact gRPC Java còn lại:

```kotlin
dependencies {
    implementation("io.grpc:grpc-services:<grpc-version>")
}
```

Ví dụ tạo bean:

```java
@Configuration
public class GrpcHealthConfiguration {

    @Bean
    HealthStatusManager healthStatusManager() {
        return new HealthStatusManager();
    }

    @Bean
    BindableService grpcHealthService(
            HealthStatusManager manager) {
        return manager.getHealthService();
    }
}
```

Bean `BindableService` chỉ tự được đăng ký nếu Spring gRPC starter/version đang dùng hỗ trợ discovery loại bean đó. Nếu starter dùng server factory, service registry hoặc customizer riêng, hãy đăng ký `manager.getHealthService()` qua đúng cơ chế của starter. Phải xác minh health service được bind vào cùng gRPC listener mà Kubernetes probe gọi.

Với server dựng thủ công, đăng ký trực tiếp:

```java
Server server = ServerBuilder.forPort(9090)
        .addService(catalogService)
        .addService(manager.getHealthService())
        .build()
        .start();
```

Không chỉ tạo HealthStatusManager mà quên đăng ký health service. Khi đó port vẫn mở nhưng Kubernetes probe gọi `grpc.health.v1.Health/Check` sẽ nhận `UNIMPLEMENTED`.

## 5. Quản lý service name riêng cho từng probe

Có thể dùng service name khác nhau để biểu diễn readiness và liveness:

- `liveness`: process và gRPC server còn có thể phản hồi health call.
- `readiness`: instance đã sẵn sàng nhận traffic nghiệp vụ.
- `catalog.v1.CatalogService`: trạng thái phục vụ của Catalog service.
- `""`: trạng thái tổng thể nếu ứng dụng có định nghĩa rõ.

Khi dùng service name riêng, phải cập nhật tất cả status tương ứng trong HealthStatusManager. Kubernetes probe gửi đúng chuỗi cấu hình trong trường `service`; sai khác chữ hoa/thường hoặc package đều có thể làm probe thất bại.

Ví dụ coordinator:

```java
public final class GrpcProbeStatus {

    private static final String LIVENESS = "liveness";
    private static final String READINESS = "readiness";
    private static final String CATALOG =
            "catalog.v1.CatalogService";

    private final HealthStatusManager manager;

    public GrpcProbeStatus(HealthStatusManager manager) {
        this.manager = manager;
    }

    public void starting() {
        setAll(ServingStatus.NOT_SERVING);
    }

    public void processAlive() {
        manager.setStatus(LIVENESS, ServingStatus.SERVING);
    }

    public void ready() {
        manager.setStatus(READINESS, ServingStatus.SERVING);
        manager.setStatus(CATALOG, ServingStatus.SERVING);
    }

    public void notReady() {
        manager.setStatus(READINESS, ServingStatus.NOT_SERVING);
        manager.setStatus(CATALOG, ServingStatus.NOT_SERVING);
    }

    public void stopping() {
        setAll(ServingStatus.NOT_SERVING);
    }

    private void setAll(ServingStatus status) {
        manager.setStatus(LIVENESS, status);
        manager.setStatus(READINESS, status);
        manager.setStatus(CATALOG, status);
        manager.setStatus("", status);
    }
}
```

Ví dụ trên minh họa các status cần công bố. Trong implementation thực tế, không nên đặt liveness thành NOT_SERVING chỉ vì database chưa sẵn sàng; hãy tách transition liveness khỏi readiness theo đúng ý nghĩa của hai probe. Khi startup hoàn tất, liveness có thể SERVING dù readiness vẫn NOT_SERVING vì dependency bắt buộc chưa kết nối được.

## 6. Đồng bộ status với Spring lifecycle

Một trình tự triển khai thường dùng:

1. Tạo HealthStatusManager với các service status ban đầu là NOT_SERVING.
2. Khởi tạo Spring bean, cấu hình server và service implementation.
3. Chờ các dependency bắt buộc hoàn tất readiness check có timeout.
4. Khi process có thể vận hành, đặt liveness thành SERVING.
5. Khi đủ điều kiện nhận traffic, đặt readiness và service status thành SERVING.
6. Khi bắt đầu graceful shutdown, đặt readiness và service status thành NOT_SERVING trước khi ngừng nhận traffic.
7. Drain RPC đang chạy rồi mới dừng server.

Có thể dùng ApplicationReadyEvent nếu readiness gate đã hoàn tất tại thời điểm event được phát. Nếu dependency readiness tiếp tục thay đổi sau startup, dùng một coordinator theo dõi dependency và cập nhật status khi trạng thái đổi. Với shutdown, dùng SmartLifecycle hoặc hook đóng context phù hợp thứ tự của starter.

Không đặt readiness SERVING ngay khi port bind thành công. Listener có thể mở trước khi database, cache hoặc service handler sẵn sàng.

## 7. Cấu hình Kubernetes native gRPC probes

Kubernetes hỗ trợ gRPC probe trực tiếp trong Pod spec. Ví dụ:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-grpc
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-grpc
  template:
    metadata:
      labels:
        app: catalog-grpc
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: catalog
          image: example/catalog-grpc:1.0.0
          ports:
            - name: grpc
              containerPort: 9090
              protocol: TCP
          startupProbe:
            grpc:
              port: 9090
              service: liveness
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            grpc:
              port: 9090
              service: liveness
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            grpc:
              port: 9090
              service: readiness
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 1
```

Trong ví dụ, startup và liveness hỏi service name `liveness`; readiness hỏi `readiness`. Application phải công bố đúng hai status đó. Startup probe có thể cho ứng dụng thời gian khởi động tối đa khoảng 150 giây theo cấu hình period/failure threshold ở trên; thời gian thực tế còn phụ thuộc timeout và lịch probe.

Native gRPC probes ổn định từ Kubernetes 1.27. Nếu cluster cũ hơn, kiểm tra version và feature gate trước khi dùng; có thể cần exec probe hoặc phương thức kiểm tra khác.

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| `port` | Port số của gRPC listener trong Pod |
| `service` | Service name gửi trong HealthCheckRequest; có thể bỏ trống để hỏi overall status |
| `periodSeconds` | Chu kỳ probe |
| `timeoutSeconds` | Thời gian tối đa chờ probe |
| `failureThreshold` | Số lần thất bại liên tiếp trước khi coi probe fail |
| `successThreshold` | Số lần thành công liên tiếp để phục hồi; liveness/startup phải là 1 |
| `initialDelaySeconds` | Thời gian chờ trước probe đầu tiên, nếu cần |

## 8. Giới hạn của native gRPC probe

Native gRPC probe có một số giới hạn cần tính đến:

- Chỉ dùng port dạng số, không dùng named port.
- Không cấu hình TLS certificate, client certificate hoặc authentication metadata.
- Không cấu hình hostname tùy ý như HTTP probe; probe nhắm tới Pod IP.
- Không cung cấp header hoặc token tùy chỉnh.
- Chỉ gọi Health/Check; không thực hiện Health/Watch.

Vì vậy, native probe phù hợp khi health service có thể được gọi qua gRPC plaintext trong Pod network và không yêu cầu authentication ở probe endpoint. Nếu application chỉ mở TLS/mTLS hoặc yêu cầu token cho mọi RPC, native probe không có trường cấu hình để cung cấp các credential đó.

Không tắt TLS hoặc authentication cho toàn bộ gRPC listener chỉ để native probe hoạt động. Có thể thiết kế health listener/health access policy riêng trong trust boundary của Pod, hoặc dùng exec probe với công cụ hỗ trợ TLS/auth.

## 9. Khi nào dùng exec probe?

Exec probe chạy một chương trình bên trong container. Đây là lựa chọn khi cần truyền certificate, token hoặc tham số mà native gRPC probe không hỗ trợ.

Ví dụ dùng công cụ grpc health probe:

```yaml
readinessProbe:
  exec:
    command:
      - /bin/grpc_health_probe
      - -addr=127.0.0.1:9090
      - -service=readiness
      - -connect-timeout=1s
      - -rpc-timeout=2s
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 2
```

Tên binary và flag phụ thuộc phiên bản grpc-health-probe được đóng gói trong image. Với TLS/mTLS, dùng đúng tùy chọn CA, certificate và key mà phiên bản công cụ hỗ trợ; quản lý secret an toàn và không ghi credential ra log.

Exec probe có chi phí tạo process mỗi lần chạy, vì vậy đặt period hợp lý và giữ binary nhỏ. Không dùng script kiểm tra phức tạp gọi nhiều dependency đồng bộ ở mỗi probe.

Một lựa chọn khác là HTTP readiness endpoint của Spring Boot Actuator, nhưng endpoint đó chỉ là tín hiệu HTTP riêng. Nếu dùng, cần bảo đảm readiness policy nhất quán với gRPC health status và không nhầm HTTP management port với gRPC listener.

## 10. Thiết kế liveness để tránh restart storm

Liveness nên kiểm tra process có thể tiếp tục chạy không, không kiểm tra mọi dependency từ xa. Ví dụ:

- Spring application context đã hoàn tất startup.
- Health handler có thể trả lời trong thời gian giới hạn.
- Worker/event loop thiết yếu không bị deadlock theo tiêu chí nội bộ.

Không đưa database, Kafka, Redis hoặc một gRPC downstream tùy chọn vào liveness. Nếu một dependency dùng chung bị outage, tất cả pod có thể fail liveness cùng lúc và restart liên tục.

Readiness có thể kiểm tra dependency bắt buộc. Tuy nhiên, health coordinator nên theo dõi dependency với timeout, cache kết quả và giới hạn concurrency. Không để mỗi probe tạo một query nặng hoặc một chuỗi RPC phụ thuộc.

Khi dependency chập chờn, có thể dùng failure/recovery threshold hoặc hysteresis để tránh status đổi liên tục. Nhưng không trì hoãn việc đánh dấu NOT_SERVING nếu request thực tế không còn được xử lý an toàn.

## 11. Điều chỉnh timeout và threshold

Probe quá nhạy có thể làm restart hoặc loại pod không cần thiết. Probe quá chậm có thể giữ traffic trên instance lỗi lâu hơn.

Ví dụ cách tính ngân sách startup:

```text
periodSeconds × failureThreshold
5 giây × 30 lần ≈ 150 giây
```

Đây là ước lượng khoảng thời gian probe theo chu kỳ, không phải deadline chính xác; timeout và lịch thực thi cũng ảnh hưởng.

Một số nguyên tắc:

- timeoutSeconds phải lớn hơn thời gian health handler bình thường nhưng vẫn hữu hạn.
- periodSeconds cần cân bằng tốc độ phát hiện với probe overhead.
- failureThreshold của readiness có thể thấp hơn liveness để loại instance lỗi khỏi traffic sớm.
- startup failureThreshold cần đủ cho startup chậm hợp lệ.
- liveness không nên phản ứng với một spike latency ngắn.
- readiness phục hồi sau successThreshold thành công liên tiếp.

Kubernetes native gRPC probe dùng timeoutSeconds như timeout của probe. Hãy xác minh kubelet behavior theo version đang chạy và không đặt timeout thấp hơn khả năng scheduler/runtime trong môi trường tải cao.

## 12. Shutdown và readiness propagation

Khi pod bị terminate, cần báo cho orchestrator ngừng gửi request mới trước khi process đóng listener:

1. Nhận tín hiệu shutdown.
2. Đặt readiness và service status thành NOT_SERVING.
3. Chờ EndpointSlice/load balancer cập nhật và ngừng chọn pod.
4. Gửi GOAWAY/drain connection nếu server/proxy hỗ trợ.
5. Cho RPC đang chạy hoàn tất trong grace period.
6. Hủy call còn lại khi hết thời gian.
7. Đóng server và process.

Thời gian terminationGracePeriodSeconds phải đủ cho propagation và drain nhưng không vượt chính sách rollout. preStop hook có thể hỗ trợ khoảng chờ nếu kiến trúc cần, nhưng không thay thế việc cập nhật readiness status.

Nếu status chỉ được đổi sau khi server đã dừng, probe không thể nhận NOT_SERVING và load balancer có thể tiếp tục gửi traffic tới endpoint đang rời đi.

## 13. Kiểm tra và chẩn đoán

### Gọi health RPC trực tiếp

Có thể dùng grpcurl nếu endpoint cho phép kết nối phù hợp:

```bash
grpcurl -plaintext \
  -d '{"service":"readiness"}' \
  localhost:9090 \
  grpc.health.v1.Health/Check
```

Kết quả cần có status SERVING khi pod ready. Nếu server dùng TLS, bỏ plaintext và cấu hình CA/client certificate phù hợp với endpoint.

### Kiểm tra từ trong Pod

Chạy cùng công cụ hoặc exec probe trong container/network namespace tương ứng để xác minh:

- Listener đúng port.
- Health service đã đăng ký.
- Service name khớp.
- Status transition theo startup/readiness/shutdown.
- Probe timeout đủ cho health handler.

### Kiểm tra Kubernetes events

Dùng kubectl describe pod và xem events/logs để phân biệt:

- Connection refused: listener chưa bind hoặc sai port.
- Deadline exceeded/timeout: health handler chậm, worker bận hoặc network path lỗi.
- UNIMPLEMENTED: health service chưa đăng ký.
- NOT_FOUND: service name probe không tồn tại.
- NOT_SERVING: ứng dụng chủ động báo chưa ready.
- Lỗi TLS/auth với exec probe: trust, certificate hoặc credential không đúng.

Không xử lý mọi probe failure bằng cách tăng timeout. Trước hết xác định lỗi là startup, service registration, sai service name, dependency readiness hay transport/security.

## 14. Kiểm thử

### Unit test status coordinator

Kiểm tra các transition:

- Startup: readiness NOT_SERVING.
- Process khởi động xong: liveness SERVING.
- Dependency bắt buộc ready: readiness SERVING.
- Dependency bắt buộc mất và không có fallback: readiness NOT_SERVING.
- Shutdown bắt đầu: readiness NOT_SERVING trước khi server đóng.

### In-process gRPC health test

Đăng ký manager.getHealthService() trên server được tạo bằng InProcessServerBuilder, tạo channel bằng InProcessChannelBuilder, rồi gọi Check bằng generated HealthBlockingStub với đúng service name. Xác minh response status đổi sau mỗi transition. Với Watch, kiểm tra trạng thái ban đầu và các update bằng latch có timeout.

### Kubernetes integration test

Deploy test Pod với native gRPC startup/liveness/readiness probes. Xác minh:

- Pod chưa ready không được đưa vào Service endpoints.
- Sau khi dependency ready, pod chuyển Ready.
- Khi readiness trả NOT_SERVING, pod bị loại khỏi traffic nhưng container không restart.
- Khi liveness thất bại liên tiếp, container bị restart.
- Startup probe bảo vệ thời gian khởi động dài.
- Khi terminate, readiness đổi trước khi server đóng.

Kiểm tra riêng native gRPC probe trên cluster version thực tế. Nếu server bắt buộc TLS/mTLS, xác minh native probe không phù hợp và kiểm thử exec probe hoặc health endpoint nội bộ được bảo vệ.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Port mở nhưng gRPC probe fail | Health service chưa đăng ký | Bind HealthStatusManager service vào đúng server |
| Probe trả NOT_FOUND | Service name không khớp | Dùng đúng Protobuf full service name hoặc đăng ký probe name |
| Probe trả UNIMPLEMENTED | Server không có Health/Check | Thêm gRPC health service |
| Pod restart khi database outage | Liveness phụ thuộc database | Chuyển dependency check sang readiness |
| Pod Ready trước khi dependency sẵn sàng | Status đặt SERVING quá sớm | Dùng readiness gate |
| Native probe không kết nối được TLS server | Native probe không có TLS/auth fields | Dùng exec probe hoặc thiết kế health access riêng |
| Probe fail vì named port | gRPC probe cần port số | Khai báo numeric port |
| Pod bị loại khỏi traffic nhưng bị restart | Nhầm readiness với liveness | Chỉ readiness fail khi cần ngừng traffic |
| Shutdown làm rơi RPC | Không báo NOT_SERVING và drain sớm | Cập nhật status, propagation và grace period |
| Probe tạo tải lớn | Mỗi lần probe gọi chuỗi dependency nặng | Cache state, timeout và giới hạn concurrency |

## 16. Bài tập thực hành

**Tình huống:** Catalog Spring gRPC chạy trên Kubernetes. Ứng dụng mất khoảng 90 giây để khởi động và cần PostgreSQL trước khi xử lý GetProduct. Hiện Deployment chỉ có TCP liveness probe, nên pod đôi khi nhận traffic trước khi database sẵn sàng.

Hãy thực hiện:

1. Đăng ký grpc.health.v1.Health service bằng HealthStatusManager trên gRPC server.
2. Khởi tạo liveness và readiness service name ở NOT_SERVING.
3. Cấu hình startupProbe để cho phép tối đa khoảng 120–150 giây startup.
4. Cấu hình livenessProbe chỉ phản ánh process/health handler còn hoạt động.
5. Cấu hình readinessProbe phản ánh PostgreSQL readiness và Catalog service readiness.
6. Chỉ đặt readiness SERVING sau khi database check thành công.
7. Đặt readiness NOT_SERVING ngay khi shutdown bắt đầu.
8. Kiểm thử native gRPC probe trên Kubernetes version triển khai; nếu TLS/mTLS bắt buộc, chọn exec probe có credential an toàn.
9. Mô phỏng database outage và xác minh pod bị loại khỏi traffic nhưng không restart hàng loạt.
10. Mô phỏng health handler treo và xác minh liveness restart theo failure threshold.

**Tiêu chí hoàn thành:** startup, liveness và readiness có ý nghĩa riêng; health service được đăng ký và dùng đúng service name; probe timeout/threshold hợp lý; dependency outage không gây restart storm; shutdown cập nhật readiness trước khi đóng listener; test chứng minh hành vi từ góc nhìn Kubernetes.

## 17. Ghi nhớ

Orchestrator cần health signal phản ánh khả năng phục vụ, không chỉ TCP port. Kubernetes startup probe bảo vệ startup chậm, liveness phát hiện process không thể tiếp tục và readiness điều khiển traffic. Native gRPC probe gọi grpc.health.v1 Health/Check; application phải đăng ký health service và công bố đúng service name/status qua HealthStatusManager. Đặt readiness NOT_SERVING trong startup và shutdown, chỉ chuyển SERVING sau readiness gate. Không đưa dependency outage vào liveness vì có thể tạo restart storm. Native gRPC probe dùng port số và không hỗ trợ TLS/auth metadata; nếu server bắt buộc TLS/mTLS, cân nhắc exec probe với công cụ và credential phù hợp. Điều chỉnh timeout, period, failure threshold và termination grace theo workload. Kiểm thử cả status transition, probe behavior và endpoint routing trên Kubernetes thực tế.
