# Apigee hybrid và yêu cầu triển khai

> **Chương:** API Gateway và Apigee  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Một doanh nghiệp có API phục vụ đối tác qua Internet, trong khi dữ liệu giao dịch và hệ thống backend nằm trong mạng riêng. Doanh nghiệp muốn quản lý API tập trung, áp dụng xác thực, giới hạn lưu lượng và quan sát sử dụng API, nhưng vẫn **tự vận hành đường xử lý request** trên cụm Kubernetes của mình. **Apigee hybrid** được thiết kế cho bài toán này: **management plane** do Google quản lý; **runtime plane** do khách hàng triển khai, vận hành trên nền tảng Kubernetes được hỗ trợ.

Bài thuộc mô-đun **CLOUD_PROVIDERS_GCP**, giúp người học lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa triển khai và kiểm soát độ tin cậy/chi phí qua các tình huống Google Cloud. Trọng tâm ở đây là **điều kiện kiến trúc và vận hành trước khi lắp đặt Apigee hybrid**, không phải một hướng dẫn “chạy một lệnh để có gateway production”.

**Sau bài học, bạn có thể:**

1. Phân biệt Apigee hybrid với API Gateway và Apigee do Google vận hành hoàn toàn.
2. Mô tả vai trò của management plane, runtime plane và luồng đồng bộ cấu hình.
3. Liệt kê thành phần runtime và trách nhiệm vận hành: ingress, Message Processor, Cassandra, Redis/Valkey theo phiên bản, MART, Synchronizer, Apigee Connect và telemetry.
4. Đánh giá Kubernetes platform/version, node pool, lưu trữ, network, DNS/TLS, IAM và Workload Identity trước triển khai.
5. Hiểu quy trình provision organization → environment/group → cluster → identities → overrides → CRDs/Helm → kiểm thử proxy.
6. Lập kế hoạch HA, backup Cassandra, nâng cấp theo chart/version, giám sát và ngân sách.
7. Thực hiện kiểm tra **chỉ đọc** và thiết kế một lab/production readiness checklist mà không tác động nhầm môi trường.

## 1. Chọn đúng giải pháp API management

| Nhu cầu | Google Cloud API Gateway | Apigee được Google quản lý | **Apigee hybrid** |
| --- | --- | --- | --- |
| Định tuyến API, auth và kiểm soát cơ bản | Phù hợp trường hợp tương đối đơn giản | Có, cùng nhiều khả năng API management nâng cao | Có, chính sách được thực thi ở runtime do khách hàng quản lý |
| API products, developer app/keys, quota và analytics doanh nghiệp | Khả năng/hướng tiếp cận khác Apigee | Tập trung trong Apigee | Dùng quản lý Apigee và runtime riêng |
| Ai vận hành runtime gateway? | Google | Google | **Doanh nghiệp**, trên Kubernetes được hỗ trợ |
| Backend tại on-prem/multi-cloud | Có thể kết nối qua kiến trúc thích hợp | Có thể, tùy networking/Apigee deployment | **Hữu ích** khi runtime gần backend/private network |
| Kubernetes/Cassandra/Helm vận hành | Không cần cho riêng gateway | Không cần cho runtime do Google quản lý | **Cần đội ngũ vận hành, quan sát và DR** |
| Chi phí và độ phức tạp | Phù hợp quy mô/feature set nhất định | Gói Apigee + network/usage | **Chi phí Apigee + cluster/storage/network/operations** |

**Không mặc định “hybrid” luôn tốt hơn hoặc rẻ hơn.** Nếu mục tiêu chỉ là công bố vài Cloud Run APIs với OpenAPI/JWT/API key và không cần runtime tự quản lý, API Gateway thường đơn giản hơn. Chọn hybrid khi **yêu cầu địa điểm xử lý, kết nối nội bộ, tuân thủ và mô hình vận hành** thực sự biện minh được cho Kubernetes/Cassandra.

Cũng không nên hiểu “hybrid” là **runtime hoàn toàn offline**: mặt phẳng runtime cần giao tiếp ra ngoài với management plane và các dịch vụ Google Cloud cho đồng bộ, analytics, logs và quản trị.

## 2. Hai mặt phẳng và luồng xử lý

~~~mermaid
flowchart TB
  ADMIN["API platform / security team"] --> MGMT["Google-managed management plane\nUI · Management APIs · API products · Analytics"]
  MGMT -->|"Config, proxy revisions, policies"| SYN["Synchronizer\nCustomer Kubernetes"]
  MGMT <-->|"Apigee Connect: channel do runtime khởi tạo"| CON["Connect Agent ↔ MART"]
  CLIENT["Mobile / partner clients"] --> DNS["DNS + TLS / Load Balancer"]
  DNS --> INGRESS["Apigee ingress gateway"]
  subgraph RUNTIME["Customer-managed runtime plane — Kubernetes"]
    INGRESS --> MP["Message Processors\nVerify key/token · Quota · Routing"]
    SYN --> MP
    MP <--> CASS["Cassandra\nPersistent API runtime state"]
    MP <--> CACHE["Redis / in-memory components"]
    CON
    UDCA["UDCA / Telemetry"]
  end
  MP --> BACK["Private backend\nGKE / Compute Engine / Cloud Run"]
  MP --> UDCA
  UDCA -->|"Analytics, logs, metrics: outbound TLS"| MGMT
~~~

Sơ đồ minh họa **ranh giới trách nhiệm**, không phải tất cả đường liên lạc nội bộ hoặc chính xác nơi mỗi message được lưu. Trong thực tế còn có operator, watcher, cert-manager và các components tùy phiên bản/chức năng.

### 2.1. Management plane do Google vận hành

Gồm các chức năng quản lý như tổ chức (organization), environments, environment groups, API proxies, API products, developer apps, deployment metadata, UI và analytics. Người quản trị định nghĩa/triển khai API proxy thông qua Apigee; **không cần đặt tất cả công cụ quản trị này trong cluster runtime**.

### 2.2. Runtime plane do khách hàng vận hành

Chứa đường xử lý API requests thật: client → ingress → Message Processor thực thi policies → backend → response. Tùy cách bố trí, runtime ở GKE, trung tâm dữ liệu riêng hoặc Kubernetes trên cloud khác. **Bạn chịu trách nhiệm cluster, capacity, security patches, persistent storage, network, HA và upgrade**.

### 2.3. Nếu mất kết nối đến management plane?

**Synchronizer** tải “contract”/cấu hình quản lý về runtime và Message Processors dùng bản đã có tại chỗ. Khi đường đến management plane bị gián đoạn, **API traffic có thể tiếp tục xử lý với cấu hình đã đồng bộ**, miễn ingress/backend/Cassandra và runtime vẫn khỏe. Nhưng:

- API proxy/config **mới** có thể chưa đến runtime.
- Reporting/analytics hoặc management operations có thể trễ.
- Token, entitlement hoặc những policies phụ thuộc dịch vụ bên ngoài vẫn chịu ảnh hưởng theo thiết kế.
- Không thể coi đây là cam kết “hybrid hoạt động đầy đủ khi không có Internet”.

## 3. Thành phần cần vận hành trong cluster

| Thành phần | Vai trò | Rủi ro vận hành quan trọng |
| --- | --- | --- |
| **Apigee ingress gateway** | Điểm vào HTTPS, route host/path đến API proxies | DNS, TLS/mTLS, L4/L7 LB và bảo vệ public ingress |
| **Message Processor (MP)** | Xử lý requests/responses và thực thi proxy policies | CPU/memory, latency, autoscaling, kết nối backend |
| **Synchronizer** | Kéo cấu hình environments và proxy deployments từ Google | IAM, egress HTTPS, sai org/env, config propagation |
| **Cassandra** | Persistent state của Apigee hybrid | Disk IOPS, storage durability, NTP, backup/restore và quorum |
| **Redis / thành phần in-memory** | Hỗ trợ state/cache theo release | Capacity, restart/recovery, compatibility khi upgrade |
| **MART** | API quản trị dữ liệu runtime từ management plane | Phân quyền, Connect Agent, service health |
| **Apigee Connect Agent** | Mở kênh bảo mật **outbound** đến management plane | Egress 443, IAM, API và kết nối dài hạn |
| **UDCA** | Đẩy analytics từ runtime tới Google-managed services | Network/credentials, lag, chính sách dữ liệu |
| **Telemetry (logger/metrics)** | Gửi logs/metrics và hỗ trợ observability | Quota, chi phí, PII trong logs, mất tín hiệu |
| **Apigee Operator/Watcher** | Reconcile Kubernetes CRDs, theo dõi deployment | Quyền cluster, version compatibility, controller availability |
| **cert-manager và CA nội bộ** | Quản lý certificates được Apigee sử dụng nội bộ | Certificate renewal, phiên bản được hỗ trợ, quyền Secrets |

Các charts, CRDs và một số backing components có thể đổi theo **Apigee hybrid minor/patch version**. Ví dụ trong nhánh 1.17, có quá trình chuyển dần từ các resource Redis sang Valkey qua các patch. Vì vậy **không tự thay chart/CRD hoặc upgrade bỏ qua patch trung gian**; dùng chính xác release notes/upgrade path của phiên bản đích.

**Ranh giới dữ liệu cần biết:** Runtime xử lý API traffic trong hạ tầng do bạn kiểm soát, nhưng **cấu hình quản lý, analytics và các dữ liệu/metadata nhất định đi tới Google-managed plane**. Không viết tài liệu tuân thủ rằng “toàn bộ dữ liệu đều ở on-prem” chỉ vì chọn hybrid.

## 4. Hỗ trợ nền tảng và phiên bản

Theo danh mục **Apigee hybrid supported platforms and versions** (kiểm tra tại thời điểm triển khai), nhánh **1.17** được phát hành tháng 9/2026 và hỗ trợ các nền tảng/phiên bản Kubernetes cụ thể, có thể gồm:

- **GKE trên Google Cloud** (**Standard**, không phải GKE Autopilot).
- **Google Distributed Cloud software-only** trên VMware hoặc bare metal.
- **Amazon EKS** và **Azure AKS**.
- **Red Hat OpenShift**.
- **Rancher Kubernetes Engine (RKE2)** và các nền tảng được liệt kê rõ trong bảng chính thức.

**GKE Autopilot hiện không được hỗ trợ cho Apigee hybrid installation.** Không suy rằng “mọi cụm Kubernetes đều chạy được” chỉ vì đáp ứng API Kubernetes cơ bản. Sự hỗ trợ còn phụ thuộc **minor/patch Apigee**, bản Kubernetes, OpenShift, Helm, cert-manager và các addon tương thích.

### 4.1. Kiểm tra version matrix trước khi thiết kế

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Apigee hybrid | Minor/patch đang được Google hỗ trợ? Lịch EOL? |
| Kubernetes | Bản K8s cụ thể **có trong matrix của Apigee patch dự kiến**? |
| Helm | Helm 3.x **đúng mức được hỗ trợ** cho nhánh đích; bảng 1.17 liệt kê 3.17+ |
| cert-manager | Phiên bản được hỗ trợ? Có known issue về rotation CA/TLS? |
| Platform-specific addons | Cloud Service Mesh, CSI driver, storage plugin, ingress/LB phù hợp? |
| Client tools | `kubectl` đúng version skew, `gcloud` có APIs được bật? |
| Lộ trình nâng cấp | Có phải qua v1.16 trước khi lên v1.17? Có patch transition đặc biệt? |

Trong ví dụ bài học, giả định **Apigee hybrid 1.17.x trên GKE Standard** và **Helm 3.17+**. Đây là ví dụ lựa chọn tương thích, **không phải lời khẳng định mọi patch v1.17 đều dùng cùng requirements**. Trước khi cài thật, đọc đúng tài liệu của patch đã chọn.

### 4.2. Về upgrade/EOL

Google công bố thời hạn hỗ trợ cho từng minor. Khi bản cũ EOL, không nên duy trì runtime không còn được vá bảo mật chỉ vì “cluster vẫn chạy”. Với 1.17, tài liệu nâng cấp còn có những bước chuyển CRDs/cache theo patch; **không tự nâng thẳng từ một bản rất cũ lên mới nhất** mà bỏ qua release path.

## 5. Điều kiện Google Cloud và tổ chức Apigee

Chuẩn bị **trước khi cấp tài nguyên Kubernetes**:

1. **Google Cloud project** hợp lệ và **billing account** đang hoạt động.
2. **Quyền sử dụng Apigee hybrid/subscription** đáp ứng hình thức thương mại của tổ chức; việc bật API không thay hợp đồng/sản phẩm.
3. **Apigee organization** liên kết với project theo quy trình provision hybrid.
4. Ít nhất một **environment**, ví dụ `test`, và một **environment group**, ví dụ `api-test-group`, chứa hostname phục vụ API.
5. **Apigee instance/runtime association** phù hợp region/cluster và organization theo flow provision.
6. **Google Cloud IAM** cho người provision, service identities cho components và tổ chức truy cập read/operate đúng phạm vi.
7. **API services** cần thiết được bật trên project (tùy platform).
8. Quy trình quản lý **hostnames/DNS, TLS certificates, quotas, support escalation và chi phí**.

### 5.1. APIs thường cần trên GKE

Trong tài liệu cài Apigee hybrid trên GKE, danh sách nền gồm:

~~~text
apigee.googleapis.com
apigeeconnect.googleapis.com
cloudresourcemanager.googleapis.com
compute.googleapis.com
container.googleapis.com
pubsub.googleapis.com
~~~

Ngoài ra, các sản phẩm tích hợp như Cloud Logging/Monitoring, Cloud Storage hoặc IAM Credentials API phải có đường truy cập/quyền khi component tương ứng cần. Với EKS/AKS/GDC, danh sách APIs GKE/Compute có thể khác; **không copy nguyên bộ rồi cho là mọi môi trường có cùng yêu cầu**.

Các lệnh **chỉ đọc** để kiểm tra project/APIs:

~~~bash
gcloud config get-value project

gcloud services list --enabled \
  --project=LAB_PROJECT_ID

gcloud projects describe LAB_PROJECT_ID
~~~

Lệnh **bật API** bên dưới là **thay đổi project**, chỉ dành cho project lab được phép:

~~~bash
gcloud services enable \
  apigee.googleapis.com \
  apigeeconnect.googleapis.com \
  cloudresourcemanager.googleapis.com \
  compute.googleapis.com \
  container.googleapis.com \
  pubsub.googleapis.com \
  --project=LAB_PROJECT_ID
~~~

Không bật API và tạo Apigee organization trong một project production nếu chưa có chủ sở hữu, license/subscription, IAM review và ngân sách. Một số thao tác tạo organization/region có giới hạn không đảo ngược đơn giản.

### 5.2. Organization, environment, environment group

| Đối tượng | Ví dụ | Vai trò |
| --- | --- | --- |
| Organization | `demo-apigee-org` | Phạm vi API management và danh tính quản trị |
| Environment | `test` | Không gian triển khai proxies |
| Environment group | `api-test-group` | Gom một hoặc nhiều environments với host aliases |
| Host alias | `api.lab.example.com` | Hostname client gọi, khớp route/TLS |
| Runtime instance | `runtime-lab-01` | Liên hệ runtime deployment theo kiến trúc provision |

Tạo environment group trong management plane **không tự tạo DNS A record, load balancer hoặc TLS certificate** trong cluster của bạn. Cần liên kết cùng tên/hostname giữa quản lý Apigee và cấu hình runtime virtual host.

## 6. IAM, Kubernetes RBAC và Workload Identity

**Ba lớp quyền tách biệt:**

| Lớp | Ai được cấp? | Dùng cho việc gì |
| --- | --- | --- |
| **Google Cloud IAM** | Người provision, Google Cloud service accounts | Quản lý Apigee org, gọi APIs, ghi metrics/logs/analytics |
| **Kubernetes RBAC** | Cluster operator, Apigee Operator, team SRE | Tạo CRDs, workloads, namespaces, secrets, storage |
| **Service identity / Workload Identity** | Pods/KSAs ↔ GSAs hoặc federation tương đương | Component truy cập Google APIs không cần key file dài hạn |

Trong GKE, nên dùng **Workload Identity Federation for GKE** theo flow của Apigee hybrid. Với EKS/AKS hoặc on-prem, dùng phương án **Workload Identity Federation** được Google hỗ trợ nếu phù hợp. Phương án dùng key files/Kubernetes Secrets cần bảo vệ vòng đời khóa; không đặt JSON key trong Git hoặc container image.

**Ví dụ mapping trách nhiệm:**

- `apigee-synchronizer`: lấy cấu hình từ management plane.
- `apigee-runtime`: quyền cần thiết cho runtime components.
- `apigee-mart` và `apigee-watcher`: quản lý cấu hình/trạng thái runtime.
- `apigee-logger` / `apigee-metrics`: ghi Cloud Logging/Monitoring khi bật.
- `apigee-cassandra`: phục vụ backup/storage integration theo lựa chọn.
- `apigee-guardrails`: kiểm tra resource/service usage theo tính năng.

**Không cấp Project Editor/Owner cho mọi pod.** Dùng service account và role đúng với mỗi chart/component, kiểm tra binding scope trên project/resource, quyền impersonation và rotation.

### 6.1. Các preflight chỉ đọc

~~~bash
# Kiểm tra identity đang dùng và GKE context
gcloud auth list
kubectl config current-context
kubectl cluster-info

# Không phơi service account keys
kubectl get serviceaccounts -n apigee
kubectl get pods -n apigee -o wide
~~~

Nếu namespace chưa tạo, lệnh `kubectl get ... -n apigee` có thể trả NotFound; đó **không chứng minh cluster sai**. Phân biệt cài mới với sửa hệ thống đã có trước.

## 7. Sizing Kubernetes, storage và khả năng sẵn sàng

### 7.1. Hai nhóm tài nguyên khác nhu cầu

**Cassandra** là stateful; Message Processors và nhiều control components trong runtime chủ yếu cần capacity theo traffic. Tài liệu minimum cluster configurations nêu khuyến nghị **tách node pools**:

| Hạng mục | Stateful pool (Cassandra) | Stateless pool (runtime/MP) |
| --- | --- | --- |
| Tên thường dùng trên GKE | `apigee-data` | `apigee-runtime` |
| Mục đích | Persistent storage, Cassandra quorum | Xử lý requests, chính sách và backends |
| Nodes tham chiếu | 1 node/zone × 3 zones | 1 node/zone × 3 zones |
| Production minimum tham chiếu | Khoảng **8 vCPU, 32 GiB RAM/node** | Khoảng **8 vCPU, 32 GiB RAM/node** |
| Non-prod minimum tham chiếu | Khoảng **4 vCPU, 16 GiB RAM/node** | Khoảng **4 vCPU, 16 GiB RAM/node** |
| Disk | Dynamic PVC/StorageClass có độ bền và IOPS | Workload/charts quản lý |
| IO/network | Ít nhất khoảng **2.000 IOPS** (tham chiếu), **1 Gbps** network/node | Theo chart/traffic và khả năng nền tảng |

Đây là **mốc thiết kế từ tài liệu**, không phải kết quả capacity planning cho traffic thật. Hãy chọn machine type, disk class và replica sizes theo **thử tải, latency target, số environments, policies, API calls, quota và log volume**. Khi chọn máy cụ thể, đối chiếu memory/CPU với SKU ở region của bạn; đừng suy kích thước máy chỉ từ tên nodepool.

**Production:** Google khuyến nghị ít nhất **hai clusters** để giảm gián đoạn khi một cluster đang nâng cấp hoặc gặp sự cố, kết hợp DNS/LB failover và Cassandra replication/backup phù hợp. Một regional cluster nhiều zones giúp chịu lỗi node/zone nhưng **không thay thế** kế hoạch cluster-level DR.

### 7.2. Yêu cầu riêng của Cassandra

- **PersistentVolumes/PVC:** storage class hỗ trợ dynamic provisioning, disk durability và các điều kiện topology/multi-zone phù hợp.
- **IOPS/latency:** Cassandra nhạy với disk I/O; chọn SAN/attached storage được hỗ trợ, **không mặc định dùng NFS** chỉ vì có dung lượng lớn.
- **Network:** Cassandra gossip, replication và consistency cần connectivity ổn định; tài liệu nêu tối thiểu khoảng **1 Gbps/node** và latency p99 tối đa nên dưới khoảng **100 ms** giữa các nút.
- **NTP:** đồng bộ thời gian các nodes/regions để tránh lỗi dữ liệu hoặc khó điều tra.
- **Backup/restore:** tạo lịch backup, kiểm thử restore, encryption và retention; Google **không tự backup Cassandra của khách hàng** thay cho bạn.
- **Pod disruption:** kiểm tra PDBs/maintenance để nâng cấp node pools không làm mất quorum. Những controls PDB có thể khác theo hybrid patch.
- **Capacity headroom:** giữ dư quota CPU/IP/storage cho rolling upgrade và node failover.

**Không thực hiện `kubectl delete pvc`, xóa Cassandra pods hàng loạt, thay StorageClass của production hoặc force redeploy** để thử nghiệm. Một cluster “pods Running” vẫn có thể mất quorum hoặc mất dữ liệu nếu PVC không đủ IOPS/khả năng khôi phục.

### 7.3. Quy mô thực tế cần đo

| Tín hiệu | Tác động |
| --- | --- |
| Average/peak requests per second | Số Message Processors, autoscaler headroom |
| P95/P99 API latency | Ngân sách policy processing + backend |
| Số proxy/policies | CPU/memory mỗi request, sync size |
| Cassandra disk utilization/latency | Dung lượng, IOPS, compaction và backup |
| Cross-region traffic | Chi phí egress, latency replication |
| Quota/analytics volume | Pub/Sub/UDCA/backpressure, logs |
| Upgrade window | Số clusters/nodes đủ duy trì service |

## 8. Mạng, ingress, TLS và đường ra Google Cloud

Apigee hybrid có **hai hướng lưu lượng độc lập**:

1. **Data path:** client → DNS/HTTPS → ingress gateway → Message Processor → backend của doanh nghiệp.
2. **Control/telemetry path:** Pods trong cluster → Google-managed APIs qua HTTPS để đồng bộ hợp đồng, quản trị, báo cáo và gửi logs/metrics.

### 8.1. Ma trận kết nối cần kiểm tra

| Nguồn | Đích | Port/Protocol thường dùng | Kiểm soát |
| --- | --- | --- | --- |
| Client/partner | Ingress LB → Apigee ingress | **HTTPS TCP/443** (nên dùng) | Public/private LB, WAF/DDoS, TLS |
| Ingress | Message Processors | Do charts/mesh quản lý | Kubernetes network policy và service discovery |
| Message Processors | Backend APIs | TCP/HTTPS theo backend | DNS, routing/VPN/Interconnect, auth/mTLS |
| Synchronizer | `apigee.googleapis.com`, IAM APIs | **TCP/443 TLS** | DNS/egress proxy/firewall/identity |
| Apigee Connect Agent | `apigeeconnect.googleapis.com` | **TCP/443 TLS** | Agent **chủ động mở outbound** |
| UDCA/analytics | Apigee/Google Storage endpoints | **TCP/443 TLS** | Data governance và quota |
| Logger/Metrics | `logging.googleapis.com`, `monitoring.googleapis.com` | **TCP/443 TLS** | IAM, sampling và chi phí |
| Cassandra nodes | Các Cassandra peers | Cổng nội bộ theo version | Network policy, replication, MTU, latency |

Danh sách chính xác các cổng/nơi gọi phụ thuộc **release/config/plugin**. Dùng tài liệu **Secure ports usage** đúng hybrid version trước khi tạo firewall rules. **Không pin địa chỉ IP của `*.googleapis.com`** vì chúng có thể thay đổi; nên dùng DNS/proxy/firewall policy theo mô hình được Google hỗ trợ.

### 8.2. Vì sao không cần inbound quản trị từ Google?

**Apigee Connect Agent** thiết lập kết nối outbound tới dịch vụ quản lý của Google, cho phép quản lý runtime data qua MART mà **không phải mở trực tiếp một cổng MART public** nhận kết nối từ management plane. Nhưng bạn **vẫn phải mở đường ingress HTTPS** nếu khách hàng/đối tác cần gọi APIs từ bên ngoài cluster.

**Không nhầm** “không cần mở inbound cho control plane” với “không cần load balancer/DNS/443 cho clients”.

### 8.3. Public hay private ingress?

| Tình huống | Thiết kế tham khảo |
| --- | --- |
| Partner API public | External Load Balancer → Apigee ingress, TLS, WAF/Cloud Armor khi phù hợp |
| API chỉ dành cho ứng dụng nội bộ | Internal Load Balancer/private DNS/VPN/Interconnect |
| Multi-cloud/on-prem | LB/proxy tại data center, route riêng đến backend, IP allowlist hoặc mTLS theo risk |
| Multi-region | DNS/GSLB failover và nhiều runtime clusters; kiểm tra backend/data consistency |

**Environment group hostname** (ví dụ `api.lab.example.com`) phải khớp host aliases, ingress certificate, DNS record, LB và proxy base path. Khi một thành phần không khớp, có thể gặp lỗi TLS, `404` hoặc route sai environment.

### 8.4. TLS/mTLS và certificates

- Cần **certificate công khai hoặc PKI nội bộ** thích hợp với hostname mà client sử dụng; tránh chứng chỉ hết hạn/sai SAN.
- Có thể cấu hình **one-way TLS** hoặc **mTLS** trên ingress theo yêu cầu, quản lý Kubernetes Secrets/cert files theo hướng dẫn Apigee.
- **cert-manager nội bộ của Apigee** phục vụ các kênh tin cậy giữa components, **không mặc định thay** ingress TLS certificate cho domain public.
- Chỉ mở port cần thiết, hạn chế TLS versions/ciphers theo policy, quản lý rotation và cảnh báo chứng chỉ sắp hết hạn.
- Nếu load balancer **terminate TLS** trước ingress, phải thiết kế TLS giữa LB ↔ ingress và HTTP headers/identity rõ ràng; không vô tình để backend tin `X-Forwarded-*` không được xác minh.

Ví dụ đoạn `overrides.yaml` dành cho virtual host **chỉ mang tính minh họa**:

~~~yaml
virtualhosts:
  - name: api-test-group
    sslCertPath: "./certs/api.lab.example.com.pem"
    sslKeyPath: "./certs/api.lab.example.com.key"
~~~

`name` phải là **tên environment group**, không phải hostname. Phải chuẩn bị **certificate/key thật và bảo vệ private key** theo kiến trúc đang dùng; cấu hình này **không đủ để chạy một hybrid instance hoàn chỉnh**.

## 9. Dữ liệu, tuân thủ và phân tách trách nhiệm

Một động cơ chọn hybrid là giữ **xử lý API requests và kết nối backend** trong môi trường khách hàng quản lý. Điều đó không có nghĩa tất cả thông tin API đều được lưu nội bộ.

| Nhóm dữ liệu | Điển hình đi đâu? | Kiểm tra cần thiết |
| --- | --- | --- |
| Request/response payload | Đi qua runtime do khách hàng quản lý | Không vô ý log payload nhạy cảm; mã hóa client→ingress→backend |
| Runtime state | Cassandra/local runtime | PVC, encryption-at-rest, backup, tenant access |
| API definitions/config | Management plane; được Synchronizer tải xuống runtime | Phê duyệt cấu hình, quyền quản trị, secrets |
| Analytics/usage | UDCA gửi dữ liệu phân tích tới managed services | Data classification, masking/hash, location/residency |
| Logs/metrics | Cloud Logging/Monitoring khi cấu hình | PII retention, logging exclusions, cost |
| TLS secrets/identity | Cluster, Secret Store, workload identity | Secret rotation, RBAC, workload isolation |

Nếu tổ chức có **yêu cầu data residency**, đối chiếu nơi lưu/control plane location, analytics region, cấu hình `contractProvider` khi áp dụng và các điều kiện thương mại/quy định; **không được tự khẳng định “data never leaves the country”**.

**Quy tắc:** Không đưa access token, thông tin khách hàng, credentials hay dữ liệu giao dịch vào analytics custom dimensions/logs chỉ để debug. Dùng redaction, hashing, sampling và retention theo yêu cầu bảo mật.

## 10. Lộ trình cài đặt tổng thể: provision → cluster → Helm → kiểm thử

Dự án thực tế nên theo từng giai đoạn với cổng kiểm chứng. Google cung cấp luồng **The big picture** cho Apigee hybrid:

~~~mermaid
flowchart TB
  P["1. Google Cloud project + billing + APIs"] --> O["2. Apigee org + environment + environment group"]
  O --> K["3. Kubernetes supported platform + node pools/PVC"]
  K --> ID["4. Service accounts + WIF + egress/DNS/TLS"]
  ID --> OV["5. overrides.yaml + chart version + secrets"]
  OV --> CRD["6. Install cert-manager / Apigee CRDs"]
  CRD --> H["7. Helm charts theo thứ tự và readiness"]
  H --> ING["8. Expose ingress, DNS + valid TLS"]
  ING --> PROXY["9. Deploy một API proxy thử nghiệm"]
  PROXY --> SLO["10. Functional + security + load + DR validation"]
~~~

**Tất cả ví dụ dưới đây giả định:** có **Apigee org đã được provision**, cluster GKE **Standard** hỗ trợ hybrid 1.17, IAM hợp lệ, node pools/StorageClass đúng, Helm/charts được tải, secret/certificates được chuẩn bị. **Không thể chỉ copy một YAML từ bài này rồi cài trọn Apigee hybrid.**

### 10.1. Sơ đồ cấu hình `overrides.yaml`

Tệp này điều chỉnh các charts runtime. Các trường lõi thường gặp:

~~~yaml
# SKELETON ĐỂ HỌC — KHÔNG PHẢI overrides.yaml CÀI ĐẶT HOÀN CHỈNH
namespace: apigee

gcp:
  projectID: "LAB_PROJECT_ID"
  region: "asia-southeast1"

k8sCluster:
  name: "hybrid-gke-lab"
  region: "asia-southeast1"

org: "LAB_APIGEE_ORG"
instanceID: "LAB_INSTANCE_ID"

envs:
  - name: "test"
    # Cache encryption secret, service identity và các thuộc tính
    # bắt buộc khác phải cấu hình theo install guide của patch.

virtualhosts:
  - name: "api-test-group"
    sslCertPath: "./certs/api.lab.example.com.pem"
    sslKeyPath: "./certs/api.lab.example.com.key"
~~~

**Khi dùng `instanceID`, nó phải khớp Apigee instance đã provision/association;** `gcp.region`, region control plane/analytics và region cluster không phải lúc nào cũng là một khái niệm. Trong mô hình multi-region/multi-org, kiểm tra quy tắc instance ID và organization mapping.

**Không lưu file secrets/keys trong Git.** Với multi-cluster, dùng cấu hình riêng theo cluster/region và quản trị các overrides như release artifact có review. Những fields như `envs[].cacheEncryptionSecret` có thể bắt buộc tùy version; đối chiếu property reference trước Helm.

### 10.2. Tải Helm charts đúng nhánh

Apigee hybrid sử dụng charts được phát hành từ Google Artifact Registry:

~~~bash
# Các lệnh dưới đây chỉ tải artifacts, không cài vào cluster.
# Thay RELEASE_PATCH bằng patch được hỗ trợ và đã review.
helm version
kubectl version --client

helm show chart \
  oci://us-docker.pkg.dev/apigee-release/apigee-hybrid-helm-charts/apigee-operator \
  --version RELEASE_PATCH
~~~

Với quy trình đã chọn patch, dùng `helm pull ... --version RELEASE_PATCH` cho toàn bộ charts, không trộn chart 1.16 với operator/CRDs 1.17. Lệnh `helm show chart` là **ví dụ đọc metadata**; placeholder `RELEASE_PATCH` phải được thay trước khi thực hiện.

Các charts chính được lắp theo thứ tự kiến trúc:

| Thứ tự | Helm chart | Chức năng |
| ---: | --- | --- |
| 1 | `apigee-operator` | Operator/controller |
| 2 | `apigee-datastore` | Cassandra datastore |
| 3 | `apigee-redis` (hoặc chart tương ứng ở patch được hỗ trợ) | In-memory store |
| 4 | `apigee-telemetry` | Logger/metrics |
| 5 | `apigee-ingress-manager` | Ingress controller/gateway |
| 6 | `apigee-org` | MART, Apigee Connect, UDCA và organization components |
| 7 | `apigee-env` | Synchronizer và runtime theo **từng environment** |
| 8 | `apigee-virtualhost` | Env group/virtual host theo **từng environment group** |

**Cảnh báo version:** Các chart names/features có thể thay theo patch, đặc biệt khi runtime chuyển Redis/Valkey. **Không thay các Helm charts theo bảng trên một cách máy móc** khi release notes/upgrade guide yêu cầu thứ tự hoặc chart chuyển đổi khác.

### 10.3. CRDs và Helm dry run

Theo tài liệu cài hiện hành, Apigee CRDs dùng Kustomize, server-side apply. Các lệnh sau **chỉ là ví dụ trong thư mục charts đã giải nén, với quyền cluster phù hợp**:

~~~bash
# CHỈ DRY RUN, chưa tạo CRDs:
kubectl apply -k apigee-operator/etc/crds/default/ \
  --server-side \
  --force-conflicts \
  --validate=false \
  --dry-run=server

# CHỈ KIỂM TRA HELM RENDER / APPLY DRY RUN:
helm upgrade operator apigee-operator/ \
  --install \
  --namespace apigee \
  -f overrides.yaml \
  --dry-run=server
~~~

**Hai lệnh vẫn truy cập Kubernetes API và cần permissions.** Trong cài đặt mới, phải hoàn tất cert-manager, service accounts, các CRDs và các preflight trong hướng dẫn **trước khi cài thật**. Không đưa lệnh `kubectl apply --force-conflicts` vào automation production mà không hiểu ownership của CRDs.

Sau khi được phê duyệt và đã thực hiện theo đầy đủ hướng dẫn Google, lệnh cài operator tương ứng có dạng:

~~~bash
# THAY ĐỔI cluster thật, chỉ chạy sau preflight và change approval:
helm upgrade operator apigee-operator/ \
  --install \
  --namespace apigee \
  -f overrides.yaml
~~~

**Không dùng lệnh operator riêng lẻ như “cài xong Apigee hybrid”.** Từng thành phần tiếp theo còn phải được lắp/kiểm tra trong thứ tự charts. Khi nâng cấp, **không áp dụng nguyên quy trình cài mới**; cần upgrade/rollback guide đúng patch.

### 10.4. Kiểm tra trạng thái sau cài

~~~bash
# Các lệnh sau chỉ đọc trạng thái trong đúng kubecontext
kubectl config current-context
helm list -n apigee
kubectl get pods -n apigee -o wide

kubectl get apigeedatastores -n apigee
kubectl get apigeeorganizations -n apigee
kubectl get apigeeenvironments -n apigee
kubectl get apigeetelemetries -n apigee

kubectl get svc -n apigee
kubectl get pvc -n apigee
kubectl get events -n apigee --sort-by=.lastTimestamp
~~~

Nếu CRD/chart chưa được cài thì lệnh get custom resources có thể báo **unknown resource type**; đừng coi đó là lỗi runtime. Sau khi cài, theo dõi các CRDs ở state `running`/**Ready** và các Pods/Helm releases, chứ không chỉ số lượng Pods `Running`.

### 10.5. Expose ingress và smoke test HTTPS

1. Cấu hình ingress gateway bằng chart/overrides phù hợp.
2. Chọn Load Balancer (internal/public), routing, port và health probes.
3. Cấp TLS certificate **hợp lệ** cho host alias, tạo DNS record.
4. Kiểm tra gateway health và khả năng gọi một proxy thử nghiệm.
5. Chỉ public endpoint sau khi đã duyệt auth/quota/rate limiting và dữ liệu.

Ví dụ kiểm thử **chỉ đọc từ client được phép** khi LB/DNS/TLS đã đúng:

~~~bash
# Thay đúng DOMAIN và IP đã cấp; không dùng -k để bỏ qua xác minh TLS.
curl --resolve "api.lab.example.com:443:INGRESS_IP" \
  "https://api.lab.example.com/healthz/ingress"
~~~

Sau khi tạo một **API proxy** có base path `/orders/v1` trỏ tới backend mock/private lab, kiểm tra một request được cho phép và một request bị từ chối theo policy. **Không dùng production token thật trong lệnh mẫu hoặc logs.**

## 11. Production rollout, HA, backup và nâng cấp

### 11.1. Năng lực HA tối thiểu

- Hai runtime clusters production khi cần HA/upgrade không gián đoạn, có **traffic failover** chủ động.
- Cassandra với storage bền, quorum/replication phù hợp và backup **được kiểm thử restore**.
- Ingress/LB, DNS, routing backend có RTO/RPO và chiến lược routing/drain.
- PodDisruptionBudgets, node-pool upgrades, capacity headroom và Kubernetes upgrades đã tính.
- Tách dev/staging/prod với cấu hình, secrets, IAM và network policy phù hợp.
- Một **runbook mất kết nối management plane** để biết phần nào vẫn xử lý request và phần nào chậm đồng bộ.

### 11.2. Backup Cassandra và dữ liệu cấu hình

Tài liệu backup Apigee hybrid nêu **Cassandra là thành phần lưu persistent runtime data chính** cần phương án backup/restore; nhiều thành phần khác stateless có thể cài lại từ charts/overrides. Tuy nhiên phải lưu **source of truth của overrides, Helm/chart versions, secrets/certificates, IAM mappings, LB/DNS config** ở nơi an toàn riêng.

**Không lấy snapshot VM hoặc copy PVC ngẫu nhiên làm backup Cassandra chuẩn** khi chưa bảo đảm consistency. Dùng workflow backup/restore Apigee hybrid được hỗ trợ, lưu vị trí khác failure domain và định kỳ chạy restore drill.

### 11.3. Nâng cấp đúng thứ tự và khả năng rollback

Quy trình vận hành tham khảo:

1. Chọn một **patch được hỗ trợ**, đọc release notes, known issues, compatibility và migration steps.
2. Chuẩn bị bản sao/backup Cassandra, `overrides.yaml`, certificate references và identities.
3. Dựng/cập nhật môi trường preprod có topology gần production.
4. Thực hiện **Helm dry run**, kiểm tra CRD migrations, API deprecations và resource quotas.
5. **Drain/divert traffic khỏi cluster** đang nâng cấp khi có nhiều clusters.
6. Nâng theo thứ tự charts/CRDs của patch; sau mỗi nhóm kiểm tra status và API requests.
7. Đưa traffic lại từng bước, quan sát latency/errors, Cassandra và analytics delivery.
8. Nếu gặp lỗi, dùng **hướng dẫn rollback đúng nhánh/patch**; không giả định rollback chỉ một `helm rollback` là đủ.

**Ví dụ rủi ro:** Trong một số patch 1.17, cấu trúc Redis/Valkey CRDs thay đổi. Rollback về 1.16 có bước xử lý conversion webhooks/CRDs riêng; **không tự hạ cấp chart một chiều** khi datastore/CRDs đã được migration.

## 12. Quan sát và vận hành theo SLO

| Tín hiệu | Nơi quan sát | Điều cần làm |
| --- | --- | --- |
| API 2xx/4xx/5xx, p95/p99 | Apigee analytics, runtime/LB telemetry | Phân biệt lỗi client, policy, backend |
| Ingress health, TLS expiry | LB probes, ingress controller, certificates | Cảnh báo 5xx handshake/502/503 |
| MP CPU/memory/replicas | Kubernetes/Cloud Monitoring | Điều chỉnh HPA, policy latency, node capacity |
| Cassandra disk IOPS, latency, quorum | Cassandra metrics, PVC/storage monitoring | Dự báo compaction/storage và backup |
| Synchronizer config sync lag | Component logs, deployment state | Kiểm tra egress/IAM/API, contract version |
| Apigee Connect availability | Connect Agent metrics/logs | Phát hiện management connectivity failure |
| UDCA analytics lag/error | Telemetry logs, analytics pipeline | Phân loại data plane healthy nhưng analytics trễ |
| Helm/Operator/CRD health | `helm list`, `kubectl get ...` | Theo dõi upgrades/drift |
| Logs/Cloud Billing/quota | Cloud Logging/Monitoring/Billing | Kiểm soát volume và chi phí |

Thiết lập **SLO endpoint chính** dựa request thật (success rate/latency) và **các SLO phụ** cho đồng bộ cấu hình, độ trễ analytics và backup RPO. **“Pods Running” không đồng nghĩa API gateway hoạt động tốt** nếu certificate hết hạn hoặc backend timeout.

### 12.1. Phân loại lỗi nhanh

| Triệu chứng | Tầng ưu tiên điều tra |
| --- | --- |
| Client không resolve host | DNS record, split-horizon DNS |
| TLS handshake/cert error | Ingress certificate, SAN, issuer, LB termination |
| `404` sau deploy proxy | Env group hostname, proxy base path, env association |
| `401/403` từ proxy | API key/OAuth/mTLS policies, developer app/product, IAM riêng |
| `502/503` và backend unreachable | MP → backend DNS/route/TLS, target health |
| Không thấy proxy mới | Synchronizer, permissions, org/env, management egress |
| Runtime requests vẫn OK nhưng analytics mất | UDCA/egress 443/IAM và managed analytics |
| Pods Cassandra CrashLoop/PVC Pending | StorageClass, disk quota/IOPS, affinity, KSA/IAM |
| `ImagePullBackOff` | Registry creds, network, image/chart version |
| Management actions chậm nhưng API traffic vẫn chạy | Apigee Connect/MART/management connectivity |
| Sau upgrade mọi cluster lỗi | Version mismatch/CRD migration, rollout không có isolation |

### 12.2. Runbook chẩn đoán ngắn

~~~mermaid
flowchart TD
    ERR["Gateway / deployment có lỗi"] --> Q{"Client request tới ingress?"}
    Q -- "Không" --> NET["DNS, LB, TLS, ingress routing"]
    Q -- "Có" --> MP{"Message Processor xử lý?"}
    MP -- "Không" --> POD["Pods, HPA, cluster capacity, mesh"]
    MP -- "Có" --> BACK{"Backend đáp ứng?"}
    BACK -- "Không" --> TARGET["Route/TLS/timeout/backend health"]
    BACK -- "Có" --> POL["Policies/auth/quota và response metrics"]
    ERR --> MGMT{"Proxy config không đồng bộ?"}
    MGMT -- "Có" --> SYNC["Synchronizer, Apigee Connect, IAM, egress 443"]
    ERR --> DATA{"Cassandra/PVC có lỗi?"}
    DATA -- "Có" --> CASS["Quorum, IOPS, disk, NTP, backup/DR"]
~~~

Khi một API bị lỗi, đừng sửa ngay IAM toàn project hoặc xóa Cassandra PVC. Xác định **đường data plane** và **đường management/telemetry plane** đang hỏng riêng hay đồng thời, lưu bằng chứng rồi thay đúng cấu hình.

## 13. Case study: API ngân hàng kết nối backend riêng

**Yêu cầu nghiệp vụ:** Ngân hàng triển khai API cho đối tác, sử dụng một hệ thống core banking ở trung tâm dữ liệu. Phải kiểm soát mọi API traffic trước backend, giữ ứng dụng và dữ liệu giao dịch trong mạng được quản lý, nhưng cho phép đội phát triển định nghĩa API products và quản lý usage.

**Kiến trúc đề xuất:**

- Management plane Apigee do Google vận hành, có RBAC và quản trị API products/proxies.
- Hai Kubernetes runtime clusters (mỗi cluster hỗ trợ Apigee hybrid) ở các failure domains đã hoạch định.
- External ingress gateway có HTTPS/mTLS theo yêu cầu đối tác, DDoS/WAF, DNS failover.
- Message Processors chạy API key/OAuth, quota, spike arrest và threat protection policies trước khi gọi backend.
- Cassandra stateful với storage IOPS, backup và DR plan.
- Control/analytics egress 443 qua policy/proxy được phép; xem residency/redaction.
- Observability ở cả gateway và backend; rollback proxy revisions qua quy trình phát hành.

**Quyết định quan trọng:** Dữ liệu phân tích nào được gửi về Google-managed services? Nếu chính sách không cho gửi PII, phải masking/hashing hoặc loại khỏi analytics/logs **trước khi bật production**. Chỉ dựa vào việc Message Processor ở on-prem là chưa đủ.

**Đo kết quả:** 99.x% success/latency SLO theo yêu cầu, failover test, restore test Cassandra, quota enforcement, no-secret-in-logs, HA capacity và TCO được tính đầy đủ.

## 14. Thực hành: lập hồ sơ sẵn sàng triển khai

Đây là **bài lab thiết kế và kiểm tra chỉ đọc**, không yêu cầu người học tự tạo Apigee org/cluster có phí cao. Nếu tổ chức cấp sandbox đã cài hybrid, chỉ thu thập cấu hình của đúng môi trường được cho phép.

### Phần A — Chọn giải pháp

Giả sử doanh nghiệp có:
- 25 APIs cho đối tác; backend tại VPC riêng và một data center on-prem.
- 1.500 requests/giây giờ cao điểm (giá trị giả định, chưa sizing).
- Yêu cầu audit, developer app credentials, quotas và data residency có kiểm soát.
- Đội Kubernetes SRE có khả năng duy trì cluster, storage và upgrades.

**Nhiệm vụ:** So sánh API Gateway, Apigee Google-managed và Apigee hybrid theo 5 tiêu chí: data path, IAM/API management, vận hành, HA/DR, chi phí. Quyết định phải có **bằng chứng**, không chọn hybrid chỉ vì tên.

### Phần B — Preflight GKE Standard

Trên một **cluster lab đã được cấp quyền**:

~~~bash
# KHÔNG thay đổi resources
gcloud config get-value project
gcloud container clusters list --project=LAB_PROJECT_ID

kubectl config current-context
kubectl get nodes -o wide
kubectl get storageclass
kubectl get pv,pvc -A

helm version
kubectl version --client
~~~

Điền bảng:

| Check | Kết quả cần ghi |
| --- | --- |
| Supported platform | GKE Standard (không Autopilot), K8s version trong matrix |
| Helm/cert-manager | Version tương thích patch hybrid dự kiến |
| Node pools | Stateful/stateless tách, node count/headroom |
| Disk | Dynamic PVC, IOPS/latency, backup class |
| NTP/network | Clock sync, peer traffic, 443 egress |
| IAM | Google Cloud role, KSA/GSA/WIF mappings |
| Organization | Org/env/envgroup + instance association |
| DNS/TLS | Host alias, valid cert/SAN, LB type |
| Data governance | Data classification, analytics redaction, residency |

### Phần C — Kiểm tra deployment (nếu hybrid đã cài)

~~~bash
# CHỈ ĐỌC, đúng context và namespace
helm list -n apigee
kubectl get pods -n apigee
kubectl get apigeedatastores -n apigee
kubectl get apigeeenvironments -n apigee
kubectl get svc -n apigee -l app=apigee-ingressgateway
~~~

**Nếu resource không tồn tại**, ghi `NOT INSTALLED`, không tự cài để “làm đủ bài”. Với ingress URL đã có phép, kiểm tra HTTPS certificate và một proxy mock test. Không thử invalid tokens trên môi trường đối tác thật.

### Phần D — Phân tích sự cố giả định

1. **API 200 nhưng analytics trễ 20 phút:** điều tra UDCA/egress/managed analytics, không xóa Cassandra.
2. **Một zone mất và Cassandra quorum suy giảm:** xem repl/backups/PDB, không xóa PVC; lập DR plan.
3. **Proxy mới deploy không xuất hiện:** kiểm tra org/env mapping, Synchronizer/Connect và logs, không mở public MART.
4. **TLS certificate hết hạn:** sửa certificate/rotation/LB, không làm rộng backend firewall.
5. **Đang nâng v1.16 → 1.17:** phải tra release notes, CRD conversion và version-dependent patch sequence.

**Bài nộp:** sơ đồ hai mặt phẳng, bảng requirements, các quyền cần thiết, runbook từng loại sự cố, ước lượng capacity từ RPS đo được và chiến lược nâng cấp hai clusters.

## 15. Câu hỏi tự kiểm tra

1. **Hybrid có nghĩa Google vận hành cả runtime không?** Không; khách hàng vận hành runtime trên supported Kubernetes.
2. **Tại sao chọn hybrid thay API Gateway?** Khi cần API management nâng cao cùng quyền kiểm soát data path/location, và chấp nhận vận hành cluster/Cassandra.
3. **GKE Autopilot có hỗ trợ Apigee hybrid 1.17 không?** Không, theo supported platforms hiện hành.
4. **Management plane down thì mọi API lập tức chết?** Không nhất thiết; runtime có contract đã đồng bộ, nhưng config mới/analytics và một số dependencies có thể bị ảnh hưởng.
5. **Component nào lưu persistent state cốt lõi?** Cassandra.
6. **Đã có three-zone GKE cluster có cần backup?** Có; HA không thay backup/restore.
7. **Apigee Connect cần mở inbound port public cho MART?** Không; Connect Agent mở outbound TLS.
8. **Có thể hard-code IP của `apigee.googleapis.com`?** Không nên; IP thay đổi, dùng supported DNS/egress.
9. **Một environment group đại diện gì?** Nhóm environments dùng các host aliases chung, liên quan virtualhost routing.
10. **Có thể cài bằng `kubectl apply -f CRD.yaml` tùy ý?** Không; làm đúng Kustomize/server-side CRD procedure.
11. **Tại sao phải xem Helm và cert-manager support matrix?** Để tránh incompatibility controller/CRD/TLS.
12. **Thế nào là runtime đã sẵn sàng?** Components/PVC/ingress healthy, proxy route hoạt động, policy/auth/backend và logs/metrics được kiểm chứng.
13. **Vì sao API traffic local không đảm bảo toàn bộ data local?** Analytics/config có thể tới Google-managed plane.
14. **Khi có hai clusters, upgrade thế nào?** Drain traffic một cluster, upgrade/test, đưa lại traffic; lặp với cluster còn lại theo patch guide.
15. **Dùng số node minimum thay load test được không?** Không; must capacity test theo RPS, policies, latency và backend.
16. **TCO bao gồm những gì?** Apigee commercial cost, Kubernetes nodes/disks/LB/egress, backups, logs và nhân sự SRE.

## 16. Checklist đưa Apigee hybrid vào production

- [ ] Đã chứng minh cần hybrid; so sánh API Gateway và Apigee managed.
- [ ] Project, billing, subscription/entitlement và Apigee org/env/envgroup đã provision đúng.
- [ ] Runtime Kubernetes platform và phiên bản nằm trong **supported matrix**; không dùng Autopilot.
- [ ] Version Helm, cert-manager, CSI, K8s/CRDs tương thích release patch được chọn.
- [ ] Node pools cho Cassandra/MP đủ CPU, RAM, IOPS, network và headroom.
- [ ] Có NTP, persistent volumes, Cassandra backup/restore drill và RTO/RPO.
- [ ] Production HA có đủ clusters/zone isolation và failover routing.
- [ ] IAM/Kubernetes RBAC/Workload Identity tối thiểu, không dùng service account keys trong Git.
- [ ] Có outbound HTTPS 443 đến đúng Apigee/Google endpoints, không hard-code IP.
- [ ] Ingress DNS/TLS/mTLS/LB và backend routing được thử nghiệm.
- [ ] Cấu hình overrides/Helm release/secret references quản lý theo quy trình review.
- [ ] Các charts/CRDs được cài theo đúng thứ tự và patch-specific instructions.
- [ ] Proxy mock → backend mock, auth/quota/threat policies và telemetry được kiểm chứng.
- [ ] Data governance/analytics/PII/residency được xét cả ở management plane.
- [ ] Theo dõi p95/p99, 5xx, Cassandra, Synchronizer, Connect, UDCA và certificates.
- [ ] Có lịch upgrade/EOL, canary rollout, backup, rollback/DR runbook.
- [ ] Dự trù license, compute, storage, network, observability và SRE operational cost.

## 17. Tài liệu Google Cloud chính thức

Chọn đúng version/patch khi truy cập tài liệu vì hướng dẫn, tên chart, CRDs và requirements có thể thay đổi.

- [Apigee hybrid là gì? (v1.17)](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/what-is-hybrid) — management plane/runtime plane, components và data placement.
- [The big picture](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/big-picture) — lộ trình provision, install, test.
- [Prerequisites](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/prerequisites.html) — billing, IAM, NTP, tools và cluster.
- [Supported platforms and versions](https://docs.cloud.google.com/apigee/docs/hybrid/supported-platforms) — Kubernetes/Helm/cert-manager matrices, EOL.
- [Enable APIs](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/precog-enableapi) — APIs phụ thuộc vào platform.
- [Minimum cluster configurations](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/cluster-overview) — node pools, disk IOPS, network/HA.
- [Secure ports usage](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/ports.html) — ingress/egress và Apigee Connect.
- [Install service accounts](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/install-service-accounts) — quyền theo components.
- [Service account authentication](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/install-sa-authentication) — Workload Identity Federation và các lựa chọn khác.
- [Configuration property reference](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/config-prop-ref) — schema `overrides.yaml`.
- [Helm reference](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/helm-reference) — chart mapping/order và upgrade.
- [Download Helm charts](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/install-download-charts) — charts từ Artifact Registry.
- [Ingress TLS/mTLS](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/ingress-tls) — certs và virtual hosts.
- [Expose Apigee ingress](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/install-expose-apigee-ingress.html) — LB/DNS/TLS health check.
- [Cassandra backup overview](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/cassandra-backup-overview.html) — persistent state và DR.
- [Upgrade Apigee hybrid 1.17](https://docs.cloud.google.com/apigee/docs/hybrid/v1.17/upgrade) — patch sequence, CRDs và rollback.
- [Apigee hybrid release notes](https://docs.cloud.google.com/apigee/docs/hybrid/release-notes) — feature fixes, known issues, support changes.

**Ghi nhớ:** Apigee hybrid cho phép **Google quản lý API control plane**, còn doanh nghiệp **tự vận hành data plane trên Kubernetes**. Đổi lại quyền kiểm soát runtime là trách nhiệm về **nền tảng được hỗ trợ, Cassandra, NTP, IAM/identity, egress 443, ingress DNS/TLS, Helm/CRDs, HA, backup, upgrade và chi phí**. Chỉ triển khai production khi các lớp này đã có bằng chứng kiểm thử.
