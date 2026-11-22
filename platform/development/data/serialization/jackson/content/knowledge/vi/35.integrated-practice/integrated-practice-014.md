# Nghiệm thu bằng tính đúng, tính tương thích, bảo mật và hiệu năng

Một thay đổi serialization chỉ sẵn sàng phát hành khi dữ liệu được chuyển đổi đúng ý nghĩa, các producer/consumer được hỗ trợ vẫn trao đổi được với nhau, payload không mở ra lỗ hổng hoặc tiêu thụ tài nguyên vô hạn, và chi phí xử lý nằm trong ngân sách hiệu năng của hệ thống. Một test round-trip thành công chỉ chứng minh một phần nhỏ của yêu cầu đó.

Với Jackson, cùng một DTO có thể được serialize thành JSON theo nhiều cấu hình khác nhau. Annotation, module, naming strategy, custom serializer, polymorphic typing, date feature và phiên bản dependency đều có thể làm thay đổi wire contract. Vì vậy, nghiệm thu cần đánh giá toàn bộ boundary dữ liệu: object đầu vào, mapper configuration, payload được phát, parser/reader của consumer, validation, tài nguyên tiêu thụ và cách hệ thống triển khai thay đổi.

Bài học này xây dựng một phương pháp nghiệm thu tích hợp theo bốn trụ cột: **tính đúng, tính tương thích, bảo mật và hiệu năng**. Mỗi trụ cột có mục tiêu, bằng chứng và tiêu chí chấp nhận riêng. Kết quả cuối cùng phải truy vết được từ yêu cầu hợp đồng tới test, fixture, số liệu và quyết định phát hành.

## 1. Nghiệm thu là quyết định dựa trên bằng chứng

Nghiệm thu không chỉ là chạy test và thấy màu xanh. Trước khi thay đổi Jackson hoặc DTO được chấp nhận, nhóm cần trả lời:

1. Payload có giữ nguyên ý nghĩa nghiệp vụ không?
2. Consumer đang tồn tại có đọc được payload mới không?
3. Reader mới có xử lý được dữ liệu cũ còn lưu hoặc còn trong queue không?
4. Payload không tin cậy có thể gây deserialize nguy hiểm, lộ dữ liệu hoặc cạn tài nguyên không?
5. Chi phí serialize/deserialize có đáp ứng SLO khi tải thực tế không?
6. Khi rollout hoặc rollback, các phiên bản có thể cùng tồn tại an toàn không?
7. Có đủ fixture, test và số liệu để người khác tái hiện quyết định không?

Một thay đổi có thể đạt một trụ cột nhưng thất bại ở trụ cột khác. Ví dụ:

- JSON round-trip giữ đúng BigDecimal nhưng client JavaScript làm tròn ID lớn.
- Reader mới đọc payload V1 nhưng writer V2 thêm enum mà consumer cũ không hiểu.
- API trả đúng JSON nhưng Jackson lazy-load entity và tạo N+1 query.
- Benchmark cho thấy throughput cao nhưng parser chấp nhận object lồng quá sâu, gây cạn stack hoặc CPU.
- Payload nhỏ hơn nhưng logging ghi cả access token và thông tin cá nhân.

Vì vậy, không gộp tất cả thành một câu hỏi “Jackson chạy được không?”. Mỗi trụ cột phải có tiêu chí độc lập, và release gate phải yêu cầu đủ bằng chứng cho cả bốn.

## 2. Xác định phạm vi nghiệm thu trước khi thay đổi

Trước tiên, xác định chính xác boundary đang thay đổi:

- HTTP request hoặc response.
- Message broker producer/consumer.
- JSON lưu trong database hoặc object storage.
- File import/export.
- Cache key/value.
- Event replay hoặc event sourcing.
- JSON tree hoặc untyped Map.
- XML, Smile, CBOR hoặc format module khác.
- Internal RPC giữa các service.

Mỗi boundary có consumer, vòng đời và yêu cầu khác nhau. Một request API có thể cần strict unknown-property handling để phát hiện client gửi sai field. Event consumer có thể cần bỏ qua hoặc giữ extension field mới để hỗ trợ forward compatibility. JSON lưu trong database có thể phải đọc payload từ nhiều năm trước.

Lập danh sách thành phần tham gia:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Producer | Class, mapper và dependency version nào tạo payload? |
| Wire format | JSON, Smile, CBOR hay XML? Encoding và media type nào? |
| Contract/schema | Field, kiểu, required, null, default và version được định nghĩa ở đâu? |
| Consumer | Ngôn ngữ, parser, target type và version nào đọc payload? |
| Persistence | Payload có thể tồn tại bao lâu? Có cần replay không? |
| Transport | Message boundary, kích thước tối đa, compression và retry ra sao? |
| Security boundary | Payload có đến từ client, partner hoặc nguồn không tin cậy không? |
| SLO | Throughput, latency, memory và error budget nào áp dụng? |

Không nghiệm thu một mapper trong môi trường cô lập rồi suy ra mọi đường tích hợp đều an toàn. Cần biết nơi bytes được tạo, nơi chúng được đọc và những hệ thống nằm giữa hai đầu.

## 3. Viết acceptance contract có thể kiểm chứng

Một contract tốt mô tả dữ liệu và hành vi quan sát được, không chỉ mô tả Java class.

Ví dụ event thanh toán:

```json
{
  "schemaVersion": 2,
  "eventId": "evt-0001042",
  "paymentId": "pay-9007199254740993",
  "amount": 1250.00,
  "currency": "VND",
  "occurredAt": "2026-11-12T03:30:00.123Z",
  "status": "PAID"
}
```

Contract cần trả lời:

- schemaVersion là integer bắt buộc và version không hỗ trợ bị từ chối.
- eventId và paymentId là string; giữ nguyên số 0 đầu và mọi ký tự.
- amount là decimal JSON number; consumer phải đọc bằng kiểu giữ precision.
- currency là mã ISO được hệ thống chấp nhận.
- occurredAt là ISO-8601 UTC và precision tối đa là milliseconds trong contract này.
- status là external code ổn định; unknown code có policy riêng.
- Field nào bắt buộc, field nào có thể null hoặc missing?
- Unknown property bị từ chối, bỏ qua hay giữ lại?
- Kích thước message, độ sâu và số phần tử tối đa là bao nhiêu?

Từ contract, viết acceptance criteria có thể quan sát. Ví dụ:

| Yêu cầu | Bằng chứng chấp nhận |
| --- | --- |
| ID không mất ký tự | Fixture chứa leading zero và ID lớn được round-trip chính xác |
| Decimal không bị làm tròn | BigDecimal assertion theo value và scale đã công bố |
| Timestamp giữ đúng instant | Test parse và so sánh Instant/precision |
| Reader mới hỗ trợ V1 | Bộ fixture lịch sử V1 được đọc và kiểm tra semantics |
| Payload sai schema bị từ chối | Negative tests xác nhận exception/status đã quy định |
| Unknown enum có policy | Test cả code đã biết và chưa biết |
| Parser có giới hạn | Payload vượt giới hạn bị từ chối có kiểm soát |
| Không phát sinh N+1 | Integration test đo query count với nhiều record |
| Hiệu năng đạt SLO | Benchmark/load test có workload và môi trường được ghi nhận |

Tránh tiêu chí mơ hồ như “nhanh”, “an toàn”, “tương thích tốt”. Hãy gắn mỗi tiêu chí với phép đo hoặc kết quả test. Ngưỡng số cụ thể cần lấy từ SLO, baseline và tải dự kiến của dự án, không tự chọn một con số chung cho mọi hệ thống.

## 4. Trụ cột thứ nhất: tính đúng của dữ liệu

Tính đúng trả lời câu hỏi: sau khi serialize, truyền/lưu và deserialize, dữ liệu có còn mang cùng ý nghĩa nghiệp vụ không?

Không chỉ kiểm tra JSON parse được. Cần xác minh:

- Field đúng tên và đúng wire type.
- Giá trị scalar giữ chính xác.
- Object lồng nhau và collection giữ cấu trúc.
- Null, missing, empty và default có semantics rõ.
- Date/time giữ đúng instant, offset và precision.
- Enum giữ external code.
- Map key không bị chuẩn hóa sai.
- Binary data giữ nguyên byte.
- Polymorphic type chọn đúng subtype.
- Validation nghiệp vụ vẫn được thực hiện.

### 4.1. Kiểm tra wire shape

Dùng JsonNode để xác nhận tên property, loại token và cấu trúc:

```java
JsonNode root = mapper.readTree(json);

assertTrue(root.get("eventId").isTextual());
assertTrue(root.get("amount").isNumber());
assertTrue(root.get("schemaVersion").isIntegralNumber());
assertTrue(root.get("occurredAt").isTextual());
assertTrue(root.get("status").isTextual());
```

Kiểm tra field bắt buộc và field không được công bố:

```java
assertTrue(root.hasNonNull("paymentId"));
assertFalse(root.has("passwordHash"));
assertFalse(root.has("internalRiskScore"));
```

Wire-shape test giúp phát hiện thay đổi kiểu number thành string, đổi tên property, vô tình đưa field nội bộ vào response hoặc thay đổi cấu trúc nested object.

Không dùng một object round-trip làm bằng chứng duy nhất. Nếu cả writer và reader cùng thay đổi theo một cách, chúng vẫn có thể hiểu nhau nhưng vi phạm contract mà consumer khác đang sử dụng.

### 4.2. Kiểm tra semantics của tiền

Dùng BigDecimal thay cho double khi cần decimal chính xác. Xác định rõ scale có thuộc contract không:

```java
assertEquals(0, expected.amount().compareTo(actual.amount()));
assertEquals(expected.amount().scale(), actual.amount().scale());
```

Nếu scale không quan trọng, assertion đầu là đủ. Nếu scale quan trọng với tiền hoặc độ chính xác đo lường, giữ assertion thứ hai. Luôn kiểm tra currency cùng amount; số 1250 không thể tự mô tả đó là VND hay USD.

Kiểm tra giá trị biên: zero, âm nếu được phép, số lớn, trailing zero, scale khác nhau, precision cao và giá trị bị từ chối. Nếu client JavaScript đọc JSON number, test cả đường client để phát hiện sai số do Number.

### 4.3. Kiểm tra semantics của thời điểm

Chọn đúng kiểu:

- Instant cho một điểm trên UTC timeline.
- OffsetDateTime khi cần giữ offset.
- ZonedDateTime hoặc local date/time cùng zone ID khi cần quy tắc vùng.
- LocalDate cho ngày không có giờ.
- LocalDateTime cho giờ lịch chưa gắn timezone.

Test cả timezone, offset và fractional seconds. Nếu contract chỉ giữ milliseconds, so sánh sau khi chuẩn hóa đến milliseconds. Nếu contract yêu cầu nanoseconds, kiểm tra precision đầy đủ. Không so sánh chuỗi đơn thuần khi contract yêu cầu cùng instant, và cũng không chỉ so sánh instant nếu offset ban đầu là dữ liệu cần giữ.

### 4.4. Kiểm tra ID và số nguyên lớn

ID thường là string, ngay cả khi chỉ chứa chữ số. Kiểm tra leading zero, chữ hoa/thường, dấu phân cách, Unicode nếu được phép và giá trị lớn hơn giới hạn integer an toàn của JavaScript.

Không để ID bị parse thành number rồi mới serialize lại. Với mã như §"0001042"§, số 0 đầu là một phần định danh.

### 4.5. Kiểm tra missing, null, empty và default

Các trạng thái này không mặc nhiên tương đương:

```json
{}
```

```json
{"comment": null}
```

```json
{"comment": ""}
```

```json
{"amount": 0}
```

```json
{"amount": 0.00}
```

Đối với từng property, quy định hành vi khi field thiếu, null tường minh, chuỗi rỗng, collection rỗng hoặc giá trị zero. Dùng wrapper type/creator/validation phù hợp nếu cần phân biệt missing với null. Không để coercion mặc định quyết định nghiệp vụ.

### 4.6. Kiểm tra collection, map và thứ tự

Xác định array có giữ thứ tự không. JSON object không nên được dùng như một cấu trúc có ý nghĩa thứ tự property nếu contract không nói rõ. Với Map key là mã, giữ key dạng String nếu lexical form có ý nghĩa.

Kiểm tra collection rỗng, null, một phần tử, nhiều phần tử, phần tử trùng nếu có thể và kích thước gần giới hạn. Với Set, xác định thứ tự output có cần ổn định hay không. Nếu cần canonical output, phải quy định sort order rõ ràng.

### 4.7. Kiểm tra polymorphism và custom mapping

Nếu dùng @JsonTypeInfo, test từng type id được hỗ trợ, subtype không biết và type id không hợp lệ. Dùng tên type ổn định thay vì tên class Java. Custom serializer/deserializer cần test cả input hợp lệ, missing/null, sai kiểu và dữ liệu biên.

Với custom serializer, kiểm tra JSON tree/fixture độc lập; đừng chỉ dùng chính deserializer của nó để đọc lại output. Hai đoạn code cùng sai có thể round-trip thành công.

## 5. Trụ cột thứ hai: tính tương thích

Tính tương thích trả lời câu hỏi: producer và consumer thuộc các phiên bản khác nhau có trao đổi được dữ liệu trong toàn bộ vòng đời payload không?

Phân biệt:

- Backward compatibility: reader mới đọc dữ liệu do writer cũ tạo.
- Forward compatibility: reader cũ xử lý dữ liệu do writer mới tạo.
- Same-version compatibility: writer và reader cùng phiên bản hoạt động đúng.
- Persistence compatibility: code hiện tại đọc dữ liệu đã lưu từ release trước.
- Replay compatibility: consumer mới đọc được event lịch sử trong queue/log.
- Rolling-deployment compatibility: các phiên bản cùng tồn tại khi deploy dần.

### 5.1. Tạo ma trận writer/reader

Ví dụ:

| Writer | Reader | Ý nghĩa |
| --- | --- | --- |
| V1 | V1 | Baseline cũ |
| V1 | V2 | Reader mới hỗ trợ dữ liệu cũ |
| V2 | V2 | Contract hiện tại |
| V2 | V1 | Reader cũ với payload mới, nếu rollout yêu cầu |
| V1 | Current migration | Migration dữ liệu lịch sử |
| Invalid | Current | Payload lỗi bị từ chối theo policy |

Không phải hệ thống nào cũng cần mọi ô. Hãy đánh dấu các cặp thực sự có thể xuất hiện trong rollout, rollback, replay hoặc lưu trữ.

### 5.2. Lưu fixture lịch sử độc lập

Giữ payload V1/V2 trong test resources. Fixture cũ nên được tạo từ release cũ, artifact đã phát hành hoặc contract sample được xác nhận. Không tạo fixture lịch sử bằng mapper hiện tại rồi gọi nó là dữ liệu cũ.

Mỗi fixture ghi rõ schema version, producer/release, trường hợp được đại diện và expected semantics. Có thể ẩn danh dữ liệu production hoặc tạo dữ liệu tổng hợp có cùng cấu trúc.

Ví dụ:

```text
src/test/resources/compatibility/payment-event/
  v1/
    minimal.json
    complete.json
    null-fields.json
  v2/
    minimal.json
    complete.json
  invalid/
    unknown-version.json
    invalid-amount.json
```

### 5.3. Kiểm tra schema evolution

Các thay đổi thường gặp:

- Thêm field optional.
- Thêm field required.
- Đổi tên field.
- Đổi kiểu field.
- Đổi enum code.
- Thêm subtype.
- Thay đổi null/default.
- Đổi timestamp format hoặc đơn vị.
- Thay object bằng array hoặc ngược lại.

Thêm field optional thường dễ tương thích hơn thêm field bắt buộc. Đổi tên có thể cần @JsonAlias để reader chấp nhận tên cũ. Đổi kiểu thường cần DTO theo version hoặc migration function. Unknown property policy phải được quyết định theo boundary.

Đối với enum mới, chọn rõ từ chối, fallback UNKNOWN hoặc giữ raw code. Không ánh xạ giá trị lạ sang trạng thái có side effect như PAID chỉ để tránh lỗi deserialize.

### 5.4. Schema version và Jackson version là hai việc khác nhau

Schema version mô tả cấu trúc và semantics của message. Jackson version mô tả thư viện đọc/ghi message. Nâng Jackson không tự động nâng schema; schema thay đổi cũng không nhất thiết cần nâng Jackson.

Khi nâng dependency, chạy lại fixture lịch sử, golden output và negative tests bằng version mới. Đồng bộ Core, Databind, Annotations và format module bằng BOM hoặc dependency management của framework.

### 5.5. Kiểm tra rolling deployment và rollback

Một thứ tự deploy phổ biến:

1. Nâng consumer trước để reader hỗ trợ cả V1 và V2.
2. Chờ consumer cũ ngừng hoạt động.
3. Bắt đầu phát V2 từ producer.
4. Theo dõi decode error, unknown field/type và dead-letter queue.
5. Chỉ bỏ hỗ trợ V1 sau khi dữ liệu V1 đã hết vòng đời hoặc được migrate.

Đây là cách mở rộng khả năng đọc trước khi thay writer. Nếu rollback về code cũ vẫn có thể xảy ra, cần xác định writer mới có phát dữ liệu mà reader cũ không đọc được hay không. Nếu có, cần giữ compatibility hoặc có kế hoạch rollback dữ liệu.

### 5.6. Persistence và replay

Database JSON, object storage, cache và event log có vòng đời khác nhau. Xác định thời gian dữ liệu tồn tại, khả năng replay và cách rebuild projection. Với event sourcing, giữ raw event lịch sử nếu nó là audit record; dùng upcaster hoặc migration mapping để chuyển sang model hiện tại.

Không loại bỏ reader cũ chỉ vì producer mới đã được deploy. Cần biết chắc payload cũ không còn tồn tại hoặc đã được chuyển đổi có kiểm chứng.

## 6. Trụ cột thứ ba: bảo mật khi đọc và ghi dữ liệu

Payload là input không tin cậy ở mọi boundary nhận dữ liệu từ client, partner, queue hoặc file. Một JSON parse thành công không có nghĩa nó an toàn. Jackson cần được cấu hình cùng validation, giới hạn tài nguyên và chính sách type rõ ràng.

### 6.1. Không bật polymorphic default typing rộng cho input không tin cậy

Polymorphic typing cho phép payload mang type metadata để Jackson chọn subtype. Nếu cấu hình quá rộng hoặc cho phép class tùy ý, dữ liệu có thể yêu cầu khởi tạo những kiểu không nên được phép.

Nguyên tắc:

- Dùng allowlist subtype cụ thể.
- Ưu tiên @JsonTypeInfo với Id.NAME và type id ổn định.
- Đăng ký subtype được phép bằng @JsonSubTypes hoặc SubtypeResolver phù hợp.
- Không tin class name/package do payload bên ngoài cung cấp.
- Không bật default typing rộng cho dữ liệu không tin cậy.
- Test type id đã biết, không biết và bị cấm.

Ví dụ contract dùng tên type công khai:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(
        value = PaymentCreated.class,
        name = "payment.created"
    ),
    @JsonSubTypes.Type(
        value = PaymentCancelled.class,
        name = "payment.cancelled"
    )
})
public interface PaymentEvent {
}
```

Type id phải được kiểm tra trước khi ứng dụng thực hiện side effect. Unknown type có thể bị từ chối, giữ raw payload hoặc đưa vào dead-letter queue theo chính sách.

### 6.2. Giới hạn kích thước và độ sâu input

Payload quá lớn hoặc lồng quá sâu có thể tiêu thụ nhiều CPU, heap hoặc stack. Đặt giới hạn cho:

- Tổng kích thước request/message.
- Độ sâu object/array lồng nhau.
- Độ dài string và field name.
- Độ dài number token nếu phù hợp.
- Số phần tử collection.
- Kích thước byte array/binary payload.
- Thời gian xử lý và concurrency.

Jackson phiên bản mới có StreamReadConstraints để giới hạn một số đặc tính parser. Cấu hình minh họa:

```java
JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(
        StreamReadConstraints.builder()
            .maxNestingDepth(100)
            .maxStringLength(1_000_000)
            .maxNumberLength(1_000)
            .build()
    )
    .build();

ObjectMapper mapper = JsonMapper.builder(factory).build();
```

Các con số trên chỉ là ví dụ, không phải mặc định an toàn cho mọi ứng dụng. Chọn giới hạn theo payload hợp lệ và SLO. Kiểm tra version Jackson đang dùng có hỗ trợ API tương ứng và áp dụng giới hạn ở transport trước khi toàn bộ body được buffer vào memory.

Giới hạn parser không thay thế giới hạn HTTP/broker, giới hạn collection sau binding hoặc kiểm soát concurrency. Cần nhiều lớp bảo vệ.

### 6.3. Từ chối input sai kiểu một cách có chủ đích

Coercion có thể biến string thành number, number thành string hoặc empty string thành null tùy cấu hình. Với boundary nhạy cảm, xác định kiểu token được chấp nhận và test input sai.

Ví dụ, amount phải là JSON number. Nếu client gửi §"amount": "100"§, contract có thể yêu cầu từ chối thay vì âm thầm chuyển đổi. Coercion policy nên được thiết kế theo từng boundary và version Jackson.

Sau deserialize, chạy Bean Validation/domain validation cho range, currency, ID format, required field và quan hệ nghiệp vụ. Jackson chỉ ánh xạ cấu trúc; nó không tự xác nhận payment amount hợp lệ hoặc người gửi có quyền dùng account ID.

### 6.4. Chống mass assignment

Không bind request JSON trực tiếp vào JPA entity hoặc domain aggregate có field quản trị. Client có thể gửi id, role, ownerId, status, passwordHash hoặc field nội bộ.

Dùng request DTO allowlist:

```java
public record CreatePaymentRequest(
    @NotBlank String customerId,
    @NotNull @Positive BigDecimal amount,
    @NotBlank String currency
) {}
```

Service tự gán field do server quản lý như status, owner, audit user và createdAt. Kiểm tra quyền trên từng resource; không dựa vào việc field có mặt hay không trong JSON.

### 6.5. Bảo vệ dữ liệu nhạy cảm trong response và log

Kiểm tra response không vô tình phát:

- Password hoặc password hash.
- Access/refresh token.
- Secret key và credential.
- Internal risk score.
- Field audit nội bộ.
- Dữ liệu cá nhân không cần cho endpoint.

Không serialize toàn bộ entity hoặc object graph chỉ vì tiện. Dùng response DTO theo endpoint. Log metadata như event type, schema version, correlation ID và byte length; chỉ log field cần thiết sau redaction. Không dump payload chứa bí mật vào log khi parse lỗi.

### 6.6. Parser error và thông tin nội bộ

Không trả stack trace, class name nội bộ, đường dẫn file, SQL hoặc cấu hình mapper trong lỗi HTTP công khai. Chuyển lỗi parse/validation thành error response ổn định, có correlation ID để tra log nội bộ.

Phân biệt lỗi client (payload sai cú pháp/contract) với lỗi hệ thống (dependency mismatch, bug serializer, database unavailable). Không biến mọi JsonProcessingException thành HTTP 500 hoặc ngược lại trả quá nhiều chi tiết parser cho client.

### 6.7. Kiểm tra XML nếu ứng dụng dùng XmlMapper

Nếu dùng Jackson XML, bảo mật còn phụ thuộc XML parser/factory và cấu hình xử lý external entity/DTD. Không giả định các bảo vệ của JSON parser tự áp dụng cho XML. Kiểm tra parser được dùng, tắt DTD/external entity theo stack phù hợp, giới hạn kích thước/depth và dùng fixture có DOCTYPE/entity để xác nhận payload bị xử lý theo policy.

### 6.8. Fuzz và negative testing

Tạo input malformed và adversarial:

- JSON bị cắt giữa chừng.
- Duplicate property.
- Nested array/object rất sâu.
- String cực dài.
- Number cực dài hoặc exponent bất thường.
- Collection rất lớn.
- Type id không được phép.
- Enum không biết.
- UTF-8 lỗi hoặc byte sequence không hợp lệ ở boundary.
- Payload có field giả mạo quyền.
- Payload chứa giá trị vượt giới hạn domain.

Kết quả mong đợi là từ chối có kiểm soát, không crash process, không treo vô hạn, không làm lộ dữ liệu và không thực hiện side effect một phần.

## 7. Trụ cột thứ tư: hiệu năng và tài nguyên

Hiệu năng không chỉ là số operation mỗi giây trong một microbenchmark. Hệ thống cần đáp ứng throughput, latency, memory, GC và payload size dưới workload thực tế.

### 7.1. Đo đúng workload

Giữ cấu hình mapper và DTO giống production:

- Cùng Jackson version và module.
- Cùng ObjectMapper feature, naming strategy và custom serializer.
- Cùng target Java type và generic type.
- Cùng đường input/output: String, byte array, InputStream, OutputStream.
- Cùng phân bố small/medium/large payload.
- Cùng tỷ lệ null, nested object, collection, map và polymorphic subtype.

Tạo ObjectMapper trong setup cho steady-state benchmark; không tạo mới trong mỗi operation trừ khi đang đo startup. Chuẩn bị fixture ngoài vùng đo. Dùng JMH cho microbenchmark JVM và load/integration test cho toàn pipeline.

### 7.2. Tách read, write và end-to-end

Đo riêng:

- Serialize POJO thành String/bytes.
- Deserialize bytes/String thành DTO.
- Parse token mà không bind object nếu cần phân tích parser.
- Bind tree hoặc POJO.
- Stream trực tiếp tới output.
- Compression/decompression.
- Validation và business mapping.
- Transport end-to-end.

Nếu benchmark JSON String output với Smile byte output, kết quả bao gồm các đường I/O khác nhau. Hãy so sánh cùng mục tiêu và báo rõ phần nào được đo.

### 7.3. Đo nhiều chỉ số

| Chỉ số | Câu hỏi |
| --- | --- |
| Throughput | Bao nhiêu message/operation mỗi giây? |
| p50/p95/p99 latency | Phần lớn và tail request mất bao lâu? |
| Allocation/op | Mỗi message tạo bao nhiêu byte allocation? |
| GC count/time | Tần suất và thời gian GC thay đổi thế nào? |
| Peak heap | Bộ nhớ tăng ra sao khi có nhiều message đồng thời? |
| Payload size | Bytes trước/sau serialization và compression là bao nhiêu? |
| CPU | Chi phí parse, bind, encode chiếm bao nhiêu CPU? |
| Error rate | Có lỗi timeout, decode hoặc rejection dưới tải không? |

Throughput cao không đảm bảo tail latency tốt. Payload nhỏ hơn không đồng nghĩa CPU ít hơn. Hãy đọc các chỉ số cùng nhau.

### 7.4. JMH cho microbenchmark

Ví dụ cấu hình cơ bản:

```java
@BenchmarkMode(Mode.Throughput)
@OutputTimeUnit(TimeUnit.SECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
@Fork(3)
@State(Scope.Thread)
public class JacksonBenchmark {
    // Mapper và fixture được chuẩn bị trong setup.
}
```

Chạy GC profiler:

```bash
java -jar target/benchmarks.jar JacksonBenchmark -prof gc
```

Các giá trị warmup/fork là điểm bắt đầu. Chạy đủ lâu để quan sát ổn định, lưu raw result và điều kiện runtime. Đừng kết luận từ một lần chạy vài mili giây hoặc từ benchmark chạy trong lúc CPU bị tải nền.

### 7.5. Load test cho concurrency và tail latency

JMH đo một phần nhỏ trong điều kiện có kiểm soát. Load test cần kiểm tra:

- Nhiều request/message đồng thời.
- Payload mix gần production.
- Buffer và thread pool thực tế.
- Backpressure và queue growth.
- Timeout/retry.
- Heap và GC dưới tải kéo dài.
- Consumer lag và dead-letter rate.
- Hành vi khi payload lớn xuất hiện theo burst.

Không dùng microbenchmark thay cho load test. Một mapper nhanh khi chạy đơn luồng vẫn có thể tạo allocation cao và làm hệ thống GC nhiều khi concurrency tăng.

### 7.6. Streaming và giới hạn bộ nhớ

Nếu payload lớn, cân nhắc đọc/ghi qua stream thay vì materialize toàn bộ String hoặc byte array. Tuy nhiên, streaming không tự động có nghĩa bộ nhớ hằng số nếu Databind vẫn tạo object graph lớn. Với hàng triệu record, xử lý từng item hoặc page có thể phù hợp hơn đọc toàn bộ List.

Đo buffer reuse và allocation đúng như production. Nếu benchmark dùng ByteArrayOutputStream tái sử dụng nhưng production tạo buffer mới mỗi request, kết quả không đại diện.

### 7.7. Compression và format phải được đo riêng

JSON, Smile và CBOR là các cách biểu diễn dữ liệu. Gzip/zstd là compression. So sánh cần tách:

- Serialization time.
- Compression time.
- Compressed bytes.
- Decompression time.
- Deserialization time.

Dữ liệu binary compact có thể giảm ít sau compression; JSON có thể nén tốt do tên field lặp lại. Chỉ benchmark trên payload đại diện mới cho kết quả hữu ích.

## 8. Kiểm thử nhiều tầng để tạo bằng chứng

Không một loại test nào bao phủ cả bốn trụ cột. Một bộ nghiệm thu nên kết hợp nhiều tầng.

| Tầng | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Unit test | Semantics của serializer/deserializer và migration | BigDecimal, Instant, ID, enum |
| Contract test | Wire shape ổn định | JSON tree, golden fixture, schema |
| Compatibility test | Reader/writer khác version | V1 fixture với V2 reader |
| Integration test | Jackson trong Spring, database và transport | MockMvc, broker, persistence |
| Security test | Input độc hại và giới hạn | Unknown type, deep nesting, huge string |
| Performance test | Tài nguyên và latency | JMH, load test, GC profiler |
| Deployment test | Rolling upgrade/rollback | Consumer cũ/mới chạy cùng lúc |

### 8.1. Unit test

Kiểm tra custom serializer/deserializer, value object, coercion, date/time và decimal. Test giá trị hợp lệ, biên và invalid. Dùng expected value độc lập thay vì đọc lại output bằng cùng logic rồi chỉ kiểm tra không exception.

### 8.2. Contract test

Lưu golden JSON hoặc schema. So sánh tree khi whitespace/property order không thuộc contract. Nếu canonical bytes dùng cho signature/hash, test byte representation riêng với canonicalization được quy định.

### 8.3. Compatibility test

Đọc fixture lịch sử bằng code hiện tại. Nếu cần forward compatibility, đọc payload mới bằng reader cũ. Giữ fixture bất biến trừ khi có thay đổi contract được review.

### 8.4. Integration test

Kiểm tra mapper được Spring Boot cấu hình thực tế, request/response converter, validation, transaction, JPA fetch plan, message converter và broker serialization. Không tạo một ObjectMapper test riêng có feature khác production rồi suy ra application context hoạt động tương tự.

### 8.5. Security test

Kiểm tra malformed input, parser constraints, unknown subtype, field giả mạo quyền, dữ liệu nhạy cảm trong response và error message. Xác nhận request lỗi không tạo side effect hoặc ghi một phần dữ liệu.

### 8.6. Performance test

Chạy benchmark trên DTO/payload đại diện, rồi load test đường end-to-end. Lưu kết quả, môi trường, dependency version và commit. Đánh giá cả tail latency, allocation và GC.

## 9. Xây dựng acceptance matrix theo bốn trụ cột

Một ma trận giúp release reviewer thấy rõ từng yêu cầu và bằng chứng:

| Trụ cột | Hạng mục | Bằng chứng cần có | Điều kiện đạt |
| --- | --- | --- | --- |
| Tính đúng | Wire shape | Contract test/golden file | Field và token type đúng schema |
| Tính đúng | Decimal/time/ID | Round-trip semantic tests | Value, precision và lexical ID đúng |
| Tính đúng | Null/enum/polymorphism | Boundary tests | Policy đã định được thực thi |
| Tương thích | Payload cũ | Historical fixtures | Reader mới xử lý toàn bộ version hỗ trợ |
| Tương thích | Producer/consumer matrix | Cross-version tests | Các cặp cần hỗ trợ đều pass |
| Tương thích | Jackson upgrade | Regression fixtures | Không có behavior drift ngoài dự kiến |
| Bảo mật | Type handling | Unknown/disallowed type tests | Chỉ subtype cho phép được bind |
| Bảo mật | Parser/resource limits | Adversarial payload tests | Payload vượt giới hạn bị từ chối có kiểm soát |
| Bảo mật | Data exposure | Response/log assertions | Không lộ field hoặc secret ngoài contract |
| Hiệu năng | Microbenchmark | JMH raw result | Đạt budget đã xác định |
| Hiệu năng | Concurrent load | Load report | Latency/throughput/GC nằm trong SLO |
| Hiệu năng | Payload size | Size report | Không vượt transport/storage budget |

Trạng thái có thể là PASS, FAIL hoặc NOT APPLICABLE, nhưng NOT APPLICABLE phải có lý do. Không dùng “chưa có test” như một trạng thái đạt.

Ngưỡng performance cần được thống nhất trước khi chạy. Ví dụ latency p95 và p99, throughput tối thiểu, allocation/message, giới hạn payload và error rate lấy từ SLO hoặc baseline của hệ thống. Nếu chưa có SLO, ghi rõ đây là khoảng trống cần quyết định thay vì tự đặt một con số rồi gọi là tiêu chuẩn.

## 10. Ví dụ một bộ acceptance test cho PaymentEvent

DTO:

```java
public record PaymentEvent(
    int schemaVersion,
    String eventId,
    String paymentId,
    BigDecimal amount,
    String currency,
    Instant occurredAt,
    PaymentStatus status
) {}
```

Mapper được cấu hình một lần theo production:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
    .build();
```

### 10.1. Kiểm tra round-trip semantics

```java
@Test
void preservesPaymentSemantics() throws Exception {
    PaymentEvent original = new PaymentEvent(
        2,
        "evt-0001042",
        "pay-9007199254740993",
        new BigDecimal("1250.00"),
        "VND",
        Instant.parse("2026-11-12T03:30:00.123Z"),
        PaymentStatus.PAID
    );

    String json = mapper.writeValueAsString(original);
    PaymentEvent actual = mapper.readValue(json, PaymentEvent.class);

    assertEquals(original.schemaVersion(), actual.schemaVersion());
    assertEquals(original.eventId(), actual.eventId());
    assertEquals(original.paymentId(), actual.paymentId());
    assertEquals(0, original.amount().compareTo(actual.amount()));
    assertEquals(original.amount().scale(), actual.amount().scale());
    assertEquals(original.currency(), actual.currency());
    assertEquals(original.occurredAt(), actual.occurredAt());
    assertEquals(original.status(), actual.status());
}
```

### 10.2. Kiểm tra wire type

```java
@Test
void emitsContractedJsonTypes() throws Exception {
    String json = mapper.writeValueAsString(samplePayment());
    JsonNode root = mapper.readTree(json);

    assertTrue(root.get("schemaVersion").isIntegralNumber());
    assertTrue(root.get("eventId").isTextual());
    assertTrue(root.get("paymentId").isTextual());
    assertTrue(root.get("amount").isNumber());
    assertTrue(root.get("currency").isTextual());
    assertTrue(root.get("occurredAt").isTextual());
    assertTrue(root.get("status").isTextual());
}
```

### 10.3. Kiểm tra input sai

```java
@Test
void rejectsAmountWithWrongWireType() {
    String invalid = """
        {
          "schemaVersion": 2,
          "eventId": "evt-1",
          "paymentId": "pay-1",
          "amount": "1250.00",
          "currency": "VND",
          "occurredAt": "2026-11-12T03:30:00Z",
          "status": "PAID"
        }
        """;

    assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue(invalid, PaymentEvent.class)
    );
}
```

Test trên giả định contract yêu cầu amount là JSON number và mapper không bật coercion cho string-to-number. Cấu hình coercion thực tế cần được xác nhận trên mapper production.

### 10.4. Kiểm tra payload lịch sử

```java
@Test
void readsVersionOneFixture() throws Exception {
    PaymentEventV1 oldEvent = mapper.readValue(
        resourceBytes("/compatibility/payment-event/v1/complete.json"),
        PaymentEventV1.class
    );

    PaymentEvent current = migration.fromV1(oldEvent);

    assertEquals("evt-0001042", current.eventId());
    assertEquals("pay-9007199254740993", current.paymentId());
    assertEquals(0, new BigDecimal("1250.00")
        .compareTo(current.amount()));
}
```

Fixture cần là artifact lịch sử độc lập, không được tạo lại bằng mapper hiện tại ngay trong test.

### 10.5. Kiểm tra resource limit

Tạo payload vượt giới hạn nesting hoặc string length được cấu hình. Test phải xác nhận parser từ chối input, API trả lỗi phù hợp và không để lại side effect. Tránh kiểm thử bằng cách cấp phát payload khổng lồ có thể làm hỏng test runner; dùng kích thước đủ vượt ngưỡng đã đặt.

## 11. Hiệu năng phải được nghiệm thu trên cùng semantics

Khi so sánh mapper version hoặc format, trước tiên phải xác nhận output tương đương về nghiệp vụ. Nếu một serializer bỏ field, làm tròn số hoặc không ghi timestamp, nó có thể nhanh hơn vì đang làm ít việc hơn.

Quy trình:

1. Dùng cùng fixture và DTO.
2. Cấu hình mapper tương đương về contract.
3. Verify semantic output trước benchmark.
4. Tách read và write.
5. Đo payload size riêng.
6. Chạy JMH warmup/measurement/fork.
7. Thu thập allocation/GC.
8. Chạy load test với concurrency và payload mix thực tế.
9. So sánh với baseline trên cùng môi trường.
10. Ghi nhận trade-off giữa latency, throughput, memory và size.

Không kết luận từ một con số ops/second. Một thay đổi có thể tăng throughput nhưng tăng allocation hoặc p99 latency. Hãy quyết định dựa trên SLO tổng thể.

## 12. Quan sát sau khi triển khai

Nghiệm thu trước release chưa kết thúc trách nhiệm. Sau deploy, cần theo dõi các tín hiệu cho biết contract và runtime đang hoạt động đúng:

- Tỷ lệ deserialize error theo schema version và event type.
- Unknown field, enum và subtype count.
- Dead-letter queue và consumer lag.
- Request validation failure.
- Payload size distribution.
- Serialization/deserialization latency.
- CPU, heap, allocation và GC.
- Database query count/latency nếu mapping entity có liên quan.
- Response error rate và timeout.
- Log redaction và dữ liệu nhạy cảm.

Không log toàn bộ payload để theo dõi. Dùng metadata có kiểm soát như schema version, event type, byte length và correlation ID. Nếu cần mẫu payload để điều tra, áp dụng redaction, access control và retention policy.

Đặt alert theo baseline và SLO. Một tỷ lệ unknown enum tăng đột ngột có thể là dấu hiệu producer đã phát code mới trước khi consumer được nâng. Một payload size tăng bất thường có thể chỉ ra field mới hoặc object graph không mong muốn.

## 13. Rollout, rollback và kế hoạch xử lý lỗi

Trước release, xác định:

- Reader mới có hỗ trợ payload cũ không?
- Producer mới có phát dữ liệu reader cũ không đọc được không?
- Có thể rollback code mà không rollback data không?
- Có cần giữ writer V1 trong giai đoạn chuyển tiếp không?
- Nếu deserialize lỗi, message retry hay chuyển dead-letter?
- Retry có thể gây side effect trùng lặp không?
- Có thể replay payload sau khi consumer được sửa không?
- Dữ liệu nào cần giữ nguyên để audit?

Với event-driven system, không xóa message lỗi chỉ để giữ consumer lag thấp. Cần lưu lỗi, schema version và correlation ID; bảo đảm retry/dead-letter có kiểm soát. Với API request, trả lỗi contract rõ ràng và không tạo một phần dữ liệu nếu validation thất bại.

Rollback phải được kiểm tra trong bối cảnh dữ liệu đã được writer mới ghi. Rollback binary/application không tự đưa schema dữ liệu trở lại version cũ.

## 14. Những lý do khiến nghiệm thu giả tạo

| Cách kiểm tra thiếu | Điều bị bỏ sót |
| --- | --- |
| Chỉ round-trip bằng một mapper | Writer/reader cùng sai vẫn pass |
| Chỉ test một payload mẫu | Không bao phủ missing/null/biên/collection lớn |
| Chỉ kiểm tra JSON parse được | Không xác nhận semantics hoặc wire contract |
| Chỉ test Java consumer | Bỏ qua precision và coercion ở client khác |
| Chỉ test schema mới | Bỏ qua payload lịch sử |
| Chỉ bật ignoreUnknown | Có thể âm thầm mất extension field |
| Chỉ kiểm tra status 200 | Không phát hiện N+1 hoặc lộ field |
| Chỉ test payload hợp lệ | Không kiểm tra parser và type handling an toàn |
| Chỉ chạy JMH đơn luồng | Không thấy tail latency/GC dưới concurrency |
| Chỉ so payload size | Bỏ qua CPU, memory và compression cost |
| Chỉ test trước deploy | Không quan sát consumer lag và lỗi thực tế |
| Cập nhật golden file tự động | Có thể khóa một thay đổi contract sai |

Nghiệm thu cần fixture độc lập, test negative, test cross-version và số liệu thực tế. Mỗi phép kiểm tra chỉ chứng minh phạm vi mà nó đo được.

## 15. Quy trình nghiệm thu trước release

Một quy trình thực tế có thể tổ chức như sau:

1. **Chốt phạm vi:** liệt kê producer, consumer, storage, transport, format và version liên quan.
2. **Chốt contract:** field, wire type, null/default, decimal/time/ID semantics, unknown field và schema version.
3. **Chuẩn bị fixture:** payload lịch sử, payload mới, giá trị biên và invalid input.
4. **Kiểm tra tính đúng:** wire shape, semantic round-trip, validation và custom mapping.
5. **Kiểm tra tương thích:** writer/reader matrix, migration, replay và rolling deployment.
6. **Kiểm tra bảo mật:** type allowlist, parser constraints, malformed payload, mass assignment, response/log redaction.
7. **Kiểm tra hiệu năng:** JMH, load test, payload size, allocation, GC và tail latency.
8. **Kiểm tra tích hợp:** Spring mapper, HTTP/message converter, database và transaction boundary.
9. **Đánh giá evidence:** mỗi acceptance criterion có test/report/fixture liên kết.
10. **Quyết định release:** PASS, FAIL hoặc NOT APPLICABLE có lý do cho từng mục.
11. **Chuẩn bị rollout/rollback:** thứ tự nâng producer/consumer, retry, dead-letter và replay.
12. **Theo dõi sau deploy:** schema errors, latency, payload size, resource và consumer lag.

Không gộp bước “test pass” với “release approved”. Người chịu trách nhiệm phát hành cần đọc evidence, chấp nhận rủi ro còn lại và xác nhận các dependency liên quan.

## 16. Mẫu hồ sơ nghiệm thu

Một hồ sơ ngắn nhưng có thể truy vết:

```text
Change:
  Mapper/configuration:
  DTO/schema version:
  Producer:
  Consumer:
  Jackson dependency versions:

Correctness:
  Wire contract:
  Round-trip fixtures:
  Edge cases:
  Result:

Compatibility:
  Historical versions:
  Writer/reader matrix:
  Migration:
  Result:

Security:
  Allowed subtype policy:
  Parser/resource limits:
  Validation and authorization:
  Redaction:
  Negative tests:
  Result:

Performance:
  JDK/JVM/hardware:
  Dataset/profile:
  JMH result:
  Load test result:
  p95/p99:
  Allocation/GC:
  Payload size:
  Result:

Deployment:
  Rollout order:
  Rollback compatibility:
  Retry/dead-letter:
  Monitoring:
  Owner/decision:
```

Hồ sơ phải liên kết đến raw JMH result, test report, fixture, schema và commit cụ thể. Không chỉ ghi “all tests passed” vì người review không thể biết test nào đã chạy hoặc chạy trên dependency nào.

## 17. Bài thực hành tổng hợp

Xây dựng một thay đổi cho PaymentEvent có schema version 2. Payload chứa event ID, payment ID, amount, currency, occurredAt và status. Hệ thống có REST API, message consumer và JSON persistence.

Thực hiện:

1. Viết contract V2, quy định JSON type, required, null/default và schema version.
2. Chọn BigDecimal cho amount, String cho ID và Instant cho event timestamp.
3. Đăng ký JavaTimeModule và cấu hình mapper production.
4. Lưu fixture V1 từ producer cũ và fixture V2 độc lập.
5. Viết wire-shape test cho V2.
6. Viết semantic round-trip test cho decimal, timestamp và ID.
7. Viết test missing/null/zero/empty và enum unknown.
8. Viết migration V1 sang domain model hiện tại.
9. Chạy writer/reader compatibility matrix cho các cặp cần hỗ trợ.
10. Kiểm tra reader cũ khi gặp field hoặc enum mới.
11. Xác định unknown subtype policy và chỉ cho phép subtype đã đăng ký.
12. Đặt giới hạn nesting, string, number và message size theo payload hợp lệ.
13. Gửi malformed/deep/oversized payload và xác nhận bị từ chối có kiểm soát.
14. Kiểm tra request DTO không cho client gán field quản trị.
15. Kiểm tra response và log không chứa secret hoặc field nội bộ.
16. Tạo JMH benchmark cho read/write với small/medium/large fixture.
17. Đo throughput, p95/p99 ở load test, allocation, GC và output size.
18. Chạy integration test qua Spring HTTP/message converter.
19. Mô phỏng rolling deployment và rollback.
20. Lập hồ sơ evidence, đánh dấu PASS/FAIL/NOT APPLICABLE và ghi lý do.
21. Xác định metric cần theo dõi sau deploy.
22. Chỉ đưa ra quyết định release khi các gate đã có bằng chứng và người chịu trách nhiệm chấp nhận rủi ro còn lại.

Bài thực hành hoàn thành khi nhóm có thể chứng minh payload V2 đúng contract, dữ liệu V1 vẫn được đọc theo semantics, input không tin cậy bị kiểm soát, hiệu năng đạt budget của hệ thống và rollout có đường xử lý lỗi/rollback rõ ràng.

## 18. Nguyên tắc ghi nhớ

- Nghiệm thu serialization cần bốn trụ cột: tính đúng, tương thích, bảo mật và hiệu năng.
- Round-trip pass chỉ chứng minh một đường đọc ghi; nó không chứng minh contract với consumer độc lập.
- Viết acceptance criteria đo được trước khi chạy test; ngưỡng hiệu năng lấy từ SLO/baseline.
- Kiểm tra cả JSON wire shape và semantic values.
- Bảo toàn BigDecimal, currency, Instant/offset/precision và lexical ID theo contract.
- Phân biệt missing, null, empty, zero và default.
- Giữ fixture lịch sử độc lập và test ma trận writer/reader.
- Schema version khác Jackson version; chạy lại fixture khi nâng dependency.
- Dùng allowlist subtype; không bật default typing rộng cho input không tin cậy.
- Giới hạn message size, nesting, string, number, collection và concurrency.
- Deserialize không thay thế validation, authorization hoặc chống mass assignment.
- Không lộ secret trong response, exception hoặc log.
- Đo throughput, tail latency, allocation, GC và payload size bằng workload đại diện.
- Dùng JMH cho microbenchmark và load/integration test cho đường end-to-end.
- Kiểm tra cả JSON contract lẫn SQL/transport behavior khi ứng dụng có persistence hoặc broker.
- Chuẩn bị rollout, rollback, retry, dead-letter và replay trước khi phát hành.
- Lưu test report, fixture, raw benchmark, dependency version và commit để quyết định có thể tái lập.
- Sau deploy tiếp tục theo dõi schema error, consumer lag, latency, payload size và resource usage.

Một thay đổi Jackson chỉ được nghiệm thu khi dữ liệu vẫn đúng, các phiên bản cần hỗ trợ vẫn hiểu nhau, payload không thể dễ dàng làm hệ thống mất an toàn hoặc cạn tài nguyên, và hiệu năng đáp ứng yêu cầu thực tế. Hãy biến từng điều kiện thành một acceptance criterion có bằng chứng, rồi dùng ma trận bốn trụ cột để đưa ra quyết định phát hành rõ ràng và có thể kiểm tra lại.
