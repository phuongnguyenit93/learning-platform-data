# Khảo sát hệ thống và lựa chọn chiến lược di chuyển

Di chuyển hệ thống lên AWS là một quyết định về kiến trúc, vận hành, chi phí và kinh doanh. Trước khi chọn Amazon EC2, Amazon RDS hay một dịch vụ managed khác, tổ chức cần hiểu mình đang vận hành những ứng dụng nào, ứng dụng phụ thuộc vào đâu, ai đang sử dụng chúng, dữ liệu nằm ở đâu, tải thực tế ra sao và điều gì sẽ xảy ra nếu cutover thất bại.

Khảo sát hệ thống (migration assessment) biến dữ liệu rời rạc về server, database, network, phần mềm và quy trình vận hành thành một danh mục workload có thể ra quyết định. Kết quả không chỉ là danh sách máy chủ. Nó phải trả lời: workload nào nên chuyển, workload nào nên giữ hoặc retire, chọn chiến lược nào trong 7 Rs, target architecture phù hợp là gì, chi phí và rủi ro ra sao, và nên chuyển theo wave nào.

Bài thuộc chương **Di chuyển và hạ tầng hybrid**, mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung kết nối AWS Application Discovery Service, AWS Migration Hub, AWS Transform, Migration Evaluator, AWS Application Migration Service (MGN), AWS Database Migration Service (DMS), AWS DataSync, AWS Snow Family, AWS Direct Connect, AWS Site-to-Site VPN và các dịch vụ đích trên AWS.

> **Nguyên tắc quan trọng:** Không chọn công cụ migration trước khi hiểu workload. Một server có CPU thấp vẫn có thể là thành phần quan trọng của hệ thống thanh toán; một database nhỏ vẫn có thể có hàng chục consumer; một ứng dụng ít được dùng có thể được retire thay vì tốn tiền migrate.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích mục đích và phạm vi của migration assessment.
2. Xây dựng inventory cho application, server, database, storage, network, license và ownership.
3. Phân biệt discovery dữ liệu tĩnh với utilization metrics và dependency mapping.
4. Sử dụng AWS Application Discovery Service, Migration Hub và AWS Transform đúng vai trò.
5. Xác định business drivers, technical constraints, compliance và migration readiness.
6. Đánh giá application dependencies và gom workload thành dependency groups.
7. Đọc CPU, memory, disk IOPS, throughput và network utilization để right-size target.
8. Ước tính TCO, migration cost, operational cost và business case.
9. Phân biệt bảy chiến lược migration: retire, retain, rehost, relocate, repurchase, replatform và refactor.
10. Chọn target AWS services cho compute, database, storage, network và integration.
11. Phân biệt AWS Application Migration Service (MGN) với AWS Elastic Disaster Recovery (DRS).
12. Chọn DMS, DataSync, Transfer Family hoặc Snow Family cho data movement.
13. Xây dựng migration waves, cutover plan và rollback plan.
14. Xác định landing zone, security, network và operational readiness.
15. Thiết kế proof of concept (PoC), pilot và tiêu chí nghiệm thu.
16. Xây dựng deliverables và governance cho migration assessment.

## 2. Migration assessment bắt đầu từ mục tiêu kinh doanh

### 2.1. Xác định business drivers

Không nên bắt đầu bằng câu hỏi "server nào chuyển trước?". Hãy bắt đầu từ lý do tổ chức cần thay đổi:

- **Data center exit:** hết hợp đồng thuê, hết vòng đời phần cứng hoặc cần đóng data center.
- **Cost optimization:** giảm chi phí facility, license, vận hành và bảo trì hạ tầng.
- **Resilience:** tăng availability, backup, disaster recovery và khả năng phục hồi.
- **Agility:** rút ngắn thời gian provisioning và release ứng dụng.
- **Modernization:** chuyển sang managed database, containers, serverless hoặc event-driven architecture.
- **Global expansion:** triển khai ứng dụng gần người dùng ở nhiều Region.
- **Compliance:** đáp ứng data residency, audit, encryption, retention và regulatory requirements.
- **M&A / divestiture:** hợp nhất hoặc tách hệ thống sau sáp nhập, mua bán doanh nghiệp.
- **Technology refresh:** thay OS, database engine, middleware hoặc runtime đã hết hỗ trợ.

Mỗi driver cần được chuyển thành outcome đo được. Ví dụ: đóng data center trước ngày hết hợp đồng; giảm 25% chi phí hạ tầng trong 12 tháng; đạt RTO 2 giờ; hoặc giảm thời gian cấp môi trường từ 10 ngày xuống 30 phút.

### 2.2. Xác định scope và boundary

Scope cần xác định rõ:

| Phạm vi | Câu hỏi cần trả lời |
|---|---|
| Organization | Business units, subsidiaries, legal entities nào tham gia? |
| Locations | Data centers, colocation, branch offices, cloud accounts nào nằm trong scope? |
| Applications | Danh sách application/service nào cần assessment? |
| Infrastructure | Physical servers, VMs, containers, appliances và network devices nào liên quan? |
| Data | Database, file shares, object storage, backup và archive nào cần chuyển? |
| Environments | Production, staging, development, DR và sandbox có được tính? |
| Time | Deadline, maintenance window, blackout periods và contract expiry là gì? |
| Exclusions | Hệ thống nào không được chuyển và vì sao? |

Định nghĩa rõ workload boundary để tránh bỏ sót các thành phần bên ngoài data center như SaaS, DNS provider, identity provider, payment gateway, partner API, backup vault và license server.

### 2.3. Phân loại mức độ quan trọng

Dùng business criticality để ưu tiên khảo sát và thiết kế:

| Tier | Đặc điểm | Ví dụ minh họa |
|---|---|---|
| Tier 0 / Mission critical | Dừng dịch vụ gây ảnh hưởng lớn tới an toàn, doanh thu hoặc toàn doanh nghiệp | Payment core, identity, ERP production |
| Tier 1 / Critical | Ảnh hưởng trực tiếp tới hoạt động cốt lõi | Order management, customer portal |
| Tier 2 / Important | Có thể dùng workaround trong thời gian ngắn | Reporting, internal workflow |
| Tier 3 / Non-critical | Có thể trì hoãn hoặc retire | Legacy test server, temporary utility |

Không suy ra criticality từ CPU hoặc số người đăng nhập. Owner nghiệp vụ phải xác nhận impact, RTO/RPO, peak season, support hours và mức downtime chấp nhận được.

## 3. Thu thập inventory và dữ liệu discovery

### 3.1. Xây dựng application portfolio

Mỗi application nên có một record định danh duy nhất và các thông tin tối thiểu:

| Nhóm dữ liệu | Trường cần thu thập |
|---|---|
| Identity | Application ID, tên, mô tả, business unit, owner, technical contact |
| Business | Criticality, users, business process, revenue impact, SLA/SLO |
| Lifecycle | Vendor, version, support end date, license, contract renewal |
| Architecture | Runtime, OS, middleware, database, protocol, deployment model |
| Infrastructure | Server IDs, vCPU, RAM, disks, storage, hypervisor, network interfaces |
| Performance | CPU/memory percentile, IOPS, throughput, latency, network utilization |
| Dependencies | Upstream/downstream applications, database, DNS, AD, queues, external APIs |
| Security | Data classification, encryption, identity, vulnerabilities, access patterns |
| Operations | Monitoring, backup, patching, deployment, incident and change process |
| Migration | Candidate 7R, target service, complexity, blockers, wave, downtime window |

Không dùng hostname làm application ID. Hostname có thể đổi, trùng giữa môi trường hoặc được reuse. Dùng stable identifier và mapping giữa CMDB, discovery tool, cloud resource tags và migration tracker.

### 3.2. Server và infrastructure inventory

Thu thập cả static configuration và time-series utilization:

- CPU architecture, sockets, cores, vCPU và hypervisor allocation.
- Memory installed, used, available, swap/pagefile và memory pressure.
- Disk count, capacity, filesystem, free space, IOPS, read/write throughput và latency.
- Network interface, IP, VLAN/subnet, route, firewall rules, bandwidth và TCP connections.
- OS distribution/version, kernel, patch level, boot mode và end-of-support date.
- Hypervisor, VM cluster, host affinity, HA/DR configuration và licensing.
- Hardware appliance, HSM, GPU, dongle, serial device hoặc dependency đặc thù.

Thu thập peak và percentile, không chỉ average. CPU average 10% có thể che giấu peak 95% trong batch window. Memory pressure, disk latency và network bursts cũng có thể quyết định EC2 instance family hoặc storage class.

### 3.3. Database inventory

Với mỗi database, ghi lại:

- Engine, edition, version, patch level và license model.
- Database size, growth rate, table count, index size, LOB, partition và schema.
- Transaction rate, peak connections, read/write ratio, query latency.
- Backup method, log retention, recovery model và replication topology.
- Extensions, stored procedures, triggers, jobs, linked servers và external integrations.
- Character set, collation, time zone, data types và compatibility requirements.
- RPO/RTO, downtime allowance và data consistency requirements.

Đặc biệt lưu ý database migration không chỉ là copy rows. Hệ thống có thể phụ thuộc stored procedures, jobs, sequences, extensions, secondary indexes, foreign keys, grants và application connection strings. AWS DMS có thể migrate data và hỗ trợ một số schema operations, nhưng không tự động chuyển mọi object/permission trong mọi engine path.

### 3.4. Application dependency mapping

Một application có thể phụ thuộc vào:

- Identity: Active Directory, LDAP, IAM Identity Center, SAML/OIDC provider.
- Name resolution: DNS, private hosted zones, service discovery.
- Data: RDBMS, NoSQL, file shares, object storage, cache.
- Integration: MQ, Kafka, SMTP, FTP/SFTP, REST/SOAP APIs, payment gateways.
- Infrastructure: NTP, PKI/CA, HSM, license server, proxy, firewall.
- Operations: monitoring, logging, backup, vulnerability scanner, deployment agent.

Dependency map nên ghi cả hướng gọi, protocol/port, frequency, criticality và owner. Một TCP connection quan sát được không tự động chứng minh dependency nghiệp vụ; cần đối chiếu với application owner, configuration, logs và tracing.

### 3.5. Phân biệt static inventory và utilization data

| Loại dữ liệu | Ví dụ | Dùng để |
|---|---|---|
| Static configuration | 8 vCPU, 32 GiB RAM, 2 TB disk, OS version | Xác định compatibility và baseline capacity |
| Utilization time series | CPU p95, memory peak, IOPS, throughput | Right-sizing và performance planning |
| Network connections | Source/destination IP, port, process, timestamp | Dependency discovery và network design |
| Business metadata | Owner, criticality, SLA, license, cost center | Chọn 7R, ưu tiên và governance |
| Application behavior | Request rate, latency, error rate, transaction volume | Thiết kế target architecture và acceptance criteria |

Nên thu thập utilization trong một chu kỳ đại diện, thường tối thiểu 2–4 tuần; workload có seasonal peak hoặc quarter-end cần thời gian dài hơn. Nếu chỉ lấy snapshot trong ngày yên tĩnh, right-sizing có thể thiếu capacity khi vào peak.



## 4. Công cụ discovery và assessment của AWS

### 4.1. AWS Application Discovery Service

AWS Application Discovery Service thu thập dữ liệu cấu hình và utilization của server/database on-premises để hỗ trợ migration planning. Dữ liệu discovery được tích hợp với AWS Migration Hub và AWS DMS Fleet Advisor.

Có hai phương thức chính:

| Phương thức | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Agentless Collector | Collector triển khai trong môi trường VMware/vCenter, thu thập server profile, utilization và TCP network connections từ hypervisor | Muốn discovery nhiều VMware VMs mà không cài agent trên từng VM |
| Discovery Agent | Agent cài trên từng physical/virtual server, thu thập server profile, utilization, processes và network connections | Cần dữ liệu chi tiết từ OS/process và server không nằm trong VMware vCenter được hỗ trợ |

Agentless Collector phù hợp để bắt đầu inventory VMware nhanh. Discovery Agent cho dữ liệu chi tiết hơn về process và connection. Có thể kết hợp nhiều nguồn như CMDB export, vCenter inventory, RVTools và dữ liệu thu thập độc lập; phải chuẩn hóa identity trước khi merge để tránh duplicate servers.

### 4.2. AWS Migration Hub

AWS Migration Hub cung cấp nơi theo dõi migration status tập trung và gom thông tin discovery/application groups từ các công cụ tích hợp. Trước khi discovery, cần đặt Migration Hub home Region. Dữ liệu discovery và tracking của Migration Hub được lưu trong home Region đó.

Migration Hub giúp:

- Xem inventory đã discover.
- Group servers thành applications.
- Quan sát network connections và application dependencies từ discovery data.
- Xem EC2 recommendations/target suggestions khi nguồn dữ liệu hỗ trợ.
- Theo dõi migration status qua các công cụ tích hợp.

Migration Hub là nơi tracking/orchestration visibility; nó không thay thế inventory owner, business case hoặc runbook. Cần có migration tracker với owner, wave, risk, target, status và cutover date được thống nhất.

### 4.3. AWS Transform

AWS Transform là workbench dùng agentic AI để hỗ trợ migration và modernization. Đối với server migration, AWS Transform có thể hỗ trợ discovery, application grouping, dependency mapping, migration wave planning, landing zone creation, network migration và server rehost từ các môi trường như VMware, Hyper-V và physical/bare-metal servers được hỗ trợ.

AWS Transform assessments có thể phân tích inventory để tạo business case/TCO, đánh giá feasibility và business value, gợi ý target AWS services, licensing options và các kịch bản chi phí. Người dùng có thể điều chỉnh giả định, bổ sung inventory và so sánh what-if scenarios.

Một số khả năng hữu ích:

- Đề xuất 7R cho server/application dựa trên OS, utilization và workload signals.
- Gợi ý target service và giải thích/độ tin cậy của recommendation.
- Nhóm ứng dụng và sắp xếp dependency-aware migration waves.
- Hỗ trợ chuyển đổi network configuration sang VPC design.
- Tạo deliverables cho assessment và migration planning.

AI recommendation là đầu vào để chuyên gia review, không phải quyết định tự động. Kiểm tra inventory completeness, confidence score, business context, licensing, compliance và dependency thực tế trước khi phê duyệt.

### 4.4. Migration Evaluator và các nguồn dữ liệu bổ sung

Migration Evaluator hỗ trợ xây dựng business case/TCO từ server inventory và utilization data, so sánh chi phí on-premises với AWS. Tổ chức có thể bổ sung dữ liệu từ CMDB, vCenter, Hyper-V, monitoring tools và license records.

Có thể sử dụng:

- CMDB/asset management export.
- VMware vCenter, RVTools, Hyper-V inventory.
- AWS Application Discovery Service.
- AWS Transform assessments.
- AWS DMS Fleet Advisor/database metadata.
- Performance monitoring/APM/logging systems.
- Network flow logs, firewall logs và NetFlow.
- Procurement, facility, software licensing và support invoices.

Không coi một công cụ discovery là nguồn chân lý duy nhất. Đối chiếu server count, CPU/memory, application owner, network connections và database inventory với các hệ thống nguồn khác.

### 4.5. Quy trình discovery có kiểm soát

1. Chốt Migration Hub home Region và account/permissions.
2. Xác định data owners, security approval và retention.
3. Chọn Agentless Collector, Discovery Agent hoặc import inventory theo source environment.
4. Thu thập static configuration và utilization trong chu kỳ đại diện.
5. Thu thập network connections và running processes khi cần dependency mapping.
6. Chuẩn hóa hostnames, IPs, server IDs, application IDs và timestamps.
7. Group servers thành application portfolio.
8. Phỏng vấn business/application owners để xác nhận dependencies.
9. Đánh dấu missing data, stale records, unknown owners và unsupported systems.
10. Chốt discovery baseline có ngày snapshot và data confidence.

Discovery agent/collector có quyền đọc thông tin nhạy cảm về hệ thống và network. Triển khai theo least privilege, change process và security review. Xác định dữ liệu nào được gửi tới AWS, ai truy cập được, home Region và retention policy trước khi thu thập.

## 5. Đánh giá khả năng di chuyển và mức độ sẵn sàng

### 5.1. Technical readiness

Đánh giá từng application theo các nhóm:

| Nhóm | Câu hỏi đánh giá |
|---|---|
| OS/runtime | OS, kernel, runtime và middleware có được target hỗ trợ không? |
| Compute | CPU architecture, memory, GPU, special hardware hoặc license có tương thích? |
| Storage | Block/file/object, IOPS, throughput, latency và shared filesystem có đáp ứng? |
| Database | Engine/version, extensions, schema, transaction rate và CDC có hỗ trợ? |
| Network | IP, CIDR, routing, firewall, DNS, latency và bandwidth có phù hợp? |
| Identity | AD/LDAP, Kerberos, SAML/OIDC, service accounts và secrets sẽ hoạt động ra sao? |
| Integration | External APIs, MQ, SMTP, SFTP, partner allowlists và certificates có được cập nhật? |
| Security | Data classification, encryption, keys, vulnerability management và audit có đáp ứng? |
| Operations | Monitoring, patching, backup, deployment, incident response và on-call có sẵn sàng? |
| Licensing | BYOL, license-included, core restrictions, mobility và vendor support có cho phép? |

Đánh giá compatibility không chỉ là kiểm tra EC2 có chạy OS đó không. Một ứng dụng có thể phụ thuộc kernel driver, USB/HSM, multicast, MAC address, static IP, license binding hoặc appliance-specific behavior mà target cloud không hỗ trợ.

### 5.2. Business readiness

Xác nhận:

- Business sponsor và application owner đã ký xác nhận scope.
- Business criticality, RTO/RPO và downtime window đã được duyệt.
- End users, partner và vendor đã được thông báo.
- Compliance/data residency đã được review.
- Contract, license, support và vendor certification đã xác minh.
- Kế hoạch đào tạo, operating model và service ownership đã có.
- Budget, funding và chargeback/showback được phê duyệt.
- Kế hoạch truyền thông, change approval và hypercare đã xác định.

### 5.3. Migration readiness scorecard

Có thể dùng thang điểm 0–3:

| Điểm | Ý nghĩa |
|---:|---|
| 0 | Chưa biết/chưa có dữ liệu |
| 1 | Có dữ liệu nhưng chưa xác minh hoặc còn blocker lớn |
| 2 | Đã xác minh, có phương án xử lý và owner |
| 3 | Đã thử nghiệm/đạt acceptance criteria |

Chấm riêng các nhóm inventory, dependency, target architecture, network, security, data migration, licensing, operations, testing và cutover. Không lấy điểm trung bình để che giấu blocker critical. Ví dụ network readiness = 3 nhưng license legality = 0 vẫn là no-go.

### 5.4. Phân loại complexity và risk

Đánh giá complexity theo số lượng dependencies, data volume, downtime tolerance, database heterogeneity, OS support, external integrations, license constraints và mức độ tùy biến. Phân loại Low/Medium/High/Very High kèm evidence.

Rủi ro cần có owner, likelihood, impact, mitigation và due date. Các risk thường gặp:

- Application owner không rõ hoặc vendor không còn hỗ trợ.
- Dependency map không đầy đủ.
- OS/database end-of-support.
- Data volume hoặc write rate vượt bandwidth/cutover window.
- License không transferable hoặc tính theo physical cores.
- IP/DNS change ảnh hưởng partner allowlists.
- Encryption key, certificate hoặc secrets không có owner.
- Target account/Region thiếu quota hoặc EC2 capacity.
- Backup/restore và rollback chưa test.
- Không có team vận hành target platform.

## 6. Business case và Total Cost of Ownership (TCO)

### 6.1. Chi phí on-premises

Không chỉ cộng giá server. TCO on-premises thường gồm:

- Server, storage, network hardware và refresh cycle.
- Data center rack/space, power, cooling và physical security.
- Hypervisor, OS, database, middleware và application licenses.
- Maintenance, support contracts, spare parts và warranty.
- Backup, DR site, replication link và tape/archive.
- Network circuits, firewall, load balancer và security appliances.
- IT operations labor, patching, monitoring và incident management.
- Migration project, downtime, vendor consulting và decommission.

Phân bổ chi phí theo application/service thay vì chia đều theo số server. Shared storage, network, database cluster và license pool có thể làm allocation phức tạp.

### 6.2. Chi phí AWS sau migration

Ước tính theo target architecture và usage profile:

- EC2 instance hours, Savings Plans/Reserved Instances/Spot nếu phù hợp.
- EBS volumes, snapshots, provisioned IOPS và throughput.
- S3 storage class, requests, retrieval và data transfer.
- RDS/Aurora/other database compute, storage, I/O, backup và Multi-AZ.
- ECS/EKS/Lambda và supporting services.
- Load balancers, NAT Gateway, Transit Gateway, Route 53 và Direct Connect.
- CloudWatch metrics/logs, CloudTrail, Config, Security Hub và GuardDuty.
- KMS, Secrets Manager, Systems Manager và backup services.
- Data transfer out, inter-AZ/inter-Region và internet egress.
- Support plan, marketplace software, licensing và managed services.

Ước tính theo nhiều kịch bản: conservative, expected và growth. Đừng dùng peak capacity cho mọi giờ nếu có thể scale; cũng đừng dùng average thấp nhất làm baseline nếu cần đáp ứng peak.

### 6.3. Chi phí migration và chuyển đổi

Ngoài chi phí vận hành AWS, cần dự trù:

- Discovery tools/collector deployment và assessment effort.
- Replication/transfer services, temporary storage và data transfer.
- Migration tooling, conversion, refactoring và testing.
- Parallel run: on-premises và AWS cùng hoạt động.
- Cutover weekend/overtime, vendor support và business downtime.
- Training, operating model changes và new skills.
- Data reconciliation, audit evidence và compliance sign-off.
- Decommission, secure wipe, contract termination và facility exit.
- Contingency cho rollback, rework và migration wave delay.

### 6.4. So sánh TCO và business value

Một mô hình đơn giản:

\[
TCO_{3y} = C_{migration} + \sum_{y=1}^{3}(C_{run,y} + C_{license,y} + C_{support,y})
\]

Net benefit:

\[
Benefit_{3y} = TCO_{on\text{-}prem,3y} - TCO_{AWS,3y}
\]

Có thể tính payback period:

\[
Payback = \frac{C_{one\text{-}time\ migration}}{Annual\ net\ savings}
\]

Các công thức chỉ là khung mô hình. Cần tính discount rate, price changes, reserved capacity, utilization, growth, currency, tax, downtime risk và residual value. Một migration có TCO cao hơn vẫn có thể hợp lý nếu cải thiện resilience, time-to-market, compliance hoặc giảm rủi ro data center exit.

### 6.5. Right-sizing

Right-sizing dựa trên utilization và application behavior:

- EC2 instance family chọn theo CPU, memory, network, storage và accelerator needs.
- Compute Optimized phù hợp CPU-bound; Memory Optimized cho in-memory/cache/database; Storage Optimized cho IOPS/throughput cao; General Purpose cho workload cân bằng.
- Graviton/ARM có thể giảm cost/performance tốt nhưng cần kiểm tra OS, runtime, native libraries và vendor support.
- Managed database giảm vận hành nhưng có thể tăng chi phí license, I/O hoặc Multi-AZ.
- Auto Scaling, scheduled scaling và serverless phù hợp workload biến động.
- EBS volume type/provisioned IOPS chọn theo measured latency/throughput, không theo dung lượng đơn thuần.

Đừng right-size chỉ từ một snapshot. Dùng p50/p95/p99, peak windows, memory pressure, disk latency và concurrency. Giữ headroom theo SLA và khả năng scale thực tế.



## 7. Bảy chiến lược migration (7 Rs)

7 Rs là khung phân loại quyết định cho từng application/workload. Một application có thể dùng nhiều chiến lược cho các thành phần khác nhau; không cần ép toàn bộ portfolio vào một cách tiếp cận.

| Chiến lược | Ý nghĩa | Khi phù hợp | Ví dụ |
|---|---|---|---|
| **Retire** | Ngừng vận hành ứng dụng không còn giá trị | Không còn business owner/user; chức năng trùng lặp; chi phí/rủi ro giữ lại lớn hơn lợi ích | Tắt legacy reporting server đã được thay thế |
| **Retain** | Giữ lại tại nơi hiện tại hoặc hoãn migration | Có ràng buộc compliance, latency, hardware, contract hoặc chưa sẵn sàng | Giữ HSM/OT workload tại site |
| **Rehost** | Chuyển nguyên trạng workload lên cloud (lift and shift) | Cần rời data center nhanh, ít thay đổi ứng dụng, modernization để sau | VM chuyển thành EC2 |
| **Relocate** | Di chuyển workload/stack sang cloud platform tương thích với thay đổi kiến trúc tối thiểu | Muốn giữ môi trường ảo hóa/stack gần như hiện tại | Di chuyển VMware stack sang dịch vụ VMware tương thích trên cloud, khi mô hình đích còn được hỗ trợ |
| **Repurchase** | Thay ứng dụng hiện tại bằng sản phẩm/SaaS khác | SaaS đáp ứng business capabilities và giảm gánh nặng tự vận hành | Thay CRM tự host bằng CRM SaaS |
| **Replatform** | Chuyển workload và thực hiện tối ưu có giới hạn | Có thể dùng managed services mà không viết lại toàn bộ ứng dụng | SQL Server trên VM chuyển sang Amazon RDS for SQL Server |
| **Refactor / Re-architect** | Thiết kế lại ứng dụng để tận dụng cloud-native capabilities | Cần agility, scale, resilience hoặc thay đổi product architecture lớn | Monolith chuyển thành microservices trên ECS/EKS |

### 7.1. Retire

Retire thường là cách tiết kiệm nhất nếu application không còn được sử dụng. Trước khi tắt, cần:

- Xác nhận business owner, data owner và legal retention.
- Kiểm tra integrations, scheduled jobs, reports và downstream consumers.
- Archive dữ liệu theo retention/compliance.
- Thu hồi credentials, DNS, firewall rules, certificates và license.
- Decommission server/storage/network và cập nhật CMDB.
- Giữ bằng chứng phê duyệt và thời điểm tắt.

Không retire chỉ vì CPU thấp hoặc server không có interactive logins. Batch job, API backend và disaster recovery systems có thể ít hoạt động nhưng vẫn critical.

### 7.2. Retain

Retain không có nghĩa là bỏ quên workload. Ghi lại lý do giữ, owner, review date và điều kiện để xem xét lại. Ví dụ: data residency chưa cho phép chuyển, ứng dụng phụ thuộc hardware chưa có cloud equivalent, hoặc vendor contract còn thời hạn. Có thể thiết kế hybrid connectivity để workload retained vẫn kết nối an toàn với AWS.

### 7.3. Rehost

Rehost phù hợp khi cần chuyển nhanh và hạn chế thay đổi application. AWS Application Migration Service (MGN) thực hiện block-level replication để chuyển source servers sang EC2. Rehost thường giảm thời gian thay đổi code nhưng không tự giải quyết technical debt, unsupported OS, license restrictions, poor architecture hoặc overprovisioning.

### 7.4. Relocate

Relocate thường áp dụng cho một stack/virtualization environment có khả năng chuyển sang nền tảng cloud tương thích với ít thay đổi. Xác minh kỹ điều kiện hỗ trợ, hợp đồng, licensing và availability của dịch vụ đích tại thời điểm lập kế hoạch. Không nhầm relocate với rehost: relocate giữ nguyên nhiều đặc điểm của platform/stack, còn rehost chuyển từng server thành cloud instance.

### 7.5. Repurchase

Repurchase thay hệ thống tự quản bằng SaaS hoặc commercial product. Đánh giá data export/import, API integration, identity federation, customization, data residency, exit strategy, SLA, vendor lock-in và subscription cost. Đừng so sánh chỉ dựa trên license fee; tính cả integration, migration, training và process redesign.

### 7.6. Replatform

Replatform chuyển sang dịch vụ đích được quản lý nhiều hơn nhưng giữ phần lớn business logic. Ví dụ:

- Self-managed MySQL trên EC2 sang Amazon RDS for MySQL/Aurora MySQL.
- File server sang Amazon FSx hoặc Amazon EFS.
- Application runtime trên VM sang ECS/Fargate với thay đổi đóng gói vừa phải.
- Object storage nội bộ sang Amazon S3.
- Oracle database sang RDS for Oracle nếu edition/feature/license phù hợp.

Replatform có thể giảm operational burden nhưng cần kiểm tra feature compatibility, extensions, performance, maintenance window và operational model.

### 7.7. Refactor / Re-architect

Refactor phù hợp khi lợi ích dài hạn đủ lớn để bù chi phí, thời gian và rủi ro thay đổi. Có thể gồm:

- Tách monolith thành services hoặc modular architecture.
- Thay synchronous coupling bằng event-driven patterns.
- Chuyển batch processing sang managed queue/workflow.
- Chuyển stateful components sang managed databases/cache.
- Containerize ứng dụng hoặc chuyển sang serverless.
- Thiết kế stateless, horizontal scaling và multi-AZ resilience.

Tránh vừa migration vừa thay đổi toàn bộ business behavior trong cùng một cutover nếu không có test coverage và rollback strategy đủ mạnh. Nhiều chương trình chọn rehost/replatform trước rồi modernize theo roadmap sau.

## 8. Quy trình lựa chọn chiến lược cho từng workload

### 8.1. Decision sequence

1. **Còn business value không?** Nếu không, đánh giá Retire.
2. **Có thể chuyển trong phạm vi pháp lý, license và kỹ thuật không?** Nếu chưa, Retain hoặc giải quyết blocker trước.
3. **Có sản phẩm SaaS thay thế tốt hơn không?** Nếu có, đánh giá Repurchase.
4. **Có cần giữ nguyên platform/virtualization stack không?** Nếu có, đánh giá Relocate.
5. **Cần chuyển nhanh, thay đổi ít không?** Đánh giá Rehost.
6. **Có target managed service phù hợp với thay đổi giới hạn không?** Đánh giá Replatform.
7. **Business outcome đòi hỏi kiến trúc mới không?** Đánh giá Refactor.

Decision sequence chỉ giúp tạo shortlist. Cần so sánh 2–3 phương án khả thi dựa trên cost, time, risk, downtime, skills và future operating model.

### 8.2. Ma trận lựa chọn theo driver

| Driver chính | Chiến lược thường được cân nhắc | Câu hỏi kiểm chứng |
|---|---|---|
| Data center exit có deadline gần | Rehost, Relocate, Retire | Có thể chuyển nguyên trạng và có đủ capacity không? |
| Giảm operational overhead | Replatform, Repurchase | Managed service/SaaS có đáp ứng feature và compliance không? |
| Tăng tốc feature delivery | Refactor, Replatform | Team có kỹ năng và test coverage để thay đổi architecture không? |
| Không thể thay đổi ngay | Retain, Rehost | Có thể giữ hybrid trong giai đoạn chuyển tiếp không? |
| Hết vòng đời application | Retire, Repurchase | Có consumer nào còn phụ thuộc không? |
| Database modernization | Replatform, Refactor | Có thể đổi engine và convert schema/code không? |
| VMware stack migration | Relocate hoặc Rehost | Licensing, service availability và portability ra sao? |

### 8.3. Ví dụ phân loại một portfolio

| Workload | Hiện trạng | Candidate 7R | Target/next action |
|---|---|---|---|
| Legacy report portal | Ít user, chức năng trùng BI SaaS | Retire / Repurchase | Xác nhận consumer và archive, chuyển report users sang SaaS |
| Internal Java monolith | Linux VM, Oracle DB, dependencies rõ | Rehost trước, Replatform sau | EC2 trước; đánh giá RDS/containers ở wave modernization |
| CRM | Custom app, vendor SaaS có feature tương đương | Repurchase | PoC integration, data export và identity federation |
| File share | SMB, dung lượng lớn, latency nội bộ quan trọng | Replatform / Retain | So sánh FSx for Windows File Server với giữ local cache |
| ERP core | License phức tạp, vendor certified stack | Retain / Rehost / Relocate | Vendor assessment, license review và PoC |
| Stateless API | Traffic burst, CI/CD sẵn có | Refactor / Replatform | ECS/Fargate hoặc Lambda sau workload profiling |

Ghi candidate strategy, final decision, rationale, approver và review date. Một recommendation từ tool không thay thế quyết định của application owner/architecture board.

## 9. Chọn AWS target services theo workload

### 9.1. Compute và application hosting

| Nhu cầu | AWS target có thể cân nhắc | Điểm cần đánh giá |
|---|---|---|
| Giữ OS/application gần nguyên trạng | Amazon EC2 | OS/AMI support, instance family, license, EBS và patching |
| Container orchestration | Amazon ECS hoặc Amazon EKS | Container readiness, state, networking, registry và platform operations |
| Container không muốn quản lý server | ECS on AWS Fargate | Startup time, CPU/memory sizing, networking và pricing |
| Event-driven short-lived functions | AWS Lambda | Runtime compatibility, execution duration, state, concurrency và cold starts |
| Java/web app cần platform quản lý | AWS Elastic Beanstalk hoặc App Runner theo use case | Runtime support, deployment model, network access và operational needs |
| Batch/HPC | AWS Batch hoặc EC2-based scheduler | Queue, placement, compute environment và data locality |
| GPU/ML | EC2 accelerated instances hoặc managed AI services | Driver, framework, GPU memory, quota và cost |

Không chọn container/serverless chỉ vì đó là cloud-native. Nếu ứng dụng phụ thuộc kernel module, local persistent state hoặc license binding, rehost có thể là bước đầu an toàn hơn.

### 9.2. Database và data stores

| Source/requirement | AWS target có thể cân nhắc | Câu hỏi quan trọng |
|---|---|---|
| MySQL/PostgreSQL self-managed | Amazon RDS hoặc Aurora | Extensions, replication, storage, IOPS, HA và version compatibility |
| SQL Server | Amazon RDS for SQL Server hoặc EC2 | Edition, feature, Windows/license và SQL Agent dependencies |
| Oracle | RDS for Oracle hoặc EC2 | Options/packs, RAC, Data Guard, BYOL và vendor certification |
| Key-value/document | DynamoDB hoặc DocumentDB | Data model, query pattern, consistency và application changes |
| Cache | ElastiCache for Redis/Valkey hoặc Memcached | Persistence, clustering, failover và client compatibility |
| Data warehouse | Amazon Redshift hoặc analytics services | Schema, ETL, concurrency, data volume và workload pattern |
| Database cần giữ engine/feature đặc thù | EC2 self-managed | DBA operations, backup, patching, HA và license |

Cùng tên engine không có nghĩa là tương thích hoàn toàn. RDS/Aurora có giới hạn về OS access, superuser privileges, extensions, file access và engine features. Cần đọc engine-specific feature matrix và chạy schema assessment/PoC.

### 9.3. File, block và object storage

| Data pattern | AWS target | Điều cần đo |
|---|---|---|
| Block storage cho EC2 | Amazon EBS | Capacity, IOPS, throughput, latency, snapshots |
| Shared Linux POSIX file system | Amazon EFS | NFS semantics, throughput mode, access points và lifecycle |
| Shared Windows SMB | Amazon FSx for Windows File Server | AD integration, SMB version, ACLs, throughput và HA |
| High-performance parallel file system | Amazon FSx for Lustre | HPC/AI access pattern và data repository integration |
| Object storage | Amazon S3 | Object count, size, versioning, metadata, retention và request patterns |
| Hybrid file access | AWS Storage Gateway | Cache, bandwidth, local application semantics và gateway availability |

Đừng chuyển file share sang S3 chỉ vì storage rẻ hơn. S3 object semantics khác POSIX/SMB: locking, rename, partial update và file handle behavior có thể khác hoàn toàn.

### 9.4. Network, identity và integration

- **Amazon VPC:** CIDR, subnet, route, security groups, NACL, endpoints.
- **AWS Transit Gateway:** kết nối nhiều VPC và on-premises networks theo mô hình hub-and-spoke.
- **AWS Direct Connect:** dedicated connectivity với bandwidth/latency characteristics phù hợp.
- **AWS Site-to-Site VPN:** IPsec encrypted tunnels, phù hợp thiết lập nhanh hoặc backup path.
- **Route 53:** public/private DNS, resolver endpoints và health-based routing.
- **AWS Directory Service / AD Connector:** identity integration tùy domain architecture.
- **AWS IAM Identity Center:** workforce access và permission sets.
- **Amazon MQ, SQS, SNS, EventBridge:** message/event integration.
- **AWS Secrets Manager / Systems Manager Parameter Store:** secrets/configuration.
- **AWS Certificate Manager:** TLS certificates cho supported integrations.

Mọi endpoint/IP/DNS change cần được lập danh sách và thông báo cho firewall owners, partners, allowlists, monitoring và certificate management.



## 10. Chọn công cụ migration và data movement

### 10.1. AWS Application Migration Service (MGN)

AWS Application Migration Service là công cụ rehost cho physical, virtual và cloud-based servers sang Amazon EC2. MGN dùng block-level replication để giữ target server cập nhật trong lúc source vẫn hoạt động, sau đó launch test instance và cutover instance.

Phù hợp khi:

- Cần migrate nhiều server với ít thay đổi OS/application.
- Muốn giảm downtime bằng continuous replication.
- Cần kiểm thử target trước khi cutover.
- Muốn chuẩn hóa server migration thành waves.

MGN không tự giải quyết application refactoring, database schema conversion hoặc mọi dependency ngoài server. Cần chuẩn bị target VPC/subnet/security groups, IAM, EC2 quotas, licensing, DNS và application validation.

### 10.2. AWS Elastic Disaster Recovery (DRS) khác MGN thế nào?

| Tiêu chí | AWS MGN | AWS DRS |
|---|---|---|
| Mục tiêu chính | Migration/rehost sang EC2 | Disaster recovery và failback |
| Source | Physical, VM, cloud servers được hỗ trợ | Physical, VM, cloud servers được hỗ trợ |
| Replication | Block-level replication trong migration workflow | Continuous block-level replication vào staging area |
| Test | Test launch trước cutover | Recovery drill định kỳ không làm gián đoạn source |
| Cutover | Hoàn tất migration và vận hành target | Failover khi disaster; traffic cutover do tổ chức |
| Failback | Không phải workflow DR chính | Có reverse replication/failback workflows |
| Use case | Data center exit, server migration | Business continuity, recovery sau sự cố |

Hai dịch vụ có thể dùng công nghệ replication tương tự nhưng mục tiêu và lifecycle khác nhau. Chọn theo outcome: chuyển hẳn workload thì xem MGN; cần bảo vệ source và phục hồi khi disaster thì xem DRS.

### 10.3. AWS Database Migration Service (DMS)

AWS DMS hỗ trợ homogeneous và heterogeneous database migrations, gồm full load và Change Data Capture (CDC) để giảm downtime. DMS Schema Conversion hỗ trợ convert schema/code objects cho một số source-target combinations.

Dùng DMS khi:

- Cần migrate dữ liệu giữa database engines được hỗ trợ.
- Cần full load rồi replicate changes tới cutover.
- Cần chuyển database lên RDS/Aurora/Redshift hoặc target được hỗ trợ.
- Cần data validation so sánh source và target.

DMS không tự động chuyển toàn bộ database ecosystem trong mọi migration. Cần đánh giá schema, stored procedures, functions, triggers, jobs, users/grants, secondary indexes, foreign keys, unsupported data types và application connection strings. Một số schema conversion cần xử lý thủ công.

### 10.4. AWS DataSync

AWS DataSync tăng tốc và tự động hóa data movement giữa on-premises storage và AWS storage services hoặc giữa AWS storage locations được hỗ trợ.

Use cases:

- NFS/SMB file shares tới Amazon S3, EFS hoặc FSx.
- Di chuyển file datasets lớn và lặp lại incremental sync.
- Copy data theo schedule và kiểm tra transfer verification.
- Di chuyển dữ liệu giữa storage systems mà không viết script copy riêng.

DataSync phù hợp file/object transfer; không thay thế database replication hoặc server block replication. Đánh giá metadata, POSIX permissions, ACLs, symlinks, hard links, file count, small-file overhead và bandwidth.

### 10.5. AWS Transfer Family

AWS Transfer Family cung cấp managed SFTP, FTPS, FTP và AS2 endpoints để trao đổi file với partners/applications. Đây thường là lựa chọn replatform cho legacy file transfer servers khi muốn giữ giao thức partner đang dùng nhưng thay server tự quản bằng managed service.

Kiểm tra authentication, user directories, SSH keys, certificates, IP allowlists, workflows, logging, endpoint type và backend storage. Không phải ứng dụng nào cũng tương thích nếu dựa vào filesystem semantics hoặc custom scripts của FTP server cũ.

### 10.6. AWS Snow Family và offline transfer

Khi dữ liệu quá lớn hoặc network bandwidth không đủ trong thời gian yêu cầu, có thể đánh giá AWS Snow Family/offline data transfer options theo service availability hiện hành tại Region và quốc gia. AWS Snowball Edge có thể hỗ trợ data transfer/offline workflows ở nơi còn cung cấp; kiểm tra trạng thái sản phẩm, ordering, shipping, export/import và supported features trước khi đưa vào kế hoạch.

Ước tính thời gian transfer online:

\[
T_{days} = \frac{D_{TB}\times 8{,}000{,}000}{B_{Mbps}\times 86{,}400 \times U}
\]

Trong đó \(D_{TB}\) là dung lượng decimal TB, \(B_{Mbps}\) là bandwidth lý thuyết và \(U\) là utilization hiệu dụng (0–1). Công thức chưa tính protocol overhead, retries, contention và write changes trong thời gian copy.

Ví dụ 100 TB qua link 1 Gbps với utilization hiệu dụng 70%:

\[
T \approx \frac{100\times 8{,}000{,}000}{1000\times 86{,}400\times 0.7}
\approx 13.23\ ngày
\]

Với dữ liệu đang thay đổi, cần initial copy rồi incremental sync hoặc CDC trước cutover. Offline seed không tự giải quyết delta changes.

### 10.7. Ma trận chọn migration tool

| Workload/data | Tool chính có thể dùng | Vai trò |
|---|---|---|
| Server rehost to EC2 | AWS MGN | Replicate và launch target EC2 |
| Server disaster recovery | AWS DRS | Continuous replication, drills, recovery/failback |
| Database migration | AWS DMS / DMS Schema Conversion | Full load, CDC, schema conversion và validation |
| File/NFS/SMB/object data | AWS DataSync | Transfer và incremental sync |
| Partner file transfer | AWS Transfer Family | Managed SFTP/FTPS/FTP/AS2 |
| Very large/offline datasets | Snow Family hoặc phương thức offline được hỗ trợ | Seed dữ liệu khi network không phù hợp |
| Portfolio discovery | Application Discovery Service / AWS Transform | Inventory, utilization, dependency analysis |
| Migration tracking | AWS Migration Hub / AWS Transform workspace | Group, track status và wave visibility |

Một application có thể cần nhiều tools. Ví dụ: MGN cho EC2 servers, DMS cho database, DataSync cho file shares, Direct Connect/VPN cho network và Migration Hub/AWS Transform để tracking.

## 11. Landing zone và hybrid connectivity trước migration

### 11.1. Landing zone readiness

Landing zone là nền tảng AWS được chuẩn bị trước khi workloads được chuyển vào. Cần có:

- AWS Organizations và account structure theo environment/business units.
- AWS Control Tower hoặc cơ chế governance tương đương khi phù hợp.
- Centralized identity, IAM roles, permission sets và break-glass access.
- Logging/audit account với CloudTrail, Config và centralized log storage.
- Security services, GuardDuty, Security Hub, Inspector và incident workflow.
- Network account, shared VPC, Transit Gateway, DNS và egress architecture.
- KMS key strategy, secrets, certificates và encryption defaults.
- Backup policies, AWS Backup vaults và cross-account/Region copies.
- Tagging, cost allocation, budgets, billing alerts và showback.
- IaC/pipelines, patching, monitoring, SSM, AMI lifecycle và operational runbooks.

Không migrate production vào account chưa có owner, logging, security baseline, budget, backup và incident response. Landing zone phải được test trước wave đầu tiên.

### 11.2. Network discovery và target design

Trước migration, inventory:

- CIDR ranges, VLANs, subnets, routing tables và IP utilization.
- Firewall rules, ACLs, NAT, proxies, load balancers và DNS.
- East-west traffic giữa applications và north-south traffic tới users/partners.
- Private/public endpoints, multicast, static routes và non-routable protocols.
- Bandwidth, latency, jitter, packet loss và peak concurrency.
- Overlapping IP ranges giữa data centers, AWS VPCs và partners.

Target design cần tránh CIDR overlap, xác định VPC segmentation, shared services, Transit Gateway attachments, inspection/egress, DNS resolution và security controls. Không chỉ replicate firewall rules nguyên trạng; review least privilege và application flows để loại bỏ obsolete access.

### 11.3. Direct Connect và Site-to-Site VPN

| Thuộc tính | AWS Direct Connect | AWS Site-to-Site VPN |
|---|---|---|
| Kết nối | Dedicated private network connectivity qua DX location/provider | IPsec tunnels qua Internet hoặc supported transit |
| Encryption | DX không mặc định mã hóa traffic; dùng MACsec/IPsec khi yêu cầu và được hỗ trợ | IPsec mã hóa tunnel |
| Performance | Bandwidth/latency ổn định hơn khi provision phù hợp | Biến động theo Internet path |
| Setup | Cần circuit/provider/cross-connect và provisioning | Có thể triển khai nhanh hơn |
| Use case | Hybrid traffic lớn, ổn định, lâu dài | Bootstrap, backup path, moderate traffic |
| Resilience | Thiết kế nhiều DX connections/locations theo yêu cầu | Nhiều tunnels và thiết kế redundancy |

Có thể dùng VPN làm backup cho Direct Connect. Với traffic nhạy cảm, xác định encryption in transit requirement riêng; private connectivity không đồng nghĩa với encrypted payload.

### 11.4. DNS và identity trong hybrid

Khi application chuyển dần, một số components ở on-premises và một số ở AWS. Cần thiết kế:

- Route 53 Resolver inbound/outbound endpoints và forwarding rules.
- Private hosted zones và DNS split-horizon.
- AD trust/domain controllers hoặc Directory Service integration.
- Kerberos/SPN, LDAP, certificate authority và time synchronization.
- Identity federation, IAM roles và service-to-service credentials.
- DNS TTL và rollback record cho cutover.
- Partner/third-party allowlists cập nhật IP mới.

DNS change có thể không lan truyền tức thì do resolver caching. Hạ TTL trước cutover trong khoảng thời gian phù hợp, kiểm tra resolver paths và có kế hoạch restore record cũ.

### 11.5. Hybrid operating model

Trong giai đoạn coexistence, cần thống nhất:

- Ai quản lý on-premises network và ai quản lý AWS VPC.
- Ai approve firewall/DNS/route changes.
- Ai xử lý incident liên quan cross-environment dependency.
- Monitoring/logging có correlation ID và timestamp thống nhất.
- Patch, vulnerability scanning và configuration compliance áp dụng ở cả hai môi trường.
- Backup/DR responsibility cho dữ liệu đang replicate hoặc còn ở on-premises.
- CMDB/asset inventory cập nhật ownership và lifecycle.



## 12. Migration wave planning

### 12.1. Vì sao cần wave?

Migration wave là một nhóm applications/workloads được chuyển trong cùng một khoảng thời gian hoặc cùng một chu kỳ triển khai. Chia wave giúp giới hạn blast radius, phân bổ team, kiểm soát cutover windows và áp dụng lessons learned từ wave trước.

Không group workload chỉ theo subnet, OS hoặc server rack. Group theo application boundary và dependency graph trước, sau đó tối ưu theo technical complexity, business criticality, target architecture và lịch change.

### 12.2. Các yếu tố tạo wave

- **Dependency group:** các applications/servers cần chuyển cùng nhau hoặc cần một dependency bridge.
- **Business criticality:** tránh gom toàn bộ Tier 0 vào một wave.
- **Technical complexity:** OS, database, network, license, data volume và vendor constraints.
- **Migration strategy:** rehost, replatform, repurchase, retire...
- **Data transfer:** dung lượng, change rate, bandwidth và replication duration.
- **Cutover window:** business hours, blackout periods, quarter-end, peak season.
- **Team capacity:** application owners, network, security, DBA, cloud platform, vendor.
- **Landing zone readiness:** account, VPC, IAM, logging, backup, monitoring.
- **Rollback feasibility:** có thể quay lại source không và trong bao lâu?
- **Business value:** deadline data center exit, cost savings hoặc modernization priorities.

### 12.3. Phân loại wave theo mức độ rủi ro

Một cách tổ chức thường dùng:

| Wave | Nội dung | Mục tiêu |
|---|---|---|
| Wave 0 — Foundation | Landing zone, network, security, tooling, monitoring | Chuẩn bị nền tảng và xác minh quy trình |
| Wave 1 — Pilot | Workloads đơn giản, non-critical, dependencies ít | Kiểm chứng tool, runbook, estimates và team collaboration |
| Wave 2 — Repeatable | Workloads tương tự, complexity thấp/trung bình | Chuẩn hóa migration factory |
| Wave 3 — Complex | Nhiều dependencies, database/license/network đặc thù | Áp dụng kinh nghiệm và kiểm soát rủi ro |
| Wave N — Critical | Tier 0/Tier 1 hoặc workload có business constraints cao | Chỉ thực hiện khi pattern, rollback và owner đã chứng minh readiness |

Đừng để pilot chỉ gồm server rỗng/không có user path. Pilot nên đại diện đủ các vấn đề thực tế nhưng có blast radius nhỏ.

### 12.4. Dependency grouping

Tạo graph với node là application/server/database/shared service và edge là dependency. Gắn thuộc tính direction, protocol/port, criticality, owner và latency sensitivity.

Ví dụ:

~~~mermaid
flowchart TD
    DNS["DNS / Identity"] --> DB["Database"]
    DB --> API["Application API"]
    MQ["Message Broker"] --> API
    API --> WEB["Web frontend"]
    API --> EXT["External payment API"]
    FILE["Shared file service"] --> API
    OBS["Monitoring / Logging"] -.-> DB
    OBS -.-> API
    OBS -.-> WEB
~~~

Khi dependency cần thiết chưa thể migrate cùng wave, cần thiết kế connectivity bridge và test latency/authentication. Một application có thể tạm thời gọi database ở on-premises qua Direct Connect/VPN, nhưng đây là trạng thái chuyển tiếp cần owner, performance test và end date.

### 12.5. Wave plan deliverables

Mỗi wave cần tối thiểu:

- Danh sách applications, source assets và dependency group.
- 7R decision, target architecture và architecture approval.
- Detailed assessment và inventory confidence.
- Data transfer plan, migration tooling và replication estimates.
- Landing zone/account/VPC/subnet/security design.
- License, compliance và security approvals.
- Test plan, acceptance criteria và business sign-off.
- Cutover runbook, rollback runbook và communications.
- Owner/approver, timeline, maintenance window và escalation contacts.
- Hypercare plan, cost estimate và decommission criteria.

AWS Prescriptive Guidance thường khuyến nghị wave có đầy đủ assessment, readiness, infrastructure build/test, data transfer, cutover và wave closure. Thời lượng một wave có thể vài tuần tùy portfolio; không áp một số tuần cố định cho mọi tổ chức.

## 13. Cutover, validation và rollback planning

### 13.1. Xác định cutover strategy

Cutover là thời điểm chuyển application users/traffic và write authority từ source sang target. Chọn phương án dựa trên downtime tolerance, consistency và architecture:

- **Big bang:** chuyển toàn bộ application/dependency group trong một maintenance window.
- **Phased:** chuyển từng component/tenant/user group theo từng đợt.
- **Blue/green:** giữ source và target cùng tồn tại, chuyển traffic qua load balancer/DNS khi target pass.
- **Canary/weighted:** chuyển một tỷ lệ traffic nhỏ trước, quan sát rồi tăng dần.
- **Read-only transition:** target nhận read traffic trước, sau đó freeze writes và cutover writes.

Không phải mọi ứng dụng đều hỗ trợ canary/blue-green. Stateful database, batch jobs và external integrations có thể yêu cầu freeze và coordinated cutover.

### 13.2. Cutover runbook

Runbook cần có thứ tự, owner, expected duration, command/action, expected result và abort criteria.

Ví dụ:

1. Gửi change notice, xác nhận incident bridge và người phê duyệt.
2. Freeze code/configuration changes trước cutover window.
3. Xác nhận target infrastructure, security, DNS, monitoring và backup.
4. Xác nhận replication lag thấp hơn ngưỡng cho phép.
5. Chạy pre-cutover smoke tests và readiness checks.
6. Đưa source application vào maintenance/read-only mode.
7. Dừng background jobs/consumers và chặn writes theo runbook.
8. Thực hiện final data sync/CDC catch-up.
9. Kiểm tra data validation, row counts, checksums hoặc business reconciliation.
10. Cập nhật connection strings/secrets/service discovery.
11. Chuyển DNS/load balancer/Global Accelerator hoặc traffic route.
12. Khởi động target services theo dependency order.
13. Chạy application smoke tests và end-to-end business transactions.
14. Mở traffic theo từng bước và theo dõi SLO.
15. Nhận business sign-off, ghi nhận cutover timestamp và giữ source ở trạng thái rollback-ready trong thời gian đã định.

### 13.3. Acceptance criteria

Acceptance criteria phải định lượng được. Ví dụ:

| Nhóm | Tiêu chí mẫu |
|---|---|
| Availability | Health checks pass, không có critical component unavailable |
| Performance | p95 latency không vượt baseline + agreed threshold |
| Data | Row counts/checksums/reconciliation pass; no unexpected data loss |
| Functionality | Các critical business journeys pass |
| Security | IAM, encryption, vulnerability, logging và network tests pass |
| Integration | Partner APIs, SFTP, payment, email, queues hoạt động |
| Operations | Monitoring, alert, backup, patching và incident workflow hoạt động |
| Cost | Actual usage nằm trong expected range hoặc có action plan |
| Business | Product/business owner ký nghiệm thu |

Không dùng "server running" hoặc "HTTP 200" làm acceptance duy nhất. Cần test transaction end-to-end và kiểm tra dữ liệu.

### 13.4. Data validation

Với database migration, có thể dùng AWS DMS data validation khi source-target path hỗ trợ. DMS so sánh dữ liệu source/target theo row và báo mismatch. Tuy nhiên, validation có thể bị ảnh hưởng nếu ứng dụng tiếp tục ghi target trong khi validation chạy, rows liên tục thay đổi, thiếu primary keys hoặc datatype không được hỗ trợ.

Ngoài DMS validation, có thể dùng:

- Row counts theo table/partition.
- Checksums/hash theo batches.
- Referential integrity checks.
- Aggregate business totals: balance, order count, inventory quantity.
- Sampled record comparison.
- File count/size/hash và metadata checks cho file transfer.
- Application-level reconciliation và audit reports.

Định nghĩa tolerance rõ ràng: zero mismatch cho dữ liệu tài chính, hoặc một ngưỡng đã được business owner chấp nhận cho dữ liệu analytics/eventual consistency.

### 13.5. Rollback strategy

Rollback cần trả lời:

- Khi nào phải abort? Ví dụ data mismatch critical, security control fail, p95 latency vượt threshold, payment transaction failure.
- Ai có quyền quyết định rollback?
- Source còn dữ liệu authoritative không?
- Có thể chuyển traffic lại mà không mất writes phát sinh trên target không?
- Có cần reverse replication hoặc dual-write reconciliation không?
- DNS TTL, load balancer weights và connection pools sẽ rollback thế nào?
- External partners có cần cập nhật allowlists/endpoint trở lại?
- Source infrastructure còn nguyên và license/contract còn hiệu lực không?

**Điểm khó nhất là dữ liệu sau cutover.** Nếu target đã nhận writes mới, chuyển traffic về source mà không đồng bộ các writes đó sẽ gây data loss. Cần freeze writes, reverse sync hoặc data reconciliation theo database/application design. Không hứa rollback "một click" nếu không có cơ chế đồng bộ ngược đã test.

### 13.6. Go / No-Go decision

Tổ chức một readiness review trước cutover. No-Go nếu còn bất kỳ blocker critical nào:

- Replication/data transfer chưa catch up.
- Backup/restore hoặc rollback chưa test.
- Network/DNS/security rules chưa được phê duyệt.
- License/compliance chưa rõ.
- Application owner/incident commander không sẵn sàng.
- EC2/service quotas hoặc target capacity không đủ.
- Acceptance tests chưa pass.
- Data consistency hoặc write fencing chưa có phương án.

Go decision cần ghi tên approvers, thời gian, scope và assumptions.

## 14. Governance, ownership và migration operating model

### 14.1. Các vai trò chính

| Vai trò | Trách nhiệm |
|---|---|
| Executive sponsor | Business outcome, funding, risk acceptance và escalation |
| Migration program lead | Scope, timeline, waves, governance và status |
| Application owner | Business requirements, dependencies, testing và sign-off |
| Infrastructure/platform team | Landing zone, accounts, VPC, compute, storage và automation |
| Network team | Connectivity, routing, DNS, firewall và partner paths |
| Security/compliance | IAM, encryption, audit, data residency và approvals |
| DBA/data team | Schema, data migration, CDC, validation và consistency |
| Operations/SRE | Monitoring, backup, patching, incident response và hypercare |
| Vendor/partner | Product support, licensing, migration assistance và certification |

Một người có thể giữ nhiều vai trò ở chương trình nhỏ, nhưng accountability phải rõ. Không để application owner và technical owner cùng nghĩ người kia sẽ nghiệm thu.

### 14.2. RACI cho các hoạt động quan trọng

| Hoạt động | Responsible | Accountable | Consulted |
|---|---|---|---|
| Inventory/discovery | Migration team | Migration lead | Application/infrastructure owners |
| 7R decision | Solution architect | Application/business owner | Security, finance, operations |
| Target architecture | Cloud/platform team | Architecture board | Network, security, DBA |
| TCO/business case | FinOps/finance | Executive sponsor | Platform, application owner |
| Data migration | DBA/data team | Application owner | Network, security |
| Cutover | Migration lead + application team | Change authority | Operations, business, vendor |
| Rollback | Technical owners | Incident/change commander | Business owner |
| Decommission | Infrastructure team | Application owner | Security, compliance, finance |

### 14.3. Migration factory

Migration factory là mô hình chuẩn hóa công việc lặp lại qua các waves:

- Standard discovery templates và inventory schema.
- Reusable 7R decision records.
- Standard landing zone patterns và IaC modules.
- Migration runbooks cho MGN/DMS/DataSync.
- Standard test/validation scripts.
- Cutover/rollback templates.
- Central dashboard và issue/risk log.
- Wave retrospectives và continuous improvement.

Factory không có nghĩa mọi workload đều giống nhau. Chuẩn hóa phần lặp lại, còn exception phải có evidence, owner và approval.

### 14.4. FinOps và cost governance

Trước và sau migration:

- Tag resource theo application, owner, environment, cost center và migration wave.
- Dùng AWS Budgets và Cost Anomaly Detection.
- Theo dõi data transfer, NAT, inter-AZ, logging và storage growth.
- So sánh forecast với actual mỗi wave.
- Chỉ mua Savings Plans/Reserved Instances sau khi usage ổn định và có commitment strategy.
- Review idle resources, unattached EBS, snapshots, test instances và duplicate environments.
- Xác nhận decommission on-premises thật sự để realized savings xuất hiện.

Nếu giữ cả source và target chạy lâu dài, cloud bill có thể tăng thay vì giảm. Gắn deadline và owner cho parallel-run exit criteria.

### 14.5. Post-migration hypercare và decommission

Sau cutover, tổ chức hypercare trong khoảng thời gian đã thống nhất:

- Theo dõi SLO, incidents, support tickets và user feedback.
- Xử lý performance regression và capacity issues.
- Xác nhận backup/restore, DR, patching và monitoring.
- Tối ưu EC2/EBS/database sizing sau khi có production metrics.
- Đóng migration issues và cập nhật architecture/CMDB.
- Archive logs/data cần giữ và xóa dữ liệu tạm đúng policy.
- Decommission source resources sau khi business owner và compliance approve.
- Chấm dứt license/contracts và cập nhật asset records.



## 15. Case study: khảo sát và chọn chiến lược cho hệ thống bán hàng

### 15.1. Hiện trạng

Một doanh nghiệp bán lẻ vận hành hệ thống thương mại điện tử trong data center:

| Thành phần | Hiện trạng | Dependency |
|---|---|---|
| Web tier | 4 Linux VMs, Java web application | API tier, DNS, TLS |
| API tier | 6 Linux VMs, Java/Spring Boot | PostgreSQL, Redis, SQS-compatible internal broker |
| Database | PostgreSQL 2 TB, streaming replication nội bộ | API, reporting, backup |
| File service | SMB share 8 TB | API, batch jobs |
| Identity | Active Directory 2 domain controllers | Web/API, admin access |
| Reporting | 2 VMs chạy batch mỗi đêm | PostgreSQL, SMB share |
| External | Payment gateway, email, SFTP logistics partner | API tier, DNS, allowlists |

Business requirements: data center lease hết hạn sau 9 tháng; peak traffic tăng 4 lần vào mùa sale; mục tiêu RTO 2 giờ, RPO 5 phút cho order database; maintenance window tối đa 2 giờ.

### 15.2. Discovery findings

Assessment thu thập CPU/memory p95 trong 4 tuần, disk IOPS, database write rate, network flows và application owner interviews. Kết quả:

- Web/API có utilization biến động mạnh, cần horizontal scaling.
- PostgreSQL là data tier critical, có nhiều extensions và stored procedures.
- SMB share có ACL phức tạp và nhiều small files.
- Reporting batch chỉ chạy ban đêm, có thể tách khỏi cutover web/API.
- Payment gateway allowlist IP; partner SFTP có maintenance window riêng.
- Một legacy report server không còn user và có thể retire sau archive.

### 15.3. 7R decisions

| Thành phần | Chiến lược | Target/next step | Lý do |
|---|---|---|---|
| Web tier | Replatform | ECS on Fargate hoặc EC2 Auto Scaling sau PoC | Stateless candidate, cần scale theo traffic |
| API tier | Replatform theo từng service | ECS/Fargate; giữ một số workers trên EC2 trong giai đoạn đầu | Tăng elasticity, thay đổi packaging có giới hạn |
| PostgreSQL | Replatform | Amazon RDS for PostgreSQL hoặc Aurora PostgreSQL sau compatibility assessment | Managed backups/HA, nhưng cần kiểm tra extensions và query behavior |
| SMB share | Replatform | Amazon FSx for Windows File Server | Giữ SMB/ACL semantics gần hiện trạng |
| Active Directory | Retain/extend trước | Hybrid AD connectivity; đánh giá AWS Managed Microsoft AD sau | Tránh thay identity đồng thời với app cutover |
| Reporting batch | Rehost trước, modernize sau | EC2 hoặc AWS Batch tùy scheduler/data access | Giảm scope wave đầu |
| Legacy report server | Retire | Archive reports/data, decommission | Không còn business usage |

### 15.4. Wave proposal

- **Wave 0:** landing zone, Direct Connect/VPN, DNS Resolver, identity integration, centralized logging, backup, CI/CD và security baseline.
- **Wave 1:** reporting non-critical server và một service nội bộ để kiểm thử MGN/observability.
- **Wave 2:** file service và batch workloads, kiểm tra FSx ACLs, DataSync và schedule.
- **Wave 3:** API/web tier theo dependency group, canary traffic và load testing.
- **Wave 4:** PostgreSQL migration với DMS/native tooling, CDC, data validation và freeze writes trong cutover.
- **Wave 5:** retire old report server, decommission source resources và optimize AWS usage.

### 15.5. Rủi ro và mitigation

| Rủi ro | Tác động | Mitigation |
|---|---|---|
| PostgreSQL extension không tương thích target | Query/application fail | DMS Schema Conversion/compatibility assessment và PoC |
| DataSync không giữ đúng ACL/metadata | User access sai | Pilot file sample, ACL validation và owner sign-off |
| Partner allowlist chưa cập nhật | Payment/SFTP fail | Test endpoint sớm, coordinated change và rollback path |
| Peak sale không đủ capacity | Latency/error tăng | Load test 4x peak, autoscaling và quota review |
| DNS caching kéo dài | Cutover chậm | Hạ TTL trước, kiểm tra resolver/partner caching |
| Hybrid AD latency | Login/service auth chậm | Test DNS/Kerberos/LDAP qua private connectivity |
| Writes phát sinh trên target sau cutover | Rollback gây mất dữ liệu | Freeze/fencing và reverse sync/reconciliation plan |

### 15.6. Quyết định cuối cùng

Không nên chuyển toàn bộ stack bằng một cutover duy nhất. Chuyển foundation và low-risk components trước, sau đó web/API, cuối cùng database và components có business risk cao. Mỗi wave có acceptance criteria, owner và rollback plan riêng. Chỉ retire data center khi toàn bộ workloads, backup, network, identity, audit và operational responsibilities đã được sign-off.

## 16. Bài thực hành trên AWS sandbox

Các lab sử dụng inventory giả lập hoặc test workloads do người học quản lý. Không cài discovery agent, migration agent hay thay đổi route/firewall trên production khi chưa có approval.

### 16.1. Lab A — Tạo application portfolio inventory

1. Tạo spreadsheet/CSV inventory với application ID, owner, business criticality, server IDs, OS, CPU, RAM, disks, database và dependencies.
2. Thêm utilization p50/p95, disk IOPS và network traffic sample.
3. Đánh dấu dữ liệu unknown, stale hoặc unverified.
4. Group servers theo application boundary.
5. Xác định data owner, business owner và technical owner.
6. Tạo dependency map cho một application.
7. Review inventory completeness và ghi confidence score.

Deliverable: application inventory, dependency map và list of assessment gaps.

### 16.2. Lab B — So sánh discovery methods

1. Đọc yêu cầu của AWS Application Discovery Service.
2. Phân biệt Agentless Collector và Discovery Agent.
3. Tạo một sample inventory từ CMDB/vCenter export hoặc dataset giả lập.
4. Đánh dấu trường nào là static configuration, utilization, process và network connection.
5. Đánh giá dữ liệu nào cần xác minh với application owner.
6. Tạo sơ đồ discovery → Migration Hub/AWS Transform → portfolio assessment.
7. Viết data access/retention assumptions.

Deliverable: discovery method decision record và data quality report.

### 16.3. Lab C — Phân loại 7R và target AWS services

1. Chọn tối thiểu 8 workloads mẫu: VM, database, file share, SaaS candidate, legacy app, batch job, stateless API và unused server.
2. Đưa ra candidate 7R cho mỗi workload.
3. Chọn ít nhất hai phương án cho workload phức tạp.
4. Mapping target services: EC2, ECS, EKS, Lambda, RDS, Aurora, DynamoDB, FSx, EFS, S3.
5. Ghi rationale, assumptions, blockers, licensing và business approval.
6. So sánh time-to-migrate, cost, risk và operational complexity.

Deliverable: 7R decision matrix và target service mapping.

### 16.4. Lab D — Tính data transfer và TCO

1. Chọn dataset 20 TB và bandwidth 500 Mbps.
2. Tính theoretical transfer duration và điều chỉnh utilization hiệu dụng.
3. Thêm delta change rate và incremental sync window.
4. Tạo cost model on-premises vs AWS 1-year/3-year.
5. Tính EC2, EBS, RDS, DataSync/network, backup và support.
6. Tạo conservative/expected/growth scenarios.
7. Xác định top 5 assumptions ảnh hưởng TCO.

Deliverable: transfer estimate, TCO model và sensitivity analysis.

### 16.5. Lab E — Lập migration wave và cutover plan

1. Tạo dependency graph cho ứng dụng ba tầng.
2. Chia foundation, pilot, repeatable và complex waves.
3. Chọn tool MGN/DMS/DataSync theo từng component.
4. Chuẩn bị cutover runbook với owner, duration và expected results.
5. Định nghĩa acceptance criteria cho data, performance, security và business flow.
6. Viết rollback decision tree và data reconciliation approach.
7. Thực hiện tabletop exercise cho scenario target database không pass validation.

Deliverable: wave plan, cutover/rollback runbook và Go/No-Go checklist.

## 17. Checklist đánh giá migration assessment

### Business và portfolio

- [ ] Business drivers và measurable outcomes đã được thống nhất?
- [ ] Scope, exclusions, locations và deadline đã rõ?
- [ ] Mỗi application có business owner và technical owner?
- [ ] Criticality, SLA/SLO, RTO/RPO và downtime tolerance đã xác nhận?
- [ ] License/vendor support và end-of-life constraints đã kiểm tra?

### Discovery và dependencies

- [ ] Server/database/storage inventory đủ và có timestamp?
- [ ] Utilization data đại diện peak/seasonal workload?
- [ ] Network connections/processes đã được thu thập khi cần?
- [ ] Dependencies, protocols, ports và owners đã xác minh?
- [ ] Unknown/stale/duplicate records có remediation owner?
- [ ] Data classification, residency và retention đã xác định?

### 7R và target architecture

- [ ] Mỗi workload có candidate 7R và rationale?
- [ ] Retire/retain đã được xem xét, không mặc định mọi thứ phải migrate?
- [ ] Có so sánh rehost/replatform/refactor khi phù hợp?
- [ ] Target services được kiểm tra compatibility, quota, Region và pricing?
- [ ] Database schema/extensions/license đã đánh giá?
- [ ] Shared file/object semantics và integration behavior đã đánh giá?

### Cost và readiness

- [ ] On-premises TCO bao gồm facility, licenses, support và labor?
- [ ] AWS estimate gồm compute, storage, database, network, security và support?
- [ ] Migration, parallel-run, training, downtime và decommission costs đã tính?
- [ ] Utilization/right-sizing assumptions và growth scenarios rõ?
- [ ] Landing zone, network, identity, security và operations sẵn sàng?
- [ ] FinOps tagging, budgets và cost ownership đã định nghĩa?

### Waves, cutover và rollback

- [ ] Dependency groups và wave sequencing hợp lý?
- [ ] Pilot đại diện đủ pattern và có blast radius nhỏ?
- [ ] Migration tool phù hợp từng data/server component?
- [ ] Cutover window, runbook, owner và approver rõ?
- [ ] Acceptance criteria định lượng và business sign-off?
- [ ] Rollback có phương án xử lý writes sau cutover?
- [ ] DNS, partner allowlists và hybrid dependencies đã test?
- [ ] Hypercare, source decommission và lessons learned có owner?

## 18. Câu hỏi tự đánh giá

1. Migration assessment cần trả lời những quyết định nào?
2. Vì sao phải bắt đầu từ business drivers thay vì chọn server để chuyển?
3. Application portfolio khác infrastructure inventory ở điểm nào?
4. Static configuration khác utilization time series thế nào?
5. Vì sao CPU average không đủ để right-size EC2?
6. Application dependency mapping cần ghi những thuộc tính nào?
7. AWS Application Discovery Service có những phương thức discovery nào?
8. Agentless Collector khác Discovery Agent ra sao?
9. AWS Migration Hub home Region dùng để làm gì?
10. AWS Transform hỗ trợ những phần nào trong migration assessment/planning?
11. AI recommendations cần được kiểm chứng ra sao?
12. Migration Evaluator/TCO analysis cần những nhóm chi phí nào?
13. Bảy chiến lược migration (7 Rs) là gì?
14. Retire khác Retain như thế nào?
15. Rehost khác Relocate ra sao?
16. Repurchase phù hợp trong trường hợp nào?
17. Replatform khác Refactor/Re-architect thế nào?
18. Vì sao không nên refactor mọi application ngay trong migration wave lớn?
19. Khi nào nên dùng AWS Application Migration Service (MGN)?
20. MGN khác AWS Elastic Disaster Recovery (DRS) ở mục tiêu nào?
21. AWS DMS hỗ trợ full load và CDC ra sao?
22. Vì sao DMS không tự động migrate mọi schema object/permission?
23. AWS DataSync phù hợp với data movement pattern nào?
24. AWS Transfer Family giải quyết use case gì?
25. Khi nào cần đánh giá offline data transfer?
26. Landing zone cần có những control nào trước production migration?
27. Direct Connect khác Site-to-Site VPN thế nào?
28. Vì sao Direct Connect không đồng nghĩa với encryption?
29. Migration wave nên group theo yếu tố nào?
30. Cutover runbook cần những bước và owner nào?
31. Acceptance criteria cần đo những khía cạnh nào?
32. Vì sao rollback sau khi target đã nhận writes khó hơn rollback trước cutover?
33. Vì sao phải có data reconciliation/reverse sync plan?
34. Migration factory giúp chuẩn hóa công việc gì?
35. Hypercare và decommission criteria có vai trò gì?
36. Những yếu tố nào cần đưa vào 3-year TCO và business case?

### Định hướng đáp án

- **Assessment:** bắt đầu từ business outcome, portfolio scope, inventory, dependencies, performance, compliance và operating model.
- **Discovery:** kết hợp static configuration, utilization, process/network connections và owner interviews; chuẩn hóa identity và data confidence.
- **7 Rs:** Retire, Retain, Rehost, Relocate, Repurchase, Replatform, Refactor/Re-architect; chọn theo business/technical constraints.
- **Tool selection:** MGN cho server rehost; DRS cho disaster recovery; DMS cho database; DataSync cho file/object; Transfer Family cho partner protocols; Snow/offline transfer cho datasets rất lớn khi được hỗ trợ.
- **TCO:** tính cả on-premises, AWS run cost, license, network, security, migration, parallel run, training và decommission.
- **Waves:** group theo dependency, criticality, complexity, data transfer, downtime và team capacity; pilot trước khi scale.
- **Cutover:** final sync, freeze writes, validate, traffic cutover, business sign-off; rollback phải xử lý dữ liệu phát sinh sau khi target đã nhận writes.

## 19. Tài liệu AWS chính thức

1. [About AWS Cloud migration strategies (7 Rs)](https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/migration-strategies.html) — Định nghĩa và use cases của bảy chiến lược migration.
2. [Detailed portfolio discovery](https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-migration/detailed-portfolio-discovery.html) — Portfolio inventory, 7R rationalization và migration planning.
3. [Application portfolio assessment strategy](https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-application-portfolio-assessment-migration/portfolio-analysis-migration-planning.html) — Assessment outcomes, dependency groups và wave planning.
4. [AWS Application Discovery Service](https://docs.aws.amazon.com/application-discovery/latest/userguide/what-is-appdiscovery.html) — Discovery concepts, data collection và Migration Hub integration.
5. [Agentless Collector](https://docs.aws.amazon.com/application-discovery/latest/userguide/agentless-collector.html) — VMware discovery, server utilization và database/analytics data collection.
6. [Discovery Agent](https://docs.aws.amazon.com/application-discovery/latest/userguide/discovery-agent.html) — Agent-based inventory, process và network connections.
7. [AWS Migration Hub](https://docs.aws.amazon.com/migrationhub/latest/ug/whatishub.html) — Central migration tracking và home Region.
8. [AWS Transform migration assessments](https://docs.aws.amazon.com/transform/latest/userguide/transform-app-assessments.html) — TCO/business case, feasibility và scenario comparison.
9. [AWS Transform migrations including VMware](https://docs.aws.amazon.com/transform/latest/userguide/transform-app-vmware.html) — Discovery, dependency mapping, wave planning, landing zone và rehost.
10. [AWS Transform 7R recommendations](https://docs.aws.amazon.com/transform/latest/userguide/transform-vmware-r-strategy-report.html) — Strategy recommendations theo server/application.
11. [Migration Evaluator business case](https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-tools/business-case-migration-evaluator.html) — TCO inputs và cost modeling.
12. [AWS Application Migration Service](https://docs.aws.amazon.com/mgn/latest/ug/what-is-application-migration-service.html) — Rehost server workloads to EC2.
13. [AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/what-is-drs.html) — DR replication/recovery, phân biệt với migration.
14. [AWS Database Migration Service best practices](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_BestPractices.html) — Database assessment, PoC, performance và data validation.
15. [AWS DMS data validation](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Validating.html) — So sánh source/target data và validation limitations.
16. [AWS DMS Schema Conversion](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_SchemaConversion.html) — Schema/code conversion cho database migration.
17. [AWS DataSync User Guide](https://docs.aws.amazon.com/datasync/latest/userguide/what-is-datasync.html) — File/object data transfer và supported locations.
18. [AWS Transfer Family](https://docs.aws.amazon.com/transfer/latest/userguide/what-is-aws-transfer-family.html) — Managed SFTP, FTPS, FTP và AS2.
19. [AWS Snow Family](https://docs.aws.amazon.com/snowball/latest/developer-guide/whatisedge.html) — Offline data transfer options và device workflows; kiểm tra availability hiện hành.
20. [AWS Direct Connect](https://docs.aws.amazon.com/directconnect/latest/UserGuide/Welcome.html) — Dedicated hybrid connectivity và resilience.
21. [AWS Site-to-Site VPN](https://docs.aws.amazon.com/vpn/latest/s2svpn/VPC_VPN.html) — IPsec tunnels và hybrid network.
22. [AWS Control Tower](https://docs.aws.amazon.com/controltower/latest/userguide/what-is-control-tower.html) — Multi-account landing zone và governance.
23. [AWS Prescriptive Guidance: Wave planning](https://docs.aws.amazon.com/prescriptive-guidance/latest/application-portfolio-assessment-guide/wave-planning.html) — Dependency groups, wave phases, cutover và rollback.
24. [Guidelines for a successful migration](https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-program-implementation/guidelines.html) — Program governance, landing zone và operating model.
25. [AWS Migration Hub large migration guide](https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/welcome.html) — Portfolio, waves, migration factory và large-scale migration.

> **Ghi nhớ cuối bài:** Khảo sát hệ thống tốt biến inventory và dependency data thành quyết định có thể kiểm chứng: workload nào retire/retain, workload nào dùng 7R nào, target AWS services nào phù hợp, chi phí và rủi ro ra sao, và chuyển theo wave nào. Migration thành công cần landing zone sẵn sàng, data movement đúng công cụ, cutover/rollback có owner, acceptance criteria định lượng và operating model sau migration. Đừng xem "server đã chạy trên AWS" là hoàn tất nếu business flow, dữ liệu, security, monitoring, backup và chi phí chưa được nghiệm thu.

