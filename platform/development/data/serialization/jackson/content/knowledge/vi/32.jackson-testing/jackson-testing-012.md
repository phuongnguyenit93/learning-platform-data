# Kiểm thử tương thích với dữ liệu của phiên bản trước

Dữ liệu JSON thường sống lâu hơn phiên bản code đã tạo ra nó. Một payload có thể được lưu trong database nhiều năm, nằm trong object storage, được giữ trong dead-letter queue hoặc chờ consumer xử lý sau một đợt deploy. Khi class Java, cấu hình Jackson hay schema thay đổi, ứng dụng mới vẫn phải hiểu đúng dữ liệu cũ theo chính sách đã công bố.

**Kiểm thử tương thích với dữ liệu của phiên bản trước** xác nhận rằng code hiện tại vẫn đọc và diễn giải đúng payload do phiên bản trước tạo ra. Kiểm thử cũng cần xác định chiều ngược lại: consumer cũ có đọc được payload mới hay không, và hai phiên bản có thể cùng tồn tại trong giai đoạn rolling deployment hay không.

Không thể chứng minh tương thích chỉ bằng cách serialize rồi deserialize bằng cùng một ObjectMapper. Một writer và reader cùng thay đổi theo một cách vẫn có thể round-trip thành công trong khi dữ liệu cũ bị đọc sai hoặc consumer khác không còn hiểu được payload. Cần giữ fixture độc lập, xác định các thay đổi schema và kiểm thử các cặp producer/consumer thực tế.

## 1. Tương thích dữ liệu là gì?

Giả sử phiên bản đầu tiên ghi một sự kiện:

```json
{
  "eventId": "evt-1042",
  "customerName": "Nguyen An",
  "createdAt": "2025-06-10T08:30:00Z"
}
```

Phiên bản sau đổi model Java:

- customerName được đổi thành displayName.
- createdAt được chuyển sang một value object.
- Thêm sourceSystem.
- Enum trạng thái có thêm giá trị mới.
- Cấu hình ngày giờ hoặc naming strategy được thay đổi.

Ứng dụng mới cần đọc payload cũ và chuyển nó thành trạng thái nghiệp vụ đúng. Việc đổi tên field trong Java không nên làm mất tên JSON cũ nếu hợp đồng cần duy trì.

Tương thích dữ liệu có nhiều chiều:

| Chiều kiểm tra | Câu hỏi |
| --- | --- |
| Backward compatibility | Reader mới có đọc đúng dữ liệu do writer cũ tạo ra không? |
| Forward compatibility | Reader cũ có xử lý được dữ liệu do writer mới tạo ra không? |
| Same-version compatibility | Writer và reader của cùng phiên bản có trao đổi đúng không? |
| Rolling-deployment compatibility | Các phiên bản cũ và mới có thể cùng chạy trong thời gian deploy không? |
| Persistence compatibility | Code mới có đọc được JSON đã lưu từ các release trước không? |
| Replay compatibility | Consumer mới có xử lý được event cũ đang nằm trong queue hoặc log không? |

Trong nhiều hệ thống, backward compatibility là yêu cầu bắt buộc vì dữ liệu cũ không thể được tạo lại. Forward compatibility thường quan trọng khi deploy rolling hoặc khi producer và consumer được nâng cấp độc lập.

## 2. Phân biệt phiên bản schema với phiên bản Jackson

Có hai loại phiên bản khác nhau:

- **Phiên bản thư viện Jackson**: ví dụ Core, Databind, Annotations và module datatype.
- **Phiên bản schema dữ liệu**: cấu trúc và ý nghĩa của JSON được producer/consumer trao đổi.

Nâng Jackson từ một minor release sang minor release khác không đồng nghĩa schema đã thay đổi. Ngược lại, schema có thể thay đổi dù phiên bản Jackson giữ nguyên.

Một compatibility test cần biết đang kiểm tra điều gì:

1. Code mới đọc payload cũ do schema cũ tạo ra.
2. Cùng schema nhưng thư viện Jackson mới đọc/ghi khác đi.
3. Schema mới được phát hành và cần hỗ trợ nhiều phiên bản payload.
4. Consumer cũ và producer mới phải cùng hoạt động trong rolling deployment.

Hãy ghi cả schema version và Jackson dependency version trong test report. Không dùng version thư viện làm thay thế cho version dữ liệu.

## 3. Xác định hợp đồng trước khi viết test

Trước khi tạo fixture, ghi rõ các quy tắc của payload:

- Tên property chính thức.
- Kiểu JSON của mỗi property.
- Property bắt buộc hay tùy chọn.
- Missing, null, empty và default có ý nghĩa gì.
- Định dạng ngày giờ và timezone.
- Precision/scale của số.
- Mã enum công khai.
- Quy tắc với property chưa biết.
- Cách biểu diễn object lồng nhau, collection và Map.
- Discriminator cho dữ liệu đa hình.
- Quy tắc versioning và migration.

Ví dụ hợp đồng version 1:

| Property | Kiểu | Quy tắc |
| --- | --- | --- |
| eventId | string | Bắt buộc, định danh ổn định |
| customerName | string | Bắt buộc |
| createdAt | string | ISO-8601 UTC |
| status | string | Mã enum đã công bố |

Nếu không có hợp đồng rõ ràng, test chỉ có thể xác nhận rằng Jackson đang làm một việc nào đó; nó không thể xác nhận việc đó có đúng với ý nghĩa mà producer và consumer đã thống nhất hay không.

## 4. Lưu fixture của các phiên bản trước

Fixture là payload mẫu được lưu cùng source code và được dùng lại trong test. Fixture cũ nên được giữ như dữ liệu lịch sử, kể cả khi class Java tương ứng đã bị xóa hoặc đổi tên.

Một cách tổ chức:

```text
src/test/resources/compatibility/
  customer-event/
    v1/
      minimal.json
      complete.json
      nullable-fields.json
      unknown-status.json
    v2/
      minimal.json
      complete.json
```

Mỗi fixture nên có nguồn gốc rõ:

- Schema version.
- Release hoặc commit đã tạo payload.
- Producer nào đã phát payload.
- Trường hợp nghiệp vụ được đại diện.
- Ý nghĩa expected sau deserialize.
- Có phải fixture đã được ẩn danh hay không.

Nên giữ một số payload lấy từ production đã được làm sạch dữ liệu nhạy cảm, cùng với fixture tổng hợp cho các trường hợp biên. Không lưu token, thông tin cá nhân hoặc bí mật production nguyên bản trong repository chỉ để tiện kiểm thử.

**Không tạo toàn bộ fixture cũ bằng mapper mới rồi gọi chúng là dữ liệu cũ.** Cách đó chỉ kiểm tra writer hiện tại. Fixture lịch sử nên đến từ artifact của release cũ, contract sample đã được xác nhận hoặc producer độc lập.

## 5. Test reader mới với payload cũ

Đây là kiểm thử backward compatibility quan trọng nhất: giữ payload cũ cố định, đọc bằng code mới và xác nhận ý nghĩa.

Ví dụ fixture version 1:

```json
{
  "eventId": "evt-1042",
  "customerName": "Nguyen An",
  "createdAt": "2025-06-10T08:30:00Z"
}
```

Model hiện tại:

```java
public record CustomerEvent(
    String eventId,
    String displayName,
    Instant createdAt,
    String sourceSystem
) {}
```

Nếu chỉ đổi tên component Java, mapper không tự biết customerName là tên cũ của displayName. Cần khai báo alias hoặc viết migration mapping.

Một lựa chọn là @JsonAlias:

```java
public record CustomerEvent(
    String eventId,

    @JsonProperty("displayName")
    @JsonAlias("customerName")
    String displayName,

    Instant createdAt,
    String sourceSystem
) {}
```

@JsonAlias giúp deserialize chấp nhận tên cũ. Khi serialize, tên chính thức theo property mapping vẫn là tên hiện tại. Đây là điểm quan trọng: alias là cơ chế đọc tên cũ, không phải yêu cầu writer tiếp tục phát cả hai tên.

Test:

```java
@Test
void readsVersionOneCustomerEvent() throws Exception {
    CustomerEvent event = mapper.readValue(
        resource("compatibility/customer-event/v1/complete.json"),
        CustomerEvent.class
    );

    assertEquals("evt-1042", event.eventId());
    assertEquals("Nguyen An", event.displayName());
    assertEquals(
        Instant.parse("2025-06-10T08:30:00Z"),
        event.createdAt()
    );
}
```

Nếu sourceSystem chưa tồn tại trong version 1, cần xác định giá trị mặc định có ý nghĩa. Không nên chỉ để null vì test pass; hãy xác định ứng dụng coi dữ liệu cũ đến từ nguồn nào hoặc field đó có thực sự optional hay không.

## 6. Missing property, null và default cần được kiểm tra riêng

Khi thêm property mới, dữ liệu cũ sẽ không chứa property đó. Hành vi khi deserialize phụ thuộc kiểu Java, constructor, record creator, initializer và cấu hình Jackson.

Ví dụ version mới có:

```java
public class CustomerEvent {
    private String eventId;
    private String sourceSystem = "legacy";

    // Getters and setters
}
```

Nếu JSON cũ không có sourceSystem, initializer có thể giữ giá trị mặc định với bean mutable khi setter không được gọi. Nhưng với constructor/record creator, cách xử lý có thể khác. Đừng suy rộng một kết quả test từ mutable bean sang mọi kiểu Java.

Cần phân biệt:

| Input | Ý nghĩa cần quyết định |
| --- | --- |
| Không có property | Giữ default, dùng fallback hoặc báo lỗi |
| "sourceSystem": null | Null hợp lệ, xóa giá trị hay từ chối |
| "sourceSystem": "" | Chuỗi rỗng có hợp lệ không |
| "sourceSystem": "legacy" | Giá trị cụ thể |
| Property có kiểu sai | Coercion hay lỗi |

Có thể dùng @JsonSetter(nulls = Nulls.SKIP) nếu explicit null cần bỏ qua khi bind vào bean, hoặc dùng validation/migration logic rõ ràng. @JsonInclude điều khiển output; nó không định nghĩa cách đọc payload cũ.

Với record hoặc immutable DTO, nếu cần default cho component bị thiếu, hãy triển khai creator/default mapping có chủ đích và test trên phiên bản Jackson đang dùng. Không mặc định rằng giá trị khởi tạo trong field sẽ được dùng trong mọi constructor binding path.

## 7. Property mới và unknown-property policy

Giả sử writer mới thêm:

```json
{
  "eventId": "evt-1042",
  "displayName": "Nguyen An",
  "sourceSystem": "mobile-app"
}
```

Reader cũ không biết sourceSystem. Nếu reader bật FAIL_ON_UNKNOWN_PROPERTIES, nó có thể từ chối payload mới. Nếu reader bỏ qua unknown property, nó có thể tiếp tục xử lý các field đã biết.

Có thể cấu hình lenient cho DTO:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public class CustomerEventV1 {
    private String eventId;
    private String displayName;

    // Getters and setters
}
```

Hoặc cấu hình reader cụ thể:

```java
ObjectReader legacyReader = mapper
    .readerFor(CustomerEventV1.class)
    .without(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
```

Đừng tắt strictness toàn cục mà không hiểu tác động. Với request API, strict unknown-property handling có thể phát hiện client gửi sai tên field. Với consumer event, bỏ qua field mới có thể cần thiết để hỗ trợ forward compatibility.

Nếu consumer cần forward payload và không được phép mất field mở rộng, ignoreUnknown không đủ vì field bị bỏ đi. Dùng @JsonAnySetter để giữ extension trong Map hoặc giữ tree node theo hợp đồng.

Ví dụ:

```java
public class ExtensibleEvent {

    private String eventId;

    private final Map<String, JsonNode> extensions =
        new LinkedHashMap<>();

    @JsonAnySetter
    public void addExtension(String name, JsonNode value) {
        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> extensions() {
        return extensions;
    }
}
```

Extension field chỉ nên được forward nếu ứng dụng có chủ đích bảo toàn chúng. Không đưa unknown property vào domain logic một cách vô điều kiện.

## 8. Enum mới có thể làm reader cũ thất bại

Giả sử version 1 có:

```java
public enum PaymentStatus {
    PENDING,
    PAID,
    FAILED
}
```

Version mới thêm REFUNDED. Reader cũ deserialize "REFUNDED" có thể ném lỗi vì không có enum constant tương ứng.

Có thể chọn một trong hai chính sách:

- Từ chối giá trị chưa biết để tránh xử lý sai nghiệp vụ.
- Ánh xạ giá trị chưa biết sang một trạng thái fallback rõ ràng như UNKNOWN.

Jackson hỗ trợ @JsonEnumDefaultValue cùng READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE:

```java
public enum PaymentStatus {
    PENDING,
    PAID,
    FAILED,

    @JsonEnumDefaultValue
    UNKNOWN
}
```

Cấu hình reader:

```java
ObjectMapper mapper = JsonMapper.builder()
    .enable(
        DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE
    )
    .build();
```

Test cả giá trị đã biết và giá trị chưa biết. Nếu chọn fallback, downstream phải xử lý UNKNOWN an toàn. Không tự động coi trạng thái lạ là PAID, SUCCESS hoặc một trạng thái có quyền thực hiện side effect.

Một lựa chọn khác là READ_UNKNOWN_ENUM_VALUES_AS_NULL, nhưng null có thể bị hiểu nhầm là field không có dữ liệu. Hãy chọn một policy và ghi rõ trong contract.

## 9. Đổi tên field mà vẫn đọc được dữ liệu cũ

Đổi tên JSON property là thay đổi có nguy cơ phá vỡ tương thích.

Có thể dùng @JsonAlias để nhận cả tên cũ và tên mới:

```java
public class CustomerEvent {

    @JsonProperty("display_name")
    @JsonAlias({"customer_name", "name"})
    private String displayName;

    // Getters and setters
}
```

Ví dụ:

- Writer hiện tại ghi display_name.
- Reader hiện tại chấp nhận display_name.
- Reader hiện tại cũng chấp nhận customer_name và name từ payload cũ.

Alias nên được giữ trong thời gian cần hỗ trợ dữ liệu lịch sử. Nếu một payload gửi đồng thời nhiều alias cho cùng property, cần xác định quy tắc và test trường hợp xung đột; không để thứ tự property trong JSON vô tình quyết định nghiệp vụ.

Nếu cần thay đổi phức tạp hơn một alias, dùng DTO theo version và migration mapper thay vì dồn nhiều tên cũ vào một class.

## 10. Đổi kiểu dữ liệu là thay đổi có rủi ro cao

Ví dụ field cũ là string:

```json
{
  "customerId": "0001042"
}
```

phiên bản mới muốn dùng số:

```json
{
  "customerId": 1042
}
```

Hai dạng không hoàn toàn tương đương. Số 0 ở đầu có thể mất; consumer có thể thực hiện phép toán trên ID; range của number có thể khác giữa ngôn ngữ.

Tương tự:

- int đổi thành long có thể mở rộng range ở Java nhưng consumer cũ vẫn có thể overflow.
- double đổi thành BigDecimal có thể thay đổi precision/scale semantics.
- Epoch milliseconds đổi thành ISO-8601 string là thay đổi wire type.
- Một scalar đổi thành object lồng nhau là thay đổi cấu trúc.

Nếu cần hỗ trợ cả hai dạng, có thể dùng custom deserializer hoặc DTO version riêng. Hãy test dữ liệu lịch sử, giá trị biên và dữ liệu sai kiểu. Đừng dựa vào coercion mặc định để làm migration vì coercion có thể thay đổi giữa cấu hình hoặc phiên bản Jackson.

Với ID, mã vùng, mã tài khoản hoặc mã có số 0 đầu, string thường phản ánh đúng bản chất định danh hơn number.

## 11. Ngày giờ và số thập phân cần fixture lịch sử

Cùng một Instant có thể được ghi thành chuỗi ISO-8601 hoặc timestamp số tùy cấu hình. Nếu phiên bản cũ ghi timestamp, phiên bản mới cần biết đơn vị là giây hay mili giây.

Ví dụ hai payload:

```json
{
  "createdAt": "2025-06-10T08:30:00Z"
}
```

```json
{
  "createdAt": 1749544200000
}
```

Một số nguyên timestamp không tự nói rõ đơn vị. Nếu hợp đồng cũ dùng milliseconds, hãy ghi rõ và test đúng instant sau khi đọc.

Với BigDecimal, cần xác định scale có thuộc nghiệp vụ không:

```java
BigDecimal expected = new BigDecimal("19.9500");
```

compareTo so sánh giá trị số, còn equals so sánh cả scale. Test phải theo đúng hợp đồng: tiền có thể cần giữ scale cố định, trong khi một phép đo chỉ quan tâm giá trị.

Lưu fixture cho:

- Timestamp có Z.
- Timestamp có offset khác UTC.
- Timestamp có/không có phần mili giây.
- Giá trị decimal có scale khác nhau.
- Số âm, zero, giá trị lớn và giá trị sát giới hạn.

## 12. Polymorphic type id cần ổn định qua phiên bản

Nếu payload dùng @JsonTypeInfo, type id là một phần của hợp đồng. Không nên dùng tên class Java hoặc package làm type id công khai vì refactor class có thể làm payload cũ không đọc được.

Ví dụ:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(
        value = CustomerCreated.class,
        name = "customer.created"
    ),
    @JsonSubTypes.Type(
        value = CustomerUpdated.class,
        name = "customer.updated"
    )
})
public interface CustomerEvent {
}
```

Các type id customer.created và customer.updated được giữ ổn định dù tên class thay đổi.

Khi thêm subtype mới, reader cũ có thể từ chối type id chưa biết. Chính sách cần được xác định:

- Từ chối và đưa message vào dead-letter queue.
- Lưu raw payload để xử lý sau khi nâng cấp.
- Dùng envelope chung để giữ event type và payload như JsonNode.
- Bỏ qua subtype mới chỉ khi việc bỏ qua an toàn về nghiệp vụ.

Không bật default typing rộng cho dữ liệu không đáng tin cậy. Type metadata là một phần của contract và cần allowlist subtype rõ ràng.

## 13. Dùng DTO theo version khi migration phức tạp

Khi schema thay đổi nhiều, một class DTO duy nhất với nhiều alias, custom setter và default có thể khó hiểu. Dùng DTO version riêng thường dễ kiểm soát hơn.

Ví dụ:

```java
public record CustomerEventV1(
    String eventId,
    String customerName,
    String createdAt
) {}

public record CustomerEventV2(
    String eventId,
    String displayName,
    Instant createdAt,
    String sourceSystem
) {}
```

Đọc payload cũ vào DTO V1, sau đó chuyển sang model hiện tại:

```java
CustomerEventV1 oldEvent =
    mapper.readValue(oldJson, CustomerEventV1.class);

Customer current = new Customer(
    oldEvent.eventId(),
    oldEvent.customerName(),
    Instant.parse(oldEvent.createdAt()),
    "legacy"
);
```

Cách này làm rõ ranh giới:

1. DTO V1 mô tả chính xác schema cũ.
2. DTO V2 mô tả schema mới.
3. Mapper/migration function định nghĩa cách chuyển dữ liệu.
4. Domain model chỉ nhận trạng thái đã được chuẩn hóa.

Khi có nhiều schema cũ, có thể giữ một reader và migration function cho từng version. Không cần để domain model hiện tại hiểu mọi biến thể lịch sử.

## 14. Thêm schemaVersion vào envelope

Nếu hệ thống cần hỗ trợ nhiều phiên bản lâu dài, đặt version trong envelope:

```json
{
  "schemaVersion": 2,
  "eventType": "customer.updated",
  "payload": {
    "eventId": "evt-1042",
    "displayName": "Nguyen An",
    "sourceSystem": "mobile-app"
  }
}
```

Reader có thể kiểm tra version rồi chọn DTO:

```java
JsonNode root = mapper.readTree(input);

JsonNode versionNode = root.get("schemaVersion");
int version = versionNode == null ? 1 : versionNode.intValue();

return switch (version) {
    case 1 -> migrateV1(root);
    case 2 -> readV2(root);
    default -> throw new UnsupportedSchemaVersionException(version);
};
```

Đoạn code trên minh họa luồng chọn version; code thực tế cần kiểm tra schemaVersion tồn tại đúng kiểu integer và không nhận giá trị sai định dạng. Không nên để intValue() âm thầm biến một node không phải integer thành một giá trị có vẻ hợp lệ.

Nếu dữ liệu cũ không có version, có thể định nghĩa rõ rằng thiếu version nghĩa là V1. Chỉ làm vậy khi lịch sử producer bảo đảm payload cũ thuộc một schema xác định.

Không suy luận version từ tên class hoặc Jackson version. Schema version là metadata của message.

## 15. Migration nên tách khỏi deserialize thông thường

Khi đổi cấu trúc dữ liệu, có hai chiến lược phổ biến:

**Migration lúc đọc (read-time migration)**

- Giữ payload cũ nguyên trạng.
- Reader nhận diện version.
- Chuyển DTO cũ thành domain model mới trong lúc đọc.
- Có thể migrate dữ liệu dần khi record được truy cập.

**Migration dữ liệu lưu trữ (bulk migration)**

- Chạy job đọc payload cũ.
- Chuyển sang schema mới.
- Validate kết quả.
- Ghi phiên bản mới và theo dõi số record thành công/thất bại.

Không nên thực hiện migration ghi đè ngay trong một lần đọc mà không có chính sách backup, rollback và idempotency. Nếu payload lưu trong database là nguồn audit, có thể cần giữ bản gốc và lưu bản normalized riêng.

Một migration function nên có tính xác định: cùng payload/version cho cùng kết quả. Nếu có gọi service ngoài, tra cứu trạng thái hiện tại hoặc phụ thuộc thời gian hệ thống, cần tách phần đó ra khỏi bước chuyển schema thuần dữ liệu.

## 16. Kiểm thử migration function

Ví dụ test chuyển V1 sang domain hiện tại:

```java
@Test
void migratesV1CustomerEventToCurrentModel() throws Exception {
    CustomerEventV1 v1 = mapper.readValue(
        resource("compatibility/customer-event/v1/complete.json"),
        CustomerEventV1.class
    );

    Customer current = migration.fromV1(v1);

    assertEquals("evt-1042", current.eventId());
    assertEquals("Nguyen An", current.displayName());
    assertEquals(
        Instant.parse("2025-06-10T08:30:00Z"),
        current.createdAt()
    );
    assertEquals("legacy", current.sourceSystem());
}
```

Nên test:

- Payload tối thiểu.
- Payload đầy đủ.
- Field thiếu.
- Null tường minh.
- Giá trị biên.
- Enum không biết.
- Field cũ bị đổi tên.
- Payload lỗi phải bị từ chối.
- Migration lặp lại nếu workflow có thể retry.

Migration từ V1 sang domain hiện tại cần có expected value độc lập, không chỉ serialize kết quả ra V2 rồi đọc lại bằng cùng mapper.

## 17. Kiểm thử backward và forward compatibility theo ma trận

Một ma trận đơn giản giúp xác định cặp producer/consumer cần hỗ trợ:

| Writer | Reader | Mục tiêu |
| --- | --- | --- |
| V1 | V1 | Hành vi gốc |
| V1 | V2 | Reader mới đọc dữ liệu cũ |
| V2 | V2 | Hành vi hiện tại |
| V2 | V1 | Reader cũ xử lý dữ liệu mới |
| V1 | Current migration | Migration dữ liệu lịch sử |
| V2 | Previous migration | Chỉ cần nếu hệ thống hỗ trợ replay ngược hoặc rollback |

Không phải mọi hệ thống đều phải hỗ trợ V2 writer với V1 reader. Nhưng trong rolling deployment, trường hợp đó có thể xảy ra nếu producer được nâng trước consumer.

Ví dụ trình tự triển khai an toàn có thể là:

1. Deploy reader mới có thể đọc cả V1 và V2.
2. Chờ toàn bộ consumer được nâng cấp.
3. Bắt đầu phát payload V2.
4. Theo dõi consumer lỗi và dead-letter queue.
5. Chỉ ngừng hỗ trợ V1 sau khi dữ liệu cũ đã hết vòng đời hoặc được migrate.

Đây là chiến lược expand-and-contract: mở rộng khả năng đọc trước, sau đó mới thay đổi writer và cuối cùng loại bỏ đường cũ.

## 18. Kiểm thử bằng JUnit và fixture resources

Một test đọc fixture từ resources:

```java
class CustomerEventCompatibilityTest {

    private final ObjectMapper mapper = createCurrentMapper();

    @Test
    void currentReaderSupportsV1Fixture() throws Exception {
        try (InputStream input = getClass()
                .getResourceAsStream(
                    "/compatibility/customer-event/v1/complete.json"
                )) {
            assertNotNull(input);

            CustomerEventV1 oldEvent =
                mapper.readValue(input, CustomerEventV1.class);

            assertEquals("evt-1042", oldEvent.eventId());
            assertEquals("Nguyen An", oldEvent.customerName());
        }
    }
}
```

Test migration và test contract output nên tách riêng. Một test có thể đọc V1 vào DTO V1; test khác xác nhận migration; test thứ ba xác nhận writer hiện tại phát schema V2 đúng tên và kiểu.

Không nên để fixture bị cập nhật tự động mỗi khi test thất bại. Thay đổi golden file cần được review như một thay đổi hợp đồng.

## 19. Golden file test và snapshot test

Golden file là output JSON/XML được lưu làm chuẩn so sánh. Chúng hữu ích để phát hiện thay đổi ngoài ý muốn về tên field, null inclusion, date format, enum code hoặc nested structure.

Ví dụ:

```java
String actual = mapper
    .writerWithDefaultPrettyPrinter()
    .writeValueAsString(event);

String expected = Files.readString(
    Path.of("src/test/resources/contracts/customer-event-v2.json")
);

JsonNode actualTree = mapper.readTree(actual);
JsonNode expectedTree = mapper.readTree(expected);

assertEquals(expectedTree, actualTree);
```

So sánh tree giúp bỏ qua khác biệt whitespace và thứ tự property object. Nếu thứ tự array có ý nghĩa, JsonNode comparison vẫn giữ thứ tự array.

Golden file không tự chứng minh output đúng nghiệp vụ. Nếu fixture được cập nhật theo output sai, test sẽ khóa lỗi. Hãy review diff và đối chiếu với contract/schema.

Nếu byte-level representation là hợp đồng, ví dụ chữ ký số hoặc hash trên canonical JSON, cần test bytes riêng với quy tắc canonicalization rõ ràng.

## 20. Test unknown property và strictness có chủ đích

Nên có hai nhóm test:

- Reader lenient: payload có field mới vẫn được đọc nếu contract cho phép.
- Reader strict: payload có field sai hoặc không được hỗ trợ bị từ chối.

Ví dụ:

```java
@Test
void strictReaderRejectsUnknownProperty() {
    ObjectReader strictReader = mapper
        .readerFor(CustomerEventV2.class)
        .with(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

    assertThrows(
        UnrecognizedPropertyException.class,
        () -> strictReader.readValue("""
            {
              "eventId": "evt-1042",
              "unexpected": true
            }
            """)
    );
}
```

Với DTO được đánh dấu @JsonIgnoreProperties(ignoreUnknown = true), annotation có thể làm reader bỏ qua field lạ dù mapper bật strictness. Hãy kiểm tra chính sách cuối cùng trên kiểu DTO thực tế.

Strictness của request API và consumer event có thể khác nhau. Đừng dùng cùng một mapper configuration cho mọi boundary nếu chúng có hợp đồng khác nhau.

## 21. Test enum và subtype chưa biết

Với enum fallback, test giá trị mới:

```java
@Test
void mapsUnknownStatusToUnknownWhenConfigured() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
        .enable(
            DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE
        )
        .build();

    PaymentStatus status = mapper.readValue(
        "\"REFUNDED\"",
        PaymentStatus.class
    );

    assertEquals(PaymentStatus.UNKNOWN, status);
}
```

Với polymorphic event type chưa biết, cần xác định ứng dụng sẽ từ chối, giữ raw payload hay đưa vào dead-letter queue. Không tự động bỏ qua event quan trọng chỉ vì type id mới xuất hiện.

Nếu cần lưu event chưa biết:

```java
public record RawEventEnvelope(
    String eventType,
    int schemaVersion,
    JsonNode payload
) {}
```

Envelope giữ payload dưới dạng tree để ứng dụng có thể lưu lại và xử lý sau. Tuy nhiên, cần validate giới hạn kích thước/depth và bảo vệ dữ liệu nhạy cảm trước khi lưu.

## 22. Compatibility test cho database và message replay

JSON lưu trong database thường có vòng đời dài hơn deployment. Ví dụ cột payload chứa event V1 được tạo từ nhiều năm trước. Code mới cần đọc chúng khi query, export hoặc rebuild projection.

Cần kiểm thử:

- Record cũ đọc được sau khi nâng ứng dụng.
- Job rebuild projection xử lý được toàn bộ schema version còn lưu.
- Query/filter không phụ thuộc field đã bị đổi tên.
- Migration job không bỏ sót record có null hoặc cấu trúc cũ.
- Rollback ứng dụng có thể đọc dữ liệu đã được writer mới ghi hay không.
- Event replay từ broker/log không làm side effect lặp ngoài ý muốn.

Đối với event sourcing, payload lịch sử thường là một phần của audit trail. Không sửa raw event cũ chỉ để phù hợp model mới; hãy tạo upcaster hoặc projection mapping khi đọc nếu kiến trúc yêu cầu bảo toàn lịch sử.

Đối với cache, dữ liệu có thể được xóa và tái tạo nên policy khác với database audit. Nhưng nếu cache key/value được chia sẻ giữa các version trong rolling deployment, vẫn cần version hóa hoặc namespace cache key để tránh deserialize sai kiểu.

## 23. Kiểm thử compatibility khi nâng phiên bản Jackson

Ngay cả khi schema không đổi, nâng Jackson có thể ảnh hưởng behavior do:

- Default feature thay đổi.
- Module Java Time thay đổi.
- Constructor/record parameter discovery thay đổi.
- Coercion hoặc enum handling thay đổi.
- Polymorphic type handling thay đổi.
- Custom serializer/deserializer phụ thuộc API nội bộ hoặc behavior cụ thể.
- Stream constraints hoặc parser behavior thay đổi.

Khi nâng version:

1. Giữ nguyên bộ fixture lịch sử.
2. Chạy chúng bằng dependency cũ để có baseline nếu có thể.
3. Chạy cùng fixture bằng dependency mới.
4. So sánh domain values sau deserialize.
5. So sánh output với golden contract.
6. Kiểm tra exception behavior cho invalid/unknown payload.
7. Ghi lại mọi thay đổi có chủ đích.

Dùng Jackson BOM để giữ Core, Databind, Annotations và module cùng release train. Không nâng riêng jackson-databind hoặc jackson-dataformat-* rồi bỏ qua dependency resolution thực tế.

## 24. Dùng schema validation khi có JSON Schema

DTO Java và Jackson annotation không phải lúc nào cũng mô tả đầy đủ contract. Nếu có JSON Schema hoặc OpenAPI, có thể validate fixture cũ và payload mới bằng schema tương ứng.

Ví dụ schema có required, properties, enum, format và additionalProperties. Khi thêm property optional, cần xác định schema V1 và V2 có được giữ riêng không.

Có thể duy trì:

```text
src/main/resources/schemas/
  customer-event-v1.schema.json
  customer-event-v2.schema.json
```

Test có thể xác nhận:

- Fixture V1 hợp lệ với schema V1.
- Writer V2 tạo payload hợp lệ với schema V2.
- Payload V1 được migration sang domain model hiện tại.
- Payload V2 không bị nhầm thành V1.
- Breaking change có version schema mới và được tài liệu hóa.

Schema validation không thay thế semantic assertion. Một payload có thể hợp lệ theo schema nhưng vẫn sai đơn vị tiền hoặc sai ý nghĩa timestamp.

## 25. Kiểm thử dữ liệu không hợp lệ và giới hạn parser

Tương thích không có nghĩa phải chấp nhận mọi payload cũ bất kể lỗi. Cần xác định payload nào từng được phát hợp lệ và payload nào bị lỗi do bug lịch sử.

Kiểm thử các trường hợp:

- JSON sai cú pháp.
- Field sai kiểu.
- Number vượt phạm vi.
- String quá dài.
- Object lồng quá sâu.
- Duplicate property nếu ứng dụng có policy.
- Unknown type id.
- Unknown enum.
- Payload bị cắt giữa chừng.
- Schema version không hỗ trợ.

Giữ các giới hạn StreamReadConstraints phù hợp. Không nới parser limit vô hạn chỉ để đọc một payload cũ bất thường; nếu có dữ liệu lịch sử vượt giới hạn mới, hãy xác định rõ nguồn gốc, đánh giá rủi ro và xử lý bằng migration có kiểm soát.

## 26. Tương thích không đồng nghĩa chấp nhận dữ liệu nguy hiểm

Một payload cũ có thể chứa field mà phiên bản mới không còn dùng, chẳng hạn isAdmin, role, ownerId hoặc một type metadata cũ. Việc reader bỏ qua unknown property không tự giải quyết authorization.

Đặc biệt với request JSON, không bind trực tiếp mọi field vào entity có quyền cao. Dùng request DTO allowlist, kiểm tra quyền và mapping sang domain model.

Với polymorphic typing, không dùng type id tùy ý từ dữ liệu không tin cậy để khởi tạo class. Duy trì allowlist subtype. Với payload cũ đã lưu, vẫn cần áp dụng validation và authorization theo ngữ cảnh xử lý hiện tại.

## 27. Quy trình kiểm thử tương thích trước khi release

Khi chuẩn bị release có thay đổi model hoặc Jackson:

1. Liệt kê schema version còn tồn tại trong database, queue, log và file.
2. Xác định producer/consumer nào có thể cùng chạy trong giai đoạn deploy.
3. Giữ fixture độc lập cho mỗi schema version được hỗ trợ.
4. Viết test reader hiện tại với payload cũ.
5. Kiểm tra missing, null, default, alias, enum và type id.
6. Viết migration test nếu cấu trúc thay đổi.
7. Viết golden output test cho schema mới.
8. Test reader cũ với output mới nếu rolling deployment cần hỗ trợ.
9. Validate schema và semantic values.
10. Chạy lại fixture khi nâng Jackson dependency.
11. Kiểm tra replay, database rebuild và cache compatibility.
12. Chỉ loại bỏ reader cũ khi dữ liệu cũ đã hết vòng đời hoặc có migration hoàn tất.
13. Ghi lại chính sách fallback và dead-letter cho version không hỗ trợ.

## 28. Bài thực hành tổng hợp

Tạo hai schema cho sự kiện khách hàng.

Version 1:

```json
{
  "eventId": "evt-1042",
  "customerName": "Nguyen An",
  "createdAt": "2025-06-10T08:30:00Z",
  "status": "ACTIVE"
}
```

Version 2:

```json
{
  "schemaVersion": 2,
  "eventId": "evt-1042",
  "displayName": "Nguyen An",
  "createdAt": "2025-06-10T08:30:00Z",
  "sourceSystem": "mobile-app",
  "status": "ACTIVE"
}
```

Thực hiện:

1. Tạo CustomerEventV1 và CustomerEventV2.
2. Lưu hai fixture JSON độc lập trong test resources.
3. Tạo mapper hiện tại với module và feature giống production.
4. Viết test đọc fixture V1.
5. Viết migration V1 sang domain model hiện tại.
6. Xác định giá trị mặc định của sourceSystem khi đọc V1.
7. Đổi customerName thành displayName và test alias hoặc version-specific DTO.
8. Thêm enum status mới và chọn policy cho reader cũ.
9. Test field mới khi reader cũ bật strict/lenient unknown-property policy.
10. Test null, missing và empty string riêng.
11. Test timestamp cũ và precision của BigDecimal nếu event có tiền.
12. Test unknown event type và schema version không hỗ trợ.
13. Serialize domain model hiện tại thành V2 và so sánh với golden file.
14. Kiểm tra migration không thay đổi payload gốc nếu raw event phải được bảo toàn.
15. Chạy compatibility matrix V1 writer/V2 reader và V2 writer/V1 reader.
16. Mô phỏng rolling deployment và xác định thứ tự nâng consumer/producer.
17. Lưu kết quả test cùng Jackson dependency version và schema version.

Bài thực hành hoàn thành khi code mới đọc được fixture cũ theo đúng ý nghĩa, writer mới phát đúng schema đã công bố và chính sách với consumer cũ được kiểm thử rõ ràng.

## 29. Nguyên tắc ghi nhớ

- Dữ liệu tồn tại lâu hơn code; reader mới cần hiểu các payload cũ còn trong database, queue, log và file.
- Phân biệt backward compatibility, forward compatibility, persistence compatibility và rolling-deployment compatibility.
- Schema version khác Jackson library version.
- Giữ fixture lịch sử độc lập; không sinh fixture cũ bằng writer hiện tại rồi coi đó là chuẩn.
- @JsonAlias giúp đọc tên cũ trong khi writer phát tên chính thức.
- Missing, null, empty và default là các trạng thái khác nhau, cần test riêng.
- Field mới có thể làm reader strict cũ thất bại; chọn unknown-property policy theo boundary.
- Enum mới và subtype mới cần fallback, raw preservation hoặc dead-letter policy rõ ràng.
- Thay đổi kiểu, đơn vị, timestamp và precision là thay đổi hợp đồng có rủi ro cao.
- Dùng DTO theo version và migration function khi alias không còn đủ rõ ràng.
- Schema version trong envelope giúp chọn reader/migration; nó không tự chuyển đổi dữ liệu.
- Test writer/reader theo ma trận phiên bản, đặc biệt trong rolling deployment.
- Golden file và round-trip hữu ích nhưng không thay thế fixture độc lập và semantic assertion.
- Nâng Jackson cần chạy lại toàn bộ fixture lịch sử với dependency mới.
- Không sửa raw event audit chỉ để khớp model mới; dùng upcaster/projection mapping nếu cần.
- Tương thích không bỏ qua validation, authorization, parser constraints hoặc allowlist subtype.

Một thay đổi model chỉ an toàn khi dữ liệu đã được phát trước đó vẫn được đọc đúng hoặc được chuyển đổi bằng migration có kiểm soát. Hãy giữ fixture lịch sử, xác định rõ từng schema version và kiểm thử cả producer lẫn consumer; đó là cách biến tương thích dữ liệu thành một cam kết có bằng chứng thay vì một giả định sau khi deploy.
