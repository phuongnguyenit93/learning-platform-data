# Producer–consumer và queue có giới hạn trong Java

## 1. Bài toán và mục tiêu

**Producer–consumer** là mô hình nhiều luồng tạo công việc (producer), đưa công việc vào một vùng đệm chung (queue), còn một hoặc nhiều luồng khác lấy công việc ra để xử lý (consumer). Producer và consumer chạy độc lập, có tốc độ biến động, nên cần một cơ chế trao đổi an toàn giữa các luồng.

Với **bounded queue** (hàng đợi có giới hạn), số phần tử đang chờ không được vượt quá một dung lượng `capacity` đã chọn. Đây là thiết kế quan trọng để giới hạn mức tiêu thụ bộ nhớ, điều tiết tốc độ sản xuất và tạo **backpressure**: khi consumer chưa theo kịp, producer phải chờ, hết thời gian chờ hoặc nhận một quyết định từ chối rõ ràng.

Sau bài này, bạn cần có thể:
- Giải thích quan hệ giữa producer, queue, consumer, dung lượng và backpressure.
- Chọn đúng phương thức `put`, `take`, `offer`, `poll` và xử lý ngắt luồng.
- Xây một luồng xử lý công việc Java với `ArrayBlockingQueue` mà không mất tác vụ do lỗi đồng bộ thông thường.
- Thiết kế kết thúc, kiểm soát quá tải, quan sát hiệu năng và kiểm thử các trường hợp queue đầy/rỗng.

Phạm vi là **Java concurrency nói chung**, sử dụng các API trong JDK, không phụ thuộc framework.

## 2. Từ mô hình đến các bất biến

Giả sử producer nhận sự kiện, consumer xử lý từng sự kiện:

~~~text
Producer P1 ──┐
              ├──> [ bounded FIFO queue: capacity = 3 ] ──> Consumer C1
Producer P2 ──┘                                    └───────> Consumer C2
~~~

Tại mọi thời điểm, nếu `size` là số tác vụ đang đợi trong queue, bất biến cơ bản là:

~~~text
0 <= size <= capacity
~~~

- **Queue chưa đầy:** producer có thể đặt thêm phần tử.
- **Queue đầy:** `put` phải đợi đến khi có chỗ; `offer` không thời hạn trả `false` ngay; `offer(timeout)` đợi tối đa khoảng thời gian cho phép.
- **Queue chưa rỗng:** consumer lấy một phần tử ra.
- **Queue rỗng:** `take` chờ công việc mới; `poll` không thời hạn trả `null` ngay; `poll(timeout)` chờ có giới hạn.
- **FIFO:** `ArrayBlockingQueue` lấy ra theo thứ tự *được đưa vào queue*. Khi nhiều producer cùng chạy, thứ tự giữa các producer không cố định; khi nhiều consumer cùng xử lý, **thứ tự hoàn thành** cũng có thể khác thứ tự lấy ra.

Ví dụ queue dung lượng 2, chỉ có một producer và một consumer:

| Bước | Hành động | Nội dung queue sau bước |
| --- | --- | --- |
| 1 | P đặt A | [A] |
| 2 | P đặt B | [A, B] (đầy) |
| 3 | P gọi `put(C)` | Vẫn [A, B]; P đang chờ |
| 4 | C gọi `take()` lấy A | [B]; P có cơ hội tiếp tục |
| 5 | `put(C)` hoàn tất | [B, C] |

Không cần consumer gọi một API “đánh thức producer” thủ công: `BlockingQueue` thực hiện điều phối này. Tuy vậy, vừa có chỗ trống không có nghĩa producer đang đợi sẽ được CPU chạy ngay; bộ lập lịch luồng quyết định thời điểm thực thi.

### Queue giải quyết điều gì, và không giải quyết điều gì?

`BlockingQueue` phối hợp luồng và trao đổi phần tử an toàn mà không cần người dùng tự khóa quanh từng thao tác `put`/`take`. Nó cũng cung cấp quan hệ **happens-before**: các hành động của một luồng trước khi đưa phần tử vào `BlockingQueue` xảy ra trước các hành động của luồng khác sau khi lấy/truy cập phần tử đó từ queue. Điều này hỗ trợ công bố đối tượng an toàn qua queue.

Nhưng queue **không** làm cho bản thân đối tượng công việc trở thành bất biến. Nếu producer tiếp tục sửa một đối tượng mutable sau khi enqueue trong khi consumer đọc đối tượng đó, bạn vẫn có thể gặp race condition. Ưu tiên truyền dữ liệu bất biến (`record` hoặc đối tượng chỉ đọc), hoặc có đồng bộ riêng cho trạng thái mutable.

Queue cũng không tự cung cấp lưu trữ bền vững, retry, transaction, chống xử lý trùng hay đảm bảo tác vụ đã hoàn thành. Consumer lấy thành công chỉ chứng minh tác vụ đã rời queue, chưa chứng minh xử lý nghiệp vụ đã thành công.

## 3. Các phương thức quan trọng của `BlockingQueue<E>`

| Ý định | Đợi vô hạn theo thiết kế API | Trả kết quả ngay | Đợi có thời hạn |
| --- | --- | --- | --- |
| Thêm phần tử khi queue đầy | `put(e)` | `offer(e)` trả `false` | `offer(e, timeout, unit)` trả `false` khi hết hạn |
| Lấy phần tử khi queue rỗng | `take()` | `poll()` trả `null` | `poll(timeout, unit)` trả `null` khi hết hạn |

Các API khác cần phân biệt:

- `add(e)` ném `IllegalStateException` nếu queue có giới hạn và đã đầy; `remove()` ném `NoSuchElementException` nếu rỗng.
- `peek()` đọc phần tử đầu nhưng **không lấy ra**; trả `null` nếu rỗng.
- `remainingCapacity()` và `size()` chỉ phản ánh trạng thái tại một thời điểm. Giữa thao tác kiểm tra và thao tác enqueue có thể có luồng khác thay đổi queue; vì thế đừng viết kiểu “`if (remainingCapacity() > 0) put(...)`” với kỳ vọng không bao giờ bị chặn.
- `drainTo(collection, n)` chuyển nhiều phần tử đang chờ sang collection nhằm giảm số lần lấy; không tự động biến việc xử lý cả batch thành một transaction.
- `BlockingQueue` không chấp nhận phần tử `null`, vì `null` được dùng làm tín hiệu “không có phần tử” cho một số phương thức.

**Điểm cần nhớ:** “đợi vô hạn” mô tả không đặt timeout trong API; luồng vẫn có thể bị interrupt. Các phương thức `put`, `take` và các bản timeout khai báo `InterruptedException`. Đừng nuốt ngoại lệ này rồi tiếp tục vòng lặp vô tận.

## 4. Ví dụ Java 17 chạy được: hai producer, hai consumer, queue dung lượng 3

Ví dụ dùng `ArrayBlockingQueue<Work>`, một record bất biến làm thông điệp, `ExecutorService` quản lý luồng và một thông điệp dừng chuyên biệt (**poison pill**) cho mỗi consumer. Main chỉ phát tín hiệu dừng **sau khi tất cả producer hoàn tất**, để không có công việc mới đứng sau tín hiệu dừng.

Lưu tệp **ProducerConsumerDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ProducerConsumerDemo {
    record Work(int producerId, int sequence) {}

    // Giá trị này nằm ngoài miền dữ liệu công việc thông thường.
    private static final Work STOP = new Work(-1, -1);

    public static void main(String[] args) throws Exception {
        int producerCount = 2;
        int consumerCount = 2;
        int workPerProducer = 6;

        BlockingQueue<Work> queue = new ArrayBlockingQueue<>(3);
        ExecutorService pool =
                Executors.newFixedThreadPool(producerCount + consumerCount);
        AtomicInteger produced = new AtomicInteger();
        AtomicInteger consumed = new AtomicInteger();

        List<Future<?>> producers = new ArrayList<>();
        List<Future<?>> consumers = new ArrayList<>();

        try {
            for (int i = 0; i < producerCount; i++) {
                final int id = i;
                producers.add(pool.submit(() -> {
                    for (int n = 1; n <= workPerProducer; n++) {
                        queue.put(new Work(id, n));
                        produced.incrementAndGet();
                    }
                    return null;
                }));
            }

            for (int i = 0; i < consumerCount; i++) {
                consumers.add(pool.submit(() -> {
                    while (true) {
                        Work work = queue.take();
                        if (work.equals(STOP)) {
                            return null;
                        }

                        // Nơi thực hiện xử lý nghiệp vụ cho "work".
                        // Ví dụ đếm một tác vụ đã xử lý thành công.
                        consumed.incrementAndGet();
                    }
                }));
            }

            // get() còn chuyển lỗi của producer về main.
            for (Future<?> producer : producers) {
                producer.get();
            }

            // Mỗi consumer phải nhận một tín hiệu dừng.
            for (int i = 0; i < consumerCount; i++) {
                queue.put(STOP);
            }

            // Đợi các consumer xử lý xong, đồng thời nhận lỗi nếu có.
            for (Future<?> consumer : consumers) {
                consumer.get();
            }

            System.out.printf(
                    "produced=%d, consumed=%d, remaining=%d%n",
                    produced.get(), consumed.get(), queue.size());
        } finally {
            // Khi gặp lỗi, đánh thức những tác vụ còn đang đợi bằng interrupt.
            // Trên đường thành công mọi Future ở trên đều đã hoàn tất.
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac ProducerConsumerDemo.java
java ProducerConsumerDemo
~~~

Kết quả cuối **xác định** của ví dụ, dù lịch thực thi của các luồng không xác định:

~~~text
produced=12, consumed=12, remaining=0
~~~

**Vì sao đúng?**

1. Hai producer sinh tổng cộng `2 × 6 = 12` phần tử. `put` chỉ trở về sau khi queue nhận phần tử; biến `produced` tăng ngay sau đó.
2. Bốn luồng chạy trên pool có bốn worker, nên có luồng producer và consumer để tiến hành đồng thời. Khi queue đầy, producer đợi; khi rỗng, consumer đợi.
3. Main gọi `get()` của **mọi producer** trước khi enqueue hai STOP. Với FIFO, STOP được xếp sau toàn bộ công việc đã enqueue; mỗi consumer nhận STOP sẽ rời vòng lặp.
4. `get()` của **mọi consumer** chỉ kết thúc sau khi các tác vụ trước STOP đã được lấy và đếm. Vì vậy `consumed == 12` và queue rỗng.
5. Nếu một tác vụ trong pool ném ngoại lệ, `Future.get()` ném `ExecutionException`, không bị bỏ qua âm thầm. Khối `finally` gửi interrupt khi cần dọn dẹp.

Đây là mẫu minh họa **kết thúc có kiểm soát khi mọi producer hoàn thành bình thường**. Trong hệ thống chạy liên tục, phải thiết kế thêm đường xử lý cho producer thất bại, consumer chết sớm, công việc treo hoặc yêu cầu hủy; chỉ gọi `put(STOP)` có thể mắc kẹt nếu queue đầy mà không còn consumer hoạt động.

**Lưu ý kiểm chứng:** bộ đếm ở đây mô phỏng xử lý thành công tức thì. Nếu thay comment bằng một thao tác có thể thất bại, chỉ tăng `consumed` sau khi thao tác thành công, và xác định chính sách lỗi riêng.

## 5. Khi quá tải: đợi, hết hạn, từ chối hay bỏ công việc?

Không có một chính sách phù hợp cho mọi hệ thống. Chọn theo thời gian chờ chấp nhận được, chi phí mất dữ liệu và cách phía gửi phản ứng.

- **`put`:** producer chờ cho đến khi có chỗ hoặc bị ngắt; hữu ích khi không được phép bỏ công việc và có thể chấp nhận chờ. Nếu mọi thành phần đều phụ thuộc vòng chờ lẫn nhau, vẫn có thể tạo deadlock ở cấp ứng dụng.
- **`offer` không timeout:** trả `false` ngay khi đầy; phù hợp với yêu cầu phản hồi tức thì. **Bắt buộc kiểm tra boolean**.
- **`offer` có timeout:** chờ một ngân sách thời gian có giới hạn; khi hết hạn, quyết định trả lỗi, retry có giới hạn, ghi nhận hoặc chuyển đến nơi khác.
- **Bỏ phần tử:** chỉ hợp lệ khi dữ liệu có thể bỏ theo yêu cầu nghiệp vụ (ví dụ sự kiện đo lường có thể lấy mẫu). Cần đo lượng bị bỏ.
- **Điều chỉnh upstream:** giảm tốc độ nhận, giảm mức đồng thời tạo việc, hoặc đưa tín hiệu quá tải về phía gửi.

Ví dụ nhỏ, độc lập, dùng một queue dung lượng 1 và **không có consumer**, để thấy chính xác các giá trị trả về. Lưu tệp **QueueOfferDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public class QueueOfferDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);

        System.out.println(queue.offer("A"));
        System.out.println(queue.offer("B"));
        System.out.println(queue.offer("B", 50, TimeUnit.MILLISECONDS));
        System.out.println(queue.poll());
        System.out.println(queue.poll());
    }
}
~~~

~~~bash
javac QueueOfferDemo.java
java QueueOfferDemo
~~~

Stdout:

~~~text
true
false
false
A
null
~~~

Lần `offer("B", 50, MILLISECONDS)` có thể thức dậy vì bị interrupt (khi đó ném `InterruptedException`), nhưng trong chương trình đơn luồng này không có consumer, không có thao tác ngắt, nên queue luôn đầy đến khi hết hạn và trả `false`. Không suy ra thời gian thực thi chính xác bằng 50 ms: lịch CPU và thời gian hệ thống có sai số.

### Timeout là một hợp đồng, không chỉ một con số

Nếu một request có tổng ngân sách 200 ms, đừng cho enqueue chờ 200 ms **rồi** tiếp tục xử lý nghiệp vụ thêm 200 ms và vẫn gọi đó là request 200 ms. Hãy quản lý một deadline hoặc chia ngân sách thời gian giữa các giai đoạn, có xử lý khi không thể nhận thêm công việc.

Ví dụ chính sách:
- Thành công enqueue trong 20 ms → nhận yêu cầu.
- Hết 20 ms mà queue còn đầy → phản hồi “đang quá tải”, đếm một lần từ chối.
- Phía gọi quyết định có retry hay không; nếu retry, cần backoff, giới hạn số lần, và kiểm soát khả năng xử lý trùng.

`InterruptedException` là tín hiệu điều khiển quan trọng. Khi phương thức cho phép `throws InterruptedException`, thường nên **propagate**; nếu buộc phải bắt để thoát vòng, gọi `Thread.currentThread().interrupt()` trước khi trả về hoặc dừng xử lý để giữ trạng thái ngắt cho tầng gọi. Không viết `catch (InterruptedException e) {}`.

## 6. Chọn queue phù hợp

| Cấu trúc trong `java.util.concurrent` | Dung lượng/đặc tính | Khi nên dùng hoặc lưu ý |
| --- | --- | --- |
| `ArrayBlockingQueue<E>` | Dung lượng cố định khi tạo; FIFO; nội bộ dùng mảng | Lựa chọn rõ ràng cho bounded producer–consumer. |
| `LinkedBlockingQueue<E>` | Có thể chỉ định capacity; nếu không, capacity mặc định là `Integer.MAX_VALUE` | Hợp lệ nếu truyền giới hạn rõ ràng; mặc định “gần như không giới hạn” dễ tăng bộ nhớ khi backlog. |
| `LinkedBlockingDeque<E>` | Có thể bounded; thêm/lấy ở hai đầu | Dùng khi thật sự cần thao tác hai đầu; cần quy định rõ chính sách thứ tự. |
| `SynchronousQueue<E>` | Không lưu phần tử chờ (capacity logic bằng 0); mỗi lần chuyển giao cần bên nhận phù hợp | Handoff trực tiếp, không tạo backlog trong queue; hành vi chờ/từ chối khác bounded buffer thông thường. |
| `PriorityBlockingQueue<E>` | Không bounded theo tham số capacity; lấy theo ưu tiên | Không thay cho bounded FIFO; có thể đói tác vụ ưu tiên thấp. |
| `DelayQueue<E>` | Queue không bounded, chỉ lấy phần tử hết độ trễ | Phù hợp lập lịch trì hoãn, không phải cơ chế chặn backlog theo capacity. |
| `ConcurrentLinkedQueue<E>` | Non-blocking, không bounded; không có `take`/`put` | Khi cần hàng đợi đồng thời không chặn và đã có cơ chế chờ/giới hạn riêng. |

Đừng nhầm **thread-safe** với **bounded**. Một queue an toàn luồng nhưng không có giới hạn vẫn có thể làm hệ thống cạn bộ nhớ nếu producer nhanh hơn consumer lâu dài.

`ArrayBlockingQueue` hỗ trợ constructor `new ArrayBlockingQueue<>(capacity, true)` để chọn thứ tự phục vụ công bằng hơn cho các luồng đang chờ. Chế độ công bằng có thể giảm throughput; nó không đảm bảo mọi tác vụ nghiệp vụ có latency bằng nhau hoặc consumer hoàn thành đúng thứ tự enqueue. Dùng mặc định khi chưa có lý do đo lường cụ thể.

## 7. Backpressure và cách xác định dung lượng

Gọi:
- `λ` là tốc độ phần tử đến (items/giây).
- `μ` là tốc độ xử lý **tổng cộng** của tất cả consumer (items/giây).
- `C` là capacity của queue; `Q` là số phần tử đang chờ.

Nếu tải đến duy trì ở mức **`λ > μ`**, backlog tăng dần cho tới khi queue đầy. Tăng `C` chỉ trì hoãn thời điểm đầy; không sửa được thiếu hụt năng lực xử lý. Nếu `λ < μ` trong dài hạn, vẫn có thể gặp queue đầy do burst ngắn, jitter, GC pause, I/O chậm hay tác vụ có độ dài không đều.

Một quy trình chọn capacity thực tế:

1. Đo tốc độ đến trung bình và ở giờ cao điểm, phân phối thời gian xử lý, số consumer thực sự chạy được.
2. Xác định **thời gian đợi tối đa chấp nhận được** của công việc và mức dùng bộ nhớ tối đa. Queue là vùng chờ, không phải kho vô hạn.
3. Ước lượng backlog của một burst: ví dụ 200 công việc/giây trong 0,5 giây mà consumer tạm ngừng có thể tạo khoảng 100 phần tử đang chờ; cần cộng phần tồn trước đó và độ biến động.
4. Ước lượng bộ nhớ = số phần tử lưu × kích thước thực tế của phần tử và dữ liệu mà nó tham chiếu + overhead queue. Đừng chỉ đo kích thước record rỗng nếu nó giữ một payload lớn.
5. Chạy thử với lưu lượng bình thường, burst và sự cố consumer chậm; quan sát các percentile latency, timeout/reject, GC và CPU. Điều chỉnh cả tốc độ nhận, concurrency và capacity.

Quan hệ Little `L = λ × W` có thể giúp phân tích **hệ thống ổn định** khi định nghĩa nhất quán số công việc đang ở hệ thống, tốc độ hoàn thành và thời gian lưu trú. Không dùng công thức đó như một cách bảo đảm capacity trong tình huống tải luôn vượt năng lực hoặc burst cực đoan. Queue dài có thể tăng latency ngay cả khi throughput nhìn có vẻ tốt.

**Đối với consumer làm CPU-bound**, thêm luồng vượt quá mức CPU hữu ích thường chỉ tăng chuyển ngữ cảnh. **Đối với công việc I/O-bound**, nhiều consumer hơn có thể tăng throughput nếu hệ thống downstream cho phép, nhưng cũng có thể chuyển điểm nghẽn sang kết nối, cơ sở dữ liệu hoặc dịch vụ khác. Mọi quyết định concurrency phải đo thực tế.

## 8. Đóng hệ thống và xử lý lỗi

### Cách 1 — Poison pill khi đã biết producer hoàn tất

Cách dùng trong ví dụ phù hợp với tập producer/consumer đã biết và muốn **xử lý nốt công việc còn trong queue**. Điều kiện đúng gồm:

- Ngừng producer hoặc đợi tất cả producer hoàn thành trước khi đặt STOP.
- Đặt **một STOP cho mỗi consumer** đang hoạt động và thực sự sẽ đọc STOP.
- STOP không được trùng một giá trị công việc thật.
- Không có producer mới enqueue sau STOP; nếu không, công việc có thể bị bỏ lại.
- Nếu consumer đã chết hoặc queue đầy mãi, main có thể bị kẹt ở `put(STOP)`; cần đường lỗi/cancellation riêng.

Poison pill là một **quy ước ứng dụng**, không phải chức năng đóng queue được cung cấp bởi `BlockingQueue`. Queue không tự có thao tác `close()` theo giao diện này.

### Cách 2 — Hủy bằng interrupt/cancellation

Khi phải dừng khẩn cấp, có thể giữ các `Future`, gọi `cancel(true)`, hoặc gọi `shutdownNow()` trên executor rồi chờ kết thúc có giới hạn. Các thao tác chặn đáp ứng interrupt bằng `InterruptedException`. Tuy nhiên, phương thức không hỗ trợ interrupt hoặc công việc đang thực hiện I/O không có timeout có thể không dừng ngay. `shutdownNow()` là nỗ lực hủy, không cam kết mọi task đã dừng.

Phân biệt hai yêu cầu nghiệp vụ:
- **Graceful drain:** ngừng nhận công việc mới, xử lý nốt queue, cho consumer thoát, rồi đóng tài nguyên.
- **Immediate stop:** yêu cầu dừng nhanh, chấp nhận hoặc xử lý riêng các phần tử còn tồn và công việc đang dang dở.

Đừng dùng `ExecutorService.shutdown()` rồi kỳ vọng nó tự làm consumer đang chờ `take()` thoát: `shutdown()` chỉ ngừng nhận task mới và chờ task đang chạy; nó không tự gửi sentinel hay interrupt các task đang chặn.

### Nếu xử lý thất bại thì sao?

Ngay khi `take()` thành công, phần tử đã bị gỡ khỏi queue. Nếu consumer ném exception sau đó, queue **không tự đưa lại** phần tử. Bạn phải chọn một chính sách có chủ đích: ghi lỗi và bỏ, retry có giới hạn, đưa vào queue retry riêng, hoặc lưu vào hệ thống bền vững khi yêu cầu không mất dữ liệu. Retry phải có backoff và khả năng nhận diện công việc trùng; retry ngay vào cùng queue đang đầy có thể làm quá tải thêm trầm trọng.

Không suy luận “exactly once” hay độ bền dữ liệu từ `BlockingQueue`. Với lỗi tiến trình/JVM, các phần tử trong bộ nhớ có thể mất. Nếu cần lưu trữ bền và xác nhận xử lý, thiết kế thêm tầng dữ liệu phù hợp.

## 9. Tại sao `wait/notifyAll` vẫn đáng hiểu?

`BlockingQueue` thường là lựa chọn tốt hơn tự viết vùng đệm. Nhưng hiểu cơ chế monitor giúp phân tích các lỗi race condition. Đoạn sau là **một lớp minh họa**, không phải chương trình chạy độc lập; muốn chạy cần thêm `main` và luồng gọi:

~~~java
import java.util.ArrayDeque;
import java.util.Objects;

final class MonitorBuffer<T> {
    private final ArrayDeque<T> items = new ArrayDeque<>();
    private final int capacity;

    MonitorBuffer(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.capacity = capacity;
    }

    public synchronized void put(T value) throws InterruptedException {
        Objects.requireNonNull(value);
        while (items.size() == capacity) {
            wait();
        }
        items.addLast(value);
        notifyAll();
    }

    public synchronized T take() throws InterruptedException {
        while (items.isEmpty()) {
            wait();
        }
        T value = items.removeFirst();
        notifyAll();
        return value;
    }
}
~~~

Các điểm cốt lõi:

- `synchronized` đảm bảo các bước kiểm tra trạng thái và sửa deque có tính loại trừ lẫn nhau, đồng thời cung cấp quy tắc visibility của monitor.
- `wait()` nhả monitor trong lúc chờ và lấy lại monitor trước khi tiếp tục. Nó **phải** được gọi khi luồng đang giữ monitor của đối tượng tương ứng.
- Dùng **`while` thay vì `if`** vì có thể có spurious wakeup, hoặc một luồng khác giành phần tử/chỗ trống trước luồng vừa thức dậy.
- `notifyAll()` đánh thức các bên chờ để tự kiểm tra lại điều kiện; cách này đơn giản và an toàn về logic cho buffer có cả producer và consumer chờ, dù có thể gây thêm lần đánh thức.
- Thực thi xử lý nghiệp vụ chậm **ngoài** synchronized block để tránh giữ khóa quá lâu; ví dụ ở trên chỉ thao tác deque khi giữ monitor.

Lớp tự viết cần thêm kiểm thử concurrency, xử lý đóng/hủy và quan sát hoạt động. Trong mã ứng dụng, ưu tiên `ArrayBlockingQueue` hoặc primitive JDK thích hợp để giảm diện tích lỗi.

## 10. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `LinkedBlockingQueue<>()` mặc định và gọi nó là bounded | Backlog tăng rất lớn khi quá tải | Truyền capacity rõ ràng hoặc dùng `ArrayBlockingQueue`. |
| Gọi `offer` nhưng bỏ qua kết quả | Mất công việc âm thầm | Xử lý `false` bằng chính sách từ chối/retry rõ ràng. |
| Kiểm tra `size` trước `put` như một điều kiện bất biến | Check–then–act race; vẫn có thể bị chặn | Dùng trực tiếp phương thức queue với chính sách chờ phù hợp. |
| Gọi `take` trên một consumer phải dừng nhưng không có cơ chế hủy | Consumer chờ mãi khi queue rỗng | Thiết kế sentinel, timeout, interrupt hoặc vòng đời riêng. |
| Chỉ gửi một STOP cho nhiều consumer | Một consumer thoát, các consumer khác có thể chờ mãi | Một tín hiệu dừng cho mỗi consumer hoặc cơ chế đóng khác. |
| Đặt STOP trước khi producer hoàn tất | Có thể còn tác vụ đứng sau STOP và bị bỏ lại | Tách pha ngừng producer và pha drain. |
| Bắt rồi nuốt `InterruptedException` | Khó hủy, ứng dụng treo khi shutdown | Propagate hoặc khôi phục interrupt và thoát. |
| Giữ đối tượng mutable rồi sửa sau enqueue | Consumer thấy trạng thái không nhất quán | Truyền message bất biến hoặc đồng bộ trạng thái riêng. |
| Đếm số lần `take` như số tác vụ xử lý thành công | Chỉ số thành công sai khi xử lý ném exception | Đếm sau điểm hoàn tất, theo dõi failures/retries riêng. |
| Tăng capacity vô hạn để chữa consumer chậm | Tăng latency, RAM, nguy cơ OOM | Sửa throughput, giới hạn nhận và chính sách quá tải. |

## 11. Quan sát, kiểm thử và các giới hạn cần chứng minh

**Chỉ số nên đo:** độ đầy queue (`size / capacity`), số lần `offer` bị từ chối hoặc timeout, thời gian producer đợi enqueue, thời gian tác vụ nằm trong queue, thời gian xử lý, throughput producer/consumer, số consumer đang hoạt động, số lỗi/retry, tốc độ tăng backlog và percentile độ trễ. Hãy ghi nhận theo thời gian; snapshot `size()` không đủ phản ánh spike ngắn.

Về kiểm thử, nên có các trường hợp có kỳ vọng rõ:

1. **Queue đầy:** capacity = 1; cho một phần tử vào, xác minh `offer` tiếp theo trả `false` và timed offer hết hạn khi không có consumer.
2. **Queue rỗng:** xác minh `poll` trả `null`; kiểm thử `take` bằng một luồng riêng rồi đặt phần tử từ luồng khác để quan sát unblock.
3. **Nhiều producer và consumer:** sinh ID duy nhất, thu các ID đã xử lý vào một cấu trúc thread-safe, xác nhận đủ số lượng và mỗi ID đúng một lần trong điều kiện không có lỗi xử lý.
4. **Interrupt:** cho worker chờ ở `put` hoặc `take`, ngắt nó và xác minh worker thoát theo hợp đồng đã định.
5. **Shutdown:** dừng producer, phát đủ STOP, xác nhận mọi worker kết thúc trong timeout; có đường dọn dẹp khi một producer hoặc consumer thất bại.
6. **Burst/quá tải:** tạo tốc độ đến cao hơn tốc độ tiêu thụ tạm thời và xác nhận queue không vượt capacity, thời gian chờ/từ chối đúng chính sách.

Để kiểm thử nhiều luồng, ưu tiên `CountDownLatch`/`CyclicBarrier` điều phối thời điểm bắt đầu và `Future.get(timeout, unit)` để tránh treo vô hạn. Không dựa hoàn toàn vào `Thread.sleep(...)` để “chờ chắc” một trạng thái race: test có thể ngẫu nhiên pass/fail theo máy chạy. Dùng deadline ở test để phát hiện deadlock và luôn thu dọn executor.

### Tình huống tự kiểm tra

**Tình huống A:** Producer tạo 500 công việc/giây, consumer tổng cộng chỉ xử lý được 350 công việc/giây liên tục. Tăng capacity từ 1.000 lên 10.000 có làm hệ thống bền vững không?

**Đáp án:** Không. Trong giai đoạn tốc độ giữ nguyên, backlog tăng khoảng 150 công việc/giây cho đến khi đầy. Capacity lớn chỉ tăng thời gian trước khi backpressure/timeout/reject xảy ra và thường tăng latency. Cần giảm tải đến hoặc tăng năng lực xử lý thực.

**Tình huống B:** Có ba consumer, hai producer, và muốn drain toàn bộ rồi dừng bằng poison pill. Cần bao nhiêu STOP, đặt khi nào?

**Đáp án:** Ba STOP, **sau khi cả hai producer đã xác nhận hoàn tất** và không còn producer mới đưa việc vào queue. Sau đó chờ tất cả consumer kết thúc; chuẩn bị đường lỗi nếu consumer không còn hoạt động.

**Tình huống C:** Consumer lấy được tác vụ, sau đó xử lý ném exception. `BlockingQueue` có tự retry không?

**Đáp án:** Không. `take()` đã xóa tác vụ khỏi queue; việc xử lý thất bại phải được ứng dụng quản lý bằng chính sách lỗi/retry riêng.

## 12. Quy tắc áp dụng

Khi triển khai producer–consumer trong Java, trước hết xác định **dữ liệu có được phép mất không**, thời gian đợi tối đa, số consumer, năng lực downstream và cách shutdown. Nếu cần bounded FIFO trong bộ nhớ, khởi đầu bằng `ArrayBlockingQueue` với capacity được đo và kiểm tra, chọn `put` hoặc `offer(timeout)` theo hợp đồng quá tải, xử lý đầy đủ `InterruptedException`, bảo đảm thứ tự kết thúc producer–consumer, và đo backlog cùng latency dưới tải thực.

Điểm mạnh của bounded queue là nó biến việc **consumer chậm hơn producer** thành trạng thái có giới hạn, nhìn thấy được và có thể xử lý. Việc lựa chọn phải đi cùng chính sách chờ, từ chối, xử lý lỗi và đóng hệ thống — chỉ tạo một đối tượng queue chưa đủ để hoàn thành thiết kế đồng thời.