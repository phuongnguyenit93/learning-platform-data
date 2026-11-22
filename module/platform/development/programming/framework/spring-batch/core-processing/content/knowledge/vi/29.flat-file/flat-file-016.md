# Append hay overwrite output

Trong Spring Batch, `FlatFileItemWriter` ghi dữ liệu của các item thành các dòng trong một file. Khi file đích đã tồn tại, ứng dụng cần xác định writer sẽ **append** (ghi nối tiếp vào cuối file), **overwrite** (ghi đè nội dung cũ) hay từ chối ghi để tránh làm mất dữ liệu. Lựa chọn này ảnh hưởng trực tiếp đến việc chạy job nhiều lần, restart sau lỗi, tạo file báo cáo và xử lý các batch chạy đồng thời.

Append và overwrite là chính sách đối với file output. Chúng cần được thiết kế cùng JobParameters, checkpoint, transaction và vòng đời của step. Chỉ bật append không tự bảo đảm dữ liệu không trùng; chỉ bật overwrite cũng không có nghĩa restart luôn an toàn. Cần phân biệt một lần chạy mới với lần restart của cùng JobInstance.

## 1. Append và overwrite là gì?

Giả sử writer tạo file `orders.txt` và ghi ba dòng:

```text
ORD-001,120.00
ORD-002,250.00
ORD-003,80.00
```

Nếu lần chạy sau dùng **overwrite**, nội dung cũ của file được thay thế bằng kết quả mới. Ví dụ job mới chỉ xử lý hai đơn hàng:

```text
ORD-010,50.00
ORD-011,70.00
```

Nếu lần chạy sau dùng **append**, dữ liệu mới được ghi tiếp vào cuối file cũ:

```text
ORD-001,120.00
ORD-002,250.00
ORD-003,80.00
ORD-010,50.00
ORD-011,70.00
```

Hai cách có ý nghĩa nghiệp vụ khác nhau:

| Chế độ | Kết quả khi file đã có dữ liệu | Trường hợp thường dùng |
|---|---|---|
| Overwrite | Xóa/thay nội dung cũ rồi ghi kết quả lần chạy hiện tại. | Tạo báo cáo mới, snapshot hoặc export đại diện cho một lần chạy. |
| Append | Giữ nội dung hiện có và ghi thêm dòng mới ở cuối. | Tạo nhật ký dạng file hoặc gom kết quả của nhiều batch vào một file theo thiết kế. |
| Fail if exists | Không ghi nếu file đích đã tồn tại. | Bảo vệ file output, tránh ghi nhầm hoặc ghi đè ngoài ý muốn. |

`FlatFileItemWriter` hỗ trợ các chính sách này qua cấu hình append và xóa file khi mở. Cần chọn chế độ dựa trên yêu cầu của output, không chỉ dựa vào việc file có tồn tại hay không.

## 2. Cấu hình append và overwrite bằng FlatFileItemWriterBuilder

Spring Batch cung cấp `FlatFileItemWriterBuilder` để cấu hình writer. Các tùy chọn quan trọng gồm:

- `append(boolean)`: cho phép nối thêm vào file đã tồn tại.
- `shouldDeleteIfExists(boolean)`: quyết định có xóa file hiện có khi mở writer trong một lần chạy mới hay không.
- `shouldDeleteIfEmpty(boolean)`: quyết định có xóa file nếu step không ghi item nào hay không.
- `saveState(boolean)`: bật/tắt lưu trạng thái writer vào `ExecutionContext` để hỗ trợ restart.
- `transactional(boolean)`: điều khiển cách writer phối hợp với transaction khi ghi file.

### Overwrite file cũ

Khi muốn mỗi lần chạy mới tạo một output hoàn toàn mới, cấu hình overwrite rõ ràng:

```java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .delimiter(",")
            .names("orderId", "amount")
            .append(false)
            .shouldDeleteIfExists(true)
            .shouldDeleteIfEmpty(false)
            .saveState(true)
            .build();
}
```

Với cấu hình này, writer được thiết kế để thay output cũ khi mở cho một lần chạy mới. `shouldDeleteIfEmpty(false)` giữ file rỗng nếu step không ghi item nào; nếu nghiệp vụ muốn không có file khi không có dữ liệu, có thể chọn chính sách ngược lại.

Không nên dùng cùng một đường dẫn cố định cho nhiều job chạy đồng thời nếu mỗi job cần output riêng. Một job có thể xóa file trong khi job khác đang ghi.

### Append vào file đã tồn tại

Nếu output được thiết kế như một file tích lũy, có thể bật append:

```java
@Bean
@StepScope
FlatFileItemWriter<Order> appendOrderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("appendOrderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .delimiter(",")
            .names("orderId", "amount")
            .append(true)
            .saveState(true)
            .build();
}
```

Khi file đã tồn tại và đây là một lần mở mới theo chính sách append, dữ liệu mới được nối vào cuối file. Ứng dụng cần bảo đảm các dòng được thêm thuộc đúng batch và không bị thêm lặp khi cùng một đơn vị công việc được khởi chạy lại.

### Từ chối nếu file đã tồn tại

Nếu không muốn xóa hoặc nối vào file có sẵn, có thể cấu hình không xóa file hiện hữu:

```java
return new FlatFileItemWriterBuilder<Order>()
        .name("newOutputOnlyWriter")
        .resource(new FileSystemResource(outputFile))
        .lineAggregator(order -> order.orderId() + "," + order.amount())
        .append(false)
        .shouldDeleteIfExists(false)
        .saveState(true)
        .build();
```

Trong chế độ này, nếu file đã tồn tại và không phải trường hợp restart được nhận diện từ state của writer, việc mở writer sẽ thất bại thay vì âm thầm xóa hoặc nối dữ liệu. Đây là lựa chọn hữu ích khi file output phải là mới cho mỗi batch.

## 3. Ý nghĩa của shouldDeleteIfExists

`shouldDeleteIfExists` kiểm soát cách writer xử lý file đích đã có khi bắt đầu một lần ghi mới. Đây là cấu hình dễ bị nhầm với append.

| `append` | `shouldDeleteIfExists` | Ý định cấu hình |
|---:|---:|---|
| `false` | `true` | Overwrite: cho phép xóa file cũ rồi tạo output mới. |
| `true` | `false` | Append: giữ file cũ và ghi nối tiếp. |
| `false` | `false` | Fail if exists: từ chối mở file đã tồn tại trong lần chạy mới. |

Khi `append(true)` được bật, writer sẽ không xóa file cũ để append vào đó. Trong builder, hãy đặt các thuộc tính rõ ràng để người đọc cấu hình hiểu chính sách output.

Không nên dựa vào default của builder khi file output có giá trị quan trọng. Hãy khai báo rõ chế độ mong muốn và kiểm thử cả trường hợp file chưa tồn tại lẫn file đã tồn tại.

## 4. Append trong lần chạy mới khác append khi restart

Đây là khác biệt quan trọng nhất khi thiết kế file output cho batch.

- **Lần chạy mới:** người dùng hoặc scheduler khởi chạy một JobInstance mới, có thể dùng một output file mới hoặc một file tích lũy. `append` quyết định writer xử lý file đã tồn tại như thế nào.
- **Restart:** job đã thất bại/dừng và được chạy lại với cùng JobInstance. Writer cần dùng state đã lưu để tiếp tục output của lần chạy trước, tránh ghi lại dữ liệu đã commit.

`FlatFileItemWriter` là một `ItemStream` và có thể lưu trạng thái vào `ExecutionContext`. Khi `saveState(true)`, writer lưu thông tin cần thiết để khôi phục quá trình ghi. Khi step được restart, writer nhận biết state của execution trước và xử lý file theo cơ chế restart.

Vì vậy, không nên hiểu `append(true)` chỉ là “bật restart”, hoặc hiểu `append(false)` luôn có nghĩa xóa file khi restart. Append mode cho lần mở file đã tồn tại và restart của cùng execution là hai tình huống cần được phân biệt. Hãy để writer khôi phục state theo checkpoint và kiểm thử hành vi restart trên phiên bản Spring Batch thực tế.

## 5. Vai trò của saveState khi restart

`saveState(true)` cho phép writer lưu trạng thái cần thiết vào `ExecutionContext`. Trạng thái này giúp writer biết đã ghi đến đâu khi step được restart.

Ví dụ:

```text
Lần chạy đầu
  chunk 1 -> ghi 100 dòng -> COMMIT
  chunk 2 -> ghi 100 dòng -> COMMIT
  chunk 3 -> lỗi trước khi commit

Restart cùng JobInstance
  khôi phục trạng thái writer đã lưu
  tiếp tục từ checkpoint phù hợp
  không ghi lại các chunk đã commit
```

Nếu tắt `saveState`, writer không lưu đủ checkpoint để tự khôi phục vị trí ghi theo cơ chế restart thông thường. Khi đó, ứng dụng phải tự thiết kế cách xác định dữ liệu đã xuất và cách tiếp tục; nếu chỉ bật append rồi restart, có thể tạo dòng trùng hoặc file không nhất quán.

Đối với job cần restart, nên giữ `saveState(true)` và dùng tên writer ổn định. Tên writer tham gia tạo key trong `ExecutionContext`; thay tên giữa lần chạy đầu và restart có thể khiến writer không tìm thấy state cũ.

## 6. Tại sao append không tự chống trùng dữ liệu?

Append chỉ thêm dữ liệu vào cuối file. Nó không biết một dòng có phải đã được ghi ở batch trước hay không, cũng không hiểu khóa nghiệp vụ của record.

Ví dụ, job được chạy hai lần với cùng input:

```text
Lần 1 append:
ORD-001,120.00
ORD-002,250.00

Lần 2 append cùng input:
ORD-001,120.00
ORD-002,250.00
```

Kết quả sẽ có hai bản sao của mỗi đơn hàng nếu không có cơ chế chống lặp. Một file append-only không đồng nghĩa với exactly-once.

Các cách kiểm soát thường dùng:

- Dùng output file riêng theo batch ID hoặc JobExecution/JobInstance identity.
- Ghi batch reference và item key vào từng dòng hoặc metadata kèm theo.
- Lưu danh sách batch đã publish để không append cùng batch lần thứ hai.
- Tạo file staging riêng rồi chỉ publish một lần khi job hoàn tất.
- Dùng một kho dữ liệu có unique key nếu cần bảo đảm chống trùng theo nghiệp vụ.
- Khi restart, dùng checkpoint của writer thay vì tự chạy lại toàn bộ item và append lại từ đầu.

Nếu file là nhật ký tích lũy, cần xác định chính sách deduplication hoặc chấp nhận các bản ghi lặp như một phần của định dạng log.

## 7. Đặt tên output theo JobParameters

Một cách an toàn để tránh nhiều lần chạy ghi vào cùng một file là tạo output path theo tham số nghiệp vụ. Ví dụ:

```text
output/
  orders-2026-11-15.csv
  orders-2026-11-16.csv
  orders-2026-11-17.csv
```

Có thể nhận path qua JobParameters:

```java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .delimiter(",")
            .names("orderId", "amount")
            .append(false)
            .shouldDeleteIfExists(true)
            .saveState(true)
            .build();
}
```

Với JobParameters:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("outputFile", "output/orders-2026-11-15.csv", true)
        .toJobParameters();
```

Đánh dấu `outputFile` là identifying hay non-identifying phụ thuộc quy tắc nghiệp vụ. Nếu đường dẫn xác định đơn vị output logic, nó có thể là identifying. Nếu chỉ là nơi lưu vật lý nhưng không thay đổi identity của batch, có thể chọn non-identifying. Dù vậy, khi restart, mọi tham số ảnh hưởng đến output phải được giữ ổn định.

## 8. Tạo output mới an toàn bằng file tạm

Với báo cáo hoặc file trao đổi quan trọng, người nhận không nên đọc file khi batch mới ghi được một phần. Một pattern phổ biến là ghi vào file tạm rồi publish bằng thao tác move/rename sau khi step/job hoàn tất.

```text
orders-2026-11-15.csv.tmp
          |
          | batch ghi và commit các chunk
          v
Kiểm tra step/job hoàn tất
          |
          | move/rename
          v
orders-2026-11-15.csv
```

Writer có thể ghi vào path `.tmp`. Một step sau đó dùng tasklet để đổi tên file khi mọi bước cần thiết đã thành công. Cách này giúp consumer chỉ nhìn thấy tên file chính thức sau khi dữ liệu đã sẵn sàng.

Ví dụ tasklet minh họa:

```java
@Bean
@StepScope
Tasklet publishOutputTasklet(
        @Value("#{jobParameters['temporaryFile']}") String temporaryFile,
        @Value("#{jobParameters['finalFile']}") String finalFile) {

    return (contribution, chunkContext) -> {
        Path source = Path.of(temporaryFile);
        Path target = Path.of(finalFile);

        Files.move(source, target,
                StandardCopyOption.REPLACE_EXISTING,
                StandardCopyOption.ATOMIC_MOVE);

        return RepeatStatus.FINISHED;
    };
}
```

`ATOMIC_MOVE` phụ thuộc filesystem và có thể không được hỗ trợ giữa các filesystem/volume khác nhau. Nếu không hỗ trợ, ứng dụng cần xử lý fallback rõ ràng. Cần bảo đảm thư mục đích tồn tại và target file có chính sách thay thế phù hợp.

Không đặt thao tác publish file ngoài transaction như thể nó có thể rollback cùng database. Nếu move thành công nhưng metadata commit thất bại, lần restart cần nhận diện file đã publish và xử lý idempotently.

## 9. Header và footer khi append hoặc overwrite

`FlatFileItemWriter` hỗ trợ `headerCallback` và `footerCallback` để ghi dòng đầu/cuối file.

Ví dụ:

```java
return new FlatFileItemWriterBuilder<Order>()
        .name("orderWriter")
        .resource(resource)
        .delimited()
        .delimiter(",")
        .names("orderId", "amount")
        .headerCallback(writer -> writer.write("orderId,amount"))
        .footerCallback(writer -> writer.write("END-OF-FILE"))
        .build();
```

Khi chọn append, cần xác định header/footer có thuộc mỗi batch hay thuộc toàn bộ file:

- Nếu file tích lũy chỉ được có một header ở đầu, không được tạo header mới cho mỗi lần append.
- Nếu mỗi batch là một segment độc lập, header/footer theo từng segment có thể là một phần của định dạng.
- Footer tổng hợp (ví dụ tổng số dòng hoặc checksum) có thể cần được tạo sau khi toàn bộ nội dung đã hoàn tất.

Hành vi callback phụ thuộc cách writer mở file, file có tồn tại hay không và có phải restart hay không. Hãy kiểm tra kết quả thực tế của phiên bản đang dùng, đặc biệt khi kết hợp append, restart và header/footer callback. Không nên chỉ dựa vào một test chạy file mới để suy luận hành vi append.

Nếu cần format tích lũy có một header duy nhất và footer cuối cùng, có thể quản lý header/footer trong bước publish riêng hoặc thiết kế định dạng segment rõ ràng.

## 10. shouldDeleteIfEmpty

`shouldDeleteIfEmpty` quyết định file output có bị xóa khi step kết thúc mà không ghi item nào hay không.

```java
.shouldDeleteIfEmpty(true)
```

Khi bật, writer có thể xóa file nếu không có dữ liệu được ghi. Điều này phù hợp khi file rỗng không có ý nghĩa hoặc consumer không nên nhận file rỗng.

Ngược lại:

```java
.shouldDeleteIfEmpty(false)
```

giữ lại file rỗng, có thể hữu ích khi hợp đồng trao đổi yêu cầu luôn có file, kể cả không có record.

Hãy phân biệt file rỗng với file chỉ có header. Nếu header callback ghi nội dung, file có thể không còn được xem là rỗng theo tiêu chí của writer. Nếu định dạng yêu cầu file có header nhưng không có record, cần kiểm thử cụ thể.

## 11. Transactional writing và chunk commit

Trong chunk-oriented step, `FlatFileItemWriter` mặc định phối hợp với transaction để tránh công bố nội dung của chunk chưa commit như thể đã hoàn tất. Writer có thể buffer dữ liệu trong lúc transaction đang mở và flush khi transaction commit.

Ví dụ:

```text
BEGIN transaction
  read 100 items
  process 100 items
  writer buffer 100 output lines
COMMIT
  flush buffered lines to file
```

Nếu chunk rollback, dữ liệu đang buffer theo transaction không được xử lý như một chunk đã commit. Tuy nhiên, file system không phải database transaction resource thông thường. Một số tình huống lỗi I/O, process crash hoặc cấu hình writer đặc biệt có thể tạo khác biệt giữa metadata và file vật lý.

Thuộc tính `transactional(false)` thay đổi cách writer phối hợp với transaction. Chỉ dùng khi hiểu rõ hậu quả: output có thể được ghi ngay cả khi transaction database rollback, làm file chứa dữ liệu chưa được commit trong database.

Nếu step vừa ghi database vừa ghi file, không có distributed transaction tự động bảo đảm cả hai tài nguyên commit nguyên tử trong mọi trường hợp. Cần thiết kế staging, reconciliation hoặc bước publish để xử lý trạng thái không đồng bộ.

## 12. Append và restart của FlatFileItemWriter

Restart là một lần chạy mới của `JobExecution` cho cùng `JobInstance`, không phải một lần chạy batch độc lập. Khi writer hỗ trợ `ItemStream` và `saveState(true)`, Spring Batch lưu state vào `ExecutionContext` để writer có thể khôi phục.

Một tình huống điển hình:

```text
JobExecution #1
  chunk 1 -> commit, writer state saved
  chunk 2 -> commit, writer state saved
  chunk 3 -> lỗi trước commit

JobExecution #2 (restart cùng JobInstance)
  writer mở lại resource và khôi phục state
  xử lý lại phần chưa commit theo checkpoint
  tiếp tục ghi phần còn lại
```

Không nên tự nối file bằng một writer mới không có checkpoint rồi giả định restart sẽ không lặp. Hãy dùng cùng tên writer, giữ `saveState(true)`, cùng output resource và cùng identifying parameters. Kiểm thử việc mở lại writer sau restart bằng JobRepository thực tế.

Nếu ứng dụng đổi output path giữa lần chạy đầu và restart, writer có thể ghi tiếp vào một file khác trong khi checkpoint vẫn mô tả tiến độ cũ. Đây là nguyên nhân phổ biến gây thiếu file hoặc output không hoàn chỉnh. Path output cần được giữ ổn định cho cùng JobInstance.

## 13. Overwrite và nhiều lần chạy JobInstance mới

Một job được khởi chạy lại với identifying parameters khác tạo JobInstance mới. Nếu output path vẫn cố định và writer được cấu hình overwrite, lần chạy mới có thể xóa kết quả của lần trước.

Ví dụ:

```text
JobInstance #1: businessDate=2026-11-15
  outputFile=output/orders.csv

JobInstance #2: businessDate=2026-11-16
  outputFile=output/orders.csv
```

Nếu cả hai lần chạy dùng overwrite trên cùng path, kết quả ngày 16 có thể thay thế file ngày 15. Nếu cần lưu lịch sử theo ngày, hãy đưa business date hoặc batch reference vào tên file.

Nếu yêu cầu là tạo một file tổng hợp qua nhiều ngày, append có thể phù hợp nhưng cần có quy trình xác định batch nào đã được thêm. Đừng dùng cùng một đường dẫn cho cả hai ý nghĩa “snapshot mỗi ngày” và “file tích lũy”.

## 14. File output trong partitioning

Khi partitioning, nhiều worker có thể chạy đồng thời. Nếu tất cả worker cùng ghi vào một file, có nguy cơ:

- Dòng bị xen kẽ hoặc thứ tự không xác định.
- Nhiều writer cùng mở/đóng một resource.
- Header/footer bị lặp.
- Trạng thái checkpoint của từng writer xung đột.
- Ghi trùng hoặc mất dòng khi một partition restart.

Một pattern an toàn hơn là tạo file riêng theo partition:

```text
output/batch-20261115/
  part-000.csv
  part-001.csv
  part-002.csv
  part-003.csv
          |
          v
   merge/publish step
          |
          v
   orders-20261115.csv
```

Mỗi worker có output path riêng, được tạo từ partition name hoặc partition key. Sau khi mọi partition hoàn tất, một step tuần tự có thể ghép file theo thứ tự xác định và publish file cuối.

Nếu bắt buộc nhiều thread ghi vào một file chung, cần cơ chế đồng bộ phù hợp và kiểm tra thread safety của writer. Đồng bộ trong một JVM không bảo vệ file khỏi process khác hoặc node khác. Cần khóa liên process hoặc một kiến trúc output khác nếu nhiều instance có thể ghi cùng path.

## 15. Không chia sẻ một file output giữa các job đồng thời

Hai JobExecution chạy đồng thời và cùng dùng một resource có thể phá hỏng output, dù cả hai writer đều cấu hình append. Append không phải cơ chế khóa file và không đảm bảo thứ tự ghi giữa process.

Các giải pháp thường dùng:

- Mỗi JobInstance có output path riêng.
- Dùng batch ID/tenant/date làm thành phần của tên file.
- Chỉ có một publisher tuần tự ghi vào file tổng hợp.
- Dùng hàng đợi hoặc database làm nơi nhận dữ liệu trung gian rồi export tuần tự.
- Dùng distributed lock nếu thực sự phải bảo vệ một output resource chung.

Đừng dựa vào việc filesystem “thường ghi nguyên dòng” để bảo đảm không bị xen kẽ. Cách hoạt động phụ thuộc filesystem, buffer, process và cách writer mở file.

## 16. Tạo tên file động bằng JobParameters

`@StepScope` thường được dùng để inject output path từ JobParameters:

```java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['runReference']}") String runReference) {

    String fileName = "orders-" + businessDate + "-" + runReference + ".csv";

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource("output/" + fileName))
            .delimited()
            .delimiter(",")
            .names("orderId", "amount")
            .append(false)
            .shouldDeleteIfExists(true)
            .saveState(true)
            .build();
}
```

Trong ví dụ, `runReference` cần được tạo và lưu ổn định cho cùng JobInstance. Nếu nó thay đổi mỗi lần restart, writer có thể ghi vào file mới và bỏ lại file cũ chưa hoàn tất.

Không đưa dữ liệu chưa được kiểm tra trực tiếp vào path. Hãy validate các tham số, chuẩn hóa tên file và bảo đảm output path nằm trong thư mục được phép của ứng dụng.

## 17. Output overwrite với quy trình publish an toàn

Một quy trình export phổ biến có ba giai đoạn:

1. Ghi dữ liệu vào file tạm riêng cho JobInstance.
2. Kiểm tra số dòng, checksum hoặc các điều kiện nghiệp vụ.
3. Đổi tên file tạm thành file chính thức sau khi mọi step thành công.

Ví dụ flow:

```text
prepareOutputStep
       |
       v
writeTemporaryFileStep
       |
       v
validateOutputStep
       |
       v
publishOutputStep
       |
       v
COMPLETED
```

Nếu `writeTemporaryFileStep` thất bại, file chính thức cũ vẫn còn nguyên. Khi restart, writer tiếp tục file tạm theo checkpoint. Khi validation thành công, publish step thay thế file chính thức theo chính sách đã định.

Nếu publish step được restart sau khi move đã thành công nhưng metadata chưa commit, tasklet cần nhận biết trạng thái file để không lỗi hoặc thay đổi dữ liệu ngoài ý muốn. Có thể kiểm tra source/target, checksum và lưu một publication marker theo JobExecution.

## 18. Kiểm thử append và overwrite

Nên test với thư mục tạm riêng cho mỗi test, không dùng một file cố định trong workspace. Điều này tránh test phụ thuộc thứ tự chạy hoặc làm mất dữ liệu do test trước để lại.

Các trường hợp cơ bản:

| Test case | Thiết lập | Kết quả cần xác nhận |
|---|---|---|
| File chưa tồn tại, overwrite | `append(false)` | File được tạo và chứa output mới. |
| File đã tồn tại, overwrite | `append(false)`, xóa file cũ được phép | Nội dung cũ được thay bằng output mới. |
| File đã tồn tại, append | `append(true)` | Nội dung mới được thêm sau nội dung cũ. |
| File đã tồn tại, fail-if-exists | `append(false)`, `shouldDeleteIfExists(false)` | Mở writer thất bại thay vì xóa/ghi nối. |
| Step không ghi item | Kiểm tra `shouldDeleteIfEmpty` | File rỗng được giữ hoặc xóa theo cấu hình. |
| Restart sau một số chunk | `saveState(true)` và cùng resource | Writer tiếp tục từ state đã lưu, không lặp chunk đã commit. |
| JobInstance mới cùng path | Parameters định danh khác | Xác nhận overwrite/append đúng chính sách output đã chọn. |

Ví dụ test ý tưởng cho append bằng `FlatFileItemWriter`:

```java
@Test
void appendsLinesToExistingFile() throws Exception {
    Path output = tempDir.resolve("orders.csv");
    Files.writeString(output, "old-order,10.00\n");

    FlatFileItemWriter<String> writer =
            new FlatFileItemWriterBuilder<String>()
                    .name("appendWriter")
                    .resource(new FileSystemResource(output))
                    .lineAggregator(item -> item)
                    .append(true)
                    .saveState(false)
                    .build();

    writer.open(new ExecutionContext());
    writer.write(Chunk.of("new-order,20.00"));
    writer.close();

    assertThat(Files.readString(output))
            .contains("old-order,10.00")
            .contains("new-order,20.00");
}
```

Ví dụ dùng `saveState(false)` chỉ để test append cơ bản mà không thiết lập restart context. Test restart phải dùng `saveState(true)`, JobRepository và transaction boundary phù hợp.

## 19. Kiểm thử restart của writer

Để kiểm thử restart thực tế, cần chạy job/step ít nhất hai lần trên cùng JobInstance và cùng output path:

1. Khởi chạy job với identifying parameters cố định.
2. Cho writer ghi và commit một số chunk.
3. Làm step thất bại có kiểm soát ở chunk tiếp theo.
4. Xác nhận file có nội dung của các chunk đã commit.
5. Khắc phục nguyên nhân lỗi.
6. Restart cùng JobInstance bằng parameters cũ.
7. Xác nhận writer khôi phục state và tiếp tục output.
8. Xác nhận file cuối không bị thiếu hoặc trùng dòng.

Test nên đọc file và so sánh danh sách business key dự kiến, không chỉ kiểm tra file tồn tại hoặc kích thước lớn hơn 0.

Nếu test thay output path khi restart, hãy xác nhận đây có phải behavior được thiết kế hay không. Thông thường, cùng JobInstance nên tiếp tục cùng logical output. Thay path mà không thay đổi/di chuyển checkpoint có thể tạo hai file dở dang.

## 20. Header/footer và output tích lũy

Nếu file append qua nhiều JobInstance, cần xác định định dạng tích lũy:

**Một header cho toàn file:** chỉ ghi header khi tạo file lần đầu. Các batch sau chỉ ghi record mới. Cần có cơ chế xác định file đã có header và xử lý trường hợp file rỗng.

**Một header cho mỗi batch segment:** mỗi batch ghi một marker/header có batch reference, sau đó là các record của batch. Consumer phải hiểu cấu trúc nhiều segment.

**Một footer tổng hợp:** nếu footer chứa tổng số dòng/checksum của toàn file, không thể đơn giản ghi một footer mới ở mỗi lần append. Cần tính lại hoặc publish footer cuối trong bước riêng.

Với định dạng trao đổi yêu cầu một header và một trailer duy nhất, thường an toàn hơn khi ghi file tạm cho từng batch rồi ghép/publish qua step kiểm soát thay vì nhiều job đồng thời append trực tiếp.

## 21. Lựa chọn chế độ theo yêu cầu nghiệp vụ

| Yêu cầu | Chiến lược đề xuất |
|---|---|
| Báo cáo ngày luôn phản ánh dữ liệu mới nhất của ngày đó | Tên file theo ngày và overwrite có kiểm soát. |
| Lưu từng lần chạy để audit | Tên file có batch/run reference riêng, không overwrite file cũ. |
| File log tích lũy qua nhiều lần chạy | Append, có batch marker và quy tắc deduplication/retention. |
| Không được ghi đè file đã được consumer nhận | Fail if exists hoặc ghi staging rồi publish với kiểm soát version. |
| Restart cùng job phải tiếp tục file chưa hoàn tất | Giữ output path, `saveState(true)` và checkpoint ổn định. |
| Nhiều partition cùng export dữ liệu | Mỗi partition ghi file riêng rồi merge tuần tự. |
| Consumer không được đọc file chưa hoàn tất | Ghi file tạm rồi move/rename sau validation. |
| Một batch lỗi không được làm hỏng output đã publish trước đó | Tạo staging output riêng và chỉ thay file chính thức khi publish thành công. |

## 22. Những lỗi thường gặp

| Vấn đề | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Dữ liệu lần chạy trước bị mất | Overwrite cùng path cho JobInstance mới. | Tạo path theo batch/date hoặc dùng staging. |
| File có dòng lặp | Append cùng input nhiều lần hoặc restart không khôi phục state. | Dùng `saveState(true)`, giữ writer name/path và idempotency. |
| Restart ghi vào file khác | Output path được tạo từ tham số thay đổi ở lần restart. | Giữ path ổn định cho cùng JobInstance. |
| File rỗng biến mất | `shouldDeleteIfEmpty(true)`. | Đặt false nếu hợp đồng cần file rỗng. |
| Step lỗi khi file đã tồn tại | `shouldDeleteIfExists(false)` và append tắt. | Chọn overwrite, append hoặc tạo tên file mới theo nghiệp vụ. |
| Header bị lặp | Header callback được xử lý trong các lần mở/append theo cách không mong đợi. | Kiểm thử header/footer trên file mới, file cũ và restart. |
| File chứa dữ liệu chưa commit | Writer không transactional hoặc tác dụng phụ file ngoài transaction. | Dùng transaction-aware writer mặc định phù hợp, staging và reconciliation. |
| Nhiều partition ghi xen dòng | Nhiều worker dùng chung một output resource. | Tách file theo partition rồi merge. |
| Hai job ghi đè file của nhau | Cùng output path và không có khóa/ownership. | Dùng path riêng hoặc cơ chế khóa liên process. |
| File chính thức bị thay thế dù batch chưa hoàn tất | Ghi trực tiếp vào final resource. | Ghi staging, validate rồi publish. |
| Test phụ thuộc file từ lần trước | Dùng đường dẫn cố định và không dọn temp resource. | Dùng thư mục tạm riêng cho mỗi test. |

## 23. Quy trình chọn append hay overwrite

Trước khi cấu hình writer, hãy trả lời các câu hỏi:

1. File đại diện cho snapshot của một lần chạy hay là log tích lũy?
2. Nếu file đã tồn tại khi khởi chạy JobInstance mới, cần thay thế, nối thêm hay từ chối?
3. Khi restart cùng JobInstance, output path và nội dung file có được giữ ổn định không?
4. Writer có lưu checkpoint bằng `saveState(true)` không?
5. Header/footer thuộc toàn file hay từng batch segment?
6. Nếu step không ghi item, file rỗng có cần được giữ lại không?
7. Có nhiều job/partition/process có thể ghi cùng resource không?
8. Consumer có thể nhìn thấy file khi batch đang ghi không?
9. Nếu publish file thành công nhưng metadata commit thất bại, lần restart xử lý thế nào?
10. Có thể đối soát hoặc tái tạo output từ nguồn nếu file bị hỏng không?

Trả lời các câu hỏi này trước khi chọn `.append(...)` và `.shouldDeleteIfExists(...)` sẽ giúp chính sách output phản ánh đúng vòng đời dữ liệu.

## 24. Những điểm cần ghi nhớ

- `FlatFileItemWriter` có thể overwrite file hiện có, append vào cuối hoặc từ chối nếu file đã tồn tại.
- `.append(true)` bật chế độ nối thêm; `.append(false)` kết hợp `shouldDeleteIfExists(true)` thể hiện overwrite.
- `.append(false)` kết hợp `shouldDeleteIfExists(false)` phù hợp khi cần fail nếu file tồn tại.
- `shouldDeleteIfEmpty` quyết định có giữ file không có item hay không.
- Append cho lần chạy mới khác cơ chế restart của cùng JobInstance.
- `saveState(true)` và `ExecutionContext` giúp writer khôi phục trạng thái khi restart; append đơn thuần không chống trùng.
- Giữ writer name, output path và identifying parameters ổn định trong cùng JobInstance.
- Không dùng cùng file path cho các JobInstance chạy đồng thời nếu không có cơ chế đồng bộ/ownership.
- Header/footer callback cần được thiết kế theo cấu trúc file tích lũy và kiểm thử trên append/restart.
- Transactional writing giúp phối hợp với transaction chunk, nhưng file system không phải transaction database toàn cục.
- Với output quan trọng, nên ghi file staging, validate rồi publish/rename để consumer không đọc dữ liệu dở dang.
- Với partitioning, ưu tiên file riêng cho từng worker rồi merge tuần tự.
- Kiểm thử file mới, file đã tồn tại, append, overwrite, fail-if-exists, empty output và restart bằng JobRepository thực tế.

Chọn append hay overwrite là quyết định về vòng đời của output. Hãy xác định file là snapshot hay dữ liệu tích lũy, phân biệt lần chạy mới với restart, giữ checkpoint và output path ổn định, đồng thời kiểm soát việc nhiều execution cùng ghi một resource. Khi kết hợp chính sách file với staging, validation và idempotency, batch có thể tạo output đáng tin cậy mà không làm mất hoặc nhân đôi dữ liệu.
