# Default classifier

Trong Spring Batch, **Classifier** là một strategy dùng để phân loại một đối tượng đầu vào và chọn một kết quả tương ứng. Kết quả thường là một delegate cần thực hiện công việc tiếp theo, chẳng hạn một ItemWriter hoặc ItemProcessor. Nhờ classifier, một step có thể định tuyến các item đến nhiều nhánh xử lý mà không phải viết nhiều điều kiện rải rác trong writer hoặc processor.

Trong package Spring Classification, **SubclassClassifier** là implementation tổng quát thường dùng khi muốn chọn kết quả dựa trên class của đối tượng. Nó nhận một type map và một default value. Khi class của item khớp với một entry trong map hoặc một kiểu cha được hỗ trợ, classifier trả về delegate đã đăng ký; nếu không tìm thấy mapping, nó trả về default value.

Default value là phần quan trọng của contract. Nó xác định điều gì xảy ra với item không có mapping cụ thể. Nếu không chọn fallback rõ ràng, ứng dụng có thể bỏ sót dữ liệu, ném NullPointerException hoặc route nhầm item. Vì vậy, default classifier cần được cấu hình và kiểm thử như một nhánh nghiệp vụ thực sự.

## 1. Classifier là gì?

Classifier là một abstraction nhỏ có một trách nhiệm: nhận một đối tượng và trả về một kết quả phân loại.

Contract cơ bản:

~~~java
public interface Classifier<C, T> {

    T classify(C classifiable);
}
~~~

Trong đó:

- C là kiểu đối tượng được phân loại.
- T là kiểu kết quả classifier trả về.
- classifiable là đối tượng cần định tuyến.

Ví dụ, classifier nhận một Payment và trả về ItemWriter phù hợp:

~~~text
Payment
   |
   v
Classifier<Payment, ItemWriter<Payment>>
   |
   +---- CashPayment ----> cashWriter
   |
   +---- CardPayment ----> cardWriter
   |
   +---- Unknown type ---> fallbackWriter
~~~

Classifier không tự xử lý dữ liệu và không ghi item. Nó chỉ chọn delegate. Delegate được composite component hoặc code gọi classifier thực thi sau đó.

## 2. Vì sao cần classifier trong Spring Batch?

Một job có thể đọc nhiều loại item từ cùng một nguồn. Tùy loại item, ứng dụng có thể cần:

- Ghi giao dịch tiền mặt vào một bảng.
- Ghi giao dịch thẻ vào một bảng khác.
- Chuyển record lỗi sang error writer.
- Dùng processor khác nhau cho từng subtype.
- Gửi từng nhóm dữ liệu đến một output resource riêng.

Không có classifier, logic routing thường bị nhồi vào một writer lớn với nhiều nhánh if/else. Khi thêm loại item mới, writer chính phải thay đổi và có thể ảnh hưởng các nhánh cũ.

Classifier tách quyết định routing khỏi hành động ghi/transform. Mỗi delegate giữ một trách nhiệm rõ ràng, còn classifier mô tả quy tắc chọn delegate.

## 3. Default classifier trong Spring Classification

Implementation phổ biến cho mapping theo class là **SubclassClassifier<C, T>**. Nó được cấu hình bằng:

- Type map: ánh xạ class sang kết quả tương ứng.
- Default value: kết quả fallback khi không tìm thấy mapping phù hợp.

Ví dụ khái niệm:

~~~java
Map<Class<? extends Payment>, ItemWriter<? super Payment>> typeMap =
        new HashMap<>();

typeMap.put(CashPayment.class, cashPaymentWriter);
typeMap.put(CardPayment.class, cardPaymentWriter);

SubclassClassifier<Payment, ItemWriter<? super Payment>> classifier =
        new SubclassClassifier<>();
classifier.setTypeMap(typeMap);
classifier.setDefaultValue(unsupportedPaymentWriter);
~~~

Đoạn mã thể hiện ý tưởng cấu hình type map và fallback. Các overload/kiểu generic cụ thể cần khớp với phiên bản Spring Batch và Spring Classification mà dự án đang sử dụng.

Khi classifier nhận một item:

1. Lấy class runtime của item.
2. Tìm mapping phù hợp trong type map theo quy tắc class/subclass của implementation.
3. Nếu tìm thấy, trả về giá trị đã ánh xạ.
4. Nếu không tìm thấy, trả về default value.

Default classifier không có nghĩa là Spring Batch tự biết writer mặc định của ứng dụng. Ứng dụng phải cung cấp giá trị fallback có ý nghĩa.

## 4. Default value dùng để làm gì?

Default value xử lý các class chưa được khai báo trong type map. Ví dụ hệ thống hiện hỗ trợ CashPayment và CardPayment, nhưng sau này nguồn có thêm VoucherPayment.

Nếu classifier không có mapping cho VoucherPayment, default value quyết định kết quả:

| Default value | Hành vi |
|---|---|
| UnsupportedPaymentWriter | Ghi record vào output dành cho loại chưa hỗ trợ |
| RejectingPaymentWriter | Ném exception để step thất bại |
| AuditWriter | Lưu business key và loại item để điều tra |
| Null | Không có delegate; caller có thể lỗi khi sử dụng kết quả |

Trong production, fallback nên được chọn theo business contract. Nếu loại item không xác định là dữ liệu không hợp lệ, một reject writer hoặc exception rõ ràng thường an toàn hơn việc âm thầm bỏ qua.

Không dùng một writer mặc định chỉ ghi log rồi trả về thành công nếu downstream cần bảo đảm mọi item đều được xử lý. Khi fallback được sử dụng, nên có metric hoặc audit để biết số lượng item đi vào nhánh đó.

## 5. Mapping theo class và subclass

SubclassClassifier được thiết kế để phân loại dựa trên kiểu của đối tượng. Type map có thể khai báo mapping cho một class cụ thể hoặc một kiểu cha để áp dụng cho các subtype phù hợp theo quy tắc tìm kiếm của implementation.

Ví dụ model:

~~~java
public abstract class Payment {
    private String paymentId;
}

public class CashPayment extends Payment {
    private BigDecimal cashAmount;
}

public class CardPayment extends Payment {
    private String cardReference;
}

public class CorporateCardPayment extends CardPayment {
    private String companyCode;
}
~~~

Nếu map có CashPayment và CardPayment, một CorporateCardPayment có thể sử dụng mapping của kiểu cha CardPayment theo cơ chế subclass lookup. Điều này giúp tránh phải đăng ký từng subtype nếu chúng thực sự có cùng cách xử lý.

Nếu CorporateCardPayment cần writer riêng, đăng ký mapping cụ thể cho class đó. Mapping cụ thể nên được ưu tiên theo đúng lookup semantics của SubclassClassifier version đang dùng.

Không giả định mọi implementation đều duyệt interface giống như duyệt superclass. Nếu domain model dựa nhiều vào interface, hãy xác nhận lookup behavior hoặc dùng classifier tùy chỉnh với quy tắc interface rõ ràng.

## 6. Mapping class cụ thể và mapping kiểu cha

Một type map có thể chứa cả mapping cho subtype và superclass:

~~~java
Map<Class<? extends Payment>, ItemWriter<? super Payment>> typeMap =
        new HashMap<>();

typeMap.put(Payment.class, generalPaymentWriter);
typeMap.put(CardPayment.class, cardPaymentWriter);
typeMap.put(CorporateCardPayment.class, corporateCardWriter);
typeMap.put(CashPayment.class, cashPaymentWriter);
~~~

Mục tiêu là:

- CashPayment dùng cashPaymentWriter.
- CardPayment dùng cardPaymentWriter.
- CorporateCardPayment dùng corporateCardWriter nếu class cụ thể được nhận diện.
- Một subtype khác của Payment có thể dùng generalPaymentWriter nếu lookup đi tới Payment.class.

Thứ tự ưu tiên chính xác phụ thuộc implementation của classifier. Với nhiều tầng kế thừa hoặc mapping phức tạp, hãy viết unit test cho từng runtime class thay vì dựa vào thứ tự khai báo trong Map.

## 7. Không nhầm classifier theo class với classifier theo field

SubclassClassifier phân loại theo class runtime. Nó không tự đọc một field nghiệp vụ như paymentType, region hoặc status.

Ví dụ hai object cùng class PaymentRecord nhưng có field type khác nhau:

~~~java
public class PaymentRecord {
    private String paymentType;
    private BigDecimal amount;
}
~~~

Nếu muốn route theo paymentType, dùng classifier tùy chỉnh:

~~~java
Classifier<PaymentRecord, ItemWriter<? super PaymentRecord>> classifier =
        payment -> switch (payment.getPaymentType()) {
            case "CASH" -> cashWriter;
            case "CARD" -> cardWriter;
            default -> unsupportedWriter;
        };
~~~

Class-based mapping phù hợp khi subtype biểu diễn sự khác nhau về cấu trúc hoặc behavior. Field-based mapping phù hợp khi một kiểu DTO duy nhất chứa discriminator nghiệp vụ.

Đừng tạo nhiều subclass chỉ để thay thế một field discriminator nếu domain model không cần phân biệt kiểu ở mức Java.

## 8. ClassifierCompositeItemWriter

Spring Batch cung cấp **ClassifierCompositeItemWriter<T>** để route item đến writer được classifier chọn. Nó là một ItemWriter có delegate được xác định theo từng item.

Ví dụ:

~~~java
@Bean
public ClassifierCompositeItemWriter<Payment> paymentWriter(
        ItemWriter<Payment> cashPaymentWriter,
        ItemWriter<Payment> cardPaymentWriter,
        ItemWriter<Payment> unsupportedPaymentWriter) {

    Classifier<Payment, ItemWriter<? super Payment>> classifier =
            new SubclassClassifier<>(
                    Map.of(
                            CashPayment.class, cashPaymentWriter,
                            CardPayment.class, cardPaymentWriter),
                    unsupportedPaymentWriter);

    return new ClassifierCompositeItemWriterBuilder<Payment>()
            .classifier(classifier)
            .build();
}
~~~

Ví dụ minh họa cách kết hợp classifier với writer composite. Cần điều chỉnh generic type và constructor theo API version cụ thể; một số phiên bản có thể cấu hình SubclassClassifier qua setter thay vì constructor.

Composite writer nhận chunk từ step, classifier chọn delegate cho từng item và delegate writer thực hiện ghi. Cần đăng ký các delegate có lifecycle/state phù hợp nếu chúng là ItemStream. Khi dùng writer có state, bảo đảm Spring Batch mở, cập nhật và đóng đúng các stream bên trong composite theo cách cấu hình của ứng dụng.

## 9. Routing theo loại item trong cùng chunk

Một chunk có thể chứa nhiều subtype:

~~~text
Chunk:
  CashPayment
  CardPayment
  CashPayment
  CorporateCardPayment
  UnknownPayment
~~~

Classifier xác định writer cho từng item. Do đó, một chunk có thể được phân phối đến nhiều delegate. Cần hiểu transaction boundary và hành vi delegate:

- Các writer dùng cùng transaction manager/resource có thể tham gia transaction của chunk.
- Một delegate ghi file hoặc gọi API có thể không rollback cùng database.
- Một delegate ném exception có thể làm chunk thất bại.
- Retry chunk có thể gọi lại delegate đã thực hiện side effect.

Không giả định routing nhiều writer tự tạo ra một distributed transaction. Nếu các delegate ghi vào các resource khác nhau, hãy thiết kế idempotency, staging hoặc outbox theo từng resource.

## 10. Default classifier trong cấu hình Spring

Có thể khai báo SubclassClassifier như một bean để tái sử dụng:

~~~java
@Bean
public Classifier<Payment, ItemWriter<? super Payment>> paymentClassifier(
        ItemWriter<Payment> cashPaymentWriter,
        ItemWriter<Payment> cardPaymentWriter,
        ItemWriter<Payment> unsupportedPaymentWriter) {

    Map<Class<? extends Payment>, ItemWriter<? super Payment>> routes =
            new HashMap<>();
    routes.put(CashPayment.class, cashPaymentWriter);
    routes.put(CardPayment.class, cardPaymentWriter);

    SubclassClassifier<Payment, ItemWriter<? super Payment>> classifier =
            new SubclassClassifier<>();
    classifier.setTypeMap(routes);
    classifier.setDefaultValue(unsupportedPaymentWriter);
    return classifier;
}
~~~

Sau đó inject classifier vào composite writer:

~~~java
@Bean
public ClassifierCompositeItemWriter<Payment> paymentCompositeWriter(
        Classifier<Payment, ItemWriter<? super Payment>> paymentClassifier) {

    return new ClassifierCompositeItemWriterBuilder<Payment>()
            .classifier(paymentClassifier)
            .build();
}
~~~

Bean classifier chỉ chứa routing rule. Delegate writer nên được cấu hình riêng để mỗi writer có name, resource, SQL và lifecycle phù hợp.

Nếu classifier có state mutable hoặc type map thay đổi trong runtime, nhiều step có thể nhìn thấy routing rule khác nhau trong cùng một job. Thông thường nên cấu hình map bất biến trước khi step chạy và không sửa nó trong lúc processing.

## 11. Cấu hình composite writer trong step

Composite writer có thể được gắn như writer bình thường:

~~~java
@Bean
public Step routePaymentsStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Payment> paymentReader,
        ItemProcessor<Payment, Payment> paymentProcessor,
        ClassifierCompositeItemWriter<Payment> paymentCompositeWriter) {

    return new StepBuilder("routePaymentsStep", jobRepository)
            .<Payment, Payment>chunk(100, transactionManager)
            .reader(paymentReader)
            .processor(paymentProcessor)
            .writer(paymentCompositeWriter)
            .build();
}
~~~

Từ góc nhìn step, chỉ có một writer là composite. Việc chọn writer cụ thể được thực hiện bên trong composite thông qua classifier.

Nếu delegate writer cần mở resource hoặc lưu state, hãy bảo đảm composite/step nhận biết stream đó. Không phải mọi wrapper tùy chỉnh đều tự động forward ItemStream lifecycle. Kiểm tra contract của component và đăng ký delegate đúng cách.

## 12. ClassifierCompositeItemProcessor

Spring Batch cũng có **ClassifierCompositeItemProcessor<I, O>** để chọn processor theo item đầu vào. Đây là cách dùng classifier khi các loại item cần transformation khác nhau:

~~~text
Input item
   |
   v
Classifier
   |
   +---- CashPayment ----> CashPaymentProcessor
   |
   +---- CardPayment ----> CardPaymentProcessor
   |
   +---- Other ----------> UnsupportedPaymentProcessor
~~~

Ví dụ khái niệm:

~~~java
Classifier<Payment, ItemProcessor<?, ?>> processorClassifier =
        payment -> {
            if (payment instanceof CashPayment) {
                return cashPaymentProcessor;
            }
            if (payment instanceof CardPayment) {
                return cardPaymentProcessor;
            }
            return unsupportedPaymentProcessor;
        };

ClassifierCompositeItemProcessor<Payment, PaymentResult> processor =
        new ClassifierCompositeItemProcessorBuilder<Payment, PaymentResult>()
                .classifier(processorClassifier)
                .build();
~~~

Các processor delegate cần có input/output type tương thích với kiểu generic mà composite công bố. Vì classifier chọn processor ở runtime, compiler không thể chứng minh mọi nhánh đều trả đúng kiểu output. Hãy thiết kế một output type chung hoặc dùng adapter rõ ràng cho từng subtype.

Nếu mỗi processor trả về kiểu kết quả hoàn toàn khác nhau, có thể dùng sealed result type, common interface hoặc một DTO envelope để writer xử lý nhất quán.

## 13. Default processor khi không có mapping

Default value của processor classifier có thể là processor chuyên xử lý subtype chưa hỗ trợ:

- Trả về một result mang trạng thái UNSUPPORTED để error writer xử lý sau.
- Ném UnsupportedPaymentTypeException để step fail.
- Chuẩn hóa item vào một common fallback DTO nếu nghiệp vụ cho phép.

Không nên để fallback processor trả null nếu điều đó khiến item biến mất mà không có audit. Null từ ItemProcessor có nghĩa filter; nếu item không được hỗ trợ là lỗi, hãy biểu diễn lỗi bằng exception hoặc output error rõ ràng.

## 14. Classifier không thay thế ItemProcessor

Classifier quyết định delegate; processor thực hiện transformation.

| Thành phần | Trách nhiệm |
|---|---|
| Classifier | Chọn nhánh/delegate dựa trên item |
| ItemProcessor | Validate, transform hoặc filter item |
| ClassifierCompositeItemProcessor | Dùng classifier để chọn processor |
| ItemWriter | Ghi item |
| ClassifierCompositeItemWriter | Dùng classifier để chọn writer |

Nếu logic chọn nhánh đang thực hiện luôn cả mapping dữ liệu, việc phân tách sẽ khó kiểm thử. Giữ classifier nhỏ để routing có thể được test độc lập với business transformation.

## 15. Classifier theo exception type

Classifier cũng có thể nhận Throwable và trả về một policy hoặc kết quả tương ứng. Đây là ý tưởng được dùng trong một số cơ chế retry/exception handling của Spring.

Ví dụ, một classifier có thể phân loại:

- Timeout thành retryable.
- Validation exception thành skippable.
- Configuration exception thành fatal.

Tuy nhiên, việc phân loại exception không tự cấu hình retry hoặc skip. Step vẫn cần RetryPolicy, SkipPolicy hoặc fault-tolerant configuration tương ứng.

Không nhầm SubclassClassifier dùng để chọn delegate với một exception classifier chuyên biệt. Cùng abstraction Classifier có thể phân loại nhiều loại đầu vào và trả nhiều loại kết quả khác nhau.

## 16. Khi nào dùng SubclassClassifier?

SubclassClassifier phù hợp khi:

- Các subtype Java biểu diễn các loại item cần xử lý khác nhau.
- Mapping class sang delegate khá tĩnh.
- Có một fallback chung cho subtype chưa đăng ký.
- Quy tắc dựa trên class hierarchy đủ để quyết định routing.

Ví dụ:

- Payment subtype sang writer.
- Event subtype sang processor.
- Command class sang handler.
- Exception class sang policy/result.

Nó ít phù hợp khi:

- Routing phụ thuộc nhiều field cùng lúc.
- Quy tắc thay đổi theo job parameter hoặc dữ liệu runtime.
- Cần tra cứu database để quyết định delegate.
- Cần xử lý interface hierarchy phức tạp mà lookup mặc định không đáp ứng.
- Cần routing theo tenant, region, thời gian hoặc trạng thái nghiệp vụ.

Trong các trường hợp đó, custom Classifier thường rõ ràng hơn. Hãy giữ logic lookup bên ngoài writer/processor và bảo đảm classifier có thể unit test độc lập.

## 17. Default value nên fail fast hay route sang fallback?

Quyết định phụ thuộc vào ý nghĩa của item không được nhận diện:

| Tình huống | Default phù hợp |
|---|---|
| Subtype mới là dữ liệu không hợp lệ theo contract | Reject writer hoặc exception |
| Subtype mới được phép lưu để xử lý sau | Quarantine/error writer |
| Mọi subtype có thể dùng cùng cách ghi chung | General writer |
| Không thể xác định business meaning | Fail fast |
| Unknown type được chấp nhận nhưng cần theo dõi | Audit/fallback writer có metric |

Fail fast hữu ích khi routing sai có thể làm sai dữ liệu. Fallback hữu ích khi hệ thống cần tiếp nhận và cách ly dữ liệu mới mà không làm mất dấu. Không có một default value đúng cho mọi job; nó phải phản ánh hợp đồng tích hợp.

## 18. Không để default writer âm thầm bỏ item

Một default writer rỗng:

~~~java
ItemWriter<Payment> discardWriter = chunk -> {
    // Không ghi gì.
};
~~~

chỉ phù hợp nếu bỏ item là hành vi được nghiệp vụ cho phép và có audit/metric riêng. Nếu dùng nó để tránh exception, job có thể báo COMPLETED trong khi dữ liệu bị mất.

Một fallback an toàn hơn có thể ghi vào bảng quarantine:

~~~java
public class UnsupportedPaymentWriter implements ItemWriter<Payment> {

    private final JdbcTemplate jdbcTemplate;

    @Override
    public void write(Chunk<? extends Payment> chunk) {
        for (Payment payment : chunk) {
            jdbcTemplate.update("""
                    insert into unsupported_payment(payment_id, java_type)
                    values (?, ?)
                    """,
                    payment.getPaymentId(),
                    payment.getClass().getName());
        }
    }
}
~~~

Đây là ví dụ minh họa. Quarantine write phải tham gia transaction phù hợp và không ghi payload nhạy cảm không cần thiết. Nếu fallback writer không ghi được, nó nên ném exception để step không báo thành công giả.

## 19. Xử lý null input

Không phải classifier nào cũng có cùng behavior khi input null. SubclassClassifier có thể trả default value hoặc có behavior riêng theo implementation/version. Custom classifier có thể ném NullPointerException nếu gọi getClass hoặc truy cập field mà không kiểm tra null.

Trong chunk processing thông thường, ItemReader dùng null để báo EOF nên processor/writer không nhận null như một item. Tuy nhiên, classifier có thể được dùng ở nơi khác, hoặc được gọi trực tiếp trong unit test.

Hãy quy định null behavior:

- Null không phải item hợp lệ: fail fast bằng exception rõ ràng.
- Null là một trạng thái có ý nghĩa: định nghĩa một nhánh riêng.
- Null chỉ được phép theo contract của framework: không truyền nó vào classifier như item.

Không dùng default writer để xử lý null ngoài ý muốn nếu điều đó làm che giấu lỗi upstream.

## 20. Type map nên được cấu hình bất biến

Type map thường được tạo lúc khởi tạo application context. Sau khi step bắt đầu, không nên thay đổi mapping:

~~~java
Map<Class<? extends Payment>, ItemWriter<? super Payment>> routes =
        Map.of(
                CashPayment.class, cashPaymentWriter,
                CardPayment.class, cardPaymentWriter);
~~~

Map bất biến giúp routing nhất quán trong suốt job execution và tránh race condition giữa các thread.

Nếu cần thay đổi routing theo job parameter, hãy tạo classifier/step-scoped component với cấu hình được xác định trước khi execution bắt đầu. Không sửa một singleton classifier đang được nhiều job sử dụng.

## 21. Thread safety của classifier và delegate

Classifier thường chỉ đọc type map và trả về delegate nên có thể được chia sẻ nếu nó không giữ mutable state. Nhưng delegate writer/processor có thể không thread-safe.

Cần phân biệt:

- Thread safety của classifier.
- Thread safety của từng delegate.
- Thread safety của composite component.
- Transaction/resource isolation giữa các thread.

Nếu nhiều partition dùng chung một classifier, mapping nên bất biến. Các writer delegate phải có state/resource riêng hoặc được thiết kế rõ ràng để dùng đồng thời. Không để hai partition ghi vào cùng một file hoặc cùng một mutable writer instance nếu component không hỗ trợ.

## 22. Classifier và transaction boundary

Classifier không tạo transaction mới. Khi composite writer được gọi trong chunk, delegate được chọn thường thực hiện công việc trong transaction context hiện tại nếu resource tham gia transaction đó.

Nếu một chunk route item đến hai JDBC writer:

- Cả hai có thể tham gia cùng transaction nếu dùng cùng transaction manager/resource.
- Exception từ một writer có thể làm rollback chunk.
- Nếu một writer đã gửi API request hoặc ghi file, side effect đó không tự rollback.
- Retry chunk có thể route lại item và gọi delegate một lần nữa.

Do đó, classifier routing không giải quyết vấn đề atomicity giữa nhiều resource. Hãy thiết kế delegate idempotent và tách external side effect qua outbox hoặc bước publish phù hợp.

## 23. Thứ tự gọi delegate và lỗi giữa các nhánh

Khi một chunk chứa nhiều loại item, composite có thể gọi các delegate theo cách triển khai của framework. Không dựa vào thứ tự gọi writer nếu business correctness yêu cầu một nhánh phải hoàn tất trước nhánh khác.

Nếu có dependency giữa hai nhánh, hãy mô hình hóa bằng step/flow riêng hoặc một writer có orchestration rõ ràng. Nếu thứ tự chỉ phục vụ performance, kiểm tra implementation/version và viết integration test cho hành vi cần dựa vào.

Một delegate có thể ghi thành công rồi delegate tiếp theo thất bại. Nếu hai writer không dùng chung transaction, output đầu tiên có thể đã commit. Retry có thể gọi lại writer đầu; idempotency là cần thiết.

## 24. Composite writer và ItemStream delegate

Một số delegate writer triển khai ItemStream để quản lý file hoặc checkpoint. Khi bọc chúng trong composite, phải bảo đảm lifecycle được truyền đúng:

- open được gọi trước khi write.
- update được gọi để lưu state.
- close được gọi khi step kết thúc.
- Delegate được mở đúng resource.
- State key của các delegate không xung đột.

Nếu composite không tự quản lý stream của delegate theo cấu hình/version đang dùng, có thể cần đăng ký delegate như stream của step hoặc dùng một wrapper hỗ trợ ItemStream. Kiểm tra API thực tế thay vì giả định mọi object được tham chiếu trong classifier sẽ tự động được quản lý lifecycle.

Đặc biệt với writer ghi file, thiếu close có thể làm mất buffer hoặc file chưa hoàn chỉnh. Với writer restartable, thiếu update có thể làm mất checkpoint riêng của delegate.

## 25. Mapping class trong package/module khác

Trong ứng dụng lớn, subtype có thể được định nghĩa trong module riêng. Classifier cần biết các class đó để đăng ký mapping. Cần tránh cấu hình phụ thuộc vòng:

- Module domain định nghĩa Payment và subtype.
- Module batch định nghĩa classifier/routing.
- Module infrastructure cung cấp writer delegate.

Đặt mapping ở module composition/configuration nơi có thể nhìn thấy cả domain type lẫn delegate. Không để domain model phụ thuộc trực tiếp vào Spring Batch writer.

Nếu plugin/module mới có thể được thêm động, SubclassClassifier với map tĩnh có thể không đủ. Khi đó cần registry có lifecycle và quy tắc cập nhật rõ ràng, nhưng registry phải được đóng băng cho từng job execution để restart deterministic.

## 26. Unit test cho SubclassClassifier

Classifier nên được test độc lập với Spring Batch step:

~~~java
class PaymentClassifierTest {

    private final ItemWriter<Payment> cashWriter = chunk -> {};
    private final ItemWriter<Payment> cardWriter = chunk -> {};
    private final ItemWriter<Payment> fallbackWriter = chunk -> {};

    private SubclassClassifier<Payment, ItemWriter<? super Payment>> classifier;

    @BeforeEach
    void setUp() {
        Map<Class<? extends Payment>, ItemWriter<? super Payment>> routes =
                new HashMap<>();
        routes.put(CashPayment.class, cashWriter);
        routes.put(CardPayment.class, cardWriter);

        classifier = new SubclassClassifier<>();
        classifier.setTypeMap(routes);
        classifier.setDefaultValue(fallbackWriter);
    }

    @Test
    void selectsWriterForExactClass() {
        assertSame(cashWriter, classifier.classify(new CashPayment()));
        assertSame(cardWriter, classifier.classify(new CardPayment()));
    }

    @Test
    void selectsDefaultForUnknownClass() {
        assertSame(fallbackWriter,
                classifier.classify(new VoucherPayment()));
    }
}
~~~

Các class và constructor trong ví dụ là model minh họa. Test thực tế nên bao gồm exact class, subclass, superclass mapping, unknown type và null behavior theo implementation/version.

Dùng assertSame khi mục tiêu là xác nhận classifier trả đúng delegate instance đã đăng ký. Dùng assertEquals nếu kết quả là một value object thay vì collaborator.

## 27. Test mapping với superclass và subtype cụ thể

Khi type map có nhiều tầng, hãy kiểm tra rõ:

| Runtime type | Mapping dự kiến |
|---|---|
| CashPayment | cash writer |
| CardPayment | card writer |
| CorporateCardPayment | corporate writer nếu đăng ký cụ thể; nếu không thì card writer theo superclass lookup |
| VoucherPayment | default writer |

Test này bảo vệ behavior khi domain thêm subtype mới. Nếu một subtype mới vô tình đi vào general writer, test sẽ phát hiện trước khi dữ liệu production được route sai.

Đối với interface, hãy viết test riêng nếu ứng dụng kỳ vọng mapping interface được áp dụng. Nếu implementation không tìm interface theo contract cần thiết, dùng custom classifier để xác định rõ ưu tiên giữa exact class, superclass và interface.

## 28. Test default value và unknown type

Default branch cần được kiểm tra như một nhánh quan trọng:

- Class chưa được đăng ký có nhận đúng fallback không?
- Fallback có ghi được business key và loại runtime không?
- Fallback có ném exception nếu dữ liệu không thể chấp nhận không?
- Metric/audit có tăng khi nhánh fallback được gọi không?
- Một subtype mới có bị route nhầm vào writer mặc định không?

Nếu default value là writer quarantine, integration test cần xác nhận item xuất hiện trong quarantine output và không xuất hiện trong bảng/file của nhánh hợp lệ.

Nếu default value là rejecting writer, xác nhận step thất bại với exception có thể chẩn đoán và transaction rollback theo mong đợi.

## 29. Integration test ClassifierCompositeItemWriter

Unit test classifier không chứng minh composite gọi delegate đúng cách. Một integration test có thể:

1. Tạo hai hoặc ba writer test double, mỗi writer ghi nhận business key đã nhận.
2. Cấu hình SubclassClassifier với type map và default writer.
3. Tạo ClassifierCompositeItemWriter.
4. Gửi một chunk chứa nhiều subtype.
5. Xác nhận mỗi item đến đúng writer.
6. Xác nhận unknown subtype đi vào default branch.
7. Xác nhận exception từ delegate được truyền lên và step không báo thành công giả.

Nếu cần kiểm tra số lần gọi write hoặc nhóm item trong từng lần gọi, hãy assert riêng theo API/version. Contract quan trọng nhất là item được route đúng và delegate failure được xử lý đúng.

## 30. Test composite processor

Với ClassifierCompositeItemProcessor, test:

- Mỗi subtype chọn đúng processor.
- Output của các processor tương thích với output type chung.
- Processor fallback xử lý unknown type đúng contract.
- Processor trả null chỉ khi chủ đích filter.
- Exception từ delegate được truyền lên để fault-tolerant policy xử lý.

Một test cho từng delegate giúp phân biệt lỗi classifier với lỗi business transformation. Nếu chỉ test toàn bộ job, khi output sai sẽ khó biết routing hay processor gây lỗi.

## 31. Kiểm tra routing theo business discriminator

Nếu custom classifier dựa trên field, cần test cả giá trị hợp lệ và không hợp lệ:

~~~java
Classifier<PaymentRecord, ItemWriter<? super PaymentRecord>> classifier =
        record -> switch (record.getPaymentType()) {
            case "CASH" -> cashWriter;
            case "CARD" -> cardWriter;
            case "VOUCHER" -> voucherWriter;
            default -> unsupportedWriter;
        };
~~~

Các trường hợp nên kiểm tra:

- paymentType là CASH.
- paymentType là CARD.
- paymentType là VOUCHER.
- paymentType null.
- paymentType rỗng.
- Giá trị viết thường hoặc không đúng casing nếu contract yêu cầu chuẩn hóa.
- Giá trị mới chưa được hỗ trợ.

Đừng tự động uppercase/trim nếu điều đó làm thay đổi contract. Nếu normalize là quy tắc nghiệp vụ, đặt nó trong một bước validation/normalization rõ ràng và test riêng.

## 32. Cấu hình mapping theo JobParameters

Một số job cần routing khác nhau theo tenant, region hoặc output version. Có thể tạo classifier theo job parameters, nhưng phải bảo đảm:

- Mapping được resolve trước khi step xử lý item.
- Một JobInstance restart nhận lại cùng routing configuration.
- Các delegate/resource có identity riêng theo output key.
- Không sửa mapping trong lúc step đang chạy.
- Cấu hình được validate trước khi mở resource.

Nếu cùng JobInstance restart với routing map khác, item đã commit trước đó có thể đã đi vào delegate khác với item sau restart. Hãy lưu routing version hoặc identifying parameter để xác nhận cấu hình không đổi.

## 33. Classifier và partitioning

Classifier routing item trong một step khác với partitioning:

- Classifier chọn delegate cho từng item trong chunk.
- Partitioning chia workload thành các execution/partition riêng, thường theo key range hoặc resource.

Nếu mục tiêu là chạy song song theo tenant hoặc shard, partitioning thường phù hợp hơn việc route nhiều item qua writer khác nhau trong cùng thread.

Có thể kết hợp hai cơ chế, nhưng cần kiểm soát writer instance, transaction và output resource cho từng partition. Không để nhiều partition cùng ghi vào một delegate mutable hoặc một file nếu không có synchronization/partition-specific resource.

## 34. Hiệu năng của classifier

Classifier theo class thường có chi phí nhỏ so với I/O của writer. Tuy nhiên, routing phức tạp có thể ảnh hưởng throughput:

- Tránh reflection hoặc tra cứu database cho mỗi item nếu có thể.
- Giữ type map bất biến và lookup đơn giản.
- Không log mỗi lần classify ở mức INFO trong job lớn.
- Dùng metric đếm theo nhánh thay vì log từng item.
- Nếu cần nhóm item theo delegate để giảm số lần write, xác nhận composite implementation có hành vi đó; không tự giả định.

Với custom classifier dựa trên nhiều field, tính toán discriminator một lần trong processor nếu nó tốn kém và lưu kết quả trong output DTO khi phù hợp.

## 35. Logging và observability cho default branch

Fallback branch thường là nơi phát hiện subtype mới hoặc dữ liệu không đúng contract. Nên theo dõi:

- Số item được route vào từng delegate.
- Số item đi vào default branch.
- Runtime class hoặc discriminator chưa hỗ trợ.
- Job/step execution identity.
- Business key cần điều tra.
- Số exception từ mỗi delegate.

Không log toàn bộ object nếu có dữ liệu cá nhân hoặc bí mật. Business key và loại runtime thường đủ để tìm record trong nguồn.

Nếu default branch nhận item mới thường xuyên, cân nhắc nâng cấp contract và đăng ký mapping chính thức thay vì để chúng nằm mãi trong fallback.

## 36. Các lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| Unknown subtype gây NullPointerException | Không cấu hình default value hoặc fallback trả null | Đăng ký default delegate không null hoặc fail rõ ràng |
| Subclass đi vào writer không mong muốn | Mapping superclass được áp dụng theo lookup hierarchy | Đăng ký mapping cụ thể và test precedence |
| Interface mapping không có tác dụng | Implementation lookup class hierarchy không xử lý interface như mong đợi | Dùng custom classifier hoặc xác nhận interface behavior |
| Mọi subtype đi vào default | Type map dùng class khác với runtime type hoặc generic mapping sai | Kiểm tra runtime class và map key |
| Field discriminator không được xét | Dùng SubclassClassifier cho routing theo field | Viết custom Classifier theo business field |
| Item biến mất âm thầm | Default writer bỏ qua dữ liệu | Dùng quarantine/reject branch và metric |
| Processor fallback filter item ngoài ý muốn | Trả null cho loại không hỗ trợ | Ném exception hoặc tạo error result |
| Composite writer ghi một phần rồi lỗi | Delegate khác resource/transaction | Idempotency, staging và integration test |
| Delegate không được mở/đóng | Stream lifecycle không được forward/đăng ký | Quản lý ItemStream delegate rõ ràng |
| Routing thay đổi sau restart | Mapping phụ thuộc runtime config không được version hóa | Giữ routing config ổn định theo JobInstance |
| Nhiều partition ghi cùng resource | Chia sẻ delegate mutable hoặc output path | Tạo writer/resource riêng theo partition |
| Log quá nhiều | Ghi mỗi lần classify ở mức cao | Dùng metric theo nhánh và log có chọn lọc |

## 37. Quy trình xây dựng default classifier

1. **Xác định đầu vào:** phân loại theo runtime class hay business discriminator?
2. **Chọn kết quả:** writer, processor, policy hoặc handler nào được trả về?
3. **Tạo type map:** khai báo mapping cụ thể và mapping superclass cần thiết.
4. **Chọn default value:** fallback, quarantine hoặc reject theo business contract.
5. **Quy định unknown/null behavior:** không để kết quả null ngoài ý muốn.
6. **Giữ mapping ổn định:** cấu hình bất biến trong một JobInstance.
7. **Kết nối composite:** dùng ClassifierCompositeItemWriter hoặc ClassifierCompositeItemProcessor khi phù hợp.
8. **Quản lý delegate lifecycle:** đăng ký ItemStream và resource đúng cách.
9. **Kiểm tra transaction:** xác định các delegate có cùng transaction resource hay không.
10. **Viết unit test:** exact class, subclass, superclass, unknown và fallback.
11. **Viết integration test:** gửi chunk nhiều subtype và xác nhận routing/output.
12. **Theo dõi fallback:** metric, audit và quy trình cập nhật mapping khi có subtype mới.

## 38. Những nguyên tắc cần nhớ

- Classifier nhận một đối tượng và trả về kết quả phân loại; nó không tự ghi hoặc transform item.
- SubclassClassifier là implementation thường dùng để map class/subclass sang delegate.
- Type map xác định mapping cụ thể; default value xác định kết quả khi không tìm thấy mapping.
- Default value phải phản ánh business contract; không để null hoặc writer rỗng âm thầm làm mất dữ liệu.
- SubclassClassifier phân loại theo runtime type, không tự đọc field discriminator.
- Với mapping superclass và subtype cụ thể, hãy test lookup precedence theo version đang dùng.
- Không giả định interface lookup giống superclass lookup.
- ClassifierCompositeItemWriter route item tới writer tương ứng; ClassifierCompositeItemProcessor chọn processor theo item.
- Delegate cần có input/output type tương thích và lifecycle phù hợp.
- Classifier routing không tạo distributed transaction giữa các delegate.
- Giữ type map bất biến và routing deterministic qua restart.
- Test default branch, unknown subtype, null behavior, delegate exception và transaction outcome.
- Dùng metric/audit để phát hiện item đi vào fallback; tránh log payload nhạy cảm.
- Dùng partitioning khi mục tiêu là chia workload song song theo shard/tenant thay vì chỉ chọn writer cho từng item.

Default classifier giúp một job Spring Batch định tuyến các loại item theo một quy tắc tập trung. Khi type map rõ ràng, fallback được chọn có chủ đích và composite delegate được kiểm thử cùng transaction/lifecycle, ứng dụng có thể mở rộng thêm subtype mà vẫn kiểm soát được nơi dữ liệu được xử lý.
