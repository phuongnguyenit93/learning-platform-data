# Mở file input và output trong reader, writer

Trong Spring Batch, file đầu vào và đầu ra thường được quản lý thông qua abstraction `Resource` của Spring. `ItemReader` mở file để đọc dữ liệu, còn `ItemWriter` mở file để ghi kết quả. Với các thành phần file có hỗ trợ `ItemStream`, Spring Batch quản lý vòng đời mở, cập nhật checkpoint và đóng tài nguyên theo vòng đời của Step.

Khi đường dẫn file thay đổi theo từng lần chạy, có thể lấy nó từ JobParameters bằng `@Value` và khai báo bean `@StepScope`. Cách này giúp mỗi StepExecution nhận đúng file của JobExecution hiện tại, đồng thời cho phép reader/writer lưu trạng thái phục vụ restart.

## 1. Resource abstraction trong Spring

Spring dùng interface `Resource` để biểu diễn một nguồn dữ liệu. Các implementation thường gặp:

| Resource | Nguồn | Trường hợp phù hợp |
|---|---|---|
| `FileSystemResource` | File trên filesystem | Đọc file đầu vào hoặc ghi file đầu ra ở một đường dẫn cụ thể. |
| `ClassPathResource` | Tài nguyên nằm trên classpath | Đọc file mẫu hoặc dữ liệu đóng gói cùng ứng dụng. |
| `UrlResource` | Tài nguyên qua URL | Đọc nội dung từ URL khi reader và hạ tầng hỗ trợ. |
| `ByteArrayResource` | Mảng byte trong memory | Dữ liệu nhỏ đã có sẵn trong bộ nhớ. |

Ví dụ tạo resource cho file hệ thống:

```java
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;

Resource inputResource =
        new FileSystemResource("/data/in/orders.csv");
```

`Resource` mô tả vị trí và cách truy cập dữ liệu. Nó không tự quyết định định dạng CSV, encoding, mapping field hay cách restart. Những việc đó do Reader/Writer và cấu hình tương ứng đảm nhiệm.

Với file output, nên dùng `FileSystemResource` trỏ tới một đường dẫn có quyền ghi. `ClassPathResource` thường phù hợp để đọc tài nguyên đóng gói trong ứng dụng; không nên dùng nó làm nơi ghi kết quả vì tài nguyên trong JAR hoặc classpath có thể không writable.

## 2. Vòng đời mở và đóng file của ItemStream

Nhiều Reader và Writer của Spring Batch triển khai `ItemStream`. Interface này có ba callback chính:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

- `open()` được gọi khi Step bắt đầu để mở file và khôi phục trạng thái đã lưu nếu có.
- `update()` được gọi tại các điểm lưu trạng thái phù hợp, thường gắn với ranh giới commit của chunk, để ghi checkpoint vào `ExecutionContext`.
- `close()` được gọi khi Step kết thúc để giải phóng file handle, stream và tài nguyên liên quan.

Với `FlatFileItemReader` và `FlatFileItemWriter`, thông thường không cần tự gọi `open()` hoặc `close()` trong Tasklet. Spring Batch quản lý vòng đời của Reader/Writer khi chúng được đăng ký trực tiếp trong Step.

```text
Step bắt đầu
    |
    v
Reader.open(context) / Writer.open(context)
    |
    v
Đọc và ghi các chunk
    |
    +--> update(context) tại điểm lưu checkpoint
    |
    v
Step kết thúc hoặc thất bại
    |
    v
Reader.close() / Writer.close()
```

Nếu Reader hoặc Writer được bọc bên trong một component tùy chỉnh, component đó cần chuyển tiếp `ItemStream` lifecycle hoặc đăng ký delegate bằng `.stream(...)` trên Step builder. Nếu không, delegate có thể không được mở, cập nhật checkpoint hoặc đóng đúng cách.

## 3. Mở file input bằng FlatFileItemReader

`FlatFileItemReader` đọc file văn bản theo từng dòng và ánh xạ field thành object. Builder thường dùng là `FlatFileItemReaderBuilder`.

```java
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.core.io.FileSystemResource;

FlatFileItemReader<Order> reader =
        new FlatFileItemReaderBuilder<Order>()
                .name("orderReader")
                .resource(new FileSystemResource("/data/in/orders.csv"))
                .encoding("UTF-8")
                .delimited()
                .names("orderId", "customerId", "amount")
                .targetType(Order.class)
                .linesToSkip(1)
                .saveState(true)
                .build();
```

Các cấu hình quan trọng:

- `name(...)`: tên ổn định của reader, được dùng khi lưu state vào ExecutionContext.
- `resource(...)`: file nguồn cần đọc.
- `encoding(...)`: charset của file; nên khai báo rõ thay vì phụ thuộc encoding mặc định của máy chạy.
- `delimited()`: chọn cách phân tách field; `names(...)` xác định tên cột.
- `targetType(...)`: kiểu object được tạo từ mỗi dòng.
- `linesToSkip(1)`: bỏ qua dòng header nếu file có header.
- `saveState(true)`: cho phép lưu trạng thái đọc để restart.

Ví dụ giả định file CSV có ba cột `orderId`, `customerId`, `amount` và dòng đầu là header. Với CSV có dấu phẩy nằm trong dấu ngoặc kép, dấu quote hoặc newline trong field, cần cấu hình tokenizer phù hợp và kiểm tra định dạng file thực tế.

## 4. Mở file input từ JobParameters

Trong nhiều Job, file đầu vào thay đổi theo từng lần chạy. Có thể truyền đường dẫn bằng JobParameters và dùng `@StepScope` để late-bind giá trị khi Step bắt đầu:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("inputFile is required");
    }

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .encoding("UTF-8")
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .linesToSkip(1)
            .strict(true)
            .saveState(true)
            .build();
}
```

`@StepScope` giúp reader nhận đúng `inputFile` của StepExecution hiện tại. `strict(true)` yêu cầu reader báo lỗi nếu resource không tồn tại hoặc không thể mở theo chính sách của reader. Đây là hành vi hữu ích cho file bắt buộc; nếu file tùy chọn, nên xử lý trường hợp thiếu file bằng một validation Step hoặc flow rõ ràng.

Khi launch Job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/in/orders-2026-11-15.csv", true)
        .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
```

Nếu Job cần restart, hãy dùng lại identifying parameter `inputFile` và bảo đảm nội dung file ở đường dẫn đó vẫn là dữ liệu của lần chạy ban đầu. Tốt hơn nữa, dùng file bất biến theo batch ID hoặc lưu checksum/version của file để tránh đọc nhầm nội dung đã bị thay thế.

## 5. Kiểm tra file input trước khi Step chạy

Reader thường phát hiện lỗi mở file khi `open()` được gọi. Nếu muốn báo lỗi rõ ràng trước khi bắt đầu xử lý dữ liệu, có thể tạo một validation Step kiểm tra đường dẫn, quyền đọc và định dạng đầu vào.

Ví dụ dùng Java NIO:

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path inputPath = Path.of(inputFile).toAbsolutePath().normalize();

if (!Files.isRegularFile(inputPath)) {
    throw new IllegalArgumentException("Input file does not exist: " + inputPath);
}

if (!Files.isReadable(inputPath)) {
    throw new IllegalArgumentException("Input file is not readable: " + inputPath);
}
```

Kiểm tra này giúp đưa ra thông báo dễ hiểu, nhưng không loại bỏ hoàn toàn race condition: file có thể bị xóa hoặc thay đổi sau khi kiểm tra và trước khi Reader mở nó. Reader vẫn cần xử lý lỗi I/O khi thực sự mở và đọc file.

Nếu đường dẫn đến từ request bên ngoài, không nên cho phép caller tùy ý truy cập mọi vị trí trên filesystem. Hãy giới hạn trong một thư mục được phép, chuẩn hóa đường dẫn rồi xác nhận nó nằm dưới thư mục gốc đã cấu hình. Không ghi đường dẫn chứa thông tin nhạy cảm vào log nếu không cần thiết.

## 6. Mở file output bằng FlatFileItemWriter

`FlatFileItemWriter` ghi item thành dòng văn bản thông qua `LineAggregator`. Builder cho phép chỉ định resource, encoding, header/footer và chính sách xử lý file đã tồn tại.

```java
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.core.io.FileSystemResource;

FlatFileItemWriter<ExportOrder> writer =
        new FlatFileItemWriterBuilder<ExportOrder>()
                .name("orderExportWriter")
                .resource(new FileSystemResource("/data/out/orders.csv"))
                .encoding("UTF-8")
                .lineAggregator(order -> String.join(",",
                        order.orderId(),
                        order.customerId(),
                        order.amount().toPlainString()))
                .headerCallback(output -> output.write(
                        "order_id,customer_id,amount"))
                .saveState(true)
                .shouldDeleteIfExists(true)
                .build();
```

Ví dụ dùng `LineAggregator` đơn giản để minh họa việc chuyển object thành một dòng. Nếu field có dấu phẩy, dấu quote hoặc ký tự xuống dòng, cần escape/quote đúng chuẩn CSV hoặc dùng một thư viện CSV chuyên dụng. Không nên nối chuỗi trực tiếp cho dữ liệu CSV phức tạp.

Các cấu hình quan trọng:

- `name(...)`: tên writer ổn định để lưu vị trí ghi trong ExecutionContext.
- `resource(...)`: file đích.
- `encoding(...)`: charset của file output.
- `lineAggregator(...)`: chuyển mỗi item thành một dòng.
- `headerCallback(...)`: ghi header khi tạo file mới.
- `footerCallback(...)`: có thể ghi footer/tổng kết khi writer đóng bình thường.
- `saveState(true)`: lưu vị trí ghi để hỗ trợ restart.
- `shouldDeleteIfExists(true)`: yêu cầu xử lý file đã tồn tại theo chế độ xóa file cũ trước khi ghi lần chạy mới; cần chọn phù hợp với yêu cầu dữ liệu.

## 7. Xử lý file output đã tồn tại: overwrite và append

Trước khi mở writer, cần quyết định rõ file cũ sẽ bị ghi đè, nối thêm hay từ chối chạy. Các lựa chọn này ảnh hưởng trực tiếp đến dữ liệu đầu ra và restart.

### Ghi file mới hoặc ghi đè

Với mỗi batch cần tạo một file kết quả mới, có thể cấu hình `shouldDeleteIfExists(true)` để xóa file cũ trước khi ghi. Cũng có thể dùng tên file duy nhất theo batch ID để tránh ghi đè kết quả của lần chạy khác.

```java
new FlatFileItemWriterBuilder<ExportOrder>()
        .name("orderExportWriter")
        .resource(new FileSystemResource(outputFile))
        .lineAggregator(this::toCsvLine)
        .shouldDeleteIfExists(true)
        .saveState(true)
        .build();
```

### Nối thêm vào file có sẵn

`append(true)` cho phép nối thêm nội dung vào file hiện có. Chỉ dùng khi nghiệp vụ thực sự yêu cầu append, ví dụ ghi nhật ký dạng append-only với cơ chế định danh và chống trùng phù hợp.

```java
new FlatFileItemWriterBuilder<ExportOrder>()
        .name("appendAuditWriter")
        .resource(new FileSystemResource(outputFile))
        .lineAggregator(this::toCsvLine)
        .append(true)
        .saveState(true)
        .build();
```

Append không phải là chiến lược restart. Nếu Job restart và writer đã lưu checkpoint, Spring Batch cần khôi phục đúng vị trí ghi của lần thực thi trước. Không được đổi tên writer, thay file hoặc tự nối lại nội dung ngoài cơ chế checkpoint giữa hai lần chạy. Hãy thử nghiệm restart với đúng cấu hình append trước khi dùng trong production.

### Từ chối ghi đè

Nếu file output đã tồn tại có nghĩa kết quả đã được tạo hoặc cần được điều tra, có thể kiểm tra file trước Step và fail rõ ràng thay vì xóa. Cách này hữu ích với file bàn giao cần được giữ lại để audit.

Không nên dùng cùng một đường dẫn output cho nhiều JobExecution đồng thời. Hai writer có thể cùng mở file và ghi đè hoặc xen kẽ dữ liệu. Tạo tên file riêng theo batch ID/JobInstance hoặc dùng cơ chế khóa ở tầng điều phối.

## 8. Ghi header và footer

Writer có thể ghi header khi mở file và footer khi đóng file:

```java
FlatFileItemWriter<ExportOrder> writer =
        new FlatFileItemWriterBuilder<ExportOrder>()
                .name("orderExportWriter")
                .resource(new FileSystemResource(outputFile))
                .encoding("UTF-8")
                .lineAggregator(this::toCsvLine)
                .headerCallback(output -> output.write(
                        "order_id,customer_id,amount"))
                .footerCallback(output -> output.write(
                        "# export completed"))
                .saveState(true)
                .shouldDeleteIfExists(true)
                .build();
```

Header thường được ghi khi bắt đầu tạo file mới, không nên tự ghi header ở mỗi chunk. Footer được ghi khi writer đóng theo luồng bình thường; nếu Job thất bại hoặc process bị kill, không nên giả định footer đã tồn tại.

Nếu footer chứa tổng số item, hãy dùng cơ chế tổng hợp số liệu phù hợp và kiểm tra khi restart. Footer không thay thế metadata của JobExecution và không phải bằng chứng duy nhất rằng toàn bộ Job đã hoàn tất.

## 9. Đường dẫn output động theo JobParameters

File output thường cần đặt theo ngày nghiệp vụ, tenant hoặc mã batch. Dùng `@StepScope` để nhận tham số:

```java
@Bean
@StepScope
public FlatFileItemWriter<ExportOrder> orderExportWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    if (outputFile == null || outputFile.isBlank()) {
        throw new IllegalArgumentException("outputFile is required");
    }

    return new FlatFileItemWriterBuilder<ExportOrder>()
            .name("orderExportWriter")
            .resource(new FileSystemResource(outputFile))
            .encoding("UTF-8")
            .lineAggregator(this::toCsvLine)
            .headerCallback(output -> output.write(
                    "order_id,customer_id,amount"))
            .saveState(true)
            .shouldDeleteIfExists(true)
            .build();
}
```

Đường dẫn output có thể được tạo từ identifying JobParameters, ví dụ `/data/out/orders-2026-11-15.csv`. Khi restart cùng JobInstance, nên giữ nguyên output path và nội dung file chưa bị thay đổi bởi tiến trình khác để writer khôi phục checkpoint chính xác.

Nếu output path chỉ là thông tin trace, không nên đưa nó thành identifying parameter một cách tùy tiện. Ngược lại, nếu đường dẫn xác định chính file kết quả của đơn vị công việc, cần quyết định rõ nó có tham gia định danh JobInstance hay không.

## 10. Đảm bảo thư mục output tồn tại và có quyền ghi

Writer cần một đường dẫn có thể mở để ghi. Thư mục cha phải tồn tại và process chạy Job phải có quyền tạo file trong thư mục đó.

Có thể kiểm tra và tạo thư mục trong một bước chuẩn bị riêng:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path outputPath = Path.of(outputFile).toAbsolutePath().normalize();
Path parent = outputPath.getParent();

if (parent == null) {
    throw new IllegalArgumentException("Output path must have a parent directory");
}

Files.createDirectories(parent);

if (Files.exists(outputPath) && !Files.isWritable(outputPath)) {
    throw new IOException("Output file is not writable: " + outputPath);
}

if (!Files.isWritable(parent)) {
    throw new IOException("Output directory is not writable: " + parent);
}
```

Đoạn code trên là ví dụ kiểm tra quyền cơ bản; quyền thực tế còn phụ thuộc user chạy process, ACL, mount và hệ điều hành. Một bước preflight không loại bỏ lỗi I/O phát sinh sau đó, vì vậy Writer vẫn cần xử lý exception khi mở hoặc ghi file.

Nếu thư mục output được cấu hình từ input bên ngoài, hãy giới hạn đường dẫn vào thư mục gốc được phép. Dùng `normalize()` và xác nhận đường dẫn sau chuẩn hóa vẫn nằm trong thư mục gốc, tránh path traversal.

## 11. Checkpoint và restart của file reader/writer

`FlatFileItemReader` và `FlatFileItemWriter` hỗ trợ lưu state thông qua `ExecutionContext` khi `saveState(true)`. Với reader, state thường bao gồm vị trí đọc; với writer, state có thể bao gồm vị trí ghi để tiếp tục file khi restart.

Ví dụ luồng restart:

```text
JobExecution #1
  Chunk 1 -> ghi output -> COMMIT
  Chunk 2 -> ghi output -> COMMIT
  Chunk 3 -> lỗi -> ROLLBACK
       |
       v
JobExecution #2 (restart cùng JobInstance)
  Reader khôi phục vị trí sau Chunk 2
  Writer khôi phục vị trí file đã commit
  Tiếp tục Chunk 3
```

Để restart đáng tin cậy:

1. Dùng tên Reader/Writer ổn định qua các lần chạy.
2. Bật lưu state nếu cần checkpoint.
3. Giữ nguyên identifying JobParameters và đường dẫn file tương ứng.
4. Không thay nội dung file input giữa lần chạy đầu và restart.
5. Không xóa hoặc sửa file output khi Job đang chạy hoặc đang chờ restart.
6. Đảm bảo Step thực sự quản lý Reader/Writer qua ItemStream lifecycle.

Nếu tắt `saveState`, Reader/Writer không lưu checkpoint theo cách thông thường. Khi restart, chúng có thể bắt đầu lại từ đầu hoặc không khôi phục đúng vị trí. Chỉ tắt lưu state khi thành phần không cần restart hoặc ứng dụng tự quản lý vị trí và tính nhất quán.

## 12. File output và transaction database

`FlatFileItemWriter` có hỗ trợ phối hợp ghi file với transaction của chunk thông qua cơ chế transactional của writer. Tuy vậy, file trên filesystem và database không phải lúc nào cũng là một tài nguyên transaction chung có thể rollback nguyên tử.

Ví dụ một chunk vừa ghi database vừa ghi file:

```text
Chunk transaction
    |
    +--> UPDATE database
    +--> write output file buffer
    |
    v
Transaction commit
```

Khi transaction rollback, writer transactional có thể không phát phần dữ liệu đang buffer ra file theo hành vi của nó. Nhưng không nên suy rộng rằng mọi thao tác filesystem đều rollback cùng database. Nếu Tasklet tự copy, rename hoặc xóa file, những thao tác đó không tự được database transaction hoàn tác.

Với file bàn giao quan trọng, một pattern an toàn là ghi ra file tạm như `orders.csv.part`, hoàn tất Job, sau đó dùng một bước publish riêng để đổi tên sang file cuối. Chỉ công bố file cuối khi Job đã hoàn tất và có thể kiểm tra kích thước/checksum. Rename nguyên tử chỉ được bảo đảm trong một số điều kiện filesystem, thường cần file nguồn và đích nằm trên cùng filesystem.

Không nên để consumer đọc file output khi Job vẫn đang ghi. Có thể dùng trạng thái batch, tên file tạm hoặc manifest hoàn tất để consumer biết khi nào file sẵn sàng.

## 13. Đóng file và xử lý lỗi I/O

Spring Batch gọi `close()` trên các ItemStream đã đăng ký khi Step kết thúc. Việc đóng file giải phóng file handle và cho writer cơ hội hoàn tất các thao tác đóng như footer hoặc flush buffer.

Các lỗi I/O có thể xảy ra ở nhiều thời điểm:

- File không tồn tại hoặc không có quyền đọc khi Reader mở.
- Disk đầy hoặc quota vượt giới hạn khi Writer ghi.
- Network filesystem mất kết nối.
- File bị tiến trình khác xóa hoặc thay thế.
- Process bị kill trước khi `close()` hoàn tất.

Không nên tự đóng stream nội bộ của `FlatFileItemReader`/`FlatFileItemWriter` trong Processor hoặc Tasklet khác. Hãy để Step quản lý vòng đời. Nếu tự triển khai ItemStream, phải bảo đảm `close()` an toàn khi được gọi sau lỗi và giải phóng mọi tài nguyên đã mở.

Nếu lỗi xảy ra trong `close()`, Step có thể không kết thúc thành công như dự kiến. Hãy ghi log đủ thông tin file, StepExecution ID và exception; tránh chỉ log tên file nếu đường dẫn có dữ liệu nhạy cảm.

## 14. Khi Reader/Writer được bọc trong component khác

Một số ứng dụng dùng decorator, composite reader/writer hoặc custom adapter. Nếu delegate triển khai `ItemStream`, lifecycle của nó phải được chuyển tiếp.

Ví dụ Step đăng ký một stream riêng:

```java
return new StepBuilder("importStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(customReader)
        .writer(writer)
        .stream(delegateFileReader)
        .build();
```

Ví dụ giả định `customReader` bọc `delegateFileReader` nhưng không tự triển khai/chuyển tiếp `ItemStream`. Đăng ký delegate bằng `.stream(...)` giúp Step gọi lifecycle tương ứng. Nếu wrapper đã triển khai `ItemStream` và chuyển tiếp đầy đủ `open`, `update`, `close`, không cần đăng ký delegate lần nữa.

Không quản lý lifecycle hai lần. Đăng ký cùng một stream qua wrapper và trực tiếp có thể dẫn đến mở/đóng lặp hoặc trạng thái không mong muốn.

## 15. Kiểm thử mở file input và output

Kiểm thử nên bao gồm cả file hợp lệ, file thiếu, encoding, header, output đã tồn tại và restart.

Các kịch bản hữu ích:

1. **Reader đọc file hợp lệ:** xác nhận số item, mapping field và encoding.
2. **Reader không tìm thấy file:** xác nhận Step thất bại với thông báo rõ ràng khi `strict(true)`.
3. **Reader bỏ qua header:** xác nhận dòng đầu không trở thành item dữ liệu.
4. **Writer tạo file mới:** xác nhận header, số dòng, line separator và encoding.
5. **Output đã tồn tại:** xác nhận hành vi overwrite, append hoặc fail đúng chính sách.
6. **Restart giữa file:** làm Job thất bại sau một số chunk đã commit, restart cùng JobInstance và xác nhận reader/writer tiếp tục đúng vị trí.
7. **Disk/permission failure:** kiểm tra Step xử lý lỗi I/O và trạng thái Job phù hợp.
8. **Hai Job đồng thời:** xác nhận chúng không ghi cùng một output path ngoài ý muốn.

Ví dụ dùng JUnit và thư mục tạm:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ExportFileTest {

    @TempDir
    Path tempDir;

    @Test
    void createsOutputFile() throws Exception {
        Path output = tempDir.resolve("orders.csv");

        // Launch Step/Job test với output path trỏ đến output.

        assertTrue(Files.exists(output));
        assertEquals("order_id,customer_id,amount",
                Files.readAllLines(output).get(0));
    }
}
```

Đây là khung minh họa; phần launch Job cần được nối với cấu hình test và `JobLauncherTestUtils` của ứng dụng. Với restart test, giữ nguyên identifying parameters và output path giữa hai lần launch, rồi kiểm tra file cuối không mất dòng đã commit hoặc lặp dòng do chunk bị xử lý lại.

## 16. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng `ClassPathResource` làm output | Tài nguyên trong classpath/JAR thường không writable. | Dùng `FileSystemResource` cho file output. |
| Không khai báo encoding | Encoding mặc định có thể khác giữa môi trường. | Chỉ định UTF-8 hoặc charset theo hợp đồng dữ liệu. |
| Không dùng `@StepScope` với đường dẫn động | Bean singleton không nhận đúng JobParameters của execution. | Dùng `@StepScope` và SpEL. |
| Tên reader/writer thay đổi giữa restart | Key ExecutionContext không còn khớp checkpoint cũ. | Giữ tên ổn định trong suốt vòng đời Job. |
| Xóa file output khi restart | Mất phần dữ liệu đã ghi ở chunk commit trước đó. | Chọn overwrite cho lần chạy mới và giữ file khi restart cùng instance. |
| Append cùng một output cho nhiều execution | Dữ liệu có thể bị nối trùng hoặc xen kẽ. | Tạo output path riêng theo batch/JobInstance. |
| File input bị thay thế giữa hai lần chạy | Checkpoint cũ có thể trỏ đến nội dung khác. | Dùng file bất biến, checksum hoặc version. |
| Không tạo thư mục output | Writer không mở được file. | Tạo/kiểm tra thư mục trong bước chuẩn bị. |
| Wrapper không chuyển tiếp ItemStream | Reader/Writer delegate không được mở, checkpoint hoặc đóng đúng cách. | Implement lifecycle hoặc đăng ký `.stream(delegate)`. |
| Cho rằng database rollback sẽ rollback mọi file operation | Filesystem không nhất thiết tham gia transaction database. | Dùng file tạm, outbox/manifest và bước publish riêng. |

## Kết luận

Spring Batch mở và đóng file thông qua Reader/Writer triển khai `ItemStream`, với `open()` khi Step bắt đầu, `update()` để lưu checkpoint và `close()` khi Step kết thúc. Dùng `Resource` phù hợp: `FileSystemResource` cho file hệ thống, `ClassPathResource` chủ yếu để đọc tài nguyên đóng gói. `FlatFileItemReader` và `FlatFileItemWriter` cần tên ổn định, encoding rõ ràng và `saveState(true)` khi cần restart. Với đường dẫn thay đổi theo lần chạy, dùng `@StepScope` và JobParameters. Chọn rõ overwrite/append, bảo đảm thư mục và quyền truy cập, giữ file input/output ổn định qua restart và không giả định thao tác filesystem được rollback nguyên tử cùng database.
