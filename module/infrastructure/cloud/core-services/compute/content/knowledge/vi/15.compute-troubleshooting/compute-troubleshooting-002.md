# Máy không khởi động: boot log, serial console và rescue disk

Máy ảo không khởi động được có thể làm ứng dụng ngừng phục vụ, khiến đội vận hành mất quyền truy cập SSH/RDP hoặc không thể triển khai workload mới. Triệu chứng thường thấy là VM ở trạng thái Starting lâu, health check thất bại, màn hình console dừng ở bootloader, kernel panic, lỗi mount root filesystem hoặc hệ điều hành khởi động nhưng dịch vụ không sẵn sàng.

Để xử lý có hệ thống, cần xác định lỗi nằm ở control plane của nhà cung cấp, cấu hình phần cứng ảo, boot chain, hệ điều hành, storage hay dịch vụ khởi động. **Boot log** cho biết các bước hệ thống đã thực hiện; **serial console** cung cấp kênh quan sát và đôi khi cho phép tương tác khi mạng chưa hoạt động; **rescue disk** giúp gắn ổ đĩa hệ điều hành vào một máy hỗ trợ để kiểm tra và sửa chữa ngoại tuyến.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, các kỹ thuật này giúp khôi phục máy ảo an toàn và giảm thời gian gián đoạn. Quy trình cần bảo vệ dữ liệu, giữ bằng chứng chẩn đoán, xác minh đúng disk trước khi sửa và kiểm tra lại khả năng khởi động sau khi phục hồi.

## 1. Xác định chính xác máy đang gặp lỗi gì

“Không khởi động” có thể mô tả nhiều trạng thái khác nhau. Trước khi thay đổi cấu hình hoặc sửa disk, cần phân biệt VM không được cấp phát, VM không qua được quá trình boot, guest OS đã chạy nhưng mạng lỗi hay chỉ có ứng dụng không sẵn sàng.

### 1.1. Phân biệt control plane và guest OS

| Quan sát | Lớp có thể gặp vấn đề | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| API/console không tạo được VM, báo quota hoặc capacity | Control plane, quota, vùng, loại máy | Operation/event, quota, availability và policy |
| VM ở trạng thái provisioning/starting kéo dài | Control plane hoặc host | Operation status, provider health, boot diagnostics |
| VM đã running nhưng SSH/RDP không kết nối | Guest OS, network, firewall hoặc dịch vụ truy cập | Health check, serial console, boot log và network path |
| Console dừng ở firmware hoặc bootloader | Boot mode, boot order, disk hoặc bootloader | Screenshot/serial output, cấu hình UEFI/BIOS và boot disk |
| Kernel panic hoặc lỗi initramfs | Kernel, driver, initramfs hoặc root filesystem | Kernel log, bản vá gần đây và storage mapping |
| OS login được nhưng ứng dụng không chạy | systemd/service, cấu hình ứng dụng hoặc dependency | Journal, application log và health endpoint |

Trạng thái running ở control plane thường chỉ cho biết hypervisor đã bật VM. Nó không chứng minh guest OS đã boot xong, mạng đã sẵn sàng hay ứng dụng đang phục vụ.

### 1.2. Ghi lại bối cảnh trước khi điều tra

Thu thập các thông tin sau:

- VM ID, vùng/zone, loại instance và thời điểm lỗi bắt đầu.
- Image ID, phiên bản OS, kiến trúc CPU và boot mode nếu biết.
- Boot disk ID, data disk liên quan và cấu hình mã hóa.
- Thay đổi gần nhất: kernel update, driver, fstab, bootloader, resize disk, thay instance type, security policy hoặc startup script.
- Trạng thái health check, event, operation và cảnh báo từ provider.
- Lỗi quan sát được từ console, serial output, screenshot hoặc monitoring.
- Thời điểm reboot gần nhất và liệu VM có từng boot thành công sau thay đổi đó không.

Mốc thời gian rất quan trọng. Nếu máy ngừng boot ngay sau khi cài kernel mới, thay đổi đó là một giả thuyết cần kiểm tra. Tuy nhiên, không nên kết luận nguyên nhân chỉ dựa trên tương quan thời gian.

## 2. Boot chain của một máy ảo

Hiểu các giai đoạn boot giúp liên kết thông báo lỗi với thành phần cần kiểm tra.

~~~mermaid
flowchart TD
    A["Provider tạo VM và gắn boot disk"] --> B["Firmware BIOS/UEFI"]
    B --> C["Boot device và bootloader"]
    C --> D["Nạp kernel và initramfs/initrd"]
    D --> E["Kernel khởi tạo driver và thiết bị"]
    E --> F["Tìm và mount root filesystem"]
    F --> G["Init system: systemd hoặc tương đương"]
    G --> H["Network, cloud agent và dịch vụ nền"]
    H --> I["Ứng dụng và health check"]
~~~

Các giai đoạn có thể được hiểu như sau:

1. **Provisioning:** nền tảng cấp VM, kết nối NIC và boot disk, áp dụng cấu hình firmware ảo.
2. **Firmware:** BIOS hoặc UEFI tìm thiết bị có thể khởi động theo boot order.
3. **Bootloader:** GRUB hoặc bootloader tương ứng đọc cấu hình và chọn kernel.
4. **Kernel/initramfs:** kernel được nạp cùng initramfs để nhận driver và chuẩn bị thiết bị cần thiết.
5. **Root filesystem:** hệ điều hành tìm đúng root device, xác minh filesystem và mount root.
6. **Init system:** systemd hoặc init tương đương khởi chạy target và dịch vụ nền.
7. **Cloud initialization:** cloud-init hoặc guest agent áp dụng metadata, network và cấu hình lần đầu.
8. **Workload:** ứng dụng khởi động, health check đạt và máy sẵn sàng phục vụ.

Lỗi ở giai đoạn đầu thường khiến VM không đến được login prompt. Lỗi ở giai đoạn cuối có thể khiến VM đã boot nhưng vẫn không đáp ứng health check.

### 2.1. BIOS/UEFI và boot mode

BIOS và UEFI là hai kiểu firmware khởi động khác nhau. Một image được tạo cho UEFI có thể không khởi động đúng nếu VM được cấu hình theo legacy BIOS, hoặc ngược lại. Cấu hình boot mode, secure boot và loại partition table cần tương thích với image.

Khi thay loại máy hoặc chuyển image, kiểm tra:

- VM có hỗ trợ boot mode mà image yêu cầu không?
- Boot disk có chứa EFI System Partition nếu dùng UEFI không?
- Firmware có nhìn thấy đúng boot device không?
- Secure Boot có từ chối bootloader hoặc kernel chưa được ký không?
- Boot order có ưu tiên nhầm disk hoặc network boot không?

Không thay đổi BIOS/UEFI mode tùy tiện trên máy đang chứa dữ liệu. Thay đổi này có thể khiến firmware không nhận diện được bootloader hiện tại.

### 2.2. Bootloader, kernel và initramfs

Bootloader chịu trách nhiệm chọn kernel và truyền tham số boot. Nếu cấu hình GRUB bị hỏng, entry trỏ đến kernel không còn tồn tại hoặc bootloader không nằm đúng vị trí, máy có thể dừng trước khi kernel khởi chạy.

Initramfs chứa các driver và công cụ tối thiểu để kernel truy cập thiết bị cần thiết trước khi mount root filesystem. Nếu thiếu driver storage, module mã hóa, LVM hoặc cấu hình UUID không đúng, kernel có thể không tìm thấy root device.

Thông báo như **VFS: Unable to mount root fs**, **ALERT! UUID does not exist** hoặc **dracut-initqueue timeout** thường gợi ý lỗi ở đường truy cập root filesystem. Cần đối chiếu UUID, initramfs, driver và mapping disk trước khi sửa.

## 3. Đọc boot log và boot diagnostics

Boot log là nguồn bằng chứng quan trọng khi máy không có mạng hoặc không thể đăng nhập. Tùy nền tảng, log có thể được cung cấp qua boot diagnostics, console screenshot, serial output, instance screenshot hoặc log của dịch vụ quản lý máy.

### 3.1. Các nguồn log thường gặp

| Nguồn | Nội dung có thể thấy | Giới hạn |
| --- | --- | --- |
| Provider operation/event | Lỗi cấp phát, attach disk, host, quota hoặc policy | Không nhất thiết có log bên trong guest |
| Boot diagnostics screenshot | Màn hình firmware, bootloader, kernel hoặc login | Là ảnh chụp tại thời điểm nhất định |
| Serial console output | Thông báo boot, kernel, init system và một số lỗi | Cần bật/hỗ trợ console; output có thể bị giới hạn hoặc không lưu đủ |
| OS journal/system log | Lỗi dịch vụ, kernel và filesystem sau khi OS boot | Có thể không truy cập được nếu root disk không mount |
| Application log | Lỗi ứng dụng và dependency | Chỉ hữu ích sau khi ứng dụng hoặc logging agent chạy |

Nên lấy log từ provider trước khi reboot thêm lần nữa. Một lần boot mới có thể làm mất phần output cũ trong bộ đệm console hoặc thay đổi trạng thái khiến việc tái hiện lỗi khó hơn.

### 3.2. Tìm lỗi trong log

Không chỉ tìm dòng cuối cùng. Boot log có thể chứa nhiều cảnh báo không liên quan; lỗi đầu tiên làm quá trình boot dừng thường hữu ích hơn lỗi timeout phát sinh sau đó.

Các dấu hiệu thường gặp:

| Thông báo hoặc triệu chứng | Giả thuyết cần kiểm tra |
| --- | --- |
| No bootable device | Boot disk không gắn, boot order sai, firmware mode không khớp hoặc bootloader hỏng |
| grub rescue prompt | GRUB không tìm thấy partition/configuration cần thiết |
| Kernel panic | Kernel, driver, module, tham số boot hoặc filesystem |
| VFS: Unable to mount root fs | Root device, UUID, initramfs, driver storage hoặc filesystem |
| dracut-initqueue timeout | Thiết bị root chưa xuất hiện, LVM/RAID/encryption chưa sẵn sàng |
| Dependency failed for /data | Mount phụ thuộc thất bại, UUID sai hoặc volume không attach |
| Entering emergency mode | Filesystem check, fstab, mount hoặc systemd dependency |
| cloud-init failed | Metadata/network, user-data hoặc script khởi tạo |
| Login prompt xuất hiện nhưng SSH không hoạt động | Network, firewall, sshd hoặc route |

Thông báo cụ thể thay đổi theo distribution và phiên bản. Dùng log đầy đủ để xác nhận giả thuyết trước khi sửa.

### 3.3. Lấy log sau khi OS boot được

Nếu có thể đăng nhập qua SSH hoặc rescue environment, các lệnh Linux thường dùng:

~~~bash
# Boot hiện tại và các boot trước đó
sudo journalctl -b
sudo journalctl -b -1

# Lỗi mức error trở lên trong boot hiện tại
sudo journalctl -b -p err

# Kernel message
sudo dmesg -T

# Dịch vụ thất bại
systemctl --failed

# Trạng thái cloud-init nếu được cài
cloud-init status --long
~~~

Lệnh **journalctl -b -1** chỉ có dữ liệu nếu journal được lưu persistent và boot trước còn được giữ. Nếu journal chỉ lưu volatile, log có thể biến mất sau reboot.

Với hệ thống dùng log file truyền thống, kiểm tra **/var/log/syslog**, **/var/log/messages**, **/var/log/boot.log** hoặc log riêng của distribution. Không giả định mọi đường dẫn tồn tại trên mọi OS.

## 4. Serial console: quan sát khi mạng chưa sẵn sàng

Serial console cung cấp một kênh console ảo tương tự cổng serial của máy vật lý. Nó có thể hiển thị boot message và cho phép tương tác với guest OS ngay cả khi NIC, IP, route hoặc SSH/RDP chưa hoạt động.

### 4.1. Khi nào nên dùng serial console?

Serial console hữu ích khi:

- SSH/RDP không kết nối nhưng VM vẫn được cấp phát.
- Firewall hoặc network configuration chặn đường quản trị.
- Kernel boot đến một phần rồi dừng.
- Cần xem GRUB, emergency mode hoặc login prompt.
- Cần sửa cấu hình boot hoặc network từ console.

Serial console không thay thế boot diagnostics. Nếu VM chưa được host khởi chạy hoặc firmware không thấy boot disk, console có thể không cung cấp đủ thông tin để sửa; khi đó cần xem operation/event và disk attachment.

### 4.2. Điều kiện sử dụng

Khả năng serial console phụ thuộc provider, loại VM, vùng, image và cấu hình guest. Có thể cần:

- Bật boot diagnostics hoặc serial console trong cấu hình VM.
- Cấp quyền IAM/RBAC riêng để đọc hoặc kết nối console.
- Guest OS được cấu hình gửi console output đến serial port.
- Tài khoản console và mật khẩu hợp lệ nếu cần đăng nhập.
- Network/control-plane access đến dịch vụ console của provider.

Không bật quyền serial console rộng cho mọi người dùng. Console có thể cho phép truy cập shell ở mức đặc quyền, vì vậy cần audit, MFA hoặc cơ chế truy cập quản trị được tổ chức yêu cầu.

### 4.3. Linux: cấu hình console output

Trên Linux, kernel có thể được cấu hình gửi thông báo ra serial console bằng tham số kernel như **console=ttyS0** hoặc thiết bị serial tương ứng với nền tảng. Tên thiết bị và tốc độ baud phụ thuộc máy ảo.

Ví dụ minh họa cấu hình kernel command line:

~~~text
console=tty0 console=ttyS0,115200n8
~~~

Thứ tự tham số console có thể ảnh hưởng thiết bị nhận output chính. Không sao chép cấu hình trên mà chưa kiểm tra serial device của VM và hướng dẫn provider.

Trên hệ thống dùng systemd, có thể bật getty trên serial TTY phù hợp nếu cần đăng nhập tương tác:

~~~bash
sudo systemctl enable serial-getty@ttyS0.service
sudo systemctl start serial-getty@ttyS0.service
~~~

Chỉ bật login prompt trên console khi có kiểm soát truy cập phù hợp. Không đặt mật khẩu yếu hoặc để console quản trị mở cho đối tượng không được phép.

### 4.4. Windows: serial console và recovery

Windows VM có thể hỗ trợ serial console hoặc boot diagnostics theo nền tảng, nhưng khả năng tương tác phụ thuộc cấu hình boot, SAC/EMS, phiên bản Windows và dịch vụ provider. Nếu không có output hữu ích, dùng screenshot boot diagnostics, Windows Recovery Environment (WinRE), Safe Mode hoặc quy trình rescue do nhà cung cấp hỗ trợ.

Không áp dụng lệnh Linux hoặc giả định Windows có cùng boot chain. Với Windows, cần kiểm tra BCD, EFI System Partition, boot files, driver storage và trạng thái volume bằng công cụ phục hồi tương ứng.

## 5. Chẩn đoán theo giai đoạn boot

### 5.1. VM không qua provisioning

Nếu VM không chuyển sang trạng thái running:

1. Xem operation ID và event của lần tạo/khởi động.
2. Kiểm tra quota CPU, số VM, disk và địa chỉ IP.
3. Xác minh zone, instance type và capacity.
4. Kiểm tra policy, encryption key và quyền truy cập boot disk.
5. Xác minh boot disk đang attach đúng VM và ở trạng thái sẵn sàng.
6. Kiểm tra provider health hoặc sự cố vùng nếu nhiều VM cùng bị ảnh hưởng.

Không sửa filesystem khi provider chưa cấp được VM hoặc chưa attach được disk. Lỗi ở control plane cần được giải quyết ở lớp đó trước.

### 5.2. Firmware không tìm thấy boot device

Nếu thấy No bootable device hoặc firmware không tìm thấy ổ khởi động:

- Xác minh đúng volume ID và đúng boot disk.
- Kiểm tra disk có ở cùng zone/region theo yêu cầu không.
- Kiểm tra boot order và device mapping.
- Xác minh firmware mode BIOS/UEFI tương thích với image.
- Kiểm tra partition boot/EFI System Partition còn tồn tại.
- Xem disk có bị detach, restore nhầm snapshot hoặc thay thế bằng volume không chứa bootloader không.

Nếu disk attach đúng nhưng bootloader hỏng, cân nhắc rescue disk để kiểm tra partition và boot files.

### 5.3. Bootloader xuất hiện nhưng không nạp được kernel

Kiểm tra:

- GRUB entry có trỏ đến kernel và initramfs đang tồn tại không?
- Root UUID trong tham số kernel có khớp volume không?
- File cấu hình GRUB có bị sửa sai không?
- Kernel mới có tương thích với loại máy, kiến trúc và driver không?
- Secure Boot có từ chối bootloader/kernel không?

Nếu lỗi xuất hiện ngay sau kernel update, thử chọn kernel cũ từ GRUB nếu còn entry và còn package tương ứng. Sau khi boot thành công, kiểm tra package, module và initramfs của kernel mới trước khi cập nhật lại boot default.

### 5.4. Kernel không mount được root filesystem

Các nguyên nhân thường gặp:

- Boot disk không attach hoặc device path thay đổi.
- UUID trong GRUB, initramfs hoặc /etc/fstab sai.
- Driver storage không có trong initramfs.
- LVM, RAID hoặc disk encryption chưa được kích hoạt đúng thứ tự.
- Filesystem bị lỗi hoặc volume có lỗi I/O.

Đối chiếu lsblk, blkid, lvm pvs/vgs/lvs, kernel log và cấu hình mount. Nếu root filesystem bị lỗi, cần dừng thao tác ghi và đánh giá snapshot/backup trước khi chạy công cụ sửa chữa.

### 5.5. OS vào emergency mode

Systemd có thể đưa máy vào emergency mode khi filesystem quan trọng không mount được hoặc dependency bắt buộc thất bại. Thông báo thường chỉ ra mount unit hoặc device UUID gây lỗi.

Nếu volume phụ như /data không còn tồn tại, kiểm tra /etc/fstab. Một mount không bắt buộc có thể dùng tùy chọn phù hợp như nofail, nhưng mount chứa dữ liệu ứng dụng cần được xử lý rõ ràng để ứng dụng không ghi vào thư mục rỗng trên root disk.

Không xóa một dòng fstab chỉ để máy boot nhanh nếu chưa xác định ứng dụng có phụ thuộc dữ liệu ở mount point đó không.

### 5.6. OS boot xong nhưng health check thất bại

Khi login prompt xuất hiện nhưng ứng dụng không sẵn sàng, chuyển sang kiểm tra:

- NIC, DHCP/static IP, route, DNS và firewall.
- Cloud-init, guest agent và startup script.
- systemd unit, dependency và service timeout.
- Disk đầy, inode hết hoặc mount point sai.
- Secret, IAM identity và kết nối database/queue.
- Ứng dụng có bind đúng interface/port không?
- Health check có kiểm tra endpoint phù hợp và timeout hợp lý không?

Không cần dùng rescue disk nếu guest OS đã hoạt động và có thể điều tra qua console/SSH. Chỉ dùng phương án ngoại tuyến khi không thể sửa từ bên trong hoặc cần kiểm tra disk an toàn.

## 6. Rescue disk là gì?

Rescue disk là phương pháp dùng một môi trường hỗ trợ khác để truy cập ổ đĩa của VM bị lỗi. Với cloud VM, cách thường gặp là:

1. Dừng VM lỗi.
2. Tách boot disk khỏi VM đó nếu nền tảng cho phép.
3. Gắn boot disk vào một VM cứu hộ cùng vùng hoặc theo giới hạn của provider.
4. Mount filesystem để kiểm tra log và cấu hình.
5. Sửa lỗi có căn cứ, sau đó unmount và detach sạch.
6. Gắn boot disk trở lại VM ban đầu và thử boot.

Rescue disk có thể là ISO/recovery image, disk cứu hộ hoặc một VM helper chạy OS tương thích. Quy trình cụ thể phụ thuộc provider; không phải nền tảng nào cũng cho detach boot disk hoặc attach disk giữa mọi loại máy.

### 6.1. Khi nào nên dùng rescue disk?

Nên cân nhắc rescue disk khi:

- Guest OS không boot đủ để đăng nhập.
- Root filesystem có thể mount ngoại tuyến để sửa cấu hình.
- Cần đọc log, kiểm tra fstab, GRUB, initramfs hoặc file hệ thống.
- Cần sao chép dữ liệu ra nơi an toàn trước khi sửa.
- Cần chạy filesystem check khi volume đã unmount.

Không dùng rescue disk chỉ vì SSH bị chặn nếu serial console vẫn cho phép sửa network hoặc firewall. Mỗi lần detach/attach có thể làm thay đổi device mapping và tạo thêm rủi ro nếu thao tác nhầm volume.

## 7. Quy trình rescue disk an toàn

Trước khi sửa chữa, cần bảo toàn khả năng quay lại trạng thái ban đầu.

### 7.1. Chuẩn bị

1. Xác định chính xác VM và boot disk ID.
2. Kiểm tra mã hóa, KMS key, quyền attach và giới hạn vùng.
3. Chụp snapshot hoặc backup theo chính sách trước khi sửa.
4. Ghi lại cấu hình boot mode, disk mapping và trạng thái VM.
5. Thông báo downtime và dừng workload theo quy trình.
6. Chọn helper VM có OS/architecture tương thích và đủ quyền truy cập disk.

Snapshot là điểm phục hồi hữu ích nhưng không thay thế backup đã kiểm chứng. Nếu dữ liệu quan trọng, cần xác minh khả năng restore trước khi thực hiện sửa chữa có rủi ro.

### 7.2. Dừng VM và attach disk vào helper

Quy trình khái niệm:

~~~text
VM bị lỗi
  -> Stop/Deallocate theo hướng dẫn provider
  -> Snapshot boot disk
  -> Detach boot disk
  -> Attach disk vào rescue VM
  -> Xác minh volume ID và device serial
~~~

Một số provider yêu cầu VM phải ở trạng thái stopped/deallocated trước khi detach OS disk. Một số loại disk có giới hạn attach hoặc không hỗ trợ chia sẻ. Luôn chờ operation ở control plane hoàn tất trước khi thao tác trong guest OS.

### 7.3. Xác định đúng disk trên helper Linux

Sau khi attach, không giả định disk cứu hộ luôn là /dev/sdb. Tên có thể khác theo loại instance, NVMe và thứ tự attach.

~~~bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS
sudo blkid
sudo dmesg | tail -n 80
~~~

Đối chiếu dung lượng, partition, filesystem UUID và serial/volume ID với boot disk đã ghi nhận. Nếu không xác định chắc chắn thiết bị, dừng lại; không chạy fsck, mount ghi hoặc mkfs trên disk chưa rõ danh tính.

### 7.4. Mount filesystem có kiểm soát

Nếu chỉ cần đọc log và cấu hình, ưu tiên mount read-only. Ví dụ với filesystem Linux thông thường:

~~~bash
sudo mkdir -p /mnt/rescue
sudo mount -o ro /dev/ROOT_PARTITION /mnt/rescue
~~~

Lưu ý: với một số filesystem có journal, tùy chọn read-only vẫn có thể cần replay journal khi mount. Nếu cần giữ nguyên tuyệt đối trạng thái nguồn, hãy làm việc trên snapshot/clone và dùng tùy chọn no-recovery phù hợp với filesystem (ví dụ ext4 hoặc XFS có tùy chọn riêng). Chế độ no-recovery có thể khiến filesystem không nhất quán và không nên dùng để tiếp tục vận hành dữ liệu; mục đích của nó là kiểm tra ngoại tuyến có kiểm soát.

Nếu filesystem dùng LVM, cần phát hiện và kích hoạt volume group đúng cách trước khi mount logical volume. Ví dụ:

~~~bash
sudo pvs
sudo vgs
sudo lvs
sudo vgchange -ay
~~~

Tên volume group có thể trùng với VG trên helper VM. Cần kiểm tra kỹ để tránh kích hoạt nhầm volume hoặc xung đột tên. Không tự động mount tất cả volume group nếu helper đang chạy workload có LVM riêng.

Một số filesystem như XFS có thể cần tùy chọn mount đặc thù khi volume được clone hoặc có cùng UUID với filesystem khác. Không áp dụng tùy chọn sửa UUID hoặc replay log nếu chưa hiểu ảnh hưởng. Khi cần ghi, thực hiện trên snapshot/clone hoặc sau khi có backup phù hợp.

## 8. Sửa lỗi Linux từ rescue environment

### 8.1. Kiểm tra log và cấu hình

Sau khi mount root filesystem vào /mnt/rescue, có thể xem:

~~~bash
sudo less /mnt/rescue/var/log/syslog
sudo less /mnt/rescue/var/log/messages
sudo less /mnt/rescue/var/log/boot.log
sudo less /mnt/rescue/etc/fstab
sudo ls -la /mnt/rescue/boot
~~~

Đường dẫn log phụ thuộc distribution và journald configuration. Nếu journal persistent, dữ liệu có thể nằm dưới /var/log/journal trong filesystem được mount.

Kiểm tra các điểm thường gây lỗi:

- UUID trong /etc/fstab có tồn tại trong blkid không?
- Mount point có đúng filesystem và thiết bị không?
- Có tham số mount hoặc filesystem type sai không?
- Kernel và initramfs được GRUB tham chiếu có tồn tại không?
- Cấu hình network có tham chiếu NIC name cũ sau khi đổi loại máy không?
- Startup script có vòng lặp hoặc lệnh chờ vô hạn không?

### 8.2. Sửa fstab

Nếu xác định một UUID trong fstab đã cũ, đối chiếu với UUID thực tế của volume và sửa đúng entry. Không thay UUID theo phỏng đoán.

Ví dụ cấu hình cần xem xét:

~~~fstab
UUID=ROOT_UUID  /      ext4  defaults  0  1
UUID=DATA_UUID  /data  xfs   defaults,nofail  0  2
~~~

Đây chỉ là ví dụ. Root mount thường do initramfs/boot configuration điều khiển trước khi systemd đọc fstab; không nên thêm tùy chọn nofail cho root filesystem. Với mount dữ liệu bắt buộc, cần đảm bảo ứng dụng phụ thuộc vào mount unit thay vì âm thầm ghi vào thư mục /data rỗng trên root disk.

Sau khi sửa, có thể kiểm tra cú pháp và UUID trong rescue environment, nhưng một số lệnh mount -a sẽ mount vào môi trường helper chứ không phải root filesystem của máy lỗi. Chỉ chạy kiểm tra phù hợp với chroot và mount namespace đã chuẩn bị.

### 8.3. Kiểm tra và sửa filesystem

Nếu có dấu hiệu filesystem lỗi, trước hết xác minh partition đã unmount và không có process sử dụng. Chạy công cụ filesystem check trên filesystem đang mount có thể gây hỏng dữ liệu.

Ví dụ với ext filesystem:

~~~bash
# Chỉ chạy khi filesystem đã unmount và đúng thiết bị
sudo e2fsck -f -n /dev/ROOT_PARTITION
~~~

Tùy chọn -n kiểm tra mà không ghi sửa chữa. Nếu cần sửa, xem kết quả, xác minh backup/snapshot và dùng chế độ sửa phù hợp theo quy trình của tổ chức. Không dùng lệnh trên cho XFS.

Với XFS, công cụ kiểm tra là xfs_repair; filesystem phải được unmount. Một số tình huống cần log replay trước khi repair, và xfs_repair -L có thể làm mất metadata journal. Không chạy tùy chọn phá hủy log như bước đầu tiên. Hãy sao lưu hoặc clone volume và đánh giá với người có kinh nghiệm khi lỗi nghiêm trọng.

### 8.4. Tạo lại initramfs hoặc GRUB

Nếu log cho thấy initramfs thiếu driver hoặc cấu hình bootloader sai, có thể cần rebuild initramfs hoặc cài lại GRUB từ rescue environment. Đây là thao tác phụ thuộc distribution, firmware mode và cách phân vùng.

Trước khi thực hiện:

- Xác định root filesystem, boot partition và EFI System Partition.
- Xác định VM dùng UEFI hay BIOS.
- Mount đúng các filesystem cần thiết vào cây rescue.
- Bind mount /dev, /proc, /sys và /run nếu quy trình chroot yêu cầu.
- Đảm bảo package kernel/GRUB cần thiết có sẵn và repository phù hợp.

Ví dụ khung chuẩn bị chroot trên Linux:

~~~bash
sudo mount /dev/ROOT_PARTITION /mnt/rescue
sudo mount /dev/BOOT_PARTITION /mnt/rescue/boot
sudo mount /dev/EFI_PARTITION /mnt/rescue/boot/efi
sudo mount --bind /dev /mnt/rescue/dev
sudo mount --bind /proc /mnt/rescue/proc
sudo mount --bind /sys /mnt/rescue/sys
sudo mount --bind /run /mnt/rescue/run
sudo chroot /mnt/rescue
~~~

Không phải hệ thống nào cũng có partition riêng cho /boot hoặc EFI; chỉ mount những filesystem thực sự tồn tại. Các lệnh rebuild initramfs/GRUB khác nhau giữa Debian/Ubuntu và RHEL-family, đồng thời phải phù hợp BIOS/UEFI. Dùng tài liệu của distribution và provider cho đúng image trước khi cài lại bootloader.

### 8.5. Unmount và trả disk về VM gốc

Sau khi sửa:

1. Ghi lại thay đổi và kiểm tra file cấu hình.
2. Thoát chroot nếu đã vào.
3. Unmount các bind mount theo thứ tự ngược.
4. Unmount boot, EFI và root filesystem.
5. Xác minh không còn mount hoặc process giữ disk.
6. Detach disk khỏi helper VM và chờ operation hoàn tất.
7. Attach disk trở lại VM ban đầu theo device mapping và boot mode cũ.
8. Khởi động VM và quan sát boot diagnostics/serial console.

Không detach khi filesystem vẫn đang mount hoặc có I/O chưa flush. Nếu thao tác sửa thất bại, giữ snapshot/clone và ghi nhận trạng thái trước khi thử phương án khác.

## 9. Sửa lỗi Windows bằng recovery environment

Windows VM thường dùng boot manager và Boot Configuration Data (BCD). Nếu máy không boot, cần xác định lỗi ở boot files, EFI System Partition, driver storage, update hoặc filesystem.

Các nguồn hỗ trợ:

- Boot diagnostics screenshot và serial output nếu được provider hỗ trợ.
- Windows Recovery Environment (WinRE) hoặc recovery ISO.
- Safe Mode hoặc Startup Repair khi có thể truy cập.
- Disk Management, DiskPart và công cụ kiểm tra filesystem.
- Log trong thư mục Windows như Windows\System32\winevt\Logs nếu có thể đọc ngoại tuyến.

Quy trình khái niệm:

1. Snapshot boot disk và dừng VM.
2. Attach disk vào helper Windows hoặc boot từ recovery media theo hướng dẫn provider.
3. Xác định đúng disk và volume letter trong recovery environment; ký tự ổ đĩa có thể khác khi boot bình thường.
4. Kiểm tra filesystem và log trước khi sửa.
5. Xác minh EFI System Partition, boot files và BCD.
6. Kiểm tra driver storage/network và bản cập nhật gần nhất.
7. Sửa lỗi bằng Startup Repair hoặc công cụ tương ứng, sau đó tháo disk sạch.
8. Gắn lại disk và thử boot, xác minh event log và dịch vụ.

Các lệnh như chkdsk, sfc, DISM hoặc bcdboot có phạm vi và điều kiện sử dụng khác nhau. Chỉ chạy trên đúng volume và đúng chế độ offline/online. Không format EFI partition hoặc chạy lệnh ghi BCD theo phỏng đoán.

Nếu lỗi xuất hiện ngay sau Windows Update hoặc driver update, có thể dùng WinRE để uninstall quality/feature update hoặc rollback driver nếu tùy chọn được hỗ trợ. Trước khi thực hiện cần có snapshot và kiểm tra khả năng tương thích với image/provider.

## 10. Những nguyên nhân phổ biến và hướng xử lý

| Nguyên nhân | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| Boot disk không attach hoặc sai mapping | Firmware báo không có boot device | Xác minh disk ID, attachment, boot order và zone |
| BIOS/UEFI không khớp | Firmware không tìm thấy bootloader | Khôi phục boot mode tương thích với image |
| GRUB/BCD hỏng | Dừng ở bootloader hoặc boot manager | Dùng rescue/recovery để kiểm tra và sửa boot files |
| Kernel hoặc driver lỗi | Kernel panic, lỗi thiết bị | Boot kernel cũ, kiểm tra driver và rebuild initramfs |
| UUID/fstab sai | Root mount fail hoặc emergency mode | Đối chiếu UUID và sửa entry có bằng chứng |
| Filesystem lỗi | I/O error, journal/check failure | Snapshot, unmount và kiểm tra bằng công cụ đúng filesystem |
| Disk đầy | Service hoặc boot step thất bại | Kiểm tra dung lượng/inode, dọn có kiểm soát hoặc mở rộng disk |
| Cloud-init/startup script lỗi | OS boot nhưng provisioning không hoàn tất | Đọc log cloud-init, metadata và script |
| Network config sai | VM chạy nhưng SSH/RDP mất | Dùng serial console hoặc rescue để sửa NIC, route và firewall |
| Permission/SELinux lỗi | Service không đọc được file hoặc bị từ chối | Kiểm tra owner, mode, label và audit log |
| KMS/key permission | Boot disk không giải mã/attach được | Kiểm tra key state, IAM/RBAC và policy |

Một số lỗi có thể xuất hiện đồng thời. Ví dụ VM đổi loại máy làm tên NIC thay đổi, khiến network không lên; đồng thời cloud-init chờ metadata và health check timeout. Cần đọc log theo thứ tự boot thay vì sửa tất cả cấu hình cùng lúc.

## 11. Phòng ngừa sự cố boot

Để giảm khả năng VM không khởi động sau thay đổi:

- Dùng image đã kiểm thử với loại máy, kiến trúc và firmware mode dự kiến.
- Giữ ít nhất một kernel entry đã biết hoạt động khi áp dụng kernel update nếu distribution hỗ trợ.
- Kiểm tra initramfs, GRUB/BCD và boot files trong pipeline image.
- Dùng UUID hoặc định danh ổn định cho mount; kiểm tra fstab trước reboot.
- Không phụ thuộc vào device name dễ thay đổi sau khi đổi instance type.
- Có snapshot/backup theo chính sách trước thay đổi boot disk hoặc filesystem.
- Áp dụng thay đổi theo canary cho nhóm VM trước khi rollout toàn fleet.
- Bật boot diagnostics và lưu serial output theo chính sách.
- Duy trì quyền truy cập console và runbook rescue được kiểm thử.
- Theo dõi disk health, capacity, I/O error và provider events.
- Kiểm tra KMS key, IAM và quyền attach khi thay đổi identity hoặc tài khoản.

## 12. Runbook xử lý VM không khởi động

Một runbook ngắn có thể giúp đội trực xử lý theo cùng thứ tự:

1. **Xác nhận phạm vi:** một VM hay nhiều VM trong cùng vùng/nhóm image.
2. **Kiểm tra control plane:** operation, provider health, quota, host và trạng thái disk.
3. **Thu thập bằng chứng:** boot screenshot, serial output, event, thời điểm và thay đổi gần nhất.
4. **Xác định boot stage:** firmware, bootloader, kernel, root mount, init system hay application.
5. **Chọn kênh truy cập:** SSH/RDP nếu OS chạy; serial console nếu mạng chưa hoạt động; rescue disk nếu cần sửa ngoại tuyến.
6. **Bảo vệ dữ liệu:** snapshot/backup và xác định disk ID trước mọi thao tác ghi.
7. **Sửa một nguyên nhân có bằng chứng:** tránh thay nhiều cấu hình cùng lúc.
8. **Trả disk về đúng VM:** unmount, detach, attach đúng mapping và khởi động.
9. **Xác minh:** boot hoàn tất, network, agent, filesystem, service và health check.
10. **Ghi nhận:** nguyên nhân gốc, thay đổi, thời gian phục hồi và hành động phòng ngừa.

### 12.1. Cây quyết định nhanh

~~~mermaid
flowchart TD
    A["VM không khởi động"] --> B{"Control plane báo running?"}
    B -- "Không" --> C["Kiểm tra operation, quota, host, zone, disk và KMS"]
    B -- "Có" --> D{"Có boot output?"}
    D -- "Không" --> E["Kiểm tra boot diagnostics, firmware và serial support"]
    D -- "Có" --> F{"Đã đến login prompt?"}
    F -- "Có" --> G["Kiểm tra network, agent, service và health check"]
    F -- "Không" --> H{"Lỗi nằm ở bootloader/kernel/root mount?"}
    H -- "Có" --> I["Snapshot rồi dùng rescue/recovery environment"]
    H -- "Chưa rõ" --> J["Đọc log đầy đủ và xác định boot stage"]
    I --> K["Sửa, unmount, reattach và boot thử"]
    K --> L["Xác minh OS, network và ứng dụng"]
    C --> M["Khởi động lại sau khi control plane ổn định"]
    E --> J
    J --> H
~~~

## 13. Ví dụ: VM Linux không boot sau khi thay đổi fstab

Một VM Linux chạy dịch vụ xử lý dữ liệu. Nhóm vận hành vừa thêm data volume và sửa /etc/fstab để mount vào /data. Sau reboot, VM vào emergency mode và health check thất bại.

Quy trình điều tra:

1. Xác nhận control plane báo VM đã được cấp phát và boot diagnostics cho thấy kernel đã chạy.
2. Mở serial console, đọc thông báo systemd cho biết mount unit của /data thất bại.
3. Xác minh data volume có còn attach và đúng ID không.
4. Nếu guest không vào được shell, snapshot boot disk và dùng helper VM để mount root filesystem.
5. Đọc /etc/fstab, phát hiện UUID trong entry /data không khớp với UUID thực tế của data volume.
6. Xác minh dữ liệu volume vẫn tồn tại; cập nhật entry bằng UUID đúng và giữ tùy chọn mount phù hợp với vai trò dữ liệu.
7. Kiểm tra cấu hình mount, unmount sạch và detach boot disk khỏi helper.
8. Gắn boot disk trở lại VM gốc, khởi động và quan sát serial output.
9. Xác minh /data mount đúng, ứng dụng có quyền truy cập và health check đạt.
10. Cập nhật runbook để lần sau kiểm tra UUID và mount dependency trước reboot.

Nếu /data là dữ liệu bắt buộc của ứng dụng, cần cấu hình service phụ thuộc mount unit. Chỉ thêm nofail có thể giúp OS boot tiếp nhưng cũng có thể khiến ứng dụng chạy trên thư mục /data rỗng ở root filesystem, tạo dữ liệu sai vị trí.

## 14. Những sai lầm thường gặp

- Chỉ nhìn trạng thái running của provider và cho rằng guest OS đã sẵn sàng.
- Reboot liên tục trước khi lưu boot log và serial output.
- Nhầm lỗi network/SSH với lỗi boot filesystem.
- Thay BIOS/UEFI mode mà không kiểm tra image và partition layout.
- Chạy mkfs hoặc filesystem repair trên nhầm disk.
- Mount boot disk có ghi khi chưa snapshot hoặc chưa xác định trạng thái filesystem.
- Detach disk khi filesystem còn mount hoặc I/O chưa flush.
- Dùng device path /dev/sdX cố định dù mapping có thể thay đổi.
- Chạy fsck trên filesystem đang mount.
- Dùng tùy chọn repair phá hủy journal mà không có bản sao phục hồi.
- Xóa hoặc sửa fstab để vượt emergency mode mà không xác định dependency ứng dụng.
- Gắn boot disk vào helper khác zone hoặc không có quyền dùng KMS key.
- Không xác minh ứng dụng và health check sau khi VM boot thành công.

## 15. Nguyên tắc vận hành

1. **Phân biệt control plane và guest:** xác định VM chưa được cấp phát hay guest OS không boot.
2. **Thu thập log sớm:** lưu operation/event, boot diagnostics và serial output trước khi reboot lại.
3. **Khoanh vùng boot stage:** firmware, bootloader, kernel, root filesystem, init system hay application.
4. **Dùng serial console đúng mục đích:** quan sát hoặc truy cập khi network chưa sẵn sàng, với quyền được kiểm soát.
5. **Snapshot trước sửa chữa:** giữ khả năng phục hồi và bằng chứng.
6. **Nhận diện disk bằng ID/UUID:** không dựa vào tên thiết bị có thể thay đổi.
7. **Ưu tiên đọc-only:** kiểm tra log và cấu hình trước khi ghi; filesystem repair phải chạy trong điều kiện phù hợp.
8. **Detach sạch:** unmount và flush trước khi tháo volume khỏi helper.
9. **Kiểm thử sau phục hồi:** xác minh boot, network, cloud agent, mount, dịch vụ và health check.
10. **Cập nhật image/runbook:** đưa nguyên nhân gốc và biện pháp phòng ngừa vào pipeline để tránh lặp lại.

Boot log cho biết máy dừng ở đâu; serial console giúp quan sát khi đường mạng chưa hoạt động; rescue disk cung cấp môi trường sửa chữa ngoại tuyến khi guest OS không thể tự khởi động. Kết hợp ba công cụ theo đúng giai đoạn, cùng với snapshot và xác minh disk cẩn thận, giúp khôi phục VM có kiểm soát và bảo vệ dữ liệu trong quá trình xử lý.
