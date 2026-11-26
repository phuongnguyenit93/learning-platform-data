# Rà soát tài nguyên, label và quyền không còn sử dụng

Trong chương **Vận hành cấu hình** của module **SPRING_CLOUD_KUBERNETES**, bài học này hướng dẫn rà soát những ConfigMap, Secret, label và quyền đã được tạo qua nhiều lần triển khai. Mục tiêu là giảm tài nguyên thừa và quyền dư mà vẫn giữ được discovery, cập nhật cấu hình, khởi động Pod mới và khả năng phục hồi.

Một đối tượng cũ chưa chắc đã hết dùng. Nó có thể được một CronJob gọi theo tháng, một ứng dụng chỉ đọc lúc khởi động, một watcher chọn bằng label hoặc một ReplicaSet giữ lại để rollback. Vì vậy, rà soát cần tạo ra bằng chứng và quyết định theo từng đối tượng, không biến tuổi tài nguyên hay việc không có Pod hiện tại thành điều kiện xóa tự động.

## 1. Tình huống và kết quả cần đạt

Giả sử namespace `shop` có dịch vụ `checkout` với các đặc điểm:

- Pod hiện tại nhận ConfigMap `checkout-config-r9` và Secret `checkout-db-cred-r5` qua volume.
- Ứng dụng vẫn dùng DiscoveryClient để tìm các Service và EndpointSlice trong `shop`.
- Một ConfigMap `checkout-config-r6` không còn xuất hiện trong cấu hình phát hành hiện tại.
- Một label `legacy.example/refresh` còn sót sau khi đổi cơ chế cập nhật cấu hình.
- Một RoleBinding cũ vẫn cấp quyền đọc Secret qua API cho ServiceAccount runtime.
- CronJob `monthly-reconciliation` chưa có Pod chạy tại thời điểm rà soát nhưng vẫn cần credential riêng.

Đội vận hành muốn loại bỏ phần không còn cần thiết mà không làm mất luồng tìm dịch vụ, dừng refresh của ứng dụng khác hoặc phá đường rollback.

Sau bài học, bạn có thể:

1. Lập danh sách tài nguyên và người tiêu thụ ở cả trạng thái hiện tại lẫn mẫu triển khai tương lai.
2. Phân biệt label mô tả với label có tác động điều khiển.
3. Đánh giá quyền hiệu lực thay vì chỉ nhìn tên Role hoặc số lượng binding.
4. Chuyển một ứng viên thu dọn thành thay đổi có phạm vi, kiểm chứng và phương án phục hồi rõ ràng.

Các lệnh trong bài là ví dụ cho môi trường học tập hoặc môi trường đã được giao quyền phù hợp. Chúng phục vụ quan sát; quyết định thay đổi cần đi qua đúng nguồn quản lý tài nguyên của hệ thống.

## 2. Phân loại kết quả rà soát trước khi thu dọn

Dùng một tập trạng thái đơn giản trong báo cáo:

| Trạng thái đánh giá | Ý nghĩa | Hành động tiếp theo |
| --- | --- | --- |
| Đang sử dụng | Có người tiêu thụ hoặc chức năng được xác nhận | Giữ và cập nhật thông tin sở hữu |
| Đang giữ có chủ đích | Phục vụ rollback, lịch chạy hoặc quy trình phục hồi | Ghi lý do, điều kiện kết thúc và thời điểm xét lại |
| Chưa đủ bằng chứng | Chưa rõ owner, consumer hoặc phạm vi quan sát | Tiếp tục điều tra; chưa kết luận bỏ được |
| Ứng viên loại bỏ | Không còn nhu cầu trong phạm vi đã kiểm chứng | Chuẩn bị thay đổi, kiểm thử và kế hoạch phục hồi |
| Đã loại bỏ và xác minh | Nguồn quản lý cùng trạng thái thực tế đã được cập nhật | Đóng hồ sơ bằng bằng chứng sau thay đổi |

Đây là trạng thái của báo cáo do đội vận hành định nghĩa, không phải một label có sẵn của Kubernetes. Không cần gắn label thử nghiệm vào tài nguyên đang chạy chỉ để lập danh sách ứng viên.

### Những tín hiệu chỉ giúp đặt câu hỏi

| Tín hiệu | Vì sao chưa đủ để kết luận không còn sử dụng? |
| --- | --- |
| Đã tồn tại lâu | Có thể là cấu hình ổn định hoặc credential dùng lâu dài |
| Không có ownerReferences | Tài nguyên độc lập vẫn có thể được Pod hoặc client sử dụng |
| Không có Pod đang tham chiếu | Workload scale về 0, CronJob hoặc lần rollback có thể còn cần |
| Không thấy GET gần đây | Client có thể đọc lúc khởi động hoặc đang dùng cache/file |
| Role không được runtime hiện tại gọi | Quyền có thể dành cho reconnect, refresh hoặc controller khác |
| Label không xuất hiện trong code ứng dụng | Service, policy, watcher hoặc công cụ quản trị có thể dùng |
| Không tìm thấy tên trong một file YAML | Tên có thể được render, tính theo profile hoặc lấy từ nguồn khác |

Bằng chứng tốt kết hợp: nguồn khai báo, trạng thái cluster, cấu hình hiệu lực, hành vi ở vòng đời cần thiết và xác nhận của chủ thể chịu trách nhiệm. Một khoảng quan sát yên lặng không chứng minh mọi nhánh sử dụng tương lai đã được loại trừ.

## 3. Lập danh mục theo đúng phạm vi và chủ thể quản lý

### 3.1. Khóa định danh và thông tin cần ghi

Mỗi mục nên được nhận diện bằng ít nhất `apiGroup/kind`, namespace nếu có và tên. Ghi thêm UID của đối tượng live khi cần phân biệt trường hợp cùng tên đã được tạo lại.

Các cột hữu ích:

| Nhóm thông tin | Ví dụ |
| --- | --- |
| Định danh | `core/ConfigMap`, `shop`, `checkout-config-r6`, UID live |
| Sở hữu vận hành | Đội quản lý `checkout`, người liên hệ, repository/overlay |
| Quản lý vòng đời | GitOps, Helm, operator, controller hoặc quy trình cấp phát |
| Người tiêu thụ | Deployment, CronJob, property source, watcher, policy |
| Lý do giữ | Rollback còn hiệu lực đến mốc đã chọn |
| Bằng chứng và giới hạn | Đã kiểm tra loại workload nào, còn nguồn động nào chưa rõ |
| Đề xuất | Giữ, thu hẹp, chuyển chủ sở hữu hoặc loại bỏ |
| Phục hồi | Revision manifest, nguồn Secret và thao tác xác minh cần thiết |

Các label khuyến nghị như `app.kubernetes.io/name`, `instance`, `part-of` và `managed-by` giúp công cụ nhận diện ứng dụng. Chúng vẫn là metadata cần được kiểm tra, không phải bằng chứng tuyệt đối về chủ sở hữu hay người tiêu thụ. [Kubernetes: Recommended Labels](https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/).

### 3.2. Quan sát ban đầu bằng lệnh chỉ đọc

```powershell
kubectl get deployments,statefulsets,daemonsets,replicasets,jobs,cronjobs,pods -n shop
kubectl get configmaps -n shop -o custom-columns='NAME:.metadata.name,CREATED:.metadata.creationTimestamp'
kubectl get secrets -n shop -o custom-columns='NAME:.metadata.name,TYPE:.type,CREATED:.metadata.creationTimestamp'
kubectl get services -n shop --show-labels
kubectl get serviceaccounts,roles,rolebindings -n shop
kubectl get clusterroles,clusterrolebindings
```

Lệnh cluster-scoped chỉ dành cho người có quyền quan sát tương ứng. Không coi kết quả bị thiếu vì RBAC là một tập dữ liệu đầy đủ.

`custom-columns` giới hạn nội dung hiển thị của lệnh Secret, không biến quyền LIST Secret thành quyền chỉ đọc metadata. Người thực hiện phải có quyền phù hợp; không cấp thêm quyền rộng cho ứng dụng chỉ để chạy một đợt inventory. Kubernetes xác định rằng GET/LIST/WATCH Secret có thể làm lộ dữ liệu Secret. [Kubernetes: Good practices for Kubernetes Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/).

`kubectl get all` không phải danh sách mọi loại tài nguyên cần xét. Cần khai báo rõ những loại quan tâm, và bổ sung custom resource của operator hoặc nền tảng đang sử dụng.

### 3.3. Ownership khác với tham chiếu sử dụng

`ownerReferences` biểu diễn quan hệ chủ sở hữu/phụ thuộc của Kubernetes, khác cơ chế label/selector. Một tên ConfigMap trong PodSpec không tự tạo quan hệ ownerReference khiến ConfigMap được giữ hoặc xóa theo Pod. [Kubernetes: Owners and Dependents](https://kubernetes.io/docs/concepts/overview/working-with-objects/owners-dependents/).

Garbage collection xử lý những quan hệ vòng đời mà Kubernetes biết; nó không thay đội ứng dụng chứng minh rằng mọi ConfigMap, Secret hoặc label đều đã hết người dùng. [Kubernetes: Garbage Collection](https://kubernetes.io/docs/concepts/architecture/garbage-collection/).

Không thêm ownerReference tùy ý để “dọn cho gọn”. Thay đổi quan hệ này có thể làm tài nguyên bị xóa theo owner hoặc vi phạm quy tắc phạm vi của quan hệ sở hữu.

## 4. Tìm tham chiếu trực tiếp từ workload

### 4.1. Các vị trí phải kiểm tra

Không chỉ xem `spec.containers` của Pod đang chạy:

| Nguồn tham chiếu | Vị trí thường gặp |
| --- | --- |
| Volume | `volumes[].configMap`, `volumes[].secret` |
| Projected volume | Các nguồn ConfigMap/Secret trong `volumes[].projected.sources` |
| Biến môi trường | `env[].valueFrom.configMapKeyRef` và `secretKeyRef` |
| Nhập nhóm biến | `envFrom[].configMapRef` và `secretRef` |
| Credential kéo image | `imagePullSecrets` ở Pod hoặc cấu hình ServiceAccount liên quan |
| Danh tính API | `serviceAccountName` |
| Mẫu workload | Pod template trong Deployment, StatefulSet, DaemonSet, ReplicaSet và Job |
| Lịch chạy | `CronJob.spec.jobTemplate.spec.template` |
| Thành phần phụ | Init container, sidecar và ephemeral container khi có |

ReplicaSet cũ và template đang scale về 0 có ý nghĩa khi đánh giá khả năng tái tạo Pod hoặc rollback. CronJob không có Pod hiện tại vẫn có một nhu cầu tương lai đã được khai báo.

### 4.2. Script PowerShell lập bảng tham chiếu

Script dưới chỉ truy vấn một namespace và xuất tên đối tượng được tham chiếu; không truy vấn nội dung ConfigMap/Secret và không thay đổi cluster. Snapshot workload vẫn có thể chứa dữ liệu nhạy cảm nếu ai đó đã đặt giá trị rõ trong PodSpec, nên không xuất toàn bộ JSON ra artifact chia sẻ.

```powershell
$auditNamespace = 'shop'
$workloadTypes = 'deployments,statefulsets,daemonsets,replicasets,jobs,cronjobs,pods'
$workloadSnapshot = kubectl get $workloadTypes -n $auditNamespace -o json
if ($LASTEXITCODE -ne 0) {
    throw 'Không lấy được snapshot workload đầy đủ; chưa được kết luận thiếu tham chiếu.'
}
$workloads = ($workloadSnapshot | ConvertFrom-Json).items

function New-ReferenceRow {
    param(
        [string]$Workload,
        [string]$RefKind,
        [string]$RefName,
        [string]$Path
    )
    if (-not [string]::IsNullOrWhiteSpace($RefName)) {
        [pscustomobject]@{
            Namespace = $auditNamespace
            Workload = $Workload
            Kind = $RefKind
            Name = $RefName
            Path = $Path
        }
    }
}

$references = @(
    foreach ($item in $workloads) {
        $workloadName = '{0}/{1}' -f $item.kind, $item.metadata.name
        $podSpec = switch ($item.kind) {
            'Pod' { $item.spec }
            'CronJob' { $item.spec.jobTemplate.spec.template.spec }
            default { $item.spec.template.spec }
        }
        if ($null -eq $podSpec) { continue }

        foreach ($volume in @($podSpec.volumes)) {
            if ($null -eq $volume) { continue }
            New-ReferenceRow $workloadName 'ConfigMap' $volume.configMap.name 'volume'
            New-ReferenceRow $workloadName 'Secret' $volume.secret.secretName 'volume'
            foreach ($source in @($volume.projected.sources)) {
                if ($null -eq $source) { continue }
                New-ReferenceRow $workloadName 'ConfigMap' $source.configMap.name 'projected'
                New-ReferenceRow $workloadName 'Secret' $source.secret.name 'projected'
            }
        }

        $containers = @($podSpec.containers) + @($podSpec.initContainers) + @($podSpec.ephemeralContainers)
        foreach ($container in $containers) {
            if ($null -eq $container) { continue }
            foreach ($entry in @($container.env)) {
                if ($null -eq $entry) { continue }
                New-ReferenceRow $workloadName 'ConfigMap' $entry.valueFrom.configMapKeyRef.name 'env'
                New-ReferenceRow $workloadName 'Secret' $entry.valueFrom.secretKeyRef.name 'env'
            }
            foreach ($entry in @($container.envFrom)) {
                if ($null -eq $entry) { continue }
                New-ReferenceRow $workloadName 'ConfigMap' $entry.configMapRef.name 'envFrom'
                New-ReferenceRow $workloadName 'Secret' $entry.secretRef.name 'envFrom'
            }
        }

        foreach ($pullSecret in @($podSpec.imagePullSecrets)) {
            if ($null -eq $pullSecret) { continue }
            New-ReferenceRow $workloadName 'Secret' $pullSecret.name 'imagePullSecrets'
        }
        $accountName = $podSpec.serviceAccountName
        if ([string]::IsNullOrWhiteSpace($accountName)) { $accountName = 'default' }
        New-ReferenceRow $workloadName 'ServiceAccount' $accountName 'serviceAccountName'
    }
)

$references |
    Sort-Object Kind, Name, Workload, Path -Unique |
    Format-Table Namespace, Workload, Kind, Name, Path -AutoSize
```

Đây là công cụ thu thập bằng chứng cho những trường chuẩn đã liệt kê, không phải bộ phát hiện mọi tài nguyên không dùng. Nó chưa kiểm tra `ServiceAccount.imagePullSecrets`, Ingress TLS Secret, custom resource, CSI/provider, tên được ứng dụng tính động, nguồn Git/Helm hoặc lịch sử phát hành ngoài cluster.

Một kết quả rỗng chỉ có nghĩa không tìm thấy trong tập trường và snapshot đó. Không nối trực tiếp danh sách “không thấy tham chiếu” với lệnh xóa hàng loạt.

## 5. Bổ sung phụ thuộc không nằm trực tiếp trong PodSpec

### 5.1. Property source của Spring Cloud Kubernetes

Một ứng dụng có thể gọi Kubernetes API để lấy cấu hình theo tên, profile hoặc selector. Ví dụ cấu hình nguồn:

```yaml
spring:
  application:
    name: checkout
  cloud:
    kubernetes:
      config:
        namespace: shop
        sources:
          - name: checkout-defaults
          - name: checkout-config-r9
```

Tên trong ví dụ là nguồn cấu hình, không phải tham chiếu volume bắt buộc xuất hiện trong PodSpec. Spring Cloud Kubernetes hỗ trợ các quy tắc chọn tên và nhiều nguồn ConfigMap; nguồn theo profile hoặc cấu hình bổ sung cũng cần được đối chiếu theo release đang dùng. [Spring Cloud Kubernetes: ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html).

Khi rà soát, cần xem cấu hình hiệu lực từ những nguồn có thẩm quyền: giá trị được đóng gói, biến môi trường, import, overlay và cơ chế bootstrap nếu có. Không chỉ tìm tên object theo một chuỗi cố định trong Deployment.

Đặc biệt chú ý tên mặc định có thể dựa vào `spring.application.name`, nguồn dùng chung cho nhiều ứng dụng và tên được render bởi chart. Việc không tìm thấy `checkout-defaults` trong danh sách volume không chứng minh nó đã hết được dùng.

### 5.2. DiscoveryClient, LoadBalancer và watcher

| Thành phần | Phụ thuộc cần ghi nhận |
| --- | --- |
| DiscoveryClient | Namespace tìm kiếm, Service, Endpoints/EndpointSlice, metadata hoặc label được sử dụng |
| Spring Cloud LoadBalancer | Nguồn danh sách instance, metadata dùng chọn instance và ảnh hưởng của cache |
| Configuration Watcher | Namespace, selector ConfigMap/Secret, ứng dụng nhận refresh và danh tính controller |
| Config Server hoặc Discovery Server dùng chung | Tập ứng dụng ở các namespace khác có thể đang dùng dữ liệu gián tiếp |

Một ứng dụng không trực tiếp GET ConfigMap không có nghĩa hệ thống không cần object đó: một thành phần trung gian hoặc watcher có thể vẫn cần nó. Tương tự, Service còn được gọi bằng DNS hoặc client bên ngoài không biến thành tài nguyên thừa chỉ vì một DiscoveryClient đã ngừng dùng.

### 5.3. Phân biệt không còn thấy với không còn cần

Một client có thể tiếp tục chạy nhờ cache hoặc cấu hình đã đọc vào bộ nhớ. Thu hồi quyền hay xóa tài nguyên rồi thấy request hiện tại vẫn thành công chưa chứng minh vòng khởi động sau sẽ thành công.

Phạm vi kiểm chứng cần bao gồm các hành vi liên quan: khởi động Pod mới, refresh, reconnect watch, nạp profile cần thiết, chạy tác vụ định kỳ và phục hồi từ phiên bản được giữ. Không cần thực hiện tất cả trên production; chọn môi trường và bước thử theo tác động của thay đổi.

## 6. Rà soát label như một phần của hợp đồng hệ thống

### 6.1. Ai đang đọc label này?

| Vị trí label | Người tiêu thụ có thể có | Tác động khi bỏ hoặc đổi |
| --- | --- | --- |
| Label của Pod | Service selector, NetworkPolicy, scheduling, giám sát | Đổi tập endpoint, đường mạng hoặc điều kiện chọn Pod |
| Label trên Service | DiscoveryClient, công cụ giám sát, quy tắc định tuyến | Service không được discovery trả về hoặc được diễn giải khác |
| Label trên ConfigMap/Secret | Configuration Watcher hoặc controller tùy biến | Bỏ theo dõi hoặc đổi tập cấu hình được xử lý |
| Label trên Namespace | Policy hoặc công cụ quản trị chọn namespace | Đổi phạm vi áp dụng chính sách |
| Label trên ClusterRole | Cơ chế aggregation | Đổi quyền được tổng hợp vào Role khác |
| Label sở hữu/quản lý | Helm, GitOps, inventory hoặc tự động hóa của đội vận hành | Sai định danh hoặc bị công cụ quản lý ghi lại |

Cần phân biệt label ở metadata của Deployment với label trong `spec.template.metadata.labels` của Pod. Chúng nằm ở các object khác nhau. Việc chỉ bỏ một label “ở Deployment” có thể tạo thay đổi rất khác tùy vị trí.

Selector dùng `!=` hoặc `notin` có thể bao gồm cả đối tượng không có key label tương ứng. Vì thế, không dùng một selector phủ định như bằng chứng mặc định rằng tập được chọn là tài nguyên đã xác nhận bỏ được. [Kubernetes: Labels and Selectors](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/).

### 6.2. Label của Service không giống selector của Service

Ví dụ:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: checkout
  namespace: shop
  labels:
    app.kubernetes.io/name: checkout
    discovery.example/enabled: "true"
spec:
  selector:
    app.kubernetes.io/name: checkout
  ports:
    - name: http
      port: 8080
      targetPort: 8080
```

`metadata.labels` mô tả chính Service. `spec.selector` chọn Pod để tạo tập endpoint phục vụ. Bỏ label metadata dùng cho discovery và đổi selector chọn Pod là hai thay đổi độc lập. [Kubernetes: Service](https://kubernetes.io/docs/concepts/services-networking/service/).

Nếu cấu hình ứng dụng có:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        service-labels:
          discovery.example/enabled: "true"
```

bỏ label `discovery.example/enabled` trên Service có thể làm Service không còn nằm trong tập discovery. Một số metadata còn ảnh hưởng cách diễn giải instance; tài liệu DiscoveryClient có quy tắc chọn cổng, gồm label `primary-port-name` trên Service. [Spring Cloud Kubernetes: DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Không tự coi label là “trang trí” vì Service vẫn có ClusterIP hoặc Pod vẫn báo Ready. Cần kiểm tra cả tập instance mà client thực sự nhận được và các lời gọi nghiệp vụ đi qua LoadBalancer.

### 6.3. Label của Configuration Watcher

Theo cấu hình mặc định được tài liệu hiện hành mô tả, watcher chọn ConfigMap có label `spring.cloud.kubernetes.config: "true"`. Theo dõi Secret cần được bật có chủ đích; khi bật, label tương ứng là `spring.cloud.kubernetes.secret: "true"`. Các selector có thể được cấu hình lại. [Spring Cloud Kubernetes Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Trước khi bỏ label:

1. Xác định watcher nào đang chạy và phiên bản/configuration thực tế của nó.
2. Xác định resource có thuộc tập được chọn hay không.
3. Xác định ứng dụng nào nhận refresh từ resource đó.
4. Kiểm tra luồng cập nhật còn cần thiết không, kể cả trường hợp ứng dụng đã chuyển sang rollout.
5. Chuyển hoặc bỏ cơ chế cũ theo đúng thứ tự, rồi kiểm chứng thay đổi cấu hình tiếp theo.

Không xóa một watcher dùng chung chỉ vì `checkout` không còn cần refresh. Những ứng dụng khác có thể vẫn phụ thuộc controller đó. Việc label dùng để lọc watcher cũng không tạo ra quyền RBAC giới hạn theo label cho danh tính watcher.

### 6.4. Ví dụ thay đổi label đã được chứng minh là thừa

Giả sử đã xác minh `legacy.example/refresh` không còn được code, controller, selector, chart hoặc tự động hóa sử dụng, còn label watcher vẫn có vai trò trong luồng đã kiểm chứng. Diff trong nguồn quản lý có thể chỉ là:

```diff
 metadata:
   labels:
     app.kubernetes.io/name: checkout
     spring.cloud.kubernetes.config: "true"
-    legacy.example/refresh: "enabled"
```

Không đồng thời đổi tên ConfigMap, thay nguồn đọc và bỏ quyền API trong cùng một thay đổi chỉ để thu dọn label. Tách những biến độc lập giúp xác định nguyên nhân nếu tập người nhận refresh hoặc hành vi ứng dụng thay đổi.

### 6.5. Label có thể tham gia tổng hợp quyền

Một ClusterRole không được RoleBinding tham chiếu trực tiếp vẫn có thể đóng góp rule cho một aggregated ClusterRole qua label selector. Bỏ label aggregation có thể làm mất quyền ở nơi khác; sửa trực tiếp `rules` do controller tổng hợp còn có thể bị ghi đè lại. [Kubernetes RBAC: Aggregated ClusterRoles](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#aggregated-clusterroles).

Do đó, rà soát label trên RBAC phải xem cả `aggregationRule` và các Role được tạo thành, không chỉ tìm tên trong `roleRef`.

## 7. Rà soát và thu hẹp quyền không còn cần

### 7.1. Đi từ chủ thể tới quyền hiệu lực

Chuỗi kiểm tra:

```text
Workload / controller / tác vụ
  → ServiceAccount hoặc danh tính người dùng
  → RoleBinding và ClusterRoleBinding, kể cả binding cho nhóm
  → Role / ClusterRole, kể cả aggregation
  → tài nguyên, namespace và động từ được phép
  → nhu cầu thực tế tại các thời điểm sử dụng
```

RBAC Kubernetes cộng các quyền từ các nguồn cấp liên quan và không có deny rule. Xóa một binding có thể không giảm quyền nếu một binding khác vẫn cấp cùng khả năng. [Kubernetes: Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Đối với mỗi quyền được đề xuất bỏ, cần trả lời:

- Nó được cấp cho ai và có những đường cấp trùng nào?
- Chức năng nào trước đây cần quyền này và chức năng đó đã thay đổi ra sao?
- Có chỉ dùng ở startup, refresh, reconnect hoặc lịch chạy thưa không?
- Có controller dùng chung hay workload scale về 0 còn cần không?
- Sau thay đổi, quyền cần thiết nào phải giữ và quyền ngoài nhu cầu nào phải không còn?

Một ServiceAccount không có Pod tại thời điểm kiểm tra chưa chắc đã hết dùng. Kiểm tra template, lịch chạy và nguồn triển khai. Binding tới một danh tính đã bị bỏ cũng cần được dọn theo kế hoạch, vì việc tái sử dụng tên danh tính có thể làm quyền cũ có hiệu lực trở lại ngoài ý định. Kubernetes khuyến nghị rà soát định kỳ các mục RBAC dư thừa và đường nâng quyền. [Kubernetes: RBAC good practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/).

### 7.2. Hợp đồng quyền sau thay đổi của `checkout`

Trong tình huống đã xác minh:

| Nhu cầu | Quyết định |
| --- | --- |
| Đọc ConfigMap và Secret đã mount | Giữ tham chiếu volume; runtime không cần quyền API cho đường đọc file |
| Discovery trong `shop` | Giữ quyền đúng tài nguyên discovery của implementation đang dùng |
| Đọc Secret qua API theo cơ chế cũ | Bỏ đường cấp quyền cũ sau khi chứng minh không còn người dùng |
| Watcher dùng chung | Giữ danh tính riêng và quyền theo phạm vi thật sự cần |
| Tạo/sửa workload hoặc RBAC bởi runtime | Không thuộc hợp đồng runtime của ví dụ |

Mẫu Role cho **implementation đã xác minh chỉ cần đọc Service và EndpointSlice**, không cần đọc Pod để bổ sung metadata:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: checkout-discovery
  namespace: shop
rules:
  - apiGroups:
      - ""
    resources:
      - services
    verbs:
      - get
      - list
      - watch
  - apiGroups:
      - discovery.k8s.io
    resources:
      - endpointslices
    verbs:
      - get
      - list
      - watch
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: checkout-discovery
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: checkout-runtime
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: checkout-discovery
```

Đây không phải Role mặc định cho mọi starter. Nếu release đang dùng Endpoints hoặc cần tài nguyên bổ sung, đối chiếu đúng implementation và request thực tế trước khi chọn rule. Không giữ quyền Secret chỉ vì một ví dụ cũ đã gộp mọi resource vào cùng Role.

Áp dụng một Role hẹp mới nhưng vẫn giữ RoleBinding cũ cấp LIST/WATCH Secret chưa hoàn tất việc thu hẹp. Cần sửa hoặc bỏ đúng đường cấp dư trong nguồn quản lý, sau khi kiểm tra các chủ thể cùng dùng Role đó.

Runtime vẫn cần credential API cho discovery; không tắt automount token một cách đồng loạt chỉ vì nó không còn đọc Secret qua API. Ngược lại, một workload đã chuyển hẳn sang DNS và file mount có thể được đánh giá giảm tiếp quyền và đường cấp token.

### 7.3. Khi nào một Role hoặc ClusterRole có thể là ứng viên bỏ?

Không có binding trực tiếp chỉ là một tín hiệu. Trước khi kết luận, kiểm tra:

1. RoleBinding/ClusterRoleBinding liên quan trong phạm vi đầy đủ.
2. `aggregationRule` và label tổng hợp.
3. Desired state của chart, operator hoặc GitOps có còn khai báo nhu cầu không.
4. Trách nhiệm của controller hoặc tài khoản hệ thống đang quản lý đối tượng.
5. Kịch bản phục hồi, bootstrap hoặc tác vụ không chạy liên tục.

Không tự sửa Role/Binding hệ thống như tài nguyên riêng của ứng dụng. Nếu chúng nằm trong phạm vi rà soát, cần xử lý cùng chủ thể quản trị nền tảng và cơ chế tự hòa giải tương ứng.

## 8. Kiểm chứng quyền trước và sau thay đổi

### 8.1. Ma trận quyền cần giữ và quyền cần bỏ

Với hợp đồng của `checkout-runtime`, dùng PowerShell để mô phỏng danh tính cùng các nhóm ServiceAccount chuẩn:

```powershell
$identityArgs = @(
    '--as=system:serviceaccount:shop:checkout-runtime'
    '--as-group=system:serviceaccounts'
    '--as-group=system:serviceaccounts:shop'
    '--as-group=system:authenticated'
)

kubectl auth can-i get services -n shop @identityArgs
kubectl auth can-i list endpointslices.discovery.k8s.io -n shop @identityArgs
kubectl auth can-i get configmaps/checkout-config-r9 -n shop @identityArgs
kubectl auth can-i list secrets -n shop @identityArgs
kubectl auth can-i watch secrets -n shop @identityArgs
kubectl auth can-i patch configmaps/checkout-config-r9 -n shop @identityArgs
kubectl auth can-i create deployments.apps -n shop @identityArgs
```

Người chạy cần có quyền impersonation user và nhóm phù hợp. Khi môi trường có cơ chế danh tính khác, đối chiếu tập nhóm và kết quả với danh tính thật của workload. `kubectl auth can-i` kiểm tra hành động được phép, không chứng minh tài nguyên đang tồn tại hoặc chức năng của ứng dụng đã hoạt động. [Kubernetes: kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Kết quả mong đợi sau khi đã loại bỏ các đường cấp dư:

| Hành động | Kết quả trong ví dụ |
| --- | --- |
| GET Service trong `shop` | `yes` |
| LIST EndpointSlice trong `shop` | `yes` |
| GET ConfigMap đang được nhận bằng volume | `no` |
| LIST/WATCH Secret | `no` |
| PATCH ConfigMap | `no` |
| Tạo Deployment | `no` |

Kết quả `no` là kết quả chủ đích của những phép kiểm tra ngoài quyền; CLI có thể trả exit code khác 0. Không gom mọi kết quả đó thành lỗi môi trường kiểm chứng.

Nếu LIST Secret vẫn trả `yes`, cần tìm nguồn quyền còn lại thay vì chỉ nhìn Role mới. Nếu quyền discovery cần giữ chuyển thành `no`, chưa thể coi thay đổi thu hẹp là đạt.

Ứng dụng vẫn có thể đọc credential đã mount dù GET/LIST Secret qua API bị từ chối. Đây là hai đường dữ liệu khác nhau. Thu hồi quyền API cũng không xóa những bản sao credential đã được tiến trình nhận từ trước.

### 8.2. Kiểm chứng hành vi, không chỉ capability

Các phép kiểm tra chức năng nên tương ứng với thay đổi đã thực hiện:

| Thay đổi | Kiểm chứng cần làm |
| --- | --- |
| Bỏ quyền API cấu hình cũ | Pod mới khởi động, đọc file và phục vụ với cấu hình đúng |
| Giữ quyền discovery | Danh sách instance đúng và client gọi được dịch vụ sau cập nhật/reconnect |
| Bỏ label watcher cũ | Luồng được giữ vẫn cập nhật đúng; luồng đã bỏ không tiếp tục phát refresh ngoài dự kiến |
| Loại bản cấu hình cũ | Không còn template/kịch bản phục hồi đang được giữ cần tên đó |
| Bỏ quyền của tác vụ định kỳ | Chạy tác vụ tương ứng trong môi trường kiểm chứng, không chỉ quan sát runtime HTTP |
| Thu hẹp phạm vi namespace | Consumer ngoài phạm vi đã được xác định và xử lý |

Pod đang chạy ổn có thể che một lỗi chỉ xuất hiện ở lần khởi động kế tiếp. Client đã mở watch có thể chưa cần tái xác thực/ủy quyền cho một kết nối mới. Vì thế cần đưa những mốc vòng đời đó vào kế hoạch kiểm chứng, thay vì chỉ đợi một khoảng thời gian rồi kết luận.

## 9. Dùng quan sát runtime và audit đúng giới hạn

### 9.1. Chọn khoảng quan sát theo chu kỳ sử dụng

Thời gian quan sát cần liên hệ với startup, refresh, reconnect, lịch CronJob, rotation credential và cửa sổ rollback. Một tác vụ theo tháng không thể được kết luận hết dùng chỉ vì không có hoạt động trong 30 phút.

Khi không thể chờ đủ chu kỳ, kiểm chứng có kiểm soát ở môi trường phù hợp và ghi rõ phần nào chưa được bao phủ. Không biến thiếu dữ liệu thành bằng chứng phủ định.

Log/metric hữu ích gồm:

- Lỗi `Forbidden`, lỗi không tìm thấy ConfigMap/Secret và lỗi tạo mount.
- Khởi động, restart, readiness và khả năng thực hiện công việc hợp lệ.
- Số instance discovery, lỗi chọn instance và lỗi gọi dịch vụ.
- Refresh được phát tới đâu, phiên bản cấu hình có hiệu lực và độ trễ hội tụ.
- Tác vụ định kỳ thành công, lần kết nối mới và hành vi reconnect.
- Tài nguyên bị controller tạo lại hoặc quyền bị nguồn quản lý cấp lại ngoài dự kiến.

Những mục này là yêu cầu quan sát của hệ thống, không phải tập metric mặc định được Spring Cloud Kubernetes bảo đảm cung cấp. Không đưa giá trị Secret, toàn bộ cấu hình hoặc credential vào log/metric.

### 9.2. Audit hỗ trợ chứng minh điều gì?

Audit API có thể giúp xác định danh tính, verb, resource, namespace và tên object được truy cập. Mức `Metadata` ghi thông tin thao tác mà không ghi body request/response; cấu hình audit phải phù hợp để tránh lưu nội dung Secret. [Kubernetes: Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/).

Đối với ứng dụng chỉ đọc volume, mỗi lần đọc file không tạo một request GET Secret mới từ ứng dụng. Do đó, không có GET trong audit không chứng minh tiến trình không dùng credential.

Cũng phải biết dữ liệu audit có được bật, có bao phủ loại request cần xét và có đủ thời gian lưu không. Một khoảng trống thu thập không phải bằng chứng quyền hoặc tài nguyên đã không được dùng.

### 9.3. Một số lệnh quan sát sau thay đổi

```powershell
kubectl get pods -n shop -l app.kubernetes.io/name=checkout
kubectl get endpointslices -n shop -l kubernetes.io/service-name=checkout
kubectl get events -n shop --sort-by=.lastTimestamp
kubectl logs -n shop -l app.kubernetes.io/name=checkout -c app --since=10m --prefix=true
```

Đối chiếu label và tên container với manifest thật. Events không thay audit hoặc log client để xác định đầy đủ các request API. Tập EndpointSlice của Service không thay việc kiểm tra danh sách instance đã đến DiscoveryClient/LoadBalancer, nhất là khi còn cache hoặc bộ lọc khác.

## 10. Thu dọn theo nguồn quản lý và giữ khả năng phục hồi

### 10.1. Biến báo cáo thành thay đổi cụ thể

Mỗi ứng viên đủ bằng chứng cần có:

| Mục | Nội dung cần xác định |
| --- | --- |
| Đối tượng chính xác | Kind, namespace, tên và đối chiếu UID live khi cần |
| Nguồn sửa | Repository, chart, operator hoặc hệ thống cấp phát thực sự quản lý |
| Lý do loại bỏ | Consumer đã chuyển đi, quyền không còn cần hoặc label hết người đọc |
| Phạm vi ảnh hưởng | Workload, controller, namespace và vòng đời được bao phủ |
| Cách kiểm chứng | Quyền cần giữ/cần bỏ, khởi động và chức năng liên quan |
| Điều kiện dừng | Lỗi discovery, refresh, mount, startup hoặc tác vụ ngoài phạm vi chấp nhận |
| Phục hồi | Manifest nguồn, đường cấp Secret và quyền tối thiểu cần khôi phục |

Xem lại trạng thái live ngay trước khi thực hiện. Snapshot cũ có thể không phản ánh rollout vừa diễn ra hoặc một object cùng tên đã được tạo lại. Khi cơ chế thao tác hỗ trợ điều kiện UID/resourceVersion, dùng điều kiện phù hợp để bảo vệ ý định đối với đúng đối tượng.

Không dùng selector rộng hoặc điều kiện “không có label giữ lại” thay cho danh sách đối tượng đã được rà soát. Một thao tác dry-run có thể giúp kiểm tra request ở lớp API nhưng không chứng minh rằng tài nguyên không có consumer nghiệp vụ.

### 10.2. Với GitOps, Helm hoặc operator

Nếu desired state vẫn khai báo đối tượng, xóa tay trên cluster có thể chỉ tạo drift rồi tài nguyên được tạo lại. Ngược lại, khi bật prune, bỏ một manifest khỏi desired state có thể dẫn tới xóa tài nguyên thật. Flux mô tả rõ garbage collection đối với tài nguyên từng được áp dụng nhưng không còn trong revision hiện tại. [Flux: Kustomization, prune](https://fluxcd.io/flux/components/kustomize/kustomizations/#prune).

Đối với label hoặc rule do controller quản lý, sửa ở nguồn có thẩm quyền. Không cố giữ một chỉnh sửa live đối nghịch với chart hoặc controller đang hòa giải.

Kiểm tra kế hoạch render trước khi áp dụng: có đúng một label, binding hay resource được bỏ không; có kéo theo thay đổi khác của chart không; tài nguyên được giữ để rollback có bị prune không. Khi operator tạo Secret đích, xem cả vòng đời khai báo nguồn và chính sách của operator thay vì chỉ xóa Secret con.

### 10.3. Bỏ nhu cầu trước, bỏ khả năng cấp sau

Một thứ tự điển hình cho cơ chế cũ của `checkout`:

1. Xác nhận nguồn đọc mới và mọi workload liên quan đã chuyển sang hợp đồng được chọn.
2. Kiểm chứng khởi động, discovery và các luồng cập nhật cần giữ.
3. Bỏ label/cấu hình kích hoạt cơ chế cũ nếu nó không còn cần.
4. Thu hồi đúng đường cấp quyền cũ; giữ quyền cho chức năng còn hoạt động.
5. Xác nhận không có template hoặc tác vụ đang chờ dùng tài nguyên cũ.
6. Sau cửa sổ giữ lại hợp lệ, bỏ resource cũ khỏi nguồn quản lý.
7. Quan sát trạng thái reconcile và hành vi ở những mốc kiểm chứng đã định.

Thứ tự cần được điều chỉnh theo quan hệ thật. Không cần giữ một quyền nguy hiểm chỉ để chờ thu dọn một label mô tả; đồng thời không thu hồi quyền mà consumer còn cần trước khi chuyển consumer.

Giữ thay đổi đủ nhỏ để biết phần nào gây tác động. Một đợt vừa đổi Service selector, xóa Secret, bỏ watcher và sửa ClusterRole sẽ khó chứng minh nguyên nhân nếu chức năng suy giảm.

### 10.4. Phục hồi không chỉ là tạo lại tên object

Nếu cần khôi phục, dùng manifest nguồn và đường cấp dữ liệu được phép, sắp thứ tự để tài nguyên có trước workload tham chiếu. Kiểm tra object tạo lại có thể có UID mới, cùng các quan hệ sở hữu và controller liên quan.

Đối với Secret, bản sao YAML hay ciphertext cũ chỉ hữu ích nếu còn khả năng giải mã và credential ở hệ thống đích vẫn hợp lệ. Xóa Secret Kubernetes không tự thu hồi mật khẩu cơ sở dữ liệu; tạo lại Secret cũng không tự làm một mật khẩu đã bị thu hồi hoạt động trở lại.

Nếu chỉ cần phục hồi một chức năng, khôi phục đúng phạm vi cần thiết thay vì cấp `cluster-admin` hoặc toàn bộ quyền cũ để vượt lỗi. Đưa quyết định phục hồi vào nguồn quản lý để controller không tiếp tục làm trạng thái dao động.

Tài nguyên đang `Terminating` cần được kiểm tra owner/controller và finalizer tương ứng. Không gỡ finalizer chỉ để làm danh sách thu dọn trống khi chưa hiểu trách nhiệm vòng đời mà nó bảo vệ.

## 11. Thực hành trong lab và ghi nhận kết quả

### 11.1. Ma trận ứng viên của tình huống

Sau khi thu thập và xác minh đủ bằng chứng, một báo cáo minh họa có thể là:

| Mục | Bằng chứng đã xác nhận | Quyết định |
| --- | --- | --- |
| `checkout-config-r9` | Pod template và nguồn cấu hình đang dùng | Giữ |
| `checkout-config-r8` | Còn nằm trong bộ rollback đã được chấp nhận | Giữ có thời hạn; xét lại khi kết thúc cửa sổ rollback |
| `checkout-config-r6` | Không còn nguồn live/desired state dùng, không thuộc bộ rollback được giữ | Ứng viên bỏ theo thay đổi riêng |
| Label `legacy.example/refresh` | Không còn consumer trong phạm vi đã rà soát | Bỏ đúng key, giữ các label điều khiển còn cần |
| Binding đọc Secret API cũ của runtime | Consumer đã chuyển sang volume; ma trận quyền và thử startup đạt | Thu hồi đường cấp này |
| Secret của `monthly-reconciliation` | CronJob template vẫn tham chiếu | Giữ dù hiện chưa có Pod |
| ClusterRole không có binding trực tiếp nhưng có aggregation | Rule vẫn được tổng hợp cho Role khác | Không coi là thừa chỉ từ kết quả tìm binding |
| Tài nguyên chưa tìm được owner | Phạm vi bằng chứng chưa đầy đủ | Chưa đủ bằng chứng; tiếp tục xác định trách nhiệm |

Các kết luận trong bảng là kết quả giả định sau kiểm chứng, không phải chỉ dẫn để xóa theo tên giống ví dụ trên một cluster thật.

### 11.2. Chuỗi thực hành

Dùng namespace thử nghiệm, cấu hình không nhạy cảm và credential giả hoặc tài khoản thử nghiệm đã giới hạn:

1. Chuẩn bị workload đang dùng cấu hình, một bản dành cho rollback và một bản cũ thật sự không còn cần.
2. Thêm CronJob có Secret riêng nhưng chưa có Pod chạy để thấy giới hạn của việc chỉ quét Pod.
3. Lập inventory và chạy script tham chiếu; ghi rõ tập nguồn được bao phủ.
4. Đối chiếu nguồn property source, selector Service/discovery, watcher và các quyền hiệu lực.
5. Chọn một label cũ không có consumer, tạo diff chỉ bỏ label đó và kiểm chứng các luồng cần giữ.
6. Thu hẹp đường cấp quyền API cũ của runtime; kiểm tra cả hành động được phép và không được phép.
7. Tạo Pod mới hoặc rollout trong lab, kiểm chứng discovery và đường đọc cấu hình vẫn hoạt động.
8. Với tác vụ định kỳ, kiểm chứng lịch/template và chạy thử chức năng bằng quy trình lab phù hợp.
9. Bỏ bản cấu hình đã được xác nhận hết nhu cầu qua nguồn quản lý; kiểm tra controller không tạo lại và không prune bản được giữ.
10. Thực hành phục hồi một mục đã chọn, xác nhận không cần mở quyền rộng ngoài hợp đồng.

Không dùng dữ liệu Secret thật hoặc tài nguyên của ứng dụng khác để minh họa việc thu dọn. Bài thực hành đánh giá chất lượng bằng chứng và khả năng giữ chức năng, không đánh giá bằng số lệnh xóa đã chạy.

### 11.3. Bằng chứng để đóng đợt rà soát

Ghi nhận tối thiểu: danh sách đã xem xét, quyết định theo mục, phạm vi quan sát, revision nguồn quản lý, thay đổi thực tế, ma trận quyền trước/sau, kết quả chức năng và phần chưa đủ bằng chứng.

Các chỉ số tiến triển có thể gồm số mục chưa rõ owner được giải quyết, số đường cấp quyền dư đã bỏ, số label cũ hết consumer được xử lý và số tài nguyên giữ lại có mốc xét lại rõ. Đi kèm là các chỉ số bảo vệ chức năng như lỗi mount/startup, 403 ngoài dự kiến, discovery rỗng và refresh không hội tụ.

Quy định thời điểm rà soát tiếp theo dựa trên lịch phát hành, thay đổi cơ chế cấu hình, rotation credential và vòng đời đội vận hành. Các mục đang giữ có chủ đích cần được xét lại theo điều kiện đã ghi, thay vì tồn tại mãi chỉ vì từng được đánh dấu là cần cho rollback.
