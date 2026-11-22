# Attached clusters và quản trị Kubernetes bên ngoài GCP

Nhiều tổ chức vận hành Kubernetes đồng thời trên Google Kubernetes Engine (GKE), Amazon EKS, Azure AKS và các cụm tự quản lý trong trung tâm dữ liệu. Mỗi môi trường có Kubernetes API nhưng khác cách cung cấp danh tính, mạng, storage, logs, metrics, nâng cấp và hỗ trợ sự cố. Khi mỗi nhóm dùng một bộ công cụ hoàn toàn riêng, nền tảng dễ xảy ra cấu hình lệch chuẩn, thiếu inventory, khó kiểm toán quyền và khó áp dụng chính sách nhất quán.

**GKE attached clusters** là khả năng kết nối những cụm Kubernetes đã tồn tại **ngoài Google Cloud** vào mô hình quản trị được Google Cloud hỗ trợ. Kết hợp với **fleet management**, tổ chức có thể quản lý inventory, quyền truy cập và một số tính năng về cấu hình, bảo mật, quan sát trên các cụm có nền tảng khác nhau. Đây là một phần của chiến lược hạ tầng lai và đa đám mây, không phải quá trình tự động di chuyển ứng dụng sang GCP.

Điểm quan trọng nhất: **attach không đồng nghĩa Google Cloud sở hữu hoặc quản lý toàn bộ control plane, worker nodes và storage của cluster gốc**. Nhà cung cấp hoặc đội vận hành ban đầu vẫn chịu trách nhiệm về các thành phần đó. Bài học hướng dẫn thiết kế kiến trúc, đăng ký và xác minh attached cluster, phân quyền IAM/RBAC, truy cập qua Connect Gateway, GitOps, policy, observability, bảo mật và cách vận hành đáng tin cậy.

## 1. Bài toán Kubernetes lai và đa đám mây

Giả sử công ty có bốn môi trường:

- EKS phục vụ hệ thống giao dịch tại AWS.
- AKS chạy ứng dụng hỗ trợ khách hàng tại Azure.
- Kubernetes tự quản lý trong data center để xử lý dữ liệu nội bộ.
- GKE chạy API và dịch vụ phân tích tại Google Cloud.

Tất cả có thể dùng Deployment, Service, StatefulSet hoặc ConfigMap nhưng cách triển khai hạ tầng lại khác nhau.

| Lớp | Khác biệt cần quản trị |
|---|---|
| Identity | AWS IAM, Microsoft Entra ID, Google Cloud IAM và Kubernetes RBAC |
| Cluster | Phiên bản Kubernetes, distribution, node pool và upgrade |
| Networking | VPC/VNet, CNI, ingress, DNS, firewall và routing |
| Storage | CSI driver, PersistentVolume, snapshot và backup |
| Security | Admission policies, image policy, workload identity, secrets |
| Observability | Logs, metrics, traces, alert và retention |
| Delivery | Helm, Kustomize, GitOps, CI/CD và artifact registry |
| DR | Region, backup, cluster rebuild và data recovery |

Mục tiêu của quản trị tập trung không phải làm mọi cloud giống hệt nhau mà tạo ra **chuẩn tối thiểu chung** cho inventory, quyền, chính sách, chất lượng và khả năng khôi phục, trong khi vẫn giữ khác biệt cần thiết ở từng provider.

## 2. Phân biệt GKE, attached clusters và fleet

| Khái niệm | Vai trò | Nơi workload chạy |
|---|---|---|
| GKE Standard/Autopilot | Kubernetes được cung cấp trên Google Cloud theo mô hình GKE | Google Cloud |
| GKE Multi-Cloud | Họ sản phẩm quản trị/triển khai Kubernetes trong môi trường đa cloud theo khả năng được hỗ trợ | Google Cloud hoặc nền tảng khác tùy loại |
| GKE attached cluster | Đăng ký cluster Kubernetes đã tồn tại bên ngoài GCP vào lớp quản trị Google Cloud | AWS, Azure hoặc hạ tầng bên ngoài được hỗ trợ |
| Fleet | Nhóm logic các cluster và cấu hình quản trị dùng chung | Nhiều môi trường |
| Fleet membership | Đại diện một cluster đã đăng ký trong fleet | Metadata quản trị tại Google Cloud |

Không nhầm **attached cluster resource** với **fleet membership resource**. Hai loại tài nguyên có API, tên và location có thể khác nhau; việc một membership xuất hiện không có nghĩa mọi tính năng của attached cluster đều đang hoạt động.

### Điều không thay đổi sau attach

- Cluster gốc vẫn dùng control plane, nodes và storage đã có.
- Ứng dụng không tự được di chuyển sang GCP.
- EKS/AKS/on-prem vẫn chịu quy trình upgrade, quota, HA và hỗ trợ của môi trường gốc.
- IAM của Google Cloud không tự thay thế Kubernetes RBAC hoặc quyền quản trị cloud provider.
- Dữ liệu volume/database không được sao chép sang GCP chỉ vì cluster được đăng ký.

**Phạm vi hỗ trợ phụ thuộc distribution, Kubernetes version, loại cluster, tính năng và thời điểm.** Cần kiểm tra tài liệu hỗ trợ trước khi dùng trong production.

## 3. Kiến trúc tham chiếu

Một giải pháp quản trị thường có các lớp:

1. Các cluster Kubernetes ngoài Google Cloud.
2. Thành phần kết nối hoặc agents theo mô hình attached clusters được hỗ trợ.
3. Resource quản lý cluster và fleet trên Google Cloud.
4. Cơ chế truy cập từ xa được phê duyệt như Connect Gateway.
5. GitOps, Policy Controller hoặc công cụ chính sách tương đương.
6. Monitoring, Logging và audit.
7. Quy trình vận hành gốc cho node, networking, storage và backup.

~~~mermaid
flowchart TD
    A[Platform team and CI CD] --> B[Google Cloud fleet]
    B --> C[Cluster inventory and membership]
    B --> D[Approved access and policy]
    B --> E[Monitoring and audit]
    C --> F[Cluster connectivity integration]
    D --> F
    E --> F
    F --> G[EKS at AWS]
    F --> H[AKS at Azure]
    F --> I[On-prem Kubernetes]
    G --> J[AWS control plane and workers]
    H --> K[Azure control plane and workers]
    I --> L[Data-center infrastructure]
~~~

Sơ đồ minh họa kiến trúc logic; không khẳng định mọi attached cluster đều có cùng agent, API hoặc tính năng.

### Management plane và data plane

**Management plane** xử lý inventory, điều khiển, chính sách và truy cập quản trị. **Data plane** thực thi Pods và các kết nối của ứng dụng. Khi kết nối quản trị tới Google Cloud bị gián đoạn, workloads có thể tiếp tục phục vụ nếu vẫn đủ các phụ thuộc runtime, nhưng đồng bộ chính sách, truy cập gateway hoặc quan sát tập trung có thể bị suy giảm.

Một thiết kế tốt phải đo riêng hai loại health này.

## 4. Tiêu chí chọn cluster để kết nối

Trước khi đăng ký một cluster, xác minh:

- Distribution và Kubernetes version được attached clusters hỗ trợ.
- API server và node health đang ổn định.
- CNI, CSI, DNS, admission webhooks và network policies đang hoạt động.
- Có owner chịu trách nhiệm ở provider gốc.
- Có người đủ quyền cài đặt agent/integration và cấu hình identity.
- Có outbound DNS/TLS/HTTPS và proxy phù hợp tới các endpoints cần thiết.
- Có quy định về data residency, logging, audit, key management.
- Có runbook cho lỗi kết nối, certificate expiry, upgrades và detach.
- Có project/billing owner và dự trù chi phí quản lý, logs, egress.

Nên bắt đầu với một cluster **staging** hoặc lab, không chứa dữ liệu thật nhạy cảm. Trong giai đoạn thí điểm, kiểm chứng quyền đọc, inventory, sync và một policy không phá hủy trước khi mở rộng sang production.

## 5. Thiết kế fleet và phạm vi quản trị

Fleet nên phản ánh ranh giới trách nhiệm thực tế. Ví dụ:

~~~text
fleet-platform-staging
  eks-orders-staging
  aks-commerce-staging
  kubernetes-lab

fleet-platform-prod
  eks-orders-prod
  aks-commerce-prod
~~~

Cấu trúc trên là cách phân nhóm minh họa, không phải cú pháp tài nguyên fleet. Một tổ chức có thể sử dụng một hoặc nhiều project/fleet theo giới hạn và chính sách của dịch vụ.

### Quy tắc phân nhóm

- Tách môi trường production và non-production khi cần cô lập quyền và policy.
- Các clusters trong cùng nhóm nên có owner, mức độ tin cậy và baseline phù hợp.
- Gắn labels hoặc inventory về cloud provider, business service, team và environment.
- Không dùng một danh tính deployment toàn quyền cho mọi cluster.
- Đặt tên membership ổn định để dashboards và alerts không mất liên kết.

### Location của resource

Location của attached cluster hoặc fleet membership không nhất thiết là region nơi cluster thực chạy. Một số API dùng global, một số dùng regional location. Khi gọi CLI hoặc API, phải dùng đúng location trả về trong resource name hoặc tài liệu của phiên bản đang dùng.

## 6. Chuẩn bị môi trường Google Cloud

Project quản lý cần có IAM thích hợp, các APIs của GKE Multi-Cloud/fleet và các tính năng thực sự sử dụng. Trước khi bật API hoặc tạo resource, xác định:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Fleet project | Project nào sở hữu membership và chính sách? |
| Billing | Tổ chức nào chi trả dịch vụ quản lý, logging và egress? |
| IAM | Ai được xem inventory, attach/detach, dùng Gateway và sửa policy? |
| APIs | Loại attached cluster và fleet features nào cần bật? |
| Security | Có hạn chế organization policy, VPC-SC hoặc identity không? |
| Location | Resource dùng global/region nào? |
| IaC | Terraform hoặc công cụ nào là source of truth? |

Có thể kiểm tra các APIs đang bật:

~~~bash
gcloud services list --enabled --project="FLEET_PROJECT_ID"
~~~

Để xem nhóm lệnh gcloud của môi trường đang sử dụng:

~~~bash
gcloud container attached clusters --help
gcloud container fleet memberships --help
~~~

Đây là những lệnh chỉ đọc trợ giúp. Không áp dụng một danh sách API hoặc registration flags không được xác minh cho mọi distribution.

## 7. Chuẩn bị phía cluster ngoài GCP

Phía EKS/AKS/on-prem cần một bộ điều kiện riêng:

1. Quyền cluster-admin hoặc một danh tính được ủy quyền đủ cho registration và cài thành phần tích hợp.
2. Quyền cloud provider gốc để cấu hình networking/identity khi quy trình yêu cầu.
3. Outbound connectivity tới endpoint dịch vụ Google phù hợp.
4. DNS, TLS CA trust và proxy settings đúng.
5. Chính sách cài agent/CRD/namespace được bảo mật và kiểm toán.
6. Không có admission policy ngăn mọi component bắt buộc hoạt động.
7. Dự phòng quy trình gỡ agent và hoàn tác thay đổi sau khi thử nghiệm.

Không tự mở Kubernetes API server công khai để một bước onboarding chạy thành công. Tùy mô hình, cơ chế kết nối từ cluster ra ngoài giúp giảm nhu cầu phơi bày endpoint trực tiếp, nhưng phải tuân theo tài liệu sản phẩm.

## 8. Quy trình đăng ký attached cluster

Đăng ký nên được điều phối như một change có thể kiểm chứng:

~~~mermaid
flowchart TD
    A[Assess cluster and owner] --> B[Confirm support and security]
    B --> C[Prepare IAM and network]
    C --> D[Register attached cluster]
    D --> E[Install required integration]
    E --> F[Check cluster and fleet status]
    F --> G[Verify least-privilege access]
    G --> H[Enable pilot policy and observability]
    H --> I[Record inventory and rollback]
~~~

### Các bước chi tiết

- Khảo sát distribution, Kubernetes version và các tính năng cần dùng.
- Dùng quy trình registration chính thức phù hợp với provider và phiên bản.
- Ghi lại tên resource, project, location, membership và service identities.
- Kiểm tra agents/connection components trong cluster.
- Dùng account chỉ đọc xác nhận inventory và health.
- Kiểm tra tích hợp với Gateway, GitOps, Policy Controller và Logging nếu đã chọn.
- Lưu cấu hình và bằng chứng vào hệ thống ticket/IaC.
- Chưa triển khai policy enforce rộng cho đến khi kiểm chứng ở lab.

Lệnh đăng ký có thể khác giữa các loại cluster. Trước khi thực thi, kiểm tra cú pháp trên CLI hiện tại:

~~~bash
gcloud container attached clusters register --help
gcloud container attached clusters list --help
~~~

Nếu CLI đang dùng không hỗ trợ một nhóm lệnh hoặc option, theo hướng dẫn phiên bản được Google Cloud công bố cho loại attached cluster của tổ chức. Không dùng một lệnh ví dụ chưa kiểm chứng như lệnh triển khai production.

## 9. Kiểm tra fleet membership

Sau khi đăng ký, xem danh sách:

~~~bash
gcloud container fleet memberships list \
  --project="FLEET_PROJECT_ID"
~~~

Xem chi tiết membership khi xác định đúng location:

~~~bash
gcloud container fleet memberships describe "MEMBERSHIP_NAME" \
  --project="FLEET_PROJECT_ID" \
  --location="MEMBERSHIP_LOCATION"
~~~

### Những trường cần ghi nhận

- Membership và attached cluster resource name.
- Distribution/version và provider gốc.
- Trạng thái kết nối gần nhất.
- Features được bật và feature health.
- Owner, environment, data classification.
- Thời điểm cập nhật và version của agents.
- Runbook truy cập trực tiếp khi Gateway không sử dụng được.

**Membership tồn tại không đồng nghĩa cluster hoặc workload khỏe.** Kiểm tra Kubernetes nodes/Pods và ứng dụng riêng, đồng thời kiểm tra đồng bộ tính năng nếu có.

## 10. Truy cập cluster qua Connect Gateway

Connect Gateway có thể cung cấp đường truy cập Kubernetes API qua lớp quản trị Google Cloud trong các kịch bản hỗ trợ. Cấu hình truy cập thường yêu cầu Google Cloud IAM lẫn cơ chế xác thực/ủy quyền của cluster.

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant I as Google Cloud IAM
    participant G as Connect Gateway
    participant C as Cluster-side connectivity
    participant K as Kubernetes API server
    O->>I: Authenticate identity
    O->>G: Request access to membership
    G->>I: Check gateway permissions
    G->>C: Forward authorized request
    C->>K: Kubernetes API request
    K-->>O: RBAC-controlled response
~~~

Sơ đồ trình bày luồng khái niệm; chi tiết danh tính, headers và cơ chế agent tùy cấu hình thực tế.

Có thể lấy kubeconfig qua Connect Gateway khi được hỗ trợ:

~~~bash
gcloud container fleet memberships get-credentials "MEMBERSHIP_NAME" \
  --project="FLEET_PROJECT_ID" \
  --location="MEMBERSHIP_LOCATION"
~~~

Sau đó kiểm tra context:

~~~bash
kubectl config get-contexts
kubectl --context="APPROVED_ATTACHED_CONTEXT" get namespaces
~~~

Đừng dùng context mặc định nếu không chắc nó đang trỏ tới cluster nào.

## 11. Phân biệt Google Cloud IAM và Kubernetes RBAC

Có ít nhất hai lớp quyền độc lập:

| Lớp | Kiểm soát |
|---|---|
| Google Cloud IAM | Xem fleet, attached cluster, dùng Gateway, cập nhật membership hoặc features |
| Kubernetes RBAC | Thực hiện các thao tác trên Pod, Deployment, Secret và namespace trong cluster |
| Provider IAM | Sửa EKS/AKS control plane, worker nodes, network và storage tại cloud gốc |
| Admission policies | Cho phép/từ chối manifest theo chuẩn bảo mật |
| Workload identity | Workload gọi Google Cloud API hoặc dịch vụ bên ngoài dưới principal nào |

Một operator có quyền truy cập Gateway không được tự xem là cluster-admin. Ngược lại, Kubernetes RoleBinding không cấp quyền chỉnh Google Cloud project.

### RBAC chỉ đọc theo namespace

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: fleet-lab
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
~~~

Liên kết với group được cluster thực sự xác thực:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: platform-readers
  namespace: fleet-lab
subjects:
  - kind: Group
    name: platform-readers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
~~~

Tên group trong manifest chỉ hoạt động nếu cơ chế xác thực Kubernetes map operator vào group đó. Không giả định IAM group và Kubernetes group tự đồng bộ.

## 12. Danh tính ứng dụng: Workload Identity Federation

Workload chạy ngoài GCP cần danh tính để gọi Cloud Storage, Pub/Sub hoặc Secret Manager. **Attached cluster không tự làm mọi Pod có ADC giống GKE hoặc Cloud Run**.

Một lựa chọn an toàn là Workload Identity Federation cho workload ngoài Google Cloud, với các identity claims từ hệ thống được ủy quyền.

~~~mermaid
flowchart LR
    A[Pod on EKS or AKS] --> B[External identity token]
    B --> C[Google Security Token Service]
    C --> D[Short-lived Google credential]
    D --> E[Cloud Storage or Pub Sub]
    F[Identity pool and provider] --> C
    G[IAM grants on resource] --> E
~~~

### Các lớp cấu hình

- External identity issuer/audience được Google Cloud trust.
- Workload identity pool và provider với attribute mappings chính xác.
- Attribute conditions giới hạn cluster, namespace và service account khi phù hợp.
- IAM trên resource hoặc ủy quyền impersonate Google service account.
- External account credential configuration cho Google Auth Library.
- Cơ chế refresh token và bảo vệ metadata/credential source.

Không chấp nhận mọi token do một identity provider rộng phát hành mà không ràng buộc principal. Tránh service account key JSON dài hạn nếu có thể dùng federation.

### Kiểm thử

Trên project/bucket lab:

1. Pod được cấp phép đọc object cho phép.
2. Pod không được cấp quyền bị từ chối.
3. Không có private key trong container hoặc Git.
4. Access token/ID token không bị in vào logs.
5. IAM có thể bị thu hồi theo quy trình incident.

## 13. GitOps và đồng bộ cấu hình đa cluster

GitOps giúp quản lý manifest bằng pull request, review và một Git revision được kiểm soát. Trong môi trường fleet, có thể dùng Config Sync theo danh sách cluster được hỗ trợ; hoặc Argo CD/Flux khi tổ chức đã chuẩn hóa và cần công cụ khác.

Một cấu trúc repository:

~~~text
platform-config/
  base/
    namespaces/
    rbac/
    networkpolicies/
    observability/
  overlays/
    eks-staging/
    aks-staging/
    eks-prod/
    aks-prod/
~~~

### Nguyên tắc

- Manifest base chỉ chứa phần Kubernetes có thể chia sẻ.
- Các khác biệt IngressClass, StorageClass, CSI, CNI và identity nằm trong overlay.
- Nhánh production có approval phù hợp.
- CI kiểm tra schema, policy và rủi ro quyền trước merge.
- Controllers theo dõi drift, sync errors và health.
- Rollback bằng revert/release đã biết tốt; không chỉnh thủ công lặp lại trên cluster.

Ví dụ Namespace lab:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: fleet-lab
  labels:
    environment: staging
    owner: platform-runtime
~~~

Nếu một manifest bị chỉnh bằng kubectl nhưng GitOps giữ source of truth, controller có thể ghi đè sự thay đổi đó. Cần có quy trình break-glass và cập nhật source control khi xử lý sự cố.

## 14. Policy Controller và chuẩn admission

Một nền tảng multi-cloud cần cùng baseline an toàn mà không làm mất các đặc thù cluster:

- Không cho privileged containers nếu không có ngoại lệ.
- Kiểm soát hostPath, hostNetwork và Linux capabilities.
- Bắt buộc labels owner/environment và image registry đã phê duyệt.
- Hạn chế wildcard RBAC và sử dụng cluster-admin.
- Kiểm tra resource requests/limits hợp lý.
- Quản lý Pod security, image signature và provenance theo hệ thống hỗ trợ.
- Giới hạn namespace hoặc workload truy cập secret nhạy cảm.

### Triển khai theo giai đoạn

1. Viết policy và unit-test với manifests mẫu.
2. Chạy ở chế độ audit hoặc dry-run nếu công cụ hỗ trợ.
3. Đối chiếu violations, false positives và application owners.
4. Tạo exception có lý do, owner, scope và thời hạn.
5. Canary enforce trên namespace/cluster ít rủi ro.
6. Quan sát admission errors và rollout health.
7. Mở rộng từng nhóm cluster.

Không bật đồng thời một policy mới trên tất cả cụm production mà chưa kiểm tra tính tương thích.

### Policy không thay thế network firewall

Admission kiểm tra cấu hình. NetworkPolicy chỉ hoạt động đúng khi CNI hỗ trợ và được cấu hình thích hợp. Cloud firewall, proxy và VPC segmentation vẫn cần có thiết kế riêng tại mỗi provider.

## 15. Mạng và kết nối giữa các cloud

Nên phân loại traffic theo mục đích:

| Đường traffic | Vấn đề cần kiểm tra |
|---|---|
| Cluster agent → Google APIs | DNS, HTTPS, CA, proxy, egress allowlist |
| Operator → Connect Gateway | SSO, IAM, endpoint reachability |
| Pod → Artifact Registry | Registry auth, image pull, egress và latency |
| Pod → Cloud Storage/Pub/Sub | WIF identity, network, quota và data residency |
| Pod → database ở cloud khác | VPN/interconnect, routes, encryption và egress |
| Logs/metrics → Google Cloud | Volume, PII, retention và cost |

Không mở rộng firewall chỉ để hoàn tất bài thử nghiệm. Nếu dùng proxy có TLS interception, phải xác minh nó không phá chuỗi tin cậy mà thành phần kết nối cần.

### Hai loại kết nối độc lập

- **Management traffic:** đăng ký, policy, inventory và truy cập Kubernetes quản trị.
- **Application traffic:** request, database, object, events và phụ thuộc nghiệp vụ.

Khi management traffic lỗi, ứng dụng không nhất thiết lỗi. Ngược lại, Connect Gateway vẫn Connected không bảo đảm traffic tới database hoặc ingress đang tốt.

### Residency

Dữ liệu telemetry, control metadata và application payload không có cùng mức nhạy cảm. Cần ghi rõ những loại dữ liệu nào gửi sang Google Cloud, location và retention. Không giả định attach tự chuyển dữ liệu ứng dụng tới GCP.

## 16. Quan sát logs, metrics và health

Các tín hiệu cần theo dõi:

- Node Ready/NotReady và Pod trạng thái Pending/CrashLoopBackOff.
- Deployment/StatefulSet readiness.
- Admission policy violations.
- GitOps sync/drift.
- Agent connectivity và certificate/token expiry.
- Request latency, error rate, throughput và saturation của ứng dụng.
- Kubernetes audit, IAM changes và access errors.
- Egress volume, billing và resource usage.

Một số tính năng Cloud Logging, Cloud Monitoring hoặc Managed Service for Prometheus có thể được triển khai qua agents/collectors và integrations. **Chỉ đăng ký cluster không bảo đảm toàn bộ logs và metrics sẽ có trong Cloud Monitoring.**

### Thiết kế labels

Các dimensions gợi ý:

~~~text
fleet=platform-production
cluster=eks-orders-prod
provider=aws
environment=production
namespace=orders
workload=orders-api
~~~

Không thêm user ID/request ID hay Pod UID biến động quá nhanh làm metrics labels nếu không có nhu cầu chính đáng; dễ gây cardinality lớn và tăng chi phí.

### Quan sát độc lập

Giữ ít nhất ba nhóm dashboard:

1. Application SLO: availability, latency, error rate.
2. Cluster health: node, Pod, autoscaling, capacity.
3. Management integrations: agent connection, sync, policy, gateway.

## 17. CI/CD và triển khai nhiều cluster

Một artifact nên giữ cùng image digest giữa staging và production, còn manifest sử dụng overlays theo cluster.

~~~mermaid
flowchart TD
    A[Source commit] --> B[Build test scan]
    B --> C[Image digest]
    C --> D[Staging EKS overlay]
    C --> E[Staging AKS overlay]
    D --> F[Staging checks]
    E --> F
    F --> G[Approval]
    G --> H[Production canary]
    H --> I[Observe SLO]
    I --> J[Gradual rollout to remaining clusters]
~~~

Cần phân biệt:

- Cluster chạy được cùng container image không có nghĩa cùng storage/ingress settings.
- Cloud Deploy không nhất thiết hỗ trợ mọi attached cluster như một native GKE target; xác minh support hoặc chọn GitOps phù hợp.
- Secrets và service account không được dùng chung tùy tiện giữa cloud.
- Một lỗi rollout phải được cô lập theo target cluster.

### Luôn chỉ định context

~~~bash
kubectl config get-contexts
kubectl config current-context
kubectl --context="APPROVED_LAB_CONTEXT" get namespaces
~~~

Áp dụng manifest sau khi xác nhận context đúng môi trường:

~~~bash
kubectl --context="APPROVED_LAB_CONTEXT" apply -f namespace.yaml
~~~

Không viết script tự động lặp qua tất cả kubeconfig contexts rồi apply một manifest production duy nhất.

## 18. Storage và dữ liệu khi chạy ngoài GCP

Một attached cluster vẫn dùng CSI drivers và nền tảng lưu trữ gốc. PersistentVolume ở EKS không tự trở thành Persistent Disk trên Google Cloud.

Đối với stateful workload, xác định:

- PersistentVolume provisioner và snapshot support.
- Replication và backup theo region/provider.
- Database ownership, HA, RTO/RPO và retention.
- Key management và quyền decrypt khi DR.
- Khả năng restore trên cluster khác trong cùng cloud hoặc cloud khác.
- Chi phí truyền dữ liệu cross-cloud.

Multi-cloud fleet management không thay thế disaster recovery. Nếu muốn failover ứng dụng giữa các cloud, phải thiết kế data replication, schema, DNS/traffic routing và khả năng nhất quán dữ liệu riêng.

## 19. Nâng cấp cluster, agents và component versions

Kubernetes upgrade cần được điều phối giữa hai lớp:

| Lớp | Trách nhiệm |
|---|---|
| Provider gốc | Control plane, worker nodes, VPC/VNet, CNI, CSI, quotas |
| GCP management | Compatibility với attached-cluster integration, fleet features và Google IAM |
| Platform team | Agents, Config Sync, Policy Controller, GitOps và alerts |
| Application team | API deprecation, CRD compatibility, workloads và SLO |

Quy trình an toàn:

1. Kiểm tra support matrix cluster/agent/Kubernetes version.
2. Xem API deprecations và khả năng rollback.
3. Sao lưu cấu hình và dữ liệu cần bảo vệ.
4. Nâng staging và xác minh các integrations.
5. Kiểm tra Gateway, policy, GitOps và observability.
6. Tiến hành production theo canary/maintenance window.
7. Cập nhật inventory và runbook.

Không chờ Google Cloud nâng node EKS hoặc AKS thay cho owner gốc chỉ vì cluster đã được attach.

## 20. Khi management plane hoặc kết nối lỗi

Một số tình huống cần diễn tập:

| Sự cố | Tác động có thể xảy ra | Phương án |
|---|---|---|
| Agent không kết nối Google Cloud | Gateway hoặc sync có thể suy giảm | Kiểm tra proxy/egress/TLS, giữ truy cập gốc |
| Google IAM/SSO không sẵn sàng | Operator không dùng Gateway được | Break-glass vào cluster gốc |
| GitOps source ngừng hoạt động | Không đồng bộ cấu hình mới | Giữ trạng thái an toàn và retry theo runbook |
| Admission webhook lỗi | Deployment có thể bị chặn tùy failure policy | HA, policy rollback và emergency procedure |
| EKS/AKS region outage | Workload và data plane mất khả năng phục vụ | DR theo cloud gốc |
| Certificate hoặc agent quá cũ | Kết nối quản trị lỗi | Version/cert rotation và giám sát |

### Thiết kế break-glass

- Có danh tính khẩn cấp do cloud provider gốc quản lý.
- Quyền truy cập được khóa và kiểm toán.
- Chỉ dùng khi đáp ứng điều kiện incident.
- Có thời hạn, thu hồi sau xử lý.
- Có buổi diễn tập định kỳ để bảo đảm quy trình thực hiện được.

Đừng đợi tới khi Gateway mất kết nối mới tìm cách tạo tài khoản quản trị gốc.

## 21. Security và shared responsibility

Các lớp cần bảo vệ:

1. Google Cloud IAM cho fleet, Gateway và policy.
2. Provider IAM cho cluster, nodes và network gốc.
3. Kubernetes RBAC cho các resource trong namespace.
4. Admission policy cho Pod, image và RBAC manifests.
5. Workload identity khi Pod gọi Google APIs.
6. Encryption, retention, backup và data classification.
7. Network segmentation và egress controls.
8. Supply chain và source control của manifests.

### Kiểm tra positive và negative paths

- Operator được cấp đúng quyền có thể đọc Pod ở namespace lab.
- Operator khác bị từ chối Gateway.
- Operator read-only không thể delete Deployment.
- Pod không được cấp WIF không thể đọc bucket thử nghiệm.
- Manifest vi phạm policy bị phát hiện ở audit hoặc bị từ chối ở enforce.
- Logs không chứa credentials hoặc PII không cần thiết.

Không cấp cluster-admin cho mọi người chỉ để xử lý một lỗi permission. Phân tích xem lỗi phát sinh tại IAM Gateway, authentication mapping, RBAC hay admission.

## 22. Chi phí và FinOps đa cloud

Việc attach có thể tạo hoặc tăng các nhóm chi phí:

- Chi phí EKS/AKS/on-prem hạ tầng gốc.
- Phí quản lý attached cluster theo mô hình được áp dụng.
- Network egress khi gửi dữ liệu tới Google Cloud.
- Logs/metrics ingestion và retention.
- Artifact Registry download và storage.
- GitOps/CI/CD runners, security scanning, operations.

### Cách đo

Theo dõi cost theo cluster, cloud provider, team, environment và workload. Khi so sánh chi phí hai cloud, phải tính network, storage, observability, SLA và công vận hành, không chỉ CPU/memory.

Giảm lượng logs/metrics gửi xuyên cloud nếu không cần; dùng sampling, retention và lọc secret/PII. Không tắt các tín hiệu an ninh hoặc SLO quan trọng chỉ để giảm chi phí ngắn hạn.

## 23. Troubleshooting attached clusters

| Triệu chứng | Nguyên nhân khả dĩ | Chẩn đoán |
|---|---|---|
| Không thấy cluster trong fleet | Sai project/location, registration chưa hoàn tất | Membership list, resource name |
| Membership tồn tại nhưng disconnected | Agent, DNS, proxy, cert, egress | Agent logs và endpoint connectivity |
| Gateway HTTP 403 | Google IAM thiếu hoặc chính sách tổ chức | Principal và gateway permissions |
| kubectl Forbidden sau khi kết nối | Kubernetes RBAC hoặc group mapping | RoleBinding/ClusterRoleBinding |
| Pod không Ready | CNI, image, storage, workload | Pod events và node status |
| GitOps drift | Repo auth, webhook, policy conflict | Sync status, Git revision |
| Admission từ chối | Constraint không phù hợp | Policy violation và exception |
| Logs/metrics thiếu | Chưa cài collector, IAM hoặc quota lỗi | Collector, export endpoint, billing |
| ImagePullBackOff | Registry auth hoặc network | Image digest, pull secret, egress |
| Sau upgrade bị lỗi | Version skew hoặc CRD incompatibility | Support matrix và agent versions |
| Egress tăng bất thường | Centralized telemetry hoặc image transfer | Usage và billing export |

Một quy trình chẩn đoán hợp lý:

1. Phân biệt lỗi **management** hay **application**.
2. Kiểm tra project, location, membership và owner.
3. Kiểm tra network, agents, DNS và certificates.
4. Kiểm tra IAM và RBAC riêng.
5. Xem GitOps/policy/observability integrations.
6. Xem change gần nhất ở cloud gốc và Google Cloud.
7. Chỉ dùng break-glass khi runbook cho phép.
8. Ghi root cause và remediation rõ ràng.

## 24. Thực hành: attach EKS staging vào fleet

Giả sử công ty có:

- EKS cluster tên **eks-orders-staging**.
- Project fleet **FLEET_PROJECT_ID**.
- GitOps repo có namespace, RBAC và một audit policy.
- Bucket Cloud Storage test với IAM chỉ đọc cho một workload.
- Nhóm platform và AWS owner đã phê duyệt buổi thử nghiệm.

### Giai đoạn A: khảo sát

Ghi Kubernetes distribution/version, region, AWS account, networking, IAM, storage, owner, các policy bắt buộc và yêu cầu version của attached clusters.

### Giai đoạn B: đăng ký

1. Chuẩn bị quyền IAM trên GCP và cluster gốc.
2. Xác minh outbound network.
3. Thực hiện registration theo hướng dẫn chính thức cho distribution/version.
4. Kiểm tra attached cluster resource và fleet membership.
5. Xác minh agents/connectivity và ghi resource IDs.

### Giai đoạn C: truy cập read-only

Dùng danh tính được cấp quyền phù hợp, lấy context qua Gateway khi hỗ trợ:

~~~bash
kubectl config get-contexts
kubectl --context="APPROVED_EKS_CONTEXT" get nodes
kubectl --context="APPROVED_EKS_CONTEXT" get namespaces
~~~

Sau đó dùng một danh tính chỉ đọc thử lệnh xem Pod, đồng thời xác minh không có quyền xóa Deployment.

### Giai đoạn D: chính sách và GitOps

- Tạo namespace fleet-lab từ Git.
- Áp Role/RoleBinding read-only.
- Áp policy audit-only cấm privileged Pod.
- Kiểm tra sync status và violation list.
- Thử revert commit và kiểm tra controller rollback.
- Không mở policy enforce toàn cluster trong buổi học.

### Giai đoạn E: xác thực workload

Cấu hình WIF cho Pod lab theo hướng dẫn danh tính ngoài GCP. Thử đọc đúng object được cấp IAM và xác minh truy cập object ngoài phạm vi bị từ chối.

### Giai đoạn F: tính sẵn sàng

Mô phỏng ngắt đường management trong lab có phê duyệt:

- Ứng dụng vẫn phục vụ?
- Gateway báo kết nối lỗi đúng?
- Có audit/alert?
- Có đường break-glass tới cluster gốc?
- Sau khôi phục, agent và sync hoạt động trở lại?

### Giai đoạn G: đánh giá

Lưu báo cáo gồm cluster/membership IDs, IAM/RBAC tests, feature availability, logs/metrics, thời gian reconnect, chi phí phát sinh và action items có owner.

## 25. Checklist production readiness

### Trước onboarding

- [ ] Distribution/Kubernetes version và tính năng được hỗ trợ.
- [ ] Cluster owner, network owner và platform owner xác nhận trách nhiệm.
- [ ] GCP project, billing, location và IAM được kiểm tra.
- [ ] Quyền provider và Kubernetes được cấp tối thiểu.
- [ ] DNS, egress, proxy, TLS và policy có cấu hình an toàn.
- [ ] Có phương án rollback/detach nếu registration lỗi.

### Sau onboarding

- [ ] Attached resource và fleet membership đúng project/location.
- [ ] Agent connectivity và health được kiểm chứng.
- [ ] Google IAM và Kubernetes RBAC được thử riêng.
- [ ] Gateway sử dụng danh tính được phê duyệt.
- [ ] GitOps source-of-truth, drift detection và policy audit hoạt động.
- [ ] Logs/metrics/audit đạt yêu cầu mà không làm lộ secret.
- [ ] Inventory owner/environment, runbook và upgrade plan cập nhật.

### Vận hành định kỳ

- [ ] Theo dõi version skew và agent/cert lifecycle.
- [ ] Review IAM, RBAC, WIF và break-glass permissions.
- [ ] Policy exemptions có owner và hạn sử dụng.
- [ ] Theo dõi chi phí egress, telemetry và control plane.
- [ ] DR/backup được thử theo RTO/RPO.
- [ ] Kiểm tra GitOps recovery, rollout và rollback.
- [ ] Có quy trình detach khi kết thúc vòng đời.

## 26. Detach, decommission và lỗi thiết kế thường gặp

Khi cần dừng quản trị cluster từ GCP:

1. Xác nhận cluster và workload vẫn được hệ thống gốc quản lý.
2. Kiểm tra dependencies vào Gateway, GitOps, policy và telemetry.
3. Chuyển alert/automation sang kênh thay thế nếu cần.
4. Lưu audit trail và resource inventory theo retention.
5. Gỡ kết nối/agent/membership theo trình tự chính thức.
6. Thu hồi IAM và federation identities không còn sử dụng.
7. Xác minh workloads không bị ảnh hưởng ngoài kế hoạch.
8. Cập nhật inventory và billing ownership.

**Detach không tự xóa cluster EKS/AKS/on-prem.** Ngược lại, xóa cluster gốc trước khi cleanup membership có thể để lại metadata stale.

Các lỗi thường gặp:

| Anti-pattern | Hệ quả |
|---|---|
| Nghĩ attach đồng nghĩa Google quản lý node và upgrade | Không rõ trách nhiệm khi sự cố |
| Mặc định mọi attached cluster có cùng tính năng | Cấu hình/rollout thất bại |
| Cấp cluster-admin cho mọi operator | Blast radius và rủi ro quá lớn |
| Mở API server công khai để hỗ trợ đăng ký | Tăng bề mặt tấn công |
| Nhúng key Google service account vào Pod | Nguy cơ lộ credential |
| Áp policy enforce lên toàn fleet cùng lúc | Chặn deployment hợp lệ |
| Chỉ xem membership Connected | Bỏ sót lỗi SLO ứng dụng |
| Không có đường quản trị gốc | Không xử lý được khi Gateway lỗi |
| Trộn manifest của mọi provider | Lỗi CNI/CSI/Ingress/identity |
| Gửi mọi logs qua cloud khác không kiểm soát | Tăng chi phí và rủi ro dữ liệu |
| Coi fleet là DR | Dữ liệu không được backup/replicate |
| Không cleanup khi decommission | Quyền thừa và inventory sai |

**Kết luận:** GKE attached clusters mở rộng khả năng quản trị Kubernetes của Google Cloud tới những cụm ngoài GCP, giúp tổ chức có inventory, phân quyền và một số công cụ chính sách/quan sát chung. Thành công phụ thuộc vào việc tôn trọng ownership của cloud provider gốc, kiểm tra support matrix, tách IAM/RBAC/workload identity, kiểm soát network, đồng bộ GitOps an toàn và duy trì khả năng vận hành khi management connectivity gặp lỗi. Đây là nền tảng cho quản trị đa đám mây nhất quán mà không đánh mất trách nhiệm đối với từng cụm.

