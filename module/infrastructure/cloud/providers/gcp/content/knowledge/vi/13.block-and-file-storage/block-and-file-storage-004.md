# Local SSD và quản lý dữ liệu tạm thời trên Google Cloud

> **Chương:** Lưu trữ khối và tệp  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Khi xử lý một tập dữ liệu lớn trên Compute Engine, thời gian đọc ghi tệp trung gian có thể chiếm phần đáng kể của công việc. **Local SSD** là dạng lưu trữ khối hiệu năng cao gắn trực tiếp với máy chủ vật lý đang chạy VM, rất thích hợp cho **cache, scratch space, dữ liệu trung gian và các thành phần có thể tái tạo**. Nhưng hiệu năng cao đi cùng một đánh đổi cốt lõi: **không được xem Local SSD là nơi lưu bản dữ liệu duy nhất**.

Bài này hướng dẫn cách nhận diện workload phù hợp, tạo và gắn Local SSD vào Compute Engine, chuẩn bị filesystem an toàn, xử lý tình huống VM reboot/stop/host failure, xây dựng cơ chế cache/checkpoint có thể phục hồi và theo dõi hiệu năng cùng chi phí. Với GKE hoặc các hệ thống Java chạy trên GCP, bài cũng chỉ ra ranh giới giữa **local ephemeral storage** và **durable storage**.

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích khác biệt giữa **Local SSD**, **Titanium SSD**, **Persistent Disk**, **Hyperdisk**, **Filestore** và **Cloud Storage**.
2. Lựa chọn Local SSD cho cache/scratch, biết những dữ liệu tuyệt đối không nên chỉ đặt trên Local SSD.
3. Hiểu cách Local SSD được cấp phát theo machine series, thiết bị **NVMe/SCSI** và giới hạn không thể thêm disk sau khi tạo VM.
4. Kiểm tra thiết bị trước khi **format, mount, RAID 0**, tránh ghi đè boot/data disks.
5. Lập ma trận về vòng đời Local SSD qua **guest reboot, live migration, host error, stop, suspend, Spot preemption và delete**.
6. Thiết kế **read-through cache, checkpoint, replicated state, retry và khôi phục sau mất dữ liệu**.
7. Theo dõi IOPS, throughput, latency, dung lượng, hành vi REPAIRING và chi phí Local SSD.
8. Vận dụng kiến thức trong một tình huống Java batch processing trên Compute Engine và các workload GKE.

## 1. Local SSD là gì?

**Local SSD** trong Compute Engine là ổ lưu trữ khối tốc độ cao **gắn trực tiếp với host vật lý** nơi VM chạy. Không giống Persistent Disk hoặc Hyperdisk là những loại lưu trữ bền vững có cơ chế tách khỏi host VM, Local SSD gần tài nguyên CPU hơn, cho **độ trễ thấp và IOPS/throughput cao** trong điều kiện thích hợp.

~~~mermaid
flowchart LR
    subgraph HOST["Host vật lý chạy Compute Engine VM"]
      VM["VM / Java workload"]
      LOCAL["Local SSD / Titanium SSD\nScratch và cache"]
      VM <-->|"Đọc ghi khối tại host"| LOCAL
    end
    VM <-->|"Lưu dữ liệu bền vững"| PD["Persistent Disk / Hyperdisk"]
    VM <-->|"Object API qua mạng"| GCS["Cloud Storage"]
    VM <-->|"File share qua mạng"| FS["Filestore"]
~~~

Các đặc điểm quan trọng:

- **Dữ liệu tạm thời:** bản trên Local SSD có thể bị mất khi VM/host thay đổi trạng thái hoặc xảy ra lỗi; không có bản sao tự động bảo đảm tồn tại độc lập.
- **Không phải boot disk:** Local SSD không dùng làm disk khởi động VM.
- **Cấp cùng VM:** chỉ có thể thêm Local SSD khi **tạo VM**; không thể gắn thêm Local SSD vào một VM đã tạo như persistent disk. Với machine series phù hợp, số lượng hoặc dung lượng đi cùng loại máy.
- **Không có snapshot/clone/machine image backup trực tiếp:** phải **sao chép dữ liệu cần giữ** sang Hyperdisk, Persistent Disk, Cloud Storage hoặc kho bền vững trước.
- **Không tự chia sẻ giữa nhiều VM:** filesystem trên một Local SSD được mount bên trong VM, không tương đương Filestore hoặc một shared block service.
- **Giới hạn loại máy:** không phải mọi machine series, instance shape, OS image và disk interface đều hỗ trợ.

### 1.1. Local SSD là dạng ephemeral block storage

Hai từ khóa cần hiểu riêng:

- **Block storage:** hệ điều hành nhìn thấy thiết bị khối như NVMe hoặc SCSI; người vận hành có thể tạo filesystem ext4/XFS, volume manager hoặc mount vào một thư mục.
- **Ephemeral:** vòng đời dữ liệu **không độc lập và không được bảo đảm bền vững** như một volume lưu trữ dài hạn.

Có thể tạo filesystem, tệp thông thường và thư mục trên Local SSD, nhưng điều đó **không biến nó thành dịch vụ file storage bền vững**. Khi VM biến mất hoặc Local SSD bị cấp lại thành thiết bị trắng, toàn bộ cấu trúc filesystem có thể không còn.

### 1.2. Phân biệt Local SSD và Titanium SSD

Google Cloud cung cấp nhiều thế hệ ổ cục bộ:

| Thuộc tính | Local SSD truyền thống | Titanium SSD |
|---|---|---|
| Khái niệm | SSD cục bộ gắn host | Thế hệ SSD cục bộ sử dụng kiến trúc Titanium I/O offload |
| Mục tiêu | Hiệu năng cao cho dữ liệu tạm | Hiệu năng cao hơn trên các machine series được hỗ trợ |
| Dung lượng | Nhiều loại VM dùng từng ổ **375 GiB** | Kích thước và số lượng thay đổi theo machine series |
| Interface | NVMe hoặc SCSI tùy machine/OS | Theo máy hỗ trợ, thông thường NVMe |
| Cấp phát | Một số máy chọn số ổ, một số máy có sẵn | Thường gắn theo machine type |
| Bền vững | Không bảo đảm | Không bảo đảm |
| Tùy chọn preserve khi stop/suspend (Preview) | Có trong những cấu hình được hỗ trợ | **Không hỗ trợ** |
| Phù hợp | Cache, scratch, I/O trung gian | Cache/scratch, tác vụ I/O nặng theo khả năng máy |

Không khẳng định mọi ổ Local SSD trên GCP đều có **375 GiB**: nhiều cấu hình Titanium SSD hiện có dung lượng mỗi disk khác, có thể tới hàng TiB. Khi lập chi phí và phân vùng phải lấy dung lượng **thực tế theo machine type**.

## 2. So sánh các lựa chọn lưu trữ

| Dịch vụ | Mô hình truy cập | Mức bền vững | Điển hình |
|---|---|---|---|
| **Local SSD / Titanium SSD** | Block device cục bộ bên trong VM | Ephemeral, không bảo đảm khi mất host/stop | Cache, sort/spill, batch scratch, dữ liệu có thể tái tạo |
| **Persistent Disk** | Block volume qua hạ tầng lưu trữ | Bền vững, tồn tại độc lập với VM theo chính sách | Boot disk, data disk, ứng dụng cần lưu file bền |
| **Hyperdisk** | Block volume với khả năng hiệu năng theo loại | Bền vững, hiệu năng/tính năng tùy loại | Database, ứng dụng có nhu cầu IOPS/throughput xác định |
| **Filestore** | Managed NFS file share qua mạng | File storage quản lý tập trung theo tier | Chia sẻ filesystem giữa các client |
| **Cloud Storage** | Object storage qua API | Lưu trữ object bền vững theo cấu hình | Datasets gốc, artifact, checkpoint, backup |
| **RAM hoặc tmpfs** | Bộ nhớ trong process / filesystem trên RAM | Mất theo vòng đời process/VM | Bộ đệm rất ngắn, dữ liệu nhỏ cần tốc độ cao |

**Không chọn storage chỉ bằng IOPS.** Cần xét độ bền dữ liệu, phương pháp khôi phục, mô hình file/block/object, tính chia sẻ, vị trí, quyền IAM, hiệu năng cuối luồng và tổng chi phí.

### 2.1. Phân loại dữ liệu trước khi chọn

| Loại dữ liệu | Có thể chỉ lưu Local SSD? | Điều kiện |
|---|---|---|
| HTTP/image cache có origin bền vững | **Có** | Cache miss phải lấy lại được; chấp nhận warm-up |
| Tệp sort/map/shuffle tạm | **Có** | Có input bền vững, job retry/checkpoint và idempotency |
| Build cache và tệp biên dịch tạm | **Có** | Có source/artifact registry để dựng lại |
| Download staging trước khi commit | **Chỉ tạm** | Chưa được coi là đã hoàn thành cho tới khi dữ liệu ghi bền |
| Log dùng để audit hoặc điều tra | **Không**, nếu là bản duy nhất | Đẩy vào Cloud Logging hoặc nơi lưu bền vững |
| Database primary data, WAL/transaction log duy nhất | **Không** | Cần durability/replication/quy trình recovery phù hợp |
| File người dùng tải lên | **Không**, nếu là bản duy nhất | Lưu sang object/durable block trước khi trả kết quả thành công |
| Checkpoint batch cuối cùng | **Không**, nếu là bản duy nhất | Đồng bộ tới kho bền vững theo lịch |
| Session nghiệp vụ, đơn hàng, thanh toán | **Không** | Ghi bền, thiết kế idempotency/transaction |
| Model weights được tải từ Cloud Storage | **Có** với bản copy cache | Có nguồn chính đáng tin và cơ chế warm-up |

**Quy tắc thực dụng:** nếu xóa sạch thư mục Local SSD và chạy lại workload từ nguồn dữ liệu còn lại mà hệ thống không thể đạt yêu cầu RPO/RTO, dữ liệu đó **không nên chỉ nằm trên Local SSD**.

## 3. Local SSD phù hợp với kiến trúc nào?

### 3.1. Cache-aside / read-through cache

Ví dụ API Java đọc ảnh hoặc dữ liệu tham chiếu từ Cloud Storage:

~~~mermaid
sequenceDiagram
    participant U as API client
    participant APP as Java service
    participant SSD as Local SSD cache
    participant GCS as Cloud Storage origin
    U->>APP: Yêu cầu object X
    APP->>SSD: Kiểm tra cache key của X
    alt Cache hit
        SSD-->>APP: Dữ liệu X
    else Cache miss
        APP->>GCS: GET object X
        GCS-->>APP: Dữ liệu X
        APP->>SSD: Lưu cache X (atomic write)
    end
    APP-->>U: Trả kết quả
~~~

Nếu Local SSD mất dữ liệu, cache miss tăng và hệ thống nạp lại từ Cloud Storage. **Rủi ro** là cache stampede (nhiều request cùng tải một object), tăng latency, phí API và mạng. Cần giới hạn concurrency, có request coalescing, eviction, TTL và quota.

### 3.2. Batch scratch + checkpoint

Ví dụ một Java batch đọc input 500 GB từ Cloud Storage, giải nén/sort bằng Local SSD rồi ghi output cuối vào bucket khác.

~~~mermaid
flowchart LR
    IN["Cloud Storage\nInput bất biến"] --> LOAD["Java batch worker"]
    LOAD --> TMP["Local SSD\nChunk, temp files, sorting"]
    TMP --> VALID["Kiểm tra checksum, định dạng"]
    VALID --> OUT["Cloud Storage\nOutput bền vững"]
    OUT --> META["Checkpoint/job metadata\nDurable DB hoặc manifest"]
    FAIL["Host/VM lỗi"] -. "Khởi chạy lại từ checkpoint" .-> LOAD
~~~

Nguyên tắc:

1. Input và định nghĩa job là **bền vững**.
2. Tệp scratch được phép mất; mỗi bước xử lý có thể **chạy lại**.
3. Sau mỗi chunk, ghi output bền vững và commit checkpoint **sau khi output đã xác minh**.
4. Job retry không gây dữ liệu trùng lặp hoặc hỏng kết quả.
5. Khi boot lại với disk trắng, worker có thể **khởi tạo filesystem/cache lại một cách có kiểm soát**.

### 3.3. Workload flash-optimized nhưng dữ liệu phải có bản bền

Một số database hoặc search engine dùng local flash để tăng hiệu năng, nhưng độ bền đến từ **replication, WAL trên kho bền vững, backup, quorum và kiến trúc phục hồi**. Không nói “database chạy trên Local SSD là an toàn” chỉ vì hệ thống có ba node; phải hiểu replication bất đồng bộ, vùng lỗi, quorum, split-brain, trạng thái replica và RPO.

## 4. Giới hạn cấp phát, machine series và interface

### 4.1. Cấp phát Local SSD khi tạo VM

Không thể tạo VM trước rồi gắn Local SSD sau như một Persistent Disk. Tùy machine series:

- **N2, N2D và một số thế hệ cũ:** có thể chọn số ổ Local SSD được hỗ trợ khi tạo VM, ví dụ dùng cờ **--local-ssd** của gcloud.
- **C3/C3D, C4/C4A/C4D/C4N và một số máy tương tự:** chọn machine type có hậu tố **-lssd** để được gắn số ổ tương ứng.
- **Một số storage-optimized/GPU/AI machine series:** Local SSD hoặc Titanium SSD đi kèm máy theo cấu hình mặc định.

Danh sách machine series hỗ trợ, số disk, dung lượng và zone có thể thay đổi. **E2 shared-core** không dùng Local SSD; không chọn máy rẻ nhất rồi giả định có thể gắn Local SSD.

### 4.2. NVMe và SCSI

| Tiêu chí | NVMe | SCSI |
|---|---|---|
| Hiệu năng tiềm năng | Thường cao hơn | Có thể thấp hơn theo cấu hình |
| Điều kiện | OS/driver và machine series hỗ trợ | Chỉ những machine/OS còn hỗ trợ |
| Tên đường dẫn Linux | Thường liên kết ổn định dưới **/dev/disk/by-id/google-local-nvme-ssd-...** | Thường dưới **/dev/disk/by-id/google-local-ssd...** |
| Khuyến nghị | Ưu tiên khi machine và image hỗ trợ | Dùng khi môi trường cần SCSI và tài liệu cho phép |

Một số thế hệ máy mới chỉ hỗ trợ **NVMe**. Với custom Linux image, cần kernel/driver phù hợp; dùng public OS images của Compute Engine thường đơn giản hơn. Không ép SCSI chỉ vì một tutorial cũ dùng **/dev/sdb**.

### 4.3. Dung lượng không đồng nghĩa hiệu năng tuyến tính

Giới hạn IOPS/throughput phụ thuộc vào:

- Số Local SSD disks.
- NVMe/SCSI và thế hệ ổ.
- Machine type và số vCPU đủ để tận dụng I/O.
- Block size, queue depth, số luồng và read/write pattern.
- Filesystem, RAID, kernel/driver và cgroup/IO limits.
- Workload CPU-bound hoặc network-bound.

Số liệu benchmark công bố là **mức tối đa trong điều kiện thử cụ thể**, không phải throughput được bảo đảm cho một Java process đang chạy nghiệp vụ thật. Benchmark phải phân biệt **random IOPS** với **sequential MB/s**, **p50/p95/p99 latency** và tỷ lệ cache hit.

### 4.4. Mã hóa và bảo mật dữ liệu

Compute Engine **tự mã hóa dữ liệu Local SSD khi ghi xuống thiết bị**. Tuy nhiên, theo tài liệu Local SSD hiện hành, **không hỗ trợ customer-managed encryption keys (CMEK) hoặc customer-supplied encryption keys (CSEK)** cho Local SSD.

Nếu quy định yêu cầu mọi dữ liệu lưu ở dạng encrypted-at-rest bằng **khóa do tổ chức kiểm soát**, không mặc nhiên chọn Local SSD; cần xem khả năng mã hóa ở tầng ứng dụng và yêu cầu compliance, hoặc chuyển dữ liệu sang storage hỗ trợ CMEK.

Local SSD vẫn nằm trong filesystem của VM, nên quyền truy cập trong guest OS (user/group, file permissions, process isolation), IAM trên VM, chống SSRF và bảo mật ứng dụng vẫn quan trọng. Mã hóa mặc định **không thay thế** cơ chế phân quyền.

## 5. Thực hành A — Khảo sát VM và Local SSD (chỉ đọc)

Trước khi tạo/format, xác minh **project, zone, danh tính và disk được gắn**. Các lệnh sau chỉ đọc và không thay đổi tài nguyên.

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
ZONE="asia-southeast1-a"
VM="scratch-worker-01"

gcloud auth list
gcloud config list project

# Kiểm tra tình trạng, machine type và disk attachments.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --format="yaml(name,id,status,machineType,disks,scheduling,labels)"

# Liệt kê các VM cùng zone để đối chiếu tên/máy.
gcloud compute instances list \
  --project="$PROJECT_ID" \
  --filter="zone:$ZONE" \
  --format="table(name,zone,status,machineType)"
~~~

Trong trường **disks**, Local SSD thường xuất hiện dưới dạng disk type **SCRATCH**; persistent boot/data disks có type **PERSISTENT**. Tuy nhiên cấu trúc dữ liệu của một machine series có Local SSD đi kèm có thể khác. Luôn đối chiếu machine type và tài liệu sản phẩm, không nhận dạng bằng mỗi số disk.

Trong guest Linux, sau khi có đường SSH/IAP được phép:

~~~bash
# CHỈ ĐỌC — liệt kê thiết bị, filesystem, mount points.
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,MODEL
ls -l /dev/disk/by-id/google-local* 2>/dev/null || true
df -hT
findmnt
~~~

Ghi lại đường dẫn, kích thước và **FSTYPE hiện tại**. Nếu một ổ đã có filesystem/dữ liệu, **không format lại** chỉ vì nó có nhãn “local”. Đối với VM đang phục vụ ứng dụng, không đổi mount point, LVM hoặc RAID mà chưa có owner review.

## 6. Thực hành tạo VM có Local SSD

Các lệnh tạo VM có thể phát sinh chi phí. Chỉ thực hiện trong **project lab có quyền và ngân sách**, không dùng production để thử. Kiểm tra machine type, zone, image và subnet có phù hợp trước khi chạy.

### 6.1. N2 VM với một ổ NVMe Local SSD

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
ZONE="asia-southeast1-a"
SUBNET="YOUR_EXISTING_SUBNET"
VM="scratch-worker-01"

# TẠO TÀI NGUYÊN THẬT — chỉ chạy ở project lab.
gcloud compute instances create "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --machine-type="n2-standard-8" \
  --image-family="debian-12" \
  --image-project="debian-cloud" \
  --subnet="$SUBNET" \
  --no-address \
  --local-ssd="interface=NVME" \
  --labels="environment=development,application=scratch-lab"
~~~

Lệnh **--local-ssd** được dùng với các machine series như N2 cho phép chỉ định ổ khi tạo VM. Muốn nhiều ổ trong giới hạn machine type, thêm số cờ **--local-ssd** tương ứng. **--no-address** không cấp external IPv4; muốn SSH/cập nhật OS có thể cần IAP, Cloud NAT hoặc đường quản trị khác.

Với những machine series có Local SSD đi cùng máy, ví dụ một số **C3/C4 -lssd**, không dùng cờ trên mà chọn **machine type có hậu tố -lssd** theo tài liệu:

~~~bash
# Ví dụ minh họa; khả dụng phụ thuộc zone và quota.
gcloud compute instances create "scratch-c3-lab" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --machine-type="c3-standard-8-lssd" \
  --image-family="debian-12" \
  --image-project="debian-cloud" \
  --subnet="$SUBNET" \
  --no-address
~~~

Không thể gắn Local SSD bổ sung vào VM đã tồn tại. Nếu cần đổi dung lượng Local SSD, thường phải **tạo VM mới phù hợp** và chuyển phần dữ liệu cần giữ sang storage bền vững trước khi thay máy.

### 6.2. Đọc lại cấu hình

~~~bash
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,id,status,machineType,disks,networkInterfaces)"
~~~

Chọn đúng **project, zone, VM ID**. Sau khi tạo, Local SSD thường chưa được format/mount để ứng dụng dùng.

## 7. Format, mount và tự mount an toàn trên Linux

**Cảnh báo:** **mkfs** có thể xóa dữ liệu và làm mất filesystem cũ. Chỉ format **Local SSD mới, hoàn toàn trống, đã xác nhận đúng thiết bị**. Không tự động format tất cả **/dev/nvme*** vì boot disk có thể cũng dùng NVMe.

### 7.1. Xác minh symlink thiết bị

~~~bash
# CHỈ ĐỌC — chạy trên VM Linux lab.
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,MODEL
ls -l /dev/disk/by-id/google-local* 2>/dev/null || true

DEV="/dev/disk/by-id/google-local-nvme-ssd-0"
test -b "$DEV" && readlink -f "$DEV"
sudo blkid "$DEV" || true
findmnt --source "$DEV" || true
~~~

Tên **google-local-nvme-ssd-0** là ví dụ theo NVMe. Nếu VM dùng SCSI hoặc machine series khác, kiểm tra tên theo output thực tế. So khớp metadata của Compute Engine **type=SCRATCH**, capacity, tên thiết bị và filesystem trước khi làm bước tiếp.

### 7.2. Tạo filesystem và mount ổ mới

~~~bash
# PHÁ HỦY DỮ LIỆU TRÊN DEV — chỉ chạy sau khi xác nhận ổ trống.
sudo mkfs.ext4 -F "$DEV"

sudo mkdir -p /mnt/localssd
sudo mount "$DEV" /mnt/localssd

# CHỈ ĐỌC: xác minh mount thật.
findmnt /mnt/localssd
df -hT /mnt/localssd
sudo blkid "$DEV"
~~~

Ứng dụng Java nên ghi trong thư mục có quyền giới hạn. Không dùng **chmod 777** lên toàn bộ mount:

~~~bash
# Giả sử appuser/appgroup đã được quản lý và tồn tại trên VM.
sudo install -d -o appuser -g appgroup -m 0750 /mnt/localssd/jobs
ls -ld /mnt/localssd /mnt/localssd/jobs
~~~

Nếu dùng XFS, cần áp dụng quy trình tạo filesystem tương ứng sau khi xác nhận image hỗ trợ; chọn dựa trên đặc điểm I/O và nhu cầu vận hành.

### 7.3. /etc/fstab với nofail

Đọc UUID:

~~~bash
sudo blkid -s UUID -o value "$DEV"
~~~

Chỉ sau khi xác minh UUID, thêm dòng tương ứng bằng editor quản trị:

~~~text
UUID=<UUID_THUC_TE> /mnt/localssd ext4 defaults,nofail 0 2
~~~

Tùy chọn **nofail** giúp OS boot ngay cả khi ổ không có mặt. Nhưng **fstab không bảo vệ dữ liệu**: nếu VM được cấp Local SSD trắng sau sự cố, filesystem UUID cũ mất và mount sẽ không diễn ra. Startup logic cần nhận diện tình huống đó, không chạy **mkfs vô điều kiện**.

### 7.4. Startup logic an toàn

1. Liệt kê đúng Local SSD qua metadata/by-id và kích thước được mong đợi.
2. Nếu filesystem hợp lệ, **mount mà không format**.
3. Nếu disk mới thực sự trống, chỉ khởi tạo lại nếu chính sách xác nhận **toàn bộ dữ liệu là cache/scratch có thể mất**.
4. Tạo thư mục, quyền user/group; kết nối nguồn dữ liệu bền vững.
5. Warm cache với giới hạn concurrency và theo dõi miss rate.
6. Chỉ cho ứng dụng báo **readiness=healthy** sau khi có thể phục vụ request an toàn.

Nếu một lần reboot bình thường vẫn giữ dữ liệu, script format lại sẽ gây mất dữ liệu **do chính người vận hành tạo ra**. Đây là lỗi nghiêm trọng cần tránh.

## 8. RAID 0 cho nhiều Local SSD

Khi VM có nhiều ổ Local SSD, **mdadm RAID 0** có thể gộp dung lượng và phân bố I/O giữa các ổ. RAID 0 **không có mirror hoặc parity**: mất một member có thể làm mất toàn bộ dữ liệu trên array.

~~~mermaid
flowchart TD
    APP["Java workload"] --> MNT["/mnt/localssd"]
    MNT --> FS["Filesystem ext4/XFS"]
    FS --> MD["/dev/md0 RAID 0"]
    MD --> D0["Local SSD 0"]
    MD --> D1["Local SSD 1"]
    FAIL["Một thiết bị hỏng/mất"] -. "Toàn array có thể mất" .-> MD
~~~

### 8.1. Ví dụ hai ổ mới trong lab

**Phá hủy dữ liệu:** chỉ chạy khi cả hai ổ đã được kiểm tra **đúng Local SSD, trống, không dùng bởi VM khác/process khác**.

~~~bash
# CHỈ ĐỌC — xác nhận hai ổ thực sự có mặt.
ls -l /dev/disk/by-id/google-local-nvme-ssd-*
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT

# TẠO RAID 0 — có thể ghi đè metadata cả hai ổ.
sudo mdadm --create /dev/md0 \
  --level=0 --raid-devices=2 \
  /dev/disk/by-id/google-local-nvme-ssd-0 \
  /dev/disk/by-id/google-local-nvme-ssd-1

# ĐỊNH DẠNG ARRAY — phá hủy dữ liệu trên /dev/md0.
sudo mkfs.ext4 -F /dev/md0
sudo mkdir -p /mnt/localssd
sudo mount /dev/md0 /mnt/localssd

# CHỈ ĐỌC.
sudo mdadm --detail /dev/md0
findmnt /mnt/localssd
df -hT /mnt/localssd
~~~

Nếu muốn tự mount sau reboot, cần cấu hình **mdadm assembly** và fstab theo UUID đúng cách. Không mặc định **/dev/md0** luôn sẵn khi OS boot. RAID 0 chỉ thích hợp với dữ liệu có thể dựng lại: nó **không phải cách tăng durability**.

## 9. Vòng đời dữ liệu Local SSD

Sự khác biệt giữa **guest reboot**, **stop/start**, **live migration**, **host error**, **preemption** và **delete** quyết định dữ liệu còn hay mất.

| Sự kiện | Khả năng giữ Local SSD data | Quy tắc ứng dụng |
|---|---|---|
| **Guest OS reboot bình thường** | Thường **được giữ** | Mount lại và kiểm tra filesystem |
| **Live migration host maintenance (khi được hỗ trợ)** | **Được giữ** trong trường hợp tài liệu nêu | Không coi đây là bản backup |
| **Host error/host failure** | **Best-effort**, có thể mất | Rebuild từ durable origin |
| **Stop VM mặc định** | **Discard dữ liệu** | Chép dữ liệu cần giữ ra storage bền trước |
| **Suspend VM mặc định** | **Discard dữ liệu** | RAM suspend không bảo vệ Local SSD |
| **Stop/suspend với preserve Preview** | Có thể giữ nếu VM/disk đủ điều kiện | Có quota/phí/giới hạn, không thay backup |
| **Spot/preemptible preemption** | **Mất dữ liệu** | Checkpoint và retry |
| **Delete VM** | **Mất Local SSD** | Không có chức năng keep Local SSD disk độc lập |
| **Host maintenance phải terminate** | Có thể mất theo machine/restart policy | Đọc chính sách host và kiểm tra phục hồi |
| **Disk unreachability/misconfiguration** | Không bảo đảm | Không format lại trước khi chẩn đoán |

**Không nói chung chung “restart làm mất dữ liệu”**: reboot trong guest OS không giống **stop từ API rồi start**. Ngược lại, dù Local SSD giữ được trong một lần reboot, nó vẫn không đạt tiêu chí durable storage.

### 9.1. REPAIRING và recovery timeout

Sau host error, Compute Engine có thể đưa VM vào **REPAIRING** khi cố khôi phục Local SSD. Trường **localSsdRecoveryTimeout** quy định khoảng chờ tính bằng giờ; theo tài liệu hỗ trợ **0–168 giờ**, với mặc định khác nhau tùy machine series.

- **0**: ưu tiên khởi động lại nhanh và bỏ dữ liệu Local SSD không thể phục hồi.
- **Lớn hơn 0**: có thời gian cố phục hồi, nhưng ứng dụng có thể không sẵn sàng khi VM đang REPAIRING.
- Hết hạn mà không phục hồi thành công: VM có thể có **Local SSD trắng và chưa format**.
- Quá trình còn phụ thuộc **automaticRestart** và chính sách bảo trì host.

Không luôn chọn 168 giờ vì muốn “an toàn nhất”. Nếu cache có thể tái tạo và hệ thống có node dự phòng, có thể ưu tiên failover nhanh để duy trì SLO hơn là chờ host sửa chữa lâu ngày.

### 9.2. Preserve Local SSD khi Stop/Suspend (Preview)

Google Cloud có khả năng bảo toàn dữ liệu Local SSD truyền thống trong lúc stop/suspend bằng cách chuyển sang durable storage, rồi khôi phục sau start/resume. Nhưng cần chú ý:

- **Preview / pre-GA**, không phải tính năng ổn định mặc định.
- **Không hỗ trợ Titanium SSD**.
- Không hỗ trợ preserve nếu VM có **hơn 48 Local SSD disks**.
- Không thể yêu cầu preserve bằng **Google Cloud console** theo hướng dẫn hiện hành; cần gcloud/REST.
- Tiêu thụ **Persistent disk standard GB quota** và phát sinh phí storage dữ liệu preserved.
- Có thể mất/hỏng dữ liệu nếu gặp lỗi phần cứng trong quá trình sao chép; khôi phục có thể chạy background.
- Spot/preemptible có thể mất dữ liệu khi bị preempt trong lúc preserve.

**Đây không phải backup**. Nếu dữ liệu quan trọng, sao chép ra Cloud Storage, Hyperdisk hoặc Persistent Disk và kiểm thử khả năng đọc lại trước khi stop/suspend.

### 9.3. Ví dụ stop và discard dữ liệu

~~~bash
# THAY ĐỔI TRẠNG THÁI, XÓA DỮ LIỆU LOCAL SSD.
# Chỉ chạy trên VM lab sau xác nhận cache/scratch có thể mất.
gcloud compute instances stop "$VM" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --discard-local-ssd=true
~~~

Nếu cần preserve trong điều kiện được hỗ trợ, tài liệu dùng **gcloud beta** với **--discard-local-ssd=false**; cần đánh giá quota/chi phí/giới hạn Preview trước khi áp dụng. Không dùng với Titanium SSD.

### 9.4. Reset không phải quy trình backup

Reset VM thường giữ ổ gắn cục bộ nhưng có thể gây mất writes chưa flush và hỏng filesystem. Không dùng reset như phương pháp duy trì transactional consistency. Với ứng dụng quan trọng, cần graceful shutdown, checkpoint và thiết kế chống crash.

## 10. Thiết kế ứng dụng Java sử dụng scratch có thể mất

Local SSD chỉ an toàn về mặt nghiệp vụ khi ứng dụng **không cần chính bản copy ở đó để khôi phục dữ liệu quan trọng**.

### 10.1. Phân loại dữ liệu theo RPO/RTO

| Câu hỏi | Nếu câu trả lời là “không” | Điều cần làm |
|---|---|---|
| Có thể tải lại từ nguồn bền vững? | Không | Không chỉ dùng Local SSD |
| Có thể tái tạo bằng một job retry? | Không | Ghi trạng thái và output sang durable storage |
| Chấp nhận mất tiến độ từ checkpoint gần nhất? | Không | Tăng tần suất checkpoint hoặc đổi kiến trúc |
| Có thể rebuild trong RTO yêu cầu? | Không | Dùng replica/hot standby hoặc storage bền hơn |
| Hệ thống biết khi nào output đã commit thành công? | Không | Thiết kế transaction/manifest/checksum và xác nhận |

**RPO (Recovery Point Objective)** là lượng dữ liệu có thể mất theo thời gian; **RTO (Recovery Time Objective)** là thời gian mong muốn để dịch vụ phục hồi. Với cache thuần túy, dữ liệu nguồn có thể RPO gần 0 vì source đã bền vững, nhưng **RTO** vẫn bị ảnh hưởng bởi thời gian warm-up.

### 10.2. Quy trình “durable-first, scratch-second”

Một Java batch an toàn nên theo quy trình:

1. Lưu **input, job definition và checksum** trong Cloud Storage hoặc database bền vững.
2. Đặt **job ID, attempt ID** và khóa idempotency để tránh ghi output trùng.
3. Tạo thư mục riêng theo job ở Local SSD, ví dụ **/mnt/localssd/jobs/JOB_ID**.
4. Xử lý tệp/chunk trung gian trên Local SSD.
5. Upload output tạm sang đích bền vững bằng API có retry, kiểm tra checksum/size.
6. **Chỉ sau khi output hoàn tất**, ghi commit manifest hoặc checkpoint bền vững.
7. Xóa tệp scratch của attempt đã hoàn tất.
8. Nếu VM/disk mất, đọc manifest để bỏ qua chunk đã commit, chạy lại phần chưa commit.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> PROCESSING: Load durable input
    PROCESSING --> UPLOADING: Tạo scratch output
    UPLOADING --> COMMITTED: Durable upload verified + checkpoint
    PROCESSING --> RETRY: VM/Local SSD failure
    UPLOADING --> RETRY: Upload failure trước commit
    RETRY --> PROCESSING: Recreate scratch
    COMMITTED --> [*]: Cleanup local cache
~~~

**Ghi output trước, checkpoint sau** để tránh trạng thái “checkpoint nói đã xong nhưng output chưa bền vững”. Khi retry upload, cần thiết kế **tên object, generation preconditions hoặc manifest** để tránh ghi đè không chủ đích; việc upload thành công nhưng commit checkpoint bị lỗi phải được xử lý idempotently.

### 10.3. Java: tạo scratch file và cleanup

Ví dụ Java thuần sau **không ghi dữ liệu nghiệp vụ bền vững**, chỉ minh họa dùng scratch đúng phạm vi. Biến **SCRATCH_ROOT** phải trỏ đến filesystem đã mount và được ứng dụng cấp quyền.

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ScratchWork {
    private static final Path SCRATCH_ROOT =
            Path.of("/mnt/localssd/jobs");

    public static void runJob(String jobId) throws Exception {
        // Directory phải có sẵn, thuộc filesystem Local SSD và đúng ACL.
        if (!Files.isDirectory(SCRATCH_ROOT) ||
            !Files.isWritable(SCRATCH_ROOT)) {
            throw new IllegalStateException(
                    "Scratch directory chưa sẵn sàng hoặc không ghi được"
            );
        }

        Path temp = Files.createTempFile(
                SCRATCH_ROOT, "attempt-", ".tmp");

        try {
            // Chỉ lưu dữ liệu tạm; không ghi bản duy nhất của đơn hàng.
            Files.writeString(
                    temp, "chunk for " + jobId,
                    StandardCharsets.UTF_8
            );

            // TODO:
            // 1. Xử lý dữ liệu tạm trong temp.
            // 2. Ghi output sang Cloud Storage/durable DB.
            // 3. Xác minh output và COMMIT checkpoint bền vững.
            // 4. Chỉ báo SUCCESS sau khi bước 3 hoàn tất.
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
~~~

Đây là ví dụ tối giản về **lifecycle file**, không phải pipeline hoàn chỉnh. **finally** có thể không chạy khi VM/host lỗi hoặc bị kill cưỡng bức, nên ngoài cleanup theo process còn cần **periodic cleanup theo job age**.

### 10.4. Cache eviction và tránh đầy disk

Khi cache gần đầy, Linux/ứng dụng có thể gặp **ENOSPC**, làm job thất bại hoặc khiến một component khác không ghi được. Nên dùng:

- **TTL** cho cache entries dựa trên tính chất dữ liệu.
- **LRU/LFU** hoặc eviction policy phù hợp.
- **Per-job quota** và concurrent-job limit.
- Tách thư mục cache, scratch, staging và log.
- Ngưỡng high-watermark, ví dụ bắt đầu xóa cache cũ trước khi chạm 90%.
- Rate limit khi warm cache sau failover, tránh dồn tải vào Cloud Storage/database.
- Quy tắc **không xóa các output đang upload** hoặc job chưa commit.

Không xóa cả thư mục mount bằng cron **rm -rf /mnt/localssd/** để “dọn nhanh”: dễ xóa file đang được process sử dụng. Nên dùng manifest/job registry và age/ownership để cleanup có kiểm soát.

## 11. Sao chép/chốt dữ liệu từ Local SSD sang nơi bền vững

### 11.1. Không có snapshot native cho Local SSD

Compute Engine không hỗ trợ tạo **snapshot, clone, disk image hoặc machine image** dùng như backup dữ liệu Local SSD. Nếu dữ liệu cần lưu, phải **copy ra trước khi bị mất**.

Các đích thông dụng:

| Đích | Khi nên dùng |
|---|---|
| **Cloud Storage** | Input/output batch, checkpoint dạng object, artifact, log archive |
| **Persistent Disk** | Cần filesystem/block data có thể gắn lại vào VM |
| **Hyperdisk** | Cần durable block storage và mức hiệu năng theo loại |
| **Database managed** | Metadata/checkpoint/transaction trạng thái có truy vấn và nhất quán |
| **Filestore** | Nhiều client cần shared filesystem NFS |

### 11.2. Copy ví dụ sang Cloud Storage

Giả sử VM đã được cấu hình **service account chỉ có quyền ghi vào bucket/checkpoint prefix phù hợp**, và **gcloud storage** đã khả dụng:

~~~bash
# CHỈ ĐỌC — xác minh thư mục scratch trước khi copy.
du -sh /mnt/localssd/jobs/job-123
find /mnt/localssd/jobs/job-123 -maxdepth 1 -type f

# GHI VÀO CLOUD STORAGE — chỉ chạy với bucket lab hợp lệ.
BUCKET="YOUR_DURABLE_BUCKET"
gcloud storage cp --recursive \
  /mnt/localssd/jobs/job-123 \
  "gs://$BUCKET/checkpoints/job-123/"

# CHỈ ĐỌC — xác minh output remote sau khi copy.
gcloud storage ls "gs://$BUCKET/checkpoints/job-123/"
~~~

Việc một lệnh copy trả exit code 0 **không đủ cho quy trình tài chính/dữ liệu nhạy cảm**. Cần kiểm tra đầy đủ file list, size, checksum hoặc generation, rồi ghi checkpoint/manifest. Với dataset đang thay đổi, phải khóa bước ghi hoặc dùng snapshot/consistent checkpoint của ứng dụng trước khi copy.

**Không đưa tệp chứa credential/secrets thô** vào bucket backup; IAM, bucket policy, encryption và retention phải phù hợp dữ liệu.

### 11.3. Điều gì xảy ra nếu upload thất bại giữa chừng?

Thiết kế an toàn cần:

- Ghi output dưới **staging prefix/object name** riêng cho từng attempt.
- Dùng retry với backoff và giới hạn thời gian.
- Xác minh upload xong bằng checksum/metadata phù hợp.
- Commit metadata trạng thái trong database hoặc manifest bền vững.
- Khi retry, nhận diện trạng thái đã hoàn tất để không double-count.
- Dọn staged artifacts quá hạn theo retention/cleanup policy.

Với Cloud Storage, có thể dùng **generation preconditions** hoặc các tính năng versioning phù hợp để tránh ghi đè mù quáng. Đừng dựa trên filesystem rename ở Local SSD như bằng chứng output đã được lưu trong Cloud Storage.

## 12. GKE, Cloud Run và dịch vụ quản lý có dùng Local SSD như thế nào?

### 12.1. GKE: ephemeral storage nằm ở node

GKE chạy pod trên node Compute Engine nên **Local SSD có thể được sử dụng** trong các cấu hình node pool được hỗ trợ, chẳng hạn:

- **Local SSD-backed ephemeral storage** dành cho dữ liệu ephemeral của pod khi cấu hình phù hợp.
- **Raw block Local SSD** được quản lý theo cách dịch vụ/cluster hỗ trợ.
- Temporary files, build scratch, sort/shuffle phục vụ workload Kubernetes.

Tuy nhiên:

- **emptyDir** không tự bảo đảm dùng Local SSD trên mọi node pool. Phải xem cách cấu hình backing storage và phiên bản GKE.
- **Kubernetes ephemeral-storage requests/limits** có thể ảnh hưởng pod scheduling/eviction, nhưng không bảo đảm dữ liệu bền.
- Khi pod **bị reschedule sang node khác**, local scratch/cache của node cũ không đi theo pod.
- **PodDisruptionBudget** giúp giảm gián đoạn có kế hoạch, không bảo đảm Local SSD sống sót qua host failure.
- GKE node pool/controller có thể tạo lại VM node; không tự stop/delete node bằng Compute Engine CLI để “giữ dữ liệu”.

Cần thiết kế Pod có thể **khởi tạo lại cache, tải lại input, xử lý retry và checkpoint**. Nếu dữ liệu phải chia sẻ hoặc bền lâu, sử dụng PersistentVolume với CSI driver/storage class phù hợp, Filestore, Cloud Storage hoặc database.

### 12.2. Cloud Run không phải VM gắn Local SSD do người dùng quản trị

Cloud Run là môi trường serverless. Filesystem ghi được bên trong instance/container theo cơ chế Cloud Run **không phải một Local SSD Compute Engine có thể attach/format qua gcloud compute**. Dữ liệu filesystem tạm có thể mất khi instance bị thay thế; không dùng làm kho dữ liệu nghiệp vụ.

Với ứng dụng Java chuyển từ Compute Engine sang Cloud Run:

1. Thay đường dẫn scratch cứng **/mnt/localssd** bằng cấu hình storage tùy môi trường.
2. Không giả định instance Cloud Run luôn giữ cache sau scale-to-zero hoặc redeploy.
3. Đưa output và state nghiệp vụ sang Cloud Storage/Cloud SQL/Firestore thích hợp.
4. Kiểm soát memory/ephemeral filesystem limits và concurrent requests.
5. Xem xét chi phí/latency khi dùng Cloud Storage thay local cache.

### 12.3. Managed database

Cloud SQL hoặc các dịch vụ database quản lý không cho người dùng tùy ý attach Local SSD block device vào host dịch vụ như Compute Engine. Người học cần xem cơ chế temporary storage, I/O và backup **riêng của sản phẩm**. Nếu một database engine dùng local flash nội bộ trong kiến trúc sản phẩm, điều đó **không làm dữ liệu của khách hàng tự động nằm trên Compute Engine Local SSD mà ta có quyền quản trị**.

### 12.4. Spot VMs và batch jobs

Spot VM có thể tiết kiệm phí compute cho batch chịu được gián đoạn, nhưng **preemption làm mất Local SSD data**. Thiết kế đúng:

- Dùng input bất biến trong Cloud Storage.
- Chia job thành chunk nhỏ có retry/idempotency.
- Ghi checkpoint/output bền vững sau mỗi chunk.
- Khi VM mới chạy, tái dựng Local SSD/cache trước khi nhận việc.
- Không tin vào shutdown notice như cơ chế đảm bảo luôn có thời gian flush hết dữ liệu.

## 13. Quan sát hiệu năng và dung lượng

Local SSD có thể cung cấp hiệu năng rất cao nhưng vấn đề thực tế thường là **filesystem đầy, I/O latency p99 tăng, RAID member mất hoặc cache warm-up tạo đột biến tải**.

### 13.1. Metrics nên đo

| Nhóm | Ví dụ metric/quan sát | Hành động |
|---|---|---|
| **Dung lượng** | Filesystem used %, free inodes | TTL/eviction, giới hạn số job và output |
| **I/O** | Read/write IOPS, MiB/s, await/latency | Phân tích block size, queue depth, machine bottleneck |
| **Cache** | Hit rate, miss rate, eviction rate | Cải thiện cache keys/TTL và warm-up |
| **Batch** | Bytes processed, chunk retry, checkpoint age | Giảm khối lượng mất khi VM fail |
| **Availability** | VM RUNNING/REPAIRING, Local SSD remount fail | Alert/switchover tới worker khác |
| **Data safety** | Durable checkpoint lag, uncommitted output | Cảnh báo RPO hoặc dừng nhận job mới |
| **Chi phí** | Local SSD provisioned GiB-hours, network/API calls | Right-size machine, disk count, cache policy |

### 13.2. Lệnh Linux chỉ đọc

~~~bash
# Dung lượng và inode.
df -hT /mnt/localssd
df -i /mnt/localssd

# Mount point/source, không ghi đè.
findmnt /mnt/localssd
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT

# Dung lượng các nhánh scratch.
du -sh /mnt/localssd/* 2>/dev/null || true

# Nếu máy đã có sysstat:
iostat -xz 1 5
~~~

Phải xác nhận **/mnt/localssd thực sự là mount** trước khi dùng lệnh ghi dữ liệu. Nếu mount bị thiếu, ứng dụng có thể ghi nhầm vào thư mục cùng tên trên boot disk và gây đầy **Persistent Disk**.

### 13.3. Benchmark không được phá dữ liệu

Có thể dùng **fio** để đo I/O, nhưng nhiều lệnh benchmark chạy trực tiếp trên block device (**/dev/nvme***, **blkdiscard**, raw write) **sẽ xóa dữ liệu**. Trong production, không chạy benchmark phá hủy chỉ để so với số tối đa Google công bố.

Nếu cần đo trong lab:

- Dùng VM/disk **không chứa dữ liệu cần giữ**.
- Ưu tiên file-based benchmark trong thư mục riêng, không phải raw block disk.
- Ghi rõ block size, ioengine, queue depth, số jobs, random/sequential, read/write.
- Quan sát CPU, RAM và throttling cùng IOPS.
- Không chạy benchmark khi ứng dụng đang có yêu cầu độ trễ quan trọng.

## 14. Bảo mật và trách nhiệm quản trị

Local SSD có tự mã hóa khi ghi xuống disk, nhưng an toàn dữ liệu cần cả những lớp khác:

- **IAM:** chỉ service account/người được phép mới có quyền quản trị VM; tránh dùng role rộng.
- **Guest OS access:** user/group, filesystem permissions, process isolation, không để nhiều workload không tin cậy ghi chung.
- **Bí mật:** không để access tokens, service account JSON keys hoặc private keys sống lâu trong cache/scratch.
- **Network:** VPC firewall, DNS, route và IAM của Cloud Storage/DB khi copy output ra nơi bền.
- **Data lifecycle:** phân loại PII, cấu hình TTL/retention, encryption requirement; nếu bắt buộc CMEK thì xem hạn chế của Local SSD.
- **Audit:** ghi nhận thay đổi VM machine type, disk config, stop/suspend, delete và người thực hiện.
- **Backups:** checkpoint và kiểm thử restore, không chỉ bật logging.

### 14.1. Dữ liệu nhạy cảm và xóa an toàn

Vì Local SSD không phải disk durable độc lập, người dùng không thể detach để chuyển cho VM khác; khi delete VM thì disk bị xóa cùng VM. Nhưng điều đó không thay thế yêu cầu **data minimization, truy cập tối thiểu và retention**. Không ghi PII/tài khoản thanh toán vào scratch nếu không có lý do và chính sách kiểm soát.

Không xem một lệnh **rm** trong guest là cơ chế chứng minh xóa vật lý theo chuẩn compliance. Với yêu cầu kiểm toán chặt, phải dựa vào chính sách lưu trữ/xóa dữ liệu và tài liệu Google Cloud về encryption/retirement, đồng thời hạn chế dữ liệu nhạy cảm trên Local SSD từ đầu.

## 15. Chi phí và lựa chọn kích thước

Local SSD được **tính phí theo dung lượng đã cấp phát** (GiB được provision) trong vòng đời VM gắn ổ, không chỉ theo số GB đã ghi. Giá và chiết khấu còn phụ thuộc region, machine series, thế hệ Local SSD/Titanium SSD và loại tiêu thụ.

| Yếu tố | Tác động tới tổng chi phí |
|---|---|
| Dung lượng Local SSD | Phí trên toàn bộ dung lượng cấp phát, kể cả phần trống |
| Machine type | Cần chọn cấu hình có số vCPU/RAM và Local SSD tương ứng |
| Thời gian VM tồn tại | Local SSD gắn với vòng đời VM; kiểm tra chi tiết SKU khi stop/suspend |
| Stop/suspend preserve | Có thể thêm phí lưu dữ liệu preserved và dùng quota PD standard |
| Cache miss | Tăng Cloud Storage reads/network và CPU rebuild |
| Checkpoint quá thường xuyên | Tăng số API/write requests và chi phí lưu dữ liệu |
| Checkpoint quá thưa | Tăng thời gian chạy lại và lượng dữ liệu mất tiến độ |
| Spot VM | Có mức giá Spot cho Local SSD nhưng rủi ro preemption cao hơn |
| Logs và Monitoring | Có thể tính phí ingestion/retention theo mức sử dụng |

### 15.1. Ví dụ tính đơn giản (giả định)

Giả sử một VM N2 có một ổ 375 GiB, đơn giá minh họa **0,10 đơn vị/GiB-tháng**. Nếu chạy/trả phí disk đủ cả tháng, phần Local SSD cơ bản là:

\[
375 \times 0,10 = 37,5\text{ đơn vị/tháng}
\]

Số này **không phải giá Google Cloud thực tế**. Để so sánh phương án, phải thêm compute, boot disk, Cloud Storage, network egress, snapshot/backup khác và thời gian retry sau host failure.

Khi một job chỉ dùng 40 GiB scratch, vẫn có thể phải trả phí dung lượng cả ổ 375 GiB (hoặc toàn bộ dung lượng Local SSD đi kèm machine type). Vì vậy cần đo **capacity utilization** và chọn machine type phù hợp, không chỉ thấy Local SSD nhanh là tăng số ổ.

### 15.2. Cách kiểm chứng hóa đơn

Dùng **Cloud Billing Reports** để lọc project và Group by Service/SKU, tìm các dòng liên quan Compute Engine Local SSD. Nếu cần đối soát chứng từ, dùng **Cost table** và đúng invoice period. Đối chiếu với thời điểm tạo/xóa VM, loại disk, các credits/discounts và độ trễ ghi nhận billing.

**Không lấy số GB đã dùng từ df làm căn cứ trực tiếp để tính phí Local SSD**, vì nhà cung cấp tính theo dung lượng đã cấp phát, không theo dung lượng file hiện tại.

## 16. Runbook: Local SSD biến mất hoặc filesystem không mount được

Khi VM restart sau host error với Local SSD trắng, vấn đề ưu tiên không phải “khôi phục một ổ cũ bằng mọi giá”, mà là **ngăn ứng dụng phục vụ dữ liệu sai**, xác nhận trạng thái disk, và **phục hồi an toàn từ nguồn bền vững**.

### 16.1. Sơ đồ phản ứng sự cố

~~~mermaid
flowchart TD
    ALERT["Alert: scratch unavailable / I/O errors"] --> STATE["Kiểm tra VM status RUNNING/REPAIRING"]
    STATE --> DEV["Kiểm tra device, lsblk, mount, logs"]
    DEV --> Q{"Filesystem/data còn đọc được?"}
    Q -- "Có" --> CHECK["Kiểm tra checksum, health, quota, app"]
    Q -- "Không" --> STOP["Ngừng nhận job mới, xác nhận data classification"]
    STOP --> SAFE{"Chỉ có cache/scratch tái tạo được?"}
    SAFE -- "Không / chưa chắc" --> ESC["Escalate, bảo toàn bằng chứng, xác minh owner"]
    SAFE -- "Có" --> INIT["Khởi tạo thiết bị trống theo runbook"]
    INIT --> RESTORE["Tải input/checkpoint durable, rebuild cache"]
    CHECK --> READY["Health/readiness/metrics"]
    RESTORE --> READY
    READY --> RESUME["Mở traffic có giám sát"]
~~~

**Không chạy mkfs trong lúc REPAIRING** hoặc trước khi biết Local SSD có thực sự mất hoàn toàn. Làm vậy có thể phá dữ liệu còn có khả năng truy cập, khó điều tra nguyên nhân và không giải quyết host availability.

### 16.2. Thao tác chỉ đọc ban đầu

~~~bash
# CHỈ ĐỌC trên máy có quyền quản lý project.
gcloud compute instances describe "$VM" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,id,status,disks,scheduling)"

# Khi VM có thể SSH và ứng dụng cho phép kiểm tra:
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT
ls -l /dev/disk/by-id/google-local* 2>/dev/null || true
findmnt /mnt/localssd || true
df -hT
sudo dmesg --ctime | tail -n 50
~~~

Không tự chép toàn bộ kernel logs vào ticket public: log có thể chứa thông tin hạ tầng nhạy cảm. Với các ứng dụng production, cần phối hợp SRE và owner khi lấy dữ liệu điều tra.

### 16.3. Bảng chẩn đoán

| Triệu chứng | Giả thuyết | Kiểm tra / bước xử lý |
|---|---|---|
| Không thấy thiết bị Local SSD | Sai machine type/VM, host failure, device không attach như kỳ vọng | Describe VM và /dev/disk/by-id; kiểm tra API/status |
| Thấy disk nhưng không có filesystem | Disk được cấp lại trắng sau lỗi/stop | Xác nhận scratch-only và runbook format/mount |
| Có filesystem nhưng không mount | Fstab UUID cũ, mdadm array chưa assemble, filesystem error | Kiểm tra blkid, mdadm, dmesg; không mkfs vội |
| VM ở REPAIRING | Đang cố khôi phục theo host policy | Đọc recovery timeout, đánh giá RTO và phương án failover |
| Disk đầy | Cache không có eviction, job temp không cleanup | df/du, dừng nhận job, xóa theo manifest/owner |
| Hết inode dù còn GB | Quá nhiều file nhỏ | df -i, cleanup theo TTL/job |
| Ứng dụng ghi vào boot disk | /mnt/localssd không được mount | findmnt, kiểm tra volume guard lúc startup |
| Latency tăng | I/O saturation, queue depth, CPU, app pattern | iostat + app tracing, kiểm tra capacity |
| Sau stop/start dữ liệu mất | Mặc định discard Local SSD | Rebuild từ origin, xác minh job checkpoint |
| Spot worker bị preempt | Bản scratch mất, job attempt dở | Schedule lại job, tải checkpoint và retry |
| Có dữ liệu nhưng không đọc được | Permissions/UID/GID, filesystem corruption | Kiểm tra mount/ACL, thông báo owner, tránh reset |
| RAID 0 hỏng | Một member mất hoặc array không assemble | mdadm detail, rebuild chỉ khi scratch được phép mất |

### 16.4. Hậu kiểm sự cố

Đóng incident khi:

1. Đã xác định rõ **nguồn dữ liệu bền vững** và checkpoint mới nhất.
2. Không có output đã báo thành công nhưng lại thiếu ở durable origin.
3. Worker/app được khôi phục và health check thực tế PASS.
4. Những job bị retry không ghi trùng hay làm mất transaction.
5. Mount guard đã ngăn ứng dụng ghi nhầm vào boot disk.
6. Có owner, timeline, nguyên nhân giả định/đã xác minh và biện pháp tránh lặp.
7. Theo dõi chi phí/phí storage, retry và Cloud Storage API sau sự cố.

## 17. Case study: Java data processing với Local SSD

**Bối cảnh giả định:** một công ty thương mại điện tử chạy **Java batch service** trên Compute Engine, nhận dữ liệu giao dịch đã ẩn danh từ Cloud Storage. Mỗi đêm, job đọc vài trăm GB, sort và aggregate, tạo file Parquet/CSV để phân tích trên BigQuery. Một VM N2 có Local SSD dùng làm scratch. Dữ liệu nguồn và output cuối cần bền vững, nhưng tệp tạm có thể tái tạo.

### 17.1. Kiến trúc được chọn

~~~mermaid
flowchart LR
    SCHED["Cloud Scheduler / Workflows"] --> JOB["Compute Engine Java worker\nLocal SSD scratch"]
    ORIGIN["Cloud Storage\ninput bất biến"] --> JOB
    JOB --> STAGE["Cloud Storage\nstaging output theo attempt"]
    STAGE --> VERIFY["Xác minh checksum/size"]
    VERIFY --> MANIFEST["Durable commit manifest"]
    MANIFEST --> BQ["BigQuery / downstream"]
    FAIL["Spot preemption / host error"] -. "Retry từ checkpoint" .-> JOB
    LOG["Cloud Monitoring & Logging"] -. "Observability" .-> JOB
~~~

Thiết kế có các quy tắc:

- Input immutable/versioned, không chỉ nằm trên Local SSD.
- Worker ghi từng chunk scratch, output tạm theo **attempt ID**.
- Durable checkpoint chỉ commit sau khi upload hoàn tất.
- Job có thể chạy lại nhiều lần mà kết quả tổng không bị double-count.
- Cache khởi động lại từ rỗng mà không làm sai kết quả.
- Nếu stop/Spot preemption/host failure, có thể tạo worker mới và tiếp tục từ checkpoint.
- Logs, IAM và storage bucket được phân quyền tối thiểu.

### 17.2. Một sự cố điển hình

Lúc 02:30, host lỗi và Compute Engine không khôi phục được Local SSD. VM boot lại với ổ trắng. Startup script cũ mount theo UUID và lỗi. Java service khởi động nhưng ghi tệp scratch vào **/mnt/localssd** thật ra đang nằm trên boot disk, khiến boot disk đầy; các job khác cùng thất bại.

**Lỗi gốc không chỉ là Local SSD mất dữ liệu**. Thiết kế còn thiếu:

- Guard kiểm tra **findmnt** và đúng block device trước khi bật readiness.
- Khởi tạo scratch an toàn cho tình huống disk mới.
- Checkpoint sau từng chunk thay vì chỉ cuối job.
- Cảnh báo boot disk đầy và local scratch mount unavailable.
- Kế hoạch tự động đưa job sang worker khác khi VM không sẵn sàng.

### 17.3. Khắc phục có thể đo được

1. Trong startup, xác minh Local SSD là mount trước khi Java nhận job.
2. Chỉ tạo filesystem nếu disk được xác nhận là scratch trắng và owner cho phép.
3. Thêm durable manifest/checkpoint sau mỗi chunk.
4. Tách staging/committed outputs; đảm bảo retry idempotent.
5. Thêm cache hit/miss, disk used %, mount state và checkpoint age metrics.
6. Áp dụng chính sách TTL cho temp files, phân quyền appuser và giới hạn concurrent jobs.
7. Chạy chaos test trong lab bằng cách **stop/discard Local SSD có chủ đích**, kiểm tra pipeline phục hồi hoàn toàn từ Cloud Storage.
8. So chi phí job và p95 duration trước/sau, không tối ưu chỉ dựa vào IOPS tối đa.

**Thước đo thành công:** một worker mất Local SSD vẫn không mất transaction/output đã commit; job có thể retry, đạt RPO/RTO mục tiêu và không dùng ổ cục bộ như nơi lưu bản dữ liệu duy nhất.

## 18. Bài tập thực hành và tự kiểm tra

### 18.1. Bài tập A — Chọn đúng loại storage

Với các tình huống dưới đây, chọn Local SSD, Persistent Disk/Hyperdisk, Filestore hay Cloud Storage và giải thích:

| Tình huống | Gợi ý |
|---|---|
| Tệp sort tạm, có input bền vững và có thể chạy lại | Local SSD |
| Boot disk VM Java | Persistent Disk hoặc Hyperdisk phù hợp |
| Hai VM cần chia sẻ filesystem qua NFS | Filestore |
| Ảnh người dùng tải lên, phải lưu dài hạn | Cloud Storage |
| WAL duy nhất của database không có replication | Không chỉ đặt trên Local SSD |
| Cache model weights tải lại từ bucket | Local SSD có thể phù hợp |
| Dataset gốc dùng nhiều tháng | Cloud Storage hoặc storage bền vững |
| Staging upload chưa có commit | Local SSD chỉ là tạm; phải ghi bền trước SUCCESS |

### 18.2. Bài tập B — Xác định trạng thái dữ liệu

Hãy trả lời sau mỗi sự kiện:

1. VM Linux chỉ chạy **reboot** bên trong guest OS. Có được mặc định xóa toàn bộ Local SSD không?
2. VM được **stop** từ Compute Engine với hành vi mặc định. Khi start lại, điều gì xảy ra với Local SSD?
3. VM dùng **Titanium SSD**. Có thể dùng preserve Local SSD Preview khi suspend không?
4. Spot VM đang chạy bị **preempt**. Job có thể dựa vào tệp scratch cũ để tiếp tục không?
5. VM bị host error và chuyển **REPAIRING**. Có nên lập tức mkfs lại thiết bị không?
6. VM bị **delete**. Có thể giữ Local SSD như một persistent disk rời không?
7. Bạn tạo **RAID 0 hai Local SSD**. Mất một thiết bị có ảnh hưởng toàn array không?
8. Tạo snapshot boot disk có sao chép toàn bộ dữ liệu Local SSD không?

**Đáp án:** (1) Không; dữ liệu thường được giữ qua guest reboot; (2) mặc định bị discard; (3) không; (4) không; (5) không; (6) không; (7) có; (8) không.

### 18.3. Bài tập C — Tìm lỗi trong startup script

Đọc script sau, **không thực thi**:

~~~bash
# VÍ DỤ SAI — KHÔNG CHẠY.
sudo mkfs.ext4 -F /dev/nvme0n1
sudo mkdir -p /mnt/localssd
sudo mount /dev/nvme0n1 /mnt/localssd
java -jar worker.jar
~~~

**Câu hỏi:**

1. Tại sao chọn cố định **/dev/nvme0n1** có thể gây mất boot disk?
2. Tại sao chạy mkfs ở mọi lần startup làm mất dữ liệu sau reboot?
3. Cần những bước kiểm tra gì trước khi quyết định format?
4. Cần kiểm tra gì trước khi Java service được đánh dấu ready?

**Định hướng:** đối chiếu symlink by-id, instance metadata và disk type=SCRATCH; dùng lsblk/blkid/findmnt; chỉ format disk trắng được xác nhận; kiểm tra mount point thật và dữ liệu nguồn bền vững trước khi phục vụ workload.

### 18.4. Bài tập D — Thiết kế checkpoint

Một batch job có 100 chunk, mỗi chunk xử lý 2 phút. Nếu Local SSD mất sau chunk thứ 90 mà job chỉ checkpoint cuối cùng, phải chạy lại bao nhiêu phút trong trường hợp xấu? Nếu checkpoint sau mỗi 5 chunk thì lượng công việc phải chạy lại tối đa là bao nhiêu chunk, giả sử không có vấn đề upload/commit?

**Đáp án định hướng:** không có checkpoint giữa chừng, có thể phải chạy lại tới 180 phút đã xử lý; với checkpoint mỗi 5 chunk, tối đa khoảng 5 chunk/10 phút công việc (cần chú ý ranh giới thời điểm checkpoint và dữ liệu đang xử lý). Muốn đạt RPO/RTO tốt hơn phải cân bằng tần suất checkpoint, phí write và overhead.

### 18.5. Biên bản kiểm kê và phục hồi Local SSD

~~~text
PROJECT_ID:
ZONE:
VM_NAME / VM_ID:
OWNER:
MACHINE_TYPE:
LOCAL_SSD_TYPE: classic / Titanium
DEVICE_INTERFACE: NVMe / SCSI
DEVICE_BY_ID:
NUMBER_OF_DISKS / CAPACITY:
FILESYSTEM / RAID:
MOUNT_PATH:
CACHE_OR_SCRATCH_PURPOSE:
DURABLE_SOURCE_OF_TRUTH:
CHECKPOINT_LOCATION / RPO:
RECOVERY_PROCEDURE / RTO:
SPOT_OR_HOST_POLICY:
LOCAL_SSD_RECOVERY_TIMEOUT:
STOP_SUSPEND_PRESERVE_POLICY:
ENCRYPTION_AND_DATA_CLASSIFICATION:
DISK_USED_PERCENT / CACHE_HIT_RATE:
COST_REVIEW:
TEST_DATE_AND_RESULT:
OPEN_ISSUES:
~~~

Không điền **PASS** khi chỉ dự đoán khả năng phục hồi. Cần ghi bước đã chạy thật, metric đã đo và bằng chứng đầu ra được lưu.

## 19. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Local SSD nhanh nên an toàn hơn Persistent Disk.” | Hiệu năng và độ bền dữ liệu là hai thuộc tính khác nhau. |
| “Đặt dữ liệu trên filesystem ext4 là đã durable.” | Filesystem không khắc phục bản chất ephemeral của host-attached storage. |
| “Có thể thêm Local SSD khi VM đã chạy.” | Chỉ cấu hình tại thời điểm tạo VM; máy có sẵn Local SSD theo machine type là trường hợp riêng. |
| “Mọi Local SSD có đúng 375 GiB.” | Kích thước phụ thuộc dòng máy, đặc biệt Titanium SSD. |
| “Reboot guest OS luôn xóa dữ liệu Local SSD.” | Guest reboot thông thường có thể giữ dữ liệu. |
| “Stop/start vẫn giữ Local SSD nếu VM name không đổi.” | Mặc định Local SSD bị discard khi stop. |
| “Preview preserve tương đương backup chắc chắn.” | Có giới hạn máy, quota, phí và nguy cơ mất dữ liệu. |
| “Titanium SSD dùng được preserve Preview.” | Không hỗ trợ theo tài liệu hiện hành. |
| “Có thể snapshot Local SSD trực tiếp.” | Không; phải copy dữ liệu cần giữ sang durable storage. |
| “RAID 0 giúp tăng tính sẵn sàng dữ liệu.” | RAID 0 không có redundancy, mất một thành viên có thể mất toàn array. |
| “fstab với nofail giữ nguyên dữ liệu.” | nofail chỉ ảnh hưởng hành vi boot/mount khi disk vắng mặt. |
| “Tên /dev/nvme0n1 luôn là Local SSD.” | Phải kiểm tra by-id, filesystem, metadata và disk type. |
| “Cache mất không ảnh hưởng người dùng.” | Cache cold start có thể tăng latency, phí network/API và gây stampede. |
| “Spot VM chỉ mất RAM khi preempt.” | Local SSD data cũng có thể mất. |
| “GKE emptyDir luôn nằm trên Local SSD.” | Tùy node pool/cấu hình backing storage và phiên bản GKE. |
| “Local SSD của VM là Filestore chia sẻ.” | Local block device khác managed NFS. |
| “Dùng hết 10 GiB thì chỉ trả phí 10 GiB.” | Tính theo dung lượng provisioned, không theo bytes đã ghi. |
| “Phần mềm startup cứ thiếu mount là mkfs.” | Đây có thể là hành động phá dữ liệu khi mount trễ/sai device. |

## 20. Tài liệu Google Cloud chính thức

Những tài liệu dùng để đối chiếu giới hạn, machine series, cú pháp gcloud và hành vi Local SSD:

- [About Local SSD disks](https://docs.cloud.google.com/compute/docs/disks/local-ssd)
- [Add Local SSD disks to your VM](https://docs.cloud.google.com/compute/docs/disks/add-local-ssd)
- [Choose a disk type](https://docs.cloud.google.com/compute/docs/disks)
- [Format and mount a non-boot disk on Linux](https://docs.cloud.google.com/compute/docs/disks/format-mount-disk-linux)
- [Optimize Local SSD performance](https://docs.cloud.google.com/compute/docs/disks/optimizing-local-ssd-performance)
- [Benchmark Local SSD performance](https://docs.cloud.google.com/compute/docs/disks/benchmarking-local-ssd-performance)
- [Host maintenance policy and Local SSD recovery](https://docs.cloud.google.com/compute/docs/instances/host-maintenance-overview)
- [Stop or restart a Compute Engine VM](https://docs.cloud.google.com/compute/docs/instances/stop-start-instance)
- [Suspend or resume a Compute Engine VM](https://docs.cloud.google.com/compute/docs/instances/suspend-resume-instance)
- [General-purpose Compute Engine pricing](https://cloud.google.com/products/compute/pricing/general-purpose)
- [Disk and image pricing](https://cloud.google.com/compute/disks-image-pricing)

Thông số performance, dòng máy, tính năng Preview, yêu cầu quota, cờ CLI và giá có thể thay đổi theo phiên bản Google Cloud. Với môi trường thật, cần đối chiếu tài liệu đúng **machine type, OS image, zone và thời điểm triển khai**.

---

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** Local SSD bổ sung một lựa chọn block storage nhanh cho Compute Engine và một số workload GKE, nhưng bài học cốt lõi là **chọn nơi giữ bản dữ liệu chính và nơi giữ bản sao tạm**. Hãy kết hợp **Cloud Storage/Persistent Disk/Hyperdisk** để lưu bền, **IAM và VPC** để bảo vệ truy cập, **Cloud Monitoring/Logging** để phát hiện lỗi và **Cloud Billing** để kiểm soát chi phí. Khi chuyển workload sang Cloud Run hoặc dịch vụ quản lý khác, tiếp tục giữ nguyên nguyên tắc **scratch có thể mất — output/checkpoint phải bền vững — ứng dụng phải phục hồi được từ nguồn tin cậy**.







