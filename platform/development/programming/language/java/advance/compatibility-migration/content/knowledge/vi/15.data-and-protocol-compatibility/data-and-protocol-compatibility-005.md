# Tên trường, kiểu dữ liệu, giá trị mặc định và thuộc tính chưa biết

Khi nâng JDK, framework serialization, thư viện giao tiếp hoặc định dạng lưu trữ, một thay đổi tưởng nhỏ có thể làm hỏng dữ liệu đã được hệ thống khác tiêu thụ. Đổi tên một field Java có thể vô tình đổi tên property JSON. Chuyển một số từ integer sang string có thể phá consumer. Thêm trường bắt buộc không có default khiến payload cũ không còn đọc được. Ngược lại, bỏ qua mọi thuộc tính chưa biết có thể giúp tương thích phiên bản mới nhưng cũng che giấu lỗi hoặc tạo lỗ hổng dữ liệu.

Bài học thuộc **Java Advance Compatibility Migration**, chương **Dữ liệu và giao thức**. Trọng tâm là bốn chiều tiến hóa schema: **tên trường**, **kiểu dữ liệu**, **giá trị mặc định** và **thuộc tính chưa biết**. Nội dung đặt trong bối cảnh Java DTO, JSON/Jackson, REST, event, Protobuf, Avro và database. Nguyên tắc xuyên suốt: **cấu trúc lớp Java không đồng nhất với hợp đồng dữ liệu trên đường truyền hoặc trong kho lưu trữ**.

## 1. Vấn đề thực tế khi hai phiên bản cùng tồn tại

Giả sử ứng dụng cũ ghi:

~~~json
{
  "orderId": "ORD-001",
  "total": 125000,
  "status": "PAID"
}
~~~

Sau một đợt hiện đại hóa Java, producer mới gửi:

~~~json
{
  "orderId": "ORD-001",
  "totalAmount": "125000.00",
  "currency": "VND",
  "status": "SETTLED",
  "traceId": "abc-123"
}
~~~

Dù hai payload mô tả một đơn hàng, chúng không còn cùng hợp đồng. Consumer cũ có thể:

- Không tìm thấy total vì tên đổi thành totalAmount.
- Từ chối totalAmount vì kiểu chuyển từ number sang string.
- Không biết enum SETTLED.
- Không có currency ở dữ liệu lịch sử.
- Báo lỗi khi gặp thuộc tính traceId chưa được khai báo.

Một hệ thống thực tế còn có nhiều nhóm consumer: ứng dụng Java cũ, ứng dụng mobile chưa cập nhật, plugin đối tác, batch job chạy lại dữ liệu lịch sử và hệ thống ngoài Java. Do đó, tương thích schema phải được nhìn theo **producer và consumer**, không chỉ một build hiện tại.

## 2. Hai hướng tương thích: reader mới và reader cũ

Để tránh sự khác nhau về thuật ngữ giữa các schema registry, ta mô tả rõ hai chiều:

- **Reader mới đọc dữ liệu do writer cũ ghi:** nhu cầu thường gọi là backward compatibility.
- **Reader cũ đọc dữ liệu do writer mới ghi:** nhu cầu thường gọi là forward compatibility.
- **Cả hai chiều đọc được:** full compatibility trong phạm vi phiên bản được cam kết.

~~~text
Writer V1  ---- payload V1 ----> Reader V2
   |                                    |
   +---------- đọc dữ liệu cũ ----------+

Writer V2  ---- payload V2 ----> Reader V1
   |                                    |
   +---------- đọc dữ liệu mới ----------+
~~~

Một hệ thống có rolling deployment hoặc event retention dài thường cần reader mới đọc dữ liệu cũ. Nếu mobile client hoặc đối tác không thể nâng đồng bộ, nó còn cần reader cũ đọc payload do writer mới tạo.

| Thay đổi | Reader mới đọc writer cũ | Reader cũ đọc writer mới |
|---|---|---|
| Thêm trường tùy chọn | Thường dễ nếu default/nullable hợp lý | Tùy cấu hình unknown fields |
| Thêm trường bắt buộc | Có nguy cơ lỗi vì payload cũ thiếu | Tùy reader cũ xử lý trường lạ |
| Xóa trường | Reader mới phải bỏ nhu cầu hoặc có fallback | Reader cũ có thể thiếu thông tin |
| Đổi tên trường | Cần alias/mapping hoặc migration | Cần dual-write/alias tại consumer |
| Đổi kiểu số sang chuỗi | Có nguy cơ không parse được | Có nguy cơ không parse được |
| Thêm enum value | Reader mới thường biết | Reader cũ có thể từ chối |
| Thêm unknown property | Reader mới hiểu hoặc bỏ qua | Reader cũ có thể strict |

Bảng chỉ mô tả rủi ro phổ biến. JSON, Protobuf, Avro, database và thư viện serialization có quy tắc thực tế khác nhau.

## 3. Tên field Java và wire name không phải một

Tên trường trong Java có thể được xác định bởi field, getter/setter, annotation, record component, constructor parameter hoặc naming strategy. Tên trên wire lại được quyết định bởi serializer và schema.

Ví dụ:

~~~java
public final class Order {
    private String customerId;

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String value) {
        customerId = value;
    }
}
~~~

Với một cấu hình Jackson thông thường, dữ liệu có thể là:

~~~json
{"customerId":"CUS-001"}
~~~

Nếu refactor field/getter thành clientId, serializer dựa vào convention có thể ghi:

~~~json
{"clientId":"CUS-001"}
~~~

Đây là breaking change đối với consumer đang tìm customerId.

### 3.1. Giữ ổn định tên wire bằng @JsonProperty

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public final class OrderDto {
    @JsonProperty("customerId")
    private String clientIdentifier;

    public String getClientIdentifier() {
        return clientIdentifier;
    }

    public void setClientIdentifier(String value) {
        clientIdentifier = value;
    }
}
~~~

Tên trong source có thể thay đổi nhưng wire contract vẫn giữ customerId. Cần xác minh cấu hình Jackson nếu getter, setter, constructor và field có annotation không nhất quán.

### 3.2. Chấp nhận cả tên cũ lẫn tên mới với @JsonAlias

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public final class OrderDto {
    @JsonProperty("customerId")
    @JsonAlias("clientId")
    private String customerIdentifier;

    public String getCustomerIdentifier() {
        return customerIdentifier;
    }

    public void setCustomerIdentifier(String value) {
        customerIdentifier = value;
    }
}
~~~

Trong cấu hình phù hợp:

- Reader nhận customerId.
- Reader cũng nhận clientId.
- Serializer tiếp tục dùng tên chính customerId.

**@JsonAlias chủ yếu hỗ trợ deserialization; nó không tự ghi hai tên.** Nếu cần dual-write, phải thiết kế representation đó và xác định thứ tự loại bỏ trường cũ.

### 3.3. Khi hai tên cùng xuất hiện

~~~json
{
  "customerId": "CUS-001",
  "clientId": "CUS-999"
}
~~~

Đây là payload mơ hồ. Nếu hệ thống có alias, cần quyết định rõ có từ chối khi hai tên xung đột hay ưu tiên một tên. Không nên để thứ tự property quyết định ngầm giá trị cho trường quan trọng. Với dữ liệu nhạy cảm, từ chối xung đột có thể là lựa chọn an toàn.

### 3.4. Naming strategy toàn cục cũng là hợp đồng

Nếu một ObjectMapper chuyển từ camelCase sang snake_case, orderId có thể được ghi thành order_id. Thay đổi toàn cục có thể ảnh hưởng nhiều API/event cùng lúc. Nên tách refactor Java khỏi đổi schema và ghi đè tên cụ thể khi cần giữ tương thích.

## 4. Đổi tên theo quy trình expand–migrate–contract

Một cách chuyển tên trường có kiểm soát:

**Expand:** Reader mới nhận cả oldName và newName, nhưng writer vẫn ghi oldName để reader cũ tiếp tục hoạt động.

**Migrate:** Cập nhật từng producer/consumer. Nếu cần, writer tạm ghi hai tên và consumer kiểm tra xung đột thay vì vô tình đọc hai lần.

**Contract:** Sau khi xác minh không còn consumer cũ và dữ liệu lịch sử đã được xử lý, ngừng hỗ trợ oldName theo chính sách.

~~~text
V1: writer -> customerId; reader -> customerId
V2: writer -> customerId; reader -> customerId hoặc clientId
V3: writer -> customerId + clientId; reader -> cả hai
V4: writer -> clientId; reader -> clientId
~~~

Đây là lộ trình minh họa. Trong API công khai nhiều consumer, việc giữ wire name cũ vĩnh viễn đôi khi an toàn và tiết kiệm hơn đổi tên. Dữ liệu event lưu nhiều năm có thể vẫn đòi hỏi reader nhận schema V1 sau khi production đã dùng V4.

## 5. Kiểu dữ liệu trên wire khác kiểu Java

JSON phân biệt object, array, string, number, boolean và null. Java có nhiều kiểu cụ thể hơn:

- byte, short, int, long, float, double.
- BigDecimal và BigInteger.
- String, UUID, char.
- LocalDate, LocalDateTime, OffsetDateTime, Instant.
- Enum.
- List, Set, Map, Optional.
- Record và POJO.
- byte[] và dữ liệu nhị phân.

Một kiểu Java có thể được serialize thành nhiều kiểu wire khác nhau tùy cấu hình. Ví dụ Instant có thể trở thành chuỗi ISO-8601 hoặc số epoch.

Không nên suy luận hai schema tương thích chỉ vì compiler Java có implicit conversion giữa hai kiểu.

### 5.1. int sang long

Trong Java, int có thể widen sang long. Nhưng:

- JSON reader cũ vẫn có thể map vào int.
- Giá trị mới ngoài miền int sẽ gây overflow hoặc parse error.
- Database column kiểu INT có thể không chứa được.
- Consumer khác ngôn ngữ có giới hạn khác.
- Protobuf/Avro có quy tắc type compatibility riêng.

Muốn tăng giới hạn số lượng, cần test giá trị lớn nhất/nhỏ nhất và xem toàn bộ pipeline lưu trữ.

### 5.2. Java long với JavaScript Number

Java long biểu diễn số nguyên 64-bit có dấu. JavaScript Number thông thường chỉ biểu diễn chính xác mọi số nguyên trong khoảng −(2^53−1) đến 2^53−1.

Payload:

~~~json
{"transactionId":9007199254740993}
~~~

có thể mất độ chính xác ở consumer JavaScript dùng Number. Nếu transactionId là định danh, chuỗi có thể phù hợp hơn:

~~~json
{"transactionId":"9007199254740993"}
~~~

Nhưng number → string vẫn là breaking wire change. Cần versioning, migration consumer hoặc trường song song có thời hạn.

### 5.3. Tiền tệ và BigDecimal

Không dùng float/double cho dữ liệu cần số thập phân chính xác nếu không có quy tắc sai số phù hợp.

~~~java
import java.math.BigDecimal;

BigDecimal subtotal = new BigDecimal("125000.25");
BigDecimal tax = subtotal.multiply(new BigDecimal("0.10"));
~~~

Cần đặc tả:

- JSON number hay string?
- Precision, scale và rounding mode?
- Đơn vị tiền, currency?
- Có negative amount không?
- Có chấp nhận scientific notation không?
- Có dùng minor unit (đồng, cent) thay vì decimal không?

Hai biểu diễn không tương đương về JSON type:

~~~json
{"amount":125000.25}
~~~

~~~json
{"amount":"125000.25"}
~~~

Parser có thể có cơ chế coercion, nhưng không nên dựa vào nó như hợp đồng tương thích.

### 5.4. Boolean và string

~~~json
{"enabled":false}
~~~

~~~json
{"enabled":"false"}
~~~

không có cùng kiểu. Một mapping library có thể chuyển "false" thành boolean, library khác có thể từ chối. Đối với request bảo mật, strict parsing thường dễ phát hiện lỗi cấu hình hơn auto-coercion âm thầm.

## 6. Thời gian, timezone và đơn vị timestamp

Một hệ thống cũ có thể dùng java.util.Date hoặc epoch milliseconds, trong khi code mới dùng java.time.Instant hay OffsetDateTime.

Ví dụ:

~~~json
{"createdAt":"2026-11-12T09:30:00Z"}
~~~

và:

~~~json
{"createdAt":1794475800000}
~~~

khác wire type. Khi migrate, cần nêu rõ:

1. Epoch là giây, milliseconds hay microseconds?
2. Giá trị có timezone/offset không?
3. Có chuẩn hóa UTC không?
4. Precision được phép là bao nhiêu?
5. Có cần giữ timezone của người dùng không?
6. Cách xử lý daylight saving time?
7. Có dữ liệu lịch sử không ghi timezone không?

Instant biểu diễn một thời điểm trên timeline; LocalDateTime là ngày giờ địa phương **không có offset/zone**. Chuyển LocalDateTime thành Instant cần ZoneId/offset. Nếu lấy timezone mặc định của server, kết quả có thể thay đổi khi deploy sang vùng khác.

Với event timestamp xuyên hệ thống, nên xác định biểu diễn có offset/UTC rõ ràng. Với lịch họp hoặc giờ mở cửa, có thể cần local time kèm timezone theo nghiệp vụ.

## 7. Enum mới và giá trị ngoài tập đã biết

Producer mới có thể phát:

~~~json
{"status":"PENDING_REVIEW"}
~~~

trong khi reader Java cũ chỉ có:

~~~java
public enum OrderStatus {
    NEW,
    COMPLETED
}
~~~

Tùy thư viện, deserializer có thể báo lỗi khi gặp PENDING_REVIEW. Nếu cấu hình map unknown enum thành null, business logic có thể lỗi tiếp khi sử dụng enum.

Một lựa chọn là thêm UNKNOWN:

~~~java
public enum OrderStatus {
    NEW,
    COMPLETED,
    UNKNOWN
}
~~~

Với Jackson, có thể dùng @JsonEnumDefaultValue và cấu hình READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE trong những phiên bản hỗ trợ. Nhưng fallback phải có nghĩa vụ nghiệp vụ rõ.

**UNKNOWN không đồng nghĩa NEW.** Nếu status mới biểu thị lệnh đang chờ kiểm duyệt, xử lý nó như NEW có thể làm sai luồng. Một consumer có thể cần từ chối hoặc đưa event vào đường xử lý riêng để giữ tính đúng đắn.

Tương tự, Java switch expression có thể gặp vấn đề khi enum được mở rộng mà code không có handling phù hợp. Nên test consumer cũ với enum value mới chứ không chỉ kiểm tra schema.

## 8. Missing, null, empty và default không giống nhau

Những payload sau có thể mang nghĩa khác nhau:

~~~json
{}
~~~

~~~json
{"name":null}
~~~

~~~json
{"name":""}
~~~

~~~json
{"count":0}
~~~

~~~json
{"enabled":false}
~~~

| Trạng thái | Ý nghĩa có thể trong hợp đồng |
|---|---|
| Property missing | Không gửi; dùng default; giữ giá trị cũ trong PATCH |
| Property null | Xóa giá trị; chưa biết; hoặc dữ liệu không hợp lệ |
| Chuỗi rỗng | Có chủ đích là chuỗi độ dài 0 |
| Số 0 | Giá trị số xác định |
| Boolean false | Phủ định xác định |

Không nên gộp missing, null và false nếu nghiệp vụ cần phân biệt.

### 8.1. Primitive Java và default do JVM tạo

~~~java
public final class Flags {
    public int retries;
    public boolean enabled;
}
~~~

Một object mới của Flags có retries = 0, enabled = false. Nếu JSON không có hai property đó, deserializer kiểu no-arg + field assignment thường để lại default tương ứng.

Nhưng 0 hoặc false không cho biết client đã gửi có chủ đích hay chỉ bỏ sót trường. Nếu cần phân biệt, primitive không đủ biểu diễn presence.

### 8.2. Wrapper không giải quyết hoàn toàn missing vs null

~~~java
public final class Flags {
    public Integer retries;
    public Boolean enabled;
}
~~~

Integer/Boolean có thể chứa null, nhưng một DTO đơn giản thường vẫn không phân biệt property missing và property explicitly null nếu cả hai được map thành null.

Khi xử lý PATCH, có thể cần một kiểu dữ liệu có ba trạng thái:

~~~text
UNSET -> không gửi trường, giữ dữ liệu cũ
NULL  -> gửi null, yêu cầu xóa
VALUE -> gửi giá trị mới
~~~

Có thể dùng JsonNode để kiểm tra presence, JSON Merge Patch/JSON Patch hoặc một wrapper chuyên dụng. Nên mô tả chính xác semantics trong API contract.

### 8.3. Ví dụ xử lý PATCH rõ ràng

~~~java
import com.fasterxml.jackson.databind.JsonNode;

public void applyPatch(JsonNode patch, Customer customer) {
    if (!patch.has("name")) {
        return;
    }

    JsonNode value = patch.get("name");

    if (value.isNull()) {
        customer.clearName();
    } else if (value.isTextual()) {
        customer.setName(value.asText());
    } else {
        throw new IllegalArgumentException(
            "name must be string or null");
    }
}
~~~

Customer là domain API minh họa. Điểm chính là absence và explicit null dẫn đến hai hành động khác nhau.

## 9. Giá trị mặc định khi thêm trường

V1:

~~~json
{
  "orderId": "ORD-001",
  "items": 2
}
~~~

V2:

~~~json
{
  "orderId": "ORD-001",
  "items": 2,
  "priority": "NORMAL"
}
~~~

Reader V2 cần cách đọc V1 không có priority. Các phương án:

- Mặc định NORMAL nếu đúng với dữ liệu V1.
- Cho phép null/UNKNOWN và yêu cầu logic nghiệp vụ xử lý.
- Thực hiện backfill dữ liệu trước khi bật xử lý V2.
- Dùng schema default ở định dạng hỗ trợ.
- Versioning nếu không thể diễn giải V1 một cách an toàn.

Một default tốt phải đáp ứng:

1. Được producer và consumer thống nhất về ý nghĩa.
2. Không làm mất thông tin unknown nếu thông tin đó quan trọng.
3. Phân biệt missing với explicit null nếu contract yêu cầu.
4. Không phụ thuộc timezone/environment không kiểm soát.
5. Được test bằng dữ liệu lịch sử.
6. Không tự tạo thông tin nhạy cảm như quyền hoặc currency.

Ví dụ, currency = USD không phải default an toàn nếu đơn hàng cũ không ghi currency và có thể thuộc nhiều loại tiền.

### 9.1. Initializer và constructor default

~~~java
public final class RetryConfig {
    public int attempts = 3;
    public boolean enabled = true;
}
~~~

Nếu deserializer tạo object qua no-arg constructor, missing property có thể giữ giá trị initializer. Nhưng explicit attempts = 0 thường ghi đè thành 0. Cấu hình null handling có thể khác, và creator-based deserialization có hành vi riêng.

Khi nâng Jackson hoặc chuyển POJO sang record, cần thử lại payload thiếu trường để xác nhận default thực tế.

## 10. Jackson: thuộc tính chưa biết trong JSON

Một reader cũ:

~~~java
public final class CustomerDto {
    public String id;
    public String name;
}
~~~

nhận payload mới:

~~~json
{
  "id": "CUS-001",
  "name": "An",
  "preferredLocale": "vi-VN"
}
~~~

Nếu Jackson bật FAIL_ON_UNKNOWN_PROPERTIES, có thể ném UnrecognizedPropertyException.

### 10.1. Ignore unknown theo DTO

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public final class CustomerDto {
    public String id;
    public String name;
}
~~~

Trong cấu hình Jackson thông thường, reader có thể đọc id/name và bỏ qua preferredLocale.

### 10.2. Cấu hình ở ObjectMapper

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

mapper.configure(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
    false
);
~~~

Điều này có thể ảnh hưởng nhiều DTO sử dụng cùng mapper. Không nên tắt strictness toàn cục chỉ để xử lý một lỗi tương thích.

Ví dụ client gửi nhầm:

~~~json
{"isAmin":true}
~~~

Nếu dự kiến là isAdmin nhưng tên bị typo, một reader bỏ qua unknown có thể khiến caller tưởng yêu cầu đã được thực hiện. Với dữ liệu liên quan phân quyền, thanh toán hoặc cấu hình an toàn, việc từ chối unknown fields thường thích hợp hơn.

### 10.3. Chọn chính sách theo ngữ cảnh

| Dữ liệu | Chính sách có thể phù hợp |
|---|---|
| Event producer được nâng trước consumer | Ignore unknown theo contract |
| API command có validation chặt | Reject unknown để phát hiện lỗi |
| Đối tác thay đổi payload thường xuyên | Ignore hoặc whitelist kèm quan sát |
| Cấu hình quyền/bảo mật | Strict parsing và validation |
| Dữ liệu cần round-trip không mất trường | Preserve unknown có giới hạn |
| Payload công khai không tin cậy | Giới hạn size/depth và allowlist |

Không có một cấu hình đúng cho mọi endpoint. “Tolerant reader” chỉ có ích khi nó không làm mất tính đúng đắn hoặc an toàn.

## 11. Preserve unknown fields để round-trip

Khi một service đọc rồi ghi lại payload, việc ignore unknown làm trường lạ **biến mất** khi serialize lại.

Ví dụ V2 gửi:

~~~json
{
  "id": "CUS-001",
  "name": "An",
  "preferredLocale": "vi-VN"
}
~~~

Một reader chỉ hiểu id/name nhưng làm vai trò forwarding service cần giữ preferredLocale. Có thể dùng extension map:

~~~java
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.LinkedHashMap;
import java.util.Map;

public final class CustomerEnvelope {
    public String id;
    public String name;

    private final Map<String, JsonNode> extra =
        new LinkedHashMap<>();

    @JsonAnySetter
    public void putExtra(String key, JsonNode value) {
        extra.put(key, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> getExtra() {
        return extra;
    }
}
~~~

Trong cấu hình Jackson phù hợp, unknown properties có thể được lưu vào extra và ghi lại.

Nhưng cần kiểm soát:

- Kích thước và độ sâu của dữ liệu extension.
- Va chạm giữa extra và property đã định nghĩa.
- Các trường nhạy cảm không được ghi log/chuyển tiếp.
- Trường lạ hôm nay có thể thành property chính thức ngày mai.
- Việc round-trip có giữ nguyên định dạng/precision cần thiết không.
- Chính sách từ chối hoặc phân vùng namespace cho property không đáng tin cậy.

Preserve unknown không phải một cách được phép để bỏ qua validation hoặc authorization.

## 12. Java record và constructor binding

Khi hiện đại hóa code, một POJO có thể được chuyển thành Java record:

~~~java
public record UserView(
    String id,
    String displayName,
    int loginCount
) { }
~~~

Record dùng component và canonical constructor. Framework deserialize có thể cần map dữ liệu theo constructor, khác với POJO có no-arg constructor và setter.

Nếu payload cũ thiếu loginCount:

~~~json
{"id":"U-001","displayName":"An"}
~~~

cần kiểm tra version Jackson và cấu hình creator/missing/null. Một số cấu hình đưa default primitive 0; chế độ strict có thể từ chối.

### 12.1. Compact constructor để bảo vệ invariant

~~~java
public record UserView(
    String id,
    String displayName,
    int loginCount
) {
    public UserView {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
        if (loginCount < 0) {
            throw new IllegalArgumentException(
                "loginCount cannot be negative");
        }
    }
}
~~~

Validation làm object không nhận trạng thái sai, nhưng không tự giải quyết việc missing loginCount có nghĩa là 0 hay UNKNOWN. Nếu contract phải phân biệt, cần DTO/schema có presence.

Đừng thay đổi Java DTO từ class sang record và đổi tên/kiểu dữ liệu trong cùng lượt nếu có thể tách để dễ khoanh vùng lỗi.

## 13. Optional và nullable DTO

Optional<T> trong Java API giúp biểu diễn kết quả có hoặc không có. Nhưng Optional đặt làm field JSON DTO không tự động biểu diễn được ba trạng thái missing, null và value.

Tùy phiên bản Jackson, module Jdk8Module và inclusion settings, Optional.empty có thể được serialize theo cách khác nhau. Nếu cần payload ổn định, hãy cấu hình và kiểm thử cụ thể.

Khi một API cập nhật từng phần, nên dùng DTO/command riêng để thể hiện presence rõ ràng. Không nên dựa vào null-check để suy luận phía client đã bỏ qua field hay yêu cầu xóa dữ liệu.

## 14. Default ở database khác default của JSON

Một schema database:

~~~sql
ALTER TABLE orders
ADD COLUMN priority VARCHAR(16) DEFAULT 'NORMAL';
~~~

không tự bảo đảm mọi Java object hay JSON event đều có priority.

Nhiều database áp dụng default khi INSERT **bỏ qua column** hoặc yêu cầu DEFAULT, nhưng explicit NULL có thể mang hành vi khác. ORM đôi khi gửi null cụ thể nên DB default không được dùng như người phát triển tưởng.

Còn có nhiều ranh giới:

- Dữ liệu lịch sử trước migration.
- Snapshot và backup.
- Cache được tạo bằng schema cũ.
- Event đã publish trước khi thêm column.
- Service cũ còn ghi trong quá trình rolling deployment.

### 14.1. Expand–migrate–contract cho database

1. Thêm column mới ở trạng thái có thể đọc cùng code cũ.
2. Deploy reader hiểu schema mới và cũ.
3. Backfill lịch sử nếu có logic suy luận hợp lệ.
4. Deploy writer ghi field mới.
5. Theo dõi consumer và job còn dùng column cũ.
6. Thêm NOT NULL/constraint và loại column cũ khi an toàn.

Default Java, default trong database và default ở event schema là ba cơ chế khác nhau. Chúng phải được đồng bộ về **ý nghĩa nghiệp vụ**, không mặc định tự có hiệu lực ở mọi tầng.

## 15. Protobuf: field number quan trọng hơn tên trong binary

Protocol Buffers dùng field number trong binary wire format.

~~~proto
syntax = "proto3";

message Order {
  string order_id = 1;
  int64 total_minor = 2;
  string currency = 3;
}
~~~

### 15.1. Không tái sử dụng tag đã xóa

Nếu bỏ currency, nên reserve tag/name để tránh một schema sau dùng tag 3 cho ý nghĩa khác:

~~~proto
syntax = "proto3";

message Order {
  reserved 3;
  reserved "currency";

  string order_id = 1;
  int64 total_minor = 2;
}
~~~

Dữ liệu lịch sử có thể vẫn chứa tag 3. Tái sử dụng tag có thể gây diễn giải nhầm.

### 15.2. Rename trong .proto không giống rename JSON

Giữ field number và type có thể duy trì một phần binary compatibility. Nhưng rename vẫn có thể làm hỏng:

- Generated Java getter/setter.
- Protobuf JSON mapping.
- Reflection dựa vào descriptor name.
- Tooling và schema validation.

Không nên nói “đổi tên field Protobuf là luôn an toàn”.

### 15.3. Unknown fields trong Protobuf

Một số binary parser/runtime Protobuf có khả năng giữ unknown fields khi parse và serialize lại. Nhưng dữ liệu có thể bị mất khi:

- Chuyển sang Protobuf JSON rồi chuyển lại.
- Map thủ công sang domain DTO không giữ unknown.
- Rebuild message chỉ từ known fields.
- Dùng một runtime/option discard unknown.

Cần kiểm thử đúng pipeline. Cấu hình ignoreUnknownFields của Protobuf JSON parser không mang nghĩa tự bảo tồn unknown properties.

### 15.4. Default và field presence

Với proto3 scalar fields dùng implicit presence, default như 0, false hoặc chuỗi rỗng có thể không phân biệt được “field vắng mặt” và “field có default”. Những field khai báo optional theo quy tắc được hỗ trợ có thể cung cấp explicit presence.

Nếu một use case yêu cầu phân biệt missing với zero, cần thiết kế presence từ schema; đừng trông chờ Java primitive của generated class tự giải quyết.

## 16. Avro: writer schema, reader schema và default

Avro có cơ chế schema resolution giữa schema của dữ liệu được ghi và schema của bên đọc.

Writer V1:

~~~json
{
  "type": "record",
  "name": "Order",
  "fields": [
    {"name": "orderId", "type": "string"}
  ]
}
~~~

Reader V2:

~~~json
{
  "type": "record",
  "name": "Order",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "priority", "type": "string", "default": "NORMAL"}
  ]
}
~~~

Khi reader V2 đọc dữ liệu V1 không có priority, default ở reader schema có thể được dùng để bổ sung giá trị trong quá trình resolution.

**Avro default không chỉ đơn giản là lệnh writer tự ghi field đó vào mọi record.** Phải phân biệt schema của writer và reader.

### 16.1. Rename bằng aliases

Avro hỗ trợ aliases trong một số tình huống rename; khả năng tương thích còn phụ thuộc schema registry, version và tooling. Alias trên reader mới không tự làm reader cũ hiểu tên do writer mới ghi.

### 16.2. Union với null

~~~json
{
  "name": "description",
  "type": ["null", "string"],
  "default": null
}
~~~

Cần kiểm tra default và quy tắc union branch theo đặc tả Avro/version sử dụng. Một default không phù hợp với schema không phải giải pháp thực tế cho dữ liệu thiếu.

### 16.3. Schema registry không thay thế test nghiệp vụ

Registry có thể phát hiện một số thay đổi schema vi phạm compatibility policy, nhưng không thể biết priority = NORMAL có đúng với dữ liệu năm trước hay không, hoặc consumer có hard-code enum nào. Contract tests vẫn cần thiết.

## 17. JSON Schema và unknown-property policy

JSON Schema có thể định nghĩa property names, required fields, type, giới hạn giá trị và chính sách cho các property ngoài danh sách.

Ví dụ strict:

~~~json
{
  "type": "object",
  "properties": {
    "orderId": {"type": "string"},
    "quantity": {"type": "integer", "minimum": 0}
  },
  "required": ["orderId"],
  "additionalProperties": false
}
~~~

Với additionalProperties: false, validator có thể từ chối trường khác ngoài schema cho phép.

Ví dụ mở hơn:

~~~json
{
  "type": "object",
  "properties": {
    "orderId": {"type": "string"}
  },
  "required": ["orderId"],
  "additionalProperties": true
}
~~~

Open schema có thể giúp reader cũ chấp nhận property mới, nhưng cũng dễ bỏ qua typo. Cần quyết định theo domain:

- Event có thể được thiết kế để reader bỏ qua field chưa biết.
- API command hoặc cấu hình quyền có thể strict.
- Extension metadata có thể nằm dưới namespace extensions.
- Request không tin cậy phải có quota, depth/size limits.
- Với object lồng nhau, open/closed policy cần xét từng cấp.

## 18. Object lồng nhau và collection cũng tiến hóa schema

Đổi:

~~~json
{
  "shipping": {
    "address": "123 Example St"
  }
}
~~~

sang:

~~~json
{
  "shipping": {
    "address": {
      "line1": "123 Example St",
      "country": "VN"
    }
  }
}
~~~

làm shipping.address đổi từ string thành object. Consumer cũ có thể lỗi dù tên property không đổi.

Tương tự:

~~~json
{"items":["A","B"]}
~~~

khác:

~~~json
{"items":{"A":1,"B":1}}
~~~

Đổi array thành map làm thay đổi ordering, duplicate semantics và element type.

### 18.1. Null list, empty list và missing list

~~~json
{}
~~~

~~~json
{"items":null}
~~~

~~~json
{"items":[]}
~~~

có thể mang ba ý nghĩa. Việc map cả ba thành Collections.emptyList có thể làm mất thông tin nếu logic nghiệp vụ phân biệt “không gửi danh sách” với “danh sách có chủ đích rỗng”.

### 18.2. Map keys

JSON object key là chuỗi. Java Map có thể dùng UUID, Integer hoặc enum key và serializer chuyển sang text. Khi đổi key type/naming, round-trip có thể không nhất quán. Một API đa ngôn ngữ có thể chọn array of entries để biểu diễn các key phức tạp theo schema tường minh.

## 19. Unknown properties và bảo mật mass assignment

Một endpoint nhận JSON rồi map trực tiếp vào entity có thể vô tình chấp nhận những field mà client không được phép sửa.

~~~json
{
  "displayName": "An",
  "role": "ADMIN",
  "accountLocked": false
}
~~~

Nếu hệ thống tự động copy mọi property từ request sang entity, nó có thể tạo privilege escalation hoặc sửa trạng thái bảo mật.

Giải pháp đúng:

- DTO request chỉ chứa field được phép.
- Validate và kiểm tra authorization theo caller.
- Map có kiểm soát từ DTO sang domain.
- Không tự copy unknown properties vào entity.
- Không dùng ignoreUnknownProperties như cơ chế bảo vệ quyền.
- Từ chối field nhạy cảm chưa được khai báo khi phù hợp.

Nếu preserve unknown để forward, phải bảo đảm không đưa raw data chưa kiểm duyệt qua trust boundary đến service có quyền cao hơn. Cũng cần giới hạn object depth, property count, string length, array length, retention và logging.

## 20. Dữ liệu lịch sử, replay và schema version

Các hệ thống event-driven có thể replay dữ liệu nhiều năm sau khi producer ban đầu đã thay đổi:

~~~text
2023: Event V1 -> orderId, total
2024: Event V2 -> orderId, total, currency
2026: Event V3 -> orderId, totalMinor, currency, tax
~~~

Reader mới có thể phải xử lý cả V1, V2 và V3. Nếu currency của event cũ không được lưu, việc gán đại VND hoặc USD có thể làm kết quả replay khác với nghiệp vụ gốc.

### 20.1. Versioned payload và upcaster

~~~json
{
  "schemaVersion": 1,
  "eventType": "OrderCreated",
  "payload": {
    "orderId": "ORD-001",
    "total": 125000
  }
}
~~~

Một reader có thể áp dụng các bước chuyển representation:

~~~text
Event V1
   |
   v
Upcast V1 -> V2
   |
   v
Upcast V2 -> V3
   |
   v
Domain handling V3
~~~

Upcaster cần có fixture lịch sử, logic lặp lại được, không âm thầm bịa dữ liệu thiếu và ghi rõ giá trị nào được suy ra. Nếu dùng Protobuf/Avro và schema registry, có thể có cơ chế gắn schema id khác; không nhất thiết phải tự thêm schemaVersion vào mọi payload.

## 21. Request, response và event có hướng tương thích khác nhau

### 21.1. API request

Client là writer; server là reader. Nếu server mới thêm field bắt buộc, client cũ có thể không gửi được. Cần default đúng, chế độ tương thích hoặc version endpoint.

Unknown fields trong request có thể là lỗi typo hoặc hành vi không được hỗ trợ, đặc biệt ở command bảo mật. Không nên mặc định mở schema.

### 21.2. API response

Server là writer; client là reader. Thêm field mới thường có thể tương thích nếu client bỏ qua unknown. Xóa hoặc đổi tên field có thể phá client cũ.

### 21.3. Event

Producer là writer; consumer là reader. Có thể có nhiều consumer độc lập và dữ liệu lưu trong broker lâu dài. Tương thích phải xét retention, replay và rollout order.

### 21.4. Database

Ứng dụng mới và cũ có thể đồng thời đọc/ghi một bảng khi rolling deployment. Expand–migrate–contract thường an toàn hơn việc rename/drop column ngay.

## 22. Contract tests cho dữ liệu đa phiên bản

Nên lưu một bộ payload fixture đại diện:

~~~text
fixtures/
  order-v1-minimal.json
  order-v1-full.json
  order-v2-optional.json
  order-v2-unknown-enum.json
  order-v3-unknown-fields.json
  order-invalid-null.json
  order-invalid-type.json
  order-large-integer.json
  order-old-timestamp.json
~~~

Fixture có thể là dữ liệu tổng hợp hoặc đã loại thông tin nhạy cảm. Đừng vô tình ghi đè fixture cũ bằng output của serializer mới; cần giữ bằng chứng của wire contract thực tế trước migration.

### 22.1. Các tình huống cần kiểm thử

- Reader mới đọc payload của writer cũ.
- Reader cũ đọc payload mới trong phạm vi hỗ trợ.
- Missing field nhận default đúng.
- Explicit null khác absent khi contract yêu cầu.
- Alias rename hoạt động; output không đổi ngoài ý muốn.
- Unknown field bị ignore/reject/preserve theo policy.
- Số lớn, số âm, precision/scale và overflow.
- Enum value mới được xử lý an toàn.
- Timestamp units, offset và timezone.
- Nested object và array/map element type.
- Schema migration và dữ liệu lịch sử replay.
- Unknown field không gây mass assignment.
- Payload quá lớn/quá sâu bị giới hạn.
- Round-trip giữ được field cần bảo tồn.

### 22.2. Reader–writer matrix

| Writer | Reader | Mục tiêu |
|---|---|---|
| V1 | V1 | Baseline |
| V1 | V2 | Đọc dữ liệu cũ |
| V2 | V1 | Reader cũ vẫn hiểu dữ liệu mới nếu được cam kết |
| V2 | V2 | Hành vi mới |
| V1 fixture | V3 | Replay lịch sử |
| V3 malformed | V3 | Từ chối dữ liệu sai |

Không phải hệ thống nào cũng cam kết mọi cặp version. Ma trận phải phản ánh chính sách phát hành, vòng đời client và thời gian lưu dữ liệu.

## 23. Quy trình migration thực tế

### Bước 1 — Kiểm kê hợp đồng

Ghi rõ:

- Endpoint, topic, file format hoặc database table.
- Producer/consumer và version đang chạy.
- JSON/Jackson, Protobuf/Avro hoặc serializer khác.
- Java runtime và dependency versions.
- Schema registry/schema validation.
- Dữ liệu lịch sử cần hỗ trợ.
- Client khác ngôn ngữ hoặc plugin bên thứ ba.

### Bước 2 — Ghi nhận baseline

Lưu payload thực tế về tên, kiểu, default, nullability, enum, timestamp, unknown fields, collection và serialization options.

### Bước 3 — Phân loại thay đổi

| Thuộc tính | Trước | Sau | Rủi ro |
|---|---|---|---|
| Tên | customerId | clientId | Consumer thiếu tên cũ |
| Kiểu | int | long | Overflow ở reader cũ |
| Required | Optional | Required | Dữ liệu cũ thiếu |
| Default | null | NORMAL | Diễn giải lại lịch sử |
| Enum | NEW, DONE | Thêm REVIEW | Reader cũ không hiểu |
| Unknown policy | Ignore | Reject | Forward compatibility giảm |
| Time | Epoch ms | ISO string | Parser và timezone |

### Bước 4 — Chọn chiều tương thích

Khi rolling deploy, thường nên bảo đảm reader mới có khả năng xử lý dữ liệu cũ **trước khi** writer mới phát payload mới. Nếu client cũ sống lâu, phải giữ thêm hướng reader cũ hiểu payload mới.

### Bước 5 — Áp dụng cơ chế phù hợp

- @JsonProperty để giữ wire name.
- @JsonAlias cho reader hỗ trợ rename.
- Optional field và default có nghĩa.
- DTO/version endpoint mới nếu đổi contract lớn.
- Schema compatibility của Avro/Protobuf/JSON Schema.
- Upcaster cho event lịch sử.
- Dual-read/dual-write có giới hạn thời gian.
- Database expand–migrate–contract.
- Preserve unknown có giới hạn.
- Strict validation cho command nhạy cảm.

### Bước 6 — Chạy trên JDK và dependency mục tiêu

Nâng Java, Jackson, Protobuf runtime hoặc Avro library có thể đổi coercion, property naming, null handling và enum behavior. Kiểm tra với đúng dependency graph và serializer configuration sẽ được deploy.

Tránh đồng thời đổi JDK, HTTP client, serializer, database schema và wire contract nếu có thể tách để khoanh vùng lỗi.

### Bước 7 — Deploy có thứ tự

1. Deploy reader đọc được schema cũ và mới.
2. Quan sát client/consumer còn dùng format cũ.
3. Deploy writer mới hoặc bật feature flag.
4. Theo dõi deserialization và business validation failures.
5. Backfill khi có dữ liệu nguồn đáng tin.
6. Chỉ loại bỏ fallback sau mốc hỗ trợ.

### Bước 8 — Theo dõi và rollback

Nên quan sát:

- Unknown-field errors.
- Missing required-field errors.
- Type/coercion failures.
- Enum parsing failures.
- Dead-letter queue và consumer lag.
- Replay/backfill failures.
- Mất field khi round-trip.
- Tỷ lệ payload theo schema version.
- Bất thường kết quả nghiệp vụ.

Rollback không đơn giản là quay lại binary cũ nếu writer mới đã ghi dữ liệu mà reader cũ không hiểu. **Reader-first rollout** giảm rủi ro đó.

## 24. Những nhầm lẫn phổ biến

### “Đổi tên field Java không ảnh hưởng API”

Sai nếu serializer dùng field/getter/record component naming convention. Cần giữ wire name hoặc version schema.

### “Thêm field JSON luôn an toàn”

Chỉ nếu consumer có chính sách unknown phù hợp và reader mới không yêu cầu field mà dữ liệu cũ thiếu.

### “Parser sẽ tự convert string sang number”

Không nên dựa vào coercion. Cấu hình mới có thể strict hơn, hoặc dữ liệu vượt miền số.

### “Missing và null giống nhau”

Sai với PATCH hoặc hợp đồng cần phân biệt “giữ nguyên” và “xóa”.

### “Default giải quyết mọi dữ liệu cũ”

Chỉ khi default có nghĩa nghiệp vụ đúng. Default sai có thể tạo dữ liệu không có thật.

### “Ignore unknown toàn cục là best practice”

Không phải. Nó có thể che typo và request field không hợp lệ.

### “Ignore unknown bảo toàn dữ liệu khi round-trip”

Sai. Field bị bỏ qua thường không được ghi lại nếu serialize DTO một lần nữa.

### “Đổi tên Protobuf field không phá compatibility”

Binary tag có thể giữ được một phần, nhưng generated source và JSON mapping có thể thay đổi.

### “Schema registry compatible nghĩa là hệ thống đã an toàn”

Registry thường chỉ đánh giá quy tắc schema, không kiểm tra enum logic, default nghiệp vụ, authorization hoặc replay behavior.

### “long JSON luôn chính xác ở mọi ngôn ngữ”

Không đúng với consumer dùng JavaScript Number cho số lớn.

## 25. Mẫu hồ sơ quyết định compatibility

~~~text
CONTRACT
  Endpoint/topic/table:
  Producer:
  Consumer(s):
  Data format:
  Schema and version:
  Serializer/version:
  Current and target JDK:

FIELD CHANGE
  Old wire name:
  New wire name:
  Old type:
  New type:
  Optional/required:
  Missing semantics:
  Explicit null semantics:
  Default and business meaning:
  Enum values:
  Unknown field policy:
  Historical retention:

COMPATIBILITY
  New reader / old writer:
  Old reader / new writer:
  Binary/schema compatibility:
  Generated API compatibility:
  Numeric/time constraints:
  Validation/security:
  Round-trip requirement:

MIGRATION
  Alias/dual-read:
  Dual-write:
  Backfill/upcaster:
  Reader-first rollout:
  Deprecation milestone:
  Rollback strategy:

VALIDATION
  Old/new fixtures:
  Missing and null cases:
  Unknown-field cases:
  Boundary/precision:
  Contract tests:
  Replay tests:
  Canary metrics:
~~~

Hồ sơ nên được lưu cùng schema và artifact versions để những lần nâng Java sau không phải suy đoán về ý nghĩa của default hoặc tên trường cũ.

## 26. Tổng kết

Hợp đồng dữ liệu ổn định không chỉ là tập tên field và kiểu Java. Nó bao gồm tên trên wire, miền giá trị, ngữ nghĩa missing/null, default, unknown-field behavior và khả năng đọc dữ liệu ở các phiên bản khác nhau.

Những nguyên tắc cần giữ:

1. **Tên trên wire:** Không đổi ngoài ý muốn khi refactor Java.
2. **Kiểu dữ liệu:** Không giả định parser có thể convert tự động mà vẫn đúng.
3. **Default:** Chỉ áp dụng khi có ngữ nghĩa nghiệp vụ rõ ràng.
4. **Missing và null:** Phân biệt khi ảnh hưởng đến update, quyền hoặc trạng thái.
5. **Unknown fields:** Chọn ignore, reject hoặc preserve theo từng contract và giới hạn bảo mật.
6. **Protocol-specific:** JSON, Protobuf, Avro và database có quy tắc tương thích khác nhau.
7. **Reader–writer tests:** Kiểm chứng các phiên bản cùng tồn tại và dữ liệu lịch sử.
8. **Rollout có thứ tự:** Reader mới cần sẵn sàng trước khi writer phát schema mới, rồi mới loại bỏ hợp đồng cũ.

Khi đặt hợp đồng dữ liệu lên trước thay đổi cấu trúc Java, nhóm phát triển có thể nâng JDK và thư viện serialization mà vẫn giữ được khả năng đọc dữ liệu lịch sử, giao tiếp với consumer chưa nâng cấp và xử lý thuộc tính mới một cách có kiểm soát.
