# Tương thích lùi

*Tiến hóa event contract mà không làm hỏng producer, consumer và dữ liệu lịch sử*

Trong hệ thống Spring Modulith, một application event có thể được xử lý bởi nhiều listener nội bộ hoặc được externalize đến broker để các tiến trình độc lập tiêu thụ. Producer và consumer thường được triển khai ở những thời điểm khác nhau; message đã lưu trong broker hoặc event store cũng có thể được đọc lại sau nhiều ngày. Vì vậy, thay đổi cấu trúc event phải tính đến cả consumer đang chạy, producer phiên bản cũ và message lịch sử.

**Tương thích lùi** là khả năng phiên bản consumer mới tiếp tục đọc và hiểu message được tạo theo hợp đồng cũ. Trong triển khai phân tán, còn cần kiểm tra chiều ngược lại: consumer cũ có đọc được message mới do producer mới phát hay không. Đừng chỉ dựa vào tên “backward” hoặc “forward” của một công cụ schema registry, vì cách gọi có thể được định nghĩa theo góc nhìn writer/reader. Hãy mô tả rõ phiên bản producer và consumer nào phải tương tác được.

## 1. Vì sao event contract phải tương thích?

Một event có thể tồn tại lâu hơn phiên bản ứng dụng đã tạo ra nó. Consumer có thể đang chạy phiên bản cũ trong lúc producer đã được nâng cấp. Broker có thể giữ message theo retention; publication hoặc event được resubmit sau sự cố; projection mới có thể replay lịch sử để dựng lại read model.

Nếu producer đổi tên field, thay kiểu dữ liệu hoặc đổi ý nghĩa một giá trị mà không có kế hoạch, consumer cũ có thể deserialize thất bại hoặc hiểu sai nghiệp vụ. Nếu consumer mới chỉ đọc được schema mới, việc replay message cũ có thể thất bại dù luồng event hiện tại đang hoạt động.

Một thay đổi event contract cần trả lời:

- Producer mới có thể phát message mà consumer cũ vẫn đọc an toàn không?
- Consumer mới có thể đọc message do producer cũ tạo ra không?
- Các message đang nằm trong broker, archive hoặc event store có còn đọc được không?
- Listener nội bộ và external consumer có cùng hiểu ý nghĩa field không?
- Việc replay hoặc resubmit có giữ nguyên ý nghĩa event đã phát trước đó không?

## 2. Phân biệt hai chiều tương thích

Để tránh nhầm thuật ngữ, dùng ma trận phiên bản cụ thể:

| Producer | Consumer | Câu hỏi |
|---|---|---|
| Cũ | Mới | Consumer mới có đọc được message cũ không? Đây là yêu cầu quan trọng cho replay và triển khai consumer trước |
| Mới | Cũ | Consumer cũ có đọc được message mới không? Đây là yêu cầu quan trọng khi producer được triển khai trước hoặc rollout có overlap |
| Mới | Mới | Hai phiên bản mới có cùng hiểu schema và semantics không? |
| Cũ | Cũ | Luồng hiện tại có tiếp tục hoạt động trong giai đoạn rollout không? |

Một thay đổi có thể tương thích theo một chiều nhưng không tương thích theo chiều còn lại. Ví dụ, thêm field tùy chọn thường cho phép consumer mới đọc message cũ nếu consumer có default phù hợp. Consumer cũ đọc message mới phụ thuộc serializer: một số JSON reader bỏ qua field không biết, trong khi một số định dạng hoặc cấu hình strict có thể từ chối.

Khi lập kế hoạch rollout, hãy ghi rõ ma trận phiên bản được hỗ trợ thay vì chỉ ghi “schema compatible”.

## 3. Thiết kế event contract ổn định ngay từ đầu

Event nên là hợp đồng nghiệp vụ độc lập với entity và cấu trúc lưu trữ. Ví dụ:

```java
public record OrderCompletedV1(
    UUID eventId,
    UUID orderId,
    Instant completedAt,
    long totalAmountMinor
) {}
```

Các nguyên tắc thiết kế:

- Dùng tên field mô tả ý nghĩa nghiệp vụ, không dùng tên cột database hoặc tên biến nội bộ dễ thay đổi.
- Dùng kiểu dữ liệu có ý nghĩa ổn định: UUID cho định danh, timestamp có múi giờ/offset rõ ràng, số nguyên minor unit cho tiền nếu hợp đồng chọn cách đó.
- Có event ID ổn định để deduplicate và truy vết.
- Xác định rõ đơn vị, currency, timezone, nullability và semantics của từng field.
- Chỉ công bố dữ liệu consumer cần và được phép nhận.
- Tránh serialize JPA entity, lazy relation hoặc object nội bộ của module.

Tương thích không chỉ là deserialize thành công. Consumer phải hiểu đúng ý nghĩa. Đổi `totalAmountMinor` từ “tổng trước thuế” thành “tổng sau thuế” mà vẫn giữ nguyên tên field là thay đổi không tương thích về semantics dù schema không đổi.

## 4. Thêm field mới theo cách tương thích

Thêm field thường là thay đổi dễ quản lý nếu field mới có thể vắng mặt trong message cũ và consumer cũ có thể bỏ qua field không biết.

Message phiên bản cũ:

```json
{
  "eventType": "orders.completed",
  "schemaVersion": 1,
  "eventId": "6d947d20-5b1c-45c6-a6d6-87c7c96d9f12",
  "orderId": "7b0e0d16-37b1-4b77-9a4d-bc7c7a8d8a01",
  "totalAmountMinor": 12500
}
```

Phiên bản mới bổ sung currency:

```json
{
  "eventType": "orders.completed",
  "schemaVersion": 2,
  "eventId": "6d947d20-5b1c-45c6-a6d6-87c7c96d9f12",
  "orderId": "7b0e0d16-37b1-4b77-9a4d-bc7c7a8d8a01",
  "totalAmountMinor": 12500,
  "currency": "VND"
}
```

Để consumer mới đọc được message cũ, consumer cần có quy tắc khi `currency` vắng mặt. Có thể dùng default chỉ khi ý nghĩa default được xác định chắc chắn bởi hợp đồng, ví dụ hệ thống trước đây chỉ hỗ trợ một currency. Nếu không thể suy ra an toàn, consumer phải đánh dấu dữ liệu chưa xác định hoặc yêu cầu version mới.

Để consumer cũ đọc được message mới, xác nhận serializer/deserializer của consumer có bỏ qua field lạ hay không. Không giả định mọi JSON mapper hoặc schema format đều có cùng hành vi. Kiểm tra cấu hình strict unknown-property, generated schema và contract test thực tế.

## 5. Field tùy chọn, null và default

Ba trạng thái “không có field”, “field có giá trị null” và “field có giá trị mặc định” có thể mang ý nghĩa khác nhau. Hợp đồng phải xác định rõ:

- Field có thể vắng mặt không?
- Nếu có mặt với `null`, consumer hiểu là không biết, chưa có hay xóa giá trị?
- Default do producer ghi vào payload hay do consumer suy ra khi đọc?
- Default có giữ đúng nghĩa của message cũ không?

Không dùng default tùy tiện để làm cho deserialize thành công. Ví dụ, nếu `currency` vắng mặt không đồng nghĩa `VND`, tự gán `VND` có thể làm sai dữ liệu lịch sử.

Với Java record, cân nhắc constructor/factory hoặc lớp mapping để chuẩn hóa dữ liệu cũ thành mô hình nội bộ hiện tại. Không phụ thuộc vào một giá trị `defaultValue` trong annotation nếu thư viện serialization không thực sự áp dụng giá trị đó khi field vắng mặt.

## 6. Không đổi tên hoặc xóa field ngay lập tức

Đổi tên field thường được nhìn nhận như xóa field cũ và thêm field mới. Consumer cũ có thể không đọc được payload nếu tên cũ biến mất. Một quy trình an toàn:

1. Thêm field mới nhưng vẫn giữ field cũ.
2. Producer ghi cả hai field trong giai đoạn chuyển tiếp, hoặc adapter chuyển đổi sang schema phù hợp cho từng consumer.
3. Nâng cấp consumer để đọc field mới và có fallback cho field cũ.
4. Quan sát để chắc chắn không còn consumer phụ thuộc field cũ.
5. Ngừng phát field cũ sau khi mọi consumer đã tương thích.
6. Chỉ bỏ hỗ trợ field cũ khỏi reader khi hết thời hạn replay và retention liên quan.

Nếu hai field cùng tồn tại, quy định field nào là nguồn chuẩn và cách xử lý khi giá trị mâu thuẫn. Tránh để consumer tự chọn field khác nhau.

## 7. Thay đổi kiểu dữ liệu và semantics

Thay kiểu dữ liệu có thể phá vỡ cả parser lẫn logic nghiệp vụ. Một số ví dụ:

| Thay đổi | Rủi ro | Cách tiếp cận |
|---|---|---|
| `int` sang `long` | Consumer cũ có thể tràn số hoặc từ chối | Thêm field mới hoặc version schema; kiểm tra giới hạn dữ liệu |
| Số nguyên sang chuỗi | Consumer mong đợi number có thể lỗi | Giữ field cũ trong giai đoạn chuyển tiếp hoặc phát version mới |
| Timestamp local sang UTC instant | Thay đổi cách diễn giải thời gian | Định nghĩa timezone/offset và chuyển đổi rõ ràng |
| Đổi đơn vị tiền | Giá trị có thể parse được nhưng sai nghiệp vụ | Đổi tên field và ghi rõ currency/minor unit |
| Đổi ý nghĩa trạng thái | Consumer có thể thực hiện nhánh sai | Phát event/version mới hoặc field semantics mới |

Đặc biệt, thay đổi semantics thường nguy hiểm hơn thay đổi cấu trúc. Một consumer có thể deserialize thành công nhưng cập nhật read model sai. Mọi thay đổi ý nghĩa cần được xem như thay đổi hợp đồng có khả năng không tương thích.

## 8. Enum và giá trị mới trong tương lai

Khi thêm giá trị enum như `OrderStatus.ON_HOLD`, consumer cũ có thể thất bại nếu deserializer yêu cầu giá trị phải tồn tại trong enum Java. Nếu hợp đồng có khả năng mở rộng, cân nhắc dùng string code và mapping có nhánh unknown rõ ràng.

Ví dụ:

```java
enum KnownOrderStatus {
    OPEN, COMPLETED, CANCELLED, UNKNOWN
}

KnownOrderStatus mapStatus(String value) {
    try {
        return KnownOrderStatus.valueOf(value);
    } catch (IllegalArgumentException ex) {
        return KnownOrderStatus.UNKNOWN;
    }
}
```

Nhánh `UNKNOWN` chỉ an toàn khi consumer có thể xử lý trạng thái chưa biết mà không tạo side effect sai. Với event yêu cầu hành động bắt buộc, không được âm thầm bỏ qua giá trị mới; hãy từ chối có kiểm soát, cảnh báo và chuyển message vào luồng tương thích/điều tra.

## 9. Version hóa envelope và event type

Có thể đặt version trong payload hoặc metadata/envelope. Ví dụ envelope:

```json
{
  "eventType": "orders.completed",
  "schemaVersion": 2,
  "eventId": "6d947d20-5b1c-45c6-a6d6-87c7c96d9f12",
  "occurredAt": "2026-11-25T10:15:30Z",
  "payload": {
    "orderId": "7b0e0d16-37b1-4b77-9a4d-bc7c7a8d8a01",
    "totalAmountMinor": 12500,
    "currency": "VND"
  }
}
```

Envelope tách metadata vận chuyển và truy vết khỏi payload nghiệp vụ. Đặt `schemaVersion` ở một vị trí ổn định, quy định cách diễn giải khi field version vắng mặt và tránh để header broker là nơi duy nhất chứa version nếu message có thể được archive hoặc chuyển qua hệ thống làm mất header.

Không cần tăng version cho mọi field bổ sung tương thích. Tuy vậy, version tường minh giúp consumer chọn mapper hoặc upcaster khi cấu trúc thay đổi. Nếu dùng event type versioned như `orders.completed.v2`, coi đó là một hợp đồng mới và quy định thời gian hỗ trợ type cũ.

## 10. Reader tolerant và validation có kiểm soát

Consumer nên chịu được khác biệt không làm thay đổi semantics, chẳng hạn field mới không liên quan. Nhưng “tolerant reader” không có nghĩa chấp nhận mọi payload.

- Bỏ qua field không biết khi hợp đồng cho phép và field đó không ảnh hưởng nghiệp vụ.
- Có default rõ ràng cho field tùy chọn.
- Kiểm tra field bắt buộc, kiểu dữ liệu, giới hạn số và quy tắc domain.
- Từ chối event type hoặc schema version không được hỗ trợ.
- Ghi nhận lỗi với event ID và version để điều tra.
- Không chuyển payload lỗi thành object rỗng hoặc trạng thái mặc định có thể tạo side effect sai.

Validation nên tách hai lớp: validation cấu trúc/schema và validation nghiệp vụ. Payload đúng schema vẫn có thể chứa số tiền âm hoặc trạng thái không hợp lệ; ngược lại, schema mới có thể hợp lệ nhưng consumer cũ chưa hiểu được.

## 11. Upcaster và lớp chuyển đổi schema cũ

Khi consumer hiện tại cần đọc message cũ, có thể dùng upcaster hoặc mapper chuyển schema lịch sử sang mô hình nội bộ hiện tại. Upcaster không sửa event gốc; nó tạo biểu diễn tương thích trong lúc đọc.

Ví dụ ý tưởng:

```java
OrderCompleted mapV1ToCurrent(OrderCompletedV1 oldEvent) {
    return new OrderCompleted(
        oldEvent.eventId(),
        oldEvent.orderId(),
        oldEvent.completedAt(),
        oldEvent.totalAmountMinor(),
        "VND"
    );
}
```

Default `VND` trong ví dụ chỉ đúng nếu hợp đồng v1 thực sự bảo đảm mọi đơn hàng dùng VND. Nếu không, upcaster cần lấy thông tin từ nguồn lịch sử đáng tin cậy hoặc giữ trạng thái currency chưa xác định; không suy đoán.

Với nhiều phiên bản, tổ chức chuỗi chuyển đổi có kiểm thử: v1 sang v2, v2 sang mô hình hiện tại. Giữ các fixture message cũ và xác nhận kết quả mapping. Tránh viết logic chuyển đổi rải rác trong nhiều listener; một lớp adapter/upcaster dùng chung giúp các consumer hiểu lịch sử nhất quán.

## 12. Schema registry và quy tắc compatibility

Nếu dùng Avro, Protobuf hoặc JSON Schema cùng schema registry, cấu hình compatibility mode phù hợp với chiến lược triển khai và replay. Các registry thường có chế độ tương thích theo chiều, toàn bộ lịch sử hoặc cả hai chiều; tên mode và chi tiết khác nhau theo sản phẩm.

Trước khi bật rule, xác định rõ:

- Registry đang so sánh schema mới với phiên bản gần nhất hay tất cả phiên bản đã đăng ký?
- Rule kiểm tra reader mới đọc writer cũ, writer mới được reader cũ đọc, hay cả hai?
- Field mới có default hợp lệ không?
- Enum có giá trị mới có được cho phép không?
- Consumer có thực sự dùng schema ID/version từ registry khi deserialize không?
- Có message lịch sử nào nằm ngoài phạm vi kiểm tra của registry không?

Schema registry kiểm tra tương thích cấu trúc theo rule được cấu hình; nó không chứng minh semantics nghiệp vụ đúng hoặc mọi consumer tự động nâng cấp. Vẫn cần contract test với producer/consumer thực tế và fixture lịch sử.

## 13. Chiến lược triển khai producer và consumer

Với thay đổi có thể tương thích, triển khai theo thứ tự giúp tránh khoảng thời gian hai phía không hiểu nhau:

1. **Chuẩn bị consumer:** triển khai reader mới có thể đọc cả schema cũ và schema mới; vẫn xử lý message cũ đúng.
2. **Xác nhận consumer:** theo dõi phiên bản đang chạy và kết quả contract test.
3. **Nâng producer:** bắt đầu phát field hoặc schema mới khi mọi consumer bắt buộc đã hỗ trợ.
4. **Quan sát:** theo dõi lỗi deserialize, unknown field/type, retry và dead-letter.
5. **Ngừng hỗ trợ cũ:** chỉ sau khi hết consumer cũ, message cũ và thời hạn replay đã được xác định.

Với thay đổi không thể tương thích, phát event type hoặc schema version mới, duy trì consumer cho cả hai phiên bản trong giai đoạn chuyển tiếp. Có thể dual-publish có kiểm soát hoặc dùng adapter chuyển đổi, nhưng phải có event ID và quy tắc chống xử lý trùng để hai luồng không tạo side effect hai lần.

Rollback cũng cần được lên kế hoạch. Nếu producer mới đã phát schema mới, rollback ứng dụng producer về phiên bản cũ không xóa message mới đã nằm trong broker. Consumer cũ sau rollback vẫn phải có khả năng đọc chúng hoặc cần giữ consumer tương thích độc lập.

## 14. Replay, retention và Event Publication Registry

Tương thích lùi đặc biệt quan trọng khi replay. Consumer mới có thể phải đọc event từ broker retention, archive hoặc event store được tạo bởi nhiều phiên bản producer. Trước khi bỏ một schema cũ, xác định message cũ còn ở đâu và trong bao lâu.

Spring Modulith Event Publication Registry theo dõi publication cần giao đến transactional listener hoặc externalization target. Registry hỗ trợ nhận diện publication chưa hoàn tất và resubmit theo cơ chế ứng dụng. Nó không tự động là kho event lịch sử vô thời hạn và không thay thế schema archive. Nếu publication cũ còn tồn tại, listener mới vẫn cần đọc được payload tương ứng hoặc có lớp chuyển đổi.

Khi nâng cấp event class, không đổi nghĩa event đã phát trong quá khứ. Event là sự thật tại thời điểm xảy ra; nếu nghiệp vụ cần điều chỉnh, phát event bù trừ hoặc correction event mới thay vì sửa lịch sử một cách âm thầm.

## 15. Kiểm thử tương thích lùi

Kiểm thử nên bao phủ cả chiều phiên bản và dữ liệu lịch sử:

1. **Consumer mới đọc payload cũ:** dùng fixture v1 và xác nhận mapping sang mô hình hiện tại.
2. **Consumer cũ đọc payload mới:** xác nhận field mới được bỏ qua hoặc xử lý theo đúng khả năng của reader cũ.
3. **Field tùy chọn:** kiểm tra absent, null và default có semantics rõ ràng.
4. **Enum mới:** kiểm tra unknown value không gây lỗi ngoài dự kiến hoặc side effect sai.
5. **Thay đổi kiểu:** kiểm tra giới hạn số, timestamp, currency và định dạng.
6. **Schema version:** xác nhận version thiếu, version cũ, version hiện tại và version không hỗ trợ.
7. **Polymorphic type:** kiểm tra discriminator cũ/new type và allow-list subtype.
8. **Replay:** đọc fixture lịch sử hoặc message đã archive bằng consumer mới.
9. **Producer/consumer rollout:** kiểm tra ma trận phiên bản được hỗ trợ trong giai đoạn deploy overlap.
10. **Publication retry:** publication cũ được resubmit vẫn giữ event ID và được listener mới xử lý idempotent.

Giữ fixture payload dưới dạng file hoặc test resource có tên version rõ ràng, chẳng hạn `order-completed-v1.json`. Không chỉ serialize rồi deserialize bằng cùng một phiên bản class trong một test; test đó có thể xanh dù producer và consumer không tương thích với nhau.

## 16. Những thay đổi thường phá vỡ tương thích

| Thay đổi | Rủi ro | Hướng xử lý |
|---|---|---|
| Xóa field đang dùng | Consumer cũ thiếu dữ liệu | Deprecate, dual-field và giai đoạn chuyển tiếp |
| Đổi tên field | Reader cũ không tìm thấy field | Thêm field mới, giữ alias/field cũ trong thời gian hỗ trợ |
| Thêm field bắt buộc không có default | Consumer mới không đọc message cũ | Cho phép absent hoặc upcast có quy tắc rõ |
| Đổi kiểu dữ liệu | Deserialize lỗi hoặc tràn/diễn giải sai | Field/version mới và chuyển đổi tường minh |
| Thêm enum value | Consumer cũ có thể từ chối | Unknown-value policy hoặc event version mới |
| Đổi ý nghĩa field | Deserialize thành công nhưng sai nghiệp vụ | Định nghĩa hợp đồng mới, không tái sử dụng semantics cũ |
| Bỏ event type cũ | Replay hoặc publication cũ thất bại | Duy trì reader cũ đến hết retention/replay window |

## 17. Những điểm cần nhớ

- Xác định rõ consumer mới đọc message cũ và consumer cũ đọc message mới; hai chiều có thể khác nhau.
- Thêm field tùy chọn thường dễ tương thích hơn xóa, đổi tên hoặc đổi kiểu field.
- Phân biệt absent, null và default; chỉ dùng default khi semantics được bảo đảm.
- Thay đổi ý nghĩa nghiệp vụ là thay đổi hợp đồng ngay cả khi JSON schema không đổi.
- Dùng event/schema version, tolerant reader có validation và upcaster khi cần đọc lịch sử.
- Triển khai consumer tương thích trước khi producer phát schema mới; giữ reader cũ trong thời hạn replay.
- Schema registry hỗ trợ kiểm tra cấu trúc theo rule, không thay thế contract test và kiểm tra semantics.
- Event Publication Registry theo dõi publication, không phải kho event lịch sử vô hạn.

Khi event contract được tiến hóa theo ma trận producer/consumer rõ ràng, consumer có default và upcaster có kiểm soát, còn rollout giữ tương thích trong giai đoạn chuyển tiếp, các module Spring Modulith có thể nâng cấp độc lập mà không làm hỏng message đang lưu hoặc consumer chưa được triển khai. Đây là nền tảng để event versioning duy trì được độ tin cậy qua nhiều phiên bản ứng dụng.
