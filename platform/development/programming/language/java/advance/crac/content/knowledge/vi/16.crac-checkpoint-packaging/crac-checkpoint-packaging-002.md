# Cấu trúc bộ tệp checkpoint và yêu cầu bảo toàn tính đầy đủ

Checkpoint CRaC là ảnh chụp trạng thái của một tiến trình JVM đang chạy. Khi sử dụng engine dựa trên CRIU, kết quả thường là một thư mục chứa nhiều tệp ảnh tiến trình, dữ liệu bộ nhớ, thông tin thread, file descriptor và tài nguyên hệ điều hành. Các tệp này phối hợp với nhau để khôi phục cùng một process state; chúng không phải những phần độc lập có thể tùy ý chọn, đổi tên hoặc sao chép riêng lẻ.

Vì vậy, **tính đầy đủ của checkpoint là tính toàn vẹn của cả bộ tệp và môi trường mà bộ tệp phụ thuộc vào**. Chỉ cần thiếu một ảnh bộ nhớ, sai đường dẫn, mất quyền truy cập, thay đổi file được tham chiếu hoặc trộn dữ liệu của hai lần dump, restore có thể thất bại hoặc khôi phục tiến trình trong trạng thái không đúng.

Bài này trình bày cấu trúc thường gặp của checkpoint CRIU, cách phân biệt thư mục ảnh với gói triển khai, cách đóng gói và kiểm tra tính toàn vẹn, cùng các yêu cầu phải giữ khi chuyển checkpoint sang môi trường khác.

## 1. Checkpoint CRaC là một bộ dữ liệu có liên kết

Khi ứng dụng chạy với JDK hỗ trợ CRaC, JVM được khởi động cùng đường dẫn đích cho checkpoint:

~~~bash
java -XX:CRaCCheckpointTo=/var/lib/myapp/checkpoints/current \
     -jar app.jar
~~~

Sau khi ứng dụng đã khởi tạo, warm-up và chuẩn bị resource, có thể yêu cầu checkpoint bằng lệnh:

~~~bash
jcmd <PID> JDK.checkpoint
~~~

Với engine lưu ảnh trên Linux, CRIU thu thập trạng thái tiến trình và ghi ra một bộ image files. Đường dẫn `-XX:CRaCCheckpointTo` là thư mục chứa ảnh checkpoint. Cách bố trí cụ thể phụ thuộc JDK build, checkpoint engine, CRIU version, kernel và tài nguyên mà process đang sử dụng.

Restore sử dụng đường dẫn ảnh:

~~~bash
java -XX:CRaCRestoreFrom=/var/lib/myapp/checkpoints/current
~~~

Lệnh restore khôi phục tiến trình từ ảnh. Đây không phải thao tác chạy lại `app.jar` theo quy trình startup bình thường. Trạng thái JVM và ứng dụng được phục hồi từ checkpoint, sau đó CRaC gọi các callback `afterRestore` để ứng dụng kết nối lại những resource cần thiết.

### 1.1. API CRaC và checkpoint engine là hai lớp khác nhau

CRaC API thông báo cho ứng dụng về các giai đoạn trước checkpoint và sau restore. Cơ chế tạo ảnh thực tế được lựa chọn bởi runtime.

Trên OpenJDK CRaC, engine Linux thường dùng CRIU. Một số runtime hoặc vendor có thể cung cấp engine khác. Ví dụ, engine mô phỏng có thể kiểm tra chu kỳ callback mà không tạo một bộ tệp ảnh trên đĩa. Vì thế, không phải mọi lần chạy CRaC đều sinh ra thư mục có cùng cấu trúc.

Khi tài liệu này nói về các file như `inventory.img`, `core-*.img`, `pagemap-*.img` và `pages-*.img`, đó là các nhóm file thường gặp trong checkpoint dùng CRIU. Không xem tên file hoặc số lượng file trong ví dụ là một chuẩn cố định cho mọi engine và phiên bản.

### 1.2. Thư mục ảnh không đồng nghĩa với gói triển khai hoàn chỉnh

Cần phân biệt hai khái niệm:

- **Checkpoint image directory**: thư mục do engine tạo ra, chứa các dữ liệu cần thiết để restore process theo định dạng của engine.
- **Deployment bundle**: gói mà pipeline phát hành và triển khai, thường gồm checkpoint directory nguyên vẹn, manifest tương thích, checksum, tham chiếu tới application artifact/JDK image và hướng dẫn về mount hoặc runtime configuration.

JAR không phải là một file ảnh CRIU. Manifest triển khai cũng không thay thế ảnh tiến trình. Ngược lại, chỉ có thư mục checkpoint chưa chắc đã đủ để triển khai ở một host khác, vì process có thể phụ thuộc vào JDK, thư viện native, file được mount, network namespace và các điều kiện hệ điều hành.

## 2. Các nhóm tệp thường gặp trong checkpoint CRIU

CRIU chia trạng thái process thành nhiều image files. Một số tệp chứa metadata có cấu trúc, một số chứa dữ liệu bộ nhớ dạng trang hoặc dữ liệu thô. Các nhóm dưới đây giúp hiểu vai trò của bộ tệp; tên cụ thể và sự hiện diện của từng nhóm thay đổi theo checkpoint.

### 2.1. Inventory và thông tin tổng thể

`inventory.img` là ảnh mô tả tập image của lần dump. Nó chứa thông tin tổng quan mà CRIU sử dụng để nhận biết bộ ảnh.

Có thể hình dung inventory như mục lục của bộ checkpoint. Nó không thay thế các file memory, thread hoặc file descriptor mà process cần để khôi phục.

Các metadata khác có thể mô tả cây process, quan hệ giữa task/thread và những thuộc tính chung của lần dump. Tên file và cách tổ chức phụ thuộc CRIU version.

### 2.2. Trạng thái process và thread

CRIU cần khôi phục từng process/task cùng trạng thái thực thi của nó. Trong bộ ảnh có thể gặp các nhóm như:

- `core-<pid>.img`: trạng thái core của process/task, gồm thông tin register và trạng thái thực thi cần thiết.
- `pstree.img`: quan hệ process tree trong những layout có sử dụng file này.
- Các image liên quan đến thread/task: thông tin thread, signal, trạng thái và quan hệ giữa các task.
- Các image liên quan tới memory map: mô tả vùng địa chỉ ảo và ánh xạ bộ nhớ của process.

Không nên giả định một process Java chỉ cần một file core. Một JVM có nhiều thread, và checkpoint phải bảo toàn trạng thái của toàn bộ thread liên quan.

### 2.3. Memory map, pagemap và pages

Đây là nhóm dữ liệu quan trọng để khôi phục heap, stack, code và những vùng memory khác.

| Nhóm | Vai trò khái quát |
|---|---|
| `mm-*.img` hoặc metadata tương đương | Mô tả memory map và các vùng địa chỉ của process |
| `pagemap-*.img` | Mô tả các trang bộ nhớ được lưu và cách ánh xạ chúng vào vùng địa chỉ |
| `pages-*.img` | Chứa nội dung các trang memory được dump |
| Image liên quan đến VMA/file mapping | Mô tả ánh xạ file, quyền truy cập và thuộc tính vùng nhớ |

`pagemap` và `pages` có quan hệ với nhau. Một nhóm metadata cho biết dữ liệu trang nào cần được đặt vào vị trí nào; nhóm còn lại giữ nội dung trang. Thiếu một trong các thành phần cần thiết có thể khiến memory không được tái tạo đúng.

Không nên tự xóa các file `pages` chỉ vì chúng lớn, hoặc cho rằng có thể tạo lại chúng từ JAR. Chúng có thể chứa trạng thái heap, stack, class metadata, code và dữ liệu runtime tại thời điểm checkpoint.

### 2.4. File descriptor và file đang mở

Process có thể đang giữ file descriptor tới file, pipe, socket hoặc tài nguyên hệ điều hành khác. CRIU cần thông tin để tái tạo hoặc liên kết lại các descriptor này.

Một số nhóm thường gặp:

- `fdinfo-*.img`: thông tin file descriptor.
- `files.img` hoặc image metadata tương ứng: mô tả quan hệ giữa descriptor và resource.
- `reg-files.img`: thông tin về file thường được mở bằng system call.
- `ext-files.img`: thông tin file được xử lý qua cơ chế/plugin bên ngoài.
- Các image riêng cho pipe, eventfd, eventpoll, inotify và những loại descriptor khác.

Không phải mọi descriptor đều có thể được giữ nguyên. Đây là lý do CRaC Resource callback yêu cầu ứng dụng đóng hoặc chuẩn bị lại các resource như socket, connection, file handle và client session trước checkpoint.

Nếu file được mở vẫn cần tồn tại khi restore, đường dẫn và nội dung file phải đáp ứng yêu cầu của engine. Một image có thể ghi nhận file được tham chiếu thay vì đóng gói toàn bộ nội dung file vào bộ checkpoint.

### 2.5. Namespace, network và IPC

Process/container có thể phụ thuộc vào Linux namespace, network interface, route, socket, pipe, shared memory hoặc cơ chế IPC khác. CRIU có thể tạo các image cho những tài nguyên này.

Ví dụ về nhóm dữ liệu có thể xuất hiện:

- Namespace và thông tin mount.
- Network interface và route.
- Socket và trạng thái liên quan.
- Pipe và dữ liệu pipe.
- Shared memory và semaphore.
- Eventfd, eventpoll và inotify.
- Thông tin file system hoặc mount cần thiết.

Sự hiện diện của các file này phụ thuộc vào tài nguyên thực tế. Một ứng dụng không dùng pipe hoặc một loại IPC nào đó có thể không có image tương ứng. Không dùng danh sách file của một checkpoint khác làm điều kiện bắt buộc cho mọi checkpoint.

### 2.6. Raw image, auxiliary file và log

Không phải tất cả file đều cùng một định dạng. CRIU có image ở định dạng protobuf, image chứa payload nhị phân và file raw được tạo bởi công cụ hoặc plugin khác.

Ngoài image phục vụ restore, thư mục có thể có auxiliary data, thống kê hoặc log. Tên và cách sinh log phụ thuộc engine/runtime. Ví dụ, một số môi trường có thể ghi log dump vào thư mục ảnh; không giả định mọi runtime đều tạo cùng tên log.

Log giúp điều tra checkpoint thất bại, nhưng không thay thế image cần thiết. Ngược lại, có log không có nghĩa checkpoint đã hoàn tất thành công.

## 3. Minh họa cấu trúc thư mục

Một thư mục CRIU có thể trông gần giống ví dụ sau:

~~~text
crac-checkpoint/
├── inventory.img
├── pstree.img
├── core-1234.img
├── mm-1234.img
├── pagemap-1234.img
├── pages-1.img
├── fdinfo-1234.img
├── reg-files.img
├── files.img
├── pipes.img
├── pipes-data.img
├── ids-1234.img
├── stats-dump
├── dump.log
└── ...
~~~

Đây chỉ là sơ đồ minh họa. Một lần dump thực tế có thể có nhiều file hơn, ít file hơn hoặc dùng tên khác. PID trong tên file là ví dụ; nó không phải giá trị cố định.

Không dùng danh sách trên để tự tạo thư mục giả, đổi tên file hoặc loại bỏ file không xuất hiện trong sơ đồ. Cấu trúc thực tế do CRaC runtime và checkpoint engine tạo ra.

### 3.1. Vì sao không thể chỉ giữ inventory.img?

Inventory mô tả tập ảnh nhưng không chứa toàn bộ trạng thái cần khôi phục. Nếu chỉ giữ inventory mà bỏ `pages`, `core`, file descriptor hoặc image khác, CRIU không thể tái tạo process.

Tương tự, chỉ giữ file pages mà bỏ metadata ánh xạ cũng không đủ để biết dữ liệu cần được đặt vào vùng địa chỉ nào. Tính đầy đủ là quan hệ giữa các file, không phải sự tồn tại của một file cụ thể.

### 3.2. Không dùng số lượng file làm tiêu chí duy nhất

Hai checkpoint của cùng ứng dụng có thể khác số file vì:

- Số thread hoặc process con khác nhau.
- Workload tạo ra memory map khác nhau.
- File descriptor và IPC resource khác nhau.
- CRIU/JDK version hoặc engine khác nhau.
- Các tính năng kernel được sử dụng khác nhau.
- Dữ liệu trang được chia thành file khác nhau.

Vì vậy, checkpoint có ít file hơn không tự động là thiếu; checkpoint có nhiều file hơn cũng không tự động là đầy đủ. Cần kiểm tra đúng output của lần dump, checksum và khả năng restore.

## 4. Các phần cần bảo toàn khi đóng gói

### 4.1. Giữ nguyên toàn bộ thư mục ảnh

Khi đóng gói, copy hoặc archive, giữ toàn bộ cây thư mục checkpoint do engine tạo ra:

- Tất cả file ảnh.
- Các thư mục con nếu có.
- Tên file và đường dẫn tương đối.
- File log/metadata được runtime tạo ra.
- File ẩn nếu có.
- Symlink, hard link và thuộc tính file nếu định dạng/engine sử dụng.

Không chọn riêng các file có đuôi `.img`. Có file hỗ trợ restore không mang đuôi đó, và có file `.img` chỉ là một phần trong tập ảnh.

### 4.2. Bảo toàn nội dung và kích thước file

Mỗi file cần được giữ nguyên byte. Không mở rồi ghi lại bằng text editor, không sửa header, không nối hai file cùng tên và không cắt file lớn để tiết kiệm dung lượng.

Những thao tác có thể làm hỏng bộ ảnh:

- Chỉ copy các file nhỏ và bỏ qua file pages lớn.
- Copy khi CRIU vẫn đang ghi checkpoint.
- Ghi đè một phần file từ checkpoint cũ.
- Nối file của hai lần dump khác nhau.
- Đổi tên file theo quy ước tự đặt.
- Chuyển qua công cụ đồng bộ làm thay đổi nội dung hoặc bỏ qua file ẩn.
- Giải nén thiếu file vì giới hạn dung lượng hoặc lỗi truyền tải.

### 4.3. Bảo toàn metadata của filesystem

Ngoài nội dung file, cần xem xét:

- Permission và executable bit.
- Owner/group và numeric UID/GID khi cần.
- Symlink và hard link.
- Timestamp nếu engine hoặc quy trình phục hồi phụ thuộc.
- Extended attributes, ACL và sparse file khi có sử dụng.
- Cấu trúc thư mục và đường dẫn mount.

Một công cụ copy chỉ giữ nội dung mà bỏ quyền truy cập có thể làm restore thất bại khi engine cần đọc file bằng user hoặc quyền cụ thể. Khi đóng gói trên Linux, nên dùng công cụ archive có khả năng bảo toàn metadata phù hợp với môi trường.

## 5. Không trộn nhiều lần checkpoint

Mỗi lần checkpoint phải có thư mục đích riêng. Không tái sử dụng một thư mục đang chứa ảnh của lần dump trước nếu chưa xử lý nó theo đúng quy trình.

Ví dụ:

~~~text
checkpoints/
├── build-2.4.0-run-001/
├── build-2.4.0-run-002/
└── build-2.4.1-run-001/
~~~

Mỗi thư mục chỉ thuộc một lần checkpoint. Không copy file từ `run-001` sang `run-002` để “bù” file thiếu. Dù tên file trùng nhau, nội dung có thể mô tả trạng thái process khác.

Nếu checkpoint thất bại giữa chừng, thư mục có thể còn file dở dang. Đánh dấu hoặc chuyển nó vào khu vực failed/quarantine, ghi lại log và tạo thư mục mới cho lần thử tiếp theo. Không coi sự tồn tại của `inventory.img` hay một số file pages là bằng chứng lần dump đã hoàn tất.

### 5.1. Dùng đường dẫn mới cho mỗi lần tạo

Ví dụ trên Linux:

~~~bash
CHECKPOINT_ROOT=/var/lib/myapp/checkpoints
CHECKPOINT_DIR="$CHECKPOINT_ROOT/build-2.4.0-run-001"

mkdir -p "$CHECKPOINT_ROOT"

java -XX:CRaCCheckpointTo="$CHECKPOINT_DIR" \
     -jar app.jar
~~~

Sau khi ứng dụng đã sẵn sàng và được chuẩn bị checkpoint, tìm PID và yêu cầu dump:

~~~bash
jcmd -l
jcmd <PID> JDK.checkpoint
~~~

Đường dẫn checkpoint cần được chuẩn bị đúng theo hướng dẫn của JDK/runtime đang dùng. Tài liệu CRaC hiện hành mô tả runtime tạo thư mục đích nếu chưa có nhưng không tự tạo mọi thư mục cha; vì vậy, tạo thư mục cha trước là cách rõ ràng và dễ tái lập.

### 5.2. Chờ checkpoint hoàn tất trước khi copy

Không archive hoặc đồng bộ thư mục trong lúc CRIU còn ghi image. Hãy xác nhận thao tác checkpoint đã kết thúc theo log của ứng dụng và engine. Một số phiên bản `jcmd` có thể in thông báo thành công ở phía client ngay cả khi lỗi chi tiết được ghi trong console/log của process; cần đọc log thực tế thay vì chỉ dựa vào một dòng stdout.

Sau khi checkpoint được xác nhận hoàn tất, mới lập inventory, tạo checksum và archive.

## 6. Tạo inventory và checksum cho bộ checkpoint

Manifest checksum là bằng chứng giúp phát hiện file bị thiếu hoặc thay đổi trong quá trình truyền tải. Manifest này nên được lưu **bên cạnh** thư mục ảnh, không tự ý thêm vào thư mục CRIU sau khi dump.

### 6.1. Liệt kê file và dung lượng

Trên Linux:

~~~bash
find "$CHECKPOINT_DIR" -type f -printf '%P\t%s bytes\n' | sort
du -sh "$CHECKPOINT_DIR"
~~~

Lệnh đầu liệt kê đường dẫn tương đối và kích thước từng file. Lệnh thứ hai cho biết tổng dung lượng thư mục.

Có thể lưu inventory:

~~~bash
find "$CHECKPOINT_DIR" -type f -printf '%P\t%s\n' \
    | sort \
    > "$CHECKPOINT_DIR.files.txt"
~~~

File inventory ở ví dụ được đặt cạnh thư mục checkpoint. Hãy lưu rõ file inventory thuộc lần checkpoint nào.

### 6.2. Tạo checksum

~~~bash
CHECKSUM_FILE="$CHECKPOINT_DIR.sha256"
(
    cd "$CHECKPOINT_DIR"
    find . -type f -print0 | sort -z | xargs -0 -r sha256sum
) > "$CHECKSUM_FILE"
~~~

Các đường dẫn trong file checksum là đường dẫn tương đối tính từ thư mục checkpoint. Khi xác minh, chạy từ đúng thư mục đã giải nén:

~~~bash
CHECKSUM_FILE=/opt/artifacts/orders-service/checkpoint.sha256
(
    cd "$RESTORED_CHECKPOINT_DIR"
    sha256sum -c "$CHECKSUM_FILE"
)
~~~

Nếu manifest checksum được đặt ở nơi khác, điều chỉnh đường dẫn tương ứng. Không sửa nội dung manifest để bỏ qua một file báo lỗi; hãy xác định file bị thiếu hoặc sai checksum và truyền lại toàn bộ gói từ bản nguồn hợp lệ.

Checksum chỉ chứng minh các file được liệt kê có nội dung khớp với manifest. Nó không chứng minh image tương thích với kernel, JDK hoặc môi trường restore.

### 6.3. Xác minh inventory sau khi giải nén

Sau khi archive được giải nén, so sánh:

- Danh sách đường dẫn tương đối.
- Số lượng file.
- Kích thước từng file.
- Checksum SHA-256.
- Permission và symlink nếu có.

Không chỉ so sánh tổng dung lượng. Hai thư mục có thể có cùng dung lượng nhưng khác nội dung hoặc thiếu một file và thừa một file khác.

## 7. Archive checkpoint mà không làm mất cấu trúc

Có thể dùng tar trên Linux để đóng gói toàn bộ cây thư mục. Ví dụ, tạo archive từ thư mục cha:

~~~bash
tar --numeric-owner --acls --xattrs --sparse \
    -cpf crac-checkpoint.tar \
    -C "$CHECKPOINT_DIR" .
~~~

Lệnh trên lưu nội dung thư mục checkpoint vào archive, bao gồm cây thư mục và các thuộc tính mà tùy chọn hỗ trợ. Tùy môi trường, việc bảo toàn owner, ACL và extended attributes khi giải nén có thể yêu cầu quyền thích hợp.

Giải nén vào một thư mục mới:

~~~bash
mkdir -p "$RESTORED_CHECKPOINT_DIR"

tar --numeric-owner --acls --xattrs --sparse \
    -xpf crac-checkpoint.tar \
    -C "$RESTORED_CHECKPOINT_DIR"
~~~

Sau khi giải nén, chạy lại kiểm tra inventory và checksum. Chỉ dùng thư mục đã xác minh cho restore.

### 7.1. Nén có thể ảnh hưởng hiệu năng và tài nguyên

Checkpoint có thể rất lớn vì chứa dữ liệu memory pages. Nén archive có thể giảm dung lượng lưu trữ nhưng tiêu tốn CPU và thời gian. Với mục tiêu giảm thời gian deploy/restore, cần đo cả:

- Thời gian tạo checkpoint.
- Thời gian archive và upload.
- Thời gian download và giải nén.
- Thời gian xác minh checksum.
- Thời gian restore.
- Dung lượng sau nén và trước nén.

Không nén riêng từng file image rồi đặt file nén trở lại thư mục checkpoint nếu runtime không hỗ trợ định dạng đó. Nếu muốn nén, hãy nén **archive bên ngoài** rồi giải nén đầy đủ trước khi restore.

### 7.2. Không đổi cấu trúc thư mục sau giải nén

Nếu archive chứa nội dung thư mục gốc, hãy giải nén sao cho `-XX:CRaCRestoreFrom` trỏ đúng tới thư mục có các image files. Tránh trường hợp vô tình tạo thêm một cấp thư mục:

~~~text
Sai đường dẫn restore:
restore-root/
└── crac-checkpoint/
    └── inventory.img

Đường dẫn restore cần trỏ vào:
restore-root/crac-checkpoint/
    ├── inventory.img
    ├── core-*.img
    └── ...
~~~

Đường dẫn chính xác tùy cách tạo archive. Hãy kiểm tra nội dung archive bằng `tar -tf` và kiểm tra thư mục sau khi giải nén trước khi chạy restore.

## 8. Manifest tương thích phải đi cùng checkpoint

Bộ image mô tả trạng thái process, nhưng không tự cung cấp mọi thông tin về môi trường triển khai. Nên tạo một manifest riêng ở cấp deployment bundle để ghi nhận nguồn gốc và điều kiện tương thích.

Ví dụ cấu trúc manifest:

~~~yaml
checkpoint:
  id: orders-service-2.4.0-run-001
  createdAt: "2026-11-13T07:00:00Z"
  engine: criu
  imageDirectory: ./checkpoint
  checksumFile: ./checkpoint.sha256

application:
  name: orders-service
  version: 2.4.0
  gitCommit: 8f31c2a
  artifact: app.jar
  artifactSha256: "<sha256>"

runtime:
  javaVendor: "<vendor>"
  javaVersion: "<full version and build>"
  architecture: x86_64
  os: Linux
  kernel: "<kernel version>"
  criuVersion: "<version>"
  jvmOptions:
    - "-Xms512m"
    - "-Xmx2g"

compatibility:
  runtimeConfigSchema: 3
  requiredMounts:
    - "/run/app-config"
    - "/run/secrets"
  notes: "Restore only in a validated compatible environment"
~~~

Đây là ví dụ schema do pipeline định nghĩa, không phải định dạng manifest chính thức của CRaC hoặc CRIU. Không ghi password, API token, private key hoặc secret value vào manifest.

### 8.1. Thông tin nên ghi nhận

| Nhóm | Thông tin |
|---|---|
| Định danh checkpoint | ID duy nhất, thời điểm tạo, môi trường tạo |
| Ứng dụng | Version, Git commit, artifact checksum |
| JVM | Vendor, version đầy đủ, build, JVM options |
| Hệ điều hành | Distribution, kernel, architecture |
| Engine | CRaC engine, CRIU version và tùy chọn liên quan |
| Filesystem | Mount path, volume, file ngoài cần có |
| Cấu hình | Schema version, revision cấu hình không nhạy cảm |
| Kiểm tra | Inventory, tổng dung lượng, checksum, kết quả restore test |

Manifest giúp người vận hành biết checkpoint nào được tạo từ source và runtime nào. Nó không thay thế việc kiểm tra khả năng tương thích trước khi restore.

### 8.2. Ghi rõ điều kiện CPU và kiến trúc

Restore trên máy khác có thể thất bại nếu CPU không có những feature mà checkpoint đã sử dụng. Tương tự, khác kiến trúc CPU hoặc khác điều kiện kernel có thể khiến image không tương thích.

Vì vậy, không nên ghi đơn giản “Linux x86_64” rồi kết luận mọi máy x86_64 đều restore được. Cần giữ thông tin CPU/JDK và tuân thủ hướng dẫn tương thích của CRaC runtime/vendor.

## 9. Các tài nguyên bên ngoài thư mục image

Một bộ image đầy đủ vẫn có thể phụ thuộc vào tài nguyên bên ngoài. Đây là lý do phải phân biệt “đủ file” với “đủ điều kiện restore”.

### 9.1. File và mount được tham chiếu

Process có thể giữ file descriptor hoặc memory mapping tới file ngoài. Tùy loại file và cách CRIU xử lý, nội dung có thể được lưu trong image, được xử lý bởi plugin hoặc cần có sẵn tại đường dẫn tương ứng.

Trước khi chuyển checkpoint:

- Xác định các mount mà process sử dụng.
- Bảo đảm file được tham chiếu có mặt và đúng nội dung.
- Giữ đường dẫn, permission và quyền truy cập cần thiết.
- Không thay file JDK/native library mà process cần ánh xạ.
- Kiểm tra volume và mount namespace của container.

Không mặc định rằng copy riêng thư mục checkpoint sẽ mang theo toàn bộ filesystem của container.

### 9.2. Socket và network

Socket đang mở thường cần được xử lý bằng CRaC Resource callback trước checkpoint. Sau restore, ứng dụng nên tạo lại kết nối tới database, broker, HTTP service và hệ thống bên ngoài theo lifecycle tương ứng.

Ngay cả khi image có metadata socket, network endpoint hoặc namespace, trạng thái phía server bên ngoài vẫn có thể thay đổi trong lúc process dừng. Do đó, callback cần xác thực hoặc tạo lại resource thay vì tin rằng session cũ vẫn hợp lệ.

### 9.3. Credential và secret

Checkpoint có thể chứa dữ liệu trong heap, kể cả secret đã được ứng dụng đọc trước đó. Nếu checkpoint dùng chung cho nhiều môi trường, tránh nạp credential riêng trước khi dump.

Không coi việc xóa một field khỏi object là bằng chứng secret đã biến mất khỏi toàn bộ memory image. Bảo vệ checkpoint artifact như dữ liệu nhạy cảm, giới hạn quyền truy cập, mã hóa khi lưu/chuyển và dùng secret manager để nạp credential theo môi trường sau restore.

### 9.4. File tạm và dữ liệu trong tmpfs

Nếu process phụ thuộc file trong `/tmp`, tmpfs hoặc một mount tạm, cần xác định CRIU engine đã lưu nội dung hay yêu cầu môi trường restore cung cấp lại. Đường dẫn tồn tại nhưng nội dung khác cũng có thể khiến ứng dụng hoạt động sai.

Với file tạm có thể tái tạo, cách an toàn thường là đóng resource trước checkpoint và tạo lại sau restore thông qua callback. Với file cần giữ nguyên, ghi nhận rõ vị trí và yêu cầu bảo toàn.

## 10. Quy trình đóng gói checkpoint an toàn

Có thể tổ chức pipeline theo các giai đoạn sau:

~~~text
1. PREPARE
   - Build application
   - Chọn JDK/CRaC runtime và CRIU
   - Xác định mount, config và resource dependency

2. RUN AND WARM UP
   - Khởi động application
   - Thực hiện workload đại diện
   - Kiểm tra trạng thái READY

3. QUIESCE
   - Ngừng nhận traffic/công việc mới
   - Drain request, transaction và background work
   - Đóng resource cần tạo lại sau restore

4. CHECKPOINT
   - Gọi JDK.checkpoint
   - Chờ engine hoàn tất dump
   - Lưu log và kết quả

5. VERIFY IMAGE SET
   - Liệt kê toàn bộ file
   - Ghi dung lượng và checksum
   - Xác nhận thư mục không còn thay đổi

6. PACKAGE
   - Archive toàn bộ thư mục
   - Tạo manifest bên ngoài
   - Tính checksum archive

7. TRANSFER
   - Upload/copy archive
   - Xác minh checksum tại đích
   - Giải nén đầy đủ

8. RESTORE TEST
   - Kiểm tra môi trường tương thích
   - Restore từ bản copy đã xác minh
   - Chạy smoke test và health check

9. PUBLISH
   - Chỉ đánh dấu artifact READY sau khi các bước trên hoàn tất
~~~

Mỗi giai đoạn nên có trạng thái riêng. Ví dụ: `PREPARING`, `CHECKPOINTING`, `IMAGE_VERIFIED`, `PACKAGED`, `TRANSFERRED`, `RESTORE_TESTED`, `READY`. Không dùng một cờ `exists=true` để biểu diễn tất cả các bước.

### 10.1. Dùng thư mục tạm và chỉ công bố khi đã xác minh

Một cách triển khai an toàn là ghi checkpoint vào đường dẫn duy nhất của lần chạy, sau đó xác minh và mới đổi tên hoặc publish archive sang vị trí chính thức.

~~~text
artifact-staging/
└── orders-2.4.0-run-001.tmp/
    ├── checkpoint/
    ├── checkpoint.sha256
    └── manifest.yml

artifact-repository/
└── orders-2.4.0-run-001/
    ├── checkpoint.tar
    ├── checkpoint.tar.sha256
    └── manifest.yml
~~~

Không đưa thư mục `.tmp` vào danh sách artifact được phép restore. Chỉ sau khi checkpoint hoàn tất, checksum khớp, archive có thể giải nén và restore test thành công mới chuyển trạng thái sang READY.

Nếu dùng object storage, có thể upload vào key tạm rồi publish manifest hoặc tag phiên bản sau cùng. Đừng để consumer tải một archive đang được upload dở.

### 10.2. Không sửa thư mục ảnh sau khi dump

Sau khi CRIU hoàn tất, xem thư mục ảnh như một artifact bất biến:

- Không thêm file do pipeline tự tạo vào bên trong.
- Không sửa nội dung hoặc quyền file nếu chưa có quy trình rõ ràng.
- Không xóa log/image “có vẻ không cần”.
- Không đổi tên file.
- Không ghép ảnh từ lần dump khác.
- Không giải nén chồng lên một thư mục cũ.

Lưu manifest, checksum và log ở bên ngoài thư mục image để tránh thay đổi tập file do engine tạo.

## 11. Kiểm tra tính đầy đủ trước khi restore

Có thể kiểm tra theo nhiều lớp.

### 11.1. Kiểm tra sự tồn tại và cấu trúc

Xác nhận đường dẫn restore trỏ đúng thư mục image, thư mục không rỗng và có các file do engine tạo. So sánh với inventory của chính lần dump đó.

Không dùng một danh sách tên file cố định làm tiêu chuẩn duy nhất. Một image hợp lệ có thể không có một loại resource nào đó nếu process không sử dụng nó.

### 11.2. Kiểm tra checksum

Chạy `sha256sum -c` với manifest được tạo ngay sau checkpoint. Nếu một file thiếu hoặc khác byte, dừng quá trình và lấy lại archive từ nguồn hợp lệ.

Không tiếp tục restore bằng cách bỏ qua một số dòng checksum lỗi. Các file có liên kết nội bộ với nhau; việc thiếu một thành phần có thể làm hỏng toàn bộ restore.

### 11.3. Kiểm tra khả năng của môi trường

CRIU có lệnh kiểm tra kernel feature và capability:

~~~bash
criu check
~~~

Lệnh này giúp xác nhận một số điều kiện môi trường mà CRIU cần. Nó không phải công cụ xác minh toàn bộ checkpoint image và không chứng minh một checkpoint cụ thể chắc chắn restore được.

Ngoài ra cần xác nhận:

- JDK CRaC tương thích với image.
- CRIU/engine version phù hợp.
- Kernel và CPU feature đáp ứng yêu cầu.
- Quyền/capability checkpoint/restore cần thiết.
- Mount và file bên ngoài có mặt.
- Network namespace, port và filesystem phù hợp.
- Runtime config và secret có thể được nạp sau restore.

### 11.4. Restore test là phép xác nhận quan trọng nhất

Cách kiểm tra thực tế nhất là restore một bản copy của checkpoint trong môi trường thử nghiệm tương thích.

~~~bash
java -XX:CRaCRestoreFrom=/opt/artifacts/orders-2.4.0/checkpoint
~~~

Sau khi restore, kiểm tra:

1. Process có khởi động từ image hay không.
2. Log CRaC và resource callback có hoàn tất không.
3. Application readiness có chuyển READY không.
4. Health endpoint có phản hồi không.
5. Database, message broker và service bên ngoài có kết nối lại không.
6. Các request hoặc background task đại diện có chạy đúng không.
7. Không có lỗi file descriptor, permission hoặc mount.
8. Memory và resource usage nằm trong giới hạn triển khai.

Một checksum đúng chỉ chứng minh dữ liệu không bị thay đổi so với manifest. Restore test mới xác nhận bộ ảnh và môi trường phối hợp được trong tình huống thực tế.

## 12. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Restore báo thiếu image file | Archive thiếu file hoặc đường dẫn giải nén sai | So sánh inventory/checksum và giải nén lại vào thư mục mới |
| Restore đọc được inventory nhưng lỗi memory page | Thiếu hoặc hỏng pagemap/pages | Truyền lại toàn bộ bộ ảnh từ nguồn hợp lệ |
| Permission denied | Mất owner, mode hoặc thiếu capability | Khôi phục metadata và kiểm tra quyền runtime |
| Không tìm thấy file được tham chiếu | Mount hoặc file ngoài không có ở host đích | Khôi phục mount/path và nội dung phù hợp |
| Restore lỗi CPU feature | Host đích không đáp ứng feature cần thiết | Dùng host tương thích hoặc tạo checkpoint với policy CPU phù hợp |
| Restore lỗi network/socket | Resource chưa được đóng/khôi phục đúng hoặc namespace khác | Xử lý bằng CRaC Resource và xác minh network |
| Archive giải nén có thêm một cấp thư mục | Cấu trúc archive/đường dẫn extract không khớp | Trỏ restore vào đúng thư mục chứa image files |
| Checksum archive đúng nhưng restore thất bại | Archive nguyên vẹn nhưng image/environment không tương thích | Kiểm tra JDK, CRIU, kernel, mount và restore log |
| Thư mục checkpoint có file nhưng dump thất bại | Chỉ tạo được một phần image trước lỗi | Đọc log, đánh dấu failed và tạo checkpoint mới |
| Restore test pass nhưng production fail | Khác quyền, mount, secret, network hoặc resource limit | So sánh manifest môi trường và kiểm tra từng dependency |

### 12.1. Không chữa checkpoint bằng cách đoán file thiếu

Nếu restore báo thiếu file, không lấy một file cùng tên từ checkpoint khác để bổ sung. Một file cùng tên không có nghĩa thuộc cùng một process snapshot.

Cách xử lý an toàn:

1. Giữ nguyên bản checkpoint gốc để điều tra.
2. Kiểm tra log dump và transfer.
3. Xác định file bị thiếu ở bước tạo, archive, upload hay extract.
4. Lấy lại nguyên archive từ nguồn hợp lệ nếu transfer bị lỗi.
5. Nếu checkpoint gốc đã thiếu file do dump thất bại, tạo checkpoint mới.
6. Tạo lại manifest/checksum và chạy restore test.

## 13. Bảo vệ và quản lý vòng đời artifact

Checkpoint có thể chứa dữ liệu ứng dụng, cache, thông tin người dùng và secret trong memory. Nó cần được bảo vệ như một artifact nhạy cảm.

Các biện pháp nên áp dụng:

- Giới hạn người và service có quyền đọc checkpoint.
- Mã hóa khi lưu trữ và truyền tải.
- Không gửi checkpoint qua kênh không bảo mật.
- Không commit image vào Git repository thông thường.
- Không để checkpoint trong thư mục public web.
- Ghi nhận ai tạo, tải, giải nén và restore artifact.
- Có retention policy và quy trình xóa an toàn.
- Xác định quyền truy cập đối với backup và replica của archive.
- Không đưa secret value vào manifest hoặc log.

Nếu checkpoint được dùng chung cho nhiều môi trường, cần đặc biệt chú ý dữ liệu đã được nạp vào heap trước lúc dump. Đóng connection hoặc xóa field không chứng minh mọi dữ liệu nhạy cảm đã bị loại khỏi memory image.

### 13.1. Phân biệt checksum với chữ ký

Checksum như SHA-256 giúp phát hiện thay đổi ngoài ý muốn trong quá trình lưu trữ hoặc truyền tải. Tuy nhiên, người có quyền thay archive cũng có thể tạo lại checksum.

Nếu cần xác minh nguồn gốc artifact, ký manifest hoặc checksum bằng khóa được quản lý riêng. Khi restore, xác minh chữ ký bằng public key/trust store được quản lý độc lập với archive. Chữ ký xác nhận nguồn phát hành theo trust policy; nó không chứng minh image tương thích hoặc an toàn về mặt nghiệp vụ.

## 14. Quy tắc bảo toàn tính đầy đủ

Khi vận hành checkpoint CRaC, cần giữ các nguyên tắc sau:

1. **Một lần dump, một thư mục riêng:** không trộn file của các lần checkpoint.
2. **Giữ nguyên cả cây thư mục:** không chỉ copy file `.img` hoặc các file có kích thước nhỏ.
3. **Không sửa image:** không đổi tên, cắt, ghép hoặc chỉnh nội dung file.
4. **Chờ dump hoàn tất:** không archive trong lúc engine còn ghi.
5. **Bảo toàn metadata:** giữ permission, owner, symlink, ACL và xattr khi cần.
6. **Tạo checksum bên ngoài image directory:** xác minh sau mỗi lần truyền hoặc giải nén.
7. **Ghi manifest tương thích:** JDK, CRIU, kernel, CPU, artifact và mount.
8. **Giữ tài nguyên ngoài image:** file, mount, secret provider và network cần thiết phải sẵn sàng.
9. **Restore test trước khi phát hành:** không dùng sự tồn tại của file hoặc checksum làm bằng chứng restore thành công.
10. **Bảo vệ checkpoint:** image có thể chứa dữ liệu nhạy cảm trong memory.

Một checkpoint chỉ được coi là sẵn sàng triển khai khi bộ image được tạo hoàn tất, được bảo toàn nguyên vẹn, có metadata tương thích, các phụ thuộc bên ngoài đã được xác định và restore test trên môi trường tương đương đã thành công.

## 15. Tài liệu tham khảo

- [CRaC — Checkpoint and restore](https://crac.org/use/checkpoint-and-restore/): cách cấu hình đường dẫn checkpoint, yêu cầu checkpoint và restore.
- [CRaC — Implementing the CRaC API](https://crac.org/use/implement-crac/): quản lý resource trước checkpoint và sau restore.
- [CRIU — Images](https://criu.org/Images): các loại image file, metadata và memory pages.
- [CRIU — Checkpoint/Restore](https://criu.org/Checkpoint/Restore): cách CRIU thu thập trạng thái process và resource.
- [Spring Boot — Checkpoint and Restore With the JVM](https://docs.spring.io/spring-boot/reference/packaging/checkpoint-restore.html): tổng quan checkpoint/restore và phạm vi hỗ trợ lifecycle của Spring Boot.

Cấu trúc file cụ thể cần được xác nhận theo JDK, engine và CRIU version đang triển khai. Các tên file trong bài là ví dụ để nhận biết nhóm dữ liệu; không phải danh sách cố định cho mọi checkpoint.

