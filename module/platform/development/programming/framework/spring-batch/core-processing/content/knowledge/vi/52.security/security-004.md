# Quyền ghi output resource trong Spring Batch

Một batch job có thể đọc dữ liệu và xử lý đúng nhưng vẫn thất bại ở bước cuối vì **không có quyền ghi tài nguyên đầu ra** (*output resource*). Ví dụ, `FlatFileItemWriter` không tạo được file CSV, writer JDBC không được `INSERT` vào bảng đích, hoặc tiến trình batch không có quyền `PutObject` lên một vùng lưu trữ đối tượng. Trong chương **Security** của **Spring Batch Core Processing**, cấu hình quyền ghi không chỉ nhằm làm cho job chạy thành công: nó còn quyết định **ai có thể tạo, sửa, ghi đè, xóa và công bố kết quả**.

Mục tiêu của bài là thiết kế quyền truy cập theo **nguyên tắc ít quyền nhất (least privilege)**, cô lập output theo kỳ chạy, tránh ghi ra đường dẫn ngoài ý muốn và vẫn bảo toàn khả năng **retry/restart** khi job lỗi.

```text
              Scheduler / JobLauncher
                      |
           JobParameters đã kiểm soát
                      |
                      v
               Spring Batch Step
                      |
         OutputPathPolicy / cấu hình đích
                      |
                      v
               ItemWriter / Tasklet
                      |
       +--------------+---------------+
       |              |               |
     File/FS       Database        S3 / SFTP / API
       |              |               |
   OS / ACL       DB privileges    IAM / credentials
       |              |               |
       +--------------+---------------+
                      |
                  Kết quả ghi
                      |
        Metadata + audit + xác nhận output
```

Điều cần phân biệt ngay từ đầu: **Spring Batch không tự cấp quyền ghi** cho tiến trình. Framework gọi writer; hệ điều hành, database, object storage hoặc hệ thống đích mới là nơi kiểm tra quyền thực tế của danh tính đang chạy batch.

## 1. “Quyền ghi” gồm những thao tác nào?

Nói “job có quyền ghi vào thư mục `/srv/batch/output`” còn khá mơ hồ. Với nhiều loại đích, quyền thường được chia nhỏ:

| Tác vụ | Ví dụ | Quyền cần quan tâm |
| --- | --- | --- |
| Tạo file mới | `orders-2026-11-16.csv` | Quyền tạo entry trong thư mục cha và quyền truy cập đường dẫn |
| Ghi nội dung file | Ghi các dòng CSV | Quyền ghi file hoặc quyền tạo file mới với chế độ cho phép ghi |
| Ghi nối | Tiếp tục một file được tạo trước đó | Quyền mở file có sẵn để ghi/append; quy tắc restart của writer |
| Ghi đè hoặc thay thế | Xuất lại báo cáo cuối ngày | Quyền ghi/xóa/đổi tên theo cơ chế filesystem hoặc API đích |
| Tạo thư mục con | `2026-11-16/` | Quyền tạo entry trong thư mục cha |
| Đổi tên/publish | `report.tmp` thành `report.csv` | Quyền sửa directory entry ở thư mục nguồn/đích; chính sách replace |
| Xóa file tạm | Cleanup sau lỗi | Quyền xóa entry hoặc quyền DELETE tương ứng |
| Liệt kê và xác minh | Kiểm tra manifest/output | Quyền đọc metadata, list hoặc read nếu cần |

Trên hệ điều hành kiểu POSIX, thao tác tạo/xóa/đổi tên file phụ thuộc nhiều vào **quyền của thư mục chứa file** (đặc biệt quyền write và execute/search), không chỉ các bit permission của chính file. Sticky bit, ACL và chính sách filesystem cũng có thể ảnh hưởng. Trên Windows, quyền truy cập được quản lý qua **ACL/NTFS**; không nên suy diễn trực tiếp mọi bit `rwx` kiểu Linux sang Windows.

Một tài khoản có thể **tạo** file nhưng không được **đọc lại**, hoặc được `PutObject` lên S3 nhưng không được `GetObject`. Điều này có thể hợp lệ theo kiến trúc, nhưng phải được phản ánh trong quá trình xác nhận output và xử lý restart.

## 2. Xác định danh tính thực sự đang ghi output

Quyền được kiểm tra theo danh tính mà kết nối/tài nguyên nhìn thấy, **không phải theo tên người viết code**. Các môi trường thường gặp:

| Môi trường | Danh tính có hiệu lực | Hệ thống cấp quyền |
| --- | --- | --- |
| Batch chạy trực tiếp trên Linux | User/group của process, ACL | Owner/group/mode/ACL, policy hệ thống |
| Batch chạy dưới Windows Service | Service account và access token | NTFS ACL, share permissions nếu dùng mạng |
| Container Docker | UID/GID trong container và ánh xạ quyền trên volume | Filesystem host, volume mount, container security |
| Kubernetes Pod | UID/GID của container, supplemental groups, service account | Volume filesystem, policy Pod và quyền cloud |
| JDBC writer | Database user của `DataSource` | `GRANT` theo schema/table/procedure |
| S3/object storage | IAM role, workload identity hoặc credentials | Bucket policy, IAM, KMS, object ownership |
| SFTP | Tài khoản SFTP/SSH | Quyền thư mục phía server, chroot, ACL |

Ví dụ, ứng dụng Spring Boot trên laptop có thể tạo file khi chạy bằng tài khoản developer, nhưng khi triển khai vào Pod chạy `runAsUser: 10001`, container lại không ghi được vào volume vì thư mục thuộc `root:root`. Cùng một `FlatFileItemWriter` sẽ có kết quả khác nhau mà không phải lỗi của API Spring Batch.

### 2.1. Nguyên tắc least privilege

- Chỉ cấp quyền trên **đường dẫn/prefix/schema cần dùng**, không cấp ghi toàn bộ filesystem hoặc bucket.
- Dùng tài khoản dịch vụ riêng cho batch thay vì tài khoản quản trị.
- Tách quyền **ghi staging**, **công bố output**, **xóa/cleanup** và **đọc audit** nếu rủi ro nghiệp vụ yêu cầu.
- Không cấp `777`, quyền root hoặc IAM wildcard chỉ để giải quyết tạm lỗi `Access denied`.
- Quản lý secret/credential qua cơ chế secrets hoặc workload identity; không hard-code password, access key vào `application.yml` hay log.
- Bảo đảm quyền **đủ cho restart**: cần mở lại đúng output/tệp tạm của `JobInstance` trước đó khi writer hỗ trợ lưu state.

## 3. Quyền ghi file trên Linux và POSIX

Giả sử output root là `/srv/batch/output`. Nên chuẩn bị thư mục tại bước **provisioning/deployment**, với owner/group xác định và chỉ nhóm batch được phép ghi.

Ví dụ các lệnh dành cho người vận hành (không phải lệnh cần nhúng vào job):

```bash
# Chuẩn bị từ tài khoản có quyền quản trị, theo quy trình deployment.
sudo install -d -o batchuser -g batchgroup -m 0750 /srv/batch/output

# Kiểm tra danh tính và quyền hiện có.
id batchuser
ls -ld /srv/batch/output
namei -l /srv/batch/output
getfacl /srv/batch/output

# Kiểm tra bằng chính danh tính chạy batch nếu chính sách hệ thống cho phép.
sudo -u batchuser test -w /srv/batch/output
```

Mode `0750` trên thư mục cho phép owner đọc/ghi/đi qua thư mục, group đọc/đi qua, không cấp quyền cho others. Nếu batch chạy bằng `batchuser` thì owner có quyền tạo file. Nếu cần nhiều service account cùng tạo output, có thể dùng group được cấp quyền ghi hoặc ACL cụ thể thay vì mở `0777`.

**Chú ý:** `test -w` hoặc `Files.isWritable(...)` chỉ kiểm tra điều kiện tại thời điểm chạy. Nó không bảo đảm thao tác ghi sau đó sẽ thành công vì ACL, quota, readonly mount, SELinux/AppArmor, thay đổi quyền, cạnh tranh hoặc filesystem mạng có thể gây lỗi. Cần xử lý exception của lần mở/ghi file thực tế.

### 3.1. File permission và `umask`

Tệp mới nhận quyền từ chế độ tạo file, `umask`, ACL mặc định và hành vi filesystem. Ví dụ process có `umask 027` thường khiến file tạo mặc định không đọc được bởi users ngoài group, nhưng permission cuối vẫn phụ thuộc API ghi file và thiết lập của môi trường.

Không đặt `chmod 777` cho mọi file output sau khi ghi: điều này mở quyền không cần thiết, có thể làm lộ dữ liệu khách hàng hoặc cho phép tiến trình khác thay đổi file trước khi được công bố. Nếu cần đặt permission cụ thể trên POSIX filesystem, có thể cấu hình thư mục/ACL từ deployment và chỉ chỉnh permission trong ứng dụng khi thực sự cần.

### 3.2. Quyền ghi thư mục cha khác quyền ghi file

Với file `/srv/batch/output/2026-11-16/orders.csv`, job cần traversable directory ở mọi cấp và cần quyền tạo file trong `2026-11-16/`. Nếu `orders.csv` đã tồn tại do một job khác tạo, quyền owner/mode của **file hiện có** có thể khiến writer không mở được ở chế độ append/truncate, dù thư mục cha có thể ghi được.

Nếu job chạy bằng các service account khác nhau qua các lần deployment, cần có chiến lược ownership/ACL nhất quán để **restart một file cũ**. Thay UID/GID mà không thay quyền volume có thể khiến lần chạy mới chỉ đọc được input nhưng không ghi tiếp output.

## 4. Quyền ghi trên Windows và thư mục mạng

Windows kiểm soát file qua NTFS ACL, quyền share (nếu truy cập UNC) và token của process. Một đường dẫn như `D:\batch\output\orders.csv` có thể ghi được khi chạy từ IDE nhưng thất bại dưới Windows Service vì service account không có quyền trên `D:\batch\output`.

Với thư mục chia sẻ `\\fileserver\batch-output`, thường cần kiểm tra **cả share permission và NTFS ACL**; quyền hiệu lực là kết quả của nhiều lớp kiểm soát. Batch service chạy như `LocalSystem` trên máy A không nhất thiết có quyền truy cập share trên máy B.

Các điểm cần kiểm tra:

1. Tài khoản chạy Windows Service hoặc scheduled task có đúng danh tính được cấp ACL không?
2. Quyền **Create files**, **Write data**, **Append data**, **Delete** hoặc **Modify** có phù hợp với cách writer tạo/replace file không?
3. File có đang bị process khác mở bằng chế độ khóa chia sẻ (sharing violation) không?
4. Đường dẫn có bị ảnh hưởng bởi mapped drive chỉ tồn tại trong session đăng nhập của người dùng không? Với service, UNC path thường rõ ràng hơn ký tự ổ đĩa map theo user.

Đừng xử lý mọi lỗi ghi file bằng cách chạy service với tài khoản Administrator. Hãy cấp ACL đúng folder và xem xét tính chất dữ liệu của output.

## 5. Kiểm soát đường dẫn đầu ra từ `JobParameters`

Spring Batch hỗ trợ đưa output path vào `JobParameters`, sau đó inject bằng `@StepScope`. Kỹ thuật này hữu ích để xuất theo kỳ dữ liệu, nhưng cũng có rủi ro nếu scheduler/API cho người dùng truyền một đường dẫn tùy ý.

Ví dụ **không nên dùng trực tiếp dữ liệu chưa xác thực**:

```java
@Bean
@StepScope
FlatFileItemWriter<String> unsafeWriter(
        @Value("#{jobParameters['outputPath']}") String outputPath) {
    return new FlatFileItemWriterBuilder<String>()
        .name("unsafeWriter")
        .resource(new FileSystemResource(outputPath))
        .lineAggregator(item -> item)
        .build();
}
```

Nếu một bên có quyền tạo batch execution truyền `/etc/sensitive.conf`, `../other-tenant/report.csv` hoặc đường dẫn thuộc vùng file chung, writer có thể cố ghi ra ngoài vùng mong muốn. Việc có thành công hay không phụ thuộc quyền OS, nhưng ứng dụng **không nên để đường dẫn do bên ngoài quyết định hoàn toàn**.

### 5.1. Sinh đường dẫn từ business key đã kiểm soát

Mô hình an toàn hơn: ứng dụng kiểm soát `outputRoot` và **tự xây dựng tên file** từ những tham số có miền giá trị hẹp. Ví dụ Spring Boot 3.x/Spring Batch 5.x:

```java
package com.example.batch.output;

import java.nio.file.Path;
import java.time.LocalDate;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class OutputPathPolicy {

    private final Path root;

    public OutputPathPolicy(
            @Value("${batch.output.root}") String configuredRoot) {
        this.root = Path.of(configuredRoot).toAbsolutePath().normalize();
    }

    public Path fileFor(String businessDate, String exportKey) {
        // Từ chuỗi ngày không tin cậy sang giá trị ngày hợp lệ.
        LocalDate date = LocalDate.parse(businessDate);

        // Chỉ cho phép ký tự dùng làm tên file; tránh dấu /, \\, .., :.
        if (exportKey == null
                || !exportKey.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid exportKey");
        }

        Path result = root
            .resolve(date.toString())
            .resolve("orders-" + exportKey + ".csv")
            .normalize();

        if (!result.startsWith(root)) {
            throw new SecurityException("Output escapes configured root");
        }
        return result;
    }
}
```

Ví dụ với `batch.output.root=/srv/batch/output`, `businessDate=2026-11-16` và `exportKey=settlement-01` sẽ tạo:

```text
/srv/batch/output/2026-11-16/orders-settlement-01.csv
```

**Giới hạn của kiểm tra lexical:** `normalize()` và `startsWith()` ngăn traversal thông qua các thành phần đường dẫn dạng `..`, nhưng **không tự bảo vệ khỏi symbolic link/junction** trong thư mục cha. Nếu người không tin cậy có thể thay các directory entry dưới output root, họ có thể khiến đường dẫn trông như nằm trong root nhưng thực tế trỏ ra ngoài. Bảo vệ quan trọng nhất là **output root và các thư mục trung gian phải thuộc quyền quản lý của service/deployment, không được người dùng khác tạo hoặc thay symlink**. Trong môi trường thực sự có đầu vào đường dẫn không tin cậy hoặc bị cạnh tranh, cần dùng các API filesystem không đi theo symlink/secure directory operations hoặc kiến trúc cô lập process phù hợp, thay vì chỉ kiểm tra chuỗi một lần.

### 5.2. Gắn writer với đường dẫn được tạo bởi policy

```java
package com.example.batch.output;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
public class OutputWriterConfiguration {

    @Bean
    @StepScope
    public FlatFileItemWriter<String> ordersWriter(
            OutputPathPolicy pathPolicy,
            @Value("#{jobParameters['businessDate']}") String businessDate,
            @Value("#{jobParameters['exportKey']}") String exportKey)
            throws IOException {

        Path target = pathPolicy.fileFor(businessDate, exportKey);

        // Thành công chỉ khi service account thực sự có quyền tạo thư mục.
        Files.createDirectories(target.getParent());

        return new FlatFileItemWriterBuilder<String>()
            .name("ordersWriter")
            .resource(new FileSystemResource(target))
            .encoding(StandardCharsets.UTF_8.name())
            .lineAggregator(value -> value)
            .saveState(true)
            .build();
    }
}
```

Đây là **mẫu cấu hình minh họa** cho step xuất các dòng `String`. `Files.createDirectories(...)` không phải cách cấp quyền: nó chỉ thành công nếu quyền trên thư mục cha đã phù hợp. Nếu môi trường yêu cầu thư mục được tạo sẵn bởi deployment hoặc thư mục con thuộc chính sách quản trị chặt chẽ, có thể bỏ bước tạo thư mục động và để job fail khi thiếu provisioning.

`@StepScope` quan trọng vì `JobParameters` được gắn với **step execution**; writer được tạo khi step thực thi thay vì khởi tạo sớm lúc Spring context bắt đầu. `name("ordersWriter")` và `.saveState(true)` giúp writer có trạng thái ổn định để phục hồi theo cơ chế `ItemStream`. Khi thay tên bean/writer, đường dẫn hoặc quyền giữa hai lần chạy, cần xem xét ảnh hưởng đến restart.

### 5.3. Định danh output qua restart

Giả sử `businessDate` và `exportKey` là identifying `JobParameters`:

```java
JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("exportKey", "settlement-01")
    .toJobParameters();
```

Khi restart **cùng JobInstance**, writer cần quay về đúng output resource, có khả năng mở file hiện có và khôi phục trạng thái đã lưu. Nếu mỗi lần thực thi lại dùng UUID mới trong tên file mà không giữ quan hệ với instance cũ, job có thể tạo file mới, bỏ mất file dở dang hoặc nhân đôi kết quả.

Với một batch đã `COMPLETED` và cần xuất lại, đó có thể là **rerun/new version** thay vì restart. Khi ấy nên dùng `exportKey`/version mới và chính sách publish rõ ràng; không tự ghi đè báo cáo chính thức bằng một lần chạy chưa được đối soát.

## 6. Quyền ghi và hành vi của `FlatFileItemWriter`

`FlatFileItemWriter` cần mở `Resource` để ghi. Một số cấu hình tác động đến output:

| Cấu hình/đặc điểm | Ý nghĩa | Điều phải kiểm tra về quyền và restart |
| --- | --- | --- |
| `resource(...)` | File hoặc resource đích | Directory/file có tồn tại? Process có quyền mở đúng đường dẫn? |
| `saveState(true)` | Lưu trạng thái writer vào `ExecutionContext` | Repository và file hiện có phải ổn định giữa các lần restart |
| `shouldDeleteIfExists(...)` | Chính sách xử lý file đã tồn tại ở lần chạy mới, có xét trạng thái restart | Không vô tình xóa output của job/instance khác |
| `appendAllowed(true)` | Cho phép nối dữ liệu vào file hiện có theo chế độ writer | Cần chống trùng, xác định output thuộc instance nào |
| `shouldDeleteIfEmpty(true)` | Xóa output rỗng theo điều kiện của writer | Cần quyền xóa file; đừng giả định có file sau step rỗng |
| `encoding(...)` | Encoding của output | Không ảnh hưởng ACL trực tiếp nhưng quan trọng khi xác nhận kết quả |

Spring Batch có logic hỗ trợ restart với writer có state; tuy vậy, không nên coi mọi chế độ append/truncate/delete là an toàn trong mọi cấu hình và filesystem. Nếu quyền không cho phép mở lại file sau thất bại, checkpoint của reader còn nguyên cũng không giúp bước ghi hoàn tất.

### Tạo được file chưa chắc ghi được toàn bộ

Permission có thể thay đổi trong lúc step chạy; quota, filesystem read-only, hết dung lượng hay lỗi I/O có thể xuất hiện sau khi writer đã mở file. Nếu bước ghi bị lỗi, framework thường chuyển step sang trạng thái thất bại và lưu metadata khi có thể. **File có thể đã tồn tại và chứa dữ liệu một phần**. Không công bố file đó là đầu ra hoàn chỉnh chỉ vì `Files.exists(path)` trả `true`.

Nên xác nhận `JobExecution`/`StepExecution`, kích thước/nội dung hoặc checksum kết quả, sau đó mới publish cho consumer. Với output quan trọng, một cơ chế **staging → verify → publish** thường dễ kiểm soát hơn ghi trực tiếp vào đường dẫn mà người dùng đọc.

## 7. Staging, công bố kết quả và quyền xóa

Một pipeline xuất báo cáo an toàn có thể dùng hai vùng quyền khác nhau:

```text
/srv/batch/staging/2026-11-16/orders-settlement-01.part
             |
       ghi và restart tại đây
             |
             v
    Batch COMPLETED + validation
             |
             v
/srv/batch/published/2026-11-16/orders-settlement-01.csv
```

Vùng `staging` chỉ batch có quyền ghi và cleanup; consumer không đọc trực tiếp. Vùng `published` được bảo vệ để chỉ một bước publish có quyền tạo hoặc thay thế output đã công nhận. Việc phân quyền có thể bằng OS group/ACL hoặc qua một dịch vụ publish riêng.

### 7.1. Publish bằng thao tác move

Trên filesystem có hỗ trợ, có thể rename/move tệp tạm sang tên chính thức sau khi đã đóng writer và xác nhận job:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

void publish(Path stagingFile, Path publishedFile) throws Exception {
    // Ví dụ: hai path đã được OutputPathPolicy xác thực trước đó.
    Files.createDirectories(publishedFile.getParent());
    Files.move(stagingFile, publishedFile,
        StandardCopyOption.ATOMIC_MOVE);
}
```

**Điều kiện và giới hạn:** `ATOMIC_MOVE` chỉ hoạt động khi provider/filesystem hỗ trợ. Nếu staging và published ở hai filesystem/volume khác nhau, thao tác có thể thất bại; cần thiết kế copy + verify + final manifest hoặc cơ chế publish khác. Hành vi khi đích đã tồn tại còn tùy provider; không dùng mã trên như chính sách chống ghi đè tuyệt đối khi có nhiều publisher cạnh tranh. Với yêu cầu “chỉ được tạo một kết quả”, cần thêm khóa/điều phối và kiểm soát replace có chủ đích.

Atomic rename giúp tránh consumer thấy **nửa file** trên filesystem có hỗ trợ, nhưng không đồng nghĩa mọi dữ liệu đã được flush bền vững qua mất điện. Nếu yêu cầu durability cao, cần tuân thủ chính sách flush/sync và lưu trữ của nền tảng.

### 7.2. Quyền cleanup không đồng nghĩa quyền ghi output chính thức

Với file tạm của job thất bại, batch có thể cần quyền xóa để cleanup sau khi không còn khả năng restart. Nhưng **không được dọn file tạm trước khi xác định không cần restart**. Một process cleanup dùng wildcard quá rộng có thể xóa output của execution khác đang chạy.

Nên đặt file theo `businessDate`, `jobInstanceId` hoặc `exportKey` ổn định và chỉ cleanup những tài nguyên được gắn với execution/instance đã xác nhận kết thúc vòng đời. Việc phân quyền xóa có thể tách khỏi writer nếu chính sách an ninh yêu cầu.

## 8. Container và Kubernetes: filesystem có thể chỉ đọc

Trong môi trường container, một cấu hình bảo mật phổ biến là cho process chạy **không phải root** và đặt root filesystem của container ở chế độ chỉ đọc. Job vẫn có thể ghi output nếu đã được cấp **volume riêng có quyền ghi**.

Ví dụ fragment Kubernetes Pod template (cần điều chỉnh theo cluster/storage class và image của ứng dụng):

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001

  containers:
    - name: batch
      image: example.com/batch/import-orders:1.0.0
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
      env:
        - name: BATCH_OUTPUT_ROOT
          value: /work/output
      volumeMounts:
        - name: batch-output
          mountPath: /work/output
          readOnly: false

  volumes:
    - name: batch-output
      persistentVolumeClaim:
        claimName: batch-output-pvc
```

Trong ứng dụng:

```yaml
batch:
  output:
    root: ${BATCH_OUTPUT_ROOT:/work/output}
```

`runAsUser`/`runAsGroup` xác định danh tính process; `fsGroup` có thể hỗ trợ cấp quyền nhóm trên volume đối với các loại volume/CSI driver có hỗ trợ. **Không phải mọi storage driver đều đổi ownership theo `fsGroup`**, và PVC vẫn cần được chuẩn bị đúng ACL/permission. Nếu dùng `emptyDir`, dữ liệu file sẽ mất khi Pod bị loại bỏ; điều này có thể phá restart nếu file đang ghi dở. Với job cần khôi phục trên Pod mới, chọn vùng lưu trữ có độ bền phù hợp và dùng đường dẫn ổn định.

### 8.1. Những lỗi container thường gặp

- Image chạy local bằng root nên ghi được; production dùng non-root nên báo `Permission denied`.
- Volume mount readonly do `readOnly: true`, policy security hoặc filesystem của node.
- Pod mới có UID/GID khác owner của file được Pod cũ tạo, khiến restart thất bại.
- Output ghi vào filesystem container thay vì volume: file biến mất khi Pod được thay thế.
- Nhiều Pod ghi cùng output name trên PVC gây tranh chấp/ghi đè.
- Network filesystem hoặc CSI có chính sách ownership/ACL khác POSIX thông thường.

Khi điều tra, cần kiểm tra identity hiệu lực, filesystem permission của **đúng mount**, pod security context, CSI driver và event của Pod. Không sửa lỗi bằng cách cho toàn bộ workload chạy privileged nếu vấn đề thực tế chỉ là ownership của thư mục output.

## 9. Object storage: quyền IAM khác quyền filesystem

Khi output là S3 hoặc object storage tương thích, writer/adapter của ứng dụng thường phải dùng SDK hoặc service API; một `FileSystemResource` thông thường **không tự biến đường dẫn `s3://...` thành file có thể ghi**. Quyền do IAM/bucket policy và có thể là KMS quyết định.

Ví dụ IAM policy cho phép **chỉ ghi object dưới một prefix xuất báo cáo** (thay tên bucket và prefix cho môi trường thật):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::example-batch-output/exports/orders/*"
    }
  ]
}
```

Policy này chỉ minh họa một quyền object-level. Nếu pipeline cần kiểm tra object đã tồn tại, đọc lại checksum, liệt kê prefix, xóa file tạm hoặc thao tác multipart upload, có thể cần các quyền tương ứng như `s3:GetObject`, `s3:ListBucket` trên bucket với điều kiện prefix, `s3:DeleteObject` trên phạm vi hẹp, hoặc quyền xử lý multipart. Nếu object được mã hóa với KMS key do khách hàng quản lý, cần cân nhắc thêm key policy/IAM cho các thao tác KMS liên quan.

**Không cấp `s3:*` trên `*` chỉ vì một lần upload bị từ chối.** Lỗi có thể do bucket policy chặn, key/prefix sai, KMS, explicit deny, permission boundary hoặc credential hết hạn. Mỗi trường hợp cần phân loại nguyên nhân chính xác.

### 9.1. Object key và version

Một object key nên được sinh từ business key đã validate:

```text
s3://example-batch-output/exports/orders/2026-11-16/settlement-01.csv
```

Như đường dẫn file, không ghép trực tiếp tenant ID hoặc path chưa kiểm tra vào key rồi tin rằng prefix restriction sẽ tự bảo đảm cách ly. Nếu ứng dụng phục vụ nhiều tenant, role/prefix cần được giới hạn theo tenant và việc kiểm tra quyền ở API nhận request phải thống nhất với policy ở object storage.

S3 object upload không giống append/truncate trên file cục bộ. Với restart hoặc retry upload, có thể cần tạo object tạm/versioned, kiểm tra ETag/checksum theo đặc điểm upload, rồi publish manifest. Nếu một request upload trả timeout, object có thể **đã được tạo** dù client không nhận response; vì vậy idempotency và kiểm tra object/version rất quan trọng.

### 9.2. SFTP và external API

Với SFTP, service account cần quyền ghi vào đúng thư mục trên server và có thể cần quyền rename/delete nếu dùng temporary upload. Không cấp shell/full filesystem permission nếu chỉ cần SFTP chroot. Với HTTP API, token nên chỉ có scope cho phép tạo resource đích; nếu API có idempotency key, sử dụng cùng key cho một logical output để tránh tạo bản ghi trùng khi timeout/retry.

## 10. Database writer cũng cần quyền ghi đúng mức

`JdbcBatchItemWriter`, `JpaItemWriter` hoặc writer tùy biến truy cập database qua user/role của `DataSource`. Để ghi vào bảng nghiệp vụ `report_output`, tài khoản batch thường cần `INSERT`, có thể `UPDATE` nếu upsert; `SELECT` nếu xác minh/idempotency; và không nhất thiết cần `DROP TABLE`, `ALTER TABLE` hoặc quyền DBA.

Ví dụ quyền tối thiểu kiểu PostgreSQL (tên schema/role giả định):

```sql
GRANT USAGE ON SCHEMA reporting TO batch_writer;
GRANT INSERT, UPDATE, SELECT ON TABLE reporting.report_output
    TO batch_writer;
```

Trường hợp sử dụng sequence hoặc auto-generated ID có thể cần quyền `USAGE`/`SELECT` trên sequence tùy SQL và schema. Trường hợp sử dụng `DELETE`, staging table hoặc stored procedure cũng cần quyền đúng phạm vi. Quyền trên các bảng `BATCH_*` của `JobRepository` là một lớp riêng: framework phải có khả năng tạo/cập nhật metadata execution và context theo cách được triển khai. Có thể đặt repository và bảng nghiệp vụ ở hai schema/datasource với roles tách biệt, nhưng cần thiết kế transaction và quyền cho từng nguồn thật rõ ràng.

**Không dùng tài khoản migration/DDL toàn quyền làm runtime `DataSource`** chỉ vì ứng dụng đang phải tạo bảng lúc khởi động. Nên tách quy trình schema migration (Flyway/Liquibase hoặc deployment step) khỏi quyền runtime của batch khi môi trường hỗ trợ.

### Quyền ghi và transaction

Một writer có đủ quyền `INSERT` không đồng nghĩa dữ liệu sẽ được commit: transaction có thể rollback khi chunk lỗi. Ngược lại, writer gửi request sang hệ thống ngoài transaction có thể tạo side effect dù metadata Batch thất bại. Đối với retry/restart, cần dùng khóa nghiệp vụ, unique constraint, upsert có chủ đích hoặc transactional outbox thay vì chỉ dựa vào permission.

## 11. Phân loại lỗi khi không ghi được resource

Một số lỗi nhìn bên ngoài đều có biểu hiện “writer thất bại”, nhưng cách xử lý khác nhau:

| Hiện tượng | Nguyên nhân có thể | Cách xử lý phù hợp |
| --- | --- | --- |
| `AccessDeniedException`/`Permission denied` | UID/GID/ACL hoặc thư mục cha không cho tạo/mở file | Kiểm tra identity và quyền trên đúng path; sửa provisioning |
| `Read-only file system` | Mount/volume readonly | Đổi kiến trúc mount hoặc đường dẫn; không retry vô hạn |
| `No such file or directory` | Thư mục cha thiếu, path sai | Chuẩn bị directory hoặc chỉnh cấu hình; không tự tạo cây thư mục ngoài vùng cho phép |
| `FileAlreadyExistsException` | Policy không cho ghi đè, chạy trùng kỳ | Kiểm tra output identity và chính sách publish/rerun |
| `No space left on device` hoặc quota | Thiếu dung lượng/inode/quota | Khắc phục hạ tầng, cleanup đúng phạm vi rồi restart |
| Windows sharing violation | File đang bị process khác khóa | Đóng handle, loại bỏ concurrent writer hoặc dùng output path riêng |
| `AccessDenied` trên object storage | IAM, bucket policy, KMS, explicit deny hoặc prefix sai | Điều tra quyền theo action/resource của request |
| SQL permission denied | User DB không có quyền DML/schema | Cấp chính xác quyền cần thiết hoặc thay runtime role |
| Timeout khi ghi API/SFTP | Mạng/đích chậm; kết quả có thể chưa rõ | Kiểm tra trạng thái đích, idempotency và retry có kiểm soát |

### 11.1. Không dùng skip để che lỗi permission

Spring Batch hỗ trợ `skip(...)` để bỏ qua **item lỗi dữ liệu** có thể định danh. Nhưng lỗi filesystem permission hoặc quyền DB thường ảnh hưởng toàn bộ output của step. Không nên cấu hình `.skip(Exception.class)` hoặc `.skip(IOException.class)` chỉ để job vẫn `COMPLETED` khi writer không thể ghi. Cách đó có thể biến cả lô dữ liệu hợp lệ thành “bị bỏ qua” mà không có kết quả đầu ra.

Đối với permission denied mang tính cố định, retry liên tục cũng không giải quyết được lỗi. Hãy **fail step**, phát cảnh báo với resource đã được làm mờ thông tin nhạy cảm, sửa quyền ở hạ tầng rồi restart. Với lỗi tạm thời (khóa file, mạng chập chờn), có thể retry giới hạn nếu thao tác lặp lại an toàn và đã xác định có khả năng phục hồi.

### 11.2. Không coi `Files.isWritable` là bước cấp quyền

Trong Java NIO:

```java
Path directory = Path.of("/srv/batch/output");

if (!Files.isDirectory(directory) || !Files.isWritable(directory)) {
    throw new IllegalStateException("Batch output directory is not writable");
}
```

Đoạn này chỉ là **preflight cho đường dẫn đã tồn tại**, hữu ích để báo lỗi sớm. Nó không bảo đảm thành công khi mở file, và có thể trả kết quả không đủ chính xác trong một số provider/ACL. Writer vẫn phải xử lý `IOException`/exception thực tế. Không dùng `Files.setWritable(..., true)` làm cách sửa quyền ở production: service account thường không phải owner, và cố tự nới rộng quyền đi ngược mô hình least privilege.

## 12. Quyền ghi và restart: hai yêu cầu không thể tách rời

Giả sử batch ghi file lớn theo chunk, lưu trạng thái vào `ExecutionContext`, rồi thất bại ở chunk thứ ba. Khi job restart:

```text
Lần chạy #1
  JobInstance = report-2026-11-16
  output = staging/report-2026-11-16.part
  chunk 1, 2: hoàn tất và checkpoint
  chunk 3: lỗi

Lần chạy #2 (restart cùng JobInstance)
  phải truy cập lại đúng output resource
  writer mở file theo checkpoint hiện có
  xử lý phần chưa commit và hoàn tất
```

Các thay đổi sau có thể phá restart dù metadata vẫn còn:

- Đổi tài khoản chạy batch từ UID 10001 sang UID 10002 nhưng file cũ chỉ cho owner ghi.
- Pod mới không mount cùng PVC hoặc mount ở một vị trí khác.
- Cleanup tự động xóa file tạm ngay khi execution `FAILED` dù instance còn cần restart.
- Đổi đường dẫn theo `jobExecutionId` thay vì khóa ổn định theo `JobInstance` mà không thiết kế cơ chế chuyển giao state.
- Tạo tên file mới ngẫu nhiên trong constructor writer khi context không lưu đường dẫn tương ứng.
- Đổi cấu hình append/delete ở writer giữa hai execution mà chưa kiểm thử migration của `ExecutionContext`.
- Phân quyền cho writer tạo file nhưng không đủ quyền mở lại hoặc ghi tiếp file đã có.

**`JobRepository` không lưu và khôi phục quyền OS/IAM.** Nó lưu metadata thực thi và context, không sửa ACL, không mount volume và không cấp token cloud. Vì vậy một playbook restart phải kiểm tra cả metadata lẫn điều kiện truy cập resource bên ngoài.

### 12.1. Nguyên tắc phục hồi an toàn

1. Đọc `JobInstance` và `JobParameters` đã persist để xác định đúng business key/output resource.
2. Kiểm tra output/tệp tạm có còn tồn tại, đúng phiên bản và đủ quyền mở bởi service account mới không.
3. Kiểm tra permission đã được sửa **theo deployment policy**, tránh `chmod 777` hoặc cấp quyền quản trị tạm thời không thu hồi.
4. Chạy restart cùng instance theo API Spring Batch phù hợp; không tự thêm identifying parameter để tạo instance mới.
5. Đối soát output cuối sau restart: số dòng, checksum, khóa nghiệp vụ hoặc manifest.

Nếu output không thể khôi phục, cần quy trình **rerun từ đầu có kiểm soát** và idempotency; không mặc định một job mới có thể tiếp tục đúng phần đã xử lý.

## 13. Kiểm thử quyền ghi output resource

Unit test kiểm tra path policy và integration test kiểm tra service account/runtime có thể ghi vào resource thật. Không cần đợi đến production mới biết batch không thể tạo file.

### 13.1. Unit test path policy bằng `@TempDir`

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class OutputPathPolicyTest {

    @TempDir
    Path root;

    @Test
    void createsDeterministicPathInsideConfiguredRoot() {
        OutputPathPolicy policy = new OutputPathPolicy(root.toString());

        Path result = policy.fileFor("2026-11-16", "settlement-01");

        assertThat(result).startsWith(root.toAbsolutePath().normalize());
        assertThat(result.getFileName().toString())
            .isEqualTo("orders-settlement-01.csv");
    }

    @Test
    void rejectsUntrustedExportKey() {
        OutputPathPolicy policy = new OutputPathPolicy(root.toString());

        assertThatThrownBy(() -> policy.fileFor("2026-11-16", "../outside"))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
```

`@TempDir` quản lý thư mục test; kiểm thử trên xác nhận quy tắc đặt tên và traversal **theo chuỗi**. Nó không xác nhận đầy đủ khả năng chống symlink race, ACL production hoặc behavior của network volume. Với đường dẫn không tin cậy, cần test bảo mật ở môi trường cô lập có quyền tạo symlink/junction và kết hợp với policy cấp quyền filesystem.

### 13.2. Integration test writer với output tạm

Ví dụ phần assertions sau khi một step Spring Batch 5.x được chạy với `@SpringBatchTest` và `JobLauncherTestUtils`:

```java
Path root = testDir.resolve("output");
Files.createDirectories(root);

JobParameters params = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16")
    .addString("exportKey", "test-001")
    .toJobParameters();

JobExecution execution = jobLauncherTestUtils.launchStep(
    "exportOrdersStep", params);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

Path output = root.resolve("2026-11-16/orders-test-001.csv");
assertThat(Files.readAllLines(output, StandardCharsets.UTF_8))
    .containsExactly("A001,PAID", "A002,NEW");
```

Đây là **mẫu một phần của test**, giả định step/beans đã được cấu hình và `batch.output.root` trong test context thực sự trỏ tới `root` do test sở hữu. Trong test thực tế, nên cung cấp output root qua cấu hình test, ví dụ dynamic property hoặc cấu hình riêng cho fixture, không dùng production directory. Một integration test chỉ kiểm tra file có tồn tại mà không đọc nội dung có thể bỏ sót file rỗng/dở dang.

### 13.3. Negative test: permission denied

Một negative test có giá trị là chạy batch bằng **cùng loại identity/volume policy của production** trong môi trường cô lập, nhưng cấp resource **read-only** hoặc không có quyền ghi. Kỳ vọng step `FAILED`, không có output được công bố và có log/cảnh báo phân loại được lỗi.

Không nên cố mô phỏng permission denied bằng `chmod` trong một test JUnit đa nền tảng rồi mặc định kết quả giống nhau. Windows ACL, Linux root, container filesystem và driver volume khác nhau. Với Kubernetes, có thể dùng test Pod non-root và mount read-only; với Windows, dùng service account thử nghiệm có ACL hạn chế. Trường hợp không thể dựng hạ tầng thật trong CI, có thể dùng fake writer/resource ném `IOException` để test chính sách fail và alert, nhưng **không thể coi đó là bằng chứng quyền OS thật được cấu hình đúng**.

### 13.4. Test sau khi sửa quyền và restart

Kịch bản gợi ý:

| Pha | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| 1 | Writer bắt đầu trên volume đủ quyền; một số chunk commit | Có output tạm và checkpoint |
| 2 | Giả lập lỗi ghi ở chunk sau hoặc thay policy quyền trong môi trường test | Execution `FAILED`, không publish file dở dang |
| 3 | Khôi phục quyền đúng theo policy | Process có thể mở lại cùng output |
| 4 | Restart cùng identifying parameters | Tạo `JobExecution` mới của cùng `JobInstance` |
| 5 | Đối soát kết quả | File cuối đúng số dòng, không thiếu/trùng; output được publish đúng một lần |

Nếu permission bị từ chối trước khi writer mở và chưa có chunk commit, vẫn phải kiểm tra status và cleanup; không giả định chắc chắn đã có file tạm.

## 14. Monitoring, logging và audit quyền ghi

Các sự kiện nên được ghi có cấu trúc để phân biệt lỗi truy cập với lỗi dữ liệu:

```text
event=batch.output.open_failed
jobName=exportOrdersJob
jobExecutionId=814
stepExecutionId=1260
businessDate=2026-11-16
resourceType=FILE
resourceAlias=orders-report-staging
errorCategory=PERMISSION_DENIED
```

Không nhất thiết log **đường dẫn tuyệt đối**, URL có chữ ký (presigned URL), secret, connection string hay object metadata nhạy cảm. Trong môi trường nhiều tenant, một `resourceAlias`, loại resource và mã lỗi thường đủ để phân loại; chi tiết nhạy cảm nên nằm ở log được phân quyền hoặc kênh điều tra nội bộ.

Các số liệu hữu ích:

- Số execution thất bại vì `PERMISSION_DENIED`, `READ_ONLY`, `QUOTA_EXCEEDED`, `RESOURCE_LOCKED`.
- Thời gian mở output và ghi mỗi chunk; tỷ lệ lỗi upload/object write.
- Số file `.tmp/.part` còn tồn tại sau khi instance đã hết khả năng restart.
- Số kỳ nghiệp vụ đã `COMPLETED` nhưng chưa có output manifest được publish.
- Số lần restart sau khi đổi identity hoặc di chuyển volume.

Đối với audit, có thể lưu `jobExecutionId`, `businessDate`, output resource alias, output version/checksum và principal/service identity ở mức **không chứa credential**. Danh tính có quyền ghi và sự kiện publish quan trọng để giải thích ai hoặc workload nào đã tạo kết quả, đặc biệt với batch tài chính hoặc báo cáo phải phê duyệt.

## 15. Checklist thiết kế quyền ghi trước deployment

| Câu hỏi | Hành động nên có |
| --- | --- |
| Job chạy bằng UID, service account hoặc IAM role nào? | Xác định identity thực và ghi rõ trong deployment config |
| Chỉ những thư mục/prefix/table nào cần ghi? | Giới hạn least privilege theo resource cụ thể |
| Job có cần tạo thư mục con, append, rename hoặc delete không? | Cấp đúng các quyền bổ sung, không chỉ “write” chung chung |
| Output path có lấy từ request/JobParameters không? | Dùng output root cố định, validate business key, bảo vệ symlink/junction |
| Writer có thể mở lại đúng output sau crash không? | Thiết kế tên output ổn định theo job instance và giữ trạng thái writer |
| Output có nằm trên storage bền vững qua restart/Pod replacement không? | Chọn PVC/object storage hoặc cơ chế staging phù hợp |
| Nếu cần publish, ai có quyền đưa file vào vùng chính thức? | Tách staging/published, kiểm soát replace và manifest |
| Môi trường có quota, read-only mount hoặc ACL riêng không? | Kiểm thử bằng runtime identity, không chỉ trên laptop |
| Có chống ghi trùng/ghi đè khi chạy đồng thời không? | Khóa nghiệp vụ, versioned key, scheduler policy và idempotency |
| Khi permission denied, batch làm gì? | Fail rõ ràng, alert, sửa policy rồi restart; không skip hàng loạt |
| Có log/audit mà không lộ path/secret nhạy cảm không? | Whitelist trường log và phân quyền truy cập |
| Đã kiểm thử negative case và restart chưa? | Test đúng loại filesystem/volume/identity của production |

## 16. Những sai lầm điển hình

| Sai lầm | Hậu quả | Cách tiếp cận đúng |
| --- | --- | --- |
| `chmod -R 777` trên output root | Người dùng/process khác có thể sửa hoặc xóa output | Provision owner/group/ACL chỉ cho service cần thiết |
| Chạy batch dưới root/Admin chỉ để ghi file | Tăng phạm vi tác động khi job bị lỗi hoặc bị khai thác | Dùng service account ít quyền và sửa quyền trên resource |
| Dùng nguyên `outputPath` từ API request | Có nguy cơ path traversal hoặc ghi sai tenant/resource | Sinh path từ business key đã validate dưới root cố định |
| Chỉ kiểm tra `Files.isWritable` | Có thể pass preflight nhưng fail lúc ghi thật | Bắt và phân loại exception từ writer/API |
| Ghi output vào filesystem ephemeral của container | File mất khi Pod thay thế, restart không còn file | Dùng volume bền vững hoặc object storage phù hợp |
| Đổi UID giữa các lần chạy nhưng giữ file owner cũ | Writer restart không mở file được | Ổn định UID/GID hoặc chuẩn bị ACL trên volume |
| Chỉ cấp `s3:PutObject` rồi yêu cầu job delete/list | Thao tác cleanup/verify bị từ chối | Phân tích tất cả operations thực sự cần, cấp quyền hẹp |
| Cấp IAM wildcard hoặc DB quyền DDL cho runtime | Vượt nhu cầu, tăng blast radius | Tách migration/admin và runtime writer |
| Xóa file tạm ngay khi job lỗi | Mất output cần thiết cho restart | Cleanup theo vòng đời job instance và chính sách recovery |
| Dùng `appendAllowed(true)` để “sửa” lỗi file tồn tại | Có thể tạo output trùng khi chạy instance mới | Phân biệt restart với rerun; đặt tên/version và state ổn định |
| Coi `BatchStatus.COMPLETED` là bằng chứng publish | Có thể chưa move/upload/xác minh output cuối | Có manifest hoặc trạng thái publish được đối soát |
| Skip lỗi `IOException`/permission | Job xanh nhưng thiếu dữ liệu đầu ra | Fail, alert và restart sau khi sửa quyền |

## Kết luận

**Quyền ghi output resource** là một phần của an toàn dữ liệu, không chỉ là cấu hình để writer hết báo `Permission denied`. Spring Batch cần một identity đủ quyền trên **đúng** filesystem directory, DB table, object prefix hoặc endpoint; đồng thời ứng dụng phải giới hạn đường dẫn, tách output tạm khỏi output đã công bố và phân biệt quyền ghi/append/replace/delete.

Với batch cần restart, tài nguyên và quyền của nó phải tồn tại nhất quán qua các execution của cùng `JobInstance`. Một thiết kế thành công là thiết kế mà job **ghi được khi được phép, từ chối khi ngoài phạm vi, thất bại rõ ràng khi quyền bị chặn, và khôi phục được mà không mất hay nhân đôi dữ liệu**.

## Tài liệu tham khảo

- [Spring Batch Reference — Flat Files](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files.html): cấu hình `FlatFileItemWriter`, tài nguyên và các lựa chọn liên quan output.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): lưu trạng thái writer/reader cho restart qua `ExecutionContext`.
- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): transaction, chunk và xử lý lỗi khi ghi.
- [Oracle Java Tutorials — File and Directory Access](https://docs.oracle.com/javase/tutorial/essential/io/fileAttr.html): thao tác quyền và thuộc tính file trong Java NIO.
- [Kubernetes Documentation — Configure a Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/): `runAsUser`, `fsGroup` và quyền truy cập volume.
- [AWS IAM User Guide — Policies and Permissions](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html): giới hạn quyền theo action và resource.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): kiểm thử step/job, metadata và thất bại theo kịch bản.
