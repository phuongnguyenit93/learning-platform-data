# Chạy bằng người dùng không có quyền root và quyền thư mục tạm

## 1. Vì sao container Native Image cần chạy non-root?

Container thường không cần quyền quản trị hệ điều hành để nhận HTTP request, đọc cấu hình, kết nối database hoặc xử lý message. Nếu tiến trình ứng dụng chạy với UID 0, một lỗ hổng trong ứng dụng hoặc thư viện có thể cho phép kẻ tấn công thực hiện thao tác với quyền root bên trong container. Việc chạy bằng user riêng có quyền tối thiểu giúp giảm tác động khi tiến trình bị khai thác.

Native Image không loại bỏ yêu cầu này. Binary do GraalVM tạo ra vẫn chạy dưới user/group mà container runtime cấp. Nó vẫn cần đọc executable, thư viện, certificate và cấu hình; đồng thời có thể cần ghi file tạm, file upload, cache hoặc dữ liệu ứng dụng. Nếu chuyển sang non-root nhưng không chuẩn bị quyền cho các thư mục cần ghi, ứng dụng có thể khởi động thất bại hoặc lỗi ở request đầu tiên tạo file tạm.

Bài học này thuộc chương **Container** của module **SPRING_BOOT_NATIVE_IMAGE**. Module hướng dẫn biên dịch Spring Boot thành GraalVM Native Image bằng Spring AOT, thực hành build Maven/Gradle, cấu hình reflection/resource, kiểm thử tương thích, đóng gói container và vận hành bản native. Bài này tập trung vào user không có quyền root và quyền ghi của thư mục tạm.

Sau bài học, người học có thể:

- Chạy native executable với UID/GID không phải 0.
- Thiết lập ownership và permission cho thư mục ứng dụng.
- Hiểu quyền chuẩn của `/tmp` và tạo thư mục tạm riêng.
- Cấu hình `java.io.tmpdir` cho native executable ở runtime.
- Chạy container với root filesystem chỉ đọc và mount writable temp volume.
- Thiết lập `securityContext` cho Kubernetes.
- Chẩn đoán lỗi `Permission denied` trong Docker, Buildpacks và Kubernetes.

## 2. UID, GID và quyền truy cập trên Linux

Linux kiểm soát quyền truy cập file dựa trên user ID (UID), group ID (GID), các nhóm bổ sung và permission bits. Trong container, UID/GID của tiến trình quyết định nó có thể đọc, ghi hoặc thực thi file nào.

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| UID | Định danh user của process | `10001` |
| GID | Group chính của process | `10001` |
| Owner | User sở hữu file/thư mục | `10001:10001` |
| Mode | Quyền đọc/ghi/thực thi | `0750`, `0640` |
| Sticky bit | Hạn chế xóa/đổi tên file của user khác trong thư mục dùng chung | `1777` trên `/tmp` |

Các quyền thường gặp:

- `r` (read): đọc file; với directory, cho phép liệt kê tên entry.
- `w` (write): ghi file; với directory, cho phép tạo/xóa/đổi tên entry nếu các điều kiện khác cho phép.
- `x` (execute): chạy file; với directory, cho phép traverse/truy cập entry khi biết tên.
- `0750`: owner có quyền đầy đủ, group đọc và traverse/execute, user khác không có quyền.
- `0640`: owner đọc/ghi, group đọc, user khác không có quyền.
- `1777`: mọi user có thể tạo file trong directory, sticky bit hạn chế user xóa file không thuộc sở hữu của họ.

User root (UID 0) có nhiều quyền đặc biệt trong Linux. Ứng dụng thường không cần các quyền đó. Hãy cấp quyền theo từng thư mục và chức năng, không cấp quyền quản trị cho toàn bộ process chỉ để sửa một lỗi ghi file.

Kiểm tra user và permission trong môi trường Linux:

```bash
id
umask
stat -c '%A %a %U:%G %n' /app /tmp
test -x /app/service && echo "executable"
test -w /tmp && echo "tmp writable"
```

Nếu image không có shell hoặc `stat`, có thể kiểm tra `Config.User` của image, dùng công cụ debug phù hợp với base image hoặc thêm một smoke check trong ứng dụng. Không cài shell, package manager hay công cụ quản trị vào final image chỉ để chẩn đoán production.

## 3. Chuẩn bị thư mục ứng dụng và thư mục ghi

Một layout rõ ràng giúp kiểm soát quyền:

```text
/
├── app/
│   └── service          # native executable, chỉ cần đọc/thực thi
├── etc/                 # cấu hình, thường chỉ đọc
└── tmp/
    └── app/             # dữ liệu tạm, có thể ghi
```

Nguyên tắc:

- Đặt executable và file cấu hình trong thư mục chỉ đọc đối với runtime user.
- Chỉ tạo thư mục writable cho nhu cầu thực tế, ví dụ `/tmp/app`, thư mục upload hoặc thư mục spool.
- Tạo directory và đặt owner/group/mode trong lúc build image, trước lệnh `USER`.
- Dùng `COPY --chown` để đặt ownership cho file được copy vào final stage.
- Không giả định `WORKDIR` tự động có quyền ghi cho user chạy ứng dụng.
- Ưu tiên log ra stdout/stderr để container runtime thu thập; nếu ghi log ra file, tạo log directory và cấp quyền riêng.

Docker `COPY` mặc định tạo file với owner root. `USER` chỉ thay đổi user mặc định cho các lệnh tiếp theo và tiến trình lúc chạy; nó không tự đổi owner của file đã copy. Đây là nguyên nhân phổ biến khiến executable đọc được nhưng không thể tạo file tạm hoặc ghi log.

## 4. Dockerfile multi-stage chạy Native Image bằng UID/GID riêng

Ví dụ sau minh họa final image dựa trên Debian slim. Thay image builder bằng GraalVM Native Image builder đã pin version/digest phù hợp với dự án:

```dockerfile
# syntax=docker/dockerfile:1
FROM <graalvm-native-image-builder> AS build
WORKDIR /workspace

COPY . .
RUN ./mvnw -Pnative native:compile

FROM debian:bookworm-slim AS runtime

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 \
       --home-dir /nonexistent --shell /usr/sbin/nologin app \
    && install -d -o 10001 -g 10001 -m 0750 /app \
    && install -d -o 10001 -g 10001 -m 0700 /tmp/app \
    && chmod 1777 /tmp

WORKDIR /app

COPY --from=build --chown=10001:10001 \
    /workspace/target/service /app/service

ENV TMPDIR=/tmp/app

USER 10001:10001

ENTRYPOINT ["/app/service", "-Djava.io.tmpdir=/tmp/app"]
```

Thay `service` bằng tên executable thực tế. Nếu build bằng Gradle, thay lệnh build và đường dẫn output tương ứng, ví dụ `./gradlew nativeCompile` và `build/native/nativeCompile/<application>`.

Một số điểm quan trọng trong ví dụ:

1. Builder và runtime là hai stage riêng. Compiler, Maven/Gradle cache và toolchain không đi vào final image.
2. User `app` được tạo với UID/GID cố định `10001`; có thể chọn ID khác theo chính sách tổ chức.
3. `/app` thuộc user ứng dụng nhưng mode `0750`; executable được copy với ownership đúng.
4. `/tmp` có mode `1777`, đúng quy ước thư mục tạm dùng chung trên Linux.
5. `/tmp/app` chỉ user ứng dụng có quyền truy cập, dùng làm temp directory riêng.
6. `USER` được đặt sau các bước tạo directory và copy file, nên process cuối chạy non-root.
7. `TMPDIR` phục vụ các native library/tool đọc biến môi trường này; `-Djava.io.tmpdir` đặt Java system property cho native executable.

Nếu runtime image không có `groupadd`, `useradd` hoặc `install`, dùng cơ chế tạo user và directory mà base image hỗ trợ, hoặc dùng numeric UID/GID và `COPY --chown`. Với image tối giản/distroless, có thể không có `/etc/passwd` hoặc shell; cần xác minh ứng dụng và thư viện không phụ thuộc vào username được phân giải từ passwd database.

Không dùng tag builder trôi nổi trong pipeline production. Pin version và tốt nhất là image digest để có thể tái tạo build.

## 5. Quyền chuẩn của /tmp và thư mục tạm riêng

Theo quy ước Linux, `/tmp` là thư mục tạm dùng chung và thường có mode `1777` (`drwxrwxrwt`). Sticky bit `t` cho phép nhiều user tạo file nhưng hạn chế việc xóa hoặc đổi tên file thuộc user khác.

Không đổi `/tmp` thành `0755`: user non-root sẽ không thể tạo file. Cũng không cần `chown -R app:app /tmp`; việc đó làm thay đổi quyền sở hữu của các file tạm khác và phá vỡ mô hình thư mục dùng chung. Giữ `/tmp` ở mode `1777`, sau đó tạo subdirectory riêng do ứng dụng sở hữu.

Ví dụ:

```bash
install -d -o 10001 -g 10001 -m 0700 /tmp/app
stat -c '%A %a %U:%G %n' /tmp /tmp/app
```

Kết quả mong đợi về mode:

```text
drwxrwxrwt 1777 root:root /tmp
drwx------ 0700 app:app /tmp/app
```

`0700` phù hợp khi chỉ một UID của ứng dụng cần đọc/ghi file tạm. Nếu nhiều process trong cùng group phải chia sẻ thư mục, cân nhắc `0770` cùng GID phù hợp và umask tương ứng. Chỉ mở rộng quyền sau khi đã xác định process nào cần truy cập.

### 5.1. Chọn Java temporary directory

Java thường đọc system property `java.io.tmpdir` để xác định thư mục mặc định cho các API tạo file tạm. Native Image cho phép truyền `-D` vào executable ở **runtime**:

```bash
./service -Djava.io.tmpdir=/tmp/app
```

Điểm cần phân biệt:

- `native-image -Djava.io.tmpdir=/tmp/app ...` đặt property cho quá trình build/hosted environment; không mặc nhiên cấu hình giá trị runtime của executable.
- `./service -Djava.io.tmpdir=/tmp/app` truyền system property khi chạy native executable.
- `TMPDIR=/tmp/app` là biến môi trường thường được native code và một số thư viện hệ điều hành sử dụng; nó không nên được xem là bằng chứng rằng `java.io.tmpdir` đã có đúng giá trị.
- Nếu dùng container, cấu hình property trong `ENTRYPOINT` hoặc command runtime và kiểm tra giá trị thực tế bằng `System.getProperty("java.io.tmpdir")`.

Native executable nhận các runtime `-D` option theo cú pháp của GraalVM. Không dựa vào `JAVA_TOOL_OPTIONS` như một cách cấu hình chung cho native binary; đây là cơ chế dành cho các JVM launch phù hợp, còn native executable cần nhận option runtime trực tiếp hoặc qua cấu hình ứng dụng.

## 6. Chạy với read-only root filesystem

Một biện pháp hardening thường dùng là mount root filesystem ở chế độ chỉ đọc. Khi đó, ứng dụng chỉ có thể ghi vào những volume/tmpfs được cấp riêng.

Với Docker:

```bash
docker run --rm \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m,mode=1777 \
  --cpus=2 \
  --memory=512m \
  -p 8080:8080 \
  my-service:native
```

Trong ví dụ, `/tmp` là tmpfs riêng của container. Process non-root có thể tạo `/tmp/app` và sở hữu directory đó. Nếu application cần một đường dẫn tạm khác, mount tmpfs đúng vào đường dẫn đó và kiểm tra UID/GID/mode của mount.

Nếu ứng dụng cần ghi dữ liệu lâu dài, dùng volume riêng và cấp quyền phù hợp. Không dùng `/tmp` làm nơi lưu dữ liệu phải tồn tại sau khi container bị xóa hoặc thay thế.

Nếu bật `--read-only` mà chỉ mount `/tmp`, các đường dẫn ghi khác như `/var/log/app`, `/app/uploads` hoặc thư mục cache vẫn sẽ lỗi. Tốt nhất cấu hình log ra console, tắt hoặc chuyển cache file sang thư mục được cấp writable, và dùng persistent volume cho dữ liệu cần lưu lâu dài.

### 6.1. Giới hạn của tmpfs

tmpfs lưu nội dung trong bộ nhớ của host/kernel và có thể dùng swap tùy cấu hình hệ thống. Giới hạn `size` không thay thế container memory limit. Dữ liệu ghi vào tmpfs có thể góp vào memory usage của container/cgroup, vì vậy chọn size hợp lý và theo dõi memory pressure.

Không dùng `noexec` nếu ứng dụng hoặc thư viện thực sự cần tạo và thực thi file trong temp directory. Native executable thông thường không cần chạy binary phụ từ `/tmp`; nếu có dependency đặc biệt, kiểm tra yêu cầu trước khi bỏ `noexec`.

## 7. Chạy non-root với Cloud Native Buildpacks

Nếu dùng Spring Boot Maven/Gradle plugin để tạo image bằng Cloud Native Buildpacks, builder và run image do buildpack lựa chọn. Một số stack phổ biến của Paketo chạy ứng dụng bằng dedicated non-root user. Tuy nhiên, user ID, group và base image phụ thuộc stack/run image version; không nên giả định mọi buildpack hoặc custom run image có cùng UID.

Sau khi build image, kiểm tra cấu hình user thực tế:

```bash
docker image inspect --format '{{.Config.User}}' my-service:native
```

Nếu output rỗng, Docker image config không khai báo user và container mặc định có thể chạy bằng root. Nếu output là numeric UID hoặc username, xác minh UID/GID thực tế bằng cách chạy image trong môi trường có công cụ phù hợp. Với image không có shell, không thể dùng lệnh shell để chẩn đoán; hãy dựa vào image metadata hoặc một diagnostic image tương đương.

Build image bằng Maven hoặc Gradle:

```bash
./mvnw -Pnative spring-boot:build-image
```

Hoặc:

```bash
./gradlew bootBuildImage
```

Buildpack thường đã chuẩn bị user non-root và thư mục làm việc của ứng dụng. Khi thay run image, thêm custom buildpack hoặc mount volume, phải kiểm tra lại quyền. Một volume mount có thể che nội dung và ownership của thư mục đã được chuẩn bị trong image.

Nếu cần đổi UID/GID, dùng cơ chế cấu hình của builder/run image đang sử dụng và xác minh tài liệu của phiên bản đó. Tránh sửa trực tiếp layer của buildpack hoặc mặc định rằng user có tên `cnb` tồn tại trong mọi stack.

## 8. Cấu hình Kubernetes với non-root và writable /tmp

Kubernetes cho phép khai báo user/group và các hạn chế bảo mật ở Pod hoặc container. Ví dụ dưới đây chạy native executable bằng UID/GID `10001`, root filesystem chỉ đọc và mount một `emptyDir` vào `/tmp`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: native-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: native-service
  template:
    metadata:
      labels:
        app: native-service
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: service
          image: registry.example.com/native-service:1.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: TMPDIR
              value: /tmp/app
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 128Mi
```

Trong cấu hình này:

- `runAsNonRoot: true` yêu cầu container không chạy với UID 0.
- `runAsUser` và `runAsGroup` xác định UID/GID của process.
- `fsGroup` bổ sung group để process truy cập volume hỗ trợ ownership theo group.
- `readOnlyRootFilesystem: true` làm root filesystem chỉ đọc.
- `emptyDir` cung cấp vùng ghi tạm cho Pod; dữ liệu trong đó tồn tại theo vòng đời Pod, không phải persistent storage.
- `sizeLimit` giới hạn dung lượng volume tạm theo cấu hình Kubernetes.

Ví dụ Dockerfile ở trên đã truyền `-Djava.io.tmpdir=/tmp/app` trong `ENTRYPOINT`; vì vậy manifest đặt `TMPDIR=/tmp/app` để native library dùng cùng thư mục. Nếu image không cấu hình sẵn property, hãy truyền runtime argument trong `ENTRYPOINT` hoặc command tương ứng. Biến `TMPDIR` trong manifest không tự chứng minh Java system property có cùng giá trị.

### 8.1. fsGroup và volume permissions

`fsGroup` giúp process truy cập các volume có hỗ trợ group ownership. Cơ chế áp dụng ownership/permission có thể phụ thuộc loại volume và CSI driver. Không phải mọi storage backend đều xử lý giống nhau; kiểm tra quyền thực tế bên trong Pod.

Với volume lớn, việc thay đổi ownership đệ quy lúc mount có thể làm chậm thời gian khởi động. Kubernetes có `fsGroupChangePolicy` cho một số volume hỗ trợ, nhưng trường này không có tác dụng với các ephemeral volume như `emptyDir`, `secret` và `configMap`. Đừng thêm nó với kỳ vọng thay đổi permission của `emptyDir`.

Không mount `configMap` hoặc `secret` vào đường dẫn cần ghi. Các volume này thường được cung cấp chỉ đọc. Nếu ứng dụng cần sửa nội dung, copy file cần thiết vào writable `emptyDir` khi khởi động bằng logic phù hợp, hoặc thiết kế ứng dụng chỉ đọc cấu hình.

### 8.2. Khi nền tảng cấp UID ngẫu nhiên

Một số nền tảng có thể ghi đè UID trong image hoặc cấp UID ngẫu nhiên cho mỗi workload. Khi đó, owner cố định `10001` trong Dockerfile có thể không trùng với UID runtime. Hãy làm theo security policy của nền tảng:

- Xác định UID/GID thực tế mà Pod nhận.
- Cấp quyền group write/traverse cho đúng group được nền tảng hỗ trợ.
- Dùng `fsGroup` nếu storage driver và policy cho phép.
- Tránh tạo thư mục writable cho mọi user nếu chỉ cần chia sẻ trong một group.
- Kiểm thử image với UID thực tế của môi trường, không chỉ UID trong Dockerfile.

Không giả định một quy tắc group cụ thể cho mọi cluster/OpenShift distribution; kiểm tra tài liệu và admission policy của nền tảng đang triển khai.

## 9. Kiểm tra java.io.tmpdir trong ứng dụng

Một smoke check nhỏ giúp phát hiện lỗi permission ngay lúc khởi động thay vì đợi tới request upload hoặc xử lý file đầu tiên.

Ví dụ dùng `ApplicationRunner`:

```java
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class TempDirectoryCheck implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) throws Exception {
        String configured = System.getProperty("java.io.tmpdir");
        Path tempDirectory = Path.of(configured);

        if (!Files.isDirectory(tempDirectory)
                || !Files.isWritable(tempDirectory)) {
            throw new IllegalStateException(
                "Temporary directory is not writable: " + tempDirectory
            );
        }

        Path probe = Files.createTempFile(
            tempDirectory, "native-image-check-", ".tmp"
        );

        Files.delete(probe);
    }
}
```

Đây là kiểm tra khởi động minh họa. Trong ứng dụng thật, cân nhắc chỉ bật nó ở profile kiểm tra hoặc giữ lại nếu việc tạo file tạm là yêu cầu bắt buộc. Không ghi nội dung nhạy cảm vào probe file. Nếu `java.io.tmpdir` không được truyền, code có thể nhận giá trị mặc định của runtime; hãy log giá trị đã chọn và xác minh nó trỏ tới mount writable dự kiến.

Có thể kiểm tra thủ công trong môi trường có shell:

```bash
id
printf 'TMPDIR=%s\n' "$TMPDIR"
test -d /tmp && test -w /tmp
touch /tmp/native-image-permission-check
rm /tmp/native-image-permission-check
```

Nếu dùng dedicated path `/tmp/app`, kiểm tra chính đường dẫn đó thay vì chỉ kiểm tra `/tmp`.

## 10. Những nơi Spring Boot có thể cần ghi file tạm

Ngoài Java API `Files.createTempFile`, các thành phần Spring Boot và thư viện tích hợp có thể cần thư mục writable:

| Thành phần | Nhu cầu | Cấu hình/kiểm tra |
|---|---|---|
| Java temporary files | File tạm mặc định của JDK | `java.io.tmpdir` |
| Servlet multipart upload | Lưu request body upload tạm | `spring.servlet.multipart.location` |
| Embedded Tomcat | Base/work/temp directory trong một số cấu hình | `server.tomcat.basedir` |
| File logging | Ghi log vào file | `logging.file.name` hoặc log ra stdout |
| Cache/file spool | Ghi cache, report hoặc file trung gian | Đường dẫn riêng theo ứng dụng |
| TLS/client libraries | Một số thư viện có thể tạo truststore/key hoặc file tạm | Kiểm tra cấu hình và tài liệu thư viện |

Nếu đặt `spring.servlet.multipart.location=/tmp/app/uploads`, hãy bảo đảm thư mục tồn tại hoặc ứng dụng có thể tạo nó. Với `server.tomcat.basedir`, dùng thư mục con có quyền phù hợp. Không bật file logging vào một đường dẫn chỉ đọc khi container chạy với `readOnlyRootFilesystem`.

Không phải mọi ứng dụng Spring Boot đều cần tất cả các đường dẫn trên. Chỉ tạo và mount thư mục mà tính năng thực sự dùng; kiểm tra bằng test upload, TLS, report generation và các luồng file tương ứng.

## 11. Chẩn đoán lỗi quyền truy cập

Khi native executable báo lỗi ghi file, xác định chính xác path và user của process trước khi thay đổi permission.

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Permission denied tại /tmp | /tmp không writable hoặc mount có mode/owner không phù hợp | Kiểm tra mode 1777, UID/GID và mount options |
| No such file or directory khi tạo temp file | java.io.tmpdir trỏ tới directory chưa tồn tại | Tạo directory trong image hoặc mount đúng path |
| Read-only file system | Root filesystem read-only nhưng path cần ghi chưa được mount | Mount emptyDir/tmpfs/volume vào path đó |
| Executable chạy được nhưng không ghi log | Log path thuộc root hoặc nằm trên read-only filesystem | Ghi stdout/stderr hoặc tạo log directory có owner phù hợp |
| Chạy Docker bình thường nhưng lỗi khi dùng --user | docker run --user ghi đè user của image | Cấp ownership/quyền theo UID/GID được override |
| Chạy local được nhưng lỗi trong Kubernetes | runAsUser, fsGroup, volume hoặc storage driver khác image local | Kiểm tra security context và permission bên trong Pod |
| Upload lỗi nhưng health check pass | Multipart location không writable | Kiểm tra spring.servlet.multipart.location và test upload |
| Temp directory đúng nhưng thư viện native vẫn lỗi | Thư viện dùng TMPDIR, path riêng hoặc yêu cầu khác | Kiểm tra biến môi trường và tài liệu thư viện |

### 11.1. Kiểm tra cấu hình image và runtime

Kiểm tra user được khai báo trong image:

```bash
docker image inspect --format '{{.Config.User}}' my-service:native
```

Kiểm tra container đang chạy với user nào và mount nào được gắn:

```bash
docker inspect --format '{{.Config.User}}' my-service-container
docker inspect --format '{{json .Mounts}}' my-service-container
docker top my-service-container
```

Nếu image có shell và các tiện ích chẩn đoán, có thể chạy kiểm tra:

```bash
id
stat -c '%A %a %u:%g %n' /app /tmp /tmp/app
test -x /app/service
test -w /tmp/app
touch /tmp/app/permission-probe
rm /tmp/app/permission-probe
```

Image tối giản có thể không chứa sh, id hoặc stat. Trong trường hợp đó, không kết luận permission chỉ từ việc không có công cụ. Dùng image debug cùng mount/security context, hoặc kiểm tra bằng code chạy trong chính process native.

### 11.2. Kiểm tra Kubernetes

Xem Pod và security context:

```bash
kubectl get pod <pod-name> -o yaml
kubectl describe pod <pod-name>
kubectl logs <pod-name>
```

Nếu container có shell:

```bash
kubectl exec <pod-name> -- id
kubectl exec <pod-name> -- sh -c 'stat -c "%A %a %u:%g %n" /tmp; test -w /tmp'
```

Nếu volume mount che thư mục đã chuẩn bị trong image, ownership của thư mục trong image không còn quyết định quyền truy cập. Kiểm tra volume sau khi mount, UID/GID thực tế, fsGroup và chính sách CSI driver.

Không giải quyết lỗi bằng cách đổi toàn bộ thư mục ứng dụng thành 0777 hoặc chạy lại container bằng root. Trước tiên tìm path đang ghi, user đang chạy và permission cụ thể cần thiết.

## 12. Nguyên tắc bảo mật khi dùng thư mục tạm

Thư mục tạm có thể chứa nội dung upload, file report, payload hoặc dữ liệu trung gian. Xử lý chúng như dữ liệu có thể nhạy cảm:

- Dùng subdirectory riêng cho ứng dụng với mode tối thiểu, thường 0700.
- Tạo tên file ngẫu nhiên bằng API an toàn như Files.createTempFile; không ghép tên file từ input không tin cậy.
- Không dùng chung temp path giữa các tenant nếu không có cơ chế phân tách và kiểm soát truy cập.
- Xóa file tạm khi hoàn thành; có chính sách dọn dẹp cho file còn lại sau crash.
- Không ghi credential, access token hoặc dữ liệu cá nhân vào temp file nếu không cần thiết.
- Đặt giới hạn dung lượng cho tmpfs/volume và kiểm tra hành vi khi hết dung lượng.
- Giữ /tmp ở mode 1777 nếu dùng như thư mục chung; không thay bằng 0777 hoặc thay owner toàn bộ /tmp.
- Chạy process bằng non-root, drop Linux capabilities không cần thiết và tắt privilege escalation.
- Giữ executable và cấu hình read-only; chỉ cấp writable mount cho những path cần thiết.

Quyền file không thay thế kiểm tra dữ liệu. Nếu ứng dụng nhận file upload, vẫn cần giới hạn kích thước, kiểm tra loại nội dung, xác thực quyền truy cập và tránh xử lý đường dẫn do client kiểm soát.

## 13. Ma trận kiểm thử container non-root

Đừng chỉ xác nhận container khởi động. Hãy kiểm tra các thao tác thực sự cần ghi:

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Start container bằng UID/GID non-root | Process có UID khác 0 |
| Đọc executable và cấu hình | File cần thiết đọc được |
| Đọc java.io.tmpdir | Giá trị trỏ tới directory dự kiến |
| Tạo/xóa temp file | Tạo, ghi và xóa thành công |
| Upload file | Multipart path có quyền ghi và giới hạn dung lượng hoạt động |
| Sinh report/cache | Đường dẫn riêng writable và cleanup đúng |
| Ghi log | Log ra stdout/stderr hoặc file path được cấp quyền |
| Read-only root filesystem | Ứng dụng không ghi vào root filesystem |
| Restart container/Pod | Temp data được xử lý theo đúng vòng đời |
| Mount volume | UID/GID/group permission phù hợp sau khi mount |
| Hết dung lượng temp | Lỗi được xử lý có kiểm soát, không làm mất dữ liệu nghiệp vụ |
| Shutdown | Process dừng và hoàn tất cleanup trong giới hạn thời gian |

Chạy cùng ma trận trên image local và môi trường triển khai thật. Docker local không mô phỏng toàn bộ admission policy, CSI driver, security profile hoặc UID injection của Kubernetes/OpenShift.

## 14. Bài tập thực hành

### Bài tập A — Chuyển Dockerfile sang non-root

Tạo user/group có UID/GID riêng, copy native executable với ownership đúng, tạo /tmp/app và chạy bằng USER. Xác minh process không có UID 0.

**Tiêu chí hoàn thành:** executable đọc/chạy được và tạo/xóa temp file trong directory riêng.

### Bài tập B — Bật read-only root filesystem

Chạy image với --read-only và mount tmpfs cho /tmp. Gọi endpoint có thao tác tạo file tạm hoặc upload. Sau đó bỏ mount /tmp để quan sát lỗi và giải thích vì sao permission/readonly filesystem gây lỗi.

**Tiêu chí hoàn thành:** ứng dụng chạy với root filesystem chỉ đọc và chỉ ghi vào path được cấp.

### Bài tập C — Deploy lên Kubernetes

Thiết lập runAsNonRoot, runAsUser, runAsGroup, fsGroup, readOnlyRootFilesystem và emptyDir. Kiểm tra UID/GID, mount permission và temp file từ bên trong Pod.

**Tiêu chí hoàn thành:** Pod khởi động, readiness pass, endpoint upload/temporary-file hoạt động và không chạy bằng root.

### Bài tập D — Kiểm tra Buildpacks

Build image bằng bootBuildImage hoặc spring-boot:build-image. Inspect Config.User, kiểm tra runtime user và xác minh các thư mục cần ghi. Thử mount volume vào thư mục ứng dụng để thấy mount có thể che ownership được chuẩn bị sẵn trong image.

**Câu hỏi:** vì sao cần kiểm tra lại quyền sau khi đổi run image hoặc mount volume dù Buildpacks mặc định đã dùng non-root user?

### Bài tập E — Kiểm tra runtime system property

Chạy native executable với -Djava.io.tmpdir=/tmp/app, in giá trị system property và tạo một file tạm. So sánh với trường hợp chỉ đặt TMPDIR hoặc chỉ truyền -D vào lệnh native-image lúc build.

**Tiêu chí hoàn thành:** phân biệt được build-time property, runtime property và biến môi trường của native library.

## 15. Checklist trước khi phát hành

- [ ] Final image khai báo user non-root hoặc runtime policy ép process chạy non-root.
- [ ] UID/GID thực tế đã được xác minh; không giả định user của builder là user của runtime.
- [ ] Executable, cấu hình và thư viện đọc được bởi runtime user.
- [ ] Các directory cần ghi đã được tạo và cấp ownership/mode trước USER.
- [ ] File được copy vào final image có ownership phù hợp.
- [ ] /tmp có mode 1777 nếu dùng làm thư mục tạm chung.
- [ ] Temp directory riêng có mode tối thiểu và được runtime user ghi được.
- [ ] java.io.tmpdir đã được cấu hình ở runtime và xác minh trong process.
- [ ] Các biến môi trường như TMPDIR không bị nhầm với Java system property.
- [ ] Multipart, Tomcat, file logging và cache path đã được kiểm tra nếu ứng dụng sử dụng.
- [ ] Root filesystem có thể đặt read-only; writable volume được mount đúng path.
- [ ] Kubernetes security context và volume ownership đã được kiểm tra trong cluster.
- [ ] Đã test UID override hoặc UID ngẫu nhiên nếu nền tảng sử dụng.
- [ ] Temp file có giới hạn dung lượng, cleanup và chính sách dữ liệu phù hợp.
- [ ] Đã chạy smoke/integration test trên final container image.

## Tài liệu tham khảo

- [Dockerfile reference — USER and COPY](https://docs.docker.com/reference/dockerfile/): hành vi của USER, COPY --chown, ownership và quyền trong image.
- [Docker build best practices](https://docs.docker.com/build/building/best-practices/): khuyến nghị chạy service bằng user không có quyền root và chọn UID/GID tường minh.
- [Docker run reference](https://docs.docker.com/engine/containers/run/): user mặc định, --user, working directory và runtime overrides.
- [Paketo — Stacks](https://paketo.io/docs/concepts/stacks/): build image/run image và dedicated non-root user trong các stack Paketo.
- [Kubernetes — Configure a Security Context for a Pod or Container](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/): runAsNonRoot, runAsUser, runAsGroup, fsGroup, readOnlyRootFilesystem và volume ownership.
- [Kubernetes — Application Security Checklist](https://kubernetes.io/docs/concepts/security/application-security-checklist/): khuyến nghị non-root, giảm privilege escalation và read-only root filesystem.
- [GraalVM — Use System Properties in a Native Executable](https://www.graalvm.org/jdk21/reference-manual/native-image/guides/use-system-properties/): phân biệt system property truyền lúc build với option -D truyền lúc chạy native executable.
- [GraalVM Native Image — Command-line Options](https://www.graalvm.org/dev/reference-manual/native-image/overview/HostedvsRuntimeOptions/): hosted options, runtime options và system properties.

## Kết luận

Chạy Spring Boot Native Image bằng user không có quyền root cần chuẩn bị cả danh tính process lẫn quyền của từng đường dẫn. Tạo UID/GID phù hợp, copy executable với ownership đúng, giữ /tmp ở mode 1777 và dùng subdirectory riêng cho file tạm. Nếu bật read-only root filesystem, mount writable tmpfs/volume cho các path thực sự cần ghi; với Kubernetes, kiểm tra runAsNonRoot, fsGroup và quyền volume sau khi mount. Cuối cùng, truyền java.io.tmpdir như runtime property của native executable và xác minh bằng thao tác tạo file thực tế. Khi các bước này được kiểm thử trên final image và môi trường triển khai, ứng dụng có thể chạy với quyền tối thiểu mà vẫn đáp ứng các nhu cầu tạm thời của Spring Boot.
