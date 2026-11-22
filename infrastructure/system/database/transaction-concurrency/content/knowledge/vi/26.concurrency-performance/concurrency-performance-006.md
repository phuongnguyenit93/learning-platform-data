# Giới hạn mức đồng thời và tạo áp lực ngược (backpressure)

Khi nhiều request cùng truy cập database, tăng số transaction chạy đồng thời không phải lúc nào cũng làm hệ thống nhanh hơn. Mỗi transaction có thể cần connection, CPU, bộ nhớ, I/O và khóa. Khi những tài nguyên này gần bão hòa, thêm request thường làm hàng đợi dài hơn, lock wait tăng, timeout nhiều hơn và p95/p99 latency xấu đi.

**Giới hạn mức đồng thời (concurrency limit)** kiểm soát số công việc được phép đang xử lý tại cùng một thời điểm. **Backpressure (áp lực ngược)** giúp truyền tín hiệu quá tải ngược về phía tạo công việc để nguồn giảm tốc độ, chờ, gom lô hoặc từ chối nhận thêm. Kết hợp hai cơ chế với hàng đợi có giới hạn, deadline và chính sách từ chối rõ ràng giúp bảo vệ database khi lưu lượng tăng đột biến.

## 1. Vì sao quá nhiều transaction đồng thời làm hệ thống chậm?

Giả sử một dịch vụ nhận nhiều request cập nhật đơn hàng. Mỗi request mở transaction, lấy connection, đọc dữ liệu, cập nhật vài hàng rồi commit. Khi số request tăng, số transaction đang hoạt động cũng tăng.

Ban đầu, thêm concurrency có thể tăng throughput vì CPU, connection và I/O còn dư. Nhưng khi một tài nguyên gần bão hòa, thời gian chờ bắt đầu tăng nhanh:

```text
Lưu lượng tăng
    │
    ▼
Nhiều request cùng được nhận
    │
    ▼
Nhiều transaction / connection đồng thời
    │
    ├── CPU và I/O cạnh tranh
    ├── Lock contention tăng
    ├── Connection pool hết connection rảnh
    └── Hàng đợi và thời gian chờ tăng
             │
             ▼
       Timeout / retry / lỗi nhiều hơn
             │
             ▼
       Tải thực tế còn tăng thêm
```

Ví dụ, 100 request cùng sửa một nhóm hàng có khóa nóng có thể không chạy nhanh gấp 10 lần 10 request. Nhiều transaction phải chờ cùng một khóa, nhưng vẫn giữ connection, bộ nhớ và đôi khi cả các khóa khác. Những transaction chờ có thể làm cạn connection pool và khiến các truy vấn không liên quan cũng không lấy được connection.

Quá nhiều concurrency có thể gây:

- **Lock contention:** nhiều transaction tranh chấp cùng hàng, index key hoặc tài nguyên khóa.
- **Connection pool exhaustion:** mọi connection đang bận; request mới phải chờ pool hoặc timeout.
- **CPU saturation:** context switching và xử lý đồng thời tăng nhưng throughput không tăng tương ứng.
- **I/O saturation:** nhiều truy vấn cùng đọc/ghi storage khiến latency I/O tăng.
- **Memory pressure:** nhiều sort, hash join, cursor và transaction cùng giữ tài nguyên.
- **Queueing delay:** request chờ lâu trước khi được thực thi, dù thời gian SQL thực tế ngắn.
- **Retry amplification:** request timeout được gửi lại, làm database nhận thêm công việc khi đang quá tải.

Mục tiêu của giới hạn concurrency là giữ số công việc đang hoạt động trong phạm vi tài nguyên có thể phục vụ ổn định, đồng thời phản hồi sớm khi không thể nhận thêm.

## 2. Phân biệt concurrency limit, rate limit và backpressure

Ba khái niệm liên quan nhưng giải quyết các vấn đề khác nhau.

| Cơ chế | Kiểm soát điều gì? | Ví dụ |
|---|---|---|
| Concurrency limit | Số công việc đang chạy cùng lúc | Tối đa 20 transaction xử lý đơn hàng đồng thời |
| Rate limit | Số request được nhận trong một khoảng thời gian | Tối đa 100 request mỗi giây cho một tenant |
| Backpressure | Tín hiệu để nguồn giảm tốc độ hoặc chỉ gửi thêm khi downstream có khả năng nhận | Consumer yêu cầu publisher chỉ phát thêm 10 item khi đã xử lý xong một phần |
| Bounded queue | Số công việc được phép chờ | Tối đa 200 request chờ trước worker pool |
| Load shedding | Loại bỏ hoặc từ chối công việc khi quá tải | Trả `429` hoặc `503` thay vì xếp hàng vô hạn |

Rate limit không tự giới hạn số request đang chạy. Ví dụ, cho phép 10 request/giây nhưng mỗi request mất 30 giây có thể tạo ra khoảng 300 request đồng thời nếu không có concurrency limit.

Ngược lại, concurrency limit không giới hạn tốc độ theo thời gian. Nếu mỗi request hoàn tất trong 1 ms, 10 worker có thể xử lý rất nhiều request mỗi giây.

Backpressure có thể phối hợp với cả hai: downstream thông báo khả năng nhận hiện tại, producer điều chỉnh tốc độ, còn admission control vẫn giới hạn số công việc và kích thước hàng đợi.

## 3. Dùng Little’s Law để hiểu số công việc đang hoạt động

Little’s Law mô tả quan hệ giữa số công việc trung bình trong hệ thống, throughput và thời gian lưu lại:

\[
L = \lambda W
\]

Trong đó:

- `L`: số công việc trung bình đang ở trong hệ thống, gồm phần đang xử lý và đang chờ trong phạm vi đo.
- `λ`: throughput trung bình, số công việc hoàn tất mỗi đơn vị thời gian.
- `W`: thời gian trung bình một công việc ở trong hệ thống.

Ví dụ, một dịch vụ hoàn tất trung bình 80 thao tác database mỗi giây, thời gian xử lý trung bình mỗi thao tác là 50 ms:

\[
L = 80 \times 0.05 = 4
\]

Trung bình có khoảng 4 thao tác database đang nằm trong phạm vi đo. Con số này giúp ước lượng mức concurrency cần thiết để đạt throughput hiện tại, nhưng **không phải công thức tự động chọn giới hạn tối đa**. Cần đo tại tải thực, xét phân phối latency, tài nguyên, lock contention và phần biến động.

### Vì sao không nên tăng concurrency vô hạn?

Khi hệ thống còn dư tài nguyên, tăng số worker có thể tăng throughput. Khi đã đến điểm bão hòa, thêm worker chủ yếu tạo thêm hàng đợi và cạnh tranh. Một mô hình khái niệm:

```text
Throughput
   ^
   |                  _________ gần bão hòa
   |              ___/
   |           __/
   |        __/
   |     __/
   |____/____________________________> Concurrency
        vùng tăng       vùng tải cao
```

Đường cong thực tế phụ thuộc workload. Với truy vấn khóa nóng, throughput có thể bão hòa rất sớm. Với workload đọc độc lập, hệ thống có thể chịu concurrency cao hơn.

Hãy tìm “đầu gối” của đường cong bằng load test: điểm mà tăng concurrency chỉ cải thiện throughput rất ít nhưng p95/p99, queue wait hoặc lock wait tăng mạnh. Đặt giới hạn vận hành có khoảng dự phòng dưới điểm đó thay vì cố chạy sát mức cực đại.

## 4. Giới hạn concurrency ở đúng ranh giới công việc

Một request HTTP có thể thực hiện nhiều phần: xác thực, gọi dịch vụ ngoài, xử lý CPU, truy cập cache và truy cập database. Không nhất thiết phải giới hạn toàn bộ request bằng cùng một con số.

Ví dụ:

```text
HTTP request
   │
   ├── xác thực / kiểm tra đầu vào
   ├── gọi dịch vụ ngoài
   │
   └── phần cần database
          │
          ├── lấy connection
          ├── transaction ngắn
          └── commit / trả connection
```

Nếu mục tiêu là bảo vệ connection pool và database, hãy giới hạn phần công việc thực sự sử dụng database. Một request đang chờ dịch vụ ngoài không nên giữ connection hoặc transaction mở nếu không cần thiết.

Các ranh giới thường được giới hạn riêng:

- Số transaction đang thực thi trên database chính.
- Số truy vấn đồng thời vào một database replica.
- Số tác vụ ghi vào một bảng hoặc nhóm tài nguyên nóng.
- Số công việc cho mỗi tenant hoặc khách hàng.
- Số lời gọi đến dịch vụ thanh toán hoặc dịch vụ bên ngoài.
- Số tác vụ CPU-bound trong worker pool.

Giới hạn quá rộng có thể làm một workload ảnh hưởng workload khác. Ví dụ, một batch import lớn chiếm toàn bộ worker và connection, khiến request tương tác của người dùng không còn capacity. Có thể dùng bulkhead để tách pool hoặc ngân sách concurrency theo loại công việc.

## 5. Bounded queue: không xếp hàng vô hạn

Nếu tất cả worker đang bận, hệ thống thường đưa công việc mới vào hàng đợi. Hàng đợi giúp hấp thụ burst ngắn, nhưng nếu không giới hạn kích thước, nó có thể tiếp tục tăng khi tốc độ đến lớn hơn tốc độ xử lý.

Một hàng đợi vô hạn có thể dẫn đến:

- Bộ nhớ tăng liên tục.
- Request chờ lâu hơn deadline của chính nó.
- Client timeout trước khi worker bắt đầu xử lý.
- Retry tạo thêm request mới trong khi request cũ vẫn nằm trong queue.
- Khi worker phục hồi, một lượng lớn công việc cũ dồn vào database cùng lúc.

Hàng đợi nên có giới hạn cả về **số lượng** và, khi cần, **thời gian chờ tối đa**.

```text
Producer
   │
   ▼
Admission control
   │
   ├── còn capacity ──▶ Worker pool ──▶ Database
   │
   ├── worker bận nhưng queue còn chỗ ──▶ Bounded queue
   │
   └── queue đầy / deadline hết ──▶ Reject hoặc shed load
```

Queue chỉ hấp thụ burst tạm thời. Nếu tốc độ đến trung bình lâu dài cao hơn tốc độ xử lý, queue sẽ đầy dù có kích thước lớn đến đâu. Khi đó phải giảm tốc độ đầu vào, tăng capacity có kiểm soát, hoặc từ chối công việc.

## 6. Chọn chính sách khi queue đầy

Không có một chính sách đúng cho mọi loại công việc. Lựa chọn phải phù hợp ngữ nghĩa nghiệp vụ.

| Chính sách | Hành vi | Khi phù hợp | Rủi ro/cần chú ý |
|---|---|---|---|
| Reject immediately | Từ chối ngay khi không còn chỗ | API tương tác cần phản hồi nhanh | Client cần biết cách retry hoặc báo người dùng |
| Bounded wait | Chờ tối đa một khoảng thời gian | Burst ngắn có thể tự giảm | Chờ quá lâu làm hết deadline và giữ tài nguyên |
| Drop newest | Bỏ công việc mới đến | Telemetry hoặc dữ liệu tạm thời có thể mất | Không dùng cho giao dịch tài chính/ghi bắt buộc |
| Drop oldest | Bỏ công việc cũ để ưu tiên dữ liệu mới | Một số luồng trạng thái mới nhất | Có thể mất công việc đã chờ lâu |
| Coalesce | Gộp nhiều yêu cầu tương đương thành một | Làm mới cache, cập nhật trạng thái mới nhất | Phải xác định phép gộp có bảo toàn nghiệp vụ |
| Persist to durable queue | Ghi công việc vào hàng đợi bền vững | Tác vụ nền có thể xử lý muộn | Cần giới hạn backlog, retry và thời gian lưu |
| Load shed by priority | Từ chối tác vụ ưu tiên thấp trước | Có nhiều lớp dịch vụ | Cần tránh starvation của nhóm thấp ưu tiên |

Với thao tác ghi database có ý nghĩa nghiệp vụ, không được âm thầm drop. Hãy trả lỗi rõ ràng hoặc lưu vào hàng đợi bền vững theo hợp đồng. Nếu client retry, dùng idempotency key để cùng một ý định không tạo nhiều hiệu ứng.

## 7. Backpressure là gì?

Backpressure là cơ chế cho phép downstream báo rằng nó chỉ có thể tiếp nhận một lượng công việc nhất định, từ đó producer giảm tốc độ phát dữ liệu hoặc chờ tín hiệu cho phép gửi tiếp.

Trong một pipeline:

```text
Nguồn sự kiện ──▶ Transform ──▶ Ghi database
     ▲                              │
     └──────── demand / capacity ───┘
```

Nếu database chỉ xử lý ổn định 50 thao tác đồng thời, tầng ghi có thể giới hạn số thao tác đang bay và chỉ yêu cầu producer phát thêm khi có capacity. Nhờ vậy, áp lực không dồn thành một backlog vô hạn ở tầng trung gian.

Backpressure khác với việc chỉ tăng queue size. Queue lớn che giấu tình trạng quá tải trong một khoảng thời gian; backpressure cố gắng điều chỉnh tốc độ nguồn theo khả năng thực tế của đích.

### Backpressure end-to-end

Để hiệu quả, tín hiệu cần truyền qua các tầng:

1. Database/consumer có capacity giới hạn.
2. Worker hoặc reactive subscriber chỉ yêu cầu một lượng công việc phù hợp.
3. Queue trung gian có giới hạn và báo đầy.
4. Producer giảm tốc độ, tạm dừng, hoặc từ chối tạo thêm công việc.
5. API/gateway trả trạng thái quá tải nếu nguồn không thể chờ.

Nếu một tầng ở giữa nhận mọi request rồi đưa vào queue vô hạn, backpressure đã bị cắt đứt tại tầng đó. Vì vậy cần kiểm tra toàn bộ đường đi, không chỉ cấu hình consumer cuối.

## 8. Backpressure trong Reactive Streams

Reactive Streams định nghĩa cơ chế demand: subscriber yêu cầu publisher phát tối đa một số phần tử thông qua `request(n)`. Publisher không được phát tùy ý nhiều phần tử hơn demand hiện tại.

Ví dụ khái niệm:

```text
Subscriber: request(10)
Publisher: phát tối đa 10 phần tử
Subscriber: xử lý xong 6 phần tử, request(6)
Publisher: có thể phát thêm tối đa 6 phần tử
```

Với Reactor, một pipeline có thể giới hạn số tác vụ bất đồng bộ cùng chạy:

```java
Flux.fromIterable(orderIds)
    .flatMap(
        orderId -> updateOrderInDatabase(orderId),
        8,   // concurrency tối đa cho inner publishers
        1    // prefetch minh họa; chọn theo đặc tính nguồn
    );
```

Tham số concurrency giới hạn số inner publisher được subscribe đồng thời. `prefetch` ảnh hưởng lượng phần tử được yêu cầu/buffer ở một số operator. Cần xem semantics của operator và phiên bản thư viện; đặt concurrency là 8 không có nghĩa toàn bộ hệ thống chỉ có 8 request hoặc 8 connection.

### Backpressure không tự làm JDBC thành non-blocking

Reactive pipeline không biến một API JDBC blocking thành non-blocking chỉ bằng cách bọc nó trong `Flux` hoặc `Mono`. Nếu gọi JDBC trên event-loop thread, một truy vấn chậm có thể chặn event loop.

Với JDBC, cần đưa công việc blocking sang scheduler/worker phù hợp và giới hạn concurrency để không tạo quá nhiều thread chờ connection. Với R2DBC, thao tác database có API reactive, nhưng connection pool và database vẫn có capacity hữu hạn; vẫn cần giới hạn concurrency, queue và timeout.

## 9. Giới hạn concurrency bằng Semaphore trong Java

`Semaphore` có thể giới hạn số luồng được phép đi vào một vùng công việc cùng lúc. Ví dụ dưới đây giới hạn phần thao tác database ở mức 12 công việc đồng thời:

```java
public final class DatabaseAdmission {
    private final Semaphore permits = new Semaphore(12);

    public PaymentResult process(PaymentCommand command)
            throws InterruptedException {
        boolean acquired = permits.tryAcquire(200, TimeUnit.MILLISECONDS);
        if (!acquired) {
            throw new DatabaseBusyException("Database capacity is busy");
        }

        try {
            return paymentRepository.processInTransaction(command);
        } finally {
            permits.release();
        }
    }
}
```

Điểm quan trọng:

- Dùng `tryAcquire` với thời gian chờ hữu hạn để request không chờ vô hạn.
- Luôn `release()` trong `finally`, kể cả khi SQL ném exception.
- Chỉ giữ permit trong khoảng công việc cần giới hạn.
- Không giữ permit trong lúc chờ người dùng hoặc gọi dịch vụ ngoài không liên quan.
- Xử lý `InterruptedException` đúng cách; nếu bắt và không ném tiếp, cần khôi phục interrupt flag bằng `Thread.currentThread().interrupt()`.

Trong ví dụ, nếu `processInTransaction` tự mở và đóng transaction, permit bao phủ đúng phần service đó. Nếu transaction được mở ở tầng ngoài, hãy bảo đảm permit được giữ đến khi transaction thật sự kết thúc, không nhả permit ngay sau khi method trả về nhưng transaction vẫn mở.

Semaphore trong một JVM chỉ giới hạn process đó. Nếu chạy 5 instance, mỗi instance có 12 permit thì tổng số có thể lên tới 60. Nếu cần giới hạn toàn cluster, phải dùng cơ chế admission control phân tán hoặc chia ngân sách concurrency cho từng instance.

## 10. ThreadPoolExecutor với queue có giới hạn

Java `ThreadPoolExecutor` cho phép cấu hình số worker và hàng đợi hữu hạn:

```java
int workers = 12;
int queueCapacity = 100;

ThreadPoolExecutor databaseExecutor = new ThreadPoolExecutor(
    workers,
    workers,
    0L,
    TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(queueCapacity),
    new ThreadPoolExecutor.AbortPolicy()
);
```

Khi 12 worker đang bận và queue đã chứa 100 tác vụ, `AbortPolicy` ném `RejectedExecutionException`. Tầng gọi cần bắt lỗi này và chuyển thành hành vi quá tải phù hợp, chẳng hạn trả `503 Service Unavailable`, đưa vào hàng đợi bền vững hoặc từ chối theo chính sách nghiệp vụ.

### Các rejection policy

- `AbortPolicy`: từ chối bằng exception; phù hợp khi tầng gọi cần kiểm soát response.
- `CallerRunsPolicy`: chạy task trên thread gọi `execute`, tạo một dạng điều tiết tự nhiên trong một số ứng dụng.
- `DiscardPolicy`: bỏ task mới mà không báo lỗi; nguy hiểm với thao tác nghiệp vụ cần bảo đảm.
- `DiscardOldestPolicy`: bỏ task đầu queue rồi thử submit task mới; chỉ dùng khi bỏ công việc cũ là chấp nhận được.

`CallerRunsPolicy` không phù hợp nếu caller là event-loop thread, thread xử lý request nhạy latency hoặc thread giữ lock khác. Chạy tác vụ database blocking ngay trên caller có thể làm nghẽn toàn bộ tầng gọi. Hãy chọn rejection policy dựa trên ngữ nghĩa công việc và loại thread submit.

Không nên dùng queue vô hạn mặc định cho workload có thể tăng đột biến. Một queue hữu hạn biến overload thành tín hiệu có thể xử lý thay vì tích lũy âm thầm.

## 11. Kết nối concurrency limit với connection pool

Connection pool giới hạn số kết nối vật lý mà ứng dụng có thể dùng cùng lúc. Ví dụ một pool có `maximumPoolSize = 20` thì tối đa 20 connection được cấp cho ứng dụng tại một thời điểm theo cấu hình pool. Điều này không có nghĩa database chỉ có tổng cộng 20 session, vì có thể có nhiều application instance, job, công cụ quản trị và service khác.

Nếu mỗi instance có pool 20 và triển khai 6 instance, ứng dụng có thể tạo tới 120 connection. Cần tính tổng kết nối từ tất cả pool và để lại ngân sách cho tác vụ quản trị, replication, migration và các service khác.

### Không đồng nhất số worker với số connection

Một worker có thể làm việc ngoài database rồi mới lấy connection. Vì vậy số worker tổng thể có thể lớn hơn pool size nếu worker không giữ connection trong lúc chờ. Nhưng số thao tác database đồng thời thường cần được giới hạn gần với capacity connection pool và database.

Một số nguyên tắc:

- Không mở transaction sớm rồi chờ queue hoặc gọi API ngoài trong khi giữ connection.
- Lấy connection gần thời điểm thực hiện SQL và trả connection ngay sau commit/rollback.
- Đo `active`, `idle`, `pending` connection và thời gian chờ pool.
- Nếu `pending` tăng lâu dài, đừng chỉ tăng pool size; xem database còn capacity hay đang bị lock/CPU/I/O saturation.
- Tính tổng pool size của tất cả instance, không chỉ một process.
- Giữ capacity riêng cho health check, quản trị hoặc tác vụ thiết yếu nếu kiến trúc yêu cầu.

### Ví dụ cấu hình pool

```properties
maximumPoolSize=20
connectionTimeout=500
```

Đây là ví dụ cú pháp kiểu HikariCP, không phải khuyến nghị giá trị mặc định cho mọi hệ thống. `connectionTimeout` là thời gian tối đa chờ lấy connection; khi hết thời gian, request nhận lỗi. Cần chọn pool size và timeout bằng đo tải, số instance, giới hạn session database và đặc tính transaction.

Tăng pool có thể giúp nếu pool quá nhỏ trong khi database còn nhiều capacity. Nhưng nếu database đã bão hòa, tăng pool có thể làm nhiều truy vấn cùng tranh chấp CPU, I/O và khóa, khiến throughput không tăng mà latency xấu hơn.

## 12. Tách bulkhead theo loại công việc

Bulkhead (vách ngăn tài nguyên) chia capacity để một nhóm công việc không chiếm hết tài nguyên của nhóm khác.

Ví dụ:

```text
                    Tổng capacity ứng dụng
                              │
             ┌────────────────┼────────────────┐
             │                │                │
          API đọc          API ghi          Batch import
         10 permits       8 permits          2 permits
             │                │                │
         Read pool         Write pool       Batch pool
```

Đây là cách chia logic; các pool có thể dùng chung database hoặc connection pool tùy kiến trúc. Nếu dùng chung pool vật lý, semaphore riêng vẫn giúp bảo vệ ngân sách theo loại công việc, nhưng cần tránh cấu hình tổng permit vượt quá capacity thực tế.

Bulkhead hữu ích khi:

- Batch job có thể tạo burst lớn.
- Một tenant có workload nặng bất thường.
- Một endpoint có truy vấn chậm và không nên làm nghẽn endpoint khác.
- Một dịch vụ ngoài thường timeout và cần giới hạn số lời gọi đang bay.

Có thể kết hợp giới hạn toàn hệ thống với giới hạn theo tenant. Giới hạn riêng ngăn một tenant chiếm hết capacity; giới hạn tổng vẫn bảo vệ database khỏi tổng tải của tất cả tenant.

## 13. Deadline, timeout và cancellation

Backpressure không chỉ là chờ. Một request chỉ có giá trị nếu hoàn tất trước deadline mà người gọi còn chấp nhận.

Giả sử deadline tổng của API là 2 giây:

```text
Deadline tổng: 2.000 ms
  ├── chờ admission: tối đa 100 ms
  ├── chờ connection: tối đa 300 ms
  ├── thực thi transaction: phần thời gian còn lại
  └── serialize / trả response
```

Nếu request đã chờ 1,8 giây trước khi được worker nhận, không nên bắt đầu một transaction có thể mất thêm 5 giây rồi hy vọng client còn chờ. Hãy truyền deadline/cancellation xuống các tầng và từ chối sớm nếu không thể hoàn tất có ý nghĩa.

Các timeout cần được phân biệt:

- Admission timeout: chờ permit/concurrency slot quá lâu.
- Queue timeout: công việc nằm trong queue quá thời gian cho phép.
- Connection timeout: chờ connection pool quá lâu.
- Lock timeout: chờ khóa quá lâu.
- Statement/query timeout: câu SQL chạy quá thời gian cho phép.
- Request deadline: tổng thời gian client/server cam kết cho toàn request.

Timeout ở một tầng không tự động hủy mọi công việc ở tầng khác. Nếu client hủy request, ứng dụng nên hủy task chưa bắt đầu, cancel query nếu driver/DBMS hỗ trợ và rollback transaction khi cần. Cần xác nhận transaction thực sự kết thúc trước khi nhả tài nguyên.

## 14. Load shedding và circuit breaker

Khi hệ thống không còn capacity, **load shedding** từ chối một phần công việc để giữ dịch vụ thiết yếu hoạt động. Ví dụ, API có thể trả `503 Service Unavailable` kèm `Retry-After` khi queue đầy hoặc admission timeout.

Circuit breaker giải quyết một vấn đề liên quan nhưng khác: khi dependency liên tục thất bại hoặc latency vượt ngưỡng, breaker tạm ngừng gửi request để tránh tiếp tục gây tải lên dependency đang lỗi. Sau một thời gian, nó cho phép một số request thử nghiệm để xác định dependency đã phục hồi chưa.

| Cơ chế | Vai trò |
|---|---|
| Concurrency limit | Giới hạn số công việc đang hoạt động |
| Backpressure | Điều chỉnh tốc độ producer theo demand/capacity của consumer |
| Bounded queue | Giới hạn số công việc chờ |
| Load shedding | Từ chối công việc khi không thể tiếp nhận |
| Circuit breaker | Tạm ngừng gọi dependency đang có dấu hiệu lỗi |
| Rate limit | Giới hạn tốc độ request theo thời gian hoặc theo client |

Các cơ chế này bổ sung cho nhau. Circuit breaker không thay thế concurrency limit; rate limit không ngăn một số ít request rất chậm chiếm toàn bộ connection; queue có giới hạn không tự điều chỉnh producer nếu không có tín hiệu ngược.

## 15. Retry có thể làm overload nặng hơn

Khi database chậm, client thường timeout rồi retry. Nếu tất cả client retry ngay lập tức, database nhận request gốc cộng với request retry. Tải có thể tăng đúng lúc hệ thống đang yếu nhất.

Ví dụ một request được thử tối đa 3 lần:

```text
Request gốc ── timeout
     │
     ├── Retry 1 ── timeout
     │      │
     │      └── Retry 2 ── timeout
     │
     └── nhiều request khác cũng retry cùng lúc
```

Để tránh retry amplification:

- Retry chỉ lỗi tạm thời có khả năng phục hồi; không retry lỗi validation hoặc lỗi nghiệp vụ cố định.
- Dùng exponential backoff và jitter để phân tán lần thử.
- Đặt giới hạn số lần retry và tổng retry budget.
- Giữ nguyên idempotency key cho cùng một ý định nghiệp vụ.
- Không retry khi deadline đã hết.
- Tôn trọng `Retry-After` nếu API trả về.
- Tránh retry ở nhiều tầng cùng lúc vì số lần thử có thể nhân lên.

Backpressure và load shedding cần được kết hợp với retry policy có kiểm soát. Nếu API từ chối do quá tải nhưng client lập tức gửi lại hàng trăm lần, cơ chế bảo vệ sẽ mất tác dụng.

## 16. Chính sách fairness và ưu tiên

Một concurrency limit tổng có thể bị một tenant hoặc một nhóm công việc chiếm hết. Fairness (công bằng phân phối capacity) giúp tránh hiện tượng đó.

Các lựa chọn:

- Giới hạn tối đa theo tenant hoặc API key.
- Dùng queue riêng theo tenant/nhóm công việc.
- Weighted fair queueing để chia capacity theo trọng số.
- Ưu tiên request tương tác so với batch có thể chạy sau.
- Giới hạn số request đang chờ của một client.
- Dùng round-robin để một tenant có backlog lớn không chiếm toàn bộ worker.

Ưu tiên cần được thiết kế cẩn thận. Nếu tác vụ ưu tiên thấp không bao giờ có cơ hội chạy, hệ thống tạo starvation. Có thể dùng aging (tăng ưu tiên theo thời gian chờ), giới hạn tỷ lệ capacity dành cho nhóm ưu tiên cao hoặc bảo đảm một phần capacity cho batch.

## 17. Adaptive concurrency limit

Một giới hạn tĩnh dễ vận hành nhưng không phải lúc nào cũng tối ưu. Khả năng phục vụ database có thể thay đổi theo thời gian do cache, kích thước dữ liệu, plan, background maintenance hoặc workload khác.

Adaptive concurrency control điều chỉnh giới hạn dựa trên tín hiệu như:

- p50/p95/p99 latency của thao tác database.
- Thời gian chờ connection pool.
- Lock wait và số transaction bị chặn.
- CPU, I/O latency và queue depth.
- Timeout, deadlock và serialization failure.
- Throughput hoàn tất.

Một bộ điều khiển đơn giản có thể tăng concurrency từ từ khi latency ổn định và giảm nhanh hơn khi latency/queue wait tăng vượt ngưỡng. Một số thuật toán dùng AIMD (Additive Increase, Multiplicative Decrease): tăng từng bước nhỏ khi hệ thống khỏe, giảm theo tỷ lệ khi phát hiện congestion.

Không nên điều chỉnh theo một mẫu đơn lẻ hoặc chỉ dựa trên CPU. Nếu có một transaction khóa nóng, CPU có thể thấp nhưng latency vẫn rất cao. Cần dùng nhiều tín hiệu, có giới hạn min/max, hysteresis để tránh dao động và thời gian quan sát đủ dài.

Adaptive limit không thay thế queue hữu hạn, deadline và load shedding. Nếu thuật toán điều chỉnh chậm, hệ thống vẫn cần cơ chế bảo vệ tức thời.

## 18. Đo lường để chọn giới hạn

Không nên chọn concurrency limit chỉ dựa trên số core CPU hoặc số connection mặc định. Hãy đo workload thực tế ở nhiều mức concurrency.

Các chỉ số nên thu thập:

| Nhóm | Metric | Ý nghĩa |
|---|---|---|
| Throughput | Requests/transactions completed per second | Hệ thống hoàn tất bao nhiêu công việc |
| Latency | p50, p95, p99 và max | Người dùng phải chờ bao lâu, tail có xấu không |
| Admission | Active permits, rejected count, wait-to-acquire | Giới hạn có thường xuyên bị chạm không |
| Queue | Queue depth, oldest item age, enqueue wait | Backlog có tăng liên tục không |
| Connection pool | Active, idle, pending, acquisition latency | Pool có bị cạn không |
| Database | CPU, I/O, buffer reads, log flush, session count | Database đang bão hòa tài nguyên nào |
| Locking | Lock wait time, blocker count, deadlock count | Transaction có tranh chấp dữ liệu không |
| Reliability | Timeout, cancellation, retry, rejection, error rate | Overload ảnh hưởng tính ổn định ra sao |

### Quy trình chọn giới hạn

1. Đo baseline ở tải bình thường và ghi nhận latency/throughput.
2. Tăng concurrency theo từng mức trong môi trường thử nghiệm gần production.
3. Ở mỗi mức, đo throughput, p95/p99, queue wait, connection pending, CPU/I/O và lock wait.
4. Tìm điểm mà throughput bắt đầu phẳng trong khi latency và wait tăng nhanh.
5. Chọn giới hạn dưới điểm bão hòa, có dự phòng cho biến động và workload khác.
6. Đặt queue capacity theo burst có thể chấp nhận và deadline, không theo mong muốn “không bao giờ từ chối”.
7. Kiểm thử lại khi số instance, pool size, schema, query plan hoặc workload thay đổi.

Một con số hợp lý trong staging có thể không phù hợp production nếu production có nhiều service khác dùng chung database. Cần tính tổng concurrency và tổng connection của toàn hệ thống.

## 19. Ví dụ thiết kế luồng ghi đơn hàng

Giả sử API nhận request tạo đơn hàng. Database có connection pool hữu hạn; một số request có thể chờ dịch vụ tính phí vận chuyển.

Thiết kế chưa tốt:

```text
Nhận request
  → mở transaction
  → lấy connection
  → khóa hàng tồn kho
  → gọi API vận chuyển
  → chờ 2 giây
  → cập nhật order
  → commit
```

Transaction giữ connection và khóa trong lúc chờ mạng. Nếu nhiều request cùng làm vậy, lock wait và pool wait tăng.

Thiết kế có kiểm soát hơn:

```text
Nhận request
  │
  ├── kiểm tra rate/concurrency admission
  ├── tính dữ liệu không cần transaction
  ├── gọi dịch vụ ngoài trước khi mở transaction nếu an toàn
  │
  └── vào vùng giới hạn database
         ├── lấy connection
         ├── transaction ngắn
         ├── cập nhật tồn kho và order
         ├── ghi outbox event
         └── commit, trả connection
                  │
                  ▼
             worker xử lý event sau commit
```

Phần tính phí vận chuyển trước transaction chỉ phù hợp nếu không phụ thuộc vào dữ liệu phải khóa và có thể xác nhận lại khi commit. Nếu điều kiện nghiệp vụ thay đổi, cần kiểm tra lại trong transaction. Side effect ngoài nên dùng idempotency key và outbox khi cần bảo đảm retry.

Admission control giới hạn số transaction đang đi vào vùng database. Queue hữu hạn hấp thụ burst ngắn. Nếu queue đầy hoặc deadline sắp hết, API từ chối sớm để client thử lại theo chính sách.

## 20. Kiểm thử concurrency limit và backpressure

Test cần chứng minh giới hạn thực sự được áp dụng và overload không làm hệ thống nhận thêm công việc vô hạn.

### Test concurrency tối đa

Dùng một tác vụ giả lập có latch để giữ worker đang chạy. Submit nhiều tác vụ hơn giới hạn và xác nhận số tác vụ đồng thời trong critical section không vượt mức cấu hình.

```java
@Test
void neverExceedsConfiguredConcurrency() throws Exception {
    int limit = 4;
    Semaphore semaphore = new Semaphore(limit);
    AtomicInteger active = new AtomicInteger();
    AtomicInteger maxObserved = new AtomicInteger();
    CountDownLatch entered = new CountDownLatch(8);
    CountDownLatch release = new CountDownLatch(1);

    // Submit nhiều worker; mỗi worker acquire permit,
    // tăng active, cập nhật maxObserved, rồi chờ release.
    // Sau đó assert maxObserved <= limit.
}
```

Đoạn code là khung minh họa; test hoàn chỉnh cần giải phóng latch trong `finally`, dùng executor riêng và timeout hữu hạn để tránh treo khi assertion thất bại.

### Test queue đầy

- Giữ tất cả worker bằng latch.
- Submit đủ tác vụ để lấp bounded queue.
- Submit thêm một tác vụ.
- Xác nhận tác vụ mới bị reject theo chính sách.
- Xác nhận queue không vượt capacity và bộ nhớ không tăng theo số request gửi vào.

### Test backpressure

- Tạo publisher nhanh hơn consumer.
- Giới hạn demand hoặc concurrency ở consumer.
- Quan sát số phần tử được phát/đưa vào buffer không vượt giới hạn thiết kế.
- Xác nhận producer giảm tốc độ hoặc queue đầy dẫn đến tín hiệu reject rõ ràng.

### Test recovery

- Làm database chậm hoặc tạm thời không nhận connection.
- Xác nhận queue có giới hạn và request vượt capacity được xử lý theo chính sách.
- Phục hồi database và kiểm tra backlog được xử lý mà không tạo burst vượt giới hạn.
- Xác nhận retry có backoff và không tạo duplicate business effect.

## 21. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Tăng connection pool khi thấy pool pending cao | Có thể đẩy database vào trạng thái bão hòa hơn | Kiểm tra CPU, I/O, lock wait và tổng pool của mọi instance |
| Dùng queue vô hạn để không mất request | Bộ nhớ và queue latency tăng không giới hạn | Bounded queue, deadline và load shedding |
| Chỉ dùng rate limit | Request chậm vẫn có thể tích lũy concurrency lớn | Kết hợp concurrency limit và queue cap |
| Chỉ dùng concurrency limit nhưng không giới hạn queue | Số request chờ vẫn có thể tăng vô hạn | Giới hạn cả active work lẫn queued work |
| Giữ connection trong lúc gọi API ngoài | Pool và lock bị chiếm lâu | Thu hẹp transaction và trả connection sớm |
| Dùng CallerRuns trên event loop | Event loop bị block bởi tác vụ database | Rejection hoặc worker pool phù hợp |
| Drop tùy tiện các thao tác ghi | Mất dữ liệu nghiệp vụ | Reject rõ ràng hoặc durable queue; không âm thầm bỏ |
| Retry ngay lập tức khi quá tải | Retry amplification | Backoff, jitter, retry budget và idempotency |
| Chỉ giới hạn trong một instance | Tổng cluster concurrency có thể vượt capacity | Tính tổng ngân sách hoặc dùng admission control phân tán |
| Chọn limit theo số CPU mà không đo | Không phản ánh lock, I/O và connection pool | Load test và tìm điểm bão hòa |
| Tăng queue size để giảm reject | Chỉ kéo dài thời gian chờ, không tăng capacity | Chọn queue theo burst và deadline |

## 22. Tự kiểm tra

**Tình huống 1:** Một API cho phép 10 request mỗi giây. Mỗi request mất trung bình 5 giây. Vì sao vẫn có thể có khoảng 50 request đang xử lý hoặc chờ?

**Đáp án:** Rate limit giới hạn tốc độ đến, không giới hạn số request đồng thời. Theo Little’s Law, `L = λ × W = 10 × 5 = 50`. Cần concurrency limit và queue cap nếu 50 request vượt capacity.

**Tình huống 2:** Worker pool có 8 thread nhưng queue vô hạn. Database chậm trong 10 phút. Điều gì có thể xảy ra?

**Đáp án:** Chỉ 8 worker chạy cùng lúc nhưng số request chờ có thể tăng liên tục, làm tăng bộ nhớ và queue latency. Khi worker phục hồi, backlog lớn có thể tạo burst. Cần bounded queue và chính sách reject/backpressure.

**Tình huống 3:** Connection pool có 20 connection. Có nên đặt concurrency limit của toàn bộ HTTP request bằng 20 không?

**Đáp án:** Không nhất thiết. HTTP request có phần việc không dùng database. Nên giới hạn riêng vùng thao tác database, đồng thời tính các instance, tác vụ khác và connection dành cho công việc thiết yếu.

**Tình huống 4:** Database đã có lock wait cao và p99 tăng. Tăng số worker có chắc làm throughput tăng không?

**Đáp án:** Không. Worker thêm có thể chỉ tạo thêm waiter và giữ connection. Cần tìm blocker/khóa nóng, rút ngắn transaction và giới hạn concurrency dưới điểm bão hòa.

**Tình huống 5:** Queue đầy. Có nên dùng `DiscardPolicy` cho tác vụ trừ tiền không?

**Đáp án:** Không. Tác vụ nghiệp vụ quan trọng không được âm thầm bỏ. Hãy từ chối rõ ràng trước khi nhận xử lý hoặc lưu vào hàng đợi bền vững theo hợp đồng, kết hợp idempotency khi retry.

**Tình huống 6:** Reactive `flatMap` được đặt concurrency bằng 8. Điều đó có nghĩa toàn hệ thống chỉ có 8 database connection không?

**Đáp án:** Không. Nó giới hạn inner publisher của operator đó trong pipeline cụ thể. Các pipeline, instance hoặc service khác vẫn có thể tạo thêm công việc. Connection pool và admission control tổng vẫn cần được cấu hình riêng.

**Tình huống 7:** Client timeout rồi retry ngay cùng lúc với hàng nghìn client khác. Rủi ro là gì và cách giảm?

**Đáp án:** Retry amplification có thể làm tải tăng thêm khi database đang quá tải. Dùng exponential backoff, jitter, retry budget, deadline, idempotency key và `Retry-After` phù hợp.

Khi thiết kế concurrency cho database, hãy đo điểm bão hòa thay vì đoán số worker; giới hạn riêng phần công việc dùng database; đặt queue hữu hạn; truyền backpressure hoặc từ chối sớm khi không còn capacity; giữ transaction và connection ngắn; và kiểm soát retry. Mục tiêu là duy trì throughput ổn định cùng latency có thể dự đoán, kể cả khi lưu lượng đến vượt khả năng xử lý trong một khoảng thời gian.
