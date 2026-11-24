# Sao chép image và dữ liệu để khôi phục ở region khác

Khi một region của cloud gặp sự cố diện rộng, workload có thể không truy cập được dù các VM và ứng dụng ở region đó chưa bị hỏng. Để tiếp tục cung cấp dịch vụ, tổ chức cần có khả năng khởi tạo compute ở region dự phòng, kết nối đến dữ liệu có thể phục hồi và chuyển người dùng sang môi trường mới. Việc này đòi hỏi chuẩn bị cả **machine image**, **dữ liệu**, **cấu hình hạ tầng**, **danh tính**, **khóa mã hóa** và **quy trình chuyển vùng**.

Sao chép image sang region khác giúp tạo VM có hệ điều hành, runtime và phần mềm nền tương đương. Nhưng image không nhất thiết chứa dữ liệu mới nhất của ứng dụng, database hoặc file người dùng. Vì vậy, DR đa region phải phối hợp image với backup, replication và kiểm thử phục hồi dữ liệu. Một image khởi động thành công vẫn chưa chứng minh ứng dụng có thể phục vụ giao dịch đúng.

Trong phạm vi CLOUD_CORE_SERVICES_COMPUTE, bài học tập trung vào khả năng khôi phục workload compute ở region khác: tạo bản image có thể dùng ở nơi dự phòng, chuyển dữ liệu đến đó theo mục tiêu RPO/RTO, tái tạo network và identity, rồi thực hiện failover và failback có kiểm soát.

Sau bài học, bạn có thể:

- Phân biệt machine image, snapshot, backup dữ liệu và replication.
- Lập kế hoạch sao chép image và các thành phần phụ thuộc sang region dự phòng.
- Chọn phương pháp bảo vệ dữ liệu phù hợp với RPO, RTO và consistency.
- Xác minh encryption key, IAM, network, quota, license và dependency ở region đích.
- Xây dựng trình tự restore, failover và failback.
- Kiểm thử khả năng khởi động VM và tính toàn vẹn nghiệp vụ sau phục hồi.

## 1. DR đa region và mục tiêu phục hồi

Disaster Recovery (DR) là tập hợp kiến trúc, dữ liệu, quy trình và năng lực vận hành giúp khôi phục dịch vụ sau sự cố nghiêm trọng. Với cloud, region dự phòng là một khu vực địa lý độc lập có thể chứa compute, storage, network và các dịch vụ cần thiết để chạy workload.

### RPO và RTO

Hai mục tiêu cơ bản:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, thường biểu diễn bằng khoảng thời gian từ thời điểm sự cố đến điểm dữ liệu có thể phục hồi.
- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để khôi phục dịch vụ về mức hoạt động được chấp nhận.

Ví dụ, một dịch vụ đặt RPO 5 phút và RTO 60 phút. Điều đó có nghĩa điểm dữ liệu khôi phục không được cũ hơn 5 phút theo mục tiêu đã định, và dịch vụ cần trở lại trạng thái phục vụ trong vòng 60 phút sau khi bắt đầu sự cố theo cách đo của tổ chức.

RPO/RTO là mục tiêu cần thiết kế và kiểm chứng, không phải bảo đảm tự động của nhà cung cấp. Nếu dùng snapshot mỗi 24 giờ, không thể tuyên bố RPO 5 phút cho dữ liệu chỉ được bảo vệ bằng snapshot đó. Nếu cần dựng mạng, xin quota, cấp key, restore database và kiểm thử ứng dụng trong 3 giờ, không thể đặt RTO 60 phút nếu chưa tự động hóa hoặc chuẩn bị trước các bước đó.

### Ví dụ phân loại mục tiêu

| Loại workload | RPO minh họa | RTO minh họa | Chiến lược có thể phù hợp |
|---|---:|---:|---|
| Môi trường dev/test | 24 giờ | 1 ngày | Backup định kỳ, image copy khi cần |
| API nội bộ ít quan trọng | 1 giờ | 4 giờ | Backup/replication định kỳ, warm recovery |
| Dịch vụ giao dịch quan trọng | 5 phút | 1 giờ | Database replication, image sẵn ở region dự phòng, IaC và warm standby |
| Hệ thống yêu cầu liên tục cao | Gần 0 hoặc theo thiết kế | Vài phút | Multi-region active/active hoặc active/passive có replication và failover tự động |

Các con số chỉ là ví dụ để minh họa cách lựa chọn. Mục tiêu thực tế phải dựa trên tác động nghiệp vụ, chi phí, khả năng dịch vụ và kết quả diễn tập.

## 2. Phân biệt image, snapshot, backup và replication

Các khái niệm này liên quan nhưng không thay thế nhau.

| Thành phần | Nội dung thường chứa | Mục đích | Điều không nên giả định |
|---|---|---|---|
| Machine image | OS, boot volume, phần mềm, cấu hình nền và metadata khởi tạo VM | Tạo VM mới có baseline tương tự | Không mặc định chứa dữ liệu ứng dụng mới nhất hoặc mọi disk đã gắn |
| Disk snapshot | Trạng thái block storage tại một thời điểm | Tạo disk mới hoặc phục hồi volume | Snapshot đơn lẻ có thể không nhất quán với database đang ghi |
| Application/database backup | Dữ liệu logic hoặc bản sao nhất quán theo cơ chế ứng dụng | Phục hồi dữ liệu và giao dịch | Không tự tạo network, compute, identity hoặc endpoint |
| Replication | Thay đổi dữ liệu được chuyển sang bản sao ở nơi khác | Giảm độ trễ điểm phục hồi | Replication có thể sao chép cả thao tác xóa hoặc corruption |
| Infrastructure as Code | Mô tả VM, network, role, load balancer và policy | Tái tạo môi trường | Không chứa dữ liệu runtime trừ khi được thiết kế riêng |
| Configuration/secret backup | Cấu hình, tham số và secret theo chính sách | Cấu hình lại ứng dụng an toàn | Không nên xuất secret thành bản rõ trong repository hoặc image |

Một kế hoạch DR hoàn chỉnh thường dùng nhiều cơ chế cùng lúc: image copy để tạo compute, database backup/replication để phục hồi dữ liệu, object replication để có file, IaC để dựng hạ tầng và secret manager/key management để cấp quyền truy cập.

### Vì sao image không phải bản backup đầy đủ?

Image thường phản ánh trạng thái máy tại lúc image được tạo. Nếu image được build tuần trước, ứng dụng có thể khởi động với phiên bản cũ hoặc thiếu cấu hình mới. Dữ liệu phát sinh sau thời điểm đó không tự xuất hiện trong image.

Đưa database hoặc file nghiệp vụ vào image cũng tạo rủi ro: image có thể lớn, dữ liệu nhanh lỗi thời, chứa secret hoặc thông tin nhạy cảm và làm khó kiểm soát consistency. Thực hành tốt là giữ image có tính tái tạo, còn dữ liệu nghiệp vụ được bảo vệ bằng cơ chế backup/replication chuyên biệt.

## 3. Lựa chọn region dự phòng

Region dự phòng cần được chọn dựa trên cả kỹ thuật, nghiệp vụ và yêu cầu quản trị.

Các tiêu chí cần xem xét:

- Khoảng cách địa lý và rủi ro tương quan với region chính.
- Độ trễ giữa hai region và tác động đến replication.
- Khả năng cung cấp loại VM, CPU architecture, GPU, disk type và network feature.
- Dung lượng quota và khả năng cấp phát compute khi có sự cố diện rộng.
- Dịch vụ database, object storage, queue, key management và monitoring có sẵn không.
- Yêu cầu data residency, quyền riêng tư, quy định ngành và nơi dữ liệu được phép lưu.
- Chi phí lưu bản sao, replication, traffic liên vùng và compute dự phòng.
- Khả năng vận hành của đội ngũ ở region đích, bao gồm quyền truy cập và on-call.
- Thời gian DNS, certificate, firewall và endpoint được cập nhật.

Không chọn region chỉ vì gần hoặc có giá thấp. Region đích phải có đủ dịch vụ và capacity cho workload cần khôi phục. Với yêu cầu đặc biệt như GPU, license phần mềm hoặc instance family cụ thể, cần kiểm tra khả năng cấp phát trước.

### Active/passive và active/active

| Mô hình | Cách hoạt động | Ưu điểm | Chi phí và độ phức tạp |
|---|---|---|---|
| Backup and restore | Có backup/image ở region khác; dựng compute khi sự cố | Chi phí duy trì thấp | RTO dài hơn; nhiều bước restore trong incident |
| Pilot light | Một số thành phần nền tảng và dữ liệu luôn được chuẩn bị | Giảm thời gian khôi phục so với chỉ có backup | Cần tự động mở rộng compute và kiểm tra dependency |
| Warm standby | Region dự phòng chạy phiên bản thu nhỏ nhưng sẵn sàng | Có thể scale lên nhanh hơn | Chi phí duy trì compute và replication |
| Hot standby/active-passive | Stack gần đầy đủ ở region phụ, traffic chính vẫn ở region chính | RTO thấp hơn nếu failover đã được diễn tập | Chi phí cao; cần đồng bộ và quản lý split-brain |
| Active/active | Hai hoặc nhiều region cùng phục vụ traffic | Có thể tiếp tục phục vụ khi một region mất | Phức tạp về dữ liệu, consistency, routing và vận hành |

Không phải mọi ứng dụng đều cần active/active. Hãy chọn mô hình đáp ứng RPO/RTO với chi phí và độ phức tạp mà tổ chức có thể vận hành.

## 4. Chuẩn bị machine image để sao chép

Image là đầu vào để tạo VM ở region đích. Một image phù hợp DR nên có version rõ ràng, không chứa dữ liệu runtime nhạy cảm và có thể khởi động trong môi trường khác.

### Nội dung image

Image thường bao gồm:

- Hệ điều hành và bản vá bảo mật.
- Kernel, driver và agent cần thiết.
- Runtime như Java, .NET, Python hoặc web server.
- Ứng dụng hoặc artifact đã version hóa.
- Cấu hình mặc định không chứa secret.
- Script bootstrap và cơ chế health check.
- Agent giám sát, backup và bảo vệ endpoint nếu cần.

Không nên nhúng private key, password database, access key dài hạn hoặc dữ liệu người dùng vào image. Những thông tin đó phải được lấy khi runtime thông qua workload identity và secret manager.

### Image bất biến và versioning

Mỗi bản image nên có định danh bất biến hoặc version rõ ràng. Không ghi đè image đang dùng bởi production mà không có lịch sử và khả năng rollback.

Metadata nên ghi nhận:

- Image ID và version.
- OS version, architecture và patch baseline.
- Ứng dụng/artifact version.
- Ngày build và pipeline build.
- Region nguồn và các region đã copy.
- Encryption key hoặc key reference.
- Kết quả kiểm thử boot, vulnerability scan và compliance.
- Người hoặc pipeline phê duyệt phát hành.

Image cần được kiểm thử trên region đích vì khác biệt về instance family, driver, firmware, boot mode, architecture hoặc dịch vụ metadata có thể làm máy không khởi động như dự kiến.

### Image copy và các thành phần đi kèm

Quy trình copy do cloud provider cung cấp có thể sao chép image, snapshot nền hoặc metadata theo semantics riêng. Cần kiểm tra:

- Những disk nào thuộc image và disk nào là data disk tách rời.
- Copy có giữ encryption hay phải chỉ định key đích.
- Image có phụ thuộc key do customer quản lý ở region nguồn không.
- Image có thể dùng với instance family và architecture ở region đích không.
- Có yêu cầu license hoặc subscription riêng không.
- Image từ marketplace hoặc image có điều khoản license có được copy và sử dụng cross-region không.
- Image có cần cập nhật metadata, boot configuration hoặc agent sau copy không.

Không giả định image ID ở region nguồn có thể dùng trực tiếp ở region đích. Nhiều nền tảng tạo một image resource mới trong region đích.

## 5. Quy trình sao chép image sang region khác

Một quy trình có kiểm soát thường gồm các bước:

1. Chọn image đã được phê duyệt và xác định version cần phục hồi.
2. Kiểm tra image boot được, đúng OS/architecture và không chứa secret.
3. Xác định disk snapshot và encryption key phụ thuộc.
4. Cấp quyền cho pipeline hoặc operator được phép copy image.
5. Chuẩn bị key mã hóa tại region đích và policy cho phép sử dụng.
6. Khởi chạy tác vụ copy/replication theo dịch vụ cloud.
7. Theo dõi trạng thái copy đến khi hoàn tất.
8. Xác minh image resource và snapshot tương ứng tồn tại ở region đích.
9. Tạo một VM thử nghiệm từ image đích trong subnet cô lập.
10. Kiểm tra boot, driver, agent, bootstrap, identity và readiness.
11. Ghi image ID/version đích vào inventory hoặc IaC variable.
12. Lặp lại theo lịch khi có image mới hoặc patch quan trọng.

### Sơ đồ luồng copy

~~~mermaid
flowchart TD
    A[Image đã kiểm thử ở region chính] --> B[Kiểm tra metadata, disk và encryption]
    B --> C[Chuẩn bị quyền và key ở region đích]
    C --> D[Copy image và snapshot phụ thuộc]
    D --> E{Copy hoàn tất?}
    E -- Không --> F[Kiểm tra quota, key, policy và lỗi tác vụ]
    F --> D
    E -- Có --> G[Xác minh image ở region đích]
    G --> H[Launch VM thử nghiệm trong mạng cô lập]
    H --> I{Boot và readiness thành công?}
    I -- Không --> J[Điều tra compatibility và bootstrap]
    I -- Có --> K[Đăng ký image version vào DR inventory]
~~~

Copy hoàn tất chỉ xác nhận tác vụ sao chép của nền tảng đã hoàn tất. Nó không chứng minh ứng dụng có thể khôi phục dữ liệu hoặc phục vụ giao dịch.

## 6. Encryption key và quyền truy cập cross-region

Một trong những nguyên nhân phổ biến khiến image hoặc snapshot không thể dùng ở region đích là thiếu key hoặc policy phù hợp.

### Khóa mã hóa

Nếu volume/image nguồn được mã hóa bằng customer-managed key, cần xác định cách dịch vụ hỗ trợ copy sang region khác:

- Có cần tạo key riêng ở region đích không?
- Có cần re-encrypt bản sao bằng key đích không?
- Principal nào được phép decrypt nguồn và encrypt đích?
- Key có đang bị disable, pending deletion hoặc hết hiệu lực không?
- Policy có cho phép dịch vụ copy sử dụng key trong cả hai region không?
- Quy trình rotation và recovery của key có được tài liệu hóa không?

Một key của region này có thể không được dùng trực tiếp ở region khác. Một số dịch vụ hỗ trợ multi-region key hoặc key replication, nhưng semantics phụ thuộc nhà cung cấp. Hãy xác minh đúng loại key và dịch vụ cụ thể.

### Nguyên tắc bảo vệ key

- Tách quyền quản trị key khỏi quyền quản trị VM khi có thể.
- Chỉ cấp quyền decrypt/encrypt cho principal và dịch vụ cần thiết.
- Không xuất key material hoặc secret ra file không bảo vệ.
- Bật audit log cho thao tác key.
- Bảo đảm key backup/recovery đáp ứng yêu cầu tổ chức.
- Không xóa key nguồn cho đến khi bản sao và khả năng restore ở region đích được xác minh.
- Kiểm thử restore khi key rotation hoặc key policy thay đổi.

### IAM và service identity

Pipeline DR cần quyền để đọc image nguồn, copy snapshot, dùng key, tạo image đích và kiểm thử VM. Nên cấp role riêng với phạm vi hẹp, tránh dùng tài khoản Owner/Administrator cho toàn bộ quy trình.

Ngoài quyền copy, cần chuẩn bị quyền runtime của workload ở region đích: VM mới phải lấy được secret, đọc config, ghi log, truy cập database/queue/object storage và đăng ký health check theo đúng nhiệm vụ.

## 7. Sao chép và bảo vệ dữ liệu ứng dụng

Image và dữ liệu có lịch trình, consistency và tốc độ thay đổi khác nhau. Hãy thiết kế từng loại dữ liệu theo RPO/RTO.

### Các phương pháp bảo vệ dữ liệu

| Phương pháp | Cách hoạt động | RPO tiềm năng | Lưu ý |
|---|---|---|---|
| Scheduled backup | Chụp bản sao theo lịch | Phụ thuộc chu kỳ backup | Đơn giản nhưng có thể mất thay đổi sau backup gần nhất |
| Snapshot copy cross-region | Copy snapshot sang region khác | Phụ thuộc tần suất snapshot và độ trễ copy | Cần consistency của ứng dụng và key đích |
| Continuous/asynchronous replication | Gửi thay đổi liên tục nhưng có độ trễ | Có thể thấp, phụ thuộc replication lag | Có thể mất dữ liệu chưa replicate |
| Synchronous replication | Chỉ xác nhận ghi theo điều kiện đồng bộ giữa bản sao | Có thể gần 0 cho phạm vi được bảo đảm | Tăng latency và phụ thuộc kết nối giữa region; không phải dịch vụ nào hỗ trợ |
| Object replication | Sao chép object và phiên bản sang bucket/region khác | Phụ thuộc replication delay và versioning | Cần xử lý delete marker, metadata, retention và object lock |
| Native database replication | Database engine hoặc managed service sao chép transaction/log | Theo semantics và lag của engine | Cần xử lý promotion, consistency, failover và split-brain |

RPO thực tế phải tính đến độ trễ copy, khoảng cách snapshot, thời gian phát hiện lỗi và khả năng truy cập bản sao. “Replication enabled” không đồng nghĩa lag luôn bằng 0.

### Database

Database thường là thành phần quyết định RPO. Các lựa chọn gồm:

- Backup đầy đủ và incremental/differential.
- Transaction log hoặc write-ahead log archive.
- Point-in-time recovery.
- Read replica hoặc cross-region replica.
- Native database replication và promotion.
- Backup nhất quán ở mức ứng dụng.

Cần xác định database replica có thể promote ở region đích hay chỉ dùng để đọc. Nếu dùng async replication, kiểm tra replication lag và xác định điểm dữ liệu cuối cùng đã được áp dụng trước khi promote.

Với database tự quản lý trên VM, cần bảo vệ data disk và log disk, đảm bảo snapshot nhất quán và kiểm thử recovery. Snapshot crash-consistent có thể cần database recovery khi boot; application-consistent backup thường yêu cầu quiesce hoặc cơ chế backup của database.

### File và object

Với object storage, kiểm tra:

- Versioning và cách phục hồi object bị ghi đè hoặc xóa.
- Replication rule và replication status.
- Delete marker có được sao chép không.
- Object lock/retention có giữ nguyên ở đích không.
- Metadata, tag, ACL và encryption có được bảo toàn không.
- Bucket policy và IAM ở region đích.
- Replication có bao gồm object cũ hay chỉ object mới sau khi bật rule.

Với shared file system, cần kiểm tra khả năng replication, snapshot, mount target, protocol, ACL và consistency. Không giả định một file system endpoint của region nguồn có thể mount trực tiếp từ region đích.

### Queue và workflow

Queue có thể giữ message đang chờ nhưng cần xác định liệu message được replicate cross-region hay phải tạo queue mới và phát lại từ event log/outbox. Cần hiểu semantics của ordering, deduplication, visibility timeout, redelivery và dead-letter queue.

Nếu queue không được replicate, database/outbox hoặc event archive có thể là nguồn để tái tạo công việc. Việc tái phát event phải idempotent để không tạo side effect trùng.

## 8. Đảm bảo consistency giữa image và dữ liệu

Một bản image được tạo lúc 02:00 và database snapshot lúc 02:30 có thể chứa phiên bản ứng dụng/config khác với schema hoặc dữ liệu. DR cần biết các phiên bản này tương thích hay không.

### Crash-consistent và application-consistent

- **Crash-consistent:** giống trạng thái dữ liệu sau khi máy mất điện đột ngột. Filesystem hoặc database có thể phải chạy journal/log recovery.
- **Application-consistent:** ứng dụng được quiesce hoặc dùng cơ chế backup-aware để tạo bản sao nhất quán giữa các file/dữ liệu liên quan.

Với hệ thống nhiều thành phần, snapshot từng volume riêng lẻ ở các thời điểm khác nhau có thể tạo trạng thái không nhất quán. Dùng cơ chế snapshot group, backup coordinator hoặc quy trình dừng ghi phù hợp.

### Đồng bộ phiên bản

Inventory DR nên ghi:

- Image version và thời điểm build.
- Application artifact version.
- Database backup/snapshot ID và timestamp.
- Replication lag hoặc transaction sequence đã áp dụng.
- Object replication status.
- Config version và schema version.
- Encryption key ID/version.
- IaC release/commit đã dùng để dựng môi trường.

Khi restore, chọn tổ hợp image, config, schema và data backup tương thích. Không chỉ chọn “bản mới nhất” của từng thành phần nếu chúng không được tạo theo một recovery point nhất quán.

### Ví dụ

Ứng dụng phiên bản 2.4 yêu cầu schema database tối thiểu 18. Nếu region đích chỉ có database backup schema 17, khởi chạy image 2.4 có thể lỗi hoặc ghi dữ liệu sai. Có thể cần dùng image tương thích schema 17, chạy migration theo kế hoạch hoặc restore database mới hơn đã được kiểm chứng.

## 9. Tái tạo network và dependency ở region đích

VM boot thành công nhưng không thể phục vụ nếu thiếu network và dependency. Cần chuẩn bị trước các thành phần sau:

- VPC/VNet, subnet, route table và network address plan.
- Security group/firewall rule và network ACL.
- Private DNS zone, service discovery và endpoint.
- NAT/egress gateway, internet gateway hoặc private connectivity.
- Load balancer, target pool và health check.
- VPN, dedicated connection hoặc kết nối đến on-premises.
- Certificate, TLS trust chain và hostname.
- Database endpoint, cache, queue, object storage và secret manager.
- Logging, metrics, tracing, alert và audit pipeline.

### Địa chỉ IP và DNS

Không giả định private IP của VM ở region chính sẽ tồn tại ở region đích. Dùng DNS/service discovery hoặc load balancer endpoint để tách ứng dụng khỏi địa chỉ instance.

Khi failover, cần cập nhật DNS, traffic manager hoặc global load balancer theo quy trình. TTL thấp có thể giúp chuyển nhanh hơn nhưng không bảo đảm mọi resolver/client cập nhật ngay; cache DNS và kết nối lâu dài có thể giữ endpoint cũ.

### Egress và kết nối đối tác

Nếu đối tác allow-list public IP nguồn, region đích cần có NAT/egress IP ổn định đã được đăng ký. Nếu không chuẩn bị, ứng dụng có thể khởi động nhưng không gọi được payment gateway, email provider hoặc API đối tác.

### Capacity và quota

Kiểm tra quota trước sự cố:

- vCPU, VM family và số instance.
- GPU hoặc accelerator nếu workload cần.
- Disk capacity, IOPS và throughput.
- Public IP, NIC, load balancer và NAT gateway.
- Database instance/storage/connection quota.
- Queue, object storage và request quota.
- Certificate, key và secret limits.

Có quota trên giấy không đảm bảo capacity vật lý luôn có sẵn trong một sự kiện khu vực. Với workload quan trọng, cân nhắc reservation, warm standby hoặc phương án instance family thay thế đã kiểm thử.

## 10. Kế hoạch khôi phục compute ở region đích

Một runbook DR nên xác định thứ tự dựng các thành phần theo dependency.

Thứ tự khái niệm:

1. Xác nhận sự cố và quyết định kích hoạt DR.
2. Chọn recovery point hợp lệ theo RPO.
3. Xác minh image, backup, key và quyền truy cập ở region đích.
4. Dựng network, route, firewall, DNS nội bộ và kết nối bảo mật.
5. Khôi phục database hoặc promote replica theo runbook.
6. Khôi phục object/file và queue/workflow cần thiết.
7. Tạo VM/instance từ image đã copy hoặc triển khai container từ image registry đích.
8. Bootstrap config, secret, identity và service discovery.
9. Chạy migration tương thích nếu cần.
10. Kiểm tra health, readiness, dependency và giao dịch đại diện.
11. Đưa backend vào load balancer hoặc traffic manager.
12. Chuyển traffic người dùng và giám sát SLO.

Không nên đưa traffic công khai vào VM trước khi database và các dependency quan trọng đã sẵn sàng. Nếu API khởi động trước database, readiness phải giữ backend khỏi nhận request cho đến khi có thể phục vụ an toàn.

### Sơ đồ recovery

~~~mermaid
flowchart TD
    A[Phát hiện sự cố region chính] --> B[Incident commander xác nhận kích hoạt DR]
    B --> C[Chọn recovery point theo RPO]
    C --> D[Xác minh image, backup, key và quyền]
    D --> E[Dựng network và security boundary ở region đích]
    E --> F[Restore hoặc promote database]
    F --> G[Restore object, file, queue và config]
    G --> H[Launch compute từ image đã copy]
    H --> I[Bootstrap identity, secret và telemetry]
    I --> J[Health/readiness và kiểm thử nghiệp vụ]
    J --> K{Đạt tiêu chí phục vụ?}
    K -- Không --> L[Giữ traffic ở trạng thái an toàn, điều tra]
    L --> J
    K -- Có --> M[Chuyển traffic sang region đích]
    M --> N[Theo dõi SLO và ổn định dịch vụ]
~~~

## 11. Failover và failback

### Failover

Failover là chuyển hoạt động từ region chính sang region dự phòng. Đây là quyết định vận hành có ảnh hưởng lớn, cần người chịu trách nhiệm và tiêu chí rõ ràng.

Trước khi chuyển:

- Xác định region chính thực sự không thể phục vụ hay chỉ một dependency bị lỗi.
- Tránh kích hoạt hai region cùng ghi vào một dữ liệu nếu kiến trúc không hỗ trợ active/active.
- Chọn replica/database recovery point và xác nhận replication lag.
- Fencing hoặc cô lập writer cũ nếu có nguy cơ split-brain.
- Kiểm tra quyền và key của region đích.
- Xác định cách chuyển DNS/global traffic và cách rollback.

Khi chuyển:

- Promote database/replica theo thứ tự.
- Khởi động compute và kiểm tra readiness.
- Mở traffic theo từng bước hoặc tỷ lệ nếu hệ thống hỗ trợ.
- Theo dõi lỗi, latency, queue, transaction và dữ liệu.
- Ghi lại thời điểm chuyển, recovery point và các quyết định.

### Split-brain

Split-brain xảy ra khi hai site cùng tin mình là primary và cùng chấp nhận ghi dữ liệu. Điều này có thể tạo xung đột hoặc mất dữ liệu khi hợp nhất.

Biện pháp phòng ngừa:

- Fencing hoặc cơ chế xác nhận quyền writer duy nhất.
- Quorum/consensus nếu hệ thống dữ liệu hỗ trợ.
- Runbook rõ ai được phép promote.
- Chặn hoặc cô lập writer cũ trước khi cho writer mới hoạt động.
- Không tự động promote chỉ dựa vào timeout mạng nếu chưa hiểu failure mode.

### Failback

Failback là chuyển dịch vụ từ region dự phòng trở lại region chính sau khi sự cố được khắc phục. Không nên đơn giản bật lại traffic về region cũ.

Trình tự có thể gồm:

1. Xác nhận region chính đã an toàn và đủ capacity.
2. Kiểm tra phiên bản image, application, schema và config.
3. Chọn chiều replication mới từ region đang hoạt động sang region phục hồi.
4. Đồng bộ dữ liệu và theo dõi lag đến ngưỡng chấp nhận.
5. Kiểm thử compute và dependency tại region chính.
6. Chọn cửa sổ chuyển traffic, drain request và ngăn ghi đồng thời.
7. Chuyển writer/traffic theo runbook.
8. Xác minh dữ liệu, SLO và health.
9. Khôi phục region dự phòng về vai trò DR và tiếp tục replication theo chiều mới.

Failback có thể khó hơn failover vì dữ liệu mới đã phát sinh ở region dự phòng. Cần có kế hoạch đồng bộ ngược, không ghi đè dữ liệu mới bằng snapshot cũ.

## 12. Tự động hóa bằng Infrastructure as Code và pipeline

IaC giúp dựng lại network, security group, load balancer, VM template, role và policy với cấu hình có thể review. Pipeline có thể tự động copy image, kiểm tra trạng thái, cập nhật inventory và chạy test boot ở region đích.

### Phân tách artifact và cấu hình theo region

Giữ các tham số như region, subnet ID, key ID, instance family và endpoint trong cấu hình môi trường. Không hardcode resource ID của region chính trong image.

Ví dụ manifest DR mang tính khái niệm:

~~~yaml
disaster_recovery:
  primary_region: region-a
  recovery_region: region-b
  compute:
    image_version: orders-api-2.4.1
    instance_family: general-purpose
    desired_capacity: 3
  data:
    database:
      recovery_method: cross_region_replica
      max_replication_lag_seconds: 300
    object_storage:
      replication_enabled: true
  security:
    encryption_key_reference: dr-region-b-key
    workload_identity: orders-api-dr
  validation:
    readiness_path: /health/ready
    smoke_test: create-and-read-order
~~~

Đây là ví dụ mô tả, không phải schema provider-specific. Recovery point và replica lag cần lấy từ dữ liệu runtime thực tế; không nên hardcode rằng lag luôn dưới ngưỡng chỉ vì cấu hình có giá trị đó.

### Các bước pipeline image

- Build image trong pipeline tin cậy.
- Quét lỗ hổng và kiểm tra baseline.
- Ghi version, checksum/digest và provenance.
- Copy image/snapshot sang region đích.
- Áp dụng encryption key và policy đúng.
- Launch test VM trong subnet cô lập.
- Chạy smoke test OS, agent, bootstrap và application.
- Ghi kết quả và image ID vào DR inventory.
- Cảnh báo nếu copy hoặc test thất bại.

Pipeline không nên tự động thay đổi traffic production chỉ vì image copy thành công. Failover cần kiểm tra dữ liệu, dependency và phê duyệt theo chính sách vận hành.

## 13. Bảo vệ backup khỏi xóa nhầm và ransomware

Sao chép backup sang region khác không đủ nếu cùng một principal có thể xóa cả bản gốc lẫn bản sao.

Các biện pháp nên cân nhắc:

- Tách tài khoản/project hoặc quyền quản trị backup khỏi workload account khi phù hợp.
- Dùng immutable backup, retention lock hoặc object lock nếu dịch vụ hỗ trợ.
- Bật versioning và retention policy cho object quan trọng.
- Hạn chế quyền delete snapshot, image, backup vault và encryption key.
- Dùng MFA hoặc approval cho thao tác phá hủy.
- Audit thao tác backup, restore, key và policy.
- Có bản sao offline hoặc isolated khi mô hình đe dọa yêu cầu.
- Kiểm thử khôi phục từ bản backup bị cô lập.
- Giữ key recovery theo quy trình riêng; backup mã hóa mà mất key có thể không sử dụng được.

Replication có thể sao chép cả file bị mã hóa bởi ransomware hoặc thao tác xóa hợp lệ. Cần kết hợp versioning, retention, point-in-time recovery và backup bất biến để có điểm phục hồi sạch.

## 14. Kiểm thử khả năng phục hồi ở region khác

DR plan chỉ đáng tin khi đã được thử. Một image tồn tại trong danh sách không chứng minh có thể boot; một backup có trạng thái completed không chứng minh dữ liệu có thể restore.

### Các cấp độ kiểm thử

- **Image validation:** tạo VM thử nghiệm từ image đích, xác minh boot, driver, agent và bootstrap.
- **Data restore test:** restore database, object và file vào môi trường cô lập; kiểm tra tính toàn vẹn và truy vấn nghiệp vụ.
- **Dependency test:** kiểm tra DNS, secret manager, key, network, endpoint và quyền runtime.
- **Application recovery test:** chạy smoke test, giao dịch đại diện và health check.
- **Failover exercise:** chuyển traffic theo kịch bản đã phê duyệt, đo RTO và RPO thực tế.
- **Failback exercise:** đồng bộ dữ liệu ngược và chuyển lại region chính.
- **Ransomware recovery exercise:** xác minh có thể chọn bản backup sạch trước thời điểm bị xâm nhập.

### Ma trận kiểm thử

| Kịch bản | Kiểm tra | Tiêu chí đạt |
|---|---|---|
| Copy image sang region đích | Image và snapshot có đủ, key hợp lệ | VM test boot được và đúng version |
| Restore database | Backup/replica có thể phục hồi | Integrity check và truy vấn đại diện thành công |
| Object replication chậm | Kiểm tra object mới nhất và replication status | Biết chính xác dữ liệu nào còn thiếu, không giả định đồng bộ |
| Thiếu quyền IAM | Chạy bootstrap bằng workload identity DR | Chỉ quyền cần thiết được cấp và secret retrieval thành công |
| Key bị disable | Thử restore theo quy trình key recovery | Phát hiện sớm và khôi phục quyền dùng key hợp lệ |
| Region chính mất | Chạy tabletop hoặc failover test | Dựng dịch vụ trong RTO và dữ liệu trong RPO |
| Backend mới không có IP cũ | Kiểm tra DNS/service discovery | Client kết nối endpoint mới thành công |
| Failback | Đồng bộ ngược và chuyển traffic | Không split-brain, không mất dữ liệu phát sinh ở DR |

### Đo RPO/RTO thực tế

Ghi lại các mốc thời gian:

- T0: sự cố bắt đầu hoặc được xác định.
- T1: quyết định kích hoạt DR.
- T2: recovery point được chọn và dữ liệu sẵn sàng.
- T3: compute/network/dependency sẵn sàng.
- T4: smoke test và kiểm tra nghiệp vụ đạt.
- T5: traffic được chuyển và SLO ổn định.

RTO thực tế cần đo theo định nghĩa tổ chức, thường tính từ T0 đến khi dịch vụ đạt tiêu chí phục vụ. RPO thực tế đo khoảng cách giữa thời điểm dữ liệu cuối cùng có thể phục hồi và thời điểm sự cố. Phải ghi rõ cách tính để các lần diễn tập so sánh được.

## 15. Ví dụ: khôi phục API và database ở region B

Một hệ thống đơn hàng chạy ở region A:

- Ba VM API sau load balancer.
- Database managed có replica ở region B.
- Object storage chứa ảnh hóa đơn và file đính kèm, có replication.
- Image API được copy sang region B sau mỗi bản phát hành.
- IaC định nghĩa network, subnet, firewall, role và load balancer.
- Secret được quản lý qua secret manager; key riêng ở từng region.

Mục tiêu giả định: RPO 5 phút, RTO 60 phút.

### Trước sự cố

- Image version 2.4.1 đã copy và boot test ở region B.
- Replica database có metric replication lag và cảnh báo khi vượt 5 phút.
- Object replication status được theo dõi.
- Quota VM, disk, IP và load balancer ở region B đã được xác minh.
- DNS/traffic manager có quy trình chuyển endpoint.
- Secret và key DR có quyền sử dụng từ workload identity ở region B.
- Runbook có người phê duyệt và smoke test.

### Khi region A gặp sự cố

1. Incident commander xác nhận kích hoạt DR.
2. Kiểm tra replication lag cuối cùng và chọn recovery point.
3. Fencing writer ở region A nếu có thể hoặc xác minh site cũ không thể ghi.
4. Promote database replica ở region B theo runbook.
5. Xác minh object cần thiết đã replicate; liệt kê object còn thiếu nếu có.
6. Dựng network và load balancer theo IaC.
7. Launch ba VM API từ image 2.4.1.
8. Bootstrap config, secret, identity và telemetry.
9. Kiểm tra database connection, object access và readiness.
10. Chạy thử tạo đơn, đọc đơn và tải hóa đơn.
11. Chuyển traffic qua DNS/global routing.
12. Theo dõi error rate, latency, transaction count và replication.

Nếu object mới nhất chưa replicate, không nên báo dữ liệu đầy đủ. Có thể tạm giới hạn chức năng phụ thuộc object, phục hồi từ backup khác hoặc thông báo trạng thái theo quy trình nghiệp vụ.

### Sau khi dịch vụ ổn định

- Ghi RTO/RPO thực tế.
- Kiểm tra giao dịch phát sinh trong thời gian chuyển vùng.
- Thiết lập replication từ region B sang nơi dự phòng tiếp theo hoặc chuẩn bị chiều failback.
- Rà soát alert, capacity và chi phí.
- Chỉ đưa region A trở lại vai trò chính sau khi dữ liệu đã đồng bộ và failback được kiểm thử.

## 16. Checklist sao chép image và dữ liệu cross-region

### Image và compute

- [ ] Image có version, provenance và baseline bảo mật rõ.
- [ ] Image không chứa secret hoặc dữ liệu runtime nhạy cảm.
- [ ] Đã xác định disk/snapshot thuộc image và data disk riêng.
- [ ] Image đã copy sang region đích và có ID/version tại đó.
- [ ] VM test từ image đích boot thành công.
- [ ] Instance family, architecture, driver, license và quota đã được xác minh.
- [ ] Bootstrap, agent và application readiness hoạt động.

### Dữ liệu

- [ ] RPO được xác định cho từng loại dữ liệu.
- [ ] Database backup/replica có recovery point và lag được quan sát.
- [ ] Backup có consistency phù hợp và restore test thành công.
- [ ] Object/file replication, versioning, delete marker và retention được hiểu rõ.
- [ ] Queue, event, outbox và workflow có phương án phục hồi.
- [ ] Encryption key ở region đích có thể sử dụng.
- [ ] Có nguồn backup bất biến/isolated nếu mô hình đe dọa yêu cầu.

### Network, identity và dependency

- [ ] VPC/VNet, subnet, route, firewall và DNS đã được dựng.
- [ ] Load balancer, health check và traffic manager có cấu hình.
- [ ] Workload identity và IAM role ở region đích có least privilege.
- [ ] Secret manager, certificate, KMS/key service và endpoint truy cập được.
- [ ] NAT/egress IP và allow-list của đối tác đã sẵn sàng.
- [ ] Quota/capacity cho VM, storage, IP, LB và dịch vụ phụ thuộc đã được xác minh.
- [ ] Logging, monitoring, tracing và audit hoạt động ở region đích.

### Failover, failback và kiểm thử

- [ ] Có runbook, incident commander, owner và tiêu chí kích hoạt DR.
- [ ] Có cơ chế ngăn split-brain hoặc writer kép.
- [ ] Trình tự restore database, object, compute và traffic được xác định.
- [ ] Smoke test kiểm tra giao dịch và tính toàn vẹn dữ liệu.
- [ ] RTO/RPO được đo qua diễn tập.
- [ ] Failback có kế hoạch đồng bộ ngược và chuyển writer/traffic an toàn.
- [ ] Backup và image được kiểm tra định kỳ, không chỉ kiểm tra trạng thái copy.
- [ ] Quyền xóa backup/key được tách và audit.

## 17. Những sai lầm thường gặp

**Cho rằng image copy là đã có DR.** Image chỉ giúp tạo compute. Database, object, queue, network, identity, key và DNS vẫn cần được chuẩn bị.

**Chỉ sao chép snapshot mà không kiểm tra consistency.** Snapshot của database đang ghi có thể cần crash recovery hoặc không nhất quán giữa nhiều volume. Dùng cơ chế backup-aware và kiểm thử restore.

**Không chuẩn bị encryption key ở region đích.** Snapshot có thể tồn tại nhưng không thể decrypt hoặc tạo volume. Kiểm tra key policy và thử restore thực tế.

**Bật replication nhưng không theo dõi lag.** Bản sao có thể chậm hơn RPO hoặc chưa nhận object mới. Giám sát trạng thái và xác định recovery point thực tế.

**Dùng cùng một credential quản trị cho cả hai region.** Tài khoản bị xâm nhập có thể xóa cả bản gốc lẫn backup. Tách quyền và bảo vệ backup.

**Quên quota và capacity.** Region đích có image nhưng không cấp được instance family, GPU, IP hoặc storage. Xác minh trước hoặc có loại tài nguyên thay thế.

**Chuyển traffic trước khi database sẵn sàng.** Request có thể ghi lỗi hoặc tạo dữ liệu không nhất quán. Dùng readiness và smoke test trước khi mở traffic.

**Không fencing region cũ.** Khi mạng phục hồi, hai region có thể cùng ghi. Phải có cơ chế writer duy nhất và runbook split-brain.

**Failback bằng cách bật lại region cũ.** Dữ liệu mới có thể chỉ tồn tại ở region dự phòng. Đồng bộ ngược, kiểm tra consistency và chuyển writer có kiểm soát.

**Chỉ diễn tập trên giấy.** Tabletop không phát hiện lỗi boot image, key permission, quota, DNS hoặc restore database. Cần thực hiện test kỹ thuật ở môi trường cô lập.

## 18. Tự kiểm tra

1. Machine image khác disk snapshot, database backup và replication như thế nào?
2. Vì sao copy image sang region khác không đủ để khôi phục một ứng dụng có database và object storage?
3. RPO và RTO khác nhau như thế nào? Chu kỳ backup ảnh hưởng RPO ra sao?
4. Vì sao image và database backup cần được kiểm tra tương thích phiên bản?
5. Khi image được mã hóa bằng customer-managed key, cần chuẩn bị gì ở region đích?
6. Phân biệt crash-consistent và application-consistent snapshot.
7. Async replication có thể gây mất dữ liệu như thế nào khi promote replica?
8. Vì sao cần fencing writer cũ trước khi mở writer ở region dự phòng?
9. Những network, IAM, quota và dependency nào cần được kiểm tra trước failover?
10. Failback khác failover như thế nào khi dữ liệu mới đã phát sinh ở region dự phòng?
11. Làm thế nào đo RPO/RTO thực tế trong một cuộc diễn tập?
12. Hãy xây dựng thứ tự khôi phục cho một API stateless, database và object storage ở region khác.

Khả năng khôi phục ở region khác cần được xây dựng như một hệ thống hoàn chỉnh: image có thể tạo lại compute, dữ liệu có recovery point phù hợp, key và identity cho phép truy cập an toàn, network và dependency có thể tái tạo, còn failover/failback có thứ tự rõ ràng. Khi các thành phần được version hóa, tự động hóa và kiểm thử thường xuyên, tổ chức có thể biết chính xác mình khôi phục được gì, mất tối đa bao nhiêu dữ liệu và cần bao lâu để dịch vụ hoạt động trở lại.
