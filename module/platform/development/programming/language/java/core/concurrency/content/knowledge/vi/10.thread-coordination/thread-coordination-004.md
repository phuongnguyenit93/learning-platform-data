# Producer–consumer với hàng đợi giới hạn trong Java Concurrency

> **Bối cảnh:** Phối hợp luồng (*thread coordination*) trong Java SE, đặc biệt là giao tiếp giữa producer và consumer qua **bounded blocking queue**. Bài trình bày `BlockingQueue`, `ArrayBlockingQueue`, `LinkedBlockingQueue`, backpressure, xử lý lỗi/dừng luồng và cơ chế triển khai bằng `Lock` + `Condition`. Phạm vi là **concurrency Java nói chung**; các API và cơ chế đặc thù của Spring thuộc một chương khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích mô hình **producer–consumer** và tại sao cần một **hàng đợi có giới hạn sức chứa** thay vì cho producer đẩy dữ liệu không kiểm soát.
- Phân biệt ba trạng thái **queue rỗng / có dữ liệu / đầy** cùng những hành vi chờ tương ứng của producer và consumer.
- Chọn đúng API `put`, `take`, `offer`, `poll`, timeout và biết tại sao không dùng `sleep` để chờ dữ liệu.
- Giải thích **backpressure** và các chính sách xử lý khi hệ thống tạo dữ liệu nhanh hơn khả năng tiêu thụ.
- Dùng `ArrayBlockingQueue` để xây một ví dụ Java 17 chạy được, có capacity, tín hiệu kết thúc, thu thập kết quả và đóng `ExecutorService`.
- Phân tích **memory visibility**, thứ tự FIFO, nhiều producer/consumer, điều kiện “đã xử lý xong”, nguy cơ deadlock/starvation và giới hạn độ bền dữ liệu.
- Hiểu hàng đợi bounded có thể được xây bằng **một `ReentrantLock` và hai `Condition`**, nhưng biết khi nào nên ưu tiên implementation chuẩn.
- Viết test và số liệu giám sát để phân biệt **tắc nghẽn bình thường có backpressure** với lỗi concurrency.

**Nguyên tắc trung tâm:** bounded queue là ranh giới đồng bộ giữa **tốc độ sản xuất** và **tốc độ xử lý**. Producer có thể phải đợi khi queue đầy, consumer có thể phải đợi khi queue rỗng. Việc đợi và truyền dữ liệu cần được điều phối bằng primitive có bảo đảm concurrency thực sự, không bằng đoán thời gian.

## 2. Mô hình producer–consumer

Producer tạo ra một **item** hoặc **work item**; consumer lấy item và xử lý. Hai vai trò có thể nằm trên những thread khác nhau và chạy với tốc độ khác nhau.

```text
   Producer P1 --\
                  \
   Producer P2 ----> [ BOUNDED QUEUE: capacity = N ] ---> Consumer C1
                  /                 |                   ---> Consumer C2
   Producer P3 --/             0 <= size <= N

Producer chờ khi đầy:            size == N
Consumer chờ khi rỗng:           size == 0
Khi có item / có chỗ:            luồng liên quan có thể tiếp tục
```

Hai trường hợp đặc biệt:

- **Queue rỗng:** consumer gọi một operation chờ như `take()` sẽ ngủ cho tới khi có item, thread bị interrupt hoặc xảy ra diễn biến phù hợp với contract của primitive.
- **Queue đầy:** producer gọi `put()` sẽ chờ cho tới khi một consumer lấy bớt item, hoặc producer bị interrupt.

Một hàng đợi giới hạn có khả năng chứa không quá **N phần tử đang ở trong queue**. Điều đó **không giới hạn tổng số công việc đã được lấy ra và đang xử lý**, cũng không ngăn consumer tiếp tục gọi một downstream service chậm. Cần tính cả **in-flight work** khi giới hạn tài nguyên toàn pipeline.

### Ví dụ thực tế

- Nhận log event rồi có worker ghi ra đĩa.
- Nhận ảnh rồi có worker biến đổi/kích thước/encode.
- Đọc dữ liệu từ một file lớn, chuyển các batch nhỏ cho nhiều CPU worker xử lý.
- Nhận command nội bộ JVM rồi một owner duy nhất cập nhật state.
- Đọc thông điệp từ nguồn ngoài rồi đẩy vào pipeline trong-memory có giới hạn số lượng chờ.

Đây là **mô hình nội bộ Java process**. Khi dữ liệu không được mất dù process crash, một `BlockingQueue` trong RAM **không thay thế** broker/persistent log/transaction store.

## 3. Vì sao “bounded” là thuộc tính quan trọng?

Giả sử producer trung bình tạo **120 item/giây**, consumer chỉ xử lý **100 item/giây**. Nếu cứ tiếp tục trong một phút và không có cơ chế kiểm soát, backlog lý tưởng hóa tăng khoảng:

```text
(120 - 100) item/s × 60 s = 1.200 item
```

Đây chỉ là phép ước lượng khi tốc độ ổn định, chưa tính burst, variance và in-flight. Nếu queue không giới hạn thực tế, backlog có thể tiếp tục ăn RAM cho đến khi GC tăng mạnh hoặc ứng dụng bị `OutOfMemoryError`.

Với queue capacity 200:

- **Số item đang xếp hàng** tối đa là 200, theo invariant của queue.
- Khi đầy, `put()` buộc producer **đợi consumer lấy bớt**, nên áp lực lan ngược đến nguồn sản xuất.
- Hệ thống có thể ổn định về lượng dữ liệu **đang giữ trong queue**, nhưng không có phép màu biến consumer 100 item/s thành 120 item/s.
- Khi source không cho phép producer block (ví dụ luồng network/event callback có deadline), chương trình cần chính sách `offer`, timeout, reject, drop, retry hoặc throttle rõ ràng.

**Backpressure** là khả năng tầng tiêu thụ phát tín hiệu “chưa nhận thêm được” cho tầng sản xuất. Tín hiệu có thể là **blocking**, boolean false, timeout, exception hoặc cơ chế điều tiết của tầng gọi. Bounded queue là một cách thiết lập backpressure nhưng cách xử lý phản ứng phụ thuộc application contract.

### Capacity không phải throughput

Tăng capacity có thể hấp thụ burst ngắn, nhưng không làm tăng tốc xử lý trung bình của consumer. Capacity quá lớn cũng không miễn phí: nó giữ nhiều object, làm tăng thời gian chờ của item và che khuất downstream bottleneck.

Chọn capacity dựa trên kích thước item, mức burst, SLA latency và throughput quan sát. Không dùng `Integer.MAX_VALUE` làm “bounded” nếu ngân sách RAM hữu hạn.

## 4. Java có sẵn BlockingQueue

`java.util.concurrent.BlockingQueue<E>` là interface cho queue phối hợp thread. Các API được thiết kế để làm việc khi chưa thể thêm/lấy item ngay.

| Hoạt động | Ném exception nếu không thực hiện ngay | Trả kết quả tức thì | Chờ vô thời hạn tới khi khả dụng | Chờ trong thời hạn |
|---|---|---|---|---|
| Thêm | `add(e)` | `offer(e)` → `false` khi đầy | `put(e)` | `offer(e, timeout, unit)` → boolean |
| Lấy và xóa | `remove()` | `poll()` → `null` khi rỗng | `take()` | `poll(timeout, unit)` → item hoặc `null` |
| Xem đầu, không xóa | `element()` | `peek()` | Không có phương thức blocking tương ứng | Không có phương thức timed tương ứng |

**Điểm nhớ nhanh:**

- `put(e)` chờ nếu đầy, có thể ném `InterruptedException`.
- `take()` chờ nếu rỗng, có thể ném `InterruptedException`.
- `offer(e)` không chờ chỗ trống: khi queue đầy, thường trả `false`.
- `poll()` không chờ item mới: khi rỗng, trả `null`.
- `offer(e, time, unit)` và `poll(time, unit)` giúp **ràng buộc thời gian chờ** và xử lý trường hợp tài nguyên không sẵn sàng.
- `add(e)` có thể ném `IllegalStateException` khi queue bị giới hạn và không còn sức chứa; `remove()` có thể ném `NoSuchElementException` nếu rỗng.
- Các implementation `BlockingQueue` chuẩn **không cho phép null item**, một phần vì `poll` dùng null làm tín hiệu “không có item”.

Đừng lấy kết quả `peek()` hay `size()` rồi tin queue sẽ giữ nguyên cho đến thao tác tiếp theo: thread khác có thể thay đổi giữa hai lời gọi. Nếu mục tiêu là “chờ rồi lấy”, gọi **`take()`** thay vì check-then-act bằng `size()`.

## 5. Chọn implementation phù hợp

### `ArrayBlockingQueue<E>`

```java
BlockingQueue<String> queue = new ArrayBlockingQueue<>(100);
```

Đây là **đoạn code trong method** có import `java.util.concurrent.BlockingQueue` và `java.util.concurrent.ArrayBlockingQueue`.

- Capacity cố định, **bắt buộc > 0**.
- Hàng đợi FIFO theo thứ tự enqueue của các item.
- Cài đặt sử dụng mảng có kích thước cố định và cơ chế lock/condition nội bộ.
- Có constructor `new ArrayBlockingQueue<>(capacity, fair)` để chọn chính sách fairness đối với những thread chờ truy cập; fairness có thể làm giảm throughput và **không bảo đảm** thời điểm một job hoàn thành.
- Phù hợp khi biết rõ số item tối đa cần đệm và muốn kiểm soát bộ nhớ tương đối dễ.

### `LinkedBlockingQueue<E>`

```java
BlockingQueue<String> queue = new LinkedBlockingQueue<>(100);
```

Đây là đoạn code minh họa với import `java.util.concurrent.LinkedBlockingQueue`. Implementation sử dụng các node liên kết và có thể đặt capacity trong constructor. Nó cũng hỗ trợ FIFO theo thứ tự enqueue.

**Cẩn thận:** `new LinkedBlockingQueue<>()` không phải bounded theo ngân sách thực tế của ứng dụng; nó có capacity mặc định `Integer.MAX_VALUE`. Đây là nguồn lỗi thường gặp: hệ thống nhìn như dùng queue thread-safe, nhưng khi producer nhanh hơn consumer, backlog vẫn có thể tăng đến mức kiệt bộ nhớ. **Luôn chỉ định capacity nếu boundedness là yêu cầu.**

### Các implementation có semantics khác

- `SynchronousQueue<E>` có **không có chỗ đệm item bên trong**: put/take là một cơ chế handoff trực tiếp giữa producer và consumer. Nó không giống `ArrayBlockingQueue<>(1)`.
- `PriorityBlockingQueue<E>` lấy theo **priority ordering**, không phải FIFO bounded queue; nó không cung cấp một hard capacity tương tự `ArrayBlockingQueue`.
- `DelayQueue<E>` dùng thời điểm đủ điều kiện của phần tử; không phải bounded FIFO thông thường.

Mỗi loại queue tạo một contract khác. Không đổi implementation chỉ vì tên đều kết thúc bằng “BlockingQueue”.

## 6. Ví dụ Java 17 chạy được: giới hạn capacity và chuyển việc

Chương trình có hai phần:

1. Minh họa capacity = 2 bằng `offer` và `take`: thêm đủ hai item, thử thêm item thứ ba khi đầy phải nhận `false`; lấy một item rồi thêm tiếp thành công.
2. Chạy **một producer và một consumer** dùng `ExecutorService`, truyền ba giá trị 5, 7, 9 qua bounded queue và gửi một **poison pill** để consumer biết khi nào dừng. Consumer trả `Result` cho main qua `Future.get()`.

Tạo file **`BoundedQueueDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BoundedQueueDemo {
    private static final int STOP = -1;
    record Result(int count, long sum) { }

    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> bounded = new ArrayBlockingQueue<>(2);
        System.out.println("offer10=" + bounded.offer(10));
        System.out.println("offer20=" + bounded.offer(20));
        System.out.println("offer30WhenFull=" + bounded.offer(30));
        System.out.println("firstTake=" + bounded.take());
        System.out.println("offer30AfterTake=" + bounded.offer(30));
        System.out.println("remaining=" + bounded.take() + "," + bounded.take());

        BlockingQueue<Integer> inbox = new ArrayBlockingQueue<>(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Result> consumer = pool.submit(() -> {
                int count = 0;
                long sum = 0;
                while (true) {
                    int value = inbox.take();
                    if (value == STOP) break;
                    count++;
                    sum += value;
                }
                return new Result(count, sum);
            });
            Future<?> producer = pool.submit(() -> {
                inbox.put(5);
                inbox.put(7);
                inbox.put(9);
                inbox.put(STOP);
                return null;
            });

            producer.get();
            Result result = consumer.get();
            System.out.println("consumedCount=" + result.count());
            System.out.println("consumedSum=" + result.sum());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac --release 17 BoundedQueueDemo.java
java BoundedQueueDemo
```

**Stdout đã biên dịch và chạy xác minh:**

```text
offer10=true
offer20=true
offer30WhenFull=false
firstTake=10
offer30AfterTake=true
remaining=20,30
consumedCount=3
consumedSum=21
```

### Giải thích phần capacity

- `new ArrayBlockingQueue<>(2)` khởi tạo queue rỗng, chứa tối đa hai phần tử.
- `offer(10)` và `offer(20)` thành công; queue đầy.
- `offer(30)` trả `false` **ngay**, không ngồi đợi consumer.
- `take()` lấy đầu FIFO là 10, tạo một chỗ trống.
- `offer(30)` lần sau thành công; hai item còn lại lần lượt là 20 và 30.
- Phần này chạy trong main để tạo **kết quả xác định**, không phụ thuộc vào scheduling.

### Giải thích phần producer–consumer

- `inbox` có capacity 2, nên producer có thể bị block ở `put(9)` hoặc `put(STOP)` nếu consumer chưa lấy kịp.
- `inbox.put(...)` vừa đảm nhiệm việc thêm item, vừa điều phối khi queue đầy; không cần code tự gọi `wait/notify`.
- Consumer gọi `inbox.take()` trong vòng lặp; khi queue rỗng, nó chờ producer.
- Giá trị `STOP=-1` được dành riêng làm tín hiệu kết thúc. Ba item hợp lệ là 5, 7, 9, nên consumer đếm chính xác 3 và tính tổng 21.
- `producer.get()` chờ producer hoàn thành việc enqueue cả ba item và STOP; `consumer.get()` chờ consumer thật sự xử lý xong và trả kết quả. Chỉ queue trống **không phải bằng chứng** mọi item đã xử lý xong.
- Pool có **hai worker threads**, đủ cho producer và consumer tiến triển ngay cả khi một bên đang block.
- `finally { pool.shutdownNow(); }` trong demo là đường cleanup sau các lần `get()`; tại đường chạy bình thường cả hai task đã hoàn tất. Ở ứng dụng thật, cần chiến lược graceful shutdown và timeout/cancellation riêng, không dùng shutdownNow như cách “đợi cho xong”.

**Lưu ý về STOP:** nếu dữ liệu hợp lệ có thể là -1, giao thức này **sai** vì consumer sẽ hiểu nhầm dữ liệu thành lệnh dừng. Khi thiết kế nghiêm túc, nên dùng kiểu thông điệp rõ ràng, ví dụ sealed interface `Message` với `Data` và `Stop`, hoặc một protocol đóng riêng. Với nhiều consumer, cần chính sách phát tín hiệu đóng tới từng consumer hoặc dùng cơ chế khác để họ không còn block ở `take()`.

## 7. Vì sao queue thread-safe mà payload vẫn có thể không an toàn?

`BlockingQueue` bảo vệ **cấu trúc queue và thao tác enqueue/dequeue**. Java concurrency API cũng quy định **memory consistency effects**: những hành động trong thread **trước khi đặt một object vào queue** *happen-before* các hành động trong thread khác **sau khi truy cập hoặc lấy object đó từ queue**.

Ví dụ:

```java
// Minh họa: queue là BlockingQueue<Message> và Message là immutable.
Message message = new Message(42, "ready");
queue.put(message);
// Thread khác: Message received = queue.take();
// Các trạng thái đã chuẩn bị trước put được công bố theo contract.
```

Đây là đoạn code minh họa; `Message` và `queue` được khai báo ở class ngoài, không phải chương trình độc lập.

**Nhưng queue không làm object mutable trở thành thread-safe mãi mãi.** Nếu producer đặt một tham chiếu `ArrayList` vào queue rồi vẫn tiếp tục `add` trên chính list đó trong khi consumer đang duyệt, hai bên có thể race trên **payload**, dù thao tác `put/take` đúng.

Các cách an toàn phổ biến:

1. **Immutable message:** xây dữ liệu đầy đủ rồi publish dưới dạng record/các trường immutable; nếu có collection, defensive copy và không chia sẻ phần tử mutable nguy hiểm.
2. **Ownership transfer:** sau khi enqueue mutable message, producer **ngừng sửa/đọc-mutate**; consumer trở thành owner cho đến khi bàn giao tiếp.
3. **Synchronized payload:** mọi lần đọc/ghi payload cùng dùng một synchronization protocol nếu bắt buộc chia sẻ để mutate.
4. **Snapshot/copy:** nếu producer cần tiếp tục sửa object gốc, đưa snapshot riêng vào queue.

`Future.get()` có thêm quan hệ memory consistency cho kết quả task, nhưng không thay thế queue publication khi consumer cần đọc dữ liệu trong lúc producer vẫn hoạt động.

## 8. Backpressure: chọn chính sách khi đầy

Có nhiều lựa chọn, tùy tính chất workload và SLO:

| Chính sách | Primitive thường dùng | Lợi ích | Rủi ro / điều cần định nghĩa |
|---|---|---|---|
| **Block producer** | `queue.put(item)` | Không bỏ item chỉ vì đầy; áp lực truyền ngược nguồn | Producer có thể bị treo lâu, giữ tài nguyên hoặc chiếm worker thread |
| **Fail fast / reject** | `queue.offer(item)` | Caller biết ngay queue đầy | Caller phải xử lý `false`; nếu bỏ qua là mất công việc |
| **Chờ có giới hạn** | `queue.offer(item, timeout, unit)` | Giới hạn thời gian producer có thể chờ | Khi timeout phải retry/drop/report theo contract; thời gian không đồng nghĩa đã enqueue |
| **Retry có điều kiện** | `offer` + bounded retries | Có thể vượt burst ngắn | Retry không giới hạn tạo vòng chờ hoặc tăng áp lực toàn hệ thống |
| **Drop có chủ đích** | Chỉ áp dụng cho dữ liệu được phép bỏ | Giữ latency, ngăn backlog | Mất dữ liệu; phải có metrics và nêu rõ loại item được bỏ |
| **Rate limiting / throttle upstream** | Cơ chế giới hạn ở producer/source | Ngăn backlog trước khi vào queue | Cần phối hợp nhiều tầng và phản hồi nguồn |
| **Scale consumer** | Tăng worker khi công việc có thể song song | Tăng khả năng tiêu thụ | Có thể làm downstream nghẽn hơn hoặc phá ordering/invariant |

**Không thể vừa cam kết “không mất item”, “producer không bao giờ chờ”, “RAM hữu hạn” và “consumer chậm vô hạn” mà không có thêm storage/khả năng xử lý**. Thiết kế phải chọn điểm đánh đổi hoặc đưa backlog ra tầng bền vững.

### Ví dụ timed offer

```java
boolean accepted = queue.offer(item, 250, TimeUnit.MILLISECONDS);
if (!accepted) {
    // Theo contract ứng dụng: reject, persist, ghi metric hoặc retry có giới hạn.
}
```

Đây là **đoạn code trong method** cần khai báo/xử lý `InterruptedException`, có import `java.util.concurrent.TimeUnit` và biến `queue`, `item` đã tồn tại. `250ms` chỉ là con số minh họa, không phải lời khuyên SLA cố định.

Một retry đúng cần giữ rõ **item đã được enqueue hay chưa**. Nếu producer không biết một side effect downstream đã xảy ra, retry có thể tạo bản sao logic. Tính exactly-once không được queue in-memory bảo đảm; cần idempotency key/transaction khi công việc mang tác động bên ngoài.

## 9. Chờ đợi đúng cách: đừng tự kiểm tra size rồi ngủ

Mẫu nên tránh:

```java
// Minh họa sai: polling và đoán thời gian.
while (queue.isEmpty()) {
    Thread.sleep(10);
}
Item item = queue.remove();
```

Đây là code minh họa chưa đầy đủ; `Item` và `queue` được khai báo ngoài đoạn. Vấn đề:

- `isEmpty()` chỉ là snapshot tại một thời điểm; giữa khi kiểm tra và `remove()` thread khác có thể lấy hết queue.
- `sleep` không chờ một event chính xác và có thể tạo độ trễ không cần thiết.
- Nhiều consumer polling làm tăng CPU/wakeup hoặc phải chọn trade-off giữa latency và thời gian ngủ.
- `Thread.sleep()` không tạo memory-ordering protocol cho những shared state ngoài queue.

Mẫu trực tiếp:

```java
Item item = queue.take();
process(item);
```

Đây cũng là đoạn minh họa trong method `throws InterruptedException`, với `queue` là `BlockingQueue<Item>`. `take()` thực hiện đúng việc chờ đến khi có item, lấy một item rồi trả về; không cần tự xây wait loop cho trường hợp chuẩn.

Tương tự, không nên làm:

```java
if (queue.remainingCapacity() > 0) {
    queue.add(item);
}
```

`remainingCapacity()` có thể đã thay đổi trước `add` nếu có producer khác. Nếu mục tiêu là “thử thêm nếu còn chỗ”, gọi **`offer(item)`** và kiểm tra boolean. Chỉ dùng `remainingCapacity` để quan sát/ước lượng, không để *reserve* slot.

## 10. Multiple producers và consumers: FIFO không đảm bảo completion order

Với `ArrayBlockingQueue` và `LinkedBlockingQueue`, item được lấy theo FIFO của **thứ tự enqueue thành công**. Nhưng cần tách nhiều thứ tự:

- **Thứ tự producer tạo item:** P1 có thể tạo A trước P2 tạo B.
- **Thứ tự enqueue:** P2 có thể được scheduler cho `put(B)` vào queue trước `put(A)`.
- **Thứ tự dequeue:** đối với FIFO queue, consumer lấy theo thứ tự item đã thực sự vào queue.
- **Thứ tự hoàn tất xử lý:** với nhiều consumer, C1 lấy A trước nhưng xử lý chậm; C2 lấy B sau nhưng hoàn tất trước.

```text
Queue FIFO:       A -> B -> C
Consumer C1:      take(A) ----------- done(A)
Consumer C2:           take(B) -- done(B)
Order take:       A, B
Order complete:   B, A
```

FIFO **không biến workload đa consumer thành thực thi tuần tự**. Nếu nghiệp vụ yêu cầu side effect theo thứ tự tuyệt đối, cần một owner xử lý tuần tự hoặc sequence/commit protocol phù hợp. Tăng số consumer chỉ an toàn khi các item được phép xử lý độc lập hoặc có synchronization cho invariant liên quan.

### Với nhiều producer, thứ tự dữ liệu không phải thứ tự thời gian tuyệt đối

Không nên suy rằng item từ các producer khác nhau sẽ có một global order giống timestamp do mỗi producer tự gán. Nếu cần tổng thứ tự nghiệp vụ, hãy xác định ai cấp sequence và ở giai đoạn nào (trước enqueue, tại enqueue, khi commit). Sequence có thể gắn vào message, nhưng thứ tự **completion** vẫn cần cách phối hợp khác.

### Một message có được nhiều consumer xử lý không?

Đối với một queue thông thường, một lần `take()` **loại item khỏi queue**, nên một item không được broadcast cho toàn bộ consumers chỉ vì họ cùng gọi `take()`. Đây là **work distribution**, không phải pub/sub. Nếu mỗi consumer phải nhận cùng một event, cần fan-out thành nhiều queue hoặc hệ thống pub/sub rõ ràng.

## 11. Dừng consumer an toàn: poison pill, interrupt và completion

### Poison pill

Poison pill là item đặc biệt báo consumer kết thúc vòng `take`:

```java
while (true) {
    Message message = queue.take();
    if (message instanceof Stop) break;
    handle(message);
}
```

Đây là đoạn mã minh họa; `Message` là kiểu chứa data/stop, `Stop` là một subtype, `queue` là `BlockingQueue<Message>`, `handle` là method đã định nghĩa; method phải xử lý/khai báo `InterruptedException`.

Cần bảo đảm:

1. **Stop không phải dữ liệu hợp lệ.** Dùng typed message để tránh xung đột sentinel.
2. **Stop được đặt sau các item cần xử lý.** Nếu có nhiều producer, phải biết **tất cả producer đã ngừng enqueue** trước khi đưa tín hiệu dừng cuối, nếu không dữ liệu có thể đến sau Stop.
3. **Nhiều consumer:** một Stop thường chỉ được **một** consumer lấy. Nếu có M consumers đang block tại `take()` và dùng cùng cơ chế này, thường cần M Stop items hoặc shutdown protocol khác.
4. **Queue bounded:** việc enqueue Stop cũng có thể block khi queue đầy; phải có consumer đang tiến triển để làm chỗ, hoặc timed/cancel policy thích hợp.
5. **Stop chỉ xác nhận consumer đã thấy tín hiệu**; caller muốn biết consumer **đã xử lý xong** phải chờ `Future.get()`/`join()` hay completion signal đáng tin.

**Không lấy `queue.isEmpty()` làm dấu hiệu dừng:** queue có thể tạm rỗng giữa hai lần producer tạo item, hoặc toàn bộ item đã bị consumer lấy ra nhưng chưa xử lý xong.

### Interrupt và cancellation

`put()`/`take()` có thể ném `InterruptedException`. Thread đang chờ phải có chính sách rõ:

- Khi API cho phép, **propagate** exception để caller quyết định hủy.
- Khi catch ở biên task không thể rethrow, khôi phục interrupt status bằng `Thread.currentThread().interrupt()` và thoát/dọn tài nguyên.
- Đừng catch rỗng rồi tiếp tục chờ vô hạn: shutdown có thể không hoàn tất.
- `Thread.interrupt()` không phải bảo đảm transaction rollback. Item đã được dequeue và xử lý một phần cần chính sách retry/idempotency riêng.

Ví dụ xử lý trong worker:

```java
try {
    while (running) {
        Item item = queue.take();
        process(item);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Cleanup/cancel theo contract của worker.
}
```

Đây là đoạn minh họa trong method có `running`, `Item`, `queue` và `process` ở bên ngoài. Nếu interrupt xảy ra giữa xử lý tác vụ không blocking, xử lý hủy còn cần logic khác để phát hiện và dừng, không thể chỉ trông chờ `take()`.

### Graceful shutdown so với shutdownNow

`ExecutorService.shutdown()` ngừng nhận task mới, cho task đã được submit tiếp tục theo contract; nó **không chờ tất cả task kết thúc**. Dùng `Future.get()`/`awaitTermination()` với timeout khi cần hoàn tất. `shutdownNow()` cố gắng dừng các task đang chạy (thường qua interrupt) và trả những task còn chưa chạy, **không cam kết mọi task dừng tức thì**.

Một shutdown protocol tốt cần quyết định: ngừng producer trước hay sau, xử lý backlog ra sao, gửi stop ở thời điểm nào, timeout bao lâu, item in-flight nếu thất bại được xử lý ra sao.

## 12. Một lỗi deadlock tinh vi: producer và consumer dùng cùng pool quá nhỏ

Giả sử một executor có **chỉ một worker**:

```java
// Sơ đồ lỗi, không phải code chạy đầy đủ.
ExecutorService pool = Executors.newSingleThreadExecutor();
BlockingQueue<Integer> q = new ArrayBlockingQueue<>(1);

pool.submit(() -> {
    q.put(1);
    q.put(2); // block vì queue đầy
    return null;
});
pool.submit(() -> q.take()); // task này đang xếp hàng, chưa có worker chạy
```

Đoạn trên là **minh họa thiết kế deadlock** với các imports của `java.util.concurrent`. Producer đầu tiên giữ worker duy nhất, thêm 1 rồi block ở lần `put(2)`. Task consumer nằm trong executor queue, không được chạy cho đến khi producer kết thúc; nhưng producer đang đợi consumer lấy item. Đây là vòng chờ **không thể tiến triển**.

Khắc phục tùy kiến trúc:

- Dùng các worker/nguồn thực thi riêng để consumer **có thể** chạy khi producer block.
- Không submit blocking producer và consumer phụ thuộc nhau vào executor không đủ capacity.
- Chọn nonblocking/timeout submit phù hợp, hoặc thiết kế luồng dữ liệu theo completion stages nếu đúng semantics.
- Nếu producer/consumer cùng một pipeline, bảo đảm luôn có đường thoát khi queue đầy hoặc khi một phía hỏng.

Không suy rằng “có thread pool nên chắc chắn các task sẽ chạy song song”. Kích thước pool, queue task của executor và bounded queue dữ liệu là **hai hàng đợi khác nhau**, và phụ thuộc giữa chúng có thể tạo deadlock.

## 13. Dùng Lock + hai Condition để hiểu bên trong bounded queue

Khi tự cài một bounded buffer, cần bảo vệ invariant:

```text
0 <= queue.size() <= capacity

Producer được thêm nếu:  queue.size() < capacity
Consumer được lấy nếu:   !queue.isEmpty()
```

Một `ReentrantLock` bảo vệ queue cùng hai condition:

- `notFull`: producer chờ “còn chỗ”.
- `notEmpty`: consumer chờ “có item”.

Sau `put` thành công, thông báo một consumer qua `notEmpty.signal()`. Sau `take` thành công, thông báo một producer qua `notFull.signal()`.

### Implementation educational: TinyBoundedBuffer.java

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Objects;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class TinyBoundedBuffer<E> {
    private final int capacity;
    private final Deque<E> queue = new ArrayDeque<>();
    private final ReentrantLock lock = new ReentrantLock();
    private final Condition notEmpty = lock.newCondition();
    private final Condition notFull = lock.newCondition();

    public TinyBoundedBuffer(int capacity) {
        if (capacity <= 0) throw new IllegalArgumentException("capacity must be > 0");
        this.capacity = capacity;
    }

    public void put(E element) throws InterruptedException {
        Objects.requireNonNull(element);
        lock.lockInterruptibly();
        try {
            while (queue.size() == capacity) {
                notFull.await();
            }
            queue.addLast(element);
            notEmpty.signal();
        } finally {
            lock.unlock();
        }
    }

    public E take() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            while (queue.isEmpty()) {
                notEmpty.await();
            }
            E element = queue.removeFirst();
            notFull.signal();
            return element;
        } finally {
            lock.unlock();
        }
    }
}
```

Lớp trên đã được **biên dịch thành công với `javac --release 17`**. Nó là một class Java độc lập (`TinyBoundedBuffer.java`) nhưng **không có `main`**, nên không chạy trực tiếp bằng `java TinyBoundedBuffer`. Có thể tạo một test driver khác để gọi `put/take`.

### Phân tích chi tiết

1. Constructor từ chối `capacity <= 0` vì bounded buffer này bắt buộc có ít nhất một slot.
2. `ArrayDeque` là cấu trúc **không tự thread-safe**; tất cả truy cập `queue` đều được bảo vệ bởi cùng `lock`.
3. Producer lấy lock bằng `lockInterruptibly()` để có thể hủy cả giai đoạn **đợi giành lock**.
4. `while (queue.size() == capacity) notFull.await()` kiểm tra predicate trước khi chờ; `await()` nhả lock trong khi đợi, rồi **reacquire trước khi trả về**.
5. Khi có chỗ, producer thêm item, signal nhóm consumer đợi `notEmpty`, rồi nhả lock trong `finally`.
6. Consumer tương tự: khi rỗng thì await `notEmpty`; khi có item thì xóa đầu, signal `notFull`, trả item.
7. `while` là bắt buộc vì spurious wakeup, `signalAll` từ nơi khác hoặc một thread khác có thể lấy tài nguyên trước waiter sau khi nó reacquire.
8. `signal()` không nhả lock ngay. Waiter chỉ có thể đi tiếp sau khi thread đang giữ lock thoát critical section và waiter giành lại lock.
9. Nếu `await()` bị interrupt, nó ném `InterruptedException` theo contract; `finally` vẫn release lock sau khi đã được reacquire theo semantics của ReentrantLock Condition.
10. `Objects.requireNonNull` từ chối null vì `ArrayDeque` không cho null và vì null thường được dùng làm marker “empty” ở các API queue.

**Chủ ý giới hạn:** lớp này chưa triển khai `offer`, `poll`, timeout, `size`, fairness, close/shutdown, batch operations, metrics, cancellation khi consumer thất bại hay các edge cases production. Nó chỉ diễn giải invariant và điều kiện chờ. Với phần lớn use case, dùng `ArrayBlockingQueue` chuẩn sẽ dễ bảo trì và đáng tin hơn.

### Tại sao phải có hai Condition?

Nếu producer và consumer cùng nằm trên một condition queue chung, `signal()` có thể đánh thức một waiter **không phải nhóm cần tiến triển**. Ví dụ sau take, cần đánh thức producer đang chờ queue đầy, không phải đánh thức thêm consumer rỗng. Hai condition phân tách đúng vai trò, giảm wake-up không cần thiết.

`signalAll()` có thể được dùng khi trạng thái cho nhiều waiter cùng tiến triển, hoặc khi shutdown cần đánh thức mọi nhóm để kiểm tra cờ dừng. Tuy nhiên, đánh thức tất cả khi chỉ có một slot mới thường tạo thundering herd: nhiều thread tranh lock rồi phần lớn lại chờ.

## 14. Điều gì xảy ra với Java Memory Model?

Queue là **concurrency primitive**. JavaDoc của `BlockingQueue` mô tả memory-consistency effect: các thao tác của producer trước khi đặt object vào queue *happen-before* thao tác của consumer sau khi truy cập/lấy object đó.

Điều này quan trọng khi item chứa dữ liệu được producer xây trước khi publish:

```java
// Minh họa trong method; record tạo immutable payload:
record Event(int id, String text) {}

BlockingQueue<Event> inbox = new ArrayBlockingQueue<>(10);
Event event = new Event(7, "created");
inbox.put(event);
// Thread khác lấy bằng inbox.take() rồi đọc id và text.
```

Đây là đoạn code minh họa, không có `main` và cần xử lý/khai báo `InterruptedException`. Khi consumer nhận event, nó có thể đọc đúng những giá trị đã được chuẩn bị trước enqueue theo hợp đồng publication.

Tuy nhiên:

- Queue không làm mọi field mutable của object trở thành atomic.
- Bên gửi tiếp tục mutate payload sau enqueue có thể tạo data race.
- Nếu cần bảo toàn invariant đa trường, nên dùng immutable snapshot hoặc transfer ownership; đọc một reference an toàn không có nghĩa thay đổi bên trong object graph được đồng bộ.
- Nếu producer crash ở thời điểm đang tạo nhưng **trước enqueue**, item chưa được truyền; nếu process crash khi queue còn chứa dữ liệu, queue trong RAM có thể mất toàn bộ backlog.
- Việc consumer lấy item ra không đồng nghĩa side effect đã commit thành công.

**`volatile`/`synchronized` thủ công không cần bọc quanh mỗi `put/take`** chỉ để bảo vệ cấu trúc `BlockingQueue` chuẩn; implementation đã có synchronization. Nhưng nếu consumer và producer chia sẻ **trạng thái khác ngoài queue**, trạng thái ấy vẫn cần giao thức thread safety riêng.

## 15. Failure handling: dequeue không phải “xử lý thành công”

Trong producer–consumer, cần phân biệt bốn mốc:

```text
Sản xuất item -> enqueue thành công -> dequeue thành công
                                     -> xử lý side effect -> xác nhận hoàn tất
```

`take()` chỉ xác nhận một consumer đã lấy item ra. Nếu consumer ném exception trong `process(item)`, item đã **không còn trong queue**. `BlockingQueue` thông thường không tự có cơ chế acknowledgment/requeue như một durable broker.

Ví dụ:

```java
Item item = queue.take();
process(item); // Có thể thất bại sau khi item đã bị xóa khỏi queue.
```

Đây là đoạn code minh họa. Muốn bảo đảm không mất job theo contract cần một cơ chế riêng:

- Ghi job bền vững trước khi enqueue, hoặc dùng broker với ack/redelivery phù hợp.
- Thiết kế retry queue/dead-letter xử lý lỗi với số lần thử có giới hạn.
- Dùng idempotency key cho side effect có thể chạy lại.
- Theo dõi in-flight jobs và trạng thái hoàn tất, không chỉ `size()`.
- Quy định xử lý khi consumer process chết, process JVM dừng, timeout hoặc kết quả không rõ ràng.

**Không khẳng định “exactly once” chỉ nhờ ArrayBlockingQueue.** Trong một execution bình thường, một element được một lần `take` lấy ra khỏi queue. Điều đó khác hoàn toàn với “side effect bên ngoài hệ thống chỉ xảy ra đúng một lần qua crash/retry”.

## 16. Cách tính capacity và số consumer

Không có một giá trị capacity tối ưu cho mọi chương trình. Một quy trình thực dụng:

1. **Đo tốc độ đến (arrival rate)**, số item/s ở tình huống trung bình và burst.
2. **Đo tốc độ xử lý (service rate)** của mỗi consumer, phân biệt CPU-bound và I/O-bound.
3. **Ước lượng memory cost mỗi item**, bao gồm object graph, payload và metadata.
4. **Chọn ngân sách backlog** theo dung lượng RAM và maximum queueing latency được phép.
5. **Giới hạn tổng in-flight** nếu mỗi consumer giữ item lớn hoặc side effect tốn tài nguyên.
6. **Stress với burst và downstream chậm**, đo rejection/timeout, blocked producer time, queue depth và p95/p99 end-to-end latency.
7. **Điều chỉnh consumer concurrency** theo bottleneck thực, tránh mở quá nhiều concurrent request đến downstream có quota.

Ví dụ giả định queue có capacity 500 và mỗi item giữ khoảng 20 KiB payload + object liên quan: riêng backlog có thể chiếm cỡ **10 MiB** chưa tính overhead, references, GC metadata hoặc các item đang xử lý. Đây là phép ước lượng minh họa; cần đo heap thực trên data thật trước khi chọn production capacity.

### Quan hệ tốc độ và độ trễ

Nếu backlog hiện tại xấp xỉ 200 item, consumer xử lý ổn định khoảng 50 item/s và không có item mới, thời gian để xả hết backlog lý tưởng là khoảng `200 / 50 = 4 giây`. Khi producer vẫn thêm item, số liệu thay đổi; khi processing time có phương sai lớn, p99 latency có thể cao hơn trung bình nhiều.

Little's Law (`L = λW`) có thể giúp kiểm tra tính nhất quán của số đo đối với một hệ ổn định và phạm vi đo được định nghĩa rõ, nhưng **không dùng nó như công thức độc lập để đặt capacity** trong hệ thống có burst lớn hoặc chưa ổn định.

### Backpressure có thể lan ngược đến đâu?

Nếu producer đang chạy trong request thread, `put()` block có thể làm request latency vượt SLA và timeout. Nếu producer lấy dữ liệu từ socket, việc block có thể làm buffer phía trước tăng. Nếu producer là một task trong executor, blocking có thể làm hết worker cho task quan trọng khác.

Vì vậy, chỉ **có queue bounded** chưa đủ; phải biết upstream phản ứng với việc đầy như thế nào và có backlog nào **trước queue** không.

## 17. Metrics và chẩn đoán một bounded queue

Một số tín hiệu hữu ích:

| Metric/quan sát | Diễn giải | Cẩn thận |
|---|---|---|
| `queue.size()` theo thời gian | Backlog hiện tại, xu hướng tích tụ | Chỉ là snapshot; không dùng để điều phối atomic |
| `remainingCapacity()` | Số slot trống ở thời điểm quan sát | Không phải reservation; thay đổi ngay khi producer khác enqueue |
| Thời gian `put`/timed offer | Producer bị backpressure bao lâu | Phân biệt thời gian chờ với thời gian tạo item |
| Thời gian `take`/poll | Consumer đợi vì thiếu item | Chờ queue rỗng có thể là idle bình thường |
| Accepted/rejected/timeouts | Áp lực tạo việc so với công suất | Cần biết policy drop/retry và số lần duplicate |
| In-flight count | Item đang xử lý sau dequeue | Không suy ra bằng `queue.size()` |
| Processing latency/throughput | Hiệu năng consumer và downstream | Queue full có thể do consumer chậm, không phải do lock queue |
| Error/retry/dead-letter count | Khả năng tiến triển sau lỗi | Retry vô hạn có thể tự tạo storm |

Khi JVM đang chạy, có thể thu thread dump:

```bash
jcmd <PID> Thread.print -l
```

Thay `<PID>` bằng process ID thật. Với queue chuẩn, stack có thể xuất hiện `ArrayBlockingQueue.put/take`, `ConditionObject.await`, `LockSupport.park` khi thread đợi queue đầy/rỗng. `WAITING (parking)` thường là chờ một condition, **không đủ để kết luận deadlock**.

Nếu cần đo các thời gian chờ, dùng JFR và profiler phù hợp (tùy JDK/JVM, event settings và workload). Thread dump là snapshot; việc quan sát chờ queue rỗng của một consumer nhàn rỗi có thể là hành vi hoàn toàn đúng.

## 18. Kiểm thử producer–consumer đúng cách

Một bài test tốt không chỉ hỏi “chương trình có in đúng một lần không?”. Nó phải bao phủ invariant, thứ tự và các tình huống đợi:

### Invariant cốt lõi

- `0 <= size <= capacity` trên toàn bộ các trạng thái có thể quan sát qua API queue.
- Với một producer và một consumer, item được lấy theo FIFO của queue.
- Nếu không có drop/cancel/error và tất cả producer hoàn tất, mọi item đã enqueue phải được consumer xử lý theo contract.
- Không item dữ liệu nào bị coi nhầm là poison pill.
- Khi dừng, các thread không còn bị block vô hạn ở `put/take`.
- Khi processing thất bại, hệ thống có chính sách retry/dead-letter/khai báo lỗi rõ ràng.

### Test các trạng thái ranh giới

1. **Empty queue:** consumer đợi, sau đó producer enqueue item; consumer tiếp tục.
2. **Full queue:** producer dùng `offer` nhận `false`; với `put`, producer chờ tới khi có chỗ.
3. **FIFO:** một producer enqueue A, B, C; một consumer lấy đúng A, B, C.
4. **Many producers:** tất cả item có ID được nhận chính xác theo contract; không giả định global order nếu không có sequence.
5. **Many consumers:** kiểm tra không item bị xử lý hai lần trong đường chạy thường, nếu không có retry; thứ tự completion có thể khác dequeue.
6. **Timeout:** timed offer trả `false` khi không có slot trong thời hạn; timed poll trả `null` khi chưa có item.
7. **Interrupt:** producer/consumer đang chờ có thể thoát theo cancellation policy và không giữ tài nguyên vô thời hạn.
8. **Shutdown:** không đặt STOP trước khi producer cuối hoàn tất; các consumer được thông báo dừng; pool hoàn tất hoặc hết deadline.
9. **Failure:** consumer ném exception giữa chừng; main nhận được lỗi qua `Future.get()` và kích hoạt recovery policy.
10. **Memory pressure:** payload lớn, backlog đột biến; capacity hạn chế số item queue nhưng in-flight/queues khác cũng phải đo.

### Đồng bộ test bằng primitive, không đoán bằng sleep

`CountDownLatch` hoặc `CyclicBarrier` có thể phối hợp cho test biết producer đã tới một checkpoint. Dùng `Future.get(timeout, unit)` để test fail có kiểm soát nếu không tiến triển. `Thread.sleep` có thể giúp mô phỏng xử lý chậm, nhưng **không phải công cụ bảo đảm** producer đã block hay consumer đã nhận item.

Ví dụ assertion logic cần đặt sau khi các Future hoàn tất: số item consumer xử lý bằng số item producer enqueue thành công, tổng checksum khớp, tất cả task thoát sạch.

## 19. Những lỗi thường gặp

1. **Dùng `new LinkedBlockingQueue<>()` rồi tưởng có capacity nhỏ.** Mặc định capacity là `Integer.MAX_VALUE`; cần chỉ định rõ ngưỡng khi muốn bounded.
2. **Bỏ qua `offer() == false`.** Công việc có thể bị mất lặng lẽ. Return boolean là một phần contract phải xử lý.
3. **Sử dụng `queue.size()` để quyết định chắc chắn put/take có thể thực hiện.** Race giữa check và action; dùng operation atomic do queue cung cấp.
4. **Dùng `Thread.sleep` thay `take`.** Polling tạo độ trễ, khó cancellation và không cần thiết.
5. **Coi queue empty là mọi công việc đã hoàn thành.** Consumer có thể đã dequeue nhưng vẫn đang xử lý.
6. **Chỉ đưa một poison pill cho N consumers.** N−1 consumers có thể vẫn block ở `take`.
7. **Đưa poison pill trước khi tất cả producers dừng.** Có thể còn data enqueue phía sau tín hiệu dừng, bị bỏ lại.
8. **Poison pill có thể trùng dữ liệu hợp lệ.** Dùng typed message hoặc marker được bảo đảm không trùng.
9. **Producer và consumer phụ thuộc nhau trong executor chỉ có một worker.** Producer block khi queue đầy, consumer task không bao giờ được cấp worker.
10. **Cho rằng FIFO dequeue nghĩa là FIFO completion.** Với nhiều consumer, task xử lý chậm/nhanh khác nhau.
11. **Tiếp tục sửa mutable payload sau enqueue.** Queue thread-safe không tự bảo vệ state bên trong item.
12. **Cho rằng `take` đồng nghĩa “đã xử lý/commit”.** Dequeue chỉ lấy item; side effect có thể lỗi.
13. **Nuốt `InterruptedException`.** Shutdown/hủy có thể treo vô thời hạn.
14. **Gọi `shutdownNow` và mặc định mọi task đã dừng.** ShutdownNow là nỗ lực hủy; cần quan sát kết thúc và xử lý interruption.
15. **Dùng queue không giới hạn để “đỡ mất item”.** Đổi sang nguy cơ OOM khi upstream nhanh hơn downstream.
16. **Tăng capacity mãi để chữa consumer chậm.** Capacity hấp thụ burst, không thay tốc độ xử lý bền vững.
17. **Đánh thức sai nhóm khi tự cài queue.** Producer phải đợi notFull, consumer phải đợi notEmpty; signal đúng condition.
18. **Dùng `if` thay `while` quanh `Condition.await`.** Spurious wakeup hoặc tranh chấp sau signal có thể làm predicate không còn đúng.
19. **Quên `finally { lock.unlock(); }` trong implementation tự viết.** Exception có thể giữ explicit lock mãi.
20. **Đặt side effect không idempotent trong retry không giới hạn.** Việc xử lý có thể lặp lại, cần chính sách commit/retry rõ.

## 20. Cách chọn mô hình và khi không nên tự xây queue

| Nhu cầu | Lựa chọn khởi đầu |
|---|---|
| Bounded FIFO buffer cơ bản trong JVM | `ArrayBlockingQueue<>(capacity)` |
| Bounded FIFO bằng node, capacity cấu hình rõ | `LinkedBlockingQueue<>(capacity)` |
| Không cần đệm, producer gặp consumer trực tiếp | `SynchronousQueue` |
| Một task trả kết quả cho caller, không cần queue data riêng | `Callable` + `Future` / `ExecutorService` |
| Điều phối từng giai đoạn hay chờ một sự kiện | `CountDownLatch`, `Phaser` hoặc `Condition` tùy predicate |
| Cần một state owner tuần tự nhận command | Một consumer + bounded queue, protocol shutdown/ack |
| Cần durability, replay và redelivery qua crash | Persistent broker/log hoặc transactional storage |
| Cần bảo vệ invariant nhiều field khi xử lý item | Khóa/atomic/immutable state đúng phạm vi, **ngoài** queue |

Chọn **primitive đơn giản nhất đáp ứng đúng contract**. Tự viết bounded buffer bằng `Condition` hữu ích để học, nhưng production implementation cần đáp ứng một tập lớn tình huống không có trong ví dụ: timeout, fairness, exception safety, shutdown, interrupt, batch draining và metrics.

## 21. Câu hỏi tự kiểm tra kèm đáp án

**Câu 1.** `new ArrayBlockingQueue<>(2)` đang chứa hai item. `offer(third)` làm gì?  
**Đáp án:** Trả `false` ngay khi không còn slot, không chờ. Nếu dùng `put(third)` thì producer sẽ chờ khi đầy.

**Câu 2.** `take()` được gọi khi queue rỗng, điều gì xảy ra?  
**Đáp án:** Thread chờ cho tới khi có item để lấy hoặc bị interrupt; không cần polling bằng `sleep`.

**Câu 3.** Tại sao queue bounded có thể giảm OOM nhưng không tự tăng throughput?  
**Đáp án:** Nó giới hạn số item đệm và có thể block/reject producer; tốc độ consumer/downstream không tự tăng.

**Câu 4.** `LinkedBlockingQueue<>()` không truyền capacity có phải bounded theo 100 item không?  
**Đáp án:** Không. Capacity mặc định là `Integer.MAX_VALUE`, có thể gây backlog lớn; nên chỉ định giới hạn theo tài nguyên.

**Câu 5.** Hai consumer lấy A rồi B theo FIFO, có chắc xử lý A hoàn tất trước B không?  
**Đáp án:** Không. C2 xử lý B nhanh hơn C1 xử lý A thì B có thể hoàn tất trước.

**Câu 6.** Producer đặt một `ArrayList` vào queue rồi tiếp tục thay đổi nó; consumer duyệt cùng list. BlockingQueue có bảo vệ list không?  
**Đáp án:** Không. Queue đồng bộ enqueue/dequeue và publication; payload mutable vẫn cần immutable snapshot, ownership transfer hoặc khóa riêng.

**Câu 7.** Có ba consumer đang `take()` và chỉ một poison pill, hệ thống có thể treo khi shutdown không?  
**Đáp án:** Có. Chỉ một consumer lấy Stop; các consumer khác có thể tiếp tục đợi. Cần gửi đủ tín hiệu hoặc protocol khác.

**Câu 8.** `queue.isEmpty() == true` có chứng minh mọi task đã xử lý xong không?  
**Đáp án:** Không. Item có thể đang in-flight trong consumer. Dùng `Future.get()`/completion tracking để biết kết quả.

**Câu 9.** Tại sao `remainingCapacity() > 0` không nên dùng như một thao tác “đặt chỗ”?  
**Đáp án:** Producer khác có thể enqueue giữa lúc kiểm tra và thêm. `offer` là operation quyết định thành công/thất bại tại thời điểm thực thi.

**Câu 10.** Khi tự cài queue bằng `ReentrantLock`, tại sao phải dùng `while` quanh `await`?  
**Đáp án:** Waiter có thể thức dậy giả, hoặc thread khác lấy item/slot trước khi waiter giành lại lock. Luôn kiểm tra lại predicate.

**Câu 11.** Producer trong executor một worker bị block ở `put` khi queue đầy, consumer task đang chờ trong cùng executor. Vì sao có thể deadlock?  
**Đáp án:** Producer giữ worker duy nhất; consumer cần worker để lấy item nhưng không được chạy; producer sẽ không giải phóng worker trước khi consumer tiến triển.

**Câu 12.** Có thể gọi side effect thanh toán ngay sau `take` và khẳng định không bao giờ xảy ra hai lần khi retry không?  
**Đáp án:** Không. Queue trong JVM không cung cấp exactly-once external side effects; retry/crash có thể gây lặp, cần idempotency/transaction.

**Câu 13.** `signal()` trong queue tự cài có nhả lock ngay và cho waiter chạy không?  
**Đáp án:** Không. Caller vẫn giữ lock đến `unlock`; waiter phải reacquire và kiểm tra lại predicate.

**Câu 14.** Một queue capacity 100 không có item nhưng consumer đang `WAITING (parking)`. Có chắc deadlock không?  
**Đáp án:** Không. Consumer có thể đang chờ item đúng thiết kế. Phải xem producer, predicate, stack, trạng thái shutdown và khả năng tiến triển.

**Câu 15.** Khi muốn producer không chờ quá 300ms, nên chọn API nào?  
**Đáp án:** `offer(item, 300, TimeUnit.MILLISECONDS)` và xử lý `false`/`InterruptedException` theo contract.

## 22. Tài liệu tham khảo

- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): các nhóm method và memory-consistency effects.
- [Java SE 17 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): capacity, FIFO, fairness và blocking operations.
- [Java SE 17 — LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): linked-node queue và các constructor capacity.
- [Java SE 17 — SynchronousQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html): handoff không có queue storage.
- [Java SE 17 — ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): explicit lock, unlock, interruptible acquisition.
- [Java SE 17 — Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): `await`, `signal`, `signalAll` và các predicate wait loops.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): lifecycle, shutdown và submission.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): completion và xử lý kết quả/ngoại lệ từ task.
- [JLS Java SE 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model và happens-before.

**Kết luận:** mô hình producer–consumer với bounded queue phải giải quyết đồng thời **an toàn chia sẻ dữ liệu**, **giới hạn backlog**, **tiến triển của cả hai phía** và **lifecycle của công việc**. Hãy bắt đầu bằng `ArrayBlockingQueue` hoặc `LinkedBlockingQueue` có capacity rõ ràng, dùng `put/take` hoặc timed `offer/poll` theo contract, xử lý interruption và shutdown dứt điểm, không coi queue rỗng là xử lý xong và không nhầm enqueue/dequeue với một transaction bền vững.