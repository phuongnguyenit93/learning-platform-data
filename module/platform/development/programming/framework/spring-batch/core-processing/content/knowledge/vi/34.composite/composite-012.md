# Kiểm thử từng nhánh composite

Trong Spring Batch, một composite có thể điều phối item qua nhiều processor theo các cách khác nhau. `CompositeItemProcessor` nối các processor thành một chuỗi cố định; còn `ClassifierCompositeItemProcessor` chọn một delegate dựa trên đặc điểm của item. Khi có nhiều nhánh xử lý, chỉ kiểm tra kết quả cuối của một Job là chưa đủ: cần xác nhận từng loại input được định tuyến đến đúng delegate, các nhánh không được chọn không bị gọi, và hành vi lỗi của từng nhánh được xử lý đúng.

Kiểm thử từng nhánh giúp phát hiện các lỗi như classifier phân loại sai, một loại item rơi vào nhánh mặc định ngoài dự kiến, delegate nhận sai kiểu dữ liệu, nhánh trả `null` không đúng ý nghĩa hoặc exception bị che giấu. Nên kết hợp unit test cho classifier/delegate với integration test cho Step để xác nhận routing hoạt động trong pipeline Batch thực tế.

## 1. Phân biệt composite dạng chain và composite dạng branch

Hai kiểu composite thường gặp có hành vi khác nhau:

**Chain processor** dùng `CompositeItemProcessor`: mỗi delegate nhận output của delegate trước và chạy theo thứ tự đã cấu hình.

```text
Input
  |
  v
NormalizeProcessor
  |
  v
EnrichProcessor
  |
  v
ValidateProcessor
  |
  v
Output
```

**Branch processor** dùng `ClassifierCompositeItemProcessor`: classifier chọn một delegate phù hợp với item, rồi delegate đó xử lý item.

```text
                 +--> CardProcessor --------+
                 |                          |
Input --> Classifier                         +--> Result
                 |                          |
                 +--> BankTransferProcessor -+
```

Với chain, kiểm thử tập trung vào thứ tự delegate, kiểu input/output trung gian và hành vi dừng khi có `null` hoặc exception. Với branch, cần kiểm tra từng điều kiện phân loại, đúng delegate được gọi và các delegate khác không được gọi cho cùng item.

Một Job có thể kết hợp cả hai: classifier chọn một nhánh, rồi mỗi nhánh lại dùng một chain riêng. Khi đó, hãy kiểm thử routing và chain như hai trách nhiệm riêng, sau đó xác nhận tích hợp ở cấp Step.

## 2. Xác định các nhánh cần kiểm thử

Trước khi viết test, liệt kê đầu vào có thể xuất hiện và nhánh tương ứng. Ví dụ Job xử lý thanh toán có ba loại:

| Loại input | Delegate được chọn | Kết quả mong đợi |
|---|---|---|
| `CARD` | `cardPaymentProcessor` | Xử lý thanh toán thẻ. |
| `BANK_TRANSFER` | `bankTransferProcessor` | Xử lý chuyển khoản. |
| `WALLET` | `walletProcessor` | Xử lý ví điện tử. |
| Loại không hỗ trợ | Nhánh từ chối/fallback hoặc lỗi rõ ràng | Không âm thầm chọn một processor sai. |

Mỗi nhánh nên có ít nhất một test xác nhận routing thành công. Với nhánh có điều kiện phức tạp, hãy thêm test cho giá trị biên và trường hợp không hợp lệ. Nếu classifier có default branch, phải kiểm tra rõ default branch nhận những input nào.

Đừng chỉ đếm số test. Một test có thể chạy Job thành công nhưng chỉ đi qua nhánh `CARD`; điều đó không chứng minh `BANK_TRANSFER` hay `WALLET` được cấu hình đúng.

## 3. Ví dụ domain và classifier

Giả sử reader trả về `Payment` và processor cần tạo `PaymentResult`:

```java
public enum PaymentMethod {
    CARD,
    BANK_TRANSFER,
    WALLET
}

public record Payment(
        String paymentId,
        PaymentMethod method,
        BigDecimal amount) {
}

public record PaymentResult(
        String paymentId,
        String status,
        String providerReference) {
}
```

Các delegate có cùng input/output type ở ví dụ này để classifier có thể định tuyến một `Payment` đến processor phù hợp:

```java
ItemProcessor<Payment, PaymentResult> cardPaymentProcessor = payment ->
        cardGateway.charge(payment);

ItemProcessor<Payment, PaymentResult> bankTransferProcessor = payment ->
        bankGateway.submit(payment);

ItemProcessor<Payment, PaymentResult> walletProcessor = payment ->
        walletGateway.pay(payment);
```

Trong ứng dụng thật, mỗi delegate có thể gọi service riêng, kiểm tra field riêng hoặc tạo output chuyên biệt. Nếu các nhánh có input model khác nhau, có thể dùng một sealed hierarchy/interface chung và cast có kiểm soát trong delegate, hoặc xây dựng adapter để giữ hợp đồng type an toàn.

Classifier xác định nhánh dựa trên `PaymentMethod`:

```java
Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>>
        paymentClassifier = payment -> switch (payment.method()) {
            case CARD -> cardPaymentProcessor;
            case BANK_TRANSFER -> bankTransferProcessor;
            case WALLET -> walletProcessor;
        };
```

Với enum switch expression đầy đủ, compiler có thể yêu cầu xử lý mọi giá trị enum. Nếu classifier có thể nhận `null`, hoặc discriminator đến từ dữ liệu không được kiểm soát, hãy xác thực trước khi phân loại và định nghĩa rõ hành vi khi không có nhánh phù hợp.

## 4. Cấu hình ClassifierCompositeItemProcessor

`ClassifierCompositeItemProcessor<I, O>` là một `ItemProcessor<I, O>`. Nó dùng một `Classifier` để chọn delegate cho từng input.

Ví dụ cấu hình bằng Java:

```java
@Bean
ItemProcessor<Payment, PaymentResult> paymentProcessor(
        ItemProcessor<Payment, PaymentResult> cardPaymentProcessor,
        ItemProcessor<Payment, PaymentResult> bankTransferProcessor,
        ItemProcessor<Payment, PaymentResult> walletProcessor) {

    ClassifierCompositeItemProcessor<Payment, PaymentResult> composite =
            new ClassifierCompositeItemProcessor<>();

    composite.setClassifier(payment -> switch (payment.method()) {
        case CARD -> cardPaymentProcessor;
        case BANK_TRANSFER -> bankTransferProcessor;
        case WALLET -> walletProcessor;
    });

    return composite;
}
```

Tên class nằm trong package `org.springframework.batch.item.support`; `Classifier` thuộc package `org.springframework.classify`. Composite chọn delegate cho từng item. Nó không gọi lần lượt tất cả processor như `CompositeItemProcessor`.

Nếu dùng nhiều bean cùng kiểu, cần `@Qualifier` để Spring inject đúng delegate. Cấu hình branch nên đọc được như một bảng routing; tránh classifier phụ thuộc vào thứ tự bean được phát hiện ngầm.

## 5. Kiểm thử routing bằng mock delegate

Một unit test cơ bản xác nhận item loại `CARD` được chuyển đến đúng processor:

```java
@Test
void cardPaymentIsRoutedOnlyToCardProcessor() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> cardProcessor =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> bankProcessor =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> walletProcessor =
            mock(ItemProcessor.class);

    Payment payment = new Payment(
            "P-1001", PaymentMethod.CARD, new BigDecimal("250.00"));
    PaymentResult expected = new PaymentResult(
            "P-1001", "APPROVED", "CARD-REF-01");

    when(cardProcessor.process(payment)).thenReturn(expected);

    ClassifierCompositeItemProcessor<Payment, PaymentResult> composite =
            new ClassifierCompositeItemProcessor<>();
    composite.setClassifier(item -> switch (item.method()) {
        case CARD -> cardProcessor;
        case BANK_TRANSFER -> bankProcessor;
        case WALLET -> walletProcessor;
    });

    assertThat(composite.process(payment)).isEqualTo(expected);

    verify(cardProcessor).process(payment);
    verifyNoInteractions(bankProcessor, walletProcessor);
}
```

Test xác nhận ba điều: kết quả được trả về từ nhánh thẻ, `cardProcessor` nhận đúng item, và hai nhánh còn lại không bị gọi. `verifyNoInteractions` đặc biệt hữu ích để phát hiện classifier vô tình gọi nhiều delegate hoặc logic bị đặt nhầm ngoài nhánh.

## 6. Viết test riêng cho từng nhánh

Không nên chỉ kiểm thử nhánh đầu tiên rồi suy luận các nhánh còn lại tương đương. Mỗi nhánh có thể có service, mapping, validation và exception riêng.

Một test cho chuyển khoản:

```java
@Test
void bankTransferIsRoutedToBankProcessor() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> cardProcessor =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> bankProcessor =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> walletProcessor =
            mock(ItemProcessor.class);

    Payment payment = new Payment(
            "P-2001", PaymentMethod.BANK_TRANSFER,
            new BigDecimal("900.00"));
    PaymentResult expected = new PaymentResult(
            "P-2001", "SUBMITTED", "BANK-REF-02");

    when(bankProcessor.process(payment)).thenReturn(expected);

    ClassifierCompositeItemProcessor<Payment, PaymentResult> composite =
            createComposite(cardProcessor, bankProcessor, walletProcessor);

    assertThat(composite.process(payment)).isEqualTo(expected);

    verify(bankProcessor).process(payment);
    verifyNoInteractions(cardProcessor, walletProcessor);
}
```

Để tránh lặp cấu hình trong nhiều test, có thể tạo helper `createComposite(...)` trong test class. Helper chỉ dựng composite với classifier giống production; không nên viết một classifier đơn giản hơn trong test vì như vậy test có thể kiểm tra logic khác với cấu hình thật.

Với nhánh `WALLET`, viết test tương tự và xác nhận `walletProcessor` là delegate duy nhất được gọi. Mỗi nhánh cũng cần test logic nội bộ của delegate, ví dụ mapping mã trạng thái của provider hoặc validation hạn mức.

## 7. Tách classifier thành component để test trực tiếp

Khi quy tắc phân loại phức tạp, nên tách classifier thành class riêng thay vì nhúng toàn bộ logic vào lambda trong bean configuration.

```java
public class PaymentProcessorClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final ItemProcessor<Payment, PaymentResult> cardProcessor;
    private final ItemProcessor<Payment, PaymentResult> bankProcessor;
    private final ItemProcessor<Payment, PaymentResult> walletProcessor;

    public PaymentProcessorClassifier(
            ItemProcessor<Payment, PaymentResult> cardProcessor,
            ItemProcessor<Payment, PaymentResult> bankProcessor,
            ItemProcessor<Payment, PaymentResult> walletProcessor) {
        this.cardProcessor = cardProcessor;
        this.bankProcessor = bankProcessor;
        this.walletProcessor = walletProcessor;
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        if (payment == null || payment.method() == null) {
            throw new IllegalArgumentException("Payment method is required");
        }

        return switch (payment.method()) {
            case CARD -> cardProcessor;
            case BANK_TRANSFER -> bankProcessor;
            case WALLET -> walletProcessor;
        };
    }
}
```

Classifier riêng có thể được unit test mà không cần khởi tạo `ClassifierCompositeItemProcessor`. Test có thể gọi `classify(payment)` và xác nhận object delegate được trả về. Sau đó, một test composite xác nhận Spring Batch gọi delegate được chọn đúng cách.

Tách classifier có ích khi routing dựa trên nhiều thuộc tính, ví dụ payment method, currency, tenant hoặc feature flag. Nếu chỉ có một switch ngắn và ổn định, lambda có thể đủ rõ ràng.

## 8. Kiểm thử bảng phân loại (decision table)

Với nhiều nhánh, dùng parameterized test hoặc một bảng case giúp thấy rõ coverage:

| Input method | Expected delegate | Expected behavior |
|---|---|---|
| `CARD` | `cardProcessor` | Gọi xử lý thẻ. |
| `BANK_TRANSFER` | `bankProcessor` | Gọi xử lý chuyển khoản. |
| `WALLET` | `walletProcessor` | Gọi xử lý ví. |
| `null` | Không có delegate | Từ chối input với lỗi rõ ràng. |

Ví dụ parameterized test cho classifier riêng:

```java
@ParameterizedTest
@EnumSource(PaymentMethod.class)
void classifierReturnsDelegateForEverySupportedMethod(
        PaymentMethod method) {

    Payment payment = new Payment(
            "P-TEST", method, new BigDecimal("10.00"));

    ItemProcessor<?, ? extends PaymentResult> selected =
            classifier.classify(payment);

    assertThat(selected).isNotNull();
    assertThat(selected).isSameAs(expectedDelegateFor(method));
}
```

`expectedDelegateFor` là helper của test trả về mock tương ứng với method. Nếu mỗi nhánh có nhiều điều kiện hơn enum đơn giản, có thể dùng `@MethodSource` cung cấp các cặp input và expected delegate.

Parameterized test kiểm tra classifier cho toàn bộ giá trị được khai báo, nhưng vẫn cần test composite để xác nhận delegate thực sự được gọi và kết quả được trả về.

## 9. Kiểm thử nhánh mặc định và input không hỗ trợ

Classifier phải có chính sách rõ khi nhận một loại item không được hỗ trợ. Có ba lựa chọn thường gặp:

- Ném exception để Step fail hoặc áp dụng skip policy.
- Chọn một fallback processor chuyên xử lý input không hỗ trợ.
- Trả một kết quả từ chối có cấu trúc nếu nghiệp vụ yêu cầu tiếp tục xử lý.

Không nên âm thầm gửi mọi input lạ đến một nhánh hợp lệ bất kỳ. Điều đó có thể tạo side effect sai hệ thống.

Ví dụ classifier có fallback rõ ràng:

```java
return payment -> switch (payment.method()) {
    case CARD -> cardProcessor;
    case BANK_TRANSFER -> bankProcessor;
    case WALLET -> walletProcessor;
    default -> unsupportedPaymentProcessor;
};
```

Nếu enum có thể được mở rộng ở phiên bản sau, default branch cần có test để xác nhận hành vi. Nếu dùng switch expression không có default, việc thêm enum value có thể khiến compiler yêu cầu cập nhật classifier; đây đôi khi là lựa chọn tốt để buộc developer xử lý loại mới.

Test input null riêng vì lỗi có thể xảy ra trước khi switch được thực hiện. Nếu `Payment` có thể null từ reader, cần quyết định từ chối ở validator/processor trước classifier hoặc kiểm tra trong classifier.

## 10. Kiểm thử delegate không được chọn không có side effect

Chỉ assert kết quả cuối chưa chắc chứng minh chỉ một nhánh được gọi. Một classifier sai có thể gọi nhầm nhánh phụ rồi vẫn trả kết quả mong đợi.

Hãy xác nhận:

- Delegate đúng được gọi đúng số lần.
- Delegate không được chọn không nhận lời gọi.
- Không có service của nhánh khác bị gọi.
- Không có dữ liệu đầu ra phụ từ nhánh không liên quan.

Ví dụ:

```java
verify(cardProcessor, times(1)).process(cardPayment);
verifyNoInteractions(bankProcessor, walletProcessor);
verifyNoInteractions(bankGateway, walletGateway);
```

Nếu các delegate dùng chung một service, hãy verify tham số được gửi đến service hoặc dùng collaborator riêng cho từng nhánh. Không nên dùng `verifyNoInteractions` trên một collaborator mà nhánh được chọn cũng hợp lệ khi gọi nó.

## 11. Kiểm thử kết quả null của nhánh

Một delegate có thể trả `null` theo hợp đồng `ItemProcessor` để filter item. Với classifier composite, kết quả null được trả về cho Step và item không đi đến writer.

Ví dụ test:

```java
@Test
void nullFromSelectedBranchFiltersItem() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> cardProcessor =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> bankProcessor =
            mock(ItemProcessor.class);

    Payment payment = new Payment(
            "P-3001", PaymentMethod.CARD, new BigDecimal("0.00"));
    when(cardProcessor.process(payment)).thenReturn(null);

    ClassifierCompositeItemProcessor<Payment, PaymentResult> composite =
            new ClassifierCompositeItemProcessor<>();
    composite.setClassifier(item -> item.method() == PaymentMethod.CARD
            ? cardProcessor : bankProcessor);

    assertThat(composite.process(payment)).isNull();
    verify(cardProcessor).process(payment);
    verifyNoInteractions(bankProcessor);
}
```

Không nhầm kết quả null với classifier không tìm thấy delegate. Nếu classifier trả về null, composite không có processor để gọi và có thể phát sinh `NullPointerException`. Nên để classifier trả về một delegate fallback hoặc ném exception có ý nghĩa thay vì trả null.

## 12. Kiểm thử exception ở từng nhánh

Mỗi delegate có thể ném loại exception riêng. Unit test cần xác nhận exception từ nhánh được chọn truyền ra ngoài và nhánh khác không chạy.

```java
@Test
void exceptionFromSelectedBranchIsPropagated() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> cardProcessor =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<Payment, PaymentResult> bankProcessor =
            mock(ItemProcessor.class);

    Payment payment = new Payment(
            "P-4001", PaymentMethod.BANK_TRANSFER,
            new BigDecimal("500.00"));
    RuntimeException failure = new IllegalStateException("bank unavailable");
    when(bankProcessor.process(payment)).thenThrow(failure);

    ClassifierCompositeItemProcessor<Payment, PaymentResult> composite =
            new ClassifierCompositeItemProcessor<>();
    composite.setClassifier(item -> item.method() == PaymentMethod.CARD
            ? cardProcessor : bankProcessor);

    assertThatThrownBy(() -> composite.process(payment))
            .isSameAs(failure);

    verify(bankProcessor).process(payment);
    verifyNoInteractions(cardProcessor);
}
```

Ở cấp unit test, xác nhận composite không nuốt exception. Ở cấp Step, xác nhận exception đó được phân loại đúng thành retry, skip hoặc failure theo policy của Job.

## 13. Kiểm thử logic bên trong từng delegate

Routing đúng không chứng minh delegate xử lý đúng nghiệp vụ. Mỗi nhánh cần unit test riêng cho logic của nó.

Ví dụ nhánh thẻ:

- Amount dương và currency được hỗ trợ: gọi gateway với đúng dữ liệu.
- Amount bằng 0 hoặc âm: trả kết quả validation hoặc ném exception nghiệp vụ.
- Gateway từ chối giao dịch: ánh xạ status đúng.
- Gateway timeout: ném exception transient để policy có thể retry.
- Response thiếu reference: xử lý theo hợp đồng, không tự tạo trạng thái thành công.

Ví dụ nhánh chuyển khoản:

- Account đích hợp lệ: tạo transfer request đúng.
- Account không tồn tại: lỗi dữ liệu hoặc business rejection.
- Ngân hàng không khả dụng: exception transient.
- Request được gửi lại: giữ idempotency key ổn định.

Ví dụ nhánh ví:

- Wallet ID hợp lệ: gọi đúng service.
- Ví bị khóa: trả kết quả nghiệp vụ tương ứng.
- Hạn mức không đủ: không gửi request thanh toán.
- Timeout sau khi service có thể đã xử lý: tra cứu trạng thái hoặc retry bằng cùng idempotency key.

Các test này nên kiểm tra kết quả và tương tác với service của chính nhánh đó, không cần dựng toàn bộ `ClassifierCompositeItemProcessor` nếu mục tiêu chỉ là logic delegate.

## 14. Kiểm thử branch-specific dependency

Nếu mỗi nhánh dùng service khác nhau, inject mock tương ứng để xác nhận chỉ service đúng được gọi:

```java
@Test
void cardBranchCallsCardGatewayOnly() throws Exception {
    CardGateway cardGateway = mock(CardGateway.class);
    BankGateway bankGateway = mock(BankGateway.class);

    ItemProcessor<Payment, PaymentResult> cardProcessor =
            new CardPaymentProcessor(cardGateway);
    ItemProcessor<Payment, PaymentResult> bankProcessor =
            new BankTransferProcessor(bankGateway);

    Payment payment = new Payment(
            "P-5001", PaymentMethod.CARD, new BigDecimal("100.00"));

    // Dựng classifier composite bằng hai processor trên.
    // Gọi process(payment), sau đó xác nhận gateway tương ứng.

    verify(cardGateway).charge(any(CardChargeRequest.class));
    verifyNoInteractions(bankGateway);
}
```

Phần dựng composite được lược trong ví dụ để tập trung vào assertion của dependency; test đầy đủ cần dùng cùng classifier production. Với service dùng chung, kiểm tra request type hoặc operation code để bảo đảm nhánh không gửi nhầm loại lệnh.

## 15. Kiểm thử chain bên trong một branch

Một branch có thể chứa một chuỗi `CompositeItemProcessor` riêng. Ví dụ thanh toán thẻ cần normalize card data, kiểm tra fraud rồi mapping request. Chuyển khoản có một chain khác.

```text
Payment
   |
   v
Classifier
   |
   +-- CARD --> NormalizeCard -> FraudCheck -> CardRequest
   |
   +-- BANK --> ValidateAccount -> BankRequest
```

Kiểm thử theo hai lớp:

1. Test classifier chọn đúng chain cho từng loại payment.
2. Test từng chain đảm bảo các delegate nội bộ chạy đúng thứ tự và truyền đúng output.

Không nên viết một test khổng lồ vừa xác nhận mọi field của từng delegate, routing, retry và database. Khi test thất bại, cần biết lỗi thuộc classifier hay một processor trong branch.

## 16. Kiểm thử ClassifierCompositeItemWriter

Nếu composite dùng để định tuyến ghi, Spring Batch có `ClassifierCompositeItemWriter<T>`. Cách kiểm thử tương tự về mặt ý tưởng: tạo item thuộc từng loại, xác nhận classifier chọn đúng writer và writer khác không nhận item.

Ví dụ định tuyến theo loại event:

```text
Event
  |
  v
Writer classifier
  |
  +--> AuditWriter
  |
  +--> ArchiveWriter
  |
  +--> RejectedWriter
```

Với writer, cần kiểm tra thêm:

- Các item được chuyển đến đúng đích.
- Hành vi khi chunk chứa item thuộc nhiều nhánh.
- Thứ tự/nhóm gọi writer theo contract của implementation đang dùng.
- Exception từ writer được chọn truyền ra Step.
- Retry không tạo side effect trùng ở đích ngoài transaction.
- Writer có state được mở, cập nhật và đóng đúng lifecycle nếu được bọc hoặc cấu hình như stream.

Không giả định test processor composite có thể thay thế test writer composite. Hai thành phần có interface và semantics khác nhau; test cần gọi đúng API đang sử dụng.

## 17. Kiểm thử tích hợp với Job/Step

Unit test classifier xác nhận quyết định định tuyến, nhưng chưa chứng minh cấu hình Spring thực tế inject đúng bean hoặc Step ghi đúng output. Dùng `@SpringBatchTest` và `JobLauncherTestUtils` để kiểm tra Job/Step trong application context.

Một integration test cho mỗi branch có thể:

1. Chuẩn bị input chứa một record thuộc branch đó.
2. Launch Job với JobParameters riêng cho test.
3. Assert `JobExecution` kết thúc `COMPLETED` khi không có lỗi.
4. Assert output tương ứng với nhánh được chọn.
5. Assert không có output của nhánh khác.
6. Assert Step counters và dữ liệu audit phù hợp.

Nếu Job dùng writer thật ghi database, kiểm tra bảng đích. Nếu output là API hoặc message broker, dùng test server/broker hoặc adapter test để quan sát request. Tránh gọi hệ thống production trong unit/integration test.

### Kiểm tra tất cả branch trong một Job run

Một test có thể đưa vào nhiều loại input và xác nhận mỗi nhánh đã được thực thi. Cách này hữu ích để kiểm tra luồng tổng thể, nhưng vẫn nên giữ unit test riêng cho từng branch để failure được định vị dễ hơn.

Ví dụ input:

```text
P-01,CARD,100.00
P-02,BANK_TRANSFER,200.00
P-03,WALLET,50.00
```

Sau khi Job chạy, kiểm tra ba kết quả có đúng provider reference/status và không có record nào bị route nhầm. Nếu processor có filter, tính toán expected count theo chính sách filter.

## 18. Kiểm thử filter count và writer output

Nếu delegate trả `null`, item bị filter và không được gửi đến writer. Integration test nên phân biệt:

- Item được đọc.
- Item được filter bởi processor.
- Item được ghi thành công.
- Item bị skip do exception.

Các counters của `StepExecution` như read count, filter count, write count, process skip count và write skip count giúp xác nhận kết quả ở cấp Step. Không chỉ assert tổng số dòng trong file nếu một nhánh có thể filter hoặc skip.

Ví dụ một nhánh lọc payment dưới ngưỡng:

```java
if (payment.amount().compareTo(minimumAmount) < 0) {
    return null;
}
```

Test cần xác nhận payment dưới ngưỡng không đến writer, `filterCount` tăng phù hợp và nhánh khác vẫn xử lý bình thường.

## 19. Retry và skip theo từng branch

Một Step có thể áp dụng chung retry/skip policy cho exception phát ra từ mọi delegate. Nếu mỗi branch có loại lỗi khác nhau, hãy dùng exception type riêng hoặc policy có phân loại rõ.

Ví dụ:

```java
return new StepBuilder("processPaymentsStep", jobRepository)
        .<Payment, PaymentResult>chunk(100, transactionManager)
        .reader(paymentReader)
        .processor(paymentProcessor)
        .writer(paymentWriter)
        .faultTolerant()
        .retry(PaymentProviderUnavailableException.class)
        .retryLimit(3)
        .skip(InvalidPaymentException.class)
        .skipLimit(25)
        .build();
```

Kiểm thử cần bao gồm:

- Lỗi transient ở nhánh thẻ được retry và sau đó thành công.
- Lỗi transient ở nhánh chuyển khoản cũng được xử lý theo policy.
- Lỗi dữ liệu của một branch được skip nếu được cho phép.
- Exception không nằm trong policy làm Step fail.
- Retry exhaustion tạo trạng thái cuối và failure metadata đúng.
- Nhánh không được chọn không bị gọi trong mọi attempt.

Nếu cần policy khác nhau theo branch, có thể tạo exception subclass riêng hoặc dùng policy tùy chỉnh dựa trên exception. Không phân loại dựa vào message text nếu có thể dùng type ổn định.

## 20. Side effect và idempotency trong branch

Delegate có thể được gọi lại do retry, rollback hoặc restart. Nếu branch gọi API thanh toán, gửi message hoặc ghi file, test phải xác nhận side effect an toàn khi lặp.

Ví dụ, idempotency key nên được tạo từ business operation ID:

```java
String key = "payment-" + payment.paymentId();
cardGateway.charge(request, key);
```

Không tạo key ngẫu nhiên mới ở mỗi lần gọi processor. Nếu API đã xử lý request nhưng response timeout, retry cần dùng cùng key hoặc tra cứu operation status trước khi gửi lại.

Với nhiều hệ thống, cân nhắc transactional outbox để lưu ý định gửi trong transaction của chunk, rồi relay theo branch tương ứng. Test relay gửi lặp và consumer deduplication riêng với test classifier.

## 21. Kiểm thử concurrency và thread safety

Classifier composite không tự chạy các nhánh song song. Tuy nhiên, nếu Step dùng multi-threaded processing hoặc nhiều Job chạy đồng thời, cùng composite bean và delegate singleton có thể được gọi từ nhiều thread.

Test concurrency cần xác nhận:

- Classifier không giữ mutable state của item trước.
- Delegate không lưu `currentPayment` trong field dùng chung.
- Dependency như client/cache có thread-safety phù hợp.
- Không trộn kết quả giữa hai payment khác nhau.
- Idempotency key và correlation ID luôn gắn đúng item.
- Output của từng branch không ghi chung resource ngoài ý muốn.

Nếu một delegate không thread-safe, dùng scope phù hợp, đồng bộ hóa có chủ đích hoặc điều chỉnh cấu hình concurrency. Không giả định vì classifier chọn một delegate cho mỗi item nên delegate chỉ được gọi một lần tại một thời điểm.

## 22. Theo dõi branch trong test và vận hành

Ở cấp Step, `ItemProcessListener` nhìn thấy composite processor như một processor. Nó không tự cung cấp callback riêng cho từng delegate bên trong.

Nếu cần theo dõi branch, có thể:

- Ghi metric trong classifier hoặc delegate.
- Bọc từng delegate bằng decorator ghi thời gian và kết quả.
- Ghi structured log với branch name và business correlation ID.
- Tạo counter riêng cho số item đi qua mỗi branch.
- Dùng tracing span cho lời gọi service bên trong từng nhánh.

Trong test, có thể dùng spy/mock để xác nhận branch count. Trong production, metric tag nên có cardinality thấp như `branch=card` hoặc `branch=bank`; không dùng payment ID làm tag.

Không ghi toàn bộ dữ liệu thanh toán hoặc thông tin định danh nhạy cảm vào log chỉ để kiểm tra routing.

## 23. Những lỗi thường gặp khi test composite branches

### Chỉ kiểm thử một nhánh

Các nhánh còn lại có thể chưa được wiring hoặc classifier phân loại sai. Tạo test cho từng giá trị discriminator và mỗi fallback.

### Chỉ kiểm tra kết quả cuối

Kết quả có thể đúng dù delegate sai cũng bị gọi. Verify delegate được chọn và xác nhận các delegate khác không có tương tác.

### Dùng classifier khác production trong test

Test có thể pass trong khi bean cấu hình thật sai. Tái sử dụng classifier production hoặc dựng composite bằng cùng cấu hình.

### Không kiểm thử input không hỗ trợ

Loại mới có thể rơi vào nhánh mặc định không an toàn. Định nghĩa fallback hoặc exception rõ và kiểm thử.

### Không test null và exception

Branch có thể filter item hoặc ném lỗi. Xác nhận `null` được xử lý như filter, còn exception truyền ra Step.

### Chỉ test classifier, không test delegate

Routing đúng không bảo đảm nghiệp vụ bên trong branch đúng. Unit test từng delegate với input hợp lệ, biên và lỗi.

### Chỉ test delegate, không test routing

Delegate tốt vẫn có thể không bao giờ được gọi nếu classifier sai. Test composite để xác nhận đường đi từ input đến đúng delegate.

### Dùng một integration test quá lớn

Khi thất bại khó xác định lỗi ở nhánh nào. Tách test branch, classifier và end-to-end Job.

### Giả định composite chạy nhánh song song

Classifier chọn một delegate cho item; không tự parallelize. Nếu cần concurrency, kiểm thử cấu hình Step/partition riêng.

### Bỏ qua side effect khi retry

Một nhánh có thể gọi API nhiều lần. Kiểm thử idempotency, timeout và trạng thái không rõ.

## 24. Ma trận test đề xuất

Một bộ test cho composite routing có thể tổ chức như sau:

| Lớp test | Trường hợp | Điều cần xác nhận |
|---|---|---|
| Classifier unit | Mỗi discriminator hợp lệ | Trả đúng delegate. |
| Classifier unit | Null/unknown discriminator | Fallback hoặc exception rõ ràng. |
| Branch unit | Input hợp lệ cho từng nhánh | Output và dependency call đúng. |
| Branch unit | Input biên/không hợp lệ | Validation hoặc business rejection đúng. |
| Composite unit | Mỗi loại item | Chỉ delegate tương ứng được gọi. |
| Composite unit | Delegate trả `null` | Kết quả null, không có delegate khác được gọi. |
| Composite unit | Delegate ném exception | Exception truyền ra, nhánh khác không chạy. |
| Step integration | Một input cho mỗi nhánh | Writer/output và counters đúng. |
| Step integration | Retry/skip theo exception | BatchStatus, ExitStatus và counters đúng. |
| Restart integration | Restart sau chunk đã commit | Routing và side effect không bị lặp sai. |
| Concurrency | Nhiều item/Job cùng lúc | Không rò state giữa branch. |

Không nhất thiết mọi dự án phải có test cho mọi dòng nếu nhánh không có hành vi tương ứng. Hãy ưu tiên các đường đi nghiệp vụ thực tế và các rủi ro có thể gây sai dữ liệu.

## 25. Quy trình kiểm thử từng nhánh composite

Khi triển khai composite có routing, có thể làm theo trình tự:

1. Liệt kê discriminator và nhánh tương ứng.
2. Xác định default/fallback và hành vi với input null hoặc không hỗ trợ.
3. Unit test classifier để xác nhận mỗi loại input chọn đúng delegate.
4. Unit test từng delegate độc lập với input hợp lệ, biên và lỗi.
5. Unit test composite để xác nhận chỉ nhánh được chọn được gọi.
6. Kiểm tra `null` filter và exception propagation.
7. Nếu branch chứa chain, test thứ tự delegate nội bộ riêng.
8. Integration test Step/Job để xác nhận bean wiring, output và counters.
9. Test retry/skip/failure cho exception từ các nhánh cần thiết.
10. Test idempotency nếu branch tạo side effect ngoài transaction.
11. Test concurrency nếu Step hoặc Job chạy nhiều thread/partition.
12. Dùng metric/log theo branch để hỗ trợ chẩn đoán mà không lộ payload nhạy cảm.

| Câu hỏi | Bằng chứng trong test |
|---|---|
| Input loại A đi đúng nhánh chưa? | Verify delegate A được gọi với item tương ứng. |
| Nhánh B có bị gọi nhầm không? | `verifyNoInteractions` hoặc verify không có lời gọi. |
| Input không hỗ trợ xử lý thế nào? | Assert fallback result hoặc exception mong đợi. |
| Nhánh có filter item không? | Assert processor trả null và writer không nhận item. |
| Nhánh gặp lỗi thì sao? | Assert exception propagation và Step retry/skip/fail đúng. |
| Tất cả nhánh hoạt động trong Job thật chưa? | Integration test với input đại diện cho từng branch và xác nhận output. |

## Kết luận

Kiểm thử từng nhánh composite cần xác nhận cả quyết định phân loại lẫn logic của delegate được chọn. Với `ClassifierCompositeItemProcessor`, hãy tạo test cho mọi discriminator, kiểm tra đúng delegate được gọi và các nhánh khác không nhận item; test riêng từng delegate cho dữ liệu hợp lệ, biên và lỗi; đồng thời xác nhận hành vi với input không hỗ trợ, `null` và exception. Unit test classifier/composite giúp định vị lỗi routing, còn integration test qua Step/Job xác nhận bean wiring, writer output, counters và retry/skip policy. Nếu nhánh có side effect hoặc chạy đồng thời, bổ sung kiểm thử idempotency và thread safety. Phân biệt rõ branch routing với `CompositeItemProcessor` dạng chain để test đúng semantics của component đang dùng.
