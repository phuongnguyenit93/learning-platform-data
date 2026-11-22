# Sự kiện tích hợp

Trong ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL) dùng để tích hợp ứng dụng, **sự kiện tích hợp (integration event)** là thông điệp mô tả một điều đã xảy ra trong một hệ thống và được công bố để hệ thống khác có thể phản ứng. Ví dụ, khi một đơn hàng được xác nhận, dịch vụ Order có thể phát sự kiện OrderConfirmed; dịch vụ Inventory nhận sự kiện để giữ hàng, dịch vụ Notification gửi thông báo và hệ thống Analytics cập nhật dữ liệu báo cáo.

Sự kiện tích hợp giúp các ứng dụng phối hợp mà không cần biết chi tiết triển khai của nhau. Producer chỉ công bố một sự kiện theo hợp đồng đã thống nhất; consumer đăng ký nhận và xử lý sự kiện đó. Một message broker, event bus, webhook gateway hoặc nền tảng streaming có thể vận chuyển thông điệp giữa các bên.

Trong DSL, sự kiện tích hợp có thể được khai báo như một phần của contract, routing rule, subscription, transformation hoặc workflow. DSL cần định nghĩa rõ tên và schema của event, nguồn phát, nơi nhận, cách serialize, delivery guarantee, ordering, retry, idempotency, bảo mật và cách xử lý lỗi. Nếu chỉ mô tả một event name mà không có semantics vận chuyển và xử lý, hệ thống tích hợp sẽ khó dự đoán khi xảy ra mất kết nối, gửi trùng hoặc thay đổi schema.

Ví dụ khái quát:

~~~text
event OrderConfirmed {
    version = 1
    data {
        orderId: UUID
        customerId: UUID
        total: Money<VND>
        confirmedAt: Instant
    }
}

publish OrderConfirmed to topic("orders.confirmed")

subscribe InventoryService to OrderConfirmed {
    handle reserveItems
}
~~~

Ví dụ minh họa này cho thấy producer công bố một sự kiện có schema và consumer đăng ký xử lý. Cú pháp thực tế tùy DSL, nhưng hợp đồng sự kiện và hành vi khi vận chuyển phải được xác định nhất quán.

## 1. Sự kiện tích hợp là gì?

Sự kiện tích hợp là một thông điệp hướng đến hệ thống khác, biểu đạt một sự kiện nghiệp vụ hoặc kỹ thuật đã xảy ra. Nó thường được phát sau khi một thay đổi đã được chấp nhận trong hệ thống nguồn.

### 1.1. Event mô tả điều đã xảy ra

Tên event thường dùng dạng quá khứ như OrderPlaced, PaymentAuthorized hoặc CustomerAddressChanged. Tên gọi thể hiện một sự thật đã xảy ra, không phải yêu cầu hệ thống khác làm điều gì.

### 1.2. Event mang dữ liệu cần thiết

Payload có thể chứa ID thực thể, trạng thái, thời điểm, số tiền hoặc dữ liệu cần để consumer phản ứng. Chỉ nên đưa những trường cần thiết cho hợp đồng tích hợp; tránh gửi toàn bộ database record một cách tùy tiện.

### 1.3. Event có producer và consumer

Producer tạo và phát event. Consumer nhận event và thực hiện xử lý. Một event có thể có nhiều consumer độc lập, và producer thường không cần biết danh sách consumer cụ thể.

### 1.4. Event có contract

Contract định nghĩa event name, version, schema, semantics, compatibility policy và metadata. Contract là thỏa thuận giữa producer và consumer; thay đổi contract có thể ảnh hưởng nhiều hệ thống.

### 1.5. Event có lifecycle

Một event có thể được tạo, serialize, publish, lưu trong broker, deliver, xử lý, retry, chuyển vào dead-letter queue hoặc hết hạn theo retention policy. DSL và nền tảng vận hành cần làm rõ từng giai đoạn.

## 2. Phân biệt event, command, query và notification

Các loại message thường được dùng trong tích hợp nhưng mang ý nghĩa khác nhau.

| Loại message | Ý nghĩa | Ví dụ |
|---|---|---|
| Event | Một điều đã xảy ra | OrderConfirmed |
| Command | Yêu cầu một hành động | ReserveInventory |
| Query | Yêu cầu dữ liệu | GetOrderStatus |
| Notification | Thông báo cho người nhận | SendDeliveryEmail |
| Reply | Kết quả trả lời request | InventoryReserved |

### 2.1. Event

Event là sự thật được công bố. Producer không yêu cầu một consumer cụ thể phải thực hiện hành động nào. Nhiều consumer có thể phản ứng theo nhu cầu riêng.

### 2.2. Command

Command diễn đạt ý định hoặc yêu cầu thực hiện hành động. Nó thường có một handler chịu trách nhiệm và có thể bị từ chối. Ví dụ ReserveInventory là yêu cầu giữ hàng, còn InventoryReserved là sự kiện cho biết thao tác đã thành công.

### 2.3. Query

Query yêu cầu thông tin và thường không làm thay đổi trạng thái nghiệp vụ. Query thường cần response trực tiếp, trong khi event có thể được phát bất đồng bộ.

### 2.4. Notification

Notification tập trung vào việc báo cho người nhận biết một điều. Trong một số hệ thống, notification cũng chính là event; trong hệ thống khác, notification là message được tạo từ event để phục vụ một kênh cụ thể.

### 2.5. Không dùng event để giả dạng command

Tên như PleaseShipOrder hoặc DoPayment nghe giống yêu cầu hành động. Nếu producer muốn consumer thực hiện một thao tác, command thường diễn đạt đúng hơn. Event nên phản ánh trạng thái hoặc sự kiện đã được xác nhận.

### 2.6. Request/reply và event-driven

Request/reply phù hợp khi caller cần câu trả lời trong một tương tác. Event-driven phù hợp khi producer muốn công bố thay đổi để một hoặc nhiều consumer xử lý độc lập. Hai kiểu có thể cùng tồn tại trong một kiến trúc.

## 3. Vai trò của sự kiện trong tích hợp ứng dụng

Sự kiện tạo ra một cách kết nối các ứng dụng theo hợp đồng và phản ứng với thay đổi.

### 3.1. Giảm coupling giữa ứng dụng

Producer chỉ cần biết event contract và nơi publish. Nó không phải gọi trực tiếp từng consumer hoặc phụ thuộc vào API nội bộ của chúng.

### 3.2. Hỗ trợ nhiều consumer

Một sự kiện OrderConfirmed có thể được Inventory, Billing, Notification và Analytics sử dụng. Thêm consumer mới không nhất thiết yêu cầu sửa producer nếu contract vẫn đáp ứng nhu cầu.

### 3.3. Xử lý bất đồng bộ

Producer có thể tiếp tục sau khi broker xác nhận đã nhận thông điệp, còn consumer xử lý sau. Điều này giúp hấp thụ tải và tách thời gian hoạt động của các ứng dụng.

### 3.4. Mở rộng theo nhu cầu

Consumer có thể tăng số worker hoặc partition để xử lý nhiều event hơn. Việc mở rộng phải tôn trọng ordering, partition key và giới hạn của hệ thống đích.

### 3.5. Đồng bộ dữ liệu giữa hệ thống

Event có thể cập nhật read model, search index, data warehouse hoặc cache. Consumer cần xử lý event trùng, đến sai thứ tự và phát lại.

### 3.6. Tạo audit trail

Event được lưu với thời điểm và nguồn có thể hỗ trợ truy vết thay đổi. Tuy nhiên, retention, dữ liệu cá nhân và quyền truy cập cần được kiểm soát.

### 3.7. Điều phối quy trình dài

Một chuỗi event và command có thể phối hợp quy trình nhiều bước như đặt hàng, thanh toán, giao hàng và hoàn tiền. Saga hoặc workflow engine có thể quản lý tiến trình và compensation.

## 4. Mô hình event-driven integration

Trong mô hình event-driven, các hệ thống trao đổi event thông qua một kênh trung gian hoặc giao thức trực tiếp.

~~~mermaid
flowchart LR
    A[Order Service] -->|OrderConfirmed| B[Event Broker]
    B --> C[Inventory Service]
    B --> D[Notification Service]
    B --> E[Analytics Service]
    C --> F[Inventory Store]
    D --> G[Email or SMS Provider]
    E --> H[Analytics Store]
~~~

### 4.1. Producer

Producer là ứng dụng hoặc thành phần phát event. Nó xác định thời điểm nghiệp vụ đã xảy ra và tạo payload theo schema.

### 4.2. Event channel

Channel có thể là topic, queue, stream, exchange hoặc webhook endpoint. Mỗi loại có semantics routing, retention và delivery khác nhau.

### 4.3. Broker hoặc event bus

Broker nhận, lưu tạm, định tuyến và phân phối message. Event bus có thể cung cấp routing theo topic, type hoặc attribute.

### 4.4. Consumer

Consumer đăng ký một hoặc nhiều event type, xác thực envelope, xử lý payload và ghi nhận kết quả. Consumer có thể là service, worker, function hoặc integration adapter.

### 4.5. Schema registry

Schema registry lưu schema và metadata version. Producer và consumer có thể kiểm tra compatibility trước khi publish hoặc deploy.

### 4.6. Observability

Tracing, metrics và logs liên kết event với request gốc, producer, broker và consumer. Correlation ID giúp theo dõi một quy trình qua nhiều ứng dụng.

## 5. Cấu trúc của một event message

Một event message thường có envelope chứa metadata và payload chứa dữ liệu nghiệp vụ.

### 5.1. Event envelope

Envelope có thể gồm:

- Event ID duy nhất.
- Event type hoặc subject.
- Schema version.
- Source hoặc producer identity.
- Timestamp.
- Content type và encoding.
- Correlation ID và causation ID.
- Partition key hoặc aggregate ID.
- Tenant hoặc routing metadata khi cần.
- Payload data.

### 5.2. Payload

Payload chứa dữ liệu mô tả sự kiện. Ví dụ OrderConfirmed có orderId, customerId, total và confirmedAt. Payload nên có kiểu rõ và đơn vị tường minh.

### 5.3. Metadata tách khỏi payload

Event ID, source, type và timestamp thường thuộc envelope. Dữ liệu nghiệp vụ thuộc payload. Tách hai phần giúp broker và middleware định tuyến mà không cần hiểu toàn bộ domain model.

### 5.4. Event ID

Event ID giúp consumer nhận diện một lần phát cụ thể và hỗ trợ deduplication. ID cần ổn định khi cùng một event được retry hoặc phát lại.

### 5.5. Timestamp

Timestamp có thể là thời điểm nghiệp vụ xảy ra hoặc thời điểm message được tạo. Nên phân biệt occurredAt và publishedAt nếu cả hai có ý nghĩa.

### 5.6. Source

Source nhận diện hệ thống hoặc instance tạo event. Dùng URI, service identity hoặc namespace ổn định theo contract.

### 5.7. Correlation và causation

Correlation ID liên kết các message cùng một quy trình hoặc request. Causation ID chỉ ra message hoặc event đã gây ra message hiện tại. Hai trường này hữu ích khi một event kích hoạt command rồi tạo event tiếp theo.

### 5.8. Content type

Content type cho biết payload dùng JSON, Avro, Protobuf hoặc format khác. Consumer cần kiểm tra đúng format trước khi deserialize.

## 6. Khai báo event trong DSL

DSL có thể định nghĩa event như một type có version, schema và metadata.

~~~text
event CustomerRegistered {
    version = 1
    description = "Khách hàng mới đã được đăng ký"

    data {
        customerId: UUID
        email: EmailAddress
        registeredAt: Instant
        sourceChannel: RegistrationChannel
    }
}
~~~

### 6.1. Tên event

Tên nên mô tả sự kiện nghiệp vụ rõ ràng, ổn định và thường dùng thì quá khứ. Tránh đưa chi tiết triển khai như tên class hoặc tên database table vào event contract.

### 6.2. Event namespace

Có thể nhóm event theo bounded context hoặc domain, ví dụ sales.order.OrderConfirmed. Namespace tránh trùng tên và giúp quản lý quyền publish/subscribe.

### 6.3. Event version

Version xác định schema và semantics. Tăng version khi thay đổi không tương thích hoặc khi policy của hệ thống yêu cầu quản lý phiên bản tường minh.

### 6.4. Data schema

Schema mô tả field, type, required status, nullability, default và constraint. Schema cần đủ rõ để producer và consumer hiểu cùng một payload.

### 6.5. Field semantics

Ngoài kiểu, field nên có ý nghĩa và đơn vị. total có thể là Money<VND>; occurredAt có thể là Instant theo UTC. Không dùng một số thập phân không rõ đơn vị cho giá trị tiền tệ.

### 6.6. Sensitive field

Đánh dấu field chứa dữ liệu cá nhân hoặc bí mật để áp dụng encryption, masking, access policy và retention phù hợp. Không đưa credential vào event payload.

### 6.7. Ownership

Mỗi event contract nên có owner chịu trách nhiệm về semantics, version và thông báo thay đổi. Ownership giúp consumer biết nơi trao đổi khi contract thay đổi.

## 7. Đặt tên và thiết kế event contract

Event contract nên thể hiện sự thật nghiệp vụ và giữ ổn định khi implementation thay đổi.

### 7.1. Dùng tên có ý nghĩa nghiệp vụ

OrderConfirmed mô tả sự kiện nghiệp vụ. OrderRowUpdated hoặc SaveOrderResult thường phản ánh chi tiết kỹ thuật hơn là sự thật miền.

### 7.2. Tránh tên quá chung

Event như Updated hoặc Changed không nói rõ thực thể và hành động. Tên nên có domain context hoặc namespace.

### 7.3. Event bất biến

Sau khi phát hành, event nên được xem là immutable. Không sửa message cũ tại broker để phản ánh trạng thái mới; hãy phát event mới hoặc correction event theo contract.

### 7.4. Chỉ công bố sự thật đã xảy ra

Không phát OrderConfirmed trước khi transaction xác nhận đơn hàng thành công. Nếu phát trước rồi database rollback, consumer sẽ nhận một sự thật không tồn tại.

### 7.5. Payload vừa đủ

Payload có thể là event notification chỉ chứa ID hoặc event-carried state transfer chứa một snapshot cần thiết. Chọn theo nhu cầu consumer, coupling và yêu cầu bảo mật.

### 7.6. Không sao chép toàn bộ database entity

Database schema có thể thay đổi vì lý do nội bộ. Event contract nên là public integration model được thiết kế độc lập với persistence model.

### 7.7. Tránh field mơ hồ

Các tên value, status hoặc date cần có semantics cụ thể. Dùng currency, unit, timezone và enum rõ ràng.

### 7.8. Giữ ý nghĩa ổn định

Một field không nên đổi nghĩa nhưng giữ nguyên tên và kiểu. Nếu semantics thay đổi, cần version hoặc event type mới để consumer không diễn giải sai.

## 8. Publish event từ producer

Producer phát event sau khi xác định sự kiện nghiệp vụ đã xảy ra và tạo message theo contract.

### 8.1. Xác định thời điểm phát

Event nên được phát tại ranh giới nghiệp vụ phù hợp, chẳng hạn sau khi đơn hàng chuyển sang trạng thái confirmed. Thời điểm này cần nhất quán với transaction và state transition.

### 8.2. Serialize

Producer chuyển event object thành byte theo content type đã thống nhất. Serialization cần kiểm tra schema và không để field không hợp lệ lọt vào message.

### 8.3. Chọn channel

Topic hoặc routing key được chọn theo event type, domain hoặc partition strategy. Tránh hardcode địa chỉ broker trong logic nghiệp vụ nếu DSL có cấu hình endpoint riêng.

### 8.4. Publish acknowledgement

Producer có thể chờ broker xác nhận đã nhận message. Acknowledgement của broker không nhất thiết có nghĩa consumer đã xử lý xong.

### 8.5. Retry publish

Khi publish timeout, producer có thể không biết broker đã nhận message hay chưa. Retry có thể tạo duplicate; event ID và consumer idempotency giúp xử lý trường hợp này.

### 8.6. Transactional outbox

Nếu cập nhật database và publish event cần nhất quán, producer có thể ghi business state và outbox record trong cùng transaction. Một relay đọc outbox rồi publish message. Cơ chế này giảm nguy cơ database commit nhưng event bị mất.

### 8.7. Không publish trước commit

Nếu publish thành công nhưng transaction nghiệp vụ rollback, consumer có thể xử lý dữ liệu không tồn tại. Outbox hoặc transaction integration phù hợp giúp đồng bộ hai hành động.

### 8.8. Producer responsibility

Producer chịu trách nhiệm phát event đúng contract, gắn metadata, không lộ secret và bảo đảm event phản ánh một sự thật đã được xác nhận.

## 9. Subscribe và xử lý event ở consumer

Consumer nhận event, kiểm tra hợp đồng rồi thực hiện xử lý phù hợp.

### 9.1. Subscription

Subscription xác định event type, channel, filter, consumer group và delivery options. Một consumer có thể đăng ký nhiều event type.

### 9.2. Deserialize và validate

Consumer xác minh content type, schema version và required field trước khi xử lý. Không tin mọi message chỉ vì nó đến từ broker nội bộ.

### 9.3. Handler

Handler thực hiện nghiệp vụ tương ứng. Nên tách việc nhận message khỏi logic domain để có thể kiểm thử handler độc lập.

### 9.4. Acknowledgement

Consumer xác nhận message đã xử lý theo semantics của broker. Với một số broker, ack có nghĩa message có thể được loại khỏi queue; với streaming platform, offset được commit.

### 9.5. Consumer group

Consumer group cho phép nhiều worker chia nhau xử lý partition hoặc message. Semantics phân phối và ordering tùy nền tảng.

### 9.6. Consumer lifecycle

Consumer cần xử lý startup, reconnect, graceful shutdown, rebalance và drain message đang xử lý. Dừng process đột ngột có thể khiến message được giao lại.

### 9.7. Handler failure

Nếu handler thất bại, consumer cần policy retry, nack, requeue hoặc dead-letter. Không ack trước khi side effect quan trọng được ghi nhận thành công.

### 9.8. Consumer ownership

Mỗi subscription nên có owner và mục đích rõ. Điều này hỗ trợ quản lý quyền, capacity và thay đổi schema.

## 10. Đồng bộ và bất đồng bộ

Integration event thường được xử lý bất đồng bộ, nhưng DSL có thể hỗ trợ nhiều delivery style.

| Kiểu | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Synchronous call | Caller chờ response | Cần kết quả ngay |
| Asynchronous event | Producer phát, consumer xử lý sau | Không cần chờ từng consumer |
| Webhook | Hệ thống gửi HTTP callback | Tích hợp với đối tác |
| Streaming | Consumer đọc liên tục từ log/stream | Dữ liệu liên tục hoặc throughput cao |
| Queue-based work | Message được worker lấy xử lý | Công việc nền và task distribution |

### 10.1. Synchronous integration

Producer gọi trực tiếp API và chờ response. Cách này đơn giản khi cần kết quả ngay nhưng tạo coupling về availability và latency.

### 10.2. Asynchronous integration

Producer gửi message đến broker rồi tiếp tục. Consumer có thể xử lý sau và retry khi gặp lỗi tạm thời. Producer ít phụ thuộc vào thời gian hoạt động của consumer.

### 10.3. Webhook

Webhook là HTTP request được gửi đến endpoint đã đăng ký khi một event xảy ra. Cần xác thực chữ ký, retry, timeout, replay protection và quản lý endpoint.

### 10.4. Streaming

Stream lưu event theo thứ tự log hoặc partition, cho phép consumer đọc lại trong retention window. Nó phù hợp với dữ liệu liên tục và xử lý theo offset.

### 10.5. Queue

Queue phân phối công việc cho worker. Message thường được một worker trong nhóm xử lý, tùy cấu hình acknowledgement và redelivery.
 
### 10.6. Chọn theo semantics

Không chọn asynchronous chỉ vì nó có vẻ mở rộng tốt. Nếu caller cần biết thao tác đã thành công hay chưa, command/reply hoặc API synchronous có thể phù hợp hơn.

## 11. Routing, filtering và subscription rules

Event bus cần biết event được gửi đến channel hoặc consumer nào.

### 11.1. Topic routing

Topic thường phân nhóm event theo domain hoặc event type. Consumer subscribe topic tương ứng và nhận message theo policy của broker.

### 11.2. Routing key

Routing key có thể dựa trên event type, tenant, region hoặc entity key. Không nên đưa dữ liệu nhạy cảm vào routing key nếu broker metadata có thể được quan sát rộng.

### 11.3. Content-based filtering

Consumer có thể nhận chỉ event thỏa điều kiện, ví dụ region == "VN" hoặc eventType == "OrderConfirmed". Filter cần được kiểm tra kiểu và giới hạn độ phức tạp.

### 11.4. Subscription filter và business rule

Filter quyết định message nào được chuyển đến consumer. Business rule quyết định cách xử lý message sau khi nhận. Hai bước nên được tách để dễ giải thích và audit.

### 11.5. Wildcard subscription

Wildcard có thể đăng ký một nhóm event, ví dụ sales.order.*. Cần giới hạn namespace để consumer không vô tình nhận event ngoài phạm vi.

### 11.6. Fan-out

Fan-out gửi một event đến nhiều subscription độc lập. Mỗi consumer có thể có retry và trạng thái xử lý riêng.

### 11.7. Competing consumers

Nhiều worker cùng một consumer group chia tải. Điều này tăng throughput nhưng cần xử lý ordering theo key và đảm bảo worker không cùng xử lý một message ngoài ý muốn.

### 11.8. Dynamic subscription

Nếu subscription được tạo từ cấu hình người dùng, cần kiểm tra quyền subscribe và giới hạn channel được phép. Không cho tenant tự đăng ký mọi topic nội bộ.

## 12. Ordering và partitioning

Thứ tự event có thể quan trọng với các thay đổi trạng thái của cùng một thực thể.

### 12.1. Global ordering

Global ordering đảm bảo mọi event trong một luồng có thứ tự toàn cục. Nó thường làm giảm khả năng song song và không phải broker nào cũng cung cấp.

### 12.2. Per-key ordering

Một lựa chọn phổ biến là bảo đảm thứ tự trong cùng partition hoặc key. Ví dụ tất cả event của một orderId đi vào cùng partition.

### 12.3. Partition key

Partition key xác định cách message được phân phối. Chọn aggregate ID hoặc entity ID khi cần giữ thứ tự cho cùng một thực thể.

### 12.4. Out-of-order event

Consumer có thể nhận event phiên bản mới trước event cũ do retry, nhiều producer hoặc nhiều channel. Payload có thể mang aggregate version hoặc sequence number để phát hiện.

### 12.5. Event time và processing time

Event time là thời điểm sự kiện xảy ra; processing time là lúc consumer xử lý. Hai thời điểm có thể khác xa khi queue bị backlog hoặc message được replay.

### 12.6. Late arrival

Event đến muộn có thể làm read model tạm thời không đúng thứ tự. Consumer cần policy xử lý event cũ, watermark hoặc reconciliation tùy workload.

### 12.7. Không giả định thứ tự giữa topic

Hai topic độc lập thường không có một thứ tự toàn cục. Nếu consumer cần quan hệ thứ tự giữa các event type, cần sequence hoặc workflow contract rõ.

## 13. Delivery guarantee

Delivery guarantee mô tả khả năng message được chuyển đến consumer và số lần xử lý có thể xảy ra.

| Guarantee | Ý nghĩa | Hệ quả |
|---|---|---|
| At-most-once | Có thể mất message nhưng không redeliver | Cần chấp nhận mất hoặc có nguồn phục hồi |
| At-least-once | Message được giao lại cho đến khi xác nhận theo policy | Có thể xử lý trùng |
| Effectively-once | Kết hợp delivery và idempotent processing để đạt hiệu ứng nghiệp vụ một lần | Cần deduplication và transaction phù hợp |
| Exactly-once | Semantics một lần trong phạm vi được định nghĩa của nền tảng | Không tự động bao phủ mọi side effect bên ngoài |

### 13.1. At-most-once

Message có thể bị mất nếu consumer lỗi trước khi xử lý xong hoặc acknowledgement được gửi quá sớm. Phù hợp khi mất một số event có thể chấp nhận hoặc có cơ chế tái tạo.

### 13.2. At-least-once

Broker hoặc producer retry cho đến khi đạt điều kiện acknowledgement. Consumer phải chịu được duplicate vì message có thể được giao nhiều lần.

### 13.3. Exactly-once semantics

Một nền tảng có thể cung cấp exactly-once trong một transaction boundary hoặc một pipeline cụ thể. Điều này không có nghĩa email, payment API hoặc database ngoài broker tự động chỉ thực hiện một lần.

### 13.4. Effectively-once processing

Consumer có thể kết hợp event ID, inbox table, unique constraint và transaction để bảo đảm side effect nghiệp vụ chỉ được ghi nhận một lần dù message được giao lại.

### 13.5. Acknowledgement timing

Ack trước side effect có thể làm mất công việc nếu process chết sau ack. Ack sau side effect có thể tạo duplicate nếu process chết trước ack. Idempotency là phần thiết yếu của thiết kế.

## 14. Idempotency và xử lý message trùng

Idempotent handler tạo cùng trạng thái cuối khi cùng một event được xử lý một hoặc nhiều lần.

### 14.1. Vì sao có duplicate?

Duplicate có thể đến từ producer retry, broker redelivery, consumer crash, timeout acknowledgement, replay hoặc lỗi cấu hình subscription.

### 14.2. Event ID và deduplication

Consumer lưu event ID đã xử lý. Nếu nhận lại ID đã tồn tại, có thể bỏ qua phần side effect đã hoàn thành.

### 14.3. Inbox pattern

Inbox table lưu message ID và trạng thái xử lý trong cùng transaction với cập nhật nghiệp vụ. Unique constraint trên message ID giúp chống xử lý lặp trong phạm vi database transaction.

### 14.4. Idempotent update

Thay vì cộng một khoản tiền mỗi lần nhận event, consumer có thể ghi nhận transaction ID duy nhất hoặc cập nhật trạng thái theo version. Thiết kế cần xét side effect thực tế.

### 14.5. External API

Nếu handler gọi payment hoặc email provider, dùng idempotency key nếu provider hỗ trợ. Nếu không, cần reconciliation hoặc quy trình xử lý uncertainty.

### 14.6. Retention của deduplication record

Nếu xóa inbox record quá sớm, một event được replay sau đó có thể tạo side effect lần nữa. Retention phải phù hợp với broker retention và khả năng replay.

### 14.7. Idempotency scope

Một event có thể được xử lý bởi nhiều consumer độc lập. Deduplication key cần có consumer identity hoặc handler scope để một consumer không chặn consumer khác.

## 15. Retry, backoff và dead-letter queue

Không phải mọi lỗi đều giống nhau. Retry policy cần phân biệt lỗi tạm thời và lỗi không thể khắc phục bằng việc thử lại.

### 15.1. Transient failure

Ví dụ network timeout, broker unavailable hoặc database connection tạm thời bị từ chối. Retry có thể thành công sau một khoảng chờ.

### 15.2. Permanent failure

Schema không hợp lệ, thiếu field bắt buộc hoặc dữ liệu vi phạm domain rule thường không tự hết lỗi. Retry liên tục chỉ làm tăng tải.

### 15.3. Exponential backoff

Thời gian chờ có thể tăng theo cấp số nhân, có giới hạn tối đa và jitter để nhiều consumer không retry đồng thời.
 
### 15.4. Retry limit

Đặt số lần thử hoặc tổng thời gian retry. Khi vượt giới hạn, message được chuyển sang dead-letter queue hoặc trạng thái lỗi cần can thiệp.

### 15.5. Dead-letter queue

DLQ lưu message không thể xử lý theo policy chính. Cần lưu nguyên nhân, số lần thử, thời điểm và metadata cần thiết để điều tra.

### 15.6. Poison message

Poison message là message luôn khiến handler lỗi, có thể do dữ liệu xấu hoặc bug. DLQ và giới hạn retry ngăn một message chặn cả queue.

### 15.7. Re-drive

Sau khi sửa lỗi, operator có thể phát lại message từ DLQ. Re-drive cần kiểm tra schema, idempotency và thứ tự trước khi chạy.

### 15.8. Retry có thể gây reorder

Một message bị retry lâu có thể được xử lý sau message mới hơn. Với dữ liệu có thứ tự, cần partition strategy, sequence check hoặc pause partition theo policy.

## 16. Transactional outbox và inbox

Outbox và inbox là hai pattern giúp xử lý ranh giới transaction giữa database và message broker.

### 16.1. Vấn đề dual write

Một service có thể cần cập nhật database và publish event. Nếu hai thao tác không nằm trong cùng transaction, một thao tác có thể thành công còn thao tác kia thất bại.

### 16.2. Outbox pattern

Trong cùng transaction, service cập nhật business table và ghi một outbox record. Relay đọc record chưa publish, gửi lên broker rồi đánh dấu đã xử lý. Nếu relay crash, record có thể được gửi lại, nên consumer vẫn cần idempotency.

### 16.3. Outbox schema

Outbox record có thể có event ID, aggregate ID, event type, schema version, payload, occurredAt, createdAt và publishedAt.
 
### 16.4. Polling relay

Relay định kỳ truy vấn outbox record chưa gửi. Cần batching, locking hoặc claim mechanism để nhiều relay không publish cùng một record đồng thời ngoài ý muốn.

### 16.5. CDC relay

Change Data Capture có thể đọc thay đổi của outbox table từ transaction log rồi publish. Cách này giảm polling nhưng cần vận hành connector và offset.
 
### 16.6. Inbox pattern

Consumer ghi nhận event ID vào inbox cùng transaction với cập nhật trạng thái nghiệp vụ. Khi message được giao lại, unique key giúp phát hiện duplicate.
 
### 16.7. Transaction boundary

Outbox/inbox giúp đồng bộ database với message processing trong một ranh giới transaction cụ thể. Chúng không tự tạo transaction phân tán nguyên tử giữa tất cả dịch vụ.

## 17. Event schema và serialization format

Producer và consumer phải trao đổi payload theo cùng schema và format.

### 17.1. JSON

JSON dễ đọc và phổ biến trong HTTP, webhook và message broker. Cần định nghĩa kiểu, nullability, number precision và cách biểu diễn date/time.

### 17.2. Avro

Avro thường dùng schema và schema ID để hỗ trợ serialization gọn và schema evolution. Việc tương thích phụ thuộc quy tắc registry và cách reader/writer schema được áp dụng.

### 17.3. Protocol Buffers

Protobuf cung cấp binary encoding và field numbering. Không tái sử dụng field number đã xóa; cần tuân thủ quy tắc compatibility khi đổi field.

### 17.4. XML

XML có thể phù hợp với hệ thống enterprise hoặc đối tác dùng schema XML. Parser phải được cấu hình an toàn và namespace/schema cần được quản lý.

### 17.5. Content type

Envelope nên chỉ rõ format và encoding. Consumer không nên đoán định dạng từ payload bytes.

### 17.6. Decimal và tiền tệ

Không dùng floating point tùy tiện cho số tiền. Dùng decimal representation hoặc cấu trúc gồm amount và currency.

### 17.7. Date/time

Dùng Instant hoặc timestamp có timezone rõ. Phân biệt local date, local date-time và instant; không giả định mọi consumer dùng cùng timezone.

### 17.8. Optional và null

Schema cần phân biệt field vắng mặt, field null và field có giá trị mặc định. Những trạng thái này có thể mang semantics khác nhau khi cập nhật consumer state.

## 18. Schema evolution và compatibility

Event contract thường được nhiều consumer sử dụng trong thời gian dài. Schema evolution cần được quản lý để producer và consumer có thể triển khai độc lập.

### 18.1. Backward compatibility

Consumer mới có thể đọc event cũ. Ví dụ consumer mới thêm field optional nhưng vẫn chấp nhận payload version trước.

### 18.2. Forward compatibility

Consumer cũ có thể đọc event mới nếu nó bỏ qua field chưa biết và schema cho phép. Không phải mọi format hoặc implementation đều tự động có đặc tính này.

### 18.3. Full compatibility

Full compatibility yêu cầu hỗ trợ cả reader/writer version mới và cũ theo policy của registry. Cần xác định chính xác phạm vi version được so sánh.

### 18.4. Add optional field

Thêm field optional thường dễ tương thích hơn field required. Tuy nhiên, consumer cũ có thể không hiểu semantics mới nếu field làm thay đổi ý nghĩa nghiệp vụ.

### 18.5. Remove field

Xóa field có thể phá consumer vẫn đang đọc nó. Có thể đánh dấu deprecated, theo dõi usage rồi loại bỏ trong major version hoặc event type mới.
 
### 18.6. Rename field

Rename thường tương đương remove field cũ và add field mới. Nếu cần migration, có thể duy trì alias hoặc phát event version mới trong giai đoạn chuyển tiếp.

### 18.7. Change field type

Đổi String thành Integer hoặc đổi number precision có thể không tương thích. Cần migration hoặc field mới với semantics rõ.
 
### 18.8. Change meaning

Đổi ý nghĩa field nhưng giữ nguyên tên và kiểu là nguy hiểm vì schema checker không phát hiện được. Semantics cần được xem là một phần của contract.
 
### 18.9. Versioning strategy

Có thể dùng version trong event type, envelope metadata hoặc schema registry. Quan trọng là producer, consumer và tooling có thể xác định schema chính xác.
 
### 18.10. Consumer-driven contract testing

Consumer có thể công bố các field và semantics mà nó phụ thuộc. Producer kiểm tra thay đổi có phá contract đã cam kết hay không.

## 19. Event transformation và integration mapping

Một integration flow có thể cần đổi tên field, chuyển kiểu, lọc hoặc kết hợp dữ liệu.

### 19.1. Field mapping

Ví dụ source có customer_id còn target yêu cầu customerId. Mapping cần khai báo tường minh và có kiểm tra kiểu.

~~~text
transform CustomerRegistered to crm.CustomerCreated {
    map customerId = source.customerId
    map emailAddress = source.email
    map createdAt = source.registeredAt
}
~~~

### 19.2. Type conversion

Chuyển timestamp, decimal, enum hoặc identifier cần quy tắc rõ. Nếu conversion thất bại, flow cần báo lỗi hoặc đưa message vào error channel.

### 19.3. Enrichment

Consumer hoặc integration service có thể lấy thêm dữ liệu từ một nguồn khác. Enrichment làm tăng coupling và latency; cần timeout, cache và provenance của dữ liệu bổ sung.

### 19.4. Filtering

Có thể bỏ qua event không liên quan trước khi xử lý. Filter phải xác định hành vi với field missing/null và không được loại nhầm message cần thiết cho consumer state.
 
### 19.5. Splitting

Một event có thể được tách thành nhiều message hoặc task. Cần gắn correlation ID và xác định thứ tự nếu các message liên quan.
 
### 19.6. Aggregation

Nhiều event có thể được tổng hợp thành một kết quả, ví dụ đếm số item hoặc tính trạng thái đơn hàng. Cần xác định cửa sổ thời gian, late event và cách xử lý duplicate.
 
### 19.7. Transformation version

Mapping logic cũng là một phần contract tích hợp. Version hóa transformation giúp tái hiện cách event cũ được chuyển đổi.

## 20. Orchestration và choreography

Event-driven integration có thể điều phối quy trình theo hai cách phổ biến.

### 20.1. Choreography

Mỗi service phát event khi hoàn thành phần việc của mình; service khác phản ứng với event đó. Không có một coordinator trung tâm nắm toàn bộ trình tự.
 
~~~mermaid
flowchart LR
    A[Order Service] -->|OrderPlaced| B[Inventory Service]
    B -->|InventoryReserved| C[Payment Service]
    C -->|PaymentAuthorized| D[Shipping Service]
    D -->|ShipmentCreated| E[Notification Service]
~~~

Choreography giảm sự phụ thuộc vào một orchestrator nhưng có thể làm luồng nghiệp vụ khó quan sát khi số service tăng.
 
### 20.2. Orchestration

Một workflow hoặc orchestrator quản lý tiến trình, gửi command và chờ event/reply từ từng service. Nó cung cấp cái nhìn tập trung về trạng thái quy trình.
 
~~~mermaid
flowchart TD
    A[Order Workflow] --> B[Reserve inventory command]
    B --> C[Inventory result event]
    C --> D[Authorize payment command]
    D --> E[Payment result event]
    E --> F[Create shipment command]
~~~

### 20.3. Chọn mô hình

Choreography phù hợp với phản ứng độc lập và luồng tương đối đơn giản. Orchestration phù hợp khi có nhiều bước, timeout, compensation và yêu cầu theo dõi trạng thái toàn quy trình. Có thể kết hợp hai mô hình.
 
### 20.4. Tránh vòng lặp event

Nếu service A phát event khiến B phát event làm A xử lý lại và phát tiếp, có thể tạo vòng lặp. Cần event type rõ, causation metadata, idempotency và rule tránh phản ứng với event do chính consumer tạo ra nếu không phù hợp.
 
### 20.5. Process manager

Process manager giữ trạng thái quy trình dài và quyết định bước tiếp theo khi event đến. Nó cần correlation key, timeout, persistence và recovery.
 
## 21. Saga và quy trình phân tán

Saga là pattern phối hợp nhiều transaction cục bộ thành một quy trình nghiệp vụ dài, với compensation khi bước sau thất bại.

### 21.1. Local transaction

Mỗi service thực hiện transaction trên dữ liệu do mình sở hữu. Không cần một transaction database xuyên qua tất cả service.
 
### 21.2. Compensation

Nếu một bước thất bại sau khi các bước trước đã commit, hệ thống có thể thực hiện hành động bù. Ví dụ hủy reservation hoặc hoàn tiền. Compensation là hành động nghiệp vụ mới, không phải rollback vật lý mọi lịch sử.
 
### 21.3. Event-triggered saga

Một event có thể kích hoạt saga instance. Correlation ID hoặc business key xác định instance cần cập nhật.
 
### 21.4. Timeout

Saga cần timeout cho bước chờ. Khi hết hạn, process manager có thể retry, yêu cầu can thiệp hoặc chạy compensation.
 
### 21.5. Duplicate và out-of-order

Saga handler phải idempotent và xác minh state transition. Event đến muộn không được làm saga quay lại trạng thái cũ.
 
### 21.6. Persisted state

Lưu trạng thái saga để process có thể phục hồi sau restart. Không chỉ giữ state trong memory của worker.
 
### 21.7. Compensation failure

Compensation cũng có thể thất bại. Cần retry, escalation và trạng thái cần can thiệp thủ công.

## 22. Event sourcing và integration events

Event sourcing và integration events có liên quan nhưng không đồng nghĩa.

### 22.1. Event sourcing

Event sourcing lưu các domain event như nguồn sự thật của trạng thái aggregate. Trạng thái hiện tại được tái tạo bằng cách áp dụng event theo thứ tự.
 
### 22.2. Integration event

Integration event được công bố cho hệ thống bên ngoài hoặc bounded context khác. Nó thường là contract công khai, có thể khác với domain event nội bộ.
 
### 22.3. Domain event

Domain event diễn tả điều quan trọng đã xảy ra trong một domain model. Nó có thể được dùng nội bộ trong cùng transaction hoặc được chuyển thành integration event.
 
### 22.4. Không phát mọi domain event ra ngoài

Domain event có thể chứa chi tiết nội bộ hoặc thay đổi thường xuyên. Chỉ những sự kiện có ý nghĩa và contract phù hợp mới nên được công bố.
 
### 22.5. Event store và message broker

Event store lưu lịch sử phục vụ rebuild state; message broker phân phối message đến consumer. Một hệ thống có thể dùng cả hai nhưng mục tiêu và retention khác nhau.
 
### 22.6. Snapshot

Event-sourced aggregate có thể dùng snapshot để giảm thời gian replay. Snapshot không thay thế event history và cần version schema riêng.
 
## 23. Bảo mật của sự kiện tích hợp

Event có thể đi qua broker, log, consumer và đối tác ngoài tổ chức. Bảo mật phải bao phủ cả message và kênh vận chuyển.

### 23.1. Authentication

Producer và consumer cần xác thực với broker hoặc webhook endpoint bằng identity phù hợp. Không chỉ dựa vào tên topic hoặc network location.
 
### 23.2. Authorization

Producer chỉ được publish event type/channel được cấp; consumer chỉ được subscribe channel cần thiết. Tenant không được đọc event của tenant khác.
 
### 23.3. Transport encryption

Dùng TLS cho kết nối broker và webhook. Quản lý certificate và trust policy phù hợp.
 
### 23.4. Payload encryption

Nếu message chứa dữ liệu nhạy cảm và cần bảo vệ ngay cả trong broker/storage, có thể mã hóa payload ở tầng ứng dụng. Key management và rotation cần được xác định.
 
### 23.5. Data minimization

Chỉ gửi trường consumer thực sự cần. Tránh đưa password, access token hoặc dữ liệu cá nhân dư thừa vào event.
 
### 23.6. Tenant isolation

Partition, topic, ACL và encryption context cần tôn trọng tenant boundary. Không dùng tenant ID từ payload làm bằng chứng authorization.
 
### 23.7. Replay protection

Event hợp lệ có thể bị phát lại. Dùng event ID, timestamp, nonce hoặc sequence theo threat model; consumer vẫn cần idempotency.
 
### 23.8. Webhook signature

Webhook có thể dùng HMAC hoặc chữ ký số trên body và metadata quan trọng. Consumer xác minh signature, timestamp và replay window trước khi xử lý.
 
### 23.9. Secret rotation

Credential broker và webhook signing key cần rotation. Có thể hỗ trợ giai đoạn chấp nhận key cũ và mới có giới hạn.
 
### 23.10. Audit và retention

Kiểm soát ai đọc event, thời gian lưu và quyền export. Log không nên sao chép toàn bộ payload nhạy cảm.

## 24. Quan sát và vận hành event integration

Hệ thống event-driven cần công cụ để hiểu luồng message và phát hiện backlog hoặc lỗi.

### 24.1. Correlation ID

Dùng correlation ID xuyên suốt request, event, command và workflow để theo dõi một nghiệp vụ.
 
### 24.2. Distributed tracing

Trace có thể gồm producer span, publish span, broker propagation và consumer span. Không phải broker nào cũng truyền context giống nhau; cần chuẩn hóa propagation.
 
### 24.3. Metrics

Theo dõi publish rate, consume rate, processing latency, queue depth, consumer lag, retry count, DLQ count và error rate.
 
### 24.4. Structured logs

Log event ID, type, version, source, consumer và processing result. Payload cần được redacted hoặc bỏ qua theo policy.
 
### 24.5. Consumer lag

Lag là khoảng cách giữa message mới nhất và vị trí consumer đã xử lý. Lag tăng có thể do throughput thấp, lỗi lặp hoặc consumer bị dừng.
 
### 24.6. Backlog và capacity

Theo dõi queue depth và tốc độ tăng backlog. Tăng worker có thể giúp nhưng cần kiểm tra partition, downstream capacity và ordering.
 
### 24.7. DLQ monitoring

DLQ không nên là nơi message bị quên. Cần dashboard, alert, owner và quy trình re-drive.
 
### 24.8. Schema error metrics

Theo dõi lỗi deserialize, version không hỗ trợ và compatibility failure để phát hiện producer rollout không đồng bộ.
 
### 24.9. Event catalog

Catalog liệt kê event type, owner, schema, producer, consumer, channel và retention. Nó giúp nhóm tích hợp tìm hợp đồng và đánh giá tác động.
 
### 24.10. Operational runbook

Mỗi event flow quan trọng nên có hướng dẫn xử lý broker outage, backlog, poison message, replay và consumer deployment.

## 25. Kiểm thử sự kiện tích hợp

Kiểm thử cần xác minh cả contract, routing, delivery và hành vi consumer.

### 25.1. Schema tests

Kiểm tra event payload tuân theo schema, required field, type, format và version.
 
### 25.2. Producer contract tests

Xác minh producer phát đúng event type, metadata và payload khi transition nghiệp vụ xảy ra.
 
### 25.3. Consumer contract tests

Xác minh consumer chấp nhận event version được hỗ trợ và xử lý field optional/unknown theo policy.
 
### 25.4. Routing tests

Kiểm tra topic, routing key, filter và subscription để event đến đúng consumer.
 
### 25.5. Duplicate delivery tests

Gửi cùng event ID nhiều lần và xác minh side effect chỉ được ghi nhận một lần theo thiết kế idempotency.
 
### 25.6. Ordering tests

Gửi event cùng aggregate theo thứ tự và cố ý đảo thứ tự để kiểm tra sequence handling.
 
### 25.7. Retry and DLQ tests

Giả lập transient failure và permanent failure. Xác minh backoff, retry limit, DLQ metadata và re-drive.
 
### 25.8. Outbox/inbox tests

Kiểm tra database rollback, broker outage, relay crash và consumer crash quanh thời điểm commit/ack.
 
### 25.9. End-to-end tests

Dùng broker hoặc test environment tương đương để kiểm tra producer, broker, consumer và side effect trong toàn flow.
 
### 25.10. Load tests

Đo throughput, latency, backlog, consumer lag và khả năng phục hồi khi downstream chậm.
 
### 25.11. Security tests

Kiểm tra ACL, tenant isolation, TLS, webhook signature, replay, payload redaction và secret leakage.
 
### 25.12. Replay tests

Phát lại một khoảng event lịch sử vào môi trường test và xác minh read model hoặc consumer output có thể được tái tạo theo policy.

## 26. Khai báo event flow trong DSL

Một DSL tích hợp có thể mô tả event, channel, producer và consumer trong cùng một model.

~~~text
event OrderConfirmed {
    version = 1
    data {
        orderId: UUID
        customerId: UUID
        total: Money<VND>
        confirmedAt: Instant
    }
}

channel orders {
    kind = topic
    delivery = AT_LEAST_ONCE
    retention = 7 days
}

producer OrderService {
    publish OrderConfirmed to orders
    key = event.orderId
}

consumer InventoryService {
    subscribe OrderConfirmed from orders
    group = "inventory-reservation"

    handler reserveInventory {
        idempotencyKey = event.id
        timeout = 10 seconds
        retry {
            attempts = 5
            backoff = exponential
        }
        deadLetter = "orders.dlq"
    }
}
~~~

### 26.1. Event declaration

Khai báo event và schema độc lập với broker. Điều này giúp contract được tái sử dụng khi đổi transport.
 
### 26.2. Channel declaration

Channel định nghĩa transport-specific properties như topic, queue, retention, partition hoặc acknowledgement. DSL cần phân biệt thuộc tính chung với thuộc tính riêng của broker.
 
### 26.3. Producer binding

Producer binding nối event type với channel và có thể xác định partition key, serializer, transaction/outbox policy.
 
### 26.4. Consumer binding

Consumer binding xác định event type, group, filter, handler, timeout và retry policy.
 
### 26.5. Handler mapping

Handler nhận event theo schema và chuyển vào logic nghiệp vụ. Cần định nghĩa behavior khi handler trả lỗi hoặc timeout.
 
### 26.6. Policy validation

Validator có thể kiểm tra event schema tồn tại, producer có quyền publish, consumer có quyền subscribe và retry/DLQ được cấu hình phù hợp.

## 27. Những sai lầm thường gặp

### 27.1. Nhầm event với command

Event mô tả điều đã xảy ra; command yêu cầu hành động. Nhầm lẫn làm producer và consumer không rõ ai chịu trách nhiệm quyết định.
 
### 27.2. Phát event trước khi transaction commit

Consumer có thể xử lý một sự kiện mà thay đổi nghiệp vụ sau đó bị rollback. Dùng outbox hoặc cơ chế transaction phù hợp.
 
### 27.3. Giả định message chỉ được giao một lần

At-least-once delivery có thể tạo duplicate. Consumer cần idempotency và deduplication.
 
### 27.4. Ack quá sớm

Ack trước khi side effect được ghi nhận có thể làm mất công việc khi consumer crash. Xác định acknowledgement boundary rõ.
 
### 27.5. Không xử lý poison message

Retry vô hạn có thể chặn partition hoặc tạo tải lớn. Đặt retry limit và DLQ.
 
### 27.6. Thay đổi schema tùy tiện

Đổi field type hoặc meaning có thể phá consumer đang chạy. Dùng compatibility checks, version và rollout có kế hoạch.
 
### 27.7. Dựa vào thứ tự toàn cục

Broker thường chỉ bảo đảm ordering trong phạm vi nhất định. Dùng partition key, sequence và state validation nếu cần per-entity order.
 
### 27.8. Payload quá lớn

Event khổng lồ làm tăng network, broker storage và consumer memory. Có thể gửi reference đến object store nếu quyền và lifecycle được quản lý.
 
### 27.9. Đưa secret vào event

Message có thể được lưu, replay và đọc bởi nhiều consumer. Không phát credential hoặc token trong payload.
 
### 27.10. Không có owner cho contract

Consumer không biết ai quản lý event và không có nơi phối hợp khi schema thay đổi. Mỗi contract cần owner rõ.
 
### 27.11. Không theo dõi DLQ

Message lỗi bị chuyển sang DLQ nhưng không có alert hoặc người chịu trách nhiệm sẽ trở thành lỗi nghiệp vụ bị bỏ quên.
 
### 27.12. Dùng event để thay mọi API

Không phải tương tác nào cũng cần event. Query cần response, command cần xác nhận và event cần công bố sự thật. Chọn kiểu message theo semantics.
 
### 27.13. Cho rằng exactly-once giải quyết mọi duplicate

Guarantee của broker thường có phạm vi cụ thể. Side effect ở hệ thống ngoài vẫn cần idempotency hoặc reconciliation.
 
### 27.14. Không kiểm soát consumer fan-out

Một event có thể kích hoạt nhiều hệ thống và tạo tải dây chuyền. Cần catalog, capacity planning, rate limit và quyền subscription.

## 28. Nguyên tắc thiết kế sự kiện tích hợp trong DSL

Một DSL tích hợp tốt cần mô tả event contract và vận hành message theo cách rõ ràng, an toàn và có thể kiểm tra.

### 28.1. Event phản ánh sự thật nghiệp vụ

Dùng tên quá khứ và semantics ổn định. Tách event khỏi command, query và chi tiết database.
 
### 28.2. Contract có kiểu và version

Khai báo schema, field semantics, unit, nullability, required status và compatibility policy. Gắn owner cho mỗi event.
 
### 28.3. Envelope nhất quán

Chuẩn hóa event ID, type, source, timestamp, correlation, causation, content type và schema version.
 
### 28.4. Producer publish sau commit

Dùng outbox hoặc cơ chế transaction phù hợp để tránh event không khớp với business state.
 
### 28.5. Consumer idempotent

Thiết kế handler chịu được duplicate, redelivery và replay. Dùng inbox/deduplication khi cần.
 
### 28.6. Delivery semantics tường minh

Khai báo at-most-once, at-least-once hoặc semantics cụ thể của nền tảng. Không tuyên bố exactly-once ngoài transaction boundary được bảo đảm.
 
### 28.7. Ordering theo key

Chọn partition key và sequence strategy khi thứ tự của cùng aggregate có ý nghĩa. Không giả định global ordering nếu transport không hỗ trợ.
 
### 28.8. Retry có giới hạn

Phân loại transient/permanent failure, dùng backoff và DLQ. Có owner và quy trình re-drive.
 
### 28.9. Schema evolution có kiểm soát

Kiểm tra compatibility trong pipeline, triển khai consumer tương thích trước khi producer phát schema mới và giữ contract cũ theo thời gian cần thiết.
 
### 28.10. Bảo mật end-to-end

Xác thực producer/consumer, phân quyền channel, mã hóa transport, giảm thiểu payload và bảo vệ tenant boundary.
 
### 28.11. Quan sát được

Dùng correlation ID, tracing, metrics, logs có cấu trúc, event catalog và runbook vận hành.
 
### 28.12. Tách contract khỏi transport

Event model nên độc lập với Kafka, AMQP, HTTP webhook hoặc broker cụ thể. Channel binding mới chứa cấu hình transport-specific.
 
### 28.13. Kiểm thử failure mode

Kiểm thử duplicate, out-of-order, timeout, retry, DLQ, schema mismatch, broker outage và replay.
 
### 28.14. Quản lý lifecycle

Quy định retention, deprecation, ownership, access, replay và deletion policy cho event data.

## 29. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Integration Event | Thông điệp công bố một sự kiện đã xảy ra để hệ thống khác phản ứng |
| Producer | Thành phần tạo và phát event |
| Consumer | Thành phần nhận và xử lý event |
| Event Contract | Hợp đồng về tên, schema, semantics và version của event |
| Event Envelope | Phần metadata bao quanh payload |
| Payload | Dữ liệu nghiệp vụ của message |
| Event Bus | Hạ tầng nhận và định tuyến event |
| Message Broker | Thành phần vận chuyển, lưu và phân phối message |
| Topic | Kênh logic để publish/subscribe message |
| Queue | Hàng đợi phân phối message cho worker |
| Subscription | Đăng ký nhận một nhóm event |
| Routing Key | Giá trị dùng để định tuyến message |
| Fan-out | Phân phối một event đến nhiều consumer độc lập |
| Consumer Group | Nhóm worker chia nhau xử lý message |
| Partition Key | Khóa xác định partition và thường dùng để giữ thứ tự theo entity |
| At-least-once | Delivery có thể lặp, consumer cần chịu duplicate |
| At-most-once | Delivery không redeliver nhưng có thể mất message |
| Exactly-once Semantics | Cam kết một lần trong phạm vi được nền tảng định nghĩa |
| Idempotency | Xử lý lặp không tạo thêm hiệu ứng nghiệp vụ |
| Deduplication | Phát hiện và bỏ qua message trùng |
| Dead-letter Queue | Nơi lưu message không thể xử lý theo retry policy |
| Retry Backoff | Khoảng chờ tăng dần giữa các lần thử lại |
| Transactional Outbox | Ghi event vào outbox cùng transaction nghiệp vụ rồi relay publish |
| Inbox Pattern | Ghi nhận message đã nhận/xử lý để chống duplicate |
| Schema Registry | Dịch vụ quản lý schema và compatibility |
| Schema Evolution | Quá trình thay đổi schema theo thời gian |
| Correlation ID | Mã liên kết các message thuộc cùng quy trình |
| Causation ID | Mã chỉ ra message đã gây ra message hiện tại |
| Choreography | Các service phản ứng với event mà không có coordinator trung tâm |
| Orchestration | Thành phần điều phối tập trung quản lý tiến trình |
| Saga | Quy trình phân tán gồm local transaction và compensation |
| Event Sourcing | Lưu event làm nguồn sự thật để tái tạo trạng thái |
| Event Replay | Phát lại event lịch sử để tái xử lý hoặc dựng read model |
| Consumer Lag | Khoảng cách giữa message mới nhất và vị trí consumer đã xử lý |
| DLQ Re-drive | Đưa message từ DLQ trở lại luồng xử lý sau khi khắc phục lỗi |

Sự kiện tích hợp giúp các ứng dụng phối hợp dựa trên những thay đổi đã xảy ra và các hợp đồng message được công bố. Trong DSL, event cần có schema, version, envelope, producer, consumer và channel binding rõ ràng; runtime cần xác định delivery guarantee, ordering, acknowledgement, retry, idempotency và xử lý lỗi. Khi kết hợp outbox/inbox, schema compatibility, security, tracing, catalog và kiểm thử failure mode, hệ thống event-driven có thể mở rộng nhiều consumer mà vẫn giữ được tính nhất quán, khả năng truy vết và độ tin cậy trong vận hành.
