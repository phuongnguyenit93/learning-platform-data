# Giới hạn consumer concurrency và tốc độ xử lý queue

Một queue có thể nhận message nhanh hơn tốc độ consumer xử lý. Nếu consumer mở quá nhiều invocation, database hoặc API phía sau có thể quá tải. Nếu consumer xử lý quá ít, backlog và tuổi message tăng cho đến khi công việc vượt SLA. Vì vậy, hệ thống cần điều tiết cả số công việc đang chạy đồng thời và tốc độ tiếp nhận công việc mới.

Hai khái niệm cần tách biệt:

- **Concurrency:** số message hoặc tác vụ đang được xử lý cùng lúc.
- **Processing rate:** số message hoàn tất trong một đơn vị thời gian, thường là message/giây.

Giới hạn concurrency bảo vệ tài nguyên bằng cách giới hạn số công việc đang in-flight. Rate limit giới hạn tốc độ bắt đầu hoặc gọi một dependency trong một khoảng thời gian. Một consumer có thể có concurrency thấp nhưng vẫn tạo rate cao nếu mỗi message xử lý rất nhanh; ngược lại, concurrency cao với message xử lý lâu có thể tạo throughput thấp.

Bài học này trình bày cách đặt giới hạn cho Java serverless consumer, phối hợp autoscaling với queue, áp dụng backpressure và rate limiting, cùng các cách cấu hình phổ biến trên SQS, Pub/Sub và Kafka.

## 1. Vì sao cần điều tiết consumer?

Giả sử producer gửi 1.000 message/giây trong khi database chỉ chịu được 200 thao tác ghi/giây. Nếu consumer mở rộng không giới hạn, queue có thể giảm nhanh nhưng database bị nghẽn, connection pool cạn và request khác cũng thất bại.

Nếu đặt concurrency quá thấp, database được bảo vệ nhưng queue backlog tăng, message age vượt SLA và hệ thống không thể phục hồi sau burst.

Điều tiết tải cần cân bằng ba mục tiêu:

1. Giữ downstream dependency trong giới hạn an toàn.
2. Đạt throughput đủ để xử lý arrival rate và backlog.
3. Duy trì latency/message age trong SLO.

~~~mermaid
flowchart TD
    P["Producer"] --> Q["Queue"]
    Q --> C["Consumer scaling"]
    C --> L["Concurrency / rate controls"]
    L --> W["Java worker"]
    W --> D["Database / API"]
    D --> W
    W --> A["Ack / delete"]
    A --> Q
    L -. "Backpressure khi quá tải" .-> C
~~~

Không có một giá trị concurrency đúng cho mọi hệ thống. Cần đo thời gian xử lý, khả năng của dependency, batch size, giới hạn nền tảng và SLO trước khi chọn.

## 2. Concurrency khác processing rate như thế nào?

Concurrency là số công việc đồng thời đang chạy. Processing rate là số công việc hoàn tất trong một giây. Hai đại lượng liên hệ với nhau thông qua thời gian xử lý.

Nếu một consumer xử lý một message mất trung bình \(d\) giây và duy trì \(c\) message đồng thời, throughput lý tưởng gần đúng là:

\[
\mu \approx \frac{c}{d}
\]

Nếu xử lý theo batch \(b\) message mỗi lần, throughput lý tưởng có thể gần:

\[
\mu \approx \frac{c \times b}{d_{\text{batch}}}
\]

Đây chỉ là ước lượng. Thực tế còn bị giới hạn bởi CPU, memory, thread pool, connection pool, broker, network và downstream quota.

Ví dụ:

| Concurrency | Thời gian xử lý trung bình | Throughput lý tưởng |
|---:|---:|---:|
| 10 | 0,5 giây | 20 message/giây |
| 20 | 0,5 giây | 40 message/giây |
| 20 | 0,2 giây | 100 message/giây |
| 50 | 1 giây | 50 message/giây |

Tăng concurrency không đảm bảo throughput tăng tuyến tính. Nếu dependency bắt đầu throttling, thời gian xử lý tăng lên và throughput có thể đứng yên hoặc giảm.

### 2.1. Little's Law và số công việc in-flight

Little's Law mô tả quan hệ giữa số công việc trung bình trong hệ thống \(L\), tốc độ đến \(\lambda\) và thời gian lưu lại trung bình \(W\):

\[
L = \lambda \times W
\]

Ví dụ, hệ thống nhận 100 message/giây và mỗi message mất trung bình 0,4 giây, số message đang xử lý trung bình cần khoảng:

\[
L = 100 \times 0,4 = 40
\]

Nếu muốn duy trì throughput 100 message/giây với thời gian xử lý 0,4 giây, cần capacity xử lý xấp xỉ 40 message đồng thời, giả sử không có bottleneck khác.

Đây là quan hệ trung bình trong trạng thái ổn định, không phải giá trị max concurrency cần cấu hình trực tiếp. Hãy bổ sung headroom có kiểm soát và đo tail latency, vì p95/p99 thường lớn hơn thời gian trung bình.

## 3. Xác định giới hạn từ dependency

Consumer thường gọi nhiều dependency. Mỗi dependency có capacity và quota riêng:

- Database có giới hạn connection, transaction và write throughput.
- Payment provider có request-per-second quota.
- Email/SMS provider có tốc độ gửi tối đa.
- API nội bộ có giới hạn concurrency hoặc rate.
- Object storage có request rate và network throughput.
- Message broker có giới hạn pull, ack và connection.

Hãy xác định dependency nào là bottleneck trước khi đặt consumer concurrency.

Ví dụ một Java worker có thể đồng thời xử lý 40 message nhưng mỗi message gọi 2 API và mở một transaction database. Nếu database chỉ chịu được 60 transaction đồng thời, giới hạn an toàn của worker cần tính đến các workload khác cùng chia sẻ database.

Một công thức capacity planning đơn giản:

\[
C_{\text{consumer}} \leq
\min(C_{\text{compute}}, C_{\text{database}}, C_{\text{API}}, C_{\text{broker}})
\]

Các giới hạn phải được quy đổi về cùng đơn vị và cùng phạm vi. Ví dụ giới hạn database là connection count, API là request/second và broker là message/second; không thể lấy min trực tiếp nếu chưa quy đổi theo số thao tác mỗi message.

### 3.1. Phân bổ ngân sách concurrency

Nếu nhiều consumer cùng gọi một database, đừng để mỗi consumer tự dùng toàn bộ connection capacity.

Ví dụ database có thể dành tối đa 120 connection cho nhóm serverless worker. Ba consumer cùng hoạt động cần chia ngân sách đó, đồng thời chừa connection cho API và tác vụ quản trị.

| Workload | Ngân sách connection ví dụ |
|---|---:|
| orders-worker | 40 |
| billing-worker | 30 |
| inventory-worker | 30 |
| Dự phòng và tác vụ vận hành | 20 |
| Tổng | 120 |

Đây là ví dụ phân bổ, không phải khuyến nghị chung. Cần tính cả số instance, connection pool mỗi instance và các workload không serverless.

Nếu mỗi instance có pool tối đa 10 connection và autoscaler có thể tạo 20 instance, tổng connection tiềm năng là 200. Chỉ đặt pool size nhỏ ở từng instance vẫn có thể vượt giới hạn database khi scale-out.

## 4. Ba lớp giới hạn tải

Một thiết kế tốt thường điều tiết ở nhiều lớp:

| Lớp | Kiểm soát | Mục đích |
|---|---|---|
| Nền tảng/function | Reserved concurrency, max instances, max scale | Giới hạn tổng số invocation hoặc instance |
| Queue/event source | Polling, flow control, batch size, max concurrency | Giới hạn lượng message giao cho consumer |
| Ứng dụng Java | Semaphore, bounded executor, rate limiter, bulkhead | Giới hạn công việc và lời gọi dependency bên trong process |

Không phải hệ thống nào cũng cần cả ba lớp. Nhưng khi nhiều consumer chia sẻ một dependency, chỉ giới hạn tại một process có thể chưa đủ vì tổng concurrency tăng theo số instance.

Ví dụ nếu mỗi instance cho phép 10 message đồng thời và autoscaler tạo 15 instance, tổng concurrency có thể lên đến 150. Nếu database chỉ chịu được 60 thao tác đồng thời, cần giảm concurrency mỗi instance, giới hạn max instances hoặc dùng rate limiter phân tán theo ngân sách chung.

## 5. Backpressure là gì?

Backpressure là cơ chế làm chậm hoặc tạm ngừng việc nhận công việc mới khi consumer hoặc dependency không còn đủ capacity.

Không có backpressure, consumer có thể tiếp tục nhận message rồi đưa vào thread pool hoặc memory queue nội bộ. Queue bên ngoài có vẻ giảm nhưng backlog thực chất chỉ chuyển vào heap của process. Khi process bị restart hoặc OOM, công việc đang giữ trong memory có thể mất hoặc bị xử lý lại.

Các nguyên tắc:

- Chỉ nhận số message mà consumer có thể xử lý trong giới hạn an toàn.
- Dùng queue/buffer có giới hạn.
- Khi downstream chậm, giảm poll hoặc tạm dừng nhận message.
- Không tạo thread hoặc future không giới hạn cho mỗi message.
- Chỉ ack sau khi xử lý hoặc lưu công việc vào nơi bền vững theo policy.
- Theo dõi cả backlog broker và in-flight trong process.

Backpressure có thể được áp dụng bằng cách giảm polling, pause partition, giới hạn outstanding messages, giảm autoscaling hoặc từ chối request mới bằng lỗi retryable phù hợp.

### 5.1. Không ack quá sớm

Nếu consumer ack message ngay khi đưa nó vào một executor nội bộ rồi process chết trước khi xử lý, broker nghĩ message đã hoàn tất và không giao lại. Vì vậy:

- Với xử lý đồng bộ, ack sau khi side effect commit.
- Với xử lý bất đồng bộ, ghi message vào một store/queue bền vững trước khi ack.
- Không coi việc submit vào in-memory executor là durable acceptance.

Nếu dùng batch, phải tuân theo semantics partial failure của event source. Không ack cả batch khi chỉ một phần message đã xử lý thành công nếu event source không hỗ trợ cơ chế phù hợp.

## 6. Rate limiting khác concurrency limiting

Concurrency limiter giới hạn số tác vụ đang chạy cùng lúc. Rate limiter giới hạn số thao tác bắt đầu trong một khoảng thời gian.

Ví dụ:

- Concurrency cap: tối đa 20 payment request đang chạy.
- Rate limit: tối đa 50 payment request mỗi giây.
- Cả hai: tối đa 20 request đồng thời và 50 request/giây.

Một API có thể chịu 50 request/giây nhưng chỉ cho phép 5 request đồng thời vì mỗi request mất nhiều thời gian. Một API khác có thể cho phép 100 request đồng thời nhưng quota chỉ 20 request/giây.

### 6.1. Token bucket

Token bucket là thuật toán rate limiting phổ biến:

- Bucket có dung lượng tối đa \(B\) token.
- Token được bổ sung theo tốc độ \(r\) token/giây.
- Mỗi request tiêu thụ một hoặc nhiều token.
- Nếu không đủ token, request phải chờ hoặc bị từ chối.

Bucket cho phép burst ngắn đến dung lượng \(B\), nhưng giới hạn tốc độ trung bình dài hạn theo \(r\).

Ví dụ bucket có capacity 20 token và refill 10 token/giây. Hệ thống có thể nhận burst 20 request khi bucket đầy, sau đó tốc độ bền vững xấp xỉ 10 request/giây.

Token bucket không tự giới hạn thời gian xử lý đồng thời. Nếu request kéo dài, cần thêm concurrency limiter.

### 6.2. Fixed window, sliding window và leaky bucket

| Thuật toán | Cách hoạt động | Đặc điểm |
|---|---|---|
| Fixed window | Đếm request trong từng cửa sổ thời gian cố định | Đơn giản nhưng có thể burst ở ranh giới hai cửa sổ |
| Sliding window | Tính request trong cửa sổ trượt | Mượt hơn nhưng cần lưu lịch sử hoặc counter phức tạp hơn |
| Token bucket | Token được nạp theo tốc độ | Cho phép burst có giới hạn |
| Leaky bucket | Xử lý request theo tốc độ đều | Làm phẳng burst, tạo tốc độ đầu ra ổn định |

Chọn thuật toán theo quota của dependency và hành vi burst mà hệ thống có thể chấp nhận. Nếu nhiều instance cần chia sẻ một quota toàn cục, rate limiter trong memory của từng instance không đủ.

## 7. Giới hạn trong một Java process

Java worker có thể dùng Semaphore để giới hạn số thao tác đồng thời gọi một dependency. Ví dụ dưới đây chỉ minh họa bulkhead đồng bộ:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class InventoryBulkhead {

    private final Semaphore permits = new Semaphore(8, true);
    private final InventoryClient client;

    public InventoryBulkhead(InventoryClient client) {
        this.client = client;
    }

    public InventoryResult reserve(
            String sku,
            int quantity,
            long waitMillis) throws InterruptedException {

        boolean acquired = permits.tryAcquire(
                waitMillis, TimeUnit.MILLISECONDS);

        if (!acquired) {
            throw new DependencyBusyException(
                    "Inventory concurrency limit reached");
        }

        try {
            return client.reserve(sku, quantity);
        } finally {
            permits.release();
        }
    }
}
~~~

Semaphore giới hạn tối đa 8 lời gọi đồng thời trong một process. finally bảo đảm permit được trả lại kể cả khi dependency ném exception.

Nếu dùng async API, phải giữ permit cho đến khi future hoàn tất, không release ngay sau khi tạo future. Với virtual thread, vẫn cần giới hạn dependency concurrency; khả năng tạo nhiều thread nhẹ không làm database hoặc API bên ngoài chịu tải vô hạn.

Semaphore trong memory không phối hợp giữa các instance. Nếu có 10 instance, mỗi instance 8 permit, tổng số lời gọi đồng thời có thể đạt 80.

### 7.1. Bounded executor

Một thread pool có queue không giới hạn có thể giữ rất nhiều task trong heap khi producer nhanh hơn consumer. Dùng bounded queue và chính sách từ chối rõ ràng.

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class WorkerPool {

    public static ThreadPoolExecutor create() {
        return new ThreadPoolExecutor(
                8,
                8,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(100),
                new ThreadPoolExecutor.AbortPolicy()
        );
    }
}
~~~

Khi cả 8 thread và 100 queue slot đều đầy, AbortPolicy ném RejectedExecutionException. Caller cần chuyển tình trạng này thành backpressure/retryable outcome phù hợp với queue trigger.

Không dùng DiscardPolicy cho message nghiệp vụ vì task có thể bị bỏ mà không có ack/retry rõ ràng. CallerRunsPolicy có thể làm chậm thread submitter, nhưng cần hiểu thread đó có phải thread xử lý event hay không và có làm vi phạm timeout của runtime không.

## 8. Rate limiter trong ứng dụng Java

Có thể dùng thư viện rate limiter như Resilience4j để giới hạn tốc độ gọi dependency. Ví dụ minh họa:

~~~java
import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.ratelimiter.RateLimiterConfig;

import java.time.Duration;
import java.util.function.Supplier;

public final class PaymentGateway {

    private final RateLimiter rateLimiter;
    private final PaymentClient client;

    public PaymentGateway(PaymentClient client) {
        this.client = client;

        RateLimiterConfig config = RateLimiterConfig.custom()
                .limitForPeriod(20)
                .limitRefreshPeriod(Duration.ofSeconds(1))
                .timeoutDuration(Duration.ofMillis(100))
                .build();

        this.rateLimiter = RateLimiter.of("payment-provider", config);
    }

    public PaymentResult charge(PaymentRequest request) {
        Supplier<PaymentResult> operation =
                RateLimiter.decorateSupplier(
                        rateLimiter,
                        () -> client.charge(request));

        return operation.get();
    }
}
~~~

Cấu hình trên giới hạn khoảng 20 lần cấp quyền trong mỗi chu kỳ một giây cho một instance của limiter. Nó không đảm bảo toàn bộ hệ thống chỉ gửi 20 request/giây nếu nhiều instance cùng chạy.

Khi limiter không cấp quyền trong thời gian chờ, ứng dụng cần quyết định có trả lỗi retryable, đưa message về queue hay trì hoãn xử lý. Không sleep dài trong Lambda invocation để chờ quota nếu có thể để broker giữ message và giao lại sau.

## 9. Giới hạn toàn cục giữa nhiều instance

Nếu quota của dependency là toàn cục, các instance cần phối hợp. Có một số cách:

- Chia quota tĩnh cho từng instance theo max instance count.
- Dùng distributed token bucket trong Redis hoặc một store có atomic operation.
- Dùng API gateway/service proxy làm điểm điều tiết chung.
- Dùng queue riêng cho dependency và một consumer pool được giới hạn.
- Dùng provider-side quota/rate limit làm lớp bảo vệ cuối cùng.

Ví dụ quota provider 100 request/giây và tối đa 10 instance. Chia đều 10 request/giây cho mỗi instance là cách đơn giản, nhưng có thể lãng phí nếu một số instance không hoạt động. Distributed limiter tận dụng quota tốt hơn nhưng thêm dependency và latency.

Nếu distributed limiter không khả dụng, cần policy fail-open hay fail-closed rõ ràng. Với payment hoặc thao tác có quota nghiêm ngặt, fail-closed có thể bảo vệ provider nhưng làm backlog tăng. Với metric hoặc cache warming, fail-open có thể phù hợp hơn.

Không giả định một Redis counter đơn giản tự động là rate limiter chính xác. Cần atomic update, TTL, xử lý clock, burst capacity và khả năng chịu lỗi của limiter.

## 10. Điều tiết Lambda consumer với SQS

Khi Lambda đọc SQS qua event source mapping, concurrency được điều khiển bởi nhiều cấu hình:

- **Reserved concurrency của function:** giới hạn tổng số invocation đồng thời của function, chia sẻ giữa các event source mapping và các nguồn gọi khác.
- **Maximum concurrency của event source mapping:** giới hạn số invocation đồng thời được phép từ mapping đó; với SQS, cấu hình này áp dụng cho standard queue mapping. FIFO queue có parallelism phụ thuộc số message group đang hoạt động và ordering semantics.
- **Batch size:** số message tối đa trong một batch.
- **Maximum batching window:** thời gian chờ gom batch trước khi invoke.
- **Event source scaling:** nền tảng tự tăng/giảm poller và invocation theo backlog cùng cấu hình.
- **FIFO message groups:** giới hạn song song theo số message group đang hoạt động và ordering semantics.

Đừng nhầm reserved concurrency với rate limit. Reserved concurrency giới hạn số invocation đồng thời; processing rate còn phụ thuộc duration và batch size.

### 10.1. Phối hợp reserved concurrency và maximum concurrency

Giả sử function có hai SQS event source mapping:

- Mapping orders có maximum concurrency 20.
- Mapping refunds có maximum concurrency 10.
- Function reserved concurrency là 25.

Hai mapping có thể cùng cạnh tranh trong tổng ngân sách 25 invocation. Nếu cần bảo đảm capacity riêng, có thể tách function hoặc phân bổ concurrency phù hợp.

Một nguyên tắc vận hành là tổng maximum concurrency dự kiến của các mapping không nên vượt reserved concurrency theo cách gây starvation ngoài ý muốn. Reserved concurrency còn có thể bị các invoker khác dùng nếu function được gọi từ nhiều nguồn.

Maximum concurrency là giới hạn theo event source mapping, không phải số request/giây. Với batch size lớn, mỗi invocation có thể xử lý nhiều message. Đo actual message throughput để biết hiệu quả thực tế.

### 10.2. FIFO queue và message group

SQS FIFO duy trì ordering trong từng message group. Messages thuộc cùng một group được xử lý tuần tự; nhiều group khác nhau có thể được xử lý song song.

Nếu queue chỉ có một message group đang hoạt động, tăng Lambda concurrency không tạo thêm parallelism cho group đó. Nếu có 100 group độc lập, nhiều group có thể được xử lý song song trong giới hạn mapping và function.

Test các trường hợp:

- Một group có nhiều message: giữ đúng thứ tự.
- Nhiều group: cho phép song song giữa group.
- Một group bị message lỗi: xác định ảnh hưởng đến message tiếp theo cùng group.
- Thêm concurrency: không phá ordering trong group.
- Retry: không tạo side effect trùng.

## 11. Điều tiết Pub/Sub subscriber

Google Pub/Sub subscriber client có flow control để giới hạn số message outstanding và tổng byte outstanding mà client đang giữ trước khi ack.

Với Java client, cấu hình FlowControlSettings cho phép đặt giới hạn số element và byte. Khi đạt giới hạn, subscriber có thể block việc nhận thêm message hoặc áp dụng hành vi limit được chọn.

Ví dụ cấu hình minh họa:

~~~java
import com.google.api.gax.batching.FlowControlSettings;
import com.google.api.gax.batching.FlowController.LimitExceededBehavior;
import com.google.cloud.pubsub.v1.MessageReceiver;
import com.google.cloud.pubsub.v1.Subscriber;
import com.google.pubsub.v1.ProjectSubscriptionName;

public final class OrdersSubscriber {

    public Subscriber create(
            String projectId,
            String subscriptionId,
            MessageReceiver receiver) {

        ProjectSubscriptionName name =
                ProjectSubscriptionName.of(projectId, subscriptionId);

        FlowControlSettings flowControl =
                FlowControlSettings.newBuilder()
                        .setMaxOutstandingElementCount(200L)
                        .setMaxOutstandingRequestBytes(20L * 1024 * 1024)
                        .setLimitExceededBehavior(
                                LimitExceededBehavior.Block)
                        .build();

        return Subscriber.newBuilder(name, receiver)
                .setFlowControlSettings(flowControl)
                .build();
    }
}
~~~

Tên API và overload có thể khác theo phiên bản Google Cloud Pub/Sub Java client. Đây là ví dụ cấu hình ý tưởng; kiểm tra dependency version đang dùng. Flow control giới hạn lượng message client giữ outstanding, không phải quota request/giây của một API downstream.

Khi callback receiver xử lý bất đồng bộ, chỉ ack khi công việc hoàn tất theo semantics của ứng dụng. Nếu callback trả về ngay sau khi submit vào executor, Pub/Sub có thể xem message đã hoàn tất trong khi worker chưa xử lý xong.

### 11.1. Ack deadline và parallelism

Flow control cần phối hợp với ack deadline, ack extension, executor concurrency và thời gian xử lý. Nếu outstanding limit quá cao, client có thể giữ quá nhiều message trong memory. Nếu quá thấp, throughput giảm và subscriber không tận dụng được capacity.

Theo dõi outstanding message count/bytes, ack latency, redelivery, oldest unacked age và callback processing duration. Điều chỉnh từng thông số trong load test thay vì tăng tất cả cùng lúc.

## 12. Điều tiết Kafka consumer

Kafka consumer thường được điều tiết qua:

- Số partition của topic.
- Số consumer trong group.
- Số record lấy trong một lần poll (max.poll.records).
- Khoảng thời gian tối đa giữa các lần poll (max.poll.interval.ms).
- Cơ chế pause/resume partition.
- Số worker xử lý song song và cách commit offset.
- Giới hạn downstream concurrency/rate.

Parallelism của consumer group bị giới hạn bởi số partition đang được gán. Nếu topic có 8 partition, tăng số consumer lên 20 không làm một group xử lý song song 20 partition; một số consumer sẽ idle.

Nếu xử lý record bất đồng bộ, phải bảo đảm commit offset không vượt qua record chưa xử lý thành công theo semantics ordering và retry đã chọn. Commit sớm có thể làm mất record khi process chết. Commit quá muộn có thể gây redelivery và duplicate.

### 12.1. Pause và resume

Khi downstream quá tải, consumer có thể pause một hoặc nhiều partition để ngừng fetch record mới, tiếp tục xử lý record đã nhận và resume khi capacity hồi phục.

Không block consumer thread quá lâu nếu điều đó khiến poll interval vượt giới hạn và group rebalance. Với client Java, cần thiết kế poll loop tiếp tục được gọi đúng nhịp trong khi worker pool xử lý record; việc pause/resume và commit phải đồng bộ theo API Kafka.

Nếu cần giữ ordering theo partition, xử lý record trong một partition theo thứ tự hoặc quản lý sequence/offset hoàn tất trước khi commit. Không dùng thread pool song song tùy tiện rồi commit offset cao nhất khi các record trước đó còn pending.

## 13. Batch size: throughput và failure blast radius

Batch lớn có thể giảm overhead invocation và tăng throughput. Nhưng batch lớn cũng:

- Tăng memory cần cho payload.
- Làm thời gian xử lý một invocation dài hơn.
- Tăng số message bị retry nếu batch-level failure.
- Có thể tăng tail latency vì phải chờ gom batch.
- Làm một poison message ảnh hưởng nhiều message tốt.

Batch size nhỏ giảm blast radius và latency gom batch nhưng tăng overhead và số invocation.

Chọn batch size bằng load test theo loại message, processing duration và partial failure semantics. Nếu message có độ lớn không đồng đều, cần giới hạn cả số lượng lẫn tổng byte.

### 13.1. Partial batch failure

Với event source hỗ trợ partial batch response, consumer có thể báo những record lỗi để broker chỉ giao lại phần cần retry. Nếu không hỗ trợ, một lỗi trong batch có thể khiến cả batch được giao lại.

Consumer cần idempotent vì record đã xử lý thành công có thể xuất hiện lại khi batch retry. Dùng event ID hoặc idempotency key ổn định và lưu kết quả xử lý bền vững.

Không bắt exception rồi trả success cho cả batch nếu message lỗi chưa được lưu vào DLQ hoặc nơi xử lý bền vững.

## 14. Chọn concurrency và rate limit theo workload

| Workload | Kiểm soát cần ưu tiên | Lý do |
|---|---|---|
| Gửi email/SMS | Rate limit theo provider quota | Provider thường giới hạn tốc độ gửi |
| Payment API | Rate limit + concurrency + idempotency | Bảo vệ quota và tránh giao dịch trùng |
| Database writer | Connection/concurrency cap | Tránh cạn connection và lock contention |
| Image processing | CPU/memory concurrency | Mỗi job có thể tiêu tốn nhiều compute |
| Kafka consumer | Partition parallelism + bounded workers | Giữ ordering và tránh commit sai |
| Pub/Sub subscriber | Outstanding message/byte flow control | Giới hạn memory và in-flight work |
| SQS Lambda consumer | Event source max concurrency + reserved concurrency | Giới hạn tổng invocation và bảo vệ dependency |

Không áp dụng một concurrency cap giống nhau cho mọi loại message. Message xử lý 5 ms và message gọi API ngoài mất 2 giây có profile capacity khác nhau.

## 15. Tương tác giữa autoscaling và concurrency cap

Autoscaler thường tăng consumer capacity khi backlog hoặc request load tăng. Concurrency cap đặt giới hạn tối đa để bảo vệ dependency.

Nếu cap quá thấp:

- Backlog tăng liên tục.
- Oldest message age vượt SLA.
- Drain time kéo dài.
- Autoscaler có thể đạt max scale nhưng throughput vẫn không đủ.

Nếu cap quá cao:

- Database/API bị quá tải.
- Timeout và retry tăng.
- Message có thể bị xử lý lại.
- Throughput hiệu dụng giảm dù số invocation cao.

Một chiến lược tốt là đặt max scale theo tổng capacity downstream, sau đó điều chỉnh concurrency mỗi instance và batch size. Theo dõi backlog age và downstream saturation cùng nhau.

### 15.1. Ví dụ tính giới hạn

Giả sử payment provider cho phép 100 request/giây. Một request mất trung bình 250 ms. Theo Little's Law, số request đồng thời trung bình để sử dụng hết quota là:

\[
C \approx \lambda \times W = 100 \times 0,25 = 25
\]

Có thể bắt đầu benchmark với concurrency khoảng 25 và rate limit 100 request/giây. Cần có headroom cho tail latency, retry và các client khác cùng dùng quota. Nếu provider quota được chia sẻ với nhiều service, ngân sách dành cho worker phải nhỏ hơn 100 request/giây.

Không đặt concurrency 100 chỉ vì quota là 100 request/giây; thời gian xử lý và giới hạn đồng thời là hai yếu tố khác nhau.

## 16. Retry có thể khuếch đại tải

Khi dependency quá tải, retry không giới hạn làm số request tăng thêm. Một burst ban đầu có thể tạo retry storm.

Ví dụ, 100 message/giây đều được thử ba lần vì API chậm có thể tạo tới 300 request/giây trong khoảng thời gian đó, chưa kể request mới. Nếu nhiều consumer cùng retry theo một chu kỳ, tải có thể đồng bộ thành các đợt spike.

Các biện pháp:

- Exponential backoff.
- Jitter để phân tán retry.
- Giới hạn số lần retry.
- Phân biệt lỗi retryable và permanent.
- Circuit breaker khi dependency liên tục lỗi.
- Giảm consumer concurrency khi downstream quá tải.
- Đưa message lỗi vào DLQ sau policy.
- Dùng idempotency key cho side effect.

Không retry ngay trong một vòng lặp tight loop. Không retry 4xx nghiệp vụ hoặc lỗi cấu hình vĩnh viễn như thiếu quyền IAM trừ khi có cơ chế sửa lỗi cụ thể.

## 17. Circuit breaker và bulkhead

Bulkhead cô lập tài nguyên giữa các dependency hoặc nhóm công việc. Circuit breaker ngừng gọi dependency tạm thời khi tỷ lệ lỗi vượt ngưỡng, cho dependency thời gian hồi phục.

Ví dụ:

- Payment provider chậm: mở circuit cho payment calls.
- Inventory API vẫn khỏe: tiếp tục xử lý loại message không phụ thuộc payment.
- Worker chỉ dành một số permit cho payment để payment không chiếm toàn bộ thread pool.
- Message payment có thể được trì hoãn hoặc retry theo policy.

Circuit breaker không thay thế queue hoặc retry policy. Khi circuit mở, consumer phải quyết định giữ message, trả lỗi để broker retry, hoặc chuyển sang một workflow trạng thái chờ. Không ack message như thành công nếu chưa có nơi lưu bền vững để tiếp tục xử lý.

## 18. Xử lý overload và load shedding

Khi hệ thống đạt giới hạn, cần quyết định loại công việc nào được ưu tiên:

- Từ chối công việc không thiết yếu.
- Hoãn xử lý công việc có thể chờ.
- Giữ message trong queue thay vì nhận vào process.
- Ưu tiên message có deadline gần hơn nếu semantics cho phép.
- Giảm batch/concurrency hoặc pause consumer.
- Chuyển lỗi vĩnh viễn sang DLQ.
- Bật chế độ degrade cho tính năng phụ trợ.

Load shedding cần có quy tắc nghiệp vụ. Không bỏ message thanh toán hoặc cập nhật tồn kho chỉ vì hệ thống đang quá tải. Nếu phải từ chối, cần bảo đảm message được giữ lại hoặc trạng thái thất bại được ghi nhận.

## 19. Đo hiệu quả điều tiết tải

Theo dõi các metric sau:

| Metric | Ý nghĩa |
|---|---|
| Active consumer concurrency | Số message đang xử lý |
| Configured max concurrency | Giới hạn cấu hình |
| Arrival rate | Tốc độ message vào |
| Processing/ack rate | Tốc độ hoàn tất |
| Queue backlog | Lượng công việc còn chờ |
| Oldest message age | Message cũ nhất đã chờ bao lâu |
| In-flight/outstanding | Message đã nhận nhưng chưa hoàn tất |
| Rate limiter denied/wait | Số lần bị giới hạn tốc độ |
| Bulkhead rejected | Số công việc không lấy được permit |
| Dependency latency/error | Tình trạng downstream |
| Retry and DLQ rate | Mức độ lỗi và redelivery |
| Drain time estimate | Thời gian dự kiến xóa backlog |

Một concurrency cap tốt thường giữ downstream latency ổn định trong khi backlog không tăng vô hạn. Nếu backlog tăng nhưng dependency còn capacity, có thể tăng cap hoặc consumer replicas có kiểm soát. Nếu dependency đã bão hòa, tăng cap có thể làm tình hình xấu hơn.

Không đưa message ID, order ID hoặc customer ID vào metric labels. Các định danh này nên nằm trong log/trace để tránh cardinality cao.

## 20. Kiểm thử load control

Một bộ kiểm thử nên bao gồm:

1. **Steady load:** arrival rate ổn định dưới capacity.
2. **Burst:** producer tăng nhanh trong thời gian ngắn.
3. **Sustained overload:** arrival rate cao hơn processing rate kéo dài.
4. **Slow dependency:** database/API tăng latency.
5. **Dependency throttling:** downstream trả 429 hoặc throttling.
6. **Consumer crash:** process dừng khi đang giữ message.
7. **Retry storm:** nhiều message cùng retry.
8. **Cold scale-out:** autoscaler tạo thêm instance.
9. **Rate limiter exhaustion:** bucket hết token.
10. **Bulkhead full:** mọi permit đều được sử dụng.
11. **Large batch:** payload hoặc batch size lớn.
12. **FIFO ordering:** nhiều message cùng group và nhiều group khác nhau.
13. **Kafka rebalance:** consumer rời group khi có record đang xử lý.
14. **Pub/Sub flow control:** outstanding limit đạt ngưỡng.
15. **Global quota:** nhiều instance cùng gọi một dependency có quota chung.

Trong test, xác minh:

- Tổng concurrency không vượt giới hạn đã định.
- Rate thực tế không vượt quota trong khoảng đo phù hợp.
- Backlog và message age có thể phục hồi sau burst.
- Dependency latency không tăng vượt ngưỡng an toàn.
- Message không bị mất khi executor đầy hoặc consumer crash.
- Duplicate được xử lý idempotent.
- Ordering được giữ theo yêu cầu.
- Alert kích hoạt khi backlog hoặc age vượt SLO.

## 21. Quy trình chọn và tinh chỉnh giới hạn

1. **Đo baseline.** Ghi arrival rate, processing duration, downstream latency và backlog.
2. **Xác định bottleneck.** Tìm giới hạn database, API, broker, CPU và memory.
3. **Tính capacity ban đầu.** Dùng throughput thực nghiệm và Little's Law để ước lượng concurrency.
4. **Đặt giới hạn nền tảng.** Cấu hình reserved concurrency, max instances hoặc event source maximum concurrency.
5. **Đặt flow control queue.** Giới hạn outstanding messages/bytes, batch size và polling.
6. **Đặt giới hạn trong Java.** Dùng bounded executor, semaphore, rate limiter hoặc bulkhead.
7. **Phối hợp retry.** Dùng backoff, jitter, max attempts và DLQ.
8. **Load test.** Tăng dần traffic, burst và dependency latency.
9. **Quan sát SLO.** Theo dõi oldest message age, drain time và downstream saturation.
10. **Điều chỉnh từng biến.** Thay một nhóm cấu hình mỗi lần để biết tác động.
11. **Ghi runbook.** Xác định khi nào giảm concurrency, pause consumer hoặc tăng capacity.

Đừng tối ưu chỉ để backlog bằng zero tại mọi thời điểm. Queue có thể hấp thụ burst và làm phẳng tải. Mục tiêu là giữ message age trong SLA, bảo vệ dependency và phục hồi backlog trong thời gian chấp nhận được.

## 22. Câu hỏi tự kiểm tra

- Concurrency khác processing rate ở điểm nào?
- Little's Law giúp ước lượng số message in-flight như thế nào?
- Vì sao semaphore trong một Java process không giới hạn được tổng concurrency của nhiều instance?
- Backpressure khác rate limiting như thế nào?
- Token bucket cho phép burst theo cách nào?
- Reserved concurrency khác maximum concurrency của event source mapping ra sao?
- Vì sao SQS FIFO parallelism phụ thuộc số message group?
- Pub/Sub flow control giới hạn outstanding messages và bytes như thế nào?
- Kafka consumer group bị giới hạn parallelism bởi yếu tố nào?
- Bounded executor giúp ngăn vấn đề gì?
- Vì sao không nên ack ngay sau khi submit task vào in-memory executor?
- Retry storm có thể làm dependency quá tải hơn ra sao?
- Khi nào dùng circuit breaker hoặc bulkhead?
- Vì sao tăng consumer concurrency có thể làm throughput giảm?
- Những metric nào cần theo dõi khi tinh chỉnh load control?

