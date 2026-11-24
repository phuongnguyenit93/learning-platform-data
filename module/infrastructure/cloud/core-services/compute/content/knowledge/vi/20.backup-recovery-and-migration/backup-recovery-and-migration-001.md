# RPO, RTO và phạm vi bảo vệ của backup workload

Một workload cloud có thể chạy trên nhiều thành phần: máy ảo, container, volume, database, object storage, queue, cấu hình mạng, danh tính và khóa mã hóa. Khi xảy ra lỗi phần cứng, xóa nhầm dữ liệu, lỗi triển khai, mã độc hoặc sự cố cả vùng cloud, việc khởi động lại máy chủ chưa chắc khôi phục được dịch vụ. Đội vận hành cần biết dữ liệu có thể mất tối đa bao nhiêu, dịch vụ phải hoạt động trở lại trong bao lâu và những thành phần nào thực sự nằm trong phạm vi bảo vệ.

Hai chỉ số quan trọng để thiết kế khả năng phục hồi là **RPO (Recovery Point Objective)** và **RTO (Recovery Time Objective)**. RPO mô tả mức mất dữ liệu có thể chấp nhận; RTO mô tả thời gian gián đoạn có thể chấp nhận. Hai chỉ số này định hướng tần suất sao lưu, cách lưu bản sao, năng lực khôi phục và chi phí vận hành.

Bài học này thuộc chương **Sao lưu, khôi phục và di chuyển** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong phạm vi đó, RPO, RTO và phạm vi backup giúp xác định workload nào cần bảo vệ, bảo vệ bằng cách nào và làm sao chứng minh có thể khôi phục.

## 1. RPO và RTO là gì?

### 1.1. Recovery Point Objective (RPO)

**RPO** là mức mất dữ liệu tối đa mà tổ chức có thể chấp nhận khi xảy ra sự cố, thường được biểu diễn bằng một khoảng thời gian.

Ví dụ, RPO 30 phút có nghĩa là tổ chức chấp nhận khôi phục dữ liệu về một điểm có thể khiến tối đa khoảng 30 phút thay đổi gần nhất bị mất. Để đạt mục tiêu này, phải có recovery point hợp lệ đủ gần thời điểm sự cố và bản sao phải chứa dữ liệu nhất quán.

RPO không đơn giản là tần suất tạo backup. Nếu lịch backup chạy mỗi 15 phút nhưng job thường hoàn tất chậm 20 phút, bị lỗi hoặc bản sao không thể restore, RPO thực tế có thể lớn hơn 15 phút. Cần đo theo timestamp của recovery point đã được xác minh có thể sử dụng.

### 1.2. Recovery Time Objective (RTO)

**RTO** là khoảng thời gian tối đa được phép để khôi phục một dịch vụ hoặc workload sau gián đoạn, tới mức đáp ứng yêu cầu vận hành đã định.

Ví dụ, RTO 4 giờ có nghĩa dịch vụ cần được khôi phục trong vòng 4 giờ theo cách đo đã thống nhất. Khôi phục có thể bao gồm tạo compute mới, gắn hoặc restore dữ liệu, khôi phục cấu hình, kiểm tra dependency, xác minh ứng dụng và đưa traffic trở lại.

RTO không chỉ là thời gian copy dữ liệu. Các bước phát hiện, quyết định, cấp quyền truy cập recovery, provision hạ tầng, restore, replay log, kiểm thử và chuyển traffic đều tiêu thụ thời gian.

### 1.3. Phân biệt RPO và RTO

| Chỉ số | Trả lời câu hỏi | Đơn vị thường dùng | Yếu tố thiết kế chính |
|---|---|---|---|
| RPO | Có thể mất bao nhiêu dữ liệu? | Giây, phút, giờ | Tần suất backup, replication lag, log shipping, checkpoint |
| RTO | Có thể gián đoạn bao lâu? | Phút, giờ | Tốc độ provision, restore, automation, năng lực recovery và kiểm thử |

Ví dụ:

- Một hệ thống có RPO 15 phút, RTO 2 giờ: cần recovery point không cũ hơn khoảng 15 phút và dịch vụ phải hoạt động trở lại trong tối đa 2 giờ.
- Một kho lưu trữ báo cáo có RPO 24 giờ, RTO 2 ngày: có thể dùng backup định kỳ và quy trình restore chậm hơn.
- Một hệ thống giao dịch quan trọng có RPO vài giây và RTO vài phút: thường cần replication liên tục, failover tự động hoặc standby được chuẩn bị sẵn, cùng cơ chế bảo vệ tính nhất quán.

RPO thấp không tự động tạo RTO thấp. Có thể có nhiều bản sao rất mới nhưng cần nhiều giờ để provision hạ tầng và restore. Ngược lại, có thể khởi động một standby rất nhanh nhưng dữ liệu của standby đã trễ nhiều giờ.

### 1.4. RPO/RTO là mục tiêu, không phải lời hứa của một công cụ

Backup product có thể cung cấp snapshot, replication hoặc restore point, nhưng công cụ không tự quyết định mục tiêu kinh doanh. RPO/RTO phải xuất phát từ tác động khi dịch vụ ngừng hoạt động hoặc mất dữ liệu.

Một hệ thống chỉ được xem là đạt mục tiêu khi có bằng chứng đo được. Cần thử khôi phục, ghi thời gian thực tế, kiểm tra dữ liệu và xác minh các thành phần phụ thuộc.

## 2. Xác định mục tiêu từ yêu cầu kinh doanh

### 2.1. Phân tích tác động kinh doanh

Trước khi chọn lịch backup, cần hiểu dịch vụ quan trọng tới đâu và hậu quả khi mất dữ liệu hoặc gián đoạn.

Các câu hỏi cần làm rõ:

- Dịch vụ phục vụ khách hàng, nội bộ hay quy trình hậu trường?
- Thời gian gián đoạn ảnh hưởng doanh thu, an toàn, hợp đồng hoặc nghĩa vụ pháp lý thế nào?
- Dữ liệu nào có thể tái tạo và dữ liệu nào không thể tái tạo?
- Có thể xử lý tạm bằng quy trình thủ công không?
- Có phụ thuộc vào hệ thống khác không?
- Có mùa cao điểm hoặc thời gian không được phép gián đoạn không?
- Ai quyết định kích hoạt disaster recovery và chấp nhận mất dữ liệu?

Kết quả thường được ghi trong Business Impact Analysis (BIA), phân loại mức quan trọng và kế hoạch liên tục kinh doanh.

### 2.2. Phân loại workload theo mức độ quan trọng

Có thể bắt đầu bằng các tier minh họa:

| Tier | Ví dụ workload | RPO tham khảo | RTO tham khảo |
|---|---|---:|---:|
| Tier 0 - rất quan trọng | Giao dịch lõi, identity hoặc control plane nội bộ | Vài giây đến vài phút | Vài phút |
| Tier 1 - quan trọng | API khách hàng, đơn hàng, thanh toán | 5-15 phút | 1-2 giờ |
| Tier 2 - thông thường | Báo cáo vận hành, worker không đồng bộ | 1-4 giờ | 4-8 giờ |
| Tier 3 - có thể trì hoãn | Dữ liệu phân tích có thể tái tạo, môi trường dev | 24 giờ hoặc hơn | 1-3 ngày |

Đây chỉ là ví dụ để thảo luận. Không dùng các con số này làm SLA mặc định. Tổ chức phải phê duyệt mục tiêu dựa trên BIA, quy định, kiến trúc, chi phí và năng lực vận hành.

### 2.3. Mỗi workload có thể có mục tiêu khác nhau

Một ứng dụng có thể chứa nhiều loại dữ liệu:

- Database giao dịch cần RPO thấp.
- File upload có thể cần backup thường xuyên nhưng restore độc lập.
- Cache có thể tái tạo và không cần backup.
- Log có thể cần retention phục vụ audit nhưng không nhất thiết nằm trong đường phục hồi ứng dụng.
- Báo cáo tổng hợp có thể tái tạo từ dữ liệu nguồn.
- Hàng đợi message cần chính sách lưu message, dead-letter và replay riêng.

Không nên gán một RPO duy nhất cho toàn bộ ứng dụng nếu các thành phần có đặc tính và khả năng phục hồi khác nhau. Cần xác định RPO/RTO của dịch vụ tổng thể và mục tiêu của từng dependency.

## 3. Đo RPO và RTO thực tế

### 3.1. RPO thực tế

Tại thời điểm sự cố, tìm recovery point mới nhất đã hoàn tất, nhất quán và có thể restore. Khoảng cách giữa thời điểm dữ liệu cần khôi phục và thời điểm của recovery point đó là mức mất dữ liệu thực tế.

Cách diễn đạt đơn giản:

**RPO thực tế = thời điểm sự cố - timestamp của recovery point hợp lệ gần nhất**

Timestamp cần phản ánh thời điểm dữ liệu trong bản sao có hiệu lực, không chỉ là lúc backup job bắt đầu hoặc kết thúc. Với backup nhiều phần hoặc có transaction log, phải xác định recovery point cuối cùng có thể dựng lại nhất quán.

Ví dụ:

- Sự cố xảy ra lúc 14:00.
- Recovery point gần nhất đã được xác minh là 13:42.
- RPO thực tế xấp xỉ 18 phút.

Nếu backup lúc 13:57 tồn tại nhưng file hỏng hoặc thiếu transaction log cần thiết, không thể xem đó là recovery point hợp lệ.

### 3.2. RTO thực tế

RTO cần được đo từ mốc bắt đầu được thống nhất, thường là lúc dịch vụ bị gián đoạn hoặc sự cố được tuyên bố, tới lúc dịch vụ được khôi phục và xác minh đạt tiêu chí tối thiểu.

**RTO thực tế = thời điểm dịch vụ phục hồi đạt tiêu chí - thời điểm bắt đầu sự cố**

Ví dụ:

| Công đoạn | Thời lượng |
|---|---:|
| Phát hiện, xác nhận và quyết định recovery | 10 phút |
| Provision compute và network | 15 phút |
| Restore database và volume | 55 phút |
| Khôi phục secret, cấu hình và dependency | 15 phút |
| Kiểm thử dữ liệu, ứng dụng và traffic | 20 phút |
| Tổng | 115 phút |

Nếu mục tiêu RTO là 2 giờ, ví dụ này còn 5 phút dự phòng. Trong thực tế cần đo nhiều lần và tính các tình huống chậm hơn, không chỉ lấy lần chạy tốt nhất.

### 3.3. Bao gồm thời gian kiểm tra

Không nên dừng đồng hồ RTO ngay khi VM khởi động hoặc database process báo running. Dịch vụ chỉ được coi là phục hồi khi đáp ứng tiêu chí đã thống nhất, chẳng hạn:

- API health check thành công.
- Người dùng hoặc hệ thống upstream truy cập được.
- Database không còn recovery pending.
- Dữ liệu đạt mức nhất quán cần thiết.
- Queue/stream có thể tiếp tục tiêu thụ.
- Monitoring, logging và backup đã hoạt động.
- Quyền truy cập và audit được khôi phục.

### 3.4. Theo dõi mục tiêu bằng dashboard

Có thể theo dõi:

- RPO target và RPO thực tế gần nhất.
- Tuổi của recovery point mới nhất.
- Backup success/failure rate.
- Replication lag.
- Restore duration theo kích thước dữ liệu.
- RTO thực tế qua các lần diễn tập.
- Tỷ lệ workload có restore test đạt.
- Số ngoại lệ backup và thời gian tồn tại.
- Dung lượng backup và chi phí lưu trữ.

Cảnh báo nên được kích hoạt trước khi vi phạm RPO, ví dụ khi tuổi recovery point tiến gần ngưỡng mục tiêu, hoặc khi replication lag vượt ngưỡng.

## 4. Phạm vi bảo vệ của backup workload

### 4.1. Backup phải bảo vệ toàn bộ thành phần cần để chạy lại dịch vụ

Một workload compute không chỉ gồm VM hoặc container. Khi lập phạm vi backup, cần lập danh mục các thành phần:

| Thành phần | Nội dung cần xem xét | Cách bảo vệ thường gặp |
|---|---|---|
| Compute instance | OS, package, runtime, cấu hình host | Golden image, image version, IaC, backup khi cần |
| Persistent block volume | File, database data, application state | Snapshot, backup theo lịch, replication |
| Database | Data files, transaction log, schema, metadata | Native backup, log backup, PITR, replica |
| Object/file storage | Object, version, metadata, ACL | Versioning, replication, backup/retention policy |
| Queue/stream | Message, offset, partition metadata | Retention, snapshot/checkpoint, replay |
| Container image | Image layers và digest đã phát hành | Registry replication, artifact retention |
| Kubernetes config | Manifest, Helm values, CRD, policy | Git/IaC, export và backup metadata cần thiết |
| Serverless config | Function code, runtime, version, trigger, layer | Source/artifact repository, IaC, release archive |
| Network | VPC/VNet, subnet, route, firewall, DNS | IaC, export cấu hình, version control |
| Identity và secret | IAM policy, role, certificate, key reference | Backup cấu hình an toàn, secret manager, key recovery plan |
| Observability | Dashboard, alert, log routing, agent config | IaC và export cấu hình |
| Recovery metadata | Catalog, encryption metadata, dependency map | Backup catalog, tài khoản recovery độc lập |

Không phải mọi thành phần đều cần copy thành backup nhị phân. Một số có thể tái tạo từ source code, image pipeline hoặc IaC. Nhưng phải bảo đảm artifact, phiên bản và thông tin cần thiết vẫn còn truy cập được khi môi trường chính bị mất.

### 4.2. Phân biệt dữ liệu persistent và ephemeral

- **Persistent data:** database, file người dùng, volume chứa trạng thái, object và dữ liệu giao dịch. Thường cần backup/replication rõ ràng.
- **Ephemeral data:** cache, temporary file, scratch space, dữ liệu có thể tạo lại. Có thể không cần backup nếu đã xác nhận không chứa trạng thái duy nhất.
- **Configuration:** có thể tái tạo từ IaC hoặc configuration management, nhưng cần lưu phiên bản đã triển khai và các giá trị cần thiết.
- **Runtime artifact:** image, package, function bundle và dependency. Cần giữ artifact tương ứng để tránh build lại một phiên bản khác khi recovery.

Không nên suy ra dữ liệu là ephemeral chỉ từ tên volume hoặc mount path. Cần hỏi chủ sở hữu ứng dụng và kiểm tra hành vi thực tế.

### 4.3. VM image không thay thế backup dữ liệu

Image của VM thường giúp tạo lại hệ điều hành và phần mềm nền. Nó có thể không chứa dữ liệu mới nhất trên volume tách rời hoặc database managed.

Một cách thiết kế phổ biến:

- Dùng image chuẩn để dựng compute.
- Dùng IaC để tạo network, security policy và IAM.
- Restore persistent volume hoặc database từ recovery point.
- Nạp secret và certificate qua hệ thống quản lý phù hợp.
- Deploy phiên bản ứng dụng đã được kiểm thử.
- Chạy kiểm tra trước khi mở traffic.

Nếu chỉ backup boot disk, có thể khôi phục được OS nhưng mất toàn bộ dữ liệu nằm trên data disk.

### 4.4. Container image không chứa toàn bộ trạng thái ứng dụng

Container image chứa filesystem và dependency được đóng gói. Persistent volume, database ngoài cluster, object storage, secret và cluster configuration có thể nằm ngoài image.

Khi bảo vệ workload Kubernetes, cần xác định:

- Image digest và registry.
- Deployment, StatefulSet, Service, Ingress/Gateway.
- ConfigMap và custom resource cần thiết.
- Secret hoặc cách tái tạo secret an toàn.
- PersistentVolume và PersistentVolumeClaim.
- StorageClass, CSI driver và snapshot support.
- CRD, operator và phiên bản cluster.
- NetworkPolicy, service account và RBAC.

Không nên export secret dạng plaintext vào repository hoặc backup không được mã hóa. Cần bảo vệ cả khả năng truy cập secret manager và khóa giải mã khi khôi phục.

### 4.5. Serverless và dịch vụ managed

Nhà cung cấp có thể quản lý compute host, nhưng khách hàng vẫn cần backup:

- Source code và artifact đã deploy.
- Runtime version, layer và extension.
- Environment configuration và trigger.
- IAM role/policy và resource binding.
- Event source mapping, schedule và permission.
- Database, object storage, queue và các dữ liệu ngoài function.
- KMS key, certificate và secret reference.

Một function có thể deploy lại dễ dàng nhưng vẫn không hoạt động nếu trigger, quyền gọi, secret hoặc database endpoint không được khôi phục.

## 5. Các phương pháp bảo vệ dữ liệu

### 5.1. Full backup

Full backup sao chép toàn bộ phạm vi dữ liệu được chọn tại một thời điểm.

Ưu điểm:

- Điểm khôi phục tương đối độc lập.
- Quy trình restore thường dễ hiểu.
- Dễ xác định nội dung của một bản backup.

Hạn chế:

- Tốn thời gian tạo và dung lượng.
- Có thể tăng tải lên hệ thống nguồn.
- Chi phí truyền và lưu trữ cao với tập dữ liệu lớn.

### 5.2. Incremental backup

Incremental backup lưu các thay đổi kể từ lần backup trước đó theo thiết kế của sản phẩm.

Ưu điểm:

- Giảm lượng dữ liệu cần truyền và lưu mỗi lần.
- Phù hợp với tập dữ liệu lớn, thay đổi thường xuyên.

Hạn chế:

- Restore có thể cần nhiều thành phần trong chuỗi backup.
- Nếu một phần phụ thuộc bị thiếu hoặc hỏng, recovery point liên quan có thể không dùng được.
- Cần quản lý catalog và kiểm tra chuỗi backup.

Một số sản phẩm dùng incremental forever và tổng hợp dữ liệu ở backend; cách restore phụ thuộc implementation. Không nên giả định mọi hệ thống incremental đều phải ghép thủ công từng file.

### 5.3. Differential backup

Differential backup lưu thay đổi kể từ lần full backup gần nhất. Restore thường cần full backup gần nhất và differential backup được chọn.

Ưu điểm:

- Restore có thể đơn giản hơn chuỗi incremental dài.
- Mỗi differential thường lớn dần cho tới lần full tiếp theo.

Hạn chế:

- Dung lượng tăng theo thời gian giữa các lần full.
- Tạo full backup có thể gây tải đáng kể.

### 5.4. Snapshot

Snapshot ghi lại trạng thái của volume hoặc tài nguyên tại một thời điểm theo cơ chế của nền tảng.

Snapshot có thể nhanh và thuận tiện để tạo restore point, nhưng cần xem:

- Snapshot là crash-consistent hay application-consistent.
- Có bao gồm tất cả volume liên quan không.
- Snapshot có độc lập với tài khoản/region hay không.
- Có bị xóa cùng tài khoản hoặc quyền quản trị nguồn không.
- Có hỗ trợ immutable retention hoặc vault lock không.
- Có thể restore sang loại volume hoặc zone khác không.

Snapshot trong cùng tài khoản và cùng miền sự cố có thể bị xóa hoặc mã hóa cùng hệ thống nguồn. Vì vậy, snapshot không tự động thay thế một chiến lược backup độc lập.

### 5.5. Replication

Replication sao chép dữ liệu sang replica hoặc địa điểm khác, có thể đồng bộ hoặc bất đồng bộ.

- **Synchronous replication:** thường yêu cầu ghi được xác nhận ở nhiều nơi trước khi hoàn tất; có thể giảm mất dữ liệu nhưng tăng latency và phụ thuộc độ trễ mạng.
- **Asynchronous replication:** ghi ở nguồn được xác nhận trước khi bản sao nhận đủ; có thể có replication lag và mất một phần thay đổi khi sự cố xảy ra.

Replication giúp availability và recovery nhanh, nhưng lỗi logic, xóa nhầm hoặc ransomware có thể được nhân bản sang replica. Cần kết hợp backup có lịch sử và khả năng quay về thời điểm trước sự cố.

### 5.6. Continuous data protection và point-in-time recovery

Một số hệ thống lưu transaction log hoặc thay đổi liên tục để cho phép khôi phục tới một thời điểm trong khoảng retention.

Ví dụ, database có thể restore full backup rồi replay transaction log đến trước thời điểm xóa nhầm. Cơ chế này hỗ trợ RPO thấp và khôi phục chính xác hơn backup định kỳ, nhưng phụ thuộc log đầy đủ, thứ tự và retention.

Cần xác định khoảng thời gian PITR được hỗ trợ và cách khôi phục sang một instance mới để kiểm tra trước khi thay thế production.

### 5.7. So sánh phương pháp

| Phương pháp | RPO có thể đạt | Thời gian restore | Điểm cần chú ý |
|---|---|---|---|
| Full backup định kỳ | Phụ thuộc tần suất backup | Có thể dài với dữ liệu lớn | Đơn giản nhưng tốn dung lượng |
| Incremental/differential | Phụ thuộc lịch và chuỗi hợp lệ | Phụ thuộc cấu trúc backup | Quản lý catalog và dependency |
| Snapshot | Phụ thuộc tần suất snapshot và consistency | Thường nhanh hơn full restore, tùy volume | Cần bản sao độc lập và kiểm thử |
| Asynchronous replication | Phụ thuộc replication lag | Có thể nhanh | Có thể sao chép lỗi logic |
| Synchronous replication | Có thể gần bằng 0 trong điều kiện hỗ trợ | Có thể failover nhanh | Latency, quorum và failure domain |
| PITR/log backup | Có thể rất thấp nếu log được bảo vệ liên tục | Phụ thuộc restore và replay log | Cần chuỗi log đầy đủ |

Không có phương pháp nào tốt nhất cho mọi workload. Thiết kế thường kết hợp nhiều cơ chế.

## 6. Tính nhất quán của backup

### 6.1. Crash-consistent backup

Crash-consistent snapshot tương tự trạng thái dữ liệu sau khi máy bị mất điện đột ngột: các ghi đã được flush có thể tồn tại, nhưng một số ghi đang ở bộ nhớ hoặc cache chưa được ghi xuống disk có thể mất.

Filesystem hoặc database có thể tự phục hồi journal/log sau khi restore, nhưng không phải mọi ứng dụng đều an toàn với snapshot crash-consistent.

### 6.2. Filesystem-consistent và application-consistent

- **Filesystem-consistent:** filesystem được đưa về trạng thái phù hợp để snapshot, thường thông qua flush hoặc freeze.
- **Application-consistent:** ứng dụng được yêu cầu chuẩn bị dữ liệu, flush buffer, hoàn tất hoặc tạm dừng transaction và phối hợp snapshot.

Với database, nên dùng công cụ backup native hoặc cơ chế quiesce được database hỗ trợ. Snapshot nhiều volume độc lập ở các thời điểm khác nhau có thể tạo trạng thái không nhất quán nếu dữ liệu được phân tán trên nhiều volume.

### 6.3. Backup nhiều volume

Nếu database dùng data volume, log volume và volume cấu hình, cần có một recovery point nhất quán giữa chúng.

Cách thực hiện có thể gồm:

1. Dùng native backup hoặc quiesce application.
2. Flush và freeze filesystem nếu quy trình yêu cầu.
3. Tạo snapshot đồng bộ theo khả năng nền tảng.
4. Ghi metadata liên kết các snapshot cùng một recovery set.
5. Thaw filesystem và tiếp tục workload.
6. Thử restore cả nhóm volume như một đơn vị.

Không tự ý freeze filesystem lâu trên production; thời gian dừng ghi cần được đánh giá và kiểm thử.

### 6.4. Backup không thay thế transaction log

Với database, full backup định kỳ có thể không đủ để đáp ứng RPO thấp. Cần bảo vệ transaction log hoặc dùng PITR/continuous backup theo khả năng hệ quản trị.

Nếu full backup thành công nhưng log chain bị thiếu, không thể replay tới thời điểm mong muốn. Phải theo dõi cả trạng thái backup data và log.

## 7. Thiết kế lịch backup và retention

### 7.1. Chọn tần suất theo RPO

Tần suất backup cần đủ để tạo recovery point mới hơn mục tiêu RPO, đồng thời tính đến thời gian job, độ trễ và xác minh.

Ví dụ, nếu RPO mục tiêu là 1 giờ, có thể thiết kế backup mỗi 30 phút để có khoảng đệm. Nhưng lịch chạy 30 phút không bảo đảm RPO 30 phút nếu backup mất 45 phút hoặc thất bại liên tục.

Cần theo dõi timestamp dữ liệu được bảo vệ, không chỉ timestamp bắt đầu job.

### 7.2. Chính sách retention

Retention xác định bản backup được giữ trong bao lâu và có bao nhiêu điểm khôi phục.

Ví dụ minh họa:

- Giữ recovery point theo giờ trong 48 giờ.
- Giữ bản hàng ngày trong 30 ngày.
- Giữ bản hàng tuần trong 12 tuần.
- Giữ bản hàng tháng trong 12 tháng hoặc theo yêu cầu lưu trữ.

Chính sách thực tế phải phù hợp quy định, nhu cầu điều tra, chi phí và khả năng restore. Retention quá ngắn có thể không phát hiện được lỗi logic xảy ra từ lâu; retention quá dài làm tăng chi phí và bề mặt dữ liệu nhạy cảm.

### 7.3. GFS và retention theo nhiều tầng

Mô hình Grandfather-Father-Son (GFS) giữ nhiều tầng recovery point:

- Son: bản sao thường xuyên, giữ ngắn hạn.
- Father: bản sao theo tuần, giữ trung hạn.
- Grandfather: bản sao theo tháng hoặc năm, giữ dài hạn.

Mô hình này giúp cân bằng độ chi tiết và chi phí lưu trữ. Cần bảo đảm các bản dài hạn vẫn có thể đọc, giải mã và restore bằng công cụ được hỗ trợ.

### 7.4. Retention lock và legal hold

Một số nền tảng hỗ trợ immutable retention hoặc retention lock để ngăn xóa/sửa backup trong thời gian quy định. Cơ chế này hữu ích trước ransomware hoặc thao tác phá hoại.

Cần phân biệt:

- **Retention policy:** quy định thời gian lưu.
- **Immutable backup:** bản sao không thể sửa/xóa theo điều kiện khóa.
- **Legal hold:** giữ dữ liệu lâu hơn lịch thông thường vì yêu cầu pháp lý hoặc điều tra.
- **Lifecycle policy:** tự động chuyển lớp lưu trữ hoặc xóa khi hết hạn.

Retention lock có thể khó hoặc không thể rút ngắn sau khi bật. Cần phê duyệt thời gian, chi phí và yêu cầu compliance trước khi áp dụng.

## 8. Bảo vệ backup khỏi sự cố và ransomware

### 8.1. Tách failure domain

Nếu backup nằm trong cùng tài khoản, cùng quyền quản trị và cùng region với production, kẻ tấn công hoặc lỗi quản trị có thể xóa cả hai.

Nên xem xét:

- Tài khoản hoặc project backup riêng.
- Quyền ghi backup tách khỏi quyền xóa backup.
- Cross-region hoặc cross-account copy cho workload quan trọng.
- Immutable storage hoặc vault lock.
- Backup admin có MFA và quyền tối thiểu.
- Audit log cho thao tác tạo, xóa, restore và thay đổi retention.
- Cơ chế khôi phục catalog và khóa mã hóa độc lập.

Bản sao ở region khác giúp chống một số sự cố vùng, nhưng không tự động chống việc xóa toàn cục nếu cùng danh tính quản trị có quyền trên cả hai nơi.

### 8.2. Nguyên tắc 3-2-1 và biến thể

Quy tắc 3-2-1 thường được diễn giải:

- Có ít nhất 3 bản dữ liệu.
- Lưu trên 2 loại phương tiện hoặc failure domain khác nhau.
- Có ít nhất 1 bản sao ở địa điểm khác.

Một số tổ chức mở rộng thành 3-2-1-1-0:

- Một bản sao offline hoặc immutable.
- Không có lỗi backup chưa được phát hiện qua xác minh.

Đây là nguyên tắc định hướng, không phải công thức bảo đảm an toàn tuyệt đối. Cần điều chỉnh theo dữ liệu, cloud architecture, RPO/RTO và khả năng quản lý.

### 8.3. Bảo vệ danh tính và khóa mã hóa

Backup mã hóa sẽ không thể khôi phục nếu mất khóa hoặc không còn quyền sử dụng khóa.

Kế hoạch recovery cần xác định:

- KMS key hoặc key vault nào mã hóa backup.
- Ai có quyền giải mã trong tình huống khẩn cấp.
- Khóa có phụ thuộc vào account/region đang gặp sự cố không.
- Cách phục hồi key material hoặc quyền truy cập.
- Có cần dual control hoặc break-glass account không.
- Audit và phê duyệt khi sử dụng quyền recovery.

Không lưu private key hoặc secret dạng plaintext trong cùng backup không được bảo vệ. Cần kiểm thử quyền giải mã trong tài khoản recovery.

### 8.4. Bảo vệ backup trước mã độc

Ransomware có thể tìm cách xóa snapshot, mã hóa file backup hoặc chiếm quyền backup service. Các biện pháp:

- Immutable/WORM backup.
- Tách tài khoản và credential.
- MFA, privileged access management và approval.
- Hạn chế xóa recovery point.
- Theo dõi hành vi xóa hàng loạt hoặc thay retention.
- Quét malware trước khi đưa file/VM trở lại production.
- Giữ bản sạch trước thời điểm bị xâm nhập.
- Thực hành khôi phục trong môi trường cô lập.

Không nên restore ngay một bản backup chỉ vì nó mới nhất. Nếu malware đã tồn tại trước đó, bản mới có thể chứa mã độc hoặc persistence.

## 9. Phạm vi backup theo mô hình compute

### 9.1. Máy ảo (VM)

Với VM, cần quyết định bảo vệ:

- Boot disk và OS configuration.
- Data disk và filesystem.
- Database hoặc file application state.
- VM metadata, instance type, NIC, IP và placement.
- Security group, firewall và route.
- IAM role/service identity.
- Image, startup script và configuration management.
- Certificate, secret reference và key dependency.

Có thể dùng image để tái tạo OS và dùng snapshot/native backup để phục hồi dữ liệu. Không nên xem image của một VM là backup đầy đủ nếu data disk, database hoặc external storage nằm ngoài image.

### 9.2. Container và Kubernetes

Container thường được tạo lại từ image, nhưng trạng thái có thể nằm trong persistent volume hoặc external service.

Phạm vi bảo vệ có thể gồm:

- Registry và image digest.
- Manifest, Helm chart, Kustomize hoặc GitOps repository.
- CRD và cấu hình operator.
- Secret manager và certificate.
- Persistent volume snapshot/backup.
- Database, object storage và queue.
- Cluster identity, network policy, RBAC và storage configuration.
- Phiên bản Kubernetes và compatibility của CNI/CSI.

Khôi phục cluster cần kiểm tra thứ tự cài CRD/operator, storage driver, network plugin và workload. Nếu restore PVC trước khi CSI driver sẵn sàng, volume có thể không attach được.

### 9.3. Serverless

Với function hoặc managed compute, phần host thường do nhà cung cấp quản lý theo phạm vi dịch vụ. Khách hàng vẫn cần backup code, artifact, configuration, trigger, IAM, secret và dữ liệu.

Khi khôi phục, cần kiểm tra:

- Runtime còn được hỗ trợ.
- Artifact đúng version/digest.
- Environment variable và secret reference.
- Event trigger và permission.
- Concurrency/quota.
- Network attachment và private endpoint.
- Database và object storage được khôi phục.

### 9.4. GPU và accelerator workload

Với workload GPU, dữ liệu quan trọng có thể gồm model checkpoint, training state, dataset reference, optimizer state, batch progress, driver/runtime compatibility và image.

Không nhất thiết backup toàn bộ GPU memory hoặc VM image thường xuyên. Thường cần checkpoint ở ranh giới an toàn của framework và lưu vào storage bền vững. Khi restore, kiểm tra GPU type, driver, CUDA/runtime và framework compatibility.

## 10. Chiến lược khôi phục và disaster recovery

### 10.1. Restore tại chỗ

Restore in-place đưa dữ liệu hoặc cấu hình về lại tài nguyên hiện tại.

Phù hợp khi:

- Tài nguyên nguồn còn an toàn.
- Sự cố chỉ ảnh hưởng một tập dữ liệu hoặc volume.
- Không cần chuyển failure domain.

Rủi ro là nếu môi trường nguồn bị xâm nhập hoặc hỏng diện rộng, restore tại chỗ có thể đưa dữ liệu về cùng miền sự cố.

### 10.2. Restore sang tài nguyên mới

Có thể tạo VM, volume, database hoặc cluster mới rồi restore vào đó. Cách này cho phép kiểm tra độc lập trước khi thay thế production.

Quy trình điển hình:

1. Chọn recovery point đã xác minh.
2. Tạo network và security boundary cô lập.
3. Provision compute và storage mới.
4. Restore dữ liệu.
5. Khôi phục cấu hình, secret và identity.
6. Kiểm tra tính nhất quán và ứng dụng.
7. Chạy smoke test và kiểm thử nghiệp vụ.
8. Chuyển traffic qua DNS/load balancer.
9. Theo dõi và giữ khả năng quay lại nếu cutover thất bại.

### 10.3. Pilot light

Pilot light giữ một tập thành phần nền tảng ở trạng thái tối thiểu, ví dụ network, database replica hoặc cấu hình cần thiết. Khi sự cố xảy ra, đội ngũ provision thêm compute và capacity.

- Chi phí thường thấp hơn warm standby.
- RTO cao hơn vì còn phải tạo và mở rộng tài nguyên.
- Cần automation và runbook đã kiểm thử.

### 10.4. Warm standby

Warm standby duy trì môi trường recovery có capacity nhỏ hơn production và thường có dữ liệu được đồng bộ hoặc restore định kỳ.

- Có thể tăng capacity nhanh khi cần.
- RTO thường thấp hơn pilot light.
- Có chi phí duy trì compute, storage và replication.
- Cần kiểm tra standby luôn tương thích và có thể nhận traffic.

### 10.5. Active-active hoặc multi-site

Nhiều site cùng phục vụ workload, có thể phân phối traffic và dữ liệu theo thiết kế.

- Có tiềm năng RTO thấp.
- RPO có thể thấp nếu replication đồng bộ hoặc cơ chế nhất quán phù hợp.
- Chi phí và độ phức tạp cao.
- Cần xử lý split-brain, conflict, quorum, failover và failback.

Active-active không có nghĩa mọi lỗi đều tự phục hồi. Một lỗi logic hoặc dữ liệu độc hại có thể lan sang nhiều site.

### 10.6. So sánh mô hình DR

| Mô hình | Mức sẵn sàng của môi trường recovery | RTO tương đối | Chi phí tương đối |
|---|---|---|---|
| Backup và restore | Chỉ có backup, dựng môi trường khi sự cố | Cao hơn | Thấp hơn |
| Pilot light | Một số thành phần nền tảng đã sẵn sàng | Trung bình đến cao | Thấp đến trung bình |
| Warm standby | Môi trường nhỏ đang chạy | Thấp đến trung bình | Trung bình đến cao |
| Active-active | Nhiều site cùng hoạt động | Thấp hơn nếu thiết kế tốt | Cao |

Đây là so sánh tương đối. Kích thước dữ liệu, tốc độ mạng, automation, quota, quy trình phê duyệt và độ phức tạp ứng dụng có thể làm RTO thực tế khác đáng kể.

## 11. Quy trình khôi phục một workload

### 11.1. Chuẩn bị trước sự cố

Cần có sẵn:

- Inventory và dependency map.
- RPO/RTO đã phê duyệt.
- Backup policy và retention.
- Runbook restore theo từng thành phần.
- IaC và artifact versioned.
- Tài khoản recovery và quyền truy cập.
- KMS key và hướng dẫn giải mã.
- DNS/load balancer cutover plan.
- Người ra quyết định và kênh liên lạc.
- Bằng chứng restore test gần nhất.

### 11.2. Các bước thực hiện

~~~mermaid
flowchart TD
    A["Phát hiện và phân loại sự cố"]
    B["Quyết định kích hoạt recovery"]
    C["Chọn recovery point phù hợp RPO"]
    D["Chuẩn bị account, key, network và quota"]
    E["Provision compute/storage"]
    F["Restore dữ liệu và cấu hình"]
    G["Kiểm tra consistency và dependency"]
    H["Smoke test và xác nhận nghiệp vụ"]
    I["Cutover traffic"]
    J["Theo dõi, đối soát và đóng sự cố"]
    A --> B --> C --> D --> E --> F --> G --> H --> I --> J
~~~

Mỗi bước cần owner, thời hạn và tiêu chí hoàn tất. Nếu recovery point không hợp lệ, phải quay lại chọn điểm khác thay vì tiếp tục một quy trình restore không thể hoàn tất.

### 11.3. Thứ tự khôi phục dependency

Một thứ tự phổ biến:

1. Identity, quyền truy cập recovery và khóa mã hóa.
2. Network, DNS, route, firewall và private endpoint.
3. Storage, database và message infrastructure.
4. Compute platform, Kubernetes hoặc runtime.
5. Application artifact, configuration và secret.
6. Worker, scheduler, integration và background jobs.
7. Load balancer, ingress và traffic routing.
8. Monitoring, logging, alert và backup policy.

Đây là thứ tự tham khảo, không phải chuỗi cứng cho mọi kiến trúc. Network có thể phải được khôi phục trước để truy cập identity hoặc KMS; một số nền tảng cần break-glass identity trước khi tạo network. Runbook phải mô tả dependency thật và chuẩn bị quyền truy cập khẩn cấp được kiểm soát.

### 11.4. Failback

Sau khi chạy trên môi trường recovery, có thể cần quay lại site chính. Failback cũng là một migration có rủi ro:

- Xác định site nào đang là nguồn ghi dữ liệu.
- Đồng bộ thay đổi phát sinh trong thời gian DR.
- Kiểm tra replication lag và consistency.
- Dừng hoặc chuyển traffic theo trình tự.
- Chuyển quyền ghi/leader.
- Xác minh ứng dụng và dữ liệu sau cutback.
- Giữ bản sao recovery cho tới khi hoàn tất đối soát.

Không được bật ghi đồng thời ở cả hai nơi nếu hệ thống không hỗ trợ multi-writer và conflict resolution.

## 12. Backup và migration

### 12.1. Backup phục vụ migration như thế nào?

Backup cung cấp điểm quay lui trước khi chuyển workload. Trước migration, cần:

- Backup dữ liệu và cấu hình.
- Xác minh backup hoàn tất và có thể restore.
- Ghi lại phiên bản ứng dụng, schema và runtime.
- Kiểm tra tương thích CPU architecture, OS, driver và storage.
- Xác định RPO trong thời gian cutover.
- Chuẩn bị kế hoạch rollback và thời điểm hết hiệu lực.

Backup chỉ là một phần của migration plan. Cần kiểm tra data transfer, delta sync, DNS, network, IAM và khả năng chạy đồng thời hai môi trường.

### 12.2. Cold migration

Cold migration dừng workload nguồn, sao chép dữ liệu và khởi động ở đích.

- Dễ kiểm soát tính nhất quán khi nguồn đã dừng ghi.
- Có thể đơn giản hơn về đồng bộ dữ liệu.
- Downtime phụ thuộc kích thước dữ liệu và tốc độ transfer.

### 12.3. Warm migration

Warm migration sao chép dữ liệu trong khi nguồn vẫn hoạt động, sau đó đồng bộ phần thay đổi cuối và cutover.

Quy trình:

1. Tạo baseline copy.
2. Bật replication hoặc delta sync.
3. Theo dõi lag.
4. Chuẩn bị môi trường đích và chạy test không ghi production.
5. Tạm dừng ghi hoặc đưa nguồn vào read-only.
6. Đồng bộ delta cuối.
7. Xác minh consistency.
8. Chuyển traffic/ownership.
9. Theo dõi và giữ phương án rollback.

### 12.4. Live migration

Live migration cố gắng chuyển workload với thời gian gián đoạn rất thấp, có thể dựa trên replication liên tục, state transfer hoặc tính năng của hypervisor/cloud.

Không phải mọi VM, database hoặc ứng dụng đều hỗ trợ live migration. Có thể bị giới hạn bởi thiết bị gắn trực tiếp, accelerator, storage, network hoặc khác biệt hypervisor. Cần kiểm tra compatibility matrix và đo downtime thực tế.

### 12.5. Cutover và rollback

Trước cutover:

- Đóng băng thay đổi schema hoặc deploy nếu cần.
- Xác định nguồn dữ liệu có quyền ghi.
- Giảm TTL DNS trước theo kế hoạch nếu dùng DNS cutover.
- Kiểm tra endpoint và certificate ở môi trường đích.
- Chuẩn bị cách chuyển traffic ngược.

Rollback sau khi đích đã nhận ghi không đơn giản là đổi DNS về nguồn. Cần đồng bộ dữ liệu mới từ đích về nguồn hoặc chấp nhận một điểm mất dữ liệu đã được phê duyệt. Nếu không có reverse replication, rollback có thể gây mất các giao dịch phát sinh sau cutover.

## 13. Kiểm thử khả năng khôi phục

### 13.1. Backup thành công không chứng minh restore thành công

Job backup có thể báo thành công nhưng:

- Backup thiếu file hoặc transaction log.
- Encryption key không truy cập được.
- Catalog bị hỏng.
- Image không tương thích.
- Network hoặc quota không đủ để provision.
- Quyền restore khác quyền backup.
- Quy trình khôi phục thiếu bước thủ công.
- Ứng dụng khởi động nhưng dữ liệu không nhất quán.

Vì vậy, cần kiểm thử restore định kỳ trong môi trường cô lập.

### 13.2. Các cấp độ kiểm thử

- **Backup verification:** kiểm tra job, checksum, catalog, encryption và metadata.
- **File-level restore:** khôi phục một file hoặc object để xác nhận khả năng đọc.
- **Volume/database restore:** khôi phục một volume hoặc database tới môi trường thử.
- **Application recovery test:** dựng các dependency và chạy smoke test.
- **Full DR exercise:** mô phỏng mất site hoặc account và khôi phục theo runbook.
- **Failback exercise:** diễn tập đồng bộ và chuyển về môi trường chính.

Cần kiểm tra dữ liệu nghiệp vụ, không chỉ trạng thái dịch vụ.

### 13.3. Diễn tập theo kịch bản

Một số kịch bản:

- Xóa nhầm một file hoặc object.
- Database bị lỗi logic hoặc xóa nhầm bảng.
- Volume bị hỏng.
- VM hoặc node mất hoàn toàn.
- Region hoặc zone không khả dụng.
- Credential production bị xâm nhập.
- Ransomware mã hóa dữ liệu và snapshot.
- KMS key hoặc quyền truy cập key bị mất.
- Backup catalog không truy cập được.
- Một phiên bản ứng dụng mới gây hỏng dữ liệu.

Mỗi lần diễn tập nên ghi lại RPO/RTO thực tế, lỗi runbook, quyền thiếu, dependency thiếu và hành động cải tiến.

### 13.4. Kiểm thử an toàn

Restore vào môi trường cô lập trước khi đưa vào production, nhất là khi nghi ngờ malware hoặc dữ liệu bị xâm nhập. Không để hệ thống phục hồi tự động kết nối vào mạng production khi chưa kiểm tra image, file và credential.

Dùng dữ liệu thử phù hợp, kiểm soát quyền truy cập và xóa môi trường thử theo retention policy sau khi diễn tập.

## 14. Ví dụ thiết kế backup cho dịch vụ API

Một dịch vụ API có:

- 6 VM stateless chạy ứng dụng.
- Managed relational database lưu giao dịch.
- Object storage lưu file người dùng.
- Queue xử lý tác vụ nền.
- Secret manager lưu credential.
- Load balancer và private network.

Yêu cầu kinh doanh đặt mục tiêu minh họa RPO 15 phút và RTO 2 giờ.

Thiết kế có thể gồm:

| Thành phần | Phạm vi bảo vệ | Cơ chế gợi ý |
|---|---|---|
| VM API | OS/runtime và cấu hình nền | Golden image, IaC, artifact versioned |
| Database | Data và transaction log | PITR/log backup, backup định kỳ, restore test |
| Object storage | File và metadata | Versioning, replication hoặc backup độc lập |
| Queue | Message chưa xử lý và trạng thái consumer | Retention đủ dài, replay, checkpoint |
| Secret | Secret reference, key và quyền truy cập | Secret manager, key recovery plan, break-glass |
| Network | Subnet, route, firewall, DNS | IaC và bản cấu hình versioned |
| Load balancer | Listener, target, health check, certificate binding | IaC và cấu hình được lưu |
| Observability | Alert, dashboard, log routing | IaC/export và agent config |

Quy trình DR:

1. Chọn recovery point database không cũ hơn mục tiêu RPO.
2. Xác minh object version và queue retention.
3. Tạo network recovery trong account/region được phê duyệt.
4. Khôi phục key access, secret và IAM.
5. Provision database và restore PITR.
6. Tạo VM từ image đã kiểm thử, deploy đúng artifact.
7. Cấu hình queue consumer ở chế độ chưa nhận message.
8. Kiểm tra API, dữ liệu giao dịch, file và quyền.
9. Chuyển traffic qua load balancer/DNS.
10. Bật worker, theo dõi queue lag và đối soát giao dịch.

Cần đo thời gian từng bước trong diễn tập. Nếu restore database mất 90 phút và các bước khác mất 50 phút, thiết kế chưa đạt RTO 2 giờ; cần tối ưu kích thước/kiến trúc restore hoặc dùng standby phù hợp hơn.

## 15. Tối ưu chi phí mà vẫn đáp ứng RPO/RTO

### 15.1. Chi phí của backup

Các yếu tố chính:

- Dung lượng dữ liệu và tốc độ tăng.
- Tần suất backup và số recovery point.
- Retention và lớp lưu trữ.
- Cross-region/cross-account copy.
- Data transfer và API request.
- Restore test và môi trường recovery.
- KMS, catalog và monitoring.
- Chi phí vận hành và diễn tập.

### 15.2. Chọn lớp lưu trữ

Dữ liệu backup có thể được phân tầng:

- Recovery point mới cần restore nhanh: lớp truy cập thường xuyên.
- Bản trung hạn: lớp lưu trữ ít truy cập.
- Bản dài hạn: archive với thời gian truy xuất và chi phí restore phù hợp.

Không nên chuyển toàn bộ backup sang archive rẻ nhất nếu RTO yêu cầu khôi phục trong vài phút. Cần tính thời gian retrieval, phí truy xuất, minimum storage duration và khả năng giải mã.

### 15.3. Tối ưu phạm vi

- Không backup cache hoặc scratch data có thể tái tạo nếu đã xác minh.
- Dùng IaC và artifact repository cho thành phần có thể build lại.
- Dùng native database backup và log backup thay vì snapshot thô khi cần PITR.
- Dùng incremental hoặc deduplication nếu phù hợp.
- Chọn retention theo yêu cầu pháp lý và nghiệp vụ.
- Kiểm tra bản sao dư thừa và orphaned snapshot.
- Tự động dọn dữ liệu hết hạn theo policy được phê duyệt.

Không loại dữ liệu khỏi phạm vi chỉ để giảm chi phí nếu chưa có owner xác nhận khả năng tái tạo và mức chấp nhận mất dữ liệu.

### 15.4. Tối ưu RTO

Có thể giảm thời gian recovery bằng cách:

- Dùng IaC để provision nhanh.
- Chuẩn bị image và artifact sẵn.
- Tạo sẵn network, quota và role recovery.
- Duy trì warm standby cho workload quan trọng.
- Parallelize các bước độc lập.
- Dùng snapshot/replica phù hợp.
- Tự động hóa kiểm tra và cutover.
- Diễn tập để loại bỏ bước thủ công không cần thiết.

Tăng mức tự động hóa có thể giảm RTO nhưng cần kiểm soát quyền, approval và điều kiện kích hoạt để tránh recovery sai môi trường.

## 16. Những sai lầm thường gặp

**Đồng nhất RPO với lịch backup.** Lịch chạy không bảo đảm recovery point hợp lệ. Cần tính tuổi của bản sao đã hoàn tất và restore được.

**Đồng nhất RTO với thời gian restore file.** RTO còn bao gồm quyết định, provision, dependency, validation và traffic cutover.

**Chỉ backup VM boot disk.** Database, data volume, object, queue và secret có thể nằm ngoài image.

**Dựa hoàn toàn vào replication.** Lỗi logic, xóa nhầm và ransomware có thể được nhân bản. Cần backup có lịch sử và retention độc lập.

**Chỉ backup trong cùng tài khoản.** Kẻ tấn công hoặc lỗi quyền có thể xóa cả production và backup. Cần tách failure domain và danh tính quản trị.

**Không bảo vệ khóa mã hóa.** Backup tồn tại nhưng không giải mã được thì không có giá trị phục hồi.

**Không kiểm tra tính nhất quán.** Snapshot nhiều volume ở các thời điểm khác nhau có thể không tạo ra một database có thể phục hồi.

**Không restore thử.** Backup job thành công không chứng minh dữ liệu, catalog, key và runbook đều dùng được.

**Không tính dependency.** Có compute và database nhưng thiếu DNS, IAM, certificate, secret hoặc quota vẫn không thể chạy ứng dụng.

**Không có kế hoạch failback.** Chuyển sang DR site có thể thành công nhưng quay về site chính gây split-brain hoặc mất dữ liệu mới.

**Giữ retention quá ngắn hoặc quá dài.** Quá ngắn làm mất điểm sạch để quay lại; quá dài tăng chi phí và thời gian lưu dữ liệu nhạy cảm.

**Không đo RPO/RTO qua diễn tập.** Mục tiêu trên tài liệu có thể khác xa thời gian phục hồi thực tế.

## 17. Checklist xây dựng phạm vi backup và recovery

### Mục tiêu và phạm vi

- [ ] Có BIA và owner cho từng workload.
- [ ] RPO/RTO được phê duyệt theo mức độ quan trọng.
- [ ] Xác định dữ liệu persistent, ephemeral và có thể tái tạo.
- [ ] Lập dependency map gồm compute, storage, database, network, IAM, secret và key.
- [ ] Xác định recovery point và tiêu chí dịch vụ được xem là phục hồi.

### Backup và bảo vệ bản sao

- [ ] Chọn backup, snapshot, log backup, PITR hoặc replication phù hợp.
- [ ] Kiểm tra application consistency và multi-volume consistency.
- [ ] Đặt lịch, retention và lifecycle policy.
- [ ] Lưu catalog và metadata cần cho restore.
- [ ] Tách backup khỏi failure domain của production.
- [ ] Bật immutable retention hoặc cơ chế chống xóa khi phù hợp.
- [ ] Bảo vệ credential, KMS key và quyền recovery.
- [ ] Theo dõi job lỗi, replication lag và tuổi recovery point.

### Khôi phục và diễn tập

- [ ] Có runbook restore từng thành phần và thứ tự dependency.
- [ ] Có IaC, image, artifact và cấu hình đúng phiên bản.
- [ ] Kiểm tra quota, network và quyền ở môi trường recovery.
- [ ] Restore thử file, volume, database và ứng dụng.
- [ ] Đo RPO/RTO thực tế và so sánh với mục tiêu.
- [ ] Diễn tập mất zone/region, xóa nhầm và ransomware.
- [ ] Có kế hoạch cutover, failback và đối soát dữ liệu.
- [ ] Ghi nhận lỗi và cập nhật runbook sau mỗi lần diễn tập.

## 18. Ghi nhớ

- **RPO** xác định mức mất dữ liệu tối đa có thể chấp nhận; **RTO** xác định thời gian tối đa để khôi phục dịch vụ.
- RPO thực tế dựa trên recovery point hợp lệ gần nhất, không chỉ lịch chạy backup.
- RTO bao gồm phát hiện, quyết định, provision, restore, validation và traffic cutover.
- Phạm vi backup phải bao gồm dữ liệu, artifact, cấu hình và dependency cần để dựng lại workload.
- VM image, container image và serverless code không tự chứa toàn bộ trạng thái ứng dụng.
- Snapshot, backup, replication và PITR có đặc tính khác nhau; replication không thay thế backup độc lập.
- Cần bảo đảm application consistency, log chain, encryption key và backup catalog.
- Tách bản sao khỏi failure domain production và bảo vệ bằng quyền riêng, immutable retention khi phù hợp.
- Restore test và DR exercise là bằng chứng quan trọng nhất cho khả năng phục hồi.
- Migration cần backup, đồng bộ delta, cutover và kế hoạch failback có kiểm soát.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| RPO | Recovery Point Objective, mức mất dữ liệu tối đa có thể chấp nhận. |
| RTO | Recovery Time Objective, thời gian tối đa để khôi phục dịch vụ. |
| Recovery point | Trạng thái dữ liệu có thể dùng để khôi phục tại một thời điểm. |
| Backup | Bản sao dữ liệu được lưu để khôi phục khi xảy ra sự cố. |
| Snapshot | Ảnh chụp trạng thái volume hoặc tài nguyên tại một thời điểm. |
| Replication | Sao chép dữ liệu sang replica hoặc địa điểm khác. |
| PITR | Point-in-Time Recovery, khôi phục dữ liệu về một thời điểm cụ thể. |
| Transaction log | Nhật ký thay đổi của database dùng để phục hồi hoặc replay giao dịch. |
| Crash-consistent | Trạng thái nhất quán tương tự sau khi hệ thống bị dừng đột ngột. |
| Application-consistent | Trạng thái backup được phối hợp với ứng dụng để bảo đảm dữ liệu hợp lệ. |
| Retention | Khoảng thời gian hoặc chính sách giữ bản backup. |
| Immutable backup | Bản backup được bảo vệ khỏi sửa/xóa trong thời gian khóa. |
| GFS | Grandfather-Father-Son, mô hình retention nhiều tầng theo giờ/ngày/tuần/tháng. |
| BIA | Business Impact Analysis, phân tích tác động kinh doanh khi dịch vụ gián đoạn. |
| Disaster Recovery (DR) | Quy trình và kiến trúc khôi phục sau thảm họa. |
| Pilot light | Mô hình DR giữ sẵn các thành phần nền tảng tối thiểu và mở rộng khi sự cố. |
| Warm standby | Môi trường recovery nhỏ đang chạy và có thể mở rộng khi cần. |
| Active-active | Nhiều site cùng hoạt động để phục vụ workload. |
| Failover | Chuyển workload sang tài nguyên hoặc site thay thế. |
| Failback | Chuyển workload trở lại môi trường chính sau recovery. |
| Cutover | Thời điểm chuyển traffic hoặc quyền ghi từ nguồn sang đích. |
| Checkpoint | Trạng thái tiến độ được lưu để tiếp tục xử lý sau gián đoạn. |
| Recovery catalog | Metadata mô tả các bản backup và cách khôi phục chúng. |
| Failure domain | Phạm vi tài nguyên có thể cùng bị ảnh hưởng bởi một lỗi hoặc sự kiện. |
| WORM | Write Once, Read Many, cơ chế lưu dữ liệu không cho sửa trong điều kiện quy định. |
