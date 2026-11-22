# Zonal disks, regional disks và nhu cầu nhân bản trên Google Cloud

> **Chương:** Lưu trữ khối và tệp  
> **Bài học:** Zonal disks, regional disks và nhu cầu nhân bản  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học học cách lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Với máy ảo Compute Engine, một trong những quyết định quan trọng nhất là **đặt dữ liệu trên đĩa ở một zone hay duy trì các bản sao trong hai zone**.

Một ứng dụng Java trên VM có thể khởi động lại từ image, nhưng dữ liệu có trạng thái như tệp upload, transaction log, database và hàng đợi trên ổ đĩa cần chiến lược bảo vệ riêng. **Zonal disk** đáp ứng nhu cầu lưu trữ khối trong một zone; **regional disk** được thiết kế để bảo vệ dữ liệu khối trước sự cố một zone bằng cách **nhân bản đồng bộ** giữa hai zone trong cùng region. Dù vậy, bản sao đĩa **không tự khởi chạy VM dự phòng, không sửa lỗi dữ liệu bị xóa và không thay thế backup**.

Bài học tập trung vào **Persistent Disk** và **Hyperdisk** của Compute Engine, đối chiếu với snapshot, nhân bản bất đồng bộ xuyên region và chiến lược HA/DR ở cấp ứng dụng. Ví dụ sử dụng project, VM, disk và region giả định; kiểm tra danh mục và giới hạn của machine type tại thời điểm triển khai thực tế.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **disk zonal** và **disk regional** về vùng lỗi, vị trí replica và cách VM truy cập dữ liệu.
2. Giải thích cách **Regional Persistent Disk** và **Hyperdisk Balanced High Availability** nhân bản đồng bộ giữa hai zone.
3. Đọc các trạng thái **fully replicated**, **catching up**, **degraded** và hiểu tác động đến khả năng khôi phục.
4. Phân biệt **độ bền dữ liệu**, **tính sẵn sàng**, **RPO**, **RTO**, **backup** và **disaster recovery**.
5. Chọn disk theo yêu cầu ứng dụng Java, file server, database, GKE workload và nhu cầu triển khai đa zone.
6. Tạo, liệt kê, mô tả và gắn disk bằng Google Cloud Console hoặc `gcloud` trong sandbox được phép.
7. Thiết kế failover có **VM dự phòng, fencing, gắn đĩa và phục hồi ứng dụng** thay vì nhầm storage replication với application failover.
8. Xây dựng quy trình snapshot, khôi phục, giám sát, tối ưu chi phí và diễn tập lỗi zone có kiểm soát.

## 2. Những khái niệm cốt lõi

### 2.1. Disk là lưu trữ khối, không phải hệ thống tệp dùng chung

**Block storage** cung cấp thiết bị khối cho hệ điều hành khách (guest OS). Trên Linux, người vận hành thường định dạng `ext4`/`xfs` rồi mount vào thư mục; Windows có thể dùng NTFS/ReFS theo cấu hình. Hệ thống tệp được quản lý bởi OS và ứng dụng phía trên.

| Thuật ngữ | Ý nghĩa | Ví dụ Google Cloud |
|---|---|---|
| **Block storage** | Thiết bị khối gắn vào VM; OS tự tạo filesystem | Persistent Disk, Hyperdisk |
| **File storage** | Chia sẻ tệp/thư mục qua giao thức file như NFS | Filestore |
| **Object storage** | Lưu đối tượng qua API, không phải block device gắn vào VM | Cloud Storage |
| **Zonal disk** | Đĩa lưu trữ ở một zone | Zonal Persistent Disk, zonal Hyperdisk |
| **Regional disk** | Đĩa nhân bản dữ liệu đồng bộ ở **hai zone cùng region** | Regional Persistent Disk, Hyperdisk Balanced High Availability |
| **Snapshot** | Bản lưu theo **thời điểm**, dùng để khôi phục | Standard snapshot/instant snapshot theo loại hỗ trợ |
| **Asynchronous replication** | Sao chép qua khu vực khác với độ trễ sao chép | Hyperdisk asynchronous replication khi loại đĩa hỗ trợ |

**Không nhầm:** Một regional block disk không tự biến thành NFS share cho hàng chục VM. Để nhiều máy đồng thời đọc/ghi tệp, xem xét **Filestore**, dịch vụ file storage phù hợp hoặc cấu hình cluster filesystem chuyên dụng trên loại disk hỗ trợ multiple writers.

### 2.2. Region, zone và failure domain

~~~text
Google Cloud region: asia-southeast1
├── Zone A: asia-southeast1-a
│   ├── VM orders-a
│   └── Replica A của regional disk
├── Zone B: asia-southeast1-b
│   ├── VM orders-b (standby)
│   └── Replica B của cùng regional disk
└── Zone C: asia-southeast1-c
    └── Workloads khác
~~~

**Region** là vùng địa lý gồm nhiều zone. **Zone** là miền triển khai với rủi ro hỏng hóc độc lập ở mức thiết kế. Một **zonal disk** có scope thuộc zone; một **regional disk** có scope thuộc region nhưng được cấu hình **hai replica zone cụ thể**. Việc bạn tạo đĩa regional ở region `asia-southeast1` **không** có nghĩa Google Cloud đặt bản sao ở tất cả zone của region.

### 2.3. Tách compute khỏi storage

Trên Compute Engine, **VM** là tài nguyên tính toán; **Persistent Disk/Hyperdisk** là tài nguyên đĩa có vòng đời riêng và có thể tồn tại khi VM dừng. Tùy cấu hình deletion rule, xóa VM có thể xóa hoặc giữ đĩa gắn kèm. Vì vậy:

- VM chạy ổn định không chứng minh disk có backup.
- Tắt VM không có nghĩa chi phí disk dừng.
- Regional disk còn đầy đủ replica không đồng nghĩa ứng dụng vẫn online nếu VM chính bị lỗi.
- Có snapshot không đồng nghĩa dữ liệu đang được sao chép đồng bộ sau mỗi ghi.

## 3. Zonal disks: phạm vi, ưu điểm và giới hạn

### 3.1. Zonal Persistent Disk

Zonal Persistent Disk là đĩa bền vững được cung cấp trong **một zone**. Các loại phổ biến gồm:

- **`pd-standard`:** HDD-backed, phù hợp nhiều workload ưu tiên dung lượng và khả năng đáp ứng I/O được xác minh.
- **`pd-balanced`:** cân bằng hiệu năng và chi phí, thường là lựa chọn khởi đầu cho boot/data disks.
- **`pd-ssd`:** SSD-backed, phù hợp workload cần hiệu năng đọc/ghi cao hơn.
- **`pd-extreme`:** hỗ trợ provisioned IOPS trong những cấu hình được hỗ trợ; kiểm tra giới hạn hiện hành.

**Zonal Persistent Disk không phải lưu trữ một bản sao đơn lẻ trên một ổ vật lý.** Google Cloud duy trì độ bền trong **cùng zone** theo kiến trúc lưu trữ của dịch vụ. Tuy nhiên, nếu **toàn zone không khả dụng**, workload có thể tạm mất khả năng sử dụng đĩa cho đến khi zone phục hồi hoặc dữ liệu được khôi phục bằng cơ chế khác.

### 3.2. Zonal Hyperdisk

Hyperdisk là họ lưu trữ khối được quản lý có các loại với khả năng cấp phát hiệu năng riêng. Các ví dụ gồm:

- **Hyperdisk Balanced:** zonal, tối ưu cân bằng giá/hiệu năng; **không** tự nhân bản qua zone.
- **Hyperdisk Extreme:** zonal, hướng hiệu năng/IOPS cao theo giới hạn hỗ trợ.
- **Hyperdisk Throughput:** phù hợp throughput tuần tự cao theo yêu cầu.
- **Hyperdisk ML / loại chuyên biệt khác:** cần đối chiếu phạm vi tính năng theo thế hệ.

Để có **nhân bản đồng bộ giữa zone cho Hyperdisk**, chọn **Hyperdisk Balanced High Availability**, không chỉ Hyperdisk Balanced thường. Có thể có cơ chế **nhân bản bất đồng bộ giữa region** cho loại Hyperdisk được hỗ trợ, nhưng đây là thiết kế DR riêng.

### 3.3. Khi nào zonal disk là lựa chọn hợp lý?

| Tình huống | Zonal disk có phù hợp? | Điều kiện |
|---|---|---|
| VM development hoặc CI runner | Thường có | Có thể tái tạo VM; snapshot nếu dữ liệu cần giữ |
| Java API stateless trên MIG | Thường có | State nằm ở Cloud SQL/Cloud Storage/managed services |
| Disk scratch/cache có thể tái tạo | Có thể | Chấp nhận mất dữ liệu cache và thời gian dựng lại |
| Database quan trọng trên một VM | Cần đánh giá thêm | Chỉ zonal có thể không đáp ứng RPO/RTO khi zone lỗi |
| Storage của workload tự replication ở cấp ứng dụng | Có thể | Database/cluster đã có quorum và replica đa zone thực sự |
| Tệp có trạng thái dùng cho nhiều máy ở các zone | Không nên mặc định | Cần filesystem/đồng bộ/chia sẻ dữ liệu phù hợp |

Nếu ứng dụng đã dùng **Cloud SQL HA**, **Spanner** hoặc hệ cơ sở dữ liệu tự quản lý có replication chuẩn, việc thêm replicated disk vào mọi VM có thể gây lãng phí mà không tăng availability tương xứng. Hãy xác định **tầng nào đã bảo vệ dữ liệu** trước.

## 4. Regional disks: bản sao ở hai zone trong cùng region

Hai nhóm sản phẩm chính được thiết kế cho nhân bản đồng bộ giữa zone:

1. **Regional Persistent Disk**: các loại `pd-balanced`, `pd-ssd` và `pd-standard` theo cấu hình được hỗ trợ.
2. **Hyperdisk Balanced High Availability**: loại Hyperdisk có chức năng đồng bộ replica giữa hai zone trong một region, đồng thời có các khả năng provisioned performance và access modes riêng.

~~~mermaid
flowchart LR
    VM["VM chính tại zone A<br/>Ghi dữ liệu"]
    VM --> D["Regional disk<br/>một tài nguyên logic"]
    D --> A["Replica A<br/>zone A"]
    D --> B["Replica B<br/>zone B"]
    B -. "Sẵn sàng cho failover" .-> SB["Standby VM tại zone B"]
    C["Control plane ứng dụng<br/>health check + fencing"] -. "Quyết định chuyển primary" .-> SB
~~~

Từ góc nhìn ứng dụng, một regional disk là **một thiết bị khối logic**. Compute Engine quản lý việc duy trì hai replica ở **các zone đã chỉ định**. Khi hoạt động bình thường, các ghi được nhân bản đồng bộ; **write acknowledgment trong trạng thái fully replicated** chỉ được trả sau khi dữ liệu được ghi bền vững ở cả hai bản sao theo cơ chế dịch vụ.

### 4.1. Primary zone và secondary zone

- **Primary zone:** thường là zone của VM đang gắn đĩa và thực hiện I/O.
- **Secondary zone:** zone còn lại chứa replica được duy trì đồng bộ.
- Hai zone phải thuộc **cùng region** và hỗ trợ loại đĩa/máy tương ứng.
- VM gắn regional disk thông thường cần nằm trong **một trong hai zone replica**; không thể lấy regional disk làm block device tùy ý cho VM ở region khác.
- Chọn zone dự phòng dựa trên khả năng tạo VM, quota, kết nối mạng, định tuyến, storage type và dependency của ứng dụng.

### 4.2. Hỗ trợ VM và access mode khác nhau theo sản phẩm

| Tiêu chí | Regional Persistent Disk | Hyperdisk Balanced High Availability |
|---|---|---|
| Phạm vi | Hai replica zone cùng region | Hai replica zone cùng region |
| Cơ chế | Synchronous replication | Synchronous replication |
| Loại disk | `pd-standard`, `pd-balanced`, `pd-ssd` | `hyperdisk-balanced-high-availability` |
| Machine type | Giới hạn tương thích; tài liệu Regional PD nêu E2, N1, N2, N2D | Danh sách machine types được hỗ trợ riêng |
| Hiệu năng | Phụ thuộc disk type, size, VM machine type | Cấu hình provisioned IOPS/throughput theo giới hạn |
| Gắn một VM đọc/ghi | Trường hợp tiêu biểu | Mặc định `READ_WRITE_SINGLE` |
| Multi-writer | Không đồng nhất giữa disk type/mode; phải xác minh hỗ trợ | Có `READ_WRITE_MANY` khi cấu hình, yêu cầu cluster filesystem và fencing |
| Bảo vệ lỗi zone | Có thể failover tới zone replica khác | Có thể failover; có thêm chế độ cluster đặc biệt |
| Backup/snapshot | Vẫn cần | Vẫn cần |

**Không mặc định:** mọi VM series đời mới đều gắn được regional PD. Có series hỗ trợ zonal Hyperdisk nhưng không hỗ trợ Regional Persistent Disk; cần kiểm tra **machine type × disk type × region** và access mode.

### 4.3. Điều gì *không* xảy ra khi chọn regional disk?

- Không tự tạo VM standby ở zone B.
- Không tự chuyển IP, DNS hoặc load balancer đến zone B.
- Không bảo đảm ứng dụng tự phục hồi crash, kiểm tra database WAL hay sẵn sàng nhận traffic.
- Không tự tạo point-in-time backup cho lỗi xóa nhầm.
- Không sao chép dữ liệu sang **region khác**.
- Không tự cung cấp clustered filesystem để hai VM ghi vào cùng ext4 an toàn.

Synchronous disk replication là **khối xây dựng HA**, không phải dịch vụ HA hoàn chỉnh.

## 5. Trạng thái nhân bản và giới hạn bảo vệ dữ liệu

### 5.1. Trạng thái của replica

| Trạng thái replica | Ý nghĩa |
|---|---|
| **Synced** | Replica sẵn sàng và theo kịp mọi ghi được áp dụng |
| **Catching up** | Replica đang đồng bộ phần dữ liệu còn thiếu |
| **Out of sync** | Replica tạm không khả dụng hoặc không cập nhật theo nội dung đĩa |

Ở cấp disk, tài liệu Google Cloud mô tả các tình trạng:

| Trạng thái disk | Tình trạng | Tác động |
|---|---|---|
| **Fully replicated** | Hai replica đều đồng bộ | Mức bảo vệ lỗi một zone ở trạng thái tốt nhất theo thiết kế |
| **Catching up** | Một replica đang theo kịp bản còn lại | Chưa đạt mức bảo vệ như khi fully replicated |
| **Degraded** | Một replica không cập nhật hoặc không khả dụng | Có thể tiếp tục I/O trên replica còn khỏe, nhưng dự phòng bị suy giảm |

**Điểm kỹ thuật quan trọng:** nếu replication bị mất ở một zone hoặc trễ quá mức, disk có thể chuyển sang `degraded`. Khi đó, **ghi có thể được xác nhận sau khi ghi bền vững ở một replica**, không phải cả hai. Nếu replica khỏe còn lại hỏng trước khi đồng bộ lại, **RPO/RTO không còn được xác định như ở trạng thái healthy**. Không được khẳng định “regional disk luôn RPO=0 trong mọi điều kiện”.

### 5.2. Sự kiện tạo hoặc clone regional disk

Disk được tạo bằng cách **clone** từ zonal disk có thể chưa ở trạng thái đồng bộ đầy đủ ngay tại thời điểm sẵn sàng sử dụng. Google Cloud có thể cần thời gian để bản sao thứ hai **catch up**. Trước khi diễn tập failover hoặc bảo vệ dữ liệu quan trọng, kiểm tra trạng thái replica thực tế và chỉ kết luận mức bảo vệ phù hợp khi đã **fully replicated**.

### 5.3. RPO và RTO

- **Recovery Point Objective (RPO):** mức mất dữ liệu tối đa chấp nhận được, đo theo thời gian (ví dụ mất tối đa 5 phút giao dịch).
- **Recovery Time Objective (RTO):** khoảng thời gian mục tiêu để dịch vụ hoạt động trở lại sau sự cố (ví dụ 15 phút).
- **Durability:** khả năng dữ liệu còn nguyên vẹn khi có lỗi hạ tầng.
- **Availability:** khả năng hệ thống vẫn phục vụ request đúng lúc.

Regional disk fully replicated giúp giảm rủi ro mất dữ liệu do **một zone** lỗi, nhưng **RTO của ứng dụng** còn gồm phát hiện lỗi, quyết định failover, fencing VM cũ, gắn disk, mount filesystem, crash recovery của database, chuyển endpoint và xác minh dịch vụ. Vì vậy, **“đĩa có thể attach nhanh” không đồng nghĩa ứng dụng luôn đạt RTO dưới một phút**.

### 5.4. Ma trận sự cố

| Sự cố | Zonal disk | Regional disk khỏe | Bổ sung bắt buộc |
|---|---|---|---|
| VM OS lỗi trong khi zone vẫn tốt | Disk vẫn còn trong zone | Disk vẫn còn | Reboot/replace VM, ứng dụng khởi động lại |
| Một zone mất hoàn toàn | Disk zonal tại zone đó không truy cập được | Có thể failover đến zone replica còn khỏe | VM standby, orchestrator và return path |
| Replica thứ cấp bị lỗi | Không có replica khác theo vùng | Có thể chuyển degraded/catching up | Cảnh báo, theo dõi healing, snapshot |
| Xóa nhầm dữ liệu từ Linux | Thao tác xóa ghi vào disk | Dữ liệu xóa được **nhân bản đồng bộ** | Snapshot/backup/versioned data |
| Ransomware sửa file | Dữ liệu có thể bị mã hóa | Bản sao cũng nhận thay đổi xấu | Backup độc lập, IAM và bảo vệ recovery |
| Cả region gặp sự cố | Không phục vụ từ region ấy | Hai replica cùng region đều có thể không dùng được | Cross-region DR/backups/asynchronous replication |
| Ứng dụng Java hoặc DB lỗi logic | Không tự sửa | Không tự sửa | Transactional consistency, replay/recovery, deployment rollback |

## 6. Nhân bản dữ liệu khác với sao lưu và disaster recovery

### 6.1. Đồng bộ trong region, không đồng bộ xuyên region

~~~mermaid
flowchart TD
    APP["Ứng dụng cần bảo vệ dữ liệu"]
    APP --> Z{"Mục tiêu lỗi cần chịu?"}
    Z -->|"Hỏng VM, dữ liệu có thể phục hồi sau"| ZON["Zonal disk + snapshot/restore"]
    Z -->|"Hỏng một zone, yêu cầu RPO thấp"| REG["Regional PD / Hyperdisk Balanced HA<br/>Synchronous 2 zones"]
    Z -->|"Hỏng toàn region"| CR["Cross-region backup / Hyperdisk async replication<br/>hoặc app/database replication"]
    REG --> B["Snapshot/backup chống lỗi logic"]
    CR --> T["Diễn tập DR, routing và application recovery"]
    ZON --> B
~~~

- **Synchronous replication:** viết dữ liệu đến hai zone **trong cùng region**, tối ưu bài toán HA một zone khi fully replicated.
- **Asynchronous replication:** duy trì một bản sao tới **region khác** ở chế độ được hỗ trợ, có **replication lag/RPO khác 0** tùy tải và thiết kế.
- **Snapshot:** lưu trạng thái tại thời điểm nhất định để restore; có thể định kỳ hoặc theo yêu cầu, không phải mirror trực tiếp từng ghi.
- **Backup ứng dụng:** có thể là database logical dump, WAL/binlog archive, PITR, immutable backups và quy trình phục hồi phù hợp.

Đối với Hyperdisk, các loại đĩa **Hyperdisk Balanced** và **Hyperdisk Balanced High Availability** có khả năng kết hợp với **Asynchronous Replication** theo giới hạn sản phẩm. Không suy rằng mọi Persistent Disk hoặc mọi series Hyperdisk hỗ trợ cùng một phương án cross-region.

### 6.2. Replication không chữa lỗi dữ liệu logic

Giả sử Java API chạy lệnh SQL xóa nhầm bảng `orders`. Storage đồng bộ sao chép thay đổi ở tầng block sang bản thứ hai. Hai replica có thể nhất quán nhưng cùng chứa **trạng thái sai**. Muốn phục hồi giao dịch cần **backup/snapshot đúng thời điểm, transaction log và quy trình restore**.

Một snapshot được tạo khi database đang chạy có thể chỉ bảo đảm **crash-consistent**, không mặc nhiên **application-consistent**. Với RDBMS, cần xem cơ chế snapshot, freeze/flush, WAL và khuyến nghị của database để có khả năng phục hồi đáng tin cậy.

### 6.3. Khi nào dùng Cloud SQL hoặc Filestore thay vì tự quản lý đĩa?

| Nhu cầu | Phương án đáng xem | Lý do |
|---|---|---|
| PostgreSQL/MySQL/SQL Server cần HA/PITR được quản lý | **Cloud SQL HA** và backup/PITR phù hợp | Google Cloud quản trị nhiều phần của DB/storage failover |
| File share qua NFS cho nhiều VM | **Filestore** tier phù hợp | Cung cấp filesystem dùng chung thay vì block device đơn |
| Object uploads, ảnh/tệp tĩnh, bản build JAR | **Cloud Storage** | API object, versioning/lifecycle và durability |
| Database tự quản lý có trạng thái trên Compute Engine | Regional disk hoặc app replication | Kiểm soát OS/database, tự xây failover và backups |
| Container stateless trên GKE/Cloud Run | Dịch vụ stateful bên ngoài hoặc storage phù hợp | Không giữ dữ liệu quan trọng trong local filesystem không bền vững |

Đối với **GKE**, Kubernetes PersistentVolume/PersistentVolumeClaim và Container Storage Interface driver (CSI) có logic provisioning/attachment riêng. Không tự gắn một regional disk vào hai Pod ở hai zone rồi đồng thời mount ext4 đọc/ghi theo kiểu bình thường; phải kiểm tra access mode, topology, cluster filesystem và cơ chế scheduler/failover.

## 7. Thiết kế HA: regional disk phải đi cùng ứng dụng và compute dự phòng

### 7.1. Ví dụ ứng dụng Java có trạng thái trên VM

Công ty có một **Java Order Processor** lưu dữ liệu công việc cục bộ vào `/var/lib/orders`. Backend nằm trên VM `orders-a` ở `asia-southeast1-a`; zone B có VM standby `orders-b`. Một regional disk `orders-data-regional` được nhân bản giữa hai zone.

~~~mermaid
flowchart TD
    LB["Load balancer / điều phối traffic"]
    A["orders-a (primary) tại zone A<br/>Java process + filesystem mount"]
    B["orders-b (standby) tại zone B<br/>Không mount RW đồng thời"]
    D["Regional disk: orders-data-regional"]
    RA["Replica A tại zone A"]
    RB["Replica B tại zone B"]
    CTRL["HA controller<br/>Health checks + fencing"]
    LB --> A
    LB -. "chuyển khi failover" .-> B
    A <-- "đọc/ghi bình thường" --> D
    D --> RA
    D --> RB
    CTRL -. "chỉ định 1 primary tại một thời điểm" .-> A
    CTRL -. "attach/mount + start service" .-> B
~~~

**Nguyên tắc:** với chế độ **single-writer**, chỉ một VM được sở hữu quyền ghi vào disk. Trên hệ thống có trạng thái, **fencing** phải bảo đảm primary cũ không tiếp tục ghi sau khi standby lên, để tránh **split-brain**.

### 7.2. Cold standby, warm standby và hot standby

| Chế độ | Ý nghĩa | Tác động |
|---|---|---|
| **Cold standby** | Tạo VM sau sự cố | Chi phí compute thấp, RTO có thể cao vì tạo/cấu hình VM |
| **Warm standby** | VM đã tạo nhưng chưa chạy toàn bộ ứng dụng, tùy thiết kế | Cân bằng chi phí và thời gian phục hồi |
| **Hot standby** | VM dự phòng sẵn sàng khởi chạy/recover nhanh | RTO tốt hơn nhưng tốn chi phí và cần kiểm thử |
| **Active–active** | Nhiều VM phục vụ cùng lúc | Không tự dùng một disk single-writer; cần app-level replication/shared storage đúng công nghệ |

Đối với nhiều ứng dụng Java stateless, **regional MIG** và database managed HA thường là lựa chọn đơn giản hơn việc chuyển regional data disk qua lại. Đối với hệ thống stateful không thể đổi sang managed DB, replicated disk có thể là một phần chiến lược HA.

### 7.3. Control plane ứng dụng phải làm gì?

Một **application-specific control plane** hoặc cơ chế orchestrator do doanh nghiệp triển khai cần:

1. Theo dõi tình trạng VM, ứng dụng và disk replica.
2. Phân biệt failure ngắn, network partition và lỗi zone thật.
3. Ngăn primary cũ ghi vào disk khi failover (fencing, cơ chế attach phù hợp).
4. Chọn VM standby nằm trong zone replica còn hoạt động.
5. Attach disk ở chế độ được hỗ trợ, mount filesystem và chạy **crash recovery** của ứng dụng/database.
6. Chuyển traffic qua health check/load balancer/DNS theo thiết kế.
7. Kiểm tra dữ liệu, transaction replay, idempotency và log lỗi trước khi chốt.
8. Có quy trình **failback** khi zone chính phục hồi, tránh hai primary chạy đồng thời.

**Không dùng một script “thấy VM ping không được thì force-attach ngay” trong production.** Thiếu xác minh/fencing có thể gây failover giả và ảnh hưởng dữ liệu.

## 8. Failover, force-attach và split-brain

### 8.1. Normal detach/attach

Nếu zone chính vẫn truy cập được và có thể dừng ứng dụng bình thường:

1. Dừng tiến trình Java/database, flush dữ liệu và ngắt luồng nhận request.
2. Unmount filesystem và detach đĩa trên VM cũ.
3. Attach đĩa regional vào VM standby ở zone còn lại.
4. Mount, kiểm tra filesystem/database recovery, khởi động service.
5. Chuyển traffic và xác minh đường về.

Đây là **planned failover**; thường an toàn hơn force-attach vì hệ điều hành primary có thể dừng ghi trật tự.

### 8.2. Force-attach khi zone không phản hồi

Trong sự cố zone, Compute Engine có cơ chế **force-attach** để gắn regional disk vào VM ở zone replica còn khả dụng **ngay cả khi disk vẫn được ghi nhận là đang gắn ở VM cũ**. Khi hoàn tất, Compute Engine ngăn VM cũ tiếp tục ghi vào regional disk theo cơ chế của dịch vụ.

Tuy nhiên:

- **Chỉ dùng cho disk và access mode được hỗ trợ**; không force-attach zonal disk.
- **Không dùng `--force-attach` cho Hyperdisk Balanced High Availability ở multi-writer mode** (không được hỗ trợ).
- Force-attach **không tự khôi phục filesystem hoặc database**; có thể phải chạy journal replay và kiểm tra nhất quán.
- Không xem force-attach là thao tác bảo dưỡng thông thường hay cách phá khóa khi một VM còn khỏe.
- Sau khôi phục cần kiểm soát chiều **failback**, tránh bật VM cũ với filesystem/application state sai.

Một dạng lệnh theo tài liệu (chỉ để tham khảo trong runbook đã được phê duyệt):

~~~bash
# Thao tác NGUY HIỂM nếu dùng sai ở production.
# Chỉ force attach khi đã xác nhận sự cố, zone và fencing.
gcloud compute instances attach-disk STANDBY_VM \
  --project=PROJECT_ID \
  --zone=REPLICA_ZONE_B \
  --disk=REGIONAL_DISK_NAME \
  --disk-scope=regional \
  --force-attach
~~~

Đây **không phải** bước lab mặc định. Bài thực hành bên dưới chỉ sử dụng attach bình thường và không tạo tình huống giả lập lỗi thật.

### 8.3. RTO thực tế gồm những gì?

~~~text
RTO thực tế ≈ thời gian phát hiện và xác nhận sự cố
            + thời gian chặn primary cũ (fencing)
            + thời gian attach disk vào standby
            + thời gian mount/filesystem replay
            + thời gian DB/ứng dụng khởi động và hồi phục
            + thời gian chuyển endpoint + health check
            + thời gian xác nhận dịch vụ đã hoạt động
~~~

Thời gian attach có thể ngắn hơn một phút trong những điều kiện được tài liệu mô tả, nhưng **không đủ để suy RTO toàn ứng dụng là dưới một phút**. Lựa chọn standby/công cụ phát hiện lỗi và chất lượng automation quyết định phần lớn RTO.

## 9. Chọn loại disk theo hiệu năng, bảo vệ và chi phí

### 9.1. Ma trận quyết định

| Workload / yêu cầu | Zonal Persistent Disk | Regional Persistent Disk | Hyperdisk Balanced HA | Cách tiếp cận bổ sung |
|---|---|---|---|---|
| Dev/test, dữ liệu tái tạo được | Phù hợp | Thường dư nhu cầu | Thường dư nhu cầu | Snapshot định kỳ nếu cần |
| Java stateless sau MIG | Phù hợp cho boot disk từng VM | Không bắt buộc nếu state đã tách | Không bắt buộc | Cloud SQL HA, Cloud Storage |
| Ứng dụng stateful chịu được failover thủ công | Có thể nếu RTO lớn | Phù hợp khi zone outage là rủi ro cần chịu | Xem xét nếu cần hiệu năng cao | Standby VM + runbook |
| Database yêu cầu RPO thấp trước lỗi zone | Khó đạt chỉ bằng zonal | Một khối xây dựng HA | Một khối xây dựng HA | DB recovery, snapshots, fencing |
| Workload IOPS/throughput cao, yêu cầu HA giữa zones | Cần app replication/snapshot | Có thể bị giới hạn bởi performance/type | Cân nhắc theo provisioned performance | Benchmark thực tế |
| Cluster filesystem cần multi-writer | Không mặc định | Không mặc định | Có chế độ `READ_WRITE_MANY` hỗ trợ | Cluster filesystem, quorum, fencing |
| DR khi **toàn region** lỗi | Không đủ | Không đủ | Không đủ nếu chỉ sync trong region | Async replication cross-region + backups |
| Tệp chia sẻ cho nhiều VM qua NFS | Không phải hướng mặc định | Không phải NFS | Không phải NFS | Filestore/file service |

### 9.2. Hiệu năng không chỉ phụ thuộc disk type

Thực tế IOPS, throughput và latency chịu ảnh hưởng bởi:

- Loại đĩa, dung lượng, và provisioned IOPS/throughput nếu là Hyperdisk phù hợp.
- **Machine type** của VM, số vCPU, giới hạn attach và băng thông I/O.
- Thao tác đọc/ghi ngẫu nhiên hay tuần tự, block size và queue depth.
- Latency giữa ứng dụng và replica, đặc tính synchronous replication.
- Filesystem, block cache, RAID/LVM (nếu dùng), database flush/fsync.
- Tải cùng lúc và môi trường đang **degraded/catching up**.

Không lấy IOPS tối đa trong bảng giá làm hiệu năng chắc chắn của mọi VM. **Đo** bằng các công cụ an toàn trên filesystem thử nghiệm và đối chiếu p95/p99 latency của ứng dụng; không chạy benchmark ghi phá dữ liệu trên disk production.

### 9.3. Chi phí replicated disk

Nhân bản hai zone cần hai bản sao dữ liệu, vì vậy **chi phí lưu trữ theo dung lượng của regional Persistent Disk thường xấp xỉ gấp đôi zonal tương đương**, nhưng **tổng hóa đơn không phải cứ nhân hai**: còn VM standby, IOPS/throughput Hyperdisk, snapshot, network, backup và log.

- Zonal `pd-balanced` 200 GiB và regional `pd-balanced` 200 GiB là **hai cấu hình giá khác nhau** theo region/SKU.
- Hyperdisk Balanced HA tính phí theo **dung lượng, provisioned IOPS và throughput** cùng quy tắc sản phẩm; có thể tính phí cả khi không gắn VM.
- VM standby chạy liên tục có chi phí compute khác với standby khởi động theo yêu cầu.
- Backup/snapshot có chi phí lưu trữ và restore/lưu lượng theo chính sách.
- Capacity/reservation và việc chọn zone có thể ảnh hưởng phương án vận hành và ngân sách.

**Không đưa ra một đơn giá USD cố định** nếu chưa biết region, SKU, thời điểm, chương trình chiết khấu, license và giá Hyperdisk provisioned performance. Dùng Google Cloud Pricing Calculator và Billing Reports cho quyết định thực tế.

## 10. Giới hạn kỹ thuật phải kiểm tra trước khi triển khai

| Giới hạn / điều kiện | Ý nghĩa |
|---|---|
| Tương thích **machine type × disk type** | Regional Persistent Disk và Hyperdisk Balanced HA có danh sách VM hỗ trợ khác nhau |
| Replica zones | Phải chỉ định đúng hai zone khác nhau thuộc **cùng region** |
| Kiểu disk regional | `pd-balanced`, `pd-ssd`, `pd-standard` và `hyperdisk-balanced-high-availability` theo loại hỗ trợ |
| Dung lượng | Regional `pd-standard` có mức tối thiểu lớn hơn, ví dụ 200 GiB; các loại khác có giới hạn riêng |
| Read-write access mode | Single writer mặc định; cluster multi-writer cần đĩa/chế độ/filesystem phù hợp |
| Boot disk | Có thể dùng regional disk làm boot disk trong giới hạn; tạo từ image hoặc clone có trạng thái hỗ trợ riêng |
| Resize | Có thể tăng dung lượng, **không giảm trực tiếp**; còn phải mở rộng partition/filesystem trong OS |
| Disk đang catching up | Chưa đạt bảo vệ đầy đủ như trạng thái healthy |
| Zonal availability | Không phải region/zone/machine type nào cũng hỗ trợ mọi cấu hình |
| AI zones | Có giới hạn riêng về regional disks |
| Quota/capacity | Quota còn dư không bảo đảm đủ capacity để tạo VM standby khi zone lỗi |
| IAM | Cần quyền trên cả VM và disk khi tạo/attach/force-attach/snapshot |

Ví dụ tài liệu quản lý regional disks mô tả các kích thước tối thiểu: regional `pd-standard` từ **200 GiB**, regional `pd-balanced` và `pd-ssd` từ **10 GiB**, Hyperdisk Balanced HA từ **4 GiB**. Các mức tối đa, access modes và tính khả dụng cần xem ở trang tài liệu theo phiên bản hiện hành.

## 11. Thực hành A — Quan sát zonal và regional disks bằng gcloud

Các lệnh trong phần này **chỉ đọc**, phù hợp để bắt đầu trên project sandbox đã được phép xem.

~~~bash
# Xác nhận danh tính và project.
gcloud auth list
gcloud config get-value project

# Liệt kê disks trong project: gồm disk zonal và regional có quyền xem.
gcloud compute disks list --project=PROJECT_ID

# Thông tin một zonal disk.
gcloud compute disks describe ZONAL_DISK_NAME \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a

# Thông tin một regional disk.
gcloud compute disks describe REGIONAL_DISK_NAME \
  --project=PROJECT_ID \
  --region=asia-southeast1

# Xem VM primary, đĩa gắn và trạng thái.
gcloud compute instances describe PRIMARY_VM \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --format="yaml(name,status,disks,machineType,networkInterfaces)"
~~~

Khi xem regional disk, chú ý:

- `name`, `sizeGb`, `type`, `region` và danh sách **replicaZones**.
- VM nào đang gắn đĩa (trường `users` hoặc thông tin attachment).
- Access mode, khả năng multi-writer nếu thuộc loại Hyperdisk hỗ trợ.
- Các trạng thái phục vụ replication/replica nếu API/Monitoring đang cung cấp.
- Chính sách snapshot và dữ liệu phục hồi có phù hợp với yêu cầu RPO/RTO không.

Một output JSON minh họa (chỉ để diễn giải, không phải response đầy đủ):

~~~json
{
  "name": "orders-data-regional",
  "sizeGb": "100",
  "type": "projects/example-lab/zones/asia-southeast1-a/diskTypes/pd-balanced",
  "region": "projects/example-lab/regions/asia-southeast1",
  "replicaZones": [
    "projects/example-lab/zones/asia-southeast1-a",
    "projects/example-lab/zones/asia-southeast1-b"
  ]
}
~~~

**Lưu ý:** API thực tế có thể biểu diễn `type` và các trường bằng URL/URI khác nhau; đừng dựa vào JSON minh họa để parser chính sách. Điều cần xác định là **disk thực sự regional với hai replica zones**.

## 12. Thực hành B — Tạo và gắn disk trong sandbox

**Các lệnh dưới đây thay đổi tài nguyên thật và phát sinh phí**. Chỉ dùng trên project sandbox, không chạy ở production khi chưa có change ticket, backup và người phê duyệt. Các VM tham chiếu được giả định **đã tồn tại**, máy chính thuộc zone A, standby thuộc zone B, và đã kiểm tra machine type tương thích.

### 12.1. Tạo zonal Persistent Disk

~~~bash
gcloud compute disks create orders-zonal-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --type=pd-balanced \
  --size=100GB
~~~

Đĩa này nằm trong một zone. Nó có thể có cơ chế đảm bảo durability **bên trong zone**, nhưng không tự có replica ở `asia-southeast1-b`.

### 12.2. Tạo regional Persistent Disk

~~~bash
gcloud compute disks create orders-data-regional \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --replica-zones=asia-southeast1-a,asia-southeast1-b \
  --type=pd-balanced \
  --size=100GB
~~~

**Kiểm tra trước khi chạy:**

1. `PROJECT_ID` đúng project sandbox, hai replica zones được hỗ trợ.
2. `pd-balanced` regional hỗ trợ machine type của VM dự kiến.
3. Disk name chưa được sử dụng trong scope tương ứng.
4. Người vận hành có quyền quản trị disk theo IAM tối thiểu và đủ quota.
5. Chấp nhận chi phí của replicated disk và có kế hoạch xóa.

### 12.3. Tạo Hyperdisk Balanced High Availability

Ví dụ lệnh nền tảng:

~~~bash
gcloud compute disks create orders-hd-ha-lab \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --replica-zones=asia-southeast1-a,asia-southeast1-b \
  --type=hyperdisk-balanced-high-availability \
  --size=100GB
~~~

Loại Hyperdisk này có quy tắc IOPS/throughput và machine types được hỗ trợ. Lệnh ở trên để minh họa **cấu trúc region/replica/type**, sử dụng giá trị performance mặc định. Nếu cần workload thực, phải thiết kế và đặt `--provisioned-iops`/`--provisioned-throughput` theo khả năng/CLI hiện hành và dự toán chi phí.

### 12.4. Xem và gắn regional disk

~~~bash
gcloud compute disks describe orders-data-regional \
  --project=PROJECT_ID \
  --region=asia-southeast1

# Chỉ gắn vào VM trong một trong hai replica zones và đúng disk compatibility.
gcloud compute instances attach-disk PRIMARY_VM \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --disk=orders-data-regional \
  --disk-scope=regional \
  --device-name=orders-data
~~~

Sau khi attach, disk là block device của VM nhưng **chưa tự có filesystem hoặc mount point**.

### 12.5. Trên Linux: nhận diện và mount an toàn

**Cảnh báo:** `mkfs` **xóa cấu trúc filesystem cũ**. Chỉ format nếu chắc chắn disk mới **trống**, đúng disk ID, và không chứa dữ liệu cần giữ. Đối với disk đang dùng hoặc được restore, **không chạy mkfs**.

~~~bash
# Quan sát bên trong VM.
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
sudo blkid

# Kiểm tra đường symlink và thiết bị thực tế được Compute Engine cung cấp.
ls -l /dev/disk/by-id/ | grep orders-data || true

# CHỈ KHI đã chắc chắn đây là disk blank của sandbox:
# sudo mkfs.ext4 -F /dev/disk/by-id/google-orders-data

# Mount disk đã có filesystem (hoặc vừa được format an toàn).
sudo mkdir -p /srv/orders-data
# sudo mount /dev/disk/by-id/google-orders-data /srv/orders-data

# Kiểm tra mount trước khi ứng dụng viết.
findmnt /srv/orders-data || true
~~~

Đường `/dev/disk/by-id/google-orders-data` là minh họa theo `--device-name=orders-data`; kiểm tra đường thực tế trước khi thao tác. Khi cần mount sau reboot, dùng **UUID** trong `/etc/fstab` hoặc unit mount được quản lý và kiểm tra tùy chọn `nofail`/dependencies theo thiết kế. Không tự copy tên `/dev/sdb` vì thứ tự thiết bị có thể thay đổi.

### 12.6. Khôi phục sau Planned Failover

Với single-writer disk:

1. Đưa API/db vào maintenance, dừng nhận request ghi.
2. Flush transaction, dừng service, unmount tại VM chính.
3. Detach disk (thao tác cloud).
4. Attach disk vào standby trong zone replica thứ hai.
5. Kiểm tra thiết bị, mount filesystem **không format**, thực hiện crash recovery nếu cần.
6. Chạy ứng dụng, health check, chuyển traffic và kiểm tra dữ liệu.
7. Ghi nhận RTO đo được và kế hoạch failback.

Không thử `force-attach` khi VM còn chạy bình thường hoặc khi không có điều kiện xác nhận fencing.

## 13. Phân tích bài toán Java: trạng thái nên nằm ở đâu?

### 13.1. Case study: Orders API trên Compute Engine

Giả sử một ứng dụng Java có:

- **REST API:** Stateless, nhiều VM phía sau load balancer.
- **Order database:** PostgreSQL cần bảo vệ giao dịch.
- **Upload invoice PDF:** nhiều API instance phải truy cập chung.
- **Cache:** dữ liệu có thể tái tạo.
- **Job runner:** xử lý queue và checkpoint công việc.

| Thành phần | Nên lưu ở đâu? | Vì sao |
|---|---|---|
| JAR/container và cấu hình không nhạy cảm | Artifact Registry hoặc image/instance template | Triển khai lại được; không cần shared regional data disk |
| Dữ liệu order giao dịch | Cloud SQL HA hoặc DB tự quản lý có HA đúng chuẩn | Bảo vệ transaction/backup/PITR |
| File invoice PDF | Cloud Storage với kiểm soát IAM và dữ liệu | Nhiều VM truy cập qua object API, không gắn chung block device |
| Cache | Memorystore hoặc cache nội bộ theo yêu cầu | Có thể tái tạo, không cần replication block vô điều kiện |
| Job checkpoint không được mất | Database/Cloud Storage hoặc persistent disk đúng RPO | Phải định nghĩa replay/idempotency |
| Log ứng dụng | Cloud Logging với cấu hình phù hợp | Theo dõi tập trung khi VM failover hoặc bị xóa |

**Kết luận kiến trúc:** phần lớn API Java hiện đại cần **tách state khỏi VM**, hơn là đặt tất cả dữ liệu vào một regional disk rồi chuyển VM qua zone khác.

### 13.2. Khi nào thật sự cần regional disk?

Có thể phù hợp nếu ứng dụng:

- Phụ thuộc filesystem/block device cụ thể và không dễ chuyển lên database/object storage.
- Cần một disk volume duy nhất mà một VM primary đọc/ghi, có standby tại zone khác.
- Có runbook hoặc bộ điều phối failover, fencing và recovery đã được kiểm thử.
- Cần RPO thấp trong lỗi một zone và chấp nhận chi phí replicated storage.
- Không đòi hỏi **active–active ghi đồng thời** nếu đang dùng chế độ single-writer.

Nếu yêu cầu “các Pod GKE ở hai zone cùng ghi vào một thư mục” hoặc “các VM chạy đồng thời trên cùng ext4”, nhu cầu đã chuyển thành **shared file system/cluster filesystem**; chọn **Filestore** hoặc sản phẩm/chế độ multi-writer phù hợp thay vì ép regional block disk giải quyết bài toán sai.

## 14. Sao lưu, nhất quán dữ liệu và phục hồi

### 14.1. Snapshot theo lịch và restore thử

Một kế hoạch tối thiểu gồm:

1. Xác định **RPO ứng dụng**: dữ liệu có thể mất tối đa bao lâu?
2. Chọn chu kỳ snapshot hoặc backup database theo RPO và dữ liệu thay đổi.
3. Xác định **location/retention** của bản sao theo chính sách và ràng buộc tuân thủ.
4. Thiết lập quyền tạo/xóa snapshots khác với quyền của ứng dụng khi có thể.
5. Bảo vệ dữ liệu backup khỏi việc xóa trái phép và giám sát backup thất bại.
6. **Diễn tập restore sang disk/VM thử nghiệm**, kiểm tra file/checksum/database consistency.
7. Ghi thời gian restore thực tế vào kết quả RTO, không chỉ thời gian API tạo disk.

### 14.2. Ví dụ snapshot read-back

Lệnh tạo snapshot (thao tác ghi tài nguyên):

~~~bash
# Ví dụ snapshot của regional disk; cần quyền và kế hoạch nhất quán DB.
gcloud compute snapshots create orders-data-snap-lab \
  --project=PROJECT_ID \
  --source-disk=orders-data-regional \
  --source-disk-region=asia-southeast1
~~~

Để kiểm tra snapshot sau tạo:

~~~bash
gcloud compute snapshots describe orders-data-snap-lab \
  --project=PROJECT_ID \
  --format="yaml(name,status,diskSizeGb,creationTimestamp,sourceDisk)"
~~~

Nếu đang dùng database, xem hướng dẫn bảo đảm **application consistency** và chỉ kết luận snapshot có thể khôi phục sau khi test restore, không chỉ thấy trạng thái snapshot đã tạo.

### 14.3. Xây dựng chính sách dữ liệu 3 lớp

| Lớp | Mục tiêu | Công cụ |
|---|---|---|
| **HA trong region** | Giảm mất dịch vụ khi một zone lỗi | Regional disk + VM standby/failover hoặc managed HA |
| **Backup độc lập** | Khôi phục sau xóa nhầm/ransomware/logic lỗi | Snapshot, database backup/PITR, retention |
| **DR xuyên region** | Ứng phó lỗi region hoặc thiên tai | Cross-region backups, async replication hoặc app replication |

Ba lớp bổ trợ, không thay thế nhau. Khi yêu cầu bảo vệ dữ liệu cao, còn cần **kiểm soát quyền**, encryption/KMS theo chính sách, chống chỉnh sửa backup và kế hoạch ứng phó sự cố an ninh.

## 15. Monitoring và chẩn đoán replica state

### 15.1. Các chỉ số cần quan sát

| Nhóm | Tín hiệu | Cảnh báo gợi ý |
|---|---|---|
| Replication | Replica state `Synced/Catching up/Out of sync` | Không còn `Fully replicated` kéo dài |
| Disk availability | Đĩa không attach/không đọc ghi được | Primary mất quyền ghi hoặc attach lỗi |
| Storage performance | IOPS, throughput, latency và throttling | DB p99 latency tăng do disk |
| Dung lượng | Filesystem gần đầy, tốc độ tăng sử dụng | Đầy `/var/lib/orders`, lỗi write |
| VM/zone | VM state, zone outage, health check failure | Kích hoạt điều tra hoặc failover đã phê duyệt |
| Ứng dụng | 5xx, DB connection error, WAL replay | Dịch vụ chưa phục hồi dù disk attach xong |
| Backup | Snapshot thất bại, thời gian từ snapshot thành công gần nhất | RPO backup bị vượt |
| Chi phí | Phí regional disk, Hyperdisk IOPS/throughput, standby VM | Vượt dự toán hoặc tài nguyên bị bỏ quên |

Có thể dùng **Cloud Monitoring metrics** và thông tin disk/replica state được Compute Engine cung cấp; tên metric cụ thể cần tra tài liệu hiện hành theo loại disk. Khi triển khai alert, kiểm tra quyền truy cập, chu kỳ xuất dữ liệu và sự khác biệt giữa các loại đĩa.

### 15.2. Tình huống A — Disk regional đang degraded

**Triệu chứng:** App vẫn ghi được nhưng dashboard báo replica B `Out of sync`, disk `Degraded`.

**Diễn giải đúng:**

- Không kết luận ngay dữ liệu đã mất.
- Dự phòng không còn đạt mức **fully replicated**; nếu replica A cũng hỏng trong lúc này, data availability và RPO/RTO có thể không xác định.
- Theo dõi quá trình tự phục hồi; kiểm tra sự cố zone/replica, workload write và trạng thái mới.
- Xem xét **snapshot** từ replica còn khỏe theo hướng dẫn nếu tình trạng kéo dài và ảnh hưởng mục tiêu RPO.
- **Không chủ động force-attach** vào replica đang out-of-sync khi không có quy trình và bằng chứng phù hợp.

### 15.3. Tình huống B — VM không tạo được ở zone dự phòng

Đĩa vẫn fully replicated, nhưng khi primary zone mất, tạo standby VM ở secondary zone báo thiếu capacity.

**Nguyên nhân:** đĩa đã có hai replica nhưng compute capacity cho VM standby chưa được bảo đảm. Bài học về HA là phải thiết kế **đủ cả storage và compute**, quota, service account, network, dependency, image và capacity/quy trình đặt trước tài nguyên khi phù hợp.

### 15.4. Tình huống C — Ứng dụng báo dữ liệu sai sau restore

Snapshot restore thành công về mặt API nhưng database không khởi động hoặc không thấy giao dịch mới nhất.

**Khả năng:**

- Snapshot cũ hơn yêu cầu RPO.
- Database chưa flush/checkpoint, cần replay WAL/transaction logs.
- Snapshot không application-consistent.
- App dùng thêm object storage, secret hoặc database phụ không cùng thời điểm.
- Quy trình rollback code và database schema không tương thích.

**Bài học:** một bản snapshot tồn tại không đồng nghĩa **khôi phục hệ thống đạt mục tiêu**. Phải kiểm thử từ tầng application.

## 16. Runbook: khi nào chuyển sang zone dự phòng?

### 16.1. Điều kiện kích hoạt

Chỉ kích hoạt failover khi có tín hiệu phù hợp:

- VM/API health checks lỗi kéo dài theo ngưỡng đã định.
- Zone primary hoặc compute không khả dụng và không tự phục hồi trong khung chấp nhận.
- Secondary replica có trạng thái cho phép failover an toàn.
- Bộ điều phối có thể ngăn split-brain.
- Có instance standby tương thích và đường traffic/database/network tại zone B.

### 16.2. Trình tự tham chiếu

~~~text
[1] Xác nhận tác động và mức sự cố
       |
       v
[2] Kiểm tra disk state + replica state
       |
       v
[3] Kiểm tra standby VM/capacity/quota/zone
       |
       v
[4] Fencing hoặc ngăn ghi từ primary cũ
       |
       v
[5] Detach/attach, hoặc force-attach khi thực sự cần
       |
       v
[6] Mount filesystem (KHÔNG FORMAT), recover DB/app
       |
       v
[7] Health check + kiểm tra dữ liệu + chuyển traffic
       |
       v
[8] Monitor + ghi bằng chứng + chuẩn bị failback
~~~

Phân công rõ: **incident commander** quyết định failover, **storage/compute owner** vận hành disk/VM, **application owner** kiểm tra dữ liệu, **network owner** xác minh route/load balancer, **security** kiểm tra hành vi bất thường và quyền. Với production, diễn tập ở sandbox để tìm lỗi quyền IAM, mount device, script và load balancer trước khi sự cố xảy ra.

### 16.3. Failback sau khi zone chính phục hồi

Failback cũng là một quá trình chuyển primary:

1. Không cho phép VM cũ tự động khởi chạy ứng dụng với quyền ghi trên dữ liệu cũ.
2. Xác định trạng thái disk fully replicated, các replica đã bắt kịp.
3. Chọn cửa sổ thay đổi hoặc failback có điều phối.
4. Dừng/flush ứng dụng ở primary hiện tại, fencing, detach/attach về zone đích.
5. Phục hồi ứng dụng và traffic; kiểm tra giao dịch, latency và backup.
6. Bảo đảm chỉ một primary đang ghi (trừ khi dùng cluster multi-writer được thiết kế đúng).

**Không tạo hai “primary” bằng cách khởi động cả hai VM với filesystem ext4 của cùng một disk** trong mô hình single-writer.

## 17. Bài tập thiết kế và tự đánh giá

### Bài 1 — Chọn zonal hay regional

Một ứng dụng Java stateless chạy trên **regional MIG** ở ba zone. Dữ liệu order nằm trong Cloud SQL HA, file ảnh ở Cloud Storage. Mỗi VM chỉ lưu cache và log tạm.

**Câu hỏi:** Có cần regional Persistent Disk cho từng VM không? Vì sao? Quy trình backup nên đặt ở đâu?

**Gợi ý:** Không nhất thiết. Khi state đã tách khỏi VM và các VM tái tạo được, zonal boot disk là lựa chọn thường phù hợp. Backup/PITR đặt ở database và object data theo yêu cầu.

### Bài 2 — RPO và RTO

Một dịch vụ kế toán tự quản lý database trên Compute Engine cần chịu được **một zone lỗi** với RPO mục tiêu gần 0 và RTO tối đa 15 phút. Đội dự định mua regional disk nhưng không tạo VM standby.

**Câu hỏi:** Thiếu những thành phần gì? Nếu zone B đang catching up thì còn có thể hứa RPO gần 0 vô điều kiện không?

**Gợi ý:** Cần compute standby/capacity, health checks, fencing, attach/mount, DB crash recovery, traffic switch và diễn tập. Khi replica degraded/catching up, mức bảo vệ đã giảm.

### Bài 3 — Nhân bản và xóa nhầm dữ liệu

Một nhân viên vô tình xóa thư mục `/var/lib/invoices` trên regional disk. Đĩa ở trạng thái fully replicated.

**Câu hỏi:** Replica B có dữ liệu trước khi xóa không? Phương án khôi phục phù hợp là gì?

**Gợi ý:** Xóa được nhân bản, không thể mặc định phục hồi từ replica B. Dùng snapshot/backup/versioning và đánh giá thời điểm restore phù hợp.

### Bài 4 — Thiết kế DR nhiều region

Dữ liệu giao dịch quan trọng phải phục hồi ngay cả khi **region A mất hoàn toàn**. Nhóm đã dùng regional disk với hai replica zone trong region A.

**Câu hỏi:** Tại sao chưa đạt yêu cầu? Phải bổ sung gì?

**Gợi ý:** Hai bản sao vẫn nằm trong cùng region. Xây dựng cross-region replication/backups, site standby, DNS/routing, data consistency, RPO/RTO và diễn tập DR.

### Bài 5 — Multi-writer

Hai VM muốn **đồng thời** ghi cùng một tập tin ext4, một VM ở zone A và một VM ở zone B. Một kỹ sư gợi ý bật `READ_WRITE_MANY` ở Hyperdisk Balanced HA và mount ext4 bình thường.

**Câu hỏi:** Có an toàn không? Những cơ chế nào còn thiếu?

**Gợi ý:** Không nên dùng ext4 như clustered filesystem đồng thời. Cần cluster-aware filesystem hoặc ứng dụng được thiết kế cho shared block, lock manager/quorum/fencing và hỗ trợ tính năng sản phẩm.

### Bài 6 — Tối ưu chi phí

Một hệ thống development nhỏ chạy VM một zone, dữ liệu có thể tạo lại từ Artifact Registry và Cloud Storage. Đội muốn dùng disk regional vì nghe rằng “regional luôn tốt hơn”.

**Câu hỏi:** So sánh phương án zonal + snapshot với regional + standby. Chi phí và độ tin cậy nào thật sự cần?

**Gợi ý:** Chọn dựa trên tác động downtime, RPO/RTO, số tiền có thể chi và chiến lược phục hồi; replicated disk có thể dư thừa trong bài toán dev.

### Bài 7 — Khắc phục disk không attach được

Bạn gọi:

~~~bash
gcloud compute instances attach-disk orders-b \
  --project=PROJECT_ID \
  --zone=asia-southeast1-c \
  --disk=orders-data-regional \
  --disk-scope=regional
~~~

Disk có replica ở `asia-southeast1-a` và `asia-southeast1-b`.

**Câu hỏi:** Vấn đề đầu tiên là gì? Có nên thử `--force-attach` không?

**Gợi ý:** Zone C không thuộc hai replica zones; VM chưa đáp ứng điều kiện attachment. `--force-attach` không sửa lỗi topology.

## 18. Checklist trước khi đưa regional disk lên production

- [ ] Đã ghi rõ workload, thành phần stateful, người sở hữu data và **RPO/RTO**.
- [ ] Đã xác định lỗi cần chịu: VM, zone hay **toàn region**.
- [ ] Đã so sánh zonal Persistent Disk, zonal Hyperdisk, Regional Persistent Disk, Hyperdisk Balanced HA và dịch vụ managed.
- [ ] Đã kiểm tra machine type × disk type × region × replica zones × access mode.
- [ ] Đã xác định single-writer hay cluster multi-writer; có fencing/quorum nếu cần.
- [ ] Đã kiểm tra VM standby, image, quota, capacity, VPC, IAM và đường traffic.
- [ ] Đã có application-specific failover controller/runbook được thử nghiệm.
- [ ] Đã hiểu `fully replicated`, `catching up`, `degraded` và cảnh báo theo replica state.
- [ ] Đã kiểm tra filesystem/database recovery, integrity, WAL, crash consistency.
- [ ] Đã tạo snapshot/backup độc lập và thử **restore**, không coi replication là backup.
- [ ] Đã có kế hoạch cross-region DR nếu requirement bao gồm lỗi region.
- [ ] Đã đo IOPS, throughput, p95 latency của ứng dụng và quan sát giới hạn VM.
- [ ] Đã kiểm tra giá provisioned storage/IOPS/throughput, standby, backup và logging.
- [ ] Đã có quy trình planned failover, emergency force-attach khi được phê duyệt và failback.
- [ ] Đã bảo vệ dữ liệu bằng IAM tối thiểu, encryption/KMS đúng chính sách và audit.
- [ ] Đã thử cleanup trong sandbox, kiểm tra deletion rule và disk tiếp tục tính phí khi VM dừng.

## 19. Tài liệu Google Cloud chính thức

Các giới hạn, khả năng machine type và tên lệnh có thể thay đổi theo phiên bản. Trước khi thực hiện trên project thật, đối chiếu tài liệu:

- [Persistent Disk overview](https://docs.cloud.google.com/compute/docs/disks/persistent-disks)
- [Google Cloud Hyperdisk overview](https://docs.cloud.google.com/compute/docs/disks/hyperdisks)
- [Create and manage regional disks](https://docs.cloud.google.com/compute/docs/disks/regional-persistent-disk)
- [About synchronous disk replication](https://docs.cloud.google.com/compute/docs/disks/about-regional-persistent-disk)
- [Manage failures for regional disks](https://docs.cloud.google.com/compute/docs/disks/repd-failover)
- [Build HA services using synchronously replicated disks](https://docs.cloud.google.com/compute/docs/disks/high-availability-regional-persistent-disk)
- [About Hyperdisk Balanced High Availability](https://docs.cloud.google.com/compute/docs/disks/hd-types/hyperdisk-balanced-ha)
- [Disk data protection](https://docs.cloud.google.com/compute/docs/disks/data-protection)
- [Attach disks to VM](https://docs.cloud.google.com/compute/docs/disks/attach-disks)
- [gcloud compute disks create](https://docs.cloud.google.com/sdk/gcloud/reference/compute/disks/create)
- [gcloud compute instances attach-disk](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances/attach-disk)
- [Compute Engine disk pricing](https://cloud.google.com/compute/disks-image-pricing)
- [Filestore overview](https://cloud.google.com/filestore/docs/overview)

**Điểm cần nhớ:** **Zonal disks** phù hợp khi dữ liệu có thể khôi phục hoặc ứng dụng tự quản lý replication; **regional disks** là công cụ nhân bản đồng bộ ở **hai zone trong cùng region**, giúp xây dựng dịch vụ chịu lỗi zone khi được kết hợp với **VM standby, fencing, failover và khôi phục ứng dụng**. Dù ở trạng thái **fully replicated**, regional disk **không thay backup** và **không bảo vệ lỗi toàn region**. Một quyết định lưu trữ tốt phải dựa trên **RPO/RTO, loại dữ liệu, hiệu năng, khả năng vận hành và tổng chi phí**, không chỉ tên gọi của disk.
