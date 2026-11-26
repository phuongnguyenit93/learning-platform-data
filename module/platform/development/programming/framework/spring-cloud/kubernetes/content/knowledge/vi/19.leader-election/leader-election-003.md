# Điều kiện hỗ trợ theo Kubernetes client và bản phát hành

Trong chương **Bầu leader** của module **SPRING_CLOUD_KUBERNETES**, câu hỏi “Spring Cloud Kubernetes có hỗ trợ leader election không?” cần được trả lời bằng một tổ hợp cụ thể: **bản phát hành, Kubernetes client, module trên classpath, cơ chế bầu leader và môi trường chạy**.

Một ứng dụng đã dùng DiscoveryClient, ConfigMap hoặc Secret không mặc nhiên có cơ chế bầu leader tương ứng. Ngược lại, việc Kubernetes cluster có tài nguyên Lease cũng chưa chứng minh ứng dụng Spring đã có implementation sử dụng Lease.

Bài học tập trung vào cách xác định khả năng hỗ trợ và chọn cấu hình đúng. Các phiên bản trong bảng là các tag cụ thể được đối chiếu; chúng không đại diện cho mọi patch của cùng một nhánh và không phải danh sách phiên bản nên nâng cấp đồng loạt.

## 1. Tình huống: ba replica, một tác vụ điều phối

Giả sử `invoice-worker` chạy ba replica trong namespace `lab`. Tất cả replica có thể phục vụ kiểm tra sức khỏe, nhưng chỉ một replica được chủ động phát công việc tổng hợp hóa đơn tại một thời điểm.

Nhóm dự án đang gặp một trong các tình huống:

- Ứng dụng dùng Fabric8 ở một bản Spring Cloud Kubernetes cũ và có listener `OnGrantedEvent`.
- Ứng dụng dùng Kubernetes Java Client chính thức, nhưng dependency chỉ phục vụ discovery/configuration.
- Dự án mới hơn có cơ chế leader election dựa trên API của client, nhưng chưa bật đúng cờ hoặc vẫn nghe sự kiện cũ.
- Trong quá trình nâng cấp, một nhóm Pod sử dụng ConfigMap, nhóm còn lại sử dụng Lease.

Các tình huống có biểu hiện giống nhau như “không thấy leader” hoặc “hai Pod đều làm việc”, nhưng cách xử lý khác nhau. Cần xác định implementation trước khi chỉnh RBAC hoặc giảm thời gian retry.

## 2. Phân biệt ba lớp hỗ trợ

| Lớp | Điều cần xác định | Ví dụ kết luận sai nếu bỏ qua |
| --- | --- | --- |
| Thư viện Kubernetes client | Fabric8 hay Kubernetes Java Client chính thức? Có API leader election nào? | Client có thuật toán nên Spring chắc chắn đã tích hợp |
| Spring Cloud Kubernetes | Release đó có module, auto-configuration và sự kiện tương ứng không? | Discovery chạy được thì leader cũng đã được bật |
| Kubernetes và môi trường triển khai | Lock API có sẵn, danh tính/quyền/mạng/readiness có đáp ứng không? | Cluster có Lease thì ứng dụng chắc chắn được ghi Lease |

Trong bài, “cơ chế native của client” nghĩa là sử dụng khả năng bầu leader do Kubernetes client cung cấp. Từ **native** ở đây không phải tuyên bố về hỗ trợ GraalVM native image hoặc Spring AOT; các khả năng đó cần được kiểm tra riêng theo release.

Các tên cũng cần tách rõ:

- `spring-cloud-kubernetes-fabric8-*`: nhóm tích hợp sử dụng Fabric8.
- `spring-cloud-kubernetes-client-*`: nhóm tích hợp sử dụng Kubernetes Java Client chính thức.
- Spring Cloud release train/BOM: tập phiên bản được quản lý cho các thành phần Spring Cloud.
- Phiên bản Spring Cloud Kubernetes: phiên bản của riêng dự án này, chẳng hạn `3.3.3` hoặc `5.1.0`.

Không dùng số phiên bản của một thành phần làm số phiên bản cho tất cả thành phần còn lại. Chọn bộ Spring Boot/Spring Cloud theo [bảng tương thích chính thức](https://spring.io/projects/spring-cloud/) và để BOM quản lý các module tương ứng.

## 3. Bảng đối chiếu theo các tag cụ thể

Có hai họ triển khai cần nhận diện:

- **Cơ chế Fabric8 cũ:** tích hợp API leader của Spring Integration, lưu thông tin trong ConfigMap, phát `OnGrantedEvent` và `OnRevokedEvent`.
- **Cơ chế dựa trên leader election của client:** có đường tích hợp cho Fabric8 và Kubernetes Java Client ở các tag mới hơn được đối chiếu, dùng nhóm thuộc tính `leader.election` và các sự kiện khác.

| Tag Spring Cloud Kubernetes | Fabric8 | Kubernetes Java Client chính thức | Kết luận sử dụng |
| --- | --- | --- | --- |
| `3.3.3` | Có module leader theo cơ chế cũ | Không có module `spring-cloud-kubernetes-client-leader` trong tập module của tag này | Không ghép ví dụ native mới vào ứng dụng `3.3.3` chỉ bằng cách thêm thuộc tính |
| `5.0.0` | Tài liệu theo tag vẫn trình bày cơ chế cũ | Tập module theo tag chưa có module client-leader | Không suy rằng mọi bản `5.0.x` có cùng khả năng |
| `5.0.5` | Tài liệu có cả đường cũ và đường native | Có module client-leader và tài liệu mô tả đường native | Chọn đúng implementation và cờ kích hoạt của tag |
| `5.1.0` | Có auto-configuration cho đường cũ và native | Có auto-configuration cho native | Kiểm tra điều kiện kích hoạt; không trộn listener của hai đường |

Căn cứ cho hai hàng đầu là [tài liệu leader của tag 3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/docs/modules/ROOT/pages/leader-election.adoc), [danh sách module 3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/pom.xml), [tài liệu tag 5.0.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.0.0/docs/modules/ROOT/pages/leader-election.adoc) và [danh sách module 5.0.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.0.0/pom.xml).

Với `5.0.5`, đối chiếu [tài liệu theo tag](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.0.5/docs/modules/ROOT/pages/leader-election.adoc) cùng [danh sách module](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.0.5/pom.xml). Với `5.1.0`, có thể xem trực tiếp [imports của module client-leader](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.1.0/spring-cloud-kubernetes-client-leader/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports) và [imports của module Fabric8 leader](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.1.0/spring-cloud-kubernetes-fabric8-leader/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports).

Bảng không xác định patch đầu tiên giới thiệu từng tính năng. Một capability hiện diện trong `5.0.5` không phải bằng chứng rằng nó đã tồn tại trong `5.0.0`. Tương tự, việc Spring Cloud Kubernetes ở một tag chưa có module tích hợp không có nghĩa thư viện Kubernetes Java Client bên dưới hoàn toàn không có API bầu leader; tự tích hợp API đó là một phạm vi triển khai khác.

## 4. Dependency cần khớp client và implementation

### 4.1. Fabric8

Module leader được tài liệu chỉ định:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-kubernetes-fabric8-leader</artifactId>
</dependency>
```

Ở các tag có cả hai đường, cùng module Fabric8 có thể chứa auto-configuration cũ và native. Vì vậy, chỉ nhìn tên artifact chưa xác định được cơ chế đang chạy; cần xem điều kiện cấu hình và bean thực tế.

### 4.2. Kubernetes Java Client chính thức ở tag có module tương ứng

Ví dụ module của tag `5.1.0`:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-kubernetes-client-leader</artifactId>
</dependency>
```

Artifact này là module leader, không nên tự bịa tên starter bằng cách thêm tiền tố `spring-cloud-starter-`. POM của [client-leader 5.1.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.1.0/spring-cloud-kubernetes-client-leader/pom.xml) cũng cho thấy Actuator là dependency tùy chọn; đừng giả định thêm module leader sẽ tự mang đầy đủ web server, endpoint sức khỏe và cấu hình probe cho ứng dụng.

Các đoạn XML bỏ phiên bản riêng vì giả định dự án đã có bộ dependency management tương thích. Nếu BOM hiện tại chưa quản lý artifact cần dùng, hãy xác định đúng release train hỗ trợ trước; đừng lấy một JAR leader mới rồi chèn vào nền Spring Boot/Spring Framework cũ để thử vận may.

### 4.3. Không kéo hai họ client chỉ để tránh chọn

Thêm cả hai họ client có thể tạo các bean hoặc auto-configuration ngoài dự kiến. Với tác vụ của bài, chọn một đường tích hợp leader, xác định dependency trực tiếp và các dependency bắc cầu.

Một DiscoveryClient gọi qua HTTP tới discovery server cũng không tự chứng minh ứng dụng có bean `ApiClient` hoặc `KubernetesClient` in-cluster. Khả năng discovery và khả năng bầu leader phải được đánh giá riêng.

Trong dự án thực tế, có thể dùng báo cáo dependency của build tool để ghi lại phiên bản đã resolve. Với Maven, ví dụ lệnh kiểm tra sau dành cho người học chạy trong dự án của họ:

```powershell
mvn dependency:tree '-Dincludes=org.springframework.cloud:*,io.fabric8:*,io.kubernetes:*'
```

Kết quả cần tìm là phiên bản module leader, họ client và sự nhất quán với BOM; không chỉ sự hiện diện của một artifact chứa chữ `kubernetes`.

## 5. Có dependency vẫn chưa đủ: điều kiện auto-configuration

Khi điều tra hỗ trợ, cần kiểm tra cả điều kiện kích hoạt bean. Ví dụ, mã nguồn native tại tag `5.1.0` yêu cầu:

| Đường tích hợp | Bean client cần có | Điều kiện môi trường và cờ |
| --- | --- | --- |
| Fabric8 native | `io.fabric8.kubernetes.client.KubernetesClient` | Nhận diện Kubernetes, điều kiện leader election được bật |
| Kubernetes Java Client native | `io.kubernetes.client.openapi.ApiClient` | Nhận diện Kubernetes, điều kiện leader election được bật |

Các điều kiện nằm trong [Fabric8LeaderElectionAutoConfiguration](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.1.0/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/election/Fabric8LeaderElectionAutoConfiguration.java) và [KubernetesClientLeaderElectionAutoConfiguration](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.1.0/spring-cloud-kubernetes-client-leader/src/main/java/org/springframework/cloud/kubernetes/client/leader/election/KubernetesClientLeaderElectionAutoConfiguration.java).

Nếu ứng dụng chạy ngoài cluster, điều kiện cloud platform có thể không khớp. Ép `spring.main.cloud-platform=KUBERNETES` trong một bài thử chỉ thay cách nhận diện môi trường; nó không tạo cluster, token, CA, quyền RBAC hay kết nối mạng.

### 5.1. Phân biệt cờ cũ và cờ mới

| Cấu hình | Ý nghĩa cần kiểm tra |
| --- | --- |
| `spring.cloud.kubernetes.leader.enabled` | Cờ của đường Fabric8 cũ |
| `spring.cloud.kubernetes.leader.election.enabled` | Cờ kích hoạt đường native ở các release có triển khai tương ứng |
| `spring.cloud.kubernetes.configuration.watcher.ha.enabled` | Cờ HA riêng của Configuration Watcher; tại tag `5.1.0` cũng kích hoạt hạ tầng native leader election |

Ở tag `5.1.0`, auto-configuration Fabric8 cũ có điều kiện đường native đang tắt. Điều này giúp chọn implementation trong một ứng dụng; nó không điều phối các Pod khác đang chạy bản cũ. Xem [Fabric8LeaderAutoConfiguration](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.1.0/spring-cloud-kubernetes-fabric8-leader/src/main/java/org/springframework/cloud/kubernetes/fabric8/leader/Fabric8LeaderAutoConfiguration.java).

Cũng tại tag này, điều kiện bật native là một điều kiện OR giữa cờ native và cờ HA của Watcher. Vì vậy, không dùng riêng `leader.enabled=false` để kết luận mọi cơ chế bầu leader đều đã tắt. Xem [ConditionalOnLeaderElectionEnabled](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.1.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/election/ConditionalOnLeaderElectionEnabled.java).

Một thuộc tính lạ có thể nằm trong Environment mà không có implementation tiêu thụ nó. Việc ứng dụng khởi động thành công sau khi thêm `leader.election.enabled=true` vào một release cũ không chứng minh tính năng đã được kích hoạt.

### 5.2. Hiện diện tính năng và vòng đời hỗ trợ là hai câu hỏi

Bảng tính năng theo tag cho biết có implementation nào để đối chiếu. Trước khi chọn bản cho một hệ thống vận hành lâu dài, còn phải kiểm tra vòng đời hỗ trợ của Spring Boot/Spring Cloud và trạng thái tính năng trong tài liệu của release đó.

Ví dụ tài liệu theo tag `5.1.0` mô tả đường native mới theo tinh thần preview. Đây là mô tả mức trưởng thành của tính năng, không phải yêu cầu bật `--enable-preview` của Java. Đừng suy rằng mọi đường triển khai trong một artifact phát hành đều có cùng lịch sử vận hành và cùng hợp đồng tương thích. Xem [tài liệu leader election của tag 5.1.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.1.0/docs/modules/ROOT/pages/leader-election.adoc).

## 6. Cấu hình của hai cơ chế không thay thế cho nhau

### 6.1. Ví dụ cho cơ chế Fabric8 cũ

Ví dụ lựa chọn nhóm leader ở tag `3.3.3`:

```yaml
spring:
  application:
    name: invoice-worker
  cloud:
    kubernetes:
      leader:
        enabled: true
        namespace: lab
        role: invoice-dispatch
        config-map-name: invoice-leaders
```

Nhóm thuộc tính cũ gồm namespace, role và tên ConfigMap. Các giá trị cùng với cách lưu record của implementation xác định miền cạnh tranh leader. Đối chiếu [LeaderProperties 3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/LeaderProperties.java).

Đây là ví dụ chọn cơ chế và nhóm cạnh tranh, chưa thay thế các điều kiện client, xác thực và RBAC. Nếu listener nghiệp vụ đang dùng API Spring Integration, phải kiểm tra nó nhận đúng sự kiện cấp/thu hồi quyền của đường này.

### 6.2. Ví dụ cho cơ chế native tại tag 5.1.0

Chọn **một** trong hai module leader tương ứng với client ở phần 4. Với biến thể thực hành native, cấu hình có thể là:

```yaml
spring:
  application:
    name: invoice-worker
  cloud:
    kubernetes:
      config:
        enabled: false
      secrets:
        enabled: false
      discovery:
        enabled: false
      leader:
        enabled: false
        election:
          enabled: true
          lock-namespace: lab
          lock-name: invoice-dispatcher
          use-config-map-as-lock: false
          wait-for-pod-ready: true
          publish-events: true
          lease-duration: 20s
          renew-deadline: 12s
          retry-period: 3s

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
```

`leader.enabled=false` thể hiện rõ rằng ví dụ không chọn đường Fabric8 cũ. Cờ native vẫn bật theo nhóm `leader.election`; hai dòng không mâu thuẫn.

Các giá trị thời gian là ví dụ, không phải cấu hình tối ưu cho mọi cluster. Giữ quan hệ thời gian phù hợp với yêu cầu của client, tính độ trễ API, GC và khoảng dừng của tiến trình khi hiệu chỉnh. Các thuộc tính thời gian dùng kiểu `Duration`; tên khóa và mặc định cụ thể có thể kiểm tra trong [LeaderElectionProperties 5.1.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.1.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/election/LeaderElectionProperties.java).

Ví dụ tắt ConfigMap/Secret PropertySource và discovery vì bài thử chỉ cần bầu leader. Không cần thêm `spring.config.import: "kubernetes:"` chỉ để kích hoạt leader election, cũng không cần Spring Cloud LoadBalancer cho thuật toán cạnh tranh lock.

## 7. Lock, danh tính và readiness cũng là điều kiện hỗ trợ

### 7.1. Kiểm tra tài nguyên lock thực tế

Cơ chế native có thể dùng Lease hoặc ConfigMap theo khả năng API và cấu hình. Lease là tài nguyên trong API group `coordination.k8s.io`, thường được dùng cho điều phối; xem [Kubernetes Leases](https://kubernetes.io/docs/concepts/architecture/leases/).

Tại tag `5.1.0`, mã nguồn hai client kiểm tra API của cluster để chọn lock. Đừng hiểu `use-config-map-as-lock=false` là lệnh bắt buộc chỉ dùng Lease trong mọi môi trường; cần xác nhận kết quả chọn lock qua log và tài nguyên thực tế.

Đồng thời, lỗi `Forbidden` khi kiểm tra API không chứng minh cluster không hỗ trợ Lease. Với một số đường thực thi, lỗi discovery API sẽ làm khởi tạo thất bại thay vì tự chuyển sang ConfigMap. Cần phân biệt API không có với tài khoản không được phép truy cập API đó.

Để kiểm tra điều kiện cluster trong môi trường thực hành:

```powershell
kubectl api-resources --api-group=coordination.k8s.io
kubectl get --raw /apis/coordination.k8s.io/v1
```

Các lệnh dùng credential của người chạy. Muốn kết luận cho ứng dụng, phải đối chiếu thêm với quyền và kết nối của ServiceAccount trong Pod.

### 7.2. Các ứng viên phải dùng cùng miền cạnh tranh

Đối với cùng tác vụ `invoice-dispatch`, các Pod cần thống nhất:

- Implementation và định dạng record/thuật toán lock tương thích.
- Loại tài nguyên lock thực sự được chọn.
- Namespace và tên lock; với đường cũ còn có role/khóa record tương ứng.
- Danh tính ứng viên riêng cho từng Pod.

`Lease/lab/invoice-dispatcher` và `ConfigMap/lab/invoice-dispatcher` là hai đối tượng khác nhau dù tên giống nhau. `Lease/default/invoice-dispatcher` cũng khác `Lease/lab/invoice-dispatcher`.

Trong thuộc tính native tại tag được đối chiếu, namespace lock có mặc định riêng; hãy khai báo rõ `lock-namespace` thay vì giả định nó luôn bằng namespace ứng dụng. Namespace của Pod và namespace lock cũng phục vụ hai mục đích khác nhau.

### 7.3. Tránh vòng chờ readiness và leadership

Với `wait-for-pod-ready=true`, ứng viên chờ Pod đạt Ready trước khi tham gia bầu leader. Nếu readiness của mọi Pod lại yêu cầu “đã là leader”, hệ thống có thể rơi vào vòng chờ:

```text
Muốn bầu leader -> phải Ready
Muốn Ready      -> phải được bầu leader
```

Với bài thực hành, follower khỏe vẫn phải có thể Ready. Trạng thái leader dùng để bật tác vụ nền, không được làm điều kiện bắt buộc để tất cả ứng viên vượt qua readiness ban đầu.

Mã native mặc định đọc Pod của chính ứng viên để xác định Ready. Vì vậy cần xác nhận tên ứng viên phù hợp với tên Pod và danh tính có quyền đọc Pod cần kiểm tra. Nếu tùy biến hostname hoặc cách cấp danh tính, phải xem implementation tìm Pod như thế nào.

## 8. RBAC phải khớp loại lock và các request phụ trợ

Trong biến thể thực hành native, giả sử cluster đã được xác nhận chọn Lease tại `lab/invoice-dispatcher`. Một cấu hình danh tính và quyền tham khảo:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: invoice-worker
  namespace: lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: invoice-worker-election
  namespace: lab
rules:
  - apiGroups: ["coordination.k8s.io"]
    resources: ["leases"]
    resourceNames: ["invoice-dispatcher"]
    verbs: ["get", "update"]
  - apiGroups: ["coordination.k8s.io"]
    resources: ["leases"]
    verbs: ["create"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: invoice-worker-election
  namespace: lab
subjects:
  - kind: ServiceAccount
    name: invoice-worker
    namespace: lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: invoice-worker-election
```

Hai rule Lease được tách có chủ đích. `resourceNames` giới hạn GET/UPDATE theo tên, nhưng không giới hạn CREATE tài nguyên cấp cao nhất theo cách tương tự. Ghép `create` vào một rule chỉ có `resourceNames` không tạo ra khả năng “chỉ tạo Lease có tên đó”. Xem [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Quyền `create` trong ví dụ có phạm vi các Lease trong namespace `lab`; đây là phạm vi rộng hơn một tên lock. Nếu chính sách yêu cầu chặt hơn, có thể đánh giá việc nền tảng cấp trước lock ở định dạng client chấp nhận rồi không cấp CREATE cho workload. Cách bootstrap đó phải được kiểm chứng với client cụ thể; đừng giả định mọi implementation đọc được một Lease rỗng tùy ý.

Rule GET Pod phục vụ kiểm tra readiness của native implementation ở ví dụ. Nó cho phép GET Pod trong namespace, không chỉ Pod của chính ứng viên. Khi cần thu hẹp hơn, phải đánh giá cách quản lý tên Pod động hoặc một cơ chế kiểm tra readiness khác được implementation hỗ trợ.

Đây không phải Role chung cho mọi release. Đường Fabric8 cũ có thể thực hiện thêm các thao tác theo dõi Pod/ConfigMap; đường native dùng ConfigMap sẽ cần quyền trên ConfigMap tương ứng. Cần xem request thực tế ở đúng implementation, không thêm `get/list/watch` cho mọi tài nguyên theo thói quen.

Leader election không cần quyền đọc Secret chỉ vì module đang dùng cùng bộ client với Secrets PropertySource. Cũng không gộp quyền đọc mọi ConfigMap với quyền ghi lock điều phối. Nếu API discovery bị giới hạn riêng trên cluster, đánh giá quyền truy cập đường discovery cần thiết thay vì cấp wildcard cho ứng dụng.

## 9. Sự kiện phải khớp cơ chế đang chạy

| Điều cần xử lý | Fabric8 cũ | Đường native ở các tag được đối chiếu |
| --- | --- | --- |
| Instance hiện tại bắt đầu làm leader | `OnGrantedEvent` | `StartLeadingEvent` |
| Instance hiện tại ngừng làm leader | `OnRevokedEvent` | `StopLeadingEvent` |
| Nhận thông báo danh tính leader | Theo API/logic của đường cũ | `NewLeaderEvent` |

Các sự kiện native nằm trong package `org.springframework.cloud.kubernetes.commons.leader.election.events`. Mã [LeaderElectionCallbacks 5.1.0](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v5.1.0/spring-cloud-kubernetes-commons/src/main/java/org/springframework/cloud/kubernetes/commons/leader/election/LeaderElectionCallbacks.java) cho thấy các callback phát từng loại sự kiện và chịu điều khiển bởi `publish-events`.

Một listener chỉ nghe `OnGrantedEvent` sẽ không tự biến thành listener `StartLeadingEvent` sau khi đổi dependency. Ngược lại, `NewLeaderEvent` là thông báo về leader được quan sát; không dùng sự kiện đó như tín hiệu cho mọi instance bắt đầu tác vụ leader.

### Ví dụ adapter cho sự kiện native

Bật `@EnableScheduling` trong cấu hình ứng dụng. Lớp sau chỉ tạo tick trong log để xác minh đường sự kiện, không thực hiện tác dụng phụ nghiệp vụ:

```java
package example.invoice;

import java.util.concurrent.atomic.AtomicBoolean;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.kubernetes.commons.leader.election.events.StartLeadingEvent;
import org.springframework.cloud.kubernetes.commons.leader.election.events.StopLeadingEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class LeaderTickProbe {
    private static final Logger log = LoggerFactory.getLogger(LeaderTickProbe.class);
    private final AtomicBoolean leading = new AtomicBoolean(false);

    @EventListener
    public void onStartLeading(StartLeadingEvent event) {
        leading.set(true);
        log.info("local leader work enabled");
    }

    @EventListener
    public void onStopLeading(StopLeadingEvent event) {
        leading.set(false);
        log.info("local leader work disabled");
    }

    @Scheduled(fixedDelay = 5000)
    public void tick() {
        if (leading.get()) {
            log.info("leader-only tick");
        }
    }
}
```

Ví dụ giúp kiểm tra rằng local start/stop thực sự nối đến logic ứng dụng. `AtomicBoolean` chỉ kiểm soát việc đi vào một lượt xử lý theo trạng thái tại thời điểm kiểm tra; nó không thu hồi tác vụ đang chạy, không hủy HTTP request đã gửi và không phải fencing cho dữ liệu bên ngoài.

Với công việc thật, cần cơ chế dừng nhận việc mới khi mất quyền, quản lý tác vụ đang chạy và xử lý trùng lặp hoặc stale worker tại nơi ghi dữ liệu. Khả năng leader election của một release không tự chứng minh yêu cầu “mỗi tác vụ chỉ có đúng một tác dụng phụ”.

## 10. Thử theo từng lớp để xác nhận tổ hợp được hỗ trợ

Các bước dưới đây là hướng dẫn chạy trong môi trường thực hành. Chúng không khẳng định rằng một cluster cụ thể đã được kiểm tra.

### 10.1. Chuẩn bị biến thể native nhất quán

Dùng cùng một image ứng dụng JVM đã build với module client được chọn, cấu hình phần 6.2 và adapter sự kiện phần 9. Ứng dụng có web server và Actuator cho probe. Namespace `lab` đã tồn tại.

Ví dụ workload, thay image minh họa bằng image thực tế:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: invoice-worker
  namespace: lab
spec:
  replicas: 3
  selector:
    matchLabels:
      app: invoice-worker
  template:
    metadata:
      labels:
        app: invoice-worker
    spec:
      serviceAccountName: invoice-worker
      containers:
        - name: app
          image: registry.example.com/training/invoice-worker:1.0.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
```

Cơ chế xác thực in-cluster phải được cấp cho Pod. Nếu môi trường đã tắt automount token và không có cơ chế xác thực thay thế, việc khai báo `serviceAccountName` một mình chưa đủ để client gọi API.

### 10.2. Xác nhận lần lượt, không sửa nhiều lớp cùng lúc

| Lớp kiểm tra | Bằng chứng cần thu được |
| --- | --- |
| Dependency | Module leader và họ client đúng phiên bản đã resolve |
| Auto-configuration | Đúng đường leader được kích hoạt; không chỉ có một thuộc tính nằm trong Environment |
| Xác thực và API | Client kết nối được API server, CA/token hợp lệ, xác định được loại lock |
| RBAC | Thao tác trên lock được phép; lỗi readiness không bắt nguồn từ thiếu quyền đọc Pod |
| Readiness | Các ứng viên có thể Ready trước khi được bầu |
| Bầu leader | Lock có holder và được gia hạn; khi leader rời đi có ứng viên tiếp quản |
| Tích hợp ứng dụng | Chỉ instance nhận local start thực hiện tick; stop làm ngừng nhận lượt việc mới |

Nếu cần condition evaluation report của Spring Boot, dùng cơ chế debug hoặc endpoint điều kiện trong phạm vi quản trị được kiểm soát. Không mở toàn bộ Actuator công khai để tìm bean.

### 10.3. Quan sát đúng loại tài nguyên

Với biến thể đã xác nhận dùng Lease:

```powershell
kubectl -n lab get pods -l app=invoice-worker
kubectl -n lab get lease invoice-dispatcher -o yaml
kubectl -n lab logs -l app=invoice-worker --all-containers=true --prefix=true --max-log-requests=3
```

Đối chiếu holder của Lease, log của từng Pod và tick nghiệp vụ minh họa. Không chỉ đếm một dòng “leader” ở một thời điểm vì leader cũ và mới có thể xuất hiện trong cùng khoảng log lịch sử.

Nếu implementation đã chọn ConfigMap, quan sát ConfigMap lock tương ứng. Không thấy Lease trong một ứng dụng dùng cơ chế ConfigMap cũ là hành vi đúng, không phải lỗi cần cấp thêm quyền Lease.

Người có quyền kiểm tra danh tính có thể đánh giá RBAC bằng `kubectl auth can-i` với ServiceAccount của workload, bao gồm quyền qua các nhóm tương ứng. Ví dụ các yêu cầu cần kiểm tra cho Role ở phần 8:

```text
get    leases/invoice-dispatcher trong lab     -> được phép
update leases/invoice-dispatcher trong lab    -> được phép
create leases trong lab                      -> được phép theo ví dụ
update leases/other-lock trong lab            -> không được phép
get    secrets bất kỳ trong lab               -> không được cấp bởi Role này
```

Kết quả là quyền tổng hợp từ mọi binding. Một Role hẹp không xóa quyền rộng đang được cấp từ binding khác.

### 10.4. Thử chuyển quyền có kiểm soát

Trong lab, xác định Pod đang giữ leader rồi cho Pod đó dừng theo quy trình thử nghiệm của môi trường. Theo dõi:

1. Dòng thời gian dừng tác vụ hoặc biến mất của Pod cũ.
2. Record lock và lần gia hạn cuối.
3. Instance nhận sự kiện bắt đầu leader mới.
4. Tick chỉ xuất hiện ở instance có quyền local mới trong trạng thái ổn định.

Thời gian tiếp quản phụ thuộc việc dừng có giải phóng lock hay không, lease duration, lịch retry, API latency và scheduling. Không dùng một giá trị timeout trong YAML để hứa chính xác thời điểm failover cho mọi trường hợp.

## 11. Nâng cấp hoặc đổi client phải kiểm tra tương thích giao thức

Giả sử nhóm cũ dùng ConfigMap và `OnGrantedEvent`, nhóm mới chuyển sang Lease và `StartLeadingEvent`. Trong một rolling rollout, hai nhóm có thể cùng tồn tại. Nếu chúng cạnh tranh trên hai lock khác nhau, mỗi nhóm có thể tự bầu một leader cho cùng tác vụ nghiệp vụ.

Ngay cả khi cả hai dùng ConfigMap cùng tên, vẫn phải đối chiếu định dạng record, role, khóa/annotation và thuật toán. Trùng tên đối tượng không phải hợp đồng tương thích giữa hai implementation.

Một kế hoạch chuyển đổi cần ghi rõ:

| Nội dung | Điều phải quyết định |
| --- | --- |
| Miền leader nghiệp vụ | Cùng tác vụ hay hai tác vụ độc lập? |
| Tương thích lock | Cùng loại, namespace, tên và giao thức lưu record không? |
| Listener | Sự kiện start/stop nào thực sự bật/tắt công việc? |
| Giai đoạn cùng tồn tại | Có thể bảo đảm chỉ một cơ chế nhận công việc không? |
| Dừng và tiếp quản | Ai ngừng nhận việc, xử lý việc đang chạy ra sao? |
| Rollback | Quay về đường cũ có tạo hai nhóm cạnh tranh độc lập không? |

Nếu chưa chứng minh tương thích, chọn cửa sổ chuyển đổi có kiểm soát: dừng nhận việc của cơ chế cũ, xác nhận các worker cũ đã dừng hoặc được chặn tại nơi ghi, rồi mới kích hoạt cơ chế mới. Với yêu cầu nghiêm ngặt, cần idempotency hoặc fencing tại hệ thống đích để giới hạn tác động của stale worker.

Đây là hệ quả thiết kế của việc đổi giao thức phối hợp, không phải lý do để luôn ngừng toàn bộ HTTP traffic. Tác vụ nền và khả năng phục vụ HTTP có thể có vòng đời riêng nếu ứng dụng được thiết kế như vậy.

## 12. Chọn tính năng đúng nhu cầu của module

DiscoveryClient xác định instance dịch vụ; Spring Cloud LoadBalancer chọn đích gọi; ConfigMap/Secret cấp cấu hình. Các khả năng đó không tự chọn một Pod để thực thi tác vụ nền.

Với Configuration Watcher, cần kiểm tra tính năng HA riêng của release. Tài liệu hiện hành được đối chiếu mô tả `spring.cloud.kubernetes.configuration.watcher.ha.enabled=true` vừa chọn chế độ HA của watcher vừa kích hoạt hạ tầng leader tương ứng. Chỉ bật cờ native leader election không tự làm watcher chỉ chạy informer trên leader. Xem [Configuration Watcher — High Availability](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Nếu ứng dụng chỉ phục vụ HTTP stateless và không có công việc điều phối độc quyền, có thể không cần leader election. Nếu tác vụ được Kubernetes CronJob hoặc hệ thống điều phối khác quản lý, đánh giá cơ chế kiểm soát đồng thời và xử lý trùng của hệ thống đó trước khi thêm một lớp bầu leader trong từng service.

## 13. Chẩn đoán nhanh theo điều kiện bị thiếu

| Hiện tượng | Điều kiện cần kiểm tra trước |
| --- | --- |
| Thêm thuộc tính mới nhưng không có bean leader | Release có module và auto-configuration tiêu thụ thuộc tính đó không? |
| Discovery chạy được nhưng leader không chạy | Đã thêm đúng module leader và có bean client cần thiết chưa? |
| Native không kích hoạt khi chạy trên máy cá nhân | Điều kiện cloud platform, client và credential thực tế có khớp không? |
| Có leader log nhưng tác vụ không bắt đầu | Listener có nghe đúng sự kiện? `publish-events` có bật không? |
| Mọi Pod đều chờ, không có lock | Có vòng chờ giữa readiness và leadership không? |
| `Forbidden` với Lease hoặc Pod | Đúng ServiceAccount, namespace và verb của request chưa? |
| Không thấy Lease nhưng có ConfigMap leader | Implementation đang dùng lock ConfigMap theo thiết kế không? |
| Hai leader sau khi đổi client/release | Có hai loại lock, namespace, role hoặc giao thức độc lập không? |
| Tắt cờ cũ nhưng native vẫn hoạt động | Cờ native hoặc cờ HA của watcher có đang kích hoạt đường mới không? |
| Failover xảy ra nhưng việc vẫn bị xử lý trùng | Cơ chế dừng tác vụ, idempotency/fencing có đáp ứng yêu cầu nghiệp vụ không? |

Bằng chứng hoàn thành cho một tổ hợp triển khai nên ghi đủ: phiên bản đã resolve, họ client, module leader, cờ kích hoạt, loại/namespace/tên lock, danh tính, quyền cần thiết, loại sự kiện và kết quả thử chuyển quyền. Một kết luận như “hỗ trợ leader election” chỉ có giá trị vận hành khi gắn với những điều kiện cụ thể đó.
