# Boot Diagnostics, Serial Console và khắc phục lỗi khởi động

Một máy ảo Azure có thể hiển thị trạng thái **Running** nhưng vẫn không nhận kết nối SSH hoặc RDP. Nguyên nhân có thể chỉ là Network Security Group (NSG) chặn cổng, nhưng cũng có thể là hệ điều hành bị kẹt ở bootloader, không tìm thấy phân vùng hệ thống, lỗi cập nhật kernel, ổ đĩa đầy hoặc dịch vụ mạng chưa khởi động. Nếu chỉ thử mở thêm cổng hay khởi động lại nhiều lần, bạn có thể kéo dài thời gian gián đoạn và làm mất dấu vết cần thiết để điều tra.

**Boot Diagnostics** và **Azure Serial Console** là hai công cụ quan trọng để quan sát và tương tác với máy ảo khi đường quản trị thông thường không hoạt động. Boot Diagnostics thu thập **ảnh màn hình máy ảo** và **log đầu ra cổng serial**; Serial Console cung cấp một phiên giao diện dòng lệnh qua cổng serial của VM, không đòi hỏi SSH/RDP hoạt động. Kết hợp chúng với thông tin trạng thái VM, snapshot/backup và quy trình sửa chữa offline giúp bạn tìm đúng nguyên nhân thay vì khắc phục bằng phỏng đoán.

Bài học thuộc chương **Máy ảo Azure** của module **CLOUD_PROVIDERS_AZURE**. Module tìm hiểu Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; đồng thời thực hành triển khai, giám sát, bảo vệ và kiểm soát chi phí. Ở đây, trọng tâm là **chẩn đoán và khôi phục lỗi khởi động của Azure VM chạy Windows hoặc Linux**, trong khuôn khổ quyền hạn và bảo vệ dữ liệu được tổ chức phê duyệt.

Sau bài học, bạn có thể:

- Phân biệt lỗi **Azure control plane**, lỗi **guest OS boot** và lỗi **kết nối SSH/RDP**.
- Bật và đọc Boot Diagnostics với managed storage hoặc custom storage account.
- Hiểu điều kiện, quyền truy cập và giới hạn của Azure Serial Console.
- Dùng Serial Console để quan sát màn hình đăng nhập, Linux serial terminal hoặc Windows Special Administration Console (SAC).
- Nhận biết các lỗi phổ biến như kernel panic, GRUB/initramfs, lỗi filesystem, cấu hình mount, BCD và INACCESSIBLE_BOOT_DEVICE.
- Thiết kế phương án cứu hộ khi hệ điều hành không thể vào chế độ quản trị: snapshot, Azure VM repair và repair VM.
- Lập runbook khắc phục theo mức độ rủi ro, lưu bằng chứng, kiểm tra sau sửa và tránh phát sinh chi phí không cần thiết.

## 1. Xác định đúng lớp xảy ra sự cố

Một VM có nhiều lớp vận hành. "Không truy cập được" chưa nói lên lớp nào bị lỗi.

~~~text
Azure control plane
  VM resource, provisioning, power state, quota, host
             |
             v
Virtual hardware
  CPU, memory, virtual NIC, OS disk, firmware
             |
             v
Guest boot process
  Bootloader -> kernel -> initramfs/driver -> OS services
             |
             v
Guest networking and identity
  NIC config, firewall, SSH/RDP, user credentials
             |
             v
Application
  Web/API/database/service health
~~~

| Hiện tượng | Nhóm nguyên nhân có thể | Công cụ đầu tiên |
|---|---|---|
| VM resource báo provisioning failed | Deployment, extension, cấu hình tài nguyên hoặc lỗi nền tảng | Activity Log, deployment operations, instance view |
| VM Stopped/Deallocated | Máy không đang chạy, có thể do thao tác hoặc chính sách | VM Overview, Activity Log |
| VM Running nhưng Boot Diagnostics hiện GRUB/emergency mode | Bootloader, filesystem hoặc cấu hình guest OS | Boot Diagnostics, Serial Console |
| VM Running, ảnh hiển thị màn hình đăng nhập, SSH timeout | NSG, UDR, firewall, IP/DNS, sshd, routing | Network Watcher, Serial Console, guest logs |
| Windows hiển thị màn hình recovery/BSOD | BCD, driver, filesystem, update hoặc thiết bị khởi động | Boot screenshot, SAC nếu khả dụng, repair workflow |
| VM đăng nhập được nhưng website lỗi 502 | Ứng dụng/backend health, port listener, dịch vụ phụ thuộc | Application logs, systemd/Windows services, load balancer logs |

**Power state = Running** thường chỉ cho biết tài nguyên tính toán đang hoạt động, **không chứng minh hệ điều hành đã boot thành công**. Ngược lại, khi một extension báo lỗi provisioning, hệ điều hành vẫn có thể đang chạy; phải kiểm tra bằng bằng chứng độc lập.

### Ba câu hỏi đầu tiên

1. VM đang **Running** hay **Stopped/Deallocated**? Có thông báo lỗi quản lý tài nguyên không?
2. Boot Diagnostics cho thấy màn hình/log cuối cùng ở bước nào?
3. Nếu hệ điều hành có vẻ đã boot, đây là lỗi **network/authentication** hay lỗi **ứng dụng**?

Nếu chưa xác định được ba điều này, **chưa nên thay OS disk, reset toàn bộ mạng hoặc format filesystem**.

## 2. Boot Diagnostics là gì?

**Azure Boot Diagnostics** thu thập thông tin phục vụ chẩn đoán khởi động và tình trạng hiển thị của VM, đặc biệt hữu ích khi SSH/RDP không hoạt động.

Hai loại bằng chứng chính:

| Dữ liệu | Nội dung thường thấy | Dùng để làm gì? |
|---|---|---|
| **Screenshot** | Ảnh trạng thái màn hình VM từ lớp ảo hóa | Nhìn thấy bootloader, Windows recovery, login screen, lỗi khởi động hoặc màn hình trống |
| **Serial log** | Nội dung guest OS gửi ra cổng serial trong quá trình boot/hoạt động | Tìm kernel messages, lỗi khởi tạo dịch vụ, filesystem, mount và các bước boot |

Ảnh chụp là **một ảnh trạng thái**, không phải video ghi lại toàn bộ quá trình boot. Serial log chỉ hiển thị những thông điệp mà hệ điều hành/bootloader thực sự gửi tới serial port; nếu custom image không cấu hình console serial, log có thể thiếu hoặc rỗng dù máy có lỗi.

Boot Diagnostics **không yêu cầu Azure VM Agent trong guest OS hoạt động** để có thể thu được ảnh và các thông điệp serial phù hợp. Đây là lý do nó có giá trị khi VM chưa boot đủ xa để khởi chạy agent hoặc thực thi extension.

### Boot Diagnostics khác Azure Monitor thế nào?

| Dịch vụ/công cụ | Cấp quan sát | Khi nên dùng |
|---|---|---|
| Boot Diagnostics | Screenshot và serial output của VM | Xem tiến trình boot và màn hình khi mất SSH/RDP |
| Serial Console | Phiên tương tác qua cổng serial | Khắc phục cấu hình guest OS khi kết nối thông thường không khả dụng |
| Azure Monitor / VM Insights | Metrics, logs, guest telemetry khi được cấu hình | Xu hướng CPU/memory/disk, ứng dụng và cảnh báo |
| Azure Activity Log | Thao tác ở management plane | Xem ai đã restart, resize, đổi disk/network, cập nhật VM |
| Network Watcher | Đường mạng, next hop, security rules và kết nối | Khi guest có vẻ chạy nhưng lưu lượng mạng thất bại |
| Run Command / VM extensions | Thực thi mã/lệnh qua khả năng guest agent | Khi VM agent còn khỏe và tính năng hỗ trợ |

Đừng xem Boot Diagnostics là bản thay thế cho full system logs hoặc backup. Nó giúp **tìm nguyên nhân**; khả năng khôi phục phụ thuộc vào tình trạng đĩa, bản backup và quy trình sửa chữa.

## 3. Managed Boot Diagnostics và custom storage account

Khi tạo Azure VM bằng Portal, Boot Diagnostics thường được bật mặc định theo trải nghiệm hiện hành, với **managed storage account** được Azure quản lý. Nếu dùng automation/IaC, vẫn cần kiểm tra cấu hình thực sự của VM.

| Tùy chọn lưu dữ liệu chẩn đoán | Điểm mạnh | Điều cần lưu ý |
|---|---|---|
| **Managed boot diagnostics storage** | Đơn giản, không cần tự tạo storage account chỉ để lấy screenshot/serial log | Account do dịch vụ quản lý, không truy cập trực tiếp như account thông thường; có giới hạn retention/dung lượng của dịch vụ |
| **Custom storage account** | Có thể đáp ứng một số quy định vận hành cũ hoặc yêu cầu tổ chức cụ thể | Phải cấu hình account, region/subscription, quyền và storage firewall tương thích |

Với custom storage account, Microsoft yêu cầu storage account dùng cho Boot Diagnostics thuộc **cùng subscription và region** với VM theo mô hình được hỗ trợ. Việc bật storage firewall có thể khiến screenshot/log không hiển thị nếu truy cập của Azure platform hoặc người xem không được cấp quyền phù hợp.

Chọn managed mode cho phần lớn bài tập và tình huống tiêu chuẩn nếu được chính sách cho phép. Không tự tạo custom account chỉ vì thấy các ví dụ cũ đề cập storage URI; chi phí và độ phức tạp vận hành có thể tăng.

**Phân biệt:** Boot Diagnostics storage account **không phải OS disk** của VM và cũng không phải nơi lưu bản backup toàn máy.

### Các giới hạn cần nhớ

- Boot Diagnostics phải được bật trước hoặc trong lúc thu thập bằng chứng; bật sau khi sự cố xảy ra **không thể tái tạo mọi log/screenshot đã không được ghi trước đó**.
- Ảnh hoặc log có thể cập nhật trễ; một ảnh cũ không nên được xem là tình trạng ngay lúc bạn mở Portal.
- Managed boot diagnostics có giới hạn lưu trữ/log theo tài liệu dịch vụ; không coi đây là archive không giới hạn.
- Khả năng dùng custom storage, account type, firewall và các điều kiện hỗ trợ khác phải được kiểm tra theo tài liệu Azure hiện hành.
- Log serial có thể chứa nội dung nhạy cảm do hệ điều hành hoặc người vận hành in ra; phải phân quyền truy cập và lưu giữ đúng chính sách.

## 4. Bật Boot Diagnostics trong Azure Portal

### Với một VM mới

1. Mở [Azure Portal](https://portal.azure.com), chọn subscription và resource group.
2. Tạo VM theo cấu hình được phê duyệt.
3. Tại tab **Management**, tìm mục **Boot diagnostics**.
4. Bật Boot Diagnostics và chọn **managed storage account** nếu phù hợp.
5. Xem lại các cấu hình VM, sau đó tạo tài nguyên.
6. Sau khi VM khởi động, kiểm tra Boot Diagnostics có ảnh và serial log phù hợp.

### Với VM đã tồn tại

1. Mở VM cần kiểm tra trong Azure Portal.
2. Vào phần **Help** hoặc **Support + troubleshooting** → **Boot diagnostics**.
3. Nếu chưa bật, mở **Settings**.
4. Chọn bật Boot Diagnostics, ưu tiên managed storage nếu phù hợp.
5. Lưu và kiểm tra kết quả trên **Screenshot** / **Serial log**.

Tên nhóm menu có thể thay đổi theo phiên bản Portal. **Không chuyển sang custom storage account trong lúc sự cố nếu không cần thiết**, vì quyền/storage firewall có thể làm chậm quá trình chẩn đoán.

### Xác nhận trước khi xử lý

- Đúng subscription, resource group, tên VM và region?
- Boot Diagnostics đang Enabled?
- Có screenshot và serial output mới không?
- Có dấu hiệu lỗi xuất hiện trước hay sau một lần restart/update?
- Có bản ghi hoạt động hoặc thay đổi cấu hình gần thời điểm sự cố?

Chụp lại timestamp, mã lỗi và những dòng log liên quan cho hồ sơ sự cố. Che thông tin nhận dạng hoặc dữ liệu nhạy cảm trước khi chia sẻ ra ngoài nhóm có quyền.

## 5. Bật và đọc Boot Diagnostics bằng Azure CLI

Các lệnh dưới đây dùng **Azure CLI** và chỉ nhắm tới VM mà bạn được phép quản trị. Trong phần thực hành, nên dùng VM lab, không thao tác trên VM production chưa được phê duyệt.

Đăng nhập và chọn subscription:

~~~bash
az login
az account list --output table
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table
~~~

Khai báo thông tin VM:

~~~bash
RG="rg-vm-lab"
VM="vm-boot-lab"
~~~

Kiểm tra trạng thái VM trước khi sửa:

~~~bash
az vm get-instance-view \
  --resource-group "$RG" \
  --name "$VM" \
  --output json
~~~

Để bật **managed Boot Diagnostics** trên VM hiện có, không truyền tham số storage URI:

~~~bash
az vm boot-diagnostics enable \
  --resource-group "$RG" \
  --name "$VM"
~~~

Lấy serial boot log khi dữ liệu đã có:

~~~bash
az vm boot-diagnostics get-boot-log \
  --resource-group "$RG" \
  --name "$VM"
~~~

Tham khảo **az vm boot-diagnostics get-boot-log-uris** khi cần lấy liên kết do dịch vụ tạo theo quyền và điều kiện hỗ trợ. Những URI tạm thời có thể chứa SAS/token ủy quyền: **không đưa chúng vào ticket, log hay repository công khai**.

Một ví dụ kiểm tra cấu hình Boot Diagnostics trong VM resource:

~~~bash
az vm show \
  --resource-group "$RG" \
  --name "$VM" \
  --query "{vm:name,bootDiagnostics:diagnosticsProfile.bootDiagnostics}" \
  --output json
~~~

**Lưu ý:** dữ liệu trong cấu hình resource không chứng minh VM đã khởi động được. Cần kết hợp **instance view**, screenshot, serial log và kiểm tra ứng dụng. Nếu CLI báo không đủ quyền, không tự dùng account key hoặc bỏ chính sách tổ chức để xem dữ liệu.

## 6. Đọc ảnh và serial log: cách suy luận

Giả sử bạn mở Boot Diagnostics và thấy một trong những trạng thái:

| Dấu hiệu | Giả thuyết ban đầu | Bước tiếp theo |
|---|---|---|
| Linux hiện GRUB menu hoặc GRUB rescue prompt | Vấn đề bootloader, filesystem hoặc cấu hình khởi động | Thu log, kiểm tra disk, dùng Serial Console/repair theo hướng dẫn |
| Linux báo kernel panic | Kernel/driver/initramfs, root filesystem, lỗi hệ thống | Ghi đúng chuỗi lỗi, xác nhận bản kernel/update |
| Linux vào emergency mode | Mount thất bại, fstab sai, filesystem hoặc phụ thuộc boot | Serial Console, kiểm tra mount và systemd logs |
| Linux hiện login prompt | Boot có thể đã hoàn tất đến chế độ đăng nhập | Điều tra SSH, mạng, auth và ứng dụng |
| Windows hiện Automatic Repair/Recovery | BCD, Windows update, driver hoặc lỗi boot | Thu mã lỗi, xem SAC/repair VM |
| Windows báo INACCESSIBLE_BOOT_DEVICE | Không truy cập được thiết bị/partition OS trong giai đoạn khởi động | Đánh giá driver, BCD, partition, disk attachment |
| Windows hiện màn hình login | OS có thể đã boot; RDP chưa chắc mở | Network Watcher, NSG, firewall, RDP services |
| Screenshot đen và serial log rỗng | Boot rất sớm, guest chưa xuất serial, hình ảnh cũ hoặc cấu hình Boot Diagnostics có vấn đề | Kiểm tra trạng thái VM, nguồn log, cấu hình serial và thời điểm |

**Một ảnh chụp không đủ chẩn đoán nguyên nhân gốc.** Luôn đối chiếu **dòng lỗi cụ thể, thời điểm thay đổi và dữ liệu từ những lớp khác**.

### Ví dụ đọc serial log Linux

~~~text
[  OK  ] Started Network Manager.
[FAILED] Failed to mount /data.
You are in emergency mode.
~~~

Đây là ví dụ minh họa. Nếu lỗi xuất hiện sau khi sửa **/etc/fstab**, giả thuyết đầu tiên nên là UUID, đường dẫn thiết bị hoặc tùy chọn mount không hợp lệ. Đừng kết luận rằng Azure mất ổ đĩa trước khi kiểm tra cấu hình và trạng thái managed disk.

### Ví dụ màn hình Windows

~~~text
Recovery
Your PC/Device needs to be repaired
Error code: 0xc000000f
~~~

Mã lỗi chỉ là **đầu mối**: nó có thể liên quan BCD/boot files hoặc những tình huống khác. Cần kiểm tra VM generation, cấu trúc phân vùng và tình trạng disk trước khi áp dụng lệnh sửa BCD.

## 7. Azure Serial Console: truy cập khi SSH/RDP không hoạt động

**Azure Serial Console** mở giao diện terminal dạng text tới cổng serial của VM thông qua dịch vụ Azure. Kết nối này **không cần SSH/RDP hoặc IP public hoạt động** và không phụ thuộc trực tiếp vào NSG mở cổng 22/3389. Nó đặc biệt hữu ích khi một thay đổi firewall trong guest hoặc cấu hình mạng làm bạn mất đường quản trị.

~~~text
Người vận hành có quyền Azure
       |
       | Azure Portal / serial-console service
       v
  Azure Serial Console
       |
       | Cổng serial ảo của VM
       v
Linux: ttyS0/getty/bootloader
Windows: EMS / SAC nếu image đã cấu hình
~~~

Serial Console **không phải một shell quản trị tự động có sẵn mọi lúc**. Nó yêu cầu VM ở trạng thái phù hợp, tính năng được hỗ trợ và guest OS có cấu hình serial console. Nếu guest bị treo rất sớm hoặc không xuất console ra serial, bạn có thể thấy màn hình trống.

### Điều kiện thường cần có

- VM chạy mô hình **Azure Resource Manager**, có trạng thái cho phép kết nối; VM đã **deallocated** không thể cung cấp phiên serial đang chạy.
- Boot Diagnostics được bật theo điều kiện dịch vụ.
- Tài khoản Azure có **quyền quản trị VM/Serial Console phù hợp**; tài liệu Microsoft thường yêu cầu quyền cấp **Virtual Machine Contributor** hoặc tương đương, đồng thời xét quyền đến boot diagnostics storage khi dùng cấu hình liên quan.
- Azure subscription/VM không bị chính sách tắt Serial Console; trình duyệt/mạng của người vận hành truy cập được dịch vụ Serial Console.
- Linux custom image cần cấu hình serial output và **getty** trên **ttyS0**; Windows cần **Emergency Management Services/Special Administration Console (EMS/SAC)** được hỗ trợ.
- Muốn đăng nhập trong guest phải có **tài khoản và phương thức xác thực guest OS hợp lệ**. Quyền Azure không thay thế mật khẩu hệ điều hành.

Chi tiết quyền/storage connectivity của Serial Console có thể thay đổi theo quá trình phát triển dịch vụ, đặc biệt với managed/custom boot diagnostics storage; khi gặp lỗi truy cập cần đối chiếu tài liệu chính thức và thông điệp thực tế.

**Bảo mật:** Serial Console có thể cho quyền khắc phục sâu trong guest OS, vì vậy phải giới hạn RBAC, ghi audit và dùng quy trình break-glass. Không chạy lệnh chứa secret hoặc in token ra console vì nội dung có thể xuất hiện trong nhật ký serial.

## 8. Mở Serial Console từ Portal và CLI

### Trong Azure Portal

1. Đăng nhập Portal bằng danh tính được phân quyền vận hành VM.
2. Mở đúng VM và xác nhận **Running**.
3. Đảm bảo Boot Diagnostics đang Enabled.
4. Chọn **Serial console** trong nhóm Help/Support + troubleshooting của VM.
5. Chờ mở kết nối; với Linux có thể cần nhấn **Enter** để hiện login prompt.
6. Nếu guest OS hỗ trợ, đăng nhập bằng tài khoản hợp lệ rồi chỉ thực hiện các bước chẩn đoán đã phê duyệt.

Với **Virtual Machine Scale Sets**, bạn thường phải chọn **instance cụ thể** thay vì chỉ màn hình nhóm scale set; cấu hình model/instance cần đáp ứng điều kiện tính năng.

### Azure CLI (tùy chọn)

Azure CLI có extension **serial-console**, với lệnh kết nối:

~~~bash
az serial-console connect \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<VM_NAME>"
~~~

Lệnh này mở phiên tương tác, không phải lệnh đọc log đơn thuần. Hãy xem **az serial-console connect --help** cho phiên bản CLI/extension đang dùng. Trong tình huống sự cố và mạng văn phòng chặn WebSocket, Portal/CLI có thể gặp lỗi truy cập dịch vụ dù VM vẫn chạy.

**Không sử dụng lệnh gửi reset/NMI/SysRq** chỉ để thử kết nối; các tín hiệu đó có thể gây gián đoạn, làm mất dữ liệu chưa ghi hoặc thay đổi trạng thái guest OS. Mọi thao tác khởi động lại nên có mục tiêu và phê duyệt rõ ràng.

## 9. Serial Console trên Linux: ttyS0 và dấu hiệu boot

Trên Linux, Azure Serial Console thường kết nối đến **ttyS0**. Nhiều Linux image được Azure hỗ trợ đã cấu hình serial console; với custom image, bạn cần chuẩn bị:

- Kernel/bootloader gửi thông điệp ra serial console khi phù hợp.
- Login prompt có thể xuất hiện nhờ dịch vụ **serial-getty@ttyS0** hoặc cơ chế tương đương của bản phân phối.
- Tài khoản guest có phương thức xác thực được cho phép để truy cập ở serial terminal.
- Chính sách mật khẩu, PAM, sudo và audit được áp dụng theo tiêu chuẩn tổ chức.

Khi đã đăng nhập vào Linux qua Serial Console, một số lệnh **đọc trạng thái** tương đối an toàn:

~~~bash
uname -a
cat /etc/os-release
systemctl --failed
systemctl status ssh --no-pager
journalctl -b -p err --no-pager
lsblk -f
findmnt -a
df -h
~~~

Không nhất thiết mọi lệnh đều khả dụng khi VM ở rescue/emergency mode. Một số bản phân phối dùng tên dịch vụ SSH là **sshd** thay vì **ssh**, và khi hệ thống boot chưa hoàn tất, journal có thể chưa ghi đầy đủ.

### Chẩn đoán lỗi /etc/fstab

**/etc/fstab** định nghĩa những filesystem cần mount trong quá trình boot. Sai UUID, mount một disk đã bị tháo hoặc đặt tham số bắt buộc không phù hợp có thể đưa Linux vào **emergency mode**.

Các lệnh chỉ đọc để so sánh:

~~~bash
cat /etc/fstab
lsblk -f
blkid
findmnt -a
systemctl --failed
~~~

Đối chiếu UUID và thiết bị thực tế trước khi sửa. **Không format, chạy mkfs hoặc xóa partition** vì chưa thấy mount point; những lệnh đó có thể phá hủy dữ liệu.

Nếu một data disk phụ là tùy chọn, có thể đánh giá **nofail** hoặc cấu hình mount phù hợp, nhưng chỉ chỉnh khi hiểu hệ quả: ứng dụng nào cần disk, có được phép khởi chạy khi thiếu disk không, và cơ chế giám sát lỗi ra sao.

### Chẩn đoán root filesystem đầy

Disk đầy có thể khiến ứng dụng, logging hoặc một số bước startup không hoàn tất:

~~~bash
df -h
df -i
du -sh /var/log /var/cache 2>/dev/null
journalctl --disk-usage
~~~

Trước khi xóa file, xác định **file đó có phải dữ liệu nghiệp vụ, transaction log hay bằng chứng điều tra không**. Không xóa bừa toàn bộ **/var/log**, journal hoặc database files; cần backup, retention và phương án xử lý có kiểm soát.

### GRUB, initramfs và kernel panic

Các lỗi rất sớm có thể liên quan:

- **GRUB/bootloader:** thay đổi cấu hình menu hoặc không tìm thấy file boot.
- **initramfs:** thiếu driver/metadata cần để mount root filesystem.
- **Kernel panic:** lỗi kernel, driver hoặc root filesystem khiến hệ điều hành không tiếp tục.
- **Filesystem corruption:** sau tắt máy không an toàn, lỗi storage/partition hoặc cập nhật.
- **Kernel/OS update:** một bản cập nhật chưa tương thích image/driver hoặc VM generation.

Boot Diagnostics giúp chụp lại dòng lỗi, Serial Console có thể cho phép tương tác bootloader khi image hỗ trợ. **Không làm theo các lệnh sửa GRUB/dracut/fsck được tìm thấy ngẫu nhiên trên Internet** trước khi xác định distro, version, disk layout, UEFI/BIOS và đã tạo bản sao an toàn.

## 10. Serial Console trên Windows: EMS và SAC

Với Windows, Azure Serial Console có thể cung cấp **Special Administration Console (SAC)** khi **Emergency Management Services (EMS)** được cấu hình. Nhiều Windows Server image được Azure hỗ trợ đã bật sẵn; custom image hoặc image cũ có thể cần thiết lập trước.

SAC là công cụ **quản trị văn bản** trong tình huống khẩn cấp, không phải RDP desktop. Tùy môi trường, SAC có thể hỗ trợ mở kênh lệnh và kiểm tra thông tin hệ thống khi bạn có thông tin đăng nhập guest hợp lệ.

| Trạng thái Windows | Cách tiếp cận |
|---|---|
| SAC prompt hiển thị | Xác thực người quản trị trong guest và kiểm tra dịch vụ, mạng, log theo quyền |
| Chỉ hiển thị thông tin sức khỏe, không có SAC prompt | Xác minh EMS/SAC có được bật trên image không |
| VM bị lỗi trước khi SAC hoạt động | Dùng screenshot, mã lỗi và quy trình repair offline |
| Windows boot được nhưng RDP lỗi | Kiểm tra RDP service, Windows Firewall, NSG/UDR, IP và credential |

Trong phiên command prompt được mở hợp lệ, các lệnh **kiểm tra** có thể gồm:

~~~powershell
hostname
whoami
ipconfig /all
sc.exe query TermService
bcdedit /enum all
wevtutil qe System /c:20 /rd:true /f:text
~~~

Các lệnh trên chỉ mang tính gợi ý và phụ thuộc quyền, phiên Windows, chế độ console. **Không tự chạy bcdedit /set, bcdboot, bootrec hoặc lệnh làm thay đổi phân vùng** nếu chưa có chẩn đoán riêng cho Gen1/Gen2, BIOS/UEFI và đường dẫn BCD chính xác.

### Windows boot error phổ biến

| Dấu hiệu | Hướng điều tra |
|---|---|
| **INACCESSIBLE_BOOT_DEVICE** | Disk boot, driver storage, cấu hình OS, thay đổi image hoặc partition |
| **0xc000000f / 0xc000000e** | Boot configuration, đường dẫn thiết bị hoặc boot files |
| **Automatic Repair loop** | Update, driver, BCD, system files hoặc filesystem |
| **Windows Update rollback liên tục** | Update history, servicing logs và trạng thái recovery |
| **Login screen nhưng RDP timeout** | Network, firewall, listener TermService, NSG, route, DNS |

Không suy diễn một mã lỗi luôn tương ứng một cách sửa. Ví dụ cùng mã 0xc000000f có thể cần các bước khác nhau giữa VM Generation 1 và Generation 2. Microsoft có runbook riêng cho từng nhóm boot failure và loại VM.

## 11. Phân biệt lỗi khởi động với lỗi kết nối mạng

Một sai lầm phổ biến là **VM không SSH/RDP được ⇒ VM không boot được**. Hai vấn đề này khác nhau.

### Khi ảnh cho thấy màn hình đăng nhập

Nếu Boot Diagnostics hiển thị login prompt của Linux hoặc Windows, khả năng OS đã khởi động đến bước đăng nhập là cao. Tiếp tục kiểm tra:

1. NIC có gắn đúng subnet, IP và route không?
2. VM có public IP hoặc kênh truy cập nội bộ phù hợp không? Không phải VM nào cũng cần public IP.
3. NSG có cho phép luồng quản trị từ nguồn đã phê duyệt không?
4. Có user-defined route đưa traffic sai đường không? Network Watcher **Next hop** hoặc connection troubleshoot có thể giúp.
5. Guest firewall có chặn cổng 22/3389 không?
6. sshd/TermService có đang chạy và lắng nghe đúng địa chỉ không?
7. Xác thực SSH key, mật khẩu hoặc quyền đăng nhập có đúng không?

**Không mở SSH/RDP cho toàn Internet chỉ để thử.** Dùng Azure Bastion, VPN, private network và các nguồn quản trị được phê duyệt nếu phù hợp. Serial Console có thể giúp kiểm tra guest firewall mà không nới NSG.

### Azure VM Agent, Run Command và extensions

**Run Command** và nhiều **VM extensions** phụ thuộc VM agent/dịch vụ guest đủ khỏe. Nếu kernel chưa chạy, root filesystem chưa mount hoặc agent hỏng, các công cụ này có thể không đáp ứng. Khi đó Boot Diagnostics và Serial Console vẫn là tuyến quan sát phù hợp hơn.

Nếu Run Command hoạt động, đây là tín hiệu guest OS đã chạy đủ để thực thi agent; không nên tiếp tục xử lý như lỗi bootloader mà không có bằng chứng khác.

## 12. Quy trình khắc phục theo mức độ rủi ro

Không phải mọi sự cố đều cần offline repair. Một runbook tốt bắt đầu bằng **read-only diagnosis**:

~~~mermaid
flowchart TD
    A[VM không truy cập được] --> B{VM đang Running?}
    B -- Không --> C[Kiểm tra power state, Activity Log, provisioning]
    B -- Có --> D[Đọc Boot Diagnostics screenshot và serial log]
    D --> E{OS đã tới login hoặc service state?}
    E -- Có --> F[Kiểm tra mạng, SSH/RDP, auth và dịch vụ]
    E -- Không --> G{Serial Console có hoạt động?}
    G -- Có --> H[Thu thập log, kiểm tra guest và sửa hẹp]
    G -- Không --> I[Đánh giá repair workflow và bản sao disk]
    H --> J[Smoke test, quan sát và ghi RCA]
    I --> J
    F --> J
    C --> J
~~~

### Các mức can thiệp

| Mức | Hành động | Độ rủi ro tương đối |
|---|---|---|
| 1 | Đọc VM instance view, Activity Log, Boot Diagnostics | Thấp, chủ yếu quan sát |
| 2 | Đọc Serial Console và log guest, kiểm tra quyền/network | Thấp đến vừa, nếu chỉ đọc |
| 3 | Sửa một cấu hình guest có bằng chứng, ghi lại diff | Vừa, cần backup/rollback |
| 4 | Restart VM, thay đổi boot settings hoặc OS service | Vừa đến cao, có downtime |
| 5 | Repair OS disk offline, swap OS disk, sửa BCD/GRUB/filesystem | Cao, cần snapshot, phê duyệt và runbook chính xác |
| 6 | Restore VM/disk từ backup, failover sang bản dự phòng | Cao, phụ thuộc RPO/RTO và dữ liệu |

Mỗi thao tác cần xác định **đối tượng, dự kiến thay đổi, điều kiện thành công, rủi ro dữ liệu và phương án quay lại**. Với production, ghi timeline và thời điểm phê duyệt trước khi can thiệp.

## 13. Khi nào cần repair VM và sửa OS disk offline?

Nếu guest không thể vào phiên quản trị dù có Serial Console, hoặc lỗi nằm trên cấu hình/partition hệ điều hành, có thể cần **offline repair**:

1. Xác nhận nguyên nhân và cách repair phù hợp với **Windows/Linux**, VM generation và loại disk.
2. Tạo **snapshot/backup hoặc bản sao an toàn** của OS disk trước thao tác thay đổi dữ liệu; xác nhận quyền và chính sách lưu giữ.
3. Dùng công cụ **Azure VM repair** được Microsoft hướng dẫn hoặc tạo repair VM có hệ điều hành phù hợp.
4. Gắn **bản sao OS disk bị lỗi** vào repair VM theo quy trình an toàn. Không format đĩa.
5. Kiểm tra partition, filesystem, boot configuration và logs khi disk được mount theo đúng chế độ.
6. Chỉ thực hiện sửa chữa đã xác định, ghi lại bước và kết quả.
7. Hoàn tất quy trình **restore/rebuild/swap** theo công cụ đã dùng.
8. Khởi động lại VM gốc, đọc Boot Diagnostics mới và chạy smoke tests.
9. Xác minh dữ liệu và dọn tài nguyên repair sau khi được phê duyệt.

### Azure VM repair commands

Microsoft cung cấp workflow **az vm repair** qua Azure CLI extension phù hợp để hỗ trợ các tình huống sửa VM Windows/Linux. Công cụ có thể tạo một **repair VM**, gắn bản sao disk hoặc điều phối quy trình repair rồi hỗ trợ khôi phục VM. Tính năng và tham số khác nhau theo hệ điều hành, mô hình triển khai và loại mã hóa.

**Không có một câu lệnh repair chung an toàn cho mọi lỗi boot.** Trước khi chạy, hãy mở hướng dẫn chính thức tương ứng với hệ điều hành và kiểm tra **az vm repair --help**; xác nhận backup, quyền, chi phí, thời gian dừng máy và phương án rollback.

### Các cảnh báo quan trọng khi sửa offline

- **Disk identity:** phân biệt disk gốc, snapshot, bản sao và disk dữ liệu của repair VM. Nhầm đĩa có thể phá hủy dữ liệu.
- **Encryption:** nếu OS disk dùng Azure Disk Encryption, BitLocker, customer-managed key hoặc cơ chế riêng, việc mount/repair phải theo hướng dẫn hỗ trợ; không tự tắt mã hóa.
- **VM generation:** khác biệt giữa BIOS/MBR (Gen1) và UEFI/GPT (Gen2) ảnh hưởng sửa bootloader/BCD.
- **Multi-disk workload:** sửa OS disk chưa chắc phục hồi một database nằm trên data disk.
- **Repair VM locality:** xác nhận region/zone, SKU, quyền và đường mạng hỗ trợ; storage/copy/VM có thể phát sinh phí.
- **Recovery point:** snapshot không tự bảo đảm application-consistency, và restore có thể làm mất thay đổi sau điểm phục hồi.

Không xóa OS disk hoặc VM gốc để tạo chỗ cho repair khi chưa có đường quay lại được xác minh.

## 14. Linux: phân tích theo nhóm sự cố boot

### Tình huống A — sai /etc/fstab sau khi thêm data disk

**Bối cảnh:** quản trị viên thêm một dòng mount dựa trên **/dev/sdc** và khởi động lại. Linux vào emergency mode vì tên thiết bị thay đổi hoặc disk không tồn tại.

**Cách tiếp cận:**

1. Đọc screenshot và serial log, xác định chính xác mount unit thất bại.
2. Vào Serial Console nếu có login, hoặc dùng repair VM khi root filesystem không vào được.
3. So sánh **/etc/fstab**, **lsblk -f**, UUID và partition.
4. Sửa **đúng dòng sai** trên bản có backup; cân nhắc UUID thay cho tên thiết bị dễ đổi.
5. Kiểm tra cấu hình filesystem/mount, sau đó reboot theo quy trình.
6. Xác nhận dữ liệu và các ứng dụng phụ thuộc mount point hoạt động.

**Không dùng mkfs** để "sửa lỗi không mount" khi chưa biết disk có dữ liệu gì.

### Tình huống B — kernel update gây panic

**Bối cảnh:** bản kernel mới được cài trước thời điểm lỗi; console có thông điệp không mount được root hoặc kernel panic.

**Cách tiếp cận:**

- Lưu lại version kernel cuối cùng boot thành công và thông điệp hiện tại.
- Xem khả năng chọn kernel trước đó từ bootloader nếu distro và cấu hình cho phép.
- Nếu bootloader/console không truy cập được, dùng offline repair theo hướng dẫn distro/Azure.
- Kiểm tra initramfs, driver và filesystem, sau đó chỉ sửa khi có backup và đường rollback.

Một kernel cũ boot được là **bằng chứng hữu ích**, không có nghĩa nguyên nhân gốc đã được xử lý hoàn toàn. Cần xem lại pipeline cập nhật và tính tương thích image.

### Tình huống C — root filesystem đầy

**Bối cảnh:** sau một đợt log tăng mạnh, SSH không phản hồi và một số systemd services khởi động lỗi.

**Cách tiếp cận:**

- Xem df/du/journal ở Serial Console hoặc recovery mode.
- Xác định file có thể dọn theo chính sách, không xóa transaction logs/bản dữ liệu duy nhất.
- Xem lý do tăng log, cấu hình rotation/retention và disk capacity.
- Khởi động lại dịch vụ hoặc máy khi cần, sau đó theo dõi utilization.

### Tình huống D — cấu hình network làm mất SSH

**Bối cảnh:** VM boot xong, nhưng sửa network config/firewall khiến SSH timeout.

**Cách tiếp cận:** ảnh Boot Diagnostics có login prompt; vào Serial Console, xem network interface, route, firewall và sshd. Đây là **lỗi connectivity**, không cần sửa bootloader hay swap OS disk.

## 15. Windows: phân tích theo nhóm sự cố boot

### Tình huống A — lỗi BCD/Windows Boot Manager

**Bối cảnh:** Boot Diagnostics screenshot cho thấy mã 0xc000000f, 0xc000000e hoặc thông báo không tìm thấy OS.

**Cách tiếp cận:**

1. Ghi mã lỗi và thay đổi gần đây: swap disk, resize, Windows update, driver, image capture.
2. Kiểm tra OS disk/resource và generation của VM.
3. Xem Microsoft runbook cho đúng loại lỗi và cấu hình UEFI/BIOS.
4. Nếu cần repair offline, snapshot rồi gắn bản sao OS disk vào repair VM theo hướng dẫn.
5. Chỉ sửa BCD/partition khi xác định đúng đường dẫn boot files; kiểm thử sau khi hoàn trả.

### Tình huống B — INACCESSIBLE_BOOT_DEVICE

Đây là lỗi hệ điều hành không truy cập được thiết bị khởi động theo điều kiện hiện tại. Điều tra disk attachment, driver storage, đổi VM image/generation và thay đổi gần đây. **Không format hoặc tạo lại phân vùng** chỉ vì hệ điều hành không tìm thấy boot device.

### Tình huống C — Windows Update hoặc driver gây vòng lặp recovery

Sau khi update, VM liên tục vào Automatic Repair. Thu màn hình lỗi, xác nhận bản update/driver và đánh giá các tùy chọn recovery của Windows hoặc offline repair. Nếu có Azure Backup application-consistent phù hợp, xem xét restore theo mục tiêu RPO/RTO. Không ngắt máy nhiều lần như cách "thử vận may".

### Tình huống D — Windows login được nhưng RDP không được

Kiểm tra TermService/Windows Firewall, NSG, Bastion/VPN, IP route và credential. Nếu SAC dùng được, có thể quan sát dịch vụ/mạng mà không phải mở 3389 ra Internet. Không thực hiện các lệnh tắt toàn bộ Windows Firewall trong production để thử.

## 16. Boot Diagnostics, Serial Console và bảo mật vận hành

Hai công cụ chứa thông tin hệ thống nhạy cảm hơn nhiều người nghĩ:

- Screenshot có thể cho thấy username, tên máy, lỗi chứa đường dẫn nội bộ hoặc một phần thông tin vận hành.
- Serial log có thể gồm kernel arguments, đường dẫn file, thông báo ứng dụng, output lệnh, dữ liệu nhạy cảm bị in nhầm.
- Người dùng có quyền mở Serial Console có thể thao tác như người đang đứng tại terminal hệ điều hành khi có guest credentials phù hợp.
- Nếu một phiên Serial Console bị người khác tiếp quản, trạng thái đăng nhập tương tác cần được quản trị theo chính sách session.

**Quy tắc an toàn:**

1. Chỉ cấp Azure RBAC tối thiểu cho nhóm vận hành VM.
2. Yêu cầu guest OS authentication theo chính sách; không chia sẻ một mật khẩu root/Administrator dài hạn.
3. Dùng tài khoản break-glass có vòng đời, kiểm soát và audit phù hợp.
4. Không nhập secret vào câu lệnh có thể xuất hiện trong serial log.
5. Không lưu ảnh/log trong kho chia sẻ công khai; làm mờ thông tin nhạy cảm khi gửi ticket.
6. Kiểm tra Storage permissions/firewall nếu dùng custom boot diagnostics storage.
7. Ghi lại ai đã dùng Serial Console, lúc nào, thao tác gì và vì sao.

### Mạng công ty có thể chặn Serial Console

Nếu Portal báo lỗi **WebSocket connection** hoặc phiên mở rồi đóng, trước hết xác định lỗi nằm ở dịch vụ truy cập từ trình duyệt hay VM. Một số môi trường cần cho phép hostname dịch vụ Serial Console hiện hành, chẳng hạn **\*.serialconsole.azure.com**, theo hướng dẫn Microsoft và chính sách mạng công ty. Đừng lập tức thay NSG của VM vì traffic Serial Console không phải phiên RDP/SSH truyền thống.

## 17. Chi phí và giới hạn vận hành

Boot Diagnostics với managed storage cung cấp trải nghiệm đơn giản, nhưng tổng chi phí khắc phục còn đến từ những tài nguyên khác:

| Tài nguyên/thao tác | Rủi ro chi phí |
|---|---|
| VM chính | Tiếp tục tính phí compute khi được cấp phát và đang chạy, theo mô hình SKU |
| Custom boot diagnostics storage | Storage, request và các chi phí liên quan theo cấu hình |
| Snapshot/copy OS disk | Lưu trữ snapshot/bản sao còn tồn tại |
| Repair VM | Compute, OS disk, network, public IP và disk tạm theo cấu hình |
| Backup/restore | Retention, backup storage và các dịch vụ liên quan |
| Logging/monitoring | Log ingestion, retention và analytics khi được bật |

Một VM **Stopped (Deallocated)** thường ngừng tính phí compute theo các quy tắc dịch vụ, nhưng **managed disks, public IP và tài nguyên khác vẫn có thể phát sinh phí**. Trong sự cố, không nên deallocate VM chỉ vì muốn tiết kiệm nếu điều đó cản trở thu bằng chứng hoặc phục hồi.

Sau repair, kiểm tra repair VM, snapshots, cloned disks, NIC/public IP và các tài nguyên phục vụ thử nghiệm. **Không xóa bản backup/bản sao cho đến khi khôi phục đã được xác nhận**.

## 18. Tình huống thực tế: VM Linux mất SSH sau cập nhật

Một VM Linux phục vụ API trong subnet private. Sau đợt update lúc 01:00, hệ thống cảnh báo SSH timeout. Azure Portal hiển thị VM **Running**.

### Bước 1 — Khoanh vùng

- Kiểm tra Activity Log: có restart VM, đổi disk, sửa NSG hay deployment không?
- Kiểm tra Boot Diagnostics: screenshot có login prompt hay emergency mode?
- Đọc serial log: có kernel panic, systemd failed units hoặc mount failed không?

Giả sử serial log có:

~~~text
Dependency failed for /data.
Failed to mount /data.
You are in emergency mode.
~~~

Từ đây, giả thuyết mạnh là sự cố mount data disk, **không phải NSG**.

### Bước 2 — Thu thập và kiểm tra

Nếu Serial Console cho phép đăng nhập:

~~~bash
lsblk -f
cat /etc/fstab
systemctl --failed
journalctl -b -p err --no-pager
~~~

Đối chiếu một dòng mount dùng sai UUID với UUID thực tế. Nếu disk đã bị tháo ở Azure, kiểm tra cả cấu hình VM/Data Disks. Tạo bản sao an toàn trước khi sửa cấu hình quan trọng.

### Bước 3 — Sửa hẹp và thử lại

Thay vì tạo disk mới hay format, người vận hành chỉnh đúng tham chiếu mount theo runbook, kiểm tra quyền/dữ liệu, rồi khởi động lại. Sau đó xác minh:

- Boot Diagnostics có login prompt và serial log không còn lỗi mount.
- SSH qua kênh private/Bastion được phép đã hoạt động.
- Volume **/data** đúng UUID và chứa dữ liệu mong đợi.
- API trả kết quả và kết nối database bình thường.
- Monitoring, backup và cấu hình mount đã ổn định.

### Bước 4 — Phòng ngừa

Trong thay đổi sau này, sử dụng UUID/mount option được phê duyệt, kiểm thử reboot trên staging và thêm synthetic health check phù hợp. Ghi root-cause analysis (RCA) về cấu hình mount thay vì chỉ ghi "VM đã restart thành công".

## 19. Tình huống thực tế: Windows VM vào Recovery

Một Windows Server VM lưu dữ liệu nghiệp vụ trên data disk. Sau một bản cập nhật, Portal hiển thị Running nhưng RDP timeout; Boot screenshot hiện **Recovery** với mã lỗi liên quan boot configuration.

**Runbook đề xuất:**

1. Ghi nhận lỗi, trạng thái OS disk và thay đổi gần nhất; không nhấn restart nhiều lần.
2. Kiểm tra Serial Console/SAC nếu VM/image hỗ trợ. Nếu Windows chưa boot tới SAC, không coi Serial Console trống là lỗi dịch vụ Azure.
3. Xác nhận có backup/snapshot và thông tin VM Generation, OS disk encryption.
4. Đánh giá đúng bài hướng dẫn Microsoft cho mã lỗi; chuẩn bị repair VM và disk copy khi cần.
5. Thực hiện sửa BCD/boot files **trên bản phù hợp và theo runbook đã phê duyệt**.
6. Đưa OS disk đã repair trở lại theo quy trình, khởi động VM.
7. Kiểm tra Boot Diagnostics, Windows services, RDP qua đường an toàn và quyền truy cập data disk.
8. Xác minh dữ liệu nghiệp vụ, event logs và khả năng backup tiếp tục hoạt động.

Nếu OS disk không thể phục hồi tin cậy, xem xét restore từ Azure Backup hoặc dựng lại VM bằng image chuẩn và gắn/khôi phục dữ liệu theo chính sách. Quyết định phụ thuộc RPO/RTO và dữ liệu chưa backup, không chỉ mức nhanh của thao tác tạo VM mới.

## 20. Bài thực hành an toàn: quan sát một VM lab

**Mục tiêu:** biết bật Boot Diagnostics, đọc screenshot/log, so sánh Serial Console với SSH/RDP và lập phương án xử lý khi boot lỗi, **không cần cố ý làm hỏng VM**.

### Chuẩn bị

- Một Azure VM lab Linux hoặc Windows được phép truy cập, không có dữ liệu quan trọng.
- Tài khoản có quyền xem Boot Diagnostics và quyền Serial Console nếu phần tương tác được thực hành.
- Được phê duyệt ngân sách, region/VM size và chi phí compute/disk/network.
- Không mở RDP/SSH ra Internet chỉ để thử truy cập Serial Console.

### Phần A — đọc trạng thái trước can thiệp

1. Xác định subscription, resource group, tên VM, OS image và power state.
2. Mở **Boot diagnostics** trên Portal.
3. Ghi lại timestamp, mô tả screenshot và thông báo quan trọng trong Serial log.
4. Chạy CLI read-only:

~~~bash
RG="<LAB_RESOURCE_GROUP>"
VM="<LAB_VM_NAME>"

az vm get-instance-view --resource-group "$RG" --name "$VM" --output json
az vm boot-diagnostics get-boot-log --resource-group "$RG" --name "$VM"
~~~

5. So sánh log với trạng thái guest khi bạn đăng nhập được bằng kênh bình thường.

Nếu Boot Diagnostics đang tắt, bạn có thể bật theo mục 4/5 **khi đã được phép**; ghi nhận đây là thao tác thay đổi cấu hình để không làm sai timeline sự cố.

### Phần B — xem Serial Console

1. Chọn Serial console trong Portal và xác minh phiên kết nối.
2. Nếu VM Linux hiện login prompt, đăng nhập bằng tài khoản lab và chạy **uname -a**, **lsblk -f**, **systemctl --failed**.
3. Nếu VM Windows có SAC được hỗ trợ, đọc thông tin ban đầu; chỉ mở command prompt khi đã có guest credentials và mục tiêu rõ ràng.
4. Ghi lại: Serial Console có cần IP public không? Có liên quan trực tiếp đến NSG 22/3389 không?
5. Đóng/log out phiên theo quy trình, không để lại shell đặc quyền mở.

Không cố gây kernel panic, phá **/etc/fstab**, xóa boot files hoặc gửi hard reset để "tạo lỗi lab". Phần thực hành dùng **bằng chứng và tình huống mô phỏng** để tránh rủi ro mất dữ liệu.

### Phần C — phân tích tình huống giả định

| Bằng chứng | Bạn cần trả lời |
|---|---|
| VM Running; screenshot Linux emergency mode; log "Failed to mount /data" | Nghi vấn nào ưu tiên và cần xem tệp/thiết bị gì? |
| VM Running; ảnh Windows login; RDP timeout | Vì sao chưa thể kết luận boot failure? |
| Boot screenshot đen; serial log rỗng; VM vừa tạo từ custom image | Những điều kiện console/boot diagnostics nào cần kiểm tra? |
| VM đã deallocate; Serial Console không kết nối | Có phải lỗi NSG không? Cần kiểm tra state nào? |
| Azure VM Agent không phản hồi, VM chưa đến login | Vì sao Run Command có thể không giúp được? |
| Snapshot OS disk có nhưng không chắc nhất quán | Bạn phải làm gì trước khi đổi disk trong production? |

### Kết quả cần nộp

| Hạng mục | Bằng chứng |
|---|---|
| VM và trạng thái | Resource ID, OS, power state, thời điểm kiểm tra |
| Boot Diagnostics | Screenshot/log đã được xem, thông điệp liên quan (đã che dữ liệu nhạy cảm) |
| Serial Console | Tình trạng kết nối, điều kiện/quyền và loại guest console |
| Chẩn đoán | Nhóm nguyên nhân, 2–3 giả thuyết, cách xác minh |
| An toàn | Bản backup/snapshot, rủi ro can thiệp và điều kiện rollback |
| Kết luận | Phương án xử lý ưu tiên, người chịu trách nhiệm, smoke tests |

## 21. Ma trận lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra hợp lý |
|---|---|---|
| Không thấy mục Boot diagnostics hoặc dữ liệu bị từ chối | Quyền chưa đủ, tính năng chưa bật, loại VM không hỗ trợ hoặc policy | Kiểm tra IAM, diagnostics settings, VM model |
| Screenshot không cập nhật | Boot Diagnostics mới bật, nguồn dữ liệu trễ hoặc VM không đang chạy | Kiểm tra timestamp, state và cấu hình |
| Serial Console báo cần bật Boot Diagnostics | Diagnostics bị tắt hoặc trạng thái cấu hình chưa cập nhật | Bật theo hướng dẫn rồi kiểm tra lại |
| Serial Console báo VM phải Running | VM Stopped/Deallocated | Xem VM power state, khởi động theo phê duyệt |
| Serial Console có kết nối nhưng màn hình trống | Guest serial output/getty/EMS không cấu hình, VM treo sớm | Kiểm tra image, boot log, thử Enter trên Linux |
| Serial Console bị lỗi WebSocket | Proxy/firewall phía người dùng hoặc dịch vụ/kết nối | Kiểm tra host dịch vụ serial console theo tài liệu |
| Linux emergency mode | /etc/fstab, UUID, mount unit, filesystem, disk thiếu | Kiểm tra serial logs, lsblk, fstab; không format |
| Linux kernel panic sau update | Kernel/initramfs/driver/root filesystem | Thu kernel messages; cân nhắc kernel trước hoặc offline repair |
| Windows hiển thị Recovery/BCD error | Boot config, disk/driver hoặc update | Đối chiếu mã lỗi và Gen1/Gen2; snapshot rồi repair |
| Windows login hiển thị nhưng RDP hỏng | Network/NSG/firewall/TermService | Network Watcher, SAC và guest logs |
| Run Command/extension timeout | Guest agent chưa khỏe hoặc OS chưa boot | Dùng Boot Diagnostics/Serial Console thay vì chờ agent |
| VM sửa xong nhưng dữ liệu app không xuất hiện | Data disk chưa attach/mount, service phụ thuộc chưa lên | Kiểm tra data disks, filesystem, DB và nghiệp vụ |
| Sau repair phát sinh phí bất thường | Repair VM, snapshots, disk copy chưa dọn | Kiểm kê tài nguyên, xác nhận khôi phục rồi cleanup |

Đừng đưa ra kết luận "Azure platform lỗi" chỉ từ việc SSH timeout hoặc screenshot trống. Sự cố platform cần xác minh thông qua trạng thái dịch vụ, instance view và các bằng chứng liên quan.

## 22. Checklist trước khi đóng sự cố

- [ ] Đã xác định đúng VM/subscription/region/OS và timeline sự cố.
- [ ] Đã đọc Boot Diagnostics screenshot, serial log và phân biệt dữ liệu mới/cũ.
- [ ] Đã đối chiếu VM Running/Provisioning với trạng thái guest OS thực tế.
- [ ] Đã xác định lỗi boot, connectivity, authentication hay application.
- [ ] Nếu dùng Serial Console, quyền Azure và guest credentials được kiểm soát; không ghi secret vào session log.
- [ ] Nếu sửa cấu hình, đã ghi lại thay đổi và tạo bản sao/backup phù hợp trước các thao tác rủi ro.
- [ ] Nếu sửa OS disk offline, đã kiểm tra VM generation, encryption, đúng disk copy và quy trình restore.
- [ ] Đã xác minh reboot/login, dịch vụ ứng dụng và dữ liệu sau khi sửa.
- [ ] Đã kiểm tra Azure Monitor, guest logs và cảnh báo để phát hiện lỗi tái diễn.
- [ ] Đã ghi root cause, các điều kiện rollback và hành động ngăn lặp lại.
- [ ] Đã dọn repair VM, snapshots hoặc tài nguyên thử nghiệm **chỉ sau khi được phê duyệt**.
- [ ] Đã kiểm tra chi phí và cập nhật runbook vận hành.

## 23. Câu hỏi tự kiểm tra

1. Vì sao một VM hiển thị Running nhưng vẫn có thể bị boot failure?
2. Boot Diagnostics thu những loại bằng chứng nào? Screenshot có phải video toàn bộ quá trình boot không?
3. Managed boot diagnostics storage khác custom storage account ở điểm gì?
4. Serial Console có cần mở cổng 22 hoặc 3389 trong NSG không?
5. Vì sao một phiên Serial Console thành công chưa đồng nghĩa người dùng có ngay quyền root/Administrator?
6. Với Linux, ttyS0, getty và serial boot messages có vai trò gì?
7. Trên Windows, SAC/EMS hỗ trợ tình huống nào và vì sao custom image có thể không hiện SAC?
8. Linux vào emergency mode sau khi gắn data disk: vì sao cần kiểm tra UUID và /etc/fstab trước?
9. VM hiển thị màn hình Windows login nhưng RDP timeout: những lớp nào nên kiểm tra?
10. Vì sao không nên format một disk được gắn vào repair VM chỉ vì không nhìn thấy mount point?
11. Snapshot OS disk có luôn application-consistent cho database đang chạy không?
12. Khi nào cần sửa disk offline, khi nào chỉ cần sửa NSG/firewall hoặc guest service?
13. Vì sao phải kiểm tra mã hóa và VM generation trước khi sửa BCD/GRUB?
14. Sau khi sửa boot, cần những smoke tests và bước cleanup nào?

## 24. Tài liệu tham khảo

- [Azure boot diagnostics](https://learn.microsoft.com/azure/virtual-machines/boot-diagnostics) — screenshot, serial log và managed/custom diagnostics storage.
- [Boot diagnostics: troubleshooting Azure VMs](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/windows/boot-diagnostics) — cách dùng screenshot/console output để điều tra.
- [Azure Serial Console overview](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/windows/serial-console-overview) — điều kiện, quyền và giới hạn truy cập.
- [Azure Serial Console for Linux](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/linux/serial-console-linux) — ttyS0 và chẩn đoán Linux.
- [Azure Serial Console for Windows](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/windows/serial-console-windows) — EMS/SAC và Windows boot.
- [Common Azure Serial Console errors](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/windows/serial-console-errors) — lỗi quyền, WebSocket và cấu hình.
- [Repair a Linux VM using VM repair commands](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/linux/repair-linux-vm-using-azure-virtual-machine-repair-commands) — workflow sửa OS disk Linux offline.
- [Repair a Windows VM using VM repair commands](https://learn.microsoft.com/troubleshoot/azure/virtual-machines/windows/repair-windows-vm-using-azure-virtual-machine-repair-commands) — workflow sửa OS disk Windows offline.
- [Azure CLI: az vm boot-diagnostics](https://learn.microsoft.com/cli/azure/vm/boot-diagnostics) — bật, tắt và xem log.
- [Azure CLI: az serial-console](https://learn.microsoft.com/cli/azure/serial-console) — kết nối console qua CLI.

**Kết luận:** Khi Azure VM không truy cập được, hãy **đọc trạng thái VM và Boot Diagnostics trước**, dùng **Serial Console** khi cần tương tác với guest OS mà SSH/RDP không hoạt động, rồi mới quyết định sửa cấu hình hay repair OS disk. Tách lỗi boot khỏi lỗi mạng, giữ bằng chứng, bảo vệ dữ liệu và có rollback giúp khôi phục nhanh hơn mà không tạo thêm rủi ro cho hệ thống.
