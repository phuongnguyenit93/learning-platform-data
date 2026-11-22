# ClassifierCompositeItemWriter

Trong Spring Batch, ClassifierCompositeItemWriter<T> định tuyến từng item đầu vào tới một ItemWriter được chọn bởi Classifier. Với mỗi item, classifier xem dữ liệu và trả về writer phù hợp; writer đó chịu trách nhiệm ghi item. Điều này hữu ích khi một chunk chứa nhiều loại kết quả hoặc nhiều nhóm nghiệp vụ cần được ghi tới các đích khác nhau.

Ví dụ, một step đọc các giao dịch thanh toán nhưng cần ghi giao dịch CARD vào writer dành cho thẻ và giao dịch BANK_TRANSFER vào writer dành cho chuyển khoản. Reader và processor vẫn tạo cùng kiểu Payment; classifier quyết định writer dựa trên phương thức thanh toán.

ClassifierCompositeItemWriter thực hiện routing, không broadcast. Mỗi item được chuyển tới writer được chọn, thay vì gửi cùng item tới tất cả delegate. Nếu mục tiêu là ghi mọi item tới nhiều writer, hãy xem CompositeItemWriter. Nếu cần biến đổi item theo loại trước khi ghi, hãy xem processor phân loại như ClassifierCompositeItemProcessor.

## 1. Vai trò trong chunk-oriented step

Trong chunk step, reader lấy item, processor có thể chuẩn hóa hoặc chuyển đổi, sau đó writer ghi kết quả. ClassifierCompositeItemWriter nằm ở vị trí writer và nhận kiểu output cuối của processor.

~~~mermaid
flowchart LR
    A[ItemReader] --> B[ItemProcessor]
    B --> C[Chunk of items]
    C --> D[ClassifierCompositeItemWriter]
    D --> E{Classifier}
    E -->|Route A| F[Writer A]
    E -->|Route B| G[Writer B]
    E -->|Route C| H[Writer C]
~~~

Ví dụ một chunk có các item theo thứ tự:

| Item | Thuộc tính phân loại | Writer được chọn |
|---|---|---|
| Payment 1 | CARD | cardPaymentWriter |
| Payment 2 | BANK_TRANSFER | bankTransferWriter |
| Payment 3 | CARD | cardPaymentWriter |
| Payment 4 | CASH | cashPaymentWriter |

Một chunk có thể chứa item đi tới nhiều writer khác nhau. Classifier được áp dụng cho từng item, vì vậy việc phân loại không yêu cầu cả chunk chỉ có một loại dữ liệu.

## 2. Các thành phần chính

Có ba thành phần cần hiểu:

| Thành phần | Trách nhiệm |
|---|---|
| Classifier<T, C> | Nhận item kiểu T và chọn một đối tượng đích kiểu C |
| ItemWriter<T> | Ghi một chunk các item có kiểu tương thích T |
| ClassifierCompositeItemWriter<T> | Gọi classifier cho từng item và chuyển item tới writer được chọn |

Về mặt generic, classifier của composite writer trả về một writer có thể nhận kiểu item T, thường được khai báo dưới dạng ItemWriter<? super T>. Điều này có nghĩa delegate writer phải chấp nhận chính kiểu item hoặc một kiểu cha của nó.

Ví dụ, nếu composite có kiểu ClassifierCompositeItemWriter<Payment>, các delegate như ItemWriter<Payment> hoặc ItemWriter<Object> có thể phù hợp. Một ItemWriter<CardPayment> không thể được gắn trực tiếp nếu CardPayment là subtype của Payment, vì writer chỉ nhận CardPayment chứ không nhận mọi Payment. Muốn định tuyến các subtype khác nhau tới writer có generic hẹp hơn, cần adapter có kiểu nhận chung và kiểm tra/cast an toàn.

## 3. Cách hoạt động khi ghi

ClassifierCompositeItemWriter nhận một Chunk<? extends T>. Với từng item trong chunk, nó gọi classifier để lấy writer rồi chuyển item cho writer đó. Trong cách triển khai chuẩn, delegate được gọi với một chunk chứa item đang xét; do đó một writer có thể được gọi nhiều lần trong một lần gọi write của composite.

Luồng xử lý:

1. Step hoàn thành read/process cho chunk hiện tại.
2. Step gọi write(chunk) trên composite writer.
3. Composite duyệt từng item trong chunk.
4. Classifier chọn delegate writer dựa trên item.
5. Composite gọi writer được chọn để ghi item đó.
6. Sau khi các lời gọi ghi hoàn tất, step tiếp tục commit transaction theo cấu hình.

Điều này khác với một writer tự nhóm toàn bộ item theo đích rồi gọi mỗi delegate một lần với danh sách tương ứng. Vì vậy, nếu delegate thực hiện bulk insert hoặc batch API, cần lưu ý rằng việc định tuyến từng item có thể làm giảm hiệu quả batching. Có thể cần custom routing writer để gom item theo destination trước khi gọi từng writer.

## 4. Cấu hình cơ bản bằng Classifier

Một Classifier có thể được viết bằng lambda. Ví dụ định tuyến payment theo phương thức:

~~~java
@Bean
ClassifierCompositeItemWriter<Payment> paymentWriter(
        ItemWriter<Payment> cardPaymentWriter,
        ItemWriter<Payment> bankTransferWriter,
        ItemWriter<Payment> cashPaymentWriter) {

    Classifier<Payment, ItemWriter<? super Payment>> classifier =
            payment -> switch (payment.method()) {
                case CARD -> cardPaymentWriter;
                case BANK_TRANSFER -> bankTransferWriter;
                case CASH -> cashPaymentWriter;
            };

    ClassifierCompositeItemWriter<Payment> writer =
            new ClassifierCompositeItemWriter<>();
    writer.setClassifier(classifier);
    return writer;
}
~~~

Trong ví dụ, cả ba delegate đều nhận Payment. Classifier đọc payment.method() và trả đúng writer. Switch trên enum giúp compiler nhắc tới các trường hợp chưa xử lý khi enum được mở rộng, tùy phiên bản Java và cách viết switch.

Nếu classifier không tìm được writer, không nên trả về null. Hãy định nghĩa rõ default route hoặc ném exception có ý nghĩa để step thất bại theo chính sách. Một writer null sẽ khiến quá trình ghi lỗi tại thời điểm dispatch và khó hiểu nguyên nhân hơn.

## 5. Cấu hình theo điều kiện nghiệp vụ

Classifier không bắt buộc chỉ dựa trên enum. Nó có thể dùng bất kỳ thuộc tính ổn định nào của item:

- Trạng thái giao dịch.
- Loại khách hàng.
- Kênh bán hàng.
- Tenant hoặc vùng dữ liệu.
- Mức ưu tiên.
- Loại record.

Ví dụ định tuyến đơn hàng đang hoạt động và đơn hàng lưu trữ:

~~~java
Classifier<Order, ItemWriter<? super Order>> orderClassifier =
        order -> {
            if (order.status() == OrderStatus.ARCHIVED) {
                return archivedOrderWriter;
            }
            return activeOrderWriter;
        };
~~~

Nếu dữ liệu có nhiều trạng thái, nên dùng switch hoặc map rõ ràng thay vì nhiều nhánh if lồng nhau. Nếu một trạng thái chưa được hỗ trợ, hãy quyết định có reject, ghi vào writer lỗi hay fail job. Không tự động route dữ liệu chưa biết vào writer mặc định nếu điều đó có thể làm sai báo cáo hoặc mất kiểm soát.

## 6. Khai báo delegate writers

Delegate có thể là các writer có sẵn của Spring Batch hoặc writer tùy chỉnh. Ví dụ, cùng kiểu Payment được ghi vào hai bảng khác nhau:

~~~java
@Bean
JdbcBatchItemWriter<Payment> cardPaymentWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Payment>()
            .dataSource(dataSource)
            .sql("""
                    insert into card_payment
                        (payment_id, amount, card_reference)
                    values
                        (:paymentId, :amount, :reference)
                    """)
            .beanMapped()
            .build();
}

@Bean
JdbcBatchItemWriter<Payment> bankTransferWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Payment>()
            .dataSource(dataSource)
            .sql("""
                    insert into bank_transfer_payment
                        (payment_id, amount, bank_reference)
                    values
                        (:paymentId, :amount, :reference)
                    """)
            .beanMapped()
            .build();
}
~~~

Ví dụ giả định model Payment có các property mà hai câu SQL cần dùng. Trong ứng dụng thực tế, các writer có thể dùng model chung, custom ItemPreparedStatementSetter hoặc ItemSqlParameterSourceProvider để ánh xạ field chính xác.

Một item được ghi vào writer được classifier chọn. Nếu cần ghi đồng thời vào cả hai bảng để tạo audit copy, classifier composite không đáp ứng yêu cầu broadcast; hãy dùng CompositeItemWriter hoặc writer điều phối riêng.

## 7. Gắn ClassifierCompositeItemWriter vào step

Ở cấp step, composite writer được khai báo như một ItemWriter<T> bình thường:

~~~java
@Bean
Step routePaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<PaymentInput> paymentReader,
        ItemProcessor<PaymentInput, Payment> paymentProcessor,
        ItemWriter<Payment> paymentWriter) {

    return new StepBuilder("routePaymentsStep", jobRepository)
            .<PaymentInput, Payment>chunk(100, transactionManager)
            .reader(paymentReader)
            .processor(paymentProcessor)
            .writer(paymentWriter)
            .build();
}
~~~

Reader cung cấp PaymentInput, processor trả Payment, và classifier writer định tuyến từng Payment tới đúng đích. Step không cần biết số lượng delegate hoặc tiêu chí routing cụ thể.

Điều này giúp thay đổi mapping route hoặc thêm writer mới mà không phải sửa reader và processor, miễn là kiểu output của pipeline vẫn là Payment.

## 8. Phân biệt routing và broadcasting

Hai loại composite writer thường bị nhầm:

| Writer | Hành vi |
|---|---|
| ClassifierCompositeItemWriter<T> | Chọn một writer cho từng item |
| CompositeItemWriter<T> | Gửi chunk tới các delegate writers theo thứ tự cấu hình |

Ví dụ, nếu một payment CARD chỉ được ghi vào bảng card payment, dùng classifier writer. Nếu mọi payment cần ghi vào bảng payment chính và đồng thời ghi audit record, dùng composite writer hoặc một writer điều phối có chủ đích.

Không cấu hình nhiều delegate trong classifier với kỳ vọng item sẽ được ghi tới tất cả. Classifier trả về một writer đích cho item đang phân loại.

## 9. Routing theo subtype và generic type

Một trường hợp thường gặp là reader trả về nhiều subtype cùng kế thừa một interface:

~~~java
public interface ImportRecord {
    String recordId();
}

public record CustomerRecord(
        String recordId,
        String customerName) implements ImportRecord {
}

public record OrderRecord(
        String recordId,
        String customerId,
        BigDecimal amount) implements ImportRecord {
}
~~~

Classifier writer có kiểu tổng thể ClassifierCompositeItemWriter<ImportRecord>. Tuy nhiên, ItemWriter<CustomerRecord> không thể dùng trực tiếp làm ItemWriter<? super ImportRecord> vì nó không thể nhận OrderRecord.

Có thể dùng adapter nhận kiểu cha rồi kiểm tra subtype trước khi chuyển cho writer chuyên biệt:

~~~java
public class CustomerRecordWriter implements ItemWriter<ImportRecord> {

    private final ItemWriter<CustomerRecord> delegate;

    public CustomerRecordWriter(ItemWriter<CustomerRecord> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends ImportRecord> items)
            throws Exception {
        for (ImportRecord item : items) {
            if (!(item instanceof CustomerRecord customer)) {
                throw new IllegalArgumentException(
                        "Expected CustomerRecord but got "
                                + item.getClass().getName());
            }
            delegate.write(Chunk.of(customer));
        }
    }
}
~~~

Adapter có thể được viết tương tự cho OrderRecord. Classifier chọn adapter theo subtype. Cách này giữ kiểm tra kiểu ở một ranh giới rõ ràng thay vì dùng raw type hoặc unchecked cast trong classifier.

Nếu các writer có thể nhận chung một kiểu base class/interface và tự xử lý các property chung, có thể dùng trực tiếp ItemWriter<ImportRecord> cho đơn giản hơn.

## 10. Dùng classifier theo class

Khi routing phụ thuộc vào subtype, có thể dùng một classifier chuyên biệt hoặc lambda instanceof:

~~~java
Classifier<ImportRecord, ItemWriter<? super ImportRecord>> classifier =
        record -> {
            if (record instanceof CustomerRecord) {
                return customerRecordWriter;
            }
            if (record instanceof OrderRecord) {
                return orderRecordWriter;
            }
            throw new IllegalArgumentException(
                    "Unsupported record type: "
                            + record.getClass().getName());
        };
~~~

Với nhiều subtype, một map từ class tới writer có thể dễ quản lý hơn. Nếu dùng classifier theo superclass/interface, xác định rõ thứ tự ưu tiên khi một class khớp nhiều rule. Không dựa vào thứ tự iteration của map không có bảo đảm để quyết định route.

## 11. Đăng ký lifecycle cho delegate ItemStream

Một điểm quan trọng khi dùng classifier writer là lifecycle của các delegate. ClassifierCompositeItemWriter điều phối lời gọi write, nhưng không tự động mở, cập nhật và đóng tất cả delegate writers như một ItemStream tổng hợp.

Nếu delegate writer triển khai ItemStream hoặc ItemStreamWriter, cần đăng ký từng delegate với step để Spring Batch gọi lifecycle:

~~~java
@Bean
Step exportPaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Payment> paymentReader,
        ItemWriter<Payment> classifierWriter,
        FlatFileItemWriter<Payment> cardFileWriter,
        FlatFileItemWriter<Payment> bankFileWriter) {

    return new StepBuilder("exportPaymentsStep", jobRepository)
            .<Payment, Payment>chunk(100, transactionManager)
            .reader(paymentReader)
            .writer(classifierWriter)
            .stream(cardFileWriter)
            .stream(bankFileWriter)
            .build();
}
~~~

stream(...) đăng ký delegate stream với step để chúng được mở, cập nhật state và đóng theo lifecycle của step. Nếu không đăng ký, writer dạng file có thể không được khởi tạo/đóng đúng cách hoặc không lưu checkpoint như mong đợi.

Không cần đăng ký riêng delegate không triển khai ItemStream. Nhưng hãy kiểm tra kiểu thực tế của writer, đặc biệt với writer tùy chỉnh hoặc wrapper. Nếu adapter che mất interface ItemStream của delegate, cần đăng ký stream gốc hoặc thiết kế adapter cũng triển khai và chuyển tiếp lifecycle.

## 12. Restart và state của từng writer

Một số writer giữ state như vị trí file, số record đã ghi hoặc metadata cần thiết để tiếp tục sau restart. Khi classifier có nhiều delegate, mỗi writer có thể có state riêng.

Để restart đúng:

- Đăng ký mọi delegate ItemStream với step.
- Đặt name ổn định và duy nhất cho từng writer cần lưu state.
- Giữ resource/output path và routing rule ổn định trong lần restart.
- Không thay đổi tiêu chí phân loại khiến item tiếp theo đi tới đích khác so với lần chạy ban đầu nếu state cũ phụ thuộc route.
- Xác định cách phục hồi output nếu một writer đã ghi được một phần trước khi step thất bại.

Ví dụ, nếu writer A ghi file card.csv và writer B ghi file bank.csv, cả hai file phải có lifecycle và checkpoint riêng. Nếu restart job với file path mới hoặc đổi route, kết quả có thể không còn nhất quán với phần đã ghi trước đó.

## 13. Transaction và nhiều writer

Các delegate được gọi trong giai đoạn write của cùng chunk. Nếu các writer ghi vào cùng database transaction và dùng cùng transaction manager/resource, lỗi ở một delegate có thể làm transaction chunk rollback theo cấu hình.

Tuy nhiên, không nên giả định mọi loại output đều rollback nguyên tử:

- Hai JdbcBatchItemWriter dùng cùng transaction-managed DataSource thường có thể tham gia cùng transaction.
- Writer ghi vào database khác hoặc transaction manager khác có thể không thuộc transaction đó.
- Gọi REST API, gửi message trực tiếp hoặc ghi file không tự động có cùng tính nguyên tử với database transaction.
- Một delegate có thể đã tạo side effect trước khi delegate sau ném exception.

Nếu chunk thất bại sau khi một delegate đã ghi, lần retry có thể gọi lại writer đó. Cần idempotency key, unique constraint, outbox hoặc quy trình reconciliation để tránh duplicate.

Với file writer, Spring Batch có cơ chế state và transaction-aware behavior tùy implementation/configuration, nhưng không coi nhiều file output như một distributed transaction. Kiểm thử rollback/restart với đúng writer và storage thực tế.

## 14. Exception từ delegate writer

Nếu writer được chọn ném exception, exception truyền ra khỏi ClassifierCompositeItemWriter.write. Step có thể áp dụng retry, skip hoặc fail policy:

~~~java
return new StepBuilder("routePaymentsStep", jobRepository)
        .<PaymentInput, Payment>chunk(100, transactionManager)
        .reader(paymentReader)
        .processor(paymentProcessor)
        .writer(paymentWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidPaymentException.class)
        .skipLimit(10)
        .build();
~~~

Chỉ cấu hình retry cho lỗi thực sự tạm thời và có thể lặp an toàn. Nếu writer đã gửi message hoặc ghi ra hệ thống ngoài trước khi lỗi, retry có thể tạo bản ghi trùng.

Nếu một route gặp lỗi dữ liệu riêng của item, có thể dùng exception chuyên biệt và skip policy nếu nghiệp vụ cho phép. Nếu route bị thiếu writer hoặc classifier có bug, thường nên fail job thay vì skip vì đó là lỗi cấu hình/chương trình.

## 15. Không dùng classifier writer để filter

Classifier writer chỉ chọn đích ghi. Nó không thay thế ItemProcessor và không có contract trả null để filter item.

Nếu item không cần ghi, hãy filter trong processor:

~~~java
public class EligiblePaymentProcessor
        implements ItemProcessor<PaymentInput, Payment> {

    @Override
    public Payment process(PaymentInput input) {
        if (!input.eligible()) {
            return null;
        }
        return toPayment(input);
    }
}
~~~

Nếu item hợp lệ nhưng chưa biết route, đó là vấn đề phân loại. Hãy route tới reject writer hoặc ném exception có ngữ cảnh. Không trả về một writer rỗng để âm thầm bỏ dữ liệu trừ khi đó là hành vi nghiệp vụ được ghi nhận rõ.

## 16. Phân loại theo dữ liệu cấu hình

Có thể classifier cần dựa trên cấu hình job như tenant hoặc export mode. Hãy inject một classifier được cấu hình cho JobExecution hoặc dùng factory tạo classifier phù hợp. Không thay đổi mutable field của singleton classifier trong khi job đang chạy.

Ví dụ dùng enum route đã được chuẩn hóa ở processor:

~~~java
public enum ExportRoute {
    CARD,
    BANK,
    REVIEW
}

public record PaymentExport(
        String paymentId,
        ExportRoute route,
        BigDecimal amount) {
}
~~~

Processor quyết định route dựa trên rule nghiệp vụ và tạo PaymentExport. Classifier writer chỉ đọc route() và chọn writer. Cách phân chia này giúp logic nghiệp vụ không bị trộn vào cơ chế I/O.

Nếu route phụ thuộc JobParameters, đảm bảo giá trị đó được cố định cho JobInstance và giữ nguyên khi restart. Với partitioning, mỗi worker có thể có route/resource riêng theo StepExecutionContext; cần dùng writer step-scoped hoặc cấu hình worker phù hợp.

## 17. Hiệu năng và batching

Trong triển khai chuẩn, composite phân loại và dispatch từng item. Một chunk 100 item có thể dẫn tới nhiều lời gọi write trên các delegate; nếu 100 item đều cùng route, writer đó vẫn có thể được gọi 100 lần với chunk singleton.

Điều này có thể làm giảm lợi ích batch của JdbcBatchItemWriter, writer gửi HTTP batch hoặc writer có chi phí khởi tạo mỗi lần gọi.

Các lựa chọn:

- Dùng classifier writer khi routing đơn giản và chi phí từng lần ghi chấp nhận được.
- Nếu cần batching theo destination, viết một ItemWriter<T> tùy chỉnh để nhóm item theo route rồi gọi mỗi delegate một lần với chunk tương ứng.
- Nếu mỗi route có query khác nhau nhưng cùng database, cân nhắc một writer tùy chỉnh gom nhóm theo SQL/statement.
- Đo số lần delegate write, số round trip, latency và throughput trên dữ liệu đại diện.

Ví dụ ý tưởng gom nhóm:

~~~java
Map<ExportRoute, List<PaymentExport>> groups =
        items.getItems().stream()
                .collect(Collectors.groupingBy(PaymentExport::route));

List<PaymentExport> cardItems =
        groups.getOrDefault(ExportRoute.CARD, List.of());
if (!cardItems.isEmpty()) {
    cardWriter.write(new Chunk<>(cardItems));
}

List<PaymentExport> bankItems =
        groups.getOrDefault(ExportRoute.BANK, List.of());
if (!bankItems.isEmpty()) {
    bankWriter.write(new Chunk<>(bankItems));
}
~~~

Đây là phác thảo cho custom grouped writer, không phải cấu hình của ClassifierCompositeItemWriter. Trong triển khai thật, cần xử lý route không hỗ trợ, giữ thứ tự nếu nghiệp vụ yêu cầu và đăng ký lifecycle cho mọi ItemStream delegate.

## 18. Thread safety và multi-threaded step

ClassifierCompositeItemWriter và các delegate cần được xem xét khi step có nhiều thread. Nếu nhiều chunk được ghi đồng thời, cùng classifier writer hoặc delegate writer có thể được gọi từ nhiều thread.

Hãy kiểm tra:

- Classifier có stateless/thread-safe không?
- Delegate writer có hỗ trợ concurrent writes không?
- Hai thread có thể ghi vào cùng file/resource không?
- Writer có mutable buffer hoặc statement dùng chung không?
- Database connection/transaction có được lấy theo thread đúng cách không?
- Routing rule có thay đổi trong khi step đang chạy không?

Ưu tiên classifier bất biến và delegate writer thread-safe. Với file output, thường dễ kiểm soát hơn nếu mỗi partition/worker có resource riêng. Nếu buộc phải serialize một writer, dùng cơ chế đồng bộ rõ ràng và đo tác động throughput; không giả định composite tự khóa các delegate.

Với partitioning, mỗi worker step có thể tạo writer riêng bằng StepScope và nhận resource path/route qua StepExecutionContext. Tránh để nhiều worker cùng mở một file output nếu writer không được thiết kế cho concurrent append.

## 19. Adapter cho writer khác kiểu dữ liệu

Như đã nêu, classifier của ClassifierCompositeItemWriter<T> phải trả về writer có thể nhận T hoặc kiểu cha của T. Nếu cần ghi các subtype bằng writer có generic riêng, tạo adapter với kiểu nhận chung.

Ví dụ:

~~~java
public class OrderRecordWriter implements ItemWriter<ImportRecord> {

    private final ItemWriter<OrderRecord> delegate;

    public OrderRecordWriter(ItemWriter<OrderRecord> delegate) {
        this.delegate = delegate;
    }

    @Override
    public void write(Chunk<? extends ImportRecord> items)
            throws Exception {
        for (ImportRecord item : items) {
            if (!(item instanceof OrderRecord order)) {
                throw new IllegalArgumentException(
                        "Expected OrderRecord");
            }
            delegate.write(Chunk.of(order));
        }
    }
}
~~~

Adapter kiểm tra loại item và chuyển nó cho writer chuyên biệt. Nếu adapter delegate triển khai ItemStream, hãy bảo đảm lifecycle được chuyển tiếp hoặc đăng ký delegate gốc với step. Không dùng unchecked cast mà không kiểm tra subtype.

## 20. So sánh với ClassifierCompositeItemProcessor

Hai class có tên gần giống nhưng hoạt động ở hai giai đoạn khác nhau:

| Thành phần | Vị trí | Nhiệm vụ |
|---|---|---|
| ClassifierCompositeItemProcessor | Processor stage | Chọn processor để biến đổi item |
| ClassifierCompositeItemWriter | Writer stage | Chọn writer để ghi item đã xử lý |

Ví dụ:

- Nếu PaymentInput CARD cần được chuyển đổi theo một rule riêng và BANK_TRANSFER cần một rule khác, dùng classifier processor.
- Nếu cả hai đã được chuẩn hóa thành Payment nhưng phải ghi vào bảng/file khác nhau, dùng classifier writer.
- Nếu cần cả hai hành vi, có thể dùng classifier processor trước rồi classifier writer sau.

Không đưa logic mapping phức tạp vào classifier writer. Writer stage nên nhận item đã sẵn sàng để ghi.

## 21. Kiểm thử classifier và delegate

Nên kiểm thử classifier riêng và composite writer ở cấp unit:

1. Item thuộc route A chọn đúng writer A.
2. Item thuộc route B chọn đúng writer B.
3. Mỗi item chỉ được gửi tới một writer.
4. Nhiều item trong cùng chunk có thể đi tới nhiều writer.
5. Route không hỗ trợ được xử lý theo default/reject/fail policy.
6. Classifier không trả null.
7. Writer delegate nhận đúng item và đúng thứ tự cần thiết.
8. Delegate exception được truyền ra.
9. Stream delegates được mở, cập nhật và đóng khi step chạy.
10. Concurrent write không làm hỏng state hoặc output.
11. Retry/restart không tạo duplicate ngoài dự kiến.
12. Số lần gọi delegate phù hợp với hiệu năng được mong đợi.

Ví dụ unit test kiểm tra routing:

~~~java
@Test
void routesCardPaymentToCardWriter() throws Exception {
    ItemWriter<Payment> cardWriter = mock(ItemWriter.class);
    ItemWriter<Payment> bankWriter = mock(ItemWriter.class);

    Classifier<Payment, ItemWriter<? super Payment>> classifier =
            payment -> payment.method() == PaymentMethod.CARD
                    ? cardWriter : bankWriter;

    ClassifierCompositeItemWriter<Payment> writer =
            new ClassifierCompositeItemWriter<>();
    writer.setClassifier(classifier);

    Payment payment = new Payment(
            "PAY-1", PaymentMethod.CARD, new BigDecimal("10.00"));

    writer.write(Chunk.of(payment));

    verify(cardWriter).write(Chunk.of(payment));
    verifyNoInteractions(bankWriter);
}
~~~

Đoạn test minh họa routing một item; khi viết test thực tế, có thể capture chunk truyền vào delegate để so sánh nội dung thay vì dựa vào equality của đối tượng Chunk.

## 22. Integration test trong step

Integration test nên chạy step với nhiều loại item và các writer có thể quan sát output. Ví dụ input có ba CARD, hai BANK_TRANSFER và một CASH; sau step, xác nhận từng đích nhận đúng số lượng và đúng item.

Các điểm cần xác nhận:

- Job/step hoàn thành khi mọi route hợp lệ.
- Không có item bị ghi vào hai đích nếu classifier chỉ chọn một writer.
- Unknown route làm reject hoặc fail đúng chính sách.
- Delegate ItemStream được mở/đóng và checkpoint đúng.
- Nếu một delegate fail, transaction rollback theo đúng resource/transaction manager.
- Restart khôi phục writer state và không lặp output đã commit.
- File output có header/footer đúng và không bị nhiều worker ghi đè.

Test với database thực tế hoặc Testcontainers khi cần xác nhận transaction, SQL và index. Với file writer, đọc lại file output và parse nội dung thay vì chỉ kiểm tra file tồn tại.

## 23. Những lỗi thường gặp

**Nhầm routing với broadcasting.** Classifier chọn một writer cho mỗi item; dùng CompositeItemWriter nếu cần gửi tới mọi delegate.

**Classifier trả null.** Không có đích ghi và lỗi xảy ra khi dispatch. Trả về reject/default writer hoặc ném exception rõ ràng.

**Delegate writer không tương thích generic.** ItemWriter<Subtype> không thể nhận mọi item của kiểu base. Dùng adapter có kiểm tra kiểu hoặc writer nhận kiểu chung.

**Quên đăng ký ItemStream delegate.** File writer có thể không được mở/đóng hoặc lưu state đúng. Đăng ký từng stream bằng .stream(...).

**Cho rằng một lần write composite đồng nghĩa một lần write delegate.** Dispatch chuẩn thực hiện theo từng item; có thể tạo nhiều lời gọi singleton chunk. Đo và cân nhắc grouped writer nếu cần batching.

**Route thay đổi giữa lần chạy và restart.** Item có thể đi tới output khác với phần đã ghi. Giữ classifier và JobParameters ổn định.

**Nhiều writer cùng ghi một file.** Có thể gây interleaving, overwrite hoặc hỏng file. Dùng resource riêng hoặc writer được thiết kế cho phối hợp.

**Giả định nhiều output cùng rollback nguyên tử.** File/API/database khác nhau có transaction semantics khác nhau. Dùng outbox, staging và reconciliation khi cần.

**Delegate không thread-safe.** Multi-threaded step có thể gọi writer đồng thời. Kiểm tra từng delegate hoặc partition resource riêng.

**Dùng writer để filter item.** Writer có nhiệm vụ ghi. Hãy filter trong processor hoặc ghi reject theo route được thiết kế.

## 24. Quy trình triển khai

Khi xây dựng ClassifierCompositeItemWriter, hãy làm theo trình tự:

1. Xác định kiểu item cuối cùng mà writer nhận.
2. Xác định tiêu chí phân loại ổn định và các route hợp lệ.
3. Tạo delegate writers có thể nhận kiểu item hoặc kiểu cha tương thích.
4. Viết classifier với default/reject/fail behavior rõ ràng.
5. Cấu hình ClassifierCompositeItemWriter và gắn vào step.
6. Đăng ký riêng các delegate triển khai ItemStream.
7. Xác định transaction, restart và idempotency cho từng output resource.
8. Đánh giá số lần gọi writer và khả năng batching theo từng route.
9. Kiểm tra thread safety nếu dùng multi-threading hoặc partitioning.
10. Viết unit test cho routing và integration test cho transaction, lifecycle, restart.

## Kết luận

ClassifierCompositeItemWriter<T> định tuyến từng item tới một ItemWriter được chọn bởi Classifier. Nó phù hợp khi cùng một pipeline cần ghi các nhóm item tới các đích khác nhau. Kiểu writer mà classifier trả về phải nhận được kiểu item T; với writer chuyên biệt cho subtype, cần adapter có kiểm tra kiểu.

Hãy định nghĩa route ổn định, xử lý rõ unknown route, phân biệt routing với broadcasting và nhớ đăng ký các delegate ItemStream với step để chúng được mở, cập nhật và đóng đúng lifecycle. Các lời gọi delegate diễn ra trong write phase của chunk nhưng không bảo đảm mọi loại output có thể rollback nguyên tử. Cần xem xét batching, transaction, restart, idempotency và thread safety cho từng writer. Kiểm thử nhiều route trong cùng chunk, lifecycle, lỗi delegate và restart để bảo đảm dữ liệu đến đúng đích mà không bị mất hoặc ghi trùng.
