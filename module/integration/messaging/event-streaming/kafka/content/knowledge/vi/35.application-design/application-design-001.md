# Thiết kế luồng sự kiện theo ranh giới miền nghiệp vụ

Một hệ thống Kafka dễ vận hành bắt đầu từ cách doanh nghiệp chia trách nhiệm, không phải từ việc tạo thật nhiều topic. Mỗi sự kiện cần trả lời được ba câu hỏi: **sự thật nghiệp vụ nào vừa xảy ra, miền nào sở hữu sự thật đó, và những miền nào cần biết?** Khi ranh giới này rõ ràng, producer có thể công bố hợp đồng ổn định, consumer phát triển độc lập và luồng sự kiện vẫn dễ hiểu khi hệ thống mở rộng.

Bài học này tập trung vào thiết kế luồng sự kiện cho một hệ thống event streaming dùng Apache Kafka. Các ví dụ sử dụng Java và Spring Kafka; những nguyên tắc về ranh giới miền, hợp đồng sự kiện, phân vùng, độ tin cậy và khả năng quan sát cũng áp dụng cho các nền tảng event-driven khác.

Sau bài học, người học có thể:

- Xác định miền nghiệp vụ sở hữu một sự kiện và các miền tiêu thụ sự kiện đó.
- Phân biệt domain event, integration event và command.
- Thiết kế topic, event key và partition theo nhu cầu nghiệp vụ.
- Xây dựng hợp đồng sự kiện có thể tiến hóa mà không làm hỏng consumer.
- Kết hợp outbox, idempotency, retry và consumer group để xử lý sự kiện tin cậy.
- Nhận biết khi nào nên dùng Kafka Connect, Kafka Streams hoặc một dịch vụ điều phối quy trình.

## 1. Bắt đầu từ ranh giới nghiệp vụ

Hãy xét một hệ thống bán hàng có các khả năng nghiệp vụ: đặt hàng, thanh toán, quản lý tồn kho và giao vận. Mỗi khả năng có quy tắc, dữ liệu và ngôn ngữ riêng:

| Miền nghiệp vụ | Trách nhiệm chính | Một số sự thật miền có thể công bố |
|---|---|---|
| Đơn hàng (Orders) | Tiếp nhận đơn, kiểm tra mặt hàng, quản lý trạng thái đơn | **OrderPlaced**, **OrderCancelled** |
| Thanh toán (Payments) | Thu tiền, hoàn tiền, quản lý kết quả giao dịch | **PaymentAuthorized**, **PaymentDeclined**, **RefundCompleted** |
| Kho hàng (Inventory) | Giữ chỗ, xuất kho, điều chỉnh tồn | **StockReserved**, **StockReservationFailed**, **StockReleased** |
| Giao vận (Shipping) | Tạo lô giao, theo dõi vận chuyển | **ShipmentCreated**, **ShipmentDelivered** |

Một miền phải sở hữu dữ liệu và quy tắc quyết định trạng thái của nó. Ví dụ, Payments quyết định một khoản thanh toán đã được chấp thuận hay bị từ chối; Orders không nên tự suy ra kết quả đó bằng cách đọc trực tiếp bảng giao dịch của Payments.

Kafka giúp các miền trao đổi sự kiện mà không cần gọi đồng bộ từng dịch vụ. Tuy vậy, Kafka không tự tạo ra ranh giới tốt. Nếu Orders và Payments cùng ghi vào một cơ sở dữ liệu hoặc cùng phụ thuộc vào cấu trúc nội bộ của một dịch vụ, việc chuyển dữ liệu qua Kafka chỉ thay đổi cách truyền tin, chưa loại bỏ sự phụ thuộc.

Một ranh giới miền rõ ràng có các đặc điểm:

1. Có một chủ sở hữu chịu trách nhiệm về ý nghĩa và tính đúng đắn của dữ liệu.
2. Có ngôn ngữ nghiệp vụ nhất quán. Ví dụ, “đã đặt hàng” có ý nghĩa cụ thể và khác “đã tạo bản ghi đơn”.
3. Công bố những sự thật mà miền khác cần biết, không công bố toàn bộ cấu trúc nội bộ.
4. Có thể thay đổi cách triển khai bên trong mà không buộc mọi consumer thay đổi theo.

## 2. Phân biệt command, domain event và integration event

Ba khái niệm này thường xuất hiện trong cùng một luồng nhưng có ý nghĩa khác nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Command | Yêu cầu một thành phần thực hiện hành động; có thể thành công hoặc thất bại | **PlaceOrder**, **AuthorizePayment** |
| Domain event | Sự thật đã xảy ra bên trong một miền, có ý nghĩa với mô hình miền đó | **OrderValidated**, **PaymentCaptured** |
| Integration event | Hợp đồng sự kiện mà một miền công bố để miền khác hoặc hệ thống ngoài sử dụng | **OrderPlaced**, **PaymentAuthorized** |

Command thường mang ý định ở dạng mệnh lệnh. Event mô tả điều đã xảy ra ở dạng quá khứ. Consumer không nên hiểu một event là yêu cầu phải thực hiện hành động. Ví dụ, **PaymentAuthorized** thông báo kết quả thanh toán đã được xác nhận; nó không yêu cầu consumer tự đi thu tiền lần nữa.

Domain event có thể chỉ tồn tại trong tiến trình của một dịch vụ. Khi cần chia sẻ sự thật ra ngoài ranh giới miền, dịch vụ chuyển đổi nó thành integration event với hợp đồng công khai. Cách chuyển đổi này có thể loại bỏ dữ liệu nội bộ, đổi tên trường cho phù hợp ngôn ngữ chung hoặc gom nhiều chi tiết triển khai thành một sự thật nghiệp vụ ổn định.

**Tên sự kiện nên mô tả sự thật nghiệp vụ**, thường ở thì quá khứ:

- Tốt: **OrderPlaced**, **PaymentAuthorized**, **StockReserved**.
- Kém rõ nghĩa: **OrderUpdated**, **PaymentChanged**, **InventoryData**.

Tên như **OrderUpdated** không cho consumer biết điều gì đã thay đổi và ý nghĩa của thay đổi đó. Nếu một consumer phải đọc lại toàn bộ bản ghi đơn hàng để đoán nguyên nhân, hợp đồng sự kiện có thể đang quá chung chung.

Không nên công bố trực tiếp mọi thay đổi của bảng cơ sở dữ liệu dưới dạng sự kiện nghiệp vụ. **orders_row_updated** là tín hiệu kỹ thuật về lưu trữ; **OrderPlaced** là sự thật mà một miền khác có thể dùng để bắt đầu quy trình giao hàng. Hai loại dữ liệu có thể cùng hữu ích, nhưng phục vụ các mục đích và có mức ổn định khác nhau.

## 3. Mô hình hóa luồng theo vòng đời nghiệp vụ

Trước khi chọn topic, hãy mô tả một kịch bản nghiệp vụ từ đầu đến cuối. Với một đơn hàng mới, nhóm thiết kế cần xác định:

- Điều kiện nào khiến đơn được xem là đã đặt?
- Miền nào có quyền phát ra sự kiện xác nhận điều đó?
- Miền nào cần phản ứng và cần dữ liệu tối thiểu nào?
- Nếu một bước thất bại hoặc hết thời gian chờ, quy trình tiếp tục, thử lại hay bù trừ?
- Sự kiện nào là kết quả cuối cùng mà khách hàng hoặc hệ thống khác cần quan sát?

Một luồng minh họa:

~~~mermaid
flowchart LR
    A["Orders<br/>Xác nhận đơn"] -->|OrderPlaced| K[("Kafka")]
    K --> B["Payments<br/>Ủy quyền thanh toán"]
    B -->|PaymentAuthorized| K
    B -->|PaymentDeclined| K
    K --> C["Inventory<br/>Giữ chỗ hàng"]
    C -->|StockReserved| K
    C -->|StockReservationFailed| K
    K --> D["Orders<br/>Cập nhật trạng thái"]
    K --> E["Shipping<br/>Chuẩn bị giao hàng"]
~~~

Sơ đồ thể hiện các thông điệp có thể được công bố qua Kafka; nó không hàm ý mọi bước phải chạy đồng thời hoặc không cần kiểm soát quy trình. Trong triển khai thực tế, chỉ phát **OrderPlaced** sau khi Orders đã xác nhận đơn theo quy tắc của mình. Payments và Inventory tự quyết định cách xử lý, sau đó công bố kết quả thuộc quyền sở hữu của chúng.

Nếu quy trình có nhiều bước, thời gian chờ, nhánh lỗi và hành động bù trừ, hãy cân nhắc dùng **Saga**. Có hai cách tổ chức phổ biến:

- **Choreography:** mỗi miền phản ứng với sự kiện và công bố sự kiện tiếp theo. Cách này phù hợp với quy trình ngắn, ít nhánh và các bước tương đối độc lập.
- **Orchestration:** một process manager hoặc saga coordinator theo dõi trạng thái quy trình, gửi command và quyết định bước tiếp theo. Cách này dễ theo dõi hơn khi có timeout, nhiều nhánh hoặc hành động bù trừ.

Ví dụ, nếu thanh toán bị từ chối sau khi kho đã giữ chỗ hàng, quy trình có thể phát **ReleaseStockReservation** hoặc một command tương đương. Sự kiện **StockReleased** xác nhận việc giải phóng đã xảy ra. Không nên phát một event giả định như **StockReleased** ngay khi gửi yêu cầu; event phải phản ánh kết quả thực tế.

Cũng cần tránh biến mọi thay đổi nhỏ thành một chuỗi sự kiện liên miền. Hãy giữ các quy tắc nội bộ trong miền sở hữu chúng. Chỉ công bố sự kiện khi có consumer thực sự cần biết hoặc khi sự kiện tạo thành một phần có giá trị của hợp đồng nghiệp vụ.

## 4. Thiết kế hợp đồng sự kiện

Một integration event cần có phần metadata đủ để nhận diện, truy vết và xử lý an toàn. Một envelope thường có:

| Trường | Mục đích |
|---|---|
| **eventId** | Định danh duy nhất cho một lần phát sự kiện; dùng để chống xử lý trùng |
| **eventType** | Loại sự kiện, ví dụ **OrderPlaced** |
| **eventVersion** | Phiên bản hợp đồng hoặc payload |
| **occurredAt** | Thời điểm sự kiện xảy ra trong miền nguồn |
| **producer** | Dịch vụ hoặc miền phát sự kiện |
| **aggregateId** | Định danh đối tượng nghiệp vụ liên quan, thường dùng làm Kafka key |
| **correlationId** | Liên kết các bước trong cùng một quy trình |
| **causationId** | Chỉ ra thông điệp hoặc sự kiện dẫn đến sự kiện hiện tại |
| **payload** | Dữ liệu nghiệp vụ đã được chọn để công bố |

Ví dụ payload JSON rút gọn:

~~~json
{
  "eventId": "evt-7f31a9",
  "eventType": "OrderPlaced",
  "eventVersion": 1,
  "occurredAt": "2026-11-20T09:15:30Z",
  "producer": "orders-service",
  "aggregateId": "order-10482",
  "correlationId": "checkout-8831",
  "causationId": "cmd-place-order-8831",
  "payload": {
    "orderId": "order-10482",
    "totalAmount": "1250000.00",
    "currency": "VND",
    "items": [
      {
        "sku": "SKU-RED-01",
        "quantity": 2
      }
    ]
  }
}
~~~

Các mã định danh trong ví dụ chỉ mang tính minh họa. Dữ liệu thực tế cần tuân theo quy tắc định danh của hệ thống. Với tiền tệ, nên truyền cả số tiền và mã tiền tệ; cần chọn biểu diễn số thập phân phù hợp để tránh sai lệch do số thực nhị phân.

Hợp đồng nên công bố đủ để consumer thực hiện trách nhiệm của mình, nhưng không biến thành bản sao toàn bộ cơ sở dữ liệu nguồn. Chẳng hạn, Shipping có thể cần **orderId**, địa chỉ giao hàng đã được xác nhận và các dòng hàng cần giao. Nó không nhất thiết cần mật khẩu, ghi chú nội bộ hay lịch sử thao tác của Orders.

### 4.1. Quản lý schema và thay đổi tương thích

Khi có nhiều producer và consumer, schema là một phần của API. Có thể dùng JSON Schema, Avro hoặc Protocol Buffers; với hệ thống nhiều nhóm phát triển, Schema Registry giúp quản lý phiên bản và kiểm tra quy tắc tương thích trước khi triển khai.

Các nguyên tắc tiến hóa thường hữu ích:

- Thêm trường mới theo cách consumer cũ có thể bỏ qua; đặt giá trị mặc định hoặc quy định rõ cách xử lý khi thiếu trường.
- Không đổi ý nghĩa của một trường đang tồn tại.
- Không tái sử dụng tên trường cũ cho một khái niệm khác.
- Consumer cần xử lý giá trị enum chưa biết để tránh lỗi khi producer bổ sung trạng thái mới.
- Không xóa hoặc đổi kiểu trường đang được consumer sử dụng nếu chưa có kế hoạch chuyển đổi.
- Kiểm tra tương thích schema trong quy trình build và triển khai.

Có thể dùng **eventVersion** hoặc phiên bản schema để nhận biết cấu trúc payload. Không phải mọi thay đổi đều cần tạo topic mới. Thay đổi tương thích thường có thể tiến hóa trong cùng hợp đồng. Thay đổi phá vỡ tương thích cần có kế hoạch migration: tạo loại sự kiện hoặc hợp đồng phiên bản mới, chạy song song trong thời gian chuyển tiếp nếu cần, cập nhật consumer, rồi mới ngừng hợp đồng cũ.

Phiên bản trong tên topic và phiên bản schema là hai quyết định khác nhau. Ví dụ **sales.order-events.v1** có thể biểu thị một hợp đồng topic được quản lý theo phiên bản; **eventVersion: 2** có thể biểu thị phiên bản payload của một loại event. Hãy chọn một quy ước nhất quán và ghi rõ trong tài liệu của miền.

## 5. Thiết kế topic và partition theo nhu cầu sử dụng

Topic là đơn vị lưu trữ và vận hành của Kafka. Nên đặt topic theo miền sở hữu hoặc luồng nghiệp vụ có vòng đời rõ ràng, ví dụ:

- **sales.order-events.v1**
- **payments.payment-events.v1**
- **inventory.stock-events.v1**
- **shipping.shipment-events.v1**

Không nên tạo topic riêng cho từng event nhỏ nếu chúng có cùng chủ sở hữu, chính sách lưu giữ và nhóm consumer. Ngược lại, một topic toàn cục chứa mọi sự kiện của mọi miền thường làm mờ quyền sở hữu, chính sách truy cập và cách xử lý dữ liệu. Quyết định tách topic nên dựa trên khác biệt về quyền sở hữu, tải, bảo mật, retention, compaction và cách consumer sử dụng.

### 5.1. Chọn message key

Kafka ghi các bản ghi vào partition. Với cùng một topic, record có cùng key thường được định tuyến đến cùng partition theo partitioner đang dùng. Kafka bảo đảm thứ tự trong một partition; Kafka không bảo đảm thứ tự toàn cục giữa nhiều partition.

Vì vậy, nếu các thay đổi của một đơn hàng phải được xử lý theo thứ tự, dùng **orderId** làm key cho các event thuộc vòng đời đơn hàng:

~~~text
key   = order-10482
value = OrderPlaced(...)
~~~

Nếu dùng **customerId** làm key, tất cả đơn của một khách hàng có thể tập trung vào cùng partition. Điều đó có thể hữu ích nếu consumer cần thứ tự theo khách hàng, nhưng dễ tạo điểm nóng khi một khách hàng phát sinh nhiều sự kiện. Chọn key theo **đối tượng mà thứ tự nghiệp vụ cần được giữ**, không chọn theo trường dễ lấy nhất.

Một số điểm cần lưu ý:

- Thứ tự chỉ được giữ trong phạm vi một partition và theo thứ tự record được ghi vào partition đó.
- Các event có cùng key cần dùng cùng quy tắc partitioning.
- Tăng số partition có thể làm thay đổi partition được chọn cho một key với partitioner theo hash mặc định; nếu thứ tự dài hạn theo key là yêu cầu quan trọng, hãy lên kế hoạch tăng partition cẩn thận.
- Không dựa vào timestamp phía ứng dụng để thay thế thứ tự Kafka. Đồng hồ các máy có thể lệch và event có thể đến trễ.
- Nếu consumer xử lý song song các record trong cùng partition, chính consumer phải bảo toàn thứ tự xử lý khi nghiệp vụ yêu cầu.

### 5.2. Chọn retention và compaction

Retention xác định Kafka giữ record trong bao lâu theo chính sách thời gian hoặc dung lượng. Nó ảnh hưởng trực tiếp đến khả năng replay, phục hồi consumer và chi phí lưu trữ. Hãy chọn khoảng lưu giữ dựa trên thời gian gián đoạn có thể chấp nhận, yêu cầu kiểm toán và nhu cầu tái dựng dữ liệu.

Log compaction giữ lại bản ghi mới nhất theo key sau quá trình compact, phù hợp với topic biểu diễn trạng thái mới nhất hoặc changelog. Nó không thay thế retention cho mọi luồng sự kiện nghiệp vụ: nếu cần lịch sử đầy đủ của từng lần đặt hàng, thanh toán hoặc giao hàng, cần chính sách lưu giữ phù hợp với lịch sử đó.

Replication factor, **min.insync.replicas**, **acks** và cấu hình broker quyết định mức bền vững khi có lỗi broker. Những giá trị này cần được chọn cùng với yêu cầu sẵn sàng và khả năng chịu mất dữ liệu của hệ thống; tăng replication cũng làm tăng chi phí lưu trữ và lưu lượng mạng.

## 6. Bảo đảm xử lý tin cậy: outbox, idempotency và retry

Một luồng sự kiện đúng về mặt nghiệp vụ vẫn có thể gặp lỗi khi ứng dụng dừng giữa hai thao tác. Tình huống phổ biến là dịch vụ vừa cập nhật cơ sở dữ liệu vừa gửi event đến Kafka:

1. Ghi đơn hàng thành công vào database.
2. Ứng dụng dừng trước khi gửi **OrderPlaced**.
3. Database có đơn hàng nhưng consumer không bao giờ nhận được sự kiện.

Chiều ngược lại cũng có thể xảy ra nếu event được gửi trước rồi transaction database rollback. Kafka producer transaction không tự tạo ra một transaction nguyên tử bao trùm database quan hệ và Kafka.

### 6.1. Transactional outbox

Outbox giải quyết khoảng hở giữa ghi dữ liệu nghiệp vụ và ghi nhận sự kiện cần phát. Trong cùng một transaction database, dịch vụ ghi trạng thái nghiệp vụ và một bản ghi vào bảng outbox. Một tiến trình relay hoặc CDC connector đọc outbox rồi xuất bản ghi sang Kafka.

~~~text
BEGIN DATABASE TRANSACTION
  UPDATE orders ...
  INSERT INTO outbox(event_id, aggregate_id, event_type, payload, created_at)
COMMIT

Outbox relay / CDC
  -> publish record to Kafka
  -> mark or checkpoint published record
~~~

Nếu transaction rollback, cả cập nhật đơn hàng và bản ghi outbox đều không tồn tại. Nếu relay gửi lại sau lỗi hoặc mất xác nhận, consumer vẫn có thể nhận trùng; vì vậy outbox cần kết hợp với idempotency. Relay phải có chiến lược checkpoint, retry và xử lý bản ghi lỗi rõ ràng.

Kafka Connect với connector CDC có thể chuyển thay đổi của bảng outbox thành record Kafka. Cần cấu hình connector và định dạng record phù hợp, đồng thời giữ hợp đồng integration event ở tầng ứng dụng hoặc một bước chuyển đổi có chủ đích. Không nên để consumer nghiệp vụ phụ thuộc trực tiếp vào mọi cột nội bộ của bảng đơn hàng.

### 6.2. Consumer idempotent

Kafka thường được thiết kế để consumer có thể nhận lại record khi xử lý thành công nhưng offset chưa được commit, hoặc khi ứng dụng khởi động lại. Vì vậy, handler nên an toàn khi xử lý cùng một event nhiều lần.

Một cách phổ biến là dùng **eventId** làm khóa duy nhất trong bảng inbox hoặc bảng đã xử lý:

1. Consumer nhận event.
2. Trong một transaction database, thử ghi **eventId** vào inbox với unique constraint.
3. Nếu **eventId** đã tồn tại, xem đây là bản trùng và kết thúc an toàn.
4. Nếu là event mới, cập nhật dữ liệu nghiệp vụ và commit cùng transaction.
5. Chỉ xác nhận offset sau khi xử lý đã hoàn tất theo cấu hình listener container.

Việc ghi inbox và cập nhật trạng thái nghiệp vụ cần nằm trong cùng transaction database. Nếu ghi inbox thành công nhưng cập nhật nghiệp vụ thất bại trong một transaction khác, consumer có thể bỏ qua event ở lần nhận lại dù nghiệp vụ chưa được thực hiện.

Idempotency cũng cần áp dụng cho tác động bên ngoài. Ví dụ, nếu consumer gọi cổng thanh toán hoặc API vận chuyển, hãy dùng idempotency key do nhà cung cấp hỗ trợ hoặc lưu trạng thái yêu cầu để tránh gửi cùng một thao tác nhiều lần.

### 6.3. Retry, dead-letter topic và thứ tự

Retry phù hợp khi lỗi có khả năng tạm thời, chẳng hạn dịch vụ phụ thuộc đang quá tải. Cần phân biệt lỗi tạm thời với lỗi dữ liệu hoặc lỗi hợp đồng không thể tự hết:

- Lỗi tạm thời: thử lại với backoff và giới hạn số lần.
- Lỗi không thể xử lý do dữ liệu: chuyển đến dead-letter topic (DLT/DLQ) sau khi ghi log và metadata cần thiết.
- Lỗi schema hoặc phiên bản: sửa tương thích hoặc triển khai consumer phù hợp; retry vô hạn không giải quyết được nguyên nhân.

Retry topic có độ trễ giúp không chặn partition quá lâu, nhưng có thể làm thay đổi thứ tự xử lý. Ví dụ, event **OrderPlaced** bị chuyển sang retry topic trong khi **OrderCancelled** tiếp tục được xử lý ở topic chính; consumer có thể nhìn thấy event hủy trước event đặt. Nếu thứ tự theo aggregate là bắt buộc, cần thiết kế retry theo key và quy trình để các event sau của cùng aggregate không vượt qua event đang lỗi. Một số lựa chọn là tạm dừng partition, giữ trạng thái chờ theo aggregate hoặc dùng cơ chế retry có kiểm soát thứ tự.

DLQ phải có người hoặc quy trình chịu trách nhiệm xử lý. Lưu event vào DLQ mà không có cảnh báo, công cụ xem nguyên nhân và quy trình phát lại chỉ chuyển lỗi sang một nơi khó quan sát hơn. Khi phát lại, cần giữ **eventId** gốc hoặc tạo metadata replay riêng để tránh vô tình xử lý nghiệp vụ hai lần.

### 6.4. Hiểu đúng về exactly-once

Kafka hỗ trợ idempotent producer và transaction để hạn chế duplicate do retry ở phía producer, cũng như hỗ trợ mô hình consume-process-produce có ngữ nghĩa exactly-once trong các trường hợp được cấu hình phù hợp, chẳng hạn Kafka Streams hoặc một transaction Kafka bao gồm đọc và ghi Kafka.

Điều này không đồng nghĩa mọi tác động bên ngoài Kafka chỉ xảy ra đúng một lần. Một lần ghi database, gọi HTTP hoặc gửi lệnh tới nhà cung cấp bên ngoài vẫn cần transaction boundary, outbox/inbox hoặc idempotency riêng. Hãy xác định rõ phạm vi của bảo đảm exactly-once trước khi dùng thuật ngữ này trong yêu cầu hệ thống.

## 7. Tổ chức consumer group theo dịch vụ

Một consumer group đại diện cho một nhóm consumer cùng chia tải đọc một topic. Trong cùng group, mỗi partition tại một thời điểm được gán cho tối đa một consumer trong group. Nếu số consumer vượt số partition, một số consumer sẽ không nhận partition để xử lý.

Các dịch vụ độc lập cần dữ liệu giống nhau nên dùng các group khác nhau:

| Consumer | Consumer group | Mục đích |
|---|---|---|
| Fulfillment | **fulfillment-service** | Bắt đầu xử lý giao hàng sau khi đơn được đặt |
| Analytics | **analytics-order-projection** | Cập nhật mô hình phân tích |
| Notification | **notification-service** | Gửi thông báo phù hợp |
| Risk | **risk-evaluation-service** | Đánh giá tín hiệu rủi ro |

Các instance của cùng một dịch vụ dùng chung **group.id** để chia partition. Nếu Analytics và Fulfillment dùng chung group, chúng sẽ chia nhau record thay vì mỗi dịch vụ nhận đầy đủ luồng sự kiện. Đây là lỗi cấu hình thường gặp khi thiết kế consumer group.

Số partition cần tính đến mức song song mong muốn, throughput, kích thước message và thứ tự theo key. Nhiều partition hơn không phải lúc nào cũng tốt hơn: chúng làm tăng chi phí quản lý, có thể ảnh hưởng thời gian rebalance và khiến việc giữ thứ tự theo key phức tạp hơn khi thay đổi cấu hình.

## 8. Áp dụng với Java và Spring Kafka

Một DTO integration event có thể được biểu diễn bằng Java record. Ví dụ sau minh họa một hợp đồng nhỏ cho **OrderPlaced**:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public record OrderPlacedV1(
    String eventId,
    Instant occurredAt,
    String orderId,
    BigDecimal totalAmount,
    String currency,
    List<OrderLine> items,
    String correlationId
) {
    public record OrderLine(String sku, int quantity) {}
}
~~~

Producer gửi **orderId** làm key để các sự kiện cùng đơn hàng có thể đi vào cùng partition:

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {
    private static final String TOPIC = "sales.order-events.v1";

    private final KafkaTemplate<String, OrderPlacedV1> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderPlacedV1> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderPlacedV1 event) {
        kafkaTemplate.send(TOPIC, event.orderId(), event);
    }
}
~~~

Đoạn code là ví dụ về cách chọn topic và key; trong ứng dụng thật, việc gửi event nên được kích hoạt từ outbox relay nếu cần bảo đảm cập nhật database và công bố sự kiện không bị lệch nhau. Cần cấu hình serializer/deserializer nhất quán ở producer và consumer. Với hợp đồng dùng chung giữa nhiều nhóm, hãy cân nhắc schema format và Schema Registry thay vì để mỗi dịch vụ tự suy luận JSON.

Cấu hình producer minh họa trong Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
~~~

**acks: all** yêu cầu xác nhận từ các replica đang nằm trong ISR theo cấu hình broker; nó cần đi cùng replication factor và **min.insync.replicas** phù hợp. **enable.idempotence** giúp producer xử lý retry an toàn hơn trong phạm vi bảo đảm của Kafka. Cấu hình này không thay thế outbox.

Consumer của dịch vụ Fulfillment có thể dùng listener như sau:

~~~java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderPlacedListener {
    private final FulfillmentHandler handler;

    public OrderPlacedListener(FulfillmentHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(
        topics = "sales.order-events.v1",
        groupId = "fulfillment-service"
    )
    public void onOrderPlaced(OrderPlacedV1 event) {
        handler.handleIdempotently(event);
    }
}
~~~

**handleIdempotently** là nơi áp dụng inbox hoặc cơ chế chống trùng tương đương. Với listener container dùng chế độ xác nhận tự động sau khi listener xử lý thành công, hãy để lỗi được ném ra khi xử lý chưa hoàn tất để error handler thực hiện retry hoặc chuyển DLQ theo cấu hình. Nếu dùng manual acknowledgment, chỉ xác nhận sau khi transaction nghiệp vụ đã commit. Cần kiểm tra **AckMode**, error handler, retry policy và transaction manager trong cấu hình ứng dụng cụ thể; không nên giả định chỉ thêm **@KafkaListener** là đã có bảo đảm xử lý đúng một lần.

## 9. Khi nào dùng Kafka Connect và Kafka Streams?

Kafka Connect phù hợp để đưa dữ liệu giữa Kafka và hệ thống ngoài bằng connector, ví dụ CDC từ database, đồng bộ sang data warehouse hoặc tích hợp một hệ thống lưu trữ. Connect giảm lượng mã tích hợp phải tự viết, nhưng connector không tự quyết định ý nghĩa nghiệp vụ. Nếu CDC đọc thay đổi bảng **orders**, hãy xác định liệu consumer cần dữ liệu thay đổi thô hay cần integration event như **OrderPlaced**. Khi cần hợp đồng nghiệp vụ, hãy tạo bước chuyển đổi và kiểm soát schema rõ ràng.

Kafka Streams phù hợp để xử lý luồng record: lọc, biến đổi, nối stream/table, tổng hợp theo key và xây dựng projection. Ví dụ, một projection có thể tổng hợp số đơn đã đặt theo ngày hoặc tạo read model phục vụ truy vấn. Khi join hoặc aggregate, cần hiểu key, partitioning, state store và thời gian của event. Không nên dùng một stream processor để âm thầm chiếm quyền sở hữu quy tắc nghiệp vụ vốn thuộc miền khác.

Hãy chọn công cụ theo trách nhiệm:

- Connect: tích hợp và di chuyển dữ liệu giữa Kafka với hệ thống ngoài.
- Streams: biến đổi, kết hợp và tổng hợp dữ liệu streaming.
- Dịch vụ miền: thực thi quy tắc nghiệp vụ và phát integration event do miền sở hữu.
- Process manager/Saga: theo dõi một quy trình liên miền có nhiều bước và nhánh kết quả.

## 10. Quan sát và quản trị luồng sự kiện

Một luồng sự kiện chỉ có thể vận hành tốt khi nhóm biết ai sở hữu nó, đang hoạt động ra sao và xử lý lỗi thế nào.

Với mỗi topic, nên ghi lại:

- Miền và nhóm chịu trách nhiệm.
- Ý nghĩa từng event type và schema tương ứng.
- Producer, consumer group đang sử dụng và mục đích sử dụng.
- Key, partition strategy, retention, replication và chính sách truy cập.
- Quy trình xử lý retry, DLQ, replay và thay đổi schema.

Các chỉ số nên theo dõi gồm:

- Consumer lag theo group và partition.
- Tốc độ ghi/đọc, thông lượng và kích thước record.
- Thời gian từ **occurredAt** đến lúc consumer xử lý xong.
- Tỷ lệ lỗi, retry, record vào DLQ và số lần rebalance.
- Tình trạng broker, replica, ISR và dung lượng đĩa.

Đưa **eventId**, **correlationId**, **causationId** và trace context vào log hoặc trace để nối các bước xử lý qua nhiều dịch vụ. Không ghi payload nhạy cảm vào log nếu không có nhu cầu và chính sách bảo vệ phù hợp. Với dữ liệu cá nhân, hãy tối thiểu hóa trường được công bố, xác định thời hạn lưu giữ và giới hạn quyền đọc topic bằng ACL.

Cảnh báo consumer lag nên dựa trên mức trễ nghiệp vụ có thể chấp nhận, không chỉ một con số cố định cho mọi topic. Một topic cập nhật dashboard có thể chịu trễ vài phút; một topic phục vụ xác nhận thanh toán có thể cần ngưỡng thấp hơn nhiều. Mỗi luồng cần SLO và người chịu trách nhiệm rõ ràng.

## 11. Ví dụ tổng hợp: thiết kế luồng đặt hàng

Giả sử yêu cầu là khi khách hàng đặt đơn, hệ thống phải xác nhận thanh toán, giữ chỗ hàng và khởi tạo giao vận. Một thiết kế ban đầu có thể như sau:

| Thành phần | Quyết định |
|---|---|
| Chủ sở hữu **OrderPlaced** | Orders |
| Topic công bố | **sales.order-events.v1** |
| Key | **orderId** |
| Consumer group | Mỗi dịch vụ một group độc lập |
| Chủ sở hữu **PaymentAuthorized** | Payments |
| Chủ sở hữu **StockReserved** | Inventory |
| Lưu sự kiện | Orders ghi outbox cùng transaction tạo đơn |
| Chống xử lý trùng | Consumer lưu **eventId** trong inbox với unique constraint |
| Quy trình nhiều bước | Saga theo dõi kết quả, timeout và hành động bù trừ |
| Theo dõi | Correlation ID, consumer lag, retry và DLQ |

Trình tự xử lý:

1. Orders kiểm tra dữ liệu và quy tắc đặt hàng. Trong một transaction, Orders lưu đơn ở trạng thái chờ xử lý và ghi **OrderPlaced** vào outbox.
2. Outbox relay xuất bản event vào **sales.order-events.v1** với key là **orderId**.
3. Payments nhận event trong group riêng, xử lý idempotent và thực hiện quy trình thanh toán. Payments công bố **PaymentAuthorized** hoặc **PaymentDeclined**.
4. Saga nhận kết quả thanh toán. Nếu được chấp thuận, quy trình yêu cầu Inventory giữ chỗ hàng. Nếu bị từ chối, quy trình chuyển đơn sang trạng thái phù hợp và kết thúc hoặc thực hiện bước bù trừ cần thiết.
5. Inventory công bố **StockReserved** hoặc **StockReservationFailed**. Saga và Orders xử lý kết quả theo quy tắc đã thống nhất.
6. Khi đủ điều kiện, Shipping nhận thông tin cần thiết và tạo lô giao. Shipping công bố các sự kiện thuộc vòng đời giao hàng.
7. Các consumer Analytics hoặc Notification đọc cùng luồng bằng consumer group riêng, không ảnh hưởng đến việc phân phối record của Fulfillment hay Shipping.

Thiết kế này cho phép từng miền thay đổi cách lưu trữ và xử lý nội bộ, miễn là vẫn giữ hợp đồng đã công bố. Nó cũng làm rõ các trường hợp phải xử lý: event bị gửi lại, consumer dừng giữa chừng, thanh toán thất bại, giữ chỗ hàng hết hạn và một bước xử lý kéo dài hơn thời gian dự kiến.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng một topic cho mọi loại event của mọi miền | Khó xác định chủ sở hữu, ACL và retention | Tách theo miền hoặc luồng có chính sách vận hành khác nhau |
| Tạo topic cho từng event nhỏ | Tăng gánh nặng quản trị và cấu hình | Gom các event cùng miền, vòng đời và chính sách |
| Công bố tên bảng hoặc CRUD event làm hợp đồng nghiệp vụ | Consumer phụ thuộc cấu trúc database | Chuyển thành integration event có ngữ nghĩa rõ |
| Dùng **customerId** làm key dù cần thứ tự theo đơn | Các event của một đơn có thể không được xử lý theo thứ tự mong muốn | Chọn key theo aggregate cần giữ thứ tự |
| Mọi consumer dùng chung **group.id** | Các dịch vụ chia nhau record và bỏ lỡ dữ liệu cần nhận | Dùng group riêng cho từng ứng dụng độc lập |
| Giả định Kafka bảo đảm thứ tự toàn cục | Kết quả sai khi topic có nhiều partition | Thiết kế thứ tự trong phạm vi key/partition |
| Commit offset trước khi lưu kết quả | Có thể mất xử lý khi ứng dụng gặp lỗi | Commit sau khi xử lý bền vững thành công |
| Retry vô hạn hoặc không có DLQ | Partition có thể bị chặn và lỗi khó điều tra | Phân loại lỗi, giới hạn retry và theo dõi DLQ |
| Tin rằng exactly-once bao phủ cả database và HTTP | Tác động bên ngoài vẫn có thể bị lặp hoặc lệch | Dùng outbox/inbox và idempotency tại ranh giới ngoài Kafka |
| Thay đổi schema không kiểm tra consumer | Consumer cũ có thể ngừng hoạt động | Kiểm tra compatibility và triển khai theo lộ trình |

## 13. Checklist trước khi đưa một luồng vào vận hành

Trước khi tạo topic và triển khai producer/consumer, hãy kiểm tra:

- [ ] Đã xác định miền sở hữu và ý nghĩa nghiệp vụ của từng event.
- [ ] Event mô tả sự thật đã xảy ra, không phải command hoặc thông báo CRUD mơ hồ.
- [ ] Payload chỉ chứa dữ liệu consumer cần và không làm lộ chi tiết nội bộ không cần thiết.
- [ ] Có **eventId**, loại/phiên bản event, thời điểm xảy ra và thông tin correlation phù hợp.
- [ ] Schema có quy tắc tương thích và quy trình phát hành phiên bản.
- [ ] Topic có owner, key, partition, retention, replication và ACL rõ ràng.
- [ ] Key phản ánh phạm vi cần giữ thứ tự; đã hiểu giới hạn thứ tự của Kafka.
- [ ] Producer có chiến lược gửi tin tin cậy; dùng outbox khi cần đồng bộ với transaction database.
- [ ] Consumer có idempotency và chỉ xác nhận offset sau khi xử lý bền vững.
- [ ] Retry, DLQ, replay và xử lý poison message đã được xác định.
- [ ] Consumer group độc lập cho từng ứng dụng cần nhận toàn bộ luồng.
- [ ] Có log/trace, cảnh báo lag, người trực và quy trình khôi phục.

## 14. Bài tập tự kiểm tra

**Bài tập 1:** Một dịch vụ Inventory phát sự kiện **ProductRowUpdated** mỗi khi số lượng tồn thay đổi. Orders cần biết khi nào có thể giữ chỗ hàng. Hãy đề xuất integration event phù hợp hơn, xác định miền sở hữu event và các trường tối thiểu cần công bố.

**Gợi ý:** Bắt đầu từ sự thật mà Orders cần biết, chẳng hạn **StockReserved** hoặc **StockReservationFailed**. Inventory vẫn có thể dùng CDC cho mục đích kỹ thuật, nhưng hợp đồng liên miền nên thể hiện kết quả nghiệp vụ.

**Bài tập 2:** Một topic có 12 partition. Fulfillment và Analytics đều cần nhận mọi **OrderPlaced**. Hãy chọn số consumer group và giải thích cách các instance chia tải.

**Gợi ý:** Dùng một group cho Fulfillment và một group cho Analytics. Trong từng group, các instance chia partition; giữa hai group, mỗi group nhận luồng độc lập.

**Bài tập 3:** Consumer đã cập nhật database nhưng bị dừng trước khi offset được commit. Khi khởi động lại, event được gửi lại. Hãy mô tả cách tránh tạo hai lô giao hàng.

**Gợi ý:** Dùng **eventId** hoặc một business idempotency key với unique constraint trong transaction cùng cập nhật nghiệp vụ. Nếu việc tạo lô giao gọi hệ thống bên ngoài, cần idempotency key hoặc cơ chế đối soát ở ranh giới đó.

Thiết kế luồng sự kiện tốt giúp mỗi miền công bố những sự thật mà nó sở hữu, consumer chỉ phụ thuộc vào hợp đồng cần thiết và Kafka đảm nhiệm việc phân phối, lưu giữ, mở rộng theo partition. Khi ranh giới nghiệp vụ, schema, key, consumer group và chiến lược phục hồi được quyết định cùng nhau, hệ thống event streaming sẽ dễ phát triển và vận hành hơn.

