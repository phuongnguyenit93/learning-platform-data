# Tính chi phí tài nguyên nhàn rỗi, máy dừng và tài nguyên đi kèm

## Bối cảnh: hóa đơn vẫn có thể tăng khi CPU gần như không hoạt động

Một VM có thể chỉ dùng 3% CPU trong nhiều giờ nhưng vẫn phát sinh chi phí compute theo thời gian cấp phát. Khi dừng VM, chi phí CPU/compute có thể ngừng hoặc giảm tùy nền tảng và trạng thái dừng; tuy nhiên, boot volume, data disk, snapshot, địa chỉ IP, load balancer, NAT gateway, log, backup, license hoặc capacity commitment vẫn có thể tiếp tục tính phí. Một cluster Kubernetes có thể ít pod chạy nhưng vẫn giữ nhiều node dự phòng. Một hàm serverless ít được gọi có thể không tính compute theo thời gian chạy, nhưng provisioned concurrency hoặc minimum instances vẫn tạo chi phí nền.

Vì vậy, tối ưu chi phí compute cần nhìn toàn bộ tài nguyên được tạo ra để phục vụ workload, không chỉ CPU và RAM đang sử dụng. Cần phân biệt **tài nguyên nhàn rỗi**, **máy đã dừng**, **máy đã xóa** và **tài nguyên phụ trợ còn tồn tại**; sau đó xác định phần chi phí nào có thể giảm mà không làm ảnh hưởng availability, RTO/RPO, bảo mật hoặc trải nghiệm người dùng.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, chủ đề này giúp kỹ sư đọc hóa đơn theo vòng đời tài nguyên, phát hiện chi phí phát sinh khi không có workload, thiết kế lịch bật/tắt, quản lý storage và network đi kèm, đồng thời đánh giá các khoản commitment dài hạn.

## 1. Cấu thành chi phí của một workload compute

Chi phí compute thường gồm nhiều thành phần:

| Nhóm chi phí | Ví dụ | Có thể còn tính phí khi VM dừng? |
|---|---|---|
| Compute capacity | vCPU, RAM, GPU, thời gian instance chạy | Thường dừng hoặc giảm với trạng thái deallocated/stopped phù hợp; tùy dịch vụ và trạng thái |
| License / software | Windows, commercial database, security software, OS subscription | Có thể tiếp tục tính theo instance, core, host hoặc hợp đồng |
| Block storage | Boot disk, data volume, provisioned IOPS/throughput | Thường vẫn tính khi volume còn tồn tại |
| Snapshot / backup | Snapshot volume, backup vault, retention copy | Thường tính theo dung lượng, số bản sao hoặc tier còn lưu |
| Network | Public IP, NAT gateway, load balancer, firewall, private endpoint, data transfer | Nhiều khoản vẫn tồn tại độc lập với trạng thái VM |
| Observability | Log ingestion, metric retention, trace, monitoring agent service | Có thể tiếp tục phát sinh khi log/metric vẫn được gửi và lưu |
| Commitment | Reserved capacity, savings plan, committed use, dedicated host | Nghĩa vụ thanh toán có thể tiếp tục dù workload không chạy |
| Orchestration | Kubernetes control plane, node pool, registry, service mesh | Một số thành phần có phí riêng hoặc tạo chi phí nền |

Không có bảng giá chung cho mọi cloud. Đơn vị tính, điều kiện dừng tính phí và tên trạng thái khác nhau theo provider, region, loại instance, hệ điều hành, license và hợp đồng. Cần xác minh pricing và billing meter của đúng dịch vụ đang dùng.

### 1.1. Chi phí thực tế khác với chi phí niêm yết

Giá niêm yết theo giờ hoặc theo GiB-tháng chỉ là một phần. Hóa đơn có thể chịu ảnh hưởng bởi:

- Region, availability zone và loại tài nguyên.
- Hệ điều hành, license, kiến trúc CPU/GPU và loại instance.
- On-demand, spot/preemptible, reserved capacity hoặc commitment.
- Thời lượng tính tối thiểu, đơn vị làm tròn và lịch thanh toán.
- Dung lượng, IOPS, throughput và loại storage.
- Data transfer nội vùng, liên zone, liên region và Internet egress.
- Discount, credit, tax, support plan và phí marketplace.

Khi so sánh hai kiến trúc, dùng cùng phạm vi chi phí và cùng giả định tải. Ví dụ, so sánh VM với serverless phải tính cả load balancer, database, log, network và chi phí giữ warm capacity nếu có.

## 2. Tài nguyên nhàn rỗi và chi phí idle

Một tài nguyên được gọi là idle khi được cấp phát nhưng ít hoặc không tạo ra công việc hữu ích trong một khoảng thời gian. Idle không nhất thiết có nghĩa là hoàn toàn không có CPU usage: VM có thể chạy agent, health check, cron hoặc daemon nền dù ứng dụng không có request.

Các dạng idle thường gặp:

- VM production chạy 24/7 nhưng traffic chỉ tập trung vài giờ mỗi ngày.
- Máy dev/test hoặc demo không được tắt sau giờ làm việc.
- Instance được cấp quá lớn so với workload thực tế.
- Node Kubernetes có nhiều CPU/RAM allocatable nhưng pod sử dụng thấp.
- GPU instance được giữ sẵn nhưng job không chạy liên tục.
- Replica standby có utilization thấp nhưng được giữ để đáp ứng RTO.
- Môi trường staging tồn tại liên tục dù chỉ cần dùng trong thời gian kiểm thử.

### 2.1. Idle utilization và billed time

Ví dụ một VM 8 vCPU chạy 730 giờ trong tháng, trung bình dùng 5% CPU. Nếu giá compute là 0,40 USD/giờ, chi phí compute vẫn xấp xỉ:

\[
730\times0.40=292\text{ USD/tháng}
\]

CPU usage 5% không có nghĩa hóa đơn chỉ tính 5% giá. Với mô hình tính theo instance-hour, người dùng trả cho capacity đã cấp phát trong thời gian tính phí. Một số dịch vụ có billing theo mức sử dụng hoặc theo giây; cần kiểm tra meter thực tế.

### 2.2. Đo mức idle có ý nghĩa

Không nên kết luận VM dư thừa chỉ vì CPU trung bình thấp. Cần xem:

- CPU p50/p95/p99, peak và run queue.
- Memory working set, available memory, swap và OOM history.
- Network throughput, connection count và request rate.
- Disk IOPS, throughput, latency và queue depth.
- Application throughput, latency, error rate và queue backlog.
- Thời gian scale-out, warm-up và yêu cầu availability.
- Lịch batch, mùa vụ và peak hiếm gặp.

Một máy có CPU thấp nhưng RAM gần đầy hoặc disk I/O cao có thể vẫn đang sử dụng tốt tài nguyên. Ngược lại, máy CPU/RAM đều thấp trong nhiều tuần và không có vai trò standby có thể là ứng viên rightsizing hoặc scheduling.

### 2.3. Idle có chủ đích và idle lãng phí

Một số capacity nhàn rỗi được giữ có chủ đích:

- Replica HA để chịu lỗi node/zone.
- Warm standby để đạt RTO ngắn.
- Headroom để hấp thụ burst hoặc autoscaling delay.
- GPU/CPU capacity được đặt trước cho job có deadline.
- Bastion, monitoring hoặc security appliance cần sẵn sàng liên tục.

Không nên xóa capacity dự phòng chỉ dựa trên utilization thấp. Cần đối chiếu failure scenario, RTO/RPO, peak demand và chi phí downtime. Phần idle không có owner, không có mục đích hoặc vượt xa headroom đã định nghĩa mới là đối tượng ưu tiên tối ưu.

## 3. Trạng thái VM và tác động đến billing

Các nền tảng thường có nhiều trạng thái vòng đời. Tên và billing behavior không hoàn toàn giống nhau giữa các provider.

| Trạng thái khái niệm | Ý nghĩa | Compute charge | Tài nguyên đi kèm |
|---|---|---|---|
| Running | VM đang được cấp phát và thực thi | Thường tính theo meter compute | Disk, IP, network, monitoring và license có thể tính riêng |
| Stopped / powered off | Guest OS đã tắt nhưng instance có thể vẫn được giữ/cấp phát | Có nền tảng vẫn tính compute hoặc một phần capacity | Disk và nhiều tài nguyên phụ trợ tiếp tục tính |
| Stopped / deallocated | Compute capacity được giải phóng khỏi host theo semantics của provider | Thường ngừng tính compute instance; cần xác minh dịch vụ cụ thể | Disk, snapshot, IP, LB, NAT, backup, commitment có thể vẫn tính |
| Suspended / hibernated | Trạng thái RAM hoặc VM được lưu để resume | Có thể có cách tính riêng; storage trạng thái lưu có thể bị tính | Disk/snapshot và tài nguyên phụ trợ vẫn có thể tính |
| Terminated / deleted | Instance resource đã bị xóa | Meter compute của instance kết thúc theo chính sách | Volume, snapshot, IP, NIC, backup, log hoặc commitment có thể còn tồn tại |

### 3.1. Stop trong guest OS khác với deallocate ở control plane

Lệnh shutdown bên trong Linux/Windows thường yêu cầu guest OS tắt máy. Tùy nền tảng, instance có thể chuyển sang trạng thái stopped nhưng vẫn giữ host allocation hoặc được tự động deallocate. Trên một số dịch vụ, thao tác stop từ portal/API giải phóng compute allocation; trên dịch vụ khác, stop và deallocate là hai hành động riêng.

Không suy luận trạng thái billing chỉ từ việc console hiển thị “Stopped”. Hãy kiểm tra trạng thái chi tiết, billing documentation và usage meter. Nếu mục tiêu là ngừng chi phí compute, cần xác nhận instance đã đạt trạng thái không còn tính compute theo provider.

### 3.2. Điều gì có thể mất khi deallocate?

Khi giải phóng compute, một số thuộc tính có thể thay đổi:

- Host vật lý hoặc placement có thể thay đổi khi khởi động lại.
- Public/dynamic IP có thể được cấp địa chỉ khác nếu không giữ static IP.
- Local/ephemeral disk có thể bị xóa.
- RAM state và process state không được giữ nếu không có cơ chế hibernation.
- Thời gian boot, bootstrap và warm cache sẽ phát sinh khi bật lại.
- Quota/capacity của instance type hoặc GPU có thể không còn sẵn ở thời điểm start.

Trước khi tự động stop/deallocate, cần lưu dữ liệu bền vững ra volume hoặc dịch vụ storage phù hợp, kiểm tra static IP/DNS, đảm bảo workload có thể khởi động lại và xác định ai được phép bật lại.

### 3.3. Xóa VM chưa chắc xóa mọi tài nguyên

Nhiều hệ thống cho phép giữ boot disk, data disk, NIC, IP hoặc snapshot khi xóa instance. Đây là hành vi hữu ích khi cần phục hồi hoặc tái tạo VM, nhưng cũng dễ tạo orphaned resources. Quy trình terminate cần chỉ rõ tài nguyên nào giữ lại, owner, thời hạn retention và điều kiện xóa.

## 4. Storage tiếp tục tính phí khi máy dừng

Storage thường có vòng đời độc lập với VM. Khi instance dừng hoặc bị xóa, volume vẫn tồn tại cho đến khi được detach/delete theo đúng quy trình. Đây là một trong những nguyên nhân phổ biến khiến hóa đơn vẫn tăng sau khi “tắt máy”.

### 4.1. Boot volume và data volume

Chi phí block storage có thể phụ thuộc:

- Dung lượng provisioned (GiB-tháng), không chỉ dung lượng đã ghi.
- Loại volume hoặc storage tier.
- IOPS/throughput provisioned ngoài mức cơ bản.
- Dung lượng tối thiểu hoặc đơn vị làm tròn của dịch vụ.
- Snapshot, replication và cross-region copy.

Ví dụ, VM có boot disk 100 GiB và data disk 500 GiB. Nếu deallocate VM nhưng giữ hai volume, chi phí storage vẫn tiếp tục theo tổng dung lượng và cấu hình của chúng. Giảm vCPU hoặc stop VM không tự động giảm dung lượng volume.

### 4.2. Snapshot và backup

Snapshot có thể được tính theo dung lượng dữ liệu snapshot lưu trữ, số bản sao, tier, region hoặc thao tác copy/restore. Một số dịch vụ dùng snapshot incremental, một số có cách tính khác; không nên mặc định mọi snapshot đều chỉ lưu phần thay đổi.

Các nguồn chi phí thường gặp:

- Snapshot cũ sau khi VM hoặc volume đã bị xóa.
- Backup policy giữ nhiều recovery point hơn yêu cầu.
- Cross-region backup copy.
- Backup vault có phí quản lý hoặc minimum retention.
- Restore test tạo volume/VM tạm nhưng không được dọn sau kiểm thử.

Không xóa backup chỉ để giảm hóa đơn nếu chưa xác minh retention, legal hold, RPO/RTO và khả năng phục hồi. Nên có lifecycle policy và owner cho từng nhóm backup.

### 4.3. Local/ephemeral storage

Local NVMe hoặc ephemeral disk thường gắn với vòng đời host/instance và có thể mất khi stop/deallocate, terminate hoặc migrate tùy dịch vụ. Dù không có dòng phí storage riêng, chi phí của local storage có thể đã nằm trong giá instance. Nếu workload cần dữ liệu tồn tại, phải chuyển sang block/file/object storage hoặc database bền vững.

## 5. Network và địa chỉ IP đi kèm

Một VM có thể không chạy nhưng các thành phần network vẫn được cấp phát và tính phí độc lập.

### 5.1. Public IP và địa chỉ tĩnh

Public IPv4, static IP hoặc elastic IP có thể phát sinh phí theo thời gian giữ địa chỉ, trạng thái attach hoặc chính sách của provider. Một số nền tảng tính phí cả địa chỉ đang gắn với VM; một số tính khác nhau giữa IP được sử dụng và IP không gắn. Giá và điều kiện thay đổi theo khu vực và thời điểm.

Khi stop/deallocate hoặc xóa VM, cần kiểm tra:

- IP có được giữ lại hay tự giải phóng?
- DNS record có trỏ đến IP cũ không?
- Static IP có còn cần cho allowlist, callback hoặc đối tác không?
- IP không gắn với resource nào có thể thu hồi không?

Không giải phóng IP chỉ để tiết kiệm nếu hệ thống cần địa chỉ cố định. Có thể thay bằng private connectivity, load balancer endpoint hoặc DNS-based routing nếu phù hợp.

### 5.2. NAT gateway, firewall và private endpoint

NAT gateway, managed firewall, VPN gateway và một số private endpoint có phí theo giờ, dung lượng xử lý hoặc data processed. Nếu VM dừng nhưng NAT gateway vẫn phục vụ các workload khác, phí vẫn phát sinh. Nếu NAT chỉ được tạo cho môi trường dev/test đã ngừng, có thể cân nhắc gỡ hoặc dùng thiết kế network khác.

Trước khi xóa NAT/firewall, cần kiểm tra route table và mọi workload đang phụ thuộc. Một thay đổi nhằm giảm chi phí có thể làm mất egress cập nhật package, gọi API, gửi log hoặc kết nối dịch vụ bên ngoài.

### 5.3. Load balancer và health check

Load balancer thường có phí theo thời gian, capacity unit, rule, connection hoặc dữ liệu xử lý tùy nhà cung cấp. Khi backend VM dừng, load balancer có thể vẫn tồn tại và tiếp tục tính phí. Health check liên tục cũng tạo request và log.

Nếu môi trường không còn sử dụng, hãy xác minh DNS, listener, target group, WAF policy, certificate và client trước khi xóa load balancer. Nếu cần duy trì endpoint HA, chi phí load balancer là chi phí nền có chủ đích.

### 5.4. Data transfer và lưu lượng liên zone/region

Chi phí network có thể đến từ:

- Internet egress.
- Traffic giữa availability zone.
- Traffic giữa region hoặc cloud provider.
- NAT processing hoặc gateway data processing.
- Traffic qua CDN, private link hoặc interconnect.
- Cross-zone load balancing và replication.

VM idle có thể không tạo nhiều egress, nhưng replica database, backup, log hoặc replication vẫn truyền dữ liệu. Cần xem byte transfer theo source/destination, không chỉ tổng network throughput trên VM.

## 6. Tài nguyên phụ trợ và chi phí nền

### 6.1. Monitoring, logging và security agent

Agent trên VM có thể gửi metric, log, trace, inventory và security telemetry ngay cả khi ứng dụng không có traffic. Chi phí có thể tính theo số host, volume ingest, retention, số lần truy vấn hoặc dung lượng lưu.

Để giảm chi phí mà vẫn giữ khả năng quan sát:

- Loại bỏ log debug hoặc duplicate không cần thiết.
- Đặt retention khác nhau cho log vận hành, audit và security.
- Giảm metric cardinality và tránh thu thập label có giá trị thay đổi liên tục.
- Dùng sampling cho trace theo policy và giữ 100% trace lỗi quan trọng nếu nền tảng hỗ trợ.
- Tắt telemetry của môi trường đã xóa sau khi lưu đủ bằng chứng cần thiết.

Không tắt audit/security logging trên production chỉ để giảm chi phí. Hãy tối ưu volume, retention và sampling theo yêu cầu bảo mật.

### 6.2. License và phần mềm thương mại

Một số image có license đã bao gồm trong giá VM; một số dùng BYOL (Bring Your Own License), license theo core/socket/host hoặc subscription riêng. Chi phí license có thể phụ thuộc số vCPU được cấp phát, loại host hoặc thời gian đăng ký, không nhất thiết giảm ngay khi guest OS tắt.

Khi stop hoặc resize, cần kiểm tra điều khoản license, license mobility, minimum core và hợp đồng marketplace. Không giả định xóa VM sẽ tự động kết thúc mọi nghĩa vụ license hoặc subscription.

### 6.3. Orchestration và control plane

Cluster Kubernetes có thể có phí control plane/management riêng; ngoài ra còn có node, load balancer, persistent volume, NAT, registry, log và service mesh. Một cluster rỗng vẫn có thể phát sinh phí nếu control plane hoặc resource phụ trợ còn tồn tại.

Các thành phần như autoscaler, controller, node pool minimum, daemonset và system pod tạo mức sử dụng nền. Cần phân biệt chi phí nền cần thiết để cluster hoạt động với capacity bị giữ lại do cấu hình quá cao.

### 6.4. Chi phí phục hồi và dự phòng

Warm standby, backup, replication, secondary region và reserved capacity có thể ít sử dụng trong ngày thường nhưng là một phần của thiết kế HA/DR. Cần đưa chúng vào cost model như chi phí resilience, rồi so sánh với mức tổn thất có thể xảy ra nếu không có dự phòng.

Một replica standby không có traffic vẫn có thể có giá trị nếu cần failover nhanh. Câu hỏi đúng là mức dự phòng có tương xứng với criticality, RTO/RPO và rủi ro hay không.

## 7. Chi phí idle trong container và Kubernetes

Container không tự loại bỏ chi phí compute. Chi phí phụ thuộc node hoặc dịch vụ compute bên dưới, số replica tối thiểu, request/limit, thời gian node chạy và các dịch vụ đi kèm.

### 7.1. Node capacity và pod utilization

Một node có thể được cấp 16 vCPU và 64 GiB RAM nhưng chỉ chạy vài pod nhỏ. Nếu node vẫn được giữ trong node pool, chi phí compute thường tiếp tục theo thời gian node được cấp phát. Scheduler đặt pod dựa trên resource requests và các ràng buộc khác; requests quá cao có thể làm node trông “đầy” dù usage thực thấp, khiến autoscaler tạo thêm node.

Các nguồn lãng phí thường gặp:

- Pod requests cao hơn mức sử dụng ổn định và peak thực tế.
- Replica count cố định lớn dù traffic thay đổi theo giờ.
- Node pool có minimum size cao hơn nhu cầu.
- DaemonSet hoặc system workload chiếm capacity trên mọi node.
- Pod bị pending do affinity, taint, topology hoặc thiếu loại tài nguyên cụ thể.
- Node không được scale-in vì PDB, local storage hoặc workload không cho phép eviction.

Rightsizing cần dựa trên request, limit, usage và peak. Giảm request quá mạnh có thể tăng packing density nhưng dẫn đến contention, throttling hoặc OOM. Cần kiểm thử workload và giữ headroom cho node failure/rolling update.

### 7.2. Autoscaling và scale-to-zero

Cluster autoscaler hoặc node auto-provisioner có thể giảm node khi workload giảm, nhưng có thể giữ minimum node count để đáp ứng availability hoặc thời gian khởi động. Horizontal Pod Autoscaler có thể giảm replica nhưng không giải phóng node nếu pod khác vẫn nằm trên đó hoặc node pool có minimum.

Scale-to-zero có thể giảm compute cost khi không có traffic, nhưng cần xem:

- Thời gian khởi động node/pod và image pull.
- Cold start và thời gian warm cache.
- Kết nối đến database, secret manager và dependency.
- Pod disruption, persistent volume và local state.
- Yêu cầu latency đầu tiên sau thời gian idle.
- Chi phí control plane, LB, IP, storage và log vẫn còn.

Với workload cần phản hồi ngay, giữ một replica hoặc node tối thiểu có thể là lựa chọn phù hợp. Với batch hoặc môi trường dev/test, scale-to-zero thường dễ áp dụng hơn.

### 7.3. Bin packing và phân nhóm node

Đặt workload tương thích trên node phù hợp giúp tăng utilization và giảm số node. Tuy nhiên, gom tất cả workload vào ít node làm tăng blast radius khi node lỗi và có thể gây noisy neighbor. Cần cân bằng bin packing với topology spread, anti-affinity, isolation, GPU/CPU family và yêu cầu bảo mật.

Node pool riêng cho GPU hoặc memory-optimized có thể đắt hơn nhưng tránh trả chi phí cho loại tài nguyên lớn khi workload không cần. Taints/tolerations và node affinity giúp workload dùng đúng pool; node không còn workload cần được scale-in hoặc xóa theo chính sách.

## 8. Chi phí idle trong serverless

Serverless thường tính theo invocation, thời gian thực thi, memory/CPU được cấp, số request hoặc tài nguyên provisioned. Khi không có invocation, compute charge có thể rất thấp hoặc bằng không ở mô hình pay-per-use, nhưng không có nghĩa toàn bộ kiến trúc không còn chi phí.

Các khoản có thể tiếp tục tồn tại:

- Provisioned concurrency, minimum instances hoặc always-on container.
- API gateway, load balancer, private endpoint và NAT.
- Queue, event bus, database, cache hoặc storage.
- Log, trace, metric, secret và key management.
- Workflow orchestration, scheduler và state machine.
- Network egress hoặc data processing.

### 8.1. Provisioned concurrency và warm capacity

Provisioned concurrency hoặc minimum instances giữ môi trường thực thi sẵn sàng để giảm cold start. Capacity này có thể bị tính phí trong thời gian được giữ, ngay cả khi ít request. Cần đo tỷ lệ cold start, latency mục tiêu và traffic pattern để quyết định mức warm capacity.

Với workload theo giờ, có thể đặt lịch tăng/giảm provisioned capacity. Với traffic đột biến khó dự đoán, cần cân nhắc chi phí giữ warm so với độ trễ cold start và tỷ lệ timeout.

### 8.2. So sánh serverless với VM

VM có thể kinh tế hơn khi tải ổn định và utilization cao trong phần lớn thời gian; serverless có thể phù hợp với workload thưa, bursty hoặc khó dự báo. Tuy nhiên, phải so sánh theo goodput và chi phí toàn kiến trúc, bao gồm gateway, database, logging, egress và minimum capacity.

Một hàm có thời gian thực thi ngắn nhưng gọi database quá nhiều có thể làm chi phí database tăng. Một dịch vụ serverless có concurrency cao có thể tạo burst kết nối đến database; cần connection pooling/proxy hoặc giới hạn concurrency.

## 9. Commitment, reservation và chi phí máy không chạy

Cloud provider có thể cung cấp các hình thức giảm giá khi cam kết sử dụng trong một thời hạn hoặc đặt trước capacity. Ví dụ tên gọi phổ biến gồm reserved instances, savings plans, committed use discounts hoặc dedicated host reservation.

Điểm quan trọng: **cam kết thanh toán và trạng thái VM là hai việc khác nhau**. Nếu tổ chức đã cam kết một mức chi tiêu hoặc capacity, nghĩa vụ thanh toán có thể tiếp tục dù VM bị stop hoặc workload không sử dụng hết. Việc dừng VM không tự động hủy reservation/commitment.

### 9.1. Phân biệt reservation và usage

- Reservation có thể bảo đảm capacity hoặc giảm giá cho mức sử dụng đủ điều kiện.
- Savings/committed spend plan có thể áp dụng discount cho mức chi tiêu compute đủ điều kiện trong kỳ.
- Dedicated host reservation có thể tính phí theo host capacity và thời hạn.
- Spot/preemptible có giá thấp hơn nhưng có thể bị thu hồi và không phù hợp mọi workload.

Tên gọi, điều kiện áp dụng và cách tính khác nhau theo provider. Cần đọc hợp đồng và billing report để hiểu khoản nào là usage, khoản nào là commitment, khoản nào là unused commitment.

### 9.2. Rủi ro khi mua commitment quá lớn

Nếu cam kết dựa trên mức sử dụng hiện tại nhưng workload giảm, kiến trúc thay đổi hoặc chuyển sang serverless, tổ chức có thể phải trả cho commitment chưa dùng. Nếu commitment không linh hoạt theo family, region, platform hoặc OS, việc rightsizing cũng có thể không tận dụng được discount.

Trước khi cam kết:

1. Phân tích usage lịch sử đủ dài để nhận ra mùa vụ và xu hướng.
2. Tách baseline ổn định khỏi peak và workload tạm thời.
3. Xác định phạm vi áp dụng, family/region/OS và tính linh hoạt.
4. Tính chi phí nếu usage thấp hơn dự báo.
5. Chừa một phần nhu cầu cho on-demand/spot nếu cần linh hoạt.
6. Rà soát commitment utilization và coverage định kỳ.

## 10. Công thức tính chi phí idle và máy dừng

Một mô hình ước lượng đơn giản cho workload VM:

```text
monthly_total_cost = compute_cost
                   + storage_cost
                   + snapshot_backup_cost
                   + public_ip_cost
                   + network_gateway_cost
                   + load_balancer_cost
                   + monitoring_logging_cost
                   + license_cost
                   + commitment_cost_not_covered_by_usage
```

Chi phí compute có thể ước lượng:

\[
C_{compute}=N_{instances}\times H_{billable}\times P_{hour}
\]

Trong đó `H_billable` là số giờ thực sự tính phí theo trạng thái và chính sách provider, không mặc định bằng thời gian VM tồn tại. Storage có thể ước lượng:

\[
C_{storage}=\sum_i Capacity_i\times P_{GiB-month,i}
\]

Nếu storage tính thêm IOPS, throughput, request hoặc snapshot, cần cộng các meter đó riêng. Public IP, NAT, LB và log thường có công thức tính phí riêng.

### 10.1. So sánh running, deallocated và deleted

Ví dụ giả định để minh họa:

- VM: 0,40 USD/giờ.
- Boot/data disk: tổng 600 GiB với giá 0,08 USD/GiB-tháng.
- Public IP: 0,005 USD/giờ.
- Load balancer được phân bổ cho workload: 25 USD/tháng.
- Snapshot/backup: 12 USD/tháng.
- Một tháng quy ước 730 giờ.

| Trạng thái | Compute | Disk | IP | LB | Backup | Tổng ước tính |
|---|---:|---:|---:|---:|---:|---:|
| Running cả tháng | 292,00 | 48,00 | 3,65 | 25,00 | 12,00 | 380,65 USD |
| Deallocated cả tháng, giữ disk/IP/LB/backup | 0,00 | 48,00 | 3,65 | 25,00 | 12,00 | 88,65 USD |
| Deleted, đã xóa disk/IP/LB, giữ backup | 0,00 | 0,00 | 0,00 | 0,00 | 12,00 | 12,00 USD |

Các mức giá hoàn toàn giả định và chỉ minh họa cách phân rã. Trong thực tế, public IP có thể có giá khác theo trạng thái, disk có thể tính theo tier/IOPS, load balancer có thể dùng chung nhiều workload, và backup có thể được tính theo dung lượng thay đổi. Nếu có commitment, tổng chi phí tiền mặt có thể không giảm theo bảng này vì nghĩa vụ cam kết vẫn còn.

### 10.2. Chi phí theo thời gian bật/tắt

Nếu môi trường dev/test chỉ chạy 10 giờ mỗi ngày trong 22 ngày làm việc, compute billable time có thể giảm từ 730 giờ xuống 220 giờ mỗi tháng nếu stop/deallocate thực sự ngừng meter compute:

\[
Saving_{compute}=1-\frac{220}{730}\approx69.9\%
\]

Đây là phần tiết kiệm compute lý thuyết trước khi tính thời gian khởi động, license, storage, IP, gateway, LB và các khoản cố định. Lịch bật/tắt cần tính cả giờ chuẩn bị, kiểm thử tự động và thời gian người dùng cần truy cập.

## 11. Phân bổ chi phí cho tài nguyên nhàn rỗi

Để biết idle cost thuộc về ai, cần gắn tài nguyên với owner, ứng dụng, môi trường và mục đích sử dụng. Nếu không có metadata, nhóm FinOps khó phân biệt tài nguyên dự phòng hợp lệ với tài nguyên bị bỏ quên.

### 11.1. Tag/label và cost allocation

Các thuộc tính thường dùng:

- `owner`: nhóm hoặc cá nhân chịu trách nhiệm.
- `application` / `service`: hệ thống sử dụng tài nguyên.
- `environment`: production, staging, dev, test hoặc sandbox.
- `cost-center` / `business-unit`: đơn vị chịu chi phí.
- `lifecycle`: temporary, persistent, standby hoặc scheduled.
- `expires-at`: thời điểm cần rà soát/xóa tài nguyên tạm.
- `criticality`: mức độ quan trọng hoặc tier dịch vụ.

Tag cần được áp dụng nhất quán qua IaC và policy; một số resource như data transfer, shared NAT hoặc load balancer có thể cần quy tắc phân bổ thay vì tag trực tiếp. Không đưa secret, dữ liệu cá nhân hoặc thông tin nhạy cảm vào tag.

### 11.2. Chi phí shared resource

Một load balancer hoặc NAT gateway có thể phục vụ nhiều ứng dụng. Có thể phân bổ theo:

- Tỷ lệ byte/request thực tế.
- Số connection hoặc thời gian sử dụng.
- Số target/endpoint hoặc mức capacity được dành riêng.
- Tỷ trọng workload theo một quy tắc thống nhất.

Nên công bố phương pháp phân bổ và giữ một phần chi phí ở nhóm platform nếu tài nguyên được vận hành chung. Phân bổ không chính xác có thể tạo động lực sai, ví dụ một nhóm bị tính phí cho traffic của nhóm khác.

### 11.3. Idle cost theo ứng dụng

Có thể ước lượng phần chi phí compute nhàn rỗi bằng cách kết hợp giá tài nguyên và thời gian không có công việc hữu ích. Tuy nhiên, utilization không phải meter billing nên đây là chỉ số quản trị, không phải hóa đơn chính thức.

Ví dụ một VM 4 vCPU có giá 0,20 USD/giờ, chạy 730 giờ/tháng và được đánh giá idle 70% thời gian. Chi phí compute gắn với thời gian idle ước lượng:

\[
C_{idle}=0.20\times730\times0.70=102.20\text{ USD}
\]

Con số này giúp ưu tiên rà soát. Không có nghĩa có thể tiết kiệm toàn bộ 102,20 USD: một phần idle có thể là headroom, HA hoặc capacity cần để đáp ứng peak. Cần chạy test rightsizing/scheduling và đo tác động trước khi chốt saving.

## 12. Phát hiện orphaned và forgotten resources

Orphaned resource là tài nguyên còn tồn tại nhưng không còn workload hoặc owner rõ ràng. Chúng thường xuất hiện sau khi VM/cluster bị xóa không đầy đủ, test kết thúc hoặc môi trường được tạo thủ công.

Các loại cần rà soát:

- Disk/volume không attach vào VM nào.
- Snapshot và backup không còn owner hoặc vượt retention.
- Public IP/NIC không còn được sử dụng.
- Load balancer, target group, NAT gateway hoặc firewall rule của môi trường đã xóa.
- GPU/VM reservation, dedicated host hoặc capacity commitment không được dùng.
- Kubernetes node pool, persistent volume, load balancer service hoặc registry artifact không còn workload.
- Log group, trace store, metric workspace và alert rule của dự án đã kết thúc.
- Static IP, DNS zone/record và certificate không còn endpoint.

### 12.1. Quy trình dọn dẹp an toàn

1. Tìm resource không có owner/tag hoặc không có liên kết đến workload đang hoạt động.
2. Kiểm tra metric sử dụng, attachment, access log và dependency trong một khoảng thời gian đủ đại diện.
3. Liên hệ owner hoặc nhóm platform để xác nhận mục đích.
4. Kiểm tra retention, backup, legal hold, DNS, allowlist và khả năng phục hồi.
5. Gắn trạng thái pending deletion và thời hạn thông báo nếu chính sách yêu cầu.
6. Snapshot/export dữ liệu cần giữ và xác minh khả năng restore.
7. Xóa theo thứ tự dependency, theo dõi lỗi sau thay đổi.
8. Cập nhật inventory và ghi nhận chi phí trước/sau.

Không tự động xóa volume chỉ vì nó đang unattached; volume đó có thể là bản dữ liệu dự phòng hoặc chờ failover. Tự động hóa nên có allowlist/denylist, owner notification, grace period và approval cho tài nguyên có dữ liệu.

## 13. Các biện pháp giảm chi phí idle

### 13.1. Rightsizing

Chọn loại VM/instance phù hợp với CPU, memory, network, storage và GPU thực tế. Có thể giảm vCPU/RAM hoặc chuyển sang family phù hợp nếu workload không cần cấu hình hiện tại.

Trước khi resize:

- Phân tích peak và percentile trong khoảng thời gian đại diện.
- Kiểm tra CPU steal/throttling, memory pressure, swap và OOM.
- Đo disk IOPS/throughput, network và GPU nếu có.
- Kiểm tra yêu cầu license theo core/host.
- Xác minh downtime, reboot, IP, storage attachment và compatibility.
- Chạy benchmark sau resize và giữ rollback option.

Không rightsize theo CPU average đơn lẻ. Máy có peak ngắn nhưng quan trọng hoặc cần chịu lỗi có thể cần capacity cao hơn mức trung bình.

### 13.2. Scheduling và auto-stop

Môi trường dev/test, build agent hoặc demo thường có lịch sử dụng rõ. Có thể tự động start trước giờ làm việc và stop/deallocate sau giờ, đồng thời gửi thông báo cho owner.

Quy tắc scheduling cần:

- Time zone và ngày nghỉ rõ ràng.
- Exclusion cho production, database hoặc workload có SLA.
- Kiểm tra job đang chạy, queue backlog và maintenance window trước khi stop.
- Gửi cảnh báo nếu stop/start thất bại.
- Giữ static IP hoặc cập nhật DNS nếu endpoint thay đổi.
- Xác minh sau khi start: health, agent, mount, secret và ứng dụng.

Auto-stop không nên áp dụng cho VM có vai trò HA/DR hoặc cần phục vụ request bất kỳ lúc nào nếu chưa đánh giá tác động.

### 13.3. Autoscaling và scale-to-zero

Autoscaling điều chỉnh capacity theo demand. Scale-in giúp giảm idle compute, còn scale-out giữ khả năng đáp ứng tải. Cần đặt min/max, cooldown, stabilization window và policy theo metric phù hợp.

Với workload batch hoặc event-driven, scale-to-zero có thể phù hợp. Với API latency nhạy cảm, cần giữ baseline replica hoặc dùng warm pool/provisioned capacity. Cần so sánh chi phí idle với cold-start penalty và chi phí giữ capacity.

### 13.4. Tách lịch compute khỏi storage lifecycle

Stop VM không đồng nghĩa xóa disk. Có thể giữ data disk nhưng xóa compute tạm, hoặc snapshot dữ liệu rồi xóa volume khi không cần truy cập nhanh. Cần lựa chọn theo thời gian phục hồi và chi phí retrieval/restore.

Ví dụ, môi trường test có thể giữ image và snapshot định kỳ, chỉ tạo VM khi cần. Tuy nhiên, tạo lại VM từ image/snapshot sẽ tốn thời gian và có thể phát sinh chi phí restore, data transfer hoặc bootstrapping.

### 13.5. Tối ưu network và shared services

- Gỡ load balancer/NAT/private endpoint không còn dùng sau khi kiểm tra dependency.
- Tối ưu placement để giảm cross-zone data transfer khi yêu cầu HA cho phép.
- Dùng cache/CDN khi giúp giảm egress hoặc tải origin tổng thể.
- Chọn NAT/egress architecture theo traffic pattern và yêu cầu bảo mật.
- Kiểm tra log/data transfer từ agent chạy trên máy idle.

Không gom workload vào một zone chỉ để giảm phí cross-zone nếu điều đó phá vỡ availability objective. Hãy định lượng phần tiết kiệm so với rủi ro tăng lên.

### 13.6. Quản lý commitment

Mua commitment cho baseline ổn định, không dựa toàn bộ vào peak ngắn hạn. Theo dõi coverage và utilization của commitment; điều chỉnh danh mục khi chuyển instance family, region, OS hoặc kiến trúc. Commitment unused cần được báo cáo riêng để tránh nhầm với tài nguyên VM đang idle.

## 14. Tính saving thực tế và theo dõi sau tối ưu

Saving không chỉ là giá niêm yết trước trừ giá sau. Cần so sánh chi phí thực tế trên cùng phạm vi, cùng thời gian và cùng mức dịch vụ.

```text
gross_saving = baseline_cost - optimized_cost
net_saving = gross_saving - migration_cost - operational_cost_change

cost_per_good_request = total_workload_cost / successful_requests
cost_per_job = total_workload_cost / jobs_completed_successfully
```

Khi tối ưu, theo dõi đồng thời:

- Tổng chi phí và chi phí theo service/environment/owner.
- Chi phí compute running, stopped/deallocated và commitment.
- Storage, snapshot, backup, IP, NAT, LB và data transfer.
- Utilization, capacity headroom, latency, error rate và availability.
- Chi phí trên request/job thành công.
- Tỷ lệ tài nguyên không có owner và orphaned resource.

Một thay đổi chỉ được coi là tối ưu tốt khi giảm chi phí mà vẫn đáp ứng SLO, HA, bảo mật và yêu cầu phục hồi. Nếu tiết kiệm 20% compute nhưng làm RTO tăng gấp đôi hoặc tăng lỗi production, cần đánh giá lại trade-off.

## 15. Ví dụ thực hành: môi trường dev/test chạy theo lịch

Giả sử một nhóm có 5 VM phục vụ dev/test. Mỗi VM có giá compute giả định 0,25 USD/giờ, chạy liên tục 730 giờ/tháng. Mỗi VM có 200 GiB disk với giá 0,08 USD/GiB-tháng. Một load balancer dùng chung có phí phân bổ 30 USD/tháng và public IP có giá giả định 0,005 USD/giờ cho mỗi VM.

### 15.1. Chi phí trước tối ưu

| Thành phần | Cách tính | Chi phí/tháng |
|---|---|---:|
| Compute | 5 × 730 × 0,25 USD | 912,50 USD |
| Disk | 5 × 200 × 0,08 USD | 80,00 USD |
| Public IP | 5 × 730 × 0,005 USD | 18,25 USD |
| Load balancer | Phân bổ theo giả định | 30,00 USD |
| Tổng | | **1.040,75 USD** |

### 15.2. Chạy theo lịch

Nếu mỗi VM chỉ cần chạy 10 giờ/ngày trong 22 ngày làm việc, compute time giảm còn 220 giờ/tháng:

| Thành phần | Cách tính | Chi phí/tháng |
|---|---|---:|
| Compute | 5 × 220 × 0,25 USD | 275,00 USD |
| Disk | Giữ nguyên 5 × 200 × 0,08 USD | 80,00 USD |
| Public IP | Giữ IP liên tục theo giả định | 18,25 USD |
| Load balancer | Vẫn tồn tại | 30,00 USD |
| Tổng | | **403,25 USD** |

Tiết kiệm giả định là 637,50 USD/tháng, tương đương khoảng 61,3% tổng chi phí trong phạm vi ví dụ. Nếu deallocate giải phóng public IP, có thể giảm thêm phí IP nhưng cần xử lý DNS/allowlist khi bật lại. Nếu xóa load balancer ngoài giờ, có thể giảm thêm nhưng cần tính thời gian tạo lại và khả năng truy cập.

### 15.3. Điều kiện vận hành

- Xác nhận không có test automation hoặc job dài chạy sau giờ.
- Gửi thông báo cho developer trước khi stop.
- Dừng VM theo thứ tự phù hợp và kiểm tra filesystem/application shutdown.
- Giữ disk nếu cần dữ liệu; dùng snapshot nếu môi trường có thể tạo lại.
- Start trước giờ làm việc đủ lâu để hoàn tất boot, patch check và health check.
- Kiểm tra IP, DNS, VPN, secret, agent và kết nối database sau khi bật.
- Có cơ chế opt-out tạm thời cho nhóm đang chạy test dài, kèm thời hạn.

Ví dụ này không đại diện cho mọi bảng giá. Chi phí disk, IP, LB và license có thể khác theo provider; savings thực tế cần đối chiếu billing export sau vài chu kỳ.

## 16. Dashboard và cảnh báo chi phí

Một dashboard FinOps cho compute nên tách chi phí theo trạng thái và loại tài nguyên:

| Góc nhìn | Chỉ số nên có | Câu hỏi cần trả lời |
|---|---|---|
| Running compute | Instance-hour, vCPU-hour, GPU-hour, chi phí theo family | Workload nào chiếm phần lớn compute spend? |
| Idle compute | Usage percentile, billed hours, idle estimate | Máy nào cấp phát lâu nhưng ít công việc? |
| Stopped/deallocated | Số VM, disk/IP/LB còn tồn tại, chi phí phụ trợ | Tắt máy rồi còn khoản nào tiếp tục tính? |
| Orphaned resource | Unattached disk, unused IP, idle LB/NAT, snapshot cũ | Tài nguyên nào không còn owner/workload? |
| Commitment | Coverage, utilization, unused commitment | Có đang trả tiền cho cam kết không dùng? |
| Network/storage | Egress, cross-zone, IOPS, snapshot/backup growth | Chi phí phụ trợ tăng do đâu? |
| Unit economics | Cost/request, cost/job, cost/tenant | Chi phí có tăng nhanh hơn giá trị tạo ra không? |

### 16.1. Cảnh báo hữu ích

- VM dev/test chạy ngoài lịch được phê duyệt.
- Instance idle vượt ngưỡng trong nhiều ngày và không có tag standby.
- Disk unattached hoặc public IP không gắn với resource.
- Snapshot/backup vượt retention hoặc tăng bất thường.
- Load balancer/NAT gateway không có traffic nhưng vẫn phát sinh phí.
- Commitment utilization thấp hoặc coverage thay đổi mạnh.
- Chi phí theo service/cost center vượt ngân sách hoặc tăng đột biến.
- Tài nguyên không có owner, environment hoặc expiration date.

Cảnh báo cần cung cấp resource ID, owner, cost estimate, thời gian idle và hướng xử lý. Không tự động xóa resource có dữ liệu hoặc vai trò HA chỉ dựa trên ngưỡng idle.

## 17. Guardrail và chính sách vòng đời tài nguyên

Để giảm chi phí bị bỏ quên, có thể đặt guardrail trong quy trình tạo và xóa resource:

- Yêu cầu tag owner, application, environment và cost center.
- Bắt buộc `expires-at` cho sandbox/test resource tạm thời.
- Tự động stop môi trường không production theo lịch đã thống nhất.
- Giới hạn instance type/GPU hoặc quota theo nhóm và môi trường.
- Dùng IaC để quản lý lifecycle, tránh tài nguyên tạo thủ công không có state.
- Tạo workflow cảnh báo trước khi xóa disk/snapshot/IP orphaned.
- Đặt retention policy cho log, snapshot và backup theo loại dữ liệu.
- Theo dõi commitment utilization và yêu cầu review trước khi mua thêm.
- Định kỳ đối chiếu inventory cloud với CMDB/service catalog.

Policy nên có ngoại lệ cho HA/DR, security appliance, forensic retention và workload có deadline. Owner cần giải thích lý do và thời hạn review để ngoại lệ không trở thành tài nguyên vĩnh viễn không ai quản lý.

## 18. Những nhầm lẫn thường gặp

**CPU gần 0% nghĩa là không tốn chi phí.** Với VM tính phí theo thời gian instance, compute vẫn được tính trong lúc instance chạy dù CPU gần idle.

**Shutdown từ bên trong OS luôn ngừng billing compute.** Một số nền tảng phân biệt stopped với deallocated; cần kiểm tra trạng thái và billing meter thực tế.

**Dừng VM thì disk cũng dừng tính phí.** Volume còn tồn tại thường vẫn tính theo dung lượng và hiệu năng provisioned.

**Xóa VM sẽ xóa toàn bộ tài nguyên liên quan.** Disk, snapshot, IP, NIC, backup, log và commitment có thể còn lại.

**Không có traffic nghĩa là không có chi phí network.** NAT, load balancer, IP, endpoint hoặc gateway có thể có phí theo giờ; replication và log cũng có thể truyền dữ liệu.

**Serverless không có idle cost.** Provisioned concurrency, minimum instances, gateway, database, storage, log và network vẫn có thể phát sinh chi phí.

**Tài nguyên idle luôn là lãng phí.** Headroom, standby và warm capacity có thể cần để đáp ứng HA, burst hoặc RTO.

**Reserved capacity dừng tính phí khi VM bị stop.** Commitment hoặc reservation có thể tiếp tục tạo nghĩa vụ thanh toán độc lập với usage.

**Unattached disk có thể xóa ngay.** Disk có thể chứa dữ liệu cần phục hồi hoặc phục vụ DR; cần xác minh owner, backup và retention.

**Giảm chi phí luôn là tối ưu tốt.** Tối ưu phải giữ SLO, capacity sau lỗi, bảo mật và khả năng phục hồi trong giới hạn đã cam kết.

## 19. Checklist rà soát chi phí idle và tài nguyên đi kèm

### Inventory và billing

- [ ] Có inventory VM/instance, node, serverless, disk, snapshot, IP, LB, NAT và gateway.
- [ ] Đã phân biệt running, stopped, deallocated, suspended và terminated theo provider.
- [ ] Đã xác minh billing meter cho từng trạng thái thay vì suy luận từ tên trạng thái.
- [ ] Có tag owner, application, environment, cost center và lifecycle.
- [ ] Chi phí compute, storage, network, license, monitoring và commitment được tách riêng.

### Idle và scheduling

- [ ] Đã xem CPU/RAM/network/storage peak và workload profile đủ dài.
- [ ] Đã phân biệt idle có chủ đích với idle không có owner/mục đích.
- [ ] Dev/test có lịch start/stop và kiểm tra job trước khi dừng.
- [ ] Rightsizing được benchmark và có rollback.
- [ ] Autoscaling/scale-to-zero không phá SLO hoặc RTO.
- [ ] Capacity standby và headroom được giữ theo failure scenario đã xác định.

### Tài nguyên phụ trợ

- [ ] Disk, snapshot và backup có owner, retention và restore test.
- [ ] Public IP/NIC/DNS được rà soát trước khi giải phóng.
- [ ] LB, NAT, firewall, private endpoint và data transfer được phân bổ đúng.
- [ ] Log/metric/trace có retention và sampling phù hợp.
- [ ] License và marketplace subscription được kiểm tra theo hợp đồng.
- [ ] Commitment/reservation được theo dõi coverage và utilization.

### Kiểm soát và cải tiến

- [ ] Có cảnh báo orphaned resources, idle spend và budget anomaly.
- [ ] Quy trình xóa có owner confirmation, grace period và kiểm tra backup.
- [ ] Saving được tính trên cùng phạm vi và cùng kỳ so sánh.
- [ ] Cost per successful request/job được theo dõi cùng SLI/SLO.
- [ ] Ngoại lệ HA/DR và security có lý do, owner và ngày review.

## Kết luận

Chi phí compute được tạo bởi thời gian cấp phát CPU/RAM/GPU cùng nhiều tài nguyên đi kèm. VM idle vẫn có thể tính compute theo giờ; VM stopped/deallocated có thể ngừng meter compute nhưng disk, snapshot, IP, load balancer, NAT, backup, monitoring, license hoặc commitment vẫn tiếp tục tính phí. Kubernetes và serverless cũng có chi phí nền từ node tối thiểu, warm capacity, provisioned concurrency và dịch vụ phụ trợ. Muốn tối ưu bền vững, cần xác minh billing behavior theo provider, phân loại idle có chủ đích, quản lý lifecycle từng resource, rightsizing và scheduling theo workload, đồng thời giữ headroom, availability và khả năng phục hồi. Dashboard theo owner và cost per successful workload giúp đo saving thực tế mà không đánh đổi chất lượng dịch vụ.
