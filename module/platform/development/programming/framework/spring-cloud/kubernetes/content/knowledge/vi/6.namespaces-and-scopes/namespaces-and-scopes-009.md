# Thiết kế ranh giới truy cập cho nhiều nhóm ứng dụng

Khi nhiều nhóm cùng dùng một Kubernetes cluster, namespace không chỉ là cách sắp xếp tài nguyên. Nó là một phần của ranh giới tên, quyền truy cập, network policy, quota, ownership và vận hành. Nếu mọi nhóm dùng chung namespace hoặc mọi workload được cấp ClusterRole rộng, một lỗi cấu hình ở một ứng dụng có thể ảnh hưởng tới nhiều nhóm khác.

Một thiết kế ranh giới tốt phải trả lời được:

- Nhóm nào sở hữu workload và resource?
- Ứng dụng nào được gọi ứng dụng nào?
- Service discovery có nhìn thấy namespace nào?
- ServiceAccount nào được phép đọc hoặc thay đổi Kubernetes API?
- Mỗi namespace có giới hạn tài nguyên và policy mạng ra sao?
- Spring Cloud Kubernetes integration cần quyền ở cấp nào?
- Khi một team bị lỗi hoặc credential bị lộ, phạm vi ảnh hưởng dừng ở đâu?

Bài học thuộc chương **Namespace và phạm vi** của module **SPRING_CLOUD_KUBERNETES**. Mục tiêu là thiết kế namespace cho nhiều nhóm ứng dụng, tách quyền và traffic, giới hạn discovery cross-namespace, kết hợp RBAC với NetworkPolicy/Quota, và giữ các tích hợp Spring Cloud Kubernetes ở phạm vi thật sự cần.

## 1. Namespace là ranh giới logic, không phải ranh giới bảo mật duy nhất

Namespace giúp tổ chức tài nguyên và tạo scope cho tên cùng một số chính sách:

- Service, ConfigMap, Secret, Deployment và Pod có namespace.
- Role và RoleBinding có scope namespace.
- ResourceQuota và LimitRange thường áp dụng theo namespace.
- NetworkPolicy có thể chọn Pod và namespace.
- DNS Service thường bao gồm tên namespace.
- Audit và ownership có thể gắn với namespace.

Nhưng namespace không tự ngăn mọi traffic hoặc mọi API access. Một ClusterRoleBinding có thể cấp quyền cho ServiceAccount trên nhiều namespace. NetworkPolicy phải được bật và cấu hình để giới hạn traffic. Node, cluster-level resource, admission policy và platform controller nằm ngoài phạm vi namespace thông thường.

Có thể hình dung các lớp ranh giới:

~~~text
Cluster
  |
  +--> Namespace ownership
  |       |
  |       +--> RBAC
  |       +--> ResourceQuota / LimitRange
  |       +--> NetworkPolicy
  |       +--> Service discovery scope
  |
  +--> Cluster-level platform controls
          |
          +--> Nodes, CRD, admission, DNS, API server
~~~

Không nên coi namespace là một “vách tường tuyệt đối”. Hãy kết hợp nhiều lớp, vì mỗi lớp ngăn một loại truy cập khác nhau.

## 2. Chọn chiến lược namespace

Có nhiều cách chia namespace:

| Chiến lược | Ví dụ | Phù hợp khi | Rủi ro |
| --- | --- | --- | --- |
| Theo team | team-orders, team-billing | Team sở hữu vòng đời riêng | Service dùng chung cần thiết kế cross-namespace |
| Theo môi trường | dev, staging, production | Muốn tách environment rõ | Nhiều team cùng chạm một namespace |
| Theo ứng dụng | orders, billing, catalog | Mỗi ứng dụng có policy riêng | Tăng số namespace và overhead vận hành |
| Theo team + môi trường | orders-prod, orders-staging | Cần tách ownership và environment | Quy ước tên, quota, policy phức tạp hơn |
| Namespace dùng chung | shared-platform | Một số dịch vụ nền tảng thật sự dùng chung | Dễ thành vùng quyền rộng và khó quy trách nhiệm |

Không có một sơ đồ đúng cho mọi tổ chức. Quyết định nên dựa trên:

- Ranh giới ownership.
- Ranh giới dữ liệu và compliance.
- Mức độc lập khi rollout/rollback.
- Chính sách mạng.
- Quota và chi phí.
- Cách cấp quyền cho team.
- Nhu cầu discovery và gọi cross-namespace.
- Khả năng audit, backup và dọn dẹp.

Nếu production và development dùng cùng namespace, một Role hoặc NetworkPolicy thử nghiệm có thể ảnh hưởng workload production. Nếu mọi team production dùng chung namespace, khó cấp quyền theo ownership tối thiểu.

Một mô hình dễ giải thích là team + environment:

~~~text
orders-dev
orders-staging
orders-prod

billing-dev
billing-staging
billing-prod
~~~

Tên thật cần theo quy ước platform. Điều quan trọng là từ namespace có thể suy ra ownership, environment và policy áp dụng.

## 3. Namespace không nên chứa workload không cùng ownership

Trong một namespace, các thành phần thường chia sẻ:

- DNS search context.
- Một số quota.
- Policy mặc định.
- Quyền được cấp cho ServiceAccount.
- Quy trình rollout và observability.
- Tập resource dễ nhìn thấy trong dashboard.

Đặt workload của nhiều team vào cùng namespace có thể làm:

- Resource name đụng nhau.
- ConfigMap/Secret bị tham chiếu nhầm.
- RoleBinding cấp quá rộng.
- NetworkPolicy khó diễn đạt.
- Quota không phản ánh trách nhiệm.
- Một team xóa hoặc sửa resource của team khác.
- Log và metric khó phân biệt ownership.

Nếu bắt buộc dùng namespace chung cho shared platform, hãy tách ServiceAccount, label, RoleBinding và convention resource rõ ràng. Không dùng ServiceAccount default cho tất cả workload.

## 4. Label và annotation cho ownership

Label giúp áp dụng selector, policy và truy vấn. Một bộ label có thể gồm:

~~~yaml
metadata:
  labels:
    app.kubernetes.io/name: order-api
    app.kubernetes.io/part-of: commerce
    app.kubernetes.io/managed-by: platform
    app.kubernetes.io/owner: team-orders
    app.kubernetes.io/environment: production
~~~

Cần phân biệt:

- Label dùng để chọn Pod, truy vấn hoặc áp policy.
- Annotation chứa metadata không dùng trực tiếp làm selector thông thường.
- Namespace name là scope chính, label namespace có thể hỗ trợ NetworkPolicy hoặc inventory.
- Không đưa Secret hoặc token vào label/annotation vì chúng có thể xuất hiện trong API và log.

Deployment selector nên ổn định và không chứa label thay đổi theo từng release nếu điều đó làm mất quan hệ quản lý. Service selector cần chọn đúng Pod của ứng dụng, không chọn cả workload của team chỉ vì nhãn team chung.

Một quy ước label tốt giúp trả lời:

- Pod thuộc team nào?
- Ứng dụng nào?
- Environment nào?
- Có phải workload production không?
- Policy nào áp dụng?
- Service nào được phép gọi?

## 5. ServiceAccount là danh tính của workload

Mỗi workload nên dùng ServiceAccount riêng hoặc một ServiceAccount có scope rõ:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-api
  namespace: orders-prod
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: orders-prod
spec:
  template:
    spec:
      serviceAccountName: order-api
      containers:
        - name: order-api
          image: registry.example.com/commerce/order-api:1.0.0
~~~

Không nên dùng default ServiceAccount cho tất cả ứng dụng. Nếu một Pod bị compromise, token của default account có thể có quyền không rõ do nhiều người đã thêm binding.

Nếu ứng dụng chỉ gọi Service qua DNS và nhận ConfigMap/Secret qua env hoặc volume, có thể tắt automount token:

~~~yaml
spec:
  automountServiceAccountToken: false
~~~

Nếu Spring Cloud Kubernetes đọc Kubernetes API trực tiếp, token hoặc cơ chế auth tương ứng phải được cung cấp. Khi đó, ServiceAccount cần Role phù hợp và không nên dùng token của nhóm khác.

ServiceAccount không đại diện cho team theo nghĩa con người. Nó đại diện cho workload runtime. Quyền của developer, CI/CD và runtime nên được tách, dù cùng namespace.

## 6. RBAC namespaced và cluster-wide

RBAC có hai phạm vi chính:

| Loại | Phạm vi | Khi dùng |
| --- | --- | --- |
| Role | Một namespace | Workload đọc resource trong namespace của mình |
| RoleBinding | Gắn Role trong namespace | Cấp Role cho ServiceAccount/user/group |
| ClusterRole | Cluster hoặc resource không namespace | Platform controller hoặc quyền dùng lại |
| ClusterRoleBinding | Gắn ClusterRole ở phạm vi cluster | Chỉ dùng khi cần và được review |

Ví dụ ứng dụng orders-prod chỉ đọc ConfigMap của chính nó:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-config-reader
  namespace: orders-prod
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["order-settings"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-config-reader
  namespace: orders-prod
subjects:
  - kind: ServiceAccount
    name: order-api
    namespace: orders-prod
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-config-reader
~~~

Nếu client cần list/watch ConfigMap, resourceNames và verbs phải được thiết kế lại theo request thực tế. Nếu ứng dụng chỉ cần một key được inject bằng volume, không cấp quyền đọc API chỉ vì resource nguồn là ConfigMap.

ClusterRole không xấu nếu dùng cho một platform controller thật sự cần nhiều namespace, nhưng phải có lý do, resource/verb hẹp, audit và quy trình review. Không dùng ClusterRoleBinding để tránh lỗi 403 trong một workload cụ thể.

## 7. Discovery trong namespace và cross-namespace

Một ứng dụng có thể gọi Service trong namespace của nó bằng DNS:

~~~text
http://catalog-api
~~~

Gọi Service ở namespace khác cần hostname có namespace:

~~~text
http://catalog-api.catalog-prod
~~~

Tên DNS giúp định vị Service nhưng NetworkPolicy vẫn có thể chặn traffic. Nếu dùng DiscoveryClient trực tiếp, phạm vi API resource cũng cần được quyết định:

- Chỉ đọc Service trong namespace hiện tại.
- Đọc Service/EndpointSlice trong danh sách namespace cho phép.
- Đọc toàn cluster qua ClusterRole.
- Gọi Discovery Server có filter và authorization riêng.

Nếu ứng dụng không cần danh sách instance, DNS thường giảm quyền và giảm phụ thuộc. Nếu cần discovery abstraction, hãy thêm namespace vào cache key và response context:

~~~text
orders-prod/catalog-api
catalog-prod/catalog-api
~~~

Không chọn instance đầu tiên nếu có thể có cùng serviceId ở nhiều namespace. Caller phải biết namespace hoặc Discovery Server phải trả identity đầy đủ.

## 8. NetworkPolicy là ranh giới traffic

RBAC kiểm soát Kubernetes API request. NetworkPolicy kiểm soát Pod traffic. Hai lớp không thay thế nhau.

Ví dụ chính sách default deny ingress trong namespace:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: orders-prod
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

Cho phép catalog-api nhận traffic từ order-api cùng namespace:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-order-to-catalog
  namespace: catalog-prod
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: catalog-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: orders-prod
          podSelector:
            matchLabels:
              app.kubernetes.io/name: order-api
      ports:
        - protocol: TCP
          port: 8080
~~~

Chi tiết hỗ trợ namespace label và behavior phụ thuộc CNI/cluster. Hãy kiểm tra policy engine thực tế. Khi dùng namespaceSelector kết hợp podSelector trong cùng một phần tử from, điều kiện thường được hiểu là Pod phải thỏa cả hai selector; cách viết cần được review cẩn thận.

Egress tới Kubernetes API và egress tới Service nghiệp vụ nên được coi là hai nhu cầu khác nhau. Một application có thể cần API access nhưng không cần gọi mọi namespace. Một application có thể gọi catalog Service nhưng không cần Kubernetes API.

## 9. Namespace labels và policy governance

Platform có thể gắn label cho namespace để policy dùng chung:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orders-prod
  labels:
    owner: team-orders
    environment: production
    network-zone: application
    policy-tier: restricted
~~~

Label namespace có thể được dùng trong NetworkPolicy hoặc admission policy. Không nên cho team tự sửa label quyết định policy nếu họ có quyền patch namespace. Namespace label ownership cần được quản lý bởi platform hoặc admission controller.

Nếu label selector là một phần của security boundary, hãy bảo vệ nguồn tạo/sửa namespace. Một typo hoặc label sai có thể làm policy cho phép hoặc chặn traffic ngoài ý muốn.

## 10. ResourceQuota và LimitRange

Namespace boundary không chỉ là quyền mà còn là tài nguyên. ResourceQuota giới hạn tổng resource hoặc số object:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: orders-prod-quota
  namespace: orders-prod
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
    pods: "40"
    services: "20"
    secrets: "50"
    configmaps: "50"
~~~

LimitRange đặt default hoặc giới hạn cho từng container:

~~~yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: orders-prod-limits
  namespace: orders-prod
spec:
  limits:
    - type: Container
      defaultRequest:
        cpu: 100m
        memory: 256Mi
      default:
        cpu: 500m
        memory: 512Mi
      max:
        cpu: "2"
        memory: 4Gi
~~~

Quota và limit ảnh hưởng Spring Cloud Kubernetes gián tiếp:

- Rollout tạo Pod mới có thể bị quota từ chối.
- Watcher/Discovery Server cần request/limit riêng.
- Tăng replica để xử lý cache hoặc API load có thể vượt quota.
- Pod không schedule được làm readiness và discovery thay đổi.
- Quota cho Secret/ConfigMap có thể làm deploy cấu hình mới thất bại.

Không dùng quota như ranh giới quyền. Quota không ngăn một Pod đọc Secret nếu RBAC cho phép; nó chỉ giới hạn consumption/object count.

## 11. Secret và dữ liệu giữa các nhóm

Secret namespaced thường được đọc trong namespace của nó. Một team không nên đọc Secret của team khác chỉ vì hai ứng dụng có cùng cluster.

Nguyên tắc:

- Tạo Secret trong namespace sở hữu dữ liệu.
- Cấp get Secret cho đúng ServiceAccount cần dùng.
- Không dùng ClusterRole đọc mọi Secret nếu chỉ cần một namespace.
- Không chia sẻ credential bằng cách copy Secret vào nhiều namespace nếu có cơ chế secret management tốt hơn.
- Không đưa Secret vào label, annotation, log hoặc discovery response.
- Tách Secret nghiệp vụ và Secret dùng cho Kubernetes API.
- Audit ai đọc Secret và từ workload nào.

Nếu ứng dụng ở orders-prod cần gọi catalog-prod, credential tới catalog API nên do catalog owner/platform thiết kế. Không tự cấp quyền đọc toàn bộ Secret catalog-prod để lấy một token.

## 12. ConfigMap và config discovery theo ownership

ConfigMap không nhạy cảm như Secret nhưng vẫn có thể chứa policy, endpoint hoặc feature flag ảnh hưởng nghiệp vụ. Không nên cho mọi team patch ConfigMap trong namespace dùng chung.

Một workload Spring có thể nhận ConfigMap qua:

- env/configMapKeyRef.
- volume mount.
- Spring Cloud Kubernetes đọc API.
- Configuration Watcher gửi tín hiệu refresh.

Mỗi cách có phạm vi và quyền khác. Nếu dùng env/volume, ứng dụng có thể không cần get ConfigMap. Nếu dùng API hoặc watcher, cấp Role cho đúng workload.

Configuration Watcher dùng chung cho nhiều namespace cần:

- Allowlist namespace.
- Filter resource và label.
- ServiceAccount riêng.
- Quyền list/watch tối thiểu.
- Authorization khi gửi tín hiệu tới application.
- Cơ chế chống gửi refresh nhầm namespace.
- Quan sát để biết replica nào đã áp dụng.

Không nên để watcher có quyền toàn cluster chỉ vì muốn nhận một ConfigMap của hai namespace. Tách watcher theo vùng hoặc dùng filter/Role phù hợp.

## 13. Namespace và service discovery của Spring Cloud

Spring Cloud Kubernetes discovery có thể cung cấp abstraction cho service/instance, nhưng namespace scope phải được xác định theo integration và release train. Các câu hỏi cần trả lời:

1. Discovery client dùng Kubernetes API trực tiếp hay Discovery Server?
2. Resource nào được đọc: Service, Endpoints, EndpointSlice hoặc resource khác?
3. Namespace lấy từ property, Pod metadata hay default client?
4. Có filter theo label không?
5. Cache key có chứa namespace không?
6. Có list/watch toàn cluster không?
7. RBAC cần ở application hay Discovery Server?
8. Khi discovery trả instance cross-namespace, caller có được phép gọi network không?

Nếu chỉ cần Service DNS, không nên thêm DiscoveryClient cho mọi application. Nếu cần DiscoveryClient trong namespace, Role namespaced thường là điểm bắt đầu. Nếu cần nhiều namespace, hãy xem xét Discovery Server hoặc một platform abstraction thay vì cấp ClusterRole cho hàng chục workload.

Discovery không cấp quyền gọi network. Nhìn thấy instance qua API không đồng nghĩa NetworkPolicy cho phép TCP tới Pod hoặc Service. Hai lớp phải được kiểm tra riêng.

## 14. Cross-namespace service contract

Nếu nhiều nhóm cần gọi một Service chung, hãy công bố contract:

| Thành phần | Ví dụ |
| --- | --- |
| Namespace đích | catalog-prod |
| Service name | catalog-api |
| Port name | http |
| DNS | catalog-api.catalog-prod |
| Protocol | HTTPS hoặc HTTP nội bộ theo policy |
| Authentication | mTLS, token hoặc workload identity |
| Network source | namespace/team allowlist |
| SLO/readiness | Điều kiện nhận traffic |
| Owner | team-catalog |
| Change policy | Versioning và deprecation |

Contract rõ giúp caller không đọc Kubernetes API chỉ để đoán endpoint. Service owner có thể thay Pod, node và EndpointSlice mà giữ Service contract ổn định.

Nếu dùng gateway/facade, caller gọi gateway contract thay vì discovery mọi backend. Điều này giảm cross-namespace visibility nhưng thêm một hop và dependency. Quyết định nên dựa trên yêu cầu latency, ownership và security.

## 15. Admission policy và guardrail

Platform có thể dùng admission policy để kiểm tra:

- Workload phải có owner label.
- Không dùng default ServiceAccount.
- Không mount Secret ngoài namespace.
- Image phải từ registry được phép.
- Production namespace phải có resource requests/limits.
- Pod phải có readiness/liveness phù hợp.
- Namespace production phải có NetworkPolicy default deny.
- Role không được cấp verbs/resource nhạy cảm ngoài allowlist.
- ClusterRoleBinding phải có phê duyệt.

Admission policy bổ sung guardrail nhưng không thay thế thiết kế ứng dụng. Nếu policy từ chối Deployment, lỗi có thể xuất hiện trước khi Spring khởi động. Đưa policy error vào pipeline và preflight để team biết cách sửa.

Không nên tạo policy dựa trên một label mà team có thể tự đổi nếu label đó quyết định quyền. Ownership của namespace và label cần rõ.

## 16. Chẩn đoán lỗi giữa nhiều namespace

Giả sử order-api trong orders-prod không gọi được catalog-api trong catalog-prod:

1. Hostname có dùng catalog-api.catalog-prod không?
2. Service có tồn tại đúng namespace không?
3. Service có endpoint ready không?
4. NetworkPolicy ở namespace đích có cho phép source namespace không?
5. Egress policy ở orders-prod có cho phép đích không?
6. Service port/targetPort có đúng không?
7. Ứng dụng đích có auth request không?
8. Nếu dùng DiscoveryClient, API RBAC có cho phép nhìn catalog-prod không?
9. Nếu dùng Discovery Server, server có filter/authorization đúng không?
10. DNS, route và CNI có hoạt động không?

Bảng phân biệt:

| Triệu chứng | Khả năng |
| --- | --- |
| DNS không phân giải | Tên/namespace/DNS policy |
| DNS phân giải, TCP timeout | NetworkPolicy, route, CNI, firewall |
| TCP kết nối, HTTP 503 | Service không có endpoint hoặc proxy |
| API discovery 403 | RBAC của ServiceAccount |
| Service call 403 | Auth của ứng dụng đích, không nhất thiết Kubernetes RBAC |
| Resource không tìm thấy | Sai namespace/group/version/name |
| Pod bị pending | Quota, LimitRange, scheduler hoặc resource request |
| Watcher gửi nhầm refresh | Scope/filter/identity của watcher |

HTTP 403 từ business API và HTTP 403 từ Kubernetes API có thể có ý nghĩa khác nhau. Ghi endpoint và request path an toàn để biết response đến từ lớp nào.

## 17. Shared namespace cho platform service

Một số dịch vụ như ingress controller, observability agent hoặc shared discovery server có thể chạy ở namespace platform. Nếu ứng dụng team gọi chúng:

- Service contract phải rõ.
- NetworkPolicy cho phép caller cụ thể.
- API auth của shared service phải phân biệt caller.
- ServiceAccount của shared service không nên được dùng cho ứng dụng team.
- ConfigMap/Secret platform không tự được đọc bởi mọi namespace.
- Quota phải dành đủ cho shared workload.
- Rollout shared service phải có canary/maintenance plan.

Shared namespace không nên trở thành nơi đặt mọi workload “không biết xếp đâu”. Mỗi resource cần owner, policy và vòng đời. Nếu shared service cần đọc tài nguyên của nhiều namespace, đó là platform controller với quyền đặc biệt, không phải lý do cấp ClusterRole cho tất cả application.

## 18. Mô hình triển khai mẫu cho một team

Một namespace production của team orders có thể gồm:

~~~text
Namespace: orders-prod
  |
  +--> order-api Deployment
  +--> order-api ServiceAccount
  +--> order-settings ConfigMap
  +--> order-credentials Secret
  +--> order-api Service
  +--> Role/RoleBinding namespaced
  +--> ResourceQuota / LimitRange
  +--> default-deny NetworkPolicy
  +--> allow policies tới dependency đã phê duyệt
~~~

Ứng dụng chỉ gọi catalog-api.catalog-prod qua network contract. Nếu không cần discovery API, order-api không có quyền đọc Service của catalog-prod. Nếu cần ConfigMap API trong orders-prod, Role chỉ giới hạn resource cần thiết.

Mô hình này giữ ownership rõ: team orders quản lý resource trong orders-prod; team catalog quản lý catalog-prod; platform quản lý namespace labels, admission, DNS, quota baseline và cross-namespace policy.

## 19. Checklist ranh giới nhiều nhóm

Trước khi đưa workload vào cluster, hãy kiểm tra:

- Namespace phản ánh ownership và environment.
- Workload không dùng default ServiceAccount.
- ServiceAccount riêng cho mỗi workload có quyền API.
- Role namespaced được ưu tiên khi đủ dùng.
- ClusterRole/ClusterRoleBinding có lý do và owner rõ.
- ConfigMap/Secret chỉ được đọc bởi workload cần thiết.
- Service DNS và cross-namespace contract được công bố rõ.
- DiscoveryClient chỉ nhìn namespace/resource cần thiết.
- Cache key phân biệt namespace và Service name.
- NetworkPolicy default deny và allow rule đã được kiểm tra thực tế.
- Quota/LimitRange không ngăn rollout hợp lệ.
- Pod có resource requests/limits và readiness.
- Namespace labels không bị workload team tự ý đổi.
- Admission policy có thông báo lỗi dễ hành động.
- Shared platform service có auth và network policy riêng.
- Log/metric có owner/namespace nhưng không lộ Secret.
- Có quy trình xử lý khi một team cần cross-namespace access.
- Có audit và rollback cho thay đổi Role, NetworkPolicy, quota.

## 20. Tự kiểm tra

1. Vì sao namespace không tự là một ranh giới bảo mật hoàn chỉnh?
2. Khi nào nên chia namespace theo team, environment hoặc team + environment?
3. Tại sao mỗi workload nên có ServiceAccount riêng?
4. Role và ClusterRole khác nhau thế nào trong thiết kế nhiều nhóm?
5. NetworkPolicy và RBAC kiểm soát hai loại truy cập nào?
6. Nếu ứng dụng chỉ gọi Service cross-namespace bằng DNS, có cần DiscoveryClient không?
7. Vì sao cache discovery phải phân biệt namespace?
8. Quota có thay thế authorization không?
9. Configuration Watcher dùng chung nhiều namespace cần những guardrail nào?
10. Vì sao HTTP 403 từ business API không đồng nghĩa Kubernetes RBAC sai?
11. Shared namespace nên có những quy tắc ownership nào?
12. Bằng chứng nào cho thấy ranh giới truy cập giữa hai team đang hoạt động đúng?

Thiết kế nhiều nhóm ứng dụng cần nhiều lớp ranh giới phối hợp: namespace cho ownership và naming, ServiceAccount/RBAC cho Kubernetes API, NetworkPolicy cho traffic, quota cho tài nguyên, cùng admission và audit cho guardrail. Với Spring Cloud Kubernetes, hãy bắt đầu từ DNS và Service khi đủ dùng; chỉ mở discovery cross-namespace, ConfigMap/Secret API hoặc watcher khi có contract rõ, quyền tối thiểu và bằng chứng kiểm tra được.

