# Mount, filesystem và quyền truy cập dữ liệu trong máy

Sau khi một volume hoặc dịch vụ lưu trữ được gắn vào máy ảo, hệ điều hành vẫn cần nhận diện thiết bị, chuẩn bị filesystem, mount vào một đường dẫn và cấp quyền cho tiến trình sử dụng. Nếu một bước sai, ứng dụng có thể không nhìn thấy dữ liệu, ghi nhầm vào đĩa hệ thống, không khởi động sau reboot hoặc vô tình cho người dùng không phù hợp quyền đọc và sửa tệp.

Bài học này trình bày cách mount block storage và network file share trên Linux/Windows, cấu hình mount bền vững qua lần khởi động, quản lý owner/group/ACL và bảo vệ dữ liệu. Nội dung cũng phân biệt filesystem với object storage, giải thích các lỗi thường gặp và đưa ra quy trình vận hành an toàn cho workload trên đám mây.

## 1. Từ storage đến đường dẫn mà ứng dụng sử dụng

Dịch vụ lưu trữ đám mây cung cấp dữ liệu theo nhiều mô hình. Cách hệ điều hành nhìn thấy và truy cập dữ liệu phụ thuộc loại dịch vụ.

| Loại lưu trữ | Cách máy truy cập | Ví dụ sử dụng | Cần mount filesystem? |
|---|---|---|---|
| Block storage | Thiết bị block được gắn vào VM | Volume chứa database, filesystem ứng dụng, boot disk | Có, sau khi tạo hoặc nhận diện filesystem |
| File storage | Chia sẻ tệp qua giao thức như NFS hoặc SMB | Thư mục dùng chung giữa nhiều máy, home directory, shared content | Có, mount share vào cây thư mục hoặc drive |
| Object storage | API hoặc SDK thao tác object theo bucket/container và key | Backup, media, log, artifact, data lake | Không bắt buộc; có thể dùng gateway/FUSE nhưng có giới hạn ngữ nghĩa |

### Block storage

Block volume cung cấp các khối dữ liệu để hệ điều hành sử dụng như một thiết bị đĩa. Trên Linux, thiết bị có thể xuất hiện dưới tên như **/dev/nvme1n1** hoặc **/dev/sdb**; trên Windows, nó xuất hiện như một disk mới.

Một volume mới thường cần được khởi tạo partition table và filesystem trước khi mount. Volume đã có dữ liệu có thể đã chứa filesystem; format lại sẽ phá hủy dữ liệu.

Ví dụ dịch vụ block storage trên cloud gồm Amazon EBS, Azure Managed Disks và Google Persistent Disk. Khả năng attach, detach, multi-attach, vùng sẵn sàng và hiệu năng phụ thuộc loại volume và cấu hình cụ thể.

### File storage

File storage cung cấp một namespace tệp dùng chung qua mạng. Máy khách mount share để ứng dụng truy cập qua đường dẫn như thư mục cục bộ.

Các giao thức thường gặp:

- NFS, phổ biến trong môi trường Linux/Unix.
- SMB, phổ biến trong Windows và cũng được Linux hỗ trợ qua CIFS.
- Các dịch vụ managed file storage có thể hỗ trợ một hoặc nhiều giao thức trên.

Ví dụ gồm Amazon EFS, Azure Files và Google Cloud Filestore. Cần kiểm tra giao thức, phiên bản, cơ chế xác thực, quyền chia sẻ và giới hạn kết nối của dịch vụ.

### Object storage

Object storage tổ chức dữ liệu thành object trong bucket hoặc container. Ứng dụng thường truy cập bằng HTTPS API, SDK hoặc công cụ đồng bộ. Object storage không cung cấp đầy đủ hành vi của filesystem POSIX như khóa tệp, rename nguyên tử, quyền owner/group và thao tác thư mục theo cách filesystem truyền thống.

Một số công cụ cho phép mount object storage qua FUSE hoặc gateway. Cách này hữu ích cho một số quy trình đọc dữ liệu, nhưng không nên mặc định phù hợp với database hoặc ứng dụng cần thao tác filesystem POSIX chính xác. Cần hiểu cache, consistency, locking, rename, permission mapping và hành vi khi mất kết nối.

## 2. Filesystem và mount point

Filesystem là cấu trúc tổ chức dữ liệu trên thiết bị lưu trữ. Nó quản lý thư mục, tệp, metadata, quyền và cách cấp phát không gian.

Một số filesystem thường gặp:

- **ext4:** phổ biến trên Linux, có journaling và phù hợp với nhiều workload máy chủ.
- **XFS:** thường dùng cho volume lớn và workload có thông lượng tốt; công cụ sửa chữa khác ext4.
- **NTFS:** filesystem phổ biến của Windows, hỗ trợ ACL và nhiều tính năng quản trị.
- **ReFS:** được dùng trong một số môi trường Windows và workload phù hợp; cần kiểm tra tính năng được hệ điều hành hỗ trợ.
- **NFS/SMB:** là giao thức chia sẻ file qua mạng, không phải filesystem cục bộ được format lên block volume.

### Mount point là gì?

Trên Linux, mount point là thư mục trong cây filesystem nơi một filesystem khác được gắn vào. Ví dụ, volume dữ liệu có thể được mount tại **/data**, còn file share tại **/mnt/shared**.

Khi mount một filesystem vào thư mục đã có nội dung, nội dung cũ của thư mục đó bị che khuất trong thời gian mount. Dữ liệu cũ vẫn nằm trên filesystem cha, nhưng ứng dụng không nhìn thấy nó qua đường dẫn đó cho đến khi unmount. Vì vậy, nên chọn mount point riêng và kiểm tra thư mục trước khi mount.

Trên Windows, volume thường được gán drive letter như **D:** hoặc có thể gắn vào một thư mục NTFS rỗng. Việc dùng mount folder thay cho drive letter có thể giúp tổ chức đường dẫn nhất quán hơn.

### Phân biệt attach và mount

- **Attach:** nền tảng cloud kết nối volume với VM.
- **Discover:** hệ điều hành nhận diện thiết bị mới.
- **Partition:** tạo hoặc đọc bảng phân vùng nếu cần.
- **Format:** tạo filesystem mới trên phân vùng hoặc thiết bị.
- **Mount:** gắn filesystem vào đường dẫn để tiến trình truy cập.

Attach thành công chưa có nghĩa dữ liệu đã sẵn sàng. Tương tự, volume có thể đã attach nhưng chưa mount, hoặc mount thành công nhưng quyền ứng dụng chưa đúng.

## 3. Quy trình an toàn khi mount block volume trên Linux

### Bước 1: xác định đúng thiết bị

Sau khi attach volume từ cloud console hoặc API, kiểm tra thiết bị:

~~~sh
lsblk -o NAME,SIZE,TYPE,FSTYPE,UUID,MOUNTPOINTS
sudo blkid
findmnt
~~~

Đối chiếu dung lượng, loại thiết bị, filesystem và thông tin volume trong cloud console. Tên thiết bị **/dev/sdX** hoặc **/dev/nvmeXnY** có thể thay đổi giữa lần boot hoặc tùy loại instance. Không dựa duy nhất vào tên thiết bị để nhận diện ổ dữ liệu.

Nếu volume đã có filesystem và dữ liệu, không chạy lệnh format. Có thể mount filesystem hiện có sau khi xác minh đúng thiết bị và trạng thái.

### Bước 2: kiểm tra volume mới hay volume đã có dữ liệu

Với volume mới, trống và đã xác nhận chính xác, có thể tạo partition table và filesystem theo thiết kế. Ví dụ sau chỉ dành cho một thiết bị mới, không chứa dữ liệu cần giữ:

~~~sh
# Chỉ chạy sau khi xác minh /dev/nvme1n1 là volume mới, trống.
sudo parted /dev/nvme1n1 --script mklabel gpt
sudo parted /dev/nvme1n1 --script mkpart primary ext4 1MiB 100%
sudo mkfs.ext4 /dev/nvme1n1p1
~~~

Tên partition trong ví dụ có thể khác theo driver và thiết bị. Một số volume được dùng trực tiếp không cần partition; một số thiết kế dùng LVM hoặc nhiều partition. Hãy làm theo chuẩn của hệ thống.

**Cảnh báo:** **mkfs**, **parted mklabel** và các thao tác format có thể ghi đè metadata và làm mất khả năng truy cập dữ liệu hiện có. Luôn xác minh volume, backup và trạng thái trước khi thực hiện. Không chạy các lệnh này trên volume đang chứa dữ liệu production.

### Bước 3: tạo mount point và mount

~~~sh
sudo mkdir -p /data
sudo mount UUID=REPLACE_WITH_FILESYSTEM_UUID /data
findmnt /data
df -hT /data
~~~

Thay **REPLACE_WITH_FILESYSTEM_UUID** bằng UUID thực tế lấy từ **blkid** hoặc **lsblk -f**. Dùng UUID hoặc đường dẫn ổn định tương đương giúp tránh phụ thuộc vào thứ tự tên thiết bị.

Nếu volume có filesystem XFS, lệnh mount vẫn tương tự; hệ điều hành tự nhận diện filesystem. Cần cài công cụ filesystem tương ứng nếu image tối giản chưa có.

### Bước 4: kiểm tra quyền và khả năng ghi

Sau khi mount, filesystem có thể thuộc **root**. Tạo nhóm hoặc user ứng dụng theo chính sách rồi cấp quyền cho đúng thư mục.

Ví dụ:

~~~sh
sudo groupadd --force appdata
sudo usermod -aG appdata appuser
sudo chown root:appdata /data
sudo chmod 2770 /data
~~~

Đăng nhập lại hoặc khởi động lại tiến trình để user nhận nhóm mới. Bit setgid trên thư mục (**2** trong **2770**) giúp file và thư mục con mới thường kế thừa group của thư mục cha trên filesystem POSIX.

Kiểm tra bằng đúng danh tính ứng dụng:

~~~sh
sudo -u appuser test -r /data && echo "readable"
sudo -u appuser test -w /data && echo "writable"
namei -l /data
~~~

Không kiểm tra chỉ bằng tài khoản root vì root có thể đọc/ghi dù user ứng dụng không có quyền.

## 4. Cấu hình mount bền vững qua reboot với /etc/fstab

Lệnh **mount** thông thường chỉ áp dụng cho phiên hiện tại. Muốn filesystem tự mount khi khởi động, Linux thường dùng **/etc/fstab**.

Cấu trúc mỗi dòng:

~~~text
<source> <mount-point> <filesystem-type> <options> <dump> <pass>
~~~

Ví dụ cho volume ext4:

~~~fstab
UUID=11111111-2222-3333-4444-555555555555 /data ext4 defaults,nofail,x-systemd.device-timeout=30s 0 2
~~~

UUID trong ví dụ chỉ là giá trị minh họa. Phải thay bằng UUID thực tế. Với XFS, trường kiểm tra filesystem thường đặt **0** ở vị trí cuối thay vì dùng thứ tự fsck như ext4; làm theo hướng dẫn của filesystem và bản phân phối.

### Ý nghĩa các trường

- **source:** UUID, LABEL, thiết bị hoặc nguồn share.
- **mount-point:** thư mục đích.
- **filesystem-type:** ext4, xfs, nfs4, cifs...
- **options:** tùy chọn mount như **defaults**, **ro**, **rw**, **_netdev**, **nofail**.
- **dump:** thường dùng **0** trên hệ thống hiện đại nếu không dùng dump.
- **pass:** thứ tự kiểm tra filesystem khi boot; filesystem gốc thường có quy tắc riêng.

### Kiểm tra fstab trước khi reboot

Sau khi sửa file, chạy:

~~~sh
sudo findmnt --verify --verbose
sudo mount -a
findmnt /data
~~~

**mount -a** thử mount các mục phù hợp trong fstab. Nếu có lỗi, sửa trước khi reboot. Một dòng sai có thể làm boot chậm hoặc khiến máy vào chế độ emergency tùy cấu hình.

### Chọn nofail cẩn thận

**nofail** cho phép hệ thống tiếp tục boot nếu một filesystem không mount được trong một số cấu hình systemd. Điều này có thể hữu ích với volume dữ liệu không bắt buộc cho việc boot hệ điều hành.

Tuy nhiên, nếu ứng dụng cần **/data** mà mount thất bại, service có thể ghi nhầm vào thư mục **/data** trên filesystem gốc. Để tránh tình huống này, service nên khai báo phụ thuộc mount, ví dụ trong systemd unit:

~~~ini
[Unit]
Description=Example application
RequiresMountsFor=/data
~~~

Khi đó systemd biết service cần mount point này trước khi khởi chạy. Cần kiểm tra chính sách fail/boot của hệ thống để chọn **nofail** phù hợp.

### Mount tự động theo nhu cầu

Với một số filesystem ít được dùng, có thể cân nhắc **x-systemd.automount** để systemd tạo automount unit và chỉ mount khi có truy cập. Điều này có thể giảm thời gian boot hoặc xử lý share mạng tạm thời, nhưng cần hiểu timeout, trạng thái khi server mất kết nối và tác động đến ứng dụng.

Không dùng automount cho mọi volume một cách máy móc. Workload cần filesystem sẵn sàng ngay khi service start nên có dependency rõ ràng.

## 5. Tùy chọn mount và ảnh hưởng bảo mật

Tùy chọn mount quyết định cách filesystem được truy cập. Một số lựa chọn phổ biến:

| Tùy chọn | Ý nghĩa | Khi cân nhắc |
|---|---|---|
| **ro** | Chỉ đọc | Dataset tham chiếu hoặc nội dung không được phép sửa |
| **rw** | Đọc/ghi | Volume ứng dụng cần ghi dữ liệu |
| **noatime** | Không cập nhật access time theo cách thông thường | Có thể giảm ghi metadata cho workload phù hợp |
| **nosuid** | Không tôn trọng set-user-ID/set-group-ID trên mount | Thư mục dữ liệu không cần chương trình có đặc quyền |
| **nodev** | Không cho diễn giải device node trên mount | Phần lớn vùng dữ liệu ứng dụng |
| **noexec** | Không thực thi chương trình trực tiếp từ mount | Thư mục chứa dữ liệu hoặc upload không tin cậy |
| **nofail** | Không để lỗi mount nhất thiết chặn boot | Volume tùy chọn, khi service có dependency riêng |
| **_netdev** | Đánh dấu filesystem phụ thuộc mạng | NFS/SMB và filesystem mạng |

Các tùy chọn **nosuid**, **nodev** và **noexec** có thể tăng an toàn cho vùng dữ liệu, nhưng có thể làm hỏng ứng dụng nếu phần mềm cần thực thi file hoặc dùng device node trên mount đó. Hãy kiểm tra chức năng trước khi áp dụng.

**noexec** cũng không phải ranh giới bảo mật tuyệt đối: interpreter vẫn có thể đọc nội dung script từ một filesystem không cho execute trực tiếp. Cần kết hợp quyền truy cập, kiểm soát nguồn file và sandbox phù hợp.

## 6. Quản lý owner, group và quyền POSIX

Trên filesystem Linux hỗ trợ quyền POSIX, mỗi file hoặc thư mục thường có:

- Owner user.
- Owner group.
- Quyền đọc (**r**), ghi (**w**) và thực thi/traverse (**x**) cho owner, group và others.

Ví dụ kết quả **ls -l**:

~~~text
drwxrws---  root appdata  /data
-rw-r-----  appuser appdata report.csv
~~~

Với thư mục, quyền **x** cho phép traverse vào thư mục; quyền **r** cho phép liệt kê tên mục; quyền **w** cho phép tạo/xóa/đổi tên mục nếu kết hợp với **x**.

### chmod và chown

~~~sh
sudo chown appuser:appdata /data/report.csv
sudo chmod 0640 /data/report.csv
sudo chmod 2770 /data
~~~

Dùng **chown** để đổi owner/group và **chmod** để thay đổi mode bits. Tránh dùng **chmod -R 777** để xử lý lỗi permission. Lệnh đó cấp quyền rộng cho mọi user và có thể khiến dữ liệu bị đọc, sửa hoặc xóa trái phép.

### Umask

Umask quyết định các quyền bị loại bỏ khi tạo file hoặc thư mục mới. Ví dụ, umask **0027** thường tạo file tối đa **0640** và thư mục tối đa **0750**, tùy mode mà ứng dụng yêu cầu.

Có thể cấu hình umask trong service hoặc môi trường người dùng. Không nên chỉ dựa vào umask nếu nhiều ứng dụng dùng chung thư mục; hãy thiết kế owner/group và default ACL rõ ràng.

### Default ACL

POSIX ACL cho phép cấp quyền chi tiết cho nhiều user/group hơn bộ ba owner/group/others.

Ví dụ:

~~~sh
sudo setfacl -m g:analytics:r-x /data
sudo setfacl -d -m g:analytics:r-x /data
getfacl /data
~~~

Dòng đầu cấp quyền cho group **analytics** trên thư mục hiện tại; dòng thứ hai đặt default ACL để mục mới tạo bên trong có thể kế thừa quyền phù hợp. Quyền hiệu lực còn phụ thuộc ACL mask và mode của đối tượng. Dùng **getfacl** để xác minh kết quả.

Không phải filesystem hoặc giao thức mạng nào cũng hỗ trợ ACL giống nhau. NFS, SMB, NTFS và filesystem cục bộ có mô hình quyền riêng; cần hiểu cách mapping giữa client và server.

## 7. Quyền truy cập trên NFS

NFS cho phép nhiều máy Linux mount cùng một export. Quyền truy cập thường kết hợp export policy ở server, danh tính UID/GID và permission trên filesystem phía server.

### UID/GID phải nhất quán

Trong mô hình POSIX truyền thống, file lưu UID/GID dạng số. Nếu user **appuser** có UID 1001 trên một VM nhưng UID khác trên VM khác, quyền có thể không như mong đợi khi cùng mount NFS.

Tổ chức nên dùng identity directory hoặc chuẩn hóa UID/GID cho các user/group dùng chung. Không chỉ dựa vào tên user hiển thị; cần kiểm tra ID số.

### Root squash

NFS server thường có thể bật **root_squash**, ánh xạ quyền root từ client thành user không đặc quyền trên server. Điều này ngăn root của một VM tự động trở thành root trên filesystem chia sẻ.

Không tắt root squash chỉ để sửa lỗi ghi file. Hãy cấp owner/group phù hợp ở server hoặc dùng danh tính dịch vụ được quản lý.

### Mount NFS trên Linux

Ví dụ mount NFSv4.1:

~~~sh
sudo mkdir -p /mnt/shared
sudo mount -t nfs4 -o vers=4.1,hard,_netdev \
  nfs.example.internal:/exports/team /mnt/shared
findmnt /mnt/shared
~~~

Tên server và export trong ví dụ là giả định. Trước khi mount, kiểm tra DNS, route, firewall/security group và quyền export. NFS thường dùng TCP 2049, nhưng cần xác minh cấu hình giao thức và dịch vụ cụ thể.

Với NFS, tùy chọn **hard** thường được dùng để client tiếp tục thử lại thao tác I/O khi server không phản hồi, giúp tránh lỗi ghi bị trả về sớm trong một số tình huống. Tuy nhiên, tiến trình có thể bị block lâu khi server mất kết nối. Cần thiết kế timeout ở tầng ứng dụng, giám sát và kế hoạch khôi phục. Không đổi sang **soft** một cách tùy tiện vì lỗi I/O được trả về cho ứng dụng có thể gây hỏng dữ liệu nếu phần mềm xử lý không đúng.

### Mount NFS bền vững

Ví dụ fstab:

~~~fstab
nfs.example.internal:/exports/team /mnt/shared nfs4 rw,hard,_netdev,nofail,x-systemd.automount 0 0
~~~

Cần điều chỉnh theo chính sách mạng, khả năng sẵn sàng và cách ứng dụng sử dụng share. Nếu service bắt buộc có share, khai báo **RequiresMountsFor=/mnt/shared** hoặc dependency phù hợp thay vì để ứng dụng tự tạo thư mục rồi ghi nhầm lên filesystem gốc.

## 8. Quyền truy cập trên SMB/CIFS

SMB thường dùng cho file share Windows và có thể được mount từ Linux bằng CIFS. Quyền hiệu lực có thể chịu tác động đồng thời của share permissions và NTFS ACL trên server. Trong nhiều mô hình, quyền thực tế là quyền hạn chế hơn giữa các lớp.

### Mount SMB trên Linux

Cài gói CIFS utilities phù hợp với bản phân phối, sau đó mount share. Không ghi password trực tiếp trong lệnh hoặc fstab vì có thể lộ qua shell history, process list hoặc file cấu hình.

Ví dụ dùng credentials file:

~~~sh
sudo install -d -m 0755 /mnt/team
sudo install -d -m 0700 /etc/samba
sudo install -m 0600 /dev/null /etc/samba/team.cred
~~~

Tệp credentials cần được điền bằng cơ chế quản lý secret phù hợp và chỉ root được đọc. Ví dụ cấu trúc nội dung, không chứa giá trị thật:

~~~text
username=SERVICE_ACCOUNT
password=RETRIEVED_SECRET
domain=EXAMPLE
~~~

Lệnh mount:

~~~sh
sudo mount -t cifs //files.example.internal/team /mnt/team \
  -o credentials=/etc/samba/team.cred,vers=3.1.1,uid=1001,gid=1001,file_mode=0640,dir_mode=0750
~~~

Tùy chọn **uid**, **gid**, **file_mode** và **dir_mode** ảnh hưởng cách quyền được trình bày trên client trong một số chế độ mount. Khi server dùng ACL và xác thực theo domain, quyền server vẫn là yếu tố quyết định. Kiểm tra phiên bản SMB và chính sách signing/encryption của dịch vụ.

### Mount SMB bền vững

Có thể đặt nguồn share và credentials file trong fstab:

~~~fstab
//files.example.internal/team /mnt/team cifs credentials=/etc/samba/team.cred,vers=3.1.1,_netdev,nofail,x-systemd.automount 0 0
~~~

Không đặt password trực tiếp trong dòng fstab. Bảo vệ credentials file bằng quyền chặt chẽ, giới hạn tài khoản dịch vụ và xoay vòng thông tin xác thực.

## 9. Mount và quyền truy cập trên Windows

### Nhận diện disk mới

Sau khi attach managed disk, dùng PowerShell để kiểm tra:

~~~powershell
Get-Disk
Get-Partition
Get-Volume
~~~

Đối chiếu số disk, dung lượng, trạng thái và thông tin volume với tài nguyên đã attach. Không chỉ dựa vào số disk vì thứ tự có thể khác sau thay đổi hạ tầng.

### Khởi tạo và format volume mới

Ví dụ dưới đây chỉ dành cho disk mới, trống và đã xác minh đúng số disk:

~~~powershell
# Chỉ chạy sau khi xác nhận Disk 2 là disk mới, không chứa dữ liệu.
Initialize-Disk -Number 2 -PartitionStyle GPT

$partition = New-Partition -DiskNumber 2 -UseMaximumSize -AssignDriveLetter
Format-Volume -Partition $partition -FileSystem NTFS -NewFileSystemLabel "AppData"
~~~

**Initialize-Disk** và **Format-Volume** có thể phá hủy cấu trúc hoặc dữ liệu hiện có. Với disk đã chứa dữ liệu, không chạy các lệnh này; hãy xác định filesystem và volume trước khi gán mount point.

### Gán drive letter hoặc mount folder

Windows có thể gán volume vào drive letter như **E:** hoặc mount vào một thư mục NTFS rỗng. Quản lý bằng Disk Management, Storage cmdlets hoặc công cụ phù hợp.

Drive letter thường được duy trì qua reboot, nhưng cần xác minh khi có thay đổi disk hoặc cấu hình máy. Với ứng dụng yêu cầu đường dẫn ổn định, có thể dùng mount folder và quản lý qua inventory.

### NTFS ACL với icacls

Ví dụ cấp quyền Modify cho một service account trên thư mục dữ liệu:

~~~powershell
icacls D:\AppData /grant "EXAMPLE\AppSvc:(OI)(CI)M"
icacls D:\AppData
~~~

**OI** và **CI** cho phép quyền kế thừa xuống file và thư mục con; **M** là Modify. Cần giữ quyền quản trị và SYSTEM theo baseline của tổ chức. Không dùng **/reset** hoặc xóa inheritance trên thư mục production khi chưa hiểu toàn bộ ACL kế thừa.

### Share permissions và NTFS permissions

Với SMB share trên Windows, quyền truy cập từ xa chịu tác động của cả quyền share và NTFS ACL. Một user có quyền Full Control ở share nhưng chỉ Read ở NTFS vẫn bị giới hạn bởi NTFS. Cần kiểm tra từ đúng tài khoản client và server để xác minh quyền hiệu lực.

## 10. Bảo mật filesystem và dữ liệu

Mount chỉ làm dữ liệu xuất hiện trong cây thư mục; nó không tự bảo đảm dữ liệu được bảo vệ. Cần phối hợp nhiều lớp.

### Mã hóa at rest

Dùng mã hóa volume hoặc filesystem theo khả năng của nền tảng:

- Cloud-managed encryption hoặc customer-managed key cho block volume.
- Mã hóa dữ liệu trên file service theo tính năng dịch vụ.
- LUKS hoặc cơ chế mã hóa filesystem khi tổ chức cần tự quản lý lớp mã hóa trong guest.
- Quản lý key policy, rotation và quyền giải mã theo môi trường.

Nếu dùng mã hóa trong guest, cần bảo đảm key có thể truy cập khi boot và có quy trình khôi phục khi VM thay thế. Không lưu passphrase hoặc key material trong image hay fstab.

### Mã hóa in transit

Với file share qua mạng, dùng phiên bản giao thức và cấu hình bảo mật phù hợp. SMB có thể hỗ trợ encryption theo phiên bản/cấu hình; NFS có thể dùng cơ chế bảo vệ danh tính và privacy phù hợp như Kerberos hoặc giải pháp mã hóa mạng do nền tảng hỗ trợ. Không giả định mọi kết nối NFS/SMB đều tự mã hóa.

### Least privilege

- Chỉ mount read-write khi ứng dụng cần ghi.
- Dùng **ro** cho dữ liệu chỉ đọc.
- Cấp owner/group/ACL cho đúng service account.
- Tránh **777** và tránh chạy ứng dụng bằng root.
- Dùng **nosuid**, **nodev**, **noexec** khi tương thích.
- Giới hạn network access tới NFS/SMB bằng security group, firewall và private endpoint.
- Tách thư mục upload không tin cậy khỏi thư mục thực thi.

### SELinux và AppArmor

Ngay cả khi Unix mode bits cho phép truy cập, SELinux hoặc AppArmor vẫn có thể chặn tiến trình. Trên Linux dùng SELinux, kiểm tra context bằng:

~~~sh
ls -Zd /data
sudo ausearch -m AVC -ts recent
~~~

Nếu context sai, dùng policy và công cụ quản lý context như **semanage fcontext** và **restorecon** theo chuẩn của hệ thống. Không tắt SELinux chỉ để làm ứng dụng chạy được.

AppArmor cũng có thể giới hạn đường dẫn mà tiến trình được phép truy cập. Kiểm tra profile và log audit khi gặp lỗi permission dù owner/group có vẻ đúng.

## 11. Filesystem trong container

Container thường dùng filesystem của host và các mount được khai báo khi tạo container hoặc pod.

Một số loại mount:

- Bind mount: gắn một đường dẫn cụ thể từ host vào container.
- Named volume: runtime hoặc orchestrator quản lý vòng đời volume.
- Persistent volume: tài nguyên lưu trữ được điều phối độc lập với vòng đời pod.
- Ephemeral volume: dữ liệu tạm theo vòng đời container hoặc pod.

Cần chú ý UID/GID bên trong container có thể không khớp owner trên host. Container chạy user 10001 nhưng thư mục host thuộc UID 1000 có thể không ghi được. Hãy thiết kế user/group nhất quán hoặc dùng cơ chế permission phù hợp.

Với Kubernetes, PersistentVolume và PersistentVolumeClaim mô tả tài nguyên lưu trữ; StorageClass có thể tự động cấp volume. Access mode mô tả kiểu truy cập mà volume hỗ trợ, nhưng không phải mọi chế độ đều bảo đảm nhiều node có thể ghi đồng thời an toàn. Cần đọc khả năng thực tế của driver và filesystem.

Ví dụ mount read-only trong Pod:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: report-reader
spec:
  containers:
    - name: reader
      image: example/report-reader:1.0
      volumeMounts:
        - name: reports
          mountPath: /reports
          readOnly: true
  volumes:
    - name: reports
      persistentVolumeClaim:
        claimName: reports-pvc
~~~

Ví dụ chỉ minh họa cấu trúc mount; PVC và quyền truy cập cần được tạo theo storage driver, namespace và policy của cluster. Với SELinux, một số runtime cần label hoặc tùy chọn mount tương ứng. Không cấp quyền rộng cho host path chỉ để tránh lỗi permission.

## 12. Quy trình tháo mount và detach volume an toàn

Trước khi detach block volume hoặc ngắt file share, dừng ứng dụng đang sử dụng dữ liệu. Nếu còn tiến trình mở file, unmount có thể báo busy hoặc gây rủi ro nhất quán.

### Trên Linux

~~~sh
sudo fuser -vm /data
sudo lsof +f -- /data
sudo sync
sudo umount /data
findmnt /data
~~~

Chỉ sau khi xác nhận filesystem đã unmount mới detach volume ở cloud console/API. Nếu có nhiều mount hoặc bind mount bên dưới, cần xử lý đúng thứ tự.

Không dùng **umount -f** hoặc lazy unmount như cách mặc định để vượt lỗi busy. Trước hết xác định tiến trình đang sử dụng mount và dừng nó an toàn. Với NFS bị mất kết nối, thao tác có thể bị treo; cần làm theo quy trình khôi phục của dịch vụ.

### Trên Windows

Dừng service và ứng dụng đang dùng volume, đóng handle file, xác minh không còn workload ghi dữ liệu rồi tháo drive letter/mount point hoặc detach disk theo hướng dẫn nền tảng. Không detach disk đang được ứng dụng sử dụng hoặc đang có thao tác ghi chưa hoàn tất.

### Backup và snapshot

Snapshot block volume có thể cung cấp điểm phục hồi ở cấp đĩa. Đối với database hoặc ứng dụng đang ghi, snapshot không tự động bảo đảm tính nhất quán ứng dụng. Cần dùng backup native, flush/quiesce hoặc cơ chế snapshot nhất quán được nền tảng hỗ trợ.

Mount, unmount và detach không thay thế backup. Xác minh định kỳ khả năng restore, quyền khóa mã hóa và thời gian phục hồi.

## 13. Hiệu năng và độ sẵn sàng của mount

Filesystem có thể mount thành công nhưng hiệu năng không đáp ứng workload. Các yếu tố cần xem:

- Loại volume, IOPS và throughput được cấp.
- Queue depth và latency ở cấp block device.
- Filesystem và kích thước block.
- Mẫu truy cập tuần tự/ngẫu nhiên, đọc/ghi.
- Nhiều tiến trình tranh chấp cùng file hoặc thư mục.
- Network latency và băng thông với NFS/SMB.
- Cache của client và server.
- Giới hạn số file mở, inode và metadata operation.
- Kích thước file và số lượng file nhỏ.

Với filesystem mạng, mất kết nối có thể khiến thao tác I/O bị chậm hoặc block. Ứng dụng cần timeout, retry có kiểm soát và xử lý lỗi khi share không khả dụng. Không nên cho service ghi dữ liệu quan trọng vào một thư mục fallback trên root disk khi mount share thất bại.

### Theo dõi dung lượng và inode

Trên Linux:

~~~sh
df -hT
df -i
du -xhd1 /data
findmnt --target /data
~~~

Filesystem có thể hết inode dù dung lượng byte còn trống. Theo dõi cả dung lượng, inode, số lượng file và tốc độ tăng trưởng.

### Theo dõi I/O

~~~sh
iostat -xz 1
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
~~~

**iostat** thường thuộc gói sysstat. Đối chiếu metric guest với metric volume của cloud provider. Một giới hạn ở cấp VM hoặc volume có thể khiến workload chậm dù filesystem và permission đúng.

## 14. Lỗi mount và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| **wrong fs type** hoặc không nhận filesystem | Chưa có filesystem, thiếu driver/tool hoặc chọn sai thiết bị | **lsblk -f**, **blkid**, kiểm tra package filesystem; không format trước khi xác minh dữ liệu |
| **already mounted** | Filesystem đã được mount ở vị trí khác | **findmnt**, kiểm tra mount point và fstab |
| **mount point does not exist** | Chưa tạo thư mục đích | Tạo mount point và kiểm tra owner |
| **permission denied** | Owner/group/ACL, export policy, SMB share ACL hoặc identity sai | **id**, **namei -l**, **getfacl**, kiểm tra server-side permissions |
| **device is busy** khi unmount | Process đang mở file hoặc working directory nằm trong mount | **fuser -vm**, **lsof**, dừng service an toàn |
| Boot chậm hoặc vào emergency mode | fstab sai, thiết bị không tồn tại hoặc network share chưa sẵn sàng | **findmnt --verify**, journal systemd, UUID và **_netdev** |
| NFS timeout | DNS, route, firewall, export hoặc server không sẵn sàng | Kiểm tra endpoint, TCP 2049, export policy và log |
| SMB mount thất bại | Credentials, dialect, DNS, port hoặc share ACL | Kiểm tra credentials file, SMB version, TCP 445 và quyền share |
| App không ghi được dù mount đã có | User service không có quyền, UID/GID mapping hoặc SELinux/AppArmor | Kiểm tra danh tính tiến trình, ACL và audit log |
| App ghi vào root disk thay vì volume | Mount thất bại nhưng thư mục mount point vẫn tồn tại | Readiness/dependency **RequiresMountsFor**, kiểm tra **findmnt** trước khi start |

### Quy trình điều tra

1. Xác minh tài nguyên đã attach ở cloud provider.
2. Kiểm tra thiết bị hoặc network endpoint mà hệ điều hành nhìn thấy.
3. Xác định filesystem và mount point thực tế bằng **lsblk**, **findmnt** hoặc công cụ Windows.
4. Đọc log kernel, systemd, NFS/SMB client hoặc VM agent.
5. Kiểm tra network, DNS, firewall và quyền server-side.
6. Kiểm tra owner/group/ACL và security policy của hệ điều hành.
7. Thử truy cập bằng đúng user của ứng dụng.
8. Sửa cấu hình, xác minh bằng mount thử hoặc lệnh kiểm tra.
9. Kiểm thử reboot hoặc reconnect trước khi đưa vào production.

Không chạy **fsck** hoặc công cụ sửa chữa filesystem trên filesystem đang mount read-write. Với XFS, dùng công cụ chuyên dụng như **xfs_repair** theo hướng dẫn và trạng thái mount phù hợp. Trước khi sửa chữa, cần có backup/snapshot và hiểu rõ rủi ro.

## 15. Ví dụ: mount volume dữ liệu cho dịch vụ Linux

Một dịch vụ web lưu tệp tải lên tại **/srv/app-data**. Nhóm vận hành attach một block volume mới, cần mount bền vững và chỉ cho user ứng dụng ghi.

Quy trình:

1. Đối chiếu volume ID và dung lượng trong cloud console.
2. Dùng **lsblk -f** để xác định thiết bị mới.
3. Xác minh thiết bị chưa có dữ liệu cần giữ.
4. Tạo filesystem theo chuẩn đã chọn.
5. Lấy UUID và tạo mount point **/srv/app-data**.
6. Thêm UUID vào fstab với tùy chọn phù hợp.
7. Chạy **findmnt --verify** và **mount -a**.
8. Tạo group **appdata**, cấp quyền cho service account.
9. Thêm **RequiresMountsFor=/srv/app-data** vào systemd unit.
10. Kiểm tra ghi/đọc bằng user ứng dụng và thử reboot trong staging.

Cấu hình fstab minh họa:

~~~fstab
UUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee /srv/app-data ext4 defaults,nofail,x-systemd.device-timeout=30s 0 2
~~~

Quyền thư mục minh họa:

~~~sh
sudo groupadd --force appdata
sudo usermod -aG appdata appuser
sudo chown root:appdata /srv/app-data
sudo chmod 2770 /srv/app-data
sudo -u appuser touch /srv/app-data/write-test
sudo -u appuser rm /srv/app-data/write-test
~~~

Trước khi xóa test file, xác minh nó đúng là file vừa tạo. Trong production, cần kiểm tra ứng dụng không start nếu mount không tồn tại, và volume đã được backup theo chính sách dữ liệu.

## 16. Checklist trước khi đưa mount vào production

- [ ] Đã xác định đúng loại storage: block, file hay object.
- [ ] Đã đối chiếu volume/share ID với thiết bị hoặc endpoint trong máy.
- [ ] Đã kiểm tra filesystem hiện có trước khi format.
- [ ] Đã chọn filesystem phù hợp với hệ điều hành và workload.
- [ ] Đã chọn mount point không che khuất dữ liệu cần giữ.
- [ ] Đã dùng UUID hoặc định danh ổn định cho block volume.
- [ ] Đã kiểm tra fstab bằng **findmnt --verify** và **mount -a**.
- [ ] Đã xác định rõ hành vi khi volume hoặc network share không khả dụng.
- [ ] Service có dependency/readiness để không ghi nhầm vào root filesystem.
- [ ] Owner, group, mode và ACL tuân theo least privilege.
- [ ] UID/GID nhất quán nếu dùng NFS hoặc filesystem chia sẻ.
- [ ] SMB credentials được bảo vệ và không nằm trong command history/fstab.
- [ ] Đã bật mã hóa at rest và in transit theo yêu cầu.
- [ ] Network chỉ cho phép máy cần thiết truy cập NFS/SMB.
- [ ] Đã kiểm tra SELinux/AppArmor nếu có.
- [ ] Đã thử truy cập bằng đúng service account.
- [ ] Đã kiểm tra dung lượng, inode, latency và throughput.
- [ ] Đã thử reboot, reconnect, unmount và quy trình detach.
- [ ] Có backup và đã kiểm tra khả năng restore.
- [ ] Có log, cảnh báo và hướng xử lý khi mount thất bại.

## Kết luận

Để ứng dụng sử dụng dữ liệu ổn định, cần hoàn thành cả chuỗi attach, nhận diện thiết bị, filesystem, mount và phân quyền. Block storage thường cần filesystem cục bộ; file storage được mount qua NFS/SMB; object storage thường được truy cập bằng API và chỉ nên dùng gateway khi ngữ nghĩa phù hợp. Cấu hình mount bền vững cần định danh ổn định, kiểm tra fstab, dependency rõ ràng và xử lý khi storage không sẵn sàng. Quyền owner/group/ACL, mã hóa, network policy và kiểm thử bằng đúng service account giúp dữ liệu chỉ được truy cập bởi tiến trình được phép trong suốt vòng đời máy.
