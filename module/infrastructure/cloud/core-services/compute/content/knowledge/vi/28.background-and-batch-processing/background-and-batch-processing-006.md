# Timeout, retry và phân loại lỗi có thể thử lại

Trong xử lý nền và theo lô, một tác vụ có thể chạy qua nhiều thành phần: scheduler, queue, worker, database, object storage và API bên ngoài. Một lần gọi dependency bị timeout không nhất thiết có nghĩa thao tác đã thất bại. Request có thể chưa tới đích, server có thể đã xử lý nhưng response bị mất, hoặc thao tác vẫn đang chạy sau khi client ngừng chờ. Nếu worker retry thiếu kiểm soát, một nghiệp vụ có thể bị thực hiện nhiều lần, dữ liệu bị ghi trùng hoặc tải tăng đột biến đúng lúc hệ thống đang gặp sự cố.

Thiết kế retry tốt bắt đầu bằng timeout có giới hạn, deadline xuyên suốt tác vụ và cách phân loại lỗi. Chỉ lỗi có khả năng tự hồi phục mới nên được retry; lỗi dữ liệu, quyền truy cập hoặc quy tắc nghiệp vụ thường cần sửa nguyên nhân hoặc đưa vào luồng xử lý riêng. Với tác vụ có side effect, retry phải đi cùng idempotency, deduplication hoặc transaction để tránh lặp tác động.

Bài học này thuộc chương **Xử lý nền và theo lô** của module **CLOUD_CORE_SERVICES_COMPUTE**. Module giúp người học tìm hiểu các mô hình năng lực tính toán trên đám mây, từ máy ảo, container đến serverless; cách chọn CPU, bộ nhớ, mạng và cấu hình bảo mật; triển khai ứng dụng, mở rộng tải, bảo đảm tính sẵn sàng và tối ưu chi phí vận hành. Trong phạm vi đó, timeout và retry quyết định cách worker sử dụng tài nguyên, phục hồi khi dependency gián đoạn và giữ tính đúng đắn của công việc khi phải chạy lại.

## 1. Timeout và retry giải quyết vấn đề gì?

### 1.1. Timeout là giới hạn thời gian chờ

Timeout quy định thời gian tối đa một thao tác được phép chờ trước khi caller dừng chờ hoặc hủy phần công việc mà nó kiểm soát được.

Timeout cần thiết vì:
- Dependency có thể ngừng phản hồi.
- Network packet có thể bị mất hoặc đường truyền bị gián đoạn.
- Worker có thể giữ thread, connection, memory và slot xử lý khi chờ vô hạn.
- Queue có thể tích tụ nếu mỗi tác vụ chiếm worker quá lâu.
- Một request bị treo có thể làm cạn concurrency của cả service.

Timeout không tự chứng minh thao tác phía server đã dừng. Client có thể hết thời gian chờ trong khi server vẫn tiếp tục xử lý.

### 1.2. Retry là thực hiện lại một thao tác

Retry là thử lại thao tác sau khi lần trước thất bại hoặc không nhận được kết quả trong thời hạn cho phép.

Retry có thể hữu ích khi lỗi chỉ tồn tại tạm thời, ví dụ:
- Kết nối bị reset trong thời gian ngắn.
- Dịch vụ trả về quá tải tạm thời.
- Một node đang được thay thế.
- Rate limit yêu cầu chờ trước khi gửi lại.
- Network có packet loss ngắn hạn.

Retry không sửa được lỗi vĩnh viễn như request sai schema, thiếu quyền, tài nguyên không tồn tại hoặc nghiệp vụ bị từ chối. Thử lại những lỗi này chỉ tăng tải và kéo dài thời gian xử lý.

### 1.3. Ba kết quả cần phân biệt

Một lần gọi có thể kết thúc theo ba trạng thái:

1. **Thành công đã xác nhận:** caller nhận kết quả thành công và có bằng chứng thao tác đã hoàn tất.
2. **Thất bại đã xác nhận:** caller nhận lỗi cho biết thao tác không được thực hiện hoặc bị từ chối.
3. **Kết quả không xác định:** caller hết timeout hoặc mất kết nối nên không biết server đã commit hay chưa.

Trạng thái thứ ba đặc biệt quan trọng. Ví dụ, worker gửi lệnh tạo hóa đơn; database commit thành công nhưng response bị mất. Worker retry một request mới có thể tạo hóa đơn thứ hai.

Với kết quả không xác định, cần dùng idempotency key, truy vấn trạng thái theo operation ID hoặc cơ chế deduplication trước khi phát lại side effect.

### 1.4. Timeout và retry phải được thiết kế cùng nhau

Nếu mỗi lần gọi có timeout 10 giây và retry 5 lần, tổng thời gian chờ có thể vượt 50 giây, chưa kể backoff và thời gian xử lý. Nếu queue visibility timeout chỉ 30 giây, message có thể được giao cho worker khác trong khi worker đầu vẫn đang retry.

Cần thiết kế đồng thời:
- Timeout từng thao tác.
- Deadline tổng của job.
- Số lần thử tối đa.
- Khoảng chờ giữa các lần thử.
- Visibility timeout hoặc lease.
- Thời gian xử lý tối đa của worker/serverless function.
- Chính sách hủy và xử lý khi hết deadline.

## 2. Phân loại lỗi trước khi retry

### 2.1. Lỗi tạm thời (transient error)

Lỗi tạm thời có khả năng biến mất nếu chờ một khoảng thời gian hợp lý.

Ví dụ:
- Network reset hoặc connection timeout.
- DNS resolver timeout tạm thời.
- HTTP 408 Request Timeout.
- HTTP 429 Too Many Requests khi có thể chờ theo hướng dẫn.
- HTTP 500, 502, 503 hoặc 504 tùy hợp đồng API.
- Database deadlock hoặc lỗi failover có thể thử lại.
- Storage throttling hoặc service unavailable.
- Queue hoặc broker tạm thời không sẵn sàng.

Không phải mọi mã 5xx đều chắc chắn retryable. Ví dụ một gateway có thể trả 502 vì upstream cấu hình sai; retry liên tục sẽ không giúp. Cần kết hợp mã lỗi, error code chi tiết, operation semantics và tài liệu của dependency.

### 2.2. Lỗi vĩnh viễn (permanent error)

Lỗi vĩnh viễn thường cần sửa request, dữ liệu, quyền hoặc cấu hình trước khi chạy lại.

Ví dụ:
- Payload không đúng schema.
- Thiếu trường bắt buộc.
- Định dạng dữ liệu không hợp lệ.
- Không có quyền truy cập.
- Credential không hợp lệ hoặc đã bị thu hồi.
- Tài nguyên được tham chiếu không tồn tại.
- Vi phạm constraint nghiệp vụ.
- Một phiên bản API không còn được hỗ trợ.
- File đầu vào bị hỏng.

Không nên retry tự động các lỗi này theo cùng một request. Có thể đưa message vào dead-letter queue (DLQ), lưu error detail và yêu cầu sửa dữ liệu hoặc can thiệp của người vận hành.

### 2.3. Lỗi cần xử lý đặc biệt

Một số lỗi không thể phân loại chỉ bằng status code:

- **Timeout sau khi gửi request:** kết quả có thể đã commit.
- **HTTP 409 Conflict:** có thể là xung đột nghiệp vụ hoặc trạng thái có thể giải quyết bằng cách đọc lại.
- **HTTP 401/403:** thường cần sửa credential/quyền; refresh token có thể là trường hợp retry có điều kiện.
- **HTTP 404:** thường là tài nguyên không tồn tại, nhưng đôi khi endpoint eventual consistency cần chờ ngắn.
- **HTTP 429:** cần tuân thủ Retry-After và giới hạn retry.
- **HTTP 500:** có thể do lỗi tạm thời hoặc lỗi logic luôn tái diễn.
- **Database connection lost khi commit:** transaction có thể đã được commit; cần kiểm tra kết quả bằng operation ID trước khi phát lại.

Phân loại cần dựa trên hợp đồng của dịch vụ và ngữ cảnh thao tác, không chỉ dựa vào một bảng mã HTTP chung.

### 2.4. Bảng quyết định retry

| Nhóm lỗi | Ví dụ | Retry tự động? | Hành động |
|---|---|---|---|
| Network tạm thời | Reset, connect timeout | Có giới hạn | Backoff và jitter |
| Quá tải | 429, throttling, 503 | Có điều kiện | Tôn trọng Retry-After, giảm concurrency |
| Dependency chưa sẵn sàng | 502/504 trong thời gian deploy | Có điều kiện | Retry, theo dõi health |
| Request không hợp lệ | 400, schema error | Không | Sửa payload hoặc đưa DLQ |
| Không được phép | 401/403 | Thường không | Sửa identity/policy hoặc credential |
| Không tìm thấy | 404 | Không mặc định | Kiểm tra tham chiếu hoặc semantics eventual consistency |
| Xung đột | 409, version conflict | Có điều kiện | Đọc trạng thái mới và giải quyết theo nghiệp vụ |
| Kết quả không xác định | Timeout sau commit có thể xảy ra | Không retry mù | Tra cứu operation/idempotency key |
| Hết deadline | Job vượt thời gian cho phép | Không trong job hiện tại | Checkpoint, requeue theo policy hoặc đánh dấu cần xử lý |

Bảng này là hướng dẫn ban đầu. Mỗi dependency cần có policy cụ thể, bao gồm mã lỗi, error code, thao tác được phép retry và giới hạn tổng.

## 3. Thiết kế timeout nhiều lớp

### 3.1. Connect timeout

Connect timeout giới hạn thời gian thiết lập kết nối tới dependency. Nó bao gồm việc hoàn thành các bước kết nối cần thiết của client, tùy giao thức và thư viện.

Nếu connect timeout quá dài:
- Worker giữ slot trong lúc không thể làm việc.
- Nhiều kết nối chờ có thể làm cạn pool.
- Queue backlog tăng.

Nếu quá ngắn:
- Kết nối hợp lệ trên mạng có độ trễ cao có thể bị hủy liên tục.
- Retry làm tăng số connection attempt và tải network.

### 3.2. Read/response timeout

Read timeout giới hạn thời gian chờ dữ liệu phản hồi sau khi kết nối đã được thiết lập hoặc sau khi gửi request, tùy client library.

Một số thư viện định nghĩa read timeout theo khoảng thời gian giữa các lần nhận byte, không phải tổng thời gian response. Vì vậy cần hiểu semantics của thư viện và đặt thêm deadline tổng nếu cần.

### 3.3. Write timeout

Write timeout giới hạn thời gian gửi request body hoặc dữ liệu tới socket. Với upload lớn hoặc stream, write có thể bị block khi network hoặc server không đọc kịp.

### 3.4. Request/operation timeout

Operation timeout giới hạn tổng thời gian cho một lần thao tác logic, có thể gồm:
- Lấy connection từ pool.
- Kết nối.
- TLS handshake.
- Gửi request.
- Chờ response.
- Đọc body.
- Deserialize và xử lý kết quả.

Cần đặt operation timeout bao trùm các timeout thành phần, tránh tổng thời gian thực tế vượt ngoài dự kiến.

### 3.5. Job deadline

Job deadline là thời điểm cuối cùng mà toàn bộ tác vụ được phép hoàn tất. Deadline phải bao gồm tất cả lần thử, backoff, thao tác phụ và bước commit.

Ví dụ:
- Job có deadline 60 giây.
- Connect timeout 2 giây.
- Operation timeout mỗi lần 8 giây.
- Tối đa 3 lần thử.
- Backoff lần lượt 1 và 2 giây.

Tổng thời gian tối đa dự kiến: 3 × 8 + 1 + 2 = 27 giây, chưa tính xử lý nội bộ. Phần còn lại dành cho validate, commit và cleanup. Nếu lần gọi đầu đã tiêu thụ 20 giây, không nên bắt đầu thêm một lần thử 8 giây khi deadline chỉ còn 5 giây.

### 3.6. Timeout theo dependency và nghiệp vụ

Không dùng một timeout chung cho mọi dependency. Ví dụ:
- Cache lookup có thể cần vài chục mili giây.
- API nội bộ có thể cần vài trăm mili giây.
- Báo cáo hoặc batch query có thể cần vài phút.
- Upload object lớn cần timeout theo kích thước và throughput.

Timeout phải phản ánh SLO, latency thực tế, kích thước request và ngân sách của job.

## 4. Deadline propagation và cancellation

### 4.1. Truyền deadline xuyên suốt

Nếu job có deadline 30 giây, mỗi service con phải biết thời gian còn lại. Nếu mỗi service tự bắt đầu một timeout 30 giây mới, tổng thời gian toàn chuỗi có thể vượt xa 30 giây.

Có thể truyền:
- Absolute deadline theo timestamp có kiểm soát đồng hồ.
- Remaining timeout theo duration.
- Operation ID để theo dõi tác vụ.
- Cancellation signal khi caller không còn cần kết quả.

Khi truyền deadline qua nhiều service, cần tính sai lệch đồng hồ và dành thời gian cho response/cleanup. Thường dùng remaining budget trong request context hoặc RPC deadline.

### 4.2. Cancellation phải truyền tới dependency

Khi job hết deadline hoặc bị hủy, worker nên:
- Ngừng bắt đầu thao tác mới.
- Hủy request đang chờ nếu client library hỗ trợ.
- Đóng stream hoặc connection phù hợp.
- Dừng batch ở ranh giới an toàn.
- Lưu checkpoint nếu có thể.
- Giải phóng lease và tài nguyên.

Hủy ở client không bảo đảm server đã dừng. Với side effect đã gửi, vẫn cần kiểm tra trạng thái hoặc dùng idempotency.

### 4.3. Timeout không phải kill switch

Một timeout có thể chỉ ngừng chờ ở caller. Server vẫn có thể:
- Tiếp tục query database.
- Hoàn tất giao dịch.
- Ghi file hoặc object.
- Gửi message.
- Gọi dịch vụ tiếp theo.

Vì vậy, timeout cần được phối hợp với server-side deadline, cancellation token, transaction timeout hoặc operation status nếu nền tảng hỗ trợ.

## 5. Backoff, jitter và giới hạn số lần retry

### 5.1. Retry ngay lập tức có thể làm sự cố nặng hơn

Giả sử database đang quá tải. 1.000 worker cùng nhận lỗi rồi retry ngay. Database nhận thêm 1.000 request mới trong khi chưa hồi phục, khiến lỗi tiếp tục tăng. Đây là retry storm.

Retry không có khoảng chờ còn có thể:
- Tạo nhiều kết nối cùng lúc.
- Làm tăng queue và CPU.
- Tạo burst lên API bị rate limit.
- Làm các worker đồng bộ retry theo cùng chu kỳ.

### 5.2. Exponential backoff

Exponential backoff tăng thời gian chờ sau mỗi lần thất bại.

Công thức cơ bản:

**delay(n) = min(max_delay, base_delay × 2^(n-1))**

Ví dụ base delay 500 ms, max delay 8 giây:

| Lần thử lại | Delay trước lần thử |
|---:|---:|
| 1 | 0,5 giây |
| 2 | 1 giây |
| 3 | 2 giây |
| 4 | 4 giây |
| 5 | 8 giây |
| 6 trở đi | 8 giây |

Cần đặt max attempts hoặc deadline tổng. Backoff không có giới hạn có thể khiến job tồn tại vô thời hạn.

### 5.3. Jitter

Jitter thêm yếu tố ngẫu nhiên vào delay để các worker không retry cùng một thời điểm.

Một cách phổ biến là full jitter:

**delay(n) = random(0, min(max_delay, base_delay × 2^(n-1)))**

Ví dụ lần thử có cửa sổ 4 giây thì mỗi worker chọn ngẫu nhiên một thời điểm từ 0 đến 4 giây. Điều này phân tán request và giảm đồng bộ tải.

Có nhiều biến thể jitter. Chọn một thuật toán thống nhất, kiểm thử với tải lớn và ghi rõ giới hạn.

### 5.4. Tôn trọng Retry-After

Một số dịch vụ trả Retry-After để chỉ ra thời gian client nên chờ trước khi gửi lại. Giá trị có thể biểu diễn số giây hoặc thời điểm theo HTTP-date.

Client nên:
- Parse header đúng định dạng.
- Không retry sớm hơn thời điểm được yêu cầu.
- Áp dụng giới hạn deadline tổng.
- Có jitter bổ sung nếu policy phù hợp.
- Không để một giá trị bất thường làm job bị giữ vô hạn; áp dụng maximum wait và chuyển sang lịch retry dài hạn nếu cần.

### 5.5. Giới hạn attempts và retry budget

Một policy cần nêu rõ:
- Số lần thử tối đa.
- Thời gian backoff.
- Deadline tổng.
- Nhóm lỗi được retry.
- Retry budget của service hoặc dependency.
- Điều kiện đưa message vào DLQ.

Retry budget giới hạn lượng retry so với lượng request gốc trong một khoảng thời gian. Khi lỗi tăng diện rộng, hệ thống có thể giảm retry để bảo vệ dependency thay vì tiếp tục tạo tải.

Không cộng retry của mọi tầng mà không tính tổng. Nếu API gateway retry 3 lần, worker retry 4 lần và SDK retry 3 lần, một thao tác gốc có thể tạo tới 36 request tới dependency trong trường hợp xấu nhất.

## 6. Idempotency và tránh lặp tác động nghiệp vụ

### 6.1. Idempotency là gì?

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng một định danh hoặc input mà không tạo thêm tác động nghiệp vụ ngoài kết quả mong muốn.

Ví dụ:
- Đặt trạng thái đơn hàng thành PAID theo version cụ thể.
- Ghi kết quả xử lý theo khóa duy nhất của job.
- Tạo resource với một idempotency key đã được cấp.
- Ghi nhận message đã xử lý trong inbox table có unique constraint.

Ngược lại, thao tác “cộng thêm 100 vào số dư” không idempotent nếu thực hiện lặp hai lần. Một thao tác chuyển tiền hoặc tạo hóa đơn cần cơ chế chống trùng rõ ràng.

### 6.2. Idempotency key

Client tạo một key ổn định cho một nghiệp vụ logic và dùng lại key đó ở mọi lần retry. Server lưu key cùng trạng thái/kết quả thao tác.

Ví dụ:
- operation_id = order-8472-charge-v1
- Request đầu tiên với key này tạo giao dịch.
- Request retry với cùng key nhận lại kết quả đã lưu.
- Request mới cho nghiệp vụ khác phải có key khác.

Không tạo idempotency key mới cho mỗi lần retry; như vậy server không thể nhận ra các lần thử thuộc cùng một thao tác.

### 6.3. Bảng idempotency

Một bảng lưu key có thể có các trường:

| Trường | Mục đích |
|---|---|
| idempotency_key | Định danh duy nhất của thao tác |
| request_hash | Phát hiện cùng key nhưng payload khác |
| status | IN_PROGRESS, SUCCEEDED, FAILED_FINAL |
| result_reference | Tham chiếu kết quả đã commit |
| created_at | Thời điểm tạo |
| expires_at | Thời điểm hết thời hạn giữ key |
| owner/lease | Theo dõi worker đang xử lý nếu cần |

Khi nhận key đã tồn tại:
- Nếu đã thành công, trả lại kết quả đã lưu.
- Nếu đang xử lý, trả trạng thái đang xử lý hoặc cho caller chờ có giới hạn.
- Nếu thất bại vĩnh viễn, trả lỗi cuối cùng.
- Nếu payload hash khác, từ chối vì cùng key đang bị dùng sai.

Trường idempotency_key cần có unique constraint hoặc cơ chế compare-and-set tương đương để hai worker nhận cùng request đồng thời không cùng tạo record mới. Thời gian giữ key phải dài hơn cửa sổ retry, redelivery và replay DLQ có thể xảy ra. Nếu provider bên ngoài chỉ giữ idempotency key trong một khoảng thời gian ngắn, sau khi khoảng đó hết hạn cần tra cứu hoặc đối soát trạng thái trước khi gửi lại side effect.

### 6.4. Atomicity giữa side effect và idempotency record

Không nên lưu idempotency record thành công trước khi side effect được commit, hoặc commit side effect rồi bỏ qua việc ghi nhận key mà không có cơ chế phục hồi.

Nếu cả hai nằm trong cùng database, có thể dùng một transaction để:
1. Kiểm tra hoặc tạo idempotency key.
2. Thực hiện thay đổi nghiệp vụ.
3. Lưu kết quả.
4. Commit cùng nhau.

Nếu side effect nằm ở hệ thống khác, cần pattern phù hợp như transactional outbox, inbox/deduplication, saga hoặc API idempotency do provider hỗ trợ.

### 6.5. Transactional outbox

Transactional outbox giải quyết trường hợp ứng dụng vừa cập nhật database vừa cần phát message.

Trong cùng một transaction:
- Cập nhật trạng thái nghiệp vụ.
- Ghi một event vào outbox table.

Một dispatcher đọc outbox và publish message. Nếu publish thành công nhưng dispatcher không kịp đánh dấu đã gửi, event có thể được publish lại. Consumer cần inbox/deduplication hoặc xử lý idempotent.

Outbox tránh khoảng trống giữa commit database và publish event, nhưng không tự tạo exactly-once end-to-end.

### 6.6. Exactly-once cần hiểu theo phạm vi

Nhiều queue hoặc stream có thể cung cấp exactly-once semantics trong một phạm vi nhất định, ví dụ giữa consumer offset và transaction của một broker. Điều đó không tự động bảo đảm side effect tới database, email, payment provider hoặc API bên ngoài chỉ xảy ra đúng một lần.

Trong hệ thống phân tán, thường thiết kế theo hướng:
- At-least-once delivery.
- Idempotent processing.
- Deduplication bền vững.
- Transaction hoặc outbox/inbox cho ranh giới dữ liệu.
- Đối soát trạng thái khi kết quả không xác định.

## 7. Retry trong queue và batch worker

### 7.1. Message có thể được giao nhiều lần

Nhiều queue hoạt động theo at-least-once delivery. Nếu worker xử lý xong nhưng ACK bị mất, message có thể được giao lại. Nếu worker crash trước ACK, message cũng có thể xuất hiện lại sau visibility timeout.

Vì vậy:
- Mỗi message nên có message ID hoặc business operation ID ổn định.
- Side effect cần idempotent hoặc có deduplication.
- ACK chỉ sau khi kết quả được commit.
- Visibility timeout phải đủ cho thời gian xử lý hoặc được gia hạn an toàn.

### 7.2. Phân biệt retry trong process và retry bằng queue

**Retry trong process:** worker giữ message và thử lại dependency trong cùng lần xử lý. Phù hợp với lỗi ngắn, có khả năng hồi phục nhanh.

**Retry bằng queue:** worker không ACK hoặc chủ động requeue message để xử lý sau. Phù hợp khi cần backoff dài, worker không nên giữ slot hoặc dependency đang gián đoạn.

Không nên retry hàng trăm lần trong một process rồi mới trả message về queue. Cách đó giữ worker, connection và memory không cần thiết.

### 7.3. Visibility timeout và lease

Visibility timeout là khoảng thời gian message đã được nhận tạm thời không hiển thị cho worker khác. Nếu thời gian xử lý vượt timeout mà worker không gia hạn, message có thể được giao lại trong khi worker cũ vẫn chạy.

Cần:
- Đặt visibility timeout lớn hơn thời gian xử lý bình thường và có headroom.
- Gia hạn visibility/lease khi job còn hoạt động.
- Có deadline tổng và số lần gia hạn tối đa.
- Dừng ghi nếu worker đã mất quyền sở hữu.
- Dùng fencing token nếu hệ thống cần ngăn worker stale ghi dữ liệu.

Gia hạn lease không được làm job treo giữ message vô hạn. Theo dõi số lần gia hạn, tuổi job và lease expiry.

### 7.4. Retry delay và delayed queue

Với lỗi cần chờ lâu, delayed queue hoặc scheduler có thể lưu thời điểm được phép thử lại. Worker ACK/requeue theo semantics của hệ thống và không phải giữ thread trong thời gian chờ.

Cần bảo đảm:
- Retry message giữ nguyên operation ID.
- Số lần thử và next-attempt time được lưu.
- Delay không vượt job deadline hoặc retention.
- Message không bị gửi đồng thời qua cả queue chính và retry queue ngoài ý muốn.
- Có cơ chế xử lý khi publish retry thành công nhưng ACK message cũ thất bại.

### 7.5. Batch processing và partial failure

Một batch có thể gồm nhiều record. Nếu một record lỗi, có hai chiến lược:
- Retry cả batch.
- Chỉ retry record lỗi nếu event source hỗ trợ partial batch response.

Retry cả batch có thể xử lý lại các record đã thành công. Consumer cần idempotent hoặc lưu kết quả theo record ID.

Ví dụ batch 100 message:
- 98 message xử lý và commit thành công.
- 2 message lỗi tạm thời.
- Nếu retry toàn batch, 98 message cũ sẽ chạy lại.
- Nếu hỗ trợ partial failure, chỉ 2 message lỗi được giao lại.

Với batch có side effect, cần ghi nhận kết quả từng item hoặc transaction phù hợp. Không ACK cả batch nếu kết quả của một phần chưa được bảo vệ theo semantics của event source.

### 7.6. Poison message và dead-letter queue

Poison message là message luôn gây lỗi do dữ liệu hoặc điều kiện không thể phục hồi bằng retry thông thường.

Sau số lần thử hoặc thời hạn nhất định, chuyển message sang DLQ. DLQ cần lưu:
- Payload hoặc tham chiếu payload.
- Message ID và operation ID.
- Error class và error code.
- Số lần thử.
- Thời điểm đầu/cuối.
- Worker/version xử lý.
- Trace ID và dependency liên quan.

DLQ không phải nơi bỏ quên message. Cần cảnh báo, phân loại, quy trình sửa dữ liệu và replay có kiểm soát.

## 8. Phân loại và lưu trạng thái lỗi

### 8.1. Error taxonomy

Có thể định nghĩa các nhóm lỗi thống nhất:

| Nhóm | Ví dụ | Retry tự động? | Hành động |
|---|---|---|---|
| TRANSIENT_NETWORK | Reset, DNS timeout | Có giới hạn | Backoff và jitter |
| TRANSIENT_CAPACITY | 429, throttling | Có điều kiện | Tôn trọng Retry-After, giảm concurrency |
| DEPENDENCY_UNAVAILABLE | 502/503/504 | Có điều kiện | Retry, circuit breaker |
| DEADLOCK_CONFLICT | Deadlock, optimistic conflict | Có giới hạn | Rollback và thử transaction mới |
| INVALID_INPUT | Schema hoặc dữ liệu sai | Không | DLQ hoặc sửa dữ liệu |
| AUTHORIZATION | Thiếu quyền, token sai | Thường không | Sửa identity/policy |
| NOT_FOUND | Resource không tồn tại | Thường không | Kiểm tra tham chiếu |
| BUSINESS_REJECTED | Vượt hạn mức, trạng thái không hợp lệ | Không | Kết thúc theo nghiệp vụ |
| UNKNOWN_OUTCOME | Timeout sau commit có thể xảy ra | Không retry mù | Tra cứu operation/idempotency |
| DEADLINE_EXCEEDED | Hết ngân sách thời gian | Không trong job hiện tại | Checkpoint hoặc requeue theo policy |

Tên nhóm là ví dụ. Hãy thống nhất taxonomy giữa worker, API, queue và monitoring để dashboard không phải xử lý hàng chục cách đặt tên tương tự.

### 8.2. Error envelope

Một lỗi có cấu trúc có thể gồm:
- code: mã lỗi ổn định.
- category: nhóm lỗi.
- retryable: quyết định theo policy.
- retry_after_ms: thời gian chờ gợi ý nếu có.
- operation_id: định danh nghiệp vụ.
- attempt: lần thử hiện tại.
- dependency: hệ thống liên quan.
- trace_id: mã truy vết.
- message: mô tả đã làm sạch, không chứa secret hoặc dữ liệu nhạy cảm.

Không nên để mọi service tự phân loại retryable theo chuỗi thông báo lỗi. Dùng error code và hợp đồng rõ ràng.

### 8.3. Lưu trạng thái attempt

Đối với job dài hoặc quan trọng, lưu:
- Job ID và operation ID.
- Attempt count.
- Thời điểm lần thử cuối.
- Next retry time.
- Deadline.
- Error category/code gần nhất.
- Checkpoint hoặc bước đã hoàn tất.
- Idempotency state.
- Worker lease/owner nếu có.

Trạng thái bền vững giúp worker mới tiếp tục sau restart và giúp vận hành điều tra vì sao job đang chờ.

## 9. Retry budget, circuit breaker và bulkhead

### 9.1. Retry budget

Retry budget giới hạn tổng lượng retry được phép trong một khoảng thời gian. Khi tỷ lệ lỗi tăng, hệ thống giảm retry để không khuếch đại tải.

Ví dụ policy minh họa:
- Chỉ retry tối đa 10% số request gốc trong một cửa sổ.
- Khi vượt budget, đưa tác vụ vào queue chờ hoặc trả lỗi có kiểm soát.
- Reset budget dần khi dependency hồi phục.

Con số phải dựa trên tải và capacity thật. Budget có thể được quản lý theo client, service, tenant hoặc dependency.

### 9.2. Circuit breaker

Circuit breaker theo dõi lỗi dependency và chuyển qua các trạng thái:
- **Closed:** request được phép đi qua.
- **Open:** tạm ngừng gọi dependency khi lỗi vượt ngưỡng.
- **Half-open:** cho phép một số request thử để xác định dependency đã hồi phục chưa.

Khi circuit open, không nên tiếp tục retry ngay trong từng worker. Có thể chờ, queue lại hoặc dùng fallback an toàn.

Circuit breaker cần:
- Ngưỡng lỗi và cửa sổ quan sát.
- Thời gian open.
- Số probe ở half-open.
- Phân loại lỗi để không mở circuit vì lỗi nghiệp vụ.
- Metric và log cho từng lần chuyển trạng thái.

### 9.3. Bulkhead

Bulkhead giới hạn tài nguyên dành cho từng dependency hoặc nhóm workload:
- Connection pool riêng.
- Thread/worker pool riêng.
- Concurrency cap theo dependency.
- Queue riêng cho tác vụ nặng.
- Giới hạn số job mỗi tenant.

Nếu một dependency chậm, bulkhead ngăn nó chiếm toàn bộ worker và connection của service.

### 9.4. Kết hợp các cơ chế

Timeout giới hạn thời gian một lần gọi. Retry xử lý lỗi tạm thời. Backoff/jitter giảm đồng bộ. Retry budget giới hạn khuếch đại tải. Circuit breaker ngăn gọi dependency đang lỗi. Bulkhead bảo vệ tài nguyên còn lại. Idempotency bảo vệ nghiệp vụ khi thao tác được thực hiện lại.

Không cơ chế nào thay thế được các cơ chế còn lại.

## 10. Ví dụ triển khai retry có deadline và idempotency

Pseudocode sau minh họa một client gọi dependency với timeout, phân loại lỗi, backoff, jitter và cùng idempotency key qua mọi lần thử:

~~~python
import random
import time

RETRYABLE_CODES = {
    "TEMPORARY_UNAVAILABLE",
    "RATE_LIMITED",
    "NETWORK_RESET",
}

def call_with_retry(client, request, operation_id, deadline):
    attempt = 0
    base_delay = 0.2
    max_delay = 3.0
    max_attempts = 4

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("operation deadline exceeded")

        attempt += 1
        call_timeout = min(2.0, remaining)

        try:
            return client.execute(
                request,
                timeout=call_timeout,
                idempotency_key=operation_id,
            )
        except client.Error as exc:
            if exc.code not in RETRYABLE_CODES:
                raise

            if attempt >= max_attempts:
                raise

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("operation deadline exceeded")

            ceiling = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay = random.uniform(0, ceiling)

            retry_after = getattr(exc, "retry_after_seconds", None)
            if retry_after is not None:
                delay = max(delay, retry_after)

            if delay >= remaining:
                raise TimeoutError("insufficient deadline for retry")

            time.sleep(delay)
~~~

Đây là pseudocode minh họa, không phải thư viện hoàn chỉnh. Trong production cần:
- Dùng monotonic clock cho deadline.
- Xác định chính xác error type/code của client.
- Xử lý Retry-After theo hợp đồng dịch vụ và giới hạn tối đa.
- Không retry nếu operation có side effect mà server không hỗ trợ idempotency hoặc trạng thái chưa được xác minh.
- Thêm cancellation và telemetry.
- Tránh sleep giữ worker nếu có thể schedule retry qua queue.

### 10.1. Ví dụ worker xử lý message

~~~text
receive(message)
operation_id = message.business_operation_id
deadline = message.deadline

if already_committed(operation_id):
    acknowledge(message)
    return

result = execute_with_deadline_and_retry(
    operation_id,
    message.payload,
    deadline
)

commit_result_and_idempotency_record(result, operation_id)
acknowledge(message)
~~~

Trong triển khai thực tế, already_committed, side effect và idempotency record phải có cơ chế atomic hoặc reconciliation. Không thể chỉ dựa vào thứ tự các dòng pseudocode nếu side effect nằm ngoài database hiện tại.

## 11. Ví dụ thực tế: worker tạo hóa đơn

Một worker nhận message yêu cầu tạo hóa đơn sau khi đơn hàng được thanh toán. Worker gọi API hóa đơn bên ngoài.

Tình huống:
1. Worker gửi request tạo hóa đơn với operation ID invoice-order-8472.
2. Provider xử lý thành công và tạo hóa đơn.
3. Response bị mất do network timeout.
4. Worker không biết hóa đơn đã được tạo.
5. Nếu retry bằng request mới không có idempotency key, provider có thể tạo hóa đơn thứ hai.

Cách thiết kế:
- Dùng operation ID ổn định theo đơn hàng và loại nghiệp vụ.
- Gửi cùng idempotency key ở mọi lần retry.
- Nếu provider hỗ trợ tra cứu theo key, truy vấn trước khi tạo lại.
- Lưu trạng thái IN_PROGRESS và kết quả provider reference.
- Chỉ đánh dấu job hoàn tất sau khi đã ghi nhận kết quả bền vững.
- ACK message sau commit.
- Nếu provider trả lỗi permanent, chuyển DLQ và cảnh báo owner.
- Nếu provider timeout liên tục, mở circuit và schedule retry sau.

Khi replay DLQ, giữ operation ID cũ. Tạo key mới sẽ làm mất khả năng nhận diện nghiệp vụ đã được thực hiện.

## 12. Batch, checkpoint và retry từng phần

### 12.1. Chia batch thành đơn vị có thể phục hồi

Một batch lớn nên có checkpoint hoặc ranh giới commit. Ví dụ xử lý 10.000 bản ghi:
- Chia thành các chunk 100 record.
- Mỗi chunk có range hoặc cursor ổn định.
- Ghi kết quả chunk theo transaction.
- Lưu checkpoint sau khi commit.
- Nếu worker bị dừng, tiếp tục từ chunk chưa hoàn tất.

Không cập nhật checkpoint trước khi kết quả của chunk được commit. Nếu lưu checkpoint trước rồi crash khi ghi dữ liệu, hệ thống có thể bỏ qua chunk chưa hoàn thành.

### 12.2. Retry một chunk

Chunk có thể có ID ổn định, ví dụ job-2026-11-22/chunk-0042. Khi retry:
- Dùng cùng chunk ID.
- Kiểm tra chunk đã commit chưa.
- Ghi kết quả theo unique key.
- Chỉ cập nhật checkpoint khi commit thành công.
- Không chạy lại side effect không idempotent ngoài transaction.

### 12.3. Partial success

Một batch có thể chứa nhiều item độc lập. Lưu trạng thái từng item:
- PENDING
- IN_PROGRESS
- SUCCEEDED
- RETRY_WAIT
- FAILED_FINAL

Có thể retry item lỗi mà không chạy lại item thành công. Tuy nhiên, nếu item thành công tạo side effect ngoài hệ thống lưu trạng thái, cần idempotency riêng cho item đó.

### 12.4. Checkpoint không thay thế idempotency

Checkpoint cho biết tiến độ đã lưu tới đâu. Nó không tự bảo đảm thao tác ngay trước checkpoint chỉ xảy ra một lần.

Ví dụ:
1. Worker ghi giao dịch thành công.
2. Worker crash trước khi ghi checkpoint.
3. Job được chạy lại từ checkpoint cũ.
4. Giao dịch có thể được ghi lần nữa.

Cần idempotency key, unique constraint, inbox table hoặc transaction kết hợp side effect với checkpoint trong cùng ranh giới dữ liệu nếu có thể.

## 13. Timeout và retry trong serverless/container

### 13.1. Serverless function

Serverless function thường có giới hạn thời gian chạy tối đa. Nếu invocation timeout, event source có thể retry theo policy riêng. Cần tính:
- Function timeout.
- Dependency timeout.
- Retry policy của trigger.
- Event retention.
- Concurrency và scaling rate.
- DLQ hoặc destination cho lỗi.
- Idempotency của side effect.

Nếu function timeout ở giây cuối sau khi đã commit database nhưng trước khi xác nhận event, event có thể được giao lại. Consumer phải idempotent.

### 13.2. Container worker

Container có thể bị restart, scale-in hoặc node bị thay thế. Worker cần:
- Bắt tín hiệu shutdown.
- Ngừng nhận message mới.
- Đặt deadline cho job đang chạy.
- Checkpoint hoặc requeue nếu không thể hoàn tất.
- Không ACK trước commit.
- Giải phóng lease và connection.
- Chịu được trường hợp bị kill mà không nhận được shutdown signal.

Timeout trong ứng dụng không thay thế timeout ở orchestrator, queue visibility hoặc external API. Các giới hạn phải được phối hợp.

### 13.3. Kubernetes Job/CronJob

Kubernetes Job có thể tạo lại Pod khi container thất bại tùy policy và giới hạn retry. Cần:
- Đặt backoffLimit phù hợp.
- Dùng activeDeadlineSeconds cho giới hạn tổng.
- Xác định restart policy.
- Đảm bảo job có thể chạy lại an toàn.
- Ghi checkpoint ở storage bền vững.
- Theo dõi failed Pod và job condition.

Kubernetes retry Pod không biết side effect nghiệp vụ đã commit hay chưa. Ứng dụng vẫn cần idempotency và deduplication.

### 13.4. Không nhân retry giữa nhiều tầng

Ví dụ:
- Queue redelivery tối đa 5 lần.
- Worker retry API 4 lần.
- SDK tự retry 3 lần.

Một message có thể tạo tới 60 request downstream trong trường hợp xấu nhất. Cần thống nhất retry ownership:
- SDK chỉ xử lý lỗi kết nối rất ngắn nếu cần.
- Worker quản lý retry nghiệp vụ và deadline.
- Queue quản lý retry dài hạn và DLQ.
- API gateway không tự retry side effect không idempotent.

Ghi rõ số lần thử tối đa tổng thể, không chỉ từng tầng riêng lẻ.

## 14. Observability và vận hành retry

### 14.1. Metric cần theo dõi

| Metric | Ý nghĩa | Dấu hiệu cần chú ý |
|---|---|---|
| operation_duration | Thời gian thao tác tổng | p95/p99 tăng |
| dependency_latency | Độ trễ dependency | Tăng đồng thời với timeout |
| timeout_count | Số timeout | Tăng theo dependency hoặc loại job |
| retry_attempts | Số lần retry | Tăng nhanh so với request gốc |
| retry_success_rate | Tỷ lệ thành công sau retry | Thấp kéo dài |
| retry_exhausted | Hết số lần thử | Tăng và tạo DLQ |
| queue_oldest_age | Tuổi message lâu nhất | Tiến gần retention/SLO |
| queue_depth | Số message đang chờ | Tăng liên tục |
| dlq_depth | Số message lỗi cuối | Có message mới hoặc tăng nhanh |
| idempotency_hit | Request đã được xử lý trước | Tăng bất thường có thể báo retry/duplicate |
| duplicate_suppressed | Side effect trùng đã bị chặn | Tăng bất thường cần điều tra |
| circuit_state | Trạng thái circuit breaker | Open kéo dài |
| deadline_exceeded | Job hết deadline | Tăng theo tải hoặc dependency |
| lease_expired | Lease hết hạn khi job còn chạy | Có thể tạo xử lý trùng |

### 14.2. Log có cấu trúc

Mỗi attempt nên ghi:
- Job ID, message ID và operation ID.
- Attempt number và max attempts.
- Error category/code.
- Dependency và operation name.
- Timeout, duration và remaining deadline.
- Retry delay và next attempt time.
- Trace ID.
- Kết quả idempotency check.

Không ghi password, token, authorization header hoặc payload nhạy cảm. Log cần giúp nối các lần retry thành một nghiệp vụ duy nhất.

### 14.3. Cảnh báo

Nên cảnh báo khi:
- Timeout rate vượt ngưỡng.
- Retry/request ratio tăng mạnh.
- DLQ có message mới hoặc vượt ngưỡng.
- Queue age vượt SLO.
- Circuit breaker open quá lâu.
- Retry budget bị tiêu thụ nhanh.
- Job hết deadline hoặc lease expiry tăng.
- Duplicate side effect được phát hiện.

Cảnh báo cần gắn với owner và runbook: kiểm tra dependency, giảm concurrency, tăng capacity có kiểm soát, dừng retry hoặc replay DLQ.

## 15. Quy trình xử lý sự cố timeout/retry

1. Xác định workload, dependency, thời điểm và phạm vi lỗi.
2. So sánh request rate, duration, concurrency và queue backlog.
3. Phân biệt connect timeout, read timeout, operation timeout và job deadline.
4. Kiểm tra mã lỗi, error code và hợp đồng retry của dependency.
5. Xác định thao tác có side effect hay không.
6. Với kết quả không xác định, tra cứu operation ID/idempotency key trước khi retry.
7. Kiểm tra retry count, backoff, Retry-After và retry budget.
8. Kiểm tra connection pool, downstream quota và circuit breaker.
9. Xem DLQ, poison message và checkpoint.
10. Khắc phục dependency hoặc dữ liệu gốc.
11. Replay có kiểm soát, giữ operation ID và theo dõi duplicate.
12. Đo lại latency, retry rate, queue age và kết quả nghiệp vụ.

Không xóa DLQ hoặc reset attempt count hàng loạt để “làm sạch” dashboard trước khi hiểu nguyên nhân. Thao tác đó có thể làm mất bằng chứng và phát lại tác vụ không an toàn.

## 16. Những sai lầm thường gặp

**Retry mọi exception.** Lỗi dữ liệu hoặc quyền không tự hết. Phân loại lỗi theo code và semantics.

**Dùng timeout quá dài.** Worker bị giữ lâu, queue backlog và concurrency tăng. Đặt timeout theo SLO và deadline.

**Retry ngay lập tức.** Các worker đồng bộ retry tạo retry storm. Dùng exponential backoff và jitter.

**Không có số lần thử tối đa.** Job có thể chạy vô hạn. Đặt max attempts, deadline và DLQ.

**Tạo idempotency key mới ở mỗi lần thử.** Server xem mỗi lần là nghiệp vụ mới. Giữ key ổn định theo operation.

**ACK message trước khi commit.** Worker crash có thể làm mất công việc. Commit kết quả rồi mới ACK.

**Cho rằng timeout nghĩa là server chưa thực hiện.** Server có thể đã commit và response bị mất. Tra cứu trạng thái trước khi phát lại.

**Chỉ dựa vào checkpoint.** Crash giữa side effect và checkpoint vẫn có thể lặp tác động. Kết hợp idempotency hoặc transaction.

**Retry ở mọi tầng.** Retry nhân lên theo tổ hợp gateway, SDK, worker và queue. Quy định rõ tầng sở hữu retry.

**Không tôn trọng Retry-After.** Có thể tiếp tục vi phạm rate limit. Chờ theo hướng dẫn và deadline.

**Giữ worker ngủ trong thời gian backoff dài.** Tốn concurrency và tài nguyên. Schedule retry qua queue khi phù hợp.

**Replay DLQ không kiểm tra.** Message cũ có thể không còn hợp lệ hoặc đã tạo side effect. Kiểm tra operation state và giữ idempotency key.

## 17. Checklist thiết kế

### Timeout và deadline

- [ ] Có connect, read/write và operation timeout phù hợp.
- [ ] Có deadline tổng cho mỗi job.
- [ ] Deadline được truyền tới dependency.
- [ ] Có cancellation và cleanup.
- [ ] Timeout được phối hợp với function runtime, queue visibility và orchestrator.

### Phân loại và retry

- [ ] Có error taxonomy ổn định.
- [ ] Chỉ retry lỗi được xác định là transient.
- [ ] Có max attempts và deadline tổng.
- [ ] Dùng exponential backoff và jitter.
- [ ] Tôn trọng Retry-After.
- [ ] Có retry budget và giới hạn concurrency.
- [ ] Không retry trùng lặp ở nhiều tầng ngoài kiểm soát.

### Bảo vệ nghiệp vụ

- [ ] Mỗi nghiệp vụ có operation ID ổn định.
- [ ] Retry giữ nguyên idempotency key.
- [ ] Side effect và idempotency record có ranh giới commit rõ.
- [ ] ACK chỉ sau commit.
- [ ] Có deduplication hoặc unique constraint.
- [ ] Có checkpoint và xử lý partial batch.
- [ ] Có cách tra cứu kết quả khi timeout tạo trạng thái không xác định.

### Vận hành

- [ ] Có DLQ và quy trình replay.
- [ ] Theo dõi timeout, retry, queue age và duplicate.
- [ ] Có circuit breaker và bulkhead khi cần.
- [ ] Log attempt có operation ID và trace ID.
- [ ] Có cảnh báo khi retry budget hoặc DLQ vượt ngưỡng.
- [ ] Kiểm thử dependency chậm, network reset và worker crash.
- [ ] Diễn tập tình huống server commit nhưng response bị mất.

## 18. Ghi nhớ

- Timeout giới hạn thời gian chờ; nó không chứng minh server đã dừng hoặc chưa commit.
- Retry chỉ phù hợp với lỗi tạm thời và phải có giới hạn.
- Phân biệt lỗi transient, permanent và kết quả không xác định.
- Connect/read/write timeout, operation timeout và job deadline có phạm vi khác nhau.
- Exponential backoff, jitter và Retry-After giúp giảm retry storm.
- Tính tổng retry qua gateway, SDK, worker và queue; tránh retry amplification.
- Side effect cần operation ID ổn định, idempotency key hoặc deduplication.
- ACK message sau khi kết quả được commit bền vững.
- Checkpoint không thay thế idempotency; crash giữa side effect và checkpoint vẫn có thể tạo tác động lặp.
- Dùng retry budget, circuit breaker và bulkhead để bảo vệ dependency.
- DLQ cần owner, cảnh báo và quy trình replay có kiểm soát.
- Kiểm thử cả trường hợp server đã commit nhưng client timeout.

## Thuật ngữ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Timeout | Giới hạn thời gian chờ của một thao tác. |
| Connect timeout | Thời gian tối đa để thiết lập kết nối. |
| Read timeout | Thời gian tối đa chờ dữ liệu phản hồi theo semantics của client. |
| Write timeout | Thời gian tối đa gửi dữ liệu qua kết nối. |
| Operation timeout | Giới hạn tổng thời gian cho một lần thao tác logic. |
| Deadline | Thời điểm cuối cùng mà công việc được phép hoàn tất. |
| Retry | Thực hiện lại thao tác sau một lần thất bại hoặc kết quả không nhận được. |
| Transient error | Lỗi tạm thời có khả năng tự hồi phục. |
| Permanent error | Lỗi cần sửa dữ liệu, quyền hoặc cấu hình trước khi thực hiện lại. |
| Exponential backoff | Tăng dần khoảng chờ giữa các lần retry. |
| Jitter | Thành phần ngẫu nhiên thêm vào delay để phân tán thời điểm retry. |
| Retry-After | HTTP header gợi ý thời điểm client nên gửi lại request. |
| Retry budget | Ngân sách giới hạn tổng lượng retry trong một khoảng thời gian. |
| Retry storm | Nhiều client retry đồng loạt làm tăng tải khi dependency đang lỗi. |
| Idempotency | Khả năng lặp thao tác mà không tạo thêm tác động ngoài mong muốn. |
| Idempotency key | Định danh ổn định của một thao tác nghiệp vụ qua nhiều lần thử. |
| Deduplication | Phát hiện và loại bỏ message hoặc thao tác trùng. |
| At-least-once delivery | Cơ chế giao message ít nhất một lần; message có thể được giao lại. |
| Acknowledgement (ACK) | Xác nhận message đã được xử lý theo semantics của queue. |
| Visibility timeout | Thời gian message đã nhận tạm thời không hiển thị cho worker khác. |
| Lease | Quyền sở hữu tài nguyên hoặc công việc có thời hạn. |
| Checkpoint | Trạng thái tiến độ được lưu để tiếp tục công việc sau gián đoạn. |
| Partial batch failure | Cơ chế báo một phần item trong batch thất bại để chỉ retry phần đó khi được hỗ trợ. |
| Dead-letter queue (DLQ) | Queue lưu message không xử lý thành công theo retry policy. |
| Poison message | Message luôn gây lỗi do dữ liệu hoặc điều kiện không thể phục hồi bằng retry thông thường. |
| Transactional outbox | Pattern lưu event cùng transaction nghiệp vụ rồi publish bằng dispatcher. |
| Inbox pattern | Pattern lưu dấu message đã nhận/xử lý để deduplicate. |
| Circuit breaker | Cơ chế ngừng tạm thời gọi dependency đang lỗi. |
| Bulkhead | Giới hạn tài nguyên riêng để lỗi ở một dependency không chiếm toàn bộ hệ thống. |
| Cancellation | Tín hiệu yêu cầu dừng công việc đang chờ hoặc đang thực hiện. |
