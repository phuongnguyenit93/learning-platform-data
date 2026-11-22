# FlatFileItemWriter

Trong Spring Batch, **FlatFileItemWriter** ghi các item của một chunk thành những dòng văn bản trong file. Writer nhận object đã được xử lý, chuyển mỗi object thành một dòng String thông qua LineAggregator, rồi mã hóa dòng đó thành byte và ghi vào Resource đích.

FlatFileItemWriter thường được dùng để tạo CSV, file phân cách bằng tab, file fixed-width hoặc định dạng text riêng theo hợp đồng trao đổi dữ liệu. Để ghi file ổn định, cần cấu hình đúng resource, cách chuyển item thành dòng, encoding, header/footer, chính sách file đã tồn tại, transaction và checkpoint khi restart.

## 1. Vị trí của FlatFileItemWriter trong chunk processing

Trong một chunk-oriented Step, ItemReader đọc dữ liệu, ItemProcessor biến đổi item và ItemWriter ghi kết quả:

~~~text
Input resource
     |
     v
ItemReader
     |
     v
ItemProcessor
     |
     v
Chunk of output items
     |
     v
FlatFileItemWriter
     |
     v
Output file
~~~

Ví dụ, một Job đọc đơn hàng từ database, tính lại tổng tiền rồi xuất file cho hệ thống kế toán. Reader trả về OrderInput, processor tạo OrderExport và FlatFileItemWriter ghi mỗi OrderExport thành một dòng.

FlatFileItemWriter chịu trách nhiệm ghi dòng và quản lý trạng thái file trong vòng đời Step. Nó không tự quyết định quy tắc nghiệp vụ để chuyển Order thành các cột; phần đó thuộc LineAggregator và FieldExtractor hoặc logic chuyển đổi tương ứng.

## 2. Cấu hình writer cơ bản

Với Spring Batch 5, có thể tạo writer bằng FlatFileItemWriterBuilder:

~~~java
@Bean
public FlatFileItemWriter<OrderExport> orderExportWriter(
        Resource outputFile) {

    return new FlatFileItemWriterBuilder<OrderExport>()
            .name("orderExportWriter")
            .resource(outputFile)
            .encoding("UTF-8")
            .lineAggregator(order ->
                    order.getOrderId() + ","
                    + order.getCustomerCode() + ","
                    + order.getTotalAmount())
            .saveState(true)
            .build();
}
~~~

Các phần quan trọng:

- **name**: tên ổn định của writer, được dùng khi lưu state trong ExecutionContext.
- **resource**: file hoặc Resource mà writer sẽ ghi.
- **encoding**: charset dùng để chuyển String thành byte.
- **lineAggregator**: chuyển mỗi item thành một dòng.
- **saveState(true)**: cho phép writer lưu tiến độ để restart.

LineAggregator là thành phần bắt buộc vì writer cần biết cách biểu diễn item thành text. Với file CSV phức tạp, không nên ghép chuỗi tùy tiện; hãy xác định quy tắc quote, escape, null và định dạng số/ngày.

## 3. Resource đầu ra

FlatFileItemWriter ghi vào một Spring Resource. Với file trên filesystem, thường dùng FileSystemResource:

~~~java
Resource outputFile =
        new FileSystemResource("output/orders.csv");
~~~

Thư mục cha phải tồn tại và ứng dụng phải có quyền ghi. Writer không tự tạo toàn bộ cây thư mục trong mọi trường hợp. Nên chuẩn bị thư mục output trước khi Step mở writer.

Nếu đường dẫn đến từ JobParameters, có thể dùng late binding:

~~~java
@Bean
@StepScope
public FlatFileItemWriter<OrderExport> orderExportWriter(
        @Value("#{jobParameters['outputFile']}") String outputPath) {

    return new FlatFileItemWriterBuilder<OrderExport>()
            .name("orderExportWriter")
            .resource(new FileSystemResource(outputPath))
            .encoding("UTF-8")
            .lineAggregator(order ->
                    order.getOrderId() + ","
                    + order.getCustomerCode() + ","
                    + order.getTotalAmount())
            .saveState(true)
            .build();
}
~~~

@StepScope trì hoãn việc tạo writer đến khi StepExecution hoạt động, lúc đó JobParameters đã có thể được resolve. Cách này hữu ích khi nhiều lần chạy dùng các file output khác nhau hoặc khi worker partition có file riêng.

Không dùng classpath resource làm file output thông thường vì tài nguyên trong JAR thường không thể ghi. Chọn resource có khả năng ghi và kiểm tra quyền truy cập trên môi trường triển khai.

## 4. LineAggregator chuyển item thành dòng

LineAggregator là abstraction nhận một item và trả về một String đại diện cho dòng cần ghi:

~~~java
public interface LineAggregator<T> {
    String aggregate(T item);
}
~~~

Một LineAggregator đơn giản có thể là lambda:

~~~java
.lineAggregator(order ->
        order.getOrderId() + ","
        + order.getCustomerCode() + ","
        + order.getTotalAmount())
~~~

Cách này phù hợp với ví dụ nhỏ và dữ liệu đơn giản. Khi có nhiều field, format phức tạp hoặc escaping, nên tách logic thành một LineAggregator riêng để dễ kiểm thử và bảo trì.

Spring Batch cung cấp các implementation phổ biến:

| Implementation | Công dụng |
| --- | --- |
| PassThroughLineAggregator | Ghi item trực tiếp dưới dạng String |
| DelimitedLineAggregator | Nối các field bằng delimiter |
| FormatterLineAggregator | Định dạng field theo format string |
| LineAggregator tùy chỉnh | Áp dụng quy tắc riêng như quote, escape hoặc layout đặc biệt |

## 5. Dùng FieldExtractor và DelimitedLineAggregator

Khi item là Java object, FieldExtractor lấy các giá trị cần ghi từ object. DelimitedLineAggregator nối các giá trị theo delimiter.

Ví dụ:

~~~java
BeanWrapperFieldExtractor<OrderExport> extractor =
        new BeanWrapperFieldExtractor<>();
extractor.setNames(new String[] {
        "orderId",
        "customerCode",
        "totalAmount"
});

DelimitedLineAggregator<OrderExport> aggregator =
        new DelimitedLineAggregator<>();
aggregator.setDelimiter(",");
aggregator.setFieldExtractor(extractor);
~~~

Đưa aggregator vào writer:

~~~java
return new FlatFileItemWriterBuilder<OrderExport>()
        .name("orderExportWriter")
        .resource(outputFile)
        .encoding("UTF-8")
        .lineAggregator(aggregator)
        .build();
~~~

BeanWrapperFieldExtractor đọc property theo tên. Các property phải tồn tại và có thể truy cập thông qua getter tương ứng. Thứ tự tên trong setNames quyết định thứ tự cột.

Ví dụ nếu khai báo:

~~~java
extractor.setNames(new String[] {
        "orderId", "customerCode", "totalAmount"
});
~~~

thì dòng được tạo có thứ tự:

~~~text
orderId,customerCode,totalAmount
~~~

DelimitedLineAggregator giúp nối field, nhưng không nên mặc định rằng nó tự thực hiện đầy đủ escaping theo chuẩn CSV cho mọi giá trị. Nếu field có thể chứa dấu phẩy, dấu nháy kép hoặc newline, hãy dùng aggregator có quy tắc quote/escape rõ ràng hoặc thư viện CSV phù hợp.

## 6. Tạo CSV an toàn với quote và escape

Một CSV hợp lệ phải bảo vệ delimiter xuất hiện bên trong field. Theo quy tắc CSV phổ biến, field có dấu phẩy, dấu nháy kép hoặc newline được đặt trong dấu nháy kép; dấu nháy kép bên trong được nhân đôi.

Ví dụ:

~~~text
1001,"Nguyen, An",250000
1002,"Customer said ""OK""",180000
~~~

Có thể viết aggregator đơn giản nếu định dạng CSV của ứng dụng chỉ cần quy tắc cơ bản:

~~~java
public class OrderCsvLineAggregator
        implements LineAggregator<OrderExport> {

    @Override
    public String aggregate(OrderExport order) {
        return String.join(",",
                quote(order.getOrderId()),
                quote(order.getCustomerCode()),
                quote(order.getCustomerName()),
                quote(order.getTotalAmount().toPlainString()));
    }

    private String quote(String value) {
        String safeValue = value == null ? "" : value;
        return "\"" + safeValue.replace("\"", "\"\"") + "\"";
    }
}
~~~

Ví dụ này luôn quote các field. Quy tắc null được chuyển thành chuỗi rỗng; nếu hệ thống cần phân biệt null với empty string, phải định nghĩa representation riêng. Cũng cần quyết định cách xử lý newline và ký tự điều khiển theo contract của file.

Với file trao đổi quan trọng, ưu tiên thư viện CSV chuyên dụng để xử lý các trường hợp edge case. Đừng xem việc nối chuỗi bằng dấu phẩy là một CSV writer hoàn chỉnh.

## 7. Ghi file fixed-width

Không phải file text nào cũng là CSV. Một số hệ thống yêu cầu field có độ rộng cố định, ví dụ mã khách hàng 10 ký tự, tên 30 ký tự và số tiền 12 ký tự.

Có thể dùng FormatterLineAggregator cùng FieldExtractor:

~~~java
BeanWrapperFieldExtractor<CustomerExport> extractor =
        new BeanWrapperFieldExtractor<>();
extractor.setNames(new String[] {
        "customerCode",
        "customerName",
        "balance"
});

FormatterLineAggregator<CustomerExport> aggregator =
        new FormatterLineAggregator<>();
aggregator.setFormat("%-10s%-30s%012.2f");
aggregator.setFieldExtractor(extractor);
~~~

Sau đó cấu hình writer với aggregator:

~~~java
return new FlatFileItemWriterBuilder<CustomerExport>()
        .name("customerFixedWidthWriter")
        .resource(outputFile)
        .encoding("UTF-8")
        .lineAggregator(aggregator)
        .build();
~~~

Format string phải phù hợp kiểu dữ liệu thực tế. Cần kiểm tra độ dài ký tự, độ rộng byte và quy tắc padding của hệ thống nhận. Với charset UTF-8, số byte của một ký tự có thể khác nhau, vì vậy fixed-width theo ký tự không nhất thiết giống fixed-width theo byte.

Nếu đối tác yêu cầu mỗi record có đúng số byte, phải xác định encoding và tính độ dài sau khi encode. Không chỉ dựa vào String.length().

## 8. Header và footer

FlatFileItemWriter hỗ trợ callback để ghi nội dung ở đầu và cuối file.

### Header callback

HeaderCallback được dùng để ghi dòng tiêu đề hoặc metadata khi writer mở file:

~~~java
return new FlatFileItemWriterBuilder<OrderExport>()
        .name("orderExportWriter")
        .resource(outputFile)
        .encoding("UTF-8")
        .headerCallback(writer ->
                writer.write("orderId,customerCode,totalAmount"))
        .lineAggregator(order ->
                order.getOrderId() + ","
                + order.getCustomerCode() + ","
                + order.getTotalAmount())
        .build();
~~~

Header phải tuân theo cùng encoding và line format với phần dữ liệu. Nếu file không có header theo hợp đồng, không cấu hình callback này.

### Footer callback

FooterCallback ghi nội dung cuối file khi writer đóng:

~~~java
.footerCallback(writer ->
        writer.write("END_OF_FILE"))
~~~

Footer có thể chứa tổng số record hoặc marker kết thúc. Nếu cần tổng số record, hãy lấy số liệu từ state được quản lý phù hợp, không dựa vào biến static dùng chung giữa các JobExecution.

Footer được gắn với lifecycle đóng writer. Không nên dùng việc footer xuất hiện làm bằng chứng duy nhất rằng toàn bộ Job đã thành công. Hãy kiểm tra BatchStatus, ExitStatus và quy trình publish file trước khi coi output là sẵn sàng cho hệ thống nhận.

Trong restart hoặc append, cần kiểm thử hành vi header/footer theo cấu hình thực tế để tránh header lặp hoặc footer xuất hiện giữa file.

## 9. Encoding và line separator

Writer chuyển dòng String thành byte theo charset được cấu hình. Nên chỉ định encoding rõ ràng:

~~~java
.encoding("UTF-8")
~~~

Nếu không cấu hình, writer có thể dùng charset mặc định của runtime. Kết quả có thể khác giữa máy phát triển và production.

Line separator quyết định cách kết thúc mỗi dòng. Có thể chọn LF hoặc CRLF theo yêu cầu của hệ thống nhận:

~~~java
.lineSeparator("\n")
~~~

Hoặc:

~~~java
.lineSeparator("\r\n")
~~~

Encoding và line separator là hai cấu hình riêng. UTF-8 không bắt buộc file phải dùng LF; file UTF-8 hoàn toàn có thể dùng CRLF.

Với file có ký tự tiếng Việt, hãy kiểm thử byte output bằng UTF-8. Nếu hệ thống nhận yêu cầu charset legacy, xác nhận mọi ký tự cần ghi đều có thể biểu diễn bằng charset đó.

## 10. Chính sách khi file đã tồn tại

Khi Step chạy, output file có thể đã tồn tại từ một lần chạy trước hoặc từ một quy trình khác. Writer cần được cấu hình rõ cách xử lý.

Các chiến lược thường gặp:

| Chiến lược | Ý nghĩa | Khi phù hợp |
| --- | --- | --- |
| Ghi file mới và xóa file cũ | Tạo output sạch cho lần chạy mới | Mỗi JobInstance tạo một file kết quả riêng |
| Append | Ghi thêm vào cuối file hiện có | Output được thiết kế để tích lũy record qua nhiều lần chạy |
| Từ chối file đã tồn tại | Bảo vệ dữ liệu cũ và tránh ghi nhầm | Tên file phải duy nhất hoặc cần kiểm soát publish |

Ví dụ yêu cầu writer xóa file cũ khi bắt đầu một lần chạy mới:

~~~java
return new FlatFileItemWriterBuilder<OrderExport>()
        .name("orderExportWriter")
        .resource(outputFile)
        .shouldDeleteIfExists(true)
        .lineAggregator(order -> toCsv(order))
        .build();
~~~

Nếu muốn append vào file hiện có, dùng chế độ append của writer (ví dụ setAppendAllowed(true) trên writer) và cấu hình việc giữ file hiện tại phù hợp. Không kết hợp append với xóa file theo cách mâu thuẫn.

Phải phân biệt lần chạy mới với restart của cùng JobInstance. Restart cần dùng state đã lưu để tiếp tục đúng vị trí; một lần chạy mới có thể cần tạo file mới hoặc append theo yêu cầu nghiệp vụ. Đừng tự xóa file trước khi restart vì có thể phá hủy dữ liệu của các chunk đã commit.

## 11. shouldDeleteIfEmpty

Trong một số pipeline, không cần giữ file output nếu không có item nào được ghi. Writer hỗ trợ chính sách shouldDeleteIfEmpty:

~~~java
.shouldDeleteIfEmpty(true)
~~~

Khi bật, writer có thể xóa file nếu không có dữ liệu được ghi theo điều kiện của implementation. Cần kiểm thử trường hợp file chỉ có header hoặc có footer, vì khái niệm “empty” có thể liên quan đến dữ liệu item và lifecycle callback.

Không bật tùy tiện nếu hệ thống nhận yêu cầu một file rỗng để biểu thị batch không có dữ liệu. Hãy xác định output contract trước khi chọn.

## 12. Transactional writing và rollback

FlatFileItemWriter mặc định hỗ trợ ghi theo transaction của chunk thông qua cơ chế buffer. Khi transaction commit, dữ liệu buffer được ghi ra file. Khi transaction rollback, phần ghi chưa commit có thể bị loại bỏ thay vì để lại các dòng của chunk thất bại.

~~~text
Chunk transaction
     |
     +-- FlatFileItemWriter nhận các item
     |
     +-- Ghi vào transactional buffer
     |
     +-- Nếu COMMIT
     |      |
     |      +--> Flush dữ liệu của chunk ra file
     |
     +-- Nếu ROLLBACK
            |
            +--> Bỏ dữ liệu chưa commit khỏi buffer
~~~

Có thể điều chỉnh transactional behavior bằng cấu hình transactional của writer. Nếu tắt transaction buffering, dữ liệu có thể được ghi trực tiếp ra file; khi chunk rollback, các dòng đã ghi có thể vẫn còn trong output.

Chỉ tắt buffering khi đã hiểu hậu quả và có cơ chế phục hồi phù hợp. Với batch output thông thường, giữ transactional behavior mặc định là lựa chọn an toàn hơn.

### File và database không tự tạo một transaction phân tán

Transactional buffering của FlatFileItemWriter phối hợp việc ghi file với transaction chunk theo cơ chế của writer. Nó không tự biến file và database thành một resource XA chung.

Nếu cùng chunk vừa ghi database vừa ghi file, vẫn cần xem xét tình huống một resource commit còn resource kia lỗi. Với yêu cầu xuất file đáng tin cậy, một mẫu thường dùng là:

1. Ghi file vào đường dẫn tạm theo JobExecution.
2. Hoàn tất Step và xác nhận Job/business outcome.
3. Kiểm tra file, kích thước, số record hoặc checksum.
4. Chuyển file tạm sang tên chính thức bằng thao tác publish phù hợp.
5. Chỉ sau đó thông báo cho hệ thống nhận.

Cách này tránh để consumer đọc một file đang được ghi dở. Thao tác rename có tính atomic hay không còn phụ thuộc filesystem và vị trí nguồn/đích.

## 13. saveState và restart

FlatFileItemWriter có thể lưu trạng thái vào ExecutionContext để restart. Cần đặt tên writer ổn định và bật saveState:

~~~java
return new FlatFileItemWriterBuilder<OrderExport>()
        .name("orderExportWriter")
        .resource(outputFile)
        .lineAggregator(order -> toCsv(order))
        .saveState(true)
        .build();
~~~

Writer lưu thông tin cần thiết về tiến độ ghi, thường gồm vị trí file tại checkpoint. Khi Job restart cùng JobInstance, writer có thể mở lại file và tiếp tục từ vị trí đã commit gần nhất.

Ví dụ chunk size 100:

~~~text
Chunk 1: ghi record 1-100       -> COMMIT
Chunk 2: ghi record 101-200     -> COMMIT
Chunk 3: ghi record 201-300     -> ROLLBACK

Checkpoint writer: sau record 200

Restart:
  tiếp tục từ vị trí sau record 200
  ghi lại record 201 trở đi
~~~

Không tự xóa hoặc thay thế output file giữa lần chạy đầu và restart. Không thay đổi writer name, output path hoặc format trong khi JobInstance cũ còn cần restart nếu chưa có chiến lược tương thích.

### saveState(false)

Nếu tắt saveState, writer không lưu vị trí để khôi phục:

~~~java
.saveState(false)
~~~

Điều này có thể phù hợp với writer không cần restart hoặc khi ứng dụng có cơ chế phục hồi khác. Nhưng nếu Step thất bại và được restart, writer có thể không biết cần tiếp tục ở đâu. Có nguy cơ ghi lại từ đầu, ghi trùng hoặc ghi sai vị trí.

Không tắt saveState chỉ để tránh metadata nếu Job cần restart. Hãy kiểm thử hành vi thực tế với đúng writer và resource.

## 14. Writer name và ExecutionContext

Tên writer phải ổn định và duy nhất trong phạm vi Step cần lưu state. Spring Batch sử dụng tên này làm một phần namespace cho các key ExecutionContext.

Nếu hai writer trong cùng Step dùng cùng tên, state có thể xung đột. Nếu đổi tên writer giữa lần chạy đầu và restart, writer có thể không tìm thấy checkpoint cũ.

Với partitioning, mỗi worker có StepExecution riêng nên mỗi writer cần có resource riêng hoặc một chiến lược ghi file an toàn. Không để nhiều worker cùng ghi vào một file bằng các writer độc lập nếu chưa có cơ chế đồng bộ và định dạng đầu ra phù hợp.

## 15. Append và restart

Append là quyết định về cách xử lý file đang tồn tại khi mở writer. Restart là quyết định về cách tiếp tục một execution đã có checkpoint. Hai khái niệm liên quan nhưng không giống nhau.

Một số nguyên tắc:

- Lần chạy mới append khi output được thiết kế để tích lũy dữ liệu.
- Restart cùng JobInstance phải dựa trên state đã lưu, không append mù quáng từ cuối file.
- Nếu file được tạo riêng cho từng JobExecution, dùng đường dẫn ổn định cho lần restart của execution đó.
- Nếu nhiều JobInstance cùng ghi vào một file, cần khóa hoặc cơ chế điều phối để tránh xen kẽ dòng.
- Nếu output được publish theo ngày hoặc batch ID, dùng tên file gắn với business key ổn định.

Không dựa vào shouldDeleteIfExists(false) như một cơ chế restart hoàn chỉnh. Hãy cấu hình append, saveState, writer name và JobParameters nhất quán, rồi kiểm thử cả lần chạy mới lẫn restart.

## 16. Footer, header và restart

Header và footer là nội dung đặc biệt ngoài các item:

- Header thường được ghi khi mở một output file mới.
- Footer được ghi trong lifecycle đóng writer.
- Khi append hoặc restart, cần tránh header lặp giữa file.
- Nếu Step thất bại, không dùng footer như dấu hiệu duy nhất để kết luận file hoàn chỉnh.

Nếu file cần footer chứa tổng record, hãy bảo đảm giá trị đếm được phục hồi đúng qua restart hoặc được tính từ dữ liệu đã commit. Nếu footer chỉ được ghi khi close, hãy kiểm thử trường hợp Job dừng, rollback hoặc restart theo đúng lifecycle của ứng dụng.

Một lựa chọn vận hành an toàn là tạo file tạm, kiểm tra trạng thái Job và chỉ publish file hoàn chỉnh sau khi Job kết thúc thành công theo quy tắc nghiệp vụ.

## 17. Ghi file rỗng và file chỉ có header

Có những Job không có item phù hợp. Cần xác định output mong muốn:

- Không tạo file.
- Tạo file chỉ có header.
- Tạo file rỗng không có header.
- Tạo file có footer và thống kê zero records.

Các callback header/footer và shouldDeleteIfEmpty có thể ảnh hưởng đến kết quả cuối. Kiểm thử đúng combination thay vì chỉ kiểm tra Step status.

Nếu hệ thống nhận dùng sự tồn tại của file như tín hiệu batch hoàn tất, phải quy định rõ trường hợp zero records. Không xóa file rỗng nếu việc không có file sẽ bị hiểu là batch chưa chạy.

## 18. Ghi nhiều file với MultiResourceItemWriter

FlatFileItemWriter ghi vào một Resource. Nếu cần chia output thành nhiều file theo số item, kích thước hoặc nhóm dữ liệu, có thể dùng MultiResourceItemWriter với FlatFileItemWriter làm delegate.

Ví dụ khung:

~~~java
@Bean
public MultiResourceItemWriter<OrderExport> multiOrderWriter(
        FlatFileItemWriter<OrderExport> delegate,
        Resource outputDirectory) {

    return new MultiResourceItemWriterBuilder<OrderExport>()
            .name("multiOrderWriter")
            .resource(outputDirectory)
            .delegate(delegate)
            .itemCountLimitPerResource(10000)
            .resourceSuffixCreator(index ->
                    String.format("-%03d.csv", index))
            .build();
}
~~~

Trong triển khai thực tế, resource base và cách ghép suffix phải phù hợp với MultiResourceItemWriter version đang dùng; ví dụ minh họa cấu trúc cấu hình. Delegate writer vẫn cần lineAggregator, encoding và state phù hợp.

Khi restart, thứ tự resource, suffix và input phải ổn định để writer tiếp tục đúng file. Nếu nhiều partition cùng tạo file, nên dùng tên file chứa partition ID hoặc business key để tránh ghi đè.

## 19. Thread safety và partitioning

FlatFileItemWriter là writer có state như resource, vị trí ghi, buffer và lifecycle. Không nên mặc định một instance có thể được nhiều thread gọi write đồng thời.

Trong multi-threaded Step:

- Nhiều thread có thể gọi writer cùng lúc.
- Dòng có thể bị xen kẽ nếu writer không đồng bộ.
- State vị trí ghi và checkpoint có thể không phản ánh đúng thứ tự mong muốn.
- Một chunk rollback có thể ảnh hưởng dữ liệu của thread khác nếu transaction và writer không được thiết kế phù hợp.

Nếu cần dùng chung writer trong môi trường đa luồng, có thể cân nhắc decorator đồng bộ như SynchronizedItemStreamWriter khi phù hợp với version và semantics của Step. Đồng bộ hóa có thể giảm throughput và không giải quyết mọi vấn đề transaction hoặc thứ tự nghiệp vụ.

Với partitioning, lựa chọn thường rõ ràng hơn là mỗi partition ghi một file riêng:

~~~text
partition0 -> orders-part-000.csv
partition1 -> orders-part-001.csv
partition2 -> orders-part-002.csv
                  |
                  v
             merge/publish
~~~

Sau khi tất cả partition hoàn tất, một Step riêng có thể hợp nhất hoặc publish file. Cách này tránh nhiều worker cùng ghi vào một resource.

## 20. forceSync và độ bền dữ liệu

Writer có tùy chọn forceSync để yêu cầu đồng bộ dữ liệu xuống storage ở mức hệ điều hành theo khả năng của implementation. Bật forceSync có thể tăng độ bền trước một số tình huống process hoặc hệ điều hành dừng bất ngờ, nhưng có chi phí I/O và có thể làm giảm throughput.

~~~java
.forceSync(true)
~~~

Không nên bật chỉ vì muốn mọi lần ghi nhanh chóng “an toàn tuyệt đối”. Force sync không tạo transaction phân tán, không bảo đảm filesystem hoặc thiết bị lưu trữ không có lỗi và không thay thế backup/checksum/atomic publish.

Hãy chọn theo yêu cầu durability và đo ảnh hưởng hiệu năng trên storage thật.

## 21. Đóng writer và quản lý file lifecycle

FlatFileItemWriter cần được mở, cập nhật state và đóng bởi Spring Batch. Không tự đóng writer từ processor hoặc service khi Step còn hoạt động.

Vòng đời khái quát:

~~~text
Step bắt đầu
    |
    v
Writer.open(ExecutionContext)
    |
    v
Writer.write(chunk)
    |
    v
Writer.update(ExecutionContext)
    |
    v
Commit / rollback
    |
    v
Lặp các chunk
    |
    v
Writer.close()
~~~

Khi Step kết thúc, framework gọi lifecycle phù hợp để giải phóng resource. Nếu bọc writer bằng decorator, hãy bảo đảm delegate ItemStream lifecycle được chuyển tiếp. Nếu không, writer có thể không mở, không lưu checkpoint hoặc không đóng file đúng cách.

Không dùng cùng một đường dẫn output cho hai JobExecution chạy đồng thời nếu không có cơ chế điều phối. Hai writer có thể ghi đè, xen kẽ dữ liệu hoặc làm hỏng checkpoint của nhau.

## 22. Quan sát và kiểm tra output

Sau khi Step chạy, cần kiểm tra cả trạng thái Batch và nội dung file:

- JobExecution và StepExecution có COMPLETED không?
- ExitStatus có mã tùy chỉnh hoặc cảnh báo không?
- Số item đọc, ghi, filter và skip có đúng kỳ vọng không?
- File có tồn tại và kích thước hợp lý không?
- Header/footer có đúng và không bị lặp không?
- Encoding, delimiter, quote và line separator có đúng contract không?
- File có bị để lại một phần sau lỗi không?
- Checksum hoặc record count có khớp với nguồn không?

Có thể dùng JobExplorer để đọc StepExecution và các counter. Việc kiểm tra file nên được thực hiện ở bước xác nhận/publish riêng nếu file là output quan trọng.

Không chỉnh sửa metadata JobRepository hoặc truncate file thủ công để ép restart nếu chưa xác định checkpoint và dữ liệu đã commit.

## 23. Những lỗi thường gặp

### Không cấu hình LineAggregator

Writer không biết chuyển item thành dòng. Cấu hình LineAggregator phù hợp với output format.

### Ghép CSV bằng dấu phẩy mà không escape

Field có dấu phẩy, quote hoặc newline có thể làm lệch cột. Dùng aggregator có quy tắc CSV rõ ràng hoặc thư viện CSV.

### Dùng charset mặc định

File có thể khác nhau giữa các môi trường. Khai báo encoding tường minh.

### Ghi vào thư mục không tồn tại hoặc không có quyền

Writer mở resource thất bại. Chuẩn bị thư mục và quyền truy cập trước khi Step chạy.

### Xóa file cũ khi restart

Có thể mất dữ liệu của các chunk đã commit. Phân biệt lần chạy mới và restart cùng JobInstance.

### Append không kiểm soát

Có thể lặp header, ghi trùng record hoặc nối dữ liệu của hai JobInstance. Dùng business key, output path và state rõ ràng.

### Tắt saveState nhưng mong restart tiếp tục

Writer không có checkpoint để khôi phục vị trí. Giữ saveState hoặc xây dựng cơ chế phục hồi riêng.

### Dùng writer singleton cho nhiều StepExecution đồng thời

State và file resource có thể bị chia sẻ. Dùng Step scope hoặc writer/resource riêng cho từng execution.

### Nhiều partition ghi cùng một file

Dòng có thể xen kẽ hoặc state bị xung đột. Ghi file riêng theo partition rồi hợp nhất.

### Nghĩ transaction buffering làm file và database atomic

Writer buffering bảo vệ việc ghi chunk theo cơ chế của writer nhưng không tạo XA giữa file và database. Dùng staging/publish hoặc idempotency khi cần.

### Dùng footer làm dấu hiệu Job thành công

Footer thuộc lifecycle writer. Kiểm tra Job status và quy trình publish trước khi công bố output.

### Không kiểm tra ký tự không biểu diễn được

Charset giới hạn có thể làm mất ký tự. Kiểm tra encoder và round-trip theo contract.

## 24. Quy trình thiết kế FlatFileItemWriter

Khi xây dựng Step xuất file, hãy xác định:

1. Resource output là file nào và thư mục có tồn tại/quyền ghi không?
2. Một item được chuyển thành dòng theo CSV, fixed-width hay format riêng?
3. FieldExtractor lấy property theo thứ tự nào?
4. Có cần quote/escape delimiter, quote và newline không?
5. Charset và line separator của hệ thống nhận là gì?
6. Có header hoặc footer không?
7. File đã tồn tại thì xóa, append hay từ chối?
8. Output có cần giữ file khi không có item không?
9. Writer có cần transactional buffering mặc định không?
10. saveState và writer name có ổn định cho restart không?
11. Có nhiều JobExecution hoặc partition cùng ghi file không?
12. Có cần file tạm, checksum, record count và bước publish không?
13. File được xác nhận thành công dựa trên BatchStatus, ExitStatus hay kiểm tra nghiệp vụ nào?

Nên kiểm thử các trường hợp: file mới, file đã tồn tại, chunk rollback, restart sau một số chunk commit, output rỗng, field có delimiter/quote/newline, ký tự Unicode, append, nhiều partition và process dừng khi đang ghi. Kiểm tra byte file cuối cùng bằng đúng charset và parser của hệ thống nhận nếu có thể.

## Kết luận

FlatFileItemWriter ghi item thành dòng văn bản thông qua LineAggregator và chuyển String thành byte theo encoding đã cấu hình. Một writer ổn định cần resource có thể ghi, format dòng đúng contract, header/footer có kiểm soát, chính sách file tồn tại rõ ràng, transactional buffering và saveState phù hợp với restart. Với CSV, phải xử lý quote/escape; với fixed-width, cần phân biệt độ rộng ký tự và byte. Không chia sẻ một writer có state cho nhiều execution hoặc partition cùng ghi một file. Với output quan trọng, hãy ghi vào file tạm, kiểm tra trạng thái và nội dung rồi mới publish cho hệ thống nhận.
