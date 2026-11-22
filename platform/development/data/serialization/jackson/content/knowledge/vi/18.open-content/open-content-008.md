# Đánh giá rủi ro khi trộn thuộc tính tĩnh với dữ liệu mở rộng

Trong nhiều API, một object có một nhóm thuộc tính ổn định và một nhóm thuộc tính có thể thay đổi theo đối tác, phiên bản hoặc loại sự kiện. Ví dụ, một sự kiện luôn có `id`, `type` và `createdAt`, nhưng payload có thể mang thêm những trường riêng như `campaignCode`, `deviceModel` hoặc `partnerRegion`.

Jackson hỗ trợ mô hình này bằng `@JsonAnySetter` và `@JsonAnyGetter`. `@JsonAnySetter` nhận các thuộc tính JSON không khớp với property đã khai báo và đưa chúng vào một cấu trúc mở rộng, thường là `Map`. `@JsonAnyGetter` phát các entry trong map đó thành các thuộc tính JSON cùng cấp với những thuộc tính tĩnh.

Cách làm này linh hoạt, nhưng trộn dữ liệu tĩnh và dữ liệu mở rộng trong cùng một object tạo ra nhiều rủi ro: khóa trùng, thay đổi schema theo thời gian, dữ liệu không được validate, mass assignment, rò rỉ trường lạ, kiểu runtime không ổn định và payload tiêu tốn tài nguyên. Cần thiết kế rõ ranh giới giữa thuộc tính được ứng dụng hiểu và thuộc tính chỉ được giữ lại để tương thích.

## 1. Thuộc tính tĩnh và dữ liệu mở rộng là gì?

**Thuộc tính tĩnh** là những field đã được mô hình Java khai báo, có tên, kiểu và ý nghĩa ổn định. Ví dụ:

```java
public class PartnerEvent {
    private String id;
    private String type;
    private Instant createdAt;
}
```

Ứng dụng biết `id` là định danh, `type` là loại sự kiện và `createdAt` là thời điểm phát sinh. Các field này có thể được validate, dùng trong logic và được compiler hỗ trợ.

**Dữ liệu mở rộng** là những thuộc tính không nằm trong schema tĩnh nhưng cần được giữ lại hoặc chuyển tiếp. Ví dụ một đối tác gửi thêm:

```json
{
  "id": "evt-1001",
  "type": "order.created",
  "createdAt": "2026-11-12T09:00:00Z",
  "partnerRegion": "south",
  "campaignCode": "NOV26",
  "deviceModel": "terminal-x"
}
```

Các trường `partnerRegion`, `campaignCode` và `deviceModel` có thể khác nhau giữa các đối tác. Nếu DTO chỉ khai báo ba field cố định, Jackson thường xem các trường còn lại là không xác định. `@JsonAnySetter` cho phép thu thập chúng vào map thay vì từ chối hoặc bỏ qua.

## 2. Dùng @JsonAnySetter để nhận thuộc tính chưa khai báo

Ví dụ DTO có một map lưu các extension:

```java
import com.fasterxml.jackson.annotation.JsonAnySetter;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public class PartnerEvent {
    private String id;
    private String type;
    private Instant createdAt;
    private final Map<String, Object> extensions = new LinkedHashMap<>();

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    @JsonAnySetter
    public void addExtension(String name, Object value) {
        extensions.put(name, value);
    }

    public Map<String, Object> getExtensions() {
        return extensions;
    }
}
```

Khi Jackson đọc một object, các property đã được nhận diện như `id`, `type` và `createdAt` sẽ được ánh xạ vào field tương ứng. Những property còn lại được chuyển tới phương thức `addExtension(name, value)`.

Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper();
PartnerEvent event = mapper.readValue(json, PartnerEvent.class);

Object region = event.getExtensions().get("partnerRegion");
```

`@JsonAnySetter` thường được đặt trên một phương thức nhận hai tham số: tên property và giá trị. Jackson gọi phương thức này cho từng property không được xử lý bởi property tĩnh. Có thể dùng `Object` để nhận nhiều loại JSON, hoặc dùng kiểu cụ thể hơn khi extension có schema rõ ràng.

Nếu không khai báo any-setter và mapper đang bật `FAIL_ON_UNKNOWN_PROPERTIES`, một trường không biết có thể làm quá trình deserialize thất bại. Nếu tắt feature đó, trường lạ có thể bị bỏ qua. `@JsonAnySetter` tạo lựa chọn thứ ba: nhận và giữ lại dữ liệu mở rộng.

## 3. Dùng @JsonAnyGetter để ghi extension thành property cùng cấp

`@JsonAnySetter` chỉ giải quyết chiều đọc. Nếu muốn các entry trong map xuất hiện thành các khóa JSON ở cùng cấp với field tĩnh, dùng `@JsonAnyGetter`:

```java
import com.fasterxml.jackson.annotation.JsonAnyGetter;

public class PartnerEvent {
    // Các field và getter/setter khác.

    private final Map<String, Object> extensions = new LinkedHashMap<>();

    @JsonAnySetter
    public void addExtension(String name, Object value) {
        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, Object> any() {
        return extensions;
    }
}
```

Nếu map có:

```java
event.getExtensions().put("partnerRegion", "south");
event.getExtensions().put("campaignCode", "NOV26");
```

JSON đầu ra có dạng:

```json
{
  "id": "evt-1001",
  "type": "order.created",
  "partnerRegion": "south",
  "campaignCode": "NOV26"
}
```

Các entry trong map được ghi như thuộc tính của object ngoài cùng, không nằm dưới một khóa `extensions`. Nếu muốn JSON có dạng:

```json
{
  "id": "evt-1001",
  "extensions": {
    "partnerRegion": "south",
    "campaignCode": "NOV26"
  }
}
```

thì chỉ cần khai báo map như một property bình thường và không dùng `@JsonAnyGetter` cho map đó. Hai hình thức có hợp đồng JSON khác nhau; cần chọn một hình thức nhất quán.

## 4. Rủi ro khóa mở rộng trùng với thuộc tính tĩnh

Đây là rủi ro quan trọng khi trộn hai nhóm property. Giả sử DTO có field tĩnh `id`, nhưng map extension cũng chứa khóa `id`:

```java
event.setId("evt-1001");
event.getExtensions().put("id", "attacker-controlled-id");
```

Khi `@JsonAnyGetter` phát map, output có thể chứa hai member cùng tên `id` hoặc tạo kết quả phụ thuộc vào cách serializer xử lý property và generator. JSON object không nên có khóa trùng; các parser khác nhau có thể chọn giá trị đầu, giá trị cuối hoặc xử lý theo cách khác. Không được dựa vào hành vi đó.

Ở chiều đọc, nếu JSON có khóa trùng:

```json
{
  "id": "evt-1001",
  "id": "evt-overwritten"
}
```

parser hoặc databind có thể chấp nhận và giá trị cuối cùng ghi đè giá trị trước, tùy cấu hình. Trường hợp này làm dữ liệu khó kiểm toán và có thể gây khác biệt giữa các thành phần trong hệ thống.

### 4.1. Quy định namespace hoặc prefix cho extension

Một cách giảm va chạm là yêu cầu extension dùng một namespace riêng:

```json
{
  "id": "evt-1001",
  "type": "order.created",
  "x_partner_region": "south",
  "x_campaign_code": "NOV26"
}
```

Hoặc đặt toàn bộ extension trong một object riêng:

```json
{
  "id": "evt-1001",
  "type": "order.created",
  "extensions": {
    "partnerRegion": "south",
    "campaignCode": "NOV26"
  }
}
```

Object lồng `extensions` tạo ranh giới rõ ràng nhất: khóa bên trong không thể nhầm với field cấp cao nhất. Nếu phải dùng `@JsonAnyGetter` để tương thích một giao thức phẳng, hãy quy định prefix hoặc danh sách khóa được dành riêng.

### 4.2. Kiểm tra khóa dành riêng

Any-setter có thể từ chối các tên không được phép:

```java
private static final Set<String> RESERVED = Set.of(
    "id", "type", "createdAt", "extensions"
);

@JsonAnySetter
public void addExtension(String name, JsonNode value) {
    if (RESERVED.contains(name)) {
        throw new IllegalArgumentException(
            "Extension key is reserved: " + name
        );
    }
    extensions.put(name, value);
}
```

Trong nhiều trường hợp Jackson sẽ xử lý các property đã biết bằng setter/field tĩnh thay vì gọi any-setter. Việc kiểm tra reserved key vẫn hữu ích khi map được tạo hoặc sửa từ code Java, khi có alias/naming strategy hoặc khi dữ liệu được hợp nhất từ nhiều nguồn. Trước khi serialize, nên kiểm tra map không chứa khóa trùng với property tĩnh.

## 5. Rủi ro schema evolution: một extension hôm nay có thể thành field tĩnh ngày mai

Giả sử phiên bản đầu tiên không biết `partnerRegion`, nên lưu nó trong map:

```json
{
  "id": "evt-1",
  "partnerRegion": "south"
}
```

Ở phiên bản sau, ứng dụng quyết định `partnerRegion` là thuộc tính chính thức và thêm field:

```java
private String partnerRegion;
```

Những bản ghi cũ trong database có thể vẫn lưu `partnerRegion` trong JSON mở rộng, trong khi object mới có thêm field tĩnh. Nếu code nạp dữ liệu cũ rồi serialize lại, có nguy cơ xuất hiện hai nguồn dữ liệu cho cùng một khái niệm hoặc giá trị trong map che khuất giá trị tĩnh ở một bước merge.

Khi một extension trở thành field chính thức, cần có kế hoạch chuyển đổi:

1. Chọn nguồn dữ liệu chuẩn khi cả field tĩnh và extension cùng tồn tại.
2. Đọc dữ liệu cũ và chuyển giá trị extension sang field mới.
3. Loại khóa đã nâng cấp khỏi map extension trước khi serialize.
4. Xác định cách xử lý payload chứa cả tên cũ và tên mới.
5. Gắn phiên bản schema hoặc migration version nếu cần.
6. Kiểm thử dữ liệu trước và sau migration, bao gồm bản ghi có giá trị xung đột.

Không nên tự động coi giá trị trong map luôn mới hơn hoặc luôn cũ hơn. Quy tắc ưu tiên phải được xác định theo nguồn dữ liệu và lịch sử hợp đồng.

## 6. Dữ liệu mở rộng làm suy yếu kiểm tra kiểu

Với field tĩnh:

```java
private long quantity;
private BigDecimal amount;
private boolean active;
```

Jackson biết kiểu đích và có thể báo lỗi nếu dữ liệu không chuyển đổi được theo cấu hình. Ứng dụng cũng có thể dùng Bean Validation hoặc logic miền để kiểm tra giá trị.

Với map `Map<String, Object>`, kiểu runtime của giá trị phụ thuộc JSON:

- JSON string thành `String`.
- JSON boolean thành `Boolean`.
- JSON number có thể thành `Integer`, `Long`, `BigInteger` hoặc `Double` tùy giá trị và cấu hình.
- JSON object thành `Map`.
- JSON array thành `List`.
- JSON null thành null Java.

Vì vậy, code như sau không an toàn:

```java
String region = (String) event.getExtensions().get("partnerRegion");
```

Nếu đối tác gửi `partnerRegion: 12`, phép ép kiểu sẽ gây `ClassCastException`. Tương tự, cast một số thành `Double` có thể thất bại nếu Jackson tạo `Integer` hoặc `Long`.

### 6.1. Dùng JsonNode để giữ loại JSON rõ ràng

Nếu extension có thể chứa object/array lồng nhau hoặc cần kiểm tra loại trước khi xử lý, `Map<String, JsonNode>` thường rõ ràng hơn `Map<String, Object>`:

```java
public class PartnerEvent {
    private final Map<String, JsonNode> extensions = new LinkedHashMap<>();

    @JsonAnySetter
    public void addExtension(String name, JsonNode value) {
        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> any() {
        return extensions;
    }
}
```

Khi xử lý:

```java
JsonNode region = event.getExtensions().get("partnerRegion");

if (region != null) {
    if (!region.isTextual()) {
        throw new IllegalArgumentException(
            "partnerRegion must be a string"
        );
    }
    String value = region.textValue();
}
```

`JsonNode` giữ rõ kiểu JSON và cấu trúc lồng nhau. Nó không tự làm dữ liệu hợp lệ, nhưng giúp code kiểm tra trước khi chuyển sang kiểu Java. Với số thập phân cần chính xác, cấu hình `USE_BIG_DECIMAL_FOR_FLOATS` trước khi đọc hoặc dùng schema tĩnh có `BigDecimal`.

### 6.2. Dùng kiểu extension cụ thể nếu schema đã biết

Nếu một số extension được định nghĩa rõ, không nhất thiết phải để chúng ở map tổng quát. Có thể tạo lớp con hoặc DTO chuyên biệt:

```java
public class PartnerAExtensions {
    private String partnerRegion;
    private String campaignCode;
}
```

Khi đó, dữ liệu đã biết có kiểu cụ thể, dễ validate và dễ tài liệu hóa. Map mở chỉ nên dành cho phần thực sự không ổn định hoặc cần giữ lại để forward compatibility.

## 7. Rủi ro validation và dữ liệu không được kiểm soát

Các annotation như `@NotNull`, `@Size`, `@Pattern` thường được đặt trên field hoặc getter tĩnh. Chúng không tự động áp dụng cho mọi entry trong map extension.

Ví dụ:

```java
public class PartnerEvent {
    @NotBlank
    private String id;

    private final Map<String, JsonNode> extensions = new LinkedHashMap<>();
}
```

`id` có thể được validate bằng Bean Validation, nhưng các extension cần logic riêng:

- Giới hạn số lượng key.
- Giới hạn độ dài tên key.
- Chỉ cho phép ký tự hoặc namespace hợp lệ.
- Giới hạn độ sâu object lồng nhau.
- Giới hạn kích thước string, array và object.
- Giới hạn số và miền giá trị nếu ứng dụng sử dụng chúng.
- Kiểm tra những extension mà nghiệp vụ thực sự đọc.

Không nên tin rằng một trường hợp đã được deserialize thành công nghĩa là extension đó hợp lệ. Jackson chỉ chứng minh nó có thể biểu diễn được dưới kiểu map/node; validation hợp đồng vẫn là trách nhiệm của ứng dụng.

## 8. Rủi ro mass assignment khi dùng extension để cập nhật model

Một lỗi nguy hiểm là lấy toàn bộ extension map rồi áp dụng vào entity hoặc cấu hình bằng reflection:

```java
for (Map.Entry<String, Object> entry : extensions.entrySet()) {
    BeanUtils.setProperty(entity, entry.getKey(), entry.getValue());
}
```

Nếu client gửi các khóa như `role`, `isAdmin`, `balance`, `ownerId` hoặc `status`, code có thể vô tình cho phép thay đổi những thuộc tính nhạy cảm. Đây là dạng mass assignment: dữ liệu đầu vào được gán vào quá nhiều thuộc tính mà không có allowlist và kiểm tra quyền phù hợp.

Không dùng extension map như một tập lệnh cập nhật tùy ý. Hãy chọn rõ các key được phép và chuyển thành command có kiểu:

```java
Set<String> allowedExtensions = Set.of(
    "partnerRegion", "campaignCode"
);

for (String key : extensions.keySet()) {
    if (!allowedExtensions.contains(key)) {
        throw new IllegalArgumentException(
            "Unsupported extension: " + key
        );
    }
}
```

Nếu extension được lưu để chuyển tiếp nhưng không được dùng trong nghiệp vụ, hãy giữ chúng tách biệt khỏi entity và command cập nhật. Chỉ đọc các key đã đăng ký qua một adapter chuyên trách.

## 9. Rủi ro rò rỉ dữ liệu khi echo extension ra response

Một ứng dụng có thể nhận payload từ đối tác, lưu extension map rồi serialize lại bằng `@JsonAnyGetter`. Cách này tiện cho forward compatibility, nhưng cũng có nghĩa mọi trường lạ được giữ lại có thể xuất hiện trong response sau đó.

Ví dụ client gửi:

```json
{
  "id": "evt-1",
  "debugToken": "secret-value",
  "internalNote": "do not expose"
}
```

Nếu map được serialize nguyên vẹn, `debugToken` và `internalNote` có thể bị trả cho một client khác hoặc ghi vào log/export. Dữ liệu lạ có thể chứa token, thông tin cá nhân, dữ liệu nội bộ hoặc trường chỉ có ý nghĩa trong phạm vi đối tác ban đầu.

Các biện pháp an toàn:

- Không tự động echo tất cả extension vào response công khai.
- Dùng DTO response riêng hoặc `@JsonAnyGetter` chỉ ở adapter cần forward dữ liệu.
- Dùng allowlist cho extension được phép xuất ra.
- Loại bỏ hoặc che các key nhạy cảm trước khi log.
- Không serialize trực tiếp extension map ra audit/event công khai nếu chưa xác định phân loại dữ liệu.
- Kiểm thử response không chứa key ngoài hợp đồng.

Nếu cần giữ nguyên payload cho mục đích lưu trữ hoặc chuyển tiếp, hãy phân biệt rõ bản payload thô được bảo vệ với DTO response đã lọc.

## 10. Rủi ro khóa JSON trùng lặp

JSON object nên có tên member duy nhất. Payload có hai khóa giống nhau có thể tạo ra khác biệt giữa parser, gateway, validator và service:

```json
{
  "role": "user",
  "role": "admin"
}
```

Một thành phần có thể giữ giá trị cuối, thành phần khác giữ giá trị đầu hoặc báo lỗi. Nếu một gateway kiểm tra giá trị đầu nhưng backend dùng giá trị cuối, có thể xuất hiện lỗi kiểm soát truy cập.

Jackson Core hỗ trợ chế độ phát hiện duplicate field names. Có thể cấu hình factory khi khởi tạo:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

API builder và feature có thể khác theo phiên bản Jackson; hãy dùng API tương ứng với dependency đang có. Với dữ liệu không tin cậy, strict duplicate detection là lựa chọn đáng cân nhắc vì giúp từ chối object có khóa trùng thay vì âm thầm ghi đè.

Kiểm tra duplicate ở đầu vào vẫn chưa đủ. Trước khi serialize, cần bảo đảm extension map không chứa key trùng với property tĩnh. Kiểm tra này đặc biệt quan trọng khi map được tạo hoặc cập nhật từ code Java, database cũ hoặc nhiều nguồn hợp nhất.

## 11. Rủi ro thay đổi schema và forward compatibility

Extension map thường được dùng để tương thích khi producer thêm field mới mà consumer cũ chưa biết. Có hai cách xử lý phổ biến:

| Chính sách | Hành vi với field lạ | Phù hợp khi |
|---|---|---|
| Strict schema | Từ chối field lạ | Hợp đồng đóng, dữ liệu cần kiểm soát chặt |
| Ignore unknown | Bỏ qua field lạ | Consumer chỉ cần phần schema đã biết |
| Capture unknown | Giữ field lạ trong extension map | Gateway, event relay hoặc hệ thống cần forward field mới |

Capture unknown giúp không mất dữ liệu khi producer mở rộng schema, nhưng consumer vẫn phải quyết định có sử dụng, lưu trữ hay phát lại trường đó không. Giữ một field không đồng nghĩa với hiểu ý nghĩa của nó.

Nên cân nhắc:

- Có trường version/schemaVersion trong envelope hay không.
- Extension thuộc namespace của producer nào.
- Một extension có thể trở thành property tĩnh trong tương lai không.
- Hệ thống có migration cho dữ liệu đã lưu không.
- Consumer cũ có được phép phát lại field chưa hiểu không.
- Có cần giữ nguyên kiểu, thứ tự hoặc văn bản gốc hay chỉ giữ cấu trúc JSON.

Nếu cần bảo toàn chính xác văn bản gốc, bao gồm whitespace, cách viết số hoặc thứ tự key, `JsonNode`/Map không đảm bảo giữ nguyên byte đầu vào. Hãy lưu payload gốc riêng nếu yêu cầu kiểm toán hoặc chữ ký số phụ thuộc văn bản nguyên bản.

## 12. Rủi ro về kiểu dữ liệu và độ chính xác số

Với `Map<String, Object>`, một số JSON có thể được ánh xạ thành `Integer`, `Long`, `BigInteger` hoặc `Double` tùy giá trị và cấu hình. Một extension số tiền có thể bị đọc thành `Double`, dẫn đến sai số dấu phẩy động.

Nếu extension có thể chứa số thập phân cần chính xác, hãy dùng `JsonNode` cùng cấu hình `USE_BIG_DECIMAL_FOR_FLOATS`, hoặc chuyển những trường đã biết sang DTO có `BigDecimal`.

Không nên viết code giả định mọi số là `Integer` hoặc `Double`:

```java
Double amount = (Double) extensions.get("amount");
```

Thay vào đó, kiểm tra kiểu thực tế hoặc dùng node API:

```java
JsonNode amountNode = extensions.get("amount");
if (amountNode == null || !amountNode.isNumber()) {
    throw new IllegalArgumentException("amount must be numeric");
}

BigDecimal amount = amountNode.decimalValue();
```

Nếu ứng dụng cần giữ kiểu dữ liệu của extension qua nhiều lần serialize/deserialize, hãy kiểm thử round-trip cho string, boolean, số nguyên lớn, số thập phân, null, array và object lồng nhau. Round-trip cấu trúc không nhất thiết giữ nguyên cách viết văn bản gốc.

## 13. Rủi ro null và giá trị thiếu trong extension map

Một extension có thể không xuất hiện, xuất hiện với null hoặc có giá trị cụ thể:

```json
{}
```

```json
{"partnerRegion": null}
```

```json
{"partnerRegion": "south"}
```

Trong any-setter, nếu property xuất hiện với JSON null, phương thức có thể nhận giá trị null hoặc `NullNode` tùy kiểu tham số và cấu hình. Nếu property không xuất hiện, any-setter không được gọi cho key đó.

Với `Map<String, JsonNode>`, JSON null được biểu diễn bằng `NullNode`, còn key không có trong map trả về null Java khi gọi `get(key)`. Điều này giúp phân biệt:

```java
if (!extensions.containsKey("partnerRegion")) {
    // Không cung cấp.
} else if (extensions.get("partnerRegion").isNull()) {
    // Cung cấp null.
} else {
    // Có giá trị.
}
```

Với `Map<String, Object>`, JSON null thường trở thành null Java, nên `containsKey()` cần thiết để phân biệt key thiếu và key có null. Không chỉ dùng `map.get(key) == null` nếu hai trạng thái có ý nghĩa khác nhau.

## 14. Giới hạn kích thước và chống tiêu thụ tài nguyên

Extension map có thể trở thành một điểm nhận dữ liệu không giới hạn. Một client có thể gửi hàng nghìn key, tên key rất dài, chuỗi lớn, array sâu hoặc object lồng nhau rất nhiều tầng.

Nên giới hạn:

- Tổng kích thước request/body sau giải nén.
- Số lượng extension key tối đa.
- Độ dài tên key.
- Độ sâu object/array lồng nhau.
- Độ dài string và number.
- Kích thước array và object con.
- Các loại node được phép cho từng extension đã biết.
- Thời gian xử lý và số request đồng thời.

Ví dụ kiểm tra giới hạn trong any-setter:

```java
private static final int MAX_EXTENSION_KEYS = 100;
private static final int MAX_KEY_LENGTH = 80;

@JsonAnySetter
public void addExtension(String name, JsonNode value) {
    if (name == null || name.isBlank() || name.length() > MAX_KEY_LENGTH) {
        throw new IllegalArgumentException("Invalid extension key");
    }
    if (!extensions.containsKey(name)
            && extensions.size() >= MAX_EXTENSION_KEYS) {
        throw new IllegalArgumentException("Too many extension properties");
    }
    extensions.put(name, value);
}
```

Giới hạn trong setter chỉ kiểm soát số key sau khi parser đã đọc token và tạo node. Cần kết hợp giới hạn parser như `StreamReadConstraints` và giới hạn request ở tầng HTTP để bảo vệ cả trước khi any-setter được gọi.

## 15. Ví dụ thiết kế extension có kiểm soát

Một DTO có thể giữ field tĩnh, extension node, allowlist và kiểm tra khóa dành riêng:

```java
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

public class PartnerEvent {
    private static final Set<String> RESERVED_KEYS = Set.of(
        "id", "type", "createdAt", "extensions"
    );

    private String id;
    private String type;
    private Instant createdAt;
    private final Map<String, JsonNode> extensions = new LinkedHashMap<>();

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getType() {
        return type;
    }

    public void setType(String type) {
        this.type = type;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    @JsonAnySetter
    public void addExtension(String name, JsonNode value) {
        if (RESERVED_KEYS.contains(name)) {
            throw new IllegalArgumentException(
                "Reserved property cannot be stored as extension: " + name
            );
        }
        if (name.length() > 80) {
            throw new IllegalArgumentException("Extension name is too long");
        }
        if (!name.startsWith("x_")) {
            throw new IllegalArgumentException(
                "Extension properties must use the x_ prefix"
            );
        }
        if (!extensions.containsKey(name) && extensions.size() >= 100) {
            throw new IllegalArgumentException("Too many extension properties");
        }
        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> any() {
        return Collections.unmodifiableMap(extensions);
    }
}
```

Ví dụ này dùng prefix `x_` làm quy ước của hợp đồng minh họa. Prefix thực tế cần được thống nhất với producer và consumer. Trả về unmodifiable view giúp caller không thể thêm/xóa entry qua getter, nhưng `JsonNode` con vẫn có thể mutable trong một số implementation; nếu cần bất biến sâu, hãy copy hoặc chuyển thành cấu trúc immutable phù hợp.

Trong ứng dụng thực tế, không nên chỉ dựa vào exception tổng quát từ any-setter. Hãy chuyển lỗi thành lỗi validation/API phù hợp, kèm tên field nhưng không đưa giá trị nhạy cảm vào message/log.

## 16. Chọn Map<String, Object> hay Map<String, JsonNode>?

| Tiêu chí | `Map<String, Object>` | `Map<String, JsonNode>` |
|---|---|---|
| Dễ sử dụng với Java code | Thuận tiện cho scalar sau khi kiểm tra kiểu | Cần gọi API node để lấy giá trị |
| Giữ rõ loại JSON | Kiểu Java tự nhiên thay đổi theo giá trị/cấu hình | Có `isTextual()`, `isNumber()`, `isArray()`… |
| Object/array lồng nhau | Thường thành Map/List lồng nhau | Thành cây `JsonNode` |
| Phân biệt JSON null | Thường là null Java; cần `containsKey()` | Có `NullNode` riêng |
| Kiểm tra kiểu | `instanceof` và kiểm tra Number cụ thể | Các phương thức `isXxx()` |
| Độ chính xác số | Phụ thuộc untyped mapping và feature | Có thể cấu hình BigDecimal khi đọc tree |
| Phù hợp | Extension đơn giản, code xử lý Java đã biết các kiểu | Payload động, cần giữ cấu trúc và kiểm tra loại tường minh |

Không có một kiểu map đúng cho mọi hệ thống. Nếu extension chỉ là vài scalar đã được kiểm soát, `Object` có thể đơn giản. Nếu cần giữ payload lạ, xử lý lồng nhau hoặc kiểm tra trước khi chuyển đổi, `JsonNode` thường an toàn và rõ ràng hơn.

## 17. Khi nào không nên dùng @JsonAnySetter/@JsonAnyGetter?

Không nên dùng mô hình mở nếu:

- Hợp đồng yêu cầu schema đóng và mọi field lạ phải bị từ chối.
- Dữ liệu có ảnh hưởng đến quyền, tiền, trạng thái hoặc các quy tắc quan trọng mà không có schema/validation cho từng key.
- Consumer không cần giữ hoặc chuyển tiếp field lạ.
- Dữ liệu mở rộng có thể chứa secret hoặc thông tin không được phép phát ra ngoài.
- Các field có cấu trúc đã ổn định và nên được mô hình hóa thành property tĩnh hoặc DTO riêng.
- Không có giới hạn số lượng key, độ sâu và kích thước payload.

Trong các trường hợp đó, strict deserialization, DTO riêng hoặc property `extensions` lồng nhau có schema cụ thể thường phù hợp hơn.

## 18. Kiểm thử hành vi tĩnh và mở

Nên kiểm thử ít nhất các trường hợp:

- Field tĩnh được ánh xạ đúng.
- Field không biết được lưu vào extension.
- Extension được ghi lại bằng `@JsonAnyGetter` theo đúng hình thức hợp đồng.
- Key reserved hoặc không đúng namespace bị từ chối.
- Key trùng với property tĩnh không thể xuất hiện trong output.
- JSON null, scalar, array và object lồng nhau được xử lý đúng.
- Số nguyên lớn và số thập phân được giữ theo chính sách.
- Quá số lượng key hoặc vượt giới hạn tên key bị từ chối.
- Extension nhạy cảm không xuất hiện trong response công khai hoặc log.
- Payload có duplicate field name bị xử lý theo chính sách đã chọn.

Ví dụ kiểm thử round-trip cơ bản:

```java
class PartnerEventTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void capturesAndWritesUnknownProperties() throws Exception {
        String json = """
            {
              "id": "evt-1",
              "type": "order.created",
              "x_region": "south",
              "x_retry": 2
            }
            """;

        PartnerEvent event = mapper.readValue(json, PartnerEvent.class);

        assertEquals("evt-1", event.getId());
        assertTrue(event.getExtensions().containsKey("x_region"));

        JsonNode output = mapper.readTree(mapper.writeValueAsString(event));
        assertEquals("south", output.path("x_region").asText());
        assertEquals(2, output.path("x_retry").asInt());
    }
}
```

Ví dụ trên giả định `PartnerEvent` dùng `Map<String, JsonNode>` và đã cấu hình các field cần thiết. Nếu class yêu cầu `JavaTimeModule` cho `Instant`, đăng ký module trong mapper test giống cấu hình production.

Không chỉ kiểm tra round-trip. Hãy test riêng các điều kiện từ chối, collision và output allowlist; một round-trip thành công không chứng minh dữ liệu mở rộng an toàn.

## 19. Quy trình thiết kế dữ liệu mở rộng

Khi một DTO cần vừa có field tĩnh vừa nhận dữ liệu động, hãy xác định rõ:

1. Field nào thuộc schema chính thức và phải có kiểu Java cụ thể.
2. Field nào được phép mở rộng, ai là producer sở hữu namespace đó.
3. Extension được flatten bằng `@JsonAnyGetter` hay nằm trong object `extensions` riêng.
4. Danh sách khóa tĩnh/reserved và quy tắc xử lý tên trùng.
5. Kiểu map là `Object`, `JsonNode` hay một extension DTO có kiểu cụ thể.
6. Giới hạn số key, độ dài tên, kích thước và độ sâu dữ liệu.
7. Quy tắc validation cho các extension mà nghiệp vụ thực sự sử dụng.
8. Chính sách mass assignment: extension không được tự động gán vào entity hoặc command.
9. Chính sách xuất dữ liệu: extension nào được phép xuất ra response, log hoặc event tiếp theo.
10. Cách nâng cấp extension thành field tĩnh khi schema thay đổi.
11. Cách xử lý duplicate key, null và kiểu số chính xác.
12. Kiểm thử deserialize, serialize, collision, dữ liệu biên và bảo vệ dữ liệu.

## 20. Bảng ghi nhớ

| Nhu cầu | Cách làm |
|---|---|
| Thu nhận property JSON chưa khai báo | `@JsonAnySetter` |
| Ghi map thành các property cùng cấp | `@JsonAnyGetter` |
| Giữ extension trong object con | Property `Map` bình thường, không flatten bằng any-getter |
| Kiểm tra kiểu và cấu trúc động | `Map<String, JsonNode>` |
| Xử lý extension đơn giản với kiểu Java tự nhiên | `Map<String, Object>` và kiểm tra `instanceof` |
| Tránh trùng với field tĩnh | Reserved key, namespace/prefix và kiểm tra trước serialize |
| Phát hiện duplicate key đầu vào | Strict duplicate detection trên `JsonFactory` |
| Tránh mass assignment | Allowlist và chuyển thành command có kiểu |
| Tránh rò rỉ extension | DTO response riêng và allowlist output |
| Hỗ trợ schema evolution | Versioning, migration và quy tắc nâng extension thành field tĩnh |
| Chống payload mở quá lớn | Giới hạn body, số key, độ sâu, độ dài và concurrency |

## 21. Kết luận

`@JsonAnySetter` và `@JsonAnyGetter` cho phép một DTO kết hợp các thuộc tính tĩnh với dữ liệu mở rộng. Chúng hữu ích cho event, webhook, gateway và tích hợp cần forward field mới mà consumer cũ chưa hiểu. Nhưng một map mở cũng làm yếu ranh giới schema: key có thể va chạm với field tĩnh, dữ liệu có thể không được validate, kiểu runtime có thể thay đổi và extension có thể bị phát lại ngoài ý muốn.

Hãy giữ field nghiệp vụ quan trọng trong DTO có kiểu rõ ràng; đặt extension trong namespace hoặc object riêng; kiểm tra khóa reserved và duplicate; giới hạn kích thước; validate mọi extension được sử dụng; không mass-assign map vào entity; và chỉ xuất những extension được phép. Khi một extension trở thành field chính thức, cần migration và quy tắc ưu tiên dữ liệu rõ ràng. Mô hình mở chỉ an toàn khi phạm vi mở rộng, quyền sở hữu key và vòng đời schema được quản lý có chủ đích.
