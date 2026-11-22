# Diễn tập phục hồi và kiểm chứng RTO, RPO thực tế

## Mục tiêu học tập

Một kế hoạch phục hồi thảm họa (Disaster Recovery - DR) chỉ có giá trị khi đội ngũ có thể thực hiện được trong điều kiện áp lực, với dữ liệu, quyền truy cập, nhân lực và dependency thực tế. Sơ đồ kiến trúc dự phòng hoặc bản runbook chưa được chạy thử không chứng minh rằng hệ thống có thể phục hồi trong thời gian cam kết. Credential có thể hết hạn, bản backup có thể không restore được, DNS cache có thể kéo dài thời gian chuyển vùng, dữ liệu replication có thể bị trễ và người trực có thể thiếu quyền để thực hiện bước quan trọng.

**Diễn tập DR** là quá trình kiểm chứng khả năng khôi phục dịch vụ và dữ liệu trước các tình huống gián đoạn đã xác định. Hai chỉ số cốt lõi là:

- **RTO (Recovery Time Objective):** thời gian mục tiêu tối đa để khôi phục một dịch vụ hoặc năng lực nghiệp vụ sau sự cố, theo điểm bắt đầu và tiêu chí phục hồi đã thống nhất.
- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa có thể chấp nhận, biểu diễn bằng khoảng thời gian dữ liệu trước sự cố mà tổ chức có thể phải tái tạo hoặc chấp nhận mất.

RTO/RPO là mục tiêu cần kiểm chứng, không phải số tự động được bảo đảm chỉ vì chọn một dịch vụ backup hay multi-region. Kết quả diễn tập phải đo được thời gian thực tế, điểm dữ liệu phục hồi, tính toàn vẹn nghiệp vụ, năng lực vận hành và các giới hạn còn tồn tại.

Bài học thuộc chương **Phục hồi thảm họa**, tập trung vào **diễn tập phục hồi và kiểm chứng RTO, RPO thực tế**. Trong bối cảnh Cloud Architecture, diễn tập phải gắn với yêu cầu nghiệp vụ, mạng, compute, database, storage, mô hình triển khai, bảo mật và chi phí; đồng thời đánh giá độ tin cậy, khả năng mở rộng và vận hành theo Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt RTO, RPO, MTD/MAO, MBCO, availability và recovery time thực tế.
- Xác định điểm bắt đầu/kết thúc đo RTO và phương pháp đo RPO theo từng loại dữ liệu.
- Phân loại workload theo criticality, dependency và yêu cầu khôi phục.
- Chọn tabletop exercise, walkthrough, component test, restore test, failover test và game day.
- Xây dựng kịch bản DR có giả thuyết, phạm vi, guardrail, tiêu chí thành công và điều kiện dừng.
- Kiểm chứng backup, point-in-time recovery, replication, DNS/network, IAM, secrets và capacity.
- Thực hiện recovery theo thứ tự dependency, xác minh tính toàn vẹn dữ liệu và business transaction.
- Đo kết quả thực tế, ghi evidence, nhận diện sai lệch RTO/RPO và xử lý vấn đề.
- Thiết kế runbook, vai trò chỉ huy, liên lạc, escalation và quyết định failback.
- Xây dựng kế hoạch cải tiến, lịch diễn tập và ngân sách DR có thể kiểm toán.

## 1. Vì sao phải diễn tập DR?

Một hệ thống có thể được thiết kế với backup hàng ngày và database replica ở region khác, nhưng trong sự cố thực tế vẫn có thể không phục hồi đúng mục tiêu. Ví dụ:

- Backup job chạy thành công nhưng file backup bị lỗi hoặc thiếu transaction log cần cho point-in-time recovery.
- Database replica có lag lớn; chuyển sang replica gây mất nhiều dữ liệu hơn RPO.
- Ứng dụng khởi động tại region dự phòng nhưng không truy cập được secret, KMS key, private DNS hoặc external API allowlist.
- Capacity ở region dự phòng chỉ đủ một phần traffic; sau failover, autoscaling không thể mở rộng do quota.
- Queue và event consumer được khởi động lại nhưng xử lý lại message gây duplicate side effect.
- DNS record được đổi nhưng client resolver hoặc connection pool giữ endpoint cũ.
- Người trực không có quyền truy cập tài khoản cloud hoặc thiếu MFA/device/credential trong môi trường DR.
- Runbook giả định một người thực hiện tuần tự, nhưng trong thực tế các bước phụ thuộc lẫn nhau hoặc chờ phê duyệt.

Diễn tập làm lộ khoảng cách giữa **thiết kế dự kiến** và **năng lực đã được chứng minh**.

### 1.1. Backup, high availability và disaster recovery không giống nhau

| Khái niệm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Backup | Có bản sao dữ liệu để khôi phục khi dữ liệu gốc mất/hỏng | Snapshot, database backup, object versioning |
| High Availability (HA) | Giảm gián đoạn do lỗi thành phần đơn lẻ | Multi-AZ database, redundant instances |
| Disaster Recovery (DR) | Khôi phục workload khi failure domain lớn bị mất | Khôi phục sang region khác |
| Business Continuity | Duy trì chức năng nghiệp vụ ở mức chấp nhận được | Quy trình vận hành thủ công tạm thời |
| Resilience | Chịu lỗi, thích ứng và phục hồi | Bulkhead, retry, failover, restore |

HA không thay thế DR. Multi-AZ có thể bảo vệ khỏi lỗi zone nhưng không nhất thiết bảo vệ khỏi xóa nhầm dữ liệu được replicate, lỗi logic lan rộng hoặc sự cố toàn region. Backup cũng không thay thế HA vì restore từ backup thường mất nhiều thời gian hơn failover.

### 1.2. Failure domain cần kiểm chứng

Có thể diễn tập theo phạm vi:

- Instance, node hoặc container.
- Availability Zone.
- Region.
- Database cluster hoặc storage service.
- Network, DNS, identity provider hoặc KMS.
- Control plane, CI/CD hoặc artifact registry.
- SaaS/external provider.
- Con người, quy trình và quyền truy cập.
- Ransomware, credential compromise hoặc dữ liệu bị xóa/sửa sai.

Một kịch bản DR phải mô tả rõ điều gì bị mất và điều gì vẫn hoạt động. “Region down” quá mơ hồ nếu không nói rõ control plane, DNS, identity, data replica, external dependencies và operator access.

## 2. Đặt mục tiêu RTO, RPO từ yêu cầu nghiệp vụ

### 2.1. RTO là gì?

RTO là khoảng thời gian mục tiêu để khôi phục một dịch vụ hoặc quy trình nghiệp vụ về mức vận hành đã định sau sự cố.

Ví dụ: dịch vụ xác nhận booking có RTO 60 phút. Điều này có nghĩa tổ chức cần khôi phục chức năng xác nhận booking trong 60 phút theo định nghĩa được phê duyệt. Nó không nhất thiết có nghĩa toàn bộ analytics, export và báo cáo phải hoạt động lại trong cùng thời gian.

RTO cần nêu rõ:

- Điểm bắt đầu: lúc sự cố xảy ra, lúc monitoring phát hiện hay lúc incident commander tuyên bố DR?
- Điểm kết thúc: hệ thống process khởi động, endpoint truy cập được, giao dịch thành công hay đạt đủ capacity/SLO?
- Phạm vi: một service, user journey hay toàn bộ business process?
- Điều kiện tải: smoke test, tải tối thiểu hay tải đại diện production?
- Phạm vi vùng: một AZ, region, account hoặc provider?

Nếu không thống nhất điểm bắt đầu/kết thúc, hai lần diễn tập không thể so sánh.

### 2.2. RPO là gì?

RPO là mức mất dữ liệu tối đa có thể chấp nhận khi khôi phục. Có thể diễn đạt bằng thời gian, nhưng khi đo thực tế cần xác định dữ liệu hoặc transaction cuối cùng được bảo vệ.

Ví dụ RPO 5 phút nghĩa là tổ chức chấp nhận có thể phải phục hồi về trạng thái cách thời điểm sự cố tối đa 5 phút, theo dữ liệu chuẩn và phương thức recovery đã chọn. Nó không bảo đảm mọi bản ghi trong năm phút gần nhất đều tồn tại; cần kiểm chứng replication/backup và transaction commit.

### 2.3. MTD/MAO và MBCO

- **MTD (Maximum Tolerable Downtime)** hoặc **MAO (Maximum Acceptable Outage):** thời gian gián đoạn tối đa mà nghiệp vụ có thể chịu trước khi hậu quả vượt ngưỡng chấp nhận.
- **MBCO (Minimum Business Continuity Objective):** mức dịch vụ tối thiểu cần duy trì trong hoặc sau sự cố.
- **RTO:** mục tiêu thời gian khôi phục một dịch vụ/năng lực cụ thể.
- **RPO:** điểm dữ liệu tối đa có thể mất theo thời gian.

RTO nên nhỏ hơn MTD/MAO để còn thời gian xác minh, xử lý backlog và khôi phục hoạt động bình thường. MBCO giúp xác định có thể khôi phục theo từng giai đoạn thay vì chờ toàn bộ chức năng.

### 2.4. Ví dụ phân loại nghiệp vụ

| Năng lực | MTD minh họa | RTO mục tiêu | RPO mục tiêu | MBCO khi phục hồi |
| --- | ---: | ---: | ---: | --- |
| Xác nhận booking | 2 giờ | 45 phút | 1 phút | Xác nhận/tra cứu booking cốt lõi |
| Payment status | 1 giờ | 30 phút | 30 giây | Tra cứu trạng thái và reconciliation |
| Search/recommendation | 8 giờ | 4 giờ | 1 giờ | Search cơ bản, có thể bỏ recommendation |
| Notification | 24 giờ | 8 giờ | 15 phút | Queue được bảo toàn và gửi bù |
| Analytics dashboard | 48 giờ | 24 giờ | 24 giờ | Báo cáo gần nhất có watermark rõ |

Các con số chỉ là ví dụ để luyện tập. Mỗi mục tiêu phải được business owner xác nhận dựa trên doanh thu, khách hàng, quy định, hợp đồng, dữ liệu và khả năng đầu tư. Không sao chép một bảng mục tiêu cho mọi module.

## 3. RTO phải đo toàn bộ chuỗi phục hồi

Một lỗi thường gặp là đo thời gian từ lúc bắt đầu restore database đến lúc restore command báo success. Trong thực tế, business recovery còn có nhiều bước.

~~~mermaid
flowchart LR
    D["Incident detected"] --> A["Declare DR / decide strategy"]
    A --> F["Provision/failover infrastructure"]
    F --> N["Network, DNS, IAM, secrets"]
    N --> DB["Restore/promote database"]
    DB --> APP["Deploy/start application"]
    APP --> V["Validate data and dependencies"]
    V --> T["Business transaction tests"]
    T --> C["Open traffic / scale capacity"]
~~~

Thời gian end-to-end có thể gồm:

1. Phát hiện và xác nhận sự cố.
2. Tuyên bố DR và kích hoạt vai trò.
3. Chọn recovery point và recovery strategy.
4. Cấp compute/network/storage hoặc chuyển traffic.
5. Khôi phục/promote database và kiểm tra dữ liệu.
6. Khôi phục secrets, identity, certificates và config.
7. Deploy ứng dụng, worker, scheduler và integration.
8. Chạy smoke test, integrity check và business transaction.
9. Mở traffic có kiểm soát, tăng capacity.
10. Xác minh SLO, backlog và ổn định sau phục hồi.

Nếu chỉ đo bước database restore, RTO báo cáo sẽ thiếu thời gian quan trọng.

### 3.1. Phân rã RTO theo workstream

| Workstream | Thời gian kế hoạch | Thời gian thực tế | Dependency/owner |
| --- | ---: | ---: | --- |
| Declare incident | 5 phút | Đo trong diễn tập | Incident commander |
| Network/IAM/secrets | 10 phút | Đo trong diễn tập | Cloud/platform |
| Database recovery | 20 phút | Đo trong diễn tập | DBA/data |
| Compute/application | 15 phút | Đo trong diễn tập | App/platform |
| Validation/business test | 10 phút | Đo trong diễn tập | QA/business |
| Traffic ramp-up | 10 phút | Đo trong diễn tập | SRE/operations |
| **Tổng tuần tự tham khảo** | **70 phút** | **Đo end-to-end** | |

Một số workstream có thể thực hiện song song. Không đơn giản cộng tất cả duration nếu dependency graph cho phép chạy đồng thời; cần đo critical path. Ngược lại, không giả định song song nếu thiếu dữ liệu, quyền hoặc người phụ trách.

## 4. Đo RPO bằng dữ liệu thực tế

RPO không chỉ là khoảng cách giữa hai timestamp của backup. Cần kiểm tra transaction nào đã được commit, replicate, ghi vào log hoặc xuất khỏi hệ thống tại thời điểm failure.

### 4.1. Tập marker transaction

Trong diễn tập, có thể tạo các marker transaction định kỳ có sequence tăng dần và timestamp từ nguồn đồng bộ:

~~~sql
CREATE TABLE dr_recovery_marker (
    marker_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    payload_checksum VARCHAR(128) NOT NULL
);
~~~

Một generator ghi marker theo chu kỳ vào database nguồn. Sau failover/restore, nhóm recovery kiểm tra marker lớn nhất có mặt, checksum và sequence gap. Cần đảm bảo marker transaction đại diện cho đúng commit path được bảo vệ; một marker ghi vào DB khác hoặc chỉ ở cache không chứng minh dữ liệu nghiệp vụ đã được bảo vệ.

### 4.2. Tính recovery point

Ví dụ:

- Thời điểm sự cố giả lập: 12:00:00 UTC.
- Transaction đã commit cuối cùng ở nguồn trước sự cố: 11:59:58 UTC.
- Transaction mới nhất có mặt và đã xác minh ở recovery target: 11:59:52 UTC.

~~~text
Observed data gap
  = Incident time - Latest verified recovered commit
  = 12:00:00 - 11:59:52
  = 8 seconds
~~~

Nếu RPO mục tiêu là 30 giây, kết quả này đạt trong lần thử. Tuy nhiên cần lặp lại ở peak load, trong lúc replication lag tăng và ở failure mode khác. Một lần test không chứng minh RPO cho mọi điều kiện.

### 4.3. Kiểm chứng tính toàn vẹn, không chỉ record mới nhất

Ngoài marker, cần:
- Kiểm tra transaction sequence liên tục hoặc giải thích gap.
- Đối soát số lượng booking/payment/ledger.
- Kiểm tra foreign key và business invariant.
- Kiểm tra checksum/manifest cho object/file.
- Kiểm tra outbox/inbox và event offset.
- Xác nhận không có duplicate side effect sau replay.
- Ghi rõ record nào bị mất, bị đảo, bị trùng hoặc cần reconciliation.

Một database có timestamp mới nhất nhưng thiếu một phần transaction giữa chừng vẫn có thể vi phạm RPO về mặt nghiệp vụ.

## 5. Phân loại chiến lược phục hồi

Các chiến lược DR thường đánh đổi chi phí duy trì môi trường dự phòng với tốc độ phục hồi.

| Strategy | Mô tả | Chi phí tương đối | RTO/RPO tiềm năng | Điều phải kiểm chứng |
| --- | --- | --- | --- | --- |
| Backup and restore | Khôi phục từ backup/snapshot và dựng lại môi trường | Thấp hơn khi bình thường | RTO dài hơn, RPO phụ thuộc backup/log | Restore time, backup integrity, keys, catalog |
| Pilot light | Một phần nền tảng tối thiểu luôn có ở vùng DR | Trung bình | Nhanh hơn backup-only | Capacity scale-up, config, data replication |
| Warm standby | Môi trường gần hoàn chỉnh, chạy capacity thấp | Cao hơn | RTO ngắn hơn, RPO phụ thuộc replication | Promote, scale, DNS, data lag |
| Multi-site active/passive | Hai site sẵn sàng, một site phục vụ chính | Cao | Có thể nhanh nếu failover được tự động hóa | Split-brain, routing, consistency, capacity |
| Active/active | Nhiều site cùng phục vụ | Rất cao và phức tạp | Có thể duy trì service khi một site lỗi | Conflict, routing, global state, cost |

Tên chiến lược không bảo đảm một mức RTO/RPO cụ thể. Một warm standby thiếu quota hoặc chưa được deploy image mới có thể phục hồi chậm hơn pilot light được automation tốt.

### 5.1. Chọn strategy theo workload

Không nhất thiết mọi service dùng cùng DR strategy. Booking write path có thể cần warm standby; analytics có thể dùng backup/restore; static assets có thể được sao chép cross-region; notification có thể dựa queue retention và replay.

Cần lập dependency map để tránh service được chọn strategy nhanh nhưng lại phụ thuộc dịch vụ khác chỉ có backup restore dài hơn.

## 6. Chuẩn bị trước diễn tập: inventory và assumptions

### 6.1. Recovery inventory

Inventory tối thiểu gồm:

- Service name, owner, tier và business criticality.
- RTO/RPO/MTD/MBCO.
- Region, account/project, VPC/VNet, subnet, route, firewall.
- Compute image, artifact registry, deployment manifest và IaC.
- Database, storage, backup vault, replication topology.
- KMS keys, certificates, secrets và identity dependencies.
- DNS zone, endpoint, CDN, WAF và traffic routing.
- Queue, event topic, scheduler, workflow và consumer offset.
- External API, allowlist, webhook và quota.
- Monitoring, alert, log, trace và status communication.
- Backup retention, restore test evidence và last verified date.

Inventory phải có owner và thời điểm kiểm tra. Một URL tài liệu cũ không chứng minh resource vẫn tồn tại.

### 6.2. Recovery dependency graph

~~~mermaid
flowchart TB
    IAM["Identity / KMS / secrets"] --> NET["Network / DNS / certificates"]
    ART["Artifacts / images / IaC"] --> APP["Compute / application"]
    NET --> APP
    DATA["Database / object storage"] --> APP
    Q["Queue / event bus"] --> APP
    APP --> EXT["External providers"]
    APP --> TEST["Business validation"]
    DATA --> TEST
    EXT --> TEST
~~~

Một trình tự restore chỉ đúng nếu dependency đã sẵn sàng. Ví dụ ứng dụng không thể đọc backup được mã hóa nếu KMS key không khả dụng; worker không thể xử lý event nếu queue policy/identity chưa được khôi phục.

### 6.3. Recovery access

Cần xác minh:
- Người trực có quyền vào account/region DR không?
- MFA/device và break-glass credential có hoạt động không?
- Secret manager/KMS được truy cập bằng identity nào?
- Có quyền đọc backup và tạo compute/network không?
- Quy trình phê duyệt khẩn cấp có khả dụng ngoài giờ không?
- Tài khoản emergency có được thử nghiệm và audit không?

Không lưu password hoặc recovery secret trong runbook. Runbook chỉ dẫn tới secret manager và cách yêu cầu quyền an toàn.

## 7. Thiết kế chương trình diễn tập DR

Một chương trình tốt tăng dần mức độ thực tế và rủi ro. Không nên lần đầu kiểm tra restore database bằng cách tắt production region.

### 7.1. Các cấp độ diễn tập

| Loại | Cách thực hiện | Mức rủi ro | Bằng chứng |
| --- | --- | --- | --- |
| Tabletop | Nhóm thảo luận tình huống và quyết định | Thấp | Decision log, gap list |
| Runbook walkthrough | Đọc và mô phỏng từng bước, không thay đổi hệ thống | Thấp | Step owner, missing access, ambiguous instructions |
| Component restore test | Restore DB/file vào môi trường cô lập | Thấp-trung bình | Duration, integrity, restore logs |
| Application recovery test | Dựng ứng dụng ở môi trường DR và chạy test | Trung bình | End-to-end recovery time |
| Failover/failback exercise | Chuyển traffic/primary theo kế hoạch | Cao hơn | Routing, data, consistency, RTO/RPO |
| Game day | Tiêm lỗi có giới hạn khi workload thật hoặc canary đang chạy | Tùy phạm vi | Blast radius, detection, mitigation |
| Full-scale DR exercise | Mô phỏng mất failure domain lớn và vận hành DR site | Cao | Evidence end-to-end, roles, costs |

### 7.2. Mục tiêu diễn tập phải đo được

Một mục tiêu tốt ví dụ:

“Trong staging với traffic mô phỏng 40% peak, nhóm recovery có thể khôi phục booking API tại region B trong tối đa 45 phút; recovery point không cũ hơn 60 giây; 100% marker transaction trước recovery point hợp lệ; payment reconciliation không có duplicate charge; service đạt 95% throughput mục tiêu trong 15 phút sau khi mở traffic.”

Mục tiêu này có điều kiện đo cụ thể. Cần chỉ rõ môi trường, workload, clock, transaction marker và business tests.

### 7.3. Exercise charter

Trước diễn tập, ghi:

- Mục đích và scope.
- Scenario và failure domain giả định.
- Hệ thống/tenant/region bị ảnh hưởng.
- Participants, role và decision authority.
- Start/stop conditions.
- Safety guardrails và rollback.
- RTO/RPO/SLO được kiểm chứng.
- Data classification và môi trường sử dụng.
- Evidence to capture.
- Communication channel.
- Chi phí tối đa hoặc budget guardrail.
- Phương án xử lý nếu diễn tập tạo incident thật.

## 8. Vai trò và điều phối trong diễn tập

Một cuộc diễn tập cần vai trò rõ ràng. Người thao tác kỹ thuật không nên đồng thời là người duy nhất ghi log và phê duyệt mọi quyết định.

| Vai trò | Trách nhiệm |
| --- | --- |
| Exercise controller | Điều phối kịch bản, inject sự kiện, giữ scope an toàn |
| Incident commander | Ra quyết định, điều phối ưu tiên và escalation |
| Recovery lead | Điều phối các workstream phục hồi kỹ thuật |
| Data lead | Khôi phục, xác minh consistency và RPO |
| Application lead | Deploy, config, integration và smoke test |
| Network/security lead | DNS, routing, IAM, key, certificate và firewall |
| Business owner | Xác nhận MBCO và business transaction |
| Scribe/timekeeper | Ghi timestamp, quyết định, blocker và evidence |
| Observer | Ghi nhận cách nhóm làm việc và khoảng trống runbook |

Với nhóm nhỏ, một người có thể giữ nhiều vai trò nhưng cần phân định lúc nào họ đang thực hiện, lúc nào đang ra quyết định.

### 8.1. Incident timeline

Ghi timestamp theo cùng một nguồn thời gian (UTC hoặc timezone quy định):

- T0: failure injected hoặc scenario start.
- T1: monitoring phát hiện.
- T2: incident declared.
- T3: DR decision/activation.
- T4: recovery infrastructure ready.
- T5: data restored/promoted.
- T6: application ready.
- T7: business validation pass.
- T8: traffic mở và service đạt MBCO.
- T9: workload đạt SLO bình thường hoặc trạng thái ổn định đã định.

RTO có thể được tính từ T0 đến T8 hoặc một mốc khác đã thống nhất trước. Không thay định nghĩa sau khi thấy kết quả để biến test fail thành pass.

## 9. Kịch bản diễn tập database và dữ liệu

### 9.1. Backup restore

Kịch bản:
1. Chọn backup đã lưu theo chính sách.
2. Kiểm tra backup ID, thời gian, retention và encryption metadata.
3. Khôi phục vào account/region test.
4. Cấp quyền, key và network.
5. Mở database ở trạng thái phù hợp.
6. Chạy integrity checks và marker validation.
7. Đo từ lúc kích hoạt tới khi ứng dụng query được và business transaction thành công.

Bằng chứng cần lưu: backup identifier, recovery point, restore start/end, engine/version, error log, checksum/record count, cost và các thao tác thủ công.

### 9.2. Point-in-time recovery

PITR cần kiểm chứng backup base và transaction log/binlog/WAL có đủ đến thời điểm cần phục hồi. Thử khôi phục về thời điểm:
- Ngay trước một thao tác xóa nhầm.
- Sau transaction hợp lệ cuối cùng.
- Trước một migration gây lỗi.

Xác nhận timezone và độ chính xác timestamp; sai lệch clock có thể làm chọn nhầm recovery point. Test trên môi trường cô lập, không overwrite nguồn dữ liệu production.

### 9.3. Replication failover

Kịch bản có thể:
- Ghi transaction marker liên tục ở primary.
- Theo dõi replication lag.
- Giả lập primary không thể phục vụ.
- Promote replica theo quy trình.
- So sánh sequence/checksum/ledger.
- Chuyển application endpoint.
- Test read/write, lock, transaction và connection pool.
- Kiểm tra replica cũ không tự trở thành writer song song.

Đo RPO theo transaction cuối cùng đã xác minh ở replica; đo RTO end-to-end tới lúc business transaction thành công. Kiểm tra split-brain và fencing để tránh hai primary cùng nhận write.

### 9.4. Object storage và file data

Cần thử:
- Restore object version hoặc backup.
- Kiểm tra lifecycle/retention không xóa bản cần thiết.
- Xác minh KMS key, bucket policy, replication rule và object lock.
- Kiểm tra manifest, checksum, file count và partition completeness.
- Đọc thử file với identity của ứng dụng DR.
- Restore metadata/catalog nếu lakehouse table phụ thuộc transaction metadata.

Object replication không luôn đồng nghĩa đồng bộ mọi metadata, version, delete marker và quyền. Hãy kiểm tra semantics của dịch vụ storage.

## 10. Kịch bản network, DNS, identity và security

DR có thể có dữ liệu nhưng ứng dụng không thể truy cập do control plane phụ thuộc.

### 10.1. DNS và traffic routing

Test:
- DNS record/zone có tồn tại ở recovery account/region không?
- TTL cấu hình có phù hợp mục tiêu failover?
- Resolver/client giữ cache trong bao lâu?
- Health check có phát hiện đúng failure không?
- CDN/WAF/certificate có phục vụ endpoint mới không?
- Outbound allowlist và webhook destination có cập nhật không?
- Connection pool có resolve lại endpoint sau failover không?

TTL thấp không đảm bảo failover tức thời; resolver và application runtime có caching riêng. Đo từ thời điểm cập nhật tới khi client đại diện truy cập đúng endpoint.

### 10.2. Identity và secrets

Diễn tập:
- Tạo/assume role tại DR.
- Truy cập secret manager và decrypt key.
- Xoay credential hoặc dùng credential đã chuẩn bị.
- Xác minh service identity của application, worker và migration.
- Kiểm tra certificate chain và expiry.
- Kiểm tra audit trail và break-glass process.

Không copy key/secret tùy tiện từ production sang region khác. Cần policy và key management có thiết kế DR.

### 10.3. Network capacity

Region DR có thể dùng CIDR, NAT, firewall, load balancer, private endpoint và quota khác. Kiểm tra:
- IP address/subnet capacity.
- Route table và peering/transit gateway.
- Security group/firewall rules.
- NAT gateway/egress capacity.
- DNS resolver, private zone và service discovery.
- Cross-region bandwidth/latency.
- Quota cho load balancer, public IP và network interface.

## 11. Kịch bản compute, application và integration

### 11.1. IaC và artifact

Một bản DR deployment cần artifact có thể tái tạo:

- IaC version và state backend.
- Container image/package immutable.
- Runtime/configuration compatible.
- Schema migration và compatibility.
- Feature flag.
- Secret reference.
- SBOM/signature nếu áp dụng.
- Dependency lock và package registry mirror/cache.

Kiểm tra image/package còn tồn tại và có thể pull từ DR. Nếu artifact registry nằm ở region bị mất, DR deployment có thể không khởi động.

### 11.2. Capacity tại recovery site

Không chỉ kiểm tra pod Ready. Hãy chạy tải đại diện:

- API request rate và latency.
- Worker throughput.
- Database connections và query latency.
- Queue consumer lag.
- CPU/memory autoscaling.
- Cache warm-up và cold-start impact.
- Rate limit của external provider.
- Quota compute/network/storage tại region dự phòng.

Warm standby có thể phải scale từ 20% lên 100% capacity; thời gian quota approval hoặc autoscaling không đạt mục tiêu phải được đưa vào RTO.

### 11.3. External dependency

Payment/email/tax provider có thể chỉ cho phép egress IP production. Region DR cần IP allowlist mới. Test webhook URL, OAuth redirect, API credential, certificate, rate limit và provider account. Không giả định dependency bên ngoài tự biết platform đã chuyển vùng.

## 12. Khôi phục theo thứ tự và kiểm chứng business

Sau khi hạ tầng lên, phải xác minh nghiệp vụ. Một database healthy không chứng minh booking/payment đúng.

### 12.1. Recovery validation layers

1. **Infrastructure validation:** resource active, route, health check, capacity.
2. **Data validation:** recovery point, checksum, schema, transaction sequence.
3. **Application validation:** process, dependencies, authentication, configuration.
4. **Integration validation:** payment, queue, storage, external API.
5. **Business validation:** tạo/đọc booking, trạng thái payment, inventory, refund/reconciliation.
6. **Operational validation:** alerts, logs, access, backup sau recovery.
7. **Traffic validation:** canary, error rate, p95/p99 và throughput.

### 12.2. Business transaction test

Ví dụ flow thử trong DR:
- Tạo booking test có định danh riêng.
- Kiểm tra inventory invariant.
- Gửi payment sandbox hoặc test operation.
- Kiểm tra booking/payment state.
- Xác nhận outbox event được phát.
- Kiểm tra notification worker hoặc queue.
- Reconcile ledger và đảm bảo không duplicate.
- Xóa/đóng transaction test theo policy.

Không dùng khoản thanh toán thật hoặc dữ liệu khách thật nếu không có phê duyệt và kiểm soát tương ứng. Dùng dữ liệu giả lập/ẩn danh và sandbox phù hợp.

### 12.3. MBCO và phased recovery

Không phải mọi feature cần bật cùng lúc. Có thể phục hồi theo các giai đoạn:

| Phase | Năng lực | Kiểm tra |
| --- | --- | --- |
| 1. Minimum safe service | Authentication, booking lookup, critical writes hoặc chế độ read-only | Business owner xác nhận MBCO |
| 2. Core operation | Booking/payment/inventory | Transaction test và reconciliation |
| 3. Customer experience | Search, notification, export | Freshness và queue lag |
| 4. Full service | Analytics, reporting, noncritical jobs | SLO, backlog và data completeness |

Thứ tự phụ thuộc nghiệp vụ. Có tình huống read-only an toàn hơn write; có tình huống cần tạm ngừng nhận booking nhưng vẫn cho tra cứu.

## 13. Failover, failback và tránh split-brain

Failover chuyển workload sang recovery site. Failback đưa workload về site chính hoặc một topology ổn định mới. Failback thường phức tạp vì trong thời gian DR, dữ liệu đã phát sinh ở site thay thế.

### 13.1. Checklist failover

- Incident commander tuyên bố và ghi thời điểm.
- Xác nhận primary failure domain không còn nhận write hoặc đã được fencing.
- Chọn recovery point và chấp nhận RPO thực tế.
- Promote database/replica theo đúng procedure.
- Cập nhật DNS/routing/load balancer.
- Deploy hoặc scale application/worker.
- Tạm hạn chế workload không thiết yếu.
- Xác minh transaction, data integrity và business flow.
- Theo dõi backlog, replication và SLO.
- Thông báo trạng thái dịch vụ theo quy trình.

### 13.2. Fencing và split-brain

Nếu primary chỉ mất kết nối từ application nhưng vẫn có thể nhận write từ nơi khác, DR promotion có thể tạo hai writer độc lập. Cần fencing: vô hiệu hóa write ở primary cũ bằng cơ chế phù hợp, xác nhận leadership/lease/quorum hoặc network isolation trước khi mở writer mới.

Không chỉ dựa vào DNS để ngăn client mới tới primary cũ; client connection hiện tại và worker có thể còn kết nối trực tiếp.

### 13.3. Failback

Trước failback:
1. Chọn nguồn dữ liệu có thẩm quyền.
2. Đồng bộ data changes từ DR site về target.
3. Đối soát transaction và backlog.
4. Dừng/điều phối writes theo cutover plan.
5. Xác minh replication lag bằng 0 hoặc trong ngưỡng đã duyệt.
6. Chuyển traffic có kiểm soát.
7. Theo dõi error/latency và rollback condition.
8. Khởi động lại replication/backup bảo vệ site chính.
9. Ghi lại data divergence và mọi transaction cần xử lý thủ công.

Không failback chỉ vì region chính đã “xanh”. Cần chứng minh dữ liệu hai phía và quyền write đã nhất quán.

## 14. Thiết kế kịch bản diễn tập mẫu

### 14.1. Scenario: mất region chính

**Giả thuyết:** region A mất khả năng phục vụ compute và primary database. Region B có warm standby database và minimum application capacity.

**Mục tiêu:**
- Business booking flow phục hồi trong RTO 45 phút.
- RPO booking không vượt 60 giây.
- Không tạo duplicate payment hoặc double booking.
- Search/dashboard có thể phục hồi sau core transaction.
- Traffic được mở theo canary, đạt 80% peak test throughput.

**Phạm vi:** staging, dữ liệu synthetic, provider sandbox, hai region test.

**Guardrails:** không chạm production DNS/traffic; không xóa backup; có người điều khiển; có kill switch nếu tài nguyên/chi phí vượt budget.

**Injects:**
- Replication lag tăng trước sự cố.
- Primary endpoint không truy cập được.
- DNS resolver giữ cache cũ.
- Một secret ở DR hết hạn.
- Image registry chính không truy cập được.
- Queue consumer nhận lại event sau failover.

**Success criteria:** ghi được RTO/RPO; marker và business invariant đạt; application DR phục vụ đúng endpoint; backlog được xử lý; không có side effect duplicate; runbook có evidence.

### 14.2. Scenario: xóa nhầm dữ liệu

**Giả thuyết:** một thao tác administrative xóa một tập booking và event history. Replication đã sao chép thao tác xóa.

**Mục tiêu:** PITR tới trước thời điểm xóa, xác minh record cần giữ và đưa dữ liệu khôi phục vào môi trường phục hồi logic mà không ghi đè các transaction hợp lệ phát sinh sau đó.

Test này kiểm chứng backup/PITR và quy trình logical recovery, không chỉ regional failover.

### 14.3. Scenario: credential/KMS unavailable

**Giả thuyết:** workload DR không thể giải mã secret hoặc backup do quyền/key phụ thuộc region chính.

**Mục tiêu:** chứng minh recovery role, key replication/availability và break-glass workflow hoạt động trong policy. Không xuất/di chuyển key trái kiểm soát để hoàn thành test.

## 15. Đo và báo cáo kết quả RTO/RPO

### 15.1. RTO observed

~~~text
Observed RTO
  = Time business service meets the agreed recovery criteria
    - Time the exercise failure begins
~~~

Nếu policy định nghĩa start tại thời điểm incident declaration thay vì inject time, phải ghi cả hai giá trị. Báo cáo cần nêu rõ clock source và timezone.

### 15.2. RPO observed

~~~text
Observed RPO
  = Incident time
    - Timestamp of latest verified recoverable business commit
~~~

Nếu nhiều loại dữ liệu có replication/backup policy khác nhau, hãy tính RPO riêng cho từng data domain. Booking database đạt 30 giây không có nghĩa object storage, queue, search index và audit logs cũng đạt.

### 15.3. RTO/RPO target so với actual

| Workload/data domain | Target RTO | Observed RTO | Target RPO | Observed RPO | Kết quả |
| --- | ---: | ---: | ---: | ---: | --- |
| Booking API | 45 phút | 52 phút | 60 giây | 35 giây | RTO fail, RPO pass |
| Payment ledger | 30 phút | 28 phút | 30 giây | 42 giây | RTO pass, RPO fail |
| Search index | 4 giờ | 95 phút | 1 giờ | 20 phút | Pass theo ví dụ |
| Analytics | 24 giờ | 7 giờ | 24 giờ | 8 giờ | Pass theo ví dụ |

Bảng chỉ minh họa cách báo cáo. Phải có evidence liên kết mỗi số với timeline, marker, backup ID và validation result. Không dùng “Pass” nếu chỉ kiểm tra process health mà chưa kiểm tra business correctness.

### 15.4. Đo percentile qua nhiều lần diễn tập

Một lần diễn tập đo một sample. RTO/RPO có thể biến động theo:
- Dung lượng dữ liệu.
- Load và replication lag.
- Region quota/capacity.
- Số lượng dependency.
- Số người có mặt và quyền truy cập.
- Backup age/retention.
- Thời điểm outage và provider health.

Lưu lịch sử nhiều lần, xem median và tail/worst observed. Với mục tiêu quan trọng, không thiết kế theo lần nhanh nhất. Cần margin để xử lý điều kiện bất lợi và biến động vận hành.

## 16. Evidence và báo cáo sau diễn tập

Mỗi claim cần bằng chứng:

| Claim | Evidence phù hợp |
| --- | --- |
| Restore hoàn tất trong 20 phút | Cloud operation timestamps, restore logs |
| RPO 30 giây | Marker sequence, verified commit timestamp |
| Application healthy | Health check và deployment status |
| Booking flow hoạt động | Business test ID, database rows, API result |
| Không duplicate payment | Provider sandbox ledger + internal ledger reconciliation |
| DNS cutover hoàn tất | Authoritative/resolver query và client observation |
| Security role hoạt động | Audit log, successful authorized operation |
| Capacity đủ | Load test report, CPU, latency, queue lag |
| Cost nằm trong budget | Cloud cost/resource report của exercise |

Báo cáo cần gồm:
- Scenario và version của exercise.
- Mục tiêu/assumption/guardrail.
- Timeline.
- RTO/RPO target và observed.
- Business validation results.
- Tác động và blast radius.
- Các bước thủ công/automation.
- Failure/gap, root cause, severity.
- Action item, owner, due date.
- Evidence link và dữ liệu nhạy cảm được xử lý ra sao.

Không lưu access token, private key hoặc payload PII trong evidence package. Evidence phải có quyền truy cập và retention phù hợp.

## 17. Cải tiến sau diễn tập

Diễn tập chỉ tạo giá trị khi gap được chuyển thành thay đổi có người chịu trách nhiệm.

### 17.1. Phân loại finding

- **Design gap:** kiến trúc không hỗ trợ RTO/RPO đã cam kết.
- **Automation gap:** phải thực hiện thủ công nhiều bước hoặc script dễ lỗi.
- **Data gap:** thiếu backup, replication, log, catalog hoặc integrity check.
- **Security/access gap:** thiếu quyền, key, secret, network rule.
- **Capacity gap:** DR site không đủ quota/compute/network.
- **Runbook gap:** thiếu bước, sai thứ tự hoặc thiếu decision criteria.
- **People gap:** thiếu training, role, on-call hoặc vendor contact.
- **Measurement gap:** không có clock, marker, log hay evidence cần thiết.

### 17.2. Action item có thể kiểm chứng

Một action item tốt ghi:

| Trường | Ví dụ |
| --- | --- |
| Finding | Database restore vượt RTO 15 phút do thiếu capacity |
| Root cause | Restore instance khởi tạo ở storage tier thấp |
| Corrective action | Thay đổi recovery configuration và tạo automation |
| Owner | Database platform team |
| Due date | Ngày được phê duyệt |
| Verification | Restore test lặp lại với dataset đại diện |
| Acceptance | p95 restore duration dưới target trong 3 lần test |
| Evidence | Exercise report/version/run ID |

Tránh action item “cải thiện DR” không có owner, hạn và tiêu chí đóng.

### 17.3. Re-test sau thay đổi

Sau khi sửa:
- Chạy component test liên quan.
- Chạy end-to-end exercise nếu thay đổi ảnh hưởng critical path.
- Cập nhật runbook và architecture decision record.
- Cập nhật RTO/RPO nếu business/cost decision thay đổi.
- Đào tạo đội vận hành và kiểm tra knowledge transfer.
- Đóng finding chỉ khi evidence đạt acceptance criteria.

## 18. Lịch diễn tập và duy trì khả năng sẵn sàng

Tần suất phụ thuộc risk, change rate và nghĩa vụ hợp đồng. Một chương trình mẫu:

| Tần suất minh họa | Hoạt động |
| --- | --- |
| Hàng tháng | Kiểm tra backup job, alert, replication lag, quyền truy cập |
| Hàng quý | Restore test database/file và tabletop cho workload critical |
| Nửa năm | Application recovery/failover test một failure domain |
| Hàng năm | Full-scale DR exercise có business owner và vendor liên quan |
| Sau thay đổi lớn | Re-test path bị ảnh hưởng: region, database engine, IAM, network, deployment |

Các mốc này là ví dụ. Workload có thay đổi thường xuyên, dữ liệu quan trọng hoặc quy định chặt có thể cần diễn tập dày hơn. Restore test nên diễn ra đủ thường xuyên để backup không trở thành thứ chỉ “có trên dashboard”.

### 18.1. Trigger diễn tập bất thường

Có thể tổ chức exercise ngoài lịch khi:
- Chuyển region/account hoặc thay đổi topology.
- Thay database engine, replication mode hoặc backup policy.
- Thay đổi KMS, identity provider, DNS hoặc network.
- Thêm critical dependency hoặc SaaS provider.
- Thay đổi retention, encryption hoặc data classification.
- RTO/RPO miss hoặc sự cố gần đây bộc lộ gap.
- Thay đổi lớn trong team/on-call/vendor support.

## 19. Chi phí và lựa chọn mức độ diễn tập

DR có chi phí từ standby capacity, cross-region replication, backup storage, restore compute, test data, traffic, egress, observability và nhân lực.

### 19.1. TCO của DR exercise

~~~text
DR program cost
  = Standby infrastructure
    + Backup and replication
    + Test environment/runtime
    + Cross-region transfer
    + Monitoring and evidence storage
    + Engineering and exercise time
    + Vendor/support cost
    + Remediation work
~~~

Không nên bỏ diễn tập để tiết kiệm chi phí nếu rủi ro gián đoạn lớn hơn. Có thể giảm chi phí bằng cách:
- Dùng synthetic/representative dataset có kiểm soát.
- Tự động hóa teardown sau test.
- Test từng component thường xuyên và full exercise ít hơn.
- Giới hạn traffic/load test trong budget.
- Sử dụng isolated account/project và quota guardrail.
- Tối ưu warm standby theo tier thay vì nhân đôi mọi dịch vụ.
- Đo cost per verified recovery exercise.

### 19.2. Cost of false confidence

Nếu tổ chức công bố RTO 30 phút nhưng chưa từng restore trong điều kiện đại diện, rủi ro là business continuity plan dựa trên giả định sai. Cost của một DR strategy không chỉ là hạ tầng; còn là xác suất không đạt mục tiêu, downtime, data loss và chi phí xử lý sự cố.

Quyết định đầu tư nên dựa trên business impact analysis và evidence thực tế; không chọn active/active chỉ vì có vẻ an toàn nếu chi phí và độ phức tạp vượt nhu cầu.

## 20. Bài tập thực hành

Một nền tảng đặt phòng hoạt động tại region A, có database primary, object storage, queue và 8 application service. Region B giữ database replica bất đồng bộ, backup object storage và pilot-light compute. Business yêu cầu:

- Booking service RTO 45 phút, RPO 60 giây.
- Payment ledger RTO 30 phút, RPO 30 giây.
- Search RTO 4 giờ, RPO 1 giờ.
- Notification RTO 8 giờ, RPO 15 phút.

Hãy thực hiện:

1. Vẽ dependency graph giữa identity/KMS, network/DNS, database, storage, queue, compute và external payment provider.
2. Xác định điểm bắt đầu/kết thúc RTO và phương pháp marker để đo RPO cho từng data domain.
3. Xây dựng exercise charter cho kịch bản mất region A, bao gồm scope, roles, guardrails và stop condition.
4. Lập timeline recovery với workstream có thể chạy tuần tự/song song; tính critical path.
5. Thiết kế component restore test cho database PITR và object storage, kèm checksum/transaction validation.
6. Thiết kế failover database replica; giải thích cách ngăn split-brain và đo replication lag.
7. Kiểm tra DNS, certificate, secret, KMS key, egress IP allowlist và quota region B.
8. Xác định MBCO theo từng giai đoạn và business transaction test tối thiểu.
9. Lập bảng evidence để chứng minh RTO/RPO; nêu cách xử lý nếu Booking đạt RTO nhưng Payment không đạt RPO.
10. Tính backlog recovery nếu queue tích lũy 180.000 message, consumer xử lý 600 message/giây và event mới tiếp tục đến 300 message/giây.
11. Thiết kế failback plan, fencing và reconciliation sau khi region A phục hồi.
12. Lập action register sau exercise, có owner, due date và acceptance test.
13. Đề xuất lịch diễn tập và TCO phù hợp với criticality từng workload.

**Gợi ý tự đánh giá:** Bài làm đạt khi mục tiêu RTO/RPO có định nghĩa đo được, test không chỉ dừng ở infrastructure health, dữ liệu được xác minh bằng marker/reconciliation, failover không tạo split-brain, và finding được chuyển thành action có thể re-test.

## 21. Checklist trước, trong và sau diễn tập

### Trước diễn tập

- [ ] Business owner phê duyệt RTO, RPO, MTD/MAO và MBCO.
- [ ] Scope/failure domain và assumption được ghi rõ.
- [ ] Inventory service, dependency, data, region, account và owner cập nhật.
- [ ] Backup/replication/retention/key được xác minh.
- [ ] Recovery access, MFA, IAM và break-glass được thử.
- [ ] Runbook có command/decision/validation và escalation.
- [ ] Exercise charter có guardrail, stop condition và rollback.
- [ ] Test data/sandbox/provider phù hợp được chuẩn bị.
- [ ] Evidence capture, clock source và timezone thống nhất.

### Trong diễn tập

- [ ] Ghi timeline T0...Tn và decision log.
- [ ] Chỉ tiêm lỗi trong scope được duyệt.
- [ ] Theo dõi blast radius và điều kiện dừng.
- [ ] Đo infrastructure, data, application và business recovery.
- [ ] Đo recovery point bằng marker/commit evidence.
- [ ] Kiểm tra business invariant, duplicate và reconciliation.
- [ ] Ghi mọi thao tác thủ công và blocker.
- [ ] Ghi quota, latency, capacity, backlog và chi phí.

### Sau diễn tập

- [ ] So sánh target/observed RTO và RPO theo từng workload.
- [ ] Xác minh tính toàn vẹn và sai lệch dữ liệu.
- [ ] Đánh giá MBCO và SLO sau khi mở traffic.
- [ ] Có report/evidence và owner review.
- [ ] Finding có severity, owner, due date, acceptance criteria.
- [ ] Runbook, IaC, architecture và training được cập nhật.
- [ ] Re-test finding quan trọng trước khi đóng.
- [ ] Cập nhật DR strategy và TCO khi mục tiêu không khả thi.

## 22. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi review DR exercise |
| --- | --- |
| **Operational Excellence** | Runbook, vai trò, timeline, evidence, postmortem và re-test có được quản lý như quy trình vận hành không? |
| **Security** | Recovery access, key, secrets, data masking, audit và break-glass có an toàn trong vùng DR không? |
| **Reliability** | Backup restore, replication, failover/failback, RTO/RPO và business integrity đã được thực chứng chưa? |
| **Performance Efficiency** | Recovery capacity, autoscaling, queue drain và traffic ramp có đạt workload mục tiêu không? |
| **Cost Optimization** | Standby, backup, replication, exercise và remediation có tương xứng business impact không? |
| **Sustainability** | Có tự động teardown test resources, tránh replication/backup thừa và quản lý retention hợp lý không? |

**Kết luận:** RTO và RPO chỉ đáng tin khi được đo trong diễn tập có phạm vi, điểm bắt đầu/kết thúc, dữ liệu marker và tiêu chí nghiệp vụ rõ ràng. Một lần restore thành công không chứng minh toàn bộ DR; cần kiểm chứng database, storage, network, identity, compute, external dependency, failover, failback và năng lực đội vận hành. Hãy lưu evidence, công bố khoảng cách so với mục tiêu, giao action có owner và chạy lại test sau sửa đổi. Đó là cách biến DR từ tài liệu giả định thành năng lực đã được thực chứng theo tinh thần Well-Architected.
