# Đổi tên trường với chiến lược chấp nhận tên cũ

Khi một API thay đổi tên JSON property, producer và consumer thường không được nâng cấp cùng lúc. Server có thể muốn dùng tên mới làm tên chuẩn, nhưng vẫn phải đọc payload từ client cũ đang gửi tên trước đây. Jackson hỗ trợ tình huống này bằng cách kết hợp tên property chính với các tên thay thế.

Cách làm thông dụng là dùng **@JsonProperty** để xác định tên wire chuẩn và **@JsonAlias** để chấp nhận một hoặc nhiều tên cũ khi deserialize. Khi ghi JSON, Jackson dùng tên chính; khi đọc JSON, Jackson nhận cả tên chính và các alias đã khai báo.

Ví dụ, API chuyển từ displayName sang display_name:

~~~java
public record CustomerRequest(
    @JsonProperty("display_name")
    @JsonAlias({"displayName", "name"})
    String displayName
) {}
~~~

Payload mới:

~~~json
{
  "display_name": "Linh"
}
~~~

Payload cũ vẫn được chấp nhận:

~~~json
{
  "displayName": "Linh"
}
~~~

Một hệ thống tích hợp khác dùng tên rút gọn cũng có thể gửi:

~~~json
{
  "name": "Linh"
}
~~~

Khi serialize CustomerRequest, Jackson phát ra tên chuẩn display_name. Các alias chỉ mở rộng khả năng đọc đầu vào; chúng không khiến output phát đồng thời nhiều tên.

## 1. Vì sao cần chấp nhận tên cũ?

Đổi tên property thường xảy ra khi:

- API chuyển từ camelCase sang snake_case.
- Tên field cũ không còn đúng thuật ngữ nghiệp vụ.
- Một hệ thống tích hợp đã công bố tên JSON cũ và không thể cập nhật ngay.
- DTO được chuẩn hóa sau khi hợp nhất nhiều nguồn dữ liệu.
- Một phiên bản API mới cần giữ tương thích với client của phiên bản trước.
- Tên field được sửa để tránh mơ hồ hoặc trùng với từ khóa trong một hệ thống khác.

Nếu chỉ đổi tên property Java hoặc đổi tên JSON mà không có chính sách tương thích, client cũ có thể gửi field mà server không còn nhận ra. Tùy cấu hình, field đó có thể bị bỏ qua hoặc gây UnrecognizedPropertyException.

Chấp nhận alias cho phép server đọc cả tên mới lẫn tên cũ trong giai đoạn chuyển tiếp. Đồng thời, server có thể chỉ phát tên mới để dần đưa producer và consumer về một quy ước thống nhất.

## 2. Phân biệt tên Java, tên JSON chuẩn và tên alias

Một property có thể có ba nhóm tên khác nhau:

| Vai trò | Ví dụ | Mục đích |
|---|---|---|
| Tên Java | displayName | Tên component/field/method trong code |
| Tên JSON chuẩn | display_name | Tên server phát ra khi serialize |
| Tên alias | displayName, name | Tên server chấp nhận khi deserialize |

Tên Java có thể giữ ổn định trong code dù wire name thay đổi. Đây là một lợi ích quan trọng: refactor hợp đồng JSON không nhất thiết phải đổi tên biến trong toàn bộ ứng dụng.

Ví dụ:

~~~java
public record CustomerRequest(
    @JsonProperty("display_name")
    @JsonAlias({"displayName", "full_name", "name"})
    String displayName
) {}
~~~

Trong code Java, accessor vẫn là displayName(). Khi ghi JSON, tên chuẩn là display_name. Khi đọc, Jackson cũng nhận displayName, full_name và name.

Không nên nhầm alias với tên Java. @JsonAlias khai báo tên đầu vào thay thế; nó không đổi tên accessor, không tạo thêm property Java và không làm output có nhiều field.

## 3. @JsonAlias hoạt động ở chiều deserialize

@JsonAlias được thiết kế để khai báo các tên thay thế khi đọc JSON. Nó không thay thế tên property chính trong serialization.

Ví dụ:

~~~java
public class UserRequest {
    @JsonProperty("user_id")
    @JsonAlias({"userId", "id"})
    private Long userId;

    public UserRequest() {
    }

    public Long getUserId() {
        return userId;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }
}
~~~

Đọc payload cũ:

~~~java
UserRequest first =
    mapper.readValue("{\"userId\": 10}", UserRequest.class);

UserRequest second =
    mapper.readValue("{\"id\": 10}", UserRequest.class);
~~~

Cả hai trường hợp đều gán giá trị vào cùng property userId.

Khi serialize:

~~~java
String json = mapper.writeValueAsString(first);
~~~

Tên field được phát ra là user_id, theo @JsonProperty. Jackson không phát userId và id như các field bổ sung.

Đây là nguyên tắc cốt lõi: **một tên chuẩn để ghi, nhiều tên được phép đọc**.

## 4. Kết hợp @JsonProperty và @JsonAlias

@JsonProperty xác định tên property được Jackson sử dụng làm tên chính. @JsonAlias bổ sung các tên đầu vào thay thế.

~~~java
public record OrderRequest(
    @JsonProperty("order_id")
    @JsonAlias({"orderId", "id"})
    String orderId,

    @JsonProperty("created_at")
    @JsonAlias({"createdAt", "creationDate"})
    Instant createdAt
) {}
~~~

Payload mới:

~~~json
{
  "order_id": "ORD-100",
  "created_at": "2026-11-12T10:30:00Z"
}
~~~

Payload cũ:

~~~json
{
  "orderId": "ORD-100",
  "createdAt": "2026-11-12T10:30:00Z"
}
~~~

Payload từ một producer khác:

~~~json
{
  "id": "ORD-100",
  "creationDate": "2026-11-12T10:30:00Z"
}
~~~

Cả ba có thể ánh xạ vào cùng một record nếu các kiểu giá trị và format tương ứng hợp lệ.

@JsonProperty và @JsonAlias không giải quyết mọi khác biệt của payload. Nếu tên cũ có cấu trúc khác, ví dụ createdAt cũ là Unix timestamp còn created_at mới là ISO-8601 string, cần thêm quy tắc định dạng hoặc deserializer. Alias chỉ thay tên field, không chuyển đổi kiểu dữ liệu hay ý nghĩa giá trị.

## 5. Dùng alias với class mutable, getter và setter

Alias có thể được đặt trên property mà Jackson nhận diện qua field, setter hoặc creator parameter. Với class mutable, cách dễ hiểu là đặt annotation trên field hoặc setter theo chiến lược property của dự án.

Ví dụ trên field:

~~~java
public class AccountRequest {
    @JsonProperty("account_number")
    @JsonAlias({"accountNumber", "acctNo"})
    private String accountNumber;

    public AccountRequest() {
    }

    public String getAccountNumber() {
        return accountNumber;
    }

    public void setAccountNumber(String accountNumber) {
        this.accountNumber = accountNumber;
    }
}
~~~

Ví dụ trên setter:

~~~java
public class AccountRequest {
    private String accountNumber;

    @JsonProperty("account_number")
    @JsonAlias({"accountNumber", "acctNo"})
    public void setAccountNumber(String accountNumber) {
        this.accountNumber = accountNumber;
    }

    public String getAccountNumber() {
        return accountNumber;
    }
}
~~~

Jackson hợp nhất metadata của field, getter, setter và creator thành logical property. Nếu cùng một property có annotation ở nhiều nơi, hãy giữ cấu hình nhất quán để tránh khó hiểu về tên wire cuối cùng.

Không nên khai báo cùng alias trên nhiều property khác nhau. Alias cần ánh xạ đến một property duy nhất trong một object.

## 6. Dùng alias với Java record và constructor creator

Với Jackson hỗ trợ record (thường từ dòng 2.12 trở lên), có thể khai báo alias trên record component:

~~~java
public record ProfileRequest(
    @JsonProperty("display_name")
    @JsonAlias({"displayName", "name"})
    String displayName,

    @JsonProperty("birth_date")
    @JsonAlias({"birthDate", "dob"})
    LocalDate birthDate
) {}
~~~

Jackson dùng metadata của component để binding vào canonical constructor.

Với immutable class dùng @JsonCreator, có thể đặt tên wire và alias trên creator parameter:

~~~java
public class ProductRequest {
    private final String productCode;

    @JsonCreator
    public ProductRequest(
        @JsonProperty("product_code")
        @JsonAlias({"productCode", "sku"})
        String productCode
    ) {
        this.productCode = productCode;
    }

    public String getProductCode() {
        return productCode;
    }
}
~~~

Nếu dùng constructor parameter mà không có @JsonCreator hoặc metadata parameter name phù hợp, Jackson có thể không biết cách liên kết input với tham số. Alias không thay thế yêu cầu phải có creator/property definition hợp lệ.

Hãy kiểm tra cả tên chuẩn và alias trên đúng phiên bản Jackson đang chạy, nhất là với record, constructor nhiều tham số và custom annotation introspector.

## 7. Chấp nhận tên cũ trong khi vẫn bật strict unknown-property policy

Một ứng dụng có thể muốn từ chối mọi field không biết nhưng vẫn chấp nhận một số tên cũ đã công bố.

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

DTO:

~~~java
public record UserRequest(
    @JsonProperty("user_id")
    @JsonAlias({"userId", "id"})
    long userId
) {}
~~~

Các payload sau được nhận diện là cùng một property:

~~~json
{"user_id": 10}
~~~

~~~json
{"userId": 10}
~~~

~~~json
{"id": 10}
~~~

Nhưng field không được khai báo vẫn bị từ chối:

~~~json
{"user_id": 10, "nickname": "linh"}
~~~

Alias là một tên đã biết của property, vì vậy nó không phải unknown property. Strict mode vẫn có thể được giữ để phát hiện typo hoặc field ngoài hợp đồng.

Đây là cách hữu ích khi API muốn tương thích ngược có kiểm soát mà vẫn cần schema rõ ràng.

## 8. Kết hợp alias với naming strategy

Ứng dụng có thể dùng naming strategy toàn cục:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
~~~

Khi đó, property Java displayName có thể được ánh xạ thành display_name theo quy tắc snake_case.

Nếu cần khai báo rõ tên chuẩn và các cách viết cũ, có thể viết:

~~~java
public record UserRequest(
    @JsonProperty("display_name")
    @JsonAlias({"displayName", "name"})
    String displayName
) {}
~~~

@JsonProperty giúp tên chuẩn của property không phụ thuộc vào việc tên Java được biến đổi theo naming strategy. Các alias nên được liệt kê bằng đúng spelling mà producer cũ thực sự gửi. Không nên giả định mọi alias sẽ tự động biến đổi giống tên property thông thường; hãy test với ObjectMapper production và naming strategy đang dùng.

Nếu không khai báo @JsonProperty, naming strategy có thể quyết định tên chuẩn khi serialize. Khi contract yêu cầu tên wire cố định, khai báo tên tường minh giúp ý định rõ hơn.

Cũng cần lưu ý @JsonNaming có thể áp dụng cho một class cụ thể, trong khi naming strategy của ObjectMapper có phạm vi rộng hơn. Hãy kiểm tra cấu hình thực tế và tránh để annotation ở class xung đột với quy ước toàn ứng dụng.

## 9. Alias không phải cơ chế chấp nhận khác biệt chữ hoa/thường

@JsonAlias khai báo các tên cụ thể. Ví dụ:

~~~java
@JsonAlias({"userId", "user_id_old"})
~~~

không có nghĩa mọi cách viết như USERID, UserID hoặc USER_ID đều tự động được chấp nhận.

Nếu muốn property matching không phân biệt chữ hoa/thường, Jackson có MapperFeature.ACCEPT_CASE_INSENSITIVE_PROPERTIES:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(MapperFeature.ACCEPT_CASE_INSENSITIVE_PROPERTIES)
    .build();
~~~

Đây là một chính sách khác với alias:

| Cơ chế | Phạm vi |
|---|---|
| @JsonAlias | Danh sách tên thay thế được chỉ định rõ |
| ACCEPT_CASE_INSENSITIVE_PROPERTIES | So khớp property không phân biệt hoa/thường theo cấu hình |
| @JsonProperty | Tên property chính, đặc biệt quan trọng khi serialize |
| PropertyNamingStrategy | Quy tắc chuyển đổi tên property theo convention |

Không nên bật case-insensitive chỉ để chấp nhận một tên cũ cụ thể. Nó có thể làm nhiều cách viết khác nhau cùng được nhận diện và khiến hợp đồng đầu vào rộng hơn dự kiến.

Nếu API chỉ cần chấp nhận displayName như alias của display_name, khai báo alias tường minh thường an toàn và dễ tài liệu hóa hơn.

## 10. Xử lý khi payload gửi đồng thời tên mới và tên cũ

Một payload có thể vô tình chứa cả tên chuẩn lẫn alias:

~~~json
{
  "display_name": "Linh Nguyen",
  "displayName": "Linh"
}
~~~

Cả hai tên ánh xạ đến cùng một logical property. Trong quá trình binding thông thường, giá trị được gán sau cùng theo thứ tự field xuất hiện có thể ghi đè giá trị trước đó.

Không nên dựa vào thứ tự JSON để quyết định giá trị nào đúng. Hai giá trị khác nhau có thể khiến dữ liệu trở nên mơ hồ.

Một số cách xử lý:

- Quy định producer chỉ gửi đúng một trong các tên được chấp nhận.
- Nếu payload chứa nhiều tên cùng ánh xạ một property, từ chối request.
- Nếu các giá trị giống nhau, có thể chấp nhận theo policy rõ ràng, nhưng vẫn cần kiểm tra trùng tên.
- Ghi metric về việc client còn dùng alias cũ để lên kế hoạch loại bỏ.

@JsonAlias tự ánh xạ nhiều tên về một property; nó không tự xác nhận rằng payload chỉ dùng một trong các tên đó.

Nếu cần từ chối trường hợp cùng property xuất hiện dưới nhiều spelling, hãy dùng custom deserializer hoặc bước kiểm tra tree trước khi binding. Parser duplicate detection mặc định chỉ phát hiện tên JSON lặp nguyên văn; nó không nhất thiết xem display_name và displayName là duplicate vì chúng là hai chuỗi khác nhau.

Ví dụ kiểm tra bằng tree:

~~~java
JsonNode root = mapper.readTree(json);

int occurrences = 0;
for (String name : List.of("display_name", "displayName", "name")) {
    if (root.has(name)) {
        occurrences++;
    }
}

if (occurrences > 1) {
    throw new IllegalArgumentException(
        "Provide only one spelling for display name"
    );
}

UserRequest request = mapper.treeToValue(root, UserRequest.class);
~~~

Ví dụ này phù hợp với root object đơn giản. Trong code thực tế, cần xác nhận root là object trước khi gọi has(), và thực hiện kiểm tra tương tự cho từng object lồng nhau nếu alias nằm ở nhiều cấp.

## 11. Phân biệt duplicate key với nhiều alias của cùng property

Có hai dạng trùng khác nhau:

**Duplicate key nguyên văn:**

~~~json
{
  "display_name": "Linh",
  "display_name": "Minh"
}
~~~

Đây là cùng một tên JSON xuất hiện hai lần. Có thể bật strict duplicate detection ở JsonFactory:

~~~java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

**Hai alias khác nhau cùng trỏ đến một property:**

~~~json
{
  "display_name": "Linh",
  "displayName": "Minh"
}
~~~

Tên JSON không trùng nguyên văn nên strict duplicate detection không nhất thiết phát hiện. Muốn từ chối trường hợp này, cần kiểm tra các tên cùng thuộc một nhóm alias trước khi binding hoặc viết deserializer kiểm soát chúng.

Hai cơ chế giải quyết hai vấn đề khác nhau. Khi API yêu cầu tính xác định cao, hãy test cả hai.

## 12. Alias chỉ đổi tên property, không đổi cấu trúc hoặc kiểu dữ liệu

@JsonAlias chỉ giúp nhận nhiều tên cho cùng một property. Nó không tự chuyển đổi:

- String thành object.
- Một object lồng thành các field phẳng.
- Unix timestamp thành ISO date.
- Chuỗi "1,25" thành decimal theo locale.
- Giá trị enum cũ sang enum mới.
- Array thành scalar.
- Map key hoặc tên field động theo một quy tắc tùy ý.

Ví dụ, hai payload:

~~~json
{"createdAt": "2026-11-12T10:30:00Z"}
~~~

~~~json
{"created_at": 1794489000}
~~~

khác cả tên lẫn kiểu/định dạng giá trị. Alias có thể xử lý phần tên, nhưng không tự chuyển Unix timestamp thành Instant.

Nếu dữ liệu cũ có format khác, có thể dùng custom deserializer, JsonFormat nếu phù hợp, hoặc một bước normalize riêng. Không nên cố dùng alias để giải quyết khác biệt về ý nghĩa dữ liệu.

Tương tự, nếu tên cũ nằm trong một object lồng khác, cần xử lý cấu trúc đó bằng DTO riêng, tree transformation hoặc custom deserializer.

## 13. Alias cho enum value là một vấn đề khác

@JsonAlias áp dụng cho tên property, không phải các giá trị chuỗi của enum.

Ví dụ:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Nếu producer cũ gửi "COMPLETE" và API mới dùng PAID, khai báo @JsonAlias trên property status không làm cho giá trị enum "COMPLETE" tự động trở thành PAID.

Có thể xử lý bằng @JsonCreator trên enum:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED;

    @JsonCreator
    public static OrderStatus fromWire(String value) {
        return switch (value) {
            case "NEW" -> NEW;
            case "PAID", "COMPLETE" -> PAID;
            case "CANCELLED" -> CANCELLED;
            default -> throw new IllegalArgumentException(
                "Unsupported order status: " + value
            );
        };
    }

    @JsonValue
    public String toWire() {
        return name();
    }
}
~~~

Trong ví dụ, "COMPLETE" được chấp nhận khi đọc và serialize luôn phát tên chuẩn "PAID". Đây là cách tương tự chiến lược đọc nhiều giá trị cũ, ghi một giá trị chuẩn, nhưng nó áp dụng cho enum value chứ không phải property name.

Với logic phức tạp hoặc cần xử lý nhiều phiên bản, custom JsonDeserializer cho enum có thể rõ ràng hơn.

## 14. Dùng mix-in khi không thể sửa class nguồn

Nếu DTO hoặc class thuộc thư viện bên ngoài, không thể thêm @JsonProperty và @JsonAlias trực tiếp. Có thể dùng mix-in để bổ sung annotation.

Class thư viện:

~~~java
public class VendorUser {
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Mix-in:

~~~java
abstract class VendorUserMixIn {
    @JsonProperty("display_name")
    @JsonAlias({"displayName", "name"})
    abstract String getDisplayName();
}
~~~

Đăng ký:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addMixIn(VendorUser.class, VendorUserMixIn.class)
    .build();
~~~

Mix-in cung cấp metadata annotation cho Jackson mà không thay đổi class gốc. Hãy xác nhận annotation được gắn vào accessor mà Jackson nhận diện trong class thực tế. Nếu class có getter/setter hoặc creator đặc biệt, có thể cần khai báo mix-in tương ứng.

Nếu cần thay đổi logic giá trị hoặc cấu trúc, mix-in annotation có thể không đủ; lúc đó hãy xem xét module với custom deserializer.

## 15. Alias trong các object lồng nhau

Alias được khai báo trên property của kiểu tương ứng. Nó không tự lan truyền sang mọi object có cùng tên field.

Ví dụ:

~~~java
public record AddressRequest(
    @JsonProperty("postal_code")
    @JsonAlias({"postalCode", "zip"})
    String postalCode
) {}

public record CustomerRequest(
    String name,
    AddressRequest address
) {}
~~~

Input:

~~~json
{
  "name": "Linh",
  "address": {
    "zip": "700000"
  }
}
~~~

Alias zip được nhận diện bên trong AddressRequest. Nếu một object khác cũng có property postalCode nhưng không khai báo alias, Jackson không tự áp dụng quy tắc của AddressRequest cho object đó.

Điều này giúp mỗi DTO kiểm soát contract riêng. Khi có nhiều kiểu lồng nhau, hãy khai báo alias tại đúng property và test payload lồng thực tế.

## 16. Alias và @JsonAnySetter

@JsonAnySetter nhận các property không được ánh xạ thành property đã biết. Nếu một tên cũ không được khai báo bằng @JsonAlias, nó có thể rơi vào nhánh any-setter thay vì gán vào property chuẩn.

Ví dụ:

~~~java
public class ExtensibleRequest {
    @JsonProperty("display_name")
    @JsonAlias("displayName")
    private String displayName;

    private final Map<String, JsonNode> extra = new LinkedHashMap<>();

    @JsonAnySetter
    public void addExtra(String name, JsonNode value) {
        extra.put(name, value);
    }
}
~~~

displayName là alias đã biết và được gán vào property displayName. Các tên khác chưa được nhận diện có thể được chuyển vào extra.

Nếu không khai báo alias, displayName có thể bị xử lý như một field động. Khi đó DTO vừa có displayName null vừa có extra chứa key displayName, khiến dữ liệu bị chia thành hai nơi.

Với DTO có @JsonAnySetter, hãy khai báo đầy đủ các tên cũ quan trọng trước khi xử lý field động. Nếu chính sách yêu cầu từ chối field lạ, đừng dùng any-setter để thu nhận mọi tên mà không có validation.

## 17. Theo dõi và loại bỏ alias theo vòng đời API

Alias thường là giải pháp tương thích chuyển tiếp. Nếu giữ alias mãi mãi, hợp đồng có thể tích lũy nhiều tên cũ và khó quản lý.

Một quy trình migration có thể gồm:

~~~text
Giai đoạn 1
  - Server đọc tên mới và tên cũ.
  - Server chỉ ghi tên mới.
  - Theo dõi producer còn gửi tên cũ.

Giai đoạn 2
  - Thông báo consumer chuyển sang tên mới.
  - Cung cấp thời hạn ngừng hỗ trợ alias.
  - Ghi metric/cảnh báo theo client hoặc integration.

Giai đoạn 3
  - Kiểm tra traffic không còn dùng alias.
  - Gỡ alias trong phiên bản API phù hợp.
  - Cập nhật contract và test fixture.
~~~

Không nên log toàn bộ payload chỉ để biết alias nào được dùng. Có thể ghi metric theo property name đã nhận diện, endpoint và client id không nhạy cảm.

Nếu có nhiều producer, có thể cần thời gian hỗ trợ khác nhau cho từng phiên bản API. Hãy cân nhắc versioning ở endpoint hoặc schema thay vì thêm hàng chục alias không có kế hoạch loại bỏ.

Tên alias là một phần của compatibility contract. Khi xóa alias, đó là một thay đổi có thể làm client cũ thất bại; cần release note hoặc version boundary phù hợp.

## 18. Kiểm thử tên chuẩn và tên cũ

Test cần xác nhận ba điều:

1. Tên chuẩn được đọc đúng.
2. Tên alias cũ được đọc vào cùng property.
3. Khi serialize, chỉ tên chuẩn được phát ra.

Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class PropertyAliasTest {

    record UserRequest(
        @JsonProperty("display_name")
        @JsonAlias({"displayName", "name"})
        String displayName
    ) {}

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void readsCanonicalName() throws Exception {
        UserRequest request = mapper.readValue(
            "{\"display_name\":\"Linh\"}",
            UserRequest.class
        );

        assertEquals("Linh", request.displayName());
    }

    @Test
    void readsLegacyAlias() throws Exception {
        UserRequest request = mapper.readValue(
            "{\"displayName\":\"Linh\"}",
            UserRequest.class
        );

        assertEquals("Linh", request.displayName());
    }

    @Test
    void writesOnlyCanonicalName() throws Exception {
        UserRequest request = new UserRequest("Linh");

        JsonNode output = mapper.readTree(
            mapper.writeValueAsString(request)
        );

        assertTrue(output.has("display_name"));
        assertFalse(output.has("displayName"));
        assertFalse(output.has("name"));
        assertEquals("Linh", output.path("display_name").asText());
    }
}
~~~

Nên bổ sung test với strict unknown-property mode:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
~~~

Xác nhận alias vẫn được chấp nhận, nhưng một tên typo như display_nam bị từ chối.

Nếu naming strategy hoặc mix-in được sử dụng trong production, hãy dựng mapper test từ đúng cấu hình đó. Test với new ObjectMapper() đơn giản có thể bỏ sót khác biệt của môi trường thực tế.

## 19. Kiểm tra trường hợp nhiều tên cùng xuất hiện

Nếu hợp đồng yêu cầu chỉ một spelling được gửi, hãy test payload chứa cả tên chuẩn và alias:

~~~json
{
  "display_name": "Linh Nguyen",
  "displayName": "Linh"
}
~~~

Với binding thông thường, property có thể nhận giá trị từ field xuất hiện sau. Đây là hành vi không nên dùng làm quy tắc ưu tiên.

Có thể tạo bước kiểm tra trước binding:

~~~java
JsonNode root = mapper.readTree(json);

if (!root.isObject()) {
    throw new IllegalArgumentException("Expected an object");
}

List<String> acceptedNames =
    List.of("display_name", "displayName", "name");

List<String> presentNames = acceptedNames.stream()
    .filter(root::has)
    .toList();

if (presentNames.size() > 1) {
    throw new IllegalArgumentException(
        "Only one display-name property may be supplied"
    );
}

UserRequest request =
    mapper.treeToValue(root, UserRequest.class);
~~~

Cách này minh họa cho một property ở root. Nếu alias xuất hiện trong nested object, hãy kiểm tra đúng subtree tương ứng. Nếu có nhiều property alias, nên đóng gói quy tắc vào helper hoặc custom deserializer để tránh lặp logic.

## 20. Khi nào cần custom deserializer thay cho @JsonAlias?

@JsonAlias phù hợp khi sự khác biệt chỉ nằm ở tên property và tất cả các tên đều có cùng ý nghĩa, cùng kiểu dữ liệu.

Hãy cân nhắc custom deserializer khi:

- Tên cũ và tên mới có kiểu giá trị khác nhau.
- Một tên cũ cần chuyển đổi hoặc chuẩn hóa đặc biệt.
- Có quy tắc ưu tiên phức tạp giữa nhiều spelling.
- Phải từ chối payload chứa đồng thời tên cũ và tên mới.
- Alias phụ thuộc phiên bản schema, tenant hoặc context.
- Cần ghi nhận chính xác tên nào đã được dùng để migration.
- Cấu trúc cũ khác cấu trúc mới chứ không chỉ khác tên.

Ví dụ, payload cũ gửi:

~~~json
{
  "amount": "1,250.50"
}
~~~

còn payload mới gửi:

~~~json
{
  "total_amount": 1250.50
}
~~~

Đây không chỉ là đổi tên: kiểu cũ là string, kiểu mới là number. @JsonAlias có thể nhận tên amount nhưng không tự parse định dạng string theo quy tắc locale. Custom deserializer hoặc bước normalize phải xử lý sự khác biệt đó.

Nếu logic chỉ là tên cũ -> cùng property, @JsonAlias gọn hơn và dễ tài liệu hóa hơn một custom deserializer.

## 21. Những lỗi thường gặp khi dùng alias

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Serialize vẫn phát tên cũ | Chỉ khai báo alias hoặc tên chính chưa được xác định rõ | Dùng @JsonProperty cho tên wire chuẩn |
| Alias không được nhận | Đặt annotation sai logical property hoặc mapper không dùng kiểu/metadata đó | Kiểm tra field/getter/setter/creator và mapper thực tế |
| Alias bị coi là unknown | Alias không khớp spelling input hoặc custom deserializer tự xử lý field | Test đúng tên producer gửi |
| Hai property cùng khai báo một alias | Tên đầu vào mơ hồ | Đảm bảo alias thuộc một property duy nhất |
| Cả tên cũ và tên mới cùng xuất hiện | Cùng ánh xạ một logical property | Từ chối hoặc xác định policy rõ ràng |
| Tên alias thay đổi theo naming strategy ngoài dự kiến | Giả định alias được biến đổi tự động | Khai báo spelling chính xác và test mapper production |
| Enum value cũ không được nhận | Nhầm alias property với alias value | Dùng @JsonCreator hoặc custom enum deserializer |
| Cấu trúc JSON cũ khác cấu trúc mới | Alias chỉ đổi tên field | Dùng DTO tương thích, tree normalization hoặc custom deserializer |
| Field lạ bị any-setter thu nhận | Tên cũ chưa được khai báo alias | Khai báo alias trước khi xử lý field động |

## 22. Quy trình triển khai đổi tên tương thích ngược

Trước khi đổi tên một field, hãy xác định:

1. Tên JSON hiện tại mà producer đang gửi.
2. Tên JSON chuẩn mới sẽ được server phát ra.
3. Những spelling cũ nào cần tiếp tục nhận.
4. Giá trị cũ và mới có cùng kiểu, format và ý nghĩa không.
5. Có naming strategy hoặc mix-in ảnh hưởng tên property không.
6. Có @JsonAnySetter hoặc unknown-property policy không.
7. Payload có thể chứa đồng thời nhiều alias không.
8. Khi nào sẽ đo mức sử dụng alias và gỡ bỏ chúng.
9. Test nào chứng minh tên chuẩn, tên cũ và output canonical.

Một thay đổi đơn giản có thể được triển khai như sau:

~~~java
public record ProfileResponse(
    @JsonProperty("display_name")
    @JsonAlias({"displayName", "fullName"})
    String displayName
) {}
~~~

Server nhận cả ba tên nhưng chỉ phát display_name. Khi client đã chuyển hết sang tên mới, team có thể loại bỏ alias trong một phiên bản contract phù hợp.

## Kết luận

Đổi tên JSON property mà vẫn chấp nhận client cũ có thể thực hiện bằng cách kết hợp @JsonProperty và @JsonAlias. @JsonProperty xác định tên chuẩn để ghi; @JsonAlias liệt kê các tên thay thế được chấp nhận khi đọc. Cách này giữ tên Java ổn định, hỗ trợ nhiều phiên bản producer và vẫn phát ra một wire name thống nhất.

Hãy dùng alias khi khác biệt chỉ là spelling. Nếu kiểu dữ liệu, format, cấu trúc hoặc quy tắc ưu tiên cũng thay đổi, cần thêm normalization hoặc custom deserializer. Tránh để nhiều alias trùng nhau giữa các property, quyết định rõ cách xử lý khi payload gửi đồng thời tên cũ và tên mới, kiểm thử với strict mode và theo dõi việc sử dụng alias để có kế hoạch loại bỏ chúng.

