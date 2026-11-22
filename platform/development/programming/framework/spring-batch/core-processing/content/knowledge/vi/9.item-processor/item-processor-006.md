# Validate trước khi transform

Trong Spring Batch, ItemProcessor thường đảm nhiệm việc kiểm tra và biến đổi dữ liệu giữa ItemReader và ItemWriter. Với dữ liệu đầu vào từ file, message hoặc database, một thiết kế an toàn là **validate dữ liệu nguồn trước khi transform sang mô hình đích**.

Thứ tự này giúp phát hiện dữ liệu không hợp lệ ngay tại ranh giới đầu vào, khi ứng dụng vẫn còn đầy đủ thông tin gốc để giải thích lỗi. Nó cũng tránh việc biến đổi một bản ghi sai thành object đích rồi mới phát hiện vấn đề ở bước sau.

Validation và transformation là hai trách nhiệm khác nhau:

- **Validation** xác định dữ liệu có đáp ứng cấu trúc và quy tắc nghiệp vụ cần thiết hay không.
- **Transformation** chuyển dữ liệu hợp lệ từ mô hình nguồn sang mô hình đích, chuẩn hóa hoặc tính toán các trường cần thiết.

Spring Batch cho phép tổ chức hai trách nhiệm này trong một ItemProcessor, hoặc ghép nhiều processor theo thứ tự bằng CompositeItemProcessor.

## 1. Vị trí của validation trong luồng chunk

Trong chunk-oriented Step, dữ liệu đi qua ItemReader, ItemProcessor và ItemWriter:

~~~text
Nguồn dữ liệu
     |
     v
 ItemReader
     |
     v
 Dữ liệu nguồn
     |
     v
 Validate
     |
     +---- không hợp lệ ----> Exception / Skip / Filter
     |
     v
 Transform
     |
     v
 Mô hình đích
     |
     v
 ItemWriter
     |
     v
 Đích dữ liệu
~~~

Reader chịu trách nhiệm đọc và chuyển dữ liệu vật lý thành item của ứng dụng. Ví dụ, FlatFileItemReader có thể parse một dòng CSV thành OrderInput. Processor kiểm tra các điều kiện mà reader không thể xác định, chẳng hạn mã đơn hàng bắt buộc, số tiền dương hoặc ngày nghiệp vụ hợp lệ. Sau đó transformer chuyển OrderInput thành Order để writer lưu vào database.

Validation trước transform đặc biệt hữu ích khi:

- Mô hình nguồn và mô hình đích khác nhau.
- Transform có thể làm mất thông tin gốc hoặc chuẩn hóa dữ liệu.
- Quy tắc nghiệp vụ cần áp dụng trên giá trị nguyên bản nhận từ nguồn.
- Muốn phân loại bản ghi lỗi trước khi thực hiện phép tính hoặc gọi dịch vụ khác.
- Cần ghi nhận chính xác giá trị nguồn và lý do từ chối để đối soát.

Không phải mọi kiểm tra đều phải đặt trong processor. Lỗi cú pháp hoặc lỗi parse có thể được phát hiện ngay ở reader. Constraint ở database vẫn cần thiết để bảo vệ dữ liệu cuối cùng. Validation trong processor bổ sung lớp kiểm tra nghiệp vụ giữa hai giai đoạn đó.

## 2. Phân biệt validation và transformation

Giả sử file nguồn chứa dữ liệu đơn hàng:

~~~text
order_id,customer_code,quantity,unit_price
ORD-1001,CUS-01,2,150000
ORD-1002,,0,-500
~~~

Dòng đầu có thể hợp lệ. Dòng thứ hai thiếu customer_code, quantity bằng 0 và unit_price âm. Nếu transformer chạy trước, nó có thể tạo Order với dữ liệu thiếu hoặc tính totalAmount từ các giá trị không hợp lệ. Khi đó lỗi có thể xuất hiện muộn hơn, chẳng hạn trong writer hoặc ở hệ thống báo cáo.

Nên chia công việc thành hai giai đoạn:

**Validation trên OrderInput**

- orderId không được rỗng.
- customerCode phải có giá trị.
- quantity phải lớn hơn 0.
- unitPrice không được âm.

**Transformation sang Order**

- Chuẩn hóa mã đơn hàng.
- Tính totalAmount từ quantity và unitPrice.
- Chuyển mã khách hàng thành customer reference theo quy tắc đã xác định.
- Gán trạng thái ban đầu cho entity đích.

Validation trả lời câu hỏi “dữ liệu nguồn có được chấp nhận không?”. Transformation trả lời câu hỏi “dữ liệu hợp lệ cần được biểu diễn như thế nào trong mô hình đích?”.

## 3. Viết validator riêng cho dữ liệu nguồn

Một cách rõ ràng là tạo validator nhận kiểu dữ liệu nguồn và ném exception khi bản ghi không hợp lệ. Spring Batch cung cấp hợp đồng Validator trong package item.validator:

~~~java
public class OrderInputValidator
        implements org.springframework.batch.item.validator.Validator<OrderInput> {

    @Override
    public void validate(OrderInput input)
            throws org.springframework.batch.item.validator.ValidationException {

        if (input == null) {
            throw new org.springframework.batch.item.validator.ValidationException(
                    "Order input must not be null");
        }

        if (input.getOrderId() == null || input.getOrderId().isBlank()) {
            throw new org.springframework.batch.item.validator.ValidationException(
                    "orderId is required");
        }

        if (input.getCustomerCode() == null
                || input.getCustomerCode().isBlank()) {
            throw new org.springframework.batch.item.validator.ValidationException(
                    "customerCode is required");
        }

        if (input.getQuantity() == null || input.getQuantity() <= 0) {
            throw new org.springframework.batch.item.validator.ValidationException(
                    "quantity must be greater than zero");
        }

        if (input.getUnitPrice() == null
                || input.getUnitPrice().signum() < 0) {
            throw new org.springframework.batch.item.validator.ValidationException(
                    "unitPrice must not be negative");
        }
    }
}
~~~

Validator chỉ kiểm tra dữ liệu và báo lỗi. Nó không thay đổi input, không ghi database và không thực hiện transformation. Giữ validator không có side effect giúp việc kiểm tra dễ dự đoán và an toàn khi Spring Batch retry một item.

Có thể kiểm tra nhiều điều kiện trong một lần và tạo một thông báo chứa danh sách lỗi thay vì dừng ở lỗi đầu tiên. Khi làm vậy, cần dùng một exception phù hợp với quy ước ứng dụng và bảo đảm thông tin lỗi đủ để người vận hành xác định bản ghi nguồn.

### Dùng ValidatingItemProcessor

Spring Batch cung cấp ValidatingItemProcessor để chuyển một Validator thành ItemProcessor. Processor này nhận và trả về cùng kiểu dữ liệu nếu validation thành công:

~~~java
@Bean
public ValidatingItemProcessor<OrderInput> orderValidationProcessor(
        OrderInputValidator validator) {

    ValidatingItemProcessor<OrderInput> processor =
            new ValidatingItemProcessor<>();
    processor.setValidator(validator);
    processor.setFilter(false);
    return processor;
}
~~~

Với filter=false, validation failure được ném ra dưới dạng ValidationException. Step có thể thất bại hoặc xử lý exception theo cấu hình retry/skip.

Nếu setFilter(true), bản ghi không hợp lệ được lọc bằng cách processor trả về null. Item đó không được chuyển đến processor tiếp theo hoặc writer. Đây là quyết định nghiệp vụ: filter phù hợp khi chỉ cần loại bỏ item, còn exception/skip phù hợp khi cần ghi nhận bản ghi bị từ chối và lý do.

## 4. Ghép validation và transformation bằng CompositeItemProcessor

CompositeItemProcessor cho phép ghép các ItemProcessor thành một chuỗi. Output của processor trước trở thành input của processor tiếp theo. Đây là cách thể hiện rõ thứ tự validate trước, transform sau.

Giả sử có hai thành phần:

- ValidatingItemProcessor<OrderInput> kiểm tra OrderInput và trả lại chính item đó nếu hợp lệ.
- OrderTransformer chuyển OrderInput thành Order.

Transformer có thể được triển khai như sau:

~~~java
public class OrderTransformer
        implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        Order order = new Order();
        order.setOrderId(input.getOrderId().trim().toUpperCase());
        order.setCustomerCode(input.getCustomerCode().trim());
        order.setQuantity(input.getQuantity());
        order.setUnitPrice(input.getUnitPrice());
        order.setTotalAmount(
                input.getUnitPrice().multiply(
                        BigDecimal.valueOf(input.getQuantity())));
        order.setStatus(OrderStatus.NEW);
        return order;
    }
}
~~~

Sau đó ghép hai processor theo đúng thứ tự:

~~~java
@Bean
public ItemProcessor<OrderInput, Order> orderProcessor(
        ValidatingItemProcessor<OrderInput> orderValidationProcessor,
        OrderTransformer orderTransformer) throws Exception {

    return new CompositeItemProcessorBuilder<OrderInput, Order>()
            .delegates(orderValidationProcessor, orderTransformer)
            .build();
}
~~~

Luồng thực thi:

~~~text
OrderInput
    |
    v
ValidatingItemProcessor<OrderInput>
    |
    +-- ValidationException nếu không hợp lệ
    |
    v
OrderInput đã hợp lệ
    |
    v
OrderTransformer
    |
    v
Order
~~~

Nếu validation ném exception, CompositeItemProcessor dừng chuỗi tại processor đó. OrderTransformer không được gọi cho item lỗi. Điều này bảo đảm transformation chỉ chạy trên dữ liệu đã qua kiểm tra.

Generic type của các processor phải nối tiếp được với nhau. Processor validation có kiểu vào và ra là OrderInput; transformer nhận OrderInput và trả về Order. Nếu output của một processor không tương thích với input của processor tiếp theo, chuỗi không thể được cấu hình đúng.

## 5. Validation bằng Jakarta Bean Validation

Với DTO có các quy tắc kiểm tra phổ biến, có thể khai báo constraint bằng Jakarta Bean Validation thay vì tự viết tất cả điều kiện.

Ví dụ:

~~~java
public class OrderInput {

    @NotBlank
    private String orderId;

    @NotBlank
    private String customerCode;

    @NotNull
    @Positive
    private Integer quantity;

    @NotNull
    @DecimalMin("0.00")
    private BigDecimal unitPrice;

    // constructors, getters and setters
}
~~~

Spring Batch có BeanValidatingItemProcessor để kiểm tra constraint trên item:

~~~java
@Bean
public BeanValidatingItemProcessor<OrderInput> beanValidatingProcessor()
        throws Exception {

    BeanValidatingItemProcessor<OrderInput> processor =
            new BeanValidatingItemProcessor<>();
    processor.setFilter(false);
    return processor;
}
~~~

Khi BeanValidatingItemProcessor được đặt trước OrderTransformer trong CompositeItemProcessor, các constraint được kiểm tra trên OrderInput trước khi chuyển đổi.

Để sử dụng cách này, ứng dụng cần dependency implementation Jakarta Bean Validation phù hợp với phiên bản Spring Boot/Spring Framework đang dùng. Với Spring Boot, thường có thể bổ sung starter validation. Nếu dự án dùng Spring Batch 4 hoặc phiên bản cũ hơn, namespace validation có thể là javax.validation thay vì jakarta.validation; cần dùng đúng namespace theo phiên bản.

Bean Validation phù hợp với constraint trên từng object như bắt buộc, độ dài, khoảng số hoặc định dạng. Quy tắc phức tạp cần truy vấn dữ liệu tham chiếu, kiểm tra trạng thái liên quan hoặc áp dụng theo ngữ cảnh Job thường phù hợp hơn với validator nghiệp vụ riêng.

## 6. Validate trước transform trong một processor duy nhất

Không bắt buộc phải dùng CompositeItemProcessor. Với logic nhỏ, có thể triển khai cả validation và transformation trong cùng một ItemProcessor, nhưng cần giữ thứ tự rõ ràng:

~~~java
public class OrderProcessor
        implements ItemProcessor<OrderInput, Order> {

    private final OrderInputValidator validator;
    private final OrderTransformer transformer;

    public OrderProcessor(
            OrderInputValidator validator,
            OrderTransformer transformer) {
        this.validator = validator;
        this.transformer = transformer;
    }

    @Override
    public Order process(OrderInput input) {
        validator.validate(input);
        return transformer.process(input);
    }
}
~~~

Ưu điểm của cách này là ít thành phần cấu hình và thứ tự được thể hiện trực tiếp trong phương thức process. Nhược điểm là processor chịu trách nhiệm điều phối hai bước, nên khi validation và transformation lớn dần, việc tách riêng sẽ dễ kiểm thử và tái sử dụng hơn.

Nên chọn một cách tổ chức phù hợp với độ phức tạp của luồng. Không cần tạo quá nhiều processor chỉ để tách những phép kiểm tra đơn giản, nhưng cũng không nên nhồi mọi quy tắc vào một phương thức process dài.

## 7. Validation failure: fail, skip hay filter?

Khi validation phát hiện item không hợp lệ, ứng dụng phải quyết định cách xử lý. Ba hành vi thường gặp có ý nghĩa khác nhau:

| Cách xử lý | Hành vi | Khi phù hợp |
| --- | --- | --- |
| Fail Step | Exception không được xử lý làm Step thất bại | Dữ liệu lỗi cho thấy nguồn hoặc quy trình không đáng tin cậy |
| Skip item | Exception thuộc nhóm được phép skip; Step tiếp tục và ghi nhận skip | Có thể bỏ qua bản ghi lỗi nhưng vẫn cần theo dõi |
| Filter item | Processor trả về null; item không đến writer | Loại bỏ item theo điều kiện nghiệp vụ mà không xem là lỗi |

Không nên dùng filter chỉ để che giấu dữ liệu sai. Filter thường dành cho item hợp lệ về mặt cấu trúc nhưng không cần đưa vào kết quả, ví dụ đơn hàng bị hủy và quy tắc nghiệp vụ yêu cầu bỏ qua trong báo cáo. Bản ghi thiếu mã đơn hàng hoặc có số lượng âm thường nên được xem là validation failure để có thể theo dõi.

### Dùng skip cho validation exception

Nếu yêu cầu là tiếp tục Job nhưng vẫn ghi nhận bản ghi không hợp lệ, có thể cấu hình fault-tolerant Step:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(ValidationException.class)
        .skipLimit(100)
        .build();
~~~

Ví dụ cho phép skip tối đa 100 validation failure theo chính sách skip của Step. Skip limit được tính trên các lỗi được skip trong Step, không phải là số lỗi tối đa riêng cho từng loại exception.

Nếu vượt giới hạn, hoặc xuất hiện exception không được phép skip, Step có thể thất bại. Không nên cấu hình skip cho mọi RuntimeException vì có thể che giấu lỗi lập trình hoặc lỗi hạ tầng.

### Ghi nhận bản ghi bị skip

Khi cần lưu lý do bản ghi bị từ chối, có thể dùng SkipListener:

~~~java
@Bean
public SkipListener<OrderInput, Order> orderSkipListener(
        RejectedOrderRepository rejectedOrderRepository) {

    return new SkipListener<>() {
        @Override
        public void onSkipInProcess(
                OrderInput item,
                Throwable cause) {

            rejectedOrderRepository.save(
                    RejectedOrder.from(item, cause.getMessage()));
        }
    };
}
~~~

Đăng ký listener vào Step bằng phương thức listener tương ứng. Trong thực tế, nên lưu mã nguồn, số dòng hoặc input identifier cùng error code và thông báo có thể tra cứu. Tránh chỉ lưu message tự do vì nội dung message có thể thay đổi theo phiên bản hoặc ngôn ngữ.

Nếu dữ liệu bị skip cần được lưu ở một database khác với transaction của Step, hãy thiết kế rõ transaction và khả năng ghi nhận lỗi. Không giả định thao tác lưu rejected record luôn được commit cùng transaction nghiệp vụ nếu nó dùng resource hoặc transaction manager khác.

## 8. Validation ở reader, processor và database

Validation nên được đặt ở lớp hiểu rõ nhất về loại lỗi cần phát hiện:

| Vị trí | Loại kiểm tra phù hợp | Ví dụ |
| --- | --- | --- |
| Reader / parser | Cấu trúc và chuyển đổi dữ liệu nguồn | CSV thiếu cột, ngày sai định dạng, số không parse được |
| ItemProcessor trước transform | Quy tắc nghiệp vụ trên mô hình nguồn | Mã khách hàng bắt buộc, số lượng phải dương |
| Sau transform | Invariant của mô hình đích | Tổng tiền không âm, trạng thái đích hợp lệ |
| Database | Ràng buộc cuối cùng bảo vệ tính toàn vẹn | NOT NULL, UNIQUE, FOREIGN KEY, CHECK |

Không nên đẩy mọi lỗi vào ItemProcessor. Nếu một dòng CSV không thể parse thành OrderInput, processor chưa có object để kiểm tra. Lỗi đó phải được xử lý ở reader hoặc parser, với skip policy phù hợp nếu nghiệp vụ cho phép.

Tương tự, validation trong processor không thay thế constraint của database. Có thể có nhiều Job hoặc ứng dụng cùng ghi vào database; constraint ở database vẫn là lớp bảo vệ cuối cùng chống dữ liệu không nhất quán.

### Validation sau transform vẫn có thể cần thiết

Validate trước transform bảo đảm dữ liệu nguồn đủ điều kiện để chuyển đổi. Nhưng transformation có thể tạo ra giá trị mới hoặc kết hợp nhiều trường. Vì vậy, đôi khi cần kiểm tra thêm invariant của mô hình đích:

~~~text
OrderInput
   |
   v
Validate source fields
   |
   v
Transform to Order
   |
   v
Validate target invariants
   |
   v
ItemWriter
~~~

Ví dụ, quantity và unitPrice đều hợp lệ nhưng phép tính totalAmount có thể vượt giới hạn nghiệp vụ. Khi đó cần kiểm tra kết quả sau transform. Hai lớp validation này có mục đích khác nhau và có thể cùng tồn tại.

## 9. Thiết kế validator dễ bảo trì

Một validator tốt nên có các đặc điểm:

- **Có phạm vi rõ:** kiểm tra một loại input hoặc một nhóm quy tắc liên quan.
- **Không có side effect:** không ghi database, gửi message hoặc sửa trạng thái bên ngoài.
- **Thông báo có ngữ cảnh:** nêu tên trường hoặc mã quy tắc bị vi phạm.
- **Có thể kiểm thử độc lập:** nhận input và trả kết quả hoặc ném exception.
- **Không lặp quy tắc:** dùng lại validator ở các luồng nhập khác nếu cùng ngữ nghĩa.
- **Phân biệt lỗi dữ liệu và lỗi hệ thống:** dữ liệu sai có thể skip theo chính sách; database hoặc service không khả dụng thường cần retry hoặc fail.

Nếu validator phải tra cứu dữ liệu tham chiếu, chẳng hạn customerCode có tồn tại hay không, cần xem xét chi phí truy vấn. Gọi database một lần cho từng item có thể tạo N+1 query và làm throughput giảm. Có thể dùng cache có giới hạn, bulk lookup hoặc preloading dữ liệu tham chiếu theo phạm vi phù hợp. Cache phải có chính sách hết hạn và tính nhất quán rõ ràng.

Tránh dùng exception cho mọi điều kiện nghiệp vụ thông thường nếu số lượng lỗi dự kiến rất lớn và cần xử lý theo hướng thống kê. Tuy nhiên, với Spring Batch, exception vẫn là cơ chế tích hợp trực tiếp với skip/retry. Quyết định cần dựa trên semantics: item lỗi phải bị từ chối có kiểm soát hay chỉ được lọc theo điều kiện.

## 10. Kiểm thử validation trước transformation

Có thể kiểm thử validator và transformer riêng, sau đó kiểm thử thứ tự của CompositeItemProcessor.

### Kiểm thử validator

~~~java
class OrderInputValidatorTest {

    private final OrderInputValidator validator =
            new OrderInputValidator();

    @Test
    void rejectsInputWithoutOrderId() {
        OrderInput input = new OrderInput(
                " ",
                "CUS-01",
                2,
                new BigDecimal("100.00"));

        assertThrows(
                ValidationException.class,
                () -> validator.validate(input));
    }
}
~~~

### Kiểm thử thứ tự xử lý

Có thể dùng Mockito để xác nhận transformer không được gọi khi validation thất bại:

~~~java
@Test
void doesNotTransformInvalidInput() throws Exception {
    OrderInputValidator validator = new OrderInputValidator();
    OrderTransformer transformer = mock(OrderTransformer.class);
    OrderInput invalidInput = new OrderInput(
            "",
            "CUS-01",
            2,
            new BigDecimal("100.00"));

    OrderProcessor processor =
            new OrderProcessor(validator, transformer);

    assertThrows(
            ValidationException.class,
            () -> processor.process(invalidInput));

    verifyNoInteractions(transformer);
}
~~~

Test này xác nhận lỗi được phát hiện trước khi transformation diễn ra. Ngoài ra, nên kiểm thử item hợp lệ được chuyển đổi đúng, item được filter không đến writer, validation exception được skip theo giới hạn và Step thất bại khi vượt skip limit.

## 11. Những lỗi thường gặp

### Transform trước rồi mới validate

Nếu transformation làm mất giá trị gốc hoặc thay đổi định dạng, thông tin cần thiết để giải thích lỗi có thể không còn. Hãy kiểm tra các quy tắc áp dụng cho input trước khi chuyển đổi.

### Gộp validation và transformation không có ranh giới

Một phương thức process dài vừa kiểm tra, vừa chuẩn hóa, vừa gọi service và ghi dữ liệu sẽ khó kiểm thử. Hãy tách validator và transformer khi mỗi phần có trách nhiệm hoặc vòng đời riêng.

### Filter mọi bản ghi không hợp lệ

Trả về null làm item biến mất khỏi luồng writer và được tính là filtered. Nếu cần audit hoặc thống kê bản ghi sai, hãy dùng exception và skip listener hoặc một luồng lưu rejected record phù hợp.

### Skip mọi exception

Skip lỗi kết nối database hoặc lỗi lập trình có thể làm Job tiếp tục trong trạng thái không đáng tin cậy. Chỉ skip các exception thể hiện lỗi dữ liệu đã được phân loại rõ.

### Validator có side effect

Nếu validator ghi dữ liệu hoặc gọi API, retry có thể lặp lại side effect. Giữ validation thuần kiểm tra; đặt các thao tác ghi hoặc điều phối ở thành phần có transaction và idempotency phù hợp.

### Truy vấn database cho từng item

Validation nghiệp vụ cần tra cứu tham chiếu có thể tạo nhiều query. Đo chi phí và cân nhắc bulk lookup hoặc cache có giới hạn thay vì truy vấn lặp không kiểm soát.

### Chỉ validate input mà quên invariant của output

Một tập input hợp lệ vẫn có thể tạo ra output không hợp lệ sau khi tính toán hoặc kết hợp trường. Bổ sung validation sau transform khi mô hình đích có các ràng buộc riêng.

## 12. Quy trình tổ chức ItemProcessor

Khi xây dựng một luồng xử lý dữ liệu, có thể đi theo trình tự:

1. Xác định kiểu item mà reader tạo ra và các lỗi parse có thể xuất hiện.
2. Liệt kê quy tắc nghiệp vụ cần kiểm tra trên dữ liệu nguồn.
3. Chọn cách validate: validator riêng, ValidatingItemProcessor hoặc BeanValidatingItemProcessor.
4. Quyết định dữ liệu lỗi sẽ làm Step fail, được skip hay được filter.
5. Viết transformer chỉ nhận dữ liệu đã hợp lệ và chuyển sang kiểu đích.
6. Dùng CompositeItemProcessor nếu cần biểu diễn chuỗi nhiều processor.
7. Bổ sung kiểm tra invariant sau transform khi cần.
8. Giữ constraint database để bảo vệ tính toàn vẹn cuối cùng.
9. Kiểm thử thứ tự validation/transformation, skip/filter và restart.
10. Theo dõi read, filter, skip, write count và lưu lý do từ chối khi nghiệp vụ cần đối soát.

## Kết luận

Validate trước khi transform giúp phát hiện dữ liệu sai trên mô hình nguồn, giữ lại ngữ cảnh gốc và ngăn transformation chạy trên item không hợp lệ. Trong Spring Batch, có thể dùng Validator cùng ValidatingItemProcessor, BeanValidatingItemProcessor hoặc một processor tùy chỉnh, rồi ghép với transformer bằng CompositeItemProcessor. Hãy phân biệt exception/skip với filter bằng null, giữ validator không có side effect và bổ sung validation sau transform khi mô hình đích có invariant riêng.
