# Thiết kế ranh giới cụm, namespace và môi trường

## 1. Vì sao phải thiết kế ranh giới trước khi triển khai container?

Container giúp đóng gói ứng dụng và phụ thuộc để triển khai nhất quán. Nhưng khi nhiều đội cùng chạy workload trên Kubernetes hoặc một nền tảng container, câu hỏi quan trọng không chỉ là pod chạy ở đâu mà còn là **ai sở hữu workload, ai được thay đổi nó, workload có thể giao tiếp với thành phần nào và một sự cố có thể lan tới đâu**.

Ba khái niệm thường bị dùng lẫn:

- **Cluster (cụm):** một miền điều khiển và thực thi của nền tảng container. Cluster có control plane, node/compute, network, chính sách và vòng đời nâng cấp riêng.
- **Namespace:** một phạm vi logic bên trong Kubernetes cluster để nhóm tài nguyên, đặt tên, gán quyền và áp dụng một số chính sách theo phạm vi.
- **Environment (môi trường):** một giai đoạn hoặc mục đích sử dụng của workload như development, test, staging hay production. Environment có thể tương ứng với một cluster riêng, một tập namespace hoặc một ranh giới cloud/account/subscription/project tùy yêu cầu.

Chọn sai ranh giới có thể gây hậu quả thực tế. Nếu production và development dùng chung một cụm mà quyền, network policy, quota và node isolation không được kiểm soát, một thử nghiệm có thể ảnh hưởng dịch vụ khách hàng. Ngược lại, tạo cluster riêng cho mọi nhánh thử nghiệm có thể tăng chi phí control plane, node, logging, nâng cấp và công trực mà đội ngũ không đủ khả năng duy trì.

Trong module **CLOUD_ARCHITECTURE**, việc tổ chức cluster, namespace và environment là quyết định kiến trúc: cần cân bằng **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành**. Không có sơ đồ phân tách duy nhất cho mọi doanh nghiệp; lựa chọn phải dựa trên mức cô lập cần thiết, chủ sở hữu và cách kiểm chứng.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt cluster boundary, namespace boundary và environment boundary.
2. Lựa chọn mô hình cluster riêng hay dùng chung dựa trên rủi ro, quy mô đội và yêu cầu vận hành.
3. Thiết kế namespace theo ownership, application/domain và vòng đời thay đổi.
4. Áp dụng RBAC, ResourceQuota, LimitRange, NetworkPolicy, admission policy và workload identity phù hợp.
5. Tổ chức dev/test/staging/production để quản lý cấu hình, dữ liệu, secret và phát hành an toàn.
6. Xác định giới hạn của namespace trong multi-tenancy và các bằng chứng cần có để nghiệm thu.

## 2. Mô hình phân tầng ranh giới

Một nền tảng Kubernetes trên cloud thường có nhiều lớp ranh giới. Mỗi lớp kiểm soát một số phạm vi khác nhau:

| Lớp | Đối tượng | Thường kiểm soát | Ví dụ quyết định |
|---|---|---|---|
| Tổ chức/cloud account | Organization, account, subscription, project | Billing, IAM cấp cao, quota cloud, policy tổ chức | Production workload có cần account/subscription riêng? |
| Network boundary | VPC/VNet, subnet, routing, firewall | Kết nối ngoài cụm và giữa các miền mạng | Cluster prod và dev có dùng chung mạng? |
| Cluster | Control plane, node pool, add-on, cluster-scoped resource | Vòng đời, quyền quản trị cụm, failure domain, phiên bản Kubernetes | Nhóm có cần control plane và nâng cấp độc lập? |
| Namespace | Kubernetes API objects có phạm vi namespace | Tên tài nguyên, RBAC scope, quota, một phần policy | Đội Booking sở hữu tài nguyên nào? |
| Workload | Deployment, StatefulSet, Job, Pod, Service | Replica, rollout, cấu hình, sức khỏe ứng dụng | API và worker có scaling riêng không? |
| Container/process | Runtime, filesystem, capability, user | Cô lập tiến trình và quyền ở runtime | Container có chạy non-root và dùng filesystem read-only? |

**Namespace không phải một máy ảo hay một cluster nhỏ.** Nó không tự cung cấp kernel riêng, control plane riêng, failure domain riêng hoặc một ranh giới bảo mật hoàn chỉnh. Pod trong nhiều namespace vẫn có thể dùng chung node, kernel, CNI, control plane và các thành phần cluster-scoped.

### 2.1. Mô hình logic tham khảo

~~~mermaid
flowchart TD
    Org["Cloud organization / account boundary"]
    Org --> Net["Network boundary"]
    Net --> Prod["Production cluster"]
    Net --> NonProd["Non-production cluster"]
    Prod --> SysP["kube-system / platform services"]
    Prod --> BookP["namespace: booking"]
    Prod --> SearchP["namespace: search"]
    NonProd --> SysN["kube-system / platform services"]
    NonProd --> Dev["namespace: booking-dev"]
    NonProd --> Stage["namespace: booking-staging"]
~~~

*Sơ đồ minh họa một cách tổ chức có cluster production riêng và cluster non-production dùng chung. Với workload nhạy cảm hoặc yêu cầu cô lập cao, staging cũng có thể cần cluster riêng; với tổ chức nhỏ, mô hình có thể giản lược nhưng vẫn cần quyền và chính sách rõ.*

## 3. Chọn cluster riêng hay cluster dùng chung?

Đây là quyết định ở cấp nền tảng. Cần đánh giá mức độ cần cô lập control plane, node, network, quyền cluster-admin, chu kỳ nâng cấp, quota cloud và phạm vi lỗi.

| Tiêu chí | Cluster dùng chung | Cluster riêng |
|---|---|---|
| **Cô lập control plane** | Nhiều đội cùng phụ thuộc control plane và cấu hình cluster | Mỗi cụm có control plane/vòng đời riêng |
| **Failure blast radius** | Lỗi CNI, upgrade, admission hoặc cluster-wide resource có thể ảnh hưởng nhiều workload | Có thể giới hạn sự cố trong một cụm nếu các phụ thuộc ngoài cụm được tách phù hợp |
| **Bảo mật** | Cần RBAC, policy, node isolation và quy trình quản trị chặt | Ranh giới mạnh hơn ở cấp cluster, nhưng IAM/network/registry và control plane vẫn cần bảo vệ |
| **Nâng cấp** | Một lịch nâng cấp có thể yêu cầu phối hợp nhiều đội | Có thể chọn lịch và cửa sổ nâng cấp riêng |
| **Sử dụng tài nguyên** | Có thể chia sẻ node/compute và tăng utilization | Có thể cấp tài nguyên riêng nhưng có nguy cơ nhàn rỗi |
| **Chi phí** | Thường ít cluster overhead hơn, nhưng có thể cần node pool lớn và governance | Thêm chi phí control plane nếu tính phí, node nền, logging, network và vận hành |
| **Độ phức tạp** | Ít cụm để duy trì nhưng governance và phối hợp nhiều tenant phức tạp | Cô lập rõ hơn nhưng phải quản lý nhiều cụm, version, policy và add-on |
| **Phù hợp** | Đội có trust level tương đối gần, workload không cần ranh giới mạnh, platform team đủ năng lực quản trị | Production/regulated workload, nhiều trust domain, yêu cầu nâng cấp hoặc lỗi độc lập |

### 3.1. Khi nào nên tách cluster?

Cân nhắc cluster riêng khi có một hoặc nhiều lý do rõ:

- **Production so với non-production:** yêu cầu cô lập quyền, dữ liệu, thay đổi và failure domain cao.
- **Khác biệt về trust:** workload thuộc đội/đối tác không được tin cậy ngang nhau, hoặc có nghĩa vụ bảo mật riêng.
- **Nâng cấp và add-on:** một workload cần phiên bản, CNI, CSI, service mesh hoặc cấu hình cluster khác biệt không thể đáp ứng an toàn trong cùng cụm.
- **Quy mô và quota:** workload có tải lớn hoặc nhu cầu node/accelerator riêng gây ảnh hưởng chia sẻ.
- **Khả năng chịu lỗi:** một cụm dùng làm failure domain riêng để hạn chế tác động của upgrade, sự cố control plane hoặc cấu hình cluster-wide.
- **Quyền quản trị:** cần tách người có thể cấp cluster-admin, tạo CRD, admission webhook hoặc thay network plugin.
- **Ràng buộc dữ liệu/vị trí:** yêu cầu region, network path hoặc residency không thể đáp ứng trong cụm hiện tại.

Cluster riêng chỉ có giá trị khi các phụ thuộc quan trọng cũng được xem xét. Hai cluster trong cùng VPC, cùng DNS, cùng registry, cùng CI/CD và cùng tài khoản quản trị root vẫn có thể chia sẻ nhiều rủi ro.

### 3.2. Khi nào cluster dùng chung là hợp lý?

- Nhiều nhóm ứng dụng có mức độ tin cậy và phân loại dữ liệu gần nhau.
- Platform team quản trị tập trung, tự động hóa RBAC, policy, quota, network và nâng cấp.
- Các workload có thể chia sẻ node pool mà vẫn đạt yêu cầu noisy-neighbor và availability.
- Nhu cầu tự chủ chưa đủ lớn để biện minh cho chi phí cụm riêng.
- Có cơ chế xử lý sự cố và giới hạn quyền ở namespace/workload được kiểm chứng.

**Không quyết định chỉ dựa trên số đội hoặc số pod.** Cluster dùng chung với 5 đội có thể an toàn hơn cluster riêng không được quản trị; cũng có thể kém phù hợp nếu một trong năm đội có quyền cluster-admin và mức rủi ro cao.

## 4. Thiết kế namespace theo ownership và vòng đời

Namespace hữu ích để tạo phạm vi đặt tên và áp dụng một số chính sách. Cách đặt namespace cần phản ánh **ai chịu trách nhiệm**, **nhóm tài nguyên nào thay đổi cùng nhau** và **vòng đời nào cần quản lý**.

| Mô hình | Ví dụ | Ưu điểm | Hạn chế |
|---|---|---|---|
| Theo đội | team-booking, team-search | Ownership rõ, dễ giao quyền | Một đội sở hữu nhiều ứng dụng có vòng đời khác nhau |
| Theo ứng dụng/domain | booking, catalog, payment | Quan sát và quản lý chính sách theo application | Cần quản lý quyền nhiều namespace cho một team |
| Theo môi trường | booking-dev, booking-stage, booking-prod | Tên thể hiện môi trường; dễ áp policy khác nhau | Tăng số namespace; dễ tạo khác biệt cấu hình nếu không tự động hóa |
| Theo tenant khách hàng | tenant-a, tenant-b | Có thể hữu ích cho workload nội bộ theo tenant | Không đủ làm ranh giới security cho tenant không tin cậy |
| Kết hợp | Cluster prod có booking, search, payment; cluster non-prod có booking-dev, booking-test | Linh hoạt theo ownership và rủi ro | Cần chuẩn naming/label và catalog rõ ràng |

Không có quy tắc đặt namespace duy nhất. Tránh chia theo từng loại Kubernetes object vì làm ownership và policy rời rạc. Cũng tránh tạo namespace cho từng nhánh Git ngắn hạn nếu không có lifecycle automation và cleanup.

### 4.1. Một namespace nên có owner và metadata

Ví dụ label chuẩn:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: booking-prod
  labels:
    app.kubernetes.io/part-of: rental-platform
    environment: production
    owner-team: booking
    data-classification: confidential
    cost-center: product-booking
~~~

Label chỉ là metadata để selector, policy hoặc cost tooling sử dụng; nó không tự cấp quyền hay bảo vệ dữ liệu. Cần kiểm soát ai có quyền sửa label mang ý nghĩa bảo mật/chi phí và kiểm tra sự nhất quán tại admission hoặc pipeline.

Một namespace có owner rõ nên kèm nhóm/platform contact, người trực on-call, phân loại dữ liệu, yêu cầu network access, quota, LimitRange, policy, cách triển khai, dashboard, backup nếu có state, environment, cost center và vòng đời dự kiến.

## 5. Namespace giới hạn tới đâu?

Kubernetes namespace cung cấp một số cơ chế scope, nhưng **không tự ngăn toàn bộ tương tác giữa namespace**.

| Cơ chế | Phạm vi | Điều cần nhớ |
|---|---|---|
| RBAC Role/RoleBinding | API permissions trong namespace | Người dùng có thể vẫn có ClusterRoleBinding hoặc quyền rộng khác |
| ResourceQuota | Tổng mức sử dụng tài nguyên/object trong namespace | Không giới hạn toàn bộ chi phí cloud hoặc mọi tài nguyên cấp node |
| LimitRange | Default/min/max cho resource requests/limits và một số field theo loại object | Không thay thế capacity planning và quota |
| NetworkPolicy | Traffic pod-to-pod/namespace theo CNI hỗ trợ | Phải xác nhận CNI hỗ trợ, policy isolation và default behavior |
| Pod Security Admission | Các mức bảo mật pod theo namespace labels | Chỉ kiểm soát một số cấu hình pod; không thay thế runtime/kernel security |
| Admission policy/webhook | Kiểm tra hoặc chặn object khi API nhận | Cần bảo vệ webhook, xử lý availability và ngoại lệ |
| Secret | Dữ liệu cấu hình nhạy cảm qua API | Cần encryption at rest, RBAC, external secret integration và rotation phù hợp |

Những tài nguyên như Node, PersistentVolume, StorageClass, CRD, ClusterRole, webhook, nhiều loại policy và một số add-on không đơn giản là tài nguyên thuộc namespace theo cùng cách Deployment hay Service. Người có quyền cluster-level có thể tác động tới nhiều tenant. Vì vậy namespace không đủ để cách ly một tenant độc hại hoặc dữ liệu chịu yêu cầu cô lập cao.

Nếu cần trust boundary mạnh, hãy xem xét cluster riêng, cloud account/project riêng, node/VM isolation hoặc cơ chế chuyên biệt tùy threat model. Cần đánh giá cả control plane, kernel, network, storage, credentials và đường quản trị.

## 6. RBAC: ai được làm gì trong namespace?

**Role-Based Access Control (RBAC)** cấp quyền cho subject (user, group hoặc service account) thông qua Role/ClusterRole và RoleBinding/ClusterRoleBinding.

- **Role** định nghĩa quyền trong một namespace.
- **RoleBinding** gán quyền cho subject trong namespace mà binding tồn tại.
- **ClusterRole** định nghĩa tập quyền có thể dùng ở phạm vi cluster hoặc được tham chiếu ở namespace.
- **ClusterRoleBinding** gán quyền cluster-wide theo phạm vi của ClusterRole.

Ví dụ một nhóm developer chỉ được xem và cập nhật một số workload trong namespace booking-dev:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: booking-developer
  namespace: booking-dev
rules:
  - apiGroups: ["apps"]
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch", "update", "patch"]
  - apiGroups: [""]
    resources: ["pods", "services", "configmaps"]
    verbs: ["get", "list", "watch"]
~~~

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: booking-developer-binding
  namespace: booking-dev
subjects:
  - kind: Group
    name: booking-developers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: booking-developer
  apiGroup: rbac.authorization.k8s.io
~~~

Ví dụ chỉ minh họa scope API. Trong môi trường thực, cần xác minh API groups/verbs cụ thể, authentication mapping, quyền rollout và quyền đọc log. Không cấp wildcard hoặc cluster-admin cho developer chỉ để giải quyết một thao tác. Cũng cần xem quyền gián tiếp: đọc Secret, tạo Pod hoặc sửa workload có thể cho phép lấy dữ liệu nhạy cảm hoặc chạy code với service account của workload.

### Kiểm tra quyền trước khi bàn giao

~~~bash
kubectl auth can-i list pods -n booking-dev --as-group=booking-developers
kubectl auth can-i create secrets -n booking-dev --as-group=booking-developers
kubectl auth can-i get nodes
kubectl get rolebindings -n booking-dev
kubectl get clusterrolebindings
~~~

Các lệnh giả định caller có quyền impersonation thích hợp. Nếu không có quyền impersonation, hãy thử qua danh tính nhóm thực tế hoặc pipeline kiểm thử quyền được kiểm soát. Kết quả no cho một thao tác không chứng minh mọi đường truy cập khác cũng bị chặn.

## 7. ResourceQuota và LimitRange

Trong cluster dùng chung, một đội có thể vô tình tạo hàng trăm pod hoặc request CPU/memory quá lớn. **ResourceQuota** giới hạn tổng resource request/limit hoặc số lượng object theo namespace. **LimitRange** đặt default/min/max cho container hoặc object thuộc phạm vi hỗ trợ.

Ví dụ:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: booking-quota
  namespace: booking-dev
spec:
  hard:
    requests.cpu: "8"
    requests.memory: 16Gi
    limits.cpu: "16"
    limits.memory: 32Gi
    pods: "40"
    persistentvolumeclaims: "10"
~~~

~~~yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: container-defaults
  namespace: booking-dev
spec:
  limits:
    - type: Container
      defaultRequest:
        cpu: 100m
        memory: 128Mi
      default:
        cpu: "1"
        memory: 512Mi
      min:
        cpu: 50m
        memory: 64Mi
      max:
        cpu: "2"
        memory: 4Gi
~~~

Giá trị chỉ là **ví dụ** và phải được hiệu chỉnh bằng load test, sizing, node capacity và quota cloud. Khi thiếu requests, scheduler khó lập kế hoạch; khi đặt limits quá thấp, workload có thể bị throttling hoặc OOMKilled. Quota cũng không phải billing budget: traffic, load balancer, storage, NAT và log có thể phát sinh chi phí ngoài phạm vi quota này.

## 8. NetworkPolicy: kiểm soát traffic giữa các namespace

NetworkPolicy cho phép xác định pod nào có thể ingress/egress theo selector, namespace selector, IP block, port và protocol. Hiệu lực phụ thuộc CNI/plugin thực thi policy; phải kiểm tra nền tảng cluster có hỗ trợ và chế độ thực tế.

Ví dụ: cô lập ingress cho pod trong namespace booking-prod, sau đó cho phép traffic từ pod thuộc namespace edge có label phù hợp:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-edge-to-booking
  namespace: booking-prod
spec:
  podSelector:
    matchLabels:
      app: booking-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              network-zone: edge
          podSelector:
            matchLabels:
              app: gateway
      ports:
        - protocol: TCP
          port: 8080
~~~

Hai selector đặt cùng một phần tử trong from nên được kết hợp theo quan hệ AND: pod cần thỏa cả namespace lẫn pod label. Nếu tách chúng thành hai phần tử riêng trong danh sách from, mỗi phần tử có thể được diễn giải như một nguồn cho phép riêng (OR).

Ví dụ chỉ quản lý ingress của các pod được selector chọn. Nó không tự tạo egress allowlist, không thay firewall cloud, không giải quyết IAM và không bảo đảm policy bao phủ hostNetwork hoặc mọi loại traffic do CNI định nghĩa. Khi áp default-deny, cần cho phép đúng DNS, monitoring, health check và dependency cần thiết để tránh cắt chính luồng nền tảng.

## 9. Tổ chức môi trường development, test, staging và production

Environment đại diện cho mục đích và mức độ ổn định của workload. Mỗi môi trường có thể khác nhau về dữ liệu, quyền, capacity, domain name, secret, kết nối và lịch phát hành.

| Môi trường | Mục đích | Đặc điểm nên có | Điều cần kiểm soát |
|---|---|---|---|
| **Development** | Phát triển và kiểm thử nhanh | Tài nguyên nhỏ, tạo/hủy linh hoạt, mock dependency khi phù hợp | Không dùng dữ liệu khách hàng thật ngoài phạm vi được duyệt |
| **Test / QA** | Kiểm thử tích hợp, regression, acceptance | Cấu hình gần production cho các khía cạnh cần kiểm chứng | Dữ liệu test có kiểm soát, seed/reset và tính lặp lại |
| **Staging / Pre-production** | Kiểm tra candidate release | Version, network path, policy và monitoring tương đồng ở mức cần thiết | Phê duyệt thay đổi, smoke/performance test, dữ liệu đã xử lý |
| **Production** | Phục vụ khách hàng và nghiệp vụ thật | SLO, backup, audit, on-call, rollback/roll-forward | Quyền tối thiểu, thay đổi có kiểm soát và data protection |

Không cần tất cả môi trường giống nhau tuyệt đối. Staging có thể ít replica hơn nhưng nên giữ các đặc tính kiến trúc mà đợt kiểm thử cần xác nhận như ingress/TLS, network policy, loại database, migration và observability. Nếu staging dùng network path khác production, nó có thể bỏ sót lỗi routing/DNS.

### 9.1. Cluster riêng cho từng môi trường

~~~mermaid
flowchart TD
    Platform["Container platform"]
    Platform --> DevCluster["Dev cluster"]
    Platform --> TestCluster["Test cluster"]
    Platform --> ProdCluster["Production cluster"]
    DevCluster --> DevNs["booking-dev"]
    TestCluster --> TestNs["booking-test"]
    ProdCluster --> ProdNs["booking-prod"]
~~~

Mô hình này tách control plane, nâng cấp và failure domain; đổi lại tạo thêm chi phí, tài nguyên nhàn rỗi, pipeline và vận hành nhiều cụm.

### 9.2. Cluster non-production chung, production riêng

~~~mermaid
flowchart TD
    Dev["Non-production cluster"]
    Prod["Production cluster"]
    Dev --> D["namespace: booking-dev"]
    Dev --> T["namespace: booking-test"]
    Prod --> P["namespace: booking-prod"]
~~~

Đây là phương án cân bằng thường dùng cho tổ chức vừa: dev/test chia sẻ cụm theo chính sách, production tách riêng. Tuy vậy phải bảo vệ node, API, quota và network của các namespace dev/test trong cluster dùng chung.

### 9.3. Cluster dùng chung cho mọi môi trường

Có thể giảm chi phí hạ tầng và đơn giản hóa quản trị khi workload nhỏ và trust level phù hợp. Nhưng nếu dev có quyền tạo workload tùy ý, dùng tài nguyên chung và có thể ảnh hưởng production, ranh giới namespace đơn thuần không đủ. Cần có bằng chứng về RBAC, admission, policy, quota, node isolation và blast radius; nếu không đạt yêu cầu, nên tách cluster hoặc account/network.

## 10. Quản lý cấu hình và secret theo môi trường

Container image nên được **promote qua các môi trường** theo cùng một build artifact đã định danh (ví dụ digest), còn cấu hình được cung cấp theo môi trường. Điều này giảm nguy cơ staging và production chạy binary khác nhau dù cùng được gọi là một release.

Phân biệt:

- **Image:** mã ứng dụng và dependencies đã build, gắn version/digest.
- **ConfigMap:** cấu hình không nhạy cảm, chẳng hạn feature flag hoặc endpoint theo môi trường.
- **Secret:** dữ liệu nhạy cảm như token, password, certificate; cần kiểm soát RBAC, encryption at rest, rotation và nguồn cấp phù hợp.
- **Resource requests/limits:** có thể khác theo capacity từng môi trường nhưng cần đo và quản lý version.
- **Network policy/ingress:** có thể siết chặt hơn ở production, cần đảm bảo đúng dependency và đường health check.
- **Data:** dev/test nên dùng dữ liệu tổng hợp, synthetic hoặc đã masking theo chính sách; không sao chép dữ liệu nhạy cảm tùy tiện.

Ví dụ cấu hình theo môi trường:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: booking-runtime
  namespace: booking-staging
data:
  LOG_LEVEL: "INFO"
  PAYMENT_MODE: "sandbox"
  FEATURE_NEW_CHECKOUT: "true"
~~~

Không lưu secret thật vào ConfigMap, Git hoặc ví dụ tài liệu. Với production, dùng secret manager/external secrets integration khi phù hợp, đồng thời kiểm soát quyền của service account và pipeline để tránh workload khác đọc được secret namespace.

## 11. Tổ chức node pool và workload placement

Cluster boundary chỉ là một phần của cô lập. Trong cluster dùng chung, các workload có thể cạnh tranh CPU, memory, disk, network và GPU trên cùng node pool. Nên định nghĩa node pool theo nhu cầu compute và yêu cầu tin cậy khi có lý do:

| Node pool | Workload ví dụ | Thiết kế cần xem xét |
|---|---|---|
| General purpose | API, worker thông thường | Capacity, autoscaling, requests/limits, topology spread |
| Memory optimized | Cache hoặc xử lý dữ liệu trong bộ nhớ | Memory pressure, eviction, giới hạn và chi phí |
| Compute optimized | CPU-heavy worker | CPU requests, throttling, scale theo tải |
| GPU/accelerator | Model inference hoặc xử lý tăng tốc | Device plugin, quota, scheduling, driver và chi phí nhàn rỗi |
| Isolated/regulated | Workload có yêu cầu tin cậy cao hơn | Taint/toleration, node identity, dedicated pool hoặc cluster riêng |

**NodeSelector, affinity, taints/tolerations không thay thế ranh giới security.** Chúng điều khiển nơi pod được schedule. Cần kết hợp RBAC, admission, network policy, runtime security, node hardening và cloud IAM.

Các workload stateful cần cân nhắc PersistentVolume, StorageClass, topology và backup. Pod chạy trong namespace riêng không có nghĩa volume của nó được cô lập quyền quản trị hay được backup tự động.

## 12. Multi-tenancy: một cluster phục vụ nhiều đội hoặc khách hàng

Multi-tenancy có thể mang hai nghĩa:

1. **Platform tenancy:** nhiều nhóm phát triển/đơn vị dùng chung cluster.
2. **Application tenancy:** nhiều khách hàng/tenant sử dụng cùng ứng dụng và dữ liệu.

Hai bài toán này khác nhau. Một namespace cho mỗi team có thể hỗ trợ platform tenancy; không tự giải quyết application tenancy. Ứng dụng vẫn phải kiểm tra tenant authorization, truy cập dữ liệu theo tenant, audit và quota nghiệp vụ.

| Loại người dùng | Mức tin cậy tương đối | Gợi ý kiến trúc |
|---|---|---|
| Các team nội bộ cùng quy trình bảo mật | Có thể chia sẻ nền tảng với guardrail | Namespace/role/quota/network policy, platform team quản trị cluster |
| Nhóm dự án có quyền triển khai nhưng không quản trị nền tảng | Cần giới hạn quyền API và runtime | Namespace riêng, RBAC chặt, admission, node/network controls |
| Workload đối tác hoặc code do bên ngoài cung cấp | Mức độ tin cậy thấp | Cân nhắc cluster/account riêng, workload sandbox và kiểm soát egress mạnh |
| Tenant khách hàng có nghĩa vụ cô lập dữ liệu cao | Phụ thuộc threat model và hợp đồng | Có thể cần namespace, cluster, account hoặc deployment riêng; xác minh storage, identity và network |

### Ma trận kiểm soát tối thiểu trong cluster dùng chung

- Namespace ownership và naming được quản lý.
- RBAC tránh cluster-admin cho team workload; rà soát quyền gián tiếp qua Pod/Secret/ServiceAccount.
- ResourceQuota và LimitRange để tránh noisy neighbor ở mức request/object.
- NetworkPolicy có default-deny phù hợp và allowlist cho luồng cần thiết; CNI thực thi đã được xác nhận.
- Pod Security Admission/admission policy để kiểm soát privileged, hostPath, hostNetwork, hostPID, capabilities và image policy.
- Workload identity riêng, quyền cloud tối thiểu; tránh service account chung cho mọi namespace.
- Node pool và runtime isolation phù hợp; hạn chế daemon/host access.
- Central audit/logging và owner nhận alert.
- Quy trình thu hồi tenant, tài nguyên, secret, volume và quyền khi rời nền tảng.

Nếu tenant có thể chạy mã tùy ý hoặc chủ động tìm cách thoát cô lập, **không nên coi namespace là sandbox an toàn độc lập**. Hãy đánh giá threat model và cơ chế isolation mạnh hơn.

## 13. GitOps, IaC và giữ môi trường nhất quán

Tạo namespace bằng tay và sửa RBAC qua lệnh ad-hoc dễ làm drift giữa dev, staging và production. Có thể quản lý declarative bằng IaC/GitOps:

1. **Cluster provisioning:** Terraform hoặc công cụ cloud/IaC tạo cluster, network, node pool, identity integration và logging.
2. **Bootstrap platform:** cài CNI, ingress controller, DNS, CSI, metrics, policy engine và GitOps agent theo thứ tự phụ thuộc.
3. **Platform baseline:** namespace chuẩn, RBAC, quota, NetworkPolicy, Pod Security Admission/admission policy.
4. **Workload delivery:** image digest, manifests/Helm/Kustomize, config không nhạy cảm và tham chiếu secrets.
5. **Promotion:** thay đổi được review; cùng artifact đi qua môi trường, config/policy được kiểm soát theo target.
6. **Drift detection:** đối chiếu trạng thái cluster và desired state; đánh giá trước khi tự reconcile các thay đổi nhạy cảm.

Ví dụ cấu trúc repository:

~~~text
platform/
  clusters/
    dev/
    staging/
    production/
  policies/
    pod-security/
    network/
    quotas/
  namespaces/
    booking/
    catalog/
apps/
  booking/
    base/
    overlays/
      dev/
      staging/
      production/
~~~

Đây là cấu trúc minh họa. Tách repository hay dùng monorepo cần dựa vào ownership, review permissions và quy trình promotion. Nếu mọi người có quyền merge vào thư mục production mà không có policy gate, GitOps không tự làm production an toàn.

### 13.1. Ví dụ Kustomize overlay

~~~yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: booking-staging
resources:
  - ../../base
images:
  - name: registry.example.com/booking-api
    newTag: "2026.11.18"
~~~

Trong production, nên ưu tiên image cố định bằng digest cho khả năng tái lập và kiểm chứng; tên tag chỉ là minh họa. Không để secret value trong manifest Git; dùng cơ chế tích hợp secret phù hợp.

## 14. Nâng cấp cluster và tính nhất quán môi trường

Cluster là một đơn vị có vòng đời. Phải quản lý version Kubernetes, CNI/CSI, ingress, admission controller, CRD, node image và autoscaler. Nhiều namespace trong cùng cụm cùng chịu ảnh hưởng khi một thay đổi cluster-wide lỗi.

Một chiến lược nâng cấp tham khảo:

1. Theo dõi version support và thời điểm hết hỗ trợ của Kubernetes/cloud provider.
2. Kiểm tra API deprecation, compatibility của CRD, controller và addon.
3. Nâng cấp dev cluster trước, chạy test workload và platform smoke test.
4. Nâng cấp staging hoặc một canary cluster với workload đại diện.
5. Kiểm tra pod disruption budget, capacity, drain behavior, persistent workload và topology.
6. Lên lịch production, quan sát lỗi và latency, chuẩn bị rollback/mitigation phù hợp.

Không nên giả định có thể downgrade control plane hoặc node version tùy ý. Cách rollback phụ thuộc nhà cung cấp và phiên bản; cần có kế hoạch khôi phục đã được xác minh.

Staging không bắt buộc có cùng số node và capacity production, nhưng nên giữ tương đồng ở ingress/TLS, Kubernetes/CNI/CSI, network/DNS, policy, secret delivery, rollout và telemetry đối với những khía cạnh cần kiểm chứng. Nếu staging rút gọn policy hay dùng quyền admin để triển khai, kết quả kiểm thử không chứng minh production sẽ hoạt động như mong muốn.

## 15. Quan sát và xử lý sự cố theo ranh giới

Mỗi ranh giới cần có dashboard, log và owner để biết lỗi thuộc cluster, namespace hay ứng dụng.

| Phạm vi | Tín hiệu cần theo dõi | Ví dụ vấn đề |
|---|---|---|
| Control plane | API availability/latency, admission errors, audit, version health | API server chậm, webhook timeout |
| Node/pool | CPU, memory pressure, disk, kubelet, node readiness | Node NotReady, eviction, image pull chậm |
| Namespace | Quota usage, pod restart, pending pods, policy deny | ResourceQuota hết hạn mức, NetworkPolicy chặn |
| Workload | Replica availability, readiness/liveness, request latency/error | CrashLoopBackOff, OOMKilled, readiness fail |
| Network | DNS error, CNI, connection reset, flow deny, ingress/LB status | DNS sai, route/firewall, SNAT |
| Storage | PVC pending, attach/mount error, latency, backup status | StorageClass sai, zone mismatch, thiếu quyền |
| Delivery | GitOps sync/health, admission rejection, deployment history | Desired state lỗi hoặc image không kéo được |

### Quy trình phân loại sự cố

1. Xác định pod, namespace, cluster, node, environment và thời điểm.
2. Kiểm tra get/describe để nhận sự kiện scheduler, admission, volume và kubelet.
3. Kiểm tra logs/events của workload; xác định có khởi động được và readiness pass không.
4. Kiểm tra DNS, Service, EndpointSlice, ingress, NetworkPolicy và firewall cloud.
5. Kiểm tra RBAC, service account, workload identity và quyền tới cloud dependency.
6. Đối chiếu quota, node capacity, image registry, storage và version.
7. Xác định phạm vi ảnh hưởng ở namespace hay cả cluster, rồi khắc phục trong phạm vi nhỏ.

Một pod Pending có thể do thiếu CPU/memory request, node affinity, taint, quota hoặc PVC; không mặc định là lỗi scheduler. Một pod Running cũng chưa chắc readiness hoặc kết nối nghiệp vụ thành công.

### Một số lệnh kiểm tra cơ bản

~~~bash
kubectl get namespaces
kubectl get pods -n booking-prod -o wide
kubectl describe pod booking-api-7d9f -n booking-prod
kubectl get events -n booking-prod --sort-by=.lastTimestamp
kubectl get networkpolicy -n booking-prod
kubectl get resourcequota,limitrange -n booking-prod
kubectl get endpointslices -n booking-prod
kubectl top pods -n booking-prod
~~~

Quyền đọc resource/event/metrics phụ thuộc RBAC và add-on. Khi điều tra production, tránh đưa Secret values hay dữ liệu cá nhân vào terminal output hoặc kênh chia sẻ.

## 16. Case study: quyết định tổ chức Kubernetes cho nền tảng đặt phòng

**Bối cảnh:** một doanh nghiệp có ba nhóm: Booking, Search và Payments. Mỗi nhóm có dev, QA và production. Booking và Payments xử lý dữ liệu khách hàng/giao dịch; Search chủ yếu tạo chỉ mục và phục vụ truy vấn đọc. Platform team có khả năng trực 24/7 nhưng quy mô còn nhỏ. Công ty muốn dùng managed Kubernetes.

### 16.1. So sánh ba phương án

| Phương án | Mô tả | Điểm mạnh | Rủi ro/chi phí |
|---|---|---|---|
| **A: Một cluster cho tất cả** | 9 namespace (3 môi trường × 3 nhóm) | Ít cluster overhead, chia sẻ node và add-on | Failure/control-plane chung; khó đáp ứng mức cô lập production nếu governance yếu |
| **B: Dev/QA chung, production riêng** | Một cluster non-prod với 6 namespace; một cluster prod với 3 namespace | Cân bằng chi phí và tách failure/upgrade của production | Non-prod vẫn cần hạn chế noisy neighbor; prod cluster có blast radius chung giữa 3 nhóm |
| **C: Cluster production theo domain nhạy cảm** | Non-prod chung; Booking và Payments có cluster prod riêng, Search prod tùy nhu cầu | Tách trust, data path và lịch nâng cấp theo độ nhạy | Nhiều cụm, log, policy, upgrade và network để vận hành |

### 16.2. Một đề xuất giai đoạn đầu

Chọn **B** làm baseline nếu đánh giá threat model cho thấy ba nhóm production có thể cùng trust domain, chia sẻ failure domain và tuân thủ được guardrail chung. Cluster non-prod được giới hạn quyền, quota và dữ liệu; cluster prod có RBAC riêng, network policy, admission controls, node pool phù hợp, logging và quy trình nâng cấp chặt.

Nếu Payments chịu yêu cầu cô lập hoặc quản trị key/identity khác biệt, hoặc nhóm cần chu kỳ thay đổi độc lập hơn, chuyển sang **C** cho Payments trước; không cần tách tất cả chỉ để giữ tính đối xứng. Nếu dữ liệu và quy định yêu cầu isolation ở cloud account/network, cluster riêng một mình chưa đủ.

### 16.3. Bản đồ namespace và chính sách

| Cluster | Namespace | Owner | Chính sách nổi bật |
|---|---|---|---|
| Non-prod | booking-dev, booking-qa | Booking team | Quota nhỏ, dữ liệu giả lập, RBAC developer |
| Non-prod | search-dev, search-qa | Search team | Quota theo workload đọc/chỉ mục, egress giới hạn |
| Non-prod | payments-dev, payments-qa | Payments team | Provider sandbox, secret staging, không dùng credential production |
| Prod | booking, search, payments | Từng product team | RBAC vận hành, default-deny phù hợp, requests/limits, audit, alert |

Các namespace thuộc production vẫn cần kiểm soát giao tiếp. Ví dụ Booking có thể gọi Payment API qua service identity/mTLS theo thiết kế, nhưng không cần quyền đọc Secret của Payments. NetworkPolicy giới hạn IP/port; authorization ở Payment quyết định hành động nghiệp vụ.

### 16.4. Điều kiện nghiệm thu

- Developer của Booking không thể đọc Secret của Payments hoặc tạo ClusterRoleBinding.
- Workload trong booking-prod chỉ gọi đúng dependency cần thiết.
- Tạo pod vượt quota bị từ chối có thông báo rõ.
- Image không đạt policy (ví dụ registry không được phép hoặc cấu hình privileged bị cấm) không được admit.
- Nâng cấp non-prod không ảnh hưởng control plane production.
- Có dashboard và on-call owner nhận sự cố cluster/namespace/workload.
- Dữ liệu production không bị sao chép vào QA khi chưa masking và phê duyệt.

## 17. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| **Xem namespace như security boundary tuyệt đối** | Team có thể vượt phạm vi qua cluster-level quyền hoặc node/shared kernel | Đánh giá threat model; tách cluster/account khi cần |
| **Một cluster cho mọi môi trường mà không policy** | Dev gây ảnh hưởng production, noisy neighbor | Tách môi trường hoặc áp RBAC, quota, network, admission và node isolation có kiểm chứng |
| **Tạo cluster cho từng team không có platform automation** | Chi phí và công nâng cấp/monitor tăng nhanh | Dùng shared cluster có kiểm soát hoặc xây cluster vending trước |
| **Namespace theo từng nhánh ngắn hạn** | Tích tụ tài nguyên mồ côi và secret/volume không thu hồi | TTL, owner, cleanup job và lifecycle rõ |
| **Chỉ giới hạn CPU/memory mà không quota object** | Có thể tạo quá nhiều pod, PVC hoặc load balancer | Dùng quota phù hợp với tài nguyên và cloud service |
| **NetworkPolicy có nhưng CNI không thực thi** | Tưởng rằng traffic bị chặn trong khi thực tế không có hiệu lực | Kiểm thử từ pod nguồn/đích và xác nhận CNI |
| **Mọi nhóm đều có cluster-admin** | Ranh giới namespace mất ý nghĩa | Role tối thiểu, break-glass có audit |
| **Staging khác production quá nhiều** | Kiểm thử không phát hiện lỗi thật | Giữ tương đồng các thuộc tính cần kiểm chứng |
| **Dùng tag/label để thay IAM** | Metadata bị sửa vẫn có thể làm policy sai | Admission/permissions và policy độc lập |
| **Không có owner cho CRD/webhook/add-on** | Lỗi cluster-wide và nâng cấp khó | Cluster add-on catalogue, owner, version và runbook |

## 18. Checklist thiết kế và nghiệm thu ranh giới

### Cluster

- [ ] Có lý do rõ để dùng cluster chung hay riêng dựa trên trust, failure domain, upgrade, quota và chi phí.
- [ ] Cloud account/network, control plane, cluster identity và người có cluster-admin được kiểm soát.
- [ ] Có node pool, autoscaling, version policy, add-on ownership và quy trình nâng cấp.
- [ ] Các phụ thuộc dùng chung (DNS, registry, network, CI/CD, storage) đã được xem xét trong blast radius.

### Namespace

- [ ] Tên, owner, environment, data classification và cost metadata được thống nhất.
- [ ] RBAC giới hạn quyền đúng namespace; kiểm tra cả quyền gián tiếp và cluster-wide.
- [ ] Có ResourceQuota, LimitRange và chính sách vòng đời.
- [ ] NetworkPolicy được thực thi bởi CNI; đã thử cả allow và deny.
- [ ] Pod Security/admission, Secret access và workload identity được kiểm soát.
- [ ] Cluster-scoped resources không bị nhầm là tài nguyên do namespace cô lập.

### Environment và vận hành

- [ ] Dev/test/staging/prod có ranh giới, quyền, dữ liệu và cấu hình phù hợp.
- [ ] Image artifact được promote nhất quán; secret/config được tách theo environment.
- [ ] Staging tương đồng production ở network, policy, version và delivery flow cần kiểm chứng.
- [ ] Có telemetry/alert/runbook theo cluster, namespace và workload.
- [ ] Có quy trình cấp/thu hồi namespace, xử lý drift, incident và nâng cấp.
- [ ] Đã ghi rõ các rủi ro tồn dư, người chấp nhận và điều kiện tách ranh giới mạnh hơn.

## 19. Bài tập thực hành

**Bối cảnh:** Một công ty SaaS có bốn team phát triển; hai workload xử lý dữ liệu khách hàng nhạy cảm, hai workload public-read. Tất cả muốn triển khai lên một managed Kubernetes platform. Platform team chỉ có ba kỹ sư; production cần bảo trì có kế hoạch, dev cần tự phục vụ nhanh. Các team muốn mỗi team có quyền admin trong namespace của mình.

Hãy đề xuất:

1. Số cluster ban đầu và lý do phân chia môi trường, trust domain, failure domain.
2. Cách đặt namespace, owner, labels và lifecycle.
3. Bộ RBAC cho developer, release pipeline, on-call operator và platform administrator.
4. ResourceQuota, LimitRange và NetworkPolicy tối thiểu cho từng nhóm workload.
5. Admission/pod security rules nào nên áp dụng, ngoại lệ được duyệt thế nào?
6. Đường đi từ commit tới production: image promotion, GitOps/IaC, secret và rollback.
7. Những tín hiệu cần thu thập để chứng minh namespace/cluster boundary thực sự có hiệu lực.
8. Điều kiện nào khiến công ty tách thêm cluster hoặc cloud account trong sáu tháng tới?

**Gợi ý:** Quyền admin trong namespace cần được cụ thể hóa thành API operations; tránh quyền tạo workload tùy ý nếu có thể truy cập node, hostPath hoặc Secret của workload đặc quyền. Xác định trust domain và phân loại dữ liệu trước khi quyết định shared cluster. Platform team ít người nên ưu tiên module/policy dùng lại và self-service có guardrail, không tự động tạo một cluster mới cho mọi yêu cầu.

## 20. Ghi nhớ

**Cluster** là ranh giới lớn hơn về control plane, vòng đời và failure domain; **namespace** là phạm vi logic để tổ chức tài nguyên và áp dụng một số quyền/chính sách; **environment** là mục đích và giai đoạn của workload. Ba khái niệm liên hệ nhưng không thể thay thế lẫn nhau.

Thiết kế tốt bắt đầu từ **ownership, trust, data classification, failure impact, nhu cầu nâng cấp, năng lực vận hành và chi phí**. Namespace đơn thuần không phải ranh giới bảo mật hoàn chỉnh; cluster riêng cũng không tự đảm bảo dữ liệu và network đã cô lập. Cần kết hợp RBAC, quota, network policy, admission, workload identity, node isolation, telemetry và quy trình vận hành, rồi kiểm chứng bằng phép thử thực tế.
