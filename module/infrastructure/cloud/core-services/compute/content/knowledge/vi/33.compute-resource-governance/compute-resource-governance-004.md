# Quản lý quota và lập kế hoạch capacity theo tăng trưởng

Quota và capacity là hai ràng buộc khác nhau nhưng thường bị nhầm lẫn khi mở rộng hạ tầng cloud. Capacity cho biết hệ thống có bao nhiêu tài nguyên thực sự có thể sử dụng để chạy workload; quota đặt giới hạn mức tài nguyên hoặc tốc độ sử dụng mà một account, project, subscription, region hay service được phép yêu cầu. Một tổ chức có thể còn quota nhưng provider không còn capacity phù hợp ở zone hoặc instance family mong muốn. Ngược lại, region có nhiều capacity nhưng workload vẫn không triển khai được vì quota vCPU, GPU, địa chỉ IP hoặc số load balancer đã chạm trần.

Khi workload tăng trưởng, đội ngũ cần dự báo nhu cầu theo thời gian, xác định tài nguyên nào sẽ chạm quota trước, dành headroom cho peak và sự cố, rồi gửi yêu cầu tăng quota đủ sớm. Kế hoạch tốt kết hợp dữ liệu sử dụng thực tế, forecast, lịch phát hành sản phẩm, seasonality, mục tiêu availability và thời gian xử lý yêu cầu của cloud provider. Nó cũng cần gắn với ngân sách, bảo mật, ownership và quy trình phê duyệt.

Trong module CLOUD_CORE_SERVICES_COMPUTE, bài học kết nối lựa chọn VM, container, Kubernetes, serverless, CPU, bộ nhớ, mạng và storage với quản trị giới hạn tài nguyên. Trọng tâm là biến tăng trưởng workload thành kế hoạch quota và capacity có thể kiểm chứng, theo dõi và điều chỉnh.

Sau bài học, bạn có thể:

- Phân biệt quota, capacity, allocation, reservation, usage và rate limit.
- Phân loại quota theo scope, region, service, resource và đơn vị đo.
- Xác định các quota có thể chặn triển khai VM, GPU, network, storage, Kubernetes và serverless.
- Dự báo nhu cầu theo xu hướng, mùa vụ, peak, kế hoạch sản phẩm và kịch bản tăng trưởng.
- Tính headroom, capacity cho N+1, quota runway và thời điểm cần gửi yêu cầu tăng quota.
- Lập kế hoạch capacity cho nhiều account, subscription, project và region.
- Thiết kế quy trình quota request, approval, monitoring, alert và escalation.
- Kết hợp autoscaling, reservation, fallback và budget guardrail để tăng trưởng có kiểm soát.

## 1. Quota, capacity và các khái niệm liên quan

### Quota

Quota là giới hạn do provider, platform hoặc tổ chức áp dụng cho một tài nguyên hay hành vi. Quota có thể là số lượng resource tối đa, tổng vCPU, dung lượng, số request trong một khoảng thời gian hoặc số kết nối đồng thời.

Ví dụ:

- Tổng số vCPU được phép chạy trong một region.
- Số GPU được phép cấp trong một project.
- Số public IP hoặc load balancer tối đa.
- Dung lượng persistent disk hoặc số volume.
- Số function invocation đồng thời.
- Số API request mỗi giây hoặc mỗi ngày.
- Số Pod, CPU request hoặc memory request trong một Kubernetes namespace.

Quota thường là giới hạn quản trị và bảo vệ nền tảng. Việc nâng quota không đồng nghĩa provider cam kết có đủ capacity vật lý tại mọi zone hoặc thời điểm.

### Capacity

Capacity là năng lực tài nguyên có thể dùng để xử lý workload. Capacity có thể được nhìn ở nhiều lớp:

- **Provider capacity:** tài nguyên vật lý/ảo provider có thể cấp trong một region, zone hoặc instance family.
- **Account capacity:** tài nguyên nằm trong phạm vi quota và chính sách account.
- **Cluster capacity:** CPU, memory, storage, network và accelerator mà cluster có thể phân bổ.
- **Workload capacity:** throughput hoặc số request/job mà hệ thống xử lý được trong giới hạn SLO.
- **Dependency capacity:** năng lực database, queue, API, NAT, storage hoặc dịch vụ phụ thuộc.

Capacity hữu dụng bị giới hạn bởi điểm nghẽn nhỏ nhất trong chuỗi. Ví dụ có 500 vCPU quota nhưng chỉ có 120 vCPU khả dụng trong node pool do thiếu GPU-compatible instance hoặc zone capacity.

### Allocation, reservation và usage

- **Allocation:** phần quota hoặc capacity đã được phân bổ cho project, team, namespace hoặc workload.
- **Reservation:** capacity được giữ trước theo cơ chế của provider hoặc platform; reservation có thể có phí hoặc điều kiện sử dụng.
- **Usage:** tài nguyên đang dùng tại thời điểm đo hoặc mức sử dụng trong kỳ.
- **Limit:** giới hạn runtime của một workload hoặc container; khác với quota account.
- **Rate limit:** giới hạn tốc độ hành động, ví dụ 100 request/second, thường có cửa sổ thời gian hoặc token bucket.

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Quota | Được phép yêu cầu tối đa bao nhiêu? | 200 vCPU trong một region |
| Capacity | Có thể cấp/chạy được bao nhiêu? | 150 vCPU phù hợp còn khả dụng |
| Allocation | Phần nào được giao cho team? | Team A có 80 vCPU budget |
| Reservation | Có bao nhiêu capacity được giữ trước? | 32 vCPU reservation trong zone |
| Usage | Đang dùng bao nhiêu? | 95 vCPU đang chạy |
| Limit | Một workload được dùng tối đa bao nhiêu? | Container memory limit 2 GiB |
| Rate limit | Được phép thực hiện bao nhiêu hành động mỗi thời gian? | 500 API call/minute |

## 2. Vì sao quota trở thành rủi ro khi workload tăng trưởng?

Một workload có thể hoạt động bình thường trong nhiều tháng rồi đột ngột không scale được khi đạt ngưỡng. Các triệu chứng thường gặp:

- VM mới không tạo được dù autoscaler yêu cầu thêm node.
- GPU job nằm Pending vì quota accelerator đã hết.
- Function bị throttling khi concurrency chạm giới hạn.
- Kubernetes Pod không được tạo vì ResourceQuota trong namespace.
- Load balancer hoặc public IP mới không thể provision.
- API automation nhận lỗi quota/rate limit khi triển khai hàng loạt.
- Storage expansion thất bại vì quota dung lượng hoặc số volume.
- Môi trường DR không thể mở rộng khi region chính gặp sự cố.

Quota thường bị phát hiện muộn vì monitoring chỉ theo dõi CPU utilization và memory usage, không theo dõi quota consumption. Một cluster có CPU utilization thấp vẫn có thể hết quota nếu nhiều instance đang tồn tại nhưng idle, hoặc quota đã bị account khác dùng.

### Quota là một phần của production readiness

Trước một chiến dịch lớn, migration, launch hoặc diễn tập DR, cần kiểm tra cả:

1. Nhu cầu peak dự kiến.
2. Quota hiện tại và mức đã sử dụng.
3. Capacity provider ở region/zone cần dùng.
4. Reservation/commitment và quota scope.
5. Thời gian xử lý quota increase.
6. Fallback nếu quota hoặc capacity không được cấp.
7. Budget và quyền phê duyệt.

Không nên đợi đến khi autoscaler báo lỗi mới gửi quota request.

## 3. Phân loại quota theo scope

Quota có thể được áp dụng ở nhiều phạm vi. Hiểu đúng scope giúp tránh gửi yêu cầu sai nơi hoặc dự báo thiếu.

| Scope | Phạm vi giới hạn | Ví dụ |
|---|---|---|
| Organization/tenant | Toàn tổ chức hoặc tenant | Tổng subscription, tổng spending hoặc policy cap |
| Account/project/subscription | Một account hoặc project | Tổng vCPU, số VM, GPU |
| Region | Từng region | vCPU regional quota, public IP |
| Availability zone | Một zone hoặc fault domain | Capacity/reservation theo zone |
| Service | Một dịch vụ cụ thể | Serverless concurrency, database instances |
| Resource family | Nhóm loại tài nguyên | GPU family, compute-optimized vCPU |
| Namespace/cluster | Phạm vi Kubernetes/platform | CPU/memory ResourceQuota |
| Principal/API client | Một identity hoặc client | API requests per minute |
| Resource instance | Một resource cụ thể | Connection limit, disk IOPS hoặc throughput |

Quota có thể có cả scope tổng và scope con. Ví dụ tổng vCPU region là 300, trong đó instance family A có quota 120 và GPU family B có quota 32. Nâng tổng vCPU lên 500 không nhất thiết tự nâng quota family A hoặc GPU B.

### Kiểm tra quota inheritance

Một số nền tảng có quota mặc định ở organization và quota riêng ở account/project. Policy nội bộ cũng có thể giới hạn thấp hơn quota provider. Effective limit là giới hạn nhỏ nhất đang áp dụng trong chuỗi.

Ví dụ:

- Provider quota: 300 vCPU.
- Organization allocation: 220 vCPU.
- Project allocation: 120 vCPU.
- Workload budget: 80 vCPU.

Workload không thể tự dùng 300 vCPU; giới hạn thực tế của workload là 80 vCPU theo allocation hiện tại.

## 4. Phân loại quota theo tài nguyên

Quota compute thường liên quan đến nhiều loại tài nguyên cùng lúc.

| Nhóm | Ví dụ quota | Rủi ro khi chạm ngưỡng |
|---|---|---|
| CPU/VM | vCPU tổng, VM count, instance family | Không scale node/VM |
| GPU/accelerator | GPU count, accelerator family | Job ML/HPC không được schedule |
| Memory/compute shape | Số VM memory-optimized hoặc RAM tổng theo sản phẩm | Thiếu node phù hợp workload |
| Storage | Disk count, total GB, snapshots, IOPS/throughput | Không tạo/mở rộng volume hoặc backup |
| Network | VPC/VNet, subnet, IP, ENI/NIC, route, NAT, load balancer | Không tạo network path hoặc scale interface |
| Serverless | Concurrent executions, function count, request rate | Throttling hoặc invocation delay |
| Container/Kubernetes | Pod, CPU/memory requests, PVC, node pool | Pod Pending hoặc namespace không tạo resource |
| Database | Instance count, storage, connection, IOPS | Không scale database hoặc connection exhaustion |
| API/control plane | API rate, operation count, resource creation rate | Automation bị throttling |
| Observability | Log ingestion, metric series, trace volume | Mất telemetry hoặc tăng chi phí |

Không phải mọi giới hạn đều được gọi là quota trong giao diện provider. Một số được gọi là service limit, capacity limit, rate limit, soft limit hoặc subscription restriction. Hãy đưa tất cả giới hạn có thể ảnh hưởng workload vào cùng inventory.

## 5. Quota cứng, quota mềm và giới hạn runtime

### Hard quota

Hard quota chặn thao tác khi vượt ngưỡng. Ví dụ API tạo VM trả lỗi khi tổng vCPU vượt limit. Cần quota increase hoặc giải phóng resource trước khi tiếp tục.

### Soft quota

Soft quota là ngưỡng cảnh báo hoặc policy nội bộ. Nó cho phép vượt trong điều kiện nhất định nhưng yêu cầu phê duyệt, budget exception hoặc kiểm soát.

### Runtime limit

Runtime limit kiểm soát một workload cụ thể, ví dụ container memory limit hoặc max concurrency của function. Runtime limit có thể thấp hơn quota account.

### Rate limit

Rate limit kiểm soát tần suất hành động. Một automation có thể còn quota VM nhưng vẫn không tạo được 100 VM trong vài giây vì API rate limit.

### Capacity availability

Provider có thể từ chối cấp một instance dù quota còn dư do thiếu capacity ở zone, host pool hoặc accelerator family. Đây là lỗi capacity availability, cần xử lý bằng lựa chọn zone/family, reservation hoặc fallback; tăng quota không tự khắc phục.

## 6. Xây dựng quota inventory

Quota inventory là danh mục có cấu trúc để biết giới hạn nào đang áp dụng, ai sở hữu và khi nào cần hành động.

Các trường nên có:

| Trường | Ý nghĩa |
|---|---|
| Provider/service | Cloud provider và dịch vụ |
| Account/project/subscription | Phạm vi account |
| Region/zone | Phạm vi địa lý |
| Resource/metric | Tên quota và đơn vị |
| Current limit | Giới hạn hiện tại |
| Current usage | Mức đang dùng |
| Peak usage | Mức cao nhất đã quan sát |
| Allocated/committed | Phần đã phân bổ hoặc cam kết |
| Forecast peak | Peak dự báo |
| Headroom | Phần dư sau forecast |
| Increase lead time | Thời gian xin nâng quota |
| Request owner | Người/team chịu trách nhiệm |
| Approval owner | Người phê duyệt |
| Criticality | Mức độ ảnh hưởng |
| Last reviewed | Ngày rà soát gần nhất |
| Evidence/link | Dashboard, ticket hoặc tài liệu xác nhận |

### Đặt tên metric nhất quán

Chuẩn hóa tên resource và đơn vị giúp so sánh giữa provider:

- compute.vcpu.total
- compute.gpu.count
- network.ipv4.addresses
- network.load_balancers.count
- storage.block.capacity_gib
- serverless.concurrent_executions
- kubernetes.namespace.cpu_requests

Tên trên là schema nội bộ minh họa, không phải tên API quota của provider.

### Quota inventory cần cập nhật khi nào?

- Khi tạo account/project/subscription mới.
- Khi thêm region hoặc node pool.
- Khi launch workload mới.
- Khi thay đổi instance family hoặc accelerator.
- Khi có quota increase/decrease.
- Khi provider đổi default limit hoặc service behavior.
- Khi team chuyển workload hoặc ownership.
- Khi thay đổi forecast tăng trưởng.

## 7. Đo quota consumption và headroom

Với quota có giới hạn theo số lượng tài nguyên đồng thời, mức sử dụng tại thời điểm t:

\[
Usage\% = \frac{CurrentUsage}{QuotaLimit} \times 100\%
\]

Headroom tuyệt đối:

\[
Headroom = QuotaLimit - CurrentUsage
\]

Headroom theo tỷ lệ:

\[
Headroom\% = 1 - \frac{CurrentUsage}{QuotaLimit}
\]

Ví dụ quota 200 vCPU, đang sử dụng 130 vCPU:

- Usage = 65%.
- Headroom = 70 vCPU.
- Headroom rate = 35%.

Nếu forecast peak tháng sau là 185 vCPU, quota hiện tại chỉ còn 15 vCPU dự phòng. Nếu cần giữ 20% headroom, quota target phải cao hơn 185 vCPU.

### Phân biệt current usage và peak usage

Current usage có thể thấp vào ban đêm nhưng peak usage trong ngày cao. Capacity planning phải dùng peak theo cửa sổ thời gian phù hợp:

- Peak 5 phút cho burst/concurrency.
- Peak 1 giờ cho batch window.
- Peak theo ngày/tuần cho workload có seasonality.
- Peak theo chiến dịch hoặc sự kiện đặc biệt.

Với quota theo tổng resource tồn tại, usage cần tính resource đã provision kể cả idle nếu provider tính vào quota. Với quota theo throughput, cần đo request rate hoặc token consumption trong đúng cửa sổ.

### Headroom không phải lúc nào cũng là quota trống

Nếu quota còn 30% nhưng provider chỉ còn 5% capacity ở zone cần thiết, headroom quota không đồng nghĩa capacity thực tế. Theo dõi hai đại lượng riêng.

## 8. Dự báo tăng trưởng workload

Dự báo quota bắt đầu từ nhu cầu workload, không bắt đầu từ con số quota mong muốn.

### Các driver tăng trưởng

- Người dùng hoạt động và số tenant.
- Request/transaction per user.
- Số job, file, record hoặc event.
- Kích thước dữ liệu và retention.
- Số replica và availability target.
- Tần suất deploy/test/preview environment.
- Kế hoạch launch sản phẩm và marketing.
- Mùa vụ, cuối tháng, cuối quý hoặc ngày lễ.
- Mức tăng complexity của workload.
- Tỷ lệ retry, logging và replication.

Ví dụ user tăng 20% không nhất thiết compute tăng 20%. Nếu mỗi user tạo nhiều transaction hơn hoặc dữ liệu cần xử lý tăng theo bình phương do join/shuffle, demand có thể tăng nhanh hơn.

### Mô hình tăng trưởng tuyến tính

Nếu workload tăng thêm gần như cố định mỗi tháng:

\[
D(t) = D_0 + a \times t
\]

Trong đó \(D_0\) là demand hiện tại, \(a\) là mức tăng mỗi kỳ và \(t\) là số kỳ.

### Mô hình tăng trưởng lũy thừa

Nếu workload tăng theo tỷ lệ phần trăm mỗi kỳ:

\[
D(t) = D_0 \times (1+g)^t
\]

Trong đó \(g\) là growth rate mỗi kỳ.

Ví dụ demand hiện tại 100 vCPU, tăng 12% mỗi tháng. Sau 6 tháng:

\[
D(6) = 100 \times 1.12^6 \approx 197.4\ vCPU
\]

Nếu chỉ dự báo tuyến tính thêm 12 vCPU mỗi tháng, forecast sẽ thấp đáng kể.

### Mùa vụ và peak

Dùng mô hình cơ sở cộng seasonal multiplier:

\[
D_{\text{peak}} = D_{\text{baseline}} \times S_{\text{season}}
\]

Ví dụ baseline 180 vCPU, hệ số peak 1,4 thì peak demand khoảng 252 vCPU. Cần dùng multiplier từ dữ liệu lịch sử hoặc kế hoạch business, không chọn tùy ý.

### Kịch bản tăng trưởng

Tạo ít nhất ba kịch bản:

| Kịch bản | Giả định | Mục đích |
|---|---|---|
| Conservative | Tăng trưởng thấp, launch trễ | Kế hoạch chi phí cơ sở |
| Expected | Tăng trưởng theo forecast chính | Kế hoạch vận hành thông thường |
| High growth | Launch thành công, peak cao hoặc acquisition tăng | Kiểm tra quota runway và fallback |

Có thể thêm stress scenario cho sự cố failover, region evacuation hoặc campaign đột biến.

## 9. Chuyển workload forecast thành resource demand

Workload demand cần được chuyển thành CPU, memory, storage, network, IP, GPU và service-specific quota.

### Ví dụ API

Giả sử mỗi 1.000 request/second cần 4 vCPU và 8 GiB RAM theo benchmark:

\[
CPU_{\text{required}} =
\frac{RPS_{\text{forecast}}}{1000} \times 4
\]

Nếu forecast peak là 8.000 RPS, CPU demand lý tưởng là 32 vCPU. Cộng headroom 30% cho burst và failure reserve, target khoảng 42 vCPU.

Cần benchmark tại latency SLO. Nếu một request phụ thuộc database và throughput database thấp, công thức CPU đơn thuần sẽ không đủ.

### Ví dụ worker queue

Nếu mỗi worker xử lý 50 message/second và queue peak cần 2.000 message/second:

\[
Workers_{\text{base}} = \frac{2000}{50} = 40
\]

Nếu cần giữ 25% headroom, có thể lập capacity 50 worker. Tuy nhiên, cần kiểm tra downstream database/API chịu được 50 worker đồng thời không.

### Ví dụ storage

Storage demand có thể gồm:

\[
Storage_{\text{required}} =
Data_{\text{active}} + Data_{\text{retained}} + Index + Backup + GrowthBuffer
\]

Nếu dữ liệu tăng 2 TB/tháng, retention 12 tháng, cần tính khoảng 24 TB dữ liệu lịch sử trước khi cộng index, replication và backup. Không dùng số TB logical làm quota vật lý mà bỏ qua replication factor hoặc snapshot copy.

### Network và IP

Tăng số VM, Pod hoặc serverless connector có thể làm tăng:

- Private IP/ENI/NIC.
- NAT connection và port mapping.
- Load balancer/frontend IP.
- Route/firewall rules.
- Cross-zone traffic và egress.
- DNS record/query volume.

Quota planning cần tính cả tài nguyên phụ trợ, không chỉ CPU và RAM.

## 10. Headroom và capacity cho failure domain

Headroom giúp hệ thống hấp thụ burst, nhưng cũng cần đủ capacity khi một node hoặc zone mất.

### N+1 planning

Nếu hệ thống cần chịu lỗi một node pool member, tính capacity còn lại sau khi loại node đó.

Ví dụ ba node, mỗi node có 32 vCPU, tổng 96 vCPU. Nếu workload cần 60 vCPU và phải tiếp tục chạy khi mất một node, hai node còn lại có 64 vCPU danh nghĩa. Sau khi trừ system reserve và headroom, có thể không đủ. Cần tăng node count hoặc shape.

### Zone failure

Với ba zone phân bố đều, khi một zone mất, hai zone còn lại phải gánh workload cần thiết. Nếu workload chạy ở mức 70% tổng capacity bình thường, sau khi mất 1/3 capacity, utilization có thể tăng lên khoảng 105% và không thể đáp ứng. Phải thiết kế theo capacity surviving, không chỉ phân bố replica.

### Headroom theo lớp

- **Quota headroom:** quota còn lại trước khi chạm limit.
- **Provider capacity headroom:** capacity có thể cấp thêm ở zone/family.
- **Cluster headroom:** allocatable còn lại trong node pool.
- **Workload headroom:** throughput còn có thể tăng trước khi vi phạm SLO.
- **Dependency headroom:** database/network/storage còn có thể xử lý bao nhiêu.

Mỗi lớp cần metric và owner riêng.

## 11. Xác định quota target và thời điểm xin tăng

Quota target cần đủ cho forecast peak, headroom và các tài nguyên cùng scope.

\[
Quota_{\text{target}} =
\frac{ForecastPeak}{1 - HeadroomTarget}
\]

Ví dụ forecast peak 240 vCPU và mục tiêu giữ 25% headroom:

\[
Quota_{\text{target}} = \frac{240}{0.75} = 320\ vCPU
\]

Nếu quota hiện tại là 250 vCPU, cần đề nghị tăng ít nhất 70 vCPU để đạt target 320 vCPU. Có thể cần xin nhiều hơn nếu growth forecast hoặc DR requirement tăng.

### Quota runway

Với quota đồng thời, runway có thể ước lượng từ thời điểm forecast usage chạm ngưỡng. Với tăng trưởng tuyến tính:

\[
Runway =
\frac{QuotaLimit - CurrentUsage}{ExpectedNetGrowthPerPeriod}
\]

Ví dụ còn 60 vCPU và demand tăng 15 vCPU/tháng, runway xấp xỉ 4 tháng nếu không có seasonality hoặc step change.

Với tăng trưởng lũy thừa, giải thời điểm t sao cho forecast demand bằng quota threshold. Không dùng runway tuyến tính nếu growth rate thay đổi theo tỷ lệ.

### Request lead time

Nếu provider thường mất 10 ngày xử lý quota request, cần gửi trước khi runway còn 10 ngày cộng buffer. Với GPU hoặc quota đặc biệt, thời gian xử lý/capacity sourcing có thể dài hơn. Dùng lead time lịch sử và xác nhận với provider.

### Quota request không đồng nghĩa capacity reservation

Quota increase cho phép account yêu cầu thêm resource trong giới hạn mới. Nó không nhất thiết giữ sẵn instance hoặc GPU. Nếu workload cần capacity chắc chắn ở một thời điểm, cần kiểm tra capacity reservation/dedicated capacity hoặc cơ chế tương đương.

## 12. Quota cho VM và instance family

VM quota có thể được tính theo tổng vCPU, số instance, family, region hoặc loại workload. Các giới hạn có thể chồng lấp.

Khi lập kế hoạch:

- Tính vCPU theo từng instance family.
- Tách quota general-purpose, compute-optimized, memory-optimized và accelerator.
- Xác định region/zone cần dùng.
- Tính VM cho production, staging, CI/CD, migration và DR.
- Tính node autoscaler max size.
- Kiểm tra quota của instance type hiếm hoặc bare metal.
- Kiểm tra reservation và commitment scope.

### Ví dụ

Một hệ thống cần:

- 80 vCPU general-purpose.
- 48 vCPU memory-optimized.
- 16 vCPU GPU worker host.
- 24 vCPU DR reserve.

Tổng vCPU danh nghĩa là 168, nhưng quota theo family có thể yêu cầu các limit riêng. Không chỉ gửi request “tăng tổng vCPU lên 168” nếu accelerator family vẫn bị giới hạn.

### Instance family fallback

Chuẩn bị danh sách instance family tương đương theo workload:

- CPU architecture tương thích.
- RAM/vCPU ratio đủ.
- Network bandwidth và disk throughput.
- Accelerator model/VRAM.
- Local NVMe hoặc ephemeral storage.
- License và software compatibility.

Autoscaler có thể dùng nhiều family để giảm rủi ro thiếu capacity, nhưng cần test hiệu năng và chi phí.

## 13. Quota cho Kubernetes và container platform

Kubernetes có nhiều lớp giới hạn.

### ResourceQuota

ResourceQuota giới hạn tổng tài nguyên hoặc số lượng object trong namespace. Ví dụ:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-compute-quota
  namespace: team-a
spec:
  hard:
    requests.cpu: "40"
    requests.memory: 80Gi
    limits.cpu: "80"
    limits.memory: 160Gi
    pods: "100"
    persistentvolumeclaims: "30"
~~~

Quota này giới hạn tổng requests/limits và số object trong namespace theo các resource được khai báo. Nó không tự tạo node capacity và không thay thế quota cloud account.

### LimitRange

LimitRange đặt default/min/max resource cho container hoặc Pod. Nó giúp ngăn container không khai báo request hoặc yêu cầu vượt mức policy, nhưng không phải tổng quota namespace.

### Node pool quota

Cluster autoscaler có thể muốn thêm node nhưng bị chặn bởi:

- Cloud vCPU quota.
- Instance family quota.
- GPU quota.
- Subnet IP exhaustion.
- Node pool maximum.
- Regional capacity.
- Managed Kubernetes node quota.

### Pod quota và IP quota

CNI có thể có giới hạn Pod/IP trên node hoặc subnet. Tăng số Pod không chỉ tiêu thụ CPU/RAM; nó có thể chạm số IP, ENI, route hoặc network policy scale limit.

### Thiết kế phân bổ namespace

Quota nên được gắn với owner và workload tier. Ví dụ production namespace có baseline và headroom riêng; dev/test có cap thấp hơn và có thể bị thu hồi capacity. Không để namespace dùng chung khiến một team tiêu thụ hết tài nguyên của team khác.

## 14. Quota cho serverless và managed services

Serverless có thể có giới hạn theo concurrency, request rate, execution duration, memory, deployment package, function count hoặc event source mapping.

Khi demand tăng:

- Forecast peak concurrent execution, không chỉ số invocation/ngày.
- Tính thời gian xử lý trung bình và tail duration.
- Đánh giá reserved/provisioned concurrency nếu sản phẩm hỗ trợ.
- Kiểm tra downstream connection limit.
- Kiểm tra event source polling/partition/consumer limit.
- Xem xét retry và DLQ làm tăng invocation.
- Kiểm tra API gateway, queue và database quota đồng thời.

### Ví dụ concurrency

Theo Little's Law, concurrency xấp xỉ throughput nhân thời gian xử lý:

\[
Concurrency \approx ArrivalRate \times AverageDuration
\]

Nếu function nhận 400 request/second và thời gian xử lý trung bình 0,25 second:

\[
Concurrency \approx 400 \times 0.25 = 100
\]

Đây là ước lượng trung bình; peak burst và p95 duration có thể cần concurrency cao hơn. Dùng arrival rate theo peak window và latency distribution để lập kế hoạch.

### Dependency quota

Nâng concurrency của function nhưng không nâng database connection hoặc API quota có thể làm hệ thống lỗi nhanh hơn. Phải lập kế hoạch capacity end-to-end.

## 15. Quota network và storage

### Network quota

Inventory cần gồm:

- VPC/VNet và subnet count.
- Private IP và public IP.
- ENI/NIC hoặc network attachment.
- NAT gateway và connection/port capacity.
- Load balancer, listener và target count.
- Route table, peering, transit attachment.
- VPN tunnel và bandwidth.
- Firewall rule/policy count.
- DNS zone, record và query rate.

Tăng compute có thể làm cạn subnet IP trước khi hết vCPU. Đặc biệt với Kubernetes hoặc serverless VPC integration, phải dự báo IP/interface theo scale pattern của dịch vụ.

### Storage quota

Theo dõi:

- Total provisioned capacity.
- Volume count và snapshot count.
- Per-volume size limit.
- IOPS/throughput provisioned.
- Object storage request rate.
- File share count/throughput.
- Backup vault capacity/retention.
- KMS key/request quota khi workload tăng.

Dung lượng còn dư không bảo đảm IOPS/throughput còn đủ. Với database, quota performance có thể chạm trước quota GB.

## 16. Lập kế hoạch capacity theo account, project và environment

Một tổ chức thường có nhiều account/project/subscription và nhiều môi trường. Cần xác định quota thuộc đâu và ai chịu trách nhiệm.

### Phân vùng account

Mô hình thường gặp:

- Production account/project.
- Non-production account/project.
- Shared platform/network account.
- Security/logging account.
- Data/analytics account.
- Disaster recovery account.

Tách account giúp giới hạn blast radius và quản trị chi phí, nhưng quota thường không tự cộng gộp hoặc chia sẻ giữa account. Capacity DR cần được tính riêng ở region/account đích.

### Allocation model

Có thể phân bổ quota theo:

- Team/owner.
- Environment.
- Workload criticality.
- Forecast demand.
- Budget.
- Reservation/commitment.
- Growth plan.

Ví dụ tổ chức có 500 vCPU provider quota, nội bộ phân bổ 300 cho production, 80 cho staging, 40 cho CI, 40 cho data batch và giữ 40 làm contingency. Tổng allocation không vượt 500, nhưng vẫn phải kiểm tra quota family/region và capacity thực tế.

### Shared platform

Network gateway, observability, DNS, Kubernetes system pool và shared database cũng tiêu thụ quota. Cần có owner cho shared capacity và mô hình cost allocation để workload không đánh giá thấp phần tài nguyên dùng chung.

### Không phân bổ toàn bộ quota

Nếu chia 100% quota cho các team, platform không còn chỗ cho rollout, recovery, migration hoặc emergency scale. Giữ contingency pool và quy định ai có quyền sử dụng.

## 17. Quản trị quota request và approval

Quota increase cần có quy trình để provider và tổ chức đánh giá tính cần thiết, tác động chi phí và rủi ro.

### Thông tin cần có trong request

- Account/project/subscription và region.
- Service/resource/quota metric chính xác.
- Limit hiện tại và limit mong muốn.
- Usage hiện tại, peak và forecast.
- Workload/business driver.
- Ngày cần quota có hiệu lực.
- Kịch bản nếu không được cấp.
- Chi phí dự kiến và budget owner.
- Capacity reservation/fallback nếu cần.
- Bằng chứng benchmark, launch plan hoặc incident/DR requirement.
- Technical owner và approver.

### Quy trình

1. Workload owner tạo demand forecast.
2. Platform/FinOps xác minh metric và quota scope.
3. SRE/architecture đánh giá availability và capacity.
4. Finance kiểm tra budget/commitment.
5. Security/governance kiểm tra scope nếu cần.
6. Authorized owner gửi request qua provider.
7. Theo dõi ticket và xác nhận limit mới.
8. Cập nhật inventory, alert threshold và forecast.
9. Kiểm tra quota thực tế bằng API/console trước khi triển khai.

### Approval theo mức độ

Có thể phân loại:

- Small increase trong allocation đã duyệt: platform owner phê duyệt.
- Production capacity increase: SRE + budget owner.
- GPU hoặc dedicated capacity đắt tiền: architecture + finance.
- Emergency quota increase: incident commander/authorized approver, hậu kiểm sau sự cố.

Không để người tạo resource tự nâng quota hoặc tự cấp budget không giới hạn nếu policy yêu cầu separation of duties.

## 18. Monitoring, alert và quota runway

Quota monitoring cần nhìn current usage, forecast peak và lead time.

### Alert thresholds

Có thể dùng nhiều ngưỡng theo mức độ:

| Mức | Điều kiện minh họa | Hành động |
|---|---|---|
| Info | Usage vượt 60% | Ghi nhận và theo dõi trend |
| Warning | Forecast peak vượt 75% | Xác minh forecast và owner |
| Action | Usage/forecast vượt 85% | Mở quota request hoặc giải phóng resource |
| Critical | Còn dưới lead-time buffer hoặc chạm 95% | Escalate, kích hoạt fallback |
| Exhausted | API trả quota exceeded | Incident/runbook, giảm hoặc chuyển tải |

Ngưỡng thực tế phụ thuộc lead time, growth rate và criticality. GPU quota có lead time dài có thể cần cảnh báo ở mức thấp hơn 70%.

### Forecast-based alert

Không chỉ cảnh báo khi current usage vượt 80%. Nếu usage hiện tại 40% nhưng growth rate tăng nhanh, forecast 30 ngày có thể chạm 95%. Cảnh báo dựa trên projected exhaustion date sẽ hữu ích hơn.

### Dashboard

Một dashboard quota nên có:

- Limit, current usage và peak.
- Forecast 30/60/90 ngày.
- Headroom và runway.
- Scope account/region/service/family.
- Pending quota request và expected approval date.
- Capacity reservation và provider capacity status.
- Owner, budget và criticality.
- Historical quota increase và utilization sau increase.

### Kiểm tra định kỳ

- Hằng ngày: quota critical cho autoscaling và production.
- Hằng tuần: forecast peak và pending request.
- Hằng tháng: allocation theo team và environment.
- Hằng quý: growth plan, reservation, region strategy và unused quota.

## 19. Tích hợp quota với autoscaling

Autoscaler thường phản ứng với demand, nhưng quota là trần. Nếu autoscaler không biết quota còn lại, nó có thể liên tục yêu cầu resource không thể cấp.

### Capacity envelope

Định nghĩa maximum scale theo giá trị nhỏ nhất trong các giới hạn:

\[
ScaleMax = \min(
QuotaAvailable,
ProviderCapacity,
SubnetCapacity,
BudgetCapacity,
DependencyCapacity,
PolicyLimit
)
\]

Đây là mô hình tư duy; mỗi đại lượng cần được quy đổi về cùng loại workload capacity trước khi so sánh.

### Quota-aware scaling

- Đọc quota còn lại và node pool max.
- Đặt max replica phù hợp.
- Ưu tiên instance family/zone fallback đã kiểm thử.
- Phát hiện quota errors và dừng retry tạo resource vô ích.
- Giảm tải hoặc queue khi không thể scale thêm.
- Giữ headroom cho system/DR.
- Cảnh báo owner khi autoscaler gần quota boundary.

### Scale-in và quota reclamation

Khi workload giảm, xóa resource không dùng có thể giải phóng quota. Tuy nhiên, không xóa resource dự phòng hoặc capacity reservation trước khi xác minh RTO/DR và policy. Có thể dùng TTL/cleanup cho dev/test, nhưng production cần owner và approval.

## 20. Kế hoạch capacity theo tăng trưởng: ví dụ thực tế

Một nền tảng API hiện có 120 vCPU đang chạy trong region A. Peak usage hiện tại là 150 vCPU do autoscaling. Business dự báo traffic tăng 15% mỗi tháng trong 4 tháng và có chiến dịch cuối quý với peak multiplier 1,3.

Forecast baseline sau 4 tháng:

\[
D(4) = 150 \times 1.15^4 \approx 262.4\ vCPU
\]

Peak chiến dịch:

\[
D_{\text{campaign}} = 262.4 \times 1.3 \approx 341.1\ vCPU
\]

Nếu muốn giữ 20% headroom:

\[
Quota_{\text{target}} = \frac{341.1}{0.8} \approx 426.4\ vCPU
\]

Làm tròn theo instance shape và quota unit, kế hoạch có thể đặt mục tiêu 432 vCPU. Nếu quota hiện tại 300 vCPU, cần đề xuất tăng khoảng 132 vCPU.

Nhưng cần kiểm tra thêm:

- 432 vCPU có nằm trong quota instance family cần dùng không?
- Zone A/B/C có đủ provider capacity không?
- Subnet còn đủ IP cho node và Pod không?
- Database connection và network throughput có chịu được peak không?
- Budget có đáp ứng peak 341 vCPU và headroom không?
- DR region có cần capacity tương đương không?
- Quota request lead time có trước chiến dịch không?

Nếu một trong các lớp này không đạt, chỉ tăng regional vCPU quota sẽ không giải quyết được.

## 21. Ví dụ quota planning cho Kubernetes nhiều team

Một cluster có tổng allocatable 400 CPU và 1 TiB memory. Các team được phân bổ:

| Namespace | CPU requests quota | Memory requests quota | Pod quota | Owner |
|---|---:|---:|---:|---|
| production-api | 160 CPU | 320 GiB | 200 | API team |
| production-worker | 100 CPU | 256 GiB | 300 | Processing team |
| data-platform | 80 CPU | 256 GiB | 150 | Data team |
| staging | 30 CPU | 64 GiB | 100 | Platform |
| system | 20 CPU | 64 GiB | 100 | Platform |
| Contingency | 10 CPU | 64 GiB | — | SRE |

Tổng CPU allocation là 400. Tuy nhiên, quota namespace không bảo đảm scheduler có thể đặt Pod nếu node affinity, zone, GPU, taint hoặc volume topology không phù hợp. Cũng cần trừ DaemonSet/system overhead khỏi allocatable và kiểm tra node pool scale quota.

Khi API team muốn tăng 40 CPU:

1. Kiểm tra forecast và peak usage.
2. Xác định namespace có thể giảm unused allocation không.
3. Xác minh cluster còn allocatable hay cần node pool scale-out.
4. Kiểm tra cloud vCPU quota và subnet IP.
5. Đánh giá ảnh hưởng tới worker/data team.
6. Phê duyệt allocation hoặc tăng quota cloud nếu cần.
7. Cập nhật ResourceQuota và alert.

## 22. Chiến lược khi quota không được tăng kịp

Quota request có thể bị từ chối hoặc chậm. Cần có phương án vận hành:

- Dùng instance family tương đương đã benchmark.
- Chuyển workload sang region/zone khác nếu data residency và latency cho phép.
- Tạm dừng dev/test hoặc batch không ưu tiên.
- Giảm replica ở workload có thể chịu tải thấp hơn.
- Dùng queue để hấp thụ burst và xử lý sau.
- Tăng hiệu quả compute bằng tối ưu code, caching và batch I/O.
- Giảm retention hoặc cleanup dữ liệu tạm theo policy.
- Dùng managed service có capacity model khác nếu phù hợp.
- Chuyển một phần workload sang serverless/container/VM pool khác.
- Dùng reservation hoặc dedicated capacity nếu phù hợp và còn thời gian.

Không vượt quota bằng cách tạo thêm account hoặc region ngoài governance để né giới hạn. Cách đó có thể phá vỡ security, audit, cost allocation và data residency.

### Priority policy

Khi capacity thiếu, ưu tiên theo business criticality:

1. Production transaction và control plane thiết yếu.
2. Workload phục vụ SLA/contract.
3. Batch có deadline gần.
4. Non-critical analytics.
5. Dev/test và preview environment.

Priority phải được thống nhất trước sự cố, không quyết định tùy hứng khi autoscaler đã thất bại.

## 23. Commitment, reservation và quota

Quota và reservation có quan hệ nhưng không đồng nhất.

- Quota cho phép account yêu cầu resource đến một ngưỡng.
- Reservation giữ hoặc bảo đảm khả năng cấp một số resource theo điều kiện provider.
- Commitment/discount plan giảm giá dựa trên cam kết sử dụng hoặc chi tiêu, không nhất thiết giữ capacity.
- Spot capacity có thể rẻ hơn nhưng không bảo đảm tồn tại.

Khi tăng trưởng ổn định, có thể dùng commitment cho baseline và on-demand/spot cho burst. Khi workload cần capacity chắc chắn ở zone/instance family cụ thể, xem xét reservation riêng. Cần kiểm tra quota tương ứng vẫn đủ để consume reservation.

### Tránh overcommit

Nếu commitment cao hơn demand thực tế, tổ chức có thể trả tiền cho capacity không dùng. Nếu reservation không khớp instance family/zone hoặc scope, nó có thể không được áp dụng như mong đợi. Review utilization và coverage định kỳ.

## 24. Multi-region và disaster recovery quota

DR thường bị bỏ quên trong quota planning. Khi region chính mất, region dự phòng có thể cần scale nhanh gấp nhiều lần baseline bình thường.

Các câu hỏi:

- DR là active-active, warm standby hay pilot light?
- Region dự phòng có quota đủ để chạy critical workload không?
- Có reservation hoặc capacity guarantee không?
- Database replication và storage quota đủ không?
- Network/IP/NAT/load balancer quota có đủ không?
- DNS và certificate đã sẵn sàng?
- Provider có thể cấp capacity trong thời điểm regional incident không?
- DR test có tạo peak usage và quota consumption tạm thời không?

### Warm standby

Warm standby có một phần compute chạy sẵn. Quota cần đủ cho baseline hiện tại và phần scale-up khi failover. Cần đo thời gian tăng capacity.

### Pilot light

Pilot light giữ một số thành phần tối thiểu. Quota cần đủ để scale-out toàn bộ khi kích hoạt. Nếu chỉ kiểm tra quota khi diễn tập, có thể phát hiện thiếu capacity quá muộn.

### Active-active

Hai region cùng phục vụ traffic. Mỗi region cần đủ capacity để gánh phần traffic tăng khi region kia mất, hoặc có cơ chế giảm tải có kiểm soát. Không giả định 50/50 traffic đồng nghĩa mỗi region chỉ cần 50% capacity.

## 25. Governance và trách nhiệm ownership

Quota không phải công việc riêng của cloud admin. Workload owner hiểu demand; platform team hiểu quota scope và node pool; FinOps hiểu budget; SRE hiểu SLO và failure mode; security/governance kiểm soát account và policy.

| Vai trò | Trách nhiệm |
|---|---|
| Workload owner | Forecast demand, benchmark và mô tả business need |
| Platform/cloud team | Inventory quota, kiểm tra scope, submit request và quản lý shared capacity |
| SRE | Headroom, N+1, availability, alert và fallback |
| FinOps/Finance | Budget, forecast cost, commitment và allocation |
| Security/governance | Account boundary, policy, region restriction và approval |
| Provider support/account team | Xác nhận quota/capacity availability và lead time |

### Ownership phải gắn với từng quota

Mỗi quota quan trọng cần owner chính, backup owner, escalation path và thời gian review. Không để quota inventory chỉ có tên service mà không có người chịu trách nhiệm.

### Exception

Nếu team cần vượt allocation nội bộ, phải có:

- Lý do và thời hạn.
- Tác động lên team khác.
- Budget owner.
- Kế hoạch thu hồi hoặc giảm allocation.
- Audit trail và ngày review lại.

## 26. IaC và automation cho quota governance

Quota inventory, alert và resource allocation có thể được quản lý bằng code hoặc policy-as-code.

### IaC

Infrastructure as Code có thể khai báo:

- Node pool min/max.
- ResourceQuota/LimitRange.
- Autoscaling boundaries.
- Instance family allow-list.
- Region allow-list.
- Network/subnet capacity.
- Budget alert và owner tags.

Quota provider đôi khi được quản lý qua API/console riêng và không phải mọi loại đều hỗ trợ IaC. Cần xác minh provider resource support và không giả định khai báo Terraform/ARM/CloudFormation tự động nâng mọi quota.

### Policy-as-code

Policy có thể từ chối deployment nếu:

- Node pool max vượt allocation được duyệt.
- Workload thiếu owner/cost center.
- GPU request không có approval.
- Region không được phép.
- Resource request vượt namespace quota.
- Production workload không có budget hoặc capacity plan.

### Automation

Có thể tự động:

- Thu thập quota và usage qua provider API.
- Tính headroom và forecast.
- Mở ticket khi projected exhaustion gần lead time.
- Kiểm tra quota sau khi request được duyệt.
- Phát hiện resource idle/orphan.
- Cập nhật dashboard và allocation report.

Automation cần idempotent, có audit, rate limit và quyền tối thiểu. Không tự động xóa production resource chỉ dựa trên một metric usage thấp.

## 27. Quy trình review capacity hàng tháng

Một buổi review hiệu quả cần kết nối forecast với hành động cụ thể.

1. So sánh actual usage với forecast kỳ trước.
2. Phân tích sai số dự báo và nguyên nhân.
3. Cập nhật tăng trưởng user, traffic, data và release plan.
4. Kiểm tra peak/seasonality và upcoming events.
5. Tính quota runway theo scope/resource.
6. Kiểm tra provider capacity và reservation utilization.
7. Xác định quota request cần mở trong kỳ.
8. Review headroom N+1 và DR region.
9. Đánh giá budget, commitment và cost per workload.
10. Gán owner, due date và escalation cho từng action.

Kết quả review nên có demand forecast, quota target, gap, cost estimate, request ticket, owner và ngày cần hoàn tất.

## 28. Runbook khi gặp quota exceeded

Khi triển khai hoặc autoscaling bị chặn:

### Xác định giới hạn

- Đọc error code/message từ API.
- Xác định metric, scope, region và resource family.
- Kiểm tra quota hiện tại và usage.
- Phân biệt quota exceeded, rate limit, provider capacity shortage và policy deny.

### Giảm tác động

- Dừng retry vô hạn của autoscaler/automation.
- Giữ workload hiện có ổn định.
- Ưu tiên critical workload.
- Pause dev/test hoặc batch không cấp thiết.
- Dùng fallback instance family/zone đã kiểm thử.
- Điều tiết queue và concurrency nếu dependency bị ảnh hưởng.

### Khôi phục

- Mở quota request hoặc escalation.
- Kiểm tra capacity availability và reservation.
- Xác nhận limit mới qua API/console.
- Thử tạo resource nhỏ trong scope cần thiết.
- Resume autoscaler/rollout theo từng bước.
- Theo dõi error, usage và budget.

### Sau sự cố

- Cập nhật inventory và forecast.
- Xác định vì sao alert không phát hiện sớm.
- Điều chỉnh threshold/lead time.
- Cập nhật runbook và owner.
- Đánh giá có cần allocation hoặc architecture change.

## 29. Các sai lầm thường gặp

**Chỉ nhìn quota tổng.** Quota family, GPU, IP, storage hoặc region có thể chạm trần trước. Theo dõi từng metric có scope rõ.

**Nghĩ quota tăng là có capacity.** Provider có thể thiếu host hoặc accelerator ở zone. Kiểm tra availability/reservation riêng.

**Dự báo bằng average.** Peak, seasonality và failure reserve có thể làm demand cao hơn nhiều. Dùng p95/peak và kịch bản.

**Đợi quota gần hết mới xin tăng.** Lead time xử lý có thể dài hơn runway. Forecast projected exhaustion date.

**Nâng quota mà không xét budget.** Quota cho phép scale lớn hơn và có thể làm bill tăng. Gắn quota request với cost estimate và guardrail.

**Tăng concurrency nhưng quên dependency.** Database, NAT, API và storage có thể quá tải trước compute. Lập kế hoạch end-to-end.

**Phân bổ hết quota cho các team.** Không còn headroom cho rollout, migration, recovery và incident. Giữ contingency pool.

**Dùng nhiều account để né quota.** Làm vỡ governance, audit, network và cost allocation. Thiết kế account boundary có chủ đích.

**Không tính DR.** Region dự phòng có thể không đủ quota khi cần failover. Kiểm tra và diễn tập quota DR.

**Autoscaler retry liên tục khi quota hết.** Gây API throttling và log noise. Phân biệt lỗi quota với lỗi tạm thời, dừng retry và kích hoạt runbook.

## 30. Checklist quản lý quota và capacity theo tăng trưởng

### Inventory và scope

- [ ] Có inventory quota theo provider, account, project, subscription, region và service.
- [ ] Ghi rõ đơn vị, current limit, usage, peak và owner.
- [ ] Phân biệt quota, rate limit, runtime limit và provider capacity.
- [ ] Kiểm tra quota tổng, quota family và quota phụ trợ.
- [ ] Có inventory cho CPU, GPU, memory shape, storage, network, IP, serverless và API.

### Forecast và capacity

- [ ] Có workload driver và forecast 30/60/90 ngày hoặc theo horizon phù hợp.
- [ ] Có kịch bản conservative, expected và high growth.
- [ ] Đã tính seasonality, launch, migration và DR.
- [ ] Có benchmark để chuyển workload thành resource demand.
- [ ] Tính peak, headroom và N+1/failure-domain capacity.
- [ ] Kiểm tra capacity provider và reservation riêng với quota.
- [ ] Có quota runway và request lead time.

### Governance và cost

- [ ] Mỗi quota quan trọng có owner và approver.
- [ ] Quota request có forecast, business driver, cost và fallback.
- [ ] Allocation theo team/environment có contingency pool.
- [ ] Có budget alert và maximum scale guardrail.
- [ ] Commitment/reservation được review theo utilization.
- [ ] Có audit trail cho exception và quota change.

### Monitoring và operations

- [ ] Dashboard hiển thị usage, peak, headroom, forecast và runway.
- [ ] Alert dựa trên projected exhaustion date.
- [ ] Autoscaler biết giới hạn quota và node pool max.
- [ ] Có fallback cho instance family/zone hoặc workload priority.
- [ ] Có runbook quota exceeded và dừng retry vô ích.
- [ ] DR region có quota và capacity được kiểm tra.
- [ ] Review forecast vs actual định kỳ.

## 31. Tự kiểm tra

1. Quota khác capacity, allocation và reservation như thế nào?
2. Vì sao nâng quota vCPU không bảo đảm tạo được GPU instance trong một zone?
3. Quota theo account, region, resource family và namespace khác nhau ra sao?
4. Phân biệt hard quota, soft quota, runtime limit và API rate limit.
5. Cần những trường nào trong quota inventory để dự báo và giao ownership?
6. Với demand hiện tại 100 vCPU và tăng 12% mỗi tháng, demand 6 tháng tới xấp xỉ bao nhiêu?
7. Nếu forecast peak 240 vCPU và muốn giữ 25% headroom, quota target cần là bao nhiêu?
8. Vì sao current usage thấp không có nghĩa quota runway dài?
9. Làm thế nào tính capacity N+1 khi mất một node hoặc một zone?
10. ResourceQuota và LimitRange trong Kubernetes kiểm soát những gì?
11. Vì sao tăng serverless concurrency cần xem xét database connection và downstream quota?
12. Quota request cần có thông tin gì để provider và budget owner đánh giá?
13. Làm thế nào để autoscaler phản ứng khi quota hết mà không retry liên tục?
14. Hãy lập quota plan 90 ngày cho workload tăng trưởng 15% mỗi tháng, có peak mùa vụ và DR region.

Quản lý quota và capacity theo tăng trưởng là một vòng lặp liên tục: kiểm kê giới hạn, đo usage, dự báo demand, tính headroom, xác minh provider capacity, xin quota đúng lead time và theo dõi kết quả. Khi quota được gắn với workload owner, forecast, budget, autoscaling và DR plan, tổ chức có thể tăng compute có kiểm soát và giảm nguy cơ hệ thống không scale được đúng lúc cần.
