# Hoàn thiện runbook và tiêu chí sẵn sàng đưa workload vào vận hành

Một workload compute chỉ thực sự sẵn sàng production khi nhóm vận hành có thể triển khai, quan sát, xử lý sự cố, khôi phục và kiểm soát chi phí một cách lặp lại. Ứng dụng chạy được trong môi trường thử nghiệm chưa đủ chứng minh khả năng vận hành: cần biết ai chịu trách nhiệm, dịch vụ phụ thuộc vào đâu, trạng thái bình thường trông như thế nào, khi nào phải cảnh báo, cách rollback và cách phục hồi dữ liệu khi có sự cố.

Runbook là tài liệu hướng dẫn thao tác cụ thể cho một dịch vụ hoặc tình huống vận hành. Operational readiness là quá trình kiểm tra bằng chứng để xác nhận workload có đủ điều kiện tiếp nhận người dùng và được đội vận hành hỗ trợ. Hai việc này gắn với nhau: runbook mô tả cách thực hiện; readiness review xác minh các bước đó đã được chuẩn bị, thử nghiệm và có người chịu trách nhiệm.

Bài học này hướng dẫn xây dựng bộ runbook và cổng sẵn sàng cho workload chạy trên VM, container hoặc serverless. Trọng tâm là các bằng chứng có thể kiểm tra: SLI/SLO, dependency map, deployment và rollback, health check, backup/restore, security, capacity, monitoring, incident response, disaster recovery và bàn giao vận hành.

## 1. Operational readiness là gì?

Operational readiness là trạng thái mà workload có thể được triển khai và vận hành theo các yêu cầu đã thống nhất về độ tin cậy, bảo mật, hiệu năng, khả năng phục hồi và chi phí. Nó bao gồm cả kỹ thuật, quy trình và con người.

Một workload sẵn sàng cần trả lời được các câu hỏi:

- Dịch vụ phục vụ ai và nghiệp vụ nào?
- Ai là service owner, technical owner và người on-call?
- Mức độ quan trọng và tác động khi dịch vụ gián đoạn là gì?
- SLI/SLO, error budget và ngưỡng cảnh báo đã xác định chưa?
- Thành phần nào là dependency bắt buộc?
- Làm sao deploy, scale, restart, drain và rollback?
- Làm sao phát hiện sự cố trước khi người dùng báo?
- Khi dữ liệu bị mất hoặc hỏng, khôi phục từ đâu và trong bao lâu?
- Ai được quyền truy cập production và cách audit ra sao?
- Có đủ capacity trong tải bình thường, peak và tình huống mất một failure domain không?
- Chi phí có thể dự báo và có owner theo dõi không?
- Đội vận hành đã thực hành các tình huống quan trọng chưa?

Readiness không phải một checkbox duy nhất trước ngày go-live. Đây là tập hợp bằng chứng được duy trì trong suốt vòng đời dịch vụ và được xem xét lại sau thay đổi lớn.

## 2. Phân biệt runbook, playbook, SOP và kiến trúc

Các loại tài liệu vận hành có mục đích khác nhau:

| Tài liệu | Trả lời câu hỏi | Nội dung thường có |
|---|---|---|
| Architecture overview | Hệ thống gồm những thành phần nào và kết nối ra sao? | Sơ đồ, trust boundary, data flow, dependency |
| Runbook | Thực hiện một thao tác vận hành cụ thể như thế nào? | Điều kiện trước, bước thao tác, xác minh, rollback |
| Incident playbook | Ứng phó một loại sự cố như thế nào? | Triage, containment, escalation, recovery, communication |
| SOP | Quy trình định kỳ phải thực hiện ra sao? | Vai trò, tần suất, bước kiểm soát và hồ sơ |
| DR plan | Phục hồi dịch vụ sau sự cố diện rộng như thế nào? | RTO/RPO, failover, restore, failback, quyết định |
| Release/change record | Thay đổi nào đã được triển khai và ai phê duyệt? | Version, scope, risk, test, window, outcome |

Một runbook tốt phải đủ cụ thể để người trực có thể làm theo khi chịu áp lực. Nó không nên chỉ chứa mô tả kiến trúc hoặc câu như “kiểm tra log và xử lý lỗi”. Cần nêu rõ nơi xem log, metric nào cần kiểm tra, điều kiện nào cho phép tiếp tục và khi nào phải escalation.

## 3. Xác định phạm vi và phân loại workload

Trước khi viết runbook, xác định workload thuộc loại nào. Các mô hình compute có cách vận hành khác nhau.

| Mô hình | Đối tượng vận hành | Điểm cần chú ý |
|---|---|---|
| Virtual machine | VM, OS, disk, NIC, agent, process/service | Boot, patch, SSH/RDP, filesystem, backup, host health |
| Container trên orchestrator | Deployment, Pod, node, cluster, image, volume | Readiness, rollout, scheduling, resource requests/limits, drain |
| Container đơn lẻ/managed container | Revision, instance, ingress, scaling config | Startup, concurrency, scale-to-zero, revision routing |
| Serverless function | Function, trigger, event source, execution config | Invocation, timeout, retry, concurrency, DLQ, cold start |
| Batch/HPC | Job, scheduler, node allocation, queue, checkpoint | Queue wait, job state, MPI/network, restart và data staging |

Phạm vi cũng cần xác định:

- Service hoặc workload được đánh giá.
- Môi trường: development, test, staging, production.
- Account/project/subscription và region.
- Các component thuộc nhóm sở hữu và component do platform team quản lý.
- Dữ liệu, API và khách hàng bị ảnh hưởng.
- Phần nào nằm ngoài phạm vi nhưng là dependency.

Không đưa mọi dịch vụ dùng chung vào runbook chi tiết của workload nếu nhóm không sở hữu chúng. Tuy nhiên, cần ghi rõ cách kiểm tra tình trạng dependency và kênh liên hệ đội phụ trách.

## 4. Tạo hồ sơ dịch vụ và ownership

Mỗi workload cần một hồ sơ ngắn làm điểm bắt đầu cho người vận hành.

| Trường | Nội dung cần ghi |
|---|---|
| Service name | Tên chuẩn dùng trong dashboard, alert và change record |
| Business purpose | Nghiệp vụ dịch vụ hỗ trợ |
| Service owner | Người/nhóm chịu trách nhiệm kết quả dịch vụ |
| Technical owner | Nhóm chịu trách nhiệm mã và kiến trúc |
| On-call | Kênh và lịch trực hiện hành |
| Support hours | Phạm vi hỗ trợ và escalation ngoài giờ |
| Criticality | Mức độ quan trọng và tác động gián đoạn |
| Environments | Các môi trường và region đang chạy |
| Repository/artifact | Nguồn code, image hoặc package đã phát hành |
| Deployment pipeline | Pipeline hoặc quy trình triển khai chuẩn |
| Dashboard | Link dashboard chính |
| Logs/traces | Nơi truy vấn log và trace |
| Runbooks | Tài liệu thao tác liên quan |
| Dependencies | Database, queue, network, identity và service ngoài |
| Data classification | Phân loại dữ liệu và yêu cầu lưu giữ |

Owner phải là nhóm hoặc vai trò có khả năng phản hồi, không chỉ là tên người đã rời dự án. Kênh on-call và escalation phải được kiểm tra định kỳ; một số điện thoại hoặc chat room cũ không tạo ra khả năng hỗ trợ thực tế.

## 5. Xác định mức độ quan trọng và tác động nghiệp vụ

Không phải workload nào cũng cần cùng một mức readiness. Hãy phân loại theo tác động khi dịch vụ ngừng hoạt động, mất dữ liệu hoặc xử lý sai.

Có thể dùng các nhóm:

- **Critical:** ảnh hưởng trực tiếp tới giao dịch hoặc chức năng thiết yếu; downtime ngắn cũng có tác động lớn.
- **High:** ảnh hưởng đáng kể tới người dùng hoặc hoạt động nội bộ; có thể có workaround giới hạn.
- **Standard:** có thể gián đoạn trong một khoảng thời gian đã thống nhất.
- **Low/Non-production:** không phục vụ production; có thể được tắt theo lịch hoặc khôi phục từ artifact.

Phân loại phải dựa trên business impact analysis, không chỉ dựa vào số lượng VM hoặc CPU. Một function nhỏ xử lý giao dịch thanh toán có thể quan trọng hơn một cluster lớn chạy báo cáo nội bộ.

Với từng workload, xác định:

- Số người dùng hoặc quy trình phụ thuộc.
- Khoảng thời gian gián đoạn có thể chấp nhận.
- Mức mất dữ liệu có thể chấp nhận.
- Tác động tài chính, pháp lý, an toàn hoặc uy tín.
- Workaround và thời gian có thể duy trì workaround.
- Các mùa cao điểm hoặc cửa sổ nghiệp vụ quan trọng.

## 6. Thiết lập SLI, SLO và error budget

**SLI** là chỉ số đo chất lượng dịch vụ. **SLO** là mục tiêu cho SLI trong một cửa sổ thời gian. **SLA** là cam kết dịch vụ với bên sử dụng hoặc khách hàng, có thể kèm điều khoản và hậu quả nếu không đạt.

Ví dụ SLI/SLO:

| SLI | Cách đo | Ví dụ SLO minh họa |
|---|---|---|
| Availability | Request hợp lệ nhận phản hồi thành công | 99,9% trong 30 ngày |
| Latency | Tỷ lệ request hoàn tất dưới ngưỡng | 95% dưới 300 ms |
| Correctness | Tỷ lệ kết quả nghiệp vụ hợp lệ | 99,99% |
| Queue freshness | Tuổi message lâu nhất hoặc p95 queue age | p95 dưới 60 giây |
| Job completion | Tỷ lệ batch job hoàn tất trong cửa sổ | 99% trước deadline |
| Data recovery | Khả năng đáp ứng RPO/RTO khi diễn tập | Đạt mục tiêu đã phê duyệt |

Các số liệu chỉ là ví dụ, không phải mặc định cho mọi hệ thống. SLO cần phản ánh kỳ vọng nghiệp vụ, khả năng kiến trúc và chi phí để đạt mục tiêu.

### 6.1. Chọn SLI có ý nghĩa với người dùng

Không dùng CPU utilization làm SLI availability. CPU là tín hiệu nội bộ; người dùng quan tâm request có hoàn tất đúng và đủ nhanh hay không.

Nên kết hợp:

- SLI hướng người dùng: success rate, latency, correctness.
- SLI xử lý nền: queue age, event processing delay, job completion.
- SLI dữ liệu: replication lag, backup freshness, restore success.
- SLI nền tảng: health của instance, node, function và dependency.

### 6.2. Error budget

Error budget là phần lỗi hoặc gián đoạn được phép trong SLO. Nếu SLO availability là 99,9% trong một cửa sổ, error budget tương ứng là phần thời gian hoặc request không đạt mục tiêu theo cách định nghĩa SLI.

Runbook và release policy có thể dùng error budget để quyết định:

- Tiếp tục phát hành bình thường.
- Tăng mức kiểm thử hoặc giảm phạm vi rollout.
- Tạm dừng thay đổi rủi ro cao.
- Ưu tiên xử lý reliability debt.
- Thực hiện capacity hoặc DR exercise.

Cần thống nhất cách tính và nguồn dữ liệu; không so sánh error budget theo phút downtime với error budget theo request nếu chưa chuẩn hóa.

## 7. Xác định RTO và RPO

Hai mục tiêu quan trọng trong khôi phục:

- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để khôi phục dịch vụ sau sự cố.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể chấp nhận mất, thường biểu diễn bằng thời gian dữ liệu.

Ví dụ: RTO 60 phút nghĩa là mục tiêu khôi phục dịch vụ trong vòng một giờ. RPO 15 phút nghĩa là chấp nhận khôi phục tới điểm dữ liệu có thể cũ tối đa khoảng 15 phút, theo cách đo đã thống nhất.

RTO/RPO phải được business owner phê duyệt. Chúng ảnh hưởng tới chi phí backup, replication, warm standby, multi-region và diễn tập.

| Mức phục hồi | Ví dụ mục tiêu | Kiến trúc có thể cần |
|---|---|---|
| RTO rất thấp, RPO gần 0 | Dịch vụ giao dịch trọng yếu | HA đa vùng, replication đồng bộ hoặc cơ chế dữ liệu chuyên dụng |
| RTO thấp, RPO vài phút | API quan trọng | Warm standby, replication bất đồng bộ có giám sát |
| RTO vài giờ, RPO theo giờ | Hệ thống nội bộ | Backup/restore và hạ tầng có thể tái tạo |
| RTO dài, RPO một ngày | Workload ít quan trọng | Backup định kỳ, IaC và quy trình phục hồi thủ công |

Không hứa RTO/RPO chỉ dựa trên việc đã bật backup. Phải đo thời gian restore, thời gian provisioning, DNS/failover, kiểm tra dữ liệu và xác nhận nghiệp vụ trong diễn tập.

## 8. Lập bản đồ dependency và luồng dữ liệu

Runbook cần cho người trực biết điều gì phải khỏe trước khi workload hoạt động.

Dependency thường gồm:

- DNS, routing, firewall, NAT và private connectivity.
- Identity provider, IAM role, managed identity hoặc service account.
- Secret manager và certificate authority.
- Database, cache, object storage và filesystem.
- Queue, event bus, stream và workflow engine.
- API bên thứ ba.
- Logging, metrics, tracing và alerting.
- Image registry, package repository và deployment control plane.
- Backup, replication và key management.

Sơ đồ dependency:

~~~mermaid
flowchart TD
    U[Client / producer] --> E[Ingress / event source]
    E --> C[Compute workload]
    C --> I[Identity and secrets]
    C --> D[(Database)]
    C --> Q[Queue / event bus]
    C --> O[Object storage]
    C --> X[External API]
    C --> T[Telemetry pipeline]
    D --> B[Backup / replication]
    C --> N[Network / DNS / NAT]
~~~

Với mỗi dependency, ghi:

- Owner và kênh hỗ trợ.
- Giao thức, endpoint và port.
- Authentication method.
- Timeout và retry behavior.
- Health signal.
- Failure impact.
- Workaround hoặc fallback.
- Cách kiểm tra kết nối an toàn.

Không lưu credential hoặc secret thật trong runbook. Chỉ ghi tên secret reference, nơi lấy và vai trò có quyền truy cập.

## 9. Xác định trạng thái bình thường và baseline

Runbook xử lý sự cố cần có baseline để nhận ra điều gì bất thường.

Thu thập baseline theo giờ/ngày/tuần và theo mùa:

- Request rate hoặc event arrival rate.
- Success/error rate.
- p50/p95/p99 latency.
- CPU, memory, disk và network.
- Container restart, Pod pending và node pressure.
- Function concurrency, duration và throttling.
- Queue depth, oldest-message age và consumer lag.
- Database connection, query latency và replication lag.
- Egress, NAT connection và network transfer.
- Chi phí theo service và environment.

Baseline cần có cả tải bình thường lẫn peak. Nếu chỉ biết average, người trực khó xác định CPU 80% là bình thường trong batch window hay là dấu hiệu sắp quá tải.

## 10. Thiết kế monitoring và alert

Một alert tốt phải chỉ ra tác động hoặc nguy cơ cần hành động. Không tạo hàng trăm alert chỉ vì metric vượt một ngưỡng ngắn.

Phân loại alert:

- **Page:** cần người trực phản ứng ngay vì user impact hoặc nguy cơ vượt SLO.
- **Ticket:** cần điều tra trong giờ hỗ trợ nhưng không cần đánh thức on-call.
- **Informational:** cung cấp thông tin hoặc xu hướng.

Mỗi alert cần có:

- Tên và mô tả rõ ràng.
- Severity.
- Điều kiện và cửa sổ đánh giá.
- Service/environment/region bị ảnh hưởng.
- Dashboard và log query liên quan.
- Runbook link.
- Owner/escalation.
- Hướng dẫn xác nhận false positive.
- Hành động an toàn đầu tiên.

### 10.1. Alert theo symptom và cause

Ưu tiên cảnh báo theo symptom hướng người dùng, ví dụ error rate hoặc latency vượt SLO. Alert theo cause như CPU cao, disk gần đầy hoặc node pressure giúp tìm nguyên nhân nhưng không phải lúc nào cũng cần page.

Ví dụ:

| Tín hiệu | Loại cảnh báo gợi ý | Hành động |
|---|---|---|
| Availability SLI giảm dưới ngưỡng | Page | Kiểm tra impact và incident triage |
| p99 latency tăng liên tục | Page hoặc ticket theo SLO | Phân tích dependency và saturation |
| Queue age tăng vượt deadline nghiệp vụ | Page | Kiểm tra consumer, downstream và scale |
| Disk gần đầy | Ticket/page tùy criticality | Kiểm tra log, data growth và capacity |
| Backup job thất bại | Page hoặc ticket theo RPO | Xác minh bản backup gần nhất |
| Certificate sắp hết hạn | Ticket có thời hạn | Gia hạn và kiểm tra rollout |
| Chi phí tăng đột biến | FinOps alert | Tách volume, duration và retry |

## 11. Logging, metrics và distributed tracing

Ba loại telemetry bổ trợ nhau:

- **Logs:** sự kiện chi tiết, lỗi và thông tin theo từng lần xử lý.
- **Metrics:** số liệu tổng hợp theo thời gian để phát hiện xu hướng và alert.
- **Traces:** đường đi của một request/event qua nhiều service và dependency.

Nên chuẩn hóa các trường:

- service name và environment.
- release/version hoặc image digest.
- timestamp có timezone.
- correlation ID và trace ID.
- request/event type.
- outcome/error code.
- duration.
- dependency name.
- region/zone hoặc instance identifier phù hợp.

Không log access token, password, private key, dữ liệu thẻ hoặc payload nhạy cảm. Dùng masking/redaction, sampling và retention theo policy. Tránh label metrics có cardinality quá cao như user ID hoặc request ID; giữ thông tin chi tiết trong log/trace có kiểm soát.

## 12. Runbook triển khai và phát hành

Runbook release cần mô tả toàn bộ đường đi từ artifact tới production.

Các bước tối thiểu:

1. Xác nhận change ticket hoặc release record.
2. Kiểm tra commit, image/package digest và build provenance.
3. Xác nhận security scan và test bắt buộc.
4. Xác nhận cấu hình, secret reference và schema compatibility.
5. Kiểm tra capacity, quota và maintenance window.
6. Xác nhận dashboard, alert và người trực.
7. Triển khai theo canary, rolling hoặc blue-green phù hợp.
8. Kiểm tra readiness và smoke test.
9. Theo dõi SLI/SLO trong observation window.
10. Promote release khi đạt tiêu chí.
11. Ghi version, thời điểm, người thực hiện và kết quả.
12. Giữ artifact/revision cũ trong rollback window.

### 12.1. Tiêu chí dừng rollout

Dừng rollout khi:

- Readiness không đạt hoặc Pod/function liên tục restart.
- Error rate hoặc latency vượt ngưỡng đã định.
- Business metric giảm bất thường.
- Database migration không tương thích với phiên bản cũ.
- Queue age hoặc retry tăng nhanh.
- Có lỗi bảo mật hoặc sai cấu hình quyền.
- Capacity không đủ cho bước rollout tiếp theo.
- Monitoring không hoạt động khiến không thể đánh giá an toàn.

Không tiếp tục chỉ vì pipeline báo deploy thành công. Trạng thái hạ tầng không thay thế xác nhận nghiệp vụ.

## 13. Runbook rollback

Rollback cần nêu rõ điều kiện, người quyết định, thao tác và kiểm tra sau khi quay lại.

Một quy trình chung:

1. Xác nhận release mới là nguyên nhân có khả năng cao hoặc rollback là lựa chọn an toàn.
2. Dừng tăng traffic và đóng change window.
3. Kiểm tra phiên bản trước còn artifact và capacity.
4. Kiểm tra database/schema compatibility.
5. Khôi phục routing hoặc deployment revision.
6. Xác nhận replica cũ Ready và dependency hoạt động.
7. Kiểm tra request, transaction và queue đang xử lý.
8. Theo dõi SLI/SLO và business metric.
9. Ghi lại thời gian, release ID và kết quả.
10. Giữ bằng chứng để điều tra nguyên nhân.

### 13.1. Ví dụ Kubernetes

~~~bash
kubectl rollout status deployment/api
kubectl rollout history deployment/api
kubectl rollout undo deployment/api
kubectl get pods -l app=api -o wide
kubectl describe deployment api
~~~

Các lệnh chỉ là ví dụ. Nếu GitOps là nguồn cấu hình chuẩn, rollback phải được thực hiện qua repository hoặc release controller tương ứng; thao tác trực tiếp có thể bị reconcile ghi đè.

### 13.2. Rollback không đồng nghĩa phục hồi dữ liệu

Rollback image không đảo ngược transaction, message đã phát, email đã gửi hoặc schema migration phá vỡ tương thích. Runbook phải phân biệt:

- Rollback application artifact.
- Rollback configuration.
- Rollback routing/traffic weight.
- Database migration rollback hoặc forward-fix.
- Restore dữ liệu từ backup.
- Compensation cho side effect nghiệp vụ.

Nếu không thể đảo ngược migration an toàn, có thể phải roll forward bằng bản sửa tương thích thay vì quay lại binary cũ.

## 14. Runbook vận hành VM

Với VM, runbook cần bao gồm OS, process, disk, network và cloud control plane.

### 14.1. Kiểm tra trạng thái VM

- Instance state và host/system status.
- CPU, memory, disk utilization.
- Filesystem read-only hoặc inode exhaustion.
- NIC, route, DNS và security rule.
- Service/process status.
- Agent quản trị, monitoring và backup.
- Boot log và system log.
- Disk attachment và snapshot status.

Ví dụ Linux:

~~~bash
systemctl status application.service
journalctl -u application.service --since "30 minutes ago"
df -h
free -m
uptime
ss -tulpn
~~~

Không chạy lệnh sửa chữa hoặc xóa file trước khi hiểu impact và có quyền phù hợp. Với disk gần đầy, xác định file tăng nhanh, log retention và data owner; không xóa dữ liệu nghiệp vụ để làm giảm alert.

### 14.2. Restart và thay thế VM

Runbook cần xác định:

- Khi nào restart process, khi nào reboot VM.
- Có cần drain khỏi load balancer trước không.
- Có state hoặc job đang chạy trên local disk không.
- VM có thể tạo lại từ image/IaC không.
- IP/DNS/volume có thay đổi khi replace không.
- Ai xác minh dịch vụ sau reboot.
- Cách quay lại nếu boot hoặc startup script thất bại.

Nếu VM chứa dữ liệu stateful duy nhất, thay thế instance có thể gây mất dữ liệu. Kiểm tra volume, replication và backup trước thao tác.

## 15. Runbook vận hành container

Container workload cần runbook cho cả application controller và cluster/node.

Các mục cần kiểm tra:

- Deployment/StatefulSet desired, current và available replicas.
- Pod Pending, CrashLoopBackOff, ImagePullBackOff.
- Readiness/liveness/startup probe.
- CPU/memory request, limit và throttling.
- Node pressure, taint, affinity và quota.
- Service/Ingress/NetworkPolicy.
- Persistent volume attachment và storage latency.
- Image digest, rollout revision và registry availability.
- Autoscaler và disruption budget.

Ví dụ lệnh Kubernetes:

~~~bash
kubectl get deploy,rs,pods -n production
kubectl rollout status deployment/api -n production
kubectl describe pod POD_NAME -n production
kubectl logs POD_NAME -n production --since=30m
kubectl get events -n production --sort-by=.lastTimestamp
kubectl top pods -n production
kubectl top nodes
~~~

Thay namespace và resource theo môi trường. Không đưa secret hoặc output có dữ liệu nhạy cảm vào ticket công khai.

### 15.1. Drain node và bảo trì

Trước khi drain:

- Kiểm tra capacity còn lại.
- Xác minh PDB và replica placement.
- Kiểm tra workload stateful và volume.
- Xác nhận job có checkpoint hoặc có thể retry.
- Kiểm tra autoscaler và maintenance policy.
- Theo dõi Pod eviction và readiness sau drain.

Không giả định PDB bảo vệ mọi dạng disruption hoặc bảo đảm workload luôn còn đủ capacity. Cần kiểm tra controller, loại disruption và topology thực tế.

## 16. Runbook vận hành serverless

Function/serverless không có OS hoặc node mà đội ứng dụng trực tiếp quản lý, nhưng vẫn cần runbook về event, runtime và dependency.

Các mục cần kiểm tra:

- Invocation count, duration p50/p95/p99.
- Error, timeout, throttling và OOM.
- Concurrency và provisioned/warm capacity.
- Cold-start/init duration.
- Trigger/event source health.
- Queue depth, oldest-message age và stream lag.
- Retry, duplicate và DLQ.
- Function version, alias/revision và traffic routing.
- IAM role/managed identity/service account.
- VPC/VNet, DNS, NAT và private endpoint.
- Cost per successful operation.

Khi function lỗi, xác định lỗi xảy ra trước handler, trong handler hay ở dependency. Với event source mapping, kiểm tra poller, batch, visibility/ack deadline và checkpoint; với push trigger, kiểm tra delivery attempt, response status và retry policy.

### 16.1. Replay event

Trước khi replay event từ DLQ:

1. Xác định nguyên nhân gốc.
2. Xác nhận phiên bản handler đã sửa.
3. Kiểm tra event schema và dữ liệu nhạy cảm.
4. Kiểm tra side effect trước đó có thể đã thành công không.
5. Xác nhận idempotency key/deduplication.
6. Replay theo batch nhỏ.
7. Theo dõi success, retry và downstream load.

Không replay hàng loạt khi dependency đang suy giảm hoặc consumer chưa có capacity.

## 17. Runbook scaling và capacity

Scaling phải có điều kiện kích hoạt, giới hạn và cách xác minh.

### 17.1. Scale-out

- Xác định symptom: latency, queue age, saturation hoặc request rejection.
- Kiểm tra bottleneck có nằm ở compute hay dependency.
- Kiểm tra quota và capacity vùng.
- Tăng replica/instance/concurrency theo policy.
- Xác nhận load balancer/trigger phân phối tới capacity mới.
- Theo dõi latency, error rate và downstream saturation.

### 17.2. Scale-in

- Xác nhận tải giảm ổn định trong cửa sổ đủ dài.
- Drain request, connection và job.
- Kiểm tra stateful workload và local data.
- Giảm capacity theo bước.
- Theo dõi SLO và queue age sau mỗi bước.
- Dừng scale-in nếu latency hoặc backlog tăng.

### 17.3. Capacity cho failure scenario

Không chỉ sizing cho peak bình thường. Hãy kiểm tra N-1 capacity: nếu mất một node, zone hoặc instance pool, phần còn lại có thể phục vụ tải cần thiết không? Với serverless, kiểm tra concurrency/quota và khả năng downstream chịu burst khi event backlog được xử lý trở lại.

## 18. Backup, restore và data protection

Runbook backup phải nêu:

- Dữ liệu nào được backup.
- Cơ chế và lịch backup.
- Retention và vị trí lưu.
- Encryption và key ownership.
- Quyền truy cập backup.
- Cách kiểm tra tính toàn vẹn.
- Cách restore theo từng loại dữ liệu.
- Ai phê duyệt restore production.
- Cách xác minh consistency và business correctness.

Backup thành công về mặt job status chưa chứng minh có thể restore. Cần kiểm thử restore định kỳ trong môi trường phù hợp và đo thời gian thực tế.

### 18.1. Restore procedure

1. Xác định incident và thời điểm dữ liệu cần phục hồi.
2. Chọn recovery point phù hợp RPO.
3. Xác minh backup và encryption key khả dụng.
4. Tạo môi trường restore cô lập.
5. Khôi phục database/file/object.
6. Chạy integrity check và đối chiếu record count hoặc checksum.
7. Xác minh ứng dụng đọc được dữ liệu.
8. Business owner xác nhận dữ liệu hợp lệ.
9. Chuyển traffic hoặc promote hệ thống đã phục hồi.
10. Ghi lại thời gian restore và RPO/RTO thực tế.

Không restore đè lên production trước khi hiểu dữ liệu mới hơn sẽ bị mất hoặc có thể cần merge. Với database phân tán, cần dùng quy trình nhất quán của engine.

## 19. Disaster recovery, failover và failback

DR runbook phải mô tả cách khôi phục sau sự cố vượt phạm vi một instance hoặc một node.

Các bước cần có:

- Tiêu chí tuyên bố disaster và người có quyền quyết định.
- Region/site dự phòng và trạng thái readiness.
- Thứ tự phục hồi network, identity, data và compute.
- Cơ chế promote database hoặc replica.
- DNS/global routing và thời gian cache.
- Kiểm tra secret, certificate, quota và image availability.
- Kiểm tra event/queue backlog và job đang chạy.
- Xác nhận dữ liệu đáp ứng RPO.
- Xác nhận dịch vụ đáp ứng RTO.
- Truyền thông với stakeholder.
- Quy trình failback sau khi region chính phục hồi.

### 19.1. Failover không phải chỉ đổi DNS

Khi chuyển region, cần xác minh data writer, replication lag, queue ownership, scheduled job và side effect. Nếu hai region cùng xử lý ghi mà không có cơ chế leader/fencing, có thể tạo split-brain hoặc dữ liệu xung đột.

### 19.2. Diễn tập DR

Diễn tập cần ghi:

- Scenario và phạm vi.
- Thời điểm bắt đầu.
- Người tham gia và vai trò.
- Các bước runbook đã thực hiện.
- RTO/RPO thực tế.
- Điểm sai khác so với tài liệu.
- Data validation result.
- Action item, owner và deadline.

Runbook chưa từng diễn tập chỉ là giả thuyết. Sau mỗi exercise, cập nhật tài liệu và kiểm tra lại các liên hệ, quyền và automation.

## 20. Security readiness

Security readiness cần kiểm tra cả workload, pipeline, identity, network và dữ liệu.

### 20.1. Identity và quyền

- Workload dùng role/managed identity/service account riêng.
- Quyền theo least privilege và scope nhỏ nhất.
- Không dùng access key dài hạn nhúng trong image hoặc source.
- Secret lấy từ secret manager và có rotation.
- Quyền deploy tách khỏi quyền runtime khi phù hợp.
- Quyền break-glass có kiểm soát và audit.
- Owner và expiry của credential được xác định.

### 20.2. Network

- Public exposure được xác định và phê duyệt.
- Private endpoint/VPC/VNet integration dùng đúng mục đích.
- Security group, firewall, NSG và NetworkPolicy giới hạn theo luồng.
- Egress được kiểm soát.
- DNS và certificate được theo dõi.
- NAT capacity và network dependency được kiểm tra.
- Không mở port quản trị ra Internet nếu không có biện pháp kiểm soát phù hợp.

### 20.3. Image và supply chain

- Artifact đến từ pipeline/repository được kiểm soát.
- Image/package được scan theo policy.
- Digest hoặc version bất biến được ghi trong release record.
- Dependency và base image có quy trình cập nhật.
- SBOM/provenance được lưu nếu policy yêu cầu.
- Không chứa secret trong layer, build log hoặc artifact.
- Có quy trình thu hồi/redeploy khi phát hiện vulnerability nghiêm trọng.

### 20.4. Dữ liệu và audit

- Data classification rõ ràng.
- Encryption at rest/in transit theo yêu cầu.
- Log không lộ secret hoặc dữ liệu nhạy cảm.
- Audit log được bảo vệ khỏi sửa/xóa trái phép.
- Retention và deletion theo policy.
- Backup và encryption key có quyền truy cập riêng.

## 21. Change management và maintenance

Runbook phải bao gồm thay đổi định kỳ, không chỉ incident.

Các loại change:

- Release application.
- OS/runtime patch.
- Base image update.
- Certificate/secret rotation.
- Database schema migration.
- Network/security policy update.
- Scaling/capacity change.
- Backup policy change.
- Region/DR configuration change.

Một change record cần nêu:

- Mục tiêu và phạm vi.
- Tài nguyên và người dùng bị ảnh hưởng.
- Risk và impact.
- Pre-check và test.
- Maintenance window.
- Rollback/forward-fix.
- Người phê duyệt và người thực hiện.
- Success criteria.
- Kết quả và follow-up.

Không phải mọi thay đổi đều cần cùng một cấp phê duyệt. Phân loại theo risk và impact, nhưng luôn giữ audit trail phù hợp.

## 22. Incident response và escalation

Một incident process rõ ràng giảm thời gian xác định người chỉ huy và hành động đầu tiên.

Các vai trò thường gặp:

- **Incident commander:** điều phối, đặt ưu tiên và quyết định nhịp xử lý.
- **Technical lead:** điều tra và điều khiển khắc phục kỹ thuật.
- **Communications lead:** cập nhật stakeholder và người dùng.
- **Scribe:** ghi timeline, quyết định và hành động.
- **Service owner:** xác nhận impact nghiệp vụ và tiêu chí phục hồi.

Với đội nhỏ, một người có thể đảm nhiệm nhiều vai trò, nhưng cần nói rõ ai đang giữ vai trò nào.

### 22.1. Quy trình incident cơ bản

1. Nhận alert hoặc báo cáo.
2. Xác nhận symptom và phạm vi ảnh hưởng.
3. Gán severity và mở incident record.
4. Chỉ định incident commander/technical lead.
5. Bảo vệ dữ liệu và containment trước.
6. Điều tra theo runbook và telemetry.
7. Khôi phục dịch vụ bằng hành động an toàn.
8. Xác minh SLI/SLO và business operation.
9. Cập nhật stakeholder theo chu kỳ.
10. Kết thúc incident khi có bằng chứng ổn định.
11. Tổ chức post-incident review và theo dõi action item.

### 22.2. Severity và escalation

| Mức | Ví dụ | Phản ứng |
|---|---|---|
| SEV-1 | Dịch vụ trọng yếu ngừng hoạt động hoặc mất dữ liệu nghiêm trọng | Page ngay, incident command, thông báo stakeholder |
| SEV-2 | Suy giảm lớn, nhiều người dùng hoặc SLO có nguy cơ vượt | On-call phản ứng nhanh, điều tra ưu tiên |
| SEV-3 | Ảnh hưởng giới hạn, có workaround | Ticket/đội hỗ trợ theo giờ quy định |
| SEV-4 | Lỗi nhỏ hoặc yêu cầu thông tin | Backlog vận hành |

Tên severity và thời gian phản hồi phải được tổ chức thống nhất. Bảng chỉ là ví dụ; không thay thế policy incident hiện hành.

## 23. Quy trình xử lý sự cố theo triệu chứng

### 23.1. Latency tăng

1. Kiểm tra SLI p95/p99 và phạm vi người dùng.
2. So sánh với baseline và thời điểm release.
3. Kiểm tra CPU/memory/concurrency và queue age.
4. Xem trace để tìm dependency chậm.
5. Kiểm tra database pool, query và network.
6. Giảm traffic hoặc rollback nếu regression được xác nhận.
7. Xác minh latency phục hồi và theo dõi đủ cửa sổ.

### 23.2. Error rate tăng

1. Phân nhóm status code và exception.
2. Kiểm tra release/config change gần nhất.
3. Kiểm tra dependency availability và credentials.
4. Xác định lỗi có ảnh hưởng dữ liệu hay side effect không.
5. Dừng retry storm nếu cần.
6. Rollback hoặc chuyển traffic sang healthy backend.
7. Xác minh success rate và correctness.

### 23.3. Queue backlog tăng

1. Kiểm tra arrival rate và processing rate.
2. Kiểm tra consumer concurrency, error và timeout.
3. Kiểm tra downstream rate limit hoặc outage.
4. Xác định poison message và DLQ growth.
5. Tăng consumer có giới hạn nếu dependency đủ capacity.
6. Giảm producer hoặc áp dụng backpressure khi cần.
7. Xác nhận oldest-message age trở về mục tiêu.

### 23.4. Memory/disk gần cạn

1. Xác định resource và workload cụ thể.
2. Kiểm tra xu hướng, leak và file growth.
3. Xác định file/cache/log có thể dọn theo policy.
4. Không xóa dữ liệu nghiệp vụ hoặc backup chưa xác minh.
5. Scale hoặc tăng disk theo change policy nếu cần.
6. Xác nhận memory/disk headroom sau xử lý.

### 23.5. Không kết nối được dependency

1. Xác định source/destination, port và protocol.
2. Kiểm tra DNS resolution.
3. Kiểm tra route, security group/firewall và private endpoint.
4. Kiểm tra identity, certificate và secret rotation.
5. Kiểm tra NAT/connection limit.
6. Kiểm tra dependency health và network path.
7. Thực hiện test kết nối có kiểm soát, không dump credential.

## 24. Capacity, performance và load test readiness

Trước production, cần bằng chứng workload đáp ứng tải dự kiến.

Kiểm thử nên bao gồm:

- Baseline load.
- Peak load.
- Burst và ramp-up.
- Soak test trong thời gian đủ dài.
- Scale-out và scale-in.
- Mất một instance/node/zone theo phạm vi cho phép.
- Dependency latency hoặc failure.
- Queue backlog và recovery.
- Deployment trong lúc có tải.
- Resource exhaustion ở môi trường kiểm thử an toàn.

Kết quả cần ghi throughput, latency p50/p95/p99, error rate, CPU/memory, network, queue age, database saturation và cost. Đặt pass/fail threshold trước khi chạy, tránh thay đổi ngưỡng sau khi đã nhìn thấy kết quả chỉ để coi test là thành công.

## 25. Cost readiness và FinOps

Một workload production cần có dự báo chi phí và cơ chế phát hiện bất thường.

Cần xác định:

- Owner/cost center và tag chuẩn.
- Chi phí compute, storage, network, backup, logging và dependency.
- Unit cost theo request, job, user hoặc business transaction.
- Budget và forecast.
- Cảnh báo spend anomaly.
- Tài nguyên nhàn rỗi và lịch tắt/mở cho non-production.
- Commitment/reservation và rủi ro capacity.
- Chi phí DR, warm standby và data replication.

Tối ưu chi phí không được phá SLO hoặc làm mất khả năng phục hồi. Mọi thay đổi giảm capacity cần được kiểm tra ở peak load và failure scenario.

## 26. Runbook template có thể tái sử dụng

Mỗi runbook thao tác nên có cấu trúc nhất quán:

~~~markdown
# Tên thao tác / tình huống

## Mục tiêu
Mô tả kết quả cần đạt.

## Phạm vi
Service, environment, region và resource liên quan.

## Người chịu trách nhiệm
Owner, on-call, approver và escalation.

## Điều kiện trước
Quyền cần có, change record, maintenance window,
backup/checkpoint và dependency health.

## Tác động và rủi ro
Người dùng, dữ liệu, downtime và side effect có thể xảy ra.

## Các bước thực hiện
1. Kiểm tra trạng thái ban đầu.
2. Thực hiện thao tác theo thứ tự.
3. Theo dõi tiến trình.
4. Xác minh kết quả.

## Tiêu chí thành công
Metric, health check và business validation cụ thể.

## Rollback / recovery
Điều kiện dừng, cách quay lại và giới hạn phục hồi.

## Escalation
Khi nào chuyển cho đội khác và cung cấp bằng chứng gì.

## Audit
Thời điểm, người thực hiện, resource ID và kết quả.
~~~

Template cần được điều chỉnh cho thao tác cụ thể. Các bước phải có lệnh hoặc đường dẫn dashboard khi cần; không để placeholder chưa được điền trong runbook production.

## 27. Ví dụ runbook: phát hành API container

**Mục tiêu:** phát hành một revision API mới mà vẫn duy trì SLO.

**Phạm vi:** namespace production, Deployment api và Service public-api.

**Điều kiện trước:**

- Release đã qua build, scan và test.
- Image digest và config version đã được ghi.
- Database migration tương thích ngược.
- Dashboard và alert đang hoạt động.
- On-call đã được thông báo.
- Replica hiện tại đủ capacity và không có incident đang mở.

**Thực hiện:**

1. Kiểm tra available replicas, error rate, latency và queue age.
2. Xác nhận image digest trong release record.
3. Áp dụng manifest hoặc promote revision theo pipeline chuẩn.
4. Theo dõi rollout status và Pod events.
5. Chạy smoke test qua endpoint production đã được phê duyệt.
6. Theo dõi error rate, p95/p99 và business metric trong observation window.
7. Nếu đạt, đánh dấu release hoàn tất và lưu kết quả.
8. Nếu không đạt, dừng rollout và thực hiện rollback theo runbook.

**Tiêu chí thành công:**

- Desired replicas đều available.
- Không có Pod restart bất thường.
- Smoke test đạt.
- SLI không vượt ngưỡng regression.
- Database và queue không có backlog bất thường.
- Owner xác nhận nghiệp vụ hoạt động.

**Rollback:** khôi phục revision/image digest ổn định qua release controller; xác minh schema compatibility trước khi chuyển toàn bộ traffic.

## 28. Ví dụ runbook: function xử lý event bị backlog

**Triệu chứng:** oldest-message age tăng, queue depth tăng và số event hoàn tất giảm.

**Điều tra:**

1. So sánh event arrival rate với processing rate.
2. Kiểm tra invocation count, duration, error và throttling.
3. Kiểm tra function concurrency và quota.
4. Kiểm tra dependency latency, connection limit và rate limit.
5. Kiểm tra retry count, poison event và DLQ.
6. Xác định backlog có tập trung theo partition/key không.

**Khắc phục:**

- Nếu function thiếu concurrency và downstream còn capacity, tăng giới hạn theo bước.
- Nếu database quá tải, giảm consumer rate và xử lý bottleneck.
- Nếu có poison event, cô lập bằng DLQ hoặc policy phù hợp.
- Nếu release mới gây lỗi, chuyển traffic/alias về version ổn định.
- Nếu event bị duplicate, xác minh idempotency trước replay.

**Tiêu chí phục hồi:**

- Queue age giảm về ngưỡng mục tiêu.
- Processing rate cao hơn arrival rate đủ lâu để xóa backlog.
- Error/retry không tăng bất thường.
- Downstream vẫn trong giới hạn.
- Business operation được xác nhận đúng.

## 29. Readiness review và các cổng Go/No-Go

Readiness review là buổi đánh giá bằng chứng trước khi workload tiếp nhận production traffic. Nên có owner nghiệp vụ, service owner, platform, security, data và operations tùy phạm vi.

Các cổng chính:

| Gate | Câu hỏi | Bằng chứng cần có |
|---|---|---|
| Business | Phạm vi và tác động đã rõ chưa? | Owner, criticality, support expectation |
| Architecture | Dependency và failure mode đã hiểu chưa? | Architecture/data-flow diagram, dependency map |
| Reliability | SLO, alert và recovery có thực hiện được không? | SLI dashboard, alert test, RTO/RPO |
| Deployment | Có thể deploy và rollback an toàn không? | Release record, artifact digest, rollback rehearsal |
| Security | Identity, network và dữ liệu đã được kiểm soát chưa? | IAM review, scan, network rule, secret handling |
| Data protection | Backup có thể restore không? | Backup policy và restore evidence |
| Performance | Workload chịu được tải dự kiến không? | Load/soak/failover test report |
| Operations | Đội trực có thể xử lý sự cố không? | Runbook, on-call, escalation, game day |
| Cost | Chi phí có owner và guardrail không? | Forecast, budget, tags, anomaly alert |
| Compliance | Retention và audit đáp ứng yêu cầu không? | Policy mapping và audit evidence |

### 29.1. Quyết định Go/No-Go

- **Go:** tất cả yêu cầu bắt buộc đạt, owner chấp nhận residual risk và lịch vận hành đã sẵn sàng.
- **Conditional Go:** chỉ còn các vấn đề rủi ro thấp, có workaround, owner và deadline rõ; phải được người có thẩm quyền chấp thuận.
- **No-Go:** còn lỗi nghiêm trọng về bảo mật, dữ liệu, rollback, monitoring, capacity, ownership hoặc khả năng phục hồi.

Không hạ severity của một blocker chỉ để giữ lịch phát hành. Conditional Go không được dùng để bỏ qua rủi ro không có biện pháp kiểm soát.

## 30. Ma trận readiness theo mô hình compute

| Hạng mục | VM | Container | Serverless function |
|---|---|---|---|
| Health | OS/process/agent | Probe, Pod và node health | Invocation/error/throttle |
| Deploy | Image/VM template/config | Image digest, rollout strategy | Function version/alias/revision |
| Rollback | Snapshot/image/config hoặc redeploy | Revision/image và traffic routing | Version/alias/config |
| Scaling | VM scale set/ASG/manual | Replica/node autoscaler | Concurrency/instance scaling |
| Network | NIC, route, firewall, DNS | Service, ingress, NetworkPolicy | VPC/VNet, egress, trigger path |
| Data | Disk, filesystem, database | PVC, volume, database | Object/database/queue; temp storage không bền |
| Backup | Disk/data/DB backup | Persistent data và cluster config | Data/dependency; function artifact được version hóa |
| Incident | OS, process, host, disk | Pod, node, scheduler, image | Trigger, runtime, retry, DLQ, quota |
| Capacity | CPU/RAM/disk/network | Requests/limits, nodes, replicas | Memory/CPU tier, concurrency, quota |
| Cost | Instance hours, disk, network | Node/cluster, storage, LB | Invocation, duration, allocation, dependency |

Ma trận giúp kiểm tra các nhóm chủ đề. Runbook chi tiết vẫn phải dựa trên dịch vụ và công nghệ đang triển khai.

## 31. Operational handover

Bàn giao chỉ hoàn tất khi đội nhận vận hành hiểu hệ thống và có thể thực hiện thao tác chính.

Gói bàn giao nên gồm:

- Service profile và ownership.
- Architecture/dependency/data-flow diagram.
- SLO/SLI và dashboard.
- Alert catalog và routing.
- Deployment/release/rollback runbook.
- Incident playbook.
- Backup/restore/DR runbook.
- Security access model.
- Capacity/performance baseline.
- Cost forecast và cost owner.
- Known issues và accepted risks.
- Lịch maintenance và certificate/secret rotation.
- Link repository, artifact và change history.
- Biên bản diễn tập và action item còn mở.

Nên tổ chức walkthrough: đội phát triển giải thích luồng, đội vận hành tự thực hiện một thao tác thường gặp và một tình huống lỗi trong môi trường an toàn. Nếu người nhận không thể làm theo runbook, tài liệu hoặc quy trình chưa hoàn tất.

## 32. Quản lý chất lượng và vòng đời runbook

Runbook nhanh chóng lỗi thời nếu không có owner và lịch review.

Mỗi tài liệu cần có:

- Owner.
- Version hoặc revision.
- Last reviewed date.
- Next review date.
- Applicable service/environment.
- Related release/config version nếu cần.
- Reviewer hoặc approver.
- Change history.

Kích hoạt review khi:

- Thay đổi kiến trúc hoặc dependency.
- Đổi runtime, image, OS hoặc scheduler.
- Đổi network, IAM hoặc secret flow.
- Thay đổi SLO, RTO hoặc RPO.
- Có incident hoặc DR exercise.
- Thay đổi vendor/service API.
- Thay đổi người trực hoặc support model.

Không chỉ review theo lịch; sự kiện thay đổi là lý do bắt buộc để kiểm tra lại tài liệu liên quan.

## 33. Các anti-pattern cần tránh

**Runbook chỉ có link dashboard.** Người trực vẫn không biết phải làm gì. Bổ sung điều kiện, bước kiểm tra, hành động an toàn và tiêu chí thành công.

**Không có owner cụ thể.** Alert bị chuyển vòng hoặc không ai nhận. Duy trì owner và escalation được kiểm tra.

**SLO chỉ là con số trên slide.** Không có metric và alert tương ứng. Tạo dashboard và kiểm tra nguồn dữ liệu.

**Backup chưa từng restore.** Không có bằng chứng phục hồi. Diễn tập restore và đo RTO/RPO.

**Rollback chỉ quay lại image.** Schema hoặc side effect không tương thích. Thiết kế migration và compensation.

**Tăng concurrency khi dependency đang quá tải.** Backlog có thể giảm tạm thời nhưng database sụp. Áp dụng backpressure và scale theo bottleneck.

**Cảnh báo quá nhiều.** On-call bị alert fatigue. Gộp alert theo symptom, severity và actionable runbook.

**Runbook lưu secret thật.** Tài liệu trở thành nguồn rò rỉ. Dùng secret reference và hướng dẫn truy cập có kiểm soát.

**Go-live không có diễn tập.** Đội vận hành chỉ phát hiện thiếu quyền hoặc bước sai khi production gặp sự cố. Thực hiện game day trước release.

**Không theo dõi action item.** Bài học sau incident không chuyển thành cải tiến. Gán owner, deadline và xác minh hoàn thành.

## 34. Checklist tổng hợp trước production

### Ownership và nghiệp vụ

- [ ] Service owner, technical owner và on-call đã xác nhận.
- [ ] Criticality, user impact và support hours đã rõ.
- [ ] Dependency map và data-flow diagram được cập nhật.
- [ ] Known risks và workaround có owner.

### Reliability và recovery

- [ ] SLI/SLO và error budget được định nghĩa và đo.
- [ ] Alert page/ticket có routing và runbook.
- [ ] RTO/RPO được business owner phê duyệt.
- [ ] Backup policy và restore test có bằng chứng.
- [ ] DR/failover/failback đã được diễn tập theo criticality.
- [ ] Capacity chịu được peak và failure scenario.

### Release và vận hành

- [ ] Artifact/version/config được truy vết.
- [ ] Deploy, smoke test, rollback và verification đã thử.
- [ ] Graceful shutdown, drain và maintenance procedure rõ.
- [ ] Runbook VM/container/serverless phù hợp workload.
- [ ] On-call đã walkthrough và thực hiện thao tác thử.
- [ ] Incident severity, commander và escalation đã rõ.

### Security và data

- [ ] IAM/identity theo least privilege.
- [ ] Secret và certificate có rotation/expiry owner.
- [ ] Network exposure và egress được kiểm soát.
- [ ] Image/dependency scan đạt policy.
- [ ] Encryption, audit, retention và data classification đạt yêu cầu.
- [ ] Không có secret hoặc dữ liệu nhạy cảm trong runbook/log.

### Performance và cost

- [ ] Load, peak, soak và failure test đạt ngưỡng đã định.
- [ ] Baseline CPU/memory/network/latency/queue được lưu.
- [ ] Quota và scaling limit được xác minh.
- [ ] Cost owner, tags, budget và anomaly alert đã thiết lập.
- [ ] Cost per request/job/transaction được theo dõi.

### Governance

- [ ] Readiness review có biên bản và quyết định Go/No-Go.
- [ ] Residual risk được owner chấp thuận.
- [ ] Runbook có owner, revision và ngày review.
- [ ] Action item còn mở có deadline và người chịu trách nhiệm.

## 35. Kết luận

Runbook biến kiến thức vận hành thành các bước có thể thực hiện và kiểm chứng; operational readiness chứng minh workload có người chịu trách nhiệm, có khả năng triển khai và rollback, được giám sát, bảo vệ dữ liệu, phục hồi sau sự cố và kiểm soát chi phí. Các yêu cầu này cần được áp dụng theo mô hình compute: VM cần quản lý OS và host; container cần quản lý rollout, node và volume; serverless cần quản lý trigger, concurrency, retry và event delivery.

Một quyết định Go chỉ nên được đưa ra khi có bằng chứng phù hợp với criticality và SLO: dashboard/alert hoạt động, runbook đã walkthrough, backup đã restore thử, rollback đã diễn tập, security review hoàn tất, capacity và chi phí được kiểm tra. Sau go-live, cập nhật runbook sau mỗi change, incident và DR exercise để tài liệu luôn phản ánh hệ thống thực tế.
