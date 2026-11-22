# Quyền đọc input resource trong Spring Batch

## 1. Vì sao quyền đọc input resource là vấn đề bảo mật?

Một batch job thường nhận dữ liệu từ file CSV, thư mục mount trong container, classpath, object storage, API hoặc cơ sở dữ liệu. Trước khi `ItemReader` đọc được item đầu tiên, **tiến trình đang chạy job phải có quyền truy cập đúng nguồn đầu vào**.

Ví dụ `importOrdersJob` nhận tham số:

```text
inputFile=2026-11-16/orders.csv
```

Theo thiết kế, file được phép đọc nằm trong:

```text
/srv/order-batch/inbound/2026-11-16/orders.csv
```

Nếu tài khoản chạy Spring Batch không có quyền trên file hoặc các thư mục cha, reader sẽ thất bại khi mở file. Ngược lại, nếu ứng dụng nhận đường dẫn tùy ý rồi đọc bằng tài khoản có quyền rộng, người gọi có thể thử một đường dẫn như:

```text
inputFile=../../private/credentials.txt
```

Đây không chỉ là lỗi cấu hình; nó có thể trở thành lỗ hổng **path traversal**, khiến một tính năng nhập dữ liệu được dùng để đọc tài nguyên ngoài phạm vi cho phép.

Trong chương **Spring Batch Core Processing → Security**, quyền đọc input resource cần được hiểu ở ba lớp:

1. **Danh tính thực thi:** tiến trình chạy dưới OS user, service account, workload identity hoặc cloud role nào?
2. **Quyền trên tài nguyên:** danh tính đó được phép đọc những file, directory, bucket, object key hay API nào?
3. **Ranh giới của input:** từ các nguồn có thể đọc được, ứng dụng cho phép người gọi chọn **nguồn nào**?

Nguyên tắc bao trùm là **least privilege**: job chỉ cần quyền đọc các input đã được phê duyệt, không cần quyền đọc toàn bộ máy chủ, bucket hoặc đường dẫn của các job khác.

## 2. Resource trong Spring khác quyền truy cập

Spring Framework cung cấp `org.springframework.core.io.Resource` làm abstraction cho nguồn dữ liệu. Reader như `FlatFileItemReader` nhận một `Resource`, nhưng đối tượng này chỉ mô tả **cách truy cập nguồn**; nó không tự cấp quyền đọc.

| Loại resource | Ví dụ | Nguồn quyền truy cập | Trường hợp phù hợp |
| --- | --- | --- | --- |
| `ClassPathResource` | `classpath:fixtures/orders.csv` | Artifact/JAR, classloader và quyền chứa file ứng dụng | Fixture/test, dữ liệu tĩnh đóng gói cùng ứng dụng |
| `FileSystemResource` | `/srv/batch/inbound/orders.csv` | OS user, group, ACL, mounted volume | File nhận từ upstream, SFTP, thư mục chia sẻ |
| `PathResource` | Một `java.nio.file.Path` | File system provider và các quyền OS tương ứng | Code dùng Java NIO |
| `UrlResource` | `https://supplier.example/data.csv` | Network, TLS, authentication và quyền phía server | Nguồn URL đã được phê duyệt |
| Resource/object reader của S3, GCS, Azure Blob | Object key theo bucket/container | IAM, workload identity, object policy, encryption key | Dữ liệu trên cloud object storage |
| `InputStreamResource` | Stream đã được mở | Nguồn đã được xác thực và mở bằng logic khác | Stream đọc một lần; cần cân nhắc restart |

**Lưu ý về classpath:** một file mới được upload vào thư mục `/data/inbound` không tự xuất hiện trong classpath. Tài nguyên trong executable JAR có thể không phải file vật lý có thể lấy qua `getFile()`; dùng `getInputStream()` khi chỉ cần đọc nội dung.

**Lưu ý về S3:** chuỗi `s3://bucket/key` không mặc định được Spring Framework core diễn giải thành một Resource có khả năng đọc. Dự án cần tích hợp hoặc reader/client hỗ trợ object storage tương ứng.

### 2.1. Đối tượng Resource chưa chứng minh đọc được

```java
import java.io.InputStream;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Resource resource =
        new FileSystemResource("/srv/batch/inbound/orders.csv");

boolean exists = resource.exists();
boolean readable = resource.isReadable();

try (InputStream in = resource.getInputStream()) {
    // Đọc nội dung ở đây.
}
```

`exists()` và `isReadable()` hữu ích để báo lỗi sớm, nhưng không phải bảo đảm vĩnh viễn. File, ACL, mount, secret hoặc trạng thái network có thể đổi trước khi `getInputStream()` thực sự mở. Quyền truy cập **được thực thi ở thời điểm mở nguồn** bởi OS, storage service hoặc server tương ứng.

Vì vậy, kiểm tra preflight và thao tác đọc cuối cùng đều phải xử lý exception đúng cách. Chỉ vì preflight đã thành công không có nghĩa các lần đọc sau sẽ luôn thành công.

## 3. Quyền đọc file local trên Linux

Với đường dẫn:

```text
/srv/order-batch/inbound/2026-11-16/orders.csv
```

OS phải cho phép tiến trình **đi qua các thư mục cha** và **đọc file đích**.

```text
Process UID + supplementary GIDs
         |
         v
    /srv                          traverse
      /order-batch                traverse
        /inbound                  traverse
          /2026-11-16             traverse
            /orders.csv           read
         |
         v
    ACL / filesystem / mount policy
         |
         v
    InputStream mở thành công?
```

Một file có mode `-rw-r-----` (640) có thể đọc được bởi owner và nhóm owner. Một thư mục có mode `drwxr-x---` (750) cho owner toàn quyền, nhóm owner quyền đọc/dò tìm và không cấp quyền cho người khác. Nhưng nếu user batch **không nằm trong nhóm ấy**, file sẽ bị từ chối.

**Quyền `x` trên directory rất quan trọng:** nó cho phép đi qua hoặc tìm entry khi đã biết tên. Quyền `r` trên file **không đủ** nếu một directory cha thiếu quyền traverse.

Ví dụ bố trí phân quyền:

```text
owner = batch-ingest   (producer)
group = batch-read
batch-service là thành viên của batch-read

inbound directory: 750
orders.csv:         640
```

Với owner/group phù hợp, service có thể đọc mà không cần ghi. Các lệnh ví dụ:

```bash
chmod 750 /srv/order-batch/inbound
chmod 640 /srv/order-batch/inbound/orders.csv
```

Chúng chỉ minh họa mode POSIX, không thay thế việc cấu hình owner, group, ACL hoặc mount. Không áp dụng máy móc cho file production khi chưa biết quyền hiện có.

### Vì sao không dùng chmod 777 hoặc chạy bằng root?

`chmod 777` cho phép rộng cả quyền ghi và thực thi phù hợp loại file/directory; nó tạo bề mặt thay đổi dữ liệu không cần thiết đối với một reader chỉ cần đọc. Chạy toàn bộ Spring Batch bằng root để vượt `AccessDeniedException` cũng cấp thêm rất nhiều quyền ngoài yêu cầu nghiệp vụ.

Thay vào đó:

- Xác định **danh tính thực thi thật** của job.
- Cấp quyền đọc vào đúng thư mục hoặc nhóm cần thiết.
- Giữ producer có quyền ghi và consumer chỉ có quyền đọc nếu quy trình cho phép.
- Kiểm tra quyền trên toàn bộ chuỗi thư mục cha.
- Tách vùng dữ liệu của các tenant hoặc job có ranh giới bảo mật khác nhau.

Trên Windows, quyền hữu hiệu dựa vào NTFS ACL và danh tính service/process. Các mode `640`/`750` không phải phép đo trực tiếp quyền NTFS.

## 4. Danh tính thực thi khác nhau theo môi trường

| Môi trường | Danh tính cần kiểm tra | Điểm thường gây lỗi |
| --- | --- | --- |
| IDE/local | User đang chạy Java | Đường dẫn tương đối, working directory, permission local |
| Linux service | `User=`/`Group=` của systemd hoặc service account | ACL, directory traverse, sandbox policy |
| Docker | UID/GID process trong container | Bind mount owner/group và file mode |
| Kubernetes Job/CronJob | `runAsUser`, `runAsGroup`, `fsGroup` | PVC/CSI, mounted volume, policy của Pod |
| VM/managed workload | User process và role của máy | File system hoặc cloud IAM |
| S3/GCS/Azure Blob | Workload identity / cloud role / service principal | Quyền object và decrypt, bucket/container policy |

Một tài khoản developer có thể đọc file trên node, trong khi user 10001 trong container không có quyền. Kết luận dựa trên việc “tôi mở file được bằng terminal của admin” có thể sai với tiến trình chạy job.

### Các lệnh quan sát trên Linux

Khi có quyền truy cập vào **đúng môi trường thực thi**:

```bash
id
ls -ld /srv/order-batch/inbound
ls -l /srv/order-batch/inbound/2026-11-16/orders.csv
namei -l /srv/order-batch/inbound/2026-11-16/orders.csv
```

`id` cho biết UID/GID hiện tại; `ls` hiển thị quyền file/directory; `namei -l` (nếu có) hiển thị quyền từng phần đường dẫn. Trên hệ thống có SELinux, AppArmor, ACL bổ sung hoặc network file system, các lệnh này có thể chưa lý giải hết quyền hữu hiệu.

## 5. Không nhận inputPath tùy ý từ người gọi

Đây là cách cấu hình dễ gây lỗi bảo mật:

```java
// Rủi ro nếu inputPath đến từ một caller không tin cậy.
Resource input = new FileSystemResource(inputPath);
```

Người gọi có thể truyền:

```text
../../private/config.yml
/etc/passwd
../other-tenant/orders.csv
```

Ngay cả khi OS đã giới hạn quyền, ứng dụng vẫn nên bảo vệ **ranh giới nghiệp vụ** của mình. Không nên dựa duy nhất vào việc service account “tình cờ không có quyền” trên file ngoài root.

Một thiết kế phù hợp hơn:

```text
Job parameter:
  inputFile = 2026-11-16/orders.csv

Server-side configuration:
  app.batch.input-root = /srv/order-batch/inbound

Resolved:
  /srv/order-batch/inbound/2026-11-16/orders.csv
```

Đối với môi trường nhiều khách hàng, ứng dụng nên ánh xạ **tenant đã được xác thực** sang vùng nguồn đã được cấp phép. Chỉ có `tenantId` trong job parameters, do caller tự truyền, chưa đủ để cho phép đọc dữ liệu tenant đó.

### 5.1. Ví dụ ApprovedInputResolver với Java NIO

Lớp dưới đây nhận một tên file tương đối, giới hạn nó bên trong một input root được cấu hình phía server, sau đó kiểm tra đường dẫn thực và quyền đọc:

```java
package com.example.batch.security;

import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public final class ApprovedInputResolver {

    private final Path root;

    public ApprovedInputResolver(Path configuredRoot) throws IOException {
        Objects.requireNonNull(configuredRoot, "configuredRoot");
        this.root = configuredRoot.toRealPath();

        if (!Files.isDirectory(root)) {
            throw new IllegalArgumentException(
                    "Input root must be a directory");
        }
    }

    public Path resolveReadableFile(String inputFile) throws IOException {
        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalArgumentException("inputFile is required");
        }

        Path supplied = Path.of(inputFile);
        if (supplied.isAbsolute()) {
            throw new SecurityException("Absolute paths are disabled");
        }

        Path candidate = root.resolve(supplied).normalize();
        if (!candidate.startsWith(root)) {
            throw new SecurityException(
                    "Input path escapes approved root");
        }

        // Giải symbolic link; sẽ lỗi nếu file không tồn tại.
        Path realFile = candidate.toRealPath();
        if (!realFile.startsWith(root)) {
            throw new SecurityException(
                    "Input symlink escapes approved root");
        }

        if (!Files.isRegularFile(realFile)) {
            throw new IllegalArgumentException(
                    "Input is not a regular file");
        }

        if (!Files.isReadable(realFile)) {
            throw new AccessDeniedException(realFile.toString());
        }
        return realFile;
    }
}
```

| `inputFile` | Kỳ vọng với root `/srv/order-batch/inbound` |
| --- | --- |
| `2026-11-16/orders.csv` | Chấp nhận nếu file thực tồn tại, nằm trong root và đọc được |
| `./2026-11-16/orders.csv` | Chấp nhận sau chuẩn hóa khi contract cho phép |
| `../private/secret.txt` | Từ chối vì vượt khỏi root |
| `/etc/passwd` | Từ chối vì là đường dẫn tuyệt đối |
| Symlink `inbound/link.csv` trỏ ra ngoài | Từ chối sau `toRealPath()` |
| `missing.csv` | Ném exception do file không tồn tại |
| `subdir` là một thư mục | Từ chối vì không phải file thường |

**Giới hạn:** phép kiểm tra `toRealPath()` và `Files.isReadable()` đánh giá đường dẫn tại **thời điểm kiểm tra**. Nếu attacker có quyền thay symlink, thay file hoặc thay mount trước khi reader mở, vẫn tồn tại rủi ro *time of check to time of use* (TOCTOU). Với nguồn không tin cậy, dùng staging directory bị giới hạn quyền ghi, snapshot bất biến, hoặc cơ chế mở an toàn gắn với directory handle (ví dụ `SecureDirectoryStream` khi file-system provider hỗ trợ).

`Files.isReadable` cũng không phải phép chứng minh quyền đọc tuyệt đối: lần mở thực tế có thể bị từ chối vì ACL, mount, network hoặc thay đổi file. Ở tầng ứng dụng, catch lỗi đọc và phân loại đúng khi mở `InputStream`.

### 5.2. Kiểm soát bằng sourceId

Khi batch được gọi qua API, an toàn và dễ quản lý hơn là nhận `sourceId`:

```text
sourceId=orders:2026-11-16:v3
```

Ứng dụng tra source ID trong catalog thuộc tenant được xác thực:

```text
sourceId
  -> tenant owner
  -> approved storage location
  -> object/file version
  -> checksum, schema version
  -> READY/VALIDATED status
```

Chỉ sau khi kiểm tra quyền của caller và trạng thái nguồn, job mới lấy location nội bộ. Cách này giảm nhu cầu cho phép caller tự chọn filesystem path hoặc URL.

## 6. Gắn đường dẫn đã kiểm tra vào FlatFileItemReader

Các ví dụ Java dưới đây áp dụng cho **Spring Batch 5.x, Spring Boot 3.x và Java 17+**. Một số package/builder API đã thay đổi ở Spring Batch 6.x; cần sử dụng đúng tài liệu phiên bản của dự án.

### 6.1. Cấu hình root ở phía server

```yaml
app:
  batch:
    input-root: /srv/order-batch/inbound
```

Đăng ký bean:

```java
import java.io.IOException;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InputSecurityConfiguration {

    @Bean
    ApprovedInputResolver approvedInputResolver(
            @Value("${app.batch.input-root}") String configuredRoot)
            throws IOException {
        return new ApprovedInputResolver(Path.of(configuredRoot));
    }
}
```

`input-root` do server quản lý. Không cho caller thay đổi thông số này bằng một request launch job.

### 6.2. Reader @StepScope dùng tham số tương đối

```java
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.file.Path;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

public record OrderRow(String orderId, BigDecimal amount) {}

@Bean
@StepScope
FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        ApprovedInputResolver resolver) throws IOException {

    Path approvedFile = resolver.resolveReadableFile(inputFile);

    return new FlatFileItemReaderBuilder<OrderRow>()
            .name("orderReader")
            .resource(new FileSystemResource(approvedFile))
            .strict(true)
            .linesToSkip(1)
            .delimited()
            .names("order_id", "amount")
            .fieldSetMapper(fields -> new OrderRow(
                    fields.readString("order_id"),
                    fields.readBigDecimal("amount")
            ))
            .build();
}
```

`@StepScope` cho phép lấy `inputFile` khi **step thực thi**. Reader singleton không nên giữ một tên file động từ lần chạy trước.

`strict(true)` cho `FlatFileItemReader` biết thiếu resource là lỗi, thay vì âm thầm coi như nguồn rỗng. Khi đang cần nhập dữ liệu thực, không dùng `strict(false)` chỉ để che lỗi quyền đọc hoặc file thiếu. Tên reader ổn định giúp quản lý state trong `ExecutionContext` khi restart.

Ví dụ kỳ vọng CSV có header `order_id,amount`; dự án thật còn phải kiểm tra schema/encoding và dữ liệu record theo hợp đồng nguồn. `JobParameters` chưa đủ để bảo vệ root nếu một code path khác trong ứng dụng tạo `Resource` trực tiếp từ chuỗi chưa được kiểm tra.

### 6.3. Step đọc và xử lý

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, OrderRow> processor,
        ItemWriter<OrderRow> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderRow, OrderRow>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Các kiểu `Step`, `JobRepository`, `StepBuilder`, `ItemProcessor`, `ItemWriter` và transaction manager lấy theo Spring Batch/Spring Framework version 5.x tương ứng. Đoạn code giả định processor/writer đã được định nghĩa và có database test khi cần chạy.

## 7. Preflight step: xác minh nguồn trước khi ghi output

Với job nhiều bước, quyền đọc input nên được kiểm tra **trước khi các bước nghiệp vụ tạo side effect**. Một preflight step có thể xác minh:

- Source ID thuộc phạm vi đã cấp quyền.
- File/object đã READY, tồn tại và có quyền đọc.
- Resource mở được ngay tại thời điểm preflight.
- Schema/header và kích thước phù hợp.
- Hash hoặc object version khớp snapshot được công bố.

### 7.1. Kiểm tra stream mở được

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public static void verifyOpenable(Path file) throws IOException {
    try (InputStream ignored = Files.newInputStream(file)) {
        // Kiểm tra thao tác mở đọc; không ghi dữ liệu.
    }
}
```

Thao tác này mạnh hơn phép kiểm tra `Files.isReadable` vì OS thực sự thực hiện mở. Tuy nhiên, nó **không đóng băng trạng thái file** và không chứng minh dữ liệu CSV hợp lệ.

### 7.2. Ví dụ Tasklet preflight

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
Tasklet inputPreflightTasklet(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        ApprovedInputResolver resolver) {

    return (contribution, context) -> {
        Path input = resolver.resolveReadableFile(inputFile);

        try (InputStream ignored = Files.newInputStream(input)) {
            // Optional: kiểm tra header, checksum và manifest.
        }
        return RepeatStatus.FINISHED;
    };
}
```

Định nghĩa step và flow:

```java
@Bean
Step inputPreflightStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet inputPreflightTasklet) {

    return new StepBuilder("inputPreflightStep", jobRepository)
            .tasklet(inputPreflightTasklet, transactionManager)
            .build();
}

@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step inputPreflightStep,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(inputPreflightStep)
            .next(importOrdersStep)
            .build();
}
```

Khi Tasklet ném exception lúc resolve/mở file, `inputPreflightStep` thất bại và flow tuần tự bình thường không đi tiếp vào importer. `StepExecution` của preflight giúp xác định đây là lỗi đọc nguồn, khác lỗi validation item trong `ItemProcessor`.

**Không coi preflight là bảo đảm quyền đọc suốt vòng đời job:** nếu nguồn có thể bị thay giữa preflight và reader, hãy xử lý vấn đề bằng snapshot/version immutable và chính sách quyền ghi của staging.

## 8. Docker và Kubernetes: quyền của volume không giống quyền của host

Job chạy trong container có thể thấy đường dẫn `/app/input/orders.csv`, nhưng file thực được mount từ volume hoặc network storage. Quyền đọc phụ thuộc UID/GID trong container, mode/ACL của dữ liệu, mount options và security policy của nền tảng.

### 8.1. Docker không dùng root

Ví dụ Dockerfile:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar /app/app.jar
USER 10001:10001
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Nếu file bind mount chỉ cho UID 1000 đọc, UID 10001 không tự nhiên được cấp quyền. Hãy điều chỉnh group/ACL của volume hoặc dùng source mount được thiết kế để consumer đọc, thay vì đổi toàn bộ JVM sang root.

### 8.2. Kubernetes Job đọc PVC

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: orders-import
spec:
  template:
    spec:
      restartPolicy: Never
      securityContext:
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 2000
      containers:
        - name: batch
          image: example/orders-batch:1.0
          volumeMounts:
            - name: inbound
              mountPath: /srv/order-batch/inbound
              readOnly: true
          env:
            - name: APP_BATCH_INPUT_ROOT
              value: /srv/order-batch/inbound
      volumes:
        - name: inbound
          persistentVolumeClaim:
            claimName: orders-inbound-pvc
```

Đây là ví dụ, giả định PVC và image đã tồn tại.

- `runAsUser`/`runAsGroup` đặt danh tính process.
- `fsGroup` có thể giúp truy cập volume qua nhóm, nhưng mức độ hỗ trợ và việc đổi ownership phụ thuộc loại volume/CSI driver và chính sách cluster.
- `readOnly: true` ngăn ghi qua mount này, nhưng **không tự cấp quyền đọc** nếu ACL/mode vẫn không cho phép.
- Kubernetes ServiceAccount cho quyền Kubernetes API hoặc workload identity theo cấu hình; nó không tự đổi ACL của mọi file PVC.

### Các nguyên nhân thường gặp khi chuyển từ local lên pod

1. File chưa được mount tại đường dẫn ứng dụng dùng.
2. Pod chạy UID/GID khác user phát triển.
3. File mode `0600`, owner là user khác.
4. Directory cha thiếu quyền traverse.
5. PVC/CSI hoặc network filesystem giữ ACL/ownership từ nơi khác.
6. `working directory` thay đổi làm đường dẫn tương đối trỏ sai.
7. Pod mới chạy trên node khác nhưng nguồn nằm trên local filesystem của node cũ.

Nên kiểm tra bên trong đúng pod/container và dưới đúng danh tính thực thi batch.

## 9. Object storage: IAM và KMS thay thế ACL của file local

Với S3, GCS hoặc Azure Blob, quyền đọc phụ thuộc policy của cloud service. Chẳng hạn với S3, job cần `GetObject` cho đúng prefix; nếu object mã hóa bằng SSE-KMS còn có thể cần `kms:Decrypt` và key policy tương ứng.

Ví dụ policy IAM **chỉ cho phép đọc object** dưới prefix `orders/inbound/`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::company-batch-input/orders/inbound/*"
    }
  ]
}
```

Đây là policy rút gọn để minh họa. Nếu ứng dụng cần liệt kê prefix thì có thể cần `s3:ListBucket` trên resource bucket cùng điều kiện prefix phù hợp. Đọc object đã biết key **không đương nhiên cần quyền liệt kê toàn bucket**.

Không lưu access key, secret token hoặc presigned URL trong `JobParameters` hay log. Job parameters thường được lưu ở metadata `JobRepository` để phục vụ restart và tra cứu; các giá trị nhạy cảm có thể bị lộ nếu đặt trực tiếp ở đó.

Nên dùng workload identity, role của VM/pod hoặc cơ chế credential provider của SDK; cấp quyền tối thiểu theo đúng bucket/prefix/key.

### Phân biệt lỗi truy cập object storage

| Lỗi | Nguyên nhân thường gặp | Cách ứng xử |
| --- | --- | --- |
| 403/AccessDenied | IAM, bucket policy, key policy, credential | Xác định role, policy và khả năng decrypt |
| 404/NoSuchKey | Sai key, object chưa được publish, version sai | Kiểm tra manifest/ready marker |
| 503/timeout | Network hoặc backend tạm thời | Retry có backoff và giới hạn |
| Object cùng key bị thay nội dung | Producer ghi version khác | Pin object version/checksum |
| Mở được nhưng parse lỗi | Schema, encoding, format sai | Data validation, không quy về lỗi IAM |

Không retry vô hạn với lỗi 403 do thiếu policy. Với lỗi network tạm thời, nên dùng timeout và backoff giới hạn theo contract của client/storage SDK.

## 10. URL resource và nguy cơ SSRF

Nếu API cho phép caller gửi `inputUrl` rồi ứng dụng tạo `UrlResource`, batch có thể bị lợi dụng để gọi endpoint nội bộ hoặc địa chỉ không thuộc nguồn được phép. Đây là dạng **server-side request forgery (SSRF)**.

Thiết kế nên:

- Nhận `sourceId` và ánh xạ sang endpoint đã được đăng ký.
- Giới hạn giao thức, thường là HTTPS, và danh sách host được phê duyệt.
- Có chính sách với redirect, DNS resolution và địa chỉ nội bộ; chỉ kiểm tra hostname bằng regex là chưa đủ.
- Áp dụng timeout, giới hạn dung lượng phản hồi và xác thực TLS.
- Không đưa credential vào URL query string, không tắt kiểm tra certificate để “chạy cho được”.
- Kết hợp network egress policy ở hạ tầng khi yêu cầu bảo mật cao.

Không mọi URL “https://...” đều là input an toàn. Chính sách authorization cần xác minh **nguồn cụ thể được phép đọc**, không chỉ giao thức.

## 11. Restart và tính bất biến của input resource

Spring Batch có thể lưu tiến độ trong `ExecutionContext`. Khi một step thất bại rồi restart, reader cần đọc **cùng một nguồn** ở trạng thái phù hợp với checkpoint. Một file có cùng tên nhưng nội dung đã thay có thể dẫn đến mất/nhân đôi record.

```text
09:00 JobExecution #101
      source=orders_2026-11-16.csv
      chunk 1..10 đã COMMIT
09:05 quyền file bị thay -> reader lỗi -> FAILED

09:30 quyền đã khôi phục
      JobExecution #102 RESTART cùng JobInstance
      reader tiếp tục từ checkpoint
```

Muốn restart an toàn:

1. Giữ **snapshot nguồn bất biến**: cùng byte stream, thứ tự record, schema và version.
2. Đảm bảo quyền đọc còn hiệu lực lúc restart.
3. Giữ ổn định identifying `JobParameters` và source identity.
4. Cấu hình reader có tên ổn định, hỗ trợ lưu state khi cần.
5. Giữ `JobRepository` và `ExecutionContext`; không xóa metadata chỉ để chạy lại.
6. Thiết kế writer idempotent khi một phần dữ liệu có thể bị phát lại.

Theo mặc định, step đã `COMPLETED` có thể được bỏ qua trong một lần restart. Nếu `inputPreflightStep` đã hoàn tất ở execution trước, nó **không nhất thiết chạy lại**. Có thể chọn:

```java
new StepBuilder("inputPreflightStep", jobRepository)
        .tasklet(inputPreflightTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
```

để yêu cầu preflight chạy lại khi restart, nhưng đây phải là quyết định có chủ đích. Không dùng revalidation để âm thầm đổi sang bản file mới vì checkpoint vẫn gắn với nguồn cũ.

### Tại sao snapshot quan trọng hơn isReadable?

```text
10:00:00 preflight file A -> OK
10:00:02 producer ghi đè đường dẫn bằng file B
10:00:05 FlatFileItemReader.open() đọc file B
```

Dù hai lần mở đều được phép, hệ thống đã kiểm tra A nhưng xử lý B. Giải pháp là publish input bằng **object version, immutable staging key, manifest/hash** và hạn chế quyền ghi sau khi công bố. Một phép kiểm tra quyền đọc đơn thuần không giải quyết được vấn đề này.

## 12. Logging và giám sát lỗi quyền đọc

Một exception “không mở được file” cần được phân loại để biết nhóm nào phải xử lý. Nên ghi log có cấu trúc:

```text
jobName
jobExecutionId
stepName
stepExecutionId
sourceId
businessDate
resourceType: FILESYSTEM / CLASSPATH / OBJECT_STORAGE / HTTPS
stage: RESOLVE / AUTHORIZE / OPEN / READ / PARSE
errorCategory: ACCESS_DENIED / NOT_FOUND / NETWORK / INVALID_SOURCE
environment
```

Ví dụ:

```json
{
  "event": "batch_input_open_failed",
  "jobName": "importOrdersJob",
  "stepName": "inputPreflightStep",
  "sourceId": "orders:2026-11-16:v1",
  "resourceType": "FILESYSTEM",
  "stage": "OPEN",
  "errorCategory": "ACCESS_DENIED",
  "environment": "production"
}
```

Chỉ log đường dẫn thực/exception chi tiết ở hệ thống có quyền truy cập phù hợp. Tránh log raw access token, URL ký tạm, credential hoặc payload nhạy cảm.

Metric tùy chỉnh có thể gồm:

| Metric gợi ý | Mục đích |
| --- | --- |
| `batch_input_open_total{jobName,result,errorCategory}` | Theo dõi lần mở thành công/thất bại |
| `batch_input_access_denied_total{jobName,resourceType}` | Đo số lần bị từ chối quyền đọc |
| `batch_input_validation_duration_seconds{jobName}` | Đo thời gian preflight |
| `batch_missing_source_total{jobName}` | Biết upstream không cung cấp input đúng hạn |
| `batch_last_success_timestamp{jobName}` | Nhận ra job không còn hoàn thành |

Đây là tên metric **đề xuất của ứng dụng**, không phải cam kết metric mặc định Spring Batch. Không dùng file path, object key, `sourceId` hoặc exception message có cardinality cao làm metric label.

## 13. Kiểm thử quyền đọc input resource

Kiểm thử security cần phân biệt **unit test chính sách chọn đường dẫn** với **integration test quyền thực tế của service account**. Một unit test chạy dưới developer/admin có thể mở file mà production user không thể đọc.

### 13.1. Unit test path validation bằng @TempDir

```java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ApprovedInputResolverTest {

    @TempDir
    Path temp;

    @Test
    void acceptsReadableFileWithinRoot() throws Exception {
        Path root = Files.createDirectory(temp.resolve("inbound"));
        Path file = Files.writeString(
                root.resolve("orders.csv"),
                "order_id,amount\nORD-1,100.00\n",
                StandardCharsets.UTF_8);

        var resolver = new ApprovedInputResolver(root);

        assertEquals(file.toRealPath(),
                resolver.resolveReadableFile("orders.csv"));
    }

    @Test
    void rejectsPathTraversal() throws Exception {
        Path root = Files.createDirectory(temp.resolve("inbound"));
        Files.writeString(temp.resolve("private.txt"), "private");

        var resolver = new ApprovedInputResolver(root);

        assertThrows(SecurityException.class,
                () -> resolver.resolveReadableFile("../private.txt"));
    }

    @Test
    void rejectsAbsoluteFilePath() throws Exception {
        Path root = Files.createDirectory(temp.resolve("inbound"));
        var resolver = new ApprovedInputResolver(root);

        assertThrows(SecurityException.class,
                () -> resolver.resolveReadableFile(
                        temp.resolve("private.txt").toString()));
    }

    @Test
    void rejectsDirectoryInsteadOfRegularFile() throws Exception {
        Path root = Files.createDirectory(temp.resolve("inbound"));
        Files.createDirectory(root.resolve("subdir"));
        var resolver = new ApprovedInputResolver(root);

        assertThrows(IllegalArgumentException.class,
                () -> resolver.resolveReadableFile("subdir"));
    }

    @Test
    void rejectsMissingFile() throws Exception {
        Path root = Files.createDirectory(temp.resolve("inbound"));
        var resolver = new ApprovedInputResolver(root);

        assertThrows(java.io.IOException.class,
                () -> resolver.resolveReadableFile("missing.csv"));
    }
}
```

Các test này xác minh chính sách path, không chứng minh OS ACL/IAM. Chúng không cần một Spring context hoặc job hoàn chỉnh.

### 13.2. Test symlink ra ngoài root

Nếu filesystem/CI cho phép tạo symlink:

```java
@Test
void rejectsSymlinkOutsideRoot() throws Exception {
    Path root = Files.createDirectory(temp.resolve("inbound"));
    Path outside = Files.writeString(
            temp.resolve("private.txt"), "private");
    Files.createSymbolicLink(root.resolve("linked.csv"), outside);

    var resolver = new ApprovedInputResolver(root);

    assertThrows(SecurityException.class,
            () -> resolver.resolveReadableFile("linked.csv"));
}
```

Một số môi trường Windows hoặc CI không cho tạo symlink. Chỉ chạy test khi feature được hỗ trợ; nếu chính hành động tạo symlink bị từ chối thì đó chưa phải bằng chứng resolver chặn thành công.

### 13.3. Test permission thật bằng danh tính giới hạn

Dựng fixture có các danh tính:

```text
batch-ingest   : có quyền ghi inbound
batch-service  : chỉ có quyền đọc inbound
unrelated-user : không có quyền đọc inbound
```

Chạy job hoặc preflight dưới **batch-service**, kiểm tra file được cho phép mở thành công và file có ACL từ chối mở bị báo lỗi. Với object storage, chạy dưới đúng role/workload identity. Một test chạy bằng root có thể vẫn đọc được file dù mode `000`, vì vậy `chmod 000` dưới tài khoản đặc quyền không chứng minh được khả năng chặn thực tế.

### 13.4. Integration test trong Spring Batch

Với **Spring Batch 5.x**, `spring-batch-test` hỗ trợ `@SpringBatchTest` cùng `JobLauncherTestUtils` để chạy job đã cấu hình. Một ma trận hữu ích:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| File hợp lệ, service có quyền | Preflight `COMPLETED`, importer được chạy |
| File không tồn tại | Preflight `FAILED`, importer không chạy |
| File tồn tại nhưng ACL từ chối | Preflight `FAILED`, log category `ACCESS_DENIED` |
| Path traversal | Resolver từ chối, không mở file ngoài root |
| Symlink ra ngoài root | Resolver từ chối |
| File mở được nhưng sai header | Permission pass, validation schema fail |
| File thay giữa preflight/import | Snapshot/version policy phát hiện hoặc nguồn được thiết kế bất biến |
| Restart sau khi sửa quyền | Cùng input/checkpoint, writer không tạo duplicate |

Ví dụ phần assertion trong một test đã có `launcher` và `parameters` hợp lệ:

```java
JobExecution execution = launcher.launchJob(parameters);

assertEquals(BatchStatus.FAILED, execution.getStatus());

assertTrue(execution.getStepExecutions().stream()
        .anyMatch(step ->
                step.getStepName().equals("inputPreflightStep")
                && step.getStatus() == BatchStatus.FAILED));

assertTrue(execution.getStepExecutions().stream()
        .noneMatch(step ->
                step.getStepName().equals("importOrdersStep")));
```

Đây là trích đoạn minh họa: các bean, import, database và fixture cần được cấu hình trong test thực. Với Spring Batch 6.x, sử dụng đúng API test theo phiên bản, bao gồm tiện ích launch tương ứng của phiên bản đó.

## 14. Các lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng giải quyết |
| --- | --- | --- |
| `AccessDeniedException` trên Linux | UID/GID/ACL/mount hoặc thiếu traverse thư mục cha | Kiểm tra danh tính process và từng phần đường dẫn |
| `FileNotFoundException`/`NoSuchFileException` | Sai path, volume chưa mount, file chưa READY | Đối chiếu input root, manifest, staging |
| Đọc được ở IDE nhưng pod báo denied | UID khác, mount khác, ACL khác | Kiểm tra từ container và bằng UID thật |
| File 640 nhưng job vẫn không đọc được | Không thuộc group hoặc thiếu quyền trên thư mục cha | Cấp group/ACL phù hợp |
| Reader mở 0 item và job báo COMPLETED | File rỗng, cấu hình non-strict hoặc input sai | Preflight và chính sách lô rỗng |
| `ClassPathResource.getFile()` không hoạt động trong JAR | Entry nằm trong JAR | Dùng `getInputStream()` |
| S3 trả 403 | IAM/bucket/key policy/KMS | Kiểm tra role và quyền theo prefix |
| S3 trả 404 | Key sai hoặc chưa publish | Kiểm tra manifest, version, thời điểm phát hành |
| URL gọi tài nguyên nội bộ | Nguồn URL không được giới hạn | Dùng source catalog/allowlist và egress restriction |
| Restart đọc file khác nội dung | Cùng path bị overwrite | Pin version/checksum, snapshot bất biến |
| File symlink vượt thư mục được phép | Path resolution sai hoặc không kiểm tra real path | Kiểm tra root và symlink, hạn chế quyền ghi nguồn |
| Preflight pass nhưng reader mở lỗi | Permission/mount/file thay giữa hai thao tác | Xử lý exception thực tế, kiểm soát snapshot/TOCTOU |
| Test chmod pass nhưng production vẫn bị lỗi | Test không chạy dưới service identity thật | Chạy integration test với đúng UID/role giới hạn |

### Quy trình điều tra một lỗi quyền đọc

1. Lấy `jobExecutionId`, `stepExecutionId`, `sourceId` và loại resource từ log.
2. Xác định lỗi phát sinh khi resolve path, mở stream, đọc nội dung hay parse.
3. Xác minh danh tính thực thi, approved root hoặc IAM role của job.
4. Kiểm tra directory chain/ACL/mount hoặc bucket/object/KMS policy.
5. Cấp đúng quyền tối thiểu cho nguồn cần thiết; không mở rộng tới nguồn khác.
6. Khôi phục bằng restart/rerun đúng contract và giữ nguồn bất biến.
7. Đối chiếu dữ liệu đã commit để tránh duplicate do xử lý lại.

## 15. Bài tập thực hành

**Bài 1 — Resource abstraction.** Đọc một fixture trong `src/test/resources` bằng `ClassPathResource` và một file ở `@TempDir` bằng `FileSystemResource`. Giải thích sự khác nhau giữa dữ liệu đóng gói trong JAR và input mới nhận.

**Bài 2 — Least privilege.** Trên Linux test, cấu hình producer có quyền ghi và batch-service chỉ có quyền đọc. Kiểm tra quyền traverse trên các thư mục cha mà không dùng `chmod 777`.

**Bài 3 — Path traversal.** Dùng `ApprovedInputResolver` để thử `orders.csv`, `../secret.txt`, đường dẫn tuyệt đối và symlink ra ngoài root. Viết JUnit cho từng trường hợp.

**Bài 4 — Preflight step.** Tạo job gồm `inputPreflightStep` và `importOrdersStep`. Với file thiếu hoặc bị từ chối quyền, xác minh importer không chạy và database output không đổi.

**Bài 5 — Container.** Chạy job bằng UID không phải root trên mounted directory read-only. Quan sát sự khác nhau khi owner/group của file phù hợp và không phù hợp.

**Bài 6 — Cloud identity.** Thiết kế role chỉ được `GetObject` trên một prefix. Kiểm thử thiếu `kms:Decrypt`, object không tồn tại và network timeout, phân loại lỗi nên fail hay retry.

**Bài 7 — Restart.** Cho một số chunk commit rồi gây lỗi nguồn, khôi phục quyền đọc và restart đúng instance. Giữ input snapshot và metadata, xác minh không nhân đôi output.

**Bài 8 — Monitoring.** Xuất log `ACCESS_DENIED` với `sourceId`, `jobExecutionId` và `stepExecutionId`; tạo metric tổng hợp theo job mà không dùng tên file hoặc object key làm label.

## 16. Kết luận

**Quyền đọc input resource** trong Spring Batch vừa là điều kiện để job hoạt động, vừa là ranh giới bảo mật của hệ thống dữ liệu. Job cần chạy dưới danh tính được quản lý, chỉ được cấp quyền đọc những nguồn nghiệp vụ cho phép, và không được biến `JobParameters` thành đường dẫn hoặc URL tùy ý.

Với file local, kết hợp OS ACL, UID/GID và kiểm tra đường dẫn trong approved root. Với container/Kubernetes, kiểm soát volume và security context. Với object storage, dùng workload identity/IAM, phạm vi bucket/prefix và quyền decrypt. Với Spring Batch, dùng reader `@StepScope`, `FlatFileItemReader.strict(true)`, preflight step và nguồn snapshot/version ổn định để phát hiện sự cố sớm và duy trì restart an toàn.

### Tài liệu tham khảo

- [Spring Framework — Resource abstraction](https://docs.spring.io/spring-framework/reference/core/resources.html)
- [Spring Batch — Flat files và FlatFileItemReader](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html)
- [Spring Batch — Late binding và StepScope](https://docs.spring.io/spring-batch/reference/step/late-binding.html)
- [Spring Batch — Domain, JobRepository và restart](https://docs.spring.io/spring-batch/reference/domain.html)
- [Java NIO — Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [Kubernetes — Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/)
- [AWS S3 — Policies and permissions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-with-s3-policy-actions.html)
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal)
