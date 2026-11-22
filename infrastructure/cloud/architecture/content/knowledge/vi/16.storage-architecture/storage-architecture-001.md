# Chọn lưu trữ đối tượng, khối và tệp theo kiểu truy cập

## 1. Bắt đầu từ cách ứng dụng sử dụng dữ liệu

Một ứng dụng cloud có thể lưu ảnh người dùng, video, tài liệu, log, bản sao lưu, file cấu hình, dữ liệu giao dịch và filesystem của máy chủ. Những dữ liệu này có cách truy cập rất khác nhau. Có dữ liệu được đọc theo một object hoàn chỉnh qua API; có dữ liệu cần block thiết bị với độ trễ thấp để hệ quản trị cơ sở dữ liệu tự quản lý trang dữ liệu; có dữ liệu cần nhiều máy cùng nhìn thấy một cây thư mục và thao tác file theo quy ước POSIX.

Ba kiểu lưu trữ phổ biến là:

- **Object storage (lưu trữ đối tượng):** lưu dữ liệu dưới dạng object cùng metadata, truy cập qua API hoặc giao thức tương thích. Phù hợp ảnh, video, tài liệu, log, backup, data lake và nội dung tĩnh.
- **Block storage (lưu trữ khối):** cung cấp các block device/volume để hệ điều hành hoặc ứng dụng định dạng filesystem hay quản lý block trực tiếp. Phù hợp đĩa máy ảo, database, volume cho container và ứng dụng cần random I/O.
- **File storage (lưu trữ tệp):** cung cấp không gian tên dạng thư mục/tệp, có thao tác open/read/write/rename/lock theo giao thức filesystem. Phù hợp thư mục dùng chung, home directory, nội dung CMS và phần mềm cần filesystem semantics.

Không có loại nào luôn nhanh nhất, rẻ nhất hoặc đáng tin cậy nhất. Lựa chọn phụ thuộc **kiểu truy cập, kích thước dữ liệu, số client đồng thời, độ trễ, IOPS, throughput, độ bền, tính nhất quán, khả năng chia sẻ, vòng đời dữ liệu, bảo mật, phục hồi và tổng chi phí sở hữu**.

Trong module **CLOUD_ARCHITECTURE**, quyết định storage là một phần của thiết kế dữ liệu và hạ tầng cloud. Phải bắt đầu từ yêu cầu nghiệp vụ và workload thực tế, sau đó đánh đổi giữa hiệu năng, độ tin cậy, bảo mật, khả năng mở rộng, chi phí và năng lực vận hành theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt object, block và file storage theo mô hình dữ liệu và giao diện truy cập.
- Chuyển access pattern thành yêu cầu đo được về IOPS, throughput, latency, concurrency và dung lượng.
- Chọn kiểu lưu trữ phù hợp cho database, VM, container, media, file dùng chung và backup.
- Đánh giá consistency, durability, availability, replication, snapshot và backup.
- Thiết kế bảo mật, mã hóa, IAM, network access, lifecycle và data protection.
- Ước lượng tổng chi phí và lập kế hoạch kiểm thử trước khi đưa storage vào production.

## 2. Ba mô hình lưu trữ nhìn từ ứng dụng

~~~mermaid
flowchart TB
    App["Ứng dụng / workload"]
    App --> API["API / SDK"]
    App --> Device["Block device / volume"]
    App --> FS["Filesystem interface"]
    API --> Obj["Object storage"]
    Device --> Block["Block storage"]
    FS --> File["File storage"]
    Obj --> OData["Object + metadata + key"]
    Block --> BData["Blocks + volume"]
    File --> FData["Directories + files + permissions"]
~~~

| Đặc tính | Object storage | Block storage | File storage |
| --- | --- | --- | --- |
| Đơn vị dữ liệu | Object có key, payload và metadata | Block address trong volume | File và directory trong namespace |
| Giao diện chính | HTTP API/SDK, REST hoặc giao thức tương thích | Block device qua protocol/driver | NFS, SMB hoặc filesystem protocol |
| Truy cập | Thường theo object/key; đọc/ghi object qua API | Đọc/ghi block ngẫu nhiên hoặc tuần tự | Thao tác file, thư mục, metadata và lock |
| Chia sẻ | Nhiều client truy cập cùng object qua API và policy | Thường gắn volume theo giới hạn attach/multi-attach của sản phẩm | Nhiều client có thể mount cùng file system |
| Scale | Thường mở rộng dung lượng rất lớn theo dịch vụ | Theo volume, kích thước, IOPS và throughput được cấp | Theo filesystem, capacity, throughput và số client |
| Phù hợp | Media, backup, archive, data lake | OS disk, database volume, transactional workload | Shared directory, home folder, enterprise apps |
| Điểm cần lưu ý | Không tự có filesystem POSIX; cập nhật object không tương đương ghi block | Cần quản trị filesystem, mount, snapshot và attach | Metadata operation, file locking, permissions và network latency |

Một số sản phẩm cung cấp nhiều giao diện hoặc tính năng lai. Ví dụ object storage có thể cung cấp mount gateway hoặc file interface; block volume có thể hỗ trợ multi-attach trong một số chế độ; file service có thể cung cấp tier hiệu năng khác nhau. Khi đánh giá, hãy hiểu **semantics của tính năng cụ thể**, không suy từ tên sản phẩm.

## 3. Phân tích access pattern trước khi chọn

Storage nên được chọn theo cách ứng dụng đọc, ghi, cập nhật và chia sẻ dữ liệu. Hãy trả lời các câu hỏi:

| Câu hỏi | Ý nghĩa đối với lựa chọn |
| --- | --- |
| Dữ liệu được đọc theo key, block offset hay đường dẫn file? | Xác định object, block hoặc file interface |
| Đọc/ghi toàn bộ object hay cập nhật từng vùng nhỏ thường xuyên? | Object phù hợp nội dung hoàn chỉnh; block phù hợp random I/O; file phù hợp thao tác file |
| Kích thước mỗi đơn vị dữ liệu và tổng dung lượng? | Ảnh nhỏ, file lớn, volume database và hàng tỷ object có hành vi chi phí khác nhau |
| Tỷ lệ read/write và mức random/sequential? | Ảnh hưởng IOPS, throughput, cache và loại media |
| Có bao nhiêu client đồng thời? | Ảnh hưởng connection, metadata operations, locking và chia sẻ |
| Client ở cùng AZ, khác AZ hay on-premises? | Ảnh hưởng latency, network path, chi phí truyền dữ liệu và khả năng mount |
| Cần consistency nào sau khi ghi? | Quyết định mức độ an toàn khi client khác đọc hoặc cập nhật |
| Dữ liệu cần tồn tại bao lâu và phục hồi ra sao? | Quyết định lifecycle, replication, backup, snapshot, retention và archive |
| Ai được đọc, ghi, chia sẻ và xóa? | Thiết kế IAM, POSIX/ACL, encryption, audit và quyền xóa |

### 3.1. Đặc tính workload thường gặp

- **Large sequential read/write:** đọc hoặc ghi file/video lớn, backup stream; quan tâm MB/s hoặc GB/s và network throughput.
- **Small random I/O:** database đọc/ghi nhiều trang nhỏ ở vị trí ngẫu nhiên; quan tâm IOPS, latency và queue depth.
- **Metadata-heavy:** duyệt thư mục, stat, rename, create/delete nhiều file; quan tâm metadata performance và concurrency.
- **Read-many/write-once:** nội dung publish, model artifact, media; object storage thường phù hợp.
- **Shared mutable files:** nhiều máy cùng đọc/ghi một file hoặc cây thư mục; cần file locking và consistency semantics.
- **Append-only event/log:** ghi tuần tự, lưu dài hạn và query theo lô; object storage/data lake hoặc dịch vụ log có thể phù hợp.
- **Temporary scratch:** dữ liệu trung gian có thể tạo lại; local ephemeral disk hoặc tier chi phí thấp có thể phù hợp.

### 3.2. Không nhầm dung lượng với hiệu năng

Một volume 10 TB không mặc nhiên nhanh hơn volume 1 TB. Nhiều dịch vụ tách dung lượng đã cấp khỏi IOPS và throughput; có sản phẩm cho provision IOPS độc lập, có sản phẩm gắn hiệu năng với size hoặc tier. Tương tự, object storage có dung lượng gần như không cần provision trước nhưng vẫn có giới hạn request rate, throughput, request cost và data retrieval.

Đo theo workload thực: request size, tỷ lệ đọc/ghi, queue depth, số luồng, file size distribution, working set và burst duration. Không chọn chỉ dựa trên dung lượng hiện tại.

## 4. Object storage: object, key và metadata

Object storage lưu payload cùng metadata và một định danh (key) trong bucket/container hoặc namespace tương ứng. Ứng dụng thao tác qua API/SDK: PUT, GET, HEAD, LIST, DELETE và các tính năng như multipart upload, versioning, lifecycle, replication hoặc signed URL tùy nền tảng.

~~~mermaid
flowchart TB
    Client["Ứng dụng / trình duyệt"] --> SDK["SDK / HTTPS API"]
    SDK --> Bucket["Bucket / container"]
    Bucket --> O1["Object key: users/42/avatar.jpg"]
    Bucket --> O2["Object key: invoices/2026/INV-001.pdf"]
    Bucket --> O3["Object key: media/video-01.mp4"]
    O1 --> Meta["Payload + system/custom metadata"]
    O2 --> Meta
    O3 --> Meta
~~~

### 4.1. Khi nào object storage phù hợp?

- Ảnh, video, âm thanh, file đính kèm và tài liệu được upload/download như một object.
- Static website assets và artifact build.
- Backup, snapshot export, archive và log lâu dài.
- Data lake: dữ liệu thô, parquet/ORC/CSV, model artifact và dữ liệu phân tích theo batch.
- Nội dung cần truy cập toàn cầu qua CDN hoặc signed URL.
- Dữ liệu có số lượng object lớn, dung lượng tăng theo thời gian và lifecycle khác nhau.

### 4.2. Key và cách tổ chức namespace

Key thường là một chuỗi định danh duy nhất trong phạm vi bucket/container. Dấu slash trong key thường chỉ là quy ước tạo cảm giác thư mục; object storage không nhất thiết có directory thật với mọi semantics filesystem.

Ví dụ:

~~~text
tenant-42/orders/2026/11/order-1001.json
tenant-42/invoices/2026/INV-1001.pdf
tenant-42/media/product-88/main.webp
~~~

Chọn key sao cho dễ truy xuất, tránh collision, hạn chế lộ thông tin cá nhân và phù hợp với partitioning/request distribution của dịch vụ. Không đưa email, số điện thoại hoặc token bí mật vào key nếu nó xuất hiện trong URL, log hay audit. Khi cần xóa theo tenant hoặc retention, namespace nên hỗ trợ truy vấn và lifecycle policy rõ.

### 4.3. Object API không phải thao tác file tùy ý

Object thường được ghi hoặc thay thế như một đơn vị; cập nhật một vài byte ở giữa object không giống ghi block ngẫu nhiên vào disk. Một số API hỗ trợ multipart upload hoặc range GET, nhưng không biến object thành filesystem POSIX. Nếu ứng dụng liên tục sửa một file lớn theo offset, block storage hoặc database có thể phù hợp hơn.

Object storage có thể hỗ trợ strong read-after-write consistency cho một số thao tác theo mô tả dịch vụ; phải đọc tài liệu provider về PUT/GET/LIST, overwrite và delete semantics. Không tự suy rằng mọi dịch vụ object đều có consistency giống nhau.

### 4.4. Multipart upload, range read và signed URL

- **Multipart upload:** chia file lớn thành nhiều part để tải song song và retry phần lỗi; phải complete hoặc abort đúng quy trình để dọn part chưa hoàn tất.
- **Range GET:** tải một byte range, phù hợp video streaming hoặc tải lại một phần nội dung; không đồng nghĩa có thể PATCH một vùng của object.
- **Pre-signed URL:** cấp quyền truy cập tạm thời cho client upload/download mà không trao credential cloud dài hạn; phải giới hạn method, object key, thời hạn và kích thước/điều kiện nếu dịch vụ hỗ trợ.
- **CDN:** cache object gần người dùng, giảm latency và request tới origin; cần thiết kế cache key, invalidation, TTL và quyền truy cập nội dung riêng tư.

## 5. Block storage: volume và block device

Block storage cung cấp thiết bị logic gồm các block địa chỉ hóa. Hệ điều hành có thể tạo partition, filesystem và mount volume; database có thể đặt data file hoặc log lên volume theo hướng dẫn của engine.

~~~mermaid
flowchart TB
    App["Database / OS / container"] --> FS["Filesystem hoặc raw block layer"]
    FS --> Driver["Block device driver"]
    Driver --> Vol["Virtual block volume"]
    Vol --> Backend["Durable storage backend"]
    Snap["Snapshot"] -. "point-in-time copy theo dịch vụ" .-> Vol
~~~

### 5.1. Khi nào block storage phù hợp?

- Boot/system disk cho VM.
- Database cần random read/write và latency thấp theo đặc tính volume.
- Transaction log, message broker data hoặc ứng dụng có file I/O trực tiếp.
- Persistent volume cho container khi driver/storage class đáp ứng topology và access requirements.
- Workload cần kiểm soát filesystem, cache, mount option và I/O scheduler.

### 5.2. IOPS, throughput và latency

- **IOPS:** số thao tác input/output mỗi giây.
- **Throughput:** lượng dữ liệu truyền mỗi giây, thường đo MB/s hoặc GB/s.
- **Latency:** thời gian hoàn thành một thao tác I/O.
- **Queue depth:** số yêu cầu I/O đang chờ hoặc đang được xử lý.

Một workload nhiều I/O nhỏ có thể bị giới hạn bởi IOPS; workload streaming file lớn có thể bị giới hạn bởi throughput. Queue depth tăng đôi khi cải thiện utilization nhưng cũng có thể làm latency tăng. Cần xem p50/p95/p99 latency thay vì chỉ throughput trung bình.

### 5.3. Burst và provisioned performance

Một số volume có baseline IOPS/throughput và cho burst trong thời gian hoặc credit nhất định; sản phẩm khác cho provision IOPS/throughput riêng hoặc hiệu năng tăng theo dung lượng. Nếu chỉ test trong vài phút đầu, nhóm có thể thấy kết quả tốt nhờ burst credit rồi gặp giảm hiệu năng trong tải kéo dài.

Kịch bản thử tải phải bao gồm:

- Tải ổn định đủ lâu để vượt thời gian burst.
- Tải cao điểm với queue depth tương ứng.
- Mixed read/write và kích thước I/O thực.
- Khởi động lại VM, attach/detach và failover nếu workload yêu cầu.
- Snapshot/backup trong lúc tải và ảnh hưởng tới latency.

### 5.4. Gắn volume và chia sẻ

Block volume truyền thống thường được attach cho một VM hoặc node tại một thời điểm theo giới hạn sản phẩm. Một số dịch vụ cung cấp multi-attach hoặc clustered disk nhưng chỉ hỗ trợ ở cấu hình/engine cụ thể và thường cần filesystem cluster-aware hoặc ứng dụng có cơ chế coordination. **Không mount cùng block volume lên nhiều máy và cho chúng ghi filesystem thông thường cùng lúc** nếu sản phẩm và filesystem không hỗ trợ; có thể gây corruption.

Với Kubernetes, PVC có access mode như ReadWriteOnce, ReadOnlyMany, ReadWriteMany hoặc ReadWriteOncePod, nhưng khả năng thực thi còn phụ thuộc CSI driver và storage backend. Một access mode không tự biến block backend thành shared filesystem an toàn.

## 6. File storage: filesystem dùng chung

File storage cung cấp cây thư mục và file có tên, metadata, owner, permissions và thao tác filesystem quen thuộc. Client mount qua network protocol như NFS hoặc SMB; nhiều instance có thể truy cập cùng filesystem khi dịch vụ hỗ trợ.

~~~mermaid
flowchart TB
    A["VM / container node A"] --> M["NFS / SMB mount"]
    B["VM / container node B"] --> M
    C["VM / container node C"] --> M
    M --> FS["Shared file system"]
    FS --> D1["/shared/reports"]
    FS --> D2["/shared/uploads"]
    FS --> D3["/home/users"]
~~~

### 6.1. Khi nào file storage phù hợp?

- Ứng dụng legacy cần đường dẫn thư mục và file system calls.
- Nhiều VM hoặc container cần cùng đọc/ghi file chia sẻ.
- Home directory, nội dung CMS, file xử lý nghiệp vụ và shared workspace.
- Pipeline xử lý file dùng chung giữa các máy/worker.
- Ứng dụng phụ thuộc vào rename, directory traversal, file locking hoặc POSIX/SMB ACL.

### 6.2. Metadata và concurrency

File workload không chỉ đọc payload; nó còn tạo, đổi tên, liệt kê, kiểm tra quyền và xóa file. Hệ thống có hàng triệu file nhỏ và thao tác metadata dày đặc có thể nghẽn dù tổng throughput MB/s thấp. Cần benchmark số file trong thư mục, directory listing, create/stat/rename rate, lock contention và số client.

Với nhiều client cùng ghi một file, phải hiểu locking semantics và cache consistency của NFS/SMB/dịch vụ. Không nên giả định hai process ghi đồng thời sẽ tự phối hợp đúng. Dùng file lock, atomic rename, application coordination hoặc database khi nghiệp vụ yêu cầu.

### 6.3. NFS và SMB

| Giao thức | Đặc điểm phổ biến | Lựa chọn thường gặp |
| --- | --- | --- |
| **NFS** | Thường dùng trong môi trường Unix/Linux; có các phiên bản và semantics khác nhau về locking, identity và transport | Shared Linux filesystem, analytics và container workloads |
| **SMB** | Thường dùng trong hệ sinh thái Windows; hỗ trợ share, ACL và tích hợp identity theo cấu hình | Windows file share, home directory và ứng dụng dùng SMB |

Đây là định hướng, không phải ràng buộc tuyệt đối. Một số dịch vụ hỗ trợ cả NFS lẫn SMB hoặc tích hợp identity đặc thù. Cần kiểm tra phiên bản protocol, authentication, encryption in transit, port, mount option và tương thích ứng dụng.

## 7. So sánh bằng tình huống truy cập

Một cách chọn nhanh là mô tả thao tác quan trọng nhất của ứng dụng và kiểm tra xem storage có hỗ trợ semantics đó một cách tự nhiên hay không.

| Tình huống | Lựa chọn khởi đầu | Lý do | Cần xác minh |
| --- | --- | --- | --- |
| Lưu avatar, ảnh sản phẩm và tài liệu tải lên | Object | Mỗi file là object riêng, truy cập bằng key/API, dễ tích hợp CDN và lifecycle | Kích thước object, signed URL, versioning, quyền tenant |
| Database PostgreSQL trên VM | Block | Database cần filesystem/block I/O và kiểm soát disk | IOPS, latency, write cache, durability, backup và crash recovery |
| Nhiều VM Linux cùng đọc/ghi thư mục dùng chung | File | Cần namespace file và chia sẻ qua NFS | Locking, metadata rate, identity mapping, throughput và mount recovery |
| Website tĩnh với lượng truy cập lớn | Object + CDN | Nội dung publish bất biến hoặc ít thay đổi, cache gần người dùng | Cache invalidation, TLS, access control và origin protection |
| Dữ liệu log dài hạn, phân tích theo lô | Object | Dữ liệu append/export theo file và đọc theo batch | Partitioning theo thời gian, format cột, lifecycle, query engine |
| Scratch data của worker có thể tạo lại | Local ephemeral hoặc block phù hợp | Cần I/O tạm, không cần bảo toàn sau khi worker kết thúc | Dung lượng, tốc độ local disk, eviction và retry |
| Ứng dụng Windows cần shared drive | File/SMB | Ứng dụng mong đợi share và semantics Windows | Directory service, ACL, locking, SMB version |
| Nhiều container xử lý chung thư mục upload | File nếu cần filesystem chung; object nếu trao đổi object | Chọn theo thao tác file hay API object | Scale, concurrent write, access mode, network và phí |

Không cần ép tất cả dữ liệu của một ứng dụng vào cùng một loại storage. Một ứng dụng thương mại điện tử có thể dùng database trên block hoặc managed database, ảnh trên object storage, file xuất báo cáo trên object, và thư mục dùng chung cho công cụ nội bộ trên file storage.

## 8. Consistency, locking và concurrency

Storage không chỉ phải giữ được byte; nó cần cung cấp hành vi quan sát và cập nhật phù hợp với ứng dụng.

### 8.1. Object consistency

Object storage thường cung cấp API-level semantics. Khi cập nhật object, client cần hiểu:

- Việc ghi object mới/thay thế có atomic visibility hay không theo hợp đồng dịch vụ.
- LIST có thấy object mới ngay theo consistency model không.
- Versioning có lưu các phiên bản trước khi overwrite/delete không.
- Conditional write, ETag, generation/version precondition hoặc compare-and-swap có được hỗ trợ không.
- Concurrent PUT tới cùng key có quy tắc thắng/thua hoặc version ra sao.

Nếu nhiều client có thể cùng sửa một object, tránh mô hình đọc rồi ghi đè thiếu coordination. Dùng conditional request/version precondition, lease/lock phù hợp hoặc chuyển dữ liệu có cập nhật đồng thời cao sang database. ETag không phải lúc nào cũng là checksum nội dung; multipart upload hoặc encryption có thể làm semantics khác nhau theo dịch vụ.

### 8.2. Block consistency

Block device thường cung cấp semantics thiết bị cho một host/kernel hoặc theo cơ chế multi-attach được hỗ trợ. Filesystem và database sử dụng flush/barrier, cache, journal và lock để duy trì tính đúng đắn. Khi có nhiều host truy cập block device, chỉ clustered filesystem hoặc application-level coordination được hỗ trợ mới có thể bảo đảm an toàn.

Không dùng hai filesystem thông thường độc lập mount và ghi trên cùng một raw block volume cùng lúc. Mỗi host có thể cache metadata riêng và làm hỏng cấu trúc filesystem.

### 8.3. File consistency và locking

File service cần xác định hành vi khi nhiều client đọc/ghi cùng file, cache attribute, file lease/oplock, locking và rename. Semantics khác nhau giữa NFS/SMB version và provider.

Khi nhiều worker cùng ghi output, cách an toàn thường là ghi vào file tạm riêng rồi publish bằng rename/manifest có coordination, thay vì để mọi worker ghi cùng file đích. Với dữ liệu giao dịch và cập nhật đồng thời cao, database thường là abstraction tốt hơn filesystem.

## 9. Availability, durability và data protection

Ba khái niệm thường bị nhầm:

- **Availability (tính sẵn sàng):** client có thể truy cập dịch vụ/dữ liệu khi cần hay không.
- **Durability (độ bền dữ liệu):** xác suất dữ liệu đã ghi bị mất trong một khoảng thời gian.
- **Recoverability (khả năng khôi phục):** tổ chức có thể đưa dữ liệu và ứng dụng về trạng thái cần thiết trong thời gian mục tiêu hay không.

Một dịch vụ có durability cao vẫn có thể bị xóa nhầm, mã hóa bởi ransomware hoặc ghi đè logic. Do đó durability không thay thế versioning, backup, retention lock, replication và restore test.

### 9.1. Snapshot không đồng nghĩa backup hoàn chỉnh

Snapshot thường ghi nhận trạng thái volume/filesystem tại một thời điểm theo khả năng của dịch vụ. Nó hữu ích cho rollback, clone, tạo image hoặc backup workflow, nhưng cần xem xét:

- Snapshot có crash-consistent hay application-consistent?
- Có phải freeze/quiesce filesystem hoặc database trước khi snapshot không?
- Snapshot được giữ cùng failure domain hay có bản sao sang tài khoản/region khác?
- Có bị xóa cùng quyền quản trị hoặc ransomware credential không?
- Có thể restore độc lập khi volume gốc bị mất không?

Với database, snapshot crash-consistent có thể cần database recovery từ WAL/transaction log. Với file share, snapshot cần semantics về file đang mở và ứng dụng đang ghi. Với object, versioning hoặc object lock có thể chống xóa/ghi đè theo policy nhưng vẫn phải quản lý lifecycle và quyền.

### 9.2. RPO và RTO

**Recovery Point Objective (RPO)** là lượng mất dữ liệu tối đa doanh nghiệp chấp nhận đo theo thời gian; **Recovery Time Objective (RTO)** là thời gian tối đa mục tiêu để khôi phục dịch vụ. Chúng phải được xác định theo quy trình nghiệp vụ:

| Workload | RPO/RTO cần hỏi | Thiết kế có thể cần |
| --- | --- | --- |
| Database đơn hàng | Có chấp nhận mất giao dịch đã xác nhận? Bao lâu cần hoạt động lại? | Backup nhất quán, log shipping/PITR, replica/failover và diễn tập |
| Ảnh sản phẩm | Có thể tái tạo hay phải giữ mọi upload đã nhận? | Object versioning, replication, deletion protection |
| File dùng chung | Bao lâu khôi phục thư mục và quyền? | Snapshot, backup ngoài miền lỗi, ACL/identity backup |
| Log analytics | Mất bao nhiêu phút log có thể chấp nhận? | Buffer/replication, object retention, partitioned export |

RPO thấp thường cần replication hoặc log capture thường xuyên hơn, tăng chi phí và phụ thuộc network. RTO thấp cần runbook, tự động hóa, capacity dự phòng và diễn tập; không đạt được chỉ bằng storage tier nhanh hơn.

### 9.3. Replication không phải backup

Replication giúp dữ liệu hiện diện ở miền lỗi khác để phục vụ HA/DR hoặc truy cập gần hơn. Nhưng xóa nhầm, overwrite sai hoặc dữ liệu bị mã hóa có thể được replicate sang bản sao. Backup có retention và khả năng khôi phục lịch sử là lớp bảo vệ khác.

Thiết kế bảo vệ dữ liệu nên phân lớp:

1. **Replication/HA** để chịu lỗi thành phần hoặc vùng theo semantics hỗ trợ.
2. **Snapshot/point-in-time recovery** để quay lại trạng thái trước một mốc.
3. **Backup độc lập** với retention, quyền xóa riêng và bản sao ngoài failure domain phù hợp.
4. **Restore test** để đo thời gian, tính nhất quán và tính đầy đủ của dữ liệu khôi phục.

## 10. Bảo mật storage và quản trị dữ liệu

Storage chứa dữ liệu quan trọng nên cần bảo vệ từ đường truyền, nơi lưu, danh tính truy cập đến vòng đời xóa.

### 10.1. Identity và access control

- Với object, cấp quyền theo bucket/container, prefix, object hoặc role cần thiết; dùng signed URL thời hạn ngắn khi client cần upload/download trực tiếp.
- Với block, giới hạn ai có quyền tạo, attach, detach, snapshot, copy và xóa volume; network access của workload cũng phải được kiểm soát.
- Với file, kết hợp network security với POSIX owner/mode, ACL, identity mapping hoặc directory service.
- Phân tách quyền đọc, ghi, xóa, quản lý key và thay đổi policy. Role ứng dụng không nhất thiết cần quyền xóa backup.
- Dùng workload identity/managed identity khi phù hợp; tránh access key dài hạn nhúng vào máy hoặc container.

### 10.2. Encryption

| Lớp | Câu hỏi |
| --- | --- |
| In transit | Client kết nối qua TLS, NFS/SMB encryption hoặc network bảo vệ nào? Certificate được xác minh ra sao? |
| At rest | Dịch vụ mã hóa mặc định hay phải bật? Object, volume, snapshot và backup có khác nhau không? |
| Key management | Dùng provider-managed key hay customer-managed key? Ai có quyền rotate/disable? |
| Key availability | Nếu KMS/key bị khóa hoặc region gặp sự cố, ứng dụng còn đọc được dữ liệu không? |
| Audit | Có log ai đọc, ghi, xóa, thay policy và thay key không? |

Customer-managed key tăng quyền kiểm soát và khả năng đáp ứng chính sách, nhưng thêm trách nhiệm rotation, availability, recovery và phân quyền. Nếu key bị disable hoặc xóa, dữ liệu mã hóa có thể không thể truy cập dù storage service vẫn khỏe.

### 10.3. Data lifecycle và xóa dữ liệu

Object storage thường có lifecycle transition sang tier lạnh, archive hoặc expiration. File và block có retention, snapshot schedule, volume deletion policy và backup cleanup riêng. Hãy định nghĩa:

- Dữ liệu nóng được truy cập thường xuyên giữ ở tier nào?
- Khi nào chuyển sang tier rẻ hơn, và mất bao lâu để restore?
- Có minimum storage duration hoặc retrieval charge không?
- Dữ liệu hết hạn được xóa ở object, version, snapshot, replica và backup thế nào?
- Nghĩa vụ pháp lý/privacy có yêu cầu xóa trong mọi bản sao hoặc retention lock không?

Không áp dụng lifecycle chỉ dựa trên tuổi dữ liệu nếu vẫn có workload truy cập thường xuyên. Phí truy xuất archive và thời gian restore có thể vượt lợi ích lưu trữ rẻ.

### 10.4. Multi-tenant storage

Với dữ liệu nhiều tenant, namespace/prefix riêng không tự bảo đảm isolation. Cần policy xác thực tenant ở backend, kiểm tra key ownership, tách role hoặc bucket theo mức rủi ro, tránh IDOR và kiểm thử truy cập chéo tenant. Với file share, xác minh identity mapping và ACL; với block, volume attach và snapshot phải tuân thủ quyền tenant/account.

## 11. Hiệu năng và sizing theo workload

Trước khi chọn tier, cần xây dựng workload profile có thể kiểm chứng:

| Thông số | Cách thu thập |
| --- | --- |
| Dung lượng hiện tại và tốc độ tăng | Tổng byte, số object/file, growth theo tuần/tháng |
| Kích thước đơn vị dữ liệu | Phân bố nhỏ/vừa/lớn, p50/p95/p99 |
| Read/write ratio | Số thao tác đọc/ghi, overwrite, delete và metadata request |
| IOPS | Số I/O nhỏ/giây tại block/file backend |
| Throughput | MB/s hoặc GB/s đọc/ghi liên tục |
| Latency | p50/p95/p99 theo operation, không chỉ trung bình |
| Concurrency | Số client, thread, process, mount và request đồng thời |
| Working set/cache | Dữ liệu nóng, cache hit ratio, page cache |
| Network path | Cùng AZ, cross-AZ, on-prem, Internet hoặc CDN |

### 11.1. Ví dụ phân biệt IOPS và throughput

Một database thực hiện 20.000 I/O mỗi giây, mỗi I/O 8 KiB. Throughput dữ liệu thô xấp xỉ:

**20.000 × 8 KiB ≈ 156,25 MiB/s.**

Một video pipeline ghi các chunk 1 MiB ở tốc độ 500 MiB/s cần khoảng 500 I/O mỗi giây nếu mỗi chunk tạo một I/O tương ứng. Hai workload có throughput và IOPS rất khác nhau; không thể chọn storage chỉ bằng một con số MB/s.

Ví dụ chưa tính filesystem metadata, write amplification, cache, replication, request overhead và kích thước I/O thực tế. Dùng benchmark ở mức ứng dụng để xác nhận.

### 11.2. Queue depth và tail latency

Khi workload gửi nhiều I/O song song, queue depth tăng có thể giúp tận dụng backend, nhưng khi vượt khả năng xử lý, thời gian chờ tăng làm p95/p99 latency xấu đi. Database có thể đạt throughput trung bình tốt hơn nhưng giao dịch quan trọng chậm hơn. Đặt ngưỡng queue, timeout và concurrency theo SLA ứng dụng.

### 11.3. Cache và CDN

Cache ở application, OS page cache, CDN hoặc cache dịch vụ có thể giảm request tới storage. Nhưng cache làm phát sinh invalidation, stale data và consistency concern. Với object tĩnh versioned, cache dài có thể hiệu quả; với file thay đổi thường xuyên, cần TTL/ETag/conditional GET và chiến lược publish. Không dùng cache để che latency backend khi chưa hiểu bottleneck.

## 12. Tổng chi phí sở hữu và tối ưu tier

Giá lưu trữ trên mỗi GB chỉ là một phần của bill. TCO có thể bao gồm:

- Dung lượng lưu theo tháng và tier.
- IOPS/throughput provisioned, capacity hoặc performance add-on.
- API request (GET/PUT/LIST/metadata), retrieval và restore.
- Snapshot, versioning, replication và backup.
- Cross-AZ/region replication, network egress và data transfer.
- Gateway, cache, CDN, mount compute và license.
- Nhân lực vận hành, on-call, kiểm toán, migration và khôi phục.
- Chi phí ngừng dịch vụ hoặc mất dữ liệu khi chọn tier không phù hợp.

| Loại | Thành phần chi phí thường gặp | Cạm bẫy |
| --- | --- | --- |
| Object | GB-month, request class, retrieval, replication, egress, versioning | LIST/GET quá nhiều, nhiều version và archive restore thường xuyên |
| Block | Dung lượng provisioned, IOPS/throughput, snapshot, cross-zone transfer | Cấp volume lớn/nhanh hơn nhu cầu, không xóa snapshot cũ, trả phí cho idle provision |
| File | Dung lượng, throughput mode, metadata/operation, backup, cross-zone | Nhiều client/metadata operation, filesystem provisioned dù ít dùng |

### 12.1. Dữ liệu nóng, ấm và lạnh

- **Hot:** truy cập thường xuyên, yêu cầu độ trễ thấp; chọn tier hiệu năng và cache phù hợp.
- **Warm:** truy cập không đều; tier tiêu chuẩn hoặc tự động phân tầng có thể phù hợp.
- **Cold/archive:** truy cập hiếm, có thể chờ restore; tính minimum retention, retrieval fee và thời gian lấy lại.

Không nhất thiết dữ liệu cũ là lạnh. Hồ sơ pháp lý có thể được truy cập đột xuất với SLA ngắn; cần tính cả xác suất và chi phí khôi phục.

### 12.2. Ước lượng dung lượng và chi phí

Ước lượng object storage sơ bộ:

**Chi phí dung lượng tháng = GB lưu trung bình × đơn giá GB-tháng.**

Tổng chi phí phải cộng request, retrieval, replication, versioned copies và egress. Với block, dung lượng volume đã provision có thể tính phí ngay cả khi filesystem chưa ghi hết; với file, cách tính có thể theo capacity/throughput mode của dịch vụ. Dùng pricing model thực tế của provider và đo growth thay vì so sánh đơn giá GB đơn lẻ.

## 13. Chọn storage cho container và ứng dụng cloud-native

Container có vòng đời ngắn, được reschedule và scale liên tục; storage cần tách khỏi vòng đời container khi dữ liệu phải tồn tại.

### 13.1. Ephemeral volume và local disk

Phù hợp cache, scratch, temp file và dữ liệu có thể tái tạo. Ưu điểm là độ trễ tốt và thường gắn trực tiếp với node; nhược điểm là dữ liệu có thể mất khi Pod/node bị xóa hoặc di chuyển. Không dùng ephemeral storage cho dữ liệu giao dịch duy nhất.

### 13.2. Persistent block volume qua CSI

Container orchestrator có thể dùng CSI driver để provision và attach block volume cho Pod. Cần hiểu access mode, topology, attach limits, volume binding mode, snapshot class và behavior khi Pod chuyển node. Volume có thể gắn với một zone nên Pod không thể tự do reschedule sang mọi zone.

### 13.3. Shared file volume

Khi nhiều replica cần cùng cây thư mục, file storage có thể mount vào nhiều Pod/node nếu driver hỗ trợ chế độ chia sẻ phù hợp. Xác minh ReadWriteMany, NFS/SMB semantics, throughput, locking, identity và network policy. Nếu mỗi replica chỉ cần file input giống nhau, object storage với download/cache local có thể đơn giản và rẻ hơn.

### 13.4. Object storage cho dữ liệu ứng dụng

Ứng dụng container thường nên lưu file upload, tài liệu và media trực tiếp trên object storage qua SDK/API hoặc signed URL. Không cần mount bucket như filesystem chỉ để thuận tiện code nếu ứng dụng vốn thao tác object; filesystem gateway có thể có khác biệt về rename, locking và consistency.

## 14. Ví dụ tổng thể: nền tảng thương mại điện tử

Giả sử hệ thống có database giao dịch, ảnh sản phẩm, tài liệu hóa đơn, thư mục dùng chung cho một công cụ xử lý cũ và backup định kỳ.

~~~mermaid
flowchart TB
    Web["Web / Mobile"] --> API["API / Application"]
    API --> DB[("Managed relational DB")]
    Web -->|Upload/download qua signed URL| Obj["Object storage: images, invoices"]
    API -->|Metadata và quyền truy cập| Obj
    Legacy["Legacy processing VMs"] --> NFS["Shared file storage"]
    Worker["Container workers"] -->|Đọc dữ liệu chia sẻ| NFS
    DB --> Backup["Backup / PITR"]
    Obj --> Lifecycle["Versioning / Lifecycle / Replication"]
    NFS --> Snap["Snapshot / Backup"]
~~~

### 14.1. Vì sao chia như vậy?

- Database dùng storage backend phù hợp engine; nếu tự chạy database trên VM, block volume cần sizing theo random I/O, write latency, durability và backup.
- Ảnh sản phẩm và hóa đơn là object; ứng dụng giữ metadata, owner, trạng thái và quyền trong database, payload ở object storage.
- File share phục vụ công cụ legacy cần cùng namespace NFS/SMB cho nhiều máy; nếu worker chỉ trao đổi file bất biến, có thể chuyển dần sang object để giảm phụ thuộc filesystem.
- Backup của database và file share cần retention, copy ngoài failure domain và restore test. Object versioning không tự thay backup toàn hệ thống.

### 14.2. Luồng upload an toàn

1. Client yêu cầu API tạo upload intent cho một tài liệu.
2. Backend xác thực tenant, loại file, kích thước cho phép và cấp signed URL thời hạn ngắn với key được tạo ở server.
3. Client upload trực tiếp tới object storage; không cần gửi toàn bộ byte qua API compute nếu không có lý do xử lý.
4. Backend xác minh upload (object key, size, checksum/metadata, trạng thái scan) và ghi metadata vào database.
5. File chưa qua kiểm tra được giữ trong vùng quarantine; sau khi scan hợp lệ mới cho phép tải qua luồng được ủy quyền.
6. Lifecycle, retention và xóa theo tenant được thực hiện theo chính sách.

Đường upload trực tiếp giảm tải bandwidth và compute cho API, nhưng backend vẫn phải kiểm soát quyền và xác minh object đã upload đúng key/kích thước. Signed URL là bearer capability; ai có URL trong thời hạn đều có thể dùng theo quyền đã ký, vì vậy không log hoặc chia sẻ URL tùy tiện.

## 15. Di chuyển giữa các loại storage

Thay object bằng file, block bằng managed database hay file share bằng object store không chỉ là copy byte. Phải chuyển cả semantics, quyền, metadata, lifecycle và cách ứng dụng truy cập.

### 15.1. Các bước migration

1. **Inventory:** liệt kê dataset, dung lượng, số object/file, access pattern, owner, ACL, metadata, dependency và retention.
2. **Target contract:** xác định API/semantics ở storage mới, consistency, performance, encryption, key, version và restore.
3. **Baseline:** đo latency, IOPS, throughput, error rate, cost và thời gian tác vụ trên hệ hiện tại.
4. **Bulk copy:** sao chép dữ liệu có kiểm tra checksum/size/metadata; giữ quyền và encryption theo policy.
5. **Incremental sync:** đồng bộ thay đổi trong lúc copy; xác định cơ chế capture và xử lý delete.
6. **Validation:** so sánh số lượng, checksum, object/file mapping, ACL, dữ liệu ứng dụng và hiệu năng.
7. **Cutover:** chuyển client qua endpoint mới, giới hạn write hoặc dùng dual-write có coordination rõ; ghi thời điểm.
8. **Rollback window:** giữ nguồn cũ chỉ đọc/khả năng quay lại theo kế hoạch; xác định cách xử lý dữ liệu phát sinh ở target.
9. **Decommission:** xóa nguồn cũ, snapshot, secret và quyền sau khi hết thời gian rollback và được owner xác nhận.

### 15.2. Rủi ro khi đổi semantics

| Chuyển đổi | Vấn đề không thể bỏ qua |
| --- | --- |
| File → Object | Rename directory, POSIX permissions, file lock và partial update không tự có semantics tương đương |
| Object → File | Key mapping, object metadata, versioning, rất nhiều object nhỏ và giới hạn path/filename |
| Block → Object | Random write, filesystem journal và database data file không thể copy từng object rồi tiếp tục chạy |
| Object → Block | Mất abstraction key/API, phải tự quản lý filesystem, partition, scaling và backup |
| Self-managed storage → Managed service | IAM, endpoint, access model, quotas, encryption key và maintenance window khác nhau |

Với database chạy trên block, migration thường cần database-native backup/restore, replication hoặc logical migration; không copy raw volume khi database đang ghi mà không có quy trình nhất quán.

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chọn storage chỉ theo giá GB | Hiệu năng, request và retrieval cost vượt dự kiến | Tính TCO theo access pattern |
| Dùng block volume để chia sẻ file giữa nhiều VM | Filesystem corruption nếu multi-writer không được hỗ trợ | Dùng file service hoặc clustered filesystem có hỗ trợ |
| Dùng object storage như POSIX filesystem | Rename/lock/partial update sai semantics | Dùng API object hoặc file service đúng yêu cầu |
| Coi snapshot là backup | Xóa/corruption có thể ảnh hưởng snapshot hoặc không đủ restore application | Backup độc lập, retention và restore test |
| Coi replication là protection khỏi xóa nhầm | Dữ liệu sai được replicate sang replica | Versioning, backup, retention lock và recovery |
| Cấp volume theo dung lượng mà không benchmark | IOPS/throughput thiếu hoặc lãng phí | Benchmark đúng I/O profile và tier |
| Đưa shared file storage cho mọi container | Tăng network latency, metadata contention và phí | Chỉ dùng khi thật sự cần filesystem sharing |
| Mở bucket/file share công khai | Rò rỉ dữ liệu và vi phạm quyền riêng tư | Least privilege, signed URL, private endpoint và audit |
| Không tính egress/replication | Hóa đơn tăng khi copy/đọc liên vùng | Ước lượng traffic và vị trí client |
| Lifecycle archive quá sớm | Restore chậm và tốn retrieval fee | Phân loại dữ liệu theo xác suất truy cập và SLA |
| Migration chỉ copy byte | Mất ACL, metadata, version, consistency hoặc rollback | Inventory, incremental sync và validation đầy đủ |

## 17. Bài thực hành: chọn storage cho hệ thống đa workload

Một nền tảng xử lý nội dung có các chức năng:

- API quản lý tài khoản, đơn hàng và metadata.
- Database giao dịch cần random read/write và khôi phục theo RPO được duyệt.
- Người dùng upload video từ thiết bị di động; file có kích thước từ vài MB đến nhiều GB.
- Worker container xử lý video theo batch và có thể chạy ở nhiều node.
- Một công cụ legacy trên nhiều VM cần cùng nhìn thấy thư mục xuất báo cáo.
- Dữ liệu hoàn tất được giữ lâu dài để phục vụ kiểm toán, nhưng tần suất đọc giảm theo thời gian.

**Yêu cầu bài làm:**

1. Chọn object, block và file storage cho từng dataset; giải thích theo access pattern.
2. Xác định đường upload video bằng signed URL/multipart và cách xác minh checksum, quyền tenant và virus scan.
3. Sizing database volume theo IOPS, throughput, latency và queue depth; ghi rõ giả định tải.
4. Chọn NFS/SMB hoặc giải pháp khác cho thư mục legacy; phân tích locking, metadata và concurrent access.
5. Xây dựng lifecycle hot/warm/archive, retention và retrieval SLA cho video, báo cáo và backup.
6. Thiết kế backup/replication để đáp ứng RPO/RTO, phân biệt snapshot với backup độc lập.
7. Đề xuất mã hóa, IAM, network isolation, audit, key rotation và chính sách xóa theo tenant.
8. Lập bảng TCO gồm dung lượng, IOPS, request, egress, snapshot, archive retrieval và nhân lực vận hành.
9. Viết kế hoạch migration nếu chuyển công cụ legacy từ file share sang object storage; nêu semantics cần thay đổi và điều kiện rollback.

### Gợi ý đánh giá

Một phương án hợp lý có thể dùng database managed với storage do dịch vụ quản lý hoặc block volume phù hợp engine, object storage cho video và tài liệu, file storage cho công cụ legacy cần shared directory. Worker chỉ dùng file storage khi cần thao tác filesystem chia sẻ; nếu các bước xử lý trao đổi object bất biến, object key và manifest có thể đơn giản hơn.

Phần backup phải nêu rõ dữ liệu nào được bảo vệ, bản sao nằm ở đâu, ai có quyền xóa và cách chứng minh restore. Phần chi phí phải tính cả request/retrieval/egress/replication chứ không chỉ GB.

## 18. Checklist trước khi đưa storage vào production

- [ ] Mỗi dataset có owner, classification, retention và yêu cầu nghiệp vụ rõ.
- [ ] Access pattern đã được mô tả: object/key, random/sequential block, file/metadata hoặc mixed.
- [ ] Có số liệu về dung lượng, growth, IOPS, throughput, latency, concurrency và kích thước đơn vị dữ liệu.
- [ ] Storage semantics về consistency, locking, atomicity, rename, overwrite và multi-client đã được xác minh.
- [ ] Block attach/multi-attach và filesystem sharing tuân thủ đúng giới hạn sản phẩm/driver.
- [ ] Object key, bucket/prefix, signed URL, versioning và lifecycle có quy hoạch.
- [ ] File protocol, identity mapping, ACL, locking và network access được kiểm thử.
- [ ] Encryption in transit/at rest, key ownership, rotation và recovery được thiết kế.
- [ ] IAM/ACL theo least privilege; tenant isolation và quyền xóa đã được kiểm tra.
- [ ] Snapshot, backup, replication và PITR được phân biệt; RPO/RTO có owner phê duyệt.
- [ ] Có restore test thực tế với dữ liệu và ứng dụng, không chỉ kiểm tra job backup thành công.
- [ ] Tier/lifecycle phù hợp SLA truy xuất; tính minimum duration, retrieval và early deletion fee.
- [ ] Chi phí gồm storage, performance, request, network, backup, replication, logging và nhân lực.
- [ ] Có benchmark dưới tải thực, gồm peak, concurrency, mixed I/O và tail latency.
- [ ] Migration/cutover có checksum, incremental sync, validation, rollback và kế hoạch xóa dữ liệu cũ.
- [ ] Logs, metrics, quota, capacity alerts và runbook đủ để vận hành, điều tra và phục hồi.

**Ghi nhớ:** Object storage phù hợp dữ liệu được truy cập theo object/key; block storage phù hợp thiết bị I/O ở mức block cho VM, database và workload cần random I/O; file storage phù hợp ứng dụng cần filesystem và namespace chia sẻ. Hãy chọn theo **access pattern và semantics cần bảo toàn**, rồi kiểm chứng bằng benchmark, security review, backup/restore test và tổng chi phí sở hữu. Một kiến trúc tốt có thể kết hợp cả ba loại để mỗi dataset được lưu ở nơi phù hợp với cách nó được tạo, đọc, chia sẻ và phục hồi.
