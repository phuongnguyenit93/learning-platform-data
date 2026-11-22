# Lựa chọn block storage, file storage và object storage trên GCP

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **block storage**, **file storage** và **object storage** theo giao diện truy cập, đơn vị dữ liệu, khả năng chia sẻ, độ trễ, tính nhất quán và cách tính phí.
2. Lựa chọn giữa **Google Cloud Hyperdisk**, **Persistent Disk**, **Local SSD**, **Filestore**, **Google Cloud Managed Lustre**, **Google Cloud NetApp Volumes** và **Cloud Storage** cho các workload cụ thể.
3. Hiểu vì sao **Cloud Storage FUSE** không biến object storage thành một file system POSIX/NFS thông thường, và vì sao không nên đặt database cần ghi ngẫu nhiên trên object mount.
4. Thiết kế theo **IOPS, throughput, latency, RPO/RTO, vùng lưu trữ, khả năng truy cập đồng thời, IAM, VPC** và yêu cầu quản lý dữ liệu.
5. Thực hành tạo/kiểm tra đĩa Compute Engine, mount file share Filestore, tạo bucket và thao tác object bằng **gcloud** một cách an toàn.
6. Nhận biết những chi phí dễ bỏ sót, chọn công cụ sao lưu và xây dựng checklist kiểm thử, vận hành cho VM, GKE, Cloud Run, dịch vụ cơ sở dữ liệu và ứng dụng Java.

## 1. Vì sao cùng là “lưu trữ” nhưng không dùng thay nhau được?

Một hệ thống thương mại điện tử trên Google Cloud thường có nhiều loại dữ liệu:

- **Boot volume và database files** của một VM chạy PostgreSQL hoặc Java application.
- **Thư mục chia sẻ** được nhiều VM hay pod đọc/ghi khi xử lý tài liệu.
- **Ảnh sản phẩm, video, tài liệu PDF, backup và logs** được truy cập theo tên object.
- **Dữ liệu tạm** để thực hiện sort, shuffle, cache hoặc dựng model AI.

Chọn cùng một dịch vụ cho mọi nhu cầu có thể gây lỗi về **API**, **locking**, **độ trễ**, **khả năng mở rộng**, **tính bền vững**, **khả năng chia sẻ** hoặc **chi phí**.

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học triển khai project/IAM/VPC, Compute Engine, GKE, Cloud Run, lưu trữ và database, đồng thời phát hành tự động, bảo vệ tài nguyên và theo dõi độ tin cậy lẫn chi phí. Quyết định lưu trữ vì thế phải bắt đầu từ **hành vi ứng dụng**, không chỉ từ bảng giá theo GiB.

### Ba câu hỏi mở đầu

1. Ứng dụng cần một **thiết bị khối** để tự định dạng file system và đọc/ghi theo địa chỉ block?
2. Nhiều máy/pod có cần một **cây thư mục chung** với thao tác file, directory, rename, file lock và quyền file?
3. Dữ liệu được quản lý như **các object hoàn chỉnh** qua API HTTP, với metadata, phiên bản, lifecycle và phân phối quy mô lớn?

Nếu câu trả lời lần lượt là **có**, hướng ban đầu thường là **block**, **file** hoặc **object storage**. Có trường hợp nên phối hợp cả ba loại.

## 2. Block, file, object: khác nhau ở lớp trừu tượng nào?

### 2.1. Block storage

Block storage đưa cho VM hoặc node một **thiết bị lưu trữ có thể đọc/ghi theo block**. Guest OS quyết định định dạng **ext4, XFS, NTFS**, tạo filesystem, mount path và xử lý locking. Nhà cung cấp lưu trữ không tự biết một block thuộc file “orders.db” hay “index.bin”.

~~~text
Java app hoặc PostgreSQL
  ↓ system calls
Guest OS: ext4/XFS/NTFS + buffer cache
  ↓ đọc/ghi block
/dev/disk/by-id/google-data-disk
  ↓
Persistent Disk hoặc Hyperdisk
~~~

**Phù hợp:** boot disk, dữ liệu ứng dụng local của VM, transaction database tự quản, index engine, workload đòi hỏi random I/O và block-level semantics.

### 2.2. File storage

File storage cung cấp **file share** qua giao thức mạng như **NFS** hoặc **SMB**. Hệ thống lưu trữ quản lý cấu trúc thư mục, file và metadata; nhiều clients có thể cùng mount một export.

~~~text
VM A: /mnt/shared/reports/2026.csv ─┐
                                    ├── NFS / SMB server
VM B: /mnt/shared/reports/2026.csv ─┘       ↓
                                      Filestore / NetApp
~~~

**Phù hợp:** shared workspace, nội dung cần dùng chung trong nhiều VM/pod, phần mềm legacy đòi hỏi đường dẫn filesystem, workloads sử dụng file locking và metadata POSIX.

### 2.3. Object storage

Object storage quản lý dữ liệu theo **bucket → object name → bytes + metadata**. API thao tác trên object: upload, read, list, delete, copy, thay metadata, tạo thế hệ mới. **Object name** có thể chứa dấu **/** để biểu diễn prefix, nhưng object API không mặc nhiên có tất cả ngữ nghĩa directory/file descriptor của một file system.

~~~text
Java app
  ↓ Cloud Storage client library / HTTPS API
gs://shop-product-media/images/sku-1001.jpg
  = bucket + object name
  + content type, generation, custom metadata, ...
~~~

**Phù hợp:** ảnh/video, document, dữ liệu phân tích, artifacts, backup, archives, static assets và dữ liệu cần truy cập từ nhiều dịch vụ qua API.

### 2.4. Bảng so sánh cốt lõi

| Tiêu chí | Block storage | File storage | Object storage |
|---|---|---|---|
| Đơn vị truy cập | Block/device | File, directory | Object và metadata |
| Giao diện ứng dụng | Block device + file system của OS | NFS/SMB hoặc giao thức file | HTTP API, SDK, CLI |
| Tên tài nguyên | Disk/volume + device path | Server IP và export path | Bucket và object name |
| Ví dụ GCP | Hyperdisk, Persistent Disk | Filestore, Managed Lustre, NetApp Volumes | Cloud Storage |
| Ghi thay đổi nhỏ | **Tốt**, theo block | **Tốt**, theo file system semantics | Thường phải ghi một object/generation mới |
| Nhiều client đọc/ghi | Phụ thuộc disk access mode và clustered FS | Mục đích thiết kế file share | Nhiều client qua API; cần kiểm soát cập nhật đồng thời |
| POSIX filesystem | Do OS tạo và quản lý | Có theo sản phẩm/protocol | **Không mặc nhiên**; FUSE không hoàn toàn POSIX |
| Phạm vi mạng | Disk gắn VM/node, có giới hạn zone/region | VPC, IP, NFS/SMB ports | Google Cloud APIs, IAM, endpoint/network policy |
| Khả năng mở rộng | Disk size/performance + giới hạn VM | Tier, share capacity, client throughput | Dung lượng object mở rộng theo mô hình dịch vụ |
| Độ trễ truy cập | Thường thích hợp I/O ngẫu nhiên thấp trễ | Phụ thuộc NFS/network/tier | API và network; không thay block latency |
| Khả năng chịu lỗi | Zonal hoặc regional replication tùy sản phẩm | Zonal/regional/service tier tùy loại | Chọn location regional/dual-region/multi-region và cấu hình bảo vệ |
| Kiểu chi phí | Provisioned GiB, IOPS, throughput, snapshots | Provisioned share capacity, performance, backups, network | Stored bytes, operations, retrieval, egress, retention |

**Không có loại nào “luôn nhanh hơn”**: một request đọc object 2 GiB qua nhiều luồng có thể đạt throughput tốt; điều đó không khiến nó thích hợp để ghi từng trang 4 KiB của một database.

## 3. Block storage trên Google Cloud: Persistent Disk, Hyperdisk và Local SSD

### 3.1. Persistent Disk: block storage bền vững gắn VM

**Persistent Disk** là block storage qua mạng của Compute Engine, tồn tại độc lập với host vật lý của VM. Disk có thể được giữ lại khi VM bị xóa nếu **auto-delete**/deletion rule được cấu hình phù hợp; có thể detach rồi attach sang VM khác trong phạm vi và mode hỗ trợ.

Các loại phổ biến:

| Disk type | Mã API/CLI | Phù hợp | Ghi chú |
|---|---|---|---|
| Standard Persistent Disk | **pd-standard** | I/O tuần tự, dữ liệu khối lượng lớn và nhạy chi phí | HDD, random IOPS thấp hơn SSD |
| Balanced Persistent Disk | **pd-balanced** | Boot/data disk đa dụng | SSD, cân bằng hiệu năng và giá |
| SSD Persistent Disk | **pd-ssd** | Database, transactional random I/O | SSD, thông lượng/IOPS tốt hơn tùy kích thước và VM |
| Extreme Persistent Disk | **pd-extreme** | Cơ sở dữ liệu yêu cầu IOPS cao | Chỉ trên machine types hỗ trợ, cấu hình IOPS riêng |

**Bẫy phổ biến:** khi tạo disk không chỉ định type, default của **Google Cloud Console** có thể là **pd-balanced**, còn **gcloud/API** có thể mặc định **pd-standard**. Luôn khai báo **--type** rõ ràng và kiểm tra kết quả.

**Hiệu năng Persistent Disk** thường tăng theo dung lượng provisioned và chịu giới hạn từ **machine series, số vCPU, network egress, số disk đang gắn, I/O size**. Một đĩa pd-ssd nhỏ trên máy rất yếu không tự đạt hiệu năng của đĩa lớn trên máy đủ vCPU.

### 3.2. Hyperdisk: block storage tách dung lượng và hiệu năng

**Hyperdisk** cung cấp khả năng cấu hình **capacity** tương đối độc lập với **provisioned performance** trong giới hạn sản phẩm, giúp tăng/giảm IOPS hoặc throughput mà không nhất thiết phải phóng to disk.

| Loại Hyperdisk | Mã tham chiếu | Phù hợp |
|---|---|---|
| **Hyperdisk Balanced** | **hyperdisk-balanced** | Hầu hết VM, ứng dụng doanh nghiệp, boot/data disk, một số database |
| **Hyperdisk Balanced High Availability** | **hyperdisk-balanced-high-availability** | Block storage đồng bộ giữa hai zone trong region cho workload cần HA |
| **Hyperdisk Extreme** | **hyperdisk-extreme** | Database cực nhiều IOPS, cấu hình cao |
| **Hyperdisk Throughput** | **hyperdisk-throughput** | Đọc/ghi tuần tự, Hadoop, Spark, analytics, cold data disk |
| **Hyperdisk ML** | **hyperdisk-ml** | Model/data đọc đồng thời rất lớn từ nhiều accelerator clients |

**Không phải dòng VM nào cũng hỗ trợ mọi Hyperdisk type**, và giới hạn disk size, số volume, throughput, IOPS cũng khác nhau. Vì vậy bước chọn disk phải đi cùng **machine type, zone và nhu cầu I/O thực tế**.

Ví dụ workload cần **20.000 IOPS nhưng chỉ chứa 100 GiB dữ liệu**: có thể cân nhắc **Hyperdisk Balanced** nếu machine series hỗ trợ, thay vì tăng dung lượng Persistent Disk lớn chỉ để lấy thêm IOPS. So sánh **tổng chi phí capacity + performance** và đo benchmark mới quyết định.

#### Multi-writer không đồng nghĩa file share

Một số Hyperdisk hỗ trợ **READ_WRITE_MANY** hoặc **READ_ONLY_MANY** theo loại disk và điều kiện. Điều này chỉ cho phép **gắn một block device vào nhiều VM** ở mode được hỗ trợ:

- Nếu hai VM cùng mount **ext4/XFS truyền thống** và cùng ghi mà không có clustered filesystem/coordination, dữ liệu **có thể bị hỏng**.
- Multi-writer block cần **cluster-aware filesystem/application fencing**, hoặc dùng như database cluster đã được chứng nhận.
- Nếu mục tiêu chỉ là **nhiều VM có thư mục dùng chung**, **Filestore/NFS** thường phù hợp và an toàn hơn là tự dựng shared block.

### 3.3. Local SSD: block storage tạm thời, không thay disk bền vững

**Local SSD** gắn với host vật lý, có độ trễ thấp và IOPS/throughput cao cho nhiều workload. Đổi lại, dữ liệu có thể mất khi host/VM bị dừng hoặc gặp sự kiện không thể phục hồi. Không dùng Local SSD là bản sao duy nhất của dữ liệu quan trọng.

Phù hợp với:

- **Cache, temporary sort/shuffle, scratch space**, intermediate files.
- Dữ liệu có thể **tái tạo** từ Cloud Storage, database hoặc source of truth khác.
- Job HPC/ML cần I/O nhanh trong phạm vi vòng đời worker.

Không phù hợp với **backup duy nhất**, database đơn lẻ không có replication/checkpoint hoặc dữ liệu cần tồn tại khi VM bị xóa.

### 3.4. Zonal, regional disk và khả năng phục hồi

**Zonal Persistent Disk/Hyperdisk** có dữ liệu trong phạm vi zone theo loại sản phẩm. **Regional Persistent Disk** và **Hyperdisk Balanced High Availability** là các lựa chọn có đồng bộ dữ liệu giữa hai zone trong cùng region theo cơ chế sản phẩm.

**Regional replication không đồng nghĩa backup**:

- Hai bản sao giúp giảm rủi ro **mất cả zone**, nhưng xóa nhầm file, mã hóa bởi ransomware hoặc ghi dữ liệu sai có thể được nhân bản.
- **Disk snapshot/backup** giải quyết bài toán khôi phục sau lỗi logic nếu chính sách và retention được thiết kế phù hợp.
- **SLO/RTO/RPO** còn phụ thuộc khả năng attach/failover VM, database consistency, DNS/IP, runbook và kiểm thử.

## 4. File storage: khi nhiều compute clients cần một cây thư mục chung

### 4.1. Filestore: NFS được quản lý

**Filestore** là dịch vụ network-attached storage (NAS) được quản lý, cho phép VM và workload GKE phù hợp mount **NFS file share**. Phần lớn ứng dụng xem share như một thư mục và dùng các thao tác đọc/ghi file thông thường.

Các lựa chọn hiện hành:

| Filestore tier | Phạm vi độ sẵn sàng | Workload điển hình | Tính năng/giới hạn cần lưu ý |
|---|---|---|---|
| **Zonal** | Theo zone | HPC cục bộ, shared files hiệu năng cao | Dữ liệu chịu rủi ro zonal; có backup/snapshot/replication theo điều kiện |
| **Regional** | Chịu lỗi zone trong region theo thiết kế | Dịch vụ nhiều zone, enterprise app cần HA | Chi phí và giới hạn capacity/performance tùy tier |
| **Multishares for GKE (Enterprise)** | Theo cơ chế regional của sản phẩm | Nhiều PVC/namespace của GKE cần file shares | Tính năng và provisioner đặc thù GKE |
| **Legacy Basic HDD/SSD** | Zonal | Ứng dụng cũ, cần tương thích | NFSv3, capacity/performance khác tier mới |

**Giao thức:** Filestore **zonal/regional** hỗ trợ **NFSv3 và NFSv4.1** theo điều kiện tier, còn các tier legacy có thể chỉ NFSv3. Không mặc định mọi instance hỗ trợ SMB hoặc mọi NFS version.

Filestore là **một server file share có địa chỉ IP trong VPC**, nên cần route/peering/network connectivity phù hợp, firewall và cấu hình NFS client. **Không có public HTTPS object URL** như Cloud Storage.

### 4.2. Filestore khác block multi-writer ra sao?

NFS server của Filestore quản lý namespace file và semantics của NFS. Clients có thể cùng mount một export với các quy tắc permission và locking phù hợp. Không cần hai VM cùng ghi thẳng raw blocks như một disk shared multi-writer.

**Tuy nhiên NFS vẫn có vấn đề concurrency:** hai ứng dụng đồng thời ghi vào **cùng một file** phải thiết kế locking, thứ tự ghi, atomic rename và flush/fsync theo ngữ nghĩa NFS phiên bản đang dùng. Shared filesystem không tự đồng bộ logic kinh doanh.

### 4.3. Google Cloud Managed Lustre: parallel file system chuyên dụng

**Managed Lustre** là managed **parallel filesystem** hướng đến **AI training, HPC, media và phân tích dữ liệu quy mô rất lớn**, cần throughput cao trên nhiều clients. Nó có POSIX interface và tích hợp với Compute Engine/GKE, hỗ trợ di chuyển dữ liệu sang/từ Cloud Storage theo tính năng sản phẩm.

Chỉ nên chọn khi workload thực sự cần **parallel I/O** và đã có phương án quản lý data staging, POSIX metadata, giá thành, số client và tương thích hệ sinh thái Lustre. Nó không phải mặc định thay Filestore cho ứng dụng web nhỏ.

### 4.4. Google Cloud NetApp Volumes: NFS/SMB cho enterprise và hybrid

**Google Cloud NetApp Volumes** hỗ trợ file-based enterprise workload với **NFSv3/v4.1/v4.2** và **SMB**, đồng thời có các tùy chọn block protocols như **iSCSI/NVMe/TCP** trong những tính năng được hỗ trợ. Phù hợp khi tổ chức di chuyển ứng dụng hiện có từ NAS on-prem, cần SMB cho Windows hoặc các khả năng data management của NetApp.

Khác biệt trọng yếu:

- **Filestore:** thường là lựa chọn NFS managed trực tiếp trên Google Cloud cho VM/GKE.
- **NetApp Volumes:** xem xét khi cần **SMB**, enterprise NAS features, hybrid migration hay service-level của NetApp.
- **Managed Lustre:** tối ưu **parallel POSIX filesystem** ở quy mô HPC/AI.

Chọn theo **protocol, tier, vùng khả dụng, hiệu năng, giấy phép/giá, khả năng khôi phục và cách quản trị**; không chỉ nhìn tên dịch vụ.

## 5. Object storage: Cloud Storage, buckets và object generations

### 5.1. Cloud Storage là dịch vụ gì?

**Cloud Storage** lưu object trong các **buckets**. Client có thể đọc/ghi qua **Cloud Storage JSON/XML APIs**, SDKs, Google Cloud CLI hoặc giao diện Console. Object có tên, metadata, content type, generation/metageneration và những thuộc tính kiểm soát vòng đời.

Một đường dẫn minh họa:

~~~text
gs://shop-product-media/images/2026/sku-1001.jpg
  bucket: shop-product-media
  object: images/2026/sku-1001.jpg
~~~

Dấu **/** thường là thành phần của tên object để tổ chức theo prefix, không mặc nhiên tạo một POSIX directory. Cloud Storage hiện còn có **hierarchical namespace** cho những bucket được cấu hình phù hợp; dù vậy **object API vẫn khác block/NFS filesystem**.

### 5.2. Các storage classes và pattern truy cập

| Lớp lưu trữ | Tần suất truy cập gợi ý | Minimum storage duration / chi phí retrieval |
|---|---|---|
| **Standard** | Dữ liệu nóng, ảnh web, video đang phục vụ, artifacts dùng thường xuyên | Không có minimum duration; cần tính operations/egress |
| **Nearline** | Dữ liệu ít truy cập, ví dụ khoảng hàng tháng | Minimum 30 ngày; có retrieval charges |
| **Coldline** | Dữ liệu rất ít truy cập, ví dụ khoảng mỗi quý | Minimum 90 ngày; có retrieval charges |
| **Archive** | Lưu giữ dài hạn, khôi phục hiếm | Minimum 365 ngày; có retrieval charges |
| **Rapid** | Trường hợp low-latency theo kiến trúc **Rapid Bucket** phù hợp | Chỉ áp dụng trong mô hình và điều kiện Rapid Bucket được hỗ trợ |

**Không kết luận Archive cần chờ nhiều giờ để được đọc:** Cloud Storage Archive vẫn có truy cập online theo API; vấn đề cần cân nhắc là **giá retrieval, storage duration và đặc tính sản phẩm**.

Tùy yêu cầu, có thể dùng:

- **Object Lifecycle Management:** chuyển lớp, xóa object theo tuổi hoặc quy tắc.
- **Autoclass:** tự quản lý storage class theo chính sách của bucket khi phù hợp.
- **Object Versioning / soft delete:** hỗ trợ khôi phục thao tác xóa/ghi đè, với chi phí retention bổ sung.
- **Retention policy, bucket lock, object holds:** phục vụ yêu cầu giữ dữ liệu hoặc compliance.
- **Signed URLs:** cấp quyền truy cập giới hạn thời gian cho người dùng ngoài hệ thống khi use case phù hợp.

### 5.3. Tính nhất quán Cloud Storage

Cloud Storage cung cấp **strong global consistency** cho các thao tác object create/read/list/delete và metadata theo tài liệu; object mới có thể đọc ngay sau khi upload thành công. Đây **không** phải lý do để coi Cloud Storage là filesystem POSIX:

- **Strong read-after-write** cho object không đồng nghĩa có **in-place block writes**, **POSIX locks** hoặc **atomic multi-file transaction**.
- Nhiều client ghi cùng một object name có thể ghi đè theo thứ tự thực thi. Dùng **generation preconditions** để tránh lost update.
- **Public caching qua CDN/browser** có thể khiến người dùng thấy phiên bản cũ cho đến khi TTL/cache policy cho phép refresh, dù object ở origin nhất quán mạnh.

Ví dụ dùng precondition **ifGenerationMatch=0** khi tạo object lần đầu để đảm bảo không ghi đè object đã tồn tại.

### 5.4. Object storage không phải chỉ dùng làm backup

Các use cases phổ biến:

- **Static assets** dùng qua backend bucket/Cloud CDN.
- **Data lake** với BigQuery, Dataflow, Dataproc, AI pipelines.
- **Backup và snapshot exports** theo công cụ hỗ trợ.
- **Event-driven processing** khi object mới xuất hiện, với cơ chế Pub/Sub/Eventarc phù hợp.
- **Artifact distribution** giữa project và hệ thống CI/CD.
- **Bảo quản tài liệu** theo retention/compliance.

Nếu workload cần lưu nhiều file lớn, đọc tuần tự, dùng qua SDK và phân phối toàn cầu, Cloud Storage thường là lựa chọn linh hoạt. Nếu workload cần sửa từng 4 KiB block hoặc lock file liên tục, không nên ép object storage làm việc của block/NFS.

## 6. Cloud Storage FUSE: “mount bucket” có phải file storage không?

**Cloud Storage FUSE** cho phép gắn bucket như một thư mục trên Linux (hoặc môi trường được hỗ trợ), để ứng dụng dùng lệnh đọc/ghi theo đường dẫn. Phía dưới, FUSE vẫn gọi **Cloud Storage object API**.

~~~text
Ứng dụng đọc /mnt/models/model.bin
   ↓ POSIX-like interface qua FUSE
Cloud Storage FUSE
   ↓ GET/PUT/list object
gs://ml-models/model.bin
~~~

**Hạn chế bắt buộc phải hiểu:**

- **Không hoàn toàn POSIX compliant**, không phải NFS/CIFS backend.
- Không hỗ trợ đầy đủ các filesystem metadata và file locking/patching semantics.
- Ghi sửa giữa file thường dẫn đến **re-upload object** thay vì block write; không phù hợp database, git repository có nhiều metadata operations hoặc filesystem workload chỉnh sửa liên tục.
- Latency của object API cao hơn disk/NFS cho nhiều random I/O nhỏ.
- Quyền truy cập kiểm soát bằng **Cloud Storage IAM**, không thay thế bằng chmod/chown POSIX thông thường.
- **Object Versioning** và một số operations có giới hạn tương thích với FUSE; cần kiểm tra tài liệu trước khi kết hợp.

**Trường hợp phù hợp:** đọc model/dataset lớn qua đường dẫn file, staged ML workloads hoặc migration tạm thời nơi ứng dụng cần file interface nhưng hành vi I/O thực chất thích hợp với object storage.

**Nguyên tắc:** Giao diện “trông như thư mục” không làm thay đổi semantics và mô hình chi phí của object storage.

## 7. Sơ đồ quyết định chọn dịch vụ

~~~mermaid
flowchart TD
    Q["Workload cần lưu gì?"] --> D{"Cần block device hoặc<br/>random in-place I/O?"}
    D -->|Có| B{"Dữ liệu có thể mất/tạo lại?"}
    B -->|Có| L["Local SSD<br/>cache/scratch"]
    B -->|Không| H{"VM hỗ trợ Hyperdisk?"}
    H -->|Có| HD["Hyperdisk phù hợp<br/>Balanced/Extreme/Throughput/ML/HA"]
    H -->|Không| PD["Persistent Disk<br/>balanced/SSD/standard/..."]
    D -->|Không| F{"Cần POSIX/NFS/SMB<br/>và shared file namespace?"}
    F -->|Có| FF{"Loại file workload?"}
    FF -->|NFS thông dụng| FS["Filestore<br/>zonal/regional"]
    FF -->|SMB/enterprise NAS| NET["NetApp Volumes"]
    FF -->|HPC/AI parallel I/O| LU["Managed Lustre"]
    F -->|Không| OBJ["Cloud Storage<br/>bucket + object APIs"]
    OBJ --> C["Chọn location/class,<br/>IAM, retention, lifecycle"]
~~~

### 7.1. Năm bước có thể áp dụng cho mọi dự án

1. **Hiểu I/O:** object nguyên khối hay đọc/ghi random block? File locking/rename có bắt buộc không? Kích thước request và mức song song?
2. **Hiểu chia sẻ:** một VM, nhiều VM, nhiều pod, đọc-only, ghi đồng thời hay nhiều dịch vụ gọi qua HTTP?
3. **Hiểu dữ liệu:** có cần giữ qua VM restart, failover zone, lỗi application, xóa nhầm hoặc ransomware?
4. **Hiểu bảo mật/kết nối:** cần VPC private/NFS port, IAM cho bucket, CMEK, service account, chính sách retention?
5. **Đo hiệu năng và tính giá:** đo IOPS/throughput/latency thực, kiểm tra machine/zone limits, tổng chi phí provisioned capacity, network, snapshots, operations và retrieval.

### 7.2. Ma trận workload điển hình

| Workload | Chọn ban đầu | Vì sao | Không nên nhầm |
|---|---|---|---|
| Boot disk VM Linux | Persistent Disk hoặc Hyperdisk được hỗ trợ | Guest OS cần block device | Không thể boot Compute Engine trực tiếp từ Cloud Storage object |
| PostgreSQL/MySQL tự quản trên VM | Hyperdisk Balanced/Extreme hoặc pd-ssd phù hợp | Random IOPS, fsync, file system thật | Không dùng Cloud Storage FUSE làm database data directory |
| Shared folder của nhiều VM | Filestore NFS | Namespace chung, file-level operations | Multi-writer disk không tự có file locking |
| Ứng dụng Windows cũ cần SMB | NetApp Volumes hoặc managed SMB phù hợp | Protocol SMB và ACL theo workload | Filestore NFS không tự thành SMB |
| AI/HPC training song song lớn | Managed Lustre hoặc hệ chuyên dụng phù hợp | Parallel POSIX I/O | Filestore nhỏ không mặc nhiên đạt throughput HPC |
| Cache tạm trên GPU VM | Local SSD | Nhanh, dữ liệu có thể tái tạo | Không đặt checkpoint duy nhất trên Local SSD |
| Ảnh sản phẩm và media | Cloud Storage Standard + CDN theo nhu cầu | Object API, scale, metadata, caching | Không dùng Persistent Disk một VM làm shared media server |
| Backup lâu dài | Cloud Storage theo class/retention, backup product phù hợp | Data protection và lifecycle | Object storage không tự tạo backup nhất quán cho database đang ghi |
| Nhiều GKE pods cùng cần đọc/ghi files | Filestore CSI hoặc NetApp/Lustre theo workload | File share có ReadWriteMany phù hợp | RWO block PVC không có nghĩa RWX |
| Data lake phân tích | Cloud Storage | Dữ liệu theo object, analytics ecosystem | Không cần NFS cho phần lớn batch object processing |

## 8. Hiệu năng: đọc IOPS, throughput, latency đúng cách

### 8.1. IOPS

**IOPS (I/O operations per second)** đo số thao tác đọc/ghi mỗi giây. Database OLTP xử lý nhiều pages nhỏ thường **nhạy IOPS và latency**.

Ví dụ chỉ để hình dung:

~~~text
10.000 IOPS × 4 KiB / operation
≈ 39 MiB/s dữ liệu, nhưng có 10.000 requests/giây.
~~~

Không thể chọn disk chỉ nhìn MiB/s; 10.000 yêu cầu 4 KiB thường có hành vi rất khác vài yêu cầu kích thước hàng MiB.

### 8.2. Throughput

**Throughput** là lượng dữ liệu qua hệ thống mỗi giây (MiB/s, GiB/s). Video processing, ETL, Hadoop và sequential backup thường nhạy throughput hơn IOPS.

### 8.3. Latency

**Latency** là thời gian một thao tác mất để hoàn thành; nên đo **p50/p95/p99**, không chỉ trung bình. Với API đồng bộ, một storage call chậm có thể khiến người dùng cảm nhận ngay.

| Loại | Giới hạn hiệu năng cần kiểm tra |
|---|---|
| **Persistent Disk** | Volume size, disk type, số vCPU, giới hạn máy, aggregate I/O, network egress |
| **Hyperdisk** | Provisioned IOPS/throughput, disk type, machine caps và số volume |
| **Local SSD** | Machine configuration, parallel I/O, lifecycle |
| **Filestore** | Tier, purchased/provisioned capacity và performance, NFS clients, nconnect, network |
| **Managed Lustre** | Số clients, striping, data distribution, metadata performance, network |
| **Cloud Storage** | Request size, client concurrency, object naming, API throughput, retries, location và network |

### 8.4. Hiệu năng thực tế thường là “min của nhiều trần”

Với Persistent Disk và Hyperdisk, throughput thực có thể bị giới hạn bởi **disk cap hoặc instance cap**. Provision **100.000 IOPS** trên disk không có nghĩa VM nhỏ cũng thực thi được 100.000 IOPS. Phải chọn **cả disk lẫn máy** phù hợp.

Với Filestore, NFS client CPU, network, mount options và number of connections có thể là nút thắt. Với Cloud Storage, nhiều object nhỏ/single-threaded requests và round-trip latency có thể chi phối. **Benchmark với pattern ứng dụng thực** thay vì dùng một con số marketing làm bảo đảm SLO.

## 9. Chia sẻ và tính nhất quán: khác biệt có thể gây hỏng dữ liệu

### 9.1. Một disk không mặc nhiên là file share

Block volume thường được gắn đọc/ghi cho một VM hoặc một node theo access mode. Các **multi-writer Hyperdisk** yêu cầu clustered FS/app logic; **ReadWriteMany** ở Kubernetes là yêu cầu về volume access semantics, không phải một tùy chọn tự động bật trên mọi PD/Hyperdisk.

### 9.2. NFS có namespace chung nhưng không thay transaction database

Nhiều clients của Filestore nhìn thấy cùng thư mục. Tuy vậy:

- File locks và cache coherence phụ thuộc NFS version và application protocol.
- Hai writers cần phối hợp khi chỉnh cùng file.
- Một NFS server regional có HA tốt hơn một share zonal theo tính năng, nhưng cần network/clients đủ sẵn sàng.

Không nên chuyển database tự quản từ block sang NFS chỉ để nhiều VM cùng mount một data directory: database có thể không hỗ trợ kiểu multi-host writer đó.

### 9.3. Object strong consistency không có nghĩa transaction liên object

Cloud Storage object sau khi tạo thành công được đọc/list nhất quán mạnh. Nhưng một quy trình tạo **orders/100.json** rồi tạo **orders/index.json** là **hai thao tác riêng**, không có atomic transaction bao trùm cả hai. Nếu cần tính toàn vẹn transactional, dùng database phù hợp và thiết kế event/manifest có idempotency.

**Generation preconditions** giúp giải quyết concurrent writers ở mức object; **object versioning** giúp theo dõi/khôi phục các phiên bản nhưng không đảm bảo logic cập nhật ứng dụng đúng.

## 10. Độ bền, HA, backup, replication và yêu cầu tuân thủ

### 10.1. Đừng nhầm durability, availability và recoverability

| Thuật ngữ | Câu hỏi | Ví dụ |
|---|---|---|
| **Durability** | Xác suất dữ liệu được giữ khi có lỗi hạ tầng? | Redundancy của disk hoặc object storage |
| **Availability** | Workload có thể truy cập dữ liệu khi một component/zone lỗi? | Regional Filestore/Regional PD, multi-zone design |
| **Recoverability** | Có thể phục hồi sau xóa nhầm, corruption, ransomware? | Snapshot, backup, versioning, retention |
| **RPO** | Cho phép mất tối đa bao nhiêu dữ liệu tính theo thời gian? | 0 phút, 15 phút, 24 giờ |
| **RTO** | Chấp nhận dịch vụ ngừng bao lâu khi khôi phục? | 5 phút, 1 giờ |

### 10.2. Block storage

**Snapshots** có thể sao lưu disk; với database đang ghi, phải quan tâm **application-consistent** (flush/quiesce hoặc backup-specific) so với crash-consistent. Snapshot disk của VM không nhất thiết chứa trạng thái RAM, mọi transaction logic của nhiều disk hoặc dữ liệu ngoài disk đó.

Disk **regional replicated** hỗ trợ tính sẵn sàng khi zone lỗi, nhưng vẫn cần **failover procedure** và backup độc lập.

### 10.3. File storage

Filestore có **backups/snapshots** theo tier và tính năng; việc restore có thể cần thời gian đáng kể theo dung lượng. Với NFS share nhiều writer, xác định yêu cầu nhất quán thời điểm snapshot, ứng dụng có cần quiesce hay không. **Regional Filestore** giúp giảm rủi ro zone outage nhưng không thay quy trình bảo vệ dữ liệu khỏi xóa nhầm.

### 10.4. Object storage

Chọn **bucket location** theo dữ liệu và yêu cầu: region, dual-region, multi-region hoặc các dạng chuyên dụng được sản phẩm hỗ trợ. Các lựa chọn có đánh đổi về độ trễ, data residency, availability và chi phí.

Thiết lập phù hợp:

- **Soft delete** và/hoặc **Object Versioning** để hỗ trợ phục hồi xóa/overwrite.
- **Lifecycle** để tự chuyển storage class hoặc xóa theo chính sách.
- **Retention policy/holds** khi cần tuân thủ pháp lý.
- **CMEK** khi có yêu cầu quản lý khóa bởi tổ chức, cùng khả năng khôi phục khóa.
- **Sao chép/định vị dữ liệu** theo sản phẩm và yêu cầu RPO/RTO; không tự giả định mọi lớp/region có cùng SLA.

**Đề phòng:** replication của data location không bảo vệ khỏi việc principal có quyền hợp lệ xóa object, trừ khi cơ chế retention, soft delete/versioning hoặc quyền khác bảo vệ.

## 11. Bảo mật và networking cho từng loại

| Chủ đề | Block | File | Object |
|---|---|---|---|
| **GCP IAM** | Quyền tạo, attach, snapshot, quản lý disk | Quyền tạo/quản trị instance/share; IAM không tự thay thế NFS file permission | Bucket/object IAM và signed URL nếu phù hợp |
| **Data-plane permissions** | OS user/group, filesystem permissions, encryption | NFS export options, UID/GID, file ACL/locking, network restrictions | Cloud Storage IAM, conditional access, object preconditions |
| **Đường mạng** | Block volume qua hạ tầng Compute Engine, guest thấy device | VPC peering/Shared VPC/route + NFS/SMB port | Google APIs, Private Google Access/PSC for Google APIs theo kiến trúc |
| **Mã hóa** | Default encryption at rest/in transit; CMEK tùy loại | Mã hóa managed service, CMEK/tính năng theo tier | Encryption at rest/in transit; CMEK nếu chọn |
| **Exposure phổ biến** | Attach nhầm disk hoặc quyền rộng | NFS share mở rộng UID/GID, firewall, route | Bucket IAM công khai, signed URL dài hạn, key lộ |
| **Theo dõi** | Compute audit, metrics disk, OS logs | Filestore audit/monitoring, NFS errors | Cloud Storage audit logs, request metrics, object access |

### 11.1. Least privilege thực tế

- Tách **service account của application** khỏi tài khoản quản trị storage.
- Với bucket private, dùng **Uniform bucket-level access** khi mô hình quyền phù hợp; hạn chế public access, xem xét **Public Access Prevention**.
- Đối với Filestore, cấu hình network export options và firewall theo clients được phép. **NFSv3 với AUTH_SYS/UID/GID không giống IAM trên từng file**; phải hiểu trust boundary của client.
- Với disk, quyền **compute.disks.use**/attachDisk cùng quyền trong guest quyết định ai có thể dùng dữ liệu; mã hóa bằng CMEK đòi hỏi chính sách IAM trên khóa và vận hành rotation/revocation phù hợp.
- Đừng gửi credentials trong image, script, repository; trên VM/GKE/Cloud Run sử dụng **service account/workload identity** thích hợp.

### 11.2. Data residency

Các loại storage có cách chọn **zone, region, dual-region hoặc multi-region** khác nhau. Nếu nghiệp vụ yêu cầu dữ liệu ở một quốc gia/khu vực cụ thể, quyết định phải đi theo **điều khoản dịch vụ, location thực và luồng replication/backup**. Không lấy bucket multi-region làm thay thế cho yêu cầu chỉ lưu ở một region.

## 12. Thực hành A: tạo và mount Persistent Disk trên Compute Engine

**Mục tiêu:** một VM Linux ở **asia-southeast1-b** cần disk 100 GiB kiểu **pd-balanced** để lưu data files. Các ID trong ví dụ là giả định; thao tác tạo có phát sinh chi phí.

| Biến | Giá trị minh họa |
|---|---|
| Project | shop-dev-001 |
| Zone | asia-southeast1-b |
| VM | app-vm-01 |
| Disk name | app-data |
| Disk size/type | 100 GiB / pd-balanced |

### 12.1. Kiểm tra trước khi tạo

~~~bash
gcloud compute instances describe app-vm-01 \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b

gcloud compute disks list --project=shop-dev-001 \
  --filter="zone:(asia-southeast1-b)"
~~~

Kiểm tra disk có bị trùng tên và đang gắn ở đâu. Không áp dụng lệnh format cho đĩa đã chứa dữ liệu.

### 12.2. Tạo disk

~~~bash
gcloud compute disks create app-data \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --type=pd-balanced \
  --size=100GB
~~~

### 12.3. Attach vào VM cùng zone

~~~bash
gcloud compute instances attach-disk app-vm-01 \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --disk=app-data \
  --device-name=app-data

gcloud compute disks describe app-data \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b
~~~

**Attach thành công chưa có nghĩa guest OS dùng được.** Disk mới có thể chưa được format hoặc mount.

### 12.4. Format và mount bên trong VM

**Cảnh báo mất dữ liệu:** lệnh **mkfs.ext4** sẽ ghi đè filesystem hiện có. **Chỉ dùng khi chắc chắn là disk mới, chưa chứa dữ liệu**, và thiết bị được nhận diện đúng.

~~~bash
# Chạy bên trong VM, không phải trên laptop
lsblk -f
ls -l /dev/disk/by-id/google-app-data

# Chỉ trên disk TRỐNG, xác nhận đúng device
sudo mkfs.ext4 -m 0 -F /dev/disk/by-id/google-app-data

sudo mkdir -p /mnt/app-data
sudo mount -o discard,defaults /dev/disk/by-id/google-app-data /mnt/app-data

df -h /mnt/app-data
~~~

Để mount tự động sau reboot, ưu tiên dùng **filesystem UUID** trong **/etc/fstab** sau khi đã kiểm tra UUID chính xác, mount options và hành vi khi disk chưa sẵn sàng; dùng **nofail** khi nghiệp vụ cho phép VM boot dù disk vắng. Không chèn fstab tự động nếu chưa có quy trình khôi phục vì sai cấu hình có thể khiến VM boot lỗi.

### 12.5. Bài học rút ra

Block disk cung cấp **device**; bạn phải tự quản lý **filesystem, permissions, mount, backup, resize filesystem và consistency khi có nhiều writer**. Đây là trách nhiệm khác với việc upload file lên Cloud Storage.

## 13. Thực hành B: file share Filestore cho hai VM

**Mục tiêu:** hai VM Linux trong cùng VPC cần dùng chung thư mục **/mnt/shared** để trao đổi tài liệu. Chọn **Filestore Regional** cho tình huống cần HA trong một region; xác nhận tier/quota/giá và supported region trước khi tạo.

Ví dụ:

| Biến | Giá trị minh họa |
|---|---|
| Project | shop-dev-001 |
| Region | asia-southeast1 |
| VPC | vpc-app |
| Filestore instance | fs-shared |
| NFS share | shared |
| Capacity | 1 TB |

### 13.1. Tạo Filestore instance

~~~bash
gcloud filestore instances create fs-shared \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --tier=REGIONAL \
  --file-share=name="shared",capacity=1TB \
  --network=name="vpc-app"
~~~

Lệnh có **chi phí provisioned capacity** ngay khi instance được tạo. Region/tier có thể có quota và chính sách tổ chức riêng. Phải kiểm tra Cloud Filestore API, quyền quản lý instance và reserved IP range trong VPC để tránh conflict.

### 13.2. Xem IP và share name

~~~bash
gcloud filestore instances describe fs-shared \
  --project=shop-dev-001 \
  --region=asia-southeast1
~~~

Đọc **networks[].ipAddresses**, **fileShares[].name**, tier và state. Ví dụ kết quả IP là **10.50.10.20**; thay bằng IP thật. VM phải có route/firewall tới địa chỉ IP Filestore.

### 13.3. Mount từ VM Linux

~~~bash
# Trên VM, ví dụ Debian/Ubuntu
sudo apt-get update
sudo apt-get install -y nfs-common

sudo mkdir -p /mnt/shared
sudo mount -t nfs -o vers=3 10.50.10.20:/shared /mnt/shared

df -h /mnt/shared
mount | grep /mnt/shared
~~~

Nếu cả hai VM cần share, chạy mount từ VM thứ hai (sau khi thiết lập route/firewall). Chọn **NFSv3/v4.1** dựa trên Filestore tier và kernel/client tương thích; đừng mặc định cả hai có quyền ghi như nhau nếu export/UID/GID/file permissions không cho phép.

**Sau reboot**, mount thủ công không tự được khôi phục. Cân nhắc **/etc/fstab, _netdev, automount/autofs** và kiểm tra behavior khi NFS server không sẵn sàng. Với GKE, ưu tiên dùng **Filestore CSI driver/PVC** thay vì tự SSH vào node sửa fstab.

### 13.4. Điều không nên làm

- Không thử **mkfs.ext4** trên địa chỉ NFS.
- Không xem Filestore IP là public DNS endpoint.
- Không để NFS share mở cho toàn bộ CIDR nếu chỉ vài clients cần quyền.
- Không trông đợi snapshot một NFS share đang có nhiều writers là application-consistent nếu không có phương án quiesce.

## 14. Thực hành C: Cloud Storage bucket cho ảnh sản phẩm

**Mục tiêu:** lưu ảnh **sku-1001.jpg** và truy cập bằng object path; bucket dùng **Standard** và quyền truy cập bucket thống nhất. Tên bucket phải duy nhất toàn cầu; ví dụ sau chỉ là placeholder.

### 14.1. Tạo bucket

~~~bash
gcloud storage buckets create gs://shop-media-REPLACE-UNIQUE \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access
~~~

Chỉ thay **REPLACE-UNIQUE** bằng tên đã được phê duyệt. Tạo bucket có thể có chi phí khi dùng lưu trữ, operations hoặc network. Kiểm tra **public access prevention**, IAM, lifecycle và policies cần thiết trong tổ chức.

### 14.2. Upload và đọc object

~~~bash
gcloud storage cp ./sku-1001.jpg \
  gs://shop-media-REPLACE-UNIQUE/images/sku-1001.jpg

gcloud storage ls \
  gs://shop-media-REPLACE-UNIQUE/images/

gcloud storage cp \
  gs://shop-media-REPLACE-UNIQUE/images/sku-1001.jpg \
  ./sku-1001-downloaded.jpg
~~~

**Không cần mount NFS hay format block**. Ứng dụng hoặc pipeline thao tác qua bucket/object APIs.

### 14.3. Ví dụ Java Cloud Storage client với ADC

Giả sử Java API có một service account được cấp quyền tạo object phù hợp ở bucket:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ProductPhotoStore {
    public static void uploadNew(String bucket, String objectName,
                                 Path localFile) throws Exception {
        Storage storage = StorageOptions.getDefaultInstance().getService();
        BlobId id = BlobId.of(bucket, objectName);
        BlobInfo blob = BlobInfo.newBuilder(id)
            .setContentType("image/jpeg")
            .build();
        byte[] bytes = Files.readAllBytes(localFile);
        storage.create(blob, bytes, Storage.BlobTargetOption.doesNotExist());
    }
}
~~~

Ví dụ dùng **Application Default Credentials**; không hardcode service account private key. **doesNotExist()** dùng generation precondition để giảm nguy cơ ghi đè khi object cùng tên đã tồn tại. Với file lớn trong production, ưu tiên **streaming/resumable upload** thay vì đọc toàn bộ object vào RAM.

### 14.4. Bảo vệ nội dung

Đừng public bucket để ứng dụng hoạt động cho nhanh. Với ảnh public, có thể chọn kiến trúc **backend bucket + Cloud CDN** cùng bucket policy phù hợp; với tài liệu riêng, dùng ứng dụng xác thực rồi trả nội dung hoặc **signed URLs** giới hạn thời gian. Thiết kế lifecycle/versioning theo nhu cầu khôi phục và chi phí.

## 15. GKE, Cloud Run và Cloud SQL: chọn storage theo compute platform

### 15.1. GKE PersistentVolume/PersistentVolumeClaim

Trong GKE, ứng dụng khai báo **PersistentVolumeClaim (PVC)** và driver **Container Storage Interface (CSI)** có thể cấp phát storage tương ứng.

| Nhu cầu trên GKE | Hướng chọn |
|---|---|
| Một pod/database instance cần block filesystem | **Compute Engine PD/Hyperdisk CSI**, access mode phù hợp |
| Nhiều pods cần chung NFS share với **ReadWriteMany** | **Filestore CSI** hoặc NFS solution được hỗ trợ |
| Dataset/training dùng object API | **Cloud Storage SDK** hoặc GCS FUSE CSI theo điều kiện |
| High throughput parallel POSIX cho HPC/AI | **Managed Lustre** nếu tích hợp phù hợp |

Ví dụ PVC cơ bản dùng StorageClass **standard-rwo** có sẵn ở môi trường GKE hỗ trợ:

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: standard-rwo
  resources:
    requests:
      storage: 50Gi
~~~

**ReadWriteOnce** không đồng nghĩa mọi pod đều đọc/ghi được ở các node khác nhau. RWO thường giới hạn read/write attachment theo node/volume; **ReadWriteMany** cần storage driver thực sự hỗ trợ chia sẻ. Kiểm tra storage class, provisioner, zone topology, reclaim policy và backup trước khi deploy StatefulSet.

### 15.2. Cloud Run

Cloud Run là nền tảng container managed, các instances có thể scale về 0 hoặc bị thay thế. Không nên coi filesystem tạm trong container là nơi lưu trạng thái lâu dài. Với Cloud Run:

- **Cloud Storage** thường phù hợp cho ảnh/tài liệu, artifact và dữ liệu lâu dài qua SDK hoặc mount được hỗ trợ.
- **Filestore/NFS** có thể phù hợp với các cách mount volume và VPC connectivity được Cloud Run hỗ trợ, nhưng cần kiểm tra giới hạn product/region, hiệu năng và chi phí.
- Database transactional nên dùng **Cloud SQL, AlloyDB, Spanner** hoặc sản phẩm phù hợp, thay vì tự quản filesystem của container.

### 15.3. Cloud SQL không cần người dùng attach Persistent Disk

**Cloud SQL** là managed database; người dùng chọn kích thước, HA, backup, bảo trì và storage settings qua giao diện dịch vụ. Không tự tạo một PD rồi attach nó vào Cloud SQL instance như với Compute Engine.

Chỉ khi **tự vận hành database trên VM** mới trực tiếp chọn PD/Hyperdisk, filesystem, mount, replication và backup ở tầng máy.

## 16. Tối ưu chi phí: không chỉ nhìn USD/GiB

### 16.1. Các thành phần cần đưa vào dự toán

| Loại | Chi phí chính | Khoản thường bị bỏ sót |
|---|---|---|
| **Persistent Disk** | Provisioned GiB theo disk type/zone | Regional replicas, snapshots, disk còn tồn tại sau khi xóa VM |
| **Hyperdisk** | Capacity + provisioned IOPS/throughput tùy type | Provision vượt nhu cầu, multi-writer architecture, snapshots |
| **Local SSD** | Capacity gắn machine theo cấu hình giá | Chi phí reconstruct dữ liệu nếu host lỗi |
| **Filestore** | Provisioned capacity/tier/performance | Dung lượng chưa dùng, backups, cross-region traffic, client VM |
| **Managed Lustre** | File system capacity/performance, operations theo dịch vụ | Data import/export, staging, idle filesystem |
| **NetApp Volumes** | Service level, capacity, features | Snapshot/replication, network, SMB/enterprise vận hành |
| **Cloud Storage** | Stored bytes × class/location | API operations, retrieval fees, early deletion, egress, versioning, soft delete, logging |

**Dừng VM không tự xóa disk**, cũng không dừng mọi phí storage. Đối với Filestore, khoản tiền có thể dựa trên **dung lượng được cấp** ngay cả khi dữ liệu dùng thực tế còn ít. Với Cloud Storage, lớp lưu trữ rẻ hơn cho bytes không chắc tiết kiệm nếu truy xuất thường xuyên và trả retrieval/early deletion charges.

### 16.2. Ví dụ tư duy TCO

Một thư mục **2 TiB hình ảnh** không cần sửa từng block, chứa nhiều object, phục vụ qua CDN. Nếu dùng VM + PD để làm file server, cần tính thêm CPU/VM uptime, patching, backup, load balancing, egress và HA. Cloud Storage có thể giảm vận hành, nhưng phải tính API calls và CDN egress.

Ngược lại, một **database 200 GiB** thực hiện hàng nghìn transaction nhỏ mỗi giây có thể gặp latency/semantics không phù hợp khi dùng object API. “Giá lưu 200 GiB rẻ hơn” không phải cơ sở chọn storage nếu ứng dụng không đáp ứng SLO.

### 16.3. Quy trình tối ưu không phá hiệu năng

1. Đo nhu cầu **capacity, IOPS, throughput, latency, requests và egress** trong ít nhất một chu kỳ tải điển hình.
2. Kiểm tra zone/region và khả năng hỗ trợ disk/file tier.
3. Chọn **bậc tối thiểu đáp ứng SLO**, không cấp quá rộng vì lo ngại mơ hồ.
4. Thiết kế backup/lifecycle/retention trước khi giảm capacity hay xóa dữ liệu.
5. Đối chiếu Cloud Billing reports, budgets/alerts, metrics workload và kết quả kiểm thử.
6. Định kỳ review khi dữ liệu/tải tăng, vì thiết kế đúng hôm nay có thể không tối ưu sau một năm.

## 17. Tình huống tổng hợp: hệ thống thương mại điện tử có xử lý AI

Doanh nghiệp **Phú An** vận hành:

- API Java trên **Compute Engine regional managed instance group**.
- PostgreSQL tự quản trên VM hoặc cân nhắc Cloud SQL.
- Hai workers cần thư mục chung để tạo báo cáo PDF.
- Hàng triệu ảnh sản phẩm, bản xuất CSV và backup.
- Worker GPU tiền xử lý ảnh với nhiều file tạm.
- Nhiều dịch vụ chạy trên GKE và Cloud Run.

### 17.1. Bản thiết kế tham khảo

~~~mermaid
flowchart TB
    WEB["Web / mobile clients"] --> LB["Application Load Balancer"]
    LB --> API["Java API<br/>Compute Engine / GKE"]
    API --> DB["PostgreSQL VM<br/>Hyperdisk / PD<br/>hoặc Cloud SQL"]
    API --> OBJ["Cloud Storage<br/>product images, exports"]
    WORK["Workers tạo PDF<br/>nhiều VM/pod"] --> NFS["Filestore Regional<br/>NFS shared directory"]
    GPU["GPU processing worker"] --> SSD["Local SSD<br/>scratch/cache"]
    GPU --> OBJ
    NFS --> OBJ
    OBJ --> CDN["Cloud CDN nếu phù hợp"]
~~~

| Thành phần | Lựa chọn | Lý do và biện pháp bảo vệ |
|---|---|---|
| API boot disks | PD Balanced/Hyperdisk Balanced | Block device, chọn theo VM và I/O thực |
| PostgreSQL tự quản | Hyperdisk Balanced/Extreme hoặc PD SSD | Random I/O, filesystem, backup nhất quán, replication |
| PostgreSQL managed | Cloud SQL | Dịch vụ DB quản lý storage/HA riêng |
| PDF shared workspace | Filestore Regional | Nhiều workers cùng thấy file tree, cân nhắc locking/HA |
| Product images | Cloud Storage Standard | Object APIs, metadata, CDN, IAM |
| Dataset/archives | Cloud Storage theo class/lifecycle | Khả năng mở rộng, retention, chi phí retrieval |
| GPU temporary files | Local SSD | Dữ liệu tạm có thể tái tạo; checkpoint ra Cloud Storage |
| ML training parallel lớn | Managed Lustre nếu workload đủ lớn | Throughput/POSIX, benchmark trước |

### 17.2. Vì sao không chọn một dịch vụ cho tất cả?

**Giả định A: dùng Cloud Storage FUSE cho PostgreSQL.** Rủi ro lớn về POSIX semantics, random write/patch và latency; không phải backend database phù hợp.

**Giả định B: dùng một PD và mount rw trên nhiều VM web.** Filesystem thông thường không xử lý an toàn concurrent writes từ nhiều host; cần shared file solution hoặc cluster-aware system.

**Giả định C: dùng Filestore cho mọi ảnh public.** Có thể hoạt động nếu ứng dụng tự phục vụ HTTP, nhưng tăng nhu cầu vận hành file serving layer và không tận dụng tự nhiên Cloud Storage/CDN, metadata, lifecycle.

**Giả định D: mọi file quan trọng để trên Local SSD.** Nguy cơ mất dữ liệu khi host event; cần durable storage/replication và checkpoint.

### 17.3. SLO và kiểm thử cho từng lớp

| Phép kiểm tra | Kỳ vọng |
|---|---|
| PostgreSQL chạy fsync/random write test | IOPS/p99 latency trong ngưỡng, backup restore thành công |
| VM/zone lỗi | Có kế hoạch failover cho disk, Filestore hoặc DB, RTO/RPO đạt yêu cầu |
| Hai workers tạo PDF trên cùng share | Không đè file nhau; locking/atomic rename đúng |
| Cloud Storage upload object mới | GET/list sau write thành công, IAM đúng, không public ngoài ý muốn |
| Client đồng thời sửa một object | Generation precondition ngăn lost update |
| GPU worker bị dừng | Có checkpoint durable; dữ liệu Local SSD có thể dựng lại |
| Cloud CDN cached image | Có cache invalidation/versioned URL strategy |
| Tháng tải cao điểm | Billing theo storage, operations, egress và metrics đủ quan sát |

## 18. Những sai lầm thường gặp

**“GCS FUSE làm Cloud Storage thành ổ NFS POSIX.”** Sai. FUSE là adapter trên object API với giới hạn về POSIX, patching, locking, latency và metadata.

**“Persistent Disk là ổ cứng nằm trên host nên xóa VM là mất dữ liệu.”** Sai về bản chất: PD là block storage qua mạng độc lập với host; tuy vậy **deletion rule auto-delete** có thể làm disk bị xóa cùng VM.

**“Block storage có multi-writer thì ai cũng mount ext4 và ghi được.”** Sai. Cần clustered filesystem hoặc application coordination chuyên dụng; có thể corrupt dữ liệu.

**“Regional disk thay thế backup.”** Sai. Replication giúp kháng lỗi zone, không khôi phục dữ liệu sau xóa nhầm hoặc ghi sai logic.

**“File storage bao giờ cũng cho mọi VM truy cập miễn cấu hình mạng.”** Sai. Filestore cần VPC route/port/firewall/export permissions, UID/GID đúng.

**“Object storage eventual consistency nên upload xong chưa được đọc ngay.”** Không đúng với các thao tác Cloud Storage được bảo đảm **strong consistency**; cần phân biệt với cache công khai và transaction liên object.

**“Archive storage nghĩa là không thể đọc ngay.”** Không hẳn; Cloud Storage Archive là online storage class với chi phí retrieval và minimum storage duration khác Standard.

**“Cloud Run filesystem giống Persistent Disk của VM.”** Sai. Filesystem trong container không tự là bền vững; cần dùng dịch vụ lưu trữ bên ngoài phù hợp.

**“Tăng Hyperdisk IOPS là ứng dụng sẽ nhanh gấp đôi.”** Chưa chắc. VM caps, CPU, queue depth, database locks, network và I/O size có thể giới hạn hiệu năng.

**“Ngừng VM là ngừng tính phí mọi disk/Filestore/bucket.”** Sai. Dữ liệu, share và objects tồn tại thường vẫn có chi phí tương ứng.

## 19. Bài tập thực hành và đáp án gợi ý

### Bài tập A — Chọn dịch vụ

Với mỗi yêu cầu, hãy chọn nhóm dịch vụ phù hợp và giải thích:

1. VM cần disk riêng để cài Ubuntu và PostgreSQL.
2. Ba VM Linux xử lý ảnh cần một thư mục cùng đọc/ghi.
3. 10 triệu ảnh sản phẩm cần phục vụ web, metadata và lifecycle.
4. GPU job cần 2 TiB scratch data có thể tái tạo.
5. Windows file server legacy yêu cầu SMB.
6. Huấn luyện AI quy mô lớn đòi parallel POSIX I/O.

**Đáp án định hướng:** (1) Hyperdisk/Persistent Disk; (2) Filestore; (3) Cloud Storage và CDN nếu phù hợp; (4) Local SSD theo cấu hình hỗ trợ, checkpoint durable; (5) NetApp Volumes/SMB solution; (6) Managed Lustre nếu scale, giá và tích hợp phù hợp.

### Bài tập B — Phân biệt access modes

Một StatefulSet trên GKE dùng PVC **ReadWriteOnce** gắn vào node A. Đội phát triển muốn nhiều pods trên nhiều nodes cùng sửa một tập tin trong volume này.

**Câu hỏi:** Có thể chỉ chuyển tất cả pods sang mount cùng volume không? Nên dùng giải pháp nào?

**Đáp án:** Không được tự suy từ RWO rằng RWX được hỗ trợ. Nếu cần shared file namespace trên nhiều nodes, chọn Filestore CSI/NFS hoặc sản phẩm hỗ trợ ReadWriteMany phù hợp. Multi-writer block là vấn đề khác, cần clustered filesystem.

### Bài tập C — Tính giá trị kỹ thuật

Workload có:

- 200 GiB dữ liệu.
- 20.000 random read/write IOPS, block 4 KiB.
- p99 latency phải thấp.
- VM hỗ trợ Hyperdisk nhưng loại PD hiện tại chỉ đạt hiệu năng thấp ở size 200 GiB.

Hãy so sánh:

- Tăng Persistent Disk size để tăng performance.
- Chuyển sang Hyperdisk Balanced và provision IOPS/throughput phù hợp.

**Định hướng:** Đánh giá **IOPS limit của disk và VM**, p99 thực, giá capacity + IOPS/throughput, khả năng migration, downtime/rollback. Không chỉ tối ưu GiB cost.

### Bài tập D — Cloud Storage concurrency

Hai workers cố upload **reports/final.json** cùng lúc. Cả hai dùng cùng object name nhưng chứa nội dung khác nhau.

**Câu hỏi:** Strong consistency có ngăn lost update không? Làm thế nào để tránh overwrite ngoài ý muốn?

**Đáp án:** Không; strong consistency nói đến visibility sau thao tác thành công. Dùng **generation preconditions** như **doesNotExist/ifGenerationMatch**, tên object phiên bản, manifest hoặc transactional coordination ở database.

### Bài tập E — Thiết kế backup và DR

Ứng dụng có database 500 GiB, thư mục NFS 2 TiB và Cloud Storage bucket 20 TiB. Quy định RPO=15 phút, RTO=2 giờ cho dữ liệu quan trọng.

Hãy mô tả:

1. Thành phần nào cần replication/HA.
2. Backup/snapshot/versioning/retention cho từng nhóm.
3. Cách thực hiện restore drill và đo RTO/RPO.
4. Cách bảo vệ khỏi xóa nhầm bằng account có quyền rộng.
5. Chi phí phát sinh từ snapshot, versioning, replication, egress và dữ liệu lâu năm.

**Gợi ý:** RPO 15 phút không tự đạt chỉ nhờ snapshot ngày một lần. Database có thể cần replication/WAL, Filestore và bucket cần lịch backup/versioning phù hợp. Khả năng khôi phục chỉ được công nhận khi thử restore thành công.

### Bài tập F — Tìm nguyên nhân lỗi vận hành

Nhóm gặp:

- **VM mới có disk nhưng không thấy /mnt/app-data**.
- **Filestore mount timeout**.
- **Cloud Storage upload trả 403**.
- **GCS FUSE sửa file lớn rất chậm**.

**Hướng giải:**

| Hiện tượng | Kiểm tra đầu tiên |
|---|---|
| Disk attach mà không có mount | Guest OS thấy device? Đã format **đúng disk** và mount? Filesystem UUID/fstab? |
| Filestore timeout | IP/export path, NFS version, VPC route, firewall, reserved range, instance state |
| Cloud Storage 403 | IAM principal, bucket access level, uniform access, org policy/PAP, service account |
| GCS FUSE patch chậm | Thực tế đang rewrite whole object? App có yêu cầu POSIX? Nên đổi sang block/NFS hoặc SDK? |

## 20. Tổng kết và tài liệu tham khảo

**Bảy nguyên tắc chốt:**

1. **Block** cung cấp thiết bị lưu trữ cho hệ điều hành và ứng dụng, phù hợp boot/database/in-place writes; chọn **Persistent Disk/Hyperdisk** theo VM, IOPS và độ bền.
2. **Local SSD** dành cho dữ liệu tạm hiệu năng cao, không phải nơi lưu bản sao duy nhất của dữ liệu quan trọng.
3. **File storage** cung cấp shared namespace và semantics qua NFS/SMB/parallel POSIX; chọn **Filestore**, **NetApp Volumes** hay **Managed Lustre** theo protocol và workload.
4. **Cloud Storage** lưu object qua APIs, có strong consistency cho các thao tác object được hỗ trợ và quản trị class/location/lifecycle/IAM theo nhu cầu.
5. **Cloud Storage FUSE** không biến bucket thành POSIX filesystem; không dùng làm data directory của database ghi ngẫu nhiên.
6. **High availability, durability và backup là ba yêu cầu khác nhau**. Regional replication không thay thế snapshot, retention hoặc thử phục hồi.
7. Quyết định tốt phải xét **I/O pattern, đồng thời, quyền, kết nối, RPO/RTO, tổng chi phí và SLO**, không chỉ chọn gói có giá lưu trữ thấp nhất.

**Tài liệu Google Cloud chính thức:**

1. [Choose a disk type — Compute Engine](https://docs.cloud.google.com/compute/docs/disks) — quyết định Persistent Disk/Hyperdisk/Local SSD.
2. [Persistent Disk overview](https://docs.cloud.google.com/compute/docs/disks/persistent-disks) — loại disk, durability và semantics.
3. [Google Cloud Hyperdisk overview](https://docs.cloud.google.com/compute/docs/disks/hyperdisks) — Balanced/HA/Extreme/Throughput/ML, giới hạn và performance.
4. [Add a Persistent Disk volume](https://docs.cloud.google.com/compute/docs/disks/add-persistent-disk) — gcloud create, attach, guest filesystem.
5. [Filestore service tiers](https://docs.cloud.google.com/filestore/docs/service-tiers) — zonal, regional, multishares, legacy.
6. [Create a Filestore instance](https://docs.cloud.google.com/filestore/docs/creating-instances) — network, share và CLI.
7. [Mount Filestore file shares on Compute Engine](https://docs.cloud.google.com/filestore/docs/mounting-fileshares) — NFS mount, network và fstab.
8. [Google Cloud Managed Lustre overview](https://docs.cloud.google.com/managed-lustre/docs/overview) — parallel POSIX filesystem cho AI/HPC.
9. [Google Cloud NetApp Volumes overview](https://docs.cloud.google.com/netapp/volumes/docs/discover/overview) — NFS/SMB và enterprise workloads.
10. [Cloud Storage storage classes](https://docs.cloud.google.com/storage/docs/storage-classes) — Standard/Nearline/Coldline/Archive/Rapid.
11. [Cloud Storage consistency](https://docs.cloud.google.com/storage/docs/consistency) — object read/list consistency.
12. [Cloud Storage FUSE overview](https://docs.cloud.google.com/storage/docs/cloud-storage-fuse/overview) — semantics và những giới hạn so với POSIX.
13. [GKE persistent volumes](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/persistent-volumes) — CSI provisioners, PV/PVC và access modes.
