# Bỏ qua thuộc tính bằng JsonIgnore và JsonIgnoreProperties

Khi Jackson ánh xạ Java object sang JSON hoặc đọc JSON thành Java object, nó tìm các property phù hợp theo quy tắc nhận diện field, getter, setter, constructor và record component. Trong một số hợp đồng dữ liệu, ứng dụng cần loại một số property khỏi quá trình mapping. Ví dụ: không xuất `passwordHash` trong response, không nhận một trường do client gửi lên, hoặc bỏ qua field mới mà một hệ thống bên ngoài vừa bổ sung.

Jackson cung cấp hai annotation thường dùng cho việc này:

- **`@JsonIgnore`**: đánh dấu một property cụ thể cần bị bỏ qua.
- **`@JsonIgnoreProperties`**: khai báo danh sách property cần bỏ qua hoặc quy tắc bỏ qua property không được nhận diện trên một kiểu.

Hai annotation có mục đích gần nhau nhưng phạm vi và cách cấu hình khác nhau. Chọn đúng annotation giúp hợp đồng JSON rõ ràng, tránh vô tình làm lộ dữ liệu và tránh khiến ứng dụng từ chối payload chỉ vì có field mở rộng.

## 1. Jackson nhận diện property như thế nào?

Trước khi bỏ qua property, cần hiểu Jackson nhìn thấy dữ liệu Java theo một **logical property**. Một property có thể được nhận diện qua:

- Field, kể cả field không public nếu annotation và visibility cho phép.
- Getter, ví dụ `getUsername()`.
- Setter, ví dụ `setUsername(...)`.
- Constructor parameter hoặc factory method được Jackson nhận diện.
- Record component và accessor tương ứng.

Ví dụ một JavaBean:

```java
public class UserDto {
    private long id;
    private String username;
    private String passwordHash;

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public void setPasswordHash(String passwordHash) {
        this.passwordHash = passwordHash;
    }
}
```

Jackson thường xem `passwordHash` là một property logic dù nó xuất hiện ở field, getter và setter. Khi annotation được đặt trên một thành phần của property, Jackson có thể hợp nhất metadata từ những thành phần còn lại theo quy tắc introspection.

Vì vậy, khi bỏ qua một property, hãy nghĩ đến toàn bộ property logic thay vì chỉ nghĩ đến một dòng field. Nếu đặt annotation không đúng vị trí hoặc khai báo annotation xung đột trên getter/setter/field, kết quả có thể khó hiểu.

## 2. Bỏ qua một property bằng @JsonIgnore

`@JsonIgnore` là annotation đơn giản nhất khi muốn loại một property khỏi quá trình Jackson mapping.

Ví dụ:

```java
public class UserDto {
    private long id;
    private String username;

    @JsonIgnore
    private String passwordHash;

    // Constructors, getters and setters...
}
```

Khi serialize một `UserDto`, property `passwordHash` không được ghi vào JSON. Khi deserialize, Jackson cũng bỏ qua property này theo hành vi mặc định của annotation.

### 2.1. Bỏ qua khi serialize

Giả sử object có dữ liệu:

```java
UserDto user = new UserDto();
user.setId(10L);
user.setUsername("an");
user.setPasswordHash("hashed-secret");

String json = mapper.writeValueAsString(user);
```

JSON được ghi ra có dạng:

```json
{
  "id": 10,
  "username": "an"
}
```

`passwordHash` vẫn tồn tại trong object Java, nhưng không xuất hiện trong JSON do Jackson tạo ra.

Điều này hữu ích với dữ liệu nội bộ không nên được gửi trong response, chẳng hạn hash mật khẩu, ghi chú quản trị hoặc thông tin triển khai riêng.

### 2.2. Bỏ qua khi deserialize

`@JsonIgnore` cũng khiến Jackson bỏ qua property tương ứng khi đọc JSON:

```json
{
  "id": 10,
  "username": "an",
  "passwordHash": "attacker-supplied-value"
}
```

Nếu `passwordHash` được đánh dấu `@JsonIgnore`, giá trị do client gửi lên không được gán vào property đó thông qua Jackson. Với JavaBean được khởi tạo thông thường, property sẽ giữ giá trị ban đầu của nó.

Điều này có thể ngăn client tự gán một trường nội bộ qua request binding. Tuy nhiên, không nên xem annotation là cơ chế phân quyền hoặc validation tổng quát. Logic nghiệp vụ vẫn phải kiểm tra dữ liệu và quyền của người dùng.

### 2.3. Đặt @JsonIgnore trên field, getter hoặc accessor

Có thể đặt annotation trên thành phần mà Jackson nhận diện:

```java
public class AccountDto {
    private String username;
    private String secret;

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    @JsonIgnore
    public String getSecret() {
        return secret;
    }

    public void setSecret(String secret) {
        this.secret = secret;
    }
}
```

Ở đây, getter `getSecret()` là một phần của property `secret`. Khi Jackson hợp nhất property metadata, `secret` được xem là property cần bỏ qua. Đừng giả định setter còn lại sẽ tự động khiến property được deserialize; `@JsonIgnore` thông thường bỏ qua property theo cả hai chiều.

Để code dễ đọc và tránh annotation phân tán, nên đặt annotation ở một vị trí nhất quán theo convention của dự án. Khi một property có field, getter và setter, hãy kiểm thử cả serialize lẫn deserialize.

### 2.4. Dùng với record

Record cũng có thể khai báo annotation trên component:

```java
public record UserResponse(
    long id,
    String username,
    @JsonIgnore String passwordHash
) {}
```

Khi serialize, Jackson bỏ qua component `passwordHash`. Khi deserialize, property JSON cùng tên cũng bị bỏ qua theo quy tắc ignore. Vì record được tạo qua canonical constructor, component bị bỏ qua không được lấy giá trị từ property JSON đó; kết quả cụ thể còn chịu ảnh hưởng của kiểu component và các feature xử lý giá trị thiếu/null.

Nếu component là dữ liệu bắt buộc để tạo một record hợp lệ, đừng bỏ qua nó một cách tùy tiện. Hãy xác định rõ dữ liệu đó có thực sự thuộc hợp đồng JSON hay không.

## 3. Bỏ qua nhiều property bằng @JsonIgnoreProperties

Khi cần bỏ qua một danh sách property trên một kiểu, dùng `@JsonIgnoreProperties`.

Ví dụ:

```java
@JsonIgnoreProperties({
    "passwordHash",
    "internalNote",
    "legacyCode"
})
public class UserResponse {
    private long id;
    private String username;
    private String passwordHash;
    private String internalNote;
    private String legacyCode;

    // Getters and setters...
}
```

Các tên trong danh sách `value` là tên property Jackson nhận diện, thường là tên JSON sau khi áp dụng naming strategy và annotation liên quan. Khi serialize, các property này không được ghi. Khi deserialize, chúng bị bỏ qua.

Dạng khai báo tường minh tương đương:

```java
@JsonIgnoreProperties(
    value = {"passwordHash", "internalNote", "legacyCode"}
)
public class UserResponse {
    // ...
}
```

Dùng `@JsonIgnoreProperties` khi một kiểu có một nhóm property luôn cần loại khỏi JSON. Với chỉ một property, `@JsonIgnore` thường dễ đọc hơn.

### 3.1. Bỏ qua property đã biết và không muốn xuất hiện

Giả sử response nội bộ có thêm thông tin:

```java
@JsonIgnoreProperties({"passwordHash", "adminComment"})
public class AccountResponse {
    private long id;
    private String username;
    private String passwordHash;
    private String adminComment;

    // Getters and setters...
}
```

Khi ghi JSON, client chỉ nhận các property được phép xuất hiện theo cấu hình còn lại. Khi đọc JSON, hai property được liệt kê cũng không được Jackson gán từ input.

Đây là quy tắc ở cấp kiểu. Mọi thao tác mapping kiểu đó đều chịu ảnh hưởng của annotation, trừ khi có cấu hình hoặc mix-in khác điều chỉnh metadata.

### 3.2. Bỏ qua các property không được nhận diện với ignoreUnknown

Một nhu cầu khác là đọc payload từ hệ thống bên ngoài. Hệ thống đó có thể bổ sung field mới mà ứng dụng hiện tại chưa sử dụng.

Ví dụ payload:

```json
{
  "eventId": "evt-100",
  "eventType": "USER_CREATED",
  "source": "identity-service",
  "traceContext": {
    "traceId": "abc-123"
  }
}
```

Ứng dụng chỉ cần `eventId` và `eventType`:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public class IncomingEvent {
    private String eventId;
    private String eventType;

    // Getters and setters...
}
```

Với `ignoreUnknown = true`, Jackson bỏ qua property không có trong mô hình Java khi deserialize `IncomingEvent`. Ví dụ trên có thể được đọc dù DTO không khai báo `source` và `traceContext`.

Điều này hữu ích cho tích hợp cần khả năng tương thích tiến: producer thêm field mới nhưng consumer cũ vẫn đọc được phần dữ liệu mà nó hiểu.

`ignoreUnknown = true` không có nghĩa là bỏ qua tất cả property. Các property đã biết vẫn được ánh xạ bình thường; chỉ tên property không được nhận diện mới bị bỏ qua trong quá trình đọc.

Nó cũng không sửa được JSON sai cú pháp, không biến object thành array, không bỏ qua lỗi kiểu dữ liệu của một property đã biết và không thay thế validation nghiệp vụ.

### 3.3. Kết hợp danh sách ignore và ignoreUnknown

Hai mục đích có thể được khai báo cùng lúc:

```java
@JsonIgnoreProperties(
    value = {"internalToken", "debugInfo"},
    ignoreUnknown = true
)
public class PartnerEvent {
    private String id;
    private String eventType;

    // Getters and setters...
}
```

Ý nghĩa:

- `internalToken` và `debugInfo` là property đã biết nhưng được yêu cầu bỏ qua.
- Những property khác mà class không nhận diện cũng được bỏ qua khi deserialize.
- Các property đã biết còn lại vẫn được đọc/ghi theo quy tắc mapping bình thường.

Hãy cân nhắc kỹ khi bật `ignoreUnknown`. Với một API nội bộ có schema chặt, việc từ chối field lạ có thể giúp phát hiện producer gửi sai tên hoặc sai hợp đồng. Với consumer cần chịu được field mở rộng từ bên ngoài, bỏ qua unknown property có thể phù hợp hơn.

## 4. Điều khiển riêng chiều đọc và chiều ghi

Mặc định, các property nằm trong `@JsonIgnore` hoặc danh sách `value` của `@JsonIgnoreProperties` bị bỏ qua ở cả hai chiều. Tuy nhiên, một số API cần hành vi một chiều.

`@JsonIgnoreProperties` cung cấp hai tùy chọn:

- `allowGetters = true`: cho phép getter của các property được liệt kê tham gia serialize; các property đó vẫn bị bỏ qua khi deserialize.
- `allowSetters = true`: cho phép setter của các property được liệt kê tham gia deserialize; các property đó vẫn bị bỏ qua khi serialize.

Bảng ghi nhớ:

| Cấu hình | Serialize Java → JSON | Deserialize JSON → Java |
| --- | --- | --- |
| `value = {"secret"}` | Bỏ qua `secret` | Bỏ qua `secret` |
| `value = {"secret"}, allowGetters = true` | Cho phép ghi `secret` qua getter | Bỏ qua `secret` |
| `value = {"secret"}, allowSetters = true` | Bỏ qua `secret` | Cho phép gán `secret` qua setter |
| `ignoreUnknown = true` | Không quyết định việc ghi property đã biết | Bỏ qua tên property không được nhận diện |

### 4.1. allowGetters: chỉ đọc ra JSON

Một trường hợp là server muốn trả về một property nhưng không muốn nhận giá trị do client gửi:

```java
@JsonIgnoreProperties(
    value = {"status"},
    allowGetters = true
)
public class AccountResponse {
    private long id;
    private String status;

    public long getId() {
        return id;
    }

    public void setId(long id) {
        this.id = id;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
```

Với cấu hình trên:

- Khi serialize, getter `getStatus()` được phép cung cấp giá trị ra JSON.
- Khi deserialize, `status` vẫn bị bỏ qua; input không thể gán property này qua Jackson.

Đây là cách biểu diễn một property theo hướng server cung cấp. Tuy nhiên, nếu đây là API response, DTO response riêng thường thể hiện ý định rõ ràng hơn.

### 4.2. allowSetters: chỉ nhận từ JSON

Một trường hợp khác là ứng dụng nhận một giá trị từ client nhưng không muốn gửi ngược giá trị đó trong response:

```java
@JsonIgnoreProperties(
    value = {"password"},
    allowSetters = true
)
public class RegistrationRequest {
    private String username;
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

Với cấu hình này, `password` được nhận khi deserialize qua setter nhưng không được serialize ra JSON qua getter.

Đối với trường hợp chỉ cần kiểm soát một chiều, `@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)` hoặc `READ_ONLY` thường diễn đạt trực tiếp ý nghĩa truy cập của property. Hãy chọn một quy ước nhất quán trong dự án và test cả hai chiều.

### 4.3. Phân biệt với @JsonIgnore

Không nên đặt `@JsonIgnore` lên property rồi kỳ vọng `allowGetters` hoặc `allowSetters` của một annotation khác luôn khôi phục được chiều mapping. Các annotation trên cùng logical property có thể tương tác theo quy tắc hợp nhất metadata của Jackson.

Nếu cần read-only hoặc write-only, ưu tiên cấu hình tường minh cho chính property, chẳng hạn `@JsonProperty(access = ...)`, hoặc dùng `@JsonIgnoreProperties` với danh sách property và tùy chọn tương ứng. Sau đó viết test để xác nhận hành vi thực tế.

## 5. So sánh hai annotation

| Tiêu chí | `@JsonIgnore` | `@JsonIgnoreProperties` |
| --- | --- | --- |
| Phạm vi điển hình | Một property cụ thể | Một hoặc nhiều property trên kiểu |
| Khai báo danh sách | Không | Có `value` |
| Bỏ qua unknown property | Không phải mục đích của annotation này | Có `ignoreUnknown = true` |
| Điều khiển getter/setter theo danh sách | Không có thuộc tính tương ứng | Có `allowGetters`, `allowSetters` |
| Vị trí thường dùng | Field, getter, setter, record component | Class/type, property hoặc mix-in tùy mục đích |
| Trường hợp phù hợp | Một giá trị nhạy cảm hoặc nội bộ | Một nhóm property hoặc payload mở rộng |

Quy tắc chọn nhanh:

- Một property luôn bị bỏ qua: dùng `@JsonIgnore`.
- Nhiều property đã biết cần bị bỏ qua: dùng `@JsonIgnoreProperties(value = {...})`.
- Consumer cần bỏ qua field mới chưa biết: dùng `@JsonIgnoreProperties(ignoreUnknown = true)` ở kiểu phù hợp.
- Cần chỉ đọc hoặc chỉ ghi: cân nhắc `allowGetters`, `allowSetters` hoặc `@JsonProperty(access = ...)`.

Không nên gắn `ignoreUnknown = true` lên mọi DTO chỉ để làm các test hiện tại chạy qua. Field lạ có thể là dấu hiệu client gửi sai tên property hoặc producer thay đổi hợp đồng ngoài dự kiến.

## 6. Bỏ qua property của class bên thứ ba bằng Mix-in

Có lúc không thể sửa class nguồn, ví dụ class đến từ thư viện hoặc generated model. Jackson Mix-in cho phép bổ sung annotation từ bên ngoài.

Giả sử class thư viện:

```java
public class ExternalAccount {
    public String getUsername() {
        // ...
        return "an";
    }

    public String getApiSecret() {
        // ...
        return "secret";
    }
}
```

Tạo Mix-in có method tương ứng và đánh dấu property cần bỏ qua:

```java
abstract class ExternalAccountMixin {

    @JsonIgnore
    abstract String getApiSecret();
}
```

Đăng ký Mix-in với mapper:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(ExternalAccount.class, ExternalAccountMixin.class);
```

Jackson áp dụng annotation từ Mix-in khi introspect `ExternalAccount`, dù source class không bị sửa. Đây là cách hữu ích để tùy chỉnh serialization của kiểu bên ngoài.

Mix-in cần khớp đúng member cần cấu hình: tên method, kiểu trả về và chữ ký tham số. Hãy kiểm thử mapper đã đăng ký Mix-in; Mix-in chỉ áp dụng cho mapper có cấu hình đó, không tự động tác động tới mọi `ObjectMapper` trong ứng dụng.

Nếu đang dùng Spring Boot, hãy đăng ký Mix-in trên mapper bean thông qua cơ chế cấu hình phù hợp thay vì tạo mapper mới ở một nơi rồi mong mapper HTTP tự nhận cấu hình đó.

## 7. Ảnh hưởng tới dữ liệu đầu vào và bảo mật

Bỏ qua property có thể giúp kiểm soát payload, nhưng cần hiểu đúng giới hạn:

### 7.1. Không xuất dữ liệu nhạy cảm

`@JsonIgnore` hoặc `@JsonIgnoreProperties` có thể ngăn Jackson đưa property vào JSON được serialize. Tuy nhiên, dữ liệu vẫn có thể xuất hiện ở nơi khác như:

- Log do ứng dụng tự ghi.
- Exception message hoặc debug output.
- DTO khác hoặc endpoint khác.
- Mapping thủ công sang Map.
- Serialization bởi thư viện khác.
- Database, message queue hoặc event payload riêng.

Vì vậy, với dữ liệu nhạy cảm như password, access token, secret key hoặc thông tin riêng tư, hãy thiết kế DTO response chỉ chứa những trường được phép công khai. Annotation ignore là lớp kiểm soát bổ sung, không phải chính sách bảo mật toàn hệ thống.

### 7.2. Không cho client tự gán trường nội bộ

Nếu một request DTO chứa `role`, `isAdmin`, `balance` hoặc `status` do server quản lý, việc bỏ qua property có thể ngăn Jackson bind giá trị từ input. Nhưng an toàn hơn thường là không đưa các trường đó vào request DTO ngay từ đầu.

Ví dụ:

```java
public record CreateUserRequest(
    String username,
    String email
) {}
```

Server tự quyết định role mặc định, trạng thái và các trường quản trị. Cách này giảm nguy cơ mass assignment và làm hợp đồng API dễ hiểu hơn.

### 7.3. ignoreUnknown không phải validation

Khi bật `ignoreUnknown = true`, một payload có thể chứa field lạ mà ứng dụng bỏ qua. Điều này không chứng minh payload hợp lệ về nghiệp vụ. Các field đã biết vẫn cần kiểm tra:

- Có bắt buộc không?
- Có null được không?
- Có đúng kiểu không?
- Có nằm trong miền giá trị cho phép không?
- Người gửi có quyền cung cấp giá trị đó không?

Jackson giải quyết parsing và binding; validation và authorization thuộc các lớp xử lý tiếp theo.

## 8. Những khác biệt cần phân biệt

### 8.1. Ignored property và unknown property

Hai khái niệm này không giống nhau:

| Khái niệm | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Ignored property | DTO có `passwordHash`, nhưng được đánh dấu ignore | Jackson biết property đó và bỏ qua theo annotation |
| Unknown property | JSON có `futureField`, DTO không có property tương ứng | Có thể báo lỗi hoặc bỏ qua theo cấu hình/`ignoreUnknown` |
| Missing property | DTO có `username`, JSON không gửi field này | Jackson xử lý như property không có giá trị đầu vào; kết quả tùy kiểu và cấu hình |
| Explicit null | JSON có `"username": null` | Jackson nhận diện property và giá trị null; xử lý tùy kiểu/cấu hình |

Đặc biệt, `@JsonIgnoreProperties(value = {"passwordHash"})` và `@JsonIgnoreProperties(ignoreUnknown = true)` giải quyết hai tình huống khác nhau. Có thể kết hợp chúng nhưng không nên dùng thay thế cho nhau.

### 8.2. Ignore property và bỏ qua cả kiểu

`@JsonIgnore` và `@JsonIgnoreProperties` điều khiển property. Chúng không có nghĩa là bỏ qua toàn bộ class hoặc mọi object lồng nhau cùng kiểu.

Nếu cần bỏ qua một kiểu hoàn toàn, Jackson có cơ chế khác như `@JsonIgnoreType`. Đây là một annotation riêng và không nên nhầm lẫn với bài học hiện tại.

### 8.3. Ignore property và bỏ qua lỗi parse

Một JSON không hợp lệ vẫn có thể thất bại trước khi Jackson xác định property nào cần ignore. Ví dụ:

```json
{
  "username": "an",
  "passwordHash":
}
```

Payload trên sai cú pháp vì thiếu giá trị sau dấu hai chấm. Dù `passwordHash` được ignore, parser vẫn không thể đọc một JSON document hợp lệ.

Tương tự, nếu một property đã biết có kiểu không tương thích, `ignoreUnknown = true` không tự động bỏ qua lỗi đó. Nó chỉ xử lý property không được nhận diện.

## 9. Kiểm thử hành vi của annotation

Đừng chỉ kiểm tra JSON output có thiếu field. Cần test cả chiều deserialize, unknown property và cấu hình một chiều.

### 9.1. Test @JsonIgnore ở cả hai chiều

Với DTO có `passwordHash` được đánh dấu `@JsonIgnore`:

```java
@Test
void ignoredPropertyIsNotWritten() throws Exception {
    UserDto user = new UserDto();
    user.setId(10L);
    user.setUsername("an");
    user.setPasswordHash("hash-value");

    String json = mapper.writeValueAsString(user);

    assertFalse(json.contains("passwordHash"));
    assertFalse(json.contains("hash-value"));
}
```

Kiểm tra chiều đọc:

```java
@Test
void ignoredPropertyIsNotRead() throws Exception {
    String json = """
        {
          "id": 10,
          "username": "an",
          "passwordHash": "client-value"
        }
        """;

    UserDto user = mapper.readValue(json, UserDto.class);

    assertEquals(10L, user.getId());
    assertEquals("an", user.getUsername());
    assertNull(user.getPasswordHash());
}
```

Test này xác nhận property không được gán qua Jackson. Nếu object có constructor hoặc giá trị khởi tạo khác null, hãy assert đúng trạng thái mặc định theo thiết kế class.

### 9.2. Test bỏ qua unknown property

Với class được đánh dấu `@JsonIgnoreProperties(ignoreUnknown = true)`:

```java
@Test
void ignoresUnknownProperties() throws Exception {
    String json = """
        {
          "eventId": "evt-100",
          "eventType": "USER_CREATED",
          "newFieldFromProducer": "future-value"
        }
        """;

    IncomingEvent event = mapper.readValue(json, IncomingEvent.class);

    assertEquals("evt-100", event.getEventId());
    assertEquals("USER_CREATED", event.getEventType());
}
```

Nếu muốn kiểm tra sự khác biệt, tạo một DTO không có `ignoreUnknown` và dùng mapper bật `FAIL_ON_UNKNOWN_PROPERTIES`. Khi payload có field lạ, Jackson sẽ báo lỗi tương ứng. Hãy cấu hình test rõ ràng để kết quả không phụ thuộc cấu hình mặc định của framework.

### 9.3. Test chiều getter/setter

Với `allowGetters` hoặc `allowSetters`, kiểm tra hai hướng độc lập:

- Serialize object có giá trị property và xác nhận JSON có hoặc không có field theo ý định.
- Deserialize JSON có field đó và xác nhận property Java được hoặc không được gán.

Không chỉ dựa vào tên tùy chọn để suy luận hành vi; một test nhỏ sẽ xác nhận cấu hình đang chạy trên phiên bản Jackson thực tế.

## 10. Lưu ý khi dùng trong Spring Boot

Spring Boot thường cấu hình `ObjectMapper` và `MappingJackson2HttpMessageConverter` cho request/response JSON. Annotation trên DTO được áp dụng khi converter sử dụng mapper đó.

Một số lưu ý:

1. Dùng DTO request và response riêng khi hai chiều có chính sách field khác nhau.
2. Kiểm tra mapper bean thực tế nếu dự án có customizer, mix-in hoặc module riêng.
3. Không tạo một `ObjectMapper` mới trong test rồi kết luận endpoint HTTP sẽ có cùng hành vi.
4. Test request có field bị ignore và response không được chứa field nhạy cảm.
5. Kiểm tra Content-Type và body thực tế khi endpoint trả scalar hoặc collection.
6. Với payload từ đối tác, quyết định rõ có bật `ignoreUnknown` theo từng DTO hay không.

Ví dụ, request có thể cần nhận `password` để đăng ký, nhưng response tuyệt đối không trả lại password. Dùng DTO riêng cho hai mục đích:

```java
public record RegisterUserRequest(
    String username,
    String password
) {}

public record UserResponse(
    long id,
    String username
) {}
```

Cách này rõ ràng hơn việc dùng chung một class rồi cố gắng điều khiển nhiều hướng bằng các annotation ignore phức tạp.

## 11. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Field vẫn xuất hiện trong JSON | Annotation đặt sai member, mapper không dùng metadata mong đợi hoặc có cấu hình khác | Kiểm tra logical property, getter/field và mapper thực tế |
| Field vẫn được gán khi đọc JSON | Property chưa thực sự bị ignore hoặc annotation xung đột | Viết test deserialize và xem metadata của property |
| ignoreUnknown = true không bỏ qua lỗi | Field đã biết nhưng sai kiểu, JSON sai cú pháp hoặc lỗi không phải unknown property | Đọc exception và token/path gây lỗi |
| Bật allowGetters nhưng field không xuất hiện | Không có getter/visibility phù hợp hoặc property name không khớp | Kiểm tra getter và tên property sau naming strategy |
| Bật allowSetters nhưng field không được gán | Không có setter/creator phù hợp hoặc kiểu dữ liệu không hợp lệ | Kiểm tra setter, constructor và payload |
| Test unit chạy nhưng endpoint vẫn lộ field | Test dùng mapper khác mapper của Spring | Test qua HTTP với Spring context |
| Property bị mất sau deserialize record | Component bị ignore hoặc thiếu giá trị đầu vào | Kiểm tra canonical constructor và kiểu component |

Khi debug, xác định đúng chiều xảy ra vấn đề: serialize hay deserialize. Sau đó kiểm tra tên property logic, annotation trên field/getter/setter/record component, mapper đang dùng và cấu hình feature liên quan.

## 12. Bài thực hành tổng hợp

Xây dựng hai DTO cho chức năng quản lý tài khoản:

- Request nhận `username`, `password` và một số thông tin đăng ký.
- Response chỉ trả `id`, `username` và `status`.

Thực hiện:

1. Tạo class JavaBean có property `passwordHash`; đặt `@JsonIgnore` và kiểm tra JSON output.
2. Gửi JSON có `passwordHash` vào class đó và xác nhận Jackson không gán giá trị.
3. Tạo một class sự kiện có `@JsonIgnoreProperties(ignoreUnknown = true)` và đọc payload có field mới.
4. Tạo một class khác có danh sách property trong `value` để bỏ qua các field nội bộ.
5. Thử `allowGetters = true` để property được ghi ra JSON nhưng không được đọc từ input.
6. Thử `allowSetters = true` để property được đọc từ input nhưng không được ghi ra JSON.
7. Đăng ký Mix-in để ignore một getter của class bên thứ ba.
8. Viết test cho cả serialize và deserialize, bao gồm unknown field và field sai kiểu.
9. Tạo request/response DTO riêng và so sánh độ rõ ràng với cách dùng một DTO chung.
10. Ghi lại những field nào được phép client gửi, field nào server sở hữu và field nào được phép xuất hiện trong response.

Bài thực hành hoàn thành khi có thể giải thích chính xác mỗi annotation tác động lên property nào, ở chiều nào và trong phạm vi mapper/kiểu dữ liệu nào.

## 13. Nguyên tắc ghi nhớ

- `@JsonIgnore` bỏ qua một property theo mặc định ở cả serialize và deserialize.
- `@JsonIgnoreProperties(value = {...})` bỏ qua một danh sách property đã biết.
- `@JsonIgnoreProperties(ignoreUnknown = true)` cho phép bỏ qua property không được nhận diện khi deserialize.
- `allowGetters = true` cho phép serialize property nằm trong danh sách ignore.
- `allowSetters = true` cho phép deserialize property nằm trong danh sách ignore.
- Ignored property khác unknown property, missing property và explicit null.
- Annotation ignore không sửa JSON sai cú pháp và không thay thế validation/authorization.
- Dùng Mix-in khi không thể sửa class nguồn.
- Không xem ignore annotation là chính sách bảo mật toàn hệ thống; ưu tiên DTO có field được phép công khai.
- Kiểm thử cả hai chiều trên `ObjectMapper` thực tế, đặc biệt khi chạy trong Spring Boot.

Khi quyết định bỏ qua property, hãy xác định property đó cần bị loại ở chiều nào, là property đã biết hay field mở rộng chưa biết, rồi chọn annotation có phạm vi hẹp và dễ kiểm thử nhất.
