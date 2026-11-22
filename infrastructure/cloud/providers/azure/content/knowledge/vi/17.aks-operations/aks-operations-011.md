# Managed Prometheus và Azure Managed Grafana cho AKS

Một cụm **Azure Kubernetes Service (AKS)** có thể chạy hàng trăm Pod và tự động tạo, xóa hoặc di chuyển chúng giữa các node. Khi API Java bắt đầu phản hồi chậm hoặc một Deployment thiếu bản sao sẵn sàng, người vận hành cần trả lời ngay: **Pod nào đang dùng nhiều CPU? Tỷ lệ lỗi HTTP tăng từ lúc nào? Node có đủ bộ nhớ không? Ứng dụng bị lỗi thật hay chỉ có một dashboard không nhận dữ liệu?** Theo dõi từng máy bằng cách đăng nhập thủ công không thể mở rộng theo Kubernetes.

**Azure Monitor managed service for Prometheus** (gọi ngắn là **Managed Prometheus**) cung cấp nơi lưu trữ và truy vấn metrics tương thích Prometheus do Azure quản lý. **Azure Managed Grafana** cung cấp giao diện bảng điều khiển để truy vấn và trực quan hóa metrics, kết hợp nhiều nguồn dữ liệu và hỗ trợ vận hành. Khi dùng với AKS, hai dịch vụ giúp bạn xây dựng hệ thống quan sát dựa trên **PromQL, dashboard, cảnh báo và dữ liệu có ngữ cảnh cluster/namespace/Pod**, mà không phải tự duy trì toàn bộ cụm Prometheus và Grafana.

Bài học thuộc chương **Vận hành AKS** trong module **CLOUD_PROVIDERS_AZURE**. Module khám phá Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, compute, lưu trữ, dữ liệu, rồi triển khai, giám sát, bảo vệ và quản lý chi phí. Trọng tâm ở đây là xây dựng **luồng metrics đáng tin cậy cho AKS**, đo sức khỏe Kubernetes lẫn ứng dụng, cấp quyền truy cập an toàn và tối ưu chi phí giám sát.

Sau khi học, bạn có thể:

- Phân biệt **metrics, logs, traces** và phần việc của Prometheus, Azure Monitor workspace, Grafana.
- Giải thích kiến trúc **AKS → metrics collector → Azure Monitor workspace → PromQL → Azure Managed Grafana**.
- Bật Managed Prometheus cho cluster bằng Portal hoặc Azure CLI khi được phép.
- Thiết lập quyền đọc metrics và quyền người dùng của Azure Managed Grafana.
- Hiểu default scrape targets, custom scrape và cách thu JVM/HTTP metrics từ Spring Boot.
- Viết truy vấn **PromQL** về CPU, memory, replica availability, tốc độ request và tỷ lệ lỗi.
- Thiết kế dashboards, alert rules, action groups và runbook xử lý sự cố.
- Chẩn đoán các lỗi **No data**, missing metrics, sai namespace/labels, thiếu quyền hoặc tắc đường mạng.
- Ước tính chi phí và hạn chế high cardinality, sampling quá dày, lưu trữ không cần thiết.

## 1. Observability trong AKS: metrics, logs và traces

**Observability** là khả năng suy luận trạng thái bên trong hệ thống từ tín hiệu vận hành. Ba nhóm dữ liệu thường gặp:

| Nhóm tín hiệu | Câu hỏi trả lời tốt | Ví dụ |
|---|---|---|
| **Metrics** | Bao nhiêu, nhanh/chậm thế nào, thay đổi theo thời gian? | CPU usage, Pod ready, requests/second, p95 latency |
| **Logs** | Sự kiện cụ thể nào xảy ra, thông điệp lỗi là gì? | Java exception, Kubernetes event, authentication failure |
| **Traces** | Một request đi qua những dịch vụ nào và bị chậm ở đâu? | HTTP gateway → orders API → database |

Prometheus tập trung vào **time-series metrics**. Một metric gồm tên, tập labels và các sample có timestamp/giá trị:

~~~text
http_server_requests_seconds_count{
  application="orders-api",
  method="GET",
  status="200"
} 18452
~~~

Đây là ví dụ minh họa; tên và labels thực tế do exporter/runtime và quá trình scrape quyết định. Khi request tăng, counter tăng; PromQL dùng **rate()** hoặc **increase()** để tính tốc độ/số request trong một khoảng.

### Đừng đồng nhất các dịch vụ quan sát

- **Managed Prometheus**: metrics kiểu Prometheus, quy tắc scrape và truy vấn PromQL.
- **Azure Monitor workspace (AMW)**: tài nguyên lưu trữ/truy vấn dữ liệu Prometheus được quản lý; không phải Azure Log Analytics workspace.
- **Azure Managed Grafana**: giao diện dashboard/query; không phải nơi lưu metrics gốc của Managed Prometheus.
- **Container Insights**: quan sát container/cluster với tập tính năng logs, inventory và một số signals khác; thường dùng Log Analytics trong mô hình phù hợp.
- **Application Insights/OpenTelemetry**: đo request, dependencies, traces và telemetry ứng dụng theo cấu hình được chọn.

Một cluster có **Managed Prometheus** không có nghĩa đã thu đủ **stdout/stderr logs** hoặc distributed traces. Ngược lại, bật Container Insights không có nghĩa tất cả custom Prometheus metrics của Java tự xuất hiện.

## 2. Kiến trúc Managed Prometheus + Managed Grafana

~~~text
                     AKS cluster
                +----------------------+
                | kubelet / cAdvisor   |
                | kube-state-metrics   |
                | node exporters       |
                | Java /metrics        |
                +----------+-----------+
                           |
                      Prometheus scrape
                           |
                           v
                 Azure Monitor metrics
                  collector (ama-metrics)
                           |
                           | Managed ingestion
                           v
                    Azure Monitor
                      workspace
                  (Prometheus metrics)
                           ^
                           | PromQL / data source
                           |
                   Azure Managed Grafana
                     dashboards / users
                           |
                     Operator / SRE

     Tùy chọn riêng:
       AKS logs ----------> Log Analytics / Container Insights
       Java traces -------> Application Insights / trace backend
       Alerts ------------> Azure Monitor Action Group
~~~

Thành phần thu thập metrics thường xuất hiện trong cluster dưới những workload liên quan **ama-metrics** khi tính năng managed Prometheus được bật theo mô hình AKS hỗ trợ.

**Dữ liệu không tự chảy vào Grafana bằng việc tạo Grafana workspace.** Cluster phải có collector/scrape; metrics phải được ghi vào AMW; Grafana phải có data source và quyền đọc; người vận hành phải có quyền vào Grafana.

### Ai chịu trách nhiệm phần nào?

| Thành phần | Azure quản lý | Nhóm vận hành vẫn cần quản lý |
|---|---|---|
| AKS control plane | Theo mô hình AKS | Node pools, workload, security, quotas, upgrades |
| Managed metrics backend | Hạ tầng dịch vụ lưu/truy vấn metrics | Chọn AMW, scrape targets, nhãn, retention/cost, quyền |
| Metrics collectors | Cơ chế addon/extension được hỗ trợ | Bật tính năng, custom scrape, kiểm tra Pods/ingestion |
| Azure Managed Grafana | Dịch vụ Grafana được quản lý | IAM, data sources, folders/dashboards, alerts và phân quyền |
| Java instrumentation | Không tự viết mã cho ứng dụng | Micrometer/Actuator, metrics hữu ích, cardinality và privacy |

Managed không đồng nghĩa **zero configuration**, **zero cost** hoặc **không cần phân quyền**.

## 3. Azure Monitor workspace là gì?

**Azure Monitor workspace (AMW)** là tài nguyên Azure dành cho dữ liệu metrics theo định dạng Prometheus được Managed Prometheus sử dụng. Đây là điểm đích để collectors gửi metrics và là nguồn dữ liệu cho các truy vấn PromQL.

### Phân biệt các "workspace"

| Tên | Mục đích chính |
|---|---|
| **Azure Monitor workspace** | Lưu và truy vấn Prometheus metrics do Azure quản lý |
| **Log Analytics workspace** | Lưu/truy vấn logs theo Kusto Query Language (KQL) khi dịch vụ gửi dữ liệu tới đó |
| **Azure Managed Grafana workspace** | Chạy giao diện Grafana, data source configuration, dashboards và quyền người dùng |

Ba tài nguyên có thể cùng phục vụ một kiến trúc AKS, nhưng **không thể dùng thay thế cho nhau**. Đặc biệt, một dashboard Grafana truy vấn PromQL từ AMW không phải là một truy vấn KQL trên Log Analytics.

### Vấn đề region và scope

Khi thiết kế:

- Chọn AMW trong khu vực, subscription và resource group được tổ chức cho phép.
- Xem tính năng hỗ trợ kết nối nhiều cluster vào một AMW theo phiên bản dịch vụ và mô hình kiến trúc.
- Cân nhắc tách **dev/test/prod**, tenant hoặc domain để kiểm soát quyền, chi phí và độ phức tạp truy vấn.
- Đừng giả định tất cả AKS, AMW và Grafana phải ở cùng một region trong mọi topology; hãy đối chiếu khả năng hỗ trợ, residency, latency và chính sách thực tế.
- Ghi lại đường sở hữu tài nguyên, cảnh báo, retention và kế hoạch phục hồi nếu AMW/dashboards gặp sự cố.

**Một AMW có nhiều nguồn metrics** cần quy ước labels đủ để phân biệt cluster, namespace và workload. Không dùng một tên cluster hiển thị làm ranh giới bảo mật nếu RBAC thực tế cho quyền đọc rộng hơn.

## 4. Những metrics nào nên theo dõi trên AKS?

Chia tín hiệu thành các lớp:

| Lớp | Metrics tiêu biểu | Phản ánh điều gì? |
|---|---|---|
| **Cluster/node** | CPU, memory, node readiness, filesystem, network | Node có đủ tài nguyên và hoạt động không? |
| **Kubernetes objects** | Deployment desired/available replicas, Pod phases, restart counts | Controllers có đạt desired state không? |
| **Container** | CPU usage, memory working set, throttling, restarts | Container nào là bottleneck? |
| **Application** | HTTP request rate, error rate, duration, JVM memory/GC | Người dùng và dịch vụ trải nghiệm thế nào? |
| **Dependencies** | DB pool usage, queue lag, dependency failures | Điểm nghẽn nằm ngoài container? |
| **Business** | Successful checkouts, background jobs, processing time | Hệ thống có thực sự hoàn thành nhiệm vụ không? |

Collector mặc định của Managed Prometheus có thể thu một tập targets/metrics Kubernetes được cấu hình sẵn, ví dụ từ **kubelet/cAdvisor, kube-state-metrics hoặc node exporters** theo phiên bản addon và tính năng được bật. Azure có thể áp dụng **keep lists/minimal ingestion** cho một số metrics mặc định nhằm kiểm soát chi phí.

**Không mặc định mọi metric từ mọi exporter trong cluster đều được thu.** Đặc biệt, metrics của Java Spring Boot cần có endpoint xuất Prometheus và **custom scraping** hoặc cấu hình thu thập tương ứng.

## 5. Bật Managed Prometheus trên AKS bằng Azure Portal

Điều kiện trước khi thao tác:

1. Có **AKS cluster** đang hoạt động trong subscription mà bạn được phép quản trị.
2. Có hoặc được phép tạo **Azure Monitor workspace** trong phạm vi phù hợp.
3. Có quyền cập nhật cấu hình giám sát AKS, kết nối tới AMW và tạo các tài nguyên liên quan.
4. Đã kiểm tra budget/ingestion cost và chính sách lưu trữ dữ liệu.
5. Network và Azure Policy không chặn addon/collector hoặc luồng tới endpoint ingestion.

Trình tự chung trong Portal:

1. Đăng nhập [Azure Portal](https://portal.azure.com), mở đúng **AKS cluster**.
2. Vào phần **Monitoring** hoặc **Insights** và tìm lựa chọn bật **Managed Prometheus / Prometheus metrics**.
3. Chọn **Azure Monitor workspace** hiện có, hoặc tạo workspace mới nếu được phép.
4. Chọn kết nối Grafana nếu workflow Portal hỗ trợ, hoặc cấu hình Azure Managed Grafana riêng sau.
5. Xem lại thông tin resource, identity, IAM, scope và ảnh hưởng chi phí.
6. Bật tính năng rồi xác nhận addon metrics collectors được triển khai.
7. Mở AMW và kiểm tra metrics đến trước khi tạo dashboard tùy chỉnh.

Tên trang/nút có thể thay đổi theo Portal. **Đừng bật Container Insights/log collection ngoài nhu cầu chỉ để có Managed Prometheus**, vì đó là đường dữ liệu và chi phí khác.

### Bật tính năng có làm ứng dụng gián đoạn?

Thường mục tiêu là thêm giám sát, không thay ứng dụng. Tuy nhiên collector dùng CPU/memory và có thể tác động mạng/nodes; khi thay đổi monitoring config trên cluster production, cần có thời điểm và quy trình kiểm tra. Không gọi đây là thao tác **không rủi ro**.

## 6. Azure CLI: kiểm tra AKS và kích hoạt metrics addon

Ví dụ dùng **Bash/Azure Cloud Shell** có Azure CLI và đủ quyền. Các dòng chứa placeholder không thể chạy nguyên văn. Chỉ chạy lệnh **update** trên cluster lab hoặc theo change request được phê duyệt.

### Chọn subscription, cluster và AMW

~~~bash
az login
az account list --output table
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG_AKS="<AKS_RESOURCE_GROUP>"
AKS="<AKS_CLUSTER_NAME>"
AMW_ID="<EXISTING_AZURE_MONITOR_WORKSPACE_RESOURCE_ID>"

az aks show \
  --resource-group "$RG_AKS" \
  --name "$AKS" \
  --query "{name:name,location:location,id:id,monitorProfile:azureMonitorProfile}" \
  --output json
~~~

**AMW_ID** phải là resource ID thật của Azure Monitor workspace, không phải Log Analytics workspace ID hay Grafana workspace ID.

### Bật managed Prometheus collection

~~~bash
az aks update \
  --resource-group "$RG_AKS" \
  --name "$AKS" \
  --enable-azure-monitor-metrics \
  --azure-monitor-workspace-resource-id "$AMW_ID"
~~~

Lệnh trên thay đổi AKS resource; kiểm tra **az aks update --help**, Azure CLI version và tính năng được hỗ trợ trong subscription trước khi áp dụng. Một số môi trường có extension/command khác theo thời điểm; không sửa bằng cách cài ngẫu nhiên nhiều extension khi chưa hiểu thông báo lỗi.

### Xác minh sau cấu hình

~~~bash
az aks show \
  --resource-group "$RG_AKS" \
  --name "$AKS" \
  --query "azureMonitorProfile" \
  --output json
~~~

Nếu bạn có quyền Kubernetes:

~~~bash
az aks get-credentials \
  --resource-group "$RG_AKS" \
  --name "$AKS"

kubectl config current-context
kubectl get pods -n kube-system | grep ama-metrics
~~~

**az aks get-credentials** có thể thay kubeconfig context mặc định, vì vậy phải xác nhận không đang trỏ tới cluster production khác. Tên/nhóm Pod addon có thể thay đổi; danh sách trên là một tín hiệu tham khảo, không chứng minh tất cả scrape targets đều healthy.

**Quan trọng:** Một collector Pod đang Running không bảo đảm AMW đã nhận dữ liệu, và AMW nhận dữ liệu chưa bảo đảm Grafana có quyền đọc.

## 7. Azure Managed Grafana phục vụ điều gì?

**Azure Managed Grafana** là dịch vụ Grafana được Azure quản lý, dùng để:

- Tạo dashboard theo nhóm vận hành, namespace, cluster, ứng dụng hoặc môi trường.
- Viết query metrics (PromQL trong trường hợp Managed Prometheus).
- Kết hợp nhiều nguồn dữ liệu tùy plugin/phiên bản/tính năng được hỗ trợ.
- Quản lý folder, dashboard variables, permissions và chia sẻ.
- Tạo/hiển thị alerting theo cơ chế của Grafana khi phù hợp.

Azure Managed Grafana **không tự động scrape Pod** và không thay cơ sở lưu trữ metrics. Grafana gửi truy vấn tới data source đã cấu hình.

~~~text
Azure Managed Grafana dashboard
  Panel: "Java API request rate"
      |
      | PromQL query
      v
Azure Monitor workspace (managed Prometheus)
      |
      v
Time-series samples đã thu từ AKS
~~~

### Dùng Grafana cho phần nào, Azure Monitor cho phần nào?

| Nhu cầu | Công cụ phù hợp |
|---|---|
| Dashboard nhiều panel/truy vấn PromQL | Azure Managed Grafana |
| Lưu, thu và query Prometheus metrics được Azure quản lý | Azure Monitor workspace + Managed Prometheus |
| Alert rules hoạt động độc lập với dashboard người vận hành | Azure Monitor Prometheus rule groups/alert rules khi phù hợp |
| Thông báo tới email, webhook, hệ thống trực | Azure Monitor Action Groups hoặc contact points theo mô hình cảnh báo |
| Điều tra exception Java cụ thể | Application logs / Application Insights |
| Theo dõi các cuộc gọi xuyên nhiều microservices | Distributed tracing/OpenTelemetry |

Không xây thiết kế cảnh báo chỉ dựa trên việc ai đó **đang mở dashboard trên trình duyệt**.

## 8. Kết nối Azure Managed Grafana với Azure Monitor workspace

Một quá trình điển hình:

1. Tạo hoặc mở **Azure Managed Grafana workspace** đã được phê duyệt.
2. Bật/cấu hình **managed identity** cho Grafana theo khả năng dịch vụ.
3. Cho identity của Grafana **quyền đọc metrics** trên Azure Monitor workspace.
4. Kết nối datasource **Azure Monitor managed service for Prometheus** hoặc kiểu dữ liệu Prometheus qua tích hợp Azure hỗ trợ.
5. Mở một dashboard có sẵn để kiểm tra các series Kubernetes.
6. Cấp vai trò **Grafana Viewer/Editor/Admin** tương ứng cho người vận hành.
7. Kiểm tra bằng tài khoản chỉ có quyền Viewer để xác nhận không thể thay đổi datasource/permissions ngoài phạm vi.

### Quyền đọc dữ liệu khác quyền đăng nhập Grafana

Hai lớp quyền khác nhau:

| Chủ thể | Phạm vi | Quyền thường cần |
|---|---|---|
| **Managed identity của Grafana** | Azure Monitor workspace | Quyền **Monitoring Data Reader** hoặc role tương đương được tài liệu tích hợp chỉ định |
| **Người mở dashboard** | Azure Managed Grafana resource | Vai trò **Grafana Viewer**, **Grafana Editor** hoặc **Grafana Admin** phù hợp |
| **Quản trị viên cấu hình kết nối** | Azure resource và Grafana settings | Quyền thiết lập datasource/IAM phù hợp, có audit |

Một người có thể đăng nhập Grafana thành công nhưng thấy **No data** vì identity của Grafana chưa được AMW cho phép truy vấn. Ngược lại, Grafana có quyền query AMW nhưng người dùng không có quyền vào Grafana cũng không xem được dashboard.

### Mô hình quyền theo nguyên tắc tối thiểu

- Người trực vận hành xem dashboard: **Viewer** khi không cần sửa nội dung.
- SRE/dashboard maintainer: **Editor** ở phạm vi được phê duyệt.
- Nhóm quản trị datasource/permissions: **Admin** với quy trình thay đổi và audit.
- Identity của Grafana: **quyền đọc**, không cần quyền xóa AMW hoặc cập nhật AKS.

**Không chia sẻ tài khoản Grafana Admin dùng chung.** Sử dụng Entra ID, nhóm người dùng, vai trò và audit phù hợp.

## 9. Tạo dashboard Kubernetes cơ bản

Một dashboard có ích cho vận hành AKS nên trả lời theo thứ tự:

1. **Cluster còn đủ node Ready không?**
2. **Deployment nào đang thiếu Pod available?**
3. **Pod/container nào đang tiêu tốn CPU/memory?**
4. **Ứng dụng có tăng lỗi hoặc latency không?**
5. **Đây là vấn đề của một namespace, một node hay nhiều workload?**

### Bố cục gợi ý

~~~text
Dashboard: AKS Production Overview

Filter: cluster | namespace | workload

┌─────────────────────────────────────────────┐
│ Node Ready │ Pods Ready │ Alerts │ RPS      │
├─────────────────────────────────────────────┤
│ CPU usage theo namespace                   │
├─────────────────────────────────────────────┤
│ Memory working set theo Pod                │
├─────────────────────────────────────────────┤
│ Deployment desired vs available replicas   │
├─────────────────────────────────────────────┤
│ Java API: request rate / 5xx / p95 latency │
└─────────────────────────────────────────────┘
~~~

Đây là một **wireframe**, không phải dashboard JSON import được. Khi tạo dashboard thật, chọn đúng datasource, interval, units, labels và format time-series của từng metric.

### Dashboard variables

Grafana hỗ trợ các biến để chọn cluster/namespace/workload theo dữ liệu hoặc danh sách định sẵn. Ví dụ ý tưởng query:

~~~promql
label_values(kube_pod_info, namespace)
~~~

**label_values** là cú pháp thường gặp trong **Grafana variable query**, **không phải một hàm PromQL chuẩn** để chạy trong mọi Prometheus query editor/API. Trong panel PromQL thuần, dùng PromQL chuẩn, ví dụ lọc theo label đã chọn:

~~~promql
sum by (namespace) (kube_pod_status_phase{phase="Running"})
~~~

Trong một số môi trường, metric/label được giảm hoặc đổi bởi minimal ingestion hay relabeling; chọn đúng series thật thay vì mặc định copy query sẽ có kết quả.

## 10. PromQL căn bản: metric, label, range vector

**PromQL** là ngôn ngữ truy vấn dữ liệu time-series theo Prometheus. Bốn loại thao tác rất phổ biến:

| Khái niệm | Ví dụ | Dùng khi |
|---|---|---|
| **Instant vector** | kube_node_status_condition | Xem giá trị mới nhất của series |
| **Label filtering** | {namespace="orders"} | Chỉ lấy một workload/phạm vi |
| **Range vector** | [5m] | Phân tích dữ liệu trong cửa sổ thời gian |
| **Aggregation** | sum by (pod) (...) | Gộp nhiều series theo chiều cần xem |

Prometheus metrics có các loại thường gặp:

- **Counter:** chỉ tăng (trừ restart/reset), ví dụ số HTTP requests. Thường dùng **rate()** hoặc **increase()**.
- **Gauge:** có thể tăng/giảm, ví dụ memory usage hay số Pod Ready.
- **Histogram:** theo dõi phân phối quan sát, thường có bucket/total count/sum để ước lượng latency.
- **Summary:** quan sát thời gian/độ lớn; cách tổng hợp percentile giữa nhiều series khác histogram.

Không dùng **rate()** trên mọi gauge hoặc cộng các percentile p95 từ nhiều Pod rồi coi là p95 toàn dịch vụ.

### Kiểm tra một metric có tồn tại trước khi vẽ panel

Trong Query editor, bắt đầu bằng một metric đơn giản:

~~~promql
up
~~~

**up = 1** thường nghĩa lần scrape gần nhất thành công với target đó; **up = 0** nghĩa scrape không thành công theo Prometheus. Tuy nhiên, tùy cơ chế ingestion, labels hoặc series được lưu, bạn cần đối chiếu các target thật. **Không có up series** không đủ để kết luận cluster không chạy.

Sau đó kiểm tra:

~~~promql
count by (job) (up)
~~~

Dùng kết quả để xem những **job** đã xuất hiện. Nếu query hoàn toàn rỗng, kiểm tra datasource, time range, region, permission, scrape configuration và độ trễ ingestion.

## 11. PromQL cho node và Pod

Ví dụ dùng metric phổ biến từ kube-state-metrics/cAdvisor; **series và labels thực tế phụ thuộc cấu hình collector, metric keep-list và phiên bản Kubernetes**.

### Đếm node Ready

~~~promql
sum(kube_node_status_condition{condition="Ready",status="true"})
~~~

Nếu dashboard có nhiều cluster chung workspace, hãy thêm label phân biệt cluster khi metric đã có nhãn đó. Không cộng toàn bộ nodes của hai cluster rồi diễn giải thành một cluster healthy.

### CPU usage theo Pod

~~~promql
sum by (namespace, pod) (
  rate(container_cpu_usage_seconds_total{
    namespace="orders",
    container!="",
    container!="POD"
  }[5m])
)
~~~

Counter **container_cpu_usage_seconds_total** thường đo số giây CPU đã dùng; **rate()** cho biết mức tiêu thụ tương đương cores CPU. Một kết quả **0.25** là xấp xỉ **0,25 core** theo thời gian của query, không phải 25% của một node bất kỳ.

### Memory working set theo Pod

~~~promql
sum by (namespace, pod) (
  container_memory_working_set_bytes{
    namespace="orders",
    container!="",
    container!="POD"
  }
)
~~~

Đơn vị ở đây là **bytes**. Trong Grafana, chọn unit **bytes/IEC** hoặc cách thể hiện phù hợp. Không nhầm working set với Java heap; container memory còn gồm native memory, thread stacks, buffers, filesystem cache tùy định nghĩa metric.

### Deployment thiếu replicas

~~~promql
kube_deployment_spec_replicas{namespace="orders",deployment="orders-api"}
-
kube_deployment_status_replicas_available{namespace="orders",deployment="orders-api"}
~~~

Kết quả dương cho thấy số desired lớn hơn số available theo time series đang có. Nếu xuất hiện nhiều cluster hoặc nhãn khác nhau, cần match labels chính xác khi trừ vector; nếu label sets không tương thích, phép toán có thể trả rỗng. Đây là lý do nên **xem labels và raw series trước khi áp dụng dashboard mẫu**.

## 12. Instrumentation ứng dụng Java bằng Micrometer

Metrics hạ tầng chỉ cho biết node/Pod có khỏe hay không. Khi khách hàng báo API chậm, cần **application metrics** về request, latency, lỗi và JVM.

Với **Spring Boot Actuator + Micrometer Prometheus registry**, bạn có thể xuất metrics ở endpoint dạng:

~~~text
GET /actuator/prometheus
Content-Type: text/plain; version=...

jvm_memory_used_bytes{area="heap",...} ...
process_cpu_usage{...} ...
http_server_requests_seconds_count{...} ...
~~~

Tên series/labels phụ thuộc phiên bản Spring Boot, Micrometer và cấu hình instrumentation.

### Maven dependencies

Trong **pom.xml**, thêm các dependency thích hợp nếu chưa có:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Với Spring Boot BOM/parent phù hợp, dependency versions thường được quản lý nhất quán. Không thêm nhiều bản thư viện Prometheus client khác nhau chỉ để làm metrics xuất hiện.

### Cấu hình application.properties

~~~properties
server.port=8080
management.endpoints.web.exposure.include=health,info,prometheus
management.endpoint.health.probes.enabled=true
~~~

Kiểm thử trong local/sandbox:

~~~bash
curl -fsS http://localhost:8080/actuator/prometheus | head -n 25
~~~

Ứng dụng cần thực sự chạy ở port 8080 và cho phép truy cập endpoint từ môi trường kiểm thử. **Không public endpoint /actuator/prometheus lên Internet chỉ để collector truy cập**. Nó có thể tiết lộ tên endpoint, thư viện, vùng bộ nhớ và topology; giữ đường scrape trong mạng nội bộ có kiểm soát.

### Đo metrics nghiệp vụ bằng Micrometer

Ví dụ dùng **Counter** để đếm một sự kiện đã hoàn tất:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutMetrics {
    private final Counter completedCounter;

    public CheckoutMetrics(MeterRegistry registry) {
        this.completedCounter = Counter.builder("checkout_completed")
                .description("Completed checkout operations")
                .tag("result", "success")
                .register(registry);
    }

    public void completed() {
        completedCounter.increment();
    }
}
~~~

Đây là ví dụ instrumentation, **không phải hệ thống thanh toán hoàn chỉnh**. Micrometer Prometheus registry thường xuất Counter có tên **checkout_completed_total** bằng cách thêm hậu tố **_total** cho tên instrument **checkout_completed**. Chỉ gọi **completed()** sau khi quy trình nghiệp vụ đã xác nhận kết quả theo logic đáng tin cậy; nếu một giao dịch có retry hoặc rollback, phải định nghĩa rõ "completed" nghĩa là gì.

**Không gắn customerId, email, orderId hoặc requestId thành labels**: mỗi giá trị khác nhau có thể tạo một time series mới, gây high cardinality, tăng chi phí và có nguy cơ lộ dữ liệu nhạy cảm.

## 13. Custom scraping từ Java Pod

Managed Prometheus thường không tự biết endpoint Java **/actuator/prometheus** của bạn. Để có metrics ứng dụng, cần cấu hình **custom scrape** theo cơ chế AKS/Managed Prometheus được hỗ trợ.

Các hướng cấu hình thường gặp:

- **Pod annotations** nếu đã bật/thiết lập cơ chế scrape theo annotations trong addon.
- **Custom Prometheus scrape config** qua ConfigMap/cơ chế cấu hình Azure Monitor metrics collector được hỗ trợ.
- Một số hình thức tích hợp Prometheus Operator/custom resources trong môi trường tương ứng; **không mặc định ServiceMonitor/PodMonitor có tác dụng** nếu chỉ bật Managed Prometheus và không có controller hỗ trợ.

### Pod annotations: thông tin quảng bá endpoint

Ví dụ metadata cho Pod template:

~~~yaml
template:
  metadata:
    labels:
      app: java-api
    annotations:
      prometheus.io/scrape: "true"
      prometheus.io/path: "/actuator/prometheus"
      prometheus.io/port: "8080"
  spec:
    containers:
      - name: java-api
        image: <ACR_LOGIN_SERVER>/java-api:1.0.0
        ports:
          - name: http
            containerPort: 8080
~~~

Đây là **trích đoạn Pod template**, không phải Deployment hoàn chỉnh. **Annotations tự chúng không bảo đảm được scrape.** Collector phải được cấu hình để nhận annotation-based targets, đúng namespace, path, port và auth/network. Cách bật pod annotation scraping và bộ lọc namespace thay đổi theo phiên bản addon; hãy dùng mẫu ConfigMap chính thức thay vì giả định Prometheus Operator đang có sẵn.

### Mẫu Prometheus scrape job khái niệm

Với một collector nhận **Prometheus scrape_config** chuẩn và được phép dùng Kubernetes service discovery, một job có thể có hình dạng:

~~~yaml
scrape_configs:
  - job_name: java-api
    scrape_interval: 30s
    metrics_path: /actuator/prometheus
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - observability-demo
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: java-api
      - source_labels: [__meta_kubernetes_pod_container_port_name]
        action: keep
        regex: http
~~~

**Đây là trích đoạn của cấu hình scrape Prometheus**, **chưa phải Kubernetes ConfigMap hoàn chỉnh** để apply ngay. Trong Managed Prometheus, phải đặt nội dung vào đúng **ConfigMap name/key/namespace** và tuân theo **định dạng custom scrape hiện hành của Azure Monitor metrics addon**. Ví dụ tên cấu hình được tài liệu sử dụng là **ama-metrics-prometheus-config**; hãy xác minh schema, quyền service discovery, giới hạn cấu hình và cách rollout trước khi áp dụng.

### Cách kiểm chứng target thật đã được scrape

1. Kiểm tra **Java app** trả metrics qua curl bên trong mạng cluster.
2. Kiểm tra collector config được áp dụng hợp lệ, không có lỗi parse/relabel.
3. Trong AMW/Grafana thử query các tên metric Java như **jvm_memory_used_bytes**.
4. Lọc theo **job**, **namespace** và **pod** sau khi xem labels thật.
5. Kiểm tra timestamps mới và số sample; đừng chỉ dựa vào một screenshot cũ.
6. Khi cluster/network bị giới hạn, xem NSG/NetworkPolicy, DNS và quyền của collector.

Nếu collector không tới endpoint Java, **đừng mở công khai ứng dụng**. Sửa đường kết nối trong cluster và cấu hình scrape.

## 14. PromQL cho ứng dụng Java

Các ví dụ dưới đây giả sử Micrometer xuất metric names quen thuộc. **Không mọi ứng dụng đều có histogram buckets** và job/namespace labels có thể do collector thêm vào. Hãy thử raw query trước khi copy dashboard.

### Requests mỗi giây

~~~promql
sum(
  rate(http_server_requests_seconds_count{job="java-api"}[5m])
)
~~~

Nếu label **job="java-api"** không tồn tại, thay bằng selector thực sự được collector gắn. Ví dụ này tính **requests/second** từ counter request do Spring/Micrometer cung cấp.

### Tỷ lệ HTTP 5xx

~~~promql
sum(
  rate(http_server_requests_seconds_count{
    job="java-api",
    status=~"5.."
  }[5m])
)
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{job="java-api"}[5m])),
  0.001
)
~~~

Kết quả là tỷ lệ **0–1**, không phải phần trăm 0–100. Trong Grafana chọn unit **Percent (0.0–1.0)** hoặc nhân **100** và chọn unit 0–100 tương ứng. Khi request volume thấp, tỷ lệ rất nhạy với vài lỗi; nên kết hợp cảnh báo với ngưỡng lưu lượng tối thiểu hoặc số lượng lỗi tuyệt đối.

### p95 latency khi có histogram buckets

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{job="java-api"}[5m])
  )
)
~~~

**Chỉ chạy ví dụ này nếu metric dạng histogram bucket đang được xuất**. Với Micrometer/Spring Boot, có thể cần bật histogram SLO/bucket phù hợp cho HTTP server requests. Nếu không có series **_bucket**, query sẽ rỗng. Không thể tính p95 từ một series count duy nhất.

Đơn vị phổ biến của **http_server_requests_seconds** là **giây**; chọn unit **seconds** trong Grafana. Để biểu diễn milliseconds, nhân 1000 với ý nghĩa đã xác nhận.

### JVM heap đang dùng

~~~promql
sum(
  jvm_memory_used_bytes{job="java-api",area="heap"}
)
~~~

Khi có nhiều replicas, **sum** tính tổng heap của các process được chọn. Muốn so từng Pod, dùng:

~~~promql
sum by (pod) (
  jvm_memory_used_bytes{job="java-api",area="heap"}
)
~~~

Hãy đo **JVM heap, non-heap, GC pause, container working set và OOMKilled** cùng nhau. Heap dưới giới hạn container không loại trừ nguy cơ OOM do native memory/thread stacks/direct buffers.

### Counter tùy biến checkout

~~~promql
sum by (result) (
  increase(checkout_completed_total{job="java-api"}[1h])
)
~~~

Đây là **số sự kiện theo instrumentation**, không tự bảo đảm bằng số giao dịch đã commit trong database. Cần đối chiếu với nghiệp vụ nếu metric dùng cho SLA/billing.

## 15. Thiết kế dashboard Java API theo bốn tín hiệu vàng

Một bảng điều khiển API nên có:

| Tín hiệu | Panel | Cách diễn giải |
|---|---|---|
| **Latency** | p50/p95/p99 request duration | User có thấy chậm ở đuôi phân phối không? |
| **Traffic** | Requests per second | Có tăng tải hoặc mất lưu lượng không? |
| **Errors** | 5xx ratio và số lỗi tuyệt đối | Lỗi có vượt SLO không? |
| **Saturation** | CPU throttling, memory, thread/connection pool | Workload có gần giới hạn phục vụ không? |

Đối với Java, thêm **GC pause duration**, heap usage, live threads và số connection tới database. Không đưa toàn bộ 100 metrics lên cùng một dashboard tổng quan; cần dashboard **overview** và dashboard **deep dive** theo use case.

### Ví dụ ngưỡng để diễn tập

Giả sử nhóm đặt **SLO thành công 99,9%** cho API (một mục tiêu giả định). Một dashboard có thể hiển thị:

~~~text
Request success rate 5m    99.95%
HTTP 5xx rate 5m           0.05%
p95 latency                220 ms
Ready Pods / desired       3 / 3
JVM heap used              62%
~~~

Các số trên là **minh họa**, không phải metrics thật từ AKS hay khuyến nghị SLO chung. Ngưỡng phải dựa trên yêu cầu người dùng, tải nền, latency budget và hành vi ứng dụng.

## 16. Azure Monitor Prometheus alert rules

Dashboard giúp con người nhìn dữ liệu; **alert rule** giúp phát hiện thay đổi ngay cả khi không ai mở Grafana.

Trong hệ sinh thái Azure Monitor, có thể tạo **Prometheus rule group** liên kết AMW, bên trong có các **recording rules** hoặc **alert rules** theo khả năng dịch vụ. Alert có thể sử dụng Azure Monitor **Action Groups** để thông báo tới email, webhook hoặc hệ thống ứng cứu hỗ trợ.

### Mẫu PromQL cảnh báo Deployment thiếu Pod

~~~promql
sum(
  kube_deployment_status_replicas_available{
    namespace="orders",
    deployment="orders-api"
  }
)
<
2
~~~

Ví dụ giả định desired minimum của workload là hai Pod và cần **for: 10m** ở cấu hình rule phù hợp để tránh cảnh báo từ các gián đoạn rất ngắn. Nếu desired replicas thay đổi bởi HPA, cảnh báo nên **so available với desired** thay vì cố định **2**.

Một expression so theo desired với labels phù hợp:

~~~promql
kube_deployment_spec_replicas{namespace="orders",deployment="orders-api"}
-
kube_deployment_status_replicas_available{namespace="orders",deployment="orders-api"}
> 0
~~~

Đây là **PromQL expression**, không phải ARM/Bicep/YAML alert rule hoàn chỉnh. Để triển khai trên Azure, cần tạo **Prometheus rule group** bằng Portal, Bicep/ARM hoặc API/CLI phù hợp, với evaluation interval, scope, condition, action group và quyền chính xác.

### Alert cho HTTP 5xx ratio

Một rule thực tế nên xét:

- Ngưỡng lỗi dựa theo SLO (ví dụ tỷ lệ 5xx vượt ngưỡng trong một thời gian).
- Minimum request volume để tránh báo động do một request trên hệ thống ít tải.
- Thời gian quan sát và **for duration** để chống noise.
- Độ trễ ingestion, scrape interval và thiếu series.
- Ai trực tiếp nhận cảnh báo, escalation và runbook.

Không chỉ đặt **error_ratio > 0**: một lỗi thoáng qua có thể làm một dịch vụ vẫn khỏe bị spam cảnh báo.

### Alert khi thiếu dữ liệu

**No data** không đồng nghĩa API healthy. Nếu collector chết hoặc scrape bị chặn, chart có thể trống trong khi ứng dụng gặp sự cố. Thiết kế thêm tín hiệu phát hiện **metrics absence**, scrape health, ingestion lag hoặc synthetic availability từ nguồn độc lập.

## 17. Recording rules và hiệu năng truy vấn

**Recording rule** tính trước kết quả một expression và lưu thành time series mới, giúp dashboard chạy query nặng nhanh hơn khi phù hợp.

Ví dụ ý tưởng:

~~~promql
sum by (namespace, deployment) (
  kube_deployment_status_replicas_available
)
~~~

Có thể ghi nhận thành một metric tổng hợp dùng lại, theo cú pháp/naming của rule group và chính sách tổ chức.

Tuy nhiên, recording rules **tạo thêm series**, có thể tăng chi phí và yêu cầu quản lý vòng đời. Không tạo một rule riêng cho mỗi Pod/customerId nếu số lượng đối tượng thay đổi liên tục. Ưu tiên các aggregation hữu ích cho SLO và dashboard truy cập thường xuyên.

### Lưu ý query range

Một dashboard có time range 30 ngày và refresh mỗi vài giây có thể làm truy vấn tốn tài nguyên hơn một dashboard 1 giờ refresh mỗi phút. Hãy:

- Đặt **time range** theo mục tiêu điều tra.
- Chọn **query step/min interval** hợp lý với scrape interval.
- Dùng recording rules cho biểu thức tốn kém khi cần.
- Tránh fan-out qua hàng triệu label values không cần thiết.
- Giới hạn dashboard variables vào các cluster/namespace cần theo dõi.

## 18. Cardinality: nguyên nhân tăng chi phí rất nhanh

Trong Prometheus, mỗi tổ hợp **metric name + label values** khác nhau tạo một time series riêng.

Giả sử metric:

~~~text
http_server_requests_seconds_count{
  method="GET",
  route="/orders/{id}",
  status="200",
  pod="orders-api-abc"
}
~~~

Nếu một label **user_id** có 100.000 giá trị và kết hợp với method, status, pod, số series có thể tăng rất mạnh.

### Ví dụ ước lượng

Giả sử:

- 10 API routes ổn định.
- 4 HTTP methods.
- 5 nhóm status.
- 10 Pod.

Số tổ hợp lý thuyết có thể tới:

~~~text
10 routes × 4 methods × 5 statuses × 10 pods
= 2.000 time series cho một metric family
~~~

Nếu thêm một label **customer_id** với 20.000 giá trị:

~~~text
2.000 × 20.000 = 40.000.000 series tiềm năng
~~~

Đây là ví dụ **upper-bound tổ hợp lý thuyết**, không có nghĩa tất cả tổ hợp chắc chắn xuất hiện. Nhưng nó cho thấy rủi ro tài chính/vận hành của label có cardinality cao.

### Nguyên tắc đặt labels

- Dùng labels có **tập giá trị hữu hạn và ổn định**: region, environment, namespace, service, method, status class.
- Với HTTP route, dùng **route template** như **/orders/{id}**, không dùng URL chứa mỗi ID.
- Không dùng **email, requestId, traceId, userId, sessionId, orderId** làm labels.
- Nếu cần định danh giao dịch, ghi **log/trace** với cơ chế bảo vệ dữ liệu thích hợp.
- Lọc/drop metrics không cần thiết từ lúc scrape khi khả năng collector hỗ trợ.
- Theo dõi series count/ingestion volume và đặt budget/alert cho chi phí.

## 19. Scrape interval, retention và mô hình chi phí

Trong mô hình metrics Prometheus, **scrape interval** quyết định tần suất thu thập sample từ exporter. Ví dụ:

~~~text
1.000 time series
Scrape mỗi 30 giây
=> 2 sample/phút/series
=> ~120.000 samples/giờ (ước lượng trước lọc/gap)
~~~

Giảm interval xuống **15 giây** có thể tăng gấp đôi số sample đối với cùng một tập series, trước khi xét filtering/aggregation. Khi chọn interval:

- Metrics cho alert nhạy thời gian có thể cần độ phân giải cao hơn.
- Metrics capacity dài hạn có thể đủ ở tần suất thấp hơn.
- Giới hạn collector, ingestion, latency và chi phí theo dịch vụ phải được xem xét.
- Retention của Managed Prometheus phụ thuộc gói/tính năng/giới hạn dịch vụ; không tự giả định dữ liệu giữ vô hạn.

### Các chi phí phải tính

| Thành phần | Chi phí/rủi ro |
|---|---|
| Managed Prometheus | Metrics ingestion và các thành phần tính giá theo mô hình hiện hành |
| Azure Monitor workspace | Lưu và truy vấn dữ liệu theo mức sử dụng/giới hạn dịch vụ |
| Azure Managed Grafana | Chi phí workspace/tier/instance và tính năng được dùng |
| Azure Monitor alerts | Alert rule evaluation, notifications và action groups theo chính sách giá |
| Container Insights/Log Analytics | Chi phí ingestion/retention **riêng** nếu bật |
| AKS collector | CPU/RAM trên node, có thể ảnh hưởng capacity của cluster |
| Network | Egress/private networking theo topology khi áp dụng |
| Application Insights | Telemetry và retention riêng nếu được bật |

Đừng áp dụng một giá cố định cho mọi region/tier. Dùng **Azure Pricing Calculator, Azure Monitor usage/cost analysis và Cost Management**. **Budget alert không tự dừng ingestion**; muốn khống chế chi phí phải điều chỉnh số series, scrape configs, tần suất và retention theo khả năng dịch vụ.

## 20. Bảo mật Managed Prometheus và Grafana

Metrics có thể chứa thông tin nội bộ:

- Tên cluster, node, namespace, service và endpoint.
- Số lượng kết nối, lưu lượng hoặc trạng thái triển khai.
- Label sai có thể tiết lộ khách hàng/username/internal URL.
- Một dashboard có thể vô tình phơi cấu trúc hệ thống nếu cấp Viewer quá rộng.

### Các kiểm soát cần có

1. **Microsoft Entra ID** và RBAC cho người dùng Grafana; Viewer/Editor/Admin tách biệt.
2. **Managed identity** cho Grafana truy vấn AMW; quyền đọc ở scope phù hợp.
3. **Least privilege** cho quản trị AMW, AKS và cấu hình collector.
4. **Endpoint metrics private** khi có thể; không public cổng 8080/Actuator chỉ để scrape.
5. **Network access** tới AMW/Grafana/ingestion endpoints theo khả năng sản phẩm và chính sách mạng.
6. **TLS, secret management** và audit khi sử dụng kết nối/tích hợp bổ sung.
7. **Không log access token** hoặc cấu hình datasource chứa credential.
8. **Data classification** đối với tên metric/labels, dashboard export và ảnh chụp màn hình.

### Multi-tenant và namespace isolation

**Namespace label không phải bảo mật theo tenant** trong AMW hoặc Grafana. Nếu một identity có quyền query toàn workspace, nó có thể thấy metrics từ nhiều namespaces/clusters tùy nguồn và quyền. Muốn cô lập nghiêm ngặt, cần thiết kế **workspace/data source/IAM boundary** và chính sách tổ chức phù hợp, không chỉ dựa vào biến dashboard **namespace**.

Không để nhóm A có thể tùy ý xóa/sửa dashboard cảnh báo quan trọng của nhóm B nếu mô hình folder/permissions có thể ngăn được.

## 21. Azure Monitor Prometheus và network private

Một AKS private cluster, một ACR private và một AMW là **ba bài toán mạng khác nhau**. Để Managed Prometheus hoạt động, collector trong AKS cần có đường gửi metrics tới endpoint ingestion của Azure Monitor theo mô hình được hỗ trợ.

Khi workload/cluster nằm trong VNet hạn chế egress:

- Kiểm tra DNS resolution và firewall/proxy cho các endpoint bắt buộc của Azure Monitor collector.
- Kiểm tra managed identity/service auth của addon theo cấu hình hỗ trợ.
- Khi dùng Azure Monitor Private Link Scope (AMPLS) hoặc private networking được hỗ trợ, cần thiết kế DNS/route cẩn thận.
- Đảm bảo probe từ metrics collector tới **/actuator/prometheus** không bị NetworkPolicy/namespace policy chặn.
- Tách lỗi **scrape in-cluster** khỏi lỗi **ingestion tới AMW** và lỗi **Grafana query AMW**.

~~~text
Java exporter (pod)
      |
      | HTTP scrape nội bộ
      v
ama-metrics collector
      |
      | Azure Monitor ingestion qua đường được hỗ trợ
      v
Azure Monitor workspace
      ^
      | Azure Monitor/Prometheus datasource API
      |
Azure Managed Grafana
~~~

Khi dashboard No data, xác định **điểm cuối đã thấy dữ liệu**: Java endpoint, collector, AMW query hay Grafana panel. Không vô hiệu hóa firewall toàn hệ thống chỉ để "kiểm tra".

## 22. Sự cố: dashboard "No data"

Một dashboard có thể trống dù Java API vẫn phục vụ. Chẩn đoán theo tầng:

| Tầng | Tín hiệu/cách kiểm tra | Nguyên nhân có thể |
|---|---|---|
| Dashboard | Time range, datasource, panel PromQL | Chọn sai datasource, metric name, namespace hoặc time range |
| Azure Managed Grafana | Người dùng login và datasource health | Vai trò Viewer/Admin hoặc Grafana managed identity chưa đủ |
| AMW | Query một metric cơ bản trực tiếp | Dữ liệu chưa được ingest, query sai hoặc quyền thiếu |
| Collector | ama-metrics Pods/logs và custom scrape config | Agent chưa chạy, lỗi config hoặc scrape targets không healthy |
| Exporter | curl /actuator/prometheus từ mạng được phép | App chưa expose Actuator, cổng/path sai, auth/network chặn |
| AKS | Pod/service readiness, network policies, node state | Workload không chạy, endpoints không có |

### Quy trình sáu bước

1. Trong Grafana, chọn time range **Last 1 hour** và đúng datasource; thử một metric Kubernetes đã xác minh tồn tại.
2. Kiểm tra Grafana identity có quyền **Monitoring Data Reader** với AMW.
3. Trên AMW, kiểm tra có metrics Kubernetes nào mới được ingest chưa.
4. Trên AKS, kiểm tra trạng thái **ama-metrics** và collector logs theo quyền hiện có.
5. Với Java metrics, thử endpoint trong cluster; xác nhận custom scrape config đã nhận.
6. Sau khi sửa, đợi chu kỳ scrape/ingestion và kiểm tra **sample timestamp** mới; ghi lại kết quả.

Không tăng thời gian refresh dashboard xuống 1 giây để sửa No data; việc đó thường chỉ làm tăng tải truy vấn.

## 23. Sự cố: chỉ có metrics node, không có JVM metrics

**Tình huống:** Azure Monitor workspace đã nhận container CPU và node metrics, Grafana dashboard Kubernetes hoạt động, nhưng truy vấn **jvm_memory_used_bytes** không có dữ liệu.

### Phân tích

Các metrics mặc định của collector có thể hoạt động bình thường, còn ứng dụng Java cần thêm instrumentation và custom scrape:

1. Java app có dependency **micrometer-registry-prometheus** và Actuator không?
2. **/actuator/prometheus** có hiển thị series **jvm_*** ở môi trường lab không?
3. Endpoint đang bind đúng port và có thể truy cập từ collector trong cluster không?
4. Có custom scrape hoặc annotation scraping thực sự được bật và cấu hình đúng namespace không?
5. Relabeling có vô tình drop job/metrics hay không?
6. Grafana query có dùng sai **job**, **pod** hoặc **cluster** labels không?

**Hướng sửa:** đảm bảo endpoint và cấu hình scrape đúng, kiểm tra collector logs, query raw metric trước rồi mới áp filter. Không chỉnh toàn bộ cluster-wide default scrape cho một ứng dụng nếu có thể dùng custom job hẹp trong namespace tương ứng.

## 24. Sự cố: dashboard báo CPU cao nhưng ứng dụng ổn định

**Tình huống:** Panel CPU của Pod tăng, nhưng p95 latency và tỷ lệ 5xx vẫn trong SLO.

Không suy diễn **CPU cao = outage**. Cần xem:

- CPU limit và dấu hiệu **throttling**, không chỉ CPU usage tuyệt đối.
- HPA có scale đúng không? Node pool có capacity không?
- JVM GC pause, heap và thread pool có bất thường không?
- Requests per second có tăng tương ứng không?
- CPU cao kéo dài bao lâu, thuộc workload nào, có batch nền không?

Một ứng dụng tận dụng CPU hiệu quả có thể dùng CPU cao trong giờ cao điểm mà không vi phạm SLO. Cảnh báo nên phản ánh **nguy cơ ảnh hưởng người dùng** và sự bão hòa có ý nghĩa, tránh gửi paging chỉ vì một đường biểu đồ vượt 70%.

## 25. Sự cố: cảnh báo biến mất khi metrics collector lỗi

**Tình huống:** Collector ngừng gửi dữ liệu. Rule **CPU > 90%** không còn đánh giá series mới; dashboard trống nhưng operator không nhận được cảnh báo CPU cao.

Nguyên nhân không phải CPU tự trở về bình thường, mà là **mất nguồn đo**.

### Giải pháp

- Thiết kế cảnh báo **absence/staleness** cho metrics quan trọng, theo khả năng rule evaluation.
- Dùng tín hiệu độc lập như **synthetic HTTP availability** hoặc health status từ Azure platform.
- Monitor trạng thái **ama-metrics pods** và pipeline ingestion.
- Xác nhận hành vi **NoData** của loại alert rule/datasource được dùng.
- Thiết lập runbook xử lý scrape/ingestion outage, tránh đánh đồng với ứng dụng khỏe.

Đây là nguyên tắc **monitor the monitoring**: hệ thống quan sát phải có cách phát hiện chính nó đang mất dữ liệu.

## 26. Diễn tập đọc metrics trên môi trường AKS lab

### Mục tiêu

Hoàn thành một luồng quan sát **không bắt buộc tạo cluster/AMW/Grafana mới**:

1. Xác định AKS cluster và AMW đã tồn tại.
2. Kiểm tra collector đang gửi Kubernetes metrics.
3. Mở Grafana bằng quyền Viewer/Editor phù hợp.
4. Viết ba PromQL queries và một dashboard.
5. Nếu có Java app lab, xác minh custom metrics và xử lý một sự cố giả định.

### Phần A: kiểm tra hạ tầng ở chế độ đọc

~~~bash
az login
az account set --subscription "<LAB_SUBSCRIPTION_ID>"

RG="<AKS_RESOURCE_GROUP>"
AKS="<EXISTING_AKS_CLUSTER>"

az aks show \
  --resource-group "$RG" \
  --name "$AKS" \
  --query "{name:name,location:location,azureMonitorProfile:azureMonitorProfile}" \
  --output json
~~~

Nếu bạn có quyền vào AKS:

~~~bash
az aks get-credentials --resource-group "$RG" --name "$AKS"
kubectl config current-context
kubectl get pods -n kube-system | grep ama-metrics
~~~

**Chỉ sử dụng cluster lab được giao**. Nếu metrics addon chưa bật, đừng tự bật trên cluster chung; ghi nhận cần phê duyệt vì đó là thay đổi có thể phát sinh chi phí.

### Phần B: mở Grafana/AMW

1. Trong Portal, mở Azure Managed Grafana workspace đã được cấp.
2. Đăng nhập bằng Entra ID với vai trò phù hợp.
3. Xác nhận datasource Managed Prometheus/Azure Monitor workspace.
4. Xem một dashboard Kubernetes có sẵn; kiểm tra time range, cluster và namespace.
5. Nếu không có dữ liệu, đối chiếu các tầng ở mục 22.

### Phần C: tạo ba panel PromQL

**Panel 1 — số node Ready**:

~~~promql
sum(kube_node_status_condition{condition="Ready",status="true"})
~~~

**Panel 2 — memory working set mỗi Pod ở namespace lab**:

~~~promql
sum by (pod) (
  container_memory_working_set_bytes{namespace="observability-demo",container!=""}
)
~~~

**Panel 3 — độ lệch replica desired và available**:

~~~promql
sum(
  kube_deployment_spec_replicas{namespace="observability-demo"}
)
-
sum(
  kube_deployment_status_replicas_available{namespace="observability-demo"}
)
~~~

Nếu namespace không tồn tại hoặc metric bị lọc, query có thể rỗng. Hãy chọn namespace có workload lab thực tế và kiểm tra labels trước khi dùng.

### Phần D: bài thực hành Java tùy chọn

Nếu nhóm đã có Java Spring Boot app lab:

1. Kiểm tra **micrometer-registry-prometheus** và **/actuator/prometheus**.
2. Xác minh custom scrape được cấu hình theo phương thức Managed Prometheus hỗ trợ.
3. Query **jvm_memory_used_bytes** và **http_server_requests_seconds_count** theo labels thật.
4. Thêm panel **RPS**, **JVM heap** và **readiness**.
5. Thay đổi **APP_MESSAGE** của app demo không tạo tải phá hoại; quan sát rollout và metrics.
6. Không public metrics endpoint hoặc tự tạo traffic gây vượt quota.

### Phần E: ghi lại kết quả

| Bằng chứng | Yêu cầu |
|---|---|
| AKS | Cluster, region, trạng thái metrics addon |
| AMW | Workspace ID, vùng, metric data source |
| Grafana | URL workspace, datasource, role của người dùng |
| Collector | Pod/collector status và thời điểm kiểm tra |
| Queries | Ba truy vấn PromQL, kết quả hoặc lý do No data |
| Java | Metric names, labels và xác nhận endpoint scrape nếu có |
| Alerts | Đề xuất ít nhất một rule gắn SLO/runbook |
| Security | Không lộ secret, không public exporter |
| Cost | Ước tính/quan sát metrics ingestion và Grafana cost |

Nếu chỉ có quyền Viewer, hãy hoàn thành phần **read-only** và mô tả dashboard mong muốn trên giấy; không cần nâng quyền để sửa shared dashboards.

## 27. Bài tập tình huống: rollout Java làm tăng 5xx

Một Deployment Java trong namespace **orders** vừa cập nhật. 10 phút sau, dashboard cho thấy:

~~~text
HTTP RPS         : 150 -> 160 requests/second
5xx ratio        : 0.2% -> 8.0%
p95 latency      : 200 ms -> 1700 ms
Available Pods   : 3 / 3
CPU usage        : không tăng đáng kể
DB pool waiting  : tăng mạnh
~~~

**Nhận xét:** đủ Pod Ready không đồng nghĩa nghiệp vụ đã khỏe. Các tín hiệu gợi ý API đang chờ database connections hoặc dependency, có thể do code thay đổi, connection pool config, DB overload hoặc một dịch vụ khác.

### Quy trình xử lý

1. Xác nhận time range, datasource và query 5xx/latency đang dùng đúng labels/release.
2. Kiểm tra deployment revision, thời điểm rollout và config đã thay đổi.
3. Đối chiếu **Java logs/traces**, DB pool metrics và database health.
4. Đánh giá rollback app nếu bản mới gây lỗi và tương thích dữ liệu cho phép.
5. Nếu cần rollback, quan sát biểu đồ 5xx/p95 sau hành động; không kết luận thành công chỉ vì kubectl rollout status hoàn tất.
6. Thêm alert rule có ngưỡng và for duration phù hợp; ghi RCA và regression test.

**Không giả định** lỗi thuộc Kubernetes node khi Pod đều Ready và CPU không bão hòa. Metrics giúp khoanh vùng, logs/traces giúp giải thích nguyên nhân.

## 28. Bài tập tình huống: Grafana No data sau thay đổi IAM

Một nhóm vừa siết RBAC. Người dùng vẫn đăng nhập Azure Managed Grafana và thấy dashboard folders, nhưng mọi panel Prometheus trả lỗi permission hoặc No data.

### Chẩn đoán

1. Xem datasource đang trỏ đúng AMW không.
2. Kiểm tra system-assigned/user-assigned **managed identity** mà Grafana đang dùng.
3. Kiểm tra role assignment **Monitoring Data Reader** hoặc role do tích hợp yêu cầu còn hiệu lực ở đúng AMW/scope không.
4. Kiểm tra Azure Activity Log về thay đổi IAM.
5. So với query AMW từ một chủ thể được phép để phân biệt mất dữ liệu và lỗi quyền.
6. Kiểm tra thời gian propagation của RBAC và metadata datasource.

**Không** cấp Owner/Contributor toàn subscription cho Grafana chỉ để thử. Khôi phục **quyền đọc tối thiểu ở scope cần thiết** rồi xác minh datasource hoạt động.

## 29. Checklist production cho AKS observability

- [ ] Có mục tiêu vận hành rõ: SLO, latency, error budget, capacity và bảo mật.
- [ ] Hiểu metrics/logs/traces khác nhau, tránh nghĩ Managed Prometheus thay toàn bộ logging.
- [ ] AMW và Azure Managed Grafana nằm trong region/subscription được cho phép.
- [ ] Managed metrics addon đã bật đúng cluster, collector healthy và có dữ liệu mới.
- [ ] Kubernetes default targets/metric keep-list đã được xác minh trên AMW.
- [ ] Java exporter có Actuator + Micrometer Prometheus và endpoint private.
- [ ] Custom scrape thực sự được cấu hình theo cơ chế addon hỗ trợ; annotation đơn thuần không bị nhầm thành cấu hình hoàn chỉnh.
- [ ] PromQL selectors dùng labels thật; dashboards phân biệt cluster/namespace/workload.
- [ ] Có panel về node readiness, replicas, CPU/memory, HTTP RPS/5xx/p95 và JVM.
- [ ] Có cảnh báo SLO/availability và cảnh báo **mất dữ liệu metrics**.
- [ ] Azure Monitor Prometheus alert rules có action group/on-call/runbook phù hợp.
- [ ] Grafana managed identity chỉ có quyền đọc AMW; người dùng có Viewer/Editor/Admin phù hợp.
- [ ] Không đặt PII/token/order ID trong metric labels.
- [ ] Scrape interval, metric retention, recording rules và series cardinality được kiểm soát.
- [ ] NetworkPolicy, DNS và private networking cho collector/AMW/Grafana được kiểm thử khi cần.
- [ ] Logs/traces được liên kết để đi từ metric anomaly tới root cause.
- [ ] Có dashboard ownership, versioning/provisioning và phương án khôi phục khi xóa nhầm.
- [ ] Có budget/Cost Management và người chịu trách nhiệm khi ingestion tăng.
- [ ] Đã diễn tập một ca lỗi ứng dụng và một ca monitoring pipeline No data.

## 30. Câu hỏi tự kiểm tra

1. Azure Monitor workspace khác Log Analytics workspace và Azure Managed Grafana workspace như thế nào?
2. Managed Prometheus có tự thu mọi Java application metrics chỉ vì AKS đã bật metrics addon không?
3. Vai trò của **ama-metrics** collector trong kiến trúc là gì?
4. Vì sao Azure Managed Grafana không phải nơi lưu metrics gốc?
5. Người dùng có Grafana Viewer nhưng dashboard No data: còn lớp quyền nào cần kiểm tra?
6. **Monitoring Data Reader** thường cần gán cho chủ thể nào khi kết nối Grafana–AMW?
7. Counter, gauge và histogram khác nhau thế nào? Khi nào dùng **rate()**?
8. Vì sao một PromQL query dùng label **job="java-api"** có thể trả rỗng dù metric tồn tại?
9. **label_values** trong Grafana variable có phải hàm PromQL chuẩn không?
10. Vì sao annotations **prometheus.io/scrape** trên Pod chưa bảo đảm Managed Prometheus đã scrape?
11. Spring Boot cần những dependency/configuration nào để mở **/actuator/prometheus**?
12. Cần điều kiện gì để tính p95 bằng **histogram_quantile**?
13. Khi Pod Ready nhưng HTTP 5xx tăng, cần xem metrics/logs nào?
14. Vì sao không đặt customerId/orderId vào labels của metric?
15. Nếu có 1.000 series và scrape 15 giây thay vì 30 giây, sample count thay đổi sơ bộ ra sao?
16. Grafana No data có chứng minh ứng dụng đã ngừng hoạt động không?
17. Cảnh báo nào giúp phát hiện collector ngừng gửi metrics?
18. Vì sao alert rules nên có time window, for duration và suppression/noise control?
19. Prometheus recording rules có thể làm tăng loại chi phí nào?
20. Phân biệt đường **Java exporter → collector**, **collector → AMW**, **Grafana → AMW** khi chẩn đoán network.
21. Một dashboard đa cluster phải có những labels/filters nào để tránh gộp nhầm dữ liệu?
22. Vì sao không nên cấp Grafana managed identity quyền Owner trên subscription?

## 31. Tài liệu tham khảo

- [Azure Monitor managed service for Prometheus](https://learn.microsoft.com/azure/azure-monitor/metrics/prometheus-metrics-overview) — kiến trúc và khả năng dịch vụ.
- [Monitor AKS with Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/containers/kubernetes-monitoring-enable) — bật thu thập metrics cho Kubernetes/AKS.
- [Default Prometheus metrics for AKS](https://learn.microsoft.com/azure/azure-monitor/containers/prometheus-metrics-scrape-default) — default targets và metric keep-lists.
- [Configure custom scraping for Managed Prometheus](https://learn.microsoft.com/azure/azure-monitor/containers/prometheus-metrics-scrape-configuration) — cách cấu hình collector.
- [Azure Managed Grafana overview](https://learn.microsoft.com/azure/managed-grafana/overview) — dịch vụ dashboard được Azure quản lý.
- [Connect Azure Managed Grafana to Azure Monitor workspace](https://learn.microsoft.com/azure/managed-grafana/how-to-connect-azure-monitor-workspace) — thiết lập datasource và permissions.
- [Prometheus rule groups in Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-prometheus) — recording/alert rules và Action Groups.
- [Prometheus query language (PromQL)](https://prometheus.io/docs/prometheus/latest/querying/basics/) — instant/range vectors, selectors và functions.
- [Prometheus best practices for instrumentation](https://prometheus.io/docs/practices/instrumentation/) — labels, metrics design và cardinality.
- [Spring Boot Actuator metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — Micrometer và Prometheus endpoint.
- [Kubernetes resource metrics pipeline](https://kubernetes.io/docs/tasks/debug/debug-cluster/resource-metrics-pipeline/) — phân biệt các đường metrics trong Kubernetes.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — ước tính chi phí giám sát và tài nguyên Azure.

**Kết luận:** Vận hành AKS hiệu quả cần nhìn thấy cả **hạ tầng Kubernetes** và **hành vi thật của ứng dụng**. Managed Prometheus thu và lưu metrics trong Azure Monitor workspace; Azure Managed Grafana trực quan hóa và giúp phân tích bằng PromQL. Muốn hệ thống hoạt động ổn định, hãy xác minh pipeline từ exporter đến collector, từ collector đến AMW rồi từ AMW tới Grafana; cấu hình đúng quyền, custom scrape, dashboard và cảnh báo. Sau cùng, kiểm soát cardinality, ingestion, retention và chi phí để hệ thống quan sát thực sự đáng tin, an toàn và bền vững.
