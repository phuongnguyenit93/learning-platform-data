# Áp dụng chiến lược đặt tên cho lớp và toàn mapper

Trong Java, tên thuộc tính thường được viết theo `lowerCamelCase`, ví dụ `firstName`, `createdAt` hoặc `accountId`. JSON API lại có thể quy định tên theo `snake_case`, `kebab-case`, `PascalCase` hoặc một quy ước riêng. Nếu phải đổi tên thủ công từng field, model Java sẽ bị gắn chặt với định dạng của một API.

Jackson cung cấp **Property Naming Strategy** để chuyển đổi tên property Java thành tên property JSON theo một quy tắc thống nhất. Có thể áp dụng chiến lược cho toàn bộ `ObjectMapper`, hoặc chỉ cho một lớp bằng annotation `@JsonNaming`. Cách này cũng được dùng khi đọc JSON: Jackson chuyển tên property JSON về đúng property Java theo chiến lược tương ứng.

Các ví dụ trong bài dùng Jackson 2.x hiện đại, với API `PropertyNamingStrategies` (có từ Jackson 2.12). Nếu dự án dùng phiên bản cũ hơn, cần kiểm tra API tương ứng trong Javadoc của đúng version.

## 1. Vì sao cần chiến lược đặt tên?

Giả sử model Java có các thuộc tính:

```java
public class UserProfile {
    private String firstName;
    private String lastName;
    private String emailAddress;

    // constructors, getters và setters
}
```

Theo mặc định, Jackson thường ghi các property với tên giữ nguyên kiểu camel case:

```json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "emailAddress": "an@example.com"
}
```

Một API bên ngoài có thể yêu cầu:

```json
{
  "first_name": "An",
  "last_name": "Nguyen",
  "email_address": "an@example.com"
}
```

Model Java vẫn có thể giữ `firstName`, `lastName`, `emailAddress`. Naming strategy chịu trách nhiệm ánh xạ tên giữa hai quy ước. Nhờ vậy, tên trong source code không cần thay đổi chỉ vì một hệ thống bên ngoài chọn quy ước JSON khác.

## 2. Các chiến lược đặt tên có sẵn

Jackson 2.x cung cấp lớp `PropertyNamingStrategies` với một số chiến lược phổ biến:

| Chiến lược | Ví dụ từ `firstName` | Khi thường gặp |
|---|---|---|
| `LOWER_CAMEL_CASE` | `firstName` | Quy ước Java phổ biến; cũng là mặc định |
| `UPPER_CAMEL_CASE` | `FirstName` | Tên property bắt đầu bằng chữ hoa |
| `SNAKE_CASE` | `first_name` | REST API hoặc JSON dùng dấu gạch dưới |
| `UPPER_SNAKE_CASE` | `FIRST_NAME` | Hệ thống dùng tên hằng/field viết hoa có dấu gạch dưới |
| `KEBAB_CASE` | `first-name` | JSON hoặc cấu hình dùng dấu gạch ngang |
| `LOWER_CASE` | `firstname` | Quy ước chuyển toàn bộ tên về chữ thường, không chèn dấu phân cách |
| `LOWER_DOT_CASE` | `first.name` | Hệ thống dùng dấu chấm làm dấu phân cách |

Ví dụ chuyển một số tên:

| Tên Java | `SNAKE_CASE` | `KEBAB_CASE` | `UPPER_SNAKE_CASE` |
|---|---|---|---|
| `firstName` | `first_name` | `first-name` | `FIRST_NAME` |
| `createdAt` | `created_at` | `created-at` | `CREATED_AT` |
| `accountId` | `account_id` | `account-id` | `ACCOUNT_ID` |

Các chiến lược xử lý ranh giới chữ hoa và acronym theo quy tắc của Jackson. Với tên đặc biệt như `URLValue`, `userID` hoặc tên có nhiều chữ viết tắt liên tiếp, hãy kiểm tra kết quả thực tế bằng đúng version Jackson của dự án thay vì tự giả định thuật toán chuyển đổi.

Không phải hệ thống JSON nào cũng chấp nhận mọi kiểu tên. Hãy chọn quy ước dựa trên hợp đồng API hoặc schema của hệ thống tích hợp.

## 3. Áp dụng chiến lược cho toàn bộ `ObjectMapper`

Khi phần lớn model trong một ứng dụng dùng chung một quy ước, cấu hình naming strategy ở cấp mapper là cách đơn giản nhất.

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;

ObjectMapper mapper = new ObjectMapper();
mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
```

Từ thời điểm này, các POJO được mapper xử lý sẽ dùng `snake_case` cho những property không có tên tường minh.

Ví dụ model:

```java
public class Customer {
    private String customerName;
    private String phoneNumber;
    private boolean active;

    public Customer() {
    }

    public Customer(String customerName, String phoneNumber, boolean active) {
        this.customerName = customerName;
        this.phoneNumber = phoneNumber;
        this.active = active;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public String getPhoneNumber() {
        return phoneNumber;
    }

    public void setPhoneNumber(String phoneNumber) {
        this.phoneNumber = phoneNumber;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
```

Ghi object:

```java
Customer customer = new Customer("An Nguyen", "0900000000", true);

String json = mapper.writeValueAsString(customer);
```

JSON có các tên property tương ứng:

```json
{
  "customer_name": "An Nguyen",
  "phone_number": "0900000000",
  "active": true
}
```

### 3.1. Naming strategy cũng được dùng khi đọc JSON

Chiến lược đặt tên không chỉ áp dụng khi serialize. Khi deserialize, Jackson dùng cùng quy tắc để ánh xạ tên JSON vào property Java:

```java
String json = """
        {
          "customer_name": "An Nguyen",
          "phone_number": "0900000000",
          "active": true
        }
        """;

Customer restored = mapper.readValue(json, Customer.class);
```

Jackson ánh xạ `customer_name` vào `customerName`, `phone_number` vào `phoneNumber` và `active` vào property tương ứng. Do đó, cùng một mapper có thể dùng để đọc và ghi theo hợp đồng `snake_case`.

### 3.2. Cấu hình trước khi chia sẻ mapper

`ObjectMapper` có thể được tái sử dụng giữa nhiều request sau khi cấu hình hoàn tất. Naming strategy là một phần cấu hình serialization/deserialization, vì vậy hãy thiết lập ngay khi khởi tạo:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

// Sau khi cấu hình hoàn tất mới đưa mapper vào sử dụng chung.
```

Không nên thay đổi naming strategy liên tục trên một mapper đang được nhiều luồng sử dụng. Nếu hai nhóm API cần quy ước tên khác nhau, cân nhắc tạo hai mapper riêng đã cấu hình sẵn hoặc áp dụng `@JsonNaming` trên từng lớp.

## 4. Áp dụng chiến lược cho riêng một lớp bằng `@JsonNaming`

Khi phần lớn model dùng camel case nhưng một DTO phải tuân theo hợp đồng `snake_case`, không cần đổi cấu hình toàn mapper. Có thể gắn `@JsonNaming` lên lớp:

```java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class PaymentRequest {
    private String transactionId;
    private String paymentMethod;
    private Long accountId;

    // constructors, getters và setters
}
```

Khi serialize, tên property được chuyển thành:

```json
{
  "transaction_id": "TX-100",
  "payment_method": "CARD",
  "account_id": 2001
}
```

Khi deserialize, Jackson cũng nhận các tên `transaction_id`, `payment_method` và `account_id` theo chiến lược được khai báo trên lớp.

`@JsonNaming` yêu cầu một class chiến lược, chẳng hạn `PropertyNamingStrategies.SnakeCaseStrategy.class`. Cần phân biệt class này với hằng instance `PropertyNamingStrategies.SNAKE_CASE` dùng khi cấu hình mapper.

### 4.1. Một mapper, nhiều quy ước theo từng DTO

Có thể dùng một mapper mặc định cho nhiều lớp, trong đó chỉ lớp có annotation mới dùng quy ước riêng:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

ObjectMapper mapper = new ObjectMapper();

public class InternalUser {
    private String firstName;
    // getters và setters
}

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class ExternalUserRequest {
    private String firstName;
    // getters và setters
}
```

Với cấu hình mặc định, `InternalUser` có property JSON `firstName`, trong khi `ExternalUserRequest` có property `first_name`. Điều này hữu ích khi model nội bộ và DTO giao tiếp với hệ thống ngoài có hợp đồng khác nhau.

Nếu mapper cũng được cấu hình global, naming strategy khai báo trực tiếp bằng `@JsonNaming` trên lớp sẽ được dùng cho lớp đó. Các lớp không khai báo annotation tiếp tục dùng chiến lược global.

## 5. Kết hợp naming strategy với `@JsonProperty`

Naming strategy phù hợp khi tên property có thể được suy ra theo quy tắc chung. Nhưng đôi khi API quy định một tên đặc biệt không tuân theo quy ước tổng thể. Khi đó, dùng `@JsonProperty` để khai báo tên bên ngoài một cách tường minh:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class AccountResponse {
    private String accountName;

    @JsonProperty("account_id")
    private String accountId;

    // getters và setters
}
```

Với mapper dùng `SNAKE_CASE`, `accountName` được suy ra thành `account_name`; `accountId` có tên tường minh `account_id`. Tên tường minh do `@JsonProperty` cung cấp được dùng làm tên JSON thay vì tiếp tục chuyển đổi theo naming strategy.

Annotation cũng có thể đặt trên getter, setter hoặc field tùy cách Jackson phát hiện property. Nếu nhiều thành phần của cùng một property có annotation khác nhau, cần đảm bảo chúng nhất quán để tránh việc Jackson hợp nhất metadata theo cách khó dự đoán.

### 5.1. Nhận nhiều tên đầu vào với `@JsonAlias`

Khi API đang chuyển từ tên cũ sang tên mới, có thể cần chấp nhận cả hai tên trong giai đoạn tương thích. `@JsonAlias` khai báo các tên thay thế được chấp nhận khi deserialize:

```java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class AccountRequest {
    @JsonProperty("account_id")
    @JsonAlias({"accountId", "id"})
    private String accountId;

    public String getAccountId() {
        return accountId;
    }

    public void setAccountId(String accountId) {
        this.accountId = accountId;
    }
}
```

Với cấu hình trên, Jackson nhận `account_id`, `accountId` hoặc `id` khi đọc JSON. Khi serialize, tên chuẩn được ghi là `account_id`. `@JsonAlias` không tạo ra nhiều tên đầu ra; nó phục vụ việc đọc dữ liệu tương thích.

## 6. Phạm vi tác động: POJO property không đồng nghĩa với mọi JSON key

Property naming strategy được thiết kế để đổi tên các property mà Jackson phát hiện trên POJO/bean. Nó không phải một phép biến đổi chuỗi áp dụng cho mọi key trong JSON.

Ví dụ với `Map`:

```java
Map<String, Object> values = Map.of(
        "firstName", "An",
        "custom-key", 10
);

String json = mapper.writeValueAsString(values);
```

Các key của map là dữ liệu do ứng dụng cung cấp. Naming strategy của POJO không tự đổi `firstName` thành `first_name` trong map. Nếu cần chuẩn hóa map key, hãy thực hiện chuyển đổi ở tầng xử lý dữ liệu hoặc dùng serializer/deserializer tùy chỉnh cho kiểu map phù hợp.

Tương tự, naming strategy không tự đổi tên các chuỗi xuất hiện trong JSON value, nội dung văn bản, URL hoặc tên của một key nằm trong raw JSON tree theo cách tổng quát. Nó chỉ điều khiển tên property trong quá trình Jackson introspect model.

## 7. Phân biệt naming strategy với các cơ chế liên quan

Một số cơ chế khác cũng ảnh hưởng đến việc nhận diện tên JSON nhưng giải quyết vấn đề khác:

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| Property naming strategy | Chuyển tên property theo một quy tắc chung | `firstName` → `first_name` |
| `@JsonProperty` | Khai báo tên JSON tường minh cho một property | `@JsonProperty("account_id")` |
| `@JsonAlias` | Nhận thêm tên thay thế khi deserialize | Nhận cả `account_id` và `id` |
| `@JsonIgnore` | Bỏ qua property trong quá trình xử lý JSON theo cấu hình/annotation | Không đọc hoặc ghi property được đánh dấu |
| `ACCEPT_CASE_INSENSITIVE_PROPERTIES` | Cho phép đối chiếu tên property không phân biệt hoa/thường | `first_name` và `FIRST_NAME` có thể được chấp nhận theo cấu hình |

Đặc biệt, naming strategy không đồng nghĩa với chế độ case-insensitive. Nếu API gửi sai dấu phân cách hoặc tên property khác quy ước, không nên kỳ vọng `SNAKE_CASE` tự chấp nhận mọi biến thể. Dùng alias cho các tên đầu vào cụ thể hoặc cấu hình case-insensitive khi hợp đồng cho phép.

## 8. Tạo naming strategy tùy chỉnh

Các chiến lược có sẵn đáp ứng phần lớn quy ước phổ biến. Nếu hệ thống có quy tắc riêng, Jackson 2.12+ cho phép tạo strategy bằng cách kế thừa `PropertyNamingStrategies.NamingBase` và triển khai `translate()`:

```java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;

public class ApiPrefixNamingStrategy
        extends PropertyNamingStrategies.NamingBase {

    @Override
    public String translate(String propertyName) {
        if (propertyName == null || propertyName.isBlank()) {
            return propertyName;
        }
        return "api_" + propertyName;
    }
}
```

Đăng ký cho toàn mapper:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.setPropertyNamingStrategy(new ApiPrefixNamingStrategy());
```

Hoặc áp dụng cho riêng lớp:

```java
@JsonNaming(ApiPrefixNamingStrategy.class)
public class PartnerRequest {
    private String partnerCode;
    private String requestTime;

    // getters và setters
}
```

Tên JSON sẽ lần lượt là `api_partnerCode` và `api_requestTime` nếu không có tên tường minh khác. Ví dụ này cố ý đơn giản để minh họa extension point; trong thực tế, strategy nên mô tả một quy ước rõ ràng, có tài liệu và được kiểm thử bằng các tên đại diện.

Một naming strategy tùy chỉnh nên có các đặc tính:

- **Xác định:** cùng một tên đầu vào luôn cho cùng một tên đầu ra.
- **Không phụ thuộc trạng thái request:** tránh giữ dữ liệu người dùng hoặc thay đổi kết quả theo thời điểm.
- **Không gây va chạm:** hai property khác nhau không nên bị biến thành cùng một tên JSON.
- **Có thể đọc ngược:** nếu dùng cùng strategy cho deserialize, tên đầu ra phải có khả năng ánh xạ nhất quán về property Java.
- **Được kiểm thử với acronym và tên biên:** ví dụ tên một ký tự, chữ viết tắt, tên đã có dấu phân cách và tên bắt đầu bằng ký tự đặc biệt.

Nếu quy tắc chỉ áp dụng cho một hoặc hai property, `@JsonProperty` thường rõ ràng và dễ bảo trì hơn việc tạo strategy riêng.

## 9. Những tình huống cần chú ý

### 9.1. Hai property có thể trùng tên sau khi chuyển đổi

Giả sử một model có cả `userName` và `user_name`. Khi áp dụng `SNAKE_CASE`, các tên có thể hội tụ về cùng tên JSON tùy cách Jackson phát hiện property. Tình trạng này tạo ra xung đột mapping hoặc khiến dữ liệu bị xử lý không như mong muốn.

Hãy tránh thiết kế hai property Java có tên khác nhau nhưng cùng ánh xạ tới một tên JSON. Nếu hai trường thực sự mang ý nghĩa khác nhau, cần quy định tên JSON tường minh và kiểm tra metadata/serialization của lớp.

### 9.2. Boolean getter có thể ảnh hưởng tên property

JavaBeans có quy ước getter `isActive()` cho boolean. Jackson có thể phát hiện property từ getter/setter/field rồi mới áp dụng naming strategy. Nếu một lớp có cả `isActive()` và `getActive()` hoặc field/getter không nhất quán, hãy xác định tên logical property mà Jackson nhìn thấy trước khi kết luận strategy chuyển đổi sai.

### 9.3. Kế thừa và property trùng tên

Khi model kế thừa field hoặc getter từ lớp cha, Jackson tổng hợp các property nhìn thấy trong kiểu đang serialize/deserialize. Annotation và tên tường minh ở lớp cha/lớp con có thể ảnh hưởng metadata cuối cùng. Với hierarchy phức tạp, hãy viết test trên kiểu cụ thể được sử dụng trong API thay vì chỉ kiểm tra lớp cha riêng lẻ.

### 9.4. Naming strategy không thay thế schema validation

Chuyển `firstName` thành `first_name` không bảo đảm JSON đã tuân thủ toàn bộ hợp đồng. Kiểu dữ liệu, field bắt buộc, nullability, enum, format ngày giờ và cấu trúc lồng nhau vẫn cần được kiểm tra riêng. Naming strategy chỉ giải quyết một phần: tên property.

## 10. Kiểm tra serialization và deserialization

Một bài kiểm tra tốt nên xác nhận cả chiều ghi lẫn chiều đọc. Ví dụ với JUnit 5 và Jackson 2.x:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class NamingStrategyTest {
    @Test
    void usesSnakeCaseForSerializationAndDeserialization() throws Exception {
        ObjectMapper mapper = new ObjectMapper()
                .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

        Customer customer = new Customer("An Nguyen", "0900000000", true);

        String json = mapper.writeValueAsString(customer);
        assertTrue(json.contains("\"customer_name\""));
        assertTrue(json.contains("\"phone_number\""));

        Customer restored = mapper.readValue(json, Customer.class);
        assertEquals("An Nguyen", restored.getCustomerName());
        assertEquals("0900000000", restored.getPhoneNumber());
        assertTrue(restored.isActive());
    }
}
```

Trong ví dụ trên, `Customer` là lớp có constructor và accessor như phần 3. Test kiểm tra hợp đồng tên JSON thay vì so sánh toàn bộ chuỗi JSON theo thứ tự field. Cách này tránh làm test phụ thuộc vào thứ tự property nếu thứ tự đó không thuộc hợp đồng.

Với `@JsonNaming`, nên có test riêng để chứng minh annotation của một DTO hoạt động đúng khi mapper vẫn giữ naming strategy mặc định hoặc đang có cấu hình global khác.

## 11. Chọn phạm vi cấu hình phù hợp

| Bối cảnh | Cách áp dụng phù hợp |
|---|---|
| Toàn bộ API dùng `snake_case` | Cấu hình global trên mapper dành cho API đó |
| Hầu hết model giữ camel case, chỉ một DTO dùng `snake_case` | `@JsonNaming` trên DTO đó |
| Một property có tên đặc biệt | `@JsonProperty` |
| Đọc được nhiều tên cũ trong giai đoạn chuyển đổi | `@JsonAlias` kết hợp tên chuẩn |
| Quy ước tên riêng của một đối tác | Naming strategy tùy chỉnh hoặc annotation tường minh, tùy phạm vi |
| Map key cần đổi tên | Xử lý key riêng hoặc serializer/deserializer cho map |

Trong ứng dụng lớn, có thể tách mapper theo ranh giới giao tiếp: mapper cho REST API, mapper cho file nội bộ hoặc mapper cho một hệ thống đối tác. Mỗi mapper nên có cấu hình rõ ràng, được tạo một lần và tái sử dụng. Điều này giúp tránh việc một thay đổi naming strategy vô tình ảnh hưởng tới những payload khác.

## 12. Kết luận

Property naming strategy giúp Jackson ánh xạ tên property Java sang quy ước tên JSON và ngược lại. Dùng cấu hình global khi một nhóm model chia sẻ cùng hợp đồng; dùng `@JsonNaming` khi chỉ một lớp cần quy ước riêng; dùng `@JsonProperty` cho tên đặc biệt và `@JsonAlias` cho tên đầu vào thay thế. Hãy nhớ rằng chiến lược này áp dụng cho property của POJO, không tự động đổi mọi key trong `Map`, và không thay thế việc kiểm tra schema hoặc hợp đồng API.
