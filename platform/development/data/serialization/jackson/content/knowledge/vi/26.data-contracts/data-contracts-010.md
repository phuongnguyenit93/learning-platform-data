# Giữ ý nghĩa của null, thiếu và mặc định qua các phiên bản

Trong JSON, một property có thể **không xuất hiện**, xuất hiện với giá trị **null**, hoặc xuất hiện với một **giá trị cụ thể**. Ba trạng thái này thường bị gộp nhầm thành “không có dữ liệu”, nhưng chúng có ý nghĩa khác nhau đối với API và dữ liệu được lưu lâu dài.

Ví dụ, ba payload sau không tương đương:

```json
{}
```

```json
{"nickname": null}
```

```json
{"nickname": "An"}
```

Property bị thiếu có thể có nghĩa “sender không gửi thông tin này” hoặc “hãy giữ giá trị hiện tại”. JSON null có thể có nghĩa “xóa giá trị” hoặc “giá trị được biết là rỗng”. Một giá trị cụ thể có nghĩa “đặt thành giá trị đó”. Nếu ứng dụng thay đổi cách serialize hoặc deserialize mà không giữ các phân biệt này, phiên bản mới có thể làm mất dữ liệu, ghi đè giá trị ngoài ý muốn hoặc phá vỡ tương thích với consumer cũ.

Trong Jackson, cần thiết kế riêng hai chiều:

- **Serialization:** quyết định khi nào property có giá trị null, rỗng hoặc mặc định được ghi ra JSON hay bị bỏ qua.
- **Deserialization:** quyết định điều gì xảy ra khi property có mặt, bị thiếu hoặc có giá trị null.

Chính sách của hai chiều không tự động đối xứng. Bỏ field null khi serialize không có nghĩa mọi field bị thiếu khi deserialize sẽ được đặt thành null; cũng không có nghĩa Jackson tự áp dụng giá trị mặc định nghiệp vụ.

## 1. Ba trạng thái của một property

Xét property nickname:

| Trạng thái JSON | Ví dụ | Ý nghĩa thường gặp |
|---|---|---|
| Thiếu (absent/missing) | `{}` | Không cung cấp thông tin về property |
| Có mặt với null | `{"nickname": null}` | Có cung cấp thông tin và giá trị được xác định là null |
| Có mặt với giá trị | `{"nickname": "An"}` | Đặt hoặc thay thế bằng giá trị cụ thể |

Ứng dụng phải xác định ý nghĩa theo từng contract. Với một API tạo user, missing và null có thể đều dẫn đến nickname chưa có. Với API cập nhật hồ sơ, missing thường có nghĩa “không thay đổi”, còn null có thể có nghĩa “xóa nickname”.

Một JSON object cũng có thể chứa giá trị rỗng nhưng không null:

```json
{
  "nickname": "",
  "tags": [],
  "metadata": {}
}
```

String rỗng, array rỗng và object rỗng vẫn là các giá trị JSON có mặt. Chúng khác cả missing lẫn null.

## 2. Serialization: khi nào ghi null, rỗng hoặc default?

Với bean thông thường, Jackson thường ghi property reference có giá trị null thành JSON null:

```java
public record Profile(String name, String nickname) {}

Profile profile = new Profile("An", null);
String json = mapper.writeValueAsString(profile);
```

JSON có dạng:

```json
{
  "name": "An",
  "nickname": null
}
```

Nếu contract yêu cầu luôn thể hiện property, kể cả null, dùng inclusion ALWAYS:

```java
@JsonInclude(JsonInclude.Include.ALWAYS)
public record Profile(String name, String nickname) {}
```

Nếu muốn bỏ property null, dùng NON_NULL:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record Profile(String name, String nickname) {}
```

Với nickname null, output chỉ còn name. NON_NULL chỉ bỏ giá trị null; string rỗng, collection rỗng và map rỗng vẫn có thể được ghi.

Các chính sách inclusion thường gặp:

| Include | Điều kiện bỏ qua điển hình |
|---|---|
| ALWAYS | Không bỏ qua property theo giá trị |
| NON_NULL | Bỏ qua giá trị Java null |
| NON_ABSENT | Bỏ qua null và giá trị absent của kiểu hỗ trợ absent, ví dụ Optional.empty() với module tương ứng |
| NON_EMPTY | Bỏ qua null và giá trị được xem là rỗng như string rỗng, collection/map rỗng, array rỗng |
| NON_DEFAULT | Bỏ qua giá trị được xem là mặc định theo quy tắc Jackson cho scope/configuration |
| CUSTOM | Dùng filter do ứng dụng định nghĩa |

Ví dụ NON_EMPTY:

```java
@JsonInclude(JsonInclude.Include.NON_EMPTY)
public record SearchResponse(
        String query,
        List<String> results,
        Map<String, String> facets
) {}
```

Nếu results là list rỗng và facets là map rỗng, các property đó có thể bị bỏ qua. Điều này có thể làm consumer không phân biệt được “đã tìm kiếm và không có kết quả” với “server không cung cấp field”.

NON_DEFAULT cần được dùng thận trọng. Giá trị mặc định có thể phụ thuộc loại property, giá trị primitive mặc định, constructor mặc định hoặc scope của inclusion. Đừng giả định giá trị nghiệp vụ như status = "NEW" sẽ tự được xem là default theo ý muốn.

Inclusion có thể được đặt ở cấp class, property hoặc mapper. Quy tắc property-level có thể ghi đè chính sách chung. Hãy xác định rõ chính sách cho từng contract.

## 3. Serialization và deserialization là hai chính sách riêng

Giả sử serializer bỏ nickname khi null:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record Profile(String name, String nickname) {}
```

Khi ghi object có nickname null, JSON là:

```json
{"name":"An"}
```

Khi đọc JSON này, Jackson không thấy property nickname. Với bean mutable, field có thể giữ giá trị được khởi tạo trước đó hoặc giá trị Java mặc định. Với record creator, tham số có thể nhận null hoặc giá trị primitive mặc định tương ứng, tùy kiểu và cấu hình.

Không thể suy ra từ NON_NULL rằng Jackson sẽ áp dụng default nghiệp vụ như "Guest". JsonInclude chỉ điều khiển serialization.

Tương tự, cấu hình deserialization cho null không quyết định null có được ghi ra hay không. Hãy kiểm tra hai chiều riêng biệt bằng test.

## 4. Missing property trong bean mutable

Xét class có field initializer:

```java
public class UserPreferences {
    private String theme = "light";
    private boolean emailEnabled = true;

    public String getTheme() {
        return theme;
    }

    public void setTheme(String theme) {
        this.theme = theme;
    }

    public boolean isEmailEnabled() {
        return emailEnabled;
    }

    public void setEmailEnabled(boolean emailEnabled) {
        this.emailEnabled = emailEnabled;
    }
}
```

Nếu JSON không chứa theme và emailEnabled, Jackson thường không gọi setter cho các property đó. Giá trị được khởi tạo trong field initializer/constructor có thể được giữ nguyên.

Với JSON:

```json
{}
```

giá trị có thể là theme = "light" và emailEnabled = true.

Nếu JSON gửi:

```json
{
  "theme": null,
  "emailEnabled": false
}
```

theme đi qua chính sách null của property; emailEnabled được gán false. Với reference property, null thường được gán. Với primitive, hãy chú ý FAIL_ON_NULL_FOR_PRIMITIVES.

Điểm cần nhớ: missing thường không kích hoạt setter; explicit null là một input value và có thể kích hoạt chính sách xử lý null.

## 5. Điều khiển explicit null bằng JsonSetter

@JsonSetter cho phép chỉ định Jackson xử lý JSON null như thế nào cho một property. Thuộc tính nulls áp dụng cho property; contentNulls áp dụng cho phần tử null bên trong container.

| Nulls | Hành vi |
|---|---|
| SET | Gán null theo hành vi thông thường |
| SKIP | Bỏ qua việc gán khi input là null; giá trị hiện có/initializer được giữ |
| FAIL | Từ chối input null |
| AS_EMPTY | Dùng giá trị empty do deserializer của kiểu đích cung cấp |
| DEFAULT | Dùng chính sách null mặc định của Jackson |

Bỏ qua explicit null:

```java
public class UserPreferences {
    private String theme = "light";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setTheme(String theme) {
        this.theme = theme;
    }

    public String getTheme() {
        return theme;
    }
}
```

Với {"theme": null}, setter bị bỏ qua và theme giữ "light" nếu object được tạo với initializer đó.

Từ chối null:

```java
@JsonSetter(nulls = Nulls.FAIL)
public void setEmail(String email) {
    this.email = email;
}
```

Nếu JSON chứa email null, Jackson báo lỗi mapping thay vì gọi setter với null.

Dùng empty value:

```java
@JsonSetter(nulls = Nulls.AS_EMPTY)
public void setTags(List<String> tags) {
    this.tags = tags;
}
```

Hành vi empty phụ thuộc deserializer của kiểu đích. Với collection thông thường, empty value thường là collection rỗng.

DEFAULT không có nghĩa là lấy một giá trị nghiệp vụ từ annotation. Nó quay về chính sách null mặc định của Jackson.

## 6. Null trong phần tử collection: contentNulls

Một property collection có thể không null nhưng phần tử bên trong chứa null:

```json
{
  "tags": ["java", null, "jackson"]
}
```

Dùng contentNulls để điều khiển phần tử null:

```java
public class UserPreferences {
    @JsonSetter(contentNulls = Nulls.SKIP)
    private List<String> tags = new ArrayList<>();
}
```

Phân biệt:
- nulls: property tags tự nó là null.
- contentNulls: một phần tử bên trong tags là null.

Do đó {"tags": null} khác {"tags": ["java", null]}.

## 7. Creator property: missing và null

Với constructor/property creator, Jackson phải tạo object bằng cách gọi constructor. Nếu property bị thiếu, tham số creator vẫn phải nhận một giá trị nào đó; không thể đơn giản “không gọi setter” như bean mutable.

```java
public record Account(
        String accountNumber,
        BigDecimal balance
) {}
```

Input thiếu balance:

```json
{"accountNumber":"AC-001"}
```

Tùy kiểu tham số và cấu hình, Jackson có thể truyền null cho BigDecimal. Nếu cần từ chối creator property bị thiếu, bật:

```java
ObjectMapper strictMapper = JsonMapper.builder()
        .enable(DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES)
        .build();
```

Để từ chối creator property nhận explicit null:

```java
strictMapper.enable(
        DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES
);
```

Với primitive, có thể bật:

```java
strictMapper.enable(
        DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES
);
```

Các feature này có phạm vi ảnh hưởng rộng trên mapper/reader. Nếu chỉ một DTO cần chính sách nghiêm ngặt, cân nhắc cấu hình ObjectReader riêng hoặc validation ở tầng DTO/service.

@JsonProperty(required = true) có thể biểu đạt yêu cầu bắt buộc, đặc biệt với creator property; hành vi phụ thuộc loại property, creator và version. Hãy test rõ cả missing lẫn explicit null.

## 8. Giá trị mặc định thực sự đến từ đâu?

Một default có thể được thiết lập ở nhiều tầng:

1. Java field initializer: giá trị gán khi object được tạo.
2. Constructor: constructor đặt giá trị nếu tham số không cung cấp.
3. Builder: builder giữ default trước khi build().
4. Deserializer: custom deserializer hoặc null provider chuyển input theo quy tắc.
5. Service/domain layer: ứng dụng áp dụng default nghiệp vụ sau khi parse.
6. Migration layer: dữ liệu từ phiên bản cũ được chuyển đổi theo schema version.

Ví dụ field initializer:

```java
public class NotificationSettings {
    private boolean enabled = true;
    private String channel = "email";
}
```

Nếu JSON không chứa property và Jackson tạo bean rồi gán các property xuất hiện, initializer có thể được giữ lại.

Ví dụ constructor áp dụng default:

```java
public final class RetryPolicy {
    private final int maxAttempts;

    @JsonCreator
    public RetryPolicy(
            @JsonProperty("maxAttempts") Integer maxAttempts
    ) {
        this.maxAttempts = maxAttempts == null ? 3 : maxAttempts;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }
}
```

Ví dụ này gộp missing và explicit null thành cùng default 3. Chỉ dùng khi contract xác định hai trường hợp có cùng ý nghĩa. Nếu missing có nghĩa giữ giá trị còn null có nghĩa xóa, constructor này không đủ để biểu diễn semantics.

### 8.1. JsonProperty.defaultValue không tự áp dụng default runtime

Có thể bắt gặp:

```java
@JsonProperty(defaultValue = "3")
private int maxAttempts;
```

defaultValue trong JsonProperty chủ yếu là metadata cho module/framework/schema tool. Jackson Databind không tự động áp dụng chuỗi này làm runtime default cho property bị thiếu trong mọi trường hợp.

Nếu cần default thực sự, dùng field initializer, constructor, builder, custom deserializer hoặc logic migration rõ ràng. Đừng dựa vào defaultValue annotation mà không kiểm tra hành vi thực tế.

## 9. Optional không tự giữ đủ ba trạng thái

Với jackson-datatype-jdk8 đã đăng ký, Jackson có thể xử lý Optional<T>:

```java
public record Profile(
        String name,
        Optional<String> nickname
) {}
```

Optional.of("An") biểu diễn một giá trị; Optional.empty() biểu diễn không có giá trị.

Nhưng Optional.empty() không tự phân biệt JSON property bị thiếu với property có explicit null trong mọi luồng deserialize. Cả hai có thể được chuyển thành empty. Optional hữu ích để biểu diễn có/không có giá trị trong domain, nhưng không phải kiểu tri-state tổng quát cho PATCH.

Để serialization bỏ qua Optional absent, có thể dùng JsonInclude.Include.NON_ABSENT khi module hỗ trợ kiểu absent đó. Hãy kiểm tra JSON thực tế với đúng module/version.

## 10. PATCH: missing giữ nguyên, null có thể xóa

Một trong những nơi phân biệt missing và null quan trọng nhất là API cập nhật từng phần.

Giả sử hồ sơ hiện tại:

```json
{
  "displayName": "An",
  "nickname": "An Nguyen"
}
```

Client gửi:

```json
{
  "displayName": "An Tran"
}
```

Ý nghĩa thường mong muốn: displayName đổi thành An Tran; nickname không được gửi nên giữ An Nguyen.

Nếu client gửi:

```json
{
  "nickname": null
}
```

ý nghĩa có thể là xóa nickname.

DTO đơn giản:

```java
public record ProfilePatch(
        String displayName,
        String nickname
) {}
```

có thể làm missing và explicit null cùng thành Java null. Service không biết nên giữ nguyên hay xóa nickname.

### 10.1. Giữ presence bằng JsonNode

Một lựa chọn là đọc PATCH body thành ObjectNode:

```java
ObjectNode patch = (ObjectNode) mapper.readTree(requestBody);

if (patch.has("nickname")) {
    JsonNode nicknameNode = patch.get("nickname");

    if (nicknameNode.isNull()) {
        profile.clearNickname();
    } else {
        profile.setNickname(nicknameNode.asText());
    }
}

// Nếu patch không có nickname, giữ nguyên giá trị hiện tại.
```

has("nickname") trả true cả khi field tồn tại với JSON null. get("nickname") trả node null-value trong trường hợp explicit null; nếu property không tồn tại, get trả Java null.

Cách này giữ rõ ba trường hợp và dễ áp dụng khi PATCH contract có nhiều field optional.

### 10.2. Dùng wrapper tri-state

Một kiểu wrapper có thể biểu diễn ba trạng thái:
- Undefined: property không xuất hiện.
- Explicit null: property có mặt và là null.
- Value: property có giá trị.

Ví dụ kiểu khái niệm:

```java
sealed interface PatchField<T> {
    record Undefined<T>() implements PatchField<T> {}
    record NullValue<T>() implements PatchField<T> {}
    record Value<T>(T value) implements PatchField<T> {}
}
```

Chỉ khai báo wrapper type thôi chưa đủ. Cần custom deserializer/binder hoặc initializer để property bị thiếu vẫn là Undefined, còn property có mặt được gán NullValue hoặc Value.

Một số thư viện cung cấp JsonNullable<T> cho mục tiêu này. Khi sử dụng, hãy kiểm tra module Jackson đi kèm và contract của đúng version.

### 10.3. JSON Merge Patch

Nếu API tuân theo JSON Merge Patch (RFC 7396), quy tắc cơ bản là:
- Member không xuất hiện: không thay đổi member đích.
- Member xuất hiện với null: xóa member đích.
- Member xuất hiện với giá trị: thêm hoặc thay thế member.
- Object lồng nhau được merge đệ quy.
- Array được thay thế như một giá trị, không merge từng phần tử.

Ví dụ:

```json
{
  "nickname": null,
  "address": {
    "city": "Da Nang"
  }
}
```

Đây là semantics của Merge Patch. Không phải mọi endpoint nhận JSON object đều tự động tuân theo RFC 7396. Nếu áp dụng chuẩn này, hãy công bố media type application/merge-patch+json và xử lý đúng quy tắc object/array/null.

## 11. Cập nhật object hiện có bằng readerForUpdating và JsonMerge

Jackson có API cập nhật một object hiện có:

```java
ObjectReader updater = mapper.readerForUpdating(existingProfile);
updater.readValue(patchJson);
```

Với bean mutable, property không xuất hiện thường không bị gán nên giá trị hiện tại được giữ. Property có explicit null sẽ đi qua null policy của property.

Tuy nhiên, đây không tự động là implementation đầy đủ của JSON Merge Patch. Cách merge object lồng nhau và collection có thể khác kỳ vọng; cần xác định contract và test.

JsonMerge có thể yêu cầu Jackson merge nội dung property thay vì thay thế toàn bộ trong một số trường hợp:

```java
public class UserPreferences {
    @JsonMerge
    private Map<String, String> options = new HashMap<>();
}
```

Khi merge map, entry mới có thể được thêm/cập nhật theo semantics của Jackson. Với object lồng nhau và collection, hành vi có thể khác nhau; collection thường có quy tắc riêng theo kiểu và cấu hình. Đừng bật JsonMerge toàn cục mà không test từng loại property.

JsonMerge không có nghĩa null tự động trở thành “giữ nguyên”. Kết hợp JsonSetter(nulls = ...) khi cần quy định null rõ ràng.

## 12. Null, missing và default trong schema evolution

Khi API hoặc message schema có phiên bản mới, các thay đổi thường gặp:
- Thêm property mới.
- Đổi tên property.
- Đổi kiểu property.
- Thay đổi default.
- Đổi cách xử lý null.
- Bỏ property cũ.
- Thay đổi enum hoặc polymorphic subtype.

Một thay đổi nhỏ như bỏ field null để JSON gọn hơn có thể làm consumer cũ hiểu khác nếu họ dựa vào sự hiện diện của field. Thêm field mới cũng có thể phá reader cũ nếu reader từ chối unknown properties.

Đánh giá tương thích theo hai chiều:

| Writer | Reader | Câu hỏi |
|---|---|---|
| Writer cũ | Reader mới | Field mới bị thiếu thì reader mới có default an toàn không? |
| Writer mới | Reader cũ | Reader cũ bỏ qua field mới hay từ chối? |
| Writer mới với null | Reader cũ | Reader cũ hiểu explicit null thế nào? |
| Writer mới bỏ field null | Reader cũ | Missing có bị hiểu thành default khác không? |
| Dữ liệu lưu từ nhiều năm trước | Code hiện tại | Có cần migration hoặc alias để đọc format cũ không? |

Một quy tắc thường an toàn hơn là thêm property optional với semantics rõ, giữ nguyên ý nghĩa field hiện tại và không đổi cách hiểu null/missing trong một thay đổi contract nhỏ.

## 13. Đổi tên property mà vẫn đọc payload cũ

Nếu property JSON đổi tên, dùng JsonAlias để chấp nhận tên cũ khi deserialize:

```java
public class UserProfile {
    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Jackson đọc được cả:

```json
{"name":"An"}
```

và:

```json
{"displayName":"An"}
```

Khi serialize, tên chính được chọn theo JsonProperty, tức displayName. Alias chủ yếu hỗ trợ input cũ; nó không có nghĩa Jackson sẽ xuất cả hai tên.

Nếu nhiều alias cùng xuất hiện trong một payload, hãy xác định cách xử lý và kiểm thử. Không nên để sender gửi cả tên cũ và mới với hai giá trị khác nhau.

## 14. Unknown property và khả năng đọc payload tương lai

Reader mới có thể gặp field chưa từng biết từ writer mới hơn. Có hai chiến lược:

**Strict reader:** từ chối unknown property để phát hiện sai schema sớm.

```java
mapper.enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

**Forward-tolerant reader:** bỏ qua field chưa biết:

```java
mapper.disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Hoặc chỉ áp dụng cho DTO cụ thể:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public class LegacyConsumerMessage {
    private String id;
}
```

Không có chính sách nào đúng cho mọi hệ thống. Với command nghiệp vụ quan trọng, strict validation giúp phát hiện lỗi. Với event consumer cần tương thích additive fields, bỏ qua unknown field có thể phù hợp.

Nếu cần giữ field chưa biết để proxy/round-trip dữ liệu, dùng JsonAnySetter để thu thập extension properties vào map. Bỏ qua unknown field đồng nghĩa có thể mất thông tin khi serialize lại.

## 15. Thay đổi default là thay đổi contract

Giả sử version 1 có:

```java
public class RetryConfig {
    private int maxAttempts = 3;
}
```

Version 2 đổi default thành 5. Payload cũ không chứa maxAttempts:

```json
{}
```

Khi đọc bằng version 1, kết quả là 3; khi đọc bằng version 2, kết quả có thể là 5. Cùng một tài liệu lưu trữ nhưng có ý nghĩa khác tùy version code.

Nếu default ảnh hưởng nghiệp vụ, cân nhắc:
- Ghi rõ giá trị vào payload thay vì dựa vào default ngầm.
- Có schemaVersion hoặc configVersion.
- Dùng migration khi đọc dữ liệu cũ.
- Giữ default theo version cũ cho đến khi dữ liệu được chuyển đổi.
- Tách default của API khỏi default của domain nếu hai contract khác nhau.

Ví dụ payload có version:

```json
{
  "schemaVersion": 1,
  "retry": {}
}
```

Migration logic có thể áp dụng default version 1 trước khi chuyển sang model nội bộ hiện tại. Đừng đổi default toàn cục rồi kỳ vọng dữ liệu cũ tự giữ nguyên semantics.

## 16. Dùng schemaVersion và migration rõ ràng

Với message/file tồn tại lâu dài, version field giúp lựa chọn quy tắc đọc:

```json
{
  "schemaVersion": 2,
  "profile": {
    "displayName": "An"
  }
}
```

Có thể deserialize envelope trước:

```java
public record VersionedPayload(
        int schemaVersion,
        JsonNode profile
) {}
```

Sau đó chọn migration:

```java
VersionedPayload payload = mapper.readValue(json, VersionedPayload.class);

JsonNode currentTree = switch (payload.schemaVersion()) {
    case 1 -> migrateV1ToV2(payload.profile());
    case 2 -> payload.profile();
    default -> throw new IllegalArgumentException(
            "Unsupported schema version: " + payload.schemaVersion()
    );
};

CurrentProfile profile = mapper.treeToValue(
        currentTree,
        CurrentProfile.class
);
```

Migration có thể đổi tên field cũ, điền default theo version cũ, chuyển null theo semantics lịch sử, chuẩn hóa enum/format ngày giờ hoặc từ chối dữ liệu không thể diễn giải an toàn.

Tách migration thành bước rõ ràng giúp kiểm thử và audit dễ hơn.

## 17. Kiểm thử ba trạng thái bằng JsonNode

Để đảm bảo không gộp missing và null, test trực tiếp JSON tree:

```java
JsonNode missing = mapper.readTree("{}");
JsonNode explicitNull = mapper.readTree("{\"nickname\":null}");
JsonNode value = mapper.readTree("{\"nickname\":\"An\"}");

assertFalse(missing.has("nickname"));

assertTrue(explicitNull.has("nickname"));
assertTrue(explicitNull.get("nickname").isNull());

assertTrue(value.has("nickname"));
assertTrue(value.get("nickname").isTextual());
assertEquals("An", value.get("nickname").textValue());
```

has() phân biệt field thiếu với field có null. hasNonNull() kiểm tra field tồn tại và khác null. path() trả MissingNode khi field không tồn tại:

```java
assertTrue(missing.path("nickname").isMissingNode());
assertTrue(explicitNull.path("nickname").isNull());
```

Không dùng asText() làm phép kiểm tra presence vì nó có thể trả chuỗi rỗng/default cho missing hoặc null theo cách khiến test mất phân biệt.

## 18. Test JsonSetter cho null

Model có default và null policy:

```java
public class Preferences {
    private String theme = "light";

    @JsonSetter(nulls = Nulls.SKIP)
    public void setTheme(String theme) {
        this.theme = theme;
    }

    public String getTheme() {
        return theme;
    }
}
```

Test missing:

```java
Preferences missing = mapper.readValue("{}", Preferences.class);
assertEquals("light", missing.getTheme());
```

Test explicit null:

```java
Preferences explicitNull = mapper.readValue(
        "{\"theme\":null}",
        Preferences.class
);
assertEquals("light", explicitNull.getTheme());
```

Với Nulls.SET, explicit null được gán vào property reference. Với Nulls.FAIL, test xác nhận Jackson ném mapping exception. SKIP bỏ qua thao tác gán null; giá trị giữ lại đến từ field initializer, constructor hoặc object đang được cập nhật.

## 19. Test missing và null trên object đang cập nhật

Khi dùng readerForUpdating, có thể xác nhận semantics giữ giá trị hiện tại:

```java
public class Profile {
    private String nickname;

    public Profile() {
    }

    public Profile(String nickname) {
        this.nickname = nickname;
    }

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}
```

Test:

```java
Profile profile = new Profile("An Nguyen");

mapper.readerForUpdating(profile).readValue("{}");
assertEquals("An Nguyen", profile.getNickname());

mapper.readerForUpdating(profile)
        .readValue("{\"nickname\":null}");
assertNull(profile.getNickname());
```

Kết quả phụ thuộc null policy của property. Nếu setter được cấu hình Nulls.SKIP, explicit null sẽ không thay đổi giá trị hiện tại. Với object lồng nhau, map và collection, kiểm tra JsonMerge và null handling riêng.

## 20. Bảng chọn chính sách theo use case

| Use case | Missing | Explicit null | Giá trị |
|---|---|---|---|
| Tạo resource | Dùng default hoặc từ chối nếu bắt buộc | Chấp nhận/từ chối theo schema | Gán giá trị |
| PATCH profile | Giữ giá trị cũ | Xóa hoặc đặt null | Thay đổi giá trị |
| Cấu hình hệ thống | Dùng default của version | Thường từ chối hoặc có nghĩa xóa override | Ghi đè cấu hình |
| Event bất biến | Thường không được thiếu field bắt buộc | Chỉ chấp nhận nếu schema cho phép | Là dữ liệu event |
| Dữ liệu lưu lâu dài | Migration/default theo schema version | Giữ đúng semantics lịch sử | Đọc theo schema |
| Search filter | Không áp dụng filter | Có thể tìm giá trị null nếu contract định nghĩa | Lọc theo giá trị |

Đây là mẫu tư duy; contract cụ thể phải ghi rõ ý nghĩa cho từng property.

## 21. Quy trình thiết kế null/default cho một contract

Khi thêm hoặc sửa property, hãy quyết định rõ:

1. Property có bắt buộc trong request không?
2. Missing có nghĩa dùng default, giữ giá trị hiện tại hay báo lỗi?
3. Explicit null có được phép không?
4. Nếu null được phép, nó có nghĩa xóa, chưa biết hay giá trị rỗng?
5. String rỗng, array rỗng và object rỗng có ý nghĩa gì?
6. Default được đặt ở Java model, constructor, builder, deserializer hay migration?
7. Khi serialize, null/default/empty có được xuất hay bỏ qua?
8. Consumer cũ xử lý field mới hoặc field bị bỏ như thế nào?
9. Dữ liệu đã lưu từ version cũ có cần migration không?
10. Test có bao gồm missing, null, empty, default, giá trị bình thường và version cũ không?

Ghi các quyết định này trong schema/API documentation. Một property không nên dựa vào “hành vi mặc định của Jackson” nếu semantics đó ảnh hưởng dữ liệu nghiệp vụ.

## 22. Ghi nhớ

Missing, explicit null và giá trị cụ thể là ba trạng thái khác nhau. Trong bean mutable, property missing thường không kích hoạt setter nên field initializer/constructor value có thể được giữ; explicit null đi qua null policy. Với creator/record, property missing vẫn phải được xử lý khi gọi constructor và có thể cần FAIL_ON_MISSING_CREATOR_PROPERTIES. Primitive, wrapper và Optional có semantics khác nhau.

Ở chiều ghi, JsonInclude quyết định property null/absent/empty/default có xuất hiện hay không; NON_NULL, NON_ABSENT, NON_EMPTY và NON_DEFAULT không tương đương. Ở chiều đọc, JsonSetter(nulls = ..., contentNulls = ...) kiểm soát explicit null; JsonProperty(defaultValue = ...) không tự động cung cấp runtime default cho Databind.

Với PATCH, missing thường có nghĩa giữ nguyên, null có thể có nghĩa xóa và value có nghĩa thay thế. DTO thông thường có thể làm mất phân biệt missing/null; dùng JsonNode, tri-state wrapper hoặc một cơ chế presence-aware. Khi schema thay đổi, kiểm thử writer cũ/reader mới và writer mới/reader cũ, giữ default theo version và dùng alias/migration rõ ràng.
