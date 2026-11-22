# Rolling update, autoscaling và định danh riêng của từng Pod

Khi triển khai ứng dụng Java dùng CRaC trên Kubernetes, checkpoint có thể giúp một Pod mới phục hồi trạng thái JVM đã chuẩn bị trước và đạt thời gian sẵn sàng ngắn hơn. Tuy nhiên, một checkpoint được tạo từ Pod cũ không mang theo danh tính hợp lệ của Pod mới. Pod mới có UID, IP, hostname, node, token và vòng đời riêng; nó cũng phải tham gia đúng quy trình rolling update, readiness, drain và autoscaling của Kubernetes.

Điểm cần thiết kế rõ là **trạng thái ứng dụng có thể được tái sử dụng, còn danh tính và tài nguyên gắn với một Pod phải được làm mới**. Nếu checkpoint chứa Pod UID, địa chỉ IP, lease, subscription hoặc kết nối của replica cũ, nhiều Pod được tạo từ cùng checkpoint có thể khởi động với trạng thái trùng lặp hoặc đã lỗi thời.

Bài này trình bày cách kết hợp checkpoint/restore với Deployment rolling update, Horizontal Pod Autoscaler (HPA), readiness probe và định danh riêng của từng Pod. Mục tiêu là để mỗi replica mới có thể restore nhanh, làm mới tài nguyên theo môi trường hiện tại và chỉ nhận traffic sau khi đã sẵn sàng.

## 1. Phân biệt container image và CRaC checkpoint image

Trong môi trường Kubernetes, từ *image* thường chỉ OCI/container image được lưu trong registry. Trong CRaC, *checkpoint image* là dữ liệu trạng thái tiến trình được runtime tạo để phục hồi JVM. Hai loại artifact có vai trò khác nhau:

| Artifact | Nội dung | Vòng đời |
|---|---|---|
| OCI image | JRE/JDK, ứng dụng, thư viện, cấu hình mặc định và entrypoint | Được kéo từ registry và tạo container |
| CRaC checkpoint | Trạng thái tiến trình đã chạy, heap và trạng thái runtime cần cho restore | Được tạo, lưu, xác minh và dùng để phục hồi tiến trình |
| Pod runtime identity | UID, tên, IP, node, service account và volume mount của Pod hiện tại | Được Kubernetes cấp cho từng Pod |

Một OCI image có thể chứa checkpoint đã chuẩn bị sẵn, hoặc container có thể đọc checkpoint từ volume/object storage lúc khởi động. Dù chọn cách nào, checkpoint vẫn là trạng thái của một tiến trình cụ thể. Không nên coi nó như một bản cấu hình chung có thể mang nguyên mọi giá trị runtime sang tất cả replica.

Checkpoint cũng không tự tạo Pod hay tham gia rollout. Kubernetes vẫn tạo Pod theo Pod template của Deployment hoặc StatefulSet. Entrypoint và CRaC-enabled runtime của container phải thực hiện đúng chế độ restore; readiness chỉ đạt sau khi ứng dụng phục hồi xong các dependency cần thiết.

## 2. Pod là một đơn vị có danh tính riêng và có vòng đời ngắn

Pod là đơn vị triển khai nhỏ nhất của Kubernetes. Pod có thể bị xóa và thay thế khi rollout, autoscaling, node failure hoặc rescheduling. Một Pod mới có thể chạy cùng container image và cùng checkpoint với Pod cũ nhưng vẫn là một thực thể khác.

Các thuộc tính nhận diện quan trọng:

| Thuộc tính | Nguồn | Đặc điểm |
|---|---|---|
| Pod UID | `metadata.uid` | Định danh duy nhất của một lần tạo Pod; Pod thay thế có UID mới |
| Pod name | `metadata.name` | Tên trong namespace; có thể được tái sử dụng sau khi Pod cũ bị xóa |
| Namespace | `metadata.namespace` | Phạm vi tên và nhiều tài nguyên Kubernetes |
| Pod IP | `status.podIP` | Địa chỉ mạng của Pod; Pod thay thế thường có IP khác |
| Hostname | `spec.hostname` hoặc tên Pod theo mặc định | Có thể thay đổi giữa các Pod |
| Node name | `spec.nodeName` | Node được scheduler chọn; Pod mới có thể chạy trên node khác |
| Service account | `spec.serviceAccountName` | Danh tính workload dùng khi truy cập Kubernetes API hoặc dịch vụ tích hợp |
| Labels/annotations | `metadata.labels`, `metadata.annotations` | Metadata điều khiển routing, rollout, policy và quan sát |

Không dùng Pod IP hoặc Pod name làm định danh bền vững cho dữ liệu nghiệp vụ. Nếu cần định danh một replica trong log hoặc telemetry, Pod UID là lựa chọn tốt hơn Pod name vì UID không bị trùng khi tên được tái sử dụng.

Đối với logic nghiệp vụ, hãy phân biệt:

- **Service identity:** tên dịch vụ ổn định như `orders-api`, dùng trong cấu hình, metrics và discovery.
- **Workload identity:** danh tính của workload hoặc service account, dùng cho xác thực và phân quyền.
- **Pod identity:** UID và metadata của một Pod cụ thể, dùng để phân biệt replica.
- **Process/run identity:** định danh cho một lần chạy JVM hoặc một lần restore, có thể tạo mới sau mỗi restore.

Không nên gộp các loại định danh này thành một UUID được lưu trong heap trước checkpoint. Khi nhiều Pod restore cùng checkpoint, giá trị UUID trong heap có thể bị nhân bản và khiến nhiều replica cùng nhận mình là một instance.

## 3. Vì sao danh tính cũ trong checkpoint gây lỗi?

Giả sử Pod `orders-api-7f8d9` tạo checkpoint khi có Pod UID `uid-A`, Pod IP `10.2.1.17` và node `worker-1`. Sau đó Deployment rolling update tạo Pod mới `orders-api-9c4ab`, có UID `uid-B`, IP `10.2.3.24` và node `worker-3`. Nếu JVM restore từ checkpoint nhưng tiếp tục dùng những giá trị đã lưu trong heap, ứng dụng có thể ghi log dưới UID cũ, đăng ký với service discovery bằng IP cũ hoặc dùng lease thuộc về Pod đã bị xóa.

Những lỗi thường gặp:

- Nhiều Pod cùng phát telemetry với một `instanceId` đã được lưu trong checkpoint.
- Client hoặc connection pool giữ socket tới endpoint cũ.
- Service discovery đăng ký địa chỉ Pod cũ hoặc không deregister địa chỉ đã hết hiệu lực.
- Lease hoặc leader-election state cũ khiến nhiều replica nghĩ mình vẫn là leader.
- Consumer giữ subscription, consumer ID hoặc session gắn với replica cũ.
- Token, certificate hoặc credential đã hết hạn hoặc được cấp cho workload identity khác.
- Cache giữ cấu hình, DNS result hoặc dữ liệu chỉ đúng với môi trường cũ.

Quy tắc thiết kế là: dữ liệu thuần Java có thể tái sử dụng nếu vẫn hợp lệ; trạng thái gắn với Pod, node, socket, credential hoặc lease phải được xác minh hoặc tạo lại sau restore.

## 4. Rolling update của Deployment hoạt động như thế nào?

Khi Pod template của Deployment thay đổi, Kubernetes tạo ReplicaSet mới và dần thay thế các Pod cũ theo `strategy.rollingUpdate`. Deployment điều phối số Pod mới được tạo và số Pod cũ được phép unavailable trong quá trình rollout.

Hai tham số quan trọng:

- `maxSurge`: số Pod có thể được tạo vượt quá số replica mong muốn trong lúc rollout.
- `maxUnavailable`: số Pod tối đa có thể unavailable trong quá trình rollout.

Ví dụ, với `replicas: 4`, `maxSurge: 1` và `maxUnavailable: 1`, Deployment có thể tạm thời có tối đa 5 Pod và cho phép tối đa 1 Pod unavailable theo quy tắc rollout. Giá trị thực tế còn phụ thuộc readiness và tiến độ các Pod.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 1
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: registry.example.com/orders-api:2.4.0
          ports:
            - name: http
              containerPort: 8080
```

Trong rollout có CRaC, Pod mới có thể restore từ checkpoint của phiên bản tương thích. Nhưng Deployment chỉ quan tâm Pod mới có trở nên Ready hay không; Kubernetes không tự xác minh checkpoint đúng phiên bản ứng dụng hoặc đúng runtime. Pipeline phát hành phải gắn checkpoint với image, JDK/CRaC runtime, kiến trúc và cấu hình tương ứng.

### 4.1. Quy trình một Pod mới tham gia rollout

Một trình tự triển khai có thể gồm:

1. Deployment tạo Pod mới từ Pod template của ReplicaSet mới.
2. Container image được kéo, volume và Downward API được mount.
3. Entrypoint kiểm tra checkpoint artifact và chọn chế độ restore.
4. CRaC-enabled JVM restore trạng thái tiến trình.
5. Callback `afterRestore` làm mới identity, kết nối, token, lease và các resource phụ thuộc môi trường.
6. Ứng dụng chạy health check và chỉ báo Ready khi dependency bắt buộc hoạt động.
7. Service/EndpointSlice bắt đầu đưa traffic tới Pod mới sau khi Pod Ready.
8. Pod cũ được đánh dấu terminating, ngừng nhận traffic, drain request và dừng an toàn.

Nếu restore thất bại, Pod mới không được báo Ready. Kubernetes có thể restart container theo restart policy hoặc Deployment tiếp tục chờ cho tới khi rollout tiến triển hoặc vượt `progressDeadlineSeconds`. Không nên tự động chuyển sang chạy ứng dụng mới trong trạng thái không rõ ràng nếu checkpoint lỗi; hãy có fallback cold-start được thiết kế tường minh và quan sát được.

## 5. Readiness, startup và liveness probe

Probe quyết định Kubernetes hiểu trạng thái container như thế nào:

| Probe | Câu hỏi | Hành vi khi thất bại |
|---|---|---|
| Startup | Ứng dụng đã hoàn tất giai đoạn khởi động ban đầu chưa? | Kubernetes chưa chạy liveness/readiness cho tới khi startup probe thành công; nếu quá hạn, container bị restart |
| Readiness | Pod hiện có thể nhận traffic không? | Pod bị loại khỏi các endpoint phục vụ traffic của Service trong thời gian chưa Ready |
| Liveness | Process có cần được restart vì không còn hoạt động bình thường? | Kubelet restart container khi probe thất bại đủ ngưỡng |

Với CRaC, readiness nên kiểm tra trạng thái sau restore chứ không chỉ kiểm tra JVM process tồn tại. Ví dụ, JVM có thể đã phục hồi nhưng database pool chưa kết nối lại, consumer chưa subscribe hoặc Pod identity chưa được refresh.

Startup probe phù hợp khi restore có thời gian biến động. Nó cho phép đặt một khoảng thời gian khởi động đủ dài mà không làm liveness probe restart container quá sớm. Readiness probe cần phản ánh điều kiện thực sự để nhận traffic. Liveness probe nên kiểm tra tiến trình có bị treo hoặc mất khả năng tự phục hồi hay không; không nên đánh dấu liveness thất bại chỉ vì một dịch vụ phụ thuộc tạm thời đang unavailable, nếu điều đó khiến toàn bộ Pod liên tục restart và tạo thêm tải.

Ví dụ cấu hình:

```yaml
containers:
  - name: app
    image: registry.example.com/orders-api:2.4.0
    ports:
      - name: http
        containerPort: 8080
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 5
      failureThreshold: 60
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: http
      periodSeconds: 3
      timeoutSeconds: 2
      failureThreshold: 2
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
```

Các endpoint ở ví dụ cần được cấu hình để phản ánh đúng trạng thái CRaC restore và dependency. `failureThreshold` cùng `periodSeconds` chỉ là giá trị minh họa; hãy đo thời gian restore trên hạ tầng thật để chọn giới hạn phù hợp.

## 6. Graceful termination và drain Pod cũ

Trong rolling update, Pod cũ được chuyển sang trạng thái terminating. Kubernetes chạy `preStop` hook nếu có, gửi tín hiệu dừng tới container theo cấu hình và chờ trong `terminationGracePeriodSeconds` trước khi buộc kết thúc process.

Ứng dụng cần phối hợp nhiều bước:

1. Ngừng readiness để Pod không tiếp tục được chọn cho traffic mới.
2. Ngừng nhận công việc mới từ listener, consumer và scheduler.
3. Drain request đang xử lý và hoàn tất transaction cần thiết.
4. Đóng kết nối và resource theo lifecycle CRaC hoặc shutdown bình thường.
5. Thoát trước khi hết termination grace period.

Không nên giả định việc readiness chuyển sang false lập tức loại bỏ mọi request đang trên đường tới Pod. EndpointSlice, kube-proxy, ingress controller và load balancer có thể cần thời gian cập nhật. `preStop` có thể được dùng để bắt đầu quiesce hoặc phối hợp drain, nhưng thời gian chạy hook nằm trong termination grace period.

Ví dụ cấu hình:

```yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: app
      lifecycle:
        preStop:
          httpGet:
            path: /internal/quiesce
            port: 8080
```

Endpoint `/internal/quiesce` là API do ứng dụng tự triển khai. Nó nên chuyển readiness sang false, ngừng admission và chờ drain theo deadline. Hook `preStop` không tự tạo checkpoint. Kubernetes cũng không tự gọi CRaC checkpoint chỉ vì Pod bị terminate; nếu muốn checkpoint khi shutdown, cần một quy trình riêng có quyền, thời gian và điều kiện phù hợp. Đối với rollout thông thường, có thể dùng checkpoint đã chuẩn bị trước cho Pod mới và graceful shutdown cho Pod cũ.

`terminationGracePeriodSeconds` phải lớn hơn tổng ngân sách cho quiesce, drain và đóng resource. Nếu quá trình drain dài hơn thời gian này, kubelet có thể buộc dừng container trước khi ứng dụng hoàn tất.

## 7. Autoscaling: mỗi replica mới là một lần restore riêng

Horizontal Pod Autoscaler điều chỉnh số replica dựa trên metrics như CPU, memory hoặc custom/external metrics. Khi tải tăng, HPA có thể tăng số Pod; mỗi Pod mới sẽ trải qua scheduling, image pull, volume setup, restore, refresh resource và readiness.

CRaC có thể giảm thời gian khởi tạo JVM và framework, nhưng không loại bỏ toàn bộ độ trễ tạo Pod. Những bước vẫn có thể tốn thời gian gồm:

- Scheduler tìm node phù hợp với CPU, memory, affinity, taint và topology.
- Kéo OCI image nếu node chưa có image.
- Attach/mount volume chứa checkpoint hoặc dữ liệu ứng dụng.
- Đọc và restore checkpoint từ storage.
- Tạo lại socket, pool, token, lease và subscription.
- Chạy health check và chờ endpoint cập nhật.

Vì vậy, khi thiết kế autoscaling, hãy đo từ lúc HPA quyết định scale tới lúc Pod Ready và nhận request đầu tiên. Đo riêng restore duration để biết CRaC giúp giảm giai đoạn nào.

### 7.1. HPA và ví dụ cấu hình

Ví dụ HPA dùng CPU utilization:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Pods
          value: 4
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
```

Đây là cấu hình minh họa, không phải khuyến nghị cố định cho mọi workload. HPA cần metrics server hoặc adapter tương ứng; resource requests phải được cấu hình để CPU utilization có ý nghĩa. `behavior` giúp giới hạn tốc độ scale và giảm dao động khi tải thay đổi nhanh.

### 7.2. Scale-out đồng thời và thundering herd

Khi HPA tạo nhiều Pod cùng lúc, tất cả có thể đọc cùng checkpoint artifact, tạo connection tới cùng database và tải cùng dữ liệu cache. Nếu checkpoint lớn, storage có thể trở thành bottleneck. Nếu mọi Pod cùng kết nối ngay sau restore, database hoặc service discovery có thể bị dồn tải.

Các biện pháp giảm đỉnh tải:

- Dùng giới hạn scale-up phù hợp để không tạo quá nhiều Pod trong một chu kỳ.
- Giới hạn concurrency của bước restore hoặc refresh nếu storage/dependency có giới hạn.
- Dùng retry có exponential backoff và jitter cho kết nối ngoài.
- Khởi động consumer và cache warm-up theo batch nếu workload cho phép.
- Đặt connection pool size theo tổng số replica dự kiến, không chỉ theo một Pod.
- Theo dõi số Pod đang restoring, số Pod Ready và thời gian dependency phục hồi.

Jitter cho retry kết nối không thay thế chính sách HPA. Một cụm vẫn có thể tạo nhiều Pod đồng thời; cần điều chỉnh cả tốc độ scale và hành vi khởi động của từng Pod.

## 8. Định danh Pod mới bằng Downward API

Kubernetes Downward API cho phép đưa metadata của Pod vào container dưới dạng environment variable hoặc file volume. Với CRaC, nên cẩn thận khi sử dụng environment variable cho identity: giá trị được inject lúc container được tạo, còn heap và process state được phục hồi từ checkpoint có thể giữ các giá trị đã chụp ở Pod cũ. Không nên giả định việc tạo Pod mới sẽ tự thay thế mọi giá trị identity đã lưu trong JVM.

Một cách rõ ràng là mount các trường identity qua Downward API volume và đọc lại sau restore:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-api-example
  labels:
    app: orders-api
spec:
  containers:
    - name: app
      image: registry.example.com/orders-api:2.4.0
      volumeMounts:
        - name: pod-identity
          mountPath: /etc/pod-identity
          readOnly: true
  volumes:
    - name: pod-identity
      downwardAPI:
        items:
          - path: uid
            fieldRef:
              fieldPath: metadata.uid
          - path: name
            fieldRef:
              fieldPath: metadata.name
          - path: namespace
            fieldRef:
              fieldPath: metadata.namespace
          - path: pod-ip
            fieldRef:
              fieldPath: status.podIP
          - path: node-name
            fieldRef:
              fieldPath: spec.nodeName
```

Mỗi Pod có volume được populate từ metadata của chính Pod đó. Sau restore, ứng dụng đọc lại file từ mount hiện tại thay vì dùng giá trị đã cache trước checkpoint. Các trường identity bất biến trong vòng đời Pod như UID không tự đổi; Pod mới có UID mới. Một số metadata có thể thay đổi theo thời gian và Downward API volume được cập nhật theo semantics của Kubernetes. Hãy kiểm tra tài liệu field được hỗ trợ và không giả định mọi field đều có cùng cơ chế cập nhật.

Nếu dùng environment variable từ `fieldRef`, ví dụ `POD_NAME`, `POD_UID`, `POD_NAMESPACE`, hãy coi đó là giá trị gắn với lần tạo container. Không dùng chúng như nguồn duy nhất để refresh identity bên trong một JVM được restore từ checkpoint của tiến trình khác.

## 9. Đọc identity hiện tại trong Java sau restore

Có thể gom các file Downward API vào một provider và đọc lại trong callback `afterRestore`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public record PodIdentity(
        String uid,
        String name,
        String namespace,
        String podIp,
        String nodeName) {
}

public final class PodIdentityProvider {
    private final Path root;

    public PodIdentityProvider(Path root) {
        this.root = root;
    }

    public PodIdentity readCurrent() throws IOException {
        return new PodIdentity(
                read("uid"),
                read("name"),
                read("namespace"),
                read("pod-ip"),
                read("node-name"));
    }

    private String read(String file) throws IOException {
        return Files.readString(root.resolve(file)).trim();
    }
}
```

Resource cập nhật identity trước các resource phụ thuộc vào nó:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class PodIdentityResource implements Resource {
    private final PodIdentityProvider provider;
    private volatile PodIdentity current;

    public PodIdentityResource(PodIdentityProvider provider) throws Exception {
        this.provider = provider;
        this.current = provider.readCurrent();
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) {
        // Identity chỉ được đọc; không cần đóng tài nguyên.
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        current = provider.readCurrent();
    }

    public PodIdentity current() {
        PodIdentity value = current;
        if (value == null) {
            throw new IllegalStateException("Pod identity is not initialized");
        }
        return value;
    }
}
```

Ví dụ giả định mount `/etc/pod-identity` hiện diện trong filesystem mà tiến trình restore truy cập được. Trong một triển khai CRaC trên container, cần xác nhận cơ chế restore thực tế giữ mount của Pod mới và callback chạy sau khi các volume đã sẵn sàng. Nếu runtime hoặc nền tảng không bảo đảm điều đó, hãy đưa bước lấy identity vào entrypoint/restore integration phù hợp và chỉ mở readiness sau khi xác minh.

Đăng ký `PodIdentityResource` trước các resource tạo client, đăng ký service discovery hoặc phát telemetry. Với global context, `afterRestore` chạy theo thứ tự đăng ký; identity được refresh trước consumer. `beforeCheckpoint` chạy theo thứ tự ngược, nên consumer dừng trước.

Điều này chỉ đúng khi volume mount của Pod mới thực sự hiện diện trong mount namespace mà runtime dùng để restore. Cần kiểm chứng khả năng đó với CRaC/container integration cụ thể; nếu runtime phục hồi mount namespace cũ, phải có bước platform-specific để cung cấp metadata hiện tại trước khi mở readiness.

## 10. Tạo process identity mới sau mỗi restore

Pod UID phân biệt Pod, nhưng đôi khi ứng dụng còn cần một định danh cho mỗi lần JVM được khởi chạy hoặc restore. Ví dụ, một Pod có thể restart container nhiều lần trong khi UID Pod không đổi. Một `processRunId` mới giúp phân biệt mỗi lần chạy trong log và trace.

Không lưu `processRunId` như một static final được khởi tạo trước checkpoint nếu muốn nó phân biệt lần restore. Tạo lại giá trị trong `afterRestore` hoặc trong bước bootstrap sau khi restore, rồi cập nhật MDC/tracing/metrics context theo cách thread-safe.

Ví dụ:

```java
import java.util.UUID;

public final class ProcessRunIdentity {
    private volatile String runId = UUID.randomUUID().toString();

    public void refreshAfterRestore() {
        runId = UUID.randomUUID().toString();
    }

    public String current() {
        return runId;
    }
}
```

Giá trị `runId` có thể được làm mới trong một `Resource.afterRestore`. Dùng Pod UID làm dimension để nhận biết Pod và process run ID để nhận biết lần chạy; không dùng hai khái niệm thay thế cho nhau.

## 11. Làm mới token và workload identity

Pod có thể dùng Kubernetes ServiceAccount để truy cập API server hoặc dùng workload identity của nền tảng cloud. Token được mount có thể được xoay vòng; certificate và credential có thể có thời hạn. Nếu ứng dụng giữ token trong heap trước checkpoint, token đó có thể hết hạn hoặc không còn phù hợp sau restore.

Các nguyên tắc:

- Không đưa token dài hạn hoặc secret vào checkpoint nếu có thể lấy lại từ secret manager hoặc projected volume.
- Sau restore, đọc lại token từ projected ServiceAccount token volume hoặc dùng credential provider được hỗ trợ.
- Không cache token vô thời hạn; tôn trọng thời hạn và cơ chế refresh của provider.
- Nếu dùng mTLS, tạo lại hoặc refresh TLS context khi certificate thay đổi.
- Không ghi token, private key hoặc credential vào log hay metric.
- Xác nhận quyền của service account mới đúng với Pod template hiện tại.

Projected ServiceAccount token có thể được rotate bởi kubelet. Ứng dụng cần đọc lại file hoặc dùng thư viện credential có khả năng reload token; giữ nội dung token cũ trong heap có thể khiến request sau restore nhận lỗi xác thực.

## 12. Lease, leader election và distributed lock

Một checkpoint có thể chứa trạng thái leader, lease owner hoặc distributed lock trong heap. Khi nhiều Pod restore từ cùng checkpoint, trạng thái này có thể bị nhân bản. Không được giả định Pod mới vẫn là leader chỉ vì snapshot trước checkpoint đang giữ cờ `isLeader = true`.

Sau restore:

1. Xóa hoặc vô hiệu hóa trạng thái leadership cũ trong bộ nhớ.
2. Kết nối lại tới coordination backend.
3. Thực hiện acquire/renew lease theo giao thức hiện tại.
4. Dùng lease expiration và fencing token để ngăn chủ sở hữu cũ tiếp tục ghi.
5. Chỉ chạy tác vụ leader sau khi lease được xác nhận.

Nếu dùng Kubernetes Lease API cho leader election, mỗi Pod cần identity riêng làm `holderIdentity`, ví dụ Pod UID cộng process run ID. Không copy holder identity từ checkpoint. Lease trong API server là nguồn sự thật; snapshot chỉ là trạng thái cục bộ có thể cũ.

Đối với distributed lock ngoài Kubernetes, cần fencing token hoặc version tăng đơn điệu. Chỉ dựa vào việc “đã lấy lock trước checkpoint” là không đủ vì tiến trình khác có thể đã lấy lock trong lúc Pod cũ dừng.

## 13. Deployment hay StatefulSet?

Chọn controller dựa trên semantics của ứng dụng:

| Controller | Danh tính | Storage/network | Phù hợp với |
|---|---|---|---|
| Deployment | Replica không có ordinal ổn định; Pod UID mới khi thay thế | Thường dùng storage dùng chung hoặc ephemeral | Stateless API, web service, worker có thể scale ngang |
| StatefulSet | Pod có ordinal ổn định như `orders-0`, `orders-1` | Có thể gắn PVC riêng cho từng ordinal và headless Service | Workload cần danh tính ordinal và storage ổn định |

StatefulSet cung cấp danh tính ổn định theo ordinal, nhưng Pod UID và Pod IP vẫn thay đổi khi Pod được tạo lại. Không nhầm tên `orders-0` với UID của một lần tạo Pod. PVC gắn với ordinal có thể giữ dữ liệu qua Pod replacement, nhưng checkpoint vẫn phải tương thích với runtime và volume; cần bảo đảm không có hai tiến trình cùng restore và ghi vào một PVC tại cùng thời điểm.

Nếu workload là stateless API, Deployment thường phù hợp hơn. Trạng thái nghiệp vụ nên nằm trong database, object storage hoặc durable queue. CRaC checkpoint dùng để tăng tốc quá trình khởi động, không nên trở thành nguồn dữ liệu duy nhất cho trạng thái nghiệp vụ của replica.

## 14. PodDisruptionBudget và khả năng duy trì capacity

PodDisruptionBudget (PDB) đặt ngân sách số Pod được phép bị gián đoạn do voluntary disruption như drain node. PDB giúp bảo vệ availability trong một số thao tác quản trị, nhưng không thay thế rollout strategy của Deployment. Deployment rolling update được điều khiển chủ yếu bởi `maxSurge` và `maxUnavailable` trong Deployment strategy; PDB không phải cơ chế khóa mọi Pod trong rollout.

Ví dụ:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api
spec:
  minAvailable: 3
  selector:
    matchLabels:
      app: orders-api
```

PDB chỉ có ý nghĩa nếu selector khớp Pod và số replica/capacity cho phép duy trì `minAvailable`. PDB không bảo đảm đủ capacity nếu nhiều Pod gặp lỗi ngoài voluntary disruption, cũng không sửa được readiness sai. Khi dùng PDB, hãy thiết kế đồng bộ với replicas, rollout strategy, autoscaling và topology spread.

## 15. Checkpoint dùng chung và dữ liệu riêng của từng Pod

Một checkpoint chuẩn bị trước có thể được dùng làm base cho nhiều Pod nếu runtime và nền tảng hỗ trợ mô hình đó. Khả năng restore cùng checkpoint trên Pod khác hoặc node khác phụ thuộc runtime, kernel, CPU architecture, namespace, filesystem và các giới hạn của CRaC/CRIU integration. Không suy luận rằng một checkpoint bất kỳ có thể di chuyển tự do giữa mọi node trong cluster. Trước rollout, hãy thử restore trên đúng loại node pool và container runtime sẽ dùng trong production. Cần phân loại trạng thái trong checkpoint:

| Trạng thái | Có thể dùng chung? | Hành động sau restore |
|---|---|---|
| Class metadata và object graph bất biến | Thường có | Có thể tái sử dụng nếu tương thích |
| Cache dữ liệu công khai, ít thay đổi | Có thể | Kiểm tra freshness và invalidate nếu cần |
| Pod UID, Pod IP, node name | Không | Đọc identity của Pod hiện tại |
| Process run ID hoặc random instance ID | Không | Sinh lại cho mỗi lần restore |
| Socket, connection pool, TLS session | Không nên giả định | Đóng/mở lại hoặc refresh theo thư viện |
| Service discovery registration | Không | Đăng ký địa chỉ hiện tại, deregister trạng thái cũ nếu cần |
| Leader lease/distributed lock | Không | Acquire/renew bằng identity mới |
| Credential/token ngắn hạn | Không nên giữ làm nguồn duy nhất | Đọc/refresh credential hiện hành |
| In-memory queue hoặc task đang chạy | Phụ thuộc semantics | Drain, lưu bền vững hoặc phục hồi có idempotency |

Nếu nhiều Pod restore từ cùng checkpoint, mỗi Pod sẽ bắt đầu với bản sao của heap snapshot. Các object mutable trong heap không được chia sẻ đồng bộ giữa Pod, nhưng trạng thái giống nhau có thể tạo ra hành vi trùng lặp. Ví dụ, hai replica cùng có bộ đếm local `nextOrderId = 100` không thể tự bảo đảm ID duy nhất. ID nghiệp vụ cần được cấp bởi database, sequence hoặc dịch vụ điều phối trung tâm.

## 16. Bảo vệ checkpoint và dữ liệu nhạy cảm

Checkpoint có thể chứa heap state, token, session, dữ liệu người dùng và thông tin xác thực. Nếu lưu checkpoint trong OCI image hoặc object storage, người có quyền đọc artifact có thể tiếp cận dữ liệu đã chụp.

Hãy áp dụng các biện pháp:

- Hạn chế quyền đọc checkpoint và manifest bằng RBAC/ACL.
- Mã hóa artifact khi lưu trữ và khi truyền tải.
- Không bake secret dài hạn vào checkpoint nếu có thể lấy lại sau restore.
- Xác minh checksum và chữ ký artifact trước khi restore.
- Gắn checkpoint với version ứng dụng và runtime; không dùng artifact không rõ nguồn.
- Có chính sách retention và xóa checkpoint cũ khi không còn cần thiết.
- Tránh chia sẻ checkpoint giữa môi trường dev, staging và production nếu chứa dữ liệu hoặc credential khác nhau.

Checksum chỉ phát hiện thay đổi so với manifest. Chữ ký manifest hoặc nguồn artifact được xác thực mới giúp xác minh nguồn gốc; mã hóa bảo vệ tính bí mật. Ba cơ chế giải quyết ba vấn đề khác nhau.

## 17. Ví dụ Pod template có checkpoint và identity volume

Ví dụ sau minh họa một Deployment dùng checkpoint từ một thư mục được mount, đồng thời cấp identity riêng cho Pod. Phần lệnh restore phụ thuộc CRaC-enabled runtime và cách đóng gói của dự án; script `restore-entrypoint` là thành phần ứng dụng cần triển khai.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example.com/orders-api:2.4.0
          command: ["/opt/app/restore-entrypoint"]
          ports:
            - name: http
              containerPort: 8080
          volumeMounts:
            - name: checkpoint
              mountPath: /opt/checkpoint
              readOnly: true
            - name: pod-identity
              mountPath: /etc/pod-identity
              readOnly: true
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 60
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 3
            failureThreshold: 2
          lifecycle:
            preStop:
              httpGet:
                path: /internal/quiesce
                port: http
      volumes:
        - name: checkpoint
          persistentVolumeClaim:
            claimName: orders-api-checkpoint
        - name: pod-identity
          downwardAPI:
            items:
              - path: uid
                fieldRef:
                  fieldPath: metadata.uid
              - path: name
                fieldRef:
                  fieldPath: metadata.name
              - path: namespace
                fieldRef:
                  fieldPath: metadata.namespace
              - path: pod-ip
                fieldRef:
                  fieldPath: status.podIP
              - path: node-name
                fieldRef:
                  fieldPath: spec.nodeName
```

Đây là ví dụ kiến trúc, không phải manifest production dùng nguyên trạng. Một PVC dùng chung giữa nhiều Pod chỉ phù hợp nếu access mode và storage semantics cho phép nhiều reader; checkpoint payload cần được publish bất biến. Ví dụ mount read-only chỉ phù hợp khi runtime có thể restore từ payload chỉ đọc. Nếu runtime cần ghi metadata hoặc file tạm, hãy copy artifact đã verify sang working directory writable riêng theo Pod UID. Không cho nhiều Pod ghi vào cùng thư mục checkpoint. Nếu mỗi Pod cần ghi checkpoint riêng, dùng đường dẫn/version riêng theo Pod UID hoặc một cơ chế snapshot/coordination phù hợp.

`maxUnavailable: 0` giữ số Pod Ready hiện có trong rollout ở mức tối đa theo khả năng capacity, nhưng cần đủ tài nguyên để tạo Pod surge. Nếu cluster không có CPU/memory hoặc quota cho Pod mới, rollout có thể bị kẹt. Hãy kiểm tra capacity và autoscaler của node pool.

## 18. Restore entrypoint và fallback có kiểm soát

Entrypoint nên xác minh artifact và runtime trước khi yêu cầu JVM restore. Một flow khái quát:

```bash
#!/usr/bin/env bash
set -euo pipefail

CHECKPOINT_DIR="/opt/checkpoint/current"

/opt/app/bin/verify-checkpoint "$CHECKPOINT_DIR"

exec java "-XX:CRaCRestoreFrom=$CHECKPOINT_DIR"
```

Đây là minh họa cách truyền option; với CRaC, restore thường tiếp tục tiến trình đã chụp và không phải một lần chạy `-jar` bình thường từ đầu. Lệnh chính xác phụ thuộc runtime, launcher và cách checkpoint được tạo. Hãy dùng lệnh restore mà bản phân phối CRaC yêu cầu; không thêm `-jar` hoặc tham số ứng dụng nếu runtime không yêu cầu chúng. Mục đích của ví dụ là nhấn mạnh bước verify phải hoàn tất trước khi JVM đọc checkpoint.

Nếu muốn hỗ trợ cold-start khi checkpoint không tương thích, hãy xác định rõ điều kiện fallback. Ví dụ, lỗi `MISSING_FILE`, `HASH_MISMATCH` hoặc runtime version không khớp nên làm Pod không Ready và phát cảnh báo; một pipeline có thể triển khai image mới với startup path bình thường hoặc tạo checkpoint mới. Không tự sửa manifest hay bỏ qua checksum để cố restore.

## 19. Quan sát rolling update và autoscaling

Để biết rollout có thực sự nhanh hơn nhờ CRaC, hãy đo các mốc riêng:

- Thời điểm Deployment tạo Pod mới.
- Thời gian scheduling và image pull.
- Thời gian mount volume/checkpoint artifact.
- Thời gian verify checksum/signature.
- Thời gian JVM restore.
- Thời gian `afterRestore` làm mới identity và resource.
- Thời gian tới readiness.
- Thời điểm EndpointSlice cập nhật và request đầu tiên tới Pod.
- Thời gian drain và terminate Pod cũ.

Metrics có thể gồm:

| Metric | Ý nghĩa |
|---|---|
| `pod_restore_duration_seconds` | Thời gian JVM restore |
| `pod_restore_failures_total` | Số lần restore thất bại theo nguyên nhân |
| `pod_identity_refresh_duration_seconds` | Thời gian đọc và áp dụng identity hiện tại |
| `pod_ready_duration_seconds` | Thời gian từ container start tới Ready |
| `pod_drain_duration_seconds` | Thời gian quiesce/drain trước termination |
| `checkpoint_verify_failures_total` | Số lần artifact không vượt qua verify |
| `post_restore_reconnect_attempts_total` | Số lần thử reconnect sau restore |
| `replicas_restoring` | Số Pod đang ở giai đoạn restore |

Dùng Pod UID làm thuộc tính log/trace để phân biệt replica, nhưng tránh đưa UID hoặc tên Pod vào label metrics nếu cardinality cao theo vòng đời workload. Với metrics, dùng tên deployment, namespace, version và kết quả có cardinality giới hạn.

## 20. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Pod mới Ready nhưng log ghi UID cũ | Identity được cache trong heap trước checkpoint | Đọc Downward API volume sau restore và refresh context logging |
| Nhiều replica cùng `instanceId` | UUID được tạo trước checkpoint rồi nhân bản | Tạo process run ID mới sau mỗi restore |
| Pod không Ready sau restore | Dependency, token hoặc lease chưa phục hồi | Kiểm tra `afterRestore`, readiness condition và log reconnect |
| Restore dùng IP hoặc endpoint cũ | Socket, DNS hoặc config cache được giữ lại | Tạo lại connection và refresh endpoint/discovery |
| Leader bị nhân đôi | Trạng thái leadership được phục hồi từ heap ở nhiều Pod | Acquire lease mới bằng Pod identity và fencing token |
| Rolling update bị kẹt | Pod mới chưa Ready hoặc không đủ capacity cho `maxSurge` | Kiểm tra events, resource requests, quota, storage và restore failures |
| HPA scale-out nhưng service vẫn quá tải | Pod mới restore đồng thời rồi cùng reconnect/warm cache | Giới hạn scale-up, concurrency và dùng backoff/jitter |
| Pod cũ bị kill trước khi drain xong | `terminationGracePeriodSeconds` quá ngắn hoặc preStop không phối hợp | Đặt deadline drain và grace period phù hợp |
| Checkpoint đọc được nhưng restore thất bại | Runtime/OS/architecture không tương thích | Gắn metadata compatibility và kiểm thử trên node pool mục tiêu |
| Nhiều Pod ghi cùng checkpoint directory | Artifact dùng chung nhưng không bất biến | Dùng checkpoint read-only/versioned hoặc thư mục riêng cho mỗi Pod |

## 21. Quy trình triển khai đề xuất

Một quy trình phù hợp cho Deployment stateless API có thể tổ chức như sau:

1. Build OCI image chứa đúng ứng dụng và CRaC-enabled runtime.
2. Tạo checkpoint từ phiên bản ứng dụng đã khởi tạo và warm-up trên môi trường tương thích.
3. Tạo manifest, checksum và chữ ký cho checkpoint; gắn checkpoint với application version, JDK/CRaC version, OS và architecture.
4. Publish checkpoint bất biến cùng release metadata.
5. Cập nhật Deployment Pod template để dùng image và checkpoint version mới.
6. Pod mới được tạo, mount checkpoint và Downward API identity.
7. Entrypoint xác minh artifact rồi restore JVM.
8. `afterRestore` refresh Pod identity, process run ID, credentials, sockets, connection pools, discovery registration và lease.
9. Readiness chỉ đạt khi resource bắt buộc đã sẵn sàng.
10. Deployment chuyển traffic sang Pod mới rồi drain Pod cũ theo graceful termination.
11. HPA điều chỉnh replica theo metrics; các Pod scale-out sử dụng cùng artifact bất biến nhưng khởi tạo identity và resource riêng.
12. Theo dõi restore duration, Ready latency, reconnect load, rollout progress và lỗi verify.

Nếu ứng dụng có stateful workload, hãy tách trạng thái bền vững khỏi checkpoint và xác định rõ quyền sở hữu PVC/lease. StatefulSet có thể giữ ordinal và PVC ổn định nhưng không làm Pod UID hoặc network identity trở nên bất biến.

## 22. Checklist thiết kế

- [ ] Đã phân biệt OCI image với CRaC checkpoint image.
- [ ] Checkpoint được gắn với version ứng dụng và runtime tương thích.
- [ ] Artifact checkpoint được verify và publish bất biến trước rollout.
- [ ] Pod mới chỉ báo Ready sau restore và refresh resource thành công.
- [ ] Readiness, startup và liveness probe có mục đích riêng.
- [ ] Pod cũ ngừng nhận công việc mới và drain trong termination grace period.
- [ ] Không giả định Kubernetes tự tạo checkpoint khi Pod bị terminate.
- [ ] `maxSurge`/`maxUnavailable` phù hợp với capacity cluster.
- [ ] HPA scale-up được giới hạn để tránh dồn tải vào storage/dependency.
- [ ] Pod UID, IP, node name và process run ID được làm mới cho từng Pod/lần restore.
- [ ] Identity hiện tại được đọc từ Downward API volume hoặc nguồn runtime đáng tin cậy.
- [ ] Token, certificate, socket, pool, subscription và DNS được refresh khi cần.
- [ ] Leader lease/distributed lock được acquire lại bằng identity mới và fencing.
- [ ] Checkpoint artifact dùng chung bất biến; mỗi Pod có working copy riêng nếu runtime cần ghi khi restore.
- [ ] Stateful workload có chiến lược PVC và single-writer rõ ràng.
- [ ] Có metrics cho restore, identity refresh, readiness, drain và reconnect.
- [ ] Đã thử rolling update, scale-out đồng thời, Pod replacement và restore failure.

## 23. Tài liệu tham khảo

- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): rolling update, `maxSurge`, `maxUnavailable` và tiến trình rollout.
- [Kubernetes Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/): HPA và cách điều chỉnh số replica theo metrics.
- [Kubernetes Downward API](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/): cung cấp Pod metadata và resource fields cho container.
- [Kubernetes Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): ý nghĩa và hành vi của từng probe.
- [Kubernetes Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): termination, `preStop`, tín hiệu dừng và grace period.
- [Kubernetes PodDisruptionBudget](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/): voluntary disruptions và ngân sách availability.
- [Kubernetes StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/): ordinal identity và stable storage.
- [CRaC Project](https://crac.org/): checkpoint/restore runtime và các yêu cầu triển khai.

Kubernetes tạo và thay thế Pod theo controller, còn CRaC phục hồi trạng thái JVM bên trong container. Một checkpoint có thể được dùng làm nền để khởi động nhiều replica, nhưng mỗi Pod phải đọc identity hiện tại, tạo process identity riêng, làm mới credential/connection/lease và chỉ nhận traffic sau readiness. Rolling update, autoscaling và graceful termination cần được cấu hình cùng nhau để giảm thời gian khởi động mà vẫn giữ capacity, tránh trùng danh tính và không làm mất công việc đang xử lý.
