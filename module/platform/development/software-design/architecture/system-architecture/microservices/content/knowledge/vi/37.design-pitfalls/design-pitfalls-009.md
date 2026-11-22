# Chọn nền tảng phức tạp khi chưa có năng lực vận hành

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Sai lầm thiết kế. Tài liệu phân tích sai lầm lựa chọn một nền tảng có độ phức tạp vận hành cao trước khi tổ chức có đủ con người, kỹ năng, quy trình, ngân sách và mức độ trưởng thành để vận hành nó. Các ví dụ gồm Kubernetes, service mesh, Kafka, multi-region, event streaming, self-hosted observability, workflow orchestration và data platform. Trọng tâm là đánh giá vấn đề thực tế, năng lực vận hành, tổng chi phí sở hữu, rủi ro, lựa chọn đơn giản hơn và lộ trình áp dụng từng bước.

## 1. Bản chất của sai lầm

Một tổ chức có thể chọn Kubernetes, service mesh, Kafka, event sourcing, multi-region hoặc một nền tảng dữ liệu phân tán vì các công nghệ đó xuất hiện trong kiến trúc của những công ty lớn. Nhưng việc một nền tảng giải quyết được vấn đề ở tổ chức khác không chứng minh rằng nó phù hợp với quy mô, tải, kỹ năng và mục tiêu hiện tại của mình.

Sai lầm xảy ra khi **độ phức tạp của nền tảng vượt quá năng lực thực tế để thiết kế, triển khai, bảo mật, giám sát, nâng cấp, khắc phục sự cố và chịu trách nhiệm cho nó**.

Những biểu hiện thường gặp:

- Đưa Kubernetes vào khi nhóm chưa có người hiểu scheduling, networking, storage, resource requests/limits, security context và cluster upgrades.
- Triển khai service mesh trước khi có nhu cầu rõ về mTLS, traffic policy, service identity hoặc telemetry ở tầng mạng.
- Dùng Kafka cho mọi luồng bất đồng bộ dù queue managed đơn giản đã đáp ứng delivery, retry và throughput.
- Tự vận hành Prometheus, Grafana, Loki, Tempo, Elasticsearch hoặc một observability stack lớn khi không có đội chịu trách nhiệm backup, scaling, retention và upgrades.
- Thiết kế multi-region active-active dù nghiệp vụ chưa có yêu cầu RTO/RPO tương ứng và dữ liệu chưa có cơ chế giải quyết conflict.
- Chọn workflow engine phân tán trong khi quy trình chỉ gồm vài bước đồng bộ, không cần durable orchestration.
- Dùng nhiều database, cache, broker và control plane khác nhau chỉ vì mỗi công nghệ có một tính năng hấp dẫn.
- Xây platform nội bộ lớn trước khi có đủ workload và người dùng để biện minh cho chi phí.

Hệ quả không chỉ là hóa đơn hạ tầng cao. Nhóm phải dành thời gian cho nền tảng thay vì sản phẩm; sự cố cần nhiều chuyên gia hơn; release chậm; cấu hình trở nên khó hiểu; một thay đổi nhỏ có thể chạm nhiều lớp; tổ chức phụ thuộc vào vài cá nhân hiểu hệ thống.

**Một nền tảng tốt là nền tảng giải quyết được vấn đề với tổng chi phí và rủi ro phù hợp, đồng thời tổ chức có thể vận hành nó một cách bền vững.**

## 2. Phân biệt độ hiện đại và mức phù hợp

Công nghệ mới hoặc mạnh hơn không tự động tạo ra kiến trúc tốt hơn.

| Tiêu chí | Câu hỏi cần trả lời |
| --- | --- |
| Business fit | Nền tảng giải quyết yêu cầu nghiệp vụ cụ thể nào? |
| Technical fit | Nó đáp ứng throughput, latency, availability, consistency và security nào? |
| Operational fit | Ai triển khai, theo dõi, nâng cấp và xử lý sự cố? |
| Organizational fit | Các nhóm có quyền, kỹ năng và thời gian cần thiết không? |
| Economic fit | Tổng chi phí sở hữu có tương xứng với giá trị không? |
| Evolutionary fit | Có thể áp dụng từng phần, rollback và thay thế khi giả định thay đổi không? |

Một hệ thống nhỏ có thể vận hành rất tốt với managed application platform, một relational database, một queue và một pipeline CI/CD đơn giản. Một hệ thống lớn có thể cần Kubernetes, service mesh và streaming platform. Cả hai đều có thể là lựa chọn đúng trong bối cảnh riêng.

Không đánh giá kiến trúc bằng số lượng công nghệ, số diagram hoặc độ phức tạp của deployment. Hãy đánh giá bằng kết quả: hệ thống có đáp ứng nhu cầu, phục hồi được, bảo mật được, thay đổi được và có thể được duy trì với nguồn lực hiện có hay không.

## 3. Nền tảng tạo ra một nghĩa vụ vận hành dài hạn

Mỗi nền tảng bổ sung thêm một tập trách nhiệm:

- Cài đặt và bootstrap.
- Cấu hình network, identity và access control.
- Provisioning, scaling và capacity planning.
- Monitoring, alerting và incident response.
- Backup, restore và disaster recovery.
- Patch, upgrade và compatibility.
- Certificate, secret và key rotation.
- Quản lý phiên bản client/agent/operator.
- Cost allocation và budget.
- Documentation, onboarding và training.
- Security review và vulnerability remediation.
- Migration, deprecation và decommission.

Một demo thành công chỉ chứng minh rằng công nghệ có thể chạy trong điều kiện demo. Nó không chứng minh rằng tổ chức có thể vận hành công nghệ đó trong 3 năm, trong giờ cao điểm, khi người hiểu hệ thống nghỉ phép hoặc khi nhà cung cấp thay đổi API.

Trước khi chọn nền tảng, hãy ghi rõ **ai sẽ làm từng công việc vận hành**. Nếu câu trả lời cho phần lớn nhiệm vụ là “sau này Platform Team sẽ lo”, nghĩa vụ đã bị trì hoãn chứ chưa được giải quyết.

## 4. Bắt đầu từ vấn đề, không bắt đầu từ tên công nghệ

Một quy trình lựa chọn nên đi theo thứ tự:

1. Mô tả vấn đề hiện tại bằng dữ liệu.
2. Xác định tác động đến người dùng và nghiệp vụ.
3. Ghi các giới hạn kỹ thuật bắt buộc.
4. Xác định mục tiêu có thể đo được.
5. Liệt kê phương án đơn giản đang có.
6. Ước lượng chi phí và rủi ro của từng phương án.
7. Đánh giá năng lực vận hành.
8. Chọn thử nghiệm nhỏ có thể rollback.
9. Đo kết quả trước khi mở rộng.

Ví dụ, câu “chúng ta cần Kubernetes” chưa phải problem statement. Các phát biểu có thể kiểm chứng hơn:

- Deploy hiện tại mất 25 phút và thường cần thao tác thủ công.
- Một dịch vụ cần scale độc lập từ 5 lên 40 replicas trong vài phút.
- Môi trường test của từng nhóm bị cấu hình lệch nhau.
- Việc phân bổ tài nguyên giữa workload đang gây contention.
- Nhóm cần chuẩn hóa deployment và policy cho nhiều workload.

Sau đó mới đánh giá liệu Kubernetes, managed container service, PaaS hoặc một cải tiến pipeline có giải quyết đúng nguyên nhân với chi phí phù hợp.

## 5. Dùng dữ liệu baseline để tránh overengineering

Trước khi đầu tư nền tảng mới, cần có baseline:

| Lĩnh vực | Baseline nên đo |
| --- | --- |
| Traffic | Requests/s, peak-to-average ratio, burst duration |
| Latency | p50, p95, p99 và deadline theo hành trình |
| Availability | SLI/SLO, downtime, error budget |
| Deployment | Lead time, deployment frequency, rollback rate |
| Operations | Incidents, MTTR, pages, toil hours |
| Capacity | CPU, memory, connection pools, queue depth |
| Data | Dataset size, growth, write rate, replication lag |
| Cost | Compute, storage, network, license, engineering time |
| Team | Số người trực, kỹ năng, coverage, bus factor |
| Complexity | Số runtime, control plane, dependencies và quy trình thủ công |

Không cần thu thập mọi metric trước khi ra quyết định. Chọn số liệu liên quan trực tiếp tới vấn đề. Nhưng nếu chưa biết hệ thống đang chậm ở đâu, thiếu năng lực nào hoặc chi phí hiện tại là bao nhiêu, rất dễ mua công nghệ để giải quyết một giả thuyết chưa được kiểm chứng.

## 6. Năng lực vận hành là một tiêu chí kiến trúc

Một nền tảng chỉ phù hợp khi có năng lực tương ứng. Có thể đánh giá theo các chiều:

- **Build:** cài đặt, cấu hình và tự động hóa provisioning.
- **Operate:** theo dõi health, capacity, logs, metrics và alerts.
- **Secure:** identity, RBAC, network policy, encryption, patching.
- **Recover:** backup, restore, failover, incident command.
- **Upgrade:** version compatibility, migration, rollback.
- **Support:** onboarding, documentation, escalation và trực vận hành.
- **Govern:** standards, policy, cost allocation và lifecycle.
- **Evolve:** thay đổi kiến trúc mà không làm gián đoạn workload.

Một nhóm có thể hiểu cách deploy ứng dụng lên Kubernetes nhưng chưa đủ khả năng vận hành control plane, CNI, CSI, ingress, DNS, certificate management và cluster upgrade. Phải phân biệt **biết sử dụng nền tảng** với **chịu trách nhiệm cho nền tảng**.

Nếu nhà cung cấp managed service gánh một phần nghĩa vụ, hãy ghi rõ ranh giới shared responsibility. Managed không có nghĩa là không cần vận hành; tổ chức vẫn phải cấu hình đúng, quan sát, bảo mật và xử lý lỗi ở phía mình.

## 7. Ma trận năng lực trước khi áp dụng nền tảng

Có thể dùng ma trận đơn giản:

| Năng lực | Chưa có | Có hỗ trợ | Có thể tự vận hành |
| --- | --- | --- | --- |
| Provisioning | Chưa biết quy trình | Có vendor/platform hỗ trợ | IaC và quy trình đã chuẩn hóa |
| Monitoring | Không có tín hiệu | Có dashboard mẫu | SLO, alerts và runbooks được sở hữu |
| Incident response | Không có escalation | Có chuyên gia hỗ trợ | Rotation và diễn tập thực tế |
| Security | Dùng quyền rộng | Có review định kỳ | Least privilege, audit, rotation |
| Backup/restore | Chưa thử | Có hỗ trợ khôi phục | Restore test và mục tiêu đo được |
| Upgrade | Thực hiện tùy lúc | Có lịch/vendor guide | Compatibility tests, canary, rollback |
| Capacity | Ước lượng cảm tính | Có tư vấn | Forecast và load test |
| Cost | Không phân bổ | Có invoice | Unit economics và budget owner |
| Onboarding | Học truyền miệng | Có tài liệu | Golden path và self-service |
| Ownership | Không rõ owner | Có người hỗ trợ | Team accountable và escalation rõ |

Không nhất thiết phải đạt mức cao nhất ở mọi chiều trước một thử nghiệm nhỏ. Nhưng trước khi đưa nền tảng vào production critical, các năng lực quan trọng phải có owner, quy trình và bằng chứng thực tế.

## 8. Chi phí sở hữu thực tế (TCO)

Không chỉ so sánh giá compute hoặc license. Tổng chi phí sở hữu có thể biểu diễn:

\[
TCO = C_{infra} + C_{license} + C_{network} + C_{storage} + C_{security} + C_{operations} + C_{training} + C_{migration} + C_{risk}
\]

Trong đó:

- `C_infra`: CPU, memory, disk, load balancer, control plane, standby capacity.
- `C_license`: subscription, support contract, per-node hoặc per-usage fees.
- `C_network`: egress, cross-zone/region traffic, private connectivity.
- `C_storage`: snapshots, logs, backups, indexes và retention.
- `C_security`: scanning, key management, audit, compliance và access tooling.
- `C_operations`: giờ kỹ sư, on-call, upgrades, incident response và maintenance.
- `C_training`: học tập, onboarding, certification và knowledge transfer.
- `C_migration`: chuyển workload, data, pipeline và quy trình.
- `C_risk`: downtime, failed releases, recovery delay và vendor/platform lock-in.

Chi phí kỹ sư là phần thường bị bỏ qua. Một nền tảng tự host có thể có compute bill thấp hơn managed service nhưng cần một nhóm chuyên trách để nâng cấp, mở rộng, backup và ứng cứu. Nếu nhóm đó chưa tồn tại, chi phí thực không bằng 0; nó được trả bằng thời gian của developer và sự cố.

### 8.1. Tính chi phí cơ hội

Giả sử hai kỹ sư dành trung bình 25% thời gian mỗi tuần để duy trì nền tảng, trong 48 tuần làm việc:

\[
2 \times 0.25 \times 48 = 24 \text{ engineer-weeks/year}
\]

Đây là ước tính thời gian, chưa quy đổi thành tiền. Hãy so sánh 24 engineer-weeks với lợi ích thực tế như giảm deployment time, tăng reliability hoặc giảm cloud spend. Nếu nền tảng chưa tạo ra lợi ích tương ứng, có thể cần managed option hoặc giảm phạm vi.

## 9. Complexity budget: mỗi thành phần mới cần biện minh

Mỗi công nghệ bổ sung tạo thêm:
- Một khái niệm cần học.
- Một cấu hình cần quản lý.
- Một failure mode mới.
- Một phiên bản cần nâng cấp.
- Một bộ quyền và bí mật cần bảo vệ.
- Một nơi lưu telemetry.
- Một quy trình backup/recovery.
- Một nhóm hoặc vendor cần liên hệ.
- Một dependency trong deployment và incident path.

Có thể xem đây là **ngân sách độ phức tạp**. Một thành phần mới nên được thêm khi lợi ích đo được vượt chi phí và rủi ro mà nó mang lại.

Không cần biến complexity budget thành con số chính xác giả tạo. Hãy dùng nó như câu hỏi trong architecture review: công nghệ mới làm giảm phần phức tạp nào, và phần phức tạp nào được chuyển sang tổ chức?

## 10. Kubernetes: khi nào mạnh, khi nào quá sớm?

Kubernetes cung cấp orchestration cho container workloads, scheduling, desired state, service discovery, rollout, resource management và hệ sinh thái mở rộng.

Nó có thể phù hợp khi:
- Có nhiều workload container cần một nền tảng thống nhất.
- Cần scheduling và resource isolation ở quy mô đáng kể.
- Deployment/rollout cần chuẩn hóa.
- Có nhu cầu portability hoặc ecosystem operators.
- Có đội/platform capability chịu trách nhiệm cluster lifecycle.
- Có yêu cầu autoscaling, policy và multi-team tenancy mà PaaS hiện tại không đáp ứng.

Nó có thể quá sớm khi:
- Chỉ có vài service và một deployment target đơn giản.
- Nhóm chưa có người vận hành networking, storage, RBAC và upgrades.
- Vấn đề hiện tại là CI/CD yếu hoặc cấu hình thủ công, có thể sửa bằng pipeline.
- Không có nhu cầu orchestration đủ lớn để bù chi phí control plane.
- Mỗi service cần một bộ chart/operator tùy biến riêng.
- Cluster có nhiều add-ons nhưng không ai hiểu failure modes.
- Team dành nhiều thời gian debug YAML hơn cải thiện sản phẩm.

### 10.1. Các lớp vận hành Kubernetes thường bị đánh giá thấp

- Cluster lifecycle và version upgrades.
- Control plane availability.
- Container runtime và node pools.
- CNI, DNS, ingress và network policies.
- CSI, persistent volumes và snapshot behavior.
- Scheduling, taints, tolerations và topology spread.
- Requests, limits, quotas và autoscaling.
- RBAC, admission policies, workload identity.
- Secrets, certificates và rotation.
- Operators, CRDs và compatibility.
- Observability, audit logs và cluster events.
- Backup/restore cho cluster state và application data.

Managed Kubernetes giảm một số trách nhiệm control plane nhưng không tự vận hành workload, node pools, network policy, storage, upgrades của add-ons hoặc ứng dụng.

### 10.2. Lựa chọn đơn giản hơn

Có thể bắt đầu với:
- Managed application platform hoặc PaaS.
- Managed container service.
- Một vài VM/container host được quản lý bằng IaC.
- Managed serverless container runtime.
- Platform do cloud provider cung cấp với deployment workflow đơn giản.

Khi số workload, nhu cầu isolation, scheduling và team autonomy tăng, có thể đánh giá Kubernetes bằng pilot có tiêu chí rõ.

## 11. Service mesh: đừng dùng để che vấn đề ở tầng ứng dụng

Service mesh có thể cung cấp mTLS, service identity, traffic routing, retries, timeouts, telemetry và policy ở tầng network proxy/control plane.

Nhưng mesh cũng thêm:
- Sidecar hoặc ambient dataplane lifecycle.
- Control plane và certificate management.
- Proxy resource overhead.
- Version compatibility và upgrade.
- Debugging giữa application và proxy.
- Policy conflicts và routing complexity.
- Một failure domain mới khi control plane hoặc configuration gặp lỗi.

Mesh có thể phù hợp khi số lượng service và yêu cầu bảo mật/traffic policy đã đủ lớn, có nhu cầu thống nhất mTLS/service identity, traffic shifting hoặc telemetry mà ứng dụng khó tự triển khai nhất quán.

Không nên triển khai chỉ vì muốn có retry, timeout hoặc tracing. Các chức năng này có thể đã được đáp ứng ở HTTP client, gateway, library hoặc observability platform. Retry ở cả mesh và ứng dụng có thể nhân số request, gây retry storm. Timeout không đúng deadline có thể khiến caller nghĩ request đã dừng trong khi downstream vẫn tiếp tục xử lý.

**Trước khi thêm mesh, hãy kiểm tra xem vấn đề có thể được giải quyết bằng client configuration, gateway policy, platform identity hoặc một thư viện dùng chung hẹp hơn không.**

## 12. Kafka và event streaming: phân biệt queue với streaming platform

Kafka mạnh khi cần:
- Event log có retention và replay.
- Nhiều consumer độc lập.
- Throughput lớn và partitioned parallelism.
- Stream processing.
- Event sourcing hoặc CDC với semantics phù hợp.
- Consumer có thể đọc lại dữ liệu theo offset.

Nhưng Kafka đòi hỏi hiểu:
- Partitioning và key selection.
- Ordering chỉ trong phạm vi partition.
- Consumer groups và rebalancing.
- Offset commit semantics.
- Retention, compaction và storage.
- Replication, ISR và broker lifecycle.
- Schema evolution.
- Idempotency và duplicate delivery.
- DLQ/retry strategy.
- Capacity, network và cross-region replication.

Nếu chỉ cần gửi một job tới một worker, queue managed có thể đơn giản hơn. Nếu cần một event được nhiều consumer xử lý độc lập và replay, streaming log có thể đáng giá. Không chọn Kafka chỉ vì hệ thống có microservices.

### 12.1. Các câu hỏi trước khi chọn broker

- Có cần replay event trong nhiều ngày/tháng không?
- Có bao nhiêu consumer độc lập?
- Có yêu cầu ordering nào, theo key hay toàn hệ thống?
- Throughput/retention thực tế bao nhiêu?
- Ai sở hữu cluster và schema registry?
- Ai xử lý partition skew, lag và broker upgrades?
- Có thể dùng managed queue/pub-sub không?
- Có cần event log hay chỉ cần delivery?
- Business effects có idempotent không?
- Recovery khi consumer offset và database state lệch được xử lý ra sao?

## 13. Multi-region: chi phí và semantics trước sơ đồ đẹp

Multi-region có thể cải thiện disaster recovery hoặc giảm latency địa lý, nhưng thêm:
- Data replication và lag.
- Failover/failback.
- DNS/global traffic management.
- Identity, secrets và certificates ở từng vùng.
- Capacity dự phòng.
- Cross-region egress.
- Split-brain và writer fencing.
- Data residency và compliance.
- Operational coverage theo timezone.
- Kiểm thử phục hồi định kỳ.

Nếu doanh nghiệp chỉ cần RTO vài giờ, backup/PITR và một vùng khôi phục có thể đáp ứng với chi phí thấp hơn active-active. Nếu yêu cầu RTO vài phút và không thể chịu gián đoạn dài, warm standby hoặc active-passive có thể hợp lý. Active-active chỉ nên chọn khi dữ liệu, conflict resolution, routing và tổ chức vận hành đã được thiết kế cho mô hình đó.

**Không suy ra nhu cầu multi-region từ việc có khách hàng ở nhiều quốc gia.** Latency, data residency, availability và DR là những yêu cầu khác nhau; cần đo và xác định riêng.

## 14. Self-hosted observability: không chỉ là cài Grafana

Một stack observability tự vận hành có thể gồm metrics backend, log store, trace backend, collectors, object storage, query frontend, alert manager và dashboard.

Nó tạo trách nhiệm:
- Ingestion capacity và cardinality control.
- Retention, compaction và indexing.
- Storage tiering và lifecycle.
- Query performance.
- High availability và backups.
- Upgrade và schema compatibility.
- Access control và data redaction.
- Alerting cho chính observability platform.
- Cost attribution và capacity forecast.

Nếu không có đội chuyên trách, managed observability có thể có TCO thấp hơn khi tính cả nhân lực và incident risk. Có thể self-host một thành phần cụ thể nếu có lý do residency/cost/control và có owner thật, thay vì tự host mọi thứ cùng lúc.

## 15. Workflow engine và orchestration: chọn đúng mức abstraction

Một workflow engine có thể cung cấp durable state, retry, timeout, compensation, scheduling và visibility cho quy trình dài hạn. Nó hữu ích cho saga, human approval, multi-day workflow hoặc orchestration có trạng thái phức tạp.

Nhưng nó cũng thêm:
- Workflow definition/versioning.
- State persistence.
- Worker lifecycle.
- Replay semantics.
- Activity idempotency.
- Schema/version compatibility.
- Upgrade và operational monitoring.
- Debugging workflow history.
- Capacity và retention.

Nếu luồng chỉ gọi ba service trong vài giây và không có yêu cầu durable workflow, một application service với queue/outbox có thể đơn giản hơn. Ngược lại, một quy trình kéo dài nhiều ngày, có retry và human intervention có thể xứng đáng dùng workflow engine.

## 16. Chọn nền tảng theo độ trưởng thành của tổ chức

Một lộ trình trưởng thành có thể gồm:

**Giai đoạn A – Basic delivery**
- Build/test/deploy tự động.
- Runtime và database được quản lý.
- Logs, metrics và alerts cơ bản.
- Một service owner và runbook.
- Backup/restore được thử.

**Giai đoạn B – Standardized operations**
- IaC và environment parity.
- SLO/error budget.
- Centralized observability.
- Secrets/IAM chuẩn.
- Release safety và rollback.
- On-call/escalation.

**Giai đoạn C – Platform capabilities**
- Self-service provisioning.
- Multi-team workload isolation.
- Standard templates/golden paths.
- Policy as code.
- Capacity/cost governance.
- Automated recovery workflows.

**Giai đoạn D – Advanced distributed operations**
- Service mesh nếu có nhu cầu rõ.
- Streaming platform có schema governance.
- Multi-region failover.
- Advanced traffic management.
- Automated chaos/game days.
- Platform SRE và productized internal platform.

Đây không phải maturity model bắt buộc theo thứ tự. Một tổ chức có thể cần một năng lực nâng cao rất sớm vì yêu cầu pháp lý hoặc tải đặc thù. Điều quan trọng là có bằng chứng và năng lực tương ứng trước khi mở rộng phạm vi.

## 17. Chọn managed service hay tự vận hành?

| Phương án | Lợi ích | Nghĩa vụ còn lại |
| --- | --- | --- |
| Managed service | Giảm công việc control plane, patching hoặc scaling tùy sản phẩm | Configuration, IAM, data, monitoring, limits, vendor dependency |
| Self-hosted | Kiểm soát sâu, portability và khả năng tùy biến | Full lifecycle, upgrades, HA, backup, security, on-call |
| Platform nội bộ | Chuẩn hóa trải nghiệm nhiều team | Product management, roadmap, support, reliability, adoption |
| Hybrid | Chọn nơi cần control và nơi cần giảm toil | Tích hợp, data flow, policy và vận hành nhiều mô hình |

Đừng so sánh giá managed với compute bill self-hosted. So sánh theo workload, availability target, retention, staffing và thời gian duy trì.

Managed service cũng có thể tạo vendor lock-in hoặc giới hạn customization. Hãy đánh giá exit path, export format, data portability, API limits và contract terms.

## 18. Architecture decision record (ADR) cho nền tảng

Một quyết định chọn nền tảng nên ghi lại:

~~~markdown
# ADR: Chọn nền tảng chạy container

## Context
- Vấn đề hiện tại:
- Tác động người dùng:
- Baseline và dữ liệu:
- Constraints:

## Decision drivers
- Scale:
- Availability/RTO/RPO:
- Security/compliance:
- Deployment frequency:
- Team skills/coverage:
- Budget/TCO:

## Options
- Option A: tiếp tục nền tảng hiện tại
- Option B: managed container platform
- Option C: Kubernetes managed
- Option D: Kubernetes self-hosted

## Decision
- Phương án được chọn:
- Phạm vi áp dụng:
- Điều kiện/assumptions:

## Consequences
- Lợi ích:
- Operational responsibilities:
- Cost:
- Failure modes:
- Migration/rollback:
- Exit strategy:

## Revisit triggers
- Metric/threshold:
- Ngày review:
- Owner:
~~~

ADR không phải thủ tục giấy tờ để hợp thức hóa quyết định đã chốt. Nó giúp nhóm hiểu vì sao một lựa chọn phù hợp trong điều kiện cụ thể và khi nào cần xem xét lại.

## 19. Scorecard lựa chọn nền tảng

Có thể dùng điểm 1–5 cho các tiêu chí, nhưng phải ghi trọng số và bằng chứng:

| Tiêu chí | Trọng số ví dụ | Câu hỏi |
| --- | ---: | --- |
| Business value | 20% | Giải quyết pain point nào? |
| Technical fit | 15% | Đạt latency, throughput, availability không? |
| Operational capability | 20% | Ai vận hành và có kỹ năng gì? |
| Security/compliance | 15% | Đáp ứng identity, data, audit và policy? |
| TCO | 15% | Chi phí 3 năm gồm cả nhân lực? |
| Migration/exit | 10% | Có rollback và đường rút lui? |
| Developer experience | 5% | Có giảm friction và tăng autonomy? |

Trọng số chỉ là ví dụ. Với hệ thống xử lý dữ liệu nhạy cảm, security có thể có trọng số cao hơn; với startup nhỏ, operational capability và time-to-market có thể quan trọng hơn. Không dùng tổng điểm để che một điều kiện bắt buộc bị fail: nếu không có người trực hoặc không có recovery plan cho một nền tảng critical, điểm trung bình cao không đủ để đưa vào production.

## 20. Pilot nhỏ trước khi mở rộng

Một pilot có mục tiêu:
- Kiểm chứng một workload đại diện.
- Đo chi phí và effort thực tế.
- Kiểm tra build/deploy/rollback.
- Kiểm tra observability và alert routing.
- Diễn tập một failure mode.
- Xác định quyền và escalation.
- Đánh giá onboarding của người không tham gia pilot.
- Xác định điều kiện scale hoặc dừng.

Pilot cần timebox và success criteria. Ví dụ:
- Deployment từ commit đến healthy dưới 10 phút.
- Rollback đã thử và hoàn tất trong ngưỡng đã thống nhất.
- Team thứ hai có thể deploy theo tài liệu.
- Chi phí môi trường nằm trong budget.
- Có người trực và runbook.
- Backup/restore đạt mục tiêu đã đặt.

Các số trên là minh họa. Không dùng một pilot trên workload nhẹ để suy rộng sang toàn bộ production. Chọn workload đủ đại diện cho network, storage, security và scale cần kiểm chứng.

## 21. Thiết kế lộ trình adoption có thể đảo ngược

Thay đổi nền tảng nên có các bước:

1. **Observe:** thu baseline và xác định giới hạn hiện tại.
2. **Prototype:** thử trên workload nhỏ, dữ liệu synthetic.
3. **Pilot:** triển khai một service ít rủi ro với monitoring và rollback.
4. **Operate:** chạy trong thời gian đủ dài để gặp upgrades, incidents và capacity changes.
5. **Standardize:** tạo template, runbook, policy và self-service.
6. **Expand:** thêm workload theo điều kiện.
7. **Review:** so sánh lợi ích với TCO và toil.
8. **Exit or evolve:** giữ, thay thế hoặc thu hẹp khi giả định thay đổi.

Mỗi bước cần owner và tiêu chí dừng. Nếu pilot không chứng minh được lợi ích hoặc phát hiện thiếu năng lực, có thể dừng mà không phải di chuyển toàn bộ hệ thống.

## 22. Golden path giúp giảm gánh nặng cho người dùng nền tảng

Một platform team nên cung cấp một con đường chuẩn:
- Template service và repository.
- CI/CD pipeline mặc định.
- Logging, metrics và tracing có sẵn.
- Health/readiness checks.
- Secret management và workload identity.
- Deployment strategy.
- Resource requests/limits và autoscaling baseline.
- Runbook/service catalog metadata.
- Backup/restore patterns khi cần.
- Cost tags và policy checks.

Golden path nên có **sensible defaults** và khả năng escape có kiểm soát. Nếu mỗi team phải tự viết Helm chart, policy, dashboard và pipeline, nền tảng mới chỉ chuyển độ phức tạp từ hạ tầng sang developer.

Không xây platform nội bộ quá lớn trước khi có người dùng và workload. Bắt đầu bằng template, automation nhỏ và feedback thật; mở rộng theo nhu cầu lặp lại.

## 23. Platform team cũng cần năng lực vận hành

Nếu một tổ chức tạo Platform Team nhưng nhóm này chỉ có một hoặc hai người không có backup, platform trở thành single point of failure mới.

Platform team cần:
- Product owner hoặc người ưu tiên roadmap.
- Service ownership và on-call.
- SLO cho năng lực nền tảng.
- Incident process và escalation.
- Upgrade/patch lifecycle.
- Security and access management.
- Capacity/cost budget.
- Documentation và support boundaries.
- User feedback và adoption metrics.
- Disaster recovery cho control plane/configuration.

Các nhóm sản phẩm cần biết phần nào platform chịu trách nhiệm, phần nào workload owner chịu trách nhiệm. Một platform contract tốt mô tả API, SLO, limits, support và cách escalation.

## 24. Shared responsibility matrix

Ví dụ với managed Kubernetes:

| Công việc | Cloud provider | Platform team | Application team |
| --- | --- | --- | --- |
| Control plane availability | Chủ yếu | Theo dõi/thiết kế usage | Không quản lý trực tiếp |
| Node pools | Theo hợp đồng | Provision, upgrade, capacity | Đặt resource requests/limits |
| CNI/ingress | Một phần theo dịch vụ | Cấu hình và vận hành | Khai báo service behavior |
| RBAC/workload identity | Cơ chế nền tảng | Thiết kế policy | Dùng quyền đúng |
| App deployment | Không | Golden path/tooling | Release và rollback |
| App SLO | Không | Cung cấp observability | Sở hữu behavior |
| Backup business data | Tùy dịch vụ | Cung cấp pattern/tool | Chọn policy và kiểm tra restore |
| Incident | Hỗ trợ theo contract | Cluster/platform incident | Application/business incident |

Bảng cần được điều chỉnh theo dịch vụ và hợp đồng cụ thể. Đừng giả định cloud provider chịu trách nhiệm cho dữ liệu ứng dụng, quyền truy cập hoặc cấu hình sai.

## 25. Năng lực cần có trước khi vận hành Kubernetes

Một nhóm cần tối thiểu hiểu hoặc có đường hỗ trợ rõ về:
- Container image, runtime và supply chain.
- Pods, deployments, services, ingress.
- DNS và network policies.
- Requests/limits, quotas, autoscaling.
- ConfigMaps, secrets và workload identity.
- Persistent volumes, storage classes và backup.
- Readiness/liveness/startup probes.
- Rolling update, canary và rollback.
- RBAC và admission policies.
- Node drain, disruption budgets và scheduling.
- Cluster upgrade và add-on compatibility.
- Monitoring, logs, events và troubleshooting.
- Incident response và capacity planning.

Không nhất thiết mọi developer phải là Kubernetes expert. Nhưng platform owner phải có kỹ năng chuyên sâu và application teams phải hiểu các khái niệm ảnh hưởng tới workload của mình.

## 26. Năng lực cần có trước khi vận hành Kafka

Các năng lực quan trọng:
- Partition key và ordering semantics.
- Consumer group, offset và rebalance.
- Delivery semantics và idempotency.
- Retry topic, DLQ và replay.
- Schema evolution và registry.
- Retention, compaction và storage.
- Broker capacity, replication và ISR.
- Authentication, ACL và encryption.
- Monitoring lag/oldest age/throughput.
- Disaster recovery và cross-cluster replication.
- Consumer backpressure và poison messages.
- Reconciliation khi database state và offsets lệch.

Nếu không có người hiểu các semantics này, dùng managed queue với contract đơn giản hơn có thể giảm rủi ro đáng kể.

## 27. Năng lực cần có trước khi vận hành service mesh

- Service identity và certificate lifecycle.
- mTLS policy và trust boundaries.
- Sidecar/ambient proxy resource overhead.
- Traffic routing, retries, timeouts và circuit breaking.
- Proxy upgrades và control plane.
- Debugging request path.
- Observability pipeline.
- Network policy và egress.
- Failure mode khi proxy/control plane unavailable.
- Rollback và canary mesh configuration.
- Compatibility với app protocols và health checks.

Một mesh có thể tạo cảm giác rằng security và resilience được giải quyết tự động. Thực tế, policy sai có thể chặn mọi traffic; retry policy sai có thể nhân tải; mTLS misconfiguration có thể làm cả service graph mất kết nối.

## 28. Năng lực cần có trước khi vận hành multi-region

- Data replication semantics và lag.
- Writer fencing và split-brain prevention.
- RTO/RPO theo business domain.
- DNS/global traffic routing.
- Identity, KMS, secrets và certificates.
- Capacity ở recovery region.
- Cross-region network cost.
- Backup độc lập với replication.
- Failover/failback runbooks.
- Synthetic end-to-end validation.
- Reconciliation cho dữ liệu nghiệp vụ.
- Incident coverage theo timezone.
- Residency/compliance constraints.

Không coi replica healthy là bằng chứng DR. Phải diễn tập khôi phục và đo kết quả so với mục tiêu.

## 29. Failure mode khi nền tảng quá phức tạp

Một nền tảng mới thường thêm failure modes:
- Control plane outage.
- Version skew.
- Misconfigured policy.
- Certificate expiry.
- Resource exhaustion.
- Queue/partition imbalance.
- Controller/operator failure.
- DNS/network partition.
- Storage latency hoặc volume attach failure.
- Telemetry backend outage.
- Credential/permission drift.
- Upgrade incompatibility.
- Vendor API or quota limit.

Mỗi failure mode cần owner và cách phát hiện. Nếu nhóm chỉ biết happy path mà không biết khi platform degraded, nền tảng có thể làm reliability giảm thay vì tăng.

**Một thiết kế cần tính cả chi phí của việc nền tảng không hoạt động.** Ví dụ nếu service mesh control plane mất, data plane hiện tại có tiếp tục xử lý traffic không? Nếu Kafka cluster mất, Order có thể ghi outbox và tiếp tục hay phải từ chối checkout? Nếu CI platform lỗi, có đường rollback production đang chạy không?

## 30. Operational readiness trước production

Trước khi đưa nền tảng hoặc workload phụ thuộc vào production, cần:
- Owner team và escalation contacts.
- SLO cho nền tảng và service.
- Dashboard, alert và runbook.
- Backup/restore và DR objectives.
- Patch/upgrade cadence.
- Security model và least privilege.
- Capacity/quota forecast.
- Cost budget và attribution.
- Deployment/rollback strategy.
- Incident command và communication.
- On-call training và secondary coverage.
- Vendor/support contacts.
- Exit/decommission strategy.
- Game day hoặc failure exercise phù hợp rủi ro.

Nếu một nền tảng chưa có người trực, runbook hoặc cách restore, hãy giới hạn ở thử nghiệm không critical cho tới khi nghĩa vụ vận hành được giải quyết.

## 31. Quản lý nâng cấp và compatibility

Nền tảng phức tạp thường có nhiều thành phần versioned:
- Kubernetes control plane, nodes và add-ons.
- CNI, CSI, ingress controller, operators.
- Service mesh control/data plane.
- Kafka brokers, clients và schema registry.
- Observability agents, collectors và backends.
- Database engine và extensions.
- CI runners, build images và deployment tooling.

Cần:
1. Version inventory và owner.
2. Supported-version policy.
3. Upgrade calendar.
4. Staging/canary compatibility test.
5. Backup và rollback/forward-fix plan.
6. Deprecation notices.
7. Security patch SLA.
8. Evidence sau nâng cấp.
9. Kế hoạch xử lý version skew.
10. Capacity cho công việc nâng cấp định kỳ.

Nếu không có capacity cho upgrades, nền tảng sẽ dần lỗi thời và tạo security/compatibility risk. Chi phí nâng cấp phải được tính ngay từ lúc chọn công nghệ.

## 32. Security: công nghệ mạnh không tự tạo ra security posture tốt

Một nền tảng có nhiều policy knobs nhưng không có người hiểu chúng có thể tạo cảm giác an toàn sai.

Các câu hỏi:
- Ai quản lý identity và quyền?
- Có least privilege theo workload không?
- Secret và certificate rotation được tự động hóa chưa?
- Network policy có test và review không?
- Audit log được lưu và truy cập thế nào?
- Image/dependency scanning có owner remediation không?
- Backup có immutable/offline khi cần không?
- Control plane và admin endpoints được bảo vệ ra sao?
- Break-glass access có TTL, MFA và audit?
- Có threat model và incident response?

Đừng bật mọi feature security mà không biết tác động vận hành. Nhưng cũng không chọn nền tảng đơn giản hơn bằng cách bỏ qua yêu cầu bắt buộc. Chọn giải pháp có security controls mà tổ chức có thể cấu hình, kiểm tra và duy trì.

## 33. Tác động đến developer experience

Một platform phức tạp có thể làm developer phải:
- Học nhiều DSL và YAML.
- Debug nhiều control plane.
- Chờ pipeline dài.
- Xin quyền qua nhiều bước.
- Tự tạo dashboard, secret và deployment policy.
- Phối hợp nhiều team cho một thay đổi nhỏ.
- Giải quyết lỗi hạ tầng không thuộc domain.
- Giữ kiến thức về quá nhiều phiên bản và tool.

Đo developer experience bằng:
- Time to first deploy.
- Lead time từ commit đến production.
- Thời gian debug pipeline.
- Số bước thủ công.
- Số ticket cần Platform.
- Onboarding time.
- Tỷ lệ developer có thể tự rollback.
- Developer satisfaction theo tác vụ cụ thể.

Một platform nội bộ tốt nên giảm cognitive load của application teams. Nếu yêu cầu mọi developer trở thành chuyên gia của tất cả thành phần nền tảng, thiết kế tổ chức chưa phù hợp.

## 34. Tổ chức ownership và trực vận hành

Mỗi nền tảng cần:
- Accountable team.
- Primary/secondary on-call nếu critical.
- Service catalog entry.
- SLO và support contract.
- Runbook cho failure modes.
- Upgrade owner.
- Security owner/approver.
- Cost center.
- Escalation tới vendor/provider.
- Lifecycle/decommission owner.

Không gán toàn bộ trách nhiệm cho “DevOps” chung chung. Platform team có thể sở hữu Kubernetes; application team sở hữu Order Service; Database team sở hữu database service; Security team định nghĩa policy. Các nhóm cần có ranh giới và cách phối hợp rõ.

Nếu tổ chức chưa đủ người để trực 24/7, hãy chọn mức managed service và support plan phù hợp, hoặc giảm criticality/scope cho tới khi có coverage. Không giả định một kỹ sư duy nhất có thể trực mọi thành phần mọi lúc.

## 35. Ví dụ: chọn Kubernetes quá sớm

### Bối cảnh

Một công ty có 8 microservices, 6 kỹ sư backend và một người phụ trách hạ tầng bán thời gian. Hiện tại các service chạy trên managed container platform. Nhóm muốn chuyển sang Kubernetes vì:
- Nhiều bài viết nói Kubernetes là chuẩn.
- Muốn scale linh hoạt.
- Muốn dùng Helm và service mesh.
- Muốn có thể chạy trên nhiều cloud.
- Một số deployment đang cần thao tác thủ công.

### Rủi ro chưa được tính

- Chưa có owner cho cluster upgrades.
- Chưa có người hiểu CNI/CSI/networking.
- Không có quota/cost monitoring cho namespaces.
- Backup của persistent workloads chưa được kiểm tra.
- Không có runbook cho node pressure hoặc DNS failure.
- Team chưa chuẩn hóa resource requests/limits.
- CI/CD hiện tại đã là bottleneck, Kubernetes không tự sửa nó.
- Portability giữa cloud chưa có business requirement cụ thể.

### Lựa chọn theo từng bước

1. Đo thời gian và lỗi deployment hiện tại.
2. Chuẩn hóa pipeline và health checks trên platform hiện tại.
3. Tạo IaC và deployment templates.
4. Kiểm tra managed container platform có đáp ứng scale/rollout không.
5. Nếu còn khoảng trống, thử một workload ít rủi ro trên managed Kubernetes.
6. Đo TCO và toil sau vài chu kỳ release/upgrade.
7. Chỉ mở rộng khi có owner, backup, runbook và capability coverage.

Có thể kết luận rằng managed container platform vẫn phù hợp; cũng có thể pilot chứng minh Kubernetes đem lại giá trị. Cả hai kết quả đều hợp lệ nếu dựa trên bằng chứng.

## 36. Ví dụ: chọn Kafka khi chỉ cần task queue

Một hệ thống gửi email và tạo hóa đơn sau khi Order được commit. Nhóm triển khai Kafka vì muốn dùng event-driven architecture.

Nhưng workload hiện tại:
- Một consumer cho mỗi loại task.
- Không cần replay nhiều tháng.
- Ordering chỉ cần theo từng order.
- Throughput thấp.
- Retry và DLQ có thể được managed queue đáp ứng.
- Không có đội vận hành broker/schema registry.

Managed queue hoặc broker đơn giản có thể phù hợp hơn. Nếu sau này cần nhiều consumer độc lập, event retention dài, replay hoặc stream processing, có thể đánh giá Kafka với yêu cầu mới.

Điểm quan trọng: **chọn theo delivery semantics và operational requirement**, không chọn theo tên gọi “event-driven”.

## 37. Ví dụ: service mesh trước khi hiểu retry semantics

Một team bật mesh retry cho mọi HTTP 5xx và timeout, đồng thời application client cũng retry ba lần. Khi Payment chậm, mỗi request có thể được nhân lên nhiều lần:
- Application gửi tối đa 4 attempts.
- Mesh retry mỗi attempt thêm 3 lần.
- Một request logic có thể tạo ra nhiều request vật lý hơn dự kiến.
- Downstream bị quá tải và timeout tăng tiếp.

Mesh không tự làm hệ thống resilient nếu retry policy không gắn với idempotency, deadline và retry budget. Trước khi áp dụng mesh, cần hiểu retry hiện tại, thiết lập một nơi chịu trách nhiệm retry, giới hạn attempts và đo request amplification.

## 38. Ví dụ: self-hosted observability nhưng thiếu năng lực lưu trữ

Một nhóm cài Prometheus, Loki và Tempo vào cluster hiện tại. Ban đầu chi phí thấp, nhưng sau vài tháng:
- Log retention tăng.
- Metric cardinality bùng nổ.
- Disk pressure làm collector/backend restart.
- Backup không có hoặc restore chưa thử.
- Upgrade làm schema/index không tương thích.
- On-call của sản phẩm phải xử lý observability outage.

Lựa chọn tốt hơn có thể là:
- Managed backend cho một số signal.
- Self-host một thành phần có volume ổn định và owner.
- Giới hạn retention/sampling/cardinality.
- Tách observability workloads khỏi application resource pool.
- Có SLO, backup, upgrade và cost budget riêng.

Không nên đánh giá self-hosted chỉ bằng compute bill; tính cả thời gian kỹ sư và risk khi telemetry biến mất đúng lúc incident.

## 39. Ví dụ: multi-region active-active khi domain chưa có consistency model

Hai region cùng nhận cập nhật Order. Một client gửi cancel ở Region A trong khi Payment callback xác nhận ở Region B. Nếu không có conflict resolution, writer fencing hoặc aggregate ownership rõ, hệ thống có thể:
- Order chuyển CANCELLED.
- Payment chuyển CAPTURED.
- Một region phát event `OrderCancelled`, region kia phát `OrderPaid`.
- Inventory release reservation trong khi shipment đã bắt đầu.

Active-active không giải quyết consistency tự động. Trước khi chọn, phải xác định command ownership, ordering, idempotency, conflict resolution, compensation và business invariants. Active-passive hoặc một writer region có thể an toàn hơn trong giai đoạn đầu.

## 40. Build vs buy vs managed: đánh giá đúng ranh giới

Khi lựa chọn một nền tảng, có ba hướng:
- **Build:** tự xây capability hoặc vận hành phần mềm mã nguồn mở.
- **Buy:** mua sản phẩm/vendor solution.
- **Managed:** dùng dịch vụ được nhà cung cấp vận hành một phần.

Đánh giá:
- Core competency: đây có phải năng lực tạo khác biệt cho sản phẩm?
- Operational staffing: ai chịu trách nhiệm 24/7?
- Customization: cần tùy biến đến mức nào?
- Compliance/data residency: dữ liệu có được phép ra ngoài?
- Exit cost: có thể export và chuyển sang phương án khác?
- SLA/support: có cam kết và escalation thực?
- Cost curve: giá tăng theo usage ra sao?
- Integration: IAM, observability, deployment và data access.
- Vendor risk: lock-in, roadmap, region availability.

Nếu nền tảng không tạo lợi thế cạnh tranh và managed option đáp ứng yêu cầu, việc tự vận hành có thể không đáng. Nếu cần kiểm soát sâu hoặc có workload đặc thù, self-host có thể hợp lý khi tổ chức đủ năng lực.

## 41. Tổ chức platform team theo nhu cầu thực

Một platform team nên được hình thành từ các nhu cầu lặp lại, không phải từ mong muốn sở hữu nhiều công nghệ.

Có thể bắt đầu bằng:
- Một người/nhóm nhỏ phụ trách golden path CI/CD.
- Một service catalog và template.
- Observability conventions và dashboard mẫu.
- IaC modules có policy.
- Self-service database/broker provisioning.
- Upgrade/patch process.
- Documentation và office hours.

Khi số workload và người dùng tăng, platform có thể phát triển thành sản phẩm nội bộ với roadmap, SLO, support model và cost allocation.

Không nên tạo một team chuyên trách cho mỗi công nghệ khi workload chưa đủ. Một nhóm Platform nhỏ có thể quản lý một số capability chuẩn hóa, còn domain teams sở hữu behavior và dữ liệu của service.

## 42. Dùng maturity gate thay vì checklist công nghệ

Trước khi mở rộng một nền tảng, có thể yêu cầu bằng chứng:
- Có owner và backup owner.
- Có ít nhất một người ngoài nhóm pilot có thể triển khai theo tài liệu.
- Có dashboard và alert actionable.
- Có runbook cho failure modes chính.
- Có rollback hoặc recovery đã thử.
- Có security/access policy.
- Có cost forecast và budget.
- Có version/upgrade policy.
- Có support/escalation.
- Có tiêu chí dừng hoặc exit.

Maturity gate nên theo rủi ro và criticality. Một thử nghiệm sandbox không cần cùng tiêu chuẩn với một control plane phục vụ toàn bộ production. Nhưng khi nền tảng trở thành dependency critical, không thể dựa vào trí nhớ của tác giả.

## 43. Đo giá trị sau khi triển khai

Một nền tảng mới phải chứng minh lợi ích bằng chỉ số:

| Mục tiêu | Chỉ số |
| --- | --- |
| Deploy nhanh hơn | Lead time, deployment duration |
| Release an toàn hơn | Change failure rate, rollback rate |
| Scale tốt hơn | Time to scale, saturation, cost per request |
| Reliability tốt hơn | SLO attainment, incidents, MTTR |
| Developer autonomy | Self-service adoption, ticket volume |
| Vận hành tốt hơn | Toil hours, pages, upgrade success |
| Chi phí hợp lý | TCO per workload, idle capacity |
| Onboarding dễ hơn | Time to first deploy, training time |
| DR tốt hơn | Observed RTO/RPO, restore success |
| Security tốt hơn | Patch latency, access review, policy violations |

So sánh trước/sau trong cùng điều kiện hoặc ghi rõ các khác biệt. Không chỉ đếm số service đã chuyển lên nền tảng. Adoption cao không chứng minh nền tảng phù hợp nếu developer bị bắt buộc dùng và operational cost tăng.

## 44. Các tín hiệu nên dừng hoặc thu hẹp adoption

Cân nhắc dừng mở rộng nếu:
- Không có owner vận hành lâu dài.
- Chi phí tăng nhưng mục tiêu kỹ thuật không cải thiện.
- Platform incidents gây ảnh hưởng lớn hơn lỗi mà nó được thiết kế để ngăn.
- Nhiều thao tác vẫn phải làm thủ công.
- On-call không thể chẩn đoán failure modes.
- Upgrade bị trì hoãn do thiếu kỹ năng.
- Team phụ thuộc vào một cá nhân.
- Managed alternative đáp ứng tốt hơn với TCO thấp hơn.
- Workload chưa cần tính năng nâng cao.
- Migration làm giảm release autonomy hoặc developer flow.
- Pilot không đạt success criteria đã đặt.
- Security/DR requirements không được đáp ứng.

Dừng adoption không phải thất bại. Đó là quyết định quản trị rủi ro dựa trên bằng chứng. Có thể giữ nền tảng ở phạm vi nhỏ, chuyển sang managed option hoặc quay về kiến trúc đơn giản hơn.

## 45. Migration và exit strategy phải có từ đầu

Một lựa chọn tốt cần có đường đi ra:
- Dữ liệu có thể export ở định dạng nào?
- Workload có phụ thuộc API riêng của vendor không?
- Có thể chuyển secrets, identity và network không?
- Artifact có lưu ở registry độc lập không?
- Configuration có thể version hóa?
- Contract và schema có độc lập khỏi implementation?
- Có thể chạy song song trong thời gian migration không?
- Cutover/rollback có được thử?
- Chi phí và thời gian exit là bao nhiêu?
- Ai chịu trách nhiệm khi nền tảng bị retire?

Không cần xây abstraction để che mọi vendor feature. Nhưng cần hiểu mức lock-in và chấp nhận nó có chủ đích. Một managed service có thể là lựa chọn tốt nếu lợi ích vượt chi phí exit; điều quan trọng là biết trade-off.

## 46. Những sai lầm thường gặp khi lựa chọn nền tảng

| Sai lầm | Hậu quả | Cách tiếp cận |
| --- | --- | --- |
| Chọn vì công ty lớn đang dùng | Bỏ qua khác biệt về quy mô và đội ngũ | Bắt đầu từ problem statement |
| Dùng Kubernetes để sửa CI/CD yếu | Vẫn chậm, thêm lớp vận hành | Sửa pipeline trước |
| Dùng Kafka cho mọi async task | Broker/offset/schema complexity không cần thiết | Chọn queue hay stream theo semantics |
| Bật service mesh để có retry mặc định | Retry amplification và debug khó | Thiết kế timeout/idempotency/retry budget |
| Tự host mọi observability backend | Toil, storage và upgrade burden | So sánh TCO managed/self-host |
| Chọn active-active chỉ để tăng availability | Split-brain và consistency risk | BIA, RTO/RPO và writer model |
| Xây platform trước khi có users | Overbuilding và thiếu feedback | Pilot từ nhu cầu lặp lại |
| Không tính training/on-call | Phụ thuộc một vài chuyên gia | Capability plan và backup coverage |
| Không có rollback/exit | Lock-in và migration risk | Reversibility từ ADR |
| Đánh giá bằng demo | Bỏ qua incident/upgrade/recovery | Pilot đủ dài với failure exercise |
| Dùng quá nhiều công nghệ cho một capability | Tăng dependency và vận hành | Chuẩn hóa và loại bỏ trùng lặp |
| Chỉ tính cloud bill | Bỏ qua engineering opportunity cost | TCO toàn phần |
| Managed được coi là không cần owner | Cấu hình sai và shared responsibility gap | Ranh giới trách nhiệm rõ |
| Chuyển hết complexity sang Platform | Platform thành bottleneck | Golden paths và self-service |
| Không đo adoption outcomes | Không biết có tạo giá trị không | Baseline và success metrics |

## 47. Checklist trước khi chọn một nền tảng mới

- [ ] Có problem statement cụ thể và dữ liệu chứng minh.
- [ ] Có mục tiêu đo được về latency, scale, reliability, security hoặc developer flow.
- [ ] Đã xem xét cải tiến nền tảng hiện tại.
- [ ] Đã so sánh giải pháp đơn giản hơn và managed alternatives.
- [ ] Đã xác định workload và phạm vi cần áp dụng.
- [ ] Đã đánh giá kỹ năng, staffing, on-call và backup coverage.
- [ ] Có accountable owner và support/escalation model.
- [ ] Đã tính TCO gồm compute, storage, network, license và nhân lực.
- [ ] Có security, IAM, secrets và compliance plan.
- [ ] Có monitoring, SLO, alert và runbook.
- [ ] Có backup/restore/DR phù hợp.
- [ ] Có upgrade, patch và compatibility policy.
- [ ] Có pilot, success criteria và stop conditions.
- [ ] Có migration/rollback/exit strategy.
- [ ] Có kế hoạch đào tạo và knowledge transfer.
- [ ] Có cách đo lợi ích sau adoption.

## 48. Checklist vận hành sau khi áp dụng

- [ ] Service/platform catalog ghi owner và lifecycle.
- [ ] Dashboard phản ánh health, saturation và business impact.
- [ ] Alerts có action và escalation rõ.
- [ ] Runbook được người không phải tác giả sử dụng được.
- [ ] On-call có primary/secondary coverage.
- [ ] Backup/restore được thử định kỳ theo rủi ro.
- [ ] Upgrade được thực hiện theo lịch và có rollback.
- [ ] Security patches và certificate/secret rotation có owner.
- [ ] Capacity/quota được forecast.
- [ ] Cost được phân bổ và review.
- [ ] Incident và toil được phân tích.
- [ ] Developer feedback được thu thập.
- [ ] Có cơ chế retire features/add-ons không còn dùng.
- [ ] Dependency và version compatibility được theo dõi.
- [ ] Adoption tiếp tục tạo giá trị đo được.

## 49. Câu hỏi thường gặp

**Khi nào nên chọn Kubernetes?**

Khi có nhu cầu orchestration, scheduling, isolation, rollout hoặc platform consistency đủ rõ, và tổ chức có năng lực vận hành cluster/workloads. Nếu chỉ có vài service và managed container platform đáp ứng, Kubernetes có thể chưa mang lại lợi ích tương xứng.

**Có phải công ty nhỏ không nên dùng công nghệ phức tạp?**

Không. Quy mô công ty không quyết định duy nhất. Một startup có yêu cầu compliance hoặc throughput đặc thù có thể cần nền tảng chuyên biệt. Điều kiện là phải có owner, kỹ năng, support và ngân sách tương ứng.

**Managed service có giải quyết hết operational burden không?**

Không. Nó chuyển một phần trách nhiệm cho provider. Tổ chức vẫn phải quản lý configuration, IAM, data, limits, monitoring, recovery và application behavior. Cần đọc shared responsibility model.

**Nếu chưa có kỹ năng, có thể học trong lúc chạy production không?**

Có thể học qua pilot, sandbox, training và managed service với phạm vi rủi ro thấp. Không nên đưa một nền tảng chưa hiểu failure modes vào đường đi critical mà không có hỗ trợ và recovery plan.

**Có nên xây Platform Team trước khi có nhiều microservices?**

Nên giải quyết các nhu cầu lặp lại trước. Có thể bắt đầu với golden path CI/CD, templates và observability conventions. Chỉ mở rộng thành platform product khi có users, demand và capacity duy trì.

**Làm sao biết nền tảng quá phức tạp?**

Khi thời gian duy trì, debug, upgrade và phối hợp tăng nhanh hơn giá trị nó tạo ra; khi chỉ một người hiểu; khi các nhóm không tự deploy/rollback được; hoặc khi incident của platform ảnh hưởng nhiều workload.

**Một pilot kéo dài bao lâu là đủ?**

Không có con số cố định. Pilot phải đủ dài để kiểm tra deployment, một lần thay đổi cấu hình, capacity, backup/restore hoặc upgrade phù hợp. Một demo vài giờ không đủ để kết luận về operational fit.

**Có nên dùng Kafka vì cần event-driven architecture?**

Không mặc định. Nếu cần durable queue cho task đơn giản, managed queue có thể phù hợp. Kafka hợp lý khi cần retained event log, nhiều consumer, replay, throughput hoặc stream processing với owner vận hành.

**Service mesh có giúp bảo mật tự động không?**

Nó cung cấp cơ chế như workload identity và mTLS, nhưng policy, certificate lifecycle, trust boundaries và incident response vẫn cần thiết kế. Cấu hình sai có thể làm traffic gián đoạn.

**Tại sao phải tính chi phí nhân lực vào TCO?**

Vì kỹ sư dành thời gian nâng cấp, trực, debug và duy trì nền tảng thì không thể dùng thời gian đó cho công việc khác. Bỏ qua chi phí này khiến self-hosted trông rẻ giả tạo.

**Có thể bắt đầu đơn giản rồi nâng cấp sau không?**

Có, nếu lựa chọn ban đầu giữ được đường tiến hóa: data portability, contracts rõ, IaC, observability và migration plan. Không cần xây sẵn toàn bộ complexity của tương lai chưa chắc xảy ra.

**Khi nào nên dừng một nền tảng đã đầu tư?**

Khi lợi ích không còn bù TCO/risk, nhu cầu thay đổi hoặc có phương án phù hợp hơn. Hãy đo chi phí exit, chuyển workload từng phần và giữ recovery path trong migration.

**Ai chịu trách nhiệm nếu platform gây outage?**

Platform owner chịu trách nhiệm phần nền tảng họ sở hữu; application owner chịu trách nhiệm behavior và SLO ứng dụng; incident commander điều phối tác động chung. Shared responsibility cần được ghi rõ trong service catalog và support contract.

**Có nên chọn nền tảng có nhiều tính năng nhất để tránh phải thay đổi sau này?**

Không. Tính năng không dùng vẫn tạo surface area, upgrade burden và rủi ro cấu hình. Chọn capability cần thiết hiện tại và một lộ trình mở rộng có thể đảo ngược.

---

**Nguyên lý ghi nhớ:** *Chọn nền tảng theo vấn đề đã đo, năng lực vận hành và tổng chi phí sở hữu. Một công nghệ mạnh chỉ tạo giá trị khi tổ chức có người chịu trách nhiệm, kỹ năng, quy trình, bảo mật, khả năng phục hồi và ngân sách để duy trì nó. Bắt đầu ở phạm vi nhỏ, đo lợi ích thật, chuẩn hóa golden path rồi mở rộng theo nhu cầu; độ phức tạp phải đi sau năng lực và giá trị.*