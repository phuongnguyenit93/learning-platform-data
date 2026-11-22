# Vai trò của hàng đợi, chủ đề và nhật ký sự kiện

> **Chủ đề:** Software Design Architecture System Architecture Microservices  
> **Nhánh kiến thức:** Giao tiếp bất đồng bộ  
> **Phạm vi:** Hiểu queue (hàng đợi), topic (chủ đề phát tin) và event log (nhật ký sự kiện); chọn mô hình phù hợp với công việc và các sự kiện nghiệp vụ; thiết kế consumer, lưu giữ, phát lại, xử lý lỗi và vận hành trong hệ thống phân tán.

## 1. Vì sao cần ba cách tổ chức thông điệp?

Trong hệ thống nhiều module hoặc microservices, các thành phần không phải lúc nào cũng cần gọi trực tiếp và chờ nhau. Khi đơn hàng được xác nhận, một thành phần có thể gửi email, một thành phần cập nhật tìm kiếm, một thành phần ghi dữ liệu phân tích. Khi người dùng tải video, hệ thống có thể tiếp nhận yêu cầu ngay và chuyển xử lý nặng sang worker. Khi hệ thống tính toán lại bảng xếp hạng, nhiều consumer có thể cần đọc cùng một dòng thay đổi dữ liệu ở những thời điểm khác nhau.

Những nhu cầu này liên quan đến ba câu hỏi độc lập:

1. **Ai cần nhận thông điệp?** Một worker thực thi công việc, nhiều hệ thống quan tâm cùng một sự kiện, hay nhiều nhóm consumer đọc một luồng lịch sử?
2. **Thông điệp tồn tại bao lâu?** Chỉ cần đến khi hoàn thành và được xác nhận, lưu theo từng subscription, hay được giữ lại theo thời gian/dung lượng/chính sách?
3. **Consumer theo dõi tiến độ bằng gì?** Lấy một message rồi acknowledge, mỗi subscription có trạng thái riêng, hay lưu offset để có thể đọc lại một phần lịch sử?

**Hàng đợi (queue)** thường phù hợp phân công công việc cho một trong nhiều worker. **Chủ đề (topic)** phù hợp công bố một thông điệp cho nhiều nhóm người nhận độc lập. **Nhật ký sự kiện (event log/stream)** phù hợp lưu một chuỗi bản ghi có thứ tự cục bộ, để consumer quản lý vị trí đã đọc và có khả năng đọc lại khi dữ liệu còn được giữ.

Ba khái niệm này không nhất thiết tương ứng với ba sản phẩm công nghệ khác nhau. Một broker có thể cung cấp nhiều mô hình. Ví dụ, một topic trong hệ sinh thái streaming có thể chính là một log phân vùng; mô hình subscription của hệ thống publish–subscribe có thể cấp một hàng đợi logic cho từng người nhận. Cần hiểu **hợp đồng hành vi** thay vì chỉ nhìn tên API.

### Mục tiêu học tập

- Giải thích sự khác nhau giữa queue, topic và event log bằng cách phân phối, xác nhận, lưu giữ và phát lại.
- Phân biệt command/job với domain event và integration event.
- Thiết kế luồng giao tiếp bất đồng bộ cho xử lý nền, fan-out và xây dựng read model.
- Hiểu delivery semantics, idempotency, ordering, consumer groups, retry và dead-letter queue.
- Biết cách kiểm soát backlog, thông lượng, độ trễ, quota, schema và an toàn dữ liệu.
- Đưa ra quyết định dựa trên nhu cầu nghiệp vụ thay vì mặc định một broker cho tất cả.

## 2. Mô hình tư duy: thông điệp, kênh và người nhận

Một hệ thống giao tiếp bất đồng bộ thường có:

- **Producer/publisher:** bên tạo command hoặc công bố sự kiện.
- **Message:** nội dung thông tin cùng định danh, thời điểm, khóa phân vùng và metadata.
- **Broker/transport:** trung gian nhận, giữ, chuyển hoặc cho phép đọc lại message.
- **Queue/topic/stream:** cách nhóm và phân phối message trong broker.
- **Consumer/worker:** phần xử lý message.
- **Ack/offset/checkpoint:** bằng chứng hoặc vị trí mà consumer đã xử lý tới.
- **Dead-letter path:** nơi giữ các message lỗi cần điều tra hoặc thao tác khôi phục.
- **Ownership và contract:** ai chịu trách nhiệm ý nghĩa, version, xử lý lỗi và thời hạn tồn tại của dữ liệu.

Một thiết kế tốt cần xác định cả **ý nghĩa nghiệp vụ** và **ngữ nghĩa truyền tải**. “Đã phát sự kiện” chưa chứng minh “consumer đã hoàn thành nghiệp vụ”. “Queue trống” cũng không chứng minh tất cả công việc đã thành công; có thể message đã bị ack nhầm, bị chuyển DLQ hoặc kết quả xử lý bị lỗi.

### Ba hình dung nhanh

~~~text
QUEUE — chia việc giữa các worker trong một nhóm logic

 Producer ---> [ Queue: GenerateReport ] ---> Worker A
                                      \-----> Worker B
                                      \-----> Worker C
 Mỗi công việc thường do một worker trong nhóm xử lý
 tại một thời điểm; lỗi/timeout có thể gây giao lại.

TOPIC — một sự kiện cho nhiều nhóm quan tâm

 Publisher ---> [ Topic: OrderPlaced ] ---+--> Subscription Email
                                         +--> Subscription Search
                                         +--> Subscription Analytics

LOG — các bản ghi tồn tại theo vị trí trong chuỗi

 Producer ---> [ Partition 0: e0 e1 e2 e3 e4 ... ]
                           |         |
                        Group A    Group B
                       offset=3   offset=1
 Các nhóm có thể đi với tốc độ khác nhau và đọc lại
 bản ghi khi chính sách lưu giữ vẫn cho phép.
~~~

Sơ đồ nhằm thể hiện mô hình logic. Một broker thực tế có thể kết hợp queue, subscription, partition và log ở những lớp khác nhau.

## 3. Hàng đợi (queue): giao việc để xử lý

### 3.1. Vấn đề queue giải quyết

Một API nhận yêu cầu tạo báo cáo 50.000 trang. Chạy ngay trong HTTP request có thể làm request timeout và tiêu tốn tài nguyên. Thay vào đó API tạo bản ghi job, gửi một task tới queue, trả mã theo dõi; worker lấy task khi có khả năng xử lý.

Đây là mô hình **work queue/competing consumers**:

~~~text
User --> Report API --> Job Store --> Queue
                                       |
                    +------------------+------------------+
                    v                  v                  v
                 Worker 1           Worker 2           Worker 3
                    \                  |                  /
                     +-------> Result Store <------------+
                                   |
                              Status API
~~~

Các worker cùng xử lý một loại việc. Mục tiêu thông thường là **mỗi job đạt kết quả đúng một lần về mặt nghiệp vụ**, mặc dù message có thể được giao lại hoặc task có nhiều attempt.

### 3.2. Semantics cần định nghĩa

- **Enqueue:** producer gửi một yêu cầu xử lý, cần biết khi nào yêu cầu được lưu bền vững.
- **Delivery/receive:** một worker nhận được quyền xử lý hoặc một bản sao message.
- **Visibility/lease:** khi đang xử lý, message có thể tạm ẩn khỏi worker khác; nếu worker mất kết nối hoặc quá hạn, message có thể xuất hiện lại.
- **Ack:** worker xác nhận đã xử lý đến điểm đủ an toàn; broker có thể xóa hoặc đánh dấu message đã hoàn tất.
- **Nack/requeue:** worker báo chưa xử lý được và đưa message trở lại hoặc chuyển sang lối khác.
- **Retry/DLQ:** chiến lược xử lý lỗi tạm thời, lỗi vĩnh viễn và message lặp lỗi.

Điểm mấu chốt là **ack không tự động có nghĩa nghiệp vụ thành công**. Nếu worker ack trước khi ghi kết quả, worker crash có thể khiến job mất. Nếu worker ghi kết quả xong nhưng crash trước ack, message được giao lại; tác dụng phụ phải chịu được xử lý lặp.

### 3.3. Queue phù hợp khi nào?

- Tạo thumbnail, encode video, lập báo cáo, import tệp.
- Xử lý email/SMS do một hệ thống thông báo chịu trách nhiệm.
- Gọi đối tác có quota/rate limit, cần giới hạn concurrency.
- Chạy các tác vụ độc lập, có thể xử lý bởi bất kỳ worker đủ quyền và năng lực.
- Giảm áp lực cho một downstream chậm bằng việc đệm tác vụ.

Queue **không mặc định** là nơi lưu lịch sử sự kiện nghiệp vụ lâu dài. Nếu cần một hệ khác xây lại trạng thái từ sự kiện trong quá khứ, phải xem broker có lưu/replay được không hoặc bổ sung event log.

### 3.4. Queue không bảo đảm tuyệt đối “một lần”

Một số broker có chế độ FIFO hoặc các cơ chế chống trùng nhất định, nhưng trong thiết kế thực tế thường phải chuẩn bị cho việc consumer nhận lại sau timeout, reconnect hoặc failover. Câu “một job đi cho một worker” mô tả **phân phối tại thời điểm giao**, không phải tuyên bố rằng sẽ chỉ có một lần xử lý trong toàn bộ vòng đời.

## 4. Chủ đề (topic): phân phối một tín hiệu cho nhiều nhóm độc lập

### 4.1. Publish–subscribe và fan-out

Sau khi Order context ghi nhận **OrderPlaced**, nhiều đơn vị cần phản ứng:

- Notifications gửi thông báo.
- Search cập nhật chỉ mục.
- Analytics cập nhật số liệu.
- Loyalty kiểm tra chương trình điểm thưởng.
- Fraud Monitoring chạy phân tích riêng nếu cần.

Ordering không nên hard-code một vòng gọi trực tiếp đến tất cả các hệ thống này. Nó công bố một sự kiện nghiệp vụ có hợp đồng rõ ràng; mỗi bên tạo subscription nếu thực sự cần.

~~~text
                      +-----------------> Notifications
                      |
Ordering --> Topic: OrderPlaced ------------> Analytics
                      |
                      +-----------------> Search Projection
                      |
                      +-----------------> Loyalty
~~~

Khái niệm trọng tâm của topic là **phân nhóm theo chủ đề quan tâm**. Một message có thể được chuyển tới **từng subscription độc lập**, mỗi subscription có thể có nhiều worker cạnh tranh để xử lý phần việc của mình.

### 4.2. Consumer độc lập ở cấp nhóm, không phải từng replica

Nếu Analytics có ba replica cùng một subscription/group, mục đích thường là chia tải: một message được nhóm Analytics xử lý bởi một replica theo cơ chế broker cung cấp. Còn Notifications, Search và Analytics là **ba nhóm khác nhau**, nên mỗi nhóm nhận bản sao logic của event.

Nhầm lẫn phổ biến: tạo ba replica consumer rồi kỳ vọng mỗi replica đều nhận mọi sự kiện. Cần phân biệt:

- **Broadcast giữa các nhóm:** mỗi subscription/group có tiến độ riêng.
- **Load balancing trong một nhóm:** các replica cùng chia việc, tránh tất cả cùng thực hiện một side effect.
- **Multiple subscriber instances:** cơ chế chính xác tùy broker, subscription type và group configuration.

### 4.3. Topic không nói chắc về retention

Topic có thể là:

- **Pub/sub không bền vững:** subscriber chỉ nhận khi đang kết nối hoặc theo cấu hình lưu tạm.
- **Topic với subscription bền vững:** broker giữ message cho subscriber đến khi ack hoặc hết hạn.
- **Topic dạng log/stream:** bản ghi được giữ theo retention, consumer đọc bằng offset.

Vì vậy câu “dùng topic là có thể replay” **không luôn đúng**. Muốn replay phải xác nhận broker lưu bao lâu, có hỗ trợ seek/rewind hay không, quyền truy cập và độ đầy đủ của dữ liệu lịch sử.

### 4.4. Topic phù hợp khi nào?

- Một domain event cần nhiều consumer độc lập.
- Producer không cần biết từng subscriber cụ thể.
- Consumer có thể thêm/bớt khi sản phẩm phát triển, miễn không phá hợp đồng.
- Cần tách nhịp triển khai giữa bên phát và bên nhận.
- Có side effect không nằm trong transaction cốt lõi, như analytics hoặc notification.

Topic không có nghĩa là **mọi sự kiện nhỏ trong code** đều đáng phát ra toàn hệ thống. Event công bố nên có giá trị nghiệp vụ, sở hữu rõ, hạn chế lộ cấu trúc nội bộ và có thể tiến hóa contract.

## 5. Nhật ký sự kiện (event log/stream): lịch sử có thể đọc theo vị trí

### 5.1. Append-only và retention

Event log là một chuỗi bản ghi được ghi nối tiếp. Thay vì xóa thông điệp ngay sau khi một consumer xử lý, broker thường giữ bản ghi theo chính sách thời gian, dung lượng hoặc compaction. Consumer theo dõi **offset/sequence** để biết đã đọc đến đâu.

~~~text
Topic: orders.events

Partition 0  [offset 0][1][2][3][4][5]...
                 |           |
                 |           +--- Consumer A tiếp tục
                 +--------------- Consumer B đọc lại từ đầu

Partition 1  [offset 0][1][2][3]...
Partition 2  [offset 0][1][2][3][4]...
~~~

Một log phân vùng thường bảo đảm thứ tự **trong mỗi partition**, không có thứ tự toàn cục đơn giản giữa mọi partition. Consumer group nhận phân công các partition; các group khác nhau đọc cùng nguồn dữ liệu theo tiến độ riêng.

### 5.2. Offset là vị trí đọc, không phải bằng chứng nghiệp vụ hoàn tất

Consumer A đọc message tại offset 120, cập nhật database, rồi commit offset 121 để nói “lần tới bắt đầu ở 121” (cách biểu diễn cụ thể tùy client/broker). Nếu commit offset trước khi ghi database, crash có thể mất cập nhật. Nếu ghi database trước và crash khi chưa commit, message được đọc lại.

Vì vậy khi chuyển đổi dữ liệu hay tạo projection, consumer phải xử lý duplicate an toàn. Có thể lưu vị trí đã commit cùng kết quả trong một transaction nếu dùng được cơ chế phù hợp với storage và mô hình xử lý. Nếu không, dùng idempotent upsert, processed-event table hoặc phiên bản đối tượng.

### 5.3. Replay và xây dựng lại projection

Giả sử Search Projection bị lỗi logic và index sai. Nếu lịch sử event còn đủ và contract tương thích, nhóm có thể:

1. Tạo một projection mới/consumer group mới.
2. Đọc lại sự kiện từ offset/thời điểm bắt đầu cần thiết.
3. Xây dựng dữ liệu đọc vào index mới.
4. Đối chiếu tính đúng, độ trễ và completeness.
5. Chuyển truy vấn sang index mới khi đạt yêu cầu.

Đó là một thế mạnh của log. Tuy nhiên, replay có thể phát lại **tác dụng phụ** nếu consumer không tách đúng vai trò. Không nên cho một replay nhằm xây lại search index vô tình gửi lại email, thu tiền hoặc tạo đơn vận chuyển. Các consumer có side effect cần chính sách replay riêng.

### 5.4. Log không đồng nghĩa event sourcing

- **Event log/stream:** hạ tầng lưu và phân phối các bản ghi sự kiện.
- **Event sourcing:** mô hình trong đó trạng thái của một aggregate được tái tạo từ lịch sử sự kiện làm nguồn sự thật chính.
- **CQRS:** phân tách mô hình thay đổi với mô hình đọc khi hữu ích.
- **Change Data Capture (CDC):** thu nhận thay đổi từ log/transaction của database để tích hợp.
- **Audit log:** lưu sự kiện phục vụ kiểm toán, có yêu cầu riêng về tính bất biến và lưu trữ.

Một hệ thống dùng log làm đường truyền nhưng vẫn lưu bảng nghiệp vụ thông thường. Không cần event sourcing để có queue, topic hay replay. Ngược lại, một hệ thống event sourcing cần những cam kết chặt chẽ hơn về phiên bản sự kiện, tính đầy đủ và khả năng phục hồi lâu dài.

### 5.5. Retention và log compaction

Hai cách lưu phổ biến:

- **Time/size retention:** bản ghi cũ được xóa khi vượt thời hạn hoặc giới hạn dung lượng. Consumer quá chậm có thể mất dữ liệu cần đọc.
- **Compaction theo key:** broker cố gắng giữ bản ghi mới nhất theo khóa, hữu ích cho việc xây trạng thái hiện tại hoặc bảng tham chiếu. Tùy cơ chế, dữ liệu trung gian không còn đầy đủ; tombstone và thời hạn lưu cũng cần hiểu.

Nếu nghiệp vụ cần mọi lần chuyển trạng thái để kiểm toán, một log compacted có thể không đủ. Nếu chỉ cần trạng thái gần nhất của từng mã sản phẩm, compaction có thể hữu ích. Phải chọn retention theo nhu cầu sản phẩm, không theo default ngẫu nhiên của broker.

## 6. Bảng so sánh queue, topic và event log

| Chiều so sánh | Queue công việc | Topic publish–subscribe | Event log/stream |
| --- | --- | --- | --- |
| Câu hỏi chính | Ai thực hiện tác vụ? | Những nhóm nào cần biết điều đã xảy ra? | Ai cần đọc lịch sử và từ vị trí nào? |
| Phân phối logic | Một worker trong một nhóm xử lý một công việc mỗi lượt | Mỗi subscription/group có bản sao logic | Nhiều group có offset riêng; replica chia partition |
| Mô hình dữ liệu | Task/command | Event hoặc thông điệp công bố | Chuỗi record có key, offset/sequence |
| Sau khi xử lý | Có thể ack để broker xóa/ẩn hẳn task | Tùy subscription và broker | Thường tiếp tục được giữ theo retention |
| Lưu tiến độ | Ack, visibility/lease, trạng thái job | Ack/subscription cursor | Offset/checkpoint mỗi group |
| Replay lịch sử | Thường hạn chế, phải thiết kế riêng | Tùy retention và cơ chế seek | Là mục tiêu quan trọng nếu lịch sử còn giữ |
| Thứ tự | Tùy queue; có chế độ FIFO hoặc không | Tùy broker/subscription | Thường có thứ tự theo partition |
| Tăng tải | Thêm worker | Thêm worker từng subscription | Thêm consumer trong giới hạn partition/assignment |
| Ví dụ | Tạo PDF, gửi email theo task | OrderPlaced cho nhiều hệ | CDC, projections, analytics, event history |
| Rủi ro lớn | Duplicate, mất job nếu ack sai, backlog | Fan-out lỗi, contract coupling | Lag, replay side effect, retention, partition skew |

**Lưu ý:** bảng trình bày **mẫu hình kiến trúc**, không phải danh sách chức năng duy nhất của từng sản phẩm. Một Kafka topic là log phân vùng nhưng cũng có thể dùng làm work distribution thông qua consumer group; một exchange/topic của broker queue có thể route message đến nhiều queue; dịch vụ pub/sub được quản lý có thể cung cấp retention và seek. Cần xem API và cam kết cụ thể của hệ thống đang chọn.

## 7. Chọn đúng thông điệp: command, job, event hay thay đổi dữ liệu

### 7.1. Command và task

**Command** là yêu cầu một chủ thể thực hiện hành động. Ví dụ:

- GenerateMonthlyReport
- ReserveInventory
- SendWelcomeEmail

Bên nhận có trách nhiệm chấp nhận/từ chối và xử lý lỗi. Khi đưa qua queue, nên biết chủ thể nào là owner, khi nào được xem là hoàn thành, idempotency key, deadline và cách báo kết quả. Một command thường hướng đến **một capability chịu trách nhiệm chính**, dù hệ thống có nhiều worker thực thi.

### 7.2. Domain event và integration event

**Domain event** là sự thật đã xảy ra trong bounded context, ví dụ PaymentCaptured, OrderCancelled. **Integration event** là hợp đồng công bố ra ngoài để context khác biết một thay đổi có ý nghĩa. Không nhất thiết phát mọi domain event nội bộ thành integration event.

Tên sự kiện phải có ý nghĩa rõ:

- **OrderPlaced:** đơn được đặt theo định nghĩa của Ordering.
- **PaymentCaptured:** Payments đã xác nhận ghi nhận một khoản thu tiền.
- **ShipmentDelivered:** Shipping xác nhận giao thành công theo quy tắc của mình.

Tránh các tên quá mơ hồ như DataChanged, UpdateStatus, RowInserted, vì consumer sẽ phải đoán ý nghĩa nghiệp vụ hoặc phụ thuộc trực tiếp vào cấu trúc database của producer.

### 7.3. Event-carried state transfer và notification

Hai kiểu payload:

1. **Event notification:** thông báo một thay đổi quan trọng và định danh; consumer gọi API/đọc nguồn khác nếu cần thêm chi tiết.
2. **Event-carried state transfer:** kèm các trường cần thiết để consumer cập nhật projection mà không gọi lại producer.

Kiểu đầu giảm rò rỉ dữ liệu và contract payload nhưng có thể tạo nhiều lời gọi đồng bộ ngược. Kiểu hai hỗ trợ consumer độc lập hơn nhưng cần versioning, giới hạn dữ liệu và consistency. Đừng phát toàn bộ bản ghi database vì tiện. Chọn trường theo contract đã thỏa thuận.

### 7.4. Ví dụ envelope

~~~json
{
  "eventId": "evt-79c1",
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "aggregateId": "order-742",
  "tenantId": "tenant-17",
  "occurredAt": "2026-11-11T08:15:20Z",
  "publishedAt": "2026-11-11T08:15:22Z",
  "correlationId": "checkout-req-89",
  "payload": {
    "orderId": "order-742",
    "customerId": "customer-115",
    "currency": "VND",
    "totalAmount": "250000"
  }
}
~~~

Đây là payload minh họa. Trong thiết kế thực tế cần xác định loại tiền/đơn vị và tránh sai số, ý nghĩa thời điểm, độ tin cậy của tenant ID, schema registry nếu cần, retention và phân quyền dữ liệu. Event ID nên ổn định qua các lần retry cùng một sự kiện. Không sử dụng thông tin định danh cá nhân không cần thiết trong topic có nhiều subscriber.

## 8. Ví dụ xuyên suốt: hệ thống đặt hàng

Giả sử nền tảng thương mại điện tử có Ordering, Payments, Inventory, Notifications và Analytics. Khi khách đặt đơn:

1. Ordering kiểm tra quy tắc nhận đơn, ghi đơn vào database.
2. Ordering công bố OrderPlaced bằng cơ chế phát đáng tin.
3. Một process manager hoặc owner của quy trình giao lệnh yêu cầu thanh toán/giữ hàng theo chính sách nghiệp vụ.
4. Payments xử lý phần thu tiền và công bố kết quả đã được xác nhận.
5. Inventory xử lý quyền giữ hàng, có thể trả kết quả bất đồng bộ.
6. Notifications và Analytics phản ứng với sự kiện phù hợp mà không chặn luồng trọng yếu.

### 8.1. Tách ba kênh theo ngữ nghĩa

~~~text
                     [Ordering]
                        |
                Outbox OrderPlaced
                        |
                        v
              [orders.events TOPIC/LOG]
                   |             |
                   v             v
             [Analytics]     [Process Manager]
                                   |
                         Command: ReserveStock
                                   |
                                   v
                         [inventory.commands QUEUE]
                                   |
                         [Inventory workers]
                                   |
                           StockReserved
                                   |
                                   v
                      [inventory.events TOPIC/LOG]
                                   |
                           [Ordering projection]
~~~

Sơ đồ là một phương án, không phải thứ tự xử lý thanh toán/kho áp dụng cho mọi doanh nghiệp. Có nơi phải giữ hàng trước khi thu tiền; có nơi cho thanh toán pending; có nơi dùng chung một module trong modular monolith. Mô hình communication phải theo quy tắc nghiệp vụ đã thống nhất.

### 8.2. Vai trò từng kênh

| Kênh | Bản chất | Vì sao dùng |
| --- | --- | --- |
| inventory.commands | Hàng đợi command | Phân phối tác vụ ReserveStock tới worker có khả năng xử lý |
| orders.events | Topic/log các sự kiện Order | Để nhiều context nhận biết OrderPlaced hoặc OrderCancelled |
| inventory.events | Topic/log các sự kiện kho | Cho các bên quan tâm cập nhật projection theo contract |
| notification.jobs | Queue công việc | Đệm và giới hạn tốc độ gửi email/SMS tới nhà cung cấp |
| analytics.events | Stream/log | Phục vụ consumer phân tích, tái xây read model khi cần |

Không nhất thiết tạo tất cả các kênh nếu một hệ thống nhỏ có thể thực hiện đơn giản hơn. Mỗi queue/topic bổ sung trách nhiệm về schema, owner, retention, ACL, monitoring và khả năng dọn dẹp.

### 8.3. Tại sao không để mỗi hệ thống tự gọi Ordering?

Nếu mọi consumer đều gọi Ordering ngay khi nhận OrderPlaced để lấy dữ liệu, thời điểm có chiến dịch lớn, Ordering có thể bị fan-out request đột biến. Có thể công bố một payload đủ thông tin cần thiết hoặc sử dụng projection/read model. Nhưng không nên nhồi các thuộc tính nhạy cảm hoặc toàn bộ đơn hàng vào mọi event.

Một tiêu chí thực tế: **consumer cần dữ liệu nào để đưa ra quyết định của chính nó, và producer có thể cam kết hợp đồng đó ổn định tới mức nào?**

### 8.4. Điều gì xảy ra nếu Notifications chậm?

Ordering vẫn phải có kết quả nhận đơn đúng theo quy tắc của mình. Queue thông báo có thể tích lũy và xử lý sau. Notifications cần theo dõi tuổi message, retry có giới hạn và cách báo lỗi. Nếu thông báo là một cam kết nghiệp vụ bắt buộc, Ordering hoặc workflow chủ sở hữu phải theo dõi trạng thái gửi, thay vì coi publish thành công là đủ.

### 8.5. Điều gì xảy ra nếu Payment event tới hai lần?

Consumer cập nhật trạng thái đơn hoặc phát lệnh giao hàng phải dùng eventId/định danh nghiệp vụ để tránh thực hiện trùng. Nếu một lần thanh toán có nhiều attempt, cần phân biệt **một event giao lại** và **hai kết quả thanh toán thực sự khác nhau**. Idempotency không đồng nghĩa bỏ qua mọi event có cùng orderId.

## 9. Delivery semantics: gửi ít nhất một lần, tối đa một lần, xử lý đúng một lần

### 9.1. At-most-once

Thông điệp có thể mất nếu lỗi xảy ra; broker không cố giao lại hoặc tiến độ được xác nhận trước xử lý. Phù hợp một số tín hiệu không quan trọng, telemetry có thể mất, nhưng thường không phù hợp cho tác vụ tài chính hoặc thay đổi trạng thái bắt buộc.

### 9.2. At-least-once

Broker/consumer cố giao lại khi chưa thấy ack hoặc checkpoint. Thông điệp có thể được xử lý nhiều lần. Đây là mô hình phổ biến và thực tế cho những tác vụ cần độ tin cậy, khi consumer được thiết kế **idempotent**.

### 9.3. Exactly-once và phạm vi cam kết

Một số hệ thống có giao dịch producer, deduplication hoặc cơ chế exactly-once trong **một phạm vi cụ thể** (ví dụ xử lý giữa những stream thuộc cùng hạ tầng). Không được suy ra rằng API bên ngoài, email, cơ sở dữ liệu khác hoặc cổng thanh toán sẽ có exactly-once business effect.

Một consumer có thể commit thành công dữ liệu rồi mất kết nối trước khi ack; broker giao lại. Để hệ thống đúng, cần thiết kế tác dụng phụ an toàn trước duplicate, hoặc có giao thức idempotency với hệ ngoài.

### 9.4. Mẫu idempotent consumer

Một cách thông dụng: trong cùng DB transaction, ghi nhận message đã xử lý và cập nhật trạng thái nghiệp vụ. Sử dụng khóa duy nhất theo consumer logic + event ID.

~~~sql
BEGIN;

INSERT INTO processed_messages(consumer_name, event_id)
VALUES ('order_projection', 'evt-79c1')
ON CONFLICT DO NOTHING;

-- Chỉ cập nhật projection nếu INSERT mới thật sự tạo bản ghi.
-- Cần kiểm tra số hàng affected hoặc dùng CTE có điều kiện.
UPDATE order_read_model
SET payment_status = 'CAPTURED'
WHERE order_id = 'order-742'
  AND payment_status <> 'CAPTURED';

COMMIT;
~~~

Pseudo-SQL này minh họa ý tưởng, không phải transaction hoàn chỉnh để copy vào production: câu UPDATE cần được ràng buộc với kết quả INSERT/phiên bản sự kiện và quy tắc thứ tự. Phải lưu trạng thái nghiệp vụ đúng trước khi ack/commit offset. Nếu side effect nằm ngoài DB, như gửi email hoặc gọi payment gateway, cần idempotency tại ranh giới đó.

### 9.5. Định danh và khóa idempotency

- **eventId:** một lần phát sinh sự thật; giữ nguyên qua lần giao lại.
- **commandId/requestId:** một lần yêu cầu một hành động; có thể được client gửi lại.
- **business key:** ví dụ paymentId, shipmentId, orderId; dùng để xác định tác dụng phụ được phép một lần theo quy tắc.
- **attemptId:** mỗi lần worker thử xử lý, có thể thay đổi dù job/message không đổi.
- **correlationId:** nối dấu vết các bước trong cùng hành trình; không dùng thay eventId nếu một hành trình có nhiều event.

Chọn khóa dựa trên nghiệp vụ, không tự dùng orderId để bỏ qua mọi thay đổi sau đơn hàng đầu tiên.

## 10. Giao dịch dữ liệu và phát tin: outbox, CDC và recovery

### 10.1. Bài toán dual-write

~~~text
1. COMMIT đơn hàng vào database.
2. PUBLISH OrderPlaced tới broker.
~~~

Nếu bước 1 thành công nhưng bước 2 thất bại, các bên khác không được thông báo. Nếu publish trước khi commit và DB thất bại, consumer có thể thấy event về một sự thật chưa từng được ghi nhận.

### 10.2. Transactional outbox

~~~text
Database transaction:
  INSERT orders(...)
  INSERT outbox(eventId, type, payload, ...)
COMMIT

Outbox relay:
  đọc outbox chưa chuyển
  publish thông điệp
  đánh dấu hoặc checkpoint đã chuyển

Consumers:
  xác minh eventId, xử lý idempotent
~~~

Outbox giúp đảm bảo thông tin để phát được ghi cùng transaction nghiệp vụ. Nhưng relay có thể gửi lại sau crash; vì vậy outbox **không thay thế idempotency** ở consumer. Cần giám sát backlog, thời gian chậm publish, poison event và chính sách dọn outbox.

### 10.3. CDC và thay đổi trong database

CDC có thể đọc transaction log và phát thay đổi. Nó hữu ích cho xây projection hoặc tích hợp, nhưng row-level change không tự mang đủ **ngữ nghĩa nghiệp vụ**. Một thay đổi cột status chưa chắc nói được khách vừa hủy hay hệ thống tự hủy do quá hạn.

Có thể dùng CDC để chuyển các outbox records thay vì để ứng dụng tự poll. Nếu dùng CDC trực tiếp trên bảng nghiệp vụ, phải thiết kế ownership, schema evolution, xóa dữ liệu, xử lý snapshot và cách ánh xạ sang event semantic phù hợp.

### 10.4. Inbox và processed-message store

Phía nhận có thể có inbox/processed-event table để chống xử lý trùng và kiểm soát công việc. Trong một số workflow, cần một **inbox có trạng thái** để nhận event trước, rồi worker nội bộ xử lý theo nhịp ổn định. Phải xác định thời điểm nào được ack broker và dữ liệu nào đã được lưu bền vững.

## 11. Thứ tự sự kiện và partitioning

### 11.1. Thứ tự nào thật sự cần?

Ví dụ một đơn có sự kiện:

1. OrderPlaced
2. PaymentCaptured
3. OrderCancelled

Nếu xử lý sai thứ tự, projection có thể hiển thị trạng thái không thể xảy ra. Nhưng lưu ý chúng có thể phát từ các bounded context khác nhau, không tự động có cùng thứ tự toàn cục. Cần xác định tính nhân quả và version trạng thái, không dựa vào việc “timestamp nhỏ hơn chắc chắn tới trước”.

Trong log phân vùng, thường bảo đảm thứ tự **trong partition**. Một chiến lược có thể là partition theo orderId để các sự kiện liên quan cùng đơn từ **cùng nguồn/sơ đồ partition hợp lệ** được xử lý có thứ tự. Nếu producer từ nhiều nguồn, phải quản lý version và hợp đồng phối hợp; việc cùng key không tạo ra thứ tự nhân quả một cách thần kỳ.

### 11.2. Chọn partition key

| Key ứng viên | Khi hữu ích | Rủi ro |
| --- | --- | --- |
| orderId | Thứ tự theo đơn | Một đơn cực nóng có thể tạo hotspot |
| customerId | Cần xử lý tuần tự theo khách | Khách lớn tạo skew; giảm khả năng song song |
| tenantId | Cô lập/thứ tự theo tenant | Tenant lớn dồn về một partition |
| random ID | Phân tải tương đối đều | Không giữ thứ tự theo thực thể |
| composite key | Gắn với domain aggregate cụ thể | Khó thay đổi nếu contract chưa rõ |

Chọn key dựa trên **đơn vị cần giữ thứ tự** và giới hạn throughput. Quá nhiều partition tăng chi phí vận hành; quá ít partition giới hạn khả năng chạy song song.

### 11.3. Rebalance, message trễ và xử lý lại

Khi consumer group thêm/bớt replica, partition có thể đổi owner. Consumer cần quản lý checkpoint và shutdown có kiểm soát. Nếu event cũ đến sau event mới do nhiều nguồn hoặc retry, projection có thể dùng version, monotonic state transition, event time và logic xử lý late event.

Không dùng mỗi timestamp máy chủ để suy ra thứ tự tuyệt đối giữa các máy khi nghiệp vụ cần bảo đảm mạnh.

## 12. Retry, dead-letter queue và poison messages

### 12.1. Lỗi tạm thời và lỗi vĩnh viễn

- **Tạm thời:** 503, timeout, throttling, database đang bảo trì; thường retry với exponential backoff và jitter.
- **Dữ liệu không hợp lệ:** thiếu trường bắt buộc, schema sai; thường không retry vô hạn.
- **Quy tắc nghiệp vụ từ chối:** ví dụ coupon hết hạn; có thể tạo kết quả rejected thay vì lỗi hạ tầng.
- **Lỗi code/poison message:** cùng payload gây exception liên tục; cần cách ly để không chặn cả kênh.

### 12.2. Retry không được gây bão

Nếu 10.000 worker cùng retry sau 1 giây khi nhà cung cấp phục hồi, downstream có thể sập lại. Dùng backoff, jitter, concurrency cap, circuit breaker và retry budget. Với message cần thứ tự, đưa một item lỗi sang retry lane có thể ảnh hưởng ordering; phải quyết định có chấp nhận out-of-order không.

### 12.3. Dead-letter queue (DLQ)

DLQ giữ message đã vượt attempt hoặc không thể xử lý để điều tra. Cần ghi nguồn, lý do, thời điểm, số attempt, correlation ID và công cụ re-drive.

~~~text
Main Queue/Subscription
        |
        v
    Consumer
      |   \
   success  failure tạm thời
      |          |
      ack       retry/backoff
                 |
          quá số lần cho phép
                 |
                 v
                DLQ --> Dashboard/Alert --> Investigate/Re-drive
~~~

DLQ **không phải nơi chôn sự kiện**. Nếu không ai sở hữu, lỗi nghiệp vụ có thể bị ẩn. Re-drive cần kiểm tra xem công việc đã thành công một phần, đã được bù hoặc đã quá hạn chưa; không tự động phát lại toàn bộ message cũ.

### 12.4. Re-drive và side effect

Với thông báo email, có thể chấp nhận gửi lại theo chính sách. Với thu tiền, hoàn tiền hoặc cấp quyền truy cập, re-drive phải có chống trùng mạnh, kiểm tra trạng thái hiện tại và quy trình phê duyệt khi cần. Replay vào consumer mới cũng phải có isolation để không tác động tới môi trường production ngoài ý muốn.

## 13. Backpressure và mở rộng năng lực xử lý

Queue làm lệch nhịp producer và consumer: lúc cao điểm, việc được xếp hàng thay vì chạy đồng thời vô hạn. Nhưng nếu producer đưa vào nhanh hơn consumer hoàn thành trong thời gian dài, backlog sẽ tiếp tục tăng.

### 13.1. Ước lượng công suất

Giả sử một job mất trung bình 20 giây trên một worker, có 15 worker song song hiệu quả:

- Năng lực lý thuyết: 15/20 = 0,75 job/giây, tức khoảng 45 job/phút.
- Nếu tải đến liên tục 60 job/phút, backlog tăng khoảng 15 job/phút, trước khi tính retry và overhead.
- Với 900 job đang đợi, kể cả chỉ lấy 900/45 = 20 phút để thấy mức thời gian cần giải quyết toàn bộ backlog theo thông lượng trung bình lý tưởng; chờ thực tế còn phụ thuộc job tiếp tục đến, độ lớn job và policy xếp hàng.

Đây là ví dụ định lượng đơn giản; production cần theo dõi phân phối thời gian xử lý, contention, I/O, sự khác biệt tải, lỗi và giới hạn downstream.

### 13.2. Queue depth khác queue age

Một queue có 100 message nhỏ có thể xử lý nhanh hơn queue 10 message mỗi job dài 2 giờ. Nên đo đồng thời:

- Queue depth, oldest unprocessed message age.
- Thời gian từ publish đến bắt đầu xử lý.
- Thời gian xử lý, hoàn tất end-to-end, retry count.
- Consumer throughput, concurrency, CPU/memory và downstream saturation.
- Số message ở DLQ, stalled jobs và sự khác biệt theo tenant.

Với log/stream, thường đo **consumer lag** theo offset hoặc thời gian so với event mới nhất. Lag theo số bản ghi không tự bằng thời gian chờ thực; cần quan sát throughput và thời gian tiêu thụ.

### 13.3. Backpressure và fairness

- Giới hạn tốc độ nhận yêu cầu khi quá tải, trả thông báo chờ hợp lý.
- Giới hạn số job chờ/đang chạy theo tenant và loại tác vụ.
- Có priority hoặc nhiều queue cho workload có SLA khác nhau.
- Dùng worker pool riêng cho tác vụ CPU nặng và tác vụ I/O.
- Giới hạn batch size, prefetch, concurrency, và timeout phù hợp.
- Không để tác vụ report làm nghẽn consumer xử lý nghiệp vụ cần đáp ứng nhanh.

Autoscale worker chỉ có ích nếu downstream cũng chịu được tăng tải. Tăng gấp đôi consumer khi database đã hết connection có thể khiến toàn hệ thống tệ hơn.

## 14. Consumer groups và mở rộng ngang

Một log topic có sáu partition và nhóm Analytics có ba consumer; broker thường chia partition để mỗi consumer phụ trách một số partition. Thêm consumer thứ tư có thể tăng song song nếu phân phối và tải đủ tốt; thêm consumer thứ bảy trong cùng nhóm thường không tăng số partition được đọc song song tại thời điểm đó.

~~~text
log topic (6 partitions)
  P0 ----> Analytics consumer A
  P1 ----> Analytics consumer A
  P2 ----> Analytics consumer B
  P3 ----> Analytics consumer B
  P4 ----> Analytics consumer C
  P5 ----> Analytics consumer C

Independent Search group:
  P0..P5 ---> Search consumers với offset riêng
~~~

Chi tiết assignment/rebalance tùy broker và client. Cần hiểu cơ chế khóa/thứ tự của consumer và nguyên tắc một partition trong một group có một owner xử lý chính tại một thời điểm. Một queue truyền thống có thể chia tải qua nhiều worker mà không dùng partition cố định; cả hai đều phải đo contention và thông lượng thực.

### Khi nào nên tạo group mới?

- Cần xây projection mới từ cùng nguồn.
- Có ứng dụng tiêu thụ khác với quyền sở hữu/độ trễ độc lập.
- Cần replay thử nghiệm an toàn trong môi trường cô lập.
- Đổi logic consumer và cần chạy song song để so sánh.

Không tạo group mới chỉ để thêm replica cho cùng một side effect; nếu mỗi replica dùng group khác nhau, mọi message có thể gây tác dụng phụ nhiều lần.

## 15. Contract, schema evolution và khả năng tái xử lý

### 15.1. Sự kiện tồn tại lâu hơn phiên bản code

Producer có thể được deploy phiên bản mới trong khi message cũ còn trong queue/log và consumer đang chạy version khác. Contract cần quy tắc:

- Tên event có ngữ nghĩa ổn định, version rõ.
- Thêm trường tùy chọn với default hợp lý khi tương thích.
- Không thay đổi nghĩa của trường cũ âm thầm.
- Hỗ trợ các version còn tồn tại trong retention hoặc migration.
- Consumer chịu được trường chưa biết nếu định dạng cho phép.
- Có kế hoạch chuyển đổi khi bắt buộc thay đổi cấu trúc phá tương thích.

### 15.2. Ví dụ thay đổi event

Phiên bản 1:

~~~json
{
  "eventType": "OrderPlaced",
  "version": 1,
  "orderId": "o-1",
  "amount": "250000"
}
~~~

Phiên bản 2 có thể thêm currency để giảm mơ hồ:

~~~json
{
  "eventType": "OrderPlaced",
  "version": 2,
  "orderId": "o-1",
  "amount": "250000",
  "currency": "VND"
}
~~~

Nếu consumer cũ hiểu amount theo đơn vị tiền định sẵn, sự thay đổi này có thể vẫn cần quy tắc tương thích về ngữ nghĩa. Trường mới không tự an toàn nếu thay cách diễn giải amount, cách làm tròn hay precision.

### 15.3. Schema registry và compatibility

Khi có nhiều producer/consumer, registry hoặc kho contract có version giúp kiểm soát schema và phát hiện phá tương thích. Có thể dùng JSON Schema, Avro hoặc Protobuf tùy hạ tầng. Nhưng registry không thay thế việc thống nhất nghĩa nghiệp vụ: một kiểu string hợp lệ vẫn có thể chứa enum sai hoặc sự kiện phát ở thời điểm không đúng.

### 15.4. Replay đòi hỏi dữ liệu và code tương thích

Khi đọc lại log của nhiều năm, các version sự kiện có thể khác nhau. Có thể cần upcaster/migration để chuyển dữ liệu cũ sang mô hình consumer hiện tại. Đồng thời phải phân biệt event-time và processing-time; việc chạy lại hôm nay không làm sự kiện quá khứ đổi thời điểm xảy ra.

Lịch sử có thể bị retention xóa hoặc compaction giữ lại trạng thái cuối. Không hứa “khôi phục toàn bộ hệ thống từ topic” nếu các điều kiện lưu trữ không bảo đảm điều đó.

## 16. Bảo mật, dữ liệu cá nhân và quyền truy cập

Một topic fan-out tới nhiều consumer khiến dữ liệu lan rộng hơn so với API trực tiếp. Một log giữ lâu có thể lưu cả thông tin nhạy cảm sau khi ứng dụng nguồn đã thay đổi hoặc xóa dữ liệu.

Cần thiết kế:

- **ACL theo producer/consumer:** ai được publish, subscribe, tạo subscription hoặc đọc lại lịch sử.
- **Mã hóa truyền và lưu:** TLS, encryption at rest phù hợp hạ tầng.
- **Tối thiểu hóa payload:** chỉ đưa dữ liệu cần thiết, ưu tiên ID hoặc trường được phép công bố.
- **Tenant isolation:** message và quyền đọc theo tenant/miền tin cậy khi cần.
- **Retention và xóa:** bảo đảm chính sách lưu, quyền xóa, tombstone hoặc chiến lược xử lý yêu cầu xóa dữ liệu.
- **Secret management:** không đưa API token, mật khẩu hay khóa bí mật vào payload/log.
- **Audit:** ghi ai tạo/xem/replay stream nhạy cảm, ai re-drive DLQ.
- **Quản lý schema và hợp đồng:** ngăn consumer phụ thuộc vào trường riêng tư của producer.

Có thể cần tách topic theo phân loại dữ liệu hoặc bounded context. Không được giả định rằng mọi team có quyền xem toàn bộ sự kiện chỉ vì chúng được công bố nội bộ.

## 17. Khả năng quan sát và SLO cho đường giao tiếp

### 17.1. Metric cho producer

- Số message phát thành công/thất bại, theo type.
- Tỷ lệ publish retry và latency publish.
- Outbox backlog/oldest outbox age.
- Số event sai schema hoặc bị từ chối.
- Tỷ lệ business transaction đã ghi nhưng event chưa phát vượt ngưỡng.

### 17.2. Metric cho consumer

- Received, processed, failed, retried, dead-lettered.
- Processing duration và end-to-end event latency.
- Consumer lag, queue age và số message đang chờ.
- Số duplicate được phát hiện; số side effect thất bại.
- Partition skew, rebalance frequency, stalled consumer.
- Tỷ lệ event bị bỏ qua có chủ đích do version không hỗ trợ.
- Sự đúng đắn của projection qua đối soát định kỳ.

### 17.3. Correlation ID xuyên các bước

~~~text
HTTP request: req-81
   |
   +--> business transaction order-742
   |       |
   |       +--> outbox eventId=evt-79c1
   |                 |
   |                 +--> broker topic orders.events
   |                            |
   |                            +--> Analytics consumer attempt-4
   |                            +--> Search consumer attempt-2
   |                            +--> Notification job send-99
~~~

Đường trace async có thể dùng correlation ID, span links hoặc metadata riêng thay vì giả định một HTTP span kéo dài cho đến khi toàn bộ consumer kết thúc. Đừng log toàn bộ payload thanh toán hay dữ liệu cá nhân để phục vụ debug.

### 17.4. Ví dụ SLO

Các mục tiêu minh họa, cần thay theo nghiệp vụ:

- 99,9% outbox event được chuyển tới broker trong 30 giây.
- 99% notification jobs hoàn tất trong 2 phút khi nhà cung cấp hoạt động bình thường.
- Search projection lag nhỏ hơn 15 giây ở tải thông thường.
- Không có message ở DLQ quá 1 giờ mà chưa có người phụ trách điều tra.

SLO của producer và của từng consumer khác nhau. Một producer phát thành công không chứng minh search đã cập nhật hoặc email đã tới người nhận.

## 18. Chọn công nghệ: tập trung vào semantics và vận hành

Một số công nghệ thường được nhắc đến:

| Hệ sinh thái/ví dụ | Mô hình thường gặp | Cần khảo sát trước khi chọn |
| --- | --- | --- |
| RabbitMQ và các broker message queue | Queue, routing qua exchange, competing consumers | Ack, DLQ, retry, ordering, durability, consumer flow control |
| Kafka và nền tảng streaming tương tự | Topic phân vùng dạng log, consumer group, offset | Retention, partition, replay, compaction, lag, schema |
| AWS SQS | Hàng đợi quản lý, có chế độ standard/FIFO | Visibility timeout, duplicate, ordering scope, DLQ |
| AWS SNS và SQS | Fan-out publish–subscribe kết hợp queue | Subscription, filter policy, retry và liên kết lỗi |
| Google Cloud Pub/Sub | Topic và subscription được quản lý | Ack deadline, retention, ordering key, replay/seek theo cấu hình |
| NATS và hệ streaming kèm theo | Pub/sub, queue group và cơ chế stream bền vững tùy cấu hình | Persistence, ack, replay, retention, consumer state |
| Database job table | Hàng đợi công việc ngay trong DB ứng dụng | Lease, concurrency, index, polling, recovery và tải DB |

Bảng giới thiệu **họ mô hình**, không tuyên bố mọi phiên bản/cấu hình đều có cùng chức năng. Khi triển khai phải đọc tài liệu của phiên bản đang dùng, thử nghiệm delivery/retention thực tế, xác nhận SLA và chi phí vận hành. Một hệ thống nhỏ có thể dùng job table đơn giản; một hệ thống có nhu cầu stream history lớn cần công cụ và vận hành tương ứng.

### Bộ câu hỏi chọn hạ tầng

1. Thông điệp dùng để **giao một việc** hay **công bố sự kiện cho nhiều bên**?
2. Có cần replay không? Trong bao lâu và ở quy mô bao nhiêu?
3. Mức thông lượng, fan-out, kích thước message và peak load là gì?
4. Cần ordering theo đối tượng nào?
5. Có dùng transaction/outbox/CDC để tránh mất sự kiện không?
6. Có broker đang vận hành tốt trong tổ chức không?
7. Ai chịu trách nhiệm ACL, quota, backup, DR, upgrade và cost?
8. Consumer có thể trễ bao lâu trước khi message hết retention?
9. Quy trình DLQ, re-drive và audit đã rõ chưa?
10. Có thể chạy thử tải và failure-injection trước khi chốt không?

## 19. Những sai lầm thiết kế thường gặp

| Sai lầm | Hệ quả | Cách tiếp cận |
| --- | --- | --- |
| Dùng queue cho mọi sự kiện rồi chỉ một consumer nhận | Hệ khác không có fan-out riêng | Tách contract publish–subscribe khi nhiều nhóm cần cùng sự kiện |
| Dùng topic nhưng nghĩ mọi subscriber đều nhận toàn bộ lịch sử | Consumer mới có thể bỏ lỡ event cũ | Xác minh retention, durable subscription và replay |
| Dùng log và tưởng thông điệp biến mất khi consumer đọc | Nhầm chi phí lưu trữ và quyền đọc lại | Hiểu offset và chính sách retention |
| Dùng mỗi replica một consumer group để scale | Mỗi replica xử lý cùng event, gây tác dụng phụ trùng | Dùng chung group khi cần chia tải |
| Commit offset/ack trước khi ghi kết quả | Crash gây mất tác dụng nghiệp vụ | Chỉ xác nhận sau điểm bền vững, có idempotency |
| Chỉ dựa vào FIFO để tránh trùng | Giao lại vẫn có thể xảy ra | Idempotency ở command/consumer và side effect |
| Dùng timestamp làm thứ tự tuyệt đối giữa service | Race và state regression | Version, causal rules và partition key phù hợp |
| Publish từ DB và broker bằng hai thao tác không điều phối | Dual-write gap làm mất event | Transactional outbox/CDC thích hợp |
| Retry vô hạn với poison message | Nghẽn queue và chiếm tài nguyên | Phân loại lỗi, backoff, DLQ có owner |
| Dùng topic làm bảng dữ liệu công khai của producer | Coupling schema và rò rỉ dữ liệu | Contract nghiệp vụ, giới hạn payload, ACL |
| Cho replay consumer có side effect thật | Gửi lại email, charge hoặc cấp quyền sai | Replay cô lập và idempotency mạnh |
| Chỉ quan sát broker up/down | Không thấy lag, lỗi xử lý âm thầm | Metric end-to-end và đối soát business |
| Chọn broker chỉ vì phổ biến | Hệ khó vận hành, không đáp ứng semantics | So sánh theo use case và năng lực team |
| Chia topic theo bảng database thay vì domain | Event vô nghĩa, consumer phải suy diễn | Bắt đầu từ hành vi/contract của bounded context |
| Không có owner cho event/topic | Thay đổi schema phá consumer không ai chịu trách nhiệm | Catalog, lifecycle, versioning và owner rõ ràng |

## 20. Bài tập 1: thiết kế kênh cho hệ thống đào tạo

**Bối cảnh:** nền tảng học trực tuyến có các capability Enrollment, Certificates, Notifications, Analytics. Khi học viên đăng ký khóa, hệ thống cần ghi nhận đăng ký, gửi email, cập nhật dashboard. Khi hoàn thành khóa, hệ thống cấp chứng chỉ PDF mất 20–90 giây; các báo cáo phân tích có thể cần xây lại từ lịch sử.

**Yêu cầu:**

1. Vẽ điểm đồng bộ mà Enrollment cần hoàn tất trước khi trả “Đăng ký thành công”.
2. Đề xuất kênh để công bố EnrollmentCreated cho Notifications và Analytics. Đây là command hay event?
3. Đề xuất queue để tạo Certificate PDF và cách phân công 10 worker.
4. Thiết kế trạng thái certificate job gồm QUEUED, RUNNING, SUCCEEDED, FAILED và cách lấy kết quả.
5. Nếu Notifications bị outage 30 phút, điều gì cần được giữ và dashboard nào cần báo động?
6. Nếu Analytics cần replay 30 ngày, retention và quyền đọc cần thỏa điều kiện nào?
7. Nếu Certificates nhận message trùng sau timeout, làm sao không phát hai chứng chỉ có hai mã khác nhau?
8. Nếu học viên bị hủy đăng ký trước khi chứng chỉ chạy xong, workflow nên kiểm tra điều kiện nghiệp vụ ở đâu?

**Một hướng thiết kế:** Enrollment commit đăng ký và outbox event trong cùng DB transaction; event được phân phối tới các subscription độc lập. Certificates nhận công việc GenerateCertificate qua queue, ghi job status bền vững, chống trùng bằng khóa học viên–khóa học–lần cấp chứng chỉ theo quy tắc. Analytics dùng log/stream có retention và khả năng tái xử lý; replay không gửi email hay cấp lại chứng chỉ.

## 21. Bài tập 2: xử lý mất thứ tự, trùng và backlog

Giả sử một consumer cập nhật read model theo các event về một tài khoản:

~~~text
AccountOpened   version=1
AddressUpdated  version=2
AddressUpdated  version=3
AccountClosed   version=4
~~~

Tại consumer, do redelivery hoặc nhiều luồng, thứ tự đến là: 1, 3, 2, 3, 4.

**Câu hỏi:**

1. Chỉ xử lý idempotency theo eventId có đủ giữ trạng thái địa chỉ mới nhất không?
2. Consumer nên làm gì khi event version 2 đến sau version 3?
3. Nếu event version 2 là sự kiện có ý nghĩa độc lập cần audit, có thể bỏ qua hoàn toàn không?
4. Partition key theo accountId hỗ trợ điều gì? Nó không giải quyết những trường hợp nào?
5. Nếu stream hết retention trước khi consumer kịp đọc, phương án phục hồi nào khả thi?
6. Nếu backlog tăng vì CPU xử lý nặng, thêm partition/worker có tác dụng gì và điều kiện nào giới hạn?
7. Nếu sự kiện thay đổi địa chỉ chứa thông tin cá nhân, consumer và log phải có chính sách nào?

**Gợi ý:** đối với projection trạng thái hiện tại, version có thể ngăn event cũ ghi đè dữ liệu mới. Nhưng đối với audit, business rules hoặc side effect quan trọng, có thể vẫn phải lưu/đánh giá sự kiện cũ; không đơn giản drop mọi event version thấp. Khả năng replay không vô hạn nếu retention không đủ.

## 22. Checklist triển khai thực tế

**Xác định hợp đồng**

- [ ] Phân biệt command/job, domain event và integration event.
- [ ] Có owner, tên và ý nghĩa rõ cho từng message/topic/queue.
- [ ] Biết consumer/group nào phải nhận, có cần fan-out và replay không.
- [ ] Có schema version, idempotency key/eventId, correlation ID và dữ liệu tối thiểu.
- [ ] Đã quyết định ordering key, consistency và thời điểm nghiệp vụ được coi là thành công.

**Bảo vệ độ tin cậy**

- [ ] Có cơ chế ghi bền vững và xử lý dual-write (outbox/CDC khi phù hợp).
- [ ] Consumer xử lý duplicate và crash ở ranh giới commit/ack an toàn.
- [ ] Có retry policy theo loại lỗi, backoff/jitter và DLQ có người sở hữu.
- [ ] Có runbook replay/re-drive; thao tác này không tạo side effect không mong muốn.
- [ ] Kiểm tra retention có đủ cho thời gian consumer có thể ngừng hoặc tiến trình rebuild.

**Khả năng vận hành**

- [ ] Đo queue age, lag, processing time, error rate và DLQ.
- [ ] Giới hạn throughput, concurrency, quota và tránh overload downstream.
- [ ] Có kế hoạch scale theo worker hoặc partition đúng với workload.
- [ ] Có ACL, retention, kiểm soát dữ liệu nhạy cảm và auditing.
- [ ] Thử lỗi producer, broker, consumer, ack, crash, duplicate, rebalance, poison message.
- [ ] Có người trực và quy trình khôi phục khi sự kiện bị trễ, mất hoặc sai.

## 23. Kết luận

**Queue** giúp phân việc và kiểm soát tải giữa các worker. **Topic** giúp một sự kiện được nhiều nhóm tiêu thụ độc lập. **Event log** lưu chuỗi bản ghi và vị trí đọc để các nhóm có thể tiến hành theo tốc độ riêng hoặc phát lại phần lịch sử còn được giữ. Chúng là những mô hình bổ sung cho nhau; một sản phẩm công nghệ có thể cung cấp một hoặc nhiều mô hình.

Thiết kế giao tiếp bất đồng bộ thành công không dừng ở việc tạo queue/topic. Điều quyết định là xác định đúng **ai sở hữu sự thật, ai chịu trách nhiệm hành động, khi nào đã hoàn thành**, rồi bảo đảm các bước phát/nhận message, ack, retry, idempotency, retention và quan sát phù hợp. Khi các điều kiện này rõ ràng, hệ thống có thể giảm phụ thuộc đồng bộ, tăng khả năng phục hồi và mở rộng, mà không đánh đổi sự đúng đắn của nghiệp vụ.
