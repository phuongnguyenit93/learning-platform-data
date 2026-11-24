# Các thành phần chi phí: máy, đĩa, mạng, giấy phép và dịch vụ quản lý

Chi phí chạy workload compute trên cloud không chỉ là giá thuê máy ảo. Một ứng dụng có thể phát sinh chi phí từ CPU/RAM, ổ đĩa, snapshot và backup, lưu lượng mạng, địa chỉ IP, load balancer, hệ điều hành, phần mềm thương mại, dịch vụ quản lý và công cụ giám sát. Nếu chỉ so sánh giá một instance theo giờ, dự toán thường thiếu các khoản phụ trợ và có thể chênh đáng kể so với hóa đơn thực tế.

Để dự toán chính xác, cần phân rã chi phí theo thành phần, hiểu đơn vị tính của từng dịch vụ, đo mức sử dụng và gắn chi phí với workload tạo ra nó. Bài học này tập trung vào mô hình chi phí của workload compute, gồm máy, đĩa, mạng, giấy phép và dịch vụ quản lý; đồng thời hướng dẫn cách ước lượng, phân bổ và tối ưu chi phí theo đơn vị nghiệp vụ.

## 1. Nhìn tổng thể chi phí của một workload

Một workload chạy trên VM thường có các nhóm chi phí sau:

| Nhóm | Thành phần thường gặp | Cách tính phổ biến |
|---|---|---|
| Compute | VM/instance, CPU, RAM, GPU, host chuyên dụng | Theo giây, phút hoặc giờ; có thể theo số lần thực thi hoặc đơn vị capacity |
| Storage | Block volume, file storage, object storage, snapshot, backup | GB-tháng, IOPS/throughput provisioned, request hoặc dung lượng lưu trữ |
| Network | Data transfer, cross-zone/cross-region, NAT, load balancer, public IP, VPN | GB truyền, giờ tài nguyên, số request/connection hoặc capacity unit |
| License | Windows, SQL/database, middleware, security agent, phần mềm thương mại | Theo core/vCPU, socket, instance, user, host hoặc hợp đồng |
| Managed services | Managed database, cache, queue, monitoring, secrets, backup | Theo instance-hour, capacity, request, operation, dung lượng hoặc retention |
| Vận hành bổ trợ | Logging, metrics, tracing, support, migration và automation | Theo ingest, lưu trữ, số tài nguyên, gói hỗ trợ hoặc nhân công |

Mô hình tổng quát:

\[
\text{Total Cost} = C_{compute} + C_{storage} + C_{network} + C_{license} + C_{managed} + C_{operations}
\]

Đây là cách phân rã để lập dự toán. Hóa đơn thực tế có thể nhóm dịch vụ theo tên SKU, region, account hoặc billing meter khác nhau. Cần đối chiếu từng khoản với bảng giá và tài liệu billing của nhà cung cấp.

## 2. Chi phí máy ảo và năng lực compute

Chi phí VM thường phụ thuộc vào loại instance, kích thước, hệ điều hành, region, mô hình mua, thời gian chạy và một số thuộc tính như tenancy hoặc accelerator.

### Loại và kích thước instance

Instance type xác định tổ hợp CPU, RAM, network và đôi khi cả storage hoặc GPU. Cùng một số vCPU nhưng hai family hoặc thế hệ CPU khác nhau có thể có giá và hiệu năng khác nhau. Một máy có nhiều RAM hơn có thể đắt hơn dù workload không dùng hết phần RAM bổ sung.

Khi lựa chọn, cần xem:

- Số vCPU và hiệu năng CPU thực tế theo benchmark.
- RAM và working set tại peak.
- Network bandwidth, packet-per-second và giới hạn kết nối.
- Loại storage cục bộ, IOPS và throughput.
- GPU/accelerator, VRAM và driver nếu workload yêu cầu.
- Kiến trúc x86-64 hay Arm và khả năng tương thích của ứng dụng.
- Giá theo region và mức sẵn có của loại máy.

Giá instance lớn không tăng tuyến tính trong mọi family. Một số size có mức giá theo bước, một số family có đặc tính burstable hoặc giới hạn CPU credit. Vì vậy, so sánh giá cần gắn với throughput và SLO, không chỉ nhìn số vCPU.

### Thời gian tính phí

Nhiều dịch vụ VM tính phí theo thời gian máy ở trạng thái chạy, với đơn vị giây hoặc giờ và mức tối thiểu tùy nhà cung cấp. Một số chi phí storage hoặc IP vẫn tiếp tục phát sinh khi VM đã stop. Xóa VM cũng không nhất thiết xóa volume, snapshot, địa chỉ IP hoặc license gắn riêng.

Trong dự toán, hãy xác định rõ:

- VM chạy 24/7 hay chỉ chạy theo lịch.
- Có thời gian khởi động, warm-up hoặc shutdown không.
- Máy stop có còn giữ boot/data volume hay không.
- Có tính phí cho trạng thái stopped, reserved capacity hoặc host allocation không.
- Có thời gian tối thiểu tính phí, làm tròn theo đơn vị hoặc phí riêng cho hệ điều hành không.

### Mô hình mua compute

| Mô hình | Đặc điểm | Phù hợp khi |
|---|---|---|
| On-Demand/pay-as-you-go | Trả theo thời gian sử dụng, linh hoạt | Tải chưa ổn định, môi trường thử nghiệm hoặc workload khó dự đoán |
| Reserved/committed use | Cam kết thời hạn hoặc mức sử dụng để nhận mức giá ưu đãi | Có baseline ổn định và dự báo đáng tin cậy |
| Savings plan/committed spend | Cam kết chi tiêu hoặc mức compute theo điều kiện sản phẩm | Nhiều loại compute nhưng có mức dùng ổn định |
| Spot/preemptible | Dùng capacity dư với giá thấp hơn, có thể bị thu hồi | Batch, worker stateless, job có checkpoint và retry |
| Dedicated host/tenancy | Dùng host riêng hoặc tenancy chuyên biệt | Yêu cầu license, compliance, cô lập hoặc kiểm soát host |

Tên sản phẩm, phạm vi cam kết, mức giảm giá, khả năng đổi family/region và phí khi không sử dụng hết khác nhau giữa nhà cung cấp. Không giả định reservation luôn tương đương capacity reservation: một cam kết giá có thể giảm đơn giá nhưng không bảo đảm có máy vật lý sẵn sàng khi cần.

## 3. Tính chi phí compute theo thời gian sử dụng

Với mô hình đơn giản, chi phí một nhóm máy có thể ước lượng:

\[
C_{compute} = \sum_{i=1}^{n} (N_i \times H_i \times P_i)
\]

Trong đó:

- `N_i`: số instance loại `i`.
- `H_i`: số giờ tính phí trong kỳ.
- `P_i`: giá một instance mỗi giờ theo region, OS và mô hình mua.

Ví dụ giả định: một dịch vụ chạy 4 VM giống nhau trong 30 ngày, mỗi máy chạy 24 giờ/ngày. Nếu đơn giá giả định là 0,20 USD/giờ:

\[
4 \times 30 \times 24 \times 0,20 = 576\text{ USD}
\]

Đây chỉ là ví dụ số học, không phải báo giá của nhà cung cấp. Chưa bao gồm đĩa, snapshot, mạng, license, managed services, thuế hoặc chiết khấu. Nếu số máy thay đổi theo autoscaling, nên tính theo số giờ instance thực tế trong từng khoảng thay vì nhân số máy tối đa cho cả tháng.

Với workload chạy theo lịch, có thể ước lượng:

\[
C_{scheduled} = N \times H_{run/day} \times D_{month} \times P_{hour}
\]

Nhưng phải cộng thời gian boot, test, warm-up và shutdown nếu những giai đoạn đó vẫn bị tính phí. Một job chạy 2 giờ mỗi ngày không nhất thiết chỉ tiêu thụ đúng 2 giờ VM nếu khởi tạo môi trường và chờ dữ liệu mất thêm thời gian.

## 4. Chi phí storage: block, file, object và local disk

Storage có nhiều mô hình tính phí khác nhau. Không nên cộng toàn bộ dung lượng vào một đơn giá GB-tháng nếu dịch vụ còn tính IOPS, throughput, operation hoặc snapshot.

### Block storage

Block volume thường gắn với VM như một thiết bị block. Chi phí có thể phụ thuộc:

- Dung lượng provisioned (GB-tháng), kể cả phần chưa ghi dữ liệu.
- Loại volume: SSD, HDD, balanced hoặc loại tối ưu IOPS.
- IOPS provisioned hoặc throughput provisioned vượt mức cơ sở.
- Snapshot, backup và bản sao liên vùng.
- Phí khôi phục hoặc thao tác đặc thù nếu dịch vụ có quy định.

Ví dụ, một VM có boot volume 100 GB và data volume 500 GB có thể trả tiền cho 600 GB provisioned ngay cả khi filesystem mới dùng 220 GB. Cần phân biệt dung lượng cấp phát với dung lượng thực dùng.

### File storage

Managed file storage có thể tính theo dung lượng lưu, throughput mode, provisioned throughput, số thao tác hoặc capacity tier. Chi phí có thể tăng khi nhiều VM mount cùng filesystem hoặc workload tạo lượng metadata operation lớn.

### Object storage

Object storage thường tính theo dung lượng theo storage class, request PUT/GET/LIST, retrieval, lifecycle transition và data transfer. Lưu trữ dữ liệu lâu dài ở class rẻ hơn có thể tiết kiệm, nhưng việc đọc lại thường xuyên hoặc chuyển class có thể làm tổng chi phí tăng.

### Local/ephemeral storage

Một số instance có local NVMe hoặc ephemeral disk được bao gồm trong giá máy; loại khác tính riêng hoặc không bảo đảm dữ liệu tồn tại khi stop/terminate. Dù không có dòng phí storage riêng, local disk vẫn có chi phí gián tiếp thông qua việc phải chọn instance family/size tương ứng và có thể cần replication/backup sang storage bền vững.

## 5. Snapshot, backup và bản sao dữ liệu

Snapshot thường được tính theo dung lượng block đã lưu hoặc dung lượng thay đổi giữa các snapshot, tùy dịch vụ. Backup managed có thể có phí dung lượng, request, cross-region copy, retention lock và restore.

Những khoản dễ bị bỏ sót:

- Snapshot cũ không còn cần nhưng chưa xóa.
- Snapshot được copy sang nhiều region.
- Backup retention dài hơn yêu cầu nghiệp vụ.
- Nhiều bản backup trùng lặp do policy ở cả ứng dụng và nền tảng.
- Chi phí restore hoặc truy xuất từ storage class lạnh.
- Dữ liệu tạm và staging được giữ lại sau migration.

Không tối ưu bằng cách xóa backup tùy tiện. Trước khi giảm retention, đối chiếu RPO/RTO, yêu cầu audit, quy định lưu giữ và khả năng phục hồi. Thực hiện restore test định kỳ để bảo đảm khoản tiền backup thực sự mua được khả năng khôi phục.

## 6. Chi phí mạng và data transfer

Network là thành phần có thể tạo chênh lệch lớn giữa dự toán và hóa đơn, đặc biệt với workload trao đổi dữ liệu nhiều hoặc phân bố nhiều zone/region.

Các loại lưu lượng thường cần xem:

- **Ingress:** dữ liệu đi vào cloud. Một số nhà cung cấp miễn hoặc tính theo điều kiện riêng; không nên mặc định mọi ingress đều miễn phí.
- **Internet egress:** dữ liệu từ cloud đi ra Internet hoặc tới người dùng. Thường có mức phí theo GB và bậc sản lượng.
- **Inter-zone transfer:** dữ liệu giữa các AZ trong cùng region; có thể tính phí theo chiều hoặc theo từng bên tùy dịch vụ.
- **Inter-region transfer:** dữ liệu giữa các region, thường có đơn giá khác internet egress.
- **Cross-cloud/on-prem transfer:** dữ liệu qua VPN, dedicated connectivity hoặc mạng đối tác; có thể gồm phí cổng kết nối và phí data transfer.
- **Service-to-service transfer:** lưu lượng qua NAT, load balancer, gateway hoặc endpoint có thể phát sinh phí theo giờ, GB hoặc request.

Luồng dữ liệu phải được mô hình hóa theo đường đi thực tế. Ví dụ, VM private subnet truy cập Internet qua NAT gateway có thể phát sinh phí NAT theo giờ và theo GB, ngoài phí egress Internet. Nếu request đi qua load balancer rồi tới backend ở zone khác, có thể có phí load balancer và phí cross-zone.

### Tính chi phí data transfer

Mô hình đơn giản:

\[
C_{transfer} = \sum_{k=1}^{m} (GB_k \times Rate_k)
\]

Trong đó `GB_k` là lượng dữ liệu của loại luồng `k` và `Rate_k` là đơn giá áp dụng cho tuyến đó. Nếu dịch vụ có bậc giá, miễn phí theo quota, tính theo chiều hoặc tính theo điểm kết nối, phải áp dụng đúng bảng giá.

Ví dụ giả định: một API gửi 2 TB dữ liệu ra Internet trong tháng, đơn giá giả định là 0,08 USD/GB. Nếu quy ước 1 TB = 1.000 GB:

\[
2.000 \times 0,08 = 160\text{ USD}
\]

Con số này chỉ minh họa phép tính và chưa áp dụng tier, quota, thuế hoặc phí gateway. Trong dự toán thật, dùng đúng đơn vị GB/GiB và quy tắc làm tròn của nhà cung cấp.

### Những nguồn network cost thường bị bỏ sót

- NAT gateway hoặc NAT instance có phí theo giờ và/hoặc GB.
- Public IPv4 address có thể bị tính phí theo thời gian sử dụng hoặc trạng thái.
- Load balancer có thể tính theo giờ, capacity unit, processed bytes hoặc rule.
- VPN, dedicated circuit, transit gateway và network firewall có phí cố định cùng phí xử lý dữ liệu.
- Cross-zone load balancing có thể tạo lưu lượng liên AZ.
- DNS query, private endpoint hoặc service endpoint có thể có meter riêng.
- Egress từ object storage, CDN origin hoặc database có thể được tính theo bảng giá riêng.

Tên meter và cách tính rất khác nhau. Cần kiểm tra xem phí data transfer đã bao gồm trong phí dịch vụ hay được tính riêng để tránh cộng trùng hoặc bỏ sót.

## 7. Chi phí load balancer và network gateway

Load balancer thường có thể tính phí theo thời gian hoạt động cộng với một thước đo tải như capacity unit, số kết nối, số rule, byte xử lý hoặc request. Khi scale backend, load balancer có thể vẫn chạy liên tục và tạo chi phí nền.

Network gateway cũng có thể có phí cố định theo giờ và phí theo lượng dữ liệu đi qua. Một kiến trúc nhiều subnet private có thể tạo nhiều NAT gateway để tăng HA; việc đó tăng chi phí cố định nhưng giảm rủi ro phụ thuộc một gateway và có thể giảm cross-zone traffic.

Khi tối ưu, so sánh tổng chi phí và kiến trúc:

- Một gateway dùng chung hay gateway theo từng AZ.
- Private endpoint/service endpoint có thể thay đường đi qua NAT hay không.
- Load balancer nội bộ và public có thể dùng chung hay cần tách.
- Cross-zone routing có cần thiết để cân bằng tải và chịu lỗi không.
- Có thể dùng CDN/cache để giảm egress và request tới origin không.

Không loại bỏ gateway hoặc load balancer chỉ để giảm phí nếu việc đó làm mất private connectivity, HA, kiểm soát bảo mật hoặc khả năng mở rộng.

## 8. Chi phí giấy phép hệ điều hành và phần mềm

License có thể được tính trong giá instance hoặc trả riêng theo mô hình BYOL (Bring Your Own License), theo core/vCPU, socket, host, user hoặc hợp đồng doanh nghiệp.

Các khoản thường gặp:

- Windows Server hoặc hệ điều hành thương mại.
- SQL/database engine và extension.
- Middleware, application server và runtime thương mại.
- Phần mềm backup, monitoring, endpoint protection hoặc security agent.
- Phần mềm CAD, AI/ML, phân tích dữ liệu hoặc ứng dụng chuyên ngành.
- License gắn với dedicated host, core count hoặc hardware fingerprint.

Khi sizing VM, cần xem license tính theo vCPU được cấp, core vật lý, host hay số instance. Một số hợp đồng có quy tắc tối thiểu core hoặc yêu cầu dedicated host. Tăng vCPU có thể làm chi phí license tăng nhanh hơn chi phí compute.

### Included license và BYOL

| Mô hình | Đặc điểm | Điều cần xác minh |
|---|---|---|
| License included | Giá dịch vụ đã bao gồm license theo điều kiện SKU | Phạm vi sản phẩm/phiên bản, số core, quyền dùng và giới hạn region |
| BYOL | Khách hàng dùng license hiện có | Quyền chuyển license lên cloud, mobility, host requirement và audit |
| License theo usage | Tính theo user, core, giờ hoặc mức sử dụng | Cách đo, tối thiểu, thời hạn và phí khi scale |
| Dedicated host licensing | License phụ thuộc host vật lý hoặc socket/core | Quy tắc phân bổ, affinity và thời gian giữ host |

Không giả định license on-prem được phép chuyển lên mọi môi trường cloud. Cần kiểm tra hợp đồng, điều khoản nhà cung cấp phần mềm và chính sách licensing hiện hành trước khi chọn BYOL.

## 9. Chi phí dịch vụ quản lý

Managed service giảm công tự vận hành nhưng vẫn tạo chi phí dịch vụ. Một số thành phần thường gặp:

- Managed database: instance/compute, storage, IOPS, backup, replica, failover và data transfer.
- Managed cache: node size, shard, replica, backup và network.
- Queue/message broker: broker-hour, throughput, request, partition hoặc storage.
- Container orchestration: control plane, worker nodes, add-on và network.
- Serverless compute: request count, execution duration, memory/CPU allocation và provisioned concurrency.
- Monitoring/logging: ingest, metric series, trace span, query và retention.
- Secrets/KMS: key, operation, request và HSM nếu dùng.
- Backup/recovery: protected instance, storage, request, cross-region copy và restore.

Managed service có thể giảm chi phí nhân lực cho patching, HA, backup và vận hành, nhưng không phải lúc nào cũng rẻ hơn VM tự quản lý. Cần so sánh cả phí dịch vụ, công vận hành, rủi ro downtime, khả năng mở rộng và trách nhiệm còn lại của khách hàng.

Ví dụ, managed database có thể có đơn giá cao hơn VM nhỏ tự cài database, nhưng đã bao gồm một phần backup, patch orchestration hoặc failover. So sánh đúng phải tính VM database, storage, license, backup, replica, monitoring, nhân lực on-call và chi phí downtime của phương án tự quản lý.

## 10. Chi phí observability và log

Monitoring thường bị xem là khoản nhỏ, nhưng log, metric và trace có thể tăng nhanh theo request rate và thời gian lưu.

Các yếu tố ảnh hưởng:

- Log ingest theo GB hoặc số sự kiện.
- Metric theo số time series, cardinality và tần suất scrape.
- Trace theo số span, sampling và dung lượng lưu.
- Retention nóng/lạnh, archive và truy vấn.
- Egress từ agent tới backend hoặc giữa region.
- Số dashboard, alert, query hoặc user tùy mô hình giá.

Để kiểm soát:

- Không ghi debug payload hoặc body nhạy cảm trong production nếu không cần.
- Dùng sampling có chủ đích cho trace và giữ đầy đủ loại sự kiện cần cho audit/security.
- Giảm cardinality metric; tránh request ID hoặc user ID làm label.
- Thiết lập retention theo mục tiêu điều tra và quy định.
- Dùng log tier/archive phù hợp cho dữ liệu ít truy cập.
- Theo dõi chi phí ingest theo service và team.

Không giảm log bảo mật hoặc audit một cách tùy tiện để tiết kiệm chi phí. Cần phân biệt dữ liệu debug, telemetry vận hành và log tuân thủ.

## 11. Chi phí theo mô hình VM, container và serverless

Ba mô hình compute có cách tính và thành phần phụ trợ khác nhau.

| Mô hình | Meter compute thường gặp | Thành phần phụ trợ cần tính |
|---|---|---|
| VM | Instance size × thời gian chạy | Volume, snapshot, IP, network, license, load balancer, monitoring |
| Container trên VM/node | Worker node/VM × thời gian; đôi khi có phí control plane | Cluster, node pool, registry, persistent volume, network, logging, ingress |
| Serverless function | Request × execution duration × memory/CPU tier; có thể có concurrency provisioned | API gateway, queue, storage, log/trace, NAT/VPC access, data transfer |
| Managed container/serverless container | vCPU/RAM allocation × thời gian hoặc request | Ingress, egress, registry, log, persistent storage và minimum capacity |

VM thường có chi phí nền khi chạy liên tục, kể cả lúc ít tải. Container không tự động rẻ hơn VM nếu vẫn phải duy trì node dư thừa hoặc cluster quá lớn. Serverless có thể hiệu quả với tải không liên tục, nhưng request nhiều, thời gian chạy dài, provisioned concurrency hoặc network dependency có thể làm chi phí tăng.

So sánh bằng cùng một workload và cùng mục tiêu dịch vụ: request/giây, p95 latency, độ sẵn sàng, throughput, thời gian job và yêu cầu bảo mật. Không so sánh đơn giá compute mà bỏ qua gateway, storage, log, network và công vận hành.

## 12. Chi phí idle, tài nguyên mồ côi và capacity dự phòng

Một phần đáng kể chi phí có thể đến từ tài nguyên không còn phục vụ workload:

- VM chạy nhưng không nhận traffic hoặc có CPU thấp kéo dài.
- Volume không còn gắn với VM.
- Snapshot cũ và backup trùng lặp.
- Public IP, load balancer hoặc NAT gateway không còn dùng.
- Disk provisioned quá lớn hoặc IOPS cao hơn nhu cầu.
- Instance group giữ min capacity quá cao.
- Cluster node không có pod/workload tương ứng.
- Test environment không được tắt theo lịch.
- Reservation/commitment không được sử dụng hết.

Không phải tài nguyên idle nào cũng lãng phí. Capacity dự phòng có thể cần cho failover, burst, maintenance, warm-up hoặc yêu cầu RTO. Hãy gắn mỗi tài nguyên với owner, workload, môi trường, mục đích và thời hạn review. Tối ưu cần giữ đúng headroom cần thiết cho resilience.

## 13. Phân bổ chi phí cho workload và đội ngũ

Để biết ai tạo ra chi phí, cần gắn metadata nhất quán cho tài nguyên và dùng dữ liệu billing/export. Các tag hoặc label thường có:

- `service` hoặc `application`: tên workload.
- `environment`: production, staging, development.
- `owner` hoặc `team`: đội chịu trách nhiệm.
- `cost-center`: mã trung tâm chi phí.
- `business-unit` hoặc `product`: đơn vị nghiệp vụ.
- `managed-by`: Terraform, CloudFormation, Ansible hoặc công cụ khác.
- `expiry` hoặc `review-date`: thời hạn xem xét tài nguyên tạm.

Không đưa thông tin bí mật hoặc dữ liệu cá nhân vào tag. Chuẩn hóa key/value, kiểm tra tag coverage và áp dụng policy tự động khi tạo tài nguyên.

Chi phí shared service như NAT, logging, cluster control plane hoặc network gateway cần có quy tắc phân bổ. Có thể phân bổ theo GB transfer, số request, số node, tỷ lệ sử dụng hoặc chia theo team. Ghi rõ phương pháp để người nhận hóa đơn hiểu được con số.

Phân biệt:

- **Direct cost:** gắn trực tiếp với một workload, ví dụ VM hoặc volume riêng.
- **Shared cost:** dùng chung, ví dụ NAT gateway, observability backend hoặc cluster.
- **Unallocated cost:** chưa có tag hoặc chưa xác định owner.
- **Commitment discount/credit:** khoản giảm giá hoặc credit cần phân bổ theo quy tắc tài chính.

## 14. Unit economics: chi phí trên mỗi đơn vị nghiệp vụ

Tổng hóa đơn tăng không nhất thiết là xấu nếu số lượng người dùng hoặc giao dịch tăng nhanh hơn. Một chỉ số hữu ích là chi phí trên mỗi đơn vị công việc:

\[
Unit\ Cost = \frac{Total\ Workload\ Cost}{Useful\ Work\ Units}
\]

Đơn vị có thể là:

- Chi phí trên 1.000 request thành công.
- Chi phí trên một đơn hàng hoàn tất.
- Chi phí trên một giờ xử lý batch.
- Chi phí trên một GB dữ liệu được xử lý.
- Chi phí trên một phiên người dùng hoạt động.
- Chi phí trên một mô hình inference hoặc một tác vụ GPU.

Ví dụ giả định: một API tốn 1.200 USD/tháng và xử lý 6 triệu request thành công. Unit cost là 0,20 USD trên 1.000 request. Nếu tháng sau chi phí tăng lên 1.320 USD nhưng số request thành công tăng lên 7,5 triệu, chi phí trên 1.000 request giảm xuống 0,176 USD. Hóa đơn tổng tăng nhưng hiệu quả chi phí tốt hơn.

Chọn mẫu số phản ánh giá trị nghiệp vụ và chất lượng dịch vụ. Không dùng tổng request nếu tỷ lệ lỗi tăng mạnh; nên tính trên request thành công hoặc giao dịch hoàn tất.

## 15. Dự toán chi phí từ kiến trúc

Một dự toán tốt bắt đầu từ kiến trúc và mô hình tải, không bắt đầu bằng việc chọn vài SKU rồi cộng giá.

Các bước:

1. Xác định workload, environment, region và yêu cầu availability.
2. Ước lượng tải nền, peak, burst, số giờ hoạt động và tăng trưởng.
3. Chọn VM/container/serverless và số lượng capacity tối thiểu, trung bình, tối đa.
4. Tính storage theo dung lượng provisioned, IOPS, snapshot, backup và retention.
5. Vẽ luồng network để ước lượng ingress, egress, cross-zone, NAT, gateway và load balancer.
6. Xác định OS, database, middleware và license.
7. Liệt kê managed services, monitoring, secrets và support.
8. Áp dụng mô hình mua phù hợp cho baseline và burst.
9. Cộng chi phí migration, chạy song song, test và headroom.
10. Chạy thử, đo usage thật và cập nhật dự toán.

Nên lập ba kịch bản:

| Kịch bản | Giả định | Mục đích |
|---|---|---|
| Low | Tải thấp, tăng trưởng chậm, ít burst | Ước lượng mức chi phí thuận lợi |
| Expected | Tải dự kiến và pattern sử dụng thông thường | Làm ngân sách cơ sở |
| High | Peak, tăng trưởng nhanh, failover hoặc egress cao | Kiểm tra ngân sách và khả năng chịu chi phí |

Đối với workload có HA, kịch bản high nên bao gồm việc mất một AZ hoặc một nhóm máy và phần capacity còn lại phải gánh tải. Đừng chỉ dự toán theo số máy chạy bình thường nếu kiến trúc yêu cầu N-1 headroom.

## 16. Ví dụ dự toán tổng chi phí một workload VM

Giả sử một ứng dụng nội bộ chạy hai VM application trong production, một managed database, hai data volume và một load balancer. Các mức giá dưới đây chỉ là số giả định để minh họa cách cộng thành phần.

| Thành phần | Giả định tính phí | Chi phí giả định/tháng |
|---|---|---:|
| 2 VM application | 2 × 730 giờ × 0,12 USD/giờ | 175,20 USD |
| Boot + data volume | 600 GB × 0,08 USD/GB-tháng | 48,00 USD |
| Snapshot/backup | 400 GB lưu trung bình × 0,05 USD/GB-tháng | 20,00 USD |
| Load balancer | Phí nền và capacity usage | 35,00 USD |
| NAT/network processing | 300 GB × 0,045 USD/GB, chưa gồm phí nền | 13,50 USD |
| Internet egress | 500 GB × 0,08 USD/GB | 40,00 USD |
| Managed database | Instance, storage và backup cơ sở | 220,00 USD |
| Monitoring/logging | Ingest và retention | 30,00 USD |
| License bổ sung | Theo hợp đồng giả định | 25,00 USD |
| **Tổng** |  | **606,70 USD** |

Ví dụ này không phải bảng giá cloud thực tế. Trong dự toán thật, cần xác minh đơn vị GB/GiB, bậc giá, phí nền, cross-zone, license, thuế và chiết khấu. Nếu VM có Windows license included hoặc database license đã nằm trong managed service, không cộng trùng license.

Điểm quan trọng là compute chỉ chiếm một phần tổng chi phí. Nếu chỉ tối ưu giá VM mà bỏ qua database, egress, backup và NAT, mức tiết kiệm tổng thể có thể rất nhỏ.

## 17. Tối ưu chi phí compute

Các biện pháp phổ biến:

- Rightsize VM dựa trên CPU, memory, network và disk thực tế.
- Tắt hoặc schedule môi trường dev/test ngoài giờ.
- Dùng autoscaling với min/max hợp lý và warm-up phù hợp.
- Dùng Spot cho workload có thể retry/checkpoint.
- Dùng commitment/reservation cho baseline ổn định sau khi có dữ liệu sử dụng.
- Chọn kiến trúc CPU và family tương thích có hiệu năng/giá tốt hơn.
- Tách workload có pattern khác nhau để scale độc lập.
- Dùng burstable instance chỉ khi pattern CPU và credit phù hợp.
- Xóa hoặc giảm tài nguyên idle sau khi xác minh owner và retention.

Không giảm capacity đến mức làm tăng lỗi, latency hoặc downtime. Đánh giá tiết kiệm theo chi phí trên đơn vị công việc và SLO.

## 18. Tối ưu chi phí storage

- Xóa volume không dùng sau khi xác nhận dữ liệu đã được bảo toàn.
- Right-size dung lượng và IOPS theo metric thực tế.
- Dùng storage class phù hợp với tần suất truy cập.
- Thiết lập lifecycle cho object và snapshot.
- Loại bỏ backup trùng lặp nhưng giữ retention bắt buộc.
- Nén hoặc deduplicate dữ liệu nếu phù hợp và không làm tăng CPU/latency quá mức.
- Đặt dữ liệu gần compute để giảm cross-zone transfer khi kiến trúc cho phép.
- Kiểm thử restore trước khi chuyển dữ liệu sang tier lưu trữ lạnh.

Storage rẻ hơn có thể tăng chi phí retrieval, độ trễ hoặc thời gian phục hồi. Chọn theo pattern truy cập và RTO, không chỉ theo giá GB-tháng.

## 19. Tối ưu chi phí network

- Đặt compute gần dependency và người dùng chính nếu đáp ứng yêu cầu latency/residency.
- Giảm cross-zone traffic không cần thiết; vẫn duy trì HA theo thiết kế.
- Dùng cache hoặc CDN để giảm request và egress từ origin.
- Dùng private endpoint/service endpoint nếu phù hợp để tránh một số tuyến qua NAT hoặc Internet.
- Gom batch hoặc nén dữ liệu truyền khi lợi ích lớn hơn CPU cost.
- Tránh gửi log/trace quá chi tiết hoặc cross-region không cần thiết.
- Theo dõi NAT processed bytes, load balancer processed bytes và egress theo workload.
- Đặt budget/cảnh báo cho data transfer vì lưu lượng tăng đột biến có thể làm hóa đơn tăng nhanh.

Không chuyển mọi workload vào một AZ chỉ để giảm cross-zone fee. Chi phí tiết kiệm phải được so sánh với rủi ro downtime và khả năng chịu lỗi.

## 20. Tối ưu license và managed services

- Kiểm tra quyền BYOL và cách tính license theo core/vCPU/host.
- Tránh cấp vCPU vượt nhu cầu nếu license tính theo core.
- Dùng license included khi tổng chi phí phù hợp và điều khoản cho phép.
- Xem lại license của máy stop, host dedicated và tài nguyên dự phòng.
- Đánh giá managed service theo TCO, gồm nhân lực vận hành và HA.
- Tắt hoặc giảm tier dịch vụ non-production khi không sử dụng.
- Chọn retention, replica count và backup frequency theo yêu cầu thực tế.
- Theo dõi request/operation và mức sử dụng vượt quota trong managed service.

Đối với managed database hoặc cache, scale lên một tier lớn hơn có thể tăng compute và memory cost đáng kể. Trước khi nâng tier, kiểm tra query, index, connection pool, cache hit ratio và storage I/O để biết nút thắt thực sự.

## 21. FinOps: quản lý chi phí liên tục

FinOps kết hợp tài chính, kỹ thuật và nghiệp vụ để tạo trách nhiệm chung về chi phí cloud. Đây không phải một lần cắt giảm ngân sách; đó là chu trình quan sát, phân bổ, tối ưu và dự báo.

Một chu trình đơn giản:

1. **Inform:** thu thập billing export, usage, tag, inventory và metric kỹ thuật.
2. **Allocate:** gán chi phí cho workload, team, environment và cost center.
3. **Optimize:** tìm tài nguyên idle, sizing sai, commitment chưa dùng và đường truyền tốn kém.
4. **Operate:** đặt budget, anomaly alert, review định kỳ và quy trình phê duyệt.
5. **Forecast:** cập nhật dự báo theo tăng trưởng, release, seasonality và thay đổi kiến trúc.

Chỉ số nên theo dõi:

- Tổng chi phí theo service, team, environment, region và ngày.
- Cost per request/job/order hoặc đơn vị nghiệp vụ.
- Compute utilization và tỷ lệ idle.
- Storage provisioned so với used.
- Network egress/cross-zone/NAT theo workload.
- Commitment coverage và utilization.
- Chi phí chưa phân bổ hoặc thiếu tag.
- Chênh lệch actual so với forecast và budget.

## 22. Budget, cảnh báo và kiểm soát bất thường

Budget giúp phát hiện chi phí tăng ngoài dự kiến nhưng không nhất thiết tự ngăn tài nguyên phát sinh. Nên thiết lập:

- Ngưỡng cảnh báo theo tháng và theo workload.
- Cảnh báo tăng đột biến so với baseline ngày/tuần.
- Ngưỡng riêng cho egress, NAT, GPU, log ingest và managed database.
- Owner nhận cảnh báo và thời hạn phản hồi.
- Quy trình xác minh trước khi tự động dừng tài nguyên.
- Báo cáo dự báo cuối tháng và chi phí đã cam kết.

Không tự động terminate VM production chỉ vì vượt budget nếu chưa có chính sách được phê duyệt. Cảnh báo cần dẫn tới điều tra: traffic tăng hợp lệ, release mới, loop tạo resource, log verbosity, data exfiltration hay autoscaling sai cấu hình đều có thể làm chi phí tăng.

## 23. Những sai lầm thường gặp khi tính chi phí

- **Chỉ tính giá VM:** bỏ sót storage, network, license và managed service. Dự toán theo kiến trúc đầy đủ.
- **Nhầm stop VM là hết phí:** volume, snapshot, IP hoặc reservation vẫn có thể tính phí. Kiểm tra vòng đời từng tài nguyên.
- **Không tính cross-zone và egress:** workload phân tán hoặc response lớn có thể tạo phí truyền dữ liệu đáng kể.
- **Cộng trùng license:** license đã bao gồm trong SKU nhưng vẫn cộng thêm BYOL. Kiểm tra điều khoản và meter.
- **Dùng giá thấp nhất để chọn instance:** máy rẻ nhưng không đáp ứng SLO hoặc làm tăng số instance cần chạy. So sánh cost per useful work.
- **Commitment quá sớm:** cam kết vượt nhu cầu khiến phần không sử dụng bị lãng phí. Phân tích lịch sử trước khi mua.
- **Dùng Spot cho tải không chịu gián đoạn:** interruption gây mất công việc hoặc downtime. Chỉ dùng cho workload có retry/checkpoint.
- **Bỏ qua chi phí observability:** log và trace tăng theo traffic. Kiểm soát ingest, cardinality và retention.
- **Cắt capacity dự phòng quá sâu:** hóa đơn giảm nhưng không còn N-1 headroom. Tính cả chi phí resilience.
- **Không phân bổ shared cost:** team không thấy chi phí NAT, gateway hoặc monitoring mà họ tạo ra. Thiết lập quy tắc chargeback/showback.

## 24. Checklist lập dự toán và tối ưu

- [ ] Đã liệt kê compute, storage, network, license, managed service và vận hành.
- [ ] Đã xác định region, đơn vị tính phí, giờ hoạt động và mô hình mua.
- [ ] Đã sizing VM theo CPU/RAM/network/disk và workload peak.
- [ ] Đã tính volume provisioned, IOPS, snapshot, backup và retention.
- [ ] Đã vẽ luồng network và ước lượng ingress, egress, cross-zone, NAT, LB và gateway.
- [ ] Đã kiểm tra license included, BYOL và quy tắc tính theo core/host/user.
- [ ] Đã tính managed database, cache, queue, orchestration, monitoring và secrets.
- [ ] Đã tính chi phí chạy song song, migration, test và headroom HA.
- [ ] Đã xây dựng kịch bản low/expected/high và đối chiếu với SLO.
- [ ] Đã gắn tag owner, service, environment và cost center.
- [ ] Đã xác định unit economics phù hợp với nghiệp vụ.
- [ ] Có budget, anomaly alert, forecast và lịch review.
- [ ] Đã kiểm tra tài nguyên idle/orphan nhưng không xóa nhầm backup hoặc capacity dự phòng.
- [ ] Đã so sánh actual billing với estimate và cập nhật giả định.

## 25. Kết luận

Chi phí compute cloud là tổng của nhiều meter độc lập: máy, đĩa, mạng, giấy phép và dịch vụ quản lý. VM có thể là khoản lớn nhất ở một workload, nhưng ở workload khác, database managed, egress, NAT, backup hoặc license mới là thành phần chi phối. Dự toán đúng cần bắt đầu từ kiến trúc và tải thực tế, sau đó ánh xạ từng thành phần sang đơn vị tính phí của nhà cung cấp.

Khi phân bổ chi phí theo workload, theo dõi cost per useful work, dự báo cả tình huống peak/failover và review hóa đơn định kỳ, tổ chức có thể tối ưu chi phí mà vẫn giữ hiệu năng, bảo mật và khả năng phục hồi cần thiết.
