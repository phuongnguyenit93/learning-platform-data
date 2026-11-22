# Sự kiện, thông điệp và luồng sự kiện khác nhau thế nào

Khi xây dựng hệ thống event streaming với **Apache Kafka**, ba thuật ngữ *sự kiện* (event), *thông điệp* (message) và *luồng sự kiện* (event stream) thường xuất hiện cạnh nhau. Tài liệu Kafka đôi khi dùng “event”, “message” và “record” gần như thay thế nhau. Tuy vậy, khi thiết kế hệ thống, phân biệt ý nghĩa của chúng giúp xác định đúng dữ liệu cần phát, cách đóng gói dữ liệu, cách tổ chức topic và cách các consumer xử lý thứ tự.

Có thể nhớ ba khái niệm theo ba câu hỏi:

- **Sự kiện:** Điều gì đã xảy ra trong nghiệp vụ?
- **Thông điệp:** Dữ liệu nào đang được gửi hoặc lưu trữ để truyền điều đó?
- **Luồng sự kiện:** Những sự kiện nào diễn ra theo chuỗi thời gian và được xử lý như một dòng liên tục?

Một sự kiện có thể được đóng gói trong một thông điệp Kafka; nhiều thông điệp tạo thành một luồng. Chúng liên quan với nhau nhưng không cùng một khái niệm.

## 1. Sự kiện là điều đã xảy ra

**Sự kiện** là một sự việc hoặc thay đổi trạng thái đã xảy ra và có ý nghĩa đối với nghiệp vụ. Nó mô tả một sự thật trong quá khứ, chẳng hạn:

- **OrderPlaced:** khách hàng đã đặt đơn hàng.
- **PaymentAuthorized:** khoản thanh toán đã được xác nhận.
- **InventoryReserved:** hàng trong kho đã được giữ.
- **OrderShipped:** đơn hàng đã được bàn giao cho đơn vị vận chuyển.

Một sự kiện thường có các đặc điểm sau:

1. **Mang ý nghĩa nghiệp vụ.** Tên và dữ liệu của sự kiện cho biết hệ thống vừa ghi nhận điều gì, thay vì chỉ mô tả một thao tác kỹ thuật.
2. **Diễn tả điều đã xảy ra.** Tên sự kiện thường dùng dạng quá khứ như OrderPlaced, UserRegistered, InvoiceIssued.
3. **Có thời điểm xảy ra.** Thời điểm nghiệp vụ xảy ra (occurredAt) hữu ích cho việc kiểm toán, phân tích và xử lý theo thời gian.
4. **Có dữ liệu để giải thích sự việc.** Ví dụ, sự kiện đặt hàng có mã đơn, mã khách hàng, tổng tiền và các dòng hàng liên quan.
5. **Được xem là bất biến về mặt ý nghĩa.** Khi một sự kiện đã được công bố, không nên âm thầm sửa nó thành một sự thật khác. Nếu nghiệp vụ thay đổi hoặc cần đính chính, hệ thống thường phát thêm sự kiện điều chỉnh hoặc bù trừ.

Ví dụ, khi khách hàng đặt đơn ORD-1042, dịch vụ đơn hàng phát sinh sự kiện OrderPlaced. Sự kiện này không phải yêu cầu “hãy tạo đơn hàng”; nó là thông báo rằng việc đặt đơn đã hoàn tất.

### Sự kiện khác với lệnh

Sự kiện và lệnh (command) thường xuất hiện trong cùng một hệ thống nhưng biểu đạt hai ý định khác nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Command | Yêu cầu một thành phần thực hiện hành động | PlaceOrder, CancelOrder, ShipOrder |
| Event | Ghi nhận hành động hoặc thay đổi đã xảy ra | OrderPlaced, OrderCancelled, OrderShipped |

Một lệnh có thể bị từ chối hoặc thất bại; vì vậy, không được coi việc gửi lệnh là bằng chứng sự kiện đã xảy ra. Chỉ phát OrderPlaced sau khi dịch vụ đã chấp nhận và ghi nhận đơn hàng theo quy tắc nghiệp vụ.

## 2. Thông điệp là đơn vị dữ liệu được truyền tải

**Thông điệp** là đơn vị dữ liệu được gửi từ thành phần này sang thành phần khác hoặc được lưu trong một hệ thống truyền tin. Thông điệp trả lời câu hỏi “dữ liệu nào đang được vận chuyển?”. Nó có thể chứa một sự kiện, nhưng không phải mọi thông điệp đều là sự kiện.

Ví dụ, một thông điệp có thể mang:

- Sự kiện nghiệp vụ như OrderPlaced.
- Lệnh như ShipOrder.
- Yêu cầu hoặc phản hồi giữa hai dịch vụ.
- Tín hiệu kỹ thuật như heartbeat hoặc thông tin điều phối.

Trong Apache Kafka, đơn vị được producer ghi vào topic được gọi chính xác hơn là **record** (bản ghi). Trong giao tiếp thông thường, người phát triển cũng hay gọi nó là message hoặc event. Một Kafka record có các thành phần dữ liệu chính:

- **Key:** khóa tùy chọn, thường dùng để xác định thực thể liên quan và quyết định record đi vào partition nào.
- **Value:** phần dữ liệu chính; Kafka lưu value dưới dạng byte sau khi producer tuần tự hóa dữ liệu.
- **Headers:** các cặp khóa-giá trị bổ sung, ví dụ loại nội dung, mã tương quan hoặc thông tin truy vết.
- **Timestamp:** dấu thời gian của record theo cấu hình timestamp của topic/producer.

Khi record được ghi vào Kafka, broker xác định thêm vị trí lưu trữ là **topic, partition và offset**. Topic, partition và offset là thông tin định vị record trong log; chúng không đồng nghĩa với các trường nghiệp vụ bên trong value.

Ví dụ, một sự kiện đặt hàng có thể được biểu diễn bằng value JSON sau:

~~~json
{
  "eventId": "evt-7f31",
  "eventType": "OrderPlaced",
  "schemaVersion": 1,
  "occurredAt": "2026-11-20T10:15:30Z",
  "aggregateId": "ORD-1042",
  "data": {
    "customerId": "CUS-018",
    "totalAmount": 1250000,
    "currency": "VND"
  }
}
~~~

Producer có thể gửi record này với key là ORD-1042, value là JSON ở trên và header trace-id để theo dõi xuyên suốt các dịch vụ. Sau khi Kafka ghi record, consumer có thể quan sát thông tin tương tự:

~~~text
topic:     orders.events
partition: 2
offset:    481
key:       ORD-1042
value:     {"eventId":"evt-7f31","eventType":"OrderPlaced", ...}
headers:   trace-id=trace-92ab
~~~

Các giá trị partition và offset trong ví dụ chỉ để minh họa. Broker cấp offset trong phạm vi từng partition. Offset xác định vị trí record trong partition, không phải mã đơn hàng, không phải thời điểm nghiệp vụ và cũng không phải số thứ tự toàn cục của cả topic.

Điểm cần nhớ: **event mô tả ý nghĩa; message/record là hình thức vận chuyển và lưu trữ ý nghĩa đó.** Kafka không tự hiểu OrderPlaced có nghĩa gì. Broker xử lý record, key, value, header, timestamp và vị trí log; ứng dụng chịu trách nhiệm diễn giải nội dung nghiệp vụ.

## 3. Luồng sự kiện là chuỗi sự kiện theo thời gian

**Luồng sự kiện** (event stream) là một chuỗi các sự kiện được tạo ra theo thời gian và có thể được xử lý liên tục. Luồng có thể tiếp tục phát sinh khi hệ thống hoạt động; vì thế, người tiêu thụ thường không biết trước điểm kết thúc của nó.

Ví dụ, vòng đời của một đơn hàng có thể tạo ra chuỗi:

~~~text
OrderPlaced
    -> PaymentAuthorized
    -> InventoryReserved
    -> OrderPacked
    -> OrderShipped
~~~

Mỗi phần tử là một sự kiện riêng. Khi được công bố dưới dạng record, các record đó hợp thành luồng dữ liệu mà những dịch vụ khác có thể đọc để cập nhật trạng thái, gửi thông báo hoặc phân tích hoạt động.

Luồng sự kiện không nhất thiết là một tệp hoặc một đối tượng duy nhất. Nó là cách nhìn logic về một chuỗi dữ liệu. Trong Kafka, luồng thường được tổ chức và lưu trữ bằng một hoặc nhiều topic. Một topic có thể có nhiều partition; do đó cần hiểu giới hạn thứ tự khi nói về “chuỗi”.

### Ba khái niệm trong cùng một ví dụ

Giả sử khách hàng đặt đơn ORD-1042:

1. **Sự kiện:** OrderPlaced — sự thật nghiệp vụ rằng đơn hàng đã được tạo.
2. **Thông điệp/record:** record Kafka có key ORD-1042, value chứa dữ liệu OrderPlaced, cùng headers và timestamp.
3. **Luồng sự kiện:** chuỗi record phản ánh các thay đổi của đơn hàng, chẳng hạn OrderPlaced, PaymentAuthorized rồi OrderShipped.

~~~mermaid
flowchart LR
    E["Sự kiện nghiệp vụ<br/>OrderPlaced"] --> R["Kafka record<br/>key + value + headers"]
    R --> T["Topic: orders.events"]
    T --> P0["Partition 0"]
    T --> P1["Partition 1"]
    T --> P2["Partition 2"]
    P0 --> C1["Consumer group<br/>fulfillment"]
    P1 --> C1
    P2 --> C1
    P0 --> C2["Consumer group<br/>analytics"]
    P1 --> C2
    P2 --> C2
~~~

Sơ đồ cho thấy cùng một luồng được nhiều consumer group sử dụng cho các mục đích khác nhau. Mỗi group quản lý tiến độ đọc riêng; việc group phân tích đã đọc record không làm record biến mất khỏi Kafka hay ngăn group xử lý đơn hàng đọc record đó.

## 4. Kafka tổ chức luồng sự kiện như thế nào?

Để ánh xạ ba khái niệm trên vào Kafka, cần phân biệt các thành phần sau.

### Producer tạo và gửi record

Producer là ứng dụng hoặc thành phần tạo record rồi gửi đến Kafka. Trong hệ thống hướng sự kiện, producer thường phát record mang một sự kiện nghiệp vụ sau khi thay đổi tương ứng đã được ghi nhận.

Ví dụ, Order Service ghi nhận đơn hàng thành công rồi gửi OrderPlaced đến topic orders.events. Producer có thể chọn key là mã đơn hàng để các sự kiện của cùng đơn hàng thường được định tuyến đến cùng partition.

### Topic đặt tên cho nhóm record

Topic là tên logic để tổ chức một nhóm record có cùng mục đích hoặc chủ đề, ví dụ:

- orders.events
- payments.events
- inventory.events

Topic giúp producer và consumer thống nhất nơi ghi và nơi đọc dữ liệu. Topic không tự đảm bảo rằng mọi record bên trong đều có cùng một kiểu sự kiện; quy ước nội dung và schema vẫn cần được ứng dụng quản lý.

### Partition là log có thứ tự

Một topic được chia thành một hoặc nhiều partition. Mỗi partition là một log được nối thêm record. Trong một partition, Kafka duy trì thứ tự ghi và gán offset cho record.

Nếu producer gửi các sự kiện có cùng key, partitioner mặc định thường định tuyến chúng vào cùng partition. Đây là cách phổ biến để giữ thứ tự xử lý theo một thực thể, chẳng hạn mọi sự kiện của ORD-1042.

Thứ tự chỉ được đảm bảo trong phạm vi một partition. Khi topic có nhiều partition, không tồn tại một thứ tự tổng thể được Kafka đảm bảo giữa tất cả partition. Consumer có thể đọc các partition song song, nên không thể suy ra sự kiện ở partition 0 luôn xảy ra trước sự kiện ở partition 1 chỉ bằng cách so sánh offset.

Nếu nghiệp vụ cần thứ tự cho một đơn hàng, hãy chọn key phù hợp như orderId và bảo đảm các sự kiện liên quan được ghi vào cùng topic/partition theo cùng quy tắc định tuyến. Khi thay đổi số partition hoặc partitioner, cần đánh giá lại cách phân phối key và giả định về thứ tự.

### Offset cho biết vị trí đọc

Offset là vị trí của record trong một partition. Consumer dùng offset đã đọc hoặc đã commit để tiếp tục từ vị trí phù hợp sau khi khởi động lại.

Offset không phải:

- Mã định danh duy nhất toàn hệ thống cho sự kiện nghiệp vụ.
- Dấu thời gian chính xác cho thời điểm sự kiện xảy ra.
- Một bộ đếm chung cho tất cả partition trong topic.

Vì vậy, ứng dụng vẫn nên có eventId và thời điểm nghiệp vụ như occurredAt khi cần nhận diện, chống xử lý trùng hoặc phân tích thời gian.

### Consumer group cho phép nhiều ứng dụng đọc độc lập

Consumer đọc record từ topic. Các consumer có cùng group.id tạo thành một consumer group. Trong một group, các partition được phân phối cho các consumer thành viên để xử lý song song; tại một thời điểm, một partition chỉ được gán cho tối đa một consumer trong cùng group.

Các group khác nhau có thể đọc cùng một topic độc lập. Chẳng hạn:

- Group fulfillment đọc orders.events để chuẩn bị giao hàng.
- Group notification đọc cùng topic để gửi email hoặc thông báo cho khách hàng.
- Group analytics đọc cùng topic để tổng hợp số liệu.

Mỗi group có tiến độ đọc riêng cho từng partition. Điều này cho phép nhiều ứng dụng phản ứng với cùng một sự kiện mà không phải gọi trực tiếp lẫn nhau.

### Retention cho phép đọc lại dữ liệu

Kafka lưu record theo chính sách retention của topic hoặc cấu hình broker, chẳng hạn theo thời gian hoặc dung lượng. Record không tự động bị xóa chỉ vì một consumer đã đọc nó. Do đó, một consumer group khác có thể đọc cùng dữ liệu, và một group có thể đọc lại dữ liệu nếu record vẫn còn trong log và tiến độ đọc được đặt lại phù hợp.

Với topic dùng log compaction, Kafka có thể giữ lại giá trị mới nhất theo key thay vì giữ mọi phiên bản cũ. Vì vậy, cần chọn chính sách lưu trữ dựa trên mục đích dữ liệu; không nên mặc định mọi topic đều lưu lịch sử đầy đủ vô thời hạn.

## 5. Vì sao phân biệt ba khái niệm lại quan trọng?

Phân biệt đúng giúp giải quyết các vấn đề thiết kế thường gặp:

| Câu hỏi thiết kế | Khái niệm cần tập trung | Điều cần quyết định |
|---|---|---|
| Dịch vụ cần thông báo điều gì? | Sự kiện | Tên, ý nghĩa nghiệp vụ, thời điểm và dữ liệu của event |
| Dữ liệu được đóng gói ra sao? | Thông điệp/record | Key, value, headers, serialization và schema |
| Dữ liệu được nhóm và đọc liên tục thế nào? | Luồng sự kiện | Topic, partition, key, consumer group và retention |
| Làm sao giữ thứ tự cho một đơn hàng? | Luồng và partition | Chọn key theo orderId, kiểm tra quy tắc phân vùng |
| Làm sao tránh xử lý một sự kiện hai lần? | Sự kiện và consumer | Dùng eventId, xử lý idempotent và quản lý offset phù hợp |
| Làm sao cho dịch vụ mới đọc dữ liệu cũ? | Luồng và retention | Chính sách lưu trữ và vị trí bắt đầu đọc của consumer group |

Một số nguyên tắc thực hành:

- **Đặt tên event theo sự thật đã xảy ra.** PaymentCaptured nói rõ việc thanh toán đã được ghi nhận; CapturePayment là một yêu cầu thực hiện hành động.
- **Dùng event ID ổn định.** Khi consumer gặp lại cùng một sự kiện do retry, khởi động lại hoặc cơ chế giao nhận, eventId hỗ trợ nhận diện và chống áp dụng tác động nghiệp vụ nhiều lần.
- **Thiết kế schema có phiên bản.** Producer và consumer có thể được triển khai ở thời điểm khác nhau. Schema rõ ràng và quy tắc tương thích giúp tránh làm hỏng consumer cũ khi bổ sung trường.
- **Chọn key theo nhu cầu thứ tự và phân phối tải.** Key theo thực thể giúp gom sự kiện liên quan vào cùng partition, nhưng một key quá nóng có thể tạo partition mất cân bằng.
- **Không dùng offset thay cho định danh nghiệp vụ.** Offset chỉ có ý nghĩa trong một partition; eventId, orderId hoặc mã nghiệp vụ mới phù hợp cho đối chiếu và liên kết dữ liệu.
- **Thiết kế consumer có thể xử lý lặp.** Consumer có thể đọc lại record sau lỗi hoặc khi tiến độ commit chưa phản ánh chính xác tác động đã thực hiện. Các thao tác ghi dữ liệu nên có cơ chế idempotency hoặc phối hợp giao dịch phù hợp.

## 6. Những nhầm lẫn thường gặp

**“Mọi message đều là event.”** Không đúng. Message chỉ nói đến đơn vị truyền tải. Một message có thể mang command, request, response hoặc tín hiệu kỹ thuật. Chỉ gọi nó là event khi nội dung thực sự ghi nhận một sự việc đã xảy ra.

**“Kafka topic chính là một luồng có thứ tự toàn phần.”** Không đúng khi topic có nhiều partition. Kafka giữ thứ tự trong từng partition; giữa các partition không có thứ tự tổng thể được đảm bảo.

**“Consumer đọc xong thì Kafka xóa message.”** Không đúng với cách Kafka lưu log. Record được giữ theo chính sách retention hoặc compaction, độc lập với việc một consumer group đã đọc đến đâu.

**“Offset cho biết sự kiện xảy ra lúc nào.”** Không đúng. Offset là vị trí trong partition. Muốn biết thời điểm nghiệp vụ, hãy lưu occurredAt; muốn biết vị trí record trong Kafka, hãy dùng partition và offset.

**“Có event stream nghĩa là đã triển khai event sourcing.”** Không nhất thiết. Event streaming là cách công bố, lưu trữ và xử lý luồng record. Event sourcing là một cách thiết kế trạng thái nghiệp vụ, trong đó lịch sử sự kiện được dùng làm nguồn dữ liệu để tái dựng trạng thái. Một hệ thống dùng Kafka để truyền event không tự động trở thành hệ thống event sourcing; điều đó còn phụ thuộc vào mô hình lưu trữ, tính đầy đủ của lịch sử và quy tắc khôi phục trạng thái.

## 7. Tự kiểm tra cách hiểu

1. OrderPlaced là gì? — Là sự kiện, vì nó ghi nhận đơn hàng đã được đặt.
2. JSON chứa OrderPlaced được producer gửi vào Kafka là gì? — Là value của một Kafka record; record đó là đơn vị thông điệp được truyền tải.
3. Chuỗi OrderPlaced, PaymentAuthorized, OrderShipped được đọc liên tục là gì? — Là một luồng sự kiện.
4. ShipOrder là gì? — Là command, vì nó yêu cầu thực hiện hành động giao hàng.
5. Hai consumer group đọc cùng một topic có dùng chung tiến độ offset không? — Không. Mỗi group quản lý tiến độ riêng.
6. Nếu hai sự kiện có cùng key trong cùng partition, Kafka có giữ thứ tự ghi của chúng không? — Có, trong partition đó. Không thể suy rộng thành thứ tự toàn cục giữa nhiều partition.

Khi thiết kế một luồng Kafka, hãy bắt đầu từ ý nghĩa nghiệp vụ của sự kiện, xác định record cần mang dữ liệu và metadata nào, sau đó mới chọn topic, key, partition và consumer group. Cách đi từ ý nghĩa đến cách truyền tải rồi đến cách tổ chức luồng giúp hệ thống dễ mở rộng, dễ theo dõi và dễ xử lý lại khi cần.

