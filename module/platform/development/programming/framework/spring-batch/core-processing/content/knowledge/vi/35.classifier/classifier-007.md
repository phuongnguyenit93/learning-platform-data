# Item không khớp classifier

Trong Spring Batch, Classifier được dùng để chọn một delegate phù hợp với từng item. Ví dụ, giao dịch CARD được chuyển tới CardPaymentProcessor, giao dịch TRANSFER được chuyển tới BankTransferProcessor. Tuy nhiên, dữ liệu đầu vào có thể chứa loại item mới, giá trị null, chuỗi rỗng, mã viết sai hoặc một subtype mà classifier chưa biết.

Trường hợp classifier không tìm được nhánh phù hợp cần có chính sách rõ ràng. Với ClassifierCompositeItemProcessor, classifier phải trả về một ItemProcessor để composite gọi xử lý item. Nếu classifier trả về null, composite không có delegate để gọi và thường phát sinh NullPointerException. ClassifierCompositeItemProcessor không tự hiểu null là filter, skip hay fallback.

Vì vậy, khi không có route phù hợp, ứng dụng cần chủ động chọn một trong các hành vi: fail fast để dừng Step, chuyển item tới fallback processor, tạo kết quả rejected/quarantine, hoặc chọn một delegate có chủ đích để filter item. Các hành vi này khác nhau về ý nghĩa nghiệp vụ, skip count, audit và khả năng restart.

## 1. Classifier chọn delegate cho từng item

Classifier nhận một đối tượng đầu vào và trả về một kết quả phân loại. Khi dùng với ClassifierCompositeItemProcessor, kết quả phân loại là một delegate ItemProcessor:

~~~text
ItemReader
    |
    v
Input item
    |
    v
ClassifierCompositeItemProcessor
    |
    v
Classifier.classify(item)
    |
    +---- CARD -------> CardPaymentProcessor
    |
    +---- TRANSFER --> TransferPaymentProcessor
    |
    +---- CASH ------> CashPaymentProcessor
    |
    +---- Không khớp -> Chính sách no-match
~~~

Ví dụ item:

~~~java
public record Payment(
        String paymentId,
        String type,
        BigDecimal amount) {
}
~~~

Classifier đơn giản:

~~~java
return payment -> switch (payment.type()) {
    case "CARD" -> cardProcessor;
    case "TRANSFER" -> transferProcessor;
    case "CASH" -> cashProcessor;
    default -> null;
};
~~~

Đoạn code cuối trả null cho mọi type không được nhận diện. Đây không phải cách xử lý no-match an toàn cho ClassifierCompositeItemProcessor. Composite cần một delegate hợp lệ; nếu nhận null, lúc gọi process trên delegate sẽ thất bại. Cần thay default bằng một chính sách tường minh.

## 2. Các trường hợp không khớp thường gặp

Một item có thể không khớp classifier vì nhiều lý do:

| Trường hợp | Ví dụ | Ý nghĩa có thể có |
|---|---|---|
| Giá trị mới | type là WALLET nhưng ứng dụng chưa hỗ trợ | Producer đã mở rộng schema |
| Sai chính tả | TRANSFRE thay vì TRANSFER | Dữ liệu nguồn không hợp lệ |
| Chuỗi rỗng | type là chuỗi trắng | Thiếu dữ liệu bắt buộc |
| Null | type không có trong payload | Mapping hoặc contract đầu vào thiếu field |
| Khác chữ hoa/thường | card thay vì CARD | Quy tắc chuẩn hóa chưa thống nhất |
| Khoảng trắng | " CARD " | Input chưa được trim |
| Class/subtype mới | Một implementation Payment mới | Model đã mở rộng nhưng registry chưa cập nhật |
| Route cấu hình thiếu | Có enum mới nhưng không đăng ký processor | Lỗi cấu hình triển khai |

Không phải mọi trường hợp đều nên đi cùng một nhánh fallback. Một type mới có thể là thay đổi producer cần triển khai consumer; một chuỗi sai chính tả có thể là dữ liệu lỗi; một route bị thiếu có thể là lỗi cấu hình khiến Job cần dừng.

Nên phân biệt lỗi dữ liệu của từng item với lỗi cấu hình của ứng dụng. Nếu route bắt buộc phải tồn tại nhưng deployment quên đăng ký delegate, việc skip hàng loạt item sẽ che giấu lỗi cấu hình.

## 3. Phân biệt no-match, filter và skip

Ba tình huống này có semantics khác nhau:

- **No-match:** classifier không tìm được delegate. Đây là quyết định định tuyến chưa được xác định.
- **Filter:** delegate được chọn và trả về null. Item bị loại có chủ đích, không đi tới writer và được tính vào filter count.
- **Skip:** một thành phần ném exception được cấu hình skippable. Spring Batch ghi nhận skip ở giai đoạn tương ứng và có thể gọi SkipListener.

| Hành vi | Nơi quyết định | Kết quả |
|---|---|---|
| No-match trả null | Classifier | Không có delegate; composite có thể ném NullPointerException |
| Fail fast | Classifier ném exception | Step thất bại, trừ khi exception được xử lý theo policy |
| Fallback | Classifier trả fallback processor | Item được xử lý theo logic fallback |
| Filter | Delegate trả null | Item không tới writer |
| Skip | Reader/processor/writer ném skippable exception | Item bị bỏ qua theo fault-tolerance policy |
| Quarantine | Fallback tạo rejected output hoặc writer riêng lưu lỗi | Có record để audit hoặc replay |

Không nên dùng null từ classifier để biểu thị filter. Nếu muốn filter, classifier vẫn phải chọn một processor hợp lệ; chính processor đó mới trả null.

## 4. Chính sách 1: fail fast khi không có route

Nếu mọi item phải thuộc một loại đã hỗ trợ, cách đơn giản nhất là ném exception có ý nghĩa:

~~~java
public class UnsupportedPaymentTypeException
        extends RuntimeException {

    public UnsupportedPaymentTypeException(String type) {
        super("Unsupported payment type: " + type);
    }
}
~~~

Classifier:

~~~java
Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> paymentClassifier =
        payment -> {
            String type = normalize(payment.type());

            return switch (type) {
                case "CARD" -> cardProcessor;
                case "TRANSFER" -> transferProcessor;
                case "CASH" -> cashProcessor;
                default -> throw new UnsupportedPaymentTypeException(type);
            };
        };
~~~

Với cách này, Job phát hiện sớm item không thuộc contract hiện tại. Nếu exception không được cấu hình skip, Step sẽ thất bại. Đây là lựa chọn phù hợp khi một type mới có thể làm thay đổi quy tắc tính tiền, trạng thái hoặc cách ghi dữ liệu.

Không dùng IllegalArgumentException chung cho mọi lỗi nếu cần phân biệt no-match với lỗi khác. Exception riêng giúp cấu hình skip/retry và phân tích log chính xác hơn.

## 5. Chính sách 2: dùng fallback processor

Nếu Job phải tiếp tục xử lý các item có type chưa hỗ trợ, classifier có thể trả về một fallback processor. Fallback là một delegate thực sự, được cấu hình và quản lý như các processor khác.

Ví dụ fallback tạo kết quả rejected:

~~~java
@Component
public class UnsupportedPaymentProcessor
        implements ItemProcessor<Payment, PaymentResult> {

    @Override
    public PaymentResult process(Payment payment) {
        return PaymentResult.rejected(
                payment.paymentId(),
                payment.type(),
                "UNSUPPORTED_PAYMENT_TYPE");
    }
}
~~~

Classifier:

~~~java
@Bean
Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> paymentClassifier(
        CardPaymentProcessor cardProcessor,
        TransferPaymentProcessor transferProcessor,
        CashPaymentProcessor cashProcessor,
        UnsupportedPaymentProcessor fallbackProcessor) {

    Map<String, ItemProcessor<Payment, PaymentResult>> routes = Map.of(
            "CARD", cardProcessor,
            "TRANSFER", transferProcessor,
            "CASH", cashProcessor);

    return payment -> {
        String type = normalize(payment.type());
        return routes.getOrDefault(type, fallbackProcessor);
    };
}
~~~

Khi type không có trong map, fallback được chọn và trả một PaymentResult hợp lệ. Writer có thể lưu kết quả rejected vào bảng audit hoặc chuyển sang output khác dựa trên trạng thái kết quả.

Fallback không nên âm thầm biến type lạ thành một giao dịch hợp lệ. Cần giữ lại payment ID, raw type, lý do rejected và batch ID nếu cần điều tra/replay. Nếu payload có dữ liệu nhạy cảm, chỉ lưu các trường cần thiết hoặc lưu raw payload trong vùng được bảo vệ.

## 6. Chính sách 3: route tới quarantine

Một fallback processor có thể chuyển item không hỗ trợ thành một kiểu output thể hiện rõ trạng thái quarantine:

~~~java
public record PaymentResult(
        String paymentId,
        String status,
        String reason,
        BigDecimal amount) {

    public static PaymentResult accepted(
            String paymentId,
            BigDecimal amount) {
        return new PaymentResult(
                paymentId, "ACCEPTED", null, amount);
    }

    public static PaymentResult rejected(
            String paymentId,
            String reason) {
        return new PaymentResult(
                paymentId, "REJECTED", reason, null);
    }
}
~~~

Fallback:

~~~java
public class QuarantinePaymentProcessor
        implements ItemProcessor<Payment, PaymentResult> {

    @Override
    public PaymentResult process(Payment payment) {
        return PaymentResult.rejected(
                payment.paymentId(),
                "NO_CLASSIFIER_MATCH:" + payment.type());
    }
}
~~~

Có thể dùng một writer để ghi cả accepted và rejected với discriminator status. Nếu quarantine cần lưu vào bảng hoặc resource riêng, có thể dùng writer định tuyến riêng hoặc tách Step sau khi đã chuẩn hóa output.

Quarantine khác skip: item vẫn có một kết quả có thể kiểm tra và đối soát. Đây là lựa chọn phù hợp khi hệ thống cần tiếp tục batch nhưng không được làm mất các record chưa hỗ trợ.

Nếu writer lưu quarantine trong cùng database và cùng transaction chunk, kết quả rejected có thể commit cùng chunk. Nếu ghi ra hệ thống ngoài database, cần idempotency key và cơ chế xử lý retry.

## 7. Chính sách 4: filter có chủ đích

Có trường hợp item không cần xử lý theo bất kỳ nhánh nghiệp vụ nào, ví dụ loại record được phép bỏ qua theo contract. Khi đó, classifier vẫn trả một delegate hợp lệ:

~~~java
@Component
public class IgnorePaymentProcessor
        implements ItemProcessor<Payment, PaymentResult> {

    @Override
    public PaymentResult process(Payment payment) {
        return null;
    }
}
~~~

Classifier:

~~~java
return payment -> {
    String type = normalize(payment.type());
    return routes.getOrDefault(type, ignorePaymentProcessor);
};
~~~

Trong ví dụ, type không có route sẽ được chuyển tới IgnorePaymentProcessor, và delegate trả null để filter item. Cách này chỉ phù hợp khi bỏ item là quyết định nghiệp vụ có chủ đích.

Filter không tự ghi lý do vào SkipListener và không tạo quarantine record. Nếu cần audit, hãy ghi metric hoặc dùng fallback tạo rejected output thay vì trả null.

Không dùng filter để xử lý type mới một cách mặc định nếu chưa biết ý nghĩa của type đó. Một thay đổi producer có thể làm dữ liệu quan trọng biến mất khỏi output mà Job vẫn COMPLETED.

## 8. Chuẩn hóa input trước khi phân loại

Một số trường hợp không khớp chỉ do khác định dạng. Có thể chuẩn hóa type trước khi tra route:

~~~java
private String normalize(String type) {
    if (type == null || type.isBlank()) {
        return "";
    }
    return type.trim().toUpperCase(Locale.ROOT);
}
~~~

Sử dụng Locale.ROOT cho mã kỹ thuật để kết quả không phụ thuộc locale mặc định của server.

Không nên chuẩn hóa quá rộng theo kiểu tự đoán mọi giá trị. Ví dụ, không tự đổi "WIRE" thành "TRANSFER" nếu contract không quy định hai mã tương đương. Alias phải được khai báo tường minh:

~~~java
Map<String, String> aliases = Map.of(
        "BANK_TRANSFER", "TRANSFER",
        "WIRE", "TRANSFER");
~~~

Sau khi chuẩn hóa, kiểm tra route key trong registry. Nếu alias không được công nhận, xử lý như unknown type. Việc normalize giúp xử lý khác biệt định dạng, nhưng không thay thế validation.

## 9. Xử lý null, blank và field thiếu

Classifier nên xử lý null trước khi gọi trim(), toUpperCase() hoặc switch:

~~~java
String type = payment == null ? null : payment.type();
~~~

Trong chunk processing thông thường, reader không nên phát null như một item vì null thường biểu thị hết dữ liệu. Tuy nhiên, property type bên trong item có thể null hoặc blank.

Có thể tách các lỗi:

~~~java
if (payment == null) {
    throw new IllegalArgumentException("Payment item must not be null");
}

if (payment.type() == null || payment.type().isBlank()) {
    throw new MissingPaymentTypeException(payment.paymentId());
}
~~~

Một field bị thiếu có thể là lỗi contract nghiêm trọng hơn một type mới. Nếu cần phân biệt, hãy dùng exception riêng hoặc đưa validation vào processor trước khi routing. Đừng để NullPointerException từ switch hoặc Map lookup trở thành thông báo lỗi duy nhất.

## 10. Phân biệt type mới với route bị cấu hình thiếu

Hai trường hợp có biểu hiện tương tự nhưng nguyên nhân khác nhau:

- Input chứa type WALLET mà ứng dụng chưa hỗ trợ: dữ liệu nguồn mới hoặc contract chưa được triển khai.
- Ứng dụng có PaymentType.WALLET nhưng registry không có WalletPaymentProcessor: lỗi cấu hình/deployment.

Nếu dùng một map route, có thể xác thực cấu hình khi tạo bean:

~~~java
public class PaymentRouter {

    private final Map<PaymentType, ItemProcessor<Payment, PaymentResult>> routes;

    public PaymentRouter(
            Map<PaymentType, ItemProcessor<Payment, PaymentResult>> routes,
            Set<PaymentType> requiredTypes) {

        this.routes = Map.copyOf(routes);

        Set<PaymentType> missing = new HashSet<>(requiredTypes);
        missing.removeAll(routes.keySet());

        if (!missing.isEmpty()) {
            throw new IllegalStateException(
                    "Missing processors for payment types: " + missing);
        }
    }
}
~~~

Kiểm tra registry lúc khởi tạo giúp phát hiện lỗi cấu hình trước khi đọc hàng triệu item. Còn type không biết từ payload được xử lý trong classify() theo policy dữ liệu.

Không nên dùng fallback cho một delegate bắt buộc nhưng bị thiếu do cấu hình sai. Nếu fallback được dùng cho cả hai trường hợp, Job có thể chạy thành công nhưng mọi item của một loại đã hỗ trợ lại bị quarantine.

## 11. Dùng enum để giảm lỗi định tuyến

Nếu danh sách type được xác định trong contract, dùng enum có thể giúp compiler kiểm tra:

~~~java
public enum PaymentType {
    CARD,
    TRANSFER,
    CASH
}
~~~

Parser chuyển chuỗi từ nguồn sang enum:

~~~java
PaymentType parseType(String rawType) {
    String normalized = normalize(rawType);
    try {
        return PaymentType.valueOf(normalized);
    } catch (IllegalArgumentException ex) {
        throw new UnsupportedPaymentTypeException(normalized);
    }
}
~~~

Classifier:

~~~java
return payment -> switch (payment.paymentType()) {
    case CARD -> cardProcessor;
    case TRANSFER -> transferProcessor;
    case CASH -> cashProcessor;
};
~~~

Nếu enum được mở rộng, cần cập nhật route registry và test tương ứng. Với Java enum switch expression không có default, compiler có thể giúp phát hiện trường hợp thiếu khi source enum thay đổi và được biên dịch lại. Tuy nhiên, nếu dữ liệu JSON có type chưa được parse thành enum, vẫn cần xử lý unknown value ở tầng deserialization.

Không ánh xạ mọi enum lạ thành một type hợp lệ như CASH. Nếu cần tiếp tục xử lý, dùng UNKNOWN hoặc một biểu diễn raw type riêng và route nó tới fallback.

## 12. Classifier theo Map và fallback

Map thường phù hợp khi số route nhiều hoặc route được cấu hình:

~~~java
public class MapPaymentClassifier
        implements Classifier<Payment, ItemProcessor<?, ? extends PaymentResult>> {

    private final Map<String, ItemProcessor<Payment, PaymentResult>> routes;
    private final ItemProcessor<Payment, PaymentResult> fallback;

    public MapPaymentClassifier(
            Map<String, ItemProcessor<Payment, PaymentResult>> routes,
            ItemProcessor<Payment, PaymentResult> fallback) {
        this.routes = Map.copyOf(routes);
        this.fallback = fallback;
    }

    @Override
    public ItemProcessor<?, ? extends PaymentResult> classify(Payment payment) {
        String key = normalize(payment.type());
        return routes.getOrDefault(key, fallback);
    }
}
~~~

Map.copyOf không chấp nhận key hoặc value null. Đây là đặc tính hữu ích để phát hiện cấu hình route không hợp lệ ngay khi tạo classifier.

Nếu fallback có thể null, cần validate constructor thay vì để lỗi xảy ra trong process(). Một router nên đảm bảo mọi đầu vào đều trả về một delegate hợp lệ hoặc ném một exception có ý nghĩa.

## 13. Classifier theo nhiều thuộc tính

Một route có thể phụ thuộc type và source system:

~~~java
public record PaymentRoute(
        String sourceSystem,
        PaymentType type) {
}
~~~

Map route:

~~~java
Map<PaymentRoute, ItemProcessor<Payment, PaymentResult>> routes = Map.of(
        new PaymentRoute("ERP", PaymentType.CARD), erpCardProcessor,
        new PaymentRoute("MOBILE", PaymentType.CARD), mobileCardProcessor,
        new PaymentRoute("ERP", PaymentType.TRANSFER), erpTransferProcessor);
~~~

Classifier:

~~~java
PaymentRoute key = new PaymentRoute(
        normalize(payment.sourceSystem()),
        payment.paymentType());

return routes.getOrDefault(key, fallbackProcessor);
~~~

Khi không tìm thấy route, cần xác định nguyên nhân: type chưa hỗ trợ, source system chưa đăng ký hay tổ hợp type/source không được phép. Có thể phân biệt bằng cách kiểm tra từng thành phần và tạo exception/rejection reason cụ thể.

Không nên dùng một fallback chung nếu các trường hợp cần hành vi khác nhau. Ví dụ, type mới từ producer có thể quarantine, còn source system bị cấu hình sai có thể phải fail Step.

## 14. No-match trong ClassifierCompositeItemProcessor

ClassifierCompositeItemProcessor thường hoạt động theo logic khái quát:

~~~java
public O process(I item) throws Exception {
    ItemProcessor<?, ? extends O> delegate = classifier.classify(item);
    return (O) delegate.process(item);
}
~~~

Đây là mô tả hành vi để giải thích contract; implementation thực tế có thể dùng generic/cast khác theo phiên bản. Điểm quan trọng là composite cần delegate trả về từ classifier. Nếu delegate là null, không có processor nào để gọi.

Do đó:

- Classifier không nên trả null để biểu thị “không xử lý”.
- Fallback phải là một ItemProcessor hợp lệ.
- Nếu cần filter, delegate được chọn trả null.
- Nếu cần dừng Step, classifier ném exception riêng.
- Nếu cần quarantine, fallback trả rejected output hoặc ghi nhận theo thiết kế writer.

Không dựa vào NullPointerException như một cơ chế báo unknown route. Nó không chỉ ra route key nào không hợp lệ và có thể làm log khó phân tích.

## 15. No-match trong ClassifierCompositeItemWriter

Classifier cũng có thể được dùng để định tuyến writer. Với ClassifierCompositeItemWriter, classifier chọn ItemWriter cho item. Nếu không có writer phù hợp và trả null, composite không có delegate để ghi item; cần một policy rõ ràng tương tự.

Các lựa chọn:

- Ném exception để chunk thất bại.
- Trả về fallback writer để ghi vào bảng/file quarantine.
- Định tuyến đến writer loại bỏ có chủ đích chỉ khi API và nghiệp vụ cho phép.
- Chuẩn hóa output về một type rồi dùng writer duy nhất.

Không nhầm việc processor trả null với writer no-match. Processor trả null là filter trước khi writer nhận item. Writer classifier không có khái niệm filter giống ItemProcessor; một writer thường thực hiện side effect ghi và cần có delegate hợp lệ.

## 16. Xử lý exception và Skip Policy

Nếu classifier ném UnsupportedPaymentTypeException bên trong ClassifierCompositeItemProcessor, exception xảy ra trong giai đoạn process. Step có thể áp dụng skip policy nếu loại exception được cấu hình skippable:

~~~java
return new StepBuilder("importPaymentsStep", jobRepository)
        .<Payment, PaymentResult>chunk(100, transactionManager)
        .reader(paymentReader)
        .processor(classifierComposite)
        .writer(paymentWriter)
        .faultTolerant()
        .skip(UnsupportedPaymentTypeException.class)
        .skipLimit(20)
        .listener(paymentSkipListener)
        .build();
~~~

Chỉ dùng cấu hình này nếu loại payment không hỗ trợ thực sự được phép bỏ qua. Nếu type không hỗ trợ cho thấy producer gửi sai schema hoặc deployment thiếu processor, fail-fast thường phù hợp hơn.

SkipListener có callback riêng cho giai đoạn process:

~~~java
public class PaymentSkipListener
        implements SkipListener<Payment, PaymentResult> {

    @Override
    public void onSkipInProcess(Payment item, Throwable cause) {
        // Ghi nhận business key và nguyên nhân skip.
    }
}
~~~

Nếu classifier ném exception trước khi tạo output, item vẫn có thể được truyền vào onSkipInProcess vì lỗi xảy ra trong process. Nếu lỗi xảy ra khi writer ghi quarantine, callback sẽ là onSkipInWrite. Hãy phân biệt đúng giai đoạn để audit.

## 17. Retry hay skip khi không có route?

No-match do dữ liệu không hợp lệ thường không tự biến mất khi retry. Nếu cùng item và cùng classifier/configuration, retry sẽ chọn cùng kết quả. Vì vậy, retry không phù hợp cho một unknown type cố định.

| Nguyên nhân | Hành vi phù hợp |
|---|---|
| Type không được hỗ trợ trong contract | Fail hoặc quarantine theo nghiệp vụ |
| Typo/field thiếu | Validation failure; skip chỉ khi được phép |
| Route registry thiếu do cấu hình | Fail fast, sửa deployment |
| Policy lookup tạm thời không truy cập được | Retry lookup có giới hạn |
| Cache tạm thời lỗi | Retry hoặc fallback an toàn theo policy |
| Delegate lỗi do dữ liệu nghiệp vụ | Skip/fail tùy exception và contract |

Không retry một UnsupportedPaymentTypeException chỉ để thử lại cùng một map route bất biến. Nếu route có thể xuất hiện sau khi tải policy từ dịch vụ ngoài, exception cần phân biệt với lỗi lookup tạm thời.

## 18. Tác động của retry và restart

Classifier nên xác định và có thể lặp lại. Nếu route phụ thuộc vào thời gian, bộ đếm, thứ tự gọi hoặc state mutable, cùng một item có thể được định tuyến khác khi retry hoặc restart.

Ví dụ không ổn định:

~~~java
return payment -> {
    if (retryCounter++ % 2 == 0) {
        return cardProcessor;
    }
    return fallbackProcessor;
};
~~~

Khi một chunk rollback, classifier có thể đã được gọi và counter đã thay đổi trong memory. Lần retry có thể đưa cùng payment sang fallback. Sau restart, counter lại được khởi tạo theo cách khác.

Để định tuyến ổn định:

- Dựa vào field bất biến của item.
- Dùng routing key rõ ràng.
- Pin policy/schema version trong JobParameters hoặc ExecutionContext.
- Không thay đổi route map trong khi Step đang chạy.
- Nếu cần lưu quyết định route, lưu theo business key và transaction semantics rõ ràng.

Retry chỉ nên áp dụng cho lỗi tạm thời. No-match cố định nên có quyết định fail, reject hoặc filter ngay từ đầu.

## 19. Thread safety của fallback và classifier

Classifier và fallback processor thường là Spring singleton. Nếu Step chạy nhiều thread hoặc nhiều JobExecution, cùng instance có thể được gọi đồng thời.

Thiết kế an toàn:

- Giữ route map immutable sau khi khởi tạo.
- Không lưu current item vào field.
- Không thay đổi fallback delegate giữa lúc Step chạy.
- Fallback processor stateless hoặc dùng dependency thread-safe.
- Nếu cần metrics, dùng Micrometer hoặc concurrent counter.
- Nếu fallback ghi audit, dùng writer/repository transaction-aware và idempotency key.

Không dùng ArrayList/HashMap mutable để gom các item không khớp từ nhiều thread. Có thể dùng concurrent collection cho telemetry, nhưng dữ liệu quarantine quan trọng nên được ghi bền vững qua writer/database thay vì chỉ giữ trong memory.

## 20. Quan sát và audit item không khớp

Khi chọn fallback, cần biết bao nhiêu item không khớp và vì sao:

- Raw route key hoặc giá trị type đã chuẩn hóa.
- Source system và schema version.
- Business key của item.
- JobExecution ID và StepExecution ID.
- Fallback/rejection reason.
- Số lần gặp theo loại.
- Timestamp và batch ID.

Không log toàn bộ payload nếu có dữ liệu cá nhân hoặc bí mật. Có thể lưu raw payload trong kho quarantine có quyền truy cập hạn chế và log reference ID.

Metrics hữu ích:

- Số item theo từng route.
- Số item không khớp.
- Số item thiếu route key.
- Số item bị filter.
- Số item bị skip.
- Số lỗi do route configuration.

Phân biệt no-match count với skip count và filter count. Một fallback có thể tạo output rejected nên vẫn được tính là item đã xử lý và ghi, không phải skip.

## 21. Kiểm thử classifier no-match

Nên unit test tất cả loại input và từng chính sách:

1. Type đã hỗ trợ chọn đúng delegate.
2. Type mới chọn fallback hoặc ném exception theo policy.
3. Type null không gây NullPointerException không rõ nguyên nhân.
4. Chuỗi blank được xử lý đúng.
5. Chữ hoa/thường và khoảng trắng được chuẩn hóa đúng.
6. Alias được hỗ trợ chỉ khi được khai báo.
7. Registry thiếu delegate bắt lỗi cấu hình khi khởi tạo.
8. Fallback trả kết quả rejected có business key và reason.
9. Filter delegate trả null và không tới writer.
10. Retry cùng item vẫn chọn cùng delegate.

Ví dụ test fallback:

~~~java
@Test
void routesUnknownTypeToFallback() throws Exception {
    Payment payment = new Payment(
            "PAY-99", "WALLET", new BigDecimal("10.00"));

    when(fallbackProcessor.process(payment))
            .thenReturn(PaymentResult.rejected(
                    "PAY-99", "WALLET", "UNSUPPORTED_TYPE"));

    ItemProcessor<?, ? extends PaymentResult> selected =
            classifier.classify(payment);

    assertSame(fallbackProcessor, selected);
    assertEquals(
            "REJECTED",
            ((ItemProcessor<Payment, PaymentResult>) selected).process(payment).status());
}
~~~

Ví dụ này minh họa lựa chọn delegate và kết quả fallback. Trong test thực tế, có thể dùng helper có kiểu generic phù hợp để tránh cast không cần thiết.

## 22. Kiểm thử composite và Step integration

Unit test classifier không chứng minh Step xử lý skip/filter/transaction đúng. Nên có integration test cho:

- Fallback được gọi và output rejected được ghi.
- Fail-fast exception làm Step FAILED.
- Exception skippable làm skip count tăng đúng.
- Filter làm filter count tăng và writer không nhận item.
- Writer quarantine thất bại làm chunk rollback theo transaction.
- Retry tạm thời không tạo duplicate.
- Restart giữ nguyên route map và policy version.

Ví dụ dữ liệu:

~~~text
PAY-01 CARD       -> CardPaymentProcessor
PAY-02 TRANSFER   -> TransferPaymentProcessor
PAY-03 WALLET     -> Fallback/Quarantine
PAY-04 null       -> MissingType policy
PAY-05 CASH       -> CashPaymentProcessor
~~~

Sau khi chạy Job, đối chiếu:

- Tổng số input.
- Số output accepted.
- Số output rejected/quarantine.
- Filter count.
- Skip count theo giai đoạn.
- Số record thực sự được commit.

Không chỉ assert Job COMPLETED. Một Job có thể COMPLETED nhưng đã filter hoặc quarantine nhiều item; cần kiểm tra đó có phải kết quả nghiệp vụ mong muốn hay không.

## 23. Khi nào nên tách route thành Step riêng?

Nếu các loại item không chỉ khác processor mà còn khác transaction, retry/skip policy, output resource hoặc lịch chạy, classifier trong cùng một Step có thể không còn là cấu trúc phù hợp.

Cân nhắc tách Step khi:

- Mỗi loại có database hoặc transaction manager khác nhau.
- Mỗi loại cần retry/skip limit riêng.
- Một loại cần file output hoặc schema riêng.
- Cần restart từng loại độc lập.
- Có thể phân loại input trước thành các staging stream riêng.
- Cần báo cáo trạng thái riêng theo loại.

ClassifierCompositeItemProcessor chỉ định tuyến processor bên trong một StepExecution. Nó không tạo StepExecution hoặc transaction boundary mới cho từng nhánh.

Nếu các nhánh vẫn chia sẻ reader, writer và transaction policy, composite thường giữ cấu hình gọn. Nếu mỗi nhánh có lifecycle khác nhau, tách Step giúp vận hành và restart rõ ràng hơn.

## 24. Các lỗi thường gặp

**Trả null từ classifier:** composite không có delegate để gọi và có thể ném NullPointerException. Trả fallback hoặc ném exception có nghĩa.

**Coi null delegate là filter:** filter là khi một ItemProcessor hợp lệ được gọi và trả null.

**Dùng fallback cho lỗi cấu hình:** route bị thiếu do deployment có thể bị che giấu như một item không hỗ trợ. Validate registry khi khởi tạo.

**Dùng một fallback xử lý mọi loại unknown:** type mới, typo và field thiếu có thể cần policy khác nhau. Phân loại lý do no-match.

**Bỏ qua type mới mà không audit:** Job vẫn hoàn tất nhưng dữ liệu có thể bị mất. Ghi rejected output hoặc fail theo contract.

**Chuẩn hóa chuỗi quá rộng:** alias không được định nghĩa có thể làm hai loại nghiệp vụ khác nhau bị nhập thành một. Khai báo alias tường minh.

**Dùng skip cho lỗi route cố định:** retry/skip không sửa được registry thiếu hoặc contract sai. Phân biệt lỗi cấu hình và lỗi dữ liệu.

**Retry unknown type không giới hạn:** cùng item thường vẫn không khớp. Retry chỉ cho lỗi lookup tạm thời.

**Nhầm no-match với lỗi trong delegate:** classifier chưa chọn được processor là lỗi định tuyến; delegate đã chọn nhưng xử lý thất bại là lỗi process.

**Không kiểm thử null/blank:** classifier có thể ném NullPointerException hoặc route nhầm.

**Không tính fallback vào đối soát:** rejected output vẫn có thể là write thành công; skip/filter/reject cần được báo cáo riêng.

## Kết luận

Khi item không khớp classifier, ClassifierCompositeItemProcessor không tự chọn hành vi thay thế. Classifier phải trả về một delegate hợp lệ hoặc ném exception có ý nghĩa; trả null thường dẫn tới lỗi khi composite gọi delegate. Hãy quyết định rõ no-match phải fail Step, chuyển sang fallback/quarantine hay được filter có chủ đích. Phân biệt no-match với delegate trả null và với skip exception để audit, metrics và retry chính xác. Chuẩn hóa route key một cách tường minh, xác thực registry bắt buộc lúc khởi tạo, giữ classifier xác định qua retry/restart và kiểm thử cả unit lẫn Step integration. Nếu mỗi nhánh có transaction hoặc lifecycle khác nhau, cân nhắc tách thành Step riêng thay vì để một classifier che giấu các khác biệt vận hành.
