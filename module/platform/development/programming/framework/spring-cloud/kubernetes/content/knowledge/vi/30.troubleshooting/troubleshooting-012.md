# Pod khởi động lại liên tục vì probe hoặc cấu hình lỗi

Trong chương **Chẩn đoán sự cố** của module Spring Cloud Kubernetes (`SPRING_CLOUD_KUBERNETES`), bài học này giải thích cách tìm nguyên nhân ứng dụng Spring bị khởi động lại khi chạy trên Kubernetes. Trọng tâm là probe, cấu hình từ ConfigMap/Secret và quyền truy cập Kubernetes API; đồng thời làm rõ ảnh hưởng tới DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher.

Tình huống xuyên suốt là dịch vụ `orders` trong namespace `sck-lab`. Các lệnh minh họa dùng PowerShell và giả định bạn có quyền quan sát workload trong namespace này. Những đoạn cấu hình cần ghép vào ứng dụng, Deployment tương ứng; chúng không phải một bộ dự án hay image ứng dụng dựng sẵn.

Sau bài học, bạn cần có thể:

- Xác định container bị kubelet dừng vì probe hay tiến trình Spring tự thoát.
- Đọc Events, trạng thái kết thúc và log của lần chạy trước để tìm bằng chứng.
- Sửa đúng đường dẫn probe, ngân sách khởi động, nguồn cấu hình hoặc RBAC.
- Xác minh ứng dụng ổn định, nhận traffic và không còn phát sinh restart sau thay đổi.

## 1. Hiểu đúng hiện tượng trước khi sửa

Người vận hành thường nói “Pod restart”, nhưng kubelet thường khởi động lại **container bên trong cùng một Pod**. Pod vẫn có UID cũ và `restartCount` của container tăng. Khi Deployment tạo Pod thay thế, Pod mới có UID khác; bộ đếm của Pod mới không nối tiếp bộ đếm cũ. `CrashLoopBackOff` mô tả khoảng chờ giữa những lần thử chạy lại, không chỉ ra lỗi gốc và không phải một Pod phase riêng. [Pod Lifecycle — Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)

Phân loại từ bằng chứng:

| Dấu hiệu | Hướng điều tra đầu tiên |
| --- | --- |
| Events có `Liveness probe failed`, tiếp theo là thông báo container bị dừng | Đường dẫn, port, timeout và nội dung liveness |
| Events có `Startup probe failed` lặp lại rồi container bị dừng | Endpoint startup hoặc thời gian khởi động thực tế |
| `Readiness probe failed`, Pod không Ready nhưng restart không tăng | Khả năng phục vụ traffic; tìm nguyên nhân restart khác nếu có |
| Log kết thúc bằng lỗi bind thuộc tính, thiếu placeholder, lỗi tạo bean | Cấu hình mà Spring thực sự nhận |
| `CreateContainerConfigError`, thông báo thiếu Secret/key | Kubernetes chưa tạo được container, chưa tới giai đoạn Spring chạy |
| `FailedMount` | Volume, ConfigMap/Secret được tham chiếu hoặc cơ chế mount |
| `lastState.terminated.reason=OOMKilled` | Bộ nhớ; không quy ngay về probe |
| Pod cũ biến mất, UID mới xuất hiện | Rollout, eviction hoặc controller tạo Pod mới |

Một container có thể gặp nhiều lỗi nối tiếp. Ví dụ, sửa thiếu Secret giúp Java bắt đầu chạy, sau đó liveness sai port mới lộ ra. Luôn xác nhận lại nguyên nhân hiện tại sau mỗi thay đổi.

## 2. Ba probe trả lời ba câu hỏi khác nhau

| Probe | Câu hỏi cần trả lời | Khi thất bại đủ ngưỡng |
| --- | --- | --- |
| `startupProbe` | Ứng dụng đã vượt qua giai đoạn khởi động ban đầu chưa? | Container bị dừng; việc chạy lại theo restart policy |
| `livenessProbe` | Tiến trình có đang trong trạng thái cần khởi động lại không? | Container bị dừng; việc chạy lại theo restart policy |
| `readinessProbe` | Instance hiện tại có sẵn sàng nhận request không? | Instance bị đánh dấu không sẵn sàng; container vẫn chạy |

Khi có startup probe, kubelet chưa thực thi liveness và readiness cho đến khi startup probe thành công. Readiness thất bại **không trực tiếp làm container restart**, cũng không trì hoãn liveness nếu bạn không cấu hình startup probe. [Liveness, Readiness, and Startup Probes — Kubernetes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)

Ví dụ suy luận:

- `orders` cần khoảng 70 giây để mở HTTP server; liveness bắt đầu quá sớm và giết tiến trình trước mốc đó: xem xét startup probe.
- Spring dừng ngay sau 4 giây vì `server.port=eighty`: tăng thời gian chờ probe không sửa được lỗi.
- Ứng dụng vẫn chạy nhưng một điều kiện phục vụ chưa đạt: readiness phù hợp hơn việc bắt tất cả instance khởi động lại.

## 3. Thu thập bằng chứng trước khi thay đổi workload

### 3.1. Chọn đúng Pod và container

Kiểm tra context hiện tại, sau đó lấy tên Pod thực tế:

```powershell
kubectl config current-context

$ns = 'sck-lab'
kubectl -n $ns get pods -l app=orders -o wide

# Thay bằng tên Pod vừa quan sát được.
$podName = 'orders-7c9b6b5d8f-abcde'
$containerName = 'orders'

$podSnapshot = kubectl -n $ns get pod $podName -o json | ConvertFrom-Json
$podSnapshot.metadata.uid
$podSnapshot.status.containerStatuses |
    Select-Object name, restartCount, state, lastState
```

Đọc `state` cùng `lastState.terminated`, đặc biệt là `reason`, `exitCode`, `startedAt` và `finishedAt`. Với Pod nhiều container, đừng lấy restart của sidecar để kết luận về ứng dụng. Nếu ứng dụng chưa được tạo, kiểm tra thêm trạng thái init container trong `status.initContainerStatuses`.

### 3.2. Đối chiếu Events với log hiện tại và log trước đó

```powershell
kubectl -n $ns describe pod $podName
kubectl -n $ns get events --field-selector "involvedObject.name=$podName" --sort-by=.lastTimestamp

kubectl -n $ns logs $podName -c $containerName --timestamps --tail=200
kubectl -n $ns logs $podName -c $containerName --previous --timestamps --tail=200
```

`--previous` lấy log của lần chạy container trước trong Pod đó. Nó hữu ích khi log hiện tại chỉ có banner Spring vì container vừa chạy lại. Nếu chưa có lần chạy trước, lệnh có thể báo không có log tương ứng. Pod đã bị thay thế cần tra hệ thống log tập trung theo UID/thời gian cũ. [Debug Running Pods — Kubernetes](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/)

Một bản ghi điều tra có thể ngắn như sau:

```text
Pod UID: 9d...; container: orders
restartCount: 6 -> 7, cùng UID
09:10:12: HTTP server bắt đầu khởi tạo
09:10:20: Liveness probe failed: connection refused
09:10:40: Container orders failed liveness probe, will be restarted
Log lần trước: chưa có lỗi bind cấu hình; chưa hoàn tất startup
Giả thuyết: liveness cắt ngang quá trình khởi động
```

Đây là dữ liệu minh họa. Kết luận cần dựa trên thứ tự thời gian thực tế; một dòng `Unhealthy` riêng lẻ chưa chứng minh probe đã gây restart.

### 3.3. Không dùng exit code như lời giải duy nhất

`exitCode=1` chỉ cho biết tiến trình kết thúc lỗi. `137` thường liên quan đến SIGKILL nhưng không tự chứng minh OOM. Hãy ghép exit code với termination reason, Events và log; một tiến trình cũng có thể bị kill sau khi hết thời gian chờ dừng.

Nếu reason là `OOMKilled`, chuyển sang điều tra bộ nhớ: heap Java, metaspace, direct buffer, thread stack và giới hạn container. CPU bị throttling có thể làm startup hoặc probe chậm hơn. Tăng timeout không xử lý được thiếu bộ nhớ. [Resource Management for Pods and Containers — Kubernetes](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)

## 4. Nhánh A: kubelet khởi động lại container vì probe

### 4.1. Kiểm tra đúng endpoint, đúng port và đúng giao thức

Với HTTP probe, hãy đọc cấu hình đang nằm trên **Pod gặp lỗi**, vì Deployment có thể đã được cập nhật sau khi Pod đó được tạo:

```powershell
$containerSpec = $podSnapshot.spec.containers |
    Where-Object { $_.name -eq $containerName }
$containerSpec.livenessProbe | ConvertTo-Json -Depth 8
$containerSpec.readinessProbe | ConvertTo-Json -Depth 8
$containerSpec.startupProbe | ConvertTo-Json -Depth 8
```

Kubelet thường gọi HTTP probe tới IP của Pod, không đi qua Ingress hay Service. Vì vậy, Ingress hoạt động không chứng minh probe đúng. Khai báo `containerPort: 8080` cũng không khiến Spring tự lắng nghe cổng 8080. HTTP probe coi mã từ 200 đến dưới 400 là thành công; tránh endpoint chuyển hướng đăng nhập vì nó có thể che khuất vấn đề. [Configure Probes — Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

| Kết quả probe | Kiểm tra tiếp |
| --- | --- |
| `connection refused` | Server chưa mở cổng, sai port hoặc chỉ bind vào loopback |
| HTTP 404 | Sai path, context path, health group chưa tồn tại hoặc thiếu Actuator |
| HTTP 401/403 | Security filter đang chặn health endpoint |
| HTTP 503 | Health group báo trạng thái không khỏe; đọc indicator tương ứng |
| Timeout | CPU, GC, luồng xử lý, mạng hoặc phép kiểm tra phụ thuộc chậm |
| Lỗi TLS | `scheme`, cấu hình TLS và cổng thực tế không khớp |

Để xem phản hồi trực tiếp khi container còn chạy:

```powershell
# Giữ lệnh này ở terminal thứ nhất.
kubectl -n $ns port-forward pod/$podName 18080:8080
```

Ở terminal thứ hai:

```powershell
curl.exe -i --max-time 3 http://127.0.0.1:18080/livez
curl.exe -i --max-time 3 http://127.0.0.1:18080/readyz
```

Port-forward giúp kiểm tra nội dung HTTP và path. Nó không tái hiện đầy đủ đường mạng kubelet đến Pod; nếu phép thử thành công nhưng probe vẫn timeout, tiếp tục kiểm tra bind address, CNI, policy và sidecar theo bằng chứng. Image tối giản không cần có sẵn `curl` để dùng cách này.

### 4.2. Tách health group của Spring Boot

Ứng dụng cần có Spring Boot Web và Actuator. Ví dụ cấu hình cho ứng dụng hỗ trợ Kubernetes health groups:

```yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
```

`add-additional-paths` tạo `/livez` và `/readyz` trên cổng ứng dụng. Điều này đặc biệt hữu ích khi management server dùng cổng riêng: health trên management port có thể trả lời dù cổng phục vụ request bị lỗi. Cần cho phép kubelet truy cập đúng hai đường dẫn trong security chain; không mở toàn bộ Actuator để chữa lỗi 401/403. [Kubernetes Probes — Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)

Không trỏ liveness vào health tổng hợp chỉ vì `/actuator/health` dễ nhớ. Health tổng hợp có thể bao gồm database, Redis hoặc discovery. Một lần Kubernetes API hay database gián đoạn không nên khiến mọi instance bị khởi động lại.

Liveness nên phản ánh khả năng sống của instance. Chỉ bổ sung phụ thuộc vào readiness khi việc loại instance khỏi luồng traffic thực sự có ích; nếu mọi replica cùng phụ thuộc một database, đánh dấu tất cả không Ready có thể làm mất toàn bộ khả năng phục vụ. [Checking External State With Kubernetes Probes — Spring Boot](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state)

### 4.3. Dành ngân sách riêng cho startup

Đoạn sau nằm trong `spec.template.spec.containers[]` của Deployment:

```yaml
name: orders
ports:
  - name: http
    containerPort: 8080
startupProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 36
livenessProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
readinessProbe:
  httpGet:
    path: /readyz
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
  successThreshold: 1
```

Trong ví dụ, `36 × 5 = 180` giây là ngân sách startup xấp xỉ để lập kế hoạch, không phải cam kết container luôn bị dừng chính xác ở giây 180. Chọn ngưỡng từ thời gian khởi động chậm quan sát được cộng khoảng đệm. Startup thành công chỉ bàn giao việc giám sát cho liveness/readiness; ứng dụng vẫn có thể chưa sẵn sàng nhận request. [Configure Probes — Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

Đây là bộ số minh họa. Nếu ứng dụng thường khởi động 20 giây nhưng đột ngột mất 5 phút, cần tìm nguyên nhân của thay đổi đó trước khi tiếp tục tăng ngưỡng. Probe cũng không có khả năng giữ một JVM đã tự thoát vì lỗi cấu hình.

## 5. Nhánh B: cấu hình làm ứng dụng không chạy được

### 5.1. Xác định lỗi xảy ra trước hay sau khi Java chạy

| Thời điểm | Ví dụ | Nơi tìm bằng chứng |
| --- | --- | --- |
| Trước khi tạo container | `secretKeyRef` trỏ tới key bắt buộc không tồn tại | Pod Events, waiting reason |
| Khi chuẩn bị volume | Tên ConfigMap sai hoặc không mount được | Events có `FailedMount` |
| Khi Spring đọc cấu hình | YAML không hợp lệ, import file không tồn tại | Log Java |
| Khi bind thuộc tính | `server.port=eighty`, kiểu dữ liệu không hợp lệ | Lỗi bind và tên property trong log |
| Khi tạo bean | Placeholder bắt buộc thiếu, URL sai, xác thực thất bại | Exception gốc và chuỗi `Caused by` |
| Khi đọc Kubernetes API | 403, namespace sai hoặc API timeout | Log client Kubernetes, tên resource và thao tác |

Thiếu Secret bắt buộc có thể ngăn container được tạo; trong trường hợp này chưa có log Spring để đọc. Đừng ép mọi lỗi thiếu cấu hình vào nhãn `CrashLoopBackOff`. [Secrets — Kubernetes](https://kubernetes.io/docs/concepts/configuration/secret/)

### 5.2. Lập bản đồ nguồn cấu hình

Trước khi sửa một giá trị, ghi lại nó đến từ đâu:

| Cách cung cấp | Ai lấy dữ liệu? | Hướng kiểm tra |
| --- | --- | --- |
| `env`, `envFrom` | Kubernetes chuẩn bị môi trường container | Tham chiếu, key và Pod được tạo lúc nào |
| Volume ConfigMap/Secret | Kubelet mount dữ liệu | Tên volume, mountPath, đường dẫn import |
| Spring Cloud Kubernetes PropertySource | Client của ứng dụng gọi API | Import, tên nguồn, namespace và ServiceAccount |
| Tham số Java/biến môi trường riêng | Spring Boot đọc khi startup | Nguồn ghi đè và kiểu dữ liệu |

Đừng giả định sửa ConfigMap sẽ thắng một biến môi trường cùng thuộc tính. Spring Boot có thứ tự ưu tiên nguồn cấu hình; đối chiếu cả profile đang bật, command-line arguments và biến môi trường. File YAML đầy đủ cần được import như file cấu hình, còn thư mục chứa mỗi property trong một file là mô hình `configtree:`. [Externalized Configuration — Spring Boot](https://docs.spring.io/spring-boot/reference/features/external-config.html)

Ví dụ mount một ConfigMap chứa file:

```yaml
# Phần ConfigMap.
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-config
  namespace: sck-lab
data:
  application.yml: |
    server:
      port: 8080
    orders:
      retry-limit: 3
```

Các phần tương ứng trong Pod template:

```yaml
spec:
  containers:
    - name: orders
      env:
        - name: SPRING_CONFIG_ADDITIONAL_LOCATION
          value: "file:/etc/orders/"
      volumeMounts:
        - name: orders-config
          mountPath: /etc/orders
          readOnly: true
  volumes:
    - name: orders-config
      configMap:
        name: orders-config
```

Đây là đường đọc file mount bằng Spring Boot. Nó không yêu cầu ứng dụng tự gọi API để lấy ConfigMap. Thư mục additional location bổ sung vào các vị trí mặc định; dấu `/` cuối đường dẫn có ý nghĩa khi chỉ định thư mục. Ví dụ cố ý coi cấu hình này là bắt buộc, nên không thêm `optional:`.

### 5.3. Nếu dùng Spring Cloud Kubernetes để đọc API

Với cơ chế Config Data được phiên bản thư viện hỗ trợ, cấu hình nhận diện nguồn có thể như sau:

```yaml
spring:
  application:
    name: orders
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        name: orders-config
        namespace: sck-lab
        fail-fast: true
```

Đặt cấu hình định vị nguồn trong cấu hình sẵn có của ứng dụng hoặc môi trường khởi động, không chỉ đặt bên trong chính ConfigMap chưa đọc được. Chọn starter Config phù hợp với Kubernetes Java Client hoặc Fabric8 và BOM đang dùng. Không chép đồng thời cơ chế legacy bootstrap và Config Data import vào cùng ứng dụng. [Kubernetes PropertySource Implementations — Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html)

`fail-fast=true` cho phép việc đọc cấu hình thất bại làm startup thất bại. Nếu có retry, kiểm tra điều kiện kích hoạt và dependency theo phiên bản; tính cả thời gian retry vào ngân sách khởi động. Retry có giới hạn hữu ích với gián đoạn tạm thời, còn lỗi 403 hoặc sai tên nguồn phải được sửa nguyên nhân. Tắt fail-fast không chứng minh ứng dụng đã có đủ cấu hình bắt buộc. [ConfigMap PropertySource — Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html)

## 6. Nhánh C: ServiceAccount hoặc RBAC không khớp

Việc bạn dùng tài khoản quản trị để `kubectl get configmap` thành công không chứng minh ứng dụng cũng đọc được dữ liệu. Trước tiên lấy ServiceAccount của **Pod gặp lỗi**:

```powershell
$saName = $podSnapshot.spec.serviceAccountName
$saName
$saIdentity = "system:serviceaccount:" + $ns + ":" + $saName

kubectl auth can-i get configmaps/orders-config -n $ns --as=$saIdentity
kubectl auth can-i list configmaps -n $ns --as=$saIdentity
```

`--as` yêu cầu người thực hiện có quyền impersonation. Nếu bị từ chối impersonate, kết quả đó chưa trả lời quyền của ServiceAccount; nhờ người có quyền thực hiện phép kiểm tra thay vì kết luận ứng dụng thiếu quyền đọc. [kubectl auth can-i — Kubernetes](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/)

Đọc lỗi API để biết verb/resource/namespace thực tế, rồi đối chiếu Role và RoleBinding. Với client đang liệt kê ConfigMap trong namespace, một Role chỉ có `get` theo tên có thể chưa đủ. Quyền `watch` liên quan tới thành phần đang theo dõi thay đổi; ServiceAccount của watcher có thể khác ServiceAccount ứng dụng.

Đối với Secret, không mở quyền đọc qua API chỉ để thử hết lỗi: xác định ứng dụng dùng volume hay Secret PropertySource. Spring Cloud Kubernetes có cấu hình riêng cho việc đọc Secret qua API; quyền list Secret có thể cho phép đọc dữ liệu của nhiều Secret trong namespace. [Secrets PropertySource — Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/secrets-propertysource.html)

Hướng sửa phải khớp tính năng thực sự dùng:

- Cấu hình qua file mount: sửa volume/import; ứng dụng không cần quyền API chỉ để đọc file đó.
- ConfigMap PropertySource qua API: cấp verb đọc cần thiết trong đúng namespace.
- DiscoveryClient: đối chiếu tài nguyên discovery mà loại client/phiên bản đang truy vấn.
- Configuration Watcher: kiểm tra identity và quyền theo dõi của controller riêng.

Không cấp `cluster-admin` cho ứng dụng để giải quyết lỗi đọc cấu hình. Sau khi sửa RoleBinding, xác minh lại chính thao tác trước đó bị 403 và lần startup tiếp theo.

## 7. Cấu hình thay đổi, refresh và restart là những việc khác nhau

ConfigMap dùng làm biến môi trường không tự thay đổi môi trường của tiến trình đang chạy. Volume ConfigMap được cập nhật theo cơ chế đồng bộ của Kubernetes; mount bằng `subPath` không nhận các cập nhật theo cách đó. File đã đổi cũng chưa chứng minh bean của Spring đã nhận giá trị mới. [ConfigMaps — Kubernetes](https://kubernetes.io/docs/concepts/configuration/configmap/)

Configuration Watcher có thể phát thông báo refresh khi ConfigMap/Secret phù hợp thay đổi. Với cách gọi HTTP, kiểm tra controller tìm đúng instance, gọi được endpoint refresh và ứng dụng hỗ trợ refresh giá trị cần đổi. Với file mount, cần tính tới độ trễ dữ liệu được chiếu xuống volume. Một refresh thành công không có nghĩa mọi tài nguyên như HTTP connector hay pool kết nối đã được dựng lại theo cấu hình mới. [Configuration Watcher — Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html)

Khi điều tra vòng restart ngay sau cập nhật cấu hình, lập bảng thời gian:

| Mốc | Cần ghi lại |
| --- | --- |
| Cấu hình thay đổi | Tên resource, namespace, resourceVersion hoặc phiên bản cấu hình nội bộ |
| Watcher xử lý | Instance đích, thời điểm, mã phản hồi; không ghi giá trị Secret |
| Ứng dụng nhận thay đổi | Thông báo refresh/rebind hoặc lỗi tạo lại bean |
| Probe thất bại | Loại probe và thời điểm |
| Tiến trình dừng | Lý do, exit code, UID và restartCount |

Không kết luận “watcher làm Pod restart” chỉ vì hai sự kiện gần nhau. Có thể ứng dụng lỗi sau refresh; cũng có thể công cụ triển khai đã thay Pod template và tạo rollout.

Nếu thuộc tính cần chạy lại tiến trình, dùng rollout có kiểm soát sau khi sửa nguồn:

```powershell
kubectl -n $ns rollout restart deployment/orders
kubectl -n $ns rollout status deployment/orders --timeout=240s
```

`rollout undo` phục hồi Pod template theo revision, không tự phục hồi nội dung một ConfigMap/Secret mutable đang được tham chiếu. Muốn quay lui đầy đủ phải khôi phục đúng phiên bản cấu hình hoặc dùng resource có tên theo phiên bản. [Deployments — Kubernetes](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)

## 8. Ảnh hưởng tới DiscoveryClient và Spring Cloud LoadBalancer

Trong đường đi qua Kubernetes Service thông thường, readiness giúp xác định endpoint sẵn sàng nhận traffic. Readiness không phải tường lửa chặn mọi request tới Pod IP.

Khi bên gọi báo “không có instance” hoặc LoadBalancer không chọn được đích, quan sát readiness và dữ liệu discovery trước khi chỉnh retry phía client:

```powershell
kubectl -n $ns get pods -l app=orders
kubectl -n $ns get service orders
kubectl -n $ns get endpointslices -l kubernetes.io/service-name=orders -o yaml
```

Đối chiếu selector Service với label Pod, cổng đích, địa chỉ endpoint và `conditions.ready`. Cách truy vấn/lọc instance còn phụ thuộc loại DiscoveryClient, tùy chọn đưa địa chỉ chưa Ready vào discovery và cache phía client. Không bật tùy chọn nhận instance chưa Ready để che lỗi khởi động. [DiscoveryClient for Kubernetes — Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html)

Spring Cloud Kubernetes không phải điều kiện bắt buộc để kubelet chạy probe; Spring Boot Actuator và Pod spec cung cấp phần đó. Chỉ đưa Config PropertySource, DiscoveryClient, LoadBalancer hoặc Watcher vào thiết kế khi ứng dụng cần chức năng tương ứng. Việc dùng Kubernetes Service DNS và cấu hình qua volume có thể đã đáp ứng một triển khai đơn giản.

## 9. Thực hành phân biệt ba tình huống

Dùng namespace lab và Deployment `orders` đã hoạt động với Actuator cùng bộ probe ở phần 4. Sau mỗi thay đổi Pod template, lấy tên và UID Pod mới trước khi so sánh restart. Chỉ thay một yếu tố trong mỗi lần thử.

### Tình huống 1: liveness sai đường dẫn

Chạy:

```powershell
kubectl -n $ns edit deployment/orders
```

Chỉ đổi `livenessProbe.httpGet.path` từ `/livez` sang `/livez-does-not-exist`; giữ startup probe đúng.

Quan sát Pod mới:

1. Startup probe thành công.
2. Liveness nhận 404, Events ghi nhận các lần thất bại.
3. Đủ ngưỡng, kubelet dừng container; restartCount tăng trong cùng UID.

Khôi phục path về `/livez`, theo dõi rollout và kiểm tra Pod mới ổn định. Lỗi thuộc hợp đồng probe; không cần đổi ConfigMap hoặc RBAC.

### Tình huống 2: Spring tự thoát vì sai kiểu cấu hình

Đặt biến môi trường ghi đè port:

```powershell
kubectl -n $ns set env deployment/orders SERVER_PORT=eighty
```

Lấy log và `--previous` của Pod mới. Dấu hiệu mong đợi là lỗi bind `server.port` sang số nguyên; tiến trình có thể thoát trước khi health endpoint xuất hiện. Đừng tăng startup budget để chữa lỗi này.

Khôi phục:

```powershell
kubectl -n $ns set env deployment/orders SERVER_PORT=8080
kubectl -n $ns rollout status deployment/orders --timeout=240s
```

Nếu Deployment ban đầu không có biến `SERVER_PORT`, có thể xóa biến để trả quyền quyết định về nguồn cấu hình ban đầu:

```powershell
kubectl -n $ns set env deployment/orders SERVER_PORT-
```

### Tình huống 3: chỉ readiness thất bại

Dùng `kubectl edit deployment/orders` đổi riêng `readinessProbe.httpGet.path` sang `/readyz-does-not-exist`. Giữ liveness và startup đúng.

Sau khi startup hoàn tất, Pod mới không Ready nhưng container tiếp tục chạy. Trong điều kiện không có lỗi khác, restartCount không tăng vì readiness. Kiểm tra EndpointSlice và gọi trực tiếp health endpoint qua port-forward để thấy sự khác nhau giữa tiến trình sống và khả năng nhận traffic qua Service.

Khôi phục readiness path về `/readyz`. Nếu restart vẫn tăng trong bài thử này, quay lại log/Events để tìm nguyên nhân độc lập; đó không phải hành vi restart do readiness.

## 10. Tiêu chí xác minh sau sửa

Một lần trả HTTP 200 chưa đủ xác nhận xử lý xong. Cần kiểm tra cả workload lẫn chức năng phục vụ:

- Ghi UID và restartCount ban đầu của từng container ứng dụng sau rollout; quan sát qua thời gian dài hơn một chu kỳ thất bại đầy đủ của probe và cả tác vụ gây lỗi trước đó.
- Xác nhận replica mong muốn Ready, rollout hoàn tất và Events không còn phát sinh lỗi liên quan.
- Kiểm tra `/livez`, `/readyz` trên đúng port; gọi thêm request nghiệp vụ qua Service.
- Xác nhận nguồn cấu hình thực sự có hiệu lực bằng thông tin không nhạy cảm, chẳng hạn mã phiên bản cấu hình; không công khai Secret qua log hoặc Actuator.
- Nếu có refresh, xác minh tất cả instance cần thiết đã nhận thay đổi. Nếu có rollout, xác minh chúng chạy cùng phiên bản cấu hình dự kiến.

Các lệnh quan sát bổ sung:

```powershell
kubectl -n $ns get pods -l app=orders -w
kubectl -n $ns rollout status deployment/orders --timeout=240s
kubectl -n $ns get endpointslices -l kubernetes.io/service-name=orders
```

Kết thúc theo dõi `-w` bằng Ctrl+C sau khi đủ cửa sổ quan sát. Nếu có Pod thay thế, ghi nhận UID mới; bộ đếm trở về 0 trên Pod mới không tự chứng minh nguyên nhân đã được sửa.

## 11. Những cách chữa làm mất dấu nguyên nhân

| Cách xử lý vội | Vấn đề | Hướng xử lý có căn cứ |
| --- | --- | --- |
| Tăng mọi timeout | Che lỗi bind/403; phát hiện lỗi thật chậm hơn | Đo startup, phân biệt lỗi tạm thời với lỗi cố định |
| Xóa Pod ngay | Mất log và trạng thái cần điều tra | Thu bằng chứng trước, sửa nguyên nhân rồi rollout |
| Cho liveness kiểm tra mọi phụ thuộc | Lỗi dùng chung có thể làm cả cụm instance restart | Dùng health group có mục đích rõ ràng |
| Tắt fail-fast để ứng dụng chạy | Có thể đưa instance thiếu cấu hình vào phục vụ | Xác định cấu hình bắt buộc, kiểm tra nguồn và kiểu |
| Cấp quyền quản trị toàn cluster | Vượt quá nhu cầu đọc cấu hình | Cấp quyền theo namespace, resource và verb thực tế |
| Thấy file ConfigMap đổi là coi refresh xong | Spring có thể vẫn dùng giá trị cũ | Xác minh giá trị có hiệu lực và cơ chế cập nhật |

Một chẩn đoán tốt cần nối được ba điều: **bằng chứng khiến container dừng**, **thay đổi sửa đúng nguyên nhân**, và **khoảng quan sát cho thấy ứng dụng phục vụ ổn định**. Probe, cấu hình và discovery liên quan tới nhau, nhưng mỗi cơ chế phải được kiểm tra bằng tín hiệu của chính nó.
