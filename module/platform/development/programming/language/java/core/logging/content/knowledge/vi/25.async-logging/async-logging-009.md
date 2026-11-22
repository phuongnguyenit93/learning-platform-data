# Đánh đổi throughput trong logging bất đồng bộ (Java)

## 1. Mục tiêu

**Logging bất đồng bộ (asynchronous logging)** cho phép thread xử lý nghiệp vụ đưa sự kiện log vào một bộ đệm/hàng đợi để worker khác định dạng và gửi đến đích (console, tệp, collector, mạng…). Cách này thường làm lệnh ghi log trả về nhanh hơn khi có **burst** (đợt tăng tải ngắn), nhưng không làm khả năng ghi thực tế của ổ đĩa hoặc hệ thống thu thập log tăng vô hạn.

Điều cần hiểu ở bài **“Đánh đổi throughput”** là: khi tăng tốc độ cho thread ứng dụng, ta đổi lấy bộ nhớ đệm, chi phí chuyển giao, độ trễ log hiển thị, và một quyết định không thể né tránh khi bộ đệm đầy: **chặn thread gửi, bỏ bớt log hoặc xử lý qua đường khác**.

Sau bài này, bạn có thể:
- Phân biệt throughput của **ứng dụng phát sinh log**, tốc độ **enqueue**, tốc độ **đích thực sự xử lý log**, và tỷ lệ sự kiện bị mất.
- Dự đoán khi nào queue đầy bằng tốc độ phát sinh (λ), tốc độ tiêu thụ (μ) và dung lượng queue (Q).
- So sánh logging đồng bộ, bất đồng bộ và chính sách xử lý khi queue đầy.
- Cấu hình các lựa chọn chính trên Logback/Log4j 2 và đo hiệu năng bằng workload thực tế.
- Chọn chính sách phù hợp với log chẩn đoán, lỗi nghiêm trọng và audit cần độ tin cậy cao.

## 2. Luồng dữ liệu và các đại lượng throughput

### 2.1. Đồng bộ so với bất đồng bộ

**Logging đồng bộ (đơn giản hóa):**

```text
Request thread -> tạo LogEvent -> format/ghi qua appender -> quay lại nghiệp vụ
                                     |
                                     +-> file / stdout / collector
```

**Logging bất đồng bộ (đơn giản hóa):**

```text
Request threads -> tạo/capture LogEvent -> [QUEUE hữu hạn] -> worker -> appender -> đích
       |              (enqueue)              |                   |
       +---- tiếp tục nghiệp vụ sớm           |                   +-> I/O chậm vẫn tồn tại
                                              +-> backlog / đầy
```

Trong triển khai thực tế, một phần công việc tạo event, kiểm tra level, thu thập timestamp/MDC, đôi khi format hoặc sao chép dữ liệu vẫn diễn ra ở thread gọi `logger.info(...)`. “Async” có nghĩa đường gửi log được tách ra; không có nghĩa toàn bộ chi phí logging bằng 0.

| Đại lượng | Ký hiệu | Ý nghĩa |
| --- | --- | --- |
| Tốc độ phát sinh | λ (events/s) | Số sự kiện ứng dụng muốn ghi mỗi giây |
| Tốc độ xử lý thực của đích | μ (events/s) | Số sự kiện được worker/appender thực sự chuyển/ghi thành công mỗi giây, tùy điểm đo |
| Dung lượng queue | Q (events) | Số event tối đa có thể chờ trong bộ đệm |
| Độ sâu queue | q(t) | Số event đang đợi tại thời điểm t; thường 0 ≤ q(t) ≤ Q |
| Throughput nghiệp vụ | requests/s hoặc ops/s | Số request/tác vụ ứng dụng hoàn thành mỗi giây |
| Call latency | thời gian của lời gọi log | Thời gian thread ứng dụng chờ ở `logger.info(...)` |
| Delivery latency | thời gian từ lúc tạo đến lúc đích nhận | Gồm thời gian chờ queue, xử lý và vận chuyển |
| Drop rate | events/s hoặc % | Sự kiện bị loại do policy hoặc lỗi |

Không gọi **số event enqueue thành công** là số event đã được ghi bền vững. Trong thời gian chạy, hàng đợi có thể còn tồn đọng, worker có thể đang xử lý một event, hoặc đích từ xa chưa xác nhận đã lưu. Muốn kiểm chứng đầu cuối cần đo tại điểm xác nhận phù hợp.

### 2.2. Trường hợp ổn định và quá tải

Giả sử một queue hữu hạn ban đầu trống, tốc độ phát sinh và tốc độ tiêu thụ xấp xỉ không đổi:

- Nếu **λ < μ**, worker có khả năng bắt kịp về dài hạn; queue hấp thụ dao động ngắn. Điều này không loại bỏ spike do GC, I/O hay tranh chấp lock.
- Nếu **λ = μ**, hệ thống cân bằng về trung bình nhưng vẫn có thể đầy trong burst; cần dự phòng cho độ biến thiên.
- Nếu **λ > μ** liên tục, backlog tăng xấp xỉ **λ − μ** event/giây. Queue hữu hạn rồi sẽ đầy: tăng Q chỉ **trì hoãn** thời điểm đầy, không giải quyết chênh lệch throughput dài hạn.

Ước lượng khi queue bắt đầu trống:

```text
thời gian tới lúc đầy ≈ Q / (λ − μ)     (khi λ > μ)
```

Ví dụ **giả định minh họa**, không phải số đo thực tế: ứng dụng tạo 12.000 event/s; đích chỉ xử lý 10.000 event/s; queue chứa 6.000 event. Backlog tăng khoảng 2.000 event/s, nên queue có thể đầy sau khoảng **3 giây** nếu tốc độ duy trì và không có cơ chế loại bỏ/giảm tải trước đó. Tăng queue lên 60.000 event dời thời điểm này lên khoảng 30 giây, nhưng tốc độ tiêu thụ vẫn là 10.000 event/s.

Trong hệ thống có nhiều luồng producer, event có kích thước biến thiên, nhiều appender hoặc mạng thất thường, λ và μ phải đo theo cửa sổ thời gian; công thức trên là mô hình gần đúng để suy luận dung lượng, không phải cam kết thời gian queue đầy.

## 3. Lợi ích throughput của async logging

### 3.1. Giảm thời gian ứng dụng chờ lệnh log

Khi hàng đợi chưa đầy, producer thường chỉ chuẩn bị event và enqueue; phần I/O được worker thực hiện. Với workload có nhiều request và những đợt log tăng đột ngột, việc rút ngắn lời gọi log có thể giảm latency cho request và tăng khả năng xử lý burst.

**Peak enqueue throughput** (bao nhiêu event producer đẩy vào queue trong một khoảng ngắn) có thể cao hơn **sustained sink throughput** (bao nhiêu event thật sự được đích xử lý lâu dài). Đừng báo “logging chạy 100.000 event/s” chỉ vì trong phép thử ngắn 100.000 lời gọi log đã trả về: cần kiểm tra queue đã xả hết hay chưa và có event nào bị loại.

### 3.2. Batching, giảm tranh chấp I/O, gom tác vụ

Worker có thể gom nhiều event, ghi theo lô và giảm số lần tương tác I/O; một số backend cũng tối ưu đồng bộ hóa giữa các producer. Tuy nhiên kết quả phụ thuộc backend, appender, encoder, số CPU, loại đích và độ lớn event. Không có kết luận chung rằng async luôn nhanh hơn sync.

### 3.3. Chi phí phát sinh

Async thêm:
- Thao tác chuyển giao giữa producer/consumer, đồng bộ bộ nhớ, đánh thức worker.
- Event/buffer chiếm heap, có thể tăng allocation và áp lực GC.
- Độ trễ giữa khi nghiệp vụ phát log và khi log xuất hiện ở đích.
- Vòng đời worker, flush và xử lý lỗi phức tạp hơn; lỗi trên worker có thể không truyền về thread gọi.
- Khả năng cạnh tranh CPU với nghiệp vụ trong môi trường ít core.

Nếu sink đã rất nhanh, lượng log thấp hoặc các thread ứng dụng tranh nhau enqueue, chi phí thêm của async có thể khiến **throughput duy trì thấp hơn sync**. Vì thế cần đo cả trạng thái queue gần rỗng và trạng thái queue bị quá tải.

## 4. Queue đầy: lựa chọn nào cũng có giá

| Chính sách | Khi queue đầy | Tác động throughput và latency | Giá phải trả / trường hợp dùng |
| --- | --- | --- | --- |
| **Block / backpressure** | Producer chờ có chỗ trống | Giảm throughput nghiệp vụ và làm tăng p95/p99 khi nghẽn; tốc độ nhận event lâu dài bị sink giới hạn | Ưu tiên giữ log đã nhận; phải dự phòng timeout, cascading stall |
| **Drop / discard** | Bỏ event theo mức ưu tiên hoặc bỏ event mới | Bảo vệ latency của producer, giữ request throughput ở một mức nào đó | Mất khả năng quan sát; cần đếm số bị loại và chọn event có thể bỏ |
| **Synchronous fallback** | Thread gọi tự ghi khi queue đầy | Có thể giữ event nhưng bất ngờ chịu chi phí I/O tại hot path | Latency spike, contention và hành vi khác khi tải cao |
| **Spill sang đĩa/buffer bền vững** | Chuyển sang cơ chế lưu tạm có độ bền khác | Giảm mất sự kiện nếu thiết kế đúng | Tăng I/O, dung lượng, chi phí vận hành; cần giới hạn và xử lý đĩa đầy |
| **Giảm số event ở nguồn** | Giảm DEBUG, sampling/rate limit | Giảm λ để gần hoặc dưới μ; hiệu quả cả throughput và bộ nhớ | Có thể mất chi tiết chẩn đoán; phải bảo vệ log quan trọng |

**Không có chính sách “không block, không mất log, không tốn tài nguyên” khi λ > μ kéo dài.** Nếu không thể mất event, phải chấp nhận chờ/backpressure hoặc đầu tư tăng năng lực tiêu thụ, giảm nguồn phát, hoặc thiết kế đường ghi bền vững riêng.

**Unbounded queue** thường chỉ dời vấn đề sang heap hoặc ổ đĩa; khi nguồn phát liên tục vượt đích, backlog sẽ tiếp tục lớn cho đến khi chạm giới hạn tài nguyên. Trong đa số ứng dụng dịch vụ, queue **có giới hạn rõ ràng** và metric cảnh báo là lựa chọn dễ kiểm soát hơn.

## 5. Ví dụ Java 17+ độc lập: throughput được “mua” bằng mất log

Đây là **mô phỏng queue/worker**, không thay thế backend logging thật và **không phải benchmark**. Ta cố ý giữ worker chưa được chạy để tạo tình huống queue đầy một cách xác định: 5 event đến cùng lúc, queue chứa 2 event và `offer` không đợi. Như vậy chỉ có 2 event được chấp nhận.

Tạo tệp **`AsyncLoggingTradeoffDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class AsyncLoggingTradeoffDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);
        CountDownLatch startDrain = new CountDownLatch(1);

        Thread sink = new Thread(() -> {
            try {
                // Chỉ tiêu thụ sau khi producer đã thử gửi cả 5 event.
                startDrain.await();
                String event;
                while ((event = queue.poll()) != null) {
                    System.out.println("consumed=" + event);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "simulated-sink");
        sink.start();

        int accepted = 0;
        int dropped = 0;
        for (int i = 1; i <= 5; i++) {
            if (queue.offer("event-" + i)) {
                accepted++;
            } else {
                dropped++;
            }
        }

        System.out.println("accepted=" + accepted + " dropped=" + dropped);
        startDrain.countDown();
        sink.join();
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac AsyncLoggingTradeoffDemo.java
java AsyncLoggingTradeoffDemo
```

**Kết quả chính xác với kịch bản này:**

```text
accepted=2 dropped=3
consumed=event-1
consumed=event-2
```

Ý nghĩa:
1. `ArrayBlockingQueue<>(2)` có dung lượng cố định 2 event.
2. `offer(event)` trả về `false` ngay khi đầy; producer **không bị block**, nhưng 3 event mất trước khi đến worker.
3. `CountDownLatch` bảo đảm worker chỉ bắt đầu sau vòng enqueue nên kết quả được cố định; trong ứng dụng thật, worker chạy đồng thời và số event bị loại phụ thuộc tải.
4. `consumed` chỉ có nghĩa worker mô phỏng đã nhận event, **không đại diện cho lưu bền vững**. Production cần đo riêng ghi file/collector thành công.
5. `sink.join()` đợi worker kết thúc, tránh kết thúc ví dụ trước khi in xong.

Để thử chính sách khác trong một chương trình thực, có thể dùng:
- `queue.put(event)`: chờ đến khi còn chỗ, không tự động drop; lời gọi có thể bị block.
- `queue.offer(event, timeout, TimeUnit.MILLISECONDS)`: chờ tối đa một khoảng rồi trả về `false` nếu vẫn đầy.
- `queue.offer(event)`: không đợi; tự tăng counter `dropped` khi thất bại.

Đây là API queue của JDK; backend như Logback hoặc Log4j 2 có cơ chế và chính sách riêng. Không tự sửa thành `put` trong ví dụ có `CountDownLatch` nêu trên: vì worker đang bị giữ lại chờ producer, producer có thể kẹt mãi khi queue đầy. Khi thử backpressure, hãy để consumer chạy đồng thời và thiết kế đường shutdown/interrupt đúng cách.

## 6. Bức tranh throughput trong production

### 6.1. Theo dõi số lượng event ở từng chặng

Đặt các điểm đo độc lập:

```text
generated -> accepted/enqueued -> dequeued -> appender success -> collector acknowledged
     |                |
     +-> filtered     +-> dropped / retry / fallback
```

Các điểm có thể khác nhau tùy backend. Cần phân biệt **filtered** (không được phát do mức log hay sampling) với **dropped** (đã có ý định ghi nhưng bị bỏ vì queue/policy). Một sự kiện được dequeue chưa chắc đã ghi thành công; một bản ghi gửi qua stdout chưa chắc đã được collector nhận.

Các metric hữu ích:
- `log_events_generated_total`, `log_events_dropped_total` theo level/đích và nguyên nhân nếu có thể.
- Queue `size`, `capacity`, `remainingCapacity`, thời gian ở mức 80–100%, số lần producer bị chặn.
- Tốc độ appender xử lý thành công; lỗi ghi/timeout/retry; thời gian flush khi shutdown.
- Thời gian của lời gọi `log(...)` (p50/p95/p99) và request end-to-end latency (p95/p99).
- Application throughput (requests/s), CPU, GC pause, heap, bytes/s ra file/mạng và tình trạng collector.

Metric “không có drop” không đủ chứng minh không mất log nếu không theo dõi shutdown, I/O failure, collector và giới hạn của backend. Nên cấu hình cảnh báo sớm khi queue liên tục tăng và khi drop/append error khác 0.

### 6.2. Đánh đổi kích thước queue

Queue lớn hơn thường hấp thụ burst lâu hơn, nhưng:
- Dùng thêm heap cho đối tượng event, chuỗi, context, tham chiếu và overhead.
- Làm tăng thời gian event phải chờ trước khi được ghi khi backlog lớn.
- Kéo dài thời gian drain lúc shutdown; khi process bị kill, lượng event chưa xử lý có thể lớn hơn.

Nếu queue đang có 6.000 event chờ và worker ghi được 10.000 event/s, event ở cuối queue có thể phải đợi cỡ **0,6 giây** chỉ cho backlog phía trước (giả sử FIFO và tốc độ không đổi). Đây là thời gian queue ước tính, chưa tính I/O/network và xử lý sau appender.

Số byte bộ nhớ phải tính theo **kích thước event thực tế sau khi tạo/capture** và overhead JVM; “Q × độ dài text” chỉ là ước lượng sơ bộ. Cần đo heap sau khi warmup, khi burst và khi backlog kéo dài, không cấp queue thật lớn chỉ vì bộ nhớ còn trống.

### 6.3. Tăng tốc ghi và giảm sự kiện đầu vào

Nếu queue liên tục đầy, tăng Q ít hiệu quả hơn việc cải thiện **μ** (chọn file encoder hợp lý, giảm việc format tốn CPU, batching phù hợp, tăng công suất đích, giảm độ trễ mạng) hoặc giảm **λ** (hạ level, sampling có kiểm soát, tránh log trong mỗi vòng lặp, gom các event trùng nhau thành một metric).

Ví dụ một request phát 100 log và ứng dụng xử lý 200 request/s tạo ra khoảng **20.000 event/s**. Giảm về 10 log có giá trị mỗi request làm nguồn phát còn khoảng **2.000 event/s** mà không phải tăng queue. Tuy nhiên không được sampling/bỏ log bắt buộc theo nghiệp vụ hoặc quy định lưu vết.

## 7. Cấu hình trong các logging backend Java

### 7.1. Logback `AsyncAppender`

Đây là ví dụ **một đoạn cấu hình** Logback, cần định nghĩa appender `FILE` phù hợp và gắn `ASYNC` vào logger/root của ứng dụng:

```xml
<appender name="ASYNC" class="ch.qos.logback.classic.AsyncAppender">
    <queueSize>4096</queueSize>
    <discardingThreshold>0</discardingThreshold>
    <neverBlock>false</neverBlock>
    <appender-ref ref="FILE"/>
</appender>
```

Ý nghĩa:
- `queueSize`: dung lượng hàng đợi event (ví dụ 4.096), không phải số lượng thread.
- `discardingThreshold=0`: tắt việc loại bỏ **sớm** các event mức thấp khi queue gần đầy.
- `neverBlock=false`: khi queue thật sự đầy, producer có thể bị chặn để chờ chỗ thay vì chủ động drop theo lựa chọn `neverBlock`.
- Dù dùng các lựa chọn này, log vẫn có thể mất khi process chết, shutdown không kịp flush, appender lỗi hoặc đích không đáng tin cậy; không thể suy ra đảm bảo durability.

Theo tài liệu Logback, `AsyncAppender` mặc định có queue 256 event và chính sách loại bỏ TRACE/DEBUG/INFO khi queue dùng khoảng 80%; `neverBlock` mặc định là `false`. Điều này tạo một **đánh đổi có chủ ý**: giảm chờ producer bằng cách hy sinh log mức thấp. Kiểm tra phiên bản đang dùng và các setting đã override trước khi diễn giải drop rate.

Nếu đặt `neverBlock=true` để producer không phải chờ khi queue đầy, phải chấp nhận event bị bỏ và theo dõi hậu quả. Với audit quan trọng, chính sách chỉ ưu tiên throughput thường không đủ.

`includeCallerData` (class/method/file/line) có thể gây thêm chi phí nên nên bật có chủ đích. Shutdown đúng cách cần đóng `LoggerContext`/appender để worker có cơ hội drain; `maxFlushTime` quyết định thời gian chờ, và vẫn không bảo vệ được trường hợp kill/power loss.

### 7.2. Log4j 2: AsyncLogger và AsyncAppender

Log4j 2 có hai cơ chế khác nhau:
- **AsyncAppender**: đưa event vào queue rồi chuyển đến các appender đích trên thread riêng; cấu hình `bufferSize` và chính sách khi queue đầy tùy phiên bản/cấu hình.
- **AsyncLogger**: dùng LMAX Disruptor cho đường chuyển event bất đồng bộ; có thể chọn toàn bộ logger async hoặc phối hợp logger sync/async. Cần dependency tương ứng theo tài liệu Log4j 2 đang dùng.

Cả hai vẫn bị giới hạn bởi tốc độ sink. `AsyncQueueFullPolicy` có thể khiến event bị bỏ, thread chờ hoặc event được xử lý trên thread gọi, tùy cấu hình. Không mặc định rằng “bật AsyncLogger” luôn đạt throughput cao hơn hoặc không bao giờ chặn. Một bộ xử lý async phía trước một appender async khác cũng có thể tạo thêm queue/latency mà không tăng μ.

**Những con số benchmark và default của phiên bản cũ không phải cam kết cho phiên bản hiện tại.** Cần benchmark ứng dụng thật với cùng cấu hình log, cùng đích ghi, số core, payload, tần suất và trạng thái tải.

## 8. Cách benchmark throughput cho đúng

Một phép thử hiệu năng đáng tin phải tách **tốc độ nhận event tức thời** khỏi **tốc độ ghi hoàn tất**, đồng thời quan sát p99 latency, drop và backlog.

1. **Xác lập mục tiêu:** log debug được bỏ hay phải giữ 100%? SLO latency của request? Có yêu cầu audit hoặc flush tối đa khi shutdown không?
2. **Giữ cùng workload:** cùng số request/giây, số event/request, kích thước thông điệp, level, context/MDC, layout JSON/text, stack trace, đích file/collector và retention. Không so sync ghi file với async chỉ enqueue rồi bỏ.
3. **Chạy baseline:** không bật loại log đang đo (để biết chi phí ứng dụng), sau đó sync và async. Warmup JVM/JIT, đo nhiều lần, báo hardware/JDK/backend phiên bản. Có thể dùng JMH cho microbenchmark gọi logger, nhưng cần benchmark integration/end-to-end để đo disk/collector.
4. **Chạy ba giai đoạn:** tải dưới công suất sink, burst ngắn và quá tải kéo dài. Đo trong lúc queue tăng, sau khi queue đầy và khi drain hết, tránh kết thúc phép thử trước worker.
5. **Báo đủ chỉ số:** requests/s, `log(...)` p99, request p99, generated/accepted/written/dropped, queue occupancy, memory, CPU/GC, bytes/s, lỗi và thời gian shutdown. So sánh theo cửa sổ thời gian bằng nhau.
6. **Tạo sự cố có kiểm soát:** cho collector chậm/ngắt ngắn, giảm tốc độ đĩa hoặc tăng log rate; xác định policy khi queue đầy, cách hiển thị lỗi, flush/recovery và số event mất thực tế.

**Ví dụ cách diễn giải:**

| Quan sát | Điều suy ra hợp lý |
| --- | --- |
| Async producer trả về nhanh, queue tăng liên tục, sink không theo kịp | Đang chuyển nợ xử lý sang backlog; throughput bền vững chưa cải thiện |
| Request throughput cao, drop rate tăng | Đã đánh đổi độ đầy đủ log lấy khả năng đáp ứng nghiệp vụ |
| Queue đầy, request p99 tăng đột biến | Backpressure hoặc fallback sync có thể đang tác động hot path |
| Async có p99 tốt khi burst, nhưng kém hơn sync trong tải đều kéo dài | Chi phí async và giới hạn sink đang lộ rõ |
| Queue thấp, written/s ≥ generated/s trên cửa sổ phù hợp, không có lỗi | Có dấu hiệu cân bằng, vẫn cần kiểm tra cuối đường và shutdown |

Tránh benchmark chỉ với **ConsoleAppender** nếu production ghi file/collector; console có đặc tính I/O và tốc độ đọc khác biệt. Tránh đưa `System.out.println` vào vòng lặp benchmark: đó cũng là một thao tác I/O rất đắt, làm sai phép đo. Dùng công cụ và đích tương ứng workload thực.

## 9. Quyết định theo loại log và yêu cầu tin cậy

- **Log chẩn đoán mức DEBUG/TRACE:** có thể cân nhắc sampling, rate limit, discard khi quá tải; phải có metric drop và bật chi tiết theo phạm vi nhỏ khi cần.
- **Log nghiệp vụ INFO:** cần xác định rõ mức độ chấp nhận mất; nhiều event INFO hữu ích nhưng có thể dư thừa ở hot path.
- **Log WARN/ERROR:** thường cần ưu tiên cao hơn; tránh chính sách bỏ vô điều kiện, nhưng queue đầy và process crash vẫn là rủi ro.
- **Audit, giao dịch, chứng từ, sự kiện đòi hỏi độ bền/tuân thủ:** không xem một queue logging trong RAM là nguồn lưu chính. Xem xét cơ chế ghi bền vững/transactional outbox hoặc hệ thống audit chuyên dụng, có xác nhận, retry, idempotency và kiểm tra cuối đường; quyết định sync/async dựa trên yêu cầu cụ thể.

**Flush không đồng nghĩa với fsync hoặc xác nhận từ collector.** Ghi ra tệp, gửi stdout và đẩy đến một pipeline tập trung đều có các mức đảm bảo khác nhau. Khi nói “không mất log”, phải nói rõ điểm nào của pipeline đã xác nhận thành công.

**Bảo vệ dữ liệu:** nhiều throughput hơn cũng có thể làm phát tán nhanh hơn dữ liệu nhạy cảm. Không log mật khẩu, token, cookie hoặc toàn bộ payload nhạy cảm; tối thiểu hóa dữ liệu, masking/redaction và cấu hình quyền truy cập/retention.

## 10. Lỗi phổ biến

1. **Nhìn throughput enqueue rồi kết luận sink nhanh hơn:** phải chờ drain và đếm số event thật sự được xử lý.
2. **Tăng queue vô hạn khi sink chậm:** đổi nghẽn tạm thời thành áp lực heap, GC và shutdown.
3. **Bật neverBlock/drop mà không có counter:** request có thể nhanh hơn trong khi observability suy giảm âm thầm.
4. **Tắt discard sớm rồi tin rằng không thể mất log:** queue đầy vẫn có thể block, appender/shutdown vẫn có thể lỗi.
5. **Dùng cùng policy cho DEBUG và audit:** mức quan trọng và mục tiêu durability khác nhau.
6. **Format dữ liệu nặng trước lời gọi logger:** dù backend async, việc ghép chuỗi hoặc chạy hàm tốn CPU ở tham số vẫn xảy ra trên producer; dùng parameterized logging/lazy evaluation đúng API và tránh tính toán đắt không cần thiết.
7. **Đọc tham số mutable sau enqueue:** sự kiện có thể được tiêu thụ khi dữ liệu đã thay đổi; chọn event bất biến/snapshot phù hợp với backend.
8. **Không đo số lần block hoặc p99:** throughput trung bình tốt có thể che tail-latency rất xấu.
9. **Shutdown đột ngột khi còn backlog:** queued event có thể không kịp đến đích; kiểm tra stop/flush của backend và đường vận hành thực tế.
10. **Kết luận một backend luôn nhanh nhất từ một bảng benchmark:** workload, JDK, số core, loại appender và điểm đo có thể đổi thứ hạng.

## 11. Bài thực hành củng cố

1. Chạy chương trình `AsyncLoggingTradeoffDemo` và xác nhận 2 event nhận, 3 event bỏ. Giải thích vì sao số lời gọi `offer` hoàn thành (5) khác số event được tiêu thụ (2).
2. Dùng một mô hình producer/consumer không có latch, cho consumer xử lý chậm; so sánh `offer`, `put` và `offer` có timeout. Đo thời gian producer chờ và đếm event mất.
3. Trên ứng dụng Java có Logback/Log4j 2, chạy ba workload: dưới công suất, burst, quá tải kéo dài. Ghi requests/s, p99, queue, drop và số event hoàn tất ở đích.
4. Thử thay đổi queue size với cùng tải kéo dài. Kiểm tra liệu **thời điểm bắt đầu nghẽn** thay đổi nhưng **tốc độ sink dài hạn** có giữ nguyên hay không.
5. Định nghĩa policy riêng cho log chẩn đoán, WARN/ERROR và audit; viết rõ SLO latency, độ đầy đủ và điểm xác nhận log.

## 12. Ghi nhớ

- Async logging thường giảm thời gian gọi logger và xử lý tốt **burst**, nhưng throughput ghi lâu dài vẫn bị **sink** giới hạn.
- Khi λ > μ kéo dài, queue hữu hạn sẽ đầy; tăng queue chỉ kéo dài thời gian chịu tải, không tăng năng lực đích.
- Block, drop và fallback sync là các lựa chọn có đánh đổi rõ ràng giữa **latency/throughput ứng dụng** và **độ đầy đủ log**.
- Đo cả requests/s, event written/s, queue depth, drop, p99 và khả năng drain/shutdown. Không tuyên bố tối ưu chỉ từ số event enqueue.
- Với log audit cần tin cậy cao, dùng đường ghi có cơ chế bền vững và xác nhận phù hợp; queue RAM bất đồng bộ là chưa đủ.

### Tài liệu tham khảo chính thức

- Logback — *AsyncAppender*: https://logback.qos.ch/manual/appenders-async-sift.html
- Logback — *Throughput Benchmark*: https://logback.qos.ch/performance.html
- Apache Log4j 2 — *Asynchronous loggers*: https://logging.apache.org/log4j/2.x/manual/async.html
- Apache Log4j 2 — *Performance*: https://logging.apache.org/log4j/2.x/manual/performance.html
- Oracle Java SE 21 — *BlockingQueue*: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html
