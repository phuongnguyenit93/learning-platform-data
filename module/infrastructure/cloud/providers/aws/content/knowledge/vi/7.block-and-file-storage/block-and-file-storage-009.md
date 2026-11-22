# Amazon FSx và lựa chọn hệ thống file được quản lý

Khi triển khai ứng dụng trên AWS, không phải mọi bài toán lưu trữ đều phù hợp với ổ EBS hoặc bucket S3. Một ứng dụng Windows có thể cần chia sẻ thư mục **SMB** và quyền **NTFS ACL**; các máy Linux có thể cần **NFS**; còn hệ thống huấn luyện AI cần hệ thống file truy cập song song với thông lượng rất cao. **Amazon FSx** cung cấp nhiều hệ thống file được AWS quản lý để đáp ứng các nhu cầu đó.

Bài học thuộc chương **Lưu trữ block và file** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung kết nối việc chọn hệ thống file với Region/AZ, IAM, VPC, dịch vụ tính toán, cơ sở dữ liệu, tích hợp và serverless. Người học sẽ rèn kỹ năng chọn dịch vụ, thiết kế triển khai an toàn, giám sát, phục hồi và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **block**, **file** và **object storage** để biết khi nào cần Amazon FSx.
2. So sánh **FSx for Windows File Server**, **FSx for Lustre**, **FSx for NetApp ONTAP** và **FSx for OpenZFS**.
3. Chọn đúng hệ thống file theo giao thức, hệ điều hành, workload, dữ liệu chia sẻ, IOPS, throughput và latency.
4. Phân tích tính sẵn sàng, **Single-AZ/Multi-AZ**, backup, snapshot, replication và RTO/RPO.
5. Thiết kế VPC, kết nối hybrid, mã hóa và quyền truy cập file theo mô hình shared responsibility.
6. Lập quy trình đánh giá, kiểm kê AWS CLI, di chuyển dữ liệu và tính tổng chi phí sở hữu.

## 2. Block, file và object storage: phân biệt trước khi chọn

| Loại | Mô hình truy cập | Dịch vụ AWS thường dùng | Điểm mạnh / giới hạn |
|---|---|---|---|
| **Block storage** | Volume gắn với hệ điều hành để tạo file system | **Amazon EBS** | Ổ đĩa cho EC2, database; không tự cung cấp file share nhiều máy |
| **File storage** | Đường dẫn thư mục/tệp, quyền file, giao thức SMB/NFS/Lustre | **Amazon EFS, Amazon FSx** | Dữ liệu chia sẻ qua mạng với các hành vi file system |
| **Object storage** | Object và key, truy cập bằng API HTTP | **Amazon S3** | Data lake, ảnh, log, artifact và backup object |

**S3 không phải POSIX/SMB file system thông thường.** Object key có thể trông giống thư mục nhưng các thao tác như file locking, rename, mở file ngẫu nhiên, Windows ACL hoặc POSIX permissions không tự tương thích. Nếu ứng dụng yêu cầu những hành vi đó, phải kiểm tra giải pháp file storage trước khi thay đổi mã.

**Amazon EBS** cung cấp block storage cho EC2 và có ràng buộc theo AZ. Trong một số điều kiện, loại volume cụ thể hỗ trợ **Multi-Attach**, nhưng ứng dụng phải tự xử lý concurrent access/clustered filesystem tương ứng. EBS không tự tạo dịch vụ SMB/NFS chia sẻ. **Amazon EFS** là file storage NFS đàn hồi, thường phù hợp khi nhiều ứng dụng Linux cần chia sẻ thư mục và ưu tiên mô hình vận hành đơn giản.

**Amazon FSx** phục vụ các ứng dụng cần một **engine file system chuyên biệt**, tính năng quản trị file system cụ thể hoặc mô hình hiệu năng không đáp ứng tốt bằng giải pháp chung.

## 3. Bốn dòng Amazon FSx

Amazon FSx là nhóm dịch vụ được quản lý: AWS vận hành hạ tầng file server và nhiều tác vụ bảo trì, thay thế phần cứng, backup hoặc failover được hỗ trợ. Khách hàng vẫn phải chọn loại hệ thống, cấp quyền, cấu hình mạng, dung lượng/hiệu năng, kiểm soát dữ liệu và thử khôi phục.

| Dòng FSx | Giao thức chính | Khi nên dùng | Khả năng riêng |
|---|---|---|---|
| **FSx for Windows File Server** | **SMB**, Windows/NTFS, Active Directory | Ứng dụng Windows, home directory, departmental shares | NTFS ACL, Windows file shares, shadow copies, SSD/HDD, Single-AZ/Multi-AZ |
| **FSx for Lustre** | **Lustre** trên Linux | HPC, ML/AI, tính toán song song, xử lý video | Throughput lớn, scratch/persistent, tích hợp S3 data repository theo cấu hình |
| **FSx for NetApp ONTAP** | **NFS, SMB**, iSCSI và NVMe/TCP theo điều kiện hỗ trợ | Đa giao thức Windows/Linux, hệ thống NetApp sẵn có | SVM, volumes, snapshot, clone, SnapMirror, SSD tier và capacity pool tier |
| **FSx for OpenZFS** | **NFS** | Linux/NFS, ứng dụng cần ZFS snapshots/clones | Compression, snapshot, clone, quota, SSD/Intelligent-Tiering, các mức HA |

Các engine này **không thể chuyển đổi qua một thao tác thay đổi thuộc tính**. Để chuyển từ SMB/Windows sang Lustre, hoặc từ NFS/EFS sang ONTAP, cần phương án chuyển dữ liệu, đổi mount, kiểm thử quyền và cách ứng dụng thao tác file.

### 3.1. Sơ đồ chọn nhanh

~~~mermaid
flowchart TD
    R["Ứng dụng cần lưu trữ"] --> A{"Cần kiểu truy cập nào?"}
    A -->|"Ổ block cho EC2"| EBS["Amazon EBS"]
    A -->|"API object"| S3["Amazon S3"]
    A -->|"File share"| B{"Giao thức/tính năng chính"}
    B -->|"SMB, AD, NTFS"| WIN["FSx for Windows File Server"]
    B -->|"HPC/AI, Lustre"| LUS["FSx for Lustre"]
    B -->|"NFS + SMB, NetApp"| ONT["FSx for NetApp ONTAP"]
    B -->|"NFS + ZFS snapshot/clone"| ZFS["FSx for OpenZFS"]
    B -->|"NFS chia sẻ đơn giản"| EFS["So sánh Amazon EFS"]
~~~

Sơ đồ chỉ là điểm khởi đầu. **Mức độ sẵn sàng ở Region, tính năng, giao thức, giá và hiệu năng thực tế** phải được kiểm tra cho ứng dụng cụ thể.

## 4. FSx for Windows File Server

### 4.1. Ứng dụng phù hợp

FSx for Windows File Server cung cấp file server **Microsoft Windows** được quản lý, với hỗ trợ **SMB**, **NTFS ACL**, **Microsoft Active Directory** và các tính năng quản trị file server quen thuộc. Phù hợp để di chuyển hệ thống chia sẻ tập tin từ data center lên AWS khi ứng dụng cần giữ hành vi Windows và quyền người dùng đã có.

Ví dụ:

- Các phòng ban dùng chung tài liệu qua thư mục mạng.
- Ứng dụng doanh nghiệp yêu cầu chia sẻ SMB và khóa file theo hành vi Windows.
- Home directories cho người dùng xác thực bằng Active Directory.
- Workload trên EC2 Windows, Amazon WorkSpaces hoặc máy on-premises truy cập qua Direct Connect/VPN khi cấu hình đúng.

Tên đường dẫn mạng **UNC** của Windows có dạng:

~~~text
\\server-name\share
~~~

Khi triển khai thật, sử dụng **DNS name hoặc DNS alias** của file system FSx và quyền truy cập AD/SMB phù hợp.

### 4.2. Active Directory, IAM và NTFS ACL khác nhau thế nào?

FSx for Windows có thể kết hợp **AWS Managed Microsoft AD** hoặc **self-managed Microsoft AD** theo yêu cầu cấu hình. Quyền được đánh giá qua nhiều lớp:

| Lớp | Quyết định điều gì? | Ví dụ |
|---|---|---|
| **IAM** | Ai được tạo, thay đổi, backup, mô tả file system bằng AWS API? | fsx:DescribeFileSystems, fsx:CreateBackup |
| **Network/VPC** | Máy nào kết nối được đến SMB/AD/DNS endpoint? | Security group, route table, firewall |
| **AD, share permission, NTFS ACL** | Người dùng/nhóm nào đọc, sửa, xóa từng file? | AD group và folder ACL |

**IAM Allow không tự cấp quyền đọc một Windows file share.** Người dùng có quyền fsx:DescribeFileSystems vẫn phải xác thực và được file/share ACL cho phép thì mới truy cập được dữ liệu qua SMB.

### 4.3. SSD/HDD, Single-AZ/Multi-AZ

AWS cung cấp các lựa chọn **SSD** và **HDD**, với **throughput capacity** và IOPS tùy cấu hình. SSD phù hợp tải cần độ trễ thấp hoặc nhiều file nhỏ; HDD có thể giảm chi phí cho dữ liệu lớn ít truy cập và yêu cầu IOPS thấp. Throughput của file server, I/O trên disk và cache cùng tác động tới hiệu năng; chọn storage capacity lớn không tự bảo đảm đạt throughput cao.

**Single-AZ** có khả năng xử lý một số lỗi thành phần trong AZ. **Multi-AZ** triển khai file server dự phòng ở AZ khác trong cùng Region, giúp giảm ảnh hưởng của lỗi cấp AZ và hỗ trợ failover. Đây **không phải** giải pháp DR toàn Region. Dịch vụ hỗ trợ managed backups; Windows shadow copies có thể giúp khôi phục dữ liệu theo cơ chế và cấu hình phù hợp.

Điểm cần kiểm tra: cấu hình AD, DNS, SMB ports, client từ xa, ACL sau di chuyển, độ trễ khi dùng từ on-premises, lựa chọn SSD/HDD và cách khôi phục ứng dụng thực tế.

## 5. FSx for Lustre

### 5.1. Vì sao Lustre hợp với HPC và ML?

**Lustre** là file system phân tán cho các workload cần **I/O song song và throughput rất cao**, chẳng hạn mô phỏng khoa học, huấn luyện ML, xử lý video, phân tích định lượng hoặc thiết kế kỹ thuật. Linux compute nodes dùng **Lustre client** tương thích để mount file system; ứng dụng thường tương tác qua đường dẫn file.

Ví dụ, một cụm EC2 có nhiều worker đọc dataset để huấn luyện. Nếu bottleneck là số lượng file, metadata operations hoặc băng thông đồng thời, cần benchmark FSx for Lustre theo số worker thật, kích thước I/O và mạng của từng instance.

### 5.2. Scratch so với Persistent

| Kiểu deployment | Mục tiêu | Khả năng bảo vệ dữ liệu |
|---|---|---|
| **Scratch** | Dữ liệu tạm, job có thể tạo lại kết quả, môi trường xử lý ngắn hạn | Không nhân bản dữ liệu theo mô hình Persistent; lỗi file server có thể làm mất dữ liệu liên quan |
| **Persistent** | Workload dài hơn, dữ liệu cần duy trì khi có lỗi thành phần | Có cơ chế nhân bản/thay thế file server theo loại Persistent được hỗ trợ |

**Không lưu bản duy nhất của dữ liệu quan trọng ở Scratch.** Persistent cũng không thay thế kế hoạch backup/khôi phục dữ liệu.

### 5.3. Tích hợp với S3 data repository

Trong các cấu hình được hỗ trợ, FSx for Lustre có thể liên kết với **Amazon S3** để trình bày object như file cho compute nodes, nhập thay đổi và xuất kết quả xử lý. Cần hiểu rõ:

1. **Import** metadata/file listing từ S3.
2. **Tải dữ liệu** để thực thi ứng dụng trên Lustre khi được yêu cầu.
3. **Export** file hoặc kết quả ra S3 bằng cơ chế data repository/task phù hợp.
4. Xác nhận việc export đã hoàn tất trước khi xóa một hệ thống file dùng cho tác vụ ngắn.

~~~mermaid
flowchart LR
    S["S3: dữ liệu gốc"] -->|"Import khi được hỗ trợ"| F["FSx for Lustre"]
    F <--> C["EC2 / EKS / HPC workers<br/>Lustre client"]
    F -->|"Export kết quả"| O["S3: dữ liệu lâu dài"]
~~~

**Giới hạn cần nhớ:** không phải mọi storage class/deployment đều hỗ trợ cùng tính năng S3 repository. Tài liệu AWS hiện hành nêu **Lustre Intelligent-Tiering** không hỗ trợ liên kết S3 data repository; **file system backups không được hỗ trợ đối với Lustre file system đã liên kết S3 repository** theo cơ chế này. Cần kiểm tra lựa chọn đang dùng, cách dữ liệu được bảo vệ và khả năng phục hồi.

### 5.4. Đo hiệu năng Lustre

Kiểm tra throughput toàn cụm, IOPS, kích thước và số lượng file, mức độ song song, thời gian metadata operations, tốc độ client EC2, cache và nghẽn mạng. Con số throughput tối đa giới thiệu bởi dịch vụ không bảo đảm một ứng dụng đơn luồng đạt hiệu năng tương đương.

## 6. FSx for NetApp ONTAP

### 6.1. Đa giao thức và di chuyển hệ thống NetApp

**FSx for NetApp ONTAP** cung cấp quản trị file storage dựa trên ONTAP, hỗ trợ **NFS** cho Linux và **SMB** cho Windows. Ngoài ra còn có cách truy cập block qua **iSCSI** và **NVMe/TCP** trong các thế hệ/cấu hình được hỗ trợ. Đây là lựa chọn khi doanh nghiệp đã vận hành NetApp on-premises, cần dùng chung dữ liệu qua nhiều giao thức hoặc cần tính năng data management nâng cao.

Các khả năng tiêu biểu: **volumes, snapshots, cloning, data compression, deduplication, tiering** và replication như **SnapMirror** theo thiết kế phù hợp.

### 6.2. File system, SVM và volume

~~~mermaid
flowchart TB
    FS["FSx for NetApp ONTAP"] --> SVM["Storage Virtual Machine (SVM)"]
    SVM --> VOL1["Volume ứng dụng A"]
    SVM --> VOL2["Volume dữ liệu B"]
    W["Windows / SMB"] --> SVM
    L["Linux / NFS"] --> SVM
    VOL1 --> SSD["SSD tier: working set"]
    VOL2 --> POOL["Capacity pool tier: dữ liệu lạnh"]
~~~

**SVM** cung cấp môi trường/endpoint phục vụ file theo giao thức và cấu hình. **Volume** là tài nguyên logic để tổ chức dữ liệu và chính sách; dung lượng logic volume không nhất thiết là toàn bộ dung lượng vật lý SSD đã dành trước.

FSx for ONTAP sử dụng **SSD tier** cho dữ liệu hiệu năng cao và **capacity pool** đàn hồi dành cho dữ liệu ít truy cập theo **tiering policy**. Dữ liệu có thể chuyển giữa hai tier theo điều kiện, lịch truy cập và chính sách, giúp tối ưu chi phí khi phần dữ liệu nóng chỉ chiếm một phần.

### 6.3. Quyền đa giao thức và sao lưu

Nếu các client Windows và Linux truy cập cùng một bộ dữ liệu, phải thiết kế **identity mapping**, Windows ACL, POSIX permissions, NFS export policy và file locking theo yêu cầu ứng dụng. Dùng được NFS và SMB chưa đủ bảo đảm các tài khoản hai hệ điều hành có quyền tương đương.

ONTAP hỗ trợ **Single-AZ/Multi-AZ** tùy cấu hình, backup và các cơ chế snapshot/replication. Snapshot có thể giúp phục hồi nhanh một thời điểm dữ liệu nhưng **không tự bảo vệ trước việc mất toàn bộ Region**. Khi dùng SnapMirror hoặc thiết kế DR khác, kiểm tra tuyến mạng, thứ tự khôi phục ứng dụng và độ trễ đồng bộ dữ liệu.

## 7. FSx for OpenZFS

### 7.1. Hệ thống NFS với khả năng ZFS

**FSx for OpenZFS** cung cấp file storage dựa trên OpenZFS, chủ yếu truy cập qua **NFS**. Phù hợp với ứng dụng Linux cần low-latency file operations, **snapshots/clones**, compression, quota và quản lý volumes kiểu ZFS.

Windows và macOS có thể sử dụng NFS client tương thích trong phạm vi hỗ trợ, nhưng **OpenZFS không phải máy chủ SMB/NTFS tương đương FSx for Windows File Server**. Nếu cần Windows share và Active Directory tích hợp sẵn, xem xét Windows File Server hoặc ONTAP.

### 7.2. Storage class và HA

Theo tài liệu AWS hiện hành, FSx for OpenZFS có các lựa chọn:

- **SSD storage class:** cấp dung lượng SSD phù hợp, ưu tiên truy cập toàn bộ dataset với hiệu năng và latency thấp.
- **Intelligent-Tiering:** lưu trữ theo dữ liệu sử dụng, với tùy chọn **SSD read cache** cho dữ liệu thường được truy cập; phù hợp khi muốn tối ưu chi phí theo working set.

Loại file system có thể là **Multi-AZ (HA)**, **Single-AZ (HA)** hoặc **Single-AZ (non-HA)**. Multi-AZ nhân bản dữ liệu giữa các AZ trong cùng Region; Single-AZ HA có cấu hình primary/standby trong một AZ; Single-AZ non-HA có cơ chế phục hồi thành phần khác. Đánh giá theo RTO/RPO, mức chịu lỗi và giá của lựa chọn cụ thể.

**Snapshot** là cơ chế điểm khôi phục ở mức file system; **managed backup** là khả năng bảo vệ dữ liệu riêng. Dù có snapshot, vẫn cần backup và diễn tập restore cho các lỗi xóa nhầm, corruption hoặc mất toàn Region.

## 8. So sánh FSx với EFS, EBS và S3 theo tình huống

| Bài toán | Lựa chọn nên đánh giá trước | Lý do |
|---|---|---|
| Windows share, AD, NTFS ACL | **FSx for Windows File Server** | Tương thích ứng dụng và quyền Windows |
| Linux cần NFS dùng chung, không phụ thuộc ZFS/ONTAP | **Amazon EFS** | NFS đàn hồi, quản lý đơn giản |
| Linux cần NFS, snapshot/clone ZFS, chọn storage class theo working set | **FSx for OpenZFS** | Tính năng file system OpenZFS |
| Windows/Linux cùng dùng dữ liệu, có NetApp on-premises | **FSx for NetApp ONTAP** | NFS/SMB và quản trị volume/tiering |
| Tính toán song song ML/HPC | **FSx for Lustre** | Thiết kế cho I/O song song hiệu năng cao |
| Volume hệ điều hành/ứng dụng trên EC2 | **Amazon EBS** | Block volume cho compute |
| Lưu ảnh, log, data lake, dữ liệu object | **Amazon S3** | Object API và mô hình lưu trữ object |

### 8.1. Vì sao không phải cứ NFS là dùng một dịch vụ?

**EFS**, **FSx for OpenZFS** và **FSx for ONTAP** đều có thể phục vụ ứng dụng NFS, nhưng khác nhau ở mô hình provision, giới hạn hiệu năng, cache, khả năng mở rộng, snapshot, quyền, HA, replication, chi phí và mức độ quản trị. Chọn đúng phụ thuộc **file semantics và workload đo được**, không chỉ giao thức.

### 8.2. Có thể truy cập FSx từ nơi nào?

Tùy engine, client và phiên bản driver, các hệ thống file có thể được dùng từ **EC2**, một số môi trường **ECS/EKS** hoặc mạng **on-premises**. Cần kiểm tra Lustre client, NFS/SMB client, CSI driver khi dùng Kubernetes, yêu cầu DNS và kết nối mạng.

Khi truy cập từ on-premises, thiết kế **Direct Connect hoặc Site-to-Site VPN**, route hai chiều, firewall, DNS và đo độ trễ. Không giả định file server FSx được mở trực tiếp lên public Internet.

## 9. Các tiêu chí cần đo trước khi quyết định

| Tiêu chí | Câu hỏi kỹ thuật | Bằng chứng |
|---|---|---|
| **Protocol** | SMB, NFS, Lustre hay block iSCSI là bắt buộc? | Cách ứng dụng mount, phiên bản client |
| **File semantics** | Cần lock, ACL, rename, snapshot, symbolic link? | Bộ test tích hợp ứng dụng |
| **Throughput** | Nhiều client đọc/ghi đồng thời với tổng MB/s bao nhiêu? | Benchmark peak throughput |
| **IOPS** | Bao nhiêu thao tác/s, kích thước I/O và tỷ lệ read/write? | Traces và metric thực |
| **Latency** | p95/p99 cho các thao tác quan trọng là bao nhiêu? | Load test với dữ liệu đại diện |
| **Metadata operations** | Có hàng triệu file nhỏ hay nhiều thao tác list/stat? | Profiling |
| **Capacity** | Dữ liệu tăng thế nào, phần nóng/lạnh ra sao? | Lịch sử dung lượng và working set |
| **Availability** | Cần Single-AZ, Multi-AZ hay DR liên Region? | RTO/RPO, thử failover |
| **Security** | Ai truy cập file và ai quản trị FSx? | IAM, AD/POSIX, SG/KMS, audit |
| **Cost** | Tính cả throughput, tier, backup và network chưa? | Ước lượng theo đúng Region và engine |

**Throughput** là lượng byte/giây; **IOPS** là số I/O/giây; **latency** là thời gian hoàn thành thao tác. Workload xử lý video có thể cần throughput cao nhưng ít file; ứng dụng lưu hàng triệu chứng từ nhỏ có thể bị giới hạn bởi IOPS/metadata dù lượng dữ liệu không lớn.

## 10. Single-AZ, Multi-AZ, snapshot, backup và DR

Các lớp bảo vệ giải quyết những sự cố khác nhau:

| Cơ chế | Giá trị | Giới hạn |
|---|---|---|
| **HA/Multi-AZ** | Duy trì dịch vụ khi gặp lỗi thành phần hoặc AZ theo cấu hình hỗ trợ | Không tự khôi phục file bị người dùng xóa/sửa nhầm |
| **Snapshot** | Điểm khôi phục nhanh của file system/volume | Không mặc nhiên là bản sao độc lập ngoài hệ thống/Region |
| **Managed backup** | Có bản sao dữ liệu theo thời điểm và retention | Không bảo đảm RTO rất thấp nếu restore mất thời gian |
| **Replication** | Bản sao dữ liệu phục vụ luồng/địa điểm khác | Có thể nhân bản cả lỗi xóa hoặc thay đổi sai |
| **Restore drill** | Kiểm chứng ứng dụng chạy được sau khi khôi phục | Phải lặp lại khi kiến trúc thay đổi |

**RTO (Recovery Time Objective)** là thời gian khôi phục dịch vụ mục tiêu; **RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa có thể chấp nhận theo thời gian. Một file system Multi-AZ vẫn cần backup. Nếu hệ thống phải chịu lỗi toàn Region, cần kiến trúc DR liên Region hoặc địa điểm được phê duyệt, gồm dữ liệu, compute, DNS, IAM, KMS và route.

Các engine có hỗ trợ snapshot/backup/replication **không giống nhau**. Đặc biệt với Lustre Scratch hoặc Lustre liên kết S3 data repository, phải kiểm tra điều kiện bảo vệ dữ liệu cụ thể thay vì mặc định có backup tự động như Windows File Server.

## 11. Bảo mật và kết nối mạng

### 11.1. VPC, subnet, security group và DNS

FSx được kết nối với mạng VPC qua tài nguyên mạng do dịch vụ quản lý. Thiết kế cần đúng subnet/AZ, SG, route table, firewall, DNS, endpoint file system và protocol ports.

~~~mermaid
flowchart LR
    subgraph VPC["VPC"]
        EC2["EC2 / container client"]
        NET["Routing + SG + DNS"]
        FSX["FSx file system<br/>SMB / NFS / Lustre"]
        EC2 --> NET --> FSX
    end
    OP["On-premises"] -->|"DX / VPN"| NET
    API["AWS management API"] -->|"IAM control plane"| FSX
~~~

**Có đường mạng không đồng nghĩa có quyền đọc tệp.** Client phải qua bảo vệ của giao thức và hệ thống file: SMB/AD ACL, NFS UID/GID/export policy, ONTAP permissions hoặc cấu hình tương ứng.

### 11.2. Ba tầng phân quyền

| Tầng | Ví dụ | Phạm vi |
|---|---|---|
| **IAM control plane** | fsx:DescribeFileSystems, fsx:CreateBackup | Quản trị tài nguyên thông qua AWS API |
| **Mạng** | VPC route, SG, firewall, DX/VPN | Quyết định client có kết nối đến endpoint không |
| **File data plane** | NTFS ACL, AD, POSIX mode, NFS export, ONTAP ACL | Quyết định tài khoản/tiến trình nào được đọc, sửa, xóa file |

Đặt quyền tối thiểu trên cả ba tầng, dùng mã hóa **at rest** theo cơ chế KMS của engine và mã hóa **in transit** theo giao thức/thiết lập được dịch vụ hỗ trợ. Không khẳng định mọi client NFS hoặc mọi luồng SMB đều tự động mã hóa nếu chưa kiểm tra.

### 11.3. CloudTrail có ghi mọi lần đọc file?

**CloudTrail** ghi các hoạt động AWS API quản trị phù hợp; điều đó **không có nghĩa mọi SMB/NFS/Lustre file read/write đều xuất hiện trong CloudTrail**. Khi cần file access audit, cấu hình công cụ audit/log của engine và kiểm tra retention, nơi lưu và quyền đọc log. Ví dụ Windows có các cơ chế file access auditing liên quan; ONTAP cũng có chức năng ghi log theo thiết kế.

Yêu cầu **data residency** phải xét cả file system gốc, snapshot, backup, repository, DR copy và bản xuất dữ liệu. Chọn một Region không tự ngăn mọi luồng sao chép hoặc xuất ra ngoài.

## 12. Quy trình lựa chọn và triển khai

### Bước 1 — Mô tả workload

Thu thập hệ điều hành, protocol, phiên bản client, file locking/rename, ACL, số client, loại file, working set, throughput/IOPS/latency, yêu cầu HA, vị trí và chi phí.

**Đầu ra:** tiêu chí bắt buộc, chẳng hạn “SMB + AD” hoặc “Lustre client với throughput song song cao”, và danh sách tối ưu.

### Bước 2 — Loại engine không phù hợp

Nếu bắt buộc SMB/NTFS, không chọn EFS/OpenZFS NFS làm giải pháp thay trực tiếp. Nếu cần Lustre client, đánh giá FSx for Lustre. Với NFS, so sánh EFS, OpenZFS, ONTAP theo tính năng, hiệu năng và chi phí. Xác nhận **dịch vụ, storage class và deployment type có mặt ở Region** được chọn.

### Bước 3 — Thiết kế network và quyền

Định nghĩa VPC, subnet, SG, route, DNS, AD/POSIX, KMS và nguyên tắc least privilege. Với ứng dụng hybrid, kiểm tra DX/VPN, latency và firewall hai chiều; lựa chọn mount/driver phù hợp cho container.

### Bước 4 — Cấu hình công suất và tính sẵn sàng

Chọn storage class, provisioned throughput, IOPS, SSD/HDD hoặc cold tier theo engine. Chọn Single-AZ/Multi-AZ và backup/replication theo RTO/RPO. Đừng mua công suất tối đa chỉ vì cần ít downtime: HA và performance là hai trục lựa chọn khác nhau.

### Bước 5 — Di chuyển dữ liệu và kiểm thử

Tùy engine, cân nhắc **AWS DataSync**, copy qua SMB/NFS, công cụ NetApp, hoặc S3 data repository của Lustre **khi được hỗ trợ**. Cần kiểm tra:

- Danh sách file, checksum, quyền file, owner, ACL và timestamps.
- Hành vi ứng dụng với lock, concurrency, rename, hidden file và file đặc biệt.
- Kết nối DNS và mount trong môi trường mới.
- Quy trình đồng bộ delta, cutover, freeze writes và rollback khi cần.

**Không giả định công cụ chuyển dữ liệu bảo toàn đầy đủ quyền/metadata khi thay đổi engine hoặc giao thức.** Xác minh bằng dữ liệu đại diện của ứng dụng.

### Bước 6 — Diễn tập khôi phục và vận hành

Thử backup restore, mất kết nối, failover phù hợp loại deployment, lỗi mount và khả năng reconnect. Cấu hình CloudWatch alerts, backup policy, runbook, tag owner, cấu hình quyền và lịch capacity review.

## 13. Kiểm kê Amazon FSx bằng AWS CLI

Các ví dụ chỉ đọc thông tin, yêu cầu AWS profile có quyền phù hợp. Thay **Region** và **file system ID** bằng tài nguyên thực tế được ủy quyền.

~~~bash
# Kiểm kê các file systems và engine trong một Region.
aws fsx describe-file-systems \
  --region ap-southeast-1 \
  --query 'FileSystems[].{Id:FileSystemId,Type:FileSystemType,State:Lifecycle,CapacityGiB:StorageCapacity}' \
  --output table

# Xem cấu hình chi tiết của một file system.
aws fsx describe-file-systems \
  --region ap-southeast-1 \
  --file-system-ids fs-0123456789abcdef0 \
  --output json

# Kiểm tra những backup mà tài khoản có quyền xem.
aws fsx describe-backups \
  --region ap-southeast-1 \
  --query 'Backups[].{Id:BackupId,Type:Type,State:Lifecycle,Created:CreationTime}' \
  --output table

# Xem các volume được API FSx hỗ trợ.
aws fsx describe-volumes \
  --region ap-southeast-1 \
  --query 'Volumes[].{Id:VolumeId,Name:Name,Type:VolumeType,State:Lifecycle}' \
  --output table
~~~

Giá trị **FileSystemType** thường là **WINDOWS**, **LUSTRE**, **ONTAP** hoặc **OPENZFS**. Những trường riêng của engine được đặt trong cấu hình chi tiết như **WindowsConfiguration**, **LustreConfiguration**, **OntapConfiguration**, **OpenZFSConfiguration** khi API trả về.

Kết quả của một Region hoặc một account **không đại diện toàn tổ chức**. Việc không tìm thấy managed backup không chứng minh không có bảo vệ dữ liệu ở một lớp khác (ví dụ bản xuất S3 hoặc replication). Phải đối chiếu chính sách và luồng dữ liệu thực.

### 13.1. Giám sát hiệu năng theo từng engine

| Engine | Nên chú ý |
|---|---|
| **Windows File Server** | Throughput capacity, disk IOPS, SSD/HDD, số SMB sessions, shadow copies, latency |
| **Lustre** | Aggregate read/write throughput, metadata bottleneck, client load, kết quả xuất S3 |
| **ONTAP** | SSD tier utilization, volume quota, capacity pool access, tiering, snapshots |
| **OpenZFS** | Free space, NFS latency, cache/working set, snapshots/clones, storage class |

Dùng **CloudWatch AWS/FSx** và metric đặc thù từng engine theo tài liệu của dịch vụ. Không dùng một tên metric hoặc ngưỡng cảnh báo chung cho mọi hệ thống file. Tăng storage capacity chưa chắc giải quyết bottleneck nếu giới hạn thật nằm ở network throughput, server CPU, metadata hoặc client.

## 14. Đánh giá tổng chi phí

Tổng chi phí cần gồm:

| Nhóm | Chi phí cần tính |
|---|---|
| **Storage** | SSD/HDD provisioned capacity, hoặc dung lượng tiêu thụ theo storage class |
| **Throughput/IOPS** | Công suất file server và IOPS tính phí trong engine hỗ trợ |
| **Data tiering** | Capacity pool/tier, các lượt đọc ghi, cache theo cách định giá hiện hành |
| **Data protection** | Backup/snapshot, storage retention, bản copy, DR environment và kiểm thử |
| **Network** | Truyền dữ liệu liên AZ/Region, DX/VPN, thiết bị và dịch vụ trung gian nếu phát sinh |
| **Identity và vận hành** | Active Directory, migration, audit, monitoring, nhân lực trực và downtime |

Không chỉ so **USD/GB/tháng**. Một hệ thống có giá lưu trữ thấp nhưng throughput yếu có thể kéo dài thời gian chạy batch và chi phí compute. Ngược lại, cấp quá nhiều SSD/IOPS cho tập dữ liệu ít truy cập có thể lãng phí. Dùng bảng giá đúng **Region/engine**, AWS Pricing Calculator và phép thử tải thật.

## 15. Tình huống thực hành

### Tình huống A — Di chuyển Windows file share

Doanh nghiệp có nhiều nhân viên dùng thư mục mạng Windows, đăng nhập bằng AD và muốn giữ nguyên NTFS ACL khi chuyển lên AWS.

**Câu hỏi:** nên cân nhắc engine nào, cần kiểm tra gì trước cutover?

**Gợi ý:** chọn **FSx for Windows File Server**. Xác định AD/DNS, network/SMB, SSD/HDD theo I/O, Single-AZ/Multi-AZ theo RTO, khả năng migration giữ ACL, thử đăng nhập và restore. OpenZFS NFS không thay trực tiếp share SMB/NTFS.

### Tình huống B — Huấn luyện AI trên dataset S3

Một nhóm ML có dataset lớn trong S3 và hàng trăm worker EC2 cần đọc song song với throughput cao. Kết quả phải được lưu lâu dài sau mỗi đợt train.

**Câu hỏi:** làm sao thiết kế vùng file và kho bền vững?

**Gợi ý:** đánh giá **FSx for Lustre** với storage/deployment phù hợp, liên kết S3 khi cấu hình hỗ trợ, mount bằng Lustre client và benchmark theo tải. Giữ dữ liệu gốc và output quan trọng trong S3; không dùng Scratch làm nơi lưu bản duy nhất. Kiểm tra hoàn tất export và các giới hạn backup.

### Tình huống C — File share đa giao thức

Nhóm Windows cần SMB, nhóm Linux cần NFS với cùng bộ dữ liệu, trong khi phần lớn dữ liệu ít được truy cập. Doanh nghiệp đang sử dụng NetApp tại chỗ.

**Câu hỏi:** ưu điểm và rủi ro của ONTAP?

**Gợi ý:** đánh giá **FSx for NetApp ONTAP** vì NFS/SMB, volumes, tiering giữa SSD/capacity pool, snapshot và replication. Cần thiết kế identity mapping, quyền/locking, quota, chi phí data tiering và diễn tập DR.

### Tình huống D — NFS nhưng cần snapshots và clones

Ứng dụng Linux muốn sao chép bộ dataset nhanh cho môi trường kiểm thử, sử dụng các tính năng ZFS và cần NFS.

**Câu hỏi:** EFS hay OpenZFS?

**Gợi ý:** so sánh **FSx for OpenZFS** với **EFS** dựa trên snapshot/clone, storage class, performance, cost, HA và yêu cầu vận hành. EFS vẫn là lựa chọn thích hợp nếu chỉ cần NFS đàn hồi và đơn giản.

### Tình huống E — Có backup nhưng không mount được sau phục hồi

Một đội đã có backup file system nhưng khi restore, ứng dụng không truy cập được do DNS, AD và security group tại môi trường khôi phục chưa được cấu hình.

**Câu hỏi:** có thể kết luận RTO/RPO đã đạt chỉ vì backup tồn tại?

**Gợi ý:** chưa. Phải kiểm tra restore end-to-end: file data, client, DNS, mạng, IAM/ACL, bí mật, ứng dụng, thời gian chuyển lưu lượng và tính nhất quán dữ liệu.

## 16. Checklist chọn hệ thống file

- [ ] Đã phân biệt yêu cầu **block/file/object** và xác định file semantics bắt buộc.
- [ ] Đã chọn giao thức: **SMB/NFS/Lustre** hoặc block iSCSI khi trường hợp hỗ trợ.
- [ ] Đã kiểm tra engine, deployment type, storage class trong **Region** định triển khai.
- [ ] Đã đo số client, dung lượng nóng/lạnh, throughput, IOPS, latency và metadata operations.
- [ ] Đã chọn Single-AZ/Multi-AZ và kiến trúc backup/DR theo RTO/RPO.
- [ ] Đã thiết kế VPC, subnet, SG, route, DNS và hybrid connectivity nếu cần.
- [ ] Đã phân biệt **IAM API**, network access và quyền file-level AD/ACL/POSIX.
- [ ] Đã cấu hình mã hóa, KMS, file auditing và lưu trú dữ liệu theo chính sách.
- [ ] Đã thử ứng dụng với quyền file, rename/locking, nhiều client và job thật.
- [ ] Đã kiểm thử migration, cutover/rollback, backup và restore.
- [ ] Đã đặt CloudWatch alerts, tag owner, runbook và lịch capacity review.
- [ ] Đã dự toán storage, throughput, IOPS, tiering, backup, mạng và vận hành.

## 17. Ghi nhớ

**Amazon FSx** là nhóm file storage được quản lý với các engine chuyên biệt: **Windows File Server** cho SMB/AD/NTFS; **Lustre** cho tính toán song song HPC/AI; **NetApp ONTAP** cho đa giao thức và tính năng quản trị dữ liệu chuyên sâu; **OpenZFS** cho NFS/ZFS, snapshot và clone. **Amazon EFS** đáng cân nhắc nếu chỉ cần NFS chia sẻ đàn hồi; **EBS** dành cho block storage; **S3** dành cho object storage.

Quy trình lựa chọn bắt đầu từ **giao thức và hành vi tệp**, sau đó mới tối ưu **hiệu năng, HA/DR, bảo mật, mạng, sao lưu và tổng chi phí**. Một dịch vụ managed giúp giảm việc vận hành phần cứng nhưng không loại bỏ trách nhiệm thiết kế ứng dụng và kiểm thử phục hồi của doanh nghiệp.

### Tài liệu AWS chính thức nên đối chiếu

- [Amazon FSx documentation](https://docs.aws.amazon.com/fsx/) — tài liệu các engine FSx.
- [FSx for Windows File Server — What is](https://docs.aws.amazon.com/fsx/latest/WindowsGuide/what-is.html) — SMB, AD, Windows ACL và backup.
- [FSx for Windows — Performance](https://docs.aws.amazon.com/fsx/latest/WindowsGuide/performance.html) — storage type, throughput, disk IOPS.
- [FSx for Lustre — What is](https://docs.aws.amazon.com/fsx/latest/LustreGuide/what-is.html) — HPC/ML, Scratch và Persistent.
- [FSx for Lustre — Using data repositories](https://docs.aws.amazon.com/fsx/latest/LustreGuide/fsx-data-repositories.html) — S3 integration và giới hạn.
- [FSx for NetApp ONTAP — What is](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) — đa giao thức, tiering và replication.
- [FSx for ONTAP — Volume storage capacity](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/volume-storage-capacity.html) — tiering policy và SSD/capacity pool.
- [FSx for OpenZFS — What is](https://docs.aws.amazon.com/fsx/latest/OpenZFSGuide/what-is-fsx.html) — NFS, SSD/Intelligent-Tiering, snapshots và HA.
- [Amazon EFS — What is](https://docs.aws.amazon.com/efs/latest/ug/whatisefs.html) — NFS đàn hồi.
- [Amazon FSx pricing](https://aws.amazon.com/fsx/pricing/) và [AWS Pricing Calculator](https://calculator.aws/) — ước tính chi phí theo engine và Region.
