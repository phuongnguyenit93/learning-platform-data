# Giới hạn CPU, memory, connection và queue

## 1. Vì sao API phải giới hạn tài nguyên?

Một API có thể xác thực và phân quyền đúng nhưng vẫn bị khai thác để làm cạn năng lực hệ thống. Người gọi không cần gửi dữ liệu độc hại hoặc vượt qua validation; chỉ cần gửi nhiều request hợp lệ, request có kích thước lớn, truy vấn phức tạp hoặc thao tác khiến server gọi nhiều dịch vụ phía sau.

Mỗi request tiêu thụ một phần tài nguyên: CPU để parse, tính toán và mã hóa; memory để giữ body, object graph và response; connection để truy cập database hoặc dependency; thread/worker để thực thi; queue slot để chờ xử lý; bandwidth và storage để truyền hoặc giữ dữ liệu. Nếu không có giới hạn, một client hoặc tenant có thể chiếm hết năng lực dùng chung và làm các request bình thường bị chậm hoặc thất bại.

Rủi ro không chỉ là denial of service. Hệ thống quá tải còn có thể:

- Làm timeout dây chuyền, khiến client và các service retry đồng loạt.
- Giữ connection database quá lâu, khiến pool cạn và các luồng nghiệp vụ khác không thể truy cập dữ liệu.
- Tạo hàng đợi lớn, giữ payload nhạy cảm lâu hơn và làm tăng thời gian hoàn thành công việc.
- Gây OOM kill, restart liên tục hoặc mất tác vụ chưa được lưu bền vững.
- Làm tăng chi phí cloud, database, API nhà cung cấp và lưu trữ.
- Khiến một tenant gây ảnh hưởng đến độ sẵn sàng của các tenant khác.

Giới hạn tài nguyên là một phần của threat model API. Mỗi endpoint cần có ngân sách thực thi phù hợp với nghiệp vụ, đầu vào và dependency mà nó kích hoạt. Một con số request/giây chung không đủ để bảo vệ mọi tài nguyên.

## 2. Phân biệt các loại giới hạn

Các cơ chế dưới đây bổ sung cho nhau:

| Cơ chế | Giới hạn điều gì? | Ví dụ |
|---|---|---|
| Request size limit | Dung lượng đầu vào | Body tối đa 1 MB |
| Work/complexity limit | Công việc mà một request được phép yêu cầu | Tối đa 100 dòng, 5 bộ lọc, độ sâu truy vấn 4 |
| Rate limit | Tốc độ request trong một khoảng thời gian | Tối đa 20 request/giây |
| Quota | Tổng lượng sử dụng trong một chu kỳ | Tối đa 10.000 lượt export/tháng |
| Concurrency limit | Số công việc đang chạy đồng thời | Tối đa 4 báo cáo đang xử lý cho một tenant |
| Connection limit | Số kết nối tới tài nguyên | Giới hạn connection pool tới database |
| Queue capacity | Số công việc được phép chờ | Hàng đợi tối đa 500 tác vụ |
| Timeout/deadline | Thời gian tối đa để hoàn tất một bước hoặc toàn request | Truy vấn database tối đa 2 giây |
| CPU/memory limit | Tài nguyên tính toán của process/container | CPU quota và memory limit theo workload |
| Egress/bandwidth limit | Lưu lượng ra ngoài | Giới hạn tải xuống hoặc gọi dependency |

Rate limit trả lời “được gửi nhanh đến mức nào”; concurrency limit trả lời “được chạy bao nhiêu việc cùng lúc”; queue capacity trả lời “được giữ bao nhiêu việc đang chờ”; timeout trả lời “được giữ tài nguyên trong bao lâu”. Không cơ chế nào thay thế các cơ chế còn lại.

Ví dụ, giới hạn 10 request/giây vẫn có thể gây quá tải nếu mỗi request giữ một database connection trong 30 giây. Ngược lại, chỉ giới hạn 10 connection cũng chưa đủ nếu mỗi request tạo hàng nghìn truy vấn tuần tự hoặc chiếm CPU trong thời gian dài.

## 3. Lập ngân sách tài nguyên theo endpoint

Trước khi chọn ngưỡng, hãy mô tả đường đi thực tế của request. Một request có thể đi qua gateway, application service, database, cache, message broker, object storage và API bên ngoài. Từng bước có mức tiêu thụ và giới hạn riêng.

Với mỗi endpoint, ghi nhận:

1. Kích thước tối đa của header, body, file và số phần tử trong collection.
2. Số truy vấn database, loại truy vấn, số row có thể đọc/ghi và thời gian giữ connection.
3. CPU time, memory peak và kích thước object graph/response.
4. Số lần gọi dependency, timeout, retry và chi phí phát sinh.
5. Số thread/worker và thời gian xử lý đồng thời.
6. Queue slot, thời gian chờ và thời gian lưu tác vụ.
7. Số byte tải lên/tải xuống và dung lượng file tạm.
8. Tác động nếu client ngắt kết nối hoặc request hết deadline.

Phân loại endpoint theo mức tiêu thụ:

| Nhóm endpoint | Tài nguyên thường chi phối | Giới hạn nên cân nhắc |
|---|---|---|
| Đọc một object | Database connection, latency | Timeout, query scope, response size |
| Tìm kiếm/danh sách | CPU, DB I/O, memory | Page size, filter complexity, query timeout |
| Export/báo cáo | CPU, memory, storage, worker | Async queue, row limit, concurrency, file TTL |
| Upload/giải nén | Bandwidth, memory, disk, CPU | Body size, decompressed size, entry count, scan timeout |
| Gửi email/SMS | Dependency quota, chi phí | Recipient count, rate, tenant quota, retry budget |
| AI/ảnh/video | CPU/GPU, memory, token, chi phí | Input/output size, concurrency, budget, deadline |
| Bulk update | DB locks, transaction time, CPU | Batch size, chunking, transaction timeout |
| Webhook/callback | Outbound connection, retry, queue | Egress policy, concurrency, retry schedule |

Không suy ra chi phí chỉ từ số byte request. Một truy vấn nhỏ có thể quét hàng triệu row; một URL ngắn có thể khiến server tải file lớn; một request có thể fan-out thành nhiều lời gọi dịch vụ.

## 4. Đặt giới hạn đầu vào và độ phức tạp

Giới hạn tài nguyên nên bắt đầu từ biên request. Từ chối sớm đầu vào vượt ngưỡng giúp tránh parse hoặc cấp phát bộ nhớ không cần thiết.

### 4.1 Giới hạn kích thước

- Giới hạn tổng request body và kích thước từng field.
- Giới hạn số phần tử trong array, số file, số trang và số người nhận.
- Giới hạn độ dài chuỗi, tên file, header và query parameter.
- Giới hạn số multipart part và tổng dung lượng file sau khi nhận.
- Đặt giới hạn kích thước response, số row và số byte tải xuống.
- Với nội dung nén, giới hạn cả kích thước nén và kích thước sau giải nén.

Đặt giới hạn tại reverse proxy/gateway để từ chối sớm, đồng thời kiểm tra ở application vì request có thể đi qua đường nội bộ hoặc gateway khác. Đừng chỉ tin Content-Length; với streaming/chunked request, cần đếm byte thực tế khi đọc.

### 4.2 Giới hạn độ phức tạp truy vấn

Với API tìm kiếm và truy vấn:

- Bắt buộc pagination và page size tối đa.
- Giới hạn số filter, sort field, group-by, include/expand và relation depth.
- Dùng cursor pagination cho tập dữ liệu lớn hoặc thay đổi liên tục.
- Giới hạn số row scan hoặc đặt query timeout phù hợp.
- Tránh cho client gửi SQL, biểu thức hoặc regular expression tùy ý.
- Với GraphQL, giới hạn depth, complexity, alias, batch size và số node.
- Với JSON:API hoặc API có field selection, giới hạn số field và relation được yêu cầu.

Page size 100 không có nghĩa request luôn rẻ: một page có thể join nhiều bảng hoặc gọi resolver cho từng row. Hãy đo số truy vấn và độ phức tạp thực tế.

### 4.3 Giới hạn upload và giải nén

File nén nhỏ có thể giải nén thành dữ liệu rất lớn. Cần giới hạn:

- Byte truyền vào và byte sau giải nén.
- Số entry trong archive, độ sâu thư mục và kích thước từng entry.
- Kích thước ảnh theo pixel, số frame, thời lượng video và độ dài audio.
- Thời gian giải mã, quét malware và chuyển đổi định dạng.
- Số file đang được xử lý đồng thời và dung lượng vùng lưu tạm.

Xử lý file theo luồng khi có thể, tránh đọc toàn bộ nội dung vào heap. Đặt file tạm trong vùng riêng, có quota và quy trình xóa khi tác vụ hoàn tất hoặc thất bại.

## 5. Bảo vệ CPU

CPU bị tiêu thụ bởi parse/serialize, mã hóa, nén, regex, tính toán, xử lý ảnh, truy vấn và logic nghiệp vụ. Một request có thể chiếm CPU lâu dù body rất nhỏ.

### 5.1 Tránh công việc không giới hạn

- Giới hạn độ dài input cho regex và dùng engine an toàn để tránh catastrophic backtracking.
- Tránh thuật toán có độ phức tạp tăng nhanh theo kích thước đầu vào nếu client kiểm soát kích thước đó.
- Đặt giới hạn cho số vòng lặp, số bước workflow và số phần tử cần xử lý.
- Giới hạn số lần parse/serialize hoặc chuyển đổi định dạng trên một request.
- Dùng thư viện có timeout hoặc khả năng hủy cho tác vụ tính toán dài.
- Không chạy tác vụ CPU-bound trên thread xử lý request nếu thời gian thực thi có thể kéo dài.

### 5.2 CPU limit trong container

Trong môi trường container, CPU request/reservation và CPU limit có ý nghĩa khác nhau tùy nền tảng. Reservation giúp scheduler phân bổ năng lực; limit có thể giới hạn thời gian CPU mà container được sử dụng trong một chu kỳ, dẫn tới throttling khi vượt ngưỡng. CPU limit quá thấp có thể làm latency tăng và timeout, ngay cả khi ứng dụng không có lỗi logic.

Không đặt CPU limit chỉ dựa trên mức sử dụng trung bình. Đo peak, burst, số replica, số worker và thời gian throttling. Theo dõi CPU usage, throttled time/periods, run queue và latency p95/p99.

### 5.3 Phân biệt CPU-bound và I/O-bound

Tác vụ CPU-bound thường cần giới hạn số worker gần với năng lực CPU thực tế. Tác vụ I/O-bound có thể dùng nhiều worker hơn vì phần lớn thời gian chờ network/database, nhưng vẫn cần giới hạn connection và memory. Dùng một thread pool chung cho mọi loại công việc dễ khiến tác vụ chậm ở một dependency chiếm hết worker của các luồng khác.

Tách executor hoặc bulkhead theo loại công việc: xử lý request, export, ảnh, gọi dependency và tác vụ nền. Mỗi pool cần queue hữu hạn, concurrency hữu hạn và chính sách từ chối rõ ràng.

## 6. Bảo vệ memory

Memory có thể tăng theo số request đồng thời, kích thước body, số object được tải, buffer, response, cache và queue. Một request lớn đơn lẻ có thể gây OOM; nhiều request vừa phải chạy đồng thời cũng có thể vượt giới hạn.

### 6.1 Kiểm soát allocation

- Dùng streaming cho file và response lớn.
- Tránh đọc toàn bộ bảng hoặc file vào collection trong heap.
- Giới hạn page size, batch size và số object lồng nhau.
- Không giữ request/response body trong log hoặc trace.
- Đặt giới hạn cache size và TTL; tránh cache không giới hạn.
- Giới hạn số tác vụ đồng thời có memory footprint lớn.
- Dọn buffer, temporary file và object tham chiếu sau khi hoàn tất.

### 6.2 Buffer và queue cũng tiêu thụ memory

Một queue in-memory chứa 10.000 tác vụ, mỗi tác vụ giữ payload 1 MB, có thể chiếm hàng GB trước khi tính overhead của object và runtime. Vì vậy, giới hạn queue theo số lượng đơn thuần có thể không đủ; cân nhắc giới hạn cả tổng byte và kích thước từng message.

Không đưa payload file lớn vào queue. Thay bằng object reference có ACL, tenant context, checksum và TTL; worker tải nội dung từ storage sau khi xác minh quyền.

### 6.3 Memory limit và OOM

Memory limit của container có thể khiến process bị OOM kill khi vượt ngưỡng. JVM heap không phải toàn bộ memory của container: còn có metaspace, thread stack, direct buffer, native library, TLS buffer và memory của agent. Đặt heap max thấp hơn container limit với headroom phù hợp và đo trên tải thật.

Theo dõi heap, non-heap, direct memory, GC pause, allocation rate, RSS/container working set và OOM events. Heap còn trống không bảo đảm container còn đủ memory.

### 6.4 Giới hạn payload trước khi deserialize

Nếu framework deserialize JSON thành object graph trước khi kiểm tra số phần tử hoặc độ sâu, memory đã bị tiêu thụ. Giới hạn body ở gateway/server connector, cấu hình parser depth/string/number limits và dùng streaming parser cho dữ liệu lớn. Validation nghiệp vụ sau deserialize vẫn cần thiết nhưng không thay thế giới hạn ở parser.

## 7. Giới hạn connection

Connection là tài nguyên hữu hạn ở database, HTTP client, cache, message broker, file descriptor và socket. Mỗi request có thể giữ nhiều connection hoặc giữ một connection trong thời gian dài.

### 7.1 Database connection pool

Connection pool tái sử dụng kết nối để tránh chi phí tạo connection liên tục. Pool phải có:

- Maximum pool size phù hợp với giới hạn connection của database và tổng số replica.
- Connection acquisition timeout để request không chờ vô hạn.
- Idle timeout, max lifetime và keepalive theo cấu hình database/network.
- Query/transaction timeout để không giữ connection quá lâu.
- Leak detection hoặc metric về connection đang active, idle và pending.

Tổng connection tiềm năng phải tính trên tất cả replica và worker:

\[
\text{Tổng connection tối đa}
= \text{số replica} \times \text{pool size mỗi replica}
+ \text{connection của job/worker}
\]

Ví dụ, 8 replica với pool tối đa 15 connection có thể tạo 120 connection, chưa tính migration, monitoring, admin và worker. Pool size lớn hơn không tự làm hệ thống nhanh hơn; nó có thể khiến database quá tải và tăng contention.

Không giữ connection trong lúc chờ gọi API bên ngoài, gửi email hoặc xử lý file. Hoàn tất truy vấn/transaction rồi mới thực hiện I/O chậm nếu nghiệp vụ cho phép.

### 7.2 HTTP client connection pool

Khi gọi dependency, giới hạn:

- Tổng connection và connection mỗi host.
- Số request đang chạy đồng thời.
- Thời gian chờ lấy connection từ pool.
- Connect timeout, TLS handshake timeout và response timeout.
- Số connection idle và thời gian giữ keep-alive.

Không tạo HTTP client mới cho từng request nếu thư viện yêu cầu tái sử dụng pool. Ngược lại, một pool dùng chung không giới hạn có thể cho một dependency chiếm hết connection. Tách pool theo dependency hoặc nhóm nghiệp vụ có thể tạo bulkhead.

### 7.3 File descriptor và socket

Mỗi socket, file và một số tài nguyên hệ điều hành sử dụng file descriptor. Kết nối rò rỉ, response body không được đóng hoặc file tạm không được giải phóng có thể làm cạn giới hạn process. Dùng try-with-resources hoặc cơ chế close tương đương; kiểm tra mọi nhánh lỗi và cancellation.

Theo dõi số descriptor, socket trạng thái CLOSE_WAIT/TIME_WAIT, connection reset và lỗi “too many open files”. Không tăng giới hạn hệ điều hành để che một connection leak.

## 8. Concurrency và bulkhead

Concurrency limit bảo đảm số công việc đang thực thi không vượt năng lực hệ thống hoặc dependency. Có thể áp dụng theo:

- Toàn hệ thống: bảo vệ tổng CPU, memory và database.
- Dependency: bảo vệ từng database/API bên ngoài.
- Tenant: bảo đảm công bằng và giới hạn ảnh hưởng giữa khách hàng.
- User/API key: ngăn một principal chiếm toàn bộ tài nguyên tenant.
- Endpoint/job type: tách tác vụ nặng khỏi request nhẹ.

Ví dụ, hệ thống có thể cho mỗi tenant tối đa 3 báo cáo đang chạy, toàn hệ thống tối đa 40 báo cáo, trong khi API đọc hồ sơ vẫn dùng pool riêng. Các con số thực tế phải dựa trên benchmark, không lấy ví dụ làm mặc định.

### 8.1 Semaphore và admission control

Semaphore giới hạn số tác vụ đồng thời. Trước khi bắt đầu công việc, hệ thống thử lấy permit; nếu không có permit trong thời gian cho phép, từ chối hoặc xếp hàng có giới hạn. Permit phải được giải phóng trong mọi trường hợp, kể cả exception, timeout và cancellation.

Admission control quyết định có nhận thêm công việc hay không dựa trên năng lực hiện tại. Nó có thể xét queue depth, active worker, database pool pending, CPU throttling và trạng thái dependency. Từ chối sớm giúp giữ hệ thống hoạt động ổn định hơn việc nhận tất cả rồi để chúng timeout.

### 8.2 Bulkhead

Bulkhead tách tài nguyên thành các pool độc lập để lỗi hoặc tải cao ở một luồng không lan sang luồng khác. Ví dụ:

~~~text
API requests
  |-- read pool ------> database read workload
  |-- write pool -----> database write workload
  |-- export pool ----> bounded export workers + queue
  |-- notification ---> bounded notification workers
  |-- external API ---> per-provider connection pool
~~~

Tách pool cần dựa trên tài nguyên thật. Nếu tất cả pool vẫn dùng cùng database và tổng connection vượt khả năng DB, bulkhead ở application chưa giải quyết được nút thắt. Đặt budget tổng và theo dõi từng pool cùng nhau.

## 9. Queue hữu hạn và backpressure

Queue giúp tách tốc độ nhận request khỏi tốc độ xử lý, nhưng queue không tạo thêm năng lực xử lý. Nếu producer gửi nhanh hơn consumer trong thời gian dài, queue sẽ tăng cho đến khi đầy hoặc chiếm hết storage/memory.

### 9.1 Luôn đặt queue capacity

Giới hạn nên xét:

- Số message tối đa.
- Tổng dung lượng byte và kích thước từng message.
- Thời gian message được phép nằm chờ.
- Số message đang được worker xử lý.
- Số lần retry và thời gian lưu dead-letter.
- Giới hạn theo tenant, loại công việc và toàn hệ thống.

Queue in-memory cần giới hạn chặt vì payload tiêu thụ heap. Queue bền vững ngoài process vẫn cần quota storage, retention, partition và kiểm soát số consumer.

### 9.2 Backpressure

Backpressure truyền tín hiệu ngược khi consumer không theo kịp producer. Tùy kiến trúc, có thể:

- Tạm ngừng nhận message hoặc giảm prefetch.
- Giảm tốc độ producer.
- Từ chối request mới với mã phù hợp.
- Trả 202 chỉ sau khi tác vụ đã được ghi bền vững vào queue.
- Xếp hàng theo tenant và áp dụng quota/fairness.
- Giảm mức ưu tiên hoặc tắt tác vụ không thiết yếu.

Không trả 202 Accepted khi chỉ mới giữ task trong bộ nhớ dễ mất. API cần xác định thời điểm “đã chấp nhận”: message đã được broker xác nhận lưu bền vững hoặc job record đã commit.

### 9.3 Ước lượng queue bằng Little’s Law

Trong hệ thống ổn định, định luật Little mô tả:

\[
L = \lambda \times W
\]

Trong đó L là số công việc trung bình trong hệ thống, λ là tốc độ đến trung bình và W là thời gian trung bình một công việc ở trong hệ thống. Nếu có 20 job/giây và thời gian từ lúc vào đến lúc hoàn tất là 5 giây, số job trung bình trong hệ thống khoảng 100.

Đây là quan hệ trung bình trong điều kiện ổn định, không phải công thức đặt capacity tối đa hoặc dự đoán spike. Khi tốc độ đến vượt tốc độ xử lý, hệ thống không ổn định và queue tiếp tục tăng. Cần benchmark burst, thời gian xử lý p95/p99 và khả năng phục hồi sau spike.

### 9.4 Công bằng giữa tenant

Một queue chung có thể bị một tenant chiếm hết slot. Cân nhắc:

- Queue hoặc partition theo tenant khi số lượng tenant và hạ tầng cho phép.
- Per-tenant concurrency và quota.
- Weighted fair scheduling hoặc round-robin giữa tenant.
- Giới hạn số job chờ và đang chạy của một tenant.
- Ưu tiên tác vụ theo SLA, nhưng tránh starvation cho nhóm ưu tiên thấp.

Không cho client tự đặt priority hoặc routing key tùy ý. Server phải xác định priority từ plan/quyền nghiệp vụ đã xác thực.

## 10. Timeout, deadline và cancellation

Timeout giới hạn thời gian một thao tác giữ tài nguyên. Cần phân biệt:

- Connection timeout: thời gian thiết lập kết nối.
- Pool acquisition timeout: thời gian chờ lấy connection.
- Read/response timeout: thời gian chờ dữ liệu từ dependency.
- Query timeout: thời gian database thực thi truy vấn.
- Request deadline: tổng thời gian cho phép xử lý request.
- Job deadline: thời gian tối đa một tác vụ nền được chạy.

Deadline nên được truyền xuyên các service để bước phía sau biết còn bao nhiêu thời gian. Timeout của dependency phải nhỏ hơn phần deadline còn lại, có chừa thời gian xử lý lỗi và phản hồi. Không đặt mọi timeout bằng nhau vì request có thể hết hạn trước khi tầng sâu hơn dừng công việc.

Khi client ngắt kết nối hoặc deadline hết, hủy các tác vụ không còn cần thiết nếu thư viện hỗ trợ. Đảm bảo cancellation giải phóng connection, semaphore permit, buffer và file tạm. Client timeout không tự động có nghĩa server hoặc dependency đã dừng xử lý.

Với thao tác có side effect, timeout tạo kết quả không rõ. Dùng idempotency key hoặc operation ID để client truy vấn trạng thái thay vì gửi lại thao tác và tạo giao dịch trùng.

## 11. Retry budget và bảo vệ dependency

Retry có thể phục hồi lỗi tạm thời nhưng cũng nhân tải khi hệ thống đang quá tải. Nếu client, gateway, application và SDK đều retry 3 lần, một request ban đầu có thể tạo nhiều lần thử ở mỗi tầng.

Quy tắc:

- Chỉ retry lỗi có khả năng phục hồi; không retry validation, authorization hoặc quota exceeded.
- Giới hạn tổng số lần retry và tổng thời gian retry cho một request/job.
- Dùng exponential backoff và jitter.
- Tôn trọng Retry-After khi phù hợp nhưng không vượt deadline.
- Đặt circuit breaker để ngừng gọi dependency đang lỗi liên tục.
- Dùng bulkhead để một dependency không chiếm hết worker/connection.
- Dùng idempotency key cho thao tác có side effect.
- Không retry khi không biết thao tác trước đã hoàn thành hay chưa nếu không có cơ chế đối soát.

Retry budget nên được tính theo operation hoặc dependency, không chỉ theo từng lần gọi thư viện. Giám sát số lần gọi dependency trên mỗi request nghiệp vụ để phát hiện fan-out hoặc retry amplification.

## 12. Giới hạn theo tenant và chống noisy neighbor

Trong multi-tenant API, một tenant có thể dùng nhiều user, API key và IP. Giới hạn theo IP hoặc user riêng lẻ không bảo đảm tenant không vượt quá phần tài nguyên được phân bổ.

Nên kết hợp:

| Phạm vi | Mục tiêu |
|---|---|
| Global | Bảo vệ tổng năng lực service và dependency |
| Tenant | Ngăn một khách hàng chiếm tài nguyên dùng chung |
| User/client | Kiểm soát ứng dụng hoặc người dùng gây tải bất thường |
| Endpoint/job type | Phản ánh chi phí khác nhau giữa các chức năng |
| Dependency | Không vượt connection/quota của nhà cung cấp |

Quota tenant phải lấy từ tenant context đã xác minh. Không cho client gửi plan, tier hoặc quota limit của chính họ. Khi tenant vượt giới hạn, từ chối hoặc trì hoãn trong phạm vi tenant đó; không làm giảm năng lực của tenant khác.

Cần phân biệt quota hợp đồng với giới hạn an toàn toàn hệ thống. Tenant trả phí cao hơn có thể được cấp throughput hoặc concurrency lớn hơn nhưng vẫn không được vượt capacity bảo vệ database, broker và dependency. Có thể dùng weighted allocation nhưng phải có global ceiling.

## 13. Xử lý quá tải và graceful degradation

Khi hệ thống gần quá tải, cần có chiến lược giảm tải có chủ đích:

- Từ chối sớm request mới thay vì giữ connection rồi timeout hàng loạt.
- Tắt hoặc trì hoãn tính năng không thiết yếu như báo cáo phụ, preview hoặc analytics.
- Trả dữ liệu cache nếu phù hợp và không vi phạm freshness/quyền.
- Giảm kích thước batch hoặc số kết quả.
- Hạ concurrency tới dependency đang quá tải.
- Dừng retry và mở circuit breaker.
- Giữ capacity cho health check, logout, thu hồi token và luồng nghiệp vụ quan trọng.
- Dùng load shedding theo tenant/endpoint/priority.

Không graceful-degrade bằng cách bỏ qua authorization, validation hoặc kiểm tra tenant. Khi thiếu năng lực, từ chối an toàn tốt hơn xử lý thiếu kiểm soát.

Health endpoint cần phản ánh khả năng phục vụ theo định nghĩa rõ. Readiness có thể đánh dấu instance không nhận traffic khi không đủ năng lực; liveness không nên thất bại chỉ vì một dependency tạm thời chậm nếu điều đó tạo restart storm. Phân biệt tình trạng process sống, instance sẵn sàng và dependency khỏe.

## 14. Ví dụ cấu hình giới hạn ở application

Ví dụ minh họa một executor hữu hạn trong Java:

~~~java
ThreadPoolExecutor exportExecutor = new ThreadPoolExecutor(
    4,
    4,
    0L,
    TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(100),
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

Pool trên có 4 worker và queue tối đa 100 tác vụ. Khi worker bận và queue đầy, submission bị từ chối. Application cần bắt rejection để trả lỗi hoặc thông báo task capacity exhausted; không dùng CallerRunsPolicy một cách tùy tiện trên request thread vì có thể khiến request nhẹ bị kéo vào chạy export nặng.

Ví dụ cấu hình giới hạn request trong Spring Boot cần được áp dụng ở server connector, gateway hoặc filter phù hợp với stack đang dùng. Tên property phụ thuộc server và phiên bản; không sao chép một key cấu hình mà chưa kiểm tra tài liệu runtime. Dù cấu hình ở edge, application vẫn cần giới hạn số item, page size, parser depth và công việc thực tế.

Ví dụ một request service dùng deadline và timeout:

~~~java
public Report createReport(
    TenantContext tenant,
    ReportRequest request,
    Duration remaining
) {
    Duration dbTimeout = min(remaining, Duration.ofSeconds(2));

    return transactionTemplate.execute(status -> {
        reportRepository.setQueryTimeout(dbTimeout);
        return reportService.buildForTenant(tenant.id(), request);
    });
}
~~~

Đây là pseudo-code để minh họa cách truyền deadline; API thực tế của transaction và repository phụ thuộc framework. Cần bảo đảm query timeout được áp dụng thật và transaction không giữ connection trong lúc gọi dịch vụ ngoài.

## 15. Ví dụ thiết kế endpoint export bất đồng bộ

Giả sử POST /reports/exports tạo báo cáo có thể quét nhiều bảng và sinh file CSV. Endpoint này không nên giữ request thread và database connection trong suốt thời gian tạo file.

Luồng an toàn:

1. Xác thực principal và xác minh quyền trên báo cáo/dataset trong tenant.
2. Validate khoảng thời gian, filter, cột được export và số row tối đa.
3. Ước lượng công việc và kiểm tra quota, budget, per-tenant concurrency.
4. Admission control kiểm tra global worker/queue capacity.
5. Ghi job record và enqueue message bền vững trong cùng quy trình có thể phục hồi.
6. Chỉ trả 202 sau khi job đã được chấp nhận bền vững, kèm operation ID.
7. Worker dựng tenant context mới, tải dữ liệu theo tenant scope và xử lý theo batch.
8. Mỗi batch có query timeout, giới hạn row và deadline.
9. Ghi file vào object storage theo tenant namespace, gắn ACL và TTL.
10. Cập nhật trạng thái job, giải phóng concurrency/quota reservation và gửi thông báo qua pool riêng.
11. Khi quá hạn, hủy job, dọn file tạm và giải phóng tài nguyên.

Nếu queue đầy, trả lỗi có thể retry sau hoặc hướng dẫn người dùng thử lại; không giữ task trong memory vô hạn. Nếu client gửi cùng idempotency key, trả lại operation ID hiện có thay vì tạo nhiều báo cáo.

## 16. Phản hồi API khi vượt giới hạn

Chọn status code theo nguyên nhân:

| Tình huống | Phản hồi thường phù hợp |
|---|---|
| Vượt rate limit hoặc quota sử dụng | 429 Too Many Requests |
| Request body vượt giới hạn | 413 Content Too Large |
| Nội dung không hợp lệ hoặc vượt giới hạn schema | 400 Bad Request hoặc 422 theo contract |
| Queue/global capacity tạm thời hết | 503 Service Unavailable |
| Dependency timeout | 504 Gateway Timeout ở gateway hoặc lỗi tương ứng theo API contract |
| Request deadline của client/server hết | 408 hoặc lỗi timeout theo ngữ cảnh; không dùng tùy tiện |

Với 429 hoặc 503, có thể gửi Retry-After nếu biết thời điểm hợp lý. Không cung cấp chi tiết cấu hình nội bộ, số connection đang dùng hoặc ngưỡng chống lạm dụng cho người gọi không có quyền.

Ví dụ:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 15
Content-Type: application/json
~~~

~~~json
{
  "code": "CAPACITY_EXCEEDED",
  "message": "Hệ thống đang bận. Vui lòng thử lại sau.",
  "retryAfterSeconds": 15
}
~~~

Client nên backoff có jitter, tôn trọng Retry-After và không retry liên tục. API cần phân biệt request bị từ chối trước khi nhận tác vụ với tác vụ đã được chấp nhận và đang xử lý.

## 17. Giám sát tài nguyên và phát hiện lạm dụng

Đo theo service, instance, endpoint, tenant, dependency và job type:

**CPU**

- CPU usage, throttling, run queue và thời gian xử lý CPU-bound.
- Latency p50/p95/p99 theo endpoint.
- Tỷ lệ request bị từ chối do admission control.

**Memory**

- Heap, non-heap, direct memory, RSS và container working set.
- Allocation rate, GC pause, số lần full GC và OOM kill.
- Kích thước request/response và queue payload bytes.

**Connection**

- Active/idle/pending connection trong từng pool.
- Thời gian chờ lấy connection, connection timeout và leak.
- DB query duration, transaction duration, lock wait và socket/file descriptor.

**Queue và worker**

- Queue depth, queue bytes, tuổi message lâu nhất và enqueue/dequeue rate.
- Active worker, worker utilization, task duration và rejection count.
- Retry, dead-letter, cancellation và job timeout.

**Dependency**

- Request rate, concurrency, latency, error rate và retry amplification.
- Circuit breaker state, connection pool pending và quota nhà cung cấp.

Đặt cảnh báo theo xu hướng và ngưỡng có ý nghĩa. Ví dụ queue tăng liên tục dù worker đã bận tối đa, DB pool pending tăng, CPU throttling trùng với p99 tăng hoặc một tenant chiếm phần lớn worker. Không chỉ cảnh báo khi CPU đạt 100%; nhiều sự cố bắt đầu từ connection wait hoặc queue age.

Log cần correlation ID, tenant ID nội bộ, endpoint, operation ID, resource budget và quyết định admission. Không log token, body nhạy cảm hoặc toàn bộ payload queue. Với metric, tránh dùng user ID/object ID không giới hạn làm label vì cardinality cao có thể làm hệ thống giám sát quá tải.

## 18. Kiểm thử giới hạn và tình huống quá tải

Kiểm thử phải xác nhận hệ thống từ chối đúng lúc, giải phóng tài nguyên và phục hồi sau spike.

| Loại test | Kịch bản | Điều cần xác minh |
|---|---|---|
| Request boundary | Body ngay dưới, bằng và vượt giới hạn | Từ chối trước khi cấp phát lớn |
| Complexity | Page size, filter, depth và batch vượt ngưỡng | Không tạo truy vấn hoặc object graph quá lớn |
| CPU saturation | Nhiều tác vụ tính toán đồng thời | Admission control và pool riêng hoạt động |
| Memory pressure | Upload lớn, response lớn, nhiều request song song | Không OOM; buffer/queue bị giới hạn |
| DB pool exhaustion | Giữ connection chậm hoặc tạo nhiều query | Acquisition timeout và pending limit có hiệu lực |
| HTTP pool exhaustion | Dependency chậm hoặc ngắt kết nối | Pool không tăng vô hạn; circuit breaker hoạt động |
| Queue full | Producer nhanh hơn consumer | Queue không vượt capacity; producer nhận backpressure |
| Tenant fairness | Tenant A gửi nhiều job hơn B | B vẫn có phần năng lực theo policy |
| Retry storm | Dependency trả 5xx/timeout | Retry budget, backoff và jitter giới hạn khuếch đại |
| Cancellation | Client ngắt hoặc deadline hết | Connection, permit, buffer và file tạm được giải phóng |
| Recovery | Dừng spike rồi theo dõi hệ thống | Queue drain, pool phục hồi và không còn task mồ côi |
| Replica scaling | Tăng số instance | Tổng connection/worker vẫn nằm trong budget toàn hệ thống |

Load test cần chạy qua gateway và các dependency thật hoặc mô phỏng có hành vi tương đương. Chỉ benchmark method trong process không chứng minh được giới hạn connection, queue và database hoạt động đúng.

## 19. Các lỗi thiết kế thường gặp

1. **Chỉ có rate limit:** request ít nhưng mỗi request tiêu thụ tài nguyên rất lớn.
2. **Queue không giới hạn:** chuyển quá tải sang memory hoặc storage.
3. **Pool connection quá lớn:** nhiều replica cộng lại vượt khả năng database.
4. **Giữ DB connection khi gọi dependency:** connection bị chiếm trong lúc chờ network.
5. **Không có timeout:** request và worker giữ tài nguyên vô thời hạn.
6. **Retry ở nhiều tầng:** số lần gọi thực tế tăng theo cấp số nhân.
7. **Dùng chung một executor:** export nặng chiếm worker của request nhẹ.
8. **Chỉ đặt container memory limit:** không kiểm soát body, queue và allocation bên trong ứng dụng.
9. **Chỉ kiểm tra kích thước sau deserialize:** memory đã bị cấp phát trước khi từ chối.
10. **Không tính tổng replica:** mỗi instance có vẻ an toàn nhưng tổng pool vượt giới hạn.
11. **Không giới hạn theo tenant:** một khách hàng gây noisy neighbor.
12. **Trả 202 trước khi enqueue bền vững:** job có thể mất sau khi API báo đã nhận.
13. **Không xử lý cancellation:** client đã bỏ request nhưng server vẫn tiếp tục tiêu thụ tài nguyên.
14. **Chỉ theo dõi CPU:** bỏ sót pool pending, queue age, memory pressure và dependency latency.

## 20. Quy trình thiết kế resource limit cho endpoint

Với mỗi endpoint hoặc job:

1. Vẽ đường đi request và liệt kê CPU, memory, DB connection, HTTP connection, queue, storage và dependency.
2. Đặt giới hạn request size, số item và độ phức tạp trước khi xử lý nặng.
3. Ước lượng chi phí bình thường và cực đại cho một request/job.
4. Chọn rate limit, quota, concurrency, queue capacity và timeout phù hợp.
5. Tính tổng connection/worker trên tất cả replica và workload nền.
6. Tách pool/bulkhead theo dependency hoặc loại công việc có đặc tính khác nhau.
7. Thiết kế admission control, backpressure và hành vi khi queue/pool đầy.
8. Đặt retry budget, circuit breaker, cancellation và idempotency.
9. Áp dụng quota theo tenant và global ceiling để chống noisy neighbor.
10. Xác định graceful degradation và status code/Retry-After.
11. Viết load/chaos test cho saturation, pool exhaustion, queue full và recovery.
12. Thiết lập metric, alert, audit và review ngưỡng theo tải thực tế.

## 21. Checklist rà soát

- [ ] Mỗi endpoint có giới hạn kích thước và độ phức tạp đầu vào.
- [ ] Có giới hạn page size, batch, query depth, row count và response size.
- [ ] CPU-bound và I/O-bound workload được phân loại và giới hạn phù hợp.
- [ ] Memory, heap, direct buffer, cache, queue payload và file tạm có budget.
- [ ] DB/HTTP connection pool có max size, acquisition timeout và metric.
- [ ] Tổng connection được tính trên mọi replica, worker và tác vụ vận hành.
- [ ] Có concurrency limit toàn hệ thống, theo dependency và theo tenant.
- [ ] Queue hữu hạn theo count/bytes; có backpressure và dead-letter policy.
- [ ] Timeout/deadline được truyền xuyên service; cancellation giải phóng tài nguyên.
- [ ] Retry budget, exponential backoff, jitter, circuit breaker và idempotency được áp dụng.
- [ ] Admission control và graceful degradation không bỏ qua authorization/validation.
- [ ] Tenant quota và global capacity ceiling ngăn noisy neighbor.
- [ ] 429/413/503/504 và Retry-After phản ánh đúng trạng thái.
- [ ] Có load test cho CPU, memory, connection, queue, tenant fairness và recovery.
- [ ] Metric/alert theo dõi pool pending, queue age, OOM, throttling và dependency amplification.

Giới hạn CPU, memory, connection và queue cần được thiết kế như một ngân sách xuyên suốt request, service, dependency và worker. Request size limit ngăn đầu vào quá lớn; timeout giới hạn thời gian giữ tài nguyên; pool và concurrency limit kiểm soát số việc đang chạy; queue hữu hạn cùng backpressure điều tiết tốc độ; tenant quota giữ công bằng; metric và load test xác nhận các giới hạn thực sự hoạt động. Khi các lớp này phối hợp, API có thể từ chối tải vượt năng lực một cách có kiểm soát và giữ dịch vụ ổn định cho các tenant khác.
