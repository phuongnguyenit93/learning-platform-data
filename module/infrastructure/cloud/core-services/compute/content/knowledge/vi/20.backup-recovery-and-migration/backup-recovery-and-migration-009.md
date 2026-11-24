# Diễn tập khôi phục và đo RPO, RTO thực tế

Backup chỉ có giá trị khi dữ liệu có thể được khôi phục đúng và workload có thể hoạt động trở lại trong khoảng thời gian nghiệp vụ chấp nhận. Một job báo Completed không chứng minh bản backup đầy đủ, khóa mã hóa còn dùng được, ứng dụng tương thích với dữ liệu đã restore hoặc đội vận hành có thể khôi phục trong thời hạn yêu cầu.

**Diễn tập khôi phục (recovery exercise/DR drill)** là hoạt động thực hiện có kế hoạch để kiểm tra quy trình phục hồi dữ liệu, hạ tầng và dịch vụ sau sự cố. Hai chỉ số quan trọng là **RPO (Recovery Point Objective)**, giới hạn lượng dữ liệu có thể mất, và **RTO (Recovery Time Objective)**, giới hạn thời gian gián đoạn có thể chấp nhận. Khi diễn tập, cần đo kết quả thực tế thay vì suy ra từ lịch backup hoặc thông số replication.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, một cuộc diễn tập có thể khôi phục boot disk của VM, phục hồi database đến một thời điểm, dựng lại nhóm instance ở region dự phòng hoặc chuyển traffic sang môi trường standby. Kết quả cần chứng minh dữ liệu nhất quán, ứng dụng hoạt động, dependency được kết nối và RPO/RTO thực tế đáp ứng mục tiêu đã thống nhất.

## 1. Vì sao cần diễn tập khôi phục?

Kế hoạch DR thường mô tả nơi lưu backup, cách tạo VM, cách khôi phục database và cách chuyển DNS. Khi thực hiện thật, nhiều phụ thuộc có thể làm quy trình chậm hoặc thất bại:

- Backup tồn tại nhưng không thể giải mã vì KMS key bị xóa, vô hiệu hóa hoặc thiếu quyền.
- Snapshot được tạo trong khi ứng dụng đang ghi nên dữ liệu giữa các volume không nhất quán.
- Restore hoàn tất nhưng image, driver hoặc phiên bản database không tương thích.
- Region dự phòng không còn quota hoặc capacity cho loại VM cần thiết.
- Subnet thiếu IP, route, firewall hoặc private endpoint chưa được cấu hình.
- Secret, certificate, workload identity hoặc service account không có ở môi trường khôi phục.
- DNS TTL và cache phía client khiến traffic tiếp tục đi đến endpoint cũ.
- Runbook thiếu bước xác minh dữ liệu hoặc thiếu người có quyền thực hiện.
- Thời gian kiểm thử chỉ tính lúc VM boot xong, bỏ qua thời gian khôi phục ứng dụng và kiểm tra nghiệp vụ.

Diễn tập giúp phát hiện những phụ thuộc này khi tổ chức còn chủ động lựa chọn thời gian, phạm vi và dữ liệu thử nghiệm. Nó cũng giúp đo thời gian thực tế cho từng bước để biết cần cải thiện backup, tự động hóa, capacity hay phối hợp vận hành.

## 2. Hiểu đúng RPO và RTO

RPO và RTO là mục tiêu nghiệp vụ được dùng để thiết kế và đánh giá khả năng phục hồi.

### 2.1. RPO: lượng dữ liệu có thể mất

**RPO (Recovery Point Objective)** là khoảng thời gian dữ liệu tối đa mà tổ chức chấp nhận mất khi xảy ra sự cố. RPO 15 phút có nghĩa là sau khi phục hồi, điểm dữ liệu nhất quán gần nhất được phép lùi tối đa 15 phút so với thời điểm sự cố theo định nghĩa đo của tổ chức.

RPO chịu ảnh hưởng bởi:

- Tần suất backup và thời gian hoàn thành backup.
- Độ trễ replication đồng bộ hoặc bất đồng bộ.
- Transaction log/binlog/WAL được lưu và chuyển đến đâu.
- Khả năng point-in-time recovery.
- Tính nhất quán giữa database, file, queue và object.
- Thời điểm dữ liệu cuối cùng được commit bền vững.

Lịch backup mỗi 15 phút không tự động bảo đảm RPO 15 phút. Backup có thể chạy lâu, thất bại, thiếu transaction log hoặc không nhất quán với dữ liệu của hệ thống khác. RPO phải được đo từ điểm phục hồi thực sự có thể sử dụng.

### 2.2. RTO: thời gian khôi phục dịch vụ

**RTO (Recovery Time Objective)** là khoảng thời gian tối đa nghiệp vụ chấp nhận dịch vụ bị gián đoạn trước khi hoạt động trở lại ở mức được xác định.

RTO thực tế có thể gồm:

- Phát hiện và xác nhận sự cố.
- Tuyên bố sự cố và huy động đội ứng cứu.
- Chọn restore point và cấp quyền cần thiết.
- Cấp phát hạ tầng hoặc mở rộng môi trường dự phòng.
- Khôi phục disk, database, file và cấu hình.
- Khởi động workload, kết nối dependency và kiểm tra readiness.
- Chuyển traffic, xác minh nghiệp vụ và thông báo phục hồi.

VM ở trạng thái Running hoặc database báo Online chưa đủ để kết luận dịch vụ đã phục hồi. Phải định nghĩa trước thế nào là “dịch vụ hoạt động trở lại”, ví dụ request nghiệp vụ thành công, dữ liệu nhất quán và capacity đáp ứng mức tải tối thiểu.

### 2.3. Phân biệt mục tiêu và kết quả thực tế

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| RPO target | Mức mất dữ liệu tối đa được phép | 5 phút |
| Actual RPO | Khoảng cách từ thời điểm sự cố đến điểm dữ liệu nhất quán mới nhất có thể phục hồi | 3 phút 20 giây |
| RTO target | Thời gian gián đoạn tối đa được phép | 30 phút |
| Actual RTO | Thời gian từ mốc bắt đầu gián đoạn đến khi dịch vụ đạt tiêu chí phục hồi | 24 phút |

RPO và RTO là hai chỉ số khác nhau. Một hệ thống có thể khôi phục nhanh nhưng mất nhiều dữ liệu; hoặc giữ được dữ liệu mới nhưng cần quá lâu để dựng lại dịch vụ.

### 2.4. Thống nhất mốc bắt đầu và kết thúc

Để các lần diễn tập so sánh được, tổ chức phải định nghĩa mốc thời gian nhất quán:

- Mốc bắt đầu có thể là thời điểm sự cố làm dịch vụ mất khả năng phục vụ hoặc thời điểm được xác nhận theo quy trình BCP/DR. Ghi cả thời điểm sự cố, phát hiện và tuyên bố để không nhầm lẫn.
- Mốc kết thúc RTO là thời điểm dịch vụ đạt lại tiêu chí phục vụ đã định, không chỉ là lúc hạ tầng khởi động xong.
- Mốc tính RPO là thời điểm xảy ra mất dữ liệu hoặc thời điểm sự cố được định nghĩa trong kế hoạch. Điểm phục hồi phải là dữ liệu nhất quán mới nhất đã xác minh.

Nếu một báo cáo chỉ ghi “RTO 12 phút” mà không nói thời gian bắt đầu từ đâu và dịch vụ được coi là phục hồi ở bước nào, kết quả đó không thể dùng để đánh giá đáng tin cậy.

## 3. Xác định mục tiêu từ yêu cầu nghiệp vụ

Không phải workload nào cũng cần RPO/RTO giống nhau. Trước khi chọn chiến lược backup hoặc DR, cần hiểu tác động của gián đoạn.

### 3.1. Business Impact Analysis

Business Impact Analysis (BIA) giúp xác định:

- Dịch vụ nào hỗ trợ hoạt động kinh doanh quan trọng.
- Mức thiệt hại khi dịch vụ ngừng trong 15 phút, 1 giờ hoặc 1 ngày.
- Dữ liệu nào có thể tái tạo và dữ liệu nào không thể mất.
- Thứ tự khôi phục giữa ứng dụng và dependency.
- Thời điểm tải cao hoặc mùa vụ nhạy cảm.
- Yêu cầu pháp lý, lưu trữ và địa điểm dữ liệu.
- Người phê duyệt mức gián đoạn và mất dữ liệu chấp nhận được.

RPO/RTO nên được thống nhất giữa owner nghiệp vụ, đội ứng dụng, hạ tầng, bảo mật và vận hành.

### 3.2. Phân tầng workload

Ví dụ cách phân nhóm:

| Tier | Ví dụ workload | RPO mục tiêu minh họa | RTO mục tiêu minh họa |
| --- | --- | ---: | ---: |
| Tier 0 | Dịch vụ giao dịch cốt lõi | 0–1 phút | 5–15 phút |
| Tier 1 | API và ứng dụng quan trọng | 5 phút | 30 phút |
| Tier 2 | Báo cáo hoặc xử lý nội bộ | 1 giờ | 4 giờ |
| Tier 3 | Dev/test hoặc dữ liệu có thể tái tạo | 24 giờ | 1 ngày |

Đây là ví dụ phân tầng, không phải chuẩn bắt buộc. Mục tiêu càng ngắn thường đòi hỏi replication, standby capacity, tự động hóa và chi phí cao hơn.

### 3.3. Dependency map và thứ tự khôi phục

Ứng dụng thường phụ thuộc nhiều thành phần. Ví dụ:

~~~mermaid
flowchart TD
    A["DNS / Traffic entry"] --> B["Load balancer"]
    B --> C["Compute fleet"]
    C --> D["Application configuration and secrets"]
    C --> E["Database"]
    C --> F["Cache"]
    C --> G["Message queue"]
    E --> H["Backup / transaction logs"]
    G --> I["Consumer workers"]
~~~

Khi lập thứ tự phục hồi, cần xác định dependency nào phải có trước:

1. Network, DNS nội bộ, identity và key management.
2. Storage, database hoặc message broker.
3. Secret/configuration và workload compute.
4. Load balancer, routing và DNS công khai.
5. Kiểm tra nghiệp vụ, tích hợp và traffic bình thường.

Thứ tự cụ thể phụ thuộc kiến trúc. Ví dụ database có thể được phục hồi song song với network và compute image, nhưng ứng dụng không nên nhận traffic trước khi dữ liệu và quyền truy cập đã sẵn sàng.

## 4. Chọn chiến lược khôi phục phù hợp

Chiến lược DR là cách tổ chức duy trì bản sao dữ liệu, hạ tầng và capacity ở nơi có thể khôi phục.

| Chiến lược | Cách hoạt động | RPO/RTO tương đối | Chi phí và đánh đổi |
| --- | --- | --- | --- |
| Backup and restore | Lưu backup; khi sự cố mới cấp hạ tầng và restore | Thường cao hơn | Chi phí thấp hơn, thời gian khôi phục dài |
| Pilot light | Duy trì các thành phần dữ liệu hoặc nền tảng tối thiểu; mở rộng compute khi cần | Trung bình | Có sẵn một phần dependency, cần tự động hóa scale-up |
| Warm standby | Môi trường dự phòng chạy ở capacity thấp hơn production | Thấp đến trung bình | Tốn chi phí duy trì standby, cần tăng capacity và chuyển traffic |
| Hot standby/active-passive | Môi trường dự phòng gần sẵn sàng, dữ liệu được replicate thường xuyên | Thấp | Chi phí cao hơn, cần kiểm soát replication và failover |
| Active-active | Nhiều site cùng phục vụ traffic | Có thể rất thấp | Kiến trúc phức tạp, xử lý consistency và conflict khó hơn |

Không có chiến lược tốt nhất cho mọi ứng dụng. Chọn theo BIA, RPO/RTO, tính nhất quán dữ liệu, năng lực đội vận hành và ngân sách.

### 4.1. Backup and restore

Phù hợp khi workload chấp nhận thời gian khôi phục dài hơn và có thể tạo lại compute từ image/IaC. Cần bảo đảm backup nằm ngoài failure domain của nguồn, có retention và có thể restore vào môi trường độc lập.

### 4.2. Pilot light

Giữ sẵn dữ liệu và các thành phần nền tảng thiết yếu ở site dự phòng. Khi có sự cố, hệ thống tạo compute, mở rộng capacity, kết nối và chuyển traffic. RTO phụ thuộc thời gian provision và cấu hình.

### 4.3. Warm standby

Site dự phòng có một phiên bản workload đang chạy ở capacity thấp. Khi cần, tăng số VM hoặc tài nguyên, kiểm tra readiness và chuyển traffic. Phải xác minh quota và capacity thực tế ở region dự phòng.

### 4.4. Hot standby và active-active

Hot standby có thể chuyển traffic nhanh hơn nhưng cần đồng bộ dữ liệu, kiểm soát split-brain và tránh cả hai site cùng nhận ghi ngoài dự kiến. Active-active cần chiến lược phân vùng dữ liệu, conflict resolution, idempotency và quan sát liên vùng.

## 5. Các loại diễn tập khôi phục

Diễn tập có thể bắt đầu từ kiểm tra runbook đơn giản rồi tăng dần đến phục hồi toàn dịch vụ.

| Loại diễn tập | Cách thực hiện | Điều kiểm chứng |
| --- | --- | --- |
| Tabletop | Thảo luận tình huống và quyết định trên giấy | Vai trò, liên lạc, quyết định và runbook |
| Walkthrough | Đi qua từng bước kỹ thuật mà chưa gây outage | Tính đầy đủ của lệnh, quyền và dependency |
| Backup restore test | Restore bản backup vào môi trường cô lập | Khả năng đọc backup và tính toàn vẹn dữ liệu |
| Component recovery | Khôi phục một VM, volume hoặc database | Thời gian và tính đúng của từng thành phần |
| Partial failover | Chuyển một phần workload/traffic sang site dự phòng | Routing, capacity và application behavior |
| Full DR exercise | Khôi phục hoặc chuyển toàn bộ dịch vụ trong phạm vi đã định | RTO/RPO end-to-end |
| Unannounced exercise | Thông báo trước trong phạm vi tổ chức nhưng không báo chi tiết thời điểm cho người trực | Khả năng phát hiện, phối hợp và runbook |

Unannounced exercise cần được quản trị cẩn thận, có người điều phối và điều kiện dừng. Không gây sự cố bất ngờ cho người dùng hoặc đội vận hành ngoài phạm vi đã thống nhất.

## 6. Chuẩn bị một cuộc diễn tập

### 6.1. Xác định mục tiêu và phạm vi

Ghi rõ:

- Dịch vụ và môi trường được thử.
- Failure scenario: mất VM, mất disk, database corruption, region outage hay lỗi cấu hình.
- Restore point dự kiến và nguồn backup/replica.
- RPO/RTO target.
- Người chỉ huy, người thực hiện, người quan sát và người phê duyệt.
- Phạm vi người dùng/traffic bị ảnh hưởng.
- Những tài nguyên nằm ngoài phạm vi.

### 6.2. Chọn môi trường khôi phục an toàn

Ưu tiên restore vào account/project/subscription hoặc VPC/VNet riêng. Dùng tên, tag và DNS riêng để không ghi đè production hoặc nhận traffic thật ngoài ý muốn.

Nếu cần kiểm tra failover production, phải có kế hoạch traffic routing, thông báo, phê duyệt và rollback riêng. Một bài restore backup trong sandbox không tự chứng minh toàn bộ quy trình production failover đã hoạt động.

### 6.3. Kiểm tra điều kiện tiên quyết

- Backup hoặc snapshot có trạng thái hoàn tất và đúng retention.
- Có transaction log/binlog/WAL cần thiết cho point-in-time recovery.
- KMS key, certificate, secret và quyền giải mã còn sẵn sàng.
- Image, template, IaC và artifact còn truy cập được.
- Quota, IP address, disk capacity và instance capacity đủ ở nơi khôi phục.
- Network, DNS, route, firewall và private endpoint có thể dựng lại.
- Có tài khoản break-glass theo chính sách và audit.
- Monitoring, logging, tracing và kênh liên lạc hoạt động.
- Có runbook và bản sao offline/ngoài môi trường bị ảnh hưởng.

### 6.4. Bảo toàn bằng chứng và dữ liệu

Trước khi thử:

1. Ghi nhận timestamp đồng bộ từ các hệ thống liên quan.
2. Chụp snapshot/backup theo kế hoạch nếu thử nghiệm có thể ghi hoặc thay đổi dữ liệu.
3. Tạo bộ transaction ID hoặc dữ liệu tổng hợp để xác minh.
4. Ghi lại backup ID, snapshot ID, LSN/SCN/binlog position hoặc timestamp tương ứng.
5. Xác nhận môi trường restore không kết nối nhầm endpoint production.

Đồng bộ thời gian giữa VM, database, logging và orchestration là điều kiện quan trọng để đo RPO/RTO chính xác.

## 7. Quy trình diễn tập khôi phục end-to-end

~~~mermaid
flowchart TD
    A["Xác định sự cố và tuyên bố DR"] --> B["Chọn restore point và recovery site"]
    B --> C["Cấp network, identity, key và capacity"]
    C --> D["Restore storage/database"]
    D --> E["Khởi động compute và dependency"]
    E --> F["Kiểm tra dữ liệu và application readiness"]
    F --> G{"Đạt RPO, integrity và readiness?"}
    G -- "Không" --> H["Dừng chuyển traffic, điều tra hoặc chọn restore point khác"]
    G -- "Có" --> I["Chuyển traffic theo kế hoạch"]
    I --> J["Kiểm tra nghiệp vụ và quan sát SLO"]
    J --> K["Ghi thời điểm phục hồi và kết thúc DR"]
    K --> L["Cleanup, failback plan và báo cáo"]
~~~

Quy trình tổng quát:

1. Ghi thời điểm bắt đầu sự cố hoặc mốc đo đã thống nhất.
2. Xác nhận sự cố và quyết định kích hoạt kế hoạch DR.
3. Chọn site và restore point phù hợp.
4. Cấp phát network, identity, key, compute và storage.
5. Khôi phục database, file, object và các dependency.
6. Khởi động ứng dụng và kiểm tra readiness.
7. Kiểm tra dữ liệu, transaction và quyền truy cập.
8. Chuyển traffic hoặc mở môi trường phục vụ.
9. Chạy kiểm tra nghiệp vụ và theo dõi SLO.
10. Ghi mốc kết thúc RTO, actual RPO và mọi thao tác thủ công.
11. Cleanup tài nguyên thử nghiệm và lập kế hoạch failback nếu cần.

Trong diễn tập, có thể dừng ở bước restore và kiểm tra trong môi trường cô lập. Nếu không chuyển traffic, báo cáo cần ghi rõ RTO end-to-end chưa được đo đầy đủ.

## 8. Khôi phục VM và compute infrastructure

Với workload VM, cần kiểm tra cả image, boot disk, data disk, network và bootstrap.

### 8.1. Khôi phục từ image và snapshot

Một trình tự thường gặp:

1. Chọn image/template revision đã biết hoạt động.
2. Tạo boot disk từ snapshot hoặc image phù hợp.
3. Khôi phục data volume theo đúng điểm dữ liệu.
4. Gắn volume với VM theo device mapping dự kiến.
5. Áp dụng network, security group/firewall và identity.
6. Khởi động VM và kiểm tra boot/guest agent.
7. Mount filesystem và xác minh dữ liệu.
8. Khởi động service, kiểm tra readiness và log.

Nếu boot disk và data disk được snapshot ở các thời điểm khác nhau, cần kiểm tra tính nhất quán giữa chúng. Với database, ưu tiên cơ chế backup/restore có hỗ trợ application consistency hoặc transaction log.

### 8.2. Khôi phục nhóm instance

Nếu dùng managed instance group hoặc scale set:

- Tạo lại group từ template version đã xác minh.
- Xác minh desired/min/max capacity và zone distribution.
- Kiểm tra image, identity, startup script và secret access.
- Chờ instance healthy trước khi đưa vào load balancer.
- Kiểm tra autoscaling policy không tạo quá nhiều VM trong quá trình phục hồi.
- So sánh cấu hình thực tế với baseline/IaC.

Một group có thể đạt đúng số lượng VM nhưng tất cả instance vẫn unhealthy do lỗi chung trong image hoặc bootstrap. Cần kiểm tra healthy capacity và application readiness.

### 8.3. Khôi phục network và traffic

Kiểm tra:

- VPC/VNet, subnet và route table.
- Firewall/security group và network ACL.
- NAT, gateway, private endpoint và peering.
- DNS zone, record, TTL và resolver.
- Load balancer, target group/backend pool và health probe.
- Certificate, TLS termination và identity path.

Không chuyển DNS hoặc public traffic trước khi môi trường mới vượt qua smoke test và kiểm tra dữ liệu. Nếu dùng DNS failover, cần tính đến TTL và cache của resolver/client.

## 9. Khôi phục database và dữ liệu

Database thường là thành phần quyết định RPO. Cần đo điểm phục hồi thực tế dựa trên dữ liệu có thể truy vấn và kiểm chứng.

### 9.1. Full backup, incremental và transaction log

- **Full backup:** bản sao đầy đủ tại một thời điểm.
- **Incremental/differential backup:** phần thay đổi kể từ một mốc backup.
- **Transaction log:** log cho phép phát lại thay đổi sau backup để đạt điểm phục hồi gần hơn.
- **Point-in-time recovery (PITR):** phục hồi database đến một thời điểm hoặc log position cụ thể.

Chuỗi backup chỉ sử dụng được nếu có đầy đủ các thành phần phụ thuộc. Thiếu một incremental hoặc log segment có thể khiến không thể phục hồi đến điểm mong muốn.

### 9.2. Xác định restore point

Trước khi restore:

1. Xác định thời điểm sự cố và khoảng dữ liệu cần giữ.
2. Liệt kê full backup, incremental/differential và transaction log sẵn có.
3. Kiểm tra tính liên tục của log sequence/position.
4. Chọn restore point nhất quán trước sự cố hoặc trước thời điểm corruption.
5. Ghi lại timestamp/log position của điểm phục hồi.
6. Restore vào database độc lập và xác minh dữ liệu.

Nếu sự cố do thao tác xóa nhầm hoặc corruption được replicate sang replica, không chọn replica mới nhất một cách máy móc. Có thể cần PITR về thời điểm trước khi dữ liệu bị hỏng.

### 9.3. Xác minh tính toàn vẹn

Không chỉ dựa vào việc database khởi động. Kiểm tra:

- Schema, table, index và constraint cần thiết.
- Record count hoặc aggregate quan trọng.
- Checksum/hash của dataset thử nghiệm.
- Transaction ID cuối cùng đã commit.
- Referential integrity và dữ liệu liên bảng.
- Sequence, identity và counter.
- Permission, role, stored procedure và extension.
- Ứng dụng đọc/ghi được bằng danh tính dự kiến.

Với dữ liệu lớn, có thể dùng checksum theo partition hoặc mẫu kiểm tra được thiết kế trước. Cần phân biệt dữ liệu thiếu do RPO với dữ liệu bị sai hoặc không nhất quán do restore lỗi.

### 9.4. Message queue và dữ liệu bất đồng bộ

Nếu workload dùng queue/event stream, cần xác định:

- Message đã được publish nhưng chưa được consumer xử lý.
- Message đang xử lý tại thời điểm sự cố.
- Offset/acknowledgement cuối cùng đã commit.
- Chính sách redelivery và dead-letter.
- Cách tránh duplicate bằng idempotency key.
- Thứ tự xử lý và khả năng replay.

Khôi phục database mà không khôi phục offset hoặc queue state phù hợp có thể làm mất hoặc xử lý lặp message. Diễn tập phải kiểm tra cả hai phía.

## 10. Đo actual RPO

Actual RPO không nên lấy từ tần suất backup cấu hình. Cần tìm điểm dữ liệu mới nhất có thể phục hồi và xác minh.

### 10.1. Cách đo

1. Ghi timestamp của sự cố theo đồng hồ chuẩn.
2. Xác định restore point thực tế được dùng.
3. Khôi phục dữ liệu vào môi trường cô lập.
4. Xác định timestamp hoặc log position của transaction cuối cùng đã commit và có thể đọc được.
5. Kiểm tra transaction đó cùng các thay đổi trước nó có nhất quán không.
6. Tính khoảng cách giữa thời điểm sự cố và timestamp của điểm dữ liệu đó.

Công thức khái niệm:

\[
\text{Actual RPO} = T_{\text{incident}} - T_{\text{latest consistent recovery point}}
\]

Nếu sự cố xảy ra lúc 10:00:00 và điểm phục hồi nhất quán mới nhất là 09:56:40, actual RPO là 3 phút 20 giây.

### 10.2. Ví dụ đánh giá RPO

Giả sử mục tiêu RPO là 5 phút:

| Dữ liệu | Thời điểm |
| --- | --- |
| Sự cố bắt đầu | 10:00:00 |
| Backup gần nhất hoàn tất | 09:50:00 |
| Transaction log mới nhất có thể phục hồi | 09:56:40 |
| Điểm dữ liệu nhất quán sau kiểm tra | 09:56:40 |
| Actual RPO | 3 phút 20 giây |

Trong ví dụ này RPO đạt vì actual RPO nhỏ hơn target 5 phút. Backup gần nhất chỉ cách sự cố 10 phút, nhưng transaction log giúp phục hồi gần hơn.

Nếu log bị thiếu hoặc không thể replay, restore point thực tế có thể lùi về 09:50:00 và actual RPO trở thành 10 phút, không đạt mục tiêu.

### 10.3. Những điểm cần chú ý khi đo RPO

- Đồng hồ giữa database, backup service và workload phải được đồng bộ.
- Timestamp của backup job không đồng nghĩa timestamp của dữ liệu cuối cùng.
- Replication lag cần đo tại thời điểm sự cố và xác minh sau restore.
- Snapshot crash-consistent có thể cần recovery log trước khi dữ liệu sử dụng được.
- Dữ liệu từ nhiều database hoặc queue cần có điểm nhất quán chung nếu giao dịch đi qua nhiều hệ thống.
- Ghi nhận cả transaction đã xác nhận với client nhưng chưa được replicate bền vững.

## 11. Đo actual RTO

Actual RTO phải bao gồm các bước cần thiết để nghiệp vụ sử dụng lại dịch vụ.

### 11.1. Chia nhỏ thời gian phục hồi

| Thành phần thời gian | Nội dung |
| --- | --- |
| Detection | Từ lúc sự cố đến khi được phát hiện |
| Declaration | Xác nhận và kích hoạt DR |
| Provisioning | Cấp network, VM, disk, identity và key |
| Data recovery | Restore backup, log, volume hoặc database |
| Application startup | Khởi động service, cấu hình và dependency |
| Traffic cutover | Chuyển load balancer, route hoặc DNS |
| Validation | Kiểm tra dữ liệu và nghiệp vụ |

Tổng thời gian có thể có các bước chạy song song. Khi báo cáo, dùng timeline thực tế thay vì cộng máy móc các thời lượng nếu chúng overlap.

### 11.2. Công thức và ví dụ

\[
\text{Actual RTO} = T_{\text{service restored}} - T_{\text{disruption start}}
\]

Ví dụ:

| Mốc | Thời điểm | Thời lượng cộng dồn |
| --- | --- | ---: |
| Dịch vụ bị gián đoạn | 10:00 | 0 phút |
| Alert được xác nhận | 10:03 | 3 phút |
| Kích hoạt DR | 10:05 | 5 phút |
| Recovery environment sẵn sàng | 10:10 | 10 phút |
| Database restore hoàn tất | 10:17 | 17 phút |
| Application readiness đạt | 10:20 | 20 phút |
| Traffic chuyển và smoke test đạt | 10:24 | 24 phút |

Nếu RTO target là 30 phút, actual RTO 24 phút đạt mục tiêu. Nếu chỉ tính đến lúc database restore xong ở phút 17, báo cáo sẽ đánh giá thiếu thời gian cần để dịch vụ thật sự hoạt động.

### 11.3. Tìm bước chiếm nhiều thời gian

Phân tích timeline để biết bottleneck:

- Chờ người có quyền phê duyệt hoặc truy cập account.
- Cấp phát VM do quota/capacity.
- Tải image hoặc artifact quá lớn.
- Restore volume/database mất nhiều thời gian.
- Thiếu script tự động dựng network và identity.
- Startup script phụ thuộc endpoint không truy cập được.
- DNS TTL hoặc cache khiến cutover chậm.
- Smoke test và xác minh dữ liệu làm thủ công.

Ưu tiên tự động hóa hoặc chuẩn bị trước bước chiếm nhiều thời gian nhất. Tối ưu một bước nhỏ không làm giảm đáng kể RTO tổng thể nếu bottleneck nằm ở bước khác.

## 12. Ví dụ diễn tập đầy đủ và đánh giá kết quả

Một dịch vụ xử lý đơn hàng chạy trên VM ở region chính, database có backup định kỳ và transaction log được lưu sang region dự phòng. Warm standby có sẵn network, identity và một số VM nhưng chưa chạy đủ capacity.

Mục tiêu đã thống nhất:

- RPO không quá 5 phút.
- RTO không quá 30 phút.
- Không mất transaction đã được xác nhận ngoài giới hạn RPO.
- Môi trường khôi phục phải xử lý được smoke test và một giao dịch tổng hợp.

### 12.1. Kịch bản

Giả lập region chính không còn phục vụ được. Đội DR khôi phục database ở region dự phòng đến điểm nhất quán gần nhất, tăng compute capacity, kiểm tra dependency và chuyển traffic thử nghiệm sang endpoint mới.

### 12.2. Timeline minh họa

| Mốc | Thời điểm |
| --- | --- |
| T0: dịch vụ bị gián đoạn | 10:00 |
| T1: alert xác nhận | 10:02 |
| T2: DR được tuyên bố | 10:04 |
| T3: network/identity standby sẵn sàng | 10:08 |
| T4: database restore hoàn tất | 10:16 |
| T5: application healthy | 10:20 |
| T6: traffic chuyển và smoke test đạt | 10:24 |
| T7: dữ liệu được đối chiếu xong | 10:27 |

Actual RTO được đo đến T6 là 24 phút nếu tiêu chí dịch vụ phục hồi bao gồm traffic và smoke test. T7 là thời điểm hoàn tất xác minh dữ liệu; tổ chức có thể ghi thêm “recovery validation time” là 27 phút.

Nếu điểm dữ liệu nhất quán mới nhất là 09:57:30, actual RPO là 2 phút 30 giây. RPO đạt mục tiêu 5 phút; RTO đạt mục tiêu 30 phút.

### 12.3. Bài học có thể rút ra

Giả sử database restore mất 8 phút trong tổng thời gian 24 phút, còn chờ phê duyệt và dựng network mất 6 phút. Tối ưu restore thêm 2 phút chỉ giảm RTO 2 phút; tự động hóa quyền và network có thể tiết kiệm nhiều hơn. Báo cáo nên nêu rõ các bước này và hành động cải thiện tương ứng.

## 13. Diễn tập failback và quay lại môi trường chính

Failover chuyển dịch vụ sang môi trường dự phòng. **Failback** là quá trình chuyển trở lại môi trường chính hoặc môi trường được chỉ định sau khi sự cố kết thúc.

Failback có thể nguy hiểm nếu hai site cùng nhận ghi:

- Database ở site dự phòng đã nhận transaction mới.
- Site chính được khôi phục từ backup cũ hơn.
- Replication direction chưa được đổi đúng.
- DNS/load balancer còn gửi một phần traffic đến site cũ.
- Queue consumer ở hai site cùng xử lý message.

Trước failback cần:

1. Xác định site nào đang là nguồn dữ liệu có thẩm quyền.
2. Dừng hoặc kiểm soát ghi ở site cũ theo kế hoạch.
3. Đồng bộ dữ liệu phát sinh trong thời gian DR.
4. Kiểm tra replication lag và consistency.
5. Chuyển vai trò primary/replica theo đúng thứ tự.
6. Chuyển traffic theo từng bước và quan sát.
7. Kiểm tra transaction, queue, DNS và health sau chuyển đổi.
8. Chỉ giải phóng tài nguyên DR sau khi owner xác nhận ổn định.

Một diễn tập DR đầy đủ nên xác định cả failback plan, kể cả khi không thực hiện failback trong cùng một cửa sổ thử nghiệm.

## 14. An toàn dữ liệu và bảo mật trong quá trình restore

Backup có thể chứa dữ liệu nhạy cảm, credential hoặc thông tin cá nhân. Môi trường restore cần được bảo vệ như production.

- Chỉ cấp quyền restore cho danh tính được phê duyệt.
- Giữ mã hóa khi truyền và khi lưu.
- Bảo đảm KMS key và quyền giải mã ở site khôi phục.
- Dùng mạng riêng và giới hạn endpoint.
- Không mở public access chỉ để kiểm tra nhanh.
- Xóa hoặc ẩn danh dữ liệu khi chỉ cần kiểm thử cấu trúc.
- Không ghi secret vào log, script hoặc ticket.
- Theo dõi audit log của thao tác restore và truy cập dữ liệu.
- Áp dụng retention và cleanup cho bản restore thử nghiệm.
- Kiểm tra certificate, secret rotation và workload identity sau khi dựng lại.

Một restore thành công về kỹ thuật nhưng để lộ backup hoặc tạo endpoint công khai không kiểm soát vẫn là một cuộc diễn tập thất bại về mặt bảo mật.

## 15. Công cụ hỗ trợ diễn tập

Có thể kết hợp công cụ backup/restore, IaC, database-native recovery, monitoring và automation.

| Nhóm công cụ | Mục đích |
| --- | --- |
| Snapshot/backup service của cloud | Tạo và khôi phục disk, volume hoặc VM image |
| Database-native backup/PITR | Phục hồi database và transaction log đến điểm xác định |
| Infrastructure as Code | Dựng lại network, VM, security policy và dependency |
| Configuration management | Cấu hình OS, package, agent và service |
| Orchestration/pipeline | Điều phối các bước restore và kiểm tra theo thứ tự |
| Monitoring/APM/logging | Ghi timeline, readiness, latency, error và recovery signals |
| Data validation scripts | Đối chiếu checksum, record count, transaction ID và nghiệp vụ |
| DNS/load balancer automation | Chuyển traffic có kiểm soát |

Không nên phụ thuộc vào một công cụ duy nhất. Runbook cần nêu rõ cách thực hiện khi automation hoặc control plane chính không khả dụng.

## 16. Mẫu báo cáo diễn tập

Một báo cáo nên cho phép người khác hiểu chính xác điều gì đã được thử và kết quả có đạt hay không.

| Trường | Nội dung |
| --- | --- |
| Exercise ID | Mã diễn tập, ngày giờ và phiên bản runbook |
| Service/tier | Dịch vụ, owner và mức độ quan trọng |
| Scenario | Loại sự cố và failure domain |
| Recovery strategy | Backup/restore, pilot light, warm standby hoặc hot standby |
| Restore source | Backup ID, snapshot ID, log position hoặc replica |
| RPO target / actual | Mục tiêu và khoảng cách dữ liệu đo được |
| RTO target / actual | Mục tiêu và thời gian phục hồi đo được |
| Timeline | T0 đến các mốc detection, declaration, restore, validation, traffic |
| Data validation | Checksum, record count, transaction ID và kết quả |
| Capacity validation | VM healthy, network, storage và dependency |
| Security validation | IAM, KMS, secret, certificate và audit |
| Findings | Bottleneck, sai lệch và nguyên nhân |
| Action items | Owner, priority, due date và tiêu chí retest |

Nên đính kèm timeline, dashboard, log, restore point và bằng chứng kiểm tra dữ liệu. Tránh ghi credential, dữ liệu nhạy cảm hoặc bản sao backup vào báo cáo.

## 17. Những sai lầm thường gặp

- Coi backup job thành công là bằng chứng có thể restore.
- Đo RPO bằng lịch backup mà không kiểm tra điểm dữ liệu thực tế.
- Đo RTO đến lúc VM chạy thay vì lúc ứng dụng phục vụ và kiểm tra nghiệp vụ đạt.
- Không thống nhất mốc bắt đầu/kết thúc RTO.
- Restore database nhưng quên transaction log, queue offset hoặc file liên quan.
- Chọn restore point mới nhất dù nó đã chứa dữ liệu bị corruption.
- Không kiểm tra KMS key, identity, certificate và secret ở region dự phòng.
- Không kiểm tra quota, IP, capacity và dependency ở recovery site.
- Chuyển traffic trước khi kiểm tra dữ liệu và readiness.
- Không tính DNS TTL, cache resolver và connection draining.
- Bỏ qua failback và nguy cơ split-brain.
- Không cleanup bản restore, disk, VM hoặc endpoint thử nghiệm.
- Không có owner và deadline cho finding sau diễn tập.
- Không retest sau khi thay đổi runbook hoặc automation.

## 18. Checklist trước, trong và sau diễn tập

**Trước diễn tập**

- [ ] BIA và RPO/RTO target đã được owner xác nhận.
- [ ] Kịch bản, phạm vi, người phụ trách và thời gian đã rõ.
- [ ] Backup, snapshot và transaction log được xác minh.
- [ ] Recovery site có quota, network, identity, key và capacity.
- [ ] Có môi trường cô lập và endpoint riêng cho restore.
- [ ] Runbook, rollback và failback plan sẵn sàng.
- [ ] Đồng hồ và timestamp giữa các hệ thống được đồng bộ.
- [ ] Có dữ liệu thử và tiêu chí kiểm tra integrity.

**Trong diễn tập**

- [ ] Ghi T0, detection, declaration và từng mốc recovery.
- [ ] Ghi backup ID, restore point và log position.
- [ ] Theo dõi provisioning, restore, startup và traffic cutover.
- [ ] Xác minh quyền, network, secret và certificate.
- [ ] Kiểm tra transaction, checksum, record và queue.
- [ ] Không chuyển traffic khi readiness hoặc integrity chưa đạt.

**Sau diễn tập**

- [ ] Tính actual RPO và actual RTO theo định nghĩa thống nhất.
- [ ] Đối chiếu kết quả với target và xác định pass/fail.
- [ ] Ghi bottleneck và nguyên nhân gốc.
- [ ] Cleanup tài nguyên và dữ liệu thử nghiệm theo chính sách.
- [ ] Giao owner/deadline cho từng hành động.
- [ ] Cập nhật runbook, automation và BIA nếu cần.
- [ ] Lên lịch retest sau khắc phục.

## 19. Quy trình xây dựng chương trình diễn tập định kỳ

1. **Phân loại dịch vụ:** xác định tier, BIA, dependency và owner.
2. **Đặt RPO/RTO:** thống nhất mục tiêu theo tác động nghiệp vụ.
3. **Chọn chiến lược:** backup/restore, pilot light, warm standby hoặc active-active.
4. **Kiểm tra backup:** xác minh tính đầy đủ, retention, encryption và restore point.
5. **Tự động hóa recovery:** quản lý network, compute, identity và data bằng script/IaC có kiểm soát.
6. **Diễn tập từng thành phần:** restore disk, database, file và message queue.
7. **Diễn tập end-to-end:** khôi phục ứng dụng và chuyển traffic trong phạm vi cho phép.
8. **Đo actual RPO/RTO:** dùng timestamp, log position và kiểm tra dữ liệu.
9. **Cải thiện:** xử lý bottleneck và cập nhật runbook.
10. **Retest và báo cáo:** chứng minh thay đổi đạt mục tiêu và lưu bằng chứng.

Tần suất diễn tập nên dựa trên mức độ quan trọng, tốc độ thay đổi hệ thống, yêu cầu pháp lý và rủi ro. Dịch vụ quan trọng cần kiểm tra thường xuyên hơn; thay đổi lớn ở database, network, identity hoặc backup pipeline cũng là lý do để diễn tập lại.

## 20. Nguyên tắc cần ghi nhớ

1. Backup chỉ đáng tin khi có thể restore và dữ liệu được xác minh.
2. RPO đo khoảng cách đến điểm dữ liệu nhất quán mới nhất có thể phục hồi.
3. RTO đo thời gian đến khi dịch vụ đạt tiêu chí phục vụ, không chỉ đến khi VM/database khởi động.
4. Thống nhất mốc thời gian và định nghĩa phục hồi trước khi diễn tập.
5. Dùng BIA và dependency map để chọn tier, thứ tự khôi phục và mục tiêu phù hợp.
6. Khôi phục phải bao gồm compute, storage, network, identity, secret và traffic.
7. Kiểm tra transaction, queue, replica và dữ liệu liên hệ thống để phát hiện mất hoặc nhân đôi.
8. Đo riêng failover, restore và failback; không giả định một bước thành công nghĩa là toàn quy trình thành công.
9. Diễn tập trong môi trường cô lập, có guardrails và cleanup.
10. Mọi khoảng cách so với RPO/RTO phải trở thành hành động có owner và được retest.

Diễn tập khôi phục biến kế hoạch DR thành năng lực có thể đo. Khi tổ chức khôi phục dữ liệu thật trong môi trường kiểm soát, xác minh workload và đo RPO/RTO bằng timestamp cùng bằng chứng nhất quán, tổ chức biết được mức phục hồi thực tế, bước nào đang làm chậm dịch vụ và cần đầu tư vào backup, replication hay tự động hóa ở đâu.
