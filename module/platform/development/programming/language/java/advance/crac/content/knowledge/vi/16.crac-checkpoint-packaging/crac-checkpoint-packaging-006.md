# Quyền truy cập, chủ sở hữu và đường dẫn cần giữ khi phân phối

Ảnh checkpoint CRaC chứa trạng thái của một tiến trình JVM tại thời điểm checkpoint. Khi phân phối ảnh sang môi trường khác để restore, việc sao chép đủ các tệp là chưa đủ. Tiến trình khôi phục còn cần đọc được ảnh, truy cập được những đường dẫn mà trạng thái tiến trình phụ thuộc vào và có quyền phù hợp với các tài nguyên bên ngoài.

Trên Linux, quyền truy cập phụ thuộc vào user ID (UID), group ID (GID), permission bits, ACL, namespace, mount và chính sách bảo mật như SELinux hoặc AppArmor. Đường dẫn cũng có ý nghĩa quan trọng: một file được mở trước checkpoint có thể cần xuất hiện ở cùng vị trí trong môi trường restore; một symlink có thể trỏ đến đích khác; một volume có thể được mount vào đường dẫn khác.

Vì vậy, khi đóng gói và phân phối checkpoint, cần quản lý đồng thời ba nhóm thông tin:

- **Quyền truy cập**: ai được đọc, ghi, traverse hoặc thay đổi ảnh và các tệp phụ thuộc.
- **Chủ sở hữu**: UID/GID nào sở hữu tệp, thư mục và tài nguyên được khôi phục; các ID này được ánh xạ ra sao trong container hoặc user namespace.
- **Đường dẫn và mount**: những đường dẫn tuyệt đối, symlink, mount point và filesystem nào phải tồn tại với cấu trúc tương thích khi restore.

Một ảnh chỉ nên được coi là sẵn sàng phân phối khi checkpoint đã hoàn tất, metadata cần thiết được bảo toàn, quyền ở đích đã được xác minh và môi trường restore đáp ứng các giả định về path, UID/GID và mount.

## 1. Vì sao quyền và đường dẫn ảnh hưởng đến restore?

Checkpoint/restore không chỉ đọc một file dữ liệu độc lập. Runtime và công cụ hệ điều hành cần truy cập các tệp ảnh, tái lập trạng thái tiến trình và xử lý những tài nguyên mà tiến trình đang sử dụng. Ứng dụng cũng có thể cần đọc cấu hình, thư viện native, certificate, file dữ liệu hoặc volume được mount tại các đường dẫn cụ thể.

Một số lỗi thường gặp:

- User chạy JVM không có quyền traverse thư mục cha hoặc đọc tệp ảnh.
- File ảnh thuộc UID/GID khác với user trong môi trường restore.
- Archive được giải nén nhưng mất owner, permission, ACL hoặc extended attributes.
- Container chạy với UID khác nhưng volume vẫn giữ owner của host.
- User namespace ánh xạ UID/GID khác với môi trường tạo checkpoint.
- Đường dẫn tuyệt đối của file hoặc mount point không tồn tại khi restore.
- Symlink được bảo toàn nhưng đích của nó không có hoặc trỏ sang dữ liệu khác.
- SELinux label hoặc AppArmor policy chặn truy cập dù permission bits trông có vẻ đúng.
- Ảnh được giải nén vào filesystem khác, nơi không hỗ trợ metadata hoặc hành vi cần thiết.

Các lỗi này có thể xuất hiện ở giai đoạn đọc ảnh, tạo lại file descriptor hoặc khi ứng dụng tiếp tục chạy sau restore. Vì vậy, cần kiểm tra cả thao tác restore lẫn các thao tác nghiệp vụ sau đó.

### Phân biệt quyền của ảnh và quyền của tài nguyên ứng dụng

Có hai nhóm quyền cần xem xét riêng:

1. **Quyền trên thư mục checkpoint**: cho phép runtime tạo ảnh, lưu các tệp con, đọc ảnh và thực hiện restore.
2. **Quyền trên tài nguyên ứng dụng**: cho phép tiến trình sau restore truy cập log, file dữ liệu, certificate, thư mục tạm, Unix socket hoặc volume mà ứng dụng cần.

Cho phép đọc ảnh không đồng nghĩa ứng dụng có quyền ghi log hoặc mở lại file dữ liệu. Ngược lại, cấp quyền cho thư mục dữ liệu không giúp runtime đọc được checkpoint nếu thư mục ảnh bị chặn.

## 2. UID, GID và permission bits trên Linux

Linux xác định quyền truy cập dựa trên UID của tiến trình, các GID mà tiến trình thuộc về, permission bits của đối tượng filesystem và các cơ chế kiểm soát bổ sung.

Ví dụ:

~~~bash
id
id myapp
stat -c '%u:%g %a %n' /var/lib/myapp/crac
~~~

Lệnh `id` cho biết UID, primary GID và supplementary groups của user. `stat` hiển thị owner, group và permission mode của đường dẫn.

### Ý nghĩa của quyền trên file và thư mục

| Quyền | Trên file | Trên thư mục |
|---|---|---|
| Read (`r`) | Đọc nội dung | Liệt kê tên các entry |
| Write (`w`) | Thay đổi nội dung | Tạo, xóa hoặc đổi tên entry nếu các điều kiện khác cho phép |
| Execute (`x`) | Chạy file nếu định dạng và chính sách cho phép | Traverse/search thư mục để truy cập entry bên trong |

Một user có quyền đọc file nhưng không có quyền `x` trên một thư mục cha vẫn không thể truy cập file qua đường dẫn đó. Vì thế, kiểm tra riêng permission của file ảnh là chưa đủ; cần kiểm tra toàn bộ chuỗi thư mục.

Ví dụ:

~~~bash
namei -l /var/lib/myapp/crac/release-001
~~~

`namei -l` hiển thị từng thành phần trên đường dẫn và quyền tương ứng. Đây là cách hữu ích để tìm thư mục cha đang chặn truy cập.

### Chọn owner và mode tối thiểu

Thư mục chứa ảnh thường nên được sở hữu bởi user hoặc group chuyên dụng của ứng dụng. Quyền truy cập chỉ nên cấp cho những thành phần cần tạo, đọc hoặc quản lý ảnh.

Ví dụ tạo thư mục cha:

~~~bash
sudo install -d -o myapp -g myapp -m 0700 /var/lib/myapp/crac
~~~

Lệnh này tạo thư mục với owner `myapp`, group `myapp` và quyền chỉ owner có thể truy cập. Nếu một tiến trình backup hoặc restore chạy bằng group riêng, thiết kế quyền cần phản ánh đúng mô hình vận hành; không mặc định `0700` phù hợp với mọi quy trình.

Không dùng `chmod -R 777` để sửa lỗi permission. Quyền đọc/ghi cho mọi user có thể làm lộ dữ liệu trong ảnh và cho phép tiến trình không liên quan sửa hoặc xóa trạng thái cần khôi phục.

## 3. Owner và group phải khớp với môi trường restore

Tên user hiển thị trong một máy không phải định danh lưu trong filesystem. Filesystem thường lưu UID/GID dạng số. Hai máy có thể cùng có user tên `myapp` nhưng UID khác nhau.

Ví dụ:

| Môi trường | User | UID | GID |
|---|---|---:|---:|
| Host tạo ảnh | myapp | 1001 | 1001 |
| Host restore | myapp | 2001 | 2001 |

Nếu archive bảo toàn numeric ownership, file có thể vẫn thuộc UID 1001 ở máy đích. User `myapp` có UID 2001 sẽ không tự động trở thành owner chỉ vì tên giống nhau.

Trước khi phân phối, xác định:

- UID/GID chạy JVM ở nguồn.
- UID/GID chạy JVM ở đích.
- Các supplementary group cần thiết.
- User của tiến trình tạo ảnh, chuyển ảnh, giải nén và restore.
- Quy tắc ownership của volume hoặc shared storage.

Có thể kiểm tra user/group ở hai môi trường bằng `id`. Khi cần, kiểm tra owner số bằng `stat` hoặc `ls -ln`; không chỉ dựa vào tên được phân giải từ `/etc/passwd`.

### Chọn một chính sách ownership rõ ràng

Có hai cách triển khai phổ biến:

**Giữ numeric UID/GID giống nhau.** Cấu hình user của ứng dụng có cùng UID/GID trên các host hoặc container liên quan. Cách này giảm nhu cầu đổi owner khi phân phối và giúp quyền filesystem nhất quán.

**Ánh xạ ownership tại đích.** Nếu UID/GID khác nhau, giải nén hoặc chuẩn bị volume với owner phù hợp với user restore. Chỉ thay owner trên bản sao đích và theo đúng chính sách bảo mật; không sửa ảnh nguồn đang được dùng bởi tiến trình khác.

Không đổi ownership một cách mù quáng. Một số tệp hoặc tài nguyên có thể cần owner khác với user chạy JVM; hãy căn cứ vào cách runtime và ứng dụng tạo chúng.

### Quyền của tiến trình restore

User chạy restore cần có quyền đọc toàn bộ ảnh và traverse các thư mục cha. Runtime có thể cần thêm quyền theo cơ chế checkpoint/restore của JDK, CRIU và hệ điều hành. Không giả định quyền đọc thông thường là đủ cho mọi cấu hình CRIU; đối chiếu yêu cầu của runtime và container.

Nếu thao tác restore chạy dưới một user khác với user tạo checkpoint, xác định rõ ai sở hữu ảnh và liệu tiến trình đó có thể truy cập các tài nguyên được phục hồi hay không.

## 4. Umask, ACL và extended attributes

Permission bits không phải metadata duy nhất của filesystem.

### Umask

Umask loại bỏ một số quyền mặc định khi tiến trình tạo file hoặc thư mục. Vì vậy, cùng một lệnh tạo file có thể cho kết quả permission khác nhau giữa hai môi trường.

Kiểm tra:

~~~bash
umask
~~~

Nếu runtime hoặc script tạo ảnh dưới umask khác nhau, các file mới có thể nhận mode khác. Không nên phụ thuộc vào umask mặc định của shell hoặc service manager; hãy cấu hình quyền rõ ràng và xác minh sau khi tạo ảnh.

### POSIX ACL

ACL có thể cấp quyền bổ sung cho user/group ngoài owner và group truyền thống. Một file có mode hiển thị `640` vẫn có thể có ACL entry ảnh hưởng đến quyền hiệu lực.

Kiểm tra:

~~~bash
getfacl -p /var/lib/myapp/crac
~~~

Khi phân phối, cần xác định ACL có phải được giữ lại hay cần tạo lại theo chính sách ở đích. Nếu công cụ archive không bảo toàn ACL, kết quả giải nén có thể thay đổi quyền truy cập.

### Extended attributes và file capabilities

Filesystem có thể lưu extended attributes (xattrs), security labels hoặc file capabilities. Một số công cụ đóng gói không bảo toàn chúng theo mặc định.

Có thể kiểm tra xattrs bằng:

~~~bash
getfattr -d -m- /var/lib/myapp/crac
~~~

Không tự ý thêm file capability hoặc security attribute vào ảnh. Chỉ bảo toàn những metadata cần thiết và được chính sách triển khai cho phép.

## 5. SELinux, AppArmor và các chính sách bảo mật

Permission bits đúng không bảo đảm truy cập sẽ thành công. Linux có thể áp dụng cơ chế Mandatory Access Control như SELinux hoặc AppArmor.

### SELinux

SELinux gắn security context vào file và tiến trình. Một file được owner cho phép đọc vẫn có thể bị từ chối nếu label không phù hợp với domain của service.

Kiểm tra context:

~~~bash
ls -Z /var/lib/myapp/crac
~~~

Kiểm tra policy và log AVC theo quy trình quản trị của hệ thống. Khi chuyển ảnh sang host khác, label có thể không còn phù hợp với policy ở đích. Thông thường, cần gán label theo policy của host đích thay vì cố sao chép nguyên label từ host nguồn.

Không tắt SELinux chỉ để làm checkpoint/restore chạy được. Xác định đúng đường dẫn, file type và policy cần thiết, rồi cấp quyền tối thiểu.

### AppArmor

AppArmor kiểm soát truy cập theo profile của tiến trình. Profile có thể cho phép service đọc một đường dẫn ở nguồn nhưng chặn đường dẫn staging hoặc restore ở đích.

Kiểm tra profile đang áp dụng và log denial. Nếu cần cập nhật profile, giới hạn rule vào đúng thư mục checkpoint và các tài nguyên ứng dụng phải truy cập.

### Container security policy

Trong container, còn có thể có:

- User namespace và UID/GID mapping.
- Read-only root filesystem.
- Seccomp profile.
- Capability set.
- Mount propagation và bind mount.
- Cgroup và giới hạn tài nguyên.
- SELinux label hoặc AppArmor profile của container.

Không dùng `--privileged` như một cách sửa lỗi quyền chung. Xác định chính xác quyền cần thiết cho CRIU, JDK và thao tác filesystem, sau đó cấu hình phạm vi nhỏ nhất có thể.

## 6. Đường dẫn tuyệt đối và cấu trúc thư mục cần giữ

Ảnh checkpoint thường được lưu trong một thư mục có cấu trúc do runtime và công cụ checkpoint tạo ra. Khi phân phối, phải giữ nguyên toàn bộ cây thư mục và tên các tệp con. Không đổi tên tùy ý từng file bên trong ảnh.

Đường dẫn checkpoint nên được xác định rõ trong cấu hình:

~~~bash
java -XX:CRaCCheckpointTo=/var/lib/myapp/crac/release-001 -jar app.jar
~~~

Khi restore:

~~~bash
java -XX:CRaCRestoreFrom=/var/lib/myapp/crac/release-001
~~~

Tên tùy chọn và hành vi có thể phụ thuộc bản phân phối JDK CRaC. Kiểm tra tài liệu của đúng runtime trước khi dùng.

### Vì sao nên dùng đường dẫn tuyệt đối?

Đường dẫn tương đối phụ thuộc working directory. Service manager, container entrypoint và script có thể đặt working directory khác nhau. Đường dẫn tuyệt đối giúp quy trình tạo ảnh, chuyển ảnh và restore thống nhất hơn.

Không chỉ ghi lại đường dẫn checkpoint. Cần ghi cả những đường dẫn ứng dụng đang sử dụng, ví dụ:

- Thư mục cấu hình.
- Thư mục log.
- Thư mục dữ liệu.
- Thư mục tạm.
- Certificate, trust store và key file.
- Native library và file mapping.
- Unix domain socket hoặc mount point của dịch vụ nội bộ.

Không phải mọi đường dẫn đều bắt buộc phải giống nhau trong mọi trường hợp. Tuy nhiên, nếu tiến trình hoặc thư viện đang giữ file descriptor, memory mapping hay trạng thái phụ thuộc vào path, môi trường restore phải đáp ứng yêu cầu tương ứng.

### Mount point và volume

Trong container, cùng một path có thể được cung cấp từ volume khác nhau. Ví dụ `/var/lib/myapp/data` ở nguồn là persistent volume, nhưng ở đích lại là thư mục rỗng trong writable layer. Restore có thể thành công nhưng ứng dụng đọc nhầm dữ liệu hoặc không tìm thấy file.

Ghi lại mount table và source của volume:

~~~bash
findmnt
findmnt -T /var/lib/myapp/data
~~~

Ở môi trường restore, mount đúng volume vào đúng path trước khi khởi động restore. Xác minh filesystem, owner, mode và dữ liệu bên trong. Nếu volume được thay thế, cần có kế hoạch tương thích dữ liệu thay vì chỉ tạo một thư mục cùng tên.

## 7. Symlink, hard link và file mapping

Một đường dẫn có thể chứa symlink. Bảo toàn symlink chỉ bảo toàn chuỗi đích mà symlink trỏ đến; nó không bảo đảm đích tồn tại hoặc giống nguồn.

Kiểm tra:

~~~bash
find /var/lib/myapp -type l -printf '%p -> %l\n'
readlink -f /var/lib/myapp/current
~~~

Trước khi restore, xác minh:

- Symlink cần thiết vẫn tồn tại.
- Đường dẫn đích có mặt.
- Đích có owner và permission phù hợp.
- Symlink không vô tình trỏ ra ngoài vùng filesystem được phép.
- Không có symlink bị thay đổi để trỏ sang dữ liệu khác hoặc đường dẫn không an toàn.

Hard link có thể khiến nhiều tên file cùng tham chiếu một inode. Nếu công cụ đóng gói không bảo toàn hard link, bản giải nén có thể tạo ra các bản sao độc lập. Với dữ liệu phụ thuộc vào hard link, cần chọn công cụ và tùy chọn bảo toàn phù hợp.

Memory-mapped file và file descriptor đang mở có thể có yêu cầu riêng khi checkpoint/restore. Đừng giả định chỉ cần tạo lại một file cùng tên là đủ. Cần kiểm tra inode, mount, file content và cách CRIU xử lý file đó theo cấu hình thực tế.

## 8. Đóng gói ảnh và bảo toàn metadata

Chỉ đóng gói sau khi checkpoint đã hoàn tất thành công và runtime không còn ghi vào thư mục ảnh. Không archive một thư mục đang được tạo hoặc đang được cập nhật.

### Dùng tar khi cần bảo toàn metadata

Trên Linux, GNU tar có các tùy chọn bảo toàn owner, ACL, xattrs và SELinux context:

~~~bash
tar --numeric-owner --acls --xattrs --selinux \
    -cpf release-001.tar \
    -C /var/lib/myapp/crac release-001
~~~

Tùy chọn hỗ trợ và hành vi phụ thuộc phiên bản tar, quyền của user và filesystem. Khi giải nén, có thể cần quyền phù hợp để phục hồi numeric ownership và metadata:

~~~bash
sudo tar --numeric-owner --same-owner --acls --xattrs --selinux \
    -xpf release-001.tar \
    -C /var/lib/myapp/crac
~~~

Nếu môi trường đích dùng SELinux policy khác, có thể cần gán lại label theo policy đích sau khi giải nén. Không giữ label nguồn một cách máy móc nếu nó không phù hợp.

### Dùng rsync để chuyển cây thư mục

Nếu chuyển trực tiếp giữa các filesystem hoặc host, rsync có thể bảo toàn nhiều loại metadata:

~~~bash
rsync -aHAX --numeric-ids \
    /var/lib/myapp/crac/release-001/ \
    restore-host:/var/lib/myapp/crac/release-001/
~~~

Trong đó:

- `-a` bảo toàn các thuộc tính archive cơ bản như permission, timestamp, symlink và owner/group theo khả năng/quyền.
- `-H` bảo toàn hard link.
- `-A` bảo toàn ACL.
- `-X` bảo toàn extended attributes.
- `--numeric-ids` dùng UID/GID dạng số thay vì ánh xạ theo tên user/group.

Các tùy chọn owner/group có thể cần quyền root ở nguồn hoặc đích. Filesystem đích cũng phải hỗ trợ metadata tương ứng. Nếu không thể bảo toàn một thuộc tính, hãy ghi nhận và áp dụng chính sách phục hồi metadata có chủ đích.

### Không chỉ copy các file nhìn thấy đầu tiên

Ảnh checkpoint có thể gồm nhiều tệp, thư mục con và metadata. Copy thiếu một phần, bỏ qua hidden file hoặc đổi cấu trúc có thể khiến restore thất bại. Dùng thao tác sao chép toàn bộ cây ảnh theo cách bảo toàn cấu trúc, rồi kiểm tra manifest/checksum và số lượng tệp.

Không chạy nhiều tác vụ đồng bộ vào cùng một thư mục ảnh. Tránh chỉnh sửa, nén lại hoặc đổi owner trong lúc một tiến trình restore đang đọc ảnh.

## 9. UID/GID mapping trong container và user namespace

Container có thể dùng user namespace để ánh xạ UID/GID bên trong container sang UID/GID khác trên host. Ví dụ, UID 1000 trong container có thể được ánh xạ thành UID 101000 trên host.

Điều này có nghĩa:

- `id` bên trong container có thể hiển thị UID 1000.
- `stat` trên host có thể hiển thị UID 101000.
- Volume được tạo từ host có thể không cho user trong container truy cập.
- Archive được giải nén trên host có thể cần owner số khác với owner nhìn thấy bên trong container.

Trước khi phân phối, xác định ảnh được tạo và restore trong cùng hay khác user namespace. Nếu mapping thay đổi, kiểm tra ownership của toàn bộ thư mục ảnh và tài nguyên ngoài ảnh.

Không tự đổi UID/GID của tất cả file trong cây checkpoint nếu chưa biết runtime có phụ thuộc metadata owner hay không. Một cách an toàn hơn là giữ mapping tương thích giữa nguồn và đích, hoặc thử nghiệm rõ ràng quy trình remap trên bản sao.

### Rootless container

Với rootless container, user trong container thường được ánh xạ vào một dải UID/GID của user chạy container trên host. Tiến trình có thể không có quyền `chown` tùy ý trên filesystem.

Hãy kiểm tra:

- UID/GID trong container.
- UID/GID mapping trên host.
- Owner của bind mount hoặc volume.
- Khả năng bảo toàn owner khi archive/unarchive.
- Quyền cần thiết của CRIU và runtime trong rootless mode.

Nếu không thể bảo toàn owner bằng thao tác thông thường, dùng cơ chế volume hoặc mapping được nền tảng hỗ trợ. Không giả định `sudo` bên trong container sẽ cấp quyền root thực trên host.

## 10. Những đường dẫn bên ngoài ảnh cần giữ

Checkpoint image không nhất thiết đóng gói mọi dữ liệu mà tiến trình cần. Nhiều tài nguyên được cung cấp từ filesystem, volume hoặc dịch vụ bên ngoài. Hãy lập danh sách đường dẫn phụ thuộc và xác định cách phân phối chúng.

| Đường dẫn/tài nguyên | Điều cần giữ hoặc xác minh |
|---|---|
| Thư mục checkpoint | Toàn bộ cấu trúc ảnh, owner, mode và metadata cần thiết |
| JDK/runtime | Đúng distribution/version và đường dẫn cài đặt tương thích |
| Native library | Binary đúng architecture, version và đường dẫn loader |
| File cấu hình | Nội dung và path phù hợp với môi trường restore |
| Certificate/trust store | File hiện hành, quyền đọc và chain hợp lệ |
| Thư mục dữ liệu | Cùng volume hoặc dữ liệu tương thích tại path mà ứng dụng dùng |
| Thư mục log | Tồn tại, có quyền ghi và không trỏ vào filesystem đã mất |
| Thư mục tạm | Có thể tạo file và có dung lượng phù hợp |
| Unix domain socket | Directory và endpoint được tạo lại bởi service owner |
| File lock | Không giữ lock cũ; thực hiện lại giao thức lock sau restore |
| Memory-mapped file | Path, inode/content và mount phù hợp với trạng thái cần khôi phục |

### Đường dẫn tuyệt đối trong trạng thái tiến trình

Một tiến trình có thể giữ working directory, root directory, file descriptor hoặc memory mapping. Một số trạng thái phụ thuộc đường dẫn hoặc mount namespace của môi trường tạo ảnh. Nếu restore trong môi trường có cấu trúc path khác, CRIU có thể không khôi phục được tài nguyên hoặc ứng dụng có thể hoạt động sai.

Ghi lại các mount và đường dẫn quan trọng trong manifest triển khai. Trước restore, tạo các mount cần thiết đúng vị trí. Nếu phải thay đổi path, cần xác minh cách runtime và ứng dụng hỗ trợ thay đổi đó; không chỉ rename thư mục ảnh để mong mọi tham chiếu được cập nhật.

### Không phân phối Unix socket như file thông thường

Unix domain socket là endpoint do một tiến trình/service tạo và quản lý. Việc copy một filesystem entry dạng socket không tạo ra server đang lắng nghe ở đích. Thông thường, service sở hữu socket phải khởi động và tạo lại endpoint sau restore; ứng dụng kết nối lại theo đường dẫn mới hoặc ổn định.

## 11. Bảo mật ảnh trong quá trình phân phối

Ảnh checkpoint có thể chứa dữ liệu trong heap và trạng thái tiến trình, bao gồm:

- Access token, password hoặc credential.
- Session và dữ liệu request.
- Thông tin cá nhân hoặc dữ liệu nghiệp vụ.
- Private key hoặc nội dung nhạy cảm đã được giải mã.
- Cache và dữ liệu nội bộ.

Hãy xem ảnh checkpoint như một bản sao dữ liệu nhạy cảm của ứng dụng.

### Giới hạn quyền truy cập

- Chỉ user/service cần thiết được đọc ảnh.
- Không đặt ảnh trong thư mục web public hoặc bucket public.
- Không commit ảnh vào Git hoặc đưa vào Docker build context.
- Không cấp quyền đọc cho mọi user trên host.
- Bảo vệ cả archive tạm, checksum manifest và bản sao lưu.
- Dùng retention policy và xóa an toàn theo chính sách dữ liệu.

### Mã hóa khi lưu và truyền

Dùng kênh truyền được xác thực và mã hóa, ví dụ SSH/SFTP hoặc storage service có TLS. Nếu cần mã hóa at rest, áp dụng cơ chế mã hóa filesystem, volume hoặc artifact repository phù hợp.

Không gửi password hoặc private key trong command line/log. Quản lý khóa mã hóa bằng hệ thống secret/key management được phê duyệt. Bảo đảm chỉ môi trường restore được cấp quyền giải mã ảnh.

### Tách quyền tạo, phân phối và restore

Trong hệ thống lớn, có thể tách:

- Service runtime tạo checkpoint.
- Job đóng gói và ký manifest.
- Artifact store lưu bản phân phối.
- Restore worker tải, xác minh và giải nén.
- JVM restore chạy bằng user runtime chuyên dụng.

Mỗi thành phần chỉ nên có quyền cần thiết cho nhiệm vụ của nó. Ví dụ, job phân phối không cần quyền đọc database production nếu chỉ chuyển archive.

## 12. Kiểm tra tính toàn vẹn và nguồn gốc ảnh

Sau khi đóng gói, tạo checksum để phát hiện lỗi hoặc thay đổi ngoài ý muốn trong quá trình chuyển.

Ví dụ:

~~~bash
sha256sum release-001.tar > release-001.tar.sha256
~~~

Ở đích:

~~~bash
sha256sum -c release-001.tar.sha256
~~~

Checksum chứng minh dữ liệu nhận được khớp với dữ liệu đã tạo checksum; nó không chứng minh người gửi đáng tin cậy nếu checksum và archive được chuyển cùng một kênh không xác thực. Với quy trình phát hành nghiêm ngặt, ký manifest bằng khóa được quản lý riêng và xác minh chữ ký ở đích.

Manifest nên ghi:

- Checkpoint ID và thời điểm tạo.
- Application build/version.
- Dependency lockfile hoặc checksum artifact.
- JDK distribution/version và JVM flags.
- CRIU, kernel, OS và CPU architecture.
- UID/GID của tiến trình tạo ảnh và chính sách mapping.
- Đường dẫn checkpoint và mount quan trọng.
- Danh sách volume hoặc dữ liệu ngoài ảnh cần có.
- Kích thước archive và SHA-256.
- Trạng thái kiểm thử restore.

Không nhúng secret vào manifest. Ghi nhận tên/version của secret hoặc reference an toàn nếu cần truy vết, không ghi giá trị bí mật.

## 13. Quy trình phân phối có kiểm soát

~~~mermaid
flowchart TD
    A[Checkpoint hoàn tất] --> B[Đóng băng cây ảnh]
    B --> C[Thu thập metadata path và UID/GID]
    C --> D[Đóng gói bảo toàn metadata]
    D --> E[Tạo checksum và ký manifest]
    E --> F[Truyền qua kênh an toàn]
    F --> G[Kiểm tra chữ ký và checksum]
    G --> H[Giải nén vào staging]
    H --> I[Áp dụng owner, ACL và security label theo đích]
    I --> J[Kiểm tra path, mount và quyền]
    J --> K[Promote sang thư mục restore]
    K --> L[Restore và kiểm tra readiness]
~~~

### Bước 1 — Chờ checkpoint hoàn tất

Chỉ bắt đầu đóng gói khi runtime xác nhận checkpoint thành công. Không archive một thư mục còn đang được CRIU/JVM ghi. Nếu checkpoint thất bại, xác định ảnh có hoàn chỉnh không trước khi phân phối.

### Bước 2 — Thu thập metadata

Ghi owner, group, mode, ACL, xattrs, symlink và mount assumptions. Ghi phiên bản runtime, kiến trúc và đường dẫn mà tiến trình cần. Tạo một manifest bên ngoài ảnh.

### Bước 3 — Đóng gói

Dùng công cụ bảo toàn metadata phù hợp với filesystem nguồn và đích. Ghi lại phiên bản công cụ và tùy chọn đã dùng để có thể lặp lại quy trình.

### Bước 4 — Tạo checksum và ký

Tính checksum archive và ký manifest nếu quy trình yêu cầu xác thực nguồn gốc. Lưu chữ ký và metadata tách biệt với secret.

### Bước 5 — Truyền ảnh

Dùng kênh truyền được xác thực, mã hóa và có quyền truy cập giới hạn. Tránh ghi archive vào thư mục tạm có quyền quá rộng.

### Bước 6 — Xác minh ở đích

Kiểm tra checksum/chữ ký trước khi giải nén. Không restore archive có checksum sai hoặc nguồn gốc không xác định.

### Bước 7 — Giải nén và chuẩn bị metadata

Giải nén vào một thư mục staging riêng. Bảo toàn cấu trúc ảnh, sau đó điều chỉnh owner/ACL/security label theo mapping và policy của đích nếu cần. Không sửa trực tiếp archive gốc.

### Bước 8 — Kiểm tra path và mount

Xác minh mọi đường dẫn cần thiết, mount point, native library, cấu hình, volume và quyền truy cập. Kiểm tra cả user runtime thực tế, không chỉ user quản trị.

### Bước 9 — Promote và restore

Khi staging đã được xác minh, chuyển sang thư mục restore cuối cùng bằng thao tác atomic rename nếu staging và đích nằm trên cùng filesystem. Không đổi tên hoặc di chuyển cây ảnh trong lúc restore đang đọc.

### Bước 10 — Kiểm tra sau restore

Xác nhận JVM restore thành công, resource được phục hồi, ứng dụng truy cập được file và volume, listener mở đúng path/port và readiness chỉ bật sau khi dependency bắt buộc sẵn sàng.

## 14. Ví dụ kiểm tra quyền và đường dẫn trước restore

Giả sử ảnh được đặt tại:

~~~text
/var/lib/myapp/crac/release-001/
~~~

Trước restore, có thể kiểm tra:

~~~bash
id myapp
namei -l /var/lib/myapp/crac/release-001
stat -c '%u:%g %a %n' /var/lib/myapp/crac/release-001
getfacl -p /var/lib/myapp/crac/release-001
findmnt -T /var/lib/myapp/crac/release-001
~~~

Nếu dùng SELinux:

~~~bash
ls -Zd /var/lib/myapp/crac/release-001
~~~

Sau khi xác minh user và policy, chạy restore bằng đúng user/service manager và cấu hình runtime. Không chạy restore bằng root chỉ để vượt qua lỗi permission nếu ứng dụng được thiết kế để chạy bằng user không đặc quyền.

### Phân biệt lỗi permission và lỗi path

| Thông báo | Điều cần kiểm tra |
|---|---|
| `Permission denied` | Owner, mode, ACL, parent directory, SELinux/AppArmor và namespace |
| `No such file or directory` | Path, symlink target, mount và thứ tự khởi động volume |
| `Read-only file system` | Mount option, container rootfs và volume mode |
| `Operation not permitted` | Capability, user namespace, filesystem và policy bảo mật |
| `Invalid argument` khi phục hồi resource | Hành vi filesystem/kernel/runtime và metadata resource |

Không kết luận lỗi chỉ từ một thông báo. Đọc log của JVM, CRIU, kernel và container runtime để xác định thành phần từ chối thao tác.

## 15. Những lỗi phân phối thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Giải nén bằng user không có quyền bảo toàn owner | UID/GID thay đổi hoặc không đúng | Dùng quy trình restore metadata được cấp quyền phù hợp |
| Copy thiếu ACL/xattrs | Quyền hiệu lực hoặc security label thay đổi | Dùng công cụ có tùy chọn bảo toàn và kiểm tra sau copy |
| User name giống nhưng UID khác | Runtime không có quyền như nguồn | Đối chiếu numeric UID/GID hoặc remap có chủ đích |
| Đổi đường dẫn checkpoint | Runtime không tìm thấy ảnh hoặc cấu trúc con | Giữ nguyên cây ảnh và cấu hình restore path rõ ràng |
| Volume mount sai vị trí | Ứng dụng đọc dữ liệu khác hoặc không tìm thấy file | Kiểm tra mount table và manifest path |
| Symlink trỏ đến đích không tồn tại | Restore hoặc ứng dụng lỗi khi truy cập | Kiểm tra target và bảo toàn cấu trúc |
| Archive khi checkpoint chưa xong | Archive thiếu hoặc không nhất quán | Chờ xác nhận checkpoint hoàn tất |
| Restore trong lúc copy | Runtime đọc dữ liệu chưa đầy đủ | Chỉ promote sau khi copy và checksum thành công |
| SELinux/AppArmor chặn truy cập | Permission bits đúng nhưng vẫn bị từ chối | Kiểm tra policy và audit log |
| Đưa ảnh lên nơi công khai | Lộ dữ liệu trong bộ nhớ | Hạn chế quyền, mã hóa và retention |
| Restore trên filesystem không tương thích | Metadata hoặc hành vi file thay đổi | Kiểm tra filesystem và chạy thử restore |
| UID mapping khác trong rootless container | Owner trên host không khớp owner trong container | Kiểm tra user namespace mapping |

## 16. Kiểm thử phân phối và restore

Kiểm thử cần bao gồm cả việc chuyển ảnh giữa môi trường, không chỉ restore tại host đã tạo checkpoint.

### Kịch bản kiểm thử cơ bản

1. Chạy ứng dụng bằng user/group được chỉ định.
2. Ghi lại UID/GID, umask, permission, ACL, xattrs và mount của thư mục ảnh.
3. Tạo checkpoint và chờ thao tác hoàn tất.
4. Đóng gói toàn bộ cây ảnh bằng công cụ bảo toàn metadata.
5. Tạo checksum/manifest.
6. Chuyển archive sang môi trường đích.
7. Xác minh checksum và chữ ký.
8. Giải nén vào staging và kiểm tra owner, mode, ACL, xattrs, symlink.
9. Chuẩn bị đúng mount point, đường dẫn và security policy.
10. Restore bằng user runtime dự kiến.
11. Kiểm tra ứng dụng truy cập file, volume, log, certificate và dependency.
12. Xác nhận readiness và thao tác nghiệp vụ.

### Các tình huống bổ sung

| Tình huống | Điều cần xác minh |
|---|---|
| UID/GID giống nhau ở nguồn và đích | Quyền hiệu lực được bảo toàn |
| UID/GID khác nhau | Quy trình remap owner hoạt động đúng |
| Restore trong rootless container | Mapping và volume permission phù hợp |
| ACL/xattrs có sử dụng | Metadata được giữ hoặc tái tạo đúng |
| SELinux bật ở đích | Label/policy cho phép truy cập cần thiết |
| Mount point khác nguồn | Restore bị từ chối an toàn hoặc path được hỗ trợ rõ ràng |
| Symlink trỏ ra ngoài cây ảnh | Target tồn tại và không vượt chính sách |
| Checksum không khớp | Artifact bị từ chối trước restore |
| Thiếu dung lượng hoặc inode | Quy trình phát hiện trước khi giải nén |
| File dữ liệu ngoài ảnh không có | Readiness không bật và lỗi được báo rõ |

Không dùng một bài test chỉ chạy bằng root để kết luận quyền của user runtime đã đúng. Kiểm thử với user, group, namespace và policy thực tế.

## 17. Checklist trước khi phân phối checkpoint

### Ownership và quyền

- [ ] Đã ghi UID/GID của user tạo checkpoint và user restore.
- [ ] Đã xác định numeric UID/GID mapping trong container hoặc user namespace.
- [ ] Owner, group và permission bits của cây ảnh được bảo toàn hoặc remap có chủ đích.
- [ ] Đã kiểm tra quyền traverse của tất cả thư mục cha.
- [ ] ACL, xattrs và file capabilities được xử lý theo chính sách.
- [ ] SELinux/AppArmor policy cho phép đúng phạm vi truy cập.
- [ ] Không cấp quyền rộng như `777` hoặc dùng root không cần thiết.

### Đường dẫn và filesystem

- [ ] Đã giữ nguyên cấu trúc cây checkpoint.
- [ ] Đã ghi đường dẫn tuyệt đối và working directory cần thiết.
- [ ] Các mount point và volume phụ thuộc được chuẩn bị ở đích.
- [ ] Symlink và hard link được bảo toàn theo nhu cầu.
- [ ] File mapping, file descriptor và Unix socket có kế hoạch xử lý.
- [ ] Filesystem đích hỗ trợ metadata và hành vi cần thiết.
- [ ] Đường dẫn dữ liệu, cấu hình, log, certificate và native library đã được xác minh.

### Đóng gói và bảo mật

- [ ] Chỉ đóng gói sau khi checkpoint hoàn tất.
- [ ] Công cụ archive/transfer bảo toàn metadata cần thiết.
- [ ] Checksum và manifest được tạo; chữ ký được xác minh nếu quy trình yêu cầu.
- [ ] Kênh truyền và nơi lưu ảnh được xác thực, mã hóa và giới hạn quyền.
- [ ] Archive tạm và bản sao lưu được bảo vệ như dữ liệu nhạy cảm.
- [ ] Không phân phối ảnh đang được sửa hoặc đang được restore.

### Restore ở đích

- [ ] Checksum/chữ ký hợp lệ trước khi giải nén.
- [ ] Owner, permission, ACL và security label đã được xác minh.
- [ ] User runtime có quyền đọc ảnh và truy cập tài nguyên ứng dụng.
- [ ] Mount, path và dependency bên ngoài tồn tại đúng vị trí.
- [ ] Đã thử restore bằng đúng user và cấu hình production-like.
- [ ] Readiness chỉ mở sau khi ứng dụng và dependency đã phục hồi.

Phân phối checkpoint CRaC là việc chuyển cả dữ liệu ảnh lẫn các giả định về filesystem và môi trường đã tạo ra nó. Bảo toàn UID/GID, permission, ACL, xattrs, symlink, mount và đường dẫn giúp runtime có thể truy cập đúng dữ liệu; manifest, checksum và kênh truyền an toàn giúp xác minh nguồn gốc và tính toàn vẹn; còn kiểm thử bằng đúng user/container ở đích chứng minh ảnh thực sự có thể restore. Khi các yếu tố này được quản lý cùng nhau, checkpoint mới có thể được đóng gói và chuyển giao một cách lặp lại, an toàn và đáng tin cậy.
