# Lưu trữ, truyền tải và dọn dẹp ảnh không còn sử dụng

Ảnh checkpoint CRaC là trạng thái của một tiến trình Java tại thời điểm checkpoint. Trong môi trường production, ảnh này cần được lưu ở nơi bền vững, truyền tới đúng môi trường restore và quản lý vòng đời như một artifact triển khai. Việc copy thiếu file, làm mất quyền truy cập, thay đổi metadata filesystem hoặc restore trên môi trường không tương thích đều có thể khiến ảnh không sử dụng được.

Ảnh checkpoint cũng có thể chứa dữ liệu nhạy cảm trong heap như access token, password, thông tin người dùng, dữ liệu cache và trạng thái session. Vì vậy, quy trình lưu trữ cần bảo vệ tính toàn vẹn, tính tương thích, tính bảo mật và khả năng truy vết. Quy trình dọn dẹp phải xác định ảnh nào còn được deployment tham chiếu và ảnh nào đang được restore trước khi xóa.

## 1. Ảnh checkpoint là một artifact có ràng buộc môi trường

Khi khởi chạy JVM với `-XX:CRaCCheckpointTo=<path>` và yêu cầu checkpoint, runtime tạo dữ liệu checkpoint tại đường dẫn được cấu hình. Cấu trúc bên trong do JDK/CRaC và lớp checkpoint nền tảng quản lý. Không nên coi từng file nội bộ là file ứng dụng để tự chỉnh sửa, đổi tên hoặc xóa riêng lẻ.

Ảnh checkpoint khác với các artifact thường gặp:

| Artifact | Nội dung | Mục tiêu |
| --- | --- | --- |
| JAR ứng dụng | Bytecode, resource và metadata đóng gói | Chạy ứng dụng trên JVM tương thích. |
| Container image | Root filesystem, runtime và cấu hình image | Tạo môi trường container. |
| CRaC checkpoint image | Trạng thái tiến trình được runtime/platform lưu | Tiếp tục tiến trình từ trạng thái đã checkpoint. |
| Database backup | Dữ liệu database và metadata theo cơ chế backup | Phục hồi dữ liệu bền vững. |
| WAL/transaction log archive | Log thay đổi database | Recovery/PITR theo khả năng database. |

CRaC checkpoint không thay thế JAR, container image, database backup hoặc transaction log. Một quy trình triển khai có thể cần lưu tất cả các artifact này và liên kết chúng bằng metadata chung.

Ảnh checkpoint thường gắn với môi trường tạo ra nó. Khả năng restore phụ thuộc vào bản JDK/CRaC, CRIU hoặc cơ chế nền tảng, kernel, kiến trúc CPU, namespace, filesystem, mount, thư viện native và các tài nguyên tiến trình. Không được mặc định có thể copy ảnh sang bất kỳ máy nào rồi restore thành công.

## 2. Vòng đời artifact checkpoint

Một vòng đời lưu trữ có thể chia thành các giai đoạn:

```text
Khởi chạy ứng dụng và chuẩn bị Resource
                 |
                 v
          Tạo checkpoint
                 |
                 v
       Xác nhận checkpoint hoàn tất
                 |
                 v
      Đóng gói / tạo metadata
                 |
                 v
     Tính checksum và xác minh
                 |
                 v
    Upload vào vùng staging tạm
                 |
                 v
   Kiểm tra artifact đã truyền đủ
                 |
                 v
   Publish artifact bất biến/hoàn tất
                 |
                 v
       Restore và kiểm tra thực tế
                 |
                 v
  Retain / mark obsolete / cleanup
```

Mỗi bước có kết quả riêng. Thư mục được tạo không đồng nghĩa checkpoint hoàn tất; file archive được upload không đồng nghĩa artifact đã được publish; checksum đúng không chứng minh ảnh tương thích với host restore; restore thành công cũng chưa chứng minh ứng dụng đã đạt readiness.

Nên lưu trạng thái theo từng attempt, ví dụ `CREATING`, `CREATED`, `PACKAGING`, `UPLOADING`, `PUBLISHED`, `RESTORE_VERIFIED`, `OBSOLETE` và `DELETED`. Đây là nhãn quản lý của pipeline, không phải trạng thái bắt buộc trong CRaC API.

## 3. Chỉ đóng gói sau khi checkpoint hoàn tất

Không copy hoặc nén thư mục checkpoint trong khi JVM/CRIU còn đang ghi ảnh. Nếu copy giữa chừng, artifact có thể thiếu image page, metadata hoặc file cần thiết. Kết quả có thể có đủ tên file nhưng nội dung chưa hoàn chỉnh.

Trước khi đóng gói:

1. Xác nhận lệnh checkpoint đã kết thúc theo semantics của runtime đang dùng.
2. Kiểm tra log JVM và CRIU/nền tảng để xác định checkpoint được xác nhận thành công.
3. Xác nhận tiến trình gốc đã chuyển sang trạng thái mong đợi của quy trình checkpoint; việc tiến trình kết thúc có thể là hành vi bình thường.
4. Bảo đảm không còn writer nào thay đổi thư mục ảnh.
5. Ghi lại thời điểm tạo và checkpoint attempt id.

Không dùng sự tồn tại của thư mục hoặc một file đơn lẻ làm tín hiệu duy nhất. Nếu checkpoint thất bại, thư mục đích có thể còn dữ liệu dở dang. Đánh dấu attempt thất bại và xử lý thư mục theo quy trình cleanup riêng; không publish dữ liệu đó.

Một cách tổ chức dễ quản lý là dùng một thư mục riêng cho mỗi attempt:

```text
/var/lib/myapp/crac/
├── staging/
│   ├── attempt-20261113T090000Z/
│   └── attempt-20261113T093000Z/
└── published/
    ├── release-2026.11.13-001/
    └── release-2026.11.13-002/
```

Không tái sử dụng cùng một thư mục đích cho nhiều checkpoint attempt đồng thời. Một attempt lỗi không được làm lẫn file với ảnh đã publish trước đó.

## 4. Giữ nguyên cấu trúc và metadata filesystem

Ảnh checkpoint có thể chứa nhiều file và thư mục con do runtime tạo. Tùy nền tảng và công cụ dump, các thuộc tính filesystem có thể quan trọng khi restore:

- Relative path và cấu trúc thư mục.
- File content và kích thước chính xác.
- Quyền đọc/ghi/thực thi.
- Owner và group id.
- Symbolic link, hard link và file type.
- Extended attributes (xattrs), ACL và metadata bảo mật nếu được sử dụng.
- Sparse file layout và các đặc tính filesystem liên quan.

Khi đóng gói, hãy dùng công cụ và tùy chọn có thể bảo toàn các thuộc tính mà môi trường CRaC/CRIU yêu cầu. Không dùng quy trình chỉ copy text hoặc chỉ copy các file có phần mở rộng quen thuộc. Không bỏ qua file ẩn hay file metadata.

Ví dụ với GNU tar trên Linux, có thể tạo archive bảo toàn nhiều loại metadata:

```bash
tar --xattrs --acls --numeric-owner --sparse \
    -cpf checkpoint.tar \
    -C /var/lib/myapp/crac/staging \
    attempt-20261113T090000Z
```

Khi giải nén trên môi trường đích:

```bash
mkdir -p /var/lib/myapp/crac/restore-staging

tar --same-owner --same-permissions --xattrs --acls \
    -xpf checkpoint.tar \
    -C /var/lib/myapp/crac/restore-staging
```

Các tùy chọn trên là ví dụ cho GNU tar; khả năng bảo toàn owner, ACL, xattrs, sparse file và security label phụ thuộc hệ điều hành, filesystem, phiên bản công cụ và quyền người chạy. Có thể cần quyền quản trị để phục hồi owner hoặc metadata bảo mật. Kiểm tra tài liệu của nền tảng đang triển khai và thử restore từ archive đã giải nén.

Nếu dùng `rsync`, chọn tùy chọn bảo toàn thuộc tính cần thiết theo môi trường, ví dụ archive mode cùng hard link, ACL, xattrs, sparse và numeric id khi phù hợp. Không thêm tùy chọn xóa đích trong lần copy đầu nếu chưa có quy trình xác minh nguồn/đích; một lệnh đồng bộ có `--delete` cấu hình sai có thể xóa artifact đang được giữ.

Không chỉnh sửa nội dung file bên trong ảnh để giảm kích thước hoặc loại bỏ một vài thành phần. Nếu runtime cung cấp định dạng hay công cụ đóng gói chính thức, ưu tiên cách được tài liệu của bản runtime hỗ trợ.

## 5. Nén và định dạng archive

Checkpoint có thể lớn vì chứa trạng thái heap và memory page của tiến trình. Nén giúp giảm dung lượng truyền và lưu trữ, nhưng cũng làm tăng CPU và thời gian đóng gói/giải nén.

Khi chọn định dạng:

- Bảo toàn toàn bộ cây thư mục và metadata cần thiết.
- Hỗ trợ file lớn, sparse file và kích thước archive dự kiến.
- Có thể kiểm tra tính toàn vẹn sau khi truyền.
- Có thể giải nén trên môi trường restore đã xác định.
- Ghi nhận phiên bản công cụ và tùy chọn nén trong metadata artifact.

Không tối ưu compression ratio bằng cách thay đổi nội dung ảnh. Chọn mức nén dựa trên thời gian RTO, CPU, dung lượng mạng và chi phí storage. Với môi trường cần restore nhanh, có thể giữ bản giải nén trên storage gần host để tránh giải nén trong critical startup path.

Archive nên chứa thư mục checkpoint ở đúng cấp tương đối mà quy trình restore mong đợi. Khi giải nén, tránh tạo thêm một lớp thư mục ngoài ý muốn khiến `-XX:CRaCRestoreFrom` trỏ sai vị trí.

## 6. Tạo checksum và xác minh tính toàn vẹn

Sau khi đóng gói hoàn chỉnh, tính checksum cho archive hoặc manifest file. SHA-256 là lựa chọn phổ biến để phát hiện file bị hỏng hoặc thay đổi ngoài ý muốn:

```bash
sha256sum checkpoint.tar > checkpoint.tar.sha256

# Ở máy nhận, sau khi tải xong:
sha256sum --check checkpoint.tar.sha256
```

Nếu lưu checkpoint dưới dạng thư mục chưa đóng gói, cần tạo manifest checksum cho các file theo thứ tự ổn định, có đường dẫn tương đối và kích thước. Không chỉ hash tên file hoặc tổng dung lượng.

Checksum trả lời câu hỏi “dữ liệu nhận được có giống dữ liệu đã hash không?”. Nó không xác nhận:

- Checkpoint đã được tạo thành công.
- File có đầy đủ metadata filesystem.
- Artifact tương thích với host restore.
- Artifact không chứa mã độc hoặc không bị tạo bởi nguồn không tin cậy.
- Ứng dụng sẽ đạt readiness sau restore.

Nếu cần xác thực nguồn phát hành, có thể ký manifest hoặc checksum bằng cơ chế ký artifact của tổ chức. Lưu chữ ký và key id riêng; không đặt private signing key trong checkpoint image hoặc cùng quyền truy cập với archive.

## 7. Metadata cần lưu cùng checkpoint

Không nên suy luận môi trường tạo ảnh chỉ từ tên thư mục. Lưu một manifest riêng bên cạnh artifact để người vận hành biết ảnh nào có thể dùng ở đâu. Manifest là metadata quản lý của pipeline, không phải file nội bộ CRIU và không nên được chèn vào bên trong cấu trúc ảnh nếu runtime không yêu cầu.

Các trường hữu ích:

| Nhóm | Metadata nên lưu |
| --- | --- |
| Định danh | Artifact id, checkpoint attempt id, tên service/module, release id. |
| Ứng dụng | Build version, Git commit, JAR checksum, cấu hình profile không chứa secret. |
| Java runtime | JDK vendor, version/build, JVM flags liên quan, CRaC support/version. |
| Nền tảng | OS/distribution, kernel version, architecture, CPU feature baseline. |
| Checkpoint stack | CRIU version/capabilities hoặc cơ chế nền tảng, container runtime version nếu áp dụng. |
| Filesystem | Loại filesystem, mount layout, đường dẫn cần thiết, UID/GID và metadata requirements. |
| Dependency | Phiên bản native library, agent, driver và dependency runtime quan trọng. |
| Thời gian | Created at, checkpoint completed at, warm-up profile nếu có, thời điểm hết hạn artifact. |
| Integrity | Archive format, compression, size, SHA-256, signature/key id. |
| Storage | URI/path, storage class, encryption key id, retention class. |
| Verification | Host/environment đã restore thử, kết quả restore, readiness result và thời điểm kiểm thử. |

Ví dụ manifest JSON minh họa:

```json
{
  "artifactId": "myapp-release-2026.11.13-001",
  "checkpointAttemptId": "attempt-20261113T090000Z",
  "application": {
    "version": "2026.11.13",
    "gitCommit": "<commit-id>",
    "jarSha256": "<sha256>"
  },
  "runtime": {
    "jdkVendor": "<vendor>",
    "jdkVersion": "<version-and-build>",
    "cracVersion": "<version>",
    "criuVersion": "<version>"
  },
  "platform": {
    "os": "<distribution>",
    "kernel": "<kernel-version>",
    "architecture": "<architecture>",
    "cpuFeatures": "<required-feature-baseline>"
  },
  "archive": {
    "format": "tar",
    "compression": "<compression>",
    "sizeBytes": 0,
    "sha256": "<sha256>"
  },
  "createdAt": "2026-11-13T09:00:00Z",
  "restoreVerified": false
}
```

Các giá trị trong dấu ngoặc nhọn là placeholder. Không đưa password, token, private key, nội dung environment secret hoặc dữ liệu người dùng vào manifest. Chỉ lưu metadata đủ để xác định compatibility và truy vết artifact.

## 8. Kiểm tra khả năng tương thích trước khi truyền

Ảnh checkpoint không phải container image portable. Trước khi chuyển sang host khác, so sánh tối thiểu:

- JDK vendor, phiên bản, build và CRaC implementation.
- Phiên bản CRIU hoặc cơ chế checkpoint nền tảng.
- Kiến trúc CPU và tập lệnh mà mã native/JIT yêu cầu.
- Kernel và các tính năng cần thiết.
- Container runtime, namespace, cgroup và security capability.
- Mount point, filesystem, đường dẫn tuyệt đối và quyền truy cập.
- Shared library, native agent, driver và file mapping.
- Tài nguyên bên ngoài như socket, database, DNS, secret và service endpoint.

Ngay cả khi hai máy cùng kiến trúc `x86_64`, chúng vẫn có thể khác CPU feature, kernel hoặc namespace. Không dùng tên OS chung làm bằng chứng tương thích.

Một số resource cần được tái tạo qua callback CRaC sau restore, ví dụ connection pool, socket hoặc client kết nối tới service bên ngoài. Việc artifact có thể restore không có nghĩa mọi tài nguyên bên ngoài đã sẵn sàng; cần kiểm tra callback và readiness sau restore.

Nếu cần chuyển checkpoint giữa host, hãy xác định trước một compatibility profile được hỗ trợ và kiểm thử trên đúng loại host đích. Nếu môi trường đích khác đáng kể, phương án an toàn có thể là khởi chạy ứng dụng mới và tạo checkpoint mới tại môi trường đích thay vì cố restore ảnh cũ.

## 9. Lưu trữ trên volume, filesystem và object storage

### Local persistent volume

Lưu ảnh trên persistent volume có thể giúp restore nhanh trên cùng host hoặc trong cùng môi trường storage. Cần bảo đảm volume tồn tại qua vòng đời container/process và có đủ dung lượng. Không để checkpoint chỉ nằm trong writable layer tạm của container nếu container có thể bị xóa.

### Shared filesystem

Shared filesystem thuận tiện cho nhiều host truy cập, nhưng phải xác nhận hỗ trợ các đặc tính mà checkpoint cần: quyền, owner, locking, xattrs, ACL, hard link, sparse file, file size và semantics rename. Không phải network filesystem nào cũng phù hợp với mọi cơ chế CRIU.

### Object storage

Object storage thường không có semantics filesystem đầy đủ. Thường cần đóng gói checkpoint thành archive rồi upload như một object bất biến. Không giả định object store hỗ trợ rename nguyên tử; nhiều hệ thống thực hiện copy/delete hoặc dùng object key mới.

Một cách publish an toàn cho object storage:

1. Upload archive với key staging riêng, ví dụ `staging/<attempt-id>/checkpoint.tar`.
2. Upload checksum và manifest vào staging.
3. Đọc lại metadata/size và xác minh checksum bằng cách tải xuống hoặc dùng checksum do storage hỗ trợ có semantics phù hợp.
4. Copy/promote sang key phiên bản bất biến trong `published/` hoặc đánh dấu artifact bằng một manifest/marker hoàn tất được ghi sau cùng.
5. Chỉ cập nhật deployment pointer sau khi toàn bộ artifact đã được xác minh.

Không ghi đè một key đang được host restore đọc. Dùng key/version mới cho mỗi checkpoint attempt và cập nhật một pointer riêng theo cơ chế có concurrency control.

## 10. Truyền tải an toàn giữa các môi trường

Khi truyền ảnh qua mạng:

- Dùng transport được mã hóa và xác thực, chẳng hạn kênh TLS hoặc SSH được tổ chức phê duyệt.
- Xác thực danh tính nguồn và đích; giới hạn quyền upload/download theo service identity.
- Kiểm tra dung lượng trống trước khi tải.
- Tải vào staging path riêng, không ghi trực tiếp lên thư mục đang được restore.
- Xác minh checksum/chữ ký trước khi giải nén hoặc restore.
- Giải nén vào thư mục mới và giữ nguyên cấu trúc/metadata cần thiết.
- Chỉ publish đường dẫn cuối sau khi kiểm tra hoàn tất.
- Ghi log artifact id, source, destination, bytes transferred, checksum và kết quả.

Không gửi ảnh qua kênh chat, email cá nhân hoặc dịch vụ chia sẻ file công khai. Checkpoint có thể chứa credential và dữ liệu nhạy cảm trong bộ nhớ. Không đặt URL có token truy cập vào log hoặc manifest công khai.

Với file lớn, có thể dùng multipart/resumable upload nếu storage hỗ trợ, nhưng chỉ coi upload hoàn tất sau khi tất cả part đã được finalize và checksum cuối được xác minh. ETag của multipart object không phải lúc nào cũng là MD5/SHA-256 của toàn bộ nội dung; dùng checksum semantics được nhà cung cấp công bố.

## 11. Publish artifact theo cách tránh đọc file dở dang

Trên filesystem hỗ trợ rename nguyên tử trong cùng filesystem, có thể chuẩn bị artifact ở thư mục staging rồi rename sang tên publish sau khi hoàn tất:

```bash
STAGING=/var/lib/myapp/crac/staging/attempt-20261113T090000Z
PUBLISHED=/var/lib/myapp/crac/published/release-2026.11.13-001

# Sau khi archive/checksum/manifest đã hoàn tất và được xác minh:
mv "$STAGING" "$PUBLISHED"
```

Rename chỉ có thể được xem là nguyên tử trong điều kiện filesystem và thao tác phù hợp, thường là cùng filesystem. Nếu hai đường dẫn nằm trên filesystem khác, `mv` có thể trở thành copy rồi delete. Trong trường hợp đó, không dùng rename như bằng chứng publish nguyên tử; hãy copy sang staging ở đích, xác minh xong rồi cập nhật một manifest/pointer hoàn tất.

Đối với object storage, dùng immutable key/version và ghi marker hoàn tất hoặc manifest tham chiếu cuối cùng sau khi upload đủ. Consumer chỉ đọc artifact có marker trạng thái `PUBLISHED` và checksum đã xác minh.

Không cập nhật deployment pointer trước khi artifact cuối đã sẵn sàng. Nếu pointer trỏ tới archive chưa hoàn tất, một restore mới có thể đọc file dở dang.

## 12. Quy trình restore từ artifact đã lưu

Trước khi chạy `-XX:CRaCRestoreFrom`, thực hiện các bước:

1. Chọn artifact id cụ thể từ manifest/deployment record; không dùng wildcard hoặc “latest” không có kiểm soát.
2. Kiểm tra trạng thái artifact là `PUBLISHED` và chưa bị đánh dấu obsolete/deleted.
3. Xác minh checksum và chữ ký nếu có.
4. Kiểm tra compatibility metadata với host đích.
5. Giải nén vào đúng path, bảo toàn metadata cần thiết.
6. Kiểm tra quyền user chạy JVM và các mount/path phụ thuộc.
7. Bảo đảm không có tiến trình khác đang ghi hoặc dọn thư mục này.
8. Restore theo lệnh và tài liệu của JDK/CRaC đang dùng.
9. Xác nhận callback `afterRestore`, kết nối tài nguyên và readiness.
10. Ghi lại host/runtime đã restore thành công để phục vụ truy vết.

Ví dụ lệnh restore:

```bash
java -XX:CRaCRestoreFrom=/var/lib/myapp/crac/restore-staging/attempt-20261113T090000Z
```

Đường dẫn phải trỏ tới thư mục checkpoint mà runtime mong đợi sau giải nén, không phải file archive hoặc thư mục cha chứa nhiều checkpoint. Cấu trúc cụ thể phụ thuộc cách đóng gói và JDK/CRaC distribution.

Nếu restore thất bại, giữ artifact và log để điều tra theo chính sách retention. Không xóa ảnh ngay sau một lần restore lỗi; lỗi có thể do host đích không tương thích chứ không phải artifact hỏng.

## 13. Chính sách retention

Retention xác định ảnh nào được giữ và trong bao lâu. Không nên chỉ dựa vào tuổi file vì một ảnh cũ có thể đang được deployment rollback sử dụng, còn một ảnh mới có thể chưa từng restore thành công.

Một policy có thể kết hợp:

- Giữ checkpoint đang được deployment hiện tại tham chiếu.
- Giữ một số checkpoint gần nhất đã restore thành công.
- Giữ checkpoint của release trước trong cửa sổ rollback đã định.
- Giữ ảnh chưa được xác minh cho tới khi có quyết định vận hành rõ ràng.
- Xóa ảnh staging thất bại sau thời gian điều tra/grace period.
- Áp dụng giới hạn tuổi tối đa và quota dung lượng.
- Giữ ảnh theo legal hold hoặc incident investigation nếu có yêu cầu.

Ví dụ policy minh họa:

| Loại artifact | Chính sách ví dụ |
| --- | --- |
| Deployment hiện tại | Giữ cho tới khi deployment thay thế và không còn restore đang tham chiếu. |
| Checkpoint đã xác minh của release gần nhất | Giữ 3 phiên bản gần nhất hoặc 14 ngày, tùy điều kiện nào dài hơn. |
| Checkpoint chưa kiểm chứng | Giữ tối đa 48 giờ trong khi chờ restore test hoặc quyết định loại bỏ. |
| Attempt thất bại/staging dở dang | Đánh dấu lỗi, giữ log và dọn sau grace period 24 giờ nếu không có incident hold. |
| Artifact bị đánh dấu obsolete | Xóa sau khi hết rollback window và không có consumer/restore lease đang hoạt động. |

Các con số chỉ là ví dụ, không phải mặc định cho mọi hệ thống. Hãy chọn theo RTO, khả năng rollback, chi phí storage, dung lượng ảnh, yêu cầu bảo mật và thời gian điều tra sự cố.

## 14. Dọn dẹp ảnh không còn sử dụng an toàn

Cleanup là thao tác phá hủy dữ liệu. Cần có tiêu chí xác định artifact không còn được tham chiếu, không có restore đang chạy và đã qua retention/grace period.

Một quy trình hai pha thường an toàn hơn:

**Pha 1 — Mark obsolete**

- Đánh dấu artifact là `OBSOLETE` trong metadata registry.
- Xác nhận deployment pointer không còn trỏ tới artifact.
- Xác nhận không có restore job hoặc host lease đang sử dụng artifact.
- Bắt đầu grace period để rollback hoặc xử lý incident.

**Pha 2 — Delete**

- Đọc lại trạng thái và reference ngay trước khi xóa.
- Xác nhận artifact id và đường dẫn tuyệt đối khớp registry.
- Xóa cả archive, manifest, checksum và dữ liệu staging liên quan theo một thao tác quản lý có kiểm soát.
- Ghi audit event gồm ai/automation nào xóa, thời điểm, artifact id và kết quả.
- Cập nhật registry thành `DELETED` sau khi xác nhận storage đã xóa theo semantics của nó.

Không xóa chỉ vì tên thư mục chứa ngày cũ. Không xóa thư mục đang được deployment rollback, restore job hoặc một host khác sử dụng. Không xóa file con bên trong checkpoint để “giải phóng một phần dung lượng”; ảnh sẽ không còn đáng tin cậy.

### Dry-run trước khi xóa

Với filesystem Linux, có thể liệt kê các thư mục staging cũ để người vận hành xem trước:

```bash
find /var/lib/myapp/crac/staging \
  -mindepth 1 -maxdepth 1 -type d \
  -name 'attempt-*' -mtime +2 -print
```

Đây chỉ là danh sách theo tuổi file; nó chưa kiểm tra deployment reference hoặc restore lease. Chỉ sau khi registry xác nhận các điều kiện retention, automation mới được xóa đúng artifact id đã chọn. Tránh ghép đường dẫn từ input không tin cậy hoặc dùng wildcard rộng với `rm -rf`.

Với object storage, xóa version cụ thể hoặc object key cụ thể. Kiểm tra versioning, soft delete, replication và lifecycle rule vì thao tác delete có thể tạo delete marker thay vì xóa vật lý ngay. Nếu có legal hold hoặc object lock, cleanup phải tuân theo policy đó.

## 15. Tránh race giữa cleanup và restore

Một lỗi vận hành nguy hiểm xảy ra khi cleanup nhìn thấy artifact “cũ” rồi xóa trong lúc restore vừa bắt đầu tải hoặc đọc artifact đó.

Có thể tránh bằng cách quản lý reference/lease:

1. Restore job yêu cầu sử dụng artifact id.
2. Registry cấp lease có thời hạn hoặc tăng reference count cho artifact.
3. Cleanup chỉ chọn artifact không có lease/reference và đã hết retention.
4. Restore hoàn tất hoặc thất bại thì giải phóng lease.
5. Lease hết hạn cần được reconcile với trạng thái job trước khi cleanup tiếp tục.

Nếu nhiều worker/host cùng thao tác, cần locking hoặc conditional update nguyên tử ở registry. Không dựa vào kiểm tra file rồi xóa sau một khoảng thời gian vì trạng thái có thể thay đổi giữa hai bước.

Với object storage, versioning giúp giữ các version cụ thể nhưng không thay thế lease. Deployment record nên trỏ tới immutable object version, không chỉ tới key có thể bị ghi đè.

## 16. Dọn dẹp staging và checkpoint thất bại

Checkpoint thất bại có thể để lại thư mục dở dang. Không publish những thư mục này và không dùng lại chúng làm đích cho lần checkpoint mới.

Quy trình xử lý:

1. Ghi nhận checkpoint attempt id và lỗi runtime/CRIU.
2. Đánh dấu attempt là `FAILED` hoặc `INCOMPLETE`.
3. Giữ log và dữ liệu cần thiết trong grace period để điều tra.
4. Xác nhận không còn JVM/CRIU process ghi vào thư mục.
5. Xác nhận không có restore job đang tham chiếu.
6. Xóa toàn bộ staging directory theo artifact id.
7. Ghi kết quả cleanup và giải phóng quota.

Nếu không xác định được writer còn hoạt động hay không, không xóa. Trước tiên phải xác nhận trạng thái tiến trình và runtime. Cleanup không được chạy đồng thời với thao tác checkpoint đang diễn ra.

## 17. Dung lượng, quota và chi phí lưu trữ

Checkpoint có thể lớn và số lượng tăng nhanh khi mỗi release/host tạo ảnh riêng. Cần dự trù:

- Kích thước heap và native memory tại thời điểm checkpoint.
- Số lượng checkpoint được giữ đồng thời.
- Dung lượng archive tạm trong lúc nén.
- Dung lượng staging tại host đích khi download và giải nén.
- Bản sao dự phòng, object versioning và replication storage.
- Khoảng trống cần thiết cho checkpoint mới khi ảnh cũ chưa được cleanup.

Một ước lượng sơ bộ:

```text
Storage budget
  = số checkpoint giữ lại × kích thước trung bình mỗi ảnh
  + staging/temporary copy
  + archive và bản giải nén đồng thời
  + overhead của versioning/replication
  + safety margin
```

Không dùng kích thước heap `-Xmx` làm ước lượng chính xác cho checkpoint size. Ảnh có thể chứa native memory, page, metadata và các vùng trạng thái khác; compression ratio cũng thay đổi theo dữ liệu.

Theo dõi dung lượng trống, tốc độ upload/download, thời gian nén/giải nén và số artifact theo trạng thái. Khi quota gần đầy, ưu tiên dọn staging thất bại đã hết grace period và artifact obsolete không còn reference; không xóa ảnh đang phục vụ rollback chỉ để giải phóng dung lượng tức thời.

## 18. Bảo mật ảnh checkpoint

Ảnh checkpoint có thể chứa nội dung bộ nhớ của process. Hãy giả định nó có độ nhạy tương đương hoặc cao hơn log ứng dụng và có thể chứa:

- Password, token, API key và credential database.
- Session cookie, access token và private data.
- Dữ liệu cá nhân đang được xử lý.
- Request/response body hoặc dữ liệu cache.
- Private key hoặc TLS material nếu ứng dụng giữ trong memory.

Biện pháp bảo vệ:

- Mã hóa dữ liệu khi lưu và khi truyền.
- Quản lý encryption key tách khỏi checkpoint storage; giới hạn quyền decrypt.
- Dùng service identity riêng cho upload/download và nguyên tắc least privilege.
- Bật audit log cho read, copy, restore và delete.
- Hạn chế người có quyền truy cập trực tiếp vào host/storage chứa ảnh.
- Không đưa ảnh vào source control, artifact public hoặc ticket/chat không được phê duyệt.
- Áp dụng retention ngắn nhất đáp ứng rollback/operational requirements.
- Xử lý bản sao staging, archive tạm và cache download theo cùng policy bảo mật.

Xóa object không nhất thiết có nghĩa dữ liệu đã bị ghi đè vật lý ngay, nhất là với SSD, snapshot hoặc object storage có versioning/replication. Nếu yêu cầu xóa an toàn, dùng cơ chế crypto-erasure/key revocation hoặc quy trình do nhà cung cấp storage hỗ trợ và xác nhận được.

## 19. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Restore báo thiếu file/image | Copy khi checkpoint chưa hoàn tất hoặc archive bỏ qua file | Kiểm tra checkpoint completion, manifest file list và đóng gói lại từ ảnh hợp lệ. |
| Restore không truy cập được file | Mất owner, permission, ACL hoặc xattr khi copy/extract | Dùng công cụ bảo toàn metadata và khôi phục bằng quyền phù hợp. |
| Archive checksum đúng nhưng restore thất bại | Artifact nguyên vẹn nhưng môi trường không tương thích hoặc ảnh vốn không hợp lệ | Kiểm tra JDK/CRaC, CRIU, kernel, CPU, mount và log restore. |
| Restore path không tìm thấy ảnh | Giải nén thừa một cấp thư mục hoặc pointer trỏ nhầm archive | Kiểm tra cấu trúc sau extract và trỏ `CRaCRestoreFrom` đúng thư mục checkpoint. |
| Object storage có archive nhưng pipeline báo chưa publish | Upload file xong nhưng manifest/marker hoàn tất chưa được ghi | Chỉ coi artifact published sau bước finalize và checksum verification. |
| Checkpoint đang được restore bị xóa | Cleanup chỉ kiểm tra tuổi file, không kiểm tra lease/reference | Dùng registry, lease và conditional delete. |
| Storage tăng không kiểm soát | Giữ mọi attempt, staging lỗi và nhiều object version | Áp dụng retention, quota, lifecycle policy và audit cleanup. |
| Không thể xóa object cũ | Object lock, legal hold, retention hoặc versioning | Kiểm tra storage policy; không bypass hold trái quy trình. |
| Dữ liệu nhạy cảm bị lộ qua checkpoint | Ảnh được lưu/chia sẻ như artifact thông thường | Mã hóa, giới hạn quyền, audit và quản lý key riêng. |

## 20. Quy trình vận hành mẫu

Một pipeline đóng gói và publish có thể triển khai theo trình tự:

```text
1. Start JVM with CRaCCheckpointTo=staging/<attempt-id>
2. Wait for application warm-up and resource preparation
3. Request JDK.checkpoint
4. Confirm checkpoint operation completed successfully
5. Confirm no process is writing the checkpoint directory
6. Create archive while preserving required filesystem metadata
7. Generate SHA-256 and external manifest
8. Upload archive + manifest to staging storage
9. Verify remote size/checksum/signature
10. Publish immutable artifact id / completion marker
11. Record artifact metadata and compatibility profile
12. Restore-test on a compatible target environment
13. Mark restore result and update deployment reference
14. Mark old artifacts obsolete after rollback window
15. Cleanup only unreferenced artifacts after grace period
```

Mỗi bước nên idempotent theo `attempt-id`. Nếu pipeline retry upload, không tạo hai artifact khác nhau cho cùng một attempt trừ khi có chủ ý. Nếu checksum khác giữa các lần retry, đánh dấu attempt bất thường và điều tra thay vì ghi đè object đã publish.

## 21. Checklist triển khai

- [ ] Mỗi checkpoint attempt dùng một thư mục riêng.
- [ ] Chỉ copy/nén sau khi runtime xác nhận checkpoint hoàn tất và không còn writer.
- [ ] Không chỉnh sửa hoặc xóa file riêng lẻ bên trong ảnh checkpoint.
- [ ] Archive giữ nguyên directory layout và metadata filesystem cần thiết.
- [ ] Đã kiểm tra công cụ archive/extract hỗ trợ ACL, xattrs, owner, hard link và sparse file khi cần.
- [ ] Manifest ghi build, JDK/CRaC, CRIU, kernel, CPU, filesystem và compatibility metadata.
- [ ] Manifest không chứa secret hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Có checksum và xác minh sau truyền; có chữ ký nếu yêu cầu provenance.
- [ ] Upload vào staging trước, chỉ publish sau khi xác minh đầy đủ.
- [ ] Dùng immutable artifact id/version; không ghi đè ảnh đang được dùng.
- [ ] Storage có encryption, access control và audit.
- [ ] Restore chỉ dùng artifact đã publish và tương thích với host đích.
- [ ] Đã restore-test trên môi trường mục tiêu.
- [ ] Retention tính đến deployment hiện tại, rollback window, restore lease và incident hold.
- [ ] Cleanup có dry-run, mark-obsolete, grace period và kiểm tra reference ngay trước delete.
- [ ] Không cleanup đồng thời với checkpoint, upload hoặc restore đang hoạt động.
- [ ] Theo dõi quota, dung lượng staging, transfer duration và số artifact theo trạng thái.
- [ ] Có quy trình xử lý checkpoint dở dang và upload thất bại.

## 22. Kết luận

Ảnh CRaC cần được quản lý như một artifact triển khai gắn với môi trường tạo ra nó. Chỉ đóng gói sau khi checkpoint hoàn tất, bảo toàn toàn bộ cấu trúc và metadata cần thiết, tạo checksum/manifest, truyền qua kênh an toàn và publish bằng định danh bất biến. Trước restore, xác minh tính toàn vẹn, compatibility, quyền và đường dẫn; sau restore, kiểm tra callback và readiness.

Cleanup phải dựa trên trạng thái tham chiếu và retention, không chỉ dựa vào tuổi file. Dùng quy trình mark-obsolete rồi delete sau grace period, kiểm tra restore lease để tránh xóa ảnh đang được dùng, và bảo vệ checkpoint như dữ liệu nhạy cảm vì heap có thể chứa credential hoặc dữ liệu người dùng. Cách quản lý artifact có metadata, integrity check và lifecycle rõ ràng giúp checkpoint có thể truy vết, truyền tải và dọn dẹp an toàn.
