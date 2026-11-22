# Bảo trì, vá lỗi và vòng đời tài nguyên nền tảng

Một nền tảng cloud không giữ nguyên trạng thái sau khi triển khai. Hệ điều hành, container base image, runtime, database engine, network appliance, certificate, firmware và dịch vụ được quản lý đều có vòng đời riêng. Nhà cung cấp phát hành bản vá, phiên bản cũ hết hỗ trợ, lỗ hổng mới được công bố, workload tăng trưởng và tài nguyên không còn phù hợp. Nếu chỉ tập trung xây dựng ban đầu mà không quản lý thay đổi trong suốt vòng đời, hệ thống sẽ dần tích tụ rủi ro bảo mật, nợ kỹ thuật, chi phí và điểm lỗi khó phục hồi.

**Bảo trì nền tảng (platform maintenance)** là hoạt động giữ hạ tầng và phần mềm nền tảng ở trạng thái an toàn, được hỗ trợ và đáp ứng mục tiêu vận hành. **Vá lỗi (patching)** là một phần của bảo trì, tập trung sửa lỗi hoặc lỗ hổng trong phần mềm/firmware. **Quản lý vòng đời tài nguyên (resource lifecycle management)** bao quát việc lập kế hoạch, cấp phát, cấu hình, vận hành, nâng cấp, mở rộng, thu hẹp và ngừng sử dụng tài nguyên cloud.

Bài học thuộc chương **Vận hành hệ thống** của lộ trình **Cloud Architecture**. Chương trình học cách thiết kế kiến trúc cloud từ yêu cầu nghiệp vụ tới mạng, compute, dữ liệu và mô hình triển khai, cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Bài này tập trung vào cách đưa bảo trì thành quy trình có inventory, owner, lịch thay đổi, kiểm chứng, rollback và bằng chứng tuân thủ.

Sau bài học, bạn có thể:

- Thiết kế quy trình maintenance và patch management theo mức độ rủi ro.
- Lập inventory tài nguyên, phiên bản, owner, dependency và ngày hết hỗ trợ.
- Phân loại lỗ hổng và ưu tiên vá theo exploitability, exposure và business impact.
- Chọn rolling, canary, blue-green hoặc in-place maintenance.
- Lập kế hoạch backup, compatibility, rollback và recovery trước khi thay đổi.
- Quản lý vòng đời compute, container, database, storage, network và managed services.
- Theo dõi capacity, cost, drift và tài nguyên hết hạn/không còn sử dụng.
- Decommission an toàn, bảo vệ dữ liệu và thu hồi identity/credential.
- Đo hiệu quả bằng coverage, patch latency, change failure rate và lifecycle compliance.

## 1. Maintenance là hoạt động liên tục

Bảo trì không chỉ diễn ra khi hệ thống gặp sự cố. Nó gồm các hoạt động chủ động để giảm khả năng xảy ra sự cố và các hoạt động phản ứng khi phát hiện lỗi/lỗ hổng.

| Nhóm hoạt động | Ví dụ | Mục tiêu |
| --- | --- | --- |
| Preventive maintenance | Patch định kỳ, certificate renewal, disk health check | Ngăn lỗi trước khi xảy ra |
| Corrective maintenance | Sửa cấu hình sai, thay instance lỗi, vá bug | Khôi phục trạng thái đúng |
| Adaptive maintenance | Nâng runtime, đổi API cloud, chuyển storage tier | Thích nghi với môi trường thay đổi |
| Predictive maintenance | Theo dõi disk wear, capacity trend, expiry | Phát hiện nguy cơ trước ngưỡng |
| Security maintenance | Vá CVE, rotate credential, cập nhật policy | Giảm bề mặt tấn công |
| Lifecycle maintenance | Upgrade, resize, retire resource | Giữ tài nguyên được hỗ trợ và hiệu quả |

Một maintenance program tốt phân biệt công việc định kỳ với việc khẩn cấp. Không phải thay đổi nào cũng cần cùng change window hoặc approval; nhưng mọi thay đổi cần owner, impact assessment, bằng chứng và cách xác nhận kết quả.

## 2. Resource inventory và ownership

Không thể bảo trì thứ mà tổ chức không biết đang tồn tại. Inventory cần bao phủ cả tài nguyên cloud và thành phần phần mềm chạy trên đó.

Thông tin tối thiểu:

- Resource ID, loại tài nguyên, account/project/subscription và region.
- Environment, application/service, tenant hoặc data classification liên quan.
- Owner kỹ thuật, owner nghiệp vụ và team on-call.
- Runtime/OS/image/firmware/engine version.
- Creation date, support end date, expiry và lifecycle state.
- Network exposure, identity/role và dependency.
- Backup/restore classification, RPO/RTO và retention.
- Cost center, tags và utilization.
- Maintenance policy, patch group và change window.

### 2.1. Inventory không chỉ dựa vào tag thủ công

Có thể kết hợp cloud asset inventory, API discovery, configuration management database (CMDB), Kubernetes inventory, software bill of materials (SBOM), package scanner và IaC state. Đối chiếu các nguồn giúp phát hiện tài nguyên không được quản lý hoặc cấu hình thực tế đã lệch so với khai báo.

Một tài nguyên không có owner hoặc environment rõ ràng cần được đưa vào hàng đợi phân loại, không mặc định là tài nguyên thử nghiệm có thể xóa.

### 2.2. Owner và responsibility model

Với managed service, nhà cung cấp có thể chịu trách nhiệm phần cứng và một phần patch nền, còn khách hàng chịu trách nhiệm cấu hình, version option, access policy và maintenance window. Cần lập shared responsibility matrix theo từng dịch vụ; từ “managed” không đồng nghĩa nhà cung cấp quản lý toàn bộ vòng đời ứng dụng.

## 3. Resource lifecycle

Một tài nguyên cloud thường đi qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Planned
    Planned --> Provisioned
    Provisioned --> Active
    Active --> Maintenance
    Maintenance --> Active
    Active --> Upgrade
    Upgrade --> Active
    Active --> Deprecated
    Deprecated --> Decommissioning
    Decommissioning --> Retired
    Retired --> [*]
~~~

Các trạng thái cần có điều kiện vào/ra. Ví dụ resource chuyển sang Deprecated khi đã có replacement path và ngày end-of-support; Decommissioning chỉ bắt đầu sau khi xác minh workload đã migrate và dữ liệu có retention/export phù hợp.

Không để resource ở trạng thái “tạm thời” vô thời hạn. Inventory cần hiển thị tài nguyên provisioning dở dang, failed, orphaned, idle và pending retirement.

## 4. Lifecycle policy theo loại tài nguyên

Mỗi loại tài nguyên cần chu kỳ và tiêu chí riêng.

| Loại | Bảo trì điển hình | Dấu mốc lifecycle |
| --- | --- | --- |
| VM/OS | Security patch, kernel update, image refresh | OS end-of-support, instance family cũ |
| Container image | Rebuild base image, scan dependency | Image digest, base image EOL |
| Kubernetes/node pool | Control plane/node upgrade, API deprecation | Cluster version support window |
| Database | Engine patch, minor/major upgrade, parameter review | Engine support end, storage growth |
| Storage | Capacity/IOPS review, integrity/replication check | Volume age, tier, retention |
| Network | Firmware/config patch, route/firewall review | Appliance EOL, certificate expiry |
| Certificate | Renewal, chain migration, revoke | Not-after date, CA transition |
| IAM/secret | Credential rotation, role review | Secret age, access owner change |
| Managed service | Review release channel and provider notice | Mandatory upgrade/deprecation |
| Backup system | Restore drill, retention and key validation | Backup age, restore test age |

Lịch maintenance cần được tạo dựa trên vendor support lifecycle, security advisories, workload compatibility và yêu cầu doanh nghiệp. Không dùng một lịch cố định duy nhất cho tất cả loại tài nguyên.

## 5. Patch management lifecycle

Một quy trình patch management có thể gồm các bước:

1. **Discover:** tìm tài sản và package/version bị ảnh hưởng.
2. **Assess:** xác định mức độ nghiêm trọng, khả năng khai thác, exposure và impact.
3. **Prioritize:** xếp thứ tự dựa trên risk và deadline.
4. **Acquire:** lấy patch/image/release chính thức, kiểm tra chữ ký/provenance.
5. **Test:** thử trong môi trường tương đương production.
6. **Plan:** xác định cohort, change window, dependency và rollback/recovery.
7. **Deploy:** phát hành theo canary/rolling/wave.
8. **Verify:** kiểm tra version, service health và behavior nghiệp vụ.
9. **Record:** lưu bằng chứng, exception và completion status.
10. **Remediate gaps:** xử lý host offline, failed deployment hoặc tài sản ngoài inventory.

Một patch chỉ được coi là hoàn tất khi tài sản thực sự chạy phiên bản đã định, hoặc có exception được phê duyệt và ngày xử lý. Lệnh deploy thành công chưa đủ nếu một node không cập nhật hoặc workload vẫn dùng image cũ.

## 6. Phân loại lỗ hổng và ưu tiên vá

Không nên chỉ ưu tiên theo một con số severity. Mức độ rủi ro thực tế còn phụ thuộc khả năng khai thác, exposure, quyền cần có, dữ liệu bị ảnh hưởng và khả năng giảm thiểu.

Các tín hiệu:

- CVSS/severity từ nguồn đánh giá.
- Có exploit thực tế hoặc exploit code công khai.
- Thành phần có thể truy cập từ Internet hay chỉ từ network nội bộ.
- Có bị khai thác trong môi trường thực tế hay không.
- Service có xử lý dữ liệu nhạy cảm/critical workload.
- Có compensating control như WAF, network isolation hoặc feature disable.
- Patch có breaking change hoặc cần reboot.
- Blast radius nếu exploit thành công.

### 6.1. Risk-based prioritization

| Mức ưu tiên | Dấu hiệu minh họa | Phản ứng |
| --- | --- | --- |
| Khẩn cấp | Lỗ hổng đang bị khai thác, exposed asset, tác động critical | Kích hoạt emergency change, cô lập/mitigate và vá theo thời hạn rất ngắn |
| Cao | Remote exploit khả thi hoặc quyền cao trên hệ thống quan trọng | Ưu tiên trong chu kỳ gần nhất, kiểm tra coverage hàng ngày |
| Trung bình | Điều kiện khai thác hạn chế, exposure thấp hơn | Lên lịch maintenance theo risk và support window |
| Thấp | Impact thấp hoặc đã có kiểm soát mạnh | Gom vào maintenance cycle, theo dõi advisory |

Các mức và thời hạn phải được tổ chức định nghĩa bằng policy; ví dụ này không thay thế tiêu chuẩn bảo mật hay yêu cầu pháp lý áp dụng.

### 6.2. Zero-day và emergency patch

Khi chưa có patch, có thể áp dụng mitigation tạm thời như tắt feature dễ bị khai thác, chặn network path, WAF rule, rotate credential hoặc cô lập workload. Mitigation phải có owner, expiry và kế hoạch quay lại cấu hình chuẩn.

Khi patch khẩn cấp có nguy cơ breaking change, cần kiểm tra tối thiểu các hành trình critical và triển khai theo cohort nhỏ nếu thời gian cho phép. Nếu không thể chờ test đầy đủ, decision record cần ghi rõ risk đã chấp nhận, validation tối thiểu và phương án rollback/restore.

## 7. Patch policy và exception management

Một patch policy nên quy định:

- Phạm vi asset và package phải scan.
- Tần suất scan và nguồn advisory.
- SLA theo risk level.
- Change window và approval path.
- Nhóm workload có maintenance riêng.
- Cách xử lý host offline hoặc không patch được.
- Evidence bắt buộc và retention.
- Quy trình exception/waiver.
- Điều kiện đóng exception.
- Escalation khi quá hạn.

Exception không nên chỉ là một ghi chú “không thể vá”. Nó cần owner, lý do kỹ thuật/nghiệp vụ, risk acceptance có thẩm quyền, compensating controls, ngày hết hạn và kế hoạch remediation. Exception hết hạn phải tự động được đưa vào review/escalation.

## 8. Kiểm tra patch trước production

Testing cần phản ánh dependency và hành vi thật của workload.

Các lớp kiểm tra:

- **Compatibility:** runtime, driver, SDK, agent, extension và library còn tương thích.
- **Functional:** các API và business workflow chính hoạt động.
- **Performance:** latency, throughput, CPU/memory và query plan không regression vượt ngưỡng.
- **Security:** lỗ hổng được xử lý, policy và certificate không bị thay đổi sai.
- **Data:** migration, backup, replica và transaction semantics an toàn.
- **Operational:** monitoring, logging, auto-scaling và restart hoạt động.
- **Recovery:** rollback hoặc restore có thể thực hiện trong mục tiêu.

Không phải patch nào cũng cần full regression suite; nhưng critical workload và thay đổi engine/kernel/network phải có mức test tương ứng với impact.

## 9. Deployment strategy cho maintenance

### 9.1. In-place maintenance

Thay đổi trực tiếp trên resource đang chạy, ví dụ update package và reboot VM.

Ưu điểm là ít tài nguyên tạm và đơn giản với môi trường nhỏ. Đánh đổi là có downtime hoặc gián đoạn; nếu patch lỗi, rollback có thể khó.

Phù hợp workload có node dự phòng hoặc chấp nhận maintenance window.

### 9.2. Rolling maintenance

Thay đổi từng nhóm instance/node trong khi phần còn lại tiếp tục phục vụ.

~~~mermaid
flowchart LR
    A["Healthy fleet v1"] --> B["Drain node 1"]
    B --> C["Patch node 1"]
    C --> D["Health check"]
    D --> E["Continue with next node"]
    E --> F["Fleet v2"]
~~~

Cần kiểm tra capacity còn lại đủ phục vụ tải khi drain node; có readiness/liveness check, disruption budget và giới hạn số node cùng unavailable.

### 9.3. Canary maintenance

Cập nhật một node hoặc cohort nhỏ, quan sát trước khi mở rộng. Canary nên đại diện cho workload, region, hardware family và tenant mix. Nếu chỉ chọn node ít tải nhất, có thể bỏ sót lỗi ở workload thật.

### 9.4. Blue-green replacement

Tạo fleet mới, validate và chuyển traffic; giữ fleet cũ trong thời gian rollback. Phương pháp này giảm tác động của patch trên runtime đang chạy nhưng tăng chi phí tạm thời và yêu cầu dữ liệu/state tương thích.

### 9.5. So sánh

| Chiến lược | Downtime | Chi phí tạm | Khả năng rollback | Rủi ro chính |
| --- | --- | --- | --- | --- |
| In-place | Có thể có | Thấp | Thường khó hơn | Node đang phục vụ bị ảnh hưởng |
| Rolling | Có thể không nếu đủ redundancy | Vừa | Theo node/cohort | Capacity thiếu khi drain |
| Canary | Giới hạn ở cohort nhỏ | Vừa | Dễ dừng rollout | Cohort không đại diện |
| Blue-green | Thường thấp nếu cutover tốt | Cao hơn | Có thể nhanh trước khi state đổi | Data/schema compatibility |

Không có chiến lược nào bảo đảm zero downtime nếu ứng dụng, database, network hoặc load balancer chưa được thiết kế cho quá trình chuyển đổi.

## 10. Maintenance window và change management

Maintenance window cần cân bằng thời điểm ít ảnh hưởng người dùng với khả năng có đủ operator và vendor support khi sự cố xảy ra.

Change record nên nêu:

- Mục tiêu và phạm vi resource.
- Lý do, advisory/CVE hoặc lifecycle deadline.
- Owner và người phê duyệt.
- Dependency và ảnh hưởng tới tenant/region.
- Kế hoạch test, deployment và health gate.
- Backup/restore readiness.
- Rollback/forward-fix criteria.
- Thời gian bắt đầu/kết thúc, communication plan.
- Metric theo dõi và người trực.
- Kết quả, incident và evidence.

### 10.1. Normal, standard và emergency change

- **Standard change:** lặp lại, rủi ro thấp, có procedure đã được phê duyệt.
- **Normal change:** cần impact assessment/review theo quy trình.
- **Emergency change:** xử lý lỗ hổng hoặc sự cố có thời hạn gấp; cần approval path rút gọn và hậu kiểm.

Emergency không có nghĩa bỏ qua log, evidence hoặc validation. Tổ chức cần ghi người quyết định và risk đã chấp nhận.

### 10.2. Change freeze

Change freeze có thể giảm rủi ro trước kỳ kinh doanh quan trọng, nhưng không nên chặn vá khẩn cấp cho lỗ hổng đang bị khai thác. Policy cần ngoại lệ emergency và phương pháp đánh giá theo risk.

## 11. Backup và rollback trước maintenance

Trước khi thay đổi database, storage, OS hoặc control plane, phải biết trạng thái có thể khôi phục.

Cần kiểm tra:

- Backup mới nhất và restore point.
- PITR/log chain nếu cần.
- Snapshot consistency và encryption key access.
- Database replication lag và failover readiness.
- Infrastructure configuration/version.
- Image/artifact cũ còn khả năng deploy.
- Schema backward compatibility.
- Secrets/certificate còn hợp lệ sau chuyển đổi.
- Data migration có thể resume hay không.

**Rollback code** không đồng nghĩa rollback data. Nếu patch chạy migration destructive hoặc ghi dữ liệu theo schema mới, quay về binary cũ có thể không an toàn. Dùng expand–migrate–contract, compatibility layer hoặc forward fix khi rollback không khả thi.

## 12. OS, VM và compute lifecycle

Compute resource cần được cập nhật và thay thế theo support lifecycle.

### 12.1. Golden image và immutable infrastructure

Golden image là image chuẩn đã được harden, cập nhật package cần thiết và kiểm tra trước khi sử dụng. Với immutable infrastructure, thay vì patch thủ công từng VM lâu năm, pipeline tạo image mới rồi replace instance theo rolling/blue-green.

Ưu điểm:

- Các instance mới có cấu hình đồng nhất.
- Dễ truy vết image digest/version.
- Giảm config drift.
- Dễ rollback bằng artifact trước nếu state cho phép.

Đánh đổi là cần pipeline build/test và quản lý dữ liệu không nằm trong instance. Không lưu state nghiệp vụ duy nhất trên ephemeral VM local disk.

### 12.2. OS end-of-support

Khi OS hết hỗ trợ bảo mật, cần nâng cấp hoặc migrate sang image/OS được hỗ trợ. Extended support nếu có chỉ là khoảng chuyển tiếp có điều kiện và có chi phí; cần deadline retire rõ ràng.

## 13. Container image và software supply chain

Container image có thể đóng gói OS packages, runtime, application dependency và agent. Một base image cũ có thể khiến mọi image downstream giữ lỗ hổng dù application code không đổi.

Quy trình nên gồm:

1. Chọn base image từ publisher đáng tin.
2. Pin digest thay vì chỉ dùng mutable tag trong production.
3. Scan OS/package/library và generate SBOM.
4. Verify signature/provenance theo policy.
5. Rebuild image khi base image có patch.
6. Test và publish artifact mới.
7. Rollout theo cohort.
8. Xác nhận pod/node cũ đã được thay.
9. Retire image digest cũ theo retention.

Không chỉ scan lúc build. Runtime inventory cần phát hiện container đang chạy digest nào; nếu không, image mới tồn tại trong registry nhưng workload vẫn chạy image cũ.

## 14. Kubernetes và managed control plane lifecycle

Kubernetes cluster có nhiều thành phần cần nâng cấp theo tương thích:

- Managed control plane version.
- Worker node image và kubelet.
- Container runtime.
- CNI/network plugin.
- CSI/storage driver.
- Ingress/controller/service mesh.
- CRD và operator.
- Helm chart/application manifests.
- API version bị deprecate.

Cần kiểm tra version skew policy của Kubernetes/provider, PodDisruptionBudget, capacity node pool và workload có chạy được trên node mới. Nâng control plane và node pool theo thứ tự được nhà cung cấp hỗ trợ.

Trước upgrade:

- Scan API deprecation và manifest.
- Kiểm tra admission webhook/operator compatibility.
- Đảm bảo đủ spare capacity để drain.
- Kiểm tra stateful workload và local volume.
- Backup cluster configuration/etcd nếu mô hình yêu cầu.
- Thử upgrade trên staging.
- Xác nhận autoscaler và network/storage plugin.

## 15. Database engine và schema lifecycle

Database maintenance có rủi ro cao vì liên quan transaction và dữ liệu durable.

Các loại thay đổi:

- Minor/patch engine update.
- Major version upgrade.
- Parameter/configuration change.
- Extension/driver upgrade.
- Schema migration và data backfill.
- Storage/instance class change.
- Certificate/credential rotation.

Major upgrade thường cần compatibility assessment cho SQL behavior, collation, extension, driver, replication và query planner. Có thể cần dump/restore, in-place upgrade hoặc replication-based migration tùy engine và managed service.

### 15.1. Expand–migrate–contract

1. Expand schema bằng field/table mới tương thích.
2. Deploy code đọc/ghi tương thích cả cũ và mới.
3. Backfill dữ liệu theo batch, checkpoint và rate limit.
4. Chuyển consumer/query sang schema mới.
5. Validate completeness và performance.
6. Contract, bỏ schema cũ sau khi không còn client cần.

Tránh thay đổi destructive đồng thời với deployment code nếu chưa có recovery plan.

## 16. Storage lifecycle và data retention

Storage có thể tăng chi phí, giảm hiệu năng hoặc hết vòng đời thiết bị/dịch vụ. Cần phân biệt data hot, warm, cold và archive theo access pattern.

Các hoạt động:

- Theo dõi capacity, latency, IOPS và throughput.
- Mở rộng volume trước khi chạm ngưỡng.
- Chọn storage class phù hợp.
- Thiết lập lifecycle chuyển tier.
- Kiểm tra replication, durability và checksum.
- Backup/restore test.
- Retention và legal hold.
- Xóa dữ liệu hết hạn theo policy.
- Decommission volume/object bucket an toàn.

Lifecycle tiering không thay backup; archive cũng phải có quy trình restore và khả năng giải mã. Xóa resource cần kiểm tra snapshot, replica, object version và backup retention.

## 17. Network và certificate lifecycle

Network resource có thể có version/limit/expiry riêng: route, firewall rule, load balancer, NAT, VPN, gateway, DNS record, IP address và certificate.

Bảo trì cần xem xét:

- Certificate/TLS expiry, renewal và trust chain.
- Firewall/security group rule stale hoặc quá rộng.
- Route/NAT capacity và quota.
- VPN/peering/transit gateway lifecycle.
- DNS TTL và cutover.
- Load balancer/ingress controller version.
- Private endpoint và certificate trust.
- IPv4/IPv6 transition nếu có.
- Vendor appliance firmware/support end.

Thay đổi network có thể làm mất đường quản trị hoặc đường tới KMS/identity. Cần có management access dự phòng và validate route từ các subnet/workload đại diện.

## 18. Managed service và nhà cung cấp thay đổi

Managed service giảm gánh nặng vận hành hạ tầng nhưng vẫn có lifecycle: engine version, parameter, API version, maintenance event, service quota, feature deprecation và pricing change.

Nên đăng ký service health/advisory, theo dõi end-of-support và cấu hình maintenance window phù hợp. Đối với maintenance do provider điều khiển, cần hiểu:

- Có thể tự chọn thời gian hay provider tự sắp lịch?
- Service có failover/restart không?
- Có thông báo trước và cách defer?
- Có downtime hoặc connection reset?
- Version mới có breaking behavior không?
- Cần kiểm tra client/driver/extension nào?
- Có audit/event sau maintenance?

Không giả định provider maintenance luôn transparent. Ứng dụng cần retry, reconnect, graceful degradation và kiểm thử disruption.

## 19. Capacity management và resource right-sizing

Vòng đời tài nguyên bao gồm đảm bảo capacity đủ và tránh provision quá mức.

Theo dõi:

- CPU/memory utilization và throttling.
- Disk capacity, IOPS, latency và queue depth.
- Network throughput, packet drop và connection count.
- Database connection, lock, cache hit và replication lag.
- Queue depth/age và worker saturation.
- Autoscaling events và quota headroom.
- Growth rate, seasonal peak và forecast.

Right-sizing không nên chỉ dựa trên average utilization. Cần xem peak, p95/p99, burst, failover capacity và maintenance headroom. Nếu chạy multi-zone, mỗi zone còn lại phải chịu được tải theo thiết kế khi một zone bị drain hoặc mất.

## 20. Configuration drift và compliance

Drift là sự khác biệt giữa trạng thái mong muốn được khai báo và trạng thái thực tế. Drift có thể đến từ console edit, script tạm, manual hotfix hoặc automation lỗi.

Các biện pháp:

- Quản lý hạ tầng bằng IaC và module/version dùng chung.
- Phát hiện drift định kỳ hoặc theo event.
- Phân quyền thay đổi trực tiếp.
- Ghi change/audit log.
- Review và import thay đổi hợp lệ về source of truth.
- Tự động remediate chỉ với rule có rủi ro thấp và đã kiểm chứng.
- Có exception cho emergency change kèm expiry.
- Đối chiếu cấu hình với security baseline.

Không tự động revert mọi drift trên production nếu chưa hiểu nguyên nhân; automation có thể xóa hotfix cần thiết hoặc gây outage. Phải phân loại, xác định owner và chọn remediate phù hợp.

## 21. Resource decommissioning

Decommission là bước có rủi ro dữ liệu và security cao. Một VM không còn traffic có thể vẫn giữ disk snapshot, service account, public IP, DNS record hoặc credential.

Quy trình:

1. Xác nhận owner và lý do retire.
2. Xác định consumer/dependency qua inventory và telemetry.
3. Thông báo stakeholder và đặt thời gian quan sát.
4. Drain traffic/job và chuyển workload.
5. Export/backup dữ liệu theo retention/legal policy.
6. Verify backup/restore và data ownership.
7. Revoke identity, token, certificate và secret.
8. Xóa DNS/route/firewall/public IP/endpoint liên quan.
9. Xóa compute/storage theo approval; xử lý snapshot/object versions.
10. Gỡ monitoring/alert/deployment/CI references.
11. Cập nhật inventory, CMDB, cost tag và audit.
12. Kiểm tra không còn billing hoặc access path ngoài dự kiến.

### 21.1. Secure deletion

Chỉ xóa VM không đồng nghĩa dữ liệu đã biến mất khỏi snapshot, backup hoặc replica. Cần tuân retention và secure deletion semantics của nhà cung cấp. Với dữ liệu mã hóa, crypto-erasure có thể là một biện pháp nếu key scope và backup dependency đã được xác minh.

Không xóa backup đang thuộc legal hold hoặc retention bắt buộc. Offboarding resource phải kết hợp với data governance và security.

## 22. Maintenance automation và orchestration

Automation có thể scan, tạo change request, patch, reboot, verify và cập nhật inventory. Nhưng cần safety guardrails:

- Target selection từ inventory có owner.
- Exclude/approval cho critical workload.
- Batch size và concurrency limit.
- Pre-check capacity/health/backup.
- Stop condition nếu error rate/latency vượt ngưỡng.
- Post-check version/service health.
- Retry idempotent, không lặp thao tác destructive.
- Audit log và artifact version.
- Human approval cho emergency/high-impact change.
- Không chạy đồng thời các maintenance có chung dependency critical.

~~~mermaid
flowchart TD
    A["Inventory and vulnerability scan"] --> B["Risk assessment / priority"]
    B --> C["Create maintenance plan"]
    C --> D["Pre-check: health, capacity, backup"]
    D --> E["Canary patch"]
    E --> F{"Health gates pass?"}
    F -- "No" --> G["Stop / rollback or forward-fix"]
    F -- "Yes" --> H["Progressive rollout"]
    H --> I["Post-check and compliance scan"]
    I --> J["Update inventory and evidence"]
~~~

Automation cần tôn trọng provider API quota và không tạo thundering herd. Có thể chia wave theo region/cell/tenant, dùng jitter và theo dõi service health trước khi mở batch tiếp theo.

## 23. Metrics và SLO cho maintenance

Một maintenance program cần được đo để biết coverage thực tế và điểm nghẽn.

| Metric | Cách hiểu |
| --- | --- |
| Asset inventory coverage | Tỷ lệ tài nguyên đã có trong inventory so với phát hiện |
| Patch compliance | Tỷ lệ asset đạt baseline trong phạm vi |
| Patch latency | Thời gian từ advisory/patch availability tới remediation |
| Vulnerability exposure window | Thời gian asset còn exposed với lỗ hổng cần xử lý |
| Unsupported asset count | Số resource/runtime đã hết hỗ trợ |
| Certificate expiry coverage | Tỷ lệ certificate có owner, alert và renewal |
| Maintenance success rate | Tỷ lệ change hoàn tất theo tiêu chí |
| Change failure rate | Tỷ lệ maintenance gây incident/rollback |
| Mean time to remediate | Thời gian xử lý finding |
| Drift rate | Số/lượng cấu hình lệch baseline |
| Orphaned resource count | Tài nguyên không có owner/consumer rõ |
| Cost of idle resources | Chi phí tài nguyên không tạo giá trị |

Không chỉ đặt mục tiêu patch compliance cao; cần đo exception age và asset không scan được. Mẫu số phải rõ: tài sản nào thuộc phạm vi, asset nào được miễn trừ và thời điểm snapshot.

## 24. Runbook và post-maintenance review

Runbook maintenance cần chứa:

- Scope và target selection.
- Precondition/health check.
- Change/patch artifact và checksum/signature.
- Dependency và thứ tự thao tác.
- Backup/rollback/recovery instructions.
- Batch size, concurrency và rate limit.
- Metric dashboard và alert.
- Stop condition/escalation.
- Validation business/technical.
- Cách đóng change và cập nhật inventory.

Sau maintenance, review các lỗi, thời gian thực tế, tenant/region bị ảnh hưởng, false positive, patch failure và gap trong automation. Nếu change gây outage, cần post-incident review để sửa quy trình, không chỉ tăng số approval.

## 25. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Không có inventory đầy đủ | Bỏ sót host/package/credential không được vá | Asset discovery và đối chiếu nhiều nguồn |
| Dựa vào severity duy nhất | Vá sai thứ tự so với exposure/business impact | Risk-based prioritization |
| Patch toàn bộ cùng lúc | Blast radius lớn nếu patch lỗi | Canary, wave, stop condition |
| Không giữ capacity khi drain node | Latency tăng hoặc outage | Maintenance headroom và disruption budget |
| Chỉ update image registry | Runtime vẫn chạy image cũ | Inventory runtime digest và verify rollout |
| Coi managed service tự bảo trì toàn bộ | Bỏ sót client, config, version hoặc deprecation | Shared responsibility matrix |
| Không test database migration | Không rollback được hoặc mất dữ liệu | Backup/PITR, expand-contract và rehearsal |
| Rollback binary nhưng giữ schema mới | Incompatibility và lỗi dữ liệu | Backward compatibility/forward-fix plan |
| Exception không expiry | Lỗ hổng tồn tại vô thời hạn | Owner, risk acceptance và deadline |
| Decommission chỉ xóa compute | Secret, disk, IP, DNS và snapshot còn tồn tại | Offboarding checklist xuyên resource graph |
| Tự động revert mọi drift | Mất hotfix hoặc gây outage | Review drift và remediation có kiểm soát |
| Không theo dõi certificate expiry | TLS outage khi certificate hết hạn | Inventory, renewal và alert sớm |
| Không kiểm tra backup restore | Backup hỏng hoặc key không truy cập | Restore drill định kỳ |
| Không đo change failure rate | Lặp lại maintenance gây incident | Post-change review và trend metric |
| Giữ resource idle vô hạn | Chi phí và bề mặt tấn công tăng | TTL/tag/owner và lifecycle cleanup |

## 26. Quy trình thiết kế và triển khai

1. **Lập inventory:** resource, software, version, owner, region, tenant, dependency và cost.
2. **Xác định support lifecycle:** EOL, advisory, certificate expiry, API deprecation và provider notice.
3. **Đặt policy:** patch SLA, maintenance window, exception, approval và emergency path.
4. **Ưu tiên risk:** exploitability, exposure, impact, data sensitivity và blast radius.
5. **Chọn chiến lược thay đổi:** in-place, rolling, canary, blue-green hoặc immutable replacement.
6. **Kiểm tra trước:** compatibility, test, capacity, backup, key/secret và dependency.
7. **Triển khai theo wave:** batch size, concurrency, health gate và stop condition.
8. **Xác minh sau:** version thực chạy, business workflow, security scan, performance và replication.
9. **Đóng thay đổi:** evidence, exception, inventory/CMDB và owner acknowledgement.
10. **Quản lý drift/capacity:** right-size, quota, lifecycle tier và cleanup.
11. **Decommission:** migrate, export, revoke, delete và kiểm tra residual access/data.
12. **Review:** patch latency, compliance, change failure, cost và runbook improvements.

## 27. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Maintenance có canary/rolling và capacity headroom? Backup/PITR/rollback đã thử? Có dừng rollout khi health gate fail? |
| **Bảo mật** | Asset inventory và patch SLA đầy đủ? Credential/certificate được rotate? EOL asset và exception có kiểm soát? |
| **Hiệu quả hiệu năng** | Patch/reboot có ảnh hưởng latency? Capacity còn lại khi drain node? Database/storage/network có được benchmark sau upgrade? |
| **Tối ưu chi phí** | Có resource idle/orphaned? Storage tier/compute right-size? Chi phí maintenance và temporary blue-green được dự báo? |
| **Khả năng vận hành** | Có owner, runbook, change record, drift detection, inventory, alert và evidence sau maintenance? |

### Checklist nghiệm thu

- [ ] Inventory bao phủ cloud resources, runtime, package, certificate, secret và dependency.
- [ ] Resource có owner, environment, region, support date và lifecycle state.
- [ ] Có patch policy và SLA theo risk/exposure.
- [ ] Vulnerability assessment xét exploitability, exposure và business impact.
- [ ] Emergency patch có approval path, mitigation và hậu kiểm.
- [ ] Artifact/image có provenance, signature/digest và scan phù hợp.
- [ ] Deployment dùng canary/rolling/wave hoặc phương án downtime được chấp nhận.
- [ ] Capacity headroom đủ khi drain/reboot một nhóm node.
- [ ] Backup/PITR/key access và rollback/forward-fix được xác minh.
- [ ] Database, Kubernetes, network và managed-service upgrade có compatibility plan.
- [ ] Drift có detection, owner và remediation guardrail.
- [ ] Certificate/secret/identity expiry có inventory và alert.
- [ ] Decommission kiểm tra dependency, data retention, secret, IP, DNS, snapshot và backup.
- [ ] Exception có risk owner, compensating control và expiry.
- [ ] Metrics đo patch coverage, patch latency, unsupported assets và change failure.
- [ ] Runbook, post-maintenance review và restore/rollback drill đã được thực hành.

## 28. Bài tập áp dụng

Một nền tảng đặt thuê thiết bị chạy trên ba availability zone. Hệ thống có 40 VM chạy một OS sắp hết hỗ trợ, 25 microservices đóng gói container, một Kubernetes cluster, database managed service và nhiều certificate nội bộ. Nhà cung cấp thông báo database engine version hiện tại sẽ hết hỗ trợ trong 90 ngày. Một lỗ hổng nghiêm trọng vừa được công bố trong base image đang dùng; một số tenant chạy workload lớn và không thể chấp nhận downtime dài.

Hãy thiết kế:

1. Inventory nào cần thu thập để biết đầy đủ asset, version, owner và dependency?
2. Phân loại ưu tiên giữa zero-day/base image, OS end-of-support và database engine EOL.
3. Chiến lược thay 40 VM sang OS mới theo cohort, giữ capacity khi drain node.
4. Pipeline rebuild/scan/sign container image và đảm bảo runtime thật sự dùng digest mới.
5. Kế hoạch nâng Kubernetes control plane, node pool, CNI/CSI và API deprecation.
6. Kế hoạch database upgrade có backup/PITR, compatibility test, canary hoặc replica-based migration.
7. Cách renew/rotate certificate và secret liên quan tới service sau maintenance.
8. Change window, emergency path, rollback/forward-fix và stop condition.
9. Quy trình decommission OS/image/resource cũ, xóa credential và xử lý snapshot/backup theo retention.
10. Metric nào chứng minh patch coverage, patch latency, availability và change failure ở mức mục tiêu?

Một phương án có cơ sở sẽ xử lý lỗ hổng đang exposed theo emergency path trước, đồng thời lập kế hoạch chuyển OS/EOL và database upgrade theo wave. Container image được rebuild từ base image đã vá, kiểm tra provenance và rollout theo digest. Kubernetes upgrade theo version compatibility và node disruption budget. Database chỉ chuyển khi PITR, replication/restore, driver và application compatibility đã được thử; resource cũ chỉ retire sau khi traffic, data, secret và dependency đã được chuyển/thu hồi đúng policy.

**Điểm cốt lõi:** bảo trì và vòng đời tài nguyên là một phần của kiến trúc, không phải công việc phụ sau triển khai. Inventory và ownership giúp biết cần bảo trì gì; risk-based patching xác định ưu tiên; canary/rolling và backup giới hạn tác động; verification chứng minh thay đổi có hiệu lực; decommission an toàn loại bỏ chi phí, dữ liệu tồn dư và quyền truy cập không còn cần thiết.
