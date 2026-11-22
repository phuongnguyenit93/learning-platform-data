# Azure Arc-enabled Kubernetes và quản trị cluster hybrid

## 1. Vì sao cần quản trị Kubernetes theo mô hình hybrid?

Một doanh nghiệp có thể dùng **Azure Kubernetes Service (AKS)** cho ứng dụng public, Kubernetes tại trung tâm dữ liệu nội bộ để xử lý hệ thống lõi, và một số cluster tại nhà máy hoặc cửa hàng để chạy tác vụ gần thiết bị. Các cluster hoạt động ở nhiều nơi nhưng cùng có nhu cầu: quản lý quyền, kiểm soát cấu hình, kiểm tra chính sách, theo dõi tình trạng và phát hành ứng dụng có thể truy vết.

Nếu từng nhóm vận hành cluster theo cách riêng, doanh nghiệp dễ gặp các vấn đề:

- Không có inventory đáng tin cậy: cluster nào thuộc môi trường production, ai sở hữu, đang dùng Kubernetes version nào?
- YAML được chỉnh trực tiếp bằng `kubectl` mà không lưu lại lịch sử, dẫn đến **configuration drift**.
- Các cluster có quy định về image registry, resource requests/limits, namespace và network policy khác nhau.
- Log và telemetry phân tán, khó xác định sự cố xuất phát từ ứng dụng, node, network hay dịch vụ Azure mà ứng dụng phụ thuộc.
- Tài khoản Kubernetes có quyền quá rộng; một cluster lỗi hoặc kết nối mạng mất khiến quy trình quản trị bị gián đoạn.

**Azure Arc-enabled Kubernetes** giúp đưa các Kubernetes cluster **đang chạy ngoài Azure hoặc trên hạ tầng được hỗ trợ** vào lớp quản trị của Azure bằng cách đăng ký chúng như tài nguyên Azure. Từ đó, tổ chức có thể áp dụng các khả năng được hỗ trợ như Azure Resource Manager inventory, Azure Policy cho Kubernetes, GitOps với Flux, theo dõi và tích hợp dịch vụ Azure.

Điểm quan trọng nhất: **kết nối cluster với Azure Arc không di chuyển cluster lên Azure, không biến cluster thành AKS và không trao quyền vận hành control plane cho Azure**. Control plane, worker nodes, storage, mạng và phần lớn tác vụ vòng đời Kubernetes vẫn thuộc trách nhiệm của nền tảng nguồn và đội vận hành.

Trong lộ trình khám phá Azure từ subscription, resource group, Microsoft Entra ID đến mạng, compute, storage, giám sát, bảo mật và kiểm soát chi phí, Arc là công cụ kết nối những môi trường không nằm hoàn toàn trong Azure vào một **mô hình quản trị chung**.

### Mục tiêu sau bài học

Bạn có thể:

1. Giải thích Azure Arc-enabled Kubernetes và phân biệt với AKS, AKS enabled by Azure Arc và Kubernetes tự quản lý.
2. Chuẩn bị cluster, quyền Azure/Kubernetes và kết nối outbound an toàn; kết nối cluster bằng Azure CLI.
3. Dùng Azure Resource Manager để tổ chức inventory, tags, resource groups và quyền truy cập cho nhiều cluster.
4. Thiết kế GitOps với Flux và quy tắc tránh thay đổi trực tiếp gây drift.
5. Chọn Azure Policy, giám sát, bảo mật, RBAC và cơ chế truy cập phù hợp cho cluster hybrid.
6. Đánh giá giới hạn khi mất kết nối Azure, xử lý sự cố agent/extension và xây runbook vận hành.
7. Thực hiện lab nhỏ có kiểm chứng, tránh xem trạng thái Connected là bằng chứng ứng dụng đang khỏe.

## 2. Phân biệt các mô hình Kubernetes liên quan đến Azure

| Mô hình | Control plane và node chạy ở đâu? | Azure quản lý phần nào? | Trách nhiệm chủ yếu của nhóm vận hành |
| --- | --- | --- | --- |
| **AKS** | Dịch vụ AKS trên hạ tầng Azure | Azure cung cấp dịch vụ Kubernetes được quản lý, có cơ chế lifecycle riêng | Workload, cấu hình cluster được phép, bảo mật, mạng, storage, SLO |
| **Azure Arc-enabled Kubernetes** | Cluster hiện hữu ở on-premises, edge, cloud khác hoặc nơi được hỗ trợ | Tạo resource đại diện trong Azure, các extension và khả năng quản trị đã bật | Vẫn vận hành nền tảng Kubernetes nguồn và các dependency của nó |
| **AKS enabled by Azure Arc** | Một số nền tảng hybrid/on-premises được sản phẩm hỗ trợ | Một giải pháp triển khai/quản lý AKS theo khả năng sản phẩm riêng | Quản trị hạ tầng và cấu hình theo mô hình triển khai tương ứng |
| **Kubernetes tự quản không kết nối Azure** | Bất kỳ hạ tầng Kubernetes phù hợp | Không có resource Arc hay quản trị trung tâm qua Azure | Inventory, policy, GitOps, monitoring và vận hành tự tổ chức |

**Không đánh đồng** Azure Arc-enabled Kubernetes với một công cụ triển khai cluster mới. Nếu một cụm đã có Kubernetes API, CNI, CSI, control plane HA và cơ chế backup, việc bật Arc chủ yếu bổ sung **kết nối tới Azure management plane**. Nó không tự cấp thêm node, sửa network, nâng phiên bản Kubernetes hoặc cấu hình DR.

### 2.1 Những khả năng có thể kết hợp

| Nhu cầu | Khả năng Azure liên quan | Điều kiện/góc cần xác minh |
| --- | --- | --- |
| Inventory theo subscription | Azure Resource Manager, resource groups, tags, Resource Graph | Tài nguyên đăng ký còn hoạt động, tags đáng tin và quyền Azure phù hợp |
| Đưa cấu hình ứng dụng xuống cluster | GitOps/Flux thông qua extension và configuration của Arc | Git repository, Flux source access, RBAC và điều kiện extension |
| Chính sách nhất quán | Azure Policy cho Kubernetes ở phạm vi hỗ trợ | Policy extension, loại effect, khả năng thực thi trên cluster và trạng thái đồng bộ |
| Quan sát | Azure Monitor, Container Insights hoặc lựa chọn giám sát hỗ trợ cho môi trường | Telemetry agent/extension, kết nối, Log Analytics workspace, phí thu thập |
| Bảo mật | Microsoft Defender for Cloud/Defender for Containers theo hỗ trợ | Plan, extension/agent, scope, dữ liệu và chính sách bảo mật |
| Truy cập quản trị | Kubernetes RBAC, cơ chế truy cập Arc/cluster connect nếu hỗ trợ | Nhận diện người dùng, quyền Azure **và** Kubernetes, audit, kết nối |
| Dịch vụ chạy tại vị trí hybrid | Các extension/khả năng Arc hỗ trợ tùy nền tảng | Không suy ra mọi dịch vụ Azure có thể chạy ngay trên mọi cluster |

Danh sách extension và tính năng thực tế **thay đổi theo phiên bản Kubernetes, phân phối (distribution), kiến trúc CPU, khu vực, license và điều kiện sản phẩm**. Không coi bảng trên như xác nhận rằng mọi chức năng đều chạy trên mọi cluster.

## 3. Kiến trúc hoạt động của Azure Arc-enabled Kubernetes

Ví dụ tổ chức có hai cluster:

- `k8s-dc1-prod`: cluster Kubernetes tại trung tâm dữ liệu, chạy API Orders cần kết nối SQL Server nội bộ.
- `k8s-edge-01`: cluster tại kho hàng, chạy xử lý sự kiện từ thiết bị và đồng bộ dữ liệu về trung tâm.

~~~mermaid
flowchart TB
    subgraph Azure["Azure management plane"]
        ARM["Azure Resource Manager\nconnectedClusters"]
        POLICY["Azure Policy / governance"]
        GITOPS["Flux configuration / extensions"]
        OBS["Azure Monitor / security"]
    end
    subgraph DC["On-premises datacenter"]
        K1["Kubernetes: k8s-dc1-prod"]
        A1["Azure Arc agents"]
        APP["Orders API + nội bộ SQL"]
        K1 --- A1
        K1 --- APP
    end
    subgraph EDGE["Edge site"]
        K2["Kubernetes: k8s-edge-01"]
        A2["Azure Arc agents"]
        EDGEAPP["Local worker"]
        K2 --- A2
        K2 --- EDGEAPP
    end
    A1 -->|"Outbound TLS / Azure endpoints"| ARM
    A2 -->|"Outbound TLS / Azure endpoints"| ARM
    ARM --> POLICY
    ARM --> GITOPS
    ARM --> OBS
~~~

Sơ đồ biểu diễn mối quan hệ quản trị, **không phải mọi extension đều đi qua cùng một luồng mạng hay proxy**. Các thành phần quan sát và GitOps có thể cần kết nối riêng tới Azure Monitor hoặc Git repository.

### 3.1 Những gì được tạo khi kết nối

Khi bật Arc trên cluster có hỗ trợ, quá trình kết nối thường:

1. Triển khai một tập **Arc agents** vào Kubernetes, phổ biến dưới namespace `azure-arc`.
2. Thiết lập danh tính/kết nối cần thiết giữa agents và dịch vụ Azure Arc.
3. Tạo resource Azure loại **`Microsoft.Kubernetes/connectedClusters`** trong subscription/resource group đã chọn.
4. Hiển thị metadata/trạng thái kết nối trên Azure và cho phép các thao tác quản trị hỗ trợ thông qua extension/configuration.

Một **connected cluster resource** là bản đại diện điều khiển/quản trị; các namespace, Pod, PVC và Kubernetes API server thật vẫn nằm tại nơi cluster được triển khai. Tạo resource Arc **không tạo một bản sao workload** trong Azure.

### 3.2 Khi mất kết nối đến Azure điều gì xảy ra?

Phải phân biệt hai sự cố:

- **Mất đường quản trị Azure, cluster nguồn vẫn chạy:** workload Kubernetes thường có thể tiếp tục phục vụ nếu các phụ thuộc tại chỗ vẫn sẵn sàng. Azure inventory/health có thể trở nên stale và các thao tác cấu hình/policy/extension qua Azure có thể bị trễ hoặc không thực hiện được. Một số agent có cơ chế retry sau khi kết nối lại.
- **Cluster, API server hoặc hạ tầng nguồn lỗi:** Azure Arc **không tự khôi phục control plane, node, storage hay nguồn điện**. Khả năng chịu lỗi phụ thuộc thiết kế Kubernetes và kế hoạch DR hiện hữu.

GitOps Flux có thể tiếp tục reconcile từ nguồn Git **nếu Flux vẫn chạy và truy cập được Git repo**; không khẳng định điều này trong mọi kiểu mất mạng. Nếu Git nằm ngoài site và đường Internet mất, vòng reconcile có thể dùng trạng thái nguồn đã cache hoặc không lấy được phiên bản mới, tùy controller. Chính sách tổ chức cần quyết định ứng xử khi offline thay vì mặc định “Azure quản lý được mọi lúc”.

## 4. Chuẩn bị kết nối một cluster hybrid

### 4.1 Điều kiện kỹ thuật

Trước khi thao tác:

- Cluster Kubernetes thuộc **phân phối/phiên bản/CPU architecture được Azure Arc hỗ trợ**; đã có API server và quyền quản trị hợp lệ. Kiểm tra tài liệu hỗ trợ hiện hành trước khi quyết định.
- `kubectl` đang trỏ tới **đúng context**; có quyền cần thiết để cài agent/CRD/role trong cluster. Onboarding thường cần quyền cao, vì vậy chỉ dùng credential cluster-admin đã được phê duyệt cho bước đăng ký nếu sản phẩm yêu cầu.
- Máy điều khiển có **Azure CLI, kubectl, Helm** hoặc thành phần được quy trình/kênh cài đặt hiện hành yêu cầu; phiên bản tương thích.
- Có subscription Azure, resource group và vùng hỗ trợ lưu metadata. Azure user hoặc service principal được cấp quyền phù hợp để tạo connected cluster và cấu hình liên quan.
- Resource providers **`Microsoft.Kubernetes`** và **`Microsoft.KubernetesConfiguration`** được đăng ký khi tính năng đang dùng yêu cầu. Đăng ký provider là thao tác trên subscription, cần quyền quản trị.
- Cluster/agents có **outbound HTTPS/TLS** tới các endpoint Azure bắt buộc; DNS, proxy/firewall, trust store, time sync và khả năng kéo container images phải đáp ứng yêu cầu. Kiểm tra danh sách hostname/port chính thức theo region và extension, thay vì mở egress toàn bộ một cách tùy tiện.
- Có người phụ trách **RBAC, network, GitOps, quan sát, billing**; không thực hiện trên cluster production khi chưa có kế hoạch rollback và cửa sổ thay đổi phù hợp.

### 4.2 Kiểm tra context Kubernetes trước khi kết nối

~~~bash
# Các lệnh dưới đây CHỈ ĐỌC trạng thái từ kubeconfig và API server.
kubectl config current-context
kubectl cluster-info
kubectl get nodes -o wide
kubectl get namespaces

# Kiểm tra quyền đã có, không tự cấp quyền mới.
kubectl auth can-i create namespaces
kubectl auth can-i create clusterrolebindings
~~~

Nếu có nhiều cluster trong kubeconfig, phải xác minh context và endpoint thật. **Sai context là một trong những rủi ro cao nhất**: lệnh Arc connect có thể đăng ký nhầm cluster, tạo agent trên production thay vì lab. Trong runbook, ghi lại cluster UID/context, region, resource group và owner trước khi bấm GO.

### 4.3 Kiểm tra subscription và resource providers

~~~bash
# Đăng nhập bằng cơ chế tổ chức quy định trước khi chạy.
az account show \
  --query "{subscription:id,name:name,tenant:tenantId}" \
  --output table

az provider show --namespace Microsoft.Kubernetes \
  --query "{namespace:namespace,state:registrationState}" -o table
az provider show --namespace Microsoft.KubernetesConfiguration \
  --query "{namespace:namespace,state:registrationState}" -o table
~~~

Khi có phê duyệt để đăng ký provider, người quản trị có thể chạy:

~~~bash
# CÁC LỆNH NÀY THAY ĐỔI ĐĂNG KÝ RESOURCE PROVIDER Ở SUBSCRIPTION.
az provider register --namespace Microsoft.Kubernetes
az provider register --namespace Microsoft.KubernetesConfiguration
~~~

Không cấp role Owner toàn subscription chỉ để thử một cluster. Thiết kế role Azure theo phạm vi resource group khi có thể, kiểm tra điều kiện đăng ký provider và tách rõ credential Azure khỏi credential Kubernetes.

## 5. Onboard cluster vào Azure Arc qua Azure CLI

### 5.1 Cài extension CLI phù hợp

Ví dụ dưới đây dành cho môi trường lab. Một số lệnh `connectedk8s`, `k8s-extension` hoặc `k8s-configuration` được cung cấp qua Azure CLI extensions; kiểm tra hỗ trợ và cú pháp đúng phiên bản đang sử dụng:

~~~bash
az extension add --name connectedk8s
az extension add --name k8s-extension
az extension add --name k8s-configuration

# Xem extension đang cài; trên máy quản trị có thể đã được cài sẵn.
az extension list \
  --query "[].{name:name,version:version}" \
  --output table
~~~

Lệnh `az extension add` thay đổi **môi trường CLI cục bộ**, chưa tác động cluster. Đối với automation, nên dùng phiên bản Azure CLI/extensions đã kiểm thử, không để pipeline ngầm nâng phiên bản trong một bước release quan trọng.

### 5.2 Tạo resource group quản trị nếu chưa có

~~~bash
# Ví dụ, CHỈ chạy khi tổ chức đã cho phép tạo RG lab.
az group create \
  --name rg-arc-hybrid-lab \
  --location southeastasia
~~~

Đây là **thao tác tạo resource group thật** trên Azure, khác với các lệnh kiểm tra chỉ đọc. Location dùng cho **resource quản trị và metadata**; nó **không di chuyển pod hoặc node** tới `southeastasia`.

### 5.3 Kết nối cluster đã được phê duyệt

~~~bash
# Lệnh thay đổi CẢ cluster nguồn (cài Arc agents) VÀ Azure (tạo resource).
# Trước khi chạy, xác nhận kubectl context và subscription đúng.
az account set --subscription "<subscription-id>"
kubectl config current-context

az connectedk8s connect \
  --name arc-dc1-lab \
  --resource-group rg-arc-hybrid-lab \
  --location southeastasia
~~~

Trong lab, sử dụng một cluster thử nghiệm có quyền và hỗ trợ đầy đủ. Tên `arc-dc1-lab` là **tên resource Azure**, không bắt buộc trùng tên context Kubernetes. Khi tổ chức quản lý nhiều cluster, nên đặt tên phản ánh location/site, environment, chủ sở hữu mà không đưa dữ liệu nhạy cảm vào tên.

### 5.4 Kiểm chứng hai phía sau khi connect

~~~bash
# Phía Azure: CHỈ ĐỌC resource Arc và thông tin kết nối.
az connectedk8s show \
  --name arc-dc1-lab \
  --resource-group rg-arc-hybrid-lab \
  --output json

az resource list \
  --resource-group rg-arc-hybrid-lab \
  --resource-type "Microsoft.Kubernetes/connectedClusters" \
  --output table

# Phía Kubernetes: CHỈ ĐỌC pods và workloads của Arc agents.
kubectl get pods -n azure-arc
kubectl get deployments -n azure-arc
~~~

Kiểm tra namespace nếu bản phân phối/quy trình đăng ký thực tế sử dụng tên khác hoặc agent chưa sẵn sàng. Một số agent có thể được khởi động lại trong quá trình cài/đăng ký; quan sát events, image pull và lỗi mạng thay vì chỉ nhìn một lần `kubectl get pods`.

**Tiêu chí kết nối đạt** cần có cả resource Azure và agent phía nguồn hoạt động đúng kỳ vọng. Nhưng trạng thái Arc Connected **không phải bằng chứng** các application deployments, storage hoặc ingress trong cluster khỏe.

## 6. Quản trị inventory theo Azure Resource Manager

Khi cluster xuất hiện như `Microsoft.Kubernetes/connectedClusters`, tổ chức có thể dùng **resource group, tags, Azure RBAC, policy ở resource scope và công cụ inventory** để nhìn các cụm hybrid trong cùng mô hình Azure.

### 6.1 Thiết kế nhóm tài nguyên và tags

Ví dụ quy tắc gắn tag:

| Tag | Ví dụ | Mục đích |
| --- | --- | --- |
| `environment` | `prod`, `staging`, `lab` | Phân biệt ảnh hưởng thay đổi |
| `site` | `dc1`, `edge-hn01` | Nhận biết vị trí vật lý/logic |
| `owner` | `platform-team` | Người nhận cảnh báo và change approval |
| `businessUnit` | `commerce` | Phân bổ trách nhiệm và ngân sách |
| `dataClassification` | `internal` | Định hướng chính sách bảo mật |
| `recoveryTier` | `tier1` | Ưu tiên DR, SLO và hỗ trợ |

Azure tags trên resource Arc **không tự lan thành Kubernetes labels/annotations** trong workload. Nếu cần gắn nhãn namespace, deployment hoặc policy chọn cluster, cần cấu hình đồng bộ riêng hoặc GitOps.

### 6.2 Tách quyền Azure và quyền Kubernetes

Hai lớp quyền luôn cần phân biệt:

- **Azure RBAC:** kiểm soát ai được xem/sửa connected cluster resource, extension, configuration và các đối tượng Azure liên quan.
- **Kubernetes RBAC:** kiểm soát ai được thao tác `get`, `list`, `update`, `delete` với pods, deployments, secrets và cluster-level resources thông qua Kubernetes API.

Một người có quyền **Reader** trên Azure Arc resource không tự có quyền `cluster-admin` trong Kubernetes. Ngược lại, có kubeconfig admin **không mặc định** cho quyền sửa Azure Policy hoặc resource group.

Một số khả năng như **Azure RBAC for Kubernetes authorization** hoặc **Cluster Connect** có thể được bật trên cluster Arc khi môi trường/tính năng hỗ trợ, tạo đường tích hợp nhận dạng/ủy quyền bổ sung. Phải cấu hình, kiểm tra RBAC theo nguyên tắc quyền tối thiểu, logging và điều kiện kết nối; **không giả định** tính năng đó được bật chỉ vì đăng ký Arc.

### 6.3 Danh mục quản lý nhiều cluster

Một tổ chức có thể đặt cluster lab và production vào các resource groups/subscriptions khác nhau để áp policy, phân quyền, giới hạn blast radius và báo cáo chi phí. Tránh gom mọi cluster dưới một tài khoản quản trị toàn cục mà không có phân tách nhiệm vụ.

Ví dụ bảng inventory do nhóm duy trì:

| Arc resource | Nơi chạy thật | Owner | Mục tiêu dịch vụ | Trạng thái cần theo dõi |
| --- | --- | --- | --- | --- |
| `arc-dc1-prod` | DC1 on-premises | Platform | Orders API production | Arc connectivity + workload health |
| `arc-edge-hn01` | Edge HN01 | Edge Ops | Sync events | Offline duration + queue backlog |
| `arc-lab01` | Lab | Enablement | Test GitOps/policy | Không gây ảnh hưởng production |

Đừng dùng cột connectivity làm chỉ số availability duy nhất. Tình trạng `Offline` có thể phản ánh mất đường quản trị trong khi Pod vẫn chạy, hoặc ngược lại agent Connected nhưng workload đang CrashLoopBackOff.

## 7. GitOps bằng Flux: cấu hình cluster từ Git

### 7.1 GitOps giải quyết configuration drift

Trong mô hình thao tác thủ công, một người có thể chạy `kubectl edit deployment` trên production. Thay đổi đó không nằm trong repository, có thể biến mất ở lần deploy sau hoặc khiến các cluster lệch nhau.

**GitOps** đặt cấu hình mong muốn trong Git; một controller như **Flux** liên tục so sánh trạng thái cluster với nội dung đã duyệt và reconcile khi có khác biệt theo phạm vi cấu hình. Azure Arc có khả năng tích hợp GitOps/Flux thông qua extension và resource configuration phù hợp.

~~~mermaid
flowchart LR
    PR["Pull request + review + CI"] --> REPO["Git repo được bảo vệ"]
    REPO --> FLUX["Flux controllers trên cluster hybrid"]
    FLUX --> NS["Namespaces / Deployments / Services"]
    NS --> HEALTH["Health + telemetry"]
    HEALTH -->|Lỗi -> PR rollback| REPO
    AZ["Azure Arc extension / configuration"] --> FLUX
~~~

Đây là sơ đồ điều khiển cấu hình. Luồng triển khai thực tế có thể bổ sung OCI registry, Helm chart repository, private repo credentials, secret management hoặc image automation. Nên chọn một **nguồn chân lý** rõ ràng: không vừa để Flux quản lý một resource vừa thường xuyên sửa thủ công cùng resource.

### 7.2 Cấu trúc repo cho nhiều cluster

Ví dụ minh họa:

~~~text
platform-gitops/
  base/
    namespaces/
    observability/
    network-policies/
  clusters/
    dc1-prod/
      kustomization.yaml
      apps/
      policies/
    edge-hn01/
      kustomization.yaml
      apps/
      policies/
    lab01/
      kustomization.yaml
      apps/
~~~

Chia **base** để tái sử dụng cấu hình phổ biến; thư mục môi trường/cluster lưu những khác biệt được phê duyệt. Với `prod`, áp branch protection, reviewer bắt buộc, kiểm tra policy/schema, scan container và secrets. Giữ credential khỏi Git hoặc dùng cơ chế mã hóa/secret manager hỗ trợ, không commit token dạng rõ.

### 7.3 Bật Flux extension qua Azure CLI

Ví dụ dưới đây **có thay đổi thực**: triển khai extension Flux xuống cluster đã kết nối. Chỉ chạy sau khi đã phê duyệt scope/role và đã xác nhận Kubernetes version, egress và khả năng extension tương thích.

~~~bash
# Tạo Flux extension cho một Arc-enabled cluster lab.
az k8s-extension create \
  --name flux \
  --cluster-type connectedClusters \
  --cluster-name arc-dc1-lab \
  --resource-group rg-arc-hybrid-lab \
  --extension-type microsoft.flux

# Chỉ đọc danh sách extension được đăng ký.
az k8s-extension list \
  --cluster-type connectedClusters \
  --cluster-name arc-dc1-lab \
  --resource-group rg-arc-hybrid-lab \
  --output table
~~~

Tên extension, tùy chọn và khả năng hỗ trợ tùy Azure CLI/extensions ở thời điểm thao tác. Không sao chép nguyên lệnh sang production trước khi kiểm tra tài liệu, version và quyền thực tế.

### 7.4 Tạo cấu hình Flux theo Git repository

Một ví dụ **minh họa** cho Git repo công khai chứa cấu hình lab (thay URL/path bằng repo đã được kiểm tra; không đưa secret vào command line):

~~~bash
# Lệnh này TẠO cấu hình GitOps và có thể khiến Flux áp manifests xuống cluster.
az k8s-configuration flux create \
  --resource-group rg-arc-hybrid-lab \
  --cluster-name arc-dc1-lab \
  --cluster-type connectedClusters \
  --name platform-lab \
  --namespace flux-system \
  --scope cluster \
  --url https://github.com/example-org/platform-gitops \
  --branch main \
  --kustomization name=platform path=./clusters/lab01 prune=true

# CHỈ ĐỌC cấu hình GitOps đã đăng ký.
az k8s-configuration flux list \
  --resource-group rg-arc-hybrid-lab \
  --cluster-name arc-dc1-lab \
  --cluster-type connectedClusters \
  --output table
~~~

Repo `example-org/platform-gitops` là **placeholder**, không phải repo được xác minh hay một lệnh chạy được ngay. Với repo riêng, cần cấu hình phương thức xác thực được hỗ trợ (SSH key, token/identity hoặc cơ chế khác theo sản phẩm), phân quyền tối thiểu, rotation và tuyệt đối không đặt credential trong command history hoặc Git.

**`prune=true` có thể xóa tài nguyên do Flux quản lý nếu khai báo của chúng biến mất khỏi nguồn Git**. Trong production, cần rõ phạm vi resource thuộc quyền Flux, strategy phê duyệt thay đổi phá hủy, bảo vệ namespace quan trọng và quy trình phục hồi. Đừng bật prune chỉ vì ví dụ sử dụng nó.

### 7.5 Trạng thái reconcile cần quan sát

Một GitOps rollout được xem là đạt khi:

1. Git revision đúng commit đã duyệt và source fetch thành công.
2. Flux `GitRepository`/`Kustomization` hoặc `HelmRelease` (nếu dùng) có điều kiện Ready phù hợp.
3. Kubernetes Deployment rollout hoàn tất, replicas ready, service/ingress phục vụ được.
4. SLI ứng dụng (success/latency) đạt mục tiêu; không có lỗi mới ở dependency.
5. Có đường rollback bằng commit/revert hoặc cách khôi phục đã thử, không chỉ “lệnh apply thành công”.

~~~bash
# Các lệnh dưới đây CHỈ ĐỌC trạng thái trong cluster.
kubectl get pods -n flux-system
kubectl get gitrepositories,kustomizations -A
kubectl get deployments -A

# Ví dụ đối chiếu một app sau khi Flux đã sync cấu hình.
kubectl rollout status deployment/orders-api -n orders --timeout=180s
~~~

Namespace, CRD và Deployment `orders-api` chỉ tồn tại khi đã cài đúng controller và workload tương ứng. Nếu `kubectl get gitrepositories` báo unknown resource, hãy kiểm tra extension/CRD Flux, không suy ra repository bị lỗi.

## 8. Chính sách nhất quán với Azure Policy

Azure Policy giúp tổ chức đặt quy tắc và xem compliance cho các tài nguyên Azure. Với **Kubernetes hỗ trợ qua Azure Arc**, có thể kết hợp **Azure Policy for Kubernetes** và extension/thành phần thực thi tương ứng để audit/enforce một số quy tắc đối với cluster.

Một số mục tiêu quản trị:

- Chỉ cho phép image đến từ registry đã duyệt theo policy được hỗ trợ.
- Yêu cầu namespace/workload có label owner hoặc environment.
- Cảnh báo hoặc từ chối Pod chạy privileged hay cấu hình rủi ro, khi policy hỗ trợ loại validation đó.
- Yêu cầu resource requests/limits hoặc cấm một số cấu hình host namespace/host path theo chính sách cụ thể.
- Audit compliance từ góc nhìn subscription/resource group để giảm lệch cấu hình giữa các site.

**Chú ý phân biệt hai tầng:**

- Azure Policy được **assign** ở management group/subscription/resource group/resource khi khả năng chính sách hỗ trợ.
- Kubernetes policy/admission được **thực thi bên trong cluster** bởi các thành phần tương ứng. Việc assign policy trong Azure không tự bảo đảm ngay lập tức admission enforcement ở cluster đang offline hoặc chưa cài extension.

### 8.1 Quy trình áp policy an toàn

1. Thống nhất nội dung policy với đội platform, ứng dụng và bảo mật; kiểm tra tác động tới workload hiện có.
2. Xác minh policy definition/effect và extension liên quan **được hỗ trợ trên Kubernetes distribution/version** thực tế.
3. Bắt đầu bằng **Audit** hoặc chế độ chỉ quan sát nếu policy cho phép; đo số tài nguyên vi phạm, owner và ngoại lệ.
4. Khắc phục manifests/GitOps trước, đo lại compliance; sau đó cân nhắc **Deny** hoặc enforcement khi không gây outage.
5. Dùng exemption có lý do, scope, người duyệt và thời hạn; không xóa bỏ kiểm soát với cả subscription để xử lý một ứng dụng.
6. Theo dõi khi cluster disconnect: trạng thái Azure compliance có thể không còn mới; quy trình kiểm tra tại cluster và báo cáo offline vẫn cần có.

Ví dụ một quy tắc mong muốn là mọi Pod production có `resources.requests.cpu` và `resources.requests.memory`. Đừng tự giả định Azure Policy cung cấp đúng template/effect này ở mọi release; hãy chọn built-in policy được hỗ trợ hoặc custom policy theo cơ chế phù hợp và kiểm tra ở lab trước.

### 8.2 GitOps và policy bổ sung, không thay thế nhau

GitOps nói **muốn cluster ở trạng thái nào**; policy xác định **trạng thái nào được phép hoặc cần cảnh báo**. Khi một PR thêm container privileged:

- CI/policy-as-code có thể phát hiện trước merge.
- Azure/Kubernetes policy ở cluster có thể audit hoặc chặn admission theo cấu hình.
- Flux sẽ báo reconcile thất bại nếu object bị admission từ chối; người vận hành phải đọc cả kết quả Flux và policy violation.

Nếu chưa thiết kế cơ chế xử lý, một policy bật Deny đột ngột có thể làm rollout bị kẹt. Việc kiểm soát bản release đòi hỏi cả Git review và policy deployment có quy trình.

## 9. Quan sát hybrid cluster với Azure Monitor và công cụ tại chỗ

### 9.1 Cần theo dõi hai lớp trạng thái

| Lớp | Tín hiệu | Vì sao cần |
| --- | --- | --- |
| **Arc management connectivity** | Connected/Disconnected, agent health, extension provisioning | Biết Azure có nhận và áp cấu hình quản trị được không |
| **Kubernetes control plane** | API reachability, etcd health (khi có quyền đo), scheduler/controller | Đánh giá nền tảng vận hành tại site |
| **Node** | Ready/NotReady, CPU/memory/disk pressure, kubelet | Nhận diện lỗi node và capacity |
| **Workload** | Pods Ready, restarts, OOMKilled, Pending, CrashLoopBackOff | Đánh giá deployment và runtime |
| **Application SLI** | Tỷ lệ request thành công, latency, queue lag, đúng dữ liệu | Đo tác động thực tới người dùng |
| **GitOps/policy** | Reconcile Ready, drift, admission errors, compliance | Biết cấu hình có đang được áp đúng không |
| **Hybrid connectivity** | DNS, TLS, proxy, Azure/Git endpoint latency, egress errors | Phân biệt lỗi ứng dụng với lỗi đường quản trị |

Chỉ có trạng thái Connected hoặc `kubectl get nodes` xanh **không chứng minh** hành trình đặt hàng đang chạy đúng. Nên có synthetic probes và distributed tracing theo critical path, bao gồm database và API đối tác nếu ứng dụng cần.

### 9.2 Azure Monitor / Container Insights

Có thể tích hợp Azure Monitor với môi trường Arc-enabled Kubernetes **theo khả năng hiện hành của loại cluster**, thường thông qua extension/agent được hỗ trợ và Log Analytics workspace hoặc đích telemetry tương ứng.

Trước khi bật:

- Xác minh loại cluster, OS/node architecture, extension và vùng hỗ trợ.
- Chọn workspace, retention, data collection rules/filters nếu tính năng cung cấp.
- Tính trước **data ingestion, retention, query và egress cost**; không bật log verbosity cao cho mọi namespace mà không quản lý volume.
- Đảm bảo DNS, outbound, proxy/CA và danh tính cần thiết; extension có thể tạo DaemonSet/Pod tiêu thụ tài nguyên tại cluster nguồn.
- Giám sát đường gửi dữ liệu; thiếu logs trên Azure có thể là mất kết nối telemetry, **không có nghĩa Kubernetes không có lỗi**.

Khi dùng Log Analytics, schema như `KubePodInventory`, `ContainerLogV2` hoặc các bảng khác có thể phụ thuộc phương thức thu thập/định dạng. Luôn kiểm tra bảng và trường được cung cấp trong workspace thực tế; không áp một truy vấn KQL cũ cho mọi pipeline.

Ví dụ **truy vấn minh họa**, chỉ dùng khi workspace có bảng `KubePodInventory` và các trường tương ứng:

~~~kusto
KubePodInventory
| where TimeGenerated >= ago(30m)
| where Namespace == "orders"
| summarize LastSeen = max(TimeGenerated),
            Observations = count()
  by ClusterName, Name, PodStatus
| order by LastSeen desc
~~~

Truy vấn trên **không tự chứng minh** SLI của Orders. Để tính SLO cần telemetry từ ingress/ứng dụng có định nghĩa good/bad requests, cỡ mẫu và cửa sổ đánh giá. PodStatus từ một bản ghi tồn tại cũng không đồng nghĩa endpoint thực sự tiếp nhận lưu lượng.

### 9.3 Giám sát tại chỗ khi mất WAN

Nếu cluster là hệ thống sản xuất tại nhà máy hoặc edge site, cần một đường giám sát **độc lập với kết nối Azure**: log buffer tại chỗ, local dashboards, alert tới nhân sự tại site hoặc cơ chế tập trung khác có khả năng store-and-forward.

Mục tiêu là phát hiện khi:

- Azure Arc agents không report, nhưng Pod vẫn phục vụ tại site.
- Git repo ngoài site không truy cập được nên cấu hình mới chưa được đồng bộ.
- WAN mất khiến ứng dụng không đồng bộ dữ liệu, backlog tăng, nhưng health probe HTTP local vẫn trả 200.

Ghi rõ SLO cho **khả năng phục vụ tại site** và cho **đồng bộ với trung tâm** có thể khác nhau; không dùng một chỉ số Connected để kết luận cả hai đều đạt.

## 10. Bảo mật, identity và quản trị nhiều tenant

### 10.1 Phân tầng quyền và danh tính

| Lớp | Quyền/danh tính | Nguy cơ nếu làm sai |
| --- | --- | --- |
| Azure subscription/resource group | Azure RBAC cho Arc resources, extension/configuration | Người không phù hợp điều khiển GitOps hoặc thay đổi policy toàn site |
| Kubernetes API | Kubernetes RBAC, service accounts, audit | Một kubeconfig có thể thay đổi toàn cluster |
| GitOps controller | Quyền Flux service accounts và nguồn Git | Controller hoặc repo bị lộ có thể sửa nhiều namespace |
| Registry, secrets, cloud APIs | Token/secret/identity dành cho workload | Rò khóa, pull image sai hoặc truy cập dữ liệu trái phép |
| Network | Firewall, proxy, TLS, DNS, private connectivity | Mất đường quản trị hoặc mở egress quá rộng |

Đừng cho Flux quyền cluster-admin để quản lý một namespace ứng dụng nếu có thể giới hạn scope. Tương tự, service principal dùng trong pipeline chỉ cần quyền trên resource group/cluster và thao tác đã được phê duyệt; tránh tái sử dụng một credential cho cả production và lab.

### 10.2 Quản lý secrets

- **Không commit secret rõ vào Git** và không đặt token trong output terminal hoặc log CI.
- Khi dùng GitOps, chọn cơ chế quản lý secret hỗ trợ (ví dụ Secret Store/External Secrets, cơ chế mã hóa GitOps, Azure Key Vault integration phù hợp) và kiểm tra danh tính của workload trên **hạ tầng nguồn**.
- Không suy rằng Pod trên cluster Arc tự nhận managed identity Azure giống AKS; cần cấu hình identity/federation hoặc secret access theo tính năng hỗ trợ và kiến trúc thực tế.
- Có quy trình rotate/revoke credential, logging quyền truy cập và phương án offline khi secret store bên ngoài site không thể truy cập.
- Cấu hình Kubernetes NetworkPolicy, admission, image verification, runtime hardening theo CNI/cluster hỗ trợ, không mặc định Azure Arc tự bật chúng.

### 10.3 Cluster Connect và truy cập từ xa

Một số cluster Arc hỗ trợ **Cluster Connect** để tạo đường truy cập Kubernetes API thông qua cơ chế Azure quản lý, có điều kiện về tính năng, agent, người dùng và quyền. Khi sử dụng:

1. Chỉ bật nếu cần và supported.
2. Áp quyền Azure và Kubernetes theo mô hình ủy quyền tương ứng.
3. Bật audit/monitoring, hạn chế phiên quản trị và xem xét session lifecycle.
4. Kiểm tra network prerequisites và thử trong lab trước production.

**Không xem Cluster Connect là VPN site-to-site**, và không giả định bật tính năng này tự cấp quyền Kubernetes cluster-admin cho người dùng. Một đường truy cập quản trị không thay thế kết nối ứng dụng tới database, registry hoặc DNS tại site.

### 10.4 Governance khi có nhiều cluster

Đặt chính sách onboarding:

- Mỗi cluster cần owner, environment, contact, data classification và expiration/review date.
- Cluster production có người duyệt khi cài extension, thay đổi GitOps repo/path hoặc Azure RBAC.
- Dùng release ring: lab → staging → một site canary → các site còn lại.
- Không nâng Flux/controller/agent đồng loạt trên mọi site nếu chưa thấy kết quả của nhóm canary.
- Thu thập inventory thường xuyên; khi một cluster bị xóa ngoài ý muốn ở nguồn, cần dọn resource Arc cũ theo phê duyệt.

## 11. Vận hành Day-2: upgrade, drift và sự cố

### 11.1 Ai nâng cấp Kubernetes?

Azure Arc-enabled Kubernetes **không tự điều hành nâng cấp control plane/node của cluster on-premises**. Đội vận hành phải tuân theo quy trình của nhà cung cấp phân phối, bảo vệ quorum/etcd, backup, PodDisruptionBudget, capacity dự phòng và test compatibility.

Các lớp có chu kỳ nâng cấp khác nhau:

1. **Kubernetes distribution, control plane và worker nodes:** theo hạ tầng nguồn.
2. **CNI, CSI, ingress, storage và monitoring stack:** theo nhà cung cấp/thành phần cụ thể.
3. **Azure Arc agents/extensions/Flux:** theo chu kỳ và cách cập nhật được Azure hỗ trợ.
4. **Workloads:** triển khai qua CI/CD/GitOps cùng health gates.

Nâng cấp chỉ một lớp không chứng minh các lớp khác tương thích. Khi mở rộng use case, ghi version matrix và thử nghiệm ở cluster tương đương trước.

### 11.2 Quản trị drift

Ba loại drift cần phân biệt:

- **GitOps drift:** manifest đang chạy khác với Git commit đã phê duyệt.
- **Platform drift:** Kubernetes version, CNI, admission, storage class hoặc runtime configuration lệch giữa các site; Flux chỉ thấy phần có trong phạm vi quản lý.
- **Azure management drift:** resource Arc, extension, policy assignment hoặc tags khác baseline IaC.

Gợi ý xử lý: phát hiện, phân loại mức ảnh hưởng, xác định nguồn chân lý, tạo PR/IaC change phù hợp và kiểm tra lại sau reconcile. Tránh dùng `kubectl edit` trực tiếp để sửa lâu dài nếu Flux đang quản lý resource đó; thay đổi thủ công có thể bị ghi đè.

### 11.3 Runbook khi status Arc bị Disconnected

1. **Xác nhận Kubernetes vẫn phục vụ:** `kubectl get nodes`, kiểm tra pod/ingress và synthetic transaction tại site.
2. **Xác nhận đúng scope Azure:** subscription, resource group, connected cluster resource, thời điểm status được cập nhật.
3. **Kiểm tra agent health:** namespace `azure-arc`, pod events, image pull, restarts và logs có liên quan; xử lý credential/log cẩn thận.
4. **Kiểm tra kết nối:** DNS, HTTPS egress, proxy, certificate CA, clock/time sync, endpoint restrictions và Git/extension endpoints khi áp dụng.
5. **Phân loại tác động:** chỉ management plane, GitOps sync, policy compliance, monitoring ingestion hay ứng dụng thật?
6. **Khôi phục theo runbook:** sửa network/permissions/agent có kiểm soát, không vội xóa resource Arc hay cài lại toàn bộ.
7. **Đối soát sau kết nối:** status, extension/GitOps Ready, policy, telemetry mới và workload SLI; ghi timeline và bài học.

Nếu cluster mất toàn bộ WAN, việc khôi phục phụ thuộc đội mạng/hạ tầng. Không dùng lỗi “Disconnected” làm lý do tự động restart tất cả Pods — có thể biến sự cố quản trị thành sự cố ứng dụng.

## 12. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `az connectedk8s connect` báo sai cluster/context | kubeconfig chọn nhầm context hoặc không tới API | Xác nhận context, endpoint, cluster identity, quyền local |
| Arc agents không Ready | Image pull, tài nguyên thiếu, PodSecurity/admission, DNS/proxy, RBAC | Xem events/pods đúng namespace, capacity và prerequisites |
| Resource Arc tồn tại nhưng Disconnected | Outbound Azure endpoint bị chặn, TLS/CA, proxy, time sync hoặc agent lỗi | Kiểm tra egress và agent health, đối chiếu Azure status timestamp |
| Không thể tạo extension | Chưa đăng ký provider, role không đủ, version/region/cluster không hỗ trợ | Kiểm tra provider, Azure RBAC, compatibility, extension provisioning details |
| Flux không kéo repo | Git URL/branch/path sai, credential hết hạn, DNS/firewall | Xem Flux source status, xác minh repo và kết nối từ cluster |
| Flux Ready nhưng app không khỏe | Manifest hợp lệ nhưng app/config, database, image hoặc readiness lỗi | Kiểm tra rollout, events, logs, dependencies và SLI |
| Policy có vi phạm bất ngờ | Policy scope/effect mới, resource không theo baseline, admission thay đổi | Kiểm tra assignment, constraint, exemption và lịch sử PR |
| Không thấy log trên Azure | DCR/agent/extension/egress hoặc retention/cost limit | Đối chiếu local logs, dữ liệu ingestion và phạm vi thu thập |
| Azure RBAC đã cấp nhưng kubectl bị Forbidden | Quyền Azure và Kubernetes/Cluster Connect chưa cấu hình tương ứng | Kiểm tra cơ chế auth được bật, Kubernetes RBAC và token |
| Cluster vẫn chạy khi Arc Disconnected | Management path lỗi nhưng data plane độc lập | Phân biệt mục tiêu phục vụ tại chỗ với quản trị Azure |

### 12.1 Cẩn trọng với việc gỡ kết nối

Xóa connected cluster resource trên Azure hoặc tháo Arc agents có thể làm mất các tích hợp quản trị và có hậu quả với extension/configuration. Tuy nhiên, **đó không phải cách “xóa luôn cluster Kubernetes nguồn”**. Quy trình decommission cần phân biệt:

- Gỡ/cập nhật Flux configuration và bảo toàn workload/data theo chính sách.
- Kiểm tra extension/agent, secrets, quyền, network và chi phí đang phát sinh.
- Hủy đăng ký Arc resource theo runbook được phê duyệt.
- Xử lý **cluster vật lý/ảo thật** bằng quy trình hạ tầng riêng nếu mục tiêu là decommission toàn bộ.

Không thử lệnh delete trên production chỉ để tìm hiểu hành vi. Với GitOps có `prune`, thao tác gỡ cấu hình hoặc repo cần được đánh giá đặc biệt vì có khả năng tác động tới resource Kubernetes.

## 13. Kiến trúc triển khai ứng dụng an toàn trên cluster hybrid

Giả sử Orders API chạy trên cả `k8s-dc1-prod` và `k8s-edge-01`. Một chiến lược triển khai có kiểm soát:

1. CI build image một lần, scan dependency/secret/image và ký/tạo metadata provenance khi quy trình hỗ trợ.
2. Push image tới registry được phép, lưu **immutable digest**; bảo đảm cluster nguồn có đường pull image và credentials.
3. Tạo PR thay đổi GitOps manifests cho **lab cluster**, chạy schema/policy tests, review.
4. Sau lab thành công, promote cùng image digest tới một site canary, đo SLI và lỗi runtime.
5. Khi đạt tiêu chí và đủ thời gian phục hồi, promote theo wave site hoặc namespace đã phê duyệt.
6. Nếu lỗi, revert Git commit/rollout theo runbook; kiểm tra compatibility của dữ liệu và external dependencies.

~~~mermaid
flowchart TD
    CI["Build + scan + ký image"] --> REG["Registry với immutable digest"]
    REG --> PR["PR thay manifest GitOps"]
    PR --> LAB["Flux -> lab cluster"]
    LAB --> G{"Smoke/SLI đạt?"}
    G -->|Không| STOP["Revert + phân tích"]
    G -->|Có| CAN["Flux -> một site canary"]
    CAN --> H{"SLI/ops/chi phí đạt?"}
    H -->|Không| STOP
    H -->|Có| WAVE["Promote từng wave hybrid"]
~~~

### 13.1 Một manifest Deployment minh họa

File này thể hiện các guard cơ bản. **Image digest là placeholder**; phải thay bằng digest hợp lệ do CI tạo. Manifest không tự cung cấp TLS, auth, NetworkPolicy hoặc database connectivity.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
  labels:
    app: orders-api
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: ghcr.io/example-org/orders-api@sha256:REPLACE_WITH_VALID_DIGEST
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /readyz
              port: 8080
            periodSeconds: 10
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
~~~

Cấu hình chỉ là **hướng dẫn cấu trúc**. `namespace: orders` phải tồn tại, registry phải truy cập được, probe phải phản ánh hành vi thật và workload cần secrets/config an toàn. Quy tắc rolling update `maxUnavailable: 0` đòi hỏi đủ capacity cho Pod surge; ở edge site tài nguyên giới hạn, nếu không đủ capacity thì rollout có thể bị Pending. Các giá trị requests/limits là ví dụ, cần đo CPU/RAM theo workload.

### 13.2 Hybrid không bảo đảm dependency ở cùng site

Một API ở edge có thể cần Azure SQL, Service Bus, Entra ID, Key Vault hoặc đối tác SaaS. Hãy đánh giá:

- DNS resolution, egress allowlists, certificate, proxy và độ trễ tới dịch vụ Azure.
- Chế độ ứng dụng khi mất WAN: local queue/cache, idempotency, replay, giới hạn dữ liệu có thể phục vụ offline.
- Tính nhất quán giữa site và trung tâm khi reconnect, tránh duplicate hoặc out-of-order messages.
- RTO/RPO theo từng kịch bản: mất node, mất site, mất mạng WAN, mất database Azure.
- Khả năng dùng private connectivity hoặc network design riêng nếu khả năng và nhu cầu cho phép; Arc onboarding không tự thiết lập VPN/ExpressRoute.

Một cluster đã kết nối Arc nhưng ứng dụng không truy cập được SQL qua network vẫn là **sự cố dữ liệu/ứng dụng**, không thể giải quyết bằng việc gắn thêm tag cho Arc resource.

## 14. Chi phí và giới hạn trách nhiệm

Việc kết nối cluster vào Azure Arc và các dịch vụ bật thêm có thể có **mô hình tính phí khác nhau**. Đừng suy ra “dùng Arc nghĩa là mọi dịch vụ quản lý đều miễn phí”, cũng đừng tính cloud compute cho node đang chạy tại chỗ như thể là Azure VM.

Các nhóm chi phí cần đưa vào business case:

| Khoản mục | Người chi trả / phạm vi chi phí | Cách kiểm soát |
| --- | --- | --- |
| Cluster on-premises/edge | Phần cứng, hypervisor, electricity, network, license, nhân sự | Inventory TCO theo site và workload |
| Internet/MPLS/VPN/ExpressRoute | Hạ tầng kết nối hybrid, egress, bảo trì đường truyền | Dự báo bandwidth, lựa chọn tuyến và dự phòng |
| Azure Monitor / Log Analytics | Ingestion, retention, query/giải pháp theo mô hình giá hiện hành | Data collection filters, retention, sampling và ngân sách |
| Security/Defender plans | Theo plan, scope và loại tài nguyên được hỗ trợ | Chỉ bật các tính năng cần thiết, kiểm tra đơn giá thực |
| Registry/Artifacts | Storage, pull, traffic và image lifecycle | Cleanup image, immutable digest và cache phù hợp |
| Extension/dịch vụ bổ sung | Tùy tính năng và biểu phí công bố | Review pricing/trial/plan trước khi bật quy mô lớn |
| Ngày công vận hành | On-call, upgrade, DR, kiểm thử và chính sách | Automation, canary, runbook, ownership rõ |

Khi đánh giá chi phí, dùng **Azure Cost Management** cho phần Azure phát sinh và hệ thống quản trị nội bộ cho phần on-premises. Azure tags trên resource Arc không tự phân bổ chi phí electricity hoặc phần cứng tại site.

## 15. Bài thực hành end-to-end trên cluster lab

### Bước 1: Ghi phạm vi và giả thuyết

Chọn **một cluster thử nghiệm** được hỗ trợ, có kubeconfig đúng và quyền đã phê duyệt. Mục tiêu: đăng ký vào Azure Arc, xác nhận agents, đặt tag/owner, thử Flux với namespace lab rồi kiểm chứng hạ tầng vẫn chạy khi ngắt đường **quản trị thử nghiệm** (nếu được phép). Không thử cắt network production.

### Bước 2: Trước khi kết nối

- Xác nhận cluster name/context/API endpoint, OS, K8s version và số nodes.
- Đọc network requirements, firewall/proxy và region hỗ trợ.
- Kiểm tra role Azure, quyền Kubernetes, provider registration và resource group.
- Ghi lại trạng thái baseline: namespaces, deployments, Pod readiness và monitoring.

### Bước 3: Kết nối Arc

Dùng các lệnh ở phần 5, thay placeholder bằng subscription, resource group và cluster lab thật. Xác minh **`az connectedk8s show`** có resource đúng và **`kubectl get pods -n azure-arc`** không còn lỗi bất thường. Ghi Azure resource ID, thời gian kết nối và operator.

### Bước 4: Bật GitOps giới hạn

- Tạo repo Git chỉ chứa namespace/app lab đã review, không có secret.
- Cài Flux extension trên cluster lab, tạo cấu hình trỏ đúng path.
- Đặt quy tắc review PR và tránh `prune=true` trên namespace chứa dữ liệu hoặc tài nguyên không thuộc quyền Flux.
- Đổi replicas từ 1 sang 2 qua PR, xác nhận reconciliation và Pod Ready.
- Thử tạo drift vô hại trong phạm vi lab, quan sát Flux reconcile; **không sửa production**.

### Bước 5: Thêm governance và quan sát

- Tạo tag `environment=lab`, `owner=platform` cho Arc resource.
- Kiểm tra role Reader ở Azure có tác dụng gì và không có tác dụng gì ở Kubernetes RBAC.
- Nếu policy extension được hỗ trợ, thử một policy **Audit** đơn giản trong lab; kiểm tra báo cáo compliance và remediation.
- Bật telemetry tối thiểu theo ngân sách hoặc dùng monitoring sẵn có; đo Pod readiness và request success riêng biệt.

### Bước 6: Diễn tập mất đường quản trị (tùy chọn, có phê duyệt)

Ở lab cô lập, có thể mô phỏng mất kết nối outbound tới Azure trong thời gian ngắn **theo cách được team mạng phê duyệt**, với đường khôi phục độc lập. Ghi:

- Workload nội bộ có tiếp tục trả request không?
- Arc resource chuyển trạng thái sau bao lâu (có độ trễ đồng bộ)?
- Flux có còn truy cập Git repo không? Có đủ log để xác nhận?
- Sau khi mạng phục hồi, extension/GitOps/telemetry có đồng bộ lại bình thường không?

**Không được kết luận “mất Azure Arc làm Kubernetes dừng” chỉ vì bảng Azure báo Disconnected.** Đồng thời không tuyên bố hệ thống đảm bảo phục vụ khi offline nếu app phụ thuộc database hoặc cloud identity qua WAN.

### Bước 7: Báo cáo kết quả

~~~yaml
# Mẫu BIÊN BẢN thí nghiệm, KHÔNG phải schema Azure resource.
cluster: arc-dc1-lab
site: dc1-lab
azure_scope: rg-arc-hybrid-lab
operator: platform-lab
checks:
  - name: "Arc resource visible and agent healthy"
    result: "PASS / FAIL / INCONCLUSIVE"
  - name: "Flux reconciles reviewed Git revision"
    result: "PASS / FAIL / INCONCLUSIVE"
  - name: "Kubernetes RBAC least privilege verified"
    result: "PASS / FAIL / INCONCLUSIVE"
  - name: "Application SLI measured independently"
    result: "PASS / FAIL / INCONCLUSIVE"
  - name: "WAN isolation recovery (optional)"
    result: "NOT_RUN / PASS / FAIL"
open_issues:
  - "List any unresolved permissions, network or policy issues"
rollback_owner: platform-team
~~~

Mẫu trên chỉ dùng để ghi kết quả và review, không đưa trực tiếp vào API Arc. Các trạng thái PASS/FAIL chỉ hợp lệ khi có bằng chứng; khi không có telemetry hoặc không chạy bước kiểm thử, dùng **INCONCLUSIVE/NOT_RUN**.

## 16. Checklist triển khai cho môi trường production

| Hạng mục | Câu hỏi trước khi duyệt |
| --- | --- |
| Scope/owner | Có resource ID, site, môi trường, người chịu trách nhiệm và data classification? |
| Kubernetes | Distribution/version/architecture, HA, CNI/CSI, storage, backup, DR đã được xác nhận? |
| Azure | Subscription/resource group/location, provider, tags, policy, quyền Azure đúng? |
| Kubeconfig/RBAC | Chọn đúng context, có credential/onboarding quyền tối thiểu và kế hoạch thu hồi? |
| Connectivity | DNS, TLS, proxy, Azure endpoints, Git registry và kết nối ứng dụng được phân biệt rõ? |
| Agents | Arc namespace, pods/extension health và nhu cầu tài nguyên đã kiểm chứng? |
| GitOps | Repo owner, branch protections, source auth, Flux scope, prune policy và rollback đã duyệt? |
| Policy | Bắt đầu Audit, remediation, exemption và kiểm tra offline rõ ràng? |
| Observability | Arc status, Kubernetes health, SLI ứng dụng và alert khi WAN mất? |
| Secrets | Không commit secret, có rotation, identity và giải pháp offline phù hợp? |
| Day-2 | Upgrade matrix, capacity, on-call, incident runbook và decommission plan? |
| Chi phí | Log ingestion, security, network, registry và phần cứng on-prem đã được ước tính? |

Một cluster không nên được đánh dấu “production-ready” chỉ vì `az connectedk8s connect` trả về mã thành công. Cần có bằng chứng về **workload, dữ liệu, bảo mật, giám sát và phục hồi**, không chỉ trạng thái quản trị Azure.

## 17. Bài tập vận dụng và câu hỏi tự kiểm tra

### Bài tập 1: Quản trị tập trung có nghĩa gì?

Một cluster Kubernetes ở trung tâm dữ liệu đang chạy API Orders. Sau khi đăng ký Azure Arc, tài nguyên hiện trong resource group trên Azure. Người quản trị kết luận: “Từ nay Azure đã vận hành các node và nâng Kubernetes tự động; ta không cần backup nữa.”

**Đáp án:** Sai. Arc đăng ký **connected cluster resource** và các khả năng quản trị liên quan, không chuyển ownership của control plane, node, storage hoặc dữ liệu. Đội nguồn vẫn phải duy trì backup, upgrade, networking, security, HA và DR theo loại cluster. Azure Arc có thể giúp quản trị policy/GitOps/observability khi được cấu hình, nhưng không thay thế trách nhiệm vận hành Kubernetes.

### Bài tập 2: Lỗi quản trị hay lỗi ứng dụng?

Trong 12 phút, Azure hiển thị cluster Arc `Disconnected`. Tại site, `kubectl get nodes` trả toàn bộ `Ready`, synthetic test nội bộ có 9.990 request tốt trên 10.000 request hợp lệ; một workload khác phụ thuộc SQL trên Azure đang timeout vì WAN mất.

**Hỏi:** Tỷ lệ request tốt của synthetic test nội bộ là bao nhiêu? Có thể kết luận toàn bộ hệ thống vẫn đạt SLO không?

**Lời giải:**

\[
\mathrm{LocalSuccessRate}=\frac{9\,990}{10\,000}\times100\%=99{,}9\%.
\]

Chỉ có thể nói **hành trình nội bộ được đo** đạt 99,9% trong cửa sổ đó. Không thể kết luận workload SQL đạt SLO vì nó đang timeout; không thể suy ra mọi Pod khỏe hay dữ liệu đồng bộ. Cần tách sự cố Arc management connectivity, WAN/data dependency và SLI từng ứng dụng.

### Bài tập 3: Thiết kế rollout GitOps ba site

Tổ chức có ba cluster: `lab01`, `dc1-prod` và `edge-hn01`. Một PR thay đổi container image và giới hạn bộ nhớ của API. Hãy thiết kế:

1. Thứ tự rollout có giảm blast radius.
2. Điều kiện dừng/rollback khi memory pressure hoặc request error tăng.
3. Cách bảo vệ Git repo và giới hạn quyền Flux trong production.

**Gợi ý đáp án:** Bắt đầu `lab01`, đo dữ liệu và SLI; tiếp tục site canary có lượng traffic giới hạn, sau đó mới đến các cluster production còn lại. Gắn image digest bất biến, kiểm tra memory/OOMKilled, latency/timeout và Pod readiness; nếu vượt ngưỡng đã duyệt thì dừng promote và revert theo runbook, đồng thời kiểm tra backward compatibility. Repo cần PR review, protection, scan secrets/image và controller/service account với quyền tối thiểu.

### Bài tập 4: Tính chi phí giám sát theo dữ liệu

Hai site gửi trung bình **6 GiB log/ngày/site** vào một dịch vụ tính tiền theo ingestion. Giả sử giá ingestion **1,50 USD/GiB** để thực hành phép tính (không phải bảng giá Azure hiện hành), tạm bỏ qua retention và phí khác. Chi phí 30 ngày được ước tính:

\[
2\times6\times30\times1{,}50=540\ \mathrm{USD}.
\]

Nếu lọc bớt telemetry không cần thiết và giảm mức gửi xuống **4 GiB/ngày/site**, ước tính còn:

\[
2\times4\times30\times1{,}50=360\ \mathrm{USD},
\]

tức **tiết kiệm 180 USD/30 ngày** theo giả định này. Phải đảm bảo lọc log không làm mất các sự kiện bảo mật hoặc bằng chứng sự cố quan trọng; chi phí thực phụ thuộc tier, retention, hợp đồng và giá hiện hành.

### Câu hỏi tự kiểm tra

1. Arc-enabled Kubernetes khác AKS ở vị trí control plane và trách nhiệm upgrade thế nào?
2. Azure connected cluster resource có chứa toàn bộ Pod và PVC của cluster nguồn không?
3. Vì sao phải kiểm tra cả `kubectl context` lẫn subscription trước khi chạy `az connectedk8s connect`?
4. Azure RBAC Reader trên resource Arc có cho quyền xóa Kubernetes Deployment không?
5. Flux và Azure Policy giải quyết hai vấn đề gì khác nhau? Khi nào policy Deny có thể làm GitOps reconcile lỗi?
6. `prune=true` trong một cấu hình GitOps có thể gây hậu quả gì và cần kiểm soát thế nào?
7. Vì sao Arc `Disconnected` chưa chắc đồng nghĩa API ở site bị gián đoạn?
8. Những metric nào cần có ngoài trạng thái Arc agent để đánh giá cluster hybrid thực sự khỏe?
9. Bật Azure Monitor cho cluster on-prem có những chi phí nào ngoài việc vận hành node?
10. Sau một đợt mất WAN, cần đối soát gì giữa GitOps revision, policy, telemetry và dữ liệu ứng dụng?

**Điểm cần ghi nhớ:** Azure Arc-enabled Kubernetes đưa các cluster hybrid vào **lớp quản trị Azure**, không đưa control plane hoặc workload về Azure. Giá trị đến từ kết hợp **inventory và Azure RBAC**, **GitOps/Flux**, **policy, security và observability** với một quy trình vận hành Kubernetes tại nguồn có trách nhiệm rõ ràng. Thiết kế tốt phải chịu được mất kết nối quản trị, giới hạn quyền, kiểm soát thay đổi và đo sức khỏe **theo trải nghiệm của ứng dụng**, không chỉ trạng thái Connected.
