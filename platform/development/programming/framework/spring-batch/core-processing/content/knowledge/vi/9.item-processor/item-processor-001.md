# ItemProcessor biến đổi hoặc kiểm tra item

Trong Spring Batch, `ItemProcessor` là thành phần xử lý một item sau khi `ItemReader` đọc item đó và trước khi `ItemWriter` ghi kết quả. Processor thường được dùng để kiểm tra dữ liệu, chuẩn hóa giá trị, áp dụng quy tắc nghiệp vụ hoặc chuyển đổi một kiểu dữ liệu đầu vào thành kiểu dữ liệu phù hợp với hệ thống đích.

`ItemProcessor` giúp tách logic xử lý từng bản ghi khỏi logic đọc và ghi dữ liệu. Reader chịu trách nhiệm lấy item, processor quyết định item cần được biến đổi hoặc loại bỏ như thế nào, còn writer nhận các kết quả hợp lệ để ghi theo chunk. Nhờ đó, cùng một processor có thể được dùng với nhiều nguồn dữ liệu hoặc writer khác nhau nếu hợp đồng dữ liệu phù hợp.

## 1. ItemProcessor nằm ở đâu trong chunk processing?

Trong chunk-oriented Step, Spring Batch thực hiện chu trình đọc, xử lý và ghi theo từng nhóm item:

```text
Nguồn dữ liệu
     |
     v
  ItemReader<I>
     |
     v
ItemProcessor<I, O>
     |
     v
  ItemWriter<O>
     |
     v
 Commit chunk
```

Trong đó:

- `I` là kiểu item mà reader trả về.
- `O` là kiểu item mà processor trả về và writer nhận vào.
- Processor được gọi cho từng item được đọc, theo thứ tự xử lý của Step.
- Kết quả processor có thể là một item mới, item đã được sửa đổi hoặc `null` để lọc item khỏi luồng.

Ví dụ, reader đọc `CustomerInput` từ CSV, processor kiểm tra email và chuẩn hóa tên, rồi chuyển thành `Customer` để writer lưu vào database:

```java
ItemReader<CustomerInput> reader;
ItemProcessor<CustomerInput, Customer> processor;
ItemWriter<Customer> writer;
```

Kiểu đầu vào và đầu ra không cần giống nhau. Đây là điểm hữu ích khi dữ liệu nguồn có cấu trúc khác với mô hình mà ứng dụng muốn lưu.

## 2. Hợp đồng của ItemProcessor

Interface cơ bản có dạng:

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

Phương thức `process` nhận một item và trả về kết quả xử lý. Phương thức có thể ném exception nếu item không thể xử lý hoặc gặp lỗi cần được Step xử lý theo chính sách đã cấu hình.

Có ba kết quả quan trọng:

1. Trả về một object khác: item đã được biến đổi sang kết quả mới.
2. Trả về chính object đầu vào: item được giữ lại, có thể đã được cập nhật nếu model cho phép thay đổi.
3. Trả về `null`: item được lọc và không được chuyển đến writer.

Nếu processor ném exception, chunk step sẽ xử lý lỗi theo cấu hình transaction, skip và retry. Nếu không có chính sách xử lý lỗi phù hợp, lỗi có thể làm Step thất bại.

## 3. Dùng ItemProcessor để kiểm tra dữ liệu

Một nhiệm vụ phổ biến của processor là kiểm tra item trước khi ghi. Ví dụ, đơn hàng cần có mã đơn hàng, mã khách hàng và số tiền dương.

```java
public class OrderValidationProcessor
        implements ItemProcessor<OrderInput, OrderInput> {

    @Override
    public OrderInput process(OrderInput item) {
        if (item.orderId() == null || item.orderId().isBlank()) {
            throw new InvalidOrderException("Order ID is required");
        }

        if (item.customerId() == null || item.customerId().isBlank()) {
            throw new InvalidOrderException("Customer ID is required");
        }

        if (item.amount() == null || item.amount().signum() <= 0) {
            throw new InvalidOrderException("Order amount must be positive");
        }

        return item;
    }
}
```

Processor trên trả lại item nếu dữ liệu hợp lệ và ném `InvalidOrderException` nếu vi phạm quy tắc. Step có thể cấu hình exception này là lỗi skip nếu nghiệp vụ cho phép bỏ qua bản ghi sai định dạng.

Validation trong processor phù hợp với quy tắc phụ thuộc vào từng item, ví dụ trường bắt buộc, miền giá trị hoặc quan hệ giữa các trường của cùng bản ghi. Kiểm tra tổng thể như tham số Job có hợp lệ hay không thường thuộc `JobParametersValidator`; kiểm tra điều kiện tài nguyên chung trước khi chạy có thể thuộc một Step preflight.

### Phân biệt validation lỗi và lọc item

Không phải item nào không cần ghi cũng là item lỗi. Nếu một item hợp lệ nhưng không thuộc phạm vi cần xử lý, processor có thể trả về `null`. Nếu item vi phạm quy tắc dữ liệu và cần được ghi nhận như một lỗi, processor có thể ném exception.

Ví dụ, đơn hàng đã bị hủy có thể được lọc theo yêu cầu báo cáo; đơn hàng thiếu mã định danh có thể là dữ liệu lỗi:

```java
@Override
public Order process(OrderInput item) {
    if (item.cancelled()) {
        return null;
    }

    if (item.orderId() == null || item.orderId().isBlank()) {
        throw new InvalidOrderException("Missing order ID");
    }

    return toOrder(item);
}
```

`null` có nghĩa processor chủ động loại item khỏi pipeline. Exception có nghĩa việc xử lý item gặp lỗi; tùy cấu hình, lỗi có thể được skip, retry hoặc làm Step thất bại. Không nên dùng `null` để che giấu dữ liệu lỗi nếu ứng dụng cần báo cáo hoặc điều tra những bản ghi đó.

## 4. Dùng ItemProcessor để biến đổi dữ liệu

Processor cũng thường chuyển đổi kiểu dữ liệu nguồn sang mô hình đích. Ví dụ, CSV cung cấp số tiền dưới dạng chuỗi và ngày dưới dạng text, trong khi entity cần `BigDecimal` và `LocalDate`.

```java
public class InvoiceProcessor
        implements ItemProcessor<InvoiceInput, Invoice> {

    @Override
    public Invoice process(InvoiceInput input) {
        BigDecimal amount = new BigDecimal(input.amountText());
        LocalDate invoiceDate = LocalDate.parse(input.dateText());

        return new Invoice(
                input.invoiceNumber().trim(),
                input.customerCode().trim(),
                amount,
                invoiceDate);
    }
}
```

Ví dụ minh họa việc chuyển đổi định dạng. Trong ứng dụng thực tế, cần xử lý riêng lỗi parse, quy định locale/format của dữ liệu nguồn và xác định kiểu exception nào được xem là lỗi dữ liệu có thể skip.

Các dạng transformation thường gặp:

- Chuẩn hóa khoảng trắng, chữ hoa/chữ thường hoặc mã định danh.
- Chuyển đổi chuỗi thành ngày, số, tiền tệ hoặc enum.
- Ánh xạ DTO đầu vào sang entity hoặc model đích.
- Tính toán trường dẫn xuất như tổng tiền, thuế hoặc phí.
- Kết hợp giá trị trong cùng item để tạo cấu trúc dữ liệu mới.
- Gắn metadata nghiệp vụ cần thiết cho bản ghi đầu ra.

Processor nên tập trung vào xử lý một item. Việc đọc dữ liệu từ nguồn và ghi kết quả sang đích vẫn nên thuộc reader và writer để pipeline dễ theo dõi.

## 5. Kết hợp kiểm tra và biến đổi trong một processor

Một processor có thể vừa kiểm tra dữ liệu, vừa chuẩn hóa và chuyển đổi sang kiểu đích. Ví dụ:

```java
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, Customer> {

    @Override
    public Customer process(CustomerInput input) {
        String email = input.email() == null
                ? ""
                : input.email().trim().toLowerCase(Locale.ROOT);

        if (email.isBlank() || !email.contains("@")) {
            throw new InvalidCustomerException("Invalid email address");
        }

        String name = input.name() == null ? "" : input.name().trim();
        if (name.isBlank()) {
            throw new InvalidCustomerException("Customer name is required");
        }

        return new Customer(input.customerId(), name, email);
    }
}
```

Processor này biến `CustomerInput` thành `Customer` và không chuyển item không hợp lệ đến writer. `Locale.ROOT` giúp chuẩn hóa chữ thường theo locale ổn định, tránh kết quả thay đổi theo locale của máy chạy.

Với logic phức tạp, có thể tách validation và transformation thành các class riêng rồi kết hợp chúng bằng composite processor. Cách này giúp từng quy tắc dễ kiểm thử và tái sử dụng.

## 6. Đăng ký ItemProcessor trong Step

Trong Spring Batch 5, có thể khai báo một chunk Step bằng `StepBuilder` và truyền reader, processor, writer:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(200, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

Chunk size là 200 trong ví dụ. Spring Batch đọc và xử lý item, sau đó chuyển các kết quả không bị lọc đến writer khi chunk được hoàn tất theo chu trình của Step.

Nếu processor không cần transformation, có thể dùng một processor trả lại item hoặc bỏ qua processor khi không có logic xử lý. Không cần tạo processor rỗng chỉ để lấp một vị trí trong cấu hình.

## 7. Processor trả về null và cơ chế filtering

Khi `process` trả về `null`, Spring Batch xem item đó đã được lọc. Item không được chuyển đến writer. Đây là cách chính thức để loại item khỏi luồng chunk.

Ví dụ chỉ xuất hóa đơn đã được xác nhận:

```java
public class ConfirmedInvoiceProcessor
        implements ItemProcessor<InvoiceInput, Invoice> {

    @Override
    public Invoice process(InvoiceInput item) {
        if (!item.confirmed()) {
            return null;
        }
        return toInvoice(item);
    }
}
```

Các item bị lọc được phản ánh trong `filterCount` của `StepExecution`. Khi theo dõi kết quả, cần phân biệt:

- `readCount`: số item được reader đọc.
- `filterCount`: số item processor lọc bằng cách trả về `null`.
- `writeCount`: số item writer đã ghi.
- Các skip count: số item bị bỏ qua do exception được cấu hình skip ở reader, processor hoặc writer.

Không nên nhầm filtering với skip. Filtering là kết quả nghiệp vụ có chủ đích của processor; skip là chính sách fault tolerance xử lý một exception.

## 8. Exception trong ItemProcessor và skip/retry

`process` có thể ném exception. Trong chunk step, exception được xử lý theo cấu hình fault tolerance và quy tắc rollback của Step.

Ví dụ cấu hình skip một loại lỗi dữ liệu:

```java
return new StepBuilder("importCustomersStep", jobRepository)
        .<CustomerInput, Customer>chunk(200, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .faultTolerant()
        .skip(InvalidCustomerException.class)
        .skipLimit(50)
        .build();
```

Trong ví dụ, tối đa 50 lỗi thuộc loại `InvalidCustomerException` có thể được skip theo chính sách. Khi vượt giới hạn hoặc gặp lỗi không được skip, Step có thể thất bại.

Retry phù hợp hơn với lỗi tạm thời, ví dụ lỗi dịch vụ có thể phục hồi hoặc lỗi truy cập database. Không nên retry một lỗi dữ liệu không thể tự thay đổi, vì cùng một item sẽ tiếp tục thất bại.

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
```

Retry có thể khiến processor được gọi lại cho cùng item. Vì vậy, processor nên tránh tác dụng phụ như gửi email, ghi sang một database ngoài transaction hoặc gọi API không có idempotency. Nếu cần tác dụng phụ, hãy thiết kế cơ chế chống lặp hoặc chuyển tác vụ đó sang bước riêng.

## 9. Tách nhiều bước xử lý bằng CompositeItemProcessor

Khi logic gồm nhiều phép biến đổi độc lập, có thể dùng `CompositeItemProcessor` để nối nhiều processor thành một pipeline. Đầu ra của processor trước trở thành đầu vào của processor tiếp theo.

Ví dụ:

```java
@Bean
CompositeItemProcessor<CustomerInput, Customer> customerCompositeProcessor(
        ItemProcessor<CustomerInput, CustomerInput> validationProcessor,
        ItemProcessor<CustomerInput, NormalizedCustomer> normalizationProcessor,
        ItemProcessor<NormalizedCustomer, Customer> mappingProcessor) {

    return new CompositeItemProcessorBuilder<CustomerInput, Customer>()
            .delegates(
                    validationProcessor,
                    normalizationProcessor,
                    mappingProcessor)
            .build();
}
```

Ví dụ mô tả ba giai đoạn: kiểm tra dữ liệu, chuẩn hóa và ánh xạ sang entity. Các kiểu generic phải nối tiếp nhau chính xác: kiểu output của một delegate phải tương thích với kiểu input của delegate kế tiếp.

Composite processor hữu ích khi mỗi bước có trách nhiệm riêng, có thể kiểm thử độc lập hoặc tái sử dụng. Nếu chỉ có một vài dòng logic đơn giản, một processor duy nhất có thể dễ đọc hơn.

Nếu một delegate trả về `null`, item đã bị lọc khỏi pipeline; các delegate tiếp theo không xử lý item đó. Nếu delegate ném exception, lỗi được chuyển lên chunk Step và xử lý theo chính sách skip/retry đã cấu hình.

## 10. ClassifierCompositeItemProcessor

Khi các item thuộc nhiều loại và cần chọn processor khác nhau theo từng item, có thể dùng `ClassifierCompositeItemProcessor`. Classifier quyết định delegate phù hợp dựa trên nội dung item.

Ví dụ, hệ thống nhập hai loại giao dịch:

```java
@Bean
ClassifierCompositeItemProcessor<TransactionInput, Transaction> transactionProcessor(
        ItemProcessor<TransactionInput, Transaction> transferProcessor,
        ItemProcessor<TransactionInput, Transaction> paymentProcessor) {

    ClassifierCompositeItemProcessor<TransactionInput, Transaction> processor =
            new ClassifierCompositeItemProcessor<>();

    processor.setClassifier(item -> {
        if (item.type() == TransactionType.TRANSFER) {
            return transferProcessor;
        }
        if (item.type() == TransactionType.PAYMENT) {
            return paymentProcessor;
        }
        throw new IllegalArgumentException("Unsupported transaction type");
    });

    return processor;
}
```

Đây là cách tổ chức khi các nhóm item có quy tắc xử lý khác nhau nhưng cùng tạo ra một kiểu đầu ra `Transaction`. Nếu các nhánh trả về kiểu dữ liệu khác nhau, cần thiết kế kiểu đầu ra chung hoặc chuyển đổi kết quả trước khi đưa đến writer.

## 11. ItemProcessor và transaction

Processor chạy trong chu trình xử lý của chunk Step, nhưng không nên mặc định mọi hành động trong `process` đều được rollback. Transaction thường bảo vệ các tài nguyên tham gia transaction manager được cấu hình, chẳng hạn database transaction tương ứng.

Nếu processor chỉ biến đổi object trong bộ nhớ và trả kết quả, nó không cần tự mở transaction. Nếu processor gọi database hoặc một dịch vụ ngoài, cần xem xét ranh giới transaction và khả năng lặp lại.

Các nguyên tắc nên áp dụng:

- Giữ processor càng ít tác dụng phụ càng tốt.
- Không gửi email hoặc gọi API không idempotent trong `process`.
- Tránh ghi dữ liệu nghiệp vụ sang một database khác ngoài transaction mà Step quản lý nếu không có cơ chế phối hợp.
- Nếu cần tra cứu dữ liệu tham chiếu, xem xét cache hoặc bulk lookup để tránh một query riêng cho mỗi item.
- Đảm bảo việc retry không làm nhân đôi tác dụng phụ.

Một processor có thể gọi service để tính toán, nhưng nếu service thực hiện ghi dữ liệu, cần thiết kế rõ việc rollback và retry. Thường nên để processor tập trung tạo kết quả, còn writer chịu trách nhiệm ghi kết quả theo transaction của chunk.

## 12. Hiệu năng của ItemProcessor

Processor được gọi cho từng item, vì vậy chi phí nhỏ trên mỗi item có thể trở nên lớn khi xử lý hàng triệu bản ghi.

Ví dụ, nếu mỗi item gọi một câu SQL để lấy thông tin khách hàng, Job có thể tạo hàng triệu truy vấn nhỏ. Có thể cải thiện bằng cách:

- Nạp dữ liệu tham chiếu vào cache nếu dữ liệu có kích thước và thời gian sống phù hợp.
- Dùng reader truy vấn join hoặc projection để lấy sẵn dữ liệu cần thiết.
- Thiết kế bước enrichment theo nhóm nếu service hỗ trợ bulk request.
- Tránh parse/format lặp lại không cần thiết.
- Dùng object bất biến hoặc tái sử dụng cấu trúc phù hợp để kiểm soát cấp phát bộ nhớ.
- Đo thời gian xử lý mỗi item, throughput và tỷ lệ lỗi trước khi tối ưu.

Không nên đặt một cache không giới hạn trong processor khi số lượng khóa có thể tăng theo toàn bộ tập dữ liệu. Cần xem xét bộ nhớ, chính sách eviction và tính nhất quán của dữ liệu tham chiếu.

## 13. Kiểm thử ItemProcessor

Vì processor thường xử lý một item độc lập, có thể kiểm thử bằng unit test mà không cần khởi chạy toàn bộ Job.

Ví dụ kiểm tra transformation:

```java
class CustomerProcessorTest {

    private final CustomerProcessor processor = new CustomerProcessor();

    @Test
    void normalizesEmailAndName() throws Exception {
        CustomerInput input = new CustomerInput(
                "C-100", "  Nguyen An  ", " AN@EXAMPLE.COM ");

        Customer result = processor.process(input);

        assertEquals("Nguyen An", result.name());
        assertEquals("an@example.com", result.email());
    }
}
```

Nên có các nhóm trường hợp:

- Item hợp lệ được biến đổi đúng.
- Giá trị biên như chuỗi rỗng, null, số âm hoặc ngày không hợp lệ.
- Item bị lọc phải trả về `null`.
- Item lỗi phải ném đúng exception.
- Quy tắc chuẩn hóa phải ổn định với locale và định dạng dữ liệu.
- Composite processor nối đúng kiểu dữ liệu và thứ tự delegate.

Unit test giúp kiểm tra quy tắc từng item. Integration test ở cấp Step có thể kiểm tra thêm cách exception tương tác với skip/retry, filter count, writer và transaction.

## 14. Những lỗi thường gặp khi triển khai ItemProcessor

### Trả về null vì không biết xử lý lỗi thế nào

`null` có nghĩa lọc item có chủ đích. Nếu item không hợp lệ và cần thống kê, điều tra hoặc xử lý lại, hãy ném exception phù hợp để áp dụng skip/retry hoặc làm Step thất bại.

### Thực hiện ghi dữ liệu trong processor

Nếu processor tự ghi dữ liệu trong khi writer cũng ghi, trách nhiệm bị phân tán và có thể tạo tác dụng phụ khó rollback hoặc lặp khi retry. Hãy ưu tiên tạo kết quả trong processor và để writer thực hiện ghi.

### Gọi hệ thống ngoài cho từng item mà không kiểm soát tải

Một API call cho mỗi item có thể tạo tải lớn, timeout và rate limit. Hãy cân nhắc bulk API, giới hạn tốc độ, timeout và retry có backoff; bảo đảm request có thể lặp an toàn.

### Dùng exception quá chung

Ném `Exception` hoặc `RuntimeException` cho mọi trường hợp làm khó phân biệt lỗi dữ liệu với lỗi hệ thống. Tạo exception nghiệp vụ rõ ràng để cấu hình skip/retry chính xác.

### Chia sẻ trạng thái mutable giữa các item

Nếu processor giữ một object mutable dùng chung và thay đổi nó cho từng item, dữ liệu có thể bị rò giữa các lần gọi hoặc gây lỗi khi xử lý song song. Hãy tạo kết quả riêng cho từng item và kiểm soát thread safety nếu processor được dùng trong môi trường đa luồng.

### Giả định processor chỉ chạy đúng một lần cho mỗi item

Retry, rollback và restart có thể khiến logic xử lý được gọi lại. Không đặt tác dụng phụ không idempotent vào processor và không dựa vào số lần gọi để tạo ID nghiệp vụ.

## 15. Quy trình thiết kế ItemProcessor

Khi xây dựng processor cho một Job, có thể đi theo trình tự:

1. Xác định kiểu item reader trả về và kiểu dữ liệu writer cần nhận.
2. Liệt kê quy tắc validation áp dụng cho từng item.
3. Xác định phép chuẩn hóa, tính toán và mapping cần thực hiện.
4. Quyết định trường hợp nào được lọc bằng `null`, trường hợp nào phải ném exception.
5. Phân loại exception để cấu hình skip/retry phù hợp ở Step.
6. Giữ processor ít tác dụng phụ và thiết kế an toàn khi được gọi lại.
7. Tách các giai đoạn thành delegate nếu logic phức tạp hoặc cần tái sử dụng.
8. Kiểm thử các trường hợp hợp lệ, biên, bị lọc và lỗi.
9. Đo hiệu năng với dữ liệu đại diện để phát hiện truy vấn hoặc API call theo từng item quá tốn kém.

| Nhu cầu | Cách xử lý trong processor |
|---|---|
| Kiểm tra trường bắt buộc | Ném exception nghiệp vụ khi vi phạm. |
| Chuẩn hóa tên hoặc email | Trả về item đã chuẩn hóa hoặc object mới. |
| Chuyển DTO sang entity | Trả về kiểu đầu ra khác với kiểu đầu vào. |
| Loại item hợp lệ nhưng không thuộc phạm vi | Trả về `null`. |
| Lỗi tạm thời từ dịch vụ tham chiếu | Ném exception phù hợp và cấu hình retry ở Step nếu an toàn. |
| Nhiều quy tắc biến đổi độc lập | Kết hợp các delegate bằng composite processor. |

## Kết luận

`ItemProcessor<I, O>` xử lý từng item giữa reader và writer. Nó có thể kiểm tra dữ liệu, chuẩn hóa, tính toán và chuyển đổi kiểu đầu vào sang kiểu đầu ra. Trả về `null` sẽ lọc item khỏi writer; ném exception sẽ chuyển lỗi cho chính sách skip/retry hoặc làm Step thất bại. Khi thiết kế processor, hãy giữ logic tập trung theo từng item, hạn chế tác dụng phụ, bảo đảm an toàn khi retry/restart và tách các bước xử lý phức tạp thành những thành phần có thể kiểm thử độc lập.
