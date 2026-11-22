# Thiết kế kết nối, DNS và định tuyến giữa các môi trường

## Mục tiêu học tập

Kiến trúc hybrid cloud kết nối môi trường on-premises với một hoặc nhiều cloud. Kiến trúc multi-cloud kết nối workload chạy trên nhiều cloud provider. Trong cả hai trường hợp, ứng dụng thường phải truy cập dịch vụ, dữ liệu và hệ thống identity nằm ở nhiều network domain khác nhau. Kết nối thành công không chỉ là tạo được tunnel hoặc route: DNS phải phân giải đúng tên, đường đi phải có tính đối xứng phù hợp, security policy phải giới hạn truy cập, capacity phải đáp ứng tải và hệ thống phải có phương án xử lý khi một đường truyền hoặc một môi trường gặp sự cố.

Một thiết kế thiếu nhất quán có thể gây ra các vấn đề khó điều tra: client phân giải hostname về private IP không thể reach; route quảng bá nhầm CIDR làm traffic đi sai cloud; firewall cho phép chiều đi nhưng chặn chiều về; DNS forwarding loop; hai site dùng CIDR overlap; failover đổi route nhưng resolver vẫn cache địa chỉ cũ; hoặc kết nối dự phòng tồn tại trên sơ đồ nhưng dùng chung conduit và cùng failure domain với kết nối chính.

Bài học này trình bày cách thiết kế **kết nối, DNS và định tuyến giữa các môi trường** trong hybrid và multi-cloud. Nội dung đi từ yêu cầu nghiệp vụ, topology, IP plan, private connectivity, VPN, transit hub, routing, DNS architecture, segmentation, resiliency, observability, troubleshooting đến vận hành thay đổi. Mỗi lựa chọn cần được đánh giá theo latency, throughput, availability, security, data residency, khả năng mở rộng, chi phí và mức độ phức tạp vận hành.

Sau bài học, bạn có thể:

- Phân biệt hybrid cloud, multi-cloud, private connectivity, overlay network và underlay.
- Xác định flow, trust boundary, latency, throughput và availability requirement.
- Thiết kế IP address plan có thể mở rộng, tránh overlap và hỗ trợ route summarization.
- Chọn giữa site-to-site VPN, dedicated private connection và SD-WAN.
- Thiết kế hub-and-spoke, transit gateway, virtual WAN hoặc kết nối mesh có kiểm soát.
- Thiết kế route propagation, static/dynamic routing, BGP, filtering và path preference.
- Thiết kế DNS namespace, resolver, conditional forwarding, private zone và split-horizon.
- Tránh DNS forwarding loop, stale cache và rủi ro resolver cross-environment.
- Xây segmentation theo environment, application, data classification và trust level.
- Thiết kế redundant path, failover, health check và capacity cho tình huống mất site/link.
- Quan sát network/DNS bằng flow logs, resolver logs, telemetry và synthetic probes.
- Xây runbook, change control, incident response và test kết nối end-to-end.

## 1. Vì sao kết nối hybrid và multi-cloud là bài toán kiến trúc?

Một tổ chức có thể chạy ERP tại data center, API mới trên Cloud A, analytics trên Cloud B và identity provider dùng chung. Một giao dịch nghiệp vụ có thể đi qua API gateway, application service, database, payment provider và message broker ở các network domain khác nhau.

Khi các môi trường được kết nối, hệ thống hình thành một mạng phân tán với nhiều lớp kiểm soát:
- Physical/underlay network của data center, carrier và cloud provider.
- Overlay network như IPsec tunnel, SD-WAN hoặc virtual network.
- Routing domain và route advertisement.
- Firewall, security group, NACL và network policy.
- DNS resolver, private zone và service discovery.
- Identity và workload authentication.
- Observability, incident response và change governance.

Một route tồn tại không chứng minh ứng dụng có thể hoạt động. Cần kiểm tra đồng thời name resolution, route selection, firewall, TLS, authentication, service health và policy của ứng dụng.

### 1.1. Các mô hình kết nối

| Mô hình | Đặc điểm | Trường hợp phù hợp |
| --- | --- | --- |
| On-premises to one cloud | Data center/VPN kết nối một VPC/VNet | Mở rộng hệ thống hiện có lên cloud |
| Hybrid hub-and-spoke | Transit hub nối nhiều spoke và data center | Nhiều workload cần kết nối tập trung |
| Multi-cloud hub | Một network hub hoặc routing domain kết nối nhiều provider | Workload phân tán giữa cloud |
| Cloud-to-cloud direct | Hai cloud kết nối qua VPN/private interconnect | Data transfer hoặc service dependency giữa hai cloud |
| SD-WAN overlay | Điều khiển kết nối nhiều site/carrier/cloud bằng policy | Nhiều chi nhánh và đường truyền đa dạng |
| Application-level connectivity | API, message broker, service mesh hoặc secure proxy | Chỉ cần kết nối capability, không cần mở rộng network rộng |

Không phải mọi ứng dụng hybrid đều cần mở rộng mạng layer 3 giữa hai môi trường. Với một số tích hợp, API gateway, private service endpoint, message broker hoặc file transfer service có thể tạo trust boundary hẹp hơn và dễ vận hành hơn.

### 1.2. Network connectivity và application connectivity

Network connectivity cung cấp khả năng truyền packet giữa các endpoint. Application connectivity còn bao gồm:
- DNS hostname được phân giải đúng.
- TLS certificate và trust chain hợp lệ.
- Authentication/authorization.
- Protocol/port và application policy.
- Service discovery và endpoint health.
- Retry, timeout và idempotency.
- Data classification và audit.

Khi kiểm tra sự cố, không kết luận “network đã thông” chỉ vì ping hoặc TCP handshake thành công. Ứng dụng có thể vẫn lỗi do TLS, identity, DNS, proxy hoặc policy.

## 2. Thu thập yêu cầu trước khi vẽ topology

Thiết kế bắt đầu bằng các flow nghiệp vụ, không bắt đầu bằng việc chọn một sản phẩm VPN hoặc transit gateway.

### 2.1. Lập ma trận flow

Mỗi flow cần mô tả source, destination, protocol, port, direction, data classification, traffic profile và owner.

| Flow | Source | Destination | Protocol | Mức quan trọng |
| --- | --- | --- | --- | --- |
| Booking API to legacy ERP | App subnet Cloud A | ERP private subnet | HTTPS | Cao |
| Cloud A app to on-prem database | Private workload | Database subnet | TCP database port | Rất cao |
| Cloud B analytics to Cloud A object API | Analytics subnet | Private service endpoint | HTTPS | Theo lịch |
| On-prem DNS to cloud private zone | Corporate resolver | Cloud resolver | DNS TCP/UDP 53 | Cao |
| Cloud workloads to identity | Private workload | Identity endpoints | HTTPS/LDAPS tùy thiết kế | Rất cao |
| Monitoring to network devices | Monitoring subnet | Network management subnet | Approved management protocols | Cao |

Không tạo rule kiểu any-to-any chỉ vì flow chưa được thống kê. Thiếu thông tin phải trở thành một action để xác minh owner và application behavior.

### 2.2. Các dimension cần lượng hóa

- Latency: round-trip time, p95/p99 và deadline của ứng dụng.
- Throughput: peak Mbps/Gbps, packet rate, burst và concurrency.
- Availability: SLO của flow, maintenance window và failure tolerance.
- Data volume: bytes/ngày, peak replication và growth.
- Direction: ingress, egress, symmetric/asymmetric.
- Security: trust level, encryption, data class, source identity.
- Residency: dữ liệu được phép đi qua region/country nào.
- Recovery: RTO/RPO, failover time và acceptable data lag.
- Cost: port/connectivity fee, VPN, egress, NAT, inspection và operations.
- Ownership: team quản lý source, destination, resolver và route.

### 2.3. Critical path và optional path

Tách flow synchronous cần hoàn thành request khỏi flow asynchronous/background. Một ứng dụng không nên phụ thuộc vào analytics network để xác nhận booking nếu analytics có thể xử lý sau. Giảm dependency đồng bộ có thể giảm yêu cầu availability và latency xuyên môi trường.

## 3. IP address planning và tránh CIDR overlap

IP plan là nền tảng của routing. CIDR overlap giữa data center, VPC/VNet và các cloud provider có thể khiến route không thể phân biệt hoặc buộc NAT workaround phức tạp.

### 3.1. Xây dựng địa chỉ có cấu trúc

Một kế hoạch có thể phân vùng theo:
- Organization/business domain.
- Environment: production, staging, development.
- Region/site.
- Network zone: ingress, application, data, management.
- Shared services.
- Future expansion và reserved blocks.

Ví dụ minh họa:

| Phạm vi | CIDR ví dụ | Vai trò |
| --- | --- | --- |
| On-prem primary | 10.10.0.0/16 | Data center chính |
| On-prem DR | 10.11.0.0/16 | Site phục hồi |
| Cloud A production | 10.40.0.0/16 | Workload chính |
| Cloud A staging | 10.41.0.0/16 | Test/staging |
| Cloud B production | 10.60.0.0/16 | Analytics/service khác |
| Shared services | 10.80.0.0/16 | DNS, monitoring, security |

Các CIDR chỉ là ví dụ, phải kiểm tra với toàn bộ mạng hiện có, partner network và future acquisition trước khi sử dụng.

### 3.2. Reserve và summarize

Không cấp phát toàn bộ address space ngay từ đầu. Giữ block dự phòng cho region/site mới, subnet growth, IPv6 và transition. Thiết kế có thể summarize route ở cấp environment hoặc region để giảm số route quảng bá; tuy nhiên summary quá rộng có thể kéo traffic vào một network không có destination thực hoặc che route cụ thể cần ưu tiên.

### 3.3. Kiểm tra overlap

Trước khi kết nối:
1. Thu thập CIDR từ data center, VPC/VNet, Kubernetes pod/service network và partner.
2. Chuẩn hóa prefix và owner.
3. Tính toán overlap, kể cả subnet chưa được route quảng bá.
4. Xác định CIDR reserved nhưng chưa dùng.
5. Đánh giá IPv4/IPv6 dual stack.
6. Lưu IPAM registry làm nguồn chuẩn.
7. Chặn việc cấp phát overlap qua policy/process.

Kubernetes Pod CIDR và Service CIDR thường bị quên trong IP inventory; khi kết nối cluster với network bên ngoài, overlap có thể làm route hoặc service discovery khó dự đoán.

### 3.4. Khi không thể đổi địa chỉ

Nếu hai môi trường đã dùng CIDR overlap, các lựa chọn gồm:
- Re-address một network theo migration plan.
- Dùng NAT/prefix translation trong phạm vi được hỗ trợ.
- Đặt application proxy hoặc gateway thay vì route trực tiếp.
- Tách routing domain/VRF và chỉ publish service endpoint cần thiết.
- Chuyển sang application-level connectivity.

NAT giải quyết một số bài toán địa chỉ nhưng làm log, source identity, troubleshooting và return path phức tạp hơn. Không dùng NAT diện rộng mà không tài liệu hóa mapping và ownership.

## 4. Các lựa chọn kết nối

### 4.1. Site-to-site IPsec VPN

VPN site-to-site tạo tunnel được mã hóa qua Internet hoặc network trung gian. Hai đầu tunnel thường là customer gateway và cloud VPN endpoint.

Ưu điểm:
- Triển khai tương đối nhanh.
- Linh hoạt với nhiều site và provider.
- Chi phí đầu tư ban đầu thường thấp hơn dedicated link.
- Có thể dùng làm backup path.

Trade-off:
- Throughput/latency chịu ảnh hưởng Internet và tunnel endpoint.
- Cần quản lý IKE/IPsec, key/certificate, rekey và MTU.
- Có thể gặp fragmentation hoặc MSS issue.
- Quality và routing failover phụ thuộc cấu hình hai đầu.
- Internet path có thể đi qua nhiều carrier không kiểm soát được.

VPN phù hợp cho workload có yêu cầu vừa phải, kết nối tạm thời, backup connectivity hoặc nơi chưa có dedicated circuit. Cần benchmark throughput thực tế thay vì chỉ dựa vào tốc độ tunnel danh nghĩa.

### 4.2. Dedicated private connectivity

Dedicated connectivity dùng circuit/port hoặc interconnect thông qua provider/partner để kết nối private network tới cloud.

Ưu điểm:
- Throughput và latency thường ổn định hơn Internet VPN.
- Có thể phù hợp data transfer lớn và workload nhạy latency.
- Có thể giảm exposure Internet ở network path.
- Hỗ trợ nhiều mô hình private routing.

Trade-off:
- Thời gian provisioning dài hơn.
- Chi phí port, cross-connect, carrier và data transfer.
- Cần thiết kế redundant circuit/site/provider.
- Private connection không tự động mã hóa end-to-end.
- Vẫn cần firewall, IAM, TLS và segmentation.

Không mặc định dedicated circuit là encrypted. Nếu data classification yêu cầu confidentiality trên đường truyền, đánh giá IPsec hoặc TLS trên dedicated connection.

### 4.3. SD-WAN

SD-WAN điều khiển overlay traffic giữa các site và cloud theo policy, link quality, application class hoặc SLA. Có thể dùng nhiều Internet link và private circuit.

Phù hợp với doanh nghiệp có nhiều chi nhánh, cần centralized policy và dynamic path selection. Tuy nhiên, controller/orchestrator, edge devices, licensing và integration tạo thêm operational dependency.

### 4.4. Cloud transit service

Cloud provider có thể cung cấp transit gateway, virtual WAN, cloud router hoặc hub networking service. Chúng giúp kết nối nhiều VPC/VNet, VPN và dedicated links qua một routing domain tập trung.

Ưu điểm là giảm số kết nối point-to-point và có central route control. Trade-off là giới hạn quota, charge theo attachment/data processing, shared failure domain và nguy cơ trở thành choke point.

### 4.5. So sánh tổng quan

| Tiêu chí | VPN | Dedicated connection | SD-WAN | Cloud transit hub |
| --- | --- | --- | --- | --- |
| Provisioning | Nhanh | Chậm hơn | Phụ thuộc overlay/edge | Tương đối nhanh trong cloud |
| Latency consistency | Phụ thuộc Internet | Thường ổn định hơn | Policy chọn path | Phụ thuộc attachment/region |
| Throughput | Theo tunnel/Internet | Có thể cao | Theo underlay | Theo quota/service limit |
| Encryption | IPsec | Không mặc định | Tùy overlay | Tùy dịch vụ/path |
| Scale site | Tunnel/routing tăng | Cần circuit/site | Policy-driven | Attachment-driven |
| Cost | Thấp đến trung bình | Trung bình đến cao | License/edge/transport | Attachment/data processing |
| Use case | Backup/low-medium traffic | High-volume/critical | Multi-site policy | Hub-and-spoke cloud |

## 5. Topology: hub-and-spoke, mesh và transit

### 5.1. Point-to-point mesh

Trong full mesh, mỗi network kết nối trực tiếp với network khác. Với N site, số cặp kết nối có thể tăng theo N(N-1)/2. Cách này có thể cho path ngắn nhưng khó vận hành khi site tăng.

Ưu điểm:
- Direct path.
- Có thể tối ưu latency theo pair.
- Không cần central hub cho mọi flow.

Hạn chế:
- Số tunnel/circuit và route tăng.
- Segmentation khó quản lý.
- Thay đổi network phải đồng bộ nhiều nơi.
- Troubleshooting và ownership phức tạp.

### 5.2. Hub-and-spoke

Các spoke kết nối về một hoặc nhiều hub. Hub thực hiện transit routing, inspection, logging hoặc shared services.

~~~mermaid
flowchart TB
    DC["On-prem data center"] --> HUB["Transit hub / firewall"]
    A["Cloud A production VPC"] --> HUB
    B["Cloud A staging VPC"] --> HUB
    C["Cloud B workload network"] --> HUB
    HUB --> SHARED["DNS / identity / monitoring"]
    HUB --> PARTNER["Partner private network"]
~~~

Ưu điểm:
- Centralized routing và security inspection.
- Giảm point-to-point connection.
- Dễ áp dụng shared DNS/egress.
- Có thể quản lý connectivity theo spoke attachment.

Rủi ro:
- Hub thành bottleneck hoặc shared failure domain.
- East-west traffic có thể hairpin qua hub làm tăng latency/cost.
- Route table và propagation phức tạp.
- Một lỗi policy có thể tác động nhiều spoke.

Có thể triển khai nhiều hub theo region, environment hoặc trust domain. Tránh để production và sandbox tự động route lẫn nhau chỉ vì cùng attach một transit network.

### 5.3. Transit theo domain và segmentation

Một mô hình có thể tách:
- Production hub.
- Non-production hub.
- Shared services hub.
- Partner/external connectivity hub.
- Restricted data zone.

Inter-hub connectivity chỉ mở theo flow được duyệt. Đây là cách thu hẹp blast radius và giảm khả năng lateral movement.

### 5.4. Hybrid transit giữa nhiều cloud

Có thể kết nối mỗi cloud vào một colocation/transit provider hoặc vào network hub do tổ chức vận hành. Khi đó cần xác định:
- Ai quản lý underlay/circuit?
- Ai quảng bá route?
- Route propagation giữa provider nào được phép?
- DNS resolver nằm ở đâu?
- Egress inspection và data loss controls ở đâu?
- Khi một cloud/provider outage, các cloud còn lại có tiếp tục kết nối không?
- Có phụ thuộc vào một control plane hoặc một carrier duy nhất không?

Không nên tạo một global flat network chỉ để các cloud “nhìn thấy nhau”. Cần publish service path cụ thể.

## 6. Routing fundamentals

Routing quyết định packet đi tới next hop nào dựa trên destination prefix, route table, policy và metric.

### 6.1. Static routing

Static route được cấu hình thủ công hoặc qua IaC. Dễ hiểu với topology nhỏ và prefix ổn định, nhưng cần cập nhật thủ công khi network thay đổi và không tự thích ứng tốt với link failure nếu thiếu health automation.

### 6.2. Dynamic routing và BGP

BGP trao đổi route giữa autonomous system hoặc routing domains. Trong hybrid cloud, BGP thường được dùng để quảng bá prefix giữa customer network và cloud router/VPN/dedicated gateway.

Các khái niệm cần nắm:
- Prefix: network được quảng bá.
- AS number: định danh autonomous system.
- Neighbor/peer: router trao đổi BGP.
- Local preference: lựa chọn đường đi trong AS.
- AS path: chuỗi AS qua đó route được quảng bá.
- MED: gợi ý preference giữa các entry point, semantics tùy policy.
- Communities: metadata để áp dụng route policy.
- Prefix filter: giới hạn route được nhận/quảng bá.

Không chỉ bật BGP và chấp nhận mọi route. Cần prefix allowlist, max-prefix limit, community policy và review route change.

### 6.3. Route propagation và isolation

Một transit hub có thể tự động propagate route từ attachment này sang attachment khác. Nếu không giới hạn, staging có thể học route tới production hoặc partner network có thể thấy prefix nội bộ không liên quan.

Thiết kế:
- Route table riêng theo trust domain.
- Explicit association/propagation.
- Prefix allowlist/denylist.
- Summarization có kiểm soát.
- Default route chỉ qua inspection/egress path phù hợp.
- Không quảng bá management network sang spoke không cần.
- Audit mọi route table và BGP change.

### 6.4. Asymmetric routing

Asymmetric routing xảy ra khi đường đi và đường về khác nhau. Stateful firewall/NAT có thể drop packet nếu return path không đi qua cùng stateful device hoặc không có session synchronization phù hợp.

Ví dụ outbound đi qua firewall hub A nhưng return route về qua hub B. TCP session có thể thất bại dù cả hai hướng đều có route. Cần:
- Xác định path symmetry requirement.
- Kiểm tra route table hai chiều.
- Cân nhắc firewall insertion/service chaining.
- Kiểm tra NAT state và session behavior.
- Test failover khi một path mất.

### 6.5. MTU, MSS và fragmentation

Encapsulation của IPsec/VXLAN/SD-WAN giảm payload hữu dụng so với MTU underlay. Packet lớn có thể bị fragmentation hoặc drop nếu path MTU discovery bị chặn. Biểu hiện thường là kết nối TCP mở được nhưng truyền payload lớn bị treo.

Cần:
- Xác định MTU end-to-end.
- Điều chỉnh TCP MSS khi phù hợp.
- Cho phép ICMP cần thiết cho PMTUD theo policy.
- Test packet size/throughput hai chiều.
- Kiểm tra overhead của nhiều lớp tunnel.

## 7. DNS trong kiến trúc hybrid và multi-cloud

DNS là control plane quan trọng của connectivity. Ứng dụng thường gọi hostname; DNS ánh xạ hostname thành địa chỉ và các record/service metadata. Private DNS cần được thiết kế xuyên environment thay vì tạo nhiều zone trùng lặp không có ownership.

### 7.1. Public DNS và private DNS

- Public DNS phục vụ tên được resolve từ Internet.
- Private DNS phục vụ tên nội bộ trong network/domain được liên kết.
- Split-horizon DNS trả lời khác nhau tùy resolver/source context.
- Conditional forwarding chuyển query của một namespace tới resolver được chỉ định.
- Delegation giao quyền quản lý một zone/subdomain cho name server khác.

Không publish private endpoint hoặc internal hostname ra public DNS nếu không có chủ đích và security review.

### 7.2. Namespace và zone ownership

Có thể chia:
- Public domain, ví dụ example.com.
- Internal namespace, ví dụ corp.example.internal.
- Environment subdomain, ví dụ prod.corp.example.internal.
- Service discovery zone, ví dụ svc.cluster.local (phạm vi cluster).
- Cloud private zone theo region/account nếu cần.

Cần quyết định owner cho từng zone, ai có quyền create record, naming convention, TTL, lifecycle và record conflict handling. Tránh nhiều resolver có authority cho cùng namespace mà không có delegation rõ.

### 7.3. Resolver architecture

~~~mermaid
flowchart TB
    ONP["On-prem client"] --> OR["Corporate DNS resolver"]
    OR -->|Conditional forward| CR["Cloud DNS resolver"]
    CR --> PZ["Cloud private zone"]
    CR -->|Forward corp zone| OR
    W["Cloud workload"] --> WR["VPC/VNet resolver"]
    WR --> PZ
    WR -->|Forward legacy zone| OR
~~~

Sơ đồ minh họa luồng hai chiều có thể dùng, nhưng cần cấu hình tránh forwarding loop. Nếu corporate resolver forward toàn bộ internal zone sang cloud, còn cloud resolver lại forward cùng zone về corporate, query có thể quay vòng cho tới timeout.

### 7.4. Conditional forwarding

Ví dụ:
- Query corp.example.com từ cloud được forward về corporate DNS.
- Query cloud.internal.example.com từ on-prem được forward về cloud resolver.
- Query public domain dùng recursive resolver đã được quản lý.
- Query service namespace được xử lý bởi cluster/service resolver.

Cần xác định zone suffix cụ thể, forward target redundancy, timeout, retry và policy về recursion. Không forward root zone hoặc domain quá rộng nếu không cần.

### 7.5. Private DNS visibility

Private zone thường chỉ được visible trong các VPC/VNet hoặc resolver context được associate/link. Multi-account/multi-region cần quy trình association và authorization. Private DNS record có thể resolve từ một environment nhưng không từ environment khác nếu thiếu zone link hoặc forwarding.

### 7.6. DNS caching và TTL

TTL thấp giúp thay đổi record có thể có hiệu lực nhanh hơn, nhưng không đảm bảo toàn bộ client cập nhật ngay. Resolver, OS, JVM, browser, connection pool và service mesh có thể cache theo semantics riêng.

Cần xem:
- Authoritative TTL.
- Recursive resolver cache.
- Negative caching.
- JVM/OS DNS cache.
- Long-lived connection.
- Application endpoint cache.
- Health check và failover propagation.

Đừng giả định TTL 30 giây có nghĩa mọi traffic chuyển vùng trong 30 giây.

## 8. DNS failover và service discovery

### 8.1. DNS-based failover

DNS health check có thể thay record hoặc trả endpoint còn khỏe. Phù hợp cho một số endpoint public/private nếu client tuân thủ TTL và DNS architecture hỗ trợ.

Hạn chế:
- Cache có thể giữ IP cũ.
- Resolver health check không luôn phản ánh business health.
- Client connection hiện tại không tự chuyển.
- DNS update và data consistency là hai vấn đề riêng.
- Private zone/conditional forward có thể không đồng bộ với public failover.

### 8.2. Service discovery

Trong cloud-native environment, service discovery có thể dùng:
- Kubernetes Service DNS.
- Cloud service registry.
- Internal load balancer.
- Service mesh control plane.
- Application config/service catalog.

Không lạm dụng DNS để thay thế health-aware load balancing ở tầng application. DNS thường phù hợp discovery/endpoint resolution; health check và traffic steering có thể cần LB/service mesh.

### 8.3. Split-brain và stale record

Trong DR, nếu cả primary và secondary cùng nhận write do DNS cập nhật không đồng bộ, hệ thống có thể tạo split-brain. DNS không phải cơ chế fencing. Cần leadership/quorum/fencing hoặc read-only mode cho site cũ trước khi mở writer mới.

## 9. Segmentation và Zero Trust giữa môi trường

Network connectivity rộng làm tăng blast radius. Segmentation kiểm soát workload nào được nói chuyện với workload nào; Zero Trust bổ sung xác minh identity và policy cho mỗi access.

### 9.1. Segmentation layers

- Physical/underlay boundary.
- VPC/VNet/subnet.
- Route table/VRF.
- Firewall/security group/network ACL.
- Kubernetes network policy.
- Workload identity và service-to-service authorization.
- Application/API policy.

Không coi subnet private là đủ an toàn. Private chỉ có nghĩa không trực tiếp routable từ Internet theo topology; workload bên trong vẫn cần identity, least privilege và monitoring.

### 9.2. Environment isolation

Production, staging và development nên có routing boundary rõ. Nếu staging cần truy cập production data, dùng masked/approved dataset hoặc service interface có policy; không mở route toàn bộ chỉ để debug.

### 9.3. Egress control

Chọn điểm egress có kiểm soát qua firewall/proxy/NAT gateway. Cần:
- Allowlist destination/domain/IP theo workload.
- TLS inspection chỉ khi policy/pháp lý cho phép.
- DNS filtering/resolution policy.
- Logging và data loss monitoring.
- Quota và bandwidth control.
- Egress cost monitoring.

Egress tập trung có thể tăng visibility nhưng tạo bottleneck và cost. Có thể dùng distributed egress theo region với policy đồng nhất.

## 10. High availability và redundancy của đường kết nối

Một kiến trúc HA cần nhiều hơn hai tunnel cùng kết nối tới một router, một carrier hoặc một facility duy nhất. Redundancy chỉ có giá trị khi failure domain độc lập đủ mức.

### 10.1. Các lớp redundancy

- Hai tunnel VPN tới hai endpoint/gateway khác nhau.
- Hai circuit qua carrier hoặc path vật lý khác nhau.
- Hai edge router/site.
- Cloud gateway attachment ở nhiều AZ/region theo service design.
- Resolver redundancy.
- Multiple DNS forwarding targets.
- Redundant firewall/inspection path.
- Independent management/control-plane access.

Cần kiểm tra dịch vụ provider thực sự phân tách endpoint/failure domain như thế nào. Hai logical connection có thể vẫn share physical facility hoặc carrier.

### 10.2. Failover behavior

Có thể dùng:
- BGP route withdrawal khi link down.
- Health check và route policy.
- SD-WAN application-aware path selection.
- DNS failover cho endpoint phù hợp.
- Application retry/connection re-establishment.
- Traffic manager/global load balancing.

Không dùng BGP route availability làm proxy duy nhất cho application health. Link có thể up nhưng packet loss/latency hoặc destination service đã hỏng.

### 10.3. Failover capacity

Nếu link chính 10 Gbps và link dự phòng 1 Gbps, failover có thể làm toàn workload bị nghẽn. Tính peak critical traffic, control traffic, replication, backup và recovery workload. Xác định traffic class nào phải giữ, class nào được rate-limit/load-shed.

### 10.4. Failback

Sau khi đường chính phục hồi:
- Xác minh stability đủ thời gian.
- Kiểm tra route preference/metric.
- Tránh route oscillation.
- Chuyển traffic có kiểm soát.
- Theo dõi session reset và packet loss.
- Kiểm tra DNS/connection cache.
- Xác nhận data replication backlog.
- Giữ rollback option nếu path chính chưa ổn định.

## 11. Bảo mật kết nối và quản lý trust

Private routing không thay thế encryption, authentication và authorization.

### 11.1. Encryption in transit

Dùng TLS cho application protocol; IPsec cho network tunnel khi phù hợp. Dedicated private circuit vẫn có thể cần encryption. Quản lý certificate/key lifecycle, rotation, revocation, trust store và clock synchronization.

### 11.2. Network identity và workload identity

Không chỉ xác định source bằng IP. IP có thể thay đổi do autoscaling, NAT hoặc migration. Kết hợp:
- Workload identity/certificate.
- Mutual TLS khi phù hợp.
- IAM/service account.
- Network source/destination constraints.
- Application authorization.
- Short-lived credential và rotation.

### 11.3. Route và control-plane security

Bảo vệ BGP session, router management, cloud network API, DNS zone write và transit attachment. Dùng RBAC, MFA, audit và approval. Route leak có thể mở exposure trên diện rộng dù application security group không đổi.

### 11.4. DNS security

- Hạn chế ai có quyền sửa zone/record.
- Audit dynamic DNS update.
- Dùng resolver được quản lý.
- Kiểm soát recursion và forwarding target.
- Bảo vệ transfer/delegation.
- Dùng DNSSEC cho public zone khi phù hợp.
- Theo dõi query bất thường và tunneling.
- Tránh ghi sensitive data vào hostname/record.

## 12. Multi-cloud routing và service placement

Nhiều provider có khái niệm VPC/VNet, routing, private endpoint và transit khác nhau. Không giả định các service tương đương hoàn toàn hoặc hỗ trợ cùng semantics.

### 12.1. Cloud-to-cloud patterns

- Site-to-site VPN giữa cloud network endpoints.
- Dedicated interconnect qua carrier/colocation provider.
- Hub/transit network do tổ chức vận hành.
- SD-WAN overlay.
- Application/API integration qua private endpoint hoặc gateway.
- Replication pipeline qua managed data service.

Lựa chọn phụ thuộc traffic, latency, volume, security, provider support, region và cost.

### 12.2. Place workload gần dependency

Một service đọc database thường xuyên nên được đặt gần database nếu latency và data residency cho phép. Cross-cloud synchronous call trên critical path có thể làm tăng latency và giảm availability do phải phụ thuộc vào hai provider cùng lúc.

Có thể giảm dependency xuyên cloud bằng:
- Event-driven integration.
- Data replication với freshness contract.
- Local cache/materialized view.
- Async command/response.
- Bulk data transfer theo batch.
- API boundary có timeout/retry/circuit breaker.

Không replicate dữ liệu nhạy cảm sang provider khác chỉ để giảm latency nếu chưa đánh giá residency, encryption, access và retention.

### 12.3. Service placement decision matrix

| Tiêu chí | Câu hỏi |
| --- | --- |
| Latency | User và dependency ở đâu? Critical path có cross-cloud không? |
| Data gravity | Dataset lớn nằm ở đâu và cần di chuyển bao nhiêu? |
| Residency | Có giới hạn country/region/provider? |
| Availability | Có single provider/network dependency không? |
| Egress | Chi phí truyền dữ liệu và API request? |
| Security | Identity/key/policy giữa provider được quản lý ra sao? |
| Operations | Ai trực, ai debug route/DNS và ai làm incident command? |
| Portability | Workload có thực sự portable hay phụ thuộc managed service? |

## 13. Observability cho network và DNS

Một thiết kế hybrid/multi-cloud cần visibility xuyên các boundary. Logs ở một phía không đủ để điều tra packet mất giữa đường.

### 13.1. Telemetry cần thu thập

| Layer | Telemetry |
| --- | --- |
| Connectivity | Tunnel state, circuit status, BGP neighbor, route count |
| Routing | Route change, prefix, next hop, route propagation |
| Network flow | Source/destination, port/protocol, bytes, accept/reject |
| Firewall | Rule hit, deny, session count, threat alert |
| DNS | Query, response code, latency, forwarding target, cache |
| Application | Connect timeout, TLS error, request latency, retry |
| Synthetic | DNS lookup, TCP connect, TLS handshake, business probe |
| Capacity | Throughput, packet loss, jitter, interface utilization |

Bảo vệ log vì địa chỉ IP, hostname và flow pattern có thể tiết lộ topology nội bộ.

### 13.2. Synthetic end-to-end probes

Một probe hữu ích nên kiểm tra lần lượt:
1. Resolve hostname từ đúng network context.
2. Kiểm tra record/TTL/target IP.
3. TCP connect tới port cần thiết.
4. TLS handshake/certificate validation.
5. Authentication bằng test identity.
6. Gọi endpoint health hoặc transaction an toàn.
7. Ghi latency và failure stage.

Probe chạy từ một subnet không đại diện không thể chứng minh mọi network path đều hoạt động. Triển khai probe ở on-prem, cloud A, cloud B và các zone cần thiết.

### 13.3. SLO cho connectivity

Có thể định nghĩa:
- Availability của end-to-end private path.
- DNS resolution success rate.
- p95/p99 DNS latency.
- Packet loss/jitter/RTT.
- Tunnel/BGP recovery time.
- Failover time.
- Application transaction success.
- Route/DNS change error budget.

SLO network cần gắn với service outcome. Tunnel up 100% nhưng API không truy cập được vẫn là failure đối với người dùng.

## 14. Troubleshooting theo lớp

Khi một service không kết nối được, điều tra theo thứ tự giúp tránh thay đổi route/firewall ngẫu nhiên.

### 14.1. DNS

- Query từ đúng host/resolver.
- Kiểm tra search suffix và record type.
- Xem authoritative/recursive answer.
- Kiểm tra conditional forwarding và zone link.
- Kiểm tra negative cache/stale cache.
- Xác minh IP answer thuộc đúng environment.

### 14.2. Routing

- Kiểm tra source/destination CIDR.
- Xem route table và longest-prefix match.
- Kiểm tra BGP neighbor/advertised/received prefixes.
- Xem route filter/propagation và next hop.
- Xác minh route hai chiều/asymmetric path.
- Kiểm tra NAT mapping nếu có.

### 14.3. Transport và policy

- TCP connect và port reachability.
- Firewall/security group/NACL/host firewall.
- MTU/MSS và fragmentation.
- Packet loss, retransmission, jitter.
- TLS certificate, SNI, cipher và trust store.
- Proxy, service mesh và egress policy.

### 14.4. Application và identity

- Authentication/authorization.
- Token audience/issuer/expiry.
- Service identity và certificate rotation.
- Timeout/retry/circuit breaker.
- Application logs và dependency health.
- Data residency/tenant policy.

Ping fail không luôn chứng minh service unreachable; ICMP có thể bị chặn trong khi TCP hoạt động. Ngược lại, ping thành công không chứng minh TLS/application request thành công.

## 15. Change management và vận hành

Network/DNS changes có blast radius lớn, vì vậy cần change control và rollback rõ.

### 15.1. Change record

Mỗi thay đổi nên có:
- Change ID và business reason.
- Source/destination flow.
- Affected CIDR, route, BGP policy, DNS zone/record.
- Security approval và data classification.
- Owner của hai đầu kết nối.
- Pre/post validation.
- Deployment window.
- Rollback configuration.
- Monitoring/alert.
- Dependency và affected environment.

### 15.2. Routing change

Trước khi thay route:
- Review route table diff.
- Xác định prefix mới/bị rút.
- Kiểm tra route summarization.
- Kiểm tra maximum prefix và policy.
- Dùng canary/route target nhỏ nếu hỗ trợ.
- Theo dõi flow logs và BGP stability.
- Chuẩn bị revert.

Một route quảng bá sai có thể khiến nhiều network gửi traffic tới một blackhole hoặc tạo route leak. Thực hiện theo từng domain và có giới hạn blast radius.

### 15.3. DNS change

Trước khi đổi record:
- Xác định authoritative owner.
- Kiểm tra TTL và cache behavior.
- Giảm TTL trước cutover nếu cần và đủ thời gian.
- Xác nhận certificate/SNI phù hợp hostname mới.
- Kiểm tra resolver từ các environment.
- Chuẩn bị rollback record.
- Theo dõi query error và synthetic probe.

### 15.4. Ownership và support model

Rõ ai sở hữu:
- Underlay/carrier circuit.
- VPN/SD-WAN edge.
- Cloud transit gateway.
- Route policy/BGP.
- DNS zone/resolver.
- Firewall/inspection.
- Workload endpoint và certificate.
- Incident command và escalation với provider.

Nếu một route đi qua ba team và hai provider, runbook phải có contact/escalation chain cụ thể, không chỉ ghi “network team”.

## 16. Case study: kết nối on-premises, Cloud A và Cloud B

### 16.1. Bối cảnh

Một doanh nghiệp có ERP và corporate DNS tại data center. Booking API và PostgreSQL managed chạy trên Cloud A. Analytics và reporting chạy trên Cloud B. Booking cần đọc một số dữ liệu ERP; analytics nhận event và batch export từ Cloud A.

Yêu cầu giả định:
- Booking-to-ERP có p95 RTT target 40 ms trong điều kiện bình thường.
- Critical transaction cần đường kết nối redundant.
- Analytics transfer có thể chạy bất đồng bộ.
- Production và staging phải cô lập.
- DNS nội bộ cần resolve từ cả ba môi trường.
- Data restricted không được chuyển ra region không được phê duyệt.

### 16.2. Topology đề xuất

~~~mermaid
flowchart TB
    subgraph ONP["On-premises"]
      ERP["ERP services"]
      DNS["Corporate DNS"]
      EDGE["Redundant edge routers"]
      ERP --> EDGE
      DNS --> EDGE
    end
    subgraph A["Cloud A"]
      HUBA["Transit hub A"]
      APP["Booking API"]
      DB[("Managed PostgreSQL")]
      APP --> DB
      APP --> HUBA
    end
    subgraph B["Cloud B"]
      HUBB["Transit hub B"]
      ANALYTICS["Analytics workers"]
      LAKE[("Data lake")]
      ANALYTICS --> LAKE
      ANALYTICS --> HUBB
    end
    EDGE <-->|"Dedicated primary + IPsec backup"| HUBA
    EDGE <-->|"IPsec / private transit"| HUBB
    HUBA <-->|"Controlled inter-cloud routes"| HUBB
    DNS <-->|"Conditional DNS forwarding"| HUBA
~~~

Sơ đồ minh họa một topology. Cấu hình thật phải phân tích liệu Cloud A và Cloud B có nên kết nối trực tiếp hay qua data center/transit provider; không để mọi traffic analytics hairpin qua Cloud A nếu có private interconnect phù hợp.

### 16.3. DNS

- Corporate DNS authoritative cho erp.corp.example.com.
- Cloud A resolver forward corp.example.com về corporate DNS qua redundant path.
- Corporate DNS conditional-forward cloud.internal.example.com về Cloud A resolver.
- Cloud B có resolver riêng và chỉ forward namespace cần thiết.
- Private zone liên kết vào đúng VPC/VNet.
- Synthetic probes kiểm tra từ on-prem, Cloud A và Cloud B.
- Có rule ngăn forwarding loop và logging query.

### 16.4. Routing và security

- IPAM xác nhận CIDR không overlap.
- Dedicated connection là primary cho booking critical path; IPsec là backup.
- BGP prefix filter chỉ quảng bá các network được phê duyệt.
- Production route table tách staging.
- ERP service chỉ nhận source từ booking subnet/identity path phù hợp.
- Cloud B chỉ nhận data export cần thiết, qua endpoint/service interface đã duyệt.
- TLS bảo vệ application traffic ngay cả trên private connection.
- Firewall logs và flow logs được gửi về monitoring account.

### 16.5. Resilience và operations

Diễn tập mất dedicated link:
- BGP/health policy chuyển sang VPN.
- Đo RTT, throughput và packet loss.
- Verify booking transaction vẫn trong SLO hoặc chuyển sang degraded mode.
- Analytics batch bị throttle nếu link backup không đủ bandwidth.
- Khi link chính phục hồi, chuyển path có kiểm soát.
- Kiểm tra DNS và long-lived connections không giữ endpoint cũ.
- Ghi failover/failback time và cost.

### 16.6. Quyết định cần ghi ADR

ADR nên giải thích:
- Tại sao chọn dedicated primary và VPN backup.
- Tại sao Cloud B không route toàn bộ production CIDR.
- Namespace DNS và owner của zone.
- Prefix allowlist và route propagation.
- Data flows được phép giữa provider.
- Failover capacity và SLO.
- Chi phí connectivity/egress.
- Residual risks và operational owner.

## 17. Anti-pattern và lỗi thường gặp

| Anti-pattern | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Flat network nối tất cả cloud | Blast radius/lateral movement rộng | Segment theo trust domain và publish flow |
| Không quản lý IPAM | CIDR overlap, NAT workaround | Central address registry và allocation policy |
| Full mesh không có scale plan | Tunnel/route tăng nhanh | Transit hub hoặc overlay policy |
| Một hub không redundancy | Shared failure domain | Multi-hub/region và diverse path |
| BGP nhận mọi prefix | Route leak/blackhole | Prefix filtering, max-prefix, community |
| Route hai chiều không đối xứng | Stateful firewall/NAT drop | Path symmetry design và packet test |
| Chỉ test ping | TLS/app vẫn có thể fail | End-to-end synthetic probe |
| DNS forward cả namespace vòng lặp | Query timeout | Explicit suffix ownership/forwarding graph |
| Giả định TTL quyết định failover time | Client còn cache/connection cũ | Measure resolver/runtime/application cache |
| Dùng DNS để fencing writer | Split-brain | Quorum/lease/fencing riêng |
| Dedicated circuit không mã hóa | Confidentiality không được bảo đảm | TLS/IPsec theo data classification |
| Shared transit mở mọi environment | Staging reach production | Separate route domains và explicit policy |
| Failover link thiếu capacity | Critical traffic nghẽn | Capacity test và traffic class priority |
| Không có owner hai đầu | Incident kéo dài | RACI, runbook và escalation |

## 18. Bài tập thực hành

Một doanh nghiệp có hai data center, Cloud A với ba VPC production, Cloud B với hai VPC analytics và 20 chi nhánh. Các hệ thống dùng nhiều dải RFC1918 khác nhau; hai VPC có CIDR overlap. Corporate DNS đang phục vụ domain nội bộ, mỗi cloud cũng có private zone riêng. Booking API tại Cloud A cần gọi ERP on-prem; analytics chỉ cần lấy dữ liệu theo batch. Doanh nghiệp muốn có hai đường kết nối dự phòng và giữ production tách staging.

Hãy thực hiện:

1. Thu thập flow matrix gồm source/destination/protocol/port/data class/owner/traffic.
2. Thiết kế IPAM plan và giải pháp cho hai VPC CIDR overlap; nêu trade-off re-address, NAT hoặc application proxy.
3. So sánh VPN, dedicated connectivity và SD-WAN cho 20 chi nhánh cùng hai data center.
4. Vẽ topology hub-and-spoke hoặc multi-hub; xác định failure domain của carrier, edge router, cloud gateway và region.
5. Thiết kế BGP prefix filter, route summary, route propagation và isolation giữa production/staging.
6. Xác định cách tránh asymmetric routing khi traffic đi qua firewall/NAT.
7. Thiết kế DNS namespace, private zone ownership và conditional forwarding hai chiều mà không tạo loop.
8. Định nghĩa TTL/cache/failover behavior cho private endpoint và public service.
9. Thiết kế segmentation và egress control theo workload identity/data classification.
10. Tính capacity cần cho link backup khi booking critical flow và control traffic vẫn phải hoạt động.
11. Xây synthetic probe kiểm tra DNS, TCP, TLS, auth và business endpoint từ mọi môi trường.
12. Viết runbook cho mất link, route leak, DNS outage, CIDR overlap và failback.
13. Định nghĩa SLO và dashboard cho RTT, packet loss, DNS success, BGP stability, failover time và transaction success.
14. Viết ADR về topology, routing ownership, DNS authority, security và connectivity cost.

**Gợi ý tự đánh giá:** Bài làm đạt khi flow được inventory, IP không overlap hoặc có biện pháp chuyển tiếp an toàn, DNS có authority/forwarding graph rõ, routing hai chiều và segmented, redundancy độc lập được kiểm chứng, và end-to-end probe chứng minh ứng dụng thực sự dùng được đường kết nối.

## 19. Checklist trước production

- [ ] Business flow, owner, criticality và data classification đã được lập inventory.
- [ ] Latency, throughput, packet rate, availability và recovery requirement được lượng hóa.
- [ ] IPAM bao phủ on-prem, cloud, Kubernetes, partner và future allocation.
- [ ] CIDR overlap được loại bỏ hoặc có NAT/proxy design được tài liệu hóa.
- [ ] VPN/dedicated/SD-WAN choice có cost, encryption và failure analysis.
- [ ] Transit topology có route domain và attachment ownership rõ.
- [ ] BGP/static route có prefix filter, policy và audit.
- [ ] Route propagation không mở unintended path giữa environment.
- [ ] Asymmetric routing, NAT state, MTU/MSS đã được kiểm thử.
- [ ] DNS zones/resolvers/conditional forward có owner và không loop.
- [ ] Private DNS visibility và resolver authorization được kiểm chứng.
- [ ] TTL, negative cache, runtime cache và long-lived connection được xem xét.
- [ ] TLS, certificate, workload identity và access policy được bảo vệ.
- [ ] Firewall/SG/NACL/NetworkPolicy chỉ mở flow cần thiết.
- [ ] Redundant link/site/edge/provider có failure domain độc lập phù hợp.
- [ ] Failover capacity đáp ứng critical traffic và recovery workload.
- [ ] DNS/routing failover và failback được diễn tập.
- [ ] Flow logs, resolver logs, BGP/tunnel telemetry và synthetic probes có owner.
- [ ] Runbook, RACI, escalation và change rollback được kiểm tra.
- [ ] Data residency, egress cost, connectivity cost và operational overhead được review.

## 20. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi review hybrid/multi-cloud connectivity |
| --- | --- |
| **Operational Excellence** | IPAM, route/DNS ownership, change process, telemetry, runbook và escalation có thể vận hành xuyên team/provider không? |
| **Security** | Network được segment theo trust domain; private path vẫn có TLS/identity; route/DNS changes có audit và least privilege không? |
| **Reliability** | Có diverse connectivity, redundant resolver, failover/failback, capacity và end-to-end recovery test không? |
| **Performance Efficiency** | Placement, routing, DNS caching và path selection có đáp ứng latency/throughput mà không tạo hairpin không cần thiết? |
| **Cost Optimization** | VPN, dedicated circuit, transit attachment, egress, NAT và inspection cost có được gắn workload/flow owner không? |
| **Sustainability** | Có giảm truyền dữ liệu dư thừa, route hairpin và cross-region processing trong khi vẫn giữ resilience và residency không? |

**Kết luận:** Kết nối hybrid và multi-cloud là một hệ thống gồm IP plan, underlay/overlay, routing, DNS, segmentation, identity, failover và operations. Thiết kế tốt bắt đầu từ flow nghiệp vụ và trust boundary; dùng IPAM để tránh overlap; chọn VPN, dedicated connectivity, SD-WAN và transit theo traffic/SLO; kiểm soát route propagation và DNS forwarding; đồng thời thử nghiệm cả đường đi, đường về, cache và capacity khi failover. Một tunnel up hoặc record DNS đúng chưa đủ chứng minh ứng dụng hoạt động. Hãy dùng synthetic probe end-to-end, audit thay đổi và diễn tập recovery để bảo đảm kết nối an toàn, ổn định, có thể mở rộng và vận hành được theo tinh thần Well-Architected.
