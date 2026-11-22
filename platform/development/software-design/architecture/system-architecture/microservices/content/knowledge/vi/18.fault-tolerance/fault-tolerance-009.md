# Áp lực ngược và kiểm soát hàng đợi khi hệ thống quá tải

> **Phạm vi:** Software Design Architecture → System Architecture → Microservices → Khả năng chịu lỗi. Tài liệu giải thích cách nhận biết, thiết kế và vận hành **backpressure** cùng **bounded queue** để hệ thống duy trì ổn định khi lưu lượng đến lớn hơn năng lực xử lý.

## 1. Vì sao quá tải có thể làm sập cả chuỗi microservices?

Một yêu cầu đi qua API Gateway → Order Service → Payment Service → cơ sở dữ liệu thường tiêu thụ kết nối, luồng xử lý, bộ nhớ, CPU và thời gian chờ ở nhiều tầng. Khi tốc độ yêu cầu đến lớn hơn tốc độ hoàn thành, các yêu cầu bị dồn vào hàng đợi hoặc tiếp tục chiếm tài nguyên trong trạng thái chờ.

Nếu không có cơ chế kiểm soát, thường xảy ra vòng xoáy:

1. Dịch vụ đích chậm khiến request đang xử lý kéo dài.
2. Số request đồng thời và hàng đợi tăng; bộ nhớ, thread pool, connection pool cạn dần.
3. Độ trễ p95/p99 vượt timeout của dịch vụ gọi.
4. Client hoặc dịch vụ upstream retry, tạo thêm tải đúng lúc downstream yếu nhất.
5. Lỗi lan qua nhiều dịch vụ, dù nguyên nhân ban đầu chỉ ở một dependency.

**Backpressure (áp lực ngược)** là cơ chế để bên tiêu thụ báo hoặc thể hiện giới hạn năng lực cho bên tạo tải, buộc tốc độ gửi/nhận dữ liệu giảm xuống, tạm dừng hoặc bị từ chối. **Queue control (kiểm soát hàng đợi)** giới hạn số phần việc đang chờ, cách xếp lịch, thời gian được phép chờ và hành vi khi đầy. Hai cơ chế phối hợp với kiểm soát concurrency, timeout và load shedding.

Một hàng đợi chỉ **hấp thụ tải tăng đột biến trong thời gian ngắn**; nó không tạo thêm năng lực xử lý. Nếu đầu vào liên tục vượt đầu ra, hàng đợi hữu hạn cuối cùng sẽ đầy, còn hàng đợi vô hạn sẽ làm độ trễ và mức sử dụng bộ nhớ tăng không giới hạn.

## 2. Mô hình tải và những đại lượng cần hiểu

Ký hiệu:

- **λ (lambda):** tốc độ phần việc đến, đơn vị request/giây hoặc message/giây.
- **μ (mu):** tốc độ xử lý trung bình của một worker, đơn vị phần việc/giây.
- **k:** số worker có thể chạy đồng thời; năng lực xấp xỉ **C = k × μ** trong điều kiện ổn định.
- **Q:** số phần việc chờ trong hàng đợi; **I:** số phần việc đang thực thi (in-flight).
- **Wq:** thời gian chờ trong queue; **Ws:** thời gian xử lý; **W:** thời gian từ lúc nhận đến lúc trả kết quả.
- **D:** deadline hoặc ngân sách độ trễ của request.

Trong một hệ thống ổn định, **Little's Law: L = λhiệu_dụng × W**, trong đó L là số phần việc trung bình đang ở trong hệ thống; với riêng hàng đợi có **Lq = λhiệu_dụng × Wq**. Đây là quan hệ trung bình dài hạn, **không đảm bảo p99** cho những đợt burst hoặc phân phối thời gian xử lý nhiều biến động.

Ví dụ: 8 worker, mỗi worker xử lý trung bình 10 request/giây → C ≈ 80 request/giây. Nếu nhận liên tục 120 request/giây, chênh lệch 40 request/giây sẽ tạo thêm khoảng 2.400 yêu cầu chờ trong một phút nếu không từ chối hoặc điều tiết đầu vào. Hàng đợi 24 request chỉ hấp thụ được khoảng **24 / 40 = 0,6 giây** chênh lệch trước khi đầy. Muốn giữ hệ thống sống sót dưới tải kéo dài, phải **giới hạn request được nhận**, giảm công việc hoặc tăng năng lực thực tế của nút nghẽn.

Cần phân biệt **độ sâu hàng đợi** với **tuổi phần việc cũ nhất**. Queue có 50 mục nhưng xử lý mỗi giây 500 mục có thể bình thường; queue có 5 mục nhưng oldest age 40 giây trong nghiệp vụ yêu cầu phản hồi 1 giây có thể là sự cố nghiêm trọng.

## 3. Các cơ chế liên quan và phạm vi tác dụng

| Cơ chế | Mục tiêu trực tiếp | Hành vi tiêu biểu |
| --- | --- | --- |
| Backpressure | Làm tốc độ upstream phù hợp downstream | Giảm demand, pause consumer, trả tín hiệu cần giảm tải |
| Bounded queue | Giới hạn công việc chờ và bộ nhớ | Queue đầy thì từ chối, tạm ngừng nhận hoặc điều tiết |
| Concurrency limit / bulkhead | Giữ số tác vụ cùng lúc trong ngân sách | Semaphore 32 permit cho một dependency; quá giới hạn thì reject |
| Rate limiting | Khống chế tốc độ theo thời gian, người dùng hoặc tenant | Token bucket, quota 100 request/giây |
| Load shedding | Chủ động bỏ bớt công việc khi quá tải | Ưu tiên traffic quan trọng; trả 503 sớm |
| Circuit breaker | Ngừng gọi dependency đang lỗi hoặc chậm bất thường | Open circuit, fail fast trong khoảng phục hồi |
| Timeout / deadline | Giới hạn thời gian một request được giữ tài nguyên | Hủy hoặc ngừng chờ khi hết ngân sách |
| Autoscaling | Tăng số worker/instance khi còn dư năng lực nền tảng | Scale consumer theo backlog, có giới hạn để bảo vệ DB |

Các cơ chế **bổ sung cho nhau**. Rate limit không bảo đảm queue không đầy khi service time bất ngờ tăng. Circuit breaker không thay thế việc giới hạn số request đang chạy. Autoscaling không giải quyết được nút nghẽn là một cơ sở dữ liệu có số connection hữu hạn.

## 4. Đặt backpressure ở đâu trong kiến trúc?

~~~text
Client / Mobile
    |
    v
API Gateway  -- rate limit, request deadline, 429/503
    |
    v
Order Service -- admission control, concurrency limit
    |                      |
    | queue chờ có giới hạn| queue đầy -> reject sớm
    v                      v
Payment Service -------> Database / external API
    |
    +---- sự kiện ----> Broker (Kafka/RabbitMQ)
                            |
                        Consumer Service
                        pause/prefetch + worker pool
                            |
                         Database
~~~

Kiểm soát cần được đặt **ngay trước tài nguyên khan hiếm** (connection pool, worker pool, CPU-bound processor, API thứ ba) và ở **biên nhận tải** (gateway, queue ingress, event producer). Một tầng chỉ tự bảo vệ mình chưa đủ nếu nó vẫn gửi tải không giới hạn xuống tầng khác.

Với HTTP đồng bộ, tín hiệu thường là trả lời sớm **429 Too Many Requests** (vượt chính sách quota/rate limit) hoặc **503 Service Unavailable** (không còn năng lực phục vụ), kèm hướng dẫn retry khi phù hợp. Với xử lý bất đồng bộ, consumer có thể giảm số message nhận, tạm dừng partition hoặc kiểm soát số message chưa ack. Với Reactive Streams, consumer có thể yêu cầu đúng số phần tử có khả năng xử lý.

**Điểm then chốt:** Một broker có queue dài không tự làm producer chậm lại. Nếu producer liên tục đẩy vào broker và chính broker đạt giới hạn lưu trữ, phải có quota, giới hạn producer, phản hồi lỗi có kiểm soát hoặc cơ chế giảm tải ở upstream.

## 5. Nguyên tắc thiết kế queue hữu hạn

### 5.1. Quy định một ngân sách rõ ràng

Mỗi điểm đệm cần có ít nhất:

- **Capacity:** tối đa bao nhiêu message/request đang chờ; kiểm tra cả in-flight và queue.
- **Wait budget:** phần việc có thể chờ tối đa bao lâu trước khi hết giá trị nghiệp vụ.
- **Overflow policy:** khi đầy sẽ reject, shed, nén/gộp, bỏ phần việc cũ hay chuyển tuyến; không mặc định drop dữ liệu quan trọng.
- **Ordering / fairness:** FIFO, theo key, ưu tiên hay công bằng theo tenant; có cho phép starvation không.
- **Ownership / durability:** queue trong RAM có thể mất khi process chết; message broker bền vững vẫn cần acknowledgment và xử lý trùng.
- **Observability:** đo queue length, oldest age, enqueue/reject rate, completion rate.

Queue nên lưu **tham chiếu nhỏ, định danh công việc hoặc envelope có giới hạn kích thước**, thay vì chứa payload khổng lồ hoặc giữ toàn bộ HTTP request object. Một queue 5.000 mục × 200 KB payload chiếm xấp xỉ 1 GB chỉ tính payload; object graph và metadata làm thực tế cao hơn.

### 5.2. Chọn cách xử lý khi đầy theo ý nghĩa nghiệp vụ

| Loại công việc | Chính sách thường phù hợp | Điều cần bảo đảm |
| --- | --- | --- |
| HTTP đồng bộ cần phản hồi nhanh | Reject sớm với 429/503 | Giải phóng permit, không treo request |
| Thanh toán / đơn hàng quan trọng | Bền vững hóa trước, giới hạn ingress, phản hồi có job ID | Idempotency, truy vết, không mất/nhân đôi giao dịch |
| Cập nhật dashboard có thể gộp | Coalesce theo khóa, chỉ giữ trạng thái mới nhất | Không làm mất yêu cầu bắt buộc xử lý từng lần |
| Telemetry ưu tiên thấp | Sample/drop có kiểm soát | Đếm số bản ghi bị bỏ, tránh che mất tín hiệu sự cố |
| Công việc batch trì hoãn được | Queue bền vững + giới hạn throughput | Giám sát backlog age và thời hạn hoàn tất |

Không áp dụng một chính sách drop chung cho thanh toán, nhật ký kiểm toán và metrics. Nếu cần bảo toàn dữ liệu, việc **không nhận mới** phải được phản hồi rõ ràng để upstream có thể lưu bền vững và thử lại an toàn.

### 5.3. Bounded queue và admission control

Một request chỉ được nhận nếu còn năng lực đã phân bổ. Có thể giới hạn riêng:

- **Max in-flight:** giới hạn số request đang thực thi, thường bằng semaphore hoặc bulkhead.
- **Max waiting:** số request được phép chờ ngắn hạn, thường nhỏ hơn nhiều so với lượng traffic một phút.
- **Max wait duration:** thời gian được phép nằm trong queue; quá deadline thì loại bỏ trước khi tiêu tốn công sức downstream.

Không giữ hàng nghìn thread HTTP chỉ để chờ semaphore vô hạn. Trong hệ thống đồng bộ, **tryAcquire với timeout rất ngắn hoặc bằng 0** thường an toàn hơn một hàng chờ dài. Việc đứng chờ cũng cần tính vào thời gian phản hồi và số thread đang bị chiếm.

### 5.4. Dùng ngưỡng cao/thấp để tránh bật tắt liên tục

Ví dụ queue capacity = 100; khi đạt **HIGH = 80** thì pause nhận thêm, khi giảm xuống **LOW = 30** mới resume. Khoảng cách giữa hai ngưỡng tạo **hysteresis**, giúp consumer không liên tục pause/resume ở đúng một ngưỡng. Ngưỡng phải đi kèm số in-flight và khả năng có thêm phần việc từ đợt poll hiện tại.

## 6. Tính kích thước và deadline theo năng lực thực tế

Một quy trình sơ bộ:

1. Đo throughput hoàn thành bền vững **C**, service time p50/p95/p99, số connection và số worker trong điều kiện tải thật.
2. Đặt **deadline D** từ SLO đầu cuối. Trừ thời gian mạng, downstream và xử lý để tìm **Wq tối đa** được phép.
3. Ước tính queue ban đầu **Q ≈ C × Wq** (Little's Law cho trạng thái ổn định và tốc độ hoàn thành gần C); sau đó hiệu chỉnh bằng load test và tail latency.
4. Đặt **max in-flight** theo CPU, DB connections và downstream quotas. Cần tính tổng của mọi replica, không chỉ một instance.
5. Áp dụng bounded admission, timeout, overload response và retry budget trước khi mở rộng queue.

Ví dụ minh họa:

| Thông số | Giá trị giả định |
| --- | ---: |
| Worker đồng thời | 8 |
| Throughput ổn định mỗi worker | 10 job/giây |
| Năng lực C | 80 job/giây |
| Ngân sách thời gian chờ Wq | 0,3 giây |
| Q ước tính ban đầu | 80 × 0,3 ≈ 24 job |
| Input đột biến | 120 job/giây |
| Chênh lệch input − capacity | 40 job/giây |

Có thể thử queue khoảng **20–24 mục**, thay vì 2.000 mục, nếu mục tiêu chính là trả lời HTTP nhanh. Với tải 120 job/giây kéo dài, vẫn cần điều tiết hoặc từ chối phần vượt quá ~80 job/giây. **Q = 24 không bảo đảm p99 queue wait = 300 ms**: service time dao động, scheduling, lock và head-of-line blocking phải được đo thực tế.

Một cấu hình ổn định phải xét **deadline theo chuỗi**, chẳng hạn:

~~~text
Deadline end-to-end: 1.000 ms
  Gateway/network:      100 ms
  Queue/admission:      100 ms
  Service work:         450 ms
  Downstream request:   250 ms
  Safety margin:        100 ms
~~~

Các con số chỉ là ví dụ phân bổ. Khi phần deadline còn lại quá ít, nên từ chối hoặc hủy sớm thay vì gọi downstream để rồi trả timeout muộn. Nếu request đã hết hạn trong queue, phải loại khỏi queue; nếu task đã chạy, cần truyền tín hiệu hủy nơi thư viện và nghiệp vụ hỗ trợ.

## 7. Triển khai HTTP đồng bộ: giới hạn tài nguyên và fail fast

Ví dụ Java 17 dưới đây minh họa một **bounded worker pool** có 8 tác vụ chạy và tối đa 24 tác vụ chờ. Các kiểu Command, Result, OverloadedException và process là thành phần nghiệp vụ cần định nghĩa trong ứng dụng.

~~~java
import java.util.concurrent.*;

public final class BoundedJobService {
    private final ThreadPoolExecutor workers = new ThreadPoolExecutor(
        8, 8,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(24),
        new ThreadPoolExecutor.AbortPolicy()
    );

    public CompletableFuture<Result> submit(Command command) {
        CompletableFuture<Result> answer = new CompletableFuture<>();

        try {
            workers.execute(() -> {
                try {
                    answer.complete(process(command));
                } catch (Exception ex) {
                    answer.completeExceptionally(ex);
                }
            });
        } catch (RejectedExecutionException full) {
            answer.completeExceptionally(
                new OverloadedException("Worker queue is full", full)
            );
        }

        return answer;
    }

    private Result process(Command command) {
        // Business logic: must have its own downstream deadline.
        throw new UnsupportedOperationException("Implement application logic");
    }

    public void shutdown() {
        workers.shutdown();
    }
}
~~~

Tại HTTP adapter, ánh xạ OverloadedException thành **503** khi hết năng lực phục vụ; nếu nguyên nhân là vượt quota theo client, trả **429**. Không mặc định trả **202 Accepted** khi chưa lưu bền vững job: HTTP 202 ngụ ý công việc đã được chấp nhận để tiếp tục xử lý. Với thao tác đã hoàn tất, dùng 2xx phù hợp; với job bất đồng bộ đã nhận bền vững, dùng 202 kèm job ID và API tra trạng thái.

Ví dụ phản hồi quá tải:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 2

{"error":"temporarily_overloaded","retryable":true}
~~~

**Retry-After** chỉ nên gửi khi có ước lượng hợp lý về thời điểm thử lại; giá trị 2 giây ở trên là minh họa. Client phải có giới hạn số lần và tổng thời gian retry, exponential backoff với jitter, đồng thời chỉ tự động retry thao tác an toàn hoặc đã có **idempotency key**. Nếu 1.000 client đều retry tức thì sau 1 giây, server có thể nhận một đợt sóng quá tải mới.

Hạn chế của ví dụ worker pool: queue nhận task vẫn giữ dữ liệu trong bộ nhớ; CompletableFuture timeout không tự động hủy tác vụ đã được đưa vào executor. Trong sản phẩm thật, bổ sung deadline ở lúc enqueue, chính sách hủy task, instrumentation, shutdown graceful và giới hạn pool theo downstream capacity. Đừng mở 100 thread nếu connection pool hoặc dependency chỉ xử lý an toàn 20 request song song.

## 8. Backpressure trong pipeline bất đồng bộ và message broker

### 8.1. Kafka: pause/resume phải đi cùng bounded processing

Consumer Kafka cần kiểm soát **số record được poll**, **số task đang chạy**, **số record đệm cục bộ** và thời điểm **commit offset**. Một sơ đồ xử lý:

~~~text
poll -> nhận batch có giới hạn -> enqueue bounded -> xử lý -> commit sau thành công
            |
         high watermark
            v
       pause(partitions) -- vẫn poll định kỳ cho heartbeat
            |
       in-flight <= low watermark
            v
       resume(partitions)
~~~

Các nguyên tắc thực thi:

1. Cấu hình **max.poll.records** phù hợp với phần chỗ trống trong local queue và giới hạn concurrency. Một lần poll vẫn có thể trả về nhiều record trước khi pause có hiệu lực; phải có phương án giữ an toàn toàn bộ batch vừa nhận.
2. Khi đầy, dùng **consumer.pause(assignment)** để ngừng fetch thêm từ partition đang quá tải; **vẫn poll định kỳ** để duy trì group membership và xử lý rebalance. Không chỉ ngừng vòng poll đến khi worker xử lý xong.
3. **Chỉ commit offset sau khi xử lý thành công** theo bảo đảm giao nhận mong muốn. Khi xử lý song song cùng partition, phải theo dõi các offset đã hoàn thành liên tục; không commit qua record còn đang xử lý.
4. Thiết kế idempotent consumer vì replay sau crash hoặc rebalance có thể khiến message được xử lý lại. Mở rộng consumer không tự tạo thêm partition.
5. Dùng retry topic/DLQ cho poison message sau số lần thử có giới hạn; phân biệt lỗi tạm thời với dữ liệu không hợp lệ. Đo DLQ rate và nguyên nhân.
6. Khi consumer pause lâu, theo dõi consumer lag, lag age, **max.poll.interval.ms**, thời gian rebalance và thời hạn nghiệp vụ. Việc pause là tín hiệu bảo vệ bộ nhớ local, không giải quyết backlog tích tụ mãi ở broker.

Ví dụ logic điều khiển (pseudocode, không phải mã Kafka đầy đủ):

~~~text
HIGH = 80; LOW = 30

loop:
    consumer.poll(shortTimeout)  // even when paused; maintain group activity
    if queuedPlusInFlight >= HIGH:
        consumer.pause(assignedPartitions)
    else if queuedPlusInFlight <= LOW:
        consumer.resume(assignedPartitions)

    dispatch only while local bounded capacity remains
    commit only offsets whose processing is durably complete
~~~

Logic thật phải xử lý các record vừa poll trước khi pause, backpressure per partition, rebalance callback và giới hạn thứ tự; **không được làm mất record** bằng cách bỏ qua khi queue đầy.

### 8.2. RabbitMQ: prefetch, manual ack và requeue

Với RabbitMQ, đặt **basic.qos(prefetchCount)** để giới hạn số delivery chưa ack mà consumer giữ, ví dụ prefetch = 16 khi worker pool thực sự chỉ xử lý được 16 tác vụ đồng thời. Dùng manual ack **sau khi nghiệp vụ thành công**. Khi lỗi có thể retry, dùng chính sách redelivery/backoff có giới hạn; không tạo vòng **nack → requeue ngay → nack** vô hạn. Có thể đưa message không xử lý được sang DLQ với thông tin lỗi, đồng thời theo dõi unacked, ready queue, redelivery rate và tuổi message.

### 8.3. Backpressure trong Reactive Streams

Trong một pipeline hỗ trợ demand, subscriber thông báo số phần tử có thể nhận bằng **request(n)**; publisher không nên phát vượt số demand còn lại. Khi kết hợp các operator, phải giới hạn concurrency và prefetch:

~~~java
Flux.fromIterable(commands)
    .limitRate(32)
    .flatMap(command -> callDownstream(command), 8, 16);
~~~

Ở ví dụ Reactor này, **8** là số inner publisher có thể đang hoạt động; **16** là tham số prefetch của flatMap. Các giới hạn này cần được đặt theo tài nguyên downstream. Backpressure nội bộ của stream **không tự lan qua HTTP endpoint, broker hoặc một API khác** nếu adapter ở biên không chuyển tín hiệu demand thành giới hạn nhận tải.

Nếu gọi downstream blocking trên thread event loop, backpressure không cứu được event loop bị chặn. Phải dùng client bất đồng bộ thích hợp hoặc scheduler dành riêng cho blocking work, có giới hạn queue và số thread.

## 9. Load shedding, công bằng và ưu tiên

Khi đã quá giới hạn, việc **reject sớm** có thể giúp throughput thành công cao hơn việc cố nhận mọi yêu cầu rồi tất cả cùng timeout. Nên ưu tiên công việc theo SLA nhưng tránh làm nhóm traffic ít ưu tiên bị đói vô hạn.

Ví dụ chia admission budget cho một API quan trọng:

- 60% capacity dành cho interactive requests có deadline ngắn.
- 30% capacity dành cho nghiệp vụ nền cần độ tin cậy cao.
- 10% capacity cho tác vụ maintenance hoặc best effort; có thể tạm giảm trong sự cố.

Các tỷ lệ chỉ là cấu hình minh họa. Có thể dùng **per-tenant concurrency budget**, weighted fair queue và một phần capacity dự phòng dùng chung. Nếu tenant A phát 10.000 request, không để một FIFO queue duy nhất khiến tenant B chỉ có 10 request cũng chờ hết deadline. Nếu có priority queue, phải có aging hoặc quota để tránh starvation.

Các chiến lược giảm tải an toàn gồm trả dữ liệu cache đã được chấp thuận, bỏ phần enrich không thiết yếu, giới hạn kích thước batch, giảm tần suất refresh và hoãn công việc không gấp. Không bỏ bước xác thực, ủy quyền, ghi sổ thanh toán hoặc audit bắt buộc chỉ để giảm độ trễ.

## 10. Quan sát hệ thống: đo cả áp lực lẫn kết quả

Bộ metric tối thiểu cho mỗi hàng đợi, dependency và instance:

| Metric | Diễn giải | Dấu hiệu cần điều tra |
| --- | --- | --- |
| queue_depth | Số mục đang chờ | Tăng liên tục dù incoming rate không đổi |
| queue_oldest_age_seconds | Thời gian chờ của mục cũ nhất | Gần hoặc vượt SLA/deadline |
| in_flight | Số công việc đang chạy | Sát ngưỡng bulkhead trong thời gian dài |
| worker_utilization | Mức sử dụng worker | Luôn 100% hoặc dao động bất thường |
| accepted_total / rejected_total | Tỷ lệ nhận và từ chối | Rejection tăng mạnh, đặc biệt theo tenant |
| dequeue_rate / completion_rate | Năng lực xử lý và hoàn tất | Completion giảm dù traffic chưa đổi |
| queue_wait_seconds p95/p99 | Tail latency trong queue | Gần hết budget trước khi chạy |
| request_latency_seconds p95/p99 | Latency đầu cuối | Vượt SLO khi backlog tăng |
| timeout_total / retry_total | Timeout và retry amplification | Retry tăng nhanh hơn request gốc |
| downstream_pool_active / pending | Connection hoặc client pool pressure | Pool cạn; nhiều thao tác chờ connection |
| consumer_lag / lag_age | Backlog của Kafka consumer | Tuổi lag tăng nhanh hơn tốc độ drain |
| messages_unacked / DLQ | RabbitMQ hoặc job reliability | Unacked cao, poison message lặp lại |

**Phân tách theo service, endpoint, queue và kết quả** nhưng tránh gắn trực tiếp request ID, user ID hoặc key duy nhất vào nhãn metric để không làm nổ cardinality. Dùng trace/log có sampling cho từng request cụ thể. Dashboard hữu ích nên đặt **incoming rate, accepted rate, completed rate, rejection rate, queue age và p99 latency** cùng một mốc thời gian.

Alert nên dựa vào hậu quả thay vì chỉ một ngưỡng queue cố định. Ví dụ: oldest age vượt 50% budget trong 5 phút **và** completion rate thấp hơn ingress; hoặc error budget/SLO đang bị tiêu thụ nhanh. Với hệ thống batch, alert vào nguy cơ không kịp deadline hoặc thời gian dự kiến để drain backlog; với API đồng bộ, theo dõi p99 latency và tỷ lệ 503/429 song song.

## 11. Thiết kế retry và timeout để không khuếch đại tải

Một lời gọi có 3 tầng, mỗi tầng retry 3 lần, trong trường hợp xấu có thể tạo **3 × 3 × 3 = 27 lần gọi** xuống dependency cuối. Hãy chỉ định nơi sở hữu retry, tránh mỗi lớp đều tự retry. Áp dụng:

1. **Bounded retries:** giới hạn số lần, tổng thời gian và ngân sách retry trên toàn hệ thống.
2. **Exponential backoff + full jitter:** tránh retry đồng pha.
3. **Deadline propagation:** request con không được phép chạy lâu hơn thời gian còn lại của request cha.
4. **Idempotency:** POST thanh toán/đơn hàng phải có key hoặc cơ chế chống ghi trùng nếu có retry; lỗi timeout không chứng minh phía server chưa thực hiện giao dịch.
5. **Circuit breaker + admission:** dependency lỗi thì fail fast; khi phục hồi cho thử lại có kiểm soát thay vì xả toàn bộ queue tức thì.
6. **Retry-After / server hint:** tuân thủ khi phù hợp, nhưng không dùng một thời điểm cố định khiến mọi client cùng dồn lại.

Timeout ở client đơn thuần có thể chỉ chấm dứt chờ phản hồi; tác vụ server vẫn chạy. Cần hỗ trợ hủy ở tầng application, query timeout của DB hoặc cơ chế kiểm tra deadline để thật sự thu hồi tài nguyên.

## 12. Autoscaling và khôi phục sau quá tải

Autoscaling nên xem **queue age, backlog drain time, CPU, memory và dependency saturation** thay vì chỉ tăng replica theo queue depth. Với backlog B và năng lực xử lý ròng (completion − incoming) dương, thời gian drain gần đúng **B / (completion − incoming)**. Nếu ròng không dương, backlog không thể tự hết.

Khi scale consumer từ 4 lên 20 instance, cần xét số Kafka partition, connection tổng đến DB, quota API đối tác, cold start và thời gian rebalance. Nếu DB chịu tối đa 200 concurrent query, tăng consumer vô hạn chỉ chuyển nút nghẽn sang DB. Giới hạn tổng concurrency ở tầng dùng DB và cân nhắc một số worker dự phòng nhưng không vượt ngân sách dependency.

Trình tự phục hồi nên là: ổn định dependency → duy trì shed/limit → khôi phục dần admission → theo dõi oldest age và p99 → cho backlog drain có kiểm soát. Không mở toàn bộ cổng nhận tải ngay khi CPU vừa giảm; có thể gây đợt quá tải thứ hai.

## 13. Các lỗi thiết kế phổ biến

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng unbounded queue vì sợ mất request | OOM, latency tăng vô hạn | Giới hạn queue; có đường trả lỗi hoặc ghi bền vững |
| Queue quá lớn so với deadline | Request hết hạn trước khi được xử lý | Sizing theo wait budget và oldest age |
| Retry ngay khi nhận 503 | Retry storm khuếch đại tải | Backoff, jitter, retry budget, idempotency |
| Mọi tầng cùng retry | Số call nhân lên theo số tầng | Chỉ định một tầng sở hữu retry |
| Pool xử lý lớn hơn downstream connection capacity | Chờ connection, timeout dây chuyền | Bulkhead theo dependency thực tế |
| Kafka pause rồi ngừng poll hoàn toàn | Mất group membership hoặc rebalance | Vẫn poll định kỳ và quản lý interval |
| Commit offset khi mới enqueue | Crash gây mất công việc chưa xử lý | Commit sau completion bền vững |
| RabbitMQ requeue ngay vô hạn | Poison-message loop | Retry có trì hoãn, giới hạn, DLQ |
| Chỉ đo queue depth | Bỏ sót các message chờ quá lâu | Đo oldest age, throughput và p99 |
| Autoscale không xét database | Dồn tải nhiều hơn vào nút nghẽn | Cap concurrency toàn cụm và test |
| Bỏ task không có thống kê | Không biết dữ liệu đã bị mất | Đo dropped/rejected và phân loại nghiệp vụ |
| Dùng Reactive Streams nhưng chặn event loop | Tắc toàn bộ pipeline | I/O bất đồng bộ hoặc bounded blocking scheduler |

## 14. Kịch bản kiểm thử tải và sự cố

Thử tải phải tạo được **overload thật** và kiểm tra hành vi khi quá tải, thay vì chỉ xác nhận throughput cực đại:

1. **Baseline:** chạy dưới capacity (ví dụ 40 request/giây với C ≈ 80), đo p50/p95/p99, queue wait và resource usage.
2. **Near saturation:** tăng đến khoảng 80 request/giây, theo dõi hàng đợi và thời gian hoàn thành; ghi nhận năng lực bền vững thật, không mặc định bằng tính toán.
3. **Sustained overload:** giữ 120 request/giây đủ lâu; queue phải **có trần**, rejected rate tăng có kiểm soát, process không OOM, phần request được nhận vẫn đạt mục tiêu trong khả năng.
4. **Burst:** đẩy tải cao trong 1–2 giây rồi hạ về baseline; xác nhận queue hấp thụ burst trong ngân sách latency và drain được.
5. **Slow dependency:** cố ý tăng độ trễ DB/API thứ ba; xác nhận bulkhead, circuit breaker và deadline ngăn lỗi lan sang API không phụ thuộc.
6. **Retry storm:** tạo nhiều client cùng gặp 503; kiểm tra backoff/jitter và ngân sách retry, bảo đảm không khuếch đại traffic quá mức.
7. **Worker crash / rebalance:** kill consumer khi đang xử lý; xác nhận ack/commit và idempotency ngăn mất dữ liệu hoặc tác động trùng.
8. **Recovery:** trả dependency về bình thường, kiểm tra tốc độ drain backlog, p99, oldest age và giới hạn concurrency khi mở nhận tải.

Tiêu chí hệ thống đạt mục tiêu phụ thuộc SLO cụ thể, nhưng tối thiểu cần chứng minh: **tài nguyên nằm trong giới hạn, không tích tụ vô hạn, lỗi quá tải rõ ràng, tác vụ quan trọng không mất âm thầm, và hệ thống tự phục hồi khi tải giảm**. Phân biệt lỗi dự kiến do shed có kiểm soát với lỗi timeout/OOM không kiểm soát.

## 15. Hướng dẫn chọn chiến lược nhanh

**Nếu là API đồng bộ:** ưu tiên giới hạn in-flight gần dependency, queue rất ngắn hoặc bằng 0, deadline rõ ràng và HTTP 429/503 sớm. Đừng cố lưu request trong RAM lâu hơn thời gian client chấp nhận.

**Nếu là job bắt buộc xử lý:** chấp nhận vào hệ thống **sau khi đã ghi bền vững**; trả job ID, giới hạn producer/consumer throughput, bảo đảm ack/commit và idempotency. Theo dõi queue age thay cho chỉ số message count đơn lẻ.

**Nếu là stream dữ liệu:** dùng demand/request(n), giới hạn prefetch/concurrency ở mỗi operator, và chuyển tín hiệu áp lực qua các biên HTTP/broker. Quy định chính sách overflow theo loại dữ liệu.

**Nếu là hệ thống multi-tenant:** thêm quota và fairness theo tenant, phân bổ capacity quan trọng, bảo vệ dependency chung. Tính giới hạn ở toàn cụm.

**Nếu thường xuyên quá tải:** trước khi tăng queue, tìm nút nghẽn bằng số liệu; giảm việc không thiết yếu, tối ưu critical path, tăng capacity trong giới hạn downstream, đồng thời thiết kế cơ chế từ chối/hoãn tải rõ ràng.

## 16. Checklist triển khai cho một microservice

- [ ] Xác định dependency khan hiếm nhất, throughput bền vững, max in-flight và deadline end-to-end.
- [ ] Đặt capacity hữu hạn cho từng queue và giới hạn riêng số task đang chạy; kiểm tra tổng trên mọi replica.
- [ ] Định nghĩa overflow policy theo nghiệp vụ; chọn 429/503, durable job hoặc shed có kiểm soát.
- [ ] Có timeout, cancellation và deadline propagation; không để tác vụ hết hạn tiêu tốn thêm tài nguyên.
- [ ] Tách retry policy, thêm backoff/jitter, retry budget và idempotency.
- [ ] Với broker, thiết kế prefetch/pause/resume, manual ack/commit, replay, retry có giới hạn và DLQ.
- [ ] Có metric queue depth, oldest age, accepted/completed/rejected, in-flight, p99, lag và dependency pool.
- [ ] Test burst, sustained overload, slow downstream, crash/rebalance và hồi phục backlog.
- [ ] Viết runbook: khi nào giảm ingress, khi nào scale, khi nào mở lại, ai chịu trách nhiệm backlog.
- [ ] Xác nhận giới hạn không làm mất dữ liệu bắt buộc và vẫn giữ dịch vụ quan trọng phục vụ được.

**Nguyên lý cần ghi nhớ:** Chỉ nhận lượng công việc mà hệ thống có thể hoàn thành trong **ngân sách thời gian và tài nguyên đã cam kết**. Khi quá tải kéo dài, phản hồi giới hạn hoặc hoãn công việc có chủ đích sẽ bảo vệ toàn bộ chuỗi microservices tốt hơn việc cho hàng đợi phát triển không kiểm soát.
