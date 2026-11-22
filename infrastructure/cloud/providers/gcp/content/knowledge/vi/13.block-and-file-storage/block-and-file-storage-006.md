# Gắn đĩa, mở rộng dung lượng và quản lý filesystem

Một API Java chạy trên Compute Engine bắt đầu gặp lỗi ghi tệp khi thư mục dữ liệu đầy. Nhóm vận hành tăng Persistent Disk từ 100 GiB lên 200 GiB trong Google Cloud Console, nhưng lệnh `df -h` trên VM vẫn báo filesystem chỉ có khoảng 100 GiB. Vấn đề nằm ở **hai lớp quản lý dung lượng khác nhau**: Google Cloud quản lý kích thước **block device**; hệ điều hành quản lý **partition, volume và filesystem** trên thiết bị đó.

Bài học **“Gắn đĩa, mở rộng dung lượng và quản lý filesystem”** thuộc chương **Lưu trữ khối và tệp** của học phần **CLOUD_PROVIDERS_GCP**. Đây là kiến thức thực hành để chọn loại lưu trữ, thao tác an toàn với Compute Engine, phân quyền qua IAM, bảo vệ dữ liệu và kết nối các dịch vụ như GKE, Cloud Run, Cloud Storage hoặc cơ sở dữ liệu. Bên cạnh cách thêm dung lượng, ta cần biết lưu trữ nào phù hợp với workload, tự động hóa thao tác, theo dõi độ tin cậy và tránh phát sinh chi phí không cần thiết.

Sau bài học, bạn có thể:

- Phân biệt **block storage** (Persistent Disk, Hyperdisk) với **file storage** (Filestore) và object storage (Cloud Storage).
- Giải thích chuỗi **disk → partition (nếu có) → LVM (nếu có) → filesystem → mount point → ứng dụng**.
- Tạo và gắn data disk vào một VM Linux bằng Console/`gcloud`.
- Nhận diện đúng thiết bị, định dạng ext4 hoặc XFS, mount an toàn và cấu hình `/etc/fstab`.
- Mở rộng dung lượng disk, partition, filesystem hoặc logical volume theo thứ tự đúng.
- Sao lưu bằng snapshot, tách disk an toàn, quản trị quyền, quan sát I/O và dự toán chi phí.
- Biết khi nào nên dùng Filestore để nhiều VM chia sẻ tệp thay vì gắn một filesystem thường vào nhiều máy.

> **Phạm vi lab:** các lệnh ví dụ dùng một VM Linux và một **data disk trống** chưa có dữ liệu. Các lệnh `mkfs`, thay partition table và chỉnh `/etc/fstab` có thể làm mất dữ liệu hoặc khiến VM không khởi động nếu áp dụng sai thiết bị. **Không chạy trên boot disk hoặc disk chứa dữ liệu thật** khi chưa kiểm tra và sao lưu. Chỉ thực thi trong project lab được phép và thay toàn bộ placeholder bằng giá trị thật.

## 1. Ba lớp lưu trữ thường gặp trên Google Cloud

Không phải mọi tài nguyên lưu trữ đều được dùng giống một “ổ cứng”.

| Loại | Dịch vụ điển hình | Cách ứng dụng truy cập | Trường hợp phù hợp |
|---|---|---|---|
| **Block storage** | Persistent Disk, Hyperdisk của Compute Engine | Hệ điều hành thấy một block device; tạo filesystem và mount | Boot disk, thư mục dữ liệu, workload yêu cầu block I/O |
| **File storage được quản lý** | Filestore | NFS file share qua VPC; client mount đường dẫn mạng | Nhiều VM/GKE Pods cần chia sẻ cây thư mục POSIX |
| **Object storage** | Cloud Storage | API/SDK, HTTP hoặc công cụ tương thích | Ảnh, file người dùng, backup, artifact, dữ liệu dạng object |
| **Local SSD** | Thiết bị lưu trữ cục bộ gắn VM | Block device trên host | Scratch, cache tốc độ cao, dữ liệu có thể tạo lại |

**Block storage** là tập hợp các khối dữ liệu, không tự có khái niệm thư mục hay quyền Unix. Khi gắn disk vào Linux, phải có filesystem như ext4 hoặc XFS (hoặc một lớp quản lý dữ liệu phù hợp) rồi mới dùng như một thư mục.

**File storage** đã có dịch vụ filesystem và cơ chế chia sẻ trên mạng. Client NFS chỉ cần kết nối và mount export được cho phép; **không chạy `mkfs.ext4` lên một NFS share**.

**Object storage** không phải ổ POSIX mặc định. Cloud Storage phù hợp dữ liệu được truy cập theo object name/API; không có cùng ngữ nghĩa filesystem, locking, rename và consistency của block disk hoặc NFS. Nếu ứng dụng Java lưu ảnh do người dùng tải lên, Cloud Storage thường đáng cân nhắc hơn một data disk gắn riêng vào VM.

### Boot disk, data disk và tính bền vững

- **Boot disk** chứa OS và thường có partition/filesystem root; xóa hoặc sửa sai có thể làm VM không khởi động.
- **Data disk** tách dữ liệu ứng dụng khỏi OS, có thể tạo snapshot, detach hoặc chuyển sang một VM khác khi thiết kế hỗ trợ.
- **Persistent Disk/Hyperdisk** là lưu trữ bền vững độc lập với vòng đời process của VM; tuy vậy disk vẫn có thể bị xóa do cài đặt auto-delete, thao tác quản trị hoặc lỗi dữ liệu trong guest OS.
- **Local SSD** thiên về dữ liệu tạm, không nên dùng làm bản sao duy nhất của dữ liệu quan trọng. Khả năng giữ dữ liệu qua các thao tác VM phụ thuộc machine series và lifecycle được hỗ trợ.

## 2. Kiến trúc dung lượng từ Google Cloud đến ứng dụng

Trên Linux, lệnh `lsblk` cho thấy **block device** và các lớp phụ thuộc; `df` cho thấy filesystem đã mount. Hai lệnh có thể hiển thị dung lượng khác nhau sau khi tăng disk.

~~~text
Google Cloud Persistent Disk: app-data (200 GiB)
                  │
                  ▼
Guest OS block device: /dev/disk/by-id/google-app-data
                  │
        ┌─────────┴──────────┐
        │ Không có partition │ Hoặc có GPT partition table
        │ (filesystem trực   │  └── /dev/sdb1 hay nvme0n2p1
        │  tiếp trên disk)   │             │
        └─────────┬──────────┘             ├── (tùy chọn) LVM
                  │                        │
                  └──────────┬─────────────┘
                             ▼
                      ext4 / XFS filesystem
                             │
                             ▼
                      /mnt/disks/app-data
                             │
                             ▼
                       Java / ứng dụng
~~~

Đường **không có partition** được dùng trong lab để hiểu đơn giản nhất. Một hệ thống thật có thể có GPT, LVM, RAID hoặc lớp mã hóa LUKS, làm quy trình mở rộng phức tạp hơn.

### Các lệnh quan sát

~~~bash
# Trên VM Linux.
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
df -hT
df -i
sudo blkid
findmnt /
~~~

| Lệnh | Trả lời câu hỏi |
|---|---|
| `lsblk` | Kernel đang thấy disk/partition nào, dung lượng và sơ đồ phụ thuộc? |
| `blkid` | Thiết bị nào có UUID, filesystem type? |
| `df -hT` | Filesystem đã mount ở đâu, có bao nhiêu dung lượng còn lại? |
| `df -i` | Có hết **inode** dù còn dung lượng byte không? |
| `findmnt` | Mount point đến từ nguồn nào, dùng filesystem/options gì? |
| `du -xsh /path` | Dữ liệu nằm trong filesystem đó đang chiếm bao nhiêu? |

Nếu `lsblk` báo disk đã 200 GiB nhưng `df -hT` vẫn thấy 100 GiB, rất có thể cần mở rộng **partition** và/hoặc **filesystem**. Nếu cả `lsblk` vẫn thấy kích thước cũ, phải kiểm tra disk thật đã được resize trên Google Cloud và guest OS có nhận thay đổi chưa.

## 3. Chọn loại block disk theo workload

Compute Engine có nhiều lựa chọn block storage. Không nên quyết định chỉ dựa trên kích thước GiB.

| Lựa chọn | Đặc điểm | Gợi ý sử dụng |
|---|---|---|
| **Persistent Disk Standard** (`pd-standard`) | HDD-backed, tối ưu chi phí cho workload cần throughput tuần tự hơn IOPS ngẫu nhiên | Dữ liệu ít truy cập, workload không nhạy IOPS |
| **Persistent Disk Balanced** (`pd-balanced`) | SSD-backed, cân bằng chi phí và hiệu năng | Boot/data disk phổ thông của VM |
| **Persistent Disk SSD** (`pd-ssd`) | SSD-backed, mục tiêu hiệu năng cao hơn balanced cho workload phù hợp | Ứng dụng có nhu cầu I/O lớn |
| **Hyperdisk** (Balanced/Extreme/Throughput/... tùy hỗ trợ) | Dung lượng và một số mức IOPS/throughput được cấu hình riêng; có giới hạn theo machine type | Database/analytics hoặc workload cần kiểm soát performance |
| **Local SSD** | I/O tốc độ cao tại host, tính chất lưu dữ liệu gắn với vòng đời VM | Cache, scratch, dữ liệu có thể tạo lại |

Hiệu năng thực tế phụ thuộc **disk type, kích thước, vCPU, machine family, số lượng disk và I/O pattern**. Với Persistent Disk, kích thước có thể ảnh hưởng giới hạn throughput/IOPS; với nhiều loại Hyperdisk, IOPS hoặc throughput được **provision** riêng và có thể điều chỉnh theo giới hạn dịch vụ. Tăng GiB không bảo đảm latency ứng dụng giảm ngay.

Một số máy chỉ hỗ trợ loại Hyperdisk nhất định. Trước khi tạo cần kiểm tra **machine type compatibility**, region/zone, giới hạn số disk, quotas và khả năng cung cấp.

### Zonal, regional và multi-writer

- **Zonal Persistent Disk** được tạo trong một zone và gắn vào VM tương thích ở zone đó.
- **Regional Persistent Disk** có bản sao dữ liệu đồng bộ giữa hai zone trong cùng region theo thiết kế sản phẩm. **Không tự động biến ứng dụng thành high availability**: vẫn cần VM dự phòng, quy trình chuyển quyền ghi/failover và khôi phục ứng dụng.
- Một số loại disk hỗ trợ **nhiều VM cùng truy cập**, có thể chỉ đọc hoặc multi-writer tùy sản phẩm và mode. **Đừng mount ext4/XFS thông thường ở chế độ ghi đồng thời trên nhiều VM** nếu filesystem không được thiết kế cho concurrent writers; nguy cơ hỏng dữ liệu rất cao. Khi cần chia sẻ tệp, Filestore/NFS thường là lựa chọn phù hợp hơn.
- Disk nằm trên Google Cloud không có nghĩa dữ liệu sẽ được backup: replication của disk, snapshots và backups có mục đích khác nhau.

## 4. Quy trình thao tác an toàn trước khi gắn hoặc sửa disk

Luôn kiểm tra bốn lớp: **tài nguyên Cloud**, **thiết bị trong OS**, **filesystem**, **dữ liệu ứng dụng**.

1. Xác nhận **project, zone, VM, tên disk**; ghi rõ owner và người được phép thay đổi.
2. Xem disk đã có dữ liệu, partition hoặc filesystem chưa. Disk **đã tồn tại không đồng nghĩa còn trống**.
3. Nếu đang chứa dữ liệu, tạo snapshot/backup và kiểm tra chính sách lưu giữ; cần application-consistent backup cho database hoặc workload ghi liên tục.
4. Xác minh dịch vụ còn dung lượng để duy trì và quota cho thay đổi; dự trù chi phí.
5. Chọn cửa sổ thao tác khi cần unmount, phân chia lại partition, di chuyển data hoặc sửa `fstab`.
6. Chuẩn bị rollback phù hợp (snapshot, backup, disk cũ, image), và biết người chịu trách nhiệm khi mount lỗi.

Ví dụ từ Cloud Shell hoặc máy đã cấu hình `gcloud`:

~~~bash
PROJECT_ID="my-storage-lab"
ZONE="us-central1-a"
VM="app-vm"
DISK="app-data"

gcloud config set project "$PROJECT_ID"
gcloud compute instances describe "$VM" \
  --zone="$ZONE" \
  --format="yaml(name,zone,disks)"

# Chỉ có thể describe khi disk đã tồn tại.
gcloud compute disks describe "$DISK" \
  --zone="$ZONE"
~~~

Trong output `instances describe`, kiểm tra `boot`, `autoDelete` và `source` của từng disk. Tránh nhầm disk mới với boot disk và không giả định tên `/dev/sdb` luôn ổn định qua mọi lần reboot hoặc mọi máy ảo.

## 5. Thực hành tạo và gắn một Persistent Disk vào VM Linux

Giả sử VM `app-vm` đã tồn tại ở `us-central1-a`, đang chạy Debian/Ubuntu và được quyền nhận data disk. Tạo một disk Balanced 100 GiB.

### Bước 1 — Tạo disk bằng Console hoặc gcloud

Trong Google Cloud Console, vào **Compute Engine → Storage → Disks → Create disk**, chọn tên, zone trùng VM, loại `Balanced persistent disk` và dung lượng 100 GiB. Không chọn image/snapshot nếu muốn disk trống để thực hành format. Sau khi tạo, kiểm tra tên và kích thước.

Tương đương qua CLI:

~~~bash
gcloud compute disks create "$DISK" \
  --zone="$ZONE" \
  --size=100GB \
  --type=pd-balanced

gcloud compute disks describe "$DISK" \
  --zone="$ZONE" \
  --format="yaml(name,sizeGb,type,status,users)"
~~~

**Disk mới chưa tự xuất hiện dưới dạng thư mục trong VM.** Nó là tài nguyên block storage được tạo trong Google Cloud project, chịu phí lưu trữ theo dung lượng được cấp phát.

### Bước 2 — Attach vào VM

Trong Console, mở **Compute Engine → VM instances → app-vm → Edit → Additional disks → Attach existing disk**, chọn `app-data`, mode read/write và lưu thay đổi. Tùy điều kiện, việc attach data disk có thể thực hiện trên VM đang chạy.

Tương đương qua CLI:

~~~bash
DEVICE_NAME="app-data"

gcloud compute instances attach-disk "$VM" \
  --zone="$ZONE" \
  --disk="$DISK" \
  --device-name="$DEVICE_NAME" \
  --mode=rw

gcloud compute instances describe "$VM" \
  --zone="$ZONE" \
  --format="yaml(disks)"
~~~

Với zonal Persistent Disk, VM và disk phải ở **cùng zone**. Với regional disk hoặc Hyperdisk, quy tắc vị trí và chế độ gắn phụ thuộc tính năng của từng loại. Nếu disk đang được VM khác dùng read/write, không tự ý attach lại ở chế độ ghi vào VM thứ hai.

### Bước 3 — Nhận diện đúng disk trong Linux

SSH vào VM và chạy:

~~~bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
ls -l /dev/disk/by-id/google-*
sudo blkid

# Đường ổn định khi lúc attach đã đặt --device-name=app-data.
DEV="/dev/disk/by-id/google-app-data"
readlink -f "$DEV"
sudo lsblk -f
~~~

Linux có thể gọi thiết bị là `/dev/sdb`, `/dev/nvme0n2` hoặc tên khác tùy giao diện SCSI/NVMe và machine series. Đường symlink `/dev/disk/by-id/google-app-data` giúp định danh disk bằng **device name đã đặt khi attach**, tránh đoán tên kernel.

**Điều kiện để format:** phải xác minh `DEV` đang trỏ đúng **data disk trống**, kích thước khoảng 100 GiB, không phải boot disk, không có filesystem/partition/dữ liệu quan trọng. Nếu `lsblk` hay `blkid` cho thấy dữ liệu có sẵn, dừng thao tác để xác minh thay vì chạy `mkfs`.

## 6. Format ext4, mount và cấu hình fstab

Để tập trung vào thao tác chính, lab sử dụng **filesystem ext4 trực tiếp trên toàn disk, không tạo partition table**. Cách này được Linux và Google Cloud hỗ trợ cho data disk; dự án thật có thể dùng GPT + partition hoặc LVM.

### Bước 1 — Format và mount lần đầu

~~~bash
DEV="/dev/disk/by-id/google-app-data"
MOUNT_DIR="/mnt/disks/app-data"

# CẢNH BÁO: mkfs XÓA cấu trúc dữ liệu cũ.
# Chỉ chạy sau khi xác nhận đây là disk data MỚI và TRỐNG.
sudo mkfs.ext4 "$DEV"

sudo mkdir -p "$MOUNT_DIR"
sudo mount -o defaults "$DEV" "$MOUNT_DIR"

# Chỉ là ví dụ quyền sở hữu cho user của VM lab.
sudo chown "$USER:$USER" "$MOUNT_DIR"

df -hT "$MOUNT_DIR"
findmnt "$MOUNT_DIR"
sudo blkid "$DEV"
~~~

Khi mount thành công, filesystem mới có đường dẫn `/mnt/disks/app-data`. Ứng dụng muốn lưu file ở đây phải có quyền Unix phù hợp, hoặc dùng ACL/user/group theo chính sách. Đừng dùng `chmod 777` như cách khắc phục mặc định vì sẽ mở quyền đọc/ghi cho mọi user trên VM.

### Bước 2 — Mount lại sau reboot

Lệnh `mount` ở trên chỉ có hiệu lực trong phiên chạy hiện tại. Để mount tự động, đặt một entry đúng vào `/etc/fstab`.

~~~bash
# Lấy UUID của filesystem đã tạo.
sudo blkid -s UUID -o value "$DEV"

# Backup fstab trước khi sửa.
sudo cp /etc/fstab /etc/fstab.bak

# Dùng trình soạn thảo để thêm CHỈ MỘT dòng đúng UUID vào /etc/fstab.
sudo nano /etc/fstab
~~~

Ví dụ nội dung một dòng, trong đó **UUID phải thay bằng giá trị vừa đọc**:

~~~fstab
UUID=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX /mnt/disks/app-data ext4 defaults,nofail 0 2
~~~

- **UUID** không phụ thuộc vào việc kernel gọi disk là `sdb` hay `nvme0n2`.
- `nofail` cho phép hệ thống tiếp tục khởi động nếu disk không có mặt; khi ứng dụng **bắt buộc** cần disk, vẫn phải cấu hình unit dependency/health check để nó không ghi nhầm vào thư mục rỗng trên boot disk.
- `0 2` là các trường `dump/fsck` thường dùng cho filesystem dữ liệu ext4.
- Không tạo nhiều entry chồng nhau cho cùng một mount point.

Kiểm tra trước khi reboot:

~~~bash
sudo mount -a
findmnt /mnt/disks/app-data
df -hT /mnt/disks/app-data
~~~

Trên các hệ thống dùng systemd, có thể chạy `sudo systemctl daemon-reload` sau chỉnh `fstab` nếu công cụ báo cần reload. Nếu `mount -a` lỗi, sửa `fstab` ngay trong khi VM còn hoạt động; **đừng reboot để kiểm tra bằng may rủi**.

### Tên thiết bị ổn định và UUID: chọn cái nào?

| Dùng | Ưu điểm | Lưu ý |
|---|---|---|
| `/dev/sdb` hoặc `/dev/nvme0n2` | Dễ nhìn trong một phiên | Có thể thay đổi giữa boot hoặc cấu hình máy |
| `/dev/disk/by-id/google-app-data` | Gắn với device name khi attach | Cần đặt đúng `--device-name` và theo dõi khi reattach |
| `UUID=...` trong `fstab` | Gắn với filesystem, bền qua đổi tên thiết bị | Snapshot/clone filesystem có thể mang UUID trùng; phải xử lý nếu mount song song |
| `LABEL=...` trong `fstab` | Dễ đọc và quản lý | Label phải duy nhất trong hệ thống để tránh mount nhầm |

Khi tạo disk từ snapshot rồi gắn **cùng VM với disk gốc**, kiểm tra UUID và label vì bản sao filesystem có thể trùng định danh. Đừng gắn vào production khi chưa xác định filesystem nào phải được mount.

## 7. Mở rộng Persistent Disk: hai bước bắt buộc

Giả sử disk `app-data` từ 100 GiB cần lên **200 GiB**. Đây là quy trình tăng dung lượng, **không phải thu nhỏ**. Persistent Disk có thể tăng dung lượng khi gắn với VM đang chạy; trước thao tác ảnh hưởng partition/filesystem, nên có snapshot hoặc backup đã kiểm chứng. Với dữ liệu database, cần nhất quán ở cấp ứng dụng.

~~~mermaid
flowchart TD
    A["Snapshot / backup và kiểm tra ổ"] --> B["Google Cloud: resize disk 100 → 200 GiB"]
    B --> C{"Linux thấy disk lớn hơn?"}
    C -- "Chưa" --> D["Kiểm tra operation/guest OS và device"]
    D --> C
    C -- "Có" --> E{"Có partition/LVM?"}
    E -- "Không" --> F["Grow filesystem trên raw device"]
    E -- "Partition" --> G["Grow partition → grow filesystem"]
    E -- "LVM" --> H["Grow partition/PV → LV → filesystem"]
    F --> I["df -hT + app read/write test"]
    G --> I
    H --> I
~~~

### Bước 1 — Tạo snapshot trước thay đổi

Từ máy điều khiển dùng `gcloud`:

~~~bash
SNAPSHOT="app-data-before-grow-20261119"

gcloud compute snapshots create "$SNAPSHOT" \
  --source-disk="$DISK" \
  --source-disk-zone="$ZONE"
~~~

**Snapshot không mặc nhiên application-consistent.** Với database hoặc dữ liệu ghi liên tục, cần cơ chế quiesce/backup phù hợp và kiểm thử restore; chỉ tạo snapshot khi ứng dụng đang ghi có thể cho một bản sao nhất quán ở cấp crash nhưng không bảo đảm transaction cấp ứng dụng. Snapshot chứa dữ liệu nhạy cảm phải được kiểm soát IAM, encryption và retention.

### Bước 2 — Resize disk ở Compute Engine

~~~bash
# TĂNG dung lượng từ 100 lên 200 GiB.
gcloud compute disks resize "$DISK" \
  --size=200GB \
  --zone="$ZONE"

gcloud compute disks describe "$DISK" \
  --zone="$ZONE" \
  --format="yaml(name,sizeGb,status)"
~~~

Trên Console: **Compute Engine → Storage → Disks → app-data → Edit → Size = 200 GiB → Save**. Kiểm tra operation thành công trước khi thao tác filesystem.

**Lưu ý:** không thể giảm trực tiếp kích thước Persistent Disk. Muốn giảm phải tạo disk nhỏ khác, copy dữ liệu sang sau khi kiểm tra dung lượng thực, xác minh ứng dụng hoạt động rồi mới ngừng disk cũ. Trong Terraform, đặt `size` nhỏ hơn có thể gây **destroy/recreate** disk, làm mất dữ liệu; luôn kiểm tra `terraform plan` và dùng `prevent_destroy` khi phù hợp.

### Bước 3 — Grow ext4 trên raw disk (lab không có partition)

Trong VM:

~~~bash
DEV="/dev/disk/by-id/google-app-data"
MOUNT_DIR="/mnt/disks/app-data"

lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
df -hT "$MOUNT_DIR"

# Chỉ đúng nếu ext4 nằm TRỰC TIẾP trên raw disk, không có partition/LVM.
sudo resize2fs "$DEV"

df -hT "$MOUNT_DIR"
findmnt "$MOUNT_DIR"
~~~

Với ext4, `resize2fs` có thể **mở rộng online** trên filesystem đang mount khi các điều kiện hỗ trợ được đáp ứng. Dữ liệu cũ không bị xóa do thao tác grow đúng; nhưng sai device, partition hoặc lỗi I/O vẫn có rủi ro. Cần so sánh dung lượng trước/sau và thử ghi/đọc một file mẫu.

**Nếu VM đã dùng public Google-provided Linux image và tăng boot disk:** Compute Engine thường tự mở rộng root filesystem của boot disk; với custom image hoặc cấu hình đặc biệt, bạn có thể cần tự grow partition/filesystem. Không áp quy trình data disk raw ở trên lên boot disk có partition.

## 8. Nếu disk có partition hoặc LVM thì làm sao?

Không phải VM nào cũng dùng filesystem trực tiếp trên raw disk. Một disk có thể chứa một hoặc nhiều partition, và các partition có thể là **physical volume (PV)** của **Logical Volume Manager (LVM)**. Hãy đọc sơ đồ thực bằng `lsblk -f` và `pvs; vgs; lvs` trước khi thao tác.

### Tình huống A — ext4 nằm trên partition

~~~text
/dev/sdb             200 GiB  ← block disk đã được tăng
└── /dev/sdb1         100 GiB  ← partition vẫn kích thước cũ
    └── ext4          100 GiB  ← filesystem vẫn kích thước cũ
        └── /data
~~~

Phải mở rộng **partition trước**, rồi mới mở rộng **filesystem**. Ví dụ minh họa với thiết bị có thật là `/dev/sdb` và partition số 1, chứa ext4:

~~~bash
# KIỂM TRA TRƯỚC: thiết bị /dev/sdb phải là đúng data disk, GPT/partition phù hợp.
lsblk -f /dev/sdb
sudo parted /dev/sdb print

# growpart thường thuộc gói cloud-guest-utils.
# Chỉ chạy khi partition số 1 là partition cần mở rộng.
sudo growpart /dev/sdb 1

# ext4 nằm trên partition, không phải raw disk.
sudo resize2fs /dev/sdb1

df -hT /data
~~~

Lệnh trên **không tự áp dụng** cho mọi cấu hình: trên máy dùng NVMe, thiết bị có thể là `/dev/nvme0n2` và partition `/dev/nvme0n2p1`; với boot disk, layout có thể gồm EFI, root và các partition khác. Hệ điều hành có thể yêu cầu rescan partition table hoặc restart trong một số trường hợp không thể cập nhật partition đang sử dụng. Nếu thứ tự partition/thiết bị khác hoặc còn dữ liệu quan trọng, không chạy theo ví dụ khi chưa có backup và kế hoạch thay đổi.

### Tình huống B — XFS

Với XFS, sau khi tăng block disk và partition (nếu có), mở rộng filesystem bằng **mount point**, không dùng `resize2fs`:

~~~bash
# Giả định filesystem XFS đã mount ở /data và block layer đã được mở rộng.
findmnt /data
sudo xfs_growfs /data
df -hT /data
~~~

XFS hỗ trợ **grow online** khi đang mount và không hỗ trợ shrink theo cách thông thường. Cần công cụ `xfsprogs` phù hợp. Nếu `xfs_growfs` báo không thay đổi dung lượng, xác minh disk/partition đã tăng và mount point thật sự là XFS.

| Filesystem | Lệnh mở rộng chính | Đầu vào |
|---|---|---|
| **ext4** | `resize2fs /dev/THIET_BI` | Block device/partition chứa ext4 |
| **XFS** | `xfs_growfs /diem-mount` | Mount point của XFS đang mount |
| **btrfs** | `btrfs filesystem resize max /diem-mount` | Mount point, sau khi block layer đã tăng |
| **NTFS trên Windows** | Disk Management hoặc PowerShell `Resize-Partition` | Volume Windows, không chạy lệnh Linux |

**Không dùng `mkfs` để “mở rộng” filesystem.** `mkfs` là thao tác tạo filesystem và có thể làm mất toàn bộ dữ liệu cũ.

### Tình huống C — Disk dùng LVM

~~~text
Persistent Disk (200 GiB)
  └── Partition /dev/sdb1 (200 GiB)
       └── Physical Volume (PV)
            └── Volume Group: vg_app
                 └── Logical Volume: lv_data
                      └── ext4 /data
~~~

Sau khi tăng disk 100 → 200 GiB và **partition** (nếu PV nằm trên partition), cần:

1. Tăng kích thước PV bằng `pvresize`.
2. Phân bổ dung lượng rảnh trong volume group cho LV bằng `lvextend`.
3. Mở rộng filesystem trong LV bằng công cụ phù hợp.

Ví dụ minh họa cho đúng layout trên:

~~~bash
sudo pvs
sudo vgs
sudo lvs

# Chỉ nếu /dev/sdb1 là PV và partition cần được grow.
sudo growpart /dev/sdb 1
sudo pvresize /dev/sdb1

# -r yêu cầu lvm thử resize filesystem cùng LV.
# Lệnh bên dưới dùng toàn bộ dung lượng còn trống trong VG: cần review trước!
sudo lvextend -l +100%FREE -r /dev/vg_app/lv_data

sudo lvs
df -hT /data
~~~

**Không chạy `lvextend` vào một tên LV đoán từ ví dụ.** Trên máy thật, PV có thể nằm trực tiếp trên raw disk, nhóm có nhiều LV hoặc còn vùng trống cần dành cho volume khác. Nếu `-r` không hỗ trợ filesystem/điều kiện hiện tại, phải thực hiện bước filesystem riêng theo tài liệu hệ điều hành. LVM tạo sự linh hoạt nhưng **không loại bỏ yêu cầu backup**.

## 9. Hyperdisk: dung lượng và IOPS/throughput có thể là hai cấu hình riêng

Với **Hyperdisk**, ngoài kích thước GiB, một số loại volume cho phép đặt **provisioned IOPS** và/hoặc **provisioned throughput**. Đây là khác biệt quan trọng so với việc chỉ tăng size để tối ưu Persistent Disk truyền thống.

| Loại Hyperdisk | Hiệu năng có thể điều chỉnh theo tính năng | Điều cần kiểm tra |
|---|---|---|
| **Balanced** | Provisioned IOPS và throughput | Machine type hỗ trợ và giới hạn theo dung lượng |
| **Extreme** | Provisioned IOPS | Hạn mức IOPS, loại máy và chi phí |
| **Throughput** | Provisioned throughput | Workload tuần tự, giới hạn throughput |
| **Balanced High Availability** | Provisioned IOPS/throughput tùy hỗ trợ | Phạm vi regional, replica và quy trình failover |
| **ML** | Provisioned throughput theo khả năng hỗ trợ | Mode truy cập và đặc tính workload |

Ví dụ khái niệm với một **Hyperdisk Balanced** tương thích:

~~~bash
# KHÔNG dùng trên disk loại Persistent Disk.
# Kiểm tra machine type và giá trị IOPS/throughput hợp lệ trước khi thực thi.
HYPERDISK="db-hyperdisk"

gcloud compute disks update "$HYPERDISK" \
  --zone="$ZONE" \
  --size=500GB \
  --provisioned-iops=10000 \
  --provisioned-throughput=500
~~~

Các giá trị chỉ là **minh họa**, không cam kết hợp lệ cho mọi loại máy/zone/dung lượng. Với Hyperdisk Balanced HA dạng regional, lệnh dùng `--region` và cấu hình tương ứng. Có giới hạn tần suất thay đổi performance và thời gian chờ để hiệu lực cập nhật; kiểm tra tài liệu của từng loại disk trước khi thao tác.

**Vẫn cần mở rộng filesystem trong guest OS** sau khi tăng kích thước Hyperdisk, tương tự Persistent Disk. Nếu volume ở multi-writer mode, phải tuân quy trình đồng bộ với tất cả VM và filesystem cluster-aware; không dùng ví dụ raw ext4 trên nhiều writer.

## 10. Tách, gắn lại và xóa disk đúng cách

Khi chuyển data disk từ một VM sang VM khác cùng zone (theo điều kiện của disk), hãy ưu tiên quy trình có kiểm soát:

1. Dừng ứng dụng ghi vào mount point, bảo đảm job/batch đã hoàn tất.
2. Xác nhận backup/snapshot nếu dữ liệu quan trọng.
3. Trong VM cũ, kiểm tra tiến trình đang giữ file rồi `umount`.
4. **Xóa hoặc comment entry liên quan trong `/etc/fstab`** của VM cũ trước khi reboot.
5. Detach disk khỏi VM cũ bằng Compute Engine API/CLI.
6. Attach disk vào VM mới với mode phù hợp; **không chạy `mkfs`** lên disk đã có filesystem.
7. Xác minh UUID, mount point, quyền truy cập và dữ liệu trước khi mở ứng dụng trên VM mới.

Ví dụ trong VM cũ:

~~~bash
MOUNT_DIR="/mnt/disks/app-data"

# Xem tiến trình còn giữ file ở mount point.
sudo fuser -vm "$MOUNT_DIR"

# Chỉ unmount sau khi ứng dụng đã ngừng ghi.
sync
sudo umount "$MOUNT_DIR"

# Chỉnh /etc/fstab: comment hoặc xóa dòng có UUID của disk trước khi reboot.
sudo nano /etc/fstab
~~~

Trên máy điều khiển:

~~~bash
# Data disk zonal, không phải boot disk.
gcloud compute instances detach-disk "$VM" \
  --zone="$ZONE" \
  --disk="$DISK"

# Đọc lại tình trạng attached users trước khi quyết định làm tiếp.
gcloud compute disks describe "$DISK" \
  --zone="$ZONE" \
  --format="yaml(name,status,users)"
~~~

Khi tách và gắn lại với VM khác, dùng `gcloud compute instances attach-disk` với tên VM mới và device name đã chọn. Nếu disk/VM không nằm cùng zone, không thể coi lệnh attach như một cách di chuyển tự động cross-zone; cần snapshot/restore hoặc giải pháp di chuyển hỗ trợ.

### Detach khác delete

- **Unmount**: ngắt filesystem khỏi cây thư mục của OS; disk vẫn gắn với VM.
- **Detach**: gỡ kết nối block device khỏi VM; tài nguyên disk vẫn tồn tại trong Google Cloud.
- **Delete disk**: xóa tài nguyên lưu trữ và dữ liệu, không phải “ngừng tính phí tạm thời”.
- **Delete VM**: có thể tự xóa boot disk hoặc data disk nếu `autoDelete` được bật; phải xem cấu hình thực tế trước khi xóa.
- **Delete filesystem files**: xóa nội dung trong guest OS, không làm giảm kích thước **provisioned disk** được tính phí.

Disk **đã detach nhưng còn tồn tại** vẫn thường chịu chi phí lưu trữ. Đừng xóa disk chỉ để giảm chi phí khi chưa xác nhận ownership, retention policy và snapshot hợp lệ.

## 11. Khi cần chia sẻ filesystem: Filestore và NFS

Một Persistent Disk format ext4/XFS phù hợp khi một VM sở hữu filesystem theo phương án single-writer thông thường. Nhưng nếu ba VM cùng cần đọc/ghi một cây thư mục POSIX, tốt hơn nên xem xét **Filestore**, dịch vụ file storage qua NFS.

~~~mermaid
flowchart LR
    A["VM ứng dụng A"] --> D["Filestore NFS share"]
    B["VM ứng dụng B"] --> D
    C["GKE Pods qua CSI driver"] --> D
    D --> E["Filesystem được quản lý và chia sẻ qua VPC"]
~~~

**So sánh block disk và NFS:**

| Câu hỏi | Persistent Disk/Hyperdisk | Filestore |
|---|---|---|
| Thao tác trong guest OS | Nhận block device, format/mount filesystem | Mount NFS export; không format block device |
| Nhiều client cùng đọc/ghi tệp | Cần mode/filesystem chuyên biệt nếu multi-writer | Được thiết kế cho multi-client NFS theo cấu hình |
| Quyền truy cập file | Linux permissions/ACL tùy filesystem | POSIX permission và cơ chế NFS, kết hợp network controls |
| Mở rộng | Tăng block disk rồi grow partition/FS nếu cần | Đổi capacity của Filestore instance theo tier/quy định |
| Đường kết nối | Disk gắn ở hạ tầng VM | IP private trong VPC, firewall và NFS mount |
| Trường hợp dùng | Data disk ứng dụng, block I/O | Dữ liệu file chia sẻ, home directory, ứng dụng cần filesystem chung |

### Ví dụ mount share trên VM Linux

Giả sử Filestore instance đã có IP private `10.0.1.2` và share name `share1`; VM có VPC route và firewall cho NFS:

~~~bash
# Debian/Ubuntu; phải có mạng đến apt repository hoặc mirror phù hợp.
sudo apt-get update
sudo apt-get install -y nfs-common

sudo mkdir -p /mnt/shared

# IP và share chỉ để minh họa; phải thay bằng Filestore thật.
sudo mount -t nfs -o rw,tcp \
  10.0.1.2:/share1 /mnt/shared

findmnt /mnt/shared
df -hT /mnt/shared
~~~

Nếu muốn mount khi VM khởi động, cấu hình `/etc/fstab` sau khi đã xác minh network và NFS mount hoạt động:

~~~fstab
10.0.1.2:/share1 /mnt/shared nfs defaults,_netdev,nofail 0 0
~~~

`_netdev` giúp hệ thống nhận biết đây là network filesystem. Các lựa chọn `nconnect`, NFS version, timeout và tính năng lock phụ thuộc tier Filestore, Linux kernel và workload. Với GKE, dùng **Filestore CSI driver** hoặc cách tích hợp được hỗ trợ thay vì SSH vào node mount thủ công.

**Cảnh báo:** Filestore dùng NFS nên phải thiết kế mạng private, firewall, quyền POSIX, file locking và backup theo yêu cầu. NFS share không phải “đĩa cứng ẩn” mà bạn cần chạy `fdisk` hay `resize2fs`. Ngay cả khi nhiều VM có chung file, ứng dụng vẫn phải xử lý concurrency và trạng thái giao dịch phù hợp.

## 12. Bảo vệ dữ liệu: snapshot, backup và phục hồi

Mở rộng disk hoặc sửa partition có thể thực hiện online trong nhiều trường hợp, nhưng **không có thao tác nào thay thế backup**.

| Biện pháp | Mục đích | Không nên hiểu nhầm |
|---|---|---|
| **Persistent Disk snapshot** | Bản sao điểm thời gian của block disk, hỗ trợ tạo disk mới/khôi phục | Không tự bảo đảm application-consistent cho database đang ghi |
| **Snapshot schedule** | Tạo snapshot theo lịch và giữ theo retention | Phải kiểm tra lịch, quyền, thời hạn và khả năng restore |
| **Application/database backup** | Giữ bản sao logic có thể restore theo giao dịch | Không đồng nghĩa chỉ có một disk snapshot là đủ |
| **Regional disk replication** | Bảo vệ khỏi một số lỗi hạ tầng/zone | Không chống xóa nhầm file do ứng dụng hoặc ransomware |
| **Filestore backup/snapshot** | Bảo vệ share theo khả năng của tier | Không nên áp lệnh PD snapshot lên Filestore |
| **Offsite/khác vùng/quyền riêng** | Giảm rủi ro hủy hoại cùng một phạm vi | Cần xét nơi lưu, chính sách dữ liệu và chi phí |

Tạo một snapshot không kiểm chứng restore vẫn để lại rủi ro. Định kỳ thực hành:

1. Chọn snapshot đã được xác định là hợp lệ.
2. Tạo disk **mới** từ snapshot ở môi trường kiểm thử.
3. Attach **read-only** nếu phù hợp hoặc gắn ở một VM cách ly.
4. Kiểm tra filesystem, file quan trọng và logic khôi phục ứng dụng.
5. Ghi lại thời gian phục hồi (RTO) và mức dữ liệu mất cho phép (RPO) theo yêu cầu hệ thống.

Với hệ thống dữ liệu quan trọng, nên dùng giải pháp backup chuyên biệt có thể quiesce/flush dữ liệu ở cấp ứng dụng và tuân thủ lịch backup/retention đã phê duyệt.

## 13. IAM, mã hóa và quyền trong hệ điều hành

Trong Google Cloud, bảo mật disk có ít nhất ba lớp:

1. **Control plane IAM:** ai được tạo, attach, detach, resize, snapshot hoặc xóa disk.
2. **Encryption/keys:** dữ liệu at rest được mã hóa theo cơ chế Google Cloud; có thể sử dụng customer-managed encryption keys (CMEK) khi quy định yêu cầu.
3. **Guest OS permissions:** ai có thể đọc/ghi thư mục đã mount bằng Unix user/group, ACL hoặc chính sách của ứng dụng.

| Vai trò công việc | Quyền cần xem xét | Cách giới hạn |
|---|---|---|
| Storage/platform operator | `compute.disks.create`, `compute.disks.update`, `compute.disks.delete` và snapshot permissions khi cần | Vai trò quản lý Compute Disk/Storage trong project được phép |
| VM operator | `compute.instances.attachDisk` / `detachDisk` và quyền tương ứng trên disk | Chỉ VM/disk phục vụ nhiệm vụ |
| Security/KMS administrator | Quản lý khóa và cấp quyền sử dụng key theo mô hình CMEK | Không trộn với mọi quyền vận hành VM |
| Guest OS administrator | Partition, mount, fsck, chỉnh fstab | Dùng sudo có kiểm toán, hạn chế SSH |
| Application service account | Quyền API Cloud Storage/Secret Manager nếu workload cần | Không có quyền xóa/sửa disk nếu không cần |

Một role quản trị rộng như `roles/compute.storageAdmin` hoặc `roles/compute.instanceAdmin.v1` có thể chứa nhiều quyền ngoài thao tác đơn lẻ. Ưu tiên predefined role nhỏ hơn hoặc custom role theo permission thực tế; xem **IAM kế thừa từ Folder/Organization** trước khi cấp thêm. Quyền sửa filesystem trong guest OS không xuất phát trực tiếp từ `roles/compute.storageAdmin`; nó còn phụ thuộc quyền đăng nhập VM và sudo.

### Mã hóa và xóa

- Persistent Disk và Hyperdisk được mã hóa at rest mặc định. **CMEK** bổ sung quyền quản lý khóa và rủi ro nếu khóa bị vô hiệu hóa/không được cấp quyền dùng; cần lập kế hoạch key rotation và recovery.
- Dữ liệu nhạy cảm trong snapshot/backup phải được bảo vệ tương tự bản gốc.
- Trước khi delete VM hoặc dùng Terraform destroy, xem `autoDelete`, các disk attachment, snapshot giữ lại và chính sách retention.
- Khi dùng Terraform, kiểm tra `plan` trước các thay đổi loại disk/kích thước; `lifecycle.prevent_destroy = true` có thể giúp bảo vệ tài nguyên dữ liệu quan trọng khỏi bị replace vô tình.
- Với Filestore, **quyền NFS/POSIX và firewall** quan trọng: client có đường mạng không tự đồng nghĩa có quyền ghi mọi file.

## 14. Theo dõi filesystem, I/O và cảnh báo dung lượng

Quản lý disk không kết thúc sau khi mount thành công. Cần quan sát cả **disk cấp Cloud**, **filesystem** và **ứng dụng**.

### Trong guest Linux

~~~bash
# Tổng quan disk/partition/filesystem.
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
df -hT
df -i
findmnt /mnt/disks/app-data

# Dung lượng thư mục trong cùng một filesystem.
sudo du -xsh /mnt/disks/app-data/*

# Kiểm tra journal khi thấy lỗi I/O.
sudo dmesg --level=err,warn | tail -n 40

# Nếu sysstat đã cài, quan sát IOPS/latency theo block device:
iostat -xz 1 5
~~~

Không suy luận disk hỏng chỉ từ việc `df` báo đầy. Một số nguyên nhân khác:

- **Inode exhaustion:** hàng triệu file nhỏ làm hết inode trong ext4 dù `df -h` còn GB trống.
- **File đã xóa nhưng còn process mở:** dung lượng vẫn bị giữ cho đến khi process đóng descriptor; có thể dùng `lsof +L1` để phân tích khi được phép.
- **Mount sai:** ứng dụng ghi vào thư mục trên boot disk vì data disk chưa mount; kiểm tra `findmnt` và `fstab`.
- **Permission denied:** Unix ownership/ACL, mount read-only hoặc policy của application.
- **I/O latency cao:** workload ngẫu nhiên, disk type, vCPU limit, throughput/IOPS, queue depth hoặc database behavior.
- **Quota/capacity:** không tạo được disk mới hoặc không đủ disk limit/attach limit cho VM.

### Cloud Monitoring và cảnh báo

Cloud Monitoring cung cấp metric disk bytes, I/O operations và độ trễ theo loại máy/disk tương ứng; Ops Agent/guest monitoring hỗ trợ đo filesystem utilization bên trong VM. Đặt alert:

| Chỉ số | Tín hiệu |
|---|---|
| Filesystem used % / free bytes | Nguy cơ hết dung lượng trong vài ngày |
| Free inodes | Hệ thống có thể không tạo thêm file |
| Read/write bytes và operations | Tải thực tế, phát hiện đột biến |
| I/O latency / queue depth | Ứng dụng có bottleneck I/O |
| Disk resize/snapshot operations | Hoạt động quản trị bất thường hoặc thất bại |
| Backup age / snapshot schedule | Không có bản sao gần thời điểm yêu cầu |
| Chi phí provisioned GiB và performance | Dung lượng cấp dư hoặc Hyperdisk IOPS/throughput cao |

Một cảnh báo `filesystem used > 85%` chỉ là ví dụ: ngưỡng tốt phụ thuộc tốc độ tăng dữ liệu, mức độ quan trọng và thời gian cần để mở rộng. Với `/var/lib` hoặc data disk của database, cần cảnh báo theo **dự báo ngày sẽ đầy**, không chỉ một ngưỡng cố định.

## 15. Chi phí và lựa chọn kiến trúc lưu trữ

Disk thường được tính phí theo **dung lượng được cấp phát**, không phải chỉ số GB dữ liệu `du` đang dùng. Nếu tăng từ 100 lên 200 GiB, phần dung lượng được cấp phát tăng có thể làm chi phí tăng ngay cả khi filesystem vẫn chỉ dùng 60 GiB. Một số loại Hyperdisk còn tính phí **provisioned IOPS/throughput**; snapshot và network/storage service cũng có phí riêng.

| Thành phần | Yếu tố tính phí | Cách tối ưu |
|---|---|---|
| Persistent Disk | Disk type, provisioned GiB, zone/region | Chọn tier và size theo workload; xóa disk không dùng sau khi backup |
| Hyperdisk | Provisioned GiB và các thông số performance tương ứng | Đo nhu cầu thật, tránh giữ IOPS/throughput cao không cần |
| Snapshot | Dung lượng snapshot được lưu và retention | Lịch giữ hợp lý; kiểm chứng restore |
| Regional disk | Loại disk/replication theo region | Chỉ dùng khi yêu cầu khả dụng cần thiết |
| Filestore | Tier, capacity, hiệu năng và thời gian tồn tại | Dùng cho multi-client POSIX thật sự cần NFS |
| Network/backup/logging | Truyền dữ liệu, backup, log/metric | Theo dõi các SKU phát sinh phụ trợ |

**Phân tích nhu cầu trước khi resize:** filesystem thiếu chỗ có thể do log không rotate, file tạm không dọn hoặc backup sai vị trí. Tăng disk liên tục mà không xử lý nguyên nhân sẽ tạo chi phí kéo dài. Ngược lại, xóa file có thể giảm `du`/`df` nhưng không tự giảm provisioned disk size được tính phí.

Nếu cần giảm từ 200 về 100 GiB, **không thể thu nhỏ Persistent Disk tại chỗ**. Phải tạo disk mới đủ chứa dữ liệu, copy/restore, thử ứng dụng, chuyển mount và ngừng disk cũ khi an toàn. Với XFS, càng không nên hứa thu nhỏ filesystem trực tiếp.

Budget alerts trong Cloud Billing giúp kiểm soát chi phí nhưng **không tự xóa disk hoặc dừng tài nguyên**. Cần quy trình inventory cho disk/snapshot không có owner, retention và quyết định dọn dẹp.

## 16. Tình huống: API Java hết dung lượng data disk

Doanh nghiệp chạy API Java trên VM Compute Engine:

~~~text
Client → External Application Load Balancer
              ↓
        Compute Engine VM
        ├── Boot disk 40 GiB (OS + JVM)
        └── Data disk 100 GiB (ext4 → /srv/app/data)
              ├── Upload tạm
              ├── Báo cáo sinh ra
              └── Cache của ứng dụng
              ↓
         Cloud Storage / Cloud SQL
~~~

Khi monitoring báo data filesystem đạt 88% và tăng nhanh, đội vận hành:

1. Kiểm tra `df -hT`, `df -i`, `du -xsh`, xác nhận app không ghi nhầm vào boot disk.
2. Kiểm tra tăng trưởng dữ liệu và retention; chuyển các file upload bền vững sang Cloud Storage nếu phù hợp, không coi data disk riêng của VM là kho dùng chung cho nhiều instance.
3. Xác nhận disk là `pd-balanced` zonal, filesystem ext4 đặt **trực tiếp trên raw block device**.
4. Tạo snapshot/backup, xác minh khả năng restore.
5. Dùng `gcloud compute disks resize` tăng 100 → 200 GiB.
6. Trên VM, kiểm tra `lsblk` và chạy `resize2fs` trên **đúng device**; kiểm tra `df -hT`.
7. Chạy một request tạo báo cáo thật, đọc lại file; theo dõi disk latency và error rate.
8. Điều chỉnh retention, cảnh báo, ngân sách và ghi change record.

Nếu API được mở rộng bằng Managed Instance Group nhiều VM, **mỗi VM có thể có disk riêng**, không phải một data disk ext4 ghi chung. File upload bền vững nên được chuyển sang Cloud Storage/Filestore hoặc một kiến trúc dữ liệu chia sẻ phù hợp; database nên có backup/HA riêng. Với ứng dụng container trên GKE, dùng PersistentVolume/PersistentVolumeClaim theo CSI driver được hỗ trợ; với Cloud Run, không giả định có thể attach Compute Engine Persistent Disk vào container như một VM thông thường.

### Khi nào cần tăng disk, khi nào cần đổi dịch vụ?

| Tình huống | Hướng phù hợp |
|---|---|
| Một VM cần thêm dung lượng cho filesystem cục bộ | Resize Persistent Disk và grow FS |
| Nhiều VM cần cùng đọc/ghi cây thư mục POSIX | Filestore/NFS theo yêu cầu locking/hiệu năng |
| Ảnh/tài liệu upload cần bền vững và truy cập qua nhiều instance | Cloud Storage và SDK/API |
| Database cần replication, HA, backup giao dịch | Dịch vụ database quản lý hoặc hệ thống dữ liệu chuyên biệt |
| Cache có thể tạo lại, rất nhạy latency | Local SSD hoặc memory cache theo khả năng chịu mất dữ liệu |
| Block I/O cần IOPS/throughput mục tiêu điều chỉnh riêng | Hyperdisk tương thích machine type và ngân sách |

## 17. Checklist trước khi tạo hoặc resize disk production

- [ ] Xác nhận project, zone/region, VM, disk name, owner và nguồn chi phí.
- [ ] Kiểm tra disk type và mức tương thích machine type/zone.
- [ ] Ghi nhận đúng **block device** qua `/dev/disk/by-id`, không đoán `sdb`.
- [ ] Xác định disk trống hay đã có dữ liệu trước mọi lệnh `mkfs`.
- [ ] Xác định raw filesystem, GPT partition, LVM hay lớp khác bằng `lsblk`, `blkid` và công cụ tương ứng.
- [ ] Có snapshot/backup và kế hoạch kiểm chứng restore/rollback.
- [ ] Biết kích thước đích và xác nhận **chỉ tăng**, không vô tình yêu cầu thu nhỏ.
- [ ] Sau khi resize Cloud disk, đã grow đúng partition/PV/LV/filesystem.
- [ ] Kiểm tra `df -hT`, `findmnt` và thực hiện app read/write test.
- [ ] `fstab` dùng UUID/by-id đúng, kiểm tra `mount -a` trước reboot.
- [ ] Data disk auto-delete, encryption, IAM và lưu trữ backup đã được rà soát.
- [ ] Không mount ext4/XFS concurrent write trên nhiều VM theo cách không được hỗ trợ.
- [ ] Có theo dõi filesystem used %, inode, I/O latency và snapshot age.
- [ ] Có kế hoạch dừng ứng dụng/unmount/đổi disk khi cần; không tách disk đang ghi.
- [ ] Chi phí disk provisioned, Hyperdisk performance, Filestore và snapshots đã được dự toán.

**Bài tập thực hành:** Một VM chạy ứng dụng Java có data disk 100 GiB; nhóm muốn lên 250 GiB. Có ba biến thể:

1. **ext4 trên raw disk:** nêu thứ tự các bước Cloud resize, Linux resize và lệnh xác minh.
2. **ext4 trên GPT partition số 1:** phân biệt `growpart` với `resize2fs`; giải thích vì sao bỏ bước partition sẽ không thấy hết dung lượng.
3. **XFS trên LVM:** vẽ chuỗi disk → partition → PV → VG → LV → XFS; liệt kê công cụ cần dùng ở mỗi tầng và điều kiện của `xfs_growfs`.

Sau đó giải thích: (4) vì sao snapshot không tự bảo đảm backup giao dịch của database; (5) tại sao không được gắn cùng một ext4 read/write vào hai VM chỉ vì block disk có hỗ trợ multi-writer; (6) cách chuyển sang Filestore nếu ba VM cần chia sẻ file; (7) vì sao hóa đơn tăng dù `du` vẫn thấp; và (8) kiểm tra nào giúp tránh reboot lỗi do `/etc/fstab`.

## Tài liệu tham khảo chính thức

- [Create a Persistent Disk volume](https://cloud.google.com/compute/docs/disks/add-persistent-disk) — tạo và attach disk vào VM.
- [Format and mount a non-boot disk on Linux](https://cloud.google.com/compute/docs/disks/format-mount-disk-linux) — filesystem, `/dev/disk/by-id` và `/etc/fstab`.
- [Resize Persistent Disk](https://cloud.google.com/compute/docs/disks/resize-persistent-disk) — mở rộng disk, partition, ext4/XFS và các giới hạn.
- [Modify Hyperdisk size and performance](https://cloud.google.com/compute/docs/disks/modify-hyperdisks) — Hyperdisk capacity, provisioned IOPS/throughput.
- [Persistent Disk and Hyperdisk overview](https://cloud.google.com/compute/docs/disks) — loại disk, hiệu năng và tính năng.
- [Detach and reattach disks](https://cloud.google.com/compute/docs/disks/detach-reattach-boot-disk) — tháo/gắn và lưu ý auto-delete/guest OS.
- [Create and manage disk snapshots](https://cloud.google.com/compute/docs/disks/create-snapshots) — bảo vệ dữ liệu và snapshot.
- [Schedule disk snapshots](https://cloud.google.com/compute/docs/disks/scheduled-snapshots) — lịch snapshot và retention.
- [Mount Filestore shares on Compute Engine](https://cloud.google.com/filestore/docs/mounting-fileshares) — NFS client, `fstab`, networking.
- [Filestore overview](https://cloud.google.com/filestore/docs/overview) — file storage và các tier.
- [Compute Engine disk pricing](https://cloud.google.com/compute/disks-image-pricing) — storage, performance và snapshots.
- [Filestore pricing](https://cloud.google.com/filestore/pricing) — file share theo tier/capacity.
