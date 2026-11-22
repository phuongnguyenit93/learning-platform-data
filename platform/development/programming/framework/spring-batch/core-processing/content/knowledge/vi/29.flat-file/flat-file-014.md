# LineAggregator

`LineAggregator<T>` là thành phần của Spring Batch chuyển một item Java thành một dòng văn bản để `FlatFileItemWriter` ghi ra file. Reader chuyển dữ liệu theo chiều ngược lại: đọc record và ánh xạ thành object; writer dùng aggregator để định dạng object thành record đầu ra.

Aggregator xác định cách biểu diễn một item trong file: thứ tự field, delimiter, định dạng số/ngày, padding hoặc quy tắc escape. Chọn đúng aggregator giúp file đầu ra tuân theo hợp đồng của hệ thống nhận dữ liệu và có thể được đọc lại ổn định.

## 1. LineAggregator nằm ở đâu trong FlatFileItemWriter?

Trong chunk-oriented step, writer nhận một chunk các item đã qua processor. `FlatFileItemWriter` lặp qua các item và gọi `LineAggregator.aggregate(item)` để tạo nội dung dòng. Writer thêm line separator và ghi kết quả vào resource.

```text
ItemWriter.write(chunk)
        |
        v
FlatFileItemWriter
        |
        +--> item 1 -> LineAggregator.aggregate(item 1) -> line 1
        +--> item 2 -> LineAggregator.aggregate(item 2) -> line 2
        +--> item 3 -> LineAggregator.aggregate(item 3) -> line 3
        |
        v
   Output file
```

Interface có hợp đồng đơn giản:

```java
public interface LineAggregator<T> {
    String aggregate(T item);
}
```

Mỗi lần gọi trả về nội dung của một record, không bao gồm trách nhiệm quản lý file hoặc tự ghi newline. `FlatFileItemWriter` quản lý resource, encoding, line separator, header/footer, checkpoint và transaction-aware output.

## 2. Cấu hình LineAggregator trong Spring Batch 5

Builder của `FlatFileItemWriter` nhận một `LineAggregator` để chuyển object thành dòng. Ví dụ xuất danh sách khách hàng:

```java
@Bean
@StepScope
FlatFileItemWriter<Customer> customerWriter(
        @Value("#{jobParameters['output.file']}") String outputFile,
        LineAggregator<Customer> customerLineAggregator) {

    return new FlatFileItemWriterBuilder<Customer>()
        .name("customerWriter")
        .resource(new FileSystemResource(outputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .lineAggregator(customerLineAggregator)
        .lineSeparator(System.lineSeparator())
        .saveState(true)
        .build();
}
```

`output.file` được late-bind khi StepScoped target được tạo. Writer nhận một aggregator đã cấu hình; mỗi item được định dạng theo cùng một hợp đồng. `name` ổn định và `saveState(true)` hỗ trợ lưu vị trí ghi để restart.

Trong production, cần chọn rõ chính sách file tồn tại, append/overwrite, encoding và restart. Những lựa chọn đó thuộc writer/resource configuration, không phải `LineAggregator`.

## 3. DelimitedLineAggregator cho file phân cách

`DelimitedLineAggregator<T>` ghép các giá trị được cung cấp bởi `FieldExtractor<T>` bằng một delimiter. Nó phù hợp với định dạng đơn giản như pipe-separated hoặc comma-separated khi quy tắc dữ liệu không yêu cầu escape phức tạp.

```java
@Bean
LineAggregator<Customer> customerLineAggregator() {
    DelimitedLineAggregator<Customer> aggregator =
        new DelimitedLineAggregator<>();

    aggregator.setDelimiter("|");
    aggregator.setFieldExtractor(customer -> new Object[] {
        customer.getCustomerId(),
        customer.getName(),
        customer.getEmail()
    });

    return aggregator;
}
```

Với một `Customer`, aggregator có thể tạo dòng:

```text
C001|An Nguyen|an@example.test
```

Thứ tự giá trị trong `Object[]` quyết định thứ tự cột. Header, nếu có, phải sử dụng đúng thứ tự đó. Nếu thay đổi thứ tự extractor mà không cập nhật schema file, consumer có thể đọc nhầm cột dù writer vẫn chạy thành công.

## 4. FieldExtractor tách dữ liệu khỏi cách định dạng

`FieldExtractor<T>` chuyển object thành mảng các giá trị theo thứ tự. Aggregator dùng mảng đó để tạo dòng. Tách hai trách nhiệm này giúp có thể thay đổi cách định dạng mà không phải viết lại logic lấy field.

```text
Customer object
      |
      v
FieldExtractor<Customer>
      |
      v
[customerId, name, email]
      |
      v
LineAggregator
      |
      v
"C001","An Nguyen","an@example.test"
```

Có thể dùng `BeanWrapperFieldExtractor` cho class theo JavaBean convention:

```java
BeanWrapperFieldExtractor<Customer> extractor =
    new BeanWrapperFieldExtractor<>();
extractor.setNames(new String[] {
    "customerId", "name", "email"
});
extractor.afterPropertiesSet();

DelimitedLineAggregator<Customer> aggregator =
    new DelimitedLineAggregator<>();
aggregator.setDelimiter(",");
aggregator.setFieldExtractor(extractor);
```

`BeanWrapperFieldExtractor` đọc các property theo tên đã khai báo, nên class cần cung cấp các property phù hợp. Với record, object bất thường hoặc quy tắc lấy field phức tạp, có thể dùng lambda/custom `FieldExtractor` để kiểm soát rõ ràng.

Ví dụ lambda:

```java
FieldExtractor<Invoice> invoiceExtractor = invoice -> new Object[] {
    invoice.getInvoiceNumber(),
    invoice.getInvoiceDate(),
    invoice.getTotalAmount()
};
```

Không đặt quy tắc nghiệp vụ hoặc truy vấn database vào extractor. Nó nên chỉ lấy giá trị từ item đã được chuẩn bị bởi processor.

## 5. DelimitedLineAggregator không tự thay thế hợp đồng CSV

Không nên mặc định rằng ghép các field bằng dấu phẩy đã tạo ra một file CSV an toàn. Một field có thể chứa dấu phẩy, dấu quote hoặc ký tự xuống dòng. Nếu chỉ nối chuỗi, record có thể bị tách sai khi consumer đọc lại.

Ví dụ dữ liệu:

```text
customerId = C001
name       = Nguyen, An
email      = an@example.test
```

Nối thẳng bằng dấu phẩy sẽ tạo:

```text
C001,Nguyen, An,an@example.test
```

Consumer có thể hiểu đây là bốn field thay vì ba. Một CSV tuân theo quy tắc quote cần biểu diễn tên thành `"Nguyen, An"` và escape dấu quote bên trong field bằng cách nhân đôi.

`DelimitedLineAggregator` hữu ích cho delimiter đơn giản, nhưng hãy kiểm tra rõ khả năng quoting/escaping của phiên bản và cấu hình đang dùng. Các thiết lập quote của `DelimitedLineTokenizer` ở phía reader không tự động cấu hình escaping cho aggregator ở phía writer.

## 6. Tạo custom LineAggregator để escape CSV

Khi cần CSV có quy tắc quote rõ ràng, có thể triển khai `LineAggregator<T>` trực tiếp. Hàm escape nên xử lý null, dấu quote, delimiter và newline theo dialect mà consumer yêu cầu.

```java
public class CustomerCsvLineAggregator
        implements LineAggregator<Customer> {

    @Override
    public String aggregate(Customer customer) {
        return String.join(",",
            csv(customer.getCustomerId()),
            csv(customer.getName()),
            csv(customer.getEmail())
        );
    }

    private String csv(String value) {
        if (value == null) {
            return "";
        }

        boolean mustQuote = value.contains(",")
            || value.contains("\"")
            || value.contains("\r")
            || value.contains("\n");

        String escaped = value.replace("\"", "\"\"");
        return mustQuote ? "\"" + escaped + "\"" : escaped;
    }
}
```

Ví dụ:

```text
C001,"Nguyen, An",an@example.test
```

Đây là ví dụ CSV cơ bản với delimiter dấu phẩy và quote dấu nháy kép. Nếu consumer yêu cầu quote mọi field, escape tab, ký tự điều khiển hoặc một dialect đặc biệt, hãy mở rộng quy tắc tương ứng hoặc dùng thư viện CSV chuyên dụng. Không tự tạo một dialect gần đúng rồi giả định mọi hệ thống đều đọc giống nhau.

## 7. FormatterLineAggregator cho định dạng có mẫu

`FormatterLineAggregator<T>` tạo dòng theo format string và `FieldExtractor<T>`. Nó hữu ích với fixed-width output hoặc định dạng mà mỗi field có độ rộng, căn lề và kiểu hiển thị cụ thể.

Ví dụ tạo record có mã đơn hàng 8 ký tự, tên khách hàng rộng 30 ký tự và số tiền 12 ký tự với hai chữ số thập phân:

```java
FormatterLineAggregator<Order> aggregator =
    new FormatterLineAggregator<>();

aggregator.setFormat("%-8s%-30s%012.2f");
aggregator.setFieldExtractor(order -> new Object[] {
    order.getOrderId(),
    order.getCustomerName(),
    order.getTotalAmount()
});
```

Với format trên:

- `%-8s`: chuỗi rộng tối thiểu 8 ký tự, căn trái.
- `%-30s`: chuỗi rộng tối thiểu 30 ký tự, căn trái.
- `%012.2f`: số thực rộng 12 ký tự, thêm số 0 ở đầu và giữ hai chữ số thập phân.

Độ rộng trong formatter thường là độ rộng tối thiểu; chuỗi dài hơn có thể vượt độ rộng nếu không có bước kiểm tra riêng. Nếu hợp đồng fixed-width yêu cầu cắt hoặc từ chối giá trị quá dài, hãy xác thực rõ ràng trước khi format. Không cắt dữ liệu định danh hoặc số tiền một cách âm thầm.

Locale cũng ảnh hưởng đến định dạng số. Nếu file yêu cầu dấu chấm làm decimal separator, hãy dùng formatter với locale được chỉ định hoặc chuẩn hóa số trước khi tạo dòng. Không dựa vào locale mặc định của máy chạy.

## 8. Custom formatter cho fixed-width

Với file fixed-width, độ dài và vị trí field là một phần của hợp đồng. Có thể dùng `FormatterLineAggregator` nếu format string đủ rõ; nếu có nhiều quy tắc kiểm tra độ dài, một `LineAggregator` tùy chỉnh có thể dễ bảo trì hơn.

Ví dụ:

```java
public class AccountFixedWidthAggregator
        implements LineAggregator<Account> {

    @Override
    public String aggregate(Account account) {
        String accountNo = requireLength(
            account.getAccountNumber(), 10, "accountNumber");
        String name = padRight(
            account.getName(), 30);
        String balance = String.format(
            Locale.ROOT, "%012.2f", account.getBalance());

        return accountNo + name + balance;
    }

    private String requireLength(String value, int length, String field) {
        if (value == null || value.length() != length) {
            throw new IllegalArgumentException(
                field + " must contain exactly " + length + " characters");
        }
        return value;
    }

    private String padRight(String value, int width) {
        String text = value == null ? "" : value;
        if (text.length() > width) {
            throw new IllegalArgumentException("name is too long");
        }
        return text + " ".repeat(width - text.length());
    }
}
```

Ví dụ minh họa việc xác thực và padding; cần điều chỉnh độ rộng, encoding và cách tính ký tự theo đặc tả của file đích. Một số hệ thống legacy định nghĩa vị trí theo byte thay vì số ký tự, đặc biệt với charset đa byte. Khi đó, padding theo `String.length()` có thể không đủ; cần tính độ dài byte theo charset thực tế.

## 9. Dùng PassThroughLineAggregator khi item đã là dòng

Nếu item đã chứa sẵn một dòng văn bản hoàn chỉnh, có thể dùng `PassThroughLineAggregator<String>` để trả lại chuỗi đó mà không tách field.

```java
@Bean
FlatFileItemWriter<String> rawLineWriter(Resource outputResource) {
    return new FlatFileItemWriterBuilder<String>()
        .name("rawLineWriter")
        .resource(outputResource)
        .lineAggregator(new PassThroughLineAggregator<>())
        .saveState(true)
        .build();
}
```

Cách này phù hợp khi processor đã tạo record theo đúng schema. Tuy nhiên, khi logic tạo dòng nằm trong processor, cần kiểm thử định dạng tại processor và giữ hợp đồng output rõ ràng. Không dùng pass-through để né việc validate dữ liệu hoặc escape field.

## 10. Header và footer thuộc writer

`LineAggregator` định dạng từng item. Header và footer là nội dung ngoài các item, do `FlatFileItemWriter` quản lý thông qua callback riêng.

```java
@Bean
FlatFileItemWriter<Customer> customerWriter(
        Resource outputResource,
        LineAggregator<Customer> customerLineAggregator) {

    return new FlatFileItemWriterBuilder<Customer>()
        .name("customerWriter")
        .resource(outputResource)
        .encoding(StandardCharsets.UTF_8.name())
        .headerCallback(writer ->
            writer.write("customerId,name,email"))
        .footerCallback(writer ->
            writer.write("# end of customer export"))
        .lineAggregator(customerLineAggregator)
        .saveState(true)
        .build();
}
```

Header phải khớp thứ tự field mà aggregator xuất ra. Footer có thể chứa số lượng, checksum hoặc marker kết thúc nếu consumer yêu cầu, nhưng không nên coi sự xuất hiện của footer là bằng chứng job đã hoàn tất thành công trong mọi tình huống. Nếu cần công bố file chỉ sau khi toàn bộ job thành công, nên ghi file tạm rồi dùng một bước cuối để xác minh và publish.

## 11. Định dạng ngày, số và null ổn định

File output thường được đọc bởi hệ thống khác, vì vậy format phải ổn định giữa các máy chạy và các lần deploy.

Đối với ngày, dùng formatter rõ ràng:

```java
DateTimeFormatter dateFormat = DateTimeFormatter.ISO_LOCAL_DATE;
String date = order.getOrderDate().format(dateFormat);
```

Đối với số tiền, dùng `BigDecimal` và định dạng có quy tắc decimal separator, scale và rounding rõ ràng. Không chuyển tiền qua `double` nếu cần độ chính xác thập phân.

Đối với null, xác định consumer mong đợi chuỗi rỗng, marker như `\N`, hay một giá trị mặc định. Không để `String.valueOf(null)` tạo ra chuỗi `null` nếu schema yêu cầu field rỗng.

Custom aggregator có thể gom các quy tắc này vào một nơi:

```java
private String formatAmount(BigDecimal amount) {
    if (amount == null) {
        return "";
    }
    return amount.setScale(2, RoundingMode.HALF_UP)
        .toPlainString();
}
```

Quy tắc rounding phải đến từ hợp đồng nghiệp vụ, không tự chọn chỉ vì tiện định dạng.

## 12. Cấu hình line separator và encoding

`LineAggregator` trả về nội dung một record. `FlatFileItemWriter` thêm line separator giữa các record theo cấu hình. Có thể chọn `\n` hoặc `\r\n` tùy hệ thống nhận.

```java
return new FlatFileItemWriterBuilder<Customer>()
    .name("customerWriter")
    .resource(outputResource)
    .encoding(StandardCharsets.UTF_8.name())
    .lineSeparator("\r\n")
    .lineAggregator(customerLineAggregator)
    .build();
```

Không nên tự thêm `\n` trong `aggregate()` nếu writer cũng thêm line separator, vì có thể tạo dòng trống giữa các record. Encoding cũng thuộc writer; aggregator chỉ tạo Java `String`, không chuyển chuỗi thành byte.

Nếu consumer yêu cầu Windows CRLF, UTF-8 BOM hoặc một code page cụ thể, hãy cấu hình và kiểm thử chính xác trên byte output chứ không chỉ so sánh string trong unit test.

## 13. Xử lý lỗi trong LineAggregator

`LineAggregator.aggregate(item)` không khai báo checked exception. Nếu không thể định dạng item, implementation có thể ném runtime exception. Khi đó writer call thất bại và chunk có thể rollback theo transaction policy của step.

Ví dụ item có field bắt buộc bị thiếu:

```java
@Override
public String aggregate(Customer customer) {
    if (customer.getCustomerId() == null) {
        throw new IllegalArgumentException(
            "customerId is required for export");
    }
    return customer.getCustomerId() + "," + csv(customer.getName());
}
```

Hãy xác thực dữ liệu đầu ra trước hoặc trong processor nếu lỗi có ý nghĩa nghiệp vụ của item. Aggregator nên tập trung định dạng; nếu aggregator chứa nhiều validation và truy vấn, trách nhiệm của nó sẽ khó kiểm thử.

Nếu lỗi định dạng có thể skip, cấu hình skip policy cho exception phù hợp trong fault-tolerant step và dùng `SkipListener` để ghi nhận item bị loại. Đảm bảo việc writer bị gọi lại trong recovery không tạo output trùng hoặc file dở dang.

## 14. LineAggregator và transaction của file writer

`FlatFileItemWriter` là `ItemStreamWriter`, tham gia transaction lifecycle của chunk. Với cấu hình transactional mặc định của writer, dữ liệu ghi được quản lý qua cơ chế buffer gắn với transaction để output chưa commit không bị coi là đã hoàn tất. Có thể cấu hình `transactional(false)` cho một số trường hợp, nhưng khi đó nội dung có thể được ghi ngay và không thể tự rollback cùng database transaction.

```text
Chunk transaction bắt đầu
       |
       v
Writer gọi LineAggregator cho từng item
       |
       v
Output được buffer theo writer transaction policy
       |
       +-- COMMIT --> flush nội dung chunk
       |
       +-- ROLLBACK -> loại bỏ phần output chưa commit nếu writer transactional
```

Không giả định file và database luôn được commit nguyên tử với nhau. Nếu file writer và database dùng các tài nguyên khác nhau, transaction manager có thể không phối hợp chúng như một distributed transaction. Với yêu cầu publish nhất quán, hãy ghi file tạm, hoàn tất dữ liệu, xác minh và đổi tên/công bố trong bước cuối phù hợp.

## 15. Restart và state của FlatFileItemWriter

Writer cần tên ổn định và `saveState(true)` nếu step phải restart. Spring Batch lưu thông tin cần thiết để biết vị trí ghi và tiếp tục output của cùng execution.

```java
new FlatFileItemWriterBuilder<Order>()
    .name("ordersOutputWriter")
    .resource(new FileSystemResource(outputFile))
    .lineAggregator(orderLineAggregator)
    .saveState(true)
    .build();
```

Khi restart cùng JobInstance, hãy dùng cùng output resource và cùng identifying parameters. Không thay file đầu ra hoặc xóa nội dung đã commit giữa hai execution nếu muốn khôi phục đúng vị trí.

Nếu `saveState(false)`, writer không lưu checkpoint. Điều này chỉ phù hợp khi step không cần restart hoặc ứng dụng có chiến lược phục hồi khác. Không tắt state rồi vẫn kỳ vọng writer tự biết vị trí đã ghi.

## 16. Append, overwrite và file đã tồn tại

Chính sách khi output file đã tồn tại cần được chọn rõ. Các lựa chọn thường gặp gồm:

- Ghi file mới/ghi đè cho một lần chạy mới.
- Append vào file hiện có theo một quy trình được thiết kế rõ.
- Restart cùng execution và tiếp tục tại checkpoint đã lưu.

`append(true)` không đồng nghĩa với restart an toàn. Append thủ công vào file cũ có thể tạo header trùng, record trùng hoặc dữ liệu từ hai lần nghiệp vụ khác nhau trong cùng file. Restart nên dựa trên JobRepository và writer state, không dựa vào việc bật append để nối tiếp tùy ý.

Ví dụ cấu hình overwrite cho lần chạy mới:

```java
return new FlatFileItemWriterBuilder<Order>()
    .name("ordersOutputWriter")
    .resource(new FileSystemResource(outputFile))
    .shouldDeleteIfExists(true)
    .append(false)
    .lineAggregator(orderLineAggregator)
    .saveState(true)
    .build();
```

Hãy kiểm tra hành vi của writer khi mở resource trong cả lần chạy mới và restart. Các tùy chọn xóa/append cần phối hợp với state đã lưu; không thay đổi chúng tùy tiện giữa các lần thực thi cùng JobInstance.

## 17. Đảm bảo thứ tự và schema output

Output file thường là hợp đồng tích hợp. Cần ghi rõ:

1. Thứ tự cột.
2. Tên và ý nghĩa từng cột.
3. Delimiter, quote và escape.
4. Format ngày, timezone và decimal separator.
5. Quy tắc null/empty.
6. Encoding và line separator.
7. Header/footer và version schema.
8. Quy tắc xử lý field quá dài hoặc giá trị không hợp lệ.

Không nên dựa vào thứ tự field tình cờ của reflection hoặc map. Hãy khai báo thứ tự rõ trong `FieldExtractor` hoặc custom aggregator. Khi schema thay đổi, cân nhắc version file hoặc tên output mới để consumer không đọc nhầm.

## 18. Kiểm thử LineAggregator

Aggregator có thể được unit test độc lập vì nó nhận một item và trả về string. Kiểm thử nên xác nhận chính xác nội dung, bao gồm trường hợp biên.

Ví dụ:

```java
@Test
void shouldQuoteCommaAndEscapeQuoteInCsvField() {
    Customer customer = new Customer(
        "C001", "An, \"Annie\" Nguyen", "an@example.test");

    String line = new CustomerCsvLineAggregator().aggregate(customer);

    assertThat(line).isEqualTo(
        "C001,\"An, \"\"Annie\"\" Nguyen\",an@example.test");
}
```

Các trường hợp nên kiểm tra:

- Giá trị bình thường và thứ tự field.
- Null, chuỗi rỗng và khoảng trắng.
- Delimiter nằm bên trong field.
- Dấu quote cần escape.
- CR/LF bên trong field nếu dialect cho phép.
- Số tiền, scale và rounding.
- Ngày giờ, timezone và locale.
- Field vượt độ rộng fixed-width.
- Ký tự Unicode và encoding output.

Integration test với `FlatFileItemWriter` nên kiểm tra header/footer, line separator, file tồn tại, restart/checkpoint và transaction rollback. Unit test aggregator không chứng minh writer quản lý resource và transaction đúng.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Ghép field bằng delimiter mà không escape | Field chứa delimiter làm sai số cột | Dùng custom aggregator hoặc thư viện CSV theo dialect |
| Nhầm tokenizer quote với writer escaping | Output không tương thích file reader | Cấu hình quy tắc định dạng ở aggregator riêng |
| Thay thứ tự FieldExtractor nhưng quên header | Consumer đọc nhầm cột | Giữ schema và thứ tự header đồng bộ |
| Đưa business validation vào aggregator | Logic khó tái sử dụng và khó kiểm thử | Validate/transform ở processor; aggregator tập trung format |
| Tự thêm newline trong `aggregate()` | Writer có thể tạo dòng trống | Để writer quản lý `lineSeparator` |
| Dựa vào locale mặc định | Decimal/date format khác giữa môi trường | Chỉ định locale và formatter rõ ràng |
| Cắt field fixed-width âm thầm | Mất dữ liệu hoặc sai định danh | Validate độ dài và fail có thông tin |
| Dùng append để giả lập restart | Header/record có thể bị lặp | Dùng writer state và JobRepository |
| Tắt saveState nhưng vẫn cần restart | Không khôi phục được vị trí output | Bật state và dùng tên writer ổn định |
| Coi file và database là một transaction nguyên tử | File có thể còn side effect khi database rollback | Dùng file tạm, verify và publish ở bước cuối |

## 20. Quy trình thiết kế LineAggregator cho production

Khi xuất file từ Spring Batch, hãy xác định:

1. Consumer cần CSV/delimited, fixed-width hay một format riêng?
2. Thứ tự field và schema có được định nghĩa rõ không?
3. Có cần quote/escape delimiter, quote và newline không?
4. Null, ngày, số và decimal separator được biểu diễn thế nào?
5. Field có giới hạn độ dài theo ký tự hay byte?
6. Có cần header/footer hoặc version schema không?
7. Writer dùng encoding, line separator và resource policy nào?
8. Output có cần restart và transaction-aware buffering không?
9. File có được công bố chỉ sau khi toàn bộ job thành công không?
10. Unit/integration test có xác nhận byte output, restart và rollback không?

## Kết luận

`LineAggregator<T>` chuyển một item Java thành một dòng văn bản cho `FlatFileItemWriter`. `DelimitedLineAggregator` ghép các field theo delimiter; `FormatterLineAggregator` định dạng theo mẫu; `FieldExtractor` xác định thứ tự giá trị; custom aggregator cho phép kiểm soát CSV escaping, fixed-width và các quy tắc đặc thù.

Hãy tách việc lấy field khỏi việc định dạng, không giả định nối delimiter đã tạo CSV hợp lệ, và để writer quản lý header/footer, encoding, line separator, resource, checkpoint và transaction-aware output. Giữ schema ổn định, kiểm thử chính xác record đầu ra và dùng file tạm cùng bước publish khi cần tránh công bố file chưa hoàn chỉnh.
