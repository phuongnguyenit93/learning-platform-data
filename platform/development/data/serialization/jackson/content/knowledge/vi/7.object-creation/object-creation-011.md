# Phân biệt khả năng khởi tạo đối tượng và kiểm tra dữ liệu hợp lệ

Khi Jackson đọc JSON thành một object Java, việc tạo được object chỉ chứng minh dữ liệu đã đi qua một phần của quá trình ánh xạ. Điều đó chưa chứng minh dữ liệu đáp ứng yêu cầu của ứng dụng. Một object có thể được tạo thành công nhưng vẫn thiếu tên, chứa email sai định dạng, có số lượng âm hoặc vi phạm quy tắc nghiệp vụ.

Cần phân biệt hai trách nhiệm:

- **Object creation và data binding**: Jackson phân tích JSON, xác định kiểu đích, tạo object và đưa giá trị vào các property.
- **Validation**: ứng dụng kiểm tra object đã tạo có đáp ứng các ràng buộc về dữ liệu và nghiệp vụ hay không.

Jackson tập trung vào việc chuyển đổi cấu trúc JSON thành cấu trúc Java. Jakarta Bean Validation cung cấp cơ chế khai báo và thực thi constraint trên object. Constructor, factory method và domain model còn có thể bảo vệ những bất biến mà ứng dụng không cho phép vi phạm.

## 1. Một object được tạo thành công chưa chắc hợp lệ

Giả sử API nhận yêu cầu tạo tài khoản. JSON sau đúng cú pháp và có thể ánh xạ vào một class Java:

~~~json
{
  "username": "",
  "email": "not-an-email",
  "age": -5
}
~~~

Nếu class có constructor và property tương ứng, Jackson có thể tạo object từ dữ liệu này. Nhưng theo yêu cầu thông thường:

- Username không được để trống.
- Email phải có định dạng phù hợp.
- Age phải lớn hơn hoặc bằng 18.

Object đã được tạo nhưng dữ liệu không đáp ứng hợp đồng.

Quá trình xử lý nên được nhìn thành các giai đoạn:

~~~mermaid
flowchart TD
    A[JSON text hoặc bytes] --> B[Parse JSON]
    B -->|Cú pháp hợp lệ| C[Jackson data binding]
    B -->|Sai cú pháp| X[Lỗi parse]
    C -->|Tạo và ánh xạ được object| D[Java object]
    C -->|Sai kiểu hoặc không tạo được| Y[Lỗi mapping / creation]
    D --> E[Bean Validation]
    E -->|Constraint không đạt| Z[Lỗi validation]
    E -->|Constraint đạt| F[Kiểm tra quy tắc nghiệp vụ]
    F -->|Hợp lệ| G[Thực hiện use case]
    F -->|Vi phạm bất biến nghiệp vụ| H[Lỗi nghiệp vụ]
~~~

Có thể phân biệt bốn câu hỏi:

1. JSON có đúng cú pháp không?
2. Các giá trị JSON có thể ánh xạ vào kiểu Java đích không?
3. Object đã tạo có đáp ứng các constraint dữ liệu không?
4. Dữ liệu có hợp lệ trong ngữ cảnh nghiệp vụ hiện tại không?

Mỗi câu hỏi thuộc một lớp xử lý khác nhau. Không nên xem việc ObjectMapper trả về object là bằng chứng rằng cả bốn câu hỏi đều đã được trả lời.

## 2. Jackson chịu trách nhiệm khởi tạo và ánh xạ đối tượng

### 2.1. Khởi tạo JavaBean bằng constructor và setter

Một JavaBean thông thường có constructor không tham số, field và setter:

~~~java
public class CreateAccountRequest {

    private String username;
    private String email;
    private Integer age;

    public CreateAccountRequest() {
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Với class này, Jackson thường thực hiện các bước:

1. Phân tích JSON thành cấu trúc token.
2. Xác định kiểu đích là CreateAccountRequest.
3. Tạo instance bằng constructor không tham số.
4. Tìm property tương ứng với các khóa JSON.
5. Chuyển đổi giá trị sang kiểu Java.
6. Gọi setter hoặc gán field theo metadata và cấu hình.
7. Trả về instance đã ánh xạ.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

String json = """
        {
          "username": "an",
          "email": "an@example.com",
          "age": 25
        }
        """;

CreateAccountRequest request =
        mapper.readValue(json, CreateAccountRequest.class);
~~~

Đến đây, Jackson đã hoàn thành việc tạo object và ánh xạ dữ liệu. Jackson không tự suy ra rằng username phải có ít nhất ba ký tự hoặc age phải lớn hơn 18 nếu ứng dụng chưa cung cấp quy tắc tương ứng.

### 2.2. Khởi tạo bằng constructor hoặc factory method

Class bất biến có thể không có setter. Ứng dụng truyền dữ liệu vào constructor để tạo object:

~~~java
public class Money {

    private final String currency;
    private final long amount;

    @JsonCreator
    public Money(
            @JsonProperty("currency") String currency,
            @JsonProperty("amount") long amount) {
        this.currency = currency;
        this.amount = amount;
    }

    public String getCurrency() {
        return currency;
    }

    public long getAmount() {
        return amount;
    }
}
~~~

Ở đây, Jackson dùng creator được chỉ định để tạo object. Giá trị JSON được chuyển thành tham số constructor trước khi instance hoàn chỉnh được trả về.

Constructor có thể kiểm tra một số bất biến ngay lúc tạo:

~~~java
public Money(String currency, long amount) {
    if (currency == null || currency.isBlank()) {
        throw new IllegalArgumentException("Currency is required");
    }
    if (amount < 0) {
        throw new IllegalArgumentException("Amount cannot be negative");
    }

    this.currency = currency;
    this.amount = amount;
}
~~~

Nếu constructor từ chối dữ liệu, Jackson không thể hoàn tất quá trình tạo object và lỗi có thể được bọc trong exception ánh xạ. Đây là kiểm tra do chính model thực hiện, không phải Bean Validation tự động.

Constructor phù hợp để bảo vệ bất biến thiết yếu của object. Tuy nhiên, không nên đưa toàn bộ quy tắc kiểm tra định dạng request, thông báo lỗi theo ngôn ngữ hoặc kiểm tra phụ thuộc database vào constructor. Những trách nhiệm đó thường thuộc validation layer hoặc application/domain service.

### 2.3. Khởi tạo record

Record là lựa chọn gọn cho DTO chỉ mang dữ liệu:

~~~java
public record AccountRequest(
        String username,
        String email,
        Integer age
) {
}
~~~

Các phiên bản Jackson hiện đại hỗ trợ record. Jackson ánh xạ dữ liệu vào canonical constructor của record. Record không có setter; sau khi tạo, các component không thể được gán lại như property của JavaBean thông thường.

Record cũng có thể mang annotation validation:

~~~java
public record AccountRequest(
        @NotBlank String username,
        @NotBlank @Email String email,
        @NotNull @Min(18) Integer age
) {
}
~~~

Các annotation trên mô tả constraint. Việc Jackson tạo được record vẫn không đồng nghĩa các constraint đã được thực thi. Ứng dụng phải gọi Validator hoặc để framework kích hoạt validation theo cơ chế phù hợp.

Khả năng hỗ trợ record và annotation phụ thuộc phiên bản Java, Jackson và Bean Validation provider đang dùng. Hãy kiểm tra phiên bản thực tế của dự án.

## 3. Jackson kiểm tra điều gì trong lúc ánh xạ?

Jackson có thể từ chối dữ liệu khi không thể phân tích hoặc chuyển đổi theo kiểu đích. Đây là các kiểm tra phục vụ quá trình parse và data binding.

### 3.1. Kiểm tra cú pháp JSON

JSON sai cú pháp không thể được phân tích:

~~~json
{
  "username": "an",
  "age": 25,
}
~~~

Dấu phẩy cuối object không thuộc cú pháp JSON chuẩn. Parser có thể ném lỗi trước khi Jackson tạo được object.

### 3.2. Kiểm tra khả năng ánh xạ kiểu

Giả sử Java khai báo:

~~~java
private int age;
~~~

Nhưng JSON gửi một object:

~~~json
{
  "age": {
    "value": 25
  }
}
~~~

Jackson không thể ánh xạ cấu trúc object đó thành int theo quy tắc thông thường và có thể ném lỗi mapping.

Tương tự, giá trị enum không nhận diện được, kiểu lồng nhau sai cấu trúc hoặc creator không phù hợp đều có thể làm quá trình ánh xạ thất bại.

### 3.3. Property không được nhận diện

JSON có thể chứa property không có trong class đích:

~~~json
{
  "username": "an",
  "department": "Engineering"
}
~~~

Với cấu hình Jackson Databind thông thường, DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES được bật. Khi đó, property lạ có thể làm thao tác đọc thất bại. Nếu feature được tắt hoặc class dùng JsonIgnoreProperties(ignoreUnknown = true), Jackson có thể bỏ qua property này.

Đây là chính sách ánh xạ cấu trúc. Nó không phải kiểm tra username có hợp lệ hay không.

### 3.4. Giá trị bắt buộc trong creator

Jackson có các feature liên quan đến property được truyền vào creator, ví dụ FAIL_ON_MISSING_CREATOR_PROPERTIES và FAIL_ON_NULL_CREATOR_PROPERTIES trong các phiên bản hỗ trợ. JsonProperty(required = true) cũng có vai trò nhất định đối với property creator.

Các cơ chế này có thể giúp kiểm soát dữ liệu thiếu hoặc null trong lúc tạo object. Tuy nhiên, chúng không thay thế validation tổng quát:

- Chúng không kiểm tra username có đúng định dạng không.
- Chúng không kiểm tra email có hợp lệ không.
- Chúng không kiểm tra tuổi có nằm trong giới hạn nghiệp vụ không.
- Chúng không kiểm tra hai thuộc tính có nhất quán với nhau không.

Vì vậy, cần phân biệt **điều kiện để Jackson tạo được object** với **điều kiện để ứng dụng chấp nhận object**.

## 4. Jakarta Bean Validation kiểm tra constraint trên object

Jakarta Bean Validation là đặc tả cung cấp cách khai báo và thực thi các ràng buộc dữ liệu bằng annotation. Một implementation như Hibernate Validator thực thi các constraint đó.

Các annotation thường gặp:

| Annotation | Ý nghĩa |
|---|---|
| @NotNull | Giá trị không được null |
| @NotBlank | String phải khác null và có ít nhất một ký tự không phải khoảng trắng |
| @NotEmpty | String, collection, map hoặc array không được rỗng theo kiểu được hỗ trợ |
| @Size(min, max) | Giới hạn kích thước hoặc độ dài |
| @Min(value) | Giá trị số phải lớn hơn hoặc bằng ngưỡng |
| @Max(value) | Giá trị số phải nhỏ hơn hoặc bằng ngưỡng |
| @Positive | Giá trị số phải dương |
| @Email | Kiểm tra định dạng email theo quy tắc của provider |
| @Pattern | Giá trị string phải khớp regular expression |
| @Valid | Kích hoạt validation đệ quy cho object lồng nhau khi validator chạy |

Các annotation này chỉ mô tả constraint. Muốn kiểm tra, phải có thành phần gọi validation.

### 4.1. Khai báo constraint trên DTO

Ví dụ request tạo tài khoản:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class CreateAccountRequest {

    @NotBlank
    @Size(min = 3, max = 30)
    private String username;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    public CreateAccountRequest() {
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Các constraint thể hiện hợp đồng dữ liệu:

- username không được null, rỗng hoặc chỉ chứa khoảng trắng; độ dài từ 3 đến 30.
- email phải có nội dung và phù hợp với kiểm tra định dạng email.
- age phải có giá trị và không nhỏ hơn 18.

Chọn Integer thay vì int cho age để validation có thể nhận diện trạng thái null. Nếu dùng int, property bị thiếu thường giữ giá trị mặc định 0; Min(18) vẫn có thể phát hiện giá trị đó không đạt, nhưng ứng dụng mất khả năng phân biệt rõ null với số 0.

### 4.2. Gọi Validator trong Java độc lập

Trong ứng dụng không dùng Spring, có thể gọi Jakarta Bean Validation trực tiếp:

~~~java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import java.util.Set;

public class AccountValidationDemo {

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            CreateAccountRequest request = new CreateAccountRequest();
            request.setUsername("");
            request.setEmail("not-an-email");
            request.setAge(15);

            Set<ConstraintViolation<CreateAccountRequest>> violations =
                    validator.validate(request);

            if (!violations.isEmpty()) {
                for (ConstraintViolation<CreateAccountRequest> violation
                        : violations) {
                    System.out.println(
                            violation.getPropertyPath() + ": "
                                    + violation.getMessage()
                    );
                }
                return;
            }

            System.out.println("Request is valid");
        }
    }
}
~~~

Lời gọi validator.validate(request) mới là thời điểm các constraint được thực thi. Chỉ tạo object có annotation không làm validation tự chạy.

Mỗi ConstraintViolation cung cấp thông tin như property path, invalid value, message và metadata của constraint. Ứng dụng có thể chuyển các violation thành lỗi API theo format thống nhất.

Để chạy ví dụ, cần có Jakarta Validation API và một implementation tương thích, chẳng hạn Hibernate Validator. Chỉ thêm dependency API mà không có provider thì không đủ để tạo validator mặc định.

### 4.3. Phân biệt @NotNull và @NotBlank

Hai constraint có ý nghĩa khác nhau:

~~~java
@NotNull
private String displayName;
~~~

@NotNull chỉ yêu cầu giá trị không null. Chuỗi rỗng và chuỗi chỉ có khoảng trắng vẫn có thể đạt constraint này.

~~~java
@NotBlank
private String username;
~~~

@NotBlank yêu cầu chuỗi không null và phải có ít nhất một ký tự không phải khoảng trắng. Với trường username, NotBlank thường sát ý nghĩa hơn NotNull.

Tương tự, Size(min = 3) kiểm tra độ dài nhưng không tự thay thế NotBlank. Một chuỗi ba dấu cách có thể đạt yêu cầu độ dài trong khi vẫn không phải username hợp lệ. Có thể kết hợp nhiều constraint khi hợp đồng yêu cầu.

## 5. Validation object lồng nhau

Một DTO có thể chứa object khác:

~~~java
public class CreateOrderRequest {

    @NotBlank
    private String orderId;

    @NotNull
    @Valid
    private CustomerInfo customer;

    @NotEmpty
    @Valid
    private List<OrderLineRequest> lines;

    // Constructor, getter và setter.
}
~~~

@Valid đánh dấu rằng khi validator kiểm tra CreateOrderRequest, nó tiếp tục kiểm tra các object lồng nhau. Nếu thiếu @Valid, validator có thể chỉ kiểm tra constraint ở cấp property của object cha mà không đi sâu vào thuộc tính bên trong.

Ví dụ:

~~~java
public class CustomerInfo {

    @NotBlank
    private String name;

    @Email
    @NotBlank
    private String email;

    // Constructor, getter và setter.
}
~~~

~~~java
public class OrderLineRequest {

    @NotBlank
    private String productCode;

    @Min(1)
    private int quantity;

    // Constructor, getter và setter.
}
~~~

Khi gọi validator.validate(orderRequest), validator có thể trả về violation ở các đường dẫn lồng nhau, chẳng hạn customer.email hoặc lines[0].quantity.

@Valid không có nghĩa Jackson tự kiểm tra object con. Jackson vẫn chỉ tạo và ánh xạ cấu trúc; Bean Validation mới thực hiện kiểm tra đệ quy khi được gọi.

## 6. Validation trong Spring Boot

Spring Boot có thể tích hợp Bean Validation với Spring MVC. Khi endpoint nhận request body, Spring thực hiện chuyển đổi JSON trước, sau đó kích hoạt validation nếu tham số được đánh dấu phù hợp.

Ví dụ:

~~~java
@RestController
@RequestMapping("/accounts")
public class AccountController {

    @PostMapping
    public ResponseEntity<String> create(
            @Valid @RequestBody CreateAccountRequest request) {

        return ResponseEntity.ok("Account request accepted");
    }
}
~~~

Dependency của ứng dụng Spring Boot thường dùng starter validation:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

Khi nhận request:

1. HTTP message converter đọc body.
2. Jackson parse JSON và ánh xạ thành CreateAccountRequest.
3. Spring kích hoạt Bean Validation do có @Valid.
4. Nếu có constraint vi phạm, Spring MVC phát sinh lỗi validation; trong trường hợp request body phổ biến, exception thường gặp là MethodArgumentNotValidException.
5. Nếu validation đạt, method controller nhận object và tiếp tục xử lý.

Ví dụ JSON:

~~~json
{
  "username": "",
  "email": "wrong",
  "age": 15
}
~~~

JSON này đúng cú pháp và có thể ánh xạ vào DTO. Nhưng validation thất bại vì username trống, email không đúng định dạng và age nhỏ hơn 18.

### 6.1. Phân biệt lỗi mapping và lỗi validation trong API

Hai loại lỗi xảy ra ở thời điểm khác nhau:

| Tình huống | Giai đoạn | Ví dụ |
|---|---|---|
| JSON sai cú pháp | Parse | Thiếu dấu ngoặc hoặc có dấu phẩy thừa |
| Giá trị không thể chuyển sang kiểu Java | Data binding | Object JSON được gửi vào field int |
| Không tạo được object | Object creation | Không có creator phù hợp hoặc constructor từ chối dữ liệu |
| Object tạo được nhưng vi phạm constraint | Bean Validation | Username rỗng, age dưới ngưỡng |
| Constraint đạt nhưng sai quy tắc nghiệp vụ | Business validation | Tài khoản trùng email trong database |

Trong Spring MVC, lỗi đọc/ánh xạ request body thường được biểu diễn bằng HttpMessageNotReadableException. Lỗi Bean Validation của request body thường được biểu diễn bằng MethodArgumentNotValidException. Cơ chế method validation và loại exception có thể khác theo phiên bản Spring và kiểu tham số được kiểm tra.

Ứng dụng nên ánh xạ các lỗi này thành response nhất quán, nhưng vẫn giữ được nguyên nhân để log và chẩn đoán.

### 6.2. Trả lỗi validation có cấu trúc

Một exception handler có thể thu thập field error:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> handleValidation(
            MethodArgumentNotValidException exception) {

        Map<String, String> errors = new LinkedHashMap<>();

        exception.getBindingResult()
                .getFieldErrors()
                .forEach(error ->
                        errors.put(error.getField(), error.getDefaultMessage())
                );

        return ResponseEntity.badRequest().body(errors);
    }
}
~~~

Ví dụ response:

~~~json
{
  "username": "must not be blank",
  "email": "must be a well-formed email address",
  "age": "must be greater than or equal to 18"
}
~~~

Trong ứng dụng thực tế, nên dùng mã lỗi ổn định và message đã được chuẩn hóa hoặc bản địa hóa. Không nên phụ thuộc hoàn toàn vào nội dung message mặc định của provider vì message có thể thay đổi theo phiên bản hoặc locale.

## 7. Validation dữ liệu khác với bất biến nghiệp vụ

Bean Validation phù hợp với constraint có thể mô tả trên object: không null, không rỗng, độ dài, giới hạn số, định dạng hoặc quan hệ giữa các field. Tuy nhiên, không phải quy tắc nào cũng nên đặt trong DTO.

Ví dụ, một request chuyển tiền có thể thỏa:

- Số tiền lớn hơn 0.
- Mã tiền tệ không rỗng.
- Tài khoản nguồn có định dạng hợp lệ.

Nhưng request vẫn có thể không được phép thực hiện vì tài khoản nguồn đã bị khóa, tài khoản đích không tồn tại, số dư không đủ, người dùng không có quyền hoặc giao dịch vượt hạn mức theo trạng thái hiện tại.

Các điều kiện này phụ thuộc dữ liệu hệ thống, quyền truy cập hoặc trạng thái tại thời điểm thực hiện. Chúng thuộc application/domain service và cần được kiểm tra trong ngữ cảnh nghiệp vụ.

### 7.1. Constraint ở DTO

DTO mô tả dữ liệu đầu vào:

~~~java
public class TransferRequest {

    @NotBlank
    private String sourceAccount;

    @NotBlank
    private String destinationAccount;

    @NotNull
    @Positive
    private BigDecimal amount;

    // Constructor, getter và setter.
}
~~~

Các constraint giúp loại bỏ request thiếu tài khoản hoặc số tiền không dương trước khi vào nghiệp vụ.

### 7.2. Quy tắc phụ thuộc trạng thái hệ thống

Service tiếp tục kiểm tra điều kiện nghiệp vụ:

~~~java
@Service
public class TransferService {

    public void transfer(TransferRequest request) {
        Account source = accountRepository
                .findByNumber(request.getSourceAccount())
                .orElseThrow(() -> new AccountNotFoundException("Source account not found"));

        Account destination = accountRepository
                .findByNumber(request.getDestinationAccount())
                .orElseThrow(() -> new AccountNotFoundException("Destination account not found"));

        if (source.isLocked()) {
            throw new BusinessRuleException("Source account is locked");
        }

        if (source.getBalance().compareTo(request.getAmount()) < 0) {
            throw new BusinessRuleException("Insufficient balance");
        }

        source.debit(request.getAmount());
        destination.credit(request.getAmount());
    }
}
~~~

Đây là ví dụ minh họa ranh giới trách nhiệm. Trong hệ thống thực tế, thao tác kiểm tra số dư và ghi nhận giao dịch phải được thiết kế cùng transaction và cơ chế đồng thời phù hợp để tránh hai giao dịch cùng sử dụng một số dư cũ.

Không nên đặt truy vấn database vào constraint annotation đơn giản chỉ để kiểm tra mọi thứ tại một nơi. Quy tắc phụ thuộc trạng thái hệ thống cần được xử lý ở tầng có đủ ngữ cảnh và kiểm soát transaction.

### 7.3. Bảo vệ bất biến trong domain object

Một domain object có thể tự bảo vệ trạng thái không hợp lệ:

~~~java
public class Money {

    private final String currency;
    private final BigDecimal amount;

    public Money(String currency, BigDecimal amount) {
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("Currency is required");
        }

        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("Amount must be non-negative");
        }

        this.currency = currency;
        this.amount = amount;
    }

    public String getCurrency() {
        return currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
~~~

Bất biến ở constructor bảo đảm mọi Money được tạo thành công đều có currency và amount theo quy tắc đã chọn. Điều này hữu ích khi object được tạo từ nhiều nguồn, không chỉ từ HTTP JSON.

Tuy nhiên, cần chọn đúng ranh giới: DTO có thể chấp nhận dữ liệu chưa hợp lệ để trả về nhiều lỗi validation cùng lúc; domain value object thường nên không cho phép trạng thái vô nghĩa tồn tại sau khi khởi tạo.

## 8. Những điểm dễ nhầm về required, null và validation

### 8.1. JsonProperty(required = true) không phải validation tổng quát

Thuộc tính required có vai trò trong quá trình ánh xạ creator property theo hỗ trợ của Jackson. Nó không thay thế NotBlank, Size hoặc quy tắc nghiệp vụ. Một username có mặt trong JSON nhưng là chuỗi rỗng vẫn có thể vượt qua kiểm tra sự hiện diện của creator property.

### 8.2. NotNull không phân biệt property bị thiếu và null tường minh

Với field reference:

~~~java
@NotNull
private Integer quantity;
~~~

Cả JSON không có quantity và JSON có quantity bằng null thường đều dẫn đến giá trị null trên object mới, sau đó NotNull báo vi phạm.

Nếu hợp đồng cần phân biệt hai trạng thái, DTO thông thường có thể không giữ đủ thông tin. Có thể dùng tree model, custom deserializer hoặc kiểu biểu diễn trạng thái hiện diện riêng. Không nên giả định NotNull cho biết client đã gửi khóa hay chưa.

### 8.3. Primitive có thể che giấu việc thiếu dữ liệu

Với:

~~~java
@NotNull
private int quantity;
~~~

Cách khai báo này không hợp lý vì primitive không thể null. Nếu property bị thiếu, field có thể giữ giá trị mặc định 0; NotNull không phát hiện được trạng thái thiếu. Nếu cần bắt buộc có giá trị và phân biệt với 0, hãy dùng Integer cùng NotNull, rồi thêm Min(1) nếu nghiệp vụ yêu cầu số lượng dương.

### 8.4. Validation không tự chạy chỉ vì có annotation

Đoạn code sau chỉ khai báo metadata:

~~~java
public class UserRequest {
    @NotBlank
    private String name;
}
~~~

Nếu code chỉ gọi mapper.readValue(json, UserRequest.class), Jackson tạo object. Nếu không có lệnh validator.validate(request) hoặc cơ chế framework kích hoạt validation, các constraint chưa được thực thi.

Trong Spring MVC, @Valid @RequestBody là một cách kích hoạt validation. Trong Java độc lập, ứng dụng phải gọi Validator trực tiếp.

## 9. Thứ tự xử lý và cách thiết kế phù hợp

Một pipeline request thường có thứ tự:

1. **Parse**: xác nhận JSON có cú pháp hợp lệ.
2. **Bind/create**: Jackson chuyển JSON thành DTO.
3. **Validate DTO**: kiểm tra constraint dữ liệu đầu vào.
4. **Map/use case**: chuyển DTO thành command hoặc domain input phù hợp.
5. **Check business rules**: kiểm tra quyền, trạng thái và dữ liệu hệ thống.
6. **Execute**: thực hiện nghiệp vụ trong transaction khi cần.

Mỗi bước nên trả về loại lỗi có ý nghĩa. Không nên gộp mọi lỗi thành một thông báo "JSON không hợp lệ", vì client và developer cần biết lỗi nằm ở cú pháp, kiểu dữ liệu, constraint hay nghiệp vụ.

| Lớp | Câu hỏi | Cơ chế thường dùng |
|---|---|---|
| JSON parser | Văn bản có đúng JSON không? | Jackson Core |
| Data binding | Có thể tạo và điền kiểu Java không? | Jackson Databind |
| DTO validation | Dữ liệu có đạt constraint không? | Jakarta Bean Validation |
| Domain invariant | Object có thể tồn tại hợp lệ không? | Constructor/factory/domain method |
| Business validation | Hành động có được phép trong trạng thái hiện tại không? | Application/domain service |

## 10. Checklist áp dụng

Khi xây dựng endpoint hoặc xử lý JSON, hãy tự xác định:

- Kiểu Java đích và cách Jackson tạo object: constructor không tham số, creator hay record.
- Property nào bắt buộc, property nào có thể null và kiểu nào cần wrapper.
- Lỗi nào do JSON sai cú pháp hoặc không ánh xạ được kiểu.
- Constraint nào có thể khai báo bằng Jakarta Bean Validation.
- Validation được kích hoạt ở đâu: gọi Validator trực tiếp hay @Valid trong Spring.
- Object lồng nhau có cần @Valid để kiểm tra đệ quy không.
- Quy tắc nào phụ thuộc database, quyền hoặc trạng thái nghiệp vụ và cần đưa vào service/domain.
- Có cần phân biệt property bị thiếu với property null hay không.
- API response có phân biệt lỗi parse, mapping, validation và business rule không.

Hiểu rõ khả năng khởi tạo object và việc kiểm tra dữ liệu hợp lệ giúp tránh một lỗi thiết kế phổ biến: coi một object đã được Jackson tạo ra là object đã sẵn sàng đưa vào nghiệp vụ. Jackson bảo đảm việc chuyển đổi theo khả năng và cấu hình ánh xạ; validation và domain logic mới quyết định dữ liệu có được ứng dụng chấp nhận hay không.
