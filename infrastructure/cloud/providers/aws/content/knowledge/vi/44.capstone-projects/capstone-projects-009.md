# Diễn tập phục hồi thảm họa và xác minh RTO, RPO

Một hệ thống AWS có thể chạy ổn định trong nhiều tháng nhưng vẫn thất bại khi cần phục hồi từ sự cố nghiêm trọng. Backup có thể tồn tại nhưng không khôi phục được; Region dự phòng có thể được tạo nhưng thiếu secret, image hoặc quota; database có thể phục hồi nhưng ứng dụng không biết chuyển endpoint; DNS có thể đổi nhưng client vẫn giữ kết nối cũ. Vì vậy, khả năng phục hồi thảm họa (Disaster Recovery – DR) phải được thiết kế, diễn tập và đo lường bằng bằng chứng thực tế.

Hai chỉ số quan trọng để đặt mục tiêu phục hồi là Recovery Time Objective (RTO) và Recovery Point Objective (RPO). RTO xác định thời gian tối đa tổ chức chấp nhận để khôi phục dịch vụ sau sự cố. RPO xác định mức dữ liệu tối đa có thể mất, tính theo khoảng thời gian giữa thời điểm sự cố và điểm dữ liệu gần nhất có thể phục hồi. Hai mục tiêu này xuất phát từ tác động kinh doanh, không nên chọn chỉ vì một dịch vụ AWS có khả năng hỗ trợ một con số cụ thể.

Một buổi diễn tập DR kiểm tra toàn bộ chuỗi: phát hiện, quyết định kích hoạt, khôi phục hạ tầng và dữ liệu, chuyển traffic, xác minh nghiệp vụ, xử lý backlog và bàn giao vận hành. Kết quả phải cho biết RTO/RPO thực tế, bước nào gây chậm, dữ liệu nào bị mất hoặc không nhất quán, chi phí phục hồi và hành động cần hoàn thành. Bài học này hướng dẫn xây dựng một capstone DR trên AWS từ yêu cầu, kiến trúc, runbook đến kế hoạch kiểm chứng.

Trong module CLOUD_PROVIDERS_AWS, người học khám phá hạ tầng Region/AZ, IAM, VPC, compute, storage, database, integration và serverless để thiết kế hệ thống an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí. Bài này kết nối các kiến thức đó thành một quy trình diễn tập có thể review và lặp lại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt high availability, backup, disaster recovery và business continuity.
- Giải thích RTO, RPO, MTD/MAO và cách đo kết quả thực tế.
- Dùng Business Impact Analysis để đặt mục tiêu phục hồi theo quy trình kinh doanh.
- Xây dựng workload inventory, dependency map và recovery tier.
- So sánh Backup and Restore, Pilot Light, Warm Standby và Multi-Site Active/Active.
- Chọn dịch vụ AWS cho backup, replication, restore và traffic failover.
- Thiết kế DR cho S3, DynamoDB, RDS/Aurora, EBS, EFS và compute.
- Xác định yêu cầu về IAM, KMS, secrets, network, DNS, quota và artifact.
- Viết runbook có owner, điều kiện kích hoạt, stop condition và rollback/failback.
- Thiết kế tabletop, component restore, failover và failback exercise.
- Đo RTO/RPO bằng timestamp, dữ liệu đối soát và business validation.
- Ước tính chi phí DR và lập kế hoạch cải tiến sau diễn tập.

## 2. Phân biệt HA, backup, DR và business continuity

### 2.1. High Availability

High Availability (HA) giảm thời gian gián đoạn do lỗi thành phần hoặc hạ tầng trong phạm vi kiến trúc được thiết kế. Ví dụ:

- Triển khai compute trên nhiều Availability Zones.
- Dùng load balancer kiểm tra health và phân phối traffic.
- Dùng RDS Multi-AZ để hỗ trợ failover database trong Region.
- Dùng queue để tách producer khỏi consumer.
- Tự động thay thế instance hoặc task không khỏe.

HA thường xử lý lỗi đơn lẻ hoặc lỗi phạm vi hẹp. Nó không bảo đảm phục hồi khi toàn Region không khả dụng, dữ liệu bị xóa nhầm, ransomware mã hóa dữ liệu hoặc một thay đổi logic làm hỏng dữ liệu trên mọi replica.

### 2.2. Backup

Backup tạo bản sao dữ liệu tại một thời điểm hoặc theo lịch để có thể khôi phục. Backup hữu ích khi:

- Người dùng xóa nhầm dữ liệu.
- Ứng dụng ghi dữ liệu sai.
- Database bị corruption.
- Tài khoản hoặc workload bị xâm nhập.
- Cần khôi phục dữ liệu về thời điểm trước sự cố.

Backup phải được bảo vệ khỏi tài khoản và workload có thể gây ra sự cố ban đầu. Nếu một role ứng dụng có quyền xóa cả dữ liệu production lẫn backup, bản backup có thể không còn là phương án phục hồi độc lập.

### 2.3. Disaster Recovery

Disaster Recovery là khả năng khôi phục hệ thống và quy trình kinh doanh sau sự cố lớn. DR bao gồm dữ liệu, compute, network, identity, security, DNS, dependency bên ngoài, con người và quy trình ra quyết định.

Một bản backup không phải một kế hoạch DR hoàn chỉnh. Muốn khôi phục dịch vụ cần biết:

- Khôi phục dữ liệu vào đâu?
- Hạ tầng nào được tạo lại?
- Secret, certificate và KMS key lấy từ đâu?
- Endpoint và DNS chuyển như thế nào?
- Làm sao tránh hai Region cùng nhận write?
- Ai xác minh dữ liệu và chấp nhận mở traffic?

### 2.4. Business Continuity

Business Continuity (BC) bao gồm kế hoạch duy trì hoạt động kinh doanh trong và sau sự cố, kể cả khi hệ thống CNTT chưa phục hồi hoàn toàn. Ví dụ, cửa hàng có thể ghi nhận đơn offline, chuyển sang quy trình thủ công hoặc xử lý giao dịch sau khi hệ thống trở lại.

DR là một phần của BC. Mục tiêu phục hồi kỹ thuật cần phù hợp với cách doanh nghiệp duy trì dịch vụ trong thời gian gián đoạn.

### 2.5. So sánh

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| HA | Làm sao tiếp tục phục vụ khi một thành phần lỗi? | Multi-AZ, health check, autoscaling |
| Backup | Có thể lấy lại dữ liệu cũ không? | AWS Backup, PITR, S3 Versioning |
| DR | Làm sao khôi phục dịch vụ sau sự cố lớn? | Restore sang Region dự phòng và chuyển traffic |
| BC | Doanh nghiệp tiếp tục phục vụ ra sao trong thời gian gián đoạn? | Quy trình ghi nhận đơn offline |

## 3. Hiểu và đặt RTO, RPO

### 3.1. Recovery Time Objective

RTO là khoảng thời gian mục tiêu tối đa để khôi phục một dịch vụ hoặc quy trình về mức hoạt động được chấp nhận sau sự cố. RTO cần nêu rõ:

- Thời điểm bắt đầu tính đồng hồ.
- Điều kiện được xem là dịch vụ đã phục hồi.
- Phạm vi chức năng cần hoạt động.
- Ai xác nhận khôi phục.

Một định nghĩa thực tế có thể tính từ lúc sự cố làm dịch vụ mất khả năng đáp ứng đến khi luồng nghiệp vụ quan trọng hoạt động và được người chịu trách nhiệm xác nhận. Nếu tổ chức chỉ tính từ lúc incident được tuyên bố, cần ghi rõ vì thời gian phát hiện và quyết định sẽ không nằm trong số đo đó.

RTO không chỉ là thời gian chạy lệnh restore. Nó có thể gồm:

1. Phát hiện và xác nhận sự cố.
2. Đánh giá phạm vi ảnh hưởng.
3. Quyết định kích hoạt DR.
4. Cô lập hoặc fencing hệ thống lỗi.
5. Khôi phục dữ liệu và hạ tầng.
6. Cấu hình endpoint, identity và network.
7. Chuyển traffic.
8. Chạy smoke test và business validation.
9. Mở lại dịch vụ và theo dõi ổn định.

### 3.2. Recovery Point Objective

RPO là mức mất dữ liệu tối đa mà doanh nghiệp chấp nhận, thường biểu diễn bằng thời gian. Nếu sự cố xảy ra lúc 10:00 và điểm dữ liệu mới nhất có thể phục hồi là 09:52, khoảng mất dữ liệu tiềm năng là 8 phút.

RPO phụ thuộc cơ chế backup hoặc replication:

- Backup hàng giờ có thể tạo khoảng mất dữ liệu gần một giờ nếu không có log/replication bổ sung.
- Point-in-time recovery có thể khôi phục tới một thời điểm trong cửa sổ hỗ trợ của dịch vụ.
- Replication bất đồng bộ có độ trễ và có thể mất các thay đổi chưa kịp replicate.
- Replication đồng bộ có trade-off về latency, availability và phạm vi lỗi.

Không suy ra RPO bằng lịch backup danh nghĩa. Cần đo timestamp của điểm dữ liệu gần nhất thực sự khôi phục được trong diễn tập.

### 3.3. MTD và MAO

Maximum Tolerable Downtime (MTD), đôi khi được gọi Maximum Acceptable Outage (MAO), là thời gian gián đoạn tối đa mà doanh nghiệp có thể chịu trước khi hậu quả trở nên không chấp nhận được.

RTO phải nhỏ hơn MTD và cần chừa thời gian cho Work Recovery Time (WRT) nếu doanh nghiệp cần đối soát, xử lý backlog hoặc khôi phục các tác vụ thủ công sau khi hệ thống đã online.

~~~text
Sự cố bắt đầu
    |
    +-- Phát hiện / quyết định / phục hồi kỹ thuật --> Dịch vụ hoạt động (RTO)
    |
    +-- Đối soát / xử lý backlog / hoàn tất công việc --> Hoạt động ổn định
    |
    +-----------------------------------------------> MTD/MAO
~~~

### 3.4. Công thức đo

RTO thực tế:

\[
RTO_{actual} = T_{service\_restored} - T_{disruption}
\]

RPO thực tế:

\[
RPO_{actual} = T_{disruption} - T_{latest\_recoverable\_data}
\]

Đây là cách đo đơn giản cho một sự cố tại một thời điểm. Với hệ thống có nhiều dataset hoặc workload, cần đo riêng từng nhóm dữ liệu và quy trình. RPO thực tế nên dựa trên timestamp hoặc sequence đã xác minh, không chỉ dựa vào thời điểm backup job báo thành công.

### 3.5. Ví dụ

Giả sử:

- Sự cố bắt đầu lúc 10:00.
- Hệ thống được xác nhận hoạt động lúc 11:25.
- Điểm dữ liệu cuối cùng khôi phục được là 09:48.
- Mục tiêu RTO là 2 giờ.
- Mục tiêu RPO là 15 phút.

Khi đó:

\[
RTO_{actual} = 11{:}25 - 10{:}00 = 85\ phút
\]

\[
RPO_{actual} = 10{:}00 - 09{:}48 = 12\ phút
\]

Trong ví dụ, cả hai mục tiêu đều đạt. Kết luận chỉ hợp lệ nếu “dịch vụ hoạt động” và “dữ liệu khôi phục được” đã được xác minh bằng tiêu chí thống nhất.

### 3.6. Đặt mục tiêu theo business impact

Không phải mọi chức năng cần cùng RTO/RPO. Ví dụ:

| Workload | RTO mục tiêu | RPO mục tiêu | Lý do |
|---|---:|---:|---|
| Order creation | 2 giờ | 15 phút | Giao dịch quan trọng |
| Product catalog | 4 giờ | 1 giờ | Có thể tái tạo một phần từ nguồn khác |
| Analytics dashboard | 24 giờ | 24 giờ | Không ảnh hưởng trực tiếp xử lý đơn |
| Audit records | 8 giờ | 5 phút | Cần bảo toàn lịch sử |

Đây chỉ là mục tiêu minh họa. Business Impact Analysis (BIA) cần xác nhận hậu quả tài chính, vận hành, pháp lý và khách hàng trước khi chốt.

## 4. Business Impact Analysis và recovery tiers

### 4.1. Thực hiện BIA

BIA xác định quy trình kinh doanh, mức độ quan trọng, tác động theo thời gian và dependency. Với từng quy trình, thu thập:

- Chủ sở hữu quy trình.
- Thời gian hoạt động quan trọng.
- Số lượng người dùng/giao dịch.
- Tác động khi gián đoạn 15 phút, 1 giờ, 4 giờ, 1 ngày.
- Mức dữ liệu có thể mất.
- Dependency nội bộ và bên ngoài.
- Workaround thủ công.
- RTO/RPO và MTD/MAO được phê duyệt.

Đừng đặt RTO chỉ dựa trên khả năng kỹ thuật. Một database có thể restore trong 30 phút nhưng quy trình đối soát sau restore có thể cần thêm 90 phút.

### 4.2. Phân loại workload

Có thể chia recovery tier:

| Tier | Mức độ quan trọng | Chiến lược tham khảo |
|---|---|---|
| Tier 0 | An toàn, identity hoặc control plane thiết yếu | Dự phòng và kiểm soát truy cập rất chặt |
| Tier 1 | Giao dịch kinh doanh trọng yếu | Warm standby hoặc pilot light nâng cao |
| Tier 2 | Ứng dụng hỗ trợ hoạt động | Pilot light hoặc backup/restore nhanh |
| Tier 3 | Báo cáo, batch có thể chạy lại | Backup/restore hoặc tái tạo |

Tên tier và strategy phải do tổ chức định nghĩa. Một workload có thể có nhiều tier dữ liệu: order record cần RPO thấp, còn cache có thể tái tạo.

### 4.3. Dependency mapping

Vẽ dependency cho mỗi workload:

- DNS và certificate.
- Identity provider và IAM.
- KMS key và secret.
- Compute image, package và container registry.
- Network, subnet, route, security group và endpoint.
- Database, object storage, queue, event bus.
- Third-party API.
- Monitoring, alerting và incident communication.

Nếu quên một dependency, hệ thống có thể khôi phục database nhưng không thể đăng nhập, giải mã dữ liệu hoặc gọi dịch vụ bên ngoài.

### 4.4. Recovery order

Thứ tự khôi phục thường theo dependency:

1. Account baseline, IAM, KMS và quyền truy cập.
2. Network, DNS và security boundary.
3. Storage và database.
4. Messaging và integration.
5. Compute và application services.
6. Monitoring, alerting và user traffic.
7. Batch/backlog và quy trình đối soát.

Thứ tự thực tế tùy kiến trúc. Một số dịch vụ managed có thể được tạo song song; runbook phải thể hiện dependency thật thay vì áp dụng một thứ tự máy móc.

## 5. Chọn chiến lược DR

### 5.1. Backup and Restore

Backup and Restore giữ backup ở vị trí an toàn và tạo lại hạ tầng khi có sự cố.

Ưu điểm:

- Chi phí dự phòng thường thấp hơn.
- Kiến trúc đơn giản hơn active standby.
- Phù hợp workload có RTO dài hơn.

Trade-off:

- Thời gian restore và deploy có thể dài.
- Cần automation và kiểm thử thường xuyên.
- Có thể phải chờ capacity, quota và dependency.

Phù hợp với workload không yêu cầu phục hồi trong vài phút và có dữ liệu backup đáng tin cậy.

### 5.2. Pilot Light

Pilot Light duy trì một phần nền tảng tối thiểu ở Region dự phòng, thường gồm dữ liệu được replicate hoặc backup, một số thành phần nền tảng và automation. Khi có sự cố, nhóm mở rộng compute, triển khai phần còn lại và chuyển traffic.

Ưu điểm:

- Chi phí thấp hơn warm standby nếu phần lớn compute chưa chạy.
- Một số dependency và data path đã sẵn sàng.
- Có thể rút ngắn thời gian so với dựng mọi thứ từ đầu.

Trade-off:

- Vẫn cần thời gian scale và deploy.
- Phải kiểm tra quota và capacity.
- Runbook phức tạp hơn backup/restore đơn giản.

### 5.3. Warm Standby

Warm Standby duy trì môi trường dự phòng hoạt động ở công suất thấp nhưng có thể phục vụ một phần traffic hoặc được scale nhanh khi cần.

Ưu điểm:

- Hạ tầng và dependency đã được triển khai.
- Có thể kiểm tra health liên tục.
- RTO thường ngắn hơn pilot light.

Trade-off:

- Chi phí compute/database/network chạy liên tục.
- Cần đồng bộ dữ liệu và cấu hình.
- Phải quản lý phiên bản giữa primary và standby.

### 5.4. Multi-Site Active/Active

Multi-Site Active/Active cho phép nhiều Region cùng phục vụ traffic. Có thể đạt RTO rất thấp đối với một số thành phần nhưng đòi hỏi thiết kế phân phối traffic, dữ liệu, consistency và conflict resolution.

Trade-off:

- Chi phí cao nhất hoặc gần cao nhất.
- Vận hành phức tạp.
- Có nguy cơ split-brain và ghi xung đột.
- Cần kiểm thử failure mode và failback kỹ lưỡng.

Không nên chọn active/active nếu ứng dụng chưa có mô hình dữ liệu và nghiệp vụ hỗ trợ ghi đa Region.

### 5.5. So sánh

| Strategy | Hạ tầng dự phòng | RTO tương đối | RPO tương đối | Chi phí tương đối |
|---|---|---|---|---|
| Backup and Restore | Chủ yếu là backup/artifact | Dài hơn | Theo backup/replication | Thấp |
| Pilot Light | Một phần nền tảng và dữ liệu | Trung bình | Theo replication/backup | Thấp đến trung bình |
| Warm Standby | Môi trường chạy ở công suất thấp | Ngắn hơn | Theo replication | Trung bình đến cao |
| Active/Active | Nhiều Region đang phục vụ | Có thể rất ngắn | Phụ thuộc consistency/replication | Cao |

Các mức chỉ mang tính tương đối. RTO/RPO thực tế phụ thuộc service, kích thước dữ liệu, workload, automation, quota và quy trình con người; không được suy ra chỉ từ tên strategy.

### 5.6. Chọn strategy theo RTO/RPO

Quy trình chọn:

1. Xác định MTD và mức gián đoạn chấp nhận.
2. Đặt RTO/RPO cho từng workload/dataset.
3. Liệt kê các strategy khả thi.
4. Đo thời gian restore/replication trong thử nghiệm.
5. Tính chi phí standby và vận hành.
6. Chọn phương án đáp ứng mục tiêu với trade-off chấp nhận được.
7. Phê duyệt bởi business, security, operations và finance.

Nếu strategy không đáp ứng mục tiêu, phải thay đổi kiến trúc, mục tiêu kinh doanh hoặc ngân sách. Không được ghi một RTO thấp trong tài liệu nếu chưa có bằng chứng.

## 6. Dịch vụ AWS cho backup và phục hồi

### 6.1. AWS Backup

AWS Backup tập trung quản lý backup cho các dịch vụ AWS được hỗ trợ. Có thể định nghĩa backup plan, schedule, lifecycle, retention, vault và copy action.

Khả năng quan trọng:

- Backup theo lịch hoặc policy.
- Quản lý backup vault.
- Copy backup giữa Region hoặc account khi resource/Region hỗ trợ.
- Vault Lock để bảo vệ backup theo cấu hình compliance/governance.
- Audit và báo cáo backup.
- Restore testing cho resource và loại backup được hỗ trợ.

Không phải mọi resource đều có cùng khả năng backup/copy/restore. Kiểm tra service support matrix và Region availability trước khi cam kết.

### 6.2. Backup Vault và Vault Lock

Backup vault là nơi lưu recovery point. Dùng encryption, access policy và phân tách quyền để hạn chế ai có thể xóa hoặc thay đổi backup.

AWS Backup Vault Lock có chế độ governance/compliance với quy tắc retention và bảo vệ xóa theo cấu hình. Cấu hình compliance mode có thể tạo ràng buộc không thể đảo ngược trong thời hạn đã đặt; phải review kỹ retention và quy trình trước khi bật.

Đối với rủi ro ransomware hoặc compromise account, cân nhắc backup account riêng, cross-account copy, organization controls và quyền quản trị độc lập.

### 6.3. Amazon S3

Các tính năng hỗ trợ bảo vệ và phục hồi object:

- Versioning giữ nhiều version của object.
- Lifecycle chuyển version cũ sang storage class phù hợp.
- Replication giữa bucket/Region theo rule.
- Object Lock hỗ trợ retention và legal hold theo cấu hình.
- AWS Backup hỗ trợ các trường hợp S3 backup được công bố.
- Cross-Region Replication (CRR) hỗ trợ bản sao object sang Region khác.

Replication không đồng nghĩa backup bất biến. Nếu object bị xóa hoặc bị ghi dữ liệu sai, hành vi replication và delete marker phụ thuộc cấu hình. Cần versioning, Object Lock hoặc backup độc lập theo yêu cầu.

CRR là bất đồng bộ; replication lag ảnh hưởng RPO. S3 Replication Time Control có thể hỗ trợ SLA replication cho phần trăm object theo điều kiện dịch vụ, nhưng không biến replication thành đồng bộ tuyệt đối.

### 6.4. Amazon DynamoDB

DynamoDB cung cấp:

- Point-in-time recovery (PITR) trong cửa sổ retention do dịch vụ hỗ trợ.
- On-demand backup.
- AWS Backup integration cho trường hợp được hỗ trợ.
- Global Tables để replicate table qua nhiều Region.

Restore từ PITR hoặc backup tạo table mới; ứng dụng cần chuyển sang table được restore, kiểm tra index, stream, autoscaling, TTL, encryption và quyền truy cập. Không giả định restore sẽ ghi đè table hiện có.

Global Tables hỗ trợ multi-Region replication theo mô hình được cấu hình. Replication bất đồng bộ có thể có độ trễ; cần thiết kế conflict handling và xác định cách chuyển traffic. Global Tables không thay thế backup vì xóa nhầm hoặc dữ liệu sai có thể replicate sang Region khác.

### 6.5. Amazon RDS và Aurora

Các cơ chế khác nhau:

- Automated backups và point-in-time recovery cho các engine/configuration được hỗ trợ.
- Manual snapshots để giữ mốc cụ thể.
- Cross-Region snapshot copy hoặc automated backup replication theo engine/Region hỗ trợ.
- Multi-AZ để tăng availability trong Region.
- Read replica hoặc Aurora Global Database cho một số nhu cầu replication/DR.

RDS Multi-AZ chủ yếu là HA/failover trong Region, không phải phương án DR toàn Region. Read replica và Aurora Global Database có replication semantics, lag và quy trình promotion riêng. Cần kiểm thử promotion, endpoint, application reconnect và consistency.

### 6.6. EBS, EFS và EC2

- EBS snapshots hỗ trợ backup volume; snapshot thường incremental sau snapshot đầu tiên. Cần xác định application-consistent backup nếu workload cần đồng bộ nhiều volume hoặc database.
- AMI có thể lưu image cấu hình EC2 để triển khai instance mới.
- EFS backup có thể được quản lý qua AWS Backup theo khả năng dịch vụ.
- AWS Elastic Disaster Recovery (AWS DRS) hỗ trợ replication và recovery cho server/workload được hỗ trợ, phù hợp một số kịch bản lift-and-shift.

Snapshot đơn lẻ không bảo đảm ứng dụng nhất quán. Với database hoặc hệ thống nhiều volume, cần freeze/quiesce, native backup hoặc cơ chế application-consistent phù hợp.

### 6.7. Compute và artifact

Để dựng lại compute:

- Lưu source và IaC trong repository có backup/access control.
- Lưu container image trong ECR và cân nhắc replication sang Region dự phòng.
- Lưu Lambda deployment package hoặc build artifact ở nơi có thể truy cập khi Region chính lỗi.
- Quản lý AMI và launch template.
- Ghi rõ runtime, version, environment variables và dependency.
- Kiểm tra service quota và capacity ở Region dự phòng.

Một Region dự phòng không sẵn sàng nếu chỉ có database replica mà thiếu image, package, configuration hoặc quyền deploy.

### 6.8. AWS Elastic Disaster Recovery

AWS DRS hỗ trợ khôi phục server/workload từ hạ tầng nguồn được hỗ trợ sang AWS bằng continuous block-level replication và recovery launch configuration. DRS phù hợp cho một số hệ thống server-based, migration hoặc DR; không thay thế thiết kế native backup cho mọi managed service.

Trong diễn tập, kiểm tra staging area, replication health, launch template, network mapping, boot order, licensing và ứng dụng sau khi recovery instance khởi động.

## 7. Thiết kế DR cho Region dự phòng

### 7.1. Chọn primary và recovery Region

Đánh giá:

- Data residency và pháp lý.
- Dịch vụ có sẵn ở cả hai Region.
- Khoảng cách và replication latency.
- Giá compute, storage và data transfer.
- Quota/capacity.
- Kết nối tới user và hệ thống ngoài AWS.
- Đội vận hành có quyền truy cập và kinh nghiệm với Region dự phòng.

Không chọn Region dự phòng chỉ vì giá thấp nếu dịch vụ hoặc kết nối cần thiết không có.

### 7.2. Chuẩn bị account và baseline

Region dự phòng cần có hoặc có thể tạo lại:

- IAM roles, trust policies và permission boundaries.
- KMS keys và key policies.
- VPC, subnet, route, security group và endpoints.
- DNS zone/record hoặc traffic management.
- Secrets và certificates.
- ECR images, Lambda artifacts và AMI.
- Database/table/bucket recovery point.
- Queue, event bus và workflow definitions.
- Monitoring, alarm, dashboard và notification.

Dùng IaC để tạo cấu hình có thể tái lập. Tuy nhiên, IaC template không tự đảm bảo secret hoặc dữ liệu đã được replicate; cần kiểm tra riêng.

### 7.3. KMS và secrets

Dữ liệu backup có thể được mã hóa bằng KMS key. Khi copy backup sang Region khác, cần bảo đảm recovery Region có key phù hợp và quyền decrypt. KMS key là tài nguyên theo Region; không thể coi key ở primary Region tự động tồn tại ở secondary Region.

Secrets Manager hỗ trợ một số khả năng replicate secret sang Region khác. Xác minh secret version, replica status, KMS key và role access. Parameter Store parameters có thể cần được triển khai/copy bằng automation tùy kiến trúc.

### 7.4. DNS và traffic routing

Có thể dùng:

- Amazon Route 53 failover routing và health checks.
- AWS Global Accelerator để điều phối traffic tới endpoint phù hợp.
- CloudFront origin failover cho một số mô hình origin.
- Load balancer hoặc API endpoint ở recovery Region.

DNS failover chịu ảnh hưởng TTL và DNS/client caching; thay đổi record không đồng nghĩa mọi client chuyển ngay. Global Accelerator cung cấp điểm vào anycast và điều phối endpoint theo health/traffic dial, nhưng endpoint và health check vẫn cần cấu hình đúng.

Kiểm thử client reconnect, connection pool, TLS certificate, CORS, authentication callback và webhook endpoint sau khi chuyển traffic.

### 7.5. Tránh split-brain

Split-brain xảy ra khi primary và recovery Region cùng tin rằng mình là nơi ghi dữ liệu chính. Có thể dẫn tới xung đột, ghi đè hoặc hai luồng nghiệp vụ cùng chạy.

Trước khi promote:

- Xác định primary đã dừng hoặc bị cô lập.
- Ngăn workload cũ nhận write nếu có thể.
- Dùng fencing/leader control hoặc routing control.
- Xác minh replication state và điểm dữ liệu.
- Chỉ mở write ở Region mới sau khi người có thẩm quyền chấp thuận.

Với multi-active, phải có mô hình conflict resolution rõ ràng và kiểm thử trường hợp hai Region cùng ghi.

## 8. Kiến trúc DR mẫu cho Order Platform

### 8.1. Bối cảnh

Một nền tảng quản lý đơn hàng chạy ở primary Region. Thành phần chính:

- CloudFront và API Gateway.
- Lambda xử lý order.
- DynamoDB lưu order và outbox.
- EventBridge và SQS xử lý fulfillment.
- S3 lưu invoice và attachment.
- Cognito hoặc identity provider.
- Secrets Manager lưu credential của payment provider.
- CloudWatch, X-Ray và CloudTrail.

Mục tiêu minh họa:

- RTO: 2 giờ.
- RPO cho order: 15 phút.
- RPO cho catalog: 1 giờ.
- RTO cho analytics: 24 giờ.

### 8.2. Strategy đề xuất

Chọn Pilot Light hoặc Warm Standby tùy ngân sách và kết quả restore test:

- IaC, IAM baseline, VPC, KMS và monitoring có thể triển khai sẵn ở recovery Region.
- DynamoDB Global Tables hoặc backup/PITR được chọn theo consistency và RPO.
- S3 CRR hoặc backup strategy cho invoice/attachment.
- ECR image và Lambda artifact được lưu/copy.
- SQS/EventBridge resources được tạo sẵn hoặc triển khai bằng IaC.
- Secrets Manager replica và KMS key được chuẩn bị.
- Compute có thể chạy ở công suất thấp hoặc scale khi DR được kích hoạt.
- Route 53/Global Accelerator được cấu hình cho traffic shift.

Không mặc định tất cả thành phần cần active-active. Order write cần một Region authoritative tại mỗi thời điểm nếu business logic không hỗ trợ conflict resolution đa Region.

### 8.3. Sơ đồ tham khảo

~~~mermaid
flowchart TB
    U[Customers] --> ROUTE[Route 53 / Global Accelerator]
    ROUTE --> PRIMARY
    ROUTE -. failover .-> RECOVERY
    subgraph PRIMARY["Primary Region"]
        PAPI[API Gateway]
        PL[Order Lambda]
        PD[(DynamoDB primary)]
        PS3[(S3 primary)]
        PQ[SQS / EventBridge]
        PAPI --> PL
        PL --> PD
        PL --> PS3
        PL --> PQ
    end
    subgraph RECOVERY["Recovery Region"]
        RAPI[API Gateway]
        RL[Order Lambda standby]
        RD[(DynamoDB recovery)]
        RS3[(S3 recovery)]
        RQ[SQS / EventBridge]
        RAPI --> RL
        RL --> RD
        RL --> RS3
        RL --> RQ
    end
    PD -. replication / backup .-> RD
    PS3 -. CRR / backup .-> RS3
    ART[Code / IaC / ECR artifacts] --> PRIMARY
    ART --> RECOVERY
    OBS[Central monitoring and audit] --- PRIMARY
    OBS --- RECOVERY
~~~

Sơ đồ là logic view. Cần xác định rõ loại replication, độ trễ, cách promote, account boundary, key, secret, queue và traffic routing trong deployment design.

### 8.4. Data consistency

Order record và outbox event phải có quy tắc nhất quán. Nếu order được replicate nhưng event chưa phát hoặc ngược lại, recovery có thể tạo trạng thái không đồng nhất.

Thiết kế cần:

- Transaction boundary cho order và outbox.
- Event ID duy nhất.
- Consumer idempotency.
- Reconciliation job để tìm record thiếu event.
- Quy tắc xử lý event đã gửi nhưng chưa được consumer xác nhận.
- Đối soát với payment provider sau failover.

Không chỉ kiểm tra số lượng record. Cần kiểm tra quan hệ giữa order, payment, fulfillment và event.

## 9. Runbook kích hoạt DR

### 9.1. Vai trò và trách nhiệm

| Vai trò | Trách nhiệm |
|---|---|
| Incident Commander | Điều phối, xác nhận mức độ và quyết định escalation |
| DR Lead | Điều phối các bước kỹ thuật và recovery order |
| Database Lead | Kiểm tra replication/backup, restore và data validation |
| Platform/Network Lead | IAM, KMS, VPC, DNS và traffic routing |
| Application Lead | Deploy, config, smoke test và business validation |
| Security Lead | Kiểm tra compromise, access và audit evidence |
| Business Owner | Chấp nhận mức dữ liệu và dịch vụ phục hồi |
| Communications Lead | Cập nhật stakeholder và người dùng |

Trong đội nhỏ, một người có thể kiêm nhiều vai trò nhưng trách nhiệm phê duyệt và thực hiện cần được ghi rõ.

### 9.2. Điều kiện kích hoạt

Runbook phải định nghĩa:

- Sự cố nào đủ nghiêm trọng để kích hoạt DR?
- Ai có quyền tuyên bố disaster?
- Bao lâu cần ra quyết định?
- Bằng chứng nào cho thấy primary Region không thể phục hồi trong RTO?
- Khi nào tiếp tục chờ primary sẽ gây rủi ro lớn hơn failover?
- Ai phê duyệt chuyển sang recovery Region?

Không kích hoạt Region failover chỉ vì một alarm đơn lẻ. Kiểm tra phạm vi sự cố, AWS Health, network, application và khả năng khôi phục trong Region hiện tại.

### 9.3. Các giai đoạn runbook

**Giai đoạn A – Declare**

1. Mở incident và ghi timestamp UTC.
2. Xác nhận account, Region và service bị ảnh hưởng.
3. Tập hợp Incident Commander và technical leads.
4. Đánh giá RTO/RPO còn lại.
5. Quyết định activate DR và ghi người phê duyệt.

**Giai đoạn B – Contain**

1. Cô lập credential hoặc workload bị compromise nếu cần.
2. Ngăn primary tiếp tục nhận write ngoài kiểm soát.
3. Kiểm tra split-brain và background worker.
4. Giữ lại log/audit evidence.
5. Xác nhận điểm dữ liệu cuối có thể tin cậy.

**Giai đoạn C – Recover infrastructure**

1. Kiểm tra recovery account/Region và service quota.
2. Triển khai IaC hoặc mở rộng Pilot Light.
3. Xác minh VPC, subnet, route, security group và endpoints.
4. Kiểm tra IAM, KMS, secret và certificate.
5. Deploy compute artifact đúng version.
6. Tạo hoặc xác minh queue, event bus, workflow và alarm.

**Giai đoạn D – Recover data**

1. Chọn recovery point được phê duyệt.
2. Restore hoặc promote database theo runbook.
3. Kiểm tra S3 object/version và replication status.
4. Xác minh encryption key và quyền đọc.
5. Chạy data integrity checks.
6. Ghi timestamp/sequence mới nhất có thể khôi phục.
7. Ngăn ứng dụng mới ghi trước khi data validation pass.

**Giai đoạn E – Switch traffic**

1. Xác minh recovery endpoint và health check.
2. Xác nhận primary đã được fence hoặc không còn ghi.
3. Chuyển DNS/traffic routing theo phương án.
4. Kiểm tra TLS, authentication và client reconnect.
5. Chạy smoke test từ mạng và danh tính đại diện.
6. Mở traffic theo từng bước nếu có thể.

**Giai đoạn F – Validate and stabilize**

1. Tạo và đọc một giao dịch kiểm thử an toàn.
2. Xác minh order/payment/event consistency.
3. Theo dõi error rate, latency, queue age và business metric.
4. Xử lý backlog có giới hạn và deduplication.
5. Xác nhận với business owner.
6. Ghi timestamp dịch vụ được xem là phục hồi.

### 9.4. Stop conditions

Tạm dừng hoặc không mở traffic nếu:

- Recovery point không xác định được hoặc vượt RPO mà chưa có chấp thuận.
- KMS key hoặc secret không khả dụng.
- Có nguy cơ hai Region cùng ghi.
- Data integrity check thất bại.
- Security compromise chưa được cô lập.
- Recovery Region thiếu quota/capacity cho workload tối thiểu.
- Health check hoặc smoke test không đạt.

Stop condition giúp ngăn việc chuyển traffic sang một hệ thống online nhưng không an toàn hoặc dữ liệu sai.

### 9.5. Failback

Failback là chuyển workload từ recovery Region trở lại primary hoặc một môi trường đích mới. Không nhất thiết phải failback ngay khi primary Region hoạt động lại.

Quy trình:

1. Xác minh nguyên nhân sự cố primary đã được khắc phục.
2. Chọn thời điểm và thông báo stakeholder.
3. Xác định hướng đồng bộ dữ liệu từ recovery về primary.
4. Kiểm tra schema/version compatibility.
5. Tạm dừng hoặc điều phối write để tránh split-brain.
6. Replicate và đối soát dữ liệu.
7. Kiểm tra KMS, secret, endpoint và workload.
8. Chuyển traffic có kiểm soát.
9. Xác minh business flow và metric.
10. Giữ recovery environment theo thời gian quan sát trước khi scale down.

Failback cũng cần đo thời gian và mức mất dữ liệu. Không xóa recovery environment ngay sau khi traffic đổi.

## 10. Thiết kế DR test và tabletop exercise

### 10.1. Vì sao phải diễn tập?

Tài liệu có thể lỗi thời; người trực có thể không có quyền; quota có thể thay đổi; endpoint và secret có thể không còn hợp lệ; thời gian restore thực tế có thể dài hơn dự kiến. Diễn tập giúp phát hiện những khoảng trống này trước khi xảy ra sự cố thật.

### 10.2. Các mức diễn tập

| Mức | Mô tả | Mục tiêu |
|---|---|---|
| Tabletop | Thảo luận kịch bản trên giấy | Kiểm tra quyết định, owner và runbook |
| Walkthrough | Đi qua từng bước, kiểm tra lệnh/quyền | Phát hiện thiếu thông tin và dependency |
| Component restore | Restore một resource hoặc dataset | Đo restore time và kiểm tra dữ liệu |
| Technical failover | Chuyển một workload test sang recovery Region | Kiểm tra automation và traffic |
| Full DR exercise | Diễn tập nhiều thành phần và business validation | Đo RTO/RPO end-to-end |
| Failback exercise | Chuyển trở lại hoặc sang Region đích mới | Xác minh vòng đời DR hoàn chỉnh |

Nên bắt đầu bằng tabletop và component restore, sau đó tăng mức độ khi automation và guardrail đã sẵn sàng.

### 10.3. Kịch bản diễn tập

Ví dụ các kịch bản:

- Mất toàn bộ primary Region.
- Database bị xóa hoặc corruption.
- IAM role hoặc KMS key không còn khả dụng.
- Ransomware hoặc compromise tài khoản.
- S3 object bị ghi đè/xóa nhầm.
- Queue consumer dừng và backlog tích lũy.
- Payment provider ngừng hoạt động.
- Một Availability Zone mất kết nối.
- Deployment mới làm hỏng dữ liệu.

Mỗi kịch bản phải có phạm vi, mục tiêu, điều kiện bắt đầu, stop condition và cách reset môi trường.

### 10.4. Chuẩn bị diễn tập

Trước buổi diễn tập:

1. Chọn workload và RTO/RPO đã được phê duyệt.
2. Xác định môi trường test và dữ liệu synthetic.
3. Chọn người điều phối và observer.
4. Kiểm tra quyền IAM và break-glass access.
5. Xác minh backup/replication health.
6. Kiểm tra quota, KMS, secrets, DNS và artifact.
7. Chốt blast radius và stop condition.
8. Chuẩn bị dashboard, log query và biểu mẫu ghi timestamp.
9. Thông báo người liên quan.
10. Tạo baseline trước khi bắt đầu.

### 10.5. Tabletop prompts

Điều phối viên có thể hỏi:

- Ai phát hiện và ai tuyên bố disaster?
- Bằng chứng nào cho thấy primary không thể phục hồi trong RTO?
- Recovery point nào được chọn và ai chấp thuận?
- Làm sao biết primary đã bị fence?
- Nếu KMS key không truy cập được thì làm gì?
- Nếu recovery Region hết quota thì phương án là gì?
- Ai xác minh order/payment consistency?
- Nếu DNS client cache lâu hơn dự kiến thì sao?
- Khi nào được mở traffic?
- Ai quyết định failback?

Ghi nhận câu trả lời không rõ, phụ thuộc một cá nhân hoặc cần truy cập tài liệu chưa tồn tại thành action item.

## 11. Đo và xác minh RTO/RPO

### 11.1. Timestamp bắt buộc

Ghi các mốc UTC:

| Mốc | Ý nghĩa |
|---|---|
| T0 | Sự cố bắt đầu hoặc thời điểm disruption được xác định |
| T1 | Hệ thống phát hiện sự cố |
| T2 | Incident được xác nhận |
| T3 | DR được tuyên bố |
| T4 | Recovery bắt đầu |
| T5 | Data restore/replication promotion hoàn tất |
| T6 | Application health check pass |
| T7 | Traffic chuyển sang recovery |
| T8 | Business validation pass |
| T9 | Dịch vụ được tuyên bố phục hồi |

RTO có thể được đo T9 − T0 hoặc theo mốc đã được tổ chức định nghĩa. Nếu chỉ đo T9 − T3, ghi rõ đó là recovery execution time, không phải end-to-end RTO.

### 11.2. Xác minh RPO bằng dữ liệu

Không chỉ xem thời điểm backup. Hãy dùng dữ liệu có sequence hoặc timestamp:

- Ghi test event theo sequence tăng dần.
- Lưu checkpoint ở nguồn độc lập nếu có thể.
- Ghi timestamp commit cuối cùng trước disruption.
- Restore/promote dữ liệu.
- Tìm sequence cuối cùng có mặt và kiểm tra tính nhất quán.
- Đối chiếu với event log hoặc nguồn nghiệp vụ độc lập.

Với hệ thống giao dịch, cần kiểm tra cả record và side effect. Một order record có thể tồn tại nhưng payment event hoặc fulfillment event bị thiếu.

### 11.3. Phân biệt replication lag và data loss

Replication lag là độ trễ giữa nguồn và bản sao tại một thời điểm. Khi sự cố xảy ra, phần chưa replicate có thể trở thành data loss nếu không thể lấy lại từ nguồn.

Đo lag trước và trong diễn tập:

- Replication timestamp.
- Sequence hoặc checkpoint.
- Số object/record pending.
- Thời gian xử lý backlog.

Không dùng một metric lag trung bình để kết luận mọi record đã được replicate.

### 11.4. Định nghĩa service restored

Một endpoint trả HTTP 200 chưa đủ để xác nhận dịch vụ phục hồi. Tiêu chí có thể gồm:

- User authentication thành công.
- Tạo/đọc giao dịch test thành công.
- Database read/write đúng.
- Event được publish và consumer xử lý.
- Dữ liệu không bị duplicate hoặc mất liên kết.
- Dashboard và alarm hoạt động.
- Error rate và latency nằm trong ngưỡng.
- Business owner xác nhận chức năng quan trọng.

### 11.5. Bảng đo kết quả

| Chỉ số | Mục tiêu | Kết quả diễn tập | Đạt? |
|---|---:|---:|---|
| Detection time | 5 phút | 3 phút | Có |
| Decision time | 10 phút | 12 phút | Không |
| End-to-end RTO | 120 phút | 95 phút | Có |
| RPO – orders | 15 phút | 11 phút | Có |
| RPO – attachments | 60 phút | 18 phút | Có |
| Backlog drain | 30 phút | 42 phút | Không |
| Business validation | 15 phút | 10 phút | Có |

Các số trong bảng chỉ là ví dụ minh họa. Kết quả thực tế phải lấy từ timestamp và data reconciliation trong diễn tập.

## 12. Kiểm thử backup và restore theo dịch vụ

### 12.1. AWS Backup restore test

Một bài test:

1. Xác định recovery point và resource được hỗ trợ.
2. Kiểm tra backup job status và vault.
3. Khôi phục vào resource có tên riêng trong test account/Region.
4. Xác minh KMS key và quyền decrypt.
5. Kiểm tra cấu hình resource sau restore.
6. Chạy application-level validation.
7. Ghi restore duration và data point.
8. Xóa resource test theo quy trình.

AWS Backup restore testing có thể tự động hóa một số bài restore cho resource được hỗ trợ. Cần xác nhận phạm vi service, cấu hình test và tiêu chí validation.

### 12.2. S3 restore

Kiểm tra:

- Khôi phục version trước khi object bị ghi đè.
- Khôi phục object đã xóa bằng version/delete marker phù hợp.
- Xác minh Object Lock/retention.
- Kiểm tra replication status và replication lag.
- Đọc object bằng role của ứng dụng.
- Kiểm tra metadata, checksum và encryption.

Một object có thể tồn tại nhưng ứng dụng không đọc được do KMS key hoặc bucket policy. Test cần dùng principal gần giống production.

### 12.3. DynamoDB restore

Quy trình:

1. Bật PITR hoặc tạo on-demand backup theo yêu cầu.
2. Ghi test records có sequence.
3. Chọn recovery timestamp.
4. Restore sang table mới.
5. Xác minh item, index, encryption và capacity mode.
6. Kiểm tra stream, TTL và ứng dụng phụ thuộc table.
7. Cập nhật alias/configuration hoặc deployment để dùng table mới.
8. Chạy read/write smoke test và đối soát.

Restore table không tự đảm bảo các consumer, stream ARN, alarms hoặc downstream integration được chuyển sang resource mới. Cần cập nhật và xác minh dependency.

### 12.4. RDS/Aurora restore

Kiểm tra:

- Snapshot hoặc point-in-time recovery.
- Restore time theo kích thước database.
- Engine version và parameter group.
- Subnet group/security group.
- KMS key và secret.
- Endpoint và connection pool.
- Schema migration và data consistency.
- Replication lag và promotion nếu dùng replica/global database.

Sau restore, chạy integrity query và nghiệp vụ test. Không chỉ kiểm tra instance ở trạng thái available.

### 12.5. EBS/EFS/EC2 restore

Kiểm tra:

- Snapshot có đúng volume và encryption key.
- Instance/AMI boot thành công.
- Device mapping và filesystem mount đúng.
- Application service tự khởi động.
- Dữ liệu nhiều volume nhất quán.
- DNS và security group đúng.

Nếu dùng AWS DRS, đo thời gian từ khi bắt đầu recovery launch đến khi ứng dụng được xác nhận sẵn sàng, không chỉ thời gian instance chuyển running.

## 13. Kiểm thử failover và failback

### 13.1. Failover checklist

- [ ] Primary và recovery Region đã được xác định.
- [ ] Backup/replication health được xác minh.
- [ ] Recovery point được business/technical owner chấp nhận.
- [ ] Primary write đã bị fence hoặc kiểm soát.
- [ ] KMS key, secret và certificate khả dụng.
- [ ] VPC, route, security group và endpoint đúng.
- [ ] Compute image/artifact đúng version.
- [ ] Database/table đã được restore/promote.
- [ ] Queue/event bus và consumer đã sẵn sàng.
- [ ] DNS/traffic routing được chuyển.
- [ ] Smoke test và business validation pass.
- [ ] RTO/RPO được ghi nhận.

### 13.2. Failback checklist

- [ ] Primary đã được xác nhận an toàn.
- [ ] Kế hoạch đồng bộ dữ liệu có hướng rõ ràng.
- [ ] Write được điều phối để tránh split-brain.
- [ ] Schema và version tương thích.
- [ ] Data reconciliation pass.
- [ ] Endpoint/secret/KMS đã sẵn sàng.
- [ ] Traffic chuyển từng bước.
- [ ] Business validation pass.
- [ ] Theo dõi ổn định sau chuyển.
- [ ] Recovery environment được giữ theo retention đã định.

### 13.3. Traffic shift

Khi dùng Route 53:

- Kiểm tra record type và routing policy.
- Health check phải đại diện đúng khả năng phục vụ.
- TTL và resolver/client caching phải được tính.
- Kiểm tra DNS từ nhiều network.
- Không giả định thay đổi record được mọi client nhận ngay.

Khi dùng Global Accelerator:

- Xác minh listener, endpoint group và health check.
- Kiểm tra traffic dial/endpoint weight.
- Đảm bảo endpoint ở Region dự phòng đã sẵn sàng.
- Kiểm tra client connection và TLS.

### 13.4. Xác minh sau failover

Kiểm tra:

- Authentication và authorization.
- Read/write nghiệp vụ.
- Event routing và consumer.
- Payment reconciliation.
- Object/file access.
- Error rate, latency, queue backlog.
- Alarm, dashboard, trace và audit.
- Data consistency và duplicate.

Chỉ mở toàn bộ traffic khi các kiểm tra trọng yếu pass và Incident Commander/business owner chấp thuận.

## 14. Bảo mật trong DR

### 14.1. Tách quyền backup và production

Workload production không nên có quyền tùy ý xóa backup hoặc sửa vault policy. Tách vai trò:

- Backup operator.
- Restore operator.
- Security/audit.
- Application deployment.
- Incident Commander.

Dùng cross-account backup hoặc backup vault account để giảm nguy cơ compromise một account làm mất cả dữ liệu chính lẫn backup.

### 14.2. Break-glass access

DR có thể cần quyền khẩn cấp. Thiết kế break-glass:

- Credential hoặc role được bảo vệ mạnh.
- MFA và approval theo chính sách.
- Thời hạn session ngắn.
- Alert khi sử dụng.
- Ghi CloudTrail.
- Review sau incident.
- Không chia sẻ access key trong runbook.

Diễn tập cần kiểm tra người được phân công có thể truy cập đúng role khi cần. Không lưu password hoặc secret trực tiếp trong tài liệu.

### 14.3. Ransomware và immutable backup

Kịch bản ransomware cần kiểm tra:

- Backup có bị xóa/mã hóa cùng workload không?
- Có bản copy account/Region khác không?
- Vault Lock/Object Lock có phù hợp không?
- KMS key có còn khả dụng và được bảo vệ không?
- Có thể xác định recovery point sạch trước khi malware xuất hiện không?
- Credential compromise đã được cô lập chưa?

Restore một backup mới nhất có thể khôi phục cả dữ liệu đã bị mã hóa. Cần chọn recovery point sạch và scan/validate trước khi mở traffic.

### 14.4. Audit evidence

Giữ:

- CloudTrail events.
- Backup job và restore job status.
- IAM role/session used.
- Change set và deployment ID.
- Recovery point identifier.
- Data validation report.
- Traffic switch timestamps.
- Approval và incident notes.

Evidence cần có quyền truy cập và retention phù hợp, tránh bị sửa/xóa bởi workload đang được phục hồi.

## 15. Giám sát DR readiness

### 15.1. Readiness metrics

Theo dõi định kỳ:

- Tuổi của recovery point gần nhất.
- Backup job success/failure.
- Cross-Region replication lag.
- Recovery Region resource health.
- Service quota headroom.
- Secret/certificate expiry.
- KMS key availability.
- ECR image replication status.
- IaC drift và deployment version.
- DNS/health check status.

### 15.2. AWS Resilience Hub

AWS Resilience Hub hỗ trợ đánh giá ứng dụng và resilience posture theo cấu hình, workload và policy được xác định. Nó có thể giúp phân tích resilience, RTO/RPO estimate hoặc recommendation cho một số kiến trúc được hỗ trợ.

Kết quả đánh giá không thay thế diễn tập restore/failover. RTO/RPO thực tế phải được đo bằng exercise vì còn phụ thuộc con người, dữ liệu, quota, dependency và quy trình.

### 15.3. AWS Fault Injection Service

AWS Fault Injection Service (FIS) cho phép chạy experiment có kiểm soát trên resource được hỗ trợ. Có thể dùng để mô phỏng một số failure mode như network disruption hoặc resource impairment.

Trước khi chạy:

- Xác định hypothesis.
- Giới hạn target và blast radius.
- Đặt stop condition/CloudWatch alarm.
- Kiểm tra quyền và thông báo.
- Chạy ở môi trường phù hợp.
- Có người giám sát và phương án dừng.

FIS không phải công cụ tự động kiểm chứng toàn bộ DR. Dùng nó để tạo failure signal có kiểm soát, sau đó kiểm tra ứng dụng và runbook phản ứng thế nào.

### 15.4. AWS Fault Injection Service và DR test

Ví dụ giả thuyết: “Khi một AZ mất kết nối, load balancer và compute ở AZ còn lại vẫn phục vụ trong SLO”. FIS có thể tạo một số điều kiện lỗi được hỗ trợ; CloudWatch/X-Ray xác minh tác động; đội vận hành kiểm tra alarm và runbook.

Không tạo sự cố toàn Region thật trong production chỉ để chứng minh DR. Dùng sandbox, staging hoặc controlled game day có phê duyệt và stop condition.

## 16. Đo lường kết quả và cải tiến

### 16.1. Exercise report

Báo cáo sau diễn tập nên có:

- Mục tiêu và kịch bản.
- Workload, Region và resource scope.
- RTO/RPO target.
- Timeline đầy đủ.
- RTO/RPO measured.
- Data loss/consistency findings.
- Steps failed hoặc manual intervention.
- Cost của exercise và recovery.
- Rủi ro còn lại.
- Owner và due date cho corrective actions.

### 16.2. Phân tích gap

Ví dụ:

| Gap | Tác động | Hành động |
|---|---|---|
| Restore table mất 70 phút | Chiếm phần lớn RTO | Tối ưu dữ liệu, test parallel recovery |
| Secret replica chưa sẵn sàng | App không khởi động | Tự động hóa secret replication/validation |
| Quota Lambda ở Region dự phòng thấp | Không đạt peak | Quota review và pre-provision |
| DNS cache lâu | Traffic chuyển chậm | Điều chỉnh TTL và test client behavior |
| DLQ không được replay | Workflow tồn đọng | Xây runbook replay và deduplication |
| Không có người phê duyệt ngoài giờ | Decision time vượt mục tiêu | On-call escalation và delegation |

### 16.3. Corrective action

Mỗi action item cần:

- Mô tả vấn đề.
- Bằng chứng.
- Mức ưu tiên.
- Owner.
- Due date.
- Tiêu chí hoàn thành.
- Exercise cần chạy lại.

Không đóng action chỉ vì tài liệu đã sửa. Nếu gap ảnh hưởng RTO/RPO, phải chạy lại phần test liên quan để xác nhận.

### 16.4. Tần suất diễn tập

Tần suất tùy mức độ quan trọng, thay đổi kiến trúc và yêu cầu quản trị. Có thể:

- Tabletop mỗi quý.
- Restore test định kỳ theo backup policy.
- Technical failover hằng năm hoặc trước release lớn.
- Test lại sau thay đổi Region, database, KMS, IAM hoặc routing.
- Game day sau khi khắc phục gap quan trọng.

Đây là lịch tham khảo; tổ chức cần điều chỉnh theo risk, compliance và business requirement.

## 17. Chi phí DR và trade-off

### 17.1. Thành phần chi phí

Chi phí DR có thể gồm:

- Backup storage và lifecycle.
- Cross-Region/cross-account copy.
- Replication request và data transfer.
- Warm standby compute/database.
- Network, VPC endpoints, NAT và load balancer.
- KMS keys và API requests.
- Monitoring, logs, traces và audit.
- Restore/failover exercise.
- AWS Support và nhân lực vận hành.

### 17.2. So sánh chi phí theo strategy

| Strategy | Chi phí thường gặp | Yếu tố chi phối |
|---|---|---|
| Backup and Restore | Backup storage và exercise | Dung lượng, retention, restore frequency |
| Pilot Light | Backup/replication và nền tảng tối thiểu | Data replication, artifact, quota readiness |
| Warm Standby | Thêm compute/database chạy thường xuyên | Tỷ lệ công suất standby, network và replication |
| Active/Active | Hai hoặc nhiều Region hoạt động | Compute, data replication, conflict handling và traffic |

Không thể gán một hệ số chi phí chung cho mọi strategy. Dùng AWS Pricing Calculator và dữ liệu thực tế để so sánh cùng một workload.

### 17.3. Chi phí diễn tập

Một exercise có thể phát sinh:

- Restore resource tạm thời.
- Compute chạy trong thời gian test.
- Data transfer.
- Log/trace ingestion.
- Snapshot hoặc backup mới.
- Load generator và test data.
- Nhân lực và downtime có kiểm soát.

Đặt budget cho exercise, cleanup resource sau test và ghi lại chi phí để đưa vào lịch DR định kỳ.

### 17.4. Cost versus RTO/RPO

Khi RTO/RPO càng thấp, thường cần replication nhanh hơn, standby capacity lớn hơn, automation nhiều hơn và nhiều bài test hơn. Tuy nhiên, không phải lúc nào chi phí cao nhất cũng cần thiết.

So sánh phương án theo:

- Business loss nếu vượt RTO/RPO.
- Chi phí vận hành thường xuyên.
- Chi phí triển khai và kiểm thử.
- Độ phức tạp và khả năng duy trì của đội.
- Mức độ tin cậy có bằng chứng.

Chọn phương án tối ưu theo business impact, không chỉ theo giá hạ tầng.

## 18. Ví dụ diễn tập: mất primary Region của Order Platform

### 18.1. Mục tiêu

Giả sử Order Platform có:

- RTO mục tiêu 120 phút.
- RPO mục tiêu 15 phút cho order.
- Primary Region và recovery Region.
- DynamoDB Global Tables hoặc backup/restore strategy đã chọn.
- S3 CRR cho invoice.
- IaC, ECR artifact, secret replica và recovery endpoint.

Mục tiêu exercise là kiểm chứng khả năng chuyển traffic và phục hồi luồng tạo/đọc đơn trong recovery Region.

### 18.2. Chuẩn bị

1. Dùng test account hoặc môi trường cô lập.
2. Tạo order test theo sequence tăng dần.
3. Ghi checkpoint độc lập.
4. Xác minh backup/replication status.
5. Kiểm tra KMS, secret, image, quota và DNS.
6. Chuẩn bị dashboard và runbook.
7. Xác định stop condition.

### 18.3. Thực hiện

1. Điều phối viên tuyên bố thời điểm T0 trong kịch bản.
2. Incident Commander đánh giá và kích hoạt DR.
3. Database Lead xác minh recovery point.
4. Platform Lead xác nhận recovery network, IAM và KMS.
5. Application Lead deploy/scale compute.
6. Team fence primary trong môi trường test.
7. Promote/restore dữ liệu và kiểm tra sequence.
8. Chuyển traffic tới recovery endpoint.
9. Chạy create/read order, event processing và attachment download.
10. Business Owner xác nhận.

### 18.4. Ví dụ kết quả đo

| Mốc | Timestamp giả định |
|---|---|
| Disruption bắt đầu (T0) | 10:00 |
| Incident được phát hiện (T1) | 10:04 |
| DR được tuyên bố (T3) | 10:12 |
| Recovery bắt đầu (T4) | 10:15 |
| Data validation pass (T5) | 10:58 |
| Application health pass (T6) | 11:08 |
| Traffic chuyển xong (T7) | 11:20 |
| Business validation pass (T8) | 11:28 |
| Dịch vụ được tuyên bố phục hồi (T9) | 11:30 |

RTO thực tế:

\[
11{:}30 - 10{:}00 = 90\ phút
\]

Nếu điểm order cuối cùng có thể phục hồi có timestamp 09:49:

\[
RPO_{actual} = 10{:}00 - 09{:}49 = 11\ phút
\]

Trong ví dụ giả định, RTO 90 phút đạt mục tiêu 120 phút và RPO 11 phút đạt mục tiêu 15 phút. Cần tiếp tục đo thời gian drain backlog và đối soát payment vì các hoạt động này có thể ảnh hưởng MTD dù dịch vụ đã được mở lại.

### 18.5. Kết luận exercise

Ghi rõ:

- RTO/RPO có đạt không.
- Thành phần nào chiếm nhiều thời gian.
- Có bước manual nào không có owner.
- Dữ liệu order, payment, event và invoice có nhất quán không.
- Có nguy cơ duplicate hoặc split-brain không.
- Chi phí exercise.
- Corrective actions và lịch chạy lại.

## 19. Các lỗi thường gặp khi diễn tập DR

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra backup job thành công | Không biết restore có hoạt động | Restore test định kỳ |
| Dùng Multi-AZ như DR toàn Region | Không phục hồi được khi Region lỗi | Có backup/copy hoặc recovery Region |
| Chọn RTO/RPO theo cảm tính | Mục tiêu không gắn business impact | Thực hiện BIA |
| Chỉ đo thời gian restore database | Bỏ sót deploy, DNS và validation | Đo end-to-end từ disruption |
| Không đo timestamp dữ liệu | RPO không có bằng chứng | Sequence/checkpoint và reconciliation |
| Không kiểm tra KMS/secret | Resource restore nhưng app không chạy | Test key, secret và IAM |
| Không kiểm tra quota | Recovery Region không scale được | Quota review và capacity plan |
| Replicate dữ liệu lỗi sang DR | Khôi phục cả corruption/ransomware | Immutable backup và recovery point sạch |
| Hai Region cùng nhận write | Split-brain và conflict | Fencing và single-writer control |
| Chỉ tabletop, không restore thật | Không biết thời gian và lỗi kỹ thuật | Component restore và failover test |
| Không diễn tập failback | Không thể trở lại primary an toàn | Có failback runbook và exercise |
| Không cleanup | Tăng chi phí và rủi ro | Teardown và post-exercise review |

## 20. Checklist capstone DR

### Business và mục tiêu

- [ ] Có BIA và business owner.
- [ ] RTO/RPO/MTD được phê duyệt.
- [ ] Định nghĩa rõ thời điểm bắt đầu/kết thúc đo RTO.
- [ ] Xác định recovery tier cho từng workload/dataset.
- [ ] Có workaround nghiệp vụ khi hệ thống chưa phục hồi.

### Kiến trúc và dữ liệu

- [ ] Chọn DR strategy theo RTO/RPO và cost.
- [ ] Có dependency map và recovery order.
- [ ] Backup/replication được cấu hình và giám sát.
- [ ] Backup được bảo vệ khỏi workload production.
- [ ] KMS, secret, certificate và IAM sẵn sàng.
- [ ] Recovery Region có quota, network và artifact.
- [ ] Có cơ chế fencing và tránh split-brain.
- [ ] Data consistency và reconciliation được định nghĩa.

### Runbook và exercise

- [ ] Có Incident Commander và recovery roles.
- [ ] Có điều kiện kích hoạt và stop condition.
- [ ] Có runbook restore, failover và failback.
- [ ] Có tabletop và technical exercise.
- [ ] Có timestamp, checkpoint và test data.
- [ ] Có smoke test và business validation.
- [ ] Có kế hoạch cleanup và rollback.

### Đo lường và cải tiến

- [ ] RTO actual được đo end-to-end.
- [ ] RPO actual được xác minh bằng dữ liệu.
- [ ] Có report và evidence.
- [ ] Gap có owner, due date và acceptance criteria.
- [ ] Exercise được chạy lại sau khi khắc phục gap.
- [ ] Chi phí DR và exercise được theo dõi.

## 21. Kết luận

DR không chỉ là tạo một bản sao dữ liệu hoặc bật Multi-AZ. Đó là khả năng khôi phục một quy trình kinh doanh với dữ liệu đáng tin cậy, identity, network, application, dependency và con người trong giới hạn RTO/RPO đã được phê duyệt. BIA giúp đặt mục tiêu theo tác động; dependency map và recovery tier giúp chọn strategy; AWS Backup, S3, DynamoDB, RDS/Aurora, EBS, EFS và AWS DRS cung cấp các cơ chế bảo vệ/phục hồi phù hợp với từng loại workload.

Một diễn tập có giá trị phải kiểm tra restore thật, chuyển traffic, data validation, split-brain prevention, backlog và failback. RTO được đo từ mốc disruption đến khi dịch vụ và nghiệp vụ được xác nhận phục hồi; RPO được đo từ dữ liệu cuối cùng có thể khôi phục so với thời điểm sự cố. Backup job xanh hoặc endpoint trả 200 không đủ để chứng minh mục tiêu đạt.

Sau mỗi exercise, tổ chức cần lưu timeline, evidence, chi phí và corrective action có owner. Chạy lại bài test sau khi sửa để xác nhận khoảng trống đã được đóng. Khi diễn tập trở thành hoạt động định kỳ, kế hoạch DR chuyển từ tài liệu giả định thành năng lực phục hồi có thể đo lường.

## 22. Tài liệu tham khảo chính thức

- [AWS Well-Architected Framework – Reliability Pillar](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/welcome.html)
- [Disaster recovery options in the cloud](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html)
- [AWS Backup Developer Guide](https://docs.aws.amazon.com/aws-backup/latest/devguide/whatisbackup.html)
- [AWS Backup restore testing](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing.html)
- [AWS Backup Vault Lock](https://docs.aws.amazon.com/aws-backup/latest/devguide/vault-lock.html)
- [Amazon S3 replication](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html)
- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [Amazon DynamoDB backup and restore](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/BackupRestore.html)
- [Amazon DynamoDB global tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html)
- [Amazon RDS backup and restore](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_CommonTasks.BackupRestore.html)
- [Amazon Aurora Global Database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database.html)
- [AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/what-is-drs.html)
- [Amazon Route 53 routing policies](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy.html)
- [AWS Global Accelerator](https://docs.aws.amazon.com/global-accelerator/latest/dg/what-is-global-accelerator.html)
- [AWS Resilience Hub](https://docs.aws.amazon.com/resilience-hub/latest/userguide/what-is.html)
- [AWS Fault Injection Service](https://docs.aws.amazon.com/fis/latest/userguide/what-is.html)
- [AWS Well-Architected Tool](https://docs.aws.amazon.com/wellarchitected/latest/userguide/intro.html)
