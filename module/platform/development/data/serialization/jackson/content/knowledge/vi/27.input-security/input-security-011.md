# Ngăn lộ bí mật qua thuộc tính tự nhận diện và nhật ký lỗi

Jackson có thể đưa dữ liệu ra JSON thông qua những property được tự phát hiện từ getter, is-getter, field hoặc annotation. Ngoài các property do ứng dụng khai báo, JSON còn có thể chứa metadata do Jackson thêm vào để nhận diện subtype hoặc object identity. Nếu những property này mang tên class nội bộ, database ID, token hoặc thông tin cấu trúc nhạy cảm, response có thể tiết lộ chi tiết mà API không định công bố.

Lỗi deserialize cũng có thể làm lộ dữ liệu. Exception, stack trace, parser location, request logging hoặc APM có thể chứa tên field, giá trị đầu vào hay một phần payload. Gửi nguyên thông báo lỗi hoặc ghi toàn bộ request body vào log khiến dữ liệu nhạy cảm lan sang nơi có chính sách truy cập và thời hạn lưu giữ khác.

Cần kiểm soát cả hai đường: **chỉ serialize những property được phép công bố** và **chỉ ghi log thông tin lỗi đã được chọn lọc**. Jackson annotation giúp điều chỉnh hành vi, nhưng DTO response có allowlist field và logging policy tập trung thường là lớp bảo vệ dễ kiểm soát nhất.

## 1. Property tự được Jackson phát hiện

Jackson Databind thường xây dựng property từ các thành phần của JavaBean:

- Getter công khai như getEmail().
- Boolean getter như isEnabled().
- Field theo visibility được cấu hình.
- Setter/constructor parameter ở chiều deserialize.
- Property được khai báo tường minh bằng annotation như JsonProperty.

Ví dụ:

~~~java
public class Account {
    private String username;
    private String passwordHash;
    private String resetToken;

    public String getUsername() {
        return username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public String getResetToken() {
        return resetToken;
    }
}
~~~

Dù passwordHash và resetToken là field private, các getter công khai khiến Jackson có thể nhận diện chúng như property có thể serialize.

Nếu code trả thẳng entity:

~~~java
return mapper.writeValueAsString(account);
~~~

JSON có thể chứa cả những giá trị nội bộ:

~~~json
{
  "username": "an",
  "passwordHash": "$argon2id$...",
  "resetToken": "secret-token-value"
}
~~~

Đây là lỗi thiết kế response phổ biến: developer thêm getter để code nội bộ sử dụng, nhưng getter đó vô tình mở rộng JSON contract.

Không nên coi private là biện pháp bảo vệ dữ liệu khỏi serialization. Hãy xác định rõ property nào được phép xuất hiện trong từng response.

## 2. Dùng DTO response với allowlist field

Cách dễ kiểm soát nhất là tạo một kiểu response riêng chỉ chứa dữ liệu được phép công bố.

~~~java
public record AccountResponse(
    String username,
    String displayName
) {
    public static AccountResponse from(Account account) {
        return new AccountResponse(
            account.getUsername(),
            account.getDisplayName()
        );
    }
}
~~~

Serialize:

~~~java
AccountResponse response = AccountResponse.from(account);
String json = mapper.writeValueAsString(response);
~~~

JSON chỉ có:

~~~json
{
  "username": "an",
  "displayName": "An Nguyen"
}
~~~

passwordHash, resetToken, internal database fields và các property mới được thêm vào entity không tự động xuất hiện trong response DTO.

DTO allowlist đặc biệt hữu ích khi:

- Entity chứa thông tin xác thực, token, dữ liệu thanh toán hoặc thông tin nội bộ.
- Nhiều endpoint có quyền xem các tập field khác nhau.
- Entity thay đổi thường xuyên nhưng API contract cần ổn định.
- Cần audit rõ dữ liệu nào được gửi ra bên ngoài.

Không dùng entity persistence làm response model chỉ vì Jackson có thể serialize nó thuận tiện.

## 3. Ẩn property bằng @JsonIgnore

Nếu một property tuyệt đối không được serialize và cũng không cần deserialize qua JSON, có thể dùng JsonIgnore:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class Account {
    private String username;

    @JsonIgnore
    private String passwordHash;

    // Getter/setter
}
~~~

Jackson bỏ qua property được đánh dấu trong quá trình data binding thông thường. Annotation có thể đặt trên field, getter hoặc property tùy cách Jackson hợp nhất các thành phần cùng tên.

Hãy kiểm tra metadata thực tế nếu cùng một property có annotation ở nhiều nơi. Một annotation trên getter có thể ảnh hưởng property được hợp nhất từ field và setter.

JsonIgnore phù hợp với dữ liệu nội bộ không nên đi qua JSON. Nếu server cần nhận giá trị từ request nhưng không bao giờ trả lại giá trị đó, dùng access direction riêng ở phần tiếp theo.

## 4. Dùng WRITE_ONLY cho bí mật chỉ nhận từ request

Một số dữ liệu cần được nhận khi tạo hoặc cập nhật, nhưng không được phát ra khi serialize response. Ví dụ password mới hoặc secret do client cung cấp.

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public class ChangePasswordRequest {
    private String username;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String newPassword;

    public String getUsername() {
        return username;
    }

    public String getNewPassword() {
        return newPassword;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public void setNewPassword(String newPassword) {
        this.newPassword = newPassword;
    }
}
~~~

WRITE_ONLY có nghĩa property được dùng ở chiều deserialize (đọc từ JSON vào Java) và không được phát ra ở chiều serialize.

Ngược lại, READ_ONLY dùng cho giá trị server trả về nhưng client không được gán qua input JSON:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private String accountStatus;
~~~

Không nhầm WRITE_ONLY với JsonIgnore: JsonIgnore thường loại property khỏi cả hai chiều, còn access mode thể hiện rõ chiều nào được phép.

Dù dùng WRITE_ONLY, vẫn tránh log ChangePasswordRequest, gọi toString() trên object hoặc đưa request vào tracing. Annotation điều khiển JSON serialization, không tự che dữ liệu trong log, debugger, heap dump hay exception nghiệp vụ.

## 5. Giới hạn auto-detection bằng @JsonAutoDetect

Với model đặc biệt nhạy cảm, có thể tắt tự phát hiện getter/field rồi chỉ công bố property có annotation rõ ràng.

~~~java
import com.fasterxml.jackson.annotation.JsonAutoDetect;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonAutoDetect(
    fieldVisibility = JsonAutoDetect.Visibility.NONE,
    getterVisibility = JsonAutoDetect.Visibility.NONE,
    isGetterVisibility = JsonAutoDetect.Visibility.NONE
)
public class AccountResponse {
    private final String username;
    private final String displayName;
    private final String internalNote;

    public AccountResponse(
            String username,
            String displayName,
            String internalNote) {
        this.username = username;
        this.displayName = displayName;
        this.internalNote = internalNote;
    }

    @JsonProperty("username")
    public String username() {
        return username;
    }

    @JsonProperty("displayName")
    public String displayName() {
        return displayName;
    }
}
~~~

Với cấu hình này, chỉ hai accessor được đánh dấu là property JSON. internalNote không được phát ra.

Ví dụ minh họa cách khóa auto-detection ở một lớp. Nếu dùng cùng lớp để deserialize, cần khai báo creator và property metadata phù hợp; không nên tắt creator visibility rồi mong Jackson tự chọn constructor không có annotation.

Có thể cấu hình visibility ở cấp mapper, nhưng ảnh hưởng sẽ rộng hơn:

~~~java
mapper.setVisibility(
    PropertyAccessor.ALL,
    JsonAutoDetect.Visibility.NONE
);
~~~

Sau đó, ứng dụng phải đánh dấu tường minh những property cần serialize/deserialize. Chỉ áp dụng chính sách global khi mapper được thiết kế cho kiểu contract đó; nếu mapper dùng chung cho thư viện hoặc DTO khác, cấu hình có thể làm hỏng data binding ngoài dự kiến.

## 6. Tránh lộ bí mật qua type metadata

Polymorphic serialization có thể thêm một property chứa type identifier. Ví dụ:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.CLASS,
    include = JsonTypeInfo.As.PROPERTY,
    property = "@class"
)
private Object payload;
~~~

JSON có thể chứa:

~~~json
{
  "@class": "com.company.internal.payment.InternalCardPayment",
  "cardToken": "..."
}
~~~

Tên class đầy đủ có thể tiết lộ package, kiến trúc nội bộ, tên module hoặc công nghệ được dùng. Nếu type metadata được đưa ra API public, client còn có thể phụ thuộc vào implementation detail mà server muốn thay đổi.

Với polymorphic contract, ưu tiên logical type name đã đăng ký rõ ràng:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
})
public interface PaymentMethod {
}
~~~

JSON:

~~~json
{
  "kind": "card",
  "cardToken": "..."
}
~~~

kind là discriminator thuộc hợp đồng API. Nó không tiết lộ tên class Java. Danh sách subtype vẫn phải là allowlist và type id từ input vẫn cần được xác thực.

Không dùng Id.CLASS hoặc Id.MINIMAL_CLASS chỉ để tiện tự động nhận diện lớp. Ngoài nguy cơ mở rộng bề mặt polymorphic deserialization, chúng còn có thể làm lộ tên lớp trong output.

### 6.1. visible type id không phải cơ chế che dữ liệu

Thuộc tính visible = true trong JsonTypeInfo quyết định type id có tiếp tục được chuyển cho deserializer như một property bình thường hay không. Nó không phải cờ ẩn metadata và cũng không phải cơ chế redaction.

Nếu discriminator là thông tin public, dùng tên logic ổn định như kind. Nếu discriminator chứa tên class, package hoặc thông tin nội bộ, hãy thay đổi thiết kế type id thay vì cố che bằng visible = false.

### 6.2. Type id và unknown subtype

Nếu nhận type id không được đăng ký, hãy từ chối theo chính sách mapping. Không ghi toàn bộ payload hoặc type id không tin cậy vào log lỗi. Nếu cần chẩn đoán, log mã lỗi cố định, tên base type và request correlation ID; chỉ log giá trị discriminator sau khi đã xác định nó không chứa thông tin nhạy cảm.

## 7. Kiểm soát object identity metadata

Jackson cũng có thể thêm object identity property khi dùng JsonIdentityInfo.

~~~java
@JsonIdentityInfo(
    generator = ObjectIdGenerators.PropertyGenerator.class,
    property = "id"
)
public class Department {
    private Long id;
    private String name;
    // ...
}
~~~

Metadata này giúp Jackson biểu diễn quan hệ tham chiếu và vòng lặp object graph. Nhưng nếu id là khóa database nội bộ, serialization có thể tiết lộ identifier mà API không định công bố.

Cần phân biệt:

- Object identity phục vụ việc tham chiếu object trong JSON.
- Public resource identifier phục vụ hợp đồng API.
- Database primary key phục vụ persistence nội bộ.

Nếu cần identity trong JSON public, cân nhắc dùng public opaque ID riêng thay cho database key. Hoặc chuyển entity sang DTO có identifier được phép công bố.

Không bật identity annotation trên entity chỉ để tránh vòng lặp rồi bỏ qua ý nghĩa bảo mật của property ID được phát ra.

## 8. @JsonView và @JsonFilter không thay thế DTO allowlist

JsonView cho phép chọn tập property theo view:

~~~java
public class Views {
    public static class Public {}
    public static class Admin extends Public {}
}

public class User {
    @JsonView(Views.Public.class)
    public String username;

    @JsonView(Views.Admin.class)
    public String internalNote;
}
~~~

Serialize với view:

~~~java
String json = mapper
    .writerWithView(Views.Public.class)
    .writeValueAsString(user);
~~~

JsonFilter cũng có thể lọc property theo tên ở runtime thông qua FilterProvider.

Các cơ chế này hữu ích khi nhiều response có tập field khác nhau, nhưng cấu hình sai có thể vô tình phát ra field nhạy cảm. Đặc biệt, hành vi property không được đánh dấu phụ thuộc cấu hình MapperFeature.DEFAULT_VIEW_INCLUSION.

Nếu dùng view/filter để phân quyền dữ liệu, phải cấu hình rõ inclusion và kiểm thử từng endpoint. Không xem tên view như một authorization check; người gọi không được tự chọn view admin nếu chưa được server cấp quyền.

DTO riêng cho public/admin response thường dễ audit hơn một entity lớn có nhiều view.

## 9. Tránh lộ bí mật qua toString() và log object

Annotation Jackson chỉ điều khiển quá trình chuyển object thành JSON. Nó không điều khiển cách Java tạo chuỗi bằng toString().

Ví dụ nguy hiểm:

~~~java
log.debug("Incoming password request: {}", request);
log.info("Account object: {}", account);
~~~

Nếu Lombok @Data, record hoặc toString() được tạo từ IDE bao gồm field nhạy cảm, log có thể chứa password, token hoặc hash ngay cả khi Jackson đã dùng WRITE_ONLY.

Không log trực tiếp:

- DTO request chứa password, token hoặc API key.
- Entity chứa password hash, reset token hoặc secret.
- Map chứa header, cookie hoặc raw claim.
- JsonNode đại diện toàn bộ request.
- JsonParser/JsonLocation nếu formatter của ứng dụng in kèm source reference.
- Exception object chưa được đánh giá nội dung.

Thay vào đó, tạo một log event allowlist:

~~~java
log.info(
    "Password change requested requestId={} accountId={}",
    requestId,
    publicAccountId
);
~~~

Chỉ ghi những giá trị thực sự cần cho vận hành. Nếu cần log trạng thái, dùng event code và outcome đã chuẩn hóa.

## 10. Vì sao exception của Jackson có thể làm lộ dữ liệu?

Các exception trong Jackson cung cấp thông tin hữu ích để tìm lỗi:

- JsonParseException có thể cho biết lỗi cú pháp và vị trí parser.
- JsonMappingException có thể chứa path tới property/index gây lỗi.
- InvalidFormatException có thể chứa giá trị không chuyển đổi được và kiểu đích.
- UnrecognizedPropertyException có thể chứa tên property không được nhận diện.

Thông tin này hữu ích cho developer, nhưng không phải lúc nào cũng phù hợp để trả cho client hoặc ghi vào log có nhiều người truy cập.

Ví dụ input:

~~~json
{
  "password": "SuperSecret123",
  "age": "not-a-number"
}
~~~

Một lỗi mapping có thể chỉ ra property age, kiểu đích và giá trị gây lỗi. Nếu ứng dụng ghi nguyên exception message hoặc toàn bộ request body, log có thể chứa cả password dù lỗi xảy ra ở field khác.

Hãy coi exception từ dữ liệu không tin cậy là dữ liệu có thể chứa thông tin nhạy cảm. Chọn thông tin an toàn cần ghi thay vì mặc định ghi toàn bộ.

## 11. Ghi log lỗi đã chọn lọc

Với lỗi parse/mapping từ request, log tối thiểu thường gồm:

- Correlation ID hoặc request ID do server tạo.
- Mã lỗi nội bộ ổn định.
- Loại exception (class simple name).
- Line/column nếu có và nếu hữu ích.
- Path đã được chọn lọc nếu path không chứa tên field nhạy cảm.
- Endpoint hoặc message type ở dạng đã chuẩn hóa.

Ví dụ:

~~~java
try {
    return mapper.readValue(body, CreateAccountRequest.class);
} catch (JsonProcessingException ex) {
    JsonLocation location = ex.getLocation();

    Integer line = location == null ? null : location.getLineNr();
    Integer column = location == null ? null : location.getColumnNr();

    log.warn(
        "Rejected JSON request requestId={} errorCode={} exceptionType={} line={} column={}",
        requestId,
        "INVALID_JSON",
        ex.getClass().getSimpleName(),
        line,
        column
    );

    throw new InvalidRequestException("Request body is invalid");
}
~~~

Ví dụ này không truyền ex làm đối số cuối cho logger nên không tự động in stack trace/message có thể chứa dữ liệu đầu vào. Exception được chuyển thành lỗi tổng quát ở tầng API; chi tiết kỹ thuật có thể được lưu qua một kênh nội bộ đã sanitize nếu thật sự cần.

### 11.1. Path reference cũng cần được xem xét

JsonMappingException.getPathReference() hữu ích để biết lỗi xảy ra tại đâu. Tuy nhiên, tên property có thể chứa dữ liệu do client kiểm soát hoặc có thể tiết lộ cấu trúc nội bộ.

Có thể chỉ log path sau khi lọc:

~~~java
if (ex instanceof JsonMappingException mappingException) {
    String safePath = sanitizePath(mappingException.getPath());
    log.warn("Invalid JSON mapping requestId={} path={}", requestId, safePath);
}
~~~

sanitizePath là logic của ứng dụng: chỉ giữ tên property trong allowlist hoặc thay tên nhạy cảm bằng nhãn như [REDACTED_FIELD]. Không giả định path luôn an toàn chỉ vì nó không chứa value.

### 11.2. Không log raw parser source

JsonLocation cung cấp line/column và có thể cung cấp source reference. Source reference có thể là object nguồn hoặc thông tin mô tả nguồn tùy parser/factory.

Khi log vị trí, chỉ lấy các trường đã chọn như line và column. Tránh gọi toString() trên toàn bộ location hoặc log getSourceRef() nếu không chắc nó có thể chứa payload.

Trong các phiên bản Jackson Core hỗ trợ StreamReadFeature.INCLUDE_SOURCE_IN_LOCATION, có thể tắt việc đưa source reference vào location:

~~~java
JsonFactory factory = JsonFactory.builder()
    .disable(StreamReadFeature.INCLUDE_SOURCE_IN_LOCATION)
    .build();
~~~

Tên feature và API cần đối chiếu với phiên bản Jackson Core đang dùng. Dù đã tắt feature này, ứng dụng vẫn phải tránh log raw body ở filter, interceptor hoặc thư viện observability.

## 12. Trả lỗi an toàn cho client

Client thường chỉ cần biết request bị từ chối và cách sửa. Không cần biết class Java nội bộ, stack trace, package, file path, SQL hoặc raw input.

Ví dụ response lỗi:

~~~json
{
  "code": "INVALID_JSON",
  "message": "Request body is invalid.",
  "requestId": "req-8f31"
}
~~~

Không trả:

~~~json
{
  "error": "Cannot deserialize value of type com.company.internal.AccountEntity from String \"SuperSecret123\" at line 1, column 28",
  "stackTrace": "..."
}
~~~

Thông báo lỗi public nên:

- Dùng mã lỗi ổn định.
- Dùng câu mô tả tổng quát, không echo raw value.
- Không gửi stack trace, class name nội bộ hoặc file path.
- Có request ID để bộ phận hỗ trợ tra log nội bộ.
- Không phân biệt quá chi tiết giữa các trạng thái xác thực nếu điều đó giúp dò tài khoản hoặc secret.

Chi tiết kỹ thuật nên ở log nội bộ đã sanitize, không nằm trong response body.

## 13. Không ghi toàn bộ request body ở middleware

Rò rỉ thường xảy ra trước cả Jackson. HTTP filter, reverse proxy, API gateway, tracing agent hoặc APM có thể ghi request/response body tự động.

Kiểm tra các vị trí:

- Access log và request logging filter.
- Interceptor của HTTP client/server.
- Framework debug logging.
- APM agent và distributed tracing.
- Message broker dead-letter queue và retry log.
- Audit event và exception reporter.

Nếu cần quan sát request, ưu tiên metadata như content length, media type, request ID và endpoint. Nếu bắt buộc log body để điều tra, hãy tạo bản sao đã redacted theo schema, giới hạn kích thước, giới hạn quyền truy cập và thời gian lưu giữ.

Không dựa vào regex đơn giản để redaction JSON tùy ý. Nested object, escaped string, duplicate key và tên field khác chữ hoa/thường có thể làm regex bỏ sót secret. Nếu cần lọc theo cấu trúc, parse thành tree rồi chỉ tạo log event từ allowlist field đã biết. Nếu payload không parse được, đừng log nguyên body làm fallback.

## 14. Redaction theo allowlist và schema

Một chiến lược tốt là chỉ ghi những field được phép, thay vì ghi tất cả rồi cố xóa secret.

Ví dụ:

~~~java
public record SafeRequestLog(
    String requestId,
    String username,
    String operation
) {
    static SafeRequestLog from(
            String requestId,
            ChangePasswordRequest request) {
        return new SafeRequestLog(
            requestId,
            request.getUsername(),
            "CHANGE_PASSWORD"
        );
    }
}
~~~

Log:

~~~java
log.info("Request received: {}", safeRequestLog);
~~~

Không đưa newPassword vào log DTO. Cách này giảm nguy cơ khi sau này request model được thêm field bí mật.

Nếu phải redact JSON tree, định nghĩa chính xác các path nhạy cảm như /password, /accessToken, /refreshToken, /credentials/*. Khi schema thay đổi, test redaction phải được cập nhật. Không chỉ thay giá trị bằng "***" rồi ghi cả payload nếu những field khác vẫn chứa PII hoặc secret.

## 15. Giới hạn dữ liệu và độ sâu khi đọc input

Bảo mật không chỉ là che output. Một payload quá lớn hoặc quá sâu có thể làm tăng bộ nhớ, CPU và log volume.

Với Jackson Core hỗ trợ StreamReadConstraints, đặt giới hạn phù hợp:

~~~java
JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(
        StreamReadConstraints.builder()
            .maxNestingDepth(100)
            .maxStringLength(1_000_000)
            .maxNumberLength(1_000)
            .build()
    )
    .build();
~~~

Các con số chỉ là ví dụ; chọn theo giới hạn request thực tế. Cần thêm giới hạn body ở HTTP server/gateway, timeout, số field/record và quota cho log.

Khi constraint bị vi phạm, exception có thể chứa chi tiết vị trí hoặc giới hạn. Vẫn áp dụng chính sách log đã sanitize; không ghi nguyên body chỉ vì lỗi xảy ra trước khi DTO được tạo.

## 16. Kiểm thử không rò rỉ property nhạy cảm

Test serialization nên xác nhận field nhạy cảm không xuất hiện trong JSON output.

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class AccountSerializationTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void responseDoesNotExposeSecrets() throws Exception {
        Account account = new Account(
            "an",
            "hash-value",
            "reset-token-value"
        );

        AccountResponse response = AccountResponse.from(account);
        JsonNode json = mapper.readTree(
            mapper.writeValueAsString(response)
        );

        assertTrue(json.has("username"));
        assertFalse(json.has("passwordHash"));
        assertFalse(json.has("resetToken"));
        assertFalse(json.toString().contains("hash-value"));
        assertFalse(json.toString().contains("reset-token-value"));
    }
}
~~~

Với polymorphic type metadata, kiểm tra output không chứa tên class/package nội bộ:

~~~java
String json = mapper.writeValueAsString(paymentRequest);

assertFalse(json.contains("com.company.internal"));
assertTrue(json.contains("\"kind\":\"card\""));
~~~

Với log lỗi, dùng test logger/appender để xác nhận thông điệp ghi nhận không chứa password, token, raw payload hoặc source reference. Chỉ kiểm tra response body là chưa đủ vì middleware có thể vẫn ghi request body vào log.

## 17. Checklist bảo vệ bí mật trong Jackson pipeline

Trước khi phát hành endpoint nhận hoặc trả JSON, hãy xác nhận:

1. Response dùng DTO allowlist hay đang serialize entity trực tiếp?
2. Getter/field mới có thể tự xuất hiện trong JSON không?
3. Password, token, hash, cookie, internal note có bị loại khỏi output không?
4. WRITE_ONLY, READ_ONLY và JsonIgnore có được dùng đúng chiều không?
5. Type metadata có tiết lộ class/package nội bộ không?
6. Object identity có phát ra database ID không?
7. View/filter có cấu hình mặc định an toàn và được test theo role không?
8. Có log trực tiếp request DTO, entity, Map hoặc JsonNode không?
9. Exception message, stack trace, path hoặc source reference có thể chứa input không?
10. HTTP filter, gateway, APM và broker có đang log raw body/header không?
11. Error response có echo raw value hoặc class name nội bộ không?
12. Log redaction có test với nested JSON, escaped value và payload sai cú pháp không?
13. Body size, nesting depth và token length đã có giới hạn chưa?
14. Log có request ID, retention và access control phù hợp không?

## 18. Ghi nhớ

- Jackson có thể tự phát hiện public getter/is-getter và property được annotation; field private có public getter vẫn có thể bị serialize.
- DTO response với allowlist field là cách rõ ràng để tránh vô tình đưa secret của entity ra ngoài.
- JsonIgnore loại property khỏi data binding thông thường; JsonProperty(WRITE_ONLY) cho phép nhận input nhưng không phát property khi serialize.
- JsonAutoDetect có thể giới hạn auto-detection; cấu hình visibility toàn mapper cần được áp dụng có chủ đích.
- Tránh Id.CLASS/Id.MINIMAL_CLASS trong JSON public; dùng logical type ID đã đăng ký như kind.
- JsonIdentityInfo có thể phát object ID; không để database key nội bộ trở thành public identity ngoài ý muốn.
- JsonView và JsonFilter cần cấu hình, authorization và test rõ ràng; không tự thay thế DTO allowlist.
- Annotation Jackson không che dữ liệu khỏi toString(), logger, APM, debugger hoặc heap dump.
- Không log raw request body, DTO chứa secret, exception message chưa lọc hoặc JsonLocation source reference.
- Log request ID, mã lỗi, loại exception và vị trí đã chọn lọc; trả client thông báo tổng quát cùng correlation ID.
- Redaction theo schema/allowlist đáng tin cậy hơn regex chung cho JSON tùy ý.
- Kiểm thử cả JSON response và log output để chứng minh secret không bị lộ ở bất kỳ đường nào.

