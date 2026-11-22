# Phân biệt block storage, file storage và object storage

> **Chương:** Lưu trữ block và file  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS từ Region/Availability Zone (AZ), IAM và VPC đến tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; thực hành lựa chọn dịch vụ, xây dựng hệ thống an toàn, có giám sát, khả năng phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích cách **block storage**, **file storage** và **object storage** tổ chức, định danh và cung cấp quyền truy cập dữ liệu.
2. Chọn đúng dịch vụ AWS: **Amazon EBS** (block), **Amazon EFS / Amazon FSx** (file) hoặc **Amazon S3** (object) theo giao diện ứng dụng và yêu cầu nghiệp vụ.
3. So sánh IOPS, throughput, latency, khả năng chia sẻ, tính sẵn sàng theo AZ/Region, durability, backup và RPO/RTO.
4. Thiết kế phân quyền và bảo vệ dữ liệu bằng IAM, mã hóa/KMS, quyền filesystem, Security Group và bucket policy.
5. Nhận diện chi phí theo dung lượng, hiệu năng, request, retrieval, truyền dữ liệu và bản sao lưu.
6. Đọc cấu hình AWS bằng CLI ở chế độ chỉ đọc và xử lý những lỗi phổ biến khi dùng storage.

## 1. Ba mô hình lưu trữ khác nhau ở đâu?

Không nên chọn storage chỉ bằng câu hỏi “cần bao nhiêu GB?”. Cần xác định ứng dụng muốn **tương tác với dữ liệu** theo cách nào.

- **Block storage** cung cấp một thiết bị lưu trữ theo khối, gần giống ổ đĩa mà hệ điều hành có thể chia phân vùng, tạo filesystem và đọc/ghi các block. Ứng dụng thường thao tác với file trên filesystem nằm trên ổ này.
- **File storage** cung cấp filesystem với cây thư mục, file, metadata và quyền truy cập. Client có thể mount qua giao thức như NFS hoặc SMB, nhiều máy có thể chia sẻ cùng namespace khi dịch vụ hỗ trợ.
- **Object storage** lưu các object gồm nội dung, key và metadata. Ứng dụng truy cập object theo bucket/key qua API như GET, PUT, LIST, DELETE thay vì mount một filesystem POSIX chuẩn.

Cùng một file báo cáo có thể được lưu theo ba cách:

| Loại | Cách ứng dụng nhìn thấy | Dịch vụ AWS điển hình |
| --- | --- | --- |
| **Block** | File **/data/reports/q4.pdf** trong filesystem ext4/XFS đặt trên block volume. | Amazon EBS gắn vào EC2. |
| **File** | File **/mnt/shared/reports/q4.pdf** trong filesystem dùng chung được mount qua NFS/SMB. | Amazon EFS hoặc một biến thể Amazon FSx. |
| **Object** | Object có bucket và key, ví dụ **s3://example-reports/reports/q4.pdf**, đọc bằng SDK/API. | Amazon S3. |

**Điểm cốt lõi:** Dù đều lưu được nội dung PDF, ba loại mang **giao diện, semantics và trách nhiệm vận hành khác nhau**. Thay đường dẫn filesystem bằng S3 URI không tự làm một ứng dụng POSIX tương thích với object storage.

~~~mermaid
flowchart TD
    A["Ứng dụng cần lưu dữ liệu"] --> Q{"Cách ứng dụng truy cập dữ liệu?"}
    Q -->|"Block device / OS filesystem"| B["Block storage — EBS"]
    Q -->|"File / directory / shared mount"| F["File storage — EFS hoặc FSx"]
    Q -->|"Bucket + key qua API"| O["Object storage — S3"]
~~~

## 2. Block storage và Amazon EBS

### 2.1. Thiết bị khối hoạt động ra sao?

Block device cung cấp không gian dữ liệu được chia thành các khối có địa chỉ. OS quản lý thao tác I/O và thường tạo filesystem như **ext4** hoặc **XFS**. Phía trên filesystem, ứng dụng có thể đọc/ghi file, database data pages hoặc transaction logs.

~~~mermaid
flowchart LR
    APP["Ứng dụng / Database"] --> FS["Filesystem ext4 / XFS"]
    FS --> OS["Linux block I/O"]
    OS --> VOL["EBS volume"]
    VOL --> AZ["Hạ tầng trong một Availability Zone"]
~~~

Block storage phù hợp khi workload cần:

- Boot disk hoặc data disk của máy ảo.
- Truy cập ngẫu nhiên (**random I/O**) với những khối dữ liệu nhỏ.
- Kiểm soát filesystem, dung lượng, IOPS và throughput theo workload.
- Tương thích với phần mềm giả định có một ổ đĩa cục bộ hoặc block device.

**Block storage không có nghĩa ứng dụng không dùng file**. File trên EBS thường được quản lý bởi filesystem của hệ điều hành. “Block” nói về **giao diện mà dịch vụ storage cung cấp**.

### 2.2. EBS là gì?

**Amazon Elastic Block Store (EBS)** cung cấp block volume được quản lý cho EC2. Một volume EBS nằm trong **một AZ cụ thể**; thông thường nó được attach vào EC2 tương thích trong **cùng AZ**. Một instance có thể có root volume và nhiều data volume theo giới hạn tài nguyên.

Ví dụ:

- **Root volume** chứa hệ điều hành EC2.
- **Data volume** chứa file ứng dụng hoặc dữ liệu của database tự quản lý.
- **Scratch/work volume** lưu dữ liệu cần block I/O, với chính sách lưu/backup tùy tính chất.

### 2.3. EBS có chia sẻ giữa nhiều EC2 được không?

Mô hình thông thường là **một EBS volume gắn cho một EC2 instance** tại một thời điểm. **EBS Multi-Attach** hỗ trợ một số loại volume nhất định như io1/io2 trong các điều kiện đã công bố, cho nhiều EC2 **cùng AZ** attach một volume.

Tuy nhiên Multi-Attach **không tự biến EBS thành NFS/SMB shared filesystem**. Nếu nhiều instance đồng thời ghi trên filesystem không hỗ trợ truy cập cluster và không có cơ chế phối hợp/locking, dữ liệu có thể bị hỏng. Khi nhiều EC2 ở nhiều AZ cần cùng một namespace file, nên đánh giá **EFS** hoặc **FSx** tương ứng trước.

### 2.4. Các loại EBS và chỉ số hiệu năng

| Chỉ số | Ý nghĩa | Ứng dụng nhạy với chỉ số |
| --- | --- | --- |
| **IOPS** | Số thao tác đọc/ghi I/O mỗi giây. | Database transaction, truy cập ngẫu nhiên. |
| **Throughput** | Dung lượng dữ liệu truyền mỗi giây (MiB/s). | Đọc/ghi dữ liệu tuần tự và file lớn. |
| **Latency** | Thời gian hoàn thành một thao tác I/O. | Ứng dụng cần phản hồi nhanh. |

Các nhóm EBS volume thường gặp:

- **gp3**: SSD thông dụng, có khả năng cấu hình dung lượng, IOPS và throughput trong giới hạn của volume.
- **io1/io2**: SSD cho workload cần provisioned IOPS và các yêu cầu hiệu năng/độ bền khác theo loại volume.
- **st1/sc1**: HDD cho workload tuần tự hoặc ít truy cập phù hợp; không phải boot volume trong các cấu hình được hỗ trợ.

Chỉ số volume không phải hiệu năng ứng dụng bảo đảm. Giới hạn **EC2 EBS bandwidth**, queue depth, kích thước I/O, filesystem và database cũng tác động tới kết quả.

### 2.5. EBS theo AZ và snapshot

Volume EBS được thiết kế với dự phòng trong AZ, nhưng **volume không tự động di chuyển hoặc attach qua nhiều AZ** khi AZ gặp sự cố. Để khôi phục sang AZ khác, có thể tạo **EBS snapshot**, sau đó tạo volume mới từ snapshot tại AZ đích và thực hiện các bước khôi phục ứng dụng.

EBS snapshot do AWS quản lý, có cơ chế incremental và không xuất hiện như object bình thường trong bucket S3 do bạn tự chọn. Snapshot có thể chứa dữ liệu ở thời điểm nhất định, nhưng để khôi phục một database nhất quán có thể cần phối hợp với hệ quản trị cơ sở dữ liệu, flush/quiesce hoặc ứng dụng.

**EBS không tự cung cấp HA cho database**. Nếu cần database luôn sẵn sàng, cần thiết kế replication, failover hoặc cân nhắc Amazon RDS/Aurora theo yêu cầu.

## 3. File storage: filesystem có thể được chia sẻ

### 3.1. Đặc điểm của file storage

File storage biểu diễn dữ liệu bằng **file**, **directory**, đường dẫn, metadata, quyền đọc/ghi và hành vi filesystem. Ứng dụng mở file theo path, thực hiện read/write, rename, tạo thư mục hoặc sử dụng lock theo **khả năng của giao thức và filesystem**.

Ví dụ:

~~~text
/projects/
  finance/2026/report.pdf
  uploads/avatar-001.png
  processing/jobs/2026-11-20/input.csv
~~~

File storage dùng chung thường truy cập qua mạng:

- **NFS**: phổ biến với Linux/Unix.
- **SMB**: phổ biến với Windows, chia sẻ file và tích hợp Active Directory.
- Các protocol chuyên biệt khác tùy filesystem.

**File storage không đồng nhất với “có một đường dẫn file trong OS”.** EBS cũng có thể chứa filesystem; điểm khác là dịch vụ file storage trình bày **filesystem dùng qua mạng** cho những client được phép mount.

### 3.2. Amazon EFS cho shared filesystem Linux

**Amazon Elastic File System (EFS)** cung cấp filesystem được quản lý qua **NFS**, giúp nhiều client/workload Linux có thể sử dụng chung namespace. EFS thích hợp khi các EC2 instance hoặc container cần nhìn thấy cùng dữ liệu theo đường dẫn filesystem.

~~~mermaid
flowchart TB
    subgraph AZ1["Availability Zone A"]
        A["EC2/App A"]
        MA["Mount target A"]
    end
    subgraph AZ2["Availability Zone B"]
        B["EC2/App B"]
        MB["Mount target B"]
    end
    EFS[("Amazon EFS Regional")]
    A -->|"NFS TCP/2049"| MA
    B -->|"NFS TCP/2049"| MB
    MA --> EFS
    MB --> EFS
~~~

Với **EFS Regional**, dữ liệu được thiết kế lưu trên nhiều AZ, và có thể tạo mount target trong những AZ thích hợp. **EFS One Zone** có đặc tính lưu trữ một AZ và rủi ro AZ khác. Không coi mọi EFS đều là Multi-AZ.

Các đặc điểm EFS cần biết:

- Storage tăng/giảm theo lượng dữ liệu được lưu trong mô hình của dịch vụ.
- Nhiều client có thể truy cập đồng thời với semantics NFS theo khả năng hỗ trợ.
- Có **EFS Access Points** để kiểm soát root directory và thiết lập POSIX identity cho workload dùng access point.
- Hiệu năng phụ thuộc **throughput mode**, storage class, mẫu truy cập metadata, network và mức đồng thời.
- Cần mount target, DNS, Security Group, NFS port **2049**, quyền POSIX và TLS/IAM khi áp dụng.

EFS không trực tiếp là **SMB share cho Windows**. Với ứng dụng Windows dựa trên SMB/NTFS/Active Directory, cần cân nhắc FSx for Windows File Server.

### 3.3. Amazon FSx cho filesystem chuyên biệt

**Amazon FSx** không phải một filesystem duy nhất. Đây là nhóm dịch vụ được quản lý, lựa chọn theo hệ điều hành, giao thức và đặc điểm workload.

| Dịch vụ | Đặc điểm | Trường hợp phù hợp |
| --- | --- | --- |
| **FSx for Windows File Server** | SMB, Windows ACL và tích hợp Active Directory theo khả năng hỗ trợ. | File server/ứng dụng Windows cần shared folder. |
| **FSx for Lustre** | Filesystem hiệu năng cao, hỗ trợ tích hợp S3 cho những workflow HPC/ML. | Tính toán hiệu năng cao, training/analytics yêu cầu throughput. |
| **FSx for NetApp ONTAP** | Hỗ trợ nhiều tính năng lưu trữ doanh nghiệp và giao thức như NFS, SMB, iSCSI. | NAS doanh nghiệp, ứng dụng cần khả năng ONTAP. |
| **FSx for OpenZFS** | Filesystem dựa trên OpenZFS, hỗ trợ NFS và các đặc tính liên quan. | Ứng dụng Linux muốn dùng mô hình filesystem OpenZFS. |

Một số FSx, đặc biệt FSx for NetApp ONTAP, có thể hỗ trợ **block access qua iSCSI**. Vì vậy tên dịch vụ không luôn xác định một mô hình truy cập duy nhất; hãy kiểm tra **giao thức đang bật**.

Tính năng Multi-AZ, backup, replication, endpoint, throughput capacity và IOPS của FSx thay đổi theo biến thể/deployment. Không dùng thông số của Lustre để suy ra chi phí hoặc semantics của Windows File Server.

### 3.4. Một EBS được mount và EFS đều có đường dẫn: khác gì?

~~~text
/data/orders.db               # Có thể nằm trong filesystem trên EBS
/mnt/shared/orders/export.csv # Có thể nằm trong EFS NFS
~~~

Ở ví dụ đầu, **EC2/OS** quản lý filesystem trên EBS volume; nếu máy bị thay thế hoặc instance khác cần dữ liệu, phải thiết kế quy trình attach/restore/replication thích hợp.

Ở ví dụ sau, **EFS** cung cấp filesystem chung; nhiều client có thể mount và thấy namespace liên quan mà không cần di chuyển EBS volume giữa các máy. Đổi lại, cần bảo đảm network mount, NFS semantics và quyền của client.

## 4. Object storage và Amazon S3

### 4.1. Object gồm những gì?

Một **object** bao gồm nội dung (body), **key** và metadata/thuộc tính. Trong Amazon S3, object nằm trong **bucket**. Ứng dụng gọi API như **PutObject**, **GetObject**, **ListObjectsV2** hoặc **DeleteObject** để thao tác.

~~~mermaid
flowchart LR
    APP["Ứng dụng / AWS SDK"] -->|"HTTPS API"| S3["Amazon S3"]
    S3 --> BUCKET[("Bucket example-assets")]
    BUCKET --> O1["images/avatar.png"]
    BUCKET --> O2["reports/2026/q4.pdf"]
    BUCKET --> O3["logs/app/event.json"]
~~~

Object key **reports/2026/q4.pdf** trông như đường dẫn nhưng dấu gạch chéo chỉ là một phần trong key/prefix theo mô hình S3 general-purpose bucket. Nó không tự sinh đầy đủ semantics của thư mục POSIX như inode, atomic rename hay file locking trên NFS.

### 4.2. S3 phù hợp với những loại dữ liệu nào?

- Ảnh, video, PDF, tệp đính kèm của người dùng.
- Data lake, dữ liệu phân tích, batch ETL input/output.
- Backup, archive, object phiên bản, log dài hạn.
- Static assets phân phối qua Amazon CloudFront.
- Dữ liệu nhiều ứng dụng cần truy cập bằng SDK/HTTP API.

S3 cung cấp nhiều storage class. **S3 Standard** được thiết kế lưu dữ liệu qua nhiều AZ, còn các class như **S3 One Zone-IA** hoặc **S3 Express One Zone** có tính chất một AZ. Không suy rằng **mọi object S3 đều mang cùng mức phân tán AZ, latency, retrieval và phí**.

### 4.3. S3 khác filesystem POSIX

Một filesystem thông thường cho phép ứng dụng mở file và thao tác theo offset, rename, chmod, sử dụng locking và metadata của filesystem. **S3 object API không đảm bảo toàn bộ các hành vi đó**.

- Object thường được tạo/ghi thay thế bằng PUT hoặc cơ chế upload hỗ trợ.
- GET có thể đọc object hoặc byte-range phù hợp, nhưng đây không phải block device cho ứng dụng ghi ngẫu nhiên từng sector.
- S3 không biến nhiều thao tác cập nhật nhiều object thành một giao dịch ACID.
- Một số gateway/mount adapter cho S3 trình bày đường dẫn file, nhưng có **giới hạn consistency, rename, locking, caching hoặc hiệu năng** khác filesystem POSIX.

Vì vậy **không đặt trực tiếp dữ liệu MySQL/PostgreSQL tự quản lý lên một “S3 mount” như thể đó là EBS** chỉ vì driver hiển thị một thư mục.

### 4.4. Tính nhất quán của S3

S3 hỗ trợ **strong read-after-write consistency** cho các thao tác object được tài liệu hóa như PUT, GET, LIST và DELETE. Sau khi ghi object thành công, các request tiếp theo quan sát dữ liệu theo mô hình nhất quán được công bố.

Điều này không có nghĩa nhiều object cập nhật trong cùng một giao dịch ACID, không thay thế khóa transaction của database và không làm S3 trở thành filesystem NFS.

### 4.5. Bucket/key và versioning

Ví dụ:

~~~text
Bucket: example-course-assets
Key:    uploads/2026/contract.pdf
S3 URI: s3://example-course-assets/uploads/2026/contract.pdf
~~~

Nếu bật **versioning**, cùng một key có thể có nhiều version để phục hồi khi overwrite/xóa theo điều kiện. Versioning không tự làm ứng dụng an toàn trước mọi lỗi logic hoặc thay thế backup/retention policy.

## 5. Bảng so sánh ba kiểu lưu trữ

| Đặc điểm | **Block** | **File** | **Object** |
| --- | --- | --- | --- |
| Giao diện | Block device; OS tạo filesystem nếu cần. | Filesystem, file path, NFS/SMB/tính năng chuyên biệt. | Bucket, key, HTTP API/SDK. |
| AWS tiêu biểu | **EBS**. | **EFS**, **FSx**. | **S3**. |
| Đơn vị truy cập | Khối I/O của thiết bị. | File/thư mục. | Object. |
| Random read/write | Phù hợp workload/FS được hỗ trợ. | Theo semantics filesystem và giao thức. | Không phải API ghi ngẫu nhiên ở byte-offset như ổ đĩa. |
| Chia sẻ nhiều máy | EBS thông thường giới hạn một instance; Multi-Attach có điều kiện. | Thiết kế cho multi-client theo kiểu filesystem. | Nhiều client độc lập qua API với quyền thích hợp. |
| Kiểu truy cập | OS/app thấy block volume. | OS/app thấy mount/share. | Ứng dụng dùng SDK/API. |
| Dữ liệu tiêu biểu | Boot volume, database tự quản, local data. | Shared workspace, SMB share, HPC files. | Ảnh, video, log, backup, data lake. |
| Phạm vi AZ | EBS volume thuộc một AZ. | EFS Regional/One Zone, FSx tùy deployment. | S3 Standard multi-AZ; class khác có thể một AZ. |
| Mở rộng | Provision volume và mở rộng FS phù hợp. | EFS co giãn theo dữ liệu; FSx theo capacity/provisioning riêng. | Mở rộng lượng object theo giới hạn dịch vụ. |
| Hiệu năng | Volume IOPS, throughput, EC2 EBS bandwidth. | Throughput, metadata operations, network, concurrency. | Request rate, size, concurrency, data processing. |
| Quyền truy cập | IAM thao tác AWS, OS/filesystem permissions. | IAM/network, POSIX/SMB/ACL và resource policy phù hợp. | IAM, bucket/object policy, Block Public Access, KMS. |
| Backup | EBS snapshots, AWS Backup, app-consistent backup. | Backup/replication/lifecycle theo EFS hoặc FSx. | Versioning, replication, Object Lock, lifecycle khi hỗ trợ. |
| Chi phí | GB đã provision, IOPS/throughput bổ sung, snapshot. | GB lưu/provision, throughput, backup, giao thức/deployment. | Storage class, request, retrieval, data transfer, retention. |

**Lưu ý:** Chất lượng bảo vệ dữ liệu không thể quy hết thành bảng “block kém bền hơn object”. Durability, availability và recoverability phải đối chiếu **từng dịch vụ, cấu hình, storage class, backup và yêu cầu RPO/RTO**.

## 6. Cách chọn dịch vụ cho các workload AWS

### 6.1. Ma trận quyết định

| Yêu cầu | Dịch vụ nên đánh giá trước | Lý do |
| --- | --- | --- |
| Ổ đĩa boot cho EC2. | **EBS**. | EC2 cần block volume cho root filesystem. |
| Self-managed PostgreSQL/MySQL trên EC2. | **EBS SSD** và thiết kế DB backup/replication. | Database cần block/filesystem và latency/IOPS phù hợp. |
| Nhiều EC2 Linux ở nhiều AZ cần chung một thư mục. | **EFS Regional**. | Shared NFS filesystem cho nhiều client. |
| Ứng dụng Windows cần SMB và Active Directory. | **FSx for Windows File Server**. | Windows share/permissions. |
| ML/HPC cần filesystem thông lượng lớn. | **FSx for Lustre** theo nhu cầu workload. | FS cho tính toán hiệu năng cao, tích hợp workflow dữ liệu. |
| Ảnh/avatar, nội dung web, video, file upload qua SDK. | **S3**. | Object storage, lifecycle, API và tích hợp CloudFront. |
| Lưu log/data lake/archive. | **S3** với class phù hợp. | Truy cập object, dữ liệu quy mô lớn và lưu trữ dài hạn. |
| Cần NFS/SMB cùng khả năng storage doanh nghiệp chuyên biệt. | **FSx for NetApp ONTAP** hoặc biến thể phù hợp. | Hỗ trợ giao thức và chức năng cụ thể. |
| Dữ liệu tạm gần compute, có bản gốc lâu dài. | **EBS/EFS/FSx kết hợp S3**. | Tách working space khỏi object source of truth. |

Không phải lúc nào tự chạy database trên EBS cũng tối ưu. **Amazon RDS/Aurora** có thể giảm phần vận hành database, backup và một số tác vụ HA khi phù hợp yêu cầu. Bài học so sánh giao diện storage; việc chọn DB managed là quyết định kiến trúc liên quan.

### 6.2. Cây lựa chọn

~~~mermaid
flowchart TD
    A["Workload cần lưu dữ liệu"] --> B{"Cần filesystem và đường dẫn POSIX/Windows?"}
    B -->|"Không, ứng dụng dùng object API"| S3["Đánh giá Amazon S3"]
    B -->|"Có"| C{"Một hay nhiều client cần chung namespace?"}
    C -->|"Một client / disk cho EC2"| EBS["Đánh giá Amazon EBS"]
    C -->|"Nhiều client"| D{"Giao thức và workload?"}
    D -->|"NFS Linux phổ biến"| EFS["Đánh giá Amazon EFS"]
    D -->|"SMB Windows / HPC / ONTAP / OpenZFS"| FSX["Đánh giá Amazon FSx"]
    S3 --> V["Kiểm tra hiệu năng, AZ, backup, bảo mật, tổng chi phí"]
    EBS --> V
    EFS --> V
    FSX --> V
~~~

Khi phần mềm vừa cần **POSIX filesystem** để xử lý tạm vừa cần **object storage** cho dữ liệu lâu dài, giải pháp thích hợp thường kết hợp hai mô hình.

## 7. Kiến trúc minh họa: ứng dụng xử lý tài liệu

Giả sử ứng dụng nhận ảnh/PDF, xử lý tệp và trả kết quả; cần phục vụ traffic nhiều AZ:

- **ALB** phân phối request tới hai EC2 ở hai AZ.
- Mỗi EC2 có **EBS** cho root volume và file tạm cục bộ.
- Hai EC2 mount **EFS Regional** nếu workflow thật sự cần dùng chung đường dẫn processing.
- File upload gốc và kết quả được đặt trong **S3** qua SDK.
- **Lambda** có thể xử lý S3 events theo kiến trúc tích hợp; metadata giao dịch được lưu trong database phù hợp.

~~~mermaid
flowchart TB
    U["Người dùng"] -->|"HTTPS"| ALB["Application Load Balancer"]
    subgraph AZ1["AZ A"]
      A["EC2 App A"]
      VA[("EBS A")]
      A --- VA
    end
    subgraph AZ2["AZ B"]
      B["EC2 App B"]
      VB[("EBS B")]
      B --- VB
    end
    ALB --> A
    ALB --> B
    EFS[("EFS Regional — shared workspace")]
    S3[("S3 — originals/results")]
    A <-->|"NFS"| EFS
    B <-->|"NFS"| EFS
    A <-->|"S3 API"| S3
    B <-->|"S3 API"| S3
    S3 -->|"S3 event khi được cấu hình"| L["Lambda processor"]
~~~

Sơ đồ là luồng **logic**, chưa bao gồm toàn bộ VPC, subnet, mount targets, route, endpoints, Security Group, IAM, database, health checks hoặc cơ chế khôi phục. Tính sẵn sàng cao phải được **kiểm chứng bằng thiết kế và thử failover**, không chỉ vì có hai EC2.

| Nhóm dữ liệu | Nơi lưu | Lý do |
| --- | --- | --- |
| Hệ điều hành EC2 | EBS riêng từng instance. | Boot và quản lý OS filesystem. |
| Cache tạm cục bộ | EBS hoặc instance store tùy yêu cầu mất dữ liệu. | Tránh đẩy dữ liệu ngắn hạn qua mạng nếu không cần. |
| Workspace nhiều worker cùng dùng | EFS Regional. | Shared NFS namespace. |
| Bản gốc và kết quả dài hạn | S3. | Object API, lifecycle và tích hợp sự kiện. |
| Transaction và metadata nghiệp vụ | RDS/Aurora hay database phù hợp. | Truy vấn/transaction; không thay DB bằng file/object chỉ vì lưu được dữ liệu. |

### 7.1. Luồng xử lý

1. Người dùng upload tài liệu; app xác thực/authorization và kiểm tra kích thước/loại file.
2. App ghi tạm vào EBS hoặc EFS tùy nhu cầu đồng bộ với worker khác.
3. App lưu bản gốc trong S3 theo object key được quản lý và quyền IAM tối thiểu.
4. Hệ thống ghi metadata trong database; phát sự kiện/điều phối xử lý khi phù hợp.
5. Worker xuất kết quả vào S3; app trả URL hoặc truy xuất nội dung qua cơ chế kiểm soát quyền.

**Nếu EC2 ở AZ A bị thay thế**, EC2 ở AZ B không tự có dữ liệu vừa được ghi **chỉ vào EBS A**. Cần bảo đảm dữ liệu quan trọng đã được đưa vào shared filesystem, S3 hoặc datastore có khả năng phục hồi phù hợp.

## 8. Hiệu năng: không so sánh bằng một con số duy nhất

### 8.1. IOPS, throughput, latency và concurrency

| Khía cạnh | Câu hỏi |
| --- | --- |
| **IOPS** | Bao nhiêu I/O nhỏ/giây? |
| **Throughput** | Bao nhiêu MiB/s cần xử lý? |
| **Latency** | Mỗi thao tác mất bao lâu, đặc biệt tail latency? |
| **Concurrency** | Có bao nhiêu client/request cùng lúc? |
| **Operation pattern** | Random reads/writes, sequential, nhiều file nhỏ hay object lớn? |

Ví dụ:

- Database trên EC2 thường quan tâm EBS IOPS/latency và giới hạn bandwidth của EC2.
- EFS/FSx phải xét metadata operations, throughput mode/provision và network latency.
- S3 workload upload tệp lớn có thể tối ưu bằng multipart upload và concurrency; nhiều object nhỏ có thể phát sinh nhiều request/cost.
- Truy cập từ AZ/Region khác nhau có thể ảnh hưởng latency/data transfer cost.

### 8.2. Vì sao S3 có thể không hợp với random write?

Filesystem trên block/file storage có thể cho ứng dụng mở file, sửa một phần dữ liệu ở offset. S3 thường cung cấp API thao tác **object**, nên việc cập nhật nội dung thông thường là upload/ghi thay thế object hoặc sử dụng những cơ chế API hỗ trợ. Byte-range GET chỉ là cách đọc một vùng object, không biến S3 thành một volume block writable theo chuẩn POSIX.

Một số tính năng chuyên biệt của S3/storage class bổ sung hành vi nhất định, nhưng không nên dựa vào ngoại lệ để giả định S3 tương thích mọi filesystem.

### 8.3. Bản thân filesystem cũng có giới hạn

EFS/FSx không đảm bảo ứng dụng nhiều máy tự đạt consistency nghiệp vụ. File locking, caching, metadata, POSIX/Windows semantics và quy tắc ghi đồng thời cần được ứng dụng thiết kế phù hợp. Hai process cùng sửa một file không có phối hợp vẫn có thể làm dữ liệu sai ở mức nghiệp vụ.

## 9. Availability, durability và khôi phục

Ba khái niệm khác nhau:

- **Availability:** hệ thống có đọc/ghi được dữ liệu đúng lúc cần không?
- **Durability:** dữ liệu đã ghi được bảo vệ đến mức nào trước những loại lỗi dịch vụ/hạ tầng theo thiết kế?
- **Recoverability:** có khôi phục được đúng phiên bản dữ liệu sau xóa nhầm, ghi đè sai hoặc sự cố lớn trong mục tiêu đã định không?

### 9.1. EBS: tính theo AZ, backup bằng snapshot

Volume EBS tồn tại trong một AZ, có cơ chế dự phòng của dịch vụ bên trong AZ. Để bảo vệ khỏi mất dữ liệu do lỗi logic hoặc hư hỏng lớn, cần **snapshot**/backup và thiết kế khôi phục. Snapshot có thể giúp tạo volume mới ở AZ khác, nhưng không tự làm database đang chạy chuyển đổi dự phòng tức thì.

Nếu snapshot được chụp khi database đang ghi liên tục, cần xem mức độ **crash consistency** hay **application consistency** mà hệ thống yêu cầu.

### 9.2. EFS và FSx

**EFS Regional** được thiết kế lưu dữ liệu trên nhiều AZ; **EFS One Zone** là lựa chọn một AZ. Tính năng backup, lifecycle và replication cần cấu hình theo yêu cầu và loại filesystem.

FSx có các phương án single-AZ/multi-AZ/backup khác nhau theo **Windows, Lustre, ONTAP, OpenZFS** và deployment đã chọn. Khi cần HA, phải kiểm tra đúng biến thể. Không suy rằng “đã dùng FSx” đồng nghĩa tự có failover multi-AZ.

### 9.3. S3: class, versioning, replication và Object Lock

- **S3 Standard** được thiết kế lưu object qua nhiều AZ.
- Một số storage class như **One Zone-IA** hoặc **Express One Zone** có đặc điểm một AZ.
- **Versioning** giúp giữ các phiên bản object theo cấu hình.
- **Replication** sao chép object theo rule/bucket/Region được chọn, phải hiểu phạm vi và độ trễ sao chép.
- **S3 Object Lock** hỗ trợ retention/WORM trong những trường hợp phù hợp, cần cấu hình và quyền chính xác.
- **Lifecycle** quản lý chuyển class và xóa theo hạn; policy sai có thể gây mất dữ liệu ngoài mong muốn.

Có versioning/replication **không mặc nhiên thay thế backup độc lập và kiểm tra restore**; việc xóa/ghi đè hợp lệ, quyền quá rộng hay lỗi ứng dụng vẫn có thể làm dữ liệu không phù hợp yêu cầu nghiệp vụ.

### 9.4. RPO và RTO

- **RPO (Recovery Point Objective)**: lượng dữ liệu mất tối đa có thể chấp nhận, thường biểu diễn bằng thời gian.
- **RTO (Recovery Time Objective)**: thời gian phục hồi tối đa có thể chấp nhận.

Ví dụ yêu cầu RPO **15 phút** và RTO **1 giờ**. Chỉ có snapshot EBS **một lần mỗi ngày** không đủ để chứng minh đạt RPO 15 phút. Phải chọn phương án backup/replication thích hợp và **diễn tập khôi phục** để đo RPO/RTO thực tế.

Không nhầm **độ bền dữ liệu theo thiết kế dịch vụ** với khả năng phục hồi mọi lỗi do người dùng/ứng dụng.

## 10. Bảo mật theo từng mô hình

### 10.1. EBS

- **IAM** kiểm soát thao tác tạo/gắn/tháo/snapshot/sao chép/chia sẻ volume theo quyền AWS.
- **OS filesystem permissions** và ứng dụng quyết định user/process nào được đọc dữ liệu khi EC2 đã sử dụng volume.
- **EBS encryption** sử dụng AWS KMS theo cấu hình; kiểm tra encryption by default khi cần.
- Bảo vệ snapshot và quyền KMS, vì snapshot có thể chứa dữ liệu nhạy cảm.

EBS volume không phải NFS server phải mở inbound TCP/2049 ở SG của volume. SG bảo vệ network của EC2; EBS là lớp block riêng.

### 10.2. EFS

Để client mount EFS thường cần đồng thời:

1. **Mount target** phù hợp trong VPC và DNS/route hoạt động.
2. **Security Group** của mount target cho phép TCP/**2049** từ client được phép, cùng outbound/NACL tương ứng.
3. OS có NFS client hoặc EFS mount helper.
4. Quyền **POSIX UID/GID/mode** hoặc EFS Access Point phù hợp.
5. Khi dùng **IAM authorization**, policy cho phép các quyền như **elasticfilesystem:ClientMount** và **ClientWrite** nếu cần; cấu hình TLS và EFS mount helper theo hướng dẫn.

Lỗi timeout khi mount thường gợi ý network/mount target. Lỗi permission denied có thể liên quan POSIX, IAM policy hoặc các tùy chọn mount. Không mở TCP/2049 từ Internet chỉ để xử lý lỗi.

### 10.3. FSx

Cơ chế bảo mật phụ thuộc biến thể:

- **FSx Windows:** SMB, Active Directory, NTFS/SMB share ACL và Security Group.
- **FSx Lustre:** quyền/mount/compute clients theo cơ chế Lustre.
- **FSx ONTAP/OpenZFS:** NFS/SMB/iSCSI, export/share permissions và các ràng buộc kết nối liên quan.

IAM quản lý tài nguyên AWS, nhưng thường **không thay thế quyền file/user của giao thức**.

### 10.4. S3

- **IAM identity policy**, **bucket policy**, S3 Access Point policy (nếu dùng) và ràng buộc khác kiểm soát API.
- **Block Public Access** giúp ngăn cấu hình công khai ngoài dự kiến; phải xem cả cấp account và bucket.
- **SSE-S3** được S3 áp dụng mặc định cho object mới; nếu cần SSE-KMS, phải quản lý key policy/quyền KMS tương ứng.
- **S3 Object Ownership**, versioning, presigned URLs và lifecycle cần được thiết kế theo quyền, dữ liệu và yêu cầu retention.
- **HTTPS/TLS** bảo vệ đường truyền; VPC endpoints/endpoint policy có thể tham gia kiến trúc truy cập riêng.

Phân biệt ARN:

~~~text
Bucket ARN: arn:aws:s3:::example-private-reports
Object ARN: arn:aws:s3:::example-private-reports/reports/*
~~~

**s3:ListBucket** hoạt động ở cấp bucket, còn **s3:GetObject** thường yêu cầu ARN ở cấp object. Khi object mã hóa bằng KMS, quyền S3 chưa chắc đủ; có thể còn cần **kms:Decrypt** và quyền key policy thích hợp.

### 10.5. Logging và trách nhiệm chia sẻ

AWS vận hành hạ tầng storage, nhưng khách hàng phải quyết định quyền truy cập, cấu hình backup, log và khả năng phục hồi. Theo nhu cầu:

- EBS: theo dõi volume metrics, snapshot policy, CloudTrail API, OS/DB logs.
- EFS/FSx: file system metrics, client/mount errors, audit theo dịch vụ và app logs.
- S3: CloudTrail **data events** khi cấu hình, access logging/metrics/CloudWatch và app logs.

Không đồng nhất việc dịch vụ **có khả năng log** với việc log đã được bật đầy đủ.

## 11. Chi phí: tổng chi phí phụ thuộc mô hình truy cập

| Loại | Khoản phí cần đánh giá | Bẫy phổ biến |
| --- | --- | --- |
| **EBS** | GB **provisioned**, IOPS/throughput theo loại volume, snapshot, data transfer và tác vụ khác khi áp dụng. | Dung lượng provision nhiều hơn dữ liệu sử dụng vẫn có thể phải trả phí volume. |
| **EFS** | GB dữ liệu lưu theo class, throughput mode, requests/access, backup và các phí liên quan theo cấu hình. | So giá GB nhưng bỏ qua throughput, class và pattern truy cập. |
| **FSx** | Capacity, throughput capacity, IOPS, backups, deployment và các phí riêng của từng biến thể. | Dùng đơn giá của biến thể FSx khác để ước tính. |
| **S3** | Storage class, PUT/GET/LIST requests, retrieval, transfer, replication, lifecycle transitions, logging. | Storage class rẻ nhưng retrieval/early deletion/request/egress đắt với access pattern thực tế. |

Ví dụ EBS **100 GiB provisioned** có thể chịu phí tính theo 100 GiB dù filesystem mới lưu 15 GiB dữ liệu. Ngược lại, chuyển toàn bộ dữ liệu sang S3 chỉ vì giá lưu trữ thấp có thể tăng chi phí nếu ứng dụng đọc/ghi nhiều lần và cần lớp chuyển đổi filesystem.

Trước khi chọn, thu thập:

1. Dung lượng hiện tại, dự báo tăng trưởng và retention.
2. Số client, tốc độ I/O, object/file size và concurrency.
3. Mức latency/IOPS/throughput cần đạt.
4. RPO/RTO, AZ/Region, backup và yêu cầu phục hồi.
5. Đường truyền dữ liệu, egress, cross-AZ/cross-Region, NAT/VPC endpoint.
6. Quy định mã hóa, KMS, audit log và lưu giữ dữ liệu.

Để có con số dự toán, dùng bảng giá AWS chính thức và Pricing Calculator theo **Region, storage class và cấu hình hiện hành**; không coi một mức giá GB là kết luận chung cho mọi môi trường.

## 12. Ví dụ AWS CLI chỉ đọc

Các lệnh dưới đây **không tạo, định dạng, ghi, xóa hoặc mount tài nguyên**. Cần AWS CLI đã được cấu hình và principal có quyền đọc tài nguyên. Các ID/bucket là ví dụ; thay bằng giá trị thuộc môi trường được phép truy cập.

### 12.1. Xác định danh tính và Region

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

Với EBS/EFS/FSx, đặt đúng Region trong CLI rất quan trọng. S3 bucket có Region riêng cần kiểm tra khi truy cập.

### 12.2. EBS

~~~bash
aws ec2 describe-volumes \
  --region ap-southeast-1 \
  --query "Volumes[].{Volume:VolumeId,AZ:AvailabilityZone,Type:VolumeType,SizeGiB:Size,Iops:Iops,Throughput:Throughput,State:State}"

aws ec2 describe-volumes \
  --filters Name=attachment.instance-id,Values=i-0123456789abcdef0 \
  --region ap-southeast-1

aws ec2 describe-snapshots \
  --owner-ids self \
  --region ap-southeast-1 \
  --query "Snapshots[].{Snapshot:SnapshotId,Volume:VolumeId,Time:StartTime,State:State}"
~~~

Kiểm tra **AvailabilityZone**, loại volume, IOPS, throughput, thời điểm snapshot và trạng thái attach. Snapshot list có thể rất dài; nếu môi trường lớn nên dùng lọc/phân trang phù hợp.

### 12.3. EFS

~~~bash
aws efs describe-file-systems \
  --region ap-southeast-1

aws efs describe-mount-targets \
  --file-system-id fs-0123456789abcdef0 \
  --region ap-southeast-1

aws efs describe-mount-target-security-groups \
  --mount-target-id fsmt-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Xem **LifeCycleState**, performance/throughput settings, mount target AZ/subnet/IP và Security Group; kiểm tra backup/lifecycle riêng theo tài nguyên nếu cần.

### 12.4. FSx

~~~bash
aws fsx describe-file-systems \
  --region ap-southeast-1 \
  --query "FileSystems[].{Id:FileSystemId,Type:FileSystemType,StorageGiB:StorageCapacity,State:Lifecycle}"
~~~

Nếu cần xem deployment type, endpoints, throughput hoặc security của một biến thể, chạy describe-file-systems với kết quả đầy đủ rồi đối chiếu đúng hệ filesystem; không suy tất cả FSx có cùng thuộc tính.

### 12.5. S3

~~~bash
aws s3api list-buckets --query "Buckets[].Name"

aws s3api get-bucket-location \
  --bucket example-private-reports

aws s3api get-public-access-block \
  --bucket example-private-reports

aws s3api get-bucket-versioning \
  --bucket example-private-reports

aws s3api get-bucket-encryption \
  --bucket example-private-reports

aws s3api list-objects-v2 \
  --bucket example-private-reports \
  --prefix reports/2026/ \
  --max-items 10
~~~

Nếu nhận **AccessDenied**, không suy bucket không tồn tại. Trường hợp Block Public Access chưa được cấu hình hoặc lệnh không trả kết quả mong muốn cần rà soát cả policy/quyền thực tế; không coi đó là kết luận an toàn.

### 12.6. Linux EC2: xem filesystem mà không thay đổi dữ liệu

~~~bash
lsblk -f
findmnt
df -hT
mount | grep -E "nfs|efs|xfs|ext4"
~~~

EBS có thể hiển thị dưới tên thiết bị NVMe thay vì tên bạn khai báo lúc attach. Một mount NFS có thể là EFS hoặc NFS server khác, nên phải xem source/mount options và cấu hình liên quan trước khi kết luận.

## 13. Khắc phục sự cố theo lớp

### 13.1. EC2 không thấy volume EBS

Xem EBS volume/EC2 có **cùng AZ** không, trạng thái attach, tên NVMe trong OS, partition/filesystem hiện có và permission/kms khi áp dụng. **Không format/khởi tạo filesystem lại trên volume chứa dữ liệu cần giữ**.

### 13.2. EFS mount thất bại

- **Timeout:** kiểm tra DNS, mount targets, Security Group TCP/2049, NACL/route và trạng thái client network.
- **Permission denied:** xem POSIX UID/GID, directory mode, EFS Access Point, IAM authorization/resource policy và mount options.
- **Hiệu năng chậm:** xem workload metadata, NFS cache, client network, throughput mode và volume operations.

Không mở SG NFS 0.0.0.0/0 để “chữa tạm” khi chưa xác định nguồn client và vấn đề.

### 13.3. FSx không kết nối được

Kiểm tra theo giao thức đang dùng: Windows cần DNS/Active Directory/SMB/NTFS permissions; Lustre cần client/mount và luồng HPC; ONTAP/OpenZFS cần xem NFS/SMB/iSCSI, export policy và network. Tránh sử dụng hướng dẫn xử lý một FSx variant cho variant khác.

### 13.4. S3 trả AccessDenied

1. Xác định principal thật từ **aws sts get-caller-identity** trong môi trường ứng dụng.
2. Kiểm tra action và đúng bucket/object ARN.
3. Rà soát identity-based policy, bucket/resource policy, Block Public Access, SCP/boundary và điều kiện.
4. Với SSE-KMS, kiểm tra KMS key policy/permission.
5. Nếu policy yêu cầu VPC endpoint, kiểm tra request đi qua đúng endpoint.
6. Với presigned URL, xem thời hạn, method, request headers và quyền của người ký.

HTTP **403 AccessDenied** thường là vấn đề quyền/điều kiện đã áp dụng sau khi request tới được endpoint; khác với **timeout** do đường mạng.

### 13.5. Chi phí S3 bất ngờ tăng

Đối chiếu object sizes, số PUT/GET/LIST, lựa chọn storage class, retrieval/early deletion, transfer, replication và logging. Một bucket có nhiều object nhỏ nhưng số request lớn có thể có pattern chi phí khác với một bucket chứa ít object lớn cùng tổng GB.

## 14. Những hiểu lầm cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Block storage không lưu được file.” | OS thường tạo filesystem trên block device để lưu file. |
| “EBS là filesystem chia sẻ cho các EC2 ở nhiều AZ.” | EBS volume thuộc một AZ; Multi-Attach có điều kiện và cần cluster-aware coordination. |
| “EFS giống block device EBS.” | EFS cung cấp filesystem NFS; client mount qua mạng. |
| “EFS là SMB share cho Windows.” | EFS là NFS; SMB Windows thường dùng FSx for Windows File Server. |
| “Tất cả FSx đều dùng cùng một giao thức.” | FSx có Windows, Lustre, ONTAP, OpenZFS với các giao thức/tính năng khác nhau. |
| “S3 key có / là thư mục POSIX.” | Prefix/key không có mọi semantics POSIX. |
| “Có tool mount S3 thì S3 thay được EBS cho database.” | Mount adapter không bảo đảm block/random write/locking như database cần. |
| “S3 luôn dùng nhiều AZ.” | Một số storage class là One Zone. |
| “Snapshot có nghĩa đạt RPO/RTO.” | Cần backup frequency, consistency, restore plan và kiểm thử. |
| “IAM Allow đủ để mount EFS.” | NFS TCP/2049, POSIX, mount target, TLS và network vẫn quan trọng. |
| “S3 server-side encryption là đủ bảo mật.” | Còn IAM/bucket policy, KMS, access path, versioning, audit và ứng dụng. |
| “Storage rẻ nhất/GB luôn rẻ nhất.” | Tổng phí còn phụ thuộc IOPS, requests, retrieval, data transfer, backup, thời gian dùng. |

## 15. Tình huống thực hành và lời giải

### Tình huống A — Avatar trên website Auto Scaling

**Bối cảnh:** Một website chạy nhiều EC2 trên hai AZ; ảnh người dùng phải có sẵn ở mọi instance.

**Lời giải:** Nếu ứng dụng xử lý ảnh qua SDK/API, **S3** phù hợp cho object gốc, có thể kết hợp CloudFront. Nếu phần mềm hiện hữu bắt buộc chia sẻ cùng filesystem path và cần NFS, cân nhắc **EFS Regional**. Không dùng EBS cục bộ của một instance làm nơi duy nhất lưu ảnh quan trọng.

### Tình huống B — Database trên EC2

**Bối cảnh:** MySQL tự quản lý cần transactional reads/writes và log với latency thấp.

**Lời giải:** Đánh giá **EBS SSD** theo IOPS/latency và bandwidth của EC2; sử dụng cơ chế backup/HA của database. Nếu muốn giảm khối lượng quản trị và được tính năng phù hợp, so sánh với **Amazon RDS**. Không trỏ datadir trực tiếp vào S3 object API.

### Tình huống C — File server Windows cho nhóm kế toán

**Bối cảnh:** Ứng dụng cần SMB, Windows ACL và Active Directory.

**Lời giải:** **FSx for Windows File Server** là ứng viên hợp lý. Kiểm tra network, AD/SMB permissions, HA option, backup, throughput và chi phí. EFS NFS không tự thay thế Windows share.

### Tình huống D — Lưu file kiểm toán nhiều năm

**Bối cảnh:** Log và PDF lưu lâu dài, hiếm khi đọc, yêu cầu chống xóa nhầm.

**Lời giải:** **S3** với storage class/lifecycle phù hợp; xem Object Lock/retention khi điều kiện cần, versioning, quyền bucket và chi phí retrieval/minimum storage duration. Lập kế hoạch thử khôi phục nếu dữ liệu cần chứng minh tính toàn vẹn.

### Tình huống E — Mất một AZ

**Bối cảnh:** Ứng dụng một EC2 và một EBS volume ở AZ A; mục tiêu RPO 15 phút, RTO 1 giờ.

**Lời giải:** EBS volume một AZ không tự đáp ứng mục tiêu khi AZ mất khả dụng. Cần replication/backup tần suất phù hợp, khả năng tạo volume/khởi chạy ở AZ khác, phục hồi database nhất quán và kiểm thử thời gian thực tế. Tùy dữ liệu, EFS Regional hoặc S3 có thể giúp tách dữ liệu quan trọng khỏi EC2 đơn lẻ, nhưng vẫn phải thiết kế phục hồi.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Block storage khác object storage ở đâu?  
**Đáp án:** Block cung cấp khối/thiết bị để OS hoặc ứng dụng xử lý I/O, còn object truy cập bằng bucket/key và API, không mặc định có POSIX filesystem semantics.

**Câu 2.** Một EBS volume có thể attach như shared drive cho EC2 ở hai AZ khác nhau không?  
**Đáp án:** Không. EBS volume thuộc một AZ; Multi-Attach có những điều kiện riêng trong cùng AZ và yêu cầu quản lý đồng bộ ở lớp cao hơn.

**Câu 3.** Hai EC2 Linux ở hai AZ muốn đọc/ghi chung thư mục nên đánh giá dịch vụ nào?  
**Đáp án:** Amazon EFS Regional với mount targets, NFS và quyền phù hợp.

**Câu 4.** Ứng dụng Windows cần SMB và AD nên xem dịch vụ nào?  
**Đáp án:** Amazon FSx for Windows File Server.

**Câu 5.** S3 key **photos/2026/a.jpg** có tạo directory POSIX tương tự Linux không?  
**Đáp án:** Không. Đó là object key; dấu / dùng làm prefix/nhóm tên trong object namespace.

**Câu 6.** Vì sao không thể kết luận mọi S3 storage class đều đa AZ?  
**Đáp án:** Một số storage class được thiết kế cho một AZ, nên availability/durability/recovery cần xem theo class.

**Câu 7.** EFS mount timeout và EFS permission denied có cùng nguyên nhân không?  
**Đáp án:** Không nhất thiết. Timeout thường liên quan DNS/network/SG/NFS; permission denied thường liên quan POSIX/IAM/resource policy hoặc mount options.

**Câu 8.** Object SSE-KMS trả S3 GetObject 403 dù user có quyền GetObject, cần kiểm tra gì?  
**Đáp án:** KMS key policy và quyền sử dụng key như kms:Decrypt, cùng các policy/điều kiện liên quan.

**Câu 9.** Có snapshot EBS một lần/ngày chứng minh RPO 10 phút không?  
**Đáp án:** Không. Cần chiến lược sao lưu/replication phù hợp và thử khôi phục để chứng minh mục tiêu.

**Câu 10.** Vì sao ứng dụng có thể đồng thời dùng EBS, EFS và S3?  
**Đáp án:** EBS phục vụ boot/block data theo instance, EFS chia sẻ filesystem giữa workload, còn S3 lưu object cho API/backup/lưu trữ lâu dài.

## 17. Ghi nhớ

Chọn storage theo **cách ứng dụng thao tác dữ liệu** trước, rồi mới tối ưu dung lượng và giá:

- **EBS / block:** ổ đĩa cho EC2 và workload cần block I/O; quản lý filesystem ở OS, quan tâm AZ, IOPS/throughput và snapshot.
- **EFS/FSx / file:** filesystem có đường dẫn và quyền file; chọn EFS cho NFS Linux phổ biến, FSx cho giao thức/tính năng chuyên biệt; quan tâm mạng mount, metadata performance, quyền POSIX/Windows và deployment HA.
- **S3 / object:** bucket/key/API; phù hợp ảnh, tài liệu, log, backup, data lake, lifecycle; quan tâm storage class, requests, IAM/bucket policy, versioning và retrieval.

Trước khi quyết định, hãy kiểm tra **giao diện truy cập**, **số client/AZ**, **hiệu năng IOPS/throughput/latency**, **mục tiêu RPO/RTO**, **phân quyền/mã hóa** và **tổng chi phí vòng đời**. Đây là nền tảng để chọn dịch vụ AWS phù hợp, giảm rủi ro dữ liệu và vận hành một hệ thống có khả năng phục hồi.

### Tài liệu AWS tham khảo

- [Amazon EBS User Guide](https://docs.aws.amazon.com/ebs/latest/userguide/what-is-ebs.html) — EBS volume và snapshot.
- [Amazon EBS volume types](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html) — cân nhắc hiệu năng theo loại volume.
- [Amazon EBS Multi-Attach](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volumes-multi.html) — điều kiện và giới hạn dùng chung block volume.
- [Amazon EFS User Guide](https://docs.aws.amazon.com/efs/latest/ug/whatisefs.html) — NFS, mount targets, storage classes và quyền truy cập.
- [Amazon FSx documentation](https://docs.aws.amazon.com/fsx/) — các filesystem Windows, Lustre, ONTAP, OpenZFS.
- [Amazon S3 User Guide](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html) — object storage và bucket.
- [Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html) — chọn class theo access pattern.
- [AWS Backup documentation](https://docs.aws.amazon.com/aws-backup/latest/devguide/whatisbackup.html) — các phương án backup theo tài nguyên.

