# Tương thích tiến

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, event là hợp đồng giao tiếp giữa producer và consumer. Khi producer thay đổi cấu trúc event, consumer đang chạy phiên bản cũ vẫn có thể nhận message mới. **Tương thích tiến (forward compatibility)** mô tả khả năng một consumer hoặc reader cũ tiếp tục đọc và xử lý dữ liệu được tạo theo schema mới hơn.

Khả năng này đặc biệt quan trọng khi các module được triển khai độc lập, event được externalize qua broker hoặc message được lưu để retry và replay. Producer có thể phát event mới trong khi một số consumer chưa được nâng cấp. Nếu consumer cũ không chịu được field mới, enum value mới hoặc event type mới, thay đổi tưởng như chỉ bổ sung schema có thể làm gián đoạn toàn bộ luồng xử lý.

Tương thích tiến không chỉ là deserialize thành công. Consumer cũ phải hiểu đủ ý nghĩa nghiệp vụ để tiếp tục xử lý an toàn. Một parser bỏ qua field lạ nhưng lại áp dụng sai quy tắc khi gặp giá trị mới vẫn có thể tạo dữ liệu sai. Vì vậy, cần kiểm tra cả khả năng đọc, cách xử lý giá trị chưa biết và semantics của event.

## 1. Xác định đúng chiều tương thích

Các thuật ngữ backward và forward compatibility thường được xác định theo chiều reader và writer:

- **Backward compatibility:** reader mới đọc được dữ liệu do writer cũ tạo ra.
- **Forward compatibility:** reader cũ đọc được dữ liệu do writer mới tạo ra.
- **Full compatibility:** cả reader cũ và reader mới đều đọc được dữ liệu do writer ở phiên bản còn lại tạo ra, theo phạm vi chính sách đã chọn.

Với event, forward compatibility có nghĩa consumer phiên bản cũ vẫn xử lý được event do producer phiên bản mới phát. Ví dụ producer v2 bổ sung field deliveryNote vào OrderConfirmed; consumer v1 vẫn phải đọc và xử lý được event đó nếu field mới không ảnh hưởng tới hành vi mà consumer v1 chịu trách nhiệm.

| Writer | Reader | Câu hỏi tương thích |
|---|---|---|
| Producer cũ | Consumer mới | Consumer mới có đọc được event lịch sử không? |
| Producer mới | Consumer cũ | Consumer cũ có đọc và xử lý event mới không? |
| Producer mới | Consumer mới | Hai phiên bản có hiểu cùng contract không? |
| Event lịch sử được replay | Consumer hiện tại | Consumer hiện tại có đọc được dữ liệu đã lưu từ trước không? |

Trong một hệ thống event-driven, cả hai chiều đều quan trọng. Consumer mới thường phải đọc được event cũ vì broker, registry hoặc archive có thể phát lại dữ liệu lịch sử. Consumer cũ phải chịu được event mới trong thời gian rollout có nhiều phiên bản chạy song song.

## 2. Phân biệt tương thích cú pháp và tương thích ngữ nghĩa

Tương thích cú pháp là khả năng parse hoặc deserialize message. Tương thích ngữ nghĩa là khả năng hiểu và xử lý message mà không vi phạm nghiệp vụ.

Ví dụ, producer mới bổ sung field priority với giá trị EXPRESS. Consumer cũ bỏ qua field mới và deserialize thành công. Nhưng nếu consumer cũ mặc định mọi đơn hàng đều STANDARD, nó có thể vẫn chạy mà không thực hiện hành vi cần thiết cho đơn EXPRESS. Message tương thích cú pháp nhưng không tương thích nghiệp vụ đối với consumer đó.

Trước khi thay đổi event, hãy xác định:

- Consumer nào đọc event và field nào consumer thực sự sử dụng.
- Field mới có làm thay đổi quyết định nghiệp vụ của consumer cũ không.
- Giá trị mặc định có giữ đúng semantics cũ không.
- Consumer có thể bỏ qua thông tin mới một cách an toàn không.
- Trường hợp không hiểu được phải từ chối, cách ly hay chuyển manual review.

Không đánh giá tương thích chỉ bằng việc JSON deserialize không ném exception. Cần kiểm thử hành vi của consumer cũ với payload mới và xác nhận kết quả nghiệp vụ.

## 3. Bắt đầu từ hợp đồng event ổn định

Event tích hợp nên có contract rõ ràng và độc lập với implementation nội bộ. Không nên dùng trực tiếp entity JPA, object graph hoặc tên class Java làm hợp đồng lâu dài giữa module hay hệ thống.

Một envelope có thể gồm:

~~~json
{
  "eventId": "d7b3f5a2-9c21-4a8d-a1c4-52f4e1e30001",
  "eventType": "orders.order-confirmed",
  "schemaVersion": 2,
  "occurredAt": "2026-11-25T10:30:00Z",
  "orderId": "ORD-10025",
  "total": 450000,
  "currency": "VND",
  "deliveryNote": "Giao tại quầy lễ tân"
}
~~~

Các trường định danh và version giúp consumer phân biệt event type, phiên bản contract và lần xảy ra cụ thể. Producer có thể thêm field theo quy tắc tương thích đã công bố.

Một contract tốt xác định:

- Tên event type ổn định và ý nghĩa nghiệp vụ.
- Field bắt buộc, tùy chọn, nullable và đơn vị đo.
- Cách biểu diễn thời gian, tiền tệ và định danh.
- Quy tắc cho field hoặc enum value chưa biết.
- Quy tắc versioning và thời gian hỗ trợ phiên bản cũ.
- Owner chịu trách nhiệm thay đổi contract.
- Consumer và use case bị ảnh hưởng.

Không đổi tên event type hoặc field chỉ để phản ánh refactor class. Tên package và class nội bộ có thể thay đổi; event contract công bố cần ổn định theo semantics nghiệp vụ.

## 4. Thêm field tùy chọn theo cách tương thích tiến

Bổ sung field thường là thay đổi dễ tương thích tiến nhất nếu consumer cũ bỏ qua field chưa biết và field đó không làm thay đổi cách hiểu dữ liệu cũ.

Ví dụ producer v1 phát:

~~~json
{
  "eventType": "orders.order-confirmed",
  "schemaVersion": 1,
  "orderId": "ORD-10025",
  "total": 450000
}
~~~

Producer v2 bổ sung field tùy chọn:

~~~json
{
  "eventType": "orders.order-confirmed",
  "schemaVersion": 2,
  "orderId": "ORD-10025",
  "total": 450000,
  "deliveryNote": "Giao tại quầy lễ tân"
}
~~~

Consumer v1 có thể tiếp tục đọc nếu parser được cấu hình bỏ qua field chưa biết và logic của nó không cần deliveryNote. Consumer v2 có thể sử dụng field mới khi có mặt.

Khi thêm field:

- Giữ nguyên tên và kiểu của field cũ.
- Không làm field mới trở thành bắt buộc đối với consumer cũ.
- Chọn giá trị mặc định có semantics rõ ràng.
- Xác định cách xử lý khi field bị thiếu hoặc null.
- Giới hạn độ dài và kích thước nếu field chứa nội dung tự do.
- Kiểm thử consumer cũ với payload có field mới.

Không mặc định mọi serializer đều bỏ qua field lạ. Cấu hình Jackson có thể bật chế độ fail khi gặp unknown property; schema decoder khác cũng có quy tắc riêng. Hãy xác nhận hành vi của serializer thực tế ở từng consumer.

## 5. Không thay đổi ý nghĩa field hiện có

Một thay đổi nguy hiểm là giữ nguyên tên field nhưng thay đổi semantics. Consumer cũ vẫn parse được nhưng diễn giải sai.

Ví dụ:

- Trước đây total là số tiền tính bằng VND, sau đó producer gửi số tiền theo đơn vị minor unit.
- Trước đây occurredAt là thời điểm UTC, sau đó gửi local time không có offset.
- Trước đây quantity là số lượng đã xác nhận, sau đó đổi thành số lượng yêu cầu.
- Trước đây status=PAID có nghĩa đã capture, sau đó dùng cho trạng thái authorize.
- Trước đây discount là giá trị dương, sau đó dùng số âm để biểu diễn giảm trừ.

Những thay đổi này không phải bổ sung field. Chúng thay đổi ý nghĩa contract và có thể phá vỡ consumer cũ mà không có lỗi deserialize.

Nếu semantics cần thay đổi, hãy tạo field mới hoặc event type/version mới với tên diễn đạt đúng ý nghĩa. Duy trì field cũ trong giai đoạn chuyển tiếp, công bố quy tắc chuyển đổi và chỉ ngừng phát field cũ khi không còn consumer cần nó.

## 6. Giá trị mặc định, null và field bị thiếu

Field tùy chọn cần phân biệt ba trạng thái: field không xuất hiện, field xuất hiện với null và field có giá trị. Không phải serializer hay domain model nào cũng xử lý ba trường hợp này giống nhau.

Ví dụ, thiếu deliveryNote có thể có nghĩa chưa cung cấp ghi chú. Null có thể biểu thị giá trị đã bị xóa. Chuỗi rỗng có thể là người dùng chủ động gửi nội dung rỗng. Nếu consumer gộp các trường hợp này thành một, nó có thể làm mất thông tin nghiệp vụ.

Khi thêm field:

- Quy định field có thể vắng mặt hay không.
- Quy định null có hợp lệ hay không.
- Chọn default khi deserialize hoặc mapping vào domain model.
- Không dùng default giả định một sự kiện nghiệp vụ đã xảy ra nếu producer không gửi dữ liệu đó.
- Với update/patch event, phân biệt “không thay đổi” với “xóa giá trị”.
- Giữ hành vi cũ khi field mới không có trong event lịch sử.

Nếu field mới là bắt buộc để consumer thực hiện một quyết định an toàn, thay đổi đó không tương thích tiến với consumer cũ. Cần nâng cấp consumer hoặc công bố một event/command mới có contract rõ ràng.

## 7. Enum và giá trị chưa biết

Thêm enum value có thể phá vỡ consumer cũ. Ví dụ producer mới phát paymentStatus=PARTIALLY_REFUNDED trong khi consumer cũ chỉ biết CAPTURED, DECLINED và REFUNDED.

Một số parser có thể ném exception khi gặp enum value không nhận diện. Một số runtime có thể giữ giá trị numeric chưa biết nhưng application code vẫn không biết phải xử lý ra sao. Tương thích tiến đòi hỏi quy tắc rõ ràng cho giá trị mới.

Các lựa chọn:

- Dùng string code trong integration contract và có nhánh UNKNOWN/UNSUPPORTED.
- Giữ nguyên raw value để log hoặc lưu lại khi cần điều tra.
- Bỏ qua giá trị mới chỉ khi hành vi đó thực sự an toàn.
- Cách ly event hoặc chuyển manual review nếu giá trị mới ảnh hưởng tới invariant.
- Không mặc định giá trị chưa biết là một trạng thái thành công.
- Kiểm thử consumer cũ với enum value chưa từng xuất hiện.

Không dùng ordinal của Java enum làm contract. Thứ tự enum có thể thay đổi và ordinal không mang ý nghĩa ổn định giữa các phiên bản. Dùng mã chuỗi hoặc numeric code được công bố rõ ràng.

## 8. Event type mới và consumer cũ

Bổ sung một event type mới khác với bổ sung field vào event type hiện tại. Consumer cũ có thể không đăng ký listener cho event type mới hoặc có thể nhận message nhưng không có handler tương ứng.

Cần xác định transport và adapter xử lý unknown event type thế nào:

- Không subscribe event type mới: consumer cũ không nhận message đó.
- Nhận qua wildcard/topic chung: deserializer hoặc router có thể từ chối.
- Có generic envelope: consumer có thể ghi nhận và bỏ qua event không thuộc phạm vi.
- Event type bắt buộc phải được xử lý: consumer cũ cần được nâng cấp trước khi producer phát.

Không được bỏ qua event type lạ một cách mù quáng nếu nó đại diện cho một thay đổi cần thiết để giữ invariant. Với consumer chỉ tạo projection không quan trọng, có thể bỏ qua có kiểm soát và phát metric. Với consumer thực hiện thanh toán, cấp quyền hoặc thay đổi tồn kho, cần từ chối hoặc cách ly để tránh mất tác dụng nghiệp vụ.

## 9. Tương thích tiến trong Jackson và JSON

Với JSON, consumer cũ thường có thể đọc payload mới nếu parser bỏ qua property chưa biết. Tuy nhiên, hành vi phụ thuộc cấu hình và DTO.

Ví dụ cấu hình hoặc annotation có thể điều khiển unknown property ở phạm vi phù hợp. Không nên thay đổi cấu hình toàn ứng dụng chỉ để làm một event tương thích nếu điều đó che giấu lỗi contract ở các API khác.

Một DTO integration có thể giữ field tùy chọn và default rõ ràng:

~~~java
public record OrderConfirmedV2(
    String eventId,
    String orderId,
    long total,
    String currency,
    String deliveryNote
) {}
~~~

Nếu consumer v1 dùng DTO không có deliveryNote, cần xác nhận ObjectMapper của consumer có bỏ qua property lạ. Nếu bật fail-on-unknown-properties, consumer sẽ ném lỗi khi deserialize payload v2.

Không dùng một DTO nội bộ thay đổi tùy ý cho nhiều contract khác nhau. Có thể dùng adapter chuyển external event schema sang command/domain model riêng. Như vậy, consumer kiểm soát cách xử lý field mới mà không để schema transport lan vào toàn bộ domain.

## 10. Tương thích tiến với Avro và Protobuf

Các format schema-based có quy tắc tương thích riêng. Không nên suy luận quy tắc từ JSON rồi áp dụng nguyên xi.

**Avro** dùng writer schema và reader schema để giải quyết dữ liệu. Trong chính sách forward compatibility, reader cũ phải có thể đọc dữ liệu được ghi theo schema mới. Thêm field mới thường cần default phù hợp để reader cũ có thể resolve khi writer schema có field mới mà reader không khai báo; cần xác nhận theo quy tắc schema resolution và công cụ đang dùng.

**Protocol Buffers** cho phép parser cũ bỏ qua field number chưa biết. Khi xóa field, không tái sử dụng field number hoặc tên đã dùng; hãy reserve chúng trong schema để tránh dữ liệu cũ bị diễn giải thành field mới. Giá trị enum mới cũng cần được xử lý có chủ đích trong code consumer cũ.

Với Schema Registry, chế độ FORWARD thường kiểm tra khả năng schema cũ đọc dữ liệu được ghi bởi schema mới theo quy tắc format. Cần xác nhận policy đang cấu hình cho subject cụ thể và cách registry kiểm tra version. Một schema pass compatibility check không chứng minh logic nghiệp vụ của consumer xử lý đúng giá trị mới.

## 11. Mở rộng rồi thu hẹp contract (expand-contract)

Một rollout an toàn thường chia thay đổi thành giai đoạn mở rộng và giai đoạn thu hẹp.

Ví dụ cần thay field customerName bằng customerReference:

1. **Mở rộng schema:** thêm customerReference tùy chọn, giữ customerName.
2. **Nâng cấp consumer:** consumer mới đọc cả customerName và customerReference; ưu tiên reference khi có.
3. **Nâng cấp producer:** bắt đầu phát cả hai field trong thời gian chuyển tiếp.
4. **Quan sát:** xác nhận mọi consumer đã đọc được customerReference và không còn phụ thuộc field cũ.
5. **Ngừng phụ thuộc cũ:** cập nhật consumer để không cần customerName.
6. **Thu hẹp schema:** ngừng phát và sau đó loại bỏ customerName theo chính sách versioning, replay và retention.

Trình tự này cho phép nhiều phiên bản producer và consumer cùng tồn tại. Không xóa field cũ ngay khi producer mới đã phát field mới; consumer cũ hoặc event lịch sử vẫn có thể cần field đó.

Nếu field cũ chứa dữ liệu nhạy cảm cần xóa, phải kết hợp migration với chính sách retention/deletion. Không giữ dữ liệu cá nhân vô thời hạn chỉ để tương thích; hãy dùng reference, mapping chuyển tiếp hoặc event version mới theo quy định.

## 12. Kế hoạch rollout khi có nhiều phiên bản consumer

Trong hệ thống triển khai rolling hoặc nhiều service độc lập, producer và consumer có thể không được nâng cấp đồng thời. Trước khi producer phát schema mới, cần biết consumer nào đang chạy và khả năng đọc của chúng.

Một kế hoạch rollout điển hình:

~~~mermaid
flowchart TD
    A["Consumer cũ đang chạy"] --> B["Nâng consumer để chấp nhận schema cũ và mới"]
    B --> C["Xác nhận consumer mới đã sẵn sàng"]
    C --> D["Producer phát schema mới theo contract"]
    D --> E["Theo dõi lỗi deserialize và xử lý nghiệp vụ"]
    E --> F["Ngừng field cũ sau khi hết consumer phụ thuộc"]
    F --> G["Loại bỏ field cũ theo thời hạn replay"]
~~~

Nếu consumer cũ không thể bỏ qua field mới, cần triển khai consumer tương thích trước producer. Nếu producer không thể giữ đồng thời schema cũ và mới, cân nhắc event type/version mới và routing theo subscription để tránh gửi message không thể đọc tới consumer cũ.

Không dựa vào thời điểm deploy hoàn tất để kết luận tất cả consumer đã nâng cấp. Có thể có instance cũ chưa restart, consumer group bị pause hoặc một hệ thống đối tác triển khai ngoài lịch. Dùng telemetry phiên bản consumer, contract test và xác nhận vận hành trước khi thu hẹp schema.

## 13. Event version và schema version

Event version có thể chỉ phiên bản semantics của event; schema version mô tả cấu trúc payload. Hai khái niệm có thể trùng nhau nhưng không bắt buộc.

Ví dụ thêm một field optional không làm thay đổi semantics có thể chỉ tăng schema version. Nếu thay đổi ý nghĩa OrderConfirmed hoặc cách hiểu trạng thái thanh toán, có thể cần event version mới hoặc event type mới.

Một số trường metadata hữu ích:

- eventType: loại sự kiện nghiệp vụ ổn định.
- schemaVersion: phiên bản cấu trúc payload.
- eventId: định danh lần xảy ra.
- occurredAt: thời điểm nghiệp vụ xảy ra.
- producerName/producerVersion: nguồn và phiên bản producer để điều tra.
- correlationId/causationId: liên kết quy trình và nguyên nhân.

Không tăng version cho mọi lần release ứng dụng nếu contract không thay đổi. Cũng không giữ version cố định khi semantics đã đổi. Version phải giúp consumer chọn cách diễn giải, không chỉ là số build.

## 14. Upcasting event cũ cho consumer mới

Consumer mới có thể cần đọc event lịch sử với schema cũ. **Upcasting** chuyển payload cũ thành representation mới trước khi logic hiện tại xử lý.

Ví dụ event v1 chỉ có total và currency, trong khi model nội bộ mới có thêm taxAmount. Upcaster có thể tạo representation mới với taxAmount mặc định chỉ khi semantics cũ cho phép suy ra giá trị đó. Nếu không thể suy ra an toàn, phải giữ trạng thái unknown hoặc dùng nhánh xử lý riêng.

Nguyên tắc:

- Upcast theo chuỗi version rõ ràng, chẳng hạn v1 → v2 → v3.
- Không sửa payload gốc trong event store hoặc archive.
- Upcaster phải deterministic và có thể chạy lại.
- Kiểm thử dữ liệu lịch sử thực tế hoặc fixture đại diện.
- Không tạo ra giá trị mặc định làm thay đổi ý nghĩa nghiệp vụ.
- Ghi nhận version đầu vào và version representation sau chuyển đổi.

Upcasting thường phục vụ backward compatibility cho reader mới đọc event cũ. Nó bổ sung cho forward compatibility nhưng không thay thế việc consumer cũ chịu được payload mới.

## 15. Replay và event lịch sử

Event có thể được replay sau nhiều tháng để rebuild projection hoặc khôi phục consumer. Vì vậy, một thay đổi schema cần xét cả event mới và dữ liệu lịch sử.

Consumer hiện tại có thể phải đọc:

- Event cũ được lưu trong broker hoặc event store.
- Event mới do producer hiện tại phát.
- Event đã qua upcasting.
- Event được replay từ archive.
- Event từ producer khác đang chạy phiên bản cũ.

Hãy giữ fixture của các schema version được hỗ trợ và kiểm thử consumer mới với chúng. Nếu consumer cũ vẫn có thể được khởi động trong môi trường replay, kiểm tra rằng nó không nhận event type hoặc payload vượt khả năng của nó.

Khi ngừng hỗ trợ schema cũ, xác định rõ thời điểm không còn replay hợp lệ, dữ liệu lịch sử đã được migrate hoặc consumer có upcaster. Không xóa schema version khỏi registry chỉ vì producer không còn phát nó; consumer và archive có thể vẫn cần schema để deserialize dữ liệu cũ.

## 16. Contract test cho forward compatibility

Contract test phải kiểm tra đúng chiều: payload được producer mới tạo ra được consumer cũ đọc và xử lý đúng.

Một ma trận test nên có:

| Producer fixture | Consumer implementation | Điều cần xác nhận |
|---|---|---|
| Schema v1 | Consumer v1 | Hành vi hiện tại không đổi |
| Schema v2 có field mới | Consumer v1 | Deserialize và xử lý an toàn |
| Schema v2 có enum mới | Consumer v1 | Fallback, reject hoặc quarantine theo policy |
| Event type mới | Consumer v1 | Ignore có kiểm soát hoặc từ chối rõ ràng |
| Schema v1 lịch sử | Consumer v2 | Backward compatibility/upcasting |
| Schema v2 | Consumer v2 | Hành vi mới theo contract |

Các test cần kiểm tra cả parser và kết quả nghiệp vụ. Nếu consumer v1 bỏ qua field deliveryNote, hãy xác nhận các hành vi cũ vẫn đúng. Nếu gặp enum value mới, xác nhận consumer không vô tình coi nó là trạng thái thành công.

Có thể lưu payload fixture theo từng schema version và chạy trong CI khi contract thay đổi. Với Avro/Protobuf và Schema Registry, thêm bước compatibility check ở registry policy. Với JSON, test ObjectMapper/converter thực tế của consumer.

## 17. Kiểm tra consumer cũ với payload mới

Một test minh họa cho JSON có thể deserialize payload v2 bằng cấu hình mapper của consumer v1:

~~~java
@Test
void oldConsumerReadsPayloadWithAdditionalField() throws Exception {
    String payload = """
        {
          "eventType": "orders.order-confirmed",
          "schemaVersion": 2,
          "orderId": "ORD-10025",
          "total": 450000,
          "currency": "VND",
          "deliveryNote": "Giao tại quầy lễ tân"
        }
        """;

    OrderConfirmedV1 event =
        objectMapper.readValue(payload, OrderConfirmedV1.class);

    assertThat(event.orderId()).isEqualTo("ORD-10025");
    assertThat(event.total()).isEqualTo(450000);
}
~~~

Test này chỉ chứng minh deserialization và mapping field cũ. Cần thêm test gọi handler của consumer cũ và xác nhận kết quả nghiệp vụ không thay đổi ngoài dự kiến.

Với enum hoặc event type mới, tạo fixture riêng. Không chỉ test field bổ sung vì những thay đổi này thường gây lỗi ở nhánh switch, router hoặc handler registry.

## 18. Xử lý consumer không tương thích

Nếu consumer cũ không thể đọc event mới, cần có chính sách xử lý thay vì để message retry vô hạn.

Các lựa chọn:

- **Retry:** chỉ dùng khi lỗi tạm thời, không phải khi contract chắc chắn không tương thích.
- **Quarantine/DLQ:** giữ message cùng metadata để điều tra và replay sau khi consumer được nâng cấp.
- **Version-specific routing:** gửi event version mới tới consumer đã hỗ trợ.
- **Compatibility adapter:** chuyển schema mới về contract cũ nếu có thể bảo toàn semantics.
- **Manual review:** dùng khi không thể tự động diễn giải an toàn.

Không chuyển event mới thành event cũ bằng cách bỏ field hoặc đổi enum một cách tùy tiện. Adapter phải biết rõ field nào có thể bỏ, giá trị nào có thể ánh xạ và trường hợp nào cần từ chối.

Khi message bị quarantine, lưu eventId, eventType, schemaVersion, producer, thời điểm, lỗi deserialize và consumer version. Hạn chế lưu payload nhạy cảm ngoài chính sách retention. Có quy trình replay sau khi consumer tương thích được triển khai.

## 19. Tương thích tiến trong Spring Modulith

Trong cùng một ứng dụng Spring Modulith, các module thường được biên dịch và triển khai cùng artifact. Thay đổi class event có thể làm compile-time consumer phát hiện lỗi sớm. Tuy nhiên, vẫn có các trường hợp cần forward compatibility:

- Event được externalize qua broker tới service triển khai độc lập.
- Application event hoặc publication được lưu bền vững rồi xử lý sau khi ứng dụng nâng cấp.
- Consumer và producer chạy nhiều phiên bản trong rolling deployment.
- Event được replay từ broker, archive hoặc dead-letter queue.
- Module khác nhận integration event theo contract công khai.

Dùng event DTO công khai và adapter giữa internal domain event với integration event. Internal event có thể phản ánh chi tiết domain trong ứng dụng; integration event cần contract ổn định, có version và data minimization.

Với **@ApplicationModuleListener**, kiểm tra listener ở ranh giới module và semantics transaction của nó. Với event externalization, kiểm tra serializer, message converter, destination và consumer version. Không giả định việc compile thành công chứng minh payload đã lưu hoặc message trên broker tương thích với phiên bản ứng dụng mới.

Event Publication Registry có thể giữ publication chưa hoàn tất để phục hồi. Khi ứng dụng nâng cấp, cần xác nhận event đã lưu có thể deserialize và listener mới xử lý được. Nếu representation cũ không còn tương thích, cần upcasting hoặc migration có kiểm soát trước khi resubmit.

## 20. Observability và quản trị vòng đời version

Tương thích tiến cần được quan sát trong production. Nên ghi nhận event type, schema version, producer version, consumer version, kết quả deserialize và kết quả xử lý.

Các metrics hữu ích:

- Số event theo eventType và schemaVersion.
- Tỷ lệ deserialize failure theo consumer version.
- Số event bị quarantine hoặc dead-letter do schema không tương thích.
- Số consumer instance còn chạy phiên bản cũ.
- Tỷ lệ event bị xử lý qua fallback/unknown enum.
- Số publication incomplete và tuổi publication.
- Thời gian từ khi producer phát version mới tới khi mọi consumer xác nhận hỗ trợ.

Không dùng eventId, orderId hoặc customerId làm metric tag vì cardinality cao. Dùng các định danh đó trong log và trace có kiểm soát. Tránh log toàn bộ payload nếu chứa dữ liệu nhạy cảm.

Một compatibility dashboard nên trả lời: producer nào đang phát schema version nào, consumer nào đã hỗ trợ, consumer nào còn lỗi và còn bao nhiêu event lịch sử cần xử lý. Chỉ thu hẹp contract sau khi có bằng chứng consumer cũ không còn được sử dụng và replay horizon đã được xử lý.

## 21. Những thay đổi thường phá vỡ forward compatibility

Các thay đổi sau cần được xem là breaking hoặc cần phân tích kỹ:

- Xóa field mà consumer cũ vẫn đọc.
- Đổi tên field hoặc đổi kiểu dữ liệu.
- Đổi đơn vị đo hoặc semantics mà không đổi contract.
- Thêm field bắt buộc khiến consumer mới không đọc được event cũ.
- Thêm enum value mà consumer cũ không có fallback.
- Thêm event type vào routing chung khiến consumer cũ không có handler.
- Đổi event type hoặc discriminator.
- Đổi cách serialize ngày giờ, decimal hoặc null.
- Tăng kích thước payload vượt giới hạn broker/consumer.
- Thay đổi encryption hoặc compression mà consumer cũ không hiểu.

Không phải mọi thay đổi đều phải tạo event type mới. Field optional có semantics độc lập thường có thể được thêm vào contract hiện tại. Nhưng khi consumer cũ không thể xử lý an toàn hoặc meaning thay đổi, cần một version mới hoặc adapter chuyển đổi.

## 22. Quy trình thay đổi event tương thích tiến

Khi cần bổ sung hoặc thay đổi event contract, thực hiện theo thứ tự:

1. Liệt kê producer, consumer, phiên bản đang chạy và event history cần replay.
2. Xác định field, enum hoặc semantics sẽ thay đổi.
3. Phân loại thay đổi là additive, optional hay breaking.
4. Kiểm tra consumer cũ có bỏ qua field mới và xử lý giá trị chưa biết an toàn không.
5. Bổ sung contract test với payload mới chạy qua consumer cũ.
6. Chạy compatibility check của schema registry nếu sử dụng schema-based format.
7. Triển khai consumer có khả năng đọc cả schema cũ và mới.
8. Xác nhận consumer đã sẵn sàng trước khi producer phát dữ liệu mới.
9. Triển khai producer và theo dõi deserialize failure, DLQ, fallback cùng consumer lag.
10. Duy trì field/event cũ trong thời gian chuyển tiếp.
11. Kiểm thử replay event lịch sử và upcasting nếu cần.
12. Chỉ loại bỏ contract cũ khi consumer, archive, registry và replay policy không còn phụ thuộc.

Tương thích tiến giúp consumer cũ tiếp tục hoạt động khi producer phát event theo schema mới. Để đạt được điều đó, hãy giữ ổn định semantics cũ, thêm field tùy chọn có default rõ ràng, xử lý giá trị chưa biết có chủ đích và kiểm thử payload mới bằng consumer cũ. Kết hợp expand-contract rollout, contract testing, version metadata, upcasting và observability sẽ giúp Spring Modulith application events tiến hóa theo thời gian mà không làm gián đoạn các module hoặc service đang chạy phiên bản cũ.

