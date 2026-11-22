# Mapping processor

Trong Spring Batch, Mapping processor là cách dùng ItemProcessor để chuyển một item từ kiểu dữ liệu đầu vào sang kiểu dữ liệu đầu ra phù hợp với bước xử lý tiếp theo. Ví dụ, reader đọc OrderEntity từ database, processor chuyển entity thành OrderExportDto, rồi writer ghi DTO thành CSV, XML hoặc một bảng đích.

Mapping processor giúp tách cấu trúc dữ liệu nguồn khỏi cấu trúc dữ liệu đích. Reader chịu trách nhiệm lấy dữ liệu, processor chuyển đổi và chuẩn hóa dữ liệu theo nghiệp vụ, writer chịu trách nhiệm lưu kết quả. Khi ranh giới này rõ ràng, thay đổi schema database hoặc format tích hợp ít ảnh hưởng tới phần còn lại của Job.

## 1. Mapping processor là gì?

Spring Batch định nghĩa ItemProcessor với hai kiểu generic: kiểu đầu vào I và kiểu đầu ra O. Phương thức process nhận một item và trả về item đã được xử lý.

~~~java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
~~~

Mapping processor triển khai contract này để tạo một object có kiểu khác:

~~~text
Reader
  |
  v
OrderEntity
  |
  v
Mapping ItemProcessor
  |
  v
OrderExportDto
  |
  v
Writer
~~~

Ví dụ reader đọc entity có quan hệ với Customer, còn hệ thống nhận chỉ cần mã đơn hàng, tên khách hàng và tổng tiền. Processor có thể chuyển entity thành DTO phẳng:

~~~java
public record OrderExportDto(
        long orderId,
        String customerName,
        BigDecimal totalAmount,
        String currency) {
}
~~~

~~~java
public class OrderExportProcessor
        implements ItemProcessor<Order, OrderExportDto> {

    @Override
    public OrderExportDto process(Order order) {
        return new OrderExportDto(
                order.getId(),
                order.getCustomer().getName(),
                order.getTotalAmount(),
                order.getCurrency());
    }
}
~~~

Kiểu đầu vào và đầu ra được khai báo ngay trong Step, giúp compiler phát hiện nhiều lỗi nối component không tương thích.

## 2. Phân biệt mapping ở reader với mapping ở processor

Không phải mọi phép chuyển đổi dữ liệu đều cần đặt trong ItemProcessor. Cần phân biệt hai lớp mapping:

| Vị trí | Trách nhiệm | Ví dụ |
|---|---|---|
| RowMapper của JDBC reader | Chuyển một hàng ResultSet thành object Java | Cột id, amount thành Order |
| ItemProcessor | Chuyển đổi hoặc áp dụng quy tắc nghiệp vụ trên item đã đọc | Order thành OrderExportDto |
| FieldSetMapper của file reader | Chuyển field của một dòng file thành object Java | CSV row thành CustomerInput |
| Writer/Marshaller | Chuyển object đầu ra thành dạng lưu trữ | DTO thành SQL parameters hoặc XML |

Nếu SQL trả về cột customer_name và reader có thể ánh xạ trực tiếp thành một projection phù hợp, không nhất thiết phải tạo entity phức tạp rồi chuyển đổi lại. Ngược lại, nếu cần chuẩn hóa, tính toán hoặc áp dụng business rule, processor là nơi thích hợp.

Một nguyên tắc hữu ích là để reader trả về mô hình biểu diễn dữ liệu nguồn, processor tạo mô hình cần cho bước tiếp theo, và writer tập trung vào output.

## 3. Khi nào nên dùng Mapping processor?

Mapping processor hữu ích khi input và output có cấu trúc khác nhau hoặc khi dữ liệu cần được chuẩn hóa trước khi ghi.

Các trường hợp thường gặp:

- Entity database chuyển thành DTO dành cho API hoặc file export.
- CSV input chuyển thành domain command.
- Dữ liệu legacy chuyển thành schema mới.
- Nhiều field nguồn được gộp thành một field đích.
- Một field nguồn được tách thành nhiều field đầu ra.
- Enum hoặc mã trạng thái được chuyển thành giá trị theo contract.
- Ngày giờ, tiền tệ và số thập phân được chuẩn hóa.
- Dữ liệu lồng nhau được làm phẳng thành record.
- Field nội bộ bị loại khỏi dữ liệu xuất.
- Một item được chuyển thành model trung gian để writer khác xử lý.

Không cần tạo mapping processor chỉ để đổi tên một biến cục bộ hoặc chuyển đổi đơn giản đã được reader/writer hỗ trợ. Hãy dùng processor khi việc chuyển đổi là một bước có ý nghĩa trong pipeline và cần được kiểm thử độc lập.

## 4. Tách domain model khỏi DTO đầu ra

Domain model phản ánh quy tắc và cấu trúc bên trong ứng dụng. DTO đầu ra phản ánh hợp đồng mà hệ thống nhận yêu cầu. Hai mô hình thường có vòng đời thay đổi khác nhau.

Ví dụ entity:

~~~java
public class Order {
    private Long id;
    private Customer customer;
    private BigDecimal totalAmount;
    private OrderStatus status;
    private Instant createdAt;

    // getters
}
~~~

DTO xuất file:

~~~java
public record OrderExportDto(
        String orderNumber,
        String customerName,
        String statusCode,
        String createdDate,
        String amount) {
}
~~~

Mapping processor:

~~~java
public class OrderExportProcessor
        implements ItemProcessor<Order, OrderExportDto> {

    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.ISO_LOCAL_DATE;

    @Override
    public OrderExportDto process(Order order) {
        return new OrderExportDto(
                order.getId().toString(),
                order.getCustomer().getName(),
                order.getStatus().getCode(),
                DATE_FORMAT.format(
                        order.getCreatedAt()
                                .atZone(ZoneOffset.UTC)
                                .toLocalDate()),
                order.getTotalAmount().toPlainString());
    }
}
~~~

DTO có thể thay đổi theo version của file/API mà không buộc domain entity phải mang annotation hoặc field dành riêng cho từng consumer. Nếu nhiều output format cùng dùng một domain model, mỗi Step có thể có processor và DTO riêng.

Không nên đưa toàn bộ entity graph vào DTO nếu writer chỉ cần một vài field. Object output nhỏ hơn giúp giảm memory footprint và làm rõ contract.

## 5. Mapping thủ công

Với mapping nhỏ, mapping thủ công thường dễ đọc và dễ kiểm soát:

~~~java
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, Customer> {

    @Override
    public Customer process(CustomerInput input) {
        Customer customer = new Customer();
        customer.setExternalId(input.externalId().trim());
        customer.setName(input.name().trim());
        customer.setEmail(normalizeEmail(input.email()));
        customer.setActive(true);
        return customer;
    }

    private String normalizeEmail(String email) {
        return email == null
                ? null
                : email.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

Ưu điểm của mapping thủ công:
- Nhìn thấy trực tiếp field nào được copy hoặc biến đổi.
- Dễ áp dụng business rule có điều kiện.
- Không cần thư viện mapping bổ sung.
- Dễ xử lý field mặc định hoặc field cần tính toán.

Khi số lượng field tăng, code thủ công có thể dài và dễ bỏ sót field mới. Nên tổ chức mapping thành method hoặc mapper riêng để không biến processor thành một class chứa mọi quy tắc của ứng dụng.

## 6. Dùng MapStruct cho mapping nhiều field

MapStruct là thư viện tạo code mapping tại thời điểm compile. Developer khai báo interface và annotation, annotation processor sinh implementation Java. Mapping không cần reflection runtime cho từng field.

Ví dụ:

~~~java
@Mapper(componentModel = "spring")
public interface OrderMapper {

    @Mapping(target = "orderNumber", source = "id")
    @Mapping(target = "customerName", source = "customer.name")
    @Mapping(target = "statusCode", source = "status.code")
    @Mapping(target = "amount", source = "totalAmount")
    OrderExportDto toExportDto(Order order);
}
~~~

Processor sử dụng mapper được inject:

~~~java
@Component
public class OrderMappingProcessor
        implements ItemProcessor<Order, OrderExportDto> {

    private final OrderMapper mapper;

    public OrderMappingProcessor(OrderMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public OrderExportDto process(Order item) {
        return mapper.toExportDto(item);
    }
}
~~~

Cần cấu hình MapStruct annotation processor trong build và chọn version tương thích với Java/compiler của dự án. Với Spring component model, implementation được tạo ra như Spring bean để inject.

MapStruct phù hợp với mapping có nhiều field, nested property hoặc nhiều DTO. Các quy tắc nghiệp vụ phức tạp vẫn nên được thể hiện trong processor hoặc service riêng, thay vì nhồi toàn bộ logic vào annotation.

## 7. Kiểm soát field chưa được mapping

Khi schema thay đổi, một field mới có thể bị bỏ quên trong DTO. Với mapper generator, có thể cấu hình chính sách unmapped target/source để cảnh báo hoặc làm build thất bại khi mapping thiếu.

Ví dụ:

~~~java
@Mapper(
    componentModel = "spring",
    unmappedTargetPolicy = ReportingPolicy.ERROR)
public interface CustomerMapper {

    CustomerExportDto toExportDto(Customer customer);
}
~~~

Chính sách ERROR hữu ích khi DTO đích có contract cần mapping đầy đủ. Tuy nhiên, có field cố ý không map, chẳng hạn metadata được tạo ở bước sau. Hãy khai báo rõ field đó bằng ignore hoặc mapping mặc định để compiler và reviewer hiểu chủ đích.

Không tắt mọi cảnh báo mapping chỉ để build qua. Một field mới trong output contract có thể bị để null hoặc default mà không ai nhận ra.

## 8. Mapping nested object và làm phẳng dữ liệu

Nguồn có thể chứa object lồng nhau:

~~~text
Order
  |
  +-- id
  +-- totalAmount
  +-- customer
        |
        +-- name
        +-- address
              |
              +-- city
              +-- country
~~~

Output có thể là một record phẳng:

~~~text
orderId, customerName, city, country, totalAmount
~~~

MapStruct có thể truy cập nested property bằng source path:

~~~java
@Mapper(componentModel = "spring")
public interface OrderFlatMapper {

    @Mapping(target = "orderId", source = "id")
    @Mapping(target = "customerName", source = "customer.name")
    @Mapping(target = "city", source = "customer.address.city")
    @Mapping(target = "country", source = "customer.address.country")
    @Mapping(target = "totalAmount", source = "totalAmount")
    OrderFlatDto toDto(Order order);
}
~~~

Cần xác định rõ hành vi khi customer hoặc address null. Nếu dữ liệu có thể thiếu quan hệ, mapping phải tạo kết quả null/default có chủ đích hoặc validation phải reject item trước khi truy cập nested property.

Đừng mặc định mọi nested association đều đã được load. Nếu dùng ORM lazy loading, processor có thể kích hoạt thêm query cho từng item và tạo N+1 problem.

## 9. Mapping và N+1 query

Một mapping processor có thể truy cập quan hệ lazy như order.getCustomer().getName(). Nếu reader trả entity và persistence context không fetch trước quan hệ, mỗi item có thể phát sinh thêm query.

Ví dụ một chunk 500 Order có thể gây:
- Một query đọc danh sách Order.
- Tới 500 query bổ sung để lấy Customer.
- Nhiều query hơn nếu mapper đi sâu vào nhiều association.

Cách xử lý:
- Dùng query projection/join để lấy đúng dữ liệu cần thiết.
- Cấu hình fetch strategy phù hợp.
- Dùng DTO projection từ reader khi không cần entity.
- Batch fetch quan hệ nếu ORM hỗ trợ.
- Đo số query trong integration test hoặc môi trường gần production.

Không giải quyết N+1 bằng cách để processor gọi repository một lần cho mỗi item nếu có thể lấy dữ liệu theo batch. Mapping nên chuyển đổi dữ liệu đã có; việc truy xuất thêm dữ liệu cần được thiết kế và đo riêng.

## 10. Mapping kiểu dữ liệu

Mapping processor thường cần chuyển giữa các kiểu Java hoặc biểu diễn khác nhau:

| Nguồn | Đích | Lưu ý |
|---|---|---|
| Long | String | Quy tắc format ID |
| BigDecimal | String | Precision, scale và locale |
| Instant | LocalDate/String | Timezone và format |
| Enum | String/code | Contract ổn định, không phụ thuộc tên enum nội bộ |
| Boolean | Y/N hoặc 1/0 | Quy ước của consumer |
| Collection | Một field hoặc nhiều item | Separator, escaping và thứ tự |
| Nested object | Flat DTO | Null và lazy loading |
| Nullable value | Optional/default | Phân biệt null với giá trị mặc định |

Ví dụ chuyển BigDecimal:

~~~java
String formatAmount(BigDecimal amount) {
    return amount == null
            ? null
            : amount.setScale(2, RoundingMode.HALF_UP)
                    .toPlainString();
}
~~~

Không dùng double cho tiền tệ nếu cần độ chính xác thập phân. Không dùng NumberFormat theo locale mặc định của server nếu output contract yêu cầu dấu chấm thập phân cố định.

## 11. Ngày giờ và timezone

Ngày giờ là nguồn lỗi phổ biến khi mapping. Instant biểu diễn một thời điểm trên timeline; LocalDateTime không chứa timezone; LocalDate chỉ biểu diễn ngày.

Ví dụ chuyển Instant sang ngày UTC:

~~~java
LocalDate toUtcDate(Instant value) {
    return value.atZone(ZoneOffset.UTC).toLocalDate();
}
~~~

Nếu consumer cần timestamp ISO-8601 có offset:

~~~java
String toIsoTimestamp(Instant value) {
    return DateTimeFormatter.ISO_INSTANT.format(value);
}
~~~

Hãy chốt timezone theo contract:
- UTC cho timestamp trao đổi giữa hệ thống.
- Zone nghiệp vụ nếu báo cáo theo ngày địa phương.
- Offset rõ ràng nếu consumer cần diễn giải thời điểm.
- Không phụ thuộc timezone mặc định của JVM.

Test các trường hợp sát nửa đêm, chuyển daylight saving time nếu vùng có áp dụng, null và giá trị có precision nano/millisecond.

## 12. Mapping enum và mã nghiệp vụ

Không nên dùng enum.name() làm output contract nếu tên enum nội bộ có thể đổi. Ví dụ enum Java:

~~~java
public enum OrderStatus {
    NEW,
    IN_PROGRESS,
    COMPLETED,
    CANCELLED
}
~~~

Consumer có thể yêu cầu mã riêng:

~~~java
public enum OrderStatus {
    NEW("N"),
    IN_PROGRESS("P"),
    COMPLETED("C"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
~~~

Mapper dùng code thay vì tên enum:

~~~java
@Mapping(target = "status", source = "status.code")
OrderExportDto toDto(Order order);
~~~

Nếu code không được định nghĩa hoặc có enum mới, cần quyết định fail, reject hoặc mapping sang UNKNOWN. Không silently gửi null nếu consumer yêu cầu status bắt buộc.

## 13. Mapping có điều kiện

Một số field đích phụ thuộc nhiều field nguồn hoặc rule nghiệp vụ.

Ví dụ xác định loại khách hàng:

~~~java
CustomerType mapCustomerType(Customer customer) {
    if (customer.isCorporate()) {
        return CustomerType.BUSINESS;
    }

    if (customer.getBirthDate() == null) {
        return CustomerType.UNKNOWN;
    }

    return CustomerType.PERSONAL;
}
~~~

Có thể gọi method helper từ mapper hoặc thực hiện logic trong processor trước khi gọi mapper. Khi rule có nhiều nhánh, nên tách thành policy/service có tên rõ ràng để test riêng.

Không để mapping chỉ dựa trên việc copy field mà vô tình quyết định business behavior. Nếu một phép biến đổi ảnh hưởng nghiệp vụ, hãy mô tả rule, version và test boundary case.

## 14. Mapping nhiều input thành một output

ItemProcessor nhận một item và trả về tối đa một output item. Nó không phải API tự nhiên để gom nhiều item thành một record. Nếu cần tổng hợp nhiều input, cân nhắc:
- Aggregation trong processor có state được quản lý rõ.
- ItemReader trả về group/aggregate.
- Grouping theo key ở database query.
- Custom reader hoặc tasklet cho một đơn vị tổng hợp.
- Writer xử lý collection theo một contract riêng.

Không tích lũy mọi item của Job vào một list bên trong processor singleton. Điều đó làm memory tăng theo toàn bộ input, khó restart và có thể trộn state giữa executions.

## 15. Mapping một input thành nhiều output

ItemProcessor chuẩn trả về một output object hoặc null để filter. Nếu một input cần sinh nhiều output records, có thể dùng:
- Output object chứa collection để writer xử lý.
- Processor tạo một wrapper/group item.
- Custom processor/writer adapter có contract rõ ràng.
- Tách thành các Step để flatten collection thành item stream.

Không trả về List<T> rồi kỳ vọng Spring Batch tự bung list thành nhiều item. Với chữ ký ItemProcessor<I,O>, List<T> chỉ là một output item có kiểu List<T> nếu writer được cấu hình nhận kiểu đó.

Nếu cần fan-out, hãy thiết kế rõ số lượng output, ordering, transaction và restart semantics.

## 16. Mapping processor kết hợp validation

Mapping và validation là hai trách nhiệm khác nhau. Processor có thể chuyển đổi dữ liệu, còn validator kiểm tra input hoặc output theo contract.

Ví dụ:
- Validate input trước khi mapping để tránh null hoặc mã không hợp lệ.
- Mapping từ source sang DTO.
- Validate DTO đầu ra để bảo đảm field bắt buộc và format đúng.
- Reject hoặc skip theo policy nếu dữ liệu không hợp lệ.

Spring Batch có ValidatingItemProcessor và BeanValidatingItemProcessor ở các phiên bản tương ứng. BeanValidatingItemProcessor có thể dùng Bean Validation annotations trên object; cần cấu hình validator/provider và kiểm tra API theo version.

Ví dụ DTO:

~~~java
public record CustomerExportDto(
        @NotBlank String externalId,
        @NotBlank String name,
        @Email String email) {
}
~~~

Validation nên có lỗi cụ thể gắn với business key để dễ điều tra. Không biến mọi lỗi mapping thành filter bằng cách trả null; chỉ filter khi loại item đó được nghiệp vụ cho phép bỏ qua.

## 17. Null return có nghĩa là filter item

Theo contract ItemProcessor, nếu process trả về null, item sẽ bị lọc và không được gửi tới writer.

Ví dụ:

~~~java
@Override
public OrderExportDto process(Order order) {
    if (order.getStatus() == OrderStatus.CANCELLED) {
        return null;
    }

    return mapper.toExportDto(order);
}
~~~

Điều này khác với exception:
- Return null: loại item theo chủ đích; không phải lỗi.
- Throw exception: báo lỗi xử lý; Step có thể fail, retry hoặc skip tùy cấu hình.
- Trả về DTO có trạng thái REJECTED: item vẫn đi tới writer và có thể được lưu vào reject output.

Chọn một cách biểu diễn nhất quán. Nếu cần audit các item bị filter, hãy ghi nhận bằng listener/metrics hoặc một luồng riêng. Không dùng null để che giấu lỗi dữ liệu bắt buộc.

## 18. Kết hợp nhiều processor

CompositeItemProcessor cho phép nối nhiều ItemProcessor theo chuỗi. Output của processor trước là input của processor sau.

Ví dụ:

~~~text
OrderInput
    |
    v
NormalizeOrderProcessor
    |
    v
NormalizedOrder
    |
    v
ValidateOrderProcessor
    |
    v
ValidatedOrder
    |
    v
OrderMappingProcessor
    |
    v
OrderExportDto
    |
    v
Writer
~~~

Cấu hình:

~~~java
@Bean
CompositeItemProcessor<OrderInput, OrderExportDto> orderProcessor(
        ItemProcessor<OrderInput, NormalizedOrder> normalizeProcessor,
        ItemProcessor<NormalizedOrder, ValidatedOrder> validateProcessor,
        ItemProcessor<ValidatedOrder, OrderExportDto> mappingProcessor) {

    return new CompositeItemProcessorBuilder<
            OrderInput, OrderExportDto>()
            .delegates(
                    normalizeProcessor,
                    validateProcessor,
                    mappingProcessor)
            .build();
}
~~~

Các kiểu generic phải khớp theo chuỗi: output của processor trước phải tương thích input của processor sau. Tách bước giúp mỗi processor có một trách nhiệm và có thể unit test độc lập.

Nếu một delegate trả null, item được filter và không tiếp tục qua các processor sau. Nếu delegate ném exception, fault-tolerance policy của Step quyết định retry, skip hoặc fail.

## 19. Chọn processor theo classifier

ClassifierCompositeItemProcessor phù hợp khi cùng một Step xử lý nhiều loại input và cần chọn processor khác nhau theo item.

Ví dụ:
- Event loại ORDER dùng OrderProcessor.
- Event loại PAYMENT dùng PaymentProcessor.
- Event loại CUSTOMER dùng CustomerProcessor.

Các processor được chọn cần có output type chung phù hợp với writer hoặc một supertype/envelope chung. Generic type không thể bị bỏ qua: ItemProcessor<Order, OrderDto> không thể thay thế tùy tiện cho ItemProcessor<BaseEvent, ExportRecord>.

Classifier quyết định processor; processor thực hiện mapping. Nếu mọi item dùng cùng một mapping, dùng một ItemProcessor trực tiếp sẽ đơn giản hơn.

## 20. Gắn Mapping processor vào Step

Trong Spring Batch 5, StepBuilder khai báo input type và output type tại chunk:

~~~java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, OrderExportDto> orderProcessor,
        ItemWriter<OrderExportDto> orderWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, OrderExportDto>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
~~~

Điểm cần chú ý:
- Generic input của Step phải khớp kiểu reader trả về.
- Generic output của Step phải khớp kiểu processor trả về và writer nhận.
- Nếu không có processor, input và output thường cùng kiểu.
- Processor được gọi cho từng item trước khi writer nhận chunk đã xử lý.
- Item bị filter không được gửi tới writer.

Ở Spring Batch phiên bản cũ, cách tạo Step và chữ ký ItemWriter có thể khác. Hãy dùng API nhất quán với version dependency của ứng dụng.

## 21. Mapping và transaction của chunk

Processor chạy trong luồng xử lý chunk nhưng không tự tạo transaction riêng. Transaction boundary do Step/transaction manager điều khiển. Nếu processor chỉ chuyển đổi object trong bộ nhớ, thao tác mapping thường không có side effect cần rollback.

Nếu processor gọi database hoặc service ngoài, cần chú ý:
- Query thêm có thể tham gia transaction hiện tại tùy cách lấy connection.
- HTTP call không tự rollback cùng transaction JDBC.
- Gọi service ngoài có thể bị lặp khi chunk retry.
- Mapping phụ thuộc dữ liệu thay đổi có thể tạo kết quả khác khi restart.

Ưu tiên processor thuần, deterministic và không side effect. Nếu cần enrichment từ database, cân nhắc join ngay trong reader, preload lookup theo batch hoặc cache có version. Nếu cần gọi service ngoài, dùng idempotency và xác định rõ cách xử lý khi retry.

## 22. Deterministic mapping khi retry và restart

Cùng một input trong cùng một bộ rule nên tạo cùng một output. Nếu mapping phụ thuộc:
- Thời gian hiện tại.
- Locale hoặc timezone mặc định của JVM.
- Cấu hình có thể thay đổi trong khi Job chạy.
- Service ngoài trả kết quả động.
- Random number hoặc counter.
- Mutable singleton state.

thì retry/restart có thể tạo output khác với lần đầu.

Để giữ ổn định:
- Dùng timezone và locale được chỉ định rõ.
- Chốt version mapping/configuration trong JobParameters.
- Dùng input snapshot hoặc dữ liệu nguồn ổn định.
- Không dùng random/counter cho field nghiệp vụ.
- Lưu mapping decision nếu không thể tái tạo.
- Giữ cùng mapping version khi restart JobInstance cũ.

Nếu format output thay đổi theo version, có thể tạo DTO hoặc mapper version riêng. Không deploy một mapper mới rồi restart một JobInstance đang cần tiếp tục với semantics cũ mà không có kế hoạch migration.

## 23. Statelessness và thread safety

Processor thường được khai báo thành Spring bean singleton. Nếu processor chỉ giữ mapper immutable và không lưu trạng thái theo item, việc dùng chung thường an toàn.

Tránh:
- Lưu item hiện tại vào field.
- Dùng List mutable làm accumulator cho toàn Job.
- Dùng SimpleDateFormat shared không thread-safe.
- Tăng counter để tạo business key.
- Giữ EntityManager hoặc ResultSet ngoài lifecycle được quản lý.
- Lưu JobParameters của execution trước vào field singleton.

Nếu cần dữ liệu theo Job hoặc Step, dùng @StepScope hoặc @JobScope và truyền tham số phù hợp. Scope không tự làm một processor an toàn khi nhiều thread cùng gọi trong một Step; vẫn cần tránh mutable shared state hoặc đồng bộ đúng cách.

## 24. Mapping và hiệu năng

Mapping thường là thao tác CPU trong bộ nhớ, nhưng có thể trở thành bottleneck nếu:
- Tạo object graph lớn.
- Format ngày/tiền tệ nhiều lần với formatter không được tái sử dụng đúng cách.
- Truy vấn database trong mỗi lần process.
- Parse JSON/XML lớn trên từng item.
- Dùng reflection hoặc conversion động nhiều lần.
- Copy collection lớn không cần thiết.

Các hướng tối ưu:
- Dùng DTO nhỏ chứa đúng field writer cần.
- Dùng MapStruct cho mapping nhiều field nếu phù hợp.
- Tái sử dụng formatter immutable/thread-safe như DateTimeFormatter.
- Tránh N+1 query.
- Chỉ tính giá trị đầu ra cần thiết.
- Đo CPU, allocation và throughput trên dữ liệu đại diện.

Không tối ưu chỉ dựa trên số lần gọi mapper. Hãy đo toàn pipeline vì thời gian database read, transaction commit hoặc output I/O có thể lớn hơn thời gian mapping.

## 25. Logging và quan sát lỗi mapping

Khi mapping lỗi, cần biết item nào gây lỗi và field nào không hợp lệ. Có thể đưa business key vào exception hoặc log context:

~~~java
@Override
public OrderExportDto process(Order order) {
    try {
        return mapper.toExportDto(order);
    } catch (RuntimeException exception) {
        throw new OrderMappingException(
                "Cannot map order id=" + order.getId(),
                exception);
    }
}
~~~

Không log toàn bộ entity hoặc payload nếu có dữ liệu cá nhân, token hay thông tin nhạy cảm. Chỉ ghi business key, JobExecution ID, Step name, mapper version và lỗi cần thiết.

Nếu exception có thể được skip, cần ghi nhận item và lý do qua SkipListener. Nếu mapping lỗi là lỗi cấu hình áp dụng cho mọi item, nên fail Job sớm thay vì skip hàng loạt record.

## 26. Kiểm thử Mapping processor

Unit test trực tiếp processor giúp xác nhận mapping mà không cần khởi chạy Job.

Ví dụ:

~~~java
@Test
void mapsOrderToExportDto() throws Exception {
    Order order = new Order(
            101L,
            customer("Acme"),
            new BigDecimal("125.50"),
            OrderStatus.COMPLETED,
            Instant.parse("2026-01-10T12:00:00Z"));

    OrderExportDto result = processor.process(order);

    assertEquals("101", result.orderNumber());
    assertEquals("Acme", result.customerName());
    assertEquals("C", result.statusCode());
    assertEquals("125.50", result.amount());
}
~~~

Nên test:
- Mapping field cơ bản.
- Nested property.
- Null ở association hoặc field optional.
- Decimal precision/scale.
- Date/time và timezone.
- Enum/code mapping.
- Giá trị mặc định.
- Điều kiện filter trả null.
- Input không hợp lệ ném exception phù hợp.
- Cùng input và cùng rule tạo cùng output.
- Field mới hoặc field chưa được mapping.

Với MapStruct, có thể test implementation được inject qua Spring hoặc instantiate mapper được sinh tùy cấu hình. Ngoài unit test, cần integration test khi mapper là Spring bean và processor được gắn trong Step.

## 27. Kiểm thử processor trong Step

Unit test không chứng minh generic wiring giữa reader, processor và writer đúng. Integration test nên xác nhận dữ liệu sau mapping được writer nhận và ghi chính xác.

Ví dụ:
1. Insert vài Order vào database test.
2. Launch Step với reader, mapping processor và writer.
3. Xác nhận số item đọc và ghi.
4. Query output table hoặc đọc file.
5. So sánh field đã chuyển đổi.
6. Kiểm tra item filter hoặc reject theo chính sách.
7. Chạy lại test với lỗi ở một chunk để xác nhận retry/restart.

Không chỉ assert Step COMPLETED. Hãy kiểm tra nội dung đầu ra, business key và số lượng record. Nếu processor filter một item, write count sẽ nhỏ hơn read count; test cần khẳng định chính xác expected behavior.

## 28. Kiểm thử composition và mapping nhiều bước

Nếu dùng CompositeItemProcessor, kiểm tra cả thứ tự delegate và kiểu dữ liệu giữa các bước.

Ví dụ:
- Normalize trước.
- Validate sau normalize.
- Mapping sang DTO cuối cùng.

Test cần xác nhận:
- Processor đầu nhận đúng input.
- Processor sau nhận output đã chuẩn hóa.
- Null ở một bước dừng chuỗi theo filter semantics.
- Exception được truyền lên Step.
- Thứ tự delegate không bị đảo.
- Output cuối đúng contract.

Nên test riêng từng delegate và có một số integration test cho composite. Không cần mock tất cả processor trong mọi test; một test dùng implementation thật giúp phát hiện lỗi wiring và mapping.

## 29. Lỗi thường gặp

**Đưa toàn bộ mapping vào RowMapper.** Reader trở nên gắn chặt với format đích và khó tái sử dụng.

**Dùng domain entity làm output contract.** Thay đổi nội bộ có thể ảnh hưởng consumer.

**Mapping nested association gây N+1 query.** Job chậm khi số item tăng.

**Không xử lý null nested object.** Processor ném NullPointerException khi gặp dữ liệu thiếu.

**Dùng timezone/locale mặc định.** Output có thể khác giữa môi trường.

**Dùng enum.name() làm mã tích hợp.** Rename enum có thể phá contract downstream.

**Dùng double cho tiền tệ.** Có thể gây sai số thập phân.

**Mapping và side effect nằm chung một processor.** Retry có thể lặp side effect ngoài transaction.

**Processor giữ mutable state trong singleton.** Nhiều execution hoặc thread có thể ảnh hưởng lẫn nhau.

**Trả null để che lỗi mapping.** Item biến mất mà không có audit.

**Kỳ vọng một input tự bung thành nhiều output.** ItemProcessor chỉ trả về một output item theo generic O.

**Không kiểm tra generic type của Step.** Reader, processor và writer có thể không nối đúng kiểu.

**Chỉ test processor bằng mock.** Không phát hiện lỗi mapper, nested field hoặc integration wiring.

## 30. Quy trình triển khai Mapping processor

Khi xây dựng mapping processor trong Spring Batch, hãy thực hiện theo trình tự:

1. Xác định kiểu input reader trả về và kiểu output writer cần nhận.
2. Xác định mapping nào thuộc RowMapper/FieldSetMapper và mapping nào là chuyển đổi nghiệp vụ.
3. Thiết kế DTO hoặc model đầu ra độc lập với domain entity khi cần.
4. Chọn mapping thủ công cho logic nhỏ hoặc MapStruct cho mapping nhiều field.
5. Khai báo rõ nested mapping, null handling, enum, decimal và date/time format.
6. Tách validation và business rule khỏi thao tác copy field khi chúng có ý nghĩa riêng.
7. Giữ processor deterministic, stateless và không tạo side effect không idempotent.
8. Dùng CompositeItemProcessor nếu cần nối nhiều bước chuyển đổi có kiểu rõ ràng.
9. Dùng ClassifierCompositeItemProcessor khi cần chọn processor theo từng loại item và API version hỗ trợ.
10. Khai báo generic input/output của Step khớp reader, processor và writer.
11. Kiểm tra N+1 query, allocation và throughput với dữ liệu đại diện.
12. Unit test mapper, null, boundary, timezone, decimal và filter behavior.
13. Integration test Step, output thực tế, skip/retry và restart.
14. Version hóa mapping nếu JobInstance cũ có thể được restart sau khi deploy.

Mapping processor là lớp chuyển đổi giữa dữ liệu mà reader cung cấp và dữ liệu mà writer cần. Khi tách DTO khỏi domain model, kiểm soát null và kiểu dữ liệu, giữ mapping deterministic và khai báo generic type chính xác, pipeline Spring Batch dễ thay đổi, kiểm thử và phục hồi hơn. MapStruct có thể giảm code lặp cho mapping lớn, còn processor vẫn là nơi điều phối các quy tắc chuyển đổi ở cấp item.

