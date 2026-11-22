# Rightsizing tài nguyên dựa trên Azure Advisor và metric

## 1. Rightsizing là gì và vì sao cần thực hiện?

Trong Microsoft Azure, ứng dụng được xây dựng từ các thành phần như Virtual Machines (VM), App Service, Azure Kubernetes Service (AKS), Azure SQL Database, lưu trữ, mạng và dịch vụ giám sát. Khi bắt đầu dự án, nhóm thường chọn cấu hình dư tài nguyên để giảm nguy cơ thiếu năng lực. Sau vài tháng, mức sử dụng thật có thể thấp hơn dự tính; ngược lại, một số tài nguyên có CPU thấp nhưng lại bị nghẽn bộ nhớ, IOPS, network hoặc một giới hạn dịch vụ khác.

**Rightsizing** là quá trình điều chỉnh loại, kích thước, số lượng hoặc mô hình cấp phát tài nguyên theo **nhu cầu thực tế và yêu cầu độ tin cậy**, qua đó giảm lãng phí mà vẫn đáp ứng hiệu năng, khả năng mở rộng và mục tiêu phục vụ người dùng. Rightsizing không đồng nghĩa với việc luôn chọn SKU rẻ nhất.

Ví dụ: một API chạy trên VM có **4 vCPU, 16 GiB RAM**; CPU trung bình quanh 12%, nhưng đôi lúc lên 85%. Azure Advisor đưa ra khuyến nghị giảm kích thước. Nếu chỉ nhìn CPU trung bình, nhóm có thể chọn VM quá nhỏ và làm tăng timeout trong giờ cao điểm. Quyết định đúng phải đối chiếu CPU theo thời gian, bộ nhớ guest, I/O, network, tải thực, yêu cầu availability và chi phí sau khi đổi.

Trong chương **Quản lý chi phí** của hệ sinh thái Azure, rightsizing là một phần của FinOps: kết nối **dữ liệu chi phí** với **mức sử dụng và kết quả vận hành**, rồi kiểm chứng tiết kiệm sau thay đổi.

Sau bài học, bạn có thể:

- Phân biệt rightsizing với autoscaling, shutdown/scheduling và mua cam kết giá.
- Sử dụng khuyến nghị **Azure Advisor** làm đầu vào phân tích, kết hợp **Azure Monitor metrics**, VM insights và dữ liệu **Cost Management**.
- Chọn khoảng đo, metric và ngưỡng phù hợp cho VM, App Service, AKS, SQL và storage; nhận biết khi CPU thấp chưa có nghĩa dư tài nguyên.
- So sánh phương án giữ nguyên, giảm SKU hoặc chuyển mô hình vận hành, với ước tính tiết kiệm có điều kiện.
- Lập kế hoạch canary, giám sát, rollback và xác minh sau rightsizing mà không làm mất SLO của ứng dụng.

## 2. Rightsizing khác gì với các biện pháp tối ưu chi phí khác?

| Biện pháp | Tác động | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **Rightsizing** | Chọn lại kích thước/loại tài nguyên hoặc số instance phù hợp | Đổi VM 4 vCPU/16 GiB sang 2 vCPU/8 GiB khi dữ liệu chứng minh đủ | Cần đánh giá CPU, memory, I/O, network, quota và gián đoạn |
| **Autoscaling** | Tự thay đổi số instance/công suất theo quy tắc tải | App Service scale-out khi nhiều request, AKS HPA | Không tự bảo đảm SKU hiện tại phù hợp; giới hạn min/max có thể gây lãng phí |
| **Scheduling / stop** | Ngừng hoặc giảm tài nguyên ngoài giờ sử dụng | Tắt VM lab vào buổi tối | Không phù hợp hệ thống cần chạy liên tục; có khoản phí vẫn tồn tại |
| **Reserved Instances / Savings Plan** | Giảm đơn giá nhờ cam kết sử dụng theo điều kiện sản phẩm | Mua cam kết cho workload ổn định | Không xóa lãng phí công suất; có rủi ro cam kết sai phạm vi |
| **Tier / architecture optimization** | Đổi mô hình dịch vụ hay lưu trữ | SQL serverless cho workload phù hợp, đổi blob tier | Khác biệt tính năng, latency, chi phí giao dịch và vận hành |
| **Xóa tài nguyên không dùng** | Loại bỏ tài nguyên không còn nhu cầu | Dọn VM thử nghiệm đã hết vòng đời | Cần xác minh owner, dependency, dữ liệu và retention |

Rightsizing thường nên làm **trước** khi quyết định các cam kết giá dài hạn: nếu mua cam kết cho công suất không cần thiết, bạn có thể “giảm đơn giá” nhưng vẫn trả tiền cho phần dư thừa.

~~~mermaid
flowchart TD
    A["Inventory và chi phí thực"] --> B["Azure Advisor: danh sách ứng viên"]
    B --> C["Azure Monitor: tải và giới hạn"]
    C --> D["Đánh giá SLO, phụ thuộc, rủi ro"]
    D --> E{"Đủ bằng chứng?"}
    E -->|Không| F["Bổ sung telemetry / theo dõi thêm"]
    F --> C
    E -->|Có| G["So sánh SKU và tổng chi phí"]
    G --> H["Thử nghiệm trên canary / staging"]
    H --> I{"Sức khỏe đạt?"}
    I -->|Không| J["Rollback và phân tích"]
    I -->|Có| K["Rollout và đo tiết kiệm thực tế"]
~~~

## 3. Ba nguồn dữ liệu cần kết hợp

### 3.1 Azure Advisor: tìm ứng viên và giả thuyết

**Azure Advisor** cung cấp các khuyến nghị phù hợp với tài nguyên Azure và thông tin có sẵn cho dịch vụ, gồm nhóm **Cost** và các nhóm như Performance, Reliability, Security, Operational Excellence. Với quyền và tài nguyên phù hợp, bạn có thể thấy gợi ý về tài nguyên ít sử dụng, tắt tài nguyên nhàn rỗi hoặc đổi kích thước; phạm vi khuyến nghị, cách tính và điều kiện đủ **tùy loại tài nguyên và thời điểm**.

Trên Azure Portal, mở **Advisor → Cost**, lọc subscription/resource group hoặc loại resource rồi đọc từng recommendation. Nên lưu các thông tin:

- Resource ID, subscription, owner, environment, tag và loại tài nguyên.
- Problem/impact mà Advisor nêu và **đề xuất cụ thể** (resize, shutdown hoặc loại điều chỉnh khác).
- Mức tiết kiệm **ước tính**, giả định tính toán và thời điểm khuyến nghị được cập nhật.
- Liên kết tới metric/điều kiện đủ của recommendation (nếu giao diện cung cấp).
- Rủi ro SLA/SLO, hạn chế tính năng, chi phí liên quan và trạng thái quyết định.

**Advisor là hệ thống đưa ra tín hiệu để phân tích, không phải lệnh phải làm ngay.** Không có khuyến nghị không có nghĩa tài nguyên đã tối ưu; có khuyến nghị cũng không chứng minh thay đổi an toàn. Advisor có thể thiếu telemetry guest, không biết giờ đóng sổ hoặc hành vi traffic bất thường, và có thể không nhận diện mọi loại tài nguyên.

### 3.2 Azure Monitor metrics: chứng minh năng lực

**Azure Monitor Metrics** chứa metric nền tảng của tài nguyên và cho phép xem biểu đồ, chọn aggregation, thời gian và tạo cảnh báo. Với VM, một tín hiệu thường dùng là **Percentage CPU**; network, disk throughput, IOPS, latency, VM availability và host-related metrics phải chọn theo loại VM/disk đang dùng.

Những câu hỏi cần trả lời trước rightsizing:

1. CPU **trung bình, p95, mức cao nhất** là bao nhiêu, ở từng giờ/đợt cao điểm?
2. RAM còn bao nhiêu vào thời điểm tải cao, có swap/oom hoặc dấu hiệu memory pressure không?
3. Disk IOPS, throughput, latency, queue và giới hạn của **VM size lẫn disk SKU** có bị chạm không?
4. Network bandwidth, số kết nối, packet rate và giới hạn NIC/SKU có đủ?
5. Có workload batch, backup, indexing, ETL, kỳ tài chính hoặc sự kiện định kỳ chưa xuất hiện trong cửa sổ đo?
6. Khi một instance hỏng, instance còn lại có thể gánh tải không? Rightsizing có làm giảm headroom cần cho failover không?

**Lưu ý quan trọng:** các metric trong guest, đặc biệt **RAM đã dùng**, có thể cần Azure Monitor Agent/VM insights hoặc cơ chế thu thập được cấu hình riêng. Không mặc định “Azure Monitor luôn có RAM của mọi VM”. Nếu chưa có dữ liệu, phải bổ sung quan sát hoặc thực hiện thử nghiệm có kiểm soát.

### 3.3 Cost Management: đo giá trị kinh tế thật

**Microsoft Cost Management** cho biết chi phí theo subscription, resource, tag, service và khoảng thời gian (tùy quyền và loại billing account). Dữ liệu có thể đến sau thời điểm sử dụng, chịu ảnh hưởng bởi discount, reservation/savings plan, chính sách phân bổ và thuế/đơn vị tiền tệ.

Từ Cost Analysis/exports, thu thập **chi phí đang phân bổ**, compute và các khoản không biến mất khi giảm VM: disk, snapshot/backup, public IP, lưu lượng ra, load balancer, monitoring và license. Đối với tài nguyên có reservation/savings plan, phải phân biệt **phân bổ chi phí nội bộ** với **cash saving hoặc chi tiêu ròng thực giảm**.

Ví dụ giảm VM size nhưng vẫn trả phí disk và log ingestion như cũ sẽ tiết kiệm compute mà **không tiết kiệm tương ứng tổng chi phí** của giải pháp.

## 4. Quy trình chọn khoảng đo và chuẩn hóa baseline

### 4.1 Đủ dài để thấy mùa vụ và đỉnh tải

Không nên đưa ra quyết định từ một biểu đồ CPU vài giờ. Khoảng đo phù hợp phụ thuộc chu kỳ nghiệp vụ. Một quy tắc thực hành có thể là thu thập **ít nhất 30 ngày**, rồi mở rộng tới **60–90 ngày hoặc hơn** nếu có cao điểm theo tháng/quý, nhiều ngày lễ hoặc thay đổi thị trường; đây là **gợi ý phân tích**, không phải một ngưỡng mặc định của Advisor.

Cần xem cả:

- Giờ thấp điểm, giờ cao điểm, ngày làm việc, cuối tuần.
- Batch đêm, backup, report cuối tháng, peak theo chiến dịch.
- Lưu lượng request thực tế; nếu workload vừa bị gián đoạn hoặc đang bị throttle, mức CPU thấp có thể phản ánh hệ thống không nhận được đủ việc.
- Phần trăm missing metrics, sampling, số mẫu và thời điểm scale/triển khai.
- Dự báo tăng trưởng, những thay đổi release trong tương lai.

**Kết hợp percentiles và peak có ý nghĩa:** CPU average = 15% không loại trừ những đỉnh 95%; p95 của **các giá trị trung bình theo giờ** không giống p95 của tất cả mẫu phút, và cũng không bắt được burst vài giây. Đọc aggregation và resolution trước khi so sánh ngưỡng.

### 4.2 Baseline bắt buộc có SLI

Rightsizing có mục tiêu chi phí, nhưng kết quả phải bảo vệ **SLI/SLO** của người dùng. Với API trên VM:

| Nhóm | Baseline cần có | Dấu hiệu rủi ro |
| --- | --- | --- |
| Trải nghiệm | p95/p99 request latency, tỷ lệ HTTP/giao dịch thành công | Latency tăng, timeout, lỗi nghiệp vụ |
| CPU | Average, peak, theo peak business window | CPU saturation, throttling, ready queue |
| Memory guest | Used/available, swap, page faults, OOM | Memory pressure sau khi giảm RAM |
| Disk | Read/write throughput, IOPS, latency, queue, giới hạn tier | Chạm trần VM hoặc disk, latency tăng |
| Network | Bytes/s, kết nối, giới hạn NIC/VM, packet drops nếu có | Nghẽn truyền tải, mất kết nối |
| Availability | Replica healthy, khả năng failover, zone, capacity dự phòng | Không đủ instance khi lỗi một node |
| Chi phí | Chi phí compute/tháng, discount, phí kèm theo | Tiết kiệm trên giấy nhưng tổng bill không giảm |

Một mục tiêu hợp lý được viết cụ thể: “Giảm chi phí compute của API **ít nhất 15%** trong tháng đầy đủ đầu tiên, trong khi success SLI ≥ **99,9%**, p95 latency ≤ **300 ms** trong tập tải tiêu biểu, và vẫn chịu lỗi một instance.” Những số liệu này **chỉ là ví dụ**; tổ chức cần đặt theo nhu cầu thật.

## 5. Đọc các metric quan trọng theo loại tài nguyên

### 5.1 Azure Virtual Machines

CPU chỉ mô tả một trục của VM size. Một VM có CPU thấp vẫn có thể cần:

- **RAM** lớn cho cache hoặc JVM heap, khiến VM nhỏ hơn bị OOM.
- Nhiều disk hoặc mức IOPS/throughput cao; VM size nhỏ hơn có giới hạn tổng disk I/O thấp hơn.
- Network bandwidth cao, accelerated networking hoặc số NIC/connection mà size nhỏ không đáp ứng.
- Dòng CPU/architecture, tính năng GPU, local temporary disk hoặc kích thước local storage khác nhau.
- Năng lực chịu peak khi một node khác lỗi hoặc autoscale chưa kịp tăng.

Ví dụ các tên SKU trong họ Dsv5 như **Standard_D4s_v5** (4 vCPU, 16 GiB RAM) và **Standard_D2s_v5** (2 vCPU, 8 GiB RAM) giúp minh họa việc hạ một bậc; **không mặc định** các quota, disk/network limit, vùng và availability zone luôn tương đương. Phải kiểm tra SKU được phép sử dụng ở region/zone và quota thực tế.

### 5.2 App Service

Rightsizing App Service có thể là đổi **App Service plan SKU/tier**, giảm số instance hoặc chỉnh autoscale min/max. Cần kiểm tra:

- CPU, memory và HTTP response time theo từng instance và peak.
- Số app **chia sẻ cùng App Service plan**: giảm tier tác động đến tất cả app trên plan, không chỉ một app được chú ý.
- Tính năng phụ thuộc tier: deployment slots, scale-out, network features, availability/zone redundancy và giới hạn kết nối.
- Cold start, warm-up, health checks, môi trường staging và khả năng rollback.

**Không nên hạ App Service plan chỉ vì một web app ít truy cập** nếu plan còn chạy worker hoặc API khác. Mọi thay đổi tier phải kiểm tra feature support và ứng dụng cùng chia sẻ.

### 5.3 AKS

Ở AKS, cần phân biệt **pod resource requests/limits**, mức sử dụng thực, **node pool VM SKU**, số node và các cơ chế **HPA/VPA/Cluster Autoscaler** theo hỗ trợ và thiết kế. Một cluster có CPU trung bình thấp có thể do requests đặt quá cao làm Kubernetes không bin-pack hiệu quả, hoặc do phải giữ node dự phòng để đáp ứng SLO.

Trước khi giảm node size/count:

1. Xem CPU/memory **theo pod**, OOMKilled, throttling và requests so với usage ở tải cao điểm.
2. Xác nhận scheduler có đặt được workload lên node nhỏ hơn, xét **maxPods, taints, affinity, topology spread, daemonsets và system pods**.
3. Kiểm tra PodDisruptionBudget, maxUnavailable, autoscaler min/max và capacity khi upgrade hoặc node failure.
4. Thử trên node pool/canary, đo hiệu năng ingress, queue, DB connections và thời gian scale.

Giảm 20% node count chưa chắc giảm 20% bill nếu workload vẫn cần reserved capacity, node system khác SKU, disk, load balancer và lưu lượng.

### 5.4 Azure SQL Database và dữ liệu

Với Azure SQL, có thể đánh giá lựa chọn tier/compute dựa trên CPU, IO, data IO, log write, storage, connections, query duration, waits và tính năng của service tier. Các metric khác nhau giữa **DTU/vCore**, provisioned/serverless hoặc các loại cơ sở dữ liệu; hãy chọn metric đúng loại dịch vụ trong Azure Monitor.

CPU thấp nhưng query latency cao có thể do lock contention, I/O hoặc cấu hình query kém. Trước khi hạ SKU, xem execution plans, query performance, peak batch, khả năng scale và ảnh hưởng failover. Nếu chọn serverless cho workload phù hợp, phải tính minimum vCores, auto-pause/warm-up khi hỗ trợ và đặc điểm workload; không lấy một tỉ lệ CPU đơn lẻ làm bằng chứng tiết kiệm.

### 5.5 Storage và các dịch vụ khác

Rightsizing storage có thể là chọn tier dữ liệu, loại disk hoặc mức provisioned performance; cần cân đối **capacity, access frequency, operation cost, egress, rehydration/retrieval, latency, retention và durability**. Với Azure Managed Disks, hiệu năng phụ thuộc cả disk SKU/size lẫn VM size. Dung lượng sử dụng thấp không tự có nghĩa có thể hạ loại disk nếu ứng dụng cần IOPS.

Với message broker, cache hay database managed service khác, hãy xem metric đúng tài nguyên (throughput, queue length, memory, eviction, connections, errors) và giới hạn tính năng ở SKU mục tiêu.

## 6. Thực hành 1: Tìm đề xuất trong Azure Advisor

### 6.1 Kiểm tra thông tin và tải khuyến nghị

Với Azure CLI, chạy trong một phiên terminal đã đăng nhập và có quyền đọc subscription:

~~~bash
# Xác nhận đúng subscription trước khi phân tích.
az account show \
  --query "{subscription:id,name:name,tenantId:tenantId}" -o table

# Chọn subscription chính xác. Thay placeholder bằng ID thật.
az account set --subscription "<subscription-id>"

# Lấy toàn bộ recommendation để tự xem cấu trúc và phạm vi.
az advisor recommendation list --output json

# Có thể lọc nhóm Cost nếu phiên bản CLI/extension hỗ trợ tùy chọn này.
az advisor recommendation list --category Cost --output json
~~~

Các lệnh trên dùng để **đọc thông tin**, không tự resize. Trong Portal, vào **Azure Advisor → Cost** để đối chiếu recommendation, impact, resource, mức tiết kiệm ước tính và các trường giải thích. Hãy kiểm tra schema thực tế và tên option của phiên bản CLI trước khi tự động xử lý JSON.

**Không tự động chạy resize cho toàn bộ danh sách**. Trước tiên cần gán owner, loại môi trường, dữ liệu SLO, lịch vận hành và quyết định chấp nhận/từ chối từng khuyến nghị. Nếu quyết định hoãn hoặc loại bỏ recommendation, nên ghi **lý do và ngày xem lại** để không biến dismiss thành bỏ qua vĩnh viễn.

### 6.2 Lập danh sách ứng viên có thể hành động

Ví dụ bảng phân loại giả định:

| Resource | Advisor gợi ý | Quyết định sơ bộ | Lý do |
| --- | --- | --- | --- |
| VM `vm-orders-api-02` | Giảm size do sử dụng thấp | **Phân tích thêm** | Cần RAM guest, CPU peak và disk/network limit |
| VM `vm-lab-report` | Tắt/giảm tài nguyên nhàn rỗi | **Xem xét lịch stop** | Chỉ chạy giờ hành chính, cần kiểm tra batch |
| App Service plan `asp-orders` | Kiểm tra công suất/cost | **Chưa đổi** | Có 3 app dùng chung, thiếu metric theo app |
| SQL `sqldb-orders` | Xem lại tầng compute | **Chưa đổi** | Có peak cuối tháng; query latency tăng |

Recommendation ở bảng là **tình huống học tập**, không phải kết quả thực từ subscription nào. Trước quyết định cuối, cần dữ liệu quan sát tại thời điểm hiện tại.

## 7. Thực hành 2: Đọc VM và Azure Monitor Metrics

### 7.1 Xác nhận kích thước đang dùng

~~~bash
RG="rg-cost-lab"
VM="vm-orders-api-02"

# Đọc cấu hình VM hiện tại; không gây thay đổi tài nguyên.
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --query "{id:id,location:location,size:hardwareProfile.vmSize}" \
  -o json

VM_ID=$(az vm show --resource-group "$RG" --name "$VM" --query id -o tsv)
~~~

Đối chiếu VM ID với recommendation trong Advisor và resource tương ứng trong Cost Management. Hai VM tên gần giống nhưng thuộc subscription/resource group khác nhau có thể có cấu hình, tải và chính sách khác nhau.

### 7.2 Xem CPU trong nhiều cửa sổ

Chuẩn bị hai biến UTC theo cửa sổ mong muốn. Lệnh dưới đây lấy các bucket một giờ:

~~~bash
# Ví dụ: thay thời điểm bằng khoảng 30 ngày cần phân tích (ISO 8601 UTC).
START_UTC="2026-10-01T00:00:00Z"
END_UTC="2026-10-31T00:00:00Z"

az monitor metrics list \
  --resource "$VM_ID" \
  --metric "Percentage CPU" \
  --start-time "$START_UTC" \
  --end-time "$END_UTC" \
  --interval PT1H \
  --aggregation Average Maximum \
  --output json
~~~

Giá trị `Percentage CPU` và các aggregation khả dụng phụ thuộc namespace/tài nguyên; kiểm tra metric definitions nếu CLI trả lỗi. **Average theo giờ** cho biết nền tải, còn **Maximum theo giờ** giúp phát hiện đỉnh trong từng bucket. Không so sánh average theo giờ với maximum theo phút như thể chúng cùng độ phân giải.

Muốn phân tích peak 5 phút, có thể thay `--interval PT5M` khi metric, retention và giới hạn truy vấn cho phép; chia khoảng truy vấn thành nhiều phần nếu cần. Thời hạn lưu metric, granularity và giới hạn API thay đổi theo loại nguồn dữ liệu và cấu hình.

### 7.3 Thêm RAM, disk và network

Với VM:

- **RAM:** bật/đọc metric guest từ Azure Monitor Agent/VM insights hoặc cách đo đáng tin cậy khác. Kiểm tra peak `Available Memory`, swap/commit, memory pressure; chú ý metric name phụ thuộc cấu hình thu thập.
- **Disk:** xem IOPS, throughput, latency, queue và các metric giới hạn disk/VM có sẵn trong Azure Monitor. Nếu hạ size mà trần VM disk throughput thấp hơn mức đỉnh, CPU có thể vẫn đẹp nhưng tác vụ đọc/ghi chậm.
- **Network:** so sánh peak in/out, retry, packet drops và giới hạn VM/NIC, nhất là workload có ingress/egress lớn.
- **SLI ứng dụng:** xem response latency, error/timeout, queue depth từ Azure Monitor/Application Insights; CPU là tín hiệu chẩn đoán, không phải mục tiêu dịch vụ cuối cùng.

Tại cửa sổ traffic thấp, một bộ số liệu ví dụ có thể là CPU mean 11%, CPU p95 28%, CPU max 84%; RAM peak 7,5 GiB; disk throughput peak 80 MB/s. Hạ RAM từ 16 xuống 8 GiB khi guest peak đã 7,5 GiB **không an toàn** nếu chưa có headroom và kiểm thử, dù CPU ít dùng. Các con số chỉ để minh họa cách suy luận.

### 7.4 Ví dụ KQL khi đã xuất metrics vào Log Analytics

Mặc định không phải mọi platform metric đều tự nằm trong bảng `AzureMetrics` của Log Analytics. Ví dụ sau chỉ dùng được nếu workspace đã có bản ghi `AzureMetrics` tương ứng theo cấu hình export/diagnostic; kiểm tra tên trường và metric thật trước khi dùng:

~~~kusto
let vmId = tolower(
    "/subscriptions/<subscription-id>/resourceGroups/rg-cost-lab/providers/Microsoft.Compute/virtualMachines/vm-orders-api-02"
);
AzureMetrics
| where TimeGenerated >= ago(30d)
| where tolower(ResourceId) == vmId
| where MetricName == "Percentage CPU"
| summarize
    Samples = count(),
    AvgOfBucketAvgs = avg(Average),
    P95OfBucketAvgs = percentile(Average, 95),
    HighestBucketMaximum = max(Maximum)
| project Samples, AvgOfBucketAvgs, P95OfBucketAvgs, HighestBucketMaximum
~~~

`P95OfBucketAvgs` là p95 của **giá trị Average đã tổng hợp trong mỗi bucket**, không phải p95 của mọi mẫu CPU gốc. Nếu Sampling, export gap hoặc thiếu series khiến số liệu không đáng tin, dùng Metrics Explorer/API hoặc telemetry khác để kiểm chứng.

## 8. Ra quyết định: từ dữ liệu đến SKU ứng viên

### 8.1 Bảng ra quyết định cho VM giả định

Giả sử VM Standard_D4s_v5 (4 vCPU, 16 GiB) đang phục vụ API. Azure Advisor gợi ý điều chỉnh công suất. Sau 45 ngày theo dõi:

| Tiêu chí | Quan sát giả định | Đánh giá |
| --- | --- | --- |
| CPU median / p95 | 14% / 32% | Có dấu hiệu dư CPU trong phần lớn thời gian |
| CPU max trong cửa sổ peak | 86% trong một số đợt ngắn | Cần xem độ dài burst và tăng trưởng |
| RAM guest peak | 9,2 GiB | **Không thể** hạ thẳng sang VM 8 GiB mà không tối ưu memory |
| Disk IOPS/throughput peak | Dưới giới hạn size hiện tại | Cần đối chiếu giới hạn size nhỏ hơn |
| Network peak | Tăng đột biến lúc xuất báo cáo | Kiểm tra trần VM/NIC ứng viên |
| SLI ứng dụng | 99,95% thành công, p95 190 ms | Cần giữ ổn khi resize |
| Headroom failover | Một node còn lại phải gánh gấp đôi lưu lượng khi lỗi | Duy trì khả năng chịu lỗi một node |

Kết luận đúng lúc này: **chưa đủ điều kiện hạ từ Standard_D4s_v5 xuống Standard_D2s_v5**, vì RAM peak 9,2 GiB cao hơn RAM 8 GiB của SKU đích, chưa kể OS và headroom. Có thể tối ưu ứng dụng/bộ nhớ, điều chỉnh cache hoặc tìm SKU khác có tỷ lệ RAM/vCPU phù hợp, rồi đo lại.

Một quy trình tốt ưu tiên **nút thắt thực tế và tiêu chí SLO** hơn việc bám theo khuyến nghị “CPU low” một cách máy móc.

### 8.2 Kiểm tra SKU, quota và giới hạn dịch vụ

Ví dụ đọc SKU khả dụng trong region (kết quả còn phụ thuộc restriction, subscription, zone và quota):

~~~bash
az vm list-skus \
  --location southeastasia \
  --resource-type virtualMachines \
  --size Standard_D2s_v5 \
  --output table
~~~

Cần xem tài liệu SKU chi tiết về vCPU/RAM, temp disk, disk count, uncached/cached IOPS, storage throughput, network bandwidth, khả năng accelerated networking, architecture, zone và giới hạn. Sau đó xác nhận khả năng cấp phát thực tế, VM quota và constraints của availability set/VMSS hoặc cluster. Kết quả query SKU **không phải bảo đảm** lệnh resize thành công trong mọi lúc.

### 8.3 Khi nào chọn giảm SKU, giảm số instance hoặc đổi kiến trúc?

| Mẫu tải | Hướng đáng thử | Điều kiện |
| --- | --- | --- |
| Tải đều, CPU/memory/disk/network thấp với headroom rõ | Giảm một bậc SKU | Kiểm chứng size mục tiêu, SLO và failover |
| Tải dao động mạnh, nhiều thời gian nhàn rỗi | Autoscale hoặc khả năng serverless phù hợp | Tốc độ scale, cold start, quota và cost |
| Nhiều instance hoạt động rất thấp | Giảm min replicas/node count có kiểm soát | Vẫn đảm bảo HA, quorum, peak và maintenance capacity |
| VM dev chỉ chạy theo giờ | Schedule stop/start hoặc automation | Không ảnh hưởng batch/owner; kiểm tra phí disk/IP |
| CPU thấp nhưng RAM cao | SKU memory-optimized hoặc tối ưu cache/heap | Đủ RAM và giới hạn disk/network; tính lại cost |
| IOPS/latency là nút thắt | Tối ưu disk tier, caching hoặc kiến trúc IO | Không hạ VM làm giảm IOPS/throughput cần dùng |
| Có cam kết Reservation/Savings Plan | Xem tác động hiệu lực cam kết trước khi resize | Tránh phí cam kết vẫn phải trả trong thời hạn |

## 9. Tính tiết kiệm: phân biệt ước tính và chi phí thực

### 9.1 Công thức cơ bản

Với workload tính theo giờ:

\[
\mathrm{SavingsMonth}_{compute}
=(\mathrm{PriceOldHourly}-\mathrm{PriceNewHourly})
\times \mathrm{HoursUsed}\times \mathrm{InstanceCount}.
\]

Ví dụ **giá hoàn toàn giả định**, dùng để học phép tính chứ không phải bảng giá Azure: một VM cũ có giá compute hiệu dụng **0,20 USD/giờ**, VM mới **0,10 USD/giờ**, chạy **730 giờ/tháng**:

\[
(0{,}20-0{,}10)\times730=73\ \text{USD/tháng cho một VM}.
\]

Nếu có **5 VM** đáp ứng cùng điều kiện:

\[
73\times5=365\ \text{USD/tháng};
\qquad 365\times12=4\,380\ \text{USD/năm (ước tính)}.
\]

Không suy ra kết quả đó là **giảm 50% toàn bộ chi phí ứng dụng**. Nó chỉ mô tả chênh lệch compute giả định khi cùng số giờ chạy và không có yếu tố giá khác. Giá thực phụ thuộc region, OS/license, chế độ mua, discount, reservation, savings plan, thuế, tiền tệ, vùng khả dụng và thời điểm.

### 9.2 Tính tổng chi phí sở hữu (TCO) theo thay đổi

Một bảng kiểm tra trước khi ghi nhận savings:

| Khoản mục | Có thay đổi khi giảm VM size? | Ghi chú |
| --- | --- | --- |
| Compute theo giờ | Thường có | Tùy SKU, purchasing model và cam kết |
| Disk được cấp phát | Thường **không** | Dung lượng/tier disk giữ nguyên nếu không đổi disk |
| Snapshot/backup | Có thể không | Theo retention và dữ liệu |
| Network egress/load balancer | Chưa chắc | Tính theo lưu lượng và loại tài nguyên |
| Log ingestion/monitoring | Có thể không | Theo volume logs/metrics và retention |
| License/OS | Phụ thuộc SKU, licensing | Kiểm tra license benefit và điều kiện phí |
| Reserved capacity/savings plan | Cần đánh giá riêng | Hiệu ứng chi phí thực/khấu hao có thể khác giá PAYG |
| Công sức triển khai, kiểm thử, rủi ro | Chi phí vận hành một lần và liên tục | Có thể làm savings ngắn hạn kém hấp dẫn |

**Payback period** giúp quyết định ưu tiên:

\[
\mathrm{PaybackMonths}=
\frac{\mathrm{OneTimeChangeCost}}
{\mathrm{MonthlyNetSavings}}.
\]

Giả sử cần **600 USD** chi phí nhân sự/kiểm thử để thay đổi, tiết kiệm ròng dự kiến **150 USD/tháng**: hoàn vốn sau **4 tháng**, nếu hiệu năng và mô hình giá vẫn giữ nguyên. Cần đánh giá cả rủi ro downtime; lợi ích tài chính không hợp thức hóa giảm availability vượt cam kết.

### 9.3 Chốt số liệu sau một kỳ thanh toán

Sau triển khai, so sánh Cost Management trước/sau theo **cùng scope, tag, charge model và độ dài kỳ**. Tách tác động từ tăng/giảm traffic, thay đổi SKU khác, giá dịch vụ, reservation, exchange rate và charge mới. Với mô hình dùng nhiều resource chung, nên tính savings theo resource/charge type thay vì chỉ nhìn tổng subscription.

Nếu không thể chứng minh tiết kiệm vì các yếu tố phân bổ, kết luận là **chưa đo được savings ròng**, không tự lấy con số Advisor ước tính làm actual saving.

## 10. Kế hoạch triển khai an toàn và rollback

Rightsizing VM hoặc App Service có thể gây restart, downtime hoặc mất headroom. Trên môi trường production, cần change record và maintenance window phù hợp:

1. **Preflight:** xác nhận owner, scope, SKU cũ/mới, quota, dependency, backup, giám sát, quyền RBAC và thời điểm ít ảnh hưởng.
2. **Khóa baseline:** lưu SLI success/latency, CPU/RAM/disk/network, chi phí và lượng traffic theo version.
3. **Thử nhỏ:** giảm size ở một instance/canary hoặc một môi trường staging tương đồng. Nếu chỉ có **một VM** mà không có dự phòng, phải công bố rủi ro gián đoạn và có kế hoạch restore.
4. **Giữ khả năng rollback:** chốt SKU gốc, lưu cấu hình/boot/extension/OS state, kiểm tra khả năng quay lại size cũ và capacity/quota; backup dữ liệu khi cần.
5. **Giám sát:** kiểm tra readiness, SLI, CPU/memory pressure, disk latency, network throughput và queue ít nhất qua một peak có đại diện.
6. **Quyết định:** nếu health/SLO suy giảm hoặc capacity dự phòng không đủ, rollback hoặc dừng mở rộng; khi đạt mới rollout từng đợt.
7. **Hậu kiểm:** sau một kỳ tải đủ đại diện, xác minh actual cost và recommendation mới; cập nhật inventory, ngân sách và runbook.

### 10.1 Lệnh resize VM — chỉ dùng khi đã phê duyệt

Lệnh minh họa dưới đây **làm thay đổi VM thật**. Nó có thể yêu cầu restart/deallocation, gây downtime, làm thay đổi khả năng cấp phát hoặc cấu hình liên quan tùy VM/size; không chạy chỉ để “thử xem có tiết kiệm không” trên production.

~~~bash
# Chỉ minh họa trong kế hoạch đã duyệt:
az vm resize \
  --resource-group rg-cost-lab \
  --name vm-orders-api-02 \
  --size Standard_D2s_v5

# Kiểm tra sau thay đổi:
az vm show \
  --resource-group rg-cost-lab \
  --name vm-orders-api-02 \
  --query "{size:hardwareProfile.vmSize,provisioningState:provisioningState}" \
  -o json
~~~

Không cho rằng VM báo `Succeeded` đồng nghĩa ứng dụng healthy. Phải thử request đầu cuối, theo dõi guest memory, disk/network và workload trong các thời điểm cao điểm. Nếu rollback, cần xác nhận SKU cũ còn khả dụng và lệnh resize về SKU trước có thể thực hiện theo quy trình ứng cứu.

### 10.2 Lấy SLI làm điều kiện rollback

Ví dụ quy định trước khi đổi:

| Chỉ tiêu | Baseline | Điều kiện phải dừng/rollback (ví dụ) |
| --- | --- | --- |
| Success rate API | ≥ 99,9% | Dưới 99,5% trong cửa sổ đánh giá và đủ số request |
| p95 latency | 180 ms | Trên 300 ms trong 10 phút dưới cùng kiểu tải |
| RAM guest | Peak dưới ngưỡng an toàn | Swap/OOM hoặc available memory xuống dưới headroom đã duyệt |
| Disk I/O | Có headroom rõ | IO latency cao kéo dài hoặc disk/VM throttling |
| Network | Thông lượng còn dự phòng | Packet drops/connection timeout tăng bất thường |
| Availability | Chịu được một instance lỗi | Không đủ capacity cho tình huống failover mục tiêu |

Các ngưỡng mang tính **minh họa**, cần chốt từ SLO và baseline thật. Việc metric bị thiếu không thể tự coi là PASS; nếu hệ thống đo mất tín hiệu đúng lúc giảm SKU, cần xác minh bằng dữ liệu từ các tầng khác.

## 11. Những sai lầm thường gặp

| Nhận định hoặc hành động sai | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “CPU trung bình dưới 20% nên giảm VM 50%” | Peak, RAM, disk/network và failover có thể là giới hạn | Xem percentile, maxima, guest memory, workload cycles |
| “Advisor đề xuất thì cứ áp ngay” | Advisor không biết đầy đủ mục tiêu nghiệp vụ và mọi dependency | Review bởi owner, kiểm chứng metric và thử canary |
| “Không thấy đề xuất nghĩa là tối ưu rồi” | Không phải mọi tài nguyên/loại lãng phí đều có recommendation | Inventory, Cost Management, Azure Monitor, audit thủ công |
| “Giảm một bậc SKU luôn tiết kiệm 50%” | Giá khác theo SKU/region/discount và phí ngoài compute | Tính actual rate và chi phí ròng |
| “RAM platform metrics đủ cho mọi VM” | Guest memory có thể chưa thu thập | Cấu hình VM insights/AMA hoặc nguồn đáng tin |
| “Đổi VM trong VMSS ngay lập tức không ảnh hưởng” | Rolling policy, availability, max surge và health có giới hạn | Test node/canary, capacity và rollback |
| “Tắt VM đồng nghĩa hết mọi phí” | Disk, backup, IP và các tài nguyên khác vẫn tính phí; stop trong guest có thể chưa deallocate | Xem billing và trạng thái deallocated |
| “Giảm node AKS theo CPU trung bình” | Requests, PDB, DaemonSet, peak và min nodes có thể buộc giữ capacity | Phân tích scheduler/pods và dự phòng |
| “Chỉ cần 24 giờ metric” | Không thấy cuối tuần, ETL, tháng/quý, sự kiện hiếm | Đo đủ chu kỳ kinh doanh, ghi missing data |
| “Giảm chi phí thành công là xong” | Có thể làm xấu latency, error rate, RTO/RPO | Đánh giá SLO và reliability sau thay đổi |

## 12. Checklist quyền sở hữu và hồ sơ rightsizing

Một quyết định rightsizing có thể được ghi thành một bảng ngắn:

| Trường | Cần ghi |
| --- | --- |
| Resource / owner | Resource ID, subscription, RG, service, environment, owner |
| Advisor | Recommendation ID/nội dung, thời điểm, mức ước tính và giả định |
| Khoảng dữ liệu | 30/60/90 ngày, peak events, sampling/missing data |
| Utilization | CPU, memory guest, disk IOPS/throughput/latency, network, usage theo giờ |
| User impact | SLI/SLO hiện tại, critical path, traffic peak, HA/failover |
| Phương án | SKU cũ/mới, scale policy, quota, dependency và giới hạn tính năng |
| Ước tính chi phí | Compute, storage, discounts, commitments, monitoring, công sức thay đổi |
| Gate | Người duyệt, thử canary, ngưỡng stop, rollback và kế hoạch phục hồi |
| Sau triển khai | Metric thực tế, errors/latency, chi phí kỳ tiếp theo, kết luận |
| Lịch đánh giá lại | Owner và thời điểm review khi nhu cầu tải thay đổi |

Tài liệu phải có **đầu vào đo được và phương pháp xác minh sau thay đổi**. Rightsizing không phải một chiến dịch một lần; tài nguyên sẽ tiếp tục thay đổi khi sản phẩm, khách hàng và mô hình tính phí phát triển.

## 13. Bài tập vận dụng và tự kiểm tra

### Bài tập 1: Vì sao recommendation chưa đủ?

Azure Advisor nhận xét một VM có CPU trung bình rất thấp và gợi ý giảm size. Metric 45 ngày cho thấy CPU p95 25%, nhưng RAM peak 9,2 GiB và SKU mục tiêu chỉ có 8 GiB; disk I/O có đỉnh lớn khi chạy báo cáo.

**Yêu cầu:** Có nên hạ size ngay không? Cần bổ sung dữ liệu nào?

**Gợi ý đáp án:** **Chưa nên.** RAM peak đã vượt dung lượng SKU đích, dễ dẫn tới memory pressure hoặc OOM. Cần xem guest memory theo peak, disk IOPS/throughput/latency, network, SLO, kỳ báo cáo, capacity khi failover và quota. Có thể tối ưu cache/heap hoặc chọn SKU có RAM lớn hơn trên mỗi vCPU rồi đo thử.

### Bài tập 2: Tính savings có điều kiện

Giá compute **giả định**: VM cũ 0,24 USD/giờ, VM mới 0,16 USD/giờ, 8 instance chạy 720 giờ/tháng; không thay đổi số instance. Chi phí ổ đĩa/backup và monitoring giữ nguyên.

**Lời giải:**

\[
(0{,}24-0{,}16)\times8\times720
=460{,}8\ \text{USD/tháng, thuộc riêng compute}.
\]

Nếu phát sinh thêm 80 USD/tháng phí dịch vụ khác do kiến trúc mới, savings ròng còn **380,8 USD/tháng** trước khi xét discount/cam kết và chi phí thay đổi. Khi compute nằm trong reservation, số tiền thực trả giảm có thể khác kết quả giá theo giờ giả định.

### Bài tập 3: Chọn kế hoạch rollout

Một API có 4 VM ở hai availability zones, yêu cầu duy trì phục vụ khi một VM bị lỗi. Nhóm muốn hạ size toàn bộ 4 VM trong một đêm vì biểu đồ CPU trung bình đẹp.

**Gợi ý đáp án:** Cần xác minh **capacity N−1** trên VM nhỏ hơn, dữ liệu RAM/disk/network ở giờ cao điểm, loại AZ/quota, khả năng rolling change và SLO. Thực hiện một VM canary, kiểm tra app/lưu lượng, rồi rollout lần lượt trong giới hạn min healthy instance; giữ kế hoạch rollback và chỉ mở rộng khi số liệu ổn. Nếu không đủ capacity N−1, cần thay đổi quy mô/kiến trúc trước.

### Câu hỏi tự kiểm tra

1. Rightsizing khác autoscaling và reservation/savings plan ở điểm nào?
2. Vì sao Azure Advisor chỉ là điểm bắt đầu của quyết định tối ưu?
3. CPU trung bình thấp nhưng p95 latency cao có thể gợi ý các nút thắt nào?
4. Metric nào của VM cần thu thập thêm nếu Azure Monitor không có sẵn dữ liệu guest RAM?
5. Vì sao giảm VM size cần kiểm tra cả giới hạn IOPS/network của VM và disk?
6. Khi nào cần quan sát 60–90 ngày thay vì 7 ngày?
7. Khi thay đổi App Service plan, vì sao phải kiểm tra tất cả ứng dụng chia sẻ plan?
8. Với AKS, vì sao mức CPU tổng thể thấp chưa chắc cho phép giảm node?
9. Làm sao phân biệt estimated Advisor savings và actual net savings?
10. Những điều kiện nào khiến bạn dừng hoặc rollback một thử nghiệm rightsizing?

**Kết quả cần đạt:** Bạn có thể chọn một ứng viên từ **Azure Advisor**, thu thập **Azure Monitor metrics** cùng SLI của ứng dụng, đánh giá **CPU, RAM, I/O, network và khả năng dự phòng**, tính tiết kiệm có điều kiện rồi triển khai thử an toàn. Quyết định chỉ thực sự có giá trị khi **chi phí giảm được xác nhận** và **hiệu năng, độ tin cậy vẫn đạt mục tiêu**.
