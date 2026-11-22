# Tách kiểm tra cú pháp, ánh xạ kiểu và kiểm tra nghiệp vụ

Khi nhận JSON từ client hoặc hệ thống bên ngoài, ứng dụng cần xác định dữ liệu có hợp lệ hay không. Tuy nhiên, “hợp lệ” có nhiều nghĩa khác nhau. Một chuỗi có thể là JSON đúng cú pháp nhưng không phù hợp với kiểu Java mà API yêu cầu; một object có thể ánh xạ thành DTO thành công nhưng vẫn vi phạm quy tắc nghiệp vụ.

Vì vậy, nên tách quá trình kiểm tra đầu vào thành các lớp rõ ràng:

1. **Kiểm tra cú pháp và cấu trúc JSON:** dữ liệu có phải JSON hợp lệ, có đúng một document, không vượt giới hạn đọc và có hình dạng cơ bản phù hợp không?
2. **Ánh xạ kiểu:** JSON có chuyển được thành DTO/Java type theo hợp đồng Jackson không? Field có đúng kiểu, tên, format và subtype được phép không?
3. **Kiểm tra ràng buộc dữ liệu:** các giá trị sau khi ánh xạ có đáp ứng constraint như bắt buộc, độ dài, định dạng email, số dương hoặc quan hệ giữa các field không?
4. **Kiểm tra nghiệp vụ:** thao tác có hợp lệ trong trạng thái hệ thống hiện tại không, ví dụ số lượng tồn kho đủ, tài khoản có quyền, ngày giao hàng không trước ngày đặt hàng và mã tham chiếu có tồn tại không?

Mỗi lớp có mục tiêu, công cụ và loại lỗi khác nhau. Jackson chủ yếu xử lý parse JSON và binding dữ liệu vào Java type. Bean Validation kiểm tra constraint trên object đã tạo. Domain/application service kiểm tra invariant và quy tắc phụ thuộc nghiệp vụ hoặc dữ liệu bên ngoài. Không nên dồn mọi quy tắc vào custom deserializer hoặc coi việc deserialize thành công là bằng chứng request hợp lệ.

Các ví dụ sử dụng Jackson 2.x, Java 17 và Jakarta Bean Validation (`jakarta.validation`). Với dự án cũ dùng Bean Validation 2.0, import có thể là `javax.validation`; hãy dùng namespace tương ứng với phiên bản framework.

## 1. Bốn lớp kiểm tra có trách nhiệm khác nhau

Một luồng xử lý request điển hình:

```text
HTTP body / message / file
          |
          v
  1. Parse JSON syntax
     - token hợp lệ
     - đúng một document
     - giới hạn kích thước/depth
          |
          v
  2. Jackson data binding
     - JSON -> DTO/Java type
     - tên field, kiểu, format, subtype
          |
          v
  3. Bean Validation
     - @NotNull, @Size, @Positive
     - cross-field constraints
          |
          v
  4. Domain/business validation
     - quyền, trạng thái, tồn kho
     - dữ liệu tham chiếu, transaction
          |
          v
       Thực hiện use case
```

| Lớp | Câu hỏi cần trả lời | Ví dụ lỗi | Nơi xử lý phù hợp |
|---|---|---|---|
| Cú pháp JSON | Body có phải JSON hợp lệ không? | Thiếu dấu `}`, dấu nháy không đóng, token sai | Jackson Core parser / HTTP message converter |
| Ánh xạ kiểu | JSON có phù hợp DTO và kiểu Java không? | `quantity` là object trong khi cần integer; ngày sai format; subtype không biết | Jackson Databind, DTO và cấu hình mapper |
| Ràng buộc dữ liệu | Giá trị trong DTO có đáp ứng constraint khai báo không? | Tên rỗng, email sai format, số lượng âm | Jakarta Bean Validation |
| Nghiệp vụ | Yêu cầu có hợp lệ với trạng thái hệ thống không? | Hết hàng, đơn đã hủy, người gọi không sở hữu tài nguyên | Domain model / application service |

Một request có thể vượt qua ba lớp đầu nhưng vẫn thất bại ở lớp nghiệp vụ. Ví dụ `quantity = 2` là JSON hợp lệ, ánh xạ thành `int` được, thỏa `@Positive`, nhưng kho chỉ còn một sản phẩm. Đây không phải lỗi cú pháp hay lỗi Jackson.

## 2. Lớp 1: kiểm tra cú pháp JSON

JSON parser kiểm tra cấu trúc từ vựng và cú pháp của JSON: dấu ngoặc, dấu nháy, dấu phẩy, dấu hai chấm, literal `true`/`false`/`null` và dạng number. Ví dụ sau hợp lệ:

```json
{
  "orderId": "ORD-100",
  "quantity": 2,
  "gift": false
}
```

Các ví dụ sau không hợp lệ về cú pháp:

```text
{"orderId":"ORD-100", "quantity": 2,}
```

```text
{'orderId':'ORD-100'}
```

```text
{"orderId":"ORD-100" "quantity":2}
```

Lỗi ở lớp này thường được biểu diễn bằng `JsonParseException` hoặc một subtype của `JsonProcessingException`. Parser chưa cần biết `quantity` có phải số lượng hợp lệ trong nghiệp vụ hay không; nó chỉ biết token JSON có hợp lệ không.

### 2.1. Parse thành `JsonNode` để kiểm tra cú pháp độc lập

Nếu cần phân biệt rõ bước parse với bước binding DTO, có thể parse body thành cây:

```java
ObjectMapper mapper = new ObjectMapper();

JsonNode root = mapper.readTree(jsonText);
if (root == null || !root.isObject()) {
    throw new IllegalArgumentException("Expected a JSON object");
}
```

`readTree()` buộc Jackson đọc JSON thành `JsonNode`; lỗi cú pháp sẽ được phát hiện trong lúc parse. Kiểm tra `isObject()` là kiểm tra hình dạng root, không phải kiểm tra toàn bộ schema hay nghiệp vụ.

Nếu JSON hợp lệ nhưng root là array trong khi API yêu cầu object, parse vẫn thành công. Ứng dụng cần kiểm tra root shape hoặc để bước binding vào DTO báo lỗi phù hợp.

### 2.2. Đảm bảo chỉ có một JSON document

Một số API cần từ chối nội dung có JSON value thứ hai nối sau document đầu tiên. Có thể bật `FAIL_ON_TRAILING_TOKENS`:

```java
ObjectMapper strictMapper = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
```

Ví dụ body:

```text
{"orderId":"ORD-100"} {"admin":true}
```

JSON object đầu tiên hợp lệ, nhưng toàn bộ body chứa thêm một root value. Với hợp đồng một document, phần dữ liệu thừa phải bị từ chối. `FAIL_ON_TRAILING_TOKENS` yêu cầu Jackson kiểm tra rằng không còn token ngoài whitespace sau value đã đọc.

Nếu giao thức chủ đích là nhiều root JSON value hoặc NDJSON, không áp dụng chính sách một document cho toàn bộ sequence. Hãy dùng API sequence tương ứng và định nghĩa framing rõ ràng.

### 2.3. Phát hiện duplicate object key

JSON object nên có tên property duy nhất. Payload sau có duplicate key:

```json
{
  "role": "user",
  "role": "admin"
}
```

Nhiều parser có thể giữ giá trị xuất hiện sau cùng hoặc xử lý theo quy tắc riêng. Nếu duplicate key có thể gây khác biệt giữa gateway, validator và service, hãy bật strict duplicate detection ở parser factory:

```java
JsonFactory factory = JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Tùy version Jackson 2.x, API cũ `JsonParser.Feature.STRICT_DUPLICATE_DETECTION` cũng có thể xuất hiện; nên dùng API factory/stream feature phù hợp với version được quản lý trong dự án. Duplicate detection có thêm chi phí bộ nhớ và CPU, vì parser phải theo dõi tên field trong object hiện tại.

### 2.4. Giới hạn tài nguyên khi parse

JSON có thể đúng cú pháp nhưng quá lớn hoặc quá sâu để xử lý an toàn. Hãy giới hạn request body ở HTTP server/gateway và cân nhắc `StreamReadConstraints` ở Jackson Core trong version hỗ trợ:

```java
JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(StreamReadConstraints.builder()
                .maxNestingDepth(100)
                .maxStringLength(1_000_000)
                .maxNumberLength(1_000)
                .build())
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Các ngưỡng trong ví dụ chỉ minh họa; chọn giới hạn theo kích thước payload hợp lệ của ứng dụng. `StreamReadConstraints` có từ các version Jackson 2.x mới hơn; kiểm tra version thực tế trước khi dùng. Giới hạn ở parser không thay thế giới hạn body ở HTTP server vì server có thể đã nhận hoặc buffer dữ liệu trước khi Jackson đọc.

## 3. Lớp 2: ánh xạ JSON sang Java type

Sau khi JSON parse được, Jackson Databind chuyển token thành object Java theo target type. Ví dụ:

```java
public class CreateOrderRequest {
    private String productCode;
    private int quantity;
    private LocalDate deliveryDate;

    // getters và setters
}
```

JSON:

```json
{
  "productCode": "KB-01",
  "quantity": 2,
  "deliveryDate": "2026-11-12"
}
```

Jackson kiểm tra các token có thể được chuyển thành kiểu property hay không. Nếu `quantity` nhận một object thay vì number, binding thất bại. Nếu `deliveryDate` có format không được hỗ trợ hoặc thiếu Java Time module, binding có thể thất bại dù JSON vẫn đúng cú pháp.

Lỗi ở lớp này thường là `JsonMappingException` hoặc subtype, ví dụ `MismatchedInputException`, `InvalidFormatException`, `UnrecognizedPropertyException` hay lỗi không tìm được subtype. Đây là lỗi ánh xạ, không phải lỗi JSON syntax.

### 3.1. Dùng DTO rõ ràng cho hợp đồng input

Không nên deserialize mọi request vào entity database hoặc một `Map<String, Object>` không có schema nếu hợp đồng cần kiểu cụ thể. DTO cho biết field nào được hỗ trợ và kiểu mong đợi:

```java
public record CreateOrderRequest(
        String productCode,
        Integer quantity,
        LocalDate deliveryDate) {
}
```

Wrapper type như `Integer` giúp phân biệt giá trị thiếu/null với số 0. Nếu dùng primitive `int`, giá trị mặc định có thể là `0` khi field bị thiếu, tùy creator/binding mode. Với dữ liệu bắt buộc, wrapper thường kết hợp tốt hơn với `@NotNull`.

### 3.2. Cấu hình unknown property

Mặc định Jackson Databind thường bật `FAIL_ON_UNKNOWN_PROPERTIES`, nhưng framework có thể cấu hình khác. Khi bật, JSON có field không có trong DTO sẽ gây lỗi:

```json
{
  "productCode": "KB-01",
  "quantity": 2,
  "debug": true
}
```

Nếu `CreateOrderRequest` không có `debug`, Jackson có thể báo `UnrecognizedPropertyException`.

Có thể tắt feature cho một reader cụ thể:

```java
ObjectReader reader = mapper.readerFor(CreateOrderRequest.class)
        .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

CreateOrderRequest request = reader.readValue(jsonText);
```

Tolerant input hữu ích khi API cần tương thích với client gửi thêm field, nhưng cũng có thể che typo như `quanity`. Chọn strict hay tolerant theo hợp đồng; không nên tắt toàn cục chỉ vì một endpoint cần tương thích.

### 3.3. Kiểm soát coercion và sai kiểu

Jackson có thể chuyển đổi một số giá trị giữa các scalar type theo cấu hình coercion. Ví dụ, tùy mapper và version, chuỗi `"2"` có thể được chuyển thành integer `2`.

Nếu API yêu cầu JSON number, không nên vô tình chấp nhận JSON string:

```json
{"quantity":"2"}
```

Hãy kiểm soát coercion bằng cấu hình phù hợp với Jackson version, hoặc dùng custom deserializer khi contract yêu cầu strict token type. Test phải phân biệt `2` và `"2"`; đừng chỉ assert giá trị Java cuối cùng nếu cả hai input đều có thể được coercion.

Với Jackson 2.12 trở lên, `CoercionConfig` cho phép đặt hành vi theo logical type hoặc class cụ thể. Vì default và API có thể khác giữa version, hãy cấu hình rõ và test input biên thay vì phụ thuộc vào hành vi ngầm.

### 3.4. Kiểm tra định dạng và module

Một JSON string có thể parse được nhưng không ánh xạ được thành kiểu đích. Ví dụ:

```json
{"deliveryDate":"12/11/2026"}
```

Nếu DTO dùng `LocalDate` và mapper chỉ chấp nhận ISO `yyyy-MM-dd`, binding thất bại. Có thể quy định format bằng `@JsonFormat`:

```java
public record CreateOrderRequest(
        String productCode,
        Integer quantity,
        @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "dd/MM/uuuu")
        LocalDate deliveryDate) {
}
```

Mapper cũng cần Java Time module:

```java
ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
```

Format kiểm soát cách biểu diễn/parse kiểu dữ liệu. Nó không chứng minh ngày đó có ý nghĩa hợp lệ trong nghiệp vụ. `31/02/2026` vẫn là chuỗi JSON hợp lệ nhưng không phải ngày lịch hợp lệ và sẽ bị từ chối ở bước parse date.

## 4. Ánh xạ kiểu thành công không đồng nghĩa dữ liệu có giá trị hợp lệ

Giả sử DTO:

```java
public record CreateOrderRequest(
        String productCode,
        Integer quantity) {
}
```

JSON:

```json
{
  "productCode": "",
  "quantity": -10
}
```

Jackson có thể ánh xạ thành công vì `productCode` là string và `quantity` là integer. Nhưng dữ liệu không đáp ứng yêu cầu đầu vào: mã sản phẩm rỗng và số lượng âm.

Đây là nhiệm vụ của validation layer. Jackson không nên tự quyết định `quantity` phải lớn hơn 0 chỉ vì nó đang deserialize một property có kiểu `Integer`.

Một phân chia trách nhiệm tốt:

- Jackson: “Token này có thể trở thành `Integer` không?”
- Bean Validation: “Giá trị `Integer` này có lớn hơn 0 không?”
- Domain service: “Sản phẩm này có bán được và kho có đủ số lượng không?”

## 5. Lớp 3: kiểm tra constraint bằng Bean Validation

Jakarta Bean Validation cung cấp annotation khai báo constraint trên DTO hoặc domain object. Các constraint phổ biến:

| Annotation | Ý nghĩa |
|---|---|
| `@NotNull` | Giá trị không được null |
| `@NotBlank` | String phải khác null và có ít nhất một ký tự không phải whitespace |
| `@NotEmpty` | String/collection/map/array không được null hoặc rỗng |
| `@Size(min, max)` | Giới hạn độ dài hoặc số phần tử |
| `@Positive` | Số phải lớn hơn 0 |
| `@PositiveOrZero` | Số phải lớn hơn hoặc bằng 0 |
| `@Min` / `@Max` | Giới hạn số nguyên theo ngưỡng |
| `@DecimalMin` / `@DecimalMax` | Giới hạn số thập phân |
| `@Email` | Kiểm tra định dạng email theo validator implementation |
| `@Pattern` | Kiểm tra chuỗi theo regular expression |
| `@Past` / `@Future` | Kiểm tra mốc thời gian tương đối với hiện tại |

Ví dụ DTO:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;

public record CreateOrderRequest(
        @NotBlank
        @Size(max = 40)
        String productCode,

        @NotNull
        @Positive
        Integer quantity,

        @NotNull
        LocalDate deliveryDate) {
}
```

Sau khi Jackson tạo DTO, gọi validator:

```java
ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
Validator validator = factory.getValidator();

Set<ConstraintViolation<CreateOrderRequest>> violations =
        validator.validate(request);

if (!violations.isEmpty()) {
    throw new ConstraintViolationException(violations);
}
```

`Validator` kiểm tra các annotation constraint trên object đã có. Nó không parse JSON và không thể kiểm tra property đã bị Jackson từ chối trước đó.

Trong ứng dụng server, `ValidatorFactory` thường được tạo và quản lý ở application startup; không tạo mới cho từng request. Framework như Spring Boot thường tự cấu hình Bean Validation khi dependency phù hợp đã có.

## 6. Phân biệt `@NotNull`, `@NotBlank` và `@NotEmpty`

Ba constraint này không thay thế cho nhau:

| Giá trị | `@NotNull` | `@NotEmpty` | `@NotBlank` |
|---|---:|---:|---:|
| `null` | Không hợp lệ | Không hợp lệ | Không hợp lệ |
| `""` | Hợp lệ | Không hợp lệ | Không hợp lệ |
| `"   "` | Hợp lệ | Hợp lệ | Không hợp lệ |
| `"An"` | Hợp lệ | Hợp lệ | Hợp lệ |
| Collection rỗng | Hợp lệ | Không hợp lệ | Không áp dụng cho collection |

Ví dụ, `productCode` thường cần `@NotBlank`; danh sách item có thể cần `@NotEmpty`; `quantity` cần `@NotNull` kết hợp `@Positive`.

Không giả định `@NotNull` sẽ loại chuỗi rỗng hoặc `@Size(min = 1)` sẽ tự từ chối null. Hầu hết constraint như `@Size` coi null là hợp lệ để có thể kết hợp với `@NotNull` khi cần.

## 7. Cascade validation cho object lồng nhau

Nếu request chứa object con, dùng `@Valid` để kích hoạt validation đệ quy:

```java
public record AddressRequest(
        @NotBlank String street,
        @NotBlank String city,
        @NotBlank String postalCode) {
}

public record CreateCustomerRequest(
        @NotBlank String name,
        @NotNull @Valid AddressRequest address) {
}
```

`@Valid` yêu cầu validator kiểm tra các constraint trong `AddressRequest`. Nếu thiếu `@Valid`, constraint bên trong object con có thể không được duyệt khi validate object cha.

Với collection:

```java
public record CreateOrderRequest(
        @NotEmpty
        List<@NotNull @Valid OrderLineRequest> lines) {
}
```

Ví dụ này yêu cầu danh sách không rỗng, mỗi phần tử không null và mỗi `OrderLineRequest` được validate. Cú pháp container element validation cần Bean Validation 2.0 trở lên.

Cascade validation chỉ kiểm tra constraint được khai báo trên object. Nó không tự tải entity liên quan từ database hoặc kiểm tra quyền sở hữu.

## 8. Kiểm tra quan hệ giữa các field bằng class-level constraint

Một số quy tắc liên quan nhiều property, ví dụ `endDate` phải sau `startDate`. Có thể dùng class-level constraint.

Annotation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DateRangeValidator.class)
public @interface ValidDateRange {
    String message() default "endDate must be on or after startDate";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

Validator:

```java
public class DateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingRequest> {

    @Override
    public boolean isValid(BookingRequest value,
                           ConstraintValidatorContext context) {
        if (value == null
                || value.startDate() == null
                || value.endDate() == null) {
            return true; // @NotNull kiểm tra riêng hai field.
        }

        return !value.endDate().isBefore(value.startDate());
    }
}
```

DTO:

```java
@ValidDateRange
public record BookingRequest(
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate) {
}
```

Validator trả `true` khi field null để tránh lặp trách nhiệm với `@NotNull`. Nếu muốn gắn lỗi vào một property cụ thể, có thể dùng `ConstraintValidatorContext` để tạo property node.

Class-level constraint phù hợp với quy tắc thuần dữ liệu trên object. Nếu quy tắc phụ thuộc trạng thái database, thời điểm giao dịch hoặc quyền của caller, nên chuyển sang domain/application layer.

## 9. Lớp 4: kiểm tra nghiệp vụ trong domain/application service

Bean Validation không thể trả lời mọi câu hỏi. Ví dụ request có:

```json
{
  "productCode": "KB-01",
  "quantity": 2
}
```

DTO có thể thỏa `@NotBlank` và `@Positive`, nhưng hệ thống vẫn cần kiểm tra:

- Sản phẩm `KB-01` có tồn tại và đang được phép bán không?
- Người gọi có quyền đặt sản phẩm này không?
- Kho có ít nhất hai sản phẩm không?
- Đơn hàng hiện tại có còn ở trạng thái cho phép thêm item không?
- Giá được áp dụng có còn hiệu lực trong thời điểm đặt hàng không?

Đây là các quy tắc phụ thuộc dữ liệu và trạng thái hệ thống. Đặt chúng trong application service hoặc domain model để có thể kiểm soát transaction và authorization.

Ví dụ:

```java
public Order createOrder(CreateOrderRequest request, UserId currentUser) {
    Product product = productRepository.findByCode(request.productCode())
            .orElseThrow(() -> new ProductNotFoundException(request.productCode()));

    authorizationService.requireCanPurchase(currentUser, product);

    if (!product.isAvailable()) {
        throw new ProductUnavailableException(product.getCode());
    }

    if (inventory.availableQuantity(product.getCode()) < request.quantity()) {
        throw new InsufficientStockException(product.getCode());
    }

    return orderRepository.save(
            Order.create(currentUser, product, request.quantity())
    );
}
```

Đoạn code minh họa thứ tự trách nhiệm; việc kiểm tra tồn kho và tạo order cần nằm trong transaction phù hợp hoặc dùng cơ chế reservation/locking để tránh race condition. Một lần đọc tồn kho trước rồi ghi đơn sau không tự bảo đảm còn hàng khi có nhiều request đồng thời.

## 10. Không đưa truy vấn database vào custom deserializer

Custom deserializer phù hợp để chuyển đổi JSON token thành kiểu Java, ví dụ parse một mã tiền tệ hoặc ngày theo format riêng. Nó thường không phải nơi phù hợp để kiểm tra sản phẩm có tồn tại trong database.

Nếu deserializer gọi repository:

- Parse JSON trở nên phụ thuộc database và transaction.
- Một request có thể gây nhiều query trong lúc binding.
- Unit test cần dựng cả mapper lẫn repository.
- Lỗi dữ liệu tham chiếu bị trộn với lỗi format/typing.
- Việc deserialize lại payload trong batch hoặc cache có thể gây side effect ngoài dự kiến.

Thay vào đó, deserialize `productCode` thành string hoặc value object, validate hình thức mã, rồi resolve product trong application service. Nếu cần batch, thu thập các mã duy nhất và truy vấn một lần.

Một ngoại lệ có thể là custom value type có parser thuần, không truy cập trạng thái bên ngoài, ví dụ `Money`, `PhoneNumber` hoặc `CurrencyCode`. Dù vậy, các quy tắc phụ thuộc vùng/quốc gia hoặc dữ liệu thay đổi vẫn nên được kiểm tra ở tầng nghiệp vụ.

## 11. Một pipeline xử lý thủ công bằng Jackson và Validator

Nếu không dùng framework HTTP tự động binding, có thể thể hiện các bước rõ ràng:

```java
public final class OrderRequestProcessor {
    private final ObjectReader reader;
    private final Validator validator;
    private final OrderService orderService;

    public OrderRequestProcessor(ObjectMapper mapper,
                                 Validator validator,
                                 OrderService orderService) {
        this.reader = mapper.readerFor(CreateOrderRequest.class)
                .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
        this.validator = validator;
        this.orderService = orderService;
    }

    public Order handle(String json, UserId currentUser) throws IOException {
        // Bước 1 + 2: Jackson parse JSON và bind thành DTO.
        CreateOrderRequest request = reader.readValue(json);

        // Bước 3: kiểm tra constraint trên DTO.
        Set<ConstraintViolation<CreateOrderRequest>> violations =
                validator.validate(request);
        if (!violations.isEmpty()) {
            throw new RequestValidationException(violations);
        }

        // Bước 4: kiểm tra quy tắc nghiệp vụ và thực hiện use case.
        return orderService.createOrder(request, currentUser);
    }
}
```

Trong ví dụ, `ObjectReader` thực hiện cả parse và binding trong một lần đọc. Nếu cần báo lỗi syntax riêng với mapping, có thể phân loại exception Jackson hoặc parse bằng Core/Tree trước, nhưng không nhất thiết phải parse toàn bộ body hai lần trong mọi API.

Validation không nên bị bỏ qua khi deserialize thành công. Ngược lại, không chạy Bean Validation trên object nếu Jackson đã thất bại và không tạo được DTO.

## 12. Có cần parse JSON hai lần không?

Không phải lúc nào cũng cần tách parse và binding thành hai lần đọc. `ObjectMapper.readValue()` đã dùng parser để đọc cú pháp và bind token trực tiếp thành target object.

Tách hai bước có ích khi:

- Cần kiểm tra root shape trước khi chọn DTO.
- Cần xử lý JSON động hoặc discriminator bên ngoài schema.
- Cần lưu/biến đổi cây JSON trước khi bind.
- Cần trả thông báo lỗi khác nhau cho cú pháp và cấu trúc.

Nhưng parse thành `JsonNode` rồi serialize/parse lại thành DTO có thể tăng CPU và bộ nhớ. Với API có DTO cố định, đọc thẳng bằng `ObjectReader` thường đủ; phân loại lỗi dựa trên exception type và xử lý Bean Validation sau đó.

Nếu parse tree trước rồi bind từ tree, hãy tránh gọi `readValue()` lần nữa trên raw body; dùng `treeToValue()` hoặc `convertValue()` khi phù hợp. `convertValue()` không thay thế hoàn toàn một lần parse JSON từ bên ngoài và không nên được dùng như một bước validation nghiệp vụ.

## 13. Kiểm tra cấu trúc object và array rõ ràng

Một số API cần phân biệt root object, array hoặc scalar. Với tree model:

```java
JsonNode root = mapper.readTree(json);

if (root == null || !root.isObject()) {
    throw new InvalidRequestShapeException("Root JSON value must be an object");
}

JsonNode lines = root.get("lines");
if (lines == null || !lines.isArray()) {
    throw new InvalidRequestShapeException("lines must be an array");
}
```

Đây là structural validation ở ranh giới JSON. Sau đó, từng phần tử vẫn cần được kiểm tra kiểu và constraint. Nếu DTO khai báo `List<OrderLineRequest>`, Jackson có thể thực hiện phần lớn kiểm tra cấu trúc/kiểu tự động.

Không nên dùng `path()` rồi gọi `asInt()` mà không kiểm tra node type nếu contract yêu cầu number nghiêm ngặt. Các accessor coercive như `asInt()` có thể trả default hoặc chuyển đổi giá trị; hãy kiểm tra `isInt()`/`isNumber()` và phạm vi giá trị khi cần.

## 14. Missing, null và default value là ba trạng thái khác nhau

Một field có thể:

1. Không xuất hiện trong JSON.
2. Xuất hiện với JSON `null`.
3. Xuất hiện với một giá trị cụ thể.

Ví dụ:

```json
{}
```

```json
{"quantity":null}
```

```json
{"quantity":0}
```

Với `Integer quantity`, Jackson thường để null cho trường hợp field thiếu hoặc explicit null, nếu không có creator/default/custom handling khác. Với primitive `int`, field thiếu có thể giữ giá trị mặc định `0`; explicit null có thể được xử lý theo `FAIL_ON_NULL_FOR_PRIMITIVES` và cấu hình coercion.

Nếu API cần phân biệt “không gửi field” với “gửi null để xóa giá trị”, DTO thông thường có thể chưa đủ. Có thể dùng wrapper ba trạng thái, custom deserializer, `JsonNode`/`Optional` theo thiết kế riêng hoặc một kiểu `PatchField<T>` biểu diễn `ABSENT`, `NULL`, `VALUE`.

Không nên tự động coi `null` là giá trị mặc định nếu điều đó có thể ghi đè dữ liệu hiện tại ngoài ý muốn.

## 15. Kiểm tra cú pháp, mapping và Bean Validation bằng các lỗi khác nhau

Ví dụ các payload:

**A. JSON syntax sai:**

```text
{"quantity": 2,
```

Parser không thể hoàn tất object. Đây là parse error.

**B. JSON hợp lệ nhưng sai kiểu:**

```json
{"quantity":{"value":2}}
```

JSON parse được, nhưng object không thể ánh xạ thành `Integer`. Đây là mapping error.

**C. JSON hợp lệ, ánh xạ thành công nhưng vi phạm constraint:**

```json
{"quantity":-2}
```

Jackson tạo `Integer(-2)`. `@Positive` từ chối giá trị. Đây là validation error.

**D. Dữ liệu thỏa constraint nhưng sai nghiệp vụ:**

```json
{"productCode":"KB-01","quantity":2}
```

Mã sản phẩm hợp lệ về hình thức và số lượng dương, nhưng sản phẩm có thể đã ngừng bán hoặc không đủ tồn kho. Đây là business rule violation.

Phân loại đúng giúp API trả mã lỗi và thông điệp có ý nghĩa, đồng thời giúp log và metric không gộp mọi lỗi vào một nhóm “bad request” không rõ nguyên nhân.

## 16. Thiết kế lỗi đầu vào nhất quán

Có thể chuẩn hóa lỗi thành một cấu trúc response chung:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid values",
  "errors": [
    {
      "field": "quantity",
      "code": "Positive",
      "message": "must be greater than 0"
    }
  ]
}
```

Các nhóm lỗi có thể được ánh xạ như sau:

| Lỗi nội bộ | Mã API gợi ý | HTTP thường dùng |
|---|---|---|
| JSON parse error | `MALFORMED_JSON` | 400 Bad Request |
| Jackson mapping/type error | `INVALID_FIELD_TYPE` hoặc `INVALID_REQUEST_FORMAT` | 400 Bad Request |
| Bean Validation violation | `VALIDATION_FAILED` | 400 hoặc 422 theo API contract |
| Business rule violation | Mã nghiệp vụ cụ thể, ví dụ `INSUFFICIENT_STOCK` | 409, 422 hoặc mã phù hợp contract |
| Authentication/authorization failure | `UNAUTHENTICATED` / `FORBIDDEN` | 401 / 403 |

HTTP status phải nhất quán với contract của API. Một số hệ thống dùng 400 cho mọi request invalid; hệ thống khác phân biệt 400 và 422. Điều quan trọng là client có thể nhận diện loại lỗi và biết có nên sửa payload, xác thực lại hay thử lại sau.

Không trả stack trace, tên class nội bộ, SQL hoặc raw payload nhạy cảm trong error response.

## 17. Ví dụ Spring MVC: Jackson binding trước, Bean Validation sau

Trong Spring MVC, `@RequestBody` thường được xử lý bởi Jackson HTTP message converter; `@Valid` yêu cầu Bean Validation kiểm tra object sau khi deserialize thành công.

DTO:

```java
public record CreateOrderRequest(
        @NotBlank String productCode,
        @NotNull @Positive Integer quantity) {
}
```

Controller:

```java
@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public OrderResponse create(
            @Valid @RequestBody CreateOrderRequest request,
            Principal principal) {
        return orderService.create(request, principal.getName());
    }
}
```

Thứ tự xảy ra:

1. HTTP converter đọc body và dùng Jackson deserialize thành `CreateOrderRequest`.
2. Nếu JSON sai cú pháp hoặc sai kiểu, converter ném lỗi và controller method không được gọi.
3. Nếu deserialize thành công, Spring chạy Bean Validation do `@Valid` yêu cầu.
4. Nếu constraint thất bại, Spring thường ném `MethodArgumentNotValidException` và không gọi method controller.
5. Nếu DTO hợp lệ, controller gọi service; service tiếp tục kiểm tra nghiệp vụ và quyền.

Trong Spring Boot, cần dependency Bean Validation implementation phù hợp, thường là starter validation. Chỉ thêm annotation mà không có provider thì validation có thể không được thực thi.

## 18. Xử lý riêng lỗi Jackson và lỗi Bean Validation trong Spring

Có thể dùng `@RestControllerAdvice` để chuẩn hóa response:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> handleUnreadableBody(
            HttpMessageNotReadableException exception) {
        ApiError error = new ApiError(
                "INVALID_REQUEST_BODY",
                "Request body is malformed or has an incompatible value",
                List.of()
        );
        return ResponseEntity.badRequest().body(error);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleBeanValidation(
            MethodArgumentNotValidException exception) {
        List<FieldErrorDetail> details = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldErrorDetail(
                        error.getField(),
                        error.getCode(),
                        error.getDefaultMessage()))
                .toList();

        return ResponseEntity.badRequest().body(new ApiError(
                "VALIDATION_FAILED",
                "Request contains invalid values",
                details
        ));
    }
}
```

`HttpMessageNotReadableException` có thể bao lỗi parse JSON, lỗi mapping, lỗi format hoặc lỗi đọc body khác; nếu cần phân loại sâu hơn, kiểm tra cause chain có kiểm soát và ánh xạ các subtype Jackson phù hợp. Không giả định mọi lỗi trong wrapper exception đều là syntax error.

`MethodArgumentNotValidException` đại diện cho lỗi Bean Validation trên argument được đánh dấu `@Valid`. Nếu dùng method validation hoặc validate service method qua `@Validated`, có thể gặp `ConstraintViolationException` hoặc exception theo framework version.

Hãy giữ error response ổn định, không phụ thuộc toàn bộ message nội bộ của Jackson vì wording có thể thay đổi giữa version.

## 19. Kiểm tra nghiệp vụ và lỗi xung đột trạng thái

Business validation thường phụ thuộc dữ liệu hiện tại. Ví dụ:

```java
public OrderResponse create(CreateOrderRequest request, String username) {
    Product product = productRepository.findByCode(request.productCode())
            .orElseThrow(() -> new ProductNotFoundException(request.productCode()));

    if (!product.isActive()) {
        throw new ProductUnavailableException(product.getCode());
    }

    User user = userRepository.findByUsername(username)
            .orElseThrow(UnauthenticatedUserException::new);

    Order order = orderService.place(user, product, request.quantity());
    return OrderResponse.from(order);
}
```

Các lỗi `ProductNotFoundException`, `ProductUnavailableException` hoặc lỗi tồn kho không phải `JsonMappingException`. Chúng mô tả trạng thái nghiệp vụ và nên có mã lỗi riêng.

Nếu trạng thái có thể thay đổi đồng thời, validation và hành động cần được thực hiện trong transaction hoặc qua cơ chế atomic phù hợp. Không nên kiểm tra một điều kiện ở controller rồi giả định nó vẫn đúng khi service ghi dữ liệu sau đó.

## 20. Dùng Bean Validation group khi có nhiều giai đoạn kiểm tra DTO

Một DTO có thể được dùng ở nhiều bước với constraint khác nhau. Bean Validation groups cho phép chia nhóm:

```java
public interface CreateChecks {}
public interface UpdateChecks {}
```

```java
public class AccountRequest {
    @NotNull(groups = UpdateChecks.class)
    private Long id;

    @NotBlank(groups = {CreateChecks.class, UpdateChecks.class})
    private String username;

    // getters và setters
}
```

Gọi validation theo nhóm:

```java
validator.validate(request, CreateChecks.class);
validator.validate(request, UpdateChecks.class);
```

Group giúp phân biệt constraint theo use case, nhưng không nên biến DTO thành một model dùng cho mọi endpoint nếu contract quá khác nhau. DTO riêng thường rõ ràng hơn khi create/update có ý nghĩa field khác nhau, đặc biệt với missing/null semantics.

## 21. Constraint tùy chỉnh không nên phụ thuộc trạng thái thay đổi nếu có thể tránh

Có thể tạo custom `ConstraintValidator` cho quy tắc định dạng, ví dụ mã sản phẩm theo pattern:

```java
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ProductCodeValidator.class)
public @interface ValidProductCode {
    String message() default "invalid product code";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

```java
public class ProductCodeValidator
        implements ConstraintValidator<ValidProductCode, String> {

    private static final Pattern FORMAT = Pattern.compile("[A-Z]{2}-[0-9]{2,8}");

    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        return value == null || FORMAT.matcher(value).matches();
    }
}
```

Validator trên chỉ kiểm tra format. Nó không hỏi database mã sản phẩm có tồn tại hay không. Quy tắc “mã phải có format hợp lệ” ổn định và thuần dữ liệu; quy tắc “sản phẩm đang active và thuộc tenant của user” phụ thuộc trạng thái hệ thống và nên nằm ở service.

Nếu custom validator cần dependency injection hoặc repository, kiểm soát lifecycle/provider rõ ràng và tránh query riêng cho từng phần tử collection. Với nhiều mã, batch lookup ở service thường hiệu quả hơn.

## 22. Kiểm thử từng lớp độc lập

Để biết lỗi thuộc lớp nào, hãy viết test tập trung cho từng giai đoạn.

### 22.1. Test cú pháp và document framing

```java
@Test
void rejectsMalformedJson() {
    String malformed = "{\"quantity\":2";

    assertThrows(JsonProcessingException.class,
            () -> mapper.readTree(malformed));
}

@Test
void rejectsTrailingRootValue() {
    String twoDocuments = "{\"quantity\":2} {\"quantity\":3}";

    assertThrows(JsonProcessingException.class,
            () -> strictReader.readValue(twoDocuments));
}
```

Test thứ hai cần `strictReader` bật `FAIL_ON_TRAILING_TOKENS`.

### 22.2. Test mapping type

```java
@Test
void rejectsObjectWhereIntegerIsExpected() {
    String wrongType = "{\"productCode\":\"KB-01\",\"quantity\":{}}";

    assertThrows(JsonMappingException.class,
            () -> mapper.readValue(wrongType, CreateOrderRequest.class));
}
```

Test này không nên phụ thuộc vào Bean Validation vì DTO chưa được tạo thành công.

### 22.3. Test Bean Validation

```java
@Test
void rejectsNonPositiveQuantity() throws Exception {
    CreateOrderRequest request = mapper.readValue(
            "{\"productCode\":\"KB-01\",\"quantity\":-1}",
            CreateOrderRequest.class);

    Set<ConstraintViolation<CreateOrderRequest>> violations =
            validator.validate(request);

    assertTrue(violations.stream()
            .anyMatch(v -> v.getPropertyPath().toString().equals("quantity")));
}
```

Jackson thành công; validator thất bại. Test này chứng minh hai lớp có thể cho kết quả khác nhau trên cùng payload.

### 22.4. Test business rule

```java
@Test
void rejectsOrderWhenInventoryIsInsufficient() {
    when(inventory.availableQuantity("KB-01")).thenReturn(1);

    assertThrows(InsufficientStockException.class,
            () -> orderService.create(
                    new CreateOrderRequest("KB-01", 2, LocalDate.now()),
                    userId));
}
```

Đây là test application/domain service. Không cần dựng JSON parser vì mục tiêu là xác nhận quy tắc tồn kho sau khi request đã được chuyển thành DTO.

## 23. Test tích hợp toàn pipeline

Sau unit test từng lớp, cần một số integration test đi qua ranh giới thật:

- Body malformed trả lỗi parse/bad request.
- JSON đúng cú pháp nhưng sai kiểu trả lỗi mapping.
- DTO ánh xạ được nhưng vi phạm `@NotBlank`/`@Positive` trả lỗi validation.
- DTO hợp lệ nhưng thiếu quyền hoặc không đủ tồn kho trả lỗi nghiệp vụ tương ứng.
- Request hợp lệ đi qua tất cả bước và tạo kết quả đúng.

Với Spring, có thể dùng `MockMvc` hoặc `WebTestClient` để đi qua HTTP converter, Bean Validation và exception handler. Test chỉ gọi method controller trực tiếp sẽ bỏ qua một phần pipeline HTTP.

Một test matrix ví dụ:

| Payload / trạng thái | Parse | Mapping | Bean Validation | Business | Kết quả |
|---|---|---|---|---|---|
| JSON thiếu dấu `}` | Fail | Chưa chạy | Chưa chạy | Chưa chạy | 400 malformed body |
| `quantity` là object | Pass syntax | Fail | Chưa chạy | Chưa chạy | 400 invalid type |
| `quantity = -1` | Pass | Pass | Fail | Chưa chạy | Validation error |
| `quantity = 2`, tồn kho = 1 | Pass | Pass | Pass | Fail | Insufficient stock |
| `quantity = 2`, đủ hàng, có quyền | Pass | Pass | Pass | Pass | Tạo đơn |

## 24. Không biến mọi lỗi thành cùng một thông báo

Nếu mọi lỗi đều trả `"Invalid JSON"`, client khó biết cách sửa request:

- JSON malformed cần sửa dấu ngoặc/dấu nháy.
- Sai kiểu cần gửi đúng JSON token type.
- Constraint violation cần sửa giá trị.
- Business conflict có thể cần chọn sản phẩm khác hoặc thử lại sau.

Hãy dùng error code ổn định và field path khi có thể. Không nhất thiết phải tiết lộ chi tiết implementation của Jackson; có thể chuyển lỗi kỹ thuật thành thông báo API rõ ràng.

Ví dụ response:

```json
{
  "code": "INVALID_FIELD_TYPE",
  "message": "One or more fields have an incompatible type",
  "errors": [
    {
      "field": "quantity",
      "message": "must be a JSON integer"
    }
  ]
}
```

Với lỗi nghiệp vụ:

```json
{
  "code": "INSUFFICIENT_STOCK",
  "message": "The requested quantity is not available",
  "errors": []
}
```

Thông điệp không nên chứa thông tin nội bộ như số tồn kho chính xác nếu chính sách không cho phép tiết lộ.

## 25. Những lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Hướng xử lý |
|---|---|---|
| Coi deserialize thành công là request hợp lệ | DTO có thể chứa null, chuỗi rỗng hoặc số âm | Chạy Bean Validation sau binding |
| Đưa kiểm tra database vào deserializer | Binding phụ thuộc hạ tầng, dễ tạo N+1 query | Resolve tham chiếu ở application service |
| Dùng `@NotNull` để kiểm tra JSON syntax | Constraint chỉ chạy sau khi object được tạo | Để Jackson parser xử lý cú pháp |
| Dùng `readTree()` và gọi `asInt()` không kiểm tra type | Có thể chấp nhận/coerce input sai kiểu | Kiểm tra node type hoặc bind DTO strict |
| Tắt unknown-property toàn cục | Che typo và thay đổi contract ở mọi endpoint | Dùng reader/DTO riêng theo use case |
| Bỏ qua missing/null distinction | Có thể vô tình xóa hoặc ghi đè dữ liệu | Dùng DTO patch ba trạng thái khi cần |
| Đưa mọi rule vào custom deserializer | Trộn parse, binding, validation và nghiệp vụ | Phân tầng theo trách nhiệm |
| Trả stack trace hoặc raw body trong lỗi | Có thể lộ dữ liệu nhạy cảm | Chuẩn hóa error response và redact log |
| Chỉ test unit mapper tự tạo | Không phản ánh mapper/framework production | Có integration test qua converter thật |
| Không giới hạn kích thước/depth JSON | Có thể bị tiêu tốn CPU/RAM bất thường | Giới hạn HTTP body và parser constraints |

## 26. Quy trình triển khai đề xuất

Khi xây dựng một endpoint nhận JSON, có thể thực hiện theo trình tự:

1. Định nghĩa DTO input và kiểu Java phản ánh đúng JSON contract.
2. Quy định strict/tolerant behavior cho unknown fields, trailing tokens, duplicate keys và coercion.
3. Cấu hình Jackson module, format và subtype allowlist cần thiết.
4. Giới hạn request body, độ sâu lồng nhau, độ dài string/number theo nhu cầu.
5. Deserialize vào DTO bằng mapper/reader được cấu hình đúng.
6. Chạy Bean Validation cho required, length, range, format và nested object.
7. Chạy domain/application validation cho quyền, trạng thái, dữ liệu tham chiếu và invariant.
8. Thực hiện thay đổi trong transaction hoặc cơ chế atomic thích hợp.
9. Chuẩn hóa lỗi theo lớp để client hiểu cần sửa payload hay xử lý xung đột.
10. Test riêng từng lớp và test tích hợp qua pipeline thật.

## 27. Ghi nhớ

Kiểm tra cú pháp JSON, ánh xạ kiểu và kiểm tra nghiệp vụ là ba trách nhiệm khác nhau; Bean Validation thường là lớp ràng buộc dữ liệu nằm giữa mapping và domain rule. Jackson xác nhận token JSON hợp lệ và chuyển chúng thành Java type theo cấu hình. Bean Validation kiểm tra giá trị của object đã tạo. Domain/application service kiểm tra quy tắc phụ thuộc quyền, trạng thái và dữ liệu hệ thống.

Hãy để mỗi lớp xử lý loại lỗi mà nó hiểu rõ nhất. Cấu hình Jackson tường minh cho syntax/framing và type binding; dùng DTO cùng Bean Validation cho constraint; dùng domain/service cho quy tắc nghiệp vụ. Kiểm thử độc lập từng lớp rồi kiểm thử tích hợp toàn pipeline sẽ giúp lỗi được phân loại chính xác, contract dễ bảo trì và logic nghiệp vụ không bị trộn vào quá trình parse JSON.
