# Bảo toàn bất biến nghiệp vụ khi tạo đối tượng từ dữ liệu ngoài

JSON nhận từ HTTP request, message queue, file hoặc hệ thống đối tác là dữ liệu bên ngoài. Dữ liệu đó có thể thiếu field, chứa `null`, sai kiểu, sai định dạng hoặc hợp lệ về cú pháp nhưng vi phạm quy tắc nghiệp vụ. Jackson có thể chuyển JSON thành object Java, nhưng việc deserialize thành công không chứng minh object đó hợp lệ để đưa vào nghiệp vụ.

Khi dùng Jackson để tạo đối tượng, cần bảo đảm các **bất biến nghiệp vụ** luôn được giữ đúng. Bất biến là điều kiện phải đúng trong suốt vòng đời của một object, chẳng hạn số tiền phải dương, tài khoản nguồn và đích phải khác nhau, mã tiền tệ phải hợp lệ hoặc trạng thái đơn hàng chỉ được chuyển theo những bước cho phép.

Một thiết kế an toàn thường có các bước:

```text
Dữ liệu ngoài (JSON)
       |
       v
Jackson parse + deserialize
       |
       v
Input DTO (dữ liệu tiếp nhận)
       |
       v
Kiểm tra field, kiểu dữ liệu, validation
       |
       v
Factory / constructor của domain
       |
       v
Đối tượng nghiệp vụ đã thỏa bất biến
```

Jackson chịu trách nhiệm chuyển đổi cấu trúc và kiểu dữ liệu. Lớp nghiệp vụ chịu trách nhiệm bảo vệ trạng thái hợp lệ. Hai trách nhiệm này liên quan chặt chẽ nhưng không nên bị nhầm lẫn.

## 1. Bất biến nghiệp vụ là gì?

Giả sử hệ thống có nghiệp vụ chuyển tiền. Một giao dịch chuyển tiền có thể cần bảo đảm:

- Tài khoản nguồn và tài khoản nhận phải tồn tại dưới dạng mã hợp lệ.
- Tài khoản nguồn không được trùng tài khoản nhận.
- Số tiền phải lớn hơn 0.
- Đơn vị tiền tệ phải thuộc danh sách hệ thống hỗ trợ.
- Một giao dịch đã được tạo không được thay đổi số tiền hoặc tài khoản tùy ý.

Đây là các điều kiện của domain. Nếu một object `Transfer` đã được tạo, code phía sau phải có quyền tin rằng những điều kiện này luôn đúng.

Ví dụ, một object như sau là nguy hiểm:

```java
public class Transfer {
    public String sourceAccount;
    public String destinationAccount;
    public BigDecimal amount;
}
```

Mọi đoạn code đều có thể gán lại field sau khi object được tạo:

```java
Transfer transfer = new Transfer();
transfer.amount = new BigDecimal("100");
transfer.amount = new BigDecimal("-500");
```

Nếu object được lưu vào database hoặc gửi tới service khác sau lần gán thứ hai, nghiệp vụ có thể nhận một trạng thái không hợp lệ. Chỉ kiểm tra dữ liệu ở controller hoặc ngay sau deserialize không đủ, vì một đoạn code nội bộ khác cũng có thể tạo hoặc sửa object theo cách sai.

## 2. Phân biệt lỗi JSON, lỗi dữ liệu và lỗi nghiệp vụ

Một request có thể thất bại ở nhiều tầng khác nhau:

| Tầng | Ví dụ lỗi | Thành phần thường xử lý |
|---|---|---|
| Cú pháp JSON | Thiếu dấu `}`, dấu nháy không hợp lệ | Jackson parser |
| Ánh xạ kiểu | Chuỗi không chuyển được thành `BigDecimal`, cấu trúc object không khớp kiểu đích | Jackson deserializer |
| Dữ liệu đầu vào | Thiếu mã tài khoản, chuỗi rỗng, số tiền null | Input validation |
| Bất biến domain | Tài khoản nguồn trùng tài khoản nhận, số tiền không dương | Constructor hoặc domain factory |
| Quy tắc phụ thuộc trạng thái hệ thống | Tài khoản không tồn tại, không đủ số dư, giao dịch bị từ chối theo trạng thái hiện tại | Domain service / application service / database |

Không phải mọi quy tắc đều có thể kiểm tra trong constructor. Ví dụ, việc tài khoản có đủ số dư hay không phụ thuộc dữ liệu đang thay đổi trong hệ thống và thường cần transaction hoặc domain service. Tuy nhiên, những điều kiện nội tại của object vẫn phải được constructor/factory bảo vệ.

## 3. Tách Input DTO khỏi domain object

Một cách phổ biến là deserialize JSON vào một DTO dành riêng cho đầu vào. DTO phản ánh cấu trúc giao tiếp bên ngoài; domain object phản ánh trạng thái nghiệp vụ mà hệ thống cho phép.

Ví dụ request JSON:

```json
{
  "source_account": "ACC-001",
  "destination_account": "ACC-002",
  "amount": 250000,
  "currency": "VND"
}
```

DTO dùng cho Jackson:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;

public class CreateTransferRequest {
    @JsonProperty("source_account")
    private String sourceAccount;

    @JsonProperty("destination_account")
    private String destinationAccount;

    private BigDecimal amount;
    private String currency;

    public CreateTransferRequest() {
    }

    public String getSourceAccount() {
        return sourceAccount;
    }

    public String getDestinationAccount() {
        return destinationAccount;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
```

Đọc JSON:

```java
ObjectMapper mapper = new ObjectMapper();
CreateTransferRequest request = mapper.readValue(json, CreateTransferRequest.class);
```

Ở bước này, Jackson chỉ tạo `CreateTransferRequest`. Việc tạo DTO thành công chưa có nghĩa đã tạo được một giao dịch hợp lệ. Các field vẫn có thể null hoặc chứa giá trị không đáp ứng quy tắc nghiệp vụ.

DTO có thể linh hoạt theo hợp đồng API, ví dụ nhận tên field cũ bằng `@JsonAlias`, hỗ trợ field tùy chọn hoặc có cấu trúc lồng nhau. Không cần buộc domain object phải mang toàn bộ sự phức tạp tương thích của API bên ngoài.

## 4. Kiểm tra dữ liệu đầu vào trước khi gọi domain factory

Validation kiểm tra những điều kiện của request trước khi chuyển nó thành đối tượng nghiệp vụ. Có thể dùng Jakarta Bean Validation hoặc kiểm tra tường minh tùy ứng dụng.

### 4.1. Validation bằng Jakarta Bean Validation

Ví dụ DTO có annotation:

```java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import java.math.BigDecimal;

public class CreateTransferRequest {
    @NotBlank
    private String sourceAccount;

    @NotBlank
    private String destinationAccount;

    @NotNull
    @DecimalMin("0.01")
    private BigDecimal amount;

    @NotBlank
    @Pattern(regexp = "[A-Z]{3}")
    private String currency;

    // constructor, getters và setters
}
```

Các annotation mô tả ràng buộc dữ liệu. Chúng không tự chạy chỉ vì Jackson deserialize object. Ứng dụng phải gọi Validator, hoặc dùng tích hợp validation của framework tại đúng điểm tiếp nhận request.

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

import java.util.Set;

try (ValidatorFactory factory = Validation.buildDefaultValidatorFactory()) {
    Validator validator = factory.getValidator();
    Set<ConstraintViolation<CreateTransferRequest>> violations =
            validator.validate(request);

    if (!violations.isEmpty()) {
        throw new IllegalArgumentException("Invalid transfer request");
    }
}
```

Đoạn minh họa trên lược bỏ việc chuyển từng violation thành lỗi API cụ thể. Ứng dụng thực tế nên trả lỗi có field/path và thông điệp phù hợp, đồng thời không đưa dữ liệu nhạy cảm vào log. Cần có implementation của Jakarta Validation, chẳng hạn Hibernate Validator, trên classpath.

### 4.2. Kiểm tra tường minh khi không dùng Bean Validation

Với một ứng dụng nhỏ hoặc quy tắc đơn giản, có thể tạo phương thức chuyển DTO thành domain object và kiểm tra đầu vào tại đó:

```java
public Transfer toDomain() {
    if (sourceAccount == null || sourceAccount.isBlank()) {
        throw new IllegalArgumentException("Source account is required");
    }
    if (destinationAccount == null || destinationAccount.isBlank()) {
        throw new IllegalArgumentException("Destination account is required");
    }
    if (amount == null || amount.signum() <= 0) {
        throw new IllegalArgumentException("Amount must be positive");
    }

    return Transfer.create(
            sourceAccount,
            destinationAccount,
            amount,
            currency
    );
}
```

Kiểm tra ở DTO giúp đưa ra lỗi đầu vào dễ hiểu. Tuy vậy, `Transfer.create()` vẫn phải kiểm tra lại những bất biến cốt lõi. Domain object không nên phụ thuộc vào giả định rằng mọi caller đều đã chạy qua đúng DTO validator.

## 5. Bảo vệ bất biến trong constructor hoặc factory của domain

Domain object nên hạn chế trạng thái có thể thay đổi tùy tiện. Một constructor hoặc factory là điểm kiểm soát tập trung để bảo đảm mọi instance được tạo ra đều hợp lệ.

Ví dụ:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

public final class Transfer {
    private final String sourceAccount;
    private final String destinationAccount;
    private final BigDecimal amount;
    private final Currency currency;

    private Transfer(String sourceAccount,
                     String destinationAccount,
                     BigDecimal amount,
                     Currency currency) {
        this.sourceAccount = sourceAccount;
        this.destinationAccount = destinationAccount;
        this.amount = amount;
        this.currency = currency;
    }

    public static Transfer create(String sourceAccount,
                                  String destinationAccount,
                                  BigDecimal amount,
                                  String currencyCode) {
        String source = requireText(sourceAccount, "sourceAccount");
        String destination = requireText(destinationAccount, "destinationAccount");

        if (source.equals(destination)) {
            throw new IllegalArgumentException(
                    "Source and destination accounts must be different");
        }

        Objects.requireNonNull(amount, "amount is required");
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        String code = requireText(currencyCode, "currencyCode");
        Currency currency = Currency.getInstance(code);

        return new Transfer(source, destination, amount, currency);
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
        return value.trim();
    }

    public String getSourceAccount() {
        return sourceAccount;
    }

    public String getDestinationAccount() {
        return destinationAccount;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public Currency getCurrency() {
        return currency;
    }
}
```

Constructor là private để caller không thể bỏ qua factory. Các field là `private final`, không có setter; sau khi tạo, object không thể bị sửa sang trạng thái âm tiền hoặc trùng tài khoản qua setter công khai.

`Currency.getInstance()` còn kiểm tra mã tiền tệ theo danh sách currency mà JDK hỗ trợ. Nếu domain chỉ cho phép một tập con như VND, USD và EUR, cần kiểm tra thêm danh sách được nghiệp vụ cho phép; mã hợp lệ theo JDK chưa chắc hợp lệ với sản phẩm.

### 5.1. Chuyển DTO thành domain object

Service điều phối hai bước:

```java
public Transfer createTransfer(CreateTransferRequest request) {
    validateRequest(request);

    return Transfer.create(
            request.getSourceAccount(),
            request.getDestinationAccount(),
            request.getAmount(),
            request.getCurrency()
    );
}
```

Ngay cả khi có một batch job, message consumer hoặc unit test gọi `Transfer.create()` trực tiếp, bất biến vẫn được bảo vệ. Đây là lợi ích quan trọng của việc đặt quy tắc trong domain object.

## 6. Khi nào nên để Jackson gọi constructor trực tiếp?

Không phải lúc nào cũng cần DTO trung gian. Với một kiểu dữ liệu nhỏ, bất biến và có cấu trúc JSON trùng khớp với cấu trúc domain, có thể cho Jackson gọi constructor được đánh dấu `@JsonCreator`.

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;
import java.util.Objects;

public final class PositiveAmount {
    private final BigDecimal value;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public PositiveAmount(
            @JsonProperty(value = "value", required = true) BigDecimal value) {
        Objects.requireNonNull(value, "value is required");
        if (value.signum() <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
        this.value = value;
    }

    @JsonProperty("value")
    public BigDecimal getValue() {
        return value;
    }
}
```

JSON:

```json
{
  "value": 125.50
}
```

Deserialize:

```java
PositiveAmount amount = mapper.readValue(json, PositiveAmount.class);
```

Jackson đọc property `value`, chuyển nó thành `BigDecimal` rồi truyền vào constructor. Constructor kiểm tra điều kiện trước khi gán field. Nếu JSON chứa `null` hoặc số âm, quá trình tạo object thất bại; Jackson thường bọc lỗi phát sinh từ creator trong một exception mapping/instantiation để bổ sung ngữ cảnh đường dẫn JSON.

`@JsonProperty(required = true)` hữu ích cho creator property nhưng không nên xem nó là cơ chế validation đầy đủ cho mọi trường hợp. Constructor vẫn cần kiểm tra null và giá trị. Đặc biệt, phải phân biệt field bị thiếu với field có giá trị null nếu hợp đồng cần hai cách xử lý khác nhau.

### 6.1. `@JsonCreator` với nhiều tham số

Với constructor nhiều tham số, khai báo tên JSON tường minh giúp Jackson ánh xạ đúng:

```java
public final class Coordinate {
    private final double latitude;
    private final double longitude;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Coordinate(
            @JsonProperty(value = "latitude", required = true) double latitude,
            @JsonProperty(value = "longitude", required = true) double longitude) {
        if (!Double.isFinite(latitude) || latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException("Invalid latitude");
        }
        if (!Double.isFinite(longitude) || longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException("Invalid longitude");
        }
        this.latitude = latitude;
        this.longitude = longitude;
    }

    public double getLatitude() {
        return latitude;
    }

    public double getLongitude() {
        return longitude;
    }
}
```

Đây là ví dụ phù hợp cho value object nhỏ: constructor có thể tự kiểm tra toàn bộ bất biến chỉ từ tham số. Với aggregate lớn cần truy vấn repository, kiểm tra quyền hoặc phối hợp nhiều dịch vụ, không nên đưa các phụ thuộc đó vào constructor để Jackson gọi. Hãy deserialize DTO rồi dùng application/domain service tạo aggregate.

## 7. Thiếu field, `null`, giá trị mặc định và primitive

Một trong những nguyên nhân làm bất biến bị phá vỡ là không phân biệt được các trạng thái đầu vào.

Với JSON sau:

```json
{}
```

và JSON:

```json
{
  "quantity": null
}
```

đều có thể dẫn tới giá trị Java null hoặc giá trị mặc định tùy kiểu đích và cấu hình. Với primitive, field bị thiếu thường giữ giá trị mặc định như `0` hoặc `false`; điều này có thể khiến ứng dụng nhầm dữ liệu không được gửi thành giá trị hợp lệ.

Nếu cần phân biệt field không có, field null và field có giá trị 0, dùng kiểu wrapper như `Integer`, `Long`, `Boolean` hoặc `BigDecimal` trong DTO:

```java
public class CreateItemRequest {
    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
```

Sau deserialize:

| JSON | Giá trị DTO thường nhận được |
|---|---|
| `{}` | `quantity == null` |
| `{"quantity": null}` | `quantity == null` |
| `{"quantity": 0}` | `quantity == 0` |
| `{"quantity": 5}` | `quantity == 5` |

Nếu cần phân biệt cả trường hợp thiếu và null, một field wrapper đơn giản chưa đủ vì cả hai cùng thành null. Có thể dùng DTO có setter theo dõi sự hiện diện, custom deserializer, `JsonNode` hoặc một kiểu biểu diễn ba trạng thái. Chỉ thêm độ phức tạp này khi hợp đồng thực sự quy định hành vi khác nhau giữa missing và explicit null.

### 7.1. Các feature giúp từ chối dữ liệu thiếu/null

Jackson 2.x cung cấp các feature để siết chặt việc tạo object qua creator:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper()
        .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
        .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
```

- `FAIL_ON_MISSING_CREATOR_PROPERTIES`: từ chối creator property không xuất hiện trong JSON.
- `FAIL_ON_NULL_CREATOR_PROPERTIES`: từ chối creator property có giá trị null.
- `FAIL_ON_NULL_FOR_PRIMITIVES`: từ chối null được gán cho primitive thay vì âm thầm dùng giá trị mặc định.

Đây là các chính sách có phạm vi ảnh hưởng trên mapper. Bật chúng toàn cục có thể làm một số payload cũ hoặc field tùy chọn không còn deserialize được. Cần đánh giá hợp đồng API trước khi áp dụng. Với chính sách chỉ dành cho một endpoint, cân nhắc mapper/reader riêng hoặc validation DTO.

## 8. Không để setter công khai phá bất biến

Một object có constructor kiểm tra nhưng vẫn mở setter có thể bị đưa về trạng thái sai sau khi được tạo:

```java
public class BankAccount {
    private BigDecimal balance;

    public BankAccount(BigDecimal balance) {
        if (balance.signum() < 0) {
            throw new IllegalArgumentException("Negative balance");
        }
        this.balance = balance;
    }

    public void setBalance(BigDecimal balance) {
        this.balance = balance; // Không kiểm tra lại bất biến
    }
}
```

Đoạn code này chỉ bảo vệ lúc tạo object. Caller vẫn có thể gọi `setBalance(new BigDecimal("-1"))`. Nếu một thuộc tính cần thay đổi trong vòng đời, hãy cung cấp hành vi domain có ý nghĩa và kiểm tra điều kiện trước khi cập nhật:

```java
public void debit(BigDecimal amount) {
    Objects.requireNonNull(amount, "amount is required");
    if (amount.signum() <= 0) {
        throw new IllegalArgumentException("Debit amount must be positive");
    }
    if (balance.compareTo(amount) < 0) {
        throw new IllegalStateException("Insufficient balance");
    }
    balance = balance.subtract(amount);
}
```

Không cung cấp setter tổng quát cho trạng thái có quy tắc. Hãy cung cấp phương thức thể hiện hành vi nghiệp vụ như `debit()`, `activate()`, `cancel()` hoặc `changeAddress()` và bảo vệ điều kiện trong chính hành vi đó.

## 9. Sử dụng record cho dữ liệu đầu vào và value object

Java record có thể biểu diễn DTO ngắn gọn. Jackson 2.12+ hỗ trợ deserialize record khi chạy trên JDK hỗ trợ record:

```java
public record CreateTransferRequest(
        String sourceAccount,
        String destinationAccount,
        BigDecimal amount,
        String currency) {
}
```

Record tự tạo field final và accessor, nhưng điều đó không tự động làm dữ liệu hợp lệ. Có thể kiểm tra ngay trong compact constructor:

```java
public record PositiveAmount(BigDecimal value) {
    public PositiveAmount {
        Objects.requireNonNull(value, "value is required");
        if (value.signum() <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
    }
}
```

Khi Jackson tạo record, nó gọi canonical constructor; các kiểm tra trong compact constructor vì thế vẫn được thực thi. Đây là một cách phù hợp cho value object nhỏ, bất biến và không cần phụ thuộc bên ngoài.

Tuy nhiên, DTO nhận request và domain value object có thể có mục đích khác nhau. Record DTO có thể chấp nhận trạng thái chưa hợp lệ để validation tổng hợp nhiều lỗi cho client; record domain nên bảo vệ bất biến ngay tại constructor. Đừng nhầm tính bất biến của field với tính hợp lệ của giá trị.

## 10. Phân biệt validation cục bộ với quy tắc cần trạng thái hệ thống

Một số điều kiện chỉ dựa vào dữ liệu của object có thể kiểm tra trong constructor/factory:

- Số tiền phải lớn hơn 0.
- Ngày kết thúc không được trước ngày bắt đầu.
- Mã quốc gia phải đúng định dạng.
- Hai đầu của một quan hệ không được trùng nhau.

Những điều kiện khác cần dữ liệu bên ngoài:

- Tài khoản có tồn tại hay đang bị khóa không.
- Người dùng hiện tại có quyền tạo giao dịch không.
- Kho hàng còn đủ số lượng không.
- Số dư hiện tại có đủ để thanh toán không.
- Một mã định danh có bị trùng trong database không.

Không nên gọi repository, HTTP client hoặc service bên ngoài từ constructor chỉ để kiểm tra những điều kiện này. Constructor cần đơn giản, xác định và không tạo side effect. Application service hoặc domain service thực hiện truy vấn và phối hợp transaction; sau đó domain method thay đổi trạng thái theo kết quả.

Ví dụ luồng tạo chuyển tiền:

```text
Controller
   |
   v
ObjectMapper / HTTP message converter
   |
   v
CreateTransferRequest
   |
   v
Input validation
   |
   v
Application service
   |-- kiểm tra quyền
   |-- tải tài khoản nguồn/đích
   |-- kiểm tra trạng thái và số dư trong transaction
   v
Transfer.create(...)
   |
   v
Domain object hợp lệ
   |
   v
Persist / publish event
```

Các kiểm tra phụ thuộc trạng thái cần được thực hiện trong ranh giới transaction phù hợp để tránh race condition. Ví dụ, kiểm tra số dư ở ngoài transaction rồi mới trừ tiền có thể khiến hai request đồng thời cùng vượt qua bước kiểm tra.

## 11. Xử lý lỗi tạo object từ JSON

Khi constructor hoặc factory được Jackson gọi trực tiếp, exception nghiệp vụ có thể được Jackson bọc trong `ValueInstantiationException` hoặc một exception mapping liên quan. Khi deserialize vào DTO rồi gọi domain factory, lỗi Jackson và lỗi domain xuất hiện ở hai giai đoạn khác nhau, giúp phân loại rõ hơn.

Một bộ xử lý request có thể phân biệt:

| Lỗi | Cách phản hồi thường phù hợp |
|---|---|
| JSON sai cú pháp | HTTP 400 với thông báo payload không hợp lệ |
| Không chuyển được kiểu dữ liệu | HTTP 400, nêu field và kiểu mong đợi nếu an toàn |
| DTO thiếu field bắt buộc hoặc sai định dạng | HTTP 400 với danh sách lỗi validation |
| Vi phạm bất biến domain | HTTP 400 hoặc 422 theo quy ước API |
| Tài khoản không tồn tại hoặc không đủ điều kiện | Lỗi nghiệp vụ theo mã lỗi được định nghĩa |
| Lỗi database hoặc hạ tầng | Lỗi server phù hợp; không biến thành lỗi dữ liệu đầu vào |

Không trả stack trace, tên class nội bộ hoặc chi tiết database cho client. Giữ nguyên nguyên nhân gốc trong log nội bộ với correlation id để có thể điều tra.

## 12. Tránh deserialization quá rộng đối với dữ liệu không tin cậy

Khi nhận JSON từ client hoặc đối tác, chỉ nên ánh xạ vào các kiểu DTO/domain được xác định trước. Không bật default typing rộng một cách tùy tiện cho dữ liệu không tin cậy. Cơ chế polymorphic deserialization có thể làm Jackson tạo kiểu con dựa trên type metadata trong JSON; nếu cấu hình allowlist không chặt, bề mặt tấn công sẽ tăng.

Nếu nghiệp vụ thực sự cần polymorphism, hãy khai báo các subtype được phép bằng `@JsonSubTypes`/`@JsonTypeInfo` hoặc dùng `PolymorphicTypeValidator` phù hợp với phiên bản. Chỉ cho phép các kiểu cần thiết và kiểm tra dữ liệu sau khi tạo object. Type metadata cũng là dữ liệu đầu vào, không phải bằng chứng rằng object đó được phép thực hiện mọi hành vi.

## 13. Ghi nhớ khi tạo đối tượng từ dữ liệu ngoài

Jackson đảm nhiệm việc đọc JSON và ánh xạ giá trị vào kiểu Java. Validation đầu vào giúp phản hồi lỗi dữ liệu rõ ràng. Constructor hoặc factory của domain phải bảo vệ bất biến để không caller nào có thể tạo object sai. Với object nhỏ, bất biến và tự kiểm tra được từ tham số, `@JsonCreator` hoặc record compact constructor có thể là lựa chọn phù hợp. Với aggregate cần phối hợp repository, quyền truy cập hoặc trạng thái hệ thống, hãy dùng DTO và application/domain service.

Một object chỉ nên được đưa vào luồng nghiệp vụ sau khi nó đã thỏa các điều kiện nội tại. Thiết kế như vậy giúp dữ liệu JSON không hợp lệ dừng ở biên hệ thống, còn phần domain có thể làm việc với trạng thái nhất quán.
