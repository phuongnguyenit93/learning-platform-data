# Đặt tên thuộc tính bằng JsonProperty

Trong một ứng dụng Java, tên thuộc tính trong lớp không phải lúc nào cũng trùng với tên khóa mà hệ thống bên ngoài sử dụng trong JSON. Java thường dùng `camelCase`, trong khi một API có thể quy định `snake_case`, tên viết tắt hoặc tên đã tồn tại từ một phiên bản giao thức cũ. Jackson cung cấp annotation `@JsonProperty` để khai báo rõ tên thuộc tính trong JSON tương ứng với một thuộc tính Java.

`@JsonProperty` giúp lớp Java giữ cách đặt tên phù hợp với ngôn ngữ và quy ước nội bộ, đồng thời vẫn tuân thủ hợp đồng dữ liệu bên ngoài. Annotation này có thể ảnh hưởng đến cả hai chiều chuyển đổi: đọc JSON thành đối tượng Java (deserialization) và ghi đối tượng Java thành JSON (serialization).

## 1. Vấn đề tên thuộc tính không trùng nhau

Giả sử một hệ thống bên ngoài gửi JSON:

```json
{
  "student_id": 23,
  "full_name": "Nguyen Van An",
  "is_active": true
}
```

Trong Java, nhóm phát triển muốn sử dụng tên thuộc tính theo quy ước `camelCase`:

```java
public class Student {
    private long studentId;
    private String fullName;
    private boolean active;

    // Constructor, getter và setter.
}
```

Nếu Jackson dùng tên thuộc tính Java theo quy tắc mặc định, tên JSON dự kiến sẽ là `studentId`, `fullName` và `active`. Nhưng hợp đồng của hệ thống bên ngoài yêu cầu `student_id`, `full_name` và `is_active`.

Đây là lúc `@JsonProperty` hữu ích. Annotation chỉ định tên thuộc tính mà Jackson phải dùng khi làm việc với JSON:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class Student {
    @JsonProperty("student_id")
    private long studentId;

    @JsonProperty("full_name")
    private String fullName;

    @JsonProperty("is_active")
    private boolean active;

    public Student() {
    }

    public long getStudentId() {
        return studentId;
    }

    public void setStudentId(long studentId) {
        this.studentId = studentId;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Khi serialize, Jackson ghi các khóa `student_id`, `full_name` và `is_active`. Khi deserialize, Jackson tìm đúng các khóa đó và gán giá trị cho các thuộc tính Java tương ứng.

## 2. Cú pháp và vị trí đặt annotation

`@JsonProperty` thuộc package `com.fasterxml.jackson.annotation`:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
```

Cách dùng cơ bản:

```java
@JsonProperty("json_name")
private String javaProperty;
```

Annotation có thể được đặt trên các thành phần mà Jackson nhận diện như một property:

- Field của lớp.
- Getter.
- Setter.
- Tham số constructor được dùng để tạo đối tượng.
- Thành phần của record trong các phiên bản Jackson hỗ trợ record.

### 2.1. Đặt trên field

Đặt annotation trên field là cách trực tiếp và dễ đọc khi muốn khai báo tên JSON tại thuộc tính:

```java
public class Product {
    @JsonProperty("product_code")
    private String code;

    public Product() {
    }

    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }
}
```

Jackson có thể kết hợp thông tin field với getter/setter để nhận diện một property logic. Annotation trên field cũng có thể khiến field được xem xét như một thuộc tính cần ánh xạ dù field không public, tùy cơ chế introspection và cấu hình visibility. Không nên mặc định mọi field private đều được tự động truy cập trong mọi cấu hình nếu không có annotation hoặc quy tắc visibility phù hợp.

### 2.2. Đặt trên getter

Annotation trên getter chỉ định tên JSON cho property được ghi ra và cũng có thể tham gia vào metadata của property khi Jackson kết hợp các thành phần cùng tên:

```java
public class Product {
    private String code;

    @JsonProperty("product_code")
    public String getCode() {
        return code;
    }

    public void setCode(String code) {
        this.code = code;
    }
}
```

Cách này có thể phù hợp khi muốn thể hiện tên JSON ngay tại accessor công khai. Tuy nhiên, với một property có field, getter và setter, nên đặt annotation nhất quán ở một vị trí rõ ràng thay vì khai báo những tên khác nhau trên từng thành phần.

### 2.3. Đặt trên setter

Annotation trên setter có thể chỉ định tên JSON được dùng khi Jackson gán giá trị vào đối tượng:

```java
public class Product {
    private String code;

    public String getCode() {
        return code;
    }

    @JsonProperty("product_code")
    public void setCode(String code) {
        this.code = code;
    }
}
```

Trong các lớp JavaBean thông thường, Jackson thường kết hợp field, getter và setter thành một property. Việc đặt annotation ở setter thường có ích khi tập trung cấu hình chiều đọc, nhưng cần hiểu cách Jackson gộp metadata của property. Với DTO mới, đặt annotation trên field hoặc khai báo rõ ràng ở constructor/record component thường giúp người đọc nhanh chóng nhận ra hợp đồng JSON.

### 2.4. Đặt trên tham số constructor

Nếu lớp không có constructor không tham số hoặc muốn tạo đối tượng thông qua constructor, có thể kết hợp `@JsonCreator` và `@JsonProperty`:

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class Customer {
    private final long id;
    private final String name;

    @JsonCreator
    public Customer(
            @JsonProperty("customer_id") long id,
            @JsonProperty("customer_name") String name) {
        this.id = id;
        this.name = name;
    }

    public long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

Khi đọc JSON, Jackson dùng tên được khai báo trên tham số để lấy giá trị truyền vào constructor. Cách này phù hợp với lớp bất biến có các trường `final`. `@JsonCreator` giúp xác định constructor hoặc factory method dùng để tạo đối tượng; các tham số được đặt tên rõ ràng bằng `@JsonProperty`.

### 2.5. Đặt trên record component

Record có thể khai báo tên JSON ngay tại component:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.UUID;

public record UserResponse(
    @JsonProperty("user_id") UUID userId,
    @JsonProperty("display_name") String displayName,
    @JsonProperty("is_active") boolean active
) {
}
```

Jackson hỗ trợ record trong các phiên bản phù hợp (record được hỗ trợ trong Jackson 2.12 trở lên). Cần dùng phiên bản thư viện tương thích với phiên bản Java và framework của dự án. Record component giúp DTO bất biến và thể hiện tên thuộc tính JSON ngay tại khai báo dữ liệu.

## 3. Dùng JsonProperty trong cả hai chiều chuyển đổi

Một điểm quan trọng là `@JsonProperty` không chỉ đổi tên khi ghi JSON. Cùng tên được dùng để nhận diện thuộc tính khi đọc JSON.

Ví dụ đầy đủ:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;

public class Account {
    @JsonProperty("account_no")
    private String accountNumber;

    @JsonProperty("owner_name")
    private String ownerName;

    public Account() {
    }

    public Account(String accountNumber, String ownerName) {
        this.accountNumber = accountNumber;
        this.ownerName = ownerName;
    }

    public String getAccountNumber() {
        return accountNumber;
    }

    public String getOwnerName() {
        return ownerName;
    }
}

public class JsonPropertyExample {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        String json = """
            {
              "account_no": "AC-1024",
              "owner_name": "Lan"
            }
            """;

        Account account = mapper.readValue(json, Account.class);
        System.out.println(account.getAccountNumber());

        String output = mapper.writeValueAsString(account);
        System.out.println(output);
    }
}
```

Kết quả JSON được ghi ra có các tên `account_no` và `owner_name`, không phải `accountNumber` và `ownerName`.

Luồng chuyển đổi:

```text
JSON: "account_no"
       |
       | @JsonProperty("account_no")
       v
Java: accountNumber
       |
       | @JsonProperty("account_no")
       v
JSON: "account_no"
```

Tên thuộc tính Java có thể thay đổi trong nội bộ mà không nhất thiết làm thay đổi hợp đồng JSON, miễn là annotation và các phần liên quan được cập nhật đúng.

## 4. Các thuộc tính của @JsonProperty

Ngoài tên JSON, `@JsonProperty` còn có một số thuộc tính để điều khiển metadata và hướng truy cập. Cú pháp tổng quát:

```java
@JsonProperty(
    value = "json_name",
    required = false,
    index = -1,
    defaultValue = "",
    access = JsonProperty.Access.AUTO
)
private String javaProperty;
```

Các tham số thường gặp:

| Thuộc tính | Ý nghĩa | Lưu ý |
|---|---|---|
| `value` | Tên property trong JSON | Đây là tham số được dùng nhiều nhất; có thể viết rút gọn `@JsonProperty("name")` |
| `required` | Đánh dấu property là bắt buộc trong một số ngữ cảnh creator | Đặc biệt có ý nghĩa với tham số constructor/factory; không thay thế validation nghiệp vụ |
| `index` | Chỉ số thứ tự property trong các định dạng hỗ trợ thứ tự | JSON object về mặt ngữ nghĩa không nên phụ thuộc thứ tự khóa |
| `defaultValue` | Metadata mô tả giá trị mặc định | Không nên giả định Jackson Databind tự động gán giá trị này cho mọi trường hợp thiếu dữ liệu |
| `access` | Quy định hướng đọc/ghi của property | Dùng `READ_ONLY`, `WRITE_ONLY`, `READ_WRITE` hoặc `AUTO` |
| `namespace` | Namespace của property trong các định dạng hỗ trợ namespace | Thường hữu ích hơn với định dạng như XML; JSON không có namespace property theo cách tương tự |

### 4.1. Thuộc tính value

`value` là tên property mà Jackson sử dụng trong JSON:

```java
@JsonProperty("order_number")
private String orderNumber;
```

Có thể viết đầy đủ:

```java
@JsonProperty(value = "order_number")
private String orderNumber;
```

Hai cách tương đương. Nếu không truyền giá trị, annotation không tạo ra một tên tùy chỉnh cụ thể và Jackson dựa vào quy tắc nhận diện property còn lại.

### 4.2. Thuộc tính access

`access` xác định property được dùng theo hướng nào:

| Giá trị | Khi đọc JSON thành Java | Khi ghi Java thành JSON |
|---|---|---|
| `AUTO` | Jackson tự xác định theo accessor/visibility | Jackson tự xác định theo accessor/visibility |
| `READ_ONLY` | Không nhận giá trị từ JSON theo property này | Có thể đưa giá trị ra JSON |
| `WRITE_ONLY` | Có thể nhận giá trị từ JSON | Không đưa giá trị ra JSON |
| `READ_WRITE` | Nhận giá trị từ JSON | Ghi giá trị ra JSON |

Tên `READ_ONLY` và `WRITE_ONLY` được hiểu theo góc nhìn của property trong JSON: `READ_ONLY` nghĩa là client có thể đọc giá trị được trả về nhưng không ghi giá trị đó qua JSON; `WRITE_ONLY` nghĩa là client có thể gửi giá trị vào nhưng không nhận lại giá trị đó trong JSON response.

Ví dụ, một request có thể cần nhận mật khẩu để tạo tài khoản nhưng không được serialize mật khẩu ra response:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class RegistrationRequest {
    private String username;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }
}
```

Khi deserialize, Jackson có thể gán `password` từ JSON. Khi serialize object, thuộc tính này không được ghi ra JSON. Tuy nhiên, `WRITE_ONLY` chỉ điều khiển cách Jackson ánh xạ; nó không phải cơ chế phân quyền hoặc bảo mật tổng thể. Không trả password trong response vẫn cần thiết kế DTO và luồng xử lý phù hợp, không log mật khẩu, không lưu mật khẩu dạng rõ và bảo vệ endpoint bằng cơ chế xác thực/ủy quyền.

Ví dụ `READ_ONLY` cho mã do hệ thống tạo:

```java
public class OrderResponse {
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String orderId;

    private String status;

    // Getter và setter.
}
```

`orderId` có thể xuất hiện trong JSON trả về nhưng không được lấy từ JSON đầu vào thông qua property đó. Với request và response có hợp đồng khác nhau, DTO riêng thường còn rõ ràng hơn việc dùng chung một lớp và dựa hoàn toàn vào access mode.

### 4.3. Thuộc tính required

`required` đánh dấu một property là bắt buộc trong các ngữ cảnh mà Jackson hỗ trợ, đặc biệt với property được truyền vào creator như constructor hoặc factory method:

```java
public class PaymentRequest {
    private final String reference;

    @JsonCreator
    public PaymentRequest(
            @JsonProperty(value = "reference", required = true)
            String reference) {
        this.reference = reference;
    }

    public String getReference() {
        return reference;
    }
}
```

Không nên xem `required = true` là giải pháp validation đầy đủ cho mọi field/setter. Hành vi kiểm tra phụ thuộc loại property, creator và phiên bản/cấu hình Jackson. Với dữ liệu nghiệp vụ, vẫn cần kiểm tra bắt buộc ở lớp validation hoặc use case, ví dụ `@NotBlank`, `@NotNull` hoặc logic tương ứng. Sự hiện diện của khóa trong JSON và tính hợp lệ của giá trị là hai yêu cầu khác nhau.

### 4.4. Thuộc tính index

`index` cung cấp thứ tự property trong các định dạng hoặc cơ chế ghi có hỗ trợ chỉ số:

```java
public class Coordinates {
    @JsonProperty(value = "latitude", index = 1)
    private double latitude;

    @JsonProperty(value = "longitude", index = 2)
    private double longitude;
}
```

Không nên thiết kế API JSON yêu cầu client phụ thuộc thứ tự khóa trong object. Theo ngữ nghĩa JSON, object là tập hợp các cặp tên/giá trị; thứ tự thành viên không nên mang ý nghĩa nghiệp vụ. Nếu cần định dạng đầu ra có thứ tự xác định để phục vụ yêu cầu tương thích hoặc so sánh văn bản, có thể dùng cấu hình thứ tự property phù hợp và kiểm thử riêng.

### 4.5. Thuộc tính defaultValue

`defaultValue` mô tả metadata về giá trị mặc định:

```java
@JsonProperty(value = "locale", defaultValue = "vi-VN")
private String locale;
```

Không nên mặc định rằng Jackson Databind sẽ tự gán `"vi-VN"` vào field mỗi khi khóa `locale` bị thiếu. Thuộc tính này chủ yếu cung cấp thông tin metadata cho các công cụ hoặc tầng tích hợp sử dụng. Nếu ứng dụng cần giá trị mặc định thực sự, hãy triển khai rõ ràng trong constructor, factory, setter, builder hoặc bước chuẩn hóa request.

Ví dụ đặt default trong constructor:

```java
public class SearchRequest {
    private String locale;

    public SearchRequest() {
        this.locale = "vi-VN";
    }

    public String getLocale() {
        return locale;
    }

    public void setLocale(String locale) {
        this.locale = locale;
    }
}
```

Nếu JSON gửi `locale` tường minh là `null`, setter có thể ghi đè giá trị mặc định bằng `null`. Nếu muốn xử lý cả trường hợp này, cần định nghĩa chính sách riêng thay vì chỉ dựa vào constructor.

## 5. Phân biệt JsonProperty và JsonAlias

`@JsonProperty` xác định tên property chuẩn mà Jackson sử dụng. Trong khi đó, `@JsonAlias` khai báo thêm những tên thay thế được chấp nhận khi đọc JSON.

Ví dụ một API trước đây gửi `fullName`, sau đó chuẩn hóa thành `full_name`:

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class PersonRequest {
    @JsonProperty("full_name")
    @JsonAlias({"fullName", "name"})
    private String fullName;

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
```

Kết quả:

- Khi đọc `{"full_name":"Lan"}`, Jackson gán vào `fullName`.
- Khi đọc `{"fullName":"Lan"}`, Jackson cũng nhận diện tên alias.
- Khi đọc `{"name":"Lan"}`, Jackson cũng có thể nhận diện alias thứ hai.
- Khi ghi đối tượng Java thành JSON, tên chuẩn `full_name` được sử dụng.

`@JsonAlias` chủ yếu có tác dụng ở chiều deserialization. Nó không làm Jackson ghi ra tất cả tên thay thế. Đây là cách hữu ích để duy trì tương thích khi API đổi tên trường mà vẫn cần tiếp nhận payload cũ.

Nếu một JSON gửi đồng thời nhiều alias cho cùng một property, cần tránh dựa vào thứ tự để quyết định giá trị cuối cùng. Hợp đồng dữ liệu nên quy định một tên chuẩn và client nên gửi đúng một biến thể. Nếu cần xử lý xung đột có chủ đích, hãy xây dựng logic validation hoặc deserializer chuyên biệt.

## 6. JsonProperty và naming strategy

Jackson có thể áp dụng quy tắc đặt tên chung cho một lớp hoặc một mapper, ví dụ chuyển tên Java từ `camelCase` sang `snake_case`. `@JsonProperty` hữu ích khi một property có tên đặc biệt hoặc cần giữ tên hợp đồng cố định.

Ví dụ dùng naming strategy cho toàn bộ lớp:

```java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class CustomerProfile {
    private String firstName;
    private String lastName;
    private String phoneNumber;

    // Constructor, getter và setter.
}
```

Với strategy trên, các thuộc tính được chuyển theo quy tắc snake case, ví dụ `firstName` thành `first_name`.

Nếu một trường cần tên đặc biệt, có thể khai báo rõ:

```java
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class CustomerProfile {
    private String firstName;

    @JsonProperty("contact")
    private String phoneNumber;
}
```

Ở đây, `firstName` tuân theo naming strategy và `phoneNumber` dùng tên tường minh `contact`. Tên được khai báo rõ bằng `@JsonProperty` được xem là tên property được chỉ định, không nên kỳ vọng naming strategy tiếp tục biến đổi nó như tên suy ra tự động.

Có thể áp dụng naming strategy toàn mapper nếu toàn bộ hợp đồng do mapper xử lý cùng theo một quy ước:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.setPropertyNamingStrategy(
    PropertyNamingStrategies.SNAKE_CASE
);
```

Hãy cân nhắc phạm vi trước khi đặt strategy toàn cục. Nếu một ứng dụng tích hợp nhiều đối tác với quy ước khác nhau, nên dùng mapper hoặc DTO phù hợp cho từng hợp đồng. Tránh cấu hình mapper chung theo từng request.

## 7. JsonProperty với kiểu bất biến và builder

Với lớp bất biến, các trường thường là `final` và không có setter. Jackson cần biết cách cung cấp giá trị khi tạo đối tượng.

### 7.1. Constructor được đánh dấu JsonCreator

```java
public final class MoneyAmount {
    private final BigDecimal amount;
    private final String currency;

    @JsonCreator
    public MoneyAmount(
            @JsonProperty("amount") BigDecimal amount,
            @JsonProperty("currency") String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
```

Tên tham số constructor được khai báo trực tiếp, vì vậy Jackson không phải đoán tên tham số từ bytecode hoặc dựa vào module parameter names. `@JsonCreator` cho biết constructor này là điểm tạo object khi đọc JSON.

### 7.2. Record

Với DTO đơn giản, record thường ngắn gọn hơn:

```java
public record ProductResponse(
    @JsonProperty("product_id") long id,
    @JsonProperty("display_name") String name,
    @JsonProperty("unit_price") BigDecimal unitPrice
) {
}
```

Record phù hợp khi dữ liệu chủ yếu là giá trị và không cần setter. Hãy bảo đảm phiên bản Jackson hỗ trợ record và cấu hình module phù hợp với kiểu thành phần, ví dụ Java Time nếu record chứa `Instant` hoặc `LocalDate`.

### 7.3. Builder

Nếu lớp dùng builder, Jackson có thể tích hợp builder thông qua `@JsonDeserialize` và `@JsonPOJOBuilder`:

```java
import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonPOJOBuilder;

@JsonDeserialize(builder = ApiSettings.Builder.class)
public class ApiSettings {
    private final String endpoint;
    private final int timeoutSeconds;

    private ApiSettings(Builder builder) {
        this.endpoint = builder.endpoint;
        this.timeoutSeconds = builder.timeoutSeconds;
    }

    public String getEndpoint() {
        return endpoint;
    }

    public int getTimeoutSeconds() {
        return timeoutSeconds;
    }

    @JsonPOJOBuilder(withPrefix = "with")
    public static class Builder {
        private String endpoint;
        private int timeoutSeconds;

        @JsonProperty("service_url")
        public Builder withEndpoint(String endpoint) {
            this.endpoint = endpoint;
            return this;
        }

        @JsonProperty("timeout_seconds")
        public Builder withTimeoutSeconds(int timeoutSeconds) {
            this.timeoutSeconds = timeoutSeconds;
            return this;
        }

        public ApiSettings build() {
            return new ApiSettings(this);
        }
    }
}
```

Trong builder, `@JsonProperty` đặt trên phương thức nhận giá trị để xác định tên JSON. `withPrefix = "with"` thông báo cho Jackson cách nhận diện các phương thức builder. Nếu builder dùng `setX`, `withX` hoặc tên khác, cần cấu hình prefix phù hợp với API builder thực tế.

## 8. Đặt tên property có ảnh hưởng đến tương thích API

Tên JSON là một phần hợp đồng giữa producer và consumer. Thay đổi tên khóa có thể làm client cũ không đọc được dữ liệu hoặc gửi trường mà server mới không nhận diện.

Ví dụ API cũ:

```json
{
  "customerName": "Lan"
}
```

API mới muốn chuẩn hóa:

```json
{
  "customer_name": "Lan"
}
```

Có thể duy trì khả năng đọc cả hai tên trong giai đoạn chuyển tiếp:

```java
public class CustomerRequest {
    @JsonProperty("customer_name")
    @JsonAlias("customerName")
    private String customerName;

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }
}
```

Server đọc được tên mới và tên cũ, nhưng khi serialize sẽ phát ra tên chuẩn `customer_name`. Điều này giúp client chuyển đổi dần. Alias không thay thế kế hoạch versioning: vẫn cần thống kê client còn gửi tên cũ, thông báo thời điểm ngừng hỗ trợ và loại bỏ alias khi hợp đồng cho phép.

Không nên đổi `@JsonProperty` chỉ để làm code Java đẹp hơn nếu tên JSON là hợp đồng đã công bố. Có thể đổi tên field Java nhưng giữ tên JSON bằng annotation để tránh thay đổi API ngoài ý muốn.

## 9. Tránh xung đột khi đặt annotation

Một property JavaBean có thể được Jackson tổng hợp từ field, getter và setter. Nếu mỗi thành phần khai báo tên hoặc access khác nhau, kết quả có thể khó dự đoán và phụ thuộc vào cấu hình visibility hoặc cách Jackson hợp nhất metadata.

Ví dụ nên tránh:

```java
public class User {
    @JsonProperty("user_name")
    private String name;

    @JsonProperty("display_name")
    public String getName() {
        return name;
    }

    @JsonProperty("login_name")
    public void setName(String name) {
        this.name = name;
    }
}
```

Ở đây cùng một property có ba tên được khai báo. Không nên dựa vào cách Jackson chọn hoặc hợp nhất các khai báo để xây dựng hợp đồng API.

Hãy chọn một tên chuẩn và đặt annotation ở vị trí nhất quán:

```java
public class User {
    @JsonProperty("user_name")
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Nếu một property thật sự cần cách đọc và ghi khác nhau, hãy diễn tả rõ bằng `access`, `@JsonAlias`, DTO riêng hoặc serializer/deserializer chuyên biệt. Không dùng nhiều tên annotation xung đột như một cách ngầm tạo hai hợp đồng.

## 10. JsonProperty không phải cơ chế bảo mật

`@JsonProperty(access = WRITE_ONLY)` có thể ngăn Jackson ghi một thuộc tính ra JSON, nhưng không thay thế kiểm soát quyền và thiết kế dữ liệu an toàn. Tương tự, `@JsonIgnore` chỉ tác động đến quá trình ánh xạ theo cấu hình; nó không tự bảo vệ dữ liệu trong log, database, debugger hoặc một đường trả dữ liệu khác.

Với dữ liệu nhạy cảm:

- Dùng request DTO và response DTO riêng nếu hai chiều có trường khác nhau.
- Không serialize trực tiếp entity chứa mật khẩu, token, secret hoặc thông tin nội bộ.
- Không log payload nhạy cảm; che dữ liệu theo chính sách logging.
- Thực hiện xác thực và phân quyền ở tầng phù hợp.
- Kiểm thử rõ ràng JSON response không chứa các trường không được phép.

Ví dụ request và response riêng:

```java
public record CreateUserRequest(
    String username,
    String password
) {
}

public record UserResponse(
    long id,
    String username
) {
}
```

Request chứa mật khẩu để tạo tài khoản; response không có trường đó. Cách thiết kế này làm hợp đồng đầu ra rõ ràng ngay từ kiểu dữ liệu.

## 11. Kiểm thử JsonProperty

Nên kiểm thử cả chiều đọc và chiều ghi. Chỉ kiểm tra một chiều có thể bỏ sót việc server nhận đúng nhưng trả sai tên, hoặc ngược lại.

Ví dụ kiểm thử với JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class StudentJsonPropertyTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void deserializesUsingExternalPropertyNames() throws Exception {
        String json = """
            {
              "student_id": 23,
              "full_name": "Lan",
              "is_active": true
            }
            """;

        Student student = mapper.readValue(json, Student.class);

        assertEquals(23L, student.getStudentId());
        assertEquals("Lan", student.getFullName());
        assertTrue(student.isActive());
    }

    @Test
    void serializesUsingExternalPropertyNames() throws Exception {
        Student student = new Student();
        student.setStudentId(23L);
        student.setFullName("Lan");
        student.setActive(true);

        JsonNode json = mapper.readTree(mapper.writeValueAsString(student));

        assertEquals(23L, json.path("student_id").asLong());
        assertEquals("Lan", json.path("full_name").asText());
        assertTrue(json.path("is_active").asBoolean());
        assertTrue(json.get("studentId") == null);
    }
}
```

Hai test xác nhận hợp đồng ở cả hai chiều. Có thể bổ sung test cho alias cũ, access mode, trường thiếu/null và naming strategy nếu các trường hợp đó thuộc hợp đồng của API.

Khi so sánh JSON, ưu tiên parse thành `JsonNode` rồi so sánh cấu trúc nếu thứ tự khóa không phải yêu cầu. So sánh chuỗi nguyên văn có thể khiến test thất bại chỉ vì khoảng trắng hoặc thứ tự property dù nội dung JSON tương đương.

## 12. Các lỗi thường gặp

### Khóa JSON vẫn dùng tên cũ

Nguyên nhân thường là annotation được đặt sai property, một accessor khác được Jackson nhận diện, hoặc cấu hình visibility/naming strategy ảnh hưởng đến cách hợp nhất property. Hãy kiểm tra JSON thực tế được ghi ra và thống nhất vị trí annotation.

### Jackson không nhận diện tên alias

`@JsonAlias` chủ yếu có hiệu lực khi đọc JSON. Nếu muốn tên đầu ra khác, phải khai báo tên chuẩn bằng `@JsonProperty`.

### Dùng required nhưng trường vẫn chưa được kiểm tra như mong đợi

`required` có ý nghĩa đặc biệt với creator property. Đối với bean/setter thông thường, không nên dựa vào nó như validation bắt buộc tổng quát. Hãy kiểm tra ràng buộc đầu vào ở tầng validation hoặc use case.

### Dùng defaultValue nhưng field vẫn null

`defaultValue` là metadata, không phải cơ chế gán mặc định tự động cho mọi kiểu property. Hãy thiết lập default bằng constructor, builder hoặc bước chuẩn hóa dữ liệu.

### Đặt access sai hướng

Nhớ đọc/ghi theo góc nhìn JSON: `READ_ONLY` là client chỉ đọc giá trị trong JSON response; `WRITE_ONLY` là client gửi giá trị vào JSON request nhưng không nhận lại giá trị đó khi serialize.

### Annotation ở nhiều nơi gây kết quả khó đoán

Field, getter và setter có thể được hợp nhất thành một property. Tránh khai báo tên khác nhau trên từng thành phần; chọn một tên chuẩn và vị trí khai báo nhất quán.

## 13. Quy trình chọn tên JSON cho một thuộc tính

Khi thiết kế DTO hoặc tích hợp một API, có thể thực hiện theo các bước:

1. Đọc hợp đồng JSON và xác định tên khóa chính xác, kể cả chữ hoa/chữ thường, dấu gạch dưới và viết tắt.
2. Chọn tên thuộc tính Java theo quy ước nội bộ, thường là `camelCase`.
3. Đặt `@JsonProperty` để liên kết tên JSON chuẩn với property Java.
4. Nếu cần tiếp nhận tên cũ, thêm `@JsonAlias` cho chiều đọc và giữ `@JsonProperty` làm tên đầu ra chuẩn.
5. Nếu cần giới hạn chiều đọc/ghi, cân nhắc `access`; với request/response khác nhau, ưu tiên DTO riêng khi giúp hợp đồng rõ hơn.
6. Nếu lớp bất biến, khai báo creator/constructor hoặc dùng record và đặt tên trên tham số/component.
7. Kiểm tra tương tác với naming strategy, visibility và accessor của lớp.
8. Viết test cho JSON đầu vào và đầu ra thực tế; xác nhận không có khóa ngoài ý muốn.
9. Khi đổi tên khóa đã công bố, lập kế hoạch tương thích và loại bỏ alias theo vòng đời API.

## 14. Bảng ghi nhớ

| Nhu cầu | Cách dùng phù hợp |
|---|---|
| Đổi tên JSON so với field Java | `@JsonProperty("json_name")` |
| Nhận cả tên cũ và tên mới khi deserialize | `@JsonProperty` kết hợp `@JsonAlias` |
| Chỉ cho phép đọc từ JSON response, không nhận đầu vào | `@JsonProperty(access = READ_ONLY)` |
| Chỉ nhận đầu vào, không ghi ra JSON | `@JsonProperty(access = WRITE_ONLY)` |
| Tạo object bất biến qua constructor | `@JsonCreator` và `@JsonProperty` trên tham số |
| Đặt tên cho record component | `@JsonProperty` trên component |
| Chuyển đổi tên theo quy ước toàn lớp | `@JsonNaming` |
| Ghi metadata bắt buộc cho creator property | `required = true`, đồng thời vẫn validate nghiệp vụ |
| Mô tả metadata giá trị mặc định | `defaultValue`, nhưng tự triển khai logic gán default |
| Kiểm soát thứ tự ở định dạng hỗ trợ | `index`, không dùng thứ tự khóa JSON làm quy tắc nghiệp vụ |

`@JsonProperty` là công cụ quan trọng để giữ ổn định hợp đồng JSON trong khi mô hình Java vẫn tuân theo quy ước đặt tên nội bộ. Hãy xác định một tên JSON chuẩn, khai báo nhất quán, dùng alias khi cần tương thích và kiểm thử cả chiều đọc lẫn chiều ghi. Khi hợp đồng request và response khác nhau, DTO riêng thường giúp kiểm soát dữ liệu rõ ràng hơn so với việc dựa hoàn toàn vào annotation trên một lớp dùng chung.
