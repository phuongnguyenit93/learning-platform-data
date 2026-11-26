# JSON event

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module trao đổi thông tin nghiệp vụ qua những hợp đồng rõ ràng. Khi event cần được lưu trong Event Publication Registry hoặc gửi qua ranh giới hệ thống, ứng dụng phải chuyển object Java thành một định dạng dữ liệu có thể lưu trữ và truyền tải. JSON là một lựa chọn phổ biến vì dễ đọc, được nhiều ngôn ngữ hỗ trợ và có hệ sinh thái công cụ phong phú.

Serialization là quá trình chuyển object thành dữ liệu; deserialization là quá trình khôi phục dữ liệu thành object có kiểu. Với JSON event, thiết kế cần trả lời hai câu hỏi: dữ liệu được biểu diễn thế nào và consumer có thể hiểu dữ liệu đó qua nhiều phiên bản ứng dụng hay không. Một payload serialize thành công về mặt kỹ thuật vẫn có thể là một hợp đồng kém nếu nó phụ thuộc vào tên class nội bộ, thay đổi ngữ nghĩa âm thầm hoặc làm mất độ chính xác của dữ liệu.

## 1. JSON event trong luồng application events

JSON là định dạng biểu diễn dữ liệu dạng text. Object được biểu diễn bằng các cặp key/value, collection bằng array, còn giá trị có thể là string, number, boolean, null, object hoặc array. JSON không có kiểu dữ liệu riêng cho Java UUID, Instant, BigDecimal hay enum. Ứng dụng phải thống nhất cách ánh xạ các kiểu đó sang JSON.

Trong Spring Modulith, event có thể được publish trong ứng dụng và được các listener xử lý. Event Publication Registry có thể theo dõi publication của listener và lưu publication theo cấu hình persistence. Nếu payload được lưu dưới dạng JSON, ứng dụng cần serializer có thể chuyển event sang JSON và khôi phục lại khi cần. Với externalization, JSON cũng có thể là payload gửi qua messaging adapter tới consumer bên ngoài.

Hai mục đích này liên quan nhưng không đồng nhất:

- Serialization phục vụ publication persistence giúp ứng dụng lưu và khôi phục event trong vòng đời của registry.
- Serialization phục vụ integration contract tạo payload ổn định để producer và consumer độc lập trao đổi dữ liệu.

Một event nội bộ có thể chứa kiểu dữ liệu phục vụ riêng cho module, trong khi integration event cần DTO công khai được thiết kế riêng. Không nên mặc định JSON được lưu trong registry chính là contract gửi ra broker. Mỗi ranh giới có thể cần cấu trúc và chính sách versioning khác nhau.

~~~mermaid
flowchart TD
    A["Application event Java"] --> B["Event Publication Registry"]
    B --> C["Serializer cho persistence"]
    C --> D["JSON được lưu"]
    D --> E["Deserialize khi phục hồi"]
    E --> F["Listener tiếp tục xử lý"]
    A --> G["Mapping sang integration DTO"]
    G --> H["JSON integration contract"]
    H --> I["Messaging adapter / broker"]
    I --> J["Consumer deserialize theo contract"]
~~~

## 2. Thiết kế payload JSON có hợp đồng rõ ràng

Payload nên mô tả một sự kiện nghiệp vụ đã xảy ra. Ví dụ, khi đơn hàng được xác nhận, producer có thể công bố các thông tin mà consumer cần để cập nhật projection hoặc bắt đầu quy trình tiếp theo.

~~~json
{
  "eventId": "9a8b6c30-1d75-4f1a-9a20-4f1c4b4d6a11",
  "eventType": "orders.order-confirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-25T10:15:30Z",
  "aggregateId": "ORD-2026-00125",
  "payload": {
    "total": 125000.00,
    "currency": "VND"
  }
}
~~~

Một envelope có thể chia thành metadata và payload:

| Thành phần | Ý nghĩa |
|---|---|
| eventId | Định danh duy nhất của event, dùng để deduplicate |
| eventType | Tên hợp đồng ổn định, không phụ thuộc tên class Java |
| schemaVersion | Phiên bản cấu trúc và ngữ nghĩa của payload |
| occurredAt | Thời điểm sự kiện nghiệp vụ xảy ra |
| aggregateId | Định danh đối tượng nghiệp vụ liên quan |
| payload | Dữ liệu nghiệp vụ consumer được phép sử dụng |

Không phải ứng dụng nào cũng cần envelope đúng cấu trúc trên. Có thể dùng header của broker cho event type, correlation ID hoặc schema version nếu quy ước tích hợp đã xác định. Điều quan trọng là producer và consumer thống nhất nơi lưu metadata, cách đặt tên và cách xử lý khi thiếu trường.

Payload nên nhỏ và chỉ chứa dữ liệu cần thiết. Đừng serialize nguyên aggregate, entity JPA hoặc object graph của persistence chỉ vì chúng có sẵn. Việc đó có thể làm lộ cấu trúc nội bộ, kéo theo lazy relationship, gây vòng tham chiếu hoặc khiến schema thay đổi mỗi khi model nội bộ được refactor.

## 3. Ánh xạ kiểu Java sang JSON

JSON không thể hiện trực tiếp mọi kiểu Java. Hãy xác định biểu diễn chuẩn ngay từ khi thiết kế event.

| Kiểu Java | Biểu diễn JSON thường dùng | Lưu ý |
|---|---|---|
| UUID | String | Dùng định dạng UUID chuẩn |
| Instant | String ISO-8601 UTC | Tránh timestamp không có đơn vị rõ ràng |
| LocalDate | String **YYYY-MM-DD** | Không tự gắn múi giờ |
| BigDecimal | Number hoặc string theo contract | Chú ý độ chính xác ở consumer |
| Enum | String code ổn định | Không dùng ordinal |
| Collection | Array | Chỉ dựa vào thứ tự nếu contract quy định |
| Optional | Giá trị hoặc field vắng mặt | Chốt rõ semantics |
| byte[] | Base64 string | Cân nhắc kích thước payload |

**Thời gian.** Với sự kiện xảy ra tại một thời điểm cụ thể, Instant thường phù hợp vì biểu diễn một thời điểm tuyệt đối. Dùng ISO-8601 có múi giờ, thường ở UTC với hậu tố Z. LocalDate phù hợp với ngày lịch như ngày sinh hoặc ngày hiệu lực, không nên chuyển thành Instant nếu nghiệp vụ không định nghĩa thời điểm trong ngày.

**Số tiền.** BigDecimal giữ độ chính xác thập phân ở Java, nhưng nhiều consumer JavaScript phân tích JSON number thành IEEE-754 Number và có thể mất độ chính xác với số lớn hoặc số thập phân đặc biệt. Hãy chọn một quy ước rõ ràng: dùng số nguyên theo đơn vị nhỏ nhất của tiền tệ, hoặc chuỗi thập phân có định dạng được quy định. Nếu dùng JSON number, mọi consumer cần có cách parse chính xác và thống nhất scale.

**Enum.** Không serialize enum bằng ordinal vì thay đổi thứ tự khai báo sẽ làm đổi ý nghĩa dữ liệu cũ. Dùng code dạng string ổn định như **CONFIRMED**, hoặc một giá trị công khai được ánh xạ rõ ràng. Nếu tên enum trong code có thể đổi, hãy tách contract code khỏi tên hằng Java.

**Collection.** JSON array có thứ tự. Nếu thứ tự có ý nghĩa nghiệp vụ, hãy mô tả nó trong contract. Nếu không, consumer không nên suy ra thứ tự xử lý chỉ từ thứ tự phần tử được serialize.

## 4. Dùng Jackson để serialize và deserialize

Trong các ứng dụng Spring Boot, Jackson thường là thư viện JSON được dùng cùng Spring MVC và messaging. Nên sử dụng ObjectMapper do Spring quản lý để các thành phần dùng chung cấu hình module, naming strategy, date format và custom serializer.

Ví dụ một integration DTO dùng record:

~~~java
public record OrderConfirmedEvent(
    UUID eventId,
    String orderId,
    Instant occurredAt,
    int schemaVersion,
    BigDecimal total,
    String currency
) {}
~~~

Jackson có thể serialize record thành JSON và khôi phục lại record khi phiên bản Jackson hỗ trợ record (Jackson 2.12 trở lên):

~~~java
@Component
class OrderEventJsonCodec {

    private final ObjectMapper objectMapper;

    OrderEventJsonCodec(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    String serialize(OrderConfirmedEvent event)
            throws JsonProcessingException {
        return objectMapper.writeValueAsString(event);
    }

    OrderConfirmedEvent deserialize(String json)
            throws JsonProcessingException {
        return objectMapper.readValue(
            json,
            OrderConfirmedEvent.class
        );
    }
}
~~~

Khi dùng Instant hoặc các kiểu ngày giờ của java.time, ObjectMapper cần hỗ trợ Java Time. Trong Spring Boot, cấu hình Jackson thường đã đăng ký module tương ứng khi dependency phù hợp có mặt. Với ứng dụng tự cấu hình ObjectMapper, có thể đăng ký JavaTimeModule và thống nhất việc ghi ngày giờ dưới dạng chuỗi:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Ví dụ trên minh họa cấu hình Jackson độc lập. Trong ứng dụng Spring Boot, hãy ưu tiên cấu hình ObjectMapper dùng chung qua cơ chế cấu hình của Spring thay vì tự tạo một mapper riêng cho từng listener. Hai mapper có cấu hình khác nhau có thể serialize cùng event thành hai payload khác nhau.

Kết quả JSON cần được xem như contract. Không dựa vào thứ tự property trong chuỗi JSON vì thứ tự object member không mang ý nghĩa theo chuẩn JSON. Khi so sánh payload trong test, nên so sánh cấu trúc JSON hoặc parse thành cây dữ liệu thay vì so sánh chuỗi nguyên văn, trừ khi kiểm tra canonical JSON là mục tiêu cụ thể.

## 5. Cấu hình tên field và định dạng có chủ đích

Tên field là một phần của contract. Nếu Java field được đặt theo camelCase, JSON thường cũng dùng camelCase. Nếu hệ thống tích hợp yêu cầu snake_case, hãy cấu hình naming strategy nhất quán hoặc khai báo rõ bằng annotation.

~~~java
public record CustomerAddress(
    @JsonProperty("street_name") String streetName,
    @JsonProperty("postal_code") String postalCode
) {}
~~~

Các annotation như JsonProperty, JsonFormat, JsonInclude và JsonIgnore có thể thay đổi cách dữ liệu được công bố. Chúng cần được xem xét như một phần của contract:

- **JsonProperty** xác định tên field công khai.
- **JsonFormat** định dạng ngày giờ hoặc giá trị theo quy ước cụ thể.
- **JsonInclude** quyết định khi nào field bị bỏ khỏi payload.
- **JsonIgnore** loại field khỏi serialization/deserialization theo cấu hình tương ứng.

Đặc biệt, bỏ field null khác với gửi field có giá trị null. Consumer có thể hiểu field vắng mặt là không được cung cấp hoặc giữ nguyên giá trị cũ, còn null là xóa giá trị. Hãy quy định rõ semantics cho từng field có thể vắng mặt.

Không nên dùng annotation chỉ để làm payload ngắn hơn mà chưa đánh giá consumer. Ví dụ, cấu hình bỏ mọi field null có thể làm thay đổi ý nghĩa cập nhật trong consumer. Hợp đồng nên quy định field bắt buộc, tùy chọn, nullable và giá trị mặc định.

## 6. Deserialize an toàn và xử lý dữ liệu không hợp lệ

Deserialize là một điểm tiếp xúc với dữ liệu bên ngoài. Consumer không nên mặc định JSON luôn hợp lệ hoặc đến từ producer đáng tin cậy.

Một quy trình nhận event nên gồm các bước:

1. Kiểm tra kích thước message và encoding.
2. Parse JSON và từ chối cú pháp không hợp lệ.
3. Kiểm tra event type và schema version có được hỗ trợ không.
4. Kiểm tra field bắt buộc, kiểu dữ liệu, giới hạn độ dài và miền giá trị.
5. Kiểm tra quyền truy cập, tenant hoặc chữ ký nếu contract yêu cầu.
6. Chuyển DTO sang command hoặc model nội bộ qua adapter.
7. Xử lý idempotency trước khi thực hiện tác dụng phụ.

Không bật Jackson default typing một cách rộng rãi cho JSON đến từ nguồn không tin cậy. Metadata kiểu class Java như **@class** có thể làm consumer phụ thuộc vào implementation và mở rộng bề mặt tấn công khi cấu hình polymorphic deserialization không an toàn. Nếu cần nhiều loại event, dùng discriminator như eventType với danh sách kiểu được cho phép và mapping tường minh.

Không deserialize trực tiếp payload thành entity JPA. Hãy parse thành DTO có giới hạn, validate dữ liệu, sau đó gọi use case để thay đổi domain model. Điều này tránh việc dữ liệu bên ngoài điều khiển trực tiếp trạng thái persistence hoặc bỏ qua quy tắc nghiệp vụ.

Khi parse lỗi, ghi log có eventId hoặc message identifier nếu có, event type, schema version và nguyên nhân. Không log toàn bộ payload nếu chứa thông tin cá nhân hoặc bí mật. Với lỗi tạm thời, có thể retry theo chính sách. Với JSON sai cú pháp hoặc schema không được hỗ trợ, retry liên tục thường không giúp khắc phục; cần dead-letter hoặc quy trình sửa contract.

## 7. Schema evolution và tương thích phiên bản

Event JSON có thể tồn tại trong broker, registry, archive hoặc log lâu hơn phiên bản ứng dụng đã tạo ra nó. Producer và consumer cũng có thể được triển khai ở các thời điểm khác nhau. Vì vậy, thay đổi DTO Java không tự động là thay đổi tương thích.

Một số thay đổi thường dễ tương thích hơn:

- Thêm field tùy chọn mới nếu consumer cũ bỏ qua field không biết.
- Giữ nguyên tên, kiểu và ý nghĩa của field hiện có.
- Duy trì giá trị mặc định hợp lý khi consumer cần field mới.
- Cho phép consumer xử lý phiên bản payload được công bố trong thời gian chuyển tiếp.

Một số thay đổi có nguy cơ phá vỡ contract:

- Xóa field mà consumer đang sử dụng.
- Đổi tên field hoặc đổi kiểu dữ liệu.
- Đổi đơn vị đo, múi giờ hoặc ý nghĩa nghiệp vụ.
- Đổi enum code hoặc cách biểu diễn số tiền.
- Chuyển field nullable thành bắt buộc mà không có migration.

Ví dụ, field **total** trước đây là tổng tiền trước thuế nhưng nay được hiểu là tổng tiền sau thuế. JSON vẫn hợp lệ và kiểu dữ liệu không đổi, nhưng ngữ nghĩa đã thay đổi. Đây là breaking change dù serializer không báo lỗi.

Có thể quản lý schema bằng JSON Schema hoặc một schema registry nếu hệ thống có nhiều producer/consumer. Schema mô tả field, kiểu dữ liệu, required, nullable, enum, format và quy tắc tương thích. Dù có công cụ quản lý schema, đội phát triển vẫn cần review thay đổi ngữ nghĩa và kiểm thử consumer thực tế.

Khi thay đổi không tương thích, cân nhắc phát event type mới hoặc tăng major version của contract. Duy trì thời gian chạy song song nếu consumer cần nâng cấp theo nhịp riêng. Tránh đổi class Java rồi hy vọng mọi consumer tự thích nghi.

## 8. Serialization trong Event Publication Registry

Event Publication Registry theo dõi publication cần được xử lý bởi listener. Khi dùng cơ chế lưu trữ bền vững, event cần được biểu diễn để lưu và khôi phục qua thời gian. Serializer được chọn phải hỗ trợ kiểu event ứng dụng sử dụng và phải có thể đọc lại dữ liệu đã ghi.

Với JSON serializer, cần quan tâm:

- Kiểu event có thể được xác định lại khi deserialize hay không.
- Các module Jackson cần thiết có sẵn trong ứng dụng hay không.
- Thay đổi class hoặc package có ảnh hưởng tới publication còn tồn đọng hay không.
- Phiên bản ứng dụng mới có thể đọc JSON do phiên bản cũ lưu hay không.
- Custom serializer/deserializer có được duy trì tương thích qua các lần nâng cấp không.

Đặc biệt, publication chưa hoàn tất có thể được khôi phục sau khi ứng dụng đã deploy phiên bản mới. Nếu phiên bản mới không còn đọc được payload cũ, quá trình resubmit có thể thất bại dù JSON cũ vẫn hợp lệ về cú pháp. Vì vậy, khi đổi event class, package hoặc schema, hãy có kế hoạch chuyển đổi dữ liệu publication còn tồn đọng hoặc duy trì khả năng deserialize tương thích.

Nếu cần custom serializer cho publication persistence, hãy dùng extension point mà phiên bản Spring Modulith của ứng dụng cung cấp và kiểm tra cấu hình được chọn. Không giả định serializer dùng cho HTTP hoặc broker tự động là serializer đang được Event Publication Registry sử dụng.

Cũng cần phân biệt publication được đánh dấu completed với việc consumer downstream đã xử lý xong. Registry theo dõi vòng đời publication trong phạm vi ứng dụng và cơ chế adapter tương ứng; acknowledgement nghiệp vụ của hệ thống khác là một hợp đồng riêng.

## 9. Serialization và externalization

Một application event có thể đi qua nhiều ranh giới:

- Trong ứng dụng, registry cần lưu payload để hỗ trợ theo dõi và phục hồi publication.
- Ở ranh giới hệ thống, integration event cần được chuyển thành payload phù hợp với contract bên ngoài.
- Ở consumer, JSON được parse và ánh xạ vào mô hình nội bộ.

Không nhất thiết dùng cùng một DTO hoặc cùng một ObjectMapper cho cả ba mục đích. Event nội bộ có thể thay đổi cùng module; integration DTO cần ổn định hơn. Nếu dùng cùng một class cho cả hai, thay đổi nội bộ có thể vô tình làm thay đổi JSON công khai.

Một mapping rõ ràng giúp bảo vệ boundary:

~~~java
OrderConfirmedIntegrationEvent toIntegrationEvent(
        OrderConfirmed domainEvent) {
    return new OrderConfirmedIntegrationEvent(
        domainEvent.eventId(),
        domainEvent.orderId().value(),
        domainEvent.occurredAt(),
        1,
        domainEvent.total().amount(),
        domainEvent.total().currency()
    );
}
~~~

Ví dụ trên cho thấy module chuyển từ domain event sang integration DTO. Integration DTO có thể có tên field, schema version và kiểu dữ liệu phù hợp với consumer. Adapter externalization chịu trách nhiệm serialize DTO theo contract và gửi tới destination đã cấu hình.

## 10. Định danh, trùng lặp và tính ổn định

Serialization không đảm bảo event chỉ được giao một lần. Khi broker hoặc adapter không chắc lần gửi trước đã thành công hay chưa, message có thể được gửi lại. Consumer cần idempotent để một event được xử lý lặp không tạo thêm tác dụng phụ.

Các nguyên tắc:

- Tạo eventId một lần khi event được hình thành.
- Giữ eventId không đổi trong mọi lần retry hoặc replay của cùng event.
- Lưu eventId đã xử lý bằng unique constraint hoặc inbox table.
- Ghi dấu xử lý và cập nhật dữ liệu nghiệp vụ trong cùng transaction.
- Với API ngoài, dùng idempotency key nếu nhà cung cấp hỗ trợ.
- Dùng aggregateId và sequence/version nếu cần kiểm soát thứ tự.

Một event có thể serialize thành JSON giống nhau qua các lần retry nếu dữ liệu không đổi, nhưng không nên dựa vào byte-for-byte equality làm định danh. JSON object không quy định thứ tự property; serializer có thể thay đổi thứ tự field, khoảng trắng hoặc cách escape mà không đổi ý nghĩa dữ liệu. Hãy dùng eventId để định danh event.

Nếu cần hash hoặc chữ ký số, cần quy định cách canonicalize JSON, thuật toán, encoding và các field được ký. Hash của hai chuỗi JSON khác thứ tự property có thể khác dù chúng biểu diễn cùng một object. Không tự dùng chuỗi JSON tùy ý làm dữ liệu ký.

## 11. Quan sát và xử lý lỗi serialization

Lỗi serialization có thể xảy ra khi event chứa kiểu không được hỗ trợ, vòng tham chiếu, dữ liệu quá lớn hoặc custom serializer phát sinh exception. Lỗi deserialization có thể xảy ra khi payload sai cú pháp, thiếu field bắt buộc, schema không tương thích hoặc kiểu dữ liệu đã thay đổi.

Nên theo dõi:

- Số lần serialize/deserialize thất bại theo event type.
- Publication chưa hoàn tất do lỗi serializer hoặc adapter.
- Tuổi publication tồn đọng lâu nhất.
- Số message bị từ chối do schema version không hỗ trợ.
- Số message chuyển vào dead-letter queue.
- Thời gian serialize, gửi và deserialize với payload lớn.

Log nên có eventId, event type, schema version, listener hoặc destination, correlation ID và exception class. Tránh log nội dung nhạy cảm. Với lỗi dữ liệu không hợp lệ, lưu thông tin chẩn đoán đủ để điều tra theo chính sách retention và quyền truy cập.

Phân biệt lỗi tạm thời và lỗi cố định. Lỗi kết nối broker có thể retry theo backoff. JSON malformed hoặc schema version không được hỗ trợ thường cần sửa producer/consumer hoặc chuyển sang dead-letter để xử lý. Retry không giới hạn một payload không thể parse sẽ làm hàng đợi bị nghẽn.

## 12. Kiểm thử JSON event

Kiểm thử serialization cần xác nhận cả dữ liệu được ghi ra và khả năng đọc lại. Một test chỉ kiểm tra rằng ObjectMapper không ném exception chưa đủ để chứng minh contract đúng.

Các kịch bản nên có:

1. **Round-trip:** serialize DTO rồi deserialize lại, xác nhận các field giữ nguyên giá trị.
2. **Golden JSON:** so sánh payload với fixture contract đã được review, kiểm tra tên field và format.
3. **Date/time:** xác nhận Instant được ghi theo format UTC đã thống nhất và đọc lại đúng thời điểm.
4. **Decimal:** xác nhận số tiền không bị mất precision hoặc scale ngoài quy ước.
5. **Null và absent:** kiểm tra sự khác nhau giữa field vắng mặt, null và giá trị mặc định.
6. **Enum:** xác nhận code string ổn định và giá trị không được hỗ trợ được xử lý có chủ đích.
7. **Unknown fields:** xác nhận consumer xử lý field mới theo chính sách tương thích.
8. **Old payload:** deserialize fixture từ phiên bản contract cũ để bảo đảm publication còn tồn đọng có thể được phục hồi.
9. **Malformed payload:** xác nhận JSON sai cú pháp hoặc sai kiểu bị từ chối và được quan sát.
10. **Security:** xác nhận payload không chứa field nội bộ hoặc dữ liệu nhạy cảm ngoài contract.

Với Spring Modulith, cần kiểm thử đường đi qua publication persistence nếu ứng dụng dựa vào registry để khôi phục event. Test serializer độc lập không chứng minh rằng cấu hình registry thực tế đang dùng cùng serializer hoặc có thể đọc lại dữ liệu sau khi ứng dụng nâng cấp.

## 13. Quy trình thiết kế JSON event

Khi tạo một event JSON mới, có thể thực hiện theo trình tự:

1. Xác định event là nội bộ hay integration contract.
2. Chọn DTO bất biến, tránh entity và object graph của persistence.
3. Chốt event type, eventId, schema version và metadata cần thiết.
4. Quy định cách biểu diễn thời gian, số tiền, enum, null và collection.
5. Cấu hình Jackson dùng chung và module cho kiểu dữ liệu cần serialize.
6. Cấu hình serializer persistence của Event Publication Registry nếu ứng dụng lưu event bền vững.
7. Tách mapping integration DTO khỏi domain model khi event đi ra ngoài.
8. Xác định chính sách schema evolution và khả năng đọc payload cũ.
9. Kiểm thử round-trip, golden JSON, compatibility, malformed payload và duplicate delivery.
10. Theo dõi lỗi serialization, publication tồn đọng và message bị dead-letter.

JSON giúp application events dễ lưu trữ và trao đổi giữa các hệ thống, nhưng định dạng không tự tạo ra một contract bền vững. Khi payload có schema rõ ràng, kiểu dữ liệu được biểu diễn nhất quán, serializer được cấu hình có chủ đích và consumer xử lý phiên bản cùng duplicate delivery đúng cách, event có thể được lưu, phục hồi và truyền qua ranh giới ứng dụng một cách đáng tin cậy.

