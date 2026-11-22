# Hệ thống tệp, mount và tài nguyên bắt buộc phải có khi restore

CRaC (Coordinated Restore at Checkpoint) lưu trạng thái của một tiến trình Java để có thể khôi phục tiến trình đó trong một môi trường chạy tương thích. Heap và trạng thái thực thi có thể được phục hồi từ checkpoint image, nhưng các hệ thống tệp, mount, volume, quyền truy cập và dịch vụ bên ngoài vẫn thuộc môi trường vận hành.

Một đối tượng Path được lưu trong heap chỉ là thông tin định vị. Nó không mang theo nội dung tệp, mount point, quyền truy cập hay bảo đảm rằng tệp ở vị trí đó vẫn là cùng một tệp sau restore. Tương tự, một file descriptor đang mở có thể phụ thuộc vào inode, filesystem, mount namespace và trạng thái kernel mà runtime checkpoint/restore phải xử lý.

Vì vậy, ứng dụng cần xác định những đường dẫn và tài nguyên bắt buộc, bảo đảm chúng tồn tại trong môi trường restore, xác minh danh tính và nội dung trước khi tiếp tục công việc, đồng thời mở lại các tài nguyên có vòng đời phụ thuộc hệ điều hành.

## 1. Phân biệt checkpoint image và dữ liệu trên filesystem

Checkpoint image lưu trạng thái tiến trình theo khả năng của runtime và cơ chế checkpoint bên dưới. Nó không nên được xem như một bản sao lưu toàn bộ filesystem của máy chủ.

Có thể chia dữ liệu thành các nhóm:

| Nhóm | Ví dụ | Cách xử lý khi restore |
|---|---|---|
| Trạng thái trong heap | Object, cấu hình đã nạp, offset ứng dụng, cache | Được phục hồi theo checkpoint image |
| Tệp ứng dụng bên ngoài | File input, file output, log, manifest | Phải còn truy cập được và được xác minh |
| Tệp thực thi và thư viện | JAR, native library, config, certificate | Môi trường restore phải cung cấp phiên bản tương thích |
| Tài nguyên kernel | File descriptor, socket, lock, pipe, device handle | Phụ thuộc khả năng checkpoint/restore và cần kiểm tra |
| Mount và volume | Bind mount, PVC, NFS, tmpfs | Phải có topology và quyền phù hợp trong môi trường restore |
| Dịch vụ ngoài tiến trình | Database, object storage, secret manager | Phải sẵn sàng hoặc có quy trình kết nối lại |

Ví dụ, ứng dụng giữ:

~~~java
Path dataPath = Path.of("/var/lib/myapp/events.dat");
long savedOffset = 1024 * 1024;
~~~

Checkpoint có thể lưu hai giá trị này trong heap. Nhưng nó không bảo đảm đường dẫn **/var/lib/myapp/events.dat** sẽ tồn tại, có cùng nội dung hoặc được mount từ cùng volume sau restore.

Một cách nghĩ an toàn là: checkpoint khôi phục trạng thái tiến trình; hệ thống triển khai phải cung cấp lại môi trường và tài nguyên mà trạng thái đó cần để tiếp tục.

## 2. Đường dẫn tuyệt đối, tương đối và working directory

Một đường dẫn tương đối được phân giải theo working directory của tiến trình. Nếu working directory khác giữa lúc checkpoint và restore, cùng một chuỗi path có thể trỏ đến một vị trí khác.

Ví dụ:

~~~java
Path path = Path.of("data/events.dat");
~~~

Nếu tiến trình chạy với working directory **/opt/service**, đường dẫn được hiểu là:

~~~text
/opt/service/data/events.dat
~~~

Nếu restore từ một thư mục làm việc khác, đường dẫn tương đối có thể trỏ sang file khác hoặc không tìm thấy file.

Với tài nguyên bắt buộc, nên dùng cấu hình đường dẫn rõ ràng và xác định working directory trong môi trường triển khai. Có thể chuyển đường dẫn tương đối thành đường dẫn tuyệt đối khi khởi tạo:

~~~java
Path configured = Path.of(System.getenv("APP_DATA_DIR"));
Path dataDirectory = configured.toAbsolutePath().normalize();
Path inputFile = dataDirectory.resolve("events.dat");
~~~

toAbsolutePath() chỉ chuyển path theo working directory hiện tại; nó không xác nhận filesystem hoặc mount sẽ tồn tại sau restore. Ứng dụng vẫn cần kiểm tra quyền và danh tính tệp.

### Không dựa vào path string như định danh tệp

Hai đường dẫn khác nhau có thể trỏ đến cùng một file qua symlink hoặc hard link. Ngược lại, cùng một path có thể trỏ đến file khác nếu file đã bị thay thế.

Ví dụ:

~~~text
/var/lib/myapp/current/events.dat
                 |
                 +---- symlink -> /mnt/data/generation-42/events.dat
~~~

Sau một lần deploy, symlink current có thể được đổi sang generation mới. Path string vẫn giống nhau nhưng dữ liệu đã khác.

Khi tệp cần giữ nguyên qua checkpoint, nên lưu thêm metadata nhận diện và kiểm tra sau restore thay vì chỉ so sánh chuỗi path.

## 3. Mount point và mount namespace

Mount point là vị trí trong cây thư mục nơi một filesystem hoặc thiết bị lưu trữ được gắn vào. Một đường dẫn chỉ có thể truy cập đúng dữ liệu khi mount tương ứng tồn tại trong namespace mà tiến trình nhìn thấy.

Trên Linux, mỗi tiến trình thuộc một mount namespace. Hai tiến trình có thể nhìn thấy các mount khác nhau dù chạy trên cùng host. Container thường dùng mount namespace riêng và ánh xạ volume từ host vào đường dẫn bên trong container.

Ví dụ:

~~~text
Host:
  /srv/volumes/customer-data

Container:
  /var/lib/myapp/data
       |
       +---- bind mount từ host /srv/volumes/customer-data
~~~

Ứng dụng chỉ biết path trong container. Khi restore, cần bảo đảm container hoặc môi trường khôi phục có mount tương ứng tại **/var/lib/myapp/data**.

Không thể chỉ kiểm tra rằng thư mục tồn tại. Nếu mount bị thiếu, đường dẫn có thể vẫn tồn tại dưới dạng thư mục rỗng trên filesystem gốc. Ứng dụng có thể vô tình ghi dữ liệu vào lớp writable của container thay vì volume dự kiến.

### Kiểm tra mount trên Linux

Một số lệnh hỗ trợ kiểm tra:

~~~bash
findmnt
findmnt -T /var/lib/myapp/data
cat /proc/self/mountinfo
df -h /var/lib/myapp/data
stat /var/lib/myapp/data
~~~

- findmnt -T cho biết filesystem chứa đường dẫn.
- /proc/self/mountinfo mô tả các mount nhìn thấy trong mount namespace hiện tại.
- df hiển thị filesystem và dung lượng.
- stat cung cấp metadata của file hoặc thư mục.

Các lệnh chỉ quan sát trạng thái tại thời điểm chạy. Cần chạy trong đúng container hoặc namespace mà tiến trình restore sẽ sử dụng, không chỉ kiểm tra trên host.

### Mount topology phải tương thích

Một số runtime checkpoint/restore có thể cần khôi phục file descriptor hoặc trạng thái kernel gắn với mount. Việc thay đổi mount namespace, thứ tự mount, filesystem hoặc đường dẫn có thể làm restore thất bại hoặc khiến ứng dụng truy cập sai dữ liệu.

Yêu cầu cụ thể phụ thuộc JDK CRaC, CRIU, kernel, container runtime và cách triển khai. Cần tuân theo hướng dẫn của runtime đang dùng và giữ topology cần thiết ổn định.

## 4. Volume bền vững và storage tạm thời

Không phải mọi filesystem đều có cùng vòng đời.

| Loại storage | Ví dụ | Rủi ro sau restore |
|---|---|---|
| Persistent volume | Disk gắn lâu dài, cloud block volume, PVC | Có thể giữ dữ liệu nhưng cần attach và mount đúng volume |
| Host bind mount | Thư mục host gắn vào container | Phụ thuộc host path và mount namespace |
| Container writable layer | Lớp filesystem riêng của container | Có thể mất khi container bị thay thế |
| tmpfs | /run, một số /tmp, memory-backed volume | Nội dung có thể không tồn tại sau khi tạo môi trường mới |
| Kubernetes emptyDir | Volume tạm gắn với vòng đời Pod | Không phải storage bền vững qua việc tạo Pod mới |
| Network filesystem | NFS, SMB, EFS, CephFS | Cần mạng, mount, quyền và semantics nhất quán |
| Object storage | S3-compatible, cloud object store | Không phải POSIX filesystem; cần client và credential |

### Persistent volume

Với dữ liệu cần giữ qua restore, dùng storage có vòng đời bền vững và có quy trình attach/mount rõ ràng.

Cần xác minh:

- Đúng volume hoặc claim được gắn.
- Filesystem đã mount trước khi runtime cần khôi phục file descriptor.
- Đường dẫn trong container giống cấu hình của ứng dụng.
- UID/GID, ACL và mount option cho phép truy cập.
- Dung lượng còn đủ.
- Nội dung dữ liệu tương ứng với checkpoint generation.

Tên PVC hoặc tên volume giống nhau chưa đủ chứng minh dữ liệu là cùng một volume. Nên kiểm tra ID hoặc metadata của storage provider khi tính đúng đắn phụ thuộc vào volume identity.

### tmpfs và thư mục tạm

/tmp không mặc định là storage bền vững. Nó có thể là tmpfs hoặc bị dọn khi container/host khởi động lại. Java cũng có thể dùng java.io.tmpdir cho file tạm.

Nếu ứng dụng cần file tạm qua restore, phải xác định filesystem thực tế và vòng đời của nó. Thông thường, file tạm nên được tạo lại từ dữ liệu bền vững hoặc được tái tạo trong afterRestore() thay vì xem nội dung cũ là chắc chắn còn tồn tại.

### Kubernetes

Trong Kubernetes, cần phân biệt:

- PersistentVolumeClaim: yêu cầu storage bền vững.
- PersistentVolume: tài nguyên storage được cấp phát.
- emptyDir: storage tạm có vòng đời gắn với Pod.
- hostPath: phụ thuộc filesystem trên node.
- CSI volume: phụ thuộc driver và quy trình attach/mount của storage provider.

Nếu restore trong cùng Pod, một số volume có thể vẫn được mount. Nếu Pod được tạo mới hoặc chuyển sang node khác, điều kiện có thể khác. Không giả định checkpoint image tự mang theo PVC, emptyDir, hostPath hay dữ liệu của volume.

Hãy để orchestration bảo đảm volume đã attach và mount trước khi khởi chạy restore. Chỉ sau đó mới yêu cầu JVM khôi phục checkpoint.

## 5. Quyền truy cập và danh tính người dùng

Tệp tồn tại nhưng tiến trình không có quyền đọc hoặc ghi vẫn không thể sử dụng nó.

Những thuộc tính cần xem xét:

- UID và GID của tiến trình.
- Owner và group của file/directory.
- POSIX permission bits.
- POSIX ACL.
- SELinux label hoặc AppArmor policy.
- Mount option như ro, rw, noexec, nodev, nosuid.
- Umask và quyền mặc định khi tạo file.
- Quyền truy cập vào parent directory.

Để mở một file theo path, tiến trình thường cần quyền search/execute trên các thư mục cha và quyền đọc/ghi phù hợp trên file. Chỉ có quyền trên file nhưng không có quyền traverse directory vẫn có thể dẫn đến AccessDeniedException.

### Kiểm tra quyền trên Linux

~~~bash
id
namei -l /var/lib/myapp/data/events.dat
ls -ld /var/lib/myapp /var/lib/myapp/data
ls -l /var/lib/myapp/data/events.dat
getfacl /var/lib/myapp/data/events.dat
~~~

Trong môi trường có SELinux, có thể cần kiểm tra context và policy tương ứng. Không nên xử lý lỗi bằng cách tắt SELinux hoặc mở quyền 777 cho toàn bộ thư mục. Hãy cấp quyền tối thiểu cho đúng user/group và mount.

### UID/GID trong container

Container có thể chạy với UID/GID khác host. Một file thuộc user có UID 1000 trên host có thể không truy cập được bởi tiến trình container chạy UID 10001 nếu group hoặc ACL không cho phép.

Nếu dùng Kubernetes securityContext, runAsUser, runAsGroup và fsGroup có thể ảnh hưởng quyền volume. Cần kiểm tra hành vi của CSI driver và storage provider; không phải mọi filesystem đều áp dụng ownership theo cùng cách.

## 6. Symlink, hard link và file identity

Path có thể chứa symlink. Nếu symlink thay đổi giữa checkpoint và restore, ứng dụng có thể mở một file khác mà không nhận ra.

Có thể kiểm tra symbolic link:

~~~java
if (Files.isSymbolicLink(path)) {
    Path target = Files.readSymbolicLink(path);
}
~~~

Để lấy đường dẫn sau khi phân giải symlink:

~~~java
Path realPath = path.toRealPath();
~~~

toRealPath() yêu cầu path tồn tại và có thể ném IOException nếu target không truy cập được. Nó giúp kiểm tra target tại thời điểm gọi nhưng không khóa target để ngăn thay đổi sau đó.

Có thể đọc BasicFileAttributes:

~~~java
BasicFileAttributes attributes = Files.readAttributes(
    path,
    BasicFileAttributes.class
);

long size = attributes.size();
FileTime modified = attributes.lastModifiedTime();
Object fileKey = attributes.fileKey();
~~~

fileKey() có thể là null và tính ổn định phụ thuộc filesystem/provider. Không dùng riêng fileKey() như một ID portable giữa các host hoặc mount. Kết hợp metadata với checksum, generation ID hoặc manifest của ứng dụng.

Nếu yêu cầu giữ nguyên tệp, cần xác minh đúng đối tượng dữ liệu trước khi mở lại và tránh race condition giữa lúc kiểm tra với lúc sử dụng. Khi filesystem hỗ trợ, có thể mở file rồi đọc attributes từ chính handle đã mở để giảm nguy cơ path bị thay thế giữa các thao tác.

## 7. File descriptor và handle đang mở

Java stream, channel và RandomAccessFile thường giữ một file descriptor hoặc handle native bên dưới. Descriptor đó tham chiếu đến trạng thái kernel, không chỉ đến một chuỗi path.

Ví dụ:

~~~java
FileChannel channel = FileChannel.open(
    Path.of("/var/lib/myapp/events.dat"),
    StandardOpenOption.READ,
    StandardOpenOption.WRITE
);
~~~

Channel có thể giữ:

- Vị trí đọc/ghi hiện tại.
- Trạng thái mở của file.
- Tham chiếu tới file object trong kernel.
- Trạng thái lock hoặc mapping liên quan.
- Buffer và trạng thái của các lớp Java bọc bên ngoài.

Khả năng checkpoint/restore một file descriptor phụ thuộc loại descriptor và runtime. File descriptor cho regular file có thể được xử lý khác socket, pipe, device hoặc filesystem đặc biệt. Không nên giả định mọi handle sẽ tự phục hồi đúng.

### Chiến lược đóng và mở lại

Với nhiều ứng dụng, cách dễ kiểm soát là:

1. Ngừng thao tác đọc/ghi mới.
2. Hoàn tất batch hoặc record đang xử lý.
3. Flush writer và force dữ liệu nếu cần.
4. Lưu offset đã commit cùng metadata file.
5. Đóng channel trước checkpoint.
6. Sau restore, mở lại path.
7. Xác minh file identity, size và nội dung.
8. Đặt lại offset rồi tiếp tục.

Cách này tránh phụ thuộc vào việc runtime phải phục hồi một số handle cũ. Tuy nhiên, nếu checkpoint bị hủy, tiến trình ban đầu cũng cần mở lại channel. Khi ứng dụng gọi Core.checkpointRestore(), có thể bắt CheckpointException để thực hiện rollback. Không dùng afterRestore() làm callback rollback cho checkpoint bị hủy.

### Memory-mapped file

MappedByteBuffer ánh xạ một vùng file vào không gian địa chỉ tiến trình. Việc restore mapping phụ thuộc filesystem, file identity, offset, kích thước và khả năng xử lý mapping của runtime.

Không tự động giả định mapping cũ luôn hợp lệ nếu file đã bị thay thế hoặc truncate. Với dữ liệu cần bảo đảm, hãy đóng/giải phóng mapping theo khả năng API/runtime, mở lại file và xác minh trước khi tiếp tục. Một số API mapping có hạn chế trong việc unmap tường minh; cần kiểm tra tài liệu JDK và cách triển khai.

## 8. File lock và quyền sở hữu dữ liệu

Java cung cấp FileLock qua FileChannel:

~~~java
try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {

    // Vùng thao tác độc quyền theo semantics của filesystem.
}
~~~

File lock có thể là advisory trên một số hệ điều hành/filesystem. Nó không phải distributed lock có bảo đảm giống nhau trên mọi storage.

Khi checkpoint và restore, lock có thể phụ thuộc file descriptor, inode hoặc semantics của network filesystem. Nếu nhiều bản sao restore từ cùng image, mỗi bản sao có thể tin rằng nó đang giữ cùng một trạng thái lock được checkpoint. Hệ thống phải kiểm tra hành vi thực tế của runtime và filesystem.

Với công việc cần độc quyền giữa nhiều instance:

- Dùng database lease hoặc distributed lock có fencing token.
- Dùng lock file trên filesystem chỉ khi filesystem hỗ trợ semantics cần thiết và đã được kiểm thử.
- Xác định rõ ai là owner của file và khi nào lease hết hạn.
- Không chỉ dựa vào synchronized hoặc ReentrantLock, vì chúng chỉ phối hợp thread trong một JVM.
- Không mở nhiều writer nếu chưa có cơ chế điều phối.

Nếu lock được giải phóng trước checkpoint, hãy xác định cách lấy lại lock sau restore. Nếu checkpoint bị hủy, tiến trình gốc cần khôi phục quyền sở hữu theo chính sách của ứng dụng.

## 9. Network filesystem và mount từ xa

Network filesystem như NFS, SMB, EFS hoặc CephFS có thể cung cấp đường dẫn POSIX nhưng vẫn phụ thuộc vào network, server, client cache, lease và mount option.

Sau restore, cần xem xét:

- Network interface và route đã sẵn sàng chưa.
- DNS có phân giải đúng endpoint không.
- Remote storage server có hoạt động không.
- Mount đã được gắn trong namespace đúng chưa.
- Credential, Kerberos ticket hoặc secret có còn hiệu lực không.
- File lock và lease có còn hợp lệ không.
- Client cache có trả dữ liệu cũ không.
- Mount có chuyển sang stale hoặc hung state không.

Không phải mọi lỗi network filesystem đều có thể khắc phục bằng cách retry mở file. Một số thao tác I/O có thể bị treo theo timeout của kernel hoặc mount option. Đặt timeout ở tầng ứng dụng nếu API hỗ trợ và giữ readiness false khi storage bắt buộc chưa sẵn sàng.

### Kiểm tra filesystem type và mount options

Có thể xem filesystem và option bằng:

~~~bash
findmnt -T /mnt/shared-data -o TARGET,SOURCE,FSTYPE,OPTIONS
~~~

Ví dụ, cùng path /mnt/shared-data có thể được mount bằng NFS ở môi trường này và bằng local disk ở môi trường khác. Nếu ứng dụng phụ thuộc semantics của NFS hoặc file locking, chỉ so sánh path là không đủ.

### Object storage không phải POSIX mount

S3-compatible object storage thường được truy cập qua SDK/API. Nếu dùng FUSE để mount object storage, semantics về rename, locking, consistency và random write có thể khác filesystem POSIX.

Với object storage, nên lưu object key và version/ETag theo hợp đồng của dịch vụ. Sau restore, tạo lại client, nạp credential và xác minh version hoặc checksum của object. Không giả định file rename hay file lock hoạt động giống local disk.

## 10. Tệp cấu hình, secret và certificate

Ứng dụng có thể đọc các tệp sau khi khởi động:

- application properties hoặc YAML.
- truststore và keystore.
- TLS certificate và private key.
- credential hoặc token.
- file cấu hình native library.
- file mapping hoặc dữ liệu model.
- file chứa feature flag hoặc endpoint.

Nếu các giá trị đã được đọc vào heap trước checkpoint, restore có thể tiếp tục dùng bản cũ trong memory dù file trên disk đã thay đổi. Nếu tài nguyên cần được làm mới, cần đọc lại sau restore theo chính sách ứng dụng.

Đối với certificate và secret:

- Xác minh file tồn tại và có quyền tối thiểu.
- Không ghi nội dung secret vào log.
- Xác minh certificate chain, validity period và truststore.
- Xem xét credential có thể bị rotate trong thời gian checkpoint.
- Tạo lại client TLS nếu client giữ SSLContext hoặc connection pool cũ.
- Không mặc định file secret được mount lại đúng phiên bản nếu secret provider có cơ chế rotation.

Nếu ứng dụng cần một phiên bản cấu hình cụ thể, lưu version hoặc generation ID cùng trạng thái checkpoint. Sau restore, kiểm tra version hiện tại có tương thích không trước khi sử dụng.

## 11. Native library, device và tài nguyên hệ điều hành

Một số ứng dụng dùng JNI/JNA hoặc thư viện native để truy cập tài nguyên ngoài Java heap:

- .so hoặc shared library.
- Unix domain socket.
- Named pipe.
- Device file như /dev/...
- Shared memory.
- GPU hoặc accelerator handle.
- File descriptor do native code tạo.
- Native thread và mutex.

Những tài nguyên này có thể không được khôi phục theo cách một object Java thông thường được khôi phục. Khả năng hỗ trợ phụ thuộc runtime, CRIU, kernel, driver và thư viện native.

Trước khi chọn CRaC, hãy lập danh sách native resource và xác định:

1. Tài nguyên có được checkpoint/restore trực tiếp hỗ trợ không?
2. Nếu không, có thể đóng trước checkpoint và tạo lại sau restore không?
3. Có API close/destroy rõ ràng không?
4. Có phụ thuộc device hoặc driver chỉ có trên một host không?
5. Có cần nạp lại shared library hoặc khởi tạo native context không?
6. Tài nguyên có thể được tạo lại trước khi worker sử dụng không?

Ví dụ một native client nên có wrapper Java triển khai Resource. beforeCheckpoint() đóng native handle; afterRestore() tạo handle mới. Không giữ một con trỏ native cũ rồi giả định nó còn hợp lệ sau restore.

### Unix domain socket và device file

Một Unix domain socket path có thể vẫn tồn tại trên filesystem nhưng server socket hoặc connection tương ứng đã không còn hoạt động. File path không chứng minh endpoint đang lắng nghe.

Sau restore, cần tạo lại client socket hoặc kết nối đến service. Với device file, cần xác nhận device node, driver, permission và quyền container vẫn được cung cấp.

## 12. Dung lượng, inode và giới hạn file descriptor

Filesystem có thể tồn tại nhưng không còn đủ tài nguyên để tiếp tục.

Kiểm tra:

- Dung lượng còn trống.
- Inode còn trống.
- Quota của user/project.
- Giới hạn open file descriptor (ulimit -n hoặc RLIMIT_NOFILE).
- Giới hạn file size.
- Giới hạn memory mapping.
- Số lượng file tạm và file log.
- Dung lượng checkpoint image riêng với dung lượng application data.

Trên Linux:

~~~bash
df -h /var/lib/myapp
df -i /var/lib/myapp
ulimit -n
cat /proc/self/limits
~~~

Nếu ứng dụng mở nhiều file sau restore, có thể chạm giới hạn descriptor dù từng file đều tồn tại. Nên đóng handle cũ, giới hạn số file đồng thời và theo dõi lỗi Too many open files.

Không lưu checkpoint image vào cùng filesystem với dữ liệu quan trọng nếu điều đó khiến checkpoint tiêu thụ hết dung lượng. Dự trù dung lượng riêng và có cảnh báo trước khi đầy.

## 13. Xác minh tài nguyên bằng Java trước khi mở dịch vụ

Có thể tạo một thành phần kiểm tra các đường dẫn bắt buộc:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.List;

public final class RequiredFileValidator {
    private final List<Path> requiredFiles;

    public RequiredFileValidator(List<Path> requiredFiles) {
        this.requiredFiles = List.copyOf(requiredFiles);
    }

    public void validate() throws IOException {
        for (Path path : requiredFiles) {
            if (!Files.exists(path)) {
                throw new IOException(
                    "Required path does not exist: " + path
                );
            }

            if (!Files.isReadable(path)) {
                throw new IOException(
                    "Required path is not readable: " + path
                );
            }

            BasicFileAttributes attributes =
                Files.readAttributes(
                    path,
                    BasicFileAttributes.class
                );

            if (!attributes.isRegularFile()) {
                throw new IOException(
                    "Expected a regular file: " + path
                );
            }
        }
    }
}
~~~

Đây là ví dụ đơn giản. Với thư mục, mount point, socket hoặc device, cần kiểm tra loại tài nguyên tương ứng thay vì yêu cầu mọi path là regular file.

Files.exists() có thể trả về false khi trạng thái không xác định hoặc không có quyền truy cập. Nó cũng không xác nhận đúng volume hoặc đúng nội dung. Validator thực tế nên kiểm tra thêm:

- Path đã phân giải có nằm trong thư mục cho phép không.
- File identity hoặc volume ID có khớp không.
- Kích thước và checksum có đúng không.
- Filesystem type và mount source có phù hợp không.
- Có thể mở file bằng đúng mode mà ứng dụng cần không.
- Có thể tạo, ghi, flush và xóa file tạm nếu workload cần ghi không.

### Kiểm tra quyền ghi bằng file tạm

Files.isWritable() là kiểm tra sơ bộ; nó không bảo đảm thao tác ghi tiếp theo sẽ thành công. Khi cần xác nhận quyền ghi, có thể tạo file tạm trong đúng directory rồi xóa:

~~~java
Path probe = Files.createTempFile(dataDirectory, ".restore-check-", ".tmp");

try {
    Files.writeString(probe, "ready");
} finally {
    Files.deleteIfExists(probe);
}
~~~

Chỉ thực hiện phép thử này ở directory mà ứng dụng được phép ghi và bảo đảm tên file không xung đột. Nếu dữ liệu nhạy cảm, dùng nội dung kiểm tra vô hại và không ghi secret.

## 14. Resource callback để đóng và mở lại tệp

CRaC cung cấp interface Resource:

- beforeCheckpoint(): xử lý tài nguyên trước khi tạo checkpoint.
- afterRestore(): tạo lại hoặc xác minh tài nguyên sau khi restore.

Một Resource quản lý file có thể đóng channel trước checkpoint và mở lại sau restore.

~~~java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class FileResource implements Resource {
    private final Path path;

    private FileChannel channel;
    private long savedOffset;
    private boolean closedForCheckpoint;

    public FileResource(Path path) throws IOException {
        this.path = path.toAbsolutePath().normalize();
        open();
        Core.getGlobalContext().register(this);
    }

    private void open() throws IOException {
        channel = FileChannel.open(
            path,
            StandardOpenOption.READ,
            StandardOpenOption.WRITE
        );
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        // Caller phải drain writer và flush buffer trước.
        channel.force(true);
        savedOffset = channel.position();

        channel.close();
        channel = null;
        closedForCheckpoint = true;
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        reopenAndRestorePosition();
    }

    public synchronized void reopenAfterAbortedCheckpoint()
            throws IOException {
        if (closedForCheckpoint) {
            reopenAndRestorePosition();
        }
    }

    private void reopenAndRestorePosition() throws IOException {
        FileChannel reopened = null;

        try {
            reopened = FileChannel.open(
                path,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE
            );

            if (savedOffset < 0 || savedOffset > reopened.size()) {
                throw new IOException(
                    "Saved offset is outside the current file"
                );
            }

            reopened.position(savedOffset);
            channel = reopened;
            reopened = null;
            closedForCheckpoint = false;
        } finally {
            if (reopened != null) {
                reopened.close();
            }
        }
    }
}
~~~

Ví dụ giả định ứng dụng sở hữu file và đã drain mọi thao tác ghi. Trong thực tế, nên lưu thêm file identity, size, generation và checksum. Không chỉ kiểm tra offset nằm trong giới hạn; cần xác minh file vẫn là dữ liệu mà ứng dụng mong đợi.

Nếu beforeCheckpoint() đóng channel nhưng checkpoint bị hủy, tiến trình ban đầu tiếp tục. Khi ứng dụng gọi Core.checkpointRestore(), có thể bắt CheckpointException và gọi reopenAfterAbortedCheckpoint(). afterRestore() chỉ phục vụ tiến trình thực sự được restore.

Nếu checkpoint được yêu cầu bằng jcmd từ bên ngoài, luồng nghiệp vụ không có catch block quanh lời gọi API. Cần thiết kế resource và quy trình vận hành phù hợp với cách kích hoạt đó.

## 15. Kiểm tra mount và volume trước khi restore

Các mount bắt buộc nên được xác minh trước khi gọi lệnh restore, không chờ đến khi ứng dụng bắt đầu xử lý request.

Một trình tự vận hành tổng quát:

~~~text
Chuẩn bị node / container
        |
        v
Attach volume hoặc mount filesystem
        |
        v
Xác minh mount namespace và mount source
        |
        v
Xác minh UID/GID, ACL và mount options
        |
        v
Xác minh file, config, secret và native dependency
        |
        v
Khởi chạy restore từ checkpoint image
        |
        v
Resource.afterRestore()
        |
        v
Mở lại file / client / handle
        |
        v
Kiểm tra dữ liệu và readiness
        |
        v
Mở request listener và worker
~~~

Nếu runtime cần truy cập file descriptor hoặc mount trong lúc phục hồi process state, mount phải sẵn sàng trước bước restore. Callback afterRestore() không thể sửa một điều kiện mà runtime cần ngay từ giai đoạn đầu.

### Ví dụ lệnh kiểm tra trong container Linux

~~~bash
id
findmnt -T /var/lib/myapp/data
df -h /var/lib/myapp/data
df -i /var/lib/myapp/data
namei -l /var/lib/myapp/data/events.dat
test -r /var/lib/myapp/data/events.dat
test -w /var/lib/myapp/data
~~~

Chạy lệnh trong đúng container hoặc mount namespace sẽ thực hiện restore. Nếu orchestration tạo container mới, hãy kiểm tra sau khi volume đã được mount vào container mới.

## 16. Kiểm tra tương thích giữa môi trường checkpoint và restore

Không phải mọi khác biệt môi trường đều làm restore thất bại. Tuy nhiên, các thay đổi sau cần được đánh giá:

| Thành phần | Thay đổi có thể gây vấn đề |
|---|---|
| Đường dẫn | Working directory hoặc absolute path thay đổi |
| Mount namespace | Mount point thiếu hoặc trỏ sang volume khác |
| Filesystem | Loại filesystem hoặc mount option thay đổi |
| Volume | Attach nhầm volume, volume generation khác |
| Permissions | UID/GID, ACL hoặc SELinux context khác |
| File identity | Path trỏ sang file mới hoặc symlink khác |
| File content | Tệp bị sửa, truncate hoặc rotate |
| Native library | Phiên bản .so hoặc đường dẫn loader khác |
| Device | Device node, driver hoặc quyền container khác |
| Network mount | DNS, route, credential hoặc remote server chưa sẵn sàng |
| Resource limit | File descriptor, inode, quota hoặc dung lượng không đủ |

Nên ghi lại một manifest môi trường khi tạo checkpoint, gồm các thông tin cần thiết để đối chiếu. Manifest không cần chứa secret; chỉ lưu định danh hoặc version an toàn.

Ví dụ:

~~~text
checkpointGeneration = image-2026-11-13-001
applicationVersion   = 4.2.1
dataVolumeId         = volume-abc123
dataMountPath        = /var/lib/myapp/data
filesystemType       = ext4
dataFormatVersion    = 7
requiredConfigVersion= 18
nativeLibraryVersion = 2.4
~~~

Các giá trị trên chỉ minh họa. Tùy storage provider, volume ID có thể lấy từ API quản lý storage hoặc metadata do hệ thống triển khai cung cấp.

## 17. Khi filesystem thay đổi trong lúc ứng dụng được checkpoint

Một checkpoint có thể tồn tại trong thời gian dài trước khi restore. Trong thời gian đó, dữ liệu bên ngoài có thể thay đổi.

Ứng dụng cần định nghĩa chính sách theo loại dữ liệu:

| Loại dữ liệu | Chính sách |
|---|---|
| File cấu hình bất biến theo image | Yêu cầu version hoặc hash khớp |
| File input append-only | Xác minh prefix đã xử lý, sau đó tiếp tục từ offset |
| File output độc quyền | Xác minh vùng đã commit, xử lý phần đuôi theo quy tắc |
| Log có rotation | Xác định đúng generation/file identity |
| Secret hoặc certificate có rotation | Đọc lại phiên bản mới nếu chính sách cho phép |
| Shared directory | Dùng lock/lease hoặc giao thức phối hợp giữa writer |
| Object storage | Kiểm tra object version/ETag và tạo lại SDK client |

Không tự động ghi đè hoặc truncate file khác với trạng thái đã checkpoint. Nếu file identity hoặc checksum không khớp, giữ ứng dụng ở trạng thái chưa sẵn sàng và áp dụng chính sách reconcile rõ ràng.

## 18. Lỗi thường gặp và cách xử lý

### Path tồn tại nhưng mount volume bị thiếu

Thư mục mount point vẫn có thể tồn tại trên root filesystem. Ứng dụng mở được path nhưng đọc nhầm lớp writable của container.

Cách xử lý: kiểm tra mount source, filesystem type và volume identity bằng công cụ hệ điều hành. Không chỉ dùng Files.exists().

### Volume chưa attach khi restore bắt đầu

Runtime hoặc callback cần truy cập file nhưng volume chưa sẵn sàng.

Cách xử lý: điều phối attach/mount trước khi gọi restore. Dùng readiness gate để không mở traffic khi volume chưa được xác minh.

### Permission khác sau restore

Tiến trình có UID/GID khác hoặc storage provider áp dụng ACL khác.

Cách xử lý: xác minh user, group, ACL, SELinux label và mount options. Cấp quyền tối thiểu cần thiết.

### Path giống nhau nhưng dữ liệu khác

Symlink, bind mount hoặc volume được đổi sang generation khác.

Cách xử lý: so sánh volume ID, file identity, version, size và checksum. Không chỉ so sánh chuỗi path.

### Network filesystem bị stale hoặc mất kết nối

Mount còn hiển thị nhưng I/O bị lỗi hoặc treo do remote server/network.

Cách xử lý: xác minh network và storage server, đặt timeout phù hợp, retry có giới hạn và giữ ứng dụng not-ready khi dữ liệu bắt buộc không truy cập được.

### File lock không còn hợp lệ

Lock phụ thuộc file descriptor hoặc semantics của filesystem; sau restore có thể không đại diện quyền sở hữu hiện tại.

Cách xử lý: lấy lại lease/lock theo giao thức ngoài tiến trình và dùng fencing token nếu cần ngăn owner cũ tiếp tục ghi.

### File descriptor hoặc native handle không khôi phục được

Loại handle không được runtime hoặc kernel hỗ trợ.

Cách xử lý: đóng trước checkpoint và tạo lại sau restore nếu có API. Nếu tài nguyên không thể tạo lại hoặc không được hỗ trợ, cần thay đổi thiết kế hoặc môi trường triển khai.

### Hết dung lượng hoặc inode

Tệp vẫn tồn tại nhưng thao tác ghi mới thất bại.

Cách xử lý: kiểm tra df -h, df -i, quota và dung lượng dành riêng cho checkpoint image. Chỉ mở dịch vụ ghi sau khi xác nhận có đủ tài nguyên.

## 19. Thiết kế readiness theo tài nguyên bắt buộc

Không nên đánh dấu ứng dụng ready chỉ vì JVM đã restore thành công. Ứng dụng cần một trạng thái readiness phản ánh tài nguyên mà workload thực sự cần.

Ví dụ:

~~~text
RESTORING
    |
    v
CHECKING_MOUNTS
    |
    v
CHECKING_FILES
    |
    v
REOPENING_HANDLES
    |
    v
CHECKING_DEPENDENCIES
    |
    v
STARTING_WORKERS
    |
    v
READY
~~~

Nếu một bước thất bại:

~~~text
Bất kỳ bước kiểm tra nào
          |
          v
        FAILED
          |
          v
Giữ request gate đóng
          |
          v
Retry có giới hạn hoặc báo lỗi orchestration
~~~

Có thể chia resource thành:

- **Required:** thiếu thì không được phục vụ, ví dụ volume chứa dữ liệu chính hoặc certificate bắt buộc.
- **Optional:** có thể tắt một tính năng mà ứng dụng vẫn hoạt động, ví dụ thư mục cache có thể tái tạo.
- **Rebuildable:** có thể tạo lại từ nguồn dữ liệu khác, ví dụ cache hoặc file index.

Phân loại rõ giúp tránh dừng toàn bộ ứng dụng vì một cache có thể tái tạo, đồng thời tránh tiếp tục chạy khi volume dữ liệu chính bị thiếu.

## 20. Quy trình triển khai

### Khi chuẩn bị checkpoint

1. Liệt kê path, mount, volume, native library, device và network filesystem mà ứng dụng cần.
2. Phân loại tài nguyên required, optional và rebuildable.
3. Ngừng công việc mới và drain thao tác đang dùng file.
4. Flush và force dữ liệu cần durability.
5. Lưu offset, file identity, volume generation và checksum phù hợp.
6. Đóng channel, lock hoặc native handle nếu chọn chiến lược tạo lại sau restore.
7. Ghi lại manifest môi trường không chứa secret.
8. Hoàn tất callback beforeCheckpoint() sau khi các thành phần đã an toàn.

### Trước khi restore

1. Chuẩn bị đúng node, container và mount namespace.
2. Attach volume và mount filesystem cần thiết.
3. Xác minh volume ID, mount source, filesystem type và mount options.
4. Xác minh UID/GID, ACL, SELinux/AppArmor và quyền truy cập.
5. Cung cấp config, secret, certificate và native library đúng version.
6. Kiểm tra dung lượng, inode, quota và giới hạn descriptor.
7. Chỉ gọi restore khi các tài nguyên runtime bắt buộc đã sẵn sàng.

### Sau restore

1. Giữ request gate đóng.
2. Mở lại file, socket hoặc native handle cần tạo lại.
3. Xác minh file identity, version, size, checksum và offset.
4. Tạo lại client cho network filesystem hoặc object storage.
5. Lấy lại lease/lock theo giao thức ứng dụng.
6. Xác minh dependency và readiness.
7. Khởi động worker rồi mới mở traffic.

### Khi checkpoint bị hủy

Nếu ứng dụng gọi Core.checkpointRestore(), bắt CheckpointException và mở lại các handle đã đóng trong tiến trình ban đầu. Xác minh lại file và mount trước khi tiếp tục. Nếu rollback thất bại, giữ ứng dụng not-ready.

Nếu checkpoint được yêu cầu bằng jcmd từ bên ngoài, luồng nghiệp vụ không bắt được exception qua API. Cần quy trình vận hành tương ứng để nhận biết checkpoint thất bại và phục hồi tài nguyên.

## 21. Nguyên tắc cần ghi nhớ

- Checkpoint image không phải bản sao lưu toàn bộ filesystem hoặc volume.
- Path trong heap không bảo đảm file hoặc mount vẫn tồn tại sau restore.
- Kiểm tra mount trong đúng namespace mà tiến trình restore sẽ nhìn thấy.
- Phân biệt persistent volume với container writable layer, tmpfs và emptyDir.
- Giữ UID/GID, ACL, SELinux/AppArmor và mount option phù hợp.
- Xác minh volume identity và file identity; path string không đủ.
- Không giả định mọi file descriptor, lock, socket, device hoặc native handle đều được khôi phục an toàn.
- Với file quan trọng, lưu offset đã commit và metadata; mở lại rồi xác minh trước khi tiếp tục.
- Network filesystem cần kiểm tra mạng, server, lease, credential và semantics của filesystem.
- Secret, certificate và native library phải có version tương thích và quyền truy cập phù hợp.
- Chuẩn bị mount bắt buộc trước khi gọi restore nếu runtime cần chúng để khôi phục process state.
- Chỉ mở request gate khi mọi tài nguyên required đã sẵn sàng.
- Kiểm thử restore trong đúng container, node, filesystem và storage provider của môi trường triển khai.

Khả năng restore không chỉ phụ thuộc checkpoint image. Tiến trình còn cần nhìn thấy đúng filesystem, mount, volume, quyền và tài nguyên hệ điều hành để tiếp tục công việc. Khi chuẩn bị mount trước restore, xác minh identity và nội dung sau restore, đồng thời tạo lại các handle không thể giữ an toàn, ứng dụng có thể phát hiện sớm môi trường không tương thích và tránh ghi nhầm dữ liệu hoặc phục vụ khi tài nguyên bắt buộc chưa sẵn sàng.
