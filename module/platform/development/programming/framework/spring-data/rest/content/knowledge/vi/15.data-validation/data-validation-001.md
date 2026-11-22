# Phân biệt kiểm tra cú pháp JSON, ràng buộc dữ liệu và quy tắc nghiệp vụ

## 1. Vì sao cần tách các lớp kiểm tra?

Một request JSON có thể hợp lệ về cú pháp nhưng vẫn không thể chuyển thành object Java, vi phạm ràng buộc của field hoặc trái với quy tắc nghiệp vụ. Các lỗi này xuất hiện ở những thời điểm khác nhau và cần được xử lý ở đúng lớp.

Ví dụ client gửi yêu cầu tạo một đơn hàng:

~~~~json
{
  "customerId": 42,
  "quantity": 0,
  "unitPrice": -10,
  "deliveryDate": "2026-02-01"
}
~~~~

JSON trên hợp lệ về cú pháp. Các giá trị có thể còn deserialize được thành kiểu Java tương ứng. Tuy nhiên, quantity bằng 0 và unitPrice âm có thể vi phạm ràng buộc dữ liệu; deliveryDate có thể vi phạm quy tắc nghiệp vụ nếu ngày giao nằm trong quá khứ hoặc đơn hàng đang ở trạng thái không cho phép giao.

Một hệ thống nên phân biệt:

1. **Kiểm tra cú pháp và binding:** body có phải JSON hợp lệ và có thể chuyển thành kiểu dữ liệu mà endpoint mong đợi không?
2. **Ràng buộc dữ liệu:** giá trị sau khi binding có thỏa các constraint về null, độ dài, định dạng, phạm vi và cấu trúc không?
3. **Quy tắc nghiệp vụ:** thao tác có hợp lệ trong trạng thái và ngữ cảnh hiện tại của hệ thống không?
4. **Ràng buộc lưu trữ:** database có thể duy trì tính toàn vẹn của dữ liệu khi ghi không?

Các lớp này bổ sung cho nhau. Không nên dùng một regex để giải quyết quy tắc nghiệp vụ, cũng không nên dựa hoàn toàn vào database exception để hướng dẫn client sửa request.

## 2. Lớp 1 — JSON syntax, media type và data binding

Ở lớp đầu tiên, server đọc request body và chuyển JSON thành object hoặc cấu trúc dữ liệu. Với Spring MVC, việc này được thực hiện bởi HttpMessageConverter; Jackson thường là JSON converter được dùng trong Spring Boot.

Một request có thể thất bại ở các bước sau:

| Vấn đề | Ví dụ | Kết quả thường gặp |
|---|---|---|
| JSON sai cú pháp | Thiếu dấu ngoặc, dấu phẩy thừa, chuỗi không đóng | Không parse được body |
| JSON root sai kiểu | Endpoint chờ object nhưng nhận array hoặc scalar | Không thể deserialize đúng kiểu đích |
| Kiểu field không tương thích | age là số nhưng client gửi "twenty" | Lỗi chuyển đổi kiểu |
| Giá trị ngày không đúng định dạng | LocalDate cần ngày nhưng nhận chuỗi không parse được | Lỗi deserialization |
| Content-Type không được hỗ trợ | Gửi XML đến endpoint chỉ nhận JSON | 415 Unsupported Media Type |
| Accept không được hỗ trợ | Client yêu cầu response media type server không thể tạo | 406 Not Acceptable |

Ví dụ body sai cú pháp:

~~~~json
{
  "name": "Alice",
  "age": 25,
}
~~~~

Dấu phẩy sau 25 làm JSON không hợp lệ theo cú pháp chuẩn. Jackson không thể tạo object Person từ body này.

Ví dụ JSON hợp lệ nhưng sai kiểu dữ liệu:

~~~~json
{
  "name": "Alice",
  "age": "twenty"
}
~~~~

JSON parser đọc được document, nhưng binder không thể chuyển chuỗi twenty thành số nguyên nếu field age là Integer. Đây là lỗi deserialize/binding, không phải lỗi Bean Validation.

Một ví dụ khác: body có thể là JSON hợp lệ và mọi field đều parse được, nhưng có field bắt buộc không xuất hiện. Nếu constructor hoặc kiểu Java cho phép giá trị mặc định/null, request có thể đi qua bước binding và chỉ bị phát hiện ở bước validation tiếp theo.

### Kiểm tra media type

Client nên khai báo đúng Content-Type:

~~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json
~~~~

Content-Type mô tả định dạng body gửi lên. Accept mô tả định dạng response mà client muốn nhận. Hai header này có mục đích khác nhau.

### Xử lý lỗi binding trong Spring MVC

Với controller tùy chỉnh, Spring Framework đọc và deserialize body vào tham số có @RequestBody. Lỗi parse hoặc chuyển đổi thường được biểu diễn bằng HttpMessageNotReadableException và trả về 400 Bad Request theo exception handling mặc định.

Ví dụ:

~~~~java
@PostMapping("/people")
public Person create(@RequestBody PersonInput input) {
    return service.create(input);
}
~~~~

Nếu JSON malformed hoặc field có kiểu không thể chuyển đổi, method có thể chưa được gọi vì message conversion thất bại trước đó.

Không nên bắt mọi lỗi parse rồi trả thông báo chung chung rằng dữ liệu vi phạm business rule. Hãy phân biệt body không đọc được với một object hợp lệ nhưng không thỏa điều kiện nghiệp vụ.

## 3. Lớp 2 — Ràng buộc dữ liệu với Bean Validation

Sau khi JSON đã được deserialize, Bean Validation kiểm tra object theo các constraint được khai báo. Trong Spring Boot hiện đại, annotation thường nằm trong package jakarta.validation.constraints.

Các constraint phổ biến:

| Annotation | Kiểm tra |
|---|---|
| @NotNull | Giá trị không được null |
| @NotBlank | Chuỗi không được null, rỗng hoặc chỉ có khoảng trắng |
| @NotEmpty | Chuỗi, collection, map hoặc array không được rỗng |
| @Size(min, max) | Giới hạn độ dài hoặc số phần tử |
| @Min / @Max | Giới hạn số nguyên theo min/max |
| @DecimalMin / @DecimalMax | Giới hạn số thập phân |
| @Positive / @PositiveOrZero | Số phải dương hoặc không âm |
| @Email | Kiểm tra định dạng email cơ bản |
| @Pattern | Kiểm tra chuỗi theo regular expression |
| @Past / @Future | Kiểm tra giá trị ngày/thời gian ở quá khứ hoặc tương lai |

Ví dụ request DTO:

~~~~java
public record PersonInput(
        @NotBlank
        @Size(max = 80)
        String name,

        @NotNull
        @Min(18)
        Integer age,

        @Email
        String email
) {
}
~~~~

Một JSON body hợp lệ về cú pháp vẫn có thể bị từ chối nếu name chỉ chứa khoảng trắng, age nhỏ hơn 18 hoặc email sai định dạng.

### Kích hoạt validation trong controller MVC

Dùng @Valid hoặc @Validated trên tham số @RequestBody:

~~~~java
@PostMapping("/people")
public Person create(
        @Valid @RequestBody PersonInput input) {

    return service.create(input);
}
~~~~

Khi constraint thất bại và controller không nhận Errors hoặc BindingResult ngay sau tham số cần validate, Spring MVC mặc định phát sinh MethodArgumentNotValidException và trả 400 Bad Request.

Nếu muốn tự xử lý lỗi trong controller:

~~~~java
@PostMapping("/people")
public ResponseEntity<?> create(
        @Valid @RequestBody PersonInput input,
        Errors errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body(errors.getAllErrors());
    }

    return ResponseEntity.ok(service.create(input));
}
~~~~

Tham số Errors/BindingResult cần đứng ngay sau object được validate. Khi method validation áp dụng cho các tham số method có constraint trực tiếp, Spring có thể phát sinh HandlerMethodValidationException; hãy xử lý loại exception phù hợp với chữ ký controller và phiên bản Spring Framework.

### Kiểm tra object lồng nhau

Dùng @Valid trên thuộc tính lồng nhau để kích hoạt validation cho object con:

~~~~java
public record AddressInput(
        @NotBlank String city,
        @NotBlank String country
) {
}

public record PersonInput(
        @NotBlank String name,

        @Valid
        @NotNull
        AddressInput address
) {
}
~~~~

Nếu không cascade validation, constraint bên trong AddressInput có thể không được kiểm tra khi validate PersonInput.

### Kiểm tra ở cấp object

Có những ràng buộc liên quan đến nhiều field, ví dụ endDate phải sau startDate. Đây không phải lỗi cú pháp JSON và cũng không phải constraint đơn giản trên một field.

Có thể tạo class-level constraint bằng annotation tùy chỉnh và ConstraintValidator, hoặc viết một Spring Validator:

~~~~java
public class BookingValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return BookingInput.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        BookingInput input = (BookingInput) target;

        if (input.startDate() != null
                && input.endDate() != null
                && input.endDate().isBefore(input.startDate())) {
            errors.rejectValue(
                    "endDate",
                    "booking.endDate.beforeStartDate",
                    "Ngày kết thúc phải sau ngày bắt đầu"
            );
        }
    }
}
~~~~

Đây vẫn là validation trên dữ liệu đầu vào. Nếu quy tắc cần đọc trạng thái đơn hàng, quyền của người dùng hoặc dữ liệu từ nhiều aggregate, nên chuyển sang lớp nghiệp vụ.

### Validation groups

Một field có thể có yêu cầu khác nhau khi tạo mới và cập nhật. Bean Validation hỗ trợ groups để chọn tập constraint áp dụng cho từng tình huống.

Ví dụ:

~~~~java
public interface Create {}
public interface Update {}

public class PersonInput {

    @NotBlank(groups = Create.class)
    private String name;

    @NotNull(groups = Update.class)
    private Long id;
}
~~~~

Trong controller tùy chỉnh, có thể dùng @Validated(Create.class) hoặc @Validated(Update.class). Với Spring Data REST, hãy kiểm tra cách event validator được gọi và cách chọn group trong phiên bản dự án; đừng giả định group được tự chọn theo HTTP method nếu ứng dụng chưa cấu hình điều đó.

## 4. Validation trong Spring Data REST

Spring Data REST xuất bản repository thành REST resource. Với các thao tác POST, PUT hoặc PATCH, request được chuyển thành domain object rồi đi qua repository lifecycle.

Spring Data REST cung cấp cơ chế gắn Spring Validator vào repository event. Tài liệu hiện hành hỗ trợ hai cách đăng ký.

### Cách 1 — Đặt tên bean theo event

Tên bean bắt đầu bằng event mà validator cần xử lý. Ví dụ:

~~~~java
@Component("beforeCreatePersonValidator")
public class BeforeCreatePersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Person.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (person.getName() == null
                || person.getName().isBlank()) {
            errors.rejectValue(
                    "name",
                    "person.name.required",
                    "Tên không được để trống"
            );
        }
    }
}
~~~~

Tiền tố beforeCreate gắn validator với sự kiện tạo mới. Có thể dùng các tiền tố tương ứng như beforeSave để kiểm tra entity trước khi cập nhật.

### Cách 2 — Đăng ký thủ công qua RepositoryRestConfigurer

Nếu muốn kiểm soát đăng ký trong cấu hình, dùng ValidatingRepositoryEventListener:

~~~~java
@Configuration
public class RepositoryValidationConfiguration
        implements RepositoryRestConfigurer {

    private final Validator personValidator;

    public RepositoryValidationConfiguration(
            Validator personValidator) {
        this.personValidator = personValidator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {

        listener.addValidator("beforeCreate", personValidator);
        listener.addValidator("beforeSave", personValidator);
    }
}
~~~~

Một validator có thể được gắn vào nhiều event nếu logic của nó phù hợp với các event đó. Nếu create và update có quy tắc khác nhau, nên dùng validator riêng hoặc phân nhánh có chủ đích.

Các event liên quan đến validation gồm:

| Event | Thời điểm |
|---|---|
| beforeCreate | Trước khi repository tạo entity mới |
| beforeSave | Trước khi repository lưu entity đã tồn tại |
| beforeLinkSave | Trước khi lưu thay đổi liên kết giữa các resource |
| afterCreate | Sau thao tác tạo |
| afterSave | Sau thao tác lưu |
| beforeDelete / afterDelete | Trước hoặc sau thao tác xóa |

Dùng beforeCreate, beforeSave hoặc beforeLinkSave khi cần từ chối dữ liệu trước thao tác tương ứng. Các event after phù hợp cho phản ứng sau thao tác; không dùng chúng làm nơi chính để ngăn dữ liệu không hợp lệ đã được lưu.

### Bean Validation và Spring Validator trong repository events

Bean Validation annotation mô tả constraint trên object, còn Spring Data REST event listener gọi các instance Spring Validator được đăng ký. Nếu muốn tái sử dụng Bean Validation provider trong repository events, có thể đăng ký một Spring Validator tương thích, chẳng hạn LocalValidatorFactoryBean, vào event listener theo cấu hình của ứng dụng.

Không nên mặc định rằng chỉ thêm @NotBlank hoặc @Email vào mọi entity là mọi repository event trong mọi phiên bản Spring Data REST sẽ tự động chạy các constraint đó. Hãy xác nhận validator đã được đăng ký, đúng event và đúng domain type; viết integration test cho POST, PUT và PATCH.

## 5. Lớp 3 — Quy tắc nghiệp vụ

Business rule quyết định một thao tác có hợp lệ trong ngữ cảnh hiện tại hay không. Quy tắc thường phụ thuộc trạng thái hệ thống, người thực hiện, dữ liệu liên quan hoặc lịch sử giao dịch.

Ví dụ:

- Chỉ đơn hàng ở trạng thái DRAFT mới được xác nhận.
- Người dùng chỉ được sửa hồ sơ thuộc tenant của mình.
- Không thể hủy một đơn hàng đã giao.
- Không thể đặt số lượng vượt quá tồn kho có thể bán.
- Tổng chiết khấu không được vượt giới hạn hợp đồng của khách hàng.
- Ngày giao phải nằm trong khoảng mà dịch vụ vận chuyển hỗ trợ.
- Tài khoản bị khóa không được thực hiện chuyển tiền.

Các quy tắc này thường không thể kiểm tra đầy đủ bằng @Min, @NotNull hoặc @Pattern, vì cần đọc trạng thái hiện tại và áp dụng logic nghiệp vụ.

### Đặt business rule ở đâu?

Nên đặt quy tắc trong domain model hoặc application/service layer, nơi có thể kiểm soát transaction và truy cập các dữ liệu cần thiết.

Ví dụ:

~~~~java
@Service
public class OrderService {

    private final OrderRepository orders;
    private final InventoryService inventory;

    @Transactional
    public Order confirm(Long orderId, User currentUser) {

        Order order = orders.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (!order.belongsTo(currentUser.tenantId())) {
            throw new AccessDeniedException("Không có quyền trên đơn hàng");
        }

        if (order.getStatus() != OrderStatus.DRAFT) {
            throw new InvalidOrderStateException(
                    "Chỉ đơn hàng nháp mới được xác nhận"
            );
        }

        inventory.reserve(order.getItems());
        order.confirm();

        return orders.save(order);
    }
}
~~~~

Service kiểm tra quyền và trạng thái, gọi domain method để chuyển trạng thái, sau đó thực hiện lưu trong transaction. Nếu một điều kiện không thỏa, thao tác bị từ chối trước khi ghi.

Với endpoint Spring Data REST thuần, repository event handler có thể kiểm tra hoặc điều chỉnh entity ở các lifecycle event. Tuy nhiên, event handler không tự biến một chuỗi thao tác nhiều repository thành một use case có transaction và thứ tự rõ ràng. Với nghiệp vụ quan trọng như thanh toán, đặt hàng hoặc chuyển trạng thái phức tạp, custom controller gọi application service thường dễ kiểm soát hơn.

### Không nhầm validation với authorization

Một request có thể đúng cú pháp và thỏa mọi constraint nhưng người gửi vẫn không có quyền thực hiện thao tác. Ví dụ user gửi một customerId hợp lệ về kiểu Long, nhưng customer đó thuộc tenant khác.

Authorization phải được kiểm tra từ security context và dữ liệu server tin cậy. Không dựa vào field do client gửi để tự xác nhận quyền. Việc trả lỗi “dữ liệu không hợp lệ” thay cho “không có quyền” cũng có thể làm sai semantics và che khuất vấn đề bảo mật.

## 6. Lớp 4 — Ràng buộc ở database

Database constraints bảo vệ tính toàn vẹn ở thời điểm ghi, kể cả khi dữ liệu đến từ nhiều luồng hoặc nhiều ứng dụng.

Các loại thường gặp:

| Database constraint | Bảo vệ |
|---|---|
| NOT NULL | Cột không được null |
| UNIQUE | Giá trị hoặc tổ hợp giá trị không bị trùng |
| PRIMARY KEY | Định danh duy nhất cho hàng |
| FOREIGN KEY | Quan hệ tham chiếu phải hợp lệ |
| CHECK | Giá trị phải thỏa biểu thức điều kiện |
| EXCLUSION hoặc constraint chuyên biệt | Ngăn các tổ hợp dữ liệu xung đột theo khả năng của database |

Ví dụ:

~~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
~~~~

Constraint ở database là lớp bảo vệ cuối. Nó đặc biệt quan trọng với unique constraint vì hai request đồng thời có thể cùng vượt qua bước kiểm tra “đã tồn tại chưa” trong application trước khi một request ghi dữ liệu.

Ví dụ, service kiểm tra email chưa được dùng rồi mới insert vẫn có race condition nếu hai request chạy đồng thời. Unique constraint ở database mới bảo đảm không thể có hai bản ghi trùng email. Ứng dụng cần bắt và chuyển lỗi integrity thành response phù hợp.

Không nhầm @Column(nullable = false) với Bean Validation @NotNull. Annotation JPA có thể ảnh hưởng mapping/schema generation; nó không tự thay thế việc validate request. Nếu muốn báo lỗi sớm, dùng Bean Validation phù hợp; nếu muốn bảo đảm ở mức lưu trữ, giữ constraint trong database.

## 7. Một request đi qua các lớp kiểm tra như thế nào?

Luồng POST hoặc PUT ở controller MVC có thể hình dung:

~~~~text
HTTP request
    |
    v
Kiểm tra Content-Type / chọn message converter
    |
    v
Parse JSON và deserialize thành DTO/object
    |
    +-- JSON sai hoặc binding thất bại --> lỗi đọc request
    |
    v
Bean Validation (@Valid / @Validated)
    |
    +-- Constraint thất bại -----------> lỗi validation
    |
    v
Application service / domain rules
    |
    +-- Sai trạng thái hoặc không có quyền --> lỗi nghiệp vụ/quyền
    |
    v
Repository / transaction
    |
    v
Database constraints
    |
    +-- Vi phạm NOT NULL / UNIQUE / FK / CHECK --> lỗi integrity
    |
    v
Commit và trả response
~~~~

Với Spring Data REST, sau khi body được đọc và chuyển thành domain object, các repository event như beforeCreate hoặc beforeSave là điểm tích hợp validator. Nếu cần kiểm soát quy trình nghiệp vụ nhiều bước, có thể dùng custom controller/application service thay vì để repository event gánh toàn bộ use case.

Một lớp thất bại thì các bước sau không nên tiếp tục theo cách tạo ra trạng thái dở dang. Với thao tác nhiều bước, dùng transaction và bảo đảm các thay đổi được commit hoặc rollback như một đơn vị phù hợp.

## 8. Ví dụ phân loại lỗi của cùng một endpoint

Giả sử endpoint tạo booking nhận:

~~~~json
{
  "customerId": 10,
  "startDate": "2026-12-10",
  "endDate": "2026-12-08",
  "guestCount": 0
}
~~~~

| Kiểm tra | Kết quả |
|---|---|
| JSON syntax | Hợp lệ |
| Data binding | Có thể thành công nếu field có kiểu Long, LocalDate và Integer |
| Bean Validation | guestCount = 0 có thể vi phạm @Min(1) |
| Object-level validation | endDate trước startDate vi phạm constraint cấp object |
| Business rule | customer có thể bị khóa hoặc không được phép đặt booking trong thời gian đó |
| Database constraint | customer_id có thể vi phạm foreign key nếu customer không tồn tại |

Nếu body bị đổi thành:

~~~~json
{
  "customerId": "ten",
  "startDate": "not-a-date"
}
~~~~

thì lỗi xuất hiện ở parse/binding trước khi Bean Validation hoặc business service được gọi.

Nếu body parse thành công và guestCount hợp lệ nhưng customer không thuộc tenant hiện tại, đây là lỗi authorization/business context, không phải lỗi JSON.

## 9. Thiết kế error response rõ ràng

Client cần biết lỗi thuộc lớp nào và field nào cần sửa. Nên chuẩn hóa error response thay vì trả stack trace hoặc câu SQL từ database.

Một cấu trúc có thể dùng:

~~~~json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Request validation failed",
  "status": 400,
  "detail": "Một hoặc nhiều field không hợp lệ",
  "errors": [
    {
      "field": "guestCount",
      "code": "Min",
      "message": "Số khách phải ít nhất là 1"
    }
  ]
}
~~~~

Có thể phân nhóm lỗi:

- **Malformed request:** body không parse hoặc không deserialize được.
- **Constraint violation:** field hoặc object không thỏa Bean Validation.
- **Business conflict:** thao tác không hợp lệ trong trạng thái hiện tại, ví dụ đơn hàng đã giao.
- **Authorization failure:** người gọi không có quyền trên resource hoặc thao tác.
- **Persistence integrity failure:** vi phạm unique, foreign key, not-null hoặc check constraint.

Status code cần nhất quán với contract API. 400 thường dùng cho request không đọc được hoặc validation thất bại; 403 cho trường hợp không được phép; 404 khi resource không tồn tại hoặc được ẩn theo chính sách; 409 cho xung đột trạng thái; 412 thường dành cho precondition như ETag không khớp. Lỗi database cần được ánh xạ theo ngữ cảnh thay vì để lộ tên constraint hoặc SQL.

Trong Spring MVC, có thể dùng @RestControllerAdvice để chuẩn hóa MethodArgumentNotValidException, HttpMessageNotReadableException, lỗi nghiệp vụ và lỗi integrity. Với Spring Data REST, cần kiểm tra exception handler mặc định và bổ sung cách xử lý tương thích nếu muốn response thống nhất với custom controller.

## 10. Kiểm thử từng lớp độc lập và kiểm thử tích hợp

Một bộ test tốt nên kiểm tra cả nguyên nhân lỗi và việc không có dữ liệu sai được lưu.

### Test cú pháp và binding

- JSON malformed bị từ chối.
- Field có kiểu sai bị từ chối.
- Ngày không parse được bị từ chối.
- Content-Type không hỗ trợ bị từ chối.
- Controller/service không được gọi khi message conversion thất bại.

### Test Bean Validation

- Null, chuỗi rỗng và chuỗi chỉ có khoảng trắng được phân biệt đúng.
- Giới hạn độ dài, số và pattern hoạt động.
- Nested object được cascade validation.
- Class-level constraint phát hiện quan hệ sai giữa các field.
- Create/update dùng đúng validation group.

### Test business rules

- Chỉ trạng thái được phép mới thực hiện transition.
- Người dùng không truy cập dữ liệu ngoài tenant.
- Hết tồn kho thì không thể xác nhận đơn hàng.
- Lỗi giữa use case nhiều bước làm transaction rollback.
- Cùng một business rule được áp dụng khi gọi từ REST, batch hoặc message consumer.

### Test database constraints

- Unique constraint ngăn ghi trùng trong trường hợp request đồng thời.
- Foreign key từ chối tham chiếu không tồn tại.
- Check constraint từ chối giá trị ngoài phạm vi.
- Ứng dụng chuyển persistence exception thành error response ổn định.

Với Spring Data REST, cần integration test riêng cho validator event được đăng ký: POST phải kích hoạt beforeCreate, PUT/PATCH phải kích hoạt beforeSave theo luồng repository tương ứng. Đừng chỉ unit test Validator rồi suy ra endpoint đã nối validator đúng.

## 11. Chọn đúng nơi cho từng loại kiểm tra

| Câu hỏi | Lớp phù hợp |
|---|---|
| Body có phải JSON hợp lệ không? | JSON parser / HttpMessageConverter |
| Chuỗi này có chuyển thành LocalDate được không? | Data binding / Conversion |
| Tên có bị rỗng hoặc quá dài không? | Bean Validation |
| Ngày kết thúc có sau ngày bắt đầu không? | Class-level validation hoặc domain rule tùy tính chất |
| Người dùng có được sửa resource này không? | Authorization / security policy |
| Đơn hàng có đang ở trạng thái cho phép xác nhận không? | Domain/application service |
| Hai request đồng thời có tạo trùng order number không? | Database unique constraint và xử lý xung đột |
| Resource liên quan có tồn tại không? | Business/service validation và foreign key |
| Một use case nhiều bước có được commit toàn bộ không? | Transaction boundary |

Một quy tắc có thể cần xuất hiện ở hơn một lớp với mục đích khác nhau. Ví dụ, quantity phải lớn hơn 0 có thể được kiểm tra sớm bằng @Min để phản hồi thân thiện, đồng thời được bảo vệ bằng CHECK constraint để giữ toàn vẹn dữ liệu khi có đường ghi khác.

## 12. Kết luận

Kiểm tra cú pháp JSON và data binding xác nhận request có thể được đọc thành kiểu dữ liệu mà endpoint mong đợi. Bean Validation kiểm tra các ràng buộc trên field và object như nullability, độ dài, định dạng, phạm vi và quan hệ giữa các field. Business rule quyết định thao tác có hợp lệ trong trạng thái và ngữ cảnh thực tế hay không. Database constraints bảo vệ tính toàn vẹn ở thời điểm lưu, kể cả khi có nhiều luồng ghi đồng thời.

Trong Spring Data REST, có thể gắn Spring Validator vào các event như beforeCreate, beforeSave và beforeLinkSave bằng tên bean hoặc RepositoryRestConfigurer. Với custom MVC controller, @Valid/@Validated kích hoạt Bean Validation sau bước deserialize. Hãy đặt quy tắc nghiệp vụ trong domain/service, dùng transaction cho use case nhiều bước và giữ constraint quan trọng ở database. Khi phân lớp rõ ràng, lỗi dễ chẩn đoán, response dễ chuẩn hóa và các đường ghi khác nhau có thể cùng tuân thủ một hợp đồng dữ liệu.

## Tài liệu tham khảo

- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST — ValidatingRepositoryEventListener API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/ValidatingRepositoryEventListener.html)
- [Spring Framework — @RequestBody and message conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
