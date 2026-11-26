# EventSerializer

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application event có thể được lưu cùng publication để Spring Modulith theo dõi việc giao sự kiện đến listener và phục hồi khi xử lý chưa hoàn tất. Muốn lưu và đọc lại publication, ứng dụng cần chuyển object event thành một dạng dữ liệu có thể lưu trữ, sau đó tái tạo event khi cần. **EventSerializer** là điểm mở rộng đảm nhiệm ranh giới chuyển đổi này trong cơ chế publication của Spring Modulith.

Serialization ảnh hưởng trực tiếp đến khả năng phục hồi. Một event có thể được ghi ở phiên bản ứng dụng hôm nay nhưng chỉ được đọc lại sau một lần deploy, khi class, package hoặc cấu trúc dữ liệu đã thay đổi. Vì vậy, serializer phải tạo ra biểu diễn ổn định, có thể đọc lại và có chiến lược tương thích theo thời gian.

## 1. EventSerializer giải quyết vấn đề gì?

Trong bộ nhớ, application event là một object Java. Database hoặc kho publication cần lưu một dạng biểu diễn như JSON hoặc chuỗi có cấu trúc. Khi publication được phục hồi, ứng dụng phải giải mã biểu diễn đó thành object phù hợp để listener tiếp tục xử lý.

Luồng khái niệm:

1. Publisher tạo application event.
2. Publication registry ghi nhận event và listener liên quan.
3. EventSerializer chuyển object event thành dữ liệu có thể lưu trữ.
4. Publication cùng dữ liệu đã serialize được lưu theo transaction và cơ chế lưu trữ đã cấu hình.
5. Khi cần phục hồi, dữ liệu được đọc và EventSerializer tái tạo object event.
6. Listener nhận event và tiếp tục xử lý theo cơ chế publication.

EventSerializer vì vậy tạo ranh giới giữa object Java trong runtime và biểu diễn event được lưu bền vững. Nó giúp registry không phải tự biết chi tiết cách chuyển đổi từng kiểu event.

Cần phân biệt ba lớp thường bị nhầm lẫn:

| Lớp | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Event object | Ứng dụng đang phát ra sự thật nghiệp vụ nào? | Record OrderConfirmed |
| Serialization cho publication | Làm sao lưu object và đọc lại nó khi phục hồi? | EventSerializer chuyển object thành payload lưu trữ |
| Serialization cho transport | Làm sao đóng gói message để broker hoặc hệ thống ngoài hiểu? | JSON message, header, content type, key và partition |

EventSerializer của publication registry phục vụ việc lưu và phục hồi publication trong ứng dụng. Cơ chế externalization có thể sử dụng adapter hoặc message converter của transport để tạo message gửi ra ngoài. Hai luồng có thể cùng dùng JSON nhưng không mặc nhiên là cùng một serializer hoặc cùng một hợp đồng. Khi thay đổi EventSerializer, cần hiểu chính xác phạm vi dữ liệu bị ảnh hưởng.

## 2. Vị trí của EventSerializer trong Spring Modulith

Spring Modulith tổ chức publication registry để theo dõi trạng thái giao application event. Registry cần lưu đủ thông tin để biết event nào được giao cho listener nào, publication đã hoàn tất hay còn dang dở và có thể phục hồi thế nào.

EventSerializer là một SPI (Service Provider Interface) cho bước chuyển đổi dữ liệu event. Ứng dụng có thể sử dụng implementation mặc định phù hợp với cấu hình và phiên bản Spring Modulith, hoặc cung cấp implementation riêng khi có yêu cầu cụ thể.

Trong các cấu hình phổ biến, serialization dựa trên Jackson là lựa chọn thuận tiện vì JSON dễ quan sát, hỗ trợ nhiều kiểu dữ liệu và có thể được tiêu thụ bởi công cụ khác. Tuy vậy, định dạng lưu trữ thực tế, cách ghi nhận kiểu event và API của SPI phụ thuộc phiên bản Spring Modulith cùng module lưu trữ được sử dụng.

Khi triển khai, hãy xem tài liệu API đúng phiên bản đang dùng để xác nhận package, chữ ký phương thức, kiểu dữ liệu trả về và cách đăng ký bean. Không nên sao chép chữ ký từ một phiên bản khác hoặc tự tạo một interface cùng tên trong ứng dụng.

## 3. Chọn định dạng serialization

### JSON

JSON là lựa chọn phổ biến cho event vì dễ đọc, dễ kiểm tra và không gắn chặt với runtime Java. Các hệ thống viết bằng ngôn ngữ khác có thể đọc JSON nếu hợp đồng trường và kiểu dữ liệu được mô tả rõ.

JSON phù hợp khi:

- Event có cấu trúc dữ liệu tương đối ổn định.
- Payload cần được quan sát trong quá trình vận hành.
- Consumer hoặc công cụ khác cần đọc dữ liệu.
- Có yêu cầu tương thích giữa nhiều phiên bản ứng dụng.

JSON không tự giải quyết schema evolution. Nếu publisher đổi tên trường, đổi đơn vị hoặc đổi ý nghĩa một thuộc tính, payload vẫn là JSON hợp lệ nhưng consumer có thể xử lý sai.

### Định dạng nhị phân

Định dạng nhị phân hoặc schema-based như Avro hay Protocol Buffers có thể phù hợp khi hệ thống cần payload nhỏ, schema rõ ràng, kiểm soát tương thích và thông lượng lớn. Đổi lại, nhóm phát triển phải quản lý schema, schema registry hoặc cơ chế phân phối schema, code generation và quy trình nâng cấp.

Chọn định dạng theo nhu cầu thực tế của hệ thống. Đừng chuyển sang định dạng phức tạp chỉ vì nó có benchmark tốt hơn trong một phép đo riêng lẻ.

### Java native serialization

Không nên dùng Java native serialization làm hợp đồng lưu trữ dài hạn cho application event. Nó gắn dữ liệu với class Java và cơ chế serialization của JVM, khiến thay đổi class khó kiểm soát và làm giảm khả năng đọc từ hệ thống khác. Dữ liệu serialized không đáng tin cậy cũng tạo thêm rủi ro bảo mật nếu bị deserialize không an toàn.

## 4. Thiết kế event để có thể serialize ổn định

Serializer chỉ chuyển đổi object; nó không thể tự làm cho mô hình event trở nên ổn định. Chất lượng serialization bắt đầu từ thiết kế event.

Ưu tiên DTO hoặc record bất biến với trường dữ liệu rõ ràng. Tránh lưu trực tiếp entity ORM, aggregate có quan hệ lazy-loading, proxy, object chứa session hoặc object graph quá lớn.

Ví dụ event gọn:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt,
    int schemaVersion,
    BigDecimal total,
    String currency
) {}
~~~

Event này chứa định danh, thời điểm, version và số tiền. Những trường này có ý nghĩa nghiệp vụ rõ ràng, không phụ thuộc vào trạng thái persistence của entity Order.

Các kiểu dữ liệu thường phù hợp:

| Dữ liệu | Cách biểu diễn nên cân nhắc |
|---|---|
| Định danh | UUID hoặc chuỗi có quy tắc rõ |
| Thời điểm | Instant theo quy ước UTC hoặc timestamp có offset |
| Tiền | BigDecimal kèm currency |
| Số lượng | Kiểu số cùng đơn vị được xác định |
| Trạng thái | Mã chuỗi ổn định và quy tắc xử lý giá trị mới |
| Danh sách | Collection có schema phần tử rõ ràng |
| Giá trị tùy chọn | Quy định rõ khác biệt giữa thiếu, null và giá trị mặc định |

Không serialize một object chỉ vì nó có thể chuyển thành JSON. Cần xác định mỗi trường có ý nghĩa gì, ai sở hữu nó và liệu consumer có thể hiểu trường đó sau nhiều lần triển khai hay không.

## 5. Cấu hình Jackson cho event

Khi sử dụng Jackson làm nền tảng serialization, cấu hình ObjectMapper phải nhất quán giữa lúc ghi và lúc đọc. Các kiểu như Instant, LocalDate hoặc OffsetDateTime cần module và quy ước biểu diễn phù hợp. Nên dùng chuỗi thời gian có định dạng xác định thay vì số timestamp không có quy ước rõ.

Ví dụ cấu hình ObjectMapper cho DTO event:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper eventObjectMapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Ví dụ chuyển đổi DTO để minh họa nguyên tắc round-trip:

~~~java
String payload = eventObjectMapper.writeValueAsString(event);

OrderConfirmed restored = eventObjectMapper.readValue(
    payload,
    OrderConfirmed.class
);
~~~

Đây là minh họa sử dụng Jackson trực tiếp. Trong ứng dụng Spring Modulith, implementation EventSerializer cần tuân thủ SPI của đúng phiên bản và sử dụng cấu hình mapper phù hợp với registry. Không mặc định rằng việc tạo một ObjectMapper bất kỳ sẽ tự động thay thế serializer đang được Spring Modulith sử dụng.

Các quyết định cấu hình cần được thống nhất:

- Quy tắc đặt tên field, ví dụ camelCase hoặc snake_case.
- Cách biểu diễn ngày giờ, timezone và độ chính xác.
- Cách biểu diễn enum.
- Quy tắc xử lý field không biết hoặc field bị thiếu.
- Cách xử lý null và giá trị mặc định.
- Kiểu số và độ chính xác của tiền tệ.
- Quy tắc polymorphism nếu event có kiểu con.
- Charset và content type của payload.

Tránh bật polymorphic default typing rộng cho dữ liệu đến từ nguồn không tin cậy. Nếu cần hỗ trợ nhiều kiểu event, hãy dùng cơ chế type mapping có kiểm soát và chỉ cho phép những kiểu đã được đăng ký.

## 6. Event type và metadata

Để đọc lại payload, hệ thống cần biết kiểu event đích. Metadata kiểu event có thể được lưu riêng hoặc được mang trong biểu diễn đã serialize, tùy implementation. Không nên giả định payload JSON luôn đủ để suy ra class Java nếu hợp đồng không có thông tin type rõ ràng.

Tên class và package Java thường không phải định danh hợp đồng bền vững. Khi đổi package hoặc refactor class, dữ liệu cũ có thể vẫn chứa tên kiểu cũ. Nếu cơ chế lưu trữ dùng tên kiểu Java, cần có kế hoạch tương thích hoặc ánh xạ tên cũ sang kiểu mới.

Với event công khai, nên phân biệt:

- **Event type:** tên nghiệp vụ ổn định, ví dụ orders.order-confirmed.
- **Schema version:** phiên bản cấu trúc payload.
- **Java class:** implementation cụ thể trong codebase.
- **Transport headers:** metadata phục vụ định tuyến, trace hoặc content negotiation.

Không dùng một trường duy nhất để gánh tất cả vai trò trên. Event type có thể ổn định trong khi class Java thay đổi; schema version có thể tăng mà ngữ nghĩa event vẫn giữ nguyên.

## 7. Schema evolution và khả năng đọc dữ liệu cũ

Publication có thể tồn tại lâu hơn vòng đời của một bản build. Khi ứng dụng được deploy phiên bản mới, event đã serialize từ phiên bản cũ vẫn có thể cần deserialize và giao lại.

Ví dụ phiên bản đầu có payload:

~~~json
{
  "eventId": "a5f5f6e0-1c4b-4e54-a22a-8b4b2bb32d11",
  "orderId": "9d3a3c10-7c4b-4d16-9bb2-2f4a9b5c91c0",
  "occurredAt": "2026-11-25T10:30:00Z",
  "schemaVersion": 1,
  "total": 125000,
  "currency": "VND"
}
~~~

Sau đó phiên bản mới cần bổ sung kênh bán hàng. Nếu trường mới là tùy chọn và có giá trị mặc định hợp lý, consumer cũ và mới có thể tương thích tùy theo quy tắc đọc.

Các nguyên tắc an toàn:

- Ưu tiên thêm trường tùy chọn thay vì đổi hoặc xóa trường đang dùng.
- Xác định giá trị mặc định khi đọc payload thiếu trường.
- Không đổi đơn vị hoặc ngữ nghĩa của trường mà giữ nguyên tên.
- Không tái sử dụng một giá trị enum cũ cho ý nghĩa mới.
- Giữ khả năng đọc payload cũ trong thời gian publication còn được phép phục hồi.
- Có fixture của các schema cũ để kiểm tra sau mỗi lần nâng cấp.
- Dùng upcaster hoặc migration có kiểm soát khi cấu trúc cũ cần chuyển đổi trước khi listener xử lý.

Nếu thay đổi không tương thích, hãy phát hành schema hoặc event type mới và lập kế hoạch chuyển đổi consumer. Không xóa hỗ trợ schema cũ khi vẫn còn publication cũ có thể được gửi lại.

## 8. Deserialize an toàn và xử lý lỗi

Deserialize là một thao tác có thể thất bại. Nguyên nhân thường gặp gồm:

- Payload bị cắt, sai encoding hoặc hỏng dữ liệu.
- Field bắt buộc không tồn tại hoặc có kiểu không hợp lệ.
- Class hoặc event type cũ không còn được nhận diện.
- Schema version không được hỗ trợ.
- Cấu hình mapper lúc đọc khác với lúc ghi.
- Payload có giá trị nằm ngoài miền hợp lệ của event.

Không nên xử lý lỗi deserialize bằng cách âm thầm trả về object rỗng hoặc bỏ qua publication. Làm vậy có thể khiến hệ thống đánh dấu event đã hoàn tất dù listener chưa thực sự xử lý đúng.

Một quy trình xử lý lỗi nên:

1. Ghi nhận publication ID, event type, schema version và nguyên nhân lỗi.
2. Giữ lại dữ liệu gốc theo chính sách bảo mật và retention để có thể điều tra.
3. Phân biệt lỗi tạm thời do cấu hình hoặc hạ tầng với lỗi payload không thể đọc.
4. Cách ly publication lỗi định dạng hoặc schema không hỗ trợ để tránh retry vô hạn.
5. Chỉ resubmit sau khi nguyên nhân đã được khắc phục.
6. Ghi lại kết quả phục hồi và bảo đảm publication chỉ được đánh dấu hoàn tất sau khi listener xử lý thành công.

Không log toàn bộ payload nếu nó có dữ liệu cá nhân hoặc bí mật. Có thể dùng hash, event ID, type, version và thông tin lỗi đã được làm sạch để truy vết.

## 9. Tùy biến EventSerializer khi nào?

Implementation mặc định thường đủ dùng nếu event là DTO đơn giản, định dạng lưu trữ phù hợp và cấu hình Jackson hiện có đáp ứng yêu cầu.

Cân nhắc implementation riêng khi có nhu cầu cụ thể:

- Định dạng serialization bắt buộc theo chuẩn tổ chức.
- Cần ánh xạ event type ổn định thay vì phụ thuộc class name.
- Cần xử lý schema version hoặc chuyển đổi payload cũ.
- Cần hỗ trợ kiểu dữ liệu đặc thù.
- Cần chuẩn hóa metadata hoặc content type.
- Có yêu cầu mã hóa payload ở lớp lưu trữ với khóa và quy trình quản lý rõ ràng.

Một custom EventSerializer nên tuân thủ các đặc tính:

- **Deterministic:** cùng một event và cùng cấu hình tạo ra biểu diễn nhất quán.
- **Round-trip:** dữ liệu được serialize có thể deserialize thành event tương đương về ngữ nghĩa.
- **Thread-safe:** có thể được sử dụng đồng thời nếu ứng dụng chạy nhiều listener hoặc instance.
- **Không có side effect nghiệp vụ:** không gọi dịch vụ ngoài hoặc thay đổi trạng thái domain trong lúc serialize.
- **Có lỗi rõ ràng:** không che giấu payload không hợp lệ bằng giá trị mặc định.
- **Tương thích:** có chính sách đọc dữ liệu từ các phiên bản trước.
- **Quan sát được:** lỗi có event type và publication context đủ để điều tra mà không lộ payload nhạy cảm.

Không tùy biến serializer chỉ để đổi cách format JSON cho đẹp. Nếu thay đổi không giải quyết yêu cầu lưu trữ, tương thích hoặc vận hành cụ thể, implementation mặc định thường dễ bảo trì hơn.

## 10. Minh họa ranh giới của custom serializer

Hợp đồng dưới đây là pseudocode để mô tả trách nhiệm, không phải chữ ký API chính thức của Spring Modulith:

~~~java
interface EventSerializer {
    SerializedEvent serialize(Object event);

    Object deserialize(SerializedEvent serializedEvent);
}
~~~

Một implementation thực tế cần sử dụng đúng interface và kiểu dữ liệu do phiên bản Spring Modulith cung cấp. Pseudocode chỉ làm rõ hai chiều chuyển đổi: từ event object sang representation và từ representation về event object.

Ví dụ logic nội bộ dựa trên Jackson có thể được hình dung như sau:

~~~java
final class JsonEventCodec {

    private final ObjectMapper objectMapper;

    JsonEventCodec(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    String encode(Object event) throws JsonProcessingException {
        return objectMapper.writeValueAsString(event);
    }

    <T> T decode(String payload, Class<T> eventType)
            throws JsonProcessingException {
        return objectMapper.readValue(payload, eventType);
    }
}
~~~

Đây là codec minh họa, chưa phải implementation EventSerializer hoàn chỉnh. Adapter thực tế còn phải đáp ứng kiểu metadata, type resolution, exception contract và cách đăng ký mà SPI của phiên bản ứng dụng yêu cầu.

Khi viết custom serializer, không nên tự đoán package hoặc chữ ký API. Hãy dựa vào dependency và tài liệu đúng phiên bản Spring Modulith của dự án để tích hợp adapter.

## 11. Serialization cho publication và externalization

Một ứng dụng có thể vừa lưu publication nội bộ vừa externalize event ra broker. Hai mục tiêu này liên quan nhưng khác nhau:

- Publication registry cần lưu dữ liệu để phục hồi việc giao event đến listener.
- Externalization cần tạo message theo hợp đồng transport, destination và metadata mà consumer bên ngoài hiểu.
- Broker có thể yêu cầu key, header, partition, content type hoặc schema registry riêng.
- Consumer bên ngoài có thể dùng một schema không trùng với class Java nội bộ.

Do đó, không nên coi EventSerializer là nơi duy nhất quyết định wire format của mọi message. Hãy xác định rõ serializer nào được dùng ở mỗi chặng và kiểm tra cả hai luồng khi thay đổi DTO hoặc schema.

Ví dụ, event nội bộ có thể chứa thêm dữ liệu phục vụ listener trong ứng dụng. Integration payload nên được ánh xạ thành DTO riêng, chỉ giữ các trường công bố cho consumer. Điều này giúp thay đổi nội bộ không làm thay đổi hợp đồng bên ngoài một cách vô tình.

## 12. Kiểm thử EventSerializer

Kiểm thử serializer cần xác minh dữ liệu có thể đi từ object sang representation và trở lại mà không mất ngữ nghĩa.

### Round-trip test

Với mỗi loại event quan trọng:

1. Tạo event có giá trị đại diện, bao gồm Unicode, số tiền, thời gian, null hoặc collection nếu có.
2. Serialize event.
3. Deserialize thành kiểu event mong đợi.
4. So sánh các trường nghiệp vụ và metadata quan trọng.

Ví dụ kiểm thử codec Jackson:

~~~java
@Test
void shouldRoundTripOrderConfirmed() throws Exception {
    var original = new OrderConfirmed(
        UUID.randomUUID(),
        UUID.randomUUID(),
        Instant.parse("2026-11-25T10:30:00Z"),
        1,
        new BigDecimal("125000.00"),
        "VND"
    );

    String payload = objectMapper.writeValueAsString(original);
    OrderConfirmed restored =
        objectMapper.readValue(payload, OrderConfirmed.class);

    assertThat(restored).isEqualTo(original);
}
~~~

### Backward compatibility test

Lưu fixture payload của các phiên bản schema cũ trong test resources hoặc bộ fixture được quản lý. Kiểm tra phiên bản ứng dụng hiện tại có thể đọc chúng và tạo ra event đúng ngữ nghĩa.

### Error test

Kiểm tra payload hỏng, thiếu trường bắt buộc, kiểu dữ liệu sai và schema version không được hỗ trợ. Xác nhận lỗi được báo rõ và publication không bị đánh dấu hoàn tất sai.

### Persistence integration test

Kiểm tra toàn bộ đường đi của publication với kho lưu trữ đang dùng: ghi event, commit, đọc lại publication và deserialize. Kiểm tra thêm trường hợp rollback và trường hợp ứng dụng cần phục hồi publication chưa hoàn tất.

### Externalization contract test

Nếu event được gửi ra broker, kiểm tra message thực tế có đúng event type, schema, content type, headers và payload mà consumer mong đợi. Round-trip của EventSerializer không thay thế kiểm thử wire contract.

## 13. Hiệu năng và kích thước payload

Serialization nằm trên đường ghi publication và có thể ảnh hưởng đến thời gian xử lý. Với event có tần suất cao, cần đo:

- Thời gian serialize và deserialize.
- Kích thước payload sau serialization.
- Chi phí cấp phát bộ nhớ.
- Tỷ lệ lỗi theo event type.
- Độ trễ khi đọc lại backlog lớn.
- Tác động của schema migration hoặc upcasting.

Giảm payload bằng cách chỉ lưu trường cần thiết. Không serialize entity lớn rồi cố tối ưu bằng nén nếu thiết kế DTO nhỏ có thể giải quyết vấn đề ngay từ đầu.

Nén có thể hữu ích với payload lớn nhưng cần cân nhắc CPU, khả năng quan sát, giới hạn kích thước và cách tương thích khi giải nén. Nếu payload chứa dữ liệu nhạy cảm, mã hóa và nén phải được thiết kế cùng chính sách bảo vệ dữ liệu, quản lý khóa và retention.

## 14. Sơ đồ luồng serialization và phục hồi

~~~mermaid
flowchart TD
    A[Publisher tạo application event] --> B[Publication registry ghi nhận event]
    B --> C[EventSerializer serialize]
    C --> D[Lưu publication và payload]
    D --> E{Cần phục hồi publication?}
    E -- Không --> F[Listener xử lý theo luồng bình thường]
    E -- Có --> G[Đọc publication từ storage]
    G --> H[EventSerializer deserialize]
    H --> I{Payload hợp lệ và type được hỗ trợ?}
    I -- Có --> J[Giao event cho listener]
    I -- Không --> K[Giữ thông tin lỗi và cách ly để điều tra]
    J --> L{Listener xử lý thành công?}
    L -- Có --> M[Đánh dấu publication hoàn tất]
    L -- Không --> N[Giữ publication chưa hoàn tất và retry theo chính sách]
~~~

Sơ đồ thể hiện trách nhiệm của serializer trong luồng publication. Externalization ra broker là một chặng tích hợp riêng, có thể có adapter và message converter riêng.

## 15. Checklist trước khi đưa serializer vào production

- [ ] Event được biểu diễn bằng DTO hoặc record có cấu trúc ổn định.
- [ ] Định dạng serialization đã được chọn theo nhu cầu lưu trữ và tích hợp.
- [ ] EventSerializer đang dùng đúng SPI và phiên bản Spring Modulith.
- [ ] Cấu hình mapper nhất quán giữa lúc serialize và deserialize.
- [ ] Thời gian, tiền tệ, enum, null và collection có quy ước rõ.
- [ ] Metadata event type và schema version được quản lý.
- [ ] Payload cũ có thể được đọc trong thời gian publication còn tồn tại.
- [ ] Có chiến lược xử lý schema evolution hoặc upcasting.
- [ ] Deserialize lỗi không làm publication bị đánh dấu hoàn tất.
- [ ] Không bật polymorphic deserialization thiếu kiểm soát.
- [ ] Payload không chứa dữ liệu nhạy cảm không cần thiết.
- [ ] Có round-trip, backward compatibility và error tests.
- [ ] Có kiểm thử persistence và externalization riêng biệt.
- [ ] Đã đo thời gian xử lý và kích thước payload ở tải dự kiến.
- [ ] Có metric và log đủ để điều tra mà không ghi lộ payload.

## 16. Nguyên tắc sử dụng EventSerializer

EventSerializer là ranh giới chuyển đổi giữa application event object và dữ liệu publication được lưu trữ. Hãy bắt đầu với implementation mặc định phù hợp phiên bản Spring Modulith, DTO bất biến và định dạng có thể đọc lâu dài. Chỉ tùy biến khi có yêu cầu rõ về schema, type mapping, định dạng, chuyển đổi dữ liệu cũ hoặc bảo vệ payload.

Đặc biệt, hãy duy trì khả năng đọc publication qua nhiều lần triển khai. Một event serialize thành công hôm nay chỉ thực sự hữu ích khi ứng dụng còn có thể deserialize và xử lý đúng ngữ nghĩa sau này. Kiểm thử round-trip, backward compatibility và lỗi deserialize là phần thiết yếu của độ tin cậy khi giao sự kiện.
