# Tránh vô tình công bố trường nội bộ qua getter

Trong Jackson, một thuộc tính Java có thể xuất hiện trong JSON dù field tương ứng được khai báo `private`. Nguyên nhân thường gặp là lớp đó có một getter `public`. Theo quy tắc nhận diện thuộc tính JavaBean, Jackson có thể xem getter như một thuộc tính có thể tuần tự hóa và gọi nó để lấy giá trị khi ghi JSON.

Điều này dễ tạo ra lỗ hổng công bố dữ liệu: một entity hoặc DTO có getter như `getPasswordHash()`, `getInternalToken()`, `getRecoveryCode()` hay `getAdminNotes()` có thể vô tình đưa giá trị nội bộ vào response. Từ khóa `private` chỉ giới hạn truy cập trực tiếp ở Java; nó không phải chính sách bảo mật cho JSON.

Trong chương **Thuộc tính và tên** của Data Serialization Jackson, cần hiểu rằng Jackson ánh xạ các *property* được phát hiện từ field, getter, setter, constructor và annotation. Một property JSON không nhất thiết tương ứng một-một với một field. Vì vậy, khi thiết kế dữ liệu đầu ra, hãy chủ động xác định thuộc tính nào được phép công bố.

## 1. Vì sao getter có thể làm lộ field private?

Xét lớp tài khoản:

```java
public class Account {
    private long id;
    private String username;
    private String passwordHash;

    public Account(long id, String username, String passwordHash) {
        this.id = id;
        this.username = username;
        this.passwordHash = passwordHash;
    }

    public long getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }
}
```

Các field đều là `private`, nhưng ba getter đều là `public`. Với cấu hình visibility mặc định thường dùng của Jackson, các getter công khai này được nhận diện thành property. Khi tuần tự hóa:

```java
ObjectMapper mapper = new ObjectMapper();

Account account = new Account(
        10L,
        "minh",
        "pbkdf2$..."
);

String json = mapper.writeValueAsString(account);
System.out.println(json);
```

JSON có thể chứa cả `passwordHash`:

```json
{
  "id": 10,
  "username": "minh",
  "passwordHash": "pbkdf2$..."
}
```

Jackson không tự biết `passwordHash` là dữ liệu bí mật. Nó chỉ thấy một property có thể đọc và thực hiện quy tắc ánh xạ đã được cấu hình. Nếu controller trả trực tiếp entity này trong response, getter có thể trở thành đường đưa dữ liệu nội bộ ra bên ngoài.

Tên property thường được suy ra từ tên getter:

| Getter | Tên property Java/JSON mặc định thường gặp |
|---|---|
| `getPasswordHash()` | `passwordHash` |
| `getInternalToken()` | `internalToken` |
| `isEnabled()` | `enabled` |
| `getApiKey()` | `apiKey` |

Với getter dạng `isXxx()` dành cho boolean, Jackson cũng có thể nhận diện property. Do đó, chỉ tìm các field nhạy cảm trong lớp là chưa đủ; cần xem cả các accessor công khai và những property được tạo ra từ chúng.

### Getter do Lombok sinh ra

Lombok có thể tạo getter mà source code không hiển thị trực tiếp. Ví dụ, `@Getter` ở cấp lớp có thể sinh `getPasswordHash()` cho field `passwordHash`; Jackson vẫn nhận diện getter đã được biên dịch như getter được viết thủ công.

Nếu dùng Lombok và không muốn tạo getter cho một field, có thể tắt getter ở chính field đó:

```java
import lombok.AccessLevel;
import lombok.Getter;

@Getter
public class Account {
    private long id;
    private String username;

    @Getter(AccessLevel.NONE)
    private String passwordHash;
}
```

Không nên đánh giá property chỉ bằng cách đọc file source có annotation Lombok. Hãy nhớ rằng Jackson làm việc với lớp đã biên dịch và các accessor thực tế mà nó nhìn thấy.

## 2. Cách trực tiếp: dùng `@JsonIgnore`

Nếu một property không được xuất hiện trong JSON theo cả chiều ghi và đọc thông thường, có thể đánh dấu bằng `@JsonIgnore`.

```java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class Account {
    private long id;
    private String username;
    private String passwordHash;

    public long getId() {
        return id;
    }

    public String getUsername() {
        return username;
    }

    @JsonIgnore
    public String getPasswordHash() {
        return passwordHash;
    }
}
```

Khi tuần tự hóa, Jackson bỏ qua property `passwordHash`:

```json
{
  "id": 10,
  "username": "minh"
}
```

`@JsonIgnore` phù hợp khi property thực sự không thuộc hợp đồng JSON của kiểu đó. Annotation có thể đặt trên accessor hoặc thành phần property mà Jackson nhận diện. Khi một property có nhiều accessor, cần giữ annotation nhất quán và kiểm tra cách Jackson hợp nhất metadata của chúng.

Ví dụ, nếu `getPasswordHash()` được đánh dấu `@JsonIgnore` nhưng một getter khác lại công bố cùng dữ liệu dưới tên JSON khác bằng `@JsonProperty`, dữ liệu vẫn có thể xuất hiện qua property kia. Annotation cần được áp dụng theo đúng property thực tế, không chỉ theo tên field mà lập trình viên đang nghĩ tới.

## 3. Khi chỉ muốn nhận dữ liệu vào: `WRITE_ONLY`

Một số dữ liệu cần được nhận từ request nhưng không bao giờ được gửi trở lại response. Mật khẩu là ví dụ điển hình. Khi đó, `@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)` biểu thị rằng Jackson chỉ cho phép ghi property vào đối tượng khi giải tuần tự hóa, và không xuất property đó khi tuần tự hóa.

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class CreateAccountRequest {
    private String username;
    private String password;

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
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

Với property `password`, Jackson có thể nhận JSON request:

```json
{
  "username": "minh",
  "password": "user-supplied-secret"
}
```

Nhưng khi tuần tự hóa chính đối tượng request này, property `password` không được ghi ra JSON. Setter vẫn có thể được dùng để nhận giá trị đầu vào.

`JsonProperty.Access` còn có các hướng truy cập khác:

| Giá trị | Ý nghĩa |
|---|---|
| `AUTO` | Jackson quyết định theo visibility và cấu hình thông thường. |
| `READ_ONLY` | Có thể xuất property khi tuần tự hóa; không nhận giá trị từ JSON khi giải tuần tự hóa theo property này. |
| `WRITE_ONLY` | Nhận property từ JSON khi giải tuần tự hóa; không xuất property khi tuần tự hóa. |
| `READ_WRITE` | Cho phép cả hai chiều theo quy tắc property. |

Tên `READ_ONLY` và `WRITE_ONLY` được hiểu theo góc nhìn của Jackson: *read* là đọc giá trị từ đối tượng Java để ghi JSON; *write* là ghi giá trị nhận từ JSON vào đối tượng Java. Vì vậy, `WRITE_ONLY` thường dùng cho mật khẩu request, còn `READ_ONLY` phù hợp với giá trị do server tạo như mã định danh hoặc thời điểm tạo.

Đối với mật khẩu, token hoặc secret, DTO riêng cho request và response thường là lựa chọn rõ ràng hơn việc tái sử dụng cùng một lớp. `WRITE_ONLY` hữu ích khi một DTO thực sự cần hỗ trợ hai hướng, nhưng không nên giữ bí mật lâu hơn cần thiết trong bộ nhớ.

## 4. Bỏ qua nhiều property bằng `@JsonIgnoreProperties`

Nếu một lớp có một nhóm property nội bộ cần loại khỏi JSON, có thể dùng annotation ở cấp lớp:

```java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties({"passwordHash", "internalMemo", "resetToken"})
public class Account {
    private long id;
    private String username;
    private String passwordHash;
    private String internalMemo;
    private String resetToken;

    // Constructor, getter và setter
}
```

Jackson bỏ qua các property có tên được liệt kê khi xử lý kiểu `Account` theo cấu hình annotation. Cách này hữu ích khi có nhiều property cần bỏ qua và danh sách đó thuộc chính sách cố định của lớp.

Có thể dùng `@JsonIgnoreProperties(ignoreUnknown = true)` để bỏ qua field lạ khi giải tuần tự hóa. Cần phân biệt hai mục đích:

- `@JsonIgnoreProperties({"passwordHash"})` chỉ định các property cụ thể cần bỏ qua.
- `@JsonIgnoreProperties(ignoreUnknown = true)` cho phép bỏ qua các property JSON không được lớp đích nhận diện.

`ignoreUnknown = true` không phải cơ chế che giấu các getter nhạy cảm của lớp khi ghi JSON. Muốn ngăn một property được xuất, hãy khai báo property cần bỏ qua hoặc thiết kế kiểu response chỉ chứa dữ liệu công khai.

## 5. Kiểm soát visibility của property

Jackson có thể cấu hình cách nhận diện field, getter, setter, creator thông qua `@JsonAutoDetect` hoặc `ObjectMapper.setVisibility()`. Nếu một lớp có nhiều getter công khai nhưng chỉ muốn đưa một số thuộc tính được chọn vào JSON, có thể giảm visibility tự động rồi đánh dấu rõ property được phép xuất.

Ví dụ chỉ nhận diện getter khi được đánh dấu tường minh:

```java
import com.fasterxml.jackson.annotation.JsonAutoDetect;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonAutoDetect(
        fieldVisibility = JsonAutoDetect.Visibility.NONE,
        getterVisibility = JsonAutoDetect.Visibility.NONE,
        isGetterVisibility = JsonAutoDetect.Visibility.NONE
)
public class PublicAccountView {
    private String username;
    private String internalMemo;

    public PublicAccountView(String username, String internalMemo) {
        this.username = username;
        this.internalMemo = internalMemo;
    }

    @JsonProperty("username")
    public String getUsername() {
        return username;
    }

    public String getInternalMemo() {
        return internalMemo;
    }
}
```

Trong ví dụ, getter `getInternalMemo()` không được tự động nhận diện do `getterVisibility = NONE`. Getter `getUsername()` được đưa vào hợp đồng JSON nhờ `@JsonProperty` tường minh.

Visibility có thể tác động rộng đến cách Jackson nhận diện property. Nếu thay đổi visibility ở cấp `ObjectMapper`, ảnh hưởng có thể lan tới mọi kiểu dữ liệu được mapper xử lý. Chỉ nên dùng cấu hình toàn cục khi đó là quy ước chung được chủ động thiết kế và kiểm tra. Với một lớp cụ thể, annotation cấp lớp thường dễ giới hạn phạm vi hơn.

## 6. Không dựa vào `private`, `transient` hoặc `@JsonInclude` để bảo vệ dữ liệu

### 6.1. `private` không ngăn getter được gọi

Field `private` vẫn có thể được getter `public` công bố. Jackson không cần truy cập trực tiếp field nếu property đã được phát hiện qua getter.

### 6.2. `transient` không phải chính sách JSON đầy đủ

Từ khóa Java `transient` chủ yếu phục vụ cơ chế serialization native và các quy tắc liên quan đến field. Nếu lớp vẫn có getter công khai trả về cùng dữ liệu, getter đó vẫn có thể được Jackson nhận diện thành property tùy cấu hình visibility. Vì vậy, không nên chỉ thêm `transient` rồi cho rằng dữ liệu đã được loại khỏi JSON.

### 6.3. `@JsonInclude` chỉ quyết định điều kiện đưa giá trị vào

Ví dụ:

```java
import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public class Account {
    private String passwordHash;

    public String getPasswordHash() {
        return passwordHash;
    }
}
```

Nếu `passwordHash` khác `null`, nó vẫn có thể được xuất. `NON_NULL` chỉ bỏ qua giá trị null; nó không biến một property nhạy cảm thành property bị ẩn. Hãy dùng `@JsonIgnore`, `WRITE_ONLY` hoặc DTO riêng cho mục đích bảo vệ dữ liệu.

## 7. Rủi ro khi trả trực tiếp entity hoặc domain object qua REST API

Một tình huống phổ biến trong Spring MVC là controller trả về entity JPA:

```java
@GetMapping("/accounts/{id}")
public Account getAccount(@PathVariable long id) {
    return accountService.findById(id);
}
```

HTTP message converter có thể dùng Jackson để tuần tự hóa giá trị trả về thành response body. Khi đó, các getter mà Jackson nhận diện trên entity có thể xuất hiện trong JSON. Nếu entity có getter cho `passwordHash`, `internalNote`, `riskScore`, `apiCredential` hoặc quan hệ nội bộ, các property đó có thể bị công bố ngoài dự kiến.

Entity còn có thể chứa các getter dẫn tới quan hệ lazy, collection lớn hoặc quan hệ hai chiều. Việc tuần tự hóa có thể kích hoạt truy cập dữ liệu, gây truy vấn ngoài dự kiến, vòng tham chiếu hoặc cấu trúc response không ổn định. Đây là một lý do nữa để xác định hợp đồng response độc lập với mô hình persistence.

### 7.1. Dùng DTO response theo nguyên tắc allowlist

Một cách rõ ràng là tạo DTO chỉ chứa dữ liệu được phép công bố:

```java
public record AccountResponse(
        long id,
        String username,
        boolean active
) {
    public static AccountResponse from(Account account) {
        return new AccountResponse(
                account.getId(),
                account.getUsername(),
                account.isActive()
        );
    }
}
```

Controller trả DTO:

```java
@GetMapping("/accounts/{id}")
public AccountResponse getAccount(@PathVariable long id) {
    Account account = accountService.findById(id);
    return AccountResponse.from(account);
}
```

DTO này chỉ có ba thành phần `id`, `username` và `active`. `passwordHash`, token, quan hệ nội bộ hoặc thuộc tính mới được thêm vào entity không tự động xuất hiện trong response. Đây là mô hình allowlist: chỉ những dữ liệu được chủ động chọn mới trở thành hợp đồng JSON.

### 7.2. Tách request DTO và response DTO

Không nên tái sử dụng một lớp có tất cả trường cho cả request lẫn response nếu hai chiều có quyền truy cập khác nhau. Ví dụ:

```java
public record RegisterAccountRequest(
        String username,
        String password
) {
}

public record AccountResponse(
        long id,
        String username,
        boolean active
) {
}
```

Request chứa mật khẩu do client gửi; response chỉ chứa thông tin công khai. Khi tạo tài khoản, service phải xử lý và băm mật khẩu trước khi lưu. Không trả lại mật khẩu thô hoặc hash trong response.

## 8. Các cơ chế khác và giới hạn bảo mật

### 8.1. `@JsonView`

`@JsonView` cho phép chọn nhóm property được xuất trong một lần tuần tự hóa. Cơ chế này hữu ích khi một kiểu có một số góc nhìn JSON được xác định trước. Tuy nhiên, view chỉ là cơ chế định hình dữ liệu. Nếu controller hoặc cấu hình chọn nhầm view, property nội bộ vẫn có thể bị xuất. Không dùng view thay cho kiểm tra quyền truy cập hoặc thiết kế DTO an toàn.

### 8.2. `@JsonFilter`

Filter cho phép loại property động tại thời điểm ghi. Cơ chế này phù hợp khi danh sách property cần xuất được quyết định bởi ngữ cảnh hợp lệ. Phải kiểm soát nơi tạo filter và danh sách field được phép; filter loại trừ theo danh sách denylist có thể bỏ sót một field nhạy cảm mới được thêm vào model.

### 8.3. Mix-in annotation

Nếu không thể sửa lớp từ thư viện bên ngoài, Jackson hỗ trợ mix-in annotation để gắn quy tắc như `@JsonIgnore` vào kiểu đó thông qua cấu hình mapper. Mix-in hữu ích để điều chỉnh cách tuần tự hóa một kiểu bên thứ ba, nhưng vẫn cần kiểm tra rằng mix-in được áp dụng trên đúng mapper đang dùng để tạo response.

## 9. Getter có thể có tác dụng phụ

Serializer thường gọi getter để lấy giá trị property. Vì vậy, getter không nên thực hiện truy vấn cơ sở dữ liệu, gọi dịch vụ mạng, thay đổi trạng thái hoặc thực hiện một thao tác tốn kém bất ngờ.

Ví dụ getter sau vừa có nguy cơ lộ dữ liệu vừa tạo tác dụng phụ:

```java
public String getInternalToken() {
    auditService.recordTokenAccess();
    return tokenRepository.loadCurrentToken(id);
}
```

Nếu Jackson gọi getter trong lúc ghi response, việc tuần tự hóa có thể kích hoạt thao tác audit và truy vấn. Điều này khiến hành vi tạo JSON khó dự đoán và có thể làm tăng độ trễ. Dữ liệu cần xuất nên được chuẩn bị rõ ràng ở tầng service, sau đó đưa vào DTO có getter đơn giản.

## 10. Bảo vệ bằng kiểm thử hợp đồng JSON

Một lớp có thể an toàn hôm nay nhưng bị lộ dữ liệu sau này khi developer thêm getter hoặc annotation mới. Vì vậy, response JSON quan trọng nên có kiểm thử xác nhận các property công khai và khẳng định các property nhạy cảm không xuất hiện.

Ví dụ kiểm thử với JUnit và Jackson:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class AccountResponseTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void responseContainsOnlyPublicAccountFields() throws Exception {
        AccountResponse response = new AccountResponse(10L, "minh", true);

        JsonNode json = mapper.readTree(mapper.writeValueAsString(response));

        assertEquals(10L, json.get("id").asLong());
        assertEquals("minh", json.get("username").asText());
        assertTrue(json.get("active").asBoolean());
        assertFalse(json.has("passwordHash"));
        assertFalse(json.has("internalToken"));
    }
}
```

Ngoài việc kiểm tra property cần có, nên kiểm tra rõ những tên nhạy cảm không được xuất. Với API có nhiều vai trò người dùng, hãy kiểm thử từng loại response theo quyền và hợp đồng tương ứng. Kiểm thử JSON là lớp bảo vệ bổ sung; nó không thay thế authorization ở service/controller.

## 11. Chọn cơ chế nào?

| Tình huống | Cơ chế phù hợp |
|---|---|
| Một property không được xuất hoặc nhận qua JSON | `@JsonIgnore` |
| Chỉ nhận dữ liệu đầu vào, không bao giờ xuất property | `@JsonProperty(access = WRITE_ONLY)` |
| Property chỉ do server tạo và chỉ xuất ra | `@JsonProperty(access = READ_ONLY)` |
| Một số property cố định cần bỏ qua ở cấp lớp | `@JsonIgnoreProperties` |
| Muốn tắt tự động nhận diện getter/field cho một lớp | `@JsonAutoDetect` với visibility tường minh |
| Một DTO có nhiều góc nhìn được kiểm soát | `@JsonView`, kèm kiểm soát view ở nơi gọi |
| Cần lọc property động | `@JsonFilter` với allowlist được kiểm soát |
| Không sở hữu mã nguồn kiểu bên thứ ba | Mix-in annotation |
| Entity chứa nhiều dữ liệu nội bộ, response cần hợp đồng riêng | DTO response theo allowlist |

Đừng xem getter `public` là một chi tiết Java thuần túy khi đối tượng được Jackson tuần tự hóa. Getter có thể trở thành một phần của hợp đồng JSON, kể cả khi field nền là `private`. Với dữ liệu nhạy cảm, hãy xác định rõ property được phép xuất, dùng annotation phù hợp khi cần, và ưu tiên DTO response chỉ chứa dữ liệu công khai. Kiểm thử JSON đầu ra giúp phát hiện việc một getter mới vô tình mở rộng hợp đồng dữ liệu trước khi thay đổi đó đến người dùng API.
