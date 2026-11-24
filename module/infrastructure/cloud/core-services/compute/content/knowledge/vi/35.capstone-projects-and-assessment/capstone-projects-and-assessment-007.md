# Đánh giá kiến trúc theo SLO, bảo mật, khả năng vận hành và chi phí

Một kiến trúc compute không thể được đánh giá chỉ bằng việc ứng dụng chạy được hoặc có đủ CPU và bộ nhớ. Kiến trúc phù hợp phải đáp ứng mục tiêu chất lượng dịch vụ (SLO), bảo vệ dữ liệu và workload, có thể được triển khai/giám sát/phục hồi bởi đội ngũ vận hành, đồng thời nằm trong ngân sách ở cả trạng thái bình thường lẫn khi xảy ra sự cố.

Bốn góc nhìn này có quan hệ chặt chẽ. Tăng số replica có thể cải thiện availability nhưng làm tăng compute cost và bề mặt tấn công. Dùng serverless giảm công việc quản lý host nhưng có thể tạo giới hạn concurrency hoặc cold start. Dùng spot giảm giá nhưng có thể làm tăng retry và nguy cơ trễ deadline. Mã hóa và private networking tăng mức bảo vệ nhưng cần thiết kế key lifecycle, DNS, egress và observability. Đánh giá kiến trúc cần làm rõ các trade-off bằng yêu cầu, số liệu và bằng chứng.

Trong module CLOUD_CORE_SERVICES_COMPUTE, bài capstone này tổng hợp kiến thức về VM, container, Kubernetes, serverless, CPU/memory/network/storage, scaling, availability, identity, security, monitoring, backup/recovery, quota và cost governance. Bạn sẽ thực hiện một architecture review có cấu trúc, chấm điểm theo tiêu chí, xác định rủi ro và đề xuất cải tiến có thể kiểm chứng.

Sau bài học, bạn có thể:

- Xác định phạm vi, giả định, stakeholder và yêu cầu của một architecture review.
- Chuyển yêu cầu nghiệp vụ thành SLI/SLO, error budget, RPO/RTO và capacity target.
- Đánh giá kiến trúc compute theo availability, latency, throughput, durability và khả năng mở rộng.
- Thực hiện threat modeling và kiểm tra identity, network, data protection, workload hardening và supply chain.
- Đánh giá observability, deployment, incident response, backup/restore và disaster recovery.
- Tính TCO và unit economics, bao gồm chi phí dự phòng, egress, managed service, vận hành và sự cố.
- So sánh phương án bằng trade-off, scoring rubric và evidence-based decision.
- Viết findings, risk register, ADR và roadmap cải tiến theo mức độ ưu tiên.

## 1. Mục tiêu và phạm vi architecture review

Architecture review là hoạt động đánh giá có phương pháp để xác định thiết kế có đáp ứng yêu cầu và có thể vận hành bền vững hay không. Review không chỉ tìm lỗi cấu hình; nó xem xét toàn bộ đường đi từ client, workload, compute, network, storage, dependency đến quy trình vận hành và chi phí.

### Các câu hỏi trung tâm

- Hệ thống cần phục vụ ai và quy trình nghiệp vụ nào?
- Mức độ gián đoạn hoặc mất dữ liệu nào có thể chấp nhận?
- Workload chạy trên VM, container, Kubernetes, serverless hay mô hình kết hợp?
- Capacity hiện tại và capacity khi peak/failover là bao nhiêu?
- Ai có thể triển khai, truy cập, thay đổi và khôi phục hệ thống?
- Có bằng chứng nào cho thấy SLO, security controls và recovery plan hoạt động?
- Tổng chi phí sở hữu và chi phí cho mỗi đơn vị công việc là bao nhiêu?
- Những giả định nào chưa được kiểm chứng?

### Phạm vi cần chốt

| Phạm vi | Ví dụ | Cần ghi rõ |
|---|---|---|
| Business service | Checkout, reporting, image processing | Owner, criticality, business hours |
| Workload | API, worker, batch, database, cache | Runtime, duration, traffic pattern |
| Compute | VM, container, Kubernetes, function | Instance shape, requests/limits, scaling |
| Network | VPC/VNet, subnet, load balancer, NAT | Trust boundary, ingress/egress, zones |
| Storage/data | Block, file, object, database | Data class, durability, retention |
| Identity/security | IAM, service account, certificate, secret | Principal, permissions, trust |
| Operations | CI/CD, monitoring, on-call, backup | Team, runbook, recovery |
| Cost | Compute, storage, network, support | Budget, allocation, forecast horizon |

Review có thể tập trung vào một service hoặc toàn bộ platform. Dù phạm vi nhỏ, cần ghi các dependency bên ngoài vì chúng ảnh hưởng trực tiếp đến SLO, security và cost.

### Stakeholder

Tối thiểu cần có workload owner, platform/cloud engineer, SRE/operations, security, data owner và FinOps/finance. Với hệ thống có yêu cầu pháp lý hoặc dữ liệu nhạy cảm, cần thêm privacy, compliance hoặc risk owner. Mỗi finding cần một owner có quyền thực hiện hành động và một người chấp nhận rủi ro nếu không khắc phục.

## 2. Thu thập evidence trước khi đánh giá

Kết luận kiến trúc cần dựa trên bằng chứng. Sơ đồ thiết kế mô tả ý định; cấu hình đang chạy và kết quả kiểm thử cho biết trạng thái thực tế.

### Evidence thường cần

- Architecture diagram và data flow.
- IaC, deployment manifest và cấu hình runtime.
- Inventory VM, node pool, Pod, function, database, storage và network.
- SLI/SLO dashboard, alert history và incident records.
- Load test, benchmark và capacity forecast.
- IAM/RBAC policy, security group, network policy và audit log.
- Vulnerability scan, image provenance và patch report.
- Backup policy, restore test và DR exercise.
- Cost export, billing report, budget và allocation tag.
- Runbook, on-call rota, change record và postmortem.
- Quota inventory, provider limits và reservation/commitment.

### Phân loại độ tin cậy

| Mức evidence | Mô tả | Ví dụ |
|---|---|---|
| E0 – Chưa có | Chỉ là giả định hoặc lời nói | “Database chắc chắn có backup” |
| E1 – Được mô tả | Có tài liệu nhưng chưa kiểm chứng | Backup policy trong design doc |
| E2 – Cấu hình tồn tại | Có cấu hình hoặc dashboard | Backup job enabled, alert rule deployed |
| E3 – Đã kiểm thử | Có kết quả test có thể lặp lại | Restore test thành công với thời gian đo |
| E4 – Đã vận hành | Có lịch sử production chứng minh | DR exercise và incident response trong thực tế |

Không nên chấm một control là “đạt” chỉ vì tài liệu nói nó tồn tại. Ví dụ, có backup job chưa chứng minh dữ liệu restore được; có autoscaler chưa chứng minh quota và provider capacity cho phép scale.

### Evidence register

Với mỗi tiêu chí, lưu:

- Mã tiêu chí.
- Yêu cầu cần đáp ứng.
- Nguồn evidence và thời điểm thu thập.
- Môi trường/region/version được kiểm tra.
- Kết quả và giới hạn của phép thử.
- Người xác nhận.
- Khoảng trống còn lại.

Dữ liệu evidence cần được xử lý theo chính sách bảo mật; không đưa secret, token, private key hoặc thông tin cá nhân không cần thiết vào review artifact.

## 3. Mô hình hệ thống và workload profile

Trước khi xem SLO hay chi phí, cần hiểu hệ thống thực sự làm gì.

### Workload profile

Ghi nhận:

- Request/second, concurrent users và traffic burst.
- Batch volume, queue depth, task duration và deadline.
- CPU time, memory working set và peak memory.
- Storage IOPS, throughput, latency và dung lượng.
- Network throughput, packet rate, egress và cross-zone traffic.
- Dependency call rate, connection pool và service quota.
- Statefulness, session, checkpoint và dữ liệu cần giữ.
- Growth rate, seasonality và event lớn.
- Các stage tuần tự, stage song song và bottleneck.

### Phân loại workload

| Workload | Đặc điểm | Điểm cần đánh giá |
|---|---|---|
| Interactive API | Latency nhạy, traffic thay đổi | p95/p99, autoscaling, dependency |
| Stateful service | Dữ liệu và identity gắn với member | Persistence, quorum, fencing, backup |
| Batch | Có deadline, chia task | Throughput, queue, retry, cost/run |
| Event-driven | Scale theo event/invocation | Concurrency, cold start, downstream |
| HPC/GPU | Compute/network/accelerator intensive | Utilization, interconnect, data feed |
| Edge/hybrid | Có giới hạn kết nối và locality | Offline behavior, sync, local recovery |

### Vẽ data flow và trust boundary

Sơ đồ cần chỉ rõ client, ingress, compute, service-to-service, database, object storage, secrets, logging, backup và control plane. Đánh dấu public/private endpoint, account/project boundary, region, zone, identity principal và nơi dữ liệu được lưu hoặc truyền.

Sơ đồ quá tổng quát không đủ để đánh giá security hoặc failure mode. Ví dụ, cần biết function gọi database qua private endpoint hay public endpoint, và backup được ghi sang account/region nào.

## 4. Đánh giá SLO và SLI

SLO (Service Level Objective) là mục tiêu nội bộ về chất lượng dịch vụ trong một cửa sổ thời gian. SLI (Service Level Indicator) là phép đo dùng để đánh giá kết quả. SLA là cam kết bên ngoài với khách hàng hoặc đối tác, có thể gắn điều khoản dịch vụ. Không nên coi ba khái niệm này là đồng nghĩa.

### Chọn SLI có ý nghĩa với người dùng

Các SLI thường gặp:

- Availability: tỷ lệ request hợp lệ được xử lý thành công.
- Latency: tỷ lệ request hoàn thành dưới ngưỡng thời gian.
- Correctness: tỷ lệ kết quả đúng hoặc transaction hợp lệ.
- Freshness: độ trễ dữ liệu đến thời điểm cần.
- Durability: khả năng giữ dữ liệu đã xác nhận.
- Batch completion: tỷ lệ job hoàn tất trước deadline.
- Queue age: tuổi của message/task chưa được xử lý.

SLI phải đo hành vi người dùng hoặc kết quả nghiệp vụ. CPU utilization 90% là metric vận hành, không tự nó là SLI chất lượng dịch vụ.

### Ví dụ SLO

| Service | SLI | SLO minh họa | Cửa sổ |
|---|---|---|---|
| Checkout API | Successful eligible requests | 99,9% | 30 ngày |
| Checkout API | p95 latency | Dưới 300 ms | 30 ngày |
| Order database | Successful committed writes | 99,95% | 30 ngày |
| Analytics batch | Jobs completed by deadline | 99% trước 05:30 | 30 ngày |
| Object processing | Valid output objects | 99,9% checksum pass | 30 ngày |

Các con số chỉ là ví dụ. SLO thực tế phải xuất phát từ business impact, user expectation, architecture và chi phí để đạt mục tiêu.

### Availability và error budget

Với availability SLO \(S\), error budget trong cửa sổ là:

\[
ErrorBudget = 1 - S
\]

Nếu SLO 99,9%, error budget là 0,1% số request hoặc thời gian được tính theo định nghĩa SLI. Trong cửa sổ 30 ngày, nếu đo theo thời gian liên tục, 0,1% tương đương khoảng 43,2 phút. Nếu đo theo request, cần tính trên tổng số request hợp lệ thay vì quy đổi trực tiếp sang phút.

Error budget giúp quyết định tốc độ thay đổi:

- Budget còn nhiều: có thể tiếp tục release theo policy.
- Budget tiêu thụ nhanh: tăng kiểm thử, giảm change risk hoặc tạm dừng release rủi ro.
- Budget cạn: ưu tiên reliability work và khắc phục nguyên nhân.

### Latency percentiles

Average latency có thể che tail latency. Review nên xem p50, p90, p95 và p99 theo endpoint và dependency. Một API p50 80 ms nhưng p99 3 giây có thể gây trải nghiệm không ổn định.

Đánh giá latency end-to-end gồm DNS, connect, TLS, queue wait, compute, database, serialization và response. Không chỉ nhìn duration của function hoặc container.

## 5. Đánh giá availability, resilience và failure domain

Availability không đến từ một con số replica. Cần xác định các thành phần có thể lỗi độc lập và cách hệ thống tiếp tục phục vụ.

### Failure domain

- Process/container.
- VM hoặc worker node.
- Rack/host group hoặc availability zone.
- Region.
- Network gateway, DNS, load balancer.
- Database primary/replica.
- Identity provider, secret manager hoặc KMS.
- Cloud control plane và external dependency.
- Human/operator error.

### Câu hỏi review

- Có single point of failure nào không?
- Replica có được phân bố qua failure domain độc lập không?
- Một node/zone mất thì surviving capacity có đủ không?
- Load balancer chỉ gửi traffic đến backend Ready không?
- Database failover có fencing và consistency check không?
- Retry có tạo duplicate transaction hoặc retry storm không?
- Circuit breaker, timeout và bulkhead có phù hợp không?
- Có degraded mode khi dependency phụ không hoạt động không?

### RTO và RPO

- **RTO:** thời gian tối đa chấp nhận để khôi phục dịch vụ.
- **RPO:** lượng dữ liệu tối đa có thể mất tính theo thời gian.

RTO/RPO phải được xác định theo từng data class hoặc service tier. Một cache có thể tái tạo có RPO gần như không quan trọng; database giao dịch có thể cần RPO thấp hơn nhiều.

### Availability không đồng nghĩa durability

Replication có thể tăng khả năng tiếp tục phục vụ nhưng cũng replicate lỗi logic hoặc thao tác xóa. Backup có thể tăng recoverability nhưng không nhất thiết giúp failover tức thời. Review cần đánh giá cả replication, backup, point-in-time recovery và restore test.

## 6. Đánh giá lựa chọn compute và resource sizing

Mỗi mô hình compute có trade-off khác nhau. Review nên đánh giá theo workload profile và lifecycle.

| Mô hình | Điểm mạnh | Rủi ro/câu hỏi review |
|---|---|---|
| VM | Kiểm soát OS, disk, network và runtime | Patch, boot time, drift, instance quota, idle cost |
| Container | Image nhất quán, đóng gói dependency | Image security, runtime, resource limit, node capacity |
| Kubernetes | Scheduling, rollout, service discovery, orchestration | Control plane, cluster complexity, quota, CNI/CSI, operator |
| Serverless | Giảm quản lý host, scale theo event | Concurrency, cold start, runtime limit, vendor constraints |
| Managed batch/data service | Scheduler và worker lifecycle tích hợp | Pricing unit, quota, capacity availability, portability |
| GPU/HPC | Accelerator và interconnect chuyên dụng | Utilization, VRAM, data pipeline, capacity reservation |

### CPU

Kiểm tra request, limit, throttling, utilization, run queue và CPU architecture. CPU limit quá thấp có thể làm latency tăng; request quá cao có thể giữ capacity trên giấy và khiến Pod khó schedule.

### Memory

Kiểm tra working set, peak memory, heap, native memory, GC, OOM và memory pressure. Capacity phải tính cả sidecar, system daemon và runtime overhead.

### Storage

Đánh giá dung lượng, IOPS, throughput, latency, durability, topology, snapshot và restore. Một volume đủ GB nhưng không đủ IOPS vẫn có thể làm database vi phạm SLO.

### Network

Đánh giá bandwidth, packet rate, connection count, NAT/egress, DNS, MTU, cross-zone cost và private endpoint. Workload compute-intensive cũng có thể bị network-bound khi shuffle hoặc tải dataset lớn.

### Capacity headroom

Không lập kế hoạch theo average usage. Dùng peak, p95 demand, scale-out time, quota runway và surviving capacity khi một failure domain mất. Headroom phải được tính ở cả compute, subnet IP, database connection, storage throughput và API quota.

## 7. Đánh giá bảo mật theo threat model

Security review bắt đầu từ tài sản, actor, trust boundary và threat scenario, không chỉ từ danh sách checkbox.

### Tài sản cần bảo vệ

- Dữ liệu nghiệp vụ và dữ liệu cá nhân.
- Credential, token, certificate và encryption key.
- Image, package, source code và deployment artifact.
- Compute resource và control plane.
- Network path và service endpoint.
- Backup, log và audit record.
- Availability và integrity của workload.

### Threat modeling

Có thể dùng STRIDE hoặc phương pháp tương đương:

| Threat | Ví dụ trong compute architecture | Control cần đánh giá |
|---|---|---|
| Spoofing | Pod/VM giả danh service khác | Workload identity, mTLS, attestation |
| Tampering | Sửa image hoặc data volume | Image signing, integrity check, encryption |
| Repudiation | Không xác định ai đổi cấu hình | Audit log, immutable event, identity |
| Information disclosure | Secret hoặc data lộ qua log/egress | Secret manager, data classification, egress control |
| Denial of service | Burst làm cạn concurrency/connection | Rate limit, quota, backpressure, autoscaling cap |
| Elevation of privilege | Pod dùng node role quá rộng | Least privilege, RBAC, workload identity, isolation |

### Identity và access

- Mỗi workload có principal riêng phù hợp.
- Quyền theo least privilege.
- Không bake access key dài hạn vào image.
- Token có audience, expiry và rotation.
- Metadata endpoint được bảo vệ.
- Admin access qua JIT/break-glass và audit.
- RBAC/Cloud IAM được review định kỳ.
- Quyền backup và quyền xóa backup được tách.

### Network security

- Public/private path được mô tả.
- Security group/firewall chỉ mở port cần thiết.
- Network policy phân đoạn workload.
- Egress có kiểm soát.
- Private endpoint/DNS được cấu hình đúng.
- Ingress được bảo vệ bằng TLS/WAF/gateway khi phù hợp.
- On-premises/private connectivity có route và firewall hai chiều.

### Data protection

- Encryption at rest và in transit.
- Key management, rotation và separation of duties.
- Backup có retention, immutability hoặc delete protection khi cần.
- Data residency/retention được đáp ứng.
- Secret không xuất hiện trong log, image, manifest công khai hoặc ticket.

### Supply chain và runtime

- Image từ registry tin cậy, có provenance/signature.
- Dependency vulnerability scan.
- SBOM và version pinning theo policy.
- Patch OS/kernel/runtime.
- Non-root, seccomp, capabilities tối thiểu.
- Không dùng privileged mode nếu không có lý do.
- Admission policy ngăn workload không đạt baseline.

## 8. Đánh giá khả năng vận hành

Kiến trúc chỉ vận hành được nếu đội ngũ có thể deploy, quan sát, chẩn đoán, phục hồi và thay đổi nó trong điều kiện thực tế.

### Deployment và change management

Kiểm tra:

- IaC và cấu hình được version control.
- Build artifact bất biến và có provenance.
- Dev/staging/prod có promotion rõ ràng.
- Deployment có health gate và rollback.
- Database/schema migration có compatibility strategy.
- Canary/blue-green/rolling update phù hợp.
- Change có owner, approval và audit.
- Drift được phát hiện và xử lý.

### Observability

Ba trụ cột phổ biến:

- **Metrics:** SLI/SLO, saturation, capacity, quota, cost.
- **Logs:** sự kiện, lỗi, audit và context có correlation ID.
- **Traces:** đường đi của request qua service và dependency.

Cần thêm event và profiling khi phù hợp. Dashboard nên trả lời: người dùng có bị ảnh hưởng không, stage nào chậm, dependency nào lỗi, capacity còn bao nhiêu và chi phí thay đổi ra sao.

### Alert quality

Alert nên actionable, có severity, owner, runbook và điều kiện escalation. Tránh alert chỉ dựa trên CPU cao nếu đó là hành vi bình thường. Ưu tiên symptom-based alert như error budget burn, p95 latency, queue age, database connection saturation hoặc batch deadline slack.

### Runbook

Runbook cần nêu:

- Triệu chứng và phạm vi ảnh hưởng.
- Dashboard/log/event cần xem.
- Bước xác minh an toàn.
- Mitigation có thể thực hiện.
- Điều kiện dừng hoặc escalation.
- Cách rollback/recover.
- Cách xác nhận dịch vụ đã phục hồi.
- Owner và contact path.

### On-call và operational load

Đánh giá số lượng alert, incident, toil, manual approval, thời gian patch, thời gian restore và độ phức tạp của hệ thống. Một kiến trúc có thể đạt SLO nhưng cần nhiều thao tác thủ công hoặc phụ thuộc một chuyên gia duy nhất; đây là operational risk.

## 9. Backup, restore và disaster recovery

Review phải xác minh rằng dữ liệu và dịch vụ có thể phục hồi trong thời gian mục tiêu.

### Backup design

- Backup frequency phù hợp RPO.
- Application-consistent backup cho database khi cần.
- Snapshot và object versioning theo policy.
- Backup account/region tách biệt khi cần.
- Encryption key có thể truy cập trong recovery.
- Retention và deletion protection.
- Backup success monitoring.
- Restore test theo lịch.

### Restore evidence

Ghi nhận:

- Dataset/backup được dùng.
- Recovery point.
- Thời gian bắt đầu/kết thúc.
- RTO thực tế.
- Data loss/RPO thực tế.
- Lỗi và thao tác thủ công.
- Validation của application/data owner.

Backup job success không chứng minh restore thành công. Review cần ít nhất một lần restore test có bằng chứng và phạm vi dữ liệu đại diện.

### DR strategy

| Mô hình | Chi phí thường gặp | RTO tương đối | Cần kiểm tra |
|---|---|---|---|
| Backup and restore | Thấp hơn khi bình thường | Dài | Restore throughput, quota, key, IaC |
| Pilot light | Trung bình | Trung bình | Scale-up, dependency, DNS |
| Warm standby | Cao hơn | Ngắn hơn | Replication, capacity, failover |
| Active-active | Cao và phức tạp | Có thể rất ngắn | Data consistency, conflict, routing |

RTO thực tế gồm detect, decision, provision, restore/catch-up, validate và traffic switch. Không chỉ đo thời gian tạo VM.

### DR test

Diễn tập cần kiểm tra cả compute quota, storage quota, network/IP, identity, secret, certificate, DNS, load balancer và dependency ở region đích. Region dự phòng có thể thiếu capacity khi nhiều khách hàng cùng failover trong một sự cố lớn.

## 10. Đánh giá hiệu năng và khả năng mở rộng

Capacity review cần trả lời hệ thống xử lý được tải hiện tại và tải dự báo hay không.

### Performance evidence

- Benchmark với dữ liệu/tải đại diện.
- Load test ở mức bình thường, peak và burst.
- p50/p95/p99 latency.
- Throughput và error rate.
- CPU/memory/storage/network saturation.
- Queue age và processing lag.
- Database connection/query latency.
- Scale-out và scale-in time.
- Cold start, image pull và bootstrap duration.
- Performance khi mất một node/zone.

### Autoscaling

Kiểm tra metric trigger, min/max, cooldown, stabilization, quota, startup delay và dependency capacity. Autoscaler có thể tạo nhiều replica nhưng không tăng throughput nếu database hoặc external API đã bão hòa.

### Quota và provider capacity

Xác minh:

- Regional vCPU và instance family quota.
- GPU/accelerator quota.
- Subnet IP, ENI/NIC và load balancer quota.
- Serverless concurrency/request quota.
- Storage size, IOPS và snapshot quota.
- Database connection và service API limit.
- Reservation hoặc fallback instance family.

Quota increase không đồng nghĩa provider có capacity ở zone cụ thể. Nếu deadline quan trọng, cần reservation/fallback hoặc kế hoạch giảm tải.

## 11. Đánh giá chi phí và TCO

Cost review không chỉ so giá instance. Tổng chi phí sở hữu (TCO) gồm hạ tầng, managed service, network, storage, vận hành, bảo mật, support và chi phí sự cố.

### Cost categories

| Nhóm | Ví dụ |
|---|---|
| Compute | VM, container node, function, GPU, batch worker |
| Storage | Block volume, object storage, snapshot, backup, IOPS |
| Network | Egress, NAT, load balancer, cross-zone/region, VPN |
| Managed services | Database, cache, queue, search, API gateway |
| Security | KMS, secrets, WAF, scanning, SIEM |
| Observability | Log ingestion/retention, metrics, traces |
| Operations | On-call, patching, platform engineering, support |
| Reliability | Replicas, headroom, reservation, DR environment |
| Failure cost | Retry, downtime, data recovery, missed deadline |

### Cost model

Một mô hình tổng quát:

\[
TCO_{\text{period}} =
C_{\text{compute}} + C_{\text{storage}} + C_{\text{network}} +
C_{\text{managed}} + C_{\text{security}} + C_{\text{observability}} +
C_{\text{operations}} + C_{\text{DR}} + C_{\text{failure}}
\]

Dùng cùng một khoảng thời gian và cùng phạm vi workload khi so sánh hai phương án.

### Unit economics

Đo chi phí trên một đơn vị kết quả:

- Cost per 1,000 successful API requests.
- Cost per order processed.
- Cost per GB transformed.
- Cost per batch completed by deadline.
- Cost per training step hoặc inference.
- Cost per active tenant.

Cost per successful unit giúp nhận ra cấu hình rẻ theo giờ nhưng throughput thấp, retry nhiều hoặc giữ nhiều idle capacity.

### Idle và overprovisioning

Xem xét utilization theo giờ, node idle, reserved capacity không dùng, storage orphan, log retention và resource dev/test. Nhưng không loại bỏ headroom cần thiết cho SLO, N+1 hoặc DR chỉ để giảm bill ngắn hạn.

### Commitment và spot

- Commitment phù hợp baseline ổn định, cần kiểm tra coverage và utilization.
- Spot phù hợp workload có thể retry/checkpoint.
- On-demand phù hợp burst hoặc fallback.
- Reservation phù hợp khi cần capacity cụ thể và điều kiện provider bảo đảm.

So sánh cost per successful workload sau khi tính interruption, retry, provisioning và idle time.

## 12. Đánh giá rủi ro và trade-off

Không có kiến trúc tối ưu cho mọi tiêu chí. Review phải nêu rõ lợi ích, chi phí, rủi ro và điều kiện để trade-off được chấp nhận.

### Ví dụ trade-off

| Quyết định | Lợi ích | Chi phí/rủi ro | Điều kiện chấp nhận |
|---|---|---|---|
| Tăng replica qua zone | Availability cao hơn | Compute/network cost tăng | Dependency và data replication đủ |
| Serverless | Giảm host operations | Runtime/concurrency/vendor constraints | Workload phù hợp duration và trigger |
| Spot workers | Giá compute thấp | Interruption, retry, deadline risk | Checkpoint/idempotency và fallback |
| Private endpoint | Giảm public exposure | Endpoint/DNS cost và complexity | DNS, route và policy được quản lý |
| Managed database | Giảm toil vận hành DB | Service cost và control constraints | SLA, backup, export và exit plan rõ |
| Multi-region active-active | Failover nhanh | Data conflict, cost và complexity | Consistency model và test đầy đủ |
| Memory limit thấp | Bảo vệ node | OOM và retry | Working set được đo và headroom đủ |

### Risk register

Mỗi risk nên có:

- ID và mô tả.
- Asset/service bị ảnh hưởng.
- Threat hoặc failure scenario.
- Likelihood và impact.
- Existing control.
- Residual risk.
- Mitigation.
- Owner và due date.
- Evidence/verification.
- Risk acceptance owner nếu không xử lý.

Dùng thang likelihood/impact nhất quán. Không che giấu rủi ro nghiêm trọng bằng điểm trung bình cao ở các tiêu chí khác.

## 13. Scoring rubric cho architecture review

Rubric giúp so sánh phương án và chỉ ra khoảng trống. Điểm số không thay thế judgement hoặc mandatory control.

### Thang điểm

| Điểm | Mức | Ý nghĩa |
|---:|---|---|
| 0 | Không có | Không có thiết kế/control/evidence |
| 1 | Yếu | Có ý tưởng nhưng thiếu triển khai hoặc phụ thuộc thao tác thủ công |
| 2 | Một phần | Có control nhưng coverage hoặc kiểm thử còn hạn chế |
| 3 | Đạt | Đáp ứng yêu cầu, có evidence và owner |
| 4 | Tốt | Có kiểm thử định kỳ, tự động hóa và metric |
| 5 | Rất tốt | Có resilience/optimization liên tục, evidence production và cải tiến |

### Trọng số minh họa

| Nhóm | Trọng số | Tiêu chí |
|---|---:|---|
| SLO và resilience | 30% | Availability, latency, durability, RTO/RPO, scaling |
| Security | 25% | Identity, data, network, runtime, supply chain, audit |
| Operability | 25% | Deploy, observability, incident, backup/restore, ownership |
| Cost | 20% | TCO, unit economics, budget, utilization, forecast |

Điểm nhóm được tính bằng trung bình có trọng số của tiêu chí trong nhóm. Điểm tổng:

\[
Score_{\text{total}} = \sum_i Weight_i \times Score_i
\]

Nếu dùng thang 0–5, cần chuẩn hóa trọng số về tổng bằng 1. Ví dụ điểm SLO 3, security 4, operability 2, cost 3:

\[
Score = 0.30(3) + 0.25(4) + 0.25(2) + 0.20(3) = 3.0
\]

### Mandatory gates

Không cho phép điểm trung bình che lấp các lỗi nghiêm trọng. Có thể quy định không đạt review nếu:

- Không có backup/restore cho dữ liệu quan trọng.
- Credential quản trị hoặc secret dài hạn bị bake vào image.
- Không có owner cho incident hoặc production service.
- SLO quan trọng không đo được.
- RPO/RTO bắt buộc không có phương án đáp ứng.
- Có public exposure hoặc quyền truy cập vượt policy mà chưa được chấp nhận.
- DR region không có quota/capacity cho workload critical.

Kết quả review nên ghi cả score, mandatory gate, risk register và quyết định. Không dùng một ngưỡng điểm duy nhất để tự động approve mọi hệ thống.

## 14. Phương pháp đánh giá từng nhóm tiêu chí

### SLO và resilience

- SLI phản ánh user/business outcome.
- SLO có owner và cửa sổ đo.
- Error budget có policy.
- Load test xác nhận peak/p95.
- Failure domain và N+1 được tính.
- RPO/RTO được test.
- Dependency timeout/retry/circuit breaker hợp lý.
- Quota/capacity đủ cho failover.

### Security

- Threat model và data classification tồn tại.
- Identity theo least privilege.
- Secret/key rotation và revocation.
- TLS/mTLS và network segmentation.
- Image provenance và vulnerability management.
- Runtime hardening.
- Audit log và access review.
- Backup/data protection.

### Operability

- IaC/CI/CD và rollback.
- Observability và alert actionable.
- Runbook/on-call.
- Incident/postmortem.
- Patch/upgrade lifecycle.
- Backup restore/DR exercise.
- Ownership và support model.
- Toil và operational complexity.

### Cost

- TCO theo cùng phạm vi.
- Unit economics.
- Peak/headroom/DR cost.
- Commitment/spot suitability.
- Storage/network/observability charges.
- Budget guardrail và forecast.
- Idle/orphan resource.
- Cost owner và allocation.

## 15. Case study capstone: nền tảng xử lý đơn hàng

Một công ty bán lẻ triển khai nền tảng xử lý đơn hàng trên cloud. Hệ thống có API checkout, database giao dịch, worker xử lý sự kiện, dịch vụ tồn kho và pipeline báo cáo ban đêm.

### Yêu cầu nghiệp vụ

- Checkout hoạt động 24/7.
- Peak 2.500 request/second trong campaign.
- SLO availability 99,95% theo tháng.
- p95 latency checkout dưới 250 ms.
- Không mất transaction đã xác nhận.
- Database RPO tối đa 1 phút và RTO tối đa 30 phút.
- Báo cáo hoàn tất trước 05:30 với tỷ lệ đúng hạn 99%.
- Budget cloud production tối đa 30.000 USD/tháng.
- Dữ liệu đơn hàng chỉ được lưu ở các region đã được phê duyệt.
- Admin access phải có MFA và audit.

Đây là giả định bài tập. Khi áp dụng thực tế, cần xác nhận SLO, peak, budget và data residency với stakeholder.

### Kiến trúc hiện tại

- API chạy trên 6 VM general-purpose trong một region, autoscaling theo CPU.
- Một managed database primary và một read replica.
- Worker chạy container trên Kubernetes, scale theo queue depth.
- Function serverless gửi email và xử lý webhook.
- Object storage lưu hóa đơn và báo cáo.
- NAT gateway cung cấp outbound Internet.
- Monitoring tập trung CPU, memory và error log.
- Backup database hàng ngày, chưa có restore exercise gần đây.
- Một số service dùng chung cloud role.
- Không có quota dashboard; quota request chỉ được gửi khi deploy lỗi.
- FinOps xem tổng bill cuối tháng, chưa có cost per order.

### Bài toán review

Đánh giá kiến trúc theo bốn nhóm. Với mỗi finding, ghi evidence hiện có, khoảng trống, impact, likelihood, mitigation và owner.

#### SLO/resilience

- Sáu VM có đủ capacity khi một VM/zone mất không?
- Autoscaling theo CPU có phản ứng kịp request burst không?
- Database primary failover có đáp ứng RTO 30 phút và RPO 1 phút không?
- Read replica có bị dùng nhầm cho consistency-sensitive read không?
- Worker queue có backlog và deadline alert không?
- Email/webhook function có retry/idempotency/DLQ không?

#### Security

- Cloud role dùng chung có quyền rộng không?
- Database và object storage có private path/TLS không?
- Admin access có MFA, JIT và audit không?
- Secret có nằm trong environment/log/image không?
- Data region restriction có policy enforcement không?
- Webhook signature và replay protection có được kiểm tra không?

#### Operability

- Có SLO dashboard và error budget không?
- Có runbook cho database failover, queue backlog và quota exceeded không?
- Backup restore có được kiểm thử không?
- Có IaC và rollback cho schema/deployment không?
- On-call biết owner của từng dependency không?
- Monitoring có correlation ID và trace end-to-end không?

#### Cost

- Compute VM có idle hoặc shape chưa tối ưu không?
- Worker có thể dùng spot với checkpoint không?
- NAT egress và cross-zone transfer chiếm bao nhiêu?
- Database replica có phù hợp workload read không?
- Log retention và trace sampling có hợp lý không?
- Có unit cost per order và budget alert không?

## 16. Ví dụ findings và cách ưu tiên

| ID | Finding | Nhóm | Mức độ | Hành động |
|---|---|---|---|---|
| F-01 | Backup hàng ngày nhưng chưa có restore evidence | Operability/SLO | High | Thực hiện restore test, đo RPO/RTO |
| F-02 | Nhiều service dùng chung role rộng | Security | Critical | Tách workload identity và least privilege |
| F-03 | Autoscaling chỉ theo CPU | SLO | High | Bổ sung RPS, queue age, latency và capacity signal |
| F-04 | Không theo dõi quota runway | SLO/Operations | High | Quota inventory, forecast và alert |
| F-05 | Không có cost per order | Cost | Medium | Phân bổ cost theo tag và unit metric |
| F-06 | Retry webhook không có idempotency key | Security/Reliability | High | Signature validation, deduplication và DLQ |
| F-07 | NAT egress chưa được phân loại theo destination | Security/Cost | Medium | Egress policy và private endpoint review |

Mức độ chỉ là ví dụ. Severity phải dựa trên likelihood, impact, exposure và khả năng phát hiện/khôi phục. Finding có thể thuộc nhiều nhóm vì một vấn đề thường ảnh hưởng đồng thời SLO, security và cost.

### Ưu tiên theo risk

Một cách đơn giản là tính risk score:

\[
Risk = Likelihood \times Impact
\]

Dùng thang 1–5 cho mỗi yếu tố. Score chỉ giúp sắp xếp; các mandatory gate hoặc rủi ro pháp lý/security nghiêm trọng cần được xử lý theo policy dù score số học thấp.

## 17. Roadmap cải tiến kiến trúc

Không nên thực hiện mọi thay đổi cùng lúc. Chia roadmap theo risk reduction, dependency và effort.

### 0–30 ngày: đóng khoảng trống critical

- Tách role dùng chung cho workload quan trọng.
- Xác minh admin MFA/JIT/audit.
- Thực hiện restore test database.
- Tạo SLO dashboard và alert cho checkout.
- Bổ sung quota inventory và cảnh báo gần ngưỡng.
- Thêm idempotency/DLQ cho webhook quan trọng.

### 31–60 ngày: tăng khả năng vận hành

- Load test ở 2.500 RPS và failure scenario.
- Xác minh N+1/zone capacity.
- Bổ sung trace end-to-end.
- Viết runbook database failover và queue backlog.
- Thiết lập cost allocation và cost per order.
- Review NAT egress, private endpoint và log retention.

### 61–90 ngày: tối ưu và kiểm chứng

- Diễn tập DR và đo RPO/RTO.
- Điều chỉnh autoscaling theo latency, RPS và queue age.
- Benchmark worker pool và spot suitability.
- Tối ưu database connection pool.
- Kiểm thử patch/rolling upgrade.
- Đánh giá TCO và forecast growth 6–12 tháng.

Roadmap cần owner, due date, effort, expected risk reduction, dependency và evidence of completion. Không coi việc tạo ticket là hoàn thành mitigation.

## 18. Architecture decision record (ADR)

Mỗi quyết định quan trọng nên được ghi lại để người khác hiểu lý do và điều kiện của nó.

### Cấu trúc ADR

~~~markdown
# ADR-012: Chọn mô hình compute cho checkout API

## Status
Proposed | Accepted | Deprecated | Superseded

## Context
- Peak 2,500 RPS
- Availability SLO 99.95%
- p95 latency < 250 ms
- Team vận hành có năng lực Kubernetes và VM

## Decision
- Chạy API trên container platform đa zone
- Giữ database trên managed service
- Autoscale theo RPS/latency với CPU guardrail

## Alternatives
- VM autoscaling group
- Serverless container/function
- Managed application platform

## Consequences
- Tăng platform complexity
- Cần node quota và cluster operations
- Cải thiện rollout và resource isolation
- Cần DR/restore evidence

## Evidence
- Load test report
- Cost model
- Security review
- Failure exercise
~~~

ADR cần liên kết tới evidence và risk register. Khi giả định thay đổi, cập nhật ADR hoặc tạo ADR thay thế; không để quyết định cũ tiếp tục được hiểu là policy hiện hành.

## 19. Tính TCO minh họa cho hai phương án

Giả sử cùng phục vụ một workload trong một tháng:

| Khoản chi | Phương án A: VM tự quản lý | Phương án B: Container managed |
|---|---:|---:|
| Compute baseline/peak | 8.000 USD | 7.000 USD |
| Storage/database | 5.000 USD | 5.000 USD |
| Network/egress/NAT | 1.800 USD | 1.500 USD |
| Observability/security | 1.200 USD | 1.400 USD |
| Platform/support | 900 USD | 1.500 USD |
| Estimated operations effort | 2.500 USD | 1.800 USD |
| DR/headroom | 1.600 USD | 1.800 USD |
| **Tổng minh họa** | **21.000 USD** | **20.000 USD** |

Các số liệu chỉ phục vụ bài tập. Phương án B có hạ tầng và platform cost cao hơn ở một số dòng nhưng operations effort thấp hơn, tổng TCO minh họa thấp hơn. Tuy nhiên, nếu team chưa có Kubernetes/managed platform skills hoặc SLO không cần orchestration, chi phí chuyển đổi và rủi ro vận hành có thể làm phương án B không còn lợi thế.

### So sánh unit cost

Nếu phương án A xử lý 10 triệu order/tháng:

\[
CostPerOrder_A = \frac{21{,}000}{10{,}000{,}000}
= 0.0021\ USD
\]

Nếu phương án B xử lý 11 triệu order/tháng:

\[
CostPerOrder_B = \frac{20{,}000}{11{,}000{,}000}
\approx 0.00182\ USD
\]

Cần bảo đảm cả hai phương án đạt cùng SLO, security controls và data quality trước khi so unit cost. So sánh bill mà bỏ qua workload volume hoặc reliability là sai lệch.

## 20. Đánh giá kiến trúc theo vòng đời

Architecture review không nên chỉ chụp trạng thái tại ngày go-live. Cần xem các giai đoạn:

- Design: yêu cầu, threat model, capacity model và ADR.
- Build: image, IaC, dependency, scan và provenance.
- Deploy: approval, rollout, health gate và rollback.
- Run: SLO, monitoring, incident, quota và cost.
- Scale: forecast, autoscaling, reservation và dependency limits.
- Recover: backup, restore, DR, identity reissue và validation.
- Change: patch, upgrade, schema migration và deprecation.
- Retire: data retention, credential revocation và resource cleanup.

Một thiết kế có thể đạt SLO hôm nay nhưng không có quota runway hoặc patch process để duy trì SLO trong 12 tháng tới.

## 21. Đánh giá chi phí rủi ro và cost of failure

Cost of failure có thể bao gồm:

- Doanh thu mất do downtime.
- Transaction phải reconcile hoặc hoàn tiền.
- Nhân sự xử lý incident và overtime.
- Data recovery, reprocessing và support.
- SLA credit hoặc contractual penalty.
- Tổn hại uy tín và churn.
- Cơ hội bị mất khi launch chậm.

Không phải mọi tổn thất đều quy đổi chính xác thành tiền. Có thể dùng range hoặc qualitative impact, ghi giả định và tránh tạo độ chính xác giả.

### Expected annual loss

Một mô hình đơn giản:

\[
ExpectedLoss = ProbabilityOfEvent \times ImpactPerEvent
\]

Nếu một outage có xác suất 10%/năm và impact 100.000 USD, expected annual loss theo mô hình đơn giản là 10.000 USD. Một control hoặc capacity investment 6.000 USD/năm có thể hợp lý nếu giảm xác suất/impact đủ lớn. Cần xem nhiều kịch bản và tránh coi xác suất độc lập khi chúng có tương quan.

## 22. Quy trình architecture review từ đầu đến cuối

1. **Intake:** xác định service owner, mục tiêu review, phạm vi và thời hạn.
2. **Requirements:** thu thập business criticality, SLO, RPO/RTO, budget và compliance.
3. **Discovery:** lấy sơ đồ, inventory, config, dependency và workload profile.
4. **Evidence collection:** dashboard, test, policy, audit, restore và cost data.
5. **Evaluation:** chấm SLO, security, operability và cost theo rubric.
6. **Threat/failure analysis:** phân tích attack path, failure domain và dependency.
7. **Findings:** ghi gap, severity, evidence, impact, owner và mitigation.
8. **Trade-off review:** so sánh lựa chọn và ghi ADR.
9. **Decision:** approve, approve with conditions hoặc reject/defer.
10. **Roadmap:** tạo action, owner, due date và evidence hoàn tất.
11. **Follow-up:** kiểm tra mitigation và cập nhật score.
12. **Re-review:** thực hiện khi workload, region, data class, SLO hoặc architecture thay đổi đáng kể.

### Decision outcomes

- **Approve:** đáp ứng mandatory gate và risk nằm trong appetite.
- **Approve with conditions:** còn action có deadline, owner và compensating control.
- **Defer:** thiếu evidence hoặc dependency cần làm rõ.
- **Reject:** vi phạm mandatory requirement hoặc residual risk không chấp nhận được.

Người phê duyệt phải có authority phù hợp. Reviewer không tự chấp nhận risk thay cho business/security owner.

## 23. Những lỗi thường gặp khi đánh giá kiến trúc

**Chấm điểm theo cảm giác.** Dùng evidence, rubric và owner cho từng kết luận.

**Chỉ xem sơ đồ thiết kế.** So sánh với cấu hình và telemetry đang chạy.

**Dùng CPU utilization làm đại diện SLO.** Đo latency, success rate, correctness và batch deadline.

**Coi multi-zone là HA đầy đủ.** Kiểm tra database, DNS, NAT, identity, quota và surviving capacity.

**Coi backup job thành công là recovery sẵn sàng.** Thực hiện restore test và đo RTO/RPO.

**Chỉ kiểm tra IAM role mà bỏ qua network/data.** Threat model phải bao gồm identity, network, storage, runtime và supply chain.

**So sánh compute price thay vì TCO.** Tính cả operations, egress, logging, DR, retries và failure cost.

**Đưa mọi tiêu chí vào điểm trung bình.** Dùng mandatory gates cho security, data protection và critical SLO.

**Không có owner và deadline cho findings.** Một review không có action tracking sẽ không làm giảm rủi ro.

**Không re-review sau thay đổi lớn.** Thêm region, workload, data class hoặc dependency mới có thể làm thay đổi toàn bộ đánh giá.

## 24. Template báo cáo architecture review

~~~markdown
# Architecture Review Report

## 1. Executive decision
- Service:
- Owner:
- Review date:
- Outcome: Approve / Conditional / Defer / Reject
- Overall score:
- Mandatory gates:

## 2. Scope and assumptions
- Workloads:
- Regions/accounts:
- Dependencies:
- Data classification:
- SLO/RPO/RTO:
- Budget and growth horizon:

## 3. Architecture summary
- Compute model:
- Network:
- Storage/data:
- Identity:
- Deployment/operations:

## 4. Scorecard
| Domain | Weight | Score | Evidence | Main gap |
|---|---:|---:|---|---|
| SLO/resilience | | | | |
| Security | | | | |
| Operability | | | | |
| Cost | | | | |

## 5. Findings and risks
| ID | Severity | Finding | Evidence | Owner | Due date |
|---|---|---|---|---|---|

## 6. Decisions and trade-offs
- Alternatives:
- Selected option:
- Consequences:
- ADR links:

## 7. Roadmap
- Immediate:
- 30 days:
- 60 days:
- 90 days:

## 8. Residual risk acceptance
- Risk:
- Business impact:
- Compensating control:
- Risk owner:
- Review date:
~~~

Báo cáo nên ngắn gọn ở phần quyết định và đủ chi tiết ở evidence/findings để người khác kiểm chứng. Không đưa secret, credential hoặc dữ liệu nhạy cảm vào báo cáo.

## 25. Capstone exercise: thực hiện một architecture review hoàn chỉnh

Dùng case study nền tảng xử lý đơn hàng ở mục 15 hoặc chọn một hệ thống tương đương đã được phép sử dụng.

### Deliverables

1. Architecture diagram có trust boundary, data flow và failure domain.
2. Workload profile và growth forecast 6–12 tháng.
3. SLO/SLI table, error budget và RPO/RTO.
4. Threat model có asset, actor, attack path và control.
5. Operability review gồm deployment, monitoring, on-call, runbook, backup/restore và DR.
6. Capacity model gồm CPU, memory, storage, network, quota và headroom.
7. TCO và cost per successful unit.
8. Scorecard có evidence và mandatory gate.
9. Risk register và ít nhất ba ADR hoặc quyết định kiến trúc.
10. Roadmap 30/60/90 ngày với owner và acceptance evidence.

### Acceptance criteria

- Mỗi SLO có SLI, query/measurement method, owner và cửa sổ.
- Có test hoặc evidence cho peak load và một failure scenario.
- Mỗi security finding gắn với asset/threat/control.
- Restore hoặc DR có kết quả đo, không chỉ policy.
- Cost model có compute, storage, network, managed service và operations.
- Quota/provider capacity được phân biệt.
- Mỗi high/critical finding có owner và due date.
- Các mandatory gate được quyết định rõ.
- Có ghi giả định, limitation và residual risk.
- Kết luận có thể truy ngược đến evidence.

### Gợi ý cách trình bày

- 1 trang executive summary.
- 1 sơ đồ kiến trúc.
- 1 scorecard.
- 1 risk register.
- 1 TCO table.
- 1 roadmap.
- Appendix cho evidence và test result.

## 26. Checklist đánh giá kiến trúc

### SLO và resilience

- [ ] SLI đo kết quả người dùng/nghiệp vụ.
- [ ] SLO có owner, cửa sổ và error budget policy.
- [ ] p95/p99 và dependency latency được đo.
- [ ] Peak load và scale-out được benchmark.
- [ ] Failure domain và N+1 được tính.
- [ ] RPO/RTO được kiểm thử.
- [ ] Retry, timeout, circuit breaker và idempotency phù hợp.
- [ ] Quota/capacity đủ cho peak và DR.

### Security

- [ ] Có data classification và threat model.
- [ ] Workload identity và least privilege.
- [ ] Secret/key/certificate lifecycle được quản lý.
- [ ] Network segmentation và egress control.
- [ ] Encryption at rest/in transit.
- [ ] Image provenance, vulnerability scan và patching.
- [ ] Runtime hardening và admission policy.
- [ ] Audit log, admin access và backup protection.

### Operability

- [ ] IaC, CI/CD, rollout và rollback.
- [ ] Metrics/logs/traces và actionable alert.
- [ ] Runbook, on-call và escalation.
- [ ] Incident/postmortem và change management.
- [ ] Backup/restore và DR exercise.
- [ ] Ownership rõ cho service/dependency.
- [ ] Operational toil và skill requirement được đánh giá.
- [ ] Có re-review trigger khi architecture thay đổi.

### Cost

- [ ] TCO theo cùng phạm vi và thời gian.
- [ ] Cost per successful unit.
- [ ] Compute/storage/network/managed-service costs.
- [ ] Logging/security/operations/DR costs.
- [ ] Headroom và reservation được giải thích.
- [ ] Spot/commitment phù hợp workload.
- [ ] Budget alert và forecast.
- [ ] Cost owner, allocation tag và review cadence.

### Review governance

- [ ] Có evidence register.
- [ ] Rubric và mandatory gates được áp dụng nhất quán.
- [ ] Findings có severity, owner và due date.
- [ ] ADR ghi lại alternatives và consequences.
- [ ] Residual risk có người có thẩm quyền chấp nhận.
- [ ] Roadmap có acceptance evidence.

## 27. Tự kiểm tra

1. SLI, SLO và SLA khác nhau như thế nào?
2. Vì sao CPU utilization không đủ để chứng minh SLO availability hoặc latency?
3. Error budget được tính và sử dụng để điều khiển release ra sao?
4. Phân biệt availability, durability, recoverability, RPO và RTO.
5. Vì sao multi-zone deployment vẫn có thể là single point of failure?
6. Threat model giúp review compute architecture như thế nào?
7. Workload identity, network policy và encryption giải quyết các lớp rủi ro nào?
8. Một runbook tốt cần những thông tin gì để người trực xử lý incident?
9. Vì sao backup success không chứng minh restore readiness?
10. TCO khác compute bill như thế nào?
11. Vì sao cần cost per successful unit khi so sánh VM, container và serverless?
12. Mandatory gate ngăn điểm trung bình che giấu rủi ro nghiêm trọng ra sao?
13. Evidence E1 khác E3 như thế nào?
14. Khi nào cần re-review kiến trúc?
15. Hãy đánh giá case study checkout theo bốn nhóm SLO, security, operability và cost; nêu ba finding ưu tiên, evidence cần bổ sung và roadmap 90 ngày.

Một architecture review có giá trị khi kết luận dựa trên yêu cầu và evidence, chỉ rõ trade-off, xác định rủi ro còn lại và chuyển thành hành động có owner. SLO cho biết chất lượng cần đạt; security xác định workload và dữ liệu được bảo vệ ra sao; operability chứng minh đội ngũ có thể triển khai, quan sát và phục hồi; cost cho biết kiến trúc có bền vững về tài chính khi tăng trưởng hay không. Đánh giá đồng thời bốn góc nhìn giúp chọn kiến trúc compute phù hợp với nhu cầu hiện tại và khả năng phát triển lâu dài.
