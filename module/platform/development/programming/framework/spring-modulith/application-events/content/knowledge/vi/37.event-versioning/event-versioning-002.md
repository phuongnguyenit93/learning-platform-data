# Version trong tên event

Application events là hợp đồng giao tiếp giữa các module trong Spring Modulith. Khi event được nhiều listener hoặc hệ thống bên ngoài tiêu thụ, cấu trúc và ý nghĩa của nó trở thành một phần của giao diện mà các consumer phụ thuộc vào. Theo thời gian, nghiệp vụ thay đổi: event cần thêm dữ liệu, đổi cách diễn giải hoặc tách một khái niệm cũ thành khái niệm mới. Đưa version vào tên event là một cách công bố rõ ràng rằng hợp đồng đã có phiên bản khác.

Ví dụ, `OrderConfirmedV1` có thể chỉ chứa mã đơn hàng và thời điểm xác nhận. Sau này, consumer cần biết kênh bán hàng và quy tắc xác nhận thay đổi; publisher có thể công bố `OrderConfirmedV2` với hợp đồng mới. Consumer cũ tiếp tục xử lý V1 trong giai đoạn chuyển đổi, còn consumer đã nâng cấp có thể đăng ký V2.

## 1. Vì sao version nằm trong tên event?

Tên event không chỉ là tên class Java. Với event được externalize, tên hoặc type identifier còn là một phần của hợp đồng mà consumer dùng để nhận biết và diễn giải thông điệp. Đặt version trong tên giúp phân biệt các hợp đồng không tương thích mà không buộc consumer cũ phải đoán cấu trúc mới.

Version trong tên event hữu ích khi:

- Ý nghĩa nghiệp vụ của event thay đổi, dù tên nghiệp vụ cũ vẫn có vẻ phù hợp.
- Một field bắt buộc được thêm vào và consumer cũ không thể xử lý nếu thiếu field đó.
- Kiểu dữ liệu hoặc cấu trúc payload thay đổi theo cách phá vỡ tương thích.
- Event được tách thành các loại mới với trách nhiệm hoặc quy tắc xử lý khác.
- Nhiều phiên bản publisher và consumer cần chạy song song trong thời gian triển khai.

Ví dụ tên theo version:

| Event name | Hợp đồng |
| --- | --- |
| `OrderConfirmedV1` | Đơn hàng được xác nhận với các trường cơ bản |
| `OrderConfirmedV2` | Đơn hàng được xác nhận với hợp đồng mới, ví dụ thêm kênh bán hàng hoặc thông tin xác nhận |
| `PaymentCapturedV1` | Thanh toán đã được thu theo hợp đồng phiên bản 1 |
| `PaymentCapturedV2` | Hợp đồng thanh toán đã thay đổi không tương thích |

Version trong tên là tín hiệu công khai về hợp đồng. Nó giúp người đọc, router và consumer xác định ngay event nào đang được xử lý.

## 2. Phân biệt event version, schema version và aggregate version

Ba loại version có mục đích khác nhau và không nên dùng thay thế cho nhau:

| Loại version | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Event contract version | Consumer đang nhận hợp đồng event nào? | `OrderConfirmedV2` |
| Schema version | Payload được serialize theo cấu trúc schema nào? | `schemaVersion: 2` hoặc schema ID của registry |
| Aggregate version/sequence | Đây là thay đổi thứ mấy của một aggregate? | `aggregateVersion: 17` |

Event contract version thể hiện phiên bản giao diện và ngữ nghĩa của loại event. Schema version mô tả cấu trúc dữ liệu được mã hóa trên wire. Aggregate version dùng để phát hiện event trùng, event cũ hoặc event bị thiếu thứ tự.

Ví dụ, `OrderConfirmedV2` có thể được phát ở `aggregateVersion=17`. Con số 2 không có nghĩa đây là thay đổi thứ hai của đơn hàng; nó chỉ là phiên bản hợp đồng. Tách bạch hai khái niệm giúp consumer không nhầm lẫn khi kiểm tra ordering.

## 3. Đặt quy ước tên nhất quán

Chọn một quy ước rõ ràng và giữ ổn định qua các module. Với Java, có thể đặt version ở cuối tên type:

~~~java
public record OrderConfirmedV1(
        UUID eventId,
        UUID orderId,
        Instant confirmedAt) {
}

public record OrderConfirmedV2(
        UUID eventId,
        UUID orderId,
        Instant confirmedAt,
        String salesChannel) {
}
~~~

Ở wire contract, có thể dùng type identifier theo dạng domain và version, chẳng hạn `orders.order-confirmed.v1` và `orders.order-confirmed.v2`. Tên Java class và wire type không bắt buộc phải giống nhau; điều quan trọng là mapping được công bố ổn định và consumer có thể nhận biết.

Quy ước nên thống nhất các điểm:

- Dùng tên mô tả sự kiện đã xảy ra, thường ở thì quá khứ như `OrderConfirmed` hoặc `PaymentCaptured`.
- Dùng một cách viết version thống nhất, ví dụ hậu tố `V1`, `V2` ở Java type và `.v1`, `.v2` ở wire type.
- Bắt đầu từ V1 và tăng version khi tạo hợp đồng mới không tương thích.
- Không dùng số version để biểu diễn lần deploy, sprint hoặc bản vá implementation.
- Không tái sử dụng tên version cũ cho ý nghĩa mới.
- Tài liệu hóa trường dữ liệu, đơn vị, timezone, nullability và ngữ nghĩa của từng version.

Không nhất thiết phải tạo topic Kafka riêng cho mỗi version. Event type và broker destination là hai quyết định độc lập. Nhiều version có thể cùng đi qua một topic nếu consumer phân biệt được type; hoặc được route sang topic riêng nếu topology và vận hành yêu cầu.

## 4. Khi nào cần version mới?

Không phải mọi thay đổi payload đều cần đổi tên event. Hãy phân biệt thay đổi tương thích và thay đổi phá vỡ tương thích:

| Thay đổi | Cách xử lý thường phù hợp |
| --- | --- |
| Thêm field tùy chọn, có default rõ ràng và consumer cũ bỏ qua được | Có thể giữ version hiện tại nếu schema policy cho phép |
| Thêm field bắt buộc mà consumer cũ không thể cung cấp hoặc diễn giải | Tạo version mới |
| Đổi kiểu field, ví dụ `amount` từ số nguyên sang object tiền tệ | Thường tạo version mới |
| Đổi đơn vị hoặc ý nghĩa field, ví dụ giây thành mili giây | Tạo version mới hoặc field mới với ngữ nghĩa rõ ràng |
| Xóa field đang được consumer sử dụng | Tạo version mới sau khi có kế hoạch migration |
| Đổi ý nghĩa nghiệp vụ nhưng giữ nguyên cấu trúc JSON | Tạo event type/version mới vì contract semantics đã đổi |
| Thêm metadata không ảnh hưởng consumer và schema tương thích | Có thể giữ version hiện tại |

Đừng chỉ dựa vào việc JSON parse thành công. Consumer có thể đọc được payload nhưng hiểu sai ý nghĩa của dữ liệu. Thay đổi ngữ nghĩa cũng là thay đổi hợp đồng.

## 5. Ví dụ hai phiên bản event trong Spring Modulith

Giả sử V1 chỉ chứa thông tin cơ bản của đơn hàng:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.modulith.events.Externalized;

@Externalized("orders")
public record OrderConfirmedV1(
        UUID eventId,
        UUID orderId,
        Instant confirmedAt) {
}
~~~

V2 bổ sung kênh bán hàng và version của aggregate:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.modulith.events.Externalized;

@Externalized("orders")
public record OrderConfirmedV2(
        UUID eventId,
        UUID orderId,
        Instant confirmedAt,
        String salesChannel,
        long aggregateVersion) {
}
~~~

Cả hai event có thể dùng cùng target logic `orders`. Adapter externalization và cấu hình integration quyết định target được ánh xạ tới destination nào và cách type được biểu diễn trong message. `@Externalized` đánh dấu event cần externalize; annotation không tự định nghĩa chính sách schema compatibility hay tự tạo một topic cho từng version.

Publisher phát V2 khi use case mới đã sẵn sàng:

~~~java
@Transactional
public void confirm(UUID orderId) {
    Order order = orders.findRequired(orderId);
    order.confirm();

    events.publishEvent(new OrderConfirmedV2(
            UUID.randomUUID(),
            order.id(),
            clock.instant(),
            order.salesChannel(),
            order.version()));
}
~~~

Trong thời gian chuyển đổi, consumer cũ có thể tiếp tục nhận V1 trong khi consumer mới đăng ký V2. Không thay đổi class V1 để mang payload V2 nhưng vẫn giữ tên V1; cách đó làm mất ý nghĩa của version và có thể khiến consumer cũ xử lý sai.

## 6. Consumer xử lý nhiều version

Consumer có thể đăng ký handler riêng cho từng phiên bản:

~~~java
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderProjectionListener {

    private final OrderProjection projection;

    OrderProjectionListener(OrderProjection projection) {
        this.projection = projection;
    }

    @ApplicationModuleListener
    void on(OrderConfirmedV1 event) {
        projection.apply(
                event.eventId(),
                event.orderId(),
                event.confirmedAt(),
                "UNKNOWN");
    }

    @ApplicationModuleListener
    void on(OrderConfirmedV2 event) {
        projection.apply(
                event.eventId(),
                event.orderId(),
                event.confirmedAt(),
                event.salesChannel());
    }
}
~~~

Ví dụ dùng giá trị `UNKNOWN` để minh họa cách chuyển V1 vào mô hình nội bộ hiện tại. Trong nghiệp vụ thật, phải xác định giá trị mặc định có ý nghĩa hay không; nếu không thể suy ra an toàn, consumer nên giữ trạng thái chưa đầy đủ hoặc từ chối xử lý theo quy trình rõ ràng.

Nếu nhiều handler cập nhật cùng projection, chúng cần dùng chung quy tắc idempotency và ordering. Khi publisher dual-publish V1 và V2 cho cùng một sự kiện nghiệp vụ, cả hai message nên mang cùng business event ID hoặc causation ID để consumer có thể nhận biết chúng là hai biểu diễn của cùng một sự thật, tránh áp dụng side effect hai lần.

## 7. Chuyển đổi publisher và consumer an toàn

Không nên nâng cấp publisher và tất cả consumer cùng một thời điểm nếu các thành phần được triển khai độc lập. Một quy trình migration có thể gồm:

1. **Chuẩn bị consumer:** triển khai consumer hiểu V1 và V2, nhưng chưa yêu cầu publisher phát V2.
2. **Triển khai publisher mới:** phát V2 theo chính sách đã thống nhất; nếu cần, duy trì V1 trong thời gian tương thích.
3. **Theo dõi adoption:** đo số message V1/V2, consumer nào còn dùng V1 và lỗi parse/validation theo version.
4. **Chuyển consumer:** cập nhật từng consumer sang V2 và xác minh kết quả nghiệp vụ.
5. **Ngừng V1:** chỉ dừng phát V1 khi mọi consumer bắt buộc đã chuyển đổi và không còn quy trình cần V1.
6. **Retire contract:** giữ tài liệu và khả năng đọc V1 trong thời gian retention/replay yêu cầu; sau đó mới loại bỏ handler và schema cũ.

Trình tự cụ thể có thể thay đổi theo việc publisher hay consumer được triển khai trước, nhưng nguyên tắc là consumer phải hiểu version mới trước khi publisher chỉ phát version mới.

### Chiến lược dual-publish

Trong một giai đoạn chuyển tiếp, publisher có thể phát cả V1 và V2 cho cùng một thay đổi nghiệp vụ. Cách này hữu ích khi consumer chưa thể chuyển cùng lúc, nhưng tạo hai message biểu diễn cùng một sự kiện.

Nếu dùng dual-publish:

- Ghi cả hai publication trong cùng transaction nghiệp vụ hoặc cùng outbox boundary phù hợp.
- Dùng cùng business event ID/causation ID để liên kết hai biểu diễn.
- Quy định consumer nào xử lý V1, consumer nào xử lý V2.
- Bảo đảm consumer không nhận cả hai và áp dụng side effect hai lần.
- Theo dõi số lượng V1/V2 và xác định mốc dừng V1.

Không dual-publish vô thời hạn. Nó làm tăng lưu lượng, độ phức tạp kiểm thử và nguy cơ hai phiên bản đi lệch nhau về dữ liệu.

## 8. Version trong tên và schema registry

Với JSON, consumer thường nhận type identifier và payload rồi ánh xạ tới DTO tương ứng. Với Avro, Protobuf hoặc định dạng có schema registry, schema ID/version giúp xác định cách giải mã payload.

Version trong event name và schema registry có thể cùng tồn tại:

- Event name xác định loại sự kiện và hợp đồng công khai, ví dụ `orders.order-confirmed.v2`.
- Schema ID xác định chính xác schema dùng để encode một message.
- Aggregate version xác định thứ tự thay đổi của đơn hàng.

Không nên coi schema registry thay thế event naming. Schema registry có thể xác định cấu trúc nhưng không tự giải quyết việc ý nghĩa nghiệp vụ đã thay đổi hay chưa. Ngược lại, chỉ thêm `V2` vào tên class cũng không đủ nếu serializer không truyền type/version metadata tới consumer.

Đối với externalization trong Spring Modulith, hãy kiểm tra integration adapter đang dùng để biết type information, headers và serialization được ánh xạ thế nào. Không giả định mọi broker adapter đều tự động tạo cùng một wire format.

## 9. Event version và Event Publication Registry

Spring Modulith Event Publication Registry theo dõi publication tới listener. Khi event được lưu bền vững để phục hồi sau restart, khả năng deserialize event cũ là một phần của chiến lược versioning.

Khi thay đổi tên class hoặc cấu trúc event:

- Xác định publication V1 còn incomplete hay không.
- Giữ class và serializer cần thiết để đọc publication V1 cho tới khi xử lý xong.
- Không xóa publication pending chỉ để hoàn tất migration.
- Nếu cần chuyển đổi payload đã lưu, thực hiện migration có kiểm soát và có cách rollback.
- Giữ khả năng đọc event cũ trong thời gian retry/replay và backup còn hiệu lực.

Registry không phải event store dài hạn; publication completed có thể được dọn theo retention. Nếu cần replay lịch sử nghiệp vụ qua nhiều năm, hãy lưu integration event hoặc audit event trong kho có schema/version lifecycle riêng.

## 10. Replay và tương thích dữ liệu cũ

Replay có thể đưa event V1 đã lưu từ nhiều tháng trước tới consumer mới. Consumer cần quyết định cách xử lý:

1. Giữ handler V1 và ánh xạ V1 sang mô hình nội bộ hiện tại.
2. Dùng upcaster để chuyển payload V1 sang cấu trúc nội bộ mới trước khi xử lý.
3. Rebuild projection từ nguồn dữ liệu chuẩn nếu replay trực tiếp không còn phù hợp.

Upcaster nên là bước chuyển đổi xác định, có kiểm thử bằng payload mẫu của từng version. Không ghi đè event lịch sử gốc khi không cần; giữ lại nguồn gốc giúp audit và điều tra.

Replay cũng cần idempotency. Event có cùng ID được xử lý lại không được tạo side effect nghiệp vụ trùng. Nếu V1 và V2 là hai biểu diễn của cùng business event, cần một định danh chung để consumer nhận ra mối quan hệ đó.

## 11. Kiểm thử hợp đồng giữa các version

Kiểm thử versioning không chỉ là kiểm tra class mới serialize được. Cần kiểm tra cả tương thích và hành vi consumer:

- V1 vẫn deserialize và được handler V1 xử lý trong thời gian migration.
- V2 serialize thành payload theo schema và type identifier đã công bố.
- Consumer mới xử lý đúng V1 và V2 hoặc từ chối version không hỗ trợ theo cách có quan sát.
- Field bổ sung, field thiếu, null, enum và kiểu dữ liệu có hành vi rõ ràng.
- Payload V1 đã lưu có thể được replay bằng code hiện tại.
- Dual-publish không tạo side effect trùng.
- Event cùng aggregate giữ đúng ordering theo aggregate version, độc lập với contract version.
- Consumer cũ không bị gửi V2 trước khi nó được nâng cấp.

Có thể lưu payload mẫu đã loại bỏ dữ liệu nhạy cảm cho mỗi version và dùng chúng làm contract test. Khi thay đổi schema, chạy test trên payload cũ và mới để phát hiện lỗi tương thích trước khi triển khai.

## 12. Quan sát việc chuyển đổi version

Trong giai đoạn migration, dashboard và log cần cho biết version nào đang được phát và xử lý:

| Tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| Message count theo event type/version | Publisher còn phát V1 hay đã chuyển sang V2? |
| Consumer success/failure theo version | Consumer nào chưa hỗ trợ version mới? |
| Parse/schema error theo version | Payload lỗi ở version nào? |
| Pending publication theo event type | Có publication cũ đang chờ xử lý không? |
| Replay count theo version | Có consumer nào đang phát lại dữ liệu lịch sử? |

Event type/version là dimension có tập giá trị giới hạn nên thường phù hợp làm metric tag. Không đưa event ID, order ID hoặc correlation ID vào metric label vì cardinality cao; dùng structured log và trace cho từng message.

Chỉ ngừng version cũ khi số liệu cho thấy không còn consumer cần nó và thời hạn retention/replay đã được đáp ứng. Việc không thấy message V1 trong một cửa sổ ngắn chưa đủ chứng minh không còn consumer hoặc bản ghi V1 pending.

## 13. Những sai lầm cần tránh

- Dùng `V2` để biểu diễn lần deploy mới dù hợp đồng không thay đổi.
- Đổi ý nghĩa payload nhưng vẫn giữ tên V1.
- Nhầm event contract version với aggregate version hoặc schema ID.
- Giả định thêm field luôn tương thích với mọi consumer.
- Giả định `@Externalized` tự tạo topic hoặc tự quản lý schema version.
- Ngừng V1 trước khi consumer cũ và replay window đã được xử lý.
- Dual-publish mà không có idempotency hoặc định danh liên kết.
- Xóa class/serializer V1 khi registry còn publication cũ cần deserialize.
- Coi schema registry thay thế việc quản lý ý nghĩa nghiệp vụ của event.

## Kết luận

Đưa version vào tên event là cách công bố rõ một hợp đồng mới khi cấu trúc hoặc ý nghĩa event thay đổi không tương thích. Hãy tách event contract version khỏi schema version và aggregate version, đặt quy ước tên ổn định, cho consumer hiểu version mới trước khi publisher chuyển đổi và duy trì khả năng đọc dữ liệu cũ trong thời gian retry/replay. Với Spring Modulith, cần xét cả application listener, externalization và Event Publication Registry để migration không làm mất publication hoặc tạo side effect trùng.
