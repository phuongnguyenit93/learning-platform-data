# Thu thập log và metric bằng Container Insights

Trong module **CLOUD_PROVIDERS_AZURE**, người học khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Mục tiêu là triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Ở chương **Vận hành AKS**, bài học này hướng dẫn thiết kế và sử dụng **Container Insights** cùng hệ sinh thái **Azure Monitor** để quan sát workload Kubernetes: từ log ứng dụng và trạng thái pod đến metric CPU, bộ nhớ, cảnh báo và điều tra sự cố.

Giả sử hệ thống đặt hàng chạy trên **Azure Kubernetes Service (AKS)** có ba Deployment: `orders-web`, `orders-api` và `payment-worker`. Lúc 14:05, khách hàng gặp HTTP 500. Trong Kubernetes, `orders-api` vẫn có ba replicas ở trạng thái `Running`. Nếu chỉ nhìn trạng thái pod, đội vận hành dễ kết luận mọi thứ bình thường. Để xác định nguyên nhân, cần ghép nhiều loại tín hiệu: **application logs** ghi lỗi, **Kubernetes inventory/events** mô tả thay đổi của pod, **metrics** chỉ ra CPU/memory pressure và **tracing** nếu đã được instrument. Container Insights giúp thu thập một phần những tín hiệu đó theo ngữ cảnh cluster, còn các dịch vụ quan sát khác của Azure bổ sung những tín hiệu ứng dụng chuyên sâu.

Sau bài học, bạn có thể:

- Phân biệt **log, metric, Kubernetes events, inventory và distributed traces** trong hoạt động AKS.
- Giải thích đường thu thập **Azure Monitor Agent (AMA) → Data Collection Rule (DCR) → Log Analytics workspace** của Container Insights.
- Phân biệt **Container Insights** với **Azure Monitor managed service for Prometheus**, Azure Monitor Metrics, Application Insights và diagnostic logs của AKS control plane.
- Bật và xác minh Container Insights bằng Portal/Azure CLI, với các điều kiện về workspace, quyền và mạng.
- Viết các truy vấn **KQL** để tìm lỗi trong `ContainerLogV2`, xác định pod gặp vấn đề và khảo sát metrics/inventory.
- Thiết kế dashboard, cảnh báo, quy trình điều tra và cách giảm chi phí ingestion/retention.
- Kiểm tra bảo mật của telemetry, tránh ghi secrets hoặc dữ liệu cá nhân vào log.

## 1. Vì sao giám sát AKS phải nhìn nhiều lớp?

AKS là nền tảng Kubernetes được Azure quản lý, nhưng ứng dụng vẫn chạy trên node, pod và container với vòng đời độc lập. Một lỗi 500 có thể bắt nguồn từ code, secret hết hạn, timeout tới database, DNS, node thiếu bộ nhớ hoặc lỗi mạng. Không có **một** metric đơn lẻ nào đủ chứng minh tất cả các nguyên nhân.

| Lớp | Câu hỏi vận hành | Nguồn tín hiệu thường dùng |
|---|---|---|
| **Ứng dụng** | API trả 500 do lỗi nào? | Structured logs, exceptions, Application Insights/traces |
| **Container** | Container có crash/restart hoặc ghi lỗi stderr? | Container logs, pod/container inventory, restart metrics |
| **Pod/Deployment** | Replica có sẵn sàng? Image pull có lỗi? | `kubectl`, Kubernetes events, inventory, workload metrics |
| **Node** | CPU/RAM/disk/network có áp lực không? | Node metrics, Container Insights performance, managed Prometheus |
| **Kubernetes control plane** | API Server, scheduler hoặc autoscaler có vấn đề? | AKS resource/diagnostic logs và các tín hiệu được dịch vụ hỗ trợ |
| **Dịch vụ Azure phụ thuộc** | Database/Storage/Key Vault có chậm hoặc từ chối truy cập? | Resource metrics, diagnostic logs, distributed tracing |
| **Toàn hệ thống** | Người dùng có gặp lỗi trong SLO? | Request rate, error rate, latency, availability tests |

### 1.1. Log là gì?

**Log** là bản ghi sự kiện theo thời điểm, có thể mô tả chi tiết một request hoặc lỗi:

```json
{
  "timestamp": "2026-11-20T07:05:21Z",
  "level": "ERROR",
  "service": "orders-api",
  "message": "Payment provider timed out",
  "traceId": "d61c2e9f08f04bdc",
  "durationMs": 3000,
  "errorType": "UpstreamTimeout"
}
```

Đây là dữ liệu giả lập, không phải log đã thu được từ một cluster. Log giúp truy ngược sự kiện nhưng nếu mỗi request đều ghi hàng chục dòng, khối lượng ingestion và chi phí lưu trữ có thể tăng nhanh.

### 1.2. Metric là gì?

**Metric** là giá trị đo theo thời gian, ví dụ tỷ lệ CPU, số lần container restart hoặc số request/giây. Metric phù hợp biểu đồ xu hướng và alert vì dữ liệu thường có kích thước gọn hơn chi tiết log:

```text
Thời gian (UTC)      Pod                   CPU sử dụng
14:00                orders-api-abc        0,45 core
14:05                orders-api-abc        0,91 core
14:10                orders-api-abc        0,58 core
```

Các số trên mang tính minh họa. Cần phân biệt đơn vị **CPU cores**, **millicores**, **nanocores** và **CPU percentage**; so sánh sai đơn vị dễ dẫn đến kết luận sai về mức sử dụng.

### 1.3. Kubernetes events và inventory

**Event** cho biết những chuyển biến cụ thể như `FailedScheduling`, `BackOff` hoặc `Unhealthy`. **Inventory** phản ánh pod, node, container, namespace và trạng thái mà agent quan sát được. Các thông tin này giúp đặt log vào đúng ngữ cảnh: một lỗi có xảy ra ngay sau khi pod bị thay thế hoặc node chuyển trạng thái không?

### 1.4. Trace không đồng nghĩa với container log

**Distributed trace** theo dõi đường đi của một request qua các dịch vụ khác nhau và thường có trace/span IDs. Traces cần instrumentation (ví dụ OpenTelemetry hoặc Azure Monitor Application Insights phù hợp), không tự xuất hiện đầy đủ chỉ vì đã bật Container Insights. Nên dùng log có `traceId` để liên kết tới trace, thay vì mong KQL trên container stdout tự tạo một cây span chi tiết.

## 2. Container Insights nằm ở đâu trong Azure Monitor?

**Container Insights** là trải nghiệm giám sát container/Kubernetes trong Azure Monitor, cho phép quan sát thông tin workload, hiệu năng và logs của AKS theo cấu hình đã bật. Trên các triển khai hiện đại, dữ liệu logs/inventory/performance được thu thập bởi **Azure Monitor Agent (AMA)** và điều phối qua **Data Collection Rule (DCR)** để gửi đến **Log Analytics workspace** được chọn.

```text
AKS cluster
├── Nodes / kubelet / container runtime
│     └── stdout/stderr của containers
├── Kubernetes API
│     └── Pod, node, workload metadata và events theo cấu hình
└── Azure Monitor Agent (ama-logs)
       │
       │ Thu thập streams được chọn
       ▼
   Data Collection Rule (DCR)
       │
       │ Chọn nguồn/streams, phạm vi và đích; transformation khi hỗ trợ
       ▼
   Log Analytics workspace
       ├── ContainerLogV2
       ├── KubePodInventory / KubeNodeInventory / KubeEvents
       ├── Perf / InsightsMetrics (khi được thu thập)
       └── Các bảng khác theo cấu hình và phiên bản
             │
             ├── Azure Portal: Container Insights
             ├── KQL / Workbooks
             └── Log search alerts
```

Đây là mô hình logic. Thực tế, tên DaemonSet/Deployment của agent, DCR, schema và các bảng được ghi có thể khác theo loại triển khai, cấu hình thu thập và phiên bản dịch vụ. Một bảng không xuất hiện trong workspace **không tự chứng minh dữ liệu mất**: có thể nguồn đó chưa được bật, chưa có sự kiện hoặc dữ liệu đang đi tới một đích khác.

### 2.1. Vai trò của từng thành phần

| Thành phần | Vai trò | Điểm cần xác minh |
|---|---|---|
| **Azure Monitor Agent** | Thu thập dữ liệu container/Kubernetes theo cấu hình | Agent đang chạy và có mạng tới đích ingest |
| **Data Collection Rule** | Mô tả nguồn/stream và đích của dữ liệu thu thập | Gắn đúng AKS, chọn đúng stream/namespace/thiết lập |
| **Log Analytics workspace** | Lưu và truy vấn logs/inventory/metrics theo các bảng | Đúng subscription/tenant, quyền, retention và billing |
| **Container Insights** | Hiển thị dữ liệu, xem cluster/nodes/controllers/containers và logs | Đang xem đúng cluster, thời gian và workspace |
| **Azure Monitor alerts / Workbooks** | Cảnh báo và trực quan hóa dữ liệu được thu thập | Ngưỡng, scope, window và quyền xem dữ liệu phù hợp |

**Không nhầm một Log Analytics workspace với nơi chạy ứng dụng.** Đây là nơi lưu telemetry, không chứa container image hay dữ liệu nghiệp vụ của workload. Khi nhiều AKS clusters gửi về cùng workspace, luôn lọc theo **ClusterName/cluster identity** và namespace trong truy vấn hoặc dashboard để tránh trộn môi trường dev/prod.

### 2.2. DCR có ý nghĩa gì?

DCR mô tả loại dữ liệu nào được gửi tới đích nào và có thể hỗ trợ các lựa chọn lọc/chuyển đổi theo loại data source. Với Container Insights, lựa chọn thường liên quan:

- Thu thập container stdout/stderr qua **`ContainerLogV2`**.
- Thu thập inventory, Kubernetes events hoặc các loại metrics mà agent hỗ trợ.
- Chọn chế độ thu thập dữ liệu theo cấu hình được dịch vụ hỗ trợ, chẳng hạn giới hạn namespace hoặc luồng logs.
- Các quy tắc về ingestion-time transformations nếu stream/bảng và cách triển khai hỗ trợ.

**Không sửa DCR đang được AKS/Container Insights quản lý mà không hiểu lifecycle của add-on.** Một thay đổi thủ công có thể bị cơ chế quản lý ghi đè hoặc làm ngắt dữ liệu toàn cluster. Nên cấu hình qua API/Portal/IaC đúng mô hình Container Insights đang dùng, sau đó kiểm tra luồng dữ liệu thật.

## 3. Phân biệt bốn hệ thống quan sát dễ nhầm

Azure Monitor có nhiều đường dữ liệu. Chúng bổ trợ nhau nhưng không phải một nút bật chung cho mọi tín hiệu.

| Công cụ/tính năng | Dữ liệu trọng tâm | Nơi truy vấn thường gặp |
|---|---|---|
| **Container Insights** | Container stdout/stderr, Kubernetes inventory/events, các tín hiệu hiệu năng theo cấu hình | Azure Portal/Log Analytics **KQL** và trải nghiệm Container Insights |
| **Azure Monitor Metrics** | Các metric nền tảng/resource hoặc metric được thu thập theo tính năng | Metrics Explorer, metric alerts, API metrics |
| **Azure Monitor managed service for Prometheus** | Prometheus-format metrics được scrape theo cấu hình từ cluster/workload | **Azure Monitor workspace**, **PromQL**, Azure Managed Grafana hoặc dashboards được hỗ trợ |
| **Application Insights / OpenTelemetry** | Request/dependency traces, exceptions, telemetry ứng dụng | Application Insights, KQL ở workspace phù hợp, trải nghiệm APM |

Ví dụ: muốn đọc một dòng `NullPointerException` ghi vào stderr của pod thì bắt đầu ở **ContainerLogV2**. Muốn đo `container_cpu_usage_seconds_total` và tính rate bằng **PromQL**, cần đường thu thập **managed Prometheus** hoặc Prometheus stack tương thích được cấu hình; không mặc định mọi Prometheus series tự xuất hiện trong `ContainerLogV2`.

### 3.1. Log Analytics workspace và Azure Monitor workspace không giống nhau

- **Log Analytics workspace (LAW):** lưu dữ liệu log dạng bảng, truy vấn bằng **Kusto Query Language (KQL)**.
- **Azure Monitor workspace (AMW):** lưu Prometheus metrics cho **Azure Monitor managed service for Prometheus** theo mô hình được hỗ trợ, truy vấn bằng **PromQL**.

Hai workspace là **hai loại tài nguyên Azure khác nhau**. Một ứng dụng có thể dùng cả hai nếu muốn log Kubernetes chi tiết và metrics Prometheus. Không trỏ các lệnh truy vấn KQL sang Azure Monitor workspace rồi kỳ vọng nhận bảng `ContainerLogV2`.

### 3.2. Control-plane logs cần bật riêng

Container Insights quan sát nhiều tín hiệu từ pod/node và Kubernetes, nhưng **AKS resource/diagnostic logs của control plane** (ví dụ các category về API Server, audit hoặc scheduler khi được hỗ trợ) phải được cấu hình riêng qua **Azure Monitor diagnostic settings** của tài nguyên AKS. Không mặc định bật Container Insights đồng nghĩa mọi audit log Kubernetes sẽ được lưu đầy đủ.

Khi cần điều tra thao tác tạo/xóa resource Kubernetes, quyền quản trị cluster hoặc sự kiện control plane, hãy kiểm tra những diagnostic categories đang có, workspace đích, retention và quyền truy vấn tương ứng. Audit logs có thể chứa thông tin nhạy cảm; cần quản trị truy cập và chi phí cẩn thận.

## 4. Những bảng Log Analytics cần biết

Khi Container Insights được cấu hình và dữ liệu đến Log Analytics workspace, những bảng sau thường hữu ích:

| Bảng | Nội dung tiêu biểu | Tình huống |
|---|---|---|
| **`ContainerLogV2`** | Dòng log stdout/stderr của container, metadata pod/container và thời gian | Truy lỗi ứng dụng, lọc theo namespace/pod |
| **`KubePodInventory`** | Thông tin pod, container, trạng thái và metadata được thu thập | Kiểm tra pod nào tồn tại hoặc ở trạng thái lỗi |
| **`KubeNodeInventory`** | Inventory node và các trạng thái liên quan | Liên hệ lỗi pod với node |
| **`KubeEvents`** | Sự kiện Kubernetes mà agent thu thập | `FailedScheduling`, `BackOff`, `Unhealthy` và các sự kiện khác |
| **`Perf`** | Một số performance counters được thu thập | Khảo sát CPU, memory hoặc counter ở mức node/container |
| **`InsightsMetrics`** | Metrics do agent xuất dưới dạng records theo cấu hình | Phân tích xu hướng hiệu năng có sẵn |

Các tên bảng và trường có thể thay đổi theo pipeline, cấu hình DCR, phiên bản Container Insights và lựa chọn legacy/resource-specific. Nơi nào còn dữ liệu ở **`ContainerLog`** kiểu cũ, câu lệnh KQL phải được điều chỉnh; bài học ưu tiên **`ContainerLogV2`** cho log container mới.

**Những dữ liệu không tự được thu thập đầy đủ:**

- Log ứng dụng ghi riêng vào file nằm trong container thay vì stdout/stderr nếu chưa có cấu hình collector phù hợp.
- Toàn bộ request tracing và dependency spans của ứng dụng không được instrument.
- Mọi custom Prometheus metric nếu chưa bật scraper, cấu hình endpoint và rule.
- Tất cả AKS audit/control-plane categories nếu chưa bật diagnostic settings.
- Dữ liệu lịch sử trước thời điểm bật giám sát hoặc đã quá thời gian retention.

## 5. Thiết kế telemetry trước khi bật collector

Trước khi bật Container Insights trên một cluster production, cần xác định mục tiêu quan sát:

| Tình huống | Tín hiệu cần | Truy vấn/hiển thị |
|---|---|---|
| API trả 500 | Application error logs và request telemetry | KQL ContainerLogV2 + App Insights |
| Pod restart liên tục | Pod/container status, Kubernetes events | Inventory, events, restart metrics |
| Pod bị `OOMKilled` | Pod termination reason, memory usage và limit | `kubectl describe`, inventory/performance, metrics |
| Node thiếu CPU | Node CPU, scheduling latency, pending pods | Metrics/Prometheus + Kubernetes events |
| Deployment mới bị lỗi | Timeline của deployment, pod logs/events | `kubectl`, Container Insights/KQL |
| Không có log sau deploy | Collector health, stdout/stderr, DCR, ingestion | Agent/stream/workspace và log producer |
| Chi phí tăng | Ingestion theo bảng, số dòng/s, retention | Azure Monitor usage/cost và workspace billing |

Một thiết kế tốt có thể đặt các câu hỏi **có thể trả lời được bằng dữ liệu thu thập**, thay vì bật tất cả categories rồi chỉ nhìn dashboard. Mỗi log/metric nên có owner, mục đích, thời gian giữ và mức độ nhạy cảm.

### 5.1. Thẻ nhận diện cho nhiều môi trường

Tối thiểu, mỗi dashboard và query phải giúp phân biệt:

- AKS cluster và Azure subscription/resource group.
- Namespace, workload/Deployment và tên container.
- Pod/node và thời gian xảy ra sự cố.
- Môi trường `dev`, `test`, `prod` thông qua resource mapping/tags hoặc metadata tương đương.
- Phiên bản ứng dụng/revision hoặc deployment timestamp nếu đã đưa vào log/telemetry.

Pod name thường có hậu tố thay đổi sau rollout. Nếu muốn dashboard tồn tại lâu, nên lọc theo **namespace, Deployment/workload hoặc label** khi dữ liệu hỗ trợ, không chỉ ghim đúng một tên pod đã bị thay thế.

## 6. Bật Container Insights cho AKS

Phần thực hành sử dụng **Azure CLI trong Bash/Azure Cloud Shell**, không chạy trên production khi chưa xác định cấu hình giám sát hiện có. Một AKS cluster có thể đã bật Container Insights và liên kết với workspace riêng của đội nền tảng. **Không tự thay workspace/DCR chỉ để chạy lab**, vì có thể khiến dashboard và alert đang dùng mất dữ liệu.

### 6.1. Các điều kiện cần chuẩn bị

1. AKS cluster đang hoạt động, user có quyền đọc cấu hình cluster và quyền phù hợp để bật add-on.
2. Log Analytics workspace trong tenant/subscription hoặc mô hình được Azure hỗ trợ, với quyền liên kết/ghi dữ liệu phù hợp.
3. Cluster/node có **outbound DNS, HTTPS và route** tới những endpoint Azure Monitor cần thiết theo thiết kế mạng; private endpoint hoặc Azure Monitor Private Link Scope có các điều kiện riêng.
4. Region, tính năng, chính sách tổ chức và phiên bản AKS/agent hỗ trợ luồng thu thập đã chọn.
5. Nhóm vận hành đã thống nhất phạm vi logs/metrics, retention, nơi lưu dữ liệu, chi phí và quyền truy vấn.
6. Có quyền Kubernetes cần thiết để đọc trạng thái agent, pod và namespaces, nếu dự định kiểm tra bằng `kubectl`.

Không nên cấp `Owner` ở subscription cho mọi operator chỉ để xem logs. Phân biệt quyền **bật add-on/quản trị resource**, quyền **truy vấn workspace** và quyền **đọc Kubernetes API**.

### 6.2. Kiểm tra cluster và subscription

```bash
az login
az account show --output table
az account set --subscription "<subscription-id>"

AKS_RG="rg-aks-operations-dev"
AKS_NAME="aks-orders-dev"
MON_RG="rg-monitoring-dev"
LOCATION="southeastasia"
LAW="law-aks-orders-dev"

az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "{name:name,id:id,location:location,monitoring:addonProfiles.omsagent}" \
  --output json
```

`addonProfiles.omsagent` là tên field **được giữ vì lịch sử tương thích** trong một số API/CLI của AKS, không có nghĩa mọi triển khai hiện tại dùng agent cũ thay vì **Azure Monitor Agent**. Muốn biết đường thu thập thực tế, hãy kiểm tra add-on, DCR và các agent resources đang chạy.

### 6.3. Tạo hoặc chọn Log Analytics workspace

Trong môi trường lab riêng, có thể tạo workspace:

```bash
az monitor log-analytics workspace create \
  --resource-group "$MON_RG" \
  --workspace-name "$LAW" \
  --location "$LOCATION"

LAW_ID=$(az monitor log-analytics workspace show \
  --resource-group "$MON_RG" \
  --workspace-name "$LAW" \
  --query id --output tsv)

az monitor log-analytics workspace show \
  --resource-group "$MON_RG" \
  --workspace-name "$LAW" \
  --query "{name:name,id:id,location:location,retentionInDays:retentionInDays}" \
  --output json
```

Ví dụ giả định `MON_RG` đã tồn tại. Nếu tổ chức có workspace tập trung và đã phân quyền đúng, hãy sử dụng **Resource ID workspace được quản trị phê duyệt** thay vì tự tạo workspace mới.

Retention và pricing plan có thể có các mức/điều kiện khác nhau theo Log Analytics và loại bảng. Trước khi thu thập log production, xem xét policy lưu giữ và dữ liệu nhạy cảm thay vì dùng mặc định mà không đánh giá.

### 6.4. Bật add-on giám sát

Với AKS và phiên bản Azure CLI hỗ trợ, thao tác bật thu thập Container Insights logs dùng dạng:

```bash
az aks enable-addons \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --addons monitoring \
  --workspace-resource-id "$LAW_ID"
```

Lệnh minh họa **bật Container Insights** theo luồng add-on; nó không tự bảo đảm đã bật **managed Prometheus**. Trong những phiên bản API/CLI mới, cách xác thực agent bằng managed identity hoặc tuỳ chọn data collection/configuration có thể có tham số bổ sung; hãy dùng Portal hoặc syntax được cluster/CLI thực tế hỗ trợ. Trước khi chạy, kiểm tra add-on có đang bật và gửi sang workspace khác hay không để tránh thay đổi ngoài ý muốn.

Kiểm tra lại:

```bash
az aks show \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME" \
  --query "addonProfiles.omsagent" \
  --output json
```

Add-on báo `enabled` chưa chứng minh dữ liệu đã tới workspace. Kiểm tra tiếp **agent health, DCR association và KQL dữ liệu thật** ở bước sau.

### 6.5. Bật bằng Azure Portal

Với Azure Portal, có thể vào tài nguyên **AKS → Insights** hoặc màn hình **Monitoring/Insights** tương đương, chọn cấu hình Container Insights, Log Analytics workspace và những lựa chọn data collection/cost preset được giao diện hỗ trợ. Sau khi review resource được tạo/thay đổi, áp dụng và kiểm tra DCR, danh mục thu thập và workspace.

**Quan trọng:** cùng một nút “Monitoring” có thể đưa ra các tùy chọn **Container Insights logs**, **Prometheus metrics** và **Grafana**. Hãy ghi nhận rõ những thành phần đã bật; đừng báo cáo “đã bật mọi metrics/traces” chỉ vì Insights đã hiện dữ liệu container.

## 7. Xác minh pipeline thu thập từ node đến workspace

Quá trình thu thập thường có độ trễ giữa lúc container ghi log và lúc dòng log xuất hiện trong Log Analytics. Khi vừa bật, cần cho hệ thống hoàn tất provisioning, agent startup và ingestion trước khi kết luận mất dữ liệu.

### 7.1. Kiểm tra node/pod/agent bằng kubectl

```bash
az aks get-credentials \
  --resource-group "$AKS_RG" \
  --name "$AKS_NAME"

kubectl config current-context
kubectl get nodes -o wide
kubectl get pods --all-namespaces

# Agent name phụ thuộc phiên bản/cấu hình; không nên giả định cố định.
kubectl get daemonsets -n kube-system
kubectl get deployments -n kube-system
```

Ở những cấu hình AMA Container Insights, có thể gặp resource/pod mang tên gần với **`ama-logs`**. Tên `omsagent` có thể xuất hiện trong các tài liệu/cluster cũ. Chỉ xem đúng đối tượng thực tế do `kubectl get` trả về; tránh copy tên pod mẫu không tồn tại.

Nếu agent pod ở `CrashLoopBackOff`, pending hoặc không chạy trên các node cần thiết, cần xem `kubectl describe`, Kubernetes events, container logs của agent và những ràng buộc node/taint/network theo quy trình. **Không xóa agent DaemonSet hoặc DCR để thử may rủi**.

### 7.2. Tạo log từ ứng dụng thử nghiệm

Trong môi trường lab có Deployment `orders-api` đã hoạt động:

```bash
kubectl logs -n orders deployment/orders-api \
  --all-containers=true \
  --since=15m \
  --tail=100
```

Lệnh `kubectl logs` giúp xác minh **log tồn tại trong Kubernetes/container runtime**. Nó không cần Log Analytics và không chứng minh Container Insights đã ingest dòng log đó.

Nếu `kubectl logs` không có dữ liệu, hãy xác minh app ghi vào **stdout/stderr**, có log trong khoảng thời gian chọn và pod đã khởi động thành công. Nếu `kubectl logs` có dữ liệu nhưng Log Analytics không thấy, tiếp tục kiểm tra **agent → DCR → workspace**.

### 7.3. Kiểm tra workspace bằng KQL

Vào Log Analytics workspace đã chọn → **Logs**, chọn khoảng thời gian khoảng 1 giờ gần nhất, chạy:

```kusto
ContainerLogV2
| where TimeGenerated > ago(1h)
| summarize LogLines=count() by PodNamespace
| order by LogLines desc
```

Nếu có dữ liệu, truy vấn trả về số dòng theo namespace. Nếu không có, chưa đủ kết luận agent hỏng: có thể không có container logs trong khoảng thời gian, DCR không thu stream, bảng chưa tạo hoặc dữ liệu đang tới workspace khác.

### 7.4. Kiểm tra Data Collection Rule và destination

Trong Azure Portal, xem cấu hình **Data Collection Rules**/associations liên quan đến AKS, xác nhận:

- DCR có kết nối tới đúng AKS resource và trạng thái hợp lệ.
- Streams thu thập có bao gồm loại dữ liệu đang mong đợi.
- Log Analytics workspace đích là workspace bạn đang query.
- Namespace, log level, collection preset hoặc transformation có vô tình loại dữ liệu không.
- Agent có permission và kết nối mạng để gửi dữ liệu.

Một số hệ thống áp dụng DCR transformation hoặc log filtering ở thời điểm ingestion. Dữ liệu đã bị lọc trước khi gửi **không thể khôi phục chỉ bằng thay KQL**; cần điều chỉnh cấu hình rồi ghi dữ liệu kiểm thử mới.

## 8. Ghi log từ ứng dụng để Container Insights thu thập hiệu quả

Container Insights thường thu thập **stdout/stderr của container** qua agent theo cấu hình. Ứng dụng nên sử dụng logging framework và ghi mỗi sự kiện có cấu trúc, mức độ và thông tin ngữ cảnh phù hợp. Không cần bắt đầu bằng việc ghi file log riêng trong filesystem của pod.

### 8.1. Log có cấu trúc

Ví dụ tốt hơn một dòng `Payment failed` khó tìm:

```json
{
  "timestamp": "2026-11-20T07:05:21Z",
  "level": "ERROR",
  "service": "orders-api",
  "operation": "charge",
  "traceId": "d61c2e9f08f04bdc",
  "durationMs": 3000,
  "status": "UPSTREAM_TIMEOUT",
  "message": "Payment provider did not respond within the deadline"
}
```

Ở ví dụ trên, **không ghi** thẻ thanh toán, secret, API token hoặc toàn bộ payload khách hàng. Khi cần liên hệ giao dịch, có thể dùng **ID nội bộ được thiết kế để không tiết lộ dữ liệu nhạy cảm**, với chính sách truy cập vào logs phù hợp.

### 8.2. Mức log và chiến lược sampling

| Level | Mục đích | Rủi ro nếu dùng sai |
|---|---|---|
| `DEBUG` | Điều tra logic chi tiết, thường bật có thời hạn | Ingestion cao, dễ lộ dữ liệu nội bộ |
| `INFO` | Lifecycle và các sự kiện nghiệp vụ có chọn lọc | Có thể rất ồn nếu ghi từng request không giới hạn |
| `WARN` | Tình huống bất thường nhưng chưa nhất thiết thất bại | Alert giả nếu log warning liên tục không phân loại |
| `ERROR` | Thao tác thất bại cần điều tra hoặc hành động | Bỏ sót lỗi nếu exception bị nuốt hoặc không log |

Với dịch vụ lưu lượng lớn, không cần log `INFO` cho mọi bước bên trong mỗi request. Dùng **sampling ở instrumentation phù hợp**, log theo sự kiện quan trọng và metrics cho thống kê tổng hợp. Trước khi giảm log, bảo đảm vẫn còn đủ bằng chứng để điều tra lỗi nghiêm trọng.

### 8.3. Ví dụ Java logging

Ứng dụng Spring Boot/Java có thể dùng SLF4J và cấu hình logging framework để ghi ra console:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderProcessor {
    private static final Logger log =
            LoggerFactory.getLogger(OrderProcessor.class);

    public void process(String operationId) {
        log.info("Order processing started: operationId={}", operationId);
        try {
            // Xử lý nghiệp vụ và gọi backend theo chính sách ứng dụng.
            log.info("Order processing completed: operationId={}", operationId);
        } catch (RuntimeException ex) {
            log.error("Order processing failed: operationId={}", operationId, ex);
            throw ex;
        }
    }
}
```

Đây là ví dụ cách sử dụng SLF4J, cần có dependency/runtime logging implementation tương thích. Muốn JSON có cấu trúc thay vì text đơn thuần, cấu hình appender/encoder của logging framework phù hợp. Đừng biến `operationId` thành một ID có thông tin định danh cá nhân chưa được cho phép; và không để exception message vô tình chứa secrets.

### 8.4. Thời gian và trace correlation

- Ưu tiên **UTC** trong log và dashboard để đối chiếu nhiều region.
- Ghi `traceId` hoặc correlation ID phù hợp để nối log container với traces trong Application Insights/OpenTelemetry.
- Ghi deployment/build version ở app metadata khi hỗ trợ, giúp phân biệt lỗi trước/sau rollout.
- Với pod bị recreate, dùng namespace/workload/trace ID thay vì dựa độc nhất vào pod name.
- Kiểm tra thời gian của node và cơ chế timestamp; nếu đồng hồ lệch, timeline có thể gây hiểu lầm.

## 9. Truy vấn KQL: tìm log của namespace và pod

Các ví dụ chạy trong **Log Analytics workspace** có dữ liệu `ContainerLogV2`. Hãy điều chỉnh tên namespace, pod và khoảng thời gian theo hệ thống thật. Để tránh nhầm nhiều cluster chung một workspace, nên bổ sung điều kiện `ClusterName` hoặc cluster identity khi đã xác nhận tên cột và giá trị thực tế.

### 9.1. Xem 100 dòng gần nhất của API

```kusto
ContainerLogV2
| where TimeGenerated > ago(1h)
| where PodNamespace == "orders"
| where PodName startswith "orders-api"
| project TimeGenerated, PodNamespace, PodName,
          ContainerName, LogLevel, Message=tostring(LogMessage)
| order by TimeGenerated desc
| take 100
```

KQL trên chọn pod có tên bắt đầu bằng `orders-api`; đây là ví dụ phù hợp với tên pod của Deployment phổ biến nhưng không phải chuẩn bắt buộc của mọi workload. Đọc log level theo thực tế dữ liệu: `LogLevel` có thể không được agent tự suy ra chính xác từ một dòng plain-text log.

### 9.2. Tìm lỗi theo nội dung

```kusto
ContainerLogV2
| where TimeGenerated > ago(30m)
| where PodNamespace == "orders"
| extend Message=tostring(LogMessage)
| where Message has_any ("ERROR", "timeout", "exception")
| project TimeGenerated, PodName, ContainerName, Message
| order by TimeGenerated desc
```

Tìm từ khóa là cách điều tra sơ bộ. `ERROR` có thể xuất hiện trong một dòng mô tả không phải lỗi thật; một lỗi JSON lại có `level` ở field khác. Với logs có cấu trúc, có thể `parse_json` sau khi hiểu định dạng được collector giữ lại.

### 9.3. Đếm dòng lỗi theo chu kỳ 5 phút

```kusto
ContainerLogV2
| where TimeGenerated > ago(2h)
| where PodNamespace == "orders"
| extend Message=tostring(LogMessage)
| where Message has_any ("ERROR", "timeout", "exception")
| summarize ErrorLines=count() by bin(TimeGenerated, 5m), PodNamespace
| order by TimeGenerated asc
```

**ErrorLines không bằng số HTTP 500**: một request lỗi có thể ghi nhiều dòng hoặc không ghi dòng nào; thêm nữa có thể có lỗi background job không liên quan HTTP. Để tính **error rate của API**, nên dùng request telemetry/HTTP metrics được instrument chính xác, rồi dùng container logs để phân tích nguyên nhân.

### 9.4. Khám phá schema thực tế khi query lỗi

Nếu workspace báo không có cột hoặc bảng:

```kusto
ContainerLogV2
| where TimeGenerated > ago(1h)
| take 5
```

Kiểm tra những cột hiện có, dataset/time range và quyền truy vấn. Nếu `ContainerLogV2` chưa tồn tại, kiểm tra DCR stream, ingestion và xem có sử dụng đường/bảng log cũ hay không. Không “sửa” bằng cách hard-code một tên cột tưởng tượng.

## 10. KQL: khảo sát pod, node, events và performance counters

Một dòng lỗi log nói "process terminated" chưa đủ xác định pod bị kill vì hết memory, bị lệnh rollout thay thế hay ứng dụng tự thoát. **Kubernetes inventory, events và metrics** giúp đối chiếu. Các truy vấn dưới đây giả định những bảng tương ứng đã được thu thập.

### 10.1. Xem trạng thái pod gần nhất

```kusto
KubePodInventory
| where TimeGenerated > ago(30m)
| summarize arg_max(TimeGenerated, PodStatus)
    by ClusterName, Namespace, Name
| summarize Pods=count()
    by ClusterName, Namespace, PodStatus
| order by Pods desc
```

`arg_max` chọn **bản ghi mới nhất trong khoảng truy vấn** cho mỗi cặp cluster/namespace/name; nó không thay thế kiểm tra realtime bằng `kubectl get pods`. Inventory ingestion có thể trễ hoặc chứa các pod đã bị xóa sau lần quan sát cuối cùng. Khi nghi ngờ, đối chiếu với Kubernetes API.

Nếu cần xem từng pod:

```kusto
KubePodInventory
| where TimeGenerated > ago(30m)
| where Namespace == "orders"
| summarize arg_max(TimeGenerated, PodStatus)
    by ClusterName, Namespace, Name
| project ClusterName, Namespace, Name, PodStatus, TimeGenerated
| order by TimeGenerated desc
```

### 10.2. Khảo sát Kubernetes events

```kusto
KubeEvents
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc
| take 50
```

Truy vấn sơ bộ giữ toàn bộ các cột để bạn kiểm tra schema có sẵn. Với workspace hỗ trợ các cột như `Reason`, `Namespace` hoặc `Message`, có thể lọc theo các giá trị liên quan đến `FailedScheduling`, `BackOff` hoặc `Unhealthy`.

So sánh với Kubernetes trực tiếp:

```bash
kubectl get events -n orders --sort-by=.metadata.creationTimestamp
kubectl describe pod <actual-pod-name> -n orders
```

Kubernetes events không được lưu vô hạn trong cluster; chúng có chính sách/vòng đời riêng. Log Analytics chỉ chứa events thực sự được collector thu nhận khi stream tương ứng bật và còn trong retention. Đừng kỳ vọng một event của tuần trước luôn có sẵn trong `kubectl get events`.

### 10.3. Khám phá performance counters

Trước khi đặt tên counter, kiểm tra những metrics đã có trong bảng `Perf`:

```kusto
Perf
| where TimeGenerated > ago(1h)
| summarize Samples=count() by ObjectName, CounterName
| top 30 by Samples desc
```

Ví dụ các triển khai Container Insights có thể xuất những counter CPU theo đơn vị nanocores. **Chỉ dùng truy vấn cụ thể sau khi đã xác nhận ObjectName/CounterName thực sự tồn tại và hiểu đơn vị**. Một mẫu khám phá giá trị của counter:

```kusto
Perf
| where TimeGenerated > ago(1h)
| where ObjectName == "K8SContainer"
| where CounterName == "cpuUsageNanoCores"
| extend Cores=CounterValue / 1000000000.0
| summarize AvgCores=avg(Cores)
    by bin(TimeGenerated, 5m), InstanceName
| order by TimeGenerated asc
```

`cpuUsageNanoCores` và `K8SContainer` là những tên counter thường gặp, **không phải cam kết về schema của mọi workspace**. Nếu không có dữ liệu, quay về truy vấn khám phá counters, kiểm tra cấu hình thu thập và dùng trải nghiệm performance tương ứng. Khi tính trung bình, cũng cần xem liệu các samples có đều nhau theo thời gian không.

### 10.4. Khảo sát bảng InsightsMetrics

```kusto
InsightsMetrics
| where TimeGenerated > ago(1h)
| summarize Samples=count() by Namespace, Name
| top 30 by Samples desc
```

`InsightsMetrics` có thể chứa dữ liệu hiệu năng theo namespace/name; danh sách metric thực tế khác nhau tùy collector. Trước khi tạo dashboard KPI, xác định **đơn vị**, nhãn (dimensions), tần suất sample và liệu giá trị là gauge hay counter.

### 10.5. Kết nối thời điểm giữa log và restart

Giả sử log `orders-api` bùng lỗi vào lúc 14:05, pod restart khoảng 14:06. Một trình tự điều tra:

1. Dùng `ContainerLogV2` lọc `orders-api` ở khoảng 14:00–14:10 UTC.
2. Dùng `KubePodInventory` hoặc events tìm container/pod có trạng thái thay đổi.
3. Dùng `kubectl describe pod` xem `Last State`, `Reason`, `Exit Code` và liveness/readiness probe nếu pod còn tồn tại.
4. Dùng perf metrics hoặc managed Prometheus xem memory/CPU trước thời điểm restart.
5. Đối chiếu thời gian deploy và thay cấu hình; không mặc định restart là nguyên nhân, có thể nó là **hậu quả** của lỗi ứng dụng.

Một pod có trạng thái `Running` tại 14:10 không chứng minh nó chưa từng crash trong khoảng 14:00–14:10. Cần nhìn **restart count/history** và các sự kiện có thời điểm.

## 11. Metrics: hiểu phạm vi Container Insights và managed Prometheus

### 11.1. Metrics từ Container Insights

Container Insights có thể hiển thị hiệu năng ở cấp cluster/node/controller/container thông qua dữ liệu thu thập. Điều cần nhớ là các số liệu CPU/memory có thể có:

- **Giá trị sử dụng tuyệt đối:** CPU cores, nanocores, memory bytes.
- **Giá trị tương đối:** CPU/memory usage so với capacity, allocatable, request hoặc limit.
- **Đơn vị thời gian:** instantaneous sample, trung bình trong cửa sổ hoặc rate.

Ví dụ một container dùng `0,5 CPU core` và được cấp request `0,25 core` có nghĩa tải sử dụng cao hơn request; chưa thể kết luận bị CPU throttling nếu chưa kiểm tra limit và metric throttling. Một container dùng `450 MiB` trên memory limit `512 MiB` cũng chưa chắc đã `OOMKilled`; phải có dấu vết tương ứng trong trạng thái container/events.

### 11.2. Azure Monitor managed service for Prometheus

Với nhu cầu Prometheus-format metrics, Azure có **managed service for Prometheus** theo khả năng AKS/region, thu dữ liệu vào **Azure Monitor workspace**. Trải nghiệm hiển thị có thể kết hợp **Azure Managed Grafana** hoặc dashboard tương thích.

Kiến trúc khái niệm:

```text
AKS nodes / pods / kube-state-metrics / Prometheus exporters
       |
       | Prometheus scrape targets + scrape configuration
       v
Azure Monitor metrics collection agent
       |
       v
Azure Monitor workspace (Prometheus)
       |
       +-- PromQL
       +-- Grafana dashboard
       +-- Prometheus rules / alerts khi cấu hình và hỗ trợ
```

Đường này **khác** Log Analytics workspace và `ContainerLogV2`. Bật metrics scraping không có nghĩa stdout/stderr đã được gửi sang Log Analytics; và bật Container Insights không có nghĩa mọi custom exporter đã được scrape.

### 11.3. Ví dụ PromQL

Khi metric container CPU của runtime thực sự có mặt trong Azure Monitor workspace:

```promql
sum by (namespace) (
  rate(container_cpu_usage_seconds_total{container!="", container!="POD"}[5m])
)
```

Vì `container_cpu_usage_seconds_total` là **counter**, `rate(...[5m])` tính tốc độ CPU-seconds/second trong cửa sổ năm phút, thường được diễn giải theo đơn vị CPU cores khi metric phù hợp. Các label như `namespace`, `pod`, `container` phụ thuộc cấu hình scraping và phiên bản exporter.

Một ví dụ truy vấn số pod ở trạng thái `Pending` nếu metric từ kube-state-metrics có sẵn:

```promql
sum by (namespace) (
  kube_pod_status_phase{phase="Pending"}
)
```

Đây là hai **PromQL**, không chạy trực tiếp trong Log Analytics KQL editor. Nếu không có metric, kiểm tra workspace, scrape targets, default targets, custom scrape configuration và labels thay vì giả định query sai cú pháp.

### 11.4. Cách lựa chọn đường metric

| Câu hỏi | Hướng tiếp cận |
|---|---|
| Muốn xem nhanh CPU/memory, trạng thái container cùng logs trong AKS Insights | Container Insights với streams/config đúng |
| Muốn query Prometheus metrics bằng PromQL hoặc dùng Grafana dashboards | Managed Prometheus + Azure Monitor workspace |
| Muốn metric HTTP request/error của Java API | Instrument OpenTelemetry/Prometheus hoặc Application Insights theo chuẩn đội vận hành |
| Muốn metrics Azure resource ngoài Kubernetes | Azure Monitor Metrics/diagnostics của resource tương ứng |
| Muốn truy vấn cả log Kubernetes và metric Prometheus trong một incident | Kết hợp KQL và PromQL theo timeline, không kỳ vọng bảng dữ liệu giống nhau |

Khi xây observability mới, có thể chọn **Container Insights cho logs/inventory** và **managed Prometheus cho metrics**. Không bật hai bộ collector trùng cùng một dữ liệu chỉ để tăng số biểu đồ; hãy đánh giá duplicate ingestion, chi phí và khác biệt ngữ nghĩa.

## 12. Dashboard, workbook và cảnh báo có ý nghĩa vận hành

### 12.1. Một dashboard AKS tối thiểu

Một bảng điều khiển có giá trị cho đội trực vận hành có thể chứa:

| Nhóm | Chỉ số hiển thị | Lý do |
|---|---|---|
| **Availability** | Ready/Desired replicas, pending pods, node NotReady | Phát hiện thiếu capacity hoặc lỗi scheduling |
| **Reliability** | Restart count, `OOMKilled`, probe failures | Phát hiện container không ổn định |
| **Performance** | CPU/memory usage, pressure, throttling nếu có | Dự báo overload |
| **Application** | Request rate, error rate, p95/p99 latency | Đo trải nghiệm người dùng |
| **Diagnostics** | Log ERROR theo namespace/workload, Kubernetes events | Điều tra nguyên nhân |
| **Change correlation** | Thời điểm deployment, config changes, autoscale | Tìm sự kiện dẫn tới bất thường |
| **Cost** | Ingestion, retention và cardinality metrics | Quản trị ngân sách quan sát |

Đừng đưa mọi namespace vào một biểu đồ duy nhất nếu các đội khác nhau cần xem ranh giới riêng. Nên cho phép lọc theo cluster, namespace, workload, environment và khoảng thời gian.

### 12.2. Log search alert từ ContainerLogV2

Một mẫu KQL để tạo **scheduled query alert** dựa trên số dòng lỗi trong 10 phút:

```kusto
ContainerLogV2
| where TimeGenerated > ago(10m)
| where PodNamespace == "orders"
| where PodName startswith "orders-api"
| extend Message=tostring(LogMessage)
| where Message has_any ("ERROR", "timeout", "exception")
| summarize ErrorLines=count()
```

Trong Azure Monitor, tạo **log search alert** với scope đúng Log Analytics workspace, thời gian đánh giá, ngưỡng, action group và severity theo chính sách. Ví dụ: cảnh báo nếu `ErrorLines` vượt ngưỡng được rút ra từ tải bình thường, không dùng một con số tùy ý cho tất cả ứng dụng.

**Không gọi đây là HTTP 5xx alert chính xác.** Vì log message có thể không phản ánh mọi request thất bại, cảnh báo SLO nên dùng **HTTP server request metrics hoặc application telemetry** đã được instrument.

### 12.3. Metric alert và Prometheus alert

Metric alert phù hợp các số liệu có ngữ nghĩa đo rõ, ví dụ CPU usage, node availability, pod restarts hoặc latency, tùy nguồn dữ liệu và hỗ trợ của Azure Monitor/managed Prometheus. Một cảnh báo phải xác định:

1. **Signal:** đo cái gì, đơn vị và nguồn nào?
2. **Scope:** AKS cluster/namespace/app nào?
3. **Condition:** vượt ngưỡng trong bao lâu hay so với baseline?
4. **Evaluation:** tần suất đánh giá, cửa sổ, điều kiện mất dữ liệu.
5. **Action:** gửi tới người trực on-call, incident system hoặc automation nào?
6. **Runbook:** bước xác minh và cách xử lý để giảm thời gian điều tra.

Với ứng dụng có nhiều replicas, không nên alert khi **một** container tăng CPU trong một sample rất ngắn, nếu không ảnh hưởng sức khỏe hệ thống. Cũng không nên chờ tới khi tất cả replicas chết mới cảnh báo. Đặt ngưỡng theo SLO, tải và đặc điểm workload.

### 12.4. Một runbook alert chuẩn

Ví dụ cảnh báo `orders-api ERROR lines surge`:

1. Xác định UTC timestamp, cluster, namespace và phạm vi alert.
2. Xem p95 latency và HTTP 5xx của ứng dụng.
3. Mở KQL `ContainerLogV2` với thời gian ±10 phút.
4. Kiểm tra restarts, pod events và node pressure.
5. Xem dependency traces hoặc diagnostic logs của database/payment API.
6. Đối chiếu deployment và thay đổi config vừa xảy ra.
7. Chọn hành động: rollback, scale, khắc phục backend hoặc xử lý secret/network.
8. Đánh dấu incident timeline và điều chỉnh alert nếu nó tạo nhiều cảnh báo giả.

Một alert không có người nhận, runbook hoặc hành động xử lý rõ ràng sẽ trở thành **nhiễu cảnh báo**, dù cú pháp KQL hoàn toàn chính xác.

## 13. Chẩn đoán khi không thấy log hoặc metric

Nếu không thấy log trong Container Insights, **đừng mặc định bật thêm mọi logging category hoặc mở toàn bộ outbound**. Một đường thu thập có nhiều mắt xích; cần xác định điểm đầu tiên bị lỗi.

### 13.1. Quy trình điều tra log bị thiếu

```text
Ứng dụng có tạo log?
       |
       +-- Không -> sửa logging/stdout/stderr của ứng dụng
       |
       v
kubectl logs có thấy log?
       |
       +-- Không -> kiểm tra pod/container, thời gian và log producer
       |
       v
Azure Monitor Agent có chạy?
       |
       +-- Không -> xem DaemonSet, node, agent logs/events
       |
       v
DCR có thu ContainerLogV2 và gửi đúng LAW?
       |
       +-- Không -> kiểm tra streams, filtering, association, destination
       |
       v
Agent có kết nối ingest endpoint?
       |
       +-- Không -> DNS, route, firewall, private link, identity/quyền
       |
       v
KQL có dùng đúng workspace, bảng, time range, cluster/namespace?
       |
       +-- Không -> sửa truy vấn và quyền đọc
       |
       v
Log đến -> kiểm tra độ trễ ingestion và chuẩn hóa dashboard
```

### 13.2. Triệu chứng và nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| `kubectl logs` trống | App ghi vào file, stdout không có log, nhầm container, hoặc khoảng thời gian không có sự kiện | Xem app config, đúng pod/container, `--previous` nếu container restart |
| `kubectl logs` có dữ liệu nhưng `ContainerLogV2` trống | Add-on/agent/DCR/workspace lỗi hoặc collector lọc logs | Kiểm tra add-on, agent, DCR stream, LAW destination |
| Chỉ thiếu logs của một namespace | Namespace filter, config collection hoặc namespace không phát log | Xem DCR và query không lọc nhầm |
| Chỉ có logs cũ | Collector ngừng, bị chặn mạng, query đang nhìn workspace sai | Thời điểm record mới nhất, agent health, network |
| `ContainerLogV2` không tồn tại | Chưa ingest stream, chưa bật, workspace khác hoặc dùng schema cũ | Khám phá bảng trong workspace, DCR, ingestion |
| Có log nhưng không thấy JSON fields riêng | JSON đang nằm dưới dạng text/dynamic trong `LogMessage` | Dùng `tostring`/`parse_json` phù hợp và kiểm tra schema |
| Không thấy Kubernetes events | Stream chưa thu, không có event trong window hoặc event hết thời gian lưu | `kubectl get events`, bảng `KubeEvents`, DCR |
| Metrics CPU thiếu nhưng logs có | Performance stream không bật hoặc nhầm managed Prometheus với LAW | DCR/AMA performance data, AMW/scrape configuration |
| PromQL trả no data | Managed Prometheus chưa bật, target chưa scrape hoặc labels không đúng | AMW, collector, scrape targets, metric discovery |
| Một vài node không có telemetry | Agent không chạy trên node, taint/OS/architecture/pressure hoặc network khác | DaemonSet scheduling, node events, agent logs |
| Log xuất hiện trễ | Ingestion latency, pipeline backlog, query window quá hẹp | `TimeGenerated`, ingestion time, workspace health |
| Không xem được Logs từ Portal | Người dùng thiếu quyền truy vấn workspace hoặc scope sai | Azure RBAC, workspace access mode, subscription/tenant |

Nếu cần đối chiếu **thời gian ingestion** với event time, KQL có thể dùng hàm `ingestion_time()` khi dữ liệu và bảng hỗ trợ:

```kusto
ContainerLogV2
| where TimeGenerated > ago(1h)
| extend IngestedAt=ingestion_time()
| where isnotnull(IngestedAt)
| extend LagSeconds=datetime_diff("second", IngestedAt, TimeGenerated)
| summarize AvgLagSeconds=avg(LagSeconds),
            P95LagSeconds=percentile(LagSeconds, 95)
    by bin(TimeGenerated, 5m)
| order by TimeGenerated asc
```

Đây là phép đo sơ bộ về **chênh lệch event/ingestion timestamps**; nếu `ingestion_time()` không sẵn có hoặc clocks sai, phải hiểu hạn chế trước khi coi kết quả là SLA ingestion của dịch vụ.

### 13.3. Phân biệt `OOMKilled` và restart do liveness probe

Một container có restart count tăng. Hai nguyên nhân có thể là:

- Container dùng vượt memory limit và bị hệ thống kết thúc với reason `OOMKilled`.
- Liveness probe thất bại liên tiếp, kubelet khởi động lại container.

Không thể phân biệt chỉ bằng `restart count`. Cần kiểm tra:

```bash
kubectl get pods -n orders -o wide
kubectl describe pod <actual-pod-name> -n orders

# Nếu container đã restart và logs trước đó còn được runtime giữ:
kubectl logs <actual-pod-name> \
  -n orders \
  --previous \
  --tail=100
```

Nếu logs trước đó đã bị xoay vòng hoặc pod bị xóa, Container Insights có thể cung cấp bản ghi lịch sử **nếu agent đã thu và retention còn hiệu lực**. Không dùng việc không có lịch sử để khẳng định container chưa từng restart.

### 13.4. Điều tra lỗi sau một rollout

Ví dụ `orders-api` triển khai bản `2.1.0` lúc 14:00 và lỗi từ 14:05:

1. Kiểm tra Pod/ReplicaSet/revision và Kubernetes events.
2. So sánh KQL logs trước/sau 14:00 cùng thời gian UTC.
3. Xem CPU/memory/restart/pending pods.
4. So sánh với request error rate và dependency duration.
5. Kiểm tra có thay secret, image, resource limit, readiness probe hoặc network policy không.
6. Nếu lỗi tập trung ở release mới, cân nhắc rollback theo runbook; không tự kết luận hạ tầng AKS lỗi.

## 14. Bảo mật dữ liệu quan sát và quyền truy cập

Telemetry có thể chứa thông tin nhạy cảm: hostname nội bộ, địa chỉ IP, user IDs, thông tin request, resource names, đôi khi cả credential nếu ứng dụng log sai. Một Log Analytics workspace tập trung của nhiều đội có thể trở thành **điểm tập trung dữ liệu cần bảo vệ**.

### 14.1. Bảo vệ từ nguồn

- Không log password, API keys, Entra access token, Kubernetes ServiceAccount JWT, connection strings hoặc private certificates.
- Không đưa request/response body chứa dữ liệu khách hàng vào stdout/stderr mặc định.
- Giới hạn các headers nhạy cảm như `Authorization`, `Cookie` và session IDs.
- Nếu cần correlation, dùng ID được thiết kế phù hợp với yêu cầu privacy và retention.
- Cấu hình mức log khác nhau giữa dev/prod; `DEBUG` phải có giới hạn thời gian và owner.
- Review thư viện logging, exception handling và HTTP middleware để tránh tự động ghi dữ liệu bí mật.

Ingestion-time transformation có thể loại một số fields theo hỗ trợ kỹ thuật, nhưng **không nên dùng làm biện pháp duy nhất chống rò rỉ secrets**. Một dòng token đã bị gửi tới collector/log buffer có thể vẫn đi qua các bề mặt khác trước khi được lọc. Chống rò rỉ ngay trong ứng dụng là ưu tiên.

### 14.2. Phân quyền xem và chỉnh telemetry

Nên tách:

| Chủ thể | Phạm vi quyền cần cân nhắc |
|---|---|
| **Platform team** | Quản trị add-on, DCR, agent configuration và networking |
| **Ứng dụng/SRE** | Truy vấn logs và dashboards của workload được giao |
| **Security/Compliance** | Audit dữ liệu và các thay đổi cấu hình theo chính sách |
| **CI/CD identity** | Thay đổi hạ tầng/collector được phê duyệt, không mặc nhiên có quyền đọc mọi log |
| **Người dùng nghiệp vụ** | Chỉ xem dashboard cấp cao nếu cần, không truy vấn raw logs tùy ý |

Azure RBAC của Log Analytics, workspace access control và các phương án phân tách dữ liệu phải được thiết kế theo khả năng thực tế của dịch vụ. **Một workspace chung không tự tạo ranh giới namespace-level** cho mọi bảng/log. Nếu yêu cầu phân quyền hoặc residency nghiêm ngặt, cân nhắc workspace riêng theo ranh giới hệ thống/dữ liệu.

### 14.3. Data retention, residency và điều tra sự cố

Trước khi bật log production:

1. Xác định vùng đặt workspace và yêu cầu nơi lưu dữ liệu.
2. Phân loại logs có khả năng chứa dữ liệu cá nhân hoặc thông tin bảo mật.
3. Chọn retention theo yêu cầu vận hành/kiểm toán và khả năng tier/bảng.
4. Thiết lập quyền truy cập, truy vấn và export phù hợp.
5. Ghi nhận quy trình xử lý yêu cầu bảo mật dữ liệu và response khi phát hiện log chứa secret.

Không mặc định retention càng dài càng tốt. Giữ dữ liệu vô hạn gây chi phí và rủi ro. Ngược lại, retention quá ngắn có thể khiến điều tra sự cố sau vài ngày không còn đủ bằng chứng.

### 14.4. Bảo vệ đường truyền telemetry

Agent cần đường mạng ra Azure Monitor ingestion endpoints theo cloud/region đã chọn. Với AKS private cluster hoặc egress hạn chế:

- Xác minh DNS và routing cho endpoint cần thiết.
- Kiểm tra Azure Firewall/NSG/UDR, proxy và các chính sách allowlist được hỗ trợ.
- Nếu dùng Azure Monitor Private Link Scope, lập kế hoạch endpoint/private DNS liên quan theo mô hình thực tế.
- Kiểm tra quyền của agent/managed identity và resource associations.
- Tránh mở toàn bộ outbound Internet khi chỉ thiếu một rule DNS/route cụ thể.

**Private AKS cluster** không tự khiến mọi log được ingest qua private endpoint. Phải xác minh đường telemetry thực tế và các điều kiện của Azure Monitor.

## 15. Quản lý chi phí Container Insights

Quan sát tốt cần đủ dữ liệu để điều tra, nhưng không thể bật mọi nguồn ở mức chi tiết cao vô thời hạn mà không xét chi phí.

### 15.1. Những yếu tố chi phí chính

| Hạng mục | Điều gì làm chi phí tăng? | Cách kiểm soát |
|---|---|---|
| **Log ingestion** | Rất nhiều dòng INFO/DEBUG, log từng request, log nhiều namespace | Cấu hình log level, sampling, streams/namespace filtering |
| **Log retention** | Giữ logs chi tiết nhiều tháng/năm | Retention theo bảng và nhu cầu điều tra |
| **Managed Prometheus** | Nhiều targets/series, labels có cardinality lớn | Scrape config, allowlists, loại labels dư |
| **Dashboard/query/alerts** | Truy vấn lớn hoặc quá nhiều alert evaluations theo pricing áp dụng | Tối ưu KQL, alert frequency và window |
| **Log Analytics/Monitor services** | Workspace plan, tính năng bổ sung, data export | Chọn cách dùng phù hợp và xem bảng giá hiện hành |
| **Networking** | Private endpoints, egress hoặc dịch vụ mạng phụ trợ | Thiết kế route hợp lý, xem tổng chi phí |

Phần lớn các chi phí nói trên **không tỉ lệ trực tiếp với số log statements trong source code** mà với dữ liệu được ingest/lưu và dịch vụ liên quan đang dùng. Khi 100 replicas cùng log debug ở mức mỗi request, tổng dữ liệu có thể lớn hơn 100 lần so với một instance.

### 15.2. Ước lượng dung lượng logs từ bảng ContainerLogV2

Trong những bảng Log Analytics có cột `_BilledSize`, có thể khảo sát kích thước bản ghi:

```kusto
ContainerLogV2
| where TimeGenerated > ago(7d)
| summarize ApproxIngestedGiB=sum(_BilledSize) / 1073741824.0
    by PodNamespace
| order by ApproxIngestedGiB desc
```

Đây là **ước lượng từ kích thước bản ghi trong bảng**, không phải hóa đơn Azure chính thức. Chính sách billable/non-billable, giá từng loại bảng, retention, vùng và các khoản phí khác có thể khiến số tiền thực tế khác; xem **Azure Cost Management**, Usage data và pricing tài nguyên để đánh giá. Nếu bảng hoặc cột không có, kiểm tra schema và billing model trước khi sửa query.

### 15.3. Vì sao nên tránh logs “mỗi request một dòng lớn”?

Giả sử API nhận 200 requests/giây và ghi trung bình 2 KB/request:

```text
200 request/s × 2 KB ≈ 400 KB/s
400 KB/s × 3600 s ≈ 1,44 GB/giờ
1,44 GB/giờ × 24 giờ ≈ 34,6 GB/ngày
```

Đây là **ước lượng minh họa thô** theo đơn vị thập phân, chưa tính hệ số metadata/encoding, compression, phần log khác hoặc cách tính billing. Nếu tăng traffic, thêm retry logs hoặc DEBUG logs, dữ liệu có thể tăng đáng kể. Do đó:

- Dùng **metrics** cho các số liệu tổng hợp lặp lại (RPS, latency, error rate).
- Dùng **logs** cho sự kiện cần chẩn đoán và phân tích có ngữ cảnh.
- Dùng **traces với sampling** khi cần theo dõi request qua nhiều dịch vụ.
- Chỉ giữ debug logs có thời hạn khi xử lý sự cố, rồi hạ mức log.

### 15.4. Lọc dữ liệu bằng cấu hình thu thập, không chỉ bằng KQL

Truy vấn KQL `where PodNamespace == "orders"` **không làm giảm chi phí ingestion của logs từ namespace khác** nếu mọi dữ liệu đã được gửi vào workspace. Muốn giảm ingestion thực tế, cần thay đổi **collection streams, namespace filtering, transformation hoặc application logging volume** theo khả năng pipeline.

Điều chỉnh DCR/filter nên có quy trình:

1. Đo dung lượng và phân bố logs theo workload/namespace.
2. Xác định những nguồn có giá trị thấp nhưng volume cao.
3. Thử cắt INFO/DEBUG không cần thiết hoặc giới hạn namespace trong dev.
4. Xác nhận không mất ERROR logs, audit logs bắt buộc hoặc tín hiệu cần điều tra.
5. Triển khai cấu hình qua IaC/phương thức được hỗ trợ.
6. So sánh ingestion, khả năng truy vấn và chi phí sau thay đổi.

Một số cấu hình **Basic logs, table plans, data collection transformation hoặc cost preset** có giới hạn tính năng, query, alert, retention hoặc điều kiện áp dụng. Không chuyển loại bảng/chế độ dữ liệu chỉ vì mức giá hấp dẫn khi chưa kiểm tra nhu cầu truy vấn và alerts hiện tại.

### 15.5. Cardinality trong Prometheus

Prometheus time series được phân biệt theo **metric name + tập labels**. Những labels như `pod`, `container`, `namespace` hữu ích trong giới hạn nhất định. Nhưng nếu dùng **userId**, **requestId** hoặc **orderId** làm label, mỗi request có thể tạo series mới, làm tăng cardinality, chi phí và độ phức tạp.

Không dùng thông tin định danh mỗi request làm metric label. Để tìm request cụ thể, ghi correlation ID vào log/traces với chính sách phù hợp; để tính RPS/latency, dùng histogram/counter theo những dimensions có cardinality được kiểm soát.

## 16. Tình huống thực tế: API lỗi 500 dù pod vẫn Running

### 16.1. Mô tả sự cố

Hệ thống đơn hàng có cấu trúc:

```text
Internet
   |
   v
Ingress / Application Gateway (tùy kiến trúc)
   |
   v
Service orders-api trong namespace orders
   |
   +-- Pod A (node-1)
   +-- Pod B (node-2)
   +-- Pod C (node-2)
   |
   v
Payment API + database
```

Lúc 14:05 UTC, alert báo error rate tăng. `kubectl get pods -n orders` cho thấy ba pod đều `Running`. Một bản cập nhật ứng dụng vừa triển khai lúc 14:00. Đội vận hành cần phân biệt:

- Bản release mới có lỗi logic?
- Database hoặc Payment API đang timeout?
- Pod bị restart/OOM nhưng đã trở lại Running?
- Node-2 thiếu CPU/RAM?
- Cấu hình mạng hoặc secret vừa bị thay?

### 16.2. Bước 1 – Xác nhận trải nghiệm người dùng

Xem **request telemetry/Application Insights** hoặc HTTP metrics thực tế để xác nhận:

- Tỷ lệ HTTP 5xx tăng từ bao nhiêu lên bao nhiêu?
- p95/p99 latency có tăng không?
- Tất cả endpoints lỗi hay chỉ `POST /orders`?
- Chỉ production hay cả môi trường khác?

Nếu chỉ có logs và chưa instrument HTTP metrics, có thể điều tra bằng log trước nhưng **không đưa ra số error rate chính xác khi chưa có request denominator**.

### 16.3. Bước 2 – Kiểm tra container logs

```kusto
ContainerLogV2
| where TimeGenerated between (datetime(2026-11-20T14:00:00Z) ..
                               datetime(2026-11-20T14:15:00Z))
| where PodNamespace == "orders"
| where PodName startswith "orders-api"
| extend Message=tostring(LogMessage)
| where Message has_any ("ERROR", "timeout", "exception")
| project TimeGenerated, PodName, ContainerName, Message
| order by TimeGenerated asc
```

Các thời điểm và nội dung là ví dụ thực hành; khi điều tra sự cố thật, dùng **UTC timestamp của incident**. Giả sử truy vấn cho thấy cả ba pod ghi `Payment provider timed out` sau rollout. Điều này là **dấu hiệu** liên quan dependency, chưa phải bằng chứng đủ để kết luận Payment API bên ngoài lỗi.

### 16.4. Bước 3 – Đối chiếu pod/events và metrics

```bash
kubectl get pods -n orders -o wide
kubectl describe deployment orders-api -n orders
kubectl get events -n orders --sort-by=.metadata.creationTimestamp
```

Trong Container Insights, xem node/container CPU/memory trong khoảng 13:55–14:15 UTC và kiểm tra restart state. Nếu `node-2` cao CPU và có `Unhealthy` events, có thể liên quan node pressure. Nếu node metrics bình thường nhưng dependency traces tăng timeout, điều tra đường kết nối và service đích.

### 16.5. Bước 4 – Đối chiếu thay đổi và cô lập nguyên nhân

Đối chiếu thời điểm:

| Thời gian | Sự kiện giả định |
|---|---|
| 14:00 | Deploy `orders-api:2.1.0` |
| 14:03 | Request latency tăng |
| 14:05 | Log `Payment provider timed out` xuất hiện |
| 14:06 | HTTP 5xx alert kích hoạt |
| 14:09 | Rollback thử một phần sang bản ổn định |
| 14:12 | Error rate giảm khi backend và network không đổi |

Nếu rollback một phần làm lỗi giảm theo tỷ lệ traffic của version mới, đó là bằng chứng đáng quan tâm về release. Tuy nhiên, vẫn cần xem **code path, retry/circuit breaker, deadline và dependency performance** để xác định nguyên nhân cụ thể.

Không kết luận nguyên nhân từ một bảng biểu duy nhất. **Tương quan thời gian không phải quan hệ nhân quả.** Runbook nên yêu cầu xác nhận trên ít nhất hai nguồn telemetry độc lập khi quyết định rollback production.

### 16.6. Bước 5 – Hậu kiểm

Sau sự cố:

1. Ghi timeline, người xử lý, phiên bản triển khai và thời điểm khôi phục.
2. Kiểm tra alert có phát hiện đủ sớm hay không.
3. Xem logs/traces còn thiếu field gì để điều tra nhanh hơn.
4. Bổ sung regression test hoặc circuit breaker/timeout policy nếu vấn đề thuộc ứng dụng.
5. Chỉ tăng log level khi cần, có thời hạn; sau đó trả về cấu hình để kiểm soát ingestion.
6. Kiểm tra retention có đủ cho điều tra sau sự cố, nhưng không lưu dữ liệu nhạy cảm ngoài chính sách.

## 17. Bài tập thực hành

### Bài tập A – Bật thu thập logs và xác minh

**Môi trường:** một AKS dev có Deployment `orders-api` và một Log Analytics workspace dành cho thử nghiệm.

**Yêu cầu:**

1. Kiểm tra cluster đã bật Container Insights hay chưa.
2. Nếu chưa, lập kế hoạch bật add-on với workspace có quyền phù hợp.
3. Xác nhận agent đang chạy, DCR liên kết với cluster và đích gửi dữ liệu đúng.
4. Xem logs từ Kubernetes bằng `kubectl logs`.
5. Truy vấn `ContainerLogV2` trong 30 phút gần nhất, lọc namespace `orders`.
6. Ghi rõ điểm khác nhau giữa “có log trong Kubernetes” và “đã ingest vào Log Analytics”.

**Hướng giải:** dùng `az aks show`, kiểm tra agent `ama-logs` hoặc resource tương ứng, xác nhận DCR/LAW rồi chạy KQL. Nếu `kubectl logs` có dữ liệu mà `ContainerLogV2` không có, kiểm tra addon/DCR, identity và network trước khi sửa ứng dụng.

### Bài tập B – Viết KQL điều tra lỗi

Giả sử có 10 pod `orders-api-*` trong namespace `orders`. Sự cố xảy ra 10 phút vừa qua.

**Nhiệm vụ:**

- Viết KQL tìm tối đa 100 dòng log có `timeout` hoặc `exception`.
- Nhóm số dòng lỗi theo pod trong mỗi khoảng 5 phút.
- Giải thích vì sao đếm số dòng lỗi không cho ra tỷ lệ HTTP 500.
- Nêu cách liên kết log với trace ID khi ứng dụng đã được instrument.

**Hướng giải tham khảo:**

```kusto
ContainerLogV2
| where TimeGenerated > ago(10m)
| where PodNamespace == "orders"
| where PodName startswith "orders-api"
| extend Message=tostring(LogMessage)
| where Message has_any ("timeout", "exception")
| summarize MatchingLines=count()
    by bin(TimeGenerated, 5m), PodName
| order by TimeGenerated desc
```

Để trả về **dòng log**, thay bước `summarize` bằng `project` các cột và `take 100`. Tỷ lệ 5xx cần tổng request và số request thất bại từ metrics/HTTP telemetry; trace ID cần được ghi hoặc propagate từ ứng dụng.

### Bài tập C – Phân biệt Prometheus và Container Insights

Đội SRE đã bật Container Insights, thấy `ContainerLogV2` trong Log Analytics nhưng không thể chạy PromQL `rate(container_cpu_usage_seconds_total[5m])` ở KQL editor.

**Câu hỏi:**

1. Vì sao không chạy được PromQL trong Log Analytics KQL?
2. Cần loại workspace nào cho managed Prometheus?
3. Metric `container_cpu_usage_seconds_total` đến từ scraper/exporter nào theo pipeline thực tế?
4. Điều gì có thể làm PromQL trả no data dù AKS healthy?
5. Tại sao không nên dùng `orderId` làm metric label?

**Hướng giải:** KQL và PromQL là hai ngôn ngữ/cơ sở dữ liệu khác nhau. Managed Prometheus lưu dữ liệu trong Azure Monitor workspace theo pipeline scrape. No data có thể do chưa bật metrics collection, thiếu targets, label không khớp hoặc workspace sai. `orderId` tạo cardinality lớn và có thể mang thông tin nhạy cảm.

### Bài tập D – Tối ưu chi phí

Một AKS cluster có 100 pods và phát sinh khoảng 35 GB container logs mỗi ngày. 60% đến từ `DEBUG` logs của namespace `test`.

**Nhiệm vụ:**

1. Đề xuất cấu hình ứng dụng giảm log DEBUG mặc định.
2. Xác định cách dùng DCR/namespace filter được tính năng hỗ trợ mà không làm mất logs production.
3. Giải thích vì sao query lọc namespace ở Log Analytics không làm giảm ingestion.
4. Chọn retention cho logs điều tra, logs audit và metrics theo yêu cầu khác nhau.
5. Tạo checklist kiểm thử sau tối ưu, bao gồm negative test khi ứng dụng phát sinh lỗi thật.

**Hướng giải:** giảm log ở nguồn trước; cấu hình pipeline thu thập theo nhu cầu; đo ingestion trước/sau; giữ ERROR logs và các sự kiện bảo mật thiết yếu; xem Cost Management và workspace billing thay vì coi `_BilledSize` là hóa đơn chính thức.

### Bài tập E – Thực hành response khi pod restart

Một Deployment `payment-worker` có restart count tăng, log báo tiến trình bị kết thúc.

**Nhiệm vụ:** nêu trình tự dùng `kubectl describe`/`kubectl logs --previous`, `KubeEvents`, `KubePodInventory`, memory metrics và phiên bản release để phân biệt `OOMKilled`, probe failure và lỗi code. Nêu bước nào vẫn cần kiểm tra trực tiếp từ Kubernetes API thay vì chỉ tin bảng tổng hợp có độ trễ.

## 18. Câu hỏi tự kiểm tra

**1. Container Insights và Log Analytics workspace có vai trò gì?** Container Insights cung cấp trải nghiệm thu thập/quan sát dữ liệu AKS; Log Analytics workspace lưu logs/inventory/performance được gửi theo cấu hình, truy vấn bằng KQL.

**2. `ContainerLogV2` chứa gì?** Các bản ghi log container stdout/stderr và metadata liên quan khi stream được bật và ingest.

**3. Bật Container Insights có tự tạo request trace cho mọi Java service không?** Không. Traces cần instrumentation như OpenTelemetry/Application Insights.

**4. Data Collection Rule quyết định điều gì?** Nguồn/streams, đích và những lựa chọn thu thập/chuyển đổi mà kiểu triển khai hỗ trợ.

**5. `kubectl logs` có dữ liệu nhưng KQL không thấy: kiểm tra gì?** Agent, DCR, LAW destination, network, quyền và query time range/cluster/namespace.

**6. Log Analytics workspace và Azure Monitor workspace có giống nhau không?** Không. LAW phục vụ KQL log tables; AMW là nơi lưu Prometheus metrics của managed Prometheus theo mô hình hỗ trợ.

**7. Muốn chạy `rate(container_cpu_usage_seconds_total[5m])` nên dùng KQL hay PromQL?** PromQL tại nguồn Prometheus metrics phù hợp.

**8. ContainerLogV2 ErrorLines có bằng số request 5xx không?** Không. Cần HTTP request metrics/telemetry và denominator.

**9. Pod Running có chứng minh chưa từng restart hay OOM không?** Không. Phải kiểm tra restart history, container last state và events/metrics.

**10. KQL lọc namespace có giảm chi phí thu thập logs không?** Không, vì logs có thể đã được ingest. Muốn giảm ingestion phải chỉnh ở nguồn/collector/DCR theo khả năng.

**11. Vì sao cần tránh labels `requestId` và `orderId` trong Prometheus?** Cardinality có thể tăng rất lớn, ảnh hưởng hiệu năng/chi phí và rủi ro lộ thông tin.

**12. Vì sao không nên log JWT hoặc secrets để điều tra lỗi?** Log lưu lâu và có nhiều người/dịch vụ truy cập; bearer credential bị lộ có thể bị lạm dụng.

**13. Muốn có AKS API Server audit logs, chỉ bật Container Insights là đủ chưa?** Chưa. Cần xem AKS diagnostic settings và categories control-plane được hỗ trợ.

**14. Vì sao cần theo dõi cả metrics plan/node và application telemetry?** Lỗi có thể đến từ hạ tầng hoặc logic/dependencies; một nguồn không đủ để xác định toàn bộ nguyên nhân.

## 19. Checklist triển khai Container Insights production

- [ ] Đã phân loại **logs, metrics, Kubernetes events/inventory, traces** và nhu cầu điều tra thực tế.
- [ ] Đã chọn đúng AKS cluster, Azure subscription, region và Log Analytics workspace.
- [ ] Đã kiểm tra cấu hình monitoring hiện có trước khi bật add-on hoặc thay DCR.
- [ ] Đã bật Container Insights theo cơ chế được AKS/CLI/Portal hỗ trợ.
- [ ] Agent thu thập đang chạy và có quyền/kết nối tới endpoint Azure Monitor.
- [ ] DCR gắn đúng cluster, chọn đúng streams, namespace filters và Log Analytics destination.
- [ ] `kubectl logs` có log và `ContainerLogV2` có dữ liệu trong khoảng thời gian kiểm thử.
- [ ] Đã kiểm tra các bảng inventory/events/performance đang thực sự có dữ liệu.
- [ ] Không nhầm KQL/LAW với PromQL/AMW; managed Prometheus được bật riêng khi cần.
- [ ] Những request metrics và traces của ứng dụng được instrument độc lập khi nhu cầu yêu cầu.
- [ ] Đã bật AKS diagnostic settings riêng nếu cần control-plane/audit logs.
- [ ] Dữ liệu logs có cluster, namespace, workload, UTC timestamp, version và correlation ID phù hợp.
- [ ] Không log secrets, tokens, dữ liệu nhạy cảm không cần thiết; đã thiết lập RBAC truy vấn logs.
- [ ] Đã có dashboard về availability, resource pressure, errors, latency và thay đổi release.
- [ ] Đã có alert với scope, threshold, evaluation window, action group và runbook.
- [ ] Đã kiểm thử các trường hợp pod restart/OOM, mất logs, mất metric và lỗi truy vấn workspace.
- [ ] Đã xem xét data residency, retention, workspace access, privacy và compliance.
- [ ] Đã đo ingestion, loại logs thừa, kiểm soát metric cardinality và dự toán chi phí.
- [ ] Đã đưa cấu hình monitoring/IaC, role assignments và change review vào quy trình vận hành.
- [ ] Đã kiểm tra khả năng rollback khi chỉnh data collection hoặc đổi workspace.

## 20. Kết luận

**Container Insights** là một lớp quan sát quan trọng cho AKS: thu thập **container logs, Kubernetes inventory/events và một số performance metrics** qua cơ chế Azure Monitor Agent, Data Collection Rules và Log Analytics workspace theo cấu hình. Dữ liệu này giúp đội vận hành điều tra lỗi pod, restart, node pressure và kết hợp thời điểm sự cố với triển khai ứng dụng. **KQL trên `ContainerLogV2`** phù hợp tìm và tổng hợp log; các bảng inventory/events/performance bổ sung ngữ cảnh.

Một hệ thống observability AKS đầy đủ thường cần phối hợp thêm **Azure Monitor managed Prometheus** cho Prometheus metrics/PromQL, **Application Insights/OpenTelemetry** cho request tracing và **AKS diagnostic settings** cho control-plane logs theo nhu cầu. Bật collector chỉ là bước đầu: cần xác minh end-to-end dữ liệu thật, thiết kế cảnh báo có runbook, bảo vệ logs khỏi thông tin nhạy cảm, giới hạn quyền truy vấn và quản lý ingestion/retention để quan sát đáng tin cậy mà không vượt ngân sách.
