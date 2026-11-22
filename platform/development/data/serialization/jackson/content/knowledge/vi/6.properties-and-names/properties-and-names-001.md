# Cách Jackson nhận diện trường, getter và setter

Khi Jackson chuyển một object Java thành JSON, nó phải quyết định thành viên nào của class sẽ trở thành thuộc tính JSON. Khi đọc JSON, Jackson lại phải tìm cách đưa từng giá trị vào object. Việc này được thực hiện thông qua cơ chế **property introspection**: Jackson khảo sát field, getter, setter, constructor hoặc factory method, sau đó ghép những thành viên tương ứng thành các logical property.

Hiểu cách nhận diện property giúp giải thích vì sao một field không xuất hiện trong JSON, vì sao một getter tạo ra thuộc tính dù class không có field cùng tên, hoặc vì sao Jackson có thể serialize được nhưng lại không deserialize được một thuộc tính. Nó cũng giúp thiết kế DTO rõ ràng và tránh để cấu hình reflection vô tình làm lộ dữ liệu nội bộ.

Các ví dụ Java trong bài chủ yếu dùng API Jackson 2.x với package `com.fasterxml.jackson.*`. Nguyên tắc nhận diện field/getter/setter vẫn là nền tảng của databind; khi dùng Jackson 3.x, cần đổi các package databind theo major version và kiểm tra API tương ứng.

## 1. Property trong Jackson là gì?

Một property của Jackson là một **thuộc tính logic** mà mapper có thể đọc từ object hoặc ghi vào object. Property không nhất thiết phải trùng với một field Java.

Ví dụ:

```java
public class Customer {
    private String fullName;

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
```

Jackson nhìn thấy ba thành viên:

- Field `fullName`.
- Getter `getFullName()`.
- Setter `setFullName(String)`.

Chúng cùng biểu diễn một property logic có tên `fullName`. Khi serialize, Jackson thường gọi getter để lấy giá trị. Khi deserialize, Jackson thường gọi setter để gán giá trị. Field private không tự động trở thành accessor theo mặc định chỉ vì nó tồn tại; tuy nhiên, trong trường hợp phù hợp Jackson có thể suy luận field là mutator đi cùng accessor đã được nhận diện.

Ví dụ kết quả:

```json
{
  "fullName": "Nguyen An"
}
```

Điểm quan trọng là Jackson không mặc định tạo ba key JSON cho ba thành viên. Nó ghép chúng thành một property có tên logic chung.

## 2. Jackson khảo sát thành viên theo từng vai trò

Property introspection không chỉ là tìm tên method. Jackson kiểm tra loại thành viên, chữ ký, visibility, annotation và quy tắc cấu hình của mapper.

### 2.1. Field

Field là biến thành viên của class:

```java
public class Product {
    public String code;
    private BigDecimal price;
}
```

Theo quy tắc auto-detection mặc định thường dùng trong Jackson 2.x:

- Field public có thể được nhận diện.
- Field private, protected hoặc package-private không tự động được chọn chỉ dựa trên tên.
- Field được đánh dấu tường minh bằng annotation như `@JsonProperty` vẫn có thể trở thành property.
- Visibility của field có thể được thay đổi bằng `@JsonAutoDetect` hoặc cấu hình mapper.

Field có thể phục vụ cả hai chiều. Jackson có thể đọc giá trị trực tiếp từ field khi serialize và gán giá trị vào field khi deserialize nếu field được phép truy cập và cấu hình cho phép.

Ví dụ dùng field public:

```java
public class Product {
    public String code;
    public BigDecimal price;
}
```

Với cấu hình mặc định, JSON có thể chứa cả `code` và `price`:

```json
{
  "code": "P-100",
  "price": 125000.0
}
```

### 2.2. Getter

Getter là method không nhận tham số và trả về giá trị. Jackson nhận diện hai dạng JavaBean phổ biến:

- Getter thông thường: tên bắt đầu bằng `get`, ví dụ `getName()`.
- Boolean is-getter: tên bắt đầu bằng `is`, ví dụ `isActive()`.

```java
public class Account {
    public String getOwnerName() {
        return "An";
    }

    public boolean isActive() {
        return true;
    }
}
```

Hai method trên tạo ra hai property logic `ownerName` và `active`. Jackson không yêu cầu phải có field cùng tên. Getter có thể trả về giá trị được tính toán từ nhiều field, lấy từ cache hoặc được tạo từ logic của class.

Ví dụ JSON:

```json
{
  "ownerName": "An",
  "active": true
}
```

Quy tắc nhận diện quan trọng:

- `getXxx()` phải không có tham số và có giá trị trả về phù hợp; method `void` không phải getter thông thường.
- `isXxx()` mặc định dành cho kiểu trả về `boolean` hoặc `Boolean`.
- `getClass()` không được xem là property JSON thông thường.
- Static method không phải getter instance của object.
- Visibility mặc định thường yêu cầu getter public, nhưng có thể thay đổi.

Trong Jackson 2.14 trở lên, `MapperFeature.ALLOW_IS_GETTERS_FOR_NON_BOOLEAN` có thể cho phép nhận diện method `isXxx()` có kiểu trả về không phải boolean. Tính năng này mặc định tắt trong Jackson 2.x; chỉ bật khi có chủ đích, chẳng hạn tương thích một quy ước property của Kotlin.

### 2.3. Setter

Setter là method nhận một tham số, thường có tên bắt đầu bằng `set`:

```java
public class Account {
    private String ownerName;

    public void setOwnerName(String ownerName) {
        this.ownerName = ownerName;
    }
}
```

Setter tạo khả năng ghi giá trị vào object khi deserialize. Trong cấu hình Jackson 2.x mặc định, setter có thể được auto-detect kể cả khi không public. Vì vậy, một setter package-private hoặc protected vẫn có thể được chọn tùy cấu hình visibility và khả năng truy cập reflection.

Setter không nhất thiết phải có getter tương ứng. Một property chỉ có setter có thể được nhận diện để đọc JSON vào object nhưng không được xuất ra khi serialize nếu không có accessor đọc phù hợp.

Ví dụ:

```java
public class ImportRequest {
    private String source;

    public void setSource(String source) {
        this.source = source;
    }
}
```

Jackson có thể dùng `setSource()` để tiếp nhận giá trị JSON `source`, nhưng không có getter hoặc field được nhận diện để xuất giá trị đó trở lại JSON.

### 2.4. Constructor và factory method

Với object bất biến hoặc class không có setter, Jackson có thể tạo object thông qua constructor hoặc static factory method. Đây là một nguồn property khác, thường được gọi là creator property.

```java
public class UserId {
    private final String value;

    @JsonCreator
    public UserId(@JsonProperty("value") String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
```

Ở đây:

- `@JsonCreator` chỉ ra constructor dùng để tạo object.
- `@JsonProperty("value")` đặt tên property tương ứng với tham số constructor.
- `getValue()` cung cấp accessor để serialize.

Cách này hữu ích với immutable DTO, value object hoặc class không muốn cung cấp setter công khai. Khả năng suy luận tên tham số constructor còn phụ thuộc phiên bản Jackson, compiler metadata và module hỗ trợ; khi cần hợp đồng rõ ràng, nên khai báo `@JsonCreator` và `@JsonProperty` tường minh.

## 3. Quy tắc đặt tên property từ field và JavaBean method

Jackson cần chuyển tên thành viên Java thành tên property logic trước khi ghi JSON hoặc tìm giá trị đầu vào.

| Thành viên Java | Property mặc định |
|---|---|
| Field `firstName` | `firstName` |
| Getter `getFirstName()` | `firstName` |
| Boolean getter `isEnabled()` | `enabled` |
| Setter `setFirstName(String)` | `firstName` |
| Getter `getURL()` | Thông thường là `url` với quy tắc mặc định của Jackson 2.x |
| Getter `getURL()` khi bật chuẩn Bean naming | `URL` |

Jackson mặc định dùng quy tắc đặt tên JavaBean có một số khác biệt lịch sử so với `java.beans.Introspector`. Cụ thể, `MapperFeature.USE_STD_BEAN_NAMING` mặc định tắt trong Jackson 2.x; khi bật, tên có các chữ hoa liên tiếp như `getURL()` được xử lý theo chuẩn Bean naming nghiêm ngặt hơn.

Ví dụ:

```java
public class Endpoint {
    public String getURL() {
        return "https://example.test";
    }
}
```

Tên property có thể là `url` theo quy tắc Jackson mặc định hoặc `URL` khi bật `USE_STD_BEAN_NAMING`. Đây là khác biệt đáng chú ý khi tích hợp với API đã có quy ước viết hoa acronym.

## 4. Cách Jackson ghép field, getter và setter thành một property

Jackson gom các thành viên có cùng logical name thành một property. Đây là lý do một field private có thể được sử dụng khi class có getter public cùng tên, hoặc một annotation đặt trên getter có thể ảnh hưởng đến cách setter được xử lý.

Xét class:

```java
public class Employee {
    private String department;

    public String getDepartment() {
        return department;
    }

    public void setDepartment(String department) {
        this.department = department;
    }
}
```

Property `department` có nhiều accessor nhưng chỉ đại diện cho một giá trị:

| Thành viên | Vai trò thường gặp |
|---|---|
| `getDepartment()` | Đọc giá trị từ object khi serialize |
| `setDepartment(...)` | Gán giá trị khi deserialize |
| `department` | Có thể là field hỗ trợ mutator nếu quy tắc visibility/inference cho phép |

Trong Jackson 2.x, `MapperFeature.INFER_PROPERTY_MUTATORS` mặc định bật. Nếu Jackson tìm thấy accessor hiển thị cho một property, nó có thể suy luận field hoặc setter ít hiển thị hơn có cùng logical name là mutator của property đó. Cơ chế này giúp mô hình JavaBean hoạt động thuận tiện, nhưng không nên dùng nó như một cách thay thế cho cấu hình rõ ràng khi thiết kế hợp đồng dữ liệu.

Serialization và deserialization cũng không bắt buộc phải dùng cùng một accessor:

- Serialization cần accessor có thể đọc giá trị, thường là getter hoặc field.
- Deserialization cần accessor có thể ghi giá trị, thường là setter, field hoặc creator parameter.

Vì vậy, một class có thể serialize thành công nhưng deserialize thất bại. Chẳng hạn, getter tồn tại nhưng class không có setter, field phù hợp hoặc creator mà Jackson có thể dùng để khởi tạo giá trị.

### 4.1. Getter-only property

Một getter-only property vẫn có thể xuất hiện trong JSON:

```java
public class Report {
    public String getStatus() {
        return "READY";
    }
}
```

Khi serialize, Jackson có thể tạo:

```json
{
  "status": "READY"
}
```

Nhưng khi deserialize, Jackson không có cách tổng quát để gán một giá trị khác vào property này. Một ngoại lệ thường gặp trong Jackson 2.x là getter trả về collection hoặc map đã được khởi tạo: với `MapperFeature.USE_GETTERS_AS_SETTERS` mặc định bật, Jackson có thể gọi getter rồi thêm phần tử vào collection/map hiện hữu. Đây là cơ chế đặc biệt, không nên suy rộng thành mọi getter-only property đều ghi được.

### 4.2. Setter-only property

Setter-only property có thể nhận dữ liệu đầu vào nhưng không nhất thiết xuất hiện trong JSON đầu ra:

```java
public class SecretInput {
    private String token;

    public void setToken(String token) {
        this.token = token;
    }
}
```

Nếu cần mô hình hóa rõ property chỉ nhận từ JSON, có thể dùng `@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)` thay vì dựa vào việc thiếu getter. Annotation làm rõ ý định và ít phụ thuộc vào cấu trúc hiện tại của class.

## 5. Visibility: field/getter/setter nào được tự động phát hiện?

Visibility quyết định thành viên nào đủ điều kiện để Jackson tự động nhận diện. Cần phân biệt **auto-detection** với **khả năng truy cập reflection**: một member không được auto-detect theo visibility mặc định vẫn có thể được chọn khi được annotation tường minh hoặc khi visibility được mở rộng.

Trong Jackson 2.x, các mặc định thường gặp:

| Loại accessor | Quy tắc auto-detection mặc định |
|---|---|
| Field | Public field |
| Getter `getXxx()` | Public getter |
| Is-getter `isXxx()` | Public, trả về boolean/Boolean |
| Setter `setXxx(value)` | Setter có thể được phát hiện bất kể visibility |
| Creator | Có các quy tắc riêng cho constructor/factory method |

Các quy tắc này có thể được thay đổi ở cấp class bằng `@JsonAutoDetect`, hoặc ở cấp mapper bằng `setVisibility(...)` trong Jackson 2.x.

### 5.1. Dùng @JsonAutoDetect cho một class

Nếu muốn Jackson làm việc trực tiếp với tất cả field, kể cả private, có thể cấu hình:

```java
import com.fasterxml.jackson.annotation.JsonAutoDetect;

@JsonAutoDetect(
        fieldVisibility = JsonAutoDetect.Visibility.ANY,
        getterVisibility = JsonAutoDetect.Visibility.NONE,
        isGetterVisibility = JsonAutoDetect.Visibility.NONE,
        setterVisibility = JsonAutoDetect.Visibility.NONE
)
public class InternalConfig {
    private String region;
    private boolean enabled;
}
```

Các mức visibility có ý nghĩa:

| Giá trị | Ý nghĩa |
|---|---|
| `ANY` | Nhận diện member ở mọi mức truy cập |
| `NON_PRIVATE` | Nhận diện member không phải private |
| `PROTECTED_AND_PUBLIC` | Chỉ protected và public |
| `PUBLIC_ONLY` | Chỉ public |
| `NONE` | Không auto-detect loại member đó |
| `DEFAULT` | Dùng cấu hình visibility mặc định đang có |

Dùng `ANY` cho field giúp serialize/deserialize private field mà không cần getter/setter. Tuy nhiên, nó cũng khiến mọi field phù hợp trở thành một phần của hợp đồng JSON. Khi class thêm field nội bộ, dữ liệu trao đổi có thể thay đổi ngoài ý muốn. Vì vậy, field-based visibility phù hợp hơn với DTO được kiểm soát rõ ràng; không nên bật rộng cho toàn ứng dụng nếu các entity có nhiều trạng thái nội bộ.

### 5.2. Cấu hình visibility trên mapper trong Jackson 2.x

Nếu muốn áp dụng quy tắc cho toàn mapper, có thể dùng:

```java
ObjectMapper mapper = new ObjectMapper();

mapper.setVisibility(PropertyAccessor.FIELD, JsonAutoDetect.Visibility.ANY);
mapper.setVisibility(PropertyAccessor.GETTER, JsonAutoDetect.Visibility.NONE);
mapper.setVisibility(PropertyAccessor.IS_GETTER, JsonAutoDetect.Visibility.NONE);
mapper.setVisibility(PropertyAccessor.SETTER, JsonAutoDetect.Visibility.NONE);
```

Cấu hình này khiến mapper dùng field làm accessor tự động và tắt auto-detection getter/setter. Hãy cân nhắc ảnh hưởng đến mọi class được mapper xử lý, bao gồm class thư viện và kiểu lồng nhau.

Nếu chỉ muốn một class có visibility khác, `@JsonAutoDetect` thường dễ kiểm soát phạm vi hơn. Nếu dự án dùng mapper chung cho nhiều hợp đồng, nên tránh cấu hình visibility toàn cục quá rộng.

## 6. Dùng annotation để chỉ rõ property

Annotation giúp Jackson hiểu ý định của ứng dụng khi quy ước JavaBean không đủ rõ.

### 6.1. @JsonProperty: đặt tên và đánh dấu property

`@JsonProperty` có thể dùng trên field, getter, setter hoặc tham số constructor. Nó có thể đánh dấu một member là property và xác định tên bên ngoài:

```java
public class User {
    @JsonProperty("user_id")
    private Long id;

    @JsonProperty("display_name")
    public String getName() {
        return name;
    }

    private String name;
}
```

Khi serialize, tên JSON của các property được đánh dấu là `user_id` và `display_name`. Annotation trên field private cũng có thể khiến field được nhận diện dù field visibility mặc định không tự chọn nó.

Khi cùng một property có nhiều accessor, nên giữ tên tường minh nhất quán hoặc đặt annotation ở vị trí thể hiện rõ hợp đồng. Tránh đặt các tên khác nhau trên field/getter/setter nếu không chủ ý tạo property tách biệt.

### 6.2. @JsonGetter và @JsonSetter

Hai annotation này làm rõ vai trò method:

```java
public class User {
    private String displayName;

    @JsonGetter("display_name")
    public String display() {
        return displayName;
    }

    @JsonSetter("display_name")
    public void updateDisplayName(String value) {
        this.displayName = value;
    }
}
```

Ví dụ cho thấy method không cần tên theo JavaBean convention nếu được đánh dấu tường minh. `@JsonGetter` xác định method cung cấp giá trị khi serialize; `@JsonSetter` xác định method nhận giá trị khi deserialize.

### 6.3. @JsonIgnore và quyền đọc/ghi

`@JsonIgnore` có thể loại bỏ một property khỏi quá trình data binding:

```java
public class User {
    private String username;

    @JsonIgnore
    public String getPasswordHash() {
        return passwordHash;
    }

    private String passwordHash;
}
```

Annotation đặt trên một accessor thường tác động đến toàn bộ logical property, kể cả accessor tương ứng. Đây là điểm cần nhớ khi field, getter và setter cùng thuộc một property.

Nếu cần một property chỉ đọc hoặc chỉ ghi theo góc nhìn JSON, dùng `@JsonProperty(access = ...)`:

```java
public class RegistrationRequest {
    private String username;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String password;

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long generatedId;
}
```

- `READ_ONLY`: Jackson có thể xuất property từ object ra JSON nhưng không nhận giá trị đó từ JSON đầu vào.
- `WRITE_ONLY`: Jackson nhận property từ JSON đầu vào nhưng không xuất nó khi serialize.
- `READ_WRITE`: cho phép cả hai chiều.
- `AUTO`: để Jackson áp dụng quy tắc mặc định.

Ví dụ, password thường là dữ liệu đầu vào và không được xuất ngược trong response. ID do server tạo có thể là dữ liệu chỉ đọc từ góc nhìn client.

## 7. Đổi tên property bằng naming strategy

Auto-detection tạo tên logic ban đầu, còn naming strategy chuyển tên đó sang quy ước của định dạng trao đổi dữ liệu.

Ví dụ Java dùng camelCase:

```java
public class UserProfile {
    private String firstName;
    private String lastName;
}
```

Nếu API yêu cầu snake_case, có thể cấu hình:

```java
ObjectMapper mapper = JsonMapper.builder()
        .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
        .build();
```

Kết quả tên JSON sẽ là:

```json
{
  "first_name": "An",
  "last_name": "Nguyen"
}
```

Có thể áp dụng ở cấp class bằng `@JsonNaming`:

```java
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public class UserProfile {
    private String firstName;
    private String lastName;
}
```

Khi cần một tên cụ thể khác với naming strategy, dùng `@JsonProperty("...")` để xác định tên external property. Trong Jackson 2.x, tên được chỉ định tường minh thường không bị naming strategy đổi lại, trừ khi bật `MapperFeature.ALLOW_EXPLICIT_PROPERTY_RENAMING`.

Không nên nhầm naming strategy với visibility: naming strategy chỉ đổi tên property đã được nhận diện, không khiến một private field vốn không được phát hiện tự động trở thành property.

## 8. Ví dụ tổng hợp: một property qua hai chiều

Xét DTO sau:

```java
public class CustomerRequest {
    private String firstName;
    private String email;
    private String password;

    public String getFirstName() {
        return firstName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    @JsonProperty("email_address")
    public String getEmail() {
        return email;
    }

    @JsonProperty("email_address")
    public void setEmail(String email) {
        this.email = email;
    }

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }
}
```

Có thể cấu hình mapper với snake_case cho các property còn lại:

```java
ObjectMapper mapper = JsonMapper.builder()
        .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
        .build();
```

Với object có `firstName = "An"`, `email = "an@example.test"`, `password = "secret"`, JSON đầu ra có thể là:

```json
{
  "first_name": "An",
  "email_address": "an@example.test"
}
```

Property `password` không xuất hiện do được đánh dấu `WRITE_ONLY`. Khi deserialize, Jackson vẫn nhận giá trị password từ JSON và gọi setter tương ứng. `email_address` được đặt tên tường minh, còn `firstName` được naming strategy chuyển thành `first_name`.

Ví dụ này minh họa ba bước riêng: Jackson nhận diện accessor, ghép accessor thành property logic, rồi áp dụng tên và quyền đọc/ghi cho property đó.

## 9. Một số trường hợp đặc biệt cần nhận biết

### 9.1. Getter tính toán có thể trở thành property ngoài dự kiến

Một method như `getDisplayLabel()` có thể bị nhận diện là property dù không có field tương ứng:

```java
public String getDisplayLabel() {
    return code + " - " + name;
}
```

Nếu đây là dữ liệu dẫn xuất không muốn đưa vào JSON, đánh dấu `@JsonIgnore` hoặc dùng DTO riêng. Không nên giả định Jackson chỉ serialize các field đã khai báo.

### 9.2. Overloaded setter

Một class có nhiều method cùng tên nhưng khác kiểu tham số có thể khiến Jackson khó chọn mutator:

```java
public void setAmount(BigDecimal amount) { ... }
public void setAmount(String amount) { ... }
```

Khi cần overload, hãy khai báo rõ kiểu dữ liệu và annotation thích hợp; tốt hơn nữa là giữ một setter không mơ hồ cho một JSON property. Nếu cần nhiều cách chuyển đổi đầu vào, dùng custom deserializer để thể hiện quy tắc rõ ràng.

### 9.3. Collection getter không có setter

Với một collection đã được khởi tạo:

```java
public class Cart {
    private final List<String> items = new ArrayList<>();

    public List<String> getItems() {
        return items;
    }
}
```

Jackson 2.x có thể dùng getter để lấy collection hiện hữu rồi thêm các phần tử từ JSON nếu `USE_GETTERS_AS_SETTERS` được bật. Nếu collection là immutable hoặc getter trả về bản sao, cách này không phù hợp. Khi cần kiểm soát chính xác, cung cấp setter hoặc creator rõ ràng.

### 9.4. Java record

Record không dùng getter theo JavaBean convention. Component `name` tạo accessor `name()`, không phải `getName()`. Jackson hỗ trợ record trong các phiên bản hiện đại; khi deserialize, mapper dùng canonical constructor cùng tên component. Với hệ thống dùng Jackson cũ, cần kiểm tra phiên bản tối thiểu và hành vi record cụ thể trước khi áp dụng.

### 9.5. Lombok và code được sinh tự động

Nếu Lombok sinh `getName()` và `setName(...)`, Jackson thường nhìn thấy bytecode method như các method Java thông thường. Tuy nhiên, vị trí annotation được Lombok sao chép hoặc không sao chép có thể ảnh hưởng kết quả introspection. Khi property biến mất sau khi thêm Lombok hoặc đổi annotation, hãy kiểm tra bytecode và cấu hình annotation target thay vì chỉ nhìn source field.

## 10. Cách chẩn đoán property không xuất hiện hoặc không đọc được

Khi một property không xuất hiện trong JSON hoặc Jackson báo không thể gán giá trị, hãy lần lượt kiểm tra:

1. **Tên member:** method có đúng dạng `getXxx()`, `isXxx()`, `setXxx(...)` không? Getter có tham số hoặc trả về `void` không? Is-getter có trả về boolean/Boolean không?
2. **Visibility:** field/getter/setter có đạt visibility mặc định hoặc được mở bằng `@JsonAutoDetect`/mapper configuration không?
3. **Hợp nhất property:** field, getter và setter có cùng logical name không? Có annotation đặt tên khác nhau hoặc overloaded setter gây xung đột không?
4. **Annotation:** có `@JsonIgnore`, `@JsonProperty(access=...)`, `@JsonInclude` hoặc mix-in nào tác động đến property không?
5. **Chiều thao tác:** lỗi xảy ra khi serialize hay deserialize? Property có accessor đọc hay mutator ghi tương ứng không?
6. **Naming strategy:** JSON đang dùng camelCase, snake_case hay tên được chỉ định bởi `@JsonProperty`? Tên đầu vào có khớp external property name không?
7. **Cấu hình mapper thực tế:** ứng dụng đang dùng mapper nào? Mapper do framework tạo có cấu hình khác mapper tự tạo không? Mapper đã được cấu hình xong trước khi sử dụng chưa?

Có thể bật log hoặc viết một test nhỏ để xác định JSON thực tế:

```java
@Test
void shouldSerializeCustomer() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    Customer customer = new Customer();
    customer.setFullName("Nguyen An");

    String json = mapper.writeValueAsString(customer);

    assertThat(json).contains("\"fullName\":\"Nguyen An\"");
}
```

Test nên kiểm tra hợp đồng JSON mà ứng dụng cần, thay vì phụ thuộc vào việc Jackson đã gọi một method nội bộ cụ thể nào. Nếu property phải đọc được, thêm test deserialize và xác nhận giá trị trên object sau khi đọc.

## 11. Kết luận

Jackson nhận diện property từ field, getter, is-getter, setter và creator theo chữ ký, visibility, tên logic và annotation. Các thành viên cùng tên logic được ghép thành một property; getter/field thường cung cấp giá trị khi serialize, còn setter/field/creator giúp deserialize. Vì vậy, khả năng đọc và ghi của một property có thể khác nhau.

Khi thiết kế DTO, hãy dùng JavaBean convention rõ ràng, đặt annotation khi hợp đồng JSON cần tên hoặc quyền truy cập cụ thể, và giới hạn visibility theo đúng phạm vi. Nếu property biến mất, hãy xác định chiều serialize/deserialization trước, sau đó kiểm tra chữ ký accessor, visibility, annotation và mapper thực tế.

## Tài liệu tham khảo

- [Jackson Annotations — Property naming, visibility và accessor annotations](https://github.com/FasterXML/jackson-annotations/wiki/Jackson-Annotations)
- [Jackson Databind — Mapper Features](https://github.com/FasterXML/jackson-databind/wiki/Mapper-Features)
- [Jackson 2.21 — JsonAutoDetect API](https://javadoc.io/static/com.fasterxml.jackson.core/jackson-annotations/2.21/com/fasterxml/jackson/annotation/JsonAutoDetect.html)
- [Jackson 3.1 — MapperFeature API](https://javadoc.io/static/tools.jackson.core/jackson-databind/3.1.0/tools.jackson.databind/tools/jackson/databind/MapperFeature.html)

