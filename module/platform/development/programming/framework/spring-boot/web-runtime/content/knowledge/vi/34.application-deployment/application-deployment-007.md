# Thư mục chỉ đọc, tài khoản tiến trình và quyền ghi tệp tạm

## 1. Mục tiêu của bài và vấn đề khi triển khai Spring Boot

Trong chủ đề **Triển khai ứng dụng** của module **Spring Boot - web-runtime**, một ứng dụng Java thường được build thành executable JAR, đóng gói container và chạy sau Kubernetes Service/Ingress. Khi chuyển từ máy phát triển sang container được harden, ứng dụng có thể bất ngờ lỗi ngay lúc khởi động hoặc khi upload file:

~~~text
java.nio.file.AccessDeniedException: /app/...
java.nio.file.FileSystemException: /tmp/...: Read-only file system
java.io.IOException: Permission denied
java.nio.file.FileSystemException: ...: No space left on device
java.lang.IllegalStateException: Unable to create tempDir
~~~

Các thông báo trên là **ví dụ triệu chứng**, không phải một stack trace cố định: tên exception còn phụ thuộc lớp code, Servlet container, filesystem, storage driver và hệ điều hành.

Đề bài cần giải quyết ba quyết định thiết kế riêng biệt:

1. **Filesystem gốc chỉ đọc:** container không được phép ghi vào /app, /etc hoặc các đường dẫn trong image đang chạy.
2. **Tài khoản tiến trình:** JVM chạy bằng một UID/GID không phải root, với những quyền Linux tối thiểu.
3. **Vùng ghi tạm:** những thành phần cần scratch space (Tomcat, Servlet multipart uploads, java.io.tmpdir, thư viện xử lý tệp) vẫn có một mount **có quyền ghi rõ ràng, giới hạn dung lượng và vòng đời đúng**.

Ba mục tiêu **không mâu thuẫn**: một container có thể root filesystem read-only nhưng vẫn ghi được vào **emptyDir/tmpfs/PVC được mount có chủ đích** nếu UID/GID và chế độ truy cập cho phép.

Sau bài này, bạn có thể:
- Phân biệt image layers, root filesystem, mounted volume, OS file permissions và Java temp directory.
- Cấu hình Dockerfile chạy UID/GID không root.
- Bật Kubernetes **readOnlyRootFilesystem**, **runAsNonRoot**, **runAsUser**, **runAsGroup**, **fsGroup** và mount **emptyDir** phù hợp.
- Cấu hình **java.io.tmpdir**, **spring.servlet.multipart.location** và hiểu **server.tomcat.basedir**.
- Chạy lab **Java 17 + Spring Boot 3.3.13** có endpoint kiểm ghi/xóa tệp tạm và multipart upload.
- Chẩn đoán AccessDeniedException, read-only filesystem, ENOSPC, startup/readiness failure, quota và tệp tạm không được dọn.
- Biết trường hợp nào cần PVC/object storage thay vì emptyDir.

## 2. Mô hình file bên trong container

Một filesystem container thường có **image layers** được xây dựng từ Dockerfile cùng một lớp ghi khi container chạy, nhưng lớp ghi này không phải nơi lưu dữ liệu bền vững. Với Docker **--read-only** hoặc Kubernetes **readOnlyRootFilesystem: true**, root filesystem được mount read-only.

~~~text
Image:
  /app/app.jar             JAR cố định trong image
  /etc/...                 cấu hình hệ điều hành
  /usr/lib/jvm/...         Java runtime
          |
          v
Running container with read-only root filesystem
  /app/app.jar             đọc được, KHÔNG ghi được
  /etc                    đọc được, KHÔNG ghi được
  /tmp                    có thể không ghi được nếu không mount riêng
  /scratch --------------> writable emptyDir hoặc tmpfs
  /config  --------------> ConfigMap/Secret read-only
  /data    --------------> PVC nếu ứng dụng thật sự cần persistence
~~~

**readOnlyRootFilesystem chỉ áp dụng root filesystem của container**, không tự biến tất cả volumes thành read-only. Một volume mount có quyền ghi vẫn writable theo mount flags, permissions, security contexts và chính sách runtime.

Điều này khác với:
- **Image bất biến:** image digest không đổi nhưng container có thể có một writable overlay nếu không bật read-only root.
- **volumeMounts.readOnly: true:** một mount cụ thể không cho phép ghi, độc lập với root filesystem.
- **ConfigMap/Secret volumes:** thông thường cung cấp dữ liệu cấu hình/bí mật dưới dạng read-only, không phải scratch disk.
- **UID không root:** ngăn tiến trình dùng đặc quyền root thông thường, nhưng không làm filesystem thành read-only nếu thư mục cho phép ghi.
- **Linux file mode 0444/0555:** quyền truy cập theo file/owner/group; vẫn khác mount read-only.
- **Kubernetes PersistentVolumeClaim:** lưu dữ liệu có vòng đời riêng, không mặc định chỉ đọc hay tạm thời.

Đừng “sửa” lỗi ghi tệp bằng cách chạy container thành root hoặc mount toàn bộ host root filesystem vào Pod. Cần xác định **đường dẫn nào thực sự cần ghi** và cấp quyền tối thiểu cho đúng mount đó.

## 3. Vì sao ứng dụng web vẫn cần ghi tệp khi mã nguồn chỉ đọc?

Một Spring Boot API có thể không gọi FileOutputStream trong business code mà vẫn cần tạo file:

| Thành phần | Khi nào có thể ghi | Chỗ cần kiểm tra |
| --- | --- | --- |
| JDK NIO / Files.createTempFile | Temporary files trong application code | System property java.io.tmpdir hoặc Path truyền tường minh |
| Spring MVC MultipartFile | HTTP multipart/form-data upload, buffering/spooling | spring.servlet.multipart.location |
| Embedded Tomcat | Tomcat base/work/temp directory, servlet context tempdir | server.tomcat.basedir và java.io.tmpdir |
| Third-party PDF/image/video tools | Intermediate output, unzip, cache | Tool-specific TMPDIR/config, subprocess environment |
| Logging | File append/rotation | logging.file.name/path hoặc Logback FileAppender |
| H2/SQLite/file-backed databases | Local persistent data/log files | Datasource URL, file permissions; tránh dùng scratch để lưu dữ liệu quan trọng |
| TLS/library/native components | Temp files, extracted native libraries, caches | java.io.tmpdir, JNI/native library requirements |
| Report/export | Sinh ZIP/CSV/PDF trung gian | Configured workspace hoặc streaming strategy |
| Actuator heapdump/diagnostics | Output lớn khi tác vụ chẩn đoán chạy | Explicit path và disk quota |
| JVM attach tooling | Socket hoặc tệp phụ tùy môi trường | /tmp và runtime tool behavior |

**Không kết luận rằng “app chỉ đọc file JAR nên chắc chắn chạy được với root read-only”.** Servlet container và dependencies có thể tạo temp directories trong startup; uploads có thể ghi disk ngay cả khi controller chỉ đọc InputStream rồi bỏ.

### 3.1. Spring Boot 3.3 multipart có thể ghi ra disk

Spring Boot 3.3 cung cấp:
- **spring.servlet.multipart.enabled**, mặc định true.
- **spring.servlet.multipart.file-size-threshold**, mặc định **0B**: vượt ngưỡng thì multipart content có thể được spool ra đĩa thay vì giữ hoàn toàn trong RAM.
- **spring.servlet.multipart.location**: thư mục trung gian cho uploaded files.
- **spring.servlet.multipart.max-file-size**, mặc định **1MB**.
- **spring.servlet.multipart.max-request-size**, mặc định **10MB**.

Các defaults trên được xác nhận theo **Spring Boot 3.3 application properties**. Nếu root read-only và location không trỏ tới vùng writable, multipart có thể thất bại trong Servlet parsing **trước khi controller nhận được MultipartFile**.

Tăng file-size-threshold lên một giá trị rất lớn để “tránh disk” không phải giải pháp phổ quát: nội dung upload có thể chiếm RAM, làm tăng GC/OOM và vẫn còn library khác cần temp. Nên dùng **scratch mount có giới hạn**, kiểm max-file-size/max-request-size và stream dữ liệu nếu phù hợp.

### 3.2. Tomcat có work directory riêng

**server.tomcat.basedir** là Tomcat base directory; nếu không chỉ định, Spring Boot có thể sử dụng một temporary directory. Tomcat servlet context còn có **jakarta.servlet.context.tempdir** cho ứng dụng cần scratch. Có thể xem Tomcat Host/Context **workDir** trong tài liệu Tomcat.

Đặt **-Djava.io.tmpdir=/scratch** từ khi JVM khởi động cho phép những thành phần dùng Java default temporary directory tìm thấy writable mount. Tuy nhiên, **không phải mọi thư viện đều tuân theo java.io.tmpdir**; có thư viện dùng biến TMPDIR, đường dẫn /tmp hard-coded, app home, current working directory hoặc cấu hình riêng. Phải inventory và test.

### 3.3. Logging nên dùng stdout/stderr

Trong container:
- Ưu tiên **console logging** qua stdout/stderr để container runtime thu thập logs.
- Không mặc định ghi file log vào **/app/logs**, **/var/log** hoặc writable layer.
- Nếu bắt buộc ghi file (vì sản phẩm legacy hoặc integration), mount đúng thư mục với rotation, quota và retention được định nghĩa.
- Tuyệt đối không “chữa” bằng chmod 777 toàn bộ image, hoặc cho root để ghi bất kỳ đường dẫn nào.

## 4. Tài khoản tiến trình: UID, GID và quyền Linux

Linux kiểm file access theo process credentials:
- **UID**: user ID hiệu dụng.
- **GID**: primary group ID.
- **Supplementary groups**: các group bổ sung.
- **Owner/group/other mode bits**, ACL và security modules như SELinux/AppArmor.
- **Mount flags**, read-only mount, storage backend/CSI permissions.

Ví dụ:

~~~text
drwxr-xr-x  root root   /app
-rw-r--r--  root root   /app/app.jar
drwxrwx---  app  app    /scratch
~~~

Một Java process chạy UID 10001, GID 10001:
- Đọc được /app/app.jar nếu permissions cho phép.
- Không thể sửa /app/app.jar khi root filesystem read-only.
- Có thể tạo tệp trong /scratch nếu mount writable và directory mode/group cho phép.
- Không cần quyền root để bind port **8080** (port cao hơn 1023).

Cấu hình chạy không root giảm blast radius khi app bị khai thác, nhưng **không phải sandbox hoàn chỉnh**. Vẫn cần network policy, Secret management, seccomp, capabilities, image scanning, RBAC và input validation.

### 4.1. USER trong Dockerfile khác runAsUser của Kubernetes

- **Dockerfile USER 10001:10001** đặt default process identity khi chạy image.
- **docker run --user 10001:10001** có thể override identity lúc tạo container.
- **Kubernetes runAsUser: 10001 / runAsGroup: 10001** đặt UID/GID cho process trong Pod theo securityContext, có thể override image default.
- **Kubernetes runAsNonRoot: true** yêu cầu runtime không chạy image process dưới root UID.
- **fsGroup: 10001** bổ sung group liên quan tới access trên volumes hỗ trợ, không đồng nghĩa thay owner mọi file trong image.
- **supplementalGroups** có thể mở rộng quyền trên volume; không thêm group rộng không cần thiết.

Không suy luận username từ UID. Nhiều production images dùng numeric UID không có entry tương ứng trong /etc/passwd; một số thư viện cần user.home hoặc getpwuid hoạt động. Kiểm image/base runtime và tránh ứng dụng phụ thuộc vào HOME writable trong root filesystem.

### 4.2. fsGroup không phải phép thay thế cho mọi permission fix

Kubernetes có thể áp **fsGroup** lên volumes hỗ trợ ownership management; process nhận group phù hợp và thư mục có quyền ghi group. Nhưng:
- Hành vi với PVC phụ thuộc storage/CSI driver, NFS root_squash, mount options và SELinux.
- **fsGroupChangePolicy** không áp dụng cho một số ephemeral volume types như emptyDir/ConfigMap/Secret theo tài liệu Kubernetes.
- Một directory được mount read-only vẫn không ghi được dù fsGroup đúng.
- Quyền root của initContainer để chmod/chown mọi nơi có thể bị Pod Security policy cấm hoặc làm lộ security risk.
- Nếu quá nhiều Pod dùng chung một GID rộng, chúng có thể truy cập volume dữ liệu của nhau nếu mounts/policies sai.

Trong lab, **emptyDir + runAsGroup/fsGroup=10001** được dùng và xác minh bằng startup write probe. Ứng dụng thật cần kiểm storage driver và cluster cụ thể.

## 5. Read-only root filesystem: phạm vi bảo vệ và ngoại lệ

Kubernetes cho container:

~~~yaml
securityContext:
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
~~~

Đoạn YAML chỉ là **fragment container securityContext**, chưa phải Pod hoàn chỉnh. Với readOnlyRootFilesystem:
- Không thể ghi vào /app từ root filesystem, ngay cả khi image đã tạo thư mục này.
- Không thể tạo file ở /tmp nếu /tmp thuộc root filesystem và **không có writable mount**.
- Vẫn có thể ghi vào /scratch nếu mount một writable volume tại đó.
- Mount ConfigMap/Secret riêng vẫn đọc được nếu quyền và mount cho phép.
- Bind mount hoặc PVC mount writable vẫn có thể ghi, nên cần xét security policy toàn Pod.

**Chạy root (UID 0) không “vượt qua” read-only mount**, và chạy non-root không bảo đảm root filesystem tự read-only. Đây là hai lớp hardening độc lập.

### 5.1. Một mount tại /scratch có thể che dữ liệu trong image

Nếu Dockerfile tạo /scratch/some-default-file và Kubernetes mount **emptyDir** lên /scratch, file nằm trong image dưới đường dẫn đó **bị mount che đi** khi container chạy. Vì vậy nên để dữ liệu cấu hình mặc định ở /app hoặc /config, còn /scratch chỉ là vùng tạm mới được mount.

### 5.2. Không dùng thư mục image như kho dữ liệu

Một JAR ở /app/app.jar không nên tự ghi bản cập nhật vào /app. Với config runtime, ưu tiên ConfigMap/Secret hoặc môi trường. Với output lâu dài, dùng object storage, database hoặc PVC. Với temporary artifacts, dùng emptyDir/tmpfs có quota và cleanup.

## 6. Chọn volume nào cho tệp tạm?

| Loại | Ghi được? | Tồn tại đến khi nào? | Dùng khi |
| --- | --- | --- | --- |
| Container writable root layer | Có nếu root không read-only | Theo container lifecycle | Không nên dựa vào để giữ dữ liệu |
| emptyDir disk-backed | Có khi mount/permissions đúng | Theo đời Pod; container restart trong cùng Pod vẫn giữ | Tomcat scratch, multipart spool, cache tạm |
| emptyDir medium: Memory | Có | Theo Pod, nhưng nằm trong RAM/tmpfs | Scratch nhỏ, tốc độ cao, phải tính memory |
| Docker --tmpfs | Có khi mount options cho phép | Theo container, không bền vững | Local Docker test với --read-only |
| ConfigMap/Secret volume | Read-only đối với mục đích config/secret | Theo cấu hình Pod/project | Đọc cấu hình và credentials, không làm scratch |
| PersistentVolumeClaim | Tùy access mode/permissions | Theo PVC/PV lifecycle | Output cần sống sau Pod deletion |
| Object storage | Không phải filesystem local trực tiếp | Theo bucket lifecycle | Uploaded files, reports, blobs cần durable storage |

### 6.1. emptyDir không phải persistent storage

Kubernetes tạo emptyDir khi Pod được gán lên node. Một container crash/restart **không tự xóa emptyDir** nếu vẫn cùng Pod. Nhưng khi Pod bị remove/evicted khỏi node, dữ liệu emptyDir bị xóa. Không dùng nó cho ảnh khách hàng, đơn hàng, hồ sơ hay tài liệu cần sống sau deployment.

Tệp tạm có thể được dọn khi request hoàn tất, nhưng nếu process bị SIGKILL, cleanup trong finally không bảo đảm chạy. Đối với emptyDir, Pod vẫn còn thì tệp orphan có thể tồn tại sau container restart; cần cơ chế dọn stale files theo TTL/ownership policy.

### 6.2. emptyDir disk-backed và tmpfs Memory

- **emptyDir: {}** dùng local ephemeral storage trên node; có thể bị ảnh hưởng bởi disk pressure, kubelet eviction và ephemeral-storage limit.
- **emptyDir.medium: Memory** dùng tmpfs; nội dung chiếm memory của container/Pod theo cách Kubernetes tính, có thể đẩy tiến trình tới OOM.
- **sizeLimit** hữu ích nhưng không có nghĩa tất cả storage drivers/node environments đều có cùng hành vi hard limit ở mọi thời điểm. Phải quan sát thực tế.
- Không tạo một tmpfs vô hạn với payload uploads không giới hạn; memory-backed uploads lớn cạnh tranh trực tiếp với Java heap, direct buffers, thread stacks và native memory.

### 6.3. Không dùng PVC chỉ để tránh cấu hình temp

PVC cung cấp persistence nhưng thường không cần thiết cho request scratch. Nó có vấn đề chia sẻ dữ liệu, cleanup và storage cost riêng. Nếu mục tiêu chỉ là multipart spooling và File.createTempFile, emptyDir có quota là lựa chọn phổ biến. Nếu file phải bền vững, copy/stream vào object storage hoặc database theo business transaction.

## 7. Cấu hình Java và Spring Boot trỏ đúng thư mục tạm

Trong lab, quy ước **/scratch** là mount writable duy nhất cho tệp trung gian:

~~~text
/scratch/
  multipart/           vùng Spring Servlet multipart spooling
  tomcat.*/            thư mục do embedded Tomcat tạo khi cần
  probe-*.tmp          file tạo khi kiểm quyền ghi, xóa ngay
~~~

Ba lớp cần cấu hình đồng nhất:

**Java runtime, trước khi process khởi động:**

~~~bash
java -Djava.io.tmpdir=/scratch -jar /app/app.jar
~~~

Trong Docker có thể dùng:

~~~dockerfile
ENV JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=/scratch"
~~~

**Spring Boot multipart:**

~~~yaml
spring:
  servlet:
    multipart:
      location: /scratch/multipart
      file-size-threshold: 0B
      max-file-size: 1MB
      max-request-size: 2MB
~~~

**Tomcat base directory tùy chọn:**

~~~yaml
server:
  tomcat:
    basedir: /scratch/tomcat
~~~

Dòng **server.tomcat.basedir** chỉ là **fragment tùy chọn**, không nằm trong lab mặc định. Nếu khai báo, phải bảo đảm Tomcat tạo/sử dụng path với quyền phù hợp **từ thời điểm startup**; không đợi một ApplicationRunner tạo directory sau khi web server đã khởi động.

Khi không cấu hình basedir, Spring Boot 3.3 nói rằng Tomcat base directory là một **temporary directory**; đổi java.io.tmpdir trước JVM startup giúp default temp có vị trí writable. Phải kiểm bằng chạy container thực vì Tomcat và các library khác có thể có work directories riêng.

### 7.1. Vì sao không chỉ đặt TMPDIR environment variable?

Java có system property **java.io.tmpdir**, và Java temp APIs thường dùng property này. Biến môi trường **TMPDIR** có thể ảnh hưởng một số native tools/JVM startup tùy nền tảng nhưng không nên coi là cách duy nhất điều khiển Java tmp path. Đặt -Djava.io.tmpdir ở JVM launch time là rõ ràng hơn; đồng thời cấu hình các thư viện có đường dẫn riêng.

Không nên gọi **System.setProperty("java.io.tmpdir", "/scratch")** trong một Controller đang chạy và kỳ vọng mọi JDK/class đã cache default temp path sẽ thay đổi. Hãy cấu hình trước khi JVM khởi động và test.

### 7.2. Quyền ghi nên xác minh bằng thao tác thật

**Files.isWritable(path)** hữu ích nhưng không đủ chứng minh có dung lượng, quota, ACL, mount flags hoặc namespace permissions đúng ở thời điểm ghi. Một startup check an toàn có thể:
1. Đảm bảo directory tồn tại.
2. Tạo tệp ngẫu nhiên bằng **Files.createTempFile** trong directory dự kiến.
3. Ghi một chuỗi nhỏ.
4. Đọc kiểm tra nếu cần.
5. Xóa trong finally.
6. Không log nội dung file hoặc path bí mật.

Nếu startup không ghi được scratch, nên fail startup hoặc giữ readiness false khi functionality bắt buộc phụ thuộc vào vùng đó, thay vì trả healthy rồi thất bại ở upload đầu tiên.

## 8. Lab Spring Boot 3.3.13 + Java 17: temp file và multipart upload

Lab này cố tình dùng:
- Embedded Tomcat và **spring-boot-starter-web**.
- **spring-boot-starter-actuator** cho readiness/liveness probes.
- Một **ApplicationRunner** kiểm writable scratch khi khởi động.
- **POST /api/temp/probe** tạo/ghi/đọc/xóa temp file.
- **POST /api/upload** nhận multipart file rồi tính SHA-256 và độ dài, không lưu file vĩnh viễn.
- Cấu hình multipart location sang **/scratch/multipart**.
- Docker image chạy **UID/GID 10001**, root filesystem read-only khi Docker/Kubernetes mount.
- Kubernetes emptyDir writable ở /scratch, readOnlyRootFilesystem=true và fsGroup.

**Lab chỉ dùng dữ liệu giả và chạy localhost/staging được phép.** Các endpoints POST không có authentication để dễ thử; **không expose lab này ra internet**. Production phải thêm authentication, authorization, rate limiting, content validation, scanning nếu cần, quotas và không dùng temporary upload file như durable asset.

### 8.1. Cây thư mục

~~~text
readonly-runtime-demo/
├── pom.xml
├── Dockerfile
├── k8s.yaml
└── src/
    ├── main/
    │   ├── java/com/example/readonly/
    │   │   └── ReadonlyRuntimeApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/com/example/readonly/
            └── FilesystemHttpTest.java
~~~

### 8.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>readonly-runtime-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Không cần starter-validation cho hai endpoint đơn giản của lab. Trong ứng dụng production có DTO validation, dùng thêm **spring-boot-starter-validation** theo đúng phạm vi.

### 8.3. application.yml

**src/main/resources/application.yml:**

~~~yaml
server:
  port: 8080

spring:
  servlet:
    multipart:
      location: /scratch/multipart
      file-size-threshold: 0B
      max-file-size: 1MB
      max-request-size: 2MB

app:
  temp-dir: /scratch

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
~~~

**Các chi tiết quan trọng:**
- **app.temp-dir** là property riêng của lab, được Java Environment đọc; không phải Spring Boot property built-in.
- **spring.servlet.multipart.location** là cấu hình chuẩn của Boot, dùng cho Servlet multipart.
- **file-size-threshold: 0B** cho phép kiểm thực tế path có quyền ghi khi multipart cần spool.
- **max-file-size/max-request-size** là bảo vệ đầu vào cơ bản nhưng không thay disk quota/concurrency limits.
- **probes.enabled** tạo **/actuator/health/liveness** và **/actuator/health/readiness**, kể cả khi không phát hiện Kubernetes.
- Chỉ expose **health** từ Actuator; production còn cần network/authentication policy cho management endpoints.

Nếu chạy JAR trực tiếp trên máy không có /scratch, phải override cả **app.temp-dir** và **spring.servlet.multipart.location**; phần 8.7 có lệnh đúng cho local.

### 8.4. Java source đầy đủ

**src/main/java/com/example/readonly/ReadonlyRuntimeApplication.java:**

~~~java
package com.example.readonly;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@SpringBootApplication
public class ReadonlyRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReadonlyRuntimeApplication.class, args);
    }
}

@Configuration
class TempBootstrap {

    @Bean
    ApplicationRunner ensureScratchWritable(Environment env) {
        return args -> {
            Path root = Path.of(
                env.getProperty("app.temp-dir", "/scratch")
            ).toAbsolutePath().normalize();

            // Tạo thư mục cần thiết sau khi volume đã được mount.
            Files.createDirectories(root.resolve("multipart"));

            Path probe = Files.createTempFile(
                root, "startup-probe-", ".tmp"
            );
            try {
                Files.writeString(
                    probe, "ready", StandardCharsets.UTF_8
                );
                String actual = Files.readString(
                    probe, StandardCharsets.UTF_8
                );
                if (!"ready".equals(actual)) {
                    throw new IOException("Scratch readback mismatch");
                }
            } finally {
                Files.deleteIfExists(probe);
            }
        };
    }
}

record UploadSummary(long bytes, String sha256) {}

@RestController
class TempController {

    private final Path scratch;

    TempController(Environment env) {
        this.scratch = Path.of(
            env.getProperty("app.temp-dir", "/scratch")
        ).toAbsolutePath().normalize();
    }

    @PostMapping("/api/temp/probe")
    Map<String, Object> tempProbe() throws IOException {
        Path file = Files.createTempFile(
            scratch, "request-probe-", ".txt"
        );
        try {
            Files.writeString(
                file, "temporary-data", StandardCharsets.UTF_8
            );
            String read = Files.readString(
                file, StandardCharsets.UTF_8
            );
            return Map.of(
                "writable", "temporary-data".equals(read),
                "deletedAfterResponse", true
            );
        } finally {
            Files.deleteIfExists(file);
        }
    }

    @PostMapping(
        path = "/api/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    ResponseEntity<UploadSummary> upload(
            @RequestParam("file") MultipartFile file
    ) throws IOException, NoSuchAlgorithmException {

        MessageDigest sha = MessageDigest.getInstance("SHA-256");
        long totalBytes = 0;
        byte[] buffer = new byte[8192];

        // Chỉ đọc stream, không tin tên file từ client
        // và không chuyển thẳng nó thành server path.
        try (InputStream in = file.getInputStream()) {
            int count;
            while ((count = in.read(buffer)) != -1) {
                sha.update(buffer, 0, count);
                totalBytes += count;
            }
        }

        UploadSummary result = new UploadSummary(
            totalBytes,
            HexFormat.of().formatHex(sha.digest())
        );
        return ResponseEntity.ok(result);
    }
}
~~~

### 8.5. Giải thích code theo từng tầng

**ApplicationRunner:**
- Chạy sau khi Spring Boot đã dựng application context và embedded server, nhưng trước mốc ứng dụng sẵn sàng phục vụ theo lifecycle thông thường.
- Tạo thư mục **/scratch/multipart** trên writable volume và kiểm tạo/ghi/đọc/xóa một temp file.
- Nếu IOException/AccessDeniedException xuất hiện, startup thất bại thay vì để instance ready rồi mới biết upload hỏng.
- Nếu root mount chưa writable hoặc fsGroup không cấp quyền như dự kiến, đây là lỗi có thể quan sát ngay khi khởi động.

**Lưu ý quan trọng:** Tomcat có thể phải tạo base/temp directory **trước ApplicationRunner**, vì server khởi động trước runner. Do đó Java system property **java.io.tmpdir** phải được đặt **trước khi JVM start**, không đợi ApplicationRunner. Phần Docker/Kubernetes cấu hình JAVA_TOOL_OPTIONS từ đầu.

**Temp probe endpoint:**
- **Files.createTempFile(scratch, prefix, suffix)** dùng tên khó đoán thay vì client-controlled file path, giảm rủi ro collision/symlink race.
- **Files.writeString / readString** kiểm quyền ghi thực tế, không chỉ Files.isWritable().
- **finally Files.deleteIfExists** giúp cleanup khi request xử lý bình thường hoặc ném exception.
- Field **deletedAfterResponse** trong demo chỉ biểu thị server đã đi tới cleanup khi method kết thúc bình thường, không phải một bằng chứng rằng file còn/đã bị dọn trong mọi trường hợp (SIGKILL có thể chặn finally). Client không nên dùng field đó làm bằng chứng bảo mật.
- Không trả absolute scratch path/UID, tên temp file hoặc thông tin host trong response public.

**Upload endpoint:**
- Servlet multipart resolver có thể sử dụng **/scratch/multipart** trước khi Controller được gọi, theo ngưỡng cấu hình.
- Controller đọc file InputStream thành từng buffer 8KiB, tính **SHA-256** và byte count.
- Không lấy **MultipartFile.getOriginalFilename()** rồi ghép vào Path. Filename là input **không đáng tin**, có thể chứa path traversal hoặc ký tự độc hại.
- File upload không được lưu bền vững; sau khi request hoàn tất, Servlet/container có thể dọn các temporary multipart parts theo lifecycle.
- SHA-256 là fingerprint dữ liệu, không phải kiểm antivirus hoặc kiểm MIME type.
- Nếu cần lưu file thật, nên stream sang object storage hoặc lưu trong storage service được phân quyền, không giữ ở emptyDir như nguồn dữ liệu chính.

**Mã và lỗi:** lab để IOException nổi lên 5xx khi vùng tạm mất khả năng ghi. Production nên có exception handling thân thiện, log đã redacted, metrics và readiness/admission policy khi disk gần đầy. Đừng bắt mọi IOException rồi trả HTTP 200.

### 8.6. Không đánh tráo filesystem read-only bằng ứng dụng không bao giờ ghi

Lab chủ động kiểm quyền ghi; một ứng dụng chỉ trả JSON hello-world có thể vẫn chạy với root read-only ngay cả khi thiếu scratch, khiến test chưa đủ. Multipart, reporting, exports và Tomcat startup là những đường cần kiểm. Trên production nên thêm một regression test **rootfs read-only + writable temp mount** vào CI/container test, thay vì chỉ test Java code ngoài container.

## 9. JUnit integration test trên HTTP server thật

**src/test/java/com/example/readonly/FilesystemHttpTest.java:**

~~~java
package com.example.readonly;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class FilesystemHttpTest {

    @DynamicPropertySource
    static void configureTemp(DynamicPropertyRegistry registry) {
        // Môi trường test chạy trên máy local:
        // sử dụng temp path của OS thay vì /scratch chỉ có trong container.
        registry.add(
            "app.temp-dir",
            () -> System.getProperty("java.io.tmpdir")
        );
        registry.add(
            "spring.servlet.multipart.location",
            () -> System.getProperty("java.io.tmpdir")
        );
    }

    @Autowired
    TestRestTemplate http;

    @Test
    void tempProbeCanWriteAndDelete() {
        ResponseEntity<Map> response =
            http.postForEntity("/api/temp/probe", null, Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        Map<?, ?> body = response.getBody();
        assertNotNull(body);
        assertEquals(Boolean.TRUE, body.get("writable"));
        assertEquals(Boolean.TRUE, body.get("deletedAfterResponse"));
    }

    @Test
    void multipartUploadCanBeParsedOnRealTomcat() {
        byte[] bytes = "abc\n".getBytes(StandardCharsets.UTF_8);

        ByteArrayResource resource = new ByteArrayResource(bytes) {
            @Override
            public String getFilename() {
                return "sample.txt";
            }
        };

        MultiValueMap<String, Object> form =
            new LinkedMultiValueMap<>();
        form.add("file", resource);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        HttpEntity<MultiValueMap<String, Object>> request =
            new HttpEntity<>(form, headers);

        ResponseEntity<Map> response =
            http.postForEntity("/api/upload", request, Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        Map<?, ?> body = response.getBody();
        assertNotNull(body);
        assertEquals(4L, ((Number) body.get("bytes")).longValue());

        String sha = String.valueOf(body.get("sha256"));
        assertTrue(sha.matches("[0-9a-f]{64}"));
    }
}
~~~

### 9.1. Vì sao cần @SpringBootTest(RANDOM_PORT)?

**@SpringBootTest(webEnvironment=RANDOM_PORT)** mở embedded Tomcat thật trên một port ngẫu nhiên. Request multipart sẽ đi qua Servlet multipart parsing/temporary storage, nên test gần với môi trường web-runtime hơn một unit test gọi trực tiếp controller.upload().

**@DynamicPropertySource** override app.temp-dir và spring.servlet.multipart.location bằng temp directory của OS test host; không yêu cầu máy developer phải có /scratch. Nhưng test này **không tự kiểm readOnlyRootFilesystem**, vì máy local không mount rootfs read-only. Cần chạy Docker/Kubernetes kiểm riêng.

### 9.2. Test không in SHA-256 cố định khi không cần

Test assert hash có 64 ký tự hex và byte count đúng; không khóa stdout vào log output của Spring Boot. Nếu API contract quy định chính xác SHA-256, có thể tính expected digest theo fixture và compare, nhưng mục tiêu bài là filesystem/temporary upload path.

### 9.3. Lưu ý khi test JVM temp path

Một số Java APIs/library cache default temp location từ JVM startup. DynamicPropertySource chỉ thay **Spring environment properties** như app.temp-dir/multipart.location; nó không chủ động thay **java.io.tmpdir** sau khi JVM bắt đầu. Trong container, property JVM phải được set từ Java startup command hoặc JAVA_TOOL_OPTIONS.

## 10. Chạy JAR trên máy local

Cần JDK 17+, Maven và cổng 8080 trống. Trong thư mục project:

~~~bash
mvn test
mvn package
~~~

Chạy trực tiếp trên Linux/macOS với /tmp writable:

~~~bash
java -Djava.io.tmpdir=/tmp \
  -jar target/readonly-runtime-demo-1.0.0.jar \
  --app.temp-dir=/tmp \
  --spring.servlet.multipart.location=/tmp
~~~

**Lưu ý:** đây là lab trên máy local, không bật root filesystem read-only. Nếu máy không có /tmp hoặc không writable, thay bằng directory tạm đã tạo có quyền phù hợp; kiểm command line arguments không bị tool/IDE bỏ.

Tại terminal khác, tạo một file mẫu:

~~~bash
printf 'abc\n' > sample.txt

curl -i -X POST http://localhost:8080/api/temp/probe
curl -i -F "file=@sample.txt" http://localhost:8080/api/upload
curl -i http://localhost:8080/actuator/health/readiness
~~~

Response thành công từ **POST /api/temp/probe** có body theo JSON object:

~~~json
{"writable":true,"deletedAfterResponse":true}
~~~

Response từ **POST /api/upload** có **bytes=4** và **sha256** là chuỗi 64 ký tự hex. Không cam kết thứ tự JSON properties hoặc HTTP headers byte-for-byte. Log startup chứa timestamp, thread names và thông tin runtime biến đổi theo môi trường.

**Kiểm thử không nên dùng dữ liệu thật nhạy cảm:** tệp ví dụ chứa "abc" và ký tự xuống dòng. Không upload secrets, ảnh cá nhân hoặc tài liệu production vào demo không có auth.

## 11. Dockerfile non-root và root filesystem read-only

Tệp **Dockerfile** dùng Ubuntu-based Eclipse Temurin JRE 17 và đặt UID/GID 10001:

~~~dockerfile
FROM eclipse-temurin:17-jre-jammy

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 \
       --home-dir /nonexistent \
       --shell /usr/sbin/nologin app \
    && mkdir -p /app /scratch \
    && chown 10001:10001 /app /scratch

WORKDIR /app
COPY --chown=10001:10001 \
    target/readonly-runtime-demo-1.0.0.jar /app/app.jar

ENV JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=/scratch"

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

**Giải thích:**
- **FROM ...:17-jre-jammy** dùng nền Java 17 với các Linux tools để tạo account lúc build. Cần pin image digest và quét CVEs trong production.
- **groupadd/useradd** chỉ chạy ở build layer, không làm runtime Java có root.
- **COPY --chown** đặt owner của JAR, nhưng root filesystem read-only vẫn bảo vệ khỏi ghi.
- **USER 10001:10001** đặt non-root default. K8s vẫn có securityContext để yêu cầu và kiểm.
- **JAVA_TOOL_OPTIONS** set java.io.tmpdir **ngay từ lúc JVM start**. JDK có thể log "Picked up JAVA_TOOL_OPTIONS"; đó là log thông thường.
- **EXPOSE 8080** chỉ là metadata cho container; port publish cần docker run -p hoặc Kubernetes Service.
- **JSON exec-form ENTRYPOINT** giúp JVM nhận signals theo container runtime semantics, tránh shell wrapper không forward TERM.

**Không mount host Docker socket** vào ứng dụng và không dùng privileged container chỉ để ghi temp file. Không chmod -R 777 /app hoặc /scratch; cấp owner/group được định nghĩa rõ.

### 11.1. Build image

~~~bash
mvn package
docker build -t readonly-runtime-demo:1.0.0 .
~~~

**Tự chạy image bình thường** có thể hoạt động vì default container root overlay writable. Đó **chưa phải test read-only**. Muốn kiểm security boundary phải chạy Docker với **--read-only** và cấp tmpfs mount riêng:

~~~bash
docker run --rm --name readonly-runtime-demo \
  -p 127.0.0.1:8080:8080 \
  --read-only \
  --tmpfs /scratch:rw,nosuid,nodev,noexec,size=64m,uid=10001,gid=10001,mode=0770 \
  readonly-runtime-demo:1.0.0
~~~

Docker --tmpfs mount tạo writable scratch memory filesystem tại /scratch, còn /app và image root vẫn read-only. UID/GID mount khớp process. Tùy Docker phiên bản và platform (Linux/Docker Desktop), cách áp dụng tùy chọn uid/gid/mode có thể khác; kiểm **docker exec ... id**, **ls -ld /scratch** và việc ghi thật.

**noexec** giúp hạn chế chạy binaries từ scratch. Nhưng một số native libraries/JNI tools thực sự cần executable temp; khi đó phải điều chỉnh theo threat model, không xóa noexec mà không kiểm lý do.

### 11.2. Docker smoke test

Khi container đang chạy ở terminal khác:

~~~bash
curl -i -X POST http://localhost:8080/api/temp/probe

printf 'abc\n' > sample.txt
curl -i -F "file=@sample.txt" http://localhost:8080/api/upload

docker exec readonly-runtime-demo id
docker exec readonly-runtime-demo sh -c 'touch /app/should-fail'
~~~

Ba lệnh đầu dự kiến thành công với localhost demo. Lệnh **touch /app/should-fail** dự kiến **thất bại** vì root filesystem read-only; CLI có thể báo **Read-only file system** hoặc **Permission denied** tùy tầng. Đây là một **negative check có chủ đích**, không phải dấu hiệu app hỏng.

Trong lab Docker image Ubuntu có sh/id/touch. Với distroless image, không có shell/coreutils; khi đó cần kiểm qua Java probe, debug ephemeral container hoặc integration test thích hợp, không lấy việc thiếu lệnh sh làm bằng chứng filesystem sai.

### 11.3. Test lỗi khi thiếu scratch

Không dùng production! Nếu chạy image với **--read-only nhưng không có --tmpfs /scratch**, Spring Boot có thể không khởi động vì java.io.tmpdir=/scratch không writable khi embedded Tomcat cần temp. Lỗi có thể xảy ra **trước ApplicationRunner**, nên không nhất thiết xuất hiện message từ startup probe. Điều này chứng minh cần mount scratch trước khi JVM chạy.

Nếu muốn test có kiểm soát mà không ảnh hưởng container khác, dùng một container riêng, timeout ngắn và đọc logs, sau đó xóa container. Không sửa image thành root để “giúp lab chạy”.

## 12. Kubernetes Deployment + Service đầy đủ

Sau khi build image, với local **kind cluster** có thể load image:

~~~bash
docker build -t readonly-runtime-demo:1.0.0 .
kind load docker-image readonly-runtime-demo:1.0.0
~~~

Nếu dùng cluster khác, publish image tới private registry đã được phê duyệt; **không giả định image local của Docker tự xuất hiện trong mọi cluster**.

Tệp **k8s.yaml**:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: readonly-runtime-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: readonly-runtime-demo
  template:
    metadata:
      labels:
        app: readonly-runtime-demo
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: web
          image: readonly-runtime-demo:1.0.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: JAVA_TOOL_OPTIONS
              value: "-Djava.io.tmpdir=/scratch"
          securityContext:
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: scratch
              mountPath: /scratch
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
              ephemeral-storage: 64Mi
            limits:
              memory: 512Mi
              ephemeral-storage: 256Mi
      volumes:
        - name: scratch
          emptyDir:
            sizeLimit: 64Mi
---
apiVersion: v1
kind: Service
metadata:
  name: readonly-runtime-demo
spec:
  type: ClusterIP
  selector:
    app: readonly-runtime-demo
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

### 12.1. Vì sao manifest đặt securityContext ở hai nơi?

**Pod securityContext:**
- **runAsUser/runAsGroup**: UID/GID của Java process.
- **runAsNonRoot: true**: không cho app chạy UID 0.
- **fsGroup: 10001**: group liên quan đến volumes hỗ trợ.
- **seccompProfile: RuntimeDefault**: dùng profile seccomp mặc định của runtime nếu môi trường hỗ trợ.

**Container securityContext:**
- **readOnlyRootFilesystem: true**: root filesystem read-only.
- **allowPrivilegeEscalation: false**: không cho tiến trình nâng đặc quyền theo cơ chế áp dụng.
- **capabilities.drop: ALL**: loại Linux capabilities bổ sung, phù hợp một HTTP Java service chỉ bind port 8080.

Những settings này giúp align với một phần **Pod Security Restricted** nhưng không tuyên bố manifest được chấp nhận ở mọi admission policy. Kiểm security policy riêng của cluster và phiên bản Kubernetes.

### 12.2. Mount emptyDir giúp root read-only nhưng temp writable

Container chỉ có writable mount được khai báo là **/scratch**. Spring:
- java.io.tmpdir=/scratch;
- spring.servlet.multipart.location=/scratch/multipart;
- ApplicationRunner tạo /scratch/multipart rồi probe quyền ghi;
- Tomcat có thể tạo temporary base directory bên dưới java.io.tmpdir.

Nếu volume ownership của cluster không phù hợp, process non-root có thể gặp AccessDeniedException. **Startup probe thật sẽ phát hiện**. Cần kiểm fsGroup, SELinux, security admission và storage behavior thực; không tùy tiện thay runAsUser=0 hoặc chmod 777.

### 12.3. resource limits và eviction

- **emptyDir.sizeLimit=64Mi** là giới hạn dữ liệu scratch ở volume theo Kubernetes semantics.
- **ephemeral-storage request/limit** tính tài nguyên local ephemeral storage theo Kubernetes accounting; workload còn dùng logs và các loại storage khác, nên phải đo tổng.
- Khi local storage thiếu, kubelet có thể evict Pod hoặc ứng dụng nhận **No space left on device**.
- Spring Boot readiness/liveness **không mặc nhiên kiểm disk writable trên mỗi request**. ApplicationRunner chỉ kiểm lúc startup; khi runtime hết disk, cần custom health/admission/metrics nếu yêu cầu.

**Không đặt mọi upload vào emptyDir rồi mặc định sizeLimit sẽ bảo vệ khỏi mọi đường OOM/eviction**. Với multipart uploads song song, quota 64Mi có thể bị dùng hết bởi nhiều requests nhỏ dưới per-file limit.

### 12.4. Không mount /tmp chỉ vì thói quen

Trong lab **java.io.tmpdir=/scratch**, Tomcat và multipart đều dùng scratch đã định nghĩa. Các thư viện khác có thể hard-code /tmp. Nếu kiểm thử phát hiện thật sự cần /tmp, chọn một writable mount riêng với giới hạn và permissions, hoặc cấu hình library chuyển về /scratch. Không mount host /tmp vào Pod, không mở root filesystem thành writable chỉ để thỏa một dependency chưa điều tra.

## 13. Chạy thử Kubernetes và đọc tín hiệu thành công

Sau khi có cluster/image:

~~~bash
kubectl apply -f k8s.yaml
kubectl rollout status deployment/readonly-runtime-demo
kubectl get pods -l app=readonly-runtime-demo
kubectl get deployment readonly-runtime-demo
~~~

Nếu Pods READY, có thể port-forward service ở terminal riêng:

~~~bash
kubectl port-forward service/readonly-runtime-demo 8080:80
~~~

Tại terminal khác:

~~~bash
curl -i http://localhost:8080/actuator/health/readiness
curl -i -X POST http://localhost:8080/api/temp/probe

printf 'abc\n' > sample.txt
curl -i -F "file=@sample.txt" http://localhost:8080/api/upload
~~~

**Kỳ vọng có điều kiện:** nếu Kubernetes áp permissions/fsGroup và volume mount đúng, readiness trả HTTP 200 và hai POST thành công. Nếu không, Pod có thể CrashLoopBackOff hoặc readiness fail; xem logs/events thay vì tự nới quyền.

Để kiểm UID/GID/volumes trong Pod:

~~~bash
kubectl exec deployment/readonly-runtime-demo -- id
kubectl exec deployment/readonly-runtime-demo -- ls -ld /app /scratch
kubectl exec deployment/readonly-runtime-demo -- sh -c 'touch /app/blocked'
kubectl exec deployment/readonly-runtime-demo -- sh -c 'touch /scratch/allowed && rm /scratch/allowed'
~~~

**touch /app/blocked** phải thất bại trên root filesystem read-only; **touch /scratch/allowed** phải thành công. Lệnh đầu có exit code khác 0 là kết quả kiểm tra mong muốn. Không dùng lệnh rm với wildcard, không xóa tệp người dùng; đường /scratch/allowed là tên thử riêng của lab.

Nếu cluster dùng distroless image không có sh, thực hiện test theo endpoint Java hoặc một debug workflow có quyền. Không đổi production security context chỉ để có shell.

### 13.1. Khi test Pod gặp CrashLoopBackOff

~~~bash
kubectl describe pod -l app=readonly-runtime-demo
kubectl logs deployment/readonly-runtime-demo --previous
kubectl get events --sort-by=.lastTimestamp
~~~

Lệnh **kubectl describe pod -l** phụ thuộc phiên bản kubectl và số Pod được match; nếu không hỗ trợ, dùng **kubectl get pods -l app=readonly-runtime-demo** lấy tên Pod rồi describe đúng tên. **--previous** chỉ có log nếu container đã restart trước đó; nếu không, đọc logs hiện tại.

Tìm dấu hiệu:
- Unable to create tempDir / No space left on device.
- Permission denied / Read-only file system.
- ImagePullBackOff do image chưa được load/publish.
- runAsNonRoot admission rejected do image/runtime user mismatch.
- Mismatch giữa /scratch mount và java.io.tmpdir.
- Startup failure do config/port/libraries khác.

## 14. Khi nào cần quyền ghi vào /tmp, /var/tmp hay user.home?

### 14.1. java.io.tmpdir

Java **Files.createTempFile(prefix,suffix)** không truyền parent thường dùng default temp directory theo runtime. Trong container read-only, cần bảo đảm đường dẫn ấy là writable mount. Đặt **-Djava.io.tmpdir** từ lúc launch là cách rõ ràng.

### 14.2. TMPDIR và native subprocess

Một native executable hoặc external tool có thể đọc **TMPDIR**, **TMP** hoặc biến riêng, không quan tâm java.io.tmpdir. Khi sử dụng ImageMagick, ffmpeg, LibreOffice headless hay custom tools, phải kiểm đúng contract của tool và sandbox cho output. Đừng chấp nhận path do client đưa để làm thư mục temp.

### 14.3. user.home và cache

Một số SDK ghi cache vào **user.home/.cache**, **~/.config** hoặc current working directory. Nếu USER 10001 không có writable home, cần:
- Cấu hình cache directory cụ thể vào writable scratch.
- Hoặc vô hiệu disk cache khi không cần.
- Hoặc dùng một dedicated writable home mount với quota.
- Không tự động mở quyền ghi toàn /home hoặc /app.

### 14.4. Access logs, GC logs và heap dumps

Nếu bật:
- **logging.file.name=/app/logs/service.log** sẽ lỗi khi /app read-only. Ưu tiên console logs.
- **server.tomcat.accesslog.enabled=true** và directory mặc định có thể ghi về Tomcat base/logs; cần config đường dẫn writable/rotation.
- **-Xlog:gc:file=/app/gc.log** cần writable path; với read-only root, dùng stdout GC logging hoặc mount riêng.
- **-XX:HeapDumpPath=/app** sẽ lỗi khi tạo dump. Heap dump có thể chứa secrets/PII; không bật tùy tiện và phải bảo vệ quyền truy cập.
- External libraries tạo native .so/.dll trong temp có thể gặp **noexec**; cần kiểm chứ không tự tắt mọi mount flags.

**Một release không nên qua QA nếu chỉ chạy được khi root filesystem writable.** Hãy có integration test container với flags/policies thực.

## 15. Cách đọc lỗi Permission denied, Read-only file system và ENOSPC

| Lỗi/triệu chứng | Tầng nghi ngờ | Cách kiểm |
| --- | --- | --- |
| Read-only file system khi ghi /app | readOnlyRootFilesystem hoặc mount ro | Xem mount flags, volumeMounts và path |
| AccessDeniedException /scratch | UID/GID/ACL/SELinux hoặc mount flags | id, ls -ld, securityContext, storage driver |
| No such file or directory | Parent directory chưa được tạo hoặc volume mount che path | Kiểm directory tồn tại trước request |
| Unable to create tempDir lúc startup | Tomcat/JVM dùng temp path không writable | JAVA_TOOL_OPTIONS, java.io.tmpdir, basedir |
| Multipart request trả 500 trước Controller | Servlet multipart location thiếu quyền | spring.servlet.multipart.location, temp dir, logs |
| Upload nhỏ thành công, upload lớn fail | Disk threshold, size limit, quota | max-file-size, max-request-size, sizeLimit |
| No space left on device | emptyDir/node disk/pvc/quotas đầy | df/du, ephemeral-storage metrics/events |
| OOMKilled khi dùng tmpfs | Memory-backed emptyDir cạnh tranh với heap/native memory | Pod memory limit, tmpfs usage |
| permission denied sau đổi image UID | Mount owner/group không hợp UID mới | runAsUser, runAsGroup, fsGroup |
| File ghi vào PVC nhưng không đọc lại sau restart | Mount path/StorageClass/lifecycle/permissions | PVC binding, access modes, Pod replacement |
| Actuator readiness UP nhưng upload lỗi | Startup probe chỉ kiểm lúc khởi động hoặc không có disk health | Test multipart và runtime disk monitoring |
| Container start với root nhưng SecurityPolicy từ chối | Image USER/root mismatch | runAsNonRoot, image metadata, admission |
| chmod 777 vẫn không ghi được | Root mount read-only hoặc SELinux/ACL | Kiểm mount ro trước permission mode |
| Log file không tạo được | FileAppender trỏ vào image path | Console logging hoặc writable log volume |
| Native library extract thất bại | Temp noexec hoặc không đủ quyền | Native tool requirements, explicit path |
| Quá nhiều file tạm sau crash | Cleanup chỉ trong finally, Pod còn sống | TTL reaper, cleanup startup, quotas |

### 15.1. Thứ tự debug thực tế

1. Tìm **đường dẫn chính xác** được process cố ghi; tránh dựa hoàn toàn vào tên exception chung.
2. Xác định path nằm trong **rootfs** hay **mounted volume**.
3. Đọc process UID/GID và file owner/group/mode; xem ACL/SELinux nếu cần.
4. Kiểm mount options ro/rw, size limit và dung lượng còn trống.
5. Kiểm **java.io.tmpdir** đã set lúc launch, không phải lúc Spring bean khởi tạo.
6. Kiểm **spring.servlet.multipart.location** và thời điểm directory được tạo.
7. Kiểm Tomcat base/temp, access log path và thư viện bên thứ ba.
8. Thử một lệnh create/write/delete bằng cùng UID trong đúng container, không dùng root debug shell để chứng minh quyền non-root.
9. Ghi regression test ở Docker/Kubernetes thay vì chỉ sửa manifest theo cảm giác.

**Không đặt chmod -R 777, privileged=true hoặc runAsUser=0** làm “quick fix” mặc định. Chúng che nguyên nhân và làm hỏng hardening.

## 16. Security considerations cho vùng tệp tạm

Temporary files cũng có thể chứa dữ liệu nhạy cảm. Cần:
- **Tên ngẫu nhiên** từ Files.createTempFile hoặc cơ chế có exclusive create; tránh path từ tên file do client cung cấp.
- **Thư mục riêng** có owner/group phù hợp, không writable bởi mọi người nếu không cần.
- **Không log path kèm token hoặc nội dung file**.
- **Quotas** cho mỗi request/user và toàn Pod; upload limit để tránh disk exhaustion DoS.
- **Cleanup** sau request và TTL cleanup cho orphan sau crash/restart.
- **Không follow symlink** từ input không đáng tin; khi mở file có security implications, dùng NIO APIs/flags đúng threat model.
- **Không execute** uploaded files; mount **noexec** cho scratch nếu dependency cho phép.
- **Không giữ credentials** dạng plaintext trong temp nếu có thể tránh; lưu secret trong Secret manager/volumes được bảo vệ.
- **Không mount cùng scratch giữa tenants** nếu app không đảm bảo isolation.
- **Không map hostPath rộng** chỉ để có chỗ ghi.

**Read-only root filesystem là defense-in-depth**, không phải thay thế patch vulnerabilities, kiểm file contents, authorization, network controls hay process capabilities.

### 16.1. Symlink và path traversal từ multipart original filename

Một client có thể gửi filename giống **../../etc/passwd** hoặc một absolute path. Controller của lab **không dùng originalFilename để tạo Path**, mà chỉ đọc InputStream; đây là lựa chọn an toàn hơn cho demo.

Nếu app cần giữ tên hiển thị, dùng nó như **metadata đã sanitize**, không dùng làm raw filesystem path. Chỉ chấp nhận đường dẫn dưới một dedicated directory, kiểm canonical path và chống symlink race theo môi trường; hoặc lưu trực tiếp vào object storage bằng generated key.

### 16.2. Khi container restart

Nếu container crash nhưng Pod còn tồn tại, emptyDir có thể vẫn chứa temporary files do request trước để lại. Không assume /scratch luôn rỗng ở mỗi process start. Cleanup theo TTL/known prefixes, giới hạn quyền và không xóa các files của sidecar khác. Khi Pod bị loại khỏi node, emptyDir dữ liệu mất, nên không được phụ thuộc vào nó cho business persistence.

## 17. Cân bằng giữa bảo mật, hiệu năng và dung lượng

Một scratch nhỏ có lợi về bảo mật và giảm nguy cơ disk exhaustion, nhưng quá nhỏ có thể làm một luồng upload hợp lệ thất bại. Một scratch lớn tăng headroom nhưng dễ che leak và dùng tài nguyên node.

Các yếu tố để tính:
- **max multipart file size** và tổng request size.
- **Số uploads đồng thời**, thời gian mỗi file nằm trên disk.
- **Tomcat/framework overhead**, third-party conversion temp size.
- **Replication**: mỗi Pod có scratch riêng và giới hạn riêng.
- **Node ephemeral storage** và eviction thresholds.
- **JVM heap/direct memory** nếu medium=Memory.
- **Cleanup duration** khi request bị client disconnect.
- **Upload cancellation, backpressure và HTTP body size limits** tại Ingress.

Ví dụ với **10 uploads đồng thời × 1MiB** chưa tính multipart overhead, Tomcat scratch và các file trung gian khác, tổng sử dụng có thể vượt 10MiB. Đặt emptyDir sizeLimit=64Mi không đồng nghĩa có thể nhận vô hạn uploads nếu có thêm conversion workloads.

### 17.1. Readiness và disk health

Startup write probe phát hiện volume bị khóa từ đầu, nhưng sau nhiều giờ volume có thể đầy. Production có thể:
- Theo dõi tỷ lệ dùng ephemeral storage và dung lượng còn trống.
- Có custom HealthIndicator/Readiness logic khi storage thiết yếu đã mất.
- Áp load shedding ở upload endpoints khi còn ít capacity.
- Dọn orphan files/rotate logs.
- Không coi liveness failure là giải pháp cho một shared node disk pressure: restart hàng loạt có thể làm tình hình xấu hơn.

Readiness phản ánh khả năng nhận traffic; liveness phản ánh process có cần restart. Cần thiết kế dựa trên failure domain, tránh để một external shared storage bị lỗi làm mọi replicas cùng bị restart.

## 18. So sánh Docker --read-only và Kubernetes readOnlyRootFilesystem

| Khía cạnh | Docker local | Kubernetes |
| --- | --- | --- |
| Root filesystem RO | docker run --read-only | container.securityContext.readOnlyRootFilesystem=true |
| UID/GID runtime | Dockerfile USER hoặc docker run --user | runAsUser/runAsGroup/runAsNonRoot |
| Writable temp | --tmpfs /scratch hoặc named volume | emptyDir/PVC volumeMount |
| Group permissions volume | --tmpfs uid/gid/mode, bind mount owner | fsGroup, storage/CSI ownership rules |
| Storage limit | tmpfs size option / Docker volumes theo driver | emptyDir.sizeLimit và resource ephemeral-storage limit |
| Process hardening | cap-drop, security-opt, no-new-privileges | allowPrivilegeEscalation=false, capabilities.drop, seccompProfile |
| Signal/shutdown | docker stop | kubelet termination/SIGTERM |
| Pod-level readiness | Docker healthcheck riêng nếu cấu hình | Kubernetes readiness/liveness probes |
| Dữ liệu sau container restart | tmpfs/ephemeral theo container lifecycle | emptyDir còn trong cùng Pod, mất khi Pod bị remove |

Cần kiểm **cùng một artifact JAR/image** dưới security settings gần production nhất. Test Java ngoài container không chứng minh non-root + read-only mount. Test Docker không tự chứng minh fsGroup/CSI/Kubernetes security policy. Các tầng phải được kiểm riêng và kết hợp.

## 19. Bài tập tự đánh giá

**1.** Container có readOnlyRootFilesystem=true có thể ghi vào emptyDir mount /scratch không?  
**Đáp án:** Có thể, nếu volume mount là writable và UID/GID/permissions/storage policy cho phép.

**2.** runAsNonRoot=true có tự làm root filesystem read-only không?  
**Đáp án:** Không. Đây là kiểm soát process UID; rootfs read-only cần setting khác.

**3.** Vì sao app không ghi business files vẫn có thể lỗi khi /tmp read-only?  
**Đáp án:** Tomcat base/temp và Servlet multipart/file-upload libraries có thể cần scratch disk.

**4.** java.io.tmpdir nên được đặt lúc nào?  
**Đáp án:** Từ khi JVM khởi động qua -Djava.io.tmpdir hoặc JAVA_TOOL_OPTIONS, không thay property giữa request rồi mong mọi library áp dụng.

**5.** Spring Boot 3.3 spring.servlet.multipart.file-size-threshold mặc định là gì?  
**Đáp án:** 0B, có thể spool uploaded content ra disk theo Servlet implementation.

**6.** Thư mục Spring multipart intermediate được cấu hình bằng property nào?  
**Đáp án:** spring.servlet.multipart.location.

**7.** Nếu chỉ đặt app.temp-dir=/scratch nhưng bỏ multipart.location, có bảo đảm upload dùng /scratch không?  
**Đáp án:** Không. app.temp-dir là custom property của lab, còn Multipart resolver có config riêng; java.io.tmpdir có thể ảnh hưởng default nhưng nên explicit.

**8.** Vì sao lệnh Files.isWritable không đủ chứng minh temp mount hoạt động?  
**Đáp án:** Không kiểm hết các điều kiện quota/space/mount/ACL tại lúc ghi; tạo/ghi/xóa file thực đáng tin hơn.

**9.** emptyDir còn sau một container crash/restart trong cùng Pod không?  
**Đáp án:** Có, dữ liệu emptyDir thường còn trong đời Pod; khi Pod bị remove khỏi node thì mất.

**10.** emptyDir medium: Memory có tính vào memory usage không?  
**Đáp án:** Có, dữ liệu tmpfs cạnh tranh với memory limit và có thể làm OOM.

**11.** fsGroup=10001 có bảo đảm mọi PVC trên mọi CSI driver writable không?  
**Đáp án:** Không; phụ thuộc storage driver, ownership behavior, mount flags/ACL/SELinux.

**12.** Tại sao nên dùng UID 10001 thay vì root trong Dockerfile?  
**Đáp án:** Giảm đặc quyền mặc định khi process bị khai thác; vẫn cần volume permission và các lớp security khác.

**13.** Chạy root có vượt được read-only mount không?  
**Đáp án:** Không, mount read-only không trở thành writable chỉ vì UID 0.

**14.** Có nên chmod 777 toàn /app để giải quyết lỗi upload?  
**Đáp án:** Không; xác định scratch path và mount writable tối thiểu.

**15.** Tại sao không dùng MultipartFile.getOriginalFilename làm Path mà không kiểm?  
**Đáp án:** Filename do client kiểm soát, có thể dẫn tới traversal hoặc file overwrite.

**16.** Một upload thành công trên Docker mà fail trên Kubernetes có thể do đâu?  
**Đáp án:** fsGroup/runAsUser mismatch, PVC/emptyDir mount permissions, SELinux, image policy hoặc temp paths khác.

**17.** Nếu volume /scratch bị đầy sau khi app đã ready thì sao?  
**Đáp án:** Upload/temp write có thể fail; startup probe không tự kiểm liên tục, cần metrics/quota/runtime health.

**18.** Khi nào nên dùng PVC hoặc object storage thay emptyDir?  
**Đáp án:** Khi file là business data cần tồn tại sau Pod deletion/redeploy hoặc cần chia sẻ theo durability contract.

**19.** noexec trên tmpfs có luôn tương thích với mọi Java app không?  
**Đáp án:** Không. Một số native libraries cần extract/execute vào temp; kiểm dependency thực trước khi giữ hoặc đổi noexec.

**20.** Vì sao không được coi JUnit test trên host là bằng chứng readOnlyRootFilesystem hoạt động?  
**Đáp án:** Host test không mount container root read-only và không áp Linux UID/fsGroup như runtime thật; cần Docker/Kubernetes test.

## 20. Checklist triển khai production

- [ ] Image chứa JAR/config đọc được nhưng không cần ghi vào /app.
- [ ] Runtime process dùng non-root UID/GID xác định hoặc chính sách random UID được hỗ trợ.
- [ ] Bật **readOnlyRootFilesystem** ở Kubernetes và tương đương Docker trong test.
- [ ] Drop Linux capabilities không cần; tắt privilege escalation; dùng seccomp policy phù hợp.
- [ ] Không dùng privileged/hostPath rộng/chmod 777 để chữa lỗi permission.
- [ ] Có writable scratch mount riêng và quota.
- [ ] Đặt **java.io.tmpdir từ lúc JVM start**, không giữa lifecycle.
- [ ] Đặt **spring.servlet.multipart.location** và giới hạn request/file sizes.
- [ ] Kiểm Tomcat base/temp/workdir, access logs, native libs, heap dumps và caches.
- [ ] Startup có write/delete probe cho temp directory thiết yếu.
- [ ] Nếu temp storage lỗi runtime, có metrics, graceful errors, readiness/admission policy phù hợp.
- [ ] Phân biệt **emptyDir ephemeral** với **PVC/object storage durable**.
- [ ] Với emptyDir Memory, có memory accounting/quota và test OOM behavior.
- [ ] Với disk emptyDir, có ephemeral-storage request/limit và giám sát eviction/ENOSPC.
- [ ] Kiểm runAsUser/runAsGroup/fsGroup và volume permissions bằng process UID thật.
- [ ] Không echo filename/path/temp content nhạy cảm trong public APIs/logs.
- [ ] Dùng Files.createTempFile và cleanup trong finally; có TTL cleanup khi crash.
- [ ] Có test multipart qua HTTP container thật, không chỉ gọi Controller trực tiếp.
- [ ] Có Docker integration test **--read-only + --tmpfs**.
- [ ] Có staging Kubernetes test **readOnlyRootFilesystem + emptyDir + fsGroup**.
- [ ] Test failure khi mount missing/RO/no space, cùng readiness và logs.
- [ ] Có chính sách bảo vệ upload: authentication, rate limit, validation, content scanning khi cần.
- [ ] Không public debug/probe endpoints của lab hoặc Actuator nhạy cảm.

## 21. Kết luận

**Readonly root filesystem, non-root process và writable temporary volume không phải ba lựa chọn loại trừ nhau**. Chúng là ba lớp trách nhiệm:
- **Readonly rootfs** bảo vệ nội dung image và giới hạn chỗ tiến trình có thể thay đổi.
- **Non-root UID/GID** hạn chế đặc quyền của JVM.
- **Writable scratch mount có quota** cung cấp tệp trung gian thực sự cần thiết cho Tomcat, multipart, JDK và các thư viện.

Một thiết kế tốt đặt **java.io.tmpdir**, **spring.servlet.multipart.location**, mount path, fsGroup và quota cùng hướng, rồi **kiểm bằng thao tác ghi/xóa thật dưới UID triển khai**. Các dữ liệu nghiệp vụ cần bền vững phải đi vào PVC/object storage/database; emptyDir chỉ là scratch. Đừng biến lỗi Permission denied thành lý do bỏ read-only filesystem, chạy root hoặc mở quyền toàn hệ thống.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Common Application Properties, spring.servlet.multipart.* và server.tomcat.basedir: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Spring MVC Multipart support và uploads: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Apache Tomcat 10.1 — Context workDir và jakarta.servlet.context.tempdir: https://tomcat.apache.org/tomcat-10.1-doc/config/context.html
- Oracle Java 17 — Files.createTempFile: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Kubernetes — Configure a Security Context for a Pod or Container: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- Kubernetes — Volumes, emptyDir lifecycle và medium: Memory: https://kubernetes.io/docs/concepts/storage/volumes/
- Kubernetes — Resource Management, ephemeral storage và tmpfs accounting: https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
- Kubernetes — Configure a Pod to Use a Volume: https://kubernetes.io/docs/tasks/configure-pod-container/configure-volume-storage/
- Docker — Run containers, USER và --read-only rootfs: https://docs.docker.com/reference/cli/docker/container/run/
- Docker — tmpfs mounts, uid/gid/mode/size: https://docs.docker.com/engine/storage/tmpfs/
- Docker — Dockerfile USER, COPY --chown và ENTRYPOINT: https://docs.docker.com/reference/dockerfile/
