# Validation processor

Trong Spring Batch, ItemProcessor là nơi thường dùng để kiểm tra dữ liệu đầu vào, chuẩn hóa giá trị, áp dụng quy tắc nghiệp vụ và chuyển đổi item sang kiểu dữ liệu phù hợp cho writer. Một validation processor giúp phát hiện record không hợp lệ trước khi ghi vào hệ thống đích, đồng thời quyết định cách xử lý lỗi theo chính sách của Job.

Validation trong batch có một điểm cần phân biệt rõ: item không hợp lệ không phải lúc nào cũng có nghĩa là Job phải dừng. Có trường hợp dữ liệu cần được bỏ qua có chủ đích, có trường hợp cần ghi vào reject output để điều tra, và có trường hợp phải làm Step thất bại vì dữ liệu hoặc cấu hình không thể tiếp tục an toàn.

Ba kết quả phổ biến:

- **Hợp lệ:** processor trả về item đã được xác thực hoặc chuyển đổi để writer xử lý.
- **Filter có chủ đích:** processor trả về null; Spring Batch không chuyển item đó tới writer.
- **Không hợp lệ:** processor ném exception; Step áp dụng skip, retry hoặc fail theo cấu hình.

Không nên dùng null để che giấu validation error. Null có nghĩa item bị filter theo logic xử lý, còn exception biểu thị có lỗi cần được xử lý theo policy. Nếu cần lưu record lỗi, phải có reject flow hoặc cơ chế audit phù hợp.

## 1. Vai trò của validation processor

Một pipeline batch thường có dạng:

~~~text
Input file / Database / Message
              |
              v
          ItemReader
              |
              v
       ValidationProcessor
              |
              v
       BusinessProcessor
              |
              v
          ItemWriter
              |
              v
        Target database
~~~

Validation processor kiểm tra cấu trúc và quy tắc dữ liệu trước khi các bước sau sử dụng item. Ví dụ với đơn hàng:

- orderId phải có giá trị và lớn hơn 0.
- customerCode không được rỗng.
- totalAmount phải lớn hơn hoặc bằng 0.
- currency phải nằm trong danh sách được hỗ trợ.
- orderDate không được nằm trong tương lai nếu nghiệp vụ không cho phép.
- quantity phải lớn hơn 0.

Validation nên diễn ra càng sớm càng tốt sau khi đọc và parse dữ liệu. Nếu item không hợp lệ, phát hiện trước khi gọi service bên ngoài hoặc ghi database sẽ giảm chi phí xử lý và tránh side effect không cần thiết.

Tuy nhiên, validation processor không nhất thiết phải chứa mọi quy tắc. Nên phân chia:

| Nhóm kiểm tra | Ví dụ | Nơi thường phù hợp |
| --- | --- | --- |
| Cấu trúc/kiểu dữ liệu | JSON field là number, ngày parse được | Reader hoặc parser |
| Field-level validation | Mã khách hàng không rỗng | DTO/Bean Validation |
| Cross-field validation | Ngày kết thúc sau ngày bắt đầu | Class-level constraint hoặc validator |
| Business validation | Khách hàng đang hoạt động, hạn mức còn đủ | Domain service hoặc processor |
| External validation | Mã thuế được dịch vụ đối tác xác nhận | Service riêng có timeout/retry |

Không đẩy mọi lỗi parse vào processor nếu reader chưa thể tạo object. Cũng không đặt mọi quy tắc nghiệp vụ vào annotation nếu quy tắc cần database, thời gian hoặc hệ thống ngoài.

## 2. Thiết kế DTO đầu vào

Ví dụ dữ liệu đơn hàng được đọc từ CSV hoặc JSON:

~~~java
public record OrderInput(
        Long orderId,
        String customerCode,
        BigDecimal totalAmount,
        String currency,
        LocalDate orderDate,
        Integer quantity) {
}
~~~

DTO nên biểu diễn đúng dữ liệu nhận được từ nguồn. Dùng kiểu wrapper như Long và Integer khi cần phân biệt field thiếu với giá trị 0. Dùng BigDecimal cho tiền để tránh sai số dấu phẩy động.

Giữ DTO đầu vào riêng với entity database nếu schema nguồn và schema đích khác nhau. Như vậy, validation kiểm tra contract của nguồn trước khi mapping sang model nội bộ.

Ví dụ:

~~~java
public record ValidatedOrder(
        long orderId,
        String customerCode,
        BigDecimal totalAmount,
        Currency currency,
        LocalDate orderDate,
        int quantity) {
}
~~~

ValidatedOrder biểu diễn dữ liệu đã qua kiểm tra và chuẩn hóa. Dùng một kiểu riêng giúp các processor tiếp theo không phải liên tục kiểm tra null hoặc parse lại currency.

Không nên tạo một DTO tên ValidatedOrder rồi vẫn cho phép mọi field null hoặc giữ nguyên các giá trị thô chưa chuẩn hóa. Tên kiểu nên phản ánh invariant mà ứng dụng thực sự bảo đảm.

## 3. Dùng Jakarta Bean Validation

Jakarta Bean Validation cung cấp annotation để khai báo constraint trên field, property, parameter hoặc class. Spring Boot thường tích hợp Hibernate Validator làm provider.

Các annotation thường dùng:

| Annotation | Ý nghĩa |
| --- | --- |
| @NotNull | Giá trị không được null |
| @NotBlank | Chuỗi không null, không rỗng và có ký tự không phải khoảng trắng |
| @NotEmpty | Chuỗi/collection/map không được rỗng |
| @Positive | Số phải lớn hơn 0 |
| @PositiveOrZero | Số phải lớn hơn hoặc bằng 0 |
| @Min / @Max | Giới hạn số nguyên |
| @DecimalMin / @DecimalMax | Giới hạn số decimal |
| @Size | Độ dài chuỗi hoặc kích thước collection |
| @Pattern | Chuỗi phải khớp regular expression |
| @Email | Chuỗi có định dạng email phù hợp |
| @Past / @Future | Ngày hoặc thời điểm ở quá khứ/tương lai |

Ví dụ DTO:

~~~java
public class OrderInput {

    @NotNull(message = "orderId is required")
    @Positive(message = "orderId must be positive")
    private Long orderId;

    @NotBlank(message = "customerCode is required")
    @Size(max = 30, message = "customerCode is too long")
    private String customerCode;

    @NotNull(message = "totalAmount is required")
    @DecimalMin(value = "0.00", message = "totalAmount must not be negative")
    private BigDecimal totalAmount;

    @NotBlank(message = "currency is required")
    @Pattern(regexp = "VND|USD|EUR", message = "unsupported currency")
    private String currency;

    @NotNull(message = "orderDate is required")
    private LocalDate orderDate;

    @NotNull(message = "quantity is required")
    @Positive(message = "quantity must be positive")
    private Integer quantity;

    // getters and setters
}
~~~

Annotation mô tả constraint, nhưng không tự chạy chỉ vì object được tạo. Cần gọi Validator.validate() hoặc dùng cơ chế validation được framework kích hoạt tại đúng boundary.

### @NotNull khác @NotBlank

Với String:

- @NotNull chỉ cấm null.
- @NotEmpty cấm null và chuỗi rỗng, nhưng chuỗi chỉ có khoảng trắng vẫn có thể hợp lệ.
- @NotBlank cấm null, chuỗi rỗng và chuỗi chỉ có khoảng trắng.

Chọn constraint theo contract dữ liệu. Với mã khách hàng, @NotBlank thường phù hợp hơn @NotNull.

### Constraint trên wrapper type

Nếu field là Integer và có thể null, @Positive chỉ kiểm tra giá trị khi có mặt; nó không thay thế @NotNull. Nếu field bắt buộc, kết hợp cả hai annotation.

## 4. Tạo Validator và gọi trong processor

Có thể inject jakarta.validation.Validator vào processor:

~~~java
public class OrderValidationProcessor
        implements ItemProcessor<OrderInput, ValidatedOrder> {

    private final Validator validator;

    public OrderValidationProcessor(Validator validator) {
        this.validator = validator;
    }

    @Override
    public ValidatedOrder process(OrderInput input) {
        Set<ConstraintViolation<OrderInput>> violations =
                validator.validate(input);

        if (!violations.isEmpty()) {
            throw new InvalidOrderException(
                    input == null ? null : input.getOrderId(),
                    violations);
        }

        return new ValidatedOrder(
                input.getOrderId(),
                input.getCustomerCode().trim(),
                input.getTotalAmount(),
                Currency.getInstance(input.getCurrency()),
                input.getOrderDate(),
                input.getQuantity());
    }
}
~~~

Ví dụ dùng class có getter để minh họa Bean Validation. Nếu DTO là record, provider Jakarta Validation hiện đại có thể hỗ trợ constraint trên record component; cách truy cập property và version provider cần khớp dự án.

Đăng ký Validator trong Spring:

~~~java
@Bean
public LocalValidatorFactoryBean validator() {
    return new LocalValidatorFactoryBean();
}
~~~

Spring Boot có thể tự cấu hình Validator khi dependency validation có mặt. Trong trường hợp đó, có thể inject jakarta.validation.Validator trực tiếp.

### Không tạo ValidatorFactory cho từng item

Không nên gọi Validation.buildDefaultValidatorFactory() trong mỗi lần process(). Việc tạo factory/provider lặp lại tốn tài nguyên và có thể không đóng factory đúng cách.

Tạo Validator một lần ở application context rồi inject vào processor. Validator được thiết kế để dùng lại sau khi cấu hình hoàn tất.

### Xử lý input null

Bean Validation có thể validate object graph, nhưng validator.validate(null) không phải cách xử lý null object đầu vào. Nếu reader hoặc caller có thể truyền null, kiểm tra trước:

~~~java
if (input == null) {
    throw new InvalidOrderException(
            null,
            "Input order must not be null");
}
~~~

Trong Spring Batch, reader thường dùng null để báo EOF và không gọi processor cho item đó. Dù vậy, unit test hoặc custom caller vẫn có thể truyền null trực tiếp.

## 5. Tạo exception validation có cấu trúc

Không nên chỉ ném IllegalArgumentException với một message chung nếu cần phân loại, log, reject hoặc thống kê lỗi.

Có thể tạo exception mang business key và danh sách lỗi:

~~~java
public class InvalidOrderException extends RuntimeException {

    private final Long orderId;
    private final List<String> violations;

    public InvalidOrderException(
            Long orderId,
            Collection<? extends ConstraintViolation<?>> violations) {
        super("Order validation failed: " + violations.size()
                + " violation(s)");
        this.orderId = orderId;
        this.violations = violations.stream()
                .map(v -> v.getPropertyPath() + ": " + v.getMessage())
                .sorted()
                .toList();
    }

    public InvalidOrderException(Long orderId, String message) {
        super(message);
        this.orderId = orderId;
        this.violations = List.of(message);
    }

    public Long getOrderId() {
        return orderId;
    }

    public List<String> getViolations() {
        return violations;
    }
}
~~~

Exception có thể cung cấp:

- Business key hoặc source record ID.
- Field/property path.
- Mã lỗi ổn định.
- Message dành cho người vận hành.
- Danh sách nhiều constraint violations.
- Nguyên nhân gốc nếu lỗi phát sinh từ hệ thống khác.

Không đưa toàn bộ payload hoặc dữ liệu nhạy cảm vào exception message. Log chỉ nên chứa những field cần thiết để điều tra và phải tuân theo chính sách bảo mật dữ liệu.

## 6. Gom nhiều validation errors trong một lần

Validator.validate() trả về tập hợp ConstraintViolation. Có thể báo nhiều lỗi cùng lúc thay vì dừng ở field đầu tiên.

Ví dụ:

~~~java
Set<ConstraintViolation<OrderInput>> violations =
        validator.validate(input);

if (!violations.isEmpty()) {
    List<String> messages = violations.stream()
            .map(v -> v.getPropertyPath() + ": " + v.getMessage())
            .sorted()
            .toList();

    throw new InvalidOrderException(
            input.getOrderId(),
            messages);
}
~~~

Việc gom lỗi giúp người dùng sửa nhiều field trong một lần. Dùng sort để thứ tự lỗi ổn định trong log và test; không phụ thuộc thứ tự iteration của Set.

Không nên gom lỗi bằng cách nối chuỗi không có cấu trúc rồi để hệ thống downstream phải parse lại. Giữ property path và error code thành các field riêng nếu cần báo cáo hoặc phân tích.

## 7. Cross-field validation

Một số quy tắc không thể kiểm tra trên một field riêng lẻ:

- startDate phải trước endDate.
- currency phải phù hợp với quốc gia.
- discount không được lớn hơn subtotal.
- loại khách hàng BUSINESS yêu cầu taxCode.
- tổng số lượng dòng phải khớp order quantity.

Có thể viết class-level constraint:

~~~java
@ValidDateRange
public class BookingInput {

    private LocalDate startDate;
    private LocalDate endDate;

    // getters and setters
}
~~~

Annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "endDate must not be before startDate";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingInput> {

    @Override
    public boolean isValid(
            BookingInput value,
            ConstraintValidatorContext context) {

        if (value == null
                || value.getStartDate() == null
                || value.getEndDate() == null) {
            return true;
        }

        return !value.getEndDate().isBefore(value.getStartDate());
    }
}
~~~

Validator trả true khi field liên quan đang null vì các constraint @NotNull riêng sẽ chịu trách nhiệm báo lỗi thiếu dữ liệu. Cách này tránh tạo hai lỗi cho cùng một nguyên nhân.

Nếu muốn thông báo cụ thể theo property, có thể disable default violation và thêm violation vào property path endDate. Khi làm vậy, test cả trường hợp null, cùng ngày, ngày đảo ngược và ngày hợp lệ.

## 8. Business validation trong processor

Bean Validation phù hợp với constraint trên object. Quy tắc cần domain context nên được đặt trong service nghiệp vụ.

Ví dụ kiểm tra khách hàng đang hoạt động và còn hạn mức:

~~~java
public class OrderBusinessValidationProcessor
        implements ItemProcessor<ValidatedOrder, ValidatedOrder> {

    private final CustomerService customerService;
    private final CreditLimitService creditLimitService;

    public OrderBusinessValidationProcessor(
            CustomerService customerService,
            CreditLimitService creditLimitService) {
        this.customerService = customerService;
        this.creditLimitService = creditLimitService;
    }

    @Override
    public ValidatedOrder process(ValidatedOrder order) {
        Customer customer =
                customerService.findByCode(order.customerCode())
                        .orElseThrow(() ->
                                new InvalidOrderException(
                                        order.orderId(),
                                        "Customer does not exist"));

        if (!customer.isActive()) {
            throw new InvalidOrderException(
                    order.orderId(),
                    "Customer is inactive");
        }

        if (!creditLimitService.hasAvailableCredit(
                customer.id(), order.totalAmount())) {
            throw new InvalidOrderException(
                    order.orderId(),
                    "Credit limit exceeded");
        }

        return order;
    }
}
~~~

Đây là ví dụ minh họa; việc kiểm tra hạn mức và reserve hạn mức có thể cần một transaction nghiệp vụ riêng. Một phép kiểm tra read-only không bảo đảm hạn mức vẫn còn khi writer thực hiện sau đó nếu có giao dịch đồng thời.

### Validation và race condition

Giả sử hai Job cùng kiểm tra hạn mức còn 100 triệu. Mỗi Job có đơn hàng 80 triệu. Cả hai có thể đọc cùng một trạng thái và đều kết luận hợp lệ, trong khi tổng cam kết vượt hạn mức.

Nếu quy tắc cần bảo đảm tại thời điểm ghi, hãy thực hiện check-and-reserve trong transaction có locking, optimistic version hoặc một câu lệnh cập nhật có điều kiện. Processor validation chỉ có thể phát hiện trạng thái tại thời điểm kiểm tra; nó không thay thế constraint hoặc concurrency control ở database.

## 9. Validation và chuẩn hóa dữ liệu

Validation và normalization liên quan nhưng khác nhau:

- Validation xác định dữ liệu có đáp ứng contract hay không.
- Normalization chuyển dữ liệu hợp lệ về một dạng chuẩn.

Ví dụ:

~~~java
String normalizedCode = input.getCustomerCode().trim().toUpperCase(Locale.ROOT);
~~~

Trước khi chuẩn hóa, cần xác định contract có cho phép khoảng trắng đầu/cuối hay chữ thường không. Không tự động sửa giá trị có thể mang ý nghĩa nghiệp vụ.

Một processor có thể thực hiện:

1. Kiểm tra object và field bắt buộc.
2. Chuẩn hóa whitespace/case theo contract.
3. Validate lại các invariant sau normalization nếu cần.
4. Chuyển sang DTO nội bộ bất biến.

Ví dụ, mã tiền tệ có thể được trim và chuyển uppercase, sau đó parse bằng Currency.getInstance(). Nếu mã không được hỗ trợ, ném InvalidOrderException có mã lỗi rõ ràng.

Không dùng normalization để che giấu dữ liệu sai. Nếu chuỗi "1,234" có thể mang nghĩa khác nhau theo locale, phải có quy tắc định dạng rõ ràng trước khi parse.

## 10. Validation processor và filter

Trong Spring Batch, processor trả null có nghĩa item được filter và không chuyển tới writer:

~~~java
public class IgnoreCancelledOrderProcessor
        implements ItemProcessor<OrderInput, OrderInput> {

    @Override
    public OrderInput process(OrderInput input) {
        if (input.status() == OrderStatus.CANCELLED) {
            return null;
        }
        return input;
    }
}
~~~

Đây là filter có chủ đích nếu nghiệp vụ quy định đơn hàng CANCELLED không thuộc tập xử lý.

Không viết:

~~~java
if (input.getOrderId() == null) {
    return null;
}
~~~

nếu thiếu orderId là lỗi dữ liệu cần điều tra. Cách này làm item biến mất khỏi pipeline mà không tạo skip count hay reject record.

### Phân biệt filter và validation failure

| Tình huống | Kết quả phù hợp |
| --- | --- |
| Item bị loại theo tiêu chí nghiệp vụ bình thường | Trả null |
| Field bắt buộc thiếu hoặc sai định dạng | Ném validation exception |
| Item không được hỗ trợ nhưng cần giữ lại | Reject/DLQ hoặc exception được skip |
| Hệ thống ngoài tạm thời không phản hồi | Exception transient để retry |
| Cấu hình hoặc schema không thể xử lý an toàn | Fail Step/Job |

Filter thường không được tính là skip. Nếu cần thống kê số item bị filter, dùng filter listener hoặc counter có phạm vi StepExecution phù hợp.

## 11. Validation processor với skip policy

Nếu dữ liệu sai có thể bỏ qua và xử lý tiếp record khác, cấu hình Step fault-tolerant:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, ValidatedOrder> processor,
        ItemWriter<ValidatedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, ValidatedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(100)
            .build();
}
~~~

Trong ví dụ, validation error được coi là lỗi record có thể skip. Nếu tổng số skip vượt giới hạn, Step sẽ thất bại. Cấu hình skip cần dựa trên yêu cầu nghiệp vụ; không nên skip mọi RuntimeException.

### Skip trong processor

Khi processor ném InvalidOrderException và exception được cấu hình skip:

- Item lỗi được bỏ qua.
- Các item còn lại trong chunk có thể tiếp tục theo fault-tolerant behavior.
- Skip count được cập nhật.
- SkipListener có thể nhận item và exception để ghi nhận reject.

Một số lỗi phát sinh khi đọc hoặc ghi có semantics khác với lỗi ở processor. Hãy phân loại exception theo stage để tránh skip nhầm lỗi hạ tầng hoặc lỗi ghi dữ liệu.

### Retry khác skip

Retry phù hợp với lỗi có khả năng tự hết, chẳng hạn timeout ngắn hoặc deadlock. Validation error thường là lỗi dữ liệu ổn định; retry cùng input thường không làm dữ liệu hợp lệ hơn.

Ví dụ:

~~~java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(100)
.retry(TransientDataAccessException.class)
.retryLimit(3)
~~~

Không đưa InvalidOrderException vào retry policy nếu không có một bước sửa dữ liệu trước lần thử tiếp theo.

## 12. Reject record và SkipListener

Skip giúp Step tiếp tục, nhưng bỏ qua item không tự động lưu lại raw record hoặc lý do lỗi. Nếu cần audit, có thể dùng SkipListener:

~~~java
public class OrderSkipListener
        implements SkipListener<OrderInput, ValidatedOrder> {

    private final RejectRecordService rejectRecordService;

    public OrderSkipListener(RejectRecordService rejectRecordService) {
        this.rejectRecordService = rejectRecordService;
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable throwable) {

        if (throwable instanceof InvalidOrderException invalid) {
            rejectRecordService.record(
                    item.orderId(),
                    invalid.getViolations());
        }
    }

    @Override
    public void onSkipInRead(Throwable throwable) {
        // Không có item nếu lỗi xảy ra trước khi reader tạo object.
    }

    @Override
    public void onSkipInWrite(
            ValidatedOrder item,
            Throwable throwable) {
        // Xử lý lỗi writer theo policy riêng.
    }
}
~~~

Đăng ký listener:

~~~java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(100)
.listener(orderSkipListener)
~~~

SkipListener có callback riêng cho read, process và write. Với lỗi validation trong processor, callback tương ứng là onSkipInProcess.

### Ghi reject có transaction

Nếu rejectRecordService ghi vào cùng database, hãy xác định transaction mà callback sử dụng trong phiên bản Spring Batch đang chạy. Skip listener được thiết kế để thông báo item bị skip; callback thường được gọi ngay trước commit chunk để tránh ghi reject lặp khi retry transaction.

Tuy vậy, không nên giả định một lời gọi API hoặc ghi file trong listener sẽ rollback cùng transaction. Nếu reject output nằm ở hệ thống ngoài, hãy dùng outbox hoặc cơ chế idempotent. Nếu reject table phải commit cùng batch metadata, dùng cùng transaction manager và kiểm thử integration.

### Không làm mất raw record

Nếu reader parse dữ liệu thành DTO rồi mới validation, có thể đã mất biểu diễn nguyên bản của record. Nếu yêu cầu điều tra chính xác, giữ source line, file name, line number hoặc message ID trong DTO metadata.

Không lưu toàn bộ raw payload nhạy cảm vào log. Reject store cần có access control, retention và masking phù hợp.

## 13. Một cách khác: biểu diễn kết quả validation

Trong một số hệ thống, muốn ghi cả item hợp lệ và item lỗi trong cùng một luồng mà không dùng skip. Có thể tạo wrapper:

~~~java
public record ValidationResult<T>(
        T original,
        T validValue,
        List<ValidationError> errors) {

    public boolean isValid() {
        return errors.isEmpty();
    }
}
~~~

Processor không ném exception cho lỗi nghiệp vụ có thể lưu lại:

~~~java
public class OrderValidationResultProcessor
        implements ItemProcessor<OrderInput, ValidationResult<ValidatedOrder>> {

    private final Validator validator;

    @Override
    public ValidationResult<ValidatedOrder> process(OrderInput input) {
        Set<ConstraintViolation<OrderInput>> violations =
                validator.validate(input);

        if (!violations.isEmpty()) {
            List<ValidationError> errors = violations.stream()
                    .map(v -> new ValidationError(
                            v.getPropertyPath().toString(),
                            "INVALID_FIELD",
                            v.getMessage()))
                    .toList();

            return new ValidationResult<>(null, null, errors);
        }

        return new ValidationResult<>(
                null,
                toValidatedOrder(input),
                List.of());
    }
}
~~~

Writer có thể tách item hợp lệ và reject record:

~~~java
public class ValidationResultWriter
        implements ItemWriter<ValidationResult<ValidatedOrder>> {

    private final ItemWriter<ValidatedOrder> validWriter;
    private final RejectWriter rejectWriter;

    @Override
    public void write(
            Chunk<? extends ValidationResult<ValidatedOrder>> chunk)
            throws Exception {

        List<ValidatedOrder> valid = new ArrayList<>();
        List<RejectRecord> rejected = new ArrayList<>();

        for (ValidationResult<ValidatedOrder> result : chunk) {
            if (result.isValid()) {
                valid.add(result.validValue());
            } else {
                rejected.add(toRejectRecord(result));
            }
        }

        if (!valid.isEmpty()) {
            validWriter.write(new Chunk<>(valid));
        }

        if (!rejected.isEmpty()) {
            rejectWriter.write(rejected);
        }
    }
}
~~~

Đây là một pattern khi lỗi validation là kết quả nghiệp vụ cần lưu lại, không phải exception cần làm Step skip. Writer cần xử lý hai output theo transaction strategy rõ ràng. Nếu validWriter commit riêng rồi rejectWriter thất bại, hai output có thể lệch; hãy dùng cùng transaction database hoặc outbox/staging khi cần.

Wrapper phải giữ original item hoặc source metadata nếu reject record cần nội dung đầu vào. Ví dụ trên rút gọn để tập trung vào luồng.

## 14. Validation groups

Một DTO có thể được dùng ở nhiều giai đoạn với yêu cầu khác nhau. Jakarta Validation groups cho phép chạy một tập constraint theo từng nhóm.

Khai báo group:

~~~java
public interface ImportChecks {
}

public interface ApprovalChecks {
}
~~~

DTO:

~~~java
public class PaymentInput {

    @NotNull(groups = ImportChecks.class)
    private String paymentId;

    @NotNull(groups = ImportChecks.class)
    @Positive(groups = ImportChecks.class)
    private BigDecimal amount;

    @NotBlank(groups = ApprovalChecks.class)
    private String approver;
}
~~~

Processor gọi group tương ứng:

~~~java
Set<ConstraintViolation<PaymentInput>> violations =
        validator.validate(input, ImportChecks.class);
~~~

Ở Step phê duyệt:

~~~java
validator.validate(input, ApprovalChecks.class);
~~~

Nếu cần chạy nhiều group theo thứ tự và dừng khi group trước có lỗi, Jakarta Validation hỗ trợ GroupSequence. Cấu hình group sequence cần cẩn thận vì thứ tự group ảnh hưởng kết quả.

Không dùng validation groups để thay thế các DTO riêng khi hai giai đoạn có contract quá khác nhau. Nếu một object tích lũy nhiều trạng thái và constraint theo giai đoạn khó hiểu, tạo kiểu dữ liệu riêng cho từng boundary thường rõ hơn.

## 15. Custom constraint và validator

Khi quy tắc được tái sử dụng ở nhiều DTO, có thể tạo annotation riêng:

~~~java
@Target({
        ElementType.FIELD,
        ElementType.PARAMETER,
        ElementType.ANNOTATION_TYPE
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = SupportedCurrencyValidator.class)
public @interface SupportedCurrency {
    String message() default "currency is not supported";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
public class SupportedCurrencyValidator
        implements ConstraintValidator<SupportedCurrency, String> {

    private static final Set<String> SUPPORTED =
            Set.of("VND", "USD", "EUR");

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context) {
        return value == null || SUPPORTED.contains(value);
    }
}
~~~

Validator trả true cho null để @NotBlank hoặc @NotNull kiểm tra riêng. Cách này giúp một field thiếu không tạo thêm lỗi "unsupported currency".

ConstraintValidator có thể được provider sử dụng nhiều lần và trong một số cấu hình đồng thời. Không giữ mutable state theo từng item trong validator. Nếu validator cần dependency Spring, dùng integration giữa Spring và Bean Validation provider được cấu hình đúng; không tự lookup ApplicationContext trong isValid().

## 16. Validation theo thời gian

Các constraint như @Past và @Future phụ thuộc clock hiện tại. Test có thể thay đổi theo ngày chạy hoặc timezone nếu không kiểm soát.

Với quy tắc nghiệp vụ cần thời gian xác định, có thể inject Clock vào validator/service:

~~~java
public class OrderDatePolicy {

    private final Clock clock;

    public OrderDatePolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isAllowed(LocalDate orderDate) {
        LocalDate today = LocalDate.now(clock);
        return !orderDate.isAfter(today);
    }
}
~~~

Test:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-11-15T10:00:00Z"),
        ZoneOffset.UTC);
~~~

Nếu dùng Jakarta Validator cho @Past/@Future, có thể cấu hình ClockProvider để validation dùng clock xác định. Điều này hữu ích cho test và batch chạy theo business date.

Phải phân biệt ngày theo UTC với business timezone. Một orderDate ở đầu ngày địa phương có thể khác ngày UTC. Hãy truyền ZoneId hoặc business date rõ ràng thay vì dựa vào timezone mặc định của JVM.

## 17. Validation bên ngoài và lỗi tạm thời

Một số quy tắc cần gọi dịch vụ khác:

- Kiểm tra mã khách hàng với hệ thống CRM.
- Xác minh mã thuế với dịch vụ đối tác.
- Kiểm tra tài khoản còn hoạt động.
- Xác nhận sản phẩm còn được phép bán.

Không nên nhồi tất cả external validation vào Jakarta ConstraintValidator. Một service riêng thường dễ kiểm soát timeout, retry, metrics và lỗi hạ tầng hơn:

~~~java
public class CustomerValidationProcessor
        implements ItemProcessor<ValidatedOrder, ValidatedOrder> {

    private final CustomerRegistryClient client;

    @Override
    public ValidatedOrder process(ValidatedOrder order) {
        RegistryResult result =
                client.checkCustomer(order.customerCode());

        if (result.isTemporarilyUnavailable()) {
            throw new ExternalValidationUnavailableException(
                    order.orderId());
        }

        if (!result.isValid()) {
            throw new InvalidOrderException(
                    order.orderId(),
                    "Customer registry rejected customer code");
        }

        return order;
    }
}
~~~

Phân biệt:

- Registry trả kết quả không hợp lệ: lỗi dữ liệu ổn định, thường skip/reject.
- Registry timeout hoặc unavailable: lỗi tạm thời, có thể retry có giới hạn.
- Authentication/configuration error: thường fail nhanh và cảnh báo.

### Không gọi dịch vụ ngoài quá nhiều lần

Nếu nhiều order dùng cùng customerCode, có thể cache kết quả trong phạm vi an toàn hoặc bulk lookup. Nhưng cache cần TTL, invalidation và concurrency policy rõ ràng.

Không cache một kết quả validation lâu hơn thời gian dữ liệu có thể thay đổi nếu quy tắc cần trạng thái hiện tại. Cũng không giữ cache mutable toàn cục nếu nhiều Job/tenant có thể dùng dữ liệu khác nhau.

### Validation không nên có side effect

Một thao tác tên validate nên quan sát và quyết định, không reserve tài nguyên hoặc thay đổi trạng thái nghiệp vụ. Nếu cần reserve hạn mức, inventory hoặc slot, hãy gọi command/service có semantics transaction riêng và thiết kế idempotency.

Processor có thể được gọi lại khi retry. Side effect trong processor có thể xảy ra nhiều lần.

## 18. Đặt validation ở reader, processor hay writer?

Không phải mọi validation đều thuộc processor:

| Vị trí | Phù hợp với | Lưu ý |
| --- | --- | --- |
| Reader/parser | Cú pháp file, kiểu dữ liệu không parse được, cấu trúc record | Lỗi có thể xảy ra trước khi có item |
| Processor | Quy tắc dữ liệu, cross-field, normalization, business decision | Exception có thể được skip/retry theo Step |
| Writer/database | Unique constraint, foreign key, invariant cần bảo vệ tại thời điểm ghi | Database là lớp bảo vệ cuối cùng |
| Service/domain layer | Quy tắc dùng chung giữa batch và ứng dụng khác | Phải xác định transaction boundary |

Ví dụ, email sai format có thể kiểm tra trong DTO validation. Nhưng email đã đăng ký hay chưa có thể cần database. Mã khách hàng có còn active tại thời điểm ghi có thể cần locking hoặc constraint phù hợp.

Không chỉ validate ở processor rồi tin rằng dữ liệu không thể thay đổi trước khi commit. Database constraint vẫn cần thiết cho tính đúng đắn khi có nhiều transaction đồng thời.

## 19. Validation và composite processor

Có thể ghép validation processor với các processor khác:

~~~text
OrderInput
    |
    v
ValidationProcessor
    |
    v
NormalizationProcessor
    |
    v
EnrichmentProcessor
    |
    v
CalculationProcessor
    |
    v
OrderOutput
~~~

Ví dụ:

~~~java
@Bean
public CompositeItemProcessor<OrderInput, OrderOutput> orderProcessor(
        ItemProcessor<OrderInput, ValidatedOrder> validationProcessor,
        ItemProcessor<ValidatedOrder, NormalizedOrder> normalizationProcessor,
        ItemProcessor<NormalizedOrder, EnrichedOrder> enrichmentProcessor,
        ItemProcessor<EnrichedOrder, OrderOutput> calculationProcessor) {

    return new CompositeItemProcessorBuilder<OrderInput, OrderOutput>()
            .delegates(
                    validationProcessor,
                    normalizationProcessor,
                    enrichmentProcessor,
                    calculationProcessor)
            .build();
}
~~~

Mỗi processor có kiểu input/output rõ ràng. Nếu validation ném exception, các processor sau không nhận item đó. Nếu processor trả null, item bị filter và chuỗi processor không tiếp tục cho item đó.

Giữ validation ở đầu chuỗi nếu các bước sau tốn chi phí hoặc gọi hệ thống ngoài. Tuy nhiên, nếu normalization cần chạy trước để chuẩn hóa dữ liệu rồi mới validate, hãy thể hiện thứ tự đó rõ ràng và kiểm tra rằng normalization không biến dữ liệu sai thành dữ liệu có vẻ hợp lệ.

## 20. Skip policy và giới hạn lỗi

Skip limit giúp Job tiếp tục khi có một số record lỗi, nhưng vẫn fail nếu số lỗi vượt ngưỡng.

~~~java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(50)
~~~

Nếu có nhiều loại exception:

~~~java
.skip(InvalidOrderException.class)
.skip(UnsupportedCurrencyException.class)
.noSkip(ExternalValidationUnavailableException.class)
.skipLimit(50)
~~~

Các rule cần được đọc cùng thứ tự và semantics của skip policy trong version Spring Batch đang dùng. Nếu exception subclass được cấu hình ở cả skip và noSkip, hãy kiểm tra precedence thực tế; tránh cấu hình chồng lấn gây khó hiểu.

### Skip limit là giới hạn tổng

Skip limit áp dụng cho số lần skip theo policy của Step, bao gồm các stage được hỗ trợ như read, process và write. Khi vượt giới hạn, Step thất bại.

Không chỉ dựa vào skipLimit để quyết định chất lượng batch. Cần theo dõi tỷ lệ lỗi:

- Tổng số record đọc.
- Tổng số record hợp lệ.
- Tổng số record bị filter.
- Tổng số record bị skip/reject.
- Tỷ lệ lỗi theo loại.

Có thể fail Job nếu tỷ lệ lỗi vượt ngưỡng nghiệp vụ dù skip count chưa đạt limit tuyệt đối. Logic này nên được thiết kế rõ bằng listener/decider hoặc bước kiểm tra kết quả, không rải điều kiện trong processor.

## 21. Validation lỗi ở writer

Một số lỗi chỉ xuất hiện khi ghi:

- Unique key đã tồn tại.
- Foreign key không hợp lệ.
- Optimistic lock conflict.
- Cột vượt độ dài.
- Database check constraint bị vi phạm.

Không thể bảo đảm mọi lỗi này được phát hiện trước processor vì trạng thái database có thể thay đổi giữa validation và write. Writer/database phải vẫn xử lý lỗi.

Không skip mọi DataIntegrityViolationException. Có thể đó là lỗi dữ liệu một record, nhưng cũng có thể là lỗi schema hoặc bug mapping. Phân loại exception cụ thể và giữ business key để reject đúng item.

Với writer exception, Spring Batch có thể phải rollback chunk và xác định item gây lỗi theo cơ chế fault-tolerant processing. Điều này có thể dẫn tới nhiều lần gọi writer/processor. Writer phải idempotent và không có side effect ngoài transaction không được bảo vệ.

## 22. Validation và transaction

Processor thường chạy trong transaction của chunk trong chunk-oriented Step, nhưng việc processor có truy cập database hay không phụ thuộc service và transaction manager.

Nếu validation chỉ kiểm tra field trong object, không cần mở transaction riêng. Nếu validation đọc database, nó có thể tham gia transaction chunk hoặc tạo transaction theo propagation được cấu hình.

Tránh:

- Mở transaction REQUIRES_NEW cho mọi validation lookup mà không có lý do.
- Gọi commit thủ công trong processor.
- Ghi reject file bên ngoài rồi kỳ vọng database rollback file đó.
- Reserve inventory trong validation mà không có compensation.

Nếu validation service thay đổi database, hãy xác định thay đổi đó có phải cùng transaction với writer không. Nếu processor ném exception sau side effect đã commit ở REQUIRES_NEW, chunk rollback không hoàn tác side effect đó.

## 23. Restart và validation ổn định

Khi Job restart, item của chunk chưa commit có thể được xử lý lại. Validation nên cho kết quả nhất quán nếu input và rule không đổi.

Một số yếu tố có thể làm kết quả khác giữa lần chạy:

- Ngày hiện tại thay đổi.
- Customer hoặc product status thay đổi.
- External registry trả kết quả mới.
- Danh sách currency/region được cập nhật.
- Cấu hình validation thay đổi.
- Database transaction khác cập nhật dữ liệu tham chiếu.

Nếu cần cùng JobInstance cho ra cùng quyết định, hãy lưu business date, rule version hoặc snapshot key trong JobParameters/metadata. Với validation external, có thể cần lưu kết quả hoặc version của dữ liệu tham chiếu.

Không lưu managed entity hoặc Validator state vào ExecutionContext. Chỉ lưu ID, version, business date hoặc checkpoint cần thiết. Validator thường được inject từ application context và không cần serialize.

Nếu rule thay đổi giữa restart, cân nhắc fail JobInstance cũ và tạo JobInstance mới với rule version khác thay vì tiếp tục cùng checkpoint bằng logic mới.

## 24. Validation và concurrency

Processor có thể được dùng đồng thời trong multi-threaded Step hoặc partitioned Step. Do đó:

- Không giữ mutable per-item state trong field của processor singleton.
- Validator và constraint validator phải được dùng theo lifecycle thread-safe của provider.
- Cache phải thread-safe và có scope phù hợp.
- Không chia sẻ một list lỗi mutable giữa các item.
- External client cần timeout và connection pool phù hợp.
- Error counter nên dùng StepExecution context, listener hoặc metric thread-safe.

Ví dụ không nên:

~~~java
private final List<String> currentViolations = new ArrayList<>();
~~~

Nếu nhiều thread gọi process(), danh sách này có thể trộn lỗi của nhiều item.

Thay vào đó, tạo list local cho từng invocation và trả/throw lỗi gắn với item hiện tại. Nếu cần tổng hợp lỗi, ghi từng reject record với message ID hoặc business key.

## 25. Unit test validation processor

Unit test nên xác nhận:

- Input hợp lệ tạo đúng output.
- Mỗi constraint quan trọng được thực thi.
- Nhiều lỗi được gom đúng.
- Exception chứa business key và property path.
- Null object được xử lý theo contract.
- Normalization chỉ thay đổi dữ liệu được phép.
- Processor không gọi dependency tiếp theo khi validation thất bại.

Ví dụ:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderValidationProcessorTest {

    private Validator validator;
    private OrderValidationProcessor processor;

    @BeforeEach
    void setUp() {
        ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory();
        validator = factory.getValidator();
        processor = new OrderValidationProcessor(validator);
    }

    @Test
    void returnsValidatedOrderForValidInput() {
        OrderInput input = validOrderInput();

        ValidatedOrder result = processor.process(input);

        assertEquals(input.getOrderId(), result.orderId());
        assertEquals("C001", result.customerCode());
    }

    @Test
    void throwsWhenRequiredCustomerCodeIsMissing() {
        OrderInput input = validOrderInput();
        input.setCustomerCode(" ");

        InvalidOrderException exception = assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));

        assertEquals(input.getOrderId(), exception.getOrderId());
        assertTrue(exception.getViolations().stream()
                .anyMatch(message -> message.contains("customerCode")));
    }
}
~~~

Trong test suite lớn, tạo ValidatorFactory một lần cho class và đóng factory sau khi test hoàn tất, hoặc dùng Validator bean được test context quản lý. Không tạo factory mới cho mỗi test mà không đóng.

### Test từng constraint

Với DTO có nhiều constraint, có thể dùng parameterized test:

~~~java
@ParameterizedTest
@MethodSource("invalidOrderCases")
void rejectsInvalidOrders(OrderInput input) {
    assertThrows(
            InvalidOrderException.class,
            () -> processor.process(input));
}
~~~

MethodSource nên đặt tên case hoặc dùng Arguments có display name để biết lỗi nào đang được kiểm tra. Một test tổng hợp nhiều field thiếu chỉ chứng minh có ít nhất một lỗi; nếu muốn xác nhận mọi constraint, assert các property path cụ thể.

## 26. Test cross-field và validation groups

Cross-field validator cần test:

| startDate | endDate | Kết quả |
| --- | --- | --- |
| null | null | Field-level @NotNull báo lỗi nếu bắt buộc |
| 2026-01-10 | 2026-01-09 | Không hợp lệ |
| 2026-01-10 | 2026-01-10 | Hợp lệ nếu cho phép cùng ngày |
| 2026-01-10 | 2026-01-11 | Hợp lệ |

Validation group cần test rằng:

- Group ImportChecks chạy đúng constraint import.
- Group ApprovalChecks chạy đúng constraint approval.
- Constraint không thuộc group không bị kích hoạt ngoài ý muốn.
- GroupSequence dừng theo thứ tự được định nghĩa.

Không chỉ test annotation có mặt trong source. Gọi Validator.validate() với group thật và assert property path/error code.

## 27. Integration test skip và reject output

Unit test không chứng minh Step thực sự skip record. Integration test nên:

1. Tạo input gồm record hợp lệ và không hợp lệ.
2. Chạy Step có validation processor và skip policy.
3. Xác nhận Step COMPLETED khi skip count nằm trong giới hạn.
4. Xác nhận valid records được ghi.
5. Xác nhận reject records được lưu đúng nếu có reject listener/writer.
6. Xác nhận skip count đúng.
7. Chạy trường hợp vượt skipLimit và xác nhận Step FAILED.
8. Restart Job và xác nhận record đã commit không bị xử lý trùng.

Nếu reject writer ghi vào database, kiểm tra transaction và idempotency. Nếu reject output là file hoặc broker, kiểm tra side effect khi chunk rollback và retry.

### Kiểm tra skip listener

Xác nhận onSkipInProcess nhận đúng item và InvalidOrderException. Với listener ghi reject record, test rằng một item lỗi không tạo nhiều reject record sau retry hoặc restart.

Có thể dùng unique key kết hợp batchId và sourceRecordId để chống reject duplicate.

## 28. Những lỗi thường gặp

### Nghĩ annotation tự động chạy trong processor

Annotation chỉ khai báo constraint. Phải gọi Validator.validate() hoặc kích hoạt validation ở boundary phù hợp.

### Dùng @NotNull thay cho @NotBlank

Chuỗi rỗng hoặc chỉ có khoảng trắng có thể lọt qua. Chọn constraint đúng với kiểu và contract.

### Dùng null để biểu thị dữ liệu lỗi

Spring Batch coi null là filter. Ném exception hoặc tạo reject result nếu cần lưu lỗi.

### Retry validation error

Dữ liệu sai ổn định thường không tự hợp lệ sau retry. Dùng skip/reject hoặc fail theo policy.

### Skip mọi RuntimeException

Có thể bỏ qua lỗi cấu hình, bug hoặc lỗi hạ tầng. Chỉ skip exception đã phân loại rõ.

### Không lưu source record metadata

Sau parse, khó xác định dòng/file/message gây lỗi. Giữ source ID, line number hoặc message ID trong item metadata.

### Validator truy vấn database trong mỗi field

Có thể tạo N+1 lookup và làm batch chậm. Gom lookup, cache có kiểm soát hoặc tách business validation service.

### Validation có side effect

Retry có thể lặp reserve, gửi message hoặc gọi API. Giữ validation read-only; command side effect cần idempotency.

### Chỉ kiểm tra dữ liệu trước khi ghi

Database có thể thay đổi giữa validate và write. Dùng constraint, locking hoặc conditional update ở nơi cần bảo đảm.

### Không xử lý lỗi trong reject listener

Record bị skip nhưng không có dấu vết. Xây dựng reject output bền vững và có transaction strategy rõ.

### Ghi payload nhạy cảm vào log

Log có thể làm lộ thông tin cá nhân hoặc bí mật. Chỉ lưu business key, field path và mã lỗi cần thiết.

### Không kiểm thử restart

Rule hoặc external reference có thể thay đổi giữa lần chạy. Lưu rule version/business date khi cần tính nhất quán.

## 29. Quy trình thiết kế validation processor

Khi triển khai, hãy thực hiện:

1. Xác định contract của input và kiểu DTO nhận từ reader.
2. Phân loại validation cấu trúc, field-level, cross-field, business và external.
3. Khai báo Jakarta constraints cho các quy tắc thuần trên object.
4. Inject và tái sử dụng Validator trong processor.
5. Tạo exception có business key, property path và error code.
6. Chuẩn hóa dữ liệu theo quy tắc rõ ràng rồi chuyển sang DTO nội bộ.
7. Quyết định rõ item lỗi sẽ fail, skip, reject hay filter.
8. Cấu hình skip/retry policy chỉ cho exception phù hợp.
9. Lưu reject record bền vững nếu dữ liệu cần điều tra hoặc replay.
10. Giữ validation processor không có side effect không idempotent.
11. Kiểm soát external validation bằng timeout, retry, cache hoặc snapshot.
12. Xác định business date và rule version để restart nhất quán.
13. Viết unit test cho mọi constraint và boundary quan trọng.
14. Viết integration test cho skip count, reject output, rollback và restart.
15. Theo dõi số record hợp lệ, filter, skip, reject và tỷ lệ lỗi.

Validation processor tốt làm rõ vì sao một item được chấp nhận hoặc từ chối, giữ lỗi ở dạng có cấu trúc và để Spring Batch áp dụng policy nhất quán. Các bước sau chỉ nhận dữ liệu đã đáp ứng invariant mà chúng cần.

## Kết luận

Validation processor kiểm tra dữ liệu trước khi các bước xử lý và ghi tiếp theo sử dụng item. Dùng Jakarta Bean Validation cho constraint trên DTO, custom class-level validator cho quy tắc liên field và domain service cho business validation cần dữ liệu tham chiếu. Inject Validator dùng lại, tạo exception có business key và lỗi có cấu trúc, rồi quyết định rõ giữa filter bằng null, skip/reject bằng exception hoặc fail Job. Skip policy phải chỉ định đúng loại lỗi; retry dành cho lỗi tạm thời, còn validation error ổn định thường cần reject hoặc skip. Giữ validation không có side effect không idempotent, bảo vệ invariant cuối cùng tại database, lưu source metadata để điều tra và kiểm thử cả rule lẫn hành vi Step, reject output và restart.
