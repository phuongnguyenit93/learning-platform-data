# Thiết kế chính sách khi gặp giá trị enum không nhận diện

Enum thường được dùng để biểu diễn trạng thái, loại sự kiện, phương thức thanh toán hoặc một tập giá trị có tên xác định. Khi Jackson đọc JSON thành enum, chuỗi trong JSON phải ánh xạ được tới một constant mà Java đã khai báo.

Ví dụ:

~~~java
public enum OrderStatus {
    NEW,
    PROCESSING,
    COMPLETED,
    CANCELLED
}
~~~

JSON:

~~~json
{
  "status": "PROCESSING"
}
~~~

Payload này ánh xạ được sang OrderStatus.PROCESSING. Nhưng nếu producer gửi "IN_TRANSIT" trong khi consumer chưa có constant tương ứng, Jackson phải áp dụng một chính sách đã được thiết kế: từ chối dữ liệu, chuyển thành null, dùng một constant mặc định hoặc giữ nguyên mã gốc trong một kiểu dữ liệu có khả năng mở rộng.

Đây là vấn đề tương thích hợp đồng giữa producer và consumer. **Không có một cách xử lý unknown enum đúng cho mọi hệ thống.** Chính sách phải dựa trên ý nghĩa nghiệp vụ, khả năng mở rộng phiên bản và việc consumer có cần giữ lại giá trị chưa biết để xử lý sau hay không.

## 1. Vì sao enum có thể không nhận diện được?

Enum Java là một tập constant được khai báo trước khi chương trình chạy. Ví dụ:

~~~java
public enum PaymentMethod {
    CASH,
    CARD,
    BANK_TRANSFER
}
~~~

Consumer chỉ nhận biết ba giá trị trên. Nếu JSON gửi:

~~~json
{
  "method": "WALLET"
}
~~~

Jackson không tìm được constant WALLET và mặc định sẽ báo lỗi mapping khi deserialize.

Các nguyên nhân thường gặp:

- Producer thêm enum constant mới nhưng consumer chưa được nâng phiên bản.
- Hai hệ thống dùng mã enum khác nhau, ví dụ BANK_TRANSFER và BANK.
- Giá trị JSON sai chính tả hoặc sai casing.
- Producer thay đổi tên constant mà không giữ alias cũ.
- Một hệ thống gửi mã nghiệp vụ bên ngoài, trong khi Java enum dùng tên nội bộ.
- Dữ liệu lịch sử chứa giá trị không còn được phiên bản hiện tại hỗ trợ.

Cần phân biệt unknown enum với JSON sai cú pháp. JSON có thể hoàn toàn hợp lệ nhưng giá trị enum không nằm trong tập mà consumer hiểu.

## 2. Hành vi mặc định của Jackson

Với enum:

~~~java
public enum OrderStatus {
    NEW,
    PROCESSING,
    COMPLETED
}
~~~

Jackson mặc định ánh xạ chuỗi JSON theo tên enum:

~~~json
{
  "status": "COMPLETED"
}
~~~

Nếu nhận:

~~~json
{
  "status": "IN_TRANSIT"
}
~~~

Jackson thường ném lỗi dạng InvalidFormatException (một subclass của JsonMappingException), cho biết giá trị không thể chuyển thành kiểu enum đích.

Đây là hành vi strict có ích cho các hợp đồng mà mọi giá trị phải được consumer hiểu. Nó giúp phát hiện producer và consumer không đồng bộ thay vì âm thầm biến trạng thái mới thành một giá trị khác.

Tuy nhiên, với event stream hoặc tích hợp cần tương thích tiến, việc từ chối toàn bộ event chỉ vì một enum mới có thể làm gián đoạn consumer. Khi đó cần chọn một chính sách fallback hoặc giữ nguyên mã gốc.

## 3. Bốn hướng xử lý unknown enum

Có bốn chiến lược thường gặp:

| Chính sách | Cách thực hiện | Khi phù hợp |
|---|---|---|
| Strict: từ chối | Giữ hành vi mặc định | Giá trị lạ có thể làm sai nghiệp vụ hoặc cần phát hiện ngay |
| Chuyển thành null | READ_UNKNOWN_ENUM_VALUES_AS_NULL | Field tùy chọn và null có ý nghĩa an toàn |
| Dùng constant mặc định | @JsonEnumDefaultValue và READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE | Có một trạng thái fallback nghiệp vụ rõ ràng |
| Giữ mã gốc | Dùng String hoặc value object thay cho enum đóng | Cần forward, lưu trữ hoặc xử lý lại giá trị chưa biết |

Không nên chọn fallback chỉ để tránh exception. Một giá trị unknown có thể mang ý nghĩa quan trọng mà consumer chưa hiểu.

## 4. Chính sách strict: từ chối giá trị không nhận diện

Nếu consumer cần hiểu mọi trạng thái trước khi xử lý, giữ hành vi mặc định là lựa chọn an toàn.

Ví dụ:

~~~java
public record PaymentEvent(
    String eventId,
    PaymentStatus status
) {}

public enum PaymentStatus {
    PENDING,
    PAID,
    FAILED,
    REFUNDED
}
~~~

Payload hợp lệ:

~~~json
{
  "eventId": "EVT-100",
  "status": "PAID"
}
~~~

Payload có giá trị chưa biết:

~~~json
{
  "eventId": "EVT-101",
  "status": "REVERSED"
}
~~~

Jackson sẽ báo lỗi khi không thể ánh xạ REVERSED sang PaymentStatus.

Strict phù hợp khi:

- Enum quyết định quyền hoặc luồng bảo mật.
- Enum điều khiển trạng thái thanh toán, hoàn tiền hoặc giao dịch.
- Mọi giá trị cần có nhánh xử lý nghiệp vụ cụ thể.
- Consumer phải từ chối event không hiểu để producer sửa hoặc gửi lại sau khi nâng phiên bản.
- Hợp đồng yêu cầu producer và consumer triển khai cùng version.

Ở tầng API, có thể chuyển lỗi mapping thành response 400 với thông báo validation phù hợp. Không trả stack trace hoặc thông tin nội bộ của Jackson cho client.

Strict không có nghĩa mọi enum đều phải từ chối. Đây là lựa chọn theo ranh giới và mức độ rủi ro của từng hợp đồng.

## 5. Chuyển unknown enum thành null

Jackson có DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_AS_NULL. Khi bật feature này, giá trị enum không nhận diện được sẽ được chuyển thành null thay vì ném lỗi.

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(
        DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_AS_NULL
    )
    .build();
~~~

Với enum:

~~~java
public enum NotificationChannel {
    EMAIL,
    SMS,
    PUSH
}
~~~

JSON:

~~~json
{
  "channel": "IN_APP"
}
~~~

Sau khi deserialize, channel có thể là null.

### 5.1. Khi nào dùng null fallback?

Có thể cân nhắc khi:

- Field thực sự tùy chọn.
- Consumer không cần thực hiện hành động theo giá trị unknown.
- null đã có ý nghĩa rõ ràng trong mô hình dữ liệu.
- Tầng xử lý tiếp theo có thể phân biệt và xử lý trạng thái không xác định.
- Việc bỏ qua giá trị không làm sai nghiệp vụ.

Ví dụ một trường display channel chỉ phục vụ giao diện phụ. Nếu consumer không biết channel mới, có thể không hiển thị thông tin đó.

### 5.2. Rủi ro của null fallback

Chuyển unknown thành null làm mất giá trị gốc. Consumer không biết producer đã gửi IN_APP, MOBILE_APP hay một mã khác.

Ngoài ra, null có thể bị hiểu nhầm là:

- Field bị thiếu.
- Producer gửi explicit null.
- Giá trị thực sự không có.
- Giá trị unknown đã bị Jackson chuyển thành null.

Nếu nghiệp vụ cần phân biệt các trường hợp này, null fallback không đủ thông tin.

Cần lưu ý rằng null không thể được đưa vào một số cấu trúc enum chuyên biệt như EnumSet hoặc làm key hợp lệ trong EnumMap. Vì vậy, chính sách unknown-to-null cần được kiểm thử riêng nếu enum nằm trong các cấu trúc đó.

## 6. Dùng constant mặc định với @JsonEnumDefaultValue

Nếu muốn consumer nhận một giá trị đại diện cho trạng thái unknown, Jackson hỗ trợ @JsonEnumDefaultValue.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonEnumDefaultValue;

public enum OrderStatus {
    NEW,
    PROCESSING,
    COMPLETED,
    CANCELLED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Bật feature:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(
        DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE
    )
    .build();
~~~

Khi JSON gửi:

~~~json
{
  "status": "IN_TRANSIT"
}
~~~

Jackson ánh xạ status thành OrderStatus.UNKNOWN.

### 6.1. Ý nghĩa của UNKNOWN phải được định nghĩa

UNKNOWN là một constant trong mô hình Java, nhưng không nên tự động coi nó là trạng thái nghiệp vụ có thể thực hiện mọi thao tác.

Ví dụ:

~~~java
switch (event.status()) {
    case NEW -> handleNew(event);
    case PROCESSING -> handleProcessing(event);
    case COMPLETED -> handleCompleted(event);
    case CANCELLED -> handleCancelled(event);
    case UNKNOWN -> recordUnrecognizedStatus(event);
}
~~~

Nhánh UNKNOWN có thể ghi nhận event, phát cảnh báo hoặc đưa vào luồng xử lý thủ công. Không nên mặc định UNKNOWN tương đương NEW, FAILED hoặc CANCELLED nếu chưa có quy tắc nghiệp vụ.

### 6.2. Không mất cảnh giác khi dùng default enum

Default enum giúp consumer tiếp tục đọc payload, nhưng nó cũng làm mất mã unknown ban đầu. Nếu cần chẩn đoán hoặc chuyển tiếp event, chỉ lưu UNKNOWN là chưa đủ.

Một lựa chọn là lưu thêm raw payload hoặc mã enum gốc trong một trường riêng. Tốt hơn nữa, nếu hệ thống cần giữ nguyên mọi mã tương lai, hãy dùng String hoặc value object có raw code.

### 6.3. Feature cần có enum default được đánh dấu

READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE cần một enum constant được đánh dấu @JsonEnumDefaultValue để Jackson biết phải dùng giá trị nào.

Nếu enum không có default constant, không nên dựa vào feature này để tạo một fallback tự động. Hãy định nghĩa constant mặc định và test cấu hình đó.

## 7. Phân biệt unknown enum với khác biệt chữ hoa/chữ thường

Các giá trị sau có thể biểu diễn cùng ý nghĩa theo một số hợp đồng:

~~~json
"PAID"
"paid"
"Paid"
~~~

Jackson mặc định thường phân biệt casing khi ánh xạ tên enum. Nếu hợp đồng cho phép không phân biệt hoa thường, có thể bật MapperFeature.ACCEPT_CASE_INSENSITIVE_ENUMS:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(MapperFeature.ACCEPT_CASE_INSENSITIVE_ENUMS)
    .build();
~~~

Khi đó, các biến thể casing có thể ánh xạ tới cùng constant.

Tuy nhiên, case-insensitive không giải quyết giá trị hoàn toàn chưa biết. "IN_TRANSIT" vẫn là unknown nếu enum không có constant tương ứng.

Không nên bật case-insensitive nếu casing là một phần của mã định danh có ý nghĩa phân biệt. Với mã từ hệ thống đối tác, tốt hơn nên quy định rõ casing trong hợp đồng hoặc chuẩn hóa tại adapter tích hợp.

## 8. Ánh xạ mã bên ngoài bằng @JsonCreator và @JsonValue

Tên enum Java không nhất thiết phải giống mã JSON.

Ví dụ hệ thống muốn Java dùng tên dễ đọc, còn JSON dùng mã ngắn:

~~~java
public enum PaymentMethod {
    CASH("C"),
    CARD("CC"),
    BANK_TRANSFER("BANK");

    private final String code;

    PaymentMethod(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }

    @JsonCreator
    public static PaymentMethod fromCode(String code) {
        for (PaymentMethod method : values()) {
            if (method.code.equals(code)) {
                return method;
            }
        }
        throw new IllegalArgumentException(
            "Unknown payment method code: " + code
        );
    }
}
~~~

Serialization:

~~~java
PaymentMethod.CARD
~~~

được biểu diễn thành:

~~~json
"CC"
~~~

Deserialization nhận "CC" và gọi factory fromCode.

Với enum, @JsonValue có thể được Jackson sử dụng để tìm lại constant khi deserialize trong các trường hợp được hỗ trợ. Tuy nhiên, khi cần custom alias, chuẩn hóa casing hoặc chính sách unknown riêng, static factory @JsonCreator làm ý định rõ hơn.

Nếu factory ném IllegalArgumentException cho mã không biết, lỗi sẽ được Jackson bọc thành lỗi mapping. Đây là cách strict. Có thể thay bằng fallback UNKNOWN nếu hợp đồng cho phép, nhưng khi đó raw code sẽ bị mất trừ khi lưu riêng.

Không nên dùng tên enum Java làm mã giao tiếp lâu dài nếu việc đổi tên constant có thể phá vỡ client. Một code ổn định như "BANK" hoặc "CC" tách hợp đồng bên ngoài khỏi tên triển khai nội bộ.

## 9. Khi cần giữ nguyên giá trị enum chưa biết

Enum Java là kiểu đóng: tập constant được xác định tại compile time. Nếu consumer phải giữ nguyên mọi mã mà producer gửi, enum đơn thuần không đủ.

Có thể dùng String:

~~~java
public record PartnerEvent(
    String eventId,
    String statusCode
) {}
~~~

Tầng nghiệp vụ chuyển các mã đã biết sang enum:

~~~java
public enum KnownStatus {
    NEW,
    PROCESSING,
    COMPLETED
}

public Optional<KnownStatus> knownStatus(String code) {
    try {
        return Optional.of(KnownStatus.valueOf(code));
    } catch (IllegalArgumentException | NullPointerException ex) {
        return Optional.empty();
    }
}
~~~

Cách này giữ được raw statusCode. Consumer có thể:

- Xử lý các mã đã biết theo enum.
- Ghi nhận mã chưa biết để quan sát.
- Lưu lại event nguyên bản.
- Forward event đến consumer khác.
- Chờ cập nhật mapping khi hiểu mã mới.

Có thể đóng gói thành value object:

~~~java
public record StatusCode(String value) {

    public StatusCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Status code is required");
        }
    }

    public Optional<KnownStatus> knownValue() {
        try {
            return Optional.of(KnownStatus.valueOf(value));
        } catch (IllegalArgumentException ex) {
            return Optional.empty();
        }
    }
}
~~~

Value object có thể bổ sung quy tắc chuẩn hóa, validation và mapping. Quan trọng là nó giữ raw code thay vì thay mọi giá trị lạ thành một constant chung.

Không nên dùng String cho mọi enum nội bộ nếu tập giá trị thật sự đóng và compiler có thể giúp phát hiện thiếu nhánh xử lý. Hãy dùng enum cho tập giá trị được kiểm soát; dùng String/value object cho mã ngoài có thể mở rộng độc lập với phiên bản consumer.

## 10. Enum trong collection và Map

Chính sách unknown enum cũng cần được xem xét khi enum nằm trong collection:

~~~java
public record BatchRequest(
    List<OrderStatus> statuses
) {}
~~~

JSON:

~~~json
{
  "statuses": ["NEW", "PROCESSING", "IN_TRANSIT"]
}
~~~

Nếu dùng READ_UNKNOWN_ENUM_VALUES_AS_NULL, phần tử unknown có thể được chuyển thành null. Consumer phải xác định có chấp nhận phần tử null trong List hay không.

Nếu dùng READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE, phần tử unknown có thể trở thành UNKNOWN. Điều này cho phép collection tiếp tục chứa một enum constant hợp lệ, nhưng raw code vẫn mất.

Với EnumSet, null không phải phần tử hợp lệ. Vì vậy, chế độ chuyển unknown enum thành null không phù hợp với cấu trúc này; hãy dùng strict hoặc default enum có chủ đích và test trực tiếp.

Với Map<OrderStatus, Integer>, enum là key. Key JSON được biểu diễn bằng tên property dạng chuỗi. Hành vi unknown key có thể khác với enum value trong field hoặc collection vì Jackson dùng key deserializer. Hãy viết test riêng cho Map/EnumMap nếu hợp đồng sử dụng enum key; đừng suy luận rằng feature xử lý enum value chắc chắn áp dụng giống hệt cho key.

## 11. Unknown enum và tương thích phiên bản producer/consumer

Giả sử producer phát hành version 2 với enum mới:

~~~java
public enum DeliveryStatus {
    CREATED,
    PACKED,
    SHIPPED,
    DELIVERED
}
~~~

Consumer version 1 chỉ biết:

~~~java
public enum DeliveryStatus {
    CREATED,
    PACKED,
    SHIPPED
}
~~~

Producer version 2 gửi DELIVERED. Consumer version 1 có thể:

- Từ chối event: an toàn khi không hiểu trạng thái có ảnh hưởng nghiệp vụ.
- Chuyển thành null: phù hợp nếu field phụ và null có ý nghĩa rõ.
- Chuyển thành UNKNOWN: phù hợp nếu consumer có nhánh xử lý unknown an toàn.
- Giữ raw code: phù hợp nếu consumer cần lưu/forward hoặc xử lý sau.

Đây là bài toán forward compatibility: consumer cũ nhận dữ liệu từ producer mới.

Backward compatibility là chiều ngược lại: producer mới vẫn gửi dữ liệu mà consumer cũ có thể hiểu. Khi thêm enum constant, producer cần xem xét liệu consumer cũ có chịu được giá trị đó không.

Một quy trình phát hành an toàn có thể là:

1. Nâng consumer để nhận biết hoặc xử lý unknown trước.
2. Triển khai chính sách fallback/forwarding phù hợp.
3. Sau khi consumer đã sẵn sàng, producer mới phát hành enum value mới.
4. Theo dõi số lượng unknown value để biết các phiên bản đang giao tiếp.
5. Chỉ bỏ fallback khi tất cả producer/consumer đã chuyển sang hợp đồng mới và có bằng chứng vận hành.

Không phải hệ thống nào cũng cần rollout theo thứ tự này. Nhưng với event hoặc trạng thái tài chính, thay đổi enum cần được quản lý như thay đổi schema, không phải chỉ là thêm một dòng vào enum Java.

## 12. Không nhầm unknown enum với null hoặc missing

Ba trạng thái cần được phân biệt:

| JSON | Ý nghĩa |
|---|---|
| Không có field status | Producer không gửi thuộc tính |
| "status": null | Producer gửi explicit null |
| "status": "FUTURE_STATE" | Producer gửi giá trị enum chưa được consumer biết |

READ_UNKNOWN_ENUM_VALUES_AS_NULL chỉ xử lý giá trị enum không nhận diện trong quá trình chuyển đổi; nó không làm cho missing và explicit null trở thành một trạng thái có presence riêng.

Nếu tất cả đều trở thành null trong DTO, ứng dụng không thể biết producer đã gửi null hay một mã enum lạ đã bị chuyển thành null.

Khi sự phân biệt này quan trọng, có thể:

- Dùng JsonNode để kiểm tra field có tồn tại và có phải null không trước khi chuyển đổi.
- Dùng String/value object để giữ mã gốc.
- Dùng một wrapper biểu diễn presence/value/unknown.
- Lưu raw payload hoặc raw enum code cho audit.

Đừng chọn null fallback nếu sau đó nghiệp vụ cần biết chính xác mã nào đã được gửi.

## 13. Kiểm thử chính sách unknown enum

Một contract test nên kiểm tra tất cả các nhánh mà hợp đồng công bố.

Ví dụ enum:

~~~java
public enum OrderStatus {
    NEW,
    PROCESSING,
    COMPLETED,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Mapper fallback:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(
        DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE
    )
    .build();
~~~

Test giá trị đã biết:

~~~java
@Test
void readsKnownEnumValue() throws Exception {
    OrderStatus status = mapper.readValue(
        "\"PROCESSING\"",
        OrderStatus.class
    );

    assertEquals(OrderStatus.PROCESSING, status);
}
~~~

Test giá trị chưa biết:

~~~java
@Test
void mapsUnknownEnumToDefault() throws Exception {
    OrderStatus status = mapper.readValue(
        "\"IN_TRANSIT\"",
        OrderStatus.class
    );

    assertEquals(OrderStatus.UNKNOWN, status);
}
~~~

Test strict mapper:

~~~java
@Test
void rejectsUnknownEnumWhenStrict() {
    ObjectMapper strictMapper = JsonMapper.builder().build();

    assertThrows(JsonMappingException.class, () ->
        strictMapper.readValue("\"IN_TRANSIT\"", OrderStatus.class)
    );
}
~~~

Test casing nếu hợp đồng cho phép:

~~~java
@Test
void acceptsDifferentEnumCasingWhenConfigured() throws Exception {
    ObjectMapper caseInsensitiveMapper = JsonMapper.builder()
        .enable(MapperFeature.ACCEPT_CASE_INSENSITIVE_ENUMS)
        .build();

    OrderStatus status = caseInsensitiveMapper.readValue(
        "\"processing\"",
        OrderStatus.class
    );

    assertEquals(OrderStatus.PROCESSING, status);
}
~~~

Ngoài unit test cho enum đơn, nên test enum trong DTO, List, Map key và các cấu trúc thực tế của API.

### 13.1. Ma trận test đề xuất

| Trường hợp | Strict | Unknown-to-null | Default enum |
|---|---|---|---|
| Giá trị đã biết | Enum tương ứng | Enum tương ứng | Enum tương ứng |
| Giá trị chưa biết | Mapping exception | null | Constant mặc định |
| JSON null | Theo null policy | Theo null policy | Theo null policy |
| Field missing | Theo creator/default | Theo creator/default | Theo creator/default |
| Sai kiểu JSON | Mapping exception hoặc coercion policy | Không tự động coi là unknown enum | Không tự động coi là unknown enum |
| Casing khác | Theo case policy | Theo case policy | Theo case policy |

Điểm quan trọng: unknown enum, null, missing và sai kiểu JSON là bốn trường hợp riêng. Test không nên gộp chúng vào một trường hợp "invalid input".

## 14. Quan sát và vận hành khi dùng fallback

Nếu chọn UNKNOWN hoặc null fallback, hãy có cách quan sát tần suất xuất hiện:

- Đếm unknown code theo producer hoặc integration.
- Ghi nhận mã raw ở log có kiểm soát, tránh log dữ liệu nhạy cảm.
- Gắn version producer/schema nếu có.
- Tạo cảnh báo khi một giá trị mới xuất hiện nhiều bất thường.
- Theo dõi thời gian tồn tại của mã unknown để quyết định cập nhật enum.

Không nên chỉ ghi log chuỗi "Unknown enum" mà bỏ mất mã thực tế. Nếu không có raw code hoặc payload gốc, đội vận hành sẽ khó xác định producer đã gửi gì.

Cũng không nên ghi toàn bộ raw payload vào log một cách mặc định. Payload có thể chứa thông tin cá nhân, token hoặc dữ liệu nhạy cảm. Chỉ ghi field cần thiết, đã được kiểm soát và có chính sách lưu trữ phù hợp.

## 15. Nguyên tắc lựa chọn

- **Strict** khi mọi enum đều có ý nghĩa nghiệp vụ bắt buộc phải hiểu.
- **Unknown-to-null** khi field tùy chọn và null là fallback an toàn, không cần giữ raw code.
- **Default enum** khi có một nhánh UNKNOWN được xử lý rõ ràng và việc mất mã gốc chấp nhận được.
- **String/value object** khi phải giữ nguyên mã chưa biết, forward event hoặc xử lý sau.
- **Case-insensitive** chỉ khi hợp đồng cho phép khác casing.
- **Versioned rollout** khi producer/consumer có thể được nâng cấp độc lập.

Giá trị enum không nhận diện được là tín hiệu về sự khác biệt giữa hợp đồng mà producer phát hành và khả năng hiểu của consumer. Jackson cung cấp các cơ chế để từ chối, fallback hoặc ánh xạ mã, nhưng quyết định cuối cùng thuộc thiết kế nghiệp vụ và khả năng tương thích. Hãy chọn chính sách cho từng ranh giới, kiểm thử cả giá trị đã biết lẫn chưa biết, và giữ raw code khi hệ thống cần bảo toàn thông tin.

