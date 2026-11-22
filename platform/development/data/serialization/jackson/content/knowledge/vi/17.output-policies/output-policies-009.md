# Ẩn dữ liệu nhạy cảm theo chính sách rõ ràng

Khi Jackson chuyển object Java thành JSON, mọi property mà serializer nhận diện được đều có khả năng xuất hiện trong output nếu không có cấu hình giới hạn. Điều này đặc biệt quan trọng với dữ liệu nhạy cảm như mật khẩu, token, khóa API, số giấy tờ, thông tin thanh toán, dữ liệu cá nhân hoặc thuộc tính nội bộ chỉ phục vụ xử lý phía server.

Ẩn dữ liệu nhạy cảm không nên là một thao tác tùy hứng tại nơi gọi `writeValueAsString()`. Ứng dụng cần có chính sách rõ ràng: dữ liệu nào được phép xuất hiện trong từng loại output, dữ liệu nào chỉ được nhận ở input, dữ liệu nào phải bị loại bỏ hoàn toàn và dữ liệu nào chỉ được hiển thị dưới dạng đã che một phần.

Jackson cung cấp nhiều cơ chế để thực hiện chính sách đó: `@JsonIgnore`, `@JsonProperty(access = ...)`, `@JsonIgnoreProperties`, JSON Views, property filters và custom serializers. Với API công khai, cách an toàn và dễ kiểm soát thường là tạo DTO output chỉ chứa các field được phép công bố. Annotation và filter là công cụ bổ trợ cho các trường hợp có phạm vi rõ ràng.

Các ví dụ trong bài sử dụng Jackson 2.x với package `com.fasterxml.jackson`. Hãy áp dụng chính sách ở đúng ranh giới output và kiểm thử cả chiều serialize lẫn deserialize.

## 1. Xác định chính sách trước khi cấu hình Jackson

Trước khi chọn annotation hoặc filter, cần phân loại property theo mục đích sử dụng:

| Nhóm dữ liệu | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Bí mật tuyệt đối | Password, password hash, private key, refresh token | Không đưa vào response; tránh log; giới hạn quyền truy cập ở mọi tầng |
| Chỉ nhận từ client | Password mới, mã xác minh, thông tin đăng nhập | Cho phép deserialize khi cần, không serialize trở lại |
| Server quản lý | ID được cấp, trạng thái đã duyệt, quyền hạn do server quyết định | Có thể serialize ra output; bỏ qua hoặc từ chối giá trị client gửi vào |
| Dữ liệu cá nhân cần giới hạn | Email, số điện thoại, địa chỉ, ngày sinh | Chỉ trả về theo quyền và mục đích; có thể dùng DTO hoặc masking |
| Dữ liệu nội bộ | Ghi chú vận hành, cờ debug, thông tin kiểm toán nội bộ | Loại khỏi public output; chỉ đưa vào output nội bộ được cấp quyền |
| Dữ liệu công khai | Tên hiển thị, mã sản phẩm công khai, trạng thái hiển thị | Có thể đưa vào response theo hợp đồng API |

Một chính sách tốt trả lời được các câu hỏi:

1. Field có được nhận từ client không?
2. Field có được gửi lại cho client không?
3. Field có được xuất hiện trong log, file export, message queue hoặc cache không?
4. Có cần che một phần giá trị hay phải loại bỏ hoàn toàn?
5. Ai được phép nhận dữ liệu đầy đủ và quyết định quyền đó nằm ở tầng nào?

Không có một annotation nào tự thay thế được việc phân quyền. Jackson quyết định cách biểu diễn dữ liệu; authorization phải được thực hiện trước khi ứng dụng chọn dữ liệu để trả về.

## 2. Vì sao không nên serialize trực tiếp entity chứa bí mật?

Giả sử một entity lưu thông tin tài khoản:

```java
public class UserAccount {
    private Long id;
    private String username;
    private String passwordHash;
    private String refreshToken;
    private String email;
    private boolean admin;

    // getters và setters
}
```

Nếu gọi:

```java
String json = mapper.writeValueAsString(userAccount);
```

Jackson có thể ghi tất cả property mà nó phát hiện được. `passwordHash`, `refreshToken` hoặc `admin` có thể bị lộ dù API chỉ định trả về thông tin cơ bản.

Vấn đề còn lớn hơn khi entity thay đổi theo thời gian. Một developer thêm `recoveryCode` hoặc `internalNotes`; nếu controller vẫn serialize trực tiếp entity, field mới có thể tự động xuất hiện trong response mà không có quyết định công bố rõ ràng.

Với dữ liệu nhạy cảm, nên dùng nguyên tắc allowlist: chỉ những field được chọn rõ ràng mới được đưa vào output. DTO riêng giúp biến nguyên tắc đó thành cấu trúc code dễ đọc và dễ review.

## 3. Cách ưu tiên: tạo DTO output chỉ chứa field được phép

Thay vì trả entity trực tiếp, tạo response DTO:

```java
public record UserProfileResponse(
        Long id,
        String username,
        String displayName,
        String emailMasked) {
}
```

Application service hoặc mapper chuyển entity sang DTO sau khi xác định quyền truy cập:

```java
public UserProfileResponse toPublicResponse(UserAccount account) {
    return new UserProfileResponse(
            account.getId(),
            account.getUsername(),
            account.getDisplayName(),
            maskEmail(account.getEmail())
    );
}
```

Serialize DTO:

```java
String json = mapper.writeValueAsString(toPublicResponse(account));
```

Vì DTO không có `passwordHash`, `refreshToken` hoặc `admin`, các field đó không thể vô tình xuất hiện qua serialization mặc định của DTO.

### 3.1. Tách DTO theo từng mục đích output

Một hệ thống có thể cần nhiều hình thức trả dữ liệu:

```java
public record PublicUserResponse(
        Long id,
        String displayName) {
}

public record AdminUserResponse(
        Long id,
        String username,
        String email,
        boolean admin,
        String accountStatus) {
}
```

Service chỉ tạo `AdminUserResponse` sau khi kiểm tra người gọi có quyền quản trị. Không nên chọn DTO dựa vào một query parameter tùy ý mà không kiểm tra quyền.

DTO allowlist đặc biệt hữu ích cho:

- Public REST response.
- Message gửi sang hệ thống đối tác.
- File export cho người dùng.
- Event công bố qua message broker.
- Log hoặc audit record đã được giới hạn field.

Nếu cùng một entity phục vụ nhiều nhóm người nhận, các DTO khác nhau giúp thể hiện rõ hợp đồng dữ liệu cho từng nhóm.

## 4. Ẩn hoàn toàn property bằng `@JsonIgnore`

`@JsonIgnore` đánh dấu property không tham gia quá trình JSON binding thông thường. Annotation này thường loại property khỏi cả serialization và deserialization.

```java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class UserAccount {
    private Long id;
    private String username;

    @JsonIgnore
    private String passwordHash;

    // getters và setters
}
```

Khi serialize, `passwordHash` không xuất hiện. Khi deserialize, Jackson cũng bỏ qua property đó theo cấu hình annotation thông thường.

`@JsonIgnore` phù hợp với dữ liệu không được phép đi qua JSON ở cả hai chiều, ví dụ password hash lưu nội bộ hoặc khóa bí mật. Tuy nhiên, nếu cùng một lớp cần nhận password mới từ request nhưng tuyệt đối không trả password đó trong response, `@JsonIgnore` có thể quá mạnh; hãy dùng access direction hoặc DTO riêng.

### 4.1. Đặt annotation trên field, getter hoặc setter

Jackson tổng hợp property từ field, getter, setter và constructor parameter theo quy tắc introspection. Annotation có thể được đặt trên một trong các thành phần này, nhưng cần giữ metadata nhất quán.

Ví dụ:

```java
public class InternalProfile {
    private String apiSecret;

    @JsonIgnore
    public String getApiSecret() {
        return apiSecret;
    }

    public void setApiSecret(String apiSecret) {
        this.apiSecret = apiSecret;
    }
}
```

Với property có nhiều accessor, hãy kiểm tra metadata cuối cùng mà Jackson phát hiện được. Tránh đặt annotation mâu thuẫn trên field và getter/setter vì việc hợp nhất property có thể khó hiểu đối với người đọc code.

## 5. Điều khiển riêng chiều đọc và chiều ghi bằng `@JsonProperty(access = ...)`

Không phải property nào cũng cần bị ẩn ở cả hai chiều. Jackson cho phép khai báo hướng truy cập của property bằng `JsonProperty.Access`.

| Access | Deserialize JSON vào Java | Serialize Java ra JSON |
|---|---|---|
| `AUTO` | Theo quy tắc mặc định | Theo quy tắc mặc định |
| `READ_ONLY` | Không nhận giá trị từ JSON | Có thể xuất hiện trong JSON |
| `WRITE_ONLY` | Có thể nhận giá trị từ JSON | Không xuất hiện trong JSON |
| `READ_WRITE` | Đọc/ghi theo quy tắc thông thường | Đọc/ghi theo quy tắc thông thường |

Tên `READ_ONLY` và `WRITE_ONLY` được hiểu theo hướng nhìn từ phía Java property trong quá trình data binding: `READ_ONLY` có thể được Jackson đọc từ object để serialize; `WRITE_ONLY` có thể được ghi vào object khi deserialize.

### 5.1. Password chỉ nhận từ request, không trả về response

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

Khi deserialize:

```json
{
  "username": "an",
  "password": "client-supplied-secret"
}
```

Jackson có thể gán password vào object để service xử lý. Khi serialize lại object đó, field `password` bị loại khỏi output.

Đây là một cách hữu ích cho request model đơn giản, nhưng DTO request và response riêng vẫn thường rõ ràng hơn. Đặc biệt, không nên giữ plaintext password lâu hơn thời gian cần thiết hoặc log object request chỉ vì password được đánh dấu `WRITE_ONLY`.

### 5.2. ID do server cấp: trả ra nhưng không nhận giá trị client

```java
public class CreatedUserResponse {
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    private String username;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }
}
```

Khi serialize, `id` có thể được trả về. Khi deserialize, giá trị `id` do client gửi không được dùng để gán property này. Điều đó giúp tránh một số tình huống mass assignment, nhưng authorization và quy trình tạo entity vẫn phải được bảo vệ ở service/database.

### 5.3. Không dùng `WRITE_ONLY` như cơ chế phân quyền

`WRITE_ONLY` chỉ quyết định field có xuất hiện trong JSON output hay không. Nó không kiểm tra ai được phép gửi giá trị đó, không xác minh password và không bảo vệ dữ liệu trong bộ nhớ, database hoặc log. Nếu một field chỉ được phép cập nhật bởi quản trị viên, service vẫn phải kiểm tra quyền trước khi áp dụng giá trị.

## 6. Bỏ qua một nhóm property bằng `@JsonIgnoreProperties`

`@JsonIgnoreProperties` có thể bỏ qua một hoặc nhiều tên property ở cấp lớp:

```java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties({"passwordHash", "refreshToken", "internalNotes"})
public class UserAccount {
    private Long id;
    private String username;
    private String passwordHash;
    private String refreshToken;
    private String internalNotes;

    // getters và setters
}
```

Các property được liệt kê bị bỏ qua theo mặc định trong cả serialization và deserialization.

### 6.1. `allowGetters` và `allowSetters`

Hai thuộc tính này điều chỉnh ngoại lệ theo hướng truy cập:

- `allowGetters = true`: property được liệt kê không bị bỏ qua khi serialize qua getter, nhưng vẫn bị bỏ qua khi deserialize.
- `allowSetters = true`: property được liệt kê không bị bỏ qua khi deserialize qua setter, nhưng vẫn bị bỏ qua khi serialize.

Ví dụ ID do server quản lý, muốn serialize nhưng bỏ qua input client:

```java
@JsonIgnoreProperties(value = {"id"}, allowGetters = true)
public class UserRecord {
    private Long id;
    private String username;

    // getters và setters
}
```

Trong trường hợp này, getter vẫn có thể đưa `id` vào output; setter không được dùng để nhận `id` từ JSON. Với một property đơn lẻ, `@JsonProperty(access = READ_ONLY)` thường diễn đạt ý định trực tiếp hơn.

### 6.2. `ignoreUnknown` không phải là ẩn dữ liệu

Ví dụ:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public class PartnerRequest {
    private String name;
}
```

`ignoreUnknown = true` cho phép bỏ qua property lạ khi deserialize. Nó không phải cơ chế che field nhạy cảm khi serialize. Đừng nhầm tính năng tương thích input này với chính sách output.

## 7. Dùng JSON Views cho nhiều mức hiển thị

JSON Views cho phép đánh dấu property thuộc một hoặc nhiều nhóm hiển thị. Khi serialize, ứng dụng chọn view phù hợp với mục đích output.

Khai báo view:

```java
public class UserViews {
    public interface Public {}
    public interface Internal extends Public {}
}
```

Đánh dấu property:

```java
import com.fasterxml.jackson.annotation.JsonView;

public class UserProfile {
    @JsonView(UserViews.Public.class)
    private Long id;

    @JsonView(UserViews.Public.class)
    private String displayName;

    @JsonView(UserViews.Internal.class)
    private String email;

    @JsonView(UserViews.Internal.class)
    private String internalNote;

    // getters và setters
}
```

Ghi public view:

```java
String publicJson = mapper.writerWithView(UserViews.Public.class)
        .writeValueAsString(profile);
```

Ghi internal view:

```java
String internalJson = mapper.writerWithView(UserViews.Internal.class)
        .writeValueAsString(profile);
```

Do `Internal` kế thừa `Public`, view nội bộ có thể bao gồm các property thuộc view public cùng những property được đánh dấu `Internal`.

### 7.1. Kiểm soát property không có `@JsonView`

Trong Jackson 2.x, `MapperFeature.DEFAULT_VIEW_INCLUSION` mặc định thường bật: property không gắn `@JsonView` vẫn có thể được đưa vào view đang chọn. Điều này có thể làm view không chặt như dự định.

Nếu muốn chỉ các property được đánh dấu mới xuất hiện trong view, cấu hình:

```java
import com.fasterxml.jackson.databind.MapperFeature;

ObjectMapper mapper = new ObjectMapper();
mapper.disable(MapperFeature.DEFAULT_VIEW_INCLUSION);
```

Hãy kiểm tra output sau khi đổi feature, vì nó có thể làm các field cũ biến mất khỏi response. Cấu hình này cũng cần được xem xét cho cả các view khác của cùng mapper.

### 7.2. View không tự kiểm tra quyền

`writerWithView(Public.class)` là lựa chọn kỹ thuật của code server. Không để client tự chọn class view hoặc tên view rồi serialize dữ liệu nhạy cảm mà không có kiểm tra quyền. Service phải xác định người nhận và quyền của họ trước khi chọn view.

Với public/admin response, hai DTO riêng thường dễ review hơn một DTO có nhiều view phức tạp. JSON Views hữu ích khi nhiều nhóm output thực sự chia sẻ cùng model và quy tắc hiển thị tương đối ổn định.

## 8. Dùng property filter khi cần chọn field theo từng lần ghi

Jackson có cơ chế filter cho phép chọn property khi serialize. Đánh dấu lớp bằng `@JsonFilter`:

```java
import com.fasterxml.jackson.annotation.JsonFilter;

@JsonFilter("userOutput")
public class UserProfile {
    private Long id;
    private String username;
    private String email;
    private String phone;
    private String internalNote;

    // getters và setters
}
```

Tạo filter chỉ cho phép field được công bố:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ser.FilterProvider;
import com.fasterxml.jackson.databind.ser.impl.SimpleBeanPropertyFilter;
import com.fasterxml.jackson.databind.ser.impl.SimpleFilterProvider;

FilterProvider filters = new SimpleFilterProvider()
        .addFilter(
                "userOutput",
                SimpleBeanPropertyFilter.filterOutAllExcept(
                        "id", "username", "email"
                )
        );

String json = mapper.writer(filters).writeValueAsString(profile);
```

`filterOutAllExcept()` dùng allowlist: chỉ các property được liệt kê mới xuất hiện. Đây thường là lựa chọn an toàn hơn `serializeAllExcept()` khi dữ liệu nhạy cảm có thể được thêm vào model trong tương lai.

### 8.1. Filter theo từng ngữ cảnh

Có thể tạo các `ObjectWriter` khác nhau từ cùng mapper:

```java
FilterProvider publicFilter = new SimpleFilterProvider()
        .addFilter("userOutput",
                SimpleBeanPropertyFilter.filterOutAllExcept("id", "username"));

FilterProvider supportFilter = new SimpleFilterProvider()
        .addFilter("userOutput",
                SimpleBeanPropertyFilter.filterOutAllExcept(
                        "id", "username", "email", "phone"));

ObjectWriter publicWriter = mapper.writer(publicFilter);
ObjectWriter supportWriter = mapper.writer(supportFilter);
```

Chỉ chọn `supportWriter` sau khi kiểm tra quyền của nhân viên hỗ trợ. `ObjectWriter` là đối tượng cấu hình bất biến, phù hợp để tạo và tái sử dụng cho một kiểu output.

### 8.2. Không mặc định filter áp dụng cho mọi loại JSON

`SimpleBeanPropertyFilter` lọc property của bean được đánh dấu bằng `@JsonFilter`. Nó không tự động áp dụng chính sách tương tự cho mọi `Map`, `JsonNode`, raw JSON hoặc chuỗi JSON đã được tạo sẵn.

Nếu output có `Map<String, Object>` hoặc cây `JsonNode`, hãy lọc key/node bằng logic allowlist riêng trước khi serialize. Không giả định filter trên POJO sẽ bảo vệ mọi đường đi của dữ liệu.

## 9. Masking: chỉ che một phần giá trị khi nghiệp vụ cho phép

Có trường hợp người nhận cần nhận diện dữ liệu nhưng không cần biết toàn bộ giá trị, ví dụ hiển thị email hoặc số điện thoại đã che. Masking tạo một biểu diễn đã biến đổi, khác với việc loại bỏ property.

Ví dụ email:

```text
an.nguyen@example.com  ->  a***@example.com
```

Nên tạo giá trị masked trong DTO output:

```java
public record ContactResponse(
        String displayName,
        String maskedEmail) {
}
```

```java
public ContactResponse toResponse(UserAccount account) {
    return new ContactResponse(
            account.getDisplayName(),
            maskEmail(account.getEmail())
    );
}
```

Cách này làm rõ rằng response chỉ chứa chuỗi đã che; entity gốc vẫn giữ giá trị đầy đủ cho các nghiệp vụ được cấp quyền.

### 9.1. Custom serializer cho masking

Nếu nhiều DTO dùng cùng quy tắc hiển thị, có thể viết custom serializer và gắn vào property:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.fasterxml.jackson.databind.ser.std.StdScalarSerializer;

import java.io.IOException;

public class MaskedEmailSerializer extends StdScalarSerializer<String> {
    public MaskedEmailSerializer() {
        super(String.class);
    }

    @Override
    public void serialize(String value,
                          JsonGenerator generator,
                          SerializerProvider provider) throws IOException {
        if (value == null) {
            generator.writeNull();
            return;
        }

        int at = value.indexOf('@');
        if (at <= 0) {
            generator.writeString("***");
            return;
        }

        String localPart = value.substring(0, at);
        String domain = value.substring(at);
        String visible = localPart.substring(0, 1);
        generator.writeString(visible + "***" + domain);
    }
}
```

Gắn serializer:

```java
import com.fasterxml.jackson.databind.annotation.JsonSerialize;

public class ContactResponse {
    @JsonSerialize(using = MaskedEmailSerializer.class)
    private String email;

    // getter và setter
}
```

Đây là quy tắc minh họa; masking thực tế cần được định nghĩa theo loại dữ liệu và yêu cầu bảo mật. Không dùng cùng một serializer cho email, số thẻ và số điện thoại nếu quy tắc che khác nhau.

### 9.2. Masking không thay thế việc loại bỏ secret

Không nên trả password, password hash, private key hoặc bearer token dưới dạng một chuỗi đã che. Với những bí mật đó, output nên loại bỏ hoàn toàn. Masking chỉ phù hợp khi người nhận có lý do nghiệp vụ để thấy một phần dữ liệu và việc tiết lộ phần đó đã được cho phép.

Masking trong serializer cũng chỉ ảnh hưởng tới đường serialization được cấu hình. Nó không sửa giá trị trong object, không che dữ liệu trong log được tạo bằng `toString()` và không ngăn một service khác đọc field gốc.

## 10. Lọc cây JSON động trước khi trả về

Khi dữ liệu đã ở dạng `JsonNode` hoặc đến từ nguồn JSON động, có thể tạo một object mới chỉ chứa các field được cho phép:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

public ObjectNode publicProjection(ObjectNode source) {
    ObjectNode result = source.objectNode();

    copyIfPresent(source, result, "id");
    copyIfPresent(source, result, "displayName");
    copyIfPresent(source, result, "publicStatus");

    return result;
}

private void copyIfPresent(ObjectNode source,
                           ObjectNode target,
                           String fieldName) {
    JsonNode value = source.get(fieldName);
    if (value != null) {
        target.set(fieldName, value.deepCopy());
    }
}
```

Kết quả chỉ chứa các field được nêu trong allowlist. Việc dùng `deepCopy()` giúp output projection có cây con độc lập nếu sau đó còn chỉnh sửa.

Với object lồng nhau, cần áp dụng allowlist đệ quy theo từng loại node. Không copy toàn bộ object con nếu bên trong nó có field bí mật. Ví dụ, nếu `profile` chứa `displayName`, `email`, `internalNote`, chỉ tạo projection của `profile` với những field được phép.

## 11. Dùng Mix-in khi không thể sửa class nguồn

Khi class đến từ thư viện bên ngoài hoặc generated code, có thể dùng Jackson Mix-in để bổ sung annotation mà không sửa class gốc.

Class bên thứ ba:

```java
public class ExternalAccount {
    public String username;
    public String accessToken;
}
```

Mix-in:

```java
import com.fasterxml.jackson.annotation.JsonIgnore;

abstract class ExternalAccountMixin {
    @JsonIgnore
    public String accessToken;
}
```

Đăng ký:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.addMixIn(ExternalAccount.class, ExternalAccountMixin.class);
```

Mix-in phù hợp khi cần điều khiển JSON mapping của kiểu không thuộc quyền sở hữu source code. Cần kiểm thử mapping sau khi đăng ký vì annotation trong mix-in được hợp nhất với metadata của lớp gốc theo quy tắc Jackson.

## 12. `@JsonInclude` không phải cơ chế bảo mật

`@JsonInclude` điều khiển khi nào property được đưa vào output dựa trên giá trị hoặc trạng thái, ví dụ bỏ qua null:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public class UserResponse {
    private String displayName;
    private String email;
}
```

Nếu `email` khác null, nó vẫn được serialize. Vì vậy, `NON_NULL` không có nghĩa “ẩn dữ liệu nhạy cảm”. Tương tự, `NON_EMPTY` chỉ bỏ các giá trị rỗng theo quy tắc inclusion; nó không phân loại bí mật.

Không nên đặt password hoặc token thành null rồi dựa vào `NON_NULL` để che. Field vẫn tồn tại trong model, có thể bị log, được serialize qua mapper khác hoặc xuất hiện khi cấu hình inclusion thay đổi. Hãy loại bỏ field bằng DTO, access policy hoặc ignore rule rõ ràng.

## 13. Không dựa vào `transient`, tên field hoặc visibility mặc định

Các cách sau không phải một chính sách output rõ ràng:

- Đặt tên field bắt đầu bằng `_` hoặc `internal` rồi mong Jackson tự bỏ qua.
- Giả định field private sẽ không được serialize trong mọi cấu hình.
- Dùng `transient` mà không kiểm tra `MapperFeature.PROPAGATE_TRANSIENT_MARKER` và cấu hình visibility thực tế.
- Ẩn getter nhưng vẫn để một field khác cùng property được phát hiện.
- Cho rằng property không xuất hiện trong một test đơn giản thì mọi mapper/framework đều bỏ qua nó.

Jackson có thể được cấu hình để nhìn vào field, getter, setter hoặc creator theo visibility rules. Framework cũng có thể cung cấp mapper với cấu hình khác mapper tự tạo trong unit test. Với dữ liệu nhạy cảm, dùng annotation hoặc DTO rõ ràng và kiểm thử trên mapper thực sự được ứng dụng sử dụng.

## 14. Chính sách output không bảo vệ log và các đường dữ liệu khác

Một property bị `@JsonIgnore` khỏi JSON response vẫn có thể bị lộ qua:

- `toString()` do Lombok hoặc IDE sinh ra.
- Log toàn bộ request/response body ở HTTP filter.
- Exception message chứa input gốc.
- Audit event hoặc message queue dùng một DTO khác.
- Cache/debug snapshot hoặc file export.
- SQL log, tracing span hoặc telemetry attribute.

Vì vậy, cần có chính sách riêng cho log và observability:

1. Không log password, access token, refresh token, private key hoặc secret header.
2. Ưu tiên log mã định danh, loại thao tác, trạng thái và correlation id thay cho payload đầy đủ.
3. Nếu cần log một phần dữ liệu cá nhân, dùng masking đã được phê duyệt.
4. Tránh đưa raw request body vào exception hoặc metric label.
5. Làm sạch ký tự điều khiển khi log dữ liệu do người dùng cung cấp để tránh log injection.
6. Giới hạn quyền truy cập và thời gian lưu log chứa dữ liệu nhạy cảm.

Annotation của Jackson chỉ kiểm soát một đường data binding cụ thể. Không coi nó là giải pháp bảo vệ toàn bộ vòng đời dữ liệu.

## 15. Một ví dụ tổng hợp: request và response có chính sách khác nhau

Giả sử đăng ký tài khoản cần nhận password, nhưng response chỉ trả thông tin công khai.

Request DTO:

```java
public record RegisterUserRequest(
        String username,
        String password,
        String displayName) {
}
```

Response DTO:

```java
public record RegisterUserResponse(
        Long id,
        String username,
        String displayName) {
}
```

Service:

```java
public RegisterUserResponse register(RegisterUserRequest request) {
    validate(request);

    String passwordHash = passwordEncoder.encode(request.password());
    UserAccount saved = repository.save(
            new UserAccount(request.username(), passwordHash, request.displayName())
    );

    return new RegisterUserResponse(
            saved.getId(),
            saved.getUsername(),
            saved.getDisplayName()
    );
}
```

Jackson đọc request vào `RegisterUserRequest`; service xử lý password và chỉ lưu hash. Response được tạo bằng `RegisterUserResponse`, không chứa password hoặc hash. Đây là allowlist ở mức kiểu dữ liệu, dễ review hơn việc serialize entity rồi cố gắng loại từng field.

Trong thực tế, `validate()` cần kiểm tra chính sách password, username và các quy tắc đăng ký. Không lưu plaintext password vào entity hoặc log sau khi đã xử lý.

## 16. Kiểm thử chính sách ẩn dữ liệu

Mỗi chính sách cần test bằng JSON output thực tế. Ví dụ với `WRITE_ONLY`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertEquals;

class RegistrationRequestJsonTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void acceptsPasswordOnInputButDoesNotWriteItBack() throws Exception {
        String input = """
                {"username":"an","password":"secret-value"}
                """;

        RegistrationRequest request = mapper.readValue(
                input,
                RegistrationRequest.class
        );

        assertEquals("secret-value", request.getPassword());

        String output = mapper.writeValueAsString(request);
        assertFalse(output.contains("password"));
        assertFalse(output.contains("secret-value"));
    }
}
```

Với DTO output, test cả việc field được phép có mặt lẫn field cấm không xuất hiện:

```java
String json = mapper.writeValueAsString(publicResponse);
JsonNode node = mapper.readTree(json);

assertTrue(node.has("displayName"));
assertFalse(node.has("passwordHash"));
assertFalse(node.has("refreshToken"));
```

Các nhóm test nên có:

- Serialize public output và xác nhận không có secret.
- Deserialize request và xác nhận field chỉ nhận được xử lý đúng.
- Gửi thử field server-managed trong input và xác nhận nó không ghi đè trạng thái server.
- Kiểm tra object lồng nhau, collection và map có chứa field nhạy cảm.
- Kiểm tra từng JSON View hoặc filter được sử dụng.
- Kiểm tra null/empty để bảo đảm `@JsonInclude` không làm lộ field ngoài dự kiến.
- Kiểm tra log/error path không chứa secret.

Đừng chỉ test một object đơn giản. Dữ liệu nhạy cảm có thể nằm sâu trong object lồng nhau hoặc phần tử array.

## 17. Chọn cơ chế nào?

| Nhu cầu | Cơ chế nên cân nhắc | Ghi chú |
|---|---|---|
| Không bao giờ đọc/ghi property qua JSON | `@JsonIgnore` | Phù hợp với secret nội bộ |
| Chỉ nhận từ input, không trả output | `@JsonProperty(access = WRITE_ONLY)` | Ví dụ password request; vẫn phải tránh log |
| Chỉ trả output, không nhận từ input | `@JsonProperty(access = READ_ONLY)` | Ví dụ ID/trạng thái do server quản lý |
| Bỏ một nhóm property theo tên | `@JsonIgnoreProperties` | Có thể điều chỉnh bằng `allowGetters`/`allowSetters` |
| Nhiều mức hiển thị trên một model | `@JsonView` | Cần kiểm soát default view inclusion và quyền chọn view |
| Chọn field theo từng lần serialize | `@JsonFilter` + allowlist filter | Phù hợp với output động; filter không tự áp dụng cho mọi Map/JsonNode |
| Che một phần dữ liệu | DTO masking hoặc custom serializer | Không dùng cho bí mật phải loại bỏ hoàn toàn |
| Không sở hữu class nguồn | Mix-in | Kiểm tra metadata hợp nhất |
| Dữ liệu public/admin có hợp đồng khác nhau | DTO riêng | Thường rõ ràng và an toàn nhất |

## 18. Nguyên tắc bảo vệ dữ liệu khi dùng Jackson

- Thiết kế output theo allowlist: chỉ xuất những field mà người nhận cần và được phép nhận.
- Tách request DTO, response DTO và domain entity khi mục đích hoặc quyền truy cập khác nhau.
- Dùng `WRITE_ONLY` cho dữ liệu chỉ nhận vào; `READ_ONLY` cho dữ liệu server trả ra; `@JsonIgnore` cho property không đi qua JSON.
- Chỉ dùng masking khi người nhận có lý do nghiệp vụ để thấy một phần giá trị.
- Chọn `@JsonView` hoặc filter theo từng ngữ cảnh, và xác định view/filter ở phía server sau khi kiểm tra quyền.
- Không nhầm `@JsonInclude(NON_NULL)` hoặc `ignoreUnknown` với bảo vệ dữ liệu.
- Kiểm tra cả object lồng nhau, map, tree, log và export; annotation trên một POJO không tự bảo vệ các đường dữ liệu khác.
- Không serialize entity trực tiếp ra public API nếu entity có field nội bộ hoặc bí mật.
- Kiểm thử output để xác nhận field cho phép có mặt và field cấm không xuất hiện.

## 19. Kết luận

Ẩn dữ liệu nhạy cảm trong Jackson cần một chính sách output rõ ràng. `@JsonIgnore` loại property khỏi JSON; `@JsonProperty(access = WRITE_ONLY/READ_ONLY)` điều khiển riêng chiều nhận và chiều trả; `@JsonIgnoreProperties` bỏ qua nhóm field; JSON Views và property filters phục vụ nhiều mức hiển thị; custom serializer có thể masking khi nghiệp vụ cho phép. Với API công khai hoặc các ranh giới tin cậy khác nhau, DTO output theo allowlist thường là lựa chọn dễ kiểm soát nhất.

Đừng xem annotation serialization là cơ chế phân quyền hoặc bảo vệ toàn bộ vòng đời dữ liệu. Service vẫn phải kiểm tra quyền, log phải có chính sách riêng và test phải xác nhận các field nhạy cảm không xuất hiện ở bất kỳ output nào ngoài dự kiến.
