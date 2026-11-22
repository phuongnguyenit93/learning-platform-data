# Xác minh định dạng đầu ra và khả năng đọc của bên nhận sau nâng cấp

Nâng cấp Jackson có thể thay đổi cách ứng dụng ghi dữ liệu ra wire format, cách ứng dụng đọc dữ liệu cũ và cách Spring cấu hình message converter. Producer có thể serialize thành công nhưng consumer vẫn không đọc được output mới. Ngược lại, consumer mới có thể đọc fixture cũ nhưng producer mới lại phát ra field, kiểu dữ liệu hoặc cấu trúc mà consumer đang chạy chưa hỗ trợ.

Vì vậy, xác minh sau nâng cấp phải kiểm tra cả hai chiều của hợp đồng:

- Định dạng mà ứng dụng thực sự phát ra có đúng contract đã công bố không?
- Những bên nhận đang triển khai có thể đọc định dạng mới không?
- Bên nhận mới có tiếp tục đọc được dữ liệu do producer cũ phát ra không?
- Khác biệt về cấu hình, module, default value hoặc phiên bản có làm thay đổi ý nghĩa dữ liệu không?

Một bài test round-trip bằng cùng một ObjectMapper chưa đủ. Producer và consumer có thể cùng thay đổi theo một cách khiến chúng vẫn hiểu nhau trong test, trong khi hệ thống bên ngoài bị hỏng. Cần dùng fixture đại diện, reader thật của bên nhận, contract tests và ma trận phiên bản trước khi phát hành.

## 1. Phân biệt serialization thành công với compatibility

Serialization thành công chỉ chứng minh Jackson có thể ghi object thành chuỗi hoặc stream. Nó không chứng minh output phù hợp với hợp đồng mà consumer mong đợi.

Ví dụ producer mới ghi:

~~~json
{
  "orderId": "ORD-100",
  "createdAt": "2026-11-12T10:30:00Z",
  "total": 1250.50,
  "status": "PAID"
}
~~~

Consumer cũ có thể mong đợi:

~~~json
{
  "order_id": "ORD-100",
  "created_at": 1794489000,
  "total": "1250.50",
  "status": "paid"
}
~~~

Cả hai tài liệu đều là JSON hợp lệ, nhưng khác tên property, kiểu dữ liệu thời gian, kiểu số và enum wire value. JSON parser chung có thể đọc được cả hai; DTO và logic nghiệp vụ của consumer có thể không.

Cần phân biệt ba lớp:

| Lớp | Câu hỏi xác minh |
|---|---|
| Syntax | Output có phải JSON/XML/YAML/CSV hợp lệ theo định dạng không? |
| Structural contract | Tên field, kiểu, nesting, required/optional và collection có đúng schema không? |
| Semantic compatibility | Consumer có hiểu đúng ý nghĩa giá trị và xử lý đúng nghiệp vụ không? |

Một file có thể qua syntax check nhưng thất bại ở binding. Nó cũng có thể bind thành DTO mà sai ý nghĩa, ví dụ thời điểm bị đổi timezone hoặc enum không còn biểu diễn cùng trạng thái.

## 2. Xác định producer và consumer của từng luồng

Trước khi chạy test, lập danh sách các hệ thống gửi và nhận dữ liệu:

- REST API client và server.
- Service gửi message lên Kafka, RabbitMQ hoặc queue khác.
- Batch job xuất file cho hệ thống đối tác.
- Webhook producer và webhook receiver.
- Cache hoặc object storage lưu JSON để đọc lại sau nhiều ngày.
- Mobile app hoặc desktop client có vòng đời phát hành riêng.
- Hệ thống cũ chỉ nâng cấp theo lịch riêng.

Một endpoint nội bộ vẫn có thể có consumer độc lập. Mobile app, partner integration hoặc job cũ có thể không được deploy cùng backend.

Ghi rõ contract theo từng luồng:

| Thuộc tính | Ví dụ cần ghi nhận |
|---|---|
| Producer | Order service v4 |
| Consumer | Billing adapter v2 |
| Format | JSON UTF-8 |
| Schema/version | order-event v3 |
| Jackson version | Version được đóng gói trong từng ứng dụng |
| Required fields | orderId, status, total |
| Optional fields | note, discount |
| Unknown fields | Ignore hoặc reject |
| Date/time | ISO-8601 UTC |
| Enum | Wire code viết thường |
| Compatibility window | Consumer cũ còn được hỗ trợ đến ngày xác định |

Không nên giả định hai service dùng cùng version Jackson chỉ vì cùng tổ chức. Mỗi ứng dụng có thể có dependency tree, Spring Boot BOM và thời điểm release khác nhau.

## 3. Lập ma trận đọc/ghi giữa các phiên bản

Một cách xác minh hữu ích là kiểm tra writer cũ/mới và reader cũ/mới:

| Writer | Reader | Câu hỏi |
|---|---|---|
| Cũ | Cũ | Baseline hiện tại có hoạt động không? |
| Mới | Cũ | Output mới có tương thích với consumer đang chạy không? |
| Cũ | Mới | Consumer sau nâng cấp có đọc được dữ liệu đã lưu hoặc đang tồn tại không? |
| Mới | Mới | Hai phía mới có hoạt động theo contract dự kiến không? |

Ma trận này đặc biệt quan trọng khi triển khai rolling deployment. Trong một khoảng thời gian, instance cũ và mới có thể cùng tồn tại.

Nếu chỉ chạy new writer với new reader, test có thể bỏ qua lỗi mà consumer cũ gặp phải. Nếu chỉ chạy new reader với fixture mới, test có thể bỏ qua dữ liệu cũ còn nằm trong queue, database hoặc object storage.

Hãy xác định hướng tương thích theo luồng:
- Backward compatibility: consumer mới đọc dữ liệu do producer cũ ghi.
- Forward compatibility: consumer cũ đọc dữ liệu do producer mới ghi.
- Rolling compatibility: hai hướng đều hoạt động trong giai đoạn deploy đồng thời.

Không phải hệ thống nào cũng cần full compatibility. Nhưng quyết định phải được ghi rõ trước khi đổi format.

## 4. Lưu fixture trước nâng cấp làm baseline

Trước khi thay dependency hoặc cấu hình mapper, lưu một bộ fixture được tạo bởi phiên bản production hiện tại.

Fixture nên bao gồm:
- Object đơn giản và object lồng nhau.
- Property null, missing và empty.
- String có Unicode, quote, backslash và newline.
- Số nguyên ở biên và BigDecimal có scale khác nhau.
- Ngày giờ, offset và timezone.
- Enum ở mọi trạng thái đang được sử dụng.
- Collection rỗng, một phần tử và nhiều phần tử.
- Polymorphic subtype nếu có.
- Map có key đặc biệt.
- Payload lớn nhưng vẫn hợp lệ theo contract.
- Message cũ được lưu trong queue hoặc file archive.

Đặt fixture theo luồng và phiên bản contract, ví dụ:

~~~text
src/test/resources/contracts/order-event/
  v2/
    minimal.json
    full.json
    null-and-empty.json
    legacy-status.json
  v3/
    minimal.json
    full.json
    timezone-edge.json
~~~

Không dùng dữ liệu production chứa thông tin cá nhân hoặc bí mật làm fixture. Tạo dữ liệu synthetic có cùng cấu trúc và đặc điểm biên.

Mỗi fixture cần ghi chú nguồn tạo, contract version, writer version và ý nghĩa các giá trị quan trọng. Nếu không biết fixture được tạo bởi mapper nào, khó xác định nó đại diện cho producer nào.

## 5. So sánh output theo semantic JSON khi byte không phải contract

JSON object không yêu cầu thứ tự property có ý nghĩa. Hai output sau thường tương đương về cấu trúc:

~~~json
{"id":"A-1","status":"NEW"}
~~~

~~~json
{"status":"NEW","id":"A-1"}
~~~

Nếu consumer parse JSON thông thường, test nên so sánh tree hoặc object đã deserialize thay vì so sánh raw string:

~~~java
JsonNode expected = mapper.readTree(expectedJson);
JsonNode actual = mapper.readTree(actualJson);

assertEquals(expected, actual);
~~~

Cách này bỏ qua whitespace và thứ tự field object, nhưng vẫn kiểm tra kiểu node và giá trị. Array order vẫn có ý nghĩa và được giữ trong phép so sánh tree.

Không dùng semantic comparison nếu byte output thực sự là contract, ví dụ:
- Payload được ký trên raw bytes.
- Hash được tính trên chuỗi JSON chính xác.
- Consumer dùng canonical JSON theo một chuẩn đã thống nhất.
- File snapshot hoặc downstream tool phụ thuộc format chính xác.
- CSV/XML output phải tuân thủ quy ước byte hoặc line ending cụ thể.

Trong các trường hợp đó, cần canonicalization hoặc byte-level test được định nghĩa rõ. Đừng thêm property order chỉ để làm snapshot xanh nếu thứ tự property không phải yêu cầu của wire contract.

## 6. Golden-file test với ObjectMapper

Golden-file test so sánh output mới với fixture được chấp nhận. Nó hữu ích để phát hiện thay đổi vô tình trong serialization.

Ví dụ:

~~~java
class OrderSerializationContractTest {

    private final ObjectMapper mapper = productionObjectMapper();

    @Test
    void writesTheExpectedOrderContract() throws Exception {
        OrderResponse response = sampleOrder();

        String actualJson = mapper.writeValueAsString(response);

        JsonNode expected = mapper.readTree(
            resource("contracts/order-event/v3/full.json")
        );
        JsonNode actual = mapper.readTree(actualJson);

        assertEquals(expected, actual);
    }
}
~~~

Fixture cần được review khi thay đổi có chủ đích. Không tự động ghi đè expected file mỗi khi test thất bại, vì điều đó biến test thành công cụ chấp nhận mọi thay đổi.

Khi diff xuất hiện, phân loại:
- Thay đổi chỉ về whitespace hoặc property order.
- Thay đổi tên field.
- Thay đổi JSON node type.
- Thay đổi null inclusion.
- Thay đổi date/time format.
- Thay đổi enum hoặc polymorphic metadata.
- Thay đổi giá trị mặc định hoặc custom serializer.

Golden test phát hiện khác biệt; người sở hữu contract quyết định khác biệt đó có được phép hay không.

## 7. Kiểm tra reader thật của bên nhận

Producer test không thể thay thế consumer test. Hãy lấy output mới từ producer rồi đưa vào deserializer và DTO của consumer.

Nếu consumer là một ứng dụng Java riêng:
1. Dùng dependency/configuration thực tế của consumer.
2. Load fixture output mới.
3. Deserialize vào DTO consumer.
4. Chạy validation và bước chuyển đổi tiếp theo.
5. Assert các giá trị nghiệp vụ quan trọng.

Ví dụ:

~~~java
String producerJson = producerMapper.writeValueAsString(event);

ConsumerOrderEvent received =
    consumerMapper.readValue(producerJson, ConsumerOrderEvent.class);

assertEquals(event.orderId(), received.orderId());
assertEquals(event.total(), received.total());
assertEquals(ConsumerStatus.PAID, received.status());
~~~

Trong integration test thực tế, producerMapper và consumerMapper phải được tạo từ cấu hình độc lập tương ứng với từng ứng dụng. Không chia sẻ cùng một ObjectMapper hoặc DTO chỉ để test dễ hơn nếu production có hai codebase khác nhau.

Nếu consumer không phải Java, chạy contract test qua parser/schema hoặc test harness của chính consumer. Việc một ObjectMapper khác đọc được JSON không chứng minh Go, Python, JavaScript hoặc hệ thống đối tác đọc được cùng contract.

## 8. Kiểm tra schema và required/optional fields

JSON Schema hoặc OpenAPI có thể mô tả:
- Tên property.
- Kiểu dữ liệu.
- Required fields.
- Nullable fields.
- Enum values.
- Format của date/time.
- Min/max, pattern và collection constraints.
- Chính sách property bổ sung.

Ví dụ schema rút gọn:

~~~json
{
  "type": "object",
  "required": ["orderId", "status", "total"],
  "properties": {
    "orderId": {"type": "string"},
    "status": {
      "type": "string",
      "enum": ["NEW", "PAID", "CANCELLED"]
    },
    "total": {"type": "number"},
    "createdAt": {
      "type": "string",
      "format": "date-time"
    }
  },
  "additionalProperties": false
}
~~~

Schema là một phần của contract, không phải bảo đảm toàn bộ semantics. Ví dụ schema có thể chấp nhận chuỗi date-time nhưng không kiểm tra timezone có được business yêu cầu hay không.

Cần xác định additionalProperties:
- false: consumer reject field mới.
- true hoặc không khai báo: consumer có thể chấp nhận field lạ tùy parser.
- Schema mở có thể hỗ trợ producer thêm field mà consumer cũ không cần hiểu.

Không bật strict unknown-property policy một cách tùy tiện nếu producer và consumer deploy độc lập. Ngược lại, nếu typo field phải bị từ chối, strictness có thể là một phần quan trọng của contract.

## 9. Kiểm tra thay đổi tên property và naming strategy

Nâng cấp hoặc đổi cấu hình có thể thay đổi tên wire:
- orderId thành order_id.
- createdAt thành created_at.
- Field được rename trong DTO.
- @JsonProperty hoặc mix-in thay đổi.
- Property naming strategy được áp dụng khác.
- Alias chỉ hỗ trợ đọc nhưng writer phát tên canonical mới.

Hãy test tên JSON thực tế, không chỉ kiểm tra field Java:

~~~java
JsonNode tree = mapper.readTree(mapper.writeValueAsString(response));

assertTrue(tree.has("order_id"));
assertFalse(tree.has("orderId"));
~~~

Đối với rename có kế hoạch, consumer có thể cần đọc cả tên cũ và tên mới trong một giai đoạn:

~~~java
public record OrderRequest(
    @JsonProperty("order_id")
    @JsonAlias("orderId")
    String orderId
) {}
~~~

@JsonAlias hỗ trợ tên đầu vào thay thế; nó không khiến serializer phát đồng thời cả hai tên. Nếu writer mới chỉ phát tên mới, consumer cũ vẫn cần được nâng cấp trước hoặc producer phải giữ wire format cũ cho đến khi hết thời gian tương thích.

Không xem việc Java field vẫn giữ tên cũ là bằng chứng wire name không đổi.

## 10. Kiểm tra null, missing và inclusion policy

Các cấu hình như @JsonInclude hoặc global inclusion policy có thể làm thay đổi output:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record CustomerResponse(
    String id,
    String nickname,
    List<String> tags
) {}
~~~

Nếu nickname null, writer có thể bỏ property. Consumer cũ có thể phân biệt:
- Property không xuất hiện.
- Property xuất hiện với null.
- Property xuất hiện với chuỗi rỗng.

Một số consumer dùng missing để giữ giá trị cũ khi patch; explicit null để xóa giá trị. Nếu writer đổi từ explicit null sang omit, ý nghĩa nghiệp vụ có thể thay đổi dù cả hai JSON đều hợp lệ.

Tạo fixture cho từng trạng thái và chạy qua reader thật. Đừng chỉ test object có tất cả field khác null.

Với primitive như int hoặc boolean, missing/null có thể dẫn đến default value hoặc lỗi tùy constructor và feature. Nếu cần phân biệt missing với zero/false, dùng wrapper, tri-state model hoặc DTO riêng cho patch semantics.

## 11. Kiểm tra date/time và timezone

Date/time là nguồn incompatibility phổ biến vì cùng một thời điểm có thể được biểu diễn theo nhiều dạng.

Ví dụ:

~~~json
{"createdAt":"2026-11-12T10:30:00Z"}
~~~

và:

~~~json
{"createdAt":1794489000}
~~~

Một dạng là chuỗi ISO-8601; dạng kia là số timestamp. Nếu consumer mong string mà producer chuyển sang timestamp, binding có thể thất bại hoặc bị hiểu sai đơn vị.

Với Java Time, kiểm tra:
- JavaTimeModule có được đăng ký trong mapper thực tế không.
- WRITE_DATES_AS_TIMESTAMPS có bật không.
- Precision có bị làm tròn đến milliseconds không.
- Offset có được giữ hay chuyển sang UTC.
- LocalDateTime có bị hiểu nhầm thành instant không.
- ZonedDateTime có giữ ZoneId nếu contract yêu cầu không.
- Consumer hỗ trợ format và độ chính xác đó không.

Test các giá trị ở biên ngày, leap day, offset khác UTC và fractional seconds. Nếu business chỉ cần instant, so sánh instant. Nếu zone name là dữ liệu nghiệp vụ, kiểm tra ZoneId riêng.

Không dùng thời gian hiện tại trong fixture vì output sẽ thay đổi theo lần chạy. Dùng giá trị cố định và timezone rõ ràng.

## 12. Kiểm tra number, BigDecimal và precision

Producer có thể ghi số theo dạng JSON number hoặc string. Hai kiểu không tương đương với mọi consumer:

~~~json
{"total":1250.50}
~~~

~~~json
{"total":"1250.50"}
~~~

Một số JavaScript consumer dùng number IEEE-754 và có thể mất precision với integer lớn hoặc decimal nhạy cảm. Consumer Java có thể dùng BigDecimal. Nếu tiền cần chính xác, contract phải quy định kiểu biểu diễn và cách consumer parse.

Kiểm tra:
- JSON node type vẫn là number/string theo contract.
- Integer vượt giới hạn an toàn của consumer.
- BigDecimal precision và scale.
- Scientific notation có được chấp nhận không.
- Zero và negative zero nếu liên quan.
- Giá trị sát min/max.
- Làm tròn có xảy ra ở serializer/deserializer hay không.

Không chỉ so sánh double. Với tiền và số chính xác, dùng BigDecimal và assert theo invariant đã thống nhất. Nếu output được ký hoặc so sánh byte, định dạng số và canonicalization cần được xác định riêng.

## 13. Kiểm tra enum và giá trị trạng thái

Enum có thể được ghi theo:
- Tên constant, ví dụ PAID.
- Wire value riêng, ví dụ paid.
- Ordinal number, nếu cấu hình không phù hợp.
- @JsonValue hoặc custom serializer.

Ordinal rất nguy hiểm cho contract bền vững: thêm hoặc sắp xếp lại enum constant có thể làm cùng số biểu diễn trạng thái khác. Với integration lâu dài, dùng wire string ổn định.

Ví dụ:

~~~java
public enum OrderStatus {
    NEW("new"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String wireValue;

    OrderStatus(String wireValue) {
        this.wireValue = wireValue;
    }

    @JsonValue
    public String wireValue() {
        return wireValue;
    }
}
~~~

Consumer cũ có thể reject một enum value mới. Trước khi thêm trạng thái, xác minh mọi consumer có thể:
- Nhận giá trị mới.
- Lưu hoặc chuyển tiếp giá trị mà không làm mất.
- Có fallback hợp lý nếu không thực hiện logic riêng.
- Không ánh xạ unknown value thành một trạng thái nghiệp vụ sai.

Nếu forward compatibility cần thiết, cân nhắc model giữ raw string hoặc UNKNOWN state có semantics rõ. Không tự ánh xạ mọi giá trị lạ thành một trạng thái hợp lệ như NEW.

## 14. Kiểm tra polymorphic type metadata

Với object có nhiều subtype, Jackson có thể ghi type discriminator:

~~~json
{
  "type": "card",
  "lastFour": "4242"
}
~~~

Thay đổi @JsonTypeInfo, @JsonSubTypes, property discriminator hoặc Id strategy có thể làm consumer không tạo đúng subtype.

Cần test:
- Mỗi subtype được phát đúng discriminator.
- Consumer cũ nhận được subtype đang hỗ trợ.
- Consumer mới đọc được discriminator cũ.
- Unknown subtype được xử lý theo policy rõ ràng.
- Metadata không bị đổi tên hoặc chuyển vị trí theo cách consumer không hiểu.

Không bật default typing không giới hạn để giải quyết vấn đề compatibility. Dùng subtype allowlist và type ID ổn định, không phụ thuộc tên class Java hoặc package.

Nếu producer thêm subtype mới mà consumer cũ không biết, đây thường là breaking change nếu consumer phải deserialize vào sealed hierarchy. Có thể cần versioned event, fallback model hoặc triển khai consumer trước producer.

## 15. Kiểm tra unknown fields và trailing content ở consumer

Khả năng đọc của bên nhận còn phụ thuộc vào deserialization features.

Các câu hỏi cần kiểm tra:
- Consumer bật hay tắt FAIL_ON_UNKNOWN_PROPERTIES?
- Unknown fields được bỏ qua hay giữ trong extension map?
- Duplicate JSON keys bị reject hay key sau ghi đè key trước?
- Có chấp nhận scalar coercion như chuỗi "42" thành integer không?
- Có chấp nhận null cho primitive không?
- Có yêu cầu token root đúng shape không?
- Có reject trailing tokens sau một JSON value không?
- Có giới hạn nesting, string và number riêng không?

Một producer có thể phát JSON hợp lệ nhưng consumer reject vì strict unknown property. Hoặc consumer đọc được nhưng coercion khiến dữ liệu bị đổi kiểu.

Không dựa vào default feature của Jackson. Hãy ghi rõ cấu hình reader và kiểm tra nó bằng test. Default có thể thay đổi theo Spring Boot/Jackson version hoặc customizer của ứng dụng.

## 16. Kiểm tra mapper thực sự được Spring sử dụng

Một test tạo new ObjectMapper có thể khác mapper mà Spring MVC dùng trong production. Spring Boot có thể đăng ký module, naming strategy, customizer, mix-in, inclusion policy và message converter qua auto-configuration.

Vì vậy, test nên lấy mapper từ application context hoặc cấu hình builder dùng chung:

~~~java
@SpringBootTest
class OrderJsonContractTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void writesTheConfiguredWireFormat() throws Exception {
        String json = objectMapper.writeValueAsString(sampleOrder());

        JsonNode tree = objectMapper.readTree(json);
        assertEquals("ORD-100", tree.path("orderId").asText());
    }
}
~~~

Nếu ứng dụng có nhiều mapper hoặc converter theo media type, test từng mapper liên quan. Một endpoint XML có thể dùng XmlMapper, trong khi JSON endpoint dùng ObjectMapper.

Không tạo mapper test riêng rồi kết luận production output tương thích. Hãy kiểm tra đúng bean, converter và configuration path đang phục vụ request/message thật.

## 17. Consumer-driven contract testing

Consumer-driven contract testing bắt đầu từ nhu cầu thực tế của bên nhận. Consumer mô tả request/response hoặc event shape mà nó cần; producer chạy verification để chứng minh output đáp ứng các kỳ vọng đó.

Một contract nên nêu:
- Required property và kiểu.
- Optional property.
- Enum values được chấp nhận.
- Date/time format và timezone semantics.
- Quy tắc null/missing.
- Unknown property behavior.
- Polymorphic subtype.
- Ví dụ payload thành công và lỗi.
- Version contract và compatibility window.

Contract tests giúp phát hiện producer vô tình đổi tên field hoặc kiểu dữ liệu trước khi deploy. Tuy nhiên, chúng chỉ bao phủ interaction mà consumer đã khai báo. Vẫn cần fixture và test nghiệp vụ cho những semantics không thể biểu đạt trong schema.

Nếu dùng công cụ contract như Pact hoặc OpenAPI-based validation, hãy đặt contract artifact trong pipeline và version hóa nó. Không xem việc build thành công là bằng chứng contract đã được verify nếu bước verification chưa chạy.

## 18. Kiểm tra khả năng đọc ở nhiều ngôn ngữ

Nếu consumer không phải Java, test bằng ObjectMapper thứ hai vẫn không đủ.

Các khác biệt thường gặp:
- JavaScript number không biểu diễn chính xác mọi integer 64-bit.
- Python có thể phân biệt int/float theo cách khác.
- Go cần struct tags và có thể xử lý unknown fields theo cấu hình decoder.
- Một số parser phân biệt null, missing và zero value khác nhau.
- Date/time library có thể yêu cầu RFC 3339 hoặc timezone rõ.
- Enum parser có thể phân biệt chữ hoa/chữ thường.
- Unicode normalization có thể khác ở tầng ứng dụng.

Dùng parser hoặc DTO thật của consumer trong contract test. Nếu không thể chạy consumer trong CI producer, có thể dùng test harness hoặc schema validator tương ứng và giữ consumer integration suite chạy trong pipeline riêng.

Đừng chỉ kiểm tra JSON parse thành generic map. Generic parser không xác nhận field type, required semantics hay domain conversion của consumer.

## 19. Nâng cấp Jackson và Spring Boot theo dependency alignment

Spring Boot quản lý nhiều dependency qua BOM. Nâng cấp Jackson độc lập có thể tạo ra một tập artifact không đồng nhất nếu một số module vẫn ở version khác.

Trước khi phát hành:
- Kiểm tra dependency tree thực tế.
- Xác nhận jackson-core, jackson-annotations, jackson-databind và các dataformat modules tương thích.
- Kiểm tra module Java Time, parameter names, Kotlin hoặc module custom.
- Kiểm tra Spring Boot và Spring Framework version hỗ trợ cấu hình đang dùng.
- Kiểm tra test runtime và packaged runtime có cùng dependency set.
- Xem release notes cho thay đổi behavior và API deprecation.

Nếu Spring Boot BOM quản lý Jackson, ưu tiên nâng Boot theo lộ trình được hỗ trợ hoặc override có chủ đích theo hướng dẫn tương thích. Tránh pin một artifact riêng lẻ khiến dependency graph bị trộn version.

Một build dependency resolution thành công không chứng minh wire output không đổi. Dependency alignment là điều kiện nền; contract tests mới kiểm tra hành vi.

## 20. Kiểm tra dataformat modules ngoài JSON

Nếu ứng dụng dùng XML, YAML hoặc CSV, mỗi module có contract riêng.

| Định dạng | Các thay đổi cần xác minh |
|---|---|
| JSON | Property name, null, date, number, enum, type metadata |
| XML | Root, element/attribute, namespace URI, wrapper, text, nil |
| YAML | Scalar typing, quote/block style, null, document markers |
| CSV | Delimiter, quote/escape, header, column order, line ending, null marker |

Với XML, không so sánh prefix namespace như thể nó luôn có ý nghĩa. Kiểm tra namespace URI và local name. Với CSV, dùng parser CSV thật để kiểm tra số cột và giá trị field, bao gồm quoted multiline. Với YAML, kiểm tra giá trị semantic sau parse thay vì giả định writer giữ nguyên quote style.

Nếu output được tiêu thụ bởi tool nhạy với formatting, line ending hoặc prefix, hãy ghi rõ đó là yêu cầu thực tế và thêm byte/text-level test tương ứng.

## 21. Kiểm tra dữ liệu tồn tại lâu dài

Compatibility không chỉ áp dụng cho request mới. Dữ liệu được ghi bởi phiên bản cũ có thể còn được đọc sau nhiều tháng hoặc nhiều năm:
- JSON lưu trong database column.
- Event nằm trong queue hoặc dead-letter queue.
- File export trong object storage.
- Cache snapshot.
- Audit log hoặc archive.
- Job retry đọc lại payload cũ.

Nâng cấp reader cần thử với fixture đại diện cho mọi schema version còn được hỗ trợ. Nếu consumer mới chỉ đọc dữ liệu mới, job retry hoặc replay có thể thất bại.

Có thể thêm trường schema version hoặc event version trong payload/envelope:

~~~json
{
  "eventType": "OrderPaid",
  "schemaVersion": 3,
  "payload": {
    "orderId": "ORD-100",
    "status": "paid"
  }
}
~~~

Version giúp chọn deserializer hoặc migration path. Không nên thêm version field tùy tiện nếu contract hiện tại chưa có cơ chế tương thích; cần có chiến lược cho dữ liệu không chứa version.

## 22. Dùng migration adapter khi wire format thay đổi có chủ đích

Nếu cấu trúc cũ và mới khác nhau, adapter có thể tách legacy wire DTO khỏi domain model:

~~~java
record LegacyOrderPayload(
    String order_id,
    String state,
    BigDecimal total
) {}

record CurrentOrderPayload(
    String orderId,
    OrderStatus status,
    BigDecimal total
) {}

Order toDomain(LegacyOrderPayload legacy) {
    return new Order(
        legacy.order_id(),
        OrderStatus.fromLegacy(legacy.state()),
        legacy.total()
    );
}
~~~

Adapter làm rõ chuyển đổi và cho phép giữ hỗ trợ payload cũ trong một thời gian. Tránh nhồi nhiều nhánh legacy vào một DTO nếu nó khiến null/default semantics khó hiểu.

Có thể chọn adapter dựa trên schema version hoặc endpoint version. Với message queue, version có thể nằm trong envelope. Với API, version có thể nằm trong URL/header hoặc content type theo contract.

Đừng tự đoán phiên bản từ việc field nào đang xuất hiện nếu hai schema có thể giao nhau hoặc tạo ambiguity.

## 23. Rolling deployment và thứ tự nâng cấp

Nếu producer và consumer deploy độc lập, thứ tự phát hành quyết định compatibility.

Một chiến lược thường dùng khi thêm field:
1. Nâng consumer để chấp nhận field mới hoặc bỏ qua unknown field.
2. Xác nhận tất cả instance consumer đã cập nhật.
3. Nâng producer để phát field mới.
4. Theo dõi lỗi deserialize và business metrics.
5. Chỉ bỏ field cũ sau khi không còn consumer cần nó.

Với rename field:
1. Consumer mới đọc cả tên cũ và tên mới.
2. Deploy consumer mới trước.
3. Producer chuyển sang tên mới hoặc phát cả hai trong giai đoạn chuyển tiếp nếu contract cho phép.
4. Theo dõi reader usage.
5. Gỡ alias cũ trong release sau khi hết thời gian tương thích.

Với breaking change, cân nhắc versioned endpoint/topic/schema thay vì thay đổi đột ngột trên một channel đang có consumer cũ.

## 24. Quan sát lỗi sau khi phát hành

Contract test giảm rủi ro nhưng không thay thế monitoring production.

Theo dõi:
- Tỷ lệ deserialize failure theo consumer và schema version.
- HTTP 4xx do invalid request.
- Message retry, dead-letter queue và poison message.
- Error rate theo Jackson exception category.
- Tỷ lệ unknown enum/type discriminator.
- Thời gian parse và allocation/GC nếu payload thay đổi lớn.
- Consumer lag và retry count.
- Số payload được xử lý bởi legacy adapter.

Không log raw payload hoặc rejected value chỉ để debug. Gắn request ID/message ID, producer version, schema version và error code đã chuẩn hóa. ID không nên làm metric label có cardinality cao; có thể lưu trong log/trace.

Thiết lập ngưỡng cảnh báo cho regression sau deploy, ví dụ tăng đột biến mapping failure hoặc dead-letter count. Nếu lỗi chỉ xuất hiện ở một consumer version, dữ liệu đó giúp xác định compatibility direction bị phá vỡ.

## 25. Quy trình rollback cần được kiểm chứng

Rollback binary không nhất thiết khôi phục compatibility nếu producer mới đã ghi payload theo schema mới vào queue hoặc database. Consumer cũ có thể tiếp tục gặp payload mới sau rollback.

Trước khi phát hành, hỏi:
- Producer mới có phát field/enum/type mới mà consumer cũ không hiểu không?
- Payload mới có được lưu lâu dài không?
- Consumer cũ có thể đọc dữ liệu mới trong queue sau rollback không?
- Có thể tạm dừng producer hoặc route về schema cũ không?
- Có adapter để đọc cả hai schema không?
- Có cần drain queue trước khi rollback không?

Nếu thay đổi chỉ là internal mapper performance và wire contract không đổi, rollback đơn giản hơn. Nếu wire format thay đổi, cần kế hoạch dữ liệu và consumer tương ứng.

Không triển khai một thay đổi phá compatibility với giả định chỉ cần rollback service mà chưa kiểm tra dữ liệu đã được phát ra.

## 26. Checklist kiểm chứng trước khi nâng cấp

**Baseline**
- [ ] Lưu fixture được tạo bởi phiên bản production hiện tại.
- [ ] Ghi rõ writer/reader version và contract version.
- [ ] Liệt kê mọi consumer đang hoạt động.
- [ ] Xác định thời gian dữ liệu cũ còn có thể được replay.

**Output**
- [ ] Serialize bằng ObjectMapper và converter thực tế.
- [ ] So sánh output theo semantic JSON nếu byte không phải contract.
- [ ] Kiểm tra property name, type, null và collection.
- [ ] Kiểm tra date/time, number precision và enum wire values.
- [ ] Kiểm tra polymorphic discriminator.
- [ ] Kiểm tra XML/YAML/CSV nếu có sử dụng.

**Consumer**
- [ ] Đọc output mới bằng reader thật của consumer.
- [ ] Đọc fixture cũ bằng reader mới.
- [ ] Chạy matrix old/new writer và old/new reader.
- [ ] Xác nhận unknown-field, coercion và strictness policy.
- [ ] Kiểm tra domain conversion, không chỉ parse thành công.

**Release**
- [ ] Contract tests chạy trong CI.
- [ ] Dependency versions được alignment.
- [ ] Rolling deployment có thứ tự rõ.
- [ ] Monitoring và alert được chuẩn bị.
- [ ] Rollback plan xét đến payload đã phát ra và đang lưu.

## 27. Ví dụ pipeline contract test

Một pipeline kiểm tra có thể được tổ chức như sau:

~~~text
Fixture corpus
     |
     v
New producer mapper
     |
     v
Output format / schema validation
     |
     +----------------------+
     |                      |
     v                      v
Old consumer reader    New consumer reader
     |                      |
     v                      v
Domain assertions      Domain assertions
     |                      |
     +----------+-----------+
                |
                v
Compatibility report
                |
                v
Release gate
~~~

Test code có thể gom fixture và reader theo version:

~~~java
@ParameterizedTest
@MethodSource("contractFixtures")
void newReaderAcceptsSupportedLegacyPayload(
        String fixtureName,
        String json) throws Exception {

    OrderEvent event =
        newReader.readValue(json, OrderEvent.class);

    assertNotNull(event.orderId());
    assertNotNull(event.status());
}
~~~

Một test khác dùng new producer output với old reader:

~~~java
@Test
void newProducerRemainsReadableByOldConsumer() throws Exception {
    String json = newProducer.writeValueAsString(sampleEvent());

    LegacyOrderEvent received =
        oldConsumer.readValue(json, LegacyOrderEvent.class);

    assertEquals("ORD-100", received.orderId());
}
~~~

Đây chỉ là cấu trúc minh họa. Trong project thực tế, reader cũ nên được đóng gói từ artifact/version tương ứng hoặc chạy trong consumer test harness riêng. Không sao chép DTO cũ vào module test rồi gọi đó là consumer thật nếu DTO/configuration có thể lệch với binary production.

## 28. Khi nào cần version hóa contract?

Không phải mọi thay đổi output đều cần tăng schema version. Thay đổi không ảnh hưởng semantic contract như whitespace thường không cần. Nhưng cần cân nhắc version khi:
- Đổi tên field mà consumer cũ không có alias.
- Đổi node type, ví dụ number thành string.
- Đổi date format hoặc timezone semantics.
- Đổi enum wire values hoặc thêm subtype mà reader cũ reject.
- Đổi nesting hoặc collection representation.
- Thay đổi null/missing semantics.
- Xóa field bắt buộc.
- Đổi cách giải thích một giá trị hiện có.

Nếu chỉ thêm optional field và mọi consumer chấp nhận unknown property, có thể không cần version mới. Nhưng điều này phải được xác minh bằng reader thật, không dựa trên giả định.

Schema version nên đại diện cho contract của payload, không phải version của Jackson library. Nâng Jackson từ một bản patch sang bản khác mà không đổi wire contract không tự động yêu cầu tăng schema version.

## Kết luận

Xác minh sau nâng cấp phải chứng minh định dạng output vẫn đúng hợp đồng và các bên nhận thực sự đọc được nó. Round-trip với cùng ObjectMapper chỉ kiểm tra tính đối xứng của một mapper; nó không đại diện cho consumer độc lập hoặc dữ liệu cũ đang tồn tại. Hãy lưu fixture baseline, so sánh output theo semantics phù hợp, chạy reader thật của consumer và kiểm tra ma trận old/new writer với old/new reader.

Đặc biệt chú ý tên property, null/missing, date/time, precision số, enum, polymorphic metadata, unknown fields và cấu hình mapper do Spring Boot cung cấp. Với triển khai rolling, nâng consumer trước khi producer phát format mới; theo dõi deserialize failure và chuẩn bị rollback có xét đến payload đã được ghi. Khi những kiểm tra này trở thành release gate, nâng cấp Jackson sẽ có bằng chứng compatibility cụ thể thay vì chỉ dựa vào việc ứng dụng khởi động và serialize thành công.

