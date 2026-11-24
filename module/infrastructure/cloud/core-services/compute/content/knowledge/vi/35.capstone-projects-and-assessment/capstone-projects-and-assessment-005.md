# Xây dựng phương án backup, khôi phục và diễn tập cutover

Một hệ thống cloud có thể chạy ổn định trong thời gian dài nhưng vẫn gặp sự cố nghiêm trọng: xóa nhầm dữ liệu, lỗi ứng dụng ghi dữ liệu sai, database bị corruption, mất một availability zone, region ngừng hoạt động hoặc cấu hình network làm người dùng không thể truy cập. Có bản backup chưa đủ để chứng minh hệ thống có thể phục hồi; có môi trường dự phòng cũng chưa đủ để chứng minh traffic có thể chuyển sang đó an toàn.

Capstone này yêu cầu xây dựng một phương án backup và disaster recovery (DR) có thể thực thi, sau đó thiết kế và diễn tập cutover từ môi trường chính sang môi trường phục hồi. Kết quả phải chứng minh dữ liệu khôi phục được, dịch vụ đạt mục tiêu RPO/RTO, traffic chuyển đúng nơi, các dependency hoạt động và đội vận hành có thể rollback hoặc failback theo điều kiện đã định.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, dự án kết hợp năng lực compute, storage, network, identity, automation, high availability và tối ưu chi phí. Phương án cần áp dụng được cho workload chạy trên VM, container hoặc serverless; các chi tiết triển khai được chọn theo kiến trúc thực tế của hệ thống.

## 1. Mục tiêu dự án

Sau khi hoàn thành, người học có thể:

1. Phân loại workload, dữ liệu và dependency theo mức độ quan trọng.
2. Xác định RPO, RTO, recovery tier và tiêu chí dịch vụ được coi là phục hồi.
3. Thiết kế chiến lược backup, retention, encryption, immutability và kiểm thử restore.
4. Chọn mô hình DR phù hợp: backup and restore, pilot light, warm standby hoặc hot standby.
5. Lập bản đồ dependency và thứ tự khôi phục compute, storage, database, network, identity và application.
6. Xây dựng runbook cutover, validation, rollback và failback.
7. Thiết kế diễn tập có phạm vi, guardrail, người phụ trách, mốc thời gian và tiêu chí dừng.
8. Đo actual RPO/RTO, chi phí DR và các khoảng cách so với mục tiêu.
9. Chuyển kết quả diễn tập thành action item có owner, deadline và lịch retest.

## 2. Bối cảnh giả định

Một doanh nghiệp vận hành nền tảng đặt hàng trực tuyến. Hệ thống production gồm:

- API Orders chạy trên container có nhiều replica.
- Worker xử lý thanh toán, gửi thông báo và tạo báo cáo chạy dưới dạng container job.
- Managed relational database lưu khách hàng, đơn hàng và trạng thái thanh toán.
- Object storage lưu hóa đơn, ảnh và file xuất dữ liệu.
- Message queue truyền sự kiện từ API đến worker.
- Cache dùng chung để giảm tải database.
- DNS, load balancer và API gateway tiếp nhận traffic.
- Identity provider, secret manager và KMS cung cấp danh tính, secret và khóa mã hóa.
- Monitoring, logging và alerting theo dõi hệ thống.

Môi trường chính chạy ở Region A, trải trên ba availability zone. Doanh nghiệp có thể khôi phục ở Region B. Một số thành phần stateless có thể được dựng lại bằng Infrastructure as Code; database và object data cần chiến lược bảo vệ riêng.

### 2.1. Sơ đồ hệ thống hiện tại

~~~mermaid
flowchart TD
    U["Người dùng / đối tác"] --> DNS["DNS / WAF / API Gateway"]
    DNS --> LB["Load balancer"]
    LB --> API["Orders API containers"]
    API --> DB["Managed relational database"]
    API --> CACHE["Shared cache"]
    API --> Q["Message queue"]
    Q --> W["Background workers"]
    API --> OBJ["Object storage"]
    W --> DB
    W --> OBJ
    W --> EXT["Payment / Notification APIs"]
    API --> ID["Identity / KMS / Secrets"]
    W --> ID
    API --> OBS["Logs / metrics / traces"]
    W --> OBS
~~~

Đây là kiến trúc tham chiếu cho bài tập. Khi áp dụng cho hệ thống khác, cần thay tên dịch vụ, luồng dữ liệu, failure domain và yêu cầu nghiệp vụ theo thực tế.

### 2.2. Giả định nghiệp vụ ban đầu

| Thành phần | Mức quan trọng | Tác động nếu gián đoạn |
| --- | --- | --- |
| Orders API | Rất cao | Không thể tạo hoặc tra cứu đơn hàng |
| Orders database | Rất cao | Mất khả năng đọc/ghi dữ liệu giao dịch |
| Payment worker/queue | Rất cao | Giao dịch có thể bị treo hoặc xử lý trùng |
| Object storage hóa đơn | Cao | Người dùng không tải được hóa đơn |
| Notification worker | Trung bình | Thông báo bị trễ, có thể gửi bù |
| Reporting pipeline | Thấp hơn | Báo cáo có thể chạy bù sau |
| Cache | Trung bình | Latency và tải database tăng |

Không mặc định mọi thành phần phải có cùng RPO/RTO. Cache có thể tái tạo; dữ liệu giao dịch cần bảo vệ nghiêm ngặt hơn; báo cáo có thể chấp nhận khôi phục chậm hơn.

## 3. Xác định phạm vi và giả định của DR

Trước khi thiết kế, hãy ghi rõ hệ thống nào, dữ liệu nào và loại sự cố nào nằm trong phạm vi.

### 3.1. Phạm vi bảo vệ

Phân loại:

- Production workload và dependency trực tiếp.
- Dữ liệu giao dịch và dữ liệu có thể tái tạo.
- Artifact, image, IaC và cấu hình runtime.
- Identity, secret, certificate và khóa mã hóa.
- Network, DNS, route, firewall và endpoint.
- Monitoring, logging, alert và kênh liên lạc.
- Quy trình vận hành, runbook và quyền truy cập khẩn cấp.

### 3.2. Kịch bản sự cố

Chọn ít nhất ba kịch bản có tác động khác nhau:

| Kịch bản | Ví dụ | Mục tiêu kiểm chứng |
| --- | --- | --- |
| Data corruption/xóa nhầm | Lệnh cập nhật sai làm hỏng dữ liệu | PITR, backup integrity và đối soát |
| Compute failure | Node pool hoặc một nhóm VM mất | Dựng lại compute và phục hồi endpoint |
| Zone outage | Một availability zone không còn phục vụ | Phân phối replica và capacity còn lại |
| Region outage | Region chính mất kết nối hoặc dịch vụ | Cutover sang recovery region |
| Identity/config failure | Secret, certificate hoặc policy sai | Khả năng khôi phục danh tính và cấu hình |
| Application release failure | Bản phát hành mới gây lỗi dữ liệu hoặc request | Rollback ứng dụng và compatibility dữ liệu |

Không cần giả lập mọi kịch bản trong một buổi diễn tập. Chọn phạm vi đủ nhỏ để kiểm soát rủi ro nhưng đủ rộng để kiểm chứng dependency end-to-end.

### 3.3. Những điều nằm ngoài phạm vi

Ghi rõ giới hạn, ví dụ:

- Không thử nghiệm mất đồng thời cả hai region.
- Không gửi giao dịch thanh toán thật trong môi trường diễn tập.
- Không xóa dữ liệu production để giả lập corruption.
- Không chuyển public traffic nếu chưa có change window và phê duyệt.
- Không giả định nhà cung cấp có thể cấp capacity bất kỳ lúc nào.

Giới hạn phạm vi giúp người tham gia hiểu rõ điều gì đã được kiểm chứng và điều gì vẫn là giả định.

## 4. Phân tích tác động nghiệp vụ và đặt RPO/RTO

### 4.1. Business Impact Analysis

Với từng dịch vụ, trả lời:

- Dịch vụ hỗ trợ hoạt động nghiệp vụ nào?
- Nếu ngừng 15 phút, 1 giờ hoặc 1 ngày thì thiệt hại là gì?
- Dữ liệu nào có thể tái tạo và dữ liệu nào không thể mất?
- Có thời điểm cao điểm hoặc thời hạn pháp lý nào không?
- Dịch vụ nào phải phục hồi trước dịch vụ khác?
- Ai có quyền chấp nhận downtime hoặc dữ liệu thiếu?

RPO/RTO cần được owner nghiệp vụ, kỹ thuật, bảo mật và vận hành thống nhất. Đội hạ tầng không nên tự đặt mục tiêu thay cho nghiệp vụ.

### 4.2. RPO

Recovery Point Objective là lượng dữ liệu tối đa có thể mất, thường biểu diễn bằng khoảng thời gian. RPO 5 phút có nghĩa điểm dữ liệu nhất quán được phục hồi không được lùi quá 5 phút so với mốc sự cố đã thống nhất.

RPO chịu ảnh hưởng bởi:

- Tần suất và thời gian hoàn tất backup.
- Độ trễ replication.
- Tính liên tục của transaction log.
- Khả năng point-in-time recovery.
- Tính nhất quán giữa database, object, queue và event.
- Thời điểm dữ liệu được commit bền vững.

Backup mỗi 5 phút không tự bảo đảm RPO 5 phút. Cần xác minh restore point thực tế và transaction log có thể replay.

### 4.3. RTO

Recovery Time Objective là thời gian gián đoạn tối đa nghiệp vụ chấp nhận. Actual RTO cần tính từ mốc bắt đầu đã định nghĩa đến khi dịch vụ đạt tiêu chí phục hồi.

Các bước thường nằm trong RTO:

- Phát hiện và xác nhận sự cố.
- Tuyên bố DR và huy động người phụ trách.
- Chọn recovery site và restore point.
- Cấp phát network, identity, key và compute.
- Restore database, object và volume.
- Khởi động API, worker và dependency.
- Kiểm tra dữ liệu và nghiệp vụ.
- Chuyển traffic và xác minh SLO.

VM ở trạng thái Running hoặc database ở trạng thái Online chưa đủ để kết luận RTO đạt.

### 4.4. Bảng mục tiêu tham chiếu

Các giá trị sau là giả định cho capstone, cần được điều chỉnh theo BIA:

| Workload/dữ liệu | RPO mục tiêu | RTO mục tiêu | Recovery tier |
| --- | ---: | ---: | --- |
| Orders database | 5 phút | 30 phút | Tier 1 |
| Payment state/queue | 1 phút | 15 phút | Tier 0/1 |
| Orders API | Không áp dụng trực tiếp cho compute stateless; dữ liệu theo DB | 15 phút | Tier 1 |
| Hóa đơn/object data | 1 giờ | 2 giờ | Tier 2 |
| Notification backlog | 15 phút | 2 giờ | Tier 2 |
| Reporting output | 24 giờ | 1 ngày | Tier 3 |
| Cache | Có thể tái tạo | 30 phút | Tier 2 |

Với API stateless, RPO dữ liệu nằm ở database và dịch vụ lưu trữ. Không nên gán RPO cho container image như thể image là dữ liệu giao dịch.

### 4.5. Định nghĩa mốc đo

Ghi rõ:

- T0 disruption: thời điểm dịch vụ mất khả năng đáp ứng tiêu chí.
- T_detect: thời điểm monitoring hoặc người trực phát hiện.
- T_declare: thời điểm chỉ huy kích hoạt DR.
- T_data: thời điểm dữ liệu nhất quán sẵn sàng.
- T_app: thời điểm ứng dụng đạt readiness.
- T_cutover: thời điểm traffic chuyển sang recovery site.
- T_restore: thời điểm smoke test và nghiệp vụ đạt.

Actual RTO thường được tính từ T0 đến T_restore. Nếu báo cáo dùng T_declare làm mốc bắt đầu, phải ghi rõ để tránh đánh giá thấp thời gian gián đoạn thực tế.

## 5. Thiết kế chiến lược backup

Backup phải bảo vệ dữ liệu trước xóa nhầm, corruption, lỗi ứng dụng, credential compromise và sự cố hạ tầng. Replication giúp duy trì bản sao gần thời gian thực nhưng có thể sao chép cả dữ liệu bị xóa hoặc bị hỏng; vì vậy replication không thay thế backup.

### 5.1. Phân loại dữ liệu

| Nhóm dữ liệu | Cách bảo vệ gợi ý | Điểm cần xác minh |
| --- | --- | --- |
| Database giao dịch | Full/incremental backup và transaction log/PITR | Restore point, consistency, log chain |
| Object hóa đơn | Versioning, replication và backup/retention độc lập | Object version, delete marker, checksum |
| Queue/event | Retention, replay hoặc archive theo yêu cầu | Offset, duplicate, ordering |
| Cache | Tái tạo từ nguồn dữ liệu chính | Không coi cache là nguồn dữ liệu duy nhất |
| VM disk/config | Snapshot, image và IaC | Application consistency, encryption |
| Container image | Registry replication và artifact retention | Digest, signature, dependency version |
| IaC/configuration | Version control và protected artifact | Drift, secret reference và version |
| Secret/key/certificate | Backup/escrow theo chính sách và recovery access | Quyền khôi phục, key lifecycle, expiry |

### 5.2. Quy tắc backup

Có thể dùng nguyên tắc 3-2-1-1-0 như một điểm kiểm tra:

- Có nhiều bản sao dữ liệu, gồm bản production và các bản backup.
- Dùng ít nhất hai loại phương tiện hoặc failure domain phù hợp.
- Có ít nhất một bản sao ngoài site/region chính.
- Có một bản sao offline hoặc immutable/khó bị thay đổi theo threat model.
- Có zero lỗi chưa được xác minh qua kiểm tra backup và restore.

Đây là hướng dẫn thiết kế, không thay thế yêu cầu pháp lý, retention hoặc kiến trúc cụ thể. Với cloud, “offline” có thể được thay bằng vault hoặc immutable storage có ranh giới quyền truy cập riêng.

### 5.3. Backup database

Thiết kế tối thiểu cần nêu:

- Full backup theo lịch.
- Incremental/differential nếu dịch vụ hỗ trợ.
- Transaction log/binlog/WAL được lưu liên tục theo yêu cầu RPO.
- Retention theo ngày/tuần/tháng.
- Mã hóa bằng key được quản lý.
- Bản sao ở account/project/subscription hoặc region khác.
- Quyền restore tách khỏi quyền xóa backup.
- Kiểm tra tự động trạng thái job và tuổi bản backup.
- Restore test định kỳ vào môi trường cô lập.

Ví dụ lịch tham chiếu:

| Loại | Tần suất | Retention minh họa |
| --- | --- | --- |
| Transaction log | Liên tục hoặc theo khả năng dịch vụ | Đủ dài để đáp ứng PITR |
| Incremental | Mỗi 6 giờ | 7 ngày |
| Full backup | Mỗi ngày | 35 ngày |
| Monthly archive | Mỗi tháng | 12 tháng |

Tần suất và retention phải phù hợp RPO, RTO, chi phí và quy định dữ liệu. Không áp dụng bảng ví dụ mà chưa xác minh khả năng PITR của database.

### 5.4. Backup object storage

Đánh giá:

- Versioning có bật cho bucket/container quan trọng không?
- Có object lock hoặc immutable retention không?
- Replication có bảo vệ khỏi xóa nhầm hoặc corruption không?
- Có cần backup độc lập với replication?
- Metadata và quyền truy cập có được bảo vệ không?
- Lifecycle có xóa phiên bản cũ trước hạn không?
- Có kiểm tra checksum và restore sample không?

Replication liên vùng giúp có bản sao gần nguồn, nhưng thao tác xóa hoặc ghi đè có thể lan sang bản sao. Versioning, retention lock và backup độc lập giúp phục hồi lịch sử.

### 5.5. Backup cấu hình và artifact

Không chỉ dữ liệu cần backup. Cần lưu:

- Infrastructure as Code và module version.
- Container image digest và SBOM.
- Deployment manifest/Helm chart đã phát hành.
- Policy, firewall rule và route configuration.
- DNS record và certificate inventory.
- Runbook, sơ đồ dependency và contact/escalation.
- Script restore và kiểm tra nghiệp vụ.

Secret không nên được lưu trong repository backup ở dạng plaintext. Backup secret phải dùng cơ chế vault/key management có kiểm soát và có quy trình recovery riêng.

### 5.6. Immutable backup và tách quyền

Để giảm nguy cơ ransomware hoặc credential bị chiếm:

- Dùng backup vault/account riêng.
- Tách quyền tạo backup, đọc backup và xóa backup.
- Bật retention lock hoặc immutability nếu dịch vụ hỗ trợ.
- Yêu cầu phê duyệt nhiều bên cho thao tác phá hủy.
- Dùng MFA và break-glass access.
- Ghi audit log ra nơi độc lập.
- Kiểm tra khả năng restore bằng danh tính DR riêng.

Một bản backup mà cùng một credential production có thể xóa ngay lập tức sẽ có rủi ro cao khi credential đó bị compromise.

## 6. Chọn mô hình DR

### 6.1. Backup and restore

Recovery site không duy trì đầy đủ compute. Khi sự cố xảy ra, đội ngũ dựng network, identity, compute và restore dữ liệu từ backup.

Ưu điểm:

- Chi phí thường thấp hơn do ít capacity standby.
- Kiến trúc đơn giản hơn.
- Phù hợp workload có RTO dài.

Đánh đổi:

- Provision và restore có thể mất nhiều thời gian.
- Phụ thuộc quota, capacity và khả năng truy cập artifact.
- RTO cần được chứng minh bằng diễn tập.

### 6.2. Pilot light

Giữ sẵn các thành phần dữ liệu hoặc nền tảng tối thiểu ở recovery site. Khi cần, mở rộng compute, cấu hình ứng dụng và chuyển traffic.

Ưu điểm:

- Nhanh hơn backup and restore.
- Không phải duy trì toàn bộ production capacity.
- Có thể phù hợp workload quan trọng với tải vừa phải.

Đánh đổi:

- Cần automation đáng tin cậy để scale-up.
- RTO phụ thuộc quota và thời gian tạo compute.
- Cấu hình dự phòng có thể drift nếu không kiểm tra.

### 6.3. Warm standby

Recovery site có bản sao workload đang chạy ở capacity thấp. Khi failover, tăng replica hoặc node capacity, kiểm tra dữ liệu rồi chuyển traffic.

Ưu điểm:

- Có thể đạt RTO ngắn hơn.
- Nhiều dependency đã được dựng sẵn.
- Có thể kiểm tra health thường xuyên.

Đánh đổi:

- Tốn chi phí duy trì môi trường standby.
- Phải đồng bộ config, image, secret và database.
- Capacity thấp có thể không đáp ứng peak khi failover.

### 6.4. Hot standby hoặc active-active

Hot standby duy trì môi trường dự phòng gần sẵn sàng, thường có replication và capacity đáng kể. Active-active cho phép nhiều site cùng phục vụ traffic.

Ưu điểm:

- Có thể giảm thời gian chuyển đổi.
- Có thể phân phối tải và tăng khả năng phục vụ.

Đánh đổi:

- Chi phí cao.
- Quản lý consistency, split-brain và conflict phức tạp.
- Cần thiết kế routing, data ownership và failback chặt chẽ.

### 6.5. Ma trận lựa chọn

| Chiến lược | RPO/RTO tương đối | Chi phí standby | Độ phức tạp |
| --- | --- | --- | --- |
| Backup and restore | Cao hơn | Thấp | Thấp đến trung bình |
| Pilot light | Trung bình | Thấp đến trung bình | Trung bình |
| Warm standby | Thấp đến trung bình | Trung bình đến cao | Cao |
| Hot standby | Thấp | Cao | Cao |
| Active-active | Có thể rất thấp | Rất cao | Rất cao |

Không có mô hình tối ưu cho mọi dịch vụ. Chọn theo BIA, consistency, RPO/RTO, khả năng vận hành và ngân sách.

## 7. Thiết kế kiến trúc recovery region

Recovery region cần có các thành phần theo đúng dependency graph, không chỉ có VM hoặc container.

### 7.1. Các lớp cần chuẩn bị

**Foundation**

- Account/project/subscription và billing.
- VPC/VNet, subnet, route, firewall và NAT.
- DNS, private zone, endpoint và connectivity.
- IAM, workload identity, KMS và secret access.
- Quota, capacity và image availability.

**Data**

- Database replica hoặc backup/PITR.
- Object replication/versioning.
- Queue retention/archive hoặc replay strategy.
- Cache có thể tái tạo.
- Encryption key và backup catalog.

**Compute/application**

- Container registry mirror hoặc image pull access.
- VM image/template hoặc node pool.
- Deployment manifest và IaC.
- API, worker, scheduler và background task.
- Load balancer, ingress và health check.

**Operations**

- Monitoring, logging và alert.
- Runbook, contact list và change record.
- DR identity và break-glass.
- Test data và business validation script.

### 7.2. Recovery dependency graph

~~~mermaid
flowchart TD
    A["DR declaration / recovery decision"] --> B["Account, quota and access"]
    B --> C["Network, DNS private, firewall"]
    B --> D["KMS, identity and secrets"]
    C --> E["Storage and database recovery"]
    D --> E
    C --> F["Compute capacity and runtime"]
    D --> F
    E --> G["Deploy API and workers"]
    F --> G
    G --> H["Service discovery and load balancer"]
    H --> I["Smoke test and data validation"]
    I --> J["Traffic cutover"]
    J --> K["Business verification and monitoring"]
~~~

Một số bước có thể chạy song song, chẳng hạn chuẩn bị network và kiểm tra artifact. Tuy nhiên, application không nên nhận traffic trước khi database, identity và dependency thiết yếu sẵn sàng.

### 7.3. Quota và capacity

Quota là giới hạn được phép sử dụng; capacity là tài nguyên vật lý/logic provider có thể cấp phát tại vị trí và thời điểm cụ thể. Quota còn dư không bảo đảm VM/GPU/instance type sẽ có capacity.

Trước khi diễn tập:

- Kiểm tra quota compute, IP, disk, load balancer và database.
- Xác nhận instance family/zone có thể được tạo.
- Đặt capacity reservation nếu RTO yêu cầu và dịch vụ hỗ trợ.
- Xác minh subnet có đủ IP.
- Kiểm tra giới hạn API, database connection và queue throughput.

## 8. Xây dựng recovery runbook

Runbook phải có thể được người trực khác thực hiện, kể cả khi người thiết kế ban đầu không có mặt.

### 8.1. Vai trò

| Vai trò | Trách nhiệm |
| --- | --- |
| Incident commander | Điều phối, quyết định chuyển trạng thái và giữ timeline |
| DR lead | Điều phối các bước kỹ thuật và recovery site |
| Database owner | Chọn restore point, restore và xác minh consistency |
| Platform/compute owner | Dựng compute, node pool, container và scaling |
| Network/DNS owner | Network, ingress, routing và traffic cutover |
| Security/IAM owner | Identity, KMS, secret, audit và quyền khẩn cấp |
| Application owner | Smoke test và xác minh nghiệp vụ |
| Communications lead | Cập nhật trạng thái cho stakeholder |
| Scribe/observer | Ghi timestamp, evidence, blocker và action item |

Một người có thể đảm nhiệm nhiều vai trò ở nhóm nhỏ, nhưng quyền phê duyệt và người thực hiện thao tác nhạy cảm nên được phân định.

### 8.2. Điều kiện kích hoạt DR

Ví dụ tiêu chí:

- Region chính không thể phục vụ trong thời gian vượt ngưỡng.
- Dự báo thời gian phục hồi production dài hơn RTO.
- Data corruption lan rộng và cần phục hồi từ bản backup sạch.
- Incident commander cùng owner nghiệp vụ phê duyệt.

Không tự động failover chỉ vì một health check thất bại ngắn. Cần có ngưỡng, xác nhận và chống flapping.

### 8.3. Runbook theo giai đoạn

| Giai đoạn | Công việc | Bằng chứng cần lưu |
| --- | --- | --- |
| 1. Declare | Xác nhận sự cố, T0, phạm vi và quyết định DR | Incident ID, timestamp, approver |
| 2. Select | Chọn recovery site và restore point | Backup ID, log position, lý do chọn |
| 3. Foundation | Xác minh access, quota, network, key và secret | IaC run result, policy check |
| 4. Data | Restore DB/object/queue theo thứ tự | Restore job ID, checksum, data validation |
| 5. Compute | Tạo node/VM/task và deploy workload | Image digest, replica count, health |
| 6. Validate | Kiểm tra dependency, API và nghiệp vụ | Smoke test, reconciliation report |
| 7. Cutover | Chuyển traffic theo kế hoạch | DNS/LB change, traffic share |
| 8. Stabilize | Theo dõi SLO và lỗi sau chuyển đổi | Dashboard, alert, business approval |
| 9. Close | Ghi RPO/RTO, cleanup và kế hoạch failback | Timeline, report, action items |

## 9. Chuẩn bị cutover

Cutover là chuyển workload hoặc traffic từ môi trường nguồn sang môi trường đích theo một trình tự có kiểm soát. Cutover có thể diễn ra trong migration có kế hoạch hoặc DR failover. Dù mục đích khác nhau, đều cần kiểm soát dữ liệu, traffic, dependency và rollback.

### 9.1. Chọn kiểu cutover

| Kiểu | Cách thực hiện | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| DNS switch | Đổi DNS record sang endpoint mới | Dễ hiểu, hỗ trợ nhiều kiến trúc | TTL/cache khiến chuyển đổi không tức thì |
| Load balancer switch | Đổi backend hoặc target group | Điều khiển traffic nhanh hơn trong một số kiến trúc | Phụ thuộc control plane và health |
| Gateway route switch | Chuyển route/weight ở gateway | Có thể canary hoặc chia traffic | Cần đồng bộ policy và route |
| Blue-green | Dựng môi trường mới song song rồi chuyển traffic | Có điểm quay lại rõ trước khi ghi dữ liệu mới | Cần tương thích schema và dual environment cost |
| Weighted traffic shift | Tăng dần tỷ lệ traffic đến đích | Giảm rủi ro khi validation tốt | Không phù hợp nếu dữ liệu ghi không đồng bộ |

DNS TTL thấp giúp resolver cập nhật nhanh hơn nhưng không xóa cache ở mọi client. Cần xác minh connection pooling, keep-alive và cache DNS của ứng dụng.

### 9.2. Data consistency trước cutover

Nếu hệ thống cho phép ghi đồng thời vào cả source và target mà không có thiết kế consistency, có thể tạo conflict hoặc mất giao dịch.

Một cutover kiểu single-writer thường gồm:

1. Xác nhận replication khỏe và lag trong ngưỡng.
2. Thông báo maintenance hoặc chuyển API sang read-only nếu cần.
3. Dừng producer tạo write mới.
4. Drain request đang xử lý và chờ transaction hoàn tất.
5. Chờ queue consumer xử lý hoặc ghi nhận offset còn lại.
6. Đồng bộ transaction log/object cuối cùng.
7. Xác minh target đã đạt điểm dữ liệu cuối.
8. Chuyển quyền ghi sang target.
9. Chuyển traffic và kiểm tra nghiệp vụ.

Không được tuyên bố zero data loss chỉ vì replication lag hiển thị bằng zero trong một thời điểm. Cần xác minh transaction cuối, log position, queue offset và các luồng dữ liệu ngoài database.

### 9.3. Freeze window

Với hệ thống không hỗ trợ multi-writer, có thể cần một cửa sổ freeze:

- Từ chối hoặc xếp hàng write mới.
- Trả thông báo bảo trì có kiểm soát.
- Cho phép request đọc nếu dữ liệu còn nhất quán.
- Chờ transaction đang chạy hoàn tất.
- Chụp mốc log/offset cuối.
- Chỉ mở write trên target sau khi xác minh.

Thời gian freeze phải nằm trong kế hoạch RTO và được truyền thông trước.

## 10. Cutover runbook chi tiết

### 10.1. Trước cutover

- [ ] Change window và người phê duyệt đã xác nhận.
- [ ] Recovery site đã dựng đủ foundation.
- [ ] Backup/replication health đạt yêu cầu.
- [ ] Restore point và transaction log chain đã xác minh.
- [ ] Image, manifest và IaC đúng version.
- [ ] Secret, certificate và workload identity hoạt động.
- [ ] Database target ở đúng role và không nhận ghi sớm.
- [ ] Queue producer/consumer có kế hoạch pause/resume.
- [ ] DNS/LB/gateway route đã chuẩn bị.
- [ ] Smoke test và business validation có người thực hiện.
- [ ] Rollback/failback criteria được thống nhất.
- [ ] Kênh liên lạc và escalation hoạt động.

### 10.2. Trong cutover

1. Incident commander tuyên bố bắt đầu cutover và ghi T_cutover_start.
2. Scribe ghi lại mọi hành động và timestamp.
3. Dừng hoặc hạn chế write ở source theo runbook.
4. Drain API request và worker đang chạy.
5. Chờ replication và log shipping đạt điểm cuối.
6. Chuyển database role hoặc restore target thành writable theo quy trình.
7. Cập nhật secret/config endpoint nếu cần.
8. Chuyển backend load balancer/gateway hoặc DNS.
9. Chạy smoke test từ network path giống người dùng.
10. Chạy giao dịch tổng hợp và kiểm tra dữ liệu.
11. Tăng traffic theo các bước đã định nếu dùng weighted shift.
12. Owner nghiệp vụ xác nhận cho phép mở traffic đầy đủ.

### 10.3. Sau cutover

- [ ] Error rate và latency trong ngưỡng.
- [ ] Database connection và query latency ổn định.
- [ ] Queue backlog giảm hoặc không tăng bất thường.
- [ ] Payment/order transaction không bị duplicate.
- [ ] Object và file có thể truy cập.
- [ ] Log, metric và trace đến đúng hệ thống.
- [ ] Alert không bị tắt hoặc trỏ về endpoint cũ.
- [ ] DNS, certificate và callback bên thứ ba hoạt động.
- [ ] Xác nhận nguồn ghi dữ liệu duy nhất.
- [ ] Ghi thời điểm dịch vụ phục hồi để tính actual RTO.

## 11. Rollback và failback

Rollback là quay lại phiên bản hoặc môi trường trước đó khi cutover chưa đạt tiêu chí. Failback là chuyển dịch vụ từ recovery site trở lại site chính sau khi site chính đã phục hồi. Hai hoạt động này có liên quan nhưng không giống nhau.

### 11.1. Rollback trước khi có write mới trên target

Nếu target chưa nhận giao dịch ghi mới và source vẫn nhất quán, rollback có thể đơn giản hơn:

1. Dừng traffic vào target.
2. Khôi phục route về source.
3. Xác minh source vẫn là authoritative writer.
4. Mở traffic và chạy smoke test.
5. Ghi lý do rollback và evidence.

### 11.2. Khi target đã nhận write mới

Không được đơn giản đổi traffic về source nếu source đã cũ hơn. Làm vậy có thể mất dữ liệu mới hoặc tạo split-brain.

Cần:

1. Dừng hoặc kiểm soát write trên target.
2. Xác định source of truth hiện tại.
3. Đồng bộ dữ liệu mới từ target về source hoặc một đích phục hồi khác.
4. Xác minh transaction log, sequence, queue offset và object version.
5. Kiểm tra consistency và business reconciliation.
6. Chỉ chuyển role/traffic sau khi owner dữ liệu phê duyệt.

Nếu không có replication ngược an toàn, có thể phải tiếp tục chạy ở recovery site và lên kế hoạch failback riêng.

### 11.3. Failback plan

Failback cần có:

- Điều kiện site chính đã ổn định.
- Đánh giá nguyên nhân sự cố đã được khắc phục.
- Kế hoạch đồng bộ dữ liệu từ recovery site.
- Quy trình đổi database role.
- Kiểm tra identity, secret, certificate và network.
- Cutover window và rollback plan.
- Validation nghiệp vụ sau chuyển đổi.

Không nên failback chỉ vì site chính đã hoạt động trở lại. Cần kiểm tra capacity, data consistency và khả năng chịu lỗi của site đó.

## 12. Diễn tập cutover an toàn

Diễn tập cần kiểm chứng runbook trong môi trường có kiểm soát. Có thể bắt đầu ở staging hoặc recovery environment tách biệt, sau đó mới thực hiện một phần cutover production nếu được phê duyệt.

### 12.1. Loại hình diễn tập

| Loại | Phạm vi | Mục tiêu |
| --- | --- | --- |
| Tabletop | Thảo luận và quyết định trên giấy | Vai trò, escalation và quyết định |
| Restore drill | Restore backup trong môi trường cô lập | Tính dùng được của backup |
| Component cutover | Chuyển một service hoặc dependency | Network, identity và health |
| Partial traffic shift | Chuyển một phần traffic thử nghiệm | Routing và application behavior |
| Full DR exercise | Khôi phục toàn bộ phạm vi đã định | RPO/RTO end-to-end |
| Failback rehearsal | Thử chuyển dữ liệu/traffic trở lại | Consistency và quy trình quay về |

### 12.2. Guardrail

Trước diễn tập:

- Chỉ định người điều phối và người có quyền dừng.
- Dùng tenant/test data hoặc traffic được kiểm soát.
- Chặn side effect ra payment, email, SMS hoặc hệ thống bên ngoài nếu không được phép.
- Đặt giới hạn chi phí và thời gian.
- Xác nhận endpoint production không bị thay đổi ngoài kế hoạch.
- Có snapshot/backup an toàn trước thao tác có nguy cơ ghi.
- Ghi rõ tiêu chí abort.

### 12.3. Điều kiện dừng

Ví dụ:

- Dữ liệu target không nhất quán hoặc không rõ source of truth.
- Không thể xác minh khóa mã hóa hoặc quyền truy cập.
- Smoke test tạo side effect thật ngoài dự kiến.
- Error rate production vượt ngưỡng.
- RTO còn lại không đủ để hoàn tất an toàn.
- Người có thẩm quyền yêu cầu dừng.

Khi abort, ghi trạng thái dữ liệu và traffic tại thời điểm dừng. Không tự động xóa môi trường thử nghiệm trước khi xác nhận không còn artifact cần điều tra.

### 12.4. Kịch bản diễn tập mẫu

**Tình huống:** Region A mất khả năng phục vụ. Recovery region B có database replica và warm standby compute. Mục tiêu là chuyển Orders API sang B.

| Thời điểm | Hành động | Bằng chứng |
| --- | --- | --- |
| T0 | Giả lập incident và bắt đầu timeline | Incident record |
| T+2 phút | Monitoring phát hiện, incident commander xác nhận | Alert và acknowledgement |
| T+4 phút | Declare DR, chọn recovery site | Decision log |
| T+7 phút | Kiểm tra quota, network, identity và KMS | Checklist pass |
| T+10 phút | Freeze write ở source giả lập | Application state |
| T+12 phút | Xác minh replication/log position | Database evidence |
| T+16 phút | Promote/restore target theo runbook | DB role/status |
| T+20 phút | Validate API, queue, object và payment sandbox | Smoke/business test |
| T+23 phút | Chuyển traffic thử nghiệm | LB/DNS/gateway change |
| T+27 phút | Xác nhận SLO và business owner | Dashboard/approval |

Các thời điểm chỉ minh họa để lập kịch bản. Actual RTO phải lấy từ timestamp thực tế trong buổi diễn tập.

## 13. Đo actual RPO và RTO

### 13.1. Actual RPO

Actual RPO là khoảng cách giữa mốc sự cố và điểm dữ liệu nhất quán mới nhất có thể phục hồi.

~~~text
Actual RPO =
    T_incident
  - T_latest_consistent_recovery_point
~~~

Ví dụ:

| Mốc | Thời điểm |
| --- | --- |
| Sự cố bắt đầu | 10:00:00 |
| Backup full gần nhất | 08:00:00 |
| Transaction log cuối có thể replay | 09:57:30 |
| Điểm dữ liệu nhất quán sau restore | 09:57:30 |
| Actual RPO | 2 phút 30 giây |

Nếu RPO target là 5 phút, kết quả đạt. Nếu log thiếu và chỉ restore được đến 08:00, actual RPO là 2 giờ và không đạt.

Không dùng timestamp hoàn tất backup làm điểm dữ liệu cuối nếu backup cần transaction log hoặc recovery step bổ sung.

### 13.2. Actual RTO

~~~text
Actual RTO =
    T_service_restored
  - T_disruption_start
~~~

Ví dụ:

| Mốc | Thời điểm | Thời lượng cộng dồn |
| --- | --- | ---: |
| Dịch vụ gián đoạn | 10:00 | 0 phút |
| Sự cố được phát hiện | 10:02 | 2 phút |
| DR được tuyên bố | 10:04 | 4 phút |
| Network/identity sẵn sàng | 10:08 | 8 phút |
| Database restore/promote xong | 10:16 | 16 phút |
| API healthy | 10:20 | 20 phút |
| Traffic chuyển và smoke test đạt | 10:24 | 24 phút |

Nếu RTO target là 30 phút, actual RTO 24 phút đạt theo tiêu chí đã định. Nếu chỉ tính đến lúc database online ở phút 16 thì báo cáo sẽ đánh giá thiếu thời gian cần để người dùng sử dụng dịch vụ.

### 13.3. Phân rã thời gian

Tách thời gian theo các bước:

- Detection và declaration.
- Access/approval.
- Foundation provisioning.
- Data recovery.
- Application startup.
- Traffic cutover.
- Validation.

Một số bước có thể chạy song song. Khi tính tổng, dùng timeline thực tế để tránh cộng trùng thời gian overlap.

### 13.4. Độ chính xác của timestamp

- Đồng bộ đồng hồ theo nguồn thời gian chuẩn.
- Ghi UTC và giữ timezone rõ ràng.
- Dùng timestamp từ hệ thống có audit khi có thể.
- Ghi cả thời điểm bắt đầu, hoàn tất và người thực hiện.
- Ghi log position/offset ngoài timestamp nếu database hoặc queue hỗ trợ.

## 14. Kiểm tra tính nhất quán sau restore

Restore thành công không chỉ là database báo Online. Cần xác minh ở nhiều lớp.

### 14.1. Database

- Schema/version đúng.
- Record count hoặc aggregate quan trọng phù hợp.
- Transaction cuối có thể đọc và đúng trạng thái.
- Foreign key và constraint hợp lệ.
- Sequence/identity counter không bị lùi.
- Index và stored procedure cần thiết có mặt.
- Ứng dụng có thể đọc/ghi bằng identity dự kiến.

### 14.2. Object và file

- Object count hoặc manifest đủ.
- Checksum/hash đúng.
- Version và metadata đúng.
- Quyền truy cập và encryption key hoạt động.
- Không có object ở trạng thái upload dở được coi là hoàn tất.

### 14.3. Queue và event

- Offset/sequence được khôi phục đúng.
- Message chưa xử lý không bị mất ngoài RPO.
- Message có thể được redeliver mà không tạo duplicate side effect.
- Dead-letter được giữ để điều tra.
- Producer/consumer không cùng ghi hoặc xử lý sai thứ tự.

### 14.4. Nghiệp vụ

Chạy các giao dịch tổng hợp:

- Tạo đơn thử.
- Đọc đơn theo ID.
- Xác nhận trạng thái thanh toán sandbox.
- Tạo hóa đơn hoặc artifact.
- Kiểm tra event được phát và worker xử lý.
- Đối soát số lượng giao dịch đầu vào/đầu ra.

Không dùng dữ liệu giả để kết luận tính toàn vẹn của dữ liệu production. Với diễn tập production, cần test record được đánh dấu và kiểm soát side effect.

## 15. Bảo mật trong backup và recovery

Backup có thể chứa toàn bộ dữ liệu nhạy cảm của hệ thống. Recovery environment phải được bảo vệ như production.

- Mã hóa backup khi lưu và khi truyền.
- Bảo vệ KMS key, key policy và quyền giải mã.
- Tách quyền backup, restore và delete.
- Dùng MFA/break-glass theo quy trình.
- Bật immutable retention nếu phù hợp.
- Giới hạn network của recovery environment.
- Không public database hoặc object bucket chỉ để diễn tập.
- Làm sạch hoặc ẩn danh dữ liệu nếu chỉ cần kiểm tra cấu trúc.
- Ghi audit mọi thao tác restore và cutover.
- Không ghi secret hoặc dữ liệu cá nhân vào log/runbook.
- Có quy trình rotate credential sau incident nếu nghi ngờ bị lộ.

Nếu key mã hóa không thể khôi phục, backup có thể không sử dụng được. Vì vậy, khả năng recovery của KMS/key vault phải được kiểm tra cùng backup, nhưng không được sao chép key một cách thiếu kiểm soát.

## 16. Tự động hóa và kiểm soát thay đổi

### 16.1. Infrastructure as Code

IaC giúp dựng lại:

- VPC/VNet, subnet, route và firewall.
- Load balancer, gateway và DNS.
- Compute node pool, VM, container service.
- Identity, role và policy.
- Storage, backup vault và replication.
- Monitoring, alert và log destination.

IaC phải được version hóa, review và thử trước. Không lưu secret plaintext trong state hoặc repository; dùng backend state được mã hóa và access control.

### 16.2. Automation pipeline

Pipeline DR có thể chia thành các stage:

1. Preflight: xác minh quyền, quota, backup và recovery site.
2. Foundation: dựng network, identity và secret integration.
3. Data: restore hoặc promote database/object.
4. Compute: triển khai image và workload.
5. Validate: health, consistency và smoke test.
6. Cutover: chỉ chạy sau approval gate.
7. Observe: theo dõi SLO và tự động cảnh báo.

Không nên tự động hóa một bước phá hủy hoặc chuyển quyền ghi mà không có approval gate và điều kiện kiểm tra trước.

### 16.3. Drift detection

So sánh cấu hình thực tế với IaC:

- Network rule.
- IAM role/policy.
- Database parameter.
- Backup schedule/retention.
- Deployment image/config.
- DNS và load balancer route.

Drift có thể làm recovery site không giống môi trường đã kiểm thử. Cần kiểm tra drift trước mỗi lần diễn tập và trước khi gia hạn DR readiness.

## 17. Tính chi phí của phương án

Chi phí DR gồm cả chi phí bảo vệ dữ liệu và chi phí duy trì khả năng phục hồi.

| Nhóm | Khoản cần tính |
| --- | --- |
| Backup | Storage, request, retrieval, retention và immutable vault |
| Replication | Data transfer, replica compute/storage và log shipping |
| Standby | VM/node/container capacity, database standby và load balancer |
| Recovery | Restore operation, temporary capacity và data transfer |
| Security | KMS, audit, secret vault và access review |
| Observability | Log, metric, trace và alert ở recovery region |
| People | On-call, diễn tập, review và maintenance |
| Cutover | Change window, dual-run và validation |

### 17.1. So sánh chi phí chiến lược

| Chiến lược | Chi phí bình thường | Chi phí khi sự cố |
| --- | --- | --- |
| Backup and restore | Backup/storage thấp hơn, compute DR gần như không chạy | Tăng compute và restore/data transfer |
| Pilot light | Data replication và nền tảng tối thiểu | Provision compute và scale-up |
| Warm standby | Duy trì workload capacity thấp | Scale standby lên production |
| Hot standby | Duy trì phần lớn capacity | Cutover nhanh hơn nhưng vẫn có chi phí vận hành |
| Active-active | Hai hoặc nhiều site cùng chạy | Tăng tải site còn lại và xử lý consistency |

Đừng chỉ chọn phương án có bill thấp nhất. So sánh chi phí với thiệt hại nghiệp vụ nếu không đáp ứng RPO/RTO.

### 17.2. Cost per recovery

Có thể tính:

~~~text
Cost per recovery exercise =
    Backup/retrieval cost
  + Temporary compute
  + Data transfer
  + Test environment
  + Labor cost
~~~

Theo dõi chi phí mỗi lần diễn tập giúp quyết định tần suất và mức tự động hóa. Tuy nhiên, không cắt bỏ bài restore quan trọng chỉ vì chi phí thử nghiệm.

## 18. Bộ deliverable của capstone

Người học cần nộp một bộ tài liệu đủ để đội khác review và thực hiện.

### 18.1. Architecture pack

- Sơ đồ production và recovery site.
- Dependency graph và data flow.
- Failure domain và recovery boundary.
- Danh sách thành phần được bảo vệ.
- Bảng trách nhiệm owner.

### 18.2. Backup policy

- Phân loại dữ liệu.
- Backup frequency và retention.
- Encryption, key management và immutability.
- Replication và offsite copy.
- Restore test frequency.
- Alert khi backup stale/failed.

### 18.3. DR strategy

- Recovery tier.
- RPO/RTO target.
- Mô hình DR được chọn và lý do.
- Recovery capacity và quota.
- Thứ tự khôi phục.
- Dependency và assumption.

### 18.4. Runbook pack

- Điều kiện declare DR.
- Vai trò và escalation.
- Preflight checklist.
- Restore procedure.
- Cutover steps.
- Validation checklist.
- Abort/rollback/failback.
- Cleanup và evidence retention.

### 18.5. Exercise report

- Kịch bản, phạm vi và ngày diễn tập.
- Người tham gia và approver.
- Timeline thực tế.
- Actual RPO/RTO.
- Kết quả consistency và business test.
- SLO trước/sau cutover.
- Finding, root cause và action item.

## 19. Mẫu backup policy

Có thể dùng bảng sau làm khung để điền cho hệ thống thực tế:

| Data asset | Owner | Backup method | Frequency | Retention | Offsite/immutable | Restore test |
| --- | --- | --- | --- | --- | --- | --- |
| Orders DB | Database owner | Full + log/PITR | Theo RPO | Theo policy | Có | Hằng tháng |
| Payment state | Payment owner | Native backup + log | Theo RPO | Theo policy | Có | Hằng tháng |
| Invoice objects | Storage owner | Versioning + replication/backup | Theo thay đổi | Theo policy | Có | Hằng quý |
| Queue/archive | Platform owner | Retention/archive/replay | Liên tục | Theo policy | Có | Hằng quý |
| Container images | App owner | Registry replication | Mỗi release | Theo release policy | Có | Mỗi DR exercise |
| IaC/config | Platform owner | Version control + protected backup | Mỗi thay đổi | Theo policy | Có | Mỗi DR exercise |
| Secrets/keys | Security owner | Vault recovery procedure | Theo lifecycle | Theo policy | Có kiểm soát | Theo key policy |

Không để các ô “theo policy” tồn tại trong bản production cuối. Phải điền giá trị, owner và cách kiểm chứng cụ thể.

## 20. Mẫu cutover decision record

Trước khi chuyển traffic, incident commander ghi nhận:

| Câu hỏi | Kết quả cần có |
| --- | --- |
| Recovery site có đủ capacity? | Pass/Fail và bằng chứng |
| Backup/replica có đúng restore point? | Backup ID, log position, timestamp |
| Data consistency đạt? | Checksum, transaction ID, reconciliation |
| KMS/secret/identity hoạt động? | Test access và audit |
| API/worker healthy? | Probe, smoke test và dependency status |
| Queue có an toàn để resume? | Offset, backlog, dedupe strategy |
| Traffic route đã chuẩn bị? | DNS/LB/gateway diff |
| Owner nghiệp vụ đã duyệt? | Người duyệt và timestamp |
| Rollback/failback khả thi? | Điều kiện, owner và bước cụ thể |

Nếu một điều kiện bắt buộc không đạt, không chuyển traffic toàn bộ. Có thể tiếp tục điều tra, chạy partial test hoặc abort theo runbook.

## 21. Mẫu timeline diễn tập

| Event | Timestamp UTC | Owner | Evidence | Ghi chú |
| --- | --- | --- | --- | --- |
| Disruption start |  |  |  | T0 đã định nghĩa |
| Detection |  |  |  | Alert/acknowledgement |
| DR declaration |  |  |  | Incident commander |
| Recovery site ready |  |  |  | Network/identity/capacity |
| Data recovery complete |  |  |  | Restore point và validation |
| Application ready |  |  |  | Replica và dependency |
| Traffic cutover |  |  |  | DNS/LB/gateway |
| Service restored |  |  |  | Smoke test và business approval |
| Exercise closed |  |  |  | Evidence và cleanup |

Actual RTO được tính từ disruption start đến service restored theo định nghĩa đã thống nhất. Lưu riêng thời điểm exercise closed nếu việc hoàn tất báo cáo diễn ra sau khi dịch vụ đã phục hồi.

## 22. Tiêu chí nghiệm thu

Capstone được xem là đạt khi có bằng chứng cho các nhóm sau:

### 22.1. Backup readiness

- Backup job thành công và có cảnh báo stale/failed.
- Có bản sao ngoài failure domain nguồn.
- Có retention/immutability và quyền xóa được kiểm soát.
- Khôi phục thử được dữ liệu vào môi trường cô lập.
- Khóa mã hóa và danh tính restore hoạt động.

### 22.2. Recovery readiness

- Có dependency map và thứ tự phục hồi.
- Recovery region có quota/capacity hoặc phương án cấp phát đã kiểm chứng.
- IaC/image/config có thể truy cập.
- Database/object/queue có restore hoặc replay procedure.
- API và worker đạt readiness sau khi phục hồi.

### 22.3. Cutover readiness

- Có preflight, approval gate và cutover runbook.
- Source/target writer role được xác định.
- Queue và background processing có kế hoạch pause/resume.
- DNS/LB/gateway chuyển đúng endpoint.
- Smoke test và business validation đạt.
- Có abort, rollback và failback criteria.

### 22.4. RPO/RTO evidence

- Actual RPO được tính từ restore point nhất quán.
- Actual RTO được tính từ disruption đến service restored.
- Timestamp và evidence đủ để kiểm tra lại.
- Kết quả so với target và nêu rõ pass/fail.

### 22.5. Operational readiness

- Có owner, on-call và escalation.
- Có log, metric, trace và dashboard.
- Có action item cho finding.
- Có lịch retest và người chịu trách nhiệm.

## 23. Rubric tự đánh giá

| Hạng mục | Trọng số | Mức đạt |
| --- | ---: | --- |
| BIA, scope và RPO/RTO | 15% | Mục tiêu có owner, định nghĩa và căn cứ nghiệp vụ |
| Backup policy và data protection | 20% | Có frequency, retention, encryption, offsite/immutable và restore proof |
| Recovery architecture | 15% | Dependency, quota, capacity và thứ tự phục hồi rõ ràng |
| Cutover/rollback/failback | 20% | Runbook có approval gate, writer control, validation và điều kiện quay lại |
| Rehearsal và evidence | 15% | Có timeline, actual RPO/RTO, consistency và business test |
| Security, cost và operations | 10% | Có IAM, KMS, audit, cost và owner |
| Chất lượng tài liệu | 5% | Người khác có thể thực hiện theo runbook |

Mức đánh giá:

- **Chưa đạt:** thiếu một trong các thành phần cốt lõi hoặc không có bằng chứng restore/cutover.
- **Đạt:** đáp ứng mục tiêu, có runbook và diễn tập được trong phạm vi kiểm soát.
- **Tốt:** có tự động hóa, evidence đầy đủ, phân tích bottleneck và action item được retest.
- **Xuất sắc:** có nhiều kịch bản failure, kiểm chứng failback, cost optimization và cải tiến dựa trên dữ liệu diễn tập.

## 24. Các câu hỏi review

1. RPO/RTO của từng data asset được suy ra từ yêu cầu nghiệp vụ nào?
2. Backup có thể bị xóa bởi cùng danh tính production không?
3. Nếu transaction log bị thiếu, restore point thay thế là gì?
4. Recovery site có đủ quota, IP và capacity ở đúng zone không?
5. KMS key và secret có thể truy cập khi region chính mất không?
6. Làm sao ngăn source và target cùng nhận write?
7. Queue message nào cần replay và cách tránh duplicate?
8. Điều kiện nào cho phép chuyển traffic toàn bộ?
9. Khi nào rollback không còn an toàn và phải tiếp tục chạy ở recovery site?
10. Ai có quyền declare DR, approve cutover và xác nhận business recovery?
11. Actual RPO/RTO được đo từ timestamp nào?
12. Finding nào cần xử lý trước lần diễn tập tiếp theo?

## 25. Lộ trình thực hiện dự án

1. **Khởi tạo:** xác định owner, scope, hệ thống, failure scenario và change boundary.
2. **BIA:** phân loại dịch vụ/dữ liệu và thống nhất RPO/RTO.
3. **Inventory:** lập danh sách compute, storage, network, identity, artifact và dependency.
4. **Backup design:** xác định backup method, frequency, retention, encryption và immutability.
5. **DR design:** chọn strategy, recovery region, capacity và dependency order.
6. **Runbook:** viết restore, validation, cutover, rollback và failback steps.
7. **Automation:** chuẩn bị IaC, scripts, health checks và approval gates.
8. **Preflight:** kiểm tra quyền, quota, backup freshness, key và recovery endpoint.
9. **Rehearsal:** thực hiện trong môi trường cô lập hoặc phạm vi đã phê duyệt.
10. **Measure:** ghi timeline, actual RPO/RTO, SLO, consistency và cost.
11. **Improve:** phân tích root cause, giao owner/deadline và cập nhật runbook.
12. **Retest:** diễn tập lại các bước đã sửa và xác nhận mục tiêu.

## 26. Nguyên tắc cần ghi nhớ

1. Backup chỉ đáng tin khi restore được và dữ liệu sau restore được xác minh.
2. Replication không thay thế backup vì lỗi hoặc thao tác xóa có thể lan sang bản sao.
3. RPO đo khoảng cách đến điểm dữ liệu nhất quán mới nhất; RTO đo đến lúc dịch vụ thực sự phục hồi.
4. Recovery phải bao gồm compute, storage, network, identity, key, secret và dependency.
5. Cutover cần kiểm soát writer role, transaction, queue và traffic.
6. Không rollback về source cũ nếu target đã nhận write mới mà chưa đồng bộ dữ liệu.
7. Diễn tập cần có scope, guardrail, abort criteria, người phụ trách và evidence.
8. Capacity reservation, quota và capacity vật lý là các khái niệm khác nhau.
9. Mọi finding cần có owner, deadline và retest.
10. Runbook phải đủ rõ để người trực khác thực hiện trong điều kiện áp lực.

Phương án backup, khôi phục và cutover chỉ hoàn chỉnh khi có thể chứng minh cả ba việc: dữ liệu có thể phục hồi đến điểm chấp nhận được, workload có thể hoạt động lại trong thời gian mục tiêu và traffic có thể chuyển sang môi trường phục hồi mà không tạo mất mát hoặc xử lý trùng ngoài kiểm soát. Capstone này biến các yêu cầu đó thành kiến trúc, policy, runbook, diễn tập và bằng chứng có thể review.
