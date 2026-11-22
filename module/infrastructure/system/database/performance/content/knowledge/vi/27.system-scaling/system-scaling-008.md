# Quản lý hàng đợi, giới hạn đồng thời và áp lực ngược khi quá tải

Khi số request đến database vượt quá khả năng xử lý, thời gian chờ tăng nhanh. Connection pool đầy, worker giữ connection lâu hơn, truy vấn xếp hàng, transaction tranh khóa và bộ nhớ dành cho request chờ tiếp tục tăng. Nếu ứng dụng cứ nhận thêm việc hoặc retry ngay khi thất bại, quá tải có thể lan từ database sang toàn bộ dịch vụ.

Trong phạm vi **DATABASE_PERFORMANCE**, mở rộng hệ thống cần dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Quản lý hàng đợi, giới hạn đồng thời và áp lực ngược là lớp điều phối để giữ lượng công việc đang hoạt động trong giới hạn mà database có thể phục vụ. Hàng đợi hấp thụ burst ngắn; giới hạn đồng thời bảo vệ tài nguyên; backpressure báo cho upstream giảm tốc hoặc từ chối công việc; load shedding loại bỏ hoặc trì hoãn phần tải có thể hy sinh.

Bài học này giải thích cách hàng đợi hình thành, cách ước lượng năng lực phục vụ, thiết kế queue có giới hạn, điều tiết số worker và connection, truyền áp lực ngược qua các tầng, xử lý retry/circuit breaker, ưu tiên workload và kiểm chứng hành vi khi quá tải.

## 1. Hàng đợi xuất hiện khi nào?

Một request database thường đi qua nhiều tầng:

~~~text
Client
  |
  v
API gateway / HTTP server
  |
  v
Application request queue
  |
  v
Worker / scheduler
  |
  v
Connection pool
  |
  v
Database admission / lock / execution
  |
  v
Storage and log
~~~

Mỗi tầng có thể có hàng đợi riêng. Request có thể chờ ở HTTP server, thread pool, semaphore, connection pool, database lock hoặc storage queue. Nếu chỉ quan sát một queue, ta có thể bỏ sót nơi thời gian chờ thực sự tích tụ.

Ví dụ, một API có 300 request đồng thời. Thread pool đang chạy 100 request, 200 request chờ. Trong số 100 request đang chạy, chỉ 20 request đã lấy được connection; 80 request còn lại đang chờ connection pool. Database có thể chỉ chạy 15 truy vấn tại một thời điểm và 5 truy vấn đang chờ khóa. Tổng thời gian phản hồi gồm nhiều khoảng chờ khác nhau.

### Hàng đợi không tự làm tăng năng lực

Queue giữ công việc đến khi worker có thể xử lý. Nó có thể làm phẳng burst trong thời gian ngắn và tách tốc độ nhận việc khỏi tốc độ thực thi. Nhưng queue không tăng CPU, IOPS, khả năng ghi log hoặc năng lực xử lý lock của database.

Nếu tốc độ công việc đến liên tục cao hơn tốc độ xử lý, queue sẽ tăng mãi nếu không có giới hạn. Một queue vô hạn chỉ trì hoãn thời điểm thất bại và thường biến overload thành latency, memory pressure hoặc timeout diện rộng.

## 2. Các đại lượng cơ bản của queueing

Để điều khiển hàng đợi, cần phân biệt:

- **Arrival rate (λ):** tốc độ công việc đến, thường tính request/giây hoặc job/giây.
- **Service rate (μ):** tốc độ một worker hoặc hệ thống hoàn tất công việc.
- **Concurrency (c):** số công việc được xử lý đồng thời.
- **Queue depth:** số công việc đang chờ.
- **Queue wait time:** thời gian một công việc nằm trong hàng đợi trước khi bắt đầu.
- **Service time:** thời gian worker thực sự xử lý công việc.
- **End-to-end latency:** tổng thời gian từ lúc nhận request đến khi hoàn tất.
- **Utilization:** tỷ lệ năng lực phục vụ đang được sử dụng.

Với một worker có tốc độ phục vụ trung bình μ, hệ thống ổn định cần tốc độ đến trung bình nhỏ hơn năng lực phục vụ. Với c worker tương đương, năng lực lý thuyết có thể gần c × μ, nhưng database thường có tranh chấp CPU, I/O, buffer, lock và log nên năng lực không tăng tuyến tính theo số worker.

### Định luật Little

Trong một hệ thống ổn định:

~~~text
L = λ × W
~~~

Trong đó:

- L là số công việc trung bình đang ở trong hệ thống.
- λ là throughput hoàn tất trung bình.
- W là thời gian trung bình một công việc ở trong hệ thống.

Với riêng hàng đợi, có thể dùng:

~~~text
Lq = λ × Wq
~~~

Trong đó Lq là số công việc chờ trung bình và Wq là thời gian chờ trung bình.

Ví dụ, nếu một hệ thống hoàn tất 200 request/giây và mỗi request ở trong hệ thống trung bình 0,25 giây, số request trung bình đang hoạt động hoặc chờ trong hệ thống xấp xỉ 50. Đây là quan hệ mô tả hệ thống ổn định; nó không dự báo chính xác p99 hoặc thời gian chờ trong giai đoạn overload.

### Ví dụ queue tăng khi quá tải

Giả sử database và ứng dụng cùng nhau chỉ xử lý ổn định 800 job/giây, nhưng upstream gửi 1.000 job/giây. Chênh lệch 200 job/giây tích tụ vào queue. Nếu queue còn 2.000 slot trống và không có cơ chế từ chối, queue có thể đầy sau khoảng 10 giây:

~~~text
Tốc độ đến       = 1.000 job/giây
Tốc độ hoàn tất  =   800 job/giây
Tốc độ tăng queue =   200 job/giây
Dung lượng trống = 2.000 job

Thời gian đầy xấp xỉ = 2.000 / 200 = 10 giây
~~~

Khi queue đầy, hệ thống cần quyết định từ chối, trì hoãn ở upstream, lưu vào durable queue hoặc giảm tải. Tiếp tục nhận thêm sẽ chuyển vấn đề sang một tầng khác.

## 3. Vì sao latency tăng mạnh gần mức bão hòa?

Khi hệ thống sử dụng gần hết năng lực, một biến động nhỏ về thời gian xử lý cũng có thể làm queue tăng. Một truy vấn chậm giữ connection lâu hơn; request sau phải chờ; timeout và retry tạo thêm việc; số request đồng thời tiếp tục tăng.

Trong nhiều hệ thống queueing, latency tăng phi tuyến khi utilization tiến gần 100%. Vì vậy, chạy database ở mức CPU hoặc connection saturation liên tục không để lại headroom cho burst, checkpoint, vacuum, backup, cache miss hay query bất thường.

### Average không phản ánh tail latency

Một số request hoàn thành rất nhanh nhưng một số khác chờ lock hoặc I/O rất lâu. Trung bình có thể trông chấp nhận được trong khi p95/p99 vượt SLO.

Hãy theo dõi:

- p50: trải nghiệm điển hình.
- p95/p99: phần request chậm.
- Queue wait riêng biệt với service time.
- Thời gian lấy connection.
- Thời gian chờ lock và I/O.
- Tỷ lệ timeout/rejection.

Nếu service time không đổi nhưng queue wait tăng, bottleneck có thể nằm ở admission hoặc concurrency. Nếu queue wait thấp nhưng service time tăng, cần điều tra database execution, lock, CPU, I/O hoặc storage.

## 4. Phân biệt queue có giới hạn và queue không giới hạn

Một queue cần có giới hạn rõ ràng theo số phần tử, tổng byte hoặc chi phí công việc.

### Unbounded queue

Queue không giới hạn dễ triển khai nhưng có thể:

- Giữ quá nhiều request và object trong heap.
- Tăng GC pause và memory pressure.
- Kéo dài thời gian chờ đến mức request hết deadline trước khi chạy.
- Giữ dữ liệu lỗi thời không còn giá trị.
- Che giấu việc arrival rate đang vượt service rate.
- Làm hệ thống mất khả năng phục hồi sau overload.

### Bounded queue

Queue có giới hạn dừng nhận thêm công việc khi đạt capacity. Khi đầy, hệ thống phải áp dụng chính sách:

- Reject ngay với lỗi có thể retry sau.
- Block producer trong một khoảng ngắn nếu upstream có thể chịu backpressure.
- Ghi vào durable queue nếu công việc được chấp nhận để xử lý sau.
- Shed hoặc hạ ưu tiên công việc không thiết yếu.
- Chuyển sang xử lý đồng bộ có giới hạn nếu thiết kế cho phép.

Không có một chính sách đúng cho mọi loại request. Ghi thanh toán, gửi email, báo cáo và truy vấn dashboard có yêu cầu mất dữ liệu, deadline và ưu tiên khác nhau.

### Giới hạn cả số lượng và kích thước

100 job nhỏ và 100 job chứa payload 20 MB có mức tiêu thụ bộ nhớ rất khác nhau. Nếu payload lớn, cần giới hạn theo byte, kích thước batch, số dòng hoặc ước lượng chi phí.

Với database workload, một job có thể đọc một dòng hoặc scan hàng triệu dòng. Queue nên phân loại theo loại công việc và resource budget thay vì coi mọi request có chi phí giống nhau.

## 5. Chọn queue capacity theo deadline và năng lực phục vụ

Queue capacity không nên chọn chỉ vì muốn chứa được nhiều request. Cần liên hệ giới hạn queue với thời gian chờ tối đa mà nghiệp vụ chấp nhận.

Một ước lượng ban đầu:

~~~text
Queue capacity mục tiêu
  ≈ throughput xử lý × thời gian chờ tối đa
~~~

Ví dụ, nếu hệ thống có thể hoàn tất ổn định 500 job/giây và công việc được phép chờ tối đa khoảng 2 giây, queue cỡ 1.000 job là một điểm bắt đầu để thử nghiệm. Con số thực tế cần điều chỉnh theo burst, độ biến thiên service time, số worker và deadline còn lại của request.

### Ước lượng thời gian chờ theo queue depth

Nếu có 600 job đứng trước một job và hệ thống hoàn tất 200 job/giây, thời gian chờ thô có thể xấp xỉ 3 giây nếu không có job mới, service time đồng đều và mọi job cùng loại. Trong thực tế, job có chi phí khác nhau và công việc mới tiếp tục đến, nên cần đo queue age và phân vị thời gian chờ.

### Loại bỏ công việc đã hết deadline

Nếu một request chỉ có deadline 2 giây nhưng đã chờ 2 giây trong queue, thực thi truy vấn lúc này có thể lãng phí database capacity. Hãy truyền deadline hoặc thời gian còn lại vào worker; trước khi bắt đầu, kiểm tra request còn giá trị hay không.

Đối với công việc đã được chấp nhận bền vững như thanh toán hoặc gửi sự kiện, không được âm thầm bỏ chỉ vì client timeout. Cần trạng thái job, idempotency và quy trình tra cứu kết quả.

## 6. Giới hạn đồng thời để bảo vệ database

Concurrency là số thao tác được phép chạy cùng lúc. Tăng concurrency có thể tăng throughput đến một điểm; vượt điểm đó thường làm lock contention, context switching, memory use, connection pressure và I/O queue tăng.

### Vì sao nhiều connection không đồng nghĩa nhiều throughput?

Mỗi connection có thể tạo session state, memory, transaction và hoạt động riêng. Nếu database đã bão hòa CPU hoặc storage, thêm connection chủ yếu làm tăng số request tranh cùng tài nguyên.

Với workload có nhiều khóa nóng, tăng concurrency có thể làm transaction chờ nhau lâu hơn. Một hệ thống chạy 100 query đồng thời chưa chắc nhanh hơn hệ thống chạy 30 query có chọn lọc và thời gian phục vụ ổn định.

### Xác định concurrency limit bằng benchmark

Thử tăng concurrency theo các mức, ví dụ 4, 8, 16, 24, 32 worker. Ở mỗi mức, ghi:

- Throughput hoàn tất.
- p50/p95/p99 service time.
- Queue wait và connection acquisition time.
- CPU, memory, IOPS, storage latency.
- Lock waits, deadlocks và transaction duration.
- Commit latency và log throughput.
- Tỷ lệ timeout và lỗi.

Nếu tăng worker nhưng throughput gần như không tăng trong khi latency và lock wait tăng, đã vượt vùng concurrency có lợi.

### Giới hạn theo loại tài nguyên

Một request có thể đồng thời tiêu thụ connection, CPU, I/O, memory và lock. Có thể cần nhiều giới hạn:

- Tổng request đang xử lý ở API.
- Số query đang chạy tới database.
- Số transaction ghi đồng thời.
- Số báo cáo/scan nặng.
- Số job bulk load hoặc maintenance.
- Số request cho mỗi tenant.

Một semaphore toàn cục đơn giản không thể bảo vệ mọi tài nguyên nếu workload có chi phí rất khác nhau.

## 7. Connection pool là một hàng đợi và một giới hạn concurrency

Connection pool tái sử dụng các connection vật lý để tránh mở kết nối mới cho từng request. Pool có kích thước tối đa và thường có hàng đợi hoặc cơ chế chờ khi tất cả connection đang bận.

Khi pool cạn:

- Request chờ lấy connection.
- Connection acquisition time tăng.
- Request thread bị giữ dù chưa chạy SQL.
- Thread pool có thể đầy.
- Deadline hết trước khi query bắt đầu.

### Không chữa pool saturation bằng cách tăng pool ngay

Trước khi tăng maximum pool size, hãy kiểm tra:

- Connection được giữ bao lâu?
- Transaction có mở quá sớm hoặc đóng quá muộn?
- Có query chậm hoặc lock wait kéo dài?
- Có connection leak hoặc ResultSet chưa đóng?
- Database CPU/IO đã bão hòa chưa?
- Throughput có tăng khi pool lớn hơn không?

Nếu database chỉ xử lý hiệu quả 40 query đồng thời, tăng pool từ 40 lên 200 có thể tạo 160 session chờ và làm latency tệ hơn.

### Cấu hình pool

Các thông số thường cần có:

- Maximum pool size.
- Minimum idle hoặc số connection duy trì.
- Connection acquisition timeout.
- Idle timeout và max lifetime.
- Leak detection hoặc theo dõi connection hold time.
- Validation/keepalive theo nhu cầu môi trường.

Tên cấu hình tùy thư viện pool. Ví dụ HikariCP có các thuộc tính tương ứng, nhưng giá trị phù hợp phải được đo theo database và ứng dụng.

### Giữ transaction ngắn

Lấy connection ngay trước thao tác database, mở transaction khi cần tính nguyên tử, rồi commit/rollback và trả connection sớm. Không giữ connection trong lúc gọi HTTP, chờ message broker hoặc xử lý CPU lâu nếu các bước đó không thuộc transaction database.

## 8. Admission control trước khi truy vấn

Admission control quyết định có cho phép công việc bắt đầu sử dụng tài nguyên hay không. Nó giúp database chỉ nhận số công việc phù hợp với capacity và SLO.

### Kiểm soát ở nhiều tầng

Có thể đặt giới hạn ở:

1. API gateway: rate limit theo client hoặc tenant.
2. Application: bounded executor và semaphore.
3. Workload scheduler: giới hạn job theo loại.
4. Connection pool: giới hạn số connection đồng thời.
5. Database: giới hạn session, statement timeout, resource group hoặc workload management nếu engine hỗ trợ.

Các tầng phải phối hợp. Nếu API nhận 10.000 request rồi để tất cả chờ ở connection pool, admission control đã đặt quá muộn.

### Semaphore cho truy vấn database

Một semaphore có thể giới hạn số query đang được phép đi vào phần xử lý database:

~~~java
Semaphore databaseSlots = new Semaphore(24);

public Result loadOrder(long orderId) throws InterruptedException {
    if (!databaseSlots.tryAcquire(100, TimeUnit.MILLISECONDS)) {
        throw new ServiceBusyException("Database capacity is busy");
    }

    try {
        return repository.loadOrder(orderId);
    } finally {
        databaseSlots.release();
    }
}
~~~

Ví dụ giới hạn 24 thao tác đồng thời và chỉ chờ slot tối đa 100 ms. Giá trị này minh họa; cần lấy từ benchmark. Semaphore phải được release trong finally để tránh mất slot khi có exception.

Nếu repository mở nhiều query song song cho một request, cần tính tổng concurrency thực tế. Một request fan-out thành 10 query có thể tiêu thụ 10 slot, không phải một.

### Đặt timeout theo deadline

Thời gian chờ admission, lấy connection và chạy SQL cần nằm trong tổng deadline của request. Ví dụ:

~~~text
Tổng deadline request:       2.000 ms
Chờ admission tối đa:          100 ms
Chờ connection tối đa:         200 ms
Thực thi SQL tối đa:         1.300 ms
Serialize/response dự phòng:   400 ms
~~~

Đây chỉ là ví dụ phân bổ. Không nên để mỗi tầng dùng timeout độc lập dài hơn tổng deadline. Khi request đã hết thời gian còn lại, không bắt đầu query mới.

## 9. Backpressure là gì?

Backpressure là cơ chế truyền tín hiệu rằng một thành phần đang xử lý chậm hoặc đã hết capacity để thành phần phía trước giảm tốc, dừng gửi thêm hoặc chỉ gửi khi có nhu cầu.

~~~text
Producer
   |
   | gửi công việc
   v
Bounded queue
   |
   v
Worker pool
   |
   v
Database capacity
   |
   +----> Queue đầy / service chậm
              |
              v
       Backpressure signal
              |
              v
     Producer giảm tốc hoặc dừng
~~~

Backpressure hữu ích khi producer và consumer có thể phối hợp. Ví dụ, một pipeline ETL đọc từ nguồn và ghi vào database. Nếu database chỉ ghi được 5.000 dòng/giây, ETL nên giảm tốc đọc hoặc giảm số batch đang bay thay vì tiếp tục nạp vào bộ nhớ.

### Backpressure đồng bộ và bất đồng bộ

- **Synchronous blocking:** producer chờ cho đến khi queue có chỗ. Cách này chỉ phù hợp nếu thread producer có thể chờ mà không làm cạn tài nguyên upstream.
- **Non-blocking rejection:** producer nhận tín hiệu queue đầy và quyết định retry có kiểm soát hoặc trả lỗi.
- **Reactive demand:** consumer yêu cầu một số phần tử; producer chỉ phát theo demand.
- **Broker flow control:** message broker giới hạn số message in-flight hoặc consumer nhận theo credit/prefetch.

Không phải mọi API đều có thể block. Chặn event-loop thread hoặc HTTP acceptor có thể làm toàn bộ dịch vụ ngừng phản hồi. Với mô hình reactive, cần dùng operator và scheduler có hỗ trợ backpressure thay vì chặn tùy tiện.

### Backpressure phải truyền xuyên các tầng

Nếu database chậm nhưng ứng dụng vẫn nhận request không giới hạn, áp lực chỉ chuyển thành connection wait hoặc thread wait. Hãy truyền tín hiệu ngược từ database capacity đến worker, từ worker đến queue, rồi đến producer hoặc client.

Một giới hạn ở tầng cuối không đủ nếu các tầng trước vẫn tích tụ lượng lớn payload hoặc thread.

## 10. Chính sách khi queue đầy

Khi queue đạt giới hạn, hệ thống cần hành vi xác định trước. Không nên để mỗi thành phần tự quyết định.

| Chính sách | Hành vi | Phù hợp khi |
|---|---|---|
| Reject fast | Từ chối ngay | Request đồng bộ có thể thử lại sau |
| Timed wait | Chờ tối đa một khoảng | Producer chịu được chờ ngắn |
| Durable enqueue | Ghi vào broker bền vững | Công việc được chấp nhận để xử lý sau |
| Shed low priority | Bỏ/hoãn việc ít quan trọng | Có thể giảm chất lượng dịch vụ |
| Coalesce | Gộp nhiều việc tương đương | Chỉ cần trạng thái mới nhất |
| Replace stale work | Thay job cũ bằng job mới | Cache refresh hoặc rebuild snapshot |

### Reject fast

Với API đồng bộ, có thể trả 429 khi client vượt quota hoặc 503 khi dịch vụ tạm không có capacity. Có thể trả Retry-After nếu biết khoảng chờ hợp lý. Không gửi một thời gian retry cố định quá ngắn khiến mọi client cùng quay lại.

### Durable enqueue

Nếu hệ thống trả lời rằng job đã được chấp nhận, thông điệp cần được lưu bền vững theo mức bảo đảm đã công bố. Queue trong RAM của một process không bảo đảm công việc sống sót sau restart.

Với durable queue, cần xác định message acknowledgment, retry, visibility timeout, dead-letter queue, retention và idempotency. Queue bền vững vẫn có thể đầy dung lượng hoặc tăng backlog vượt deadline.

### Coalesce và thay thế công việc cũ

Một dashboard chỉ cần cache mới nhất cho từng tenant có thể gộp nhiều yêu cầu refresh thành một job. Nếu có 100 yêu cầu refresh tenant A đang chờ, chỉ cần giữ một job mới nhất thay vì chạy cả 100 job.

Không coalesce các lệnh ghi có tác động nghiệp vụ riêng như thanh toán, trừ khi logic nghiệp vụ định nghĩa rõ cách gộp.

## 11. Load shedding và giảm chất lượng có kiểm soát

Load shedding là chủ động giảm hoặc loại bỏ một phần tải khi hệ thống không thể phục vụ tất cả request trong giới hạn SLO.

Ví dụ:

- Tạm hoãn báo cáo lớn.
- Từ chối truy vấn export không khẩn cấp.
- Phục vụ dữ liệu cache hơi cũ cho dashboard.
- Giảm tần suất refresh tổng hợp.
- Tắt chức năng gợi ý hoặc thống kê phụ.
- Giới hạn truy vấn ad hoc.
- Ưu tiên thao tác ghi cốt lõi và truy vấn phục vụ giao dịch.

### Phân loại công việc trước khi quá tải

Hãy xác định trước:

- Công việc bắt buộc phải hoàn tất.
- Công việc có thể trì hoãn.
- Công việc có thể trả kết quả cache/stale.
- Công việc có thể gộp hoặc bỏ.
- Công việc cần reject để client thử lại.

Không đợi đến lúc database đã bão hòa mới quyết định cái gì có thể bỏ. Chính sách phải được thống nhất với nghiệp vụ và có thể quan sát.

### Không âm thầm bỏ ghi đã xác nhận

Nếu API đã trả thành công hoặc đã xác nhận message được lưu bền vững, hệ thống phải bảo đảm semantics tương ứng. Không được loại bỏ giao dịch ghi quan trọng khỏi queue mà không có trạng thái lỗi, đối soát hoặc thông báo rõ ràng.

## 12. Fairness và cô lập workload

Một tenant gửi lượng truy vấn lớn có thể chiếm toàn bộ queue và connection slots. Một báo cáo nặng có thể khiến truy vấn tra cứu đơn hàng bị chậm.

### Giới hạn theo tenant

Có thể đặt quota riêng theo tenant, API key hoặc customer tier. Ví dụ mỗi tenant được tối đa 10 query đang chạy và 100 job đang chờ, trong khi tổng hệ thống có giới hạn lớn hơn.

Quota riêng tránh một tenant độc chiếm tài nguyên nhưng cần xử lý tenant có quy mô rất khác nhau. Có thể dùng weighted quota theo tier hoặc mức sử dụng đã thỏa thuận.

### Workload classes

Phân loại workload:

- Interactive OLTP: truy vấn ngắn, cần latency thấp.
- Transactional writes: thao tác ghi cần durability.
- Background jobs: có thể chờ.
- Analytics/reporting: query dài, đọc nhiều.
- Maintenance: vacuum, analyze, index rebuild, backup.
- Administrative: thao tác vận hành cần kiểm soát riêng.

Có thể dùng pool hoặc queue riêng cho các lớp này. Tuy nhiên, mọi pool vẫn dùng chung database CPU, memory, I/O và lock; tổng concurrency phải nằm trong giới hạn capacity chung.

### Fair scheduling

FIFO đơn giản có thể khiến job dài đứng trước nhiều job ngắn. Strict priority có thể khiến job ưu tiên thấp bị đói vô hạn. Các lựa chọn:

- FIFO trong từng lớp.
- Weighted fair queue.
- Round-robin theo tenant.
- Aging: tăng dần ưu tiên theo thời gian chờ.
- Deadline scheduling cho công việc có hạn hoàn thành.
- Giới hạn số job nặng chạy đồng thời.

Chọn chính sách theo mục tiêu latency và công bằng, đồng thời đo queue age theo từng lớp.

## 13. Bulkhead: ngăn một loại tải làm sập mọi thứ

Bulkhead chia tài nguyên thành các vùng độc lập tương đối. Nếu báo cáo lớn bị chậm, nó không được phép chiếm hết worker hoặc connection dành cho giao dịch tương tác.

Ví dụ:

~~~text
Application
   |
   +-- Interactive queue --> 20 slots ----+
   |                                      |
   +-- Write queue -------> 12 slots -----+--> Shared database
   |                                      |
   +-- Report queue ------>  2 slots -----+
   |
   +-- Maintenance queue ->  1 slot ------+
~~~

Các con số chỉ minh họa. Tổng slot cần được benchmark và có thể thấp hơn giới hạn connection pool. Mục tiêu là giới hạn từng lớp và bảo vệ phần capacity dành cho workload quan trọng.

### Bulkhead không tạo tài nguyên mới

Các pool riêng vẫn tranh CPU, I/O, buffer, lock và log của cùng database. Bulkhead bảo vệ quota và fairness; nó không làm tăng throughput vật lý.

### Cẩn trọng với pool riêng quá nhiều

Mỗi pool có thể giữ connection idle hoặc tạo tổng số connection vượt giới hạn database. Hãy tính tổng connection tối đa trên tất cả service instance, job worker và công cụ quản trị.

Nếu có 10 instance ứng dụng, mỗi instance tạo pool tối đa 30 connection, database có thể nhận tới 300 connection từ riêng ứng dụng đó. Cần tính toàn bộ topology, không chỉ cấu hình một process.

## 14. Retry storm và cách điều khiển retry

Khi database quá tải hoặc timeout, client có thể retry. Nếu mọi client retry ngay, tải mới cộng vào tải cũ và tạo retry storm.

Ví dụ, 1.000 request thất bại cùng lúc và mỗi request retry 3 lần ngay lập tức có thể tạo thêm 3.000 lần gọi trong thời gian ngắn.

### Exponential backoff và jitter

Khoảng chờ tăng theo số lần thử:

~~~text
delay = min(max_delay, base_delay × 2^attempt) + jitter
~~~

Jitter phân tán thời điểm retry để tránh mọi client đồng loạt gửi lại. Cần giới hạn tổng thời gian retry và số lần thử.

### Retry budget

Một dịch vụ có thể giới hạn tỷ lệ request được phép retry so với request mới. Khi ngân sách retry cạn, trả lỗi thay vì tạo thêm tải.

### Chỉ retry lỗi phù hợp

Có thể cân nhắc retry lỗi tạm thời như deadlock victim hoặc lỗi kết nối đã xác định, nhưng cần biết transaction đã rollback hay commit chưa. Không retry vô hạn:

- Lỗi cú pháp hoặc constraint.
- Lỗi dữ liệu không hợp lệ.
- Request hết deadline.
- Database báo quá tải kéo dài.
- Kết quả commit không rõ mà không có idempotency.

### Idempotency và chống ghi trùng

Với thao tác ghi, client có thể gửi idempotency key. Database lưu key cùng kết quả trong transaction; nếu request được gửi lại, ứng dụng trả kết quả đã ghi nhận thay vì thực hiện tác động lần nữa.

Đối với job bất đồng bộ, dùng message id hoặc business key để chống xử lý trùng. At-least-once delivery có thể giao message nhiều lần; consumer cần idempotent.

## 15. Circuit breaker và timeout

Circuit breaker ngăn ứng dụng tiếp tục gọi một dependency đang thất bại liên tục. Nó thường có các trạng thái:

~~~text
CLOSED
  |
  | lỗi vượt ngưỡng
  v
OPEN
  |
  | hết thời gian chờ
  v
HALF-OPEN
  |
  +-- probe thành công --> CLOSED
  |
  +-- probe thất bại ---> OPEN
~~~

Khi OPEN, request bị từ chối nhanh hoặc chuyển sang fallback. HALF-OPEN chỉ cho một số probe giới hạn để kiểm tra dependency đã phục hồi chưa.

### Circuit breaker không thay thế admission control

Circuit breaker phản ứng với lỗi hoặc latency của dependency. Admission control giới hạn tải trước khi dependency bị bão hòa. Cần cả hai khi hệ thống có burst và failure.

### Timeout phải có thứ tự

Tổng request deadline nên lớn hơn các timeout thành phần nhưng vẫn đủ thời gian trả response và cleanup. Ví dụ:

- Admission wait timeout ngắn.
- Connection acquisition timeout ngắn hơn thời gian còn lại.
- Statement/query timeout theo deadline còn lại.
- Network timeout phù hợp với driver và hạ tầng.
- Transaction rollback/cleanup được tính vào ngân sách.

Khi client timeout, server có thể vẫn đang chạy query nếu cancellation không được truyền hoặc xử lý ngay. Cần xác minh query đã dừng, transaction đã rollback và connection đã được trả lại.

## 16. Batching và điều tiết tốc độ ghi

Batching có thể giảm round trip và overhead cho nhiều thao tác nhỏ. Tuy nhiên, batch quá lớn làm transaction dài, giữ khóa lâu và tạo log burst.

Một pipeline ghi nên giới hạn:

- Số batch đang bay.
- Số dòng hoặc byte mỗi batch.
- Thời gian tối đa một transaction.
- Số worker ghi đồng thời.
- Tốc độ enqueue và tốc độ commit.
- Số lần retry.

Nếu queue tăng liên tục dù worker đã chạy hết concurrency, không nên tiếp tục tăng batch size một cách mù quáng. Cần xác định database đang giới hạn ở log, lock, CPU, I/O hay execution plan.

### Adaptive batching

Có thể điều chỉnh batch size theo tín hiệu:

- Khi commit latency thấp, lock wait thấp và queue ổn định, tăng batch size từng bước nhỏ.
- Khi transaction duration, log backlog hoặc p99 tăng, giảm batch size.
- Khi database bão hòa, giảm số worker trước khi tăng concurrency.
- Khi queue gần đầy, dừng nhận job không khẩn cấp.

Giữ min/max rõ ràng và tránh điều chỉnh quá nhanh gây dao động.

## 17. Hàng đợi bền vững cho công việc database bất đồng bộ

Một durable queue phù hợp với công việc có thể chấp nhận xử lý sau, như gửi thông báo, tổng hợp báo cáo, import file hoặc đồng bộ dữ liệu.

Luồng phổ biến:

~~~text
Request
  |
  v
Ghi job vào durable queue
  |
  v
Trả accepted + job id
  |
  v
Worker nhận job
  |
  v
Thực hiện transaction database
  |
  v
Commit kết quả
  |
  v
Ack message
~~~

### Ack sau khi commit

Nếu worker ack message trước khi transaction database commit, process có thể chết sau ack và job bị mất khỏi queue dù dữ liệu chưa ghi.

Một cách thường dùng là commit dữ liệu trước, sau đó ack message. Nếu worker chết sau commit nhưng trước ack, message có thể được giao lại. Vì vậy, consumer cần idempotency để lần xử lý sau không tạo tác động trùng.

### Transactional outbox

Nếu một transaction vừa cập nhật database vừa cần phát message, ghi thay đổi nghiệp vụ và outbox record trong cùng transaction. Một publisher đọc outbox và gửi message sau commit. Cách này tránh trạng thái database commit nhưng message không bao giờ được phát do crash giữa hai thao tác.

Outbox vẫn cần xử lý gửi lặp, checkpoint và dọn record đã gửi. Consumer cũng cần idempotency.

### Queue backlog và retention

Durable queue cần giới hạn dung lượng, tuổi message và dead-letter policy. Nếu backlog vượt thời gian nghiệp vụ cho phép, cần cảnh báo, dừng nhận job mới hoặc tăng capacity downstream trong giới hạn an toàn.

## 18. Quan sát queue và database cùng lúc

Queue depth đơn lẻ không đủ để xác định tình trạng. Một queue có 100 job nhưng service rate 1.000 job/giây có thể ổn; queue 20 job nhưng mỗi job chờ 10 phút có thể là sự cố.

### Metrics phía queue

- Queue depth hiện tại.
- Enqueue rate và dequeue/completion rate.
- Oldest message age.
- Queue wait p50/p95/p99.
- Số job đang chạy.
- Số job bị reject, timeout hoặc expired.
- Retry count và dead-letter count.
- Payload bytes hoặc estimated work units.
- Backlog theo tenant và workload class.

### Metrics phía worker và pool

- Worker active/idle.
- Executor queue depth và rejected task.
- Semaphore slots đang dùng.
- Connection pool active/idle/pending.
- Connection acquisition latency.
- Connection hold duration.
- Transaction duration.
- Batch size và commit latency.

### Metrics phía database

- Active sessions và running statements.
- CPU, memory, buffer/cache pressure.
- IOPS, throughput và storage latency.
- Lock waits, deadlocks và wait events.
- Query p95/p99, rows examined và logical reads.
- WAL/redo/log generation và flush latency.
- Temp spill, sort/hash spill.
- Replication lag.
- Checkpoint/vacuum/maintenance activity.

### Kết nối trace giữa các tầng

Mỗi request/job nên có correlation id hoặc trace id. Ghi nhận timestamp ở các mốc enqueue, dequeue, connection acquired, query started, query finished, commit và response. Khi đó có thể phân rã:

~~~text
End-to-end latency
  = ingress wait
  + application queue wait
  + connection pool wait
  + database lock/execution wait
  + result transfer
  + application processing
~~~

Các thành phần có thể chồng lấp nếu pipeline song song, nên đây là cách phân rã cho luồng tuần tự điển hình. Trace thực tế phải dùng span và timestamp nhất quán.

## 19. Công cụ quan sát theo hệ quản trị

### PostgreSQL

Có thể bắt đầu với:

- pg_stat_activity để xem session, query và wait events.
- pg_locks để xem khóa và quan hệ chờ.
- pg_stat_statements để thống kê query theo fingerprint nếu extension được bật.
- Thống kê I/O và WAL theo view có trong phiên bản.
- EXPLAIN (ANALYZE, BUFFERS) để kiểm tra truy cập dữ liệu.

Ví dụ tìm session đang hoạt động hoặc chờ:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start;
~~~

Không dùng query text để thu thập dữ liệu nhạy cảm ngoài chính sách log. View hiển thị session chờ lock, I/O hoặc các event khác tùy tình trạng và phiên bản.

### MySQL InnoDB

Có thể sử dụng:

- Performance Schema để xem statement, wait, file I/O và lock.
- sys schema cho các view tổng hợp.
- SHOW ENGINE INNODB STATUS để xem transaction, deadlock và trạng thái InnoDB.
- Connection/thread metrics và replication status.
- Slow query log hoặc statement digest để tìm truy vấn tốn thời gian.

Cần đối chiếu wait của connection pool với session thực tế trên server. Nhiều request chờ pool có thể không xuất hiện như query đang chạy trong database.

### SQL Server

Có thể sử dụng:

- DMVs như sys.dm_exec_requests và sys.dm_os_waiting_tasks.
- Wait statistics để nhận diện nhóm tài nguyên đang chờ.
- Query Store để theo dõi plan và runtime.
- Extended Events cho deadlock, timeout và sự kiện quan trọng.
- Connection/session metrics và Resource Governor nếu được cấu hình.

Counter DMV thường tích lũy; hãy lấy delta theo khoảng thời gian và đối chiếu với thời điểm workload tăng.

## 20. Ví dụ thiết kế pipeline import

Một dịch vụ nhận file import chứa 500.000 dòng. Nếu API xử lý toàn bộ trong request đồng bộ, connection có thể bị giữ lâu và client timeout. Thiết kế bất đồng bộ có thể dùng queue và worker:

1. API kiểm tra định dạng và quyền truy cập.
2. Lưu file vào object storage.
3. Ghi job metadata vào durable queue.
4. Trả job id để client truy vấn trạng thái.
5. Worker lấy job và chia thành chunk.
6. Worker dùng giới hạn đồng thời để ghi vào database.
7. Mỗi chunk commit theo transaction riêng nếu nghiệp vụ cho phép.
8. Checkpoint ghi cùng transaction với dữ liệu chunk.
9. Khi lỗi tạm thời, retry với backoff và idempotency.
10. Khi queue backlog tăng, giảm tốc producer hoặc từ chối job mới.
11. Khi hoàn tất, ghi trạng thái và phát sự kiện kết quả.

### Giới hạn worker

Nếu database chịu được 12 batch ghi đồng thời ở mức latency mục tiêu, đặt giới hạn worker tương ứng hoặc thấp hơn sau khi tính số instance. Nếu có 4 instance, mỗi instance không thể tự đặt 12 worker mà không tính tổng 48 batch đồng thời.

### Không giữ transaction suốt quá trình import

Mỗi chunk có transaction ngắn và checkpoint rõ ràng. Nếu yêu cầu nghiệp vụ all-or-nothing, cần staging/publish hoặc cơ chế khác để không công bố dữ liệu một phần. Không được thay đổi semantics chỉ vì muốn giảm queue.

### Xử lý job trùng

Dùng job id và chunk key để xác định một chunk đã hoàn tất chưa. Nếu worker chết sau commit trước ack, lần nhận lại phải kiểm tra checkpoint và không áp dụng lại tác động cộng dồn.

## 21. Kịch bản quá tải và phản ứng phù hợp

| Dấu hiệu | Nguyên nhân có thể | Phản ứng ban đầu |
|---|---|---|
| Queue depth và oldest age cùng tăng | Arrival rate vượt service rate | Giảm nhận việc, reject hoặc tăng capacity có kiểm chứng |
| Pool pending tăng, DB active thấp | Connection leak, pool nhỏ hoặc connection bị giữ ngoài query | Đo hold time, kiểm tra leak và transaction scope |
| DB active cao, CPU gần bão hòa | Query/CPU capacity | Giới hạn concurrency, tối ưu plan, giảm workload phụ |
| Lock wait và deadlock tăng | Tranh chấp dữ liệu hoặc transaction dài | Giảm writer concurrency, rút ngắn transaction, chuẩn hóa lock order |
| Log flush latency tăng | Log storage hoặc commit pressure | Giới hạn batch/write rate, kiểm tra storage và durability |
| Temp spill tăng | Sort/hash vượt memory grant | Giảm input, sửa thống kê/plan, giới hạn report concurrency |
| Retry rate tăng nhanh | Timeout hoặc lỗi tạm thời | Mở retry budget, backoff/jitter, circuit breaker |
| Queue đầy nhưng database rảnh | Worker/pool bottleneck hoặc cấu hình sai | Kiểm tra worker health, pool và giới hạn tầng ứng dụng |
| Queue thấp nhưng latency cao | Service time hoặc downstream wait cao | Phân tích trace, wait events và execution plan |

Không áp dụng cùng một hành động cho mọi dấu hiệu. Ví dụ, tăng worker khi lock wait cao có thể làm database tệ hơn; giảm batch size khi commit latency do network round trip có thể làm số lần commit tăng.

## 22. Tự động điều chỉnh concurrency

Một controller có thể điều chỉnh số worker dựa trên throughput, latency và saturation. Cách đơn giản là tăng dần khi còn headroom và giảm nhanh khi dấu hiệu quá tải xuất hiện.

### Tín hiệu tăng concurrency

- Queue age tăng nhẹ nhưng database CPU/I/O còn headroom.
- Throughput tăng theo worker mới.
- p95/p99 chưa vượt SLO.
- Lock wait và commit latency ổn định.
- Connection pool còn capacity.

### Tín hiệu giảm concurrency

- p95/p99 vượt SLO kéo dài.
- Lock wait, deadlock hoặc timeout tăng.
- Database CPU hoặc I/O chạm giới hạn.
- Commit latency hoặc replication lag tăng.
- Queue wait tăng dù throughput không cải thiện.

### Tránh dao động

- Dùng khoảng quan sát đủ dài.
- Tăng từng bước nhỏ.
- Giảm nhanh hơn tăng khi overload.
- Có min/max và cooldown.
- Dùng hysteresis để tránh bật/tắt quanh một ngưỡng.
- Không để autoscaler chỉ nhìn queue depth mà bỏ qua database saturation.

Tăng số worker có thể làm queue ngắn đi trong vài giây nhưng khiến DB quá tải và service rate giảm. Controller cần tối ưu throughput hoàn tất ở latency mục tiêu, không phải số worker.

## 23. Benchmark và thử nghiệm overload

Một hệ thống cần được kiểm tra cả ở tải bình thường, burst và overload kéo dài.

### Các kịch bản thử

1. **Steady load:** arrival rate ổn định dưới capacity.
2. **Burst:** lượng request tăng đột ngột trong thời gian ngắn.
3. **Sustained overload:** arrival rate cao hơn service rate trong một khoảng có kiểm soát.
4. **Slow database:** tăng latency query hoặc giảm năng lực downstream trong môi trường thử nghiệm.
5. **Lock contention:** nhiều worker cập nhật cùng một tập khóa.
6. **Connection pool exhaustion:** giữ connection có chủ đích trong môi trường test.
7. **Recovery:** giảm tải sau overload và đo thời gian queue drain.
8. **Worker failure:** dừng worker khi job đang xử lý để kiểm tra redelivery và idempotency.

### Chỉ số thành công

- Throughput hoàn tất và tỷ lệ lỗi.
- p50/p95/p99 end-to-end.
- Queue wait và oldest age.
- Queue depth peak và thời gian drain.
- Connection acquisition time.
- Database CPU, I/O, lock waits và commit latency.
- Số retry và duplicate được ngăn chặn.
- Công việc bị reject/shed theo loại.
- Không mất job đã được xác nhận durable.
- Database phục hồi về baseline sau khi burst kết thúc.

### Kiểm tra sau khi giảm tải

Queue có thể tiếp tục lớn ngay cả khi arrival rate đã giảm. Hãy đo net drain rate:

~~~text
Queue drain rate = completion rate - arrival rate
~~~

Nếu completion 800 job/giây và arrival 500 job/giây, backlog giảm khoảng 300 job/giây trong điều kiện ổn định. Nếu database vẫn chậm do cache lạnh, vacuum backlog hoặc log pressure, thời gian drain có thể dài hơn dự kiến.

## 24. Những sai lầm thường gặp

- **Dùng queue không giới hạn:** backlog chuyển thành memory pressure và latency không kiểm soát.
- **Cho rằng queue làm database nhanh hơn:** queue chỉ điều phối thời điểm thực thi.
- **Chỉ giới hạn connection:** request vẫn có thể tích tụ ở HTTP thread hoặc worker queue.
- **Tăng pool size khi DB đã bão hòa:** làm tăng session và contention.
- **Tăng worker chỉ để giảm backlog:** có thể giảm service rate của database.
- **Block event-loop hoặc HTTP acceptor:** khiến toàn bộ dịch vụ mất khả năng nhận request.
- **Không có chính sách queue full:** hành vi quá tải trở nên ngẫu nhiên.
- **Retry ngay khi timeout:** tạo retry storm.
- **Retry không giới hạn:** giữ tải cao và kéo dài outage.
- **Không có idempotency:** retry hoặc redelivery có thể tạo ghi trùng.
- **Ack message trước khi commit:** có thể làm mất job khi worker chết.
- **Chỉ đo queue depth:** bỏ qua queue age, wait time và service rate.
- **Chỉ đo CPU:** bỏ qua lock, log flush, storage và pool wait.
- **Để báo cáo chiếm connection OLTP:** workload dài làm giao dịch ngắn chậm theo.
- **Autoscale worker theo backlog mà không có DB cap:** mở rộng ứng dụng có thể làm sập database.
- **Dùng một timeout độc lập ở mọi tầng:** request có thể tiếp tục chạy sau khi client đã bỏ cuộc.
- **Bỏ công việc đã xác nhận thành công:** phá vỡ semantics và gây mất dữ liệu nghiệp vụ.
- **Không thử recovery:** queue có thể chạy tốt khi bình thường nhưng không drain được sau sự cố.

## 25. Checklist thiết kế queue và backpressure

Trước khi đưa workload database vào production, hãy xác nhận:

- Đã xác định arrival rate, service rate và concurrency capacity bằng benchmark.
- Queue có giới hạn theo số phần tử và/hoặc byte.
- Queue capacity phù hợp deadline và thời gian chờ tối đa.
- Có metric queue depth, oldest age, enqueue/dequeue rate và wait time.
- Có admission control trước khi lấy connection.
- Connection pool có maximum size và acquisition timeout rõ ràng.
- Tổng connection từ tất cả instance nằm trong ngân sách database.
- Workload interactive, write, report và maintenance có giới hạn phù hợp.
- Có fairness hoặc quota theo tenant khi cần.
- Backpressure truyền được tới producer/upstream.
- Queue full có reject, timed wait, durable enqueue hoặc shedding policy rõ ràng.
- Công việc đã hết deadline được xử lý theo semantics nghiệp vụ.
- Retry có giới hạn, backoff, jitter và retry budget.
- Ghi có idempotency key hoặc cơ chế chống xử lý trùng.
- Message chỉ ack sau khi kết quả database đã được commit theo thiết kế.
- Timeout được phân bổ theo tổng request deadline.
- Circuit breaker và fallback có hành vi rõ.
- Có load shedding cho workload ít ưu tiên.
- Autoscaling worker tôn trọng database concurrency cap.
- Dashboard kết hợp queue, pool, DB waits, CPU, I/O và latency.
- Đã thử burst, sustained overload, dependency chậm và recovery.

## Kết luận

Quản lý hàng đợi, giới hạn đồng thời và backpressure giúp hệ thống database duy trì hành vi có thể dự đoán khi tải tăng. Queue có giới hạn hấp thụ burst trong khoảng thời gian ngắn; admission control giữ số công việc đang chạy trong capacity; backpressure truyền tín hiệu để upstream giảm tốc; load shedding bảo vệ giao dịch quan trọng; retry, circuit breaker và idempotency giúp phục hồi có kiểm soát.

Hãy đo arrival rate, service rate, queue wait, oldest age, connection acquisition, transaction duration và database wait events cùng nhau. Chọn concurrency bằng benchmark, giới hạn queue theo deadline, tách workload theo mức ưu tiên và kiểm tra cả lúc overload lẫn lúc drain backlog. Một hệ thống mở rộng tốt giữ throughput hoàn tất ổn định, tail latency trong SLO và không để quá tải ở một tầng lan thành sự cố toàn dịch vụ.
