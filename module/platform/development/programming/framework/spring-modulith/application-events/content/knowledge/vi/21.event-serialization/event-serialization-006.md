# Polymorphic event

*Tuần tự hóa nhiều biến thể event qua một hợp đồng chung*

Trong một hệ thống Spring Modulith, nhiều event có thể thuộc cùng một nhóm nghiệp vụ nhưng biểu diễn những việc khác nhau. Module đơn hàng có thể phát `OrderPlaced`, `OrderCancelled` hoặc `OrderShipped`. Ở thời điểm chạy, các event này là những kiểu Java riêng biệt; khi lưu publication hoặc chuyển event qua broker, chúng thường được tuần tự hóa thành JSON hay một định dạng thông điệp khác.

**Polymorphic event** là cách biểu diễn nhiều kiểu event cụ thể thông qua một kiểu hợp đồng chung. Consumer đọc hợp đồng đó, xác định biến thể thực tế bằng một trường phân biệt (type discriminator), rồi giải mã thành kiểu tương ứng. Cách làm này giữ cho producer và consumer trao đổi bằng hợp đồng rõ ràng mà không phải phụ thuộc vào tên class hoặc package nội bộ của nhau.

## 1. Vì sao cần polymorphic serialization?

Giả sử module `orders` phát nhiều sự kiện liên quan đến vòng đời đơn hàng. Nếu mọi sự kiện đều bị ép thành một class lớn với nhiều trường tùy chọn, consumer phải suy luận loại sự kiện từ tổ hợp field và kiểm tra nhiều giá trị null. Nếu mỗi event được gửi như một JSON không có thông tin loại, consumer cũng không biết nên giải mã payload thành class nào.

Một hợp đồng đa hình giải quyết vấn đề bằng cách định nghĩa kiểu cơ sở `OrderEvent` và các biến thể cụ thể. Mỗi biến thể có trường dữ liệu riêng, còn discriminator cho biết payload thuộc loại nào.

| Cách biểu diễn | Đặc điểm | Hệ quả |
|---|---|---|
| Một class lớn với nhiều field tùy chọn | Mọi loại event dùng chung một cấu trúc | Dễ xuất hiện tổ hợp field không hợp lệ và nhiều nhánh kiểm tra |
| Nhiều class nhưng không có discriminator | Mỗi event có cấu trúc riêng | Consumer khó xác định kiểu đích khi chỉ nhận một payload chung |
| Kiểu cơ sở và discriminator tường minh | Mỗi biến thể có cấu trúc riêng, payload nêu rõ loại | Có thể giải mã có kiểm soát và kiểm tra hợp đồng rõ ràng |

Không phải mọi hệ thống đều cần một hierarchy đa hình. Nếu chỉ có một event type hoặc consumer đã biết trước chính xác kiểu payload theo từng destination, một kiểu cụ thể có thể đơn giản hơn. Dùng polymorphism khi nhiều biến thể thực sự thuộc cùng một hợp đồng và cần được xử lý theo một điểm vào chung.

## 2. Thiết kế kiểu event cơ sở

Với Java hiện đại, có thể dùng `sealed interface` để giới hạn những biến thể hợp lệ. Ví dụ sau định nghĩa nhóm event của đơn hàng:

```java
import java.time.Instant;
import java.util.UUID;

public sealed interface OrderEvent
        permits OrderPlaced, OrderCancelled {

    UUID eventId();

    UUID orderId();
}

public record OrderPlaced(
    UUID eventId,
    UUID orderId,
    Instant placedAt
) implements OrderEvent {}

public record OrderCancelled(
    UUID eventId,
    UUID orderId,
    Instant cancelledAt,
    String reason
) implements OrderEvent {}
```

`OrderEvent` định nghĩa các thuộc tính chung cần cho truy vết và định danh. `OrderPlaced` và `OrderCancelled` giữ dữ liệu riêng của từng sự kiện. `sealed` giúp compiler biết tập kiểu được phép triển khai trong phạm vi module và hỗ trợ kiểm tra khi xử lý các biến thể.

Kiểu cơ sở nên thể hiện một nhóm nghiệp vụ có ý nghĩa. Không gom các event không liên quan chỉ vì chúng có vài field giống nhau. Một hierarchy quá rộng sẽ tạo hợp đồng khó hiểu và khiến consumer phải xử lý những biến thể không thuộc trách nhiệm của nó.

## 3. Dùng discriminator ổn định với Jackson

Khi dùng Jackson, `@JsonTypeInfo` khai báo cách lưu thông tin loại vào payload. `@JsonSubTypes` ánh xạ tên logic sang các class được phép giải mã:

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(
        value = OrderPlaced.class,
        name = "order-placed.v1"
    ),
    @JsonSubTypes.Type(
        value = OrderCancelled.class,
        name = "order-cancelled.v1"
    )
})
public sealed interface OrderEvent
        permits OrderPlaced, OrderCancelled {

    UUID eventId();

    UUID orderId();
}
```

Trong ví dụ, `eventType` là tên trường discriminator; `order-placed.v1` và `order-cancelled.v1` là tên loại được thống nhất trong hợp đồng. Tên này là định danh dữ liệu ổn định, không phải tên class Java. Có thể đổi tên class hoặc package nội bộ mà không làm thay đổi payload miễn là ánh xạ discriminator vẫn được giữ.

Một payload sau khi serialize có dạng:

```json
{
  "eventType": "order-placed.v1",
  "eventId": "a8f54a1a-61f6-4f4c-9ef5-2c3b9a3d5e71",
  "orderId": "51a1f98c-7ef8-4f12-90a1-8f7a5c4d3e21",
  "placedAt": "2026-11-25T10:15:30Z"
}
```

Consumer đọc trường `eventType`, tìm subtype đã đăng ký và tạo đối tượng tương ứng. Với `OrderPlaced`, JSON có `placedAt`; với `OrderCancelled`, JSON có `cancelledAt` và `reason`. Các trường chung vẫn có mặt ở cả hai loại.

Ưu tiên `JsonTypeInfo.Id.NAME` với danh sách subtype cho phép. Tránh dùng class name làm discriminator hoặc bật default typing rộng cho message đến từ mạng. Class name gắn payload với cấu trúc code nội bộ và có thể mở rộng phạm vi kiểu được khởi tạo ngoài dự kiến nếu cấu hình không giới hạn chặt chẽ.

## 4. Serialize và deserialize qua kiểu cơ sở

Khi ghi hoặc đọc payload đa hình, điểm giải mã cần biết kiểu cơ sở. Với Jackson `ObjectMapper` đã được cấu hình các module cần thiết, có thể kiểm tra vòng đời như sau:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = applicationObjectMapper;

OrderEvent original = new OrderPlaced(
    UUID.randomUUID(),
    UUID.randomUUID(),
    Instant.parse("2026-11-25T10:15:30Z")
);

String payload = mapper.writeValueAsString(original);
OrderEvent restored = mapper.readValue(payload, OrderEvent.class);
```

Kết quả `restored` là một `OrderPlaced` với các trường được khôi phục từ payload. Nếu đầu vào mang `eventType` không nằm trong danh sách subtype đã đăng ký, Jackson thường từ chối giải mã bằng lỗi type id không hợp lệ. Ứng dụng cần xử lý lỗi đó theo chính sách message không hợp lệ thay vì âm thầm coi payload là một biến thể khác.

Sử dụng cùng quy ước mapper và module Java time ở producer lẫn consumer. `Instant`, UUID, enum và kiểu số cần có biểu diễn thống nhất. Trong ứng dụng Spring, nên dùng `ObjectMapper` đã cấu hình cho ứng dụng thay vì tự tạo mapper mặc định riêng ở từng adapter, để tránh khác biệt serializer giữa các đường đi.

## 5. Phân biệt event nội bộ, publication lưu trữ và message bên ngoài

Application event trong cùng tiến trình được truyền dưới dạng object Java; không nhất thiết phải serialize khi một listener nội bộ nhận event. Serialization trở nên quan trọng khi event được lưu bền vững, khi publication registry cần khôi phục dữ liệu sau restart, hoặc khi event được externalize sang broker và tiến trình khác.

Trong Spring Modulith, event publication registry theo dõi publication cần được hoàn tất cho listener hoặc externalization target. Nếu cấu hình lưu publication có serialize payload, serializer phải giữ đủ thông tin để khôi phục đúng biến thể event sau khi ứng dụng khởi động lại. Với externalization, message contract phải cho consumer biết event type và schema mà nó cần giải mã.

Các đường đi này có thể dùng cấu hình serializer khác nhau. Hãy xác định rõ:

- Serializer nào được dùng cho publication store?
- Serializer nào tạo payload gửi ra broker?
- Consumer đọc kiểu cơ sở nào và subtype nào được phép?
- Discriminator và phiên bản schema được giữ ở đâu trong envelope hoặc payload?
- Khi subtype cũ không còn được hỗ trợ, publication tồn đọng hoặc message lưu trên broker được xử lý ra sao?

Không giả định rằng cấu hình `ObjectMapper` cho HTTP API tự động được dùng cho publication registry hoặc broker adapter. Cần xác minh integration thực tế được cấu hình để sử dụng mapper và serializer nào.

## 6. Xử lý event đa hình trong consumer

Consumer có thể nhận kiểu cơ sở và phân nhánh theo subtype:

```java
public void handle(OrderEvent event) {
    switch (event) {
        case OrderPlaced placed -> handlePlaced(placed);
        case OrderCancelled cancelled -> handleCancelled(cancelled);
    }
}
```

Đây là pattern matching cho `switch` trong các phiên bản Java hỗ trợ tính năng này. Nếu dự án dùng phiên bản Java cũ hơn, dùng `instanceof` hoặc visitor tương ứng. Với hierarchy `sealed`, compiler có thể hỗ trợ kiểm tra tính đầy đủ của các nhánh khi xử lý toàn bộ subtype đã biết.

Trong Spring, listener có thể nhận kiểu cơ sở nếu hợp đồng của listener là xử lý tất cả biến thể thuộc nhóm đó. Nếu mỗi biến thể có quy trình nghiệp vụ riêng, tách handler theo subtype hoặc chuyển dispatch vào một thành phần chuyên trách để tránh một listener lớn chứa nhiều nhánh không liên quan.

Không dùng discriminator để bỏ qua xác thực nghiệp vụ. Dù payload giải mã thành subtype hợp lệ, consumer vẫn phải kiểm tra quyền, trạng thái aggregate, giới hạn dữ liệu và điều kiện chuyển trạng thái trước khi tạo side effect.

## 7. Tiến hóa subtype và schema

Hợp đồng đa hình cần tồn tại qua nhiều lần triển khai producer và consumer. Một consumer có thể chạy phiên bản cũ trong khi producer đã phát một subtype mới. Vì vậy, thay đổi hierarchy cần có kế hoạch tương thích.

**Thêm subtype mới.** Việc thêm `OrderReturned` không làm payload cũ thay đổi, nhưng consumer cũ chưa biết discriminator mới có thể không giải mã được. Hãy triển khai consumer có khả năng nhận subtype mới trước khi producer bắt đầu phát nó, hoặc định tuyến subtype mới đến destination mà consumer tương thích đã sẵn sàng.

**Thêm field tùy chọn.** Có thể bổ sung trường mới nếu consumer cũ có thể bỏ qua trường không biết và consumer mới xử lý được payload cũ khi trường vắng mặt. Quy định rõ giá trị mặc định và nullability.

**Thay đổi không tương thích.** Nếu đổi ý nghĩa hoặc kiểu dữ liệu, phát hành loại/version mới như `order-placed.v2` và duy trì khả năng đọc phiên bản cũ trong giai đoạn chuyển tiếp. Không tái sử dụng discriminator cũ cho một cấu trúc có ý nghĩa khác.

**Loại bỏ subtype.** Trước khi bỏ một subtype khỏi danh sách giải mã, cần chắc chắn không còn publication chưa hoàn tất, message còn retention hoặc dữ liệu replay nào chứa discriminator đó. Nếu vẫn còn, giữ compatibility reader hoặc chuyển dữ liệu theo quy trình có kiểm soát.

Một bảng mapping giúp nhóm phát và nhóm nhận thống nhất hợp đồng:

| Discriminator | Kiểu Java minh họa | Trạng thái hợp đồng |
|---|---|---|
| `order-placed.v1` | `OrderPlaced` | Phiên bản hiện tại |
| `order-cancelled.v1` | `OrderCancelled` | Phiên bản hiện tại |
| `order-placed.v2` | `OrderPlacedV2` | Phiên bản mới khi có thay đổi không tương thích |

## 8. Unknown subtype và dữ liệu không hợp lệ

Unknown subtype có thể xuất hiện khi producer được nâng cấp trước consumer, message bị lỗi hoặc discriminator không đúng hợp đồng. Cần phân biệt ít nhất ba tình huống:

- **Discriminator chưa được biết:** consumer chưa hỗ trợ loại event đó. Ghi nhận event ID, discriminator, producer và schema metadata; chuyển message sang luồng chờ tương thích hoặc dead-letter theo chính sách.
- **Payload sai cấu trúc:** trường bắt buộc thiếu, kiểu dữ liệu sai hoặc JSON hỏng. Đây thường là lỗi hợp đồng hoặc dữ liệu, không nên retry liên tục như lỗi mạng tạm thời.
- **Subtype hợp lệ nhưng dữ liệu nghiệp vụ không hợp lệ:** deserialize thành công nhưng event vi phạm quy tắc nghiệp vụ. Đưa vào quy trình xử lý nghiệp vụ hoặc đối soát phù hợp.

Không tự động chuyển unknown subtype thành một subtype mặc định, vì như vậy có thể làm thay đổi ý nghĩa sự kiện và gây side effect sai. Cũng không xóa message trước khi lưu đủ thông tin phục vụ điều tra và replay.

## 9. Kiểm thử polymorphic serialization

Kiểm thử cần chứng minh mỗi subtype được serialize và khôi phục đúng, đồng thời payload không hợp lệ bị từ chối có kiểm soát. Các ca nên có:

1. **Round-trip từng subtype:** serialize `OrderPlaced` và `OrderCancelled`, deserialize về `OrderEvent`, xác nhận đúng class và giá trị từng field.
2. **Discriminator ổn định:** xác nhận JSON chứa tên logic như `order-placed.v1`, không phụ thuộc tên class hoặc package Java.
3. **Subtype không được phép:** gửi discriminator lạ và xác nhận giải mã thất bại theo chính sách.
4. **Payload cũ:** đọc fixture của schema cũ để bảo đảm consumer mới còn tương thích trong thời gian hỗ trợ.
5. **Field tùy chọn:** kiểm tra hành vi khi field mới vắng mặt hoặc null theo hợp đồng.
6. **Publication persistence:** nếu event được lưu trong registry, kiểm tra có thể khôi phục publication sau khi tạo lại context hoặc restart ứng dụng bằng cùng cấu hình serializer.
7. **Externalization:** xác nhận message broker giữ discriminator, event ID và metadata cần thiết sau serialize.
8. **Idempotency:** giao cùng một event nhiều lần không tạo side effect lặp lại ở consumer.

Ví dụ kiểm thử round-trip có thể dùng `ObjectMapper` đang được ứng dụng cấu hình:

```java
@Test
void restoresConcreteSubtypeFromBaseType() throws Exception {
    OrderEvent original = new OrderCancelled(
        UUID.randomUUID(),
        UUID.randomUUID(),
        Instant.parse("2026-11-25T10:15:30Z"),
        "Customer request"
    );

    String json = objectMapper.writeValueAsString(original);
    OrderEvent restored = objectMapper.readValue(json, OrderEvent.class);

    assertEquals(original, restored);
}
```

Ngoài round-trip, nên giữ các JSON fixture đại diện cho từng phiên bản hợp đồng. Fixture giúp phát hiện thay đổi vô tình về tên discriminator, kiểu dữ liệu, timestamp hoặc cấu trúc lồng nhau khi nâng cấp thư viện serialization.

## 10. Quan sát và bảo mật

Khi event được serialize, discriminator trở thành metadata có ích cho giám sát. Có thể đếm số event theo `eventType`, tỷ lệ deserialize lỗi theo subtype, tuổi publication chưa hoàn tất và tỷ lệ dead-letter. Kết hợp event ID, correlation ID và trace ID để lần theo cùng một sự kiện qua producer, registry, broker và consumer.

Không ghi toàn bộ payload vào log nếu payload có dữ liệu cá nhân hoặc bí mật. Log discriminator, event ID, schema version, destination và mã lỗi thường đủ để phân loại sự cố. Giới hạn kích thước payload và kiểm tra dữ liệu đầu vào trước khi deserialize để giảm rủi ro từ message quá lớn hoặc dữ liệu độc hại.

Danh sách subtype được phép là một phần của ranh giới bảo mật. Chỉ đăng ký những kiểu event consumer thực sự hỗ trợ. Tránh bật cơ chế polymorphic typing toàn cục cho dữ liệu không đáng tin cậy; dùng discriminator tường minh và allow-list giúp giới hạn loại đối tượng có thể được tạo.

## 11. Những điểm cần nhớ

- Polymorphic event biểu diễn nhiều biến thể event qua một kiểu hợp đồng cơ sở.
- Discriminator tường minh giúp consumer xác định subtype; dùng tên logic ổn định thay cho tên class Java.
- Với Jackson, `@JsonTypeInfo` và `@JsonSubTypes` có thể khai báo type metadata cùng danh sách subtype được phép.
- Event nội bộ không nhất thiết phải serialize; publication store và externalization cần serializer tương thích khi event đi qua ranh giới lưu trữ hoặc tiến trình.
- Thêm, đổi hoặc bỏ subtype cần kế hoạch schema compatibility và xử lý message cũ.
- Kiểm thử round-trip, unknown subtype, publication persistence và consumer idempotency để bảo vệ hợp đồng.

Khi hierarchy event phản ánh đúng nhóm nghiệp vụ, discriminator được quản lý như một phần của hợp đồng và serializer chỉ khôi phục các subtype được phép, Spring Modulith có thể lưu trữ và chuyển các biến thể application event một cách rõ ràng qua các module và hệ thống độc lập.
