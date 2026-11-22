# So sánh chi phí dịch vụ được quản lý với chi phí tự vận hành

## 1. Vì sao không thể chỉ so sánh giá dịch vụ?

Khi thiết kế kiến trúc cloud, đội dự án thường cân nhắc dùng dịch vụ được quản lý (managed service) hay tự vận hành phần mềm trên VM, container hoặc Kubernetes. Managed service thường thu phí cao hơn cho từng đơn vị tài nguyên hoặc request, nhưng nhà cung cấp đảm nhận một phần công việc như provisioning, patching, backup, failover và vận hành control plane. Tự vận hành có thể giảm một số khoản phí dịch vụ, đồng thời chuyển trách nhiệm triển khai, cập nhật, bảo mật, giám sát và xử lý sự cố sang đội nội bộ.

So sánh giá theo giờ của một database managed với giá VM chạy database sẽ bỏ qua phần lớn chi phí. Cần so **Total Cost of Ownership (TCO – tổng chi phí sở hữu)** trong cùng một phạm vi workload, mức dịch vụ, thời gian đánh giá và nghĩa vụ vận hành.

TCO nên bao gồm:

- **Chi phí trực tiếp:** compute, storage, network, license, request, backup, replication và support.
- **Chi phí nhân lực:** thiết kế, triển khai, patching, on-call, incident response, upgrade và capacity planning.
- **Chi phí công cụ:** monitoring, security scanning, backup tooling, orchestration, automation và observability.
- **Chi phí rủi ro:** downtime, data loss, security incident, SLA credits và recovery.
- **Chi phí linh hoạt:** khả năng scale up/down, thay đổi region, migrate và tránh lock-in.
- **Chi phí cơ hội:** thời gian đội kỹ thuật dành cho hạ tầng thay vì tính năng và năng lực tạo giá trị cho sản phẩm.

Trong module **CLOUD_ARCHITECTURE**, chương **Chi phí và bền vững** xem quyết định managed hay self-managed như một đánh đổi giữa chi phí, trách nhiệm vận hành, độ tin cậy, bảo mật, khả năng mở rộng và hiệu quả sử dụng tài nguyên.

Sau bài học, người học có thể:

1. Phân biệt managed service, self-managed và các mức dịch vụ trung gian.
2. Xây dựng TCO trên cùng workload, SLO, capacity và thời gian đánh giá.
3. Tính chi phí trực tiếp, nhân lực, tooling, dự phòng và rủi ro.
4. Ước lượng điểm hòa vốn theo quy mô sử dụng và chi phí vận hành.
5. So sánh trách nhiệm bảo mật, patching, backup, HA và compliance.
6. Đánh giá elasticity, utilization, lock-in và khả năng chuyển đổi.
7. Chọn mô hình theo workload, kỹ năng đội ngũ và giá trị kinh doanh.
8. Lập kế hoạch migration, thử nghiệm và review chi phí sau triển khai.

## 2. Managed service và self-managed là gì?

### 2.1. Dịch vụ được quản lý

Managed service là dịch vụ mà nhà cung cấp chịu trách nhiệm vận hành một phần hoặc phần lớn nền tảng bên dưới. Khách hàng cấu hình và sử dụng dịch vụ qua API, console hoặc control plane.

Ví dụ:
- Managed relational database.
- Managed Kubernetes control plane.
- Managed message broker.
- Managed cache.
- Managed object storage.
- Managed search/analytics engine.
- Managed identity hoặc observability platform.

Nhà cung cấp có thể đảm nhận phần cứng, host OS, control plane, patching hoặc backup tùy dịch vụ và tier. Khách hàng vẫn thường chịu trách nhiệm về dữ liệu, IAM, network access, cấu hình, ứng dụng, quota, key policy và cách sử dụng dịch vụ.

### 2.2. Tự vận hành

Self-managed nghĩa là tổ chức tự triển khai và vận hành software trên compute/storage/network do mình kiểm soát. Có thể chạy trên VM, bare metal, container platform hoặc Kubernetes.

Ví dụ:
- Cài PostgreSQL trên VM và tự quản lý replication/backup.
- Chạy Kafka cluster trên Kubernetes.
- Vận hành Redis cluster.
- Chạy Elasticsearch/OpenSearch cluster.
- Tự quản lý ingress, certificate, monitoring và upgrade.

Self-managed không có nghĩa tự sản xuất phần cứng. Cloud provider vẫn vận hành datacenter, physical network và hypervisor; tổ chức nhận thêm trách nhiệm ở tầng software/platform.

### 2.3. Mô hình trung gian

Thực tế có phổ lựa chọn:

| Mô hình | Nhà cung cấp đảm nhận | Đội nội bộ đảm nhận |
| --- | --- | --- |
| Fully managed | Hạ tầng và phần lớn platform operations | Data, access, config, workload |
| Managed control plane | Control plane/coordination | Worker nodes, add-ons, workloads |
| Hosted software | Host runtime hoặc phần cứng tùy hợp đồng | App config, data, upgrades ở mức được hỗ trợ |
| Self-managed on cloud | Physical cloud infrastructure | OS, software, HA, backup, patch, monitoring |
| Self-hosted on-prem | Phần cứng có thể do tổ chức quản lý | Hầu hết stack từ datacenter tới application |

Tên gọi không đủ để xác định trách nhiệm. Phải đọc service boundary, SLA, maintenance policy, support plan và shared responsibility model của dịch vụ cụ thể.

## 3. So sánh trách nhiệm vận hành

| Hoạt động | Managed service | Self-managed |
| --- | --- | --- |
| Datacenter/hardware | Provider | Cloud provider hoặc đội hạ tầng tùy môi trường |
| Host/hypervisor | Provider | Thường provider |
| OS patching | Thường provider ở service layer được quản lý | Đội nội bộ |
| Software version/engine upgrade | Provider hỗ trợ theo policy; khách hàng chọn lịch/tier tùy dịch vụ | Đội nội bộ lập kế hoạch và thực hiện |
| Control plane | Thường provider | Đội nội bộ nếu tự dựng |
| Data model/schema | Đội ứng dụng | Đội ứng dụng |
| IAM/network configuration | Chia sẻ trách nhiệm | Chủ yếu đội nội bộ |
| Backup policy | Dịch vụ có thể cung cấp cơ chế; khách hàng cấu hình/kiểm tra | Đội nội bộ thiết kế và vận hành |
| Restore validation | Khách hàng phải kiểm chứng yêu cầu nghiệp vụ | Đội nội bộ |
| Monitoring/SLO | Provider có telemetry nền; khách hàng theo dõi workload | Đội nội bộ xây dựng end-to-end |
| Incident response | Provider xử lý phần dịch vụ; khách hàng xử lý workload/config | Đội nội bộ xử lý phần lớn stack |
| Capacity/quota | Provider cấp capacity theo quota và giới hạn dịch vụ | Đội nội bộ sizing và scaling workload |

Managed service chuyển giao một phần công việc, không xóa trách nhiệm của khách hàng. Ví dụ provider có thể tự backup database, nhưng khách hàng vẫn phải xác minh retention, quyền truy cập, RPO/RTO và khả năng restore độc lập.

## 4. Xác định phạm vi so sánh công bằng

Hai phương án chỉ có thể so sánh khi đáp ứng cùng mục tiêu.

Trước khi tính TCO, ghi rõ:
- Workload: requests/s, transactions/s, data size, growth và traffic mix.
- Availability/SLO: uptime, latency, error budget và maintenance window.
- RPO/RTO: mức mất dữ liệu và thời gian phục hồi.
- Security: encryption, identity, audit, key management và network isolation.
- Compliance: data residency, retention, evidence và certification scope.
- Capacity: peak, burst, headroom, HA replicas và DR.
- Environment: production, staging, development và non-production.
- Time horizon: 1 năm, 3 năm hoặc vòng đời dự kiến.
- Region, currency, pricing tier và support level.

Không so một database managed multi-AZ có backup, monitoring và support với một VM đơn lẻ không có redundancy. Đó là hai mức dịch vụ khác nhau.

### 4.1. Baseline service level

Có thể lập bảng requirement tối thiểu:

| Requirement | Baseline cần đạt |
| --- | --- |
| Throughput | Đủ design peak và growth |
| Latency | Đạt p95/p99 mục tiêu |
| Availability | Đúng SLO đã thỏa thuận |
| Recovery | RPO/RTO đã kiểm chứng |
| Security | Encryption, IAM, audit, patching |
| Operations | Monitoring, on-call, runbook |
| Compliance | Data location, retention, evidence |
| Capacity | N+1 hoặc failure scenario đã xác định |

Nếu một phương án không đáp ứng baseline, cần tính chi phí bổ sung để đạt baseline hoặc ghi rõ residual risk. Không dùng giá thấp hơn để che việc service level thấp hơn.

## 5. Mô hình TCO tổng quát

TCO trong một khoảng thời gian T:

```text
TCO(T) =
    Direct infrastructure cost
  + Managed service / license cost
  + Network and data transfer
  + Backup and disaster recovery
  + Observability and security tooling
  + Engineering and operations labor
  + Support and training
  + Migration and exit cost
  + Expected incident / risk cost
  - Discounts and reusable value
```

Đối với self-managed, direct infrastructure có thể thấp hơn nhưng engineering/operations labor cao hơn. Với managed service, service premium có thể lớn hơn nhưng một số operational tasks được chuyển sang provider.

### 5.1. Phân loại chi phí

| Nhóm | Ví dụ | Dễ bị bỏ sót? |
| --- | --- | --- |
| Compute | VM, CPU, memory, managed node | Có |
| Storage | Capacity, IOPS, throughput, snapshots | Có |
| Network | NAT, load balancer, egress, cross-zone transfer | Rất dễ |
| License | Commercial engine, OS, add-on | Có |
| HA/DR | Replicas, standby, cross-region copy | Có |
| Backup | Retention, restore, archive retrieval | Rất dễ |
| Observability | Logs, metrics, traces, index | Rất dễ |
| Security | KMS, secrets, scanning, SIEM | Có |
| Labor | SRE, DBRE, platform engineer, on-call | Rất dễ |
| Support | Provider plan, vendor support, training | Có |
| Migration | Data transfer, refactor, dual run, testing | Có |
| Exit | Export, conversion, replatforming | Thường bị bỏ qua |

## 6. Chi phí trực tiếp của managed service

Managed service có thể tính phí theo:
- Instance size hoặc vCPU/memory.
- Provisioned IOPS/throughput.
- Storage capacity và snapshots.
- Request/operation count.
- Data processed hoặc data scanned.
- Message/partition/throughput unit.
- Data transfer và cross-region replication.
- License/edition/tier.
- Backup retention và restore operation.
- Minimum capacity hoặc idle resources.
- Support plan và enterprise feature.

Một số dịch vụ thu phí riêng cho control plane, worker, node hoặc data plane. Một số tính phí theo giờ, một số theo request/GB hoặc capacity reservation. Cần dùng pricing calculator và usage profile của provider cụ thể; không có một đơn giá managed service chung.

### 6.1. Chi phí premium đổi lấy công việc nào?

Không nên xem toàn bộ phần chênh lệch giá là “phí tiện lợi”. Hãy ghi cụ thể dịch vụ thay đội nội bộ thực hiện việc gì:

| Năng lực managed | Công việc có thể được provider đảm nhận |
| --- | --- |
| Provisioning | Cài đặt, cấu hình nền tảng, tạo endpoint |
| Patching | Cập nhật host/engine theo phạm vi dịch vụ |
| Backup | Lập recovery point và lưu trữ theo policy |
| Failover | Health detection, promotion hoặc endpoint change |
| Scaling | Capacity operation theo tier/limit |
| Control plane | API, scheduler, orchestration và service management |
| Monitoring nền | Health signals và service-level telemetry |
| Support | Escalation tới đội vận hành dịch vụ |

Đánh giá từng mục theo service description và SLA. Nếu provider không đảm nhận một công việc, vẫn cần tính phần nhân lực nội bộ.

## 7. Chi phí trực tiếp của self-managed

Self-managed có thể dùng compute phổ thông và phần mềm mã nguồn mở, nhưng cần tính toàn bộ stack:

- VM/bare metal, disk, network và load balancing.
- OS license hoặc subscription.
- Software license và commercial support nếu có.
- Orchestration/control plane.
- Database/broker/cache replicas.
- Backup, snapshots, log shipping và archive.
- Monitoring, metrics, logs, tracing và alerting.
- Security scanning, vulnerability management và secret service.
- Build/deploy automation và configuration management.
- Staging/performance environment.
- DR capacity và failover environment.
- Data transfer, egress và recovery traffic.

### 7.1. Tài nguyên dự phòng và utilization

Nếu self-managed cluster được sizing để chịu mất một node hoặc AZ, một phần capacity phải luôn được giữ để tiếp nhận workload khi sự cố. Capacity nhàn rỗi vẫn có chi phí.

Nếu managed service đã tính HA vào tier hoặc thu riêng cho standby/replica, cần so tổng capacity tương đương. Không cộng spare capacity ở một phương án nhưng quên nó ở phương án kia.

### 7.2. Phần mềm miễn phí không có nghĩa vận hành miễn phí

Phần mềm open source có thể không cần license, nhưng đội vẫn phải cài, nâng cấp, vá lỗ hổng, xử lý CVE, backup, restore, benchmark và on-call. Community support cũng có thời gian tìm hiểu và xử lý khác với contractual support.

Chi phí labor thường lặp lại hàng tháng và tăng theo complexity, số cluster, số region, số version và mức độ tùy biến.

## 8. Chi phí nhân lực và vận hành

Labor là một cost driver lớn, đặc biệt với self-managed platform. Cần ước lượng theo hoạt động thực tế:

| Hoạt động | Thời gian cần tính |
| --- | --- |
| Initial architecture/build | Thiết kế, automation và hardening ban đầu |
| Provisioning/onboarding | Tạo môi trường, cấp quyền, cấu hình |
| Patching/upgrades | Lên lịch, test, deploy, rollback |
| Backup/restore | Theo dõi backup, restore drill và remediation |
| Monitoring/on-call | Alert triage, incident response, postmortem |
| Capacity planning | Forecast, benchmark, scale và rebalancing |
| Security/compliance | Scan, audit evidence, access review |
| Vendor/provider coordination | Case handling, escalation, maintenance |
| Documentation/training | Runbook, handover, knowledge transfer |

### 8.1. Công thức labor cost

```text
Annual labor cost =
    Σ (hours per activity per year × fully loaded hourly cost)
```

Fully loaded hourly cost có thể bao gồm salary, benefits, overhead và chi phí quản lý theo accounting model của tổ chức.

Ví dụ giả định:
- 30 giờ/tháng cho patching, upgrades và maintenance.
- 20 giờ/tháng cho on-call và incident follow-up.
- 15 giờ/tháng cho backup, restore và capacity tasks.
- Fully loaded labor cost 50 USD/giờ.

```text
Monthly hours = 30 + 20 + 15 = 65 hours
Monthly labor = 65 × 50 = 3,250 USD
Annual labor = 3,250 × 12 = 39,000 USD
```

Đây là ví dụ tính toán, không phải mức lương hoặc benchmark ngành. Cần dùng actual staffing cost, workload và thời gian đo của tổ chức.

### 8.2. Không tính cùng một giờ lao động hai lần

Nếu giờ on-call đã nằm trong fully loaded cost hoặc team allocation, tránh cộng trùng vào một dòng khác. Ghi rõ FTE, hours và rate. Với đội làm nhiều workload, phân bổ theo usage/effort có thể thực tế hơn gán toàn bộ chi phí cho một service.

### 8.3. Opportunity cost

Một platform engineer dành 20% thời gian vận hành broker self-managed không còn dùng thời gian đó để cải thiện deployment platform hoặc developer productivity. Có thể thể hiện opportunity cost qua capacity/FTE và roadmap value, nhưng tránh định giá quá chính xác khi chưa có phương pháp nội bộ.

## 9. Security, compliance và risk cost

Managed service có thể cung cấp patching, encryption integration, audit hooks hoặc certification evidence; nhưng khách hàng vẫn phải cấu hình và sử dụng đúng. Self-managed cho nhiều quyền tùy biến, đồng thời đội phải chịu trách nhiệm kiểm soát toàn stack.

Các khoản cần tính:
- Vulnerability scanning và patch remediation.
- IAM review, secret rotation và privileged access.
- Encryption/KMS key operations.
- Network segmentation và egress controls.
- Audit logging, retention và SIEM ingestion.
- Backup immutability và restore validation.
- Compliance assessment và evidence collection.
- Incident response, forensic và recovery.
- Contract/SLA review và provider risk assessment.

### 9.1. Shared responsibility model

Với mỗi control, ghi rõ ai chịu trách nhiệm:
- Provider: physical security, host infrastructure hoặc managed control plane theo dịch vụ.
- Customer: identity, data, access policy, application config và nhiều phần network/security.
- Shared: patch windows, key management, backup policy, monitoring, incident coordination.

Không giả định managed đồng nghĩa provider chịu mọi trách nhiệm compliance. Kiểm tra service scope, region, edition, contract và audit report.

### 9.2. Expected risk cost

Có thể dùng mô hình đơn giản:

```text
Expected annual incident cost =
    Σ (scenario probability × business impact)

Risk-adjusted TCO =
    operating TCO + expected incident cost
```

Xác suất và impact thường không chắc chắn. Dùng các scenario như region loss, unpatched vulnerability, failed restore và operator error; làm sensitivity analysis thay vì đưa ra một con số duy nhất có vẻ chính xác.

## 10. Availability, backup và disaster recovery

Một lựa chọn managed có thể cung cấp multi-AZ, automated backup và failover, nhưng cần biết:
- HA có nằm trong tier mặc định hay tính riêng?
- Backup retention và PITR hỗ trợ tới đâu?
- Replica đồng bộ hay bất đồng bộ?
- RPO/RTO được cam kết hay chỉ là mục tiêu?
- Restore có cần tạo resource mới?
- Failover có tự động hay manual?
- Cross-region recovery có được hỗ trợ?
- Có giới hạn quota hoặc service dependency?
- Backup có thể xóa cùng account/security principal không?

Với self-managed, cần tự tính compute dự phòng, replica, backup storage, transfer, monitoring, runbook và nhân lực diễn tập.

Không so managed multi-AZ với self-managed single-node. Cần so cùng failure scenario và evidence restore/failover.

### 10.1. Giá trị của automation

Một dịch vụ managed có thể giảm toil nhưng vẫn cần:
- Load test.
- Backup restore test.
- Failover game day.
- Application-level health check.
- Data integrity validation.
- Reconciliation sau sự cố.

Nếu những công việc này vẫn nằm ở phía khách hàng, không xóa chúng khỏi TCO.

## 11. Elasticity và utilization

Managed service thường cho phép tăng/giảm capacity qua API hoặc autoscaling, nhưng có thể có minimum tier, scaling delay, quota và phí burst. Self-managed có thể tối ưu utilization bằng bin packing và shared cluster, nhưng phải duy trì headroom và capacity planning.

Các chỉ số:
- Average và peak utilization.
- Idle/reserved capacity.
- Scaling frequency và time-to-capacity.
- Resource fragmentation.
- Cost per request/transaction.
- Cost per GB stored/processed.
- Capacity headroom cho failure scenario.

### 11.1. Burst và variable workloads

Với workload bursty, managed serverless/elastic service có thể tiết kiệm nhờ trả theo usage. Tuy nhiên cần kiểm tra request pricing, cold start, burst quota, minimum charge và egress.

Self-managed có thể rẻ khi workload ổn định, utilization cao và đội tối ưu được resource. Nhưng nếu phải giữ cluster lớn cho peak ngắn, phần idle capacity có thể làm TCO cao.

## 12. Cost break-even giữa managed và self-managed

Giả sử:
- M là monthly managed service fee theo workload.
- I là monthly self-managed infrastructure/license/tooling cost.
- O là monthly self-managed operations labor.
- G là monthly managed-specific tooling/network/support cost chưa nằm trong M.
- F là fixed setup/migration cost phân bổ theo thời gian nếu cần.

Khi đó:

```text
Managed monthly TCO = M + G + Managed labor
Self-managed monthly TCO = I + O

Managed is cheaper when:
M + G + Managed labor < I + O
```

Nếu phần lớn managed labor và self-managed labor không giống nhau, tính riêng theo activity matrix thay vì giả định bằng 0.

### 12.1. Điểm hòa vốn minh họa

Giả sử:
- Managed service fee: 4.500 USD/tháng.
- Managed operations effort: 10 giờ/tháng × 50 USD = 500 USD.
- Self-managed infrastructure, license và tooling: 2.500 USD/tháng.
- Self-managed operations: 65 giờ/tháng × 50 USD = 3.250 USD.

```text
Managed TCO = 4,500 + 500 = 5,000 USD/month
Self-managed TCO = 2,500 + 3,250 = 5,750 USD/month

Managed savings = 750 USD/month
Annual difference = 9,000 USD/year
```

Trong ví dụ này managed có hóa đơn dịch vụ cao hơn nhưng tổng TCO thấp hơn do labor. Kết quả sẽ thay đổi nếu tổ chức đã có đội vận hành và năng lực automation dùng chung; khi đó phần incremental labor có thể thấp hơn.

### 12.2. Tính ngược quy mô hòa vốn

Nếu managed fee tăng theo usage còn self-managed infra tăng theo các bước capacity, break-even không nhất thiết là một đường thẳng. Có thể mô hình hóa:

```text
TCO_managed(x) = fixed_managed + unit_rate_managed × x
TCO_self(x) = fixed_self + tiered_infra(x) + ops(x)

Break-even occurs where:
TCO_managed(x) = TCO_self(x)
```

x có thể là transactions/month, GB processed, active connections hoặc throughput unit. Với tiered infrastructure, autoscaling và labor step changes, cần tính theo nhiều workload scenarios.

## 13. Quy mô, độ ổn định và kỹ năng đội ngũ

Các điều kiện thường nghiêng về managed:
- Workload nhỏ/vừa hoặc tăng trưởng chưa chắc chắn.
- Traffic biến động, cần elasticity.
- Đội ngũ ít người hoặc thiếu chuyên môn vận hành database/broker.
- Time-to-market quan trọng.
- Cần HA/backup/patching baseline nhanh.
- Giá trị sản phẩm nằm ở logic nghiệp vụ hơn là platform software.

Các điều kiện có thể nghiêng về self-managed:
- Workload lớn, ổn định và utilization cao.
- Có đội platform/SRE/DBRE chuyên sâu.
- Cần tùy biến sâu kernel, runtime, plugin hoặc topology.
- Có yêu cầu portability hoặc chạy hybrid/on-prem.
- Managed service có giới hạn/feature không phù hợp.
- License/provider pricing làm cost tăng mạnh ở quy mô lớn.

Đây là tín hiệu để đánh giá, không phải quy tắc tự động. Workload lớn vẫn có thể rẻ hơn khi dùng managed nếu provider có economies of scale; workload nhỏ vẫn có thể cần self-managed vì yêu cầu đặc thù.

## 14. Vendor lock-in và chi phí chuyển đổi

Managed service có thể tạo lock-in qua:
- API/configuration độc quyền.
- Data format hoặc backup format riêng.
- Extension/plugin khác biệt.
- IAM và network integration riêng.
- Monitoring/alert format.
- Proprietary feature như serverless scaling hoặc global replication.
- Contract, support và pricing commitment.

Self-managed có thể tăng portability nếu dùng open source và standard protocol, nhưng không tự động portable. Storage layout, operator, Helm chart, custom plugin, data migration và operational knowledge cũng có thể gắn chặt vào một nền tảng.

### 14.1. Exit cost

Ước lượng:
- Data export và transfer.
- Data format/schema conversion.
- Downtime hoặc dual-run.
- Application refactor.
- Rebuild automation và monitoring.
- Security/compliance revalidation.
- Training và staffing.
- Contract termination hoặc commitment overlap.

Thiết kế exit strategy khi bắt đầu chọn dịch vụ: backup format có export được không, API standard có dùng được không, dữ liệu đặt ở đâu, và migration cần bao lâu.

## 15. Sustainability và hiệu quả sử dụng tài nguyên

Sustainability liên quan đến lượng compute, storage, network và năng lượng cần cho mỗi đơn vị công việc hữu ích.

Managed provider có thể đạt utilization và efficiency tốt nhờ chia sẻ hạ tầng quy mô lớn; self-managed có thể giảm waste bằng tuning, bin packing và workload consolidation nếu đội đủ năng lực. Ngược lại:
- Managed tier provision quá lớn gây idle capacity.
- Self-managed cluster giữ headroom quá nhiều gây resource waste.
- Replica/backup/retention không được quản lý làm storage tăng.
- Data transfer liên vùng và log volume lớn làm network footprint tăng.
- Workload không scale-to-zero hoặc không tắt non-production gây tiêu thụ không cần thiết.

Các chỉ số hữu ích:
- Energy/carbon intensity nếu provider cung cấp đáng tin cậy.
- Compute hours và utilization trên mỗi transaction.
- Storage GB-month và retention age.
- Network bytes/transaction.
- Idle capacity percentage.
- Useful throughput trên mỗi đơn vị tài nguyên.
- Waste do overprovisioning và abandoned resources.

Không suy ra dấu chân carbon chỉ từ số VM hoặc hóa đơn. Cần dùng phương pháp và dữ liệu provider nhất quán, ghi rõ giới hạn của số liệu.

## 16. Managed database và self-managed database

Đây là ví dụ phổ biến, nhưng phải so đúng engine, version, workload và HA level.

| Tiêu chí | Managed database | Self-managed database |
| --- | --- | --- |
| Provisioning | Nhanh qua API/console | Cần automation/cài đặt |
| OS/host patch | Provider đảm nhận theo dịch vụ | Đội nội bộ |
| Engine upgrade | Theo support matrix/maintenance policy | Đội nội bộ lập kế hoạch |
| Backup | Có thể tích hợp snapshot/PITR | Tự xây và kiểm thử |
| HA | Có topology/failover được hỗ trợ | Tự triển khai replication/failover |
| Tuning | Có parameter/extension giới hạn | Tùy biến sâu hơn |
| Access | Endpoint và IAM/network policy | Kiểm soát OS/engine sâu hơn |
| Cost | Service premium và feature charges | Compute/storage/tooling + labor |
| Portability | Có thể phụ thuộc extension/service feature | Có thể linh hoạt nhưng vẫn cần migrate |
| Operations | Nhẹ hơn ở tầng managed | Nặng hơn và cần chuyên môn |

### 16.1. Những khoản cần kiểm tra

- Storage autoscaling và maximum size.
- IOPS/throughput và read replica.
- Backup retention, snapshot copy và PITR.
- Multi-AZ failover semantics và downtime.
- Database connection limit/proxy.
- Extension, version compatibility và parameter access.
- Maintenance window và forced upgrade policy.
- Data egress, cross-region replication và restore fees.
- Performance under peak and failover.

## 17. Managed Kubernetes và tự vận hành Kubernetes

Managed Kubernetes thường quản lý control plane và một số integration; đội vẫn cần quản lý workload, node groups, add-ons, network policy, storage, upgrades và security theo dịch vụ.

Self-managed Kubernetes có thể cho phép tùy biến control plane/network/runtime sâu hơn nhưng kéo theo:
- API server/etcd availability.
- Control-plane patching và backup.
- Certificate rotation.
- Scheduler/controller health.
- Upgrade compatibility.
- CNI/CSI/ingress lifecycle.
- Cluster autoscaler và node image.
- Multi-AZ quorum và restore.
- On-call, runbook và security hardening.

Không giả định managed Kubernetes loại bỏ mọi việc vận hành cluster. So sánh dựa trên những thành phần chính xác provider quản lý và những add-on khách hàng vẫn sở hữu.

## 18. Managed broker, cache và observability

Các hệ thống stateful/distributed như message broker, cache và observability có operational complexity riêng.

| Service | Managed value thường gặp | Self-managed responsibility |
| --- | --- | --- |
| Message broker | Provisioning, broker replacement, managed replication theo tier | Partition/rebalance, upgrade, storage, replication, consumer lag |
| Cache | Node lifecycle, failover/topology theo tier | Cluster/shard management, failover, eviction, memory sizing |
| Search engine | Cluster provisioning, snapshots/upgrade support | Shard allocation, JVM/heap, indexing, reindex, snapshot |
| Observability | Ingest/storage/search backend | Collector, index lifecycle, scaling, retention, query capacity |

Dù managed, khách hàng vẫn phải thiết kế partition key, data retention, cache invalidation, consumer idempotency và query/index strategy.

## 19. Shared platform và economies of scale

Nếu một tổ chức vận hành nhiều workload, self-managed platform có thể chia sẻ giữa các team:
- Compute cluster dùng chung.
- Database/broker platform tiêu chuẩn.
- Monitoring và logging pipeline.
- CI/CD và policy controls.
- On-call và platform engineering.

Điều này có thể làm chi phí incremental mỗi workload thấp hơn so với mỗi team tự vận hành. Nhưng shared platform cũng cần tính cost của multi-tenancy, noisy neighbor, chargeback, support, upgrade coordination và blast radius.

Managed service cũng có shared economics ở phía provider; khách hàng trả cho capacity và abstraction, không cần tự xây đội vận hành toàn stack.

### 19.1. Tránh phân bổ labor sai

Nếu platform team tồn tại bất kể workload, không nên phân bổ toàn bộ salary của team cho một service mới. Tính incremental effort hoặc phân bổ theo usage/consumption. Ngược lại, không bỏ qua hiring/on-call capacity nếu workload mới thực sự buộc tổ chức mở thêm vị trí.

## 20. FinOps: đo và tối ưu sau khi lựa chọn

Một quyết định TCO không kết thúc lúc apply. Theo dõi actual spend và operational effort:

- Cost per transaction/request/job.
- Cost per GB stored/processed.
- Compute utilization và idle capacity.
- Managed tier/instance size so với load.
- Backup/replication/egress cost.
- Engineering hours cho operations.
- Incident count, MTTR và error budget.
- Upgrade/patch cadence.
- Cost allocation theo team/service/environment.
- Forecast so với actual.

### 20.1. Unit economics

Ví dụ:

```text
Cost per successful booking =
  total monthly platform TCO / successful bookings per month
```

Dùng successful business transactions thay raw request count để so hiệu quả. Nếu throughput tăng nhưng tỷ lệ lỗi/duplicate cũng tăng, cost per useful transaction có thể xấu đi.

### 20.2. Review cadence

- Hằng tháng: spend anomalies, utilization, idle resources, unit cost.
- Hằng quý: capacity, support tier, backup, operational toil.
- Trước renewal: commitment, exit terms, feature usage và pricing.
- Sau incident: cost của outage, recovery và remedial capacity.

Không tối ưu chi phí bằng cách bỏ backup, patching, security hoặc headroom đã được xác định là cần thiết cho SLO.

## 21. Quy trình ra quyết định managed hay self-managed

1. **Mô tả workload:** demand, data growth, peak, burst, traffic mix và latency.
2. **Xác định service objective:** availability, RPO/RTO, security, compliance và support.
3. **Lập responsibility matrix:** provider làm gì, customer làm gì, shared control nào cần cấu hình.
4. **Tạo hai kiến trúc tương đương:** cùng capacity, HA/DR, retention và security.
5. **Ước lượng direct cost:** compute, storage, network, license, managed fee, backup và support.
6. **Ước lượng labor/tooling:** initial build, patch, on-call, upgrade, monitor, restore và audit.
7. **Tính risk cost:** incident scenarios, downtime, recovery và residual risk.
8. **Tính TCO/unit cost:** theo 1–3 năm và nhiều growth scenarios.
9. **Phân tích sensitivity:** labor rate, traffic growth, utilization, egress và provider pricing.
10. **Đánh giá lock-in/exit:** export, format, API, migration và contract.
11. **Chạy proof of concept:** benchmark, restore, failover, upgrade và cost telemetry.
12. **Ghi ADR và review định kỳ:** owner, assumptions, decision trigger và thời điểm xem lại.

## 22. Tình huống thực hành: nền tảng booking chọn message broker

**Bối cảnh:** Nền tảng booking cần broker để phát booking events, payment status và notifications. Workload hiện tại trung bình 5.000 messages/s, campaign peak 20.000 messages/s, retention 3 ngày và cần multi-zone availability. Team có hai platform engineers đang vận hành Kubernetes và database; chưa có người chuyên sâu về broker.

### 22.1. Phương án managed

- Broker được provision theo managed tier hỗ trợ throughput/replication.
- Provider đảm nhận broker host lifecycle và các tác vụ quản lý theo hợp đồng.
- Team vẫn thiết kế topic/partition, schema, producer idempotency, consumer lag, retention và alert.
- Tính service fee, storage, network, cross-zone transfer, support và backup/export nếu cần.
- Kiểm tra throughput peak, quota, failover và data export.

### 22.2. Phương án self-managed

- Chạy broker trên Kubernetes hoặc VM.
- Team chịu trách nhiệm broker nodes, storage, replication, upgrades, security, monitoring, backup và recovery.
- Cần capacity dư cho một node/AZ failure và partition rebalancing.
- Tính compute, disk throughput, network, persistent volume, observability, automation và on-call labor.
- Đánh giá ảnh hưởng tới roadmap của hai platform engineers và nhu cầu hiring/backup coverage.

### 22.3. Mô hình TCO minh họa

Giả sử trong một tháng:

| Khoản mục | Managed | Self-managed |
| --- | ---: | ---: |
| Service/compute/storage | 6.000 USD | 3.000 USD |
| Network/backup/tooling | 900 USD | 1.100 USD |
| Labor | 600 USD | 3.000 USD |
| Support/training | 300 USD | 400 USD |
| Total | 7.800 USD | 7.500 USD |

Trong ví dụ này chênh lệch TCO chỉ 300 USD/tháng. Tuy nhiên, self-managed labor 60 giờ/tháng có thể cạnh tranh với công việc nền tảng khác. Nếu campaign tăng gấp đôi hoặc cần thêm engineer trực on-call, kết quả có thể đảo chiều.

Các số liệu hoàn toàn giả định nhằm minh họa phương pháp; phải thay bằng quotation/provider calculator, usage test và labor rate nội bộ.

### 22.4. Quyết định có điều kiện

Có thể chọn managed trong giai đoạn đầu để tập trung đội ngũ vào event contract và product workflow. Sau khi có telemetry về throughput, retention, partition count và cost per event, review lại khi workload ổn định và đội platform có năng lực vận hành đủ. Trước quyết định phải chạy benchmark peak, failover, consumer recovery và export test.

## 23. ADR mẫu: chọn managed service sau khi so TCO

```text
ADR-173: Managed hay self-managed message broker

Bối cảnh:
- Booking platform cần 5.000 msg/s average và 20.000 msg/s peak.
- Cần multi-zone availability và retention 3 ngày.
- Team platform có hai engineer, chưa chuyên sâu broker.
- Self-managed infrastructure bill thấp hơn nhưng labor cao hơn.

Lựa chọn:
A. Managed broker theo tier có throughput và HA phù hợp.
B. Self-managed broker trên Kubernetes.
C. Managed trong giai đoạn đầu, review lại sau khi có usage evidence.

Quyết định:
- Chọn C.
- Managed broker đáp ứng peak, retention và failure objective đã test.
- Team chịu trách nhiệm topic/partition/schema, producer/consumer correctness và alert.
- Cost được theo dõi theo monthly TCO và cost per successful event.
- Định kỳ đánh giá lại dựa trên growth, provider pricing và staffing.

Đánh đổi:
- TCO hóa đơn dịch vụ cao hơn.
- Giảm operational toil và nhu cầu chuyên môn broker thường trực.
- Có dependency vào provider feature, quota và export semantics.

Kiểm chứng:
- Benchmark throughput/latency ở peak.
- Multi-zone failover và consumer recovery test.
- Verify retention, replay và data export.
- Đo actual monthly spend và engineering hours.
- Cost per successful booking event nằm trong budget.

Điều kiện xem lại:
- Volume/retention thay đổi đáng kể.
- Provider fee hoặc quota thay đổi.
- Đội platform có broker expertise và staffing mới.
- TCO/unit cost hoặc SLO không đạt.
```

## 24. Những sai lầm thường gặp

1. **So service fee với VM bill:** bỏ qua labor, HA, backup và tooling.
2. **So hai service level khác nhau:** managed multi-AZ với self-managed single-node.
3. **Coi managed là zero operations:** application, access, data, quota và recovery vẫn cần quản lý.
4. **Coi open source là miễn phí:** labor, support, patching và incident cost vẫn tồn tại.
5. **Bỏ qua egress/cross-zone transfer:** chi phí network có thể đáng kể.
6. **Không tính standby/headroom:** thiếu capacity sau failure làm so sánh sai.
7. **Đếm labor trùng hoặc bỏ labor:** làm TCO lệch đáng kể.
8. **Dùng utilization trung bình:** bỏ qua peak, burst và idle capacity.
9. **Không tính restore test:** backup cost có nhưng restore path chưa được chứng minh.
10. **Giả định provider chịu trách nhiệm compliance:** customer vẫn giữ nhiều control.
11. **Không tính migration/exit:** khóa dữ liệu hoặc format làm chi phí rời dịch vụ cao.
12. **Quyết định theo giá năm đầu:** bỏ qua growth, renewal và commitment.
13. **Bỏ qua support tier/contract:** SLA và escalation không tương đương.
14. **Không có unit economics:** không biết cost trên transaction hữu ích.
15. **Coi carbon theo hóa đơn:** không phản ánh trực tiếp energy/carbon intensity.
16. **Không review sau triển khai:** usage, price và operational effort thay đổi theo thời gian.
17. **Chỉ xem chi phí cloud:** bỏ qua opportunity cost và hiệu quả đội ngũ.
18. **Không làm PoC:** pricing estimate không thay benchmark và failover test.

## 25. Checklist trước khi quyết định

- [ ] Hai phương án dùng cùng workload, region, growth và time horizon.
- [ ] SLO, RPO/RTO, security và compliance baseline được ghi rõ.
- [ ] Responsibility matrix mô tả provider/customer/shared controls.
- [ ] Managed fee gồm tier, backup, support, request và capacity charges.
- [ ] Self-managed gồm compute, storage, network, license và HA/DR headroom.
- [ ] Labor gồm build, patch, upgrade, on-call, restore, audit và training.
- [ ] Observability, security tooling và backup được tính vào TCO.
- [ ] Egress, cross-AZ/region, NAT, request và archive retrieval được xét.
- [ ] Incident/risk cost và residual risk được mô tả.
- [ ] Có TCO 1–3 năm và nhiều workload/growth scenarios.
- [ ] Có sensitivity analysis cho labor, utilization, egress và pricing.
- [ ] Cost per successful transaction/event được tính khi phù hợp.
- [ ] Lock-in, data export, migration và exit cost được đánh giá.
- [ ] Staffing, skill coverage và on-call sustainability được xác nhận.
- [ ] Backup restore, HA failover, upgrade và peak load được kiểm thử.
- [ ] Pricing/contract/SLA và provider service boundary đã được xác minh.
- [ ] Owner, assumptions, decision trigger và review date có trong ADR.
- [ ] Actual spend/labor sẽ được theo dõi sau production.

---

**Ghi nhớ:** Managed service thường đổi service premium lấy một phần năng lực provisioning và vận hành; self-managed có thể giảm một số hóa đơn hạ tầng nhưng chuyển thêm công việc, rủi ro và trách nhiệm sang đội nội bộ. Quyết định đúng phải so TCO trên cùng workload và SLO, tính đủ labor, HA/DR, security, network, tooling và exit cost, rồi kiểm chứng bằng PoC cùng dữ liệu vận hành thực tế.
