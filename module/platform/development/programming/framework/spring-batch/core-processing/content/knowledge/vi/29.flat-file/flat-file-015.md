# HeaderCallback và FooterCallback

Trong Spring Batch, `FlatFileItemWriter` hỗ trợ ghi nội dung bổ sung ở đầu và cuối file thông qua `FlatFileHeaderCallback` và `FlatFileFooterCallback`. Header thường chứa tên cột, thông tin batch hoặc metadata của file; footer có thể chứa tổng số bản ghi, mã lô hoặc dấu kết thúc file.

Hai callback này thuộc vòng đời của Writer. Header được ghi khi Writer mở file cho một lần ghi mới; footer được gọi khi Writer đóng. Chúng không phải `ItemReader`, `ItemProcessor` hay `ItemWriter` riêng, và không chạy một lần cho mỗi item hoặc mỗi chunk.

## 1. Header và footer trong file batch

Một file xuất thường có ba phần:

```text
HEADER
order_id,customer_id,amount

DATA RECORDS
ORD-1001,CUST-01,125.50
ORD-1002,CUST-02,89.90
ORD-1003,CUST-03,240.00

FOOTER
# records=3
# batch=orders-2026-11-15
```

- Header mô tả cấu trúc hoặc nguồn gốc của file.
- Các dòng dữ liệu được tạo bởi `LineAggregator` của `FlatFileItemWriter`.
- Footer có thể ghi tổng số dòng, checksum, mã batch hoặc marker cho biết file đã được đóng.

Header và footer hữu ích khi file được trao đổi với hệ thống khác, cần có schema dễ nhận diện hoặc cần kiểm tra số lượng bản ghi sau khi truyền tải. Nếu định dạng file của hệ thống nhận không cho phép dòng header/footer, không nên tự thêm chúng vì có thể làm dữ liệu không còn đúng hợp đồng.

## 2. FlatFileHeaderCallback và FlatFileFooterCallback

Spring Batch cung cấp hai callback interface:

```java
public interface FlatFileHeaderCallback {
    void writeHeader(Writer writer) throws IOException;
}

public interface FlatFileFooterCallback {
    void writeFooter(Writer writer) throws IOException;
}
```

Mỗi callback nhận một `java.io.Writer` để ghi ký tự vào output stream do `FlatFileItemWriter` quản lý.

- `writeHeader(Writer)`: ghi nội dung header khi Writer khởi tạo file output.
- `writeFooter(Writer)`: ghi nội dung footer khi Writer đóng.

Vì callback ghi trực tiếp vào `Writer`, cần tự ghi ký tự xuống dòng nếu muốn header/footer nằm trên dòng riêng. Callback không nhận `Chunk` hoặc item hiện tại. Nếu footer cần số liệu xử lý, phải lấy số liệu từ một nguồn phù hợp như `StepExecution` hoặc một accumulator có scope đúng.

Không gọi `close()` trên Writer được truyền vào callback. Vòng đời của stream do Spring Batch quản lý; callback chỉ ghi phần nội dung của mình.

## 3. Cấu hình header bằng FlatFileItemWriterBuilder

Với Spring Batch 5 trở lên, có thể cấu hình header bằng `headerCallback(...)` trên `FlatFileItemWriterBuilder`:

```java
import java.io.IOException;
import java.io.Writer;

import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.FlatFileHeaderCallback;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.core.io.FileSystemResource;

FlatFileHeaderCallback headerCallback = writer -> {
    writer.write("order_id,customer_id,amount");
    writer.write("\n");
};

FlatFileItemWriter<ExportOrder> itemWriter =
        new FlatFileItemWriterBuilder<ExportOrder>()
                .name("orderExportWriter")
                .resource(new FileSystemResource("/data/out/orders.csv"))
                .encoding("UTF-8")
                .lineSeparator("\n")
                .lineAggregator(order -> String.join(",",
                        order.orderId(),
                        order.customerId(),
                        order.amount().toPlainString()))
                .headerCallback(headerCallback)
                .saveState(true)
                .shouldDeleteIfExists(true)
                .build();
```

Khi Writer mở file mới, callback ghi dòng tên cột trước các record. `lineSeparator("\n")` cấu hình dấu xuống dòng cho các item do Writer ghi; callback tự ghi newline vì nó thao tác trực tiếp với `Writer`.

Ví dụ dùng `String.join()` để minh họa. Nếu field có dấu phẩy, dấu quote hoặc newline, cần dùng cách escape/quote CSV đúng chuẩn hoặc thư viện CSV phù hợp. Header phải mô tả đúng thứ tự field do `lineAggregator` tạo ra.

## 4. Cấu hình footer bằng FlatFileFooterCallback

Footer callback được đăng ký bằng `footerCallback(...)`:

```java
import org.springframework.batch.item.file.FlatFileFooterCallback;

FlatFileFooterCallback footerCallback = writer -> {
    writer.write("# end-of-export");
    writer.write("\n");
};

FlatFileItemWriter<ExportOrder> itemWriter =
        new FlatFileItemWriterBuilder<ExportOrder>()
                .name("orderExportWriter")
                .resource(new FileSystemResource("/data/out/orders.csv"))
                .encoding("UTF-8")
                .lineSeparator("\n")
                .lineAggregator(this::toCsvLine)
                .headerCallback(writer -> {
                    writer.write("order_id,customer_id,amount\n");
                })
                .footerCallback(footerCallback)
                .saveState(true)
                .shouldDeleteIfExists(true)
                .build();
```

Footer có thể chứa một marker hoặc thông tin tổng hợp. Ví dụ `# end-of-export` giúp consumer nhận diện ranh giới cuối file nếu định dạng trao đổi cho phép dòng comment.

Footer callback được gọi khi Writer đóng, không phải sau mỗi chunk. Không nên đặt logic gửi email, gọi API hoặc cập nhật một quy trình nghiệp vụ dài bên trong callback. Hãy dùng callback để ghi nội dung file; các bước publish và thông báo nên được điều phối riêng.

## 5. Ghi header/footer động theo JobParameters

Header thường cần chứa mã batch, ngày nghiệp vụ hoặc tên nguồn. Có thể inject JobParameters vào Writer `@StepScope` rồi capture giá trị trong callback:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemWriter<ExportOrder> orderExportWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile,
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new FlatFileItemWriterBuilder<ExportOrder>()
            .name("orderExportWriter")
            .resource(new FileSystemResource(outputFile))
            .encoding("UTF-8")
            .lineSeparator("\n")
            .lineAggregator(this::toCsvLine)
            .headerCallback(writer -> {
                writer.write("# batch=" + batchId + "\n");
                writer.write("# business-date=" + businessDate + "\n");
                writer.write("order_id,customer_id,amount\n");
            })
            .footerCallback(writer -> {
                writer.write("# batch-end=" + batchId + "\n");
            })
            .saveState(true)
            .shouldDeleteIfExists(true)
            .build();
}
```

`@StepScope` bảo đảm target Writer được tạo cho StepExecution hiện tại và nhận các JobParameters của lần chạy đó. Nếu nhiều JobExecution chạy đồng thời, không nên lưu batch ID trong field mutable của một Writer singleton dùng chung.

Chỉ đưa giá trị vào header/footer nếu hệ thống nhận cho phép metadata đó. Nếu file là hợp đồng CSV thuần với header đúng một dòng tên cột, thêm dòng comment có thể khiến consumer đọc file sai. Có thể lưu metadata vào manifest riêng thay vì đưa vào CSV.

## 6. Ghi số liệu động trong footer

Footer đôi khi cần chứa tổng số bản ghi đã ghi hoặc số lỗi đã skip. Callback chỉ nhận `Writer`, vì vậy cần cung cấp số liệu qua một nguồn khác. Một cách là inject `StepExecution` vào Step-scoped Writer:

```java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;

@Bean
@StepScope
public FlatFileItemWriter<ExportOrder> orderExportWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile,
        @Value("#{stepExecution}") StepExecution stepExecution) {

    return new FlatFileItemWriterBuilder<ExportOrder>()
            .name("orderExportWriter")
            .resource(new FileSystemResource(outputFile))
            .lineAggregator(this::toCsvLine)
            .footerCallback(writer -> {
                writer.write("# written=" + stepExecution.getWriteCount() + "\n");
                writer.write("# skipped=" + stepExecution.getSkipCount() + "\n");
            })
            .saveState(true)
            .build();
}
```

Ví dụ này minh họa việc đọc bộ đếm của StepExecution tại thời điểm đóng Writer. `writeCount` là số item được ghi theo metadata Step; `skipCount` là tổng lỗi được skip trong StepExecution. Nếu footer cần tổng hợp dữ liệu phức tạp hoặc số liệu qua nhiều Step/JobExecution, hãy tính và lưu kết quả ở service hoặc Step riêng rồi publish sau khi Job hoàn tất.

Không dùng một `int totalRows` mutable trong callback object singleton để cộng dồn giữa nhiều JobExecution. Giá trị có thể bị trộn giữa các lần chạy đồng thời và mất khi restart. Nếu cần accumulator, hãy đặt nó trong `@StepScope` hoặc dùng dữ liệu bền vững gắn với execution/batch ID.

## 7. Callback có chạy lại khi restart không?

Header và footer có hành vi khác nhau trong restart:

- Khi Writer mở cho lần thực thi mới, header callback được dùng để ghi header.
- Khi restart với ExecutionContext đã lưu, Writer khôi phục vị trí ghi từ checkpoint; header không nên được ghi lặp vào giữa file.
- Khi Writer đóng, footer callback được gọi để ghi footer.

Giả sử Job ghi hai chunk rồi thất bại ở chunk thứ ba:

```text
Lần chạy đầu
  open -> ghi header
  chunk 1 -> commit
  chunk 2 -> commit
  chunk 3 -> lỗi / rollback
  close -> footer callback

Restart cùng JobInstance
  open -> khôi phục checkpoint, cắt phần chưa commit/footer sau checkpoint
  tiếp tục chunk 3
  close -> ghi footer cho lần đóng mới
```

Footer có thể được ghi khi Writer đóng dù Job chưa `COMPLETED`, chẳng hạn Step kết thúc vì lỗi hoặc dừng. Vì vậy, không dùng sự hiện diện của footer làm bằng chứng duy nhất rằng Job thành công. Nếu consumer chỉ được đọc file hoàn tất, hãy dùng một Step publish sau khi Job/flow xử lý thành công hoặc tạo manifest trạng thái hoàn tất.

Restart cũng phụ thuộc `saveState(true)`, tên Writer ổn định và file output không bị thay đổi ngoài Spring Batch. Nếu xóa file hoặc sửa nội dung sau checkpoint, vị trí ghi đã lưu có thể không còn phù hợp.

## 8. HeaderCallback với append và file đã tồn tại

`FlatFileItemWriterBuilder` có các tùy chọn như `append(true)` và `shouldDeleteIfExists(true)`. Chúng quyết định cách Writer xử lý file cũ khi mở cho một lần ghi mới.

```java
new FlatFileItemWriterBuilder<ExportOrder>()
        .name("auditWriter")
        .resource(new FileSystemResource(outputFile))
        .lineAggregator(this::toCsvLine)
        .append(true)
        .saveState(true)
        .build();
```

Append có thể phù hợp với file log hoặc định dạng append-only, nhưng cần xác định rõ header có được ghi lại khi mở file hiện hữu hay không. Nếu callback luôn thêm header mà file đã có nội dung, có thể xuất hiện header lặp ở giữa file. Hãy kiểm thử chính xác cấu hình append của phiên bản Spring Batch đang dùng và chọn một trong các cách:

1. Dùng file output mới, riêng cho từng JobInstance/batch ID.
2. Ghi header trong một file manifest riêng.
3. Dùng callback có điều kiện dựa trên trạng thái file nếu hợp đồng cho phép và việc kiểm tra không tạo race condition.
4. Không append nếu định dạng file yêu cầu đúng một header ở đầu.

`append(true)` không thay thế cơ chế restart. Khi restart một Step, Writer cần khôi phục checkpoint của chính lần thực thi; không được tự ý đổi file hoặc nối dữ liệu bằng một tiến trình ngoài trong lúc Job đang chạy.

## 9. Footer không phải tín hiệu Job thành công

Footer callback gắn với vòng đời đóng Writer. Writer có thể được đóng khi Step kết thúc thành công, thất bại hoặc dừng. Vì vậy, footer như `# COMPLETE` có thể gây hiểu nhầm nếu Job chưa hoàn tất toàn bộ flow.

Nếu consumer cần biết file đã sẵn sàng, nên dùng quy trình publish rõ ràng:

```text
Export Step
   |
   +--> ghi orders.csv.part
   +--> header + records + footer kỹ thuật
   |
   v
Job/flow xác nhận các Step thành công
   |
   v
Publish Step
   |
   +--> kiểm tra file / checksum / số dòng
   +--> rename hoặc copy sang orders.csv
   +--> ghi manifest trạng thái COMPLETE
   |
   v
Consumer được phép đọc file cuối
```

Ghi file tạm và publish sau khi thành công giúp consumer không đọc file đang được tạo. Nếu dùng rename nguyên tử, file nguồn và đích thường cần nằm trên cùng filesystem; cần kiểm tra semantics của môi trường lưu trữ thực tế.

Nếu Job thất bại, file `.part` có thể được giữ để restart hoặc điều tra. Không tự động công bố file đó chỉ vì footer callback đã chạy.

## 10. Xử lý lỗi trong callback

Callback có thể ném `IOException` khi ghi header hoặc footer, ví dụ disk đầy, filesystem mất kết nối hoặc Writer không thể ghi. Lỗi này có thể làm Step thất bại.

Ví dụ xử lý trong callback:

```java
.headerCallback(writer -> {
    writer.write("order_id,amount\n");
})
.footerCallback(writer -> {
    writer.write("# end-of-file\n");
})
```

Không nên bắt rồi bỏ qua `IOException` trong callback. Nếu header không ghi được, file có thể không tuân thủ schema; nếu footer không ghi được, file có thể không hoàn chỉnh theo hợp đồng. Hãy để lỗi được phản ánh vào trạng thái Step/Job và ghi log đủ thông tin để điều tra.

Không thực hiện tác vụ không liên quan tới file trong callback, chẳng hạn gửi email hoặc gọi API. Nếu callback thất bại khi đóng Writer, việc xử lý thêm nhiều side effect có thể khiến kết quả khó xác định. Hãy đưa thông báo hoặc publish vào Step/listener riêng và dùng outbox/idempotency nếu cần.

## 11. Header/Footer và định dạng CSV

Header cần khớp thứ tự cột của `LineAggregator`. Ví dụ:

```java
.headerCallback(writer -> {
    writer.write("order_id,customer_id,amount\n");
})
.lineAggregator(order -> String.join(",",
        order.orderId(),
        order.customerId(),
        order.amount().toPlainString()))
```

Nếu `lineAggregator` thay đổi thứ tự thành `customer_id,order_id,amount`, header cũng phải thay đổi tương ứng. Nếu header mô tả sai dữ liệu, consumer có thể gán nhầm cột dù file vẫn parse được.

Footer trong CSV thuần thường không phải record dữ liệu. Nếu hệ thống nhận đọc mọi dòng như một order, dòng `# records=...` sẽ gây lỗi mapping. Có thể dùng một định dạng file có trailer theo hợp đồng, hoặc lưu tổng số bản ghi trong file sidecar như `orders.csv.manifest`.

Đối với CSV cần quote/escape, hãy đảm bảo cả dữ liệu và header tuân theo cùng quy tắc encoding, delimiter và quote. Callback ghi raw text, nên không tự động escape nội dung metadata.

## 12. Header/Footer trong file fixed-width hoặc định dạng tùy chỉnh

Callback không giới hạn ở CSV. Có thể ghi record header/footer theo fixed-width layout:

```java
.headerCallback(writer -> {
    writer.write(String.format(
            "%-8s%-10s%08d",
            "BATCH",
            businessDate,
            expectedRecordCount));
    writer.write("\n");
})
.footerCallback(writer -> {
    writer.write(String.format(
            "%-8s%08d",
            "TRAILER",
            actualRecordCount));
    writer.write("\n");
})
```

Định dạng minh họa cần được điều chỉnh theo đặc tả của hệ thống nhận: độ rộng field, padding, charset, số chữ số và quy tắc checksum. `String.format()` mặc định có thể phụ thuộc locale với một số kiểu; nếu định dạng số phải cố định, hãy dùng locale rõ ràng hoặc tự định dạng theo hợp đồng.

Nếu footer cần checksum của toàn bộ file, cần tính checksum trên đúng byte sequence đã ghi, bao gồm hay không bao gồm header/footer theo đặc tả. Không nên tính trên chuỗi Java trước encoding nếu hệ thống nhận xác minh checksum ở mức byte.

## 13. Kết hợp callback với JobExecution/StepExecution

Header có thể cần thông tin của JobExecution như JobInstance ID, ngày nghiệp vụ hoặc mã nguồn. Footer có thể cần bộ đếm Step. Các giá trị này nên được inject vào Step-scoped Writer:

```java
@Bean
@StepScope
public FlatFileItemWriter<ExportOrder> exportWriter(
        @Value("#{jobExecution.id}") Long executionId,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{stepExecution}") StepExecution stepExecution,
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<ExportOrder>()
            .name("exportWriter")
            .resource(new FileSystemResource(outputFile))
            .lineAggregator(this::toCsvLine)
            .headerCallback(writer -> writer.write(
                    "# execution=" + executionId
                            + ", businessDate=" + businessDate + "\n"))
            .footerCallback(writer -> writer.write(
                    "# written=" + stepExecution.getWriteCount() + "\n"))
            .saveState(true)
            .build();
}
```

Ví dụ dùng `jobExecution.id` cho trace và `stepExecution` để lấy bộ đếm. ID JobExecution thay đổi khi restart, vì vậy nếu header phải giữ nguyên qua các lần restart của cùng một JobInstance, không nên đưa execution ID vào nội dung header nếu Writer không ghi lại header khi restart. Có thể dùng JobInstance ID hoặc identifying business key ổn định thay thế.

Không ghi JobParameters nhạy cảm như token, password hoặc thông tin cá nhân không cần thiết vào header. Nội dung file thường được chia sẻ ra ngoài và có thể tồn tại lâu hơn metadata nội bộ.

## 14. Kiểm thử HeaderCallback và FooterCallback

Nên kiểm tra file thực tế được tạo ra, thứ tự header/data/footer, encoding và hành vi restart. Chỉ kiểm tra callback được gọi chưa đủ để xác nhận file có định dạng đúng.

Các trường hợp nên kiểm thử:

1. **File mới:** header xuất hiện đúng một lần ở đầu file.
2. **Có dữ liệu:** record được ghi theo đúng thứ tự field và delimiter.
3. **Không có item:** xác định rõ file rỗng có header/footer hay bị xóa theo cấu hình `shouldDeleteIfEmpty`.
4. **Footer:** footer xuất hiện ở cuối sau khi Writer đóng.
5. **Restart:** header không bị lặp ở giữa file; Writer khôi phục đúng vị trí đã commit và footer cuối cùng chỉ còn đúng vị trí mong muốn.
6. **Append:** kiểm tra có/không có header lặp theo cấu hình và hợp đồng file.
7. **Callback lỗi:** mô phỏng lỗi ghi để xác nhận Step/Job phản ánh lỗi phù hợp.
8. **Job thất bại:** xác nhận footer không bị dùng nhầm như tín hiệu file đã publish thành công.

Ví dụ test với JUnit và thư mục tạm:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class ExportHeaderFooterTest {

    @TempDir
    Path tempDir;

    @Test
    void writesHeaderRecordsAndFooter() throws Exception {
        Path output = tempDir.resolve("orders.csv");

        // Launch Step test với output path trỏ đến output.

        List<String> lines = Files.readAllLines(output);
        assertEquals("order_id,customer_id,amount", lines.get(0));
        assertTrue(lines.get(lines.size() - 1).startsWith("# records="));
    }
}
```

Đây là khung test; phần launch cần kết nối với Job/Step test và `JobLauncherTestUtils` của ứng dụng. Với restart test, giữ nguyên identifying JobParameters và output path giữa hai lần chạy. Tạo lỗi sau một chunk đã commit, restart cùng JobInstance rồi xác nhận header không lặp, record không trùng và footer cuối cùng nằm đúng vị trí.

## 15. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Ghi newline không đúng trong callback | Callback ghi raw text, không tự thêm line separator cho nội dung header/footer. | Ghi rõ `\n` hoặc newline theo hợp đồng file. |
| Header không khớp LineAggregator | Thứ tự hoặc tên cột thay đổi nhưng header không đổi. | Quản lý header và mapping cùng một schema. |
| Footer được xem là bằng chứng Job thành công | Writer có thể đóng cả khi Step lỗi hoặc dừng. | Publish file ở Step riêng sau khi flow thành công. |
| Footer dùng field mutable của singleton | Nhiều execution đồng thời có thể trộn số liệu. | Dùng `@StepScope`, StepExecution hoặc store theo execution ID. |
| Header lặp khi append | Callback có thể ghi header khi mở file append. | Kiểm thử append; dùng file riêng hoặc manifest nếu cần. |
| Header lặp khi restart | Writer không khôi phục đúng state hoặc cấu hình/file bị thay đổi. | Bật `saveState`, giữ tên Writer và file ổn định. |
| Gọi API trong footer callback | Callback chạy khi Writer đóng, kể cả tình huống không thành công như mong đợi. | Tách side effect sang Step/listener/outbox. |
| Footer chứa dòng không đúng schema CSV | Consumer coi trailer là record dữ liệu. | Dùng định dạng trailer được hỗ trợ hoặc sidecar manifest. |
| Bắt và bỏ qua IOException | File có thể thiếu header/footer nhưng Step vẫn bị báo thành công. | Để lỗi I/O được phản ánh và xử lý rõ ràng. |

## Kết luận

`FlatFileHeaderCallback` và `FlatFileFooterCallback` cho phép `FlatFileItemWriter` ghi metadata ở đầu và cuối file. Header callback ghi tên cột hoặc thông tin batch khi Writer mở file; footer callback ghi tổng kết hoặc trailer khi Writer đóng. Cần tự quản lý newline, giữ header khớp với LineAggregator, lấy số liệu qua Step-scoped state và hiểu hành vi callback khi append/restart. Footer không chứng minh Job đã `COMPLETED`, vì Writer có thể đóng khi Step thất bại hoặc dừng. Với file bàn giao quan trọng, hãy ghi file tạm và publish bằng Step riêng sau khi Job flow thành công; kiểm thử file thực tế qua cả lần chạy mới và restart để tránh header/footer lặp hoặc sai định dạng.
