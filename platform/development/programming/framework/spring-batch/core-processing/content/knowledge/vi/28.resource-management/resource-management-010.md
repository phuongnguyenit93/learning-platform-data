# Quyền filesystem

Spring Batch thường đọc dữ liệu từ file và ghi kết quả, file lỗi hoặc báo cáo ra filesystem. Một reader có thể được cấu hình đúng, đường dẫn có thể tồn tại, nhưng Job vẫn thất bại nếu process chạy Spring Batch không có quyền truy cập cần thiết.

**Quyền filesystem** là quyền mà hệ điều hành cấp cho một user, group hoặc security principal đối với file và thư mục. Spring Batch không tự vượt qua các quyền này. Khi reader mở file, writer tạo file hoặc Job đổi tên output, thao tác được thực hiện dưới danh tính OS của process đang chạy ứng dụng.

Để xử lý đúng, cần xác định:

- Process chạy dưới user hoặc service account nào.
- File và tất cả thư mục cha có quyền phù hợp không.
- Reader cần quyền đọc hay writer cần quyền tạo, sửa, xóa và đổi tên.
- File nằm trên ổ đĩa cục bộ, network share, container volume hay mounted storage.
- Quyền có còn đúng khi Job restart hoặc chạy trên worker khác không.

Không nên giải quyết lỗi permission bằng cách cấp quyền rộng cho toàn bộ filesystem. Hãy cấp đúng quyền tối thiểu cho đúng thư mục và danh tính chạy Batch.

## 1. Filesystem permission là gì?

Hệ điều hành kiểm soát ai được phép truy cập một đối tượng filesystem và được phép thực hiện thao tác nào.

Các đối tượng thường gặp:

- File đầu vào mà reader cần mở.
- Thư mục chứa file đầu vào.
- Thư mục output mà writer cần tạo file.
- Thư mục staging hoặc thư mục tạm.
- Thư mục lưu file rejected, archive và log.
- File lock hoặc marker mà Job tạo trong quá trình xử lý.

Một quyền có thể cho phép đọc file nhưng không cho phép truy cập thư mục cha. Ngược lại, process có thể liệt kê thư mục nhưng không được đọc nội dung một file cụ thể.

Vì vậy, kiểm tra quyền của riêng file chưa đủ. Cần xem cả đường dẫn từ thư mục gốc tới file và các thao tác mà ứng dụng sẽ thực hiện.

## 2. Quyền read, write và execute trên POSIX

Trên Linux và các hệ thống Unix-like, quyền truyền thống được biểu diễn bằng ba nhóm:

- Owner: user sở hữu đối tượng.
- Group: group sở hữu đối tượng.
- Others: các user còn lại.

Mỗi nhóm có thể có quyền read, write và execute.

| Quyền | Trên file | Trên directory |
|---|---|---|
| r — read | Đọc nội dung file | Liệt kê tên entry trong thư mục |
| w — write | Thay đổi nội dung file | Tạo, xóa hoặc đổi tên entry trong thư mục |
| x — execute | Chạy file nếu đó là executable | Traverse/search: đi qua thư mục và truy cập entry theo tên |

Điểm dễ nhầm nhất là quyền execute của directory. Để mở một file bằng đường dẫn, process thường cần quyền search/execute trên mọi thư mục cha của file đó.

Ví dụ:

~~~text
/data
  |
  +-- batch
        |
        +-- input
              |
              +-- orders.csv
~~~

Để đọc orders.csv, user chạy Batch cần:

- Quyền traverse trên /data, /data/batch và /data/batch/input.
- Quyền read trên orders.csv.
- Các quyền bổ sung nếu ứng dụng cần liệt kê, kiểm tra hoặc đổi tên file.

Để tạo file mới trong input, process cần quyền write và execute trên thư mục input. Chỉ có quyền write trên một file đã tồn tại không đủ để tạo một file khác trong cùng thư mục.

## 3. Quyền cần thiết cho từng thao tác

Các thao tác của Spring Batch có yêu cầu quyền khác nhau.

| Thao tác | Quyền thường cần |
|---|---|
| Mở file input để đọc | Read trên file, traverse trên thư mục cha |
| Liệt kê file trong thư mục | Read và execute trên directory |
| Tạo file output mới | Write và execute trên directory cha |
| Ghi vào file output có sẵn | Write trên file và traverse trên đường dẫn |
| Xóa file | Write và execute trên directory chứa file; chính sách sticky bit/ACL có thể ảnh hưởng |
| Đổi tên hoặc move file | Quyền phù hợp trên thư mục nguồn và đích |
| Tạo file tạm | Write và execute trên thư mục tạm |
| Tạo lock file | Write và execute trên thư mục chứa lock |
| Đọc file rejected/archive | Read trên file và traverse trên thư mục cha |

Trên POSIX, xóa file chủ yếu được quyết định bởi quyền trên thư mục chứa entry, không chỉ quyền write của file. Đây là lý do một file có thể không writable nhưng vẫn bị user có quyền trên thư mục xóa hoặc đổi tên.

Các hệ thống ACL, sticky bit, mount option và policy bảo mật có thể bổ sung điều kiện. Khi chẩn đoán, cần xét quyền hiệu lực chứ không chỉ nhìn một bit mode.

## 4. Xác định process chạy dưới danh tính nào

Quyền filesystem được kiểm tra theo danh tính của process thực hiện thao tác.

Trong môi trường phát triển, ứng dụng có thể chạy bằng tài khoản người đăng nhập. Khi triển khai, cùng ứng dụng có thể chạy dưới:

- Linux service account.
- Windows service account.
- Container UID/GID.
- Kubernetes service workload với security context.
- User của application server hoặc scheduler.
- Tài khoản riêng của batch worker.

Ví dụ, file được tạo bởi user deploy nhưng Job chạy bằng user batch-runner. Nếu file chỉ cho phép owner deploy đọc và group không có quyền, reader sẽ nhận lỗi AccessDeniedException hoặc IOException.

Không nên suy ra danh tính runtime từ tài khoản đang mở IDE hoặc terminal. Hãy kiểm tra user thực tế của service, container hoặc worker.

## 5. Kiểm tra quyền trên Linux

Một số lệnh hữu ích:

~~~bash
id
whoami
ls -ld /data /data/batch /data/batch/input
ls -l /data/batch/input/orders.csv
namei -l /data/batch/input/orders.csv
~~~

Các lệnh cho biết:

- User và group hiện tại.
- Owner/group và mode của từng file hoặc directory.
- Quyền traverse trên từng thành phần của đường dẫn.
- Thành phần nào có thể chặn truy cập.

Ví dụ:

~~~text
drwxr-x--- batch batch /data/batch
drwxr-x--- batch batch /data/batch/input
-rw-r----- batch batch orders.csv
~~~

Nếu process chạy với user batch và thuộc group batch, cấu hình trên có thể cho phép đọc file và traverse thư mục. Một user ngoài group có thể không truy cập được.

Kết quả của ls không phải lúc nào cũng cho biết toàn bộ quyền hiệu lực nếu có POSIX ACL, SELinux, AppArmor hoặc mount policy. Có thể cần kiểm tra ACL và security policy tương ứng.

## 6. Cấp quyền tối thiểu trên Linux

Một cách quản lý thường dùng là tạo group chuyên dụng cho batch, đặt owner/group cho thư mục dữ liệu và cấp quyền theo nhu cầu.

Ví dụ:

~~~bash
sudo groupadd batch-data
sudo usermod -aG batch-data batch-runner
sudo chown -R batch-runner:batch-data /data/batch
sudo chmod 750 /data/batch
sudo chmod 750 /data/batch/input
sudo chmod 640 /data/batch/input/orders.csv
~~~

Ý nghĩa của ví dụ:

- batch-runner là owner.
- batch-data là group dùng chung.
- Owner có quyền đọc/ghi/traverse phù hợp.
- Group có quyền đọc và traverse.
- Others không được truy cập.

Lệnh và giá trị mode cần điều chỉnh theo chính sách thực tế. Không chạy chmod hoặc chown đệ quy trên thư mục rộng nếu chưa xác định chính xác phạm vi, vì có thể thay đổi quyền của file không liên quan.

Không dùng chmod 777 như cách sửa lỗi mặc định. Nó cấp quyền rộng cho mọi user và có thể cho phép sửa hoặc thay thế file input/output.

## 7. Umask ảnh hưởng quyền file mới

Khi process tạo file hoặc directory mới, quyền mode yêu cầu được kết hợp với umask của process. Vì vậy, file output có thể có permission khác với giá trị ứng dụng truyền vào.

Ví dụ umask 0027 thường loại bỏ quyền write của group và mọi quyền của others khỏi mode được yêu cầu.

~~~bash
umask
~~~

Nếu writer tạo file output mà group downstream cần đọc, hãy xác định umask của service và quyền mặc định mong muốn. Có thể dùng setgid trên thư mục hoặc ACL mặc định để file mới thừa hưởng group/quyền phù hợp.

Không nên giả định file mới luôn thuộc group của người dùng hoặc luôn có mode giống file input. Kiểm tra owner, group và permission sau khi tạo output.

## 8. ACL và quyền hiệu lực

POSIX mode bits không phải cơ chế duy nhất. Access Control List (ACL) cho phép cấp quyền chi tiết hơn cho user hoặc group cụ thể.

Ví dụ:

~~~bash
getfacl /data/batch/input
setfacl -m u:batch-runner:rx /data/batch/input
setfacl -m u:batch-runner:r-- /data/batch/input/orders.csv
~~~

ACL hữu ích khi không muốn thay đổi owner/group chính của thư mục nhưng cần cấp quyền cho một service account.

Khi có ACL, quyền hiển thị bằng ls có thể chứa dấu +. Cần kiểm tra ACL và mask vì mask giới hạn quyền hiệu lực của các entry ACL.

Với thư mục dùng chung, default ACL có thể áp dụng cho file hoặc thư mục con được tạo mới. Hãy kiểm tra cả ACL hiện tại và default ACL nếu output file được tạo trong lúc Job chạy.

## 9. Quyền filesystem trên Windows

Windows sử dụng Access Control List (ACL) và security principal để quyết định quyền truy cập. Một file hoặc directory có thể có quyền được kế thừa từ thư mục cha và các entry riêng.

Các quyền thường gặp:

- Read: đọc nội dung hoặc metadata.
- Write: tạo hoặc sửa nội dung.
- Modify: đọc, ghi, xóa và sửa đối tượng trong phạm vi được cấp.
- Read & execute: đọc và thực thi file, traverse directory.
- List folder contents: liệt kê nội dung directory.
- Delete: xóa đối tượng hoặc entry theo ACL.
- Full control: quyền quản trị rộng hơn, bao gồm thay đổi quyền và owner theo policy.

Có thể xem ACL bằng PowerShell:

~~~powershell
Get-Acl 'D:\batch\input\orders.csv' | Format-List
icacls 'D:\batch\input\orders.csv'
icacls 'D:\batch\input'
whoami
~~~

Nếu ứng dụng chạy như Windows Service, hãy kiểm tra Log On As của service. Quyền của user đang mở PowerShell không chứng minh service account có cùng quyền.

Windows cũng có thể truy cập file qua network share. Khi đó, quyền truy cập hiệu lực chịu ảnh hưởng cả share permissions lẫn NTFS permissions; quyền thực tế thường là phần giao nhau của hai lớp quyền.

## 10. Đường dẫn file và working directory

Một đường dẫn tương đối được giải quyết theo working directory của process. Working directory khi chạy từ IDE có thể khác khi chạy từ service, scheduler hoặc container.

Ví dụ:

~~~java
Resource resource = new FileSystemResource("input/orders.csv");
~~~

Đường dẫn này không nhất thiết trỏ tới thư mục dự án. Nếu service khởi động với working directory khác, reader có thể báo file không tồn tại hoặc mở nhầm file.

Với file vận hành, nên dùng đường dẫn tuyệt đối hoặc cấu hình đường dẫn gốc rõ ràng:

~~~properties
batch.input.directory=/data/batch/input
batch.output.directory=/data/batch/output
~~~

Sau đó ghép đường dẫn từ cấu hình đã được kiểm soát. Tránh dựa vào vị trí hiện tại của terminal hoặc thư mục chứa JAR.

Phân biệt lỗi "NoSuchFileException" với "AccessDeniedException". Một đường dẫn sai, một thư mục cha không có quyền traverse và một file không có quyền read là các nguyên nhân khác nhau.

## 11. Spring Resource không vượt qua quyền OS

Spring Resource là abstraction để truy cập tài nguyên, ví dụ:

- FileSystemResource: file trên filesystem.
- ClassPathResource: tài nguyên nằm trên classpath.
- UrlResource: tài nguyên qua URL.
- InputStreamResource: stream được cung cấp bởi ứng dụng.

Ví dụ:

~~~java
Resource input = new FileSystemResource(inputPath);

try (InputStream stream = input.getInputStream()) {
    // Đọc nội dung.
}
~~~

Resource abstraction giúp code không phụ thuộc hoàn toàn vào một cách biểu diễn tài nguyên, nhưng không cấp thêm quyền OS. Nếu process không được phép đọc file, FileSystemResource vẫn không thể mở file đó.

ClassPathResource cũng có semantics khác file vận hành. Tài nguyên đóng gói bên trong JAR thường không phải file có thể ghi trực tiếp. Không dùng classpath resource làm output directory.

Nếu cần tạo output, dùng FileSystemResource hoặc API Path/Files trỏ tới thư mục được cấp quyền ghi.

## 12. Cấu hình FlatFileItemReader và quyền đọc

Ví dụ reader đọc CSV:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("id", "orderNumber", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

Để reader mở được file, process cần:

- Quyền traverse trên tất cả thư mục cha.
- Quyền read trên file.
- Quyền truy cập vào mount hoặc volume chứa file.
- Nguồn file tồn tại tại thời điểm reader mở resource.

Nếu reader cần liệt kê file trước khi chọn input, thư mục chứa file còn cần quyền list/read và traverse phù hợp.

Không chỉ kiểm tra quyền lúc khởi chạy. File có thể bị thay owner, thay ACL, bị rotate hoặc bị di chuyển trước khi Step thực sự mở resource.

## 13. Cấu hình FlatFileItemWriter và quyền ghi

Writer tạo output file cần quyền trên thư mục đích. Ví dụ:

~~~java
@Bean
@StepScope
public FlatFileItemWriter<OrderResult> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<OrderResult>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .names("id", "orderNumber", "status")
            .shouldDeleteIfExists(true)
            .saveState(true)
            .build();
}
~~~

Trước khi dùng shouldDeleteIfExists(true), cần bảo đảm chính sách output cho phép xóa file cũ. Nếu process không có quyền xóa file hoặc quyền trên thư mục chứa entry, writer có thể thất bại dù có quyền ghi file.

Các yêu cầu thường gặp:

- Thư mục cha có write và execute để tạo file.
- File cũ có thể cần quyền xóa/replace tùy chế độ.
- Nếu append, file hiện có cần quyền write.
- Nếu tạo file tạm rồi rename, cần quyền phù hợp trên cả thư mục nguồn và đích.
- User downstream cần quyền đọc output sau khi Job hoàn tất.

Tên file output nên được kiểm soát. Không lấy path tùy ý từ dữ liệu đầu vào mà không xác thực.

## 14. Tạo thư mục trước khi chạy Job

Một lỗi phổ biến là writer được cấu hình với output path nhưng thư mục cha chưa tồn tại.

Có thể tạo thư mục trước khi khởi chạy:

~~~java
Path outputDirectory =
        Paths.get(configuredOutputDirectory);

Files.createDirectories(outputDirectory);

if (!Files.isDirectory(outputDirectory)
        || !Files.isWritable(outputDirectory)) {
    throw new IllegalStateException(
            "Output directory is not writable: " + outputDirectory);
}
~~~

Files.createDirectories tạo các thư mục cha còn thiếu nếu process có quyền phù hợp.

Files.isWritable là kiểm tra sơ bộ, không bảo đảm lần ghi sau chắc chắn thành công. Quyền có thể thay đổi, quota có thể hết, mount có thể mất hoặc file system có thể chuyển sang read-only sau lần kiểm tra.

Nếu cần xác nhận quyền thực tế, hãy thực hiện thao tác tạo file thử trong một thư mục riêng đã được thiết kế cho health check, rồi xóa file đó. Không tạo file thử trong thư mục dữ liệu nghiệp vụ nếu có thể gây nhầm lẫn với Job.

## 15. File tạm, staging và atomic publish

Một quy trình an toàn thường ghi output vào file tạm hoặc staging rồi chỉ công bố khi Job hoàn tất.

~~~text
Output directory
      |
      +--> report.csv.tmp
              |
              v
        Writer ghi các chunk
              |
              v
        Job hoàn tất thành công
              |
              v
        Rename thành report.csv
              |
              v
        Consumer đọc report.csv
~~~

Việc đổi tên trong cùng filesystem thường có thể thực hiện atomic theo semantics của filesystem, nếu filesystem hỗ trợ và điều kiện quyền phù hợp. Java có thể yêu cầu atomic move:

~~~java
Files.move(
        temporaryFile,
        finalFile,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
~~~

ATOMIC_MOVE có thể không được hỗ trợ giữa hai filesystem hoặc trên một số network filesystem. Khi không hỗ trợ, ứng dụng cần xử lý rõ ngoại lệ và có chiến lược publish thay thế. Không giả định move giữa hai volume là atomic.

Process thường cần quyền ghi trên thư mục đích và quyền xóa entry khỏi thư mục nguồn. Nếu final file đã tồn tại, việc replace còn phụ thuộc quyền và policy trên entry đích.

## 16. Quyền cho archive và rejected files

Batch Job thường chuyển file đầu vào sang archive hoặc lưu record lỗi sau khi xử lý.

Ví dụ thư mục:

~~~text
/data/batch/
    input/
    processing/
    output/
    archive/
    rejected/
    temp/
~~~

Hãy xác định quyền theo vai trò:

| Thư mục | Quyền của batch process |
|---|---|
| input | Traverse và read; có thể cần quyền move nếu lấy file khỏi inbox |
| processing | Read/write nếu Job chuyển file vào đây |
| output | Create/write; có thể cần rename/delete |
| archive | Create hoặc move file đã xử lý |
| rejected | Create/write file lỗi hoặc báo cáo |
| temp | Create/read/write/delete file tạm |

Nếu một service khác cần đọc output hoặc archive, hãy cấp group/ACL read cho service đó thay vì mở quyền cho mọi user.

Có thể dùng group chung hoặc default ACL để các file mới được tạo ra có quyền phù hợp với consumer. Kiểm tra umask và inheritance để tránh file mới có quyền quá hẹp hoặc quá rộng.

## 17. Quyền filesystem trong container

Trong container, UID/GID của process có thể khác UID/GID trên host. Một thư mục trên host được mount vào container vẫn giữ ownership và permission theo cách filesystem/volume driver cung cấp.

Ví dụ container chạy với user 10001 nhưng thư mục host thuộc owner 1000 và chỉ owner được ghi. Writer có thể nhận Permission denied.

Các điểm cần kiểm tra:

- Container process đang chạy với UID/GID nào.
- Volume được mount read-only hay read-write.
- Ownership và mode của thư mục trên host.
- fsGroup hoặc securityContext nếu dùng Kubernetes.
- User namespace hoặc rootless container mapping.
- SELinux label hoặc policy của host.
- Storage driver có hỗ trợ chmod/chown hay không.

Kubernetes có thể dùng securityContext và fsGroup để cấp quyền truy cập volume cho group phù hợp. Hành vi cụ thể phụ thuộc loại volume và cấu hình cluster. Không mặc định fsGroup sẽ sửa được mọi loại volume hoặc ACL.

Không chạy container bằng root chỉ để bỏ qua lỗi permission nếu không có yêu cầu vận hành rõ ràng. Hãy cấu hình UID/GID và quyền volume đúng với service account của ứng dụng.

## 18. Network share và mounted filesystem

File có thể nằm trên NFS, SMB hoặc storage được mount từ xa. Khi đó, quyền truy cập chịu ảnh hưởng của cả filesystem phía server và cấu hình client.

Một số nguyên nhân thường gặp:

- NFS export map UID/GID khác với client.
- Root squash khiến root trong container không có quyền như mong đợi.
- SMB share permissions và NTFS ACL không tương thích.
- Credential hoặc ticket truy cập share hết hạn.
- Mount được cấu hình read-only.
- Network filesystem mất kết nối hoặc stale handle.
- Locking và rename semantics khác filesystem cục bộ.

Với output cần publish atomic, cần xác minh filesystem từ xa hỗ trợ semantics cần thiết. Với reader restart, cần bảo đảm file không bị thay thế hoặc thay đổi trong lúc Job tạm dừng.

Nên chạy thử thao tác dưới đúng service identity trên đúng mount mà Job sử dụng. Một lệnh chạy trên máy developer hoặc một mount khác không chứng minh quyền runtime đã đúng.

## 19. Quyền file khi Job restart

Restart có thể xảy ra sau khi quyền filesystem đã thay đổi.

Ví dụ:

1. Lần chạy đầu reader mở được file và commit một số chunk.
2. Job thất bại.
3. Administrator đổi ACL hoặc file được chuyển sang archive.
4. Job restart dùng checkpoint cũ.
5. Reader không thể mở file hoặc không thể seek tới vị trí đã lưu.

Checkpoint chỉ lưu trạng thái đọc; nó không lưu quyền truy cập và không giữ file descriptor sống qua process restart.

Để restart đáng tin cậy:

- Giữ input file bất biến và ở vị trí ổn định.
- Giữ quyền read/traverse cho service identity trong toàn bộ thời gian restart có thể xảy ra.
- Không xóa hoặc thay file khi Job còn ở trạng thái có thể restart.
- Giữ quyền ghi trên thư mục output/staging nếu writer cần tiếp tục.
- Kiểm tra quyền và fingerprint của resource khi Step mở lại.

Nếu file đầu vào đã được chuyển sang archive sau khi Job thất bại, hãy xác định rõ restart phải đọc từ archive path hay cần khôi phục file về vị trí ban đầu. Đừng để một workflow khác di chuyển file khi Job còn đang chạy hoặc chờ restart.

## 20. Không dựa hoàn toàn vào Files.isReadable và isWritable

Java NIO cung cấp:

~~~java
Files.isReadable(path);
Files.isWritable(path);
Files.isExecutable(path);
~~~

Các phương thức này hữu ích cho kiểm tra sơ bộ nhưng có một số giới hạn:

- Chúng không chứng minh thao tác tiếp theo chắc chắn thành công.
- Quyền có thể thay đổi giữa lúc check và lúc open/write.
- ACL, mount, quota hoặc network state có thể ảnh hưởng.
- Một số filesystem không cung cấp đầy đủ thông tin quyền.
- isWritable trên file không chứng minh thư mục cha cho phép tạo file mới.

Đây là dạng time-of-check to time-of-use (TOCTOU): trạng thái được kiểm tra có thể thay đổi trước khi thao tác thật diễn ra.

Hãy xem thao tác mở, tạo hoặc ghi file thực tế là kết quả cuối cùng. Bắt và phân loại IOException, AccessDeniedException hoặc FileSystemException với đường dẫn và operation tương ứng.

## 21. Bảo vệ đường dẫn khỏi path traversal

Nếu tên file đến từ JobParameters hoặc dữ liệu bên ngoài, không ghép trực tiếp chuỗi tùy ý vào thư mục gốc.

Ví dụ đầu vào không an toàn:

~~~java
Path target = outputRoot.resolve(requestedFileName);
~~~

Nếu requestedFileName chứa ../ hoặc đường dẫn tuyệt đối, target có thể thoát khỏi outputRoot.

Có thể chuẩn hóa và xác minh:

~~~java
Path root = outputRoot.toAbsolutePath().normalize();
Path target = root.resolve(requestedFileName).normalize();

if (!target.startsWith(root)) {
    throw new IllegalArgumentException(
            "Output path is outside the allowed directory");
}
~~~

Kiểm tra này giúp chặn traversal theo đường dẫn chuẩn hóa. Nếu môi trường cho phép symlink không tin cậy, cần xem xét thêm real path, quyền trên symlink/target và khả năng thay symlink giữa lúc kiểm tra và mở file.

Tốt hơn là nhận một logical file ID hoặc tên đã được whitelist thay vì cho caller truyền path tùy ý. Chỉ cho phép Job ghi trong các thư mục được cấu hình.

## 22. Symlink và file được thay thế

Symlink có thể khiến một đường dẫn nằm trong thư mục được phép nhưng trỏ tới file ở vị trí khác. Quyền truy cập cuối cùng còn phụ thuộc target và các thư mục dẫn tới target.

Trong môi trường xử lý file không tin cậy:

- Không theo symlink ngoài phạm vi nếu nghiệp vụ không cho phép.
- Kiểm tra loại file và target theo chính sách.
- Hạn chế quyền tạo symlink trong thư mục staging.
- Dùng thư mục do service sở hữu và không cho user không tin cậy sửa entry.
- Cẩn thận với race condition giữa lúc validate path và lúc mở file.

Java NIO có các tùy chọn như LinkOption.NOFOLLOW_LINKS cho một số thao tác. Chúng không tự giải quyết mọi race condition, nhưng có thể giúp từ chối symlink trong những bước kiểm tra phù hợp.

Không mở file dựa trên path do user không tin cậy cung cấp nếu process có quyền truy cập rộng hơn user đó.

## 23. Quyền file lock và chạy nhiều Job

Một số ứng dụng dùng lock file để ngăn hai Job xử lý cùng một input. Khi tạo hoặc xóa lock file, process cần quyền phù hợp trên thư mục chứa lock.

Ví dụ:

~~~text
processing/
    orders.csv
    orders.csv.lock
~~~

Nếu batch-runner có quyền read input nhưng không có quyền write trên processing directory, Job có thể đọc file nhưng không tạo được lock.

Cũng cần xác định lock file được tạo bởi user nào và có thể được xóa bởi process restart hay không. Nếu file lock còn sót lại, cần quy trình kiểm tra owner, thời gian và trạng thái Job trước khi xóa.

Filesystem lock không phải lúc nào cũng đáng tin trên mọi network filesystem. Nếu nhiều node chạy Job, có thể cần distributed lock hoặc cơ chế claim file có tính nguyên tử được storage hỗ trợ.

## 24. Chẩn đoán lỗi permission trong Spring Batch

Một số exception thường gặp:

- AccessDeniedException: thao tác bị từ chối do quyền.
- FileSystemException: lỗi filesystem tổng quát, có thể kèm reason.
- NoSuchFileException: file hoặc một thành phần đường dẫn không tồn tại.
- FileNotFoundException: file không tìm thấy hoặc không mở được; trên một số môi trường thông tin lỗi có thể không phân biệt rõ nguyên nhân.
- IOException: lỗi I/O tổng quát.

Khi log lỗi, nên ghi:

- Job name và JobExecution ID.
- Step name và StepExecution ID.
- Partition name nếu có.
- Operation: open, read, create, write, delete hoặc move.
- Đường dẫn đã chuẩn hóa, nếu không chứa dữ liệu nhạy cảm.
- User/UID của process hoặc service identity.
- Exception class và nguyên nhân gốc.

Không log nội dung file nhạy cảm hoặc toàn bộ JobParameters nếu có credential. Chỉ ghi thông tin cần thiết để xác định file và thao tác thất bại.

## 25. Kiểm tra quyền từ chính process chạy Batch

Một bài kiểm tra chạy dưới user developer không đại diện cho quyền của service.

Có thể tạo một health check hoặc startup validation trong ứng dụng để kiểm tra các thư mục cấu hình:

~~~java
public void validateDirectory(Path directory) throws IOException {
    Files.createDirectories(directory);

    if (!Files.isDirectory(directory)) {
        throw new IllegalStateException(
                "Not a directory: " + directory);
    }

    Path probe = Files.createTempFile(
            directory,
            ".batch-permission-check-",
            ".tmp");

    try {
        Files.writeString(
                probe,
                "permission check",
                StandardOpenOption.TRUNCATE_EXISTING);
    } finally {
        Files.deleteIfExists(probe);
    }
}
~~~

Ví dụ này kiểm tra khả năng tạo, ghi và xóa file tạm dưới process identity hiện tại. Chỉ dùng trong thư mục health-check được dành riêng cho ứng dụng, không chạy trên thư mục input có thể bị consumer hiểu nhầm.

Đối với input file, có thể thử mở stream ở bước kiểm tra resource. Tuy nhiên, hãy tránh mở cùng file theo cách làm ảnh hưởng reader, lock hoặc vị trí đọc. Kiểm tra thực tế nên nằm trong bước chuẩn bị trước khi Step bắt đầu.

## 26. Quyền tối thiểu và phân tách thư mục

Một thiết kế dễ vận hành là phân tách thư mục theo mục đích và cấp quyền riêng.

~~~text
/data/customer-batch/
    inbox/       # nguồn gửi file vào
    processing/  # file đang được Job claim
    output/      # kết quả thành công
    rejected/    # báo cáo hoặc dữ liệu lỗi
    archive/     # input đã xử lý
    temp/        # file tạm và staging
~~~

Ví dụ chính sách:

| Actor | Inbox | Processing | Output | Archive | Rejected |
|---|---|---|---|---|---|
| File producer | Create/write | Không cần | Không cần | Không cần | Không cần |
| Batch runner | Read/move | Read/write | Create/write | Create/move | Create/write |
| Downstream consumer | Không cần | Không cần | Read | Tùy nhu cầu | Read theo policy |
| Operator | Read theo policy | Inspect | Read | Read | Read |

Phân tách này giảm khả năng một producer ghi đè output hoặc một consumer xóa input đang được xử lý. Quyền thực tế nên được áp dụng bằng owner/group/ACL và kiểm thử dưới đúng service identity.

## 27. Những lỗi thường gặp

### File tồn tại nhưng reader vẫn không mở được

Có thể process thiếu quyền read trên file hoặc execute/traverse trên một thư mục cha. Kiểm tra toàn bộ đường dẫn và user runtime.

### Có quyền read file nhưng không traverse được directory

Trên POSIX, thiếu execute trên thư mục cha có thể chặn truy cập file theo path. Cấp quyền search/traverse phù hợp.

### Writer báo permission denied dù file chưa tồn tại

Tạo file cần write và execute trên thư mục cha. Quyền write trên một file khác trong thư mục không đủ.

### Chạy trong IDE thành công nhưng Windows/Linux service thất bại

Service chạy bằng danh tính khác. Kiểm tra Log On As hoặc UID/GID của process thật.

### Container có quyền root nhưng volume vẫn không ghi được

Volume có thể được mount read-only, UID mapping khác, ACL/SELinux chặn hoặc storage driver áp dụng policy riêng.

### Output file có quyền quá rộng hoặc quá hẹp

Kiểm tra umask, default ACL, group inheritance và quyền consumer cần. Không cấp quyền 777 để tránh xử lý ownership.

### File bị khóa hoặc không thể rename

Một process khác có thể đang mở file, share mode không cho delete/rename hoặc filesystem từ xa có semantics riêng. Xác định owner và lifecycle file.

### Job restart không mở lại được input

File đã bị move, xóa, thay thế hoặc ACL đã thay đổi. Giữ nguồn bất biến và quyền truy cập trong thời gian restart.

### Files.isWritable trả true nhưng writer vẫn thất bại

Quyền có thể thay đổi, quota hết, mount read-only hoặc directory khác với path thực tế. Thử thao tác thực tế và log nguyên nhân gốc.

### Dùng path từ dữ liệu đầu vào mà không kiểm tra

Path traversal hoặc symlink có thể khiến Job đọc/ghi ngoài thư mục được phép. Chuẩn hóa, giới hạn root và kiểm soát symlink.

## 28. Quy trình cấp và xác minh quyền filesystem

Trước khi triển khai Job đọc/ghi file, hãy xác định:

1. Process chạy bằng user, group hoặc service account nào?
2. Input file có tồn tại và bất biến trong suốt vòng đời restart không?
3. Mọi thư mục cha có quyền traverse phù hợp không?
4. Reader có quyền read trên file không?
5. Writer có quyền create/write trên thư mục output không?
6. Có cần delete, replace, rename hoặc move file không?
7. File mới sẽ có owner, group, mode và ACL như thế nào?
8. Volume có read-only, UID mapping hoặc network policy riêng không?
9. Các thư mục temp, rejected, archive và lock có quyền phù hợp không?
10. Path có được giới hạn trong thư mục cho phép và chống traversal không?
11. Health check có chạy dưới đúng process identity không?
12. Job restart có còn truy cập được đúng file và đúng checkpoint không?

Quyền filesystem là một phần của cấu hình vận hành Job. Reader cần quyền đọc file và traverse đường dẫn; writer cần quyền tạo hoặc sửa entry trong thư mục đích; thao tác archive, delete và atomic publish cần thêm quyền phù hợp trên thư mục liên quan. Khi cấp quyền tối thiểu cho đúng service identity, giữ nguồn ổn định qua restart và kiểm tra thao tác dưới đúng runtime, Spring Batch có thể đọc/ghi tài nguyên một cách an toàn và dễ chẩn đoán.
