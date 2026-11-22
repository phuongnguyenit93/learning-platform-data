# Phân biệt Event Sourcing với Domain Event và nhật ký kiểm toán

Trong Domain-Driven Design (DDD), **Domain Event**, **Event Sourcing** và **Audit Log** đều có thể ghi lại điều đã xảy ra, nhưng chúng giải quyết những bài toán khác nhau. Domain Event mô tả một sự thật có ý nghĩa nghiệp vụ; Event Sourcing là cách lưu trạng thái của một đối tượng bằng chuỗi sự kiện bất biến; Audit Log ghi dấu vết hoạt động để trả lời ai đã làm gì, khi nào, từ đâu và kết quả ra sao.

Một ứng dụng có thể phát Domain Event mà vẫn lưu trạng thái hiện tại bằng các bản ghi CRUD thông thường. Một ứng dụng dùng Event Sourcing có thể dùng các sự kiện nghiệp vụ để dựng lại Aggregate, nhưng vẫn cần Audit Log riêng cho truy cập, thao tác quản trị và các lần bị từ chối. Không nên coi ba khái niệm là ba tên gọi cho cùng một cơ chế.

## 1. Ba khái niệm trả lời ba câu hỏi khác nhau

| Khái niệm | Câu hỏi chính | Vai trò |
| --- | --- | --- |
| Domain Event | Sự việc nghiệp vụ nào đã xảy ra? | Diễn đạt sự thật trong ngôn ngữ miền và có thể kích hoạt xử lý tiếp theo |
| Event Sourcing | Trạng thái hiện tại được hình thành từ những sự kiện nào? | Lưu chuỗi sự kiện làm nguồn dữ liệu chính để dựng lại trạng thái |
| Audit Log | Ai đã thực hiện hoặc cố thực hiện hành động gì, khi nào và với kết quả nào? | Truy vết, điều tra, kiểm soát và đáp ứng yêu cầu kiểm toán |

Ví dụ trong hệ thống đơn hàng:

- Domain Event: đơn hàng đã được xác nhận, một dòng hàng đã được thêm hoặc đơn đã bị hủy.
- Event Sourcing: lưu lần lượt các sự kiện làm thay đổi Aggregate Order để có thể dựng lại trạng thái của đơn tại một thời điểm.
- Audit Log: ghi người dùng nào đã yêu cầu hủy đơn, thao tác được thực hiện từ kênh nào, quyền nào được kiểm tra và yêu cầu được chấp nhận hay từ chối.

Một sự kiện nghiệp vụ có thể là đầu vào của Event Sourcing, nhưng không phải mọi Domain Event đều phải được lưu trong event store. Một Audit Log cũng có thể ghi một hành động liên quan đến Domain Event, nhưng nó có mục tiêu và cấu trúc khác.

## 2. Domain Event là sự thật nghiệp vụ đã xảy ra

Domain Event biểu diễn một sự việc có ý nghĩa trong một Bounded Context. Tên sự kiện thường diễn đạt điều đã xảy ra, chẳng hạn:

- OrderSubmitted
- OrderConfirmed
- PaymentAuthorized
- InventoryReserved
- ShipmentDispatched
- CustomerCreditLimitChanged

Event thường mang định danh đối tượng, dữ kiện nghiệp vụ cần thiết và thời điểm xảy ra. Nó có thể được phát ra trong hệ thống CRUD thông thường sau khi một thay đổi được commit thành công.

Ví dụ, một ứng dụng dùng JPA lưu Order vào bảng orders. Sau khi cập nhật thành công, ứng dụng có thể công bố OrderConfirmed để Fulfillment tạo yêu cầu chuẩn bị hàng. Ứng dụng đó đang dùng Domain Event và có thể dùng transactional outbox, nhưng chưa phải Event Sourcing nếu trạng thái Order vẫn được lưu trực tiếp như một bản ghi hiện tại và không được dựng lại từ event stream.

Domain Event giúp các phần của hệ thống phản ứng với sự thật nghiệp vụ mà không cần gọi trực tiếp lẫn nhau. Tuy nhiên, sự kiện được công bố không tự động trở thành nguồn dữ liệu chính thức để khôi phục toàn bộ Aggregate.

## 3. Event Sourcing là cách lưu trạng thái

Với cách lưu CRUD, ứng dụng thường ghi trạng thái mới vào bản ghi:

~~~text
orders
------------------------------------------------
order_id | status     | total_amount | version
O-1001   | CONFIRMED  | 1250000      | 4
~~~

Sau khi cập nhật, giá trị cũ của status hoặc total_amount có thể bị ghi đè, trừ khi hệ thống lưu thêm lịch sử riêng.

Với Event Sourcing, hệ thống lưu các sự kiện làm thay đổi Aggregate theo thứ tự:

~~~text
Order stream: O-1001
------------------------------------------------
1  OrderCreated
2  OrderLineAdded
3  OrderLineQuantityChanged
4  OrderConfirmed
~~~

Trạng thái hiện tại được dựng bằng cách áp dụng lần lượt các sự kiện. Event stream là nguồn dữ liệu chính; bảng trạng thái hiện tại hoặc read model nếu có chỉ là projection có thể được tạo lại từ stream.

Điểm cốt lõi của Event Sourcing không phải là “có lưu event”, mà là **lưu các thay đổi trạng thái dưới dạng sự kiện và dùng chúng để tái dựng trạng thái**.

## 4. Event Sourcing không đồng nghĩa với việc phát Domain Event

Hai cách triển khai sau khác nhau:

**Ứng dụng CRUD có Domain Event**

1. Nạp Order từ bảng.
2. Gọi hành vi confirm.
3. Cập nhật bản ghi Order.
4. Lưu OrderConfirmed vào outbox hoặc công bố sau commit.
5. Consumer nhận event để xử lý tiếp.

**Ứng dụng Event Sourcing**

1. Nạp các sự kiện của stream Order.
2. Dựng Aggregate hiện tại bằng cách replay.
3. Gọi hành vi confirm.
4. Aggregate tạo sự kiện OrderConfirmed nếu hành động hợp lệ.
5. Append sự kiện vào stream với expected version.
6. Cập nhật projection hoặc công bố sự kiện cho consumer.

Ở ứng dụng CRUD, trạng thái bản ghi là nguồn dữ liệu chính. Ở ứng dụng Event Sourcing, event stream là nguồn dữ liệu chính và trạng thái hiện tại được suy ra từ stream.

Do đó:

- Có Domain Event không chứng minh hệ thống dùng Event Sourcing.
- Dùng Event Sourcing thường cần event có đủ thông tin để dựng lại trạng thái.
- Integration Event công bố ra ngoài có thể khác event nội bộ được lưu trong stream.
- Một hệ thống Event Sourcing vẫn có thể tạo read model, audit log và message tích hợp riêng.

## 5. Event Store lưu gì?

Event Store lưu các sự kiện thuộc stream của Aggregate hoặc một thực thể được quản lý theo lịch sử. Một event record thường cần:

| Trường | Ý nghĩa |
| --- | --- |
| stream_id / aggregate_id | Định danh stream hoặc Aggregate |
| stream_version | Vị trí hoặc version của event trong stream |
| event_id | Định danh duy nhất của event |
| event_type | Loại sự kiện |
| event_version | Phiên bản schema của loại event |
| payload | Dữ kiện cần để áp dụng sự kiện |
| occurred_at | Thời điểm nghiệp vụ xảy ra |
| recorded_at | Thời điểm event được ghi vào store |
| metadata | Correlation, causation, actor hoặc thông tin truy vết phù hợp |

Ví dụ cấu trúc logic:

~~~json
{
  "streamId": "order-O-1001",
  "streamVersion": 4,
  "eventId": "evt-8c91",
  "eventType": "OrderConfirmed",
  "eventVersion": 1,
  "occurredAt": "2026-11-18T03:00:00Z",
  "payload": {
    "orderId": "O-1001",
    "customerId": "C-72",
    "totalAmount": "1250000",
    "currency": "VND"
  },
  "metadata": {
    "correlationId": "cmd-31a0",
    "actorId": "user-42"
  }
}
~~~

Đây là dạng minh họa; event store cụ thể có thể tổ chức payload, metadata và index khác nhau. Không nên đưa mọi thông tin cá nhân hoặc dữ liệu nhạy cảm vào event chỉ vì thuận tiện cho replay.

## 6. Dựng lại Aggregate bằng event replay

Khi cần tải Order, ứng dụng lấy các event trong stream theo đúng thứ tự rồi áp dụng vào một Aggregate mới. Các hàm áp dụng sự kiện phải có kết quả xác định dựa trên event và trạng thái trước đó.

Ví dụ các event:

~~~java
public sealed interface OrderEvent
    permits OrderCreated, OrderLineAdded, OrderConfirmed {
}

public record OrderCreated(
    OrderId orderId,
    CustomerId customerId
) implements OrderEvent {}

public record OrderLineAdded(
    OrderLineId lineId,
    Sku sku,
    int quantity,
    Money unitPrice
) implements OrderEvent {}

public record OrderConfirmed(
    Instant occurredAt
) implements OrderEvent {}
~~~

Aggregate có thể áp dụng chúng như sau:

~~~java
public final class Order {
    private OrderId id;
    private CustomerId customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status;

    public static Order rehydrate(List<OrderEvent> history) {
        Order order = new Order();
        for (OrderEvent event : history) {
            order.apply(event);
        }
        return order;
    }

    private void apply(OrderEvent event) {
        switch (event) {
            case OrderCreated e -> {
                id = e.orderId();
                customerId = e.customerId();
                status = OrderStatus.DRAFT;
            }
            case OrderLineAdded e ->
                lines.add(new OrderLine(
                    e.lineId(), e.sku(), e.quantity(), e.unitPrice()
                ));
            case OrderConfirmed e ->
                status = OrderStatus.CONFIRMED;
        }
    }
}
~~~

Ví dụ dùng pattern matching trong switch, cần Java 21 trở lên. Đây là minh họa rút gọn: mã thật cần kiểm tra thứ tự, dữ liệu thiếu, event không được hỗ trợ và các bất biến khi dựng lại. Phương thức apply dùng cho replay thường chỉ áp dụng sự kiện đã được chấp nhận; nó không thay thế phương thức nghiệp vụ như confirm() vốn kiểm tra điều kiện và quyết định có tạo event hay không.

Quy trình ra quyết định thường có hai phần:

1. Hành vi nghiệp vụ kiểm tra trạng thái hiện tại và tạo các event mới nếu hợp lệ.
2. Hàm apply áp dụng event đã được tạo hoặc đã đọc từ store để cập nhật trạng thái trong bộ nhớ.

Tách hai trách nhiệm này giúp replay không vô tình chạy lại side effect như gửi email, gọi thanh toán hoặc đọc thời gian hệ thống.

## 7. Event stream có thứ tự và concurrency control

Các event trong cùng một stream cần một thứ tự xác định. Version tăng dần giúp xác định trạng thái nào đã được ghi và phát hiện hai command cùng sửa một Aggregate từ cùng một version.

Ví dụ:

| Transaction | Version đã đọc | Thao tác append | Kết quả |
| --- | ---: | --- | --- |
| A | 7 | Append OrderConfirmed với expected version 7 | Thành công, version mới 8 |
| B | 7 | Append OrderLineAdded với expected version 7 | Conflict vì stream đã ở version 8 |

Transaction B cần tải lại stream, dựng lại Aggregate và đánh giá command trên trạng thái mới. Không được append event dựa trên snapshot cũ chỉ để tránh conflict.

Expected version bảo vệ thứ tự trong một stream. Nó không tự tạo ra thứ tự toàn cục giữa các Aggregate khác nhau. Nếu quy trình phụ thuộc nhiều stream, cần correlation/causation metadata và cơ chế điều phối riêng.

## 8. Snapshot giúp tăng tốc, không thay thế event stream

Một Aggregate có hàng trăm nghìn event sẽ tốn thời gian replay nếu mỗi lần nạp đều đọc từ đầu. Snapshot lưu trạng thái đã dựng tại một version nhất định để giảm số event cần áp dụng.

Ví dụ:

~~~text
Stream version 1 ... 5000
          |
          v
Snapshot tại version 5000
          |
          v
Khi nạp lại: đọc snapshot + replay event 5001 ... version hiện tại
~~~

Snapshot là dữ liệu dẫn xuất. Event stream vẫn là nguồn lịch sử chính. Nếu snapshot bị hỏng hoặc không còn tương thích, hệ thống có thể tạo lại từ event stream, miễn là còn giữ được các event và logic chuyển đổi cần thiết.

Snapshot cần lưu version tương ứng và phiên bản cấu trúc. Không được áp dụng lại các event đã nằm trong snapshot vì sẽ làm trạng thái bị nhân đôi.

## 9. Domain Event, Event Sourced Event và Integration Event

Các thuật ngữ này có thể gần nhau nhưng nên phân biệt theo mục đích:

| Loại | Mục tiêu | Đặc điểm |
| --- | --- | --- |
| Domain Event | Diễn đạt sự thật có ý nghĩa trong mô hình miền | Dùng ngôn ngữ bounded context, có thể tồn tại trong hệ CRUD |
| Event Sourced Event | Lưu thay đổi cần thiết để tái dựng Aggregate | Là dữ liệu lịch sử chính của stream, cần replay được |
| Integration Event | Công bố thông tin cho context hoặc hệ thống khác | Là hợp đồng bên ngoài, cần ổn định và tương thích |

Một event như OrderConfirmed có thể vừa là Domain Event vừa là Event Sourced Event. Tuy nhiên, event store có thể cần dữ kiện nội bộ phục vụ replay mà consumer bên ngoài không nên biết. Adapter có thể chuyển nó thành Integration Event với payload nhỏ và ổn định hơn.

Không nên cho consumer truy cập trực tiếp event store nội bộ chỉ vì nó muốn nhận thông báo. Hãy công bố hợp đồng tích hợp qua broker/API và quản lý version riêng.

## 10. Audit Log ghi dấu vết ai, làm gì và kết quả ra sao

Audit Log tập trung vào khả năng truy vết và kiểm soát. Nó thường trả lời:

- Ai thực hiện hành động hoặc gửi yêu cầu?
- Hành động nào được yêu cầu?
- Đối tượng hoặc tài nguyên nào bị tác động?
- Hành động xảy ra lúc nào và từ kênh nào?
- Kết quả là thành công, bị từ chối hay thất bại?
- Quyền nào hoặc lý do nào liên quan đến quyết định?

Ví dụ một audit record:

~~~json
{
  "auditId": "aud-4102",
  "actorId": "employee-17",
  "action": "ORDER_CANCEL_REQUESTED",
  "resourceType": "Order",
  "resourceId": "O-1001",
  "occurredAt": "2026-11-18T03:05:00Z",
  "channel": "ADMIN_PORTAL",
  "outcome": "DENIED",
  "reasonCode": "ORDER_ALREADY_DISPATCHED",
  "correlationId": "req-91c2"
}
~~~

Audit Log có thể ghi cả hành động bị từ chối hoặc hành động chỉ đọc, trong khi Domain Event thường ghi nhận sự thật nghiệp vụ đã xảy ra. Ví dụ, người dùng cố truy cập hồ sơ khách hàng nhưng bị từ chối là một sự kiện audit quan trọng; nó không nhất thiết là Domain Event của Customer Management.

Audit Log cũng có thể ghi ai đã phê duyệt một thay đổi. Domain Event PriceAdjustmentApproved mô tả sự thật nghiệp vụ; audit record có thể ghi danh tính người phê duyệt, vai trò, phiên đăng nhập và kết quả kiểm tra quyền.

## 11. Event Store không tự động thay thế Audit Log

Event stream có thể chứa actorId hoặc correlationId, nhưng thường không ghi đầy đủ mọi hoạt động cần kiểm toán. Ví dụ:

- Một người dùng mở màn hình xem đơn hàng nhưng không làm thay đổi Aggregate.
- Một yêu cầu cập nhật bị từ chối trước khi tạo event.
- Một quản trị viên thay đổi quyền truy cập.
- Một truy vấn dữ liệu nhạy cảm được thực hiện.
- Một tiến trình hệ thống chạy thao tác bảo trì hoặc replay.

Những hoạt động này có thể cần audit record, dù không làm thay đổi trạng thái Aggregate.

Ngược lại, Event Sourcing cần lưu mọi thay đổi trạng thái có ý nghĩa đối với Aggregate, kể cả thay đổi do hệ thống tự động hoặc quy trình nền tạo ra. Audit Log có thể không đủ dữ kiện hoặc không có cấu trúc phù hợp để replay trạng thái.

Không nên lấy event store làm audit log duy nhất nếu yêu cầu kiểm toán cần theo dõi truy cập, hành động bị từ chối, danh tính actor hoặc thay đổi quyền. Cũng không nên dùng audit log như nguồn để dựng lại Aggregate nếu nó không được thiết kế cho mục tiêu đó.

## 12. So sánh Event Store và Audit Log

| Tiêu chí | Event Store | Audit Log |
| --- | --- | --- |
| Mục tiêu chính | Dựng lại trạng thái nghiệp vụ | Truy vết và kiểm toán hoạt động |
| Nội dung | Event biểu diễn thay đổi trạng thái | Actor, action, resource, outcome, reason và metadata |
| Đơn vị tổ chức | Stream theo Aggregate hoặc entity | Nhật ký theo actor, resource, thời gian hoặc phạm vi hệ thống |
| Thứ tự | Thứ tự trong stream là quan trọng | Thời điểm và chuỗi truy vết quan trọng; không nhất thiết tạo state stream |
| Replay | Có thể dựng lại Aggregate từ đầu | Thường không dùng để dựng Aggregate |
| Hành động bị từ chối | Không nhất thiết có event state change | Thường cần được ghi nếu thuộc phạm vi audit |
| Đọc dữ liệu | Tái dựng state, projection và lịch sử miền | Điều tra, truy vấn và báo cáo kiểm toán |
| Bảo vệ | Append-only, version và kiểm soát stream | Kiểm soát truy cập, chống sửa đổi và lưu giữ theo chính sách |

Hai kho có thể liên kết bằng correlationId hoặc resourceId, nhưng nên giữ mục đích và quyền truy cập riêng.

## 13. Event Sourcing thường kết hợp CQRS, nhưng không đồng nghĩa CQRS

CQRS tách mô hình ghi (command model) khỏi mô hình đọc (query model). Event Sourcing lưu trạng thái bằng event stream. Hai kiến trúc có thể kết hợp, nhưng mỗi khái niệm độc lập:

- Có thể dùng CQRS với database CRUD thông thường.
- Có thể dùng Event Sourcing và tạo projection để đọc.
- Có thể dùng Event Sourcing mà không triển khai đầy đủ hai service riêng cho command và query.
- Có thể dùng Domain Event trong ứng dụng không có CQRS lẫn Event Sourcing.

Khi kết hợp CQRS và Event Sourcing, command xử lý hành vi trên Aggregate được dựng từ stream. Sau khi append event, projection cập nhật read model. Read model có thể trễ so với write model, nên API cần thể hiện eventual consistency nếu người dùng vừa ghi xong và đọc lại ngay.

Không nên chọn CQRS hoặc Event Sourcing chỉ vì chúng thường xuất hiện cùng nhau. Hãy bắt đầu từ nhu cầu lịch sử, truy vấn, audit và khả năng thay đổi của miền.

## 14. Projection và read model được dựng từ event

Một projection là mô hình dẫn xuất từ event stream hoặc integration event. Ví dụ, OrderSummary có thể lưu mã đơn, tên khách hàng, tổng tiền và trạng thái để hiển thị danh sách nhanh.

Projection có thể:

- Được xây dựng từ đầu bằng cách replay event.
- Được cập nhật tăng dần khi event mới đến.
- Được tạo lại khi thay đổi cách đọc hoặc cấu trúc dữ liệu.
- Có version riêng để theo dõi tiến độ xử lý.

Projection không phải nguồn dữ liệu chính nếu event stream là source of truth. Khi projection lỗi, cần có khả năng rebuild và đối soát. Consumer phải xử lý event lặp an toàn vì việc publish/consume thường có thể theo cơ chế at-least-once.

Không phải mọi projection đều cần được dựng từ event sourcing. Một hệ CRUD cũng có thể dùng Domain Event hoặc outbox để cập nhật read model.

## 15. Event Sourcing và tính bất biến của lịch sử

Event đã được ghi vào stream không nên bị sửa hoặc xóa chỉ để làm lịch sử trông giống trạng thái hiện tại. Nếu phát hiện một giao dịch sai, hãy ghi nhận một event mới có ý nghĩa nghiệp vụ để sửa hoặc bù trừ.

Ví dụ:

- PaymentCaptured ghi nhận đã thu tiền.
- PaymentRefunded ghi nhận đã hoàn tiền.
- InvoiceIssued ghi nhận hóa đơn đã phát hành.
- InvoiceCorrected ghi nhận một điều chỉnh hóa đơn.

Không xóa PaymentCaptured rồi thay payload thành PaymentRefunded. Lịch sử cần phản ánh cả việc thu tiền và việc hoàn tiền sau đó.

Append-only không có nghĩa dữ liệu được phép lưu vô thời hạn bất kể yêu cầu bảo mật hoặc lưu giữ. Event có thể chứa thông tin cá nhân; cần thiết kế giảm thiểu dữ liệu, mã hóa, phân quyền, chính sách retention và cách xử lý yêu cầu xóa/ẩn danh phù hợp với quy định áp dụng. Một số hệ thống dùng tham chiếu hoặc token thay cho dữ liệu cá nhân trực tiếp để có thể quản lý vòng đời thông tin nhạy cảm độc lập hơn.

## 16. Event Schema Evolution và Upcasting

Event có thể tồn tại nhiều năm, trong khi mô hình miền và code thay đổi. Một event cũ có thể thiếu trường mới hoặc dùng tên/định dạng khác với kiểu hiện tại.

Các cách xử lý phổ biến:

- Gắn eventVersion hoặc schemaVersion vào record.
- Giữ parser cho các phiên bản event cũ.
- Dùng upcaster để chuyển payload cũ sang hình dạng hiện tại khi đọc.
- Không thay đổi ý nghĩa của event cũ chỉ để khớp code mới.
- Tạo event mới khi ý nghĩa nghiệp vụ thực sự thay đổi.
- Kiểm thử replay trên dữ liệu lịch sử đại diện trước khi triển khai.

Ví dụ, OrderAddressChanged phiên bản 1 chỉ có street và city; phiên bản 2 có thêm postalCode và countryCode. Upcaster có thể cung cấp giá trị mặc định hoặc biểu diễn trường thiếu theo quy tắc đã xác định. Không nên tự suy ra dữ kiện lịch sử không có trong event nếu việc đó làm thay đổi ý nghĩa.

Thay đổi schema không tương thích cần được triển khai có kiểm soát. Nếu replay thất bại trên một event cũ, Aggregate có thể không được khôi phục; vì vậy event contract và code xử lý lịch sử là một phần quan trọng của vận hành Event Sourcing.

## 17. Side Effect không được chạy lại khi replay

Replay có thể chạy hàng nghìn hoặc hàng triệu event để dựng lại state hoặc rebuild projection. Nếu hàm apply gửi email, thu tiền, gọi API hoặc ghi sang hệ thống ngoài, việc replay có thể lặp side effect và gây hậu quả nghiêm trọng.

Hãy giữ hàm áp dụng event có tính xác định và không có side effect bên ngoài. Các hành động tích hợp nên được xử lý qua subscription, outbox hoặc projection handler có idempotency.

Ví dụ:

- apply(OrderConfirmed) chỉ đổi trạng thái Aggregate trong bộ nhớ.
- Một integration handler nhận OrderConfirmed và tạo lệnh chuẩn bị hàng.
- Handler lưu eventId đã xử lý hoặc dùng khóa idempotency để không tạo lệnh trùng.

Nếu cần rebuild projection, tạo một projection mới hoặc dùng checkpoint riêng; không phát lại các side effect nghiệp vụ như thể event vừa xảy ra lần đầu.

## 18. Event Sourcing và Audit Log: yêu cầu bảo mật khác nhau

Event store thường là dữ liệu vận hành cốt lõi của domain. Nếu bị sửa hoặc mất, trạng thái Aggregate có thể không dựng lại được. Audit Log có thể là bằng chứng điều tra và kiểm toán, nên thường cần kiểm soát truy cập, tính toàn vẹn và lưu giữ riêng.

Một số biện pháp có thể áp dụng:

- Chỉ cấp quyền append/read theo vai trò; hạn chế quyền sửa/xóa trực tiếp.
- Ghi lại truy cập quản trị và thao tác thay đổi cấu hình.
- Mã hóa dữ liệu khi truyền và khi lưu.
- Tách dữ liệu nhạy cảm khỏi event payload nếu có thể.
- Dùng hash chain, chữ ký hoặc cơ chế tamper-evident nếu yêu cầu toàn vẹn đòi hỏi.
- Giới hạn truy vấn và export audit log; ghi nhận việc truy cập log.
- Xác định retention, backup, restore và quy trình xử lý dữ liệu theo chính sách.

Không phải hệ thống nào cũng cần hash chain hoặc chữ ký cho mọi event. Chọn biện pháp theo yêu cầu kiểm soát và mức độ rủi ro. Cần phân biệt append-only ở tầng ứng dụng với bảo đảm chống sửa đổi ở tầng hạ tầng.

## 19. Khi nào nên dùng Event Sourcing?

Event Sourcing có thể phù hợp khi:

- Lịch sử thay đổi là dữ liệu nghiệp vụ quan trọng, cần biết trạng thái hình thành ra sao.
- Cần tái dựng trạng thái tại một thời điểm hoặc giải thích quyết định lịch sử.
- Nhiều projection khác nhau cần được dựng từ cùng một lịch sử sự kiện.
- Quy trình nghiệp vụ có các sự kiện có ý nghĩa rõ ràng và có thể mô hình hóa ổn định.
- Tổ chức sẵn sàng đầu tư vào versioning, replay, concurrency, vận hành và giám sát event store.

Ví dụ phù hợp có thể là tài khoản tài chính, sổ cái, đơn hàng cần lịch sử trạng thái chi tiết hoặc hệ thống quản lý hợp đồng cần giải thích các thay đổi theo thời gian. Mức độ phù hợp vẫn phụ thuộc yêu cầu nghiệp vụ và quy định cụ thể.

## 20. Khi nào chưa nên dùng Event Sourcing?

CRUD thường đơn giản và phù hợp hơn khi:

- Ứng dụng chủ yếu lưu dữ liệu hiện tại và không cần replay.
- Lịch sử có thể được đáp ứng bằng audit table hoặc change history đơn giản.
- Domain chưa có ngôn ngữ sự kiện ổn định.
- Các thay đổi schema và nghiệp vụ diễn ra nhanh, chưa có năng lực quản lý event version.
- Đội ngũ chưa sẵn sàng vận hành event store, projection, replay và xử lý lỗi.
- Chi phí đọc/ghi và độ phức tạp vượt lợi ích của việc lưu event stream.

Không nên dùng Event Sourcing chỉ để “có lịch sử”. Nếu yêu cầu chỉ là ghi người sửa, thời điểm và giá trị trước/sau, Audit Log hoặc temporal table có thể đáp ứng đơn giản hơn.

## 21. Ví dụ phân biệt trong một luồng nghiệp vụ

Giả sử nhân viên hủy đơn đã được xác nhận:

1. Nhân viên gửi command CancelOrder.
2. Order Aggregate kiểm tra đơn có được phép hủy không.
3. Nếu hợp lệ, hệ thống ghi OrderCancelled.
4. Fulfillment nhận Integration Event và yêu cầu dừng xử lý.
5. Audit Log ghi actor, vai trò, thời điểm, kênh admin và kết quả.

Nếu hệ thống dùng CRUD:

- Bản ghi orders được cập nhật status thành CANCELLED.
- OrderCancelled được lưu trong outbox để công bố.
- Audit record ghi người thực hiện và kết quả.

Nếu hệ thống dùng Event Sourcing:

- OrderCancelled được append vào stream Order với version mới.
- Trạng thái Order được dựng lại từ event stream.
- Projection cập nhật danh sách đơn.
- Integration Event có thể được tạo từ event nội bộ.
- Audit record vẫn ghi actor và hành động quản trị.

Hai kiến trúc có thể tạo ra thông tin tương tự cho consumer, nhưng nguồn dữ liệu chính và cách khôi phục trạng thái khác nhau.

## 22. Kiểm thử và vận hành

Với Event Sourcing, cần kiểm thử nhiều hơn việc một command tạo đúng một event:

- Replay toàn bộ stream tạo ra đúng trạng thái Aggregate mong đợi.
- Thứ tự event được giữ trong từng stream.
- Expected version phát hiện append cạnh tranh.
- Event cũ được đọc qua upcaster hoặc handler tương thích.
- Snapshot khớp với replay từ đầu tại cùng version.
- Projection có thể rebuild và xử lý event trùng.
- Replay không phát sinh side effect bên ngoài.
- Event sửa sai được biểu diễn bằng event bù trừ thay vì sửa lịch sử.
- Audit Log ghi được cả hành động bị từ chối theo phạm vi kiểm soát.
- Quyền truy cập event store và audit log được kiểm tra riêng.

Vận hành cần theo dõi độ dài stream, tốc độ append, lỗi replay, projection lag, consumer lag, event không thể đọc, dead-letter và thời gian rebuild. Cần có backup/restore đã được diễn tập vì event store là nguồn dữ liệu chính.

## 23. Những lỗi thường gặp

**Gọi ứng dụng có Domain Event là Event Sourcing.** Domain Event có thể được phát trong CRUD; Event Sourcing yêu cầu event stream là nguồn trạng thái chính và replay được.

**Dùng Audit Log để dựng Aggregate.** Audit record có thể thiếu dữ kiện và không theo đúng thứ tự thay đổi miền. Chỉ dùng event được thiết kế cho replay để khôi phục state.

**Dùng Event Store làm Audit Log duy nhất.** Event store thường không ghi mọi lần đọc, hành động bị từ chối hoặc thay đổi quyền. Duy trì audit concern riêng.

**Cho consumer đọc trực tiếp event store nội bộ.** Điều này làm lộ cấu trúc và schema lịch sử. Hãy công bố Integration Event hoặc read API.

**Chạy side effect trong replay.** Có thể gửi email, thu tiền hoặc tạo lệnh trùng. Hàm apply phải tập trung cập nhật state; side effect xử lý riêng và idempotent.

**Sửa event cũ để sửa trạng thái hiện tại.** Làm sai lịch sử. Hãy append event correction hoặc compensation có ý nghĩa.

**Không quản lý event version.** Code mới có thể không đọc được stream cũ. Hãy version schema, upcast và kiểm thử replay.

**Coi snapshot là nguồn dữ liệu chính.** Snapshot là tối ưu hóa; event stream vẫn là lịch sử có thể dựng lại.

**Bỏ qua dữ liệu nhạy cảm trong event.** Event bất biến có thể khiến việc xóa dữ liệu khó hơn. Hãy giảm thiểu dữ liệu, dùng tham chiếu/token và thiết kế retention ngay từ đầu.

## 24. Quy trình lựa chọn và triển khai

1. **Xác định nhu cầu lịch sử:** cần replay trạng thái hay chỉ cần biết ai đã thay đổi dữ liệu?
2. **Phân biệt yêu cầu:** Domain Event, Event Sourcing, Audit Log và Integration Event đang giải quyết vấn đề nào?
3. **Chọn Aggregate/stream boundary:** xác định stream nào đại diện cho vòng đời và bất biến nào.
4. **Thiết kế event schema:** tên, payload, version, metadata và thứ tự.
5. **Thiết kế command handling:** dựng Aggregate, kiểm tra hành vi, tạo event và append với expected version.
6. **Thiết kế replay:** hàm apply xác định, không có side effect và xử lý event lịch sử.
7. **Thiết kế snapshot/projection:** chỉ thêm khi cần hiệu năng hoặc truy vấn; bảo đảm rebuild được.
8. **Thiết kế Integration Event:** chuyển đổi event nội bộ thành hợp đồng công bố phù hợp.
9. **Thiết kế Audit Log riêng:** ghi actor, action, resource, outcome và metadata kiểm soát.
10. **Quản lý bảo mật và vòng đời:** retention, mã hóa, quyền truy cập, schema evolution, backup và restore.
11. **Kiểm thử và vận hành:** replay, concurrency, projection lag, duplicate, correction và khôi phục sự cố.

## 25. Checklist rà soát

- Hệ thống có thực sự cần dựng lại trạng thái từ lịch sử không?
- Event stream có là nguồn dữ liệu chính hay chỉ là bản ghi phụ?
- Domain Event có được phân biệt với command và state không?
- Event có đủ dữ kiện để replay Aggregate không?
- Event store có stream version và expected version không?
- Replay có xác định và không tạo side effect không?
- Snapshot có lưu version và có thể tái tạo không?
- Event schema cũ có thể đọc bằng version/upcaster không?
- Integration Event có được tách khỏi event nội bộ khi cần không?
- Audit Log có ghi actor, action, outcome và các lần bị từ chối theo yêu cầu không?
- Event store và audit log có quyền truy cập/retention phù hợp không?
- Dữ liệu nhạy cảm có được giảm thiểu trong event payload không?
- Có thể rebuild projection và khôi phục event store sau sự cố không?

## 26. Nguyên tắc cần ghi nhớ

Domain Event là sự thật có ý nghĩa nghiệp vụ đã xảy ra. Event Sourcing là cách lưu các sự kiện thay đổi trạng thái làm nguồn dữ liệu chính để dựng lại Aggregate. Audit Log là dấu vết về actor, hành động, tài nguyên, thời điểm và kết quả phục vụ truy vết hoặc kiểm toán.

Một hệ thống có thể dùng Domain Event mà không dùng Event Sourcing; một hệ thống Event Sourcing vẫn cần Audit Log riêng cho những hoạt động không làm thay đổi trạng thái nghiệp vụ. Hãy chọn Event Sourcing khi lịch sử và khả năng replay mang lại giá trị đủ lớn để bù chi phí versioning, projection, concurrency và vận hành. Giữ ranh giới rõ giữa event stream, event tích hợp và audit trail để lịch sử nghiệp vụ có thể tin cậy, trạng thái có thể khôi phục và hoạt động hệ thống có thể được kiểm soát.
