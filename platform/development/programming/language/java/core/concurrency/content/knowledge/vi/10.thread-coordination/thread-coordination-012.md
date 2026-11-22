# So sánh phối hợp bằng shared state và message passing trong Java

## 1. Hai cách cơ bản để các thread cộng tác

Một chương trình concurrent thường chia công việc thành nhiều tác vụ chạy đồng thời. Những tác vụ ấy cần **trao đổi dữ liệu**, **báo tiến độ** hoặc **tạo ra một kết quả chung**. Trong Java, hai cách tổ chức nền tảng là:

1. **Shared state (trạng thái dùng chung):** các thread cùng truy cập một vùng dữ liệu. Chúng phối hợp bằng monitor `synchronized`, `Lock`, `volatile`, biến atomic, điều kiện chờ hoặc các cấu trúc dữ liệu concurrent.
2. **Message passing (truyền thông điệp):** các tác vụ trao đổi những thông điệp qua một kênh, chẳng hạn `BlockingQueue`. Một tác vụ có thể **sở hữu độc quyền** trạng thái của nó, còn tác vụ khác yêu cầu nó làm việc bằng cách gửi thông điệp thay vì sửa trực tiếp trạng thái đó.

Cả hai đều tồn tại trong Java concurrency thông thường. Không có lựa chọn nào luôn nhanh hơn hoặc luôn đơn giản hơn. Khác biệt quan trọng là **dữ liệu nằm ở đâu, ai có quyền thay đổi, ai chờ ai, và sự nhất quán được đảm bảo bằng cách nào**.

Ví dụ một bộ đếm nhận yêu cầu tăng từ hai worker:

```text
SHARED STATE

Producer A ────┐
                ├──> shared Counter <── synchronized / AtomicInteger
Producer B ────┘
        Các thread thực hiện cập nhật trực tiếp.


MESSAGE PASSING

Producer A ────┐
                ├──> BlockingQueue<Increment> ──> Counter owner
Producer B ────┘                             (chỉ owner sửa count)
        Các thread gửi yêu cầu, owner cập nhật.
```

Hai thiết kế có thể cho cùng kết quả đúng, nhưng đường truyền quyền sở hữu và chi phí điều phối khác nhau. Bài học thuộc chủ đề **Phối hợp luồng** của **Java concurrency nói chung**, không phụ thuộc framework.

## 2. Phân biệt dữ liệu dùng chung với truyền thông điệp

### Shared state

Ở mô hình shared state, nhiều thread có thể có tham chiếu tới cùng object mutable:

```java
final class Counter {
    private int count;

    synchronized void increment() {
        count++;
    }

    synchronized int get() {
        return count;
    }
}
```

Đây là **định nghĩa lớp minh họa**, không phải chương trình có `main`. Mọi thread gọi `increment()` trên **cùng instance** phải lấy monitor của instance đó. Nếu reader cũng gọi `get()`, các thao tác được bảo vệ nhất quán bằng cùng monitor.

**Ý tưởng:** dữ liệu chung vẫn tồn tại; các thread được phép truy cập nhưng phải tuân thủ giao thức đồng bộ của nó.

### Message passing

Ở mô hình truyền thông điệp, một worker khác có thể gửi yêu cầu tăng thông qua hàng đợi:

```java
record Increment(int amount) {}

BlockingQueue<Increment> mailbox = new ArrayBlockingQueue<>(32);
mailbox.put(new Increment(1));
```

Đây là **đoạn minh họa** cần import `java.util.concurrent.BlockingQueue` và `ArrayBlockingQueue`. Một thread tiêu thụ `mailbox.take()` sẽ nhận thông điệp. Nếu chỉ thread tiêu thụ đó sở hữu và cập nhật `count`, các producer không cần khóa biến `count` — vì chúng **không được phép sửa nó**.

**Ý tưởng:** thay vì chia sẻ quyền ghi state, các thread chia sẻ một kênh chuyển giao yêu cầu/dữ liệu. Cần đảm bảo an toàn cho kênh, xử lý khi đầy/rỗng, vòng đời consumer và ngữ nghĩa thông điệp.

**Điểm tinh tế:** message passing trong cùng JVM vẫn có thể chuyển **tham chiếu tới object trên heap chung**. Việc gọi `queue.put(message)` không tự deep-copy `message` và không tự biến payload mutable thành immutable. Muốn tránh data race, thường dùng **immutable message** hoặc giao thức chuyển quyền sở hữu rõ ràng: producer không sửa payload nữa sau khi gửi.

## 3. Bảng so sánh nhanh

| Tiêu chí | Shared state | Message passing |
| --- | --- | --- |
| Giao diện giữa các tác vụ | Gọi method/đọc-ghi object dùng chung | Gửi/nhận thông điệp qua queue hoặc channel |
| Chủ sở hữu mutable state | Có thể nhiều thread, cần giao thức đồng bộ | Thường một owner xử lý state; producer chỉ gửi yêu cầu |
| Primitive Java thường dùng | `synchronized`, `ReentrantLock`, `AtomicInteger`, `volatile`, `Condition` | `BlockingQueue`, `ArrayBlockingQueue`, `LinkedBlockingQueue`, `TransferQueue` |
| Nguy cơ thường gặp | Data race, stale read, lost update, deadlock, invariant bị phá | Queue đầy, producer bị chặn, backlog, shutdown khó, payload bị sửa sau khi gửi |
| Cách kiểm tra nhất quán | Khóa chung, thao tác atomic, immutable snapshot | Một consumer tuần tự hóa cập nhật hoặc protocol điều phối giữa owners |
| Kiểm soát tải | Thường phải bổ sung cơ chế giới hạn riêng | Bounded queue hỗ trợ backpressure tự nhiên |
| Trả kết quả | Gọi method thường có thể trả kết quả ngay | Có thể cần response message hoặc `CompletableFuture` |
| Độ trễ | Có thể ngắn khi chỉ một cập nhật atomic | Thêm enqueue, dequeue và chuyển ngữ cảnh/tác vụ |
| Mức cô lập | Caller có thể biết sâu cấu trúc state | Owner có thể giấu chi tiết state sau tập thông điệp |
| Phù hợp | Một số ít trường cập nhật đơn giản, snapshot được đồng bộ | Pipeline, producer–consumer, actor-like owner, bàn giao tác vụ |

**Không đồng nhất “message passing = không lock”:** queue thread-safe có thể sử dụng khóa, CAS, condition hoặc các kỹ thuật khác bên trong implementation. Điều bạn đạt được là **không phải tự chia sẻ quyền ghi state nghiệp vụ** nếu mô hình owner được thiết kế đúng.

**Không đồng nhất “shared state = chắc chắn sai”:** một `AtomicInteger.incrementAndGet()` hoặc một object được bảo vệ khóa đúng cách hoàn toàn có thể thread-safe và rõ ràng hơn việc tạo cả một worker với queue cho một phép tăng đơn giản.

## 4. Ví dụ chạy được: shared state với synchronized counter

Tạo tệp `SharedCounterDemo.java` (Java 17+):

```java
import java.util.concurrent.CountDownLatch;

public class SharedCounterDemo {
    private static final class Counter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int value() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        CountDownLatch start = new CountDownLatch(1);

        Runnable worker = () -> {
            try {
                start.await();
                for (int i = 0; i < 1_000; i++) {
                    counter.increment();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(worker, "a");
        Thread b = new Thread(worker, "b");
        a.start();
        b.start();
        start.countDown();

        a.join();
        b.join();
        System.out.println("shared total=" + counter.value());
    }
}
```

```bash
javac SharedCounterDemo.java
java SharedCounterDemo
```

Kết quả khi không có interrupt ngoài ý muốn:

```text
shared total=2000
```

**Cơ chế đúng:**

1. `Counter` giữ `value` là trường private.
2. Hai thread gọi `increment()` trên **cùng một instance `counter`**.
3. Method synchronized dùng monitor của `counter`, nên hai phép đọc–sửa–ghi không xen ngang nhau.
4. `value()` đọc dưới chính monitor đó.
5. Main đợi cả hai `join()` nên chỉ in sau khi mọi phép tăng đã hoàn tất.

Nếu bỏ `synchronized` khỏi `increment()`, phép `value++` có thể mất cập nhật. Nếu chỉ để `synchronized` trên getter mà writer không khóa, giao thức không còn đúng. Nếu mỗi thread tạo một `Counter` riêng, kết quả sẽ là hai bộ đếm độc lập — không phải một shared counter.

### Khi dùng AtomicInteger thay vì synchronized

Với đúng một phép tăng đơn giản, có thể sử dụng `AtomicInteger`:

```java
AtomicInteger counter = new AtomicInteger();
counter.incrementAndGet();
int total = counter.get();
```

Đoạn này minh họa (cần import `java.util.concurrent.atomic.AtomicInteger`). Một atomic counter loại bỏ nhu cầu tự viết critical section để bảo vệ **duy nhất bộ đếm đó**. Tuy nhiên, nếu thao tác cần đổi ba trường đồng thời và duy trì một invariant, ba `AtomicInteger` riêng chưa chắc đủ; cần khóa bao phủ thao tác hoặc immutable snapshot được công bố atomically.

## 5. Ví dụ tương đương: message passing với một owner

Ở thiết kế tiếp theo, **producer không có tham chiếu tới biến `count`**. Mỗi producer gửi 1.000 thông điệp có giá trị `1` vào queue. Consumer duy nhất nhận từng thông điệp và cập nhật `count` cục bộ.

Tạo tệp `MessageCounterDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class MessageCounterDemo {
    private static final int STOP = -1;

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> inbox = new ArrayBlockingQueue<>(16);
        CountDownLatch start = new CountDownLatch(1);
        int[] result = new int[1];

        Thread owner = new Thread(() -> {
            int count = 0;
            try {
                while (true) {
                    int amount = inbox.take();
                    if (amount == STOP) {
                        break;
                    }
                    count += amount;
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            result[0] = count;
        }, "owner");

        Runnable producerTask = () -> {
            try {
                start.await();
                for (int i = 0; i < 1_000; i++) {
                    inbox.put(1);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(producerTask, "producer-a");
        Thread b = new Thread(producerTask, "producer-b");
        owner.start();
        a.start();
        b.start();
        start.countDown();

        a.join();
        b.join();
        inbox.put(STOP);
        owner.join();

        System.out.println("message total=" + result[0]);
    }
}
```

```bash
javac MessageCounterDemo.java
java MessageCounterDemo
```

Kết quả khi không có interrupt ngoài ý muốn:

```text
message total=2000
```

**Vì sao đúng:**

- Producer chỉ gửi các số dương `1`, không giữ biến `count` của owner.
- `BlockingQueue.put()` và `take()` bảo vệ quá trình bàn giao giữa nhiều producer và consumer.
- Chỉ owner thay đổi biến `count` cục bộ, nên phần cập nhật count không có hai thread cạnh tranh sửa.
- Main đợi **cả hai producer kết thúc** trước khi gửi `STOP`. Mọi thông điệp số `1` đã vào FIFO queue trước STOP, do đó owner nhận hết các thông điệp rồi mới dừng.
- Main đợi `owner.join()` trước khi đọc `result[0]`; kết thúc thread qua `join` cung cấp quan hệ happens-before cho lần ghi kết quả của owner. Mảng một phần tử ở đây chỉ là nơi lưu kết quả cho ví dụ đơn giản, không phải một queue hoặc cơ chế đồng bộ.

**Chú ý:** nếu main gửi `STOP` trước khi các producer hoàn tất, owner có thể dừng quá sớm và để lại công việc chưa xử lý; producer có thể tiếp tục `put()` đến khi queue đầy và chờ vô hạn. Bài học chính là **shutdown cũng là một phần của giao thức message passing**.

Có thể dùng record `Increment(int amount)` thay vì `Integer` để phân biệt thông điệp nghiệp vụ với ký hiệu điều khiển; ở bài minh họa dùng số `STOP = -1` vì mọi dữ liệu hợp lệ đều là số dương. Ứng dụng thực cần tránh để marker trùng dữ liệu hợp lệ.

## 6. Vì sao cả hai chương trình đều cho 2000 nhưng ý nghĩa khác nhau?

Trong `SharedCounterDemo`, hai worker thực hiện trực tiếp công việc:

```text
A --increment()--> Counter
B --increment()--> Counter
         monitor serialize critical sections
```

Trong `MessageCounterDemo`, mỗi worker diễn đạt một yêu cầu:

```text
A --put(1)--> Queue --take()--> Owner --count += 1
B --put(1)--> Queue --take()--> Owner --count += 1
```

Về mặt correctness của tổng cuối, hai cách đều đúng khi giao thức được tuân thủ. Nhưng trách nhiệm khác nhau:

- Shared state: mọi đường đọc/ghi state đều phải đồng bộ; nếu một code path quên khóa, bug có thể xuất hiện.
- Message passing: owner chịu trách nhiệm tuần tự hóa state; producer phải gửi đúng message và quản lý lifecycle. Nếu payload mutable bị chia sẻ hoặc nhiều owner cùng sửa state ngoài protocol, lợi ích ownership biến mất.

Chi phí cũng khác: shared counter có thể chỉ phải lock/unlock hoặc atomic instruction, còn message passing thường thêm thao tác enqueuing, dequeuing, buffer và context switch. Với nhiều producer, queue còn cung cấp điểm gom tải và tách nhịp sản xuất/tiêu thụ.

## 7. Sở hữu dữ liệu: actor-like model trong cùng JVM

Một thiết kế message passing dễ suy luận là **single writer**:

1. Một thành phần sở hữu mutable state.
2. Các thành phần khác **không nhận tham chiếu mutable** tới state đó.
3. Họ gửi **command**, **event** hoặc **request** qua kênh thread-safe.
4. Owner nhận từng message rồi đổi state.
5. Nếu cần trả lời, owner gửi một response hoặc hoàn thành một `CompletableFuture`.

Mô hình này gần với nguyên tắc actor, nhưng sử dụng `Thread` và `BlockingQueue` **không tự tạo ra toàn bộ actor runtime**. Bạn vẫn cần tự xử lý mailbox, scheduling, failure recovery, ordering, giới hạn tải và shutdown.

### Command, event, request khác nhau ở đâu?

- **Command:** “hãy thực hiện thay đổi X”. Có thể được chấp nhận hoặc từ chối.
- **Event:** “X đã xảy ra”. Thường mô tả một sự kiện đã commit; người tiêu thụ có thể cập nhật một view.
- **Request–response:** “hãy tính hoặc thay đổi X rồi gửi kết quả cho tôi”. Cần correlation giữa yêu cầu và phản hồi.

Có thể dùng Java record để định nghĩa thông điệp bất biến:

```java
record Add(int amount) {}
record TotalRequest(long requestId) {}
record TotalReply(long requestId, int total) {}
```

Đây là những định nghĩa record minh họa. Record có các trường component là final, nhưng **không tự bất biến sâu** nếu chứa mảng hoặc danh sách mutable. Với primitive và `String`, xây dựng message bất biến đơn giản hơn.

## 8. Ví dụ request–response bằng CompletableFuture

Không phải mọi caller đều muốn “gửi rồi quên”. Đôi khi họ cần biết owner đã xử lý yêu cầu và kết quả là bao nhiêu. Một cách trong JVM là đặt một `CompletableFuture` trong message; owner hoàn thành future khi xử lý xong.

Tạo tệp `QueueRequestReplyDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;

public class QueueRequestReplyDemo {
    record Add(int amount, CompletableFuture<Integer> reply) {}

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Add> inbox = new ArrayBlockingQueue<>(8);
        CompletableFuture<Integer> first = new CompletableFuture<>();
        CompletableFuture<Integer> second = new CompletableFuture<>();

        Thread owner = new Thread(() -> {
            int total = 0;
            try {
                for (int i = 0; i < 2; i++) {
                    Add message = inbox.take();
                    total += message.amount();
                    message.reply().complete(total);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "owner");

        owner.start();
        inbox.put(new Add(5, first));
        inbox.put(new Add(7, second));

        System.out.println("first=" + first.join());
        System.out.println("second=" + second.join());
        owner.join();
    }
}
```

```bash
javac QueueRequestReplyDemo.java
java QueueRequestReplyDemo
```

Kết quả:

```text
first=5
second=12
```

Main gửi lần lượt hai message vào FIFO queue. Owner là consumer duy nhất, nên xử lý `Add(5)` trước `Add(7)`. Mỗi message kèm future riêng, tránh nhầm response. `CompletableFuture.join()` trên main đợi kết quả của từng request; đây là **một cách đồng bộ giữa caller và owner**, không phải `Thread.join()`. Nếu future hoàn thành exceptionally, `join()` có thể ném `CompletionException`.

**Quan trọng:** đối tượng `CompletableFuture` là mutable để owner hoàn thành response. Message record ở đây chỉ cố định tham chiếu tới future; nó không phải đồ thị bất biến sâu hoàn toàn. Điều này được phép vì protocol trao quyền hoàn thành cho owner và quyền chờ cho caller, nhưng mọi thành phần phải tuân thủ hợp đồng.

Một implementation production cần định nghĩa nếu owner bị crash, bị interrupt hoặc gặp exception trước khi hoàn thành future thì phải báo lỗi thế nào; nếu bỏ quên future, caller `join()` có thể chờ mãi. Nên hoàn thành exceptionally, đặt timeout phía caller và thiết kế vòng đời rõ ràng. `CompletableFuture.cancel()` cũng **không tự đảm bảo ngắt luồng owner** hoặc gỡ bỏ message đang nằm trong queue.

## 9. Shared state vẫn hữu ích khi có nhiều reader

Không phải cứ có nhiều thread đọc là phải gửi “ReadRequest” cho một owner. Ví dụ thông tin cấu hình được tạo thành **immutable snapshot** rồi công bố qua `AtomicReference<Config>`:

```java
record Config(String host, int port) {}

AtomicReference<Config> active =
        new AtomicReference<>(new Config("localhost", 8080));

Config snapshot = active.get();
System.out.println(snapshot.host() + ":" + snapshot.port());
```

Đây là đoạn minh họa, cần import `java.util.concurrent.atomic.AtomicReference`, đặt trong một class/method hợp lệ. Reader chỉ lấy một tham chiếu snapshot và đọc các field bất biến, không cần owner nhận một message để trả host/port. Khi config đổi, writer tạo `Config` mới hoàn chỉnh rồi công bố **một tham chiếu** phù hợp.

Đây là một mô hình **lai**: dữ liệu đọc được chia sẻ, nhưng bất biến và được công bố an toàn; cập nhật có thể đến qua message passing tới một owner, rồi owner thay root reference. Hai hướng không loại trừ nhau.

**Cẩn trọng:** hai lần đọc `active.get().host()` và `active.get().port()` có thể đến từ hai phiên bản nếu writer thay snapshot giữa chúng. Khi cần consistency, lấy `Config snapshot = active.get()` **một lần** rồi đọc mọi component từ snapshot ấy.

## 10. Shared mutable object cần những gì?

Khi chọn shared state, cần xác định:

- **Invariant:** điều kiện phải luôn đúng, ví dụ `balance >= 0` hoặc `left + right == 100`.
- **Reader/writer:** ai có quyền đọc, ghi, và tất cả có tuân thủ cùng cơ chế không?
- **Atomicity:** một thay đổi logic có thể gồm nhiều trường hay không?
- **Visibility:** thread đọc có bảo đảm thấy ghi của thread khác không?
- **Điểm chờ:** có giữ lock trong lúc I/O hoặc chờ thread khác không?
- **Liveness:** có thể deadlock, starvation hoặc vòng chờ thiếu tín hiệu không?

### Ví dụ dùng lock đúng phạm vi

```java
final class Balance {
    private int amount;

    synchronized boolean withdraw(int cost) {
        if (cost < 0 || cost > amount) {
            return false;
        }
        amount -= cost;
        return true;
    }

    synchronized void deposit(int value) {
        if (value < 0) {
            throw new IllegalArgumentException();
        }
        amount += value;
    }

    synchronized int snapshot() {
        return amount;
    }
}
```

Đây là đoạn định nghĩa lớp minh họa. Kiểm tra đủ tiền và phép trừ **cùng một critical section** để không có hai writer cùng vượt điều kiện. Cũng cần kiểm tra overflow nếu domain có giá trị lớn. Việc khóa writer mà để reader đọc trường trực tiếp ngoài lock vẫn là lỗi đồng bộ.

Một `volatile int amount` không làm thao tác “kiểm tra rồi trừ” nguyên tử. `AtomicInteger` có thể giải bằng vòng CAS nếu một field, nhưng code phải retry/validate trên state mới. Nếu dữ liệu trải nhiều field thì một immutable snapshot hoặc critical section là cách dễ chứng minh hơn.

## 11. Message passing và happens-before: dữ liệu trong thông điệp có nhìn thấy được không?

Một queue thuộc `java.util.concurrent` không chỉ làm nhiệm vụ giữ phần tử. API của các concurrent collection có **bảo đảm bộ nhớ** để việc chuyển giao giữa thread có ý nghĩa.

Với các `BlockingQueue` tiêu chuẩn, hành động của producer **trước khi đặt một object vào queue** *happens-before* những hành động của consumer **sau khi lấy object đó ra** theo hợp đồng các concurrent collection. Vì vậy producer có thể tạo payload, khởi tạo các field và `put`; consumer lấy message qua `take` có cơ sở JMM để nhìn thấy những ghi xảy ra trước lúc enqueue.

Nhưng hãy phân biệt hai điều:

1. **Công bố dữ liệu đã tạo trước khi gửi:** queue giúp producer và consumer có thứ tự/visibility rõ.
2. **Sửa payload sau khi gửi:** nếu producer tiếp tục sửa một object mutable trong khi consumer đang đọc, queue **không tự bảo vệ những sửa đổi sau enqueue**.

Ví dụ nguy hiểm:

```java
List<String> payload = new ArrayList<>();
payload.add("A");
queue.put(payload);
payload.add("B"); // Có thể tranh chấp với consumer đang duyệt payload.
```

Đây là đoạn phản ví dụ, cần khai báo/import `queue` và các loại collection phù hợp. Cách sửa là copy thành immutable data trước khi gửi:

```java
List<String> message = List.copyOf(payload);
queue.put(message);
```

Nếu các phần tử danh sách là object mutable, `List.copyOf` chỉ copy **cấu trúc/tham chiếu phần tử**, không tự deep-copy từng object. Nên dùng kiểu phần tử bất biến hoặc xác định quyền sở hữu rõ.

## 12. Ordering: thứ tự thông điệp là thứ tự nào?

`BlockingQueue` có nhiều implementation với hợp đồng ordering khác nhau. `ArrayBlockingQueue` và `LinkedBlockingQueue` được dùng như FIFO queue: các phần tử được lấy theo thứ tự vào queue. Tuy nhiên, khi **nhiều producer gửi đồng thời**, ai enqueue trước là kết quả của việc xen kẽ được hệ thống thực hiện, **không phải thứ tự tuyệt đối theo tên thread**.

Một consumer duy nhất xử lý từng message theo thứ tự dequeue, nhưng nếu có **nhiều consumer**, các message có thể được lấy bởi các worker khác nhau và **hoàn tất xử lý không theo đúng thứ tự nhận**.

Câu hỏi thiết kế:

- Có cần giữ thứ tự **trong một producer** không?
- Có cần thứ tự toàn cục **giữa nhiều producer** không? Nếu có, ai cấp sequence và ở đâu?
- Có cần đảm bảo **xử lý xong** tuần tự hay chỉ **dequeue** tuần tự?
- Có message nào được xử lý lại sau lỗi không?
- Nếu message là một phần của giao dịch, làm sao giữ consistency giữa các message?

**FIFO không có nghĩa exactly-once processing.** Queue trong bộ nhớ không tự cung cấp lưu trữ bền vững hoặc giao dịch. Một consumer có thể lấy message ra rồi gặp exception trước khi cập nhật kết quả. Cần quyết định retry, dead-letter, idempotency hoặc cơ chế durable messaging khi bài toán yêu cầu.

## 13. Backpressure: khác biệt rất quan trọng

Một producer có thể tạo việc nhanh hơn consumer xử lý. Nếu queue tăng vô hạn, chương trình có thể giữ ngày càng nhiều object trong heap và cuối cùng gặp áp lực GC hoặc `OutOfMemoryError`.

Một **bounded queue** đặt giới hạn backlog. Khi đầy:

- `put(message)` **chờ** đến khi có chỗ; có thể bị interrupt bằng `InterruptedException`.
- `offer(message)` không đợi, trả `false` nếu không thêm được ngay.
- `offer(message, timeout, unit)` chờ tối đa thời hạn và có thể bị interrupt.
- `add(message)` có thể ném `IllegalStateException` nếu queue có giới hạn và không còn chỗ.

### Ví dụ backpressure với kết quả xác định

Tạo `BackpressureDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class BackpressureDemo {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Integer> queue = new ArrayBlockingQueue<>(1);

        queue.put(10);
        System.out.println("offer while full=" + queue.offer(20));
        System.out.println("take=" + queue.take());
        System.out.println("offer after take=" + queue.offer(20));
        System.out.println("take again=" + queue.take());
    }
}
```

```bash
javac BackpressureDemo.java
java BackpressureDemo
```

Kết quả:

```text
offer while full=false
take=10
offer after take=true
take again=20
```

Queue có capacity 1. Khi chứa `10`, thêm `20` bằng `offer` không thành công. Sau khi `take` lấy `10`, có một ô trống cho `20`. Ví dụ chạy một thread để minh họa **hợp đồng queue**, không phải phép đo số luồng cùng chạy.

### Chọn chính sách khi queue đầy

Không có chính sách đúng cho mọi hệ thống. Có thể:

- **Block producer:** dùng `put` để lan ngược áp lực; cần xét producer có được phép chờ không.
- **Fail fast:** dùng `offer` trả `false` để caller nhận biết “busy” và quyết định retry.
- **Timeout:** dùng `offer(timeout)` để cân bằng thời gian chờ.
- **Drop/coalesce:** chỉ áp dụng nếu nghiệp vụ cho phép mất hoặc gộp message (ví dụ một số chỉ số quan sát).
- **Scale consumer hoặc partition:** chia tải theo key khi yêu cầu ordering/ownership cho phép.

Với **unbounded queue**, `put` thường không block vì giới hạn capacity theo kiểu bounded, nhưng không nên xem “không có backpressure” là miễn phí: heap vẫn hữu hạn. `LinkedBlockingQueue` không truyền capacity thì có khả năng nhận rất nhiều phần tử trước khi chạm giới hạn thực tế của bộ nhớ.

## 14. Shutdown và cancellation của message passing

Ở shared state, một lời gọi synchronized method có thể kết thúc sau khi sửa xong. Với message passing, còn một **mailbox**, một hoặc nhiều consumer, và các producer có thể đang đợi gửi. Đóng hệ thống cần trả lời:

1. Có nhận message mới nữa không?
2. Các producer đang block tại `put` được xử lý như thế nào?
3. Có cần xử lý hết queue trước khi dừng?
4. Consumer đang block tại `take` được đánh thức bằng cách nào?
5. Request đang chờ response sẽ được hoàn thành hay báo lỗi?
6. Có bao nhiêu consumer và cần bao nhiêu tín hiệu dừng?

### Poison pill (thông điệp dừng)

Ở `MessageCounterDemo`, main gửi `STOP` sau khi producer đã hoàn thành. Một consumer nhận STOP và kết thúc. Với **N consumer**, thông thường cần **N tín hiệu dừng** tương thích với protocol, hoặc một cơ chế dừng khác; gửi một STOP không tự đánh thức tất cả consumer.

Nếu queue đầy mà consumer đã chết, `put(STOP)` có thể chờ vô hạn. Nếu producer còn chạy, STOP có thể nằm trước các message nghiệp vụ, khiến consumer kết thúc quá sớm. Do đó cần **quy trình shutdown theo thứ tự**: ngừng nhận mới, chờ producer hoặc hủy có kiểm soát, cho phép drain nếu cần, gửi tín hiệu dừng hợp lệ, đợi consumer cleanup.

### Interrupt khác poison pill

`Thread.interrupt()` là **yêu cầu hủy hợp tác** ở cấp thread; các phương thức chặn như `BlockingQueue.take()` và `put()` có thể ném `InterruptedException`. Poison pill là **một message của giao thức nghiệp vụ**. Chúng không tương đương:

- Interrupt có thể dừng consumer khi queue vẫn còn message.
- Poison pill thường giữ được thứ tự theo queue và cho phép “drain rồi dừng”, nhưng phụ thuộc khả năng enqueue marker.
- Có thể kết hợp một cờ lifecycle và cơ chế interrupt/wakeup; cần đảm bảo không có producer gửi sau trạng thái đóng.

Không dùng `Thread.stop()` để hủy consumer; đó là API không an toàn và đã lỗi thời.

## 15. Error handling: exception xảy ra ở đâu?

Trong shared state, caller thường thực thi method trên chính thread của mình. Nếu method ném exception, caller nhận exception trực tiếp và có thể xử lý trong cùng call stack.

Trong message passing, producer thường chỉ enqueue. Exception xảy ra trong **consumer** sau đó, không tự “quay về” thread producer:

```text
Producer -> put(command) -> return
Consumer -> take(command) -> process -> exception
```

Muốn caller biết kết quả, phải thiết kế **response channel**, một future, callback, event kết quả hoặc cơ chế ghi nhận lỗi phù hợp. Nếu owner ngừng vì exception và các future chưa hoàn thành, caller có thể treo khi chờ.

Trong một worker event loop, nên phân biệt:

- **Lỗi của một message:** có thể báo lỗi cho riêng request đó, tiếp tục xử lý phần tử tiếp theo nếu state vẫn nhất quán.
- **Lỗi phá invariant của owner:** có thể phải ngừng owner, thông báo những request đang pending và khởi tạo lại state theo hợp đồng.
- **Lỗi hạ tầng:** nếu queue hoặc resource phụ trợ không còn hoạt động, cần có đường shutdown/retry rõ ràng.

Message passing tách thành phần xử lý nhưng **không tự giải quyết retry, exactly-once, transaction, idempotency hoặc hồi phục sau crash**. Những yêu cầu ấy cần giao thức ứng dụng và thường là tầng lưu trữ phù hợp.

## 16. Trạng thái chia sẻ vẫn xuất hiện ngay trong message passing

Tại JVM, “truyền message” không phải truyền dữ liệu qua một không gian địa chỉ cô lập như hai process ở hai máy khác nhau. Các thread vẫn có thể có tham chiếu tới cùng object. Vì vậy cần hai nguyên tắc đồng thời:

1. **Kênh phải thread-safe:** chẳng hạn `ArrayBlockingQueue` là primitive được thiết kế cho nhiều producer/consumer.
2. **Nội dung message có ownership rõ:** tốt nhất là immutable DTO/record chứa dữ liệu bất biến; nếu là payload mutable được chuyển quyền, producer phải **ngừng sửa** sau khi chuyển và consumer phải sở hữu rõ ràng.

Vì vậy hai cách thường hòa trộn:

- Producer tạo một **immutable message** ở local state.
- Producer `put` vào **shared thread-safe queue**.
- Consumer sở hữu mutable state nghiệp vụ, cập nhật tuần tự.
- Consumer có thể **publish immutable snapshot** qua một `AtomicReference` để reader đọc nhanh.

Mô hình lai này dùng shared state ở phần queue/atomic reference, nhưng tách trách nhiệm ghi state chính. Không có ranh giới tuyệt đối “message passing không chia sẻ bộ nhớ”.

## 17. Nên chọn shared state hay message passing?

### Chọn shared state khi

- Trạng thái nhỏ, bất biến đơn giản và thao tác cần phản hồi **ngay trong lời gọi method**.
- Có primitive atomic phù hợp, như tăng một counter bằng `AtomicInteger.incrementAndGet()`.
- Critical section ngắn và số thread tranh chấp ở mức chấp nhận được.
- Các thao tác trên object có contract rõ ràng, có thể gói trong method synchronized hoặc lock bảo vệ toàn bộ invariant.
- Cần đọc snapshot hiện hành với độ trễ thấp và đã có cơ chế công bố dữ liệu đúng.

### Chọn message passing khi

- Có mô hình **producer–consumer**, pipeline hoặc worker nhận các command.
- Muốn một owner quản lý độc quyền mutable state để giảm số đường ghi trực tiếp.
- Muốn tách nhịp tạo việc và xử lý, đồng thời cần **bounded backlog/backpressure**.
- Có nhiều loại message và một vòng xử lý tuần tự hóa các thay đổi liên quan.
- Cần gom command, ghi log sự kiện, phân luồng theo key hoặc thêm cơ chế gửi phản hồi theo request.

### Cân nhắc phương án lai khi

- Một owner nhận message để cập nhật state;
- State public được biểu diễn bằng **immutable snapshot**;
- Nhiều reader chỉ lấy snapshot bằng atomic/volatile reference;
- Queue dùng để điều phối writer, còn reader không phải gửi message chỉ để xem dữ liệu.

Bảng chọn nhanh:

| Bài toán | Lựa chọn xuất phát | Rủi ro cần kiểm tra |
| --- | --- | --- |
| Nhiều thread tăng một thống kê | `AtomicLong` hoặc `LongAdder` theo yêu cầu snapshot | Contention, overflow, ngữ nghĩa `sum()` |
| Chuyển tiền trong một object nhỏ | `synchronized`/lock hoặc immutable CAS snapshot | Tính nguyên tử của kiểm tra và cập nhật |
| Một worker tiêu thụ nhiều job | `BlockingQueue<Job>` + consumer | Backpressure, shutdown, interrupt |
| Nhiều producer gửi log sự kiện | Bounded queue + logger owner (nếu thích hợp) | Mất log khi queue đầy, lỗi I/O, drain |
| Cấu hình ít thay đổi, nhiều reader | Immutable config + `AtomicReference` | Reader lấy cùng snapshot một lần |
| Nhiều task cùng chỉnh một object graph phức tạp | Một owner nhận command hoặc lock bao trùm invariant | Chi phí queue/lock và state leak |
| Cần request–response bất đồng bộ | Message + `CompletableFuture`/response channel | Timeout, correlation, exceptional completion |
| Cần giao dịch xuyên database và RAM | Giao thức transaction/idempotency ở tầng tương ứng | Không primitive trong JVM nào tự bảo đảm distributed atomicity |

## 18. Performance và fairness: đừng quyết định chỉ từ tên mô hình

**Shared state** có thể rất nhanh khi lock không bị tranh hoặc khi dùng primitive atomic thích hợp. Nếu một class monitor toàn cục được giữ qua I/O chậm, nó có thể gây head-of-line blocking. Nếu nhiều thread cùng sửa một giá trị atomic nóng, cache contention có thể khiến throughput giảm.

**Message passing** có thêm bước enqueue/dequeue, copy/đóng gói message và thường là chuyển ngữ cảnh. Bù lại, owner có thể batch nhiều message, tối ưu locality của state, hạn chế số writer và giữ backpressure bằng queue giới hạn.

Không có kết luận “không khóa = nhanh” hay “queue = luôn mở rộng tốt”. Một consumer duy nhất có thể trở thành điểm nghẽn nếu khối lượng xử lý quá lớn. Muốn scale, có thể chia state thành các partition với mỗi owner riêng, nhưng yêu cầu ordering và invariant xuyên partition trở nên phức tạp hơn.

Cũng cần phân biệt:

- **Fairness:** một request có bị chờ mãi vì các request khác không? Một số implementation lock/queue cho tùy chọn fairness nhưng có tradeoff.
- **Throughput:** số công việc hoàn thành mỗi giây.
- **Latency:** thời gian từ lúc yêu cầu gửi tới lúc có kết quả.
- **Tail latency:** các trường hợp chậm nhất, thường chịu tác động mạnh bởi queue backlog.
- **Memory:** số message chờ trong heap, object allocation và pressure của GC.

Đo trên workload thật hoặc benchmark đúng cách; một vài lần `System.nanoTime()` không đủ để khẳng định mô hình nào nhanh hơn vì ảnh hưởng của JIT, warm-up, số core và lịch chạy.

## 19. Những hiểu nhầm phổ biến

### 19.1. “Message passing tức là không còn data race”

Sai nếu producer gửi object mutable rồi tiếp tục sửa. Consumer có thể đọc cùng object trong lúc producer ghi. Queue chỉ bảo đảm giao thức chuyển giao qua các thao tác queue; nó không tự đóng băng payload.

### 19.2. “Shared state chỉ cần volatile là đủ”

Sai nếu thao tác là read-modify-write hoặc invariant trải nhiều field. `volatile` phù hợp công bố/đọc một số trạng thái theo hợp đồng, nhưng không biến `counter++` thành atomic transaction.

### 19.3. “Một owner nghĩa là không cần suy nghĩ về synchronization”

Sai nếu dữ liệu của owner rò rỉ qua getter trả mutable reference, callback hoặc future/collection không được bảo vệ. Single writer là một **quy ước quyền sở hữu**, không phải thuộc tính mà JVM tự áp đặt cho bất kỳ object nào.

### 19.4. “Queue FIFO bảo đảm mọi tác vụ hoàn tất đúng thứ tự”

FIFO của queue bảo đảm thứ tự **dequeue** theo hợp đồng của queue. Với nhiều consumer, thời điểm hoàn tất có thể khác thứ tự nhận. Với nhiều producer, thứ tự enqueue toàn cục phụ thuộc lịch chạy.

### 19.5. “`put()` luôn trả về ngay”

Với bounded queue đã đầy, `put` sẽ block cho đến khi có chỗ hoặc bị interrupt. Nếu thiết kế không xử lý cancellation/shutdown, producer có thể chờ vô hạn.

### 19.6. “`Future.cancel(true)` là consumer đã dừng và cleanup xong”

Cancel gửi tín hiệu theo hợp đồng của Future/executor, không tự bảo đảm thread đã cleanup ngay hoặc queue đã drain. Muốn xác nhận shutdown hoàn tất, cần thêm cơ chế giám sát/đợi phù hợp.

### 19.7. “Consumer đã nhận message thì chắc chắn đã xử lý thành công”

Không. Consumer có thể ném exception sau `take()`. Nếu cần bảo đảm retry/durable delivery, một queue trong RAM đơn giản chưa đủ.

### 19.8. “Gửi một poison pill dừng được mọi consumer”

Nếu có nhiều consumer, một marker chỉ được một consumer nhận. Thiết kế số marker hoặc cơ chế shutdown phù hợp với số worker và hợp đồng phân phối.

### 19.9. “`CompletableFuture` phản hồi cho request tự là message bất biến”

Record chứa tham chiếu `CompletableFuture` chỉ cố định tham chiếu, còn future tự nó là object có trạng thái thay đổi. Cần phân quyền ai có thể complete/cancel và xử lý timeout/exception.

### 19.10. “Khi đã dùng message passing thì không cần tính chuyện nhất quán xuyên owner”

Nếu một nghiệp vụ phải cập nhật state ở **hai owner khác nhau**, gửi hai message liên tiếp không tự biến hai thay đổi thành một transaction. Cần xác định thứ tự, xác nhận, bù trừ hoặc coordinator; hoặc cân nhắc gộp invariant trong một owner.

## 20. Tự kiểm tra

**Câu 1.** Hai worker gọi một `synchronized` method trên cùng counter. Vì sao không lost update?

**Trả lời:** Chúng dùng cùng monitor của instance; không thể cùng thực hiện phần read-modify-write đã bảo vệ tại một thời điểm. Các method đọc liên quan cũng phải dùng cùng cơ chế.

**Câu 2.** Hai producer gửi `Increment(1)` qua `BlockingQueue` tới một consumer duy nhất. Consumer có cần đồng bộ biến count cục bộ với hai producer không?

**Trả lời:** Không nếu count chỉ thuộc quyền sở hữu consumer và producer không có đường sửa/đọc nó ngoài protocol. Queue giải quyết việc chuyển message giữa thread; kết quả chuyển ra thread khác cần quan hệ công bố phù hợp.

**Câu 3.** Sau `queue.put(list)`, producer có thể tiếp tục `list.add(...)` mà vẫn an toàn không?

**Trả lời:** Không có bảo đảm nếu consumer đồng thời đọc danh sách mutable ấy. Dùng snapshot bất biến hoặc một giao thức chuyển quyền sở hữu không còn writer cũ.

**Câu 4.** `ArrayBlockingQueue` có capacity 1 đang chứa một phần tử. `offer(newItem)` trả gì?

**Trả lời:** `false` nếu không còn chỗ vào thời điểm gọi; `put(newItem)` thì chờ có chỗ trừ khi bị interrupt.

**Câu 5.** Có thể gửi STOP vào queue trước khi producer hoàn thành không?

**Trả lời:** Dễ gây lỗi. Consumer có thể dừng trước khi xử lý các thông điệp đến sau STOP, producer có thể block nếu queue không còn consumer. Cần giao thức shutdown/drain rõ.

**Câu 6.** Queue FIFO và hai consumer có đảm bảo message đầu tiên hoàn tất xử lý trước message thứ hai không?

**Trả lời:** Không. FIFO chi phối thứ tự lấy phần tử, còn hai consumer xử lý song song có thể hoàn thành đảo thứ tự.

**Câu 7.** Một message kèm `CompletableFuture` đã được gửi; consumer gặp exception trước khi complete. Caller `future.join()` có tự nhận exception từ thread consumer không?

**Trả lời:** Không tự động. Cần catch lỗi và `completeExceptionally` hoặc áp dụng timeout, supervision và chính sách failure rõ ràng.

**Câu 8.** Trong shared state, khi nào chỉ một `AtomicInteger` là lựa chọn hợp lý hơn message passing?

**Trả lời:** Khi chỉ cần cập nhật một biến số nguyên bằng thao tác atomic đơn giản và không có invariant nhiều field, không cần ownership pipeline hay backpressure.

**Câu 9.** Một owner nhận message rồi thay `AtomicReference<Config>` để nhiều reader đọc. Đây là shared state hay message passing?

**Trả lời:** Là **mô hình lai**: message passing cho đường ghi, shared immutable snapshot cho đường đọc.

**Câu 10.** Hai owner xử lý hai phần giao dịch. Có thể bảo đảm cả hai cập nhật atomic chỉ bằng hai lần `queue.put` không?

**Trả lời:** Không. Hai thông điệp tạo hai hành động độc lập. Cần thiết kế transaction/coordination hay bù trừ phù hợp.

## 21. Kết luận

**Shared state** phối hợp bằng cách bảo vệ dữ liệu mà nhiều thread cùng truy cập. Điểm mạnh là trực tiếp, có thể rất hiệu quả với thao tác nhỏ; yêu cầu cốt lõi là **mọi reader và writer tuân thủ cùng cơ chế synchronization và invariant**.

**Message passing** phối hợp bằng cách gửi dữ liệu/yêu cầu qua kênh thread-safe và thường giao **một owner** thực hiện cập nhật. Điểm mạnh là giảm chia sẻ quyền ghi state và cho phép điều phối producer–consumer, queueing, backpressure; đổi lại, phải thiết kế message immutability/ownership, thứ tự xử lý, response, failure và shutdown.

Hai cách không loại trừ nhau: một ứng dụng Java có thể dùng `BlockingQueue` để gửi command, một owner để cập nhật trạng thái, và một `AtomicReference` chứa immutable snapshot cho những reader cần đọc nhanh. Chọn theo **đơn vị nhất quán, tốc độ cập nhật, nhu cầu phản hồi và vòng đời công việc**, không theo khẩu hiệu “dùng queue sẽ không có race” hay “dùng lock thì không scalable”.
