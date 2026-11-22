# Hàng đợi có giới hạn, lấy mẫu sự kiện và chính sách khi quá tải

## 1. Vì sao instrumentation cần chính sách quá tải?

Java instrumentation có thể đặt điểm đo ở đầu/cuối phương thức, ghi trace, log, metric hoặc phát sự kiện cho một hệ thống quan sát. Trong ứng dụng tải lớn, **đường tạo sự kiện (producer)** thường chạy cùng thread với nghiệp vụ. Nếu điểm đo trực tiếp ghi mạng, ghi đĩa hoặc đưa vô hạn sự kiện vào RAM, phần quan sát có thể trở thành nguyên nhân khiến ứng dụng chậm, hết bộ nhớ hoặc deadlock.

Giả sử một phương thức được gọi 40.000 lần/giây. Nếu mỗi lần gọi sinh hai sự kiện `ENTER` và `EXIT`, mức đầu vào tiềm năng là 80.000 sự kiện/giây. Nếu exporter chỉ gửi được 30.000 sự kiện/giây, **lượng tồn tăng 50.000 sự kiện mỗi giây** nếu không giới hạn, kể cả lúc nghiệp vụ còn hoạt động bình thường.

Bài học thuộc nhóm **Đồng thời và hiệu năng** của Java instrumentation. Ta sẽ kết hợp ba cơ chế:

1. **Hàng đợi có giới hạn (bounded queue):** có sức chứa hữu hạn, phản ứng rõ ràng khi đầy.
2. **Lấy mẫu sự kiện (sampling):** quyết định giữ một phần thông tin để giảm số bản ghi phải xử lý, ưu tiên tính nhất quán của một invocation/trace.
3. **Chính sách quá tải (overload policy):** quyết định có chặn thread, bỏ bản ghi mới/cũ, giảm cấp, ghi bền vững hoặc dừng xuất dữ liệu — và đo được hệ quả mất dữ liệu.

**Mục tiêu vận hành:** **giữ sức khỏe của ứng dụng trước**, giữ chi phí instrumentation trong mức đo được, và **không báo dữ liệu “đầy đủ” khi đã sampling hoặc drop**. Một hàng đợi bounded chỉ hạn chế một chỗ chứa, không tự giới hạn mọi tài nguyên hay bảo đảm mọi sự kiện sẽ được gửi thành công.

### 1.1. Phân biệt “sự kiện được tạo” với “đã xuất thành công”

~~~text
Business invocation
     |
     v
Entry hook / Recorder
     |
     +--> Bộ đếm nghiệp vụ tối giản (có thể chạy với mọi invocation)
     |
     v
Quyết định sampling
     |                    \
     | không chọn          \ có chọn
     v                      v
Cộng sampledOut           Tạo record/snapshot nhỏ
                            |
                            v
                    Bounded in-memory queue
                      |               |
                      | offer OK      | queue FULL
                      v               v
                 Consumer/worker   Chính sách quá tải
                      |               |
                      v               v
                 Serializer       droppedQueueFull++
                      |
                      v
                  Exporter
                      |
                      +--> accepted by sink / retry / failure
~~~

Ở đây **accepted by queue ≠ exported ≠ persisted by backend**. Cần ít nhất ba lớp số liệu: **được chọn để ghi**, **được chấp nhận vào buffer**, **được hệ thống nhận cuối cùng**. Một `offer` thành công mới chỉ xác nhận queue đã nhận record.

## 2. Hàng đợi bounded là gì?

Trong Java 17, `ArrayBlockingQueue<E>` là một triển khai `BlockingQueue<E>` có kích thước mảng cố định. Khi tạo:

~~~java
BlockingQueue<TelemetryEvent> queue = new ArrayBlockingQueue<>(1024);
~~~

Đây là **mảnh code** trong chương trình đã khai báo record/class `TelemetryEvent` và import `BlockingQueue`, `ArrayBlockingQueue`; chưa phải chương trình độc lập.

Sức chứa 1.024 là **số phần tử**, không phải số byte. Một record có stack trace hoặc payload lớn có thể chiếm nhiều RAM dù chỉ tính là một phần tử. Muốn có hard memory budget cần thêm giới hạn payload, byte-weight, số nhãn, chuỗi có độ dài tối đa và kiểm soát bộ nhớ các producer/exporter.

### 2.1. Bốn thao tác cơ bản và hậu quả

| API Java 17 | Khi queue đầy/rỗng | Phù hợp với hook nóng? |
| --- | --- | --- |
| `queue.offer(event)` | Đầy: trả `false` ngay nếu không thể thêm, **không đợi có slot** | **Phù hợp** với chính sách drop-new |
| `queue.add(event)` | Đầy: thường ném `IllegalStateException` | Ít phù hợp; exception mỗi lúc quá tải tốn chi phí |
| `queue.put(event)` | Đầy: **chặn** producer cho tới khi có chỗ (hoặc bị interrupt) | Thường **không nên** dùng trong transformer/advice |
| `queue.offer(event, timeout, unit)` | Chờ tối đa khoảng timeout để có chỗ; rồi trả boolean | Chỉ khi cho phép độ trễ có giới hạn |
| `queue.poll()` | Rỗng: trả `null` | Dùng lúc drain/đọc không chặn |
| `queue.take()` | Rỗng: chặn consumer đợi item | Dùng ở worker riêng khi có shutdown đúng cách |

**Chi tiết kỹ thuật:** `ArrayBlockingQueue.offer` không đợi tới khi buffer trống, nhưng implementation vẫn có thể dùng khóa ngắn để đồng bộ queue. Vì thế “non-blocking ở mức chính sách chờ dung lượng” **không đồng nghĩa lock-free hoặc latency bằng 0**.

`remainingCapacity()` hữu ích để quan sát, **không** phải cơ chế đặt chỗ nguyên tử. Mẫu sai:

~~~java
if (queue.remainingCapacity() > 0) {
    queue.add(event); // Một thread khác có thể lấy mất slot.
}
~~~

Giữa hai lời gọi có thể có producer khác. Đúng hơn là:

~~~java
if (!queue.offer(event)) {
    queueDropped.increment();
}
~~~

Hai đoạn trên là **mảnh mã** giả định có `queue`, `event` và counter `queueDropped`. `offer` tự kiểm tra khả năng nhận trong một thao tác queue; không cần kiểm tra trước.

### 2.2. Vì sao hàng đợi không giới hạn nguy hiểm?

`LinkedBlockingQueue` có thể tạo với capacity, nhưng constructor mặc định có giới hạn `Integer.MAX_VALUE` nên trên thực tế gần như unbounded đối với nhiều hệ thống. `ConcurrentLinkedQueue` cũng không áp dụng hard capacity. Nếu producer nhanh hơn consumer trong nhiều phút, memory và GC tăng cho tới khi ứng dụng suy giảm hoặc OOME.

Không biến một hàng đợi “có size()” thành “bounded” chỉ bằng cách:

~~~java
if (queue.size() < limit) {
    queue.add(event); // Kiểm tra và thêm không atomic.
}
~~~

Đây là **mảnh code sai** khi có nhiều producer. Cần một queue bounded đúng nghĩa hoặc một cơ chế admission có tính đồng bộ, không dùng phép so `size` rồi thêm làm giới hạn.

## 3. Sampling: quyết định bỏ trước khi phải tạo dữ liệu đắt tiền

Nếu dữ liệu thô quá nhiều, **sampling** giảm lượng phải giữ và xuất. Các khái niệm:

- **Head-based:** quyết định khi một request/trace/invocation bắt đầu, chưa biết toàn bộ kết quả sau này. Chi phí thấp, cho phép tránh ghi payload của những phần tử bị loại.
- **Tail-based:** quyết định sau khi biết latency, outcome hoặc toàn bộ trace; cần **lưu/buffer trước** và có chính sách hết hạn/dung lượng.
- **Probability/rate-based:** chọn khoảng một tỷ lệ `p`; cần nói rõ áp dụng cho **invocation, event hay trace**, vì mỗi cách khác nhau.
- **Parent-based/consistent trace sampling:** child dùng hoặc tương thích quyết định của parent/trace, tránh cây trace bị thủng do từng span lấy mẫu độc lập.
- **Adaptive sampling:** tỷ lệ có thể giảm khi áp lực tăng, nhưng phải tránh dao động mạnh và bảo toàn các giới hạn trọng yếu.

Sampling **không đồng nghĩa drop lúc queue đầy**. `sampledOut` xảy ra **theo chính sách chọn mẫu**; `queueDropped` xảy ra vì **không đủ năng lực buffer** sau khi đã chọn. Phải thống kê riêng, vì nguyên nhân và độ lệch thống kê khác nhau.

### 3.1. Quyết định sampling cho cùng invocation phải ổn định

Nếu ghi hai event:

~~~text
ENTER(id=72)
EXIT (id=72)
~~~

không được rút thăm độc lập:

~~~java
if (randomAtEnter()) emitEnter(id);
if (randomAtExit())  emitExit(id);
~~~

Đây là **pseudocode Java** với các hàm chưa định nghĩa. Hai lần chọn độc lập có thể tạo `ENTER` không có `EXIT` hoặc ngược lại.

Cách đúng: tạo một **token/scope** ở entry, lưu `sampled` trên token, và dùng **chính quyết định ấy** khi thoát method. Nếu sampling ở mức trace, cần truyền quyết định cùng trace context qua thread/process, không tự random lại ở từng child.

### 3.2. Hash ổn định tốt hơn chia chẵn/lẻ sequence trong production

Ví dụ chạy được ở mục 7 dùng `id % 2 == 0` để có kết quả **hoàn toàn tái lập**. Đó **chỉ là một bài thử deterministic**, **không phải thuật toán chọn mẫu production**. ID tuần tự có thể tương quan với thứ tự request, tenant hoặc burst và gây thiên lệch.

Trong production, hãy cân nhắc:

- Sử dụng trace ID có entropy đủ và một hàm hash ổn định để quyết định theo tỷ lệ; tất cả thành phần cần có quy ước thống nhất.
- Hoặc dùng `ThreadLocalRandom.current().nextDouble() < p` cho **một quyết định ở entry**, giữ quyết định đó tới exit. Nếu cần sự nhất quán giữa dịch vụ, random cục bộ độc lập là chưa đủ.
- Khi sampling theo tenant/endpoint, tính rõ tỷ lệ của từng nhóm; không suy dữ liệu đã sampled là một mẫu ngẫu nhiên đồng đều nếu có ưu tiên theo loại.
- Sampling tỉ lệ 10% **không** có nghĩa luôn giữ đúng 10% trong mọi cửa sổ nhỏ; đó là phân bố kỳ vọng với các sampler ngẫu nhiên phù hợp.

### 3.3. Head sampling không đảm bảo bắt mọi lỗi

Nếu chỉ biết request lỗi **sau khi kết thúc**, bộ head sampler quyết định sớm không thể đảm bảo giữ mọi request lỗi. Có ba lựa chọn:

1. **Bộ đếm lỗi nhỏ, luôn hoạt động:** giữ metric `failures` cho mọi invocation mà không phải lưu toàn bộ event payload.
2. **Tail sampling:** giữ event trong một buffer có giới hạn để quyết định sau, đổi lại chi phí/độ trễ lớn hơn.
3. **Ghi “error summary” bổ sung ngoài mẫu:** khi gặp lỗi, thử đưa một record ưu tiên vào kênh có admission riêng; vẫn có thể bị drop khi buffer đầy, và không thể hứa “zero loss”.

Không nói rằng một head sampler 1% “giữ 100% lỗi” nếu chưa có cơ chế bổ sung hoặc mô hình ưu tiên chính xác.

## 4. Chính sách khi queue đầy: phải chọn trước, không ứng biến trong hook

| Chính sách | Khi không còn slot | Lợi ích | Rủi ro/điều kiện |
| --- | --- | --- | --- |
| **Drop-new** | `offer` trả false, tăng counter, bỏ event hiện tại | Độ trễ producer có chặn bởi thao tác queue ngắn, đơn giản | Mất event mới, có thể mất lỗi vừa phát sinh |
| **Drop-oldest** | Loại record cũ để nhường chỗ cho record mới | Giữ cái gần hiện tại, phù hợp một số dashboard | Phá lịch sử/chuỗi, dễ gây starvation cho event cũ |
| **Bounded wait** | `offer(timeout)` đợi tối đa thời gian | Giảm drop khi burst ngắn | Tăng tail latency, có thể cộng dồn trong request |
| **Block/put** | Chờ tới khi queue có slot | Có thể tránh drop trong điều kiện consumer còn tiến triển | Hot path bị giữ vô hạn, deadlock/throughput collapse |
| **Spool to disk** | Ghi bền vững vào buffer thứ cấp có quota | Chịu được gián đoạn exporter ngắn hơn | Disk I/O/FS đầy, replay, bảo mật, durability và cleanup phức tạp |
| **Reduce/aggregate** | Chỉ giữ counters/histogram hoặc bản tóm tắt | Hữu ích khi trace chi tiết không thiết yếu | Mất correlation/stack chi tiết |
| **Disable/degrade instrumentation** | Tạm giảm/suspend probe đắt tiền | Bảo vệ ứng dụng lúc sự cố nặng | Khoảng trống observability, cần cảnh báo và cơ chế phục hồi |
| **Fail-closed** | Từ chối request nghiệp vụ do telemetry mất | Phù hợp chỉ với yêu cầu audit bắt buộc theo thiết kế | Không nên dùng cho tracing/metrics thông thường |

**Khuyến nghị mặc định cho agent quan sát hiệu năng:** chọn **bounded queue + sampling quyết định sớm + drop-new có counter**; exporter chạy ở thread riêng, producer không chờ mạng/đĩa. Đây là **chính sách fail-open**: instrumentation không làm request nghiệp vụ thất bại chỉ vì telemetry không gửi được. Nó là lựa chọn vận hành, **không** phải yêu cầu của Java API.

Với hệ thống **audit pháp lý hoặc giao dịch bắt buộc ghi**, mất event có thể không được chấp nhận. Khi đó phải dùng thiết kế giao dịch/durable log/commit có điều kiện riêng, không “lén” dùng cùng hàng đợi tracing rồi hứa không mất dữ liệu.

### 4.1. Drop-oldest có thể làm mất cặp ENTER/EXIT

Giả sử queue chứa hai event `ENTER(id=1)`, `ENTER(id=2)`. Để nhường chỗ cho `EXIT(id=1)`, drop-oldest sẽ bỏ `ENTER(id=1)` — kết quả còn `EXIT` không có entry. Drop-new lại có thể bỏ `EXIT` và giữ `ENTER` mồ côi.

Vì vậy nếu cần **tính toàn vẹn theo một invocation**, việc chỉ lựa chọn “bỏ mới hay bỏ cũ” **không đủ**. Phải thiết kế format/admission: một envelope hoàn chỉnh, nhóm record atomic hoặc cơ chế đánh dấu “incomplete”/reconciliation.

### 4.2. Tại sao `put` nguy hiểm trong agent?

Một method nghiệp vụ đang giữ lock và gọi điểm đo. Nếu queue đầy, `put` đợi exporter. Nếu exporter hoặc một thành phần mà nó cần lại phụ thuộc lock/tài nguyên do thread nghiệp vụ giữ, có thể tạo **chu kỳ chờ**. Ngay cả khi không deadlock, thời gian chờ tạo ra p99 latency xấu và làm tắc thread pool.

Đặc biệt, gọi blocking I/O trong `ClassFileTransformer.transform` có thể cản class loading, kéo theo reentrancy hoặc class initialization dependency. Hàng đợi bounded **phải đi kèm chính sách bỏ chờ phù hợp**, không chỉ đặt capacity.

## 5. Giữ cặp sự kiện: một envelope hoàn chỉnh thay vì hai lần enqueue

Khi mục tiêu là thống kê một method invocation hoàn tất, có thể biểu diễn kết quả bằng **một record**:

~~~text
CompleteCall {
    invocationId,
    methodKey,
    outcome: OK | ERROR,
    startNanos?,
    durationNanos?,
    traceId?,
    attributes?
}
~~~

Thay vì enqueue `ENTER` và `EXIT` độc lập, recorder lưu quyết định sampling và ngữ cảnh trên **frame/token trong lúc method chạy**, rồi **enqueue một CompleteCall trong `finally`**. Một lần `offer` sẽ **nhận trọn record hoặc từ chối trọn record**; không thể làm mất riêng `ENTER` do full queue.

**Đổi lại:** record chỉ xuất hiện sau khi method kết thúc. Với invocation đang chạy rất lâu hoặc JVM crash giữa chừng, backend **chưa có dấu vết “đang chạy”**. Nếu cần giám sát live spans, phải có thiết kế riêng cho cặp streaming events với dự phòng dung lượng, correlation ID, TTL, và khả năng đánh dấu incomplete.

~~~text
ENTRY
  -> cấp invocationId
  -> quyết định sampled một lần
  -> tạo scope nhỏ trên call stack
  -> chạy business method
EXIT trong finally
  -> nếu sampled: gom outcome + duration vào MỘT record
  -> offer(record) MỘT lần
  -> nếu full: tăng droppedQueueFull
~~~

**Đặc biệt:** producer có thể chết/hỏng process trước `finally`; một envelope tránh **partial admission**, không bảo đảm “mọi invocation đều có record”. Chính sách mất dữ liệu vẫn phải có counter/diagnostic.

## 6. Tránh nhầm các bộ đếm khi sampling + overload

Ta có thể tách các giai đoạn:

| Counter | Cộng khi nào | Không phải |
| --- | --- | --- |
| `calls` | Một invocation vào được hook | Số sự kiện đã xuất |
| `businessFailures` | Business body thoát bằng exception được hook bắt | Số error records đã giữ |
| `sampled` | Một invocation được head sampler chọn | Số event đã vào queue |
| `notSampled` | Sampler chủ động bỏ invocation | Số event mất do quá tải |
| `accepted` | `queue.offer(record)` thành công | Xác nhận backend đã lưu |
| `queueDropped` | `queue.offer(record)` trả false do full | Số sampling decisions không chọn |
| `exported` | Consumer thực hiện thao tác export thành công theo định nghĩa local | Bảo đảm end-to-end durable persistence nếu exporter chưa xác nhận |
| `exportFailures` | Exporter gửi thất bại hoặc retry hết quota | Mọi thất bại nghiệp vụ |

Khi **mọi invocation đã hoàn tất**, exporter chưa làm gì:

~~~text
calls   = sampled + notSampled
sampled = accepted + queueDropped
queue.size() = accepted      (chỉ trong demo nếu queue chưa drain)
~~~

Sau khi **consumer drain toàn bộ queue thành công** và không có producer mới:

~~~text
exported = accepted
queue.size() = 0
~~~

Đây là **bất biến cho demo với một producer và không retry**. Trong hệ thống nhiều thread hoạt động liên tục, `LongAdder.sum()` không phải snapshot nguyên tử; không assert những đẳng thức đó bằng nhiều lần đọc độc lập giữa lúc cập nhật. Trong production còn có reject/serializer error/worker crash và các counter riêng.

**Ý nghĩa của “mất” phụ thuộc biên quan sát:** head-sampled-out là **chọn mẫu có chủ đích**, queue-drop là **quá tải**, export failure là **sự cố gửi**. Gộp cả ba thành một bộ `dropped` khiến người vận hành không biết cần tăng queue, tăng exporter hay đổi tỷ lệ mẫu.

## 7. Ví dụ Java 17 chạy độc lập: queue capacity 2, sampling 1/2, drop-new

Ví dụ sau có stdout **deterministic**. Nó cố ý **không khởi chạy consumer** cho tới khi toàn bộ producer hoàn thành, để chứng minh queue đầy và hành vi `offer` một cách có thể lặp lại. Trong production, consumer phải chạy liên tục trên worker riêng và có giới hạn tài nguyên.

**Tệp đầy đủ: `BoundedTelemetryDemo.java`**

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public final class BoundedTelemetryDemo {
    record CompleteCall(long id, String method, String outcome) { }

    static final class Recorder {
        private final AtomicLong sequence = new AtomicLong();
        private final ArrayBlockingQueue<CompleteCall> queue =
                new ArrayBlockingQueue<>(2);
        private final LongAdder calls = new LongAdder();
        private final LongAdder businessFailures = new LongAdder();
        private final LongAdder sampled = new LongAdder();
        private final LongAdder notSampled = new LongAdder();
        private final LongAdder accepted = new LongAdder();
        private final LongAdder queueDropped = new LongAdder();
        private final LongAdder exported = new LongAdder();

        void invoke(String method, Runnable body) {
            long id = sequence.incrementAndGet();
            calls.increment();
            boolean keep = id % 2 == 0;  // Only for a deterministic demo.
            if (keep) {
                sampled.increment();
            } else {
                notSampled.increment();
            }
            String outcome = "OK";
            try {
                body.run();
            } catch (RuntimeException | Error exception) {
                outcome = "ERROR";
                businessFailures.increment();
                throw exception;
            } finally {
                if (keep) {
                    CompleteCall result = new CompleteCall(id, method, outcome);
                    if (queue.offer(result)) {
                        accepted.increment();
                    } else {
                        queueDropped.increment();
                    }
                }
            }
        }

        void reportAndDrain() {
            System.out.println("calls=" + calls.sum());
            System.out.println("businessFailures=" + businessFailures.sum());
            System.out.println("sampled=" + sampled.sum());
            System.out.println("notSampled=" + notSampled.sum());
            System.out.println("accepted=" + accepted.sum());
            System.out.println("queueDropped=" + queueDropped.sum());
            System.out.println("queueDepthBeforeDrain=" + queue.size());
            CompleteCall item;
            while ((item = queue.poll()) != null) {
                System.out.println("event=" + item.id() + "|"
                        + item.method() + "|" + item.outcome());
                exported.increment();
            }
            System.out.println("exported=" + exported.sum());
            System.out.println("queueDepthAfterDrain=" + queue.size());
            boolean accounting = calls.sum() == sampled.sum() + notSampled.sum()
                    && sampled.sum() == accepted.sum() + queueDropped.sum()
                    && exported.sum() == accepted.sum() && queue.isEmpty();
            System.out.println("accounting=" + accounting);
        }
    }

    public static void main(String[] args) {
        Recorder recorder = new Recorder();
        for (int i = 1; i <= 10; i++) {
            final int call = i;
            try {
                recorder.invoke("work", () -> {
                    if (call == 4 || call == 9) {
                        throw new IllegalStateException("business failure");
                    }
                });
            } catch (IllegalStateException expected) {
                // Keep the demo running; no producer-side logging.
            }
        }
        recorder.reportAndDrain();
    }
}
~~~

### 7.1. Biên dịch và chạy

Chỉ cần JDK 17 trở lên, không cần Java agent hoặc thư viện bên thứ ba:

~~~bash
javac --release 17 BoundedTelemetryDemo.java
java BoundedTelemetryDemo
~~~

**Stdout chính xác**, đã kiểm thử bằng OpenJDK 21 với `javac --release 17`:

~~~text
calls=10
businessFailures=2
sampled=5
notSampled=5
accepted=2
queueDropped=3
queueDepthBeforeDrain=2
event=2|work|OK
event=4|work|ERROR
exported=2
queueDepthAfterDrain=0
accounting=true
~~~

Giải thích:

1. Có **10** invocation `work`.
2. Hai call ID 4 và ID 9 ném `IllegalStateException`, nên `businessFailures=2` ngay cả khi không lưu bản ghi cho cả hai.
3. Demo quyết định giữ ID **chẵn**, nên `sampled=5` (2,4,6,8,10) và `notSampled=5` (1,3,5,7,9).
4. Buffer capacity **2** chưa được drain trong lúc producer chạy: ID 2 và ID 4 được chấp nhận; ID 6, 8, 10 bị `offer` trả false.
5. Do đó `accepted=2` và `queueDropped=3`. **ID 9 có lỗi nghiệp vụ nhưng không nằm trong sample** — đây là một ví dụ trực quan rằng head sampling không giữ mọi lỗi.
6. `event=4|work|ERROR` là một **record hoàn chỉnh** gồm ID và kết quả; không có hai event ENTER/EXIT phải ghép qua hai thao tác queue.
7. Sau khi drain, `exported=2` theo định nghĩa **in ra stdout thành công**, không phải export mạng thực; queue rỗng và các đẳng thức accounting đúng.

**Không đọc sai output:** `exported` của demo chỉ có nghĩa consumer đã in record ra stdout. Production phải đo ack/ingest hoặc mức bảo đảm riêng của exporter/backend; không dùng từ này để hứa dữ liệu đã được ghi bền vững trong hệ thống bên ngoài.

### 7.2. Phân tích điểm chèn mã quan trọng

**A. Tạo ID riêng và đếm mọi invocation**

`AtomicLong sequence` cấp số ID duy nhất trong một `Recorder`, kể cả nhiều producer thread. `calls.increment()` thực hiện **trước** sampling. Vì vậy phép đếm tổng không phụ thuộc backend; nếu mục tiêu là đếm tất cả call, không chỉ đếm những bản ghi đã sampled.

**B. Sampling một lần tại entry**

`boolean keep` được gắn với invocation hiện tại, không rút lại trong `finally`. Demo dùng chẵn/lẻ để tái hiện chính xác; khi dùng trace ID hash hoặc head sampler thật, vẫn giữ nguyên một `keep` per invocation.

**C. Ghi outcome đúng ranh giới**

`try/catch/finally` bắt `RuntimeException | Error` từ `Runnable.run()`, ghi `ERROR` rồi **ném lại cùng exception**. `finally` phát record hoàn chỉnh khi được chọn. Không có việc một lỗi từ business body biến thành return thành công chỉ vì recorder. Tuy nhiên, code recorder trong `finally` cũng có thể lỗi nghiêm trọng như OOME; phần production phải có thiết kế fail-open/giới hạn allocation thích hợp.

**D. Dùng `offer` thay vì `put`**

Hàng đợi đầy thì tăng `queueDropped` và cho business thread tiếp tục, không chờ consumer. Đây là chính sách drop-new rõ ràng.

**E. Consumer drain là bước tách biệt**

`queue.poll()` lấy từng record rồi in, tăng `exported`. Demo đợi producer kết thúc rồi mới drain để mọi kết quả ổn định. Production có consumer/exporter riêng để hệ thống hoạt động liên tục; khi đó không giả định queue lúc nào cũng đầy đúng hai record.

### 7.3. Bài tập biến thể nhỏ

Thử sửa capacity từ 2 lên 3 rồi chạy lại. Với cùng các ID được sampled và không drain sớm, số `accepted` dự kiến tăng thành 3, số `queueDropped` giảm còn 2, hàng đợi chứa ba ID đầu được chọn (2,4,6). `calls` vẫn là 10 và `businessFailures` vẫn là 2: capacity của telemetry **không nên làm thay đổi kết quả nghiệp vụ**.

Thử thay phép chọn `id % 2 == 0` bằng `id % 5 == 0`: trong 10 invocation sẽ chọn ID 5 và 10. Đây vẫn chỉ là bài tập deterministic, không phải sampling không thiên lệch trong traffic thực.

## 8. Vì sao ví dụ không chạy một consumer thread liên tục?

Trong phần học, cần tách hai đặc tính:

- **Hành vi khi đầy:** phải có cách tạo queue full theo thứ tự có thể kiểm tra.
- **Hệ thống vận hành:** consumer nên drain đồng thời với producer, có batching, export, retry và shutdown.

Nếu chạy consumer thật trong demo deterministic, scheduling có thể khiến nó lấy item trước khi producer tiếp tục; `accepted`/`queueDropped` không còn kết quả cố định giữa các lần chạy. Demo chủ động **tách pha** nên stdout có thể xác minh exact 100%.

Một consumer production có thể có cấu trúc:

~~~java
while (running || !queue.isEmpty()) {
    Event event = queue.poll(100, TimeUnit.MILLISECONDS);
    if (event != null) {
        exporter.send(event);
    }
}
~~~

Đây là **pseudocode Java**, cần định nghĩa `running`, `Event`, `queue`, `exporter` và xử lý `InterruptedException`/exception từ exporter; **không phải chương trình độc lập**. Trong thực tế cần giới hạn thời gian flush, số lần retry, kích thước batch và đảm bảo shutdown không giữ JVM mãi.

Không được coi `queue.poll()` trả `null` là exporter đã rỗng toàn hệ thống: producer khác có thể enqueue ngay sau đó; còn những bản ghi đang ở batch hoặc network in-flight.

### 8.1. Batching và cách đếm số liệu

Consumer có thể dùng `drainTo(batch, maxBatchSize)` rồi gửi batch, tiết kiệm syscall/network so với một request mỗi event. Nhưng:

- Nếu gửi **một batch thất bại**, xác định retry **cả batch hay từng record** và giới hạn số retry.
- Nếu backend có thể ingest một phần batch, một ACK chung không nhất thiết chứng minh tất cả record đã bền vững; cần hiểu hợp đồng exporter.
- Dùng correlation key/sequence/traceId nếu backend phải deduplicate khi retry.
- Không tạo batch vô hạn `drainTo(all)` rồi giữ một danh sách tăng lớn dưới tải nặng; giới hạn maxBatchSize và số batch in-flight.
- Bảo vệ shutdown: một worker không ngừng retry vô hạn khi hệ thống phía sau down, làm ứng dụng không thể thoát.

Một consumer duy nhất tạo thứ tự dequeue FIFO trong `ArrayBlockingQueue`, nhưng **không tự bảo đảm thứ tự nhận ở backend** khi có nhiều worker, retry, batch hoặc network. Nếu thứ tự per-trace quan trọng, cần chiến lược partition/ordering và event ID thích hợp.

## 9. Tính đúng đắn đa luồng: bounded queue và counters

`ArrayBlockingQueue` hỗ trợ nhiều producer/consumer đồng thời. `AtomicLong` cấp sequence an toàn và `LongAdder` thích hợp tổng hợp counter có tần suất update cao. Tuy vậy, các yếu tố phải được hiểu đúng:

1. **`offer` atomic ở mức thêm một item**, không phải atomic với `accepted.increment()`. Một thread có thể vừa enqueue rồi bị pause, thread khác đọc counters trước khi nó tăng; đây là snapshot tạm thời, không phải corruption.
2. **`LongAdder.sum()` không phải atomic snapshot** khi nhiều thread đang cập nhật; không assert phương trình cross-counter khi hệ thống còn hoạt động.
3. **`ArrayBlockingQueue.size()` thay đổi liên tục**; chỉ coi giá trị là chỉ báo áp lực tại thời điểm đọc, không phải bằng chứng end-to-end loss.
4. **`remainingCapacity()` không dành slot** khi có nhiều producer; phải dựa vào kết quả `offer`.
5. **Mỗi invocation giữ `sampled` riêng**, không dùng một static boolean chia sẻ giữa các lần gọi lồng nhau hoặc giữa thread.
6. Với `ThreadLocal<Scope>` hoặc stack, phải dọn sau outermost exit để thread pool không giữ context cũ. Nếu chuyển sang async thread khác, phải propagate context có chủ đích.
7. Các class helper/recorder/logger phải được loại khỏi phạm vi instrument để tránh việc công cụ tự tạo ra thêm sự kiện.

### 9.1. Hàng đợi có giới hạn không có nghĩa toàn pipeline giới hạn

Ngay cả khi `queue` có capacity 1.024:

~~~text
Producer stack/context/payload còn đang giữ
         |
         v
Queue 1024 records
         |
         v
Consumer batch 500 records
         |
         v
HTTP in-flight 20 requests x 500 records
         |
         v
Retry buffer / spool
~~~

Tổng bộ nhớ liên quan telemetry còn ở producer, batch, network-client, retry buffer, serialization buffers, text strings và stack traces. Muốn ổn định cần **ngân sách riêng cho từng tầng**, kể cả giới hạn concurrent exports và timeout.

### 9.2. Fairness và chi phí

`ArrayBlockingQueue` có constructor cho phép `fair=true`. Fairness có thể giảm starvation của những thread đang đợi, nhưng Javadoc lưu ý thường giảm throughput. Với chiến lược `offer` bỏ event mới, **đừng bật fairness chỉ vì tưởng queue sẽ “công bằng theo tenant”** — fairness về lock/wait không phải quota per-tenant. Cần partition/counter riêng nếu muốn công bằng giữa tenant/service.

## 10. Ước lượng capacity và xác định overload

Gọi:

- `R` = số invocation/s vào recorder;
- `p` = tỷ lệ sampling được giữ ở entry (0–1);
- `e` = số queue record mỗi invocation được chọn (với **complete envelope**, `e = 1`; với hai event riêng, thường `e = 2`);
- `λ = R × p × e` = tốc độ record **muốn vào queue**;
- `μ` = tốc độ consumer/exporter xử lý bền vững theo cùng đơn vị record/s;
- `C` = capacity queue theo record.

Nếu `λ > μ` kéo dài, backlog tăng xấp xỉ `λ - μ` record/s cho tới khi queue chạm `C`. Giả sử queue bắt đầu rỗng và tốc độ tương đối ổn định, thời gian đạt đầy **xấp xỉ**:

~~~text
time_to_full ~= C / (lambda - mu)  (nếu lambda > mu)
~~~

Đây là **ước lượng công suất trung bình**, không phải công thức dự đoán thời điểm chính xác trong hệ thống bursty/concurrent.

**Ví dụ:** ứng dụng có `R=20.000` call/s, giữ `p=10%` và mỗi call giữ tạo một envelope. Vậy `λ=2.000` record/s. Exporter chỉ xử lý `μ=1.500` record/s. Nếu `C=500`, backlog tăng khoảng **500 record/s**; buffer đầy khoảng **1 giây** nếu các tốc độ giữ nguyên.

Nếu exporter đủ nhanh về trung bình (`λ < μ`), buffer vẫn có thể đầy khi có burst ngắn hoặc exporter bị pause (GC, DNS, mạng). Capacity nên dựa trên **burst tolerance**, độ trễ exporter và mức memory/latency chấp nhận được, không chỉ tần suất trung bình.

### 10.1. Một queue capacity hữu hạn không đặt hard budget theo byte

Nếu event payload trung bình có 256 bytes, 500 record tương ứng tối thiểu khoảng 128.000 byte **chỉ xét payload trung bình**. Kích thước heap thực tế còn object headers, references, string/byte[] backing, alignment, records lớn bất thường, batch và client buffers. **Không** lấy 500 × 256 rồi khẳng định tổng heap usage chắc chắn chỉ 128 KB.

Nên giới hạn payload (tên class/method, stack trace depth, baggage, attribute count và độ dài value) và đo allocation thực tế trong JVM. Với payload độ dài biến thiên lớn, có thể cần queue tính **byte budget** bằng semaphore/weight bên cạnh count cap.

### 10.2. Khi nào tăng capacity không giải quyết vấn đề?

Nếu `λ > μ` liên tục, tăng `C` chỉ **trì hoãn** thời điểm full. Muốn bền vững phải giảm tốc độ nhập (sampling, aggregation, filtering) hoặc tăng năng lực xuất (batching, worker phù hợp, backend capacity). Với exporter/network down hoàn toàn (`μ≈0`), dù buffer rất lớn cuối cùng vẫn đầy.

Không coi “queue size bằng 0” luôn là tốt: có thể do producer không hoạt động hoặc instrumentation đã bị tắt. Phải đọc cùng `calls`, `sampled`, `accepted`, `queueDropped` và export throughput.

## 11. Sampling, thống kê và độ lệch khi có queue drop

Một sampler xác suất `p` có thể cho phép ước lượng tổng event từ mẫu **khi điều kiện lấy mẫu phù hợp**. Nhưng nếu sau sampling còn **drop do quá tải**, xác suất được giữ cuối cùng không còn chỉ là `p` và có thể phụ thuộc thời gian, method, tenant, kích thước payload hoặc độ trễ exporter.

Ví dụ:

~~~text
100.000 calls
  | head sampling 10%
  v
10.000 selected
  | queue đầy, chỉ accepted 4.000
  v
4.000 accepted
  | exporter lỗi, backend chỉ nhận 3.800
  v
3.800 observed records
~~~

Nếu dashboard lấy 3.800 × 10 để kết luận có 38.000 calls thì **sai**, vì bỏ qua queue drop và export failure. Nếu sampling không ngẫu nhiên đồng đều hoặc ưu tiên errors/slow requests, phép nhân `1/p` còn có thể sai ngay cả khi không có queue drop.

Trong thực tế nên ưu tiên:

- **Counters luôn-on, cardinality thấp:** tổng calls/failures/latency histogram từ nguồn đã kiểm soát, không lấy từ raw trace sample nếu muốn chỉ số đầy đủ.
- **Traces đã sampled:** dùng để chẩn đoán ví dụ đường đi, không mặc định là tổng thể đầy đủ.
- **Loss accounting:** cho biết bao nhiêu record được chọn, bị queue full, bị exporter reject/retry exhaustion.
- **Tỷ lệ sampling theo phiên bản/thời gian/tenant:** có thông tin để phân tích thống kê, tránh nhân nhầm.
- **Các thống kê độ trễ:** kiểm soát sampling bias; nếu ưu tiên slow requests thì phân bố trace retained không là phân bố gốc.

### 11.1. Không để nhãn metric bùng nổ

Tăng `queueDropped` theo số lần drop là rẻ khi label count ít. Nhưng tạo một metric label `invocationId`, `rawUrl`, `exceptionMessage` hoặc full stack trace cho mỗi record sẽ gây cardinality/memory/CPU lớn ngay chính trong hệ thống telemetry.

Những label tương đối an toàn có thể là `service`, `methodGroup`, `dropReason`, `exporter`, hoặc tenant đã được giới hạn/định danh theo thiết kế. Chỉ lưu data chi tiết trong sampled record theo quota.

## 12. Adaptive sampling khi áp lực thay đổi

Tỷ lệ cố định (ví dụ 5%) có thể đủ khi tải ổn định. Nhưng với burst, một bộ điều khiển có thể thay đổi `p` để giữ áp lực trong giới hạn.

Mẫu ý tưởng:

~~~text
Mỗi cửa sổ theo dõi:
  offeredRate, acceptedRate, dropRate, queueFillRatio,
  exporterLatency, exporterErrorRate

Nếu fillRatio cao liên tục và dropRate tăng:
  giảm sampleProbability theo từng nấc có giới hạn

Nếu fillRatio thấp liên tục, exporter ổn định:
  phục hồi sampleProbability chậm hơn

Luôn có minRate/maxRate, hysteresis, cooldown
và cơ chế giữ metric trọng yếu ngoài raw sampling.
~~~

Đây là **thuật toán mô tả**, không phải chương trình tự động cắm vào production. Những điểm bắt buộc:

- **Không rút thăm lại cho cùng một invocation** khi config `p` đổi giữa `ENTER` và `EXIT`; lưu `sampled` trong scope/token.
- Khi sampling theo trace, quyết định được truyền xuống children/upstream/downstream theo quy ước; không áp dụng tỷ lệ mới giữa chừng làm vỡ trace.
- Dùng **hysteresis/cooldown** để tránh mẫu `p` tăng/giảm liên tục theo dao động queue.
- Không phản ứng chỉ theo `queue.size()`: cần tốc độ drop, exporter errors, latency và tốc độ vào.
- Có floor để không mất hoàn toàn khả năng quan sát, trừ khi chính sách hệ thống quy định tắt; ngoại lệ/audit có thể cần kênh riêng.
- Ghi lại `sampleProbability` cùng dữ liệu export nếu mục tiêu là ước lượng tổng thể theo thời gian.

**Quan trọng:** adaptive sampling giảm nhu cầu ghi, **không bảo đảm** không mất record khi full. Consumer có thể bị ngắt kết nối hoàn toàn, hàng đợi vẫn phải có chính sách drop/spool rõ ràng.

## 13. Bảo vệ hot path: fail-open phải được triển khai cẩn thận

Java agent thường được chèn vào bytecode ở những method rất thường xuyên hoặc những class nhạy cảm. Logic instrumentation cần:

1. **Bỏ qua sớm** các class/method không cần đo; tránh phân tích/khởi tạo payload khi sampling đã loại.
2. **Không gọi logger/network/exporter đồng bộ** trong transformer/advice nóng; logging framework có thể tự bị instrument gây reentrancy.
3. **Hạn chế allocation** trên đường hot path: không tạo stack trace hay JSON string cho every call nếu chỉ giữ 1%.
4. **Dùng bộ đếm ít label** để phân biệt business failures, sampled-out, queue-full, serializer failure và export failure.
5. **Tạo token per invocation**, lưu decision/outcome/time đúng mỗi frame nếu nested/recursive.
6. **Không chặn class loading** vì queue đầy; tránh `put` và lock vòng quanh network.
7. **Không làm thay đổi semantics của business method** vì một event bị drop: exception nghiệp vụ được giữ nguyên và return value không đổi.
8. **Không che lỗi nền nghiêm trọng:** cách xử lý `OutOfMemoryError`, `ThreadDeath`, crash hoặc lỗi recorder phải được thiết kế, test riêng; không catch `Throwable` rồi giả vờ mọi thứ thành công.

**Phân biệt demo và production:** ví dụ `BoundedTelemetryDemo` cố tình đơn giản, tạo `CompleteCall` trong `finally` và không có guard chống recursion từ thư viện logging. Trong bytecode advice của agent thật cần tách helper/recorder khỏi phạm vi instrument, kiểm tra an toàn khi allocation hoặc enqueue thất bại, và có policy diagnostics fail-open rõ ràng. Đừng sao chép ví dụ mà tuyên bố đã xử lý mọi tình huống JVM-level.

### 13.1. Không ép độ tin cậy audit vào một queue dùng cho performance telemetry

Nếu luật/hợp đồng nghiệp vụ yêu cầu **mỗi giao dịch có audit record bền vững**, việc đưa audit vào queue sampling rồi drop-new khi full vi phạm yêu cầu. Thiết kế đó cần transactional outbox, durable storage hoặc commit policy tương ứng. Nhấn mạnh sự khác nhau:

| Mục tiêu | Độ ưu tiên | Phương án ví dụ |
| --- | --- | --- |
| Performance trace | Bảo vệ ứng dụng; chấp nhận mất có đo đếm | Bounded queue, head sample, drop-new |
| Diagnostic error summary | Cần tỷ lệ giữ cao hơn; vẫn có quota | Priority lane riêng, counters luôn-on, bounded buffering |
| Audit bắt buộc | Không được im lặng bỏ bản ghi theo quy tắc nghiệp vụ | Ghi bền vững/transactional, fail-closed khi quy định yêu cầu |
| Debug cục bộ khi dev | Có thể chấp nhận overhead tạm thời | Tăng sample, log trực tiếp có kiểm soát |

Không dùng một policy chung cho tất cả dữ liệu chỉ vì tất cả được gọi là “event”.

## 14. Consumer/exporter: thất bại phía sau queue vẫn là thất bại dữ liệu

Một producer enqueue thành công nhưng exporter có thể:

- Timeout hoặc trả HTTP error.
- Gửi được một phần batch.
- Retry rồi tạo duplicate nếu ACK bị mất.
- Bị shutdown trước khi flush.
- Bị hạn chế băng thông/quota hoặc backend reject vì cardinality/size.
- Không xác minh record đã thực sự persisted ở sink.

Vì vậy:

- Có **exporter failure counter**, retry counter và queue/worker shutdown metrics riêng.
- Nếu dùng retries, cần **giới hạn attempts, elapsed time, backoff và số record đang giữ**, tránh biến retry queue thành bộ nhớ không giới hạn.
- Dùng **idempotency/correlation key** nếu backend hỗ trợ để giảm duplicate khi retry.
- Khi shutdown, ngừng/giới hạn producer, drain đến deadline và báo số record còn lại; không khẳng định flush thành công chỉ vì gọi `shutdown()`.
- Nếu shutdown/crash có thể làm mất hàng đợi in-memory, **ghi rõ mức bảo đảm**: in-memory queue không bền vững qua process death.

**Không sinh “EXIT OK” giả** để lấp một trace thiếu event vì exporter thất bại. Dữ liệu thiếu phải được đánh dấu dropped/unknown/incomplete tùy mô hình, không biến thành một kết quả nghiệp vụ bịa ra.

## 15. Các lỗi triển khai hay gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `ConcurrentLinkedQueue` vô hạn cho mọi event | Heap/GC tăng đến OOME khi exporter chậm | Bounded buffer + giới hạn tầng khác |
| Dùng `put` trong Java advice | Business thread chờ, p99 tăng hoặc deadlock | `offer`/bounded wait có chính sách rõ |
| Check `remainingCapacity` rồi `add` | Race dưới nhiều producer | Một `offer` và kiểm tra kết quả |
| Dùng `queue.add`, để exception full bay ra app | Telemetry làm hỏng nghiệp vụ | Xử lý saturation không bằng exception |
| Random độc lập ở ENTER/EXIT | Event pair bị orphan | Lưu sampling decision trong scope |
| Chỉ giữ `ENTER` hoặc `EXIT` khi queue còn chỗ | Trace rách | Một complete envelope hoặc admission theo cặp |
| Dùng sequence parity làm production sampler | Có thể thiên lệch theo traffic/order | Trace ID hash/parent-based hoặc sampler được thiết kế |
| Gọi `sum()` của nhiều `LongAdder` giữa lúc tải chạy rồi assert equality | Không có snapshot nguyên tử | Test sau quiescence hoặc dùng snapshot đồng bộ |
| Nghĩ capacity 1.024 là 1.024 byte | Payload vẫn có thể rất lớn | Giới hạn byte/event và dữ liệu phụ |
| Tăng queue capacity vô hạn khi exporter chậm hơn lâu dài | Chỉ kéo dài thời gian trước khi full | Giảm λ hoặc tăng μ |
| Coi accepted là durable exported | Mất sau queue/worker/network vẫn có thể | Đếm riêng accepted/exported/ack |
| Nhân observed trace count với 1/p dù đã queue-drop | Ước lượng thiên lệch | Counters luôn-on và loss accounting |
| Cùng một metric cho sampled-out, queue-drop và export failure | Không biết nguyên nhân mất dữ liệu | Các counter có reason |
| Spawn thread mới cho mọi event | Thread/stack/GC bùng nổ | Worker pool có giới hạn |
| Exporter tự bị agent instrument | Recursive emission, queue tự lấp | Exclude agent/helper/logger/exporter |
| Không cleanup ThreadLocal trong thread pool | Context request cũ rò sang request mới | Remove/restore context khi scope ngoài cùng kết thúc |
| Retry vô hạn không quota | “Bounded queue” bị phá bởi tầng retry | Bounded retry/timeout/backoff |
| Drop-oldest dùng cho stream enter/exit | Có thể mất entry, giữ exit | Atomic envelope hoặc reconciliation |
| Cho mọi lỗi “ưu tiên vô hạn” | Priority queue cũng quá tải | Dành quota riêng, fail-open/audit policy rõ |
| Không kiểm tra plugin/module/class loader | Helper không resolve hoặc static counters bị chia đôi | Thiết kế class-loader visibility/bridge phù hợp |

## 16. Bộ kiểm thử cần có trước khi triển khai production

**Kiểm thử logic:**

- [ ] `ArrayBlockingQueue` capacity 2 nhận đúng 2 record, lần thêm thứ 3 bị từ chối khi chưa drain.
- [ ] `offer` khi full không chờ consumer có chỗ; test không dùng thời gian quá chặt để tránh flaky.
- [ ] `calls` không phụ thuộc sampling/queue/export thành công.
- [ ] Outcome `ERROR` được giữ đúng khi exception đi qua method boundary; không biến lỗi thành return bình thường.
- [ ] Một invocation sử dụng **một quyết định sampling** từ entry tới exit.
- [ ] Khi dùng streaming pair, kiểm tra tình huống queue đầy giữa ENTER và EXIT; có thiết kế xử lý incomplete.
- [ ] Sau khi **mọi task đã hoàn thành**, đối chiếu counters `calls = sampled + notSampled` và `sampled = accepted + queueDropped` với phạm vi test tương ứng.
- [ ] Exporter retry/partial success không làm báo ack sai hoặc duplicate không kiểm soát.

**Kiểm thử tải:**

- [ ] Tốc độ producer thấp hơn, bằng và cao hơn consumer.
- [ ] Burst ngắn, network outage, exporter tạm dừng hoặc chậm nhiều phút.
- [ ] Nhiều producer/consumer, thread pool reuse và class-loading concurrency.
- [ ] Event payload lớn/stack trace sâu; đo heap/GC và allocation tại hook.
- [ ] Sampling thay đổi giữa invocation; token vẫn dùng quyết định ban đầu.
- [ ] Khi sampling ở mức trace, kiểm tra parent/child continuity xuyên thread/process.
- [ ] Cấu hình runtime bằng JVM khác nhau, shutdown có deadline và flush mất kết nối.
- [ ] Drop counter tăng đúng reason; dashboard phân biệt dropped vs intentionally sampled-out.

**Kiểm thử an toàn instrumentation:**

- [ ] Không instrument lại helper/recorder/logger/exporter của agent.
- [ ] Khi exporter down, nghiệp vụ vẫn trả đúng result/exception theo chính sách fail-open.
- [ ] Không đặt blocking I/O hoặc chờ queue vô hạn trong `ClassFileTransformer`.
- [ ] Metrics high-cardinality được kiểm soát, sample/payload theo quota.
- [ ] Có giới hạn hành vi khi memory pressure, không chạy vòng lặp logging chính nó.
- [ ] Nếu hệ thống đòi audit không mất, dùng đường bền vững riêng và test fail-closed đúng yêu cầu, không dùng drop-new âm thầm.

### 16.1. Các câu hỏi tự kiểm tra

1. `ArrayBlockingQueue.offer(e)` và `put(e)` khác nhau thế nào khi queue full?
2. Vì sao `remainingCapacity() > 0` rồi `add` không an toàn khi nhiều producer?
3. `sampledOut` khác `queueDropped` và `exportFailures` ở đâu?
4. Vì sao một head sampling decision phải được lưu xuyên suốt một invocation?
5. Một complete-call envelope giải quyết được loại mất sự kiện nào, và **không** giải quyết được loại nào?
6. Vì sao vẫn có thể mất event dù `queue.offer` trả true?
7. Với `R=20.000` call/s, `p=0,1`, `e=1`, `μ=1.500` record/s, `C=500`, buffer đầy xấp xỉ sau bao lâu nếu không có burst thay đổi?
8. Khi `businessFailures=2` mà queue chỉ còn một error record, bộ đếm lỗi nghiệp vụ có nên bị sửa xuống 1 không?
9. Tại sao `id % 2 == 0` chỉ phù hợp làm demo deterministic?
10. Tại sao `LongAdder.sum()` không thích hợp để khẳng định toàn bộ counters đồng thời nhất quán giữa lúc hệ thống đang chạy?
11. Khi nào chính sách drop-new không được phép dùng vì yêu cầu audit/transaction?
12. Vì sao tăng capacity không cứu được pipeline nếu producer nhanh hơn exporter **liên tục**?
13. Khi muốn tail-sample mọi slow/error request, cần ngân sách lưu state nào?
14. Vì sao bounded queue theo số record vẫn có thể khiến RAM tăng mạnh?
15. Làm sao biết tracer giữ record nào mà không làm thay đổi kết quả method nghiệp vụ?

**Ghi nhớ:** Với instrumentation hiệu năng, hãy **lấy mẫu sớm và nhất quán**, **đưa bản ghi nhỏ vào hàng đợi có giới hạn**, dùng **chính sách full queue tường minh** và **đếm chính xác các nguyên nhân mất telemetry**. `offer` + drop-new thường phù hợp hơn `put` trên hot path; nhưng accepted chưa có nghĩa persisted. Một envelope sau khi invocation kết thúc giúp tránh mất nửa cặp event do queue full, còn queue/adaptive sampling chỉ hữu ích khi đi cùng **bounded consumer, bounded retries, shutdown và tài nguyên được giám sát**. Mục tiêu không phải lưu mọi trace bằng mọi giá, mà là bảo vệ ứng dụng và luôn biết mức độ dữ liệu đang thiếu.

### Tài liệu tham khảo

- [Java 17 — ArrayBlockingQueue: capacity, offer, put, poll, fairness](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)
- [Java 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)
- [Java 17 — AtomicLong và LongAdder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [Java 17 — ThreadLocalRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadLocalRandom.html)
- [Java 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [OpenTelemetry — Trace sampling: head/tail/parent-based và trade-offs](https://opentelemetry.io/docs/concepts/sampling/)
