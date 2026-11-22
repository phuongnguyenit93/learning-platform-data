# Lựa chọn mô hình trao đổi theo độ trễ, độ bền và yêu cầu nghiệp vụ

## 1. Vì sao phải chọn mô hình trao đổi?

Một hệ thống có thể trao đổi dữ liệu theo nhiều cách: gọi trực tiếp một hàm, gửi yêu cầu và chờ phản hồi, chuyển việc sang xử lý nền, phát sự kiện cho nhiều bên nhận, hoặc ghi sự kiện vào một luồng để các consumer đọc và phát lại. Các cách này khác nhau về thời gian phản hồi, mức độ phụ thuộc giữa các thành phần, khả năng chịu lỗi, thứ tự xử lý và chi phí vận hành.

Không có mô hình nào tốt nhất cho mọi tình huống. Một thao tác cần kết quả ngay để hiển thị cho người dùng thường phù hợp với request-response. Một sự kiện nghiệp vụ cần được xử lý kể cả khi consumer tạm ngừng thường cần hàng đợi hoặc broker có lưu trữ bền vững. Một luồng sự kiện cần nhiều consumer độc lập và khả năng đọc lại lịch sử có thể phù hợp với nền tảng streaming.

Trong Spring, cần phân biệt hai lớp quyết định:

- **Mô hình nghiệp vụ:** command, query, request-reply, event notification, work queue hoặc event stream.
- **Cơ chế truyền tải:** lời gọi trong cùng tiến trình, Spring application event, message channel, HTTP, WebSocket/STOMP, JMS, RabbitMQ, Kafka hoặc một broker khác.

Spring Messaging cung cấp các abstraction như `Message`, `MessageHeaders`, `MessageChannel` và `MessageHandler`. Những abstraction này giúp chuẩn hóa message và điểm gửi/nhận; bản thân một `Message` hay `MessageChannel` không tự bảo đảm dữ liệu sẽ được lưu bền vững, giao đúng một lần hoặc xử lý bất đồng bộ. Các bảo đảm đó đến từ implementation, broker, cấu hình và logic nghiệp vụ.

## 2. Bắt đầu từ yêu cầu nghiệp vụ

Trước khi chọn công nghệ, hãy xác định điều gì phải đúng đối với nghiệp vụ:

1. Người gọi có cần kết quả ngay để quyết định bước tiếp theo không?
2. Nếu tiến trình nhận dừng trong vài phút, thông điệp có được phép mất không?
3. Một thông điệp cần một consumer xử lý hay nhiều consumer độc lập cùng nhận?
4. Có cần giữ thứ tự giữa các thông điệp không? Thứ tự toàn hệ thống hay chỉ theo một đơn hàng/tài khoản?
5. Một yêu cầu có thể xử lý lại không? Nếu xử lý lặp, có tạo đơn trùng, trừ tiền hai lần hoặc gửi thông báo lặp không?
6. Khối lượng có tăng đột biến không? Hệ thống cần giới hạn tốc độ, xếp hàng hoặc tạo áp lực ngược như thế nào?
7. Cần lưu lịch sử bao lâu, truy vết ai phát sự kiện và phát lại từ thời điểm nào?
8. Thời gian chờ tối đa và mức độ nhất quán nào được chấp nhận?

Chuyển các câu trả lời thành tiêu chí đo được. Ví dụ, một API có thể có ngân sách phản hồi p95 dưới 200 ms; một luồng cập nhật hóa đơn có thể chấp nhận xử lý chậm vài giây nhưng không được mất sự kiện đã xác nhận; một thông báo giao diện có thể chấp nhận mất khi người dùng đã rời trang.

Không nên dùng một ngưỡng latency cố định cho mọi hệ thống. Hãy xác định ngân sách p50/p95/p99, thời gian timeout, thông lượng dự kiến, kích thước message, số consumer và thời gian lưu trữ dựa trên tải thực tế.

## 3. Các mô hình trao đổi chính

### 3.1. Gọi đồng bộ và request-response

Người gọi gửi yêu cầu và chờ kết quả trong cùng luồng tương tác. Mô hình này phù hợp khi kết quả là điều kiện để tiếp tục: kiểm tra quyền, xác thực dữ liệu, tính giá tức thời hoặc truy vấn thông tin cần hiển thị.

**Ưu điểm:** luồng điều khiển dễ hiểu; lỗi và kết quả thường được trả về trực tiếp; phù hợp với thao tác cần xác nhận ngay.

**Giới hạn:** thời gian phản hồi phụ thuộc cả các dịch vụ phía sau; caller và callee cùng chịu ảnh hưởng khi một bên chậm; timeout ở caller không tự hủy công việc đã chạy ở server; retry request có thể tạo thao tác trùng nếu không có idempotency.

Trong ứng dụng Spring, gọi method/service trực tiếp trong cùng tiến trình thường đơn giản nhất. Khi qua ranh giới dịch vụ, HTTP request-response là lựa chọn phổ biến. Có thể dùng messaging request-reply khi hệ thống đã vận hành broker và cần định tuyến message, nhưng phải xác định correlation ID, reply destination, timeout, xử lý phản hồi muộn và hành vi khi không có consumer.

Chọn mô hình này khi:

- Người dùng hoặc nghiệp vụ cần quyết định dựa trên kết quả ngay.
- Thao tác có thời gian xử lý dự đoán được và có timeout hợp lý.
- Có thể kiểm soát phụ thuộc và bảo vệ dịch vụ khỏi chuỗi gọi đồng bộ quá dài.

Tránh chuỗi request đồng bộ sâu qua nhiều dịch vụ cho một giao dịch quan trọng. Một dịch vụ chậm có thể kéo dài toàn bộ đường đi, làm cạn connection/thread pool và tạo hiệu ứng domino.

### 3.2. Bất đồng bộ trong cùng tiến trình

Người gửi giao công việc cho một executor, channel hoặc event listener rồi tiếp tục xử lý. Consumer có thể chạy ở thread khác, nhưng vẫn thuộc cùng ứng dụng và cùng vòng đời triển khai.

Trong Spring Framework, `ApplicationEventPublisher` hỗ trợ phát application event trong cùng ứng dụng. `SimpleApplicationEventMulticaster` mặc định gọi listener đồng bộ; cấu hình executor có thể khiến listener chạy bất đồng bộ. Vì vậy, không được giả định rằng cứ publish event là công việc tự chạy nền.

**Ưu điểm:** giảm thời gian chờ của caller; không cần vận hành broker riêng; phù hợp với tác vụ phụ trợ có thể mất khi tiến trình dừng nếu nghiệp vụ cho phép.

**Giới hạn:** bộ nhớ và thread pool bị giới hạn bởi instance ứng dụng; event không tự được lưu bền vững; restart hoặc crash có thể làm mất công việc đang chờ; tăng số instance không tự tạo cơ chế chia sẻ queue đáng tin cậy.

Chọn mô hình này cho việc như cập nhật cache cục bộ, ghi telemetry không trọng yếu, hoặc tác vụ hậu xử lý có thể tạo lại. Không dùng một executor trong bộ nhớ làm nơi lưu duy nhất cho thanh toán, đơn hàng hoặc thông báo bắt buộc phải giao.

### 3.3. Work queue / competing consumers

Producer gửi một công việc vào queue; trong một nhóm consumer, một consumer nhận và xử lý mỗi lần giao message. Đây là mô hình phù hợp để phân phối công việc cho worker, điều tiết tốc độ xử lý và hấp thụ đột biến tải.

**Ưu điểm:** producer và worker tách rời; worker có thể tăng/giảm số lượng; queue tạo vùng đệm khi tốc độ gửi lớn hơn tốc độ xử lý; broker có thể lưu message bền vững.

**Giới hạn:** xử lý có thể trễ khi backlog tăng; cần giám sát độ sâu queue và tuổi message; retry có thể làm message được giao nhiều lần; thứ tự toàn cục thường bị giảm khi có nhiều consumer hoặc partition.

Chọn queue khi một tác vụ cần được thực hiện bởi một worker trong nhóm, chẳng hạn tạo PDF, gửi email giao dịch, xử lý ảnh hoặc thực hiện bước hậu xử lý đơn hàng. Nếu message chứa command, consumer cần kiểm tra trạng thái nghiệp vụ trước khi thực thi để tránh chạy lại một hành động đã hoàn thành.

### 3.4. Publish-subscribe và event notification

Producer phát một sự kiện; nhiều consumer độc lập có thể nhận bản sao hoặc đọc cùng sự kiện theo cơ chế của broker. Ví dụ `OrderPlaced` có thể kích hoạt việc giữ hàng, gửi email và cập nhật phân tích.

**Ưu điểm:** producer không cần biết toàn bộ consumer; có thể thêm consumer mới mà không thay đổi producer; mỗi nhóm consumer có thể tiến triển độc lập.

**Giới hạn:** trạng thái hệ thống trở nên eventual consistent; consumer có thể xử lý ở các thời điểm khác nhau; thứ tự giữa các subscriber không được mặc định bảo đảm; sự kiện cần hợp đồng dữ liệu ổn định.

Event nên mô tả điều đã xảy ra (`OrderPlaced`, `PaymentCaptured`), còn command mô tả điều được yêu cầu (`CapturePayment`, `ReserveInventory`). Consumer của event không nên được hiểu là đã nhận một mệnh lệnh bắt buộc phải thành công. Nếu một bước cần xác nhận thành công để quyết định bước tiếp theo, hãy dùng command/reply hoặc một quy trình điều phối có trạng thái rõ ràng.

### 3.5. Event stream / log có thể phát lại

Trong mô hình streaming, sự kiện được ghi vào log có thứ tự trong phạm vi partition và được giữ theo chính sách retention. Consumer theo dõi offset hoặc vị trí đọc; nhiều consumer group có thể đọc cùng luồng độc lập.

**Ưu điểm:** phù hợp với thông lượng cao, nhiều consumer, xử lý lại dữ liệu, phân tích và xây dựng projection; có thể tái tạo trạng thái đọc từ lịch sử còn được lưu.

**Giới hạn:** cần quản lý partition key, offset, retention, schema và lag; thứ tự thường chỉ được bảo đảm trong một partition; replay có thể tái thực hiện tác động nếu consumer không idempotent.

Chọn stream khi lịch sử sự kiện là một phần có giá trị của hệ thống, cần nhiều consumer độc lập hoặc cần đọc lại dữ liệu. Không chọn streaming chỉ vì tải hiện tại có vẻ lớn; queue đơn giản có thể dễ vận hành hơn nếu yêu cầu chỉ là phân phối một công việc cho một worker.

### 3.6. Push notification tới client

Ứng dụng có thể gửi cập nhật đến trình duyệt hoặc thiết bị qua WebSocket/STOMP, Server-Sent Events hoặc cơ chế push khác. Đây thường là kênh cập nhật giao diện, không phải nơi lưu trạng thái nghiệp vụ chuẩn.

Nếu client mất kết nối, cần xác định có thể bỏ qua thông báo hay phải lấy lại trạng thái từ API khi kết nối lại. Với thông tin quan trọng, hãy lưu trạng thái ở backend và dùng notification như tín hiệu để client tải dữ liệu mới.

## 4. Bảng so sánh nhanh

| Mô hình | Độ trễ cảm nhận | Độ bền mặc định | Mức ghép nối | Tình huống phù hợp |
| --- | --- | --- | --- | --- |
| Gọi trực tiếp trong tiến trình | Thấp | Theo trạng thái ứng dụng; không có queue | Cao về lời gọi | Logic cần kết quả ngay trong cùng ứng dụng |
| HTTP request-response | Thấp đến trung bình, phụ thuộc mạng và downstream | Không tự lưu yêu cầu để xử lý lại | Caller phụ thuộc endpoint | Query hoặc command cần phản hồi ngay |
| Async trong bộ nhớ | Caller trả về nhanh; xử lý nền có thể trễ | Thấp; có thể mất khi process dừng | Thấp hơn ở thời điểm gọi, vẫn cùng ứng dụng | Tác vụ phụ trợ không trọng yếu |
| Durable work queue | Có thể tăng theo backlog | Có thể cao nếu broker và cấu hình phù hợp | Producer/consumer tách rời | Worker, retry, hấp thụ tải đột biến |
| Pub-sub event | Producer thường không chờ consumer | Theo broker/retention và cấu hình | Thấp | Một sự kiện, nhiều consumer độc lập |
| Event stream | Thấp khi ghi thành công; consumer có lag riêng | Log lưu theo retention | Thấp | Nhiều consumer, replay, phân tích, projection |
| WebSocket/STOMP | Thấp khi kết nối ổn định | Notification không đồng nghĩa dữ liệu bền vững | Client phụ thuộc endpoint/session | Cập nhật giao diện theo thời gian thực |

Đây là xu hướng thường gặp, không phải cam kết của framework. Một broker cấu hình không bền vững có thể làm mất message; một HTTP service có thể lưu command vào database trước khi trả về; một async channel có thể vẫn chạy đồng bộ nếu implementation gọi handler trực tiếp.

## 5. Độ trễ: đo toàn bộ hành trình

Độ trễ của message-driven system gồm nhiều phần:

1. Thời gian producer tạo payload, serialize và gửi.
2. Thời gian truyền qua mạng hoặc chuyển vào queue.
3. Thời gian message chờ trong backlog.
4. Thời gian consumer nhận, deserialize và xử lý.
5. Thời gian ghi kết quả xuống database hoặc gọi dịch vụ khác.

Đối với request-response, người dùng thường cảm nhận tổng thời gian của cả chuỗi. Đối với async, thời gian trả lời của producer có thể ngắn nhưng thời gian hoàn thành nghiệp vụ vẫn dài. Không nên báo cáo rằng hệ thống nhanh hơn chỉ vì API trả về sớm trong khi backlog tăng liên tục.

Hãy đo ít nhất:

- p50, p95, p99 của thời gian xử lý và thời gian chờ.
- Throughput vào/ra, số message đang chờ và tuổi message cũ nhất.
- Consumer lag, số lần retry, dead-letter count và tỷ lệ xử lý lỗi.
- Timeout, tỷ lệ request hết hạn và số công việc bị từ chối.

Đặt deadline ở ranh giới request; truyền deadline/correlation ID khi phù hợp; tránh retry vô hạn. Nếu downstream đã quá tải, retry dồn dập có thể làm hệ thống phục hồi chậm hơn.

## 6. Độ bền và ngữ nghĩa giao nhận

### 6.1. Volatile và durable

Message nằm trong bộ nhớ của một instance có thể mất khi process crash hoặc deploy. Một broker có persistent message, durable queue/topic, replication và xác nhận ghi phù hợp có thể giữ message qua một số lỗi, nhưng mức bảo vệ phụ thuộc cấu hình thực tế: durable destination, persistence, replication/quorum, acknowledgement, retention, disk và chính sách failover.

Không đồng nhất các khái niệm:

- **Durable queue/topic:** cấu trúc đích được lưu qua restart theo bảo đảm của broker.
- **Persistent message:** broker được yêu cầu lưu nội dung message theo cơ chế persistence.
- **Publisher confirm/acknowledgement:** producer biết broker đã nhận/ghi theo mức xác nhận được cấu hình.
- **Consumer acknowledgement:** consumer xác nhận đã xử lý hoặc đã nhận trách nhiệm xử lý.
- **Replication:** bản sao dữ liệu trên nhiều node; cần hiểu mức quorum và failure model.

Chỉ có queue bền vững không đủ nếu producer gửi message nhưng không xác nhận kết quả ghi, consumer ack trước khi commit nghiệp vụ hoặc broker không có cấu hình replication phù hợp.

### 6.2. At-most-once, at-least-once và effectively-once

| Ngữ nghĩa | Đặc điểm | Hệ quả thiết kế |
| --- | --- | --- |
| At-most-once | Message được xử lý không quá một lần; có thể mất | Chỉ phù hợp khi mất message chấp nhận được hoặc có cách tái tạo |
| At-least-once | Message được giao lại cho đến khi xác nhận theo chính sách; có thể trùng | Consumer phải chịu được xử lý lặp |
| Effectively-once ở nghiệp vụ | Nhiều lần giao nhưng tác động nghiệp vụ chỉ được áp dụng một lần nhờ dedup/idempotency và transaction | Cần khóa duy nhất, inbox/dedup record hoặc cập nhật có điều kiện |

Không nên hứa “exactly once” cho toàn bộ nghiệp vụ xuyên qua nhiều dịch vụ chỉ dựa vào cấu hình broker. Một broker có thể hỗ trợ giao dịch hoặc exactly-once semantics trong phạm vi cụ thể, nhưng ghi database, gọi API bên ngoài, gửi email và cập nhật nhiều hệ thống vẫn cần thiết kế nhất quán riêng.

### 6.3. Idempotency và chống trùng

Consumer idempotent nghĩa là nhận lại cùng một message không làm nghiệp vụ bị áp dụng thêm lần nữa. Một cách thường dùng là gắn `eventId` hoặc `messageId` ổn định, lưu ID đã xử lý trong cùng transaction với thay đổi nghiệp vụ, và đặt unique constraint để hai lần xử lý đồng thời không cùng thành công.

Ví dụ, khi nhận `PaymentCaptured` với `eventId=evt-123`, consumer kiểm tra inbox/dedup table. Nếu ID đã được xử lý, consumer bỏ qua tác động lặp và ack message; nếu chưa, consumer ghi dedup record và cập nhật hóa đơn trong cùng transaction. Cần xử lý trường hợp hai consumer cùng tranh một ID bằng constraint/locking, không chỉ bằng một lần `SELECT` trước khi `INSERT`.

Đối với command tạo tài nguyên, có thể dùng idempotency key do client hoặc service upstream tạo. Key cần gắn với phạm vi nghiệp vụ và lưu đủ lâu so với thời gian retry có thể xảy ra.

### 6.4. Transactional outbox và inbox

Một lỗi phổ biến là cập nhật database thành công nhưng publish event thất bại, hoặc publish event thành công rồi transaction database rollback. Nếu nghiệp vụ yêu cầu đồng bộ giữa thay đổi dữ liệu và sự kiện phát ra, có thể dùng transactional outbox:

1. Trong cùng transaction database, cập nhật dữ liệu nghiệp vụ và ghi một bản ghi outbox.
2. Một publisher đọc các bản ghi outbox chưa gửi, phát message lên broker.
3. Sau khi nhận xác nhận theo chính sách, đánh dấu bản ghi đã phát hoặc lưu trạng thái gửi.
4. Consumer dùng inbox/dedup để xử lý message lặp an toàn.

Outbox tránh yêu cầu một transaction phân tán giữa database và broker. Tuy nhiên publisher có thể gửi lại nếu crash sau khi broker nhận nhưng trước khi đánh dấu outbox hoàn tất; do đó consumer vẫn cần idempotency. Phải có chính sách retry, dọn bản ghi, giám sát backlog và xử lý poison message.

## 7. Thứ tự, phân vùng và tính nhất quán

Thứ tự toàn hệ thống thường làm giảm khả năng mở rộng. Nhiều broker chỉ bảo đảm thứ tự trong một queue hoặc partition; nhiều consumer, retry, redelivery và xử lý song song có thể khiến thời điểm hoàn tất khác thứ tự gửi.

Nếu các sự kiện của cùng một đơn hàng phải theo thứ tự, hãy dùng khóa partition nhất quán như `orderId`, và bảo đảm consumer xử lý tuần tự trong phạm vi khóa đó. Nếu không cần thứ tự toàn cục, đừng ép tất cả message vào một partition duy nhất vì nó tạo điểm nghẽn.

Consumer nên kiểm tra version hoặc sequence number của aggregate khi cần phát hiện sự kiện đến sai thứ tự. Có thể lưu sự kiện đến sớm vào vùng chờ, yêu cầu phát lại hoặc từ chối để retry theo chính sách. Không tự giả định rằng timestamp của máy gửi phản ánh thứ tự nghiệp vụ chính xác.

Eventual consistency có nghĩa các phần của hệ thống có thể quan sát trạng thái khác nhau trong một khoảng thời gian. Giao diện và API cần thể hiện điều đó: trạng thái `PROCESSING`, `PENDING` hoặc thông báo “đang cập nhật” có thể phù hợp hơn việc trả lời thành công như thể mọi consumer đã hoàn thành.

## 8. Retry, timeout, dead-letter và backpressure

### 8.1. Retry có giới hạn

Retry phù hợp với lỗi tạm thời như timeout mạng hoặc dịch vụ phụ thuộc quá tải. Dùng số lần thử tối đa, exponential backoff và jitter để tránh nhiều consumer cùng retry tại một thời điểm. Phân biệt lỗi tạm thời với lỗi dữ liệu không hợp lệ, vi phạm nghiệp vụ hoặc schema không hỗ trợ; các lỗi vĩnh viễn không nên được retry vô hạn.

### 8.2. Dead-letter queue

Message không thể xử lý sau chính sách retry có thể chuyển sang dead-letter queue (DLQ) hoặc nơi cách ly tương đương. Cần ghi lý do, exception, số lần thử, thời điểm, correlation ID và thông tin để người vận hành có thể sửa dữ liệu hoặc triển khai consumer mới rồi phát lại có kiểm soát.

DLQ không phải thùng rác để quên. Cần cảnh báo khi có message mới, phân loại lỗi, đặt thời hạn lưu và quy trình replay tránh tạo tác động nghiệp vụ trùng.

### 8.3. Backpressure và giới hạn tài nguyên

Nếu producer nhanh hơn consumer trong thời gian dài, backlog sẽ tăng. Hãy giới hạn số message đang xử lý, kích thước batch, concurrency, prefetch, queue capacity hoặc tốc độ gửi. Khi đầy, hệ thống phải có hành vi xác định: chặn producer, từ chối, trả lỗi, giảm tải hoặc ghi vào một vùng lưu trữ khác.

Không tạo thread mới cho từng message mà không có giới hạn. Trong Spring, cấu hình executor cần xem xét core/max pool size, queue capacity, rejection policy và cách shutdown chờ công việc. Một queue vô hạn có thể biến áp lực ngược thành lỗi hết bộ nhớ.

## 9. Chọn mô hình theo tình huống thực tế

| Tình huống | Mô hình gợi ý | Lý do và điều kiện cần |
| --- | --- | --- |
| Người dùng cần biết ngay dữ liệu có hợp lệ không | Synchronous request-response | Trả kết quả/validation trực tiếp; đặt timeout và giới hạn downstream |
| Tạo hóa đơn PDF sau khi đơn đã được chấp nhận | Durable work queue | Tách thời gian tạo file khỏi API; retry và idempotency theo invoice ID |
| Khi đơn hàng được đặt, kho và email cùng cần biết | Pub-sub event | Mỗi consumer có vòng đời riêng; chấp nhận eventual consistency |
| Nhiều consumer cần đọc lại lịch sử thay đổi | Event stream | Retention, offset, schema evolution và partition key được quản lý |
| Cập nhật số lượng giỏ hàng trong cùng request | Gọi service/transaction đồng bộ | Người dùng cần kết quả ngay và thao tác thường nằm trong cùng ranh giới dữ liệu |
| Gửi tín hiệu “có dữ liệu mới” tới trình duyệt | WebSocket/STOMP hoặc SSE | Client tải trạng thái chuẩn từ backend khi kết nối lại |
| Ghi metric hoặc audit không trọng yếu trong cùng process | Async in-process | Chi phí vận hành thấp; chỉ dùng nếu mất khi restart được chấp nhận |
| Ghi nhận giao dịch và phải phát event tương ứng | Database transaction + outbox + broker | Tránh mất đồng bộ giữa commit dữ liệu và publish |

Đây là điểm xuất phát để thảo luận. Trước khi triển khai, xác nhận SLA, failure mode, tải cực đại, chi phí vận hành và khả năng đội ngũ trực hệ thống hỗ trợ công nghệ đó.

## 10. Ánh xạ vào Spring Framework và hệ sinh thái Spring

### 10.1. Message và headers

`org.springframework.messaging.Message<T>` biểu diễn một payload cùng `MessageHeaders`. Payload chứa dữ liệu nghiệp vụ; headers mang metadata như correlation ID, event ID, loại sự kiện, phiên bản schema, tenant hoặc thông tin định tuyến. Không nên nhét toàn bộ dữ liệu nghiệp vụ vào headers.

`MessageBuilder` hỗ trợ tạo message theo cách rõ ràng. Message abstraction giúp handler làm việc với envelope thống nhất, nhưng payload vẫn cần có hợp đồng và quy tắc tương thích.

### 10.2. MessageChannel và MessageHandler

`MessageChannel` là abstraction gửi message. `SubscribableChannel` hỗ trợ đăng ký handler để nhận message; `PollableChannel` hỗ trợ consumer lấy message bằng thao tác receive/poll. Kiểu channel và implementation quyết định cách dispatch, chờ, timeout và cạnh tranh consumer.

Không được suy ra rằng mọi `MessageChannel` đều là durable queue hoặc asynchronous. Spring Framework cung cấp các abstraction nền; các implementation và adapter trong hệ sinh thái Spring quyết định cách message thực sự được truyền.

### 10.3. Phân biệt Spring Framework, Spring Integration và broker adapters

- **Spring Framework Messaging:** định nghĩa message, headers, channel, handler và một số hỗ trợ dispatch như executor-based channel.
- **Spring Integration:** cung cấp nhiều channel và endpoint phục vụ tích hợp, chẳng hạn `DirectChannel`, `QueueChannel`, `PublishSubscribeChannel`, poller và adapter. Đây là module riêng; không nên nhầm các class này là tất cả đều thuộc `spring-messaging`.
- **Spring AMQP:** tích hợp với RabbitMQ/AMQP, cung cấp template, listener container và các cơ chế acknowledgement/retry tùy cấu hình.
- **Spring for Apache Kafka:** tích hợp Kafka, producer/consumer, listener container, transaction và offset management.
- **Spring JMS:** tích hợp các JMS provider và listener container.
- **Spring WebSocket/STOMP:** truyền message giữa server và client qua WebSocket/STOMP; kết nối client không tự thay thế kho dữ liệu bền vững.

Chọn adapter theo broker và giao thức mà hệ thống thực sự cần. Hãy đọc cấu hình acknowledgement, persistence, retry, transaction, concurrency và serialization của adapter cụ thể; abstraction chung không thể thay thế việc kiểm tra các thuộc tính đó.

### 10.4. Application events không phải broker

`ApplicationEventPublisher` hữu ích cho sự kiện nội bộ trong cùng Spring application context. Mặc định listener được gọi đồng bộ; nếu cấu hình async, công việc có thể chạy ở executor. Application event không tự có durable storage, retry sau restart hay khả năng phát lại cho một service khác.

Nếu event chỉ là tín hiệu nội bộ, không cần tồn tại qua restart và không phải hợp đồng tích hợp giữa service, application event có thể đủ. Nếu event phải được giao đáng tin cậy qua ranh giới tiến trình, hãy dùng cơ chế lưu trữ và truyền tải có bảo đảm phù hợp.

## 11. Ví dụ Spring Messaging: tạo message envelope

Ví dụ sau minh họa cách đóng payload và metadata vào một Spring `Message`. Nó không giả lập broker, queue, persistence hay bảo đảm giao nhận; mục tiêu là cho thấy dữ liệu và metadata được tách rõ để transport/handler có thể dùng chung hợp đồng.

Tạo dự án Maven với cấu trúc:

~~~text
message-envelope-demo/
  pom.xml
  src/main/java/com/example/messaging/MessageEnvelopeDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>message-envelope-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.8</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring.version}</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/messaging/MessageEnvelopeDemo.java`:

~~~java
package com.example.messaging;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class MessageEnvelopeDemo {
    private MessageEnvelopeDemo() {
    }

    public static void main(String[] args) {
        Message<String> message = MessageBuilder
                .withPayload("OrderPlaced: order-42")
                .setHeader("eventType", "OrderPlaced")
                .setHeader("eventId", "evt-42")
                .setHeader("correlationId", "corr-42")
                .setHeader("schemaVersion", 1)
                .build();

        System.out.println(message.getPayload());
        System.out.println("eventType=" + message.getHeaders().get("eventType"));
        System.out.println("eventId=" + message.getHeaders().get("eventId"));
        System.out.println("correlationId=" + message.getHeaders().get("correlationId"));
        System.out.println("schemaVersion=" + message.getHeaders().get("schemaVersion"));
    }
}
~~~

Chạy từ thư mục chứa `pom.xml` bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.MessageEnvelopeDemo
~~~

Stdout:

~~~text
OrderPlaced: order-42
eventType=OrderPlaced
eventId=evt-42
correlationId=corr-42
schemaVersion=1
~~~

Trong hệ thống thật, producer có thể gửi message này qua adapter phù hợp; consumer phải xác thực payload, kiểm tra phiên bản schema, dùng event ID để chống trùng và ghi log bằng correlation ID. Không nên coi việc tạo `Message` thành công là bằng chứng broker đã lưu hoặc consumer đã xử lý.

## 12. Các lỗi thiết kế thường gặp

- **Chọn async chỉ để API có vẻ nhanh:** caller trả về nhanh nhưng backlog tăng và nghiệp vụ không hoàn tất đúng hạn. Đo cả thời gian xử lý cuối cùng, không chỉ response time.
- **Dùng in-memory queue cho dữ liệu bắt buộc phải giao:** restart có thể làm mất công việc. Chuyển sang durable broker/outbox khi yêu cầu nghiệp vụ đòi hỏi.
- **Giả định message chỉ được giao một lần:** crash sau khi commit nhưng trước khi ack có thể khiến consumer nhận lại. Thiết kế idempotency ngay từ đầu.
- **Retry vô hạn mọi lỗi:** message độc hại hoặc payload sai sẽ chiếm tài nguyên mãi. Phân loại lỗi, giới hạn retry và dùng DLQ.
- **Dùng một partition cho mọi thứ để giữ thứ tự toàn cục:** throughput bị giới hạn. Chỉ bảo đảm thứ tự theo aggregate/key khi đó là yêu cầu thực sự.
- **Phát event trước khi transaction nghiệp vụ commit:** consumer có thể nhìn thấy sự kiện cho dữ liệu chưa được lưu. Dùng after-commit phù hợp hoặc transactional outbox.
- **Đưa dữ liệu nhạy cảm vào header/log:** metadata cũng có thể bị ghi log hoặc truyền qua nhiều thành phần. Chỉ đưa thông tin tối thiểu và áp dụng kiểm soát truy cập/mã hóa.
- **Dùng event notification thay cho query:** consumer nhận event nhưng không có đủ trạng thái để trả lời truy vấn hiện tại. Cần projection/read model hoặc API query riêng.
- **Không quản lý schema:** producer đổi tên field hoặc kiểu dữ liệu khiến consumer cũ lỗi. Có versioning và quy tắc tương thích khi rollout.
- **Không theo dõi backlog/lag:** hệ thống vẫn nhận message nhưng kết quả nghiệp vụ đã chậm hơn SLA. Cảnh báo theo tuổi message và consumer lag, không chỉ theo trạng thái process.

## 13. Quy trình ra quyết định

1. Xác định ai cần kết quả và khi nào: ngay trong request, sau vài giây hay bất kỳ lúc nào trong một SLA dài hơn.
2. Xác định khả năng mất dữ liệu: nếu process hoặc broker restart, message nào phải được giữ?
3. Chọn topology: một consumer, nhiều subscriber, hay nhiều consumer group cần replay.
4. Chốt semantics: at-most-once hay at-least-once; nơi lưu dedup key; cách xử lý duplicate và out-of-order.
5. Chốt tải và giới hạn: throughput, burst, queue capacity, concurrency, backpressure và retention.
6. Chọn adapter Spring phù hợp: in-process event/channel, Spring Integration, AMQP, Kafka, JMS hoặc WebSocket/STOMP.
7. Thiết kế lỗi trước khi triển khai: timeout, retry, DLQ, poison message, shutdown và replay.
8. Kiểm thử failure mode: kill producer/consumer, restart broker, ngắt mạng, gửi duplicate, gửi sai schema, tăng tải và kiểm tra phục hồi.
9. Đo SLA đầu cuối và chi phí vận hành; chỉ giữ mô hình phức tạp khi lợi ích nghiệp vụ rõ ràng.

## 14. Ghi nhớ

Chọn mô hình trao đổi bằng cách bắt đầu từ kết quả nghiệp vụ, ngân sách độ trễ, khả năng chấp nhận mất dữ liệu, nhu cầu nhiều consumer, thứ tự và khả năng xử lý lặp. Request-response phù hợp khi cần kết quả ngay; async trong bộ nhớ phù hợp với tác vụ phụ trợ có thể mất; durable queue phù hợp với công việc nền; pub-sub phù hợp với một sự kiện có nhiều bên quan tâm; event stream phù hợp khi cần nhiều consumer và khả năng replay. Spring Messaging chuẩn hóa message và điểm gửi/nhận, còn độ bền, delivery semantics, ordering và retry phụ thuộc implementation, broker, cấu hình và thiết kế consumer. Một lựa chọn tốt phải đo được, vận hành được và bảo vệ được tác động nghiệp vụ khi có lỗi.