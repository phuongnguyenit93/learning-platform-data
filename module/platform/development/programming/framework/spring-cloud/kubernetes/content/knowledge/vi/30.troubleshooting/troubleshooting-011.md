# Leader không được bầu hoặc chuyển giao quá chậm

## Mục tiêu và bối cảnh

Trong module **SPRING_CLOUD_KUBERNETES**, leader election phục vụ trường hợp nhiều replica cùng chạy nhưng chỉ một replica chủ động điều phối một tác vụ, chẳng hạn quét đơn hàng chờ đối soát. Khi leader không xuất hiện hoặc chuyển giao chậm, cần kiểm tra cả Kubernetes API, cấu hình Spring và hành vi của tác vụ.

Sau bài này, bạn có thể:

- Xác định đúng cơ chế bầu leader và tài nguyên khóa đang được sử dụng.
- Phân biệt lỗi RBAC, sai namespace, Pod chưa Ready và lỗi xử lý sự kiện.
- Đo khoảng gián đoạn nghiệp vụ khi leader thay đổi.
- Chọn cách khắc phục dựa trên bằng chứng, đồng thời hạn chế tác vụ chạy trùng.

DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher giải quyết các nhu cầu khác nhau. Một ứng dụng tìm thấy Service, đọc được cấu hình hoặc trả HTTP thành công chưa chứng minh rằng phần bầu leader hoạt động.

## 1. Chốt implementation trước khi sửa cấu hình

Ví dụ chính của bài sử dụng **cơ chế Fabric8/ConfigMap truyền thống**, đối chiếu với Spring Cloud Kubernetes **3.3.3**. Đây là mốc tham chiếu để hiểu hành vi, không phải yêu cầu nâng hoặc hạ phiên bản ứng dụng.

Cơ chế này dùng dependency `spring-cloud-kubernetes-fabric8-leader` và sự kiện `OnGrantedEvent`, `OnRevokedEvent` của Spring Integration. Tài nguyên phối hợp là ConfigMap. Xem [Leader Election của nhánh 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/leader-election.html).

Tài liệu Spring Cloud Kubernetes 5.1 còn mô tả cơ chế native với nhóm thuộc tính `spring.cloud.kubernetes.leader.election.*`. Cơ chế native có thể dùng Lease hoặc ConfigMap và có các sự kiện `StartLeadingEvent`, `StopLeadingEvent`, `NewLeaderEvent`. Vì vậy, phải xác định implementation thực tế trước khi chọn listener hoặc manifest. Xem [Leader Election của Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/leader-election.html).

| Điểm cần xác định | Fabric8/ConfigMap truyền thống trong ví dụ | Native khi phiên bản đang dùng có hỗ trợ |
| --- | --- | --- |
| Chọn tên khóa | `leader.config-map-name` | `leader.election.lock-name` |
| Namespace của khóa | `leader.namespace` | `leader.election.lock-namespace` |
| Tài nguyên cần quan sát | ConfigMap và trạng thái Pod | Lease hoặc ConfigMap thực sự được chọn |
| Thông số thời gian cần đọc | `leader.update-period` và đường watch | `retry-period`, `renew-deadline`, `lease-duration` |
| Sự kiện vào/ra vai trò chủ động | `OnGrantedEvent` / `OnRevokedEvent` | `StartLeadingEvent` / `StopLeadingEvent` |

Các tên ngắn trong bảng đều nằm dưới `spring.cloud.kubernetes`. Không ghép hai cột thành một cấu hình chung.

Trong dự án cần chẩn đoán, lấy dependency tree, phiên bản Spring Cloud BOM và báo cáo auto-configuration để trả lời:

1. Thư viện leader nào thực sự nằm trên runtime classpath?
2. Kubernetes client nào được tạo thành bean?
3. Auto-configuration nào được kích hoạt hoặc bị loại?
4. Nhóm thuộc tính nào được phiên bản đó nhận diện?

Chỉ có discovery starter hoặc load-balancer starter chưa đủ để kết luận ứng dụng đã có leader election. Với implementation tham chiếu, auto-configuration còn phụ thuộc bean `KubernetesClient` và cờ `spring.cloud.kubernetes.leader.enabled`. Candidate mặc định lấy định danh từ hostname; cần đối chiếu định danh này với Pod thực tế nếu bạn tùy biến hostname. Xem [Fabric8LeaderAutoConfiguration 3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeaderAutoConfiguration.java).

## 2. Phân loại triệu chứng bằng ba lớp bằng chứng

Giả sử Deployment `orders-worker` có ba replica. Chúng cạnh tranh vai trò `order-reconciliation` và dùng ConfigMap `orders-worker-leaders` trong namespace `orders-lab`.

Một lần chẩn đoán cần ghép ba lớp:

| Lớp | Bằng chứng | Câu hỏi cần trả lời |
| --- | --- | --- |
| Kubernetes | Pod conditions, ServiceAccount, tài nguyên khóa, mã lỗi API | Có ứng viên đủ điều kiện và có quyền thao tác không? |
| Leader election trong JVM | Log tham gia, nhận/mất leadership, role và candidate ID | Ứng dụng đã nhận biết thay đổi chưa? |
| Nghiệp vụ | Lần xử lý cuối của leader cũ, lần xử lý đầu của leader mới, khóa idempotency | Công việc có tiếp tục và có bị lặp không? |

Các triệu chứng dễ bị đánh đồng:

- **Không có leader:** không có replica nào ghi nhận nhận leadership; bản ghi khóa cũng không có chủ hợp lệ.
- **Có leader nhưng tác vụ không chạy:** khóa và sự kiện cho thấy đã bầu được, nhưng scheduler, executor hoặc nhánh nghiệp vụ không hoạt động.
- **Chuyển giao chậm:** cuối cùng có leader mới, nhưng khoảng không xử lý vượt mục tiêu.
- **Nhiều Pod đều xử lý:** có thể các Pod dùng nhóm khóa khác nhau, hoặc tác vụ không bị ràng buộc bởi leadership.
- **Leader thay liên tục:** kiểm tra readiness dao động, lỗi kết nối API và tải JVM trước khi giảm timeout.

Không dùng duy nhất số Pod `Running` để kết luận. Ghi cả `Ready`, số lần restart và thời điểm quan sát.

## 3. Hiểu đường bầu leader của ví dụ ConfigMap

Trong implementation tham chiếu, ứng viên đọc bản ghi leader rồi kiểm tra Pod tương ứng. Ứng viên cũng phải Ready trước khi giành leadership. Cập nhật ConfigMap sử dụng `resourceVersion` để phát hiện xung đột. ConfigMap này không có cơ chế TTL giống cấu hình Lease native; không thể sửa thời gian chuyển giao bằng cách thêm `lease-duration` vào nhóm thuộc tính cũ. Xem [Fabric8LeadershipController 3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeadershipController.java).

~~~mermaid
flowchart TD
    A[Ứng viên đã khởi động] --> B{Đọc được ConfigMap?}
    B -->|Lỗi API hoặc RBAC| C[Chẩn đoán lỗi truy cập]
    B -->|Đọc được hoặc chưa tồn tại| D{Có leader với Pod Ready?}
    D -->|Có| E[Theo dõi leader hiện tại]
    D -->|Không| F{Pod ứng viên Ready?}
    F -->|Không| G[Chờ readiness]
    F -->|Có| H[Thử ghi bản ghi bằng resourceVersion]
    H -->|Thành công| I[Nhận leadership]
    H -->|Xung đột| J[Đọc lại và cạnh tranh tiếp]
~~~

Sơ đồ mô tả luồng chính; khi chính ứng viên đang giữ bản ghi nhưng không còn Ready, implementation có nhánh thu hồi leadership trước khi ổn định lại.

Thông tin nhóm cạnh tranh phải thống nhất: cùng cluster, namespace, tên ConfigMap, role và tiền tố khóa. Trong ví dụ, khóa dữ liệu mặc định cho role là:

~~~yaml
data:
  leader.id.order-reconciliation: orders-worker-7d6f9c8d5b-q2x4m
~~~

Đây là hình dạng minh họa sau khi thư viện ghi thành công. Không chép tên Pod này vào ConfigMap để chỉ định leader thủ công. Giá trị phải do vòng bầu leader quản lý.

Role khác nhau tạo khóa dữ liệu khác nhau trong cùng ConfigMap. Vì vậy hai Pod cùng dùng một ConfigMap nhưng khác role vẫn có thể đều trở thành leader của hai nhóm khác nhau. Xem [LeadershipController 3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/LeadershipController.java).

## 4. Thu thập bằng chứng trước khi thay đổi

Các lệnh dưới đây dùng **PowerShell và kubectl**. Thay tên namespace, label và Pod cho đúng môi trường của bạn. Các lệnh ở phần này chỉ đọc.

### 4.1. Xác định cluster, ứng viên và ServiceAccount

~~~powershell
$ns = "orders-lab"
$appSelector = "app=orders-worker"
$lockName = "orders-worker-leaders"

kubectl config current-context
kubectl get pods -n $ns -l $appSelector -o wide
kubectl get deployment orders-worker -n $ns -o jsonpath='{.spec.template.spec.serviceAccountName}'
~~~

Nếu template không chỉ rõ `serviceAccountName`, hãy kiểm tra Pod vì Pod thường sử dụng ServiceAccount `default`. Không lấy ServiceAccount trong một manifest cũ làm bằng chứng cho Pod đang chạy.

~~~powershell
$podName = "TEN_POD_THUC_TE"
kubectl get pod $podName -n $ns -o jsonpath='{.spec.serviceAccountName}'
kubectl get pod $podName -n $ns -o jsonpath='{.status.conditions}'
kubectl describe pod $podName -n $ns
~~~

Đọc nguyên nhân `Unhealthy`, `BackOff`, probe thất bại, container bị `OOMKilled` và các lần restart. Nếu container đã restart, lấy thêm log phiên trước của đúng container:

~~~powershell
kubectl logs $podName -n $ns -c app --previous --timestamps=true
~~~

Thay `app` bằng tên container ứng dụng. Nếu chưa có lần restart, kubectl có thể báo không có container trước đó; điều này không phải lỗi leader election.

### 4.2. Đọc khóa và log của mọi ứng viên

~~~powershell
kubectl get configmap $lockName -n $ns -o yaml

kubectl logs -n $ns -l $appSelector --all-containers=true --prefix=true --timestamps=true --since=15m --max-log-requests=10 |
    Select-String -Pattern 'leader|leadership|Forbidden|Unauthorized|Conflict|timeout|watch|SSL'
~~~

Nếu số replica lớn hơn giới hạn lấy log, chia nhóm Pod hoặc điều chỉnh `--max-log-requests` phù hợp. Dùng timestamp và tiền tố Pod để tránh ghép nhầm sự kiện của nhiều replica.

Đối chiếu từng replica theo mẫu:

| Pod | Image đang chạy | Candidate ID | Namespace khóa | Tên khóa | Role | Ready |
| --- | --- | --- | --- | --- | --- | --- |
| Pod A | Bản phát hành X | Tên Pod A | orders-lab | orders-worker-leaders | order-reconciliation | True |
| Pod B | Bản phát hành X | Tên Pod B | orders-lab | orders-worker-leaders | order-reconciliation | True |

Sai lệch giữa cấu hình dự kiến và cấu hình hiệu lực thường xuất hiện khi một replica còn chạy image cũ, profile khác hoặc biến môi trường ghi đè. Nếu phải xem cấu hình runtime, chỉ truy vấn thuộc tính cần thiết qua kênh quản trị được bảo vệ; không xuất toàn bộ Secret hoặc môi trường ra log.

### 4.3. Đọc mã lỗi theo thao tác thật

| Bằng chứng | Diễn giải cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `401 Unauthorized` | Token không có, không hợp lệ hoặc cấu hình client dùng credential sai | Kiểm tra cơ chế xác thực của Pod và cấu hình client |
| `403 Forbidden` | Credential được nhận nhưng thiếu quyền cho resource/verb/namespace đó | Sửa Role/RoleBinding đúng ServiceAccount |
| `404 NotFound` | Sai tên, sai namespace hoặc khóa chưa được tạo | Đối chiếu cấu hình và chính sách tạo khóa |
| `409 Conflict` thỉnh thoảng | Hai ứng viên cập nhật cùng phiên bản tài nguyên | Quan sát lần thử tiếp và kết quả bầu |
| `409` liên tục, không ổn định | Có cạnh tranh kéo dài hoặc tác nhân ngoài cùng sửa khóa | Kiểm tra các workload và GitOps/controller cùng ghi |
| Timeout, lỗi TLS, mất watch | Đường tới API, CA/proxy, tải API hoặc client cần kiểm tra | Phân biệt lỗi mạng với lỗi RBAC |

Một phản hồi xung đột đơn lẻ trong lúc nhiều replica khởi động không đủ để kết luận hệ thống hỏng. Ngược lại, operator đọc được ConfigMap bằng tài khoản quản trị không chứng minh ServiceAccount của ứng dụng có quyền tương tự.

## 5. Cấu hình nền cho Fabric8/ConfigMap

### 5.1. Khai báo thư viện và cấu hình leader

Dependency dưới đây giả định dự án đã quản lý phiên bản bằng Spring Cloud BOM tương thích với Spring Boot đang dùng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-kubernetes-fabric8-leader</artifactId>
</dependency>
~~~

Cấu hình tham chiếu cho cả ba replica:

~~~yaml
spring:
  application:
    name: orders-worker
  cloud:
    kubernetes:
      leader:
        enabled: true
        auto-startup: true
        namespace: orders-lab
        config-map-name: orders-worker-leaders
        role: order-reconciliation
        create-config-map: false
        update-period: 5s
        publish-failed-events: true

logging:
  level:
    org.springframework.cloud.kubernetes.fabric8.leader: DEBUG
    org.springframework.cloud.kubernetes.commons.leader: DEBUG
~~~

`5s` là giá trị phục vụ lab, cần đo trước khi chọn cho production. `publish-failed-events` hỗ trợ quan sát các lần thư viện phát sự kiện thất bại; không bảo đảm mọi lỗi client đều xuất hiện dưới dạng sự kiện đó.

Trong lớp thuộc tính 3.3.3, `enabled` và `auto-startup` mặc định bật, `config-map-name` mặc định là `leaders`, còn `update-period` mặc định là 60 giây. Đặt rõ giá trị giúp tránh hiểu nhầm giữa mặc định của thư viện và cấu hình triển khai. Xem [LeaderProperties 3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/LeaderProperties.java).

Cấu hình này chọn tạo khóa trước, nên `create-config-map: false`. Nếu ConfigMap chưa tồn tại, phải tạo trước khi mong chờ bầu được leader. Nếu ứng dụng được phép tự tạo, phải đổi cấu hình và cấp quyền `create` tương ứng.

Không mặc định rằng thay ConfigMap cấu hình sẽ tái tạo Kubernetes client, watcher và leader initiator đang chạy. Với thuộc tính ảnh hưởng vòng đời bầu leader, dùng phương án cập nhật được phiên bản hỗ trợ hoặc triển khai lại có kiểm soát, rồi xác minh trên từng replica.

### 5.2. Chuẩn bị ConfigMap và RBAC trong namespace lab

Manifest dưới đây là ví dụ có thể áp dụng trong namespace `orders-lab` đã tồn tại. Nó dùng ConfigMap chuyên biệt cho coordination, tách khỏi ConfigMap chứa cấu hình nghiệp vụ.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-worker
  namespace: orders-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-worker-leaders
  namespace: orders-lab
data: {}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orders-worker-leader
  namespace: orders-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["orders-worker-leaders"]
    verbs: ["get", "watch", "update"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orders-worker-leader
  namespace: orders-lab
subjects:
  - kind: ServiceAccount
    name: orders-worker
    namespace: orders-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: orders-worker-leader
~~~

Trong Pod template của Deployment:

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: orders-worker
      automountServiceAccountToken: true
~~~

Đoạn trên chỉ là phần cần ghép vào Deployment hiện có. Mẫu quyền này phục vụ ví dụ ConfigMap; không phải bộ quyền dùng chung cho discovery, đọc Secret hoặc native Lease.

Quyền `watch` có giới hạn `resourceNames` yêu cầu request watch gửi field selector tên tương ứng. Kiểm tra hành vi client đang dùng; nếu client thực hiện watch/list rộng hơn, quyền phải phù hợp với request thật. Khi cho ứng dụng tự tạo khóa, không đặt `create` vào một rule có `resourceNames` rồi cho rằng đã cấp được quyền tạo; Kubernetes không giới hạn top-level create theo tên theo cách đó. Xem [quy tắc RBAC về resourceNames](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#referring-to-resources).

Việc tạo ConfigMap rỗng ở trên dành cho lần khởi tạo lab. Khi GitOps quản lý resource này, cần để phần `data` do thư viện cập nhật được bảo toàn; không liên tục đồng bộ `data: {}` lên một khóa đang hoạt động.

### 5.3. Kiểm tra quyền theo đúng danh tính

Các lệnh giả lập danh tính bên dưới yêu cầu tài khoản operator có quyền impersonate. Nếu bị từ chối impersonation, chưa thể kết luận ServiceAccount thiếu quyền thao tác khóa.

~~~powershell
$saName = "orders-worker"
$saSubject = "system:serviceaccount:$($ns):$saName"

kubectl auth can-i get "configmaps/$lockName" -n $ns --as=$saSubject
kubectl auth can-i update "configmaps/$lockName" -n $ns --as=$saSubject
kubectl auth can-i watch "configmaps/$lockName" -n $ns --as=$saSubject
kubectl auth can-i get "pods/$podName" -n $ns --as=$saSubject
kubectl auth can-i list pods -n $ns --as=$saSubject
kubectl auth can-i watch pods -n $ns --as=$saSubject
~~~

Để kiểm tra đường watch giới hạn tên trong lab:

~~~powershell
kubectl get configmaps -n $ns --as=$saSubject --field-selector="metadata.name=$lockName" --watch --request-timeout=15s
~~~

Lệnh kết thúc do hết `request-timeout` sau khoảng quan sát không đồng nghĩa bị từ chối quyền. Quan sát lỗi `Forbidden` riêng. Nếu cấu hình cho phép tự tạo khóa, kiểm tra thêm:

~~~powershell
kubectl auth can-i create configmaps -n $ns --as=$saSubject
~~~

Trong mẫu tạo khóa trước, kết quả `no` cho quyền create là bình thường. Cũng không cần cấp `cluster-admin` hoặc quyền đọc Secret để giải quyết lỗi cập nhật ConfigMap leader.

## 6. Pod Running nhưng không có leader: kiểm tra readiness

### 6.1. Loại bỏ vòng chờ giữa readiness và leadership

Một thiết kế dễ gây bế tắc:

~~~text
readiness chỉ UP khi đã là leader
        ↓
mọi Pod follower đều NotReady
        ↓
implementation yêu cầu ứng viên Ready mới nhận leadership
        ↓
không Pod nào trở thành leader
~~~

Thiết kế phù hợp hơn cho workload này:

- Readiness thể hiện ứng dụng đã khởi tạo và đủ khả năng tham gia công việc.
- Replica follower vẫn có thể Ready khi đang chờ đến lượt.
- Trạng thái leader được quan sát riêng và dùng để cho phép chạy tác vụ chủ động.
- Nếu có API chỉ leader được nhận traffic, thiết kế đường định tuyến riêng, không buộc readiness của mọi ứng viên phụ thuộc vào việc đã thắng bầu.

Đây là suy luận từ yêu cầu Ready của implementation tham chiếu. Không tắt kiểm tra sức khỏe một cách máy móc để vượt qua vòng chờ.

### 6.2. Dùng probe đúng mục đích

Ví dụ nếu ứng dụng đã cấu hình Spring Boot Actuator và các endpoint probe trên cổng 8080:

~~~yaml
containers:
  - name: app
    startupProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 5
      failureThreshold: 24
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      failureThreshold: 3
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 10
      failureThreshold: 3
~~~

Đây là fragment của container, cần ghép thêm image và các trường triển khai cần thiết. Nếu management port hoặc đường dẫn khác, sửa probe tương ứng. Kiểm tra security của endpoint để kubelet không nhận `401/403` ngoài ý muốn.

Readiness thất bại ảnh hưởng việc Pod được dùng làm endpoint sẵn sàng. Liveness thất bại đủ ngưỡng có thể dẫn tới restart container; startup probe cho ứng dụng thời gian khởi tạo trước khi các probe còn lại chạy. Xem [hướng dẫn probe của Kubernetes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Với ứng dụng có khởi động dài, probe quá gắt có thể tạo chuỗi restart khiến ứng viên không bao giờ ổn định. Với readiness liên tục đổi True/False, kiểm tra cả dependency được gộp vào health group và việc thiếu CPU/bộ nhớ.

### 6.3. Kiểm tra namespace client và định danh Pod

Trong mã tham chiếu, đọc khóa có thể dùng `leader.namespace`, trong khi các thao tác kiểm tra/watch Pod đi theo namespace của Kubernetes client. Chỉ đổi namespace khóa không bảo đảm mọi thao tác Pod đi sang namespace đó.

Giữ ứng viên, client namespace và khóa trong cùng namespace cho ví dụ này. Khi tùy biến client hoặc chạy qua nhiều namespace, đối chiếu từng request và quyền thực tế. Không chữa lỗi bằng cách cấp quyền toàn cluster trước khi biết client đang nhìn Pod nào.

Nếu candidate ID không trùng tên Pod có thể đọc được, kiểm tra cấu hình hostname và các tùy biến candidate. Một tên hợp lệ trong log JVM chưa đủ để API tìm thấy đúng Pod.

## 7. Đã bầu được leader nhưng công việc vẫn không chạy

Kiểm tra độc lập hai câu hỏi: JVM có nhận sự kiện hay chưa, và tác vụ có được kích hoạt khi nhận sự kiện hay chưa.

Với cơ chế truyền thống, có thể quan sát `OnGrantedEvent` và `OnRevokedEvent`. Spring Integration cung cấp `Context` với `isLeader()` và `yield()`. Xem [Leadership Event Handling](https://docs.spring.io/spring-integration/reference/leadership-event-handling.html).

Ví dụ dưới đây chỉ minh họa cách chặn một scheduler ở cấp JVM và ghi log. Ứng dụng phải bật `@EnableScheduling` trên một lớp cấu hình hoặc lớp ứng dụng.

~~~java
package example.orders;

import java.util.concurrent.atomic.AtomicReference;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.integration.leader.Context;
import org.springframework.integration.leader.event.OnGrantedEvent;
import org.springframework.integration.leader.event.OnRevokedEvent;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class LeaderOnlyJob {

    private static final Logger log =
            LoggerFactory.getLogger(LeaderOnlyJob.class);
    private static final String ROLE = "order-reconciliation";

    private final AtomicReference<Context> leadership =
            new AtomicReference<>();

    @EventListener
    public void onGranted(OnGrantedEvent event) {
        if (ROLE.equals(event.getRole())) {
            leadership.set(event.getContext());
            log.info("leader_granted role={}", event.getRole());
        }
    }

    @EventListener
    public void onRevoked(OnRevokedEvent event) {
        if (ROLE.equals(event.getRole())) {
            leadership.set(null);
            log.info("leader_revoked role={}", event.getRole());
        }
    }

    @Scheduled(fixedDelayString = "5000")
    public void tick() {
        Context context = leadership.get();
        if (context == null || !context.isLeader()) {
            return;
        }
        log.info("leader_work_tick role={}", ROLE);
        // Gọi một đơn vị công việc nhỏ, có idempotency ở đây.
    }
}
~~~

Mẫu giả định sự kiện được phân phối theo thứ tự mặc định và chỉ có nhóm election tương ứng trong application context. Nếu tùy biến event multicaster bất đồng bộ hoặc có nhiều initiator, phải xử lý thứ tự và định danh nguồn sự kiện rõ ràng.

Khi chẩn đoán, kiểm tra:

1. Component listener có được scan và thuộc application context đúng không?
2. Role trong code có khớp cấu hình runtime không?
3. Bạn đang nghe đúng loại sự kiện của implementation không?
4. Scheduler có được bật, executor có nghẽn hoặc task có ném lỗi không?
5. Log `leader_work_tick` có xuất hiện trên đúng Pod nhận leadership không?

Đừng chạy tác vụ dài, gọi API chậm hoặc chờ database ngay trong listener. Listener nên cập nhật trạng thái hoặc chuyển lệnh sang executor có kiểm soát để không kéo dài đường xử lý leadership.

Nếu dùng Actuator của nhánh có leader info contributor, có thể kiểm tra `/actuator/info` trên **từng Pod** qua kênh quản trị phù hợp. Truy cập qua Service cân bằng tải có thể trả về replica khác nhau giữa các lần gọi. Không mở công khai endpoint quản trị chỉ để chẩn đoán.

## 8. Chuyển giao chậm: đo khoảng gián đoạn trước khi giảm thời gian

### 8.1. Chia thời gian thành các mốc

Ghi ít nhất các thời điểm sau:

| Mốc | Ý nghĩa |
| --- | --- |
| `t0` | Leader cũ hoàn tất đơn vị công việc cuối trước sự cố |
| `t1` | Lỗi được đưa vào hoặc có bằng chứng leader cũ không còn khả dụng |
| `t2` | Một ứng viên nhận leadership |
| `t3` | Leader mới bắt đầu đơn vị công việc đầu tiên |

Hai đại lượng phục vụ hai mục tiêu khác nhau:

~~~text
Thời gian tiếp quản sau lỗi = t2 - t1
Khoảng gián đoạn xử lý      = t3 - t0
~~~

Nếu `t2 - t1` nhỏ nhưng `t3 - t2` lớn, hãy tìm scheduler/executor, khởi tạo tài nguyên hoặc dependency nghiệp vụ. Chỉnh vòng bầu leader không giải quyết được đoạn trễ đó.

Ví dụ minh họa: sự cố xảy ra lúc 10:00:00, leader mới nhận vai trò lúc 10:00:03, nhưng scheduler đến 10:00:08 mới bắt đầu lượt tiếp theo. Trễ khởi động tác vụ chiếm năm giây; không nên quy toàn bộ tám giây cho Kubernetes API.

### 8.2. Với cơ chế ConfigMap truyền thống

`update-period` là chu kỳ kiểm tra, không phải TTL. Implementation còn có watch ConfigMap và watch readiness của Pod; watch có thể kích hoạt kiểm tra sớm hơn lịch định kỳ. Xem [LeaderRecordWatcher](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeaderRecordWatcher.java) và [PodReadinessWatcher](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8PodReadinessWatcher.java).

Lịch kiểm tra định kỳ của bản tham chiếu có lần chạy đầu sau một `update-period`; khi dừng lifecycle, initiator đóng watcher và gọi thu hồi leadership. Điều này giúp giải thích một phần trễ khởi động hoặc khác biệt giữa dừng êm và chết đột ngột. Xem [LeaderInitiator 3.3.3](https://github.com/spring-cloud/spring-cloud-kubernetes/blob/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/LeaderInitiator.java).

Khi chuyển giao chậm, lần lượt kiểm tra:

- Pod dự phòng có Ready từ trước không, hay vẫn cần khởi động?
- Watch có bị đóng, mất kết nối hoặc lặp lỗi không?
- Client còn đọc/cập nhật API được không?
- Pod leader cũ đã được API phản ánh là không còn sẵn sàng chưa?
- Công việc có chờ đến lượt scheduler tiếp theo mới chạy không?

Khi mất cả node, việc Kubernetes phát hiện tình trạng Pod cũng có thể là phần đáng kể của khoảng gián đoạn. Không lấy thời điểm bấm xóa Pod làm phép đo cho mọi loại lỗi hạ tầng.

Sau khi xác nhận nguyên nhân là chờ kiểm tra định kỳ, có thể thử giảm `update-period` trong lab. So sánh thời gian tiếp quản và số request API trước/sau. Nhiều replica với chu kỳ ngắn làm tăng tải đọc trạng thái và cạnh tranh ghi; không đặt chu kỳ cực ngắn chỉ để đạt một lần đo đẹp.

### 8.3. Với cơ chế native dùng Lease

Chỉ dùng các thuộc tính bên dưới khi đã xác nhận phiên bản và implementation hỗ trợ. Ví dụ cấu hình native riêng biệt:

~~~yaml
spring:
  cloud:
    kubernetes:
      leader:
        election:
          enabled: true
          lock-name: orders-worker-native-lock
          lock-namespace: orders-lab
          wait-for-pod-ready: true
          publish-events: true
          retry-period: 2s
          renew-deadline: 10s
          lease-duration: 15s
~~~

Các giá trị thời gian trên có trong [phụ lục thuộc tính Spring Cloud Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html). Đây là ví dụ để hiểu nhóm cấu hình native, không thay thế cấu hình ConfigMap của các phần trước.

`retry-period` liên quan nhịp thử lại, `renew-deadline` là khoảng chịu đựng thất bại gia hạn ở leader, còn `lease-duration` ảnh hưởng thời gian bên cạnh tranh chờ bản ghi hết hiệu lực. Không coi `renew-deadline` là thời gian chết tối đa của hệ thống.

Giữ `lease-duration > renew-deadline > retry-period` và kiểm tra ràng buộc bổ sung của client, gồm hệ số jitter nếu có. Đừng chỉ so ba con số: cần đủ dư địa cho độ trễ API, thời gian GC, CPU throttling và gián đoạn mạng.

Nếu runtime thực sự chọn Lease, đọc tài nguyên tương ứng:

~~~powershell
$nativeLockName = "orders-worker-native-lock"

kubectl get lease $nativeLockName -n $ns -o yaml
kubectl describe lease $nativeLockName -n $ns
~~~

Quan sát `holderIdentity`, `renewTime`, `leaseDurationSeconds`, `leaseTransitions` và log của ứng viên. Kubernetes dùng Lease trong nhiều cơ chế coordination; một Lease có tên gần giống ứng dụng chưa đủ chứng minh nó thuộc vòng election đang điều tra. Xem [Lease trong Kubernetes](https://kubernetes.io/docs/concepts/architecture/leases/).

RBAC cho Lease thuộc API group `coordination.k8s.io`, resource `leases`. Quyền ConfigMap không bao gồm Lease. Cấp quyền theo request thật; nếu client tự tạo Lease, cần quyền create phù hợp. Khi chọn ConfigMap làm native lock, quay lại kiểm tra đúng loại tài nguyên đó.

Mẫu listener của phần 7 không dùng cho các sự kiện native. Khi chuyển implementation, phải chuyển đồng bộ cấu hình, quyền, listener và chiến lược rollout. Không để hai nhóm dùng hai khóa độc lập cùng thực thi một tác vụ trong giai đoạn chuyển đổi.

## 9. Bầu được leader không bảo đảm tác vụ không chạy trùng

Kiểm tra `isLeader()` chỉ phản ánh trạng thái được JVM biết tại thời điểm đọc. Leadership có thể bị mất sau phép kiểm tra nhưng trước khi transaction hoặc HTTP request hoàn tất.

Tài liệu thư viện leader election của Kubernetes cũng phân biệt election với bảo đảm fencing. Không được suy ra rằng có một bản ghi khóa thì mọi tác động ngoài hệ thống tự động chỉ xảy ra một lần. Xem [ghi chú về fencing của client-go](https://pkg.go.dev/k8s.io/client-go/tools/leaderelection). Đây là nguyên lý cần xét khi thiết kế tác vụ; không có nghĩa ứng dụng Spring trong bài sử dụng client-go.

Với bài toán đối soát đơn hàng, có thể thiết kế:

- Mỗi lượt xử lý mang khóa idempotency ổn định, chẳng hạn `orderId + reconciliationPeriod`.
- Database dùng unique constraint hoặc cập nhật có điều kiện để nhận quyền xử lý.
- API ngoài hỗ trợ idempotency key nếu có tác động không thể lặp.
- Công việc dài chia thành đơn vị nhỏ và kiểm tra trạng thái trước khi nhận thêm đơn vị.
- Khi mất leadership, ngừng nhận việc mới và hủy phần việc có thể hủy an toàn.
- Nếu cần fencing, tài nguyên đích phải từ chối thao tác mang token cũ; token cần được thiết kế có thứ tự phù hợp.

Không tự dùng `metadata.resourceVersion` như số tăng toàn cục cho fencing nghiệp vụ. Không tự chế token chỉ bằng timestamp của từng Pod rồi coi là đã có thứ tự tin cậy.

Tín hiệu cần quan sát là số tác động nghiệp vụ duy nhất và số lần thử bị loại vì trùng. Một lần thấy `leader_revoked` trong log không chứng minh tác vụ cũ đã dừng hoàn toàn.

## 10. Thực hành có kiểm soát với nhiều replica

Chuẩn bị một namespace lab, ít nhất hai replica đủ tài nguyên, các probe đúng và tác vụ ghi log hoặc tác động có thể lặp an toàn. Đặt mục tiêu thời gian tiếp quản trước khi thử; con số mục tiêu thuộc hệ thống của bạn.

### 10.1. Xác minh trạng thái ổn định

1. Kiểm tra tất cả ứng viên Ready và cấu hình nhóm cạnh tranh giống nhau.
2. Đọc ConfigMap, ghi nhận Pod giữ role `order-reconciliation`.
3. Kiểm tra chỉ Pod tương ứng phát `leader_work_tick` trong một khoảng quan sát.
4. Xác minh các follower vẫn Ready và không chạy phần nghiệp vụ dành cho leader.

Trong một terminal quan sát thay đổi khóa:

~~~powershell
kubectl get configmap $lockName -n $ns --watch
~~~

Trong terminal khác, theo dõi log từng Pod hoặc log tập hợp có timestamp. Giá trị cần so sánh là sự thay đổi chủ khóa và sự kiện tương ứng; `resourceVersion` đổi một mình chưa nói được ai đang xử lý.

### 10.2. Thử dừng có thời gian graceful

Sau khi xác định đúng Pod leader, chỉ trong lab:

~~~powershell
$leaderPod = "TEN_POD_LEADER_DA_XAC_MINH"
kubectl delete pod $leaderPod -n $ns --wait=false
~~~

Lệnh này gây thay đổi workload; Deployment sẽ tạo Pod thay thế theo cấu hình. Có grace period không có nghĩa mọi cleanup đều kịp hoàn thành. Đo `t1`, `t2`, `t3` từ bằng chứng thực tế và kiểm tra Pod dự phòng tiếp quản.

Kubernetes có quá trình dừng Pod với thời gian grace; hook `preStop` cũng tiêu thụ thời gian trong ngân sách dừng. Nếu process không kết thúc kịp, việc dừng cưỡng bức có thể xảy ra. Xem [quá trình kết thúc Pod](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination).

### 10.3. Tách riêng các nhóm lỗi

| Thử nghiệm trong lab | Cách tạo tình huống | Kết quả cần quan sát |
| --- | --- | --- |
| Thiếu quyền cập nhật khóa | Dùng bộ Role lab thiếu update | Lỗi 403 chỉ ra đúng resource, verb và danh tính |
| Không có ứng viên Ready | Cấu hình probe lab không đạt | Không nhận leadership; thấy nguyên nhân probe |
| Sai nhóm khóa | Cho một replica dùng role hoặc tên khóa khác | Bằng chứng cho thấy hai nhóm cạnh tranh riêng |
| Lỗi đường watch | Dùng cơ chế giả lập mạng có kiểm soát | Log watch/client và thay đổi độ trễ tiếp quản |
| Tác vụ chậm sau grant | Tăng độ trễ scheduler/executor của lab | `t2` sớm nhưng `t3` muộn |
| Leader chết không cleanup | Dùng fault injection được môi trường lab hỗ trợ | Phân biệt với lần dừng graceful |

Không dùng `kubectl delete --force --grace-period=0` làm bằng chứng rằng process trên node đã dừng. Xóa nhanh đối tượng API và chấm dứt tiến trình thực tế là hai điều cần xác minh riêng.

Mỗi lần chỉ thay một yếu tố, ghi lại kết quả rồi phục hồi cấu hình lab. Chạy lại tình huống ổn định để chắc chắn quyền, probe và tên khóa đã trở về trạng thái mong muốn.

## 11. Runbook khi gặp sự cố thật

| Thứ tự | Việc làm | Điều kiện để chuyển bước |
| --- | --- | --- |
| 1 | Chốt implementation, phiên bản, nhóm khóa và scope nghiệp vụ | Biết đọc ConfigMap hay Lease, biết listener nào đúng |
| 2 | Kiểm tra số ứng viên Ready và trạng thái restart | Có ứng viên thực sự đủ điều kiện tiếp quản |
| 3 | Đối chiếu ServiceAccount, namespace client và namespace khóa | Biết danh tính/request cần kiểm quyền |
| 4 | Ghép mã lỗi API với log election trên mọi Pod | Có nguyên nhân cụ thể hoặc đã loại nhóm lỗi truy cập |
| 5 | Kiểm tra grant/revoke và việc kích hoạt scheduler | Tách được lỗi bầu leader khỏi lỗi tác vụ |
| 6 | Đo các mốc chuyển giao và gián đoạn xử lý | Biết đoạn trễ nào chi phối |
| 7 | Sửa cấu hình/quyền đúng phạm vi và thử lại | Hành vi ổn định, đáp ứng mục tiêu đã đặt |
| 8 | Kiểm tra tác động lặp, cleanup và rollout | Không còn xử lý ngoài thiết kế khi đổi leader |

Nếu phát hiện bản ghi trỏ tới Pod cũ, giữ lại bằng chứng và xác định leader cũ còn có thể chạy nghiệp vụ hay không. Không bắt đầu bằng xóa hoặc sửa tay khóa: ứng viên cũ còn sống có thể tiếp tục làm việc trong khi ứng viên khác nhận vai trò.

Tương tự, không bật thêm DiscoveryClient, LoadBalancer hay Configuration Watcher để thử chữa lỗi bầu leader. Với mỗi thay đổi, nêu rõ thao tác hoặc điều kiện nào sẽ được sửa và log nào chứng minh hiệu quả.

## 12. Tiêu chí kết thúc chẩn đoán và chọn tính năng cần dùng

Có thể coi lần khắc phục đạt yêu cầu vận hành khi:

- Nhận diện được một nhóm cạnh tranh duy nhất cho tác vụ cần một leader.
- Các follower đủ điều kiện tiếp quản mà không mắc vòng chờ readiness.
- Không còn lỗi quyền/xác thực/truy cập API chưa giải thích.
- Sự kiện lifecycle và việc chạy/dừng tác vụ khớp trên từng Pod.
- Khoảng tiếp quản và khoảng gián đoạn xử lý đạt mục tiêu qua các tình huống đã thử.
- Có cơ chế bảo vệ tác động nghiệp vụ khi chuyển giao hoặc thử lại.
- Quy trình rollout không tạo hai nhóm leader độc lập cùng xử lý một nhiệm vụ.

Leader election phù hợp với worker hoặc bộ điều phối chủ động có các replica chờ dự phòng. Nếu ứng dụng chỉ phục vụ HTTP độc lập, hãy xác định có thật sự cần một leader hay không. Nếu nhu cầu là một tác vụ chạy theo lịch, có thể đánh giá Kubernetes CronJob cùng yêu cầu chống trùng và phục hồi của tác vụ. Chỉ đưa thêm thành phần Spring Cloud Kubernetes khi nó giải quyết một yêu cầu cụ thể của triển khai.
