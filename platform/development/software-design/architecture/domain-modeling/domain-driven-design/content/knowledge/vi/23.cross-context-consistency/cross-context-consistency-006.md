# Xử lý thông điệp lặp, đến muộn hoặc sai thứ tự

Trong một hệ thống Domain-Driven Design có nhiều Bounded Context, một sự kiện nghiệp vụ thường được tạo ở một context và được tiêu thụ ở context khác. Hai context có mô hình, dữ liệu và vòng đời riêng nên việc gửi thông điệp qua broker không làm cho trạng thái của chúng tự động nhất quán. Consumer có thể nhận cùng một thông điệp nhiều lần, nhận một thông điệp sau khi các thông điệp mới hơn đã được xử lý, hoặc nhận các thông điệp theo thứ tự khác với thứ tự chúng được tạo.

Ví dụ, Order Management phát ra các sự kiện OrderPlaced, OrderCancelled và OrderConfirmed. Inventory phản ứng để giữ hoặc giải phóng tồn kho. Nếu OrderPlaced được giao lại hai lần, Inventory không được giữ hàng hai lần. Nếu OrderCancelled đến trước OrderPlaced, consumer không nên tạo ra một trạng thái hợp lệ chỉ vì nó xử lý mọi thông điệp theo thứ tự nhận được. Nếu OrderPlaced đã được xử lý nhưng OrderCancelled đến muộn, consumer phải có cách xác định phiên bản nào mới hơn.

Vấn đề vì vậy không phải là làm cho toàn bộ hệ thống có một transaction duy nhất. Vấn đề là xác định bất biến nào phải được bảo vệ trong từng Bounded Context, mức nhất quán nào cần đạt qua ranh giới context, rồi thiết kế thông điệp và consumer để chịu được những đặc tính thực tế của hệ thống phân tán.

## 1. Bắt đầu từ bất biến của Bounded Context

Mỗi Bounded Context sở hữu một mô hình và một tập bất biến riêng. Khi một context nhận sự kiện từ context khác, nó phải bảo vệ bất biến của chính nó. Không nên biến consumer thành nơi cố gắng tái tạo toàn bộ mô hình của producer.

Giả sử Order Management sở hữu trạng thái đơn hàng:

~~~text
OrderPlaced -> Confirmed -> Shipped -> Completed
                  |
                  v
              Cancelled
~~~

Inventory có một mô hình khác:

~~~text
InventoryItem
    |
    +-- availableQuantity
    +-- reservedQuantity
    +-- reservations
~~~

Inventory không cần biết mọi chi tiết của Order. Nó chỉ cần biết những sự kiện và dữ liệu mà quy tắc giữ hàng của nó yêu cầu. Nếu Inventory nhận OrderCancelled, bất biến cục bộ có thể là:

> Không được giải phóng cùng một reservation nhiều hơn một lần.

Đây là lý do idempotency thuộc trách nhiệm của consumer. Producer có thể gửi cùng một event nhiều lần mà không phá vỡ bất biến của Inventory.

Một bất biến khác có thể là:

> Tổng số lượng đã giữ không được vượt quá số lượng có thể giữ.

Nếu consumer xử lý sai thứ tự và áp dụng một event cũ lên trạng thái mới, bất biến này có thể bị phá vỡ. Khi đó chỉ kiểm tra eventId là chưa đủ; consumer cần thêm thông tin về phiên bản hoặc thứ tự nghiệp vụ.

## 2. Ba lỗi thường gặp không giống nhau

Thông điệp lặp, thông điệp đến muộn và thông điệp sai thứ tự thường xuất hiện cùng nhau nhưng cần được xử lý bằng những cơ chế khác nhau.

| Tình huống | Ví dụ | Câu hỏi chính |
|---|---|---|
| Lặp | OrderPlaced có cùng eventId được giao hai lần | Event này đã được xử lý chưa? |
| Đến muộn | OrderCancelled xảy ra trước nhưng tới consumer sau nhiều phút | Event này còn có ý nghĩa với trạng thái hiện tại không? |
| Sai thứ tự | Consumer nhận version 5 trước version 4 | Có thể áp dụng version 5 ngay không? |
| Retry | Consumer lỗi tạm thời rồi broker giao lại | Retry có làm side effect lặp không? |
| Redelivery sau timeout | Consumer đã ghi DB nhưng chưa acknowledge broker | Broker coi event là chưa xử lý và giao lại |

Một consumer tốt thường phải chịu được cả ba đặc tính cùng lúc. Ví dụ, event version 7 có thể được giao trước version 6, sau đó version 6 được giao lại hai lần. Thiết kế chỉ dựa trên một kỹ thuật duy nhất thường không đủ.

## 3. Event ID và idempotency

Mỗi domain event hoặc integration event cần có một định danh ổn định. eventId đại diện cho chính message instance, không phải cho mỗi lần broker giao message.

Một envelope có thể có dạng:

~~~json
{
  "eventId": "01J...",
  "eventType": "OrderCancelled",
  "aggregateId": "order-123",
  "aggregateVersion": 8,
  "occurredAt": "2026-11-18T10:15:00Z",
  "schemaVersion": 1,
  "correlationId": "checkout-456",
  "causationId": "payment-failed-789"
}
~~~

Nếu broker giao lại cùng event, eventId vẫn giữ nguyên. Consumer có thể lưu những event đã xử lý:

~~~text
processed_message
-----------------------------
consumer_name
event_id
processed_at
result

inventory-service | 01J... | ...
~~~

Khóa duy nhất trên cặp consumer_name + event_id tạo ra một hàng rào đơn giản chống xử lý lặp.

Điểm quan trọng là kiểm tra duplicate phải nằm trong cùng transaction với side effect mà nó bảo vệ khi có thể. Nếu consumer thực hiện:

~~~text
1. kiểm tra eventId chưa tồn tại
2. cập nhật inventory
3. ghi eventId đã xử lý
~~~

mà ba bước không cùng transaction, hai consumer thread có thể cùng thấy event chưa được xử lý và cùng tạo side effect.

Với cơ sở dữ liệu quan hệ, một cách phổ biến là:

~~~text
BEGIN

INSERT INTO processed_message(consumer_name, event_id)
VALUES ('inventory', :eventId)

-- Nếu unique constraint báo duplicate:
-- rollback và coi message đã được xử lý.

UPDATE inventory_item
SET reserved_quantity = reserved_quantity + :quantity
WHERE sku = :sku;

COMMIT
~~~

Nếu insert thành công nhưng update thất bại, transaction rollback và message có thể được retry. Nếu cả insert và update commit, một lần giao lại sẽ bị unique constraint chặn.

Đây là một dạng Inbox pattern. Inbox lưu dấu vết message đã được consumer chấp nhận. Nó đặc biệt hữu ích khi side effect chính nằm trong cùng database transaction với inbox.

## 4. Idempotency không chỉ là kiểm tra eventId

eventId giúp nhận diện cùng một event được giao lại. Nó không giải quyết trường hợp producer tạo hai event khác nhau nhưng cùng thể hiện một nghiệp vụ mà consumer chỉ nên thực hiện một lần.

Ví dụ:

~~~text
eventId=A, OrderCharged(order-123, payment-456)
eventId=B, OrderCharged(order-123, payment-456)
~~~

Hai event có eventId khác nhau nhưng cùng tham chiếu một paymentId. Nếu nghiệp vụ yêu cầu một payment chỉ được ghi nhận một lần, consumer cần bất biến dựa trên paymentId, không chỉ dựa trên eventId.

Có thể cần unique key theo business key:

~~~text
payment_id UNIQUE
~~~

hoặc một command idempotency key:

~~~text
requestId + operationName
~~~

Vì vậy nên phân biệt:

| Cơ chế | Bảo vệ điều gì |
|---|---|
| eventId | Cùng một message được giao lại |
| aggregateId + version | Phiên bản của cùng một aggregate |
| businessId | Một nghiệp vụ chỉ được thực hiện một lần |
| commandId | Cùng một yêu cầu command được retry |

## 5. Version của aggregate là tín hiệu thứ tự tốt hơn thời gian

Timestamp không phải lúc nào cũng thể hiện đúng thứ tự nghiệp vụ. Hai service có clock khác nhau, event có thể nằm trong queue lâu, và một event xảy ra trước có thể được publish sau.

Nếu producer sở hữu aggregate Order, nó có thể tăng version mỗi lần aggregate thay đổi:

~~~text
Order v1 -> OrderPlaced
Order v2 -> AddressChanged
Order v3 -> OrderConfirmed
Order v4 -> OrderCancelled
~~~

Consumer có thể lưu lastProcessedVersion theo aggregate:

~~~text
order-123 -> version 4
~~~

Khi nhận event:

~~~text
event.version <= lastProcessedVersion
    -> event cũ hoặc duplicate, bỏ qua

event.version == lastProcessedVersion + 1
    -> có thể xử lý theo thứ tự

event.version > lastProcessedVersion + 1
    -> đang thiếu event trước đó
~~~

Tuy nhiên, điều kiện version liên tiếp chỉ phù hợp khi consumer thực sự cần xử lý tuần tự toàn bộ event của aggregate. Có những consumer chỉ quan tâm trạng thái cuối cùng. Khi đó nó có thể chấp nhận version 8 dù chưa thấy version 7, miễn là event 8 chứa đủ dữ liệu hoặc consumer có thể lấy trạng thái hiện tại từ nguồn phù hợp.

Do đó version là công cụ để thể hiện thứ tự, còn việc có bắt buộc thứ tự hay không vẫn là quyết định nghiệp vụ và kiến trúc.

## 6. Khi event đến sai thứ tự

Giả sử Inventory nhận:

~~~text
OrderConfirmed v3
OrderPlaced    v1
OrderCancelled v4
~~~

Có ít nhất ba chiến lược.

### Bỏ qua thứ tự

Consumer xử lý event theo thứ tự nhận. Cách này chỉ phù hợp khi mỗi event độc lập và thứ tự không ảnh hưởng đến bất biến.

Ví dụ một consumer dùng event để gửi audit log có thể không cần khôi phục trạng thái chính xác của aggregate.

### Bỏ event cũ

Consumer lưu version mới nhất và bỏ event có version nhỏ hơn hoặc bằng version đã xử lý.

Điều này phù hợp với projection mà mục tiêu là phản ánh trạng thái mới nhất.

Ví dụ:

~~~text
lastVersion = 5
incomingVersion = 3

=> ignore
~~~

Không nên dùng cách này nếu version 3 chứa một side effect bắt buộc phải xảy ra riêng và version 5 không thể thay thế nó.

### Chờ event bị thiếu

Nếu nhận version 5 trong khi đang ở version 3, consumer có thể lưu version 5 vào vùng pending:

~~~text
lastVersion = 3
pending = {4, 5}
~~~

Khi version 4 tới:

~~~text
apply v4
apply v5
lastVersion = 5
~~~

Nếu version 4 không tới trong thời gian cho phép, consumer có thể retry, yêu cầu replay, đọc lại trạng thái từ nguồn, hoặc đưa trường hợp vào dead-letter workflow.

## 7. Không phải event nào cũng cần được xử lý tuần tự

Một sai lầm phổ biến là áp dụng ordering toàn hệ thống chỉ vì một số aggregate cần ordering.

Ví dụ:

~~~text
Order-123:
  v1 -> v2 -> v3 -> v4

Order-456:
  v1 -> v2
~~~

Thông thường chỉ cần bảo vệ thứ tự trong phạm vi aggregate có quan hệ nhân quả. Event của Order-123 không cần chặn event của Order-456.

Nếu broker hỗ trợ partition key, có thể dùng aggregateId làm partition key để các event của cùng aggregate đi vào cùng một partition:

~~~text
partition key = orderId
~~~

Điều này có thể giúp producer giữ thứ tự publish trong partition, nhưng không loại bỏ hoàn toàn nhu cầu idempotency. Consumer vẫn phải chịu được retry, redelivery và các tình huống phục hồi.

## 8. Event đến muộn không nhất thiết là event sai

Event có occurredAt cũ nhưng được xử lý ở thời điểm hiện tại vẫn có thể hoàn toàn hợp lệ.

Ví dụ:

~~~text
10:00  OrderCancelled xảy ra
10:01  PaymentRefundRequested được tạo
10:05  Payment context mới nhận OrderCancelled
~~~

OrderCancelled đến sau năm phút không có nghĩa event đã hết hạn. Consumer phải phân biệt:

- thời điểm nghiệp vụ xảy ra;
- thời điểm message được publish;
- thời điểm message được broker giao;
- thời điểm consumer xử lý.

Một envelope tốt có thể chứa cả occurredAt và metadata phục vụ tracing. Consumer không nên dùng thời gian nhận làm bằng chứng rằng event mới hơn event khác nếu nghiệp vụ yêu cầu thứ tự.

## 9. Event muộn và cửa sổ xử lý

Có những bài toán chấp nhận dữ liệu muộn trong một khoảng thời gian xác định. Ví dụ một reporting context tổng hợp doanh thu theo ngày có thể cho phép dữ liệu của ngày hôm qua cập nhật thêm trong vài phút.

Khi đó cần định nghĩa một processing window:

~~~text
Ngày nghiệp vụ: 2026-11-18
Cho phép event muộn: 30 phút
Đóng sổ: 2026-11-19 00:30
~~~

Sau khi đóng sổ, event đến muộn có thể:

1. cập nhật correction;
2. tạo adjustment;
3. đưa vào quy trình đối soát;
4. bị từ chối nếu nghiệp vụ thực sự không cho phép thay đổi.

Không nên dùng một timeout kỹ thuật để tự quyết định chính sách nghiệp vụ. Cửa sổ chấp nhận event muộn phải xuất phát từ yêu cầu của domain.

## 10. Snapshot và trạng thái hiện tại

Một consumer gặp event version 12 trong khi đang ở version 8 có thể không nhất thiết phải replay version 9, 10 và 11 nếu domain cho phép lấy trạng thái hiện tại từ một nguồn đáng tin cậy.

Ví dụ:

~~~text
Event stream
v1 v2 v3 v4 v5 v6 v7 v8 v9 v10 v11 v12
                     ^
                  consumer
~~~

Consumer có thể:

~~~text
1. phát hiện gap 9..11
2. yêu cầu snapshot hoặc current state
3. cập nhật projection
4. ghi nhận lastVersion = 12
~~~

Điều này phù hợp với read model cần trạng thái hiện tại. Nó không phù hợp nếu mỗi event có một side effect riêng không thể tái tạo từ trạng thái cuối.

## 11. Inbox kết hợp với version check

Trong nhiều hệ thống, một consumer cần cả hai lớp bảo vệ:

~~~text
                 +----------------+
message -------->| Inbox / dedup  |
                 +-------+--------+
                         |
                         v
                 +----------------+
                 | Version check  |
                 +-------+--------+
                         |
                         v
                 +----------------+
                 | Domain update  |
                 +----------------+
~~~

Inbox trả lời:

> Đây có phải cùng một message đã xử lý rồi không?

Version check trả lời:

> Message này có phù hợp với trạng thái phiên bản hiện tại của aggregate không?

Hai câu hỏi khác nhau. Một event mới có thể không duplicate nhưng vẫn đến sai thứ tự. Một event đúng thứ tự có thể vẫn được broker giao lại.

## 12. Mẫu xử lý consumer trong Java

Một consumer đơn giản có thể biểu diễn chính sách version như sau:

~~~java
public final class OrderEventConsumer {

    private final ProcessedMessageRepository inbox;
    private final OrderProjectionRepository projection;

    public void handle(OrderEvent event) {
        if (inbox.exists(event.eventId())) {
            return;
        }

        OrderProjection current =
                projection.findByOrderId(event.orderId());

        if (event.version() <= current.lastVersion()) {
            inbox.markProcessed(event.eventId());
            return;
        }

        if (event.version() > current.lastVersion() + 1) {
            throw new MissingEventException(
                    event.orderId(),
                    current.lastVersion(),
                    event.version()
            );
        }

        apply(event, current);
        projection.save(current.withLastVersion(event.version()));
        inbox.markProcessed(event.eventId());
    }
}
~~~

Ví dụ trên chỉ minh họa ý tưởng. Trong hệ thống thực, projection.save và inbox.markProcessed nên có chiến lược transaction phù hợp. Nếu hai thao tác không nguyên tử, retry có thể xảy ra và apply phải được thiết kế để chịu được retry.

## 13. Optimistic concurrency ở phía consumer

Version cũng có thể được bảo vệ bằng optimistic concurrency:

~~~sql
UPDATE order_projection
SET status = :status,
    last_version = :incomingVersion
WHERE order_id = :orderId
  AND last_version = :expectedVersion;
~~~

Nếu số dòng cập nhật bằng 0, có thể đã có consumer khác cập nhật projection trước đó hoặc message không còn đúng version kỳ vọng.

Đây là cách hữu ích khi một partition có thể được xử lý song song hoặc khi nhiều worker cùng truy cập một projection.

## 14. Retry phải đi cùng idempotency

Retry là cơ chế xử lý lỗi tạm thời, không phải cơ chế đảm bảo message chỉ được xử lý một lần.

Một consumer có thể thất bại vì:

- database tạm thời không truy cập được;
- service downstream timeout;
- network bị ngắt;
- lock contention;
- deployment hoặc restart.

Nếu broker retry message, consumer phải giả định rằng message có thể được giao lại sau khi một phần side effect đã thành công.

Ví dụ nguy hiểm:

~~~text
1. Gọi Payment Provider: charge thành công
2. Database timeout
3. Consumer throw exception
4. Broker retry
5. Charge lại
~~~

Ở đây idempotency phải được thiết kế ở boundary của thao tác thanh toán. Có thể dùng paymentId hoặc idempotency key mà Payment Provider hỗ trợ.

Nguyên tắc là:

> Mọi side effect có thể bị retry phải có cách nhận biết hoặc hấp thụ việc retry.

## 15. Dead Letter không phải nơi vứt bỏ nghiệp vụ

Khi event không thể xử lý sau một số lần retry, hệ thống có thể đưa message vào Dead Letter Queue. Nhưng DLQ chỉ là cơ chế vận hành; nó không quyết định ý nghĩa nghiệp vụ.

Một workflow tốt có thể là:

~~~text
Broker
  |
  v
Consumer
  |
  +-- success ------------------> ACK
  |
  +-- transient failure --------> retry
  |
  +-- missing version ----------> wait/replay
  |
  +-- permanent invalid --------> DLQ + alert
~~~

Ví dụ event có schema không hợp lệ có thể cần DLQ và alert. Event version 10 đến trước version 9 thì chưa chắc nên đưa thẳng vào DLQ; có thể chỉ đang thiếu message.

## 16. Poison message và retry vô hạn

Một message luôn thất bại vì dữ liệu sai có thể tạo vòng lặp:

~~~text
consume -> fail -> retry -> fail -> retry -> ...
~~~

Retry policy nên có giới hạn và phân biệt lỗi tạm thời với lỗi cố định.

| Loại lỗi | Cách xử lý |
|---|---|
| Timeout database | Retry với backoff |
| Service downstream unavailable | Retry có giới hạn |
| Duplicate event | Acknowledge và bỏ qua |
| Version bị thiếu | Chờ/replay |
| Schema không hợp lệ | DLQ |
| Business rule bị vi phạm do dữ liệu | DLQ hoặc workflow nghiệp vụ |

Backoff giúp giảm áp lực lên hệ thống khi downstream đang gặp sự cố. Nhưng backoff không thay thế idempotency.

## 17. Correlation ID và Causation ID

Khi một event gây ra nhiều event khác, việc điều tra duplicate hoặc ordering sẽ dễ hơn nếu message giữ quan hệ nhân quả.

Ví dụ:

~~~text
PlaceOrder command
    |
    +--> OrderPlaced event
             |
             +--> InventoryReserved event
             |
             +--> PaymentAuthorized event
~~~

correlationId có thể nối toàn bộ workflow. causationId cho biết message hiện tại được tạo bởi message nào.

Điều này không giải quyết ordering, nhưng giúp quan sát và chẩn đoán:

~~~text
correlationId = checkout-123

OrderPlaced
  eventId = e1

InventoryReserved
  eventId = e2
  causationId = e1

PaymentAuthorized
  eventId = e3
  causationId = e1
~~~

## 18. Phân biệt domain event và integration event

Domain event mô tả một sự kiện có ý nghĩa trong một Bounded Context. Integration event là thông điệp được thiết kế để context khác có thể hiểu và sử dụng.

Ví dụ domain model có thể có:

~~~text
OrderConfirmed
~~~

Integration contract có thể là:

~~~json
{
  "type": "OrderConfirmed",
  "orderId": "order-123",
  "confirmedAt": "2026-11-18T10:15:00Z",
  "version": 3
}
~~~

Consumer không nên phụ thuộc vào mọi chi tiết nội bộ của aggregate. Contract nên chứa đủ dữ liệu để consumer thực hiện trách nhiệm của nó và duy trì bất biến của context đó.

## 19. Không dùng distributed transaction để chữa mọi vấn đề

Khi hai context cần cùng commit một transaction, phản xạ đầu tiên thường là cố gắng mở transaction xuyên qua cả hai context. Điều này làm coupling tăng mạnh và làm giảm lợi ích của bounded context.

Một lựa chọn thường phù hợp hơn là:

~~~text
Context A
  |
  | local transaction
  v
Domain change + Outbox
  |
  v
Message Broker
  |
  v
Context B
  |
  | local transaction
  v
Inbox + Domain change
~~~

Outbox bảo đảm việc thay đổi dữ liệu và ghi message để publish thuộc cùng local transaction. Inbox giúp consumer xử lý redelivery an toàn. Hai pattern kết hợp tạo thành một đường đi thực tế cho eventual consistency.

## 20. Saga và thông điệp đến không đúng thứ tự

Một quy trình dài qua nhiều context có thể được mô hình hóa bằng Saga hoặc Process Manager. Khi đó ordering không chỉ là vấn đề của một aggregate mà còn là vấn đề của workflow.

Ví dụ:

~~~text
OrderPlaced
    |
    v
ReserveInventory
    |
    v
AuthorizePayment
    |
    v
ConfirmOrder
~~~

Nếu PaymentAuthorized đến sau OrderCancelled, Process Manager phải có state riêng để biết workflow đang ở đâu và quyết định phản ứng.

Không nên giả định broker sẽ luôn giao message theo đúng thứ tự business process. Process Manager cần biểu diễn trạng thái workflow và các điều kiện chuyển trạng thái.

## 21. State machine cho workflow

Một Process Manager có thể có trạng thái:

~~~text
WAITING_FOR_INVENTORY
WAITING_FOR_PAYMENT
COMPLETED
CANCELLED
~~~

Khi event đến:

~~~text
WAITING_FOR_PAYMENT + PaymentAuthorized
    -> COMPLETED

COMPLETED + PaymentAuthorized duplicate
    -> ignore

CANCELLED + PaymentAuthorized late
    -> compensation hoặc ignore theo policy
~~~

Điểm quan trọng là transition phải được định nghĩa theo nghiệp vụ. Không phải event đến muộn nào cũng là lỗi kỹ thuật.

## 22. Command và event có yêu cầu khác nhau

Command thường có một người gửi yêu cầu và một nơi chịu trách nhiệm quyết định có thực hiện hay không. Event mô tả điều đã xảy ra.

Với command:

~~~text
CancelOrder(commandId=cmd-1, orderId=order-123)
~~~

Consumer hoặc application service có thể lưu commandId để bảo đảm cùng command được retry mà không thực hiện hai lần.

Với event:

~~~text
OrderCancelled(eventId=evt-1, aggregateVersion=4)
~~~

Consumer quan tâm event đã xử lý chưa và event có phù hợp với version hiện tại hay không.

Không nên dùng một trường duy nhất để xử lý mọi loại message.

## 23. Khi nào nên lưu toàn bộ Inbox

Inbox không nhất thiết phải tồn tại vĩnh viễn. Retention phụ thuộc vào khả năng replay của hệ thống và thời gian broker có thể redeliver message.

Nếu duplicate có thể xuất hiện sau nhiều ngày do replay, việc xóa Inbox quá sớm có thể khiến consumer xử lý lại side effect.

Do đó cần trả lời:

1. Message có thể được replay trong bao lâu?
2. Side effect có thể được gọi lại an toàn không?
3. Business key có cung cấp thêm một lớp idempotency không?
4. Có cần audit lịch sử xử lý không?

Nếu side effect là tài chính hoặc nghiệp vụ không thể đảo ngược, retention và audit thường cần chặt chẽ hơn.

## 24. Khi nào không nên deduplicate bằng thời gian

Một cách dễ nhưng nguy hiểm là lưu eventId trong cache với TTL ngắn:

~~~text
eventId -> Redis TTL 5 minutes
~~~

Nếu broker redeliver sau 6 phút, consumer không còn thấy eventId và có thể thực hiện side effect lần nữa.

TTL chỉ phù hợp khi nghiệp vụ cho phép duplicate sau khoảng thời gian đó hoặc khi side effect đã có idempotency riêng. Với bất biến quan trọng, nên dùng storage và retention dựa trên yêu cầu nghiệp vụ.

## 25. Ordering và partitioning

Nếu broker hỗ trợ partition, một chiến lược phổ biến là:

~~~text
partitionKey = aggregateId
~~~

Khi đó:

~~~text
Order-123 -> partition 4
Order-456 -> partition 7
Order-789 -> partition 4
~~~

Các event của cùng aggregate có thể được xử lý tuần tự trong partition, trong khi các aggregate khác vẫn chạy song song.

Nhưng partitioning không đảm bảo mọi thứ:

- retry có thể làm message được giao lại;
- consumer restart có thể thay đổi thời điểm xử lý;
- event từ các producer khác nhau có thể không có cùng ordering domain;
- một workflow có nhiều aggregate vẫn có thể cần Process Manager.

Vì vậy ordering ở broker chỉ là một phần của thiết kế. Bất biến vẫn phải được bảo vệ ở consumer.

## 26. Multi aggregate không có một version duy nhất

Giả sử Payment và Order là hai aggregate độc lập:

~~~text
Order v10
Payment v7
~~~

Không có một aggregateVersion chung để nói event nào toàn cục mới hơn. OrderConfirmed và PaymentAuthorized có thể được tạo độc lập.

Không nên cố ghép hai version thành một thứ tự toàn cục giả tạo. Nếu nghiệp vụ yêu cầu một chuỗi hành động, hãy biểu diễn chuỗi đó bằng workflow hoặc process state.

## 27. Read model có thể chấp nhận eventual consistency

Một trang dashboard có thể hiển thị:

~~~text
Đơn hàng: Đã xác nhận
Tồn kho: Đang cập nhật
~~~

Điều này có thể chấp nhận nếu người dùng được thông báo rõ và thao tác quan trọng vẫn kiểm tra dữ liệu authoritative tại context sở hữu.

Read model không nên trở thành nguồn sự thật chỉ vì nó cập nhật nhanh hơn. Mỗi context cần biết dữ liệu nào là authoritative và dữ liệu nào chỉ là projection.

## 28. Khi event bị mất

Duplicate và out-of-order thường được nhắc đến nhiều hơn lost message, nhưng consumer cũng cần có cách phát hiện hoặc phục hồi gap.

Nếu consumer nhận:

~~~text
v1
v2
v4
~~~

thì lastVersion=4 mà không phát hiện thiếu v3 có thể tạo ra projection sai.

Các cơ chế phục hồi có thể gồm:

- broker retention để replay;
- event store;
- snapshot;
- API đọc trạng thái authoritative;
- reconciliation job;
- đối soát định kỳ.

Một hệ thống đáng tin cậy cần có đường phục hồi khi message bị mất hoặc consumer đã xử lý sai.

## 29. Reconciliation là lớp bảo vệ cuối

Không nên giả định mọi consumer đều luôn đúng. Một reconciliation process có thể định kỳ so sánh projection với source of truth:

~~~text
Authoritative Context
        |
        | compare
        v
Read Model
        |
        v
Mismatch detected
        |
        +--> replay
        +--> rebuild
        +--> correction
~~~

Reconciliation đặc biệt hữu ích cho các context có dữ liệu quan trọng nhưng không yêu cầu transaction đồng bộ.

## 30. Kiểm thử duplicate, late và out-of-order

Một consumer có logic idempotency cần test các tình huống mà happy path không thể chứng minh.

Ví dụ:

~~~text
Given lastVersion = 3

When v4 arrives
Then projection becomes v4

When v4 arrives again
Then projection remains v4
And side effect is not repeated

When v6 arrives before v5
Then v6 is buffered or rejected according to policy

When v5 arrives
Then v5 and v6 are applied in valid order
~~~

Nên có test riêng cho:

| Tình huống | Kỳ vọng |
|---|---|
| Cùng eventId hai lần | Side effect một lần |
| Hai event khác eventId nhưng cùng business key | Bất biến nghiệp vụ vẫn được bảo vệ |
| Version cũ | Ignore hoặc xử lý theo policy |
| Version tương lai | Buffer/retry/reject theo policy |
| Retry sau DB failure | Không tạo side effect kép |
| Event schema không hợp lệ | DLQ hoặc error workflow |
| Consumer restart giữa transaction | Có thể tiếp tục an toàn |

## 31. Một ví dụ đầy đủ

Giả sử Order Management phát:

~~~text
OrderPlaced       v1
OrderConfirmed    v2
OrderCancelled    v3
~~~

Inventory nhận theo thứ tự:

~~~text
OrderConfirmed v2
OrderPlaced v1
OrderPlaced v1
OrderCancelled v3
~~~

Consumer có thể xử lý như sau:

~~~text
v2 arrives
  lastVersion=0
  gap detected
  -> pending v2

v1 arrives
  lastVersion=0
  -> apply v1
  -> lastVersion=1
  -> apply pending v2
  -> lastVersion=2

v1 arrives again
  -> eventId already processed
  -> ignore

v3 arrives
  -> apply cancellation
  -> release reservation
  -> lastVersion=3
~~~

Nếu cancellation release được gọi tới một service khác, thao tác release cũng phải có idempotency key. Bảo vệ ở Inbox của Inventory không tự động bảo vệ side effect bên ngoài.

## 32. Thiết kế message envelope

Một envelope thực dụng có thể chứa:

~~~text
eventId
eventType
schemaVersion
aggregateType
aggregateId
aggregateVersion
occurredAt
correlationId
causationId
producer
payload
~~~

Không phải hệ thống nào cũng cần mọi trường. Nhưng những trường này thường trả lời được các câu hỏi vận hành quan trọng:

- Đây là message nào?
- Nó thuộc aggregate nào?
- Phiên bản nghiệp vụ nào?
- Nó xảy ra khi nào?
- Nó được tạo bởi message nào?
- Nó thuộc workflow nào?
- Producer nào phát ra?

## 33. Chọn chiến lược theo loại consumer

Không có một chiến lược ordering chung cho mọi consumer.

| Consumer | Thường cần gì |
|---|---|
| Audit log | Có thể chấp nhận out-of-order |
| Search index | Thường cần trạng thái cuối |
| Projection UI | Version check và bỏ event cũ |
| Inventory reservation | Idempotency + bất biến + ordering theo aggregate nếu cần |
| Payment | Idempotency business key rất quan trọng |
| Analytics | Có thể cần event-time và xử lý late event |
| Process Manager | State machine + correlation + compensation |

Thiết kế consumer từ trách nhiệm domain giúp tránh việc áp dụng một cơ chế nặng cho mọi nơi.

## 34. Quy trình thiết kế

Khi một Bounded Context tiêu thụ event từ context khác, có thể đi theo quy trình:

~~~text
1. Xác định source of truth
        |
2. Xác định bất biến của consumer
        |
3. Xác định event có cần ordering không
        |
4. Chọn identity: eventId, businessId, aggregateVersion
        |
5. Thiết kế inbox/dedup
        |
6. Thiết kế xử lý gap và event muộn
        |
7. Thiết kế retry và DLQ
        |
8. Thiết kế replay/reconciliation
        |
9. Kiểm thử duplicate + late + out-of-order
        |
10. Quan sát và đo lường production
~~~

## 35. Các chỉ số vận hành nên theo dõi

Khi message consistency quan trọng, metrics nên phản ánh cả độ trễ và lỗi ordering:

| Metric | Ý nghĩa |
|---|---|
| Consumer lag | Consumer đang chậm bao nhiêu |
| Duplicate rate | Có bao nhiêu message bị giao lại |
| Gap count | Có bao nhiêu aggregate đang thiếu version |
| Pending event count | Có bao nhiêu event đang chờ event trước |
| DLQ count | Có bao nhiêu message không xử lý được |
| Processing latency | Event mất bao lâu từ nhận đến commit |
| Replay count | Có bao nhiêu lần phải phục hồi |

Các metric này giúp phân biệt lỗi ứng dụng với đặc tính bình thường của hệ thống phân tán.

## 36. Những sai lầm thường gặp

### Chỉ dùng timestamp để quyết định mới/cũ

Clock và delivery delay khiến timestamp nhận không phản ánh thứ tự nghiệp vụ.

### Chỉ deduplicate bằng eventId

Điều này không bảo vệ business key hoặc side effect được tạo từ hai event khác nhau.

### Cho rằng broker exactly-once giải quyết toàn bộ

Exactly-once ở một lớp vận chuyển không tự động làm cho side effect bên ngoài idempotent.

### Đưa mọi out-of-order event vào DLQ

Event đến sớm có thể chỉ đang chờ event trước đó.

### Retry vô hạn

Poison message có thể làm consumer bị kẹt và che khuất các message hợp lệ.

### Ép tất cả context dùng một transaction

Điều này làm mất ranh giới ownership và tăng coupling giữa context.

### Không có replay hoặc reconciliation

Khi projection sai, hệ thống không có cách phục hồi đáng tin cậy.

### Không xác định source of truth

Khi dữ liệu giữa hai context khác nhau, không biết context nào authoritative sẽ khiến việc sửa sai trở thành tranh luận thay vì quy tắc rõ ràng.

## 37. Checklist

Trước khi đưa một integration flow vào production, hãy trả lời:

- Event có eventId ổn định không?
- Event có identity của aggregate hoặc business operation cần thiết không?
- Consumer có idempotent không?
- Duplicate có thể xuất hiện sau thời gian bao lâu?
- Inbox có retention phù hợp không?
- Event có cần xử lý đúng thứ tự không?
- Nếu cần ordering, ordering được xác định bằng gì?
- Consumer làm gì khi gặp gap?
- Consumer làm gì khi event đến muộn?
- Event cũ có thể bỏ qua không?
- Side effect bên ngoài có idempotency riêng không?
- Retry có backoff và giới hạn không?
- Poison message được xử lý thế nào?
- DLQ có quy trình xử lý không?
- Có replay hoặc reconciliation không?
- Projection có source of truth rõ ràng không?
- Có metrics cho lag, duplicate, gap và DLQ không?
- Test có bao phủ duplicate, retry, late và out-of-order không?

## 38. Kết luận

Nhất quán liên ngữ cảnh là bài toán quản lý bất biến và trách nhiệm giữa các Bounded Context trong một hệ thống phân tán. Message có thể lặp, đến muộn hoặc sai thứ tự vì retry, broker, partition, consumer restart và nhiều nguyên nhân vận hành khác. Thiết kế tốt bắt đầu từ yêu cầu nghiệp vụ: context nào sở hữu sự thật, bất biến nào cần bảo vệ và mức nhất quán nào đủ cho use case.

Từ đó, eventId và Inbox xử lý redelivery; business key bảo vệ những nghiệp vụ phải thực hiện một lần; aggregate version giúp phát hiện event cũ hoặc gap; buffering, replay và snapshot xử lý trường hợp thiếu thứ tự; retry và DLQ tạo đường phục hồi; reconciliation giúp sửa projection khi có sai lệch. Các cơ chế này nên được kết hợp theo trách nhiệm của từng consumer thay vì áp dụng một chính sách giống nhau cho toàn hệ thống.

Mục tiêu cuối cùng là để mỗi Bounded Context có thể tiến hóa độc lập nhưng vẫn giữ được các cam kết nghiệp vụ cần thiết khi giao tiếp với những context khác.
