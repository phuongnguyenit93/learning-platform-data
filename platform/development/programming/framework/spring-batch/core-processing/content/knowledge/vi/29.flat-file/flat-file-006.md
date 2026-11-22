# BeanWrapperFieldSetMapper

Trong Spring Batch, `BeanWrapperFieldSetMapper` là một implementation của `FieldSetMapper<T>` dùng để chuyển một `FieldSet` thành Java object. Nó dựa trên cơ chế `BeanWrapper` của Spring để gán giá trị từng cột vào property tương ứng của bean.

Mapper này thường được dùng cùng `FlatFileItemReader`: reader đọc một dòng, `LineTokenizer` tách dòng thành các field, tạo `FieldSet`, rồi `BeanWrapperFieldSetMapper` bind các field đó vào object như `Order`, `Customer` hoặc `Employee`.

Điểm thuận tiện là không cần viết thủ công các lệnh `fieldSet.readString(...)`, `readBigDecimal(...)` rồi gọi setter cho từng thuộc tính. Tuy nhiên, tên field cần khớp với property của JavaBean, kiểu dữ liệu phải chuyển đổi được và các lỗi binding cần được xử lý rõ ràng.

## 1. FieldSetMapper nằm ở đâu trong luồng đọc file?

Với `FlatFileItemReader`, việc chuyển một dòng text thành object thường đi qua các thành phần:

1. `Resource` cung cấp file đầu vào.
2. `LineMapper` nhận từng dòng text.
3. `LineTokenizer` tách dòng thành các field.
4. Tokenizer tạo `FieldSet` gồm giá trị và tên field.
5. `FieldSetMapper` chuyển `FieldSet` thành object nghiệp vụ.
6. Reader trả object cho processor của Step.

```text
orders.csv
   |
   v
FlatFileItemReader
   |
   v
LineMapper
   |
   v
DelimitedLineTokenizer
   |
   v
FieldSet
   |  orderId = "1001"
   |  customerName = "Lan"
   |  amount = "125.50"
   v
BeanWrapperFieldSetMapper<Order>
   |
   v
Order
   |  orderId = 1001L
   |  customerName = "Lan"
   |  amount = 125.50
```

`BeanWrapperFieldSetMapper` chỉ phụ trách bước cuối: ánh xạ `FieldSet` vào bean. Nó không tự đọc file, không tự tách delimiter và không thay thế validation nghiệp vụ của processor.

## 2. FieldSet là gì?

`FieldSet` là abstraction của Spring Batch đại diện cho các giá trị đã được tokenizer tách ra từ một dòng. FieldSet có thể đọc giá trị theo vị trí hoặc theo tên:

```java
String orderId = fieldSet.readString("orderId");
BigDecimal amount = fieldSet.readBigDecimal("amount");
```

Tên field được xác định bởi cấu hình tokenizer, ví dụ `.names(...)` trong builder. Khi dùng `BeanWrapperFieldSetMapper`, các tên này được dùng để tìm property tương ứng trên target bean.

Ví dụ file:

```csv
order_id,customer_name,amount
1001,Lan,125.50
1002,Minh,89.00
```

Tokenizer có thể gán tên cho các cột:

```java
.delimited()
.delimiter(",")
.names("orderId", "customerName", "amount")
```

Khi đó `FieldSet` của dòng thứ hai có các field tên `orderId`, `customerName` và `amount`. Nếu target class có các property tương ứng, mapper có thể bind trực tiếp.

Tên header trong file không tự động quyết định tên property trong mọi cấu hình. Nếu dùng `.names(...)`, đó là tên do cấu hình cung cấp; nếu cần đọc header để xác định cột, phải cấu hình reader/tokenizer theo cách phù hợp.

## 3. JavaBean cần có gì để BeanWrapperFieldSetMapper bind được?

`BeanWrapperFieldSetMapper` dùng property access của Spring. Target class thường cần:

- Một constructor không tham số để mapper tạo instance khi dùng `targetType`.
- Property có setter công khai hoặc property writable tương ứng.
- Tên property khớp với tên field trong `FieldSet`, hoặc có thể được tìm bằng cơ chế fuzzy matching đã cấu hình.
- Kiểu dữ liệu có thể chuyển đổi từ giá trị text sang kiểu của property.

Ví dụ model:

```java
public class Order {

    private Long orderId;
    private String customerName;
    private BigDecimal amount;

    public Order() {
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
```

Nếu model chỉ có constructor nhận tham số và không có setter, cách bind JavaBean thông thường sẽ không phù hợp. Khi đó, có thể dùng custom `FieldSetMapper` để gọi constructor hoặc factory method theo đúng thứ tự và quy tắc dữ liệu.

## 4. Cấu hình BeanWrapperFieldSetMapper bằng targetType

Cách cấu hình phổ biến là tạo mapper, gọi `setTargetType(...)`, rồi truyền mapper vào `FlatFileItemReader`:

```java
@Bean
public FieldSetMapper<Order> orderFieldSetMapper() {
    BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
    mapper.setTargetType(Order.class);
    return mapper;
}

@Bean
public FlatFileItemReader<Order> orderReader(
        Resource orderResource,
        FieldSetMapper<Order> orderFieldSetMapper) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(orderResource)
            .delimited()
            .delimiter(",")
            .names("orderId", "customerName", "amount")
            .fieldSetMapper(orderFieldSetMapper)
            .build();
}
```

`setTargetType(Order.class)` cho mapper biết class cần tạo. Sau đó mapper tạo instance và bind các giá trị trong FieldSet vào các property phù hợp.

Builder và API có thể khác giữa các phiên bản Spring Batch, nhưng nguyên tắc không đổi: cấu hình `FieldSetMapper` cho reader và cung cấp target type cho `BeanWrapperFieldSetMapper`.

## 5. Ví dụ kết quả ánh xạ

Giả sử tokenizer tạo FieldSet từ dòng:

```text
1001,Lan,125.50
```

Với tên field:

```java
.names("orderId", "customerName", "amount")
```

Mapper sẽ tìm các property tương ứng và chuyển kiểu:

| FieldSet | Giá trị dạng text | Property Java | Kiểu property |
|---|---|---|---|
| `orderId` | `"1001"` | `orderId` | `Long` |
| `customerName` | `"Lan"` | `customerName` | `String` |
| `amount` | `"125.50"` | `amount` | `BigDecimal` |

Kết quả tương đương một object:

```java
Order order = new Order();
order.setOrderId(1001L);
order.setCustomerName("Lan");
order.setAmount(new BigDecimal("125.50"));
```

Đây là mapping tự động dựa trên tên property và conversion service/property editor của Spring. Không cần viết các setter này trong một mapper thủ công cho mọi dòng.

## 6. Chuyển đổi kiểu dữ liệu

Giá trị đọc từ file thường là text, trong khi property của bean có thể là `Long`, `Integer`, `BigDecimal`, `LocalDate`, `Boolean` hoặc kiểu khác. `BeanWrapperFieldSetMapper` dựa vào cơ chế chuyển đổi của Spring để bind giá trị vào kiểu property.

Các chuyển đổi phổ biến có thể thực hiện được khi định dạng đầu vào phù hợp:

| Giá trị file | Kiểu đích | Ví dụ |
|---|---|---|
| `"1001"` | `Long` | ID |
| `"25"` | `Integer` | Số lượng |
| `"125.50"` | `BigDecimal` | Số tiền |
| `"true"` | `Boolean` | Cờ trạng thái |
| `"2026-11-15"` | `LocalDate` | Ngày ISO, nếu conversion được cấu hình hỗ trợ |

Không nên giả định mọi định dạng ngày hoặc số đều được chuyển đổi theo đúng quy tắc nghiệp vụ. Ví dụ `15/11/2026`, `11/15/2026` và `2026-11-15` có thể mang ý nghĩa khác nhau tùy locale. Hãy cấu hình conversion tường minh khi dữ liệu có format riêng.

## 7. Cấu hình ConversionService cho định dạng riêng

Khi file dùng định dạng ngày riêng, có thể cung cấp `ConversionService` cho mapper. Ví dụ, file chứa ngày theo `dd/MM/yyyy`:

```java
@Bean
public ConversionService orderConversionService() {
    DefaultConversionService conversionService = new DefaultConversionService();
    conversionService.addConverter(String.class, LocalDate.class,
            value -> LocalDate.parse(value, DateTimeFormatter.ofPattern("dd/MM/yyyy")));
    return conversionService;
}

@Bean
public FieldSetMapper<Order> orderFieldSetMapper(
        ConversionService orderConversionService) {

    BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
    mapper.setTargetType(Order.class);
    mapper.setConversionService(orderConversionService);
    return mapper;
}
```

Model có property:

```java
private LocalDate orderDate;

public LocalDate getOrderDate() {
    return orderDate;
}

public void setOrderDate(LocalDate orderDate) {
    this.orderDate = orderDate;
}
```

Tokenizer cần đặt tên field `orderDate`. Conversion service chuyển text sang `LocalDate` theo format đã quy định.

Trong ứng dụng thực tế, hãy dùng `DateTimeFormatter` bất biến và format rõ ràng. Nếu nhiều loại file dùng định dạng khác nhau, có thể cần mapper/conversion service riêng theo từng loại nguồn thay vì một converter toàn cục có quy tắc mơ hồ.

## 8. Sử dụng custom PropertyEditor

Ngoài `ConversionService`, Spring `BeanWrapper` còn hỗ trợ `PropertyEditor` để chuyển đổi giá trị. `BeanWrapperFieldSetMapper` có thể được cấu hình custom editors cho các kiểu cần xử lý đặc biệt, tùy API của phiên bản đang dùng.

Ví dụ ý tưởng với một editor cho ngày:

```java
public class OrderDateEditor extends PropertyEditorSupport {

    private final DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern("dd/MM/yyyy");

    @Override
    public void setAsText(String text) {
        setValue(LocalDate.parse(text, formatter));
    }
}
```

Có thể đăng ký editor cho `LocalDate` thông qua cấu hình `customEditors` của mapper:

```java
Map<Class<?>, PropertyEditor> editors = new HashMap<>();
editors.put(LocalDate.class, new OrderDateEditor());
mapper.setCustomEditors(editors);
```

`PropertyEditor` có trạng thái và không phải implementation nào cũng an toàn khi chia sẻ giữa thread. Hãy kiểm tra lifecycle của editor và cách mapper sử dụng nó trong phiên bản Spring Batch của dự án. Với ứng dụng mới, `ConversionService`/`Converter` thường dễ kiểm thử và thể hiện quy tắc chuyển đổi rõ ràng hơn.

## 9. Field name và bean property name

Thông thường, tên field do tokenizer cung cấp nên khớp chính xác với tên property JavaBean. Ví dụ:

```java
.names("orderId", "customerName", "amount")
```

với bean có property `orderId`, `customerName` và `amount`.

Nếu file dùng header `ORDER_ID`, `CUSTOMER_NAME`, `TOTAL_AMOUNT`, không nên giả định mapper tự chuyển mọi kiểu đặt tên thành property camelCase theo đúng quy tắc nghiệp vụ. Hãy chủ động cấu hình tên field hoặc dùng custom mapper để ánh xạ alias.

Ví dụ tokenizer đặt tên theo property dù header file khác:

```java
.delimited()
.names("orderId", "customerName", "amount")
```

Nếu cột đầu vào có tên khác và cần quy tắc chuyển đổi riêng, custom `FieldSetMapper` sẽ làm ý định rõ ràng hơn.

## 10. Fuzzy matching và distanceLimit

`BeanWrapperFieldSetMapper` hỗ trợ tìm property gần giống tên field trong một giới hạn khoảng cách. Điều này có thể giúp xử lý một số khác biệt nhỏ về tên, nhưng không nên xem fuzzy matching là cơ chế mapping nghiệp vụ chính.

Ví dụ, field name `customerNmae` có thể được xem là gần với property `customerName` do lỗi đảo ký tự. Mapper có thể tìm property gần nhất nếu cấu hình distance limit cho phép.

Có thể cấu hình giới hạn khoảng cách bằng `setDistanceLimit(...)`:

```java
BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
mapper.setTargetType(Order.class);
mapper.setDistanceLimit(2);
```

Distance limit càng nhỏ thì việc chấp nhận tên gần giống càng chặt. Giá trị và cách đo khoảng cách phụ thuộc implementation/phiên bản; nên cấu hình tường minh và kiểm tra trên schema field thực tế thay vì dựa vào default.

Fuzzy matching có rủi ro ánh xạ nhầm nếu bean có các property gần giống nhau, ví dụ `orderDate` và `orderData`. Với dữ liệu tài chính hoặc dữ liệu quan trọng, nên dùng tên chính xác hoặc custom mapper để tránh bind nhầm âm thầm.

## 11. Strict mode và field không có property tương ứng

Strict mode quyết định mapper xử lý thế nào khi không tìm được property phù hợp cho một field. Với cấu hình strict, field không thể bind sẽ tạo lỗi mapping; chế độ không strict có thể bỏ qua field không khớp tùy hành vi implementation.

Ví dụ cấu hình rõ ràng:

```java
BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
mapper.setTargetType(Order.class);
mapper.setStrict(true);
```

Strict mode phù hợp khi file có schema cố định và mọi cột đều phải được xử lý. Nếu upstream thêm cột không dùng đến, strict có thể khiến Job thất bại; khi đó cần quyết định có cho phép cột dư hay không.

Không nên tắt strict chỉ để che giấu lỗi đánh máy trong tên field. Nếu field `amount` vô tình thành `amout`, bỏ qua mapping có thể khiến property giữ giá trị mặc định và dữ liệu sai vẫn đi tiếp. Hãy kiểm tra schema đầu vào và chọn chính sách rõ ràng.

## 12. Mapping nested property

`BeanWrapper` của Spring hỗ trợ property path, vì vậy có thể ánh xạ field đến property lồng nhau khi object graph và các setter/getter phù hợp.

Ví dụ model:

```java
public class CustomerOrder {
    private Long orderId;
    private Address address;

    public CustomerOrder() {
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}

public class Address {
    private String city;

    public Address() {
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
```

Tokenizer có thể cung cấp field name `address.city` nếu property path và object graph được mapper hỗ trợ:

```java
.names("orderId", "address.city")
```

BeanWrapper có khả năng auto-grow nested path trong một số cấu hình, nhưng object graph phức tạp, collection hoặc property không thể khởi tạo có thể gây lỗi. Hãy test nested mapping với model thực tế. Nếu việc tạo object con cần quy tắc nghiệp vụ, custom mapper thường rõ ràng hơn.

## 13. Dùng prototypeBeanName thay cho targetType

`setTargetType(...)` phù hợp khi mapper có thể tạo bean bằng constructor không tham số. Nếu cần Spring tạo target từ bean prototype đã cấu hình dependency hoặc factory method, có thể dùng `prototypeBeanName` và `BeanFactory`.

Ví dụ cấu hình prototype bean:

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public Order orderPrototype(OrderDefaults defaults) {
    Order order = new Order();
    order.setCurrency(defaults.currency());
    return order;
}

@Bean
public FieldSetMapper<Order> orderFieldSetMapper(
        BeanFactory beanFactory) {

    BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
    mapper.setBeanFactory(beanFactory);
    mapper.setPrototypeBeanName("orderPrototype");
    return mapper;
}
```

Trong trường hợp này, mapper lấy một prototype bean mới khi cần map từng FieldSet. Không cấu hình đồng thời `targetType` và `prototypeBeanName` theo cách mâu thuẫn; chọn cơ chế tạo object phù hợp với model.

Prototype bean hữu ích khi object cần dependency hoặc giá trị khởi tạo do Spring quản lý. Nếu model đơn giản và có constructor mặc định, `targetType` thường ngắn gọn hơn.

## 14. Tích hợp đầy đủ với FlatFileItemReader

Ví dụ cấu hình đọc CSV có header:

```java
@Bean
public FieldSetMapper<Order> orderFieldSetMapper(
        ConversionService orderConversionService) {

    BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
    mapper.setTargetType(Order.class);
    mapper.setConversionService(orderConversionService);
    mapper.setStrict(true);
    return mapper;
}

@Bean
public FlatFileItemReader<Order> orderReader(
        Resource orderFile,
        FieldSetMapper<Order> orderFieldSetMapper) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(orderFile)
            .linesToSkip(1)
            .delimited()
            .delimiter(",")
            .names("orderId", "customerName", "amount", "orderDate")
            .fieldSetMapper(orderFieldSetMapper)
            .saveState(true)
            .build();
}
```

Ở đây:

- `linesToSkip(1)` bỏ qua dòng header.
- `.names(...)` cung cấp tên field cho các cột theo đúng thứ tự.
- `BeanWrapperFieldSetMapper` tạo `Order` và bind các property.
- `ConversionService` xử lý kiểu dữ liệu cần chuyển đổi.
- `saveState(true)` lưu state reader để hỗ trợ restart.

Tên và thứ tự trong `.names(...)` phải khớp với schema file. Nếu thứ tự cột thay đổi, reader có thể bind sai dữ liệu dù tên property đúng.

## 15. Khi nào nên dùng custom FieldSetMapper?

`BeanWrapperFieldSetMapper` phù hợp khi cấu trúc file gần với cấu trúc JavaBean và mapping chủ yếu là gán property. Một custom mapper phù hợp hơn khi:

- Tên cột và tên property khác nhau đáng kể.
- Một field nguồn cần tạo nhiều property đích.
- Nhiều field cần kết hợp thành một object value.
- Cần quy tắc parse đặc biệt theo từng cột.
- Cần chuẩn hóa hoặc tính giá trị trong lúc mapping.
- Target là immutable object/record hoặc không có constructor không tham số.
- Cần xử lý các trường hợp null/blank theo quy tắc nghiệp vụ phức tạp.

Ví dụ custom mapper:

```java
public class OrderFieldSetMapper implements FieldSetMapper<Order> {

    @Override
    public Order mapFieldSet(FieldSet fieldSet) {
        Order order = new Order();
        order.setOrderId(fieldSet.readLong("order_id"));
        order.setCustomerName(fieldSet.readString("customer_name").trim());
        order.setAmount(fieldSet.readBigDecimal("total_amount"));
        return order;
    }
}
```

Ở đây, custom mapper chủ động ánh xạ `order_id` sang `orderId`, `customer_name` sang `customerName` và `total_amount` sang `amount`. Logic nhìn thấy rõ, dễ kiểm soát khi schema file khác với model.

## 16. Phân biệt mapping với validation nghiệp vụ

Mapping trả lời câu hỏi: giá trị trong `FieldSet` được đưa vào property nào và chuyển thành kiểu Java nào? Validation trả lời câu hỏi: object sau khi tạo có hợp lệ theo nghiệp vụ hay không?

Ví dụ `amount="-100.00"` có thể parse thành `BigDecimal` thành công. Mapper không tự biết đơn hàng âm có được phép hay không. Quy tắc đó nên được xử lý trong processor hoặc validator chuyên biệt.

```java
@Bean
public ItemProcessor<Order, Order> validateOrderProcessor() {
    return order -> {
        if (order.getAmount().signum() < 0) {
            throw new InvalidOrderException("Order amount must not be negative");
        }
        return order;
    };
}
```

Tách mapping khỏi validation giúp phân loại lỗi rõ hơn:

- Lỗi binding/conversion: file không thể chuyển thành object đúng kiểu.
- Lỗi nghiệp vụ: object tạo được nhưng vi phạm quy tắc.
- Lỗi hệ thống: database, filesystem hoặc dịch vụ phụ thuộc gặp sự cố.

Spring Batch có thể áp dụng skip/retry policy cho các exception tương ứng. Tuy nhiên, không nên skip mọi lỗi binding hoặc mọi exception chung chung nếu điều đó làm mất dữ liệu quan trọng.

## 17. Lỗi binding thường gặp

Khi mapping thất bại, cần phân biệt nguyên nhân thay vì chỉ ghi “cannot map row”.

| Nguyên nhân | Ví dụ | Cách xử lý |
|---|---|---|
| Không có setter/property | FieldSet có `customerName`, bean không có property writable này | Sửa tên field/model hoặc dùng custom mapper |
| Không tạo được target | Class không có constructor phù hợp khi dùng `targetType` | Thêm constructor không tham số hoặc dùng prototype bean/custom mapper |
| Sai kiểu dữ liệu | `amount="abc"` nhưng property là `BigDecimal` | Kiểm tra dữ liệu và conversion rule |
| Sai format ngày | `15/11/2026` không khớp formatter | Cấu hình converter/formatter rõ ràng |
| Field name sai | `custmerName` thay vì `customerName` | Sửa `.names(...)`; tránh phụ thuộc fuzzy matching |
| Field dư | File có cột không có property | Xem lại strict mode hoặc bỏ cột khỏi mapping |
| Property nested không khởi tạo được | `address.city` nhưng `address` không thể tạo | Khởi tạo object graph hoặc custom mapper |

Lỗi chuyển đổi thường được bọc trong exception binding của Spring, chẳng hạn `BindException` hoặc exception liên quan property access. Loại exception thực tế phụ thuộc đường đi binding và phiên bản. Khi cấu hình skip, hãy dùng đúng exception hoặc root cause quan sát được trong log/test.

## 18. Strict mode, skip và lỗi dữ liệu

Nếu `BeanWrapperFieldSetMapper` không thể bind một dòng, `FlatFileItemReader` có thể ném exception và Step áp dụng fault tolerance nếu đã cấu hình.

Ví dụ cho phép skip một số dòng parse/binding lỗi:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(validateOrderProcessor())
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(20)
        .build();
```

Đây chỉ là ví dụ cho lỗi parse ở reader; lỗi binding cụ thể có thể có loại exception khác và cần xác nhận bằng test. Không nên giả định mọi lỗi do BeanWrapper đều là `FlatFileParseException`.

Nếu file có lỗi schema như tên cột sai hoặc thiếu cột bắt buộc, bỏ qua từng dòng có thể không hợp lý vì mọi dòng đều có thể bị map sai. Hãy kiểm tra header/schema trước khi đọc dữ liệu và fail sớm khi cấu trúc file không đúng hợp đồng.

## 19. Hiệu năng và tính an toàn khi dùng mapper

`BeanWrapperFieldSetMapper` dùng reflection/property access và conversion để tạo object. Với phần lớn batch job, chi phí này hợp lý và giảm lượng code mapping thủ công. Nếu xử lý hàng chục triệu dòng, hãy đo throughput thực tế trước khi thay mapper vì lý do hiệu năng.

Một số nguyên tắc:

- Cấu hình mapper một lần trước khi Step chạy; không thay đổi target type, editor hoặc conversion service giữa lúc đang xử lý.
- Dùng converter bất biến và có thể tái sử dụng.
- Tránh converter phụ thuộc mutable state theo từng item.
- Giữ mapping đơn giản; chuyển logic nghiệp vụ phức tạp sang processor.
- Nếu Step chạy đa luồng, kiểm tra thread safety của converter/editor tùy chỉnh và mọi state dùng chung.
- Không lưu dữ liệu nhạy cảm vào exception message hoặc log toàn bộ dòng nếu file có thông tin cá nhân.

Nếu cần mapping phức tạp, custom mapper có thể vừa rõ ràng vừa hiệu quả hơn. Lựa chọn dựa trên độ phức tạp schema và khả năng bảo trì, không chỉ dựa trên số dòng code.

## 20. Kiểm thử BeanWrapperFieldSetMapper

Có thể kiểm thử mapper độc lập mà không cần chạy toàn bộ Job. Tạo `FieldSet`, gọi `mapFieldSet()` rồi xác nhận property được gán đúng.

Ví dụ:

```java
@Test
void mapsFieldSetToOrderBean() throws Exception {
    BeanWrapperFieldSetMapper<Order> mapper = new BeanWrapperFieldSetMapper<>();
    mapper.setTargetType(Order.class);

    FieldSet fieldSet = new DefaultFieldSet(
            new String[] {"1001", "Lan", "125.50"},
            new String[] {"orderId", "customerName", "amount"}
    );

    Order order = mapper.mapFieldSet(fieldSet);

    assertEquals(1001L, order.getOrderId());
    assertEquals("Lan", order.getCustomerName());
    assertEquals(new BigDecimal("125.50"), order.getAmount());
}
```

Ngoài trường hợp thành công, nên kiểm thử:

1. Giá trị số không hợp lệ cho property số.
2. Ngày theo format đúng và sai.
3. Field name không có property tương ứng khi strict bật.
4. Field name gần giống property khi cấu hình distance limit.
5. Field không khớp khi strict tắt, xác nhận hành vi bỏ qua theo implementation.
6. Nested property có object graph hợp lệ và không hợp lệ.
7. Target class không có constructor không tham số.
8. File có header, delimiter, quote và encoding thực tế.
9. Job restart sau khi một số chunk đã commit.

Integration test với `FlatFileItemReader` giúp xác nhận tokenizer tạo đúng FieldSet và mapper nhận đúng tên/giá trị cột. Unit test mapper riêng không kiểm tra được delimiter, quote, header hoặc cấu hình Resource.

## 21. Những nhầm lẫn thường gặp

**Cho rằng BeanWrapperFieldSetMapper đọc file.** Nó chỉ map `FieldSet` thành object; `FlatFileItemReader`, `LineMapper` và tokenizer đảm nhiệm việc đọc/tách dòng.

**Cho rằng tên header tự động khớp với Java property.** Tên field đến từ cấu hình tokenizer hoặc cơ chế header được cấu hình. Hãy xác định tên cột rõ ràng.

**Cho rằng mọi kiểu dữ liệu đều tự chuyển đổi đúng format.** Chuyển đổi phụ thuộc conversion service/property editor. Ngày, tiền tệ và locale cần cấu hình tường minh.

**Cho rằng fuzzy matching luôn an toàn.** Hai property gần tên nhau có thể bị bind nhầm. Ưu tiên tên chính xác và test distance limit.

**Cho rằng strict=false giải quyết mọi lỗi schema.** Nó có thể bỏ qua field không map được, nhưng không xác nhận dữ liệu nguồn đúng. Schema sai có thể làm object thiếu giá trị.

**Dùng mapper để kiểm tra quy tắc nghiệp vụ.** Mapper chuyển đổi cấu trúc và kiểu dữ liệu; processor/validator nên kiểm tra quy tắc nghiệp vụ.

**Dùng BeanWrapperFieldSetMapper cho immutable object mà không có factory phù hợp.** Nếu không thể tạo và set property theo JavaBean, dùng prototype bean hoặc custom mapper.

## 22. Cách lựa chọn mapper cho flat file

Dùng `BeanWrapperFieldSetMapper` khi tên cột có thể được cấu hình khớp với JavaBean property, target có thể được tạo và các giá trị chuyển đổi bằng conversion service/property editor. Cấu hình `targetType`, strict mode và conversion rule rõ ràng; chỉ bật fuzzy matching khi có lý do và đã kiểm thử.

Nếu file có schema khác model, cần alias phức tạp, tạo object lồng nhau theo quy tắc riêng hoặc target immutable, hãy dùng custom `FieldSetMapper`. Giữ validation nghiệp vụ trong processor hoặc validator để mapping không bị trộn với quyết định nghiệp vụ.

Khi tích hợp với `FlatFileItemReader`, kiểm tra toàn bộ chuỗi từ Resource, tokenizer, tên FieldSet, mapper đến model. Với file production, kiểm thử cả dữ liệu hợp lệ, lỗi chuyển đổi, schema thay đổi, skip policy và restart. Cách tổ chức đó giúp `BeanWrapperFieldSetMapper` giảm code mapping mà vẫn giữ việc nhập file rõ ràng và có thể kiểm soát.
