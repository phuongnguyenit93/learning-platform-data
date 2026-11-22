# Thực hành đo hiệu năng và phục hồi dữ liệu đĩa

> **Chương:** Lưu trữ khối và tệp  
> **Module:** CLOUD_PROVIDERS_GCP  
> **Phạm vi module:** Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Khi một ứng dụng trên Compute Engine đọc file dữ liệu, ghi nhật ký hay vận hành cơ sở dữ liệu, hiệu năng đĩa tác động trực tiếp tới thời gian phản hồi. Tuy nhiên, “đĩa 100 GB” chưa cho biết số lần đọc/ghi mỗi giây, lượng dữ liệu truyền mỗi giây hay độ trễ thực tế. Cùng một loại đĩa có thể cho kết quả khác nhau khi kích thước, loại VM, số vCPU, kích thước I/O và độ song song thay đổi.

Khả năng **phục hồi dữ liệu** cũng không tự xuất hiện chỉ vì sử dụng Persistent Disk hoặc Hyperdisk. Đĩa bền vững giúp dữ liệu tồn tại qua một số sự kiện vòng đời của VM, nhưng thao tác xóa nhầm, lỗi ứng dụng hoặc mã độc có thể khiến dữ liệu bị sửa/hủy. Cần có **snapshot hoặc phương án backup riêng**, và quan trọng hơn, phải **thử khôi phục** để chứng minh bản sao có thể sử dụng.

Bài này kết hợp hai kỹ năng: **đo IOPS/throughput/latency với `fio`** trên một đĩa lab độc lập và **tạo snapshot → phục hồi sang đĩa khác → kiểm tra checksum**. Mọi thao tác có thể ghi/xóa dữ liệu được giới hạn rõ vào tài nguyên thử nghiệm.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Chọn đúng vai trò của **Persistent Disk**, **Hyperdisk**, **Local SSD** và **Filestore** khi đánh giá hiệu năng và khả năng phục hồi.
2. Phân biệt **IOPS**, **throughput**, **latency**, **block size**, **queue depth** và cache; giải thích vì sao kết quả benchmark thay đổi.
3. Xác định đĩa dữ liệu an toàn từ Compute Engine và Linux, tránh nhầm **boot disk** với đĩa lab.
4. Dùng `fio` thực hiện phép thử đọc/ghi tuần tự và đọc/ghi ngẫu nhiên trên **file riêng** mà không ghi thẳng vào raw block device.
5. Giải thích tác động của kích thước disk, VM machine type, vCPU, I/O profile và giới hạn provisioned performance.
6. Tạo snapshot **sau khi đồng bộ và ngừng ghi**, tạo đĩa mới từ snapshot, gắn vào VM và xác minh file/checksum.
7. Lập kế hoạch backup/restore với **RPO**, **RTO**, chi phí, phân quyền, mã hóa và quy trình dọn tài nguyên.

## 1. Chọn đúng loại lưu trữ trước khi đo

Compute Engine có những hình thức lưu trữ khác nhau, nên phải xác định **đang benchmark loại nào**:

| Loại lưu trữ | Cách dùng chính | Hiệu năng | Phục hồi / lưu ý |
|---|---|---|---|
| **Persistent Disk (`pd-standard`, `pd-balanced`, `pd-ssd`...)** | Block disk cho VM; boot hoặc data | Tùy loại, kích thước, số vCPU và giới hạn VM | Có thể tạo disk snapshot, tạo disk mới từ snapshot |
| **Hyperdisk** | Block disk có khả năng tùy chỉnh hiệu năng theo loại (Balanced, Extreme, Throughput...) | IOPS/throughput được provision theo tính năng và bị giới hạn bởi VM | Có cơ chế snapshot/backup hỗ trợ; phải kiểm tra tương thích từng loại |
| **Local SSD** | Block storage cục bộ rất nhanh, dành cho scratch/cache | Thường độ trễ thấp, IOPS cao | **Không xem là bản sao bền vững**; dữ liệu có thể mất theo sự kiện vòng đời VM, không dùng quy trình disk snapshot như PD |
| **Filestore** | File share qua NFS cho nhiều client | Tùy tier, năng lực instance, mạng và client | Dùng chính sách backup/snapshot **của Filestore**, không dùng lệnh snapshot Compute Engine disk |
| **Cloud Storage** | Object storage qua API | Đo bằng request/throughput object, không phải raw block IOPS | Versioning, retention và backup theo mô hình object |

**Bài lab sử dụng `pd-balanced`** để dễ thực hành với VM tương thích, không nhằm tuyên bố đó là lựa chọn hiệu năng tốt nhất cho mọi hệ thống. Với các machine series mới chỉ hỗ trợ Hyperdisk, cần chọn loại disk phù hợp hoặc dùng VM lab tương thích với Persistent Disk.

### 1.1. Block storage khác file storage

**Block storage** xuất hiện trong hệ điều hành dưới dạng thiết bị, ví dụ `/dev/sdb` hoặc một tên NVMe. Người dùng tạo partition/filesystem, mount rồi ứng dụng đọc/ghi. **File storage** như Filestore cung cấp một filesystem chia sẻ qua NFS, client mount qua mạng; khách hàng không quản lý một thiết bị block độc lập có thể snapshot bằng `gcloud compute snapshots create`.

Vì vậy, đo `fio` trên thư mục NFS của Filestore có thể hữu ích khi tối ưu ứng dụng, nhưng kết quả chịu thêm ảnh hưởng của NFS protocol, mạng và nhiều client. Hướng dẫn snapshot đĩa trong bài **không áp dụng cho Filestore**.

### 1.2. Đĩa bền vững không đồng nghĩa backup

```text
Ứng dụng trên VM
   |
   +--> Persistent Disk / Hyperdisk: dữ liệu đang chạy
   |       |
   |       +--> Thao tác sửa/xóa nhầm vẫn có thể làm mất dữ liệu
   |
   +--> Disk snapshot: điểm khôi phục tại thời điểm T
           |
           +--> Tạo disk mới từ snapshot
                    |
                    +--> Mount, xác minh file/checksum, phục hồi dịch vụ
```

Regional disk hoặc cơ chế replicate cải thiện khả năng chịu một số lỗi hạ tầng, nhưng **không thay thế backup theo thời điểm**: thao tác xóa hoặc ghi sai có thể được phản ánh lên các replica.

## 2. Những chỉ số phải hiểu trước khi benchmark

### 2.1. IOPS, throughput, latency

| Chỉ số | Đơn vị | Câu hỏi được trả lời |
|---|---|---|
| **IOPS** | Operations/second | Đĩa thực hiện được bao nhiêu lần đọc/ghi mỗi giây? |
| **Throughput** | MiB/s hoặc MB/s (phải ghi rõ) | Mỗi giây đọc/ghi được bao nhiêu dữ liệu? |
| **Latency** | ms, µs; p50/p95/p99 | Mất bao lâu để một thao tác I/O hoàn tất? |
| **Block size** | 4 KiB, 64 KiB, 1 MiB... | Mỗi thao tác I/O chuyển bao nhiêu dữ liệu? |
| **Queue depth** | Số I/O chờ/đồng thời | Workload đưa bao nhiêu yêu cầu vào hàng đợi? |
| **Read/write mix** | Ví dụ 70% read / 30% write | Mức độ ưu tiên đọc/ghi của ứng dụng |
| **Random/sequential** | Truy cập ngẫu nhiên hoặc tuần tự | Mô hình I/O có tương tự database hay ghi file lớn? |

Công thức gần đúng trong một phép thử mà kích thước I/O nhất quán:

\[
\text{Throughput (MiB/s)} \approx
\frac{\text{IOPS} \times \text{block size (KiB)}}{1024}
\]

Ví dụ giả định **5.000 IOPS** ở **4 KiB** tương đương khoảng **19,5 MiB/s**. Cùng 5.000 IOPS ở **256 KiB** tương đương **1.250 MiB/s**, nếu hạ tầng và workload thực sự đạt được mức đó. **Không suy luận rằng một đĩa có thể duy trì cả hai cấu hình này** chỉ từ phép nhân: IOPS và throughput có trần riêng.

### 2.2. Latency thấp không phải lúc nào cũng đồng nghĩa IOPS cao

`fio` có thể báo:

- **`clat`**: completion latency của I/O, gồm thời gian chờ kết quả hoàn tất theo engine đo.
- **`slat`**: submission latency, thời gian chuẩn bị/đẩy I/O.
- **`lat`**: tổng thời gian được `fio` tính cho request.
- **Percentiles** như p95/p99: chỉ ra đuôi độ trễ, có ý nghĩa đặc biệt với ứng dụng nhạy latency.

Khi queue depth tăng, throughput/IOPS có thể tăng nhưng p99 latency cũng có thể xấu đi. Do vậy, không báo cáo chỉ một con số “IOPS tối đa” mà bỏ qua SLO độ trễ.

### 2.3. Tại sao cùng disk cho số khác nhau?

Hiệu năng quan sát thực tế có thể bị giới hạn bởi **một hoặc nhiều yếu tố**:

```text
Hiệu năng I/O đạt được
    <= Giới hạn của disk theo type / size / provisioned performance
    <= Giới hạn của VM machine type / vCPU / năng lực I/O
    <= Khả năng của filesystem, OS, queue, application và workload
```

Với **Persistent Disk**, kích thước disk, loại disk và loại VM/vCPU ảnh hưởng trần hiệu năng. Với **Hyperdisk**, có thể cấu hình IOPS/throughput riêng theo loại disk, nhưng hiệu năng thực tế vẫn bị giới hạn bởi machine series, khả năng tương thích và các trần áp dụng cho VM/tổng các disk. Đọc bảng giới hạn của chính xác loại disk và VM trước khi kết luận cần “nâng cấp đĩa”.

**Ví dụ:** nếu một VM quá nhỏ hoặc CPU bận, tăng hiệu năng provisioned của Hyperdisk không nhất thiết khiến workload nhanh hơn; bottleneck có thể nằm ở VM hoặc ứng dụng.

## 3. Thế nào là một benchmark đáng tin cậy?

Benchmark có giá trị khi điều kiện **lặp lại được**:

1. Ghi lại **project, zone, VM machine type, số vCPU, disk type, disk size, filesystem và cấu hình I/O**.
2. Dùng **đĩa dữ liệu lab riêng**, không ghi `fio` lên boot disk hoặc disk production.
3. Chỉ benchmark trong **một thư mục riêng**; không dùng `--filename=/dev/sdX` hay thiết bị block bất kỳ.
4. Thực hiện các test **sequential write/read** và **random read/write** tách biệt, báo cáo cùng block size/iodepth/numjobs/runtime.
5. Dùng `--direct=1` khi muốn giảm tác động **page cache của hệ điều hành**; vẫn phải hiểu các lớp cache phía dưới và hành vi filesystem có thể ảnh hưởng.
6. Có **warm-up/ramp time**, thời gian thử phù hợp, tránh kết luận từ một burst rất ngắn.
7. Không chạy nhiều test cạnh tranh I/O cùng lúc trừ khi đó là workload thật cần đánh giá.
8. Lặp phép đo và ghi **IOPS, throughput, p95/p99 latency**, CPU và tình trạng VM; công bố cả giới hạn của phép đo.

**Lưu ý an toàn:** `fio` có thể phá hủy dữ liệu nếu chọn sai `--filename`, `--directory`, `--rw` hoặc đường dẫn đích. Trong lab này, chỉ sử dụng **file mới dưới `/mnt/disk-lab`**. Không chạy trên filesystem dùng chung, thư mục dữ liệu thực, boot disk hoặc device raw.

### Các kiểu phép thử tương ứng ứng dụng

| Workload | `fio --rw` | Block size gợi ý | Chú ý |
|---|---|---|---|
| Đọc file dung lượng lớn | `read` | `1m` | Ưu tiên throughput; nguồn file phải tồn tại |
| Ghi file lớn | `write` | `1m` | Đo throughput ghi; chỉ ghi **file test** |
| Database OLTP | `randread` hoặc `randrw` | `4k` hoặc `8k` | IOPS, p95/p99 và read/write mix |
| Ghi nhật ký tuần tự | `write`/`append` tương ứng | Theo kích thước ứng dụng | Đo thêm fsync/durability nếu cần |
| Workload hỗn hợp | `randrw`, `rwmixread=70` | `4k`/`16k` | So sánh với profile ứng dụng thật |

Kết quả một synthetic benchmark **không tự đại diện** cho database production. Database có transaction log, index, cache, flush và concurrency riêng.

## 4. Chuẩn bị lab: chỉ dùng tài nguyên được phép

Bài thực hành chính giả định bạn đã có **một VM Linux sandbox** với quyền SSH/OS Login được phê duyệt. Ta sẽ tạo một **data disk mới**, định dạng và mount riêng, không động đến boot disk. Các lệnh tạo disk, snapshot và disk phục hồi **có thể phát sinh chi phí**.

### 4.1. Giá trị minh họa

| Biến | Giá trị ví dụ | Ý nghĩa |
|---|---|---|
| `PROJECT_ID` | `my-gcp-disk-lab` | Project sandbox |
| `ZONE` | `asia-southeast1-a` | Zone của VM và data disk |
| `VM_NAME` | `disk-test-vm` | VM Linux sẵn có, được phép thao tác |
| `DISK_NAME` | `bench-data-lab` | Disk mới chỉ dành cho benchmark |
| `RESTORE_DISK` | `bench-restored-lab` | Disk khôi phục từ snapshot |
| `SNAPSHOT_NAME` | `bench-data-lab-snap-01` | Snapshot của data disk |
| `DATA_DEVICE` | `/dev/disk/by-id/google-bench-data-lab` | Đường dẫn guest OS dự kiến theo device name |
| `RESTORED_DEVICE` | `/dev/disk/by-id/google-bench-restored-lab` | Đường dẫn disk phục hồi |
| `MOUNT_DIR` | `/mnt/disk-lab` | Thư mục mount disk nguồn |
| `RESTORE_MOUNT` | `/mnt/restore-lab` | Thư mục mount disk phục hồi |

**Tên/địa chỉ đều là ví dụ.** Nếu VM đã có disk cùng tên hoặc đang gắn thiết bị `/dev/disk/by-id/google-bench-data-lab`, **dừng** và kiểm tra. Chỉ thực hiện bước format sau khi xác nhận đó là **disk mới trống do lab tạo**.

### 4.2. Phân quyền và môi trường

Bạn cần:

- IAM phù hợp để **xem/tạo/attach/detach/delete disk** và **tạo/xem/xóa snapshot** trong project; không cấp Owner/Editor chỉ vì bài lab.
- Quyền truy cập VM Linux theo cách tổ chức cho phép; có `sudo` trong guest OS nếu định dạng/mount.
- Compute Engine API đã bật, quota disk và machine type hỗ trợ `pd-balanced`.
- Dung lượng disk đủ cho hai file `fio` riêng; bài chọn **20 GiB** và hai file thử nghiệm mỗi file khoảng **2 GiB**, nhưng nếu có ràng buộc riêng phải điều chỉnh theo chính sách.
- Kế hoạch IAM, Billing budget, thời điểm thực hành và **chi phí snapshot**. Budget chỉ gửi cảnh báo, không tự dừng tài nguyên.
- Đồng ý của chủ VM nếu dùng VM sẵn có: benchmark có thể làm tăng latency của mọi disk/workload cùng sử dụng VM, đặc biệt do shared VM limits.

**Không dùng Local SSD** cho phần snapshot. Với một VM không hỗ trợ `pd-balanced`, thay bài thực hành thành thao tác **read-only** hoặc nhờ chủ môi trường chọn disk và VM tương thích; không tự thay machine type của VM production.

## 5. Kiểm tra project, VM và disk trước khi tạo

Chạy trong **Cloud Shell hoặc terminal có Google Cloud CLI**:

```bash
PROJECT_ID="my-gcp-disk-lab"
ZONE="asia-southeast1-a"
VM_NAME="disk-test-vm"
DISK_NAME="bench-data-lab"
RESTORE_DISK="bench-restored-lab"
SNAPSHOT_NAME="bench-data-lab-snap-01"

# Chỉ đọc: tài khoản, VM và disk đang có
gcloud auth list --filter="status:ACTIVE"
gcloud projects describe "$PROJECT_ID" \
  --format="table(projectId,name,lifecycleState)"

gcloud compute instances describe "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,status,machineType,disks)"

gcloud compute disks list \
  --project="$PROJECT_ID"

# Xem snapshot đang có, tránh dùng lại tên thuộc hệ thống khác
gcloud compute snapshots list \
  --project="$PROJECT_ID"
```

Đối chiếu `machineType`, tên disk boot trong `disks`, disk đang gắn và owner của tài nguyên. **Không sử dụng `gcloud compute instances delete`** trong bài này: VM có sẵn và không thuộc vòng đời dọn disk.

### 5.1. Tạo data disk lab và gắn vào VM

Chỉ sau khi đã xác nhận tên `bench-data-lab` **chưa tồn tại** và VM ở đúng zone:

```bash
# Tạo disk 20 GiB loại pd-balanced, chi phí phát sinh theo bảng giá
gcloud compute disks create "$DISK_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --type=pd-balanced \
  --size=20GB

# Gắn data disk vào VM, đặt device name ổn định cho guest OS
gcloud compute instances attach-disk "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --disk="$DISK_NAME" \
  --device-name="$DISK_NAME"

# Xác minh data disk đã gắn và không phải boot disk
gcloud compute instances describe "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(disks)"
```

Disk mới chỉ là **block device**; chưa có filesystem. Việc **attach** thường có thể thực hiện khi VM đang chạy, nhưng việc thao tác disk trong guest OS vẫn cần tuân thủ điều kiện của nền tảng và chủ VM.

## 6. Trên Linux VM: nhận diện và mount disk **an toàn**

Các lệnh mục này chạy **bên trong VM Linux**, không chạy từ Cloud Shell để suy đoán device trên VM. Tên `/dev/sdb`, `/dev/nvme0n2` có thể thay đổi giữa lần boot và machine series; ưu tiên đường dẫn **`/dev/disk/by-id/google-<device-name>`** nếu guest OS cung cấp.

### 6.1. Kiểm tra danh tính disk

```bash
# Các lệnh chỉ đọc trong VM
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL
ls -l /dev/disk/by-id/
df -hT

# Phải khớp với --device-name từ bước attach; nếu không có, dừng để kiểm tra
DATA_DEVICE="/dev/disk/by-id/google-bench-data-lab"
test -b "$DATA_DEVICE" && readlink -f "$DATA_DEVICE"
lsblk -f "$DATA_DEVICE"
```

**Dừng ngay nếu**:

- Đường dẫn không tồn tại hoặc không phải block device.
- Disk đó xuất hiện là **boot disk**, chứa `/`, `/boot` hoặc filesystem của workload có trước.
- `lsblk -f` cho thấy đã có filesystem/partition hoặc một mountpoint không do lab tạo.
- Kích thước/serial/device name không khớp data disk 20 GiB vừa tạo.

Tuyệt đối không dựa vào tên `/dev/sdb` suy đoán đó là data disk. Nếu guest OS không cung cấp symlink `google-...` đúng như ví dụ, kiểm tra hướng dẫn guest environment và nhận diện disk bằng thông tin thực tế trước khi tiếp tục.

### 6.2. Tạo filesystem **chỉ trên data disk mới trống**

**`mkfs.ext4` là thao tác phá hủy dữ liệu trên thiết bị đích.** Chỉ chạy sau khi xác nhận device là **disk mới của bài lab**, chưa có filesystem, partition hoặc dữ liệu cần giữ. Không chạy đối với disk khôi phục từ snapshot.

```bash
DATA_DEVICE="/dev/disk/by-id/google-bench-data-lab"
MOUNT_DIR="/mnt/disk-lab"

# Xem thông tin lần cuối; nếu thấy filesystem/mountpoint, KHÔNG mkfs
lsblk -f "$DATA_DEVICE"
sudo blkid "$DATA_DEVICE" || true

# CẢNH BÁO: chỉ format data disk lab mới hoàn toàn
sudo mkfs.ext4 "$DATA_DEVICE"

# Mount để thao tác trên file, không ghi trực tiếp raw device
sudo mkdir -p "$MOUNT_DIR"
sudo mount "$DATA_DEVICE" "$MOUNT_DIR"
sudo chown "$(id -u):$(id -g)" "$MOUNT_DIR"

# Đọc lại: mountpoint phải đúng disk lab
findmnt "$MOUNT_DIR"
df -hT "$MOUNT_DIR"
```

Nếu filesystem có partition, hướng dẫn có thể yêu cầu mount đúng partition thay vì raw disk. Trong ví dụ này, ta tạo filesystem trực tiếp trên **toàn bộ data disk trống** để đơn giản hóa, không tự tạo partition table.

### 6.3. Tạo marker để phục hồi sau snapshot

Tạo một file nhỏ có nội dung dễ kiểm tra và một file checksum trên đĩa lab. File này là **mốc khôi phục**, độc lập với dữ liệu benchmark `fio`:

```bash
MOUNT_DIR="/mnt/disk-lab"

printf 'backup-point=v1\nworkload=disk-lab\n' \
  > "$MOUNT_DIR/marker.txt"

# Tạo checksum có tên file tương đối, để phục hồi và kiểm tra ở mount khác
(cd "$MOUNT_DIR" && sha256sum marker.txt > marker.sha256)

cat "$MOUNT_DIR/marker.txt"
(cd "$MOUNT_DIR" && sha256sum --check marker.sha256)
```

**Kỳ vọng:** dòng `marker.txt: OK`. Lưu riêng giá trị checksum hoặc kết quả trong nhật ký bài lab để đối chiếu độc lập nếu cần. Không lưu dữ liệu cá nhân hay secret trong file thử nghiệm.

## 7. Chuẩn bị công cụ fio và sysstat

`fio` tạo tải đọc/ghi giả lập; `iostat` (thuộc `sysstat`) giúp theo dõi tình trạng thiết bị và queue của hệ điều hành.

Trên một VM Debian/Ubuntu lab đã được phép cài package:

```bash
sudo apt-get update
sudo apt-get install -y fio sysstat

# Xác minh đúng công cụ và trạng thái disk/mount
fio --version
iostat -V
findmnt /mnt/disk-lab
```

Trên RHEL/Rocky/Container-Optimized OS, cách cài tool khác và có thể cần image test thích hợp. Đừng chỉnh package hoặc restart dịch vụ production chỉ để có `fio`.

### 7.1. Giới hạn an toàn của lệnh

Các phép thử sắp chạy:

- Chỉ dùng `/mnt/disk-lab/bench-seq.dat` và `/mnt/disk-lab/bench-rand.dat`.
- Không sử dụng `/dev/...` làm `--filename`.
- Đặt thời gian `60s` mỗi phép thử (có ramp `5s`), dung lượng file khoảng `2 GiB`; có thể giảm theo giới hạn project.
- Dùng `--numjobs=1`, `--iodepth=16` để bài lab có thể kiểm soát, không coi đây là mức tải tối ưu cho mọi ổ đĩa.
- Bỏ qua hoặc dừng benchmark nếu VM đang chạy service nhạy latency hay dữ liệu trong mountpoint không thuộc lab.

**`fio` có thể ghi đè file hiện có nếu trùng tên.** Trước mỗi lần chạy, xác minh đúng mount và đảm bảo file target là file thử nghiệm riêng của bài học:

```bash
MOUNT_DIR="/mnt/disk-lab"
test "$(findmnt -n -o TARGET --target "$MOUNT_DIR")" = "$MOUNT_DIR" \
  || { echo "Không phải mountpoint lab; dừng."; exit 1; }

ls -lh "$MOUNT_DIR"
```

## 8. Benchmark IOPS/throughput/latency bằng fio

### 8.1. Kiểm thử ghi tuần tự (sequential write)

Lệnh sau ghi vào **file mới trên data disk lab**, không ghi raw block device. Nếu file đã chứa dữ liệu cần giữ, không chạy.

```bash
fio --name=seq-write-lab \
  --filename=/mnt/disk-lab/bench-seq.dat \
  --rw=write \
  --bs=1m \
  --size=2G \
  --ioengine=libaio \
  --direct=1 \
  --iodepth=16 \
  --numjobs=1 \
  --ramp_time=5 \
  --runtime=60 \
  --time_based \
  --group_reporting
```

**Đọc kết quả:**

- `write: IOPS=...`: số thao tác ghi mỗi giây với block 1 MiB.
- `BW=...MiB/s`: tốc độ ghi theo MiB/s trong phép thử.
- `clat (usec/msec)` và bảng percentiles: độ trễ hoàn tất.
- `IO depths`: queue có thực sự đạt mức đã cấu hình hay không.

Giá trị output **phụ thuộc VM/disk thật**, không dùng một con số giả định làm kết quả lab. Do file size 2 GiB và thời gian giới hạn, đây là **đo nhanh**; không đủ để cam kết throughput bền vững của workload production.

### 8.2. Kiểm thử đọc tuần tự (sequential read)

Sau khi file `bench-seq.dat` được tạo thành công, đọc đúng file đó:

```bash
sync
fio --name=seq-read-lab \
  --filename=/mnt/disk-lab/bench-seq.dat \
  --rw=read \
  --bs=1m \
  --size=2G \
  --ioengine=libaio \
  --direct=1 \
  --iodepth=16 \
  --numjobs=1 \
  --ramp_time=5 \
  --runtime=60 \
  --time_based \
  --group_reporting
```

`--direct=1` yêu cầu direct I/O, giúp giảm ảnh hưởng page cache của Linux. Nó **không** loại bỏ mọi dạng cache ở tất cả tầng lưu trữ hoặc bảo đảm kết quả giống truy cập dữ liệu của ứng dụng thật.

### 8.3. Kiểm thử random read/write 4 KiB, 70/30

Thử workload giống truy cập random nhỏ của một số ứng dụng database:

```bash
fio --name=randrw-lab \
  --filename=/mnt/disk-lab/bench-rand.dat \
  --rw=randrw \
  --rwmixread=70 \
  --bs=4k \
  --size=2G \
  --ioengine=libaio \
  --direct=1 \
  --iodepth=16 \
  --numjobs=1 \
  --ramp_time=5 \
  --runtime=60 \
  --time_based \
  --group_reporting
```

Kết quả có hai nhóm `read` và `write`. **Tổng IOPS** có thể xét tổng hoạt động đọc và ghi của phép thử, nhưng đừng so một số IOPS chỉ đọc với một workload hỗn hợp 70/30 mà không ghi rõ điều kiện.

Để đo **latency theo SLO**, quan sát p95/p99 của read và write riêng; p99 cao có thể ảnh hưởng request dù IOPS tổng nhìn tốt.

### 8.4. Đọc trạng thái OS khi benchmark

Ở một terminal khác **trong cùng VM**, dùng:

```bash
# Thông số của các thiết bị block đang hoạt động; Ctrl+C để kết thúc
iostat -xz 2
```

Các trường hữu ích:

- `r/s`, `w/s`: số request đọc/ghi được OS ghi nhận mỗi giây.
- `rkB/s`, `wkB/s`: lượng dữ liệu đọc/ghi trên thiết bị.
- `await`: thời gian I/O trung bình theo quan sát của Linux.
- `aqu-sz`: độ dài hàng đợi I/O trung bình.
- `%util`: tỷ lệ thời gian thiết bị có request; **không diễn giải đơn giản `100%` = cloud disk đã đạt trần throughput** trên hạ tầng lưu trữ ảo/song song.

Tên device trong `iostat` có thể là `sdb` hoặc `nvme...`, **không giống tên symlink**. Xác nhận chúng ánh xạ tới data disk lab trước khi đọc số.

### 8.5. Ghi bảng kết quả có thể so sánh

| Phép thử | Block / mix | IOPS thực tế | Throughput (MiB/s) | Read p95/p99 | Write p95/p99 |
|---|---|---:|---:|---|---|
| Seq write | 1 MiB, 100% write | *Điền từ fio* | *Điền từ fio* | — | *Điền từ fio* |
| Seq read | 1 MiB, 100% read | *Điền từ fio* | *Điền từ fio* | *Điền từ fio* | — |
| Random read/write | 4 KiB, 70/30 | *Điền tổng/riêng* | *Điền kết quả* | *Điền từ fio* | *Điền từ fio* |

Lưu thêm **disk type/size, machine type, vCPU, zone, kernel, filesystem, fio version, iodepth, numjobs và thời điểm**. Không so bảng này với kết quả người khác nếu cấu hình khác nhau.

## 9. Diễn giải kết quả: tìm nút thắt đúng chỗ

Một số trường hợp thường gặp:

| Quan sát | Khả năng giải thích | Bước kiểm tra |
|---|---|---|
| IOPS random thấp nhưng throughput tuần tự chấp nhận được | Đĩa/workload không tối ưu I/O nhỏ, queue chưa phù hợp | Đối chiếu block size, IOPS limit, queue depth |
| Throughput không tăng khi nâng disk size | Chạm trần VM/vCPU hoặc I/O pattern | Xem machine type và giới hạn PD của VM |
| Hyperdisk provision IOPS cao nhưng không đạt | VM không hỗ trợ mức đó hoặc workload không tạo đủ queue | Kiểm tra giới hạn Hyperdisk/VM, I/O size, fio depth |
| p99 cao dù IOPS trung bình ổn | Burst, tranh chấp I/O, CPU hoặc queue quá dài | Đo theo thời gian, theo dõi CPU và iostat |
| `fio` read rất nhanh khi không dùng direct I/O | Page cache ảnh hưởng số đo | So lại với `--direct=1` và dataset phù hợp |
| Kết quả không ổn định giữa hai lần chạy | Cache, startup, contention, nền tảng và file size | Thử nhiều vòng trong môi trường kiểm soát |
| App chậm nhưng benchmark disk tốt | Bottleneck thuộc DB query, lock, CPU, mạng hoặc application | Đọc profiler, tracing, metrics nghiệp vụ |
| Tăng disk capacity khiến chi phí tăng | PD bị ràng buộc hiệu năng theo capacity | Cân nhắc Hyperdisk nếu máy hỗ trợ và economics phù hợp |

**Công thức tư duy:** hiệu năng hữu ích là **mức đạt được với latency chấp nhận được và chi phí phù hợp**, không chỉ là số IOPS cao nhất do benchmark ngắn tạo ra.

### 9.1. Dữ liệu Cloud Monitoring

Compute Engine cung cấp số liệu đĩa và VM qua **Cloud Monitoring**; có thể xem biểu đồ read/write bytes/operations và những metric hỗ trợ theo loại disk/VM. Nếu cần quan sát Linux filesystem latency hoặc disk queue chi tiết, có thể dùng **Ops Agent**/guest monitoring theo cấu hình được phép.

**Phân biệt:**

- Metrics Cloud Monitoring về VM/disk phản ánh thống kê ở cấp nền tảng theo khoảng đo.
- `fio` đo hiệu năng của một workload kiểm thử cụ thể trong guest OS.
- `iostat` đo I/O nhìn từ guest OS.
- Application SLO đo người dùng thực sự nhận được gì.

Không mặc định các con số giống hệt nhau do cách đếm, đơn vị, thời gian tổng hợp và cache.

## 10. Chuẩn bị snapshot: an toàn dữ liệu trước hết

**Snapshot** là điểm phục hồi dữ liệu disk theo thời gian. Snapshots Compute Engine thường lưu dữ liệu dạng tăng dần (incremental) theo cơ chế sản phẩm và có thể được phục hồi thành disk mới. Một snapshot được tạo thành công không đồng nghĩa **ứng dụng đang ghi** đã ở trạng thái nhất quán nghiệp vụ.

### 10.1. Crash consistency và application consistency

| Tính nhất quán | Điều được kỳ vọng | Rủi ro |
|---|---|---|
| **Crash-consistent** | Phản ánh trạng thái block như sau sự cố mất điện tại một thời điểm | Dữ liệu trong bộ nhớ ứng dụng, transaction chưa flush có thể thiếu; cần recovery logic |
| **Filesystem-consistent** | Filesystem được đồng bộ/ngừng ghi đủ để giảm rủi ro journal chưa flush | Chưa bảo đảm database đã hoàn tất các giao dịch logic |
| **Application-consistent** | Ứng dụng/database phối hợp flush/quiesce trước snapshot | Cần hook/công cụ phù hợp, có thể ảnh hưởng availability |

Với PostgreSQL, MySQL, SQL Server hoặc workload có nhiều disk/transaction, không nên chỉ dựa vào một lệnh `sync` rồi tuyên bố ứng dụng đã **application-consistent**. Cần dùng phương thức backup phù hợp của cơ sở dữ liệu, quiescing hoặc công cụ được hỗ trợ. Với lab **một filesystem chỉ có file thử nghiệm**, ta có thể **ngừng ghi và unmount** trước khi snapshot để có trạng thái filesystem sạch.

### 10.2. Vì sao snapshot và backup phải được thử?

Một quy trình backup hoàn chỉnh cần:

1. Chọn **đối tượng** (disk/dữ liệu nào), điểm khôi phục và vị trí lưu.
2. Xác định **RPO** (mức dữ liệu tối đa có thể mất) và **RTO** (thời gian tối đa muốn khôi phục).
3. Tạo snapshot theo lịch phù hợp, kiểm soát IAM, mã hóa và retention.
4. Định kỳ **restore sang disk riêng**, mount, kiểm tra dữ liệu và chạy smoke test ứng dụng.
5. Đánh giá khả năng phục hồi khi **cả VM/zone bị lỗi**, không chỉ khi một file bị xóa.

**Ví dụ:** snapshot mỗi 24 giờ có thể dẫn đến RPO gần 24 giờ trong kịch bản bất lợi. RTO bao gồm tạo disk từ snapshot, attach, mount, kiểm tra và đưa ứng dụng vào hoạt động; **không chỉ thời gian hoàn thành lệnh tạo snapshot**.

## 11. Tạo snapshot cho data disk lab

### 11.1. Ngừng ghi, kiểm tra marker, unmount

Trên **VM Linux lab**, kết thúc mọi lệnh `fio` và tiến trình ghi vào `/mnt/disk-lab`, sau đó:

```bash
MOUNT_DIR="/mnt/disk-lab"

# Kiểm tra nội dung gốc và checksum vẫn đúng
(cd "$MOUNT_DIR" && sha256sum --check marker.sha256)

# Đẩy các write buffers phù hợp rồi unmount disk lab
sync
sudo umount "$MOUNT_DIR"

# Không còn mountpoint; đừng snapshot khi benchmark vẫn đang ghi
findmnt "$MOUNT_DIR" || echo "Disk lab đã unmount"
```

Nếu `umount` báo “target is busy”, không dùng `umount -l` để né an toàn. Kiểm tra terminal/process còn mở file hoặc `cwd` trong mountpoint, đóng đúng tiến trình rồi unmount. Không cưỡng bức khi có workload thật.

### 11.2. Tạo snapshot bằng gcloud

Trở về **Cloud Shell hoặc terminal đã đăng nhập**, sử dụng lệnh được tài liệu Google Cloud khuyến nghị:

```bash
# Snapshot disk zonal; dữ liệu đã dừng ghi và filesystem đã unmount
gcloud compute snapshots create "$SNAPSHOT_NAME" \
  --project="$PROJECT_ID" \
  --source-disk="$DISK_NAME" \
  --source-disk-zone="$ZONE" \
  --snapshot-type=STANDARD

# Kiểm tra trạng thái, nguồn disk và vị trí lưu của snapshot
gcloud compute snapshots describe "$SNAPSHOT_NAME" \
  --project="$PROJECT_ID" \
  --format="yaml(name,status,sourceDisk,storageLocations,creationTimestamp)"
```

**Chỉ tiếp tục restore khi snapshot đã sẵn sàng/hoàn tất theo trạng thái API.** Tên snapshot là resource độc lập; không cần xóa disk nguồn để tạo bản khôi phục.

Snapshot có **storage location**, có thể được chọn theo snapshot settings hoặc `--storage-location` nếu cần đáp ứng vị trí lưu dữ liệu. Bài lab dùng cài đặt mặc định đã được người quản trị chấp thuận; môi trường thực phải kiểm tra **data residency, IAM, CMEK/encryption và retention** trước khi tạo.

### 11.3. Console tương đương

1. Mở **Compute Engine → Snapshots → Create snapshot**.
2. Chọn tên `bench-data-lab-snap-01`, loại snapshot thông thường (**STANDARD**) và **source disk `bench-data-lab`**, không phải boot disk.
3. Xem **vị trí lưu trữ** và chính sách backup của project.
4. Xác minh ứng dụng đã dừng ghi, filesystem lab đã unmount.
5. Tạo snapshot, mở chi tiết và xem trạng thái hoàn thành.

**Cảnh báo:** đừng chọn nhầm disk chứa database/production; snapshot của dữ liệu nhạy cảm có cùng yêu cầu bảo vệ và kiểm soát truy cập như dữ liệu gốc.

## 12. Phục hồi từ snapshot sang **đĩa mới**

Phương án an toàn là **không ghi đè đĩa nguồn**, mà tạo một disk mới từ snapshot rồi mount để kiểm chứng. Snapshot không phải lệnh “thay nội dung một disk đang tồn tại”.

### 12.1. Tạo disk phục hồi

Trong Cloud Shell:

```bash
# Chỉ tạo disk tên mới, không trùng disk đang có
gcloud compute disks create "$RESTORE_DISK" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --type=pd-balanced \
  --source-snapshot="$SNAPSHOT_NAME"

# Kiểm tra disk mới có sourceSnapshot và trạng thái hợp lệ
gcloud compute disks describe "$RESTORE_DISK" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(name,status,sizeGb,type,sourceSnapshot)"
```

Disk được tạo **từ ảnh snapshot** chứa filesystem và file tại thời điểm snapshot. **Tuyệt đối không chạy `mkfs.ext4` trên disk phục hồi**: việc định dạng mới sẽ ghi đè metadata filesystem và làm mất ý nghĩa kiểm thử phục hồi.

### 12.2. Gắn disk phục hồi vào VM lab

```bash
gcloud compute instances attach-disk "$VM_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --disk="$RESTORE_DISK" \
  --device-name="$RESTORE_DISK"

# Phân biệt rõ disk boot, disk nguồn và disk mới
gcloud compute instances describe "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(disks)"
```

**Lưu ý:** disk nguồn và disk phục hồi có thể chứa cùng **filesystem UUID** vì snapshot sao chép filesystem. Bài lab giữ disk nguồn **unmounted**, rồi chỉ mount disk phục hồi để tránh nhầm lẫn khi quản lý mount/fstab theo UUID.

### 12.3. Mount chỉ đọc và kiểm tra checksum

Chạy trên **VM Linux**, xác nhận thiết bị khôi phục khác thiết bị nguồn và boot disk:

```bash
RESTORED_DEVICE="/dev/disk/by-id/google-bench-restored-lab"
RESTORE_MOUNT="/mnt/restore-lab"

# Chỉ đọc để xác minh disk mới và filesystem sẵn có
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL
ls -l /dev/disk/by-id/
test -b "$RESTORED_DEVICE" && readlink -f "$RESTORED_DEVICE"
lsblk -f "$RESTORED_DEVICE"

# Disk phục hồi đã có filesystem; KHÔNG chạy mkfs
sudo mkdir -p "$RESTORE_MOUNT"
sudo mount -o ro "$RESTORED_DEVICE" "$RESTORE_MOUNT"

findmnt "$RESTORE_MOUNT"
ls -lah "$RESTORE_MOUNT"

# Dùng checksum đã tạo TRƯỚC snapshot để xác minh nội dung
(cd "$RESTORE_MOUNT" && sha256sum --check marker.sha256)

# Đọc file marker tại đúng điểm khôi phục
cat "$RESTORE_MOUNT/marker.txt"
```

**Kỳ vọng:** `marker.txt: OK` và nội dung marker là:

```text
backup-point=v1
workload=disk-lab
```

Nếu mount báo lỗi về journal/filesystem, **không dùng `fsck -y` hoặc format trên disk khôi phục ngay**. Kiểm tra trạng thái snapshot, disk, nguồn và thông báo lỗi. Khi cần sửa filesystem, sao chép/restore một disk khác để chẩn đoán thay vì làm mất bản thử nghiệm ban đầu. Với dữ liệu thực, chỉ chuyển sang chạy ứng dụng sau khi kiểm tra filesystem và dữ liệu ở tầng ứng dụng.

### 12.4. Kiểm chứng điểm khôi phục bằng thay đổi sau snapshot (tùy chọn)

Để thấy rõ snapshot là **ảnh của một thời điểm**, có thể thực hành trên disk nguồn riêng sau khi snapshot đã hoàn tất:

1. Khi disk phục hồi đã được xác minh và **unmount**, giữ bản checksum v1 ở nơi an toàn.
2. Mount lại disk **nguồn lab**, đổi nội dung `marker.txt` thành `backup-point=v2`, rồi `sync` và unmount.
3. Mount lại disk **phục hồi** theo chế độ chỉ đọc. Nội dung trong disk khôi phục vẫn là `v1`.
4. Không thay đổi file `marker.sha256` bên disk nguồn nếu đang muốn dùng nó để minh họa sự khác biệt; chỉ dùng checksum v1 để so với disk phục hồi.

**Chỉ thực hiện khi đây là disk lab và bạn biết chính xác device đang mount.** Không ghi file test vào đĩa chứa workload thật. Với database, “khôi phục một file” không thay thế quy trình restore dữ liệu giao dịch.

### 12.5. Console tương đương

1. Mở **Compute Engine → Snapshots**, chọn snapshot `bench-data-lab-snap-01`.
2. Chọn hành động **Create disk** từ snapshot.
3. Đặt tên mới `bench-restored-lab`, zone phù hợp với VM và disk type được hỗ trợ.
4. Mở **Compute Engine → VM instances → VM lab → Edit** rồi attach disk hiện có theo cơ chế được giao diện hỗ trợ.
5. SSH vào VM, kiểm tra device, mount **read-only** và so checksum trước khi cho ứng dụng dùng dữ liệu.

## 13. Đọc kết quả phục hồi: RPO, RTO và tính nhất quán

| Mục tiêu | Cách kiểm tra trong lab | Lỗi thường gặp |
|---|---|---|
| **Có backup** | Snapshot tồn tại và trạng thái hoàn tất | Chỉ thấy job chạy, chưa kiểm tra trạng thái |
| **Khôi phục disk** | Disk mới có `sourceSnapshot` đúng | Nhầm snapshot hoặc tạo trong zone không tương thích |
| **Khôi phục filesystem** | Mount chỉ đọc thành công | Sai device, duplicate UUID hoặc filesystem lỗi |
| **Toàn vẹn dữ liệu** | `sha256sum --check` trả `OK` | Không giữ checksum từ trước snapshot |
| **RPO** | Điểm snapshot gần nhất so với thời điểm lỗi | Lịch snapshot quá thưa |
| **RTO** | Thời gian từ lúc bắt đầu khôi phục đến khi ứng dụng phục vụ được | Chỉ đo thời gian tạo disk, bỏ qua mount/app restore |
| **Khả năng vận hành** | Quyền IAM, key, network và dependency hoạt động | Disk còn dữ liệu nhưng app không kết nối DB/secret |

Trong một ứng dụng đa disk hoặc cơ sở dữ liệu, restore thành công một filesystem **chưa chứng minh** mọi bảng, index, transaction và các service phụ thuộc đã nhất quán. Cần thêm test nghiệp vụ, kiểm tra checksum/logical consistency, và quy trình phục hồi tương ứng.

### 13.1. Thử một kịch bản sự cố thực tế

Ví dụ đội vận hành đặt:

- **RPO mục tiêu:** tối đa 4 giờ dữ liệu.
- **RTO mục tiêu:** ứng dụng trở lại phục vụ trong 60 phút.
- **Biện pháp:** snapshot theo lịch đáp ứng RPO, thử restore định kỳ, dùng IaC/scripts quản lý cấu hình VM, đo thời gian tạo disk và khởi động app.

Không thể kết luận đạt RPO/RTO chỉ vì snapshot được lập lịch. Phải đo trong điều kiện sự cố giả định phù hợp, bao gồm dữ liệu, image, quyền truy cập, secrets và những dependency quan trọng.

## 14. Snapshot schedules, retention và chống xóa nhầm

Snapshot thủ công chỉ là điểm khôi phục đầu tiên. Trong vận hành cần:

1. **Lịch snapshot** tương ứng nhu cầu RPO; giới hạn về tần suất và tính năng cần kiểm tra theo disk type.
2. **Retention policy**: giữ đủ số điểm phục hồi và tránh xóa các bản còn cần thiết.
3. **Phân quyền tối thiểu:** người dùng xem dữ liệu không tự động có quyền tạo/xóa snapshot; quản trị khóa mã hóa và disk phải đúng trách nhiệm.
4. **Vị trí lưu snapshot** tuân thủ quy định lưu trữ dữ liệu và phương án DR của tổ chức.
5. **Theo dõi lỗi snapshot**, kiểm tra backup hoàn tất và báo động khi chu kỳ bị bỏ lỡ.
6. **Restore drills:** định kỳ tạo disk mới, mount/test ứng dụng rồi dọn tài nguyên kiểm thử.

**Incremental snapshot** giảm dung lượng dữ liệu phải lưu so với việc giữ nguyên bản full copy ở mọi thời điểm theo cơ chế dịch vụ; tuy nhiên, chi phí snapshot và restore vẫn phụ thuộc dung lượng dữ liệu thực và cấu hình. **Không giả định snapshot là miễn phí**, hoặc có thể khôi phục mà không cần quyền/quota ở project đích.

Lịch snapshot và backup ứng dụng là hai lớp bổ sung. Với hệ thống yêu cầu point-in-time recovery của database, cần giải pháp hỗ trợ **transaction log / WAL / binlog** hoặc dịch vụ backup chuyên dụng thích hợp, không dựa duy nhất vào snapshot disk.

## 15. Bảo mật và giới hạn của bản sao dữ liệu

Snapshot và disk mới có thể chứa:

- Nội dung file, database files, log và cấu hình ứng dụng.
- Token/secret từng được lưu sai cách trên disk.
- Thông tin cá nhân hoặc dữ liệu phải tuân thủ chính sách lưu trữ.

Vì vậy:

- **IAM của snapshot và disk** phải giới hạn ai xem/khôi phục/xóa.
- Xác định **encryption at rest**, khóa CMEK/CSEK nếu tổ chức áp dụng, vòng đời và quyền truy cập key khi khôi phục.
- Không chia sẻ snapshot chứa dữ liệu thật cho project cá nhân chỉ để thử benchmark.
- Snapshot không mặc nhiên là biện pháp chống ransomware độc lập: cần policy ngăn xóa trái phép, retention, kiểm toán thay đổi và bản sao đủ cách ly theo mô hình bảo vệ của tổ chức.
- Khi xóa disk đã restore để dọn, kiểm tra rằng đây không phải bản duy nhất còn giữ dữ liệu quan trọng.

## 16. Dọn tài nguyên lab và ngừng chi phí

**Chỉ dọn những disk/snapshot được tạo riêng trong bài này.** Không xóa VM đã tồn tại sẵn, boot disk, bucket, file dữ liệu production hoặc snapshot đang nằm trong chính sách backup của tổ chức.

### 16.1. Unmount và xác minh guest OS

Trên VM:

```bash
# Dừng mọi chương trình dùng dữ liệu thử nghiệm rồi unmount
sudo umount /mnt/restore-lab

# Disk nguồn cũng phải đang unmount trước khi detach
findmnt /mnt/disk-lab || echo "Disk nguồn không mount"
findmnt /mnt/restore-lab || echo "Disk phục hồi không mount"
```

Nếu báo “target is busy”, xử lý tiến trình còn sử dụng filesystem; không dùng lệnh cưỡng bức hoặc xóa disk khi VM đang ghi.

### 16.2. Kiểm kê disk/snapshot bằng Cloud Shell

```bash
printf 'Project=%s Zone=%s VM=%s\nSource=%s Restore=%s Snapshot=%s\n' \
  "$PROJECT_ID" "$ZONE" "$VM_NAME" \
  "$DISK_NAME" "$RESTORE_DISK" "$SNAPSHOT_NAME"

gcloud compute instances describe "$VM_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE" \
  --format="yaml(disks)"

gcloud compute disks describe "$DISK_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE"

gcloud compute disks describe "$RESTORE_DISK" \
  --project="$PROJECT_ID" --zone="$ZONE"

gcloud compute snapshots describe "$SNAPSHOT_NAME" \
  --project="$PROJECT_ID"
```

### 16.3. Detach rồi delete **chỉ disk lab**

```bash
# Gỡ disk phục hồi khỏi VM, chỉ khi đã unmount và xác nhận owner
gcloud compute instances detach-disk "$VM_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --disk="$RESTORE_DISK"

# Gỡ data disk benchmark khỏi VM
gcloud compute instances detach-disk "$VM_NAME" \
  --project="$PROJECT_ID" \
  --zone="$ZONE" \
  --disk="$DISK_NAME"

# Chỉ xóa hai disk do bài lab tạo, sau khi kiểm kê dữ liệu cần giữ
gcloud compute disks delete "$RESTORE_DISK" \
  --project="$PROJECT_ID" --zone="$ZONE"

gcloud compute disks delete "$DISK_NAME" \
  --project="$PROJECT_ID" --zone="$ZONE"
```

**Xóa disk là thao tác phá hủy dữ liệu.** Nếu định giữ snapshot như điểm khôi phục, đừng xóa snapshot sau đó. Ngược lại, nếu lab kết thúc và không cần giữ snapshot, kiểm tra chủ sở hữu rồi mới xóa.

### 16.4. Xóa snapshot lab khi không còn cần

```bash
# CHỈ khi snapshot này được tạo cho lab và đã xác minh không cần giữ
gcloud compute snapshots delete "$SNAPSHOT_NAME" \
  --project="$PROJECT_ID"

# Đọc lại danh sách tài nguyên để biết còn phí tài nguyên nào
gcloud compute disks list --project="$PROJECT_ID"
gcloud compute snapshots list --project="$PROJECT_ID"
```

Không xóa ảnh chụp đang phục vụ backup/DR hoặc được hệ thống khác dùng. Dữ liệu Billing Reports có thể hiển thị trễ sau khi tài nguyên bị xóa; xác nhận không còn disk/IP/snapshot lab trong danh sách mới là bước kiểm kê chủ động.

## 17. Troubleshooting: benchmark và restore

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không tạo được disk lab | Không đủ quyền, quota, billing hoặc machine type không hỗ trợ | Kiểm tra IAM, disk type/zone và Compute Engine API |
| `attach-disk` báo không tương thích | Disk khác zone, VM không hỗ trợ loại disk hoặc resource đang được dùng theo mode không tương thích | So VM/disk location, machine series và attach mode |
| `/dev/disk/by-id/google-...` không có | Device name khác hoặc guest environment thiếu symlink | Đọc `instances describe`, `lsblk`, `ls -l /dev/disk/by-id`; không đoán bằng `/dev/sdb` |
| `mkfs` báo device đang bận | Disk mounted/đã có partition hoặc bị kernel giữ | **Dừng** và xác minh disk đúng; không cưỡng ép |
| `fio` ghi chậm | Disk size/type, VM vCPU, queue, CPU hoặc I/O contention | Đọc fio/iostat, so giới hạn của disk và VM |
| `fio` read nhanh bất thường | Page cache, file quá nhỏ hoặc cách đo chưa phù hợp | Dùng direct I/O, tăng dataset có kiểm soát |
| `fio` báo `No space left on device` | File test cộng lại vượt dung lượng filesystem | Xem `df -hT`, giảm file size hoặc dùng disk lab đủ lớn |
| `umount` báo `busy` | Terminal/process vẫn truy cập file trong mount | Thoát thư mục, dừng fio/tiến trình, kiểm tra `fuser` nếu được phép |
| Snapshot thất bại | Permission, quota, disk/zone không đúng hoặc trạng thái snapshot lỗi | Đọc thông báo lỗi và operation; không xóa disk nguồn |
| Snapshot thành công nhưng file thiếu | File chưa flush, ghi sau snapshot hoặc chọn sai disk | Kiểm tra thời điểm, marker, nguồn snapshot và chiến lược quiesce |
| Restore disk không mount được | Chọn nhầm device/FS, snapshot chưa hoàn tất hoặc filesystem cần kiểm tra | `lsblk -f`, `blkid`, thông tin snapshot; không format disk restored |
| `sha256sum --check` không đạt | File khác điểm khôi phục, checksum sai hoặc dữ liệu hỏng | Đối chiếu tên snapshot, dữ liệu nguồn tại T, thử restore mới |
| VM có hai filesystem cùng UUID | Snapshot sao chép cả filesystem UUID | Tránh mount theo UUID trùng; dùng device ID ổn định và quy trình quản lý filesystem |
| Có bản backup nhưng RTO không đạt | Disk restore được nhưng ứng dụng/DB/IAM/network chưa sẵn sàng | Đo toàn bộ quy trình khôi phục và chạy smoke tests |
| Xóa disk nhưng vẫn phát sinh phí | Snapshot/disk phụ còn tồn tại hoặc billing chưa cập nhật | Kiểm kê disk/snapshot, xem Billing Reports/labels |

### Cách chẩn đoán theo thứ tự

1. **Lớp tài nguyên:** đúng project, zone, VM, disk type và snapshot chưa?
2. **Lớp block device:** `lsblk` và symlink có khớp disk lab không?
3. **Lớp filesystem:** mountpoint, `df`, `findmnt` và checksum có đúng không?
4. **Lớp hiệu năng:** cấu hình `fio`, `iostat`, cache, CPU/VM limits, disk limits?
5. **Lớp backup:** snapshot source, thời điểm, trạng thái, vị trí lưu và quyền IAM?
6. **Lớp ứng dụng:** dữ liệu logical consistency, database recovery và smoke test?
7. **Lớp vận hành:** đã hoàn thành RPO/RTO, lưu bằng chứng và dọn tài nguyên chưa?

## 18. Những tình huống vận hành

### Tình huống A — Database có nhiều random I/O

Một VM chạy PostgreSQL có p99 latency cao khi tăng traffic. Đội định chuyển từ Persistent Disk Balanced sang Hyperdisk để tăng IOPS. Trước khi làm, họ đo workload `4 KiB random` với tỷ lệ đọc/ghi gần thực tế, kiểm tra disk/VM limits, CPU và latency tail, thay vì chỉ xem throughput khi ghi file 1 MiB.

**Bài học:** nếu bottleneck thuộc CPU, SQL query hoặc lock, nâng disk có thể không cải thiện nhiều. Nếu thực sự thiếu IOPS/throughput, so lựa chọn disk type, provisioned performance, VM compatibility và chi phí.

### Tình huống B — Tạo snapshot lúc ứng dụng đang ghi

Nhóm snapshot một data disk chứa database khi transaction đang ghi mạnh. Snapshot hoàn tất nhưng khi restore, database cần crash recovery hoặc thiếu các giao dịch chưa flush.

**Bài học:** snapshot block-level theo thời điểm không mặc nhiên application-consistent. Cần phương thức quiescing/backup database được hỗ trợ và kiểm thử restore.

### Tình huống C — Xóa nhầm file trên data disk

Một script thao tác sai xóa `reports/2026/summary.csv` trong ứng dụng. Disk vẫn healthy, VM vẫn chạy, nhưng dữ liệu đã mất. Nếu có snapshot ở điểm trước khi file bị xóa, đội tạo disk **mới** từ snapshot, mount read-only, kiểm tra checksum và copy đúng file phục hồi theo quy trình.

**Bài học:** replication/độ bền của disk không thay thế versioned backup; nên phục hồi sang vị trí riêng trước khi chép vào hệ thống đang chạy.

### Tình huống D — Bài lab làm đầy disk

Học viên chạy `fio` với `--size=100G` lên filesystem 20 GiB hoặc chọn nhầm boot disk. File test không có đủ chỗ và có thể khiến ứng dụng/OS lỗi do hết dung lượng.

**Bài học:** benchmark phải giới hạn đúng **filesystem lab**, dùng `df`/`findmnt` và file size có kiểm soát. Tránh chạy trên boot disk và raw device.

### Tình huống E — Cần phục hồi khi một zone không còn khả dụng

Ứng dụng và zonal disk chạy tại một zone. Nếu zone gặp sự cố, kế hoạch DR có thể cần **snapshot lưu ở vị trí hợp lệ** và tạo một disk mới trong **zone khác được hỗ trợ**, đồng thời tạo/đưa VM lên ở zone dự phòng.

**Bài học:** restore khả thi còn tùy snapshot scope, vùng lưu trữ dữ liệu, loại disk/VM, quyền IAM và các dependency ứng dụng. Cần diễn tập cùng network, DNS, secrets và database, không chỉ phục hồi file.

## 19. Checklist hoàn thành

| Mục kiểm tra | Bằng chứng |
|---|---|
| Project/VM | Đúng project sandbox, VM được phép thao tác |
| Data disk | Disk mới, không phải boot disk, kích thước/loại đã xác minh |
| Device mapping | Symlink `/dev/disk/by-id` trùng `--device-name` |
| Filesystem | `findmnt` và `df -hT` cho thấy mount riêng `/mnt/disk-lab` |
| Không phá dữ liệu | Không dùng `fio --filename=/dev/...`; `mkfs` chỉ chạy một lần trên disk mới |
| Benchmark | Có seq write/read, random mix, ghi IOPS/throughput/p95/p99 |
| Giới hạn | Đã giải thích ảnh hưởng VM, disk, cache, queue depth và runtime |
| Marker | File `marker.txt` và `marker.sha256` được tạo trước snapshot |
| Consistency | Đã dừng `fio`, `sync` và unmount nguồn trước snapshot |
| Snapshot | Đúng source disk, trạng thái hoàn tất, vị trí lưu được chấp thuận |
| Restore | Disk mới từ snapshot, **không format**, mount read-only |
| Checksum | `sha256sum --check marker.sha256` trả `OK` |
| RPO/RTO | Biết điểm khôi phục và những bước phải đo để đưa app trở lại |
| Cleanup | Unmount, detach/delete disk lab, xử lý snapshot theo retention |
| Billing | Đã kiểm kê disk/snapshot còn tồn tại, xem chi phí có thể cập nhật trễ |

## 20. Câu hỏi tự kiểm tra

**1. Vì sao đo throughput 1 MiB sequential không đủ để đánh giá một database OLTP?**  
**Trả lời:** database có thể phát sinh nhiều I/O ngẫu nhiên nhỏ và nhạy với p99 latency; cần workload, block size, read/write mix và concurrency gần thực tế.

**2. `--direct=1` trong fio dùng để làm gì?**  
**Trả lời:** yêu cầu direct I/O để giảm ảnh hưởng page cache của OS; không loại bỏ mọi cache trong hệ thống và không biến synthetic benchmark thành SLO ứng dụng.

**3. Đã cấp IOPS lớn cho Hyperdisk, sao hiệu năng vẫn thấp?**  
**Trả lời:** có thể chạm trần VM/machine type, workload không đủ queue/CPU, kích thước I/O không phù hợp hoặc có tranh chấp I/O.

**4. Có thể tạo snapshot Compute Engine disk để backup Filestore NFS share không?**  
**Trả lời:** không. Filestore là dịch vụ file storage, cần cơ chế backup/snapshot riêng của Filestore.

**5. Snapshot được tạo khi database đang ghi mạnh có chắc application-consistent không?**  
**Trả lời:** không. Phải dùng quy trình quiesce/flush/backup tương ứng và kiểm tra restore logic.

**6. Vì sao không chạy `mkfs.ext4` lên disk vừa phục hồi từ snapshot?**  
**Trả lời:** disk phục hồi đã chứa filesystem và dữ liệu từ snapshot; format sẽ ghi lại metadata và có thể phá dữ liệu cần kiểm chứng.

**7. Thấy `marker.txt: OK` trên disk phục hồi chứng minh điều gì?**  
**Trả lời:** dữ liệu file marker khớp checksum đã lưu trước snapshot; không tự chứng minh mọi file, database hoặc ứng dụng đều nhất quán.

**8. Snapshot tạo mỗi ngày có RPO mặc định bằng 0 không?**  
**Trả lời:** không. Có thể mất những thay đổi sau snapshot gần nhất; RPO phụ thuộc chu kỳ backup và khả năng phục hồi giao dịch.

**9. Sao một disk bền vững vẫn cần backup?**  
**Trả lời:** độ bền không loại bỏ rủi ro xóa nhầm, sửa sai, mã độc hoặc lỗi logic của ứng dụng; cần điểm khôi phục độc lập.

**10. Sau khi xóa disk benchmark, còn thành phần nào có thể tạo chi phí?**  
**Trả lời:** disk phục hồi, snapshot, VM/boot disk, địa chỉ IP được giữ, log và những dịch vụ khác; phải kiểm kê theo project.

## Ghi nhớ

- **IOPS, throughput và latency** đo ba khía cạnh khác nhau. Để so sánh phải giữ rõ block size, queue depth, read/write mix, disk/VM configuration và thời gian đo.
- **Persistent Disk** chịu ảnh hưởng loại/kích thước disk và giới hạn VM; **Hyperdisk** có thể tách provisioned performance khỏi dung lượng theo loại và machine series được hỗ trợ.
- **`fio` chỉ được chạy trên file thử nghiệm của disk lab**; không benchmark raw device/boot disk chứa dữ liệu cần giữ.
- **Snapshot là điểm khôi phục, không phải chứng nhận nhất quán ứng dụng**. Dừng ghi/quiesce đúng cách và phải diễn tập restore.
- **Phục hồi sang disk mới, mount read-only và so checksum** trước khi đưa dữ liệu vào ứng dụng. Không format disk đã restore.
- **RPO/RTO là yêu cầu vận hành cần kiểm thử**, không chỉ là cấu hình lịch snapshot; bảo vệ IAM, mã hóa, retention và ngân sách trong suốt vòng đời.
- **Dọn đúng tài nguyên thuộc lab**; VM có sẵn, boot disk và backup dùng chung không nằm trong phạm vi xóa.

## Tài liệu tham khảo chính thức

- [Google Cloud — Choose a disk type](https://cloud.google.com/compute/docs/disks)
- [Google Cloud — Persistent Disk performance](https://cloud.google.com/compute/docs/disks/performance)
- [Google Cloud — Hyperdisk performance](https://cloud.google.com/compute/docs/disks/hyperdisk-performance)
- [Google Cloud — Optimize Persistent Disk performance](https://cloud.google.com/compute/docs/disks/optimizing-pd-performance)
- [Google Cloud — Benchmarking Persistent Disk performance](https://cloud.google.com/compute/docs/disks/benchmarking-pd-performance)
- [Google Cloud — Create archive and standard snapshots](https://cloud.google.com/compute/docs/disks/create-snapshots)
- [Google Cloud — Manage disk snapshots](https://cloud.google.com/compute/docs/disks/manage-snapshots)
- [Google Cloud — Add a non-boot disk to a VM](https://cloud.google.com/compute/docs/disks/add-persistent-disk)
- [Google Cloud — Filestore documentation](https://cloud.google.com/filestore/docs)
