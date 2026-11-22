# Đặt tên sự kiện theo sự việc đã xảy ra và thời điểm nghiệp vụ

Trong Domain-Driven Design (DDD), **Domain Event (sự kiện miền)** mô tả một sự việc có ý nghĩa nghiệp vụ đã thực sự xảy ra. Tên sự kiện vì vậy nên diễn đạt một sự thật đã hoàn tất, thường dùng dạng quá khứ như `OrderSubmitted`, `PaymentAuthorized` hoặc `InvoiceIssued`. Tên gọi cần giúp người đọc hiểu điều gì đã xảy ra mà không phải suy đoán từ tên hàm, trạng thái kỹ thuật hay mã lỗi.

Thời điểm đi cùng sự kiện cũng cần phản ánh đúng ý nghĩa nghiệp vụ. Thời điểm một giao dịch thực sự xảy ra có thể khác thời điểm hệ thống ghi nhận, phát đi hoặc xử lý sự kiện. Một điều chỉnh giá được phê duyệt hôm nay nhưng có hiệu lực từ đầu tháng là ví dụ điển hình: ngày phê duyệt và ngày bắt đầu hiệu lực là hai thông tin khác nhau. Nếu gộp chúng thành một timestamp, lịch sử và các phép tính về sau có thể bị sai.

## 1. Domain Event ghi nhận một sự thật đã xảy ra

Một Domain Event là bản ghi về một sự việc trong miền nghiệp vụ mà các bên liên quan cần biết. Sự kiện có thể làm thay đổi trạng thái của một quy trình, kích hoạt hành động tiếp theo hoặc tạo ra thông tin cần lưu trong lịch sử.

Ví dụ trong hệ thống thương mại:

- `OrderSubmitted`: khách hàng đã gửi đơn hàng.
- `QuoteValidated`: báo giá đã được xác nhận còn hiệu lực.
- `InventoryReserved`: hàng đã được giữ cho đơn.
- `PaymentAuthorized`: khoản thanh toán đã được cấp phép.
- `OrderConfirmed`: đơn hàng đã được xác nhận.
- `ShipmentDispatched`: lô hàng đã được bàn giao để vận chuyển.
- `PaymentRefunded`: khoản tiền đã được hoàn lại.

Điểm chung của các tên này là chúng mô tả kết quả hoặc sự việc đã xảy ra. Khi một thành phần khác nhận `OrderConfirmed`, nó có thể hiểu rằng đơn đã được xác nhận theo quy tắc của context sở hữu sự kiện.

Một event không phải là lời dự đoán, yêu cầu hoặc ý định. `ConfirmOrder` diễn đạt yêu cầu xác nhận; `OrderConfirmed` ghi nhận việc xác nhận đã thành công. Nếu yêu cầu bị từ chối, `OrderConfirmed` không được phát ra.

## 2. Phân biệt Command, Event và State

Ba khái niệm thường xuất hiện trong cùng một luồng nhưng trả lời các câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Command | Muốn hệ thống thực hiện điều gì? | `ConfirmOrder` |
| Domain Event | Điều gì đã xảy ra? | `OrderConfirmed` |
| State | Đối tượng hiện đang ở tình trạng nào? | `OrderStatus.CONFIRMED` |

Command có thể được chấp nhận hoặc từ chối. Event chỉ được ghi nhận khi sự việc tương ứng đã xảy ra. State mô tả tình trạng hiện tại sau khi áp dụng các hành động và sự kiện liên quan.

Ví dụ:

1. Khách hàng gửi command `SubmitOrder`.
2. Aggregate kiểm tra các điều kiện gửi đơn.
3. Nếu hợp lệ, đơn chuyển từ `DRAFT` sang `PENDING_CONFIRMATION`.
4. Hệ thống ghi nhận `OrderSubmitted`.
5. Nếu báo giá hết hạn, command bị từ chối và event `OrderSubmitted` không được tạo. Nếu việc từ chối có ý nghĩa nghiệp vụ cần lưu hoặc thông báo, có thể ghi nhận một sự kiện riêng như `OrderSubmissionRejected`.

Không nên đặt tên event giống command rồi coi việc nhận command là bằng chứng hành động đã thành công. Ví dụ, nhận `CancelOrder` không có nghĩa đơn đã hủy; kết quả có thể là `OrderCancelled` hoặc một lỗi nghiệp vụ nếu đơn đã được giao.

## 3. Đặt tên bằng ngôn ngữ nghiệp vụ

Tên sự kiện nên sử dụng thuật ngữ mà chuyên gia nghiệp vụ và đội phát triển đã thống nhất trong bounded context sở hữu sự kiện. Một tên tốt thường cho biết:

- Đối tượng hoặc khái niệm nào liên quan.
- Sự việc gì đã xảy ra với đối tượng đó.
- Kết quả hoặc ý nghĩa nghiệp vụ nào đã hoàn tất.

Trong mã nguồn, cách đặt tên phổ biến là `Subject + PastParticiple` hoặc một cụm danh từ diễn tả sự thật đã xảy ra:

| Tên mơ hồ hoặc mang tính lệnh | Tên sự kiện rõ hơn | Ý nghĩa |
| --- | --- | --- |
| `ProcessOrder` | `OrderSubmitted` | Đơn đã được gửi |
| `ConfirmOrder` | `OrderConfirmed` | Đơn đã được xác nhận |
| `UpdatePayment` | `PaymentAuthorized` | Khoản thanh toán đã được cấp phép |
| `ChangeInvoice` | `InvoiceIssued` | Hóa đơn đã được phát hành |
| `SendShipment` | `ShipmentDispatched` | Lô hàng đã được gửi đi |
| `HandleReturn` | `ReturnApproved` | Yêu cầu trả hàng đã được chấp thuận |

Không nhất thiết mọi event đều phải kết thúc bằng `-ed`. Điều quan trọng là tên phải diễn đạt một sự việc đã xảy ra và có ý nghĩa rõ ràng. Ví dụ `PaymentDeclined`, `OrderExpired` hoặc `DeliveryDelayed` đều có thể là tên event phù hợp.

### Dùng tên cụ thể thay cho tên quá tổng quát

Tên như `OrderUpdated` hoặc `StatusChanged` có thể hữu ích nếu chính việc cập nhật tổng quát là điều nghiệp vụ cần quan tâm. Tuy nhiên, nếu sự kiện thực tế là đơn đã được xác nhận, hủy hoặc giao, tên cụ thể sẽ giúp consumer hiểu kết quả và phản ứng đúng hơn.

Ví dụ, `OrderStatusChanged` buộc consumer phải đọc thêm trường `newStatus` mới biết chuyện gì xảy ra. `OrderCancelled` đã thể hiện rõ sự thật nghiệp vụ và giúp hợp đồng dễ hiểu hơn.

### Không nhét thời gian hoặc chi tiết triển khai vào tên

Tránh những tên như `OrderConfirmedAt2026`, `OrderConfirmedFromApi` hoặc `OrderConfirmedAfterDatabaseUpdate`. Thời gian, nguồn phát sinh và chi tiết triển khai là metadata hoặc dữ liệu liên quan; chúng không nên làm biến dạng tên sự kiện. Tên event cần ổn định khi cách triển khai thay đổi.

## 4. Sự kiện từ chối và thất bại cũng có thể là sự thật nghiệp vụ

Không phải mọi Domain Event đều diễn tả một kết quả thành công. Một quyết định từ chối có thể là một sự việc nghiệp vụ quan trọng:

- `CreditApplicationRejected`: hồ sơ tín dụng đã bị từ chối.
- `OrderSubmissionRejected`: yêu cầu gửi đơn đã bị từ chối.
- `ReturnRequestDeclined`: yêu cầu trả hàng đã không được chấp thuận.
- `PaymentDeclined`: nhà cung cấp thanh toán đã từ chối giao dịch.

Hãy phân biệt kết quả nghiệp vụ với lỗi kỹ thuật. `PaymentDeclined` có thể là phản hồi hợp lệ từ nhà cung cấp; `PaymentGatewayConnectionTimedOut` thường mô tả tình trạng kỹ thuật hoặc một kết quả chưa xác định. Timeout không chứng minh rằng khoản thanh toán đã thất bại: nhà cung cấp có thể đã xử lý nhưng phản hồi bị mất.

Chỉ đưa một thất bại vào Domain Event khi nó có ý nghĩa đối với nghiệp vụ hoặc vòng đời quy trình. Không cần biến mọi exception, HTTP 500 hay lỗi truy vấn thành sự kiện miền.

## 5. Một event cần ghi nhận sự thật nào?

Payload của event nên chứa dữ kiện đủ để consumer hiểu sự việc và thực hiện trách nhiệm của mình. Thường cần:

- Định danh của đối tượng hoặc giao dịch liên quan.
- Các định danh liên quan cần thiết để liên kết quy trình.
- Những dữ kiện nghiệp vụ cần thiết tại thời điểm sự việc xảy ra.
- Thời điểm nghiệp vụ xảy ra.
- Phiên bản hoặc metadata cần thiết để diễn giải hợp đồng.

Ví dụ:

```java
public record OrderConfirmed(
    OrderId orderId,
    CustomerId customerId,
    QuoteId quoteId,
    Instant occurredAt
) implements DomainEvent {}
```

Sự kiện ghi nhận đơn nào đã được xác nhận, thuộc khách hàng nào, dựa trên báo giá nào và xảy ra khi nào. Nó không cần mang toàn bộ object graph của `Order`, cũng không nên chứa tham chiếu đến Entity mutable. Consumer cần dữ kiện khác có thể truy vấn qua hợp đồng phù hợp hoặc nhận thêm event liên quan.

Đừng đưa quá nhiều dữ liệu chỉ vì consumer hiện tại muốn tiện sử dụng. Payload lớn và chứa nhiều trường nội bộ làm producer khó thay đổi mô hình, đồng thời tạo phụ thuộc không cần thiết. Ngược lại, payload quá ít có thể khiến consumer phải gọi ngược producer cho mọi thông tin. Hãy chọn dữ kiện dựa trên ý nghĩa sự kiện và hợp đồng tích hợp.

## 6. Phân biệt thời điểm nghiệp vụ và thời điểm hệ thống

Một sự kiện có thể đi qua nhiều thời điểm khác nhau. Không nên dùng một trường `timestamp` chung chung nếu các thời điểm mang ý nghĩa khác nhau.

| Trường thời gian | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `occurredAt` | Thời điểm sự việc nghiệp vụ thực sự xảy ra theo nguồn có thẩm quyền | Đơn được xác nhận lúc 10:15 |
| `effectiveAt` / `effectiveFrom` | Thời điểm quy tắc hoặc thay đổi bắt đầu có hiệu lực trong nghiệp vụ | Giá mới có hiệu lực từ ngày đầu tháng |
| `recordedAt` | Thời điểm event được lưu vào event store hoặc nhật ký bền vững | Event được ghi lúc 10:15:02 |
| `publishedAt` | Thời điểm event được gửi ra broker hoặc kênh tích hợp | Message được publish lúc 10:15:03 |
| `receivedAt` | Thời điểm consumer nhận được message | Consumer nhận lúc 10:15:05 |
| `processedAt` | Thời điểm consumer hoàn tất xử lý | Consumer xử lý xong lúc 10:15:06 |

Các trường này không bắt buộc phải xuất hiện hết trong payload Domain Event. `occurredAt` và dữ kiện hiệu lực có thể thuộc nội dung nghiệp vụ; `recordedAt`, `publishedAt`, `receivedAt` và `processedAt` thường thuộc envelope hoặc metadata của hạ tầng.

### Ví dụ: phê duyệt hôm nay, có hiệu lực từ ngày trước đó

Một thay đổi giá được phê duyệt vào ngày 10 tháng 4 nhưng có hiệu lực từ ngày 1 tháng 4. Sự kiện có thể là `PriceAdjustmentApproved`, với:

- `occurredAt`: ngày 10 tháng 4 — thời điểm phê duyệt thực sự xảy ra.
- `effectiveFrom`: ngày 1 tháng 4 — ngày mức giá mới bắt đầu được áp dụng.

Không nên đặt `occurredAt` thành ngày 1 tháng 4 chỉ vì giá có hiệu lực từ ngày đó. Làm như vậy sẽ viết sai lịch sử phê duyệt. Hai thời điểm trả lời hai câu hỏi khác nhau và cần được lưu riêng.

## 7. Chọn kiểu thời gian phù hợp

Trong Java, kiểu thời gian cần phản ánh đúng ý nghĩa:

| Kiểu | Dùng khi |
| --- | --- |
| `Instant` | Cần một thời điểm tuyệt đối trên dòng thời gian, có thể so sánh giữa các hệ thống |
| `LocalDate` | Nghiệp vụ quan tâm đến ngày lịch, không phải một thời điểm cụ thể trong ngày |
| `LocalDateTime` | Cần ngày và giờ địa phương nhưng múi giờ được quản lý riêng hoặc không có ý nghĩa trong khái niệm |
| `ZonedDateTime` | Cần thời gian địa phương gắn với múi giờ và quy tắc lịch của vùng |
| `OffsetDateTime` | Cần ngày giờ cùng độ lệch UTC tại thời điểm ghi nhận |

Với `occurredAt` của một giao dịch trên hệ thống phân tán, `Instant` thường là lựa chọn phù hợp. Khi hiển thị, ứng dụng chuyển sang múi giờ của người dùng hoặc địa điểm kinh doanh. Với một `BusinessDate` như ngày hạch toán, ngày bán hàng hoặc ngày làm việc, `LocalDate` có thể phù hợp hơn.

Không nên lưu một thời điểm toàn cầu dưới dạng `LocalDateTime` rồi giả định mọi consumer hiểu cùng múi giờ. Nếu thời gian địa phương có ý nghĩa nghiệp vụ, hãy lưu cả `ZoneId` hoặc dữ kiện vùng cần thiết. Ví dụ, giờ đóng cửa của cửa hàng tại TP. Hồ Chí Minh phụ thuộc múi giờ `Asia/Ho_Chi_Minh`, trong khi một event được trao đổi giữa nhiều hệ thống nên có thể dùng `Instant` để xác định thời điểm tuyệt đối.

## 8. Đưa thời gian vào event một cách xác định

Không nên gọi `Instant.now()` rải rác bên trong Entity hoặc Policy. Việc đọc đồng hồ trực tiếp khiến kiểm thử khó xác định và có thể tạo ra các thời điểm không nhất quán trong cùng một thao tác.

Một cách rõ ràng là lấy thời gian từ `Clock` ở application layer rồi truyền vào hành vi miền:

```java
public void confirm(Instant occurredAt) {
    requirePendingConfirmation();
    status = OrderStatus.CONFIRMED;
    registerEvent(new OrderConfirmed(id, customerId, quoteId, occurredAt));
}
```

Application service cung cấp thời gian:

```java
public final class ConfirmOrderHandler {
    private final OrderRepository orders;
    private final Clock clock;

    public ConfirmOrderHandler(OrderRepository orders, Clock clock) {
        this.orders = orders;
        this.clock = clock;
    }

    public void handle(ConfirmOrder command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(() -> new OrderNotFound(command.orderId()));

        order.confirm(clock.instant());
        orders.save(order);
    }
}
```

Trong kiểm thử, có thể tiêm `Clock.fixed(...)` để xác nhận event mang đúng thời điểm. Điều này giúp kiểm thử các quy tắc theo ngày hiệu lực, hạn thanh toán hoặc thời hạn reservation mà không phụ thuộc thời gian thực của máy chạy test.

Thời điểm nên được lấy gần với thời điểm sự việc được quyết định và ghi nhận. Nếu một quy trình kéo dài nhiều bước, không nên dùng thời gian bắt đầu request làm `occurredAt` cho một sự kiện chỉ xảy ra sau khi các điều kiện hoàn tất.

## 9. Thời gian xảy ra không phải thứ tự nhân quả

Trong hệ thống phân tán, timestamp không phải lúc nào cũng đủ để xác định thứ tự sự kiện:

- Đồng hồ của các máy có thể lệch nhau.
- Hai sự kiện có thể có cùng độ chính xác timestamp.
- Event xảy ra trước có thể được publish hoặc nhận sau do retry, mạng hoặc hàng đợi.
- Một consumer có thể xử lý message theo thứ tự khác với thứ tự phát sinh.

Vì vậy, đừng dùng riêng `occurredAt` để quyết định thứ tự tuyệt đối hoặc kết luận quan hệ nhân quả. Với các event thuộc cùng Aggregate, có thể dùng `aggregateVersion` hoặc sequence number tăng dần để xác định thứ tự thay đổi. Với quy trình qua nhiều context, cần thêm quan hệ nhân quả hoặc correlation metadata nếu nghiệp vụ yêu cầu.

Ví dụ envelope:

```java
public record EventEnvelope<T extends DomainEvent>(
    UUID eventId,
    String aggregateId,
    long aggregateVersion,
    String correlationId,
    String causationId,
    Instant recordedAt,
    T payload
) {}
```

Trong đó:

- `eventId` nhận diện một message event cụ thể để hỗ trợ deduplication.
- `aggregateId` cho biết event phát sinh từ Aggregate nào.
- `aggregateVersion` hoặc sequence cho biết thứ tự thay đổi trong Aggregate đó.
- `correlationId` liên kết các thông điệp thuộc cùng một quy trình.
- `causationId` cho biết command hoặc event nào dẫn đến message hiện tại.
- `recordedAt` là thời điểm envelope được ghi nhận.

Các trường metadata này không thay thế nội dung nghiệp vụ của event. Chúng hỗ trợ vận hành, truy vết và xử lý message.

## 10. Xử lý event đến trễ hoặc sai thứ tự

Giả sử `OrderConfirmed` xảy ra lúc 10:00 nhưng do broker retry, consumer chỉ nhận được lúc 10:05. `occurredAt` vẫn là 10:00; `receivedAt` là 10:05. Consumer không nên sửa thời điểm xảy ra để khớp với thời điểm nhận.

Một consumer cần xem xét:

- Event có bị gửi lặp không? Dùng `eventId` hoặc khóa nghiệp vụ để xử lý idempotent.
- Event có cũ hơn trạng thái consumer đã xử lý không? Dùng version hoặc sequence khi hợp đồng cung cấp.
- Có event trước đó còn thiếu không? Có cần chờ, tải lại dữ liệu hoặc đối soát không?
- Quy tắc nghiệp vụ dùng thời điểm xảy ra hay thời điểm xử lý? Ví dụ, hạn thanh toán thường dựa vào thời điểm nghiệp vụ, không phải thời điểm message được tiêu thụ.
- Nếu event đến muộn làm thay đổi kết quả báo cáo, hệ thống có cơ chế cập nhật lại projection không?

Với event đến từ nhiều Aggregate hoặc nhiều bounded context, không tồn tại một thứ tự toàn cục đáng tin cậy chỉ dựa trên timestamp. Hãy xác định thứ tự nào thực sự cần cho nghiệp vụ và dùng metadata hoặc quy trình điều phối phù hợp.

## 11. Phạm vi ngữ nghĩa và bounded context

Tên event cần có ý nghĩa trong bounded context phát sinh nó. `OrderConfirmed` trong Order Management có thể ghi nhận đơn đã thỏa điều kiện xác nhận của context đó. Fulfillment có thể nhận event này và tạo quy trình thực hiện đơn; nó không nên diễn giải event như thể hàng đã được đóng gói hoặc giao đi.

Một số lưu ý:

- Dùng thuật ngữ của context phát sinh event.
- Không đặt tên theo cách consumer suy đoán từ mô hình nội bộ của producer.
- Nếu cần chia sẻ ra ngoài context, thiết kế integration event hoặc contract phù hợp với bên nhận.
- Không giả định event nội bộ và event tích hợp phải có cùng payload hoặc cùng tên nếu ngữ nghĩa công bố khác nhau.
- Nếu cùng một từ có nghĩa khác ở hai context, hãy làm rõ mapping thay vì ép hai context dùng một event mơ hồ.

Ví dụ, Order Management có thể phát `OrderConfirmed`; một adapter tích hợp chuyển nó thành message `SalesOrderAccepted` theo ngôn ngữ của hệ thống đối tác. Việc chuyển đổi giúp mỗi bên giữ mô hình riêng và tạo hợp đồng rõ ràng.

## 12. Domain Event khác Audit Log và Technical Event

Ba loại thông tin này có thể cùng được lưu hoặc gửi qua message broker nhưng mục đích khác nhau:

| Loại | Mục đích | Ví dụ |
| --- | --- | --- |
| Domain Event | Ghi nhận sự thật có ý nghĩa nghiệp vụ | `InvoiceIssued` |
| Audit Record | Ghi ai đã thực hiện hành động nào, khi nào, theo quyền nào | `user-42 updated invoice address` |
| Technical Event | Theo dõi hoạt động hoặc sự cố của hạ tầng | `DatabaseConnectionPoolExhausted` |

Một hành động nghiệp vụ có thể tạo ra cả Domain Event và audit record. Ví dụ, `CreditLimitChanged` ghi nhận sự thật nghiệp vụ; audit record có thể ghi người phê duyệt, địa chỉ IP và lý do truy cập. Không nên nhồi mọi thông tin kiểm toán hoặc kỹ thuật vào payload Domain Event nếu chúng không thuộc ngữ nghĩa của sự kiện.

## 13. Tính bất biến của event và thay đổi hợp đồng

Event là sự thật lịch sử đã xảy ra. Sau khi được công bố hoặc lưu trữ, không nên sửa nội dung để làm cho lịch sử trông giống trạng thái hiện tại. Nếu có thông tin mới hoặc phát hiện sai sót, hãy ghi nhận một event mới có ý nghĩa như `InvoiceCorrectionIssued` hoặc `PaymentReconciliationCompleted` theo ngôn ngữ nghiệp vụ.

Tên và ý nghĩa của event cũng là một phần của hợp đồng. Khi consumer đã phụ thuộc vào `OrderConfirmed`, không nên âm thầm đổi tên hoặc thay đổi ý nghĩa của nó. Khi cấu trúc payload cần thay đổi, hãy cân nhắc:

- Thêm trường tùy chọn tương thích ngược nếu consumer cũ có thể bỏ qua.
- Dùng version schema hoặc version event khi thay đổi cấu trúc không tương thích.
- Chuyển đổi event cũ sang mô hình đọc mới bằng upcaster hoặc adapter khi cần.
- Công bố event mới nếu ngữ nghĩa nghiệp vụ thực sự khác.

Không dùng version để che giấu việc một event đã đổi ý nghĩa. `OrderConfirmed` phiên bản mới vẫn cần nói về cùng một sự thật; nếu nó chuyển từ “đơn được chấp thuận” thành “đơn đã giao”, đó là một sự kiện khác và cần tên khác.

## 14. Ví dụ tổng hợp: tên event và thời điểm

Một luồng đơn hàng có thể tạo ra các sự kiện sau:

| Event | occurredAt | Dữ kiện thời gian khác | Ý nghĩa |
| --- | --- | --- | --- |
| `OrderSubmitted` | 09:00 | — | Đơn đã được gửi |
| `InventoryReserved` | 09:00:02 | `reservationExpiresAt` = 09:15 | Hàng đã được giữ đến hạn |
| `PaymentAuthorized` | 09:00:05 | — | Khoản thanh toán đã được cấp phép |
| `OrderConfirmed` | 09:00:06 | — | Đơn đã được xác nhận |
| `ShipmentDispatched` | 14:30 | `businessDate` = ngày giao | Lô hàng đã được gửi đi |

Giả sử `PaymentAuthorized` được publish lúc 09:00:07 nhưng consumer nhận lúc 09:00:20. Consumer vẫn phải hiểu sự kiện xảy ra lúc 09:00:05. Nếu một báo cáo cần tính số đơn được xác nhận trong ngày, nó nên dựa trên thời điểm nghiệp vụ hoặc business date theo quy tắc báo cáo đã thống nhất, không tự động dùng thời điểm nhận message.

Một event có thể được biểu diễn bằng Java như sau:

```java
public record InventoryReserved(
    ReservationId reservationId,
    OrderId orderId,
    Sku sku,
    Quantity quantity,
    Instant occurredAt,
    Instant reservationExpiresAt
) implements DomainEvent {}
```

`occurredAt` cho biết việc giữ hàng đã xảy ra lúc nào; `reservationExpiresAt` cho biết thời điểm lượt giữ hàng hết hiệu lực. Hai trường không thể thay thế nhau. Nếu reservation được gia hạn, hệ thống có thể ghi một sự kiện mới như `InventoryReservationExtended` với thời điểm xảy ra và hạn mới.

## 15. Kiểm thử tên và thời điểm của Domain Event

Kiểm thử event không chỉ xác nhận lớp event được tạo mà còn cần kiểm tra ngữ nghĩa và thời điểm:

- Tên event có phản ánh sự việc đã xảy ra không?
- Event có chỉ được ghi khi hành động nghiệp vụ thành công không?
- Event từ chối có được phân biệt với command bị từ chối và lỗi kỹ thuật không?
- `occurredAt` có được lấy từ nguồn thời gian xác định không?
- `effectiveAt` có được tách khỏi `occurredAt` khi quy tắc có hiệu lực hồi tố không?
- Consumer có phân biệt thời điểm xảy ra với thời điểm nhận và xử lý không?
- Có dùng version/sequence thay vì timestamp đơn thuần khi cần thứ tự trong Aggregate không?
- Event có thể được xử lý lặp mà không tạo side effect trùng không?
- Payload có đủ dữ kiện nghiệp vụ nhưng không làm lộ mô hình nội bộ không?

Ví dụ kiểm thử với đồng hồ cố định:

```java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-11-18T03:00:00Z"),
    ZoneOffset.UTC
);

handler.handle(command);

assertEquals(
    Instant.parse("2026-11-18T03:00:00Z"),
    publishedEvent.occurredAt()
);
```

Ví dụ giả định test có thể quan sát event được ghi hoặc publish. Trong hệ thống dùng transactional outbox, có thể kiểm tra event đã được lưu cùng transaction; việc publish ra broker là bước riêng và có thể xảy ra muộn hơn.

## 16. Những lỗi thường gặp khi đặt tên và gắn thời gian

**Đặt tên event như command.** `ConfirmOrder` khiến người đọc không biết đó là yêu cầu hay kết quả. Hãy dùng `OrderConfirmed` cho sự thật đã xảy ra.

**Dùng tên tổng quát cho mọi thay đổi.** `DataUpdated` hoặc `StatusChanged` buộc consumer phải suy luận từ payload. Hãy chọn tên phản ánh sự kiện nghiệp vụ cụ thể khi có thể.

**Phát event trước khi hành động thành công.** Consumer có thể thực hiện bước tiếp theo dựa trên một sự thật chưa xảy ra. Chỉ ghi event sau khi điều kiện và thay đổi được xác nhận; công bố ra ngoài cần cơ chế nhất quán với lưu trữ.

**Dùng thời điểm xử lý thay cho thời điểm xảy ra.** Message đến muộn không làm sự kiện xảy ra muộn hơn. Giữ `occurredAt` và `receivedAt` riêng.

**Dùng một timestamp cho cả thời điểm xảy ra và hiệu lực.** Một quyết định được phê duyệt hôm nay có thể áp dụng từ ngày khác. Hãy lưu `occurredAt` và `effectiveFrom` riêng.

**Dùng LocalDateTime không kèm múi giờ cho thời điểm toàn cục.** Các hệ thống có thể diễn giải khác nhau. Dùng `Instant` cho thời điểm tuyệt đối và lưu múi giờ khi ngữ nghĩa địa phương cần thiết.

**Sắp xếp event chỉ bằng timestamp.** Đồng hồ lệch và message đến sai thứ tự có thể tạo kết quả sai. Dùng sequence/version và metadata nhân quả khi phù hợp.

**Đổi ý nghĩa event mà giữ nguyên tên.** Consumer cũ sẽ diễn giải sai lịch sử. Nếu ý nghĩa nghiệp vụ khác, tạo event khác; nếu chỉ đổi schema, quản lý phiên bản tương thích.

## 17. Quy trình đặt tên và thiết kế thời gian cho event

Có thể áp dụng quy trình sau:

1. **Xác định sự việc:** mô tả bằng một câu điều gì đã thực sự xảy ra trong nghiệp vụ.
2. **Kiểm tra trạng thái thành công:** xác nhận command đã hoàn tất hay chỉ mới được yêu cầu/tiếp nhận.
3. **Dùng thuật ngữ của bounded context:** chọn danh từ và động từ mà chuyên gia nghiệp vụ hiểu thống nhất.
4. **Đặt tên như một sự thật:** dùng dạng quá khứ hoặc cụm từ diễn tả kết quả; tránh tên lệnh, dự đoán hoặc chi tiết kỹ thuật.
5. **Xác định dữ kiện cần công bố:** chọn định danh, dữ kiện nghiệp vụ và thông tin cần cho consumer.
6. **Chọn thời điểm nghiệp vụ:** xác định chính xác sự việc xảy ra lúc nào và dùng `occurredAt` phù hợp.
7. **Tách thời điểm hiệu lực:** thêm `effectiveAt`, `effectiveFrom` hoặc `businessDate` nếu nghiệp vụ cần.
8. **Xác định metadata hệ thống:** ghi riêng thời điểm lưu, publish, nhận và xử lý ở envelope hoặc log.
9. **Xác định thứ tự và quan hệ nhân quả:** dùng version, sequence, correlation ID hoặc causation ID khi cần.
10. **Kiểm thử và quản lý hợp đồng:** xác nhận event được phát đúng lúc, consumer xử lý lặp an toàn và thay đổi schema không làm sai ý nghĩa lịch sử.

## 18. Checklist rà soát Domain Event

Trước khi công bố một event, hãy hỏi:

- Tên event có nói rõ điều gì đã xảy ra không?
- Người hiểu nghiệp vụ có nhận ra ý nghĩa tên gọi trong bounded context này không?
- Event có bị nhầm với command, state hoặc thông báo kỹ thuật không?
- Event chỉ được tạo sau khi sự việc thực sự hoàn tất chưa?
- Payload có định danh và dữ kiện cần thiết cho consumer không?
- `occurredAt` có phản ánh thời điểm nghiệp vụ thay vì thời điểm nhận hoặc xử lý không?
- Có cần phân biệt `effectiveAt`, `businessDate` hoặc thời hạn không?
- Múi giờ và độ chính xác thời gian đã rõ chưa?
- Có cần version/sequence để xác định thứ tự thay đổi không?
- Consumer có thể xử lý message trùng hoặc đến trễ an toàn không?
- Tên và schema có được quản lý như một hợp đồng ổn định không?

## 19. Nguyên tắc cần ghi nhớ

Tên Domain Event cần diễn đạt một sự thật nghiệp vụ đã xảy ra, dùng ngôn ngữ thống nhất trong bounded context và phân biệt rõ với command hoặc state. Payload cần chứa dữ kiện đủ để hiểu sự việc; không nên trộn chi tiết triển khai hoặc mọi thông tin audit vào event.

Thời điểm xảy ra, thời điểm có hiệu lực và thời điểm hệ thống ghi nhận hoặc xử lý là những khái niệm khác nhau. Hãy lưu chúng riêng khi nghiệp vụ cần, dùng kiểu thời gian phù hợp, và không dựa riêng vào timestamp để suy ra thứ tự nhân quả. Khi tên gọi và thời gian đều chính xác, event trở thành lịch sử nghiệp vụ đáng tin cậy để các context phối hợp và giải thích những gì đã xảy ra.
