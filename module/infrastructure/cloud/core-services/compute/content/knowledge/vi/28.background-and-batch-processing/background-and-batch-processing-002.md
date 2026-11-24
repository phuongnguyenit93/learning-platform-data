# Hàng đợi công việc và cơ chế điều phối worker

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Mô tả vai trò của producer, queue, broker, dispatcher và worker trong kiến trúc xử lý nền.
- Chọn kiểu hàng đợi và cơ chế phân phối phù hợp với yêu cầu về độ bền, thứ tự, thông lượng và độ trễ.
- Thiết kế vòng đời thông điệp gồm nhận, xử lý, xác nhận, retry và chuyển vào dead-letter queue.
- Xây dựng worker có khả năng xử lý lặp an toàn, giới hạn concurrency và dừng có kiểm soát.
- Điều phối worker trên Kubernetes hoặc dịch vụ container, mở rộng theo backlog và bảo vệ các dịch vụ phụ thuộc.
- Theo dõi và kiểm chứng độ tin cậy, thông lượng, độ trễ và chi phí của hệ thống.

## 1. Vì sao cần hàng đợi công việc?

Một yêu cầu trực tuyến thường cần phản hồi nhanh. Tuy nhiên, nhiều thao tác phía sau có thể mất vài giây hoặc vài phút, chẳng hạn tạo hóa đơn, gửi email, chuyển mã video, tạo báo cáo, đồng bộ dữ liệu hoặc xử lý ảnh. Nếu API thực hiện toàn bộ công việc trước khi trả lời, thời gian phản hồi sẽ phụ thuộc vào tốc độ của tất cả dịch vụ liên quan. Khi một dịch vụ chậm, số request đang chờ tăng lên và có thể làm cạn thread, connection hoặc bộ nhớ.

Hàng đợi công việc (work queue) tách việc tiếp nhận yêu cầu khỏi việc thực hiện công việc. API xác thực yêu cầu, ghi một thông điệp vào broker rồi trả về mã công việc. Worker lấy thông điệp từ queue và xử lý độc lập. API có thể trả trạng thái accepted hoặc queued; ứng dụng cung cấp endpoint hoặc trang trạng thái để người dùng tra cứu kết quả khi hoàn tất.

Kiến trúc này tạo ra một vùng đệm giữa tốc độ tạo công việc và tốc độ xử lý. Khi có đột biến, queue giữ công việc chờ worker thay vì buộc API phải giữ kết nối trong suốt quá trình xử lý. Queue không làm công việc biến mất: nếu tốc độ đến lâu dài lớn hơn tốc độ xử lý, backlog sẽ tiếp tục tăng. Cần có capacity, giới hạn tải và cảnh báo phù hợp.

Ví dụ, một cửa hàng trực tuyến nhận 500 yêu cầu tạo hóa đơn trong một phút. API có thể ghi 500 công việc vào queue trong thời gian ngắn. Nhóm worker xử lý dần, gọi dịch vụ hóa đơn và lưu kết quả. Nếu dịch vụ hóa đơn chậm, queue hấp thụ một phần biến động, còn API vẫn trả lời nhanh sau khi thông điệp được lưu thành công.

## 2. Các thành phần và luồng xử lý

Một hệ thống xử lý nền thường có các thành phần:

- **Producer:** tạo công việc và gửi thông điệp. Có thể là API, ứng dụng, lịch chạy hoặc một worker khác.
- **Queue/broker:** lưu thông điệp, quản lý việc phân phối, xác nhận, retry hoặc thời gian lưu.
- **Consumer/worker:** nhận thông điệp, thực thi logic nghiệp vụ và ghi kết quả.
- **Dispatcher hoặc scheduler:** chọn worker, queue, partition hoặc thời điểm thực hiện theo chính sách điều phối. Một số broker thực hiện phần lớn việc phân phối nên không cần một dispatcher riêng.
- **Kho trạng thái công việc:** lưu trạng thái nghiệp vụ như queued, running, succeeded hoặc failed để API và người vận hành tra cứu.
- **Dead-letter queue (DLQ):** giữ thông điệp không thể xử lý sau số lần thử hoặc điều kiện được quy định.
- **Hệ thống quan sát:** thu thập độ dài queue, tuổi thông điệp, thời gian xử lý, lỗi, retry và số worker sẵn sàng.

Luồng cơ bản:

1. Producer kiểm tra quyền, dữ liệu đầu vào và điều kiện nghiệp vụ.
2. Producer tạo mã công việc duy nhất và gửi thông điệp đến queue.
3. Broker xác nhận thông điệp đã được nhận theo mức bảo đảm lưu trữ được cấu hình.
4. Worker nhận thông điệp và chuyển công việc sang trạng thái đang xử lý.
5. Worker thực thi, lưu kết quả và cập nhật trạng thái công việc.
6. Worker xác nhận (ack) thông điệp sau khi xử lý thành công.
7. Nếu xử lý thất bại, worker áp dụng retry hoặc chuyển thông điệp vào DLQ theo chính sách.

Cần phân biệt xác nhận gửi từ producer với xác nhận xử lý từ worker. Producer nhận được xác nhận gửi có nghĩa broker đã nhận thông điệp theo hợp đồng của broker; điều đó không có nghĩa công việc đã hoàn tất. Trạng thái hoàn tất cần được ghi nhận riêng.

### 2.1. Thiết kế thông điệp công việc

Thông điệp nên mang đủ thông tin để worker hiểu cần làm gì, nhưng tránh nhúng dữ liệu lớn hoặc bí mật không cần thiết.

Một cấu trúc minh họa:

    {
      "messageId": "msg-7f21",
      "jobId": "invoice-2026-00421",
      "jobType": "generate-invoice",
      "schemaVersion": 1,
      "createdAt": "2026-11-22T10:30:00Z",
      "correlationId": "order-00421",
      "attempt": 0,
      "payload": {
        "orderId": "order-00421",
        "customerId": "customer-018"
      }
    }

Các trường thường hữu ích:

- **messageId:** định danh duy nhất của một thông điệp để theo dõi và phát hiện trùng.
- **jobId:** định danh nghiệp vụ, ổn định qua các lần retry.
- **jobType:** loại công việc để worker chọn handler.
- **schemaVersion:** phiên bản cấu trúc payload để triển khai tương thích.
- **createdAt:** thời điểm tạo để đo tuổi thông điệp.
- **correlationId/traceId:** liên kết log và trace giữa API, broker và worker.
- **attempt:** số lần thử, nếu broker hoặc ứng dụng quản lý trường này.
- **payload:** dữ liệu tối thiểu hoặc tham chiếu đến dữ liệu được lưu ở kho bền vững.

Không đưa mật khẩu, access token, khóa riêng hoặc dữ liệu nhạy cảm vào queue nếu không có nhu cầu rõ ràng. Nếu payload lớn, hãy lưu đối tượng ở object storage hoặc cơ sở dữ liệu, sau đó gửi tham chiếu cùng checksum và quyền truy cập có thời hạn. Worker phải kiểm tra quyền truy cập và tính hợp lệ của dữ liệu được tham chiếu.

## 3. Chọn queue, pub/sub và cơ chế phân phối

Các mô hình messaging có mục tiêu khác nhau. Chọn mô hình dựa trên cách công việc được tiêu thụ, yêu cầu lưu trữ và thứ tự xử lý.

| Mô hình | Cách hoạt động | Trường hợp phù hợp |
|---|---|---|
| Work queue / competing consumers | Nhiều worker cùng lấy công việc từ một queue; mỗi thông điệp thường được một worker xử lý thành công | Gửi email, tạo hóa đơn, xử lý ảnh |
| Pub/sub | Một sự kiện được phát đến nhiều subscription độc lập; mỗi nhóm subscriber có luồng tiêu thụ riêng | Khi một sự kiện cần cập nhật kho dữ liệu, analytics và notification |
| Partitioned queue / stream | Thông điệp được chia theo partition hoặc key; thứ tự được bảo toàn trong phạm vi partition theo cam kết của nền tảng | Xử lý sự kiện theo tài khoản, đơn hàng hoặc thiết bị |
| Delayed queue / scheduled delivery | Thông điệp chỉ sẵn sàng sau một thời điểm hoặc khoảng trễ | Nhắc thanh toán, retry sau, tác vụ theo lịch |
| Priority queue | Công việc được chọn theo mức ưu tiên | Hỗ trợ tác vụ khẩn cấp hoặc phân tầng SLA |

Trong work queue, nhiều worker thường cạnh tranh để nhận công việc. Khi một worker lấy thông điệp, broker đánh dấu thông điệp đang được xử lý hoặc cấp một lease/visibility timeout. Nếu worker xác nhận thành công, thông điệp được loại khỏi queue. Nếu worker chết hoặc hết lease mà chưa xác nhận, broker có thể đưa thông điệp trở lại để worker khác xử lý.

Trong pub/sub, một sự kiện có thể được giao đến nhiều subscription. Không nên dùng một queue chung nếu mọi nhóm xử lý đều phải nhận cùng sự kiện, vì competing consumers sẽ chia công việc cho nhau thay vì phát bản sao đến tất cả nhóm.

Với partitioned queue, key quyết định nơi thông điệp được ghi. Nếu cần thứ tự theo đơn hàng, dùng orderId làm partition key để các sự kiện của cùng đơn hàng đi theo một luồng. Thứ tự toàn cục thường làm giảm khả năng song song và không được mọi broker hỗ trợ. Cần nêu rõ phạm vi thứ tự cần bảo đảm: toàn queue, từng partition hay từng thực thể nghiệp vụ.

### 3.1. Chọn broker theo yêu cầu

Một số dịch vụ thường gặp:

| Dịch vụ | Kiểu sử dụng phổ biến | Điểm cần xem xét |
|---|---|---|
| RabbitMQ | Queue, routing key, exchange, acknowledgement và consumer | Routing linh hoạt; cần vận hành broker, quorum/replication và dung lượng queue |
| Amazon SQS | Queue được quản lý, Standard hoặc FIFO, visibility timeout và DLQ | Ít phải vận hành broker; xem giới hạn throughput, retention, FIFO và phí request |
| Google Cloud Pub/Sub | Pub/sub, subscription và acknowledgement deadline | Phù hợp phân phối sự kiện; thiết kế ordering key và retry theo subscription |
| Azure Service Bus | Queue/topic, subscription, lock duration, dead-lettering | Hỗ trợ routing và nghiệp vụ messaging; cần cấu hình lock, duplicate detection và DLQ |

Không có broker tốt nhất cho mọi workload. Đánh giá ít nhất: durability, retention, thứ tự, throughput, kích thước message, khả năng retry, DLQ, bảo mật, tích hợp quan sát, quota, vùng sẵn sàng và chi phí.

## 4. Vòng đời thông điệp: nhận, xử lý và xác nhận

Thông điệp chỉ nên bị xóa hoặc đánh dấu hoàn tất sau khi kết quả xử lý đã được ghi bền vững. Nếu worker ack trước rồi mới ghi dữ liệu, một sự cố giữa hai bước có thể làm mất công việc. Nếu worker ghi dữ liệu xong nhưng chết trước khi ack, broker có thể giao lại thông điệp và công việc có thể được thực hiện lần thứ hai.

Đây là lý do hệ thống queue thường cung cấp giao nhận ít nhất một lần (at-least-once). Worker phải giả định cùng một thông điệp có thể xuất hiện nhiều lần.

### 4.1. At-most-once, at-least-once và exactly-once

| Cơ chế | Đặc điểm | Rủi ro |
|---|---|---|
| At-most-once | Thông điệp được giao tối đa một lần theo cơ chế của hệ thống; có thể mất nếu lỗi xảy ra sau khi lấy | Có thể mất công việc |
| At-least-once | Broker giao lại khi không nhận ack hợp lệ | Có thể xử lý trùng |
| Exactly-once | Phạm vi và bảo đảm phụ thuộc broker, transaction và tích hợp với hệ thống đích | Không tự bảo đảm tác dụng phụ bên ngoài chỉ xảy ra một lần |

Trong nhiều hệ thống nghiệp vụ, at-least-once kết hợp xử lý idempotent là lựa chọn thực tế. Một số nền tảng hỗ trợ exactly-once trong phạm vi hẹp, chẳng hạn xử lý trong transaction của broker hoặc trong một pipeline được hỗ trợ. Khi ghi vào database, gọi API thanh toán hoặc gửi email, vẫn cần kiểm soát trùng ở tầng nghiệp vụ.

### 4.2. Idempotency và chống xử lý trùng

Một thao tác idempotent có thể được thực hiện lặp lại mà kết quả nghiệp vụ cuối cùng không thay đổi ngoài lần đầu. Ví dụ, tạo hóa đơn với khóa idempotency là jobId. Trước khi tạo, worker kiểm tra bảng xử lý công việc hoặc dùng unique constraint để bảo đảm jobId chỉ tạo một hóa đơn.

Một quy trình đơn giản:

1. Nhận thông điệp có jobId.
2. Bắt đầu transaction trong database.
3. Ghi jobId vào bảng processed_jobs với unique constraint.
4. Nếu jobId đã tồn tại ở trạng thái hoàn tất, bỏ qua tác dụng phụ và ack thông điệp.
5. Nếu chưa tồn tại, thực hiện cập nhật nghiệp vụ và lưu trạng thái hoàn tất trong cùng transaction khi có thể.
6. Commit transaction rồi ack thông điệp.

Nếu tác dụng phụ nằm ngoài transaction database, chẳng hạn gọi cổng thanh toán hoặc gửi email, dùng idempotency key mà dịch vụ đích hỗ trợ hoặc một quy trình saga/outbox/inbox thích hợp. Không giả định transaction cục bộ có thể rollback một request HTTP đã được dịch vụ khác thực hiện.

### 4.3. Transactional outbox

Một lỗi phổ biến xảy ra khi API ghi đơn hàng vào database thành công nhưng gửi message thất bại, hoặc message được gửi thành công nhưng transaction database rollback. Khi đó dữ liệu nghiệp vụ và queue không nhất quán.

Transactional outbox giải quyết bằng cách ghi bản ghi đơn hàng và bản ghi outbox trong cùng transaction database. Một publisher đọc outbox và gửi message đến broker; sau khi broker xác nhận, publisher đánh dấu bản ghi đã gửi. Publisher có thể gửi lại nếu bị dừng giữa chừng, vì vậy consumer vẫn cần idempotency.

Mẫu này giúp tránh khoảng trống giữa commit dữ liệu nghiệp vụ và phát thông điệp. Nó không loại bỏ mọi lỗi phân tán, nhưng làm cho việc phát message có thể retry và quan sát được.

## 5. Lease, visibility timeout và thời gian xử lý

Nhiều broker không xóa message ngay khi worker nhận. Thay vào đó, broker cấp một khoảng thời gian xử lý (visibility timeout hoặc lock/lease duration). Trong thời gian đó, message tạm thời không được giao cho worker khác. Worker phải ack trước khi lease hết hạn.

Nếu thời gian xử lý dài hơn lease, message có thể được giao lại trong khi worker đầu tiên vẫn đang chạy. Hai worker có thể cùng thực hiện một công việc. Có ba cách xử lý:

- Đặt lease dài hơn thời gian xử lý tối đa đã đo, có tính đến biến động.
- Gia hạn lease/visibility timeout định kỳ khi worker vẫn đang tiến triển.
- Thiết kế idempotent và dùng khóa nghiệp vụ để ngăn hai worker đồng thời ghi cùng kết quả.

Đặt lease quá dài làm chậm việc khôi phục message khi worker chết. Đặt quá ngắn làm tăng giao lại trùng. Hãy đo p95/p99 thời gian xử lý, đặt thời gian ban đầu có khoảng dự phòng và theo dõi số lần lease hết hạn.

Với RabbitMQ, consumer acknowledgement và cơ chế prefetch ảnh hưởng số message đang được giao cho một consumer. Với SQS, visibility timeout và ChangeMessageVisibility điều khiển khoảng message bị ẩn. Với Pub/Sub, acknowledgement deadline có thể được gia hạn trong khi xử lý. Tên API khác nhau nhưng nguyên tắc chung là giới hạn thời gian worker giữ quyền xử lý và cho phép khôi phục khi worker mất khả năng hoạt động.

## 6. Retry, backoff và dead-letter queue

Không phải lỗi nào cũng cần retry. Cần phân biệt:

- **Lỗi tạm thời:** timeout, lỗi mạng, giới hạn tốc độ hoặc dịch vụ phụ thuộc tạm thời không sẵn sàng.
- **Lỗi dữ liệu/logic:** payload sai schema, thiếu trường bắt buộc hoặc vi phạm quy tắc nghiệp vụ.
- **Lỗi hạ tầng:** worker bị dừng, node mất kết nối hoặc broker tạm thời không truy cập được.

Lỗi tạm thời có thể retry. Lỗi dữ liệu không thể khắc phục bằng cách thử lại liên tục; nên chuyển sang DLQ hoặc hàng chờ cách ly để kiểm tra. Nếu mọi worker liên tục retry một message lỗi, message đó có thể chiếm capacity và làm queue bị nghẽn.

### 6.1. Exponential backoff và jitter

Một chính sách retry thường tăng thời gian chờ sau mỗi lần thất bại:

    delay = min(maxDelay, baseDelay * 2^attempt)

Có thể thêm jitter ngẫu nhiên để các worker không đồng loạt retry cùng lúc:

    actualDelay = random(0, delay)

Ví dụ minh họa với baseDelay 2 giây và maxDelay 60 giây:

| Lần thử tiếp theo | Delay tối đa trước jitter |
|---|---:|
| 1 | 2 giây |
| 2 | 4 giây |
| 3 | 8 giây |
| 4 | 16 giây |
| 5 | 32 giây |
| 6 trở đi | 60 giây |

Cần đặt max attempts hoặc giới hạn thời gian retry. Nếu không, một message độc hại hoặc dữ liệu không hợp lệ có thể tồn tại vô hạn và tiêu thụ tài nguyên. Với lỗi rate limit, tôn trọng Retry-After nếu dịch vụ phụ thuộc cung cấp.

### 6.2. Dead-letter queue

DLQ nhận thông điệp đã vượt số lần thử hoặc vi phạm điều kiện xử lý. DLQ cần giữ thông tin đủ để điều tra: messageId, jobId, loại lỗi, số lần thử, thời điểm lỗi cuối, correlationId và payload hoặc tham chiếu payload.

Quy trình vận hành DLQ:

1. Cảnh báo khi DLQ có message mới hoặc tốc độ tăng vượt ngưỡng.
2. Phân nhóm lỗi theo mã lỗi, jobType và phiên bản schema.
3. Xác định nguyên nhân: dữ liệu sai, lỗi code, dependency hoặc cấu hình.
4. Sửa nguyên nhân và xác minh trên một message mẫu trong môi trường kiểm thử.
5. Redrive có giới hạn về tốc độ và số lượng; theo dõi duplicate và downstream load.
6. Giữ audit trail để biết message nào đã được phát lại và kết quả cuối cùng.

Không tự động đưa toàn bộ DLQ trở lại queue chính liên tục. Nếu lỗi chưa được sửa, hệ thống chỉ tạo vòng lặp retry và làm tăng tải. Có thể cần queue cách ly theo loại lỗi hoặc quy trình xử lý thủ công có phê duyệt cho các công việc nhạy cảm.

## 7. Điều phối worker và giới hạn tải

Worker là tiến trình thực thi công việc. Một worker có thể xử lý một message tại một thời điểm hoặc nhiều message song song. Số worker và concurrency quyết định thông lượng, nhưng tăng concurrency không phải lúc nào cũng tăng năng lực thực tế.

### 7.1. Competing consumers

Nhiều worker cùng đọc một queue tạo mô hình competing consumers. Broker phân phối message cho worker sẵn sàng theo cơ chế của nó. Khi số worker tăng, thông lượng có thể tăng gần tuyến tính trong giai đoạn đầu nếu công việc độc lập và downstream còn capacity.

Tuy nhiên, nếu tất cả worker cùng gọi một database có giới hạn kết nối, thêm worker có thể làm database quá tải. Cần giới hạn tổng số kết nối, pool mỗi worker, concurrency và tốc độ gọi API phụ thuộc.

### 7.2. Concurrency và prefetch

Concurrency là số công việc worker xử lý cùng lúc. Prefetch là số message broker có thể giao trước cho consumer chưa ack. Hai thông số liên quan nhưng không giống nhau.

- Concurrency quá thấp làm CPU hoặc worker nhàn rỗi khi công việc có thể chạy song song.
- Concurrency quá cao làm tăng bộ nhớ, connection, contention và số công việc bị ảnh hưởng khi worker chết.
- Prefetch quá lớn có thể khiến một worker giữ nhiều message trong khi worker khác rảnh, làm giảm tính công bằng.
- Prefetch quá nhỏ có thể làm giảm throughput do worker phải chờ broker cấp message liên tục.

Bắt đầu với concurrency nhỏ, đo throughput, latency, memory, connection pool và lỗi rồi tăng dần. Đặt prefetch gần với số công việc worker thực sự có thể xử lý đồng thời, đặc biệt khi thời gian xử lý giữa các message khác nhau nhiều.

### 7.3. Ưu tiên và công bằng

Nếu có nhiều loại công việc, có thể dùng queue riêng hoặc priority. Ví dụ, tác vụ xác nhận thanh toán có SLA ngắn hơn tác vụ tạo báo cáo. Một queue duy nhất với công việc nặng có thể khiến tác vụ khẩn cấp phải chờ lâu.

Tách queue theo loại công việc giúp đặt worker pool, retry và autoscaling riêng. Tuy nhiên, quá nhiều queue làm tăng độ phức tạp vận hành. Có thể gom nhóm theo SLA và đặc tính tài nguyên thay vì tạo queue cho từng loại message.

Với hệ thống nhiều tenant, cần giới hạn quota theo tenant hoặc áp dụng weighted fair scheduling. Nếu một khách hàng gửi quá nhiều công việc, họ không nên chiếm toàn bộ worker và làm các khách hàng khác bị đói tài nguyên.

### 7.4. Backpressure và giới hạn producer

Queue chỉ là vùng đệm hữu hạn về mặt vận hành. Nếu producer gửi nhanh hơn khả năng xử lý trong thời gian dài, backlog tăng, thời gian chờ tăng và chi phí lưu trữ tăng. Khi gần đạt ngưỡng, hệ thống cần phản hồi ngược:

- Giới hạn tốc độ nhận yêu cầu hoặc trả về trạng thái thử lại sau.
- Áp dụng quota theo tenant, jobType hoặc API key.
- Từ chối công việc không thiết yếu khi queue vượt ngưỡng.
- Tạm dừng producer hoặc giảm tốc độ phát sự kiện.
- Tăng worker nếu downstream còn capacity.
- Tách queue ưu tiên cao để công việc quan trọng không bị backlog thông thường chặn.

Cần đặt giới hạn message size, retention, số message chờ và tuổi tối đa. Đối với công việc có thời hạn, message quá cũ có thể không còn giá trị; cần chính sách hết hạn và xử lý trạng thái tương ứng.

## 8. Ước lượng thông lượng và số worker

Gọi:

- λ là tốc độ message đến, tính bằng công việc mỗi giây.
- μ là tốc độ một worker xử lý, tính bằng công việc mỗi giây.
- N là số worker hoạt động.
- ρ là mức sử dụng mục tiêu, nhỏ hơn 1 để giữ dự phòng.

Để xử lý tải ổn định mà không tạo backlog dài hạn, năng lực xử lý cần lớn hơn tốc độ đến:

    N × μ × ρ >= λ

Số worker tham khảo:

    N = ceil(λ / (μ × ρ))

Ví dụ, queue nhận trung bình 60 công việc mỗi giây; một worker xử lý 5 công việc mỗi giây; mức sử dụng mục tiêu là 75%:

    N = ceil(60 / (5 × 0.75))
    N = ceil(16)
    N = 16 workers

Đây là ước lượng cho tải ổn định. Nếu cần xóa backlog hiện có trong một khoảng thời gian, phải bổ sung thông lượng để xử lý cả message mới lẫn message tồn đọng.

Ví dụ có 12.000 message đang chờ, cần xóa backlog trong 10 phút. Tốc độ xử lý bổ sung cần đạt 20 message mỗi giây, ngoài tốc độ đến mới. Nếu tốc độ đến là 60 message mỗi giây, worker pool cần năng lực ít nhất 80 message mỗi giây trước khi tính headroom.

Không chỉ theo dõi queue depth. Hai queue có cùng 10.000 message có thể có thời gian chờ rất khác nếu thời gian xử lý trung bình khác nhau. Theo dõi tuổi message lâu nhất, thời gian chờ trước khi worker nhận, thời gian xử lý và tốc độ hoàn tất để đánh giá SLA.

## 9. Triển khai worker trên Kubernetes

Với Kubernetes, worker thường chạy dưới dạng Deployment nếu cần duy trì một pool liên tục, hoặc Job/CronJob nếu mỗi lần chạy là một tác vụ hữu hạn.

- **Deployment:** phù hợp với worker liên tục poll queue và xử lý message.
- **Job:** phù hợp với một lần chạy có điểm kết thúc, ví dụ nhập một tập dữ liệu.
- **CronJob:** tạo Job theo lịch, ví dụ tổng hợp báo cáo mỗi đêm.
- **HPA:** điều chỉnh số Pod theo CPU, memory hoặc custom metric.
- **KEDA:** tích hợp metric từ queue và event source để scale worker, kể cả scale về 0 nếu cấu hình cho phép.

Ví dụ Deployment worker liên tục:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: invoice-worker
    spec:
      replicas: 3
      selector:
        matchLabels:
          app: invoice-worker
      template:
        metadata:
          labels:
            app: invoice-worker
        spec:
          terminationGracePeriodSeconds: 60
          containers:
            - name: worker
              image: registry.example.com/invoice-worker:v1
              env:
                - name: QUEUE_NAME
                  value: invoices
                - name: BROKER_URL
                  valueFrom:
                    secretKeyRef:
                      name: broker-credentials
                      key: url
              resources:
                requests:
                  cpu: 500m
                  memory: 512Mi
                limits:
                  cpu: "1"
                  memory: 1Gi
              readinessProbe:
                exec:
                  command: ["/app/worker", "ready"]
                periodSeconds: 10
              livenessProbe:
                exec:
                  command: ["/app/worker", "health"]
                periodSeconds: 20
                failureThreshold: 3

Readiness probe cho worker nên phản ánh khả năng nhận công việc, chẳng hạn kết nối broker và trạng thái drain. Không dùng liveness probe để kiểm tra mọi dependency bên ngoài nếu lỗi tạm thời khiến container bị restart liên tục. Worker cần xử lý SIGTERM: ngừng nhận message mới, hoàn tất hoặc nhả message đang xử lý và thoát trong thời gian grace period.

Bảo mật thông tin kết nối bằng Secret hoặc hệ thống quản lý bí mật của nền tảng. Trong production, cần cấu hình service account tối thiểu quyền, network policy, TLS, image đã quét và giới hạn tài nguyên phù hợp.

### 9.1. Co giãn worker theo queue với KEDA

KEDA có thể đọc metric của broker và tạo hoặc điều chỉnh HPA cho Deployment. Ví dụ dưới đây dùng RabbitMQ scaler với queue invoices, mục tiêu 25 message trên mỗi worker:

    apiVersion: keda.sh/v1alpha1
    kind: ScaledObject
    metadata:
      name: invoice-worker-scaler
    spec:
      scaleTargetRef:
        name: invoice-worker
      minReplicaCount: 1
      maxReplicaCount: 30
      pollingInterval: 15
      cooldownPeriod: 120
      triggers:
        - type: rabbitmq
          metadata:
            protocol: amqp
            queueName: invoices
            mode: QueueLength
            value: "25"
            hostFromEnv: BROKER_URL

Trong ví dụ, KEDA kiểm tra queue mỗi 15 giây, mục tiêu là 25 message trên mỗi replica và giới hạn worker từ 1 đến 30. Cần bảo đảm biến BROKER_URL được khai báo trong Pod template và lấy từ Secret; cấu hình scaler cụ thể phải khớp phiên bản KEDA và broker đang dùng.

Min replica bằng 1 giúp luôn có worker sẵn sàng, giảm cold start nhưng tốn tài nguyên khi queue rỗng. Nếu workload chấp nhận thời gian khởi động, có thể cấu hình minReplicaCount bằng 0. Khi scale từ 0, phải xác minh scaler vẫn đọc được queue và không có dependency khiến việc khởi động worker bị treo.

Các bước triển khai và quan sát:

    kubectl apply -f invoice-worker.yaml
    kubectl apply -f invoice-worker-scaledobject.yaml
    kubectl get deployment invoice-worker
    kubectl get scaledobject invoice-worker-scaler
    kubectl describe scaledobject invoice-worker-scaler
    kubectl get hpa
    kubectl get pods -l app=invoice-worker -w

Đưa message thử nghiệm vào queue và quan sát số Pod, queue depth, tốc độ hoàn tất, tuổi message lâu nhất và lỗi. Khi queue rỗng, kiểm tra scale in có diễn ra theo cooldown hay không. Nếu Pod Pending, kiểm tra resource request, node capacity, taint/toleration và giới hạn node pool.

### 9.2. Điều phối Job hữu hạn

Với tác vụ chạy một lần, Kubernetes Job phù hợp hơn một worker luôn poll queue. Ví dụ, một Job có thể xử lý một tập dữ liệu đã được xác định, kết thúc khi hoàn thành và được Kubernetes retry theo backoffLimit khi Pod thất bại.

    apiVersion: batch/v1
    kind: Job
    metadata:
      name: reconcile-orders
    spec:
      backoffLimit: 3
      activeDeadlineSeconds: 1800
      ttlSecondsAfterFinished: 3600
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: reconcile
              image: registry.example.com/order-reconcile:v1
              args: ["--date", "2026-11-21"]
              resources:
                requests:
                  cpu: 1
                  memory: 1Gi

Job controller quản lý Pod của Job; Job không thay thế broker nếu cần tiếp nhận và lưu một lượng lớn công việc độc lập. Nếu mỗi message tạo một Job, cần cân nhắc overhead tạo Pod và API server. Với số lượng message lớn, một pool worker thường hiệu quả hơn.

## 10. Lịch chạy và điều phối công việc

Một số công việc cần chạy theo lịch thay vì ngay khi được tạo. Có thể dùng scheduler bên ngoài hoặc Kubernetes CronJob để tạo Job theo chu kỳ.

Các chính sách lịch quan trọng:

- **Concurrency policy:** cho phép, bỏ qua hoặc thay thế lần chạy mới nếu lần trước chưa hoàn tất.
- **Deadline:** bỏ qua lần chạy nếu quá thời điểm bắt đầu cho phép.
- **Retry:** giới hạn số lần chạy lại khi Job thất bại.
- **Idempotency:** bảo đảm chạy lại cùng kỳ không tạo dữ liệu trùng.
- **Catch-up:** quyết định có chạy bù những kỳ bị bỏ lỡ khi hệ thống gián đoạn hay không.
- **Time zone:** xác định rõ múi giờ và hành vi khi chuyển giờ mùa hè ở khu vực có áp dụng.

Ví dụ CronJob chạy tổng hợp mỗi ngày:

    apiVersion: batch/v1
    kind: CronJob
    metadata:
      name: daily-report
    spec:
      schedule: "0 2 * * *"
      timeZone: "Asia/Ho_Chi_Minh"
      concurrencyPolicy: Forbid
      startingDeadlineSeconds: 900
      jobTemplate:
        spec:
          backoffLimit: 2
          template:
            spec:
              restartPolicy: Never
              containers:
                - name: report
                  image: registry.example.com/report-worker:v1
                  args: ["--period", "previous-day"]

Với CronJob, chính sách **Forbid** bỏ qua lần chạy mới nếu Job trước đó vẫn đang hoạt động. Đây là lựa chọn phù hợp khi không muốn hai lần tổng hợp cùng ghi vào một tập dữ liệu. Nếu cần chạy bù, phải thiết kế quy trình catch-up rõ ràng; không giả định CronJob sẽ tạo mọi lần chạy đã bỏ lỡ trong mọi tình huống.

## 11. Quan sát, bảo mật và vận hành

Một queue có thể hoạt động nhưng dịch vụ vẫn vi phạm SLA nếu message nằm chờ quá lâu. Theo dõi cần bao gồm cả broker, worker và kết quả nghiệp vụ.

| Nhóm | Metric | Câu hỏi vận hành |
|---|---|---|
| Queue | Depth, tuổi message lâu nhất, số message sẵn sàng và đang in-flight | Backlog có tăng liên tục? Công việc có quá hạn? |
| Throughput | Message đến/giây, xử lý thành công/giây, ack/giây | Worker có theo kịp tốc độ đến? |
| Worker | Replica sẵn sàng, CPU, memory, restart, concurrency | Có đủ worker? Có bị giới hạn tài nguyên? |
| Latency | Thời gian chờ trong queue, thời gian xử lý, end-to-end duration | SLA bị ảnh hưởng ở bước nào? |
| Reliability | Retry, redelivery, timeout, DLQ, lỗi theo jobType | Có message lỗi lặp hoặc poison message? |
| Dependency | Connection pool, API error, rate limit, database latency | Worker có làm quá tải dịch vụ phụ thuộc? |
| Cost | Worker-hours, request broker, storage/retention, egress | Chi phí tăng do backlog hoặc retry? |

Bảo vệ queue bằng xác thực, phân quyền producer/consumer theo từng queue hoặc topic, mã hóa khi truyền và khi lưu nếu nền tảng hỗ trợ. Giới hạn quyền purge, delete, redrive và thay đổi retention. Dùng audit log cho thao tác vận hành DLQ và tránh ghi payload nhạy cảm vào log.

Nên thiết lập cảnh báo theo SLA thay vì chỉ theo một ngưỡng queue depth cố định. Ví dụ, cảnh báo khi tuổi message lâu nhất vượt 5 phút, backlog tăng liên tục trong 10 phút hoặc tỷ lệ DLQ vượt ngưỡng. Ngưỡng thực tế phải lấy từ thời hạn xử lý của nghiệp vụ.

## 12. Quy trình kiểm chứng hệ thống worker

Thực hiện trong môi trường kiểm thử hoặc staging:

1. **Kiểm tra gửi:** gửi message hợp lệ và xác nhận producer nhận kết quả publish thành công.
2. **Kiểm tra xử lý:** xác nhận worker nhận message, cập nhật trạng thái và ack sau khi lưu kết quả.
3. **Kiểm tra xử lý trùng:** gửi lại cùng jobId hoặc mô phỏng worker chết sau commit nhưng trước ack; xác nhận không tạo tác dụng phụ trùng.
4. **Kiểm tra retry:** làm dependency trả timeout có kiểm soát; xác nhận backoff, số lần thử và trạng thái message.
5. **Kiểm tra DLQ:** gửi payload không hợp lệ; xác nhận message được cách ly sau ngưỡng retry và có đủ metadata điều tra.
6. **Kiểm tra lease:** cho một job chạy lâu hơn lease ban đầu; xác nhận gia hạn hoặc xử lý trùng an toàn.
7. **Kiểm tra shutdown:** gửi SIGTERM cho worker đang xử lý; xác nhận message không mất và Pod thoát trong grace period.
8. **Kiểm tra tải:** tăng tốc độ publish, đo throughput, queue age, p95/p99 processing latency và downstream load.
9. **Kiểm tra backpressure:** đưa queue gần giới hạn và xác nhận producer bị giới hạn hoặc nhận phản hồi phù hợp.
10. **Kiểm tra phục hồi:** khởi động lại broker/worker trong môi trường thử nghiệm theo kịch bản; xác nhận message bền vững và trạng thái công việc nhất quán.

Kết quả cần được so sánh với mục tiêu cụ thể: thời gian chờ tối đa, throughput, tỷ lệ lỗi, tỷ lệ xử lý trùng, thời gian phục hồi và ngân sách.

## 13. Tình huống thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Queue tăng liên tục | Tốc độ đến cao hơn năng lực xử lý hoặc worker lỗi | So sánh λ, throughput, replica và dependency latency |
| Message được xử lý nhiều lần | Worker chết trước ack, lease hết hạn hoặc redelivery | Kiểm tra ack, visibility timeout, idempotency và log jobId |
| Message nằm in-flight quá lâu | Worker treo, lease dài hoặc không gia hạn đúng | Kiểm tra heartbeat, worker health và thời gian xử lý |
| DLQ tăng nhanh | Payload sai, lỗi code hoặc dependency lỗi kéo dài | Phân loại lỗi, dừng redrive tự động và xử lý nguyên nhân |
| Worker CPU thấp nhưng queue vẫn lớn | Worker chờ I/O, concurrency thấp hoặc downstream giới hạn | Đo thời gian chờ, connection pool và số công việc đồng thời |
| Tăng worker làm database quá tải | Mỗi worker mở quá nhiều connection hoặc query đồng thời | Giới hạn pool, concurrency và tốc độ gọi database |
| Công việc ưu tiên thấp không được xử lý | Queue ưu tiên cao chiếm toàn bộ worker | Tách pool, đặt quota hoặc weighted fair scheduling |
| Job lịch chạy trùng | Lần trước chưa kết thúc hoặc lịch catch-up | Kiểm tra concurrencyPolicy, khóa kỳ chạy và idempotency |
| Producer gửi thành công nhưng không có kết quả | Publish chỉ xác nhận broker nhận message; worker chưa xử lý | Kiểm tra queue, consumer, trạng thái job và DLQ |

## 14. Checklist trước khi đưa vào production

- [ ] Chọn work queue, pub/sub, partitioned queue hoặc scheduled queue theo yêu cầu nghiệp vụ.
- [ ] Định nghĩa schema thông điệp, messageId, jobId, version và correlationId.
- [ ] Cấu hình durability, retention, quota, giới hạn message size và quyền truy cập broker.
- [ ] Chọn delivery semantics và thiết kế consumer idempotent.
- [ ] Chỉ ack sau khi kết quả đã được ghi bền vững.
- [ ] Đặt visibility timeout/lease và cơ chế gia hạn cho job dài.
- [ ] Cấu hình retry, exponential backoff, jitter, max attempts và DLQ.
- [ ] Giới hạn concurrency, prefetch, connection pool và tốc độ gọi downstream.
- [ ] Có backpressure, quota và chính sách ưu tiên/công bằng giữa tenant hoặc job type.
- [ ] Triển khai graceful shutdown và xử lý message chưa ack khi worker dừng.
- [ ] Chọn Deployment, Job hoặc CronJob theo vòng đời công việc.
- [ ] Theo dõi queue age, depth, throughput, processing latency, retry và DLQ.
- [ ] Kiểm thử duplicate, worker crash, lease expiry, backlog spike và broker recovery.
- [ ] Đặt cảnh báo dựa trên SLA và đối chiếu chi phí vận hành.

## Kết luận

Hàng đợi tách việc tiếp nhận khỏi việc thực thi và giúp hệ thống hấp thụ biến động tải. Độ tin cậy phụ thuộc vào cách lưu thông điệp, xác nhận sau khi ghi kết quả, xử lý trùng, retry và cách cô lập message lỗi. Điều phối worker cần cân bằng concurrency, prefetch, năng lực downstream, fairness và backpressure. Khi triển khai trên Kubernetes, chọn Deployment cho worker liên tục, Job/CronJob cho tác vụ hữu hạn hoặc theo lịch, và mở rộng theo metric phản ánh backlog cùng SLA. Hãy kiểm chứng cả trường hợp bình thường lẫn worker chết, broker chậm, message trùng và backlog tăng trước khi đưa hệ thống vào production.
