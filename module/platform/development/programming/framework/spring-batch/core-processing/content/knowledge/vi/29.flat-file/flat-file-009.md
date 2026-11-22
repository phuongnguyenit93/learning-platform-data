# Header và footer callback trong Spring Batch

Khi xuất dữ liệu ra file bằng Spring Batch, nội dung thường cần thêm thông tin ngoài các dòng dữ liệu chính. Một file CSV có thể bắt đầu bằng tên báo cáo, ngày nghiệp vụ và tên cột; cuối file có thể chứa tổng số bản ghi, tổng tiền, mã lô hoặc dấu kết thúc. Những phần này được gọi là **header** và **footer**.

Với **FlatFileItemWriter**, Spring Batch cung cấp hai callback chuyên dụng: **FlatFileHeaderCallback** và **FlatFileFooterCallback**. Header callback ghi nội dung đầu file khi writer khởi tạo file output; footer callback ghi phần cuối khi writer đóng file. Callback nhận một đối tượng Writer do framework quản lý, nên chỉ cần ghi nội dung vào đó.

Header và footer callback thuộc lifecycle của file writer. Chúng không phải listener được gọi cho từng item và cũng không phải tín hiệu xác nhận toàn bộ Job đã thành công. Đặc biệt, writer có thể được đóng trong đường đi thất bại của Step; vì vậy footer callback có thể được gọi ngay cả khi Job không hoàn tất thành công. Nếu cần công bố file chính thức hoặc ghi dấu SUCCESS, hãy thực hiện bằng một bước publish sau khi các bước xử lý đã hoàn tất.

Bài học này giải thích hợp đồng của hai callback, cách cấu hình FlatFileItemWriter, cách tạo header/footer tĩnh và động, cách kết hợp với JobParameters và StepExecution, hành vi khi file rỗng hoặc restart, cách xử lý nhiều file, cùng các lưu ý về transaction, encoding, CSV escaping và kiểm thử.

## 1. Header và footer trong file batch

Một file xuất thường có cấu trúc:

~~~text
CUSTOMER EXPORT
Business date: 2026-11-15
customer_id,full_name,email
C001,An,an@example.test
C002,Binh,binh@example.test
C003,Chi,chi@example.test
TOTAL_RECORDS,3
END_OF_FILE
~~~

Trong ví dụ, các dòng đầu file là header; các dòng dữ liệu được tạo bởi ItemWriter và LineAggregator; các dòng cuối file là footer hoặc trailer.

Header thường chứa metadata mô tả file hoặc dòng tên cột. Footer thường chứa tổng số record, tổng giá trị, checksum hoặc mã kết thúc để hệ thống nhận file biết nội dung đã được đóng.

Không phải định dạng nào cũng cần cả hai. CSV đơn giản có thể chỉ cần dòng tên cột. Một file trao đổi dữ liệu cố định có thể cần trailer theo đặc tả đối tác. Hãy dùng callback khi định dạng file yêu cầu phần đầu hoặc cuối file.

## 2. Hai callback do Spring Batch cung cấp

Spring Batch cung cấp hai interface trong phần file support:

~~~java
public interface FlatFileHeaderCallback {
    void writeHeader(Writer writer) throws IOException;
}
~~~

~~~java
public interface FlatFileFooterCallback {
    void writeFooter(Writer writer) throws IOException;
}
~~~

Cả hai callback nhận một java.io.Writer.

- Header callback ghi nội dung đầu file.
- Footer callback ghi nội dung cuối file.
- Callback không nhận item hoặc chunk.
- Callback không tự mở file và không sở hữu Writer.
- Spring Batch quản lý vòng đời Writer; callback chỉ ghi nội dung.

Thông thường callback được cấu hình trực tiếp trên FlatFileItemWriter bằng builder:

~~~java
.headerCallback(headerCallback)
.footerCallback(footerCallback)
~~~

Callback là một phần của file writer. Nếu dùng một ItemWriter khác, chẳng hạn JdbcBatchItemWriter, các phương thức này không tự tồn tại. Khi đó cần triển khai logic riêng hoặc dùng một writer hỗ trợ file.

### Không đóng Writer trong callback

Đối tượng Writer được truyền vào callback thuộc quyền quản lý của FlatFileItemWriter. Callback chỉ nên gọi write() để ghi dữ liệu.

Không gọi close() trên Writer, không tự mở một FileWriter khác ghi vào cùng đường dẫn và không xóa hoặc đổi tên file trong callback. Việc đóng hoặc mở thêm writer có thể làm hỏng buffer, thứ tự ghi hoặc trạng thái restart của FlatFileItemWriter.

## 3. Header callback được gọi khi nào?

Header callback được FlatFileItemWriter gọi trong quá trình mở output file khi writer xác định cần khởi tạo nội dung đầu file. Với file mới hoặc file rỗng, callback có thể ghi tiêu đề trước các item đầu tiên.

Ví dụ:

~~~java
FlatFileHeaderCallback header = writer -> {
    writer.write("customer_id,full_name,email");
    writer.write(System.lineSeparator());
};
~~~

Khi writer bắt đầu ghi item, nội dung header đã được đặt trước các dòng dữ liệu.

Header callback không chạy cho từng item hoặc từng chunk. Nó thuộc vòng đời mở file. Khi file được mở lại do restart, hành vi phụ thuộc trạng thái file, checkpoint, append configuration và phiên bản writer. Thông thường writer khôi phục file đã có nội dung mà không thêm lại header vào giữa file.

Không nên dựa vào giả định chung rằng callback luôn chạy đúng một lần cho toàn bộ Job. Với restart, append, file rỗng hoặc multi-resource output, hãy kiểm thử chính xác số lần callback được gọi.

## 4. Footer callback được gọi khi nào?

Footer callback được FlatFileItemWriter gọi trong quá trình đóng output file:

~~~java
FlatFileFooterCallback footer = writer -> {
    writer.write("END_OF_FILE");
    writer.write(System.lineSeparator());
};
~~~

Footer được ghi sau các dòng dữ liệu đã được writer xử lý trước khi writer hoàn tất việc đóng file. Footer callback không được gọi sau mỗi chunk; nó là callback ở cuối vòng đời writer.

### Footer không đồng nghĩa Job thành công

Đây là điểm quan trọng khi thiết kế file batch.

Spring Batch cần đóng các ItemStream đã đăng ký khi Step kết thúc theo lifecycle thông thường, kể cả khi Step thất bại do exception. Vì FlatFileItemWriter ghi footer trong quá trình close, footer callback có thể chạy trên đường kết thúc thất bại.

Do đó, không nên ghi nội dung mang nghĩa JOB_STATUS,SUCCESS chỉ vì footer callback đã được gọi.

Nếu file cần một trailer kỹ thuật, có thể ghi END_OF_FILE hoặc tổng số record đã ghi. Nếu cần dấu xác nhận file đã được kiểm tra và công bố thành công, hãy tạo publish Step chỉ chạy sau khi xử lý thành công.

## 5. Cấu hình FlatFileItemWriter với header và footer

Ví dụ đầy đủ dùng FlatFileItemWriterBuilder:

~~~java
@Bean
FlatFileItemWriter<Customer> customerWriter(Resource outputResource) {

    BeanWrapperFieldExtractor<Customer> extractor =
        new BeanWrapperFieldExtractor<>();

    extractor.setNames(new String[] {
        "customerId",
        "fullName",
        "email"
    });

    DelimitedLineAggregator<Customer> aggregator =
        new DelimitedLineAggregator<>();

    aggregator.setDelimiter(",");
    aggregator.setFieldExtractor(extractor);

    return new FlatFileItemWriterBuilder<Customer>()
        .name("customerWriter")
        .resource(outputResource)
        .encoding(StandardCharsets.UTF_8.name())
        .lineSeparator(System.lineSeparator())
        .lineAggregator(aggregator)
        .headerCallback(writer -> {
            writer.write("customer_id,full_name,email");
            writer.write(System.lineSeparator());
        })
        .footerCallback(writer -> {
            writer.write("END_OF_FILE");
            writer.write(System.lineSeparator());
        })
        .saveState(true)
        .build();
}
~~~

Các phần quan trọng:

- name đặt tên ổn định cho writer, cần thiết để lưu state.
- resource xác định file output.
- encoding chọn charset.
- lineSeparator đặt ký tự xuống dòng cho record do LineAggregator tạo.
- lineAggregator chuyển từng item thành một dòng.
- headerCallback ghi phần đầu file.
- footerCallback ghi phần cuối file.
- saveState(true) cho phép writer lưu trạng thái phục vụ restart.

Trong ví dụ, callback tự ghi ký tự xuống dòng. Thuộc tính lineSeparator của writer áp dụng cho các dòng dữ liệu do writer ghi; callback ghi trực tiếp vào Writer nên cần thêm newline khi định dạng yêu cầu.

## 6. Header callback dạng lambda

Vì interface chỉ có một phương thức trừu tượng, có thể khai báo callback bằng lambda:

~~~java
.headerCallback(writer ->
    writer.write("id,name,email" + System.lineSeparator())
)
~~~

Cách này phù hợp với header ngắn, cố định và không cần dependency.

Nếu header dài hoặc có logic định dạng, tách thành bean riêng để dễ đọc và kiểm thử:

~~~java
@Bean
FlatFileHeaderCallback customerHeaderCallback() {
    return writer -> {
        writer.write("CUSTOMER EXPORT");
        writer.write(System.lineSeparator());
        writer.write("customer_id,full_name,email");
        writer.write(System.lineSeparator());
    };
}
~~~

Sau đó inject callback vào writer:

~~~java
@Bean
FlatFileItemWriter<Customer> customerWriter(
        Resource outputResource,
        FlatFileHeaderCallback customerHeaderCallback) {

    return new FlatFileItemWriterBuilder<Customer>()
        .name("customerWriter")
        .resource(outputResource)
        .lineAggregator(customerLineAggregator())
        .headerCallback(customerHeaderCallback)
        .build();
}
~~~

Tách callback giúp dùng lại định dạng giữa các writer và test nội dung header độc lập.

## 7. Footer callback dạng lambda

Footer đơn giản cũng có thể viết trực tiếp:

~~~java
.footerCallback(writer -> {
    writer.write("TOTAL_RECORDS,0");
    writer.write(System.lineSeparator());
})
~~~

Ví dụ trên là footer cố định, chỉ phù hợp khi giá trị thực sự cố định. Trong thực tế footer thường chứa số record hoặc tổng tiền. Khi đó cần lấy dữ liệu tổng hợp từ trạng thái của Step hoặc một thành phần quản lý riêng.

Không nên tính lại toàn bộ dữ liệu nguồn trong footer callback. Callback chỉ nên ghi trailer dựa trên trạng thái đã được tổng hợp trong quá trình xử lý.

## 8. Header động từ JobParameters

Header có thể chứa ngày nghiệp vụ, mã lô hoặc hệ thống nguồn do caller truyền khi launch Job.

Ví dụ JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15")
    .addString("batchId", "BATCH-20261115")
    .addString("sourceSystem", "CRM")
    .toJobParameters();
~~~

Khai báo callback StepScope để late-bind các tham số:

~~~java
@Bean
@StepScope
FlatFileHeaderCallback customerHeaderCallback(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{jobParameters['sourceSystem']}") String sourceSystem) {

    return writer -> {
        writer.write("CUSTOMER EXPORT");
        writer.write(System.lineSeparator());
        writer.write("Business date: " + businessDate);
        writer.write(System.lineSeparator());
        writer.write("Batch: " + batchId);
        writer.write(System.lineSeparator());
        writer.write("Source: " + sourceSystem);
        writer.write(System.lineSeparator());
        writer.write("customer_id,full_name,email");
        writer.write(System.lineSeparator());
    };
}
~~~

Gắn callback vào writer:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Customer> customerWriter(
        @Value("#{jobParameters['output.file']}") String outputFile,
        FlatFileHeaderCallback customerHeaderCallback,
        FlatFileFooterCallback customerFooterCallback) {

    return new FlatFileItemWriterBuilder<Customer>()
        .name("customerWriter")
        .resource(new FileSystemResource(outputFile))
        .lineAggregator(customerLineAggregator())
        .headerCallback(customerHeaderCallback)
        .footerCallback(customerFooterCallback)
        .saveState(true)
        .build();
}
~~~

@StepScope trì hoãn việc tạo target callback và writer đến khi StepExecution tồn tại. Vì vậy, callback có thể nhận JobParameters của lần chạy hiện tại.

### Kiểm tra tham số bắt buộc

Nếu businessDate hoặc batchId là bắt buộc, hãy kiểm tra null và blank trước khi tạo header. Không nên âm thầm ghi giá trị null vào file vì downstream có thể hiểu đó là metadata hợp lệ.

JobParametersValidator có thể kiểm tra tham số trước khi Job chạy; scoped callback vẫn nên bảo vệ các giá trị trực tiếp cần dùng.

## 9. Header động từ ExecutionContext

Một Step trước có thể kiểm tra file và lưu metadata vào JobExecutionContext. Step xuất file sau đó dùng late binding để ghi thông tin đó vào header.

Ví dụ Step trước lưu source version:

~~~java
contribution.getStepExecution()
    .getExecutionContext()
    .putString("sourceVersion", sourceVersion);

contribution.getStepExecution()
    .getExecutionContext()
    .putString("validatedFile", validatedFile);
~~~

Nếu Step sau cần các key này, promote chúng lên JobExecutionContext bằng ExecutionContextPromotionListener hoặc ghi vào JobExecutionContext theo cơ chế phù hợp.

Callback đọc metadata:

~~~java
@Bean
@StepScope
FlatFileHeaderCallback exportHeaderCallback(
        @Value("#{jobExecutionContext['sourceVersion']}")
        String sourceVersion,
        @Value("#{jobExecutionContext['validatedFile']}")
        String validatedFile) {

    return writer -> {
        writer.write("SOURCE_VERSION," + sourceVersion);
        writer.write(System.lineSeparator());
        writer.write("INPUT_FILE," + validatedFile);
        writer.write(System.lineSeparator());
        writer.write("id,name");
        writer.write(System.lineSeparator());
    };
}
~~~

Không đọc key từ JobExecutionContext nếu key chỉ được ghi vào StepExecutionContext của Step trước mà chưa được promote. Hai context có phạm vi khác nhau.

## 10. Footer chứa số record đã ghi

Một footer thường chứa tổng số record. Footer callback chỉ nhận Writer, nhưng có thể giữ tham chiếu tới StepExecution để đọc bộ đếm tại thời điểm callback được gọi.

Ví dụ:

~~~java
@Bean
@StepScope
FlatFileFooterCallback customerFooterCallback(
        @Value("#{stepExecution}") StepExecution stepExecution) {

    return writer -> {
        writer.write(
            "TOTAL_RECORDS," + stepExecution.getWriteCount()
        );
        writer.write(System.lineSeparator());
    };
}
~~~

Điểm quan trọng là inject đối tượng StepExecution, rồi đọc getWriteCount() khi callback thực thi. Nếu chỉ inject một số scalar bằng biểu thức stepExecution.writeCount lúc target bean được tạo, giá trị có thể được bind quá sớm và không phản ánh bộ đếm cuối cùng.

Bộ đếm writeCount là số item được ghi theo metadata của StepExecution. Nó không nhất thiết bằng số dòng vật lý trong file nếu có header/footer, filter, skip, writer ghi nhiều dòng cho một item hoặc logic tùy chỉnh.

Nếu footer cần tổng tiền, tổng số lượng hoặc checksum, hãy duy trì accumulator phù hợp trong quá trình xử lý và bảo đảm giá trị được cập nhật nhất quán theo transaction/restart. Không dùng writeCount thay cho một phép tổng hợp nghiệp vụ khác.

### Footer không nên công bố trạng thái thành công

Nếu Step thất bại sau một số chunk, writeCount có thể lớn hơn 0 và footer vẫn có thể được ghi khi writer close. Giá trị đó phản ánh số item đã được ghi theo StepExecution, không chứng minh toàn bộ Job đã thành công.

Có thể ghi một trailer mang nghĩa thống kê như ROWS_WRITTEN, nhưng dấu SUCCESS nên được thêm trong bước publish sau khi xác nhận Job/Step thành công.

## 11. Footer chứa tổng tiền hoặc checksum

Một báo cáo tài chính có thể cần tổng số tiền ở cuối file. Có thể duy trì accumulator trong processor hoặc writer.

Ví dụ một thành phần tổng hợp:

~~~java
public class ExportTotals {

    private long recordCount;
    private BigDecimal totalAmount = BigDecimal.ZERO;

    public void add(Invoice invoice) {
        recordCount++;
        totalAmount = totalAmount.add(invoice.amount());
    }

    public long recordCount() {
        return recordCount;
    }

    public BigDecimal totalAmount() {
        return totalAmount;
    }
}
~~~

Writer cập nhật accumulator khi ghi item:

~~~java
@Bean
ItemWriter<Invoice> invoiceWriter(
        FlatFileItemWriter<Invoice> delegate,
        ExportTotals totals) {

    return chunk -> {
        delegate.write(chunk);
        for (Invoice invoice : chunk.getItems()) {
            totals.add(invoice);
        }
    };
}
~~~

Footer callback có thể ghi totals:

~~~java
@Bean
FlatFileFooterCallback invoiceFooter(ExportTotals totals) {
    return writer -> {
        writer.write("TOTAL_RECORDS," + totals.recordCount());
        writer.write(System.lineSeparator());
        writer.write("TOTAL_AMOUNT," + totals.totalAmount().toPlainString());
        writer.write(System.lineSeparator());
    };
}
~~~

Ví dụ này chỉ minh họa cách truyền dữ liệu. Trong một Job restartable hoặc multi-threaded, ExportTotals cần được thiết kế để lưu/khôi phục và cập nhật an toàn. Nếu delegate ghi thành công nhưng accumulator cập nhật rồi transaction rollback, accumulator có thể lệch so với dữ liệu đã commit. Hãy cập nhật state theo chunk commit hoặc tính tổng từ nguồn dữ liệu bền vững sau khi Step hoàn tất.

Với checksum, xác định rõ thuật toán và thứ tự byte/record. Nếu cần checksum cho toàn bộ file, cách chắc chắn là tính sau khi file đã đóng, trong một Step riêng đọc lại file đã hoàn chỉnh.

## 12. Callback không thay thế ItemListener

Header/footer callback và item listener có phạm vi khác nhau.

| Thành phần | Khi được gọi | Mục đích |
|---|---|---|
| FlatFileHeaderCallback | Khi writer khởi tạo phần đầu file | Ghi metadata/header |
| FlatFileFooterCallback | Khi writer đóng file | Ghi trailer/footer |
| ItemReadListener | Trước/sau đọc item hoặc khi đọc lỗi | Quan sát hoạt động reader |
| ItemProcessListener | Trước/sau process hoặc khi process lỗi | Quan sát processor |
| ItemWriteListener | Trước/sau write hoặc khi write lỗi | Quan sát writer |
| StepExecutionListener | Trước/sau Step | Thống kê và lifecycle cấp Step |
| JobExecutionListener | Trước/sau Job | Lifecycle cấp Job |

Header callback không được gọi cho mỗi item. Footer callback cũng không được gọi cho mỗi chunk.

Nếu cần ghi một dòng audit cho từng item, dùng writer hoặc listener phù hợp. Không đặt logic item-level trong header/footer callback.

## 13. Header và footer cần tự ghi newline

Callback nhận Writer và ghi trực tiếp. Nó không nhận LineAggregator và không tự động biến nội dung callback thành một item line.

Ví dụ đúng:

~~~java
.headerCallback(writer -> {
    writer.write("id,name,email");
    writer.write(System.lineSeparator());
})
~~~

Nếu bỏ newline, dòng item đầu tiên có thể nối ngay sau header tùy cách writer ghi separator, tạo file sai định dạng.

Tương tự footer:

~~~java
.footerCallback(writer -> {
    writer.write("END_OF_FILE");
    writer.write(System.lineSeparator());
})
~~~

Hãy xác định quy tắc xuống dòng của định dạng file. Có thể dùng LF cố định nếu đối tác yêu cầu bất kể operating system, hoặc dùng System.lineSeparator() nếu định dạng theo hệ điều hành là phù hợp.

Không giả định lineSeparator của FlatFileItemWriter tự áp dụng cho nội dung callback; callback ghi trực tiếp vào Writer nên tự thêm separator.

## 14. Header/footer và CSV escaping

Header callback ghi raw text. Nó không tự escape dấu phẩy, dấu nháy kép hoặc newline trong dữ liệu động.

Nếu metadata là một field CSV, hãy dùng cùng quy tắc quoting với dữ liệu. Ví dụ helper đơn giản:

~~~java
static String csvField(String value) {
    String escaped = value.replace("\"", "\"\"");
    return "\"" + escaped + "\"";
}
~~~

Sau đó:

~~~java
writer.write(
    "SOURCE," + csvField(sourceSystem)
        + System.lineSeparator()
);
~~~

Helper trên xử lý quote theo quy tắc CSV cơ bản, nhưng định dạng thực tế còn phụ thuộc encoding, null handling và quy ước của hệ thống nhận file.

Không nối dữ liệu không tin cậy trực tiếp vào header/footer nếu nó có thể chứa newline hoặc ký tự điều khiển. Hãy validate hoặc encode để tránh tạo thêm dòng giả trong file.

## 15. Header có thể chứa tên cột hoặc metadata riêng

Header có thể là một dòng tên cột CSV, nhiều dòng metadata rồi đến dòng tên cột, một record version của định dạng, mã batch, ngày nghiệp vụ, hệ thống nguồn hoặc schema identifier để downstream chọn parser.

Ví dụ:

~~~text
FORMAT_VERSION,2
BATCH_ID,BATCH-20261115
BUSINESS_DATE,2026-11-15
SOURCE,CRM
customer_id,full_name,email
~~~

Nếu hệ thống nhận file chỉ chấp nhận dòng tên cột đầu tiên, không thêm metadata vào header. Hãy tuân thủ đúng contract của downstream consumer.

Nếu cần nhiều loại file hoặc nhiều version, đưa schema version vào header để parser có thể chọn mapping tương ứng.

## 16. Footer có thể chứa trailer record

Một số hệ thống trao đổi file yêu cầu trailer record:

~~~text
C001,An,100.00
C002,Binh,250.00
C003,Chi,50.00
TRL,3,400.00
~~~

Trailer có thể chứa số record, tổng tiền, mã lô, checksum, ngày tạo file, mã định dạng hoặc dấu kết thúc.

Cần phân biệt số item đầu vào, số item đã filter, số item skip và số dòng thực tế được ghi. Footer phải dùng đúng chỉ số theo đặc tả.

Ví dụ, nếu processor filter 10 item và writer ghi 90 item, trailer thường phải phản ánh 90 record dữ liệu, không phải 100 item reader đã đọc. Nếu writer chuyển một item thành nhiều dòng, cần đếm số dòng output thay vì writeCount.

## 17. Hành vi với file rỗng

Một Step có thể đọc 0 item. Khi đó writer vẫn có thể được mở và đóng theo lifecycle Step, nhưng nội dung file phụ thuộc cấu hình và cách callback được kích hoạt.

Các câu hỏi cần quyết định:

- File rỗng có cần header không?
- Footer có được ghi khi không có item không?
- Có cần tạo file khi nguồn không có dữ liệu không?
- Downstream chấp nhận file chỉ có header/trailer không?
- Có nên xóa file nếu không có record?
- Một file không có item có phải là thành công hợp lệ hay là dữ liệu đầu vào thiếu?

Không nên giả định shouldDeleteIfEmpty sẽ có cùng ý nghĩa với mọi tổ hợp header/footer. Hãy kiểm thử FlatFileItemWriter với file rỗng theo đúng builder flags và phiên bản Spring Batch đang dùng.

Nếu yêu cầu là không tạo file khi không có record, có thể kiểm tra số item sau Step rồi xử lý file trong Step riêng. Nếu yêu cầu file vẫn phải có header, cấu hình writer và xác nhận output thực tế.

## 18. Restart và header callback

FlatFileItemWriter hỗ trợ lưu state để restart. Khi Step thất bại sau một số chunk đã commit, writer có thể khôi phục vị trí ghi từ ExecutionContext và tiếp tục file.

Một số nguyên tắc:

- Đặt writer name ổn định.
- Bật saveState khi cần restart.
- Dùng cùng output resource cho cùng JobInstance nếu restart cần tiếp tục file đó.
- Không tự xóa file khi restart.
- Không bật append một cách tùy tiện.
- Kiểm tra header không bị lặp ở giữa file.
- Kiểm tra dữ liệu chưa commit được xử lý theo transaction và checkpoint.
- Không để hai JobExecution khác nhau cùng ghi vào một đường dẫn.

Header callback thường chỉ tạo header khi writer khởi tạo file rỗng. Khi restart trên file đã có dữ liệu, writer khôi phục trạng thái và tiếp tục ghi thay vì chèn header lần nữa. Tuy nhiên, hành vi cụ thể chịu ảnh hưởng bởi appendAllowed, shouldDeleteIfExists, saveState và trạng thái file; hãy viết integration test để xác nhận.

### Không tự ghi header trong beforeStep

Nếu dùng FlatFileItemWriter, hãy để header callback quản lý phần đầu file. Ghi header thủ công từ StepExecutionListener có thể làm trùng header khi restart hoặc khi Step được mở lại.

## 19. Restart và footer callback

Footer callback gắn với close, vì vậy cần hiểu nó trong bối cảnh restart.

Khi Step thất bại theo lifecycle thông thường, writer có thể được đóng và footer callback có thể ghi trailer. Nếu Step được restart, writer sẽ dựa vào state/checkpoint để khôi phục file. Phần output chưa được commit hoặc phần được ghi sau checkpoint có thể cần được xử lý theo cơ chế khôi phục của writer.

Không nên giả định footer đã ghi ở lần thất bại sẽ được giữ nguyên như footer cuối cùng. Cũng không nên giả định callback chỉ chạy khi Job thành công.

Hãy kiểm thử các tình huống:

1. Step thành công: file có đúng một footer.
2. Step thất bại sau một chunk: xác định footer được ghi ở close hay không.
3. Restart Step: file được khôi phục đúng và không có footer cũ nằm giữa dữ liệu.
4. Step thất bại lần nữa: cleanup và footer không tạo nội dung lặp ngoài dự kiến.
5. File được publish: chỉ file đã được xác nhận hoàn tất mới trở thành output chính thức.

Nếu yêu cầu trailer chỉ xuất hiện trên file thành công, không dùng footer callback làm dấu thành công. Hãy thêm trailer thành công ở publish Step sau khi writer đã đóng file và Job flow xác nhận xử lý thành công.

## 20. Footer và lỗi khi close

Footer callback có thể ném IOException nếu không ghi được trailer. Lỗi này xảy ra trong quá trình đóng writer và có thể được bọc thành ItemStreamException hoặc lỗi đóng resource.

Nếu footer ghi thất bại:

- File có thể thiếu trailer.
- Step có thể kết thúc thất bại do lỗi close.
- Nếu Step đã có exception khác, lỗi close có thể xuất hiện như lỗi thứ cấp.
- File staging cần được giữ hoặc quarantine theo chính sách.
- Không publish file như một output hoàn chỉnh.

Không nuốt IOException rồi coi file là hợp lệ. Hãy ghi log với JobExecution ID, StepExecution ID và đường dẫn file.

## 21. Kết hợp footer callback với StepExecution

Nếu footer cần số liệu của Step, có thể inject StepExecution object vào callback bean StepScope:

~~~java
@Bean
@StepScope
FlatFileFooterCallback footerCallback(
        @Value("#{stepExecution}") StepExecution stepExecution) {

    return writer -> {
        writer.write("READ_COUNT," + stepExecution.getReadCount());
        writer.write(System.lineSeparator());

        writer.write("WRITE_COUNT," + stepExecution.getWriteCount());
        writer.write(System.lineSeparator());

        writer.write("FILTER_COUNT," + stepExecution.getFilterCount());
        writer.write(System.lineSeparator());

        writer.write("SKIP_COUNT," + stepExecution.getSkipCount());
        writer.write(System.lineSeparator());
    };
}
~~~

Callback đọc bộ đếm từ StepExecution khi được gọi. Đây là thông tin vận hành hữu ích, nhưng cần đặt tên trailer rõ ràng để downstream không nhầm số liệu với số dòng file.

Nếu callback được tạo ngoài StepScope hoặc giữ một snapshot scalar từ lúc Step bắt đầu, số liệu có thể không phản ánh trạng thái cuối. Late binding bằng StepExecution object giúp đọc trạng thái mới nhất tại thời điểm callback chạy.

Không dùng footer để quyết định Job thành công. BatchStatus của Job chỉ có thể được xác định sau khi các Step và flow kết thúc.

## 22. MultiResourceItemWriter và callback cho từng file

Khi cần chia output thành nhiều file, có thể dùng MultiResourceItemWriter với FlatFileItemWriter làm delegate.

Ví dụ khái niệm:

~~~java
@Bean
MultiResourceItemWriter<Customer> multiCustomerWriter(
        FlatFileItemWriter<Customer> customerDelegate,
        Resource outputResource) {

    return new MultiResourceItemWriterBuilder<Customer>()
        .name("multiCustomerWriter")
        .resource(outputResource)
        .delegate(customerDelegate)
        .itemCountLimitPerResource(1000)
        .resourceSuffixCreator(index ->
            "-" + index + ".csv"
        )
        .build();
}
~~~

Trong thực tế, resource base phải là Resource phù hợp với thư mục và tên file; cấu hình suffix creator cần khớp convention của ứng dụng.

Vì delegate được mở/đóng theo từng resource khi rollover, header/footer callback của FlatFileItemWriter có thể chạy theo lifecycle từng file. Do đó, mỗi file có thể có header và trailer riêng.

Cần kiểm thử:

- Header có xuất hiện ở đầu mỗi file.
- Footer có xuất hiện khi delegate đóng từng file.
- Resource cuối được đóng khi Step kết thúc.
- Restart tiếp tục đúng file và không tạo file trùng.
- Mỗi file có record count riêng nếu trailer yêu cầu.
- Không publish tập file cho đến khi mọi worker/resource hoàn tất.

Nếu trailer cần tổng số record của toàn bộ lô thay vì từng file, không dùng writeCount cục bộ của delegate mà không xác định phạm vi. Hãy tổng hợp số liệu ở cấp Step/Job hoặc một bước kiểm tra sau khi tất cả file được đóng.

## 23. Phân biệt header/footer callback với file header/trailer trong domain

Một số hệ thống gọi metadata đầu/cuối file là business header và trailer. Chúng có thể có schema riêng:

~~~text
HDR|FORMAT-02|BATCH-123|20261115
DTL|C001|100.00
DTL|C002|250.00
TRL|2|350.00
~~~

Trong trường hợp này, callback có thể ghi record HDR và TRL. Tuy nhiên, cần kiểm tra:

- Record header có cần một mã record cố định không?
- Trailer count tính số detail record hay số item input?
- Tổng tiền có scale và rounding cụ thể không?
- Checksum tính trên bytes, ký tự hay các record đã chuẩn hóa?
- Có yêu cầu CRLF hay LF?
- Encoding là UTF-8, UTF-16 hay charset đối tác quy định?
- File có cần byte order mark không?
- Có cần ký hoặc mã hóa file sau khi đóng không?

Callback chỉ ghi text. Nó không tự thực hiện signing, encryption, compression hoặc checksum nếu ứng dụng không bổ sung logic.

## 24. Encoding và newline

Header/footer phải dùng cùng encoding và quy ước xuống dòng với nội dung item.

Ví dụ:

~~~java
.encoding(StandardCharsets.UTF_8.name())
.lineSeparator("\n")
.headerCallback(writer -> {
    writer.write("id,name");
    writer.write("\n");
})
.footerCallback(writer -> {
    writer.write("END");
    writer.write("\n");
})
~~~

Nếu file được gửi sang hệ thống yêu cầu CRLF, dùng CRLF nhất quán cho cả callback và lineSeparator. Không trộn newline theo platform với newline cố định trong callback nếu downstream yêu cầu định dạng byte chính xác.

Nếu cần BOM, hãy xác định writer hoặc resource wrapper có hỗ trợ không. Không tự ghi BOM trong callback sau khi writer đã ghi byte khác, vì BOM phải nằm ở đầu file.

## 25. Header/footer và dữ liệu nhạy cảm

Header/footer thường chứa metadata nhưng vẫn có thể chứa dữ liệu nhạy cảm:

- Tên khách hàng hoặc tài khoản.
- Đường dẫn nội bộ.
- Mã hệ thống.
- Token hoặc credential.
- Thông tin vận hành có thể tiết lộ hạ tầng.

Chỉ ghi trường cần thiết theo contract. Không ghi password, access token hoặc secret vào file output. Nếu header có source file path, cân nhắc ghi logical source ID thay vì đường dẫn vật lý.

Với giá trị đến từ JobParameters hoặc ExecutionContext, validate và escape trước khi ghi. Một newline trong metadata có thể tạo thêm dòng giả hoặc phá cấu trúc file.

## 26. Header/footer và transactional file writing

FlatFileItemWriter có cơ chế buffer và transaction-aware writing để phối hợp việc ghi item với transaction chunk theo cấu hình. Tuy nhiên, file không phải lúc nào cũng là một resource transactionally đồng nhất với database.

Cần hiểu:

- Các dòng item có thể được buffer và ghi theo commit của chunk.
- Header thường được ghi trong quá trình mở writer.
- Footer được ghi khi writer đóng.
- Rollback database không tự xóa nội dung file đã flush ra filesystem.
- File output không tự atomic với commit của database.
- Nếu publish file và database phải nhất quán, cần thiết kế staging và publish workflow.

### Staging và publish

Một mô hình thường dùng:

~~~mermaid
flowchart TD
    A["FlatFileItemWriter mở staging file"] --> B["Ghi header"]
    B --> C["Ghi các item theo chunk"]
    C --> D["Close writer và ghi footer"]
    D --> E{"Step và Job thành công?"}
    E -- "Có" --> F["Publish file"]
    E -- "Không" --> G["Quarantine hoặc giữ staging"]
    F --> H["Downstream nhận file chính thức"]
~~~

Một publish Step riêng có thể kiểm tra file tồn tại, size, trailer, checksum và trạng thái Step trước khi đổi tên hoặc chuyển file vào thư mục chính thức.

Nếu cần move atomic, dùng Files.move với ATOMIC_MOVE khi filesystem hỗ trợ. Nếu không, triển khai fallback có kiểm soát và tránh để consumer nhìn thấy file đang được copy dở.

## 27. Callback không nên thực hiện công việc nặng

Header/footer callback nên ghi nội dung ngắn dựa trên dữ liệu đã có. Tránh truy vấn database lớn, gọi API từ xa, tính lại tổng dữ liệu toàn bộ nguồn, đợi nhiều thread hoàn tất, thực hiện publish hoặc gửi email, hay đóng resource do thành phần khác sở hữu.

Header callback chạy trong quá trình mở file, có thể làm Step chưa bắt đầu đọc item nhưng đã bị chặn. Footer callback chạy trong quá trình close; nếu chậm hoặc thất bại, Step close cũng bị ảnh hưởng. Callback có thể được gọi lại trong restart hoặc resource rollover. Side effect trong callback khó phối hợp với transaction và restart.

Tính toán dữ liệu cần thiết trong Step hoặc service riêng, rồi truyền kết quả vào callback.

## 28. Kiểm thử header callback

Kiểm thử nên xác nhận nội dung file thực tế, không chỉ xác nhận callback được gọi.

Ví dụ kiểm thử callback độc lập:

~~~java
@Test
void writesHeaderLines() throws Exception {
    StringWriter output = new StringWriter();

    FlatFileHeaderCallback callback = writer -> {
        writer.write("CUSTOMER EXPORT");
        writer.write(System.lineSeparator());
        writer.write("id,name");
        writer.write(System.lineSeparator());
    };

    callback.writeHeader(output);

    assertEquals(
        "CUSTOMER EXPORT" + System.lineSeparator()
            + "id,name" + System.lineSeparator(),
        output.toString()
    );
}
~~~

Kiểm thử này xác nhận logic callback, nhưng chưa kiểm tra FlatFileItemWriter có gọi callback đúng thời điểm hay không.

### Integration test với writer

Dùng FlatFileItemWriter thật với file tạm:

1. Cấu hình resource tạm.
2. Đăng ký header callback.
3. Mở writer.
4. Ghi một số item.
5. Đóng writer.
6. Đọc file.
7. Xác nhận header đứng trước record đầu tiên và chỉ xuất hiện đúng số lần mong muốn.

Không cần khởi chạy toàn bộ Job nếu chỉ kiểm tra builder/writer. Nhưng cần test Job/Step khi muốn xác nhận scope, restart hoặc callback lifecycle.

## 29. Kiểm thử footer callback

Test callback độc lập:

~~~java
@Test
void writesFooter() throws Exception {
    StringWriter output = new StringWriter();

    FlatFileFooterCallback callback = writer -> {
        writer.write("TOTAL_RECORDS,2");
        writer.write(System.lineSeparator());
        writer.write("END");
        writer.write(System.lineSeparator());
    };

    callback.writeFooter(output);

    assertEquals(
        "TOTAL_RECORDS,2" + System.lineSeparator()
            + "END" + System.lineSeparator(),
        output.toString()
    );
}
~~~

Integration test cần mở FlatFileItemWriter, ghi item, đóng writer, đọc file, xác nhận footer ở cuối file và xác nhận callback không được gọi sau mỗi chunk.

Nếu footer dùng StepExecution metrics, chạy Step thật và xác nhận trailer phản ánh bộ đếm cuối.

## 30. Kiểm thử lỗi và restart

Các trường hợp nên có:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Step thành công | Header, detail và footer đúng thứ tự |
| Step không có item | Nội dung file đúng policy empty output |
| Processor thất bại | Writer được đóng theo lifecycle; footer behavior được xác nhận |
| Writer thất bại | Không publish file dở dang |
| Footer callback ném IOException | Step/close failure được ghi nhận |
| Restart sau chunk đã commit | Không lặp header hoặc mất detail |
| Restart sau close do failure | Footer cũ không bị giữ ở vị trí sai |
| Append vào file có sẵn | Header không xuất hiện giữa dữ liệu |
| MultiResourceItemWriter rollover | Mỗi file có header/footer theo contract |
| Job rerun với output path mới | Không ghi đè file của lần chạy trước |

### Kiểm tra số lần gọi callback

Có thể dùng callback đếm số lần được gọi:

~~~java
AtomicInteger headerCalls = new AtomicInteger();
AtomicInteger footerCalls = new AtomicInteger();

FlatFileHeaderCallback header = writer -> {
    headerCalls.incrementAndGet();
    writer.write("id,name" + System.lineSeparator());
};

FlatFileFooterCallback footer = writer -> {
    footerCalls.incrementAndGet();
    writer.write("END" + System.lineSeparator());
};
~~~

Sau khi chạy writer hoặc Step, xác nhận số lần gọi theo trường hợp cụ thể. Với restart và multi-resource, không giả định luôn bằng một; số lần gọi gắn với lifecycle của file writer/delegate.

## 31. Những lỗi triển khai thường gặp

### Quên newline trong callback

Header hoặc footer dính vào dòng dữ liệu kế tiếp. Callback phải tự ghi line separator khi định dạng yêu cầu.

### Đóng Writer trong callback

Writer thuộc FlatFileItemWriter. Đóng nó trong callback làm framework không thể tiếp tục ghi hoặc đóng đúng lifecycle.

### Ghi file bằng một Writer thứ hai

Hai writer cùng ghi một resource có thể làm mất dữ liệu, sai thứ tự hoặc xung đột buffer. Dùng Writer callback được truyền vào.

### Dùng footer làm dấu SUCCESS

Footer có thể được ghi khi writer close trên đường thất bại. Dùng publish Step sau khi xử lý thành công để thêm dấu xác nhận.

### Tính tổng từ dữ liệu nguồn trong footer

Footer callback bị chậm và có thể được gọi lại. Tổng hợp trong quá trình xử lý hoặc một Step kiểm tra riêng.

### Inject scalar StepExecution count quá sớm

Một giá trị số bind lúc tạo bean có thể là snapshot đầu Step. Inject StepExecution object rồi đọc bộ đếm khi callback chạy.

### Cho rằng header/footer tự escape CSV

Callback ghi raw text. Tự encode field động theo contract của file.

### Không kiểm thử file rỗng

File không có detail có thể vẫn có header/footer hoặc bị xóa theo cấu hình. Xác định yêu cầu và test.

### Restart tạo header/footer trùng

Không ghi header/footer thủ công từ listener. Dùng callback và kiểm thử với saveState, append và checkpoint thực tế.

### Publish file trong footer callback

Footer chỉ kết thúc file writer, không chứng minh toàn bộ Job thành công. Publish trong Step riêng.

### Dùng chung output path cho nhiều JobExecution

Hai writer có thể ghi đè hoặc xen kẽ dữ liệu. Tạo staging path riêng theo JobInstance/run ID và publish có kiểm soát.

### Ghi metadata không được escape

Newline hoặc delimiter trong JobParameters có thể phá file. Validate và encode trước khi ghi.

## 32. Quy trình triển khai header/footer callback

Khi xây dựng file output, có thể làm theo trình tự:

1. **Xác định định dạng:** header, tên cột, metadata, trailer và newline theo contract downstream.
2. **Chọn writer:** dùng FlatFileItemWriter nếu cần callback tích hợp.
3. **Tạo LineAggregator:** định nghĩa cách chuyển item thành record.
4. **Viết header callback:** ghi metadata và tên cột, tự thêm newline.
5. **Viết footer callback:** ghi trailer dựa trên state đã được tổng hợp.
6. **Bind dữ liệu runtime:** dùng @StepScope để đọc JobParameters hoặc ExecutionContext.
7. **Cấu hình writer state:** đặt name ổn định và saveState phù hợp restart.
8. **Kiểm soát output path:** dùng resource riêng cho JobInstance và staging.
9. **Tách publish:** chỉ công bố file sau khi Step/Job thành công.
10. **Kiểm thử callback:** nội dung, newline, file rỗng, lỗi close, restart, append và multi-resource.
11. **Theo dõi lỗi:** ghi nhận IOException và không publish file thiếu header/footer hoặc trailer.

## 33. Những điểm cần nhớ

- FlatFileHeaderCallback ghi phần đầu file; FlatFileFooterCallback ghi phần cuối file.
- Hai callback nhận java.io.Writer do FlatFileItemWriter quản lý.
- Header được gọi trong quá trình mở file khi writer cần khởi tạo đầu file; footer được gọi trong quá trình close.
- Callback không chạy cho từng item hoặc từng chunk.
- Callback phải tự ghi newline khi định dạng yêu cầu.
- Không đóng Writer hoặc mở writer thứ hai trong callback.
- Có thể dùng @StepScope và SpEL để lấy JobParameters, JobExecutionContext hoặc StepExecutionContext.
- Footer có thể đọc bộ đếm từ StepExecution object tại thời điểm callback thực thi.
- Footer không phải bằng chứng Job thành công vì writer có thể close trong đường thất bại.
- Nếu cần dấu SUCCESS, hãy thêm ở publish Step sau khi xử lý hoàn tất.
- Header/footer ghi raw text; dữ liệu động cần validate và CSV-escape.
- Restart và append phụ thuộc saveState, checkpoint, appendAllowed và trạng thái file; cần integration test.
- MultiResourceItemWriter có thể tạo header/footer theo lifecycle từng file delegate.
- File output nên dùng staging và chỉ publish sau khi được xác nhận hoàn chỉnh.
- Kiểm thử cả file rỗng, exception, restart, callback failure và resource rollover.

Header và footer callback giúp FlatFileItemWriter tạo file đúng cấu trúc mà không phải trộn metadata file với logic xử lý từng item. Khi hiểu rõ thời điểm callback chạy, quản lý đúng Writer được truyền vào và tách footer kỹ thuật khỏi xác nhận thành công, ứng dụng có thể tạo file dễ đọc, restart an toàn và tránh công bố output chưa hoàn chỉnh.

