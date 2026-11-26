# Kiểu dữ liệu trong payload

Payload là phần dữ liệu mà consumer nhận được khi một application event được serialize qua ranh giới ứng dụng. Khi event chỉ chạy trong cùng một tiến trình Java, producer và listener có thể cùng nhìn thấy một object. Khi event được lưu, chuyển qua broker hoặc đọc bởi một ứng dụng viết bằng ngôn ngữ khác, hai phía chỉ còn chia sẻ một hợp đồng dữ liệu đã được serialize.

Vì vậy, kiểu dữ liệu trong payload cần được chọn theo ý nghĩa nghiệp vụ, khả năng biểu diễn trên wire format và thời gian tồn tại của hợp đồng. Một kiểu Java tiện dùng trong domain model chưa chắc là kiểu phù hợp để công bố ra ngoài. Payload tốt phải dễ đọc, không phụ thuộc cấu trúc nội bộ của producer, giữ được độ chính xác và có thể tiến hóa mà không làm consumer hiện tại xử lý sai.

Trong Spring Modulith, event được đánh dấu để externalize sẽ đi qua integration và cơ chế chuyển đổi dữ liệu của ứng dụng. Target identifier xác định hướng định tuyến; serializer và cấu hình transport quyết định cách biểu diễn payload trên wire. Không nên giả định mọi adapter hoặc mọi hệ thống nhận đều dùng cùng một mặc định serialization.

## 1. Chọn kiểu theo hợp đồng, không theo entity nội bộ

Một event contract mô tả sự kiện nghiệp vụ đã xảy ra. Payload chỉ nên chứa dữ liệu cần để consumer hiểu sự kiện và thực hiện trách nhiệm của mình.

Ví dụ, khi đơn hàng được thanh toán, consumer có thể cần mã event, mã đơn hàng, số tiền, loại tiền và thời điểm thanh toán. Consumer không cần nhận toàn bộ entity Order, các quan hệ JPA, lazy proxy, trạng thái persistence hoặc những trường chỉ phục vụ giao diện nội bộ.

| Nhu cầu dữ liệu | Kiểu wire thường phù hợp | Ví dụ |
|---|---|---|
| Định danh duy nhất | Chuỗi có định dạng được công bố | UUID |
| Số lượng đếm được | Số nguyên có giới hạn rõ ràng | itemCount |
| Tiền hoặc giá trị thập phân chính xác | Chuỗi thập phân theo quy ước hoặc decimal của định dạng có hỗ trợ | total = "125000.50" |
| Thời điểm tuyệt đối | Chuỗi ISO-8601/RFC 3339 có múi giờ hoặc UTC | occurredAt |
| Ngày nghiệp vụ | Chuỗi ngày YYYY-MM-DD | deliveryDate |
| Giá trị phân loại | Chuỗi mã ổn định | paymentMethod |
| Danh sách có thứ tự | Mảng | items |
| Dữ liệu nhị phân nhỏ | Base64 hoặc định dạng nhị phân được thống nhất | documentDigest |
| Tập thuộc tính có schema cố định | Object với tên trường rõ ràng | address |

Tên trường, kiểu dữ liệu, đơn vị đo, miền giá trị và ý nghĩa của từng trường cần được mô tả trong contract. Chỉ ghi rằng total là number là chưa đủ: consumer còn cần biết số tiền tính theo đơn vị nào, có bao gồm thuế không và được làm tròn theo quy tắc nào.

Một payload ví dụ:

~~~json
{
  "eventId": "7d6b0d85-8a2e-4d2c-9c2d-2c4b7b1a9120",
  "eventType": "orders.order-paid",
  "schemaVersion": 1,
  "occurredAt": "2026-11-25T10:15:30Z",
  "payload": {
    "orderId": "ORD-2026-00421",
    "total": "125000.50",
    "currency": "VND",
    "paymentMethod": "BANK_TRANSFER",
    "itemCount": 2
  }
}
~~~

Đây là một quy ước JSON minh họa. Tổ chức có thể dùng envelope, metadata và serializer khác, nhưng cần công bố rõ ràng để mọi consumer hiểu cùng một cách.

## 2. Số nguyên và số thập phân

Số nguyên phù hợp với số lần, số lượng, mã thứ tự hoặc giá trị đếm có giới hạn. Hãy xác định miền giá trị trước khi chọn kiểu như int32 hay int64. Consumer ở JavaScript thường biểu diễn number bằng IEEE-754 double và chỉ bảo đảm chính xác mọi số nguyên đến 2^53 - 1. Một số long lớn hơn giới hạn đó có thể bị làm tròn khi đi qua consumer JavaScript.

Nếu giá trị có thể vượt giới hạn an toàn của consumer, hãy serialize thành chuỗi số nguyên với quy tắc parse được công bố, hoặc dùng định dạng có hỗ trợ integer 64-bit rõ ràng. Không nên chuyển mọi số thành chuỗi một cách tùy tiện vì điều đó làm mất khả năng kiểm tra schema và tính toán tự nhiên ở consumer.

### Tiền và decimal

Trong Java, BigDecimal thường là lựa chọn phù hợp cho phép tính tiền vì nó giữ được giá trị thập phân theo độ chính xác được khai báo. Tuy nhiên, JSON không có kiểu decimal chính xác được bảo đảm cho mọi ngôn ngữ. Một JSON number như 125000.50 có thể bị consumer chuyển sang số dấu phẩy động nhị phân.

Nếu tính chính xác tài chính là bắt buộc và consumer có thể dùng ngôn ngữ hoặc thư viện khác nhau, biểu diễn decimal dưới dạng chuỗi thường an toàn hơn:

~~~json
{
  "total": "125000.50",
  "currency": "VND"
}
~~~

Contract cần quy định chuỗi decimal dùng dấu chấm làm dấu phân cách thập phân, không có dấu phân tách hàng nghìn, cách biểu diễn số âm, scale được phép và cách xử lý số 0 ở cuối. Consumer chuyển chuỗi thành decimal hoặc kiểu tiền chính xác tương ứng trước khi tính toán.

Nếu tổ chức chọn JSON number, cần quy định rõ giới hạn precision, scale và yêu cầu thư viện consumer không chuyển giá trị sang floating point thiếu chính xác. Không dùng float hoặc double cho số tiền chỉ vì chúng serialize thuận tiện.

Cũng cần phân biệt giá trị tiền và số lượng. Đơn giá, thuế, tỷ giá và tổng tiền có thể có scale khác nhau. Đừng mặc định mọi decimal đều có hai chữ số thập phân.

## 3. Ngày, giờ và múi giờ

Thời gian là nguồn lỗi phổ biến khi event đi qua nhiều hệ thống và khu vực địa lý. Payload cần phân biệt thời điểm tuyệt đối với ngày hoặc giờ địa phương.

| Ý nghĩa | Kiểu Java gợi ý | Biểu diễn ví dụ |
|---|---|---|
| Thời điểm một sự kiện thực sự xảy ra | Instant | 2026-11-25T10:15:30Z |
| Ngày sinh, ngày giao hàng, ngày kế toán | LocalDate | 2026-11-25 |
| Thời gian địa phương không gắn múi giờ | LocalDateTime | 2026-11-25T17:15:30 |
| Thời điểm có offset cụ thể | OffsetDateTime | 2026-11-25T17:15:30+07:00 |
| Lịch theo vùng địa lý | LocalDateTime kèm ZoneId | 2026-11-25T17:15:30 và Asia/Ho_Chi_Minh |

Với event mô tả một điều đã xảy ra, Instant thường phù hợp vì nó biểu diễn một thời điểm tuyệt đối. Serialize thành chuỗi ISO-8601 ở UTC với hậu tố Z. Consumer có thể chuyển đổi sang múi giờ hiển thị riêng.

LocalDate phù hợp khi nghiệp vụ chỉ quan tâm ngày lịch, chẳng hạn ngày đáo hạn hoặc ngày giao hàng. Không biến ngày lịch thành Instant lúc nửa đêm UTC vì có thể làm thay đổi ngày khi consumer hiển thị ở múi giờ khác.

LocalDateTime không chứa offset hoặc zone. Nếu dùng nó cho một lịch hẹn hoặc thời điểm cần thực thi trong tương lai, hãy gửi thêm ZoneId như Asia/Ho_Chi_Minh. Nếu chỉ gửi 2026-11-25T17:15:30, consumer ở nơi khác không thể biết đó là giờ của vùng nào.

Không dùng timestamp dạng số nếu contract không chỉ rõ đơn vị. Giá trị 1795601730 có thể là epoch seconds, trong khi 1795601730000 có thể là epoch milliseconds. Chuỗi ISO-8601 giúp người đọc và công cụ kiểm tra dễ hiểu hơn, nhưng producer và consumer vẫn phải thống nhất độ chính xác, timezone và cách xử lý leap second theo chuẩn hệ thống chọn.

## 4. UUID, mã nghiệp vụ và kiểu định danh

UUID nên được serialize thành chuỗi chuẩn, ví dụ 7d6b0d85-8a2e-4d2c-9c2d-2c4b7b1a9120. Không gửi object UUID nội bộ hoặc phụ thuộc cách một thư viện Java cụ thể ghi object đó.

Mã nghiệp vụ như order number, invoice number hoặc customer code nên là chuỗi nếu nó có thể chứa chữ, số 0 ở đầu, dấu phân cách hoặc quy tắc định dạng. Không biến mã ORD-00042 thành số 42 rồi làm mất số 0 đầu.

Đừng nhầm định danh với số đo. orderId là định danh; itemCount là số lượng. Định danh không nên được cộng, trừ hoặc so sánh theo thứ tự số học chỉ vì hiện tại nó trông giống số.

Một event thường cần hai loại định danh:

- Event ID nhận diện một lần xảy ra trong miền nghiệp vụ và được giữ nguyên khi phát lại.
- Business ID nhận diện thực thể liên quan, chẳng hạn orderId hoặc paymentId.

Consumer có thể dùng event ID để chống xử lý trùng và business ID để tìm hoặc cập nhật dữ liệu tương ứng. Không tạo event ID mới mỗi lần retry vì điều đó khiến consumer không nhận ra bản giao lặp.

## 5. Enum và giá trị phân loại

Enum trong Java thường tiện cho domain model, nhưng không nên serialize ordinal. Ordinal phụ thuộc vị trí khai báo. Khi thêm một giá trị vào giữa enum, consumer cũ có thể hiểu sai số nguyên đã nhận.

Ví dụ không nên gửi:

~~~json
{
  "paymentMethod": 2
}
~~~

Hãy gửi mã chuỗi có ý nghĩa và ổn định:

~~~json
{
  "paymentMethod": "BANK_TRANSFER"
}
~~~

Tên enum cũng là một phần của contract nếu được gửi trực tiếp. Đổi tên BANK_TRANSFER thành BANK sẽ có thể phá vỡ consumer. Nếu cần tên hiển thị khác nhau, tách code ổn định khỏi label dành cho giao diện.

Khi consumer gặp một enum code chưa biết, cách xử lý phải được định nghĩa. Với trường chỉ mang tính mô tả, consumer có thể lưu giá trị chưa biết hoặc dùng nhánh UNKNOWN. Với trường điều khiển nghiệp vụ, consumer nên từ chối có kiểm soát và đưa message vào quy trình xử lý lỗi thay vì âm thầm chọn một hành vi mặc định nguy hiểm.

Nếu có nhiều hệ thống cùng chia sẻ danh mục mã, cần có tài liệu mã hợp lệ, ý nghĩa, thời điểm bắt đầu/ngừng dùng và quy tắc tương thích.

## 6. Boolean, null và trường không xuất hiện

Boolean nên biểu diễn một câu hỏi có đúng hai trạng thái rõ ràng. Nếu nghiệp vụ có ba trạng thái như đã duyệt, bị từ chối và chưa quyết định, đừng nén chúng thành một boolean rồi diễn giải null theo cách riêng ở mỗi consumer.

Cần phân biệt:

| Cách biểu diễn | Ý nghĩa có thể có | Cần quy định |
|---|---|---|
| Trường có giá trị false | Đã xác định là sai | Không được hiểu là thiếu dữ liệu |
| Trường có giá trị null | Giá trị không có hoặc chưa biết | Quy định null có hợp lệ không |
| Trường bị bỏ qua | Producer không gửi trường | Consumer có dùng default hay giữ trạng thái cũ |
| Trường rỗng | Chuỗi hoặc collection có mặt nhưng không có phần tử | Phân biệt với null và không xuất hiện |

Trong event bất biến như OrderPaid, trường bị thiếu thường là lỗi contract nếu trường đó bắt buộc. Trong event cập nhật một phần, trường bị bỏ qua có thể có nghĩa là không thay đổi. Hai trường hợp cần schema và ngữ nghĩa riêng.

Java Optional hữu ích ở một số API nội bộ nhưng thường không phải kiểu wire cần công bố. Hãy biểu diễn rõ field nullable, field tùy chọn hoặc một cấu trúc có discriminator. Đừng để từng serializer tự quyết định Optional.empty() trở thành null, mảng rỗng hay field bị bỏ qua.

Với dữ liệu cập nhật, cân nhắc dùng operation rõ ràng như SET, CLEAR hoặc UNCHANGED nếu consumer phải phân biệt ba hành vi này. Không dùng null để gánh nhiều ý nghĩa.

## 7. Collection, map và object lồng nhau

List được serialize thành mảng và giữ thứ tự. Dùng List khi thứ tự phần tử có ý nghĩa, chẳng hạn các dòng hàng hoặc các bước trong quy trình. Set thường không bảo đảm thứ tự; nếu consumer cần thứ tự ổn định, hãy chuyển thành List và quy định tiêu chí sắp xếp trước khi serialize.

Map phù hợp với tập thuộc tính động có khóa chuỗi, nhưng không nên dùng Map<String, Object> làm payload chính của event nghiệp vụ. Kiểu Object khiến schema yếu, consumer phải đoán kiểu lúc runtime và lỗi chỉ xuất hiện khi dữ liệu thật được xử lý.

Với tập trường cố định, dùng object hoặc DTO có schema rõ ràng:

~~~json
{
  "shippingAddress": {
    "recipient": "Nguyen Van A",
    "provinceCode": "79",
    "districtCode": "001",
    "addressLine": "12 Example Street"
  }
}
~~~

Object lồng nhau nên có giới hạn độ sâu và trách nhiệm rõ ràng. Không serialize toàn bộ object graph của entity vì có thể chứa vòng tham chiếu, lazy proxy, quan hệ không cần thiết hoặc dữ liệu riêng tư.

Đối với collection lớn, hãy xem lại ranh giới event. Một event thường nên thông báo sự kiện và mang đủ dữ liệu cần thiết để consumer xử lý. Nếu payload chứa hàng trăm nghìn bản ghi hoặc file lớn, cân nhắc chia thành các event theo lô hoặc lưu tài liệu ở object storage rồi gửi một tham chiếu có kiểm soát truy cập.

## 8. Kiểu nhị phân và dữ liệu đặc biệt

JSON không có kiểu byte array riêng. Một byte[] thường được biểu diễn dưới dạng Base64. Cách này thuận tiện cho dữ liệu nhị phân nhỏ, nhưng làm payload lớn hơn và khó đọc hơn.

Không nhúng file lớn, ảnh, PDF hoặc nội dung nhị phân dung lượng cao vào event nếu broker có giới hạn kích thước message. Thay vào đó, lưu nội dung ở object storage và gửi object key, checksum, media type, kích thước cùng thông tin tham chiếu cần thiết. Consumer cần xác thực quyền truy cập và thời hạn của tham chiếu.

Với dữ liệu đặc biệt như địa chỉ, đơn vị đo, tọa độ hoặc tỷ giá, hãy công bố cả giá trị và ngữ nghĩa:

- Số đo cần đơn vị, chẳng hạn millisecond, kilogram hoặc meter.
- Tỷ giá cần xác định chiều quy đổi và thời điểm áp dụng.
- Tọa độ cần quy ước thứ tự longitude/latitude và hệ tọa độ.
- Ngôn ngữ cần mã locale rõ ràng như vi-VN hoặc en-US.
- Giá trị phần trăm cần nói rõ là 0.15 hay 15.

Không dựa vào tên trường để consumer tự suy đoán đơn vị.

## 9. DTO và cách serialize bằng Java

Event payload nên dùng DTO bất biến, thường có thể dùng Java record. DTO là hợp đồng dành cho consumer; domain entity vẫn thuộc quyền sở hữu của module phát event.

Ví dụ:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderPaidPayload(
    UUID eventId,
    String orderNumber,
    BigDecimal total,
    String currency,
    Instant occurredAt,
    PaymentMethodCode paymentMethod
) {}

public enum PaymentMethodCode {
    BANK_TRANSFER,
    CARD,
    CASH
}
~~~

Nếu JSON là wire format, hãy công bố quy tắc serialize BigDecimal và enum như đã nêu ở trên. Với yêu cầu chính xác tài chính đa ngôn ngữ, DTO có thể dùng String cho total và validate chuỗi decimal ở ranh giới producer/consumer. Ví dụ:

~~~java
public record OrderPaidPayload(
    UUID eventId,
    String orderNumber,
    String total,
    String currency,
    Instant occurredAt,
    String paymentMethod
) {}
~~~

Producer nên chuyển domain model sang DTO tường minh:

~~~java
OrderPaidPayload toPayload(Order order, Payment payment) {
    return new OrderPaidPayload(
        payment.eventId(),
        order.getOrderNumber(),
        payment.amount().toPlainString(),
        payment.currency(),
        payment.confirmedAt(),
        payment.method().externalCode()
    );
}
~~~

Cách mapping này tạo một điểm kiểm soát để bỏ trường nội bộ, chuẩn hóa thời gian, tiền tệ và mã enum. Không serialize trực tiếp entity chỉ vì Jackson có thể truy cập getter của entity đó.

Nếu dùng Jackson, cần thống nhất module cho Java Time, cách ghi ngày giờ, naming strategy, xử lý null, enum và unknown fields. Spring Boot có thể cung cấp cấu hình ObjectMapper được quản lý; hãy kiểm tra mapper thực sự mà externalization adapter sử dụng. Một ObjectMapper tự tạo trong test có thể cho kết quả khác mapper ở runtime.

Không dựa vào thứ tự property trong JSON. Consumer phải đọc theo tên trường. Nếu dùng Avro, Protobuf hoặc định dạng schema-based khác, hãy công bố schema và quy trình quản lý version tương ứng thay vì áp dụng giả định riêng của JSON.

## 10. Tránh Java native serialization và metadata class

Java native serialization gắn payload với cơ chế biểu diễn object của Java và thường tạo phụ thuộc chặt giữa phiên bản class ở producer và consumer. Nó cũng không phù hợp cho consumer viết bằng ngôn ngữ khác và có rủi ro bảo mật khi deserialize dữ liệu không đáng tin cậy.

Không gửi tên class Java hoặc metadata kiểu để consumer tự khởi tạo class tùy ý. Với payload đa hình, dùng discriminator do contract định nghĩa:

~~~json
{
  "notificationType": "EMAIL",
  "recipient": "user@example.test",
  "templateCode": "ORDER_PAID"
}
~~~

Consumer kiểm tra notificationType theo danh sách loại được hỗ trợ và xử lý rõ trường hợp không biết loại. Không bật cơ chế polymorphic deserialization rộng cho dữ liệu từ broker nếu không có allowlist và kiểm soát phù hợp.

Serialization cần có giới hạn kích thước, giới hạn độ sâu và kiểm tra dữ liệu đầu vào. Không coi payload đã deserialize là đáng tin cậy chỉ vì message đến từ broker nội bộ. Consumer vẫn cần validate trường bắt buộc, miền giá trị, định dạng, quyền và các invariant nghiệp vụ.

## 11. Tiến hóa schema và tương thích consumer

Event có thể tồn tại trong broker, dead-letter queue, bản sao lưu hoặc hệ thống replay lâu hơn vòng đời của một phiên bản ứng dụng. Vì thế, schema phải được thiết kế cho việc đọc dữ liệu cũ.

Một số nguyên tắc thường hữu ích:

- Thêm trường mới dưới dạng optional hoặc có default được công bố, để consumer cũ có thể bỏ qua.
- Không đổi kiểu dữ liệu hoặc ý nghĩa của trường hiện tại trong cùng schema version nếu thay đổi đó phá vỡ tương thích.
- Không tái sử dụng tên trường cũ cho ý nghĩa mới.
- Khi loại bỏ trường, công bố giai đoạn deprecation và kiểm tra consumer còn sử dụng hay không.
- Giữ event type và event ID ổn định qua retry.
- Có quy tắc chuyển đổi hoặc hỗ trợ đọc schema cũ khi replay message tồn đọng.

Ví dụ, phiên bản đầu chỉ có mã đơn và tổng tiền:

~~~json
{
  "schemaVersion": 1,
  "orderId": "ORD-42",
  "total": "125000.50"
}
~~~

Phiên bản sau có thể bổ sung currency nếu consumer cũ có thể bỏ qua trường mới:

~~~json
{
  "schemaVersion": 2,
  "orderId": "ORD-42",
  "total": "125000.50",
  "currency": "VND"
}
~~~

Nếu consumer cũ cần biết currency để diễn giải total một cách chính xác, currency thực tế là trường bắt buộc về mặt nghiệp vụ. Trong trường hợp đó, không thể chỉ dựa vào khả năng bỏ qua field của parser; cần triển khai consumer tương thích trước, phát schema mới sau hoặc công bố event type/version mới.

Schema registry hoặc contract test có thể giúp kiểm tra tương thích trước khi triển khai. Nhưng công cụ không thay thế quyết định nghiệp vụ về ý nghĩa trường và thời gian hỗ trợ dữ liệu cũ.

## 12. Kiểm thử serialization ở ranh giới

Unit test cho mapper giúp kiểm tra mapping domain sang DTO. Tuy nhiên, cần có kiểm thử serialization thực tế bằng cùng serializer, cấu hình và wire format mà integration dùng trong môi trường chạy.

Các trường hợp nên kiểm tra:

- UUID được ghi và đọc lại đúng định dạng.
- Instant giữ đúng thời điểm và timezone quy ước.
- LocalDate không bị đổi ngày khi đi qua múi giờ khác.
- Decimal giữ nguyên precision và scale theo contract.
- Enum được ghi bằng mã ổn định, không phải ordinal.
- Null, field bị bỏ qua và collection rỗng có ngữ nghĩa rõ.
- Consumer đọc được field mới có thể bỏ qua.
- Payload cũ vẫn đọc được trong thời gian hỗ trợ schema.
- Dữ liệu thiếu hoặc sai định dạng bị từ chối có kiểm soát.
- Payload quá lớn hoặc quá sâu bị chặn theo giới hạn đã đặt.

Một ví dụ kiểm thử JSON bằng Jackson có thể kiểm tra round-trip của DTO:

~~~java
@Test
void serializesEventPayloadWithStableValues() throws Exception {
    var payload = new OrderPaidPayload(
        UUID.fromString("7d6b0d85-8a2e-4d2c-9c2d-2c4b7b1a9120"),
        "ORD-42",
        new BigDecimal("125000.50"),
        "VND",
        Instant.parse("2026-11-25T10:15:30Z"),
        PaymentMethodCode.BANK_TRANSFER
    );

    String json = objectMapper.writeValueAsString(payload);
    OrderPaidPayload restored =
        objectMapper.readValue(json, OrderPaidPayload.class);

    assertThat(restored.eventId()).isEqualTo(payload.eventId());
    assertThat(restored.total()).isEqualByComparingTo(payload.total());
    assertThat(restored.occurredAt()).isEqualTo(payload.occurredAt());
}
~~~

Test này kiểm tra round-trip trong một cấu hình Java. Nó chưa chứng minh consumer ở ngôn ngữ khác đọc cùng payload đúng. Với contract dùng chung, nên lưu các payload mẫu và kiểm thử chúng bằng parser hoặc contract test của từng consumer.

## 13. Lỗi thường gặp khi chọn kiểu payload

**Serialize trực tiếp JPA entity.** Payload có thể chứa quan hệ không cần thiết, proxy, vòng tham chiếu và chi tiết persistence. Hãy map sang DTO riêng.

**Dùng double cho tiền.** Một số decimal không thể biểu diễn chính xác bằng floating point nhị phân. Hãy chọn decimal chính xác hoặc chuỗi decimal có quy tắc.

**Gửi timestamp không kèm đơn vị hoặc timezone.** Consumer có thể hiểu seconds thành milliseconds hoặc diễn giải thời gian theo múi giờ khác. Hãy dùng Instant dạng ISO-8601 hoặc ghi rõ đơn vị và timezone.

**Gửi ordinal của enum.** Thêm hoặc sắp xếp lại enum có thể làm thay đổi ý nghĩa số đã gửi. Hãy dùng code chuỗi ổn định.

**Dùng Map<String, Object> cho mọi event.** Contract trở nên mơ hồ và lỗi kiểu chỉ xuất hiện lúc runtime. Hãy định nghĩa DTO và schema có trường rõ ràng.

**Đồng nhất null với field bị thiếu.** Consumer có thể hiểu nhầm giữa chưa biết, xóa giá trị và không cập nhật. Hãy quy định riêng từng trạng thái.

**Đổi tên hoặc tái sử dụng field mà không versioning.** Consumer cũ có thể parse thành công nhưng hiểu sai nghiệp vụ. Hãy quản lý schema và thời gian chuyển đổi.

**Cho phép deserialize class tùy ý.** Điều này tạo rủi ro bảo mật và gắn chặt payload với Java. Hãy dùng wire format và discriminator nằm trong contract.

## Kết luận

Kiểu dữ liệu trong payload là một phần của hợp đồng tích hợp. UUID, mã nghiệp vụ, thời gian, decimal, enum, collection và giá trị nullable cần có biểu diễn ổn định, đơn vị và ngữ nghĩa được công bố. DTO bất biến giúp tách contract khỏi entity nội bộ; serializer và cấu hình transport phải được kiểm thử đúng tại ranh giới ứng dụng.

Khi chọn kiểu dữ liệu theo nhu cầu nghiệp vụ và khả năng của consumer, event có thể được đọc chính xác qua nhiều ngôn ngữ, phiên bản và hệ thống messaging. Việc quản lý schema, idempotency và payload mẫu giúp consumer tiếp tục xử lý an toàn khi event được lưu lâu hoặc phát lại sau này.

