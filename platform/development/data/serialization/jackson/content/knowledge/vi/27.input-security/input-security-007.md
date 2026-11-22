# Kiểm soát creator, setter và mã tùy biến có tác động phụ

Khi Jackson đọc JSON thành object Java, nó có thể gọi constructor, static factory, setter, builder method, field mutator hoặc custom deserializer. Những điểm này là mã ứng dụng được kích hoạt bởi dữ liệu đầu vào. Nếu chúng thực hiện nhiều hơn việc tạo và gán dữ liệu, một request JSON có thể vô tình kích hoạt hành vi ngoài ý muốn như ghi database, phát sự kiện, tải tài nguyên, thay đổi trạng thái dùng chung hoặc gọi dịch vụ bên ngoài.

Đây là vấn đề bảo mật đầu vào, không chỉ là vấn đề thiết kế class. Một property JSON có thể làm thay đổi field nhạy cảm nếu model cho phép Jackson gán trực tiếp; một setter có side effect có thể chạy ngay trong lúc deserialize; một custom deserializer có thể gọi code có quyền cao hơn quyền của người gửi request. Vì vậy, cần kiểm soát rõ những constructor/factory/setter nào Jackson được phép gọi và giữ quá trình binding đơn giản, có giới hạn, dễ dự đoán.

Nguyên tắc quan trọng là chỉ deserialize vào kiểu được thiết kế cho boundary đó. Dùng request DTO với allowlist field, giữ constructor và setter thuần, kiểm tra dữ liệu trước khi tạo domain command, rồi để application service thực hiện authorization và nghiệp vụ. Không xem annotation hoặc custom deserializer như một hàng rào phân quyền độc lập.

## 1. Jackson có thể gọi mã nào khi deserialize?

Jackson không chỉ ghi giá trị trực tiếp vào bộ nhớ. Tùy kiểu model và cấu hình, nó có thể kích hoạt nhiều điểm mở rộng:

| Cơ chế | Cách Jackson sử dụng | Rủi ro nếu mã có side effect |
|---|---|---|
| Constructor mặc định | Tạo instance trước khi gán property | Constructor có thể mở resource hoặc thay đổi trạng thái ngoài object. |
| Constructor có tham số | Thu thập creator properties rồi gọi constructor | Có thể thực hiện hành động trước khi toàn bộ request được kiểm tra. |
| Static factory với JsonCreator | Gọi factory để tạo instance | Factory có thể truy vấn, ghi dữ liệu hoặc chọn implementation theo input. |
| Setter với JsonProperty/JsonSetter | Gọi setter khi đọc property | Setter có thể phát event, gọi repository hoặc cập nhật object khác. |
| Builder | Gọi builder method rồi build object | Builder method hoặc build() có thể chạy logic phụ. |
| Field mutator | Gán trực tiếp field nếu visibility/configuration cho phép | Có thể bỏ qua validation và setter guard. |
| Custom JsonDeserializer | Chạy code do ứng dụng định nghĩa | Có thể truy cập dependency, tài nguyên hoặc thực hiện thao tác vượt quá trách nhiệm binding. |
| Polymorphic type resolution | Chọn subtype theo type ID | Cấu hình quá rộng có thể cho phép khởi tạo kiểu không mong muốn. |

Ví dụ setter đơn giản:

```java
public class UserRequest {
    private String displayName;

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Setter này chỉ gán dữ liệu vào object, nên dễ dự đoán. Nhưng setter sau có hành vi khác:

```java
public void setEmail(String email) {
    this.email = email;
    emailService.sendVerificationEmail(email);
}
```

Khi Jackson đọc property email, setter có thể gửi email ngay lập tức. Nếu một field phía sau không hợp lệ khiến toàn bộ deserialize thất bại, email vẫn có thể đã được gửi. Nếu client gửi lặp property, setter còn có thể chạy nhiều lần.

Do đó, setter được Jackson gọi nên chỉ cập nhật trạng thái cục bộ của DTO/model. Side effect phải được thực hiện sau khi toàn bộ input đã được xác thực và use case đã kiểm tra quyền.

## 2. Phân biệt binding với thực thi nghiệp vụ

Deserialize nên trả lời các câu hỏi về dữ liệu:

- JSON có đúng cấu trúc không?
- Property nào được phép nhận?
- Giá trị có đúng kiểu và nằm trong giới hạn không?
- Field bắt buộc có mặt không?
- Object có thỏa invariant cơ bản để tồn tại không?

Application service/domain layer mới trả lời:

- Người gọi có quyền thay đổi tài nguyên này không?
- Trạng thái hiện tại có cho phép thao tác không?
- Có cần ghi database, phát event hoặc gọi dịch vụ ngoài không?
- Thao tác có hợp lệ trong transaction hiện tại không?

Không gọi các hành động ở nhóm thứ hai từ constructor, setter hoặc custom deserializer. Những điểm này được Jackson gọi trong quá trình chuyển đổi dữ liệu và có thể chạy trước khi ứng dụng hoàn tất validation hoặc authorization.

Một luồng xử lý rõ ràng:

```text
HTTP request
    |
    v
Jackson parser / databinding
    |
    v
Request DTO (chỉ dữ liệu)
    |
    v
DTO validation
    |
    v
Application service
    |
    +--> Authorization
    |
    +--> Domain rules
    |
    +--> Database / events / external services
    |
    v
Response
```

Đặt side effect sau authorization giúp tránh trường hợp người dùng không có quyền vẫn kích hoạt hành động chỉ bằng cách gửi một property.

## 3. Dùng request DTO thay vì deserialize trực tiếp vào entity

Một lỗi phổ biến là nhận JSON trực tiếp vào JPA entity hoặc domain aggregate:

```java
@PostMapping("/users/{id}")
public User update(
        @PathVariable Long id,
        @RequestBody User user) {
    return userRepository.save(user);
}
```

Nếu entity có property như role, enabled, ownerId, balance, passwordHash hoặc internalStatus và Jackson có thể gán chúng, client có thể gửi thêm field để thay đổi trạng thái ngoài ý muốn. Đây là dạng mass assignment/over-posting.

Tạo DTO chỉ chứa field mà endpoint cho phép:

```java
public record UpdateUserRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @Email
    String contactEmail
) {}
```

Controller chuyển DTO vào service:

```java
@PutMapping("/users/{id}")
public UserView update(
        @PathVariable Long id,
        @Valid @RequestBody UpdateUserRequest request,
        Authentication authentication) {

    return userService.updateProfile(
        id,
        authentication,
        request
    );
}
```

Service tải entity, xác thực quyền và gọi domain method:

```java
public UserView updateProfile(
        Long id,
        Authentication actor,
        UpdateUserRequest request) {

    User user = userRepository.findById(id)
        .orElseThrow(UserNotFoundException::new);

    authorization.requireCanEditProfile(actor, user);
    user.changeProfile(request.displayName(), request.contactEmail());

    return userMapper.toView(userRepository.save(user));
}
```

Trong ví dụ này, client không thể gán role hoặc ownerId vì chúng không thuộc request DTO. Service quyết định tài nguyên nào được cập nhật và trong điều kiện nào. Nếu một endpoint thực sự cho phép thay đổi role, nên có command riêng và authorization riêng cho hành động đó.

## 4. Kiểm soát creator bằng JsonCreator

Jackson có thể dùng constructor hoặc static factory được đánh dấu JsonCreator. Đây là cách tốt để tạo object bất biến, nhưng creator vẫn là mã được gọi bởi dữ liệu đầu vào.

Ví dụ:

```java
public final class Money {
    private final BigDecimal amount;
    private final String currency;

    @JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
    public Money(
            @JsonProperty(value = "amount", required = true)
            BigDecimal amount,
            @JsonProperty(value = "currency", required = true)
            String currency) {

        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("invalid currency code");
        }

        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() { return amount; }
    public String getCurrency() { return currency; }
}
```

Creator nhận các giá trị đã được Jackson ánh xạ, kiểm tra invariant cục bộ rồi tạo object. Constructor không truy vấn database, không phát event và không gọi dịch vụ ngoài. Nhờ vậy, object chỉ được tạo khi các điều kiện cơ bản đã thỏa mãn.

### 4.1. Chọn creator mode tường minh

JsonCreator có các mode chính:

| Mode | Ý nghĩa |
|---|---|
| PROPERTIES | Các tham số được bind từ property JSON có tên. |
| DELEGATING | Toàn bộ giá trị JSON được bind vào một tham số creator. |
| DEFAULT | Jackson tự chọn cách diễn giải theo metadata và quy tắc creator. |

Với object có nhiều property, PROPERTIES thường rõ ràng:

```java
@JsonCreator(mode = JsonCreator.Mode.PROPERTIES)
public SearchRequest(
    @JsonProperty("query") String query,
    @JsonProperty("page") Integer page) {
    // Validate and assign.
}
```

Với value object đại diện cho một scalar, DELEGATING có thể phù hợp:

```java
public final class CountryCode {
    private final String value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public CountryCode(String value) {
        if (value == null || !value.matches("[A-Z]{2}")) {
            throw new IllegalArgumentException("invalid country code");
        }
        this.value = value;
    }
}
```

Mode tường minh giúp tránh cách hiểu khác nhau khi class có nhiều constructor/factory. Hãy cung cấp tên property rõ ràng bằng JsonProperty; không dựa vào tên tham số Java nếu cấu hình compiler hoặc parameter-name module không bảo đảm metadata đó.

### 4.2. Creator phải kiểm tra dữ liệu trước khi tạo trạng thái

Creator nên:

- Xác nhận null và required values.
- Kiểm tra range và format cục bộ.
- Chuẩn hóa giá trị nếu contract quy định.
- Gán tất cả field final.
- Không để object ở trạng thái nửa khởi tạo.

Creator không nên:

- Ghi database hoặc gửi message.
- Gọi API bên ngoài.
- Dựa vào user/session hiện tại để quyết định quyền.
- Lưu object vào cache toàn cục.
- Thực hiện thao tác có thể cần rollback nếu property phía sau không hợp lệ.

Constructor có thể ném IllegalArgumentException khi invariant sai; Jackson thường bọc lỗi khởi tạo trong exception mapping. Ở API boundary, chuyển nó thành lỗi validation phù hợp mà không trả stack trace nội bộ cho client.

### 4.3. Kiểm soát creator property bị thiếu và null

Với creator-based binding, có thể bật:

```java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
    .enable(DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES)
    .build();
```

- FAIL_ON_MISSING_CREATOR_PROPERTIES từ chối creator property không xuất hiện.
- FAIL_ON_NULL_CREATOR_PROPERTIES từ chối creator property nhận explicit null.

Hai trạng thái này khác nhau. Cấu hình ở cấp mapper có thể tác động đến nhiều DTO, vì vậy chỉ bật khi contract của mapper thực sự yêu cầu mọi creator property đều bắt buộc. Nếu chỉ một field cần bắt buộc, dùng validation/creator logic phù hợp cho kiểu đó.

JsonProperty(required = true) chủ yếu là metadata cho creator property; không coi nó là validation tổng quát cho mọi mutable field hoặc setter. Với field mutable, hãy xác nhận presence bằng validation hoặc custom deserializer.

## 5. Kiểm soát setter và JsonSetter

Setter là điểm Jackson có thể gọi trong lúc đọc từng property. Setter tốt nên chỉ kiểm tra và gán giá trị vào object hiện tại:

```java
public class ProfileRequest {
    private String displayName;

    @JsonSetter("displayName")
    public void setDisplayName(String displayName) {
        if (displayName != null && displayName.length() > 80) {
            throw new IllegalArgumentException("displayName is too long");
        }
        this.displayName = displayName;
    }
}
```

Không thực hiện các hành động như gửi email, ghi audit event, gọi repository hoặc cập nhật object khác từ setter. Nếu setter được gọi hai lần do input có duplicate property, các side effect cũng có thể bị lặp.

### 5.1. JsonSetter và chính sách null

JsonSetter cho phép kiểm soát cách xử lý explicit null:

```java
public class CreateUserRequest {
    private String username;

    @JsonSetter(
        value = "username",
        nulls = Nulls.FAIL
    )
    public void setUsername(String username) {
        this.username = username;
    }
}
```

Một số chính sách null thường dùng:

| Chính sách | Hành vi |
|---|---|
| SET | Gán null cho property theo kiểu đích. |
| SKIP | Bỏ qua việc gán khi input là null. |
| FAIL | Báo lỗi khi gặp explicit null. |
| AS_EMPTY | Dùng giá trị empty do deserializer của kiểu đích cung cấp. |
| DEFAULT | Dùng chính sách mặc định của Jackson. |

Có thể dùng contentNulls để kiểm soát phần tử null bên trong collection/map. Ví dụ:

```java
@JsonSetter(contentNulls = Nulls.FAIL)
public void setTags(List<String> tags) {
    this.tags = tags;
}
```

Điều này từ chối phần tử null trong collection khi Jackson áp dụng setter đó. Hãy phân biệt null của cả property với null của từng phần tử. Một list null và một list có phần tử null là hai input khác nhau.

### 5.2. Missing không giống explicit null

JsonSetter null policy chỉ áp dụng khi property xuất hiện với JSON null. Nếu property không xuất hiện, setter thường không được gọi và field giữ giá trị khởi tạo/default. Vì vậy:

- Missing: không có lời gọi setter.
- Explicit null: setter/deserializer nhận null theo null policy.
- Empty string: setter nhận chuỗi rỗng.

Với PATCH, cần một kiểu biểu diễn presence riêng nếu muốn phân biệt ba trạng thái. Không dùng giá trị null cuối cùng để suy ra client đã gửi property hay chưa.

### 5.3. Setter không nên phụ thuộc thứ tự field

Jackson đọc property theo thứ tự token trong input. Một setter có thể được gọi trước hoặc sau setter khác tùy JSON. Không viết setter giả định một field khác đã được gán:

```java
public void setEndDate(LocalDate endDate) {
    if (endDate.isBefore(startDate)) {
        throw new IllegalArgumentException("endDate precedes startDate");
    }
    this.endDate = endDate;
}
```

Nếu startDate xuất hiện sau endDate, giá trị mà setter nhìn thấy có thể chưa được cập nhật. Hãy thu thập dữ liệu rồi kiểm tra quan hệ giữa các field trong constructor, creator hoặc bước validation sau binding.

## 6. Builder cũng là mã được Jackson gọi

Với @JsonDeserialize(builder = ...), Jackson gọi builder method cho từng property rồi gọi build():

```java
@JsonDeserialize(builder = UserCommand.Builder.class)
public final class UserCommand {
    private final String username;
    private final String displayName;

    private UserCommand(Builder builder) {
        this.username = builder.username;
        this.displayName = builder.displayName;
    }

    @JsonPOJOBuilder(withPrefix = "")
    public static class Builder {
        private String username;
        private String displayName;

        public Builder username(String value) {
            this.username = value;
            return this;
        }

        public Builder displayName(String value) {
            this.displayName = value;
            return this;
        }

        public UserCommand build() {
            return new UserCommand(this);
        }
    }
}
```

Builder method và build() đều chạy trong quá trình deserialize. Vì vậy, chúng cũng phải tránh side effect. Có thể kiểm tra format/range trong build() và tạo object bất biến sau khi tất cả property đã được thu thập.

Không gửi message hoặc lưu database từ từng builder method. Nếu build() thực hiện side effect, một lỗi ở bước binding/response có thể để lại thay đổi ngoài ý muốn. Giữ builder là bộ thu thập dữ liệu và để application service thực hiện nghiệp vụ.

## 7. Tránh field mutator vô tình mở rộng bề mặt ghi

Jackson có thể phát hiện property thông qua getter/setter, field visibility, annotation và mapper features. Việc một field private không có setter không phải lúc nào cũng đồng nghĩa nó không thể được gán: annotation, mix-in hoặc visibility configuration có thể làm thay đổi khả năng truy cập.

Không cấu hình mapper theo kiểu mở toàn bộ private field của mọi class nếu không có nhu cầu rõ ràng. Với boundary nhận dữ liệu không tin cậy:

- Chỉ expose property được phép trong request DTO.
- Tránh bind trực tiếp vào entity/domain aggregate.
- Kiểm tra mix-in và visibility override.
- Không dùng setter/field mutator để cho client sửa ID, owner, role hoặc trạng thái nội bộ.
- Dùng command riêng cho hành động nhạy cảm.

### 7.1. JsonProperty.Access

JsonProperty.Access có thể diễn tả hướng truy cập:

```java
public class AccountView {
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String accountId;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String newPassword;
}
```

- READ_ONLY: property được dùng khi serialize nhưng không được nhận từ input trong quá trình deserialize.
- WRITE_ONLY: property được nhận khi deserialize nhưng không được đưa ra output.
- READ_WRITE: property có thể tham gia cả hai chiều.

Đây là quy tắc mapping, không phải authorization. READ_ONLY có thể giúp ngăn client gán một field qua databinding chuẩn, nhưng service vẫn phải xác định ai được phép thay đổi field đó qua use case. WRITE_ONLY phù hợp với input như mật khẩu mới, nhưng ứng dụng vẫn phải hash/validate mật khẩu ở service trước khi lưu.

Nếu property được expose qua custom deserializer hoặc một đường binding khác, hãy kiểm tra behavior thực tế bằng test. Không dựa duy nhất vào annotation trên entity để bảo vệ dữ liệu nhạy cảm.

## 8. Unknown property và duplicate property

Với request command, field không biết có thể là dấu hiệu client gửi nhầm tên hoặc cố thử một property nội bộ. Có thể giữ strict unknown-property handling:

```java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
```

Trong vanilla Jackson Databind, feature này thường được bật mặc định; framework hoặc cấu hình ứng dụng có thể tắt. Kiểm tra mapper thật sự đang dùng thay vì dựa vào default.

Nếu cần bỏ qua field mới cho response/event consumer, chỉ bật ignore unknown cho DTO phù hợp bằng JsonIgnoreProperties(ignoreUnknown = true) hoặc mapper riêng. Không tắt strict mode toàn hệ thống nếu các command cần phát hiện field lạ.

Duplicate property là trường hợp riêng:

```json
{
  "role": "user",
  "role": "admin"
}
```

Nếu parser chấp nhận duplicate, setter có thể được gọi nhiều lần và giá trị sau có thể ghi đè giá trị trước. Bật strict duplicate detection:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Duplicate detection ở parser giúp phát hiện sớm và áp dụng nhất quán trước khi setter/creator xử lý các giá trị mâu thuẫn. Với custom deserializer, có thể giữ cờ seen để đưa ra lỗi theo tên field cụ thể.

## 9. Kiểm soát custom deserializer

Custom deserializer là mã do ứng dụng viết và được gọi khi Jackson gặp kiểu tương ứng. Nó có thể làm mọi thứ mà code Java được cấp quyền có thể làm; vì vậy, cần giới hạn trách nhiệm của nó.

Deserializer nên:

- Đọc token theo contract.
- Xác nhận token type, presence và range.
- Giới hạn string, collection và nesting khi cần.
- Tạo DTO/value object qua constructor/factory thuần.
- Ném JsonMappingException có thông tin field hữu ích khi input sai.
- Dùng DeserializationContext để tái sử dụng deserializer và cấu hình Jackson phù hợp.

Deserializer không nên:

- Ghi database hoặc cập nhật entity đang tồn tại.
- Gửi email, message hoặc webhook.
- Gọi API bên ngoài.
- Đọc file tùy ý theo đường dẫn client gửi.
- Thực hiện authorization dựa trên dữ liệu do client tự khai.
- Truy cập singleton mutable để lưu trạng thái giữa các request.

Ví dụ một custom deserializer thuần:

```java
public final class PositiveAmountDeserializer
        extends JsonDeserializer<BigDecimal> {

    @Override
    public BigDecimal deserialize(
            JsonParser parser,
            DeserializationContext context) throws IOException {

        if (!parser.currentToken().isNumeric()) {
            throw JsonMappingException.from(
                parser, "amount must be a JSON number"
            );
        }

        BigDecimal value = parser.getDecimalValue();
        if (value.signum() <= 0 || value.scale() > 2
                || value.precision() > 14) {
            throw JsonMappingException.from(
                parser, "amount is outside the allowed range"
            );
        }

        return value;
    }
}
```

Deserializer chỉ kiểm tra representation và trả về value. Nó không biết tài khoản có đủ số dư hay không; service kiểm tra điều đó khi thực hiện use case.

### 9.1. Không lưu request context mutable trong deserializer dùng chung

Jackson có thể cache serializer/deserializer và tái sử dụng chúng giữa nhiều lần đọc. Không giữ một field mutable như currentUser, currentTenant hoặc currentRequest trong instance deserializer dùng chung:

```java
// Không an toàn nếu deserializer được chia sẻ giữa các request.
private User currentUser;
```

Hai request đồng thời có thể ghi đè context của nhau. Nếu cần contextual configuration, dùng ContextualDeserializer để tạo instance cấu hình bất biến dựa trên metadata property. Nếu cần actor/tenant, truyền thông tin đó qua application service sau khi DTO đã được tạo và xác thực, không nhúng request state vào deserializer singleton.

## 10. Polymorphic deserialization và lựa chọn subtype an toàn

JSON đa hình có thể chứa discriminator để Jackson chọn class con. Cấu hình quá rộng có thể cho phép input chọn kiểu Java mà ứng dụng không dự kiến.

Ưu tiên ID logic có allowlist:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
})
public abstract class PaymentCommand {
}
```

Client chỉ có thể chọn subtype trong danh sách được đăng ký. Không dùng type ID do client gửi để nạp class tùy ý.

Tránh dùng Id.CLASS hoặc permissive default typing cho JSON không tin cậy. Nếu ứng dụng thực sự cần default typing, phải cấu hình PolymorphicTypeValidator với allowlist base type/subtype phù hợp và kiểm thử input không được phép. Không bật cơ chế polymorphic typing rộng chỉ để giải quyết việc deserialize interface/abstract class.

Ngay cả với Id.NAME, subtype được đăng ký vẫn có constructor/setter/deserializer riêng. Hãy kiểm tra các điểm khởi tạo của từng subtype và bảo đảm chúng không thực hiện side effect khi Jackson tạo object.

## 11. JacksonInject và dữ liệu được inject

Jackson có thể inject giá trị từ cấu hình mapper thông qua JacksonInject:

```java
public class ImportRequest {
    private String fileName;
    private String tenantId;

    @JacksonInject("importPolicy")
    private ImportPolicy importPolicy;
}
```

Giá trị inject đến từ InjectableValues hoặc cơ chế cấu hình của mapper, không phải từ property JSON thông thường. Đây có thể là cách cung cấp dependency/configuration cho một số model, nhưng cần phân biệt dữ liệu tin cậy do server cấp với dữ liệu do client gửi.

Không inject service có side effect vào request DTO rồi gọi nó từ setter/creator. Việc đó làm cho quá trình deserialize phụ thuộc container state và khiến code khó kiểm thử. Dependency nghiệp vụ nên được sử dụng trong service sau binding.

Nếu dùng JacksonInject, chỉ đăng ký giá trị tin cậy ở mapper scope phù hợp. Không để client quyết định injectable value bằng cách gửi tên property hoặc type ID.

## 12. Constructor, setter và lỗi một phần

Một lý do khác để tránh side effect trong quá trình binding là deserialize có thể thất bại giữa chừng:

```json
{
  "displayName": "An",
  "email": "an@example.test",
  "age": "not-a-number"
}
```

Jackson có thể đã gọi setter cho displayName và email trước khi gặp lỗi ở age. Nếu setter đã ghi database hoặc phát event, một phần tác động đã xảy ra dù toàn bộ request không tạo được object.

Nếu setter chỉ gán vào DTO cục bộ, object lỗi sẽ không được trả cho service và có thể bị loại bỏ an toàn. Đây là lý do binding code nên tránh side effect.

Không cố rollback side effect trong catch của deserializer. Deserializer không phải transaction coordinator và có thể không biết mọi hành động đã xảy ra. Hãy chuyển các hành động ra khỏi binding để chỉ bắt đầu sau khi input hoàn chỉnh, hợp lệ và được authorization.

## 13. Giới hạn tài nguyên cũng là một phần của kiểm soát input

Ngay cả creator/setter thuần cũng có thể bị khai thác để tiêu tốn tài nguyên nếu input quá lớn. Cần giới hạn ở nhiều tầng:

- HTTP server/API gateway giới hạn request body bytes và timeout.
- Jackson Core giới hạn nesting depth, string length và number length bằng StreamReadConstraints.
- Custom deserializer giới hạn số phần tử, số map entry hoặc tổng node trước khi cấp phát.
- Domain constructor kiểm tra range và invariant cuối cùng.

Ví dụ cấu hình Jackson Core (API StreamReadConstraints có từ Jackson Core 2.15):

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(32)
    .maxStringLength(4_096)
    .maxNumberLength(64)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Các giới hạn ví dụ cần được điều chỉnh theo contract và workload. StreamReadConstraints không thay thế giới hạn request body hoặc giới hạn số phần tử array. Không dùng một ngưỡng chung cho mọi endpoint nếu chúng có nhu cầu khác nhau; có thể cấu hình factory/mapper riêng cho boundary có payload đặc biệt.

## 14. Không dùng annotation làm cơ chế authorization

Các annotation như JsonIgnore, JsonProperty.Access.READ_ONLY, JsonSetter(nulls = FAIL) và JsonIgnoreProperties kiểm soát hành vi mapping. Chúng không trả lời câu hỏi người dùng có quyền thực hiện thao tác hay không.

Ví dụ READ_ONLY có thể ngăn property được gán qua databinding chuẩn, nhưng:

- Một endpoint khác có thể dùng DTO khác.
- Một custom deserializer có thể xử lý property theo cách riêng.
- Service có thể cập nhật field qua một đường code khác.
- Quyền thay đổi field có thể phụ thuộc actor, resource owner hoặc trạng thái hiện tại.

Vì vậy:

1. DTO chỉ chứa các field mà endpoint cho phép nhận.
2. Service xác thực actor và resource trước khi thay đổi.
3. Domain method bảo vệ invariant.
4. Annotation chỉ hỗ trợ contract serialize/deserialize.
5. Test authorization độc lập với test Jackson mapping.

Đừng cho client gửi role, ownerId, isAdmin hoặc trạng thái nội bộ chỉ vì setter có thể kiểm tra một phần giá trị. Những field đó cần command và quyền riêng nếu thực sự được phép thay đổi.

## 15. Kiểm thử creator, setter và custom code

Test nên xác nhận cả giá trị được bind và việc binding không kích hoạt side effect.

### 15.1. Test creator validation

```java
@Test
void rejectsInvalidMoneyDuringCreation() {
    String json = """
        {"amount":-10,"currency":"USD"}
        """;

    assertThrows(JsonMappingException.class, () ->
        mapper.readValue(json, Money.class)
    );
}
```

Test này xác nhận constructor invariant được áp dụng khi Jackson tạo value object. Exception cụ thể có thể được bọc theo Jackson version; ở API boundary, kiểm tra lỗi mapping được chuyển thành response validation phù hợp.

### 15.2. Test setter không gây side effect

Tạo DTO setter thuần và service mock. Deserialize request rồi xác nhận service chưa được gọi. Chỉ khi application service được gọi sau validation/authorization, side effect mới được thực hiện.

Không viết test phụ thuộc vào thứ tự setter nếu thứ tự property không thuộc contract.

### 15.3. Test field không được phép

Gửi request chứa field như role hoặc ownerId:

```json
{
  "displayName": "An",
  "role": "ADMIN",
  "ownerId": "someone-else"
}
```

Xác nhận request DTO không thể thay đổi các giá trị nội bộ. Nếu endpoint dùng strict unknown-property handling, xác nhận field lạ bị từ chối. Nếu endpoint cố ý ignore unknown, xác nhận các field đó không ảnh hưởng domain state.

### 15.4. Test null và duplicate

Test:

- Required creator property bị thiếu.
- Required creator property explicit null.
- Setter nhận explicit null với Nulls.FAIL.
- Property bị thiếu không gọi setter và giữ default đúng contract.
- Duplicate property bị parser từ chối.
- Collection có phần tử null khi contentNulls = FAIL.

### 15.5. Test custom deserializer không gọi dịch vụ

Dùng mock/fake service để xác nhận deserialize không gọi repository, message publisher hoặc HTTP client. Sau khi DTO được tạo, service mới thực hiện thao tác tương ứng trong use case.

### 15.6. Test polymorphic allowlist

Kiểm tra:

- Type ID hợp lệ tạo đúng subtype.
- Type ID chưa đăng ký bị từ chối hoặc đi vào fallback đã định nghĩa.
- Type ID không thể chọn class ngoài allowlist.
- Constructor/setter của từng subtype không có side effect ngoài ý muốn.

## 16. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Request JSON làm gửi email hoặc phát event | Setter thực hiện side effect | Chuyển hành động sang application service sau validation/authorization. |
| Client sửa được role/owner/status | Deserialize trực tiếp vào entity có writable property | Dùng request DTO allowlist và command riêng cho field nhạy cảm. |
| Setter kiểm tra sai khi field khác chưa được gán | Phụ thuộc thứ tự property trong JSON | Validate quan hệ sau khi thu thập đầy đủ dữ liệu. |
| Object được tạo dù thiếu field quan trọng | Creator/default value không có required policy | Dùng creator validation hoặc missing/null creator features phù hợp. |
| Explicit null bị chấp nhận ngoài ý muốn | Setter dùng null policy mặc định | Dùng JsonSetter(nulls = FAIL) hoặc validation cụ thể. |
| Builder gây cập nhật một phần | Builder method/build() có side effect | Giữ builder thuần và chỉ tạo object sau khi input hoàn chỉnh. |
| Custom deserializer rò context giữa request | Lưu actor/tenant mutable trong instance được cache | Dùng instance bất biến/contextualization; truyền actor vào service. |
| Input chọn subtype không mong muốn | Polymorphic typing quá rộng | Dùng Id.NAME với allowlist; tránh Id.CLASS/permissive default typing. |
| Deserialize lỗi nhưng side effect vẫn xảy ra | Side effect chạy trước khi toàn bộ JSON hợp lệ | Không thực hiện side effect trong creator/setter/deserializer. |
| Annotation bị coi là bảo đảm phân quyền | Nhầm mapping policy với authorization | Kiểm tra quyền trong application service và test riêng. |

## 17. Quy trình thiết kế an toàn

1. Xác định boundary nhận JSON và tạo request DTO riêng cho endpoint.
2. Chỉ expose những property endpoint cho phép client gửi; tránh bind trực tiếp vào entity/aggregate.
3. Dùng JsonCreator với mode tường minh cho immutable value object và kiểm tra invariant cục bộ trong constructor.
4. Giữ setter/builder method thuần, không truy cập repository, gửi message hoặc gọi API.
5. Dùng JsonSetter null policy để diễn tả rõ explicit null; phân biệt missing với null khi contract yêu cầu.
6. Kiểm tra creator property bắt buộc bằng constructor/validation và feature phù hợp.
7. Hạn chế field mutator, visibility override và mix-in làm tăng property writable ngoài dự kiến.
8. Giữ strict unknown/duplicate handling cho command nhạy cảm; chỉ ignore unknown ở boundary có chủ đích.
9. Viết custom deserializer chỉ cho parsing, giới hạn và mapping; không đặt side effect hoặc authorization trong đó.
10. Với polymorphism, dùng subtype ID ổn định và allowlist; không nạp class tùy ý từ input.
11. Đặt giới hạn request/token/collection để binding không tiêu tốn tài nguyên quá mức.
12. Thực hiện authorization, business rule và side effect sau khi DTO đã được tạo và xác thực.
13. Test field nhạy cảm, setter/creator side effect, null/missing, duplicate, subtype và lỗi giữa chừng.

Jackson có thể gọi constructor, factory, setter, builder và custom deserializer ngay trong lúc xử lý input. Hãy xem mỗi điểm đó như một phần của bề mặt nhận dữ liệu không tin cậy. Khi các điểm khởi tạo chỉ làm nhiệm vụ parse, validate cấu trúc và tạo object cục bộ, còn authorization và side effect nằm trong application service, request lỗi sẽ không để lại thay đổi một phần và client không thể dùng property binding để kích hoạt hành động ngoài quyền hạn.
