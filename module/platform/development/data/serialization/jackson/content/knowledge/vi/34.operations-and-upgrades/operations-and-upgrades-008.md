# Chạy bộ kiểm thử dữ liệu cũ trước khi triển khai cấu hình mới

Khi thay đổi cấu hình Jackson hoặc nâng cấp `jackson-core`, `jackson-databind` và các module dataformat, dữ liệu JSON đã lưu từ những phiên bản ứng dụng trước có thể được đọc hoặc ghi theo cách khác. Một cấu hình mới có thể làm thay đổi tên field, cách xử lý null, enum, ngày giờ, kiểu số, unknown property, polymorphic type hoặc giới hạn parser. Những thay đổi này đôi khi không làm ứng dụng khởi động thất bại; chúng chỉ xuất hiện khi một file cũ, message trong queue hoặc record lịch sử được đọc lại.

Trước khi triển khai cấu hình mới, cần chạy một **bộ kiểm thử dữ liệu cũ (legacy data compatibility suite)**: tập payload đại diện cho các phiên bản đã phát hành, kèm kết quả mong đợi và test tự động chạy bằng cấu hình ứng viên. Mục tiêu là xác nhận ứng dụng mới vẫn hiểu dữ liệu cần hỗ trợ, đồng thời output mới không phá consumer còn được hỗ trợ.

Kiểm thử dữ liệu cũ khác với kiểm thử một mapper mới trên object mới tạo. Một test round-trip dùng cùng mapper có thể thành công dù format đã thay đổi theo cách khiến dữ liệu lịch sử hoặc service cũ không đọc được. Cần giữ fixture độc lập, kiểm tra semantics sau deserialize và xác nhận chiều tương thích mà hệ thống cam kết.

## 1. Vì sao phải kiểm thử dữ liệu cũ trước khi nâng cấp?

Jackson là một phần của wire contract nếu ứng dụng lưu JSON, gửi message hoặc trao đổi dữ liệu với service khác. Cùng một Java class có thể được serialize thành JSON khác nhau khi thay đổi:

- `ObjectMapper` feature hoặc `JsonFactory` feature.
- Jackson version hoặc module version.
- Naming strategy, annotation hoặc mix-in.
- Custom serializer/deserializer.
- Java Time module và date/time settings.
- Enum representation và coercion policy.
- Inclusion/null policy.
- Polymorphic typing và type metadata.
- Parser strictness, duplicate detection, trailing-token checks hoặc input constraints.

Ví dụ, phiên bản cũ ghi enum bằng tên constant:

```json
{
  "status": "IN_PROGRESS"
}
```

Sau khi đổi cấu hình, writer có thể ghi `"in-progress"`, còn reader mới có thể chỉ nhận `"IN_PROGRESS"`. Object vừa tạo trong test nội bộ vẫn có thể round-trip nếu writer và reader mới dùng cùng quy tắc, nhưng dữ liệu cũ hoặc consumer cũ sẽ không hiểu output mới.

Một ví dụ khác là đổi timestamp từ epoch milliseconds sang ISO-8601. Cả hai đều có thể parse thành kiểu thời gian, nhưng nếu consumer cũ hiểu số là milliseconds thì chuỗi mới không còn tương thích. Đó là thay đổi contract dù code compile và unit test thông thường vẫn pass.

## 2. Xác định phạm vi tương thích trước khi chạy test

Không phải mọi ứng dụng đều cần hỗ trợ mọi payload từng tồn tại. Trước tiên, xác định dữ liệu nào phải tiếp tục đọc được và consumer nào phải tiếp tục đọc output mới.

Các nguồn dữ liệu thường cần đưa vào corpus:

- JSON file đã lưu trong database, object storage hoặc filesystem.
- Message còn tồn tại trong broker, retry queue hoặc dead-letter queue.
- Event lịch sử được replay để dựng lại projection.
- Request/response mẫu từ client đang được hỗ trợ.
- Snapshot hoặc export do các bản ứng dụng trước tạo ra.
- Payload từ hệ thống đối tác có chu kỳ nâng cấp chậm.
- Fixture cũ đang được dùng trong integration/contract tests.

Ghi rõ khoảng version cần hỗ trợ, ví dụ: đọc được payload từ ba release gần nhất; output mới phải được consumer hiện tại và release trước đó đọc được; dữ liệu trước một mốc migration không còn được hỗ trợ nếu đã có chuyển đổi chính thức.

### 2.1. Bốn câu hỏi tương thích

| Câu hỏi | Ý nghĩa | Ví dụ kiểm tra |
|---|---|---|
| New reader đọc old data? | Reader mới phải hiểu payload đã lưu trước đây | V1 fixture → candidate mapper |
| Old reader đọc new output? | Consumer cũ có hiểu dữ liệu writer mới không? | Candidate writer → mapper/consumer V1 |
| New reader đọc new output? | Cấu hình mới hoạt động bình thường | Candidate writer → candidate reader |
| Old reader đọc old output? | Baseline lịch sử vẫn được tái lập | V1 writer → V1 reader |

Không phải hệ thống nào cũng cần cả bốn chiều. Nhưng phải ghi rõ chiều nào là yêu cầu bắt buộc, chiều nào chỉ để tham khảo và chiều nào không được hỗ trợ.

### 2.2. Backward compatibility và forward compatibility

- **Backward compatibility:** phiên bản mới đọc được dữ liệu do phiên bản cũ tạo ra.
- **Forward compatibility:** phiên bản cũ đọc được dữ liệu do phiên bản mới tạo ra.

Đối với dữ liệu lưu lâu dài, backward compatibility thường rất quan trọng vì reader mới phải mở được record cũ. Với rolling deployment, forward compatibility cũng quan trọng: trong một khoảng thời gian, instance cũ có thể nhận message do instance mới phát ra.

Nếu deployment bảo đảm mọi consumer được nâng cấp trước producer, có thể không cần forward compatibility trong thời gian đó. Nhưng thứ tự rollout phải được bảo đảm bằng quy trình triển khai và kiểm thử, không nên dựa vào giả định.

## 3. Tạo corpus dữ liệu lịch sử có version

Một corpus tốt gồm nhiều payload nhỏ, có tên và metadata rõ ràng. Ví dụ:

```text
src/test/resources/legacy-json/
  README.md
  v1/
    user-created-minimal.json
    user-created-full.json
    order-with-null-fields.json
    order-with-old-enum.json
    event-with-epoch-time.json
  v2/
    user-created-with-profile.json
    order-with-decimal-total.json
  v3/
    order-with-new-status.json
  invalid/
    truncated-object.json
    duplicate-key.json
    trailing-root-value.json
```

Tên fixture nên thể hiện phiên bản producer hoặc loại tình huống, không chỉ là `test1.json`. Nếu nhiều service tạo cùng event type, ghi rõ producer/service trong metadata.

### 3.1. Mỗi fixture cần có thông tin nguồn gốc

README hoặc manifest của corpus nên ghi:

- Event/API type.
- Producer version hoặc schema version.
- Jackson version và các module liên quan nếu biết.
- Ngày hoặc release tạo fixture.
- Nội dung fixture được lấy từ đâu (synthetic, integration test hay bản sao đã ẩn danh).
- Kết quả semantics mong đợi.
- Các field đặc biệt: null, absent, enum cũ, timestamp, decimal, binary hoặc extension.
- Reader version tối thiểu cần hỗ trợ.

Ví dụ metadata mô tả fixture:

```yaml
id: order-created-v1-null-shipping
eventType: OrderCreated
producerVersion: 1.8.0
jacksonLine: 2.15.x
fixture: v1/order-created-null-shipping.json
expected:
  shippingAddress: null
  status: CREATED
compatibility: must-read
```

Đây chỉ là ví dụ cách mô tả. Không cần đưa metadata vào chính JSON payload nếu contract không yêu cầu.

### 3.2. Giữ fixture độc lập với code đang kiểm thử

Không regenerate toàn bộ corpus bằng mapper ứng viên mỗi khi test chạy. Nếu làm vậy, test có thể tự cập nhật expected data theo implementation mới và không còn phát hiện thay đổi ngoài ý muốn.

Fixture nên được tạo từ một nguồn đã biết:

- Artifact từ release cũ đã được lưu.
- Test fixture được commit từ thời điểm contract được chốt.
- Payload do producer độc lập tạo ra.
- Dữ liệu production đã được ẩn danh và phê duyệt sử dụng.

Khi cần cập nhật fixture, thực hiện thay đổi có chủ đích, ghi nguồn và review diff như một thay đổi contract.

## 4. Bảo vệ dữ liệu thật khi xây dựng corpus

Payload production có thể chứa email, số điện thoại, token, địa chỉ, thông tin tài chính hoặc dữ liệu cá nhân. Không đưa nguyên dữ liệu nhạy cảm vào repository chỉ để làm fixture.

Các lựa chọn an toàn hơn:

- Tạo synthetic fixture có cùng cấu trúc và edge case.
- Ẩn danh hoặc thay thế dữ liệu định danh trước khi lưu.
- Loại bỏ password, access token, secret, session ID và thông tin xác thực.
- Giữ kích thước, kiểu và trạng thái null/absent cần kiểm thử sau khi ẩn danh.
- Lưu fixture nhạy cảm trong môi trường test được kiểm soát nếu không thể tạo synthetic equivalent.
- Không ghi toàn bộ payload vào CI log khi test thất bại.

Ẩn danh phải giữ các đặc tính quan trọng của dữ liệu. Ví dụ, nếu test cần xác nhận Unicode, không thay mọi tên thành ASCII. Nếu test cần một string dài sát giới hạn, giữ độ dài nhưng thay nội dung.

## 5. Chụp baseline bằng cấu hình hiện tại

Trước khi đổi cấu hình, chạy corpus với mapper hiện tại để biết trạng thái baseline. Lưu lại:

- Fixture nào deserialize thành công.
- DTO/domain values sau khi đọc.
- Fixture nào cố ý bị từ chối.
- JSON output của các object mẫu nếu cần so sánh writer.
- Warning, coercion hoặc deprecated behavior đã biết.
- Thời gian parse/serialize nếu hiệu năng là mục tiêu nâng cấp.

Baseline giúp phân biệt regression mới với lỗi đã tồn tại. Nếu fixture đã fail ở cấu hình hiện tại, không nên quy lỗi đó cho thay đổi mới; ghi nhận trạng thái và quyết định có sửa trong cùng đợt hay không.

### 5.1. Cố định mapper cũ trong test

Có thể tạo hai mapper factory trong cùng test suite nếu đang so sánh cấu hình trên cùng Jackson runtime:

```java
ObjectMapper oldMapper = createCurrentMapper();
ObjectMapper candidateMapper = createCandidateMapper();
```

`createCurrentMapper()` phải tái tạo chính xác cấu hình đang chạy ở production, gồm module, feature, mix-in và custom serializer. Không chỉ dùng `new ObjectMapper()` nếu ứng dụng thực tế có Spring Boot auto-configuration hoặc module riêng.

Nếu thay đổi Jackson dependency version, hai bộ thư viện khác version không thể luôn được nạp an toàn trong cùng classloader vì trùng package/class. Trong trường hợp đó, chạy baseline và candidate trong các Gradle/Maven module, process hoặc container riêng, mỗi bên khóa dependency của chính nó. So sánh fixture và kết quả qua file/JSON contract thay vì cố nạp hai Jackson version vào một JVM.

### 5.2. Không thay đổi mapper dùng chung trong runtime test

Tạo mapper hoàn chỉnh trước khi sử dụng. `ObjectMapper` được thiết kế để tái sử dụng sau khi cấu hình; thay đổi feature/module trên mapper đang được dùng đồng thời có thể làm test không xác định hoặc không phản ánh production.

## 6. Chạy old payload qua candidate reader

Đây là kiểm tra trung tâm của backward compatibility: dữ liệu lịch sử phải được đọc bởi cấu hình mới.

Ví dụ test fixture JSON:

```java
class LegacyOrderCompatibilityTest {
    private final ObjectMapper candidateMapper = createCandidateMapper();

    @Test
    void readsOrderCreatedByPreviousRelease() throws Exception {
        byte[] payload;
        try (InputStream input = getClass().getResourceAsStream(
                "/legacy-json/v1/order-created-full.json")) {
            if (input == null) {
                throw new IllegalStateException("Missing legacy fixture");
            }
            payload = input.readAllBytes();
        }

        OrderCreated event = candidateMapper.readValue(
            payload,
            OrderCreated.class
        );

        assertEquals("evt-100", event.getEventId());
        assertEquals("ORD-100", event.getOrderId());
        assertEquals(OrderStatus.CREATED, event.getStatus());
    }
}
```

Không dừng ở việc `readValue()` không ném exception. Hãy xác nhận các field quan trọng được hiểu đúng. Một payload có thể parse thành công nhưng giá trị mặc định, enum fallback hoặc coercion khiến semantics thay đổi.

### 6.1. Test tất cả fixture bắt buộc

```java
@ParameterizedTest
@ValueSource(strings = {
    "/legacy-json/v1/order-created-minimal.json",
    "/legacy-json/v1/order-created-full.json",
    "/legacy-json/v2/order-created-with-profile.json"
})
void candidateReaderAcceptsSupportedHistoricalPayloads(String resource)
        throws Exception {
    byte[] payload;
    try (InputStream input = getClass().getResourceAsStream(resource)) {
        if (input == null) {
            throw new IllegalStateException("Missing fixture: " + resource);
        }
        payload = input.readAllBytes();
    }

    OrderCreated event = candidateMapper.readValue(payload, OrderCreated.class);
    assertNotNull(event.getOrderId());
}
```

Đây là kiểm tra smoke cho tập fixture. Với từng loại fixture, nên có assertion semantics cụ thể hơn, ví dụ timestamp, null, decimal và enum.

## 7. So sánh kết quả cũ và mới theo semantics

Khi cùng một fixture được đọc bằng mapper cũ và mapper mới, có thể so sánh kết quả:

```java
OrderCreated oldResult = oldMapper.readValue(payload, OrderCreated.class);
OrderCreated newResult = candidateMapper.readValue(payload, OrderCreated.class);

assertEquals(oldResult.getOrderId(), newResult.getOrderId());
assertEquals(oldResult.getStatus(), newResult.getStatus());
assertEquals(oldResult.getCreatedAt(), newResult.getCreatedAt());
```

Không nhất thiết mọi field phải giống nhau. Một nâng cấp có thể cố ý chuẩn hóa legacy value, ví dụ alias enum cũ thành constant mới. Khi đó, assertion phải kiểm tra mapping mới theo contract được phê duyệt, không chỉ so sánh object cũ và mới một cách máy móc.

Nên định nghĩa expected result độc lập:

```java
assertEquals(OrderStatus.IN_PROGRESS, newResult.getStatus());
assertEquals(Instant.parse("2024-03-01T10:00:00Z"), newResult.getCreatedAt());
```

Expected values rõ ràng giúp test phát hiện cả hai mapper cùng có lỗi hoặc baseline cũ vốn đã hiểu sai dữ liệu.

### 7.1. So sánh JsonNode khi kiểm tra JSON representation

Nếu cần so sánh output JSON theo cấu trúc thay vì thứ tự property:

```java
JsonNode expected = jsonMapper.readTree(expectedJson);
JsonNode actual = jsonMapper.readTree(candidateJson);

assertEquals(expected, actual);
```

So sánh tree phù hợp khi contract quan tâm field/value và không quan tâm thứ tự key. Nhưng tree equality không thay thế mọi kiểm tra type/format; hãy kiểm tra riêng number type, null, array order và representation của timestamp/decimal.

Nếu output được ký số, hash hoặc dùng byte-level cache key, cần kiểm tra canonicalization/deterministic serialization theo một contract riêng. Không coi `JsonNode.equals()` là bằng chứng byte output giống nhau.

## 8. Kiểm tra writer mới có phá consumer cũ không

Nếu hệ thống rolling deploy hoặc có consumer ngoài chưa nâng cấp, hãy test payload mới bằng reader cũ.

Ví dụ trong cùng Jackson runtime với hai mapper config:

```java
byte[] newPayload = candidateMapper.writeValueAsBytes(newEvent);

OrderCreated oldConsumerResult = oldMapper.readValue(
    newPayload,
    OrderCreated.class
);

assertEquals(newEvent.getOrderId(), oldConsumerResult.getOrderId());
```

Nếu `oldMapper` dùng Jackson dependency cũ, chạy phần đọc trong module/process riêng. Cần test consumer thực tế hoặc artifact consumer được khóa version, không chỉ tạo một mapper mới với vài feature giả lập.

### 8.1. Unknown property policy

Nếu writer mới thêm field, reader cũ có thể:

- Từ chối với `FAIL_ON_UNKNOWN_PROPERTIES`.
- Bỏ qua nếu cấu hình lenient hoặc DTO có `@JsonIgnoreProperties(ignoreUnknown = true)`.
- Thu thập field qua `@JsonAnySetter`.

Hãy kiểm tra policy thực tế của consumer. Không mặc định mọi client đều bỏ qua field mới.

### 8.2. Thay đổi required field

Thêm field mới bắt buộc có thể khiến reader mới không đọc được payload cũ hoặc khiến consumer cũ không hiểu payload mới. Nếu field có default, kiểm tra default có cùng semantics với giá trị lịch sử hay không.

### 8.3. Đổi tên property

`@JsonAlias` có thể giúp reader mới chấp nhận tên cũ khi deserialize:

```java
public class OrderCreated {
    @JsonAlias("order_number")
    private String orderId;
}
```

Alias không làm writer tự serialize đồng thời tên cũ và mới. Writer thường dùng tên property canonical theo cấu hình. Nếu consumer cũ chỉ biết tên cũ, output mới dùng tên mới vẫn có thể phá consumer; cần migration/versioning phù hợp.

## 9. Kiểm thử thay đổi naming strategy

Thay naming strategy có thể đổi mọi key trong JSON:

```java
ObjectMapper mapper = JsonMapper.builder()
    .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    .build();
```

Java property `createdAt` có thể trở thành `created_at`. Trước khi triển khai:

- Đọc fixture có tên cũ.
- Xác nhận alias hoặc mix-in nhận được cả tên legacy nếu cần.
- So sánh output mới với golden JSON.
- Kiểm tra consumer đang chờ tên nào.
- Kiểm tra tên đặc biệt có `@JsonProperty` override hay không.

Ví dụ DTO nhận cả tên cũ và mới:

```java
public class EventRequest {
    @JsonAlias("createdAt")
    private Instant createdAt;
}
```

Nếu mapper dùng snake_case, property chính có thể serialize thành `created_at`; alias chỉ hỗ trợ deserialize `createdAt`. Cần test chính xác output canonical để tránh đổi wire format ngoài ý muốn.

## 10. Kiểm thử null, absent và inclusion policy

Các feature như `JsonInclude.Include.NON_NULL`, `NON_EMPTY` hoặc `NON_DEFAULT` có thể làm output mới bỏ đi field từng được ghi trước đây.

Ví dụ:

```java
ObjectMapper candidateMapper = JsonMapper.builder()
    .serializationInclusion(JsonInclude.Include.NON_NULL)
    .build();
```

Nếu field `middleName` null, output có thể không còn chứa key:

```json
{}
```

thay vì:

```json
{"middleName":null}
```

Với một số API, absent và null có semantics khác nhau, đặc biệt khi consumer dùng PATCH hoặc merge logic. Test phải bao gồm:

- Field có giá trị.
- Field null.
- Field absent trong input cũ.
- Field được khởi tạo default.
- Chuỗi rỗng và collection rỗng.
- Output trước/sau thay đổi inclusion policy.

Không kết luận tương thích chỉ vì DTO Java sau deserialize có cùng giá trị null. Cần kiểm tra key presence nếu contract phụ thuộc vào sự khác nhau giữa absent và null.

## 11. Kiểm thử enum và giá trị legacy

Enum là một điểm dễ bị phá khi đổi tên constant hoặc cấu hình serialize/deserialize.

Ví dụ enum mới:

```java
public enum OrderStatus {
    CREATED,
    IN_PROGRESS,
    COMPLETED,
    CANCELLED,
    @JsonEnumDefaultValue UNKNOWN
}
```

Nếu dữ liệu cũ có token `PROCESSING`, có thể chấp nhận alias hoặc custom mapping:

```java
public enum OrderStatus {
    CREATED,
    @JsonProperty("processing")
    IN_PROGRESS,
    COMPLETED,
    CANCELLED,
    @JsonEnumDefaultValue UNKNOWN
}
```

Tùy contract, có thể dùng `@JsonCreator` để map nhiều token cũ. Điều quan trọng là giữ writer output ổn định và test token cũ/mới.

Corpus enum nên bao gồm:

- Mọi token enum từng được phát hành và còn nằm trong dữ liệu lưu trữ.
- Case khác nhau nếu từng được chấp nhận.
- Alias cũ sau khi rename.
- Giá trị không biết.
- Null và field absent.
- Numeric ordinal nếu hệ thống lịch sử từng ghi số.

Nếu bật `READ_UNKNOWN_ENUM_VALUES_AS_NULL` hoặc `READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE`, kiểm tra xem giá trị lạ có bị biến thành null/UNKNOWN ngoài ý muốn hay không. Với workflow quan trọng, fail có thể an toàn hơn fallback âm thầm.

## 12. Kiểm thử date/time và timezone

Nâng cấp module Java Time hoặc đổi date feature có thể làm thay đổi representation của ngày giờ. Các trường hợp cần giữ trong corpus:

- ISO-8601 UTC với `Z`.
- Offset dương/âm.
- Timestamp có fractional seconds.
- Local date không có time.
- Legacy epoch seconds hoặc milliseconds.
- Giá trị null/absent.
- Ngày giờ ở biên timezone/DST nếu domain sử dụng local time.

Ví dụ assertion:

```java
assertEquals(
    Instant.parse("2024-03-01T10:00:00Z"),
    event.getCreatedAt()
);
```

Không chỉ so sánh chuỗi output. Hãy xác nhận cùng một instant và timezone semantics. Nếu format mới đổi từ numeric timestamp sang ISO string, cần đánh giá consumer cũ có đọc được hay không và có version migration không.

## 13. Kiểm thử numeric coercion, decimal và overflow

Jackson có các coercion rule để chuyển token JSON sang kiểu Java. Thay đổi coercion configuration có thể khiến dữ liệu cũ từng đọc được nay bị từ chối hoặc được chuyển theo cách khác.

Corpus số nên có:

- Integer bình thường và số âm.
- Integer gần giới hạn `int`/`long`.
- Số nguyên lớn cần `BigInteger`.
- Decimal có scale đáng kể.
- Exponent notation.
- Numeric string nếu từng được chấp nhận.
- Empty string/null ở cột số nếu dữ liệu cũ có.
- Giá trị vượt range hoặc sai kiểu.

Ví dụ tiền nên dùng `BigDecimal` và assertion chính xác:

```java
assertEquals(new BigDecimal("125.50"), order.getTotal());
```

Không chuyển qua `double` trong expected test nếu contract yêu cầu decimal precision. Nếu thay đổi coercion policy, xác nhận numeric string như `"12"` được chấp nhận hay từ chối đúng ý định.

## 14. Kiểm thử unknown properties và duplicate keys

Khi thay đổi `FAIL_ON_UNKNOWN_PROPERTIES`, `@JsonIgnoreProperties` hoặc `@JsonAnySetter`, hãy kiểm tra payload cũ có extension fields.

Các fixture cần phân biệt:

- Field mới nhưng hợp lệ theo schema mới.
- Field gõ sai.
- Field lạ cần giữ lại.
- Field lạ cần từ chối.
- Duplicate key ở root.
- Duplicate key trong object lồng nhau.
- Token/root value dư sau document.

Nếu bật strict duplicate detection:

```java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper candidateMapper = new ObjectMapper(factory)
    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
```

Một fixture cũ có duplicate key có thể bắt đầu fail sau thay đổi này. Đó có thể là điều mong muốn để loại bỏ input mơ hồ, nhưng nếu dữ liệu đã lưu chứa duplicate thì cần kế hoạch migration hoặc xử lý trước khi bật strict mode cho luồng đọc lịch sử.

## 15. Kiểm thử polymorphic type và security configuration

Nếu ứng dụng dùng `@JsonTypeInfo`, custom type resolver hoặc default typing, thay đổi type metadata có thể làm dữ liệu cũ không còn đọc được. Cần fixture cho mọi subtype đang được lưu hoặc truyền.

Kiểm tra:

- Property discriminator và tên type cũ.
- Subtype đã rename hoặc package đã đổi.
- Type ID không biết.
- Payload thiếu discriminator.
- Nested polymorphic property.
- Unknown subtype behavior.
- Default typing và allowlist/subtype validator.

Không bật default typing rộng cho dữ liệu không tin cậy chỉ để đọc được fixture cũ. Nếu legacy payload có type metadata không an toàn, dùng allowlist và migration có kiểm soát. Tương thích dữ liệu không được đánh đổi bằng việc cho phép khởi tạo arbitrary Java type.

## 16. Kiểm thử parser constraints mới trên dữ liệu cũ

Khi bật `StreamReadConstraints`, payload cũ có thể bị từ chối nếu chứa string, property name, number token hoặc nesting depth vượt giới hạn mới.

Ví dụ:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
    .maxNestingDepth(100)
    .maxStringLength(1_000_000)
    .maxNumberLength(128)
    .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper candidateMapper = new ObjectMapper(factory);
```

Nếu có fixture vượt giới hạn, quyết định có chủ đích:

- Payload đó là dữ liệu lỗi/không hợp lệ và nên bị từ chối.
- Payload đó hợp lệ theo contract cũ nhưng giới hạn mới quá thấp.
- Cần migration hoặc tách reader legacy có giới hạn phù hợp.
- Cần giới hạn body/record ở transport thay vì hạ ngưỡng token một cách rộng.

Không tăng giới hạn vô hạn để mọi fixture đều pass. Parser constraints là lớp bảo vệ tài nguyên; mục tiêu là giữ dữ liệu hợp lệ trong giới hạn an toàn và xử lý ngoại lệ có kiểm soát.

## 17. Kiểm thử custom module, serializer và deserializer

Một mapper production có thể đăng ký:

- `JavaTimeModule`.
- Custom serializer/deserializer.
- Mix-in annotations.
- Naming strategy.
- Problem handlers.
- Subtype registrations.
- Coercion configuration.
- Module riêng do ứng dụng hoặc thư viện cung cấp.

Nếu quên đăng ký một module trong test candidate, kết quả test không đại diện production. Nên có một factory method duy nhất tạo mapper theo cấu hình production, hoặc một Spring configuration được test trực tiếp.

Ví dụ:

```java
public final class ApiObjectMappers {
    private ApiObjectMappers() {
    }

    public static ObjectMapper candidateMapper() {
        JavaTimeModule javaTime = new JavaTimeModule();

        return JsonMapper.builder()
            .addModule(javaTime)
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
            .build();
    }
}
```

Ví dụ này chỉ minh họa cấu trúc. Mapper thực tế phải bao gồm toàn bộ module, serializer, mix-in và feature của ứng dụng. Nếu dùng Spring Boot auto-configuration, hãy test `ObjectMapper` được Spring inject thay vì chỉ test mapper tự tạo.

## 18. Tách kiểm thử cấu hình khỏi kiểm thử nâng cấp dependency

Có hai loại thay đổi thường xảy ra cùng lúc nhưng nên phân biệt:

1. **Configuration change:** vẫn dùng cùng Jackson version nhưng đổi feature, module registration, naming, inclusion hoặc parser policy.
2. **Library upgrade:** đổi Jackson Core/Databind/dataformat version và có thể thay đổi behavior mặc định/API.

Nếu thay cả hai cùng lúc và test fail, khó xác định nguyên nhân. Quy trình an toàn hơn:

- Chạy baseline trên version hiện tại/cấu hình hiện tại.
- Chỉ đổi config trên cùng dependency để xác định tác động của feature.
- Nâng dependency với cấu hình đã biết và chạy lại corpus.
- Nếu cần, thử từng module version theo BOM đồng bộ.
- Ghi lại kết quả riêng cho config và dependency upgrade.

Không phải lúc nào cũng cần phát hành thành nhiều deployment. Nhưng trong kiểm thử, tách biến số giúp xác định chính xác regression.

## 19. Ma trận test cho old/new reader và writer

Một ma trận đơn giản:

| Writer | Reader | Kết quả kỳ vọng | Khi nào cần |
|---|---|---|---|
| Old | Old | Pass baseline | Luôn hữu ích để tái lập lịch sử |
| Old | New | Pass với mọi fixture còn hỗ trợ | Bắt buộc cho backward compatibility |
| New | New | Pass | Bắt buộc cho candidate release |
| New | Old | Pass hoặc fail có chủ đích | Quan trọng với rolling deploy/consumer cũ |

Với nhiều release, có thể tạo matrix:

| Producer fixture | Candidate reader | Must pass? |
|---|---|---|
| V1 | Current | Theo retention/support policy |
| V2 | Current | Có nếu V2 còn trong support window |
| V3 | Current | Có |
| Candidate | Previous consumer | Theo deployment order |
| Candidate | Current consumer | Có |

Không nhất thiết chạy mọi cặp version nếu chi phí lớn. Chọn các cặp dựa trên retention window, rollout strategy và consumer đang hoạt động.

## 20. Ví dụ một bộ test tương thích có thể tái sử dụng

Có thể mô tả fixture và expected behavior bằng test case object:

```java
record LegacyFixtureCase(
    String resource,
    String expectedOrderId,
    OrderStatus expectedStatus,
    Instant expectedCreatedAt
) {}
```

Sau đó dùng parameterized test:

```java
@ParameterizedTest
@MethodSource("legacyFixtures")
void candidateMapperReadsLegacyPayload(LegacyFixtureCase testCase)
        throws Exception {

    byte[] payload;
    try (InputStream input = getClass().getResourceAsStream(
            testCase.resource())) {
        if (input == null) {
            throw new IllegalStateException(testCase.resource());
        }
        payload = input.readAllBytes();
    }

    OrderCreated event = candidateMapper.readValue(payload, OrderCreated.class);

    assertEquals(testCase.expectedOrderId(), event.getOrderId());
    assertEquals(testCase.expectedStatus(), event.getStatus());
    assertEquals(testCase.expectedCreatedAt(), event.getCreatedAt());
}

static Stream<LegacyFixtureCase> legacyFixtures() {
    return Stream.of(
        new LegacyFixtureCase(
            "/legacy-json/v1/order-created.json",
            "ORD-100",
            OrderStatus.CREATED,
            Instant.parse("2024-01-01T00:00:00Z")
        ),
        new LegacyFixtureCase(
            "/legacy-json/v2/order-created-processing.json",
            "ORD-200",
            OrderStatus.IN_PROGRESS,
            Instant.parse("2024-02-01T12:30:00Z")
        )
    );
}
```

Ví dụ dùng JUnit 5. Thay expected values và DTO theo contract thực tế. Điểm quan trọng là fixture và expected semantics được khai báo tường minh, không được tính từ cùng mapper đang kiểm thử.

## 21. Kiểm tra output mới bằng golden files

Nếu thay đổi writer configuration, hãy kiểm tra output mới:

```java
String actual = candidateMapper.writeValueAsString(event);
JsonNode actualTree = jsonMapper.readTree(actual);
JsonNode expectedTree = jsonMapper.readTree(expectedJson);

assertEquals(expectedTree, actualTree);
```

Golden file hữu ích để phát hiện:

- Field rename hoặc naming strategy thay đổi.
- Null field bị bỏ hoặc xuất hiện.
- Enum đổi token.
- Timestamp đổi format/unit.
- Decimal bị chuyển thành floating point/string.
- Property mới vô tình lộ ra.
- Nested structure hoặc array order thay đổi.

Khi expected output thay đổi có chủ đích, review diff và ghi rõ contract change. Không tự động cập nhật golden file khi test fail.

### 21.1. Khi nào cần byte-for-byte golden test?

Chỉ dùng byte-for-byte khi byte representation là contract, ví dụ chữ ký số, canonical JSON, deterministic artifact hoặc hash content. Với JSON thông thường, thứ tự object property có thể không mang ý nghĩa; so sánh JSON tree thường phù hợp hơn.

Nếu output là CBOR/Smile, byte-for-byte có thể khác do encoder version hoặc map ordering dù semantics giống nhau. Chỉ yêu cầu byte identity nếu đã chọn canonical encoding/deterministic serialization rõ ràng.

## 22. Kiểm thử migration và reserialization

Một số hệ thống đọc record cũ rồi ghi lại bằng cấu hình mới để chuẩn hóa dữ liệu. Đây là migration, không chỉ là đọc dữ liệu.

Pipeline có thể là:

```text
Legacy bytes
    |
    v
Candidate reader
    |
    v
Domain object
    |
    v
Validation / normalization
    |
    v
Candidate writer
    |
    v
New bytes
```

Test migration cần xác nhận:

- Dữ liệu quan trọng không bị mất.
- Null/absent/empty có semantics đúng.
- Enum alias được chuẩn hóa đúng.
- Timestamp không đổi instant.
- Decimal không mất precision.
- Unknown extension field có được giữ hoặc loại bỏ theo policy.
- Migration có idempotent không: chạy hai lần có tạo thêm thay đổi không?
- Có thể rollback hoặc khôi phục bản gốc nếu migration thất bại không?

Không ghi đè dữ liệu gốc trước khi migration được kiểm chứng và có backup/rollback plan. Với event log immutable, thường nên giữ payload gốc và tạo projection/version mới thay vì rewrite lịch sử tùy tiện.

## 23. Kiểm thử dữ liệu cũ ở tầng Spring

Nếu ứng dụng dùng Spring Boot, `ObjectMapper` thường được cấu hình qua auto-configuration, builder customizer hoặc bean riêng. Test mapper tự tạo có thể bỏ sót cấu hình thật.

Có thể inject mapper production trong Spring test:

```java
@SpringBootTest
class LegacyPayloadSpringCompatibilityTest {
    @Autowired
    ObjectMapper objectMapper;

    @Test
    void readsPayloadFromPreviousRelease() throws Exception {
        String json = """
            {
              "event_id": "evt-100",
              "order_id": "ORD-100",
              "status": "CREATED"
            }
            """;

        OrderCreated event = objectMapper.readValue(json, OrderCreated.class);

        assertEquals("ORD-100", event.getOrderId());
    }
}
```

Nếu ứng dụng có nhiều mapper cho REST, Kafka, Redis hoặc file import, test từng mapper/factory riêng. Một mapper của HTTP không nhất thiết là mapper dùng cho message consumer.

### 23.1. Test qua endpoint hoặc message listener

Đối với API, dùng `MockMvc` hoặc WebTestClient để kiểm tra `HttpMessageConverter` thực tế. Đối với broker, dùng integration test cho serializer/deserializer thực tế và header/content type. Đối với file import, test đường đọc `InputStream`/`ObjectReader` thực tế.

Mục tiêu là kiểm tra toàn bộ đường đi mà dữ liệu cũ sẽ sử dụng sau deployment, không chỉ một mapper isolated.

## 24. Đưa legacy suite vào CI/CD

Chạy bộ kiểm thử trước khi build artifact được phát hành hoặc trước khi promote candidate lên môi trường tiếp theo.

Một pipeline gợi ý:

```text
Pull request / dependency update
            |
            v
       Unit tests
            |
            v
   Legacy fixture suite
            |
            v
   Golden output tests
            |
            v
  Cross-version contract tests
            |
            v
   Spring integration tests
            |
            v
   Performance regression tests
            |
            v
      Build candidate
            |
            v
       Deploy canary
            |
            v
  Observe decode/error metrics
            |
            v
       Full rollout
```

Không phải mọi performance test đều cần chạy ở mỗi pull request; có thể chạy theo lịch hoặc khi dependency/configuration thay đổi. Nhưng fixture compatibility suite nên đủ nhanh để chạy thường xuyên.

### 24.1. Đặt release gate rõ ràng

Một candidate không nên được promote nếu:

- Fixture bắt buộc đọc được nhưng candidate reader từ chối.
- Giá trị quan trọng sau deserialize thay đổi ngoài dự kiến.
- Writer output phá consumer còn được hỗ trợ.
- Enum/date/decimal/null semantics bị đổi ngoài contract.
- Parser mới từ chối dữ liệu hợp lệ trong retention window.
- Security-sensitive payload trở nên permissive ngoài chủ đích.

Một fixture không còn thuộc support window có thể được đánh dấu deprecated/expected-to-fail, nhưng quyết định đó cần có owner và thời điểm loại bỏ rõ ràng.

## 25. Canary và quan sát sau triển khai

Test corpus không thể bao phủ mọi payload production. Sau khi deploy canary, theo dõi:

- Tỷ lệ deserialize failure theo event type và producer version.
- Unknown property/enum frequency.
- Parser constraint violations.
- Invalid format/coercion errors.
- Message retry và dead-letter rate.
- Số lượng record cũ được replay thành công.
- Latency parse/serialize và allocation/GC.
- Sự khác biệt output giữa canary và baseline nếu có shadow comparison.

Không log raw payload nhạy cảm. Ghi exception category, schema/event version, source service, correlation ID và field path an toàn khi cần điều tra.

### 25.1. Shadow read hoặc dual decode

Trong một giai đoạn kiểm soát, có thể gửi cùng payload tới reader cũ và candidate reader ở chế độ shadow, chỉ so sánh kết quả mà không để candidate ghi side effect. Điều này giúp phát hiện dữ liệu production chưa có trong corpus.

Dual decode tiêu tốn thêm CPU và cần tránh xử lý nghiệp vụ hai lần. Không chạy hai reader nếu việc đó làm tăng tải vượt khả năng hệ thống hoặc gây side effect.

## 26. Quy trình rollback và migration

Nếu candidate reader bắt đầu từ chối dữ liệu cũ hoặc writer mới tạo output consumer không hiểu:

1. Dừng rollout hoặc rollback về artifact/cấu hình trước nếu còn tương thích.
2. Giữ nguyên payload lỗi và metadata an toàn để tái hiện.
3. Thêm fixture đã ẩn danh vào corpus.
4. Xác định thay đổi đến từ config, Jackson dependency, module hay contract producer.
5. Quyết định sửa candidate reader, thêm compatibility alias, migrate data hoặc version contract.
6. Chạy lại toàn bộ legacy suite và consumer matrix.
7. Chỉ triển khai lại khi release gate pass và có kế hoạch theo dõi.

Nếu writer mới đã phát ra dữ liệu không đọc được bởi release cũ, rollback ứng dụng có thể không đủ. Có thể cần reader hotfix, replay/migration hoặc tiếp tục chạy consumer mới. Vì vậy, forward compatibility và deployment order cần được quyết định trước khi rollout.

## 27. Những lỗi thường gặp

**Chỉ test object mới tạo rồi round-trip bằng mapper mới.** Test này không chứng minh dữ liệu lịch sử đọc được. Dùng fixture thật từ các release cũ.

**Chỉ kiểm tra không có exception.** Deserialize thành công nhưng enum, timestamp, decimal hoặc null có thể bị diễn giải sai. Assert expected semantics.

**Tạo fixture bằng mapper đang kiểm thử.** Producer và test cùng chia sẻ giả định, dễ che lỗi. Giữ fixture độc lập và không tự regenerate.

**Nâng Jackson version và đổi config cùng lúc mà không tách baseline.** Khi test fail khó xác định nguyên nhân. Đo riêng config change và dependency upgrade.

**Giả lập Jackson cũ bằng mapper mới với vài feature cũ.** Đây không tương đương runtime cũ. Dùng process/module/container riêng nếu cần so sánh library version thật.

**Bỏ qua consumer cũ trong rolling deployment.** Writer mới có thể phát field/enum/format mà instance cũ không hiểu. Test chiều new writer → old reader nếu deployment yêu cầu.

**Coi null và absent là giống nhau.** Inclusion policy hoặc default có thể làm thay đổi semantics. Kiểm tra cả key presence và value.

**Không có fixture cho enum cũ hoặc timestamp legacy.** Đây là những trường dễ đổi behavior khi nâng cấp module/config. Giữ fixture đại diện cho mọi token/unit từng phát hành.

**Tăng parser limit để mọi dữ liệu cũ pass mà không điều tra.** Một payload cực lớn có thể là dữ liệu lỗi hoặc rủi ro. Phân loại fixture trước khi thay giới hạn.

**Dùng permissive parsing để tương thích mà không đánh giá security.** Alias/unknown fallback/duplicate handling cần policy rõ; không bật default typing rộng cho dữ liệu không tin cậy.

**Tự cập nhật golden files khi test fail.** Điều này biến thay đổi ngoài ý muốn thành expected output. Review mọi golden change như một contract change.

**Chỉ test mapper tự tạo, bỏ qua mapper Spring production.** Auto-configuration và customizer có thể làm behavior khác. Test bean mapper thực tế và đường HTTP/message/file.

## 28. Checklist triển khai nâng cấp cấu hình Jackson

### Trước khi thay đổi

- [ ] Liệt kê mapper/factory được dùng cho HTTP, message, cache, file và persistence.
- [ ] Ghi lại Jackson Core, Databind và dataformat module versions.
- [ ] Xác định support window của dữ liệu lịch sử và consumer cũ.
- [ ] Thu thập fixture cũ đại diện cho từng event/request type.
- [ ] Ẩn danh dữ liệu thật và ghi nguồn gốc fixture.
- [ ] Chạy baseline trên cấu hình đang production.
- [ ] Lưu expected semantic values và golden output cần thiết.

### Khi thử cấu hình mới

- [ ] Xác nhận candidate mapper chứa đủ module, mix-in và custom serializer.
- [ ] Chạy old fixture → candidate reader.
- [ ] Kiểm tra null, absent, empty, enum, timestamp, decimal và nested values.
- [ ] Kiểm tra unknown properties, duplicate keys và trailing tokens.
- [ ] Kiểm tra parser constraints với dữ liệu lịch sử sát giới hạn.
- [ ] So sánh output mới với golden contract.
- [ ] Chạy new output → old consumer nếu rollout yêu cầu.
- [ ] Tách lỗi do config với lỗi do dependency version.
- [ ] Chạy test qua mapper Spring/broker/file thực tế.

### Trước và sau rollout

- [ ] Chạy legacy suite trong CI làm release gate.
- [ ] Xác nhận thứ tự nâng cấp producer/consumer.
- [ ] Có rollback hoặc migration plan cho dữ liệu đã ghi bằng format mới.
- [ ] Deploy canary và theo dõi decode failure, unknown enum/property, parser limit và dead-letter.
- [ ] Thêm fixture cho mọi lỗi production có thể tái hiện.
- [ ] Chỉ bỏ fixture cũ khi hết support window và có quyết định rõ ràng.

## Kết luận

Chạy bộ kiểm thử dữ liệu cũ trước khi triển khai cấu hình Jackson mới giúp phát hiện breaking change trước khi nó chạm tới file lưu trữ, message queue, API client hoặc consumer cũ. Hãy tạo corpus fixture có version và nguồn gốc rõ ràng; chạy baseline trên mapper hiện tại; đọc toàn bộ fixture bắt buộc bằng candidate reader; kiểm tra semantics chứ không chỉ việc parse thành công; so sánh output writer với golden contract; và test chiều new writer → old reader khi rolling deployment yêu cầu. Tách thay đổi cấu hình khỏi nâng cấp dependency, kiểm tra mapper Spring thực tế, giữ dữ liệu fixture an toàn và đặt legacy suite thành release gate. Sau triển khai, tiếp tục theo dõi decode errors và bổ sung fixture từ các trường hợp production đã được ẩn danh để bộ kiểm thử luôn phản ánh dữ liệu thực tế.

## Tài liệu tham khảo

- [Jackson Databind](https://github.com/FasterXML/jackson-databind) — `ObjectMapper`, `ObjectReader`, `ObjectWriter` và data binding configuration.
- [Jackson Core](https://github.com/FasterXML/jackson-core) — parser/generator features, stream constraints và low-level JSON processing.
- [Jackson Java 8 Modules](https://github.com/FasterXML/jackson-modules-java8) — Java Time module và các module hỗ trợ kiểu Java.
- [Spring Boot JSON support](https://docs.spring.io/spring-boot/reference/features/json.html) — cách Spring Boot cấu hình Jackson và JSON message conversion.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — parameterized tests và tổ chức test suite.
