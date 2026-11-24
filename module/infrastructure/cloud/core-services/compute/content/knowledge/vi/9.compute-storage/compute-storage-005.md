# Gắn, tháo và mở rộng volume an toàn

Volume là đơn vị lưu trữ dạng khối có thể gắn vào máy tính toán để hệ điều hành sử dụng như một thiết bị đĩa. Trên hạ tầng đám mây, volume thường được cung cấp độc lập với vòng đời máy ảo, nhờ đó có thể tăng dung lượng, thay máy hoặc khôi phục dữ liệu theo chính sách của dịch vụ. Tuy nhiên, thao tác attach, detach hoặc resize ở control plane chỉ là một phần của quy trình. Hệ điều hành và ứng dụng cũng phải nhận đúng thiết bị, quản lý filesystem và đóng các hoạt động I/O an toàn.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, quản lý volume đúng cách giúp máy ảo có đủ dung lượng cho ứng dụng, cơ sở dữ liệu và dữ liệu vận hành, đồng thời hạn chế mất dữ liệu, filesystem lỗi hoặc gián đoạn dịch vụ. Khi thiết kế cần xem xét cả loại storage, vùng sẵn sàng, hiệu năng IOPS/throughput, mã hóa, snapshot, backup, quyền truy cập và cách phục hồi.

## 1. Volume trong hạ tầng compute

Volume thường được cung cấp dưới dạng block storage. Sau khi gắn vào máy ảo, hệ điều hành nhận thiết bị khối; người quản trị có thể tạo partition, filesystem, mount point và cấp quyền cho ứng dụng.

Một số khái niệm cần phân biệt:

- **Volume:** tài nguyên lưu trữ dạng khối do nền tảng quản lý, có dung lượng và đặc tính hiệu năng riêng.
- **Disk/device:** thiết bị mà hệ điều hành nhìn thấy sau khi volume được gắn.
- **Partition:** vùng logic được chia trên một thiết bị đĩa.
- **Filesystem:** cấu trúc quản lý file và thư mục, ví dụ ext4, XFS hoặc NTFS.
- **Mount point:** thư mục mà filesystem được gắn vào trong cây thư mục Linux; trên Windows, volume thường được gán ký tự ổ đĩa hoặc mount vào thư mục.
- **Snapshot:** bản chụp trạng thái volume tại một thời điểm theo cơ chế của nhà cung cấp.
- **Backup:** bản sao phục vụ khôi phục, thường có chính sách lưu giữ và khả năng bảo vệ độc lập hơn snapshot thông thường.

Không phải mọi loại storage đều là volume. Object storage truy cập qua API để lưu object; file storage cung cấp giao diện chia sẻ file như NFS hoặc SMB; local/ephemeral disk gắn với host và có vòng đời khác với block volume bền vững. Chọn đúng loại lưu trữ ngay từ đầu giúp tránh dùng block volume cho nhu cầu chia sẻ file hoặc dùng local disk làm nơi lưu dữ liệu duy nhất.

### 1.1. Block volume và local/ephemeral disk

| Đặc điểm | Block volume bền vững | Local/ephemeral disk |
| --- | --- | --- |
| Vị trí lưu trữ | Hệ thống storage của nhà cung cấp | Thiết bị cục bộ trên host hoặc máy vật lý |
| Vòng đời | Có thể tồn tại độc lập với VM nếu cấu hình giữ lại | Thường gắn với vòng đời VM/host |
| Độ trễ | Phụ thuộc backend và đường truy cập storage | Thường thấp do gần CPU và bộ nhớ |
| Khả năng detach/reattach | Thường hỗ trợ theo giới hạn nền tảng | Có thể không hỗ trợ hoặc không có ý nghĩa tương tự |
| Dữ liệu khi host/VM bị thay thế | Thường giữ nếu volume được bảo toàn | Có thể mất |
| Trường hợp sử dụng | OS/data disk, database, dữ liệu cần lưu bền vững | Cache, scratch, dữ liệu tạm có thể tái tạo |

Trước khi thao tác, xác định rõ volume nào chứa dữ liệu cần giữ và volume nào chỉ chứa dữ liệu tạm. Không suy luận độ bền dữ liệu chỉ từ tên thiết bị hoặc việc hệ điều hành đang hiển thị một ổ đĩa.

### 1.2. Các giới hạn cần kiểm tra

Khả năng gắn volume phụ thuộc vào:

- Vùng hoặc zone mà volume được tạo và vị trí của VM.
- Số lượng volume tối đa mà VM hoặc loại instance hỗ trợ.
- Loại giao thức và kiểu thiết bị được nền tảng cung cấp.
- Hỗ trợ multi-attach và điều kiện sử dụng đồng thời.
- Kích thước volume tối đa, IOPS, throughput và giới hạn tổng ở cấp VM.
- Loại volume có hỗ trợ mã hóa, snapshot và thay đổi dung lượng trực tuyến hay không.

Một số volume chỉ có thể gắn vào VM trong cùng availability zone. Một số dịch vụ hỗ trợ chia sẻ volume giữa nhiều máy nhưng chỉ với loại volume, filesystem và cơ chế khóa cụ thể. Không được giả định hai VM có thể mount cùng một filesystem thông thường ở chế độ đọc/ghi đồng thời mà không gây hỏng dữ liệu.

## 2. Quy trình gắn volume (attach)

Attach là thao tác liên kết volume với một máy tính toán. Sau khi provider báo thao tác hoàn tất, hệ điều hành có thể cần thời gian để phát hiện thiết bị. Tên thiết bị mà control plane yêu cầu cũng có thể khác tên thực tế trong guest OS, đặc biệt với thiết bị NVMe.

Quy trình tổng quát:

1. Xác định VM đích, vùng, volume ID và mục đích sử dụng.
2. Kiểm tra volume đang ở trạng thái có thể attach và không bị gắn trái với chính sách.
3. Xác minh vùng, loại máy, giới hạn attach và quyền IAM.
4. Gắn volume qua console, API, CLI hoặc công cụ IaC.
5. Chờ thao tác attach hoàn tất ở control plane.
6. Quét lại thiết bị trong hệ điều hành và xác định đúng volume bằng ID/serial/UUID.
7. Nếu là volume mới, tạo partition và filesystem theo thiết kế; nếu là volume có dữ liệu, kiểm tra filesystem và mount hiện có.
8. Mount vào đường dẫn phù hợp, thiết lập quyền và cấu hình mount bền vững nếu cần.
9. Kiểm tra ứng dụng đọc/ghi được và metric I/O bình thường.

### 2.1. Xác định thiết bị trong Linux

Tên như /dev/sdf, /dev/xvdf hoặc /dev/nvme1n1 không phải lúc nào cũng ổn định giữa các lần khởi động hoặc các loại instance. Nên đối chiếu thông tin từ provider với serial, volume ID hoặc liên kết ổn định dưới /dev/disk/by-id/.

Một số lệnh kiểm tra thường dùng:

~~~bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,UUID
sudo blkid
sudo dmesg | tail -n 50
~~~

Trước khi chạy **mkfs**, phải xác nhận thiết bị thực sự là volume mới và chưa chứa dữ liệu cần giữ. Lệnh tạo filesystem có thể ghi đè metadata của filesystem cũ.

### 2.2. Khởi tạo volume mới trên Linux

Ví dụ minh họa sau giả định đường dẫn /dev/disk/by-id/DEVICE_ID là thiết bị mới, trống và đã được xác minh. Tên thiết bị và kích thước cần thay theo môi trường thực tế.

~~~bash
# Xác minh thiết bị trước khi thay đổi
lsblk -f /dev/disk/by-id/DEVICE_ID

# Tạo filesystem trực tiếp trên thiết bị (nếu không cần partition)
sudo mkfs.ext4 /dev/disk/by-id/DEVICE_ID

# Tạo mount point và mount
sudo mkdir -p /data
sudo mount /dev/disk/by-id/DEVICE_ID /data

# Kiểm tra
findmnt /data
df -hT /data
~~~

Với volume cần partition table, tạo partition bằng công cụ phù hợp như parted hoặc fdisk, sau đó tạo filesystem trên partition, ví dụ /dev/nvme1n1p1. Việc chọn GPT/MBR, alignment và kích thước partition cần theo yêu cầu hệ điều hành và dung lượng.

### 2.3. Mount tự động sau reboot

Để filesystem tự mount sau khi khởi động, Linux thường dùng /etc/fstab. Nên tham chiếu UUID hoặc định danh ổn định thay vì tên /dev/sdX có thể thay đổi.

~~~bash
sudo blkid
~~~

Ví dụ một dòng cấu hình:

~~~fstab
UUID=FILESYSTEM_UUID  /data  ext4  defaults,nofail  0  2
~~~

Tùy chọn **nofail** có thể giúp máy tiếp tục khởi động khi volume tùy chọn không sẵn sàng, nhưng không phù hợp với mọi mount point. Nếu ứng dụng bắt buộc phải có /data, cần cấu hình phụ thuộc dịch vụ để ứng dụng không khởi động khi filesystem chưa mount. Nếu không, ứng dụng có thể ghi nhầm dữ liệu vào thư mục /data trên root filesystem.

Sau khi chỉnh sửa, kiểm tra cấu hình trước reboot:

~~~bash
sudo mount -a
findmnt --verify
~~~

Không thêm một dòng fstab chưa kiểm tra vào máy production; lỗi cú pháp hoặc UUID sai có thể làm quá trình khởi động gặp vấn đề.

### 2.4. Gắn volume trên Windows

Sau khi attach volume ở control plane, Windows có thể cần rescan disk trong Disk Management hoặc công cụ quản trị tương ứng. Với volume mới:

1. Mở Disk Management và xác nhận đúng disk theo dung lượng/trạng thái.
2. Nếu disk mới ở trạng thái Offline hoặc Not Initialized, đưa online và khởi tạo theo chính sách GPT/MBR.
3. Tạo New Simple Volume, chọn kích thước và gán drive letter hoặc mount path.
4. Format bằng filesystem được hỗ trợ, thường là NTFS hoặc ReFS tùy nhu cầu.
5. Đặt nhãn volume, cấu hình quyền NTFS và kiểm tra ứng dụng truy cập.

Nếu volume đã có dữ liệu, không khởi tạo hoặc format lại. Xác minh filesystem, trạng thái disk và ký tự ổ đĩa trước khi đưa vào sử dụng.

## 3. Tháo volume an toàn (detach)

Detach là thao tác tách volume khỏi VM ở control plane. Nếu hệ điều hành hoặc ứng dụng vẫn đang ghi dữ liệu, detach cưỡng bức có thể gây lỗi filesystem, mất dữ liệu hoặc làm hỏng database.

Quy trình an toàn:

1. Xác định ứng dụng, process và mount point đang dùng volume.
2. Ngừng nhận công việc mới và drain request nếu volume phục vụ ứng dụng đang chạy.
3. Hoàn tất transaction, flush dữ liệu hoặc tạo checkpoint theo hướng dẫn của ứng dụng.
4. Dừng dịch vụ có sử dụng volume nếu cần.
5. Xác minh không còn process giữ file hoặc current working directory trên mount point.
6. Unmount filesystem trong guest OS.
7. Xác minh thiết bị không còn mount và không có I/O đang diễn ra.
8. Gọi detach từ control plane và chờ trạng thái hoàn tất.
9. Kiểm tra volume vẫn tồn tại, đúng trạng thái và có thể attach lại khi cần.

### 3.1. Kiểm tra trước khi unmount trên Linux

~~~bash
findmnt /data
sudo fuser -vm /data
sudo lsof +f -- /data
~~~

Nếu có process đang dùng filesystem, cần xác định đó là dịch vụ nào và dừng theo quy trình của ứng dụng. Không nên dùng **umount -l** hoặc **umount -f** như cách xử lý mặc định để bỏ qua process còn hoạt động; các tùy chọn này có thể che giấu trạng thái I/O và tạo rủi ro cho dữ liệu.

Sau khi ứng dụng đã dừng và filesystem không còn hoạt động:

~~~bash
sync
sudo umount /data
findmnt /data
~~~

Nếu umount báo target busy, cần tìm process còn sử dụng mount point, kể cả shell đang đứng trong thư mục đó, container bind mount hoặc dịch vụ nền. Giải quyết nguyên nhân rồi thử lại.

### 3.2. Tháo volume trên Windows

Trên Windows, cần đóng ứng dụng và handle đang sử dụng volume, dừng dịch vụ phụ thuộc, rồi đưa disk offline hoặc tháo volume theo hướng dẫn của nhà cung cấp trước khi detach. Không rút disk khi database hoặc ứng dụng vẫn ghi dữ liệu.

Nếu volume có nhiều partition hoặc drive letter, xác minh tất cả mount path đã được giải phóng. Với cluster hoặc shared disk, phải tuân thủ quy trình chuyển quyền sở hữu và khóa cluster trước khi detach khỏi một node.

### 3.3. Volume chứa hệ điều hành

OS/root volume có thể có quy tắc riêng. Nhiều nền tảng không cho detach root disk khi VM đang chạy; một số cho phép thay root disk khi máy đã dừng hoặc theo quy trình phục hồi đặc biệt. Không áp dụng quy trình detach data disk cho root volume nếu chưa xác minh hỗ trợ của nền tảng.

## 4. Mở rộng dung lượng volume (resize)

Resize thường gồm hai lớp:

1. **Tăng dung lượng volume ở control plane:** yêu cầu nhà cung cấp mở rộng block device.
2. **Mở rộng cấu trúc trong guest OS:** cập nhật partition, physical volume, logical volume và filesystem để hệ điều hành sử dụng phần dung lượng mới.

Chỉ tăng size trên console/API không tự động làm filesystem lớn hơn. Ngược lại, mở rộng partition trước khi provider hoàn tất resize có thể không thấy dung lượng mới.

### 4.1. Trước khi resize

Trước khi thay đổi dung lượng:

- Xác minh volume ID, VM, filesystem và dung lượng hiện tại.
- Kiểm tra loại volume có hỗ trợ online resize hay cần dừng VM.
- Kiểm tra dung lượng tối đa, mức tăng tối thiểu và số lần thay đổi trong khoảng thời gian.
- Xem xét IOPS/throughput có thay đổi theo dung lượng hoặc cần cấu hình riêng.
- Xác minh snapshot/backup gần nhất và khả năng restore.
- Kiểm tra filesystem và partition có hỗ trợ mở rộng trực tuyến không.
- Dự trù thời gian hoàn tất thao tác provider và thời gian mở rộng filesystem.
- Thông báo bảo trì nếu workload cần dừng hoặc có thể bị ảnh hưởng hiệu năng.

Snapshot không thay thế backup độc lập. Với dữ liệu quan trọng, nên có backup đã kiểm chứng và quy trình phục hồi trước khi thay đổi cấu trúc đĩa.

### 4.2. Mở rộng volume và filesystem trên Linux

Giả sử volume được mở rộng từ 100 GiB lên 200 GiB ở control plane. Hệ điều hành cần quét lại thiết bị nếu chưa tự nhận dung lượng mới:

~~~bash
lsblk
sudo blockdev --getsize64 /dev/nvme1n1
~~~

Nếu volume dùng filesystem trực tiếp trên toàn bộ block device, có thể mở rộng filesystem theo loại:

~~~bash
# ext4: có thể mở rộng khi filesystem đang mount
sudo resize2fs /dev/nvme1n1

# XFS: mở rộng trên mount point đang sử dụng
sudo xfs_growfs /data
~~~

Lệnh cần áp dụng đúng với thiết bị và filesystem thực tế. **resize2fs** không dùng cho XFS; **xfs_growfs** nhận mount point của filesystem XFS.

### 4.3. Mở rộng partition trước filesystem

Nếu volume có partition, cần mở rộng partition chứa filesystem sau khi block device đã tăng dung lượng. Trên một số hệ Linux, công cụ **growpart** có thể thực hiện việc này:

~~~bash
# Ví dụ: mở rộng partition số 1 trên /dev/nvme1n1
sudo growpart /dev/nvme1n1 1

# Sau đó mở rộng filesystem tương ứng
sudo resize2fs /dev/nvme1n1p1
~~~

Với XFS trên partition, chạy **xfs_growfs** trên mount point sau khi partition đã mở rộng. Cần kiểm tra tên partition thực tế; thiết bị NVMe thường có hậu tố p1, còn một số thiết bị khác dùng dạng s1.

Không chạy lệnh grow trên thiết bị chưa xác định. Nếu partition table hoặc filesystem có lỗi, dừng thao tác và kiểm tra backup trước khi tiếp tục.

### 4.4. Mở rộng volume dùng LVM

Với Linux Logical Volume Manager (LVM), chuỗi cấu trúc thường là:

**Volume block device → Partition (nếu có) → Physical Volume (PV) → Volume Group (VG) → Logical Volume (LV) → Filesystem**

Sau khi provider tăng dung lượng, có thể cần mở rộng partition, sau đó cập nhật PV và LV:

~~~bash
# Xác minh cấu trúc trước
sudo pvs
sudo vgs
sudo lvs

# Nếu PV nằm trên partition, mở rộng partition trước
# Sau đó yêu cầu LVM nhận dung lượng mới
sudo pvresize /dev/nvme1n1p1

# Mở rộng LV và filesystem cùng lúc nếu filesystem hỗ trợ
sudo lvextend -r -L +50G /dev/vg_data/lv_app
~~~

Ví dụ trên chỉ phù hợp khi volume group còn đủ extents và đường dẫn PV/LV đúng. **lvextend -r** gọi công cụ resize filesystem phù hợp; cần kiểm tra output và xác minh dung lượng sau thao tác. Nếu không dùng tùy chọn -r, phải tự mở rộng filesystem sau khi LV tăng.

### 4.5. Mở rộng volume trên Windows

Sau khi provider mở rộng disk:

1. Rescan Disks trong Disk Management hoặc công cụ quản trị.
2. Xác minh dung lượng mới xuất hiện dưới dạng Unallocated space liền kề partition cần mở rộng.
3. Dùng Extend Volume nếu bố cục disk và filesystem hỗ trợ.
4. Xác minh dung lượng, filesystem và trạng thái volume.

Nếu có nhiều partition, recovery partition hoặc layout đặc biệt nằm giữa vùng trống và partition dữ liệu, thao tác Extend có thể không khả dụng. Không xóa partition chỉ để tạo vùng trống liền kề nếu chưa xác định rõ vai trò và khả năng phục hồi.

## 5. Shrink volume và thay đổi loại volume

Mở rộng thường được hỗ trợ phổ biến hơn thu nhỏ. Nhiều dịch vụ block storage không cho giảm dung lượng volume trực tiếp vì việc này có thể cắt bỏ dữ liệu đang nằm ở cuối block device.

Nếu cần giảm dung lượng:

1. Tạo volume mới có dung lượng phù hợp.
2. Tạo filesystem và mount trên máy đích.
3. Sao chép dữ liệu bằng công cụ phù hợp, giữ quyền, owner, ACL và metadata.
4. Tạm dừng ghi hoặc dùng cơ chế đồng bộ cuối để tránh mất cập nhật.
5. Xác minh checksum, số lượng file, quyền và ứng dụng.
6. Chuyển mount hoặc cấu hình ứng dụng sang volume mới.
7. Giữ volume cũ trong thời gian rollback trước khi xóa theo chính sách.

Không dùng resize volume để thu nhỏ filesystem nếu nhà cung cấp không hỗ trợ shrink hoặc chưa kiểm tra giới hạn của filesystem. Thay đổi loại volume, IOPS hoặc throughput cũng có thể có điều kiện và thời gian áp dụng riêng; cần xem trạng thái modify/optimization trước khi thực hiện thay đổi tiếp theo.

## 6. Snapshot, backup và tính nhất quán dữ liệu

Snapshot thường là bản chụp volume ở một thời điểm theo cơ chế của nhà cung cấp. Tính nhất quán của snapshot phụ thuộc việc ứng dụng và hệ điều hành có đang ghi dữ liệu khi chụp hay không.

Phân biệt:

- **Crash-consistent snapshot:** tương tự trạng thái sau khi hệ thống mất điện đột ngột; filesystem hoặc ứng dụng có thể cần recovery khi khôi phục.
- **Filesystem-consistent snapshot:** hệ thống tệp được flush hoặc freeze theo cơ chế hỗ trợ trước khi snapshot.
- **Application-consistent backup:** ứng dụng được phối hợp để đưa dữ liệu về trạng thái có thể phục hồi, ví dụ database checkpoint hoặc backup API.

Với database hoặc hệ thống nhiều volume, snapshot từng volume ở thời điểm khác nhau có thể tạo ra một tập dữ liệu không đồng bộ. Cần dùng cơ chế snapshot nhất quán đa volume hoặc backup ở cấp ứng dụng nếu workload yêu cầu.

Quy trình snapshot có kiểm soát:

1. Kiểm tra ứng dụng và loại volume hỗ trợ snapshot.
2. Flush dữ liệu hoặc gọi cơ chế quiesce/checkpoint theo hướng dẫn ứng dụng.
3. Tạo snapshot hoặc backup.
4. Chờ trạng thái hoàn tất và xác minh metadata.
5. Ghi retention, encryption key và quyền truy cập.
6. Thử restore định kỳ vào volume hoặc môi trường cách ly.

Không nên coi việc tạo snapshot thành công là bằng chứng backup có thể phục hồi. Chỉ thử restore mới xác minh được quy trình khôi phục đầu cuối.

## 7. Mã hóa, quyền truy cập và bảo vệ volume

Volume có thể chứa dữ liệu ứng dụng, thông tin người dùng hoặc dữ liệu nhạy cảm. Cần áp dụng bảo vệ từ lúc tạo đến khi xóa:

- Bật mã hóa at rest theo chính sách; xác minh khóa do provider quản lý hay customer-managed key.
- Giới hạn quyền attach, detach, snapshot, copy và delete theo IAM/RBAC.
- Không chia sẻ volume hoặc snapshot sang tài khoản khác nếu chưa kiểm soát quyền.
- Dùng encryption key có chính sách rotation, backup và quyền sử dụng phù hợp.
- Bảo vệ dữ liệu khi truyền qua mạng theo cơ chế mã hóa mà nền tảng hỗ trợ.
- Ghi log thao tác volume và thay đổi quyền.
- Xóa hoặc hủy khóa theo quy trình lưu giữ dữ liệu, tránh làm dữ liệu cần phục hồi trở nên không thể giải mã.

Detach volume không xóa dữ liệu và cũng không thu hồi quyền truy cập snapshot. Khi bàn giao volume cho nhóm khác, cần xem xét xóa dữ liệu, tạo volume mới từ image sạch hoặc dùng quy trình sanitize được tổ chức phê duyệt.

## 8. Gắn cùng một volume vào nhiều máy

Một số dịch vụ cung cấp multi-attach hoặc shared block storage, nhưng việc nhiều máy cùng truy cập block device không tự động làm filesystem an toàn.

Nếu hai máy cùng mount một filesystem như ext4 hoặc XFS ở chế độ đọc/ghi thông thường, mỗi kernel có thể cập nhật metadata độc lập và gây hỏng filesystem. Multi-attach cần filesystem cluster-aware, cơ chế distributed lock hoặc ứng dụng được thiết kế để truy cập block device đồng thời.

Trước khi dùng shared volume:

- Kiểm tra provider và loại volume có hỗ trợ multi-attach không.
- Xác minh giới hạn số VM, zone, loại instance và chế độ read/write.
- Dùng clustered filesystem hoặc cơ chế khóa phù hợp.
- Xác định node sở hữu quyền ghi và quy trình fencing khi node lỗi.
- Kiểm thử split-brain, mất kết nối và khôi phục node.

Nếu mục tiêu là chia sẻ file giữa nhiều máy, file storage như NFS/SMB thường phù hợp hơn block volume gắn nhiều nơi, tùy yêu cầu latency và throughput.

## 9. Theo dõi hiệu năng và chẩn đoán lỗi volume

Sau attach, resize hoặc thay đổi loại volume, cần theo dõi cả phía provider và hệ điều hành.

| Nhóm chỉ số | Ý nghĩa | Dấu hiệu cần điều tra |
| --- | --- | --- |
| IOPS | Số thao tác đọc/ghi mỗi giây | Đạt trần provisioned hoặc instance limit |
| Throughput | Dữ liệu đọc/ghi mỗi giây | Đạt trần volume hoặc trần tổng ở VM |
| Read/write latency | Thời gian hoàn tất I/O | p95/p99 tăng, ứng dụng chờ đĩa |
| Queue depth | Số I/O đang chờ hoặc xử lý | Hàng đợi tăng kéo dài |
| Burst balance/credit | Khả năng dùng hiệu năng burst nếu dịch vụ có | Credit cạn và hiệu năng giảm |
| Filesystem capacity | Dung lượng đã dùng và còn trống | Disk full, inode exhaustion |
| I/O wait | Thời gian CPU chờ I/O | Workload bị giới hạn bởi storage |
| Disk errors | Lỗi thiết bị hoặc filesystem | Reset, timeout, read/write error |

Trên Linux có thể dùng:

~~~bash
lsblk -f
df -hT
df -i
iostat -xz 1
findmnt
dmesg | tail -n 100
~~~

**df -hT** cho biết dung lượng và loại filesystem; **df -i** kiểm tra inode; **iostat** giúp quan sát IOPS, throughput, queue và thời gian chờ nếu gói sysstat được cài. Metric của nhà cung cấp vẫn cần thiết vì một số giới hạn nằm ở tầng storage backend hoặc instance mà guest OS không nhìn thấy.

Các triệu chứng phổ biến:

- **Volume attach thành công nhưng không thấy trong OS:** kiểm tra rescan, driver, quyền, trạng thái operation và mapping thiết bị.
- **Thấy disk nhưng không mount được:** xác minh filesystem, partition, UUID, trạng thái read-only và lỗi kernel.
- **Sau reboot mount sai volume:** kiểm tra fstab, UUID và dependency của dịch vụ.
- **Resize ở console nhưng dung lượng OS không đổi:** rescan block device, mở rộng partition/PV/LV rồi filesystem.
- **Disk full dù còn dung lượng block:** kiểm tra inode, filesystem reserved space và mount point thực tế.
- **Detach báo busy:** tìm process, container hoặc shell còn sử dụng mount point.
- **I/O chậm:** đối chiếu IOPS, throughput, latency, queue depth, burst credit và giới hạn ở cấp VM.

## 10. Ví dụ: mở rộng data volume cho ứng dụng Linux

Một máy ảo chạy dịch vụ xử lý đơn hàng có data volume 100 GiB gắn tại /data. Khi dung lượng sử dụng tăng đến ngưỡng cảnh báo, nhóm vận hành cần tăng lên 200 GiB mà không làm mất dữ liệu.

Quy trình:

1. Xác minh volume ID, filesystem, partition và mount point bằng lsblk, findmnt và df.
2. Kiểm tra backup gần nhất và khả năng restore; thông báo nếu có thể xuất hiện độ trễ I/O trong lúc thay đổi.
3. Tăng dung lượng volume ở control plane và chờ trạng thái modify hoàn tất.
4. Rescan thiết bị trong guest nếu OS chưa nhận dung lượng mới.
5. Nếu có partition, mở rộng partition tương ứng; nếu dùng LVM, mở rộng PV và LV theo thứ tự.
6. Mở rộng filesystem: dùng resize2fs cho ext4 hoặc xfs_growfs cho XFS.
7. Xác minh df -hT /data, quyền truy cập và khả năng đọc/ghi của ứng dụng.
8. Theo dõi I/O latency, queue depth và log kernel sau thay đổi.
9. Cập nhật hồ sơ tài nguyên, dung lượng cảnh báo và kế hoạch tăng trưởng tiếp theo.

Nếu bước mở rộng filesystem thất bại, dừng các thao tác tiếp theo và giữ volume ở trạng thái hiện tại. Thu thập output, log kernel và metadata; không format lại volume hoặc tạo filesystem mới để cố khắc phục. Khôi phục từ backup hoặc nhờ hỗ trợ nền tảng khi cấu trúc filesystem có dấu hiệu lỗi.

## 11. Tự động hóa vòng đời volume

IaC và automation giúp chuẩn hóa cách tạo, gắn, mở rộng và bảo vệ volume. Một định nghĩa tài nguyên có thể mô tả dung lượng, loại volume, mã hóa, tag, snapshot policy và liên kết VM. Tuy nhiên, thay đổi trong guest OS như partition, filesystem và mount thường cần cloud-init, configuration management hoặc script riêng.

Một workflow tự động nên chia thành các giai đoạn:

1. **Provision:** tạo volume với encryption, zone, loại hiệu năng và tag đúng chuẩn.
2. **Attach:** gắn vào VM và chờ provider hoàn tất.
3. **Discover:** xác định thiết bị bằng ID/serial ổn định.
4. **Initialize:** chỉ với volume mới, tạo partition/filesystem theo cấu hình khai báo.
5. **Mount:** tạo mount point, quyền và cấu hình tự mount.
6. **Verify:** kiểm tra filesystem, dung lượng, quyền và I/O.
7. **Monitor:** cảnh báo dung lượng, inode, latency và giới hạn hiệu năng.
8. **Detach/cleanup:** drain workload, unmount và detach theo quy trình.

Automation cần idempotent: chạy lại không được format nhầm volume đang chứa dữ liệu hoặc tạo thêm filesystem không cần thiết. Hãy lưu metadata xác nhận volume đã được khởi tạo, kiểm tra filesystem signature trước khi format và yêu cầu điều kiện rõ ràng cho mọi thao tác phá hủy.

Ví dụ khai báo mang tính khái niệm:

~~~yaml
volume:
  name: orders-data
  size_gib: 200
  type: general-purpose-ssd
  availability_zone: zone-a
  encrypted: true
  delete_on_instance_termination: false
  tags:
    application: orders
    environment: production
    owner: platform-team
mount:
  device_identity: provider-volume-id
  path: /data
  filesystem: xfs
  initialize_only_if_empty: true
~~~

Tên trường và loại volume phụ thuộc provider. Cần xác minh chính sách delete_on_instance_termination hoặc tùy chọn tương đương để bảo đảm vòng đời disk đúng mong muốn.

## 12. Checklist trước và sau mỗi thao tác

**Trước khi attach**

- [ ] Đúng volume ID, VM, vùng và loại thiết bị.
- [ ] Volume chưa bị gắn trái với chính sách hoặc vượt giới hạn attach.
- [ ] Xác định rõ volume mới hay volume đã có dữ liệu.
- [ ] Đã kiểm tra mã hóa, quyền và chính sách lưu giữ.

**Trước khi detach**

- [ ] Ứng dụng đã drain và hoàn tất transaction/checkpoint.
- [ ] Không còn process sử dụng mount point.
- [ ] Đã flush và unmount filesystem sạch.
- [ ] Đã xác định dữ liệu local/ephemeral có bị mất hay không.

**Trước khi resize**

- [ ] Đúng volume và dung lượng đích.
- [ ] Đã kiểm tra giới hạn, loại volume và hỗ trợ online/offline.
- [ ] Có backup/snapshot phù hợp và đã biết cách restore.
- [ ] Đã xác định chuỗi partition, LVM và filesystem cần mở rộng.

**Sau thao tác**

- [ ] Control plane báo trạng thái hoàn tất.
- [ ] OS nhận đúng thiết bị và dung lượng.
- [ ] Filesystem mount đúng vị trí, quyền và dung lượng.
- [ ] Ứng dụng đọc/ghi bình thường.
- [ ] Metric I/O, log và cảnh báo không có dấu hiệu bất thường.
- [ ] Metadata và hồ sơ tài nguyên được cập nhật.

## 13. Nguyên tắc vận hành

1. **Xác minh danh tính volume:** dùng volume ID, serial hoặc UUID thay vì chỉ dựa vào tên thiết bị có thể thay đổi.
2. **Phân biệt loại lưu trữ:** biết dữ liệu nào nằm trên block volume bền vững và dữ liệu nào nằm trên local/ephemeral disk.
3. **Attach có kiểm soát:** kiểm tra vùng, giới hạn, quyền và trạng thái volume trước khi gắn.
4. **Detach sau khi quiesce:** drain ứng dụng, flush dữ liệu, unmount sạch rồi mới detach ở control plane.
5. **Resize đủ hai lớp:** mở rộng block device, sau đó partition/LVM và filesystem trong guest OS.
6. **Không format volume có dữ liệu:** chỉ khởi tạo filesystem khi đã xác nhận volume mới và trống.
7. **Snapshot không thay backup:** kiểm tra tính nhất quán và thử restore định kỳ.
8. **Bảo vệ truy cập:** mã hóa, IAM/RBAC, quản lý khóa và log thao tác volume.
9. **Multi-attach cần cơ chế phối hợp:** dùng clustered filesystem hoặc ứng dụng hỗ trợ chia sẻ block; không mount ghi đồng thời tùy tiện.
10. **Đo sau thay đổi:** xác minh dung lượng, IOPS, throughput, latency và khả năng phục vụ của ứng dụng.

Gắn, tháo và mở rộng volume là các thao tác ở cả tầng đám mây lẫn hệ điều hành. Khi phối hợp đúng hai tầng, nhận diện chính xác thiết bị, bảo vệ dữ liệu và xác minh sau mỗi thay đổi, đội vận hành có thể tăng năng lực lưu trữ mà vẫn duy trì tính toàn vẹn, tính sẵn sàng và chi phí trong giới hạn dự kiến.
