# Java 7 — Hàng đợi đồng thời: Chuyển giao dữ liệu giữa bên tạo và bên nhận

## 1. Mục tiêu: chuyển giao công việc an toàn giữa các luồng

Trong mô hình *producer–consumer*, **producer** tạo dữ liệu/công việc và **consumer** nhận để xử lý. Hai bên không nhất thiết chạy cùng tốc độ, cùng thời điểm hoặc cùng thread. Nếu trao đổi qua một `ArrayList`/`LinkedList` thông thường mà không đồng bộ, có thể xảy ra data race, mất phần tử, lỗi trạng thái bộ nhớ hoặc consumer không nhìn thấy dữ liệu vừa được tạo.

Java cung cấp các **concurrent queues** trong `java.util.concurrent`. Với producer–consumer cần đợi khi không có phần tử, API quan trọng là `BlockingQueue<E>`:

- Producer gửi: `put(e)`, `offer(e)` hoặc `offer(e, timeout, unit)`.
- Consumer nhận: `take()`, `poll()` hoặc `poll(timeout, unit)`.
- Hàng đợi tự đồng bộ thao tác thêm/lấy. Producer/consumer **không phải tự viết synchronized** để bảo vệ từng lần `put/take`.
- Một phần tử được consumer lấy ra khỏi queue không còn nằm trong queue đó; nhiều consumers cạnh tranh để lấy các công việc khác nhau.
- Bounded queues cung cấp **backpressure**: khi đầy, producer phải đợi, từ chối hoặc áp dụng chính sách mất dữ liệu do ứng dụng chọn.
- Queue **không tự đóng khi producer kết thúc**; cần giao thức shutdown như poison pill, signal bên ngoài, timeout/cancellation và quản lý worker lifecycle.

Bài học tập trung vào **chuyển giao dữ liệu giữa bên tạo và bên nhận**, không biến thành hướng dẫn tổng quát cho mọi collection. Những API chính (`BlockingQueue`, `ArrayBlockingQueue`, `SynchronousQueue`, `LinkedTransferQueue`) đều **còn áp dụng với Java SE 17+**. Ví dụ được thiết kế để có kết quả ổn định và đã kiểm tra trên JDK hiện đại.

### 1.1. Mô hình

```text
Producer thread(s)                      Consumer thread(s)
  ┌─────────────────┐                    ┌──────────────────┐
  │ tạo Work(id,...)│                    │ nhận từng Work   │
  └────────┬────────┘                    └────────▲─────────┘
           │                                      │
           │ put / offer                          │ take / poll
           ▼                                      │
  ┌─────────────────────────────────────────────────────────┐
  │               BlockingQueue<Work>                       │
  │        [work-101] [work-102] [work-103]                  │
  │          capacity hữu hạn (nếu bounded)                  │
  └─────────────────────────────────────────────────────────┘
           │                                      │
       queue đầy                            queue rỗng
           │                                      │
    put có thể đợi                       take có thể đợi

Handoff trực tiếp: SynchronousQueue không lưu phần tử;
producer và consumer phải gặp nhau ở cùng một lần giao nhận.
```

**Không nhầm:** *enqueue thành công* chỉ nghĩa là queue nhận phần tử theo hợp đồng; nó **không** xác nhận consumer đã xử lý nghiệp vụ, cập nhật database thành công hay lưu dữ liệu bền vững.

## 2. Những thuật ngữ và bất biến cốt lõi

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Producer | Luồng/tác vụ tạo message/job rồi đưa vào queue |
| Consumer | Luồng/tác vụ lấy message/job khỏi queue và xử lý |
| Enqueue | Đưa phần tử vào queue |
| Dequeue | Lấy và loại phần tử khỏi queue |
| Bounded capacity | Giới hạn số phần tử tối đa được đệm đồng thời |
| Backpressure | Điều chỉnh/chặn producer khi consumer không theo kịp |
| Handoff | Giao phần tử từ producer tới consumer, có thể qua queue hoặc trực tiếp |
| Sentinel/poison pill | Message đặc biệt báo không còn việc và yêu cầu consumer dừng |
| Shutdown protocol | Quy tắc dừng nhận thêm việc, drain, gửi tín hiệu và kết thúc workers |
| Happens-before | Quan hệ về memory visibility giữa thao tác của các threads |
| At-least-once/exactly-once | Thuộc ngữ nghĩa nghiệp vụ giao nhận, **không** tự sinh ra chỉ từ in-memory queue |

**Một concurrent queue thread-safe không tự làm cho mọi object đặt trong queue trở thành immutable hoặc thread-safe.** Đặt phần tử vào queue thiết lập việc công bố dữ liệu trước đó; nhưng nếu producer tiếp tục sửa cùng object mà consumer đang đọc, vẫn có thể xảy ra race.

### 2.1. Một queue có thể có nhiều producer và consumer

`BlockingQueue` hỗ trợ nhiều producer và consumer đồng thời. Queue tự quản lý thao tác thêm/lấy ở mức thread-safe. Với các queue FIFO thông thường, mỗi phần tử lấy ra theo thứ tự queue, nhưng **không đảm bảo** hai producers đang chạy đồng thời có một thứ tự tổng thể theo “thời gian bắt đầu tạo job” mà code ứng dụng tự hình dung.

Nếu cần định tuyến công việc đến một consumer cụ thể, thứ tự toàn cục theo sequence number hoặc xử lý đúng một lần ở tầng business, cần thiết kế thêm. Queue chỉ là cơ chế chuyển giao trong tiến trình.

## 3. API BlockingQueue: bốn chế độ khi chưa thể thêm/lấy ngay

Các phương thức quan trọng của `BlockingQueue<E>`:

| Hành động | Ném ngoại lệ khi không làm được ngay | Trả giá trị đặc biệt | Chờ vô hạn (nếu không bị ngắt) | Chờ có thời hạn |
| --- | --- | --- | --- | --- |
| Thêm | `add(e)` | `offer(e)` → `false` | `put(e)` | `offer(e, timeout, unit)` |
| Lấy | `remove()` | `poll()` → `null` | `take()` | `poll(timeout, unit)` → `null` |
| Chỉ xem phần tử đầu | `element()` | `peek()` → `null` | Không có | Không có |

Đây là bảng **hợp đồng phương thức**; biểu hiện “đầy” có ý nghĩa khi queue bị giới hạn capacity. Với queue không giới hạn nội tại, `put` có thể thêm ngay cả khi consumer chậm, khiến **bộ nhớ tăng**.

### 3.1. put(e): producer chờ cho đến khi có chỗ

```java
BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);
queue.put("job-A");
queue.put("job-B");
// queue.put("job-C") sẽ đợi nếu chưa có consumer lấy ra phần tử.
```

Đây là snippet **trong phương thức**, cần imports concurrent và xử lý `InterruptedException`. Nó minh họa queue có capacity 2. Đừng chạy thêm `put("job-C")` trong một chương trình chỉ có một thread và không có consumer, vì sẽ **chờ vô hạn**.

**Không nên dùng put vô điều kiện trên thread xử lý request HTTP/UI** nếu bạn cần deadline. Producer sẽ bị block khi queue đầy; có thể làm toàn bộ request chain chậm hoặc dẫn đến thread starvation.

### 3.2. offer(e): không chờ

```java
boolean accepted = queue.offer("job-C");
if (!accepted) {
    // Queue đang đầy hoặc không thể nhận ngay;
    // ứng dụng quyết định retry/drop/reject.
}
```

Đây là snippet trong phương thức với queue đã khởi tạo. `offer` trả `false` nếu không thể thêm ngay, nhưng **không có nghĩa message đã được lưu để retry tự động**. Nếu app bỏ qua `false` thì đã chủ động làm mất message.

### 3.3. offer(e,timeout,unit): đợi tối đa theo deadline

```java
boolean accepted = queue.offer(
        "job-D", 200, TimeUnit.MILLISECONDS);
if (!accepted) {
    // Hết thời gian chờ vẫn chưa thêm được; xử lý quá tải.
}
```

Đây là snippet trong phương thức; lời gọi có thể ném `InterruptedException`. Có giới hạn chờ giúp producer tránh bị treo vô hạn, nhưng chọn timeout phù hợp SLA và cân nhắc cancellation.

### 3.4. take(): consumer đợi phần tử

```java
String job = queue.take();
process(job);
```

Đây là snippet minh họa: `process` là hàm nghiệp vụ, cần xử lý checked `InterruptedException`. Nếu queue rỗng, `take` đợi cho tới khi có phần tử hoặc thread bị ngắt. Nó **không** trả `null` để báo “producer đã kết thúc”.

### 3.5. poll(timeout): consumer chờ nhưng có cơ hội kiểm tra trạng thái dừng

```java
String job = queue.poll(500, TimeUnit.MILLISECONDS);
if (job == null) {
    // Chưa có phần tử trước deadline; kiểm tra shutdown/cancellation.
} else {
    process(job);
}
```

Đây là snippet trong phương thức. `null` chỉ biểu thị **không có phần tử trước timeout**, không có nghĩa queue đã đóng hay sẽ không có việc trong tương lai.

### 3.6. null không phải poison pill

Theo `BlockingQueue`, **không chấp nhận `null` elements**: `put(null)` hoặc `offer(null)` ném `NullPointerException`. Lý do quan trọng: `poll()` sử dụng `null` để báo queue rỗng. Nếu muốn end-of-stream, tạo một message sentinel **không null** hoặc dùng trạng thái shutdown bên ngoài.

## 4. Bốn lựa chọn chuyển giao thường gặp

| Cấu trúc | Có bộ đệm? | Có thể chờ khi enqueue? | Dùng khi |
| --- | --- | --- | --- |
| `ArrayBlockingQueue<E>` | **Có giới hạn cố định**, FIFO | `put` chờ khi đầy | Cần backpressure rõ, biết capacity |
| `LinkedBlockingQueue<E>` | Có thể cấp capacity; constructor không tham số có capacity rất lớn | `put` chờ nếu đạt bound | Muốn FIFO và cấu hình dung lượng, tránh quên bound |
| `SynchronousQueue<E>` | **Không có dung lượng**, ngay cả một phần tử | `put` đợi consumer nhận | Bàn giao trực tiếp, rendezvous |
| `LinkedTransferQueue<E>` | Không giới hạn nội tại, FIFO với mỗi producer | `transfer` đợi consumer nhận, còn `put` không chờ do đầy | Cần cả enqueue thường và chuyển giao chờ xác nhận *đã được nhận* |
| `ConcurrentLinkedQueue<E>` | Không giới hạn nội tại, nonblocking API | Không có `take/put` | Polling/event loops được điều phối phù hợp, không muốn consumer block ở `take` |

Đây là so sánh các kiểu **còn dùng được trên Java 17+**. Không đánh đồng “lock-free” với “luôn nhanh hơn”; hiệu quả thực tế phụ thuộc workload, contention, wakeup và memory.

### 4.1. Chọn bounded hay unbounded?

**Bounded queue** giúp giới hạn số *message objects* đang đợi trong queue. Khi producer nhanh hơn consumer trong thời gian dài, bounded queue buộc phải áp một chính sách: block, timed wait, reject, shed load hoặc scale. Nó không tự giới hạn tổng memory của tất cả stages: payload bên trong message có thể lớn, và có thể còn các messages đang được consumer xử lý ngoài queue.

**Unbounded queue** có thể có throughput tốt khi có burst ngắn, nhưng nếu rate producer lớn hơn rate consumer liên tục, backlog/memory vẫn tăng. Dung lượng báo `Integer.MAX_VALUE` về mặt API **không** là cam kết JVM có đủ RAM cho từng phần tử.

## 5. Chương trình Java 17+ hoàn chỉnh: bounded producer–consumer

Ví dụ có:

- Một `ArrayBlockingQueue<Integer>` **capacity 2**.
- Một producer gửi lần lượt các số 1 đến 5 rồi gửi **sentinel -1**.
- Một consumer liên tục `take()` tới khi gặp sentinel; kết quả được lưu **trong thread consumer**.
- Một `ExecutorService` 2 threads để producer có thể tiếp tục khi consumer lấy phần tử, tránh việc người tạo đang đợi queue đầy mà không có consumer.
- Main thread đợi hai `Future` với deadline rồi in kết quả, nên thứ tự stdout **xác định**, không tùy scheduler.

**Tệp: `BoundedHandoffDemo.java`**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class BoundedHandoffDemo {
    private static final int END = -1;

    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(2);
        ExecutorService executor = Executors.newFixedThreadPool(2);

        Future<Integer> producer = executor.submit(() -> {
            for (int i = 1; i <= 5; i++) queue.put(i);
            queue.put(END);
            return 5;
        });

        Future<List<Integer>> consumer = executor.submit(() -> {
            List<Integer> received = new ArrayList<>();
            while (true) {
                int item = queue.take();
                if (item == END) return received;
                received.add(item);
            }
        });

        try {
            int produced = producer.get(5, TimeUnit.SECONDS);
            List<Integer> received = consumer.get(5, TimeUnit.SECONDS);
            int sum = received.stream().mapToInt(Integer::intValue).sum();
            System.out.println("produced = " + produced);
            System.out.println("received = " + received);
            System.out.println("sum = " + sum);
            System.out.println("queue empty = " + queue.isEmpty());
            System.out.println("capacity = 2");
        } finally {
            producer.cancel(true);
            consumer.cancel(true);
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 BoundedHandoffDemo.java
java BoundedHandoffDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24, tương thích Java 17+:**

```text
produced = 5
received = [1, 2, 3, 4, 5]
sum = 15
queue empty = true
capacity = 2
```

### 5.1. Điều gì thật sự xảy ra ở hàng đợi?

- Capacity=2 nghĩa tại một thời điểm queue **không đệm quá 2 elements**.
- Producer có thể gọi `put(3)` khi queue đang đầy và phải đợi consumer nhận một phần tử.
- Consumer `take()` lần lượt lấy dữ liệu theo FIFO của `ArrayBlockingQueue`.
- Sentinel là **một element cuối** producer đặt vào, nên consumer nhìn thấy nó sau các số trước đó trong cùng queue.
- Consumer dừng ở sentinel và trả `List<Integer>`, producer trả số lượng đã tạo.
- Main chỉ in sau `Future.get(timeout)` của hai nhiệm vụ, không cần dựa vào `Thread.sleep()` hoặc thứ tự các dòng log từ hai threads.

### 5.2. Tại sao sentinel -1 chỉ phù hợp bài demo?

-1 là giá trị **được dành riêng** không thể trùng dữ liệu hợp lệ 1–5. Nếu ứng dụng xử lý số âm bình thường, -1 có thể là dữ liệu thực và consumer sẽ dừng nhầm. Production nên dùng **message envelope** phân biệt `DATA`, `END`, `ERROR` hoặc type-safe sealed hierarchy/record; đừng dựa vào “giá trị hiếm gặp”.

### 5.3. Cái gì được đảm bảo và cái gì không?

Đảm bảo theo API: thread-safe queue operations, FIFO của một ArrayBlockingQueue, `Future.get` nhận kết quả hoàn thành, có memory consistency. Không đảm bảo producer và consumer chạy trên hai thread **cùng lúc tại mọi thời điểm**, thời gian chờ cụ thể, hay message được xử lý thành công ở DB.

### 5.4. Tại sao không gọi get() trong cùng pool có một worker?

Nếu chỉ dùng một thread executor, producer có thể block khi queue đủ 2 phần tử; consumer đang ở queue executor chưa có thread để chạy, dễ **thread starvation/deadlock**. Bài demo dùng 2 workers. Với N consumers đang đợi queue, phải đánh giá thread capacity và dependencies, không chỉ đếm producer threads.

## 6. Backpressure: khi bên tạo nhanh hơn bên nhận

Giả sử:

```text
Producer: 1000 jobs/giây
Consumer: 300 jobs/giây

Tốc độ backlog tăng ≈ 700 jobs/giây nếu không có chính sách giới hạn.
Sau 60 giây ≈ 42.000 jobs chưa được xử lý (giả sử rate ổn định).
```

Đây là **ví dụ tính toán giả định**, không phải benchmark Java. Unbounded queue giữ backlog tăng cho tới khi tải thay đổi hoặc memory cạn. Bounded queue đạt capacity rồi buộc producer đối mặt với việc quá tải.

### 6.1. Những lựa chọn chính sách khi queue đầy

1. **Đợi đến khi có chỗ** với `put(e)` — phù hợp batch workers khi chấp nhận chặn producer; cần chính sách interrupt/shutdown.
2. **Đợi có hạn** với `offer(e,t,unit)` — cân bằng độ trễ và cơ hội nhận job.
3. **Từ chối ngay** với `offer(e)` trả false — trả HTTP 429/503 hoặc business error tùy API; không im lặng bỏ dữ liệu.
4. **Drop/shed load** khi dữ liệu có thể mất, ví dụ telemetry sampling — phải có policy có thể quan sát, không áp cho financial transactions không được phép mất.
5. **Retry có kiểm soát** theo deadline và jitter/backoff — không tạo vòng retry dồn dập làm overload nặng thêm.
6. **Scale consumers hoặc giảm upstream rate** — chỉ hiệu quả nếu bottleneck thật sự có thể scale.

Không có một queue tự cung cấp tất cả những chiến lược này. **Queue là primitive**, chính sách là lựa chọn của ứng dụng.

### 6.2. Đừng xem isFull rồi put như một transaction

```java
if (queue.remainingCapacity() > 0) {
    queue.put(item);
}
```

Đây là **anti-pattern nếu code cần bảo đảm không block**. Giữa lúc kiểm tra và lúc `put`, thread khác có thể thêm phần tử vào chỗ trống, khiến `put` vẫn block. Muốn thử thêm ngay, dùng trực tiếp `offer(item)`; muốn timed wait, dùng `offer(item, timeout, unit)`.

### 6.3. Queue capacity khác tổng lượng memory

Một queue chứa 100 messages, nhưng mỗi message giữ mảng lớn hoặc reference tới object graph khổng lồ, thì usage có thể rất cao. Dung lượng **số element** không phải memory budget theo bytes. Với payload biến đổi lớn, cần quản lý kích thước bytes hoặc leases/quotas bổ sung.

## 7. Happens-before: tại sao consumer nhìn thấy dữ liệu producer chuẩn bị?

Javadoc Java SE 17 `BlockingQueue` mô tả **memory consistency effects**:

> Các hành động của một thread trước khi đặt object vào queue *happen-before* các hành động của thread khác sau khi truy cập/lấy object đó khỏi queue.

Ý nghĩa:

1. Producer tạo message.
2. Producer điền nội dung trước khi gọi `put/offer` thành công.
3. Consumer `take/poll` lấy message.
4. Những writes của producer **trước khi publish** được nhìn thấy trong consumer theo quan hệ happens-before.

```text
Producer thread                         Consumer thread
  Message m = new Message();
  m.payload = "ready";
  queue.put(m); ------------happens-before------> Message x = queue.take();
                                                 read x.payload -> "ready"
```

Đây là sơ đồ khái niệm; không phải một đoạn Java class độc lập.

### 7.1. Concurrent queue không đóng băng object

Sai:

```java
Message m = new Message();
m.payload = "ready";
queue.put(m);
m.payload = "changed"; // Consumer có thể đang đọc cùng object!
```

Nếu producer sửa `m` **sau khi enqueue** trong lúc consumer đọc, có race nếu không thêm đồng bộ. Happens-before cho các writes **trước khi đưa vào queue** không hợp pháp hóa mọi writes sau đó.

### 7.2. Nên chuyển quyền sở hữu hoặc dùng immutable message

Dùng record Java 17+:

```java
record Work(int id, String payload) {}
Work work = new Work(7, "ready");
queue.put(work);
```

Đây là snippet trong phương thức có `BlockingQueue<Work> queue` hợp lệ. Record cung cấp fields final cho components, nên phù hợp message nhỏ immutable; nếu record chứa `byte[]` mutable, bản thân mảng vẫn có thể bị sửa — cần defensive copy/ownership.

**Ownership principle:** Producer hoàn tất việc dựng message và không sửa nó sau enqueue; consumer sở hữu xử lý và chịu trách nhiệm công bố result cho hệ thống tiếp theo. Nếu hai bên cùng dùng mutable buffer, phải có protocol để chuyển quyền hoặc synchronization.

### 7.3. Queue bảo đảm visibility nhưng không bảo đảm processing success

Nếu consumer lấy message thành công rồi ném exception trước khi commit DB, queue **không tự đưa message trở lại**. Với in-memory handoff, thường là semantics *dequeue-on-receive*, không có built-in ACK/retry/durable delivery. Nếu hệ thống cần khôi phục sau crash, đòi hỏi message broker/durable queue hoặc write-ahead log/transactional outbox ở tầng kiến trúc phù hợp.

## 8. ArrayBlockingQueue và LinkedBlockingQueue: hai lựa chọn FIFO thường dùng

### 8.1. ArrayBlockingQueue

```java
BlockingQueue<Work> queue = new ArrayBlockingQueue<>(256);
```

Đây là snippet trong phương thức với record/class `Work` của ứng dụng. Queue này có **capacity cố định**, thường sử dụng mảng và FIFO. Khi đầy, `put` block, `offer` trả false hoặc timed offer có thể timeout. Constructor `new ArrayBlockingQueue<>(capacity, true)` cho phép cấu hình **fairness** khi threads chờ.

Fairness=true có thể giảm starvation của các producers/consumers đang đợi nhưng thường có chi phí throughput; nó **không** đảm bảo thứ tự xử lý business jobs hoặc thứ tự hoàn thành.

### 8.2. LinkedBlockingQueue

```java
BlockingQueue<Work> queue = new LinkedBlockingQueue<>(256);
```

Đây là snippet trong phương thức với `Work` đã khai báo. Nó cũng FIFO và **giới hạn 256** theo cấu hình, nhưng backed by linked nodes nên memory/throughput tradeoff có thể khác ArrayBlockingQueue.

**Cảnh báo:** `new LinkedBlockingQueue<>()` không truyền capacity có giới hạn mặc định rất lớn (`Integer.MAX_VALUE`). Nó không phải một bounded queue thực tế theo mục tiêu bảo vệ RAM. Chọn capacity tường minh khi cần backpressure.

### 8.3. Cách chọn

Dùng `ArrayBlockingQueue` khi muốn giới hạn fixed và cấu trúc đơn giản. Dùng `LinkedBlockingQueue` có capacity khi việc cấp phát nodes/throughput phù hợp workload. Không kết luận một loại luôn nhanh hơn. Thử với payload size, số producers/consumers, contention, CPU/cache, thời gian xử lý và GC của hệ thống.

## 9. SynchronousQueue: chuyển giao trực tiếp, không có bộ đệm

`SynchronousQueue<E>` **không có internal capacity**, thậm chí không chứa nổi một phần tử để chờ. Nó là một **rendezvous/handoff point**: thao tác thêm phải **gặp** thao tác lấy của một thread khác.

- `put(e)` đợi đến khi consumer thực sự nhận element.
- `take()` đợi đến khi producer đưa element.
- `offer(e)` trả false nếu tại thời điểm đó không có consumer đang đợi nhận.
- `offer(e,t,unit)` có thể chờ tới deadline để tìm consumer.
- `size() == 0`, `remainingCapacity() == 0`, `isEmpty() == true` theo API; không có queue backlog để duyệt.
- Constructor `new SynchronousQueue<>(true)` có chính sách fairness FIFO cho những producers/consumers đang đợi; không bảo đảm ordering xử lý nghiệp vụ.

### 9.1. Khi nào phù hợp?

Khi không muốn đệm công việc ở giữa và producer **chỉ tiếp tục khi đã giao phần tử cho consumer**, ví dụ điều phối request tới worker sẵn sàng. Đây là mức **backpressure trực tiếp**: không có receiver thì không có chỗ đặt message.

Không nhầm nó với queue capacity=1. Một `ArrayBlockingQueue<>(1)` có thể giữ một phần tử dù chưa có consumer; `SynchronousQueue` thì không.

### 9.2. Chương trình Java 17+ hoàn chỉnh: handoff trực tiếp

**Tệp: `SynchronousHandoffDemo.java`**

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.TimeUnit;

public class SynchronousHandoffDemo {
    public static void main(String[] args) throws Exception {
        SynchronousQueue<String> queue = new SynchronousQueue<>();
        boolean beforeConsumer = queue.offer("before");

        ExecutorService executor = Executors.newSingleThreadExecutor();
        Future<String> consumer = executor.submit(() -> queue.take());
        try {
            boolean sent = queue.offer("ping", 5, TimeUnit.SECONDS);
            if (!sent) throw new IllegalStateException("No consumer");
            String received = consumer.get(5, TimeUnit.SECONDS);
            System.out.println("offer without consumer = " + beforeConsumer);
            System.out.println("handoff sent = " + sent);
            System.out.println("consumer received = " + received);
            System.out.println("queue size = " + queue.size());
            System.out.println("remaining capacity = " + queue.remainingCapacity());
        } finally {
            consumer.cancel(true);
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Chạy:

```bash
javac --release 17 SynchronousHandoffDemo.java
java SynchronousHandoffDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
offer without consumer = false
handoff sent = true
consumer received = ping
queue size = 0
remaining capacity = 0
```

**Giải thích:**

1. Khi `offer("before")` được gọi, chưa có consumer đang đợi, nên trả **false** và không lưu message.
2. Consumer được submit vào executor; `take()` có thể đợi producer.
3. `offer("ping",5,SECONDS)` chờ tối đa 5 giây để giao được message; khi có consumer, trả true.
4. Sau handoff, consumer nhận `ping`; `Future.get` đưa kết quả về main.
5. `size()` và `remainingCapacity()` đều bằng 0 theo định nghĩa SynchronousQueue — **không** có bộ đệm.

Nếu môi trường quá tải và consumer không được chạy trước deadline, timed offer có thể trả false và demo ném lỗi; đây là timeout có chủ đích, không phải lời hứa mọi máy luôn giao trong 5 giây.

### 9.3. Handoff không phải acknowledgment nghiệp vụ

`offer(...) == true` với SynchronousQueue xác nhận message được **chuyển cho consumer**, không có nghĩa consumer đã chạy xong logic hoặc commit dữ liệu. Nếu cần chờ xử lý thành công, dùng thêm Future/CompletionStage/ACK có semantics rõ ràng.

## 10. TransferQueue và LinkedTransferQueue: chờ consumer nhận nhưng cũng cho phép đệm

`TransferQueue<E>` mở rộng `BlockingQueue<E>` với khả năng **đợi cho đến khi một consumer thực sự nhận phần tử**. Java 17 có `LinkedTransferQueue<E>`, một hàng đợi liên kết **không giới hạn capacity nội tại**.

Phân biệt các lời gọi:

| Phương thức | Ý nghĩa |
| --- | --- |
| `put(e)` trên LinkedTransferQueue | Thêm vào queue; **không chờ vì đầy** vì queue unbounded |
| `offer(e)` | Thêm ngay, thường trả true trên LinkedTransferQueue |
| `transfer(e)` | Giao cho consumer, **đợi** nếu chưa có consumer nhận |
| `tryTransfer(e)` | Chỉ giao nếu **ngay lúc đó** có consumer đang đợi, nếu không trả false **và không enqueue** |
| `tryTransfer(e,t,unit)` | Đợi consumer nhận tới deadline; timeout trả false và phần tử không còn nằm trong queue |
| `take()` | Consumer đợi để nhận một element |
| `hasWaitingConsumer()` | Hint có consumer đang đợi; **không phải reservation atomic** |

### 10.1. transfer khác put

`queue.put(job)` nghĩa job đã được **enqueue**, không nghĩa consumer đã take.

`queue.transfer(job)` chờ đến khi job được **consumer nhận**, không nghĩa consumer đã xử lý xong. Nếu chưa có consumer waiting, operation có thể enqueue phần tử rồi đợi tới khi phần tử đó được nhận.

### 10.2. tryTransfer không tự lưu khi không có receiver

`queue.tryTransfer(job)` sẽ trả false nếu không có waiting consumer và **không để job trong queue**. Đây là điểm khác với `offer(job)` trên LinkedTransferQueue vốn enqueue.

### 10.3. Chương trình Java 17+ hoàn chỉnh: ba kiểu giao nhận

**Tệp: `TransferQueueDemo.java`**

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedTransferQueue;
import java.util.concurrent.TimeUnit;

public class TransferQueueDemo {
    public static void main(String[] args) throws Exception {
        LinkedTransferQueue<String> queue = new LinkedTransferQueue<>();

        boolean immediate = queue.tryTransfer("orphan");
        boolean emptyAfterFailed = queue.isEmpty();

        queue.put("buffered");
        String buffered = queue.take();

        ExecutorService executor = Executors.newSingleThreadExecutor();
        Future<String> consumer = executor.submit(() -> queue.take());
        try {
            boolean transferred =
                    queue.tryTransfer("direct", 5, TimeUnit.SECONDS);
            String received = consumer.get(5, TimeUnit.SECONDS);
            System.out.println("tryTransfer without taker = " + immediate);
            System.out.println("empty after failed transfer = " + emptyAfterFailed);
            System.out.println("buffered item = " + buffered);
            System.out.println("timed transfer succeeded = " + transferred);
            System.out.println("directly received = " + received);
            System.out.println("queue empty = " + queue.isEmpty());
        } finally {
            consumer.cancel(true);
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 TransferQueueDemo.java
java TransferQueueDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
tryTransfer without taker = false
empty after failed transfer = true
buffered item = buffered
timed transfer succeeded = true
directly received = direct
queue empty = true
```

**Điểm đáng chú ý:** `tryTransfer("orphan")` thất bại khi chưa có consumer, và queue **vẫn rỗng**. `put("buffered")` thêm vào queue mà không chờ consumer. Timed `tryTransfer("direct",...)` thành công khi có thread khác nhận qua `take()`.

### 10.4. Timeout của transfer không phải rollback business work

Timed `tryTransfer` trả false khi chưa giao được trước deadline; theo API phần tử **không còn được enqueue** khi timeout. Nhưng một producer/consumer ở tầng application vẫn cần xử lý race, logging và retry policy có ID, bởi chuyển giao thành công cũng không nói rằng consumer đã hoàn thành business work.

### 10.5. Không dùng LinkedTransferQueue như bounded backpressure chỉ vì có transfer()

`LinkedTransferQueue.put(e)` không chờ vì capacity (queue unbounded). Nếu code thường xuyên dùng `put/offer` thay vì `transfer`, backlog vẫn có thể tăng rất lớn. Muốn bảo vệ memory, chọn bounded queue hoặc quota/semaphore riêng; `transfer()` chỉ ràng buộc từng thao tác đến lúc **được nhận**.

## 11. ConcurrentLinkedQueue: không có take() để đợi

`ConcurrentLinkedQueue<E>` là concurrent queue không block ở API enqueue/dequeue thông thường. Nó có:

- `offer(e)`: thêm phần tử.
- `poll()`: lấy phần tử, hoặc null nếu rỗng.
- `peek()`: xem phần tử đầu, hoặc null nếu rỗng.

Nó **không implements BlockingQueue**, nên **không có `take()`, `put()` hoặc `poll(timeout,unit)`**. Nếu consumer phải chờ không tốn CPU, hãy dùng BlockingQueue hoặc một tín hiệu/wakeup mechanism phù hợp; đừng busy-loop `while(queue.poll()==null){}`.

### 11.1. Khi ConcurrentLinkedQueue phù hợp

Dùng khi application có event loop/notification mechanism riêng hoặc cần nonblocking handoff trong một kiến trúc được điều phối rõ. Nhưng nó **không tự cung cấp backpressure** và có thể tăng memory nếu producer vượt consumer trong thời gian dài.

### 11.2. Không dùng size() như cơ chế đồng bộ

Với linked concurrent queues, `size()` có thể cần duyệt nhiều nodes, chậm hoặc không phản ánh một snapshot atomic khi đồng thời enqueue/dequeue. Không dùng size() để quyết định chính xác “còn bao nhiêu jobs trong flight” hoặc làm một admission check không có race. Đo backlog qua metrics riêng, capacity/permits và futures khi cần.

## 12. Nhiều consumers: dừng từng người một bằng poison pill

Với **một consumer**, một sentinel ở cuối stream đủ để consumer nhận tín hiệu dừng trong ví dụ. Nhưng nếu có **ba consumer threads đang `take()`**, một sentinel thường chỉ đánh thức **một** consumer; hai consumer còn lại có thể đợi mãi.

Nếu có C consumers và muốn từng worker dừng từ queue, một mẫu phổ biến là đặt **C poison-pill messages** sau khi tất cả producers đã hoàn thành enqueue dữ liệu. Mỗi consumer lấy một pill rồi thoát.

### 12.1. Giao thức đúng trong một producer, nhiều consumers

```text
Producer: DATA1 DATA2 ... DATA9 END END END
          |      |              |   |   |
          v      v              v   v   v
      ArrayBlockingQueue capacity=4
             |
        3 consumers
             |
        mỗi consumer take đến khi END
             |
     tập hợp Future results từ cả 3
```

Pills **được enqueue sau tất cả data**, nên trong một FIFO queue, không có consumer nào nhận pill trước khi tất cả messages trước pill **đã được dequeue**. Nhưng khi pill được take, một consumer khác vẫn có thể đang **xử lý** data đã lấy: phải đợi **tất cả consumer Futures** hoàn tất để chắc tất cả đã xử lý xong.

### 12.2. Chương trình Java 17+ hoàn chỉnh: ba consumer và ba poison pills

Chương trình dùng `record Work(int id, boolean stop)` (Java 17 chuẩn) để tránh nhầm giá trị nghiệp vụ hợp lệ với sentinel. Có ba consumer threads và một producer, queue capacity 4. Kết quả mỗi consumer có thể chia job không giống nhau theo lịch chạy, nhưng tổng count và tổng IDs xác định.

**Tệp: `MultiConsumerStopDemo.java`**

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class MultiConsumerStopDemo {
    private record Work(int id, boolean stop) {}
    private static final Work END = new Work(0, true);
    private static final int CONSUMERS = 3;

    public static void main(String[] args) throws Exception {
        BlockingQueue<Work> queue = new ArrayBlockingQueue<>(4);
        ExecutorService executor = Executors.newFixedThreadPool(CONSUMERS + 1);
        List<Future<int[]>> consumerFutures = new ArrayList<>();

        for (int i = 0; i < CONSUMERS; i++) {
            consumerFutures.add(executor.submit(() -> {
                int count = 0, sum = 0;
                while (true) {
                    Work work = queue.take();
                    if (work.stop()) return new int[] { count, sum };
                    count++;
                    sum += work.id();
                }
            }));
        }

        Future<?> producer = executor.submit(() -> {
            for (int id = 1; id <= 9; id++)
                queue.put(new Work(id, false));
            for (int i = 0; i < CONSUMERS; i++) queue.put(END);
            return null;
        });

        try {
            producer.get(5, TimeUnit.SECONDS);
            int count = 0, sum = 0;
            for (Future<int[]> f : consumerFutures) {
                int[] value = f.get(5, TimeUnit.SECONDS);
                count += value[0];
                sum += value[1];
            }
            System.out.println("total handled = " + count);
            System.out.println("sum of ids = " + sum);
            System.out.println("consumers exited = " + consumerFutures.size());
            System.out.println("queue empty = " + queue.isEmpty());
        } finally {
            producer.cancel(true);
            for (Future<int[]> f : consumerFutures) f.cancel(true);
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 MultiConsumerStopDemo.java
java MultiConsumerStopDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
total handled = 9
sum of ids = 45
consumers exited = 3
queue empty = true
```

### 12.3. Tại sao không in job ID theo thứ tự từ consumers?

Ba consumers chạy song song, nên **thứ tự hoàn tất processing** không nhất thiết cùng thứ tự lấy jobs. Chúng có thể phân chia 9 jobs theo tỷ lệ 4–3–2, 5–2–2 hoặc lịch khác. Nhưng nếu không có lỗi và đã chờ hết futures, tổng count **9** và tổng IDs **45** được bảo toàn.

### 12.4. Vì sao có producer + consumers = 4 threads?

Nếu tạo executor chỉ một worker rồi producer bị block do queue đầy, các consumers trong queue executor chưa có cơ hội chạy → deadlock/starvation. Ví dụ chọn đủ threads cho 1 producer + 3 consumers. Đây là cấu hình phục vụ demo; production có thể dùng executors khác và thiết kế phù hợp, nhưng phải phân tích trường hợp **blocking**.

### 12.5. Điểm yếu của poison pills cần nhớ

- Queue không cung cấp `close()`/`shutdown()`; pill là **protocol application**, không phải tính năng built-in.
- Nếu producer ném exception **trước khi gửi đủ pills**, consumers có thể treo ở `take()`.
- Nếu producer/consumer bị cancel/interrupt trong khi enqueue pills vào bounded queue đang đầy, protocol dừng cần kế hoạch dự phòng.
- Với **nhiều producers**, phải có một **coordinator** xác nhận tất cả producers đã xong enqueue data trước khi đưa pills. Nếu một producer gửi END khi producer khác vẫn còn gửi job, consumer có thể dừng quá sớm.
- Số pills phải đủ cho những consumers thực sự cần rời bằng cơ chế này; một pill không tự broadcast.
- Trong hệ thống cần **không mất dữ liệu**, phải kiểm tra workers xử lý xong qua Futures/ACK, không chỉ kiểm tra queue rỗng.
- Đừng để END trùng message nghiệp vụ hợp lệ; dùng type/envelope riêng.

Ví dụ chạy bình thường đạt kết quả xác định; trong production nên thiết kế shutdown state, error propagation và rollback/retry thích hợp thay vì chỉ dựa vào finally có pills.

## 13. Nhiều producers: khi nào được phát tín hiệu kết thúc?

Giả sử có P producers đang thêm vào cùng một FIFO queue, C consumers lấy jobs. Một mô hình đúng:

1. Coordinator quyết định **dừng nhận producers mới**.
2. Đợi **tất cả P producers** hoàn thành hoặc có failure policy rõ ràng.
3. Nếu thành công và muốn drain, coordinator enqueue **C END messages**.
4. Đợi tất cả C consumers kết thúc xử lý và nhận END.
5. Đối chiếu job counts/ACKs và xử lý job failures.
6. Shutdown executors theo chính sách, ghi metrics và báo trạng thái.

**Không** để mỗi producer tự gửi END trong finally; điều đó có thể tạo quá nhiều hoặc quá ít pills và làm một số consumers dừng **trước khi các producers khác gửi xong**.

### 13.1. Cách tách dữ liệu và control messages

Một mô hình message envelope:

```java
sealed interface Message permits Data, End {}
record Data(long id, String payload) implements Message {}
record End() implements Message {}
```

Đây là các **type declarations Java 17** hợp lệ, phải đặt ở top level hoặc scope phù hợp. Khi queue dùng `BlockingQueue<Message>`, consumer phân biệt `Data` và `End` bằng `instanceof`. Không cần dựa vào `null` hoặc integer magic value.

Nếu một message có error/cancel/status, có thể mở rộng sealed hierarchy; nhưng không nhét toàn bộ logic business vào lớp queue.

### 13.2. Queue không là message broker bền vững

Một producer đưa dữ liệu vào process memory rồi JVM crash trước khi consumer xử lý → queue mất. Nếu cần replay, exactly-once business effects hoặc phối hợp nhiều services, hãy dùng durable messaging/transactional outbox, retries có ID và idempotent consumers. `BlockingQueue` không tạo durable storage hoặc distributed consensus.

## 14. Shutdown và cancellation: tránh consumers chờ vô hạn

Vì `BlockingQueue` không có `close()`, shutdown thường dựa vào một trong các chiến lược:

- **Drain + END:** đợi producers xong, gửi đúng số END rồi đợi consumers.
- **External running flag + timed poll:** consumer định kỳ timeout để kiểm tra flag **và** queue remaining; phải dùng cấu hình visibility như `volatile`/atomic và protocol dừng không mất jobs.
- **Interrupt/cancel:** khi cần dừng khẩn cấp, interrupt threads bị block tại `put/take/poll(timeout)`. Xử lý `InterruptedException` đúng.
- **Forceful shutdown:** `ExecutorService.shutdownNow()` cố interrupt running tasks nhưng không đảm bảo mọi business operation sẽ lập tức dừng, và không tự rollback.
- **Graceful pool shutdown:** `shutdown()` ngừng nhận task executor mới; các tasks đã submit có thể chạy tiếp. Nó **không đồng nghĩa** gửi END vào queue riêng do app quản lý.

### 14.1. Xử lý InterruptedException

Một consumer đơn giản:

```java
try {
    while (!Thread.currentThread().isInterrupted()) {
        Work work = queue.take();
        process(work);
    }
} catch (InterruptedException stop) {
    Thread.currentThread().interrupt();
    // Báo caller/owner và kết thúc theo shutdown policy.
}
```

Đây là **snippet**, cần `Work`, `queue` và `process` đã định nghĩa. Khi bị ngắt trong `take()`, worker chưa chắc có job từ lệnh take đó; nhưng nếu bị ngắt khi đang *process* job từ lần take trước, phải xử lý trạng thái job đang làm để không mất nghiệp vụ.

### 14.2. Timed poll với shutdown flag

```java
while (running.get() || !queue.isEmpty()) {
    Work work = queue.poll(200, TimeUnit.MILLISECONDS);
    if (work != null) process(work);
}
```

Đây là snippet trong phương thức, `running` là `AtomicBoolean`, `queue` là BlockingQueue và `process` do app định nghĩa. **Điều kiện quan trọng:** owner chỉ set `running=false` sau khi đã đóng admission của mọi producers và không còn enqueue mới. Nếu flag bị hạ quá sớm, một consumer có thể thấy queue rỗng rồi thoát dù producer còn job đang tới.

Việc `isEmpty()` riêng lẻ chỉ là snapshot, nên tính đúng của shutdown còn phụ thuộc **protocol producer completion** chứ không phải chỉ `running || !isEmpty`.

### 14.3. put END cũng có thể block

Nếu bounded queue đầy và consumers đã dừng do failure, producer có thể bị block vô hạn khi `put(END)`. Vì vậy shutdown robust cần deadline/cancel, ví dụ `offer(END, timeout, unit)`, và nếu không đưa được END thì escalate tới interrupt/force termination theo policy. Không hứa “finally put poison pill luôn chạy xong”.

### 14.4. Producer ngừng nhưng consumer vẫn chờ

Nếu producer tự kết thúc mà không gửi END hoặc không cập nhật shutdown state, consumer `take()` sẽ không nhận thông báo cuối stream. Không có tính năng `queue.isClosed()` mặc định. Đây là một trong những lỗi vận hành phổ biến nhất của producer–consumer.

## 15. Tính đúng khi sử dụng nhiều consumer

### 15.1. “Một phần tử chỉ được take bởi một consumer” khác “được xử lý thành công một lần”

Với thao tác lấy bình thường, một phần tử bị dequeue khỏi queue cho một consumer. Nhưng consumer có thể crash trước khi hoàn thành business operation. Queue không tự ghi nhận ACK hay retry. Do đó không nên diễn giải việc dequeue là **exactly-once processing**.

Nếu có retry application, một job có thể được xử lý lại. Dùng job ID, idempotency key, durable state, deduplication và transactional boundaries thích hợp.

### 15.2. FIFO không có nghĩa hoàn thành theo FIFO

Ví dụ consumer A nhận job 1 nhưng xử lý mất 5 giây, consumer B nhận job 2 và xử lý trong 10 ms. **Job 2 có thể hoàn thành trước job 1** dù thứ tự dequeue là FIFO.

Nếu cần bảo đảm kết quả theo thứ tự, dùng một consumer, partition theo key với mỗi partition xử lý tuần tự, reordering buffer với sequence ID hoặc thiết kế serialization.

### 15.3. Đừng dùng một non-thread-safe result List cho nhiều consumers

Nếu cả ba consumers cùng gọi `sharedArrayList.add(item)`, ArrayList không thread-safe và có thể mất dữ liệu. Bài demo nhiều consumers để mỗi thread giữ counter riêng và main cộng sau `Future.get`. Cách khác có thể dùng `ConcurrentLinkedQueue` làm result collection hoặc collections synchronized khi cần, nhưng điều phối kết quả sau completion thường dễ kiểm tra hơn.

### 15.4. Fairness khác ordering dữ liệu

Một số blocking queues có fairness policy cho **threads đang chờ**, không phải đặt độ ưu tiên cho jobs hoặc bảo đảm output thứ tự theo ID. Nếu cần ưu tiên, `PriorityBlockingQueue` là một cấu trúc riêng với `Comparator`, và không còn FIFO chung; nó cũng không có intrinsic capacity bound.

## 16. Cách xử lý lỗi của producer và consumer

Một system handoff tốt phải phân biệt:

| Sự kiện | Queue biết gì? | Ứng dụng cần làm gì? |
| --- | --- | --- |
| Producer submit task thành công | Không nhất thiết biết task được enqueue vào queue riêng | Theo dõi producer Future/ACK |
| Queue `offer(e)` trả false | Enqueue không thành công ngay | Reject/retry/drop có chủ ý |
| Producer bị interrupt khi `put` đang đợi | Lệnh bị ngắt | Hoàn tất/cancel job, không báo đã enqueue nếu chưa rõ |
| Consumer `take()` xong | Job đã rời queue | Xử lý rồi report success/failure |
| Consumer throw trong business code | Queue không tự retry | Job ID, retry/requeue/durable error channel |
| END enqueue thành công | Queue có control message | Consumer vẫn phải take/exit |
| END đã được take | Consumer nhận tín hiệu dừng | Đợi Future worker hoàn thành |
| `ExecutorService.shutdown()` được gọi | Executor không nhận task mới | Queue riêng không tự đóng |
| JVM crash | In-memory queue không bền vững | Durable delivery nếu requirement đòi hỏi |

### 16.1. Không nuốt InterruptedException

Sai:

```java
try {
    queue.put(job);
} catch (InterruptedException ignored) {
    // Sai: mất tín hiệu hủy và không nói job đã được enqueue chưa.
}
```

Đây là anti-pattern. Trong task hỗ trợ cancellation, hãy propagate hoặc restore interrupt flag sau khi cleanup, và report kết quả đúng cho owner. Không cố `put` vô hạn trở lại ngay sau interrupt trừ khi có policy rõ.

### 16.2. Không catch mọi exception rồi cho rằng có thể tiếp tục

Nếu consumer bị lỗi parse một message, việc retry, dead-letter hoặc dừng toàn pipeline tùy độ quan trọng. Nếu consumer mất kết nối DB, tiếp tục lấy hàng nghìn jobs mà không kiểm soát có thể làm mất khả năng khôi phục. Dùng error channel và điều phối admission/backpressure.

### 16.3. Không dùng sentinel như một lệnh “xóa hàng đợi”

Nếu producer gửi END sau dữ liệu, consumer có thể xử lý dữ liệu trước END. Nếu bạn muốn **hủy ngay, không drain**, cần giao thức khác: ngừng producers, interrupt/cancel consumers, xử lý pending messages và giải phóng resources. Dùng END không tự clear mọi job đang nằm trong queue.

## 17. Vì sao Thread.sleep không tạo ra cơ chế handoff đúng?

Một anti-pattern:

```java
while (queue.isEmpty()) {
    Thread.sleep(10);
}
Work work = queue.poll();
```

Đây là pseudo snippet với `Work`/`queue`, không phải pattern tốt. Sau `isEmpty()`, consumer khác có thể lấy mất phần tử; `poll()` trả null. Sleep tạo latency nhân tạo, vẫn polling, và không giải quyết shutdown/cancel.

Nếu consumer cần **đợi**, dùng `take()` hoặc `poll(timeout,unit)`. Nếu producer cần **đợi chỗ**, dùng `put()`/timed offer. Queues được thiết kế để làm nhiệm vụ đợi/wakeup phù hợp mà không cần người học tự viết monitor lock/notify cho mỗi phần tử.

## 18. Các cấu trúc queue khác: khi nào không dùng FIFO thông thường?

### 18.1. PriorityBlockingQueue

Có thứ tự ưu tiên theo natural ordering/Comparator, **không bảo đảm FIFO theo thời gian enqueue**. Nó không có intrinsic capacity bound nên `put` không chờ vì đầy. Phù hợp khi ưu tiên job quan trọng nhưng phải cân nhắc starvation của job ưu tiên thấp.

### 18.2. DelayQueue

Một queue phục vụ các `Delayed` elements chỉ trở nên khả dụng để lấy khi delay hết. Phù hợp scheduling/deferred work. Không phải lựa chọn FIFO đơn giản cho mọi producer–consumer; capacity không giới hạn nội tại.

### 18.3. LinkedBlockingDeque

Một blocking deque có thể thêm/lấy ở **hai đầu**, ví dụ work queues cần ưu tiên xử lý phần tử đầu hoặc các tác vụ đặc biệt. Khi chỉ cần FIFO producer–consumer thông thường, API hai đầu có thể làm tăng độ phức tạp không cần thiết.

### 18.4. Không dùng queue non-thread-safe giữa các threads nếu không có đồng bộ

`ArrayDeque`, `LinkedList` hoặc `ArrayList` thông thường không tự đảm bảo thread-safety cho nhiều threads truy cập. Nếu app tự `synchronized` toàn bộ truy cập, phải tự xử lý waiting, notification và shutdown; với producer–consumer cơ bản, BlockingQueue đơn giản và ít lỗi hơn.

## 19. Monitoring và capacity planning

Những metrics hữu ích:

- Enqueue rate, dequeue rate (jobs/s).
- Job latency từ create đến take, từ take đến business completion.
- Thời gian producer bị chặn khi `put` hoặc timed `offer`.
- Tỷ lệ `offer(e)` bị từ chối / timed offer bị timeout.
- Queue length, high-watermark, remaining capacity (snapshot).
- Số consumers active, idle, failed và processing duration.
- Số jobs đang processing bên ngoài queue (**in-flight**).
- Retry count, dead-letter count, duplicate job IDs.
- Shutdown/drain duration và số job còn chưa xử lý.
- Heap usage, GC pressure và kích thước payload.

**Queue size là một số quan sát tức thời, không là khóa hoặc tín hiệu đồng bộ.** Với `LinkedTransferQueue` và `ConcurrentLinkedQueue`, size có thể không O(1), và trong lúc concurrent modification nó chỉ là một giá trị biến động. Đừng đặt logic correctness vào size polling.

### 19.1. Capacity dựa trên thời gian chịu được backlog

Một cách suy nghĩ: nếu producer có thể burst thêm khoảng 500 jobs và consumer xử lý không kịp trong 2 giây, capacity cần xét load profile, memory và SLA thay vì chọn theo số ngẫu nhiên. Dù queue đủ chứa burst, nếu rate dài hạn của producer lớn hơn consumer thì backlog vẫn tăng; capacity chỉ kéo dài thời gian trước khi phải áp backpressure.

### 19.2. Fairness có chi phí

`ArrayBlockingQueue<>(capacity,true)` có fairness policy cho các threads chờ, có thể giảm variance của thời gian đợi ở một số workload nhưng có chi phí scheduling/throughput. Bật chỉ khi có yêu cầu, đo đúng tải thực.

### 19.3. Không tạo hàng nghìn consumers chỉ để tăng throughput

Số consumers có thể bị giới hạn bởi CPU cores, DB connection pool, rate limits hoặc external API. Tạo quá nhiều consumers có thể tăng contention, memory và downstream overload. Tune consumers cùng với queue capacity, job cost và downstream limits.

## 20. Quy trình thiết kế một pipeline an toàn

Một thiết kế thực tế nên quyết định rõ:

1. **Message type:** immutable hay ownership-transfer? Có job ID, payload, status?
2. **Queue type:** bounded buffered, direct handoff hay transfer semantics?
3. **Capacity:** số elements và memory budget; có phù hợp burst/SLA?
4. **Admission:** `put`, timed offer, reject, shed hay retry?
5. **Consumer concurrency:** bao nhiêu workers có thể chạy và chặn? Có bottleneck ở downstream?
6. **Ordering:** FIFO dequeue đủ chưa, hay business cần per-key/order guarantee?
7. **Error semantics:** retry, dead-letter, idempotency, recovery khi consumer crash?
8. **Shutdown:** ngừng producers rồi drain/END, hoặc cancel ngay; kiểm soát đúng số consumers.
9. **Interrupt:** thread nào chịu trách nhiệm hủy? Thao tác blocking có timeout?
10. **Monitoring:** metrics backlog, enqueue failures, processing latency và drain time.
11. **Testing:** đúng values, số jobs, không mất job khi happy path; có failure injection.
12. **Security/durability:** dữ liệu có yêu cầu bền vững, xác thực, kiểm soát truy cập?

### 20.1. Mẫu end-to-end

```text
Receive request
      |
 Validate & assign job ID
      |
 try offer(job, deadline) ---- false ----> overload response / retry policy
      |
     true
      |
 bounded BlockingQueue
      |
 consumer take()
      |
 process with idempotency & error handling
      |
 record success / retry / dead letter
      |
 lifecycle owner coordinates producer stop -> drain -> consumer exit
```

Giữa enqueue success và business success có một **khoảng rủi ro**. Hãy xác định rõ API trả response khi nào: sau enqueue, sau take, hay sau xử lý hoàn tất; mỗi lựa chọn mang semantics khác nhau.

## 21. Kiểm thử producer–consumer không phụ thuộc lịch scheduler

### 21.1. Test nên assert những gì?

- Một producer, một consumer trên FIFO: dữ liệu 1..N được nhận **đúng thứ tự**.
- Đủ số jobs nhận được, tổng checksum đúng.
- Queue rỗng sau khi tất cả consumers đã hoàn tất.
- Bounded capacity không bị vượt (cấu hình, và các phép thử offer khi đầy).
- Timed offer trả false khi đầy và không có consumer trong deadline.
- Timed poll trả null khi rỗng và không có producer trong deadline.
- SynchronousQueue không giữ element, `offer` thất bại khi không có waiting consumer.
- LinkedTransferQueue `tryTransfer` thất bại không enqueue nếu không có waiting consumer.
- Nhiều consumers nhận đúng tổng số jobs, không assert mỗi consumer nhận bao nhiêu.
- Sau shutdown protocol, tất cả futures hoàn thành hoặc report lỗi rõ.

### 21.2. Test không nên assert những gì?

- Consumer A chắc luôn nhận job 1, consumer B chắc job 2.
- Producer và consumer luôn chạy khác core CPU.
- Log từ nhiều threads in đúng một thứ tự cứng.
- Mọi handoff kết thúc trong 1 ms trên mọi hệ thống.
- `queue.size()` đọc trước và sau tác vụ đồng thời là phép đo atomic.
- Một `Thread.sleep(20)` đủ chứng minh consumer đã start.
- SynchronousQueue fairness=true đảm bảo business processing FIFO.
- Mọi exception đều có thể khắc phục bằng retry vô hạn.

### 21.3. Dùng CountDownLatch/Future để điều phối tests

Với những tests concurrency cần trạng thái “consumer đã bắt đầu chờ”, `CountDownLatch` có thể giúp điều phối startup. Nhưng latch báo thread **đã chạy tới một dòng code** không nhất thiết chứng minh nó **đã nằm trong internal take() wait queue**. Nếu cần kiểm thử `tryTransfer` khi có waiting consumer, dùng API observation kết hợp timeout/test coordination một cách có kiểm soát; đừng biến một assert timing rất nhạy thành tiêu chuẩn logic của ứng dụng.

Trong bốn demos, thay vì dựa vào log timing, chương trình sử dụng `Future.get(timeout)` và các output xác định. Các timeout chỉ là giới hạn thử nghiệm; máy quá tải có thể timeout thay vì đạt stdout, không phải lỗi của hợp đồng API.

## 22. Các lỗi phổ biến và cách sửa

**1. “Dùng LinkedList chung cho producer và consumer là đủ.”** Sai nếu thiếu synchronization; dùng BlockingQueue hoặc cấu trúc đồng thời thích hợp.

**2. “Concurrent queue đồng nghĩa message tự immutable.”** Sai. Không mutate message sau khi publish nếu không có ownership/synchronization.

**3. “Queue giúp consumer biết producer đã đóng.”** Sai. BlockingQueue không có close/shutdown built-in.

**4. “take() trả null khi producer hết dữ liệu.”** Sai. take chờ; null không phải element hợp lệ.

**5. “put(null) là poison pill chuẩn.”** Sai. BlockingQueue không chấp nhận null.

**6. “offer(e) trả false vẫn nghĩa job đã được nhận và sẽ retry.”** Sai. Enqueue thất bại; caller quyết định policy.

**7. “put không bao giờ block nếu queue thread-safe.”** Sai. Bounded queue có thể đầy.

**8. “ArrayBlockingQueue<>(1) giống SynchronousQueue.”** Sai. Queue capacity 1 đệm được 1 element; synchronous queue không đệm.

**9. “SynchronousQueue.size()==0 chứng minh không có producers đang đợi.”** Sai; size luôn 0 theo đặc tả.

**10. “SynchronousQueue.offer(e) luôn lưu lại e để consumer đến sau lấy.”** Sai. Nếu chưa có waiting consumer thì trả false và không lưu.

**11. “LinkedTransferQueue.put(e) chờ consumer nhận.”** Sai; put enqueue ngay vì unbounded. Chỉ `transfer` có nghĩa chờ nhận.

**12. “tryTransfer(e)==false vẫn để message trong queue.”** Sai; không enqueue khi không giao được ngay.

**13. “transfer thành công nghĩa DB đã commit.”** Sai; chỉ consumer đã nhận element.

**14. “LinkedTransferQueue là bounded vì có transfer.”** Sai; put/offer có thể làm backlog tăng lớn.

**15. “Một END đủ dừng ba consumers.”** Sai; mỗi END chỉ được một consumer take.

**16. “Mỗi producer tự gửi END ngay khi xong.”** Nguy hiểm nếu còn producers khác đang thêm data; dùng coordinator.

**17. “Queue rỗng nghĩa tất cả jobs đã được xử lý.”** Sai; consumers có thể đang xử lý jobs đã dequeue.

**18. “FIFO queue bảo đảm FIFO completion trên nhiều consumers.”** Sai; thứ tự hoàn thành phụ thuộc thời gian xử lý.

**19. “ConcurrentLinkedQueue có take().”** Sai; nó không implements BlockingQueue.

**20. “Poll null luôn báo cuối stream.”** Sai; có thể chỉ tạm thời rỗng.

**21. “Thread.sleep trong vòng while là handoff tốt.”** Không; poll/sleep tạo race và latency.

**22. “remainingCapacity()>0 rồi put không bao giờ block.”** Sai; kiểm tra và put không atomic.

**23. “size() là một phép snapshot chính xác để tính số jobs đang in-flight.”** Sai; còn jobs đã được lấy và size có thể biến động.

**24. “Không có giới hạn capacity thì memory không phải vấn đề.”** Sai; unbounded backlog có thể gây OOM.

**25. “shutdown executor cũng đóng queue.”** Sai; hai vòng đời khác nhau.

**26. “finally put(END) luôn chạy xong.”** Sai nếu queue đầy và consumers đã ngừng.

**27. “Nuốt InterruptedException để tiếp tục sẽ không ảnh hưởng.”** Sai; mất tín hiệu hủy và có thể treo shutdown.

**28. “Một job được take thì đã xử lý exactly-once.”** Sai; còn failure giữa take và commit.

**29. “Một consumer chết sẽ tự động làm consumer khác nhận lại job đang xử lý.”** Không; queue không có visibility timeout/ACK built-in.

**30. “Fairness=true sắp xếp job theo business priority.”** Sai; fairness của threads chờ, không phải job priority.

**31. “Dùng ConcurrentLinkedQueue luôn nhanh hơn BlockingQueue.”** Không có bảo đảm; phụ thuộc wait/wakeup và contention.

**32. “Cứ tăng consumer count vô hạn là xử lý nhanh hơn.”** Sai; có thể quá tải DB/network và tăng context switching.

**33. “addAll vào BlockingQueue là một transaction atomic.”** Không mặc định; các bulk Collection operations không nhất thiết atomic.

**34. “Có thể dùng `PriorityBlockingQueue` mà vẫn mặc định FIFO.”** Sai; thứ tự phụ thuộc priority.

## 23. Checklist triển khai

- [ ] Message có type rõ ràng, không dùng null làm sentinel?
- [ ] Có xác định producer và consumer ownership/lifecycle?
- [ ] Chọn đúng BlockingQueue khi cần wait; không busy-spin trên ConcurrentLinkedQueue?
- [ ] Nếu cần backpressure, queue có capacity hữu hạn?
- [ ] Với LinkedBlockingQueue, đã truyền capacity tường minh?
- [ ] Chọn put/offer/timed offer theo deadline và overload policy?
- [ ] Kiểm tra `offer(e)` trả false, không bỏ qua enqueue failure?
- [ ] Có xử lý `InterruptedException` và restore interrupt khi cần?
- [ ] Có phân biệt được queue received và business processed?
- [ ] Message object immutable hoặc không mutate sau enqueue?
- [ ] Nếu dữ liệu chứa mutable arrays/buffers, có ownership/defensive copy?
- [ ] Đã hiểu happens-before giữa publish và consume?
- [ ] Không để producer tiếp tục sửa object consumer đang đọc?
- [ ] Đã xác định FIFO per producer và ordering nghiệp vụ cần thiết?
- [ ] Nếu dùng nhiều consumers, có tránh assert thứ tự completion?
- [ ] Nếu dùng poison pills, có gửi đúng số consumers?
- [ ] Nếu nhiều producers, coordinator đợi họ xong trước khi phát END?
- [ ] Có fallback nếu producer lỗi trước khi gửi hết END?
- [ ] Có giải pháp khi queue đầy mà shutdown cần gửi END?
- [ ] Không coi `queue.isEmpty()` là proof mọi jobs đã xử lý?
- [ ] Có theo dõi jobs đang in-flight bằng Futures/ACK/counters riêng?
- [ ] Nếu dùng SynchronousQueue, hiểu không có capacity và offer có thể false?
- [ ] Nếu dùng TransferQueue, phân biệt put, transfer, tryTransfer và timed version?
- [ ] Không dùng TransferQueue.put như bounded queue?
- [ ] Nếu dùng nonblocking queue, có wakeup mechanism và backpressure?
- [ ] Worker pool đủ capacity cho những tasks có thể bị block ở put/take?
- [ ] Có shutdown policy graceful/forced/cancel và deadlines?
- [ ] Có test failure của consumer, submission rejection, interrupt và timeout?
- [ ] Có xử lý poison pill là control message, không phải dữ liệu hợp lệ?
- [ ] Nếu cần durable delivery, có kiến trúc ngoài in-memory BlockingQueue?
- [ ] Có metrics enqueue/dequeue rate, backlog, processing latency, failure/timeout?
- [ ] Có benchmark trên dữ liệu và contention của ứng dụng thật?
- [ ] API và mã mẫu tương thích Java 17+?

## 24. Câu hỏi tự kiểm tra

**1.** Producer–consumer là gì? — Một bên tạo job, một bên lấy job và xử lý, có thể chạy trên threads khác nhau.

**2.** BlockingQueue khác queue không blocking thế nào? — Hỗ trợ các thao tác chờ chỗ/chờ dữ liệu như `put/take`.

**3.** `put(e)` làm gì khi bounded queue đầy? — Chờ đến khi có chỗ hoặc thread bị interrupt.

**4.** `offer(e)` làm gì khi queue đầy? — Trả false ngay.

**5.** `offer(e,timeout,unit)` có tác dụng gì? — Chờ tối đa một thời hạn để thêm element.

**6.** `take()` làm gì khi queue rỗng? — Đợi cho đến khi có element hoặc bị interrupt.

**7.** `poll()` trả null có phải EOF? — Không; chỉ queue chưa có element tại thời điểm đó.

**8.** BlockingQueue có chấp nhận null element không? — Không.

**9.** BlockingQueue có API close/shutdown built-in không? — Không.

**10.** Bounded queue giúp gì? — Giới hạn backlog theo số elements và buộc chính sách backpressure.

**11.** LinkedBlockingQueue không truyền capacity có an toàn bộ nhớ tuyệt đối không? — Không; giới hạn mặc định rất lớn.

**12.** `SynchronousQueue` có capacity bao nhiêu? — Không có bộ đệm, capacity 0.

**13.** `SynchronousQueue.offer` không có waiting consumer trả gì? — False.

**14.** `SynchronousQueue.put` có thể chờ gì? — Một consumer tương ứng tới nhận element.

**15.** `LinkedTransferQueue.put` có chờ consumer không? — Không vì capacity unbounded.

**16.** `LinkedTransferQueue.transfer` có tác dụng gì? — Đợi đến khi element được consumer nhận.

**17.** `tryTransfer(e)` không có waiting consumer có lưu element không? — Không, trả false.

**18.** Timed `tryTransfer` timeout trả gì? — False; element không còn được enqueue.

**19.** ConcurrentLinkedQueue có `take()` không? — Không.

**20.** Handoff thành công có nghĩa consumer xử lý DB xong không? — Không.

**21.** Happens-before của BlockingQueue nói gì? — Các writes trước khi enqueue được nhìn thấy sau khi consumer lấy element.

**22.** Producer có nên sửa mutable message sau enqueue không? — Không nếu thiếu synchronization/ownership.

**23.** Với ba consumers, cần bao nhiêu END messages trong mẫu poison-pill? — Thường ba, mỗi consumer một END.

**24.** Nếu có nhiều producers, bao giờ coordinator gửi END? — Sau khi tất cả producers đã hoàn tất enqueue dữ liệu và không còn producer mới.

**25.** Queue rỗng đã chứng minh mọi jobs xử lý xong chưa? — Chưa, còn jobs in-flight.

**26.** Queue FIFO có bảo đảm completion FIFO khi nhiều consumers không? — Không.

**27.** Tại sao một executor quá ít threads có thể deadlock? — Task đang chạy block trong khi task cần thiết khác còn ở queue chưa được chạy.

**28.** Interrupt khi đang take/put nên xử lý thế nào? — Theo cancellation policy, propagate hoặc restore interrupt flag và cleanup.

**29.** Có thể dùng một `ArrayList` chung cho ba consumers ghi kết quả không? — Không an toàn nếu không đồng bộ; dùng thread-local results rồi tổng hợp hoặc concurrent collection.

**30.** Poison pill có giải quyết producer crash trước khi enqueue END không? — Không, cần failure/timeout/cancel fallback.

**31.** Muốn message sống qua JVM crash thì dùng gì? — Durable queue/broker hoặc persistence/protocol thích hợp.

**32.** Có nên dùng size()/remainingCapacity() như phép đặt chỗ atomic không? — Không; đó là snapshot biến động.

**33.** Khi nào chọn SynchronousQueue thay bounded buffer? — Khi muốn giao trực tiếp và producer chỉ tiếp tục nếu có consumer tương ứng.

**34.** Khi nào chọn TransferQueue? — Khi cần cả enqueue thường và chuyển giao chờ consumer nhận với semantics cụ thể.

**35.** Vì sao phải benchmark? — Throughput và latency còn phụ thuộc workload, payload, số producers/consumers, downstream bottleneck và GC.

## 25. Tài liệu chính thức Java SE 17

- [BlockingQueue — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): ma trận add/offer/put/take/poll, không hỗ trợ null, memory consistency, không có close/shutdown.
- [ArrayBlockingQueue — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded FIFO, capacity và fairness tùy chọn.
- [LinkedBlockingQueue — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): FIFO, cấu hình capacity và producer–consumer.
- [SynchronousQueue — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html): zero-capacity rendezvous handoff, offer/put/take.
- [TransferQueue — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TransferQueue.html): transfer, tryTransfer và waiting consumer.
- [LinkedTransferQueue — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedTransferQueue.html): unbounded linked transfer queue và semantics thực tế.
- [ConcurrentLinkedQueue — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): nonblocking concurrent FIFO, không có take.
- [ExecutorService — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit/stop worker pools và Futures.
- [Future — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): quan sát completion, exceptions, timeout, cancellation.
- [AtomicBoolean — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html): shutdown flag có memory visibility.
- [Java Concurrency Package — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html): memory consistency effects và primitives.

**Ghi nhớ:** Chuyển giao producer–consumer an toàn cần cả **thread-safe queue** lẫn **protocol xử lý/đóng hệ thống**. Dùng `BlockingQueue` để producer `put/offer` và consumer `take/poll`, chọn bounded queue nếu cần backpressure. `SynchronousQueue` là handoff không đệm; `LinkedTransferQueue.transfer` đợi consumer nhận nhưng `put` của nó không giới hạn backlog. Queue bảo đảm visibility của writes trước enqueue, **không bảo đảm business ACK hoặc dữ liệu bền vững**. Khi nhiều consumers, một poison pill không đủ cho mọi người; phải điều phối producer completion và worker shutdown rõ ràng, có timeout, interrupt và error handling.