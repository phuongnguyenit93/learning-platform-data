# Hàng đợi đồng thời trong Java: Kiểm tra dữ liệu dùng chung và bảo đảm quan sát giữa các luồng

## 1. Mục tiêu: hàng đợi thread-safe khác với object thread-safe

Khi xây dựng hệ thống producer–consumer trên Java, một thread chuẩn bị message và đưa vào hàng đợi; thread khác nhận rồi xử lý. Hai câu hỏi về tính đúng cần được trả lời riêng:

1. **Queue có an toàn khi nhiều thread cùng gọi `put`, `offer`, `take`, `poll` không?**
2. **Consumer có nhìn thấy đúng dữ liệu mà producer đã ghi, và những thay đổi sau đó có còn an toàn không?**

`BlockingQueue`, `LinkedBlockingQueue`, `ArrayBlockingQueue`, `ConcurrentLinkedQueue`, `LinkedTransferQueue` và các concurrent collections khác cung cấp cơ chế đồng thời và **bảo đảm memory visibility khi công bố phần tử**. Nhưng queue **không tự khóa tất cả các trường của object đã đưa vào**, không biến `ArrayList` bên trong message thành thread-safe, không bảo đảm các thay đổi sau khi gửi được quan sát chính xác, và không xác nhận nghiệp vụ đã xử lý xong.

Bài **“Kiểm tra dữ liệu dùng chung và bảo đảm quan sát giữa các luồng”** thuộc **“Hàng đợi đồng thời”**, sử dụng kiến thức từ **Java 7** vẫn còn hiệu lực với **Java 17+**:

- Java Memory Model (JMM), quan hệ `happens-before` và safe publication.
- Bảo đảm từ producer **trước khi đưa phần tử vào concurrent collection** đến consumer **sau khi truy cập/lấy phần tử đó**.
- Vì sao chỉnh sửa mutable object **sau enqueue** cần đồng bộ bổ sung.
- Thiết kế **immutable message** và defensive copy.
- Dữ liệu dùng chung ngoài queue: `volatile`, `AtomicInteger`, lock và bất biến của nhiều trường.
- Cách kiểm thử dựa trên `CountDownLatch`, `Thread.join`, `AtomicReference`, không phụ thuộc `Thread.sleep`.
- Sự khác biệt giữa **queue empty**, **received** và **processed**.

Bài có một chương trình `QueueVisibilityDemo.java` **biên dịch và chạy được trên Java 17+**. Kết quả thực tế đã kiểm tra bằng `javac` và `java`; những tình huống data race cố ý chỉ được trình bày dưới dạng mã phản ví dụ, không chạy như một kiểm thử nondeterministic.

## 2. Bức tranh ba lớp bảo đảm

Một pipeline có thể được nhìn theo ba lớp độc lập:

```text
Producer thread                  Concurrent queue            Consumer thread
---------------                  ----------------            ---------------
packet.version = 7
packet.payload = "READY"
packet.samples = [2, 3]

queue.put(packet) --------------> [ packet ] ----------------> packet = take()
       ^                                                       |
       |                                                       v
  ENQUEUED                                                 READ fields
  (accepted)                                                (visibility
                                                              guaranteed
                                                              for writes
                                                              BEFORE put)

                                                               |
                                                               v
                                                          process(packet)
                                                               |
                                                               v
                                                            COMPLETED
                                                          (needs own ack)
```

**Lớp A — queue operation:** một lệnh thêm/xóa phần tử thực hiện đúng contract đồng thời của implementation. Ví dụ `take()` trả một phần tử và loại bỏ nó khỏi queue.

**Lớp B — memory visibility:** những phép ghi xảy ra trước khi công bố phần tử vào concurrent queue được consumer nhìn thấy khi truy cập phần tử đó theo quy tắc `happens-before`.

**Lớp C — business completion:** consumer đã xử lý, commit, lưu thành công hoặc gửi phản hồi. Queue **không cung cấp** xác nhận cấp này; cần `Future`, trạng thái xử lý riêng, transaction, acknowledgment hoặc một giao thức tương đương.

Chỉ có A và B không suy ra C. Thậm chí A không biến tất cả những hành động diễn ra **sau khi gửi** thành có thứ tự với consumer.

## 3. Java Memory Model và quan hệ `happens-before`

### 3.1. `happens-before` có nghĩa gì?

`happens-before` là quan hệ thứ tự bộ nhớ trong JMM. Nếu phép ghi `W` trên thread A `happens-before` phép đọc `R` trên thread B, và không có các ghi cạnh tranh xen giữa theo quy tắc JMM, phép đọc được bảo đảm quan sát hiệu ứng phù hợp của `W`. Đây không đơn thuần là thứ tự đồng hồ thực tế; nó là **quy tắc visibility và ordering** được Java định nghĩa.

Những nguồn phổ biến tạo `happens-before` gồm:

- Thứ tự chương trình trong cùng một thread (*program order*).
- Thoát khỏi `synchronized` rồi thread khác vào cùng monitor.
- Ghi `volatile` rồi thread khác đọc tương ứng.
- `Thread.start()`: những hành động trước `start` xảy ra trước hành động của thread được start.
- `Thread.join()`: những hành động của thread đã kết thúc có quan hệ với thread gọi join thành công.
- `CountDownLatch.countDown()` rồi `await()` thành công trên cùng latch.
- Đưa phần tử vào một concurrent collection rồi thread khác truy cập/lấy phần tử ấy.
- Submit task vào `ExecutorService` rồi task thực thi, và kết quả task được lấy bằng `Future.get()` theo contract.

Những bảo đảm này được trình bày tại Java SE 17 `java.util.concurrent` package và JLS Chapter 17.

### 3.2. Bảo đảm cụ thể của concurrent queue

Theo tài liệu `BlockingQueue` và `java.util.concurrent`:

> Các hành động của producer **trước khi đặt object vào concurrent collection** `happens-before` các hành động của consumer **sau khi truy cập hoặc loại bỏ object đó** khỏi collection.

Diễn đạt bằng mã:

```java
final class Packet {
    int version;
    String payload;
}

BlockingQueue<Packet> queue = new ArrayBlockingQueue<>(10);

// Producer thread:
Packet message = new Packet();
message.version = 7;
message.payload = "READY";
queue.put(message);

// Consumer thread:
Packet received = queue.take();
int v = received.version;      // Thấy 7 theo publication contract.
String s = received.payload;   // Thấy "READY".
```

Đây là **snippet gồm hai luồng khác nhau**, không phải một chương trình độc lập; `queue` là đối tượng dùng chung, import `java.util.concurrent.*` và xử lý `InterruptedException`. Việc hai trường của `Packet` không có `volatile` **không làm ví dụ sai**: các phép ghi đã được thực hiện **trước `put`**, và consumer đọc **sau `take`**. Quan hệ `happens-before` qua queue là đủ cho lần bàn giao này.

### 3.3. Chuỗi quan hệ

```text
Producer writes fields (W)
         |
         | program order
         v
Concurrent queue.put(message)
         |
         | queue publication / access happens-before
         v
Consumer queue.take() returns message
         |
         | program order
         v
Consumer reads fields (R)

Therefore: W happens-before R.
```

Tính bắc cầu là điểm then chốt: không nhất thiết phải đặt `volatile` lên từng trường được khởi tạo trước khi enqueue. Nhưng nếu consumer hoặc producer còn **ghi tiếp cùng trường**, cần kiểm tra các quan hệ khác cho những phép ghi sau đó.

### 3.4. Đừng suy diễn quá phạm vi

Queue publication bảo đảm các hành động **trước lần công bố liên quan**. Nó không nói rằng mọi biến toàn cục vô tình được truy cập ở hai thread sẽ luôn mới nhất, không nói rằng các phép tăng counter là atomic, và không bảo đảm một chuỗi ghi nhiều trường sau enqueue được consumer đọc thành một snapshot nhất quán.

**Một object được publish an toàn không có nghĩa object đó an toàn để mutate đồng thời mãi mãi.**

## 4. Queue thread-safe không đồng nghĩa payload thread-safe

### 4.1. Mutable object sau enqueue

Xét phản ví dụ:

```java
final class MutableJob {
    int status;
    String note;
}

MutableJob job = new MutableJob();
job.status = 1;
queue.put(job);      // Công bố status=1.
job.status = 2;      // GHI SAU ENQUEUE, không có sync với consumer.
```

Đây là **mã phản ví dụ**, không phải mẫu được khuyến nghị. Nếu consumer đọc `job.status` đồng thời với phép ghi `status=2`, queue chỉ tạo quan hệ `happens-before` cho các ghi **trước `put`**. Phép ghi `2` không tự nhiên trở thành đồng bộ với consumer; đây có thể là **data race**. JMM không bảo đảm consumer luôn thấy `2` chỉ vì “producer đã sửa xong trước trên đồng hồ”.

Đừng viết test chạy hàng nghìn lần rồi kết luận “vì máy tôi luôn thấy `2`, code này an toàn”. Các race có thể không lộ trên một CPU/JIT rồi xuất hiện trên môi trường khác.

### 4.2. Tham chiếu thread-safe khác state thread-safe

`BlockingQueue<MutableJob>` bảo vệ **các thao tác trên queue**, không bảo vệ toàn bộ `MutableJob`. Một số nhầm lẫn thường thấy:

- “Queue là concurrent nên các fields của object đưa vào đều volatile.” — Sai.
- “`queue.put` tự clone object.” — Sai; queue giữ reference theo contract, không mặc định copy payload.
- “Khi consumer `take` thì producer không còn reference nữa.” — Sai; producer vẫn có thể giữ reference và mutate.
- “`final MutableJob job` khiến fields immutable.” — Sai; `final` trên reference chỉ ngăn reassign biến ấy.
- “`volatile MutableJob ref` khiến tất cả fields của `MutableJob` thread-safe.” — Sai. Volatile publication có ordering riêng, nhưng không cung cấp mutual exclusion hoặc atomicity cho các mutations trên object.

### 4.3. `int` đọc/ghi atomic nhưng không đủ

Đọc/ghi `int` thông thường thường là một thao tác nguyên tử ở mức giá trị, nhưng không đồng nghĩa được bảo đảm nhìn thấy **phiên bản mới nhất** khi không có synchronization. Hơn nữa `count++` là read–modify–write, không phải một phép cập nhật atomic ngay cả nếu biến `count` là `volatile int`.

Nếu có nhiều writers, phải lựa chọn đồng bộ tương ứng với **invariant của dữ liệu**, không chỉ dựa vào khả năng “không bị rách byte”.

## 5. Thiết kế message bất biến để tránh race sau khi gửi

### 5.1. Ưu tiên object bất biến

Một message nên hoàn chỉnh **trước khi enqueue**, rồi được consumer đọc mà không cần chỉnh sửa fields:

```java
record Event(long id, String payload, List<String> tags) {
    Event {
        tags = List.copyOf(tags);
    }
}
```

Đây là snippet Java 17+, import `java.util.List`. `record` giúp các components có final fields; `List.copyOf(tags)` tạo một list unmodifiable chứa snapshot các **tham chiếu phần tử** tại lúc tạo.

**Điểm quan trọng:** `List.copyOf` không deep-copy các objects bên trong. Nếu phần tử là mutable object, nội dung object ấy vẫn có thể bị mutate từ bên ngoài. Ví dụ dùng `String` làm tags vì bản thân strings bất biến.

### 5.2. Defensive copy trước khi publish

```java
List<String> draft = new ArrayList<>(List.of("A", "B"));
Event event = new Event(42, "READY", draft);
queue.put(event);

// Nguồn draft vẫn có thể bị sửa mà không làm tags trong event đổi.
draft.add("LATE");
```

`draft` và `queue` là các biến của đoạn minh họa, cần import `java.util.*` và `java.util.concurrent.*`. `Event` lưu snapshot riêng của list, nên consumer thấy tags `[A, B]`, không phải `[A, B, LATE]`. Chính sách không cho mutator trực tiếp sửa `event.tags()` cũng giúp tránh race.

### 5.3. Arrays và `ByteBuffer`

`byte[]`, `int[]` và `ByteBuffer` thông thường là mutable. Nếu producer tái sử dụng buffer sau enqueue trong khi consumer đang đọc, consumer có thể thấy dữ liệu bị thay đổi.

Các lựa chọn:
- Clone array trước khi gửi: `data.clone()`.
- Dùng immutable representation hoặc copy một phần byte hợp lệ vào array mới.
- Chuyển hẳn **quyền sở hữu** buffer cho consumer, producer không chạm lại cho đến khi có ack hoàn tất.
- Dùng pool buffer với lifecycle/ref-count/ack rõ ràng.
- Với `ByteBuffer.asReadOnlyBuffer()`, cần nhớ view chỉ chống ghi qua view ấy, **không bảo vệ dữ liệu nếu một alias writable khác vẫn sửa backing memory**.

### 5.4. Ownership transfer thực tế

Một thiết kế đơn giản là:

```text
Producer creates message
Producer fills all fields
Producer makes immutable snapshot (or relinquishes mutable ownership)
Producer enqueues
Producer DOES NOT mutate published payload
Consumer dequeues
Consumer reads/processes
Consumer returns explicit completion ack if required
```

Không có lệnh của `BlockingQueue` tự lấy mất reference ở producer. “Không được mutate sau enqueue” là một **quy ước thiết kế hoặc bất biến mã nguồn** mà team phải thực hiện và kiểm thử.

## 6. Nếu bắt buộc sửa dữ liệu sau enqueue, cần thêm đồng bộ

### 6.1. Ví dụ dùng CountDownLatch

`CountDownLatch` tạo một quan hệ `happens-before` khác ngoài queue:

```java
// Consumer thread (sau queue.take()):
MutableJob job = queue.take();
updated.await();
int status = job.status;

// Producer thread (sau queue.put() và tín hiệu consumer đã take):
job.status = 2;
updated.countDown();
```

Đây là **snippet mô tả hai threads**, `updated` là `CountDownLatch(1)` dùng chung, và cần xử lý `InterruptedException`. Nếu được điều phối đúng, hành động ghi `status=2` trước `countDown` `happens-before` phần đọc sau `await` trở về thành công. Quan hệ này đến từ latch, **không phải từ lần enqueue trước đó**.

### 6.2. `volatile`: visibility và ordering cho một tín hiệu

Một pattern có thể phù hợp khi có một writer duy nhất và consumer muốn chờ một trạng thái:

```java
final class SharedState {
    int result;
    volatile boolean ready;
}

// Writer thread:
shared.result = 42;
shared.ready = true;

// Reader thread:
if (shared.ready) {
    int value = shared.result;
}
```

Đây là snippet minh họa, `shared` là một instance được publish an toàn theo cách khác. Ghi `volatile ready=true` có quan hệ `happens-before` với đọc `ready` tương ứng; các ghi trước nó như `result=42` được nhìn thấy khi reader thấy ready. Không dùng busy-spin vô hạn `while (!ready) {}` trong production: có thể lãng phí CPU, thiếu deadline và không xử lý cancellation.

`volatile` **không** làm `result++`, `if (...) result=...` hay cập nhật nhiều fields trở thành một transaction.

### 6.3. `AtomicInteger` và CAS

Dùng khi nhiều workers cùng cập nhật một counter:

```java
AtomicInteger completed = new AtomicInteger();
completed.incrementAndGet();
int count = completed.get();
```

Đây là atomic read–modify–write, tránh **lost update** do nhiều threads cùng `count++`. `LongAdder` có thể hữu ích cho high-contention counters, nhưng `sum()` không là một atomic snapshot đồng thời với các updates; nó thường thích hợp cho thống kê, không thay thế bộ đếm có invariant mạnh.

### 6.4. `synchronized` / `Lock` khi nhiều fields phải nhất quán

Nếu một business state gồm `balance` và `lastTransactionId`, người đọc không được thấy nửa cập nhật cũ/nửa cập nhật mới. Có thể cần khóa chung cho cả write và read:

```java
synchronized (sharedLock) {
    state.balance += delta;
    state.lastTransactionId = transactionId;
}
```

Bên đọc phải đồng bộ **cùng lock** khi muốn một snapshot nhất quán. Một mình synchronized phía writer nhưng đọc không synchronized vẫn có thể có data race.

### 6.5. Snapshot nguyên tử của nhiều chỉ số

Hai `AtomicInteger` riêng biệt bảo đảm từng counter được cập nhật atomic, **không bảo đảm cặp giá trị nhất quán trong một lần đọc** nếu workers đang cập nhật giữa chừng.

Nếu cần đồng bộ count và sum như một state:

```java
record Stats(int count, int sum) {}

AtomicReference<Stats> stats =
        new AtomicReference<>(new Stats(0, 0));

int value = 5;
stats.updateAndGet(old ->
        new Stats(old.count() + 1, old.sum() + value));

Stats snapshot = stats.get();
```

Đây là một phương án dùng snapshot immutable và CAS. Hàm truyền vào `updateAndGet` **phải side-effect-free** vì dưới contention nó có thể được áp dụng lại nhiều lần. Không gọi database, gửi email hoặc tăng counter bên ngoài trong lambda này.

## 7. Kiểm thử memory visibility phải dựa vào điều gì?

### 7.1. Một lần thử thành công không đủ chứng minh JMM

Nếu một data race xảy ra nhưng luôn “trông đúng” trên máy bạn, điều đó không biến code thành đúng. Các tình huống data race có thể phụ thuộc:
- CPU cache/coherence, số cores.
- JIT compilation và tối ưu hóa.
- Scheduling của threads.
- Tần suất contention.
- Khả năng JVM/CPU reorder các phép truy cập hợp lệ theo JMM.

Vì vậy lập luận an toàn phải xuất phát từ **quan hệ `happens-before` hoặc các bất biến đồng bộ** được API/JLS bảo đảm. Bài test chỉ là một bằng chứng thực thi bổ sung.

### 7.2. Đồng bộ test bằng latches

Để test đúng thứ tự, dùng `CountDownLatch`:

- `countDown()` của producer/consumer báo sự kiện đã xảy ra.
- `await(timeout, unit)` chờ và thất bại rõ nếu sự kiện không đến.
- `Thread.join(timeout)` đợi worker hoàn tất và phát hiện thread leak.
- `AtomicReference<Throwable>` truyền lỗi worker về main để không nuốt exception.

Không dùng `Thread.sleep(50)` để kết luận consumer đã dequeue. Sleep chỉ trì hoãn theo thời gian, không đảm bảo consumer được scheduler chạy đến dòng cần đo.

### 7.3. Test giữ nguyên contract thay vì thử ép một race

Thay vì cố tạo test “consumer chắc chắn đọc sai field nonvolatile” (không thể đảm bảo trên mọi JVM), ta có thể:
1. Kiểm tra **pre-enqueue writes** được consumer đọc đúng qua queue.
2. Kiểm tra **post-enqueue writes** chỉ được đọc sau một latch tạo HB bổ sung.
3. Kiểm tra defensive copy không bị thay đổi khi source list được sửa.
4. Tạo gate để chứng minh queue đã rỗng trong khi business processing vẫn chưa xong.
5. Cho hai workers cập nhật counters bằng atomics và kiểm tra tổng sau khi cả hai join.

Đó là năm kịch bản của chương trình `QueueVisibilityDemo`.

## 8. Queue trống không đồng nghĩa consumer đã xử lý xong

Khi consumer gọi `take()`, phần tử rời khỏi queue **trước khi business code xử lý xong**. Queue có thể trống nhưng consumer vẫn đang tính toán, gọi API, ghi database hoặc chưa gửi ack.

```text
Time T1: producer puts JOB             queue=[JOB], processed=false
Time T2: consumer takes JOB             queue=[],    processed=false
Time T3: consumer starts processing     queue=[],    processed=false
Time T4: consumer finishes processing   queue=[],    processed=true
```

Đừng viết:

```java
while (!queue.isEmpty()) {
    Thread.onSpinWait();
}
reportSuccess(); // Sai: queue empty không chứng minh job đã process.
```

Đây là **phản ví dụ**, không chạy; `reportSuccess()` minh họa cho hành động báo sai. Ngoài việc tốn CPU, `isEmpty` là snapshot có thể thay đổi ngay khi producer khác gửi thêm.

Nếu cần biết **mọi việc đã xử lý xong**, hãy dùng ack/số lượng `inFlight` có đồng bộ, `CountDownLatch` cho batch cố định, `Future` cho task, hoặc một lifecycle protocol có trạng thái riêng. Hãy đóng quyền submit trước khi kết luận toàn bộ hệ thống idle; tránh các producers còn đang thêm message.

### 8.1. Enqueued vs received vs processed

| Mốc | Quan sát nào có ý nghĩa? | Điều chưa được bảo đảm |
| --- | --- | --- |
| Enqueued | `put` trả về / `offer` trả true | Consumer đã lấy |
| Received | `take`/`poll` trả phần tử; producer `transfer` có thể đợi tới đây | Business logic thành công |
| Processed | Worker gửi ack/future complete sau khi xử lý | Durability trừ khi có commit bền vững |
| Persisted | Transaction/commit hoặc durable broker báo kết quả theo contract | End-to-end exactly-once nếu chưa thiết kế |

`LinkedTransferQueue.transfer` chỉ cung cấp **handoff tới consumer**, không chờ logic consumer hoàn tất. Chủ đề này tập trung memory safety; khi cần business completion, phải phân biệt cấp độ xác nhận.

## 9. Tại sao `size()`, `peek()`, `isEmpty()` không phải barrier?

### 9.1. Các phép quan sát là snapshot

`size()`/`isEmpty()`/`peek()` có thể có semantics thread-safe cho từng method, nhưng kết quả là trạng thái **tại thời điểm quan sát**. Trong hệ thống nhiều producers/consumers, trạng thái có thể thay đổi ngay sau khi trả về.

Không viết logic “nếu `!queue.isEmpty()` thì `queue.take()` chắc chắn không block”:

```java
if (!queue.isEmpty()) {
    Object work = queue.take(); // Consumer khác có thể đã take trước.
}
```

Đây là phản ví dụ check-then-act. Với yêu cầu không block, gọi `poll()` **một lần** rồi kiểm tra `null`.

### 9.2. `ConcurrentLinkedQueue.size()`

Class này có thể cần traversal để đếm và độ chính xác không được bảo đảm nếu queue thay đổi đồng thời. Không dùng `size` làm “transaction boundary” hay điều kiện đúng sai của business logic. Các metrics có thể dùng gần đúng nhưng cần hiểu chi phí và latency.

### 9.3. `peek()` và safe publication

Javadoc memory-consistency nói các hành động trước công bố `happens-before` thao tác **access hoặc removal** của element, nên `peek` một object từ concurrent collection có thể hưởng bảo đảm visibility cho các ghi trước công bố. Tuy nhiên `peek` **không lấy phần tử ra**, không chuyển ownership, không ngăn producer/consumer khác mutate hoặc remove nó, và không báo processing done.

Không lấy guarantee của memory publication để nâng `peek` thành acknowledgment nghiệp vụ.

## 10. Phân biệt object immutable, final field, volatile và atomic

| Cơ chế | Bảo đảm chính | Điều không tự cung cấp |
| --- | --- | --- |
| Concurrent queue handoff | Thread-safe queue ops và HB khi publish/access object | Thread safety cho mọi mutations của payload |
| `final` field | Có quy tắc khởi tạo final-field theo JMM | Deep immutability của referenced object |
| `record` | Final component fields, cấu trúc dữ liệu rõ ràng | Defensive copy của array/list mutable nếu không tự viết |
| `List.copyOf` | List unmodifiable snapshot của phần tử | Deep-copy element objects |
| `volatile` | Visibility/ordering cho accesses trên field | Atomicity của `counter++`, composite invariants |
| `AtomicInteger` | Atomic read–modify–write một integer | Transaction cho nhiều field độc lập |
| `AtomicReference<ImmutableState>` | Atomic thay thế một snapshot object | Tính side-effect-free của update lambda nếu coder làm sai |
| `synchronized` | Mutual exclusion và HB qua cùng monitor | An toàn nếu writer/reader dùng khóa khác |
| `CountDownLatch` | Event HB qua countDown/await thành công | Khởi động lại sau count về 0 |
| `Thread.join` | Quan sát worker đã kết thúc và HB | Timeout nếu worker còn sống |
| `Future.get` | Nhận result và HB của task đã tính | Automatically persist hoặc retry kết quả |

Quan trọng: không có “magic keyword” khiến mọi shared state tự trở nên an toàn. Phải xác định **luồng nào được ghi, luồng nào đọc, giữa hai bên có quan hệ đồng bộ nào và invariant cần bảo vệ là gì**.

## 11. Ví dụ production pattern: xử lý message theo sở hữu rõ ràng

### 11.1. Message được xây xong trước khi enqueue

```java
record OrderEvent(String orderId, long amountCents) {}

BlockingQueue<OrderEvent> queue = new ArrayBlockingQueue<>(1024);

// Producer:
queue.put(new OrderEvent("order-42", 12_500L));

// Consumer (thread khác):
OrderEvent event = queue.take();
processOrder(event);
```

Đây là snippet minh họa, `processOrder` cần được định nghĩa và queue cần lifecycle. `OrderEvent` chỉ dùng `String` và primitive `long`, nên dễ coi là immutable. Producer không còn mutation nào trên payload sau enqueue.

### 11.2. Không cập nhật trạng thái message theo alias chia sẻ

Nếu consumer muốn đánh dấu xử lý, tốt hơn là cập nhật một **store keyed by orderId** hoặc trả kết quả qua ack, không sửa `event.status` trên một object mutable mà producer vẫn đọc không đồng bộ.

### 11.3. Nếu phải giữ state mutable riêng

Có thể dùng một concurrent map các request states:

```java
record ProcessingState(boolean done, String result) {}

ConcurrentHashMap<String, ProcessingState> states =
        new ConcurrentHashMap<>();

states.put("order-42", new ProcessingState(false, ""));
states.compute("order-42", (id, old) ->
        new ProcessingState(true, "OK"));
```

Đây là snippet minh họa. `ConcurrentHashMap.compute` cung cấp semantics atomic cho key tương ứng theo contract; mapping function nên ngắn, không block và không có side effects khó retry. Trường hợp cần transaction giữa nhiều keys hoặc database records, cần thiết kế đồng bộ/transaction khác.

### 11.4. Completion ack

Nếu consumer có thể thất bại sau khi `take`, nên phân biệt:
- `received` — message đã được lấy.
- `started` — consumer bắt đầu xử lý.
- `succeeded` / `failed` — xử lý đã hoàn tất, với cause.
- `persisted` — trạng thái đã được commit bền vững.

Thông tin này không xuất hiện chỉ nhờ một lệnh `BlockingQueue.put` hoặc `LinkedTransferQueue.transfer`.

## 12. Chương trình Java 17+ đầy đủ đã biên dịch và chạy

Chương trình sau chứng minh **năm kịch bản** bằng những điều kiện có kiểm soát, tránh cố tạo một data race để lấy kết quả không ổn định.

Lưu file **`QueueVisibilityDemo.java`**:

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class QueueVisibilityDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static void await(CountDownLatch latch, String label)
            throws InterruptedException {
        check(latch.await(5, TimeUnit.SECONDS), label);
    }

    static void join(Thread thread) throws InterruptedException {
        thread.join(5000);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Thread did not finish: " + thread.getName());
        }
    }

    static final class MutablePacket {
        int version;
        String payload;
        int[] samples;
        int afterPublication;
    }

    static void safePublication() throws Exception {
        BlockingQueue<MutablePacket> queue = new ArrayBlockingQueue<>(1);
        AtomicReference<String> seen = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        CountDownLatch consumed = new CountDownLatch(1);
        Thread receiver = new Thread(() -> {
            try {
                MutablePacket packet = queue.take();
                check(packet.version == 7, "version");
                check("READY".equals(packet.payload), "payload");
                check(packet.samples[0] == 2 && packet.samples[1] == 3,
                        "samples");
                seen.set(packet.version + ":" + packet.payload + ":"
                        + (packet.samples[0] + packet.samples[1]));
            } catch (Throwable t) {
                failure.set(t);
            } finally {
                consumed.countDown();
            }
        }, "visibility-reader");

        receiver.start();
        try {
            MutablePacket packet = new MutablePacket();
            packet.version = 7;
            packet.payload = "READY";
            packet.samples = new int[]{2, 3};
            queue.put(packet);
            await(consumed, "consumer did not receive packet");
            join(receiver);
            check(failure.get() == null, "read failed: " + failure.get());
            check("7:READY:5".equals(seen.get()), "read mismatch");
            System.out.println("publication.consumerSaw=7:READY:5");
            System.out.println("publication.prePutWritesVisible=true");
        } finally {
            receiver.interrupt();
            join(receiver);
        }
    }

    static void laterWriteNeedsSynchronization() throws Exception {
        BlockingQueue<MutablePacket> queue = new ArrayBlockingQueue<>(1);
        CountDownLatch took = new CountDownLatch(1);
        CountDownLatch updated = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicReference<Integer> before = new AtomicReference<>();
        AtomicReference<Integer> after = new AtomicReference<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread receiver = new Thread(() -> {
            try {
                MutablePacket packet = queue.take();
                before.set(packet.version);
                took.countDown();
                await(updated, "update signal missing");
                after.set(packet.afterPublication);
            } catch (Throwable t) {
                failure.set(t);
                took.countDown();
            } finally {
                finished.countDown();
            }
        }, "later-write-reader");

        receiver.start();
        try {
            MutablePacket packet = new MutablePacket();
            packet.version = 11;
            queue.put(packet);
            await(took, "consumer not ready for later update");
            packet.afterPublication = 99;
            updated.countDown();
            await(finished, "consumer did not finish");
            join(receiver);
            check(failure.get() == null, "later update error: " + failure.get());
            check(Integer.valueOf(11).equals(before.get())
                    && Integer.valueOf(99).equals(after.get()),
                    "post-put update not seen");
            System.out.println("laterWrite.prePutValue=" + before.get());
            System.out.println("laterWrite.withLatch=" + after.get());
            System.out.println("laterWrite.extraHappensBefore=true");
        } finally {
            updated.countDown();
            receiver.interrupt();
            join(receiver);
        }
    }

    record Snapshot(int id, List<String> labels) {
        Snapshot {
            labels = List.copyOf(labels);
        }
    }

    static void immutableSnapshot() throws Exception {
        List<String> source = new ArrayList<>(List.of("A", "B"));
        Snapshot snapshot = new Snapshot(42, source);
        BlockingQueue<Snapshot> queue = new ArrayBlockingQueue<>(1);
        queue.put(snapshot);
        source.add("LATE");
        Snapshot taken = queue.take();
        check(taken.id() == 42, "snapshot id");
        check(taken.labels().equals(List.of("A", "B")),
                "snapshot changed after source mutation");
        boolean immutable;
        try {
            taken.labels().add("X");
            immutable = false;
        } catch (UnsupportedOperationException expected) {
            immutable = true;
        }
        check(immutable, "snapshot labels should not be mutable");
        System.out.println("snapshot.labels=" + taken.labels());
        System.out.println("snapshot.originalListSize=" + source.size());
        System.out.println("snapshot.unmodifiable=" + immutable);
    }

    static void emptyQueueIsNotProcessed() throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        CountDownLatch taken = new CountDownLatch(1);
        CountDownLatch allowFinish = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(1);
        AtomicBoolean processed = new AtomicBoolean(false);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread consumer = new Thread(() -> {
            try {
                String job = queue.take();
                check("JOB".equals(job), "wrong job");
                taken.countDown();
                await(allowFinish, "processing release missing");
                processed.set(true);
            } catch (Throwable t) {
                failure.set(t);
                taken.countDown();
            } finally {
                done.countDown();
            }
        }, "process-reader");

        consumer.start();
        try {
            queue.put("JOB");
            await(taken, "job was not taken");
            boolean queueEmpty = queue.isEmpty();
            boolean processedBefore = processed.get();
            check(queueEmpty && !processedBefore,
                    "must show queue empty before processing");
            System.out.println("processing.queueEmptyAfterTake=" + queueEmpty);
            System.out.println("processing.doneBeforeRelease="
                    + processedBefore);
            allowFinish.countDown();
            await(done, "processing did not finish");
            join(consumer);
            check(failure.get() == null, "processing failed");
            check(processed.get(), "job not processed");
            System.out.println("processing.doneAfterAck=" + processed.get());
        } finally {
            allowFinish.countDown();
            consumer.interrupt();
            join(consumer);
        }
    }

    static void atomicAggregate() throws Exception {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(8);
        AtomicInteger count = new AtomicInteger();
        AtomicInteger sum = new AtomicInteger();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread[] consumers = new Thread[2];
        for (int i = 0; i < consumers.length; i++) {
            consumers[i] = new Thread(() -> {
                try {
                    while (true) {
                        int task = queue.take();
                        if (task == -1) return;
                        count.incrementAndGet();
                        sum.addAndGet(task);
                    }
                } catch (Throwable t) {
                    failure.compareAndSet(null, t);
                }
            }, "counter-consumer-" + i);
            consumers[i].start();
        }

        try {
            for (int n = 1; n <= 4; n++) queue.put(n);
            queue.put(-1);
            queue.put(-1);
            for (Thread consumer : consumers) join(consumer);
            check(failure.get() == null, "counting failed: " + failure.get());
            check(count.get() == 4 && sum.get() == 10,
                    "atomic aggregate mismatch");
            System.out.println("aggregate.processedCount=" + count.get());
            System.out.println("aggregate.sum=" + sum.get());
        } finally {
            for (Thread consumer : consumers) consumer.interrupt();
            for (Thread consumer : consumers) join(consumer);
        }
    }

    public static void main(String[] args) throws Exception {
        safePublication();
        laterWriteNeedsSynchronization();
        immutableSnapshot();
        emptyQueueIsNotProcessed();
        atomicAggregate();
        System.out.println("checks=PASS");
    }
}
```

### 12.1. Cách chạy

Cần JDK 17 hoặc mới hơn vì ví dụ dùng `record` và `List.copyOf`. Những bảo đảm JMM/queue nói đến đã áp dụng từ trước, nhưng file demo này cố ý chọn cú pháp hiện đại.

```bash
javac -encoding UTF-8 QueueVisibilityDemo.java
java QueueVisibilityDemo
```

### 12.2. Stdout chính xác đã kiểm chứng

```text
publication.consumerSaw=7:READY:5
publication.prePutWritesVisible=true
laterWrite.prePutValue=11
laterWrite.withLatch=99
laterWrite.extraHappensBefore=true
snapshot.labels=[A, B]
snapshot.originalListSize=3
snapshot.unmodifiable=true
processing.queueEmptyAfterTake=true
processing.doneBeforeRelease=false
processing.doneAfterAck=true
aggregate.processedCount=4
aggregate.sum=10
checks=PASS
```

Chương trình đã được biên dịch bằng `javac -encoding UTF-8` và chạy `java` thành công trên JDK phù hợp, thoát với mã 0 và in `checks=PASS`. Toàn bộ tệp trên là một class Java duy nhất, không cần project ngoài, network hay database.

## 13. Giải thích năm test trong chương trình

### 13.1. `safePublication()`

Consumer được chạy trên thread riêng, gọi `queue.take()`. Producer hoàn chỉnh các trường thường của `MutablePacket`:
- `version=7`,
- `payload="READY"`,
- `samples=[2,3]`,

rồi `put(packet)`. Consumer kiểm tra tất cả và tạo summary `7:READY:5`. Các fields **không khai báo volatile** nhưng có visibility qua queue, đúng contract `BlockingQueue`.

Lưu ý mã còn dùng `CountDownLatch`/`Thread.join` để main **đợi kết quả test**, nhưng việc consumer nhìn thấy các trường do producer ghi trước enqueue được bảo đảm bởi quan hệ queue publication. Không biến kết quả một lần chạy thành lời khẳng định vượt quá Javadoc.

### 13.2. `laterWriteNeedsSynchronization()`

Producer `put(packet)` khi `version=11`. Consumer `take` xong, báo latch `took`. Sau đó producer mới ghi `afterPublication=99` và `updated.countDown()`. Consumer **chỉ đọc trường sau** khi `updated.await` trở về thành công.

Điểm cần học:
- Queue bảo đảm visibility của `version=11` ghi trước enqueue.
- Latch `updated` tạo **quan hệ HB bổ sung** cho `afterPublication=99`, vì trường này được ghi **sau enqueue**.
- Nếu xóa latch và cho consumer đọc `afterPublication` trong lúc producer đang cập nhật, không có bảo đảm từ queue cho phép ghi sau ấy.

`laterWrite.extraHappensBefore=true` là chú thích về cấu trúc đồng bộ được dùng, không phải phép đo rằng tất cả dữ liệu mutable trên máy đều luôn an toàn.

### 13.3. `immutableSnapshot()`

Producer tạo `List<String> source=[A,B]`, xây `record Snapshot` có `List.copyOf(source)`, rồi queue giữ snapshot. Dù source thêm `LATE`, `snapshot.labels` vẫn `[A,B]`. Cố gọi `snapshot.labels().add("X")` ném `UnsupportedOperationException`.

Vì tags là `String`, chúng bất biến. Nếu danh sách chứa một `MutablePerson`, `List.copyOf` không tự clone `MutablePerson`; phải tự deep-copy theo miền dữ liệu.

### 13.4. `emptyQueueIsNotProcessed()`

Consumer nhận `JOB`, báo latch `taken` nhưng **chờ `allowFinish`** trước khi đặt `processed=true`. Main nhìn thấy `queue.isEmpty()==true` trong khi `processed==false`.

Chỉ sau khi giải phóng gate và đợi `done` mới in `processing.doneAfterAck=true`. Đây là bằng chứng có kiểm soát: **message rời queue và worker xử lý xong là hai mốc khác nhau**.

### 13.5. `atomicAggregate()`

Hai consumers cùng `take` bốn số 1,2,3,4; mỗi consumer tăng `AtomicInteger count` và cộng `AtomicInteger sum`. Sau khi main gửi hai sentinel `-1` để kết thúc hai workers, chờ `join` và xác minh:
- `processedCount=4`,
- `sum=10`.

Dùng atomics tránh mất cập nhật. Tuy nhiên **hai AtomicInteger tách rời không tạo atomic snapshot cho cặp count/sum trong lúc workers đang chạy**. Demo chỉ đọc cặp giá trị **sau khi hai worker đã kết thúc**; do đó kết luận `4,10` ổn định. Nếu cần đọc một cặp nhất quán khi vẫn có concurrent updates, dùng shared lock hoặc `AtomicReference<Stats>` immutable snapshot.

### 13.6. Các sentinel và shutdown

Demo gửi **hai giá trị `-1`** bởi có hai consumers. Đây là protocol riêng trong phạm vi demo, và `-1` không thuộc dữ liệu hợp lệ 1..4. Trong service thực, có thể dùng message type `Stop` rõ ràng thay vì một số magic; nếu có nhiều producers, chỉ gửi stop **sau khi ngừng nhận công việc mới** để tránh worker nghỉ trước khi những jobs cuối được enqueue.

## 14. Các kiểu lỗi visibility thường gặp

| Cách viết | Vấn đề | Hướng sửa |
| --- | --- | --- |
| Tạo payload rồi gửi trước khi điền đủ fields | Consumer có thể nhận object chưa hoàn tất | Hoàn tất object trước enqueue |
| `queue.put(job)` rồi tiếp tục sửa `job.status` | Queue HB không bao phủ ghi sau enqueue | Immutable message hoặc sync bổ sung |
| Dùng `volatile Job ref` rồi mutate `ref.list` | Volatile reference không khóa object graph | Defensive copy / lock / ownership |
| `final List<String> list` nhưng `list.add` song song | Final reference không khiến List immutable | `List.copyOf`, unmodifiable snapshot |
| Truyền `byte[]` rồi producer tái dùng ngay | Consumer có thể đọc bytes thay đổi | Copy hoặc chuyển ownership |
| Nhiều threads cùng `volatile count++` | Read–modify–write không atomic | `AtomicInteger.incrementAndGet` |
| Tăng count và sum bằng hai atomics rồi đọc “nhất quán” giữa chừng | Các field cập nhật độc lập | Immutable pair CAS/lock |
| Dùng `queue.isEmpty` là business-done | Consumer có thể vẫn đang xử lý | Completion ack/inFlight counter |
| `if (!queue.isEmpty()) queue.take()` | Check-then-act race giữa consumers | `poll()` một thao tác |
| Dùng `Thread.sleep(100)` để test visibility | Timing không phải synchronization | Latches/joins/atomics |
| Chạy test 10.000 lần đều PASS rồi kết luận không có race | Kết quả thực nghiệm không chứng minh JMM | Phân tích HB, review/stress bổ sung |
| Đọc `AtomicInteger` mà nghĩ tự biết mọi side effects đã commit | Counter không thay transaction | Ack sau commit và lifecycle |
| Gọi `queue.clear` khi consumer còn chạy | Có thể bỏ việc hoặc race với processing | Stop producers, drain/ack, shutdown có policy |
| Dùng `ConcurrentLinkedQueue.size()` làm invariant | Kết quả có thể không chính xác khi concurrent modification | Theo dõi state bằng cơ chế phù hợp |
| Dùng queue in-memory như durable log | JVM crash có thể mất dữ liệu | Durable broker/outbox/DB |
| Coi `transfer` là processing ack | Chỉ chờ receiver nhận phần tử | Completion future/status |
| Dùng `Collections.unmodifiableList(source)` như defensive copy | Wrapper vẫn nhìn thấy sửa đổi qua alias nguồn | `List.copyOf(source)` / clone |
| Coi `List.copyOf` là deep copy | Element references vẫn được chia sẻ | Sao chép element mutable |
| Catch InterruptedException rồi tiếp tục vô hạn | Shutdown khó, có thể mất yêu cầu dừng | Khôi phục flag và áp dụng policy |
| Tạo hai locks khác nhau ở producer/consumer | Không có mutual exclusion/HB qua cùng monitor | Chia sẻ đúng lock hoặc dùng concurrent primitive |

## 15. Các trường hợp biên liên quan đến queue implementation

### 15.1. `ArrayBlockingQueue`: bounded và có blocking

Queue có giới hạn dung lượng:

```java
BlockingQueue<String> q = new ArrayBlockingQueue<>(2);
q.put("A");
q.put("B");
```

Nếu có thêm `put("C")` và không consumer remove, producer có thể block chờ chỗ trống. Điều đó là **capacity backpressure**, không phải chờ business completion. Nó không thay đổi quy tắc memory publication cho A/B/C khi được lấy.

### 15.2. `LinkedBlockingQueue` và `LinkedTransferQueue`

`LinkedBlockingQueue` có thể nhận capacity; constructor không capacity sử dụng giới hạn logic lớn. `LinkedTransferQueue` là unbounded và có `transfer`/`tryTransfer`. Các class này vẫn cung cấp memory-consistency guarantee của concurrent collections, nhưng khác nhau ở capacity, handoff và chờ.

Truyền payload mutable sau enqueue vẫn cần tránh dù queue implementation nào được chọn.

### 15.3. `ConcurrentLinkedQueue`

Đây là concurrent queue không cung cấp `take()` kiểu `BlockingQueue`; consumer dùng `poll()` có thể nhận `null` và cần thiết kế scheduling/signaling phù hợp. Javadoc vẫn ghi memory-consistency effect về actions trước khi add và sau khi access/remove phần tử.

Không dùng busy-poll mãi trong production mà không có backoff hoặc cơ chế thông báo.

### 15.4. `SynchronousQueue`

`SynchronousQueue` có **zero capacity** và handoff trực tiếp producer–consumer. Nó không giữ backlog. Một lần `put/take` match chuyển phần tử và vẫn có visibility bảo đảm khi phần tử được trao đổi. Nhưng nhận vật thể không chứng minh processing complete.

### 15.5. Bulk operations

`BlockingQueue` nói rõ các operations như `addAll`, `removeAll`, `retainAll` không nhất thiết atomic toàn bộ trừ khi implementation bảo đảm. Nếu cần chuyển một batch như một transaction, hãy tự định nghĩa ranh giới atomicity, không cho rằng “thread-safe queue” khiến tất cả bulk operations indivisible.

`drainTo` có semantics riêng và có thể chuyển nhiều phần tử, nhưng không tạo business transaction xuyên những steps xử lý của consumer.

## 16. Hướng dẫn xử lý sự cố khó tái hiện

Khi báo cáo “consumer thỉnh thoảng thấy field rỗng”:
1. Xem payload có được điền đầy đủ **trước** enqueue không.
2. Xem references có bị expose/escape cho thread khác trước khi xây xong không.
3. Xem producer có sửa fields hoặc collections **sau enqueue** không.
4. Kiểm tra consumer có truy cập object **từ queue** hay từ một shared reference khác không có synchronization.
5. Xem các fields được cập nhật có cần invariant atomic qua nhiều trường không.
6. Xem đã dùng `CountDownLatch`, `Future.get`, `AtomicReference` hoặc lock đúng cặp producer/consumer chưa.
7. Không đưa `Thread.sleep` để “chữa” timing mà không tạo quan hệ HB.
8. Nếu có batching hoặc queue draining, xem các thao tác ngoài queue có được đồng bộ không.
9. Với shared buffer, kiểm tra vòng đời ownership và pool reuse.
10. Ghi rõ JDK, OS, số producers/consumers, payload type, thứ tự events và cách tạo queue.

**Đặc biệt:** Không cần cố tái hiện một data race thành công rồi mới được sửa. Nếu code thiếu quan hệ `happens-before` hoặc có mutable shared state không được bảo vệ, lập luận JMM đã đủ để chỉ ra nguy cơ.

## 17. Ma trận QA và kiểm thử concurrency

| Test | Điều phải chứng minh | Điều không được suy ra |
| --- | --- | --- |
| Producer ghi fields rồi `put`; consumer `take` | Consumer đọc đúng các ghi trước publication | Những mutations sau put đều an toàn |
| Consumer đọc sau một latch signal | Ghi trước countDown nhìn thấy sau await | Latch tự bảo vệ mọi biến mutable |
| `List.copyOf` với `String` elements | Sửa source list không đổi snapshot | Deep-copy arbitrary objects |
| Queue empty sau take | Không còn phần tử đang chờ trong queue ở snapshot | Job đã xử lý xong |
| Completion ack sau processing | Worker xác nhận đã hoàn tất protocol | Data được lưu bền nếu ack không gắn commit |
| 2 consumers tăng AtomicInteger | Không mất updates của counter | Cặp nhiều counters là atomic snapshot |
| `volatile counter++` | Không có guarantee RMW atomic | Cứ chạy nhanh thì đúng |
| Consumer khác lấy sau `!isEmpty` | Có thể race giữa check/take | Có quyền dùng check-then-act |
| Producer sửa array sau put | Có thể có data race | Luôn quan sát được lỗi trên máy test |
| Many producers and poison pills | Shutdown chỉ an toàn khi stop protocol đúng | Queue tự close/shutdown |
| `put` lúc queue đầy | Có thể block chờ capacity | Consumer đã process |
| `LinkedTransferQueue.transfer` | Bàn giao tới consumer | Business committed |

### 17.1. Viết test deterministic

- Dùng **gates** để kiểm soát thời điểm một worker được phép đi tiếp.
- Dùng **timeout** cho mọi blocking wait trong test.
- Thu thập worker exceptions vào `AtomicReference<Throwable>` và fail main nếu có lỗi.
- Luôn có `finally` mở gates/interrupt/join workers nếu test fail.
- Assert **kết quả cuối** chỉ sau khi các worker liên quan hoàn tất.
- Không assert tên thread, số lần scheduler chuyển context hoặc thời điểm tuyệt đối.

### 17.2. Stress testing có ý nghĩa nhưng không thay thế proof

Đối với concurrent algorithm phức tạp, có thể tham khảo công cụ **jcstress** của OpenJDK để kiểm thử những kết quả được JMM cho phép dưới các interleavings khác nhau. Tuy nhiên một lần stress test “không thấy lỗi” không chứng minh không có data race; trước hết phải phân tích contract và quan hệ đồng bộ.

Đối với hiệu năng, benchmark phải tách khỏi test correctness và dùng công cụ phù hợp. Không dùng tốc độ của một lần `System.nanoTime` như bằng chứng thread safety.

## 18. FAQ

**1. `BlockingQueue.put` có bảo đảm consumer nhìn thấy những fields đã set trước đó không?**  
Có, khi consumer truy cập/lấy chính phần tử từ queue theo contract memory-consistency và không có những ghi cạnh tranh không được đồng bộ làm thay đổi trạng thái ấy.

**2. Tôi có phải khai báo tất cả fields là `volatile` trước khi gửi queue không?**  
Không, nếu dữ liệu được xây hoàn chỉnh trước publication và không có mutation đồng thời sau đó. Queue đã tạo HB cho những ghi trước khi đưa vào.

**3. Nếu chỉnh sửa payload sau `put` thì sao?**  
Các chỉnh sửa ấy không được queue publication trước đó tự đồng bộ. Dùng immutable snapshot, ownership, `volatile/atomic`, lock hoặc latch phù hợp.

**4. `final Job job` có biến mọi fields của Job thành immutable không?**  
Không. Nó chỉ ngăn tham chiếu biến `job` được gán đối tượng khác.

**5. `record` có tự deep-copy `List` không?**  
Không. Phải chủ động `List.copyOf` hoặc sao chép sâu các phần tử mutable nếu cần.

**6. `List.copyOf` có bảo đảm phần tử mutable bên trong bất biến không?**  
Không. Nó chỉ tạo list unmodifiable; object elements có thể vẫn mutable.

**7. `volatile count++` có an toàn khi nhiều workers cùng cập nhật không?**  
Không. Cần `AtomicInteger.incrementAndGet` hoặc lock.

**8. Hai counters `AtomicInteger` có tạo một snapshot nhất quán không?**  
Không trong lúc concurrent updates. Dùng lock hoặc immutable state gói trong `AtomicReference`.

**9. `queue.isEmpty()==true` có chứng minh toàn bộ công việc đã xong không?**  
Không. Consumer có thể vừa `take` nhưng vẫn đang processing.

**10. `transfer` có đợi consumer xử lý xong không?**  
Không. Nó chờ consumer nhận phần tử theo contract, không chờ database commit hay business ack.

**11. `peek` có phá vỡ queue visibility guarantee không?**  
Không nhất thiết; Javadoc nói access/removal đều nhận HB đối với các ghi trước publication. Nhưng `peek` không chuyển ownership và không xác nhận xử lý xong.

**12. Vì sao `if(!queue.isEmpty()) queue.take()` vẫn có thể block?**  
Vì một consumer khác có thể lấy phần tử giữa hai method calls.

**13. `CountDownLatch` có thể dùng để đồng bộ writes sau enqueue không?**  
Có, nếu write xảy ra trước `countDown` và consumer đọc sau `await` thành công trên cùng latch.

**14. Một test chạy 100.000 lần đều đúng có loại trừ race không?**  
Không. Có thể scheduling/JIT/CPU chưa kích hoạt interleaving nguy hiểm.

**15. Queue in-memory có là durable storage không?**  
Không. JVM/process crash có thể mất những phần tử chưa được xử lý.

**16. Phải xử lý `InterruptedException` trong `take/put` thế nào?**  
Dùng shutdown/cancellation policy của ứng dụng, thường khôi phục interrupt flag và thoát/propagate phù hợp, không nuốt vô hạn.

**17. Nếu cần process ACK mạnh hơn thì dùng gì?**  
Future/ack/result store/transaction, với request ID và idempotency phù hợp để xử lý retry và kết quả đến muộn.

**18. Tại sao `AtomicReference.updateAndGet` lambda phải side-effect-free?**  
CAS có thể retry dưới contention, hàm cập nhật có thể được gọi nhiều lần; side effect bên ngoài có thể bị lặp.

## 19. Checklist code review

- [ ] Producer hoàn thiện payload trước khi enqueue.
- [ ] Consumer nhận payload bằng concurrent queue phù hợp; không đi vòng qua unsynchronized alias.
- [ ] Hiểu HB của `BlockingQueue`/concurrent collection.
- [ ] Không tưởng queue thread-safe nghĩa payload tự thread-safe.
- [ ] Không mutate payload sau enqueue nếu không có ownership/synchronization.
- [ ] Nếu dùng `record` với mutable components, có defensive copy.
- [ ] Không coi `List.copyOf` là deep copy arbitrary objects.
- [ ] Arrays/ByteBuffers sau enqueue không bị producer tái sử dụng trái protocol.
- [ ] Khi cần update sau enqueue, thiết kế thêm HB rõ ràng.
- [ ] `volatile` dùng đúng cho visibility, không dùng như atomic increment.
- [ ] Counters nhiều writers dùng atomic/locks.
- [ ] Multi-field invariants được đọc/ghi dưới cùng synchronization.
- [ ] Không dùng `size/isEmpty/peek` làm business-completion ack.
- [ ] Tránh check-then-act trên queue và shared state.
- [ ] Consumer processing có ack riêng khi ứng dụng cần.
- [ ] Queue bounded/unbounded có backpressure và memory budget.
- [ ] Shutdown ngừng producers trước, xử lý in-flight và workers đúng thứ tự.
- [ ] Poison pills có số lượng đủ và được gửi đúng lúc nếu dùng protocol này.
- [ ] Lỗi worker không bị nuốt; main/test nhận được cause.
- [ ] Tests dùng latches/joins/deadlines, không dựa vào sleep.
- [ ] Nếu stress test PASS vẫn phải review JMM/HB.
- [ ] Java code, tên file/class và stdout đã được biên dịch kiểm chứng.
- [ ] Chỉ sử dụng kiến thức còn áp dụng cho Java 17+.

## 20. Kết luận và tài liệu chính thức

Bài **“Kiểm tra dữ liệu dùng chung và bảo đảm quan sát giữa các luồng”** phải giữ đúng ranh giới giữa ba bảo đảm:

1. **Queue operation** an toàn với nhiều thread theo API implementation.
2. **Memory publication** bảo đảm các ghi trước enqueue được consumer quan sát sau khi truy cập/lấy phần tử theo `happens-before`.
3. **Mutable shared state và business completion** cần thêm thiết kế riêng: immutable message, ownership, volatile/atomic/lock/latch và acknowledgment.

Các kết luận áp dụng trong Java 17+:
- **Trước enqueue:** hoàn thiện dữ liệu; concurrent queue tạo một đường visibility.
- **Sau enqueue:** không mutate object đang được chia sẻ nếu không có giao thức đồng bộ.
- **Nhiều writers:** dùng atomic/lock cho invariants, không dựa vào `volatile++`.
- **Queue rỗng:** chỉ nói về phần tử đang chờ, không chứng minh processing finished.
- **Kiểm thử:** dùng HB và contract để chứng minh, dùng concurrency tests để kiểm chứng implementation và protocol, không suy luận từ timing tình cờ.

### Tài liệu chính thức Java SE 17

- [Oracle `java.util.concurrent` — Memory Consistency Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html): các quan hệ `happens-before` của concurrent collections, Executors, Futures, locks, atomics.
- [Oracle `BlockingQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `put/take/offer/poll`, bảo đảm memory consistency, capacity và semantics đồng thời.
- [Oracle `ArrayBlockingQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded producer–consumer queue.
- [Oracle `ConcurrentLinkedQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): lock-free concurrent queue và memory consistency.
- [Oracle `LinkedTransferQueue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedTransferQueue.html): enqueue và consumer handoff, publication semantics.
- [Oracle `AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic read–modify–write.
- [Oracle `AtomicReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): CAS và cập nhật immutable snapshots.
- [Oracle `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): HB qua `countDown/await`.
- [Oracle `List`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `List.copyOf` và unmodifiable-list semantics.
- [Java Language Specification 17, `17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5): mô hình memory visibility và ordering.
