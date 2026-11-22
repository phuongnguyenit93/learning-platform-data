# Giao tiếp đồng bộ, bất đồng bộ và lựa chọn theo luồng nghiệp vụ

## 1. Giao tiếp giữa các thành phần là một quyết định kiến trúc

Trong hệ thống phân tán, một dịch vụ thường phải gọi dịch vụ khác để hoàn thành hành trình nghiệp vụ. Cách giao tiếp quyết định **ai phải chờ ai, khi nào kết quả được xem là hoàn tất, lỗi lan truyền tới đâu và trạng thái dữ liệu được phối hợp như thế nào**.

Hai kiểu giao tiếp thường gặp:

- **Đồng bộ (synchronous communication):** bên gọi gửi yêu cầu và chờ kết quả của thao tác trong cùng một tương tác. Ví dụ API đặt chỗ gọi dịch vụ kiểm tra tồn phòng và trả kết quả ngay cho khách.
- **Bất đồng bộ (asynchronous communication):** bên gửi bàn giao thông điệp hoặc công việc cho một cơ chế trung gian hay bên nhận; việc xử lý và phản hồi có thể xảy ra sau. Ví dụ sau khi xác nhận đặt chỗ, hệ thống phát sự kiện để gửi email và cập nhật báo cáo.

Đồng bộ và bất đồng bộ là **mô hình tương tác**, không phải tên của một giao thức cụ thể. HTTP có thể được dùng để gửi lệnh bất đồng bộ rồi trả 202 Accepted; message broker có thể được dùng theo request/reply nhưng bản chất vẫn có thời gian chờ và coupling logic. Cần mô tả rõ ngữ nghĩa trước khi chọn REST, gRPC, queue, event broker hay callback.

Trong module **CLOUD_ARCHITECTURE**, lựa chọn giao tiếp API phải xuất phát từ yêu cầu nghiệp vụ và liên hệ tới mạng, compute, dữ liệu, mô hình triển khai; sau đó đánh giá đánh đổi về **độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

Ví dụ xuyên suốt: nền tảng đặt chỗ cần tìm phòng, giữ phòng, thu tiền và gửi thông báo. Khách cần biết ngay thao tác nào đã thành công; hệ thống cũng phải xử lý được lúc cổng thanh toán phản hồi chậm, webhook gửi lặp hoặc email tạm thời không gửi được.

## 2. Đồng bộ: khi nào cần kết quả ngay?

Trong tương tác đồng bộ, luồng điển hình là:

~~~mermaid
sequenceDiagram
    actor U as Khách hàng
    participant A as Booking API
    participant I as Inventory Service
    participant D as Database
    U->>A: POST /bookings
    A->>I: Kiểm tra và giữ phòng
    I->>D: Ghi giữ chỗ
    D-->>I: Kết quả
    I-->>A: Đã giữ / hết phòng
    A-->>U: Trạng thái yêu cầu
~~~

Bên gọi chỉ có thể hoàn tất phản hồi sau khi các bước bắt buộc trả kết quả. Cách này phù hợp khi người dùng cần câu trả lời ngay, nghiệp vụ cần kết quả kiểm tra/cập nhật trước bước tiếp theo và các dependency có thể đáp ứng ngân sách latency end-to-end.

Ưu điểm là mô hình dễ hiểu, kết quả trực tiếp và phù hợp với truy vấn/command cần phản hồi tức thì. Nhược điểm là **coupling theo thời gian**: bên nhận chậm hoặc mất kết nối có thể khiến bên gọi chờ, timeout hoặc lỗi theo chuỗi.

### 2.1. Chi phí của chuỗi lời gọi đồng bộ

Giả sử một API cần gọi lần lượt ba dịch vụ:

| Bước | Thời gian minh họa |
| --- | ---: |
| Kiểm tra tồn phòng | 80 ms |
| Tính giá | 60 ms |
| Xác minh quyền/điều kiện | 40 ms |
| Xử lý tại API và overhead mạng | 70 ms |
| **Tổng thời gian tuần tự gần đúng** | **250 ms** |

Nếu các bước chạy tuần tự, thời gian đáp ứng có xu hướng gần tổng thời gian từng bước cộng overhead. Nếu một bước mất 2 giây, toàn bộ request có thể phải chờ tương ứng. Có thể chạy song song các bước độc lập để giảm thời gian, nhưng phải xử lý lỗi từng nhánh, hủy công việc khi không còn cần thiết và tránh tạo tải đột biến xuống dependency.

Không được cộng p95 riêng của từng dịch vụ rồi khẳng định đó là p95 end-to-end. Phân bố latency và tương quan giữa các lời gọi cần được đo từ trace của toàn hành trình.

### 2.2. Timeout và ngân sách thời gian

Mỗi cuộc gọi đồng bộ cần timeout hữu hạn. Ngân sách thời gian toàn hành trình nên được chia cho các bước:

~~~text
Client timeout:       2.0 s
Gateway budget:       1.8 s
Booking API budget:   1.5 s
Inventory call:       0.5 s
Pricing call:         0.3 s
~~~

Các con số chỉ là ví dụ. Thực tế cần tính cả kết nối, DNS, TLS, hàng đợi nội bộ, xử lý dữ liệu và serialize response. Timeout ở tầng ngoài phải đủ dài hơn deadline phân bổ cho bước bên trong, nhưng không nên quá dài đến mức giữ tài nguyên cho request đã không còn giá trị.

Khi timeout xảy ra, **không đồng nghĩa thao tác phía server đã bị hủy hoặc chưa thực hiện**. Client có thể mất phản hồi sau khi server đã ghi dữ liệu. Với command có tác dụng ghi, cần khóa idempotency hoặc cơ chế truy vấn trạng thái để client không tạo thao tác trùng khi retry.

## 3. Bất đồng bộ: khi nào không cần giữ người gọi chờ?

Trong mô hình bất đồng bộ, bên gửi bàn giao thông điệp cho queue/broker hoặc một cơ chế tiếp nhận công việc. Bên gửi có thể nhận xác nhận đã tiếp nhận, còn xử lý hoàn tất sau:

~~~mermaid
sequenceDiagram
    actor U as Khách hàng
    participant A as Booking API
    participant DB as Database
    participant Q as Event Broker
    participant W as Notification Worker
    U->>A: Hoàn tất đặt chỗ
    A->>DB: Ghi đặt chỗ + sự kiện cần phát
    DB-->>A: Commit
    A->>Q: Publish BookingConfirmed
    Q-->>A: Broker nhận thông điệp
    A-->>U: Đã xác nhận đặt chỗ
    Q-->>W: Chuyển sự kiện
    W->>W: Gửi email / SMS
~~~

Trong hệ thống dùng outbox, sự kiện được ghi vào database cùng transaction nghiệp vụ rồi một publisher chuyển ra broker. Điều này tránh khoảng trống giữa commit dữ liệu và publish sự kiện.

Bất đồng bộ thường phù hợp khi công việc có thể hoàn tất sau mà không bắt người dùng chờ; cần co giãn theo hàng đợi; có thể chấp nhận độ trễ nhất quán và có cách hiển thị trạng thái; hoặc nhiều bên nhận độc lập cần phản ứng với cùng một sự kiện.

Ưu điểm là giảm coupling theo thời gian, giúp điều hòa tải và tách bên phát với bên nhận. Đánh đổi gồm quản lý trạng thái công việc, khả năng xử lý lặp, thứ tự, dead-letter, quan sát queue và trải nghiệm người dùng khi chờ kết quả.

### 3.1. Phân biệt command, event và query

| Loại thông điệp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Command** | Yêu cầu một bên thực hiện hành động | ReserveRoom, ChargePayment |
| **Event** | Thông báo một sự kiện đã xảy ra | BookingConfirmed, PaymentCaptured |
| **Query** | Yêu cầu đọc dữ liệu và mong nhận kết quả | GetBookingStatus, SearchRooms |

Command thường nhắm tới một handler có trách nhiệm thực hiện. Event mô tả sự kiện đã xảy ra, có thể có nhiều subscriber độc lập. Query thường phù hợp với phản hồi đồng bộ, nhưng có thể trở thành asynchronous job nếu truy vấn dài hoặc xuất dữ liệu lớn.

Không nên đặt tên event như một lệnh chưa xảy ra. BookingConfirmed có nghĩa đặt chỗ đã được xác nhận; ConfirmBooking là yêu cầu xác nhận. Sự khác biệt này giúp consumer hiểu đúng trạng thái và tránh thực hiện hành động dựa trên sự kiện sai ngữ nghĩa.

### 3.2. HTTP 202 Accepted không phải kết quả nghiệp vụ hoàn tất

Một API có thể nhận yêu cầu tạo báo cáo hoặc xử lý tác vụ và trả:

~~~http
HTTP/1.1 202 Accepted
Location: /jobs/job-8342
Retry-After: 3
Content-Type: application/json

{
  "jobId": "job-8342",
  "status": "accepted",
  "statusUrl": "/jobs/job-8342"
}
~~~

202 Accepted cho biết request đã được chấp nhận để xử lý, không khẳng định công việc đã hoàn tất hoặc chắc chắn sẽ thành công. API nên cung cấp cách xem trạng thái, lỗi cuối cùng, thời hạn giữ kết quả và cách hủy nếu nghiệp vụ hỗ trợ.

## 4. Chọn mô hình theo từng luồng nghiệp vụ

Không nên chọn một kiểu giao tiếp cho toàn hệ thống. Hãy phân loại từng bước theo câu hỏi: **ai cần câu trả lời, cần vào thời điểm nào, hậu quả nếu chậm hoặc thất bại là gì, và có chấp nhận xử lý trễ không?**

| Luồng nghiệp vụ | Mô hình thường phù hợp | Lý do và điều kiện |
| --- | --- | --- |
| Tìm phòng và trả kết quả | Đồng bộ | Khách cần xem kết quả để chọn; có thể cache và giới hạn truy vấn |
| Kiểm tra/giữ phòng tạm thời | Đồng bộ hoặc workflow có trạng thái | Cần phản hồi giữ chỗ thành công/hết phòng; kiểm soát cạnh tranh và timeout |
| Xác nhận giao dịch thanh toán | Đồng bộ với nhà cung cấp hoặc workflow nhiều bước | Cần xác định trạng thái; timeout có thể dẫn tới trạng thái chưa rõ và cần đối soát/webhook |
| Gửi email xác nhận | Bất đồng bộ | Không nên bắt khách chờ hệ thống email |
| Tạo báo cáo lớn | Bất đồng bộ | Thời gian thực hiện dài; có job status và thông báo khi xong |
| Cập nhật chỉ mục tìm kiếm | Bất đồng bộ | Chấp nhận độ trễ cập nhật; có cơ chế replay/rebuild |
| Kiểm tra quyền truy cập đơn hàng | Đồng bộ | Kết quả cần trước khi trả dữ liệu nhạy cảm |
| Đồng bộ dữ liệu sang analytics | Bất đồng bộ | Tách tải phân tích khỏi giao dịch và xử lý theo lô |

| Yếu tố | Nghiêng về đồng bộ | Nghiêng về bất đồng bộ |
| --- | --- | --- |
| Người dùng cần kết quả ngay | Có | Ít phù hợp, trừ khi trả trạng thái xử lý |
| Công việc dài/không dự đoán thời gian | Khó quản lý timeout | Phù hợp với job status |
| Dependency có độ sẵn sàng thấp | Dễ lan truyền lỗi | Có thể đệm tải, nhưng broker/consumer cũng cần HA |
| Nhiều subscriber độc lập | Có thể gọi tuần tự/song song nhưng coupling cao | Event phù hợp để phân phối |
| Cần đọc trạng thái nhất quán ngay | Thường dễ diễn đạt hơn | Cần mô hình trạng thái/độ trễ rõ |
| Muốn hấp thụ burst | Cần capacity, rate limit và backpressure trực tiếp | Queue hữu hạn có thể đệm tải |
| Gỡ lỗi | Trace call chain | Correlation ID, event history và consumer lag |
| Vận hành | Ít thành phần hơn ở hệ thống nhỏ | Thêm broker, DLQ, schema và quy trình replay |

Đây là xu hướng chứ không phải luật cứng. Một hệ thống nhỏ có thể dùng đồng bộ cho hầu hết luồng vì dễ vận hành; hệ thống lớn có thể dùng asynchronous job cho tác vụ dài nhưng vẫn cung cấp endpoint đồng bộ để tra cứu trạng thái.

## 5. Nhất quán dữ liệu và transaction giữa nhiều service

Lựa chọn đồng bộ hay bất đồng bộ ảnh hưởng tới thời điểm dữ liệu được nhìn thấy và cách xử lý transaction. Trong một service dùng chung database, một transaction có thể cập nhật nhiều bản ghi nguyên tử. Khi nghiệp vụ đi qua nhiều service/database, **không thể mặc định một transaction cục bộ bao phủ tất cả hệ thống**.

### 5.1. Eventual consistency

**Nhất quán cuối cùng (eventual consistency)** có nghĩa các bản sao hoặc view dữ liệu có thể tạm thời khác nhau sau một thay đổi, nhưng nếu không có cập nhật mới và xử lý thành công thì chúng sẽ hội tụ theo mô hình đã định nghĩa.

Ví dụ khi đặt chỗ được xác nhận:

1. Booking database ghi trạng thái CONFIRMED.
2. Event BookingConfirmed được phát.
3. Search index cập nhật số phòng đã đặt sau một khoảng trễ.
4. Analytics nhận sự kiện và cập nhật báo cáo.

Trong vài giây, giao diện tìm kiếm có thể chưa phản ánh thay đổi. Điều này chỉ chấp nhận được nếu quy trình giữ phòng/đặt phòng ở nguồn dữ liệu có thẩm quyền vẫn ngăn đặt trùng. Không được dùng chỉ mục tìm kiếm trễ làm nguồn quyết định cuối cùng cho giao dịch ghi quan trọng.

### 5.2. Saga và quy trình nhiều bước

Nếu giao dịch trải qua nhiều service, có thể mô hình hóa thành **Saga**: mỗi bước có transaction cục bộ, kèm hành động bù trừ (compensation) nếu bước sau thất bại.

~~~mermaid
flowchart LR
    A["Giữ phòng"] --> B["Ủy quyền thanh toán"]
    B --> C["Xác nhận đặt chỗ"]
    C --> D["Phát sự kiện thông báo"]
    B -. thất bại .-> X["Giải phóng giữ phòng"]
    C -. lỗi không thể hoàn tất .-> Y["Hủy/hoàn giao dịch theo quy tắc"]
~~~

Ví dụ: tạo giữ chỗ có thời hạn; yêu cầu cổng thanh toán ủy quyền/thu tiền theo hợp đồng; chuyển đơn sang CONFIRMED. Nếu thanh toán thất bại thì giải phóng giữ chỗ. Nếu bước xác nhận thất bại sau khi đã thu tiền thì cần quy trình hoàn tiền/void và đối soát.

Hành động bù trừ không nhất thiết đảo ngược vật lý thao tác ban đầu hoặc chạy tức thì. Hoàn tiền có thể cần nhiều phút hoặc xử lý thủ công. Workflow phải có trạng thái rõ như PENDING_PAYMENT, CONFIRMED, PAYMENT_UNKNOWN, COMPENSATING, CANCELLED và REQUIRES_RECONCILIATION nếu phù hợp.

### 5.3. Transactional outbox

Một lỗi kinh điển khi phát event là: ghi booking thành công trong DB, tiến trình crash trước khi publish event; dữ liệu booking đã đổi nhưng consumer không biết để gửi email/cập nhật index.

**Transactional outbox** giải quyết khoảng trống này bằng cách ghi thay đổi nghiệp vụ và bản ghi sự kiện cần phát trong **cùng một transaction database**. Một publisher riêng đọc outbox và gửi message tới broker; sau khi gửi, nó đánh dấu đã xử lý theo chiến lược phù hợp.

~~~mermaid
flowchart LR
    API["Booking API"] --> DB[("Booking DB: booking + outbox")]
    DB --> PUB["Outbox Publisher"]
    PUB --> Q["Message Broker"]
    Q --> C["Consumers"]
~~~

Outbox giảm nguy cơ mất sự kiện giữa commit và publish, nhưng **không mặc nhiên tạo exactly-once end-to-end**. Publisher có thể gửi message rồi crash trước khi ghi dấu hoàn tất, dẫn tới gửi lặp. Consumer vẫn cần idempotency/deduplication và quan sát outbox backlog.

## 6. Bảo đảm xử lý lặp: idempotency và delivery semantics

Trong hệ phân tán, timeout, retry, broker redelivery và consumer restart khiến một thông điệp có thể được xử lý hơn một lần. Cần định nghĩa delivery semantics:

- **At-most-once:** tối đa một lần giao; có thể mất thông điệp nếu lỗi ở thời điểm không thuận lợi.
- **At-least-once:** giao ít nhất một lần khi cơ chế retry/recovery thành công; có thể giao lặp.
- **Exactly-once:** cần định nghĩa chính xác phạm vi bảo đảm; tính chất này thường chỉ có trong một ranh giới nhất định của broker/transaction, không tự kéo dài qua mọi database, API bên ngoài và side effect.

Vì vậy nhiều hệ thống thực tế chọn at-least-once và thiết kế consumer **idempotent**.

### 6.1. Idempotency cho API ghi

Với API đặt chỗ, client gửi một Idempotency-Key duy nhất cho một ý định tạo đơn; server lưu key cùng kết quả/trạng thái để lần gọi lặp trả lại kết quả trước.

~~~http
POST /bookings
Idempotency-Key: 7f7c6a8d-example
Content-Type: application/json

{
  "roomId": "room-42",
  "checkIn": "2026-12-18",
  "checkOut": "2026-12-21"
}
~~~

Server cần xác định key có phạm vi theo tenant/user/client nào và giữ trong bao lâu; cùng key nhưng payload khác trả lỗi gì; nếu yêu cầu đầu đang xử lý thì request thứ hai chờ hay nhận trạng thái; nếu DB commit nhưng phản hồi mất thì lần retry đọc được kết quả nào; và nếu key hết hạn nhưng client vẫn retry thì nghiệp vụ bảo vệ thế nào.

Idempotency không chỉ là cache response. Với thao tác ghi, cần ràng buộc transaction/database đủ mạnh để hai request cạnh tranh cùng key không tạo hai kết quả.

### 6.2. Consumer deduplication

Message event nên có eventId ổn định. Consumer có thể ghi nhận eventId đã xử lý trong cùng transaction với thay đổi dữ liệu của nó. Khi broker gửi lặp, consumer nhận ra event cũ và không lặp side effect. Với side effect ngoài DB như gửi email hay gọi đối tác, cần xác định cách giảm trùng vì không phải nhà cung cấp nào cũng hỗ trợ idempotency.

## 7. Thứ tự, partition và khả năng mở rộng consumer

Không phải mọi event cần thứ tự toàn cục. Yêu cầu ordering phải được xác định theo **đối tượng nghiệp vụ**.

Ví dụ một booking có các sự kiện BookingCreated → PaymentAuthorized → BookingConfirmed. Nếu BookingConfirmed đến trước BookingCreated do xử lý song song hoặc replay, consumer cần phát hiện phiên bản/trạng thái và xử lý an toàn.

Các cách phổ biến:

- **Partition theo entity key:** các event của cùng bookingId đi vào cùng partition key để giữ thứ tự trong phạm vi broker hỗ trợ.
- **Sequence/version number:** consumer so sánh phiên bản để bỏ qua event cũ hoặc phát hiện event bị thiếu.
- **State machine:** chỉ chấp nhận chuyển trạng thái hợp lệ; event đến sai thứ tự được retry, lưu chờ hoặc đưa vào reconciliation.
- **Idempotent processing:** cùng event gửi lại không làm lặp hiệu ứng.

Tăng số partition và consumer có thể tăng throughput nhưng cũng làm phức tạp ordering, rebalance, chi phí và quan sát. Một partition nóng (hot partition) có thể giới hạn throughput của một tenant/entity lớn.

## 8. Retry, backoff, circuit breaker và dead-letter queue

Retry giúp vượt qua lỗi tạm thời, nhưng retry vô hạn hoặc đồng loạt có thể biến một lỗi nhỏ thành sự cố lan rộng.

| Loại lỗi | Hướng xử lý thường cân nhắc |
| --- | --- |
| Timeout kết nối hoặc lỗi mạng tạm thời | Retry hữu hạn với exponential backoff và jitter, chỉ khi thao tác an toàn |
| HTTP 429 | Tôn trọng Retry-After nếu được cung cấp, giảm tốc độ |
| HTTP 5xx tạm thời | Retry theo chính sách, giới hạn số lần và deadline |
| HTTP 4xx do dữ liệu/quyền không hợp lệ | Không retry tự động nếu đầu vào/quyền chưa thay đổi |
| Lỗi schema/serialization | Quarantine hoặc DLQ; sửa consumer/schema trước khi phát lại |
| Lỗi nghiệp vụ vĩnh viễn | Đánh dấu thất bại hoặc yêu cầu xử lý nghiệp vụ, không retry vô hạn |

Ví dụ exponential backoff có jitter:

~~~text
delay(attempt) = random(0, min(maxDelay, baseDelay * 2^attempt))
~~~

Giới hạn số lần thử, tổng thời gian retry và thời hạn công việc. Tránh để client, API gateway, SDK và worker cùng tự retry một request vì số lần gọi có thể nhân lên nhiều lần.

### 8.1. Circuit breaker và bulkhead

- **Circuit breaker** tạm ngừng gọi dependency khi tỷ lệ lỗi/timeout vượt điều kiện; sau thời gian chờ, cho phép một số request thử phục hồi.
- **Bulkhead** giới hạn tài nguyên dành cho từng nhóm phụ thuộc hoặc loại tác vụ để một dependency chậm không chiếm hết thread, connection hay worker của phần còn lại.
- **Timeout/cancellation** giới hạn thời gian tài nguyên bị giữ cho công việc không còn khả năng thành công.

Các cơ chế này hữu ích với cuộc gọi đồng bộ tới nhà cung cấp thanh toán hoặc dịch vụ nội bộ có độ tin cậy khác nhau.

### 8.2. Dead-letter queue (DLQ)

Thông điệp đã vượt số lần thử hoặc gặp lỗi không thể xử lý có thể được chuyển vào DLQ/quarantine. DLQ không phải nơi cất dữ liệu rồi quên; cần cảnh báo khi số lượng/tuổi message tăng, lưu nguyên nhân và correlation ID, phân loại lỗi, chỉ replay sau khi sửa nguyên nhân, và bảo vệ quyền đọc/replay vì message có thể chứa dữ liệu khách hàng.

## 9. Thiết kế queue, pub-sub và event contract

| Kiểu | Mô hình | Phù hợp |
| --- | --- | --- |
| Work queue | Một message thường được một worker trong nhóm nhận xử lý | Job xử lý ảnh, gửi email, tác vụ nền |
| Publish-subscribe | Một event có thể có nhiều subscriber độc lập | BookingConfirmed cho thông báo, analytics và cập nhật chỉ mục |
| Stream/log | Lưu chuỗi event có offset/retention, consumer đọc theo vị trí | Event history, analytics, replay và streaming |
| Request/reply qua broker | Lệnh gửi qua message và người gọi chờ correlation response | Tích hợp cần tách transport nhưng vẫn cần phản hồi; cần cân nhắc timeout |

Đừng phát một event vào work queue nếu cần nhiều nhóm consumer đều nhận; tùy broker, consumer trong cùng group thường cạnh tranh nhận message, còn các group/subscription khác nhau nhận bản sao độc lập theo semantics nền tảng.

Một event nên có envelope có thể truy vết:

~~~json
{
  "eventId": "evt-9b4a",
  "eventType": "BookingConfirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-12-18T08:30:00Z",
  "producer": "booking-service",
  "correlationId": "req-7a21",
  "aggregateId": "booking-42",
  "sequence": 3,
  "data": {
    "bookingId": "booking-42",
    "customerRef": "customer-18"
  }
}
~~~

Không đưa toàn bộ thông tin thanh toán, token hoặc dữ liệu cá nhân vào event nếu consumer không cần. Ưu tiên định danh tham chiếu và kiểm soát quyền truy cập tới dữ liệu chi tiết. Message contract cần có owner, schema version, quy tắc tương thích và thời gian hỗ trợ phiên bản cũ.

### 9.1. Schema evolution

Khi thêm field, đổi kiểu hoặc đổi semantics, phải nghĩ tới consumer cũ đang chạy và message cũ còn trong retention. Có thể thêm field optional với default rõ ràng, dùng versioning khi thay đổi không tương thích, triển khai consumer tương thích trước hoặc theo expand-and-contract, và không tái sử dụng tên field với ý nghĩa mới.

## 10. Quan sát giao tiếp đồng bộ và bất đồng bộ

Hai mô hình cần cách quan sát khác nhau nhưng nên dùng chung **correlation/trace context** để nối hành trình:

| Khía cạnh | Đồng bộ | Bất đồng bộ |
| --- | --- | --- |
| Latency | Thời gian request end-to-end, p95/p99 từng dependency | Thời gian từ enqueue đến hoàn tất, tuổi message và consumer processing time |
| Lỗi | HTTP status, timeout, connection reset, circuit state | Publish failure, retry count, redelivery, poison message, DLQ |
| Throughput | Requests/second, concurrent requests, connection pool | Messages/second, queue depth, consumer lag, partition utilization |
| Tương quan | Trace ID, span cho từng lời gọi | Correlation ID, event ID, causation ID và context xuyên consumer |
| SLO | Tỷ lệ request hoàn tất đúng hạn | Tỷ lệ job/event hoàn tất trong thời hạn nghiệp vụ |
| Vận hành | Dependency dashboard, timeout budget và runbook | Backlog age, DLQ, replay procedure và consumer ownership |

**Queue depth thấp không luôn đồng nghĩa khỏe.** Nếu consumer bị treo nhưng message không được nhận, cần xem oldest message age, processing rate, consumer health và delivery errors. Queue tăng ngắn hạn trong chiến dịch có thể bình thường nếu tốc độ xử lý sau đó bắt kịp trong SLO.

Với giao tiếp bất đồng bộ, cần theo dõi thời gian từ lúc nghiệp vụ phát sinh tới lúc mọi side effect quan trọng hoàn tất, không chỉ thời gian broker nhận message.

## 11. Bảo mật giao tiếp và quản lý quyền

Đồng bộ hay bất đồng bộ đều phải xác thực bên gửi, kiểm tra quyền và bảo vệ dữ liệu:

- Dùng TLS cho kết nối mạng; mTLS khi cần xác thực hai chiều giữa workload.
- Service identity và IAM cấp quyền tối thiểu cho publish/consume từng queue/topic.
- Không coi việc ở cùng VPC hoặc cùng cluster là đủ tin cậy.
- Mã hóa dữ liệu lưu trong broker/storage theo yêu cầu; quản lý khóa và vòng đời secret.
- Kiểm tra payload, schema, kích thước và nguồn phát; chống message giả mạo/replay.
- Giới hạn quyền đọc/replay DLQ và event history; audit thao tác quản trị.
- Tránh log token, thông tin xác thực và nội dung payload nhạy cảm.

Ví dụ chỉ booking-service được phép publish BookingConfirmed; notification-service và search-indexer có subscription riêng. Notification worker không cần quyền đọc database giao dịch hoặc phát lại event vào topic nghiệp vụ. Cấp quyền theo chức năng giảm rủi ro khi một consumer bị xâm nhập.

## 12. Chi phí và các đánh đổi vận hành

Giao tiếp đồng bộ thường có ít thành phần trung gian hơn, nhưng tăng phụ thuộc trực tiếp, connection, giữ thread và rủi ro timeout. Bất đồng bộ thêm broker, storage thông điệp, network transfer, consumer runtime, monitoring, DLQ và hoạt động xử lý dữ liệu trễ.

| Tiêu chí | Đồng bộ | Bất đồng bộ |
| --- | --- | --- |
| Độ trễ phản hồi cho người dùng | Kết quả trực tiếp khi dependency nhanh | Có thể chỉ trả trạng thái đã nhận |
| Coupling theo thời gian | Cao hơn: bên nhận phải sẵn sàng lúc gọi | Thấp hơn: có thể xử lý sau |
| Điều hòa burst | Cần capacity, rate limit và backpressure trực tiếp | Queue hữu hạn có thể đệm tải |
| Nhất quán | Dễ thể hiện kết quả ngay trong luồng, nhưng nhiều service vẫn cần transaction strategy | Thường có độ trễ hội tụ; cần state machine và consumer idempotency |
| Gỡ lỗi | Call trace trực tiếp | Theo correlation ID xuyên message/retry |
| Vận hành | Ít broker/consumer hơn | Thêm backlog, DLQ, schema, replay và retention |
| Chi phí | Compute và connection của call path | Broker, lưu message, egress, worker và observability |

Khi tính tổng chi phí, không chỉ so giá REST request với message. Hãy tính số lần retry, thời gian giữ connection, compute chờ, broker throughput, retention, message size, cross-zone/region traffic và nhân lực vận hành. Một asynchronous workflow xử lý kém có thể tốn hơn synchronous đơn giản.

## 13. Quy trình lựa chọn theo luồng nghiệp vụ

~~~mermaid
flowchart TD
    A["Xác định hành trình và kết quả nghiệp vụ"] --> B{"Người gọi cần kết quả ngay?"}
    B -->|Có| C["Đồng bộ: ngân sách latency, timeout và fallback"]
    B -->|Không| D["Bất đồng bộ: command/event, queue và trạng thái job"]
    C --> E{"Nhiều service / side effect?"}
    D --> F["Thiết kế idempotency, ordering, retry và DLQ"]
    E -->|Có| G["Transaction strategy / Saga / outbox"]
    E -->|Không| H["API contract và error handling"]
    G --> I["Security, observability, capacity và DR"]
    H --> I
    F --> I
    I --> J["Load/failure test và ADR"]
~~~

Với mỗi luồng, ghi mục tiêu nghiệp vụ, ngữ nghĩa query/command/event, thời gian p95/p99 và deadline, nguồn sự thật, consistency, thứ tự, idempotency, lỗi/retry/fallback, bảo mật, SLI/SLO, owner, runbook và chi phí. Không áp bất đồng bộ chỉ vì microservice hiện đại nên phải dùng event; cũng không bắt client chờ email, báo cáo hoặc analytics hoàn tất khi công việc có thể chạy độc lập.

## 14. Bài thực hành: thiết kế giao tiếp cho hành trình đặt chỗ

**Bối cảnh:** một khách chọn phòng, hệ thống kiểm tra tồn, yêu cầu thanh toán, xác nhận đơn và gửi email. Cổng thanh toán đôi khi phản hồi chậm và có webhook gửi lại nhiều lần. Search index và báo cáo không yêu cầu cập nhật tức thời.

### Nhiệm vụ

1. Vẽ sequence diagram cho hành trình đặt phòng, phân biệt đoạn synchronous với asynchronous.
2. Định nghĩa API POST /bookings, status resource cho operation chưa hoàn tất và hợp đồng idempotency.
3. Thiết kế event BookingConfirmed gồm event ID, schema version, correlation ID, aggregate ID và dữ liệu tối thiểu cần thiết.
4. Chọn queue hay pub/sub cho email, search index và analytics; giải thích consumer group/subscription và retention.
5. Xây dựng state machine cho timeout thanh toán, webhook lặp, webhook đến muộn và hoàn tiền.
6. Chọn chiến lược outbox/inbox, retry, backoff, DLQ và reconciliation.
7. Định nghĩa SLI cho API đồng bộ và job bất đồng bộ; ghi p95/p99, oldest message age, retry count, DLQ và business completion.
8. So sánh ít nhất hai phương án về độ tin cậy, độ trễ, bảo mật, chi phí và vận hành; ghi ADR kèm điều kiện phải xem lại.

### Mẫu ma trận thiết kế

| Luồng | Kiểu giao tiếp | Kết quả được coi là hoàn tất | Bảo vệ lỗi trọng yếu |
| --- | --- | --- | --- |
| Search rooms | Đồng bộ query | Có kết quả hoặc lỗi có thể giải thích | Timeout, cache, rate limit |
| Reserve room | Đồng bộ command có trạng thái | Giữ chỗ thành công hoặc từ chối | Idempotency, transaction, concurrency control |
| Payment | Đồng bộ khởi tạo + webhook/event bất đồng bộ | Trạng thái thanh toán được xác minh | Idempotency, signature verification, reconciliation |
| Send confirmation email | Bất đồng bộ | Provider/worker xử lý hoặc ghi nhận lỗi cuối | Retry hữu hạn, DLQ, chống gửi trùng |
| Update search index | Bất đồng bộ event | Index đạt phiên bản dữ liệu tương ứng | Ordering/version, replay và rebuild |
| Analytics | Bất đồng bộ/stream/batch | Dữ liệu được xử lý trong cửa sổ cho phép | Backlog monitoring, schema evolution |

### Tiêu chí hoàn thành

- Không nhầm 202 Accepted với nghiệp vụ đã hoàn tất.
- Các thao tác ghi có idempotency và cách xử lý timeout chưa rõ kết quả.
- Event có schema/identity/ordering phù hợp và consumer xử lý lặp an toàn.
- Có phương án cho trường hợp publish thất bại sau commit, retry kéo dài và DLQ.
- Trải nghiệm người dùng thể hiện đúng trạng thái chờ, thành công, thất bại hoặc cần đối soát.
- Có bằng chứng kiểm thử tải và lỗi; chi phí broker/consumer/observability đã được tính.

## 15. Checklist Well-Architected trước khi chốt giao tiếp

- [ ] Mỗi luồng có yêu cầu nghiệp vụ và kết quả được định nghĩa rõ.
- [ ] Đồng bộ chỉ dùng ở nơi bên gọi thực sự cần kết quả trong cùng tương tác; timeout nằm trong ngân sách latency.
- [ ] Công việc bất đồng bộ có trạng thái, deadline, owner và cách thông báo kết quả.
- [ ] Command, query và event được phân biệt về ngữ nghĩa.
- [ ] Transaction giữa các service có chiến lược rõ (local transaction, Saga, outbox/inbox hoặc đối soát).
- [ ] API write/message consumer có idempotency, xử lý lặp và quy tắc deduplication.
- [ ] Ordering/partition/version được xác định theo entity khi nghiệp vụ yêu cầu.
- [ ] Retry hữu hạn, exponential backoff/jitter, timeout, circuit breaker và DLQ có runbook.
- [ ] Queue có giới hạn, cảnh báo backlog/oldest age và phương án khi consumer chậm.
- [ ] Schema evolution tương thích với consumer cũ và message còn trong retention.
- [ ] TLS, workload identity, IAM publish/consume, quyền đọc DLQ và bảo vệ dữ liệu được xác định.
- [ ] Có correlation ID, trace/log/metric xuyên cả request và event.
- [ ] Đã tính chi phí broker, retention, message size, retry, compute và truyền dữ liệu.
- [ ] Đã kiểm thử dependency chậm/mất kết nối, broker unavailable, consumer crash và replay.
- [ ] ADR ghi các đánh đổi về reliability, security, performance, cost và operations.

**Điểm cốt lõi:** đồng bộ phù hợp khi nghiệp vụ cần phản hồi trực tiếp và các phụ thuộc có thể đáp ứng ngân sách thời gian; bất đồng bộ phù hợp khi công việc có thể hoàn tất sau, cần tách coupling hoặc hấp thụ burst. Kiến trúc tốt thường **kết hợp cả hai theo từng luồng**, đồng thời thiết kế trạng thái, idempotency, transaction, quan sát và phục hồi để hệ thống xử lý đúng ngay cả khi mạng hoặc dependency không hoàn hảo.
