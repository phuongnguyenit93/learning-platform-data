# Kiểm thử event payload

Event payload là dữ liệu được công bố qua application event hoặc được serialize để gửi sang module, broker hay ứng dụng khác. Payload là một phần của hợp đồng tích hợp: producer quyết định dữ liệu nào được gửi, kiểu dữ liệu và ý nghĩa của từng trường; consumer dựa vào hợp đồng đó để deserialize và thực hiện nghiệp vụ.

Một bài kiểm thử payload tốt cần xác minh nhiều lớp. Mapping phải chuyển đúng dữ liệu domain sang DTO công bố; serializer phải tạo wire format ổn định; consumer phải đọc được payload theo schema đã thống nhất; dữ liệu thiếu hoặc sai phải bị xử lý có kiểm soát; thay đổi schema phải giữ tương thích với consumer đang hoạt động.

Trong Spring Modulith, application events giúp module giao tiếp qua hợp đồng nghiệp vụ và Event Publication Registry theo dõi publication tới listener. Kiểm thử event payload cần xác minh nội dung thực sự đi qua ranh giới đó. Kiểm tra rằng publisher đã được gọi hoặc listener đã chạy chưa đủ để chứng minh payload đúng.

## 1. Kiểm thử payload nhằm bảo vệ điều gì?

Một event có thể được phát thành công nhưng vẫn gây lỗi ở consumer nếu payload sai kiểu, sai ý nghĩa hoặc thiếu trường bắt buộc. Ví dụ, producer gửi tổng tiền dưới dạng floating point trong khi consumer yêu cầu decimal chính xác; producer đổi tên enum; timestamp mất timezone; hoặc một entity nội bộ vô tình được serialize cùng các quan hệ không cần công bố.

Các mục tiêu kiểm thử chính:

| Mục tiêu | Câu hỏi cần trả lời |
|---|---|
| Mapping | Giá trị domain có được chuyển đúng sang event DTO không? |
| Serialization | Payload có đúng định dạng wire và kiểu dữ liệu đã công bố không? |
| Deserialization | Consumer có đọc được payload mẫu và giá trị có giữ nguyên không? |
| Validation | Trường bắt buộc, miền giá trị và invariant có được kiểm tra không? |
| Contract compatibility | Consumer cũ có tiếp tục đọc payload mới không? Payload cũ có còn được hỗ trợ không? |
| Metadata | Event ID, type, version, occurredAt và correlation ID có chính xác không? |
| Error handling | Payload lỗi được từ chối, cách ly hoặc dead-letter đúng chính sách không? |
| Data minimization | Payload không chứa trường nội bộ hoặc dữ liệu nhạy cảm ngoài phạm vi không? |

Nên kiểm thử ở nhiều ranh giới thay vì gom mọi thứ vào một test lớn. Unit test cho mapping chạy nhanh và dễ định vị lỗi; serialization test kiểm tra wire format; contract test bảo vệ producer-consumer; integration test xác nhận cấu hình thực tế của Spring và transport.

## 2. Tách domain event khỏi payload công bố

Domain model và payload công bố có vòng đời khác nhau. Entity có thể thay đổi theo cấu trúc database, trong khi event contract cần ổn định để consumer độc lập có thể đọc cả message mới lẫn message còn tồn trong broker.

Ví dụ domain event và DTO công bố:

~~~java
public record OrderPaid(
    UUID eventId,
    UUID orderId,
    BigDecimal total,
    String currency,
    Instant occurredAt
) {}

public record OrderPaidPayload(
    String eventId,
    String orderNumber,
    String total,
    String currency,
    Instant occurredAt,
    int schemaVersion
) {}
~~~

Trong ví dụ, payload dùng chuỗi cho total để bảo toàn decimal chính xác khi consumer ở ngôn ngữ khác đọc JSON. Event ID được chuyển thành chuỗi UUID; thời gian dùng Instant để serialize theo định dạng thời gian có timezone rõ ràng.

Mapper chuyển domain event sang payload:

~~~java
@Component
class OrderPaidPayloadMapper {

    OrderPaidPayload map(OrderPaid event, String orderNumber) {
        return new OrderPaidPayload(
            event.eventId().toString(),
            orderNumber,
            event.total().toPlainString(),
            event.currency(),
            event.occurredAt(),
            1
        );
    }
}
~~~

Mapper cần là nơi có chủ đích để chuẩn hóa giá trị, lọc trường và đặt version. Không serialize trực tiếp entity JPA chỉ vì Jackson có thể đọc getter. Entity có thể kéo theo quan hệ lazy, vòng tham chiếu, trường nội bộ hoặc thay đổi schema persistence không thuộc hợp đồng tích hợp.

## 3. Unit test cho mapping

Mapping test xác minh từng trường được chuyển đúng và không làm thay đổi ý nghĩa nghiệp vụ. Test nên dùng dữ liệu có thể phát hiện lỗi như số 0 ở đầu mã đơn, decimal có nhiều chữ số, thời điểm có UTC và mã enum ổn định.

Ví dụ:

~~~java
class OrderPaidPayloadMapperTest {

    private final OrderPaidPayloadMapper mapper =
        new OrderPaidPayloadMapper();

    @Test
    void mapsDomainEventToPublishedPayload() {
        var event = new OrderPaid(
            UUID.fromString("7d6b0d85-8a2e-4d2c-9c2d-2c4b7b1a9120"),
            UUID.fromString("8a4d3e2f-5b6c-4d7e-9f10-123456789abc"),
            new BigDecimal("125000.50"),
            "VND",
            Instant.parse("2026-11-25T10:15:30Z")
        );

        var payload = mapper.map(event, "ORD-00042");

        assertThat(payload.eventId())
            .isEqualTo("7d6b0d85-8a2e-4d2c-9c2d-2c4b7b1a9120");
        assertThat(payload.orderNumber()).isEqualTo("ORD-00042");
        assertThat(payload.total()).isEqualTo("125000.50");
        assertThat(payload.currency()).isEqualTo("VND");
        assertThat(payload.occurredAt()).isEqualTo(event.occurredAt());
        assertThat(payload.schemaVersion()).isEqualTo(1);
    }
}
~~~

Test kiểm tra cả giá trị lẫn biểu diễn. Với tiền, so sánh chuỗi decimal nếu contract quy định giữ scale; nếu domain chỉ quan tâm giá trị số, có thể so sánh bằng BigDecimal theo quy tắc nghiệp vụ. Với mã định danh, phải kiểm tra chuỗi được giữ nguyên, bao gồm số 0 đầu và ký tự phân cách.

Nên có test chứng minh payload không chứa trường không được công bố. Tuy nhiên, kiểm tra danh sách field chính xác cần được cập nhật có chủ đích khi schema thay đổi. Mục tiêu là ngăn lộ dữ liệu nội bộ, không khóa mọi mở rộng tương thích của contract.

## 4. Kiểm thử JSON serialization

Mapping đúng chưa đảm bảo serializer tạo payload đúng. Serialization test cần dùng cùng cấu hình ObjectMapper hoặc serializer thực tế mà ứng dụng dùng ở runtime, bao gồm Java Time module, naming strategy, enum policy, null handling và custom serializer.

Spring Boot hỗ trợ slice test với @JsonTest và JacksonTester. Ví dụ:

~~~java
@JsonTest
class OrderPaidPayloadJsonTest {

    @Autowired
    JacksonTester<OrderPaidPayload> json;

    @Test
    void writesStableWireValues() throws Exception {
        var payload = new OrderPaidPayload(
            "7d6b0d85-8a2e-4d2c-9c2d-2c4b7b1a9120",
            "ORD-00042",
            "125000.50",
            "VND",
            Instant.parse("2026-11-25T10:15:30Z"),
            1
        );

        var content = json.write(payload);

        assertThat(content)
            .extractingJsonPathStringValue("$.eventId")
            .isEqualTo("7d6b0d85-8a2e-4d2c-9c2d-2c4b7b1a9120");

        assertThat(content)
            .extractingJsonPathStringValue("$.total")
            .isEqualTo("125000.50");

        assertThat(content)
            .extractingJsonPathStringValue("$.occurredAt")
            .isEqualTo("2026-11-25T10:15:30Z");
    }
}
~~~

Các assertion trên kiểm tra giá trị JSON theo path, không phụ thuộc thứ tự property hoặc khoảng trắng. Đây thường là điều cần bảo vệ trong contract. Không nên so sánh toàn bộ JSON bằng chuỗi nếu thứ tự field, escape hoặc format whitespace không phải một phần của hợp đồng.

Nếu contract yêu cầu timestamp ISO-8601 ở UTC, hãy kiểm tra chính xác hậu tố Z và độ chính xác thời gian. Nếu contract cho phép offset, kiểm tra giá trị sau khi parse tương đương về thời điểm và giữ đúng quy ước được công bố.

## 5. Kiểm thử deserialization và round-trip

Consumer cần đọc được payload theo hợp đồng. Deserialization test nên dùng JSON mẫu độc lập với object được serialize trong cùng test. Nếu chỉ serialize rồi deserialize lại cùng một object, producer và consumer có thể cùng mắc một lỗi nhưng test vẫn pass.

Ví dụ đọc payload mẫu:

~~~java
@JsonTest
class OrderPaidPayloadReadTest {

    @Autowired
    JacksonTester<OrderPaidPayload> json;

    @Test
    void readsPublishedPayloadSample() throws Exception {
        String sample = """
            {
              "eventId": "7d6b0d85-8a2e-4d2c-9c2d-2c4b7b1a9120",
              "orderNumber": "ORD-00042",
              "total": "125000.50",
              "currency": "VND",
              "occurredAt": "2026-11-25T10:15:30Z",
              "schemaVersion": 1
            }
            """;

        OrderPaidPayload payload = json.parseObject(sample);

        assertThat(payload.orderNumber()).isEqualTo("ORD-00042");
        assertThat(payload.total()).isEqualTo("125000.50");
        assertThat(payload.currency()).isEqualTo("VND");
        assertThat(payload.occurredAt())
            .isEqualTo(Instant.parse("2026-11-25T10:15:30Z"));
        assertThat(payload.schemaVersion()).isEqualTo(1);
    }
}
~~~

Round-trip test hữu ích để kiểm tra serializer và deserializer của cùng ứng dụng, nhưng không thay thế test đọc fixture đã được công bố. Nên giữ một số payload mẫu đại diện cho từng schema version và xác minh consumer đọc được chúng.

Đối với consumer viết bằng ngôn ngữ khác, cần chạy contract fixture qua parser hoặc contract test của consumer đó. Java round-trip chỉ chứng minh cấu hình Java tự hiểu dữ liệu do chính nó tạo ra.

## 6. Kiểm thử kiểu dữ liệu có rủi ro

Một payload có thể parse thành công nhưng vẫn sai nghiệp vụ. Hãy tập trung vào các kiểu dễ mất thông tin khi đi qua wire format.

| Kiểu dữ liệu | Ca kiểm thử nên có | Lỗi cần phát hiện |
|---|---|---|
| UUID | UUID chuẩn và chuỗi sai định dạng | Mất định danh hoặc parse nhầm |
| Mã nghiệp vụ | Chuỗi có số 0 đầu, chữ và dấu phân cách | Chuyển nhầm sang số |
| Decimal/tiền | Scale khác nhau, số lớn, số âm theo quy tắc | Sai precision hoặc làm tròn |
| Instant | UTC, offset, độ chính xác timestamp | Mất timezone hoặc lệch thời điểm |
| LocalDate | Ngày ở vùng có múi giờ khác nhau | Đổi ngày ngoài ý muốn |
| Enum | Mã đã biết và mã mới chưa biết | Phụ thuộc ordinal hoặc fail không kiểm soát |
| Boolean/null | false, null, thiếu trường | Nhầm trạng thái không biết với false |
| Collection | Rỗng, một phần tử, nhiều phần tử | Thứ tự hoặc phần tử bị mất |
| Số nguyên lớn | Giá trị gần giới hạn consumer | Tràn hoặc mất độ chính xác |

Ví dụ với decimal, test cần xác minh chuỗi "125000.50" vẫn giữ hai chữ số thập phân nếu scale là một phần của contract. Với enum, test phải chứng minh serializer gửi code ổn định như BANK_TRANSFER, không gửi ordinal 0 hoặc 1.

Với timestamp, cần phân biệt thời điểm tuyệt đối và ngày lịch. Instant phù hợp với thời điểm đã xảy ra; LocalDate phù hợp với ngày nghiệp vụ. Không chuyển LocalDate thành Instant lúc nửa đêm UTC nếu consumer cần giữ nguyên ngày lịch.

## 7. Kiểm thử validation của payload

Deserialize thành công không đồng nghĩa payload hợp lệ. Consumer cần kiểm tra trường bắt buộc, miền giá trị và invariant nghiệp vụ trước khi thực hiện side effect.

Ví dụ DTO có validation constraint:

~~~java
public record OrderPaidPayload(
    @NotBlank String eventId,
    @NotBlank String orderNumber,
    @NotBlank String total,
    @Pattern(regexp = "[A-Z]{3}") String currency,
    @NotNull Instant occurredAt,
    @Positive int schemaVersion
) {}
~~~

Có thể dùng Jakarta Bean Validation để kiểm tra:

~~~java
class OrderPaidPayloadValidationTest {

    private final Validator validator =
        Validation.buildDefaultValidatorFactory().getValidator();

    @Test
    void rejectsPayloadWithMissingRequiredValues() {
        var payload = new OrderPaidPayload(
            "",
            "",
            "not-a-decimal",
            "vnd",
            null,
            0
        );

        var violations = validator.validate(payload);

        assertThat(violations)
            .extracting(v -> v.getPropertyPath().toString())
            .contains(
                "eventId",
                "orderNumber",
                "currency",
                "occurredAt",
                "schemaVersion"
            );
    }
}
~~~

Ví dụ trên minh họa các constraint cơ bản; chuỗi total vẫn cần kiểm tra decimal bằng parser hoặc custom constraint vì NotBlank không xác minh cú pháp số. Sau khi parse, cần kiểm tra scale, miền giá trị, currency và quan hệ giữa các trường theo quy tắc nghiệp vụ.

Không giả định Jackson tự gọi Bean Validation khi deserialize. Hãy gọi Validator rõ ràng tại ranh giới nhận message hoặc dùng một thành phần tích hợp có hành vi đã được kiểm thử. Nếu payload không hợp lệ, consumer cần từ chối hoặc cách ly theo chính sách, không tiếp tục xử lý bằng giá trị mặc định.

## 8. Kiểm thử payload thiếu, thừa và không tương thích

Schema thay đổi theo thời gian. Consumer cần có hành vi được định nghĩa khi gặp trường mới, trường bị thiếu hoặc giá trị enum chưa biết.

Các tình huống cần kiểm tra:

- Trường bắt buộc bị thiếu.
- Trường tùy chọn không xuất hiện.
- Trường có giá trị null.
- Payload chứa field mới mà consumer cũ chưa biết.
- Enum có code mới.
- schemaVersion không được hỗ trợ.
- Field đổi kiểu dữ liệu hoặc thay đổi ý nghĩa.
- Payload JSON sai cú pháp hoặc sai content type.

Không nên mặc định bỏ qua mọi field không biết. Với field mở rộng tương thích, bỏ qua có thể là chính sách phù hợp; với discriminator hoặc field điều khiển nghiệp vụ, giá trị không biết có thể cần cách ly. Hãy cấu hình Jackson và validation theo contract cụ thể, sau đó kiểm thử hành vi đó.

Một test tương thích có thể dùng payload v2 có thêm trường optional để xác nhận consumer v1 vẫn đọc được các trường cũ. Ngược lại, nếu payload v2 đổi total từ chuỗi decimal sang object hoặc đổi ý nghĩa currency, cần test xác nhận consumer cũ bị từ chối hoặc producer phát event version mới theo kế hoạch migration.

## 9. Golden payload và fixture contract

Golden payload là các mẫu JSON đại diện cho contract được lưu cùng test hoặc trong một kho contract có version. Chúng giúp kiểm tra producer và consumer qua nhiều lần phát hành.

Một bộ fixture có thể gồm:

- Payload hợp lệ cho schema hiện tại.
- Payload hợp lệ của schema cũ còn trong thời hạn hỗ trợ.
- Payload có trường optional mới.
- Payload có giá trị biên của decimal, timestamp và collection.
- Payload lỗi để xác minh validation và dead-letter policy.

Test nên parse fixture và assert các trường quan trọng theo JSON path hoặc DTO đã deserialize. Tránh snapshot quá cứng với thứ tự property, khoảng trắng hoặc chi tiết serializer không nằm trong contract.

Khi thay đổi fixture, cần review như thay đổi API: trường nào được thêm, bỏ hoặc đổi ý nghĩa; consumer nào bị ảnh hưởng; schema version có cần tăng không; payload cũ được hỗ trợ đến khi nào.

Không cập nhật golden file tự động chỉ để test pass. Một fixture thay đổi phải phản ánh quyết định có chủ đích về contract, không phải kết quả tình cờ của serializer mới.

## 10. Kiểm thử schema evolution và backward compatibility

Event thường tồn tại trong broker, dead-letter queue, bản sao lưu hoặc hệ thống replay lâu hơn vòng đời một phiên bản ứng dụng. Consumer mới có thể phải đọc payload cũ; producer mới có thể gửi payload có field mà consumer cũ chưa biết.

Các quy tắc tương thích phổ biến:

| Thay đổi | Tác động | Kiểm thử |
|---|---|---|
| Thêm field optional | Thường tương thích nếu consumer bỏ qua field lạ | Consumer cũ đọc payload mới |
| Thêm field bắt buộc | Có thể phá consumer cũ hoặc payload cũ | Kiểm tra default/migration |
| Bỏ field | Có thể phá consumer đang dùng field đó | Consumer mới đọc payload cũ |
| Đổi kiểu field | Thường là thay đổi phá vỡ | Kiểm tra parser và schema version |
| Đổi ý nghĩa field | Nguy hiểm dù parse vẫn thành công | Test ngữ nghĩa và version mới |
| Thêm enum code | Có thể khiến consumer cũ từ chối | Test unknown enum policy |
| Đổi tên event type | Có thể làm routing hoặc handler không nhận | Contract và routing test |

Nếu dùng JSON Schema, Avro hoặc Protobuf, hãy kiểm tra schema bằng công cụ tương ứng và quy định compatibility mode. Với JSON không có schema registry, có thể quản lý schema bằng file versioned và contract tests. Dù chọn cách nào, test phải xác minh cả cú pháp lẫn ngữ nghĩa của dữ liệu.

Không tăng schemaVersion cho mọi lần thêm field nếu tổ chức đã chọn chính sách tương thích không cần đổi version. Ngược lại, không giữ nguyên version khi ý nghĩa hoặc cấu trúc thay đổi phá vỡ. Quy tắc versioning cần được ghi trong contract.

## 11. Kiểm thử event metadata và headers

Payload body không phải thành phần duy nhất consumer dựa vào. Message có thể mang metadata trong envelope hoặc broker headers.

Các giá trị thường cần kiểm tra:

- Event ID ổn định qua retry và replay.
- Event type đúng tên contract.
- Schema version đúng.
- occurredAt dùng UTC hoặc định dạng được quy định.
- Correlation ID được truyền qua các bước liên quan.
- Content type đúng, ví dụ application/json.
- Producer identity hoặc source nếu contract yêu cầu.
- Routing key hoặc destination khớp event type.

Nếu cùng metadata xuất hiện ở cả header và body, phải có một quy tắc nguồn sự thật. Không để header event type là OrderPaid trong khi body ghi OrderCancelled.

Với broker integration test, hãy nhận message từ queue kiểm thử và xác minh body lẫn headers. Test chỉ kiểm tra method publish được gọi không chứng minh broker đã nhận đúng byte payload hoặc header thực tế.

## 12. Kiểm thử tại ranh giới Spring Modulith

Spring Modulith tổ chức module và application event theo ranh giới module. Có thể kiểm thử mapper và serializer độc lập, sau đó kiểm thử tích hợp listener hoặc externalization trong application context.

Một số cấp độ kiểm thử:

1. **Mapper unit test:** domain event được chuyển thành payload đúng.
2. **Serialization test:** DTO được ghi thành JSON hoặc wire format đúng.
3. **Deserialization test:** consumer đọc payload mẫu và validate đúng.
4. **Module integration test:** module phát và nhận application event qua cấu hình thực tế của ứng dụng.
5. **Broker integration test:** externalization adapter gửi đúng message body, headers và destination.
6. **Contract test:** consumer độc lập đọc payload mẫu do producer công bố.

Spring Modulith cung cấp các công cụ kiểm thử module, nhưng việc một module test pass không tự chứng minh JSON payload tương thích với consumer bên ngoài. Cần kiểm tra đúng ranh giới mà test đang bảo vệ.

Với externalized event, có thể dùng broker kiểm thử hoặc môi trường tương thích để publish event và đọc lại message. Xác minh serializer, content type, target mapping và header thực tế. Nếu adapter gửi bất đồng bộ, hãy chờ điều kiện message xuất hiện bằng cơ chế đồng bộ hóa có timeout, không dùng sleep tùy tiện.

## 13. Kiểm thử payload lỗi và đường xử lý thất bại

Payload lỗi có thể đến từ producer phiên bản cũ, nguồn bên ngoài, message bị sửa hoặc lỗi serialization. Consumer cần có hành vi xác định thay vì ném lỗi không kiểm soát hoặc âm thầm bỏ qua.

Các trường hợp nên kiểm thử:

- JSON malformed.
- Thiếu event ID hoặc event type.
- schemaVersion không hỗ trợ.
- Decimal không parse được hoặc vượt miền giá trị.
- Timestamp không đúng định dạng.
- Enum code không được biết.
- Payload vượt giới hạn kích thước.
- Trường nhạy cảm không được phép xuất hiện.
- Mapping thất bại trước khi gửi broker.
- Consumer validation thất bại sau khi nhận message.

Kiểm thử cần xác minh message được reject, retry hoặc dead-letter đúng chính sách. Lỗi dữ liệu không thể tự sửa thường không nên retry vô hạn. Nếu đưa vào quarantine, phải xác minh record cách ly có event ID, nguyên nhân và khả năng điều tra/replay.

Không bắt exception rồi trả về bình thường nếu payload chưa được xử lý và chưa có quyết định cách ly bền vững. Hành vi đó có thể khiến publication hoặc message được xác nhận hoàn tất trong khi dữ liệu bị bỏ mất.

## 14. Kiểm thử tính tối thiểu và bảo mật payload

Payload là dữ liệu rời khỏi module hoặc tiến trình, vì vậy test nên bảo vệ nguyên tắc chỉ công bố trường consumer thực sự cần.

Có thể kiểm tra:

- Không serialize password, access token hoặc credential.
- Không gửi entity chứa toàn bộ hồ sơ khách hàng.
- Không đưa trường nội bộ như database key hoặc audit metadata không thuộc contract.
- Không log toàn bộ payload nếu có thông tin nhạy cảm.
- Các trường cần pseudonymization hoặc masking đã được xử lý.
- Consumer không nhận field ngoài quyền được phép.

Một test có thể serialize DTO rồi kiểm tra các field cấm không xuất hiện trong JSON tree. Nên kiểm tra cả nested object và metadata/header, vì dữ liệu nhạy cảm có thể bị đưa ra ngoài ở một trong hai nơi.

Nếu một consumer cần thêm dữ liệu, hãy cân nhắc event contract riêng hoặc projection được phê duyệt. Không thêm dữ liệu nhạy cảm vào payload chung chỉ để làm một consumer tiện hơn.

## 15. Bộ kiểm thử tối thiểu cho một event

Với event OrderPaid, có thể dùng bộ kiểm thử sau làm điểm xuất phát:

| Nhóm | Test case | Kỳ vọng |
|---|---|---|
| Mapping | Domain event sang DTO | ID, order number, amount, currency, timestamp đúng |
| Serialization | DTO sang JSON | Field và wire type theo contract |
| Deserialization | JSON fixture sang DTO | Consumer đọc được payload |
| Decimal | Giá trị 125000.50 | Không mất scale/precision theo quy ước |
| Time | Instant UTC | Giữ đúng thời điểm |
| Enum | Payment method code | Dùng code ổn định, không ordinal |
| Validation | Thiếu event ID | Bị từ chối |
| Compatibility | Payload cũ và mới | Đọc theo chính sách version |
| Metadata | Header và envelope | Event type, content type, correlation đúng |
| Security | Trường bí mật | Không xuất hiện |
| Error path | JSON malformed | Retry/quarantine/DLQ đúng policy |
| Broker | Publish rồi consume | Body, headers, destination chính xác |

Không cần một test duy nhất bao phủ tất cả. Tách test theo trách nhiệm giúp khi lỗi xuất hiện có thể xác định nhanh mapper, serializer, schema, consumer hay broker adapter là nguyên nhân.

## 16. Lỗi thường gặp khi kiểm thử event payload

**Chỉ kiểm tra publisher được gọi.** Điều đó không chứng minh payload đúng. Hãy assert DTO, serialized body và metadata.

**Chỉ kiểm tra round-trip trong cùng một ObjectMapper.** Producer và consumer có thể cùng hiểu một biểu diễn sai. Hãy dùng fixture độc lập và contract test.

**So sánh JSON bằng chuỗi nguyên văn.** Test dễ hỏng vì whitespace hoặc thứ tự field. Hãy assert theo JSON path hoặc parse thành tree trừ khi canonical JSON là một phần của contract.

**Serialize trực tiếp entity JPA.** Test có thể vô tình khóa contract vào cấu trúc persistence. Hãy dùng DTO công bố riêng.

**Không kiểm tra decimal và thời gian.** Payload vẫn parse nhưng có thể làm sai số tiền hoặc thời điểm. Hãy dùng dữ liệu biên và assert biểu diễn chính xác.

**Không test field thiếu hoặc enum mới.** Consumer có thể crash khi gặp message hợp lệ theo phiên bản producer mới. Hãy định nghĩa unknown-field và unknown-enum policy.

**Tự động cập nhật golden fixture khi test fail.** Điều này có thể che giấu thay đổi contract phá vỡ. Mỗi fixture thay đổi cần được review.

**Chỉ test trong module, bỏ qua broker.** Module test không chứng minh adapter gửi đúng wire format. Hãy có integration test tại ranh giới externalization khi ứng dụng sử dụng broker.

**Bỏ qua dữ liệu nhạy cảm.** Payload có thể đúng chức năng nhưng lộ trường không cần thiết. Hãy kiểm tra field allowlist và metadata.

## Kết luận

Kiểm thử event payload cần bảo vệ mapping, serialization, deserialization, validation và khả năng tương thích schema. Unit test giúp xác minh domain event được chuyển đúng sang DTO; serialization test xác nhận wire format; fixture và contract test bảo vệ consumer qua các phiên bản; integration test xác minh payload cùng headers thực tế đi qua ranh giới Spring Modulith và broker.

Khi test dùng dữ liệu biên, fixture độc lập, unique contract version và kiểm tra cả đường lỗi, producer có thể thay đổi nội bộ mà không làm consumer hiểu sai event. Đây là nền tảng để các module và hệ thống tích hợp giao tiếp ổn định qua application events.

