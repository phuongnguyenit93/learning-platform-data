# Contended monitor và rủi ro giữ khóa quá lâu trong Java

Khi nhiều thread muốn vào cùng một khối `synchronized`, chỉ một thread được giữ **monitor** tại một thời điểm; những thread còn lại có thể phải đợi. Đây là **monitor contention**. Việc đợi là một phần bình thường của đồng bộ, nhưng nếu thread sở hữu monitor giữ khóa quá lâu, một đoạn mã tưởng chừng nhỏ có thể trở thành nút thắt cho toàn bộ ứng dụng: độ trễ tăng, throughput giảm, các thread chờ dồn lại, thậm chí xuất hiện deadlock hoặc starvation.

Bài học tập trung vào **Java Concurrency nói chung**: intrinsic monitor, vòng đời thread, Java Memory Model, cách thiết kế critical section và các công cụ quan sát trên JVM. Các cơ chế tích hợp riêng với Spring thuộc nội dung khác.

## 1. Monitor là gì và khi nào xảy ra contention?

Mỗi object Java có thể được dùng làm **intrinsic lock/monitor** cho một vùng mã `synchronized`. Khi một thread đã vào khối:

~~~java
synchronized (lock) {
    // Truy cập trạng thái chia sẻ được lock bảo vệ.
}
~~~

thread khác muốn vào `synchronized (lock)` phải đợi cho đến khi monitor được giải phóng. Nếu mỗi thread dùng một object khóa khác nhau, chúng **không** tranh chấp cùng monitor; việc chọn đúng identity của lock quyết định cả mutual exclusion lẫn bảo đảm visibility.

Một thread sở hữu monitor có thể vào lại `synchronized` trên cùng monitor vì monitor Java **reentrant**. Mỗi lần vào phải có một lần ra tương ứng; khi thoát các khối synchronized, JVM giải phóng monitor kể cả khi có exception thoát ra. Điều này không có nghĩa thao tác nghiệp vụ tự rollback sau exception.

### 1.1 Phân biệt ba loại tình huống

| Tình huống | Kết quả | Ví dụ |
| --- | --- | --- |
| **Không tranh chấp** | Thread lấy monitor và chạy critical section, thường nhanh. | Chỉ một thread sử dụng bộ đếm. |
| **Contention bình thường** | Một số thread đợi ngắn, rồi lần lượt vào critical section. | Nhiều thread cập nhật queue hoặc counter chung. |
| **Contention kéo dài** | Thread sở hữu lock chờ I/O, sleep, tính toán lâu hoặc gọi callback; các thread khác xếp hàng. | Worker giữ khóa khi gọi dịch vụ mạng hoặc xử lý file lớn. |

**Contention không đồng nghĩa deadlock.** Nếu holder nhả monitor trong thời gian hữu hạn và thread khác được scheduler cấp CPU, chúng có thể tiếp tục. Deadlock là trường hợp phụ thuộc vòng tròn khiến một nhóm thread không thể tiến triển; nó có thể liên quan nhiều monitor hoặc các loại chờ khác nhau.

**Contention cũng không tự chứng minh lỗi correctness.** Lock có thể bảo vệ invariant hoàn toàn đúng nhưng làm performance kém. Ngược lại, bỏ lock để tăng throughput khi chưa thay giao thức có thể gây race và dữ liệu sai.

## 2. `synchronized` điều khiển ownership và memory visibility

`synchronized` cung cấp hai bảo đảm cần phân biệt:

1. **Mutual exclusion:** tại một thời điểm, chỉ một thread có thể sở hữu một monitor cho các critical section trên chính monitor đó.
2. **Happens-before:** lần unlock trên monitor **happens-before** lần lock về sau trên cùng monitor. Các cập nhật thực hiện theo giao thức đúng sẽ được thread khác quan sát theo quy tắc Java Memory Model.

Ví dụ:

~~~java
private final Object lock = new Object();
private int balance;

void deposit(int amount) {
    synchronized (lock) {
        balance += amount;
    }
}

int balance() {
    synchronized (lock) {
        return balance;
    }
}
~~~

Đây là **mảnh lớp minh họa**, chưa phải file có `main`. Cả writer và reader dùng **cùng `lock`**, nên không chỉ phép cộng được bảo vệ khỏi chen ngang mà cả lần đọc cũng nhận visibility phù hợp.

Nếu chỉ đồng bộ writer rồi reader đọc `balance` ngoài lock, không thể coi mọi đường truy cập đã tuân thủ cùng protocol. Nếu dùng hai monitor khác nhau, việc cả hai chỗ đều có từ khóa `synchronized` cũng không tạo mutual exclusion chung.

Một monitor không tự quyết định fairness; Java **không bảo đảm FIFO** cho việc các contender lấy monitor. Thread chờ lâu có thể vẫn bị contender khác vượt qua tùy lịch thực thi.

### 2.1 `synchronized` method khóa object nào?

| Cú pháp | Monitor được sử dụng |
| --- | --- |
| `synchronized (mutex) { ... }` | Chính object reference `mutex`. |
| `public synchronized void update() { ... }` | `this` của instance đang chạy method. |
| `public static synchronized void reset() { ... }` | `Class` object của lớp khai báo method, ví dụ `Counter.class`. |

Hai instance method synchronized thuộc **hai instance khác nhau** không tự khóa nhau. Instance method synchronized và static synchronized cũng dùng **hai monitor khác nhau**. Khi bảo vệ state dùng chung, phải thiết kế lock identity và quyền sở hữu phù hợp.

Tránh `synchronized ("literal")`, `synchronized (Integer.valueOf(...))` hoặc khóa vào object mà code bên ngoài có thể vô tình dùng chung. String interned và boxed values được tái sử dụng có thể gây contention ngoài mong muốn. Thông thường chọn:

~~~java
private final Object lock = new Object();
~~~

và cho phép truy cập state chỉ qua các method của owner.

## 3. Thread `BLOCKED`, `WAITING` và `TIMED_WAITING` khác nhau

Khi xem thread dump, từ “đang chờ” có thể mô tả nhiều cơ chế khác nhau. Trong Java, `Thread.State` giúp phân biệt nguyên nhân.

| Trạng thái | Ý nghĩa thường gặp | Ví dụ |
| --- | --- | --- |
| `RUNNABLE` | Đang thực thi hoặc sẵn sàng để JVM thực thi; không nhất thiết chiếm CPU đúng lúc quan sát. | Tính toán trong method. |
| `BLOCKED` | Đang chờ lấy intrinsic monitor để vào hoặc vào lại vùng `synchronized`. | Contender ở trước `synchronized(lock)` khi holder chưa nhả. |
| `WAITING` | Chờ vô thời hạn do một operation chờ điều kiện hoặc hoàn tất. | `Object.wait()` không timeout, `Thread.join()` không timeout, `CountDownLatch.await()`. |
| `TIMED_WAITING` | Chờ có thời hạn. | `Thread.sleep(100)`, `Thread.join(100)`, timed `Object.wait()`. |
| `TERMINATED` | Thread đã kết thúc. | `run()` trả về hoặc thoát bởi exception. |

**Quan trọng:** một thread đang đợi `ReentrantLock` có thể xuất hiện ở `WAITING` hoặc `TIMED_WAITING` dựa trên primitive park của lock, không nhất thiết ở `BLOCKED`. `BLOCKED` trong `Thread.State` nói cụ thể về **intrinsic monitor**.

Ngoài ra, một thread ở `WAITING` vẫn có thể **đang giữ một monitor khác**. Trạng thái thread không cho biết nó không nắm giữ khóa nào. Phải đọc stack trace và phần “locked monitors” trong thread dump.

### 3.1 Bức tranh contention

~~~text
Thread A                            Thread B                       Thread C
--------                            --------                       --------
synchronized (lock)                synchronized (lock)            synchronized (lock)
       |                                   |                              |
       v                                   v                              v
owns monitor                         BLOCKED waiting                BLOCKED waiting
       |
critical section dài
       |
unlock() khi thoát synchronized
                                           |
                                           v
                                    một contender lấy monitor
~~~

Không có quy tắc FIFO bắt buộc trong intrinsic monitor để xác định B hay C thắng. Điều ta có thể dựa vào là **chỉ một holder** chạy trong cùng critical section tại một thời điểm.

## 4. Ví dụ Java 17+: quan sát hai thread tranh cùng monitor

Ví dụ dùng latch để holder giữ monitor đến khi main cho phép nhả. Như vậy thứ tự message là xác định, không phụ thuộc việc `sleep()` có đủ dài hay không.

Tạo file `MonitorContentionDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class MonitorContentionDemo {
    public static void main(String[] args) throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch holderEntered = new CountDownLatch(1);
        CountDownLatch releaseHolder = new CountDownLatch(1);
        CountDownLatch contenderApproaching = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            synchronized (monitor) {
                System.out.println("Holder entered");
                holderEntered.countDown();
                try {
                    releaseHolder.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                System.out.println("Holder leaving");
            }
        }, "holder");

        Thread contender = new Thread(() -> {
            contenderApproaching.countDown();
            synchronized (monitor) {
                System.out.println("Contender entered");
            }
        }, "contender");

        holder.start();
        holderEntered.await();
        contender.start();
        contenderApproaching.await();

        releaseHolder.countDown();
        holder.join();
        contender.join();
        System.out.println("Finished");
    }
}
~~~

Chạy trên JDK 17 trở lên:

~~~bash
javac MonitorContentionDemo.java
java MonitorContentionDemo
~~~

Stdout khi không có external interruption:

~~~text
Holder entered
Holder leaving
Contender entered
Finished
~~~

**Phân tích:** `holder` lấy monitor trước khi báo `holderEntered`. `contender` không thể in “Contender entered” trước khi holder thoát `synchronized`. Main dùng `releaseHolder.countDown()` để cho holder hoàn tất rồi join hai thread.

`contenderApproaching.countDown()` chỉ báo thread đã đến trước câu lệnh đồng bộ; nó **không chứng minh contender đã kịp đến trạng thái BLOCKED** trước lúc main mở cổng. Muốn chụp đúng trạng thái BLOCKED, phải để holder giữ monitor trong lúc lấy thread dump hoặc quan sát `Thread.getState()` khi contender thực sự đang đợi. Đừng xem một lần chạy in đúng thứ tự là chứng minh đã đo được contention.

Một chi tiết cố ý trong demo: holder gọi `CountDownLatch.await()` **ngay khi đang giữ monitor**. Await trên latch không nhả intrinsic monitor đó, nên các contender có thể bị chặn trong lúc holder đợi. Đây là cách tái hiện tình huống **giữ khóa quá lâu** để học, không phải mẫu nên áp dụng cho business logic.

## 5. Vì sao critical section dài gây hại?

Độ dài critical section là thời gian mà một thread giữ lock từ lúc vào đến lúc ra. Khi nhiều thread tranh chấp, thời gian này góp phần quyết định độ trễ của tất cả contender.

Ví dụ ý niệm: 20 yêu cầu cùng tranh một monitor; mỗi holder giữ monitor 50 ms chỉ để xử lý việc nằm trong lock. Trong một lịch chạy tuần tự lý tưởng, 20 critical section đã chiếm khoảng 1.000 ms tổng thời gian giữ khóa, chưa kể scheduling và overhead; các yêu cầu đến sau có thể phải đợi nhiều lượt. Đây chỉ là **ước lượng minh họa**, không phải công thức đo latency thực của JVM.

Hệ quả thường gặp:

- **Lock convoy:** các thread lần lượt xếp hàng sau một holder chậm. Một vài lần xử lý kéo dài tạo đuôi latency lớn.
- **Throughput giảm:** công việc có thể chạy song song bên ngoài nhưng bị tuần tự hóa bên trong monitor.
- **Tail latency tăng:** trung bình có thể còn ổn nhưng p95/p99 của những request cần lock tăng mạnh.
- **Thread exhaustion:** trong thread pool có số worker hữu hạn, nhiều worker đợi lock khiến ít worker còn rảnh để làm việc khác.
- **Priority inversion:** thread có ưu tiên thấp hơn đang giữ lock mà thread khác cần; thread ưu tiên cao phải đợi. Java thread priority không cung cấp một giải pháp portable đảm bảo cho tình huống này.
- **Độ nhạy với lỗi:** I/O chậm, retry ngoài ý muốn hoặc callback ném exception có thể biến một critical section nhỏ thành điểm nghẽn lớn.

Với mỗi lock, hãy tìm **đường chạy chậm nhất**, không chỉ dòng mã trung bình. Một nhánh hiếm gọi mạng, xử lý file, chờ latch hoặc gọi method không rõ thời lượng vẫn có thể khiến hàng đợi phía sau tăng vọt.

## 6. Những thao tác rất nguy hiểm khi thực hiện trong monitor

### 6.1 I/O, mạng, cơ sở dữ liệu và remote call

~~~java
synchronized (lock) {
    updateLocalState();
    remoteClient.send(payload); // Có thể chậm, retry hoặc không trả về.
}
~~~

Đây là mảnh mã minh họa, không phải file runnable; `remoteClient`, `payload`, `updateLocalState` và `lock` là các thành phần giả định. Tất cả contender khác cùng lock phải đợi **trong suốt remote call**, ngay cả khi họ chỉ cần đọc một giá trị.

Một hướng thiết kế là chuẩn bị dữ liệu/snapshot dưới lock, nhả lock, thực hiện I/O bên ngoài. Tuy nhiên nếu kết quả I/O quyết định việc sửa state, cần thiết kế commit/validation lại để tránh **stale snapshot**. Không chỉ di chuyển dòng gọi ra ngoài lock mà bỏ qua tính đúng đắn.

### 6.2 `Thread.sleep()` và các phép chờ khác

~~~java
synchronized (lock) {
    Thread.sleep(500);
}
~~~

Mảnh này giả định method khai báo/xử lý `InterruptedException`. `sleep()` **không nhả monitor** đang giữ. Trong 500 ms, contender có thể bị BLOCKED dù thread holder không làm công việc hữu ích.

Tương tự, `CountDownLatch.await()`, `Future.get()` và `Thread.join()` không tự nhả **monitor không liên quan** mà thread đang giữ. Gọi chúng khi đang giữ lock có thể gây lock convoy hoặc deadlock nếu tác vụ được chờ lại cần chính lock đó.

Ngược lại, `Object.wait()` được gọi khi đang giữ monitor của **đúng object đó** sẽ nhả monitor đó và chờ theo giao thức wait/notify; khi tỉnh dậy, thread phải lấy lại monitor trước khi return. `wait()` **không nhả những monitor khác** mà thread đang giữ. Nó cũng cần vòng `while` kiểm tra predicate vì có thể có spurious wakeup.

**Không thay `sleep()` bằng `wait()` tùy tiện**: wait/notify là protocol điều kiện có yêu cầu sở hữu monitor, tín hiệu và kiểm tra predicate. Với task completion, ưu tiên `Future`/latch; với producer–consumer, cân nhắc `BlockingQueue`.

### 6.3 Callback và mã bên ngoài không kiểm soát

~~~java
synchronized (lock) {
    state = next;
    listener.onChanged(state);
}
~~~

Đây là mảnh mã minh họa với `state`, `next`, `listener` đã khai báo. Callback có thể gọi lại object hiện tại, lấy lock khác, chờ I/O hoặc ném exception. Dù monitor Java reentrant, callback lấy lock theo thứ tự khác có thể tạo vòng chờ giữa nhiều thread.

Hãy cân nhắc copy snapshot và danh sách listener trong vùng lock, rồi gọi callback **sau khi nhả khóa**. Nếu callback cần phản ánh thứ tự sự kiện chính xác, phải thiết kế hàng đợi sự kiện/sequence version thay vì giả định chuyển vị trí lệnh giữ nguyên toàn bộ semantics.

## 7. Giảm thời gian giữ monitor mà vẫn bảo vệ invariant

Mục tiêu là **làm ít việc nhất có thể khi sở hữu monitor**, nhưng vẫn giữ các điều kiện dữ liệu phải được cập nhật atomically.

Ví dụ cần tính checksum của nội dung lớn rồi cập nhật bộ đếm. Tính checksum trên dữ liệu **local/immutable** có thể làm trước khi lấy lock. Chỉ cộng kết quả vào trạng thái chia sẻ bên trong monitor.

~~~java
int checksum = calculateChecksum(immutableInput); // Không cần lock.
synchronized (lock) {
    aggregateChecksum += checksum;
    processedCount++;
}
~~~

Đây là mảnh minh họa, chưa có method/class độc lập. Giả định `immutableInput` không bị thread khác sửa trong lúc tính, và checksum không phụ thuộc trạng thái chia sẻ đã thay đổi. Cả hai trường `aggregateChecksum` và `processedCount` được cập nhật dưới **cùng lock**, nên vẫn có một ranh giới atomic hợp lý với các reader cũng dùng lock.

### 7.1 Mẫu Prepare → Lock → Commit

Một quy trình thông dụng:

1. **Prepare:** kiểm tra tham số, parse input, tính toán thuần, tạo value object candidate; không truy cập state mutable bị chia sẻ nếu chưa có snapshot hợp lệ.
2. **Lock:** lấy monitor đúng owner của invariant.
3. **Validate:** kiểm tra lại precondition **phụ thuộc state hiện tại** trong critical section.
4. **Commit:** cập nhật nhóm trường cần atomically; không gọi I/O hay callback ở giữa.
5. **Unlock:** thoát khối synchronized sớm, cho thread khác có cơ hội.
6. **Post-commit:** phát event/gửi I/O sau lock, với protocol idempotency/thứ tự rõ ràng nếu cần.

Mẫu này giúp critical section ngắn hơn. Nhưng nếu việc chuẩn bị dùng một snapshot có thể lỗi thời, hãy so sánh version/kiểm tra lại trong lock trước khi commit.

### 7.2 Tối ưu không được làm hỏng snapshot

Giả sử phải chuyển `available--` và `reserved++` để giữ `available + reserved == capacity`. Có thể tính trước các tham số chỉ phụ thuộc input, nhưng việc đọc `available`, kiểm tra điều kiện và thay **cả hai trường** phải cùng critical section.

~~~java
boolean reserveOne() {
    synchronized (lock) {
        if (available == 0) {
            return false;
        }
        available--;
        reserved++;
        return true;
    }
}
~~~

Đây là mảnh method minh họa có các field và lock giả định. Nếu reader cần quan sát tổng, reader phải dùng cùng lock và **đọc cả hai field trong một lần lock**. Hai getter synchronized riêng lẻ có thể trả hai snapshot khác nhau nếu writer chen giữa chúng.

## 8. Ví dụ Java 17+: critical section nhỏ, cập nhật chính xác

Tạo `SmallCriticalSectionDemo.java`:

~~~java
public final class SmallCriticalSectionDemo {
    private static final class Totals {
        private final Object lock = new Object();
        private int processed;
        private long sum;

        void record(int contribution) {
            synchronized (lock) {
                processed++;
                sum += contribution;
            }
        }

        Snapshot snapshot() {
            synchronized (lock) {
                return new Snapshot(processed, sum);
            }
        }
    }

    private record Snapshot(int processed, long sum) {}

    private static int prepareWork(int input) {
        // Mô phỏng phần tính toán thuần bằng dữ liệu local.
        return input * 2;
    }

    public static void main(String[] args) throws InterruptedException {
        Totals totals = new Totals();
        Runnable task = () -> {
            for (int i = 1; i <= 1_000; i++) {
                int contribution = prepareWork(i);
                totals.record(contribution);
            }
        };

        Thread a = new Thread(task, "worker-a");
        Thread b = new Thread(task, "worker-b");
        a.start();
        b.start();
        a.join();
        b.join();

        Snapshot snapshot = totals.snapshot();
        System.out.println("Processed: " + snapshot.processed());
        System.out.println("Sum: " + snapshot.sum());
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac SmallCriticalSectionDemo.java
java SmallCriticalSectionDemo
~~~

Stdout:

~~~text
Processed: 2000
Sum: 2002000
~~~

**Vì sao đúng?** Mỗi thread xử lý 1.000 giá trị, tổng 2.000 record. `prepareWork(i)` trả `i*2` và không đụng đến shared state, nên chạy ngoài monitor. `Totals.record()` giữ lock chỉ trong hai phép cập nhật. `snapshot()` đọc cả hai trường dưới cùng monitor. Tổng contribution của một thread là `2 × (1 + 2 + ... + 1000) = 1.001.000`; hai thread tạo `2.002.000`.

Không thể suy từ ví dụ nhỏ rằng thay đổi luôn nhanh hơn mọi phiên bản giữ lock dài; việc giảm lock scope thường có lợi khi phần prepare tốn thời gian. Nếu mọi phép tính phụ thuộc trực tiếp shared state thì phải cân bằng giữa correctness và mức tranh chấp.

## 9. Lock scope và sự đánh đổi về correctness

Một thay đổi tưởng như “tối ưu” có thể phá bảo đảm atomic:

~~~java
// Sai nếu check phụ thuộc state chia sẻ.
boolean canReserve;
synchronized (lock) {
    canReserve = available > 0;
}

// Thread khác có thể reserve hết quota tại đây.
if (canReserve) {
    synchronized (lock) {
        available--;
        reserved++;
    }
}
~~~

Đây là mảnh code lỗi, không phải chương trình độc lập. Kiểm tra và commit được chia thành **hai critical section khác nhau**, nên một thread khác có thể chen vào giữa. Tính đúng đắn yêu cầu kiểm tra lại precondition **trong cùng lần giữ lock** với cập nhật.

Cũng cần nghĩ đến lỗi và exception safety: `synchronized` nhả monitor nếu phát sinh exception, nhưng **không tự rollback** những phép ghi đã thực hiện trước exception. Nếu method cập nhật ba trường rồi gọi code có thể throw ở giữa, monitor được nhả với state có thể chưa nhất quán. Thiết kế **prepare/calculate all → validate → commit các phép gán an toàn**, hoặc có rollback đã kiểm chứng.

### 9.1 Snapshot/version khi tính toán ngoài lock

Nếu phép tính nặng phụ thuộc state hiện tại, có thể áp dụng optimistic pattern:

~~~text
lock:
    snapshot = copy(state, version)
unlock

heavyComputation(snapshot)  // có thể mất nhiều thời gian

lock:
    if (version đã đổi) retry hoặc từ chối
    else commit(candidate), tăng version
unlock
~~~

Đây là **mã giả**, không phải Java runnable. Việc snapshot phải đầy đủ và không chứa reference đến object mutable có thể tiếp tục thay đổi ngoài lock. Nếu version thay đổi, kết quả prepare có thể lỗi thời; đừng commit bất chấp.

Nếu phép tính có side effect không thể lặp an toàn (gửi tiền, gọi dịch vụ ngoài), retry cần cơ chế idempotency hoặc chuyển sang quy trình transaction rõ ràng. Không đưa side effect vào phần có thể được thực hiện lại mà không kiểm soát.

## 10. Các kiểu deadlock do giữ monitor khi chờ

Một lỗi đặc biệt nguy hiểm: holder giữ monitor rồi đợi một thread/task mà để hoàn thành lại cần monitor đó.

~~~java
Object lock = new Object();

Thread worker = new Thread(() -> {
    synchronized (lock) {
        // Worker cần lock để hoàn tất.
    }
});

synchronized (lock) {
    worker.start();
    worker.join(); // Caller vẫn giữ lock.
}
~~~

Đây là **mảnh minh họa lỗi**, method chứa nó phải xử lý `InterruptedException`. Caller giữ `lock` trong lúc `join()`; worker không vào được monitor nên không thể hoàn tất; caller lại đợi worker, tạo vòng chờ. `join()` **không giải phóng lock tùy ý** mà caller đang giữ.

Một cách sửa:

~~~java
worker.start();
worker.join(); // Chờ khi không giữ lock mà worker cần.
~~~

Đây cũng là mảnh code, giả định `worker` đã được xây dựng và method xử lý interruption.

Deadlock với hai monitor có thể xảy ra khi:

~~~text
Thread A: owns lock1, waits lock2
Thread B: owns lock2, waits lock1
~~~

Nếu thật sự cần nhiều lock, dùng **thứ tự khóa toàn cục** theo ID ổn định, nhất quán trên mọi đường gọi, và tránh callback có thể lấy lock khác ngược thứ tự. Với state thuộc cùng một invariant, một owner lock có thể đơn giản hơn.

**Phân biệt:**

- Contented monitor: các contender có thể tiến triển khi holder cuối cùng nhả lock.
- Deadlock: các participant tạo vòng phụ thuộc, không participant nào trong vòng có thể tự giải phóng chờ.
- Starvation: một thread không được phục vụ trong thời gian không giới hạn dù thread khác tiến triển; intrinsic monitor không có bảo đảm FIFO.
- Livelock: các thread vẫn chạy/phản ứng nhưng không hoàn thành công việc hữu ích.

Chỉ đo CPU sử dụng cao hay thấp không đủ để phân biệt những trường hợp này; cần dữ liệu về thread state, lock ownership và giao thức chờ.

## 11. Intrinsic monitor không có timed hoặc interruptible acquisition

Với `synchronized` thông thường, thread đang chờ **lấy monitor** không có API cho việc chỉ chờ tối đa N millisecond hoặc hủy việc chờ bằng `InterruptedException` như `lockInterruptibly()`. Nếu thread bị gọi `interrupt()` khi đang BLOCKED để lấy monitor, nó không tự bỏ yêu cầu lấy khóa ngay; interrupted flag có thể được ghi nhận để code xử lý sau khi đi tiếp.

Điều đó khác với `Object.wait()` khi thread đã vào monitor và chủ động nhả monitor để đợi điều kiện: wait là interruptible và yêu cầu sở hữu monitor đúng object.

Nếu cần giới hạn thời gian lấy lock hoặc xử lý cancellation trong lúc đợi, cân nhắc `ReentrantLock`:

- `tryLock()`: thử lấy lock ngay; trả `true/false`.
- `tryLock(timeout, unit)`: đợi có thời hạn, có thể ném `InterruptedException`.
- `lockInterruptibly()`: cho phép interruption khi đang chờ lock.
- `lock()`: đợi lấy lock theo hợp đồng không cùng semantics hủy như `lockInterruptibly()`.

Một lưu ý: `ReentrantLock` bảo đảm exclusion và memory effects tương tự monitor khi dùng đúng; nó **không** tự làm critical section ngắn lại. Nếu bạn vẫn gọi I/O chậm trong khi giữ ReentrantLock, contention vẫn tồn tại.

## 12. Ví dụ Java 17+: ReentrantLock.tryLock có timeout

Ví dụ này giữ lock bằng một thread rồi yêu cầu thread khác thử lấy lock trong thời hạn ngắn. Latch bảo đảm holder chưa nhả trước khi contender hoàn tất việc thử.

Tạo `TimedLockDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public final class TimedLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch holderHasLock = new CountDownLatch(1);
        CountDownLatch releaseHolder = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            lock.lock();
            try {
                holderHasLock.countDown();
                releaseHolder.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                lock.unlock();
            }
        }, "holder");

        Thread contender = new Thread(() -> {
            try {
                boolean acquired = lock.tryLock(100, TimeUnit.MILLISECONDS);
                System.out.println("Acquired: " + acquired);
                if (acquired) {
                    try {
                        // Bảo vệ state nếu lấy được lock.
                    } finally {
                        lock.unlock();
                    }
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "contender");

        holder.start();
        holderHasLock.await();
        contender.start();
        contender.join();
        releaseHolder.countDown();
        holder.join();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac TimedLockDemo.java
java TimedLockDemo
~~~

Stdout khi không có external interruption:

~~~text
Acquired: false
~~~

**Vì sao xác định?** Holder không nhả lock cho đến khi main gọi `releaseHolder.countDown()`. Main chỉ mở cổng **sau khi contender kết thúc**, nên contender phải hết thời gian thử lock mà không thể lấy được khóa. Ngay cả nếu contender được scheduler cho chạy muộn, holder vẫn giữ lock cho đến khi contender hoàn thành.

`tryLock(100, TimeUnit.MILLISECONDS)` giới hạn **thời gian chờ để lấy lock** chứ không giới hạn toàn bộ tác vụ hoặc công việc sau khi lấy lock. Trong code thật, đừng dùng một timeout nhỏ tùy ý để thay SLA; xác định deadline ở cấp yêu cầu và xử lý nhánh không lấy được lock. Đảm bảo mọi nhánh đã acquire đều `unlock()` trong `finally`.

**Lưu ý:** ví dụ diễn giải đường thành công/thất bại khi không bị interrupt bởi tác nhân bên ngoài. Trong chương trình thực tế, cần thiết kế shutdown/cancellation để các latch được giải phóng và các thread được join theo chính sách rõ.

## 13. Điều kiện chờ đúng: `Object.wait()` và `Condition.await()`

Có trường hợp thread giữ lock nhưng cần chờ **một điều kiện dữ liệu** do thread khác thay đổi. Nếu đợi trong lúc vẫn giữ monitor, thread thay đổi điều kiện có thể không thể vào vùng khóa để phát tín hiệu.

Sử dụng monitor wait đúng cách:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    // ready đang đúng dưới monitor lock.
}
~~~

Mảnh code giả định `lock` và `ready` tồn tại và method xử lý `InterruptedException`. `wait()`:

1. Yêu cầu thread đang sở hữu monitor của `lock`.
2. **Nhả monitor `lock`** trong lúc đợi để thread khác có thể vào và thay đổi predicate.
3. Khi thức dậy, phải reacquire monitor rồi mới trả về từ `wait()`.
4. Có thể tỉnh dậy giả (*spurious wakeup*), nên **luôn** kiểm tra predicate trong vòng `while`, không chỉ `if`.
5. Không tự nhả những monitor khác mà thread đang giữ.

Thread thay đổi trạng thái phải dùng cùng monitor và thông báo theo protocol:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
~~~

Đây là mảnh minh họa. `notifyAll()` đánh thức các waiter để họ cạnh tranh reacquire monitor; không lập tức giao CPU hoặc làm các waiter vào critical section ngay. Nếu state chứa nhiều điều kiện phức tạp, cân nhắc `java.util.concurrent.locks.Condition` cùng `ReentrantLock`, hoặc dùng `BlockingQueue`/`CountDownLatch`/`Semaphore` nếu chúng khớp bài toán hơn.

Không thay toàn bộ `wait/notify` thành `sleep` rồi polling; nó vừa làm mất ý nghĩa predicate, vừa làm thời gian phản ứng khó kiểm soát.

## 14. Quan sát contention bằng thread dump và JVM tooling

Khi một ứng dụng Java có latency tăng, hãy kiểm tra liệu nhiều thread đang chờ cùng monitor không. Công cụ khả dụng tùy JDK/JVM và môi trường, nhưng tư duy quan sát là thống nhất:

### 14.1 Thread dump

Có thể tạo thread dump bằng công cụ JDK phù hợp, ví dụ trên HotSpot:

~~~bash
jcmd <pid> Thread.print -l
~~~

`<pid>` là **placeholder của PID tiến trình Java**, không phải một lệnh đầy đủ để chạy nguyên văn. Output tùy JDK nhưng thường cho thấy tên thread, trạng thái và vùng stack hiện tại. Tìm:

- Nhiều thread `BLOCKED` ở cùng method/monitor.
- Dòng cho biết thread đang “waiting to lock” monitor và object/owner tương ứng khi JVM xuất thông tin đó.
- Thread holder và stack của nó: có `Thread.sleep`, I/O, gọi phương thức ngoài, xử lý dữ liệu lớn hoặc chờ task khác trong lúc giữ lock không?
- Dấu hiệu vòng chờ giữa lock A/B, hoặc thread giữ lock rồi chờ completion của worker cần lock ấy.

Đừng kết luận chỉ từ **một** thread `BLOCKED` rằng có deadlock. Contention ngắn có thể là bình thường; cần xem số contender, độ dài, tần suất và khả năng tiến triển.

### 14.2 ThreadMXBean

`java.lang.management.ThreadMXBean` có thể hỗ trợ đọc trạng thái, locked monitors, deadlock và một số thống kê contention (phụ thuộc JVM và cấu hình). Ví dụ:

~~~java
ThreadMXBean bean = ManagementFactory.getThreadMXBean();
long[] deadlocked = bean.findDeadlockedThreads();
~~~

Đây là mảnh mã minh họa cần import `java.lang.management.ManagementFactory` và `java.lang.management.ThreadMXBean`. API trả về `null` khi không tìm thấy deadlock thuộc phạm vi có thể phát hiện; không có kết quả **không chứng minh** không có starvation, livelock, I/O wait hoặc mọi vòng phụ thuộc tác vụ.

`isThreadContentionMonitoringSupported()` cho biết JVM có hỗ trợ thống kê blocked/waited time hay không. Khi được hỗ trợ, có thể bật bằng `setThreadContentionMonitoringEnabled(true)` nếu có quyền và cần đo; việc thu thập có overhead và các số đo là dữ liệu runtime theo khả năng JVM, không phải SLA bảo đảm.

### 14.3 Java Flight Recorder

JFR có event phục vụ phân tích monitor contention, trong đó có `jdk.JavaMonitorEnter` trên những JDK hỗ trợ. Event có threshold/cấu hình thu thập, nên không phải mọi lần lấy monitor đều được ghi lại. Kiểm tra cấu hình recording, thời điểm thu thập, thread liên quan và stack trace để tìm critical section chậm.

JFR hữu ích để so sánh mức contention **trước/sau** một thay đổi code. Một số công cụ profiler còn đo thời gian giữ lock và thời gian đợi; cần phân biệt hai đại lượng này để tránh tối ưu sai chỗ.

## 15. Những điều cần đo khi cải thiện lock

Đừng đánh giá một bản sửa bằng một lần chạy “nhanh hơn”. Hãy đo theo workload có tranh chấp thực tế:

| Chỉ số | Giúp trả lời câu hỏi |
| --- | --- |
| **Blocked time / contention count** | Thread đợi monitor bao nhiêu lần và bao lâu? |
| **Critical-section hold time** | Holder giữ lock trong bao lâu? Có outlier bất thường? |
| **Throughput** | Hệ thống hoàn thành bao nhiêu operation mỗi giây dưới tải? |
| **p95/p99 latency** | Những request chậm nhất bị ảnh hưởng thế nào? |
| **Thread pool saturation** | Bao nhiêu worker bận chờ lock, queue backlog ra sao? |
| **CPU utilization / context switching** | Có nhiều thread tranh CPU hoặc overhead do contention không? |
| **Correctness invariants** | Bản tối ưu có giữ kết quả chính xác, không mất cập nhật không? |

Cùng một phép đo có thể phản ánh nhiều nguyên nhân. Ví dụ blocked time tăng có thể do hold time dài, số contender tăng hoặc một đường code mới phải dùng lock. Cần xem tương quan giữa nguyên nhân và tải, không chỉ quy kết cho từ khóa `synchronized`.

Nếu critical section rất ngắn và contention hiếm, giữ một lock đơn giản thường có lợi về tính rõ ràng. Tăng độ phức tạp bằng lock striping hoặc CAS không chắc cải thiện khi chi phí conflict/GC/retry lớn hơn.

## 16. Các hướng tối ưu nâng cao và giới hạn

### 16.1 Giảm phạm vi hoặc số lần cần lấy lock

Gộp các cập nhật mà về nghiệp vụ có thể batch để giảm số lần acquire, nhưng đừng giữ monitor lâu hơn chỉ để xử lý batch khổng lồ. Cân nhắc trade-off giữa kích thước batch, độ trễ của contender và invariant cần bảo vệ.

### 16.2 Tách state độc lập

Nếu hai nhóm dữ liệu **không cùng invariant**, có thể mỗi nhóm có lock riêng hoặc một object owner riêng. Nhưng nếu một báo cáo yêu cầu snapshot nhất quán trên cả hai nhóm, tách lock làm bài toán atomic snapshot khó hơn. Không nên chia lock theo từng field của cùng một invariant chỉ để bớt contention.

### 16.3 Immutable snapshot + atomic update

Nếu state có thể biểu diễn như một immutable value object, một `AtomicReference<State>` cho phép reader lấy **một reference snapshot** mà không phải giữ monitor. Writer có thể tạo state mới rồi commit bằng `compareAndSet`. Đây là cách khác để giữ invariant đa trường, nhưng CAS có thể retry nhiều lần dưới tranh chấp, tạo object mới và đòi hỏi tránh side effect không idempotent trong phần thử lại.

### 16.4 Cấu trúc dữ liệu concurrent tiêu chuẩn

`ConcurrentHashMap`, `BlockingQueue`, `LongAdder` và các primitive trong `java.util.concurrent` có những hợp đồng riêng, phù hợp nhiều workload. Ví dụ `LongAdder` hữu ích cho thống kê throughput cao khi nhiều writer cùng cộng, nhưng `sum()` trong lúc update đồng thời **không phải atomic snapshot** của mọi cell; không dùng nó để bảo vệ invariant thanh toán đòi con số chính xác ngay tại mọi thời điểm.

Không có primitive “tốt nhất” cho mọi bài toán. Nếu throughput tăng nhưng xuất hiện inconsistency hoặc bỏ mất tính chất snapshot, tối ưu đã làm đổi hợp đồng nghiệp vụ.

### 16.5 Virtual threads và monitor contention

Trong Java 21+, virtual threads có thể giúp một lượng lớn tác vụ chờ I/O mà không cần gắn một platform thread cố định cho từng task. Tuy nhiên **virtual thread không biến một monitor thành nhiều monitor**: nhiều virtual threads tranh cùng `synchronized(lock)` vẫn phải tuần tự trong critical section, nên lock contention và hold time dài vẫn là nút thắt logic.

Những chi tiết triển khai scheduler, pinning và tối ưu liên quan `synchronized` đã thay đổi giữa các phiên bản JDK. Khi đánh giá hiệu năng virtual threads, cần kiểm tra **phiên bản JDK cụ thể và profiler thực tế**, không áp dụng một kết luận về pinning của một JDK cho mọi phiên bản.

## 17. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Giữ `synchronized` khi gọi HTTP/database/file I/O. | Các contender cùng monitor chờ theo thời gian I/O. | Prepare/snapshot dưới lock, I/O ngoài lock, validate/commit lại đúng protocol. |
| `Thread.sleep()` trong critical section. | Thread ngủ nhưng vẫn giữ monitor. | Di chuyển sleep/chờ ra ngoài lock nếu có thể. |
| `CountDownLatch.await()` hoặc `Future.get()` khi giữ monitor worker cần. | Lock convoy hoặc deadlock phụ thuộc task. | Đợi ở ngoài vùng lock; xem lại đồ thị phụ thuộc. |
| Callback dưới monitor và callback lấy lock khác. | Lock-order inversion, deadlock, độ trễ khó đoán. | Gọi callback sau lock với snapshot/ordering phù hợp. |
| Dùng hai monitor khác nhau cho một invariant. | Mutual exclusion/visibility không áp dụng cho toàn trạng thái. | Một owner lock hoặc giao thức đa lock đã chứng minh đúng. |
| Chỉ synchronized writer mà getter không theo lock. | Reader có thể nhìn trạng thái trung gian/thiếu HB. | Đọc snapshot dưới cùng protocol. |
| Chia check và update ra hai critical section. | Thread khác chen vào; quota oversubscription/lost update. | Check lại và commit trong cùng critical section. |
| Nghĩ `Thread.interrupt()` hủy ngay thread `BLOCKED` chờ monitor. | Cancellation không có hiệu lực kỳ vọng. | Dùng primitive hỗ trợ interruptible/timed acquisition nếu cần. |
| Xem mọi thread `WAITING` là monitor contention. | Chẩn đoán sai do latch, future, park, I/O. | Phân biệt `BLOCKED` với trạng thái chờ khác; xem stack/owner. |
| Coi fairness của intrinsic monitor là FIFO. | Một contender có thể bị chờ lâu hơn dự kiến. | Thiết kế policy fairness bằng primitive phù hợp nếu có yêu cầu. |
| Thêm lock mới mà không đo tải và kiểm invariant. | Có thể giảm throughput hoặc tạo deadlock mới. | Đo latency/contention, test correctness, review lock ordering. |

## 18. Checklist khi phát hiện monitor contended

1. **Xác định lock identity.** Những thread đang tranh có cùng monitor thật không? Là `this`, `Class` hay private object?
2. **Xác định holder.** Thread nào sở hữu lock? Stack holder đang thực hiện gì?
3. **Đo hold time và blocked time.** Contention do hoạt động thường xuyên hay có một nhánh chậm bất thường?
4. **Tìm blocking operation trong critical section.** Có I/O, sleep, join, Future, latch, callback hoặc nested lock không?
5. **Viết invariant.** Những trường/operation nào thực sự phải đi cùng monitor? Reader có cần snapshot?
6. **Đề xuất phạm vi tối thiểu.** Đưa công việc local/immutable ra ngoài, giữ check + commit state trong lock.
7. **Xem lại exception và cancellation.** Thao tác bị lỗi có bỏ dở state hoặc giữ thread chờ vô hạn không?
8. **Xem lại lock ordering.** Các call path khác có lấy lock theo thứ tự ngược hoặc gọi callback giữ thêm lock không?
9. **Kiểm chứng** bằng test concurrency và profiling trước/sau dưới cùng tải.
10. **Chỉ thay primitive khi có lý do.** `ReentrantLock`, atomic state hoặc concurrent collection thay đổi hợp đồng, cần review lại correctness.

## 19. Câu hỏi tự kiểm tra

**1.** Một thread đang `BLOCKED` chờ `synchronized(lock)` thường bị chặn ở bước nào?  
**Đáp:** Ở bước lấy intrinsic monitor đang do thread khác sở hữu.

**2.** Thread holder gọi `Thread.sleep(500)` trong `synchronized(lock)` có nhả monitor không?  
**Đáp:** Không. `sleep` tạm dừng thread, nhưng lock vẫn do nó sở hữu.

**3.** `Object.wait()` trên object lock nhả những lock nào?  
**Đáp:** Nhả monitor của chính object được wait, không tự nhả các monitor khác đang sở hữu; khi trở lại từ wait, phải lấy lại monitor đó.

**4.** Hai method đều `synchronized` có chắc tranh cùng monitor không?  
**Đáp:** Không. Instance synchronized khóa `this`; static synchronized khóa `Class` object; hai instance khác nhau có monitor khác nhau.

**5.** Vì sao main giữ lock rồi `join()` worker cần cùng lock có thể deadlock?  
**Đáp:** Main chờ worker kết thúc nhưng worker không thể lấy lock do main giữ; join không tự giải phóng monitor của main.

**6.** `interrupt()` một contender chờ intrinsic monitor có bảo đảm nó bỏ chờ ngay không?  
**Đáp:** Không. Chờ lấy intrinsic monitor không có cùng semantics interruptible acquisition của `ReentrantLock.lockInterruptibly()`.

**7.** Nếu chuyển check quota ra ngoài synchronized còn update vẫn trong lock thì có an toàn không?  
**Đáp:** Không nếu không kiểm tra lại dưới lock; một thread khác có thể thay state giữa check và update.

**8.** Vì sao một `ReentrantLock` không tự xử lý contention dài?  
**Đáp:** Vì thời gian giữ lock vẫn phụ thuộc code bên trong. ReentrantLock thêm các cơ chế lấy khóa có timeout/interruption, không tự giảm hold time.

**9.** Thread dump thấy 20 thread `BLOCKED` có chứng minh deadlock không?  
**Đáp:** Chưa. Cần xem lock owner, đường chạy của holder, tiến triển theo thời gian và vòng phụ thuộc.

**10.** Một thay đổi tối ưu critical section cần đạt những gì?  
**Đáp:** Giữ invariant, HB/visibility và atomicity như cũ, đồng thời cải thiện blocked time/latency/throughput được đo trên workload phù hợp.

**Ghi nhớ:** Monitor contention xuất hiện khi nhiều thread cùng muốn một intrinsic lock. **Giữ khóa ngắn, bảo vệ đúng invariant và không chờ việc ngoài trong lúc giữ khóa** là những nguyên tắc thiết kế chính. Khi cần timeout/cancellation ở bước lấy khóa, dùng primitive có hợp đồng phù hợp; khi điều tra ứng dụng chậm, phân biệt trạng thái `BLOCKED`, `WAITING` và tìm chính xác holder cùng thời gian giữ monitor.