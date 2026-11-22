# Khôi phục Boot Volume và xử lý lỗi mount dữ liệu

## Mục tiêu bài học

Một instance OCI không truy cập được qua SSH chưa chắc đã hỏng Boot Volume. Tương tự, ứng dụng báo không ghi được file chưa chắc có lỗi attachment. Khôi phục hiệu quả bắt đầu bằng việc xác định đúng lớp gặp sự cố, bảo toàn dữ liệu và chọn đường phục hồi phù hợp.

Bài thuộc chương **Block Volume và Boot Volume**, module **CLOUD_PROVIDERS_ORACLE**. Nội dung kết nối Compute và lưu trữ với IAM, mạng VCN, giám sát, backup và khả năng khôi phục dịch vụ.

Sau bài này, bạn có thể:

- Phân biệt lỗi truy cập instance, lỗi khởi động hệ điều hành và lỗi mount volume dữ liệu.
- Chọn giữa khôi phục từ Boot Volume backup và sửa Boot Volume qua máy cứu hộ.
- Đối chiếu volume, attachment, thiết bị, phân vùng, filesystem và mount point.
- Nhận diện lỗi UUID, `/etc/fstab`, thứ tự khởi động, filesystem và quyền truy cập.
- Lập kế hoạch phục hồi có kiểm chứng, tránh cho ứng dụng ghi nhầm lên Boot Volume hoặc chạy đồng thời hai bản hệ thống có tác dụng phụ.

Phần lệnh trong bài minh họa cho Linux. Điều kiện tháo/gắn Boot Volume, kiểu attachment và công cụ cứu hộ phải phù hợp với loại instance, shape, hệ điều hành và khả năng OCI hỗ trợ. Không áp dụng quy trình tháo boot của một VM cho mọi loại bare metal hoặc mọi cấu hình khác.

## 1. Nhìn sự cố theo từng lớp

Một đường dữ liệu điển hình:

```text
Tài nguyên volume trong OCI
  -> Attachment tới instance
  -> Thiết bị mà hệ điều hành nhận diện
  -> Phân vùng / LVM / lớp mã hóa, nếu có
  -> Filesystem
  -> Mount point
  -> Quyền truy cập và ứng dụng
```

Một lỗi ở lớp dưới có thể tạo nhiều triệu chứng ở lớp trên. Tuy nhiên, sửa sai lớp có thể khiến dữ liệu khó phục hồi hơn.

| Triệu chứng | Giả thuyết cần kiểm tra trước | Chưa thể kết luận |
| --- | --- | --- |
| SSH timeout | Trạng thái instance, route, NSG/security list, firewall và đường truy cập | Boot Volume đã hỏng |
| SSH từ chối đăng nhập | User, khóa SSH, dịch vụ SSH và cấu hình xác thực | Cần restore toàn bộ hệ điều hành |
| Console cho thấy emergency mode | Lỗi boot, filesystem hoặc mục mount bắt buộc trong `fstab` | Phân vùng root đã mất |
| OCI báo đã attach nhưng không thấy mount | Kết nối thiết bị, phân vùng, filesystem và mount point | Dữ liệu không còn |
| Ứng dụng báo permission denied | User/group, mode, ACL và chính sách bảo mật hệ điều hành | IAM không cho mount volume |
| Ứng dụng báo read-only filesystem | Trạng thái mount, lỗi filesystem hoặc I/O | Chỉ cần đổi quyền file |
| Ứng dụng báo no space left | Dung lượng, inode, quota và filesystem đang thực sự chứa đường dẫn | Phải tạo lại filesystem |

Trạng thái Compute đang chạy chỉ cho biết một phần vòng đời hạ tầng. Nó không bảo đảm hệ điều hành đã khởi động bình thường, ứng dụng đã sẵn sàng hoặc dữ liệu đã mount đúng.

## 2. Chuẩn bị trước khi thực hiện phục hồi

### 2.1. Ghi nhận danh tính và quan hệ tài nguyên

Lập một phiếu sự cố với:

- Region, availability domain, compartment và OCID của instance.
- OCID Boot Volume, các Block Volume và attachment liên quan.
- Loại instance, shape, image/hệ điều hành và kiến trúc CPU.
- Mount point, filesystem và định danh thiết bị trước sự cố nếu có.
- Thao tác gần nhất: cập nhật hệ điều hành, sửa `fstab`, đổi attachment, thay instance hoặc tăng volume.
- Các backup sẵn có, thời điểm khôi phục mong muốn và nơi giữ khóa/secrets cần thiết.
- Ứng dụng, batch hoặc automation nào có thể tiếp tục tác động đến instance trong lúc xử lý.

Không chỉ dùng tên hiển thị làm căn cứ chọn volume. Hai bản phục hồi có thể có tên gần giống nhau, dung lượng giống nhau và thậm chí UUID filesystem trùng nhau.

### 2.2. Xác định mục tiêu dữ liệu và thời gian

- **RPO**: chấp nhận mất dữ liệu đến thời điểm nào?
- **RTO**: cần khôi phục dịch vụ trong khoảng thời gian nào?

Một Boot Volume backup của tuần trước có thể khôi phục hệ điều hành, nhưng không tự đáp ứng yêu cầu dữ liệu phát sinh hôm nay. Cũng cần xem tương thích giữa phiên bản ứng dụng trên boot được phục hồi và schema/dữ liệu hiện tại của cơ sở dữ liệu Oracle.

### 2.3. Giữ đường quay lại

Trước thay đổi có thể ghi lên dữ liệu, giữ bản gốc và tạo bản sao hoặc backup phù hợp khi điều kiện cho phép. Thao tác kiểm tra và sửa chữa nên thực hiện trên bản phục hồi riêng trước nếu thời gian và nguồn lực cho phép.

Không để máy gốc và máy phục hồi đồng thời chạy cùng một vai trò ghi dữ liệu ngoài ý muốn. Cần kiểm soát load balancer, worker, batch, scheduler và automation có thể tự khởi động lại ứng dụng.

Một subnet không có public IP chưa chắc đã cách ly được tác dụng phụ: máy vẫn có thể truy cập DB, queue hoặc API qua mạng riêng. Cách ly phải dựa vào các đường truy cập và quyền thực tế.

## 3. Chọn đường phục hồi Boot Volume

| Tình huống | Hướng ưu tiên đánh giá | Điều kiện cần kiểm tra |
| --- | --- | --- |
| Có backup tốt, cần quay về trạng thái đã biết | Restore thành Boot Volume mới rồi tạo môi trường phục hồi | Thời điểm backup, vị trí, image/shape, khóa và dữ liệu đi kèm |
| Boot còn nguyên nhưng cấu hình như `fstab` sai | Sửa qua console hoặc máy cứu hộ | Khả năng truy cập, tháo/gắn boot được hỗ trợ, định danh đúng filesystem |
| Nghi filesystem bị hỏng | Giữ bản gốc, chẩn đoán offline trên bản sao | Công cụ đúng filesystem, thiết bị không được mount, kế hoạch khi không sửa được |
| Instance mất nhưng boot đã được giữ lại | Đánh giá dùng Boot Volume còn lại theo luồng OCI hỗ trợ | Tương thích, vị trí và tình trạng dữ liệu |
| Không có bản phục hồi phù hợp, dữ liệu chưa rõ | Bảo toàn và xác định khả năng cứu dữ liệu | Tránh tiếp tục ghi hoặc tạo filesystem lên thiết bị cũ |

Không cần restore cả Boot Volume nếu hệ điều hành vẫn tốt và lỗi chỉ là một volume dữ liệu chưa mount. Ngược lại, sửa `fstab` không giải quyết được trường hợp không còn một bản hệ điều hành có thể sử dụng.

## 4. Khôi phục từ Boot Volume backup

### 4.1. Chọn đúng bản backup

Trước khi restore, đối chiếu:

1. Backup thuộc Boot Volume và môi trường nào.
2. Thời điểm dữ liệu mà bản backup đại diện.
3. Backup có trước sự cố hoặc thay đổi gây lỗi không.
4. Trạng thái backup có cho phép phục hồi không.
5. Khả năng sử dụng tại region/availability domain đích và các bước sao chép cần thiết, nếu có.
6. Quyền IAM và khả năng sử dụng khóa mã hóa liên quan.
7. Những dữ liệu nào nằm trên Block Volume khác, dịch vụ DB hoặc nơi lưu trữ khác.

Không chọn backup chỉ theo thời gian hoàn tất tác vụ mà bỏ qua thời điểm dữ liệu được ghi nhận. Với workload có giao dịch, phải dùng quy trình backup/restore nhất quán được ứng dụng hoặc database hỗ trợ.

### 4.2. Tạo volume phục hồi riêng

Restore từ Boot Volume backup tạo một Boot Volume phục hồi theo luồng dịch vụ hỗ trợ. Không xem thao tác này là ghi đè tại chỗ mọi volume đang gắn vào instance lỗi.

Chọn vị trí phù hợp với instance dự kiến sử dụng. Việc gắn volume thông thường chịu ràng buộc vị trí như availability domain; một backup hoặc bản sao không đồng nghĩa có thể attach trực tiếp volume ở bất kỳ nơi nào.

Chờ quá trình phục hồi đạt trạng thái cho phép sử dụng và kiểm tra kết quả thao tác. Có tài nguyên mới xuất hiện chưa chứng minh dữ liệu đã sẵn sàng để khởi động ứng dụng.

### 4.3. Tạo instance phục hồi và kiểm soát khởi động ứng dụng

Dùng luồng tạo instance từ Boot Volume được OCI hỗ trợ, với shape và cấu hình tương thích. Gán mạng, quyền và chính sách bảo mật phù hợp với môi trường phục hồi.

Trước khi bật lưu lượng thật, kiểm tra khả năng phần mềm trong bản boot tự chạy:

- Service ứng dụng có được bật khởi động cùng hệ điều hành không?
- Scheduler có chạy tác vụ gửi email, xử lý thanh toán hoặc cập nhật DB không?
- Agent hoặc ứng dụng có danh tính cấu hình trùng với máy gốc không?
- Cloud-init hoặc script khởi tạo có hành vi gì khi môi trường instance thay đổi?
- Cấu hình network, hostname và địa chỉ phụ thuộc có còn đúng không?

Khôi phục hệ điều hành không tự khôi phục đúng IAM policy, route, NSG, load balancer và các tài nguyên bên ngoài volume. Các phần đó cần được tạo hoặc đối chiếu bằng cấu hình hạ tầng phù hợp.

### 4.4. Đối chiếu dữ liệu ngoài boot

Nếu bản boot chứa ứng dụng cũ nhưng Block Volume hoặc DB chứa dữ liệu mới, cần đánh giá tương thích trước khi cho ghi. Không chạy migration tự động một cách vô thức trong lần khởi động phục hồi.

Backup boot không bao gồm mọi dữ liệu trên các Block Volume riêng. Từng thành phần cần có nguồn phục hồi và quan hệ thời điểm phù hợp, nhất là khi giao dịch trải qua nhiều nơi lưu trữ.

## 5. Sửa Boot Volume bằng máy cứu hộ

### 5.1. Vai trò của máy cứu hộ

Máy cứu hộ là một instance hoạt động bình thường, dùng để nhận volume lỗi như một thiết bị dữ liệu trong luồng attachment được hỗ trợ. Bạn xem log, kiểm tra cấu hình hoặc xử lý filesystem mà không phải khởi động hệ điều hành từ chính volume đang lỗi.

Khi chọn máy cứu hộ:

- Đảm bảo vị trí và loại attachment tương thích với volume.
- Có công cụ hỗ trợ filesystem, LVM hoặc lớp mã hóa cần xử lý.
- Kiểm soát tự động mount và tránh tự chạy phần mềm từ volume được gắn.
- Nếu cần chạy binary của hệ điều hành được cứu bằng `chroot`, phải đánh giá kiến trúc CPU và môi trường runtime tương thích. Chỉ đọc file trên filesystem không đồng nghĩa cần chạy binary đó.

### 5.2. Trình tự thao tác có kiểm soát

1. Ngăn ứng dụng và automation tiếp tục tác động đến tài nguyên cần phục hồi theo quy trình vận hành.
2. Dừng instance nguồn khi luồng tháo Boot Volume yêu cầu, chờ trạng thái thích hợp.
3. Xác nhận lựa chọn giữ volume; không dùng terminate như cách thay cho việc stop/detach có chủ đích.
4. Tháo Boot Volume theo khả năng OCI hỗ trợ cho đúng loại instance.
5. Gắn boot đó, hoặc bản sao của nó, làm volume dữ liệu vào máy cứu hộ theo luồng được hỗ trợ.
6. Đối chiếu attachment với thiết bị và phân vùng thực tế trong hệ điều hành cứu hộ.
7. Đọc cấu hình, log và kiểm tra filesystem trước khi quyết định sửa.
8. Sau sửa, flush/unmount và tháo attachment có kiểm soát; không tháo khi còn sử dụng.
9. Gắn lại làm boot hoặc tạo instance phục hồi theo đường được hỗ trợ.
10. Kiểm tra boot, mount dữ liệu và ứng dụng trước khi khôi phục lưu lượng.

Không giữ một filesystem thông thường ở trạng thái ghi đồng thời từ máy gốc và máy cứu hộ. Khả năng tạo nhiều attachment không tự bảo vệ filesystem khỏi truy cập đồng thời không được hỗ trợ.

### 5.3. Phân biệt root của máy cứu hộ và root của máy bị lỗi

Giả sử filesystem root cần cứu được mount tại `/mnt/recovery`:

| Đường dẫn | Thuộc môi trường nào? |
| --- | --- |
| `/etc/fstab` | Máy cứu hộ đang chạy |
| `/mnt/recovery/etc/fstab` | Hệ điều hành đang được cứu |
| `/var/log` | Log của máy cứu hộ |
| `/mnt/recovery/var/log` | Log lưu trên filesystem được cứu, nếu log nằm tại đó |

Sửa nhầm `/etc/fstab` của máy cứu hộ vừa không sửa được sự cố gốc, vừa có thể làm máy cứu hộ không khởi động bình thường. Tương tự, `journalctl -b` chạy thông thường đọc boot của máy hiện tại, không tự đọc lịch sử của volume đang mount ở nơi khác.

Nếu cần đọc journal lưu trên volume được cứu, dùng chế độ đọc thư mục/root phù hợp của công cụ với đúng đường dẫn và định dạng log. Không diễn giải log của máy cứu hộ như bằng chứng từ máy lỗi.

### 5.4. Read-only mount có giới hạn cần hiểu

Một filesystem có journal có thể cần replay log trong lúc mount. Chỉ có tùy chọn `ro` chưa đủ để khẳng định mọi thao tác mount đều không thay đổi dữ liệu nguồn.

Khi cần giữ nguyên bản gốc, ưu tiên làm trên bản sao và dùng chế độ kiểm tra/mount không replay phù hợp với filesystem và công cụ đang dùng. Ví dụ, ext4 có lựa chọn liên quan đến không nạp journal; XFS có chế độ không recovery khi mount chỉ đọc. Các chế độ này có thể cho góc nhìn chưa nhất quán nếu trước đó filesystem chưa đóng sạch.

Nếu gặp UUID trùng khi gắn bản sao, xác định đúng nguyên nhân và cách truy cập bản sao theo filesystem. Không đổi UUID của bản gốc chỉ để vượt qua thông báo mà chưa biết những tham chiếu nào đang phụ thuộc vào nó.

## 6. Chẩn đoán lỗi mount dữ liệu từ dưới lên

### 6.1. Lớp OCI: volume có thực sự gắn đúng máy?

Đối chiếu:

- OCID volume và attachment, không chỉ tên hiển thị.
- Instance đích, availability domain và trạng thái attachment.
- Chế độ truy cập được cấu hình: đọc/ghi, chỉ đọc hoặc chia sẻ theo khả năng hỗ trợ.
- Kiểu attachment và các bước kết nối trong hệ điều hành.
- Sự kiện thao tác thất bại hoặc thay đổi gần nhất.

Với iSCSI, kiểm tra session và các thao tác kết nối theo hướng dẫn cho đúng attachment. Không tự mở một cổng iSCSI ra Internet hoặc thay đổi toàn bộ security rules như phản ứng mặc định trước lỗi mount.

Với paravirtualized attachment, vẫn phải xác nhận hệ điều hành nhận thiết bị và có driver phù hợp. “Attached” ở control plane không có nghĩa mọi lớp trong guest đều đã sẵn sàng.

### 6.2. Lớp thiết bị: phân vùng nào chứa dữ liệu?

Dùng lệnh đọc thông tin trên máy đang chẩn đoán:

```bash
# Quan hệ thiết bị, phân vùng, filesystem và mount
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,UUID

# Đọc định danh filesystem; có thể cần quyền quản trị
sudo blkid

# Nguồn filesystem root của máy hiện tại
findmnt -T /
```

Volume có thể chứa một filesystem trực tiếp, nhiều phân vùng, LVM hoặc lớp mã hóa. Không chọn thiết bị cha để mount nếu filesystem thực sự nằm trong phân vùng hoặc logical volume.

Không kết luận thiết bị trống chỉ vì một công cụ không hiển thị `FSTYPE`. Cần kiểm tra lớp lưu trữ và khả năng công cụ hỗ trợ trước khi quyết định tạo filesystem.

### 6.3. Lớp filesystem và mount point

```bash
# Thay bằng đường dẫn dữ liệu thực sự tồn tại
findmnt -T /srv/app-data

# Dung lượng và inode của các filesystem đã mount
df -hT
df -i

# Các unit thất bại và lỗi kernel của boot hiện tại
systemctl --failed
sudo journalctl -k -b --no-pager
```

Nếu `findmnt -T /srv/app-data` trả về filesystem root, có thể volume dữ liệu chưa mount tại đó. Ứng dụng có thể đang ghi vào thư mục nằm trên Boot Volume thay vì nơi dự kiến.

Đặc biệt, khi mount volume lên một thư mục đã có file, các file cũ bên dưới bị che khỏi đường dẫn đó; chúng không tự được chuyển lên volume mới. Cần lập kế hoạch hợp nhất dữ liệu nếu trước sự cố đã có giai đoạn ứng dụng ghi nhầm lên root.

### 6.4. Ứng dụng không ghi được nhưng mount vẫn đúng

Kiểm tra riêng:

- Mount có đang chỉ đọc không.
- Dung lượng hoặc inode có hết không.
- User/group, mode, ACL và chính sách như SELinux có cho phép không.
- UID/GID của ứng dụng có thay đổi sau khi phục hồi hoặc thay máy không.
- Dịch vụ có đang dùng đúng thư mục, container mount hoặc namespace không.

Quyền IAM quyết định các thao tác dịch vụ OCI, không thay thế quyền file trong hệ điều hành. Không dùng việc cấp thêm quyền quản trị tenancy để xử lý một lỗi ownership trong filesystem.

## 7. Sửa lỗi `/etc/fstab` và thứ tự khởi động

### 7.1. Dòng mount có thể làm hệ điều hành dừng ở emergency mode

`/etc/fstab` khai báo filesystem và cách mount. Một entry trỏ đến UUID không còn tồn tại, sai kiểu filesystem hoặc có tùy chọn không hợp lệ có thể khiến boot bị chặn tùy chính sách của hệ điều hành.

Các trường cần hiểu:

| Trường | Vai trò |
| --- | --- |
| Nguồn | UUID, label hoặc đường dẫn thiết bị ổn định được hỗ trợ |
| Mount point | Thư mục đích |
| Kiểu filesystem | Ví dụ ext4 hoặc XFS, phải đúng dữ liệu thực tế |
| Tùy chọn | Quyền, hành vi mount, yêu cầu mạng và tùy chọn đặc thù |
| Dump/fsck | Tham số liên quan đến công cụ backup cũ và thứ tự kiểm tra theo filesystem |

Dòng minh họa cho volume dữ liệu ext4 cần được xử lý như thiết bị phụ thuộc mạng ở giai đoạn mount:

```fstab
UUID=<UUID_THUC_TE_CUA_FILESYSTEM> /srv/app-data ext4 defaults,_netdev 0 2
```

Đây không phải dòng để sao chép nguyên trạng. Phải dùng UUID, filesystem và tùy chọn phù hợp. `_netdev` giúp mô tả phụ thuộc mạng cho quá trình mount; nó không tạo iSCSI session, không sửa attachment và không chứng minh ứng dụng có thể truy cập dữ liệu.

Không áp dụng trường kiểm tra filesystem của ext4 cho XFS một cách máy móc. Mỗi filesystem và hệ điều hành có cơ chế kiểm tra/phục hồi riêng.

### 7.2. Kiểm tra trước khi thử mount toàn bộ

Trên hệ điều hành đang được sửa trực tiếp, có thể đọc và kiểm tra cấu hình bằng:

```bash
cat /etc/fstab
findmnt --verify --verbose
```

Lệnh kiểm tra cần có trong phiên bản công cụ đang dùng và không thay thế việc xác minh nội dung dữ liệu. Nếu đang cứu hộ, đường dẫn cần sửa là file trong root được mount của hệ điều hành lỗi; các lệnh mặc định ở trên không tự đổi sang file đó.

Không dùng `mount -a` như một phép kiểm tra chỉ đọc. Nó có thể thực sự mount các entry và làm phát sinh truy cập ghi hoặc liên hệ dịch vụ ngoài. Chỉ thử sau khi đã kiểm tra các entry, loại filesystem, thiết bị và tác động dự kiến trong môi trường phù hợp.

Trước khi sửa `fstab`, giữ lại nội dung cũ trong phạm vi kế hoạch phục hồi. Thay đổi đúng entry gây lỗi, rồi kiểm tra lại trước khi reboot; đừng xóa đồng loạt mọi dòng dữ liệu để chỉ đạt mục tiêu đăng nhập được.

### 7.3. `nofail` không phải cách bỏ qua mọi lỗi dữ liệu

Với một mount tùy chọn, cấu hình cho phép boot tiếp khi mount thiếu có thể phù hợp. Nhưng nếu đó là dữ liệu bắt buộc của DB hoặc ứng dụng, boot tiếp rồi để ứng dụng ghi vào thư mục trống trên root là hành vi nguy hiểm.

Hai yêu cầu cần tách rõ:

1. Có cho phép hệ điều hành tiếp tục boot khi volume thiếu không?
2. Có cho phép dịch vụ ứng dụng chạy khi filesystem dữ liệu chưa sẵn sàng không?

Ví dụ, với dịch vụ dùng systemd, có thể thiết kế dependency của unit như sau, trong cấu hình phù hợp của đúng service:

```ini
[Unit]
RequiresMountsFor=/srv/app-data
```

Dependency này giúp liên hệ khởi động dịch vụ với mount cần thiết, nhưng không tự chứng minh mount đó là đúng volume hoặc nội dung dữ liệu đã hợp lệ. Cần kiểm tra định danh volume và điều kiện sẵn sàng của ứng dụng riêng.

Không đặt một thời gian chờ mount cố định chỉ để lỗi biến mất nhanh hơn mà không hiểu thời gian kết nối thực tế. Thứ tự boot, attachment và việc sẵn sàng của thiết bị phải phù hợp nhau.

## 8. Khi nghi filesystem bị hỏng

### 8.1. Ngừng suy đoán từ thông báo chung

Thông báo như “wrong filesystem type”, “bad superblock” hoặc “read-only filesystem” có nhiều nguyên nhân:

- Chọn nhầm thiết bị hoặc phân vùng.
- Filesystem nằm trong LVM hoặc lớp mã hóa chưa được mở đúng.
- Thiếu công cụ hoặc driver hỗ trợ.
- UUID trùng từ bản clone.
- Journal/log cần phục hồi.
- Metadata bị hỏng hoặc có lỗi I/O ở lớp dưới.

Giữ thông báo lỗi đầy đủ và log kernel liên quan. Không tạo filesystem mới trên thiết bị chỉ để mount thành công; thao tác đó không phải sửa lỗi mount của dữ liệu cũ.

### 8.2. Chẩn đoán offline trên thiết bị đã xác định

Các công cụ kiểm tra/sửa filesystem cần đúng loại filesystem và đúng trạng thái thiết bị. Để kiểm tra offline đáng tin cậy, filesystem cần không còn được mount hoặc ghi bởi máy khác.

| Filesystem | Công cụ chuyên dụng thường dùng | Lưu ý |
| --- | --- | --- |
| ext4 | `e2fsck` | Xác minh đúng thiết bị; chế độ kiểm tra và sửa có tác động khác nhau |
| XFS | `xfs_repair` | Không coi cách gọi fsck chung là đủ; kiểm tra yêu cầu liên quan đến log và trạng thái mount |
| Loại khác | Công cụ được filesystem/hệ điều hành hỗ trợ | Không dùng công cụ của loại khác chỉ vì tên thiết bị giống nhau |

Chế độ chỉ kiểm tra, nếu công cụ hỗ trợ, giúp đánh giá trước nhưng có thể không phản ánh trạng thái cuối sau journal recovery. Đọc kết quả và giới hạn của chế độ đó trước khi quyết định sửa.

Không tự động trả lời đồng ý cho mọi sửa chữa hoặc xóa log filesystem như bước đầu tiên. Các thao tác sửa có thể làm mất một phần dữ liệu; cần bản sao, kế hoạch và đánh giá ảnh hưởng. Nếu xuất hiện lỗi I/O lặp lại, phải điều tra lớp attachment/dịch vụ thay vì chỉ chạy sửa metadata nhiều lần.

### 8.3. Dữ liệu mount được chưa chắc ứng dụng đã nhất quán

Filesystem trở lại trạng thái có thể mount không bảo đảm mọi giao dịch ứng dụng đã hoàn thành. Với cơ sở dữ liệu tự quản trị, còn cần recovery, kiểm tra và công cụ của database theo quy trình được hỗ trợ.

Tương tự, dữ liệu trải trên nhiều volume có thể được phục hồi về các thời điểm khác nhau. Một volume mount tốt không giải quyết sự không nhất quán giữa data file, log và cấu hình nằm ở các nơi khác.

## 9. Bảng xử lý lỗi thường gặp

| Hiện tượng | Kiểm tra | Hướng xử lý có cơ sở |
| --- | --- | --- |
| Không thấy thiết bị | Attachment, kiểu kết nối, session/driver và log kernel | Hoàn tất đúng kết nối, không tạo filesystem để thử |
| Không tìm thấy UUID trong `fstab` | UUID thực tế, volume đang gắn, clone/restore và các lớp LVM | Sửa tham chiếu đúng sau khi xác định nguồn dữ liệu |
| Boot chờ mount rồi vào emergency mode | Entry bắt buộc, thiết bị chưa sẵn sàng, thứ tự mạng | Sửa cấu hình và dependency; chỉ cho boot bỏ qua khi đúng yêu cầu |
| Báo sai filesystem | Phân vùng, metadata, lớp mã hóa/LVM và công cụ hỗ trợ | Chọn đúng lớp thiết bị và loại filesystem |
| Bản clone không mount do trùng UUID | Volume gốc và bản sao đang cùng hiện diện | Dùng cách truy cập bản sao được filesystem hỗ trợ, kiểm soát thay đổi định danh |
| Filesystem tự chuyển chỉ đọc | Log lỗi filesystem và I/O | Bảo toàn dữ liệu, chẩn đoán offline khi cần; không ép ghi một cách suy đoán |
| Mount đúng nhưng permission denied | UID/GID, ACL, SELinux và quyền đường dẫn | Sửa theo danh tính ứng dụng thực tế |
| Mount point báo busy khi tháo | Tiến trình, thư mục làm việc và mount con | Ngừng sử dụng có kiểm soát trước khi unmount/detach |
| Volume lớn hơn nhưng filesystem còn nhỏ | Kích thước thiết bị, phân vùng, LVM và filesystem | Mở rộng đúng từng lớp theo cách được hỗ trợ |
| Sau mount thấy thiếu file vừa ghi | Dữ liệu có từng nằm trên root dưới mount point không? | Đối chiếu hai nguồn, hợp nhất dữ liệu có kiểm soát |
| Khôi phục boot nhưng ứng dụng vẫn lỗi | Volume dữ liệu, DB, secrets, quyền và cấu hình mạng | Phục hồi đầy đủ phụ thuộc, không chỉ phần hệ điều hành |

## 10. Ví dụ xuyên suốt: lỗi `fstab` làm VM không khởi động bình thường

### 10.1. Bối cảnh

Một API Java chạy trên VM OCI. Hệ điều hành nằm trên Boot Volume, dữ liệu làm việc nằm trên Block Volume mount tại `/srv/app-data`; kết quả nghiệp vụ được lưu trong cơ sở dữ liệu Oracle riêng.

Sau khi thay volume dữ liệu bằng một bản phục hồi, người vận hành giữ nguyên UUID cũ trong `fstab`. Lần reboot tiếp theo, console cho thấy hệ điều hành chờ thiết bị không tồn tại rồi vào emergency mode.

### 10.2. Cách phân tích

Bằng chứng ban đầu:

- Instance vẫn có tài nguyên Compute và Boot Volume.
- Console hiển thị lỗi chờ UUID của mount dữ liệu.
- Có một attachment dữ liệu mới, nhưng định danh filesystem không khớp entry cũ.

Vì vậy, hướng xử lý đầu tiên là đối chiếu mount và `fstab`, không phải kết luận boot bị mất và restore toàn bộ hệ điều hành về tuần trước.

### 10.3. Cách phục hồi có thể đánh giá

1. Cô lập luồng xử lý để ứng dụng không chạy ghi dữ liệu trong lúc sửa.
2. Ghi nhận volume/attachment và giữ đường quay lại.
3. Nếu console cho phép sửa an toàn, dùng đường đó; nếu không, đánh giá máy cứu hộ theo điều kiện tháo/gắn boot.
4. Đối chiếu UUID thực tế của filesystem dữ liệu với `fstab` của hệ điều hành lỗi.
5. Sửa entry đúng volume đã xác minh, không chỉ chọn một thiết bị có cùng dung lượng.
6. Kiểm tra dependency của service Java để không khởi động khi dữ liệu thiếu.
7. Đưa Boot Volume trở lại luồng khởi động theo cách được hỗ trợ.
8. Xác nhận root và `/srv/app-data` có nguồn đúng; đối chiếu dữ liệu với thời điểm phục hồi mong muốn.
9. Kiểm tra kết nối DB và tác vụ ứng dụng trước khi nhận traffic.
10. Theo dõi lỗi và xác nhận một lần reboot có kế hoạch khi điều kiện cho phép.

Nếu sau đó phát hiện ứng dụng từng ghi vào thư mục trên root khi data volume chưa mount, cần xử lý phần dữ liệu đó riêng. Việc sửa UUID không tự chuyển những file ấy sang volume dữ liệu.

## 11. Kiểm tra trước khi đưa dịch vụ hoạt động lại

| Nhóm | Điều kiện cần xác nhận |
| --- | --- |
| Boot | Hệ điều hành khởi động, không còn lỗi cần can thiệp trong đường boot |
| Danh tính | Đúng instance, volume, attachment và bản phục hồi dự kiến |
| Mount | Root, dữ liệu và các filesystem bắt buộc có đúng nguồn, quyền và tùy chọn |
| Dữ liệu | Nội dung và thời điểm phục hồi đáp ứng yêu cầu; không bỏ sót dữ liệu dưới mount point |
| Ứng dụng | Đúng phiên bản, cấu hình, secrets và trạng thái migration |
| Phụ thuộc | DB, mạng, DNS, IAM và các dịch vụ liên quan hoạt động phù hợp |
| Đồng thời | Chỉ những bản ứng dụng/worker được phép mới thực hiện tác dụng phụ |
| Phục hồi | Có bản gốc hoặc bản quay lại còn sử dụng được theo kế hoạch |
| Giám sát | Theo dõi boot, dung lượng, I/O, mount và lỗi nghiệp vụ sau khôi phục |
| Chi phí | Biết các máy cứu hộ, volume/bản sao/backup còn giữ và chủ sở hữu |

Kiểm tra mount thành công một lần chưa chứng minh mount sẽ đúng sau reboot. Cần xác nhận cấu hình khởi động và dependency bằng một lần thử phù hợp với yêu cầu sẵn sàng của môi trường.

Sau khi ổn định, ghi nguyên nhân, thời điểm khôi phục, dữ liệu có thể mất theo RPO và thời gian thực tế so với RTO. Chỉ loại bỏ tài nguyên cứu hộ hoặc bản sao khi đã hết nhu cầu phục hồi theo quy trình giữ dữ liệu; một tài nguyên bị detach vẫn có thể còn dữ liệu cần giữ và chi phí cần quản lý.

## 12. Tự kiểm tra

1. Vì sao SSH timeout chưa phải bằng chứng Boot Volume bị hỏng?
2. Khi nào nên restore từ backup thay vì sửa cấu hình qua máy cứu hộ?
3. Backup boot có bảo vệ dữ liệu trên các Block Volume riêng không? Cần đối chiếu thêm gì với cơ sở dữ liệu Oracle?
4. Khi filesystem cần cứu nằm tại `/mnt/recovery`, file `fstab` nào mới là đích cần kiểm tra?
5. Vì sao chỉ dùng tùy chọn mount `ro` chưa đủ để khẳng định bản nguồn không bị thay đổi bởi journal recovery?
6. Nếu `findmnt -T /srv/app-data` trả về filesystem root, ứng dụng có thể đang gặp rủi ro gì?
7. Vì sao thêm `nofail` không phải cách sửa chung cho mount dữ liệu bắt buộc?
8. Điều gì cần được xác nhận trước khi chạy công cụ sửa filesystem?
9. Tại sao bản boot phục hồi không nên tự do chạy cùng scheduler hoặc worker với máy gốc?
10. Những bằng chứng nào cần có trước khi đưa instance phục hồi trở lại load balancer?

Đầu ra của bài thực hành là một quy trình chỉ rõ lớp lỗi, nguồn phục hồi, bản dữ liệu được bảo toàn, thay đổi đã áp dụng và bằng chứng ứng dụng dùng đúng dữ liệu sau khởi động.
