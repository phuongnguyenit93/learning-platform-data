# Hàng đợi đồng thời trong Java: Iterator nhất quán yếu và thao tác nhiều bước

## 1. Bài toán thực tế

Một dịch vụ Java có nhiều producer thêm công việc vào một hàng đợi và nhiều consumer lấy công việc ra để xử lý. Bên cạnh đó, một thread giám sát muốn duyệt queue để ghi log hoặc xuất bảng trạng thái, trong khi các thread khác vẫn liên tục `offer()` và `poll()`.

Hai câu hỏi thường bị đánh đồng:

1. **Duyệt queue giữa lúc các thread khác đang thêm/xóa có an toàn không?** Với nhiều implementation queue đồng thời của Java, câu trả lời là **có thể duyệt an toàn bằng iterator nhất quán yếu** (*weakly consistent iterator*); nó không ném `ConcurrentModificationException` chỉ vì các thread khác đang thay đổi queue, nhưng **không phải ảnh chụp bất biến đầy đủ của một thời điểm**.
2. **Các phép riêng lẻ đều thread-safe thì việc nối nhiều phép có tự động atomic không?** **Không.** Một đoạn như `if (queue.size() < LIMIT) queue.offer(e)` là thao tác **check-then-act** nhiều bước, có race. Hai producer có thể cùng đọc `size() == 0` rồi cùng thêm một phần tử, khiến queue có 2 phần tử dù `LIMIT=1`.

Bài học tập trung vào **hai ranh giới**: mức nhất quán của phép duyệt và mức nguyên tử của một chuỗi hành động. Hiểu chúng giúp tránh những lỗi tinh vi như thống kê thiếu/méo, vượt hạn mức, xử lý trùng công việc, hoặc vô tình làm thất lạc message.

Tất cả API sử dụng đều **vẫn hiện hành** trong Java hiện đại. `ConcurrentLinkedQueue` và `LinkedBlockingQueue` có từ Java 5; `LinkedTransferQueue` có từ **Java 7**. Bài đặt trong module **Java 7** vì ứng dụng hàng đợi đồng thời vẫn có giá trị đến hiện tại; chương trình chạy hoàn chỉnh dùng **JDK 17+**.

### Kết quả học tập

Sau bài này, bạn có thể:

- Định nghĩa đúng **weakly consistent iterator** và phân biệt với fail-fast iterator, snapshot iterator.
- Giải thích vì sao một vòng `for (E e : queue)` **không khóa queue** và không bảo đảm thấy toàn bộ cập nhật đồng thời.
- Hiểu giới hạn của `size()`, `isEmpty()`, `contains()` và `peek()` khi có nhiều writer/consumer.
- Chỉ ra các race trong `size → offer`, `peek → poll`, `contains → remove`, `iterate → remove`.
- Chọn thao tác đơn an toàn như `poll()`, bounded `offer()` thay cho check-then-act.
- Biết khi nào dùng lock chung, bounded queue, snapshot sau khi tạm dừng writers, hoặc một protocol acknowledgement riêng.
- Hiểu `removeIf`, `forEach`, `addAll` và những bulk operation không được bảo đảm **atomic với concurrent updates**.
- Kiểm thử các race **có điều phối bằng barrier/latch**, không phụ thuộc may rủi scheduler hay `Thread.sleep`.
- Phân biệt thread-safety của **cấu trúc queue** với thread-safety của **object bên trong queue**.

## 2. Những queue đồng thời quan trọng

| Lớp/API | Công dụng chính | Iterator | Ghi chú thiết kế |
| --- | --- | --- | --- |
| `ConcurrentLinkedQueue<E>` | Queue FIFO không chặn cho nhiều thread | **Weakly consistent** | Unbounded; `size()` O(n), không đáng dùng để enforce capacity |
| `LinkedTransferQueue<E>` | FIFO queue có `transfer/tryTransfer` | **Weakly consistent** | Unbounded; thêm cơ chế producer–consumer handoff |
| `LinkedBlockingQueue<E>` | Blocking FIFO queue có thể cấp capacity | **Weakly consistent** | `put/take` có thể chặn; có thể tạo queue bounded |
| `ArrayBlockingQueue<E>` | Bounded FIFO queue dùng array | **Weakly consistent** | Capacity được enforce trong thao tác queue, không qua check ngoài |
| `PriorityBlockingQueue<E>` | Queue ưu tiên không chặn khi thêm | **Weakly consistent** | Iterator **không cam kết thứ tự ưu tiên**; `poll/take` mới lấy theo priority |
| `SynchronousQueue<E>` | Rendezvous queue không có storage | Không dùng làm queue để duyệt backlog | `put/take` phối hợp trực tiếp, size thường 0 |

**Không khái quát rằng mọi collection concurrent đều có iterator giống nhau.** Luôn đọc Javadoc của **implementation**. Một vài collection đồng thời khác dùng snapshot hoặc chiến lược duyệt riêng; thậm chí hai class cùng có từ “concurrent” cũng có thể khác nhau về thứ tự và số phần tử quan sát được.

### 2.1. Vì sao cần biết implementation?

`Queue<E>` và `BlockingQueue<E>` là interface, quy định các thao tác chung. Nhưng **chiến lược duyệt, cấu trúc bên trong, thời gian chạy `size()`, capacity và blocking** phụ thuộc implementation.

Ví dụ:

```java
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

Queue<String> queue = new ConcurrentLinkedQueue<>();
queue.offer("task-A");
queue.offer("task-B");

for (String item : queue) {
    System.out.println(item);
}
```

Đây là đoạn minh họa có thể đặt trong `main`. Vì không có thread khác thay đổi queue trong đoạn này, kết quả đơn giản là:

```text
task-A
task-B
```

Nhưng nếu một producer/consumer khác chạy cùng lúc, **không** dùng đúng hai dòng output này như lời hứa mọi lần duyệt trên queue đồng thời đều sẽ giống nhau.

## 3. Weakly consistent iterator là gì?

Một iterator **nhất quán yếu** cho phép thread đang duyệt **tiếp tục trong khi thread khác sửa queue**, không yêu cầu dừng tất cả các thread để tạo bản snapshot. Theo hợp đồng của `ConcurrentLinkedQueue`:

- Iterator trả phần tử phản ánh trạng thái queue ở **một số thời điểm từ lúc tạo iterator trở đi**.
- Iterator **không ném `ConcurrentModificationException` chỉ vì queue bị sửa đồng thời**.
- Nó có thể tiếp tục duyệt trong khi `offer()`, `poll()` hoặc `remove()` đang chạy ở thread khác.
- Implementation có các bảo đảm riêng về việc không trả trùng những phần tử tồn tại liên tục kể từ khi iterator được tạo.
- **Không** được suy rằng iterator đại diện cho **chính xác toàn bộ trạng thái queue tại thời điểm bắt đầu hoặc kết thúc**.

Đối với `ConcurrentLinkedQueue`, Javadoc còn nói những phần tử **liên tục có mặt trong queue kể từ khi tạo iterator** được trả về đúng một lần. Đó là **bảo đảm cụ thể của lớp này**; không mở rộng mù quáng cho mọi iterator concurrent khác, và không suy từ đó rằng những phần tử đã bị xóa hay mới được thêm trong lúc duyệt đều phải xuất hiện.

### 3.1. Phần tử có thể xuất hiện hoặc bị bỏ qua thế nào?

Giả sử iterator được tạo khi queue có `[A, B, C]`. Thread khác lần lượt xóa B và thêm D lúc vòng duyệt đang tiến hành.

Có thể quan sát một kết quả như `[A, C]`, hoặc `[A, B, C]`, hoặc có thêm D tùy timing và hợp đồng implementation. Đây chỉ là **các minh họa về khả năng quan sát**, không phải danh sách tất cả lịch thực thi được bảo đảm.

Các giới hạn quan trọng:

- Nếu B bị remove **sau khi iterator đã trả B**, ứng dụng đã nhìn thấy B rồi.
- Nếu B bị remove **trước khi iterator đi tới node đó**, việc B có còn được trả hay không phụ thuộc trạng thái và quy tắc duyệt của implementation.
- Nếu D được thêm khi iterator đang duyệt, iterator **có thể** thấy D hoặc không.
- Không có “điểm chụp duy nhất” để bắt buộc toàn bộ kết quả phải bằng queue vào đúng một thời điểm.
- Không được dùng iterator để đếm chính xác toàn bộ công việc pending nếu producer/consumer vẫn thay đổi queue.

**Weakly consistent không có nghĩa dữ liệu hỏng, không thứ tự và có thể ném bất kỳ exception nào.** Nó là một hợp đồng nhất quán **cố ý yếu hơn snapshot**, được thiết kế để cho phép tiến triển đồng thời. Thứ tự duyệt của từng implementation vẫn có ý nghĩa: `ConcurrentLinkedQueue.iterator()` duyệt theo thứ tự queue từ head tới tail, còn `PriorityBlockingQueue.iterator()` không cam kết thứ tự ưu tiên.

### 3.2. Không phải fail-fast iterator

Với `ArrayList`, iterator có cơ chế phát hiện thay đổi cấu trúc không được thực hiện qua iterator và thường ném `ConcurrentModificationException`. Đây là **best-effort bug detection**, không phải cơ chế khóa hay công cụ đồng bộ thread-safe.

So sánh:

| Đặc tính | Fail-fast iterator (ví dụ `ArrayList`) | Weakly consistent iterator (`ConcurrentLinkedQueue`) |
| --- | --- | --- |
| Có thể duyệt an toàn khi thread khác sửa collection? | Không, cần external synchronization | Có theo hợp đồng implementation |
| Concurrent modification có thể ném CME? | **Có**, best-effort | **Không** do sự thay đổi đồng thời của queue |
| Có phải snapshot cố định? | **Không** | **Không** |
| Có đợi writers dừng để tạo ảnh chụp? | Không tự động | Không tự động |
| Kết quả có thể phản ánh thay đổi sau khi tạo iterator? | Không phải cơ chế dùng được an toàn | **Có thể** |
| Dùng cho exact accounting khi đang sửa đồng thời? | Không | Không |

**Không viết code dựa vào việc “nếu có CME thì dữ liệu đã đổi” hoặc “không có CME thì snapshot chính xác”.** Hai giả định đều sai về hợp đồng đồng bộ.

### 3.3. Không phải snapshot iterator

Một collection như `CopyOnWriteArrayList` có iterator **snapshot** theo mảng tại thời điểm tạo iterator: thay đổi sau đó không ảnh hưởng kết quả iterator ấy; `Iterator.remove` của loại snapshot này không được hỗ trợ.

Đó là một chiến lược rất khác với `ConcurrentLinkedQueue`. **`CopyOnWriteArrayList` không phải queue thay thế tương đương**; nhắc tới chỉ để phân biệt kiểu nhất quán.

Nếu yêu cầu nghiệp vụ là “cho tôi toàn bộ danh sách công việc tại thời điểm đóng sổ”, weak iterator **không đáp ứng** điều đó. Hãy định nghĩa một khoảng **quiescence** (ngừng sửa queue), dùng snapshot có phối hợp writer/reader, hoặc một giao thức epoch/version phù hợp.

### 3.4. Nhìn thấy object không đồng nghĩa object immutable

Iterator có thể an toàn để nhận reference tới phần tử, nhưng **object bên trong** có thể vẫn mutable.

```java
final class MutableJob {
    volatile int progress;
}
```

Đây là đoạn minh họa: `volatile` giúp thấy thay đổi trên một trường cụ thể, nhưng không tự tạo snapshot nhất quán của nhiều trường trong object. Nếu thread khác sửa payload trong lúc iterator đọc, app vẫn phải thiết kế synchronization/immutability cho payload.

Thông dụng là tạo **record hoặc immutable DTO** trước khi `offer`, rồi không sửa object sau khi publish.

## 4. Iterator.remove(): được hỗ trợ nhưng không phải transaction

`ConcurrentLinkedQueue` và `LinkedTransferQueue` hỗ trợ thao tác tùy chọn `Iterator.remove()`. Nó có thể loại bỏ phần tử vừa được trả về gần nhất theo hợp đồng iterator.

Ví dụ không có concurrent mutation:

```java
import java.util.Iterator;
import java.util.concurrent.ConcurrentLinkedQueue;

ConcurrentLinkedQueue<String> jobs = new ConcurrentLinkedQueue<>();
jobs.offer("old");
jobs.offer("new");

Iterator<String> it = jobs.iterator();
System.out.println(it.next()); // old
it.remove();                    // Gỡ phần tử vừa thăm.
System.out.println(jobs.contains("old")); // false
```

Ở ví dụ tuần tự này, output là:

```text
old
false
```

Tuy nhiên:

- `remove()` của iterator **không phải** lệnh “xóa mọi phần tử khớp một điều kiện nghiệp vụ”.
- Nếu thread khác đã remove cùng node, việc xóa qua iterator có thể không có tác dụng bổ sung.
- Iterator có thể thấy một phần của các cập nhật đồng thời, nên `iterate + remove` **không** là batch atomic.
- Nếu có phần tử bằng nhau hoặc trùng ID ở queue, việc xóa và kiểm tra riêng lẻ có thể có các race về identity.
- Không dùng iterator làm cơ chế đảm bảo **một job chỉ được claim bởi đúng một worker**. Để claim phần tử head, dùng `poll()` hoặc `take()`.

### 4.1. Đừng tự xóa một phần tử đã xử lý chỉ qua for-each

```java
for (Job job : queue) {
    process(job);
    queue.remove(job);
}
```

Đây là anti-pattern minh họa, với `Job` và `process` do ứng dụng định nghĩa. Trong lúc duyệt, consumer khác có thể đã nhận hoặc xóa job đó, queue có thể có giá trị tương đương, producer có thể thêm job mới và kết quả iteration không phải danh sách công việc được claim ổn định.

**Mẫu xử lý worker thích hợp hơn:**

```java
Job job;
while ((job = queue.poll()) != null) {
    process(job);
}
```

Đây là đoạn phác thảo cho một lần drain tại thời điểm hiện tại. Lệnh `poll` **claim bằng cách lấy ra** một item head cho caller, thay vì chỉ quan sát qua iterator. Nhưng nếu producer tiếp tục thêm sau khi `poll` trả null, vòng này **không** đồng nghĩa queue sẽ mãi trống hoặc dịch vụ đã shutdown. Khi cần consumer chạy lâu dài, dùng blocking `take()` với protocol dừng.

### 4.2. Lấy ra khỏi queue không bảo đảm nghiệp vụ exactly-once

`poll`/`take` xác định **một caller nhận phần tử tại một lần lấy** theo hợp đồng queue, nhưng sau đó caller có thể crash trước khi `process(job)` thành công. Với yêu cầu không mất công việc, cần retry/ack/durable store hoặc giao thức claim trạng thái riêng.

Tránh nói “poll atomic nên toàn bộ nghiệp vụ atomic”. Atomic queue removal không bao gồm database, network request hoặc business transaction.

## 5. Vì sao các thao tác nhiều bước không atomic?

**Thread-safe per operation** không tự mở rộng sang một đoạn code gồm nhiều lời gọi.

Xét:

```java
if (queue.size() < 1) {
    queue.offer(job);
}
```

`size()` là một thao tác; `offer(job)` là thao tác khác. Giữa hai lời gọi, thread khác có thể thay đổi queue. Hai lệnh không được thực thi dưới một transaction chung.

### 5.1. Timeline size → offer gây vượt hạn mức

```text
Giới hạn nghiệp vụ: tối đa 1 phần tử.
Queue ban đầu: []

Thread A                       Thread B
--------                       --------
size() -> 0
                               size() -> 0
0 < 1, điều kiện đúng           0 < 1, điều kiện đúng
offer(A)                       offer(B)

Queue sau hai lời gọi: [A, B]
size() = 2  > giới hạn 1
```

Cả `offer` đều **đúng và thread-safe** đối với `ConcurrentLinkedQueue`, nhưng logic hợp thành **không enforce được hạn mức**.

Vấn đề còn nặng hơn vì với `ConcurrentLinkedQueue` và `LinkedTransferQueue`, `size()` có thể phải duyệt **O(n)** và có thể không chính xác khi queue liên tục thay đổi trong lúc đếm. Vì vậy `size()<LIMIT` không chỉ có race giữa read/write mà còn là metric không phù hợp để điều kiện hóa tính đúng đắn.

### 5.2. Giải pháp: bounded queue enforce capacity ở chính offer

```java
import java.util.concurrent.ArrayBlockingQueue;

ArrayBlockingQueue<String> bounded = new ArrayBlockingQueue<>(1);

boolean first = bounded.offer("A");
boolean second = bounded.offer("B");
```

Trong ví dụ tuần tự, kết quả:

```text
first  = true
second = false
```

Với nhiều producers đồng thời, `ArrayBlockingQueue` vẫn enforce capacity trong chính hoạt động `offer`: nếu capacity 1 đang rỗng và không có consumer, chỉ một trong hai producer có thể thành công. **Không cần và không nên** đọc `size` trước rồi mới quyết định có được thêm hay không.

Với chính sách chờ có giới hạn:

```java
boolean accepted = bounded.offer(
        job, 250, TimeUnit.MILLISECONDS);
```

Đây là đoạn minh họa trong phương thức xử lý `InterruptedException`; `job` phải đúng kiểu queue và đã khởi tạo, `TimeUnit` cần import. Timed `offer` có thể đợi **có chỗ trống**, khác với `TransferQueue.tryTransfer` đợi **consumer nhận trực tiếp**.

### 5.3. Với queue unbounded, dùng quota/permit nếu cần

Nếu bắt buộc dùng `ConcurrentLinkedQueue`, muốn giới hạn số phần tử bằng permit, có thể đặt một `Semaphore` trước bước enqueue. Đây không phải lệnh thay thế `ArrayBlockingQueue` đơn giản: ứng dụng phải đảm bảo **release permit đúng một lần** khi item thực sự rời queue và xử lý các đường exception/shutdown/retry.

Phác thảo:

```java
if (permits.tryAcquire()) {
    boolean stored = queue.offer(job);
    if (!stored) {
        permits.release();
    }
} else {
    onCapacityReached(job);
}
```

Đây là **code minh họa**, không độc lập: `permits`, `queue`, `job`, `onCapacityReached` do ứng dụng định nghĩa. `ConcurrentLinkedQueue.offer` cho phần tử hợp lệ thường luôn thành công, nhưng release trong nhánh thất bại thể hiện nguyên tắc cleanup. Trong production, nếu offer ném unchecked exception, cần xử lý hoàn trả permit; nếu consumer lấy ra, phải release đúng một lần; nếu retry job, đừng cấp trùng permit.

Nếu không cần đặc tính khác của queue, **`ArrayBlockingQueue`/bounded `LinkedBlockingQueue` đơn giản hơn** để enforce capacity.

### 5.4. Không dùng queue.size() làm bộ đếm sự kiện nghiệp vụ

Nếu cần đếm số jobs đã nhận/hoàn thành, dùng metric được tăng giảm tại **điểm state transition** với logic phù hợp, không suy lượng công việc đã xử lý từ queue size. `LongAdder` phù hợp với **metrics thống kê** có concurrency cao, nhưng bản thân một `LongAdder` cộng với thao tác queue riêng lẻ **không biến hai operation thành transaction**.

## 6. check-then-act: peek → poll có thể trả hai phần tử khác nhau

`peek()` chỉ **quan sát** head mà không remove. `poll()` lấy và remove một head ở thời điểm **sau đó**. Nếu thread khác lấy head ở giữa, kết quả khác nhau là hoàn toàn hợp lệ.

Ví dụ timeline:

```text
Queue đầu: [A]

Thread 1                         Thread 2
--------                         --------
peek() -> A
                                 poll() -> A
                                 offer(B)
poll() -> B

Thread 1 quan sát A nhưng thực sự lấy B.
```

**Sai:**

```java
String observed = queue.peek();
if (observed != null) {
    String claimed = queue.poll();
    useAsIfSame(observed, claimed);
}
```

Đây là đoạn minh họa có hàm `useAsIfSame` do ứng dụng định nghĩa. Không có ràng buộc atomic rằng `observed == claimed`; `claimed` còn có thể là `null`.

**Đúng khi muốn lấy và làm việc với đúng phần tử:**

```java
String claimed = queue.poll();
if (claimed != null) {
    process(claimed);
}
```

Đây là code minh họa; xử lý dựa trên **giá trị mà `poll` thực sự trả**, không dựa trên một lần `peek` trước đó.

### 6.1. Một phần tử không được trao hai lần bởi hai poll đồng thời

Với `ConcurrentLinkedQueue` có một phần tử 42, hai consumers cùng `poll`:

- Một lời gọi có thể nhận 42.
- Lời gọi còn lại có thể nhận `null` nếu không có producer thêm phần tử khác.
- Cả hai không được claim **cùng node** 42 qua các thao tác poll như một thành công hai lần.

**Điều này không có nghĩa consumer nào chắc chắn thắng**, và không bảo đảm toàn bộ quá trình xử lý nghiệp vụ đúng một lần.

### 6.2. Nếu mục tiêu là “kiểm tra rồi xóa khi đúng trạng thái”

Một đoạn như:

```java
if (queue.contains(job)) {
    queue.remove(job);
}
```

cũng có check-then-act race. Với một giá trị cụ thể, `queue.remove(job)` là một lời gọi có boolean kết quả: có thể gọi trực tiếp, nhưng nó **không giải quyết** bài toán điều kiện nghiệp vụ phức tạp hoặc atomic compare-and-delete với state bên ngoài.

Nếu cần atomically “chỉ xóa khi job còn ở trạng thái PENDING” và cập nhật một map/DB, hãy đặt logic đó ở cấu trúc có primitive atomic thích hợp (ví dụ `ConcurrentHashMap.computeIfPresent` cho **một key trong map**), hoặc transaction tại tầng lưu trữ. Queue không tự thực hiện một commit across resources.

## 7. Iterator và những phép toán bulk: cẩn thận với ảnh chụp tưởng tượng

Java cung cấp các phương thức thuận tiện:

```java
queue.forEach(this::inspect);
queue.removeIf(this::expired);
queue.addAll(batch);
Object[] copied = queue.toArray();
```

Đây là đoạn code phác thảo **không độc lập**, có `this::inspect`/`this::expired` và `batch` do ứng dụng định nghĩa.

Theo Javadoc của `ConcurrentLinkedQueue` và `LinkedTransferQueue`, những thao tác **thêm, xóa hoặc xem xét nhiều phần tử**, ví dụ `addAll`, `removeIf` hay `forEach`, **không được bảo đảm nguyên tử so với các thao tác đồng thời khác**.

### 7.1. addAll không phải publish một batch như một transaction

Nếu thread A gọi `queue.addAll(List.of(A,B,C))` trong khi thread B duyệt `forEach`, B có thể nhìn thấy **một phần** các item mới thay vì cả bộ A/B/C.

Nếu logic downstream yêu cầu “nhìn thấy cả lô hoặc không nhìn thấy gì”, không thể thay thế transaction bằng một lệnh `addAll` trên concurrent queue. Có thể đóng gói **cả batch thành một immutable object** rồi `offer(batch)`, hoặc dùng giai đoạn commit riêng.

### 7.2. removeIf không bảo đảm toàn queue được làm sạch tại một thời điểm

`queue.removeIf(predicate)` có thể hữu ích để best-effort cleanup, nhưng nếu producer vẫn liên tục thêm những phần tử khớp predicate, không có đảm bảo rằng sau khi method kết thúc **không còn bất kỳ item khớp nào**.

Ví dụ: task mới được thêm **ngay sau** khi iterator đã duyệt qua vị trí tương ứng. Lệnh removeIf hoàn tất vẫn không chứng minh predicate là false cho mọi phần tử hiện có tại một thời điểm chung.

Đối với correctness, hãy quản lý validity của mỗi job **khi được consumer claim**, ví dụ kiểm tra deadline/version/trạng thái hiện hành trước khi thực thi, thay vì kỳ vọng một vòng removeIf tạo hàng rào tuyệt đối.

### 7.3. forEach cũng là phép duyệt nhất quán yếu

`forEach` của concurrent queue không khóa writers để tạo một snapshot. Dùng cho telemetry/debug best-effort hợp lý; không dùng làm **audit cuối ngày chính xác** khi queue đang thay đổi.

Tránh đặt một hàm tác động mạng/database chậm và có side effect bên trong `forEach` rồi coi kết quả là một batch transaction. Nếu việc inspect yêu cầu ack/rollback, hãy tách dữ liệu và protocol rõ.

### 7.4. toArray có tạo snapshot không?

Sau khi `toArray()` **đã trả về**, mảng là một cấu trúc **riêng**, nên thêm phần tử vào queue **sau đó** không tự làm mảng thay đổi. Nhưng nếu các thread khác **đang sửa queue trong khi `toArray` chạy**, kết quả vẫn không được bảo đảm là một snapshot **atomic tại một thời điểm**.

Phân biệt:

- **Bản copy tĩnh sau lời gọi hoàn tất**: đúng, các slot trong mảng là bản sao reference đã lấy.
- **Snapshot tuyến tính hóa của toàn queue ngay giữa concurrent mutations**: **không tự bảo đảm**.
- **Object được trỏ tới bởi slot mảng là immutable**: không, phụ thuộc kiểu payload.

Nếu cần dữ liệu chính xác, phải điều phối để writers/consumers tạm ngưng trong khoảng snapshot, hoặc sử dụng thiết kế state/version phù hợp.

### 7.5. Stream và spliterator không cho phép “đóng băng” queue

Với `ConcurrentLinkedQueue`, `spliterator()` cũng có đặc tính **weakly consistent** và báo `CONCURRENT`, `ORDERED`, `NONNULL` theo Javadoc.

Điều đó giúp một số thao tác stream duyệt queue khi có concurrent writers, nhưng **không tạo transaction hoặc snapshot toàn queue**. `parallelStream()` không phải một cách “tự động atomic hóa” phép tính tổng/đếm trên queue đang thay đổi.

Nếu báo cáo cần số liệu chính xác, xác định event-time cutoff, nguồn dữ liệu đã commit và quy trình snapshot/aggregation chuyên biệt.

### 7.6. Thứ tự ưu tiên không phải thứ tự iterator

`PriorityBlockingQueue` có priority semantics khi **lấy phần tử** qua `poll/take`, nhưng **iterator của nó không cam kết thứ tự đặc biệt**. Nếu muốn duyệt theo priority trên một bản dữ liệu ổn định, cần tạo copy phù hợp và sort với comparator; nếu vẫn có producer concurrent, việc lấy mẫu không phải một global snapshot atomic.

Không dùng thứ tự duyệt để suy ra worker chắc chắn sẽ xử lý công việc theo thứ tự đó.

## 8. Khi nào nên dùng iterator? Khi nào nên dùng poll/take?

| Mục tiêu | API/thiết kế phù hợp | Tránh |
| --- | --- | --- |
| Dashboard xem mẫu công việc đang chờ | `iterator`/`forEach` best-effort | Nói là exact snapshot khi vẫn có writer |
| Thống kê approximate | Metrics riêng, sampled iteration nếu chấp nhận sai số | Đếm bằng duyệt rồi dùng làm invariant |
| Consumer thực sự nhận công việc | `poll()`/`take()` | Lặp iterator rồi gọi `process` như đã claim |
| Giới hạn queue tối đa N | `ArrayBlockingQueue(N)`, bounded `LinkedBlockingQueue` | `if(size<N) offer` |
| Xóa một phần tử cụ thể | `remove(x)`, kiểm tra boolean | `contains(x)` rồi `remove(x)` coi là atomic |
| Kiểm tra và nhận phần tử head | `poll()` rồi dùng giá trị trả | `peek()` rồi `poll()` coi bằng nhau |
| Gửi batch như một đơn vị | `offer(immutableBatch)` hoặc transaction tầng cao | `addAll` rồi kỳ vọng all-or-nothing visibility |
| Cần point-in-time snapshot thực | Phối hợp writers/consumers, snapshot có ranh giới | Weak iterator đang chạy giữa mutations |
| Xóa item expired | Kiểm tra deadline/version khi claim, cleanup phụ trợ | `removeIf` như hàng rào chặn mọi expired item |
| Xử lý exactly-once nghiệp vụ | Message identity + durable claim/ack/idempotency | Tin rằng poll atomic đồng nghĩa xử lý exactly-once |

### 8.1. Dùng poll trong vòng chỉ là một lần drain

```java
E item;
while ((item = queue.poll()) != null) {
    consume(item);
}
```

Đây là code khái niệm với `E`, `queue`, `consume` cần được khai báo trong scope Java. Khi `poll()` trả `null`, chỉ biết **ở thời điểm lời gọi đó không lấy được item**. Producer có thể `offer` một item mới ngay sau đó.

Nếu muốn consumer phục vụ lâu dài, sử dụng `BlockingQueue.take()`/timed `poll()` theo shutdown policy, không coi một lần drain thấy rỗng là điều kiện kết thúc toàn hệ thống.

### 8.2. Khi muốn snapshot để báo cáo

Một thiết kế có thể:

1. Coordinator ngừng nhận work mới hoặc cho producer chuyển sang queue khác.
2. Chờ các producer/consumer đang xử lý batch hiện tại đạt **điểm quiescence**.
3. Copy nội dung queue hoặc state chứa phiên bản commit.
4. Phát hành snapshot immutable cho thread báo cáo.
5. Tiếp tục producers/consumers.

Chỉ đặt một `synchronized(queue)` quanh vòng duyệt **không đủ** nếu các thread khác vẫn gọi `queue.offer/poll` mà **không cùng giữ lock đó**. Các concurrent queue tự tổ chức synchronization bên trong chứ không tự sử dụng monitor của application làm một transaction ngoài.

### 8.3. Không cần tạm dừng hệ thống cho mọi dashboard

Một dashboard chỉ cần trạng thái gần đúng có thể dùng weak iterator và số đo approximate. Điểm quan trọng là **ghi rõ semantics**: “đây là quan sát best-effort”, không coi đó là danh sách chứng thực chính xác cho billing, audit hoặc hạn mức an toàn.

## 9. Thread-safety và memory visibility

Các concurrent collections của Java có các cam kết **memory consistency**. Với `ConcurrentLinkedQueue`, một thread tạo object, chuẩn bị các trường rồi đặt vào queue; những hành động **trước khi đặt object** *happen-before* những hành động **sau khi thread khác truy cập hoặc gỡ** phần tử tương ứng khỏi queue.

Ví dụ:

```java
record Job(long id, String description) {}

ConcurrentLinkedQueue<Job> pending = new ConcurrentLinkedQueue<>();
pending.offer(new Job(101L, "rebuild-index"));

Job received = pending.poll();
if (received != null) {
    System.out.println(received.description());
}
```

Đây là đoạn minh họa có thể chạy trong phương thức Java 17. Trong tình huống không có thread khác cạnh tranh, output:

```text
rebuild-index
```

**Lưu ý:**

- `Job` dạng `record` giữ payload immutable theo cấu trúc ví dụ này, dễ chuyển ownership giữa threads.
- Happen-before giúp publish object đã khởi tạo, nhưng nếu producer sửa mutable payload **sau khi enqueuing**, cần synchronization cho những sửa đổi đó.
- Weak iterator có thể nhìn thấy một object an toàn theo memory visibility, nhưng **số object được nhìn thấy** vẫn không phải snapshot atomic.
- Nếu message có side effect ở database, memory visibility của queue không đồng nghĩa transaction database committed.

### 9.1. Phân biệt ba cấp độ bảo đảm

1. **Thread safety của một thao tác queue**: phương thức được triển khai để concurrent calls không phá vỡ cấu trúc dữ liệu.
2. **Atomicity của nhiều thao tác**: `size→offer`, `peek→poll` và `iterate→remove` **không tự trở thành một transaction**.
3. **Business correctness**: nội dung message, ack, persistence, retry, idempotency còn thuộc giao thức tầng ứng dụng.

Một API có thể đạt cấp độ 1 nhưng không tự cấp độ 2 hoặc 3.

### 9.2. Queue không phải nguồn dữ liệu audit bền vững

`ConcurrentLinkedQueue`/`LinkedTransferQueue` giữ dữ liệu **trong JVM memory**. Nếu process crash, kết quả iterator trước crash không tạo ra log có khả năng khôi phục hoặc bảo đảm exactly-once.

Với billing hay event processing có SLA bền vững, cần durable store, checkpoint/version và idempotent consumers — không dùng weak iterator làm bằng chứng “mọi job đã được xử lý”.

## 10. Chương trình Java 17+ hoàn chỉnh: kiểm thử race có kiểm soát

Tạo file **`WeakIteratorAndCompoundActionsDemo.java`**. Chương trình thực thi các kiểm tra độc lập:

1. `ConcurrentLinkedQueue<Integer>` có các phần tử 0..99. Tạo iterator và lấy phần tử đầu, **sau đó** một worker xóa 0..49 và thêm 100..199. Duyệt phần còn lại, xác minh không gặp `ConcurrentModificationException`, không có giá trị ngoài domain hoặc bản sao cùng ID; **không assert một danh sách iterator chính xác**, vì lịch sửa đồng thời có thể thay đổi điều quan sát. Sau khi worker hoàn tất, kiểm tra final queue đúng 50..199.
2. Dùng `CyclicBarrier(2)` để buộc hai producer **đều đọc `size()<1` khi queue rỗng** trước khi được phép `offer`. Kết quả final queue có **2 phần tử**, chứng minh compound check/act không enforce capacity.
3. Dùng cùng kỹ thuật với `ArrayBlockingQueue(1)`; hai producers thử `offer` khi không có consumer: **chỉ một thành công**, queue có đúng 1 item.
4. Dùng `CountDownLatch` buộc một worker `peek` thấy "A"; một thread khác `poll` lấy "A" rồi `offer` "B"; worker đầu gọi `poll` và nhận "B". Không có phỏng đoán scheduler.
5. Hai consumers gọi `poll()` gần đồng thời trên queue chỉ có 42; một consumer lấy 42, consumer còn lại nhận `null`.
6. Copy `toArray` sau khi queue chỉ có "old"; thêm "new" **sau khi copy hoàn tất** và xác minh mảng đã trả về không tự thay đổi.
7. Trong trường hợp không có concurrent mutation, dùng `ConcurrentLinkedQueue.iterator().remove()` xóa phần tử vừa duyệt và xác minh phần tử mới vẫn còn.
8. Shutdown executor do demo sở hữu, chờ kết thúc.

**Kết quả có tính xác định ở cấp độ invariants.** Chương trình không đo xem iterator thấy bao nhiêu item, thread nào thắng `offer`, hay consumer nào lấy 42: những chi tiết đó **không cần và không thể hứa**. Test dùng synchronization để thiết lập mốc trước/sau thay vì bắt một interleaving may rủi.

### 10.1. Mã đầy đủ: WeakIteratorAndCompoundActionsDemo.java

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ConcurrentLinkedQueue;

public final class WeakIteratorAndCompoundActionsDemo {
    private static void check(boolean ok, String why) {
        if (!ok) throw new AssertionError(why);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        try {
            ConcurrentLinkedQueue<Integer> queue = new ConcurrentLinkedQueue<>();
            for (int i = 0; i < 100; i++) queue.offer(i);
            Iterator<Integer> iterator = queue.iterator();
            Integer first = iterator.next();
            check(first == 0, "unexpected first entry");
            Future<?> changing = pool.submit(() -> {
                for (int i = 0; i < 50; i++) {
                    check(queue.remove(i), "initial element missing");
                }
                for (int i = 100; i < 200; i++) queue.offer(i);
            });
            changing.get(5, TimeUnit.SECONDS);

            Set<Integer> visited = new HashSet<>();
            visited.add(first);
            while (iterator.hasNext()) {
                Integer item = iterator.next();
                check(item >= 0 && item < 200,
                        "unexpected item value");
                check(visited.add(item),
                        "duplicate item in iterator");
            }
            check(queue.size() == 150, "final queue size");
            for (int i = 0; i < 50; i++) {
                check(!queue.contains(i), "removed item remained");
            }
            for (int i = 50; i < 200; i++) {
                check(queue.contains(i), "expected item missing");
            }
            System.out.println("weak iterator during writes = PASS");
            System.out.println("final queue state = PASS");

            ConcurrentLinkedQueue<Integer> race = new ConcurrentLinkedQueue<>();
            CyclicBarrier checkBarrier = new CyclicBarrier(2);
            Future<?> addOne = pool.submit(() -> {
                if (race.size() < 1) {
                    checkBarrier.await(5, TimeUnit.SECONDS);
                    race.offer(1);
                }
                return null;
            });
            Future<?> addTwo = pool.submit(() -> {
                if (race.size() < 1) {
                    checkBarrier.await(5, TimeUnit.SECONDS);
                    race.offer(2);
                }
                return null;
            });
            addOne.get(5, TimeUnit.SECONDS);
            addTwo.get(5, TimeUnit.SECONDS);
            check(race.size() == 2, "size check race not observed");
            System.out.println(
                    "size-check then offer exceeded limit = true");

            ArrayBlockingQueue<Integer> bounded = new ArrayBlockingQueue<>(1);
            CyclicBarrier offerBarrier = new CyclicBarrier(2);
            Future<Boolean> offerOne = pool.submit(() -> {
                offerBarrier.await(5, TimeUnit.SECONDS);
                return bounded.offer(1);
            });
            Future<Boolean> offerTwo = pool.submit(() -> {
                offerBarrier.await(5, TimeUnit.SECONDS);
                return bounded.offer(2);
            });
            boolean one = offerOne.get(5, TimeUnit.SECONDS);
            boolean two = offerTwo.get(5, TimeUnit.SECONDS);
            check(one != two && bounded.size() == 1,
                    "bounded offer must allow one");
            System.out.println(
                    "bounded queue enforced capacity = true");

            ConcurrentLinkedQueue<String> checkThenAct =
                    new ConcurrentLinkedQueue<>();
            checkThenAct.offer("A");
            CountDownLatch peekComplete = new CountDownLatch(1);
            CountDownLatch allowPoll = new CountDownLatch(1);
            Future<String> observer = pool.submit(() -> {
                String peeked = checkThenAct.peek();
                peekComplete.countDown();
                check(allowPoll.await(5, TimeUnit.SECONDS),
                        "poll release");
                return peeked + "->" + checkThenAct.poll();
            });
            check(peekComplete.await(5, TimeUnit.SECONDS),
                    "observer did not peek");
            check("A".equals(checkThenAct.poll()),
                    "other consumer");
            checkThenAct.offer("B");
            allowPoll.countDown();
            check("A->B".equals(observer.get(5, TimeUnit.SECONDS)),
                    "peek and poll should be independent operations");
            System.out.println(
                    "peek and later poll can differ = true");

            ConcurrentLinkedQueue<Integer> single =
                    new ConcurrentLinkedQueue<>();
            single.offer(42);
            CyclicBarrier consumers = new CyclicBarrier(2);
            Future<Integer> popA = pool.submit(() -> {
                consumers.await(5, TimeUnit.SECONDS);
                return single.poll();
            });
            Future<Integer> popB = pool.submit(() -> {
                consumers.await(5, TimeUnit.SECONDS);
                return single.poll();
            });
            Integer a = popA.get(5, TimeUnit.SECONDS);
            Integer b = popB.get(5, TimeUnit.SECONDS);
            check((a == null && Integer.valueOf(42).equals(b))
                    || (b == null && Integer.valueOf(42).equals(a)),
                    "poll must claim the item once");
            System.out.println(
                    "atomic poll gives one winner = true");

            ConcurrentLinkedQueue<String> copySource =
                    new ConcurrentLinkedQueue<>();
            copySource.offer("old");
            Object[] stableCopy = copySource.toArray();
            copySource.offer("new");
            check(Arrays.equals(stableCopy, new Object[] {"old"}),
                    "copy should not change after return");
            System.out.println(
                    "completed array copy independent = true");

            Iterator<String> removable = copySource.iterator();
            check("old".equals(removable.next()), "iterator first");
            removable.remove();
            check(!copySource.contains("old")
                            && copySource.contains("new"),
                    "iterator.remove should remove last visited element");
            System.out.println("iterator.remove supported = true");
            System.out.println("checks = PASS");
        } finally {
            pool.shutdownNow();
            check(pool.awaitTermination(5, TimeUnit.SECONDS),
                    "pool did not terminate");
        }
        System.out.println("pool terminated = true");
    }
}
```

### 10.2. Lệnh biên dịch và chạy

Lưu file đúng tên class và chạy JDK 17+:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 WeakIteratorAndCompoundActionsDemo.java
java WeakIteratorAndCompoundActionsDemo
```

**Stdout chính xác của lượt chạy kiểm thử thực tế trên JDK 17:**

```text
weak iterator during writes = PASS
final queue state = PASS
size-check then offer exceeded limit = true
bounded queue enforced capacity = true
peek and later poll can differ = true
atomic poll gives one winner = true
completed array copy independent = true
iterator.remove supported = true
checks = PASS
pool terminated = true
```

Đã biên dịch không có warning bằng `-Xlint:all -Werror` và chạy thành công. Các lời gọi `Future.get(5,TimeUnit.SECONDS)`/`CyclicBarrier.await` có deadline để test phát hiện worker không tiến triển. Nếu máy quá tải hoặc thread pool không thể được tạo, test có thể thất bại do môi trường; không được lén xem đó là PASS.

### 10.3. Vì sao test iterator không assert danh sách đã duyệt?

Vòng duyệt bắt đầu từ queue có 0..99, nhưng có concurrent changes. Chương trình chỉ assert:

- Phần tử đầu tiên trước mutation là 0, theo FIFO của queue khi chưa có writer.
- Mọi giá trị được duyệt thuộc domain được test tạo.
- Không có duplicate ID trong vòng duyệt của test.
- Không ném `ConcurrentModificationException`.
- Sau khi worker mutation hoàn tất, queue **thực tế** chứa 50..199, 150 phần tử.

Nếu test đòi iterator phải trả chính xác `0..99` hay `50..199`, nó sẽ gắn vào một tình cờ scheduling thay vì hợp đồng weak consistency. Bài học là **điều cần assert phụ thuộc contract**, không phụ thuộc output của một lần chạy cụ thể.

### 10.4. Vì sao CyclicBarrier giúp chứng minh race?

Hai producer đều chạy:

```java
if (race.size() < 1) {
    checkBarrier.await(5, TimeUnit.SECONDS);
    race.offer(value);
}
```

Đây là đoạn minh họa lấy từ chương trình đầy đủ, với `race`, `checkBarrier`, `value` có scope tương ứng. Barrier khiến **cả hai đã vượt qua điều kiện `size()<1`** trước khi một producer được phép `offer`. Vì thế queue chắc chắn nhận cả hai item nếu không có consumer. Đây là test xác thực **race của logic hợp thành**, không phải bug bên trong `ConcurrentLinkedQueue`.

### 10.5. Tại sao ArrayBlockingQueue(1) giải quyết được?

Cả hai producer có thể gọi `bounded.offer` cùng lúc, nhưng queue có capacity 1 được enforce trong **chính thao tác thêm**. Một lời gọi nhận true, một nhận false; ứng dụng phải **xử lý false** (backpressure, retry hoặc reject) theo chính sách.

Không cần canh `size()==0` rồi mới thêm. Điều này chuyển invariant về nơi có primitive đồng bộ đúng.

### 10.6. Tại sao peek và poll cho kết quả khác nhau?

Test dùng latch bắt buộc thứ tự: observer `peek` thấy "A"; main `poll` lấy "A" và thêm "B"; observer mới được phép `poll`. Vì vậy chuỗi `"A->B"` là kết quả **cố ý** để thấy hai method không tạo một transaction. Không dùng `peek` để quyết định chắc chắn item nào sẽ được claim.

### 10.7. Vì sao poll chỉ có một winner?

Khi queue chứa duy nhất 42 và không có producer, hai lời gọi `poll` đồng thời không thể trả cùng node 42 cho cả hai. Test chỉ assert “một trả 42, một trả null”, **không assert consumer A hay B thắng**. Đây là điều kiện đúng của single-operation removal.

### 10.8. Vì sao toArray được coi là copy nhưng không phải snapshot concurrent?

Trong test, `toArray` hoàn tất **trước khi** main `offer("new")`, nên array không đổi là hiển nhiên. Test **không** khẳng định nếu có writer sửa queue **trong suốt lúc toArray chạy** thì mảng thu được là snapshot atomic của một thời điểm.

Đây chính là ranh giới cần ghi nhớ trong production reporting.

### 10.9. Vì sao iterator.remove được test lúc không có writer?

Mục tiêu là xác nhận **API iterator hỗ trợ remove**, không đánh lừa rằng operation trên iterator là atomic với một luồng xóa/chèn khác. Với writer đang chạy, thời điểm và mục tiêu xóa có thể phải xét theo identity/state của phần tử; mọi yêu cầu business cần protocol mạnh hơn.

## 11. Kỹ thuật kiểm thử và quan sát chuẩn

### 11.1. Không dùng Thread.sleep để “chứng minh” race

Viết:

```java
Thread.sleep(10);
queue.offer(item);
```

không bảo đảm hai thread sẽ xen kẽ chính xác theo ý định. Thời gian scheduler/JIT/GC/CPU khác nhau giữa CI và laptop. `Thread.sleep` có thể hữu ích để tạo khoảng nghỉ trong **test poll có deadline**, nhưng không phải công cụ tạo mốc happens-before rõ ràng.

Dùng `CountDownLatch`, `CyclicBarrier`, `Phaser` hoặc các primitive đồng bộ khác để cưỡng bức thứ tự có thể kiểm chứng. Và **test không nên có kết quả phụ thuộc thứ tự winner**, trừ khi thứ tự đó đã được điều phối.

### 11.2. Stress test bổ sung

Một vòng stress test với nhiều producer/consumer có thể đếm:

- Tổng số message IDs được producer `offer` thành công.
- Tổng số IDs được consumer `poll/take`.
- IDs bị trùng, thiếu, hỏng hoặc xử lý nhiều lần.
- Thời điểm shutdown, số message còn pending và số message đang xử lý.
- p95/p99 thời gian claim, queue throughput, producer/consumer imbalance.
- Số lần thao tác `offer` bị từ chối bởi capacity.
- Những sai khác do snapshot best-effort **không phải** khẳng định mất message.

Dùng unique ID và tập result thread-safe để kiểm tra dữ liệu **được claim**, không suy correctness từ một iterator giám sát queue trong lúc stress test.

### 11.3. Không áp dụng assertion quá mạnh cho weak iterator

Một test sai:

```java
Iterator<Job> it = queue.iterator();
// Sau đó producer thêm 100 jobs.
assertCountExactly100(it); // Sai nếu đòi iterator phải thấy tất cả jobs mới.
```

Đây là code phác thảo minh họa, không độc lập. Vì iterator có thể không thấy toàn bộ cập nhật đồng thời, count exact sẽ biến một ứng dụng đúng thành test flaky.

Một test đúng nên tập trung **không xảy ra corruption/CME**, mọi giá trị trong domain và những invariant mà Javadoc cụ thể cam kết. Nếu cần snapshot exact, phải **đổi thiết kế kiểm thử và đồng bộ hệ thống**, không ép iterator cung cấp điều chưa được hứa.

## 12. Các sai lầm thường gặp

| Sai lầm | Vấn đề thực sự | Cách sửa |
| --- | --- | --- |
| “Concurrent queue thì iterator là snapshot” | Weakly consistent không phải snapshot | Chỉ dùng best-effort hoặc tạo snapshot có phối hợp |
| “Iterator luôn thấy mọi phần tử mới” | Concurrent additions có thể không được thấy | Không dùng để exact counting |
| “Không có ConcurrentModificationException nghĩa là atomic” | Chỉ nói về traversal contract | Tách traversal và transaction |
| “Duyệt rồi process là đã claim job” | Iterator chỉ quan sát | Dùng `poll/take` |
| “Một vòng for-each liệt kê mọi pending job tại 12:00” | Có concurrent mutations | Quiescence, epoch/version, durable snapshot |
| “queue.size() là constant-time” | CLQ/LTQ size có thể O(n) | Tránh trong hot path |
| “size()<N rồi offer luôn giữ N” | Check-then-act race | Bounded queue hoặc atomic quota |
| “isEmpty() true nên poll chắc chắn null” | Producer có thể thêm giữa hai lệnh | Tin vào kết quả poll |
| “peek rồi poll chắc chắn cùng item” | Consumer khác có thể lấy trước | Poll trực tiếp và dùng return |
| “contains rồi remove là compare-and-delete atomic” | Hai operation khác nhau | Remove trực tiếp hoặc state primitive phù hợp |
| “removeIf sẽ quét sạch tất cả item expired tại một thời điểm” | Bulk operation không atomic với writer | Validate khi claim + cleanup phụ trợ |
| “addAll đăng ký một batch all-or-nothing” | Reader có thể thấy một phần batch | Đóng batch trong một object hoặc transaction |
| “toArray luôn là snapshot atomic khi có writer” | Copy không đồng nghĩa linearization | Phối hợp writer và snapshot |
| “forEach an toàn nên có thể billing trực tiếp” | Không có fixed membership set | Audit source riêng |
| “iterator.remove không được hỗ trợ vì concurrent” | CLQ/LTQ có hỗ trợ | Dùng khi semantics đủ, không cho business claim |
| “Số item trong queue bằng số task chưa hoàn tất” | Item đã poll có thể đang xử lý | Theo dõi inflight + pending |
| “poll atomic thì processing exactly-once” | Consumer có thể crash sau poll | Ack/idempotency/durability |
| “Queue thread-safe nên payload mutable tự an toàn” | Object vẫn có data race | Immutable DTO/ownership |
| “ArrayBlockingQueue vẫn cần size check trước offer” | Capacity enforced bởi offer | Gọi offer và xử lý boolean |
| “SynchronousQueue có backlog để duyệt” | Zero-capacity handoff | Không dùng làm pending list |
| “PriorityBlockingQueue iterator cho priority order” | Iterator không ordered theo priority | Poll/drain có điều phối, hoặc sort snapshot |
| “Một synchronized(queue) ở reader là đủ” | Writers không giữ chung lock | Cùng lock cho mọi bên hoặc đổi kiến trúc |
| “Snapshot mỗi giây đủ để chứng minh không mất job” | Có thể bỏ sót giữa hai lần lấy mẫu | Counter/ack log theo state transitions |
| “Không có CME nghĩa dữ liệu business không bị sửa” | CME chỉ liên quan cấu trúc traversal | Đồng bộ payload riêng |
| “parallelStream tự đóng băng queue” | Spliterator vẫn weakly consistent | Không dùng cho exact audit |
| “Không cần tắt producer khi shutdown worker” | Có thể xuất hiện jobs sau lần drain | Quản lý lifecycle/stopping gate |
| “Một test stress pass là chứng minh mọi interleaving đúng” | Stress không bao phủ mọi lịch | Kết hợp deterministic race tests |
| “Bỏ qua offer false của bounded queue” | Job có thể bị từ chối | Retry/reject/fallback có trách nhiệm |

## 13. Bài tập tự luyện kèm đáp án

### Bài 1 — Định nghĩa

Iterator của `ConcurrentLinkedQueue` được gọi là **weakly consistent**. Điều đó có nghĩa nó trả snapshot tại thời điểm tạo hay không?

**Đáp án:** Không. Nó có thể phản ánh một phần thay đổi trong lúc duyệt, không tự khóa writers và không ném `ConcurrentModificationException` do concurrent structural changes.

### Bài 2 — Số item mới

Iterator được tạo trước khi producer thêm 20 phần tử. Có cam kết iterator sẽ trả đủ cả 20 phần tử mới đó không?

**Đáp án:** Không. Các thêm mới có thể được nhìn thấy hoặc không tùy tiến trình duyệt và implementation. Muốn số lượng chính xác cần điều phối trạng thái.

### Bài 3 — ConcurrentModificationException

Một iterator CLQ duyệt khi thread khác liên tục `offer/poll`. Không xuất hiện CME có chứng minh queue đang bất biến không?

**Đáp án:** Không. Đây là đặc điểm hợp đồng weak iteration, không phải bằng chứng không có write.

### Bài 4 — Fail-fast vs weak

`ArrayList.iterator` và `ConcurrentLinkedQueue.iterator` khác nhau chủ yếu ở đâu?

**Đáp án:** ArrayList iterator fail-fast best-effort khi thay đổi cấu trúc không đúng cách; CLQ iterator weakly consistent, có thể tiếp tục khi queue bị sửa đồng thời. Cả hai không phải point-in-time snapshot cho một hệ thống có concurrent writers.

### Bài 5 — Check-then-act

Hai producers đều thực hiện `if(queue.size()<1) queue.offer(job)` trên CLQ rỗng. Queue có thể có 2 phần tử không?

**Đáp án:** Có. Cả hai có thể đọc size 0 rồi cùng offer. Chúng là hai operation riêng không có transaction.

### Bài 6 — Capacity thật

Muốn tối đa một item pending trong queue, dùng cấu trúc nào dễ enforce hơn `size` check?

**Đáp án:** `ArrayBlockingQueue<>(1)` hoặc `LinkedBlockingQueue<>(1)`, gọi `offer` và xử lý true/false. Capacity được kiểm tra trong chính thao tác thêm.

### Bài 7 — peek/poll

Worker A thấy `peek()=="A"`. Worker B poll A và offer B. Worker A gọi `poll`. Có thể lấy B không?

**Đáp án:** Có. `peek` không đặt chỗ giữ item cho caller; `poll` là operation tại thời điểm sau.

### Bài 8 — Claim công việc

Nên xử lý job bằng vòng `for-each` trên CLQ hay vòng `poll`?

**Đáp án:** Nếu muốn mỗi consumer **claim/remove** một phần tử để xử lý, dùng `poll` hoặc `take` trên blocking queue. Iterator phù hợp quan sát best-effort.

### Bài 9 — removeIf

Producer vẫn thêm jobs expired trong lúc thread khác gọi `removeIf(Job::expired)`. Sau removeIf return có chắc queue không còn expired jobs không?

**Đáp án:** Không. Đây là bulk operation không được bảo đảm atomic với concurrent updates; producer có thể thêm trong hoặc sau lượt quét.

### Bài 10 — addAll

Producer `addAll(List.of(A,B,C))`. Một iterator đang chạy có thể chỉ thấy A và B không?

**Đáp án:** Có thể, vì addAll không bảo đảm all-or-nothing visibility khi concurrent traversal. Nếu batch phải atomic ở mức nghiệp vụ, chuyển cả batch như một message hoặc có transaction.

### Bài 11 — size complexity

Vì sao không gọi `ConcurrentLinkedQueue.size()` trên mỗi request để kiểm tra quota?

**Đáp án:** `size` phải duyệt O(n), có thể không chính xác khi concurrent changes, và check+offer không atomic. Dùng bounded queue/quota đồng bộ thay thế.

### Bài 12 — toArray

`Object[] copy = queue.toArray()`; sau khi method trả, queue được thêm item. Array copy tự xuất hiện item mới không?

**Đáp án:** Không. Mảng riêng ổn định về phần tử được copy. Nhưng nếu queue thay đổi **trong khi** toArray chạy, không được suy đó là atomic snapshot tại một thời điểm.

### Bài 13 — Iterator.remove

`ConcurrentLinkedQueue.iterator().remove()` có được hỗ trợ không, và nó có phải giao thức exactly-once job claim không?

**Đáp án:** Có hỗ trợ optional iterator.remove, nhưng **không** là transaction business/claim với các worker khác. Để claim, dùng poll/take và state ack riêng.

### Bài 14 — Ưu tiên

`PriorityBlockingQueue.iterator()` có trả các phần tử theo priority order không?

**Đáp án:** Không cam kết. Priority semantics nằm ở các thao tác lấy phần tử, không ở iterator.

### Bài 15 — Snapshot chính xác

Muốn audit backlog lúc đóng kỳ, có nên dùng weak iterator khi producers vẫn ghi liên tục không?

**Đáp án:** Không. Cần coordinated snapshot/quiescence, versioned state hoặc durable log có ranh giới rõ.

### Bài 16 — Memory visibility

Producer xây immutable Job rồi `offer`; consumer nhận qua `poll`. Điều gì hỗ trợ visibility?

**Đáp án:** Memory consistency/happens-before của concurrent collection đối với hành động trước publication và sau khi truy cập/removal ở thread khác. Nó không làm mutable object thread-safe khi sửa tiếp sau publish.

### Bài 17 — Exactly once

Hai consumers `poll` cùng một node 42; có thể cả hai lấy 42 từ cùng node không? Điều này có bảo đảm xử lý business exactly-once không?

**Đáp án:** Không thể cả hai claim cùng node qua poll; nhưng process có thể crash/retry. Atomic claim khác exactly-once processing.

### Bài 18 — has no items

`poll()` trả `null`. Dịch vụ có thể khẳng định không bao giờ nhận thêm item nữa không?

**Đáp án:** Không. Producer có thể offer ngay sau; phải có shutdown protocol xác nhận ngừng nhận work.

### Bài 19 — Đồng bộ ngoài

Reader dùng `synchronized(queue)` khi tạo `toArray` nhưng writers không dùng synchronized(queue). Snapshot đã atomic chưa?

**Đáp án:** Chưa. Writers không tuân thủ lock ngoài đó. Tất cả bên liên quan phải phối hợp cùng protocol hoặc đổi kiến trúc.

### Bài 20 — Bounded offer

Hai threads cùng `offer` vào `ArrayBlockingQueue(1)` đang rỗng, không consumer. Có thể cả hai trả true không?

**Đáp án:** Không. Capacity được enforce cho từng lời gọi; chỉ một nhận true, bên còn lại false. Không xác định thread nào thắng.

### Bài 21 — Monitoring

Một dashboard đếm 90 jobs qua weak iterator, trong khi hệ thống nhận 100 jobs. Có đủ kết luận queue làm mất 10 job không?

**Đáp án:** Không. Một số job có thể đã được lấy hoặc thêm/xóa khi duyệt. Muốn kết luận phải đối chiếu accepted, claimed, processed, rejected, inflight theo giao thức đo riêng.

### Bài 22 — Bulk operations

`queue.forEach` đọc các phần tử trong lúc thread khác `addAll` một batch. Có cần thấy hoặc tất cả, hoặc không phần tử nào trong batch không?

**Đáp án:** Không. Theo Javadoc, bulk operation không được bảo đảm atomic với concurrent operations; có thể chỉ thấy một phần batch.

### Bài 23 — Payload mutable

Một Job đã offer có hai trường mutable mà producer liên tục sửa; iterator đọc hai trường. Có đảm bảo hai giá trị cùng phiên bản không?

**Đáp án:** Không. Cần immutable snapshot, lock hoặc protocol version/atomic phù hợp trên chính payload.

### Bài 24 — Test race

Vì sao kiểm thử `size < 1` bằng `CyclicBarrier` tốt hơn gọi `Thread.sleep` rồi hy vọng hai thread cùng đọc size 0?

**Đáp án:** Barrier cố ý tạo thứ tự “cả hai qua check trước khi offer”, giúp quan sát race một cách đáng tin và không phụ thuộc thời gian ngủ may rủi.

## 14. Checklist áp dụng vào ứng dụng

- [ ] Xác định queue implementation cụ thể và hợp đồng iterator của nó.
- [ ] Không coi weakly consistent iterator là snapshot bất biến.
- [ ] Không dựa vào iterator để kiểm đếm/audit chính xác khi có concurrent writers.
- [ ] Không mong iterator nhất thiết thấy mọi phần tử thêm sau khi tạo.
- [ ] Không dùng CME làm cơ chế đồng bộ.
- [ ] Phân biệt thread-safety của queue với thread-safety của payload.
- [ ] Giữ message immutable hoặc có quy tắc chuyển ownership rõ.
- [ ] Dùng `poll/take` cho consumer claim công việc thay vì for-each xử lý.
- [ ] Phân biệt atomic claim với xử lý nghiệp vụ exactly-once.
- [ ] Không dùng `size<N` rồi `offer` để enforce capacity.
- [ ] Với CLQ và LTQ, nhớ `size()` O(n) và không phải số đếm transactional.
- [ ] Dùng bounded queue nếu cần enforce số phần tử chờ.
- [ ] Xử lý `offer` false thay vì làm mất công việc.
- [ ] Không coi `peek` là phép giữ chỗ cho lần `poll` sau đó.
- [ ] Khi xóa theo value, kiểm tra kết quả `remove`, không coi contains+remove atomic.
- [ ] Không coi `addAll/removeIf/forEach` thành transaction toàn queue.
- [ ] Không dùng `parallelStream` trên weak spliterator để tạo exact snapshot.
- [ ] Hiểu `toArray` là bản copy sau khi trả về nhưng có thể không phản ánh một thời điểm chung trong lúc bị sửa.
- [ ] Dùng cùng protocol đồng bộ cho mọi writer/consumer nếu cần chụp trạng thái chính xác.
- [ ] Không giữ lock chung trong thao tác mạng/database lâu gây nghẽn.
- [ ] Không giả định queue empty đồng nghĩa hệ thống đã dừng.
- [ ] Có shutdown signal, no-more-work boundary và pending/inflight accounting.
- [ ] Test bằng barrier/latch với deadline, không chỉ bằng sleep.
- [ ] Kiểm tra invariants thay vì thứ tự thread thắng cuộc.
- [ ] Với queue ưu tiên, đừng coi iterator là danh sách đã sort.
- [ ] Dùng API Java hiện hành; ví dụ chính xác đã kiểm thử trên JDK 17.

## 15. Tài liệu Java chính thức

- [Java SE 17 — ConcurrentLinkedQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html): weakly consistent iterator, `Iterator.remove`, O(n) `size`, bulk-operation caveats và memory consistency.
- [Java SE 17 — LinkedTransferQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedTransferQueue.html): weakly consistent iterator, handoff, O(n) `size` và các bulk operations.
- [Java SE 17 — LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html): iterator, blocking FIFO và capacity.
- [Java SE 17 — ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html): bounded queue và `offer/put/take`.
- [Java SE 17 — PriorityBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html): ưu tiên khi take/poll, không có thứ tự iterator được bảo đảm.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): sự khác nhau giữa `offer`, `put`, `poll` và `take`.
- [Java SE 17 — CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): ví dụ đối chiếu **snapshot iterator**, không phải queue tương đương.
- [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): công cụ điều phối deterministic race test.

## 16. Tổng kết

Iterator **nhất quán yếu** trên các queue đồng thời như `ConcurrentLinkedQueue` cho phép duyệt an toàn cùng lúc với `offer/poll` mà không ném `ConcurrentModificationException` vì thay đổi cấu trúc. Nhưng nó **không phải snapshot atomic** và không nên dùng để xác nhận chính xác backlog, xử lý toàn bộ công việc hay audit một lô message đang bị sửa đồng thời.

Cùng lúc, việc từng lệnh `size`, `offer`, `peek`, `poll`, `contains` hoặc `remove` thread-safe **không có nghĩa đoạn gồm hai ba lệnh atomic**. Một `size() < LIMIT` rồi `offer` có thể vượt hạn mức; `peek` rồi `poll` có thể quan sát hai item khác nhau; `addAll/removeIf/forEach` không là transaction toàn queue.

Muốn **claim** một item, dùng `poll/take` và dựa vào giá trị trả. Muốn **capacity thật**, dùng bounded queue hoặc quota đồng bộ. Muốn **snapshot chính xác**, cần điều phối writers/consumers hoặc versioned/durable state. Muốn **exactly-once business processing**, cần giao thức idempotency, acknowledgement và persistence riêng. Đây là những nguyên tắc quan trọng của concurrent programming **vẫn áp dụng đầy đủ trong Java hiện đại**, không dựa vào API legacy.