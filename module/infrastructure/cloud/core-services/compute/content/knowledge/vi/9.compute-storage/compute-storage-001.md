# Boot disk, data disk và local ephemeral disk

Một máy ảo cloud thường sử dụng nhiều loại ổ đĩa. Hệ điều hành và thành phần khởi động nằm trên **boot disk**; dữ liệu ứng dụng nằm trên một hoặc nhiều **data disk**; tệp tạm, cache và dữ liệu trung gian có thể đặt trên **local ephemeral disk** gắn với máy chủ vật lý. Ba loại disk có mục đích, vòng đời, hiệu năng và mức độ bền dữ liệu khác nhau.

Chọn sai loại lưu trữ có thể khiến dữ liệu biến mất khi xóa VM, ứng dụng khởi động mà không có volume cần thiết, hoặc hệ thống phải trả chi phí cho hiệu năng vượt quá nhu cầu. Bài học này giải thích cách phân biệt ba loại disk, quản lý vòng đời và chọn chúng theo workload.

Bài học thuộc chương **Lưu trữ phục vụ compute** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Hiểu boot disk, data disk và local ephemeral disk giúp thiết kế vòng đời dữ liệu phù hợp với vòng đời compute.

## 1. Ổ đĩa trong môi trường cloud

### 1.1. Block storage và các giao diện lưu trữ

Trong môi trường máy ảo, ổ đĩa thường được trình bày cho hệ điều hành dưới dạng **block device**. Hệ điều hành đọc và ghi các khối dữ liệu theo địa chỉ logic. Người quản trị có thể tạo partition, filesystem, volume manager hoặc dùng thiết bị thô theo yêu cầu ứng dụng.

Cần phân biệt ba loại giao diện:

- **Block storage:** cung cấp thiết bị dạng khối để hệ điều hành hoặc ứng dụng quản lý filesystem và dữ liệu.
- **File storage:** cung cấp hệ thống tệp chia sẻ qua giao thức như NFS hoặc SMB.
- **Object storage:** lưu đối tượng theo key và metadata qua API; không được gắn như block device thông thường nếu không có lớp gateway hoặc driver riêng.

Boot disk và data disk trong bài này chủ yếu là block storage. Local ephemeral disk cũng có thể được hiển thị như block device, nhưng dữ liệu của nó gắn với vòng đời instance hoặc host vật lý.

### 1.2. Vòng đời của volume

Ổ đĩa có thể thuộc một trong ba kiểu vòng đời:

- **Gắn với VM:** volume được tạo và xóa cùng máy theo chính sách.
- **Quản lý độc lập:** VM có thể bị xóa nhưng volume vẫn tồn tại để gắn vào máy khác.
- **Gắn với host:** dữ liệu nằm trên thiết bị cục bộ và có thể mất khi instance dừng, di chuyển hoặc host gặp sự cố.

Không suy luận vòng đời chỉ từ tên “disk”. Cần kiểm tra thuộc tính delete-on-termination, retention policy, loại volume và tài liệu của dịch vụ cụ thể.

## 2. Boot disk

### 2.1. Boot disk là gì?

**Boot disk** là ổ đĩa chứa hệ điều hành và các thành phần cần thiết để VM khởi động. Trên Linux, nó thường chứa bootloader, kernel, initramfs, root filesystem và các gói hệ thống. Trên Windows, nó chứa các phân vùng khởi động và phân vùng hệ điều hành.

Boot disk thường được tạo từ **machine image** hoặc image hệ điều hành. Image là mẫu dùng để tạo disk; boot disk là volume cụ thể được cấp cho một VM. Image có thể chứa hệ điều hành, cấu hình khởi đầu và phần mềm đã cài sẵn.

Khi VM khởi động, firmware ảo hoặc boot mechanism của nền tảng đọc thành phần khởi động từ boot disk, sau đó hệ điều hành nạp và gắn root filesystem.

### 2.2. Persistent boot disk và ephemeral OS disk

Nhiều nền tảng cung cấp boot disk dưới dạng persistent block volume. Dữ liệu có thể tồn tại sau khi VM stop hoặc delete, tùy chính sách xóa.

Một số nền tảng có **ephemeral OS disk** hoặc cơ chế boot từ storage cục bộ. Hệ điều hành được triển khai trên lưu trữ gắn với host hoặc cache cục bộ; thay đổi trên boot disk có thể không được giữ lại qua một số thao tác vòng đời. Cần kiểm tra hành vi khi stop, deallocate, reimage, resize, migrate và host failure.

| Đặc điểm | Persistent boot disk | Ephemeral boot disk |
|---|---|---|
| Vị trí | Volume lưu trữ được quản lý theo chính sách cloud | Storage cục bộ hoặc cơ chế ephemeral của nền tảng |
| Vòng đời | Có thể tồn tại sau khi VM bị xóa nếu giữ volume | Thường gắn với VM/host và có thể tạo lại từ image |
| Khôi phục | Có thể dùng snapshot, backup hoặc attach sang VM khác nếu hỗ trợ | Thường khôi phục bằng cách tạo lại từ image và cấu hình |
| Phù hợp | VM cần giữ thay đổi hệ điều hành hoặc phục hồi từ disk | Workload bất biến, tự động tái tạo, không lưu dữ liệu duy nhất trên OS disk |

Persistent boot disk vẫn có thể bị xóa nếu bật delete-on-termination hoặc người vận hành xóa volume. Ephemeral OS disk phù hợp khi hệ thống có thể dựng lại OS từ image và cấu hình. Hãy xác minh chính sách của nhà cung cấp.

### 2.3. Thiết kế boot disk

Khi chọn boot disk, cần xem xét:

- **Dung lượng:** đủ cho OS, package, log hệ thống, agent và khoảng trống cập nhật.
- **Hiệu năng:** thời gian boot, cập nhật package và thao tác hệ thống phụ thuộc IOPS và latency.
- **Filesystem:** image hệ điều hành thường đã thiết lập filesystem phù hợp.
- **Mã hóa:** bật encryption at rest; kiểm tra quyền truy cập khóa nếu dùng customer-managed key.
- **Sao lưu:** dùng image chuẩn, snapshot hoặc backup theo yêu cầu khôi phục.
- **Quản lý cấu hình:** dùng cloud-init, configuration management hoặc image pipeline để giảm thay đổi thủ công.
- **Chính sách xóa:** xác định boot disk có được giữ lại khi xóa VM hay không.

Với server bất biến (immutable server), thay đổi phần mềm nên được đóng gói thành image hoặc deployment mới. Khi cần rollback, triển khai lại image trước đó thường dễ kiểm soát hơn sửa chữa thủ công trên boot disk đã thay đổi nhiều lần.

### 2.4. Khôi phục boot disk

Nếu boot disk hỏng hoặc hệ điều hành không khởi động:

1. Kiểm tra trạng thái VM, console log và sự kiện của nền tảng.
2. Xác định lỗi nằm ở cấu hình boot, filesystem, kernel, driver hay volume.
3. Nếu volume persistent và nền tảng hỗ trợ, tạo snapshot trước khi sửa.
4. Tạo VM cứu hộ và gắn boot disk lỗi như data disk nếu cần kiểm tra filesystem hoặc lấy log.
5. Tạo boot disk mới từ snapshot hoặc image đã xác minh nếu phải khôi phục.
6. Kiểm tra network, IAM, startup script, agent và cấu hình ứng dụng trước khi đưa VM trở lại phục vụ.

Không sửa filesystem khi disk vẫn đang được hệ điều hành khác ghi. Đưa volume về trạng thái nhất quán theo quy trình của nền tảng trước khi kiểm tra ngoại tuyến.

## 3. Data disk

### 3.1. Data disk là gì?

**Data disk** là ổ đĩa bổ sung dùng để lưu dữ liệu ứng dụng, database, file tải lên, log, queue hoặc nội dung cần tồn tại độc lập với hệ điều hành.

Tách dữ liệu khỏi boot disk giúp quản lý vòng đời và dung lượng rõ ràng. Có thể thay VM hoặc cập nhật image hệ điều hành mà vẫn giữ data volume để gắn vào máy mới, nếu chính sách volume cho phép.

Một VM có thể gắn nhiều data disk. Tùy hệ điều hành và ứng dụng, chúng có thể được dùng riêng, ghép thành logical volume, cấu hình RAID hoặc mount vào các thư mục khác nhau.

### 3.2. Lợi ích của việc tách boot disk và data disk

- **Vòng đời độc lập:** thay hoặc tái tạo VM mà vẫn giữ data volume nếu chính sách cho phép.
- **Quản lý dung lượng:** tăng dung lượng dữ liệu mà không cần tăng boot disk.
- **Hiệu năng riêng:** chọn loại volume và mức IOPS/throughput theo nhu cầu.
- **Sao lưu có mục tiêu:** đặt lịch snapshot hoặc backup theo mức độ quan trọng.
- **Bảo mật:** áp dụng encryption, quyền truy cập khóa và chính sách lưu giữ riêng.
- **Di chuyển:** tháo volume và gắn sang VM khác nếu đáp ứng giới hạn zone, loại instance và filesystem.

Tách disk không tự tạo tính sẵn sàng cao. Nếu chỉ có một volume trong một zone, volume vẫn có thể là điểm lỗi của ứng dụng. Cần kiểm tra khả năng dự phòng và replication của dịch vụ lưu trữ.

### 3.3. Data disk theo workload

| Workload | Cách bố trí thường gặp | Điều cần đánh giá |
|---|---|---|
| Web/API stateless | Boot disk cho OS; data disk khi cần cache hoặc file cục bộ | Có thể tái tạo VM; file quan trọng nên lưu ở dịch vụ bền vững |
| Database | Data disk cho data files, log hoặc WAL tùy thiết kế | IOPS, latency, throughput, durability và backup |
| File upload | Data disk hoặc file/object storage | Dung lượng, chia sẻ giữa VM, retention và backup |
| Logging | Disk riêng hoặc dịch vụ log tập trung | Dung lượng tăng, tốc độ ghi, rotation và thời gian lưu |
| Batch processing | Data disk cho input/output; local ephemeral cho scratch | Retry, checkpoint và khả năng tái tạo |
| Container host | Boot disk cho OS/runtime; volume riêng cho dữ liệu cần giữ | Writable layer không nên là nơi lưu dữ liệu duy nhất |

Với database, tuân thủ hướng dẫn của hệ quản trị về layout data, transaction log, WAL, cache và filesystem. Không tự ý chia nhiều disk hoặc dùng RAID nếu chưa hiểu ảnh hưởng đến durability, write ordering và recovery.

### 3.4. Phạm vi zone và region

Persistent data disk thường được cung cấp theo phạm vi zone hoặc region. Volume zonal có thể chỉ gắn được vào VM trong cùng zone. Nếu VM lỗi, có thể tạo VM thay thế trong zone đó và gắn lại volume; nhưng khi cả zone gặp sự cố, volume có thể không truy cập được.

Một số dịch vụ cung cấp regional disk hoặc volume replicated có thể hỗ trợ nhiều zone theo cơ chế riêng. Không mặc định mọi persistent disk đều được sao chép qua nhiều zone.

Khi thiết kế, xác định:

- Volume được tạo ở zone hay region.
- Có thể attach vào VM ở zone khác không.
- Có hỗ trợ multi-attach và bao nhiêu VM.
- Cơ chế replication và failover.
- Snapshot/backup có thể khôi phục sang zone hoặc region nào.

## 4. Local ephemeral disk

### 4.1. Local ephemeral disk là gì?

**Local ephemeral disk** là vùng lưu trữ từ thiết bị cục bộ trên host vật lý đang chạy VM, thường là SSD hoặc NVMe. Nền tảng có thể hiển thị nó như một hoặc nhiều block device bên trong VM.

Vì nằm gần CPU và không nhất thiết đi qua mạng tới hệ thống block storage, local disk thường có latency thấp và throughput/IOPS cao. Nó phù hợp với dữ liệu tạm, cache, scratch space, file trung gian và dữ liệu có thể tạo lại.

Dữ liệu trên local ephemeral disk không có cam kết tồn tại độc lập như persistent volume. Dữ liệu có thể mất khi VM stop/deallocate, migrate, resize, reimage, host failure hoặc khi instance được tạo lại. Tập hợp sự kiện cụ thể phụ thuộc nhà cung cấp và loại instance.

### 4.2. Trường hợp sử dụng phù hợp

Local ephemeral disk phù hợp với:

- **Temporary files:** file tạm trong quá trình xử lý.
- **Cache:** dữ liệu có thể nạp lại từ nguồn bền vững.
- **Scratch space:** vùng làm việc cho batch, ETL, xử lý ảnh hoặc mô phỏng.
- **Temporary database workspace:** dữ liệu trung gian hoặc index có thể tái tạo nếu ứng dụng hỗ trợ.
- **Checkpoint tạm:** checkpoint được đẩy định kỳ sang persistent storage trước khi kết thúc job.
- **Build workspace:** thư mục build và artifact trung gian có thể tạo lại.

Không dùng local ephemeral disk làm nơi lưu bản duy nhất của database, file người dùng, khóa mã hóa, cấu hình quan trọng hoặc checkpoint duy nhất. Dữ liệu cần giữ phải được sao chép sang persistent volume hoặc dịch vụ lưu trữ bền vững.

### 4.3. Vòng đời và rủi ro

Local ephemeral disk có thể được giữ qua một số thao tác reboot nhưng mất dữ liệu trong thao tác khác. Có nền tảng giữ dữ liệu qua reboot mềm nhưng xóa khi stop/deallocate; nền tảng khác có hành vi riêng khi live migration hoặc host maintenance.

Cần phân biệt:

- **Reboot guest OS:** khởi động lại hệ điều hành bên trong VM.
- **Stop/start:** dừng và khởi động VM theo semantics của cloud provider.
- **Deallocate:** giải phóng compute host hoặc capacity.
- **Resize:** thay đổi loại máy hoặc tài nguyên.
- **Reimage/recreate:** tạo lại hệ điều hành hoặc instance từ image.
- **Host failure/maintenance:** sự cố hoặc thao tác bảo trì ở hạ tầng vật lý.

Không suy ra dữ liệu sẽ còn hay mất chỉ từ tên thao tác. Kiểm tra tài liệu loại instance và thử nghiệm trong môi trường không chứa dữ liệu quan trọng.

### 4.4. So sánh local ephemeral và persistent data disk

| Tiêu chí | Persistent data disk | Local ephemeral disk |
|---|---|---|
| Vị trí | Dịch vụ block storage được quản lý | Thiết bị lưu trữ cục bộ trên host |
| Độ bền | Có thể tồn tại độc lập với VM theo chính sách | Gắn với vòng đời instance/host; có thể mất khi instance thay đổi |
| Hiệu năng | Phụ thuộc loại volume, mạng lưu trữ và mức provision | Thường latency thấp, throughput cao; phụ thuộc host và model |
| Attach/detach | Thường hỗ trợ theo giới hạn dịch vụ | Thường gắn với instance, không di chuyển như volume độc lập |
| Snapshot/backup | Thường có snapshot hoặc backup theo dịch vụ | Cần sao chép dữ liệu sang nơi bền vững |
| Mục đích | Dữ liệu cần giữ, database, file ứng dụng | Cache, scratch, temporary files, dữ liệu tái tạo được |

Local disk không mặc nhiên nhanh hơn mọi persistent disk. Cần benchmark trên instance và loại volume thực tế; persistent volume được provision đúng mức có thể đáp ứng tốt hơn local disk bị giới hạn bởi host.

## 5. Kiến trúc kết hợp ba loại disk

Một VM có thể sử dụng đồng thời boot disk, data disk và local ephemeral disk:

~~~mermaid
flowchart TB
    VM["Virtual Machine"]
    VM --> OS["Boot disk<br/>OS, kernel, agents"]
    VM --> DATA["Persistent data disk<br/>Database, uploads, application data"]
    VM --> TMP["Local ephemeral disk<br/>Cache, scratch, temporary files"]
    DATA --> SNAP["Snapshot / Backup"]
    TMP --> COPY["Copy dữ liệu cần giữ<br/>sang persistent storage"]
    SNAP --> RESTORE["Restore / Attach<br/>khi thay VM"]
~~~

Ví dụ một máy chủ xử lý ảnh:

- Boot disk chứa Linux, runtime và agent giám sát.
- Data disk chứa hàng đợi file đầu vào hoặc dữ liệu ứng dụng cần giữ.
- Local ephemeral disk chứa file ảnh trung gian sau khi giải nén và các buffer xử lý.
- Khi xử lý xong, kết quả được ghi sang persistent data disk hoặc object storage.
- Nếu VM bị thay thế, máy mới được tạo từ image và gắn lại data disk; scratch data được tạo lại.

Ứng dụng phải có khả năng xử lý việc scratch data biến mất và chạy lại job khi cần.

## 6. Gắn và quản lý data disk trong hệ điều hành

### 6.1. Quy trình tổng quát

Sau khi tạo volume và attach vào VM, hệ điều hành cần nhận diện thiết bị. Quy trình phổ biến:

1. Tạo volume với dung lượng, loại hiệu năng, zone và encryption phù hợp.
2. Attach volume vào VM.
3. Kiểm tra thiết bị mới xuất hiện trong hệ điều hành.
4. Nếu là disk trống mới, tạo partition hoặc filesystem.
5. Mount vào thư mục ứng dụng.
6. Cấu hình mount bền vững qua reboot.
7. Kiểm tra quyền truy cập, owner, filesystem và khả năng đọc/ghi.
8. Cấu hình monitoring, backup và cảnh báo dung lượng.

Không chạy lệnh format trên disk đang chứa dữ liệu. Xác định device mới bằng size, serial, volume ID hoặc đường dẫn ổn định trước khi thao tác.

### 6.2. Ví dụ trên Linux

Liệt kê block device và filesystem:

~~~bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
~~~

Kiểm tra định danh và filesystem:

~~~bash
sudo blkid
~~~

Giả sử `/dev/nvme1n1` là disk mới hoàn toàn, vừa được attach và đã xác minh không chứa dữ liệu cần giữ. Có thể tạo filesystem ext4:

~~~bash
sudo mkfs.ext4 /dev/nvme1n1
sudo mkdir -p /data
sudo mount /dev/nvme1n1 /data
~~~

**Lưu ý:** `mkfs.ext4` tạo filesystem mới và có thể phá hủy dữ liệu hiện có. Chỉ thực hiện trên disk trống đã xác minh. Với disk đã có partition, thường cần dùng thiết bị partition như `/dev/nvme1n1p1` thay vì format toàn bộ disk.

Để mount tự động sau reboot, lấy UUID:

~~~bash
sudo blkid -s UUID -o value /dev/nvme1n1
~~~

Sau khi xác nhận UUID, thêm một dòng tương ứng vào `/etc/fstab`:

~~~fstab
UUID=REPLACE_WITH_UUID /data ext4 defaults,nofail 0 2
~~~

Thay giá trị REPLACE_WITH_UUID bằng UUID thực tế. `nofail` cho phép hệ thống tiếp tục khởi động nếu volume không sẵn sàng; với ứng dụng bắt buộc phải có `/data`, cần thêm systemd dependency hoặc health check để service không ghi nhầm dữ liệu vào thư mục trống trên root disk.

Kiểm tra cấu hình trước khi khởi động lại:

~~~bash
sudo findmnt --verify
sudo mount -a
findmnt /data
df -h /data
~~~

Sau đó thiết lập owner và quyền thư mục theo tài khoản dịch vụ. Không cấp quyền ghi rộng như `777` nếu không có yêu cầu rõ ràng.

### 6.3. Tên thiết bị có thể thay đổi

Tên thiết bị như `/dev/sdb` hoặc `/dev/nvme1n1` có thể thay đổi khi VM khởi động lại, attach thêm disk hoặc thay đổi instance type. Không nên dùng tên thiết bị tạm thời trong cấu hình mount nếu nền tảng cung cấp UUID, filesystem label hoặc đường dẫn ổn định trong `/dev/disk/by-id`.

Với NVMe, tên thiết bị có thể phản ánh cách cloud provider ánh xạ volume. Dùng metadata hoặc serial để đối chiếu đúng volume ID trước khi thao tác.

### 6.4. Trên Windows

Trên Windows Server, disk mới thường xuất hiện trong Disk Management hoặc qua PowerShell. Quy trình thông thường gồm:

1. Xác định disk mới bằng dung lượng và trạng thái.
2. Đưa disk online nếu cần.
3. Khởi tạo partition style GPT cho trường hợp phù hợp.
4. Tạo volume và format filesystem như NTFS hoặc ReFS theo yêu cầu ứng dụng.
5. Gán drive letter hoặc mount point.
6. Thiết lập quyền NTFS và kiểm tra ứng dụng truy cập.
7. Xác minh volume xuất hiện sau reboot.

Chỉ initialize và format disk đã xác minh là disk mới. Nếu disk có dữ liệu từ máy cũ, kiểm tra trạng thái và filesystem trước khi ghi.

## 7. Hiệu năng và lựa chọn loại volume

### 7.1. Các chỉ số chính

Hiệu năng lưu trữ thường được đánh giá bằng:

- **IOPS (Input/Output Operations Per Second):** số thao tác đọc/ghi mỗi giây.
- **Throughput:** lượng dữ liệu truyền mỗi giây, thường đo bằng MB/s hoặc GB/s.
- **Latency:** thời gian hoàn thành một thao tác I/O.
- **Queue depth:** số yêu cầu I/O đang chờ hoặc đang được xử lý.
- **Block size:** kích thước mỗi thao tác đọc/ghi.
- **Read/write mix:** tỷ lệ đọc và ghi trong workload.

IOPS cao không tự động đồng nghĩa throughput cao. Với block size nhỏ, workload có thể bị giới hạn bởi IOPS; với block size lớn, có thể bị giới hạn bởi throughput. Latency cao có thể làm database chậm dù tổng throughput chưa đạt giới hạn.

### 7.2. Các nhóm storage phổ biến

| Nhóm storage | Đặc điểm | Workload thường phù hợp |
|---|---|---|
| General-purpose SSD | Cân bằng chi phí, IOPS và throughput; có thể có cơ chế burst | Boot disk, web/API, ứng dụng phổ thông |
| Provisioned IOPS SSD | Cho phép chọn mức IOPS cao hoặc ổn định theo dịch vụ | Database giao dịch, workload I/O ngẫu nhiên |
| Throughput-optimized HDD/SSD | Tối ưu thông lượng tuần tự hoặc chi phí trên dung lượng | Batch, data processing, log |
| Cold/archive storage | Chi phí thấp cho dữ liệu ít truy cập; độ trễ truy xuất cao hơn hoặc cần restore | Backup dài hạn, dữ liệu ít dùng |
| Local NVMe/instance store | Thiết bị cục bộ, latency thấp và hiệu năng cao; vòng đời ephemeral | Scratch, cache, temporary data |

Tên loại volume, mức hiệu năng, cơ chế burst và giá khác nhau giữa nhà cung cấp. Kiểm tra cả giới hạn theo volume và giới hạn tổng hợp của instance, vì VM có thể có trần IOPS hoặc throughput thấp hơn tổng năng lực các disk đã gắn.

### 7.3. Chọn theo mẫu truy cập

- Database OLTP thường có nhiều I/O nhỏ và ngẫu nhiên, nên latency và IOPS rất quan trọng.
- Data warehouse hoặc batch scan thường đọc khối lớn, nên throughput tuần tự có thể quan trọng hơn.
- Log ghi liên tục cần đánh giá write throughput, độ bền và chính sách rotation.
- Boot disk cần thời gian khởi động và cập nhật ổn định, nhưng thường không cần profile IOPS cao nhất.
- Cache và scratch có thể tận dụng local NVMe nếu dữ liệu có thể tạo lại.

Benchmark cần dùng mẫu tải gần thực tế: block size, read/write ratio, queue depth, số luồng và thời gian chạy. Kết quả đo ngắn có thể bị ảnh hưởng bởi cache hoặc burst credit, không đại diện cho tải dài hạn.

### 7.4. Ghép nhiều disk

Có thể ghép nhiều disk bằng LVM, RAID hoặc storage pool để tăng dung lượng hoặc hiệu năng. Tuy nhiên:

- RAID 0 có thể tăng throughput/IOPS tổng hợp nhưng không có dự phòng; lỗi một disk có thể làm mất toàn bộ array.
- RAID 1/10 có thể tăng khả năng chịu lỗi hoặc hiệu năng đọc tùy cấu hình, nhưng tốn thêm dung lượng.
- LVM giúp quản lý dung lượng linh hoạt nhưng không tự tạo replication hoặc backup.
- Snapshot của một disk không tự đảm bảo tính nhất quán giữa nhiều disk nếu ứng dụng ghi đồng thời.

Với database hoặc workload quan trọng, chỉ dùng RAID và multi-disk layout theo hướng dẫn của hệ điều hành, database và cloud provider. Không coi RAID là phương án thay thế backup.

## 8. Snapshot, backup và phục hồi dữ liệu

### 8.1. Snapshot là gì?

**Snapshot** là bản ghi trạng thái volume tại một thời điểm, thường được quản lý bởi dịch vụ lưu trữ cloud. Snapshot có thể được dùng để tạo volume mới, khôi phục dữ liệu hoặc tạo image tùy nền tảng.

Snapshot hữu ích cho sao lưu theo thời điểm, nhưng không tự đảm bảo ứng dụng đang ở trạng thái nhất quán. Nếu hệ điều hành hoặc database đang ghi, snapshot có thể chỉ phản ánh trạng thái crash-consistent.

### 8.2. Crash-consistent và application-consistent

- **Crash-consistent snapshot:** tương tự trạng thái disk khi máy bị mất điện đột ngột. Filesystem hoặc database có thể cần replay journal/log khi khởi động.
- **Application-consistent snapshot:** ứng dụng được chuẩn bị trước khi snapshot, ví dụ flush buffer, freeze filesystem hoặc dùng cơ chế backup của database để bảo đảm dữ liệu nhất quán.

Với database, dùng backup tool hoặc cơ chế snapshot tích hợp được hệ quản trị hỗ trợ. Nếu dữ liệu trải trên nhiều volume, cần phối hợp snapshot để giữ quan hệ giữa data files, transaction logs và metadata.

### 8.3. Backup không giống snapshot

Snapshot thường gắn với dịch vụ volume và có thể chia sẻ một số phụ thuộc cùng region hoặc tài khoản. Backup có thể bao gồm chính sách retention, catalog, bản sao khác vùng, khóa mã hóa và quy trình khôi phục riêng.

Cần xác định:

- Tần suất backup và thời gian lưu.
- RPO và RTO của workload.
- Có bản sao ở region hoặc account khác không.
- Ai có quyền xóa backup và snapshot.
- Khóa mã hóa có thể truy cập trong tình huống khôi phục không.
- Có thể restore về volume hoặc VM mới không.
- Quy trình kiểm tra dữ liệu sau restore.

Backup chỉ hữu ích khi đã thử restore và xác minh ứng dụng hoạt động với dữ liệu khôi phục.

### 8.4. Quy trình phục hồi data disk

1. Xác định snapshot/backup cần khôi phục và thời điểm dữ liệu.
2. Tạo volume mới từ bản sao đã chọn.
3. Chọn zone và loại volume phù hợp với VM đích.
4. Attach volume mới vào VM cứu hộ hoặc VM ứng dụng.
5. Kiểm tra filesystem, UUID, partition và quyền truy cập.
6. Nếu là database, thực hiện recovery theo hướng dẫn của hệ quản trị.
7. Kiểm tra tính toàn vẹn dữ liệu và chức năng ứng dụng.
8. Chuyển traffic hoặc ứng dụng sang volume đã khôi phục.
9. Ghi nhận thời gian phục hồi thực tế và cập nhật runbook.

Không ghi đè volume gốc khi chưa xác minh bản khôi phục. Giữ lại bản gốc theo chính sách điều tra hoặc rollback nếu cần.

## 9. Bảo mật và quản lý vòng đời

### 9.1. Mã hóa

Block volume có thể hỗ trợ mã hóa at rest bằng khóa do nhà cung cấp quản lý hoặc customer-managed key. Cần xác minh:

- Boot disk, data disk và snapshot đều được mã hóa theo chính sách.
- Quyền sử dụng khóa được cấp đúng cho VM, service hoặc tài khoản khôi phục.
- Khóa không bị vô hiệu hóa hoặc xóa trước khi hết thời gian lưu dữ liệu.
- Snapshot hoặc bản sao liên vùng có giữ nguyên chính sách mã hóa hay cần cấu hình lại.
- Dữ liệu truyền giữa VM và dịch vụ lưu trữ được bảo vệ theo yêu cầu.

Mã hóa volume không thay thế quyền truy cập filesystem. Ứng dụng vẫn cần phân quyền file, tài khoản dịch vụ và quản lý secret phù hợp.

### 9.2. Attach và detach an toàn

Trước khi detach data disk khỏi Linux VM:

1. Dừng ứng dụng đang ghi vào disk.
2. Flush dữ liệu còn trong buffer.
3. Unmount filesystem.
4. Xác minh thiết bị không còn được sử dụng.
5. Thực hiện detach từ cloud control plane.
6. Kiểm tra trạng thái volume trước khi attach vào VM khác.

Có thể dùng `sync`, `fuser` hoặc `lsof` để hỗ trợ kiểm tra. Không detach volume khi database hoặc filesystem vẫn đang ghi vì có thể gây hỏng dữ liệu.

Với Windows, dừng dịch vụ sử dụng volume và đưa disk offline theo quy trình phù hợp trước khi detach.

### 9.3. Multi-attach và filesystem dùng chung

Một số loại volume hỗ trợ gắn cùng lúc vào nhiều VM, nhưng khả năng này có giới hạn về loại volume, số VM, zone và hệ điều hành. Việc nhiều VM nhìn thấy cùng block device không có nghĩa filesystem thông thường có thể được nhiều máy ghi đồng thời an toàn.

Filesystem như ext4 hoặc NTFS thường không được thiết kế để nhiều host cùng mount read-write trên cùng block device mà không có cơ chế cluster phù hợp. Cần dùng clustered filesystem, distributed lock hoặc dịch vụ file storage được thiết kế cho truy cập đồng thời.

Nếu ứng dụng chỉ cần nhiều VM cùng đọc/ghi file, NFS, SMB hoặc object storage có thể phù hợp hơn multi-attach block storage.

### 9.4. Xóa volume và bảo vệ dữ liệu

Khi xóa VM, cần biết volume sẽ được giữ lại hay xóa theo. Chính sách có thể khác giữa boot disk và data disk, hoặc giữa loại instance.

Trước khi xóa tài nguyên:

- Kiểm tra delete-on-termination và retention policy.
- Xác minh volume không còn được ứng dụng sử dụng.
- Tạo backup nếu dữ liệu cần giữ.
- Kiểm tra snapshot có thể restore.
- Xác nhận yêu cầu lưu giữ dữ liệu và quy định nội bộ.
- Ghi nhận volume ID và chủ sở hữu để tránh xóa nhầm.

Dọn dẹp volume không còn dùng giúp giảm chi phí, nhưng cần có inventory, tag owner và quy trình phê duyệt cho dữ liệu quan trọng.

## 10. Chọn loại disk theo nhu cầu

| Nhu cầu | Boot disk | Data disk | Local ephemeral disk |
|---|---|---|---|
| Chứa hệ điều hành | Phù hợp | Không phải mục đích chính | Có thể dùng cho ephemeral OS disk nếu nền tảng hỗ trợ |
| Dữ liệu ứng dụng cần giữ | Không nên dùng làm nơi duy nhất nếu có thể tách | Phù hợp | Không phù hợp làm bản duy nhất |
| Database | Chỉ khi kiến trúc yêu cầu rõ | Phù hợp nếu chọn hiệu năng và durability đúng | Chỉ dùng cho cache/scratch hoặc dữ liệu có thể phục hồi |
| Cache có thể tạo lại | Có thể nhưng thường lãng phí boot storage | Có thể dùng nếu cần giữ lâu hơn | Rất phù hợp nếu hiệu năng và vòng đời đáp ứng |
| Scratch/batch temporary | Không nên dùng làm vùng tạm lớn | Có thể dùng | Phù hợp |
| Khôi phục VM | Image/snapshot boot disk | Attach hoặc restore volume | Tạo lại dữ liệu từ nguồn bền vững |
| Di chuyển giữa VM | Theo khả năng volume và zone | Thường hỗ trợ attach/detach theo giới hạn dịch vụ | Thường gắn với instance/host |

Máy chủ production có thể dùng boot disk vừa đủ cho OS, một hoặc nhiều data disk cho dữ liệu cần giữ và local ephemeral disk cho cache hoặc scratch. Workload stateless có thể ưu tiên boot disk bất biến và lưu dữ liệu ở dịch vụ ngoài VM.

## 11. Ví dụ thiết kế

### Ví dụ A: Web server stateless

Một nhóm chạy nhiều VM web giống nhau. Boot disk được tạo từ image chuẩn chứa hệ điều hành, runtime và agent. File upload được lưu ở object storage hoặc dịch vụ file dùng chung; cache tạm có thể đặt trên local ephemeral disk.

Khi VM lỗi, autoscaling tạo VM mới từ image. Không cần phục hồi cache vì ứng dụng có thể nạp lại. Log quan trọng được chuyển tới hệ thống logging tập trung thay vì chỉ giữ trên disk cục bộ.

### Ví dụ B: Database trên VM

Một VM database có persistent boot disk cho hệ điều hành và data disk hiệu năng cao cho database files. Transaction log hoặc WAL có thể nằm trên volume riêng nếu database và hướng dẫn thiết kế yêu cầu. Backup được tạo bằng công cụ database và lưu ở nơi độc lập với VM.

Đội vận hành theo dõi latency, IOPS, throughput, queue depth và dung lượng trống. Khi cần thay VM, data volume có thể được attach lại theo giới hạn zone và quy trình recovery. Local ephemeral disk chỉ được dùng cho cache hoặc dữ liệu trung gian có thể tái tạo.

### Ví dụ C: Batch xử lý dữ liệu lớn

Một worker tải input từ object storage, xử lý trên local NVMe và ghi kết quả về persistent storage. Job có checkpoint định kỳ để có thể tiếp tục sau khi instance bị thay thế.

Nếu local ephemeral disk mất dữ liệu, scheduler chạy lại job hoặc tải lại input. Thiết kế này tận dụng tốc độ local storage nhưng không phụ thuộc vào việc dữ liệu tạm tồn tại mãi.

### Ví dụ D: Thay VM nhưng giữ data volume

Một VM cũ cần nâng cấp hệ điều hành. Nhóm tạo snapshot data disk, tạo VM mới từ image chuẩn, attach volume theo đúng zone và mount bằng UUID. Ứng dụng được kiểm tra với dữ liệu trước khi chuyển traffic.

Khi VM mới hoạt động ổn định, nhóm mới xử lý VM cũ theo chính sách. Nếu cần rollback, data volume và snapshot vẫn có phương án khôi phục được kiểm soát.

## 12. Những sai lầm thường gặp

**Cho rằng mọi boot disk đều persistent.** Một số nền tảng hỗ trợ ephemeral OS disk hoặc chính sách xóa boot volume cùng VM. Cần kiểm tra loại disk và delete behavior.

**Lưu dữ liệu duy nhất trên local ephemeral disk.** Dữ liệu có thể mất khi instance hoặc host thay đổi. Chỉ dùng local disk cho dữ liệu có thể tạo lại hoặc đã được sao chép sang nơi bền vững.

**Format nhầm disk đang chứa dữ liệu.** Lệnh tạo filesystem có thể phá hủy dữ liệu. Luôn xác minh volume ID, size, partition và filesystem trước khi format.

**Dùng tên thiết bị cố định như `/dev/sdb`.** Thứ tự thiết bị có thể thay đổi. Ưu tiên UUID hoặc đường dẫn ổn định để mount.

**Chỉ tạo snapshot mà không thử restore.** Snapshot không chứng minh ứng dụng có thể khôi phục đúng. Cần diễn tập và kiểm tra dữ liệu sau restore.

**Coi snapshot luôn application-consistent.** Snapshot khi database đang ghi có thể chỉ crash-consistent. Dùng cơ chế backup hoặc quiesce được ứng dụng hỗ trợ.

**Detach disk khi ứng dụng vẫn đang ghi.** Có thể làm hỏng filesystem hoặc dữ liệu database. Dừng ứng dụng, flush và unmount trước khi detach.

**Dùng multi-attach với filesystem không hỗ trợ.** Nhiều VM cùng mount read-write một filesystem thông thường có thể làm hỏng dữ liệu. Cần clustered filesystem hoặc dịch vụ file chia sẻ phù hợp.

**Chỉ nhìn dung lượng mà quên hiệu năng.** Volume đủ GB nhưng thiếu IOPS hoặc throughput vẫn có thể làm ứng dụng chậm. Benchmark theo mẫu I/O thực tế.

**Coi RAID là backup.** RAID có thể cải thiện hiệu năng hoặc khả năng chịu lỗi disk nhưng không bảo vệ khỏi xóa nhầm, lỗi ứng dụng hoặc sự cố toàn vùng.

## 13. Checklist trước khi triển khai

- [ ] Xác định dữ liệu nào thuộc boot disk, data disk và local ephemeral disk.
- [ ] Kiểm tra vòng đời của từng loại disk khi stop, deallocate, resize, delete và host failure.
- [ ] Xác định chính sách delete-on-termination và retention.
- [ ] Chọn dung lượng, IOPS, throughput và loại volume theo workload.
- [ ] Kiểm tra phạm vi zone/region và khả năng attach/detach.
- [ ] Bật encryption at rest và xác minh quyền truy cập khóa.
- [ ] Cấu hình filesystem, mount bằng UUID hoặc định danh ổn định.
- [ ] Chỉ format disk mới sau khi xác minh không có dữ liệu cần giữ.
- [ ] Cấu hình backup/snapshot, retention và bản sao độc lập khi cần.
- [ ] Xác định crash-consistent hay application-consistent backup.
- [ ] Thử restore boot disk và data disk theo runbook.
- [ ] Dừng ứng dụng, flush và unmount trước khi detach.
- [ ] Kiểm tra multi-attach và filesystem trước khi nhiều VM truy cập đồng thời.
- [ ] Theo dõi dung lượng, latency, IOPS, throughput và lỗi I/O.
- [ ] Xác định cách tái tạo dữ liệu local ephemeral sau khi VM được thay thế.

## 14. Ghi nhớ

- **Boot disk** chứa hệ điều hành và thành phần khởi động; vòng đời có thể persistent hoặc ephemeral tùy nền tảng.
- **Data disk** lưu dữ liệu ứng dụng và có thể được quản lý độc lập với VM để hỗ trợ thay thế hoặc khôi phục máy.
- **Local ephemeral disk** thường nhanh và phù hợp với cache, scratch, temporary files; dữ liệu gắn với instance hoặc host và có thể mất.
- Phân biệt block, file và object storage để chọn giao diện lưu trữ phù hợp.
- Chọn volume theo IOPS, throughput, latency, block size và mẫu truy cập, không chỉ theo dung lượng.
- Snapshot và backup cần được kiểm tra bằng quy trình restore; database có thể cần application-consistent backup.
- Attach/detach phải thực hiện sau khi ứng dụng dừng ghi và filesystem được unmount.
- Multi-attach chỉ an toàn khi volume, filesystem và ứng dụng hỗ trợ truy cập đồng thời.
- Thiết kế tốt đặt dữ liệu cần giữ ở persistent storage và chỉ dùng local ephemeral disk cho dữ liệu có thể tạo lại.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Boot disk | Ổ đĩa chứa hệ điều hành và thành phần cần thiết để VM khởi động. |
| Data disk | Ổ đĩa bổ sung dùng để lưu dữ liệu ứng dụng. |
| Local ephemeral disk | Lưu trữ cục bộ gắn với VM hoặc host, có vòng đời tạm thời. |
| Persistent volume | Volume có thể tồn tại độc lập với vòng đời VM theo chính sách dịch vụ. |
| Block storage | Lưu trữ cung cấp thiết bị dạng khối cho hệ điều hành hoặc ứng dụng. |
| Machine image | Mẫu dùng để tạo boot disk hoặc máy ảo. |
| Attach / detach | Gắn hoặc tháo volume khỏi VM. |
| Filesystem | Cấu trúc quản lý tệp và thư mục trên block device. |
| UUID | Định danh duy nhất của filesystem hoặc thiết bị theo cách hệ điều hành cung cấp. |
| IOPS | Số thao tác đọc/ghi mỗi giây. |
| Throughput | Lượng dữ liệu truyền trong một đơn vị thời gian. |
| Latency | Thời gian hoàn thành một thao tác I/O. |
| Snapshot | Bản ghi trạng thái volume tại một thời điểm. |
| Crash-consistent | Trạng thái snapshot tương tự sau một lần crash đột ngột. |
| Application-consistent | Snapshot được tạo sau khi ứng dụng chuẩn bị dữ liệu để bảo đảm tính nhất quán. |
| Delete-on-termination | Chính sách xóa volume khi VM bị xóa hoặc kết thúc. |
| Multi-attach | Khả năng gắn một volume vào nhiều VM cùng lúc nếu dịch vụ hỗ trợ. |
| RAID | Cách kết hợp nhiều disk để tăng hiệu năng, dung lượng hoặc khả năng chịu lỗi. |
| Headroom | Dung lượng hoặc năng lực dự phòng để đáp ứng tăng trưởng và biến động. |
