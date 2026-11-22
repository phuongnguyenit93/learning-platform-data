# AWS Storage Gateway và tích hợp lưu trữ tại chỗ

Nhiều doanh nghiệp vẫn có ứng dụng chạy tại trung tâm dữ liệu, máy chủ Windows/Linux, hệ thống backup và quy trình xử lý file đã tồn tại nhiều năm. Việc chuyển toàn bộ ứng dụng lên cloud trong một lần có thể tốn kém hoặc không khả thi vì độ trễ, thiết bị, yêu cầu pháp lý, phần mềm cũ và phụ thuộc vận hành. Doanh nghiệp cần một cách để ứng dụng tại chỗ tiếp tục dùng giao thức lưu trữ quen thuộc, trong khi dữ liệu được đưa lên AWS để mở rộng dung lượng, lưu trữ dài hạn hoặc hỗ trợ khôi phục thảm họa.

**AWS Storage Gateway** là dịch vụ lưu trữ hybrid kết hợp dịch vụ AWS với một gateway appliance chạy tại chỗ hoặc trên Amazon EC2. Gateway cung cấp giao diện lưu trữ quen thuộc cho ứng dụng, đồng thời kết nối dữ liệu với các dịch vụ lưu trữ AWS. Tùy loại gateway, ứng dụng có thể truy cập file qua NFS/SMB, block volume qua iSCSI hoặc virtual tape library qua iSCSI.

Trong hệ sinh thái **CLOUD_PROVIDERS_AWS**, Storage Gateway giúp tích hợp hệ thống tại chỗ với Amazon S3, Amazon FSx, Amazon EBS snapshots và các dịch vụ archive. Mục tiêu của module là giúp người học chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí. Vì vậy, cần hiểu chính xác loại gateway, luồng dữ liệu, cache, network, IAM, mã hóa, backup và giới hạn nhất quán trước khi đưa vào production.

## 1. Storage Gateway giải quyết vấn đề gì?

Storage Gateway phù hợp khi ứng dụng tại chỗ cần tiếp tục sử dụng giao thức hoặc quy trình lưu trữ hiện có nhưng doanh nghiệp muốn tận dụng backend lưu trữ AWS.

Các tình huống thường gặp:

- Ứng dụng Linux cần mount một file share NFS nhưng doanh nghiệp muốn lưu file ở Amazon S3.
- Ứng dụng Windows cần SMB share, Active Directory và quyền file tương thích với hệ thống hiện tại.
- Ứng dụng cũ cần một thiết bị block iSCSI và muốn lưu dữ liệu chính hoặc snapshot ở AWS.
- Phần mềm backup hiện có cần ghi ra virtual tape library thay cho băng từ vật lý.
- Doanh nghiệp muốn giữ bản sao dữ liệu ngoài site để hỗ trợ backup và disaster recovery.
- Một nhóm ứng dụng cần truy cập file share Windows trên Amazon FSx qua kết nối hybrid.

Storage Gateway không phải là giải pháp thay thế cho mọi loại lưu trữ. Nếu ứng dụng có thể dùng trực tiếp S3 API, truy cập Amazon EFS hoặc Amazon FSx qua kết nối mạng, có thể không cần gateway. Nếu mục tiêu là chuyển dữ liệu hàng loạt theo lịch, AWS DataSync có thể phù hợp hơn. Hãy bắt đầu từ giao thức mà ứng dụng cần, semantics dữ liệu và yêu cầu latency.

## 2. Các loại Storage Gateway

Storage Gateway có bốn loại gateway chính thường gặp trong kiến trúc hybrid:

| Loại | Giao diện ứng dụng | Backend AWS | Trường hợp sử dụng |
|---|---|---|---|
| S3 File Gateway | NFS hoặc SMB | Amazon S3 | Chia sẻ file tại chỗ, lưu file dưới dạng S3 object |
| FSx File Gateway | SMB | Amazon FSx for Windows File Server | Truy cập file share Windows trên AWS từ client tại chỗ |
| Volume Gateway | iSCSI block volume | Amazon S3 và EBS snapshots | Ứng dụng cần block storage hoặc backup volume |
| Tape Gateway | iSCSI virtual tape library | Amazon S3 và S3 Glacier Flexible Retrieval/Deep Archive | Tích hợp phần mềm backup dùng quy trình tape |

Không nên xem bốn loại là các cấu hình có thể hoán đổi. S3 File Gateway ánh xạ file thành object; FSx File Gateway ánh xạ SMB share tới file system Windows; Volume Gateway cung cấp block device; Tape Gateway mô phỏng tape library và quy trình archive. Mỗi loại có cách lưu trữ, khôi phục và chi phí khác nhau.

## 3. Kiến trúc tổng quát

Gateway appliance chạy trên host hoặc hypervisor tại chỗ, nhận request từ ứng dụng bằng giao thức phù hợp và trao đổi dữ liệu với dịch vụ Storage Gateway qua kết nối mạng tới AWS.

~~~mermaid
flowchart LR
    subgraph OnPrem["Trung tâm dữ liệu tại chỗ"]
      A[Ứng dụng và máy chủ]
      B[Storage Gateway appliance]
      C[Cache / Upload buffer / Local disks]
      A --> B
      B <--> C
    end
    subgraph AWS["AWS Region"]
      D[Storage Gateway service]
      E[S3 / FSx / EBS snapshots / Glacier]
      D --> E
    end
    B <-->|Kết nối được mã hóa| D
~~~

Gateway appliance không phải backend lưu trữ độc lập. Nó cung cấp giao diện cho ứng dụng và quản lý cache, buffer hoặc luồng dữ liệu theo loại gateway. Dữ liệu cuối cùng được lưu tại dịch vụ AWS tương ứng.

### Vai trò của cache và upload buffer

- **Cache storage** giữ dữ liệu thường xuyên được truy cập để giảm latency và giảm số lần đọc qua WAN. Cách sử dụng cache khác nhau giữa File Gateway và Volume Gateway.
- **Upload buffer** là vùng staging cho dữ liệu cần tải lên AWS trong các loại gateway sử dụng cơ chế này. Dung lượng phải đủ cho tốc độ ghi và thời gian gián đoạn kết nối.
- **Local storage** có thể là nơi lưu dữ liệu chính đối với Stored Volume Gateway; không được nhầm với cache của Cached Volume Gateway.

Khi sizing, cần tách dung lượng dữ liệu chính, working set, tốc độ ghi, bandwidth và thời gian WAN có thể mất kết nối. Chọn disk nhỏ hơn chỉ dựa trên dung lượng hiện tại có thể làm gateway hết buffer trong lúc upload bị chậm.

## 4. Triển khai gateway ở đâu?

Storage Gateway có thể chạy dưới dạng virtual appliance tại chỗ hoặc trên Amazon EC2, tùy gateway type và điều kiện hỗ trợ. Các nền tảng ảo hóa được tài liệu hiện hành hỗ trợ gồm VMware ESXi, Microsoft Hyper-V, Linux KVM và một số môi trường khác theo phiên bản được công bố.

Trên EC2, Storage Gateway hỗ trợ triển khai S3 File Gateway, Cached Volume Gateway và Tape Gateway theo điều kiện dịch vụ. Stored Volume Gateway không được hỗ trợ chạy trên EC2 vì mô hình này yêu cầu lưu toàn bộ dữ liệu chính trên local disks tại chỗ.

Trước khi triển khai, kiểm tra:

- Phiên bản hypervisor, hệ điều hành host và yêu cầu CPU/RAM.
- UEFI/boot requirement và cấu hình VM theo image hiện hành.
- Dung lượng, loại và hiệu năng local disks.
- NIC, network path, DNS, NTP và firewall.
- Kết nối tới Storage Gateway service endpoint và backend AWS.
- Khả năng dự phòng host, hypervisor và nguồn điện tại chỗ.
- Hạn mức gateway, volume, tape hoặc file share theo Region.

### Lưu ý về Hardware Appliance

AWS đã ngừng cung cấp mới Storage Gateway Hardware Appliance từ ngày 12 tháng 5 năm 2025. Khách hàng hiện có appliance có thể tiếp tục sử dụng và nhận hỗ trợ tới tháng 5 năm 2028 theo thông báo của AWS. Khi thiết kế triển khai mới trong giai đoạn hiện nay, nên ưu tiên phương án VM appliance hoặc EC2 phù hợp với gateway type và yêu cầu hạ tầng.

Không tạo gateway VM bằng cách clone hoặc restore snapshot hypervisor/AMI của một gateway VM khác. Nếu gateway VM gặp lỗi không thể phục hồi, triển khai và kích hoạt gateway mới rồi khôi phục dữ liệu theo quy trình của loại gateway đó.

## 5. S3 File Gateway là gì?

S3 File Gateway cung cấp giao diện file NFS hoặc SMB cho ứng dụng tại chỗ, trong khi dữ liệu được lưu dưới dạng object trong Amazon S3. Ứng dụng có thể mount file share và đọc/ghi file bằng giao thức quen thuộc mà không cần tự tích hợp S3 API.

S3 File Gateway phù hợp cho:

- File share dùng chung giữa ứng dụng tại chỗ và workflow cloud.
- Nội dung, media, tài liệu và file export.
- Lưu trữ dữ liệu ứng dụng cần truy cập theo giao thức file.
- Đưa dữ liệu file lên S3 để áp dụng lifecycle, replication và analytics.

### Luồng ghi và đọc

Khi client ghi file qua NFS/SMB, gateway ghi dữ liệu vào local cache trước rồi tải file và metadata lên S3 theo cơ chế bất đồng bộ. Khi đọc, gateway phục vụ từ cache nếu dữ liệu đã có; nếu chưa có, gateway đọc từ S3 theo cơ chế read-through.

~~~mermaid
flowchart TD
    A[NFS / SMB client] --> B[S3 File Gateway]
    B --> C{File có trong local cache?}
    C -->|Có| D[Đọc từ cache]
    C -->|Không| E[Đọc object từ S3]
    E --> F[Cập nhật cache]
    B --> G[Nhận ghi file]
    G --> H[Ghi local cache]
    H --> I[Upload dữ liệu và metadata bất đồng bộ]
    I --> J[Amazon S3 object]
~~~

Điểm cần nhớ: khi ứng dụng nhận xác nhận ghi từ gateway, dữ liệu đã được ghi vào local cache; upload lên S3 có thể vẫn đang diễn ra. Nếu yêu cầu là dữ liệu phải có bản sao trên S3 trước khi một workflow tiếp tục, hãy dùng cơ chế upload notification hoặc kiểm tra trạng thái đồng bộ phù hợp.

## 6. NFS và SMB trên S3 File Gateway

S3 File Gateway hỗ trợ NFS và SMB. Chọn giao thức theo hệ điều hành, mô hình xác thực và ứng dụng.

| Tiêu chí | NFS | SMB |
|---|---|---|
| Client thường gặp | Linux/Unix | Windows và ứng dụng hỗ trợ SMB |
| Phiên bản phổ biến | NFSv3, NFSv4.1 | SMBv2, SMBv3 |
| Xác thực | Client access theo IP/network và quyền Unix metadata | Có thể tích hợp Microsoft Active Directory |
| Quyền file | UID/GID và Unix permissions/metadata | Windows ACL và thông tin owner/permissions |
| Use case | Linux application, batch, render và file processing | Windows file share, home directory, ứng dụng Windows |

Với SMB, có thể cấu hình Active Directory, danh sách user/group được phép, guest access theo nhu cầu và audit log. Với NFS, cần giới hạn client CIDR/IP, cấu hình squash và metadata mặc định phù hợp.

Không nên mở SMB/NFS cho toàn bộ mạng nếu chỉ một nhóm server cần truy cập. Dùng network segmentation và file share access policy để giới hạn nguồn.

## 7. S3 object và file semantics

S3 là object storage, không phải POSIX file system hay block device. S3 File Gateway cung cấp một file interface nhưng backend vẫn là object. Do đó, cần hiểu các khác biệt:

- Directory được biểu diễn bằng key/prefix và metadata object.
- Rename, append, truncate hoặc thay đổi metadata có thể tạo thao tác object mới hoặc upload lại phần dữ liệu tương ứng.
- Object được ghi trực tiếp vào bucket từ một client khác không tự động xuất hiện ngay trong cache của gateway.
- Versioning có thể giữ nhiều version khi file được sửa hoặc metadata thay đổi.
- Một số ứng dụng phụ thuộc file locking, rename atomic hoặc semantics POSIX đặc biệt có thể cần kiểm thử tương thích.

Khi S3 Versioning bật, một lần ghi file có thể tạo version cho object data và một version khác khi gateway cập nhật metadata. Các thao tác sửa file hoặc đổi ownership/metadata có thể làm số version tăng. Cần theo dõi noncurrent versions và thiết kế S3 Lifecycle phù hợp; không đặt expiration quá ngắn nếu cần khôi phục hoặc audit.

Không nên để nhiều hệ thống độc lập đồng thời sửa cùng một object qua đường S3 API và file share nếu chưa có quy tắc đồng bộ rõ ràng. AWS khuyến nghị tránh ghi object trực tiếp vào bucket đang được S3 File Gateway quản lý qua workflow ngoài gateway.

### Cache refresh

Nếu một client hoặc dịch vụ khác thêm, xóa hoặc thay object trực tiếp trong bucket, file share có thể vẫn hiển thị inventory đã cache. Có thể dùng `RefreshCache` để cập nhật inventory của file share.

`RefreshCache` không tải toàn bộ object vào local cache; nó cập nhật danh sách object mà gateway nhìn thấy. API trả thành công chỉ có nghĩa thao tác refresh đã được khởi tạo, không bảo đảm refresh đã hoàn tất. Dùng notification hoàn tất refresh trước khi workflow phụ thuộc vào file mới tiếp tục.

Ví dụ:

~~~bash
aws storagegateway refresh-cache \
  --file-share-arn "arn:aws:storagegateway:ap-southeast-1:111122223333:share/share-EXAMPLE"
~~~

Nếu refresh cả bucket hoặc prefix lớn, thao tác có thể tiêu tốn API request, tài nguyên gateway và thời gian. Chỉ refresh phạm vi cần thiết và tránh kích hoạt một lần cho mỗi object trong đợt upload lớn.

## 8. FSx File Gateway là gì?

FSx File Gateway cung cấp SMB access từ client tại chỗ tới file share được lưu trên Amazon FSx for Windows File Server. Nó dùng local cache để giảm độ trễ và giảm lượng dữ liệu phải đọc qua kết nối WAN, trong khi backend là file system Windows được quản lý trên AWS.

Khác biệt quan trọng:

- S3 File Gateway ánh xạ file share tới S3 object.
- FSx File Gateway ánh xạ file share tại chỗ tới SMB shares trên FSx for Windows File Server.

FSx File Gateway phù hợp với ứng dụng Windows cần SMB, Active Directory, Windows ACL và semantics của file system Windows. Nó không phải lựa chọn để biến S3 bucket thành Windows file server.

### Dependency

Để sử dụng FSx File Gateway, cần có FSx for Windows File Server file system và kết nối mạng từ gateway tới FSx. Kết nối hybrid thường dùng AWS Direct Connect hoặc Site-to-Site VPN. Gateway phải tham gia domain Active Directory theo cấu hình, sau đó được liên kết với file system FSx.

Client tại chỗ kết nối SMB tới gateway. Gateway giao tiếp với FSx trong VPC qua kết nối được thiết lập. Cần tính cả DNS, AD domain controller, Kerberos, SMB và các port RPC cần thiết theo tài liệu port requirements.

### Luồng truy cập

~~~mermaid
flowchart LR
    A[Windows client tại chỗ] -->|SMB| B[FSx File Gateway]
    B <--> C[Local cache]
    B -->|VPN / Direct Connect| D[Amazon FSx for Windows File Server]
    D --> E[Windows file system]
    B --- F[Active Directory]
~~~

FSx File Gateway cung cấp truy cập low-latency tới working set thường dùng, nhưng hiệu năng phụ thuộc cache hit, băng thông WAN, latency và throughput của FSx. Kiểm tra file locking, quyền AD và failover behavior với ứng dụng thực tế.

## 9. Volume Gateway là gì?

Volume Gateway cung cấp block storage qua iSCSI target để ứng dụng tại chỗ truy cập như một disk. Dữ liệu được tích hợp với Amazon S3 và có thể được bảo vệ bằng snapshot lưu dưới dạng Amazon EBS snapshots.

Volume Gateway có hai cấu hình:

- **Cached volumes:** Amazon S3 là nơi lưu dữ liệu chính; gateway giữ phần dữ liệu thường truy cập trong local cache.
- **Stored volumes:** toàn bộ dữ liệu được lưu tại chỗ trên local disks; gateway tải snapshot bất đồng bộ lên AWS để có bản sao ngoài site.

Hai cấu hình có mô hình dữ liệu và yêu cầu local storage khác nhau. Chọn dựa trên việc doanh nghiệp muốn giữ toàn bộ data set tại chỗ hay muốn dùng S3 làm backend chính.

## 10. Cached volumes và Stored volumes

| Tiêu chí | Cached volumes | Stored volumes |
|---|---|---|
| Nơi lưu dữ liệu chính | Amazon S3 | Local disks tại chỗ |
| Local cache | Giữ dữ liệu thường truy cập | Không dùng theo mô hình cache volume |
| Upload buffer | Có | Có |
| Giao thức client | iSCSI | iSCSI |
| Backup trên AWS | EBS snapshots | EBS snapshots |
| Phù hợp | Muốn giảm dung lượng lưu trữ tại chỗ, working set nhỏ hơn toàn bộ data set | Cần latency thấp cho toàn bộ dữ liệu và muốn backup off-site |
| Phụ thuộc WAN | Cao hơn cho dữ liệu cache miss và upload | Chủ yếu cho upload snapshot và quản lý |

### Cached volumes

Ứng dụng ghi vào iSCSI volume. Gateway giữ dữ liệu ghi trong upload buffer và chuyển lên S3; cache giữ các block được truy cập gần đây. Ứng dụng có thể truy cập nhanh working set trong cache, nhưng cache miss cần lấy dữ liệu từ AWS qua mạng.

### Stored volumes

Ứng dụng ghi dữ liệu vào local disks được gán cho gateway. Gateway tạo snapshot theo lịch hoặc theo yêu cầu và tải thay đổi lên AWS. Cách này giữ hiệu năng truy cập local cho toàn bộ data set, nhưng cần dung lượng local đủ lớn và có kế hoạch bảo vệ disk tại chỗ.

### Ví dụ lựa chọn

Một ứng dụng xử lý file video có tập dữ liệu lớn nhưng chỉ truy cập một phần file thường xuyên có thể phù hợp cached volumes. Một ứng dụng database cũ cần truy cập toàn bộ block data với latency thấp tại trung tâm dữ liệu có thể xem xét stored volumes, nhưng phải kiểm tra tính tương thích của database, iSCSI và yêu cầu nhất quán.

## 11. iSCSI và tích hợp ứng dụng

Volume Gateway trình bày iSCSI target cho application server. Máy chủ tại chỗ cấu hình iSCSI initiator, kết nối tới target và nhận block device. Sau đó hệ điều hành có thể tạo partition và file system theo cách ứng dụng yêu cầu.

Các điểm cần thiết kế:

- iSCSI initiator và target có kết nối ổn định qua mạng LAN.
- Network ACL/firewall chỉ cho phép initiator được phê duyệt.
- Dùng multipathing khi kiến trúc và gateway hỗ trợ để tăng khả năng chịu lỗi.
- Theo dõi session, latency, throughput và queue depth.
- Không mount cùng một volume read-write từ nhiều host nếu ứng dụng/file system không hỗ trợ cluster coordination.
- Bảo đảm quy trình shutdown và detach volume đúng cách.

Volume Gateway phù hợp với ứng dụng cần block device nhưng không tự động biến một workload thành ứng dụng cloud-native. Cần kiểm thử database consistency, file system recovery và behavior khi gateway mất kết nối.

## 12. Snapshot và AWS Backup cho Volume Gateway

Volume Gateway hỗ trợ tạo snapshot một lần hoặc theo lịch. Snapshot được lưu dưới dạng Amazon EBS snapshots trong AWS và chỉ lưu phần dữ liệu thay đổi so với snapshot trước theo cơ chế incremental.

Có thể dùng:

- Snapshot schedule tích hợp trong Storage Gateway.
- AWS Backup để quản lý backup plan, retention, audit và restore tập trung.

AWS Backup hỗ trợ backup và restore cho cả cached volumes và stored volumes. Recovery point có thể được restore thành Storage Gateway volume hoặc Amazon EBS volume tùy mục đích.

### Quy trình backup tham khảo

1. Xác định RPO và cửa sổ backup.
2. Kiểm tra upload buffer, trạng thái volume và kết nối AWS.
3. Tạo backup plan hoặc snapshot schedule.
4. Đặt retention và copy sang account/Region khác nếu cần.
5. Theo dõi backup job và recovery point.
6. Thử restore định kỳ vào gateway hoặc EBS.
7. Kiểm tra dữ liệu, application consistency và quyền KMS.

Snapshot volume không tự bảo đảm application consistency cho mọi database. Với workload cần quiesce I/O hoặc transaction consistency, phối hợp snapshot với quy trình backup của ứng dụng.

## 13. Tape Gateway là gì?

Tape Gateway cung cấp virtual tape library (VTL) cho phần mềm backup tại chỗ. Backup application nhìn thấy tape drives và media changer qua iSCSI, sau đó ghi dữ liệu vào virtual tapes. Gateway lưu dữ liệu tape trên Amazon S3 và có thể archive tape tới S3 Glacier Flexible Retrieval hoặc S3 Glacier Deep Archive.

Tape Gateway hữu ích khi doanh nghiệp đã đầu tư vào phần mềm backup sử dụng tape workflow và muốn chuyển kho lưu trữ băng từ sang cloud mà không thay đổi toàn bộ quy trình.

### Các thành phần

- **Virtual tape library (VTL):** nơi backup software nhìn thấy các virtual tapes sẵn sàng ghi/đọc.
- **Tape drives:** thiết bị iSCSI mà backup application sử dụng để đọc/ghi.
- **Media changer:** mô phỏng robot nạp và tháo tape trong thư viện.
- **Virtual tape shelf (VTS):** nơi tape được archive để lưu trữ dài hạn.

Khi backup software eject tape, Tape Gateway upload dữ liệu rồi archive tape vào pool đã chọn. Tape trong archive không thể đọc trực tiếp; cần retrieve tape về Tape Gateway trước khi restore.

## 14. Archive và retrieval của Tape Gateway

Khi tạo virtual tape, chọn archive pool:

| Archive pool | Backend | Mục đích |
|---|---|---|
| Glacier Pool | S3 Glacier Flexible Retrieval | Lưu trữ dài hạn, có nhu cầu retrieve định kỳ |
| Deep Archive Pool | S3 Glacier Deep Archive | Lưu trữ rất dài hạn, hiếm khi truy xuất |

Thời gian retrieve tham khảo theo tài liệu AWS:

- Tape ở S3 Glacier Flexible Retrieval thường mất khoảng 3–5 giờ để retrieve.
- Tape ở S3 Glacier Deep Archive thường mất khoảng 12 giờ.

Thời gian thực tế và chi phí phụ thuộc archive tier, loại retrieval, kích thước tape và trạng thái hệ thống. Không dùng archive pool cho dữ liệu cần khôi phục ngay trong vài phút.

Quy trình restore:

1. Xác định barcode và trạng thái tape trong VTL.
2. Yêu cầu retrieve tape từ archive về một Tape Gateway trong cùng Region.
3. Chờ trạng thái tape chuyển sang AVAILABLE.
4. Dùng backup software để mount/đọc tape và khôi phục dữ liệu.
5. Xác minh dữ liệu và ghi lại thời gian/chi phí retrieval.

Tape được retrieve từ archive có trạng thái write-protected; mục đích là đọc dữ liệu đã lưu. Hãy kiểm thử restore trước khi cam kết RTO với nghiệp vụ.

## 15. Tích hợp với phần mềm backup

Tape Gateway được thiết kế để làm việc với các ứng dụng backup hỗ trợ VTL/iSCSI. AWS duy trì danh sách ứng dụng bên thứ ba được hỗ trợ và tài liệu cấu hình cho một số sản phẩm.

Trước khi chọn, kiểm tra:

- Phiên bản backup software có nằm trong danh sách tương thích.
- Cách phần mềm quản lý media changer, barcode và tape pool.
- Quy trình eject/export tape để bắt đầu archive.
- Cách xử lý tape đầy, tape hết hạn và media rotation.
- Catalog backup được bảo vệ ở đâu và có thể khôi phục độc lập không.
- Cách backup application phục hồi khi gateway thay thế hoặc Region mất kết nối.

Ví dụ, AWS có hướng dẫn cấu hình Veeam Backup & Replication với Tape Gateway. Tuy nhiên, các thao tác cụ thể phụ thuộc version phần mềm và chính sách backup của tổ chức; hãy dùng hướng dẫn của nhà cung cấp cùng danh sách hỗ trợ hiện hành.

Với Volume Gateway, ứng dụng backup có thể sử dụng snapshot của Storage Gateway hoặc AWS Backup. Với S3 File Gateway, dữ liệu cuối cùng là S3 object nên có thể áp dụng S3 Versioning, lifecycle, replication và cơ chế backup S3 phù hợp.

## 16. Kết nối mạng hybrid

Gateway cần kết nối tới ứng dụng tại chỗ và các endpoint AWS. Thiết kế network phải đáp ứng cả luồng dữ liệu, quản trị và đồng bộ.

### Luồng client tới gateway

| Loại gateway | Giao thức chính | Cổng thường dùng |
|---|---|---:|
| S3 File Gateway NFS | NFS | TCP 2049; một số phiên bản/hoạt động cần thêm dịch vụ RPC liên quan |
| S3 File Gateway SMB | SMB | TCP 445 |
| FSx File Gateway | SMB | TCP 445; thêm port Active Directory theo cấu hình |
| Volume Gateway | iSCSI | TCP 3260 |
| Tape Gateway | iSCSI | TCP 3260 |

Đây là các cổng giao thức chính, không phải danh sách firewall hoàn chỉnh. Cần kiểm tra trang port requirements theo loại gateway và phiên bản để mở đúng DNS, NTP, activation, service endpoint, AD/Kerberos/LDAP/RPC và các kết nối cần thiết.

### Gateway tới AWS

Gateway cần DNS/NTP hoạt động và kết nối HTTPS tới Storage Gateway service endpoint. Nếu dùng private connectivity, có thể thiết kế VPC endpoint và network path phù hợp với tài liệu dịch vụ. Không giả định gateway có thể upload dữ liệu khi mất toàn bộ đường truyền tới AWS; cache/upload buffer chỉ hấp thụ được một lượng dữ liệu hữu hạn.

Gateway thường cần outbound HTTPS qua TCP 443 tới các endpoint dịch vụ AWS và những endpoint phụ trợ được liệt kê trong port requirements. Giới hạn outbound theo endpoint/Region phù hợp với loại gateway, đồng thời cho phép DNS và NTP tới hạ tầng được phê duyệt. Không mở toàn bộ outbound nếu có thể dùng danh sách endpoint cụ thể.

### Direct Connect hay Site-to-Site VPN?

| Tiêu chí | AWS Site-to-Site VPN | AWS Direct Connect |
|---|---|---|
| Kết nối | Tunnel mã hóa qua Internet | Kết nối mạng riêng tới AWS |
| Thời gian triển khai | Thường nhanh hơn | Cần nhà cung cấp/đường truyền và cấu hình |
| Độ ổn định latency | Phụ thuộc Internet và đường đi | Thường ổn định, có thể chọn bandwidth |
| Mã hóa | IPsec | Không tự động mã hóa ở lớp vật lý; cân nhắc MACsec hoặc VPN overlay khi yêu cầu |
| Phù hợp | Workload vừa, backup, kết nối dự phòng | Lưu lượng lớn, latency ổn định, hybrid lâu dài |

Có thể dùng VPN làm đường dự phòng cho Direct Connect. Dù chọn cách nào, hãy đo throughput thực tế, packet loss, latency và chi phí data transfer.

## 17. Bảo mật dữ liệu và quyền truy cập

Storage Gateway nằm giữa mạng doanh nghiệp và cloud nên cần kiểm soát cả client, gateway và backend.

### IAM và S3

Với S3 File Gateway, file share sử dụng IAM role để truy cập bucket/prefix. Role cần quyền tối thiểu cho thao tác cần thiết; bucket policy nên giới hạn gateway, account và encryption requirements. Không dùng quyền S3 rộng nếu chỉ cần một prefix.

### Active Directory và file permissions

Với SMB, tích hợp Active Directory và giới hạn user/group. Với NFS, giới hạn client IP/CIDR và metadata UID/GID/Unix permissions. Không cho phép guest access nếu ứng dụng không yêu cầu.

### Encryption

- Dữ liệu truyền giữa gateway và AWS được bảo vệ bằng TLS theo cơ chế dịch vụ.
- S3 object có thể được mã hóa bằng SSE-S3 hoặc SSE-KMS theo cấu hình file share và yêu cầu bucket.
- Volume/Tape và backup cần được kiểm tra encryption key, key policy và quyền restore.
- Local disks, host, hypervisor và network nội bộ cũng cần bảo vệ theo chính sách của tổ chức.

KMS key là dependency quan trọng. Nếu key bị disabled, policy mất quyền hoặc key bị lên lịch xóa, dữ liệu đã mã hóa có thể không restore được. Đưa key ARN, Region, owner và quy trình khôi phục quyền vào runbook DR.

### Audit

Bật CloudTrail để theo dõi API quản trị Storage Gateway, S3 và AWS Backup. Với SMB, bật audit logging phù hợp nếu cần ghi nhận truy cập file. Lưu log ở nơi tách quyền và retention phù hợp.

## 18. Hiệu năng, sizing và cache

Hiệu năng gateway phụ thuộc host CPU/RAM, local disk, NIC, cache hit, upload buffer, network bandwidth và đặc tính workload.

### Sizing cần xem xét

- Working set: phần dữ liệu thường được đọc lại.
- Write rate: lượng dữ liệu ghi mới trong giờ cao điểm.
- Upload backlog: lượng dữ liệu có thể tồn tại khi WAN chậm hoặc mất kết nối.
- Cache hit ratio: tỷ lệ request được phục vụ từ local cache.
- Concurrent clients: số client và số operation đồng thời.
- File size distribution: nhiều file nhỏ có thể tạo overhead metadata; file lớn có thể ảnh hưởng upload throughput.
- Gateway VM CPU/RAM và local storage latency.

Không dùng một VM cấu hình tối thiểu cho mọi workload. Dựa trên sizing guidance của từng gateway, sau đó load test bằng file size, concurrency và pattern truy cập giống production.

### Cache metrics

Với S3 File Gateway, các metric như CacheHitPercent, CachePercentUsed, CacheFree và CloudBytesUploaded/Downloaded giúp đánh giá cache và network. Với Volume Gateway, theo dõi cache, upload buffer, read/write latency và throughput theo loại volume.

Nếu CacheHitPercent thấp, có thể cần tăng cache, cải thiện working set locality hoặc xem lại pattern truy cập. Nếu CachePercentDirty tăng lâu, dữ liệu đang chờ upload; kiểm tra bandwidth, upload throughput, network errors và buffer capacity.

## 19. Giám sát và vận hành gateway

Amazon CloudWatch cung cấp metric và alarm cho Storage Gateway. Cần giám sát cả gateway health lẫn tài nguyên liên quan.

| Nhóm | Chỉ số hoặc trạng thái | Ý nghĩa |
|---|---|---|
| Gateway health | Gateway status, health notifications | Gateway có hoạt động bình thường không |
| Cache | CacheHitPercent, CachePercentUsed, CacheFree | Working set có phù hợp và cache có sắp đầy không |
| Upload | UploadBufferPercentUsed, CloudBytesUploaded | Dữ liệu đang chờ upload hay upload có bị chậm không |
| Download | CloudBytesDownloaded, read latency | Cache miss và nhu cầu đọc từ AWS |
| Volume | Read/WriteBytes, IOPS, latency, snapshot status | Hiệu năng block volume và tiến độ backup |
| File share | File share status, upload notification, refresh status | File share có sẵn sàng và đồng bộ không |
| Tape | Tape status, archive/retrieval progress | Tape có sẵn sàng để ghi/đọc hoặc archive không |

Storage Gateway metrics được ghi trong CloudWatch theo retention của dịch vụ; không nên xem chúng là log lưu trữ dài hạn. Nếu cần phân tích nhiều tháng, export metric hoặc xây dựng dashboard/retention riêng.

### Cảnh báo nên có

- Gateway chuyển sang trạng thái không khả dụng.
- Cache gần đầy hoặc cache hit giảm bất thường.
- Upload buffer tăng liên tục hoặc gần đầy.
- Upload/download throughput giảm dưới baseline.
- Snapshot job hoặc backup job thất bại.
- File share không ở trạng thái AVAILABLE.
- RefreshCache không hoàn tất trong thời gian dự kiến.
- Tape archive/retrieval bị treo hoặc quá thời gian.

## 20. Cập nhật, HA và khôi phục gateway

Gateway appliance cần được cập nhật phần mềm và bảo trì. Lập lịch maintenance window, kiểm tra release notes và theo dõi trạng thái sau cập nhật. Không tự ý thay đổi cấu hình hypervisor hoặc local disks đang được gateway sử dụng.

### VMware HA

Storage Gateway hỗ trợ tích hợp VMware vSphere High Availability với application-level health checks cho một số triển khai VMware. Khi host gặp lỗi, vSphere HA có thể khởi động lại VM trên host khác trong cluster. Đây là một lớp HA cho gateway appliance, không thay thế backup dữ liệu hay DR cho Region.

### Khôi phục khi gateway lỗi

Quy trình khác nhau theo gateway type:

- S3 File Gateway: tạo/activate gateway mới, gắn file share và kiểm tra cache/inventory theo quy trình khôi phục.
- Volume Gateway: có thể khôi phục từ EBS snapshot hoặc recovery point; với cached volume có thể tạo recovery snapshot theo hướng dẫn.
- Tape Gateway: retrieve/associate virtual tape trên gateway mới theo quy trình.
- FSx File Gateway: triển khai gateway mới, kết nối lại FSx file system và xác minh AD/share.

Không khôi phục gateway bằng cách clone VM cũ. Cần dùng quy trình recovery chính thức của AWS để tránh trạng thái không nhất quán.

## 21. Storage Gateway, DataSync và các lựa chọn khác

| Nhu cầu | Dịch vụ thường phù hợp | Lý do |
|---|---|---|
| Ứng dụng tại chỗ cần NFS/SMB interface tới S3 | S3 File Gateway | Cung cấp file protocol với cache |
| Ứng dụng Windows cần SMB và AD tới file server cloud | FSx File Gateway + FSx for Windows | Duy trì semantics Windows file share |
| Ứng dụng cần iSCSI block device | Volume Gateway | Cung cấp block volume qua iSCSI |
| Phần mềm backup cần VTL/tape workflow | Tape Gateway | Giữ quy trình backup tape và archive cloud |
| Chuyển dữ liệu file/object hàng loạt hoặc theo lịch | AWS DataSync | Dịch vụ truyền dữ liệu có kiểm soát, không cần giữ gateway làm file interface thường trực |
| Ứng dụng cloud-native cần object API | Amazon S3 trực tiếp | Không cần lớp file gateway |
| Ứng dụng cần file system cloud-native | Amazon EFS hoặc Amazon FSx | File system được quản lý, truy cập trực tiếp qua network |

Storage Gateway thường được chọn khi ứng dụng cần tiếp tục sử dụng giao thức lưu trữ tại chỗ. DataSync phù hợp cho migration hoặc đồng bộ dữ liệu theo lịch; hai dịch vụ có thể phối hợp, ví dụ DataSync đưa dữ liệu ban đầu lên S3 rồi File Gateway cung cấp file interface cho ứng dụng.

## 22. Ví dụ triển khai: tích hợp file share tại chỗ với S3

Một công ty có Linux application tạo báo cáo hằng ngày và lưu file vào NFS share. Dung lượng tăng nhanh, đội vận hành muốn chuyển dữ liệu sang S3 nhưng chưa thể sửa ứng dụng để gọi S3 API.

### Thiết kế

1. Triển khai S3 File Gateway dưới dạng VM tại data center.
2. Chuẩn bị local cache SSD theo working set và tốc độ truy cập.
3. Tạo S3 bucket riêng cho báo cáo, bật encryption và bucket policy giới hạn gateway role.
4. Tạo NFS file share với allowed client CIDR chỉ gồm application subnet.
5. Mount share vào application server và kiểm thử quyền file.
6. Cấu hình CloudWatch alarm cho cache, upload và gateway health.
7. Nếu có hệ thống khác ghi trực tiếp vào bucket, thiết kế RefreshCache và notification; ưu tiên một luồng ghi chuẩn qua gateway.
8. Áp dụng S3 lifecycle cho dữ liệu đã upload theo retention và storage class phù hợp.
9. Kiểm thử restore file từ S3, thay gateway và xử lý khi WAN gián đoạn.

### Luồng vận hành

~~~mermaid
flowchart TD
    A[Linux report application] -->|NFS| B[S3 File Gateway]
    B --> C[Local cache]
    B -->|Upload async| D[S3 bucket]
    D --> E[S3 Lifecycle / Replication]
    F[CloudWatch metrics and alarms] --> G[Operations team]
    B --> F
    D --> H[Analytics / Data processing]
~~~

Nếu ứng dụng cần xác nhận báo cáo đã được lưu bền vững trên S3 trước khi gửi thông báo hoàn tất, workflow phải chờ upload notification hoặc cơ chế xác nhận tương ứng. Không coi việc ghi vào cache là bằng chứng upload đã hoàn tất.

## 23. Ví dụ triển khai: backup máy chủ tại chỗ bằng Volume Gateway

Một ứng dụng cũ cần block storage qua iSCSI và muốn có bản backup ngoài site.

### Lựa chọn

- Nếu toàn bộ data set cần latency thấp tại chỗ, cân nhắc Stored Volume Gateway.
- Nếu dữ liệu lớn nhưng working set nhỏ và có thể chịu cache miss qua WAN, cân nhắc Cached Volume Gateway.

### Các bước

1. Triển khai gateway trên host đủ CPU/RAM và local disk.
2. Cấu hình upload buffer và cache/storage theo mode.
3. Kết nối application server bằng iSCSI initiator.
4. Tạo volume, format và mount theo yêu cầu ứng dụng.
5. Tạo snapshot schedule hoặc AWS Backup plan.
6. Theo dõi upload buffer, snapshot status và latency.
7. Thử restore snapshot thành volume mới và gắn vào máy chủ test.
8. Ghi nhận RTO/RPO thực tế và cập nhật runbook.

Nếu data center mất kết nối, Stored Volume Gateway vẫn giữ dữ liệu chính trên local disk nhưng không thể upload snapshot mới. Cached Volume Gateway phụ thuộc nhiều hơn vào khả năng đọc cache và truy cập S3 cho dữ liệu cache miss. Phải mô phỏng tình huống này trước khi cam kết mức sẵn sàng.

## 24. Chi phí và tối ưu

Chi phí Storage Gateway không chỉ là phí gateway. Cần tính backend storage, request, transfer, retrieval, snapshot, local infrastructure và vận hành.

| Loại gateway | Thành phần chi phí cần xem xét |
|---|---|
| S3 File Gateway | S3 storage class, request, versioning, replication, data transfer và local cache hardware |
| FSx File Gateway | FSx capacity/throughput/backup, network, gateway VM và local cache |
| Volume Gateway | EBS snapshot storage, data transfer, gateway host/local disks và AWS Backup |
| Tape Gateway | Virtual tape storage, archive tier, retrieval, backup software license và network |

### Cách tối ưu

- Sizing cache theo working set thay vì toàn bộ data set.
- Dùng cache hit và dirty cache metrics để xác định bottleneck.
- Chọn storage class theo tần suất đọc và thời gian phục hồi.
- Quản lý S3 object version lifecycle để tránh lưu quá nhiều version ngoài ý muốn.
- Dùng bandwidth throttling cho upload ở thời điểm cần bảo vệ đường truyền.
- Với Tape Gateway, chọn Glacier Flexible Retrieval hay Deep Archive theo RTO restore.
- Với Volume Gateway, tối ưu lịch snapshot và retention theo RPO.
- Theo dõi data transfer và request cost ở bucket.
- Xóa gateway, volume, snapshot hoặc tape không còn sử dụng sau khi owner xác nhận.

Không chọn archive tier chỉ dựa trên giá lưu trữ. Nếu RTO yêu cầu restore trong 30 phút nhưng tape cần 12 giờ để retrieve, giải pháp không đáp ứng nghiệp vụ.

## 25. Lỗi triển khai thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Gateway không activate được | DNS, NTP, firewall hoặc service endpoint không truy cập được | Kiểm tra network requirements và activation endpoint |
| File share không AVAILABLE | IAM role, bucket hoặc KMS policy sai | Xác minh role, bucket, key và quyền |
| File mới từ S3 không xuất hiện | Gateway đang dùng cached inventory | Chạy RefreshCache và đợi notification hoàn tất |
| S3 storage tăng bất thường | Versioning giữ nhiều version hoặc file update tạo object versions | Rà soát version lifecycle và write pattern |
| Cache hit thấp | Working set lớn hoặc truy cập ngẫu nhiên | Tăng cache, tối ưu locality và đo lại |
| Upload buffer gần đầy | WAN chậm, upload throughput thấp hoặc mất kết nối | Kiểm tra network, buffer sizing và bandwidth |
| iSCSI volume không xuất hiện | Port, initiator, target hoặc session sai | Kiểm tra TCP 3260, initiator và volume status |
| Snapshot không hoàn tất | Upload buffer, disk hoặc connectivity có vấn đề | Kiểm tra gateway health và snapshot status |
| Tape không restore kịp | Tape nằm trong archive tier cần retrieval hours | Lập kế hoạch archive theo RTO và test retrieval |
| Gateway VM lỗi sau clone | Clone/snapshot VM gateway không được hỗ trợ | Deploy gateway mới và dùng recovery procedure |
| FSx share không truy cập được | AD, DNS, VPN/Direct Connect hoặc SMB policy | Kiểm tra domain join, routing và port requirements |

## 26. Checklist production

- [ ] Đã chọn đúng loại gateway theo giao thức và backend dữ liệu.
- [ ] Đã kiểm tra hypervisor/EC2 support và vòng đời Hardware Appliance.
- [ ] Host có CPU/RAM, local disk và NIC đủ theo sizing guidance.
- [ ] Cache và upload buffer được sizing theo working set, write rate và outage window.
- [ ] DNS, NTP, firewall, service endpoint và routing hybrid hoạt động.
- [ ] NFS/SMB/iSCSI chỉ mở cho client và subnet được phép.
- [ ] IAM role, bucket policy, Active Directory và KMS policy theo least privilege.
- [ ] Đã xác định source of truth và quy tắc tránh ghi ngoài gateway.
- [ ] RefreshCache có lịch hoặc workflow phù hợp nếu S3 bucket thay đổi ngoài gateway.
- [ ] Snapshot/AWS Backup/retention và restore test được cấu hình.
- [ ] Tape archive tier đáp ứng thời gian retrieval của nghiệp vụ.
- [ ] CloudWatch alarm theo dõi gateway, cache, upload buffer và snapshot.
- [ ] Có quy trình cập nhật gateway và khôi phục gateway mới.
- [ ] Có runbook khi WAN mất, gateway VM lỗi hoặc data center không khả dụng.
- [ ] Đã đo latency, throughput, cache hit và RTO/RPO trong load test.
- [ ] Chi phí storage, request, transfer, snapshot và retrieval được theo dõi.

## 27. Ghi nhớ

AWS Storage Gateway kết nối ứng dụng tại chỗ với dịch vụ lưu trữ AWS bằng các giao thức quen thuộc. S3 File Gateway cung cấp NFS/SMB trên S3 object; FSx File Gateway cung cấp SMB tới FSx for Windows File Server; Volume Gateway cung cấp iSCSI block volume với cached hoặc stored mode; Tape Gateway mô phỏng VTL để backup software ghi virtual tape và archive lên S3 Glacier.

Mỗi loại gateway có luồng dữ liệu và semantics riêng. Cần sizing cache/upload buffer, kiểm tra WAN, DNS, NTP, IAM, KMS, Active Directory và firewall; hiểu rõ upload bất đồng bộ, cache refresh, snapshot và archive retrieval. Backup và HA của gateway phải được kiểm thử bằng restore thực tế, không chỉ dựa trên trạng thái thiết bị.

Chọn Storage Gateway khi ứng dụng cần giao thức lưu trữ tại chỗ và cần tích hợp backend AWS. Kết hợp CloudWatch, AWS Backup, S3 lifecycle, replication và runbook recovery để tạo giải pháp hybrid có thể vận hành, kiểm soát chi phí và đáp ứng yêu cầu nghiệp vụ.

## Tài liệu tham khảo

- [What is AWS Storage Gateway?](https://docs.aws.amazon.com/storagegateway/latest/userguide/WhatIsStorageGateway.html)
- [Creating and Activating a Gateway](https://docs.aws.amazon.com/storagegateway/latest/userguide/creating-your-gateway.html)
- [Storage Gateway Requirements and Supported Hosts](https://docs.aws.amazon.com/storagegateway/latest/userguide/Requirements.html)
- [Storage Gateway Port Requirements](https://docs.aws.amazon.com/storagegateway/latest/userguide/Resource_Ports.html)
- [What is Amazon S3 File Gateway?](https://docs.aws.amazon.com/filegateway/latest/files3/what-is-file-s3.html)
- [How Amazon S3 File Gateway Works](https://docs.aws.amazon.com/filegateway/latest/files3/file-gateway-concepts.html)
- [Refreshing the S3 File Gateway Cache](https://docs.aws.amazon.com/filegateway/latest/files3/refresh-cache.html)
- [Monitoring S3 File Gateway](https://docs.aws.amazon.com/filegateway/latest/files3/monitoring-file-gateway.html)
- [What is Amazon FSx File Gateway?](https://docs.aws.amazon.com/filegateway/latest/filefsxw/what-is-file-fsxw.html)
- [FSx File Gateway Requirements](https://docs.aws.amazon.com/filegateway/latest/filefsxw/Requirements.html)
- [What is Volume Gateway?](https://docs.aws.amazon.com/storagegateway/latest/vgw/WhatIsStorageGateway.html)
- [How Volume Gateway Works](https://docs.aws.amazon.com/storagegateway/latest/vgw/StorageGatewayConcepts.html)
- [Backing Up Storage Gateway Volumes](https://docs.aws.amazon.com/storagegateway/latest/vgw/backing-up-volumes.html)
- [Best Practices for Volume Gateway](https://docs.aws.amazon.com/storagegateway/latest/vgw/best-practices.html)
- [How Tape Gateway Works](https://docs.aws.amazon.com/storagegateway/latest/tgw/StorageGatewayConcepts.html)
- [Archiving Virtual Tapes](https://docs.aws.amazon.com/storagegateway/latest/tgw/archiving-tapes-vtl.html)
- [Retrieving Archived Tapes](https://docs.aws.amazon.com/storagegateway/latest/tgw/retrieving-archived-tapes-vtl.html)
- [Monitoring Storage Gateway](https://docs.aws.amazon.com/storagegateway/latest/vgw/Main_monitoring-gateways-common.html)
- [VMware vSphere High Availability with Storage Gateway](https://docs.aws.amazon.com/storagegateway/latest/vgw/vmware-ha.html)
- [AWS Storage Gateway Hardware Appliance Availability Notice](https://docs.aws.amazon.com/storagegateway/latest/tgw/appliance-quick-start.html)
