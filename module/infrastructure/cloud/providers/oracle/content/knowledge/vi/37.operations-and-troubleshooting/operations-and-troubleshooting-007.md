# Xử lý disk full, volume latency và filesystem errors

## 1. Mục tiêu và phạm vi

Trong chương **Vận hành và xử lý sự cố** của module **CLOUD_PROVIDERS_ORACLE**, bài này hướng dẫn xử lý ba nhóm sự cố lưu trữ thường gặp trên Oracle Cloud Infrastructure (OCI):

- Ứng dụng không ghi được vì hết dung lượng, cạn inode hoặc chạm quota.
- I/O chậm khiến request, batch job hoặc giao dịch cơ sở dữ liệu tăng thời gian đáp ứng.
- Filesystem báo lỗi, chuyển sang chỉ đọc hoặc không mount được.

Mục tiêu vận hành là khôi phục dịch vụ với dữ liệu còn tin cậy, tìm được nguyên nhân và đặt cơ chế ngăn tái diễn. Tăng dung lượng hoặc tăng hiệu năng volume chỉ là một trong các biện pháp có thể chọn.

Các lệnh trong bài dành cho **Bash trên Linux**, chủ yếu Oracle Linux với XFS hoặc ext4 và volume gắn vào OCI Compute. Người học cần biết SSH, quyền `sudo`, mount point, partition và cách xác định tài nguyên trong đúng tenancy, region, compartment.

Đường dẫn `/srv/app-data`, thiết bị `/dev/sdb`, partition `/dev/sdb1`, service `myapp.service` và OCID trong ví dụ đều là giá trị minh họa. Phải thay bằng kết quả đã xác minh trên máy đích. Không mặc định thiết bị có cùng tên sau khi detach, attach hoặc chuyển sang máy cứu hộ.

Bài phân tích filesystem do người vận hành quản trị trên Compute. Với OCI File Storage, cần chuyển sang nhánh NFS; với Object Storage, cần xem request, quyền và giới hạn dịch vụ. Với Autonomous Database hoặc dịch vụ cơ sở dữ liệu được quản lý, sử dụng cơ chế vận hành của dịch vụ. Không áp dụng lệnh sửa filesystem của máy Compute vào những lớp lưu trữ không thuộc quyền quản trị hệ điều hành của mình.

## 2. Tách các lớp trước khi chọn cách sửa

Một đường ghi dữ liệu có thể đi qua:

```text
Ứng dụng / cơ sở dữ liệu
          |
Filesystem: XFS, ext4
          |
Logical volume (LV), volume group (VG), physical volume (PV) nếu dùng LVM
          |
Partition nếu có
          |
Thiết bị block trong Linux
          |
Attachment: paravirtualized hoặc iSCSI, có thể có multipath
          |
OCI Block Volume hoặc Boot Volume
```

Không phải hệ thống nào cũng có đủ các lớp. Filesystem có thể nằm trực tiếp trên cả volume; PV của LVM cũng có thể nằm trực tiếp trên disk thay vì partition.

Ba phép đo trả lời ba câu hỏi khác nhau:

| Phép quan sát | Câu hỏi được trả lời | Điều chưa thể kết luận |
| --- | --- | --- |
| Kích thước volume trên OCI | Dịch vụ đã cấp bao nhiêu dung lượng block? | Filesystem đã sử dụng được phần tăng thêm chưa? |
| `lsblk`, `pvs`, `lvs` | Linux và LVM nhìn thấy kích thước từng lớp thế nào? | Ứng dụng có còn ghi được theo user, quota và đường dẫn của nó không? |
| `df`, kiểm tra inode/quota | Filesystem còn tài nguyên cấp phát cho workload không? | Đường I/O có đáp ứng đủ độ trễ và throughput không? |

Ví dụ, OCI đã tăng volume từ 100 lên 200 đơn vị dung lượng nhưng `df` vẫn thể hiện kích thước cũ là dấu hiệu cần kiểm tra chuỗi mở rộng trong guest OS. Đây chưa phải bằng chứng resize trên OCI thất bại.

### Nhận diện thông báo lỗi

| Triệu chứng | Hướng điều tra đầu tiên | Cách xử lý dễ đi sai |
| --- | --- | --- |
| `No space left on device` / `ENOSPC` | Dung lượng, inode, mount thực tế, giới hạn cấp phát | Xóa ngẫu nhiên file lớn nhất |
| `Disk quota exceeded` / `EDQUOT` | Quota user, group hoặc project | Tăng volume nhưng giữ nguyên quota |
| `Read-only file system` / `EROFS` | Mount options, kernel log, trạng thái filesystem | Remount ghi ngay khi chưa biết nguyên nhân |
| `Input/output error` / `EIO` | Kernel log, attachment, đường I/O, metadata filesystem | Mặc định cứ chạy công cụ repair là hết |
| Request chậm, timeout, không có lỗi dung lượng | I/O queue, workload, giới hạn volume và instance | Tăng VPU trước khi đo |
| `Permission denied` / `EACCES` | Quyền, ACL, SELinux và user thực thi | Quy mọi lỗi ghi cho disk full |

Một hệ thống có thể gặp nhiều nhóm lỗi cùng lúc. Ví dụ, mount data bị mất làm ứng dụng ghi vào root filesystem; root đầy khiến agent mất khả năng gửi telemetry; việc retry liên tục lại tạo thêm log và I/O.

## 3. Ổn định dịch vụ và thu bằng chứng ban đầu

Trước thao tác thay đổi dữ liệu, ghi lại thời điểm bắt đầu theo UTC, mức ảnh hưởng, thay đổi gần nhất và tài nguyên liên quan. Bộ nhận diện tối thiểu gồm instance OCID, volume OCID, attachment, compartment, region, mount point, filesystem và workload sở hữu dữ liệu.

Tách hai mặt quyền:

- IAM trên OCI cho phép xem hoặc thay đổi volume, attachment, metrics và backup theo compartment.
- Quyền trong guest OS cho phép đọc log, xem thiết bị, dừng service hoặc quản trị filesystem.

Có quyền `sudo` không tự tạo quyền resize volume trên OCI. Ngược lại, quyền quản lý volume không tự cho phép đăng nhập Linux. Khi CLI hoặc Console báo không được phép, kiểm tra principal, region, compartment và OCID trước khi xem đó là sự cố lưu trữ.

Nếu workload có replica hoặc cơ chế chuyển dịch vụ đã được kiểm chứng, giảm lưu lượng vào node lỗi theo runbook. Với job không thiết yếu, có thể tạm dừng producer, export hoặc batch đang tăng dữ liệu để tạo thời gian xử lý. Khi có lỗi metadata hoặc lỗi I/O lặp lại, ưu tiên cô lập ghi và giữ bằng chứng.

### Bộ lệnh quan sát đầu tiên

Chạy trên instance cần điều tra:

```bash
date -u
hostname

findmnt -T /srv/app-data -o TARGET,SOURCE,FSTYPE,OPTIONS
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINT

df -hT -- /srv/app-data
df -i -- /srv/app-data

sudo journalctl -k --since "-30 minutes" --no-pager
```

Cách đọc:

- `findmnt -T` chỉ ra filesystem đang phục vụ đường dẫn, kể cả khi đường dẫn đó chỉ là thư mục trên root filesystem.
- `lsblk` giúp nối mount point với partition, LV và disk. Đối chiếu thêm UUID, đường dẫn thiết bị ổn định và thông tin attachment khi cần xác nhận danh tính.
- `df -hT` thể hiện dung lượng và loại filesystem; `df -i` thể hiện mức dùng inode. Kiểm tra cả hai trước khi kết luận “còn chỗ”. [GNU: df](https://www.gnu.org/software/coreutils/manual/html_node/df-invocation.html)
- Kernel log giúp xác định lỗi xuất hiện trước hay sau thao tác mount, resize, thay đổi attachment hoặc reboot.

Nếu đường dẫn nằm trong container, kiểm tra filesystem và mount namespace mà tiến trình ứng dụng nhìn thấy. Một đường dẫn cùng tên trên host có thể không trỏ đến cùng nơi lưu dữ liệu.

Các công cụ `iostat`, `pidstat`, `lsof`, `growpart` hoặc bộ công cụ XFS có thể chưa được cài. Nên chuẩn bị trong image vận hành. Không cài hàng loạt package vào root filesystem đang đầy để phục vụ điều tra.

## 4. Xử lý disk full theo nguyên nhân

### 4.1. Hết block dung lượng

Ví dụ minh họa:

```text
Filesystem     Type  Size  Used  Avail  Use%  Mounted on
/dev/sdb1      xfs    98G   97G   1.0G   99%  /srv/app-data
```

Đầu tiên, xác định thư mục tăng nhanh trong đúng filesystem:

```bash
sudo du -xhd1 /srv/app-data
```

Sau đó chỉ đi sâu vào nhánh lớn, chẳng hạn:

```bash
sudo du -xhd1 /srv/app-data/logs
```

Tùy chọn `-x` giới hạn việc duyệt sang filesystem khác; `-d1` giới hạn độ sâu hiển thị. Việc giới hạn đầu ra không làm mất chi phí duyệt các file bên dưới, nên một cây có hàng triệu file vẫn có thể tạo tải đáng kể. [GNU: du](https://www.gnu.org/software/coreutils/manual/html_node/du-invocation.html)

Những nguồn tăng dung lượng cần kiểm tra gồm log ứng dụng, file export, heap dump, core dump, thư mục upload, file tạm và bản sao lưu đặt nhầm trên máy ứng dụng.

Chọn hành động dựa trên chủ sở hữu và vòng đời dữ liệu:

| Dữ liệu chiếm chỗ | Hành động phù hợp |
| --- | --- |
| Log cũ đã đóng, hết thời hạn lưu | Dọn theo retention sau khi giữ đủ dữ liệu điều tra |
| Log hiện tại tăng đột biến | Giảm nguyên nhân phát log, rotate và yêu cầu ứng dụng mở lại file theo cơ chế hỗ trợ |
| Cache có thể tái tạo | Dùng công cụ dọn cache của ứng dụng |
| Export hoặc backup đã xác minh ở nơi khác | Dọn bản local theo chính sách, kiểm tra khả năng phục hồi nếu đây là backup |
| Dữ liệu nghiệp vụ còn cần | Mở rộng hoặc di chuyển có kế hoạch |
| Datafile, redo, control file, archived log của Oracle Database | Chuyển cho quy trình DBA và công cụ cơ sở dữ liệu |

Di chuyển file sang thư mục khác trên cùng filesystem không giải phóng dung lượng. Nén file ngay tại filesystem gần đầy có thể cần thêm chỗ tạm và làm tăng CPU/I/O. Chỉ thực hiện khi đã tính được khoảng trống và mức ảnh hưởng.

### 4.2. Cạn inode vì quá nhiều file nhỏ

Ví dụ:

```text
Dung lượng đã dùng: 58%
Inode đã dùng:     100%
Tạo file mới:      No space left on device
```

Với các filesystem có báo cáo inode phù hợp, có thể khoanh vùng bằng:

```bash
sudo du --inodes -x --max-depth=1 /srv/app-data
```

Những tác nhân thường gặp là một file cho mỗi request, cache không có TTL, session file, spool và thư mục tạm không được thu gom. Cần dừng nguồn tạo file bất thường, xác định nhóm file hết hạn và dọn theo lô có giới hạn tải.

Không mặc định rằng mở rộng volume sẽ tự giải quyết mọi trường hợp inode. Cách cấp phát inode phụ thuộc filesystem; ext4 và XFS có đặc tính khác nhau. Sau khi xử lý phải đo lại inode, thử tạo file bằng user ứng dụng và xem tốc độ tăng số file.

Dọn triệu file có thể làm tăng tải metadata. Nếu dịch vụ đang suy giảm, kiểm soát tốc độ dọn và phối hợp thời điểm với workload thay vì chạy nhiều tác vụ quét cùng lúc.

### 4.3. `df` báo đầy nhưng `du` không giải thích được

Một nguyên nhân quan trọng là **file đã bị unlink nhưng tiến trình vẫn giữ file descriptor mở**. Tên file không còn trong cây thư mục để `du` duyệt, trong khi không gian vẫn được cấp phát cho tới khi tham chiếu mở được giải phóng. [GNU Coreutils FAQ](https://www.gnu.org/software/coreutils/faq/coreutils-faq.html)

Kiểm tra:

```bash
sudo lsof +L1
```

Đối chiếu thiết bị, inode, PID, loại file và kích thước với filesystem đang đầy. Không cộng cơ học mọi dòng vì một inode có thể xuất hiện qua nhiều descriptor hoặc tiến trình.

Cách khôi phục thường là yêu cầu ứng dụng mở lại log bằng chức năng được hỗ trợ, hoặc restart đúng service sau khi đánh giá ảnh hưởng. Ví dụ restart `myapp.service` chỉ có ý nghĩa khi đã xác nhận service đó đang giữ file liên quan và có phương án duy trì dịch vụ.

Không mặc định truncate qua `/proc/<pid>/fd/<fd>`: thao tác này có thể phá dữ liệu đang dùng và không sửa nguyên nhân log tiếp tục tăng.

Nếu không thấy file bị giữ mở, xem tiếp:

- `du` có được chạy đủ quyền và trên cùng filesystem với `df` không?
- Có dữ liệu nằm dưới một mount point bị che bởi mount khác không?
- Có khác biệt do filesystem metadata, reserved blocks, sparse file hoặc cách tính dung lượng không?
- Container hoặc tiến trình có mount namespace khác không?
- Kernel log có lỗi filesystem khiến số liệu không còn đáng tin không?

Chỉ điều tra dữ liệu bị che sau mount bằng quy trình bảo trì thích hợp. Không unmount volume đang phục vụ ghi chỉ để “nhìn thử” thư mục bên dưới.

### 4.4. Quota chặn ghi dù filesystem còn trống

Quota có thể giới hạn dung lượng hoặc inode cho user, group hay project. Trên XFS đã bật loại quota tương ứng, những lệnh dưới chỉ xuất báo cáo:

```bash
sudo xfs_quota -x -c 'report -ubh' /srv/app-data
sudo xfs_quota -x -c 'report -uih' /srv/app-data
sudo xfs_quota -x -c 'report -pbh' /srv/app-data
```

Các báo cáo lần lượt hỗ trợ xem block theo user, inode theo user và block theo project. Phải xác định loại quota đang dùng cùng user thực thi; tăng quota cho nhầm user không giải quyết lỗi của ứng dụng. [Oracle Linux: báo cáo quota XFS](https://docs.oracle.com/en/operating-systems/oracle-linux/8/xfs/xfs-ManagingQuotasonanXFSFileSystem_displaying_block_usage_information.html)

Quota filesystem trong Linux khác với quota tài nguyên của compartment trên OCI. Một cơ chế chặn ghi trong filesystem; cơ chế còn lại có thể chặn yêu cầu cấp thêm tài nguyên.

Với ext4, kiểm tra thêm reserved blocks nếu chỉ user thường bị hết phần dung lượng khả dụng. Không giảm vùng dự phòng của root filesystem theo phản xạ: phải đánh giá vai trò của nó trong việc giữ khả năng quản trị lúc gần đầy.

### 4.5. Mount data bị mất làm root đầy

Nếu `/srv/app-data` vốn phải là volume riêng nhưng `findmnt -T` trả về filesystem của `/`, ứng dụng có thể đã ghi vào thư mục trên root trong lúc volume chưa mount.

Trình tự xử lý:

1. Dừng nguồn ghi vào đường dẫn đó.
2. Ghi nhận dữ liệu phát sinh trên root và dữ liệu đang có trên data volume.
3. Khôi phục attachment hoặc mount theo nguyên nhân thực tế.
4. Đối soát, di chuyển hoặc hợp nhất dữ liệu theo quy tắc ứng dụng.
5. Chỉ khởi động lại ứng dụng khi mount point đã được xác minh.

Mount volume trở lại sẽ che dữ liệu đang có trong thư mục nền, không tự hợp nhất dữ liệu. Nếu chỉ nhìn thấy root bớt tăng và bỏ qua phần phát sinh, hệ thống có thể mất dấu một số bản ghi.

Để ngăn tái diễn, service cần phụ thuộc vào mount cần thiết và kiểm tra filesystem mong đợi trước khi ghi. Với systemd, có thể thiết kế dependency bằng `RequiresMountsFor=` kết hợp kiểm tra danh tính mount trong runbook hoặc cơ chế khởi động.

## 5. Khi cần tăng dung lượng OCI volume

Chỉ mở rộng sau khi xác định đúng volume và biết lớp nào đang thiếu chỗ. Trước thay đổi cần có backup hoặc điểm khôi phục phù hợp; với dữ liệu đang ghi, phối hợp cơ chế quiesce/backup của ứng dụng để đáp ứng yêu cầu nhất quán.

OCI hỗ trợ tăng kích thước block volume và boot volume; không hỗ trợ giảm kích thước volume tại chỗ. Vì vậy, quyết định tăng cần tính chi phí dài hạn. Nếu cần thu nhỏ về sau, phải lập phương án tạo volume nhỏ hơn và di chuyển dữ liệu phù hợp. [OCI: Resizing a Volume](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/resizingavolume.htm)

### 5.1. Mở rộng ở lớp dịch vụ

Ví dụ OCI CLI cho **data block volume**, thực hiện ở môi trường đã cấu hình quyền và region:

```bash
VOLUME_OCID='ocid1.volume.REPLACE_ME'

oci bv volume get --volume-id "$VOLUME_OCID"

oci bv volume update --volume-id "$VOLUME_OCID" --size-in-gbs 200
```

Giá trị `200` là kích thước mới mong muốn, không phải lượng tăng thêm. Phải lớn hơn kích thước hiện tại. Đọc lại volume sau khi yêu cầu hoàn tất và xác nhận kích thước mới. Với boot volume, dùng đúng thao tác dành cho boot volume; không lấy lệnh data volume áp dụng nguyên xi. [OCI: Online Resizing a Block or Boot Volume](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/update-online-resize-block-boot-volume.htm)

Yêu cầu resize trên OCI thành công chưa hoàn thành phần công việc trong Linux.

### 5.2. Rescan đúng thiết bị

Sau khi volume tăng kích thước, dùng hướng dẫn rescan mà OCI cung cấp cho attachment và hệ điều hành tương ứng. Với đường thiết bị SCSI phù hợp, tài liệu OCI minh họa việc đọc trực tiếp một block rồi yêu cầu rescan. Nếu đã xác minh disk là `/dev/sdb` và sysfs tương ứng tồn tại:

```bash
sudo dd iflag=direct if=/dev/sdb of=/dev/null count=1
echo 1 | sudo tee /sys/class/block/sdb/device/rescan
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINT
```

Đây là ví dụ rescan, không phải bài đo hiệu năng. Nếu attachment, driver hoặc thiết bị không khớp, không tự suy tên sysfs. Với multipath, cần quy trình cập nhật đầy đủ các path và map, không chỉ rescan một đường thành viên. [OCI: Rescanning the Disk](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/rescanningdisk.htm)

### 5.3. Ví dụ data volume có partition và XFS, không dùng LVM

Giả định đã xác minh:

- `/dev/sdb` là đúng data volume vừa tăng.
- `/dev/sdb1` chứa XFS đang mount tại `/srv/app-data`.
- Partition có vùng trống liền kề phía sau để mở rộng.
- Filesystem đang khỏe; đã có phương án phục hồi và cửa sổ thay đổi phù hợp.

Xem trước thay đổi partition:

```bash
sudo growpart -N /dev/sdb 1
```

Chỉ khi kết quả phù hợp mới mở rộng thật:

```bash
sudo growpart /dev/sdb 1
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINT
```

`growpart` nhận **disk** và **số partition** thành hai đối số riêng. `-N` là chế độ dry run. Nếu báo không thể mở rộng, thiếu không gian liền kề hoặc kernel chưa nhận kích thước mới, dừng để xử lý đúng lớp thay vì xóa và tạo lại partition theo phỏng đoán. [Canonical: growpart](https://github.com/canonical/cloud-utils/blob/main/man/growpart.1)

Sau khi partition trong kernel đã có kích thước mới:

```bash
sudo xfs_growfs -d /srv/app-data
df -hT -- /srv/app-data
```

XFS được grow khi đang mount; đối số của lệnh trên là mount point. Lệnh này không tự tăng disk hoặc partition bên dưới. [Oracle Linux: Growing an XFS File System](https://docs.oracle.com/en/operating-systems/oracle-linux/9/xfs/xfs-GrowinganXFSFileSystem.html)

Nếu filesystem nằm trực tiếp trên toàn bộ disk thì bỏ qua bước partition. Nếu là ext4 đã được xác minh khỏe và môi trường hỗ trợ online grow, dùng `resize2fs` trên thiết bị chứa filesystem sau khi lớp bên dưới đã mở rộng:

```bash
sudo resize2fs /dev/sdb1
df -hT -- /srv/app-data
```

Chỉ chọn nhánh tương ứng với filesystem thật. `resize2fs` không dành cho XFS; `xfs_growfs` không dành cho ext4. Khi cần kiểm tra và sửa ext4 trước thay đổi, thực hiện offline theo quy trình bảo trì. [Oracle Linux: Resizing an Ext File System](https://docs.oracle.com/en/operating-systems/oracle-linux/9/ext/ext-ResizinganExtFileSystem.html)

### 5.4. Trường hợp có LVM hoặc mở rộng root filesystem

Với LVM, trước tiên xem quan hệ thiết bị:

```bash
sudo pvs
sudo vgs
sudo lvs -o lv_path,lv_size,vg_name,devices
```

Nếu PV nằm trên partition thì partition phải tăng trước. Sau đó mới cập nhật PV, kiểm tra dung lượng trống trong VG, tăng đúng LV và grow filesystem. Nếu PV nằm trực tiếp trên cả disk thì không tạo thêm partition.

Ví dụ riêng cho cấu hình đã xác minh PV là `/dev/sdb1`, LV là `/dev/vg_app/lv_data` và filesystem là XFS tại `/srv/app-data`:

```bash
sudo pvresize /dev/sdb1
sudo pvs
sudo vgs

sudo lvextend -L +20G /dev/vg_app/lv_data
sudo lvs -o lv_path,lv_size,vg_name,devices

sudo xfs_growfs -d /srv/app-data
df -hT -- /srv/app-data
```

`+20G` là lượng tăng thêm cho LV và chỉ thực hiện nếu VG đủ free extents. Không mặc định lấy toàn bộ dung lượng trống nếu VG còn phục vụ LV khác. Một số phiên bản công cụ có thể đã cập nhật PV khi grow partition, nên phải kiểm tra trạng thái thực tế giữa các bước. [Oracle: Configure Logical Volumes](https://docs.oracle.com/en/learn/ol-lvm/)

Với root filesystem trên Oracle Linux được hỗ trợ, `oci-growfs` trong bộ OCI Utilities có thể xử lý việc mở rộng theo layout được công cụ hỗ trợ. Kiểm tra layout, phiên bản và hướng dẫn đúng image trước khi dùng; không chạy chuỗi data-volume giả định trên boot disk. [OCI Utilities Reference](https://docs.oracle.com/en-us/iaas/oracle-linux/oci/oci-utilities-reference.htm)

## 6. Điều tra volume latency bằng bằng chứng

### 6.1. Xác định chậm ở đâu

“Disk chậm” có thể là:

- Ứng dụng chờ lock hoặc chờ CPU trước khi phát I/O.
- Filesystem hoặc memory pressure làm thao tác ghi, flush hoặc writeback bị dồn.
- Nhiều workload cùng tranh volume.
- Workload chạm giới hạn IOPS hoặc throughput.
- Instance shape, attachment hoặc đường kết nối giới hạn hiệu năng.
- Đường I/O có timeout, retry hoặc mất kết nối.
- Cơ sở dữ liệu chờ I/O đồng bộ theo đặc tính giao dịch.

Đo đồng thời request latency của ứng dụng, số liệu guest OS và metrics OCI trong cùng khoảng thời gian. So sánh với baseline có workload tương đương; không dùng một giá trị latency chung làm chuẩn cho mọi loại I/O.

### 6.2. Quan sát trong Linux

```bash
iostat -xz -y 1 10
vmstat 1 10
sudo pidstat -d 1 10
```

`iostat -y` bỏ báo cáo đầu tiên tính từ lúc boot để tập trung vào cửa sổ hiện tại. Những cột cần chú ý gồm:

| Cột | Ý nghĩa khi điều tra |
| --- | --- |
| `r/s`, `w/s` | Số yêu cầu đọc/ghi hoàn tất mỗi giây |
| `rkB/s`, `wkB/s` hoặc biến thể theo phiên bản | Lưu lượng đọc/ghi |
| `r_await`, `w_await` | Thời gian trung bình của I/O, gồm xếp hàng và phục vụ |
| `aqu-sz` | Độ dài hàng đợi trung bình |
| `%util` | Thời gian thiết bị bận theo phép đo của OS |

Trên thiết bị phục vụ song song, `%util` gần 100% không thể tự nó chứng minh đã đạt giới hạn hiệu năng. `await` cũng không phải latency thuần của dịch vụ OCI. [iostat manual](https://man7.org/linux/man-pages/man1/iostat.1.html)

Dùng `pidstat` để nhận diện workload tạo I/O, sau đó đối chiếu lịch backup, log rotation, scan dữ liệu và batch job. Với `vmstat`, chú ý swap và memory pressure; đọc liên tiếp các mẫu đo, vì báo cáo đầu có thể phản ánh thống kê tích lũy.

Không cộng I/O trên LV, partition và disk như thể đó là các luồng độc lập: cùng một I/O có thể được quan sát tại nhiều lớp.

Nếu p99 request tăng nhưng block I/O không thay đổi, xem trace, lock, CPU, connection pool hoặc dependency khác trước khi sửa cấu hình volume. Trung bình ổn định cũng có thể che những đợt flush ngắn gây tăng độ trễ đuôi.

### 6.3. Ghép với metrics trên OCI

Trong namespace `oci_blockstore`, chọn đúng volume bằng `resourceId` và phân biệt các attachment khi cần:

| Metric | Điều cần xem |
| --- | --- |
| `VolumeReadOps`, `VolumeWriteOps` | Số thao tác đọc/ghi trong khoảng đo |
| `VolumeReadThroughput`, `VolumeWriteThroughput` | Lượng byte đọc/ghi trong khoảng đo |
| `VolumeThrottledIOs` | Số I/O bị throttling |
| `VolumeGuaranteedIOPS` | Mức IOPS được cấp theo cấu hình hiện hành |
| `VolumeGuaranteedVPUsPerGB` | Mức VPU/GB đang áp dụng |

Không coi tổng thao tác trong một phút là IOPS; phải quy đổi theo thời gian và phép tổng hợp. Metrics của volume không thay thế phép đo dung lượng filesystem trong guest. [OCI: Block Volume Metrics Reference](https://docs.oracle.com/en-us/iaas/Content/Block/References/volumemetrics-reference.htm)

Khi dữ liệu vắng mặt, kiểm tra đúng region, compartment, bộ lọc, cửa sổ thời gian và quyền xem metrics. “Không có dữ liệu” cần có nhánh xử lý riêng, vì nó không đồng nghĩa I/O bằng không.

### 6.4. Hiểu giới hạn trước khi nâng hiệu năng

Hiệu năng sử dụng được bị ràng buộc bởi nhiều lớp: kích thước và mức hiệu năng volume, giới hạn mỗi volume, giới hạn tổng của instance và cấu hình attachment. Tăng VPU không loại bỏ giới hạn ở instance. Với Ultra High Performance, cần kiểm tra điều kiện hỗ trợ và cấu hình multipath theo attachment, shape và image thực tế. [OCI: Block Volume Performance](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumeperformance.htm)

Một cách tính để định hướng:

```text
Throughput xấp xỉ = IOPS × kích thước I/O trung bình

12.000 IOPS × 8 KiB   = 93,75 MiB/s
1.000 IOPS × 256 KiB  = 250 MiB/s
```

Đây là phép tính minh họa, không phải cam kết hiệu năng OCI. Một workload có ít IOPS vẫn có thể chạm giới hạn throughput vì kích thước I/O lớn.

Tương tự, workload tuần tự từng I/O với độ trễ trung bình 2 ms chỉ có thể hoàn tất xấp xỉ 500 I/O mỗi giây khi luôn chỉ có một yêu cầu đang chờ. Tăng hiệu năng được cấp không làm ứng dụng tự tạo thêm concurrency. Ngược lại, tăng queue depth quá mạnh có thể nâng throughput nhưng làm latency của request tăng.

### 6.5. Chọn hành động từ mẫu số liệu

| Bằng chứng kết hợp | Giả thuyết cần kiểm chứng | Hành động đầu tiên |
| --- | --- | --- |
| Throttling tăng, queue tăng, workload áp sát mức cấp | Giới hạn volume đang là nút thắt | Giảm tải không thiết yếu; cân nhắc điều chỉnh hiệu năng |
| Nhiều volume cùng chậm trên một instance | Giới hạn tổng của instance hoặc áp lực guest OS | Đối chiếu shape, CPU, memory và tổng I/O |
| Không có throttling nhưng kernel báo timeout/reset | Sự cố attachment hoặc đường I/O | Giữ log, kiểm tra kết nối và cấu hình path |
| Latency tăng đúng lúc backup/export | Tranh chấp workload | Đổi lịch hoặc giới hạn concurrency của job |
| Ghi chậm, swap và memory pressure tăng | Thiếu bộ nhớ hoặc writeback bị dồn | Xử lý áp lực bộ nhớ và cấu hình ứng dụng |
| IOPS thấp, queue thấp, app chỉ ghi đồng bộ từng lần | Workload thiếu concurrency hoặc bị giới hạn ở ứng dụng | Xem thiết kế ghi và yêu cầu độ bền dữ liệu |

Các hàng là hướng điều tra, không phải kết luận tự động. Thay đổi một yếu tố mỗi lần và đo trước/sau trong điều kiện có thể so sánh.

Không tắt `fsync`, flush hoặc cơ chế bảo đảm độ bền của database chỉ để giảm số đo latency. Với iSCSI, có thể quan sát session bằng lệnh đọc trạng thái phù hợp:

```bash
sudo iscsiadm -m session -P 3
```

Nếu hệ thống dùng multipath, kiểm tra map và path bằng:

```bash
sudo multipath -ll
```

Hai lệnh chỉ có ý nghĩa khi hệ thống thực sự dùng công nghệ tương ứng. Không logout session hoặc detach volume đang có filesystem mount để thử kết nối lại.

### 6.6. Benchmark có kiểm soát

Trong sự cố production, bắt đầu bằng số liệu của workload thực. Chạy benchmark mạnh trên volume đang phục vụ có thể làm tình hình xấu thêm.

Khi cần xác minh giới hạn, dùng volume hoặc file thử nghiệm riêng, kiểm soát dữ liệu, dung lượng, I/O size, read/write mix, queue depth và thời lượng. Ghi phiên bản công cụ, cấu hình shape/volume cùng metrics trong đúng cửa sổ đo. Phân biệt bài đo baseline latency với bài đo khả năng bão hòa IOPS hoặc throughput. [OCI: Block Volume Performance Tests](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/bv-perf-win-tests.htm)

Không dùng `dd` ghi lên raw device có dữ liệu. Không dùng một lần copy file chịu ảnh hưởng page cache để tuyên bố volume đạt hay không đạt mức hiệu năng.

## 7. Xử lý filesystem errors và trạng thái chỉ đọc

### 7.1. Xác định lỗi thuộc filesystem hay đường thiết bị

Bắt đầu bằng mount options và kernel log:

```bash
findmnt -T /srv/app-data -o TARGET,SOURCE,FSTYPE,OPTIONS
sudo journalctl -k --since "-1 hour" --no-pager
```

Những nhóm thông báo cần giữ lại gồm lỗi I/O hoặc timeout ở block device, lỗi ext4 journal, lỗi metadata XFS, filesystem shutdown và thông báo remount chỉ đọc.

Một filesystem gắn `ro` có thể do cấu hình chủ động hoặc do cơ chế bảo vệ sau lỗi. XFS cũng có thể shutdown filesystem và trả lỗi I/O; không phải mọi lỗi XFS đều xuất hiện dưới dạng remount chỉ đọc.

Nếu đường block vẫn timeout hoặc mất thiết bị, ưu tiên khôi phục đường I/O và kiểm soát ghi trước. Công cụ sửa metadata không sửa được kết nối iSCSI bị mất hoặc attachment đang sai.

### 7.2. Chuẩn bị trước khi repair

Một quy trình có thể phục hồi cần trả lời được:

1. Dữ liệu nào đang bị ảnh hưởng và ai sở hữu?
2. Có replica, backup hoặc bản sao phục hồi nào đáp ứng RPO/RTO?
3. Có thể dừng producer, drain traffic và đóng tiến trình dùng filesystem không?
4. Đúng thiết bị chứa filesystem là partition, LV hay cả disk?
5. Có backup hoặc clone giữ nguyên trạng thái trước sửa không?
6. Kernel và công cụ repair có hỗ trợ các tính năng của filesystem không?

Backup của trạng thái hỏng vẫn có thể hữu ích cho điều tra hoặc thử phương án khác, nhưng không phải bản backup khỏe. Với dữ liệu quan trọng, ưu tiên thử khôi phục trên bản sao phù hợp khi có thể.

Không chạy `mkfs` để sửa filesystem chứa dữ liệu cần giữ. Không chạy repair trên parent disk khi filesystem thật nằm trong partition hoặc LV.

### 7.3. XFS: kiểm tra offline rồi mới sửa

Ví dụ này chỉ dành cho **data filesystem XFS** đã xác minh trên `/dev/sdb1`. Ứng dụng đã drain/dừng và không còn tiến trình sử dụng mount:

```bash
sudo umount /srv/app-data
findmnt --source /dev/sdb1

sudo xfs_repair -n /dev/sdb1
```

Lệnh `findmnt` không được còn liệt kê mount của filesystem đó. Nếu `umount` báo busy, tìm tiến trình sử dụng và xử lý dependency; không dùng lazy unmount như cách né điều kiện offline.

`xfs_repair -n` chỉ khảo sát các sửa đổi dự kiến. Sau khi đã đọc kết quả, giữ bản sao cần thiết và chọn repair:

```bash
sudo xfs_repair /dev/sdb1
```

Nếu có dirty log, có thể cần journal replay qua chu trình mount/unmount có kiểm soát trên môi trường phù hợp; dừng khi không rõ trạng thái. `xfs_repair -L` xóa log và có thể mất dữ liệu, chỉ là phương án cuối sau đánh giá phục hồi, không phải lệnh mặc định. [Oracle Linux: Checking and Repairing XFS](https://docs.oracle.com/en/operating-systems/oracle-linux/9/xfs/xfs-CheckingandRepairinganXFSFileSystem.html)

Sau repair, mount lại bằng cấu hình đã xác minh, xem kernel log rồi kiểm tra dữ liệu của ứng dụng. Repair thành công về metadata chưa chứng minh nội dung từng file còn đầy đủ.

### 7.4. ext4: kiểm tra và sửa khi đã unmount

Ví dụ riêng cho **ext4**, không chạy nối tiếp nhánh XFS:

```bash
sudo umount /srv/app-data
findmnt --source /dev/sdb1

sudo e2fsck -f -n /dev/sdb1
```

Khi đã xem kết quả, có bản sao phù hợp và chấp nhận thay đổi:

```bash
sudo e2fsck -f /dev/sdb1
```

Không mặc định thêm `-y` để chấp nhận mọi sửa đổi. Giữ output, xử lý theo kết quả và kiểm tra exit status. Việc kiểm tra/sửa filesystem đang mount có thể làm hỏng dữ liệu; root filesystem cần môi trường offline hoặc máy cứu hộ. [Oracle Linux: Checking and Repairing an Ext File System](https://docs.oracle.com/en/operating-systems/oracle-linux/9/ext/ext-CheckingandRepairinganExtFileSystem.html)

Nếu dữ liệu được phục hồi vào `lost+found`, cần đối soát với ứng dụng. Không xem việc mount được là bằng chứng toàn bộ nghiệp vụ đã khôi phục.

### 7.5. Boot volume lỗi, không SSH được

Khi instance không boot hoặc root filesystem chỉ đọc, dùng serial console để lấy thông báo khởi động. Nếu cần sửa offline, quy trình OCI là dừng instance, detach boot volume và attach nó như data volume vào Linux instance cứu hộ tương thích trong cùng region và availability domain.

Trên máy cứu hộ, so sánh `lsblk` trước/sau attach, nhận diện đúng partition hoặc LV, tránh nhầm root disk của máy cứu hộ và tránh tự động mount bản cần sửa. Sau khi sửa và xác minh, unmount, detach khỏi máy cứu hộ rồi gắn lại vào instance ban đầu. [OCI: Recovering a Corrupted Boot Volume](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/recoveringlinuxbootvolume.htm)

Nếu boot volume và máy cứu hộ có VG hoặc UUID trùng nhau, cần xử lý theo quy trình LVM/filesystem phù hợp trước khi activate hoặc mount. Không kích hoạt hàng loạt LV một cách mù quáng.

Reboot có kiểm soát có thể hỗ trợ journal recovery trong một số tình huống; reboot cưỡng bức lặp đi lặp lại không thay thế việc chẩn đoán và có thể làm mất bằng chứng.

## 8. Lưu ý khi workload là Oracle Database

Trước hết phân biệt ba loại “đầy”:

| Lớp | Dấu hiệu cần xem | Đơn vị xử lý |
| --- | --- | --- |
| Filesystem Linux | Block, inode, quota, lỗi mount | OS và storage operator |
| ASM disk group | Dung lượng và yêu cầu dự phòng trong ASM | DBA/ASM administrator |
| Tablespace hoặc Fast Recovery Area (FRA) | Giới hạn và mức sử dụng trong database | DBA và công cụ database |

Disk còn trống không bảo đảm FRA hoặc tablespace còn trong giới hạn cấu hình. Ngược lại, database cho phép autoextend không bảo đảm filesystem bên dưới đủ chỗ.

Với FRA hoặc archived log, quyết định dọn phải xét backup, recovery window và các bên còn cần log, chẳng hạn standby database. Dùng công cụ quản lý của Oracle Database và phối hợp DBA; xóa file ở OS có thể làm repository không khớp với dữ liệu thực và làm mất khả năng phục hồi. [Oracle Database: Maintaining RMAN Backups](https://docs.oracle.com/en/database/oracle/oracle-database/18/bradv/maintaining-rman-backups.html)

Khi database báo chờ I/O, đối chiếu số liệu database với guest OS và OCI theo cùng timestamp. Dùng công cụ chẩn đoán phù hợp với quyền và giấy phép hiện có. Không gọi mọi wait event liên quan I/O là sự cố hạ tầng nếu chưa xem kiểu truy cập, kế hoạch thực thi, concurrency và lịch backup.

## 9. Ví dụ phối hợp các bước trên một data volume

Giả sử ứng dụng Java chạy trên OCI Compute tăng lỗi ghi sau một lần bật debug log. Đây là số liệu minh họa để giải thích quyết định, không phải kết quả benchmark thực tế.

| Quan sát | Kết quả |
| --- | --- |
| `findmnt -T /srv/app-data` | Đúng data filesystem dự kiến |
| `df -hT` | Dùng 99% |
| `df -i` | Dùng 9% inode |
| `du` trên filesystem | Ít hơn đáng kể mức dùng mà `df` báo |
| `lsof +L1` | JVM đang giữ một log đã bị xóa |
| Kernel log | Không thấy lỗi thiết bị hoặc metadata trong cửa sổ kiểm tra |

Hướng xử lý:

1. Giảm debug log và chặn nguồn phát log bất thường.
2. Giữ phần log cần điều tra ở nơi còn chỗ, tránh tạo bản sao trên filesystem đầy.
3. Dùng cơ chế reopen log được ứng dụng hỗ trợ; nếu cần restart JVM, drain node và bảo đảm phương án duy trì dịch vụ.
4. Xác nhận descriptor được đóng, dung lượng được thu hồi và ứng dụng ghi lại được.
5. Kiểm tra retention và cơ chế rotation với ứng dụng.
6. Dùng xu hướng tăng dữ liệu sau ổn định để quyết định có cần resize.

Nếu sau đó vẫn còn latency cao, mở nhánh điều tra I/O riêng bằng `iostat`, workload và metrics OCI. Không kết luận latency đã hết chỉ vì `df` giảm.

Nếu thay vào đó kernel log có lỗi I/O hoặc XFS shutdown, dừng ở nhánh bảo vệ dữ liệu và phục hồi filesystem/đường lưu trữ. Việc xóa log không giải quyết được tình trạng đó.

## 10. Giám sát, tự động hóa và kiểm soát chi phí

### 10.1. Cảnh báo theo khả năng còn phục vụ

Nên kết hợp nhiều tín hiệu:

| Tín hiệu | Ý nghĩa vận hành |
| --- | --- |
| Tỷ lệ dùng block và số byte còn lại | Dung lượng khả dụng thực tế |
| Mức dùng inode và quota | Khả năng tạo file/cấp phát cho workload |
| Tốc độ tăng và thời gian dự kiến đến ngưỡng cạn | Khoảng thời gian còn để can thiệp |
| Throttled I/O, queue và latency ứng dụng | Mức suy giảm hiệu năng |
| Lỗi kernel hoặc filesystem chuyển trạng thái bất thường | Nhu cầu bảo vệ dữ liệu |
| Mount bắt buộc bị thiếu | Nguy cơ ghi nhầm vào root |
| Telemetry ngừng gửi | Điểm mù trong giám sát |

Cần thu số liệu filesystem từ guest bằng agent hỗ trợ hoặc custom metrics phù hợp. Chỉ nhìn kích thước Block Volume không biết được dung lượng đã dùng trong XFS/ext4.

Ví dụ, 80% và 90% có thể là ngưỡng cảnh báo khởi đầu của một đội, nhưng phải hiệu chỉnh theo workload. Một filesystem rất lớn dùng 92% có thể còn nhiều thời gian hơn một filesystem nhỏ dùng 75% đang nhận dump tốc độ cao.

Ước lượng đơn giản:

```text
Thời gian còn lại ≈ Dung lượng khả dụng / Tốc độ tăng ròng

Còn 24 GiB, tăng ròng 3 GiB/giờ
=> Khoảng 8 giờ nếu tốc độ giữ nguyên
```

Cần tính thêm burst, độ trễ phản ứng và thời gian resize/khôi phục. Khi tốc độ tăng không ổn định, dùng nhiều cửa sổ đo và ngưỡng dung lượng tuyệt đối để hỗ trợ quyết định.

### 10.2. Tự động hóa theo điều kiện kiểm chứng được

Một tác vụ tự động dọn log cần có đường dẫn cho phép, loại file, tuổi file, giới hạn lượng dọn, bằng chứng đã lưu ở nơi cần thiết và cơ chế tránh chạy đồng thời. Giữ log hành động ở đích không phụ thuộc filesystem đang đầy.

Với tự động mở rộng, cần kiểm tra đúng OCID, giới hạn kích thước/chi phí, trạng thái volume, quota và khả năng grow trong guest. Phải có bước kiểm tra sau mỗi lớp; yêu cầu resize thành công trên OCI không được xem là tiêu chí kết thúc.

Không tự động repair filesystem hoặc xóa dữ liệu nghiệp vụ từ một cảnh báo phần trăm dung lượng.

### 10.3. Cân bằng hiệu năng, sẵn sàng và ngân sách

- Tách log, data và file tạm khi giúp khoanh vùng ảnh hưởng và đặt retention phù hợp.
- Giảm tranh chấp bằng cách đổi lịch batch trước khi mua thêm hiệu năng.
- Khi tăng VPU hoặc đổi shape để ứng cứu, ghi thời điểm và đặt bước đánh giá lại sau ổn định.
- Dùng dữ liệu tăng trưởng để chọn kích thước mới; volume không thu nhỏ tại chỗ nên tăng quá mức có chi phí kéo dài.
- Thử restore định kỳ và đo thời gian khôi phục. Backup chưa thử không cho biết chắc RTO thực tế.
- Thiết kế chuyển dịch vụ bằng replication hoặc cơ chế HA phù hợp. Không mount XFS/ext4 thông thường ở chế độ ghi đồng thời từ nhiều instance chỉ vì volume hỗ trợ nhiều attachment.

HA không tự thay thế backup: dữ liệu bị xóa hoặc ghi sai có thể lan sang replica. Phương án vận hành cần bảo đảm cả khả năng tiếp tục phục vụ lẫn khả năng trở về trạng thái dữ liệu đúng.

## 11. Xác minh trước khi đóng sự cố

Xác minh bằng user và đường chạy của ứng dụng, không chỉ bằng tài khoản root.

| Nhóm kiểm tra | Bằng chứng cần có |
| --- | --- |
| Đúng nơi lưu dữ liệu | Mount point, source, UUID hoặc định danh tương ứng khớp thiết kế |
| Đủ tài nguyên cấp phát | Block, inode và quota đều còn khoảng dự phòng |
| Ghi được trong điều kiện thực | Health check hoặc giao dịch thử theo cơ chế ứng dụng có tạo/đọc lại dữ liệu thành công |
| Không còn lỗi lưu trữ mới | Kernel log và log ứng dụng không tiếp tục phát lỗi liên quan trong cửa sổ quan sát |
| Hiệu năng đáp ứng | Latency, error rate và I/O trở lại mức chấp nhận ở tải đại diện |
| Dữ liệu tin cậy | Đối soát phù hợp sau repair, failover hoặc restore |
| Phương án khôi phục sẵn sàng | Backup/replication/HA đã được kiểm tra lại sau thay đổi |
| Nguyên nhân không tiếp diễn | Producer, retention, mount dependency hoặc cấu hình gây lỗi đã được xử lý |

Nếu đã tăng volume, xác minh đầy đủ các lớp đang dùng:

```text
Kích thước trên OCI
    -> disk trong Linux
    -> partition nếu có
    -> PV / VG / LV nếu có
    -> filesystem
    -> quyền, quota và thao tác ghi của ứng dụng
```

Hồ sơ sự cố nên giữ timeline UTC, định danh tài nguyên, output trước/sau, thay đổi đã làm, mức ảnh hưởng dữ liệu và người phụ trách hành động tiếp theo.

Khi chuyển Oracle Support, cung cấp volume/instance/attachment OCID, region, availability domain, loại attachment, cấu hình hiệu năng, cửa sổ thời gian, metrics, kernel log và thay đổi gần nhất. Loại bỏ credential và dữ liệu nhạy cảm không cần thiết. Bằng chứng theo cùng thời gian giúp phân biệt lỗi guest OS, workload và dịch vụ nhanh hơn.
