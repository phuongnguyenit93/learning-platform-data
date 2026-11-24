# Thư mục tạm, quyền tệp và lưu trữ ngoài binary

## 1. Vì sao filesystem là một phần của vận hành Native Image?

Spring Boot Native Image tạo ra executable native, nhưng ứng dụng vẫn cần tương tác với filesystem trong lúc chạy. Framework và thư viện có thể tạo file tạm, đọc certificate, ghi log, xuất báo cáo, lưu upload, tạo cache hoặc tải thư viện JNI vào thư mục tạm. Binary khởi động thành công chưa chứng minh các thao tác này hoạt động trong container production.

Một lỗi thường gặp là ứng dụng chạy tốt trên máy developer với user có quyền rộng, nhưng thất bại khi container chạy non-root hoặc root filesystem được mount read-only. Lỗi cũng có thể xuất hiện muộn, chỉ khi người dùng upload file, tạo PDF, chạy migration hoặc thư viện cần giải nén native resource.

Trong module **SPRING_BOOT_NATIVE_IMAGE**, cần thiết kế rõ ba nhóm dữ liệu:

- **Binary và tài nguyên bất biến**: executable, classpath resources và thư viện đi cùng image; thường chỉ cần quyền đọc/thực thi.
- **Dữ liệu tạm**: file trung gian, upload đang xử lý, socket file hoặc extraction; có thể xóa sau khi process kết thúc.
- **Dữ liệu cần giữ bền vững**: file người dùng, báo cáo, state hoặc dữ liệu nghiệp vụ; phải lưu trên volume/object storage/database phù hợp.

Không dùng thư mục trong container writable layer làm nơi lưu dữ liệu cần tồn tại qua lần thay container. Container có thể bị thay thế trong deploy, reschedule hoặc autoscaling.

## 2. Các khái niệm filesystem cần phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Working directory | Thư mục hiện hành của process | /app |
| Temporary directory | Nơi tạo dữ liệu tạm | /tmp |
| Classpath resource | Tài nguyên đóng gói cùng ứng dụng | templates/invoice.html |
| Runtime file | File được mount hoặc tạo khi chạy | /var/run/secrets/db-password |
| Persistent volume | Lưu dữ liệu qua vòng đời container | /var/lib/app-data |
| Executable permission | Quyền cho phép chạy binary/script | chmod +x |
| Read permission | Quyền đọc file hoặc traverse directory | r--, x trên directory |
| Write permission | Quyền tạo/xóa/thay đổi file | w trên directory |

Quyền directory có ý nghĩa khác quyền file. Để đọc một file, process cần quyền đọc file và quyền execute/traverse trên từng directory cha. Để tạo file trong directory, process cần quyền write và execute trên directory đó.

## 3. Xác định những thao tác filesystem của ứng dụng

Trước khi chọn quyền, lập danh sách thao tác thực tế:

- Đọc classpath template, schema, migration và message bundle.
- Đọc file cấu hình hoặc secret được mount.
- Tạo file tạm khi xử lý request.
- Ghi log vào stdout/stderr hay file.
- Xuất PDF/CSV hoặc archive.
- Upload/download file.
- Cache dữ liệu có thể tái tạo.
- Thư viện JNI giải nén binary vào temp directory.
- Tạo PID file, lock file hoặc Unix domain socket nếu ứng dụng dùng.

Mỗi đường dẫn cần có chủ sở hữu, vòng đời, dung lượng dự kiến, quyền cần thiết và chính sách cleanup. Không cấp quyền ghi toàn bộ filesystem chỉ vì một thư viện cần ghi một thư mục.

## 4. Thư mục tạm trong Java và Spring Boot

Java cung cấp system property `java.io.tmpdir` để xác định thư mục tạm mặc định. Có thể kiểm tra lúc runtime:

```java
System.out.println(System.getProperty("java.io.tmpdir"));
```

Tạo file tạm bằng API chuẩn:

```java
Path tempFile = Files.createTempFile("invoice-", ".tmp");
try {
    // Write or process temporary content.
} finally {
    Files.deleteIfExists(tempFile);
}
```

Nếu file cần được chia sẻ giữa nhiều bước hoặc process, xác định rõ quyền sở hữu và cleanup. Không để file tạm chứa dữ liệu nhạy cảm tồn tại vô thời hạn.

Spring có thể dùng Resource, MultipartFile, upload handling và thư viện bên thứ ba. Hãy kiểm tra thư viện tạo file ở đâu; không giả định mọi thư viện đều dùng `java.io.tmpdir`. Một số thư viện có property riêng hoặc dùng working directory.

## 5. Cấu hình temp directory khi chạy native executable

Có thể đặt temp directory qua system property khi khởi chạy executable nếu runtime hỗ trợ option đó:

```bash
./api-app -Djava.io.tmpdir=/tmp/app-tmp
```

Với Native Image, xác minh cách truyền system properties theo GraalVM Native Image version và cách application launcher xử lý arguments. Có thể đặt `TMPDIR` hoặc cấu hình property riêng cho thư viện nếu thư viện sử dụng biến môi trường đó.

Trong container, tạo directory và cấp quyền cho user runtime:

```dockerfile
RUN mkdir -p /tmp/app-tmp \
    && chown -R 10001:10001 /tmp/app-tmp
ENV TMPDIR=/tmp/app-tmp
USER 10001
```

Không cần tạo thư mục riêng nếu image/runtime đã cung cấp /tmp với permission phù hợp. Hãy xác minh bằng cách chạy process với đúng user.

## 6. Quyền Unix: owner, group và mode

Unix permission gồm owner, group và others. Các bit thường gặp:

| Bit | File | Directory |
|---|---|---|
| r | Đọc nội dung | Liệt kê tên entry |
| w | Sửa nội dung | Tạo/xóa/đổi tên entry |
| x | Thực thi file | Traverse/search directory |

Ví dụ:

```bash
chmod 0555 /app/api-app
chmod 0750 /var/lib/app-data
chown 10001:10001 /var/lib/app-data
```

Binary có thể được đọc và thực thi bởi user runtime mà không cần writable. Data directory nên thuộc user/group thích hợp và chỉ cấp quyền cần thiết.

Mode 0777 thường quá rộng. Ưu tiên owner/group rõ ràng, group permissions nếu cần chia sẻ và umask phù hợp để file mới không bị tạo với quyền công khai.

## 7. Chạy container bằng non-root user

Container nên chạy bằng user không có quyền root nếu ứng dụng không cần đặc quyền hệ thống. Ví dụ Dockerfile:

```dockerfile
FROM debian:bookworm-slim
WORKDIR /app
COPY --chown=10001:10001 api-app /app/api-app
RUN mkdir -p /tmp/app-tmp /var/lib/app-data \
    && chown -R 10001:10001 /tmp/app-tmp /var/lib/app-data \
    && chmod 0555 /app/api-app
ENV TMPDIR=/tmp/app-tmp
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/app/api-app"]
```

Đây là ví dụ. Nếu data directory được mount từ volume runtime, chown trong image build không thay đổi ownership của volume được mount đè lên. Cần cấu hình quyền ở storage/platform layer hoặc dùng cơ chế group ownership phù hợp.

Kiểm tra process thực sự chạy bằng UID/GID dự kiến. Không chỉ nhìn USER trong Dockerfile vì orchestrator có thể override user/security context.

## 8. Read-only root filesystem

Read-only root filesystem giảm khả năng process sửa executable, cấu hình hoặc các file khác trong image. Nhưng ứng dụng vẫn có thể cần ghi vào một số mount riêng như temp, upload staging hoặc cache.

Thiết kế:

- /app: chứa executable và immutable files, read-only.
- /tmp: emptyDir hoặc writable tmpfs với quota phù hợp.
- /var/lib/app-data: persistent volume nếu cần state.
- /var/run/secrets: secret/config mount read-only.
- stdout/stderr: logging ra container runtime.

Không bật read-only root filesystem mà chưa xác định mọi đường ghi. Kiểm thử các luồng tạo file, logging, PDF, upload, cache và JNI extraction.

## 9. Cấu hình read-only filesystem trong Docker

Docker có thể chạy container với root filesystem read-only và cấp tmpfs riêng:

```bash
docker run --read-only \
  --tmpfs /tmp/app-tmp:rw,noexec,nosuid,size=64m \
  -p 8080:8080 api-app:local
```

Các option tmpfs phụ thuộc Docker host/kernel. Nếu ứng dụng cần chạy native library được extract vào temp, noexec có thể ngăn thực thi file đó; không bỏ noexec một cách mặc định. Xác minh yêu cầu cụ thể của thư viện, rồi giới hạn mount/permission đúng phạm vi.

Nếu cần ghi dữ liệu bền vững, mount volume riêng thay vì làm writable toàn bộ root filesystem.

## 10. Kubernetes: emptyDir cho dữ liệu tạm

Kubernetes emptyDir cung cấp thư mục tạm gắn với Pod lifecycle. Dữ liệu tồn tại khi container trong Pod restart nhưng bị xóa khi Pod bị loại bỏ.

Ví dụ:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: native-api
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: api
      image: registry.example.com/native-api:1.0.0
      securityContext:
        readOnlyRootFilesystem: true
        allowPrivilegeEscalation: false
      env:
        - name: TMPDIR
          value: /tmp/app-tmp
      volumeMounts:
        - name: temp
          mountPath: /tmp/app-tmp
  volumes:
    - name: temp
      emptyDir:
        sizeLimit: 128Mi
```

Đây là manifest minh họa. fsGroup behavior phụ thuộc volume driver và Kubernetes configuration. Với dữ liệu tạm cần memory-backed tmpfs, có thể dùng emptyDir.medium: Memory, nhưng cần đặt size limit và tính vào memory usage của Pod.

## 11. Kubernetes: persistent volume cho dữ liệu cần giữ

Nếu ứng dụng phải lưu file qua vòng đời Pod, dùng PersistentVolumeClaim hoặc object storage. Ví dụ volume mount:

```yaml
volumeMounts:
  - name: app-data
    mountPath: /var/lib/app-data
volumes:
  - name: app-data
    persistentVolumeClaim:
      claimName: native-api-data
```

PVC manifest và access mode phụ thuộc storage class. Không giả định volume có thể được mount đồng thời read-write bởi nhiều replica. Với nhiều instance, cân nhắc object storage hoặc storage hỗ trợ access pattern tương ứng.

Nếu file là dữ liệu nghiệp vụ quan trọng, thiết kế backup, retention, encryption, access control và recovery. Persistent volume không tự động thay thế backup.

## 12. Classpath resource không phải thư mục ghi dữ liệu

Classpath resource thường nằm trong executable/JAR hoặc native image. Chúng phù hợp để đọc template mặc định, schema và file cấu hình bất biến.

Không ghi đè classpath resource khi runtime. Thay vào đó:

- Đọc template mặc định từ classpath.
- Ghi output vào data directory hoặc object storage.
- Đặt file cấu hình override ở external config path.
- Mount secret riêng ở path chỉ đọc.
- Giữ file upload của người dùng ở storage bền vững.

Một resource trong JAR có thể không tương ứng với một file filesystem có thể sửa. Dùng stream để đọc resource; không dựa vào Resource.getFile() cho resource đóng gói.

## 13. Cấu hình đường dẫn dữ liệu bên ngoài binary

Đặt các path runtime thành configuration rõ ràng:

```yaml
app:
  storage:
    temp-dir: ${APP_TEMP_DIR:/tmp/app-tmp}
    data-dir: ${APP_DATA_DIR:/var/lib/app-data}
```

Bind vào configuration properties:

```java
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(Path tempDir, Path dataDir) {}
```

Khi khởi động, kiểm tra directory tồn tại hoặc tạo nếu policy cho phép, kiểm tra readable/writable và fail fast nếu không đáp ứng. Không tự động tạo directory tùy ý ở mọi vị trí; path cần nằm trong vùng đã được cấp quyền.

Đường dẫn nên được truyền từ môi trường triển khai. Binary có thể giống nhau giữa staging và production trong khi storage mount/path khác nhau.

## 14. Upload file và kiểm soát dung lượng tạm

Upload thường cần staging file trước khi ghi vào storage cuối cùng. Cần kiểm soát:

- Maximum request/file size ở gateway và application.
- Dung lượng temp volume.
- Tên file do server tạo, không tin tên path từ client.
- Cleanup khi request fail/cancel.
- Giới hạn số upload đồng thời.
- Kiểm tra content type và nội dung thực tế.
- Antivirus/content scanning nếu yêu cầu sản phẩm.
- Chính sách retention cho file chưa hoàn tất.

Nếu temp volume đầy, upload có thể fail dù process còn memory. Theo dõi disk usage, inode usage và số file tạm. Có job cleanup an toàn cho file staging hết hạn; không xóa file đang được process khác sử dụng.

## 15. Thư viện JNI và temp directory

Một số Java library đóng gói native library trong JAR rồi giải nén vào thư mục tạm trước khi gọi JNI. Trong container:

- Temp path phải tồn tại và writable cho runtime UID.
- Nếu thư viện cần execute extracted binary, mount không được chặn execution.
- Architecture và libc của thư viện phải khớp binary/container.
- Root filesystem read-only vẫn cần writable temp mount.
- Cleanup phải không xóa thư viện khi process còn sử dụng.

Không cấp quyền execute cho toàn bộ /tmp nếu chỉ một thư mục cụ thể cần. Tìm property chính thức của thư viện để đặt extraction path; không giả định mọi thư viện dùng java.io.tmpdir.

## 16. Logging: stdout/stderr hay file?

Trong container, ưu tiên log ra stdout/stderr để runtime platform thu thập và chuyển tiếp. Nếu ứng dụng ghi file:

- Chọn thư mục log có writable mount rõ ràng.
- Cấu hình rotation và retention.
- Tránh ghi log vào thư mục chứa executable.
- Theo dõi disk usage.
- Không ghi secret, credential hoặc dữ liệu nhạy cảm.
- Đảm bảo log path writable với non-root UID.

Không mount persistent volume chỉ để lưu log nếu nền tảng đã có log aggregation. File log trong container có thể mất khi Pod/container bị thay thế.

## 17. Umask, ownership và volume permission

Umask giới hạn quyền mặc định của file mới. Ví dụ umask 0027 thường tạo file không cho others đọc/ghi, tùy mode được ứng dụng yêu cầu.

Kiểm tra quyền trong container:

```bash
id
umask
pwd
ls -ld /app /tmp /tmp/app-tmp /var/lib/app-data
touch /tmp/app-tmp/permission-check
```

Lệnh touch là phép kiểm tra đơn giản; xóa file kiểm tra sau đó. Chạy dưới đúng user runtime, không kiểm tra bằng root rồi suy ra user non-root cũng ghi được.

Với NFS hoặc CSI volume, ownership mapping và root-squash có thể ảnh hưởng. Xử lý tại storage/platform layer; tránh chạy init container đặc quyền chỉ để chmod/chown nếu có thể cấu hình volume permissions an toàn hơn.

## 18. Dung lượng, quota và cleanup

Thư mục tạm cần giới hạn dung lượng. Nếu dùng tmpfs, dữ liệu tiêu thụ có thể tính vào memory của container/Pod. Nếu dùng disk-backed volume, cần theo dõi ephemeral storage request/limit và quota.

Theo dõi:

- Bytes used và free.
- Inode/file count.
- File tạm theo tuổi.
- Upload staging chưa hoàn tất.
- Disk pressure/eviction events.
- Cleanup failure.
- Temp write latency và I/O errors.

Cleanup nên dựa trên naming convention/metadata và tuổi file có kiểm soát. Không xóa toàn bộ file trong temp directory đang được nhiều process hoặc thư viện chia sẻ mà không biết lifecycle.

## 19. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| AccessDeniedException | UID/GID không có quyền trên path | Kiểm tra id, owner, mode và directory traversal |
| Read-only file system | Ứng dụng ghi vào root filesystem read-only | Xác định path ghi và mount writable riêng |
| No space left on device | Temp/ephemeral volume đầy hoặc hết inode | Kiểm tra quota, usage và cleanup |
| Temp file không được tạo | java.io.tmpdir hoặc TMPDIR sai/không writable | In path runtime và thử tạo file |
| JNI library load fail | Extraction path không writable hoặc noexec | Kiểm tra thư viện, temp mount và ABI |
| Upload mất sau redeploy | Ghi vào container writable layer/emptyDir | Chuyển sang PVC/object storage |
| Config/secret không đọc được | Mount path hoặc permission sai | Kiểm tra mount, UID/GID và read permission |
| Binary không chạy | Thiếu executable bit hoặc sai architecture | Kiểm tra mode và binary target |
| Log không xuất hiện | File appender ghi vào path không tồn tại | Dùng stdout/stderr hoặc mount log path |
| Chỉ lỗi khi chạy non-root | Image build tạo file thuộc root | Sửa ownership/group trong image hoặc volume |

## 20. Checklist trước khi phát hành

- Đã liệt kê mọi đường dẫn ứng dụng/thư viện đọc và ghi.
- Binary và classpath resources được xem là immutable.
- Temp directory có path, quota, permission và cleanup rõ ràng.
- java.io.tmpdir/TMPDIR phù hợp với runtime image.
- Process chạy bằng non-root UID/GID.
- Read-only root filesystem đã được kiểm thử.
- Writable mounts chỉ cấp cho temp/data path cần thiết.
- Persistent data dùng PVC/object storage/database phù hợp.
- Secret/config mount read-only và quyền đọc tối thiểu.
- JNI extraction path đáp ứng writable/execute requirements.
- Upload có size limit, staging và cleanup.
- Logging dùng stdout/stderr hoặc volume được quản lý.
- Disk/inode usage và cleanup failures có monitoring.
- Smoke/integration tests chạy dưới đúng user và final container image.

## 21. Câu hỏi tự kiểm tra

1. Vì sao native executable vẫn cần thư mục tạm?
2. Khác nhau giữa classpath resource, temporary file và persistent data là gì?
3. java.io.tmpdir ảnh hưởng thế nào tới thư viện Java?
4. Vì sao quyền write trên directory khác quyền write trên file?
5. Read-only root filesystem cần những writable mount nào?
6. Kubernetes emptyDir khác PVC ở vòng đời dữ liệu ra sao?
7. Vì sao container non-root có thể không ghi được volume dù Dockerfile đã chown?
8. JNI library extraction có thể bị ảnh hưởng bởi noexec như thế nào?
9. Vì sao upload/file nghiệp vụ không nên chỉ nằm trong container writable layer?
10. Cần kiểm thử filesystem dưới đúng UID/GID và image cuối ra sao?

**Ghi nhớ:** giữ binary và classpath resources bất biến; cấp temp directory có quota/quyền phù hợp; đặt dữ liệu cần giữ trên persistent storage; chạy non-root và kiểm thử read-only filesystem trên chính container cuối cùng.
