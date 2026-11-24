# Đĩa đầy hoặc I/O chậm: inode, hàng đợi và giới hạn volume

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt tình trạng hết dung lượng block, hết inode và volume bị giới hạn IOPS hoặc thông lượng.
- Đọc các chỉ số dung lượng, inode, latency, IOPS, throughput và queue depth để tìm nút thắt.
- Khoanh vùng lỗi ở filesystem, guest OS, volume cloud, đường kết nối lưu trữ hoặc giới hạn I/O của VM.
- Dùng công cụ Linux và Windows để kiểm tra disk, filesystem và hoạt động đọc/ghi.
- Lựa chọn cách xử lý an toàn: giải phóng dung lượng, mở rộng filesystem, điều chỉnh workload hoặc thay đổi cấu hình volume.
- Thiết lập cảnh báo và quy trình kiểm thử để tránh lặp lại sự cố.

## 1. Vì sao VM có thể chậm hoặc không ghi được dữ liệu?

Đĩa của VM thường gồm một hoặc nhiều volume được nền tảng cloud cung cấp dưới dạng thiết bị block hoặc dịch vụ lưu trữ tương tự. Guest OS tạo partition, filesystem và mount point trên thiết bị đó; ứng dụng tiếp tục tạo file, thư mục, database và log.

Một sự cố disk có thể xuất hiện ở nhiều lớp:

1. **Dung lượng filesystem:** không còn block trống để tạo hoặc mở rộng file.
2. **Inode hoặc metadata filesystem:** không còn inode để tạo file mới, dù vẫn còn block trống.
3. **Hiệu năng volume:** volume đạt giới hạn IOPS, thông lượng hoặc đang chịu độ trễ cao.
4. **Hàng đợi I/O:** nhiều yêu cầu đọc/ghi chờ hoàn tất, khiến ứng dụng phải đợi.
5. **Giới hạn ở VM hoặc đường truyền:** VM đã chạm giới hạn I/O tổng hợp, băng thông mạng lưu trữ hoặc giới hạn thiết bị ảo.
6. **Ứng dụng và hệ điều hành:** workload ghi đồng bộ, truy vấn kém hiệu quả, filesystem lỗi, driver hoặc kernel gặp vấn đề.

Các nguyên nhân có thể cùng xuất hiện. Ví dụ, database tạo nhiều file tạm làm inode cạn, đồng thời workload ghi ngẫu nhiên làm volume chạm IOPS. Nếu chỉ tăng dung lượng volume, vấn đề inode hoặc I/O có thể vẫn còn.

**Triệu chứng thường gặp:**

- Ứng dụng báo No space left on device, Disk full, write failed hoặc lỗi tạo file.
- Log không ghi được, database chuyển sang read-only hoặc không thể tạo transaction log.
- SSH/RDP đăng nhập được nhưng shell hoặc ứng dụng phản hồi chậm.
- Thời gian truy vấn tăng, hàng đợi công việc dồn lại, timeout hoặc retry liên tục.
- CPU không cao nhưng tiến trình thường xuyên chờ I/O.
- VM vẫn Running nhưng volume có latency cao hoặc đạt giới hạn hiệu năng.

Cần xác định sự cố thuộc dung lượng, inode hay hiệu năng trước khi thay đổi cấu hình.

## 2. Dung lượng block và inode khác nhau thế nào?

### 2.1. Dung lượng block

Filesystem cấp phát không gian lưu trữ theo block hoặc đơn vị cấp phát tương ứng. Khi file được tạo hoặc mở rộng, filesystem cần có đủ block để chứa nội dung và metadata.

Ví dụ, một filesystem 100 GiB đã dùng hết 100 GiB sẽ không thể ghi thêm dữ liệu. Lệnh df -h có thể báo 100% dù volume cloud bên dưới vẫn có thể được mở rộng; filesystem chưa tự động nhận phần dung lượng mới cho tới khi partition hoặc filesystem được mở rộng đúng cách.

### 2.2. Inode

Trên các filesystem Unix/Linux phổ biến như ext4, inode là cấu trúc metadata mô tả một đối tượng file hoặc thư mục. Inode lưu thông tin như quyền, owner, kích thước, timestamp và vị trí các block dữ liệu. Tên file và quan hệ thư mục được lưu trong directory entry, tham chiếu tới inode.

Một filesystem có thể còn nhiều block trống nhưng không tạo được file mới nếu đã dùng hết inode. Điều này thường xảy ra khi ứng dụng tạo số lượng rất lớn file nhỏ, cache, session, mail spool, file tạm hoặc log theo từng request.

Ví dụ:

- Một filesystem 50 GiB có thể chứa hàng triệu file nhỏ.
- Nếu số inode được tạo lúc format đã dùng hết, ứng dụng có thể báo hết chỗ dù lệnh df -h vẫn hiển thị còn nhiều GiB.
- Xóa một file lớn giải phóng block đáng kể, nhưng nếu sự cố là inode cạn thì cần xóa đủ số lượng file để giải phóng inode.

Không phải mọi filesystem đều quản lý inode theo cùng cách. XFS cấp phát inode động theo thiết kế của filesystem, trong khi ext4 thường xác định số inode tại thời điểm tạo filesystem. Trên Windows NTFS, khái niệm inode không được trình bày theo cách giống ext4; NTFS sử dụng Master File Table (MFT) và các cấu trúc metadata riêng.

### 2.3. Phân biệt nhanh

| Dấu hiệu | Hết block/dung lượng | Hết inode |
|---|---|---|
| Dung lượng dùng | Gần hoặc bằng 100% | Có thể còn rất nhiều dung lượng |
| Inode dùng | Có thể còn | Gần hoặc bằng 100% |
| Tác vụ thường lỗi | Ghi file lớn, mở rộng file, tạo file | Tạo file/thư mục mới |
| Nguyên nhân thường gặp | Log lớn, database, backup, file upload | Rất nhiều file nhỏ, cache, session, spool, file tạm |
| Kiểm tra Linux | df -h | df -i |
| Hướng xử lý | Xác định file chiếm block, mở rộng hoặc giải phóng dung lượng | Tìm thư mục có quá nhiều file, dọn file phù hợp hoặc thay đổi thiết kế |

### 2.4. Block, inode và file descriptor là ba thứ khác nhau

- Block là không gian chứa dữ liệu trên filesystem.
- Inode là metadata của file trên filesystem kiểu Unix.
- File descriptor là định danh mà một tiến trình đang dùng để truy cập file, socket hoặc tài nguyên khác.

Ứng dụng có thể hết file descriptor dù block và inode vẫn còn. Khi đó, lỗi thường có nội dung Too many open files. Cần kiểm tra giới hạn tiến trình và số descriptor đang mở, không xử lý như lỗi hết dung lượng.

## 3. IOPS, throughput và latency

Volume cloud thường được mô tả bằng các chỉ số hiệu năng chính:

- **IOPS (Input/Output Operations Per Second):** số thao tác đọc/ghi mỗi giây mà volume hoặc thiết bị có thể phục vụ.
- **Throughput:** lượng dữ liệu đọc/ghi trong một đơn vị thời gian, thường tính bằng MiB/s hoặc MB/s.
- **Latency:** thời gian hoàn tất một thao tác I/O, thường tính bằng ms hoặc µs.
- **Queue depth:** số yêu cầu I/O đang chờ hoặc đang được xử lý tại một lớp của đường I/O.
- **IO size:** kích thước trung bình của mỗi thao tác đọc/ghi.

### 3.1. IOPS và throughput có quan hệ với kích thước I/O

Một workload gồm nhiều thao tác nhỏ có thể cần IOPS cao nhưng throughput không lớn. Ngược lại, thao tác tuần tự với block lớn có thể đạt throughput cao dù số IOPS thấp hơn.

Công thức gần đúng để liên hệ hai chỉ số:

\[
\text{Throughput (MiB/s)} \approx
\frac{\text{IOPS} \times \text{IO size (KiB)}}{1024}
\]

Ví dụ, 3.000 IOPS với kích thước I/O trung bình 16 KiB tương đương khoảng 46,9 MiB/s nếu mọi thao tác đều hoàn tất ở tốc độ đó. Đây là phép quy đổi lý thuyết, chưa tính overhead, giới hạn volume/VM và đặc điểm đọc/ghi.

Do đó, volume có thể chạm giới hạn IOPS trước throughput hoặc ngược lại. Cần quan sát cả hai.

### 3.2. Latency và queue depth

Latency cao có nghĩa ứng dụng phải chờ lâu hơn để một thao tác I/O hoàn tất. Queue depth cao cho thấy nhiều thao tác đang chờ hoặc đang bay (in flight), nhưng không tự động chứng minh volume bị lỗi. Workload có thể chủ động gửi nhiều I/O song song để tận dụng thiết bị.

Cần xem queue depth cùng latency, IOPS, throughput, mức sử dụng thiết bị và độ trễ ở ứng dụng:

- Queue tăng và latency tăng cùng lúc: có thể thiết bị hoặc đường I/O đang bão hòa.
- Queue tăng nhưng throughput và IOPS cũng tăng, latency ổn định: có thể workload đang khai thác song song bình thường.
- Queue thấp nhưng latency cao: có thể từng request bị chậm do storage backend, network path, sync write, flush hoặc dependency khác.
- I/O wait cao nhưng volume metric bình thường: xem thêm filesystem, kernel, network, ứng dụng và giới hạn ở VM.

Không dùng một ngưỡng queue depth chung cho mọi volume. Mỗi thiết bị, driver, loại workload và nền tảng có đặc điểm khác nhau.

### 3.3. Giới hạn volume và giới hạn VM

Hiệu năng thực tế thường bị chi phối bởi giới hạn thấp nhất trên đường I/O:

- Giới hạn IOPS và throughput của volume.
- Giới hạn IOPS/throughput theo kích thước hoặc loại volume.
- Giới hạn tổng I/O của VM hoặc instance family.
- Giới hạn của controller, thiết bị ảo hoặc network path.
- Giới hạn ở filesystem, kernel và ứng dụng.
- Giới hạn theo burst credit hoặc cơ chế hiệu năng nền tảng.

Ví dụ, một VM gắn nhiều volume có thể có tổng nhu cầu I/O vượt giới hạn tổng hợp của instance dù từng volume chưa chạm giới hạn riêng. Ngược lại, VM có khả năng I/O cao nhưng một volume nhỏ vẫn là nút thắt.

## 4. Burst, baseline và giới hạn hiệu năng của volume

Một số loại volume có hiệu năng cơ bản và khả năng burst trong một khoảng thời gian. Khi nhu cầu tăng cao, volume có thể tạm thời phục vụ vượt mức baseline nhờ credit hoặc cơ chế burst. Khi credit cạn hoặc thời gian burst kết thúc, hiệu năng quay về mức duy trì.

Dấu hiệu cần kiểm tra:

- IOPS hoặc throughput tăng nhanh rồi bị giới hạn.
- Metric burst balance/credit giảm về thấp.
- Latency và queue depth tăng sau một khoảng thời gian tải cao.
- Hiệu năng phục hồi sau khi workload giảm hoặc credit được tích lũy lại.

Không phải mọi loại volume đều dùng burst credit. Một số loại cho phép cấu hình IOPS/throughput riêng hoặc tự động điều chỉnh. Hãy xem tài liệu của đúng loại volume và region.

Khi chọn volume, cần xác định:

1. Hiệu năng baseline cần duy trì liên tục.
2. Mức đỉnh và thời gian kéo dài của workload.
3. Khả năng burst và thời gian phục hồi credit nếu có.
4. Giới hạn tổng hợp của VM.
5. Chi phí dung lượng, IOPS và throughput được provision.
6. Khả năng thay đổi hiệu năng khi volume đang gắn vào VM.

Không dùng burst làm cơ sở cho workload có tải cao liên tục nếu baseline không đáp ứng yêu cầu.

## 5. Thu thập bằng chứng trước khi thay đổi

Khi disk đầy hoặc I/O chậm, hãy ghi nhận các thông tin sau trước khi dọn dẹp, reboot hoặc thay đổi volume:

- VM ID, hostname, region/zone, loại instance.
- Volume ID, loại volume, dung lượng và cấu hình hiệu năng.
- Filesystem, mount point, partition, LVM hoặc storage pool.
- Thời điểm bắt đầu, khoảng thời gian và workload đang chạy.
- Metric dung lượng, inode, IOPS, throughput, latency, queue depth và burst balance.
- Log ứng dụng, database, kernel và hệ thống.
- Thay đổi gần đây: deploy, backup, log rotation, batch job, snapshot, resize hoặc patch.
- Tác vụ nào bị lỗi và phạm vi người dùng bị ảnh hưởng.

Nếu đang có sự cố production, không chạy benchmark nặng hoặc xóa file hàng loạt trước khi hiểu dữ liệu nào đang được sử dụng. Việc ghi nhận trạng thái ban đầu giúp so sánh trước/sau và giữ bằng chứng để tìm nguyên nhân gốc.

## 6. Chẩn đoán dung lượng và inode trên Linux

### 6.1. Xem dung lượng filesystem

```bash
# Dung lượng đã dùng và còn trống theo filesystem
df -hT

# Xem inode đã dùng và còn trống
df -i

# Xem thiết bị, filesystem, partition và mount point
lsblk -f

# Xem các mount và tùy chọn mount
findmnt
```

Dùng df để kiểm tra filesystem đã mount. Nếu volume cloud đã được tăng dung lượng nhưng df vẫn không thay đổi, có thể partition hoặc filesystem chưa được mở rộng.

### 6.2. Tìm thư mục và file chiếm nhiều dung lượng

```bash
# Tổng dung lượng theo thư mục cấp một trong root filesystem
sudo du -xhd1 / 2>/dev/null | sort -h

# Xem thư mục log
sudo du -xhd1 /var/log 2>/dev/null | sort -h

# Tìm file lớn hơn 1 GiB trên filesystem hiện tại
sudo find / -xdev -type f -size +1G -printf '%s %p\n' 2>/dev/null | sort -n

# Xem dung lượng của một thư mục cụ thể
sudo du -sh /var/cache
```

Tùy chọn -xdev giới hạn tìm kiếm trong cùng filesystem để tránh đi qua các mount khác. Điều này hữu ích khi root filesystem đầy nhưng volume dữ liệu riêng vẫn còn dung lượng.

Không xóa file chỉ vì nó lớn. Xác định file thuộc ứng dụng nào, còn được tiến trình sử dụng không, có phải dữ liệu database hoặc backup cần lưu giữ không. Với log, ưu tiên log rotation, retention policy hoặc truncate theo hướng dẫn ứng dụng thay vì xóa tệp đang được tiến trình ghi.

### 6.3. Tìm nơi tiêu thụ inode

```bash
# Đếm số file trong một thư mục con
sudo find /var -xdev -type f | wc -l

# Đếm file theo thư mục cấp một trong một vùng cần điều tra
sudo find /var/spool -xdev -type f -printf '%h\n' 2>/dev/null |
  sort | uniq -c | sort -n

# Xem số lượng entry của các thư mục ứng viên
sudo find /var/cache -xdev -type f | wc -l
sudo find /tmp -xdev -type f | wc -l
```

Lệnh find có thể tốn CPU và I/O trên filesystem có hàng triệu file. Chạy trong phạm vi hẹp, cân nhắc thời điểm tải thấp và tránh lặp lại quá thường xuyên trên production.

### 6.4. File đã xóa nhưng vẫn chiếm dung lượng

Trên Linux, xóa một tên file không giải phóng block nếu tiến trình vẫn giữ file descriptor mở. Trường hợp này thường xảy ra với log đã bị xóa thủ công trong khi daemon vẫn tiếp tục ghi vào file cũ.

Kiểm tra:

```bash
# Tìm file đã bị xóa nhưng vẫn được tiến trình mở
sudo lsof +L1

# Xem descriptor của tiến trình nếu đã xác định PID
sudo ls -l /proc/<PID>/fd
```

Nếu phát hiện file deleted nhưng vẫn mở, xác định tiến trình và cách reload/reopen log theo tài liệu của ứng dụng. Không kill tiến trình tùy tiện vì có thể làm gián đoạn giao dịch hoặc gây mất dữ liệu chưa ghi.

### 6.5. Dung lượng dành riêng và khác biệt giữa df với du

Một số filesystem dành một phần block cho root hoặc metadata. Vì vậy, dung lượng hiển thị cho user thường có thể khác dung lượng tổng. Ngoài ra:

- du chỉ đếm file có thể duyệt qua thư mục.
- df phản ánh block được filesystem cấp phát, kể cả file đã unlink nhưng vẫn mở.
- Snapshot hoặc thin provisioning ở lớp cloud có cách tính dung lượng riêng.
- Filesystem metadata, journal và reserved blocks cũng chiếm không gian.

Nếu df báo đầy nhưng du cộng các thư mục không tương ứng, kiểm tra file deleted đang mở, reserved blocks, filesystem metadata, mount bị che khuất và các mount point riêng.

## 7. Kiểm tra I/O trên Linux

### 7.1. Quan sát theo thiết bị

```bash
# Thống kê I/O theo thiết bị, độ trễ và queue
iostat -xz 1

# Tiến trình đang đọc/ghi nhiều (nếu sysstat đã được cài)
pidstat -d 1

# Quan sát tiến trình và I/O tổng quan
iotop -oPa

# Thống kê bộ nhớ, run queue, swap và I/O wait
vmstat 1
```

Trong iostat, các trường thường hữu ích:

- r/s, w/s: số thao tác đọc/ghi mỗi giây.
- rMB/s, wMB/s hoặc các trường throughput tương đương: lượng dữ liệu đọc/ghi.
- await: thời gian trung bình một yêu cầu I/O hoàn tất, gồm thời gian chờ và phục vụ theo cách đo của công cụ.
- aqu-sz: kích thước hàng đợi trung bình trong khoảng lấy mẫu ở các phiên bản sysstat mới.
- %util: tỷ lệ thời gian thiết bị có I/O đang hoạt động theo cách công cụ báo cáo.

Ý nghĩa chi tiết có thể khác theo kernel, driver và loại thiết bị. Với thiết bị lưu trữ song song hoặc thiết bị ảo, %util 100% không phải lúc nào cũng đồng nghĩa đã đạt giới hạn throughput/IOPS. Hãy kết hợp với latency, queue, metric cloud và SLO ứng dụng.

### 7.2. Xem tiến trình gây I/O

Nếu một tiến trình tạo nhiều I/O:

- Kiểm tra file hoặc database đang truy cập.
- Xác định workload có chạy backup, scan, compaction, vacuum, indexing hoặc log rotation không.
- So sánh với lịch batch và thời điểm deployment.
- Xem ứng dụng có ghi đồng bộ quá thường xuyên hoặc tạo nhiều file nhỏ không.
- Kiểm tra retry storm có làm tăng lượng đọc/ghi lặp lại không.

Không giảm ưu tiên hoặc dừng tiến trình database chỉ dựa trên số I/O cao. I/O có thể là hoạt động bình thường để duy trì durability hoặc phục vụ truy vấn.

### 7.3. Phân biệt I/O wait với CPU bottleneck

I/O wait là thời gian CPU nhàn rỗi trong khi hệ thống có tác vụ I/O đang chờ hoàn tất theo cách kernel thống kê. I/O wait cao có thể là dấu hiệu lưu trữ chậm, nhưng không xác định được nguyên nhân cụ thể.

Hãy kiểm tra đồng thời:

- CPU utilization và run queue.
- iowait và latency theo thiết bị.
- Queue depth, IOPS, throughput và burst balance.
- Ứng dụng có nhiều synchronous write/fsync hay không.
- Network/storage path và metric ở phía cloud.
- RAM và cache hit, vì thiếu RAM có thể gây đọc/ghi nhiều hơn.

## 8. Kiểm tra disk và filesystem trên Windows

Windows dùng NTFS hoặc ReFS trong nhiều môi trường VM. Thay vì inode như Linux, cần theo dõi dung lượng volume, metadata filesystem, MFT và số lượng file.

### 8.1. Dung lượng volume và partition

```powershell
# Xem volume, filesystem và dung lượng
Get-Volume

# Xem disk và partition
Get-Disk
Get-Partition

# Dung lượng trống của volume
Get-CimInstance Win32_LogicalDisk |
  Select-Object DeviceID, Size, FreeSpace

# Xem dung lượng volume từ công cụ hệ thống
fsutil volume diskfree C:
```

### 8.2. Kiểm tra I/O và latency

```powershell
# Một số counter disk quan trọng
Get-Counter '\PhysicalDisk(_Total)\Disk Reads/sec', '\PhysicalDisk(_Total)\Disk Writes/sec', '\PhysicalDisk(_Total)\Avg. Disk sec/Read', '\PhysicalDisk(_Total)\Avg. Disk sec/Write', '\PhysicalDisk(_Total)\Current Disk Queue Length' -SampleInterval 2 -MaxSamples 5

# Xem tiến trình có hoạt động I/O
Get-Process | Sort-Object IOReadBytes -Descending |
  Select-Object -First 10 Name, Id, IOReadBytes, IOWriteBytes
```

Tên counter có thể khác theo ngôn ngữ Windows và cấu hình hệ thống. Có thể dùng Performance Monitor để chọn đúng counter của LogicalDisk, PhysicalDisk và tiến trình. Current Disk Queue Length cần được diễn giải cùng latency và IOPS; một giá trị queue cao có thể là bình thường nếu workload có nhiều I/O song song và thiết bị vẫn đáp ứng nhanh.

### 8.3. Kiểm tra filesystem và lỗi hệ thống

```powershell
# Kiểm tra filesystem online ở chế độ chỉ đọc
chkdsk C:

# Kiểm tra sự kiện disk, NTFS và storage trong System log
Get-WinEvent -FilterHashtable @{
  LogName = 'System'
  StartTime = (Get-Date).AddHours(-24)
} | Where-Object {
  $_.ProviderName -match 'disk|Ntfs|stor|vol'
} | Select-Object TimeCreated, ProviderName, Id, LevelDisplayName, Message
```

Không chạy chkdsk với tùy chọn sửa chữa trên production nếu chưa có bản sao lưu và kế hoạch bảo trì. Kiểm tra filesystem có thể tạo tải I/O đáng kể trên volume lớn.

## 9. Đọc metric volume ở lớp cloud

Metric trong guest và metric của dịch vụ lưu trữ đo các phần khác nhau của đường I/O. Hãy đối chiếu chúng theo cùng khoảng thời gian.

### Những metric cần xem

| Metric | Ý nghĩa | Câu hỏi chẩn đoán |
|---|---|---|
| Volume read/write IOPS | Số thao tác đọc/ghi mỗi giây | Có chạm giới hạn provisioned hoặc baseline không? |
| Volume read/write throughput | Lượng dữ liệu đọc/ghi mỗi giây | Có đạt trần MiB/s hoặc MB/s không? |
| Read/write latency | Thời gian phục vụ I/O | Độ trễ tăng ở volume hay chỉ trong guest? |
| Queue length / outstanding I/O | Yêu cầu đang chờ hoặc đang bay | Queue tăng cùng latency hay chỉ phản ánh concurrency? |
| Burst balance / credit | Khả năng burst còn lại nếu loại volume hỗ trợ | Hiệu năng giảm sau khi credit cạn không? |
| Volume status / health | Trạng thái thiết bị và sự kiện nền tảng | Có lỗi volume, detach hoặc maintenance không? |
| VM disk bandwidth/IOPS cap | Giới hạn I/O tổng hợp của instance | Tổng các volume có vượt trần VM không? |

Tên metric, đơn vị, cách lấy mẫu và độ trễ cập nhật khác nhau theo nhà cung cấp. Một số nền tảng cung cấp metric theo volume, một số còn cung cấp metric theo VM hoặc host. Không so sánh trực tiếp hai metric nếu chúng có aggregation period, đơn vị hoặc cách tính khác nhau.

### 9.1. Đối chiếu guest và cloud metric

- Guest báo latency cao, cloud volume latency cũng cao: điều tra volume, backend, giới hạn provisioned và burst.
- Guest báo latency cao nhưng cloud volume latency bình thường: xem filesystem, kernel, queue trong guest, sync write, driver và giới hạn tổng của VM.
- Cloud volume đạt IOPS nhưng throughput thấp: có thể workload dùng I/O nhỏ; kiểm tra IO size và IOPS cap.
- Throughput đạt trần nhưng IOPS chưa cao: có thể workload dùng I/O lớn; xem throughput cap và VM bandwidth.
- Volume chưa đạt giới hạn riêng nhưng nhiều volume cùng chậm: kiểm tra tổng I/O của VM, network path hoặc host-level limit.
- Metric cloud bình thường nhưng ứng dụng chậm: kiểm tra database lock, connection pool, CPU, RAM, cache và dependency.

### 9.2. Ví dụ nhận diện giới hạn

Một VM có hai volume. Volume dữ liệu được provision 8.000 IOPS, nhưng loại VM chỉ hỗ trợ tổng cộng 10.000 IOPS cho tất cả volume. Nếu volume thứ hai đang dùng 4.000 IOPS, VM có thể chạm giới hạn tổng dù volume dữ liệu riêng chưa đạt 8.000 IOPS.

Trong tình huống này, tăng IOPS riêng của volume dữ liệu có thể không cải thiện. Cần kiểm tra giới hạn instance, phân bổ I/O giữa các volume hoặc chọn loại VM có giới hạn tổng cao hơn nếu workload cần.

Các con số chỉ minh họa. Giới hạn thực tế phải tra cứu theo đúng loại VM, volume, vùng và cấu hình.

## 10. Xử lý filesystem đầy hoặc inode cạn

Trước khi dọn dẹp, xác định filesystem, owner của dữ liệu và chính sách lưu giữ. Không xóa database file, WAL, transaction log, journal hoặc backup chỉ vì chúng chiếm nhiều dung lượng.

### 10.1. Quy trình xử lý dung lượng đầy

1. Xác định mount point bị đầy bằng df -hT.
2. Xác định thư mục và file chiếm block bằng du/find.
3. Kiểm tra file deleted nhưng còn được tiến trình mở bằng lsof +L1.
4. Xác định dữ liệu có thể dọn theo retention policy.
5. Dừng hoặc giảm workload ghi nếu cần để ngăn dung lượng tiếp tục tăng.
6. Giải phóng dung lượng an toàn hoặc mở rộng volume/filesystem.
7. Xác minh ứng dụng có thể ghi lại và filesystem không tiếp tục tăng bất thường.
8. Điều chỉnh log rotation, retention, quota hoặc cảnh báo để tránh tái diễn.

Nếu volume cloud đã đầy ở mức provisioned nhưng filesystem chưa dùng hết, cần kiểm tra metric và cấu hình storage. Nếu filesystem đầy trong khi volume còn dung lượng chưa phân vùng, có thể cần mở rộng partition/filesystem.

### 10.2. Quy trình xử lý inode cạn

1. Xác nhận inode gần hoặc bằng 100% bằng df -i.
2. Khoanh vùng thư mục có số lượng file lớn.
3. Xác định loại file: cache, session, file tạm, spool, log nhỏ hoặc artifact.
4. Kiểm tra ứng dụng có đang dùng các file đó không.
5. Dọn file hết hạn theo chính sách hoặc điều chỉnh cơ chế tạo file.
6. Xác minh inode đã được giải phóng và ứng dụng tạo file mới được.
7. Thiết kế lại cache hoặc lưu trữ để giảm số file nhỏ nếu cần.

Nếu filesystem ext4 đã tạo với số inode quá thấp, chỉ tăng kích thước block device không tự tăng số inode hiện có. Có thể cần tạo filesystem mới với mật độ inode phù hợp và di chuyển dữ liệu theo kế hoạch. Với XFS, inode được cấp phát động nhưng vẫn có thể gặp giới hạn dung lượng hoặc metadata. Hãy kiểm tra tài liệu filesystem trước khi quyết định.

### 10.3. Mở rộng volume và filesystem trên Linux

Mở rộng disk thường gồm hai lớp: tăng dung lượng volume ở cloud, sau đó để guest nhận dung lượng mới và mở rộng partition/LVM/filesystem. Thứ tự và lệnh phụ thuộc layout.

Quy trình tổng quát:

1. Xác nhận volume hỗ trợ online resize và tạo snapshot/backup theo yêu cầu.
2. Tăng dung lượng volume trong cloud console/API.
3. Kiểm tra guest đã nhận kích thước disk mới bằng lsblk.
4. Nếu có partition, mở rộng partition bằng công cụ phù hợp.
5. Nếu dùng LVM, mở rộng physical volume/logical volume theo layout.
6. Mở rộng filesystem bằng công cụ đúng loại.
7. Kiểm tra df -hT và khả năng ghi của ứng dụng.

Ví dụ cho partition thứ nhất trên thiết bị giả định /dev/nvme1n1:

```bash
# Xác nhận disk và partition
lsblk

# Mở rộng partition (cần gói cloud-guest-utils hoặc growpart tương ứng)
sudo growpart /dev/nvme1n1 1

# Với filesystem ext4 trên partition đó
sudo resize2fs /dev/nvme1n1p1

# Với filesystem XFS đã mount tại /data, dùng lệnh riêng
sudo xfs_growfs /data

# Xác minh
df -hT /data
```

Không chạy cả resize2fs và xfs_growfs trên cùng filesystem. Chọn đúng lệnh theo filesystem. Tên thiết bị NVMe và cách đặt tên partition khác nhau theo nền tảng. Kiểm tra lsblk và findmnt trước khi thao tác.

Với LVM, quy trình có thể cần growpart, pvresize, lvextend và sau đó resize filesystem. Không áp dụng lệnh mẫu nếu chưa xác định chính xác PV, VG, LV và mount point.

### 10.4. Mở rộng volume và partition trên Windows

Sau khi tăng kích thước disk trong cloud:

1. Kiểm tra Windows đã nhận disk mới.
2. Xác định đúng disk và partition cần mở rộng.
3. Kiểm tra giới hạn kích thước có thể mở rộng và vùng unallocated liền kề.
4. Mở rộng partition/volume.
5. Xác minh dung lượng và ứng dụng.

Ví dụ PowerShell cho một volume đã được xác định:

```powershell
# Xem volume và partition
Get-Volume
Get-Partition

# Kiểm tra kích thước tối đa partition có thể mở rộng
Get-PartitionSupportedSize -DriveLetter F

# Mở rộng partition tới kích thước tối đa được hỗ trợ
$size = Get-PartitionSupportedSize -DriveLetter F
Resize-Partition -DriveLetter F -Size $size.SizeMax

# Xác minh
Get-Volume -DriveLetter F
```

Thay F bằng drive letter đúng. Không chạy lệnh trên volume hệ thống hoặc volume production nếu chưa xác định layout, backup và quy trình thay đổi. Partition cần có vùng unallocated phù hợp; nếu vùng trống không liền kề, cần xử lý layout riêng.

## 11. Xử lý I/O chậm hoặc volume chạm giới hạn

Khi xác định latency tăng, hãy phân biệt workload đã vượt cấu hình với lỗi backend hoặc lỗi trong guest.

### 11.1. Xác định kiểu workload

- **Random small I/O:** nhiều thao tác nhỏ ở vị trí ngẫu nhiên; thường nhạy với IOPS và latency. Ví dụ database OLTP.
- **Sequential large I/O:** đọc/ghi các vùng liên tiếp với block lớn; thường nhạy với throughput. Ví dụ streaming, backup hoặc xử lý file lớn.
- **Mixed workload:** kết hợp đọc/ghi ngẫu nhiên và tuần tự; cần đo tỷ lệ read/write và kích thước I/O.
- **Metadata-heavy:** tạo, xóa, đổi tên hoặc tra cứu rất nhiều file nhỏ; có thể bị giới hạn bởi filesystem metadata và inode.
- **Sync-write-heavy:** ứng dụng thường xuyên yêu cầu flush/fsync để bảo đảm durability; latency của từng thao tác có thể ảnh hưởng mạnh đến response time.

Không chọn volume chỉ dựa trên dung lượng. Một database nhỏ có thể cần IOPS cao; một kho dữ liệu lớn có thể cần throughput cao hơn.

### 11.2. Kiểm tra giới hạn volume

Đối chiếu IOPS/throughput thực tế với cấu hình và loại volume. Nếu đã chạm giới hạn:

- Tăng IOPS hoặc throughput provisioned nếu loại volume hỗ trợ.
- Chọn loại volume phù hợp với workload.
- Tăng kích thước volume nếu hiệu năng được gắn với dung lượng theo mô hình dịch vụ.
- Giảm I/O không cần thiết bằng cache, batching hoặc điều chỉnh ứng dụng.
- Phân vùng dữ liệu hoặc tách workload ra nhiều volume nếu kiến trúc và giới hạn VM cho phép.

Tăng kích thước volume không phải lúc nào cũng tăng hiệu năng. Một số loại volume gắn hiệu năng với dung lượng; một số loại cho phép cấu hình IOPS/throughput độc lập. Hãy kiểm tra pricing và giới hạn của loại volume cụ thể.

### 11.3. Kiểm tra giới hạn VM

Nếu tổng I/O của nhiều volume đã đạt giới hạn instance, tăng cấu hình volume riêng có thể không có tác dụng. Hướng xử lý:

- Đối chiếu giới hạn storage bandwidth/IOPS của instance family.
- Xem tổng I/O của tất cả volume cùng thời điểm.
- Kiểm tra network bandwidth nếu volume dùng đường truyền mạng.
- Xem loại instance có hỗ trợ optimized storage path hay không.
- Cân nhắc chuyển sang instance có giới hạn I/O tổng cao hơn.
- Tách workload đọc nhiều và ghi nhiều nếu có thể.

### 11.4. Giảm I/O không cần thiết

Các biện pháp ở tầng ứng dụng và hệ điều hành có thể cải thiện hiệu năng:

- Gom nhiều lần ghi nhỏ thành batch nếu không làm sai yêu cầu durability.
- Dùng cache phù hợp và theo dõi cache hit ratio.
- Tránh quét toàn bộ file hoặc directory quá thường xuyên.
- Tối ưu truy vấn và index để giảm đọc ngẫu nhiên không cần thiết.
- Điều chỉnh log level, log rotation và retention.
- Tránh chạy backup, compaction, indexing và batch job cùng lúc nếu chúng tranh chấp I/O.
- Kiểm tra retry storm và tác vụ lặp lại sau timeout.
- Dùng queue để giới hạn tốc độ ghi nếu producer nhanh hơn storage.

Không giảm fsync hoặc durability setting một cách tùy tiện với database. Thay đổi đó có thể tăng tốc nhưng làm tăng nguy cơ mất dữ liệu khi sự cố xảy ra.

## 12. Kiểm thử hiệu năng an toàn

Benchmark giúp xác định cấu hình có đáp ứng workload hay không, nhưng công cụ benchmark có thể tạo tải lớn và ghi dữ liệu. Chỉ chạy trong môi trường thử nghiệm hoặc cửa sổ được phê duyệt, với file test riêng trên filesystem đã mount.

### 12.1. Linux với fio

fio có thể mô phỏng nhiều kiểu workload và đo IOPS, throughput, latency. Ví dụ dưới đây dùng file test trong thư mục /mnt/bench, không ghi trực tiếp lên thiết bị block:

```bash
# Tạo thư mục test trên filesystem đã mount
sudo mkdir -p /mnt/bench

# Ví dụ workload đọc/ghi ngẫu nhiên 4 KiB, thời gian ngắn
# Chỉ chạy trên volume thử nghiệm, file test riêng.
sudo fio --name=rand-mix \
  --filename=/mnt/bench/fio-test.bin \
  --size=2G \
  --rw=randrw \
  --rwmixread=70 \
  --bs=4k \
  --iodepth=16 \
  --numjobs=2 \
  --direct=1 \
  --runtime=60 \
  --time_based \
  --group_reporting
```

Ý nghĩa một số tham số:

- rw=randrw: đọc/ghi ngẫu nhiên hỗn hợp.
- rwmixread=70: tỷ lệ đọc mục tiêu 70%, phần còn lại là ghi.
- bs=4k: kích thước I/O 4 KiB.
- iodepth=16: số I/O outstanding mục tiêu cho mỗi job trong chế độ hỗ trợ.
- numjobs=2: hai job chạy song song.
- direct=1: giảm ảnh hưởng page cache của guest trong bài test này.
- runtime=60: thời gian chạy 60 giây.

Kết quả phụ thuộc filesystem, driver, cache, thiết bị, loại volume và giới hạn VM. Không so sánh benchmark nếu workload profile khác nhau. Xóa file test sau khi xác nhận không còn tiến trình sử dụng và theo chính sách dữ liệu.

### 12.2. Windows

Có thể dùng DiskSpd trong môi trường kiểm thử để mô phỏng workload và đo latency/IOPS/throughput. Cần tạo file test riêng trên volume thử nghiệm, chọn kích thước, read/write ratio, block size, queue depth và thời gian phù hợp. Không chạy test trên raw disk hoặc volume production đang phục vụ database nếu chưa có kế hoạch tải và backup.

### 12.3. Đọc kết quả benchmark

Không chỉ xem IOPS trung bình. Cần xem:

- Read/write IOPS và throughput riêng.
- Latency trung bình và percentile nếu công cụ cung cấp.
- CPU utilization và memory pressure trong lúc test.
- Queue depth thực tế.
- Thời gian warm-up và ảnh hưởng cache.
- Kết quả khi chạy một job và khi có concurrency thực tế.
- Mức tải đồng thời từ ứng dụng khác.

Benchmark phải phản ánh kích thước I/O, tỷ lệ đọc/ghi, mức đồng thời và yêu cầu durability của workload thật.

## 13. Quy trình xử lý sự cố theo triệu chứng

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý có thể phù hợp |
|---|---|---|
| df -h báo 100%, df -i còn nhiều | Tìm file/thư mục lớn, deleted-open file, reserved blocks | Dọn theo retention hoặc mở rộng volume/filesystem |
| df -h còn trống nhưng df -i báo 100% | Tìm thư mục có quá nhiều file nhỏ | Dọn file hết hạn, giảm file churn hoặc chuyển thiết kế lưu trữ |
| Filesystem còn dung lượng nhưng ứng dụng báo Too many open files | Kiểm tra descriptor và giới hạn tiến trình | Sửa leak, đóng file đúng cách, điều chỉnh limit có kiểm soát |
| Latency cao và volume đạt IOPS cap | So sánh IOPS provisioned, thực tế và queue | Tăng IOPS, đổi volume type hoặc giảm random I/O |
| Throughput đạt trần nhưng IOPS chưa cao | Xem IO size và throughput cap | Tăng throughput hoặc tối ưu sequential I/O |
| Nhiều volume cùng chậm | Kiểm tra instance-level I/O/network cap | Đổi instance family, phân bổ workload hoặc giảm tổng I/O |
| df báo đầy nhưng du không tìm thấy file tương ứng | Kiểm tra lsof +L1, reserved blocks và mount | Reopen log, xử lý mount hoặc filesystem theo quy trình |
| Disk metric bình thường nhưng ứng dụng chậm | Xem sync write, lock, database, CPU/RAM và network | Tối ưu ứng dụng/dependency và xác định latency ở đúng lớp |
| Volume vừa mở rộng nhưng filesystem không đổi | Kiểm tra partition, LVM và filesystem | Mở rộng đúng lớp partition/LVM/filesystem |

### Quy trình chẩn đoán tổng quát

1. Xác định lỗi là hết block, hết inode, file descriptor hay I/O chậm.
2. Ghi lại VM, volume, filesystem, mount point, thời điểm và workload.
3. Kiểm tra metric guest và cloud trong cùng khoảng thời gian.
4. Tìm tiến trình hoặc thư mục tạo nhiều I/O/file.
5. Xác định giới hạn nằm ở volume, VM, filesystem hay ứng dụng.
6. Chọn thay đổi nhỏ nhất có thể khôi phục: dọn dữ liệu đúng retention, điều chỉnh workload hoặc mở rộng cấu hình.
7. Thực hiện trên phạm vi nhỏ hoặc cửa sổ bảo trì nếu có rủi ro.
8. Xác minh dung lượng, inode, latency, queue, ứng dụng và dữ liệu sau thay đổi.
9. Cập nhật cảnh báo, runbook và capacity plan để ngăn tái diễn.

## 14. Thiết kế giám sát và phòng ngừa

### 14.1. Cảnh báo dung lượng và inode

Nên cảnh báo theo cả tỷ lệ sử dụng và dung lượng còn lại. Một filesystem 100 GiB còn 10% tương đương 10 GiB; một filesystem 2 TiB còn 10% tương đương 200 GiB. Thời gian còn lại trước khi đầy có thể khác nhau rất lớn.

Theo dõi:

- Filesystem usage percentage.
- Free bytes và xu hướng tăng dung lượng.
- Inode usage percentage trên filesystem có inode cố định.
- Inode còn lại và tốc độ tạo file.
- Dung lượng log, temp, cache và database.
- File deleted nhưng còn mở nếu có công cụ phù hợp.

Cảnh báo nên dựa trên thời gian dự kiến đầy (time to exhaustion) nếu có thể, không chỉ một ngưỡng phần trăm cố định.

### 14.2. Cảnh báo hiệu năng I/O

Theo dõi theo volume và VM:

- IOPS và throughput đọc/ghi.
- Latency đọc/ghi.
- Queue depth hoặc outstanding I/O.
- Burst balance/credit.
- VM storage bandwidth/IOPS cap.
- Disk errors, timeout, detach và health event.
- I/O wait và application latency.

Dùng thời gian duy trì và baseline để giảm alert noise. Một đợt I/O cao ngắn có thể là backup bình thường; I/O cao kéo dài kèm p99 latency tăng và queue tăng mới có thể là sự cố người dùng cảm nhận.

### 14.3. Phòng ngừa ở tầng ứng dụng

- Thiết lập log rotation và retention.
- Đặt giới hạn cho cache và file tạm.
- Dọn session, spool và artifact hết hạn.
- Dùng object storage cho dữ liệu dạng file lớn hoặc cần lưu lâu, nếu phù hợp.
- Tránh tạo hàng triệu file nhỏ khi có thể gom vào database/object storage.
- Thiết lập quota theo user hoặc project khi filesystem hỗ trợ.
- Tách log, database và dữ liệu tạm sang volume phù hợp khi cần.
- Lập kế hoạch capacity theo tăng trưởng dữ liệu và tải đỉnh.

### 14.4. Phòng ngừa ở tầng hạ tầng

- Chọn volume type theo profile IOPS, throughput và latency.
- Kiểm tra giới hạn I/O tổng của instance.
- Đặt dung lượng và hiệu năng dự phòng phù hợp.
- Kiểm tra khả năng resize online và giới hạn của volume.
- Dùng snapshot/backup trước thay đổi có rủi ro.
- Diễn tập restore và mở rộng filesystem.
- Theo dõi chi phí provisioned IOPS/throughput và dung lượng.
- Định kỳ đánh giá lại volume khi workload thay đổi.

## 15. Ví dụ thực tế: database chậm vào cuối ngày

Một VM chạy database có volume dữ liệu 500 GiB. Ban ngày truy vấn bình thường, nhưng cuối ngày báo cáo chậm và ứng dụng timeout. Dashboard cho thấy:

- Filesystem còn 35% dung lượng.
- Inode còn nhiều.
- Volume IOPS gần chạm mức cấu hình.
- Throughput vẫn dưới giới hạn.
- Read latency tăng cùng queue depth.
- Một batch job chạy đồng thời với backup.

Đội vận hành điều tra:

1. df -h và df -i cho thấy không phải lỗi hết block hoặc inode.
2. iostat cho thấy nhiều I/O nhỏ ngẫu nhiên và await tăng.
3. Metric cloud xác nhận volume gần chạm IOPS cap, burst balance thấp nếu loại volume dùng cơ chế burst.
4. Lịch job cho thấy batch báo cáo và backup chạy đồng thời, tạo nhiều thao tác đọc/ghi.
5. Đội vận hành chuyển lịch backup ra ngoài giờ báo cáo, điều chỉnh concurrency và đo lại.
6. Nếu tải thường xuyên vẫn vượt baseline, đội đánh giá tăng IOPS provisioned hoặc chuyển sang volume phù hợp hơn.
7. Sau thay đổi, kiểm tra p95/p99 query latency, queue depth và chi phí.

Tăng dung lượng volume lên 1 TiB có thể không giúp nếu loại volume không tự tăng IOPS theo dung lượng hoặc nếu giới hạn nằm ở instance. Cần xác định cơ chế hiệu năng trước khi thay đổi.

### Biến thể: inode cạn dù còn dung lượng

Một worker Linux tạo file tạm riêng cho mỗi request. Sau nhiều ngày, df -h cho thấy còn 40 GiB nhưng df -i đạt 100%. Worker không thể tạo file mới và trả lỗi No space left on device.

Đội vận hành xác định thư mục temp có hàng triệu file cũ, xác nhận file nào hết hạn và không còn được tiến trình sử dụng, sau đó dọn theo retention. Nhóm phát triển bổ sung cơ chế xóa file sau khi xử lý, giới hạn số file tạm và cảnh báo inode. Nếu filesystem ext4 được tạo với số inode không phù hợp với workload lâu dài, nhóm lập kế hoạch di chuyển sang filesystem mới với mật độ inode thích hợp.

## 16. Những nhầm lẫn thường gặp

- **Còn dung lượng nghĩa là còn tạo được file.** Filesystem có thể hết inode hoặc metadata dù block còn trống.
- **Hết inode nghĩa là volume cloud đã hết dung lượng.** Inode là giới hạn metadata của filesystem; tăng dung lượng block không nhất thiết tăng số inode.
- **Queue depth cao luôn là lỗi.** Queue phải được đọc cùng latency, IOPS, throughput và concurrency của workload.
- **IOPS cao đồng nghĩa throughput cao.** Kích thước I/O quyết định lượng dữ liệu mỗi thao tác; workload nhiều I/O nhỏ có thể đạt IOPS cao nhưng throughput thấp.
- **Tăng volume size luôn tăng IOPS.** Cơ chế hiệu năng phụ thuộc loại volume; có loại tách dung lượng khỏi IOPS/throughput.
- **Volume chưa chạm giới hạn nghĩa là VM còn dư I/O.** Instance có thể có giới hạn tổng hợp thấp hơn tổng khả năng các volume.
- **Xóa log là giải phóng dung lượng ngay.** File đã unlink nhưng còn được tiến trình mở vẫn giữ block cho tới khi descriptor được đóng.
- **CPU thấp nghĩa là ứng dụng không bị nghẽn.** Ứng dụng có thể chờ disk, sync write hoặc dependency.
- **Chạy fio trên disk production là cách kiểm tra nhanh.** Benchmark có thể tạo tải và ghi dữ liệu; cần môi trường thử nghiệm và file test riêng.
- **Mở rộng disk ở cloud là đủ.** Guest có thể còn partition hoặc filesystem cũ; phải mở rộng đúng lớp.
- **Tắt fsync để tăng tốc là an toàn.** Thay đổi durability có thể làm tăng nguy cơ mất dữ liệu khi crash hoặc mất điện.

## 17. Tự kiểm tra

**Tình huống 1:** Một filesystem Linux còn 25 GiB nhưng ứng dụng báo No space left on device khi tạo file. Bạn kiểm tra gì trước?

**Gợi ý:** Chạy df -i để xem inode. Nếu inode đã hết, tìm thư mục có số lượng file nhỏ lớn bất thường và xác định file hết hạn có thể dọn.

**Tình huống 2:** df -h báo 100%, nhưng du không cộng đủ dung lượng. Nguyên nhân nào cần kiểm tra?

**Gợi ý:** Kiểm tra file deleted nhưng còn được tiến trình mở bằng lsof +L1, reserved blocks, metadata filesystem và mount point bị che khuất.

**Tình huống 3:** Volume đạt IOPS provisioned nhưng throughput còn thấp. Điều này có thể xảy ra không?

**Gợi ý:** Có. Workload có thể dùng nhiều I/O nhỏ, đạt giới hạn số thao tác trước khi đạt giới hạn lượng dữ liệu. Xem IO size và profile đọc/ghi.

**Tình huống 4:** Volume chưa đạt IOPS cap nhưng mọi disk gắn vào VM đều chậm cùng lúc. Nên kiểm tra gì?

**Gợi ý:** Kiểm tra giới hạn IOPS/throughput tổng của instance, network/storage path và workload cạnh tranh giữa các volume.

**Tình huống 5:** Sau khi tăng volume cloud, lệnh df vẫn hiển thị dung lượng cũ. Vì sao?

**Gợi ý:** Guest có thể đã nhận disk mới nhưng partition, LVM hoặc filesystem chưa được mở rộng. Kiểm tra lsblk, findmnt và layout trước khi chạy công cụ grow phù hợp.

**Tình huống 6:** Database chậm khi backup chạy đồng thời, latency và queue depth tăng nhưng dung lượng còn nhiều. Nên thử điều chỉnh nào trước?

**Gợi ý:** Kiểm tra IOPS/throughput cap và lịch workload. Có thể tách thời điểm backup, giới hạn concurrency hoặc điều chỉnh cấu hình volume sau khi benchmark.

## Kết luận

Sự cố disk đầy hoặc I/O chậm cần được phân biệt theo dung lượng block, inode, file descriptor, hiệu năng volume và giới hạn I/O của VM. Dùng df/du/lsof và công cụ hệ điều hành để xác định tình trạng filesystem; đối chiếu IOPS, throughput, latency, queue depth và burst metric ở cloud để tìm nút thắt lưu trữ. Khi xử lý, hãy xác định dữ liệu có thể dọn, mở rộng đúng lớp partition/filesystem hoặc điều chỉnh volume và workload theo profile thực tế. Giám sát xu hướng dung lượng, inode và hiệu năng cùng với quy trình backup/restore sẽ giúp phát hiện sớm và giảm nguy cơ tái diễn.
