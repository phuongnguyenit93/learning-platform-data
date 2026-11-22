# Reentrant synchronization là gì trong Java?

## 1. Định nghĩa và lý do cần reentrancy

**Reentrant synchronization** (đồng bộ tái nhập) có nghĩa: **một thread đang sở hữu một khóa được phép lấy lại chính khóa đó** mà không tự chặn mình. Quy tắc loại trừ các thread khác vẫn giữ nguyên: thread khác không thể chiếm khóa khi owner chưa nhả hết các lần giữ.

Java có hai cơ chế quan trọng:

- **Intrinsic monitor của `synchronized`:** một thread có thể vào thêm những khối hoặc phương thức synchronized sử dụng **cùng monitor**.
- **`ReentrantLock` trong `java.util.concurrent.locks`:** cùng thread có thể gọi `lock()` lồng nhau; khóa theo dõi số lần giữ (*hold count*) và phải có số lần `unlock()` tương ứng.

Reentrant giúp phương thức có khóa gọi helper có khóa, gọi đệ quy hoặc gọi phương thức của lớp cha mà **không bị tự kẹt khi lấy lại cùng khóa**. Nó không có nghĩa nhiều thread được đồng thời chạy vùng critical section.

**Điểm quyết định:** reentrancy gắn với **cùng một thread và cùng một đối tượng khóa**, không gắn với tên biến, tên phương thức hay việc hai object cùng kiểu. Thread giữ monitor của instance A vẫn có thể phải chờ monitor của instance B.

## 2. Monitor của `synchronized` tái nhập như thế nào?

Các dạng thường gặp:

```java
// Snippet: lockObject là tham chiếu tới đối tượng khóa đã khai báo.
synchronized (lockObject) {
    // Vùng tới hạn.
}
```

- `synchronized (object)` lấy monitor của **object**.
- Phương thức instance `synchronized` lấy monitor của `this`.
- Phương thức `static synchronized` lấy monitor của `Class` object, ví dụ `Account.class`. Monitor class **khác** monitor instance.

JVM quản lý quyền sở hữu và số tầng tái nhập. Khi owner vào cùng monitor thêm lần nữa, mức giữ tăng. Khi thoát một tầng, mức giữ giảm. Thread khác chỉ có thể lấy monitor sau khi owner đã thoát hết các tầng.

**Khác với khóa tường minh:** thoát khối hoặc phương thức synchronized tự nhả monitor đúng số mức, kể cả khi `return` hoặc exception. Không cần và không thể gọi một `unlock()` cho intrinsic monitor như với `ReentrantLock`.

### Ví dụ Java 17+ hoàn chỉnh

Tạo tệp `IntrinsicReentrancy.java`:

```java
public class IntrinsicReentrancy {
    private int balance = 10;

    public synchronized void withdraw(int amount) {
        System.out.println("Outer entered");
        decrease(amount);
        System.out.println("Outer resumed");
    }

    private synchronized void decrease(int amount) {
        balance -= amount;
        System.out.println("Inner balance: " + balance);
    }

    public synchronized int balance() {
        return balance;
    }

    public static void main(String[] args) {
        IntrinsicReentrancy account = new IntrinsicReentrancy();
        account.withdraw(3);
        System.out.println("Final balance: " + account.balance());
    }
}
```

Chạy:

```bash
javac IntrinsicReentrancy.java
java IntrinsicReentrancy
```

Đầu ra:

```text
Outer entered
Inner balance: 7
Outer resumed
Final balance: 7
```

Thread main lấy monitor của `account` khi vào `withdraw`, rồi tái nhập chính monitor đó khi gọi `decrease`. Khi `decrease` trả về, `withdraw` **vẫn giữ monitor**; chỉ khi `withdraw` kết thúc, monitor mới được giải phóng hoàn toàn đối với lời gọi này. Phương thức `balance` dùng cùng monitor để đọc.

Ví dụ chỉ minh họa cơ chế reentry; `withdraw` không kiểm tra số dư, nên không phải thiết kế giao dịch tài chính đầy đủ. Khi thread khác gọi phương thức synchronized của **cùng account**, thread đó phải chờ owner thoát hết các tầng.

### Reentry qua đệ quy và kế thừa

Một phương thức synchronized có thể tự gọi hoặc gọi tiếp helper synchronized trên cùng receiver. Mỗi tầng đệ quy lấy lại monitor được sở hữu bởi cùng thread. Reentrancy **không** ngăn đệ quy vô hạn hoặc `StackOverflowError`, chỉ tránh self-deadlock tại monitor.

Lớp con gọi `super.someSynchronizedMethod()` trên cùng receiver cũng tái nhập được nếu cả hai khóa `this`. Nhưng `synchronized(other)` dùng monitor khác; static synchronized cũng không dùng monitor của receiver.

## 3. `ReentrantLock`, owner thread và hold count

`ReentrantLock` là khóa tường minh có thể tái nhập, hỗ trợ thêm `tryLock()`, `lockInterruptibly()`, `newCondition()`, và `getHoldCount()`.

Mẫu an toàn khi lấy khóa:

```java
// Snippet: lock là ReentrantLock đã khai báo.
lock.lock();
try {
    // Thao tác trên trạng thái được bảo vệ.
} finally {
    lock.unlock();
}
```

`finally` bảo đảm unlock cả khi có exception. Chỉ gọi `unlock()` nếu acquisition đã thành công. Không nên đặt `unlock()` trong một `finally` chạy sau khi `tryLock()` trả về false.

| Hành động của thread T | Hold count của T | Hệ quả |
| --- | --- | --- |
| T lấy lock đang rảnh | 1 | T trở thành owner |
| T gọi `lock()` lại cùng lock | 2 | T vẫn là owner |
| T gọi `unlock()` một lần | 1 | Thread khác vẫn phải đợi |
| T gọi `unlock()` lần thứ hai | 0 | Khóa được giải phóng |

`getHoldCount()` đếm số lần **thread hiện tại** giữ khóa. `isHeldByCurrentThread()` kiểm tra owner của thread gọi. Không nên suy ra một snapshot về trạng thái thread khác từ những phương thức này.

### Ví dụ Java 17+ với hold count

Tạo tệp `ReentrantLockDepth.java`:

```java
import java.util.concurrent.locks.ReentrantLock;

public class ReentrantLockDepth {
    private final ReentrantLock lock = new ReentrantLock();

    private void outer() {
        lock.lock();
        try {
            System.out.println("Outer: " + lock.getHoldCount());
            inner();
            System.out.println("Back in outer: " + lock.getHoldCount());
        } finally {
            lock.unlock();
        }
        System.out.println("After outer: " + lock.getHoldCount());
    }

    private void inner() {
        lock.lock();
        try {
            System.out.println("Inner: " + lock.getHoldCount());
        } finally {
            lock.unlock();
        }
    }

    public static void main(String[] args) {
        new ReentrantLockDepth().outer();
    }
}
```

Chạy:

```bash
javac ReentrantLockDepth.java
java ReentrantLockDepth
```

Đầu ra:

```text
Outer: 1
Inner: 2
Back in outer: 1
After outer: 0
```

Chỉ một thread thực hiện mã, nhưng nó lấy cùng lock hai lần. `inner` nhả một mức, `outer` nhả mức còn lại. Nếu `inner` quên unlock, sau khi `outer` unlock khóa vẫn còn hold count 1, khiến thread khác có thể chờ mãi. Nếu thread không phải owner gọi `unlock()`, hoặc unlock quá số lần sở hữu, `ReentrantLock` ném `IllegalMonitorStateException`.

**Kết luận thực hành:** mỗi lần `lock()` thành công cần một `unlock()` tương ứng. Cả `synchronized` và `ReentrantLock` đều tái nhập, nhưng một bên có lexical scope tự nhả, bên kia cần lập trình viên cân bằng thủ công.

## 4. Reentrancy không làm mất mutual exclusion

Tái nhập chỉ được phép cho **thread chủ sở hữu**, chứ không trao quyền cho thread khác chen vào. Xem một class với monitor private:

```java
final class Counter {
    private final Object mutex = new Object();
    private int count;

    public void incrementTwice() {
        synchronized (mutex) {
            incrementOne();
            incrementOne();
        }
    }

    private void incrementOne() {
        synchronized (mutex) {
            count++;
        }
    }

    public int get() {
        synchronized (mutex) {
            return count;
        }
    }
}
```

Đây là class phụ trợ, chưa có `main`. Khi thread T vào `incrementTwice`, T giữ mutex. Hai lần gọi `incrementOne` lấy lại cùng mutex, nên T chạy được. Một thread U cố `get` hay `incrementTwice` phải đợi cho đến khi T nhả hết.

Dùng `private final Object mutex` giúp giữ quyền kiểm soát lock của object, tránh caller cố tình hoặc vô tình giữ monitor bên ngoài. Nếu helper khóa **một đối tượng khác**, đó không phải reentry và có thể bị chặn.

### Ví dụ Java 17+: nhiều worker và khóa lồng nhau

Tạo tệp `NestedCounter.java`:

```java
public class NestedCounter {
    private final Object mutex = new Object();
    private int count;

    public void addBatch(int size) {
        synchronized (mutex) {
            for (int i = 0; i < size; i++) {
                incrementOne();
            }
        }
    }

    private void incrementOne() {
        synchronized (mutex) {
            count++;
        }
    }

    public int get() {
        synchronized (mutex) {
            return count;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        NestedCounter counter = new NestedCounter();
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> counter.addBatch(1_000));
            workers[i].start();
        }
        for (Thread worker : workers) {
            worker.join();
        }
        System.out.println("Final count: " + counter.get());
    }
}
```

Chạy:

```bash
javac NestedCounter.java
java NestedCounter
```

Đầu ra:

```text
Final count: 4000
```

Bốn thread cập nhật cùng bộ đếm; thứ tự scheduling có thể khác nhau nhưng kết quả luôn là 4.000 khi tất cả hoàn tất. Monitor chung ngăn hai thread cùng sửa `count`; trong mỗi thread, helper được tái nhập cùng monitor. `join()` giúp main đợi đủ worker trước khi đọc kết quả.

Việc khóa lồng nhau trên từng bước ở đây là có chủ đích để minh họa. Với vòng lặp lớn, có thể viết một helper yêu cầu caller đã giữ khóa để giảm overhead, nhưng phải thực thi nhất quán tiền điều kiện đó. Reentrancy không có nghĩa mọi helper đều nên tự khóa.

## 5. Self-deadlock và giới hạn của reentrancy

**Self-deadlock** có thể xuất hiện nếu một thread đang giữ tài nguyên rồi lại chờ chính tài nguyên ấy bằng một cơ chế không tái nhập. Ví dụ `Semaphore(1)` không theo dõi owner như `ReentrantLock`: một thread `acquire()` hai lần mà không có `release()` ở giữa sẽ phải chờ permit thứ hai, có thể chặn vô thời hạn. Không nên chạy ví dụ gây treo này như một chương trình demo.

Với monitor Java hoặc `ReentrantLock`, owner có thể lấy lại **chính khóa đang giữ**, nên tránh được dạng self-deadlock do reentry.

Nhưng **reentrancy không tránh được deadlock giữa các khóa khác nhau**:

```text
Thread T1                  Thread T2
---------                  ---------
giữ lock A                 giữ lock B
chờ lock B                 chờ lock A
       \                    /
          vòng chờ khóa
```

A và B có thể đều là `ReentrantLock`. T1 không sở hữu B; T2 không sở hữu A. Vì vậy reentrancy không giúp họ vượt qua vòng chờ.

Các cách phòng tránh gồm áp dụng thứ tự lấy nhiều khóa thống nhất, tránh chờ I/O hoặc gọi callback khi đang giữ nhiều lock, hạn chế critical section, cân nhắc `tryLock(timeout, unit)` nếu có đường phục hồi, và phân tích thread dump/JFR khi xảy ra bế tắc.

**Trường hợp dễ nhầm:** thread T giữ lock L rồi gọi `worker.join()` trong khi worker cần L để kết thúc. T chờ worker, worker chờ L do T giữ: đây cũng là deadlock dù L reentrant. Không giữ khóa mà worker cần khi chờ worker.

## 6. So sánh `synchronized` và `ReentrantLock`

| Đặc điểm | `synchronized` | `ReentrantLock` |
| --- | --- | --- |
| Có tái nhập | Có | Có |
| Khóa của | Monitor object hoặc `Class` object | Instance `ReentrantLock` |
| Giải phóng khi exception | Tự nhả khi thoát scope | Phải `unlock()` trong `finally` |
| Số lần giữ | JVM quản lý, không có API `getHoldCount` | Có `getHoldCount()` |
| Lấy khóa không chờ | Không có `tryEnter` của cú pháp | `tryLock()` |
| Lấy khóa có timeout | Không có monitor acquisition timeout | `tryLock(long, TimeUnit)` |
| Lấy khóa có thể interrupt | Không có dạng acquisition tương đương | `lockInterruptibly()` |
| Điều kiện chờ | `wait()`, `notify()`, `notifyAll()` | `Condition.await()`, `signal()` |
| Fairness | Không cấu hình trực tiếp | Có tùy chọn `new ReentrantLock(true)` |

**Fair lock không đảm bảo OS scheduling công bằng hay thứ tự hoàn thành tác vụ**. Ngay trên fair `ReentrantLock`, `tryLock()` không timeout có thể lấy ngay khi khóa đang rảnh dù còn thread đang chờ. Không dùng fairness để chứng minh một yêu cầu nghiệp vụ phải hoàn thành trước yêu cầu khác.

Nếu chỉ cần vùng bảo vệ ngắn và không cần API bổ sung, `synchronized` thường dễ duy trì. Dùng `ReentrantLock` khi thật sự cần timeout, khả năng hủy việc đợi lấy khóa hoặc các condition độc lập.

## 7. `wait()`, `Condition.await()` và reentrant lock

Khi thread đang giữ lock rồi cần **đợi một điều kiện**, phải phân biệt việc **tái nhập khóa** với việc **nhả khóa tạm để chờ**:

- `Object.wait()` cần được gọi khi thread đang sở hữu đúng monitor object. Khi đợi, thread nhả monitor **đó** với số mức tái nhập thích hợp và phải lấy lại trước khi `wait()` trở về. Nó không tự nhả các monitor khác.
- `Condition.await()` do `ReentrantLock` tạo qua `newCondition()` sẽ nhả mức giữ của lock liên kết khi chờ, rồi lấy lại theo hợp đồng Condition trước khi trở về. Phải giữ lock trước khi await.
- `Thread.sleep()` **không nhả monitor hay `ReentrantLock`** mà thread đang giữ.
- `notify()` hoặc `signal()` không chuyển quyền sở hữu lock ngay tức khắc; thread được đánh thức còn phải lấy lại lock.
- `wait()`/`await()` có thể thức dậy ngoài dự kiến (*spurious wakeup*); luôn kiểm tra điều kiện bằng **`while`**.

Ví dụ ý tưởng:

```java
// Snippet: mutex, ready và consume() được khai báo trong class.
synchronized (mutex) {
    while (!ready) {
        mutex.wait();
    }
    consume();
}
```

Đây là snippet, **không phải chương trình biên dịch độc lập**. Thread phát tín hiệu phải sửa `ready` dưới cùng mutex rồi gọi `mutex.notifyAll()` phù hợp. Vòng `while` bảo vệ điều kiện ngay cả khi thức dậy bất thường hoặc thread khác đã thay đổi state.

## 8. Callback tái nhập và invariant

Tái nhập có một rủi ro dễ bỏ qua: code đang giữ lock gọi một callback do caller cung cấp. Callback chạy **trên cùng thread** và có thể gọi ngược API dùng cùng lock; vì lock reentrant, callback **không bị chặn**. Nó có thể thay đổi state khi thao tác bên ngoài vẫn đang giả định state chưa đổi.

```java
// Snippet minh họa; mutex, state, callback và use() đã được khai báo.
synchronized (mutex) {
    int previous = state;
    callback.run();
    use(previous); // Có thể không còn phù hợp nếu callback đã đổi state.
}
```

Lock ngăn **thread khác** chen vào, nhưng không cấm chính owner tái nhập qua một đường gọi không dự kiến. Callback còn có thể chặn I/O, lấy khóa thứ hai, gọi lại đệ quy vô hạn hoặc ném exception.

Để an toàn: không chạy code không kiểm soát trong lock nếu không cần thiết; định nghĩa rõ hợp đồng callback có được reenter không; duy trì invariant ở mọi thời điểm callback quan sát; cân nhắc chụp snapshot rồi gọi callback ngoài lock nếu nghiệp vụ cho phép. Tuy nhiên nếu phải thực hiện check–then–act nguyên tử, **không** tùy tiện thả lock giữa check và update.

## 9. Các hiểu nhầm về phạm vi khóa

- Hai instance cùng class có **monitor instance khác nhau**. `accountA` và `accountB` không tự loại trừ nhau.
- `static synchronized` khóa `SomeClass.class`; phương thức instance synchronized khóa `this`. Hai khóa khác nhau dù code trong cùng class.
- Hai đối tượng `new ReentrantLock()` là hai khóa khác nhau; việc đặt cùng tên biến không liên quan.
- Dùng đối tượng công khai như String literal làm monitor có thể gây chia sẻ khóa không dự kiến; ưu tiên `private final Object mutex = new Object()` cho trạng thái riêng.
- Monitor trong một JVM không tự bảo vệ dữ liệu bị một tiến trình khác ghi. Khi bất biến trải qua file/database/service, phải dùng giao thức cập nhật tại chính nguồn dữ liệu đó.
- Reentrancy không thay thế chính sách bảo vệ mọi đường đọc/ghi. Dù helper tái nhập đúng, một getter đọc state mutable ngoài lock vẫn có thể là data race.

## 10. Những lỗi thường gặp

1. **“Một phương thức synchronized không gọi được một phương thức synchronized khác.”** Sai nếu cùng owner thread và cùng monitor.
2. **“Reentrant cho phép hai thread cùng giữ khóa.”** Sai; chỉ thread đang sở hữu được tái nhập.
3. **“Lock hai lần thì unlock một lần là đủ.”** Sai đối với `ReentrantLock`; hold count phải về 0 mới giải phóng.
4. **“Thread khác có thể unlock thay để sửa deadlock.”** Sai; `ReentrantLock` yêu cầu thread chủ sở hữu, ngược lại ném `IllegalMonitorStateException`.
5. **“Mọi deadlock biến mất khi dùng `ReentrantLock`.”** Sai với hai khóa khác nhau hoặc vòng phụ thuộc chờ.
6. **“Sleep sẽ thả monitor để thread khác chạy.”** Sai: `sleep` không tự giải phóng monitor.
7. **“Static và instance synchronized khóa cùng object.”** Sai: khóa class và khóa receiver khác nhau.
8. **“Fairness của `ReentrantLock(true)` cam kết thứ tự xử lý.”** Sai: không bảo đảm scheduler hay thời điểm hoàn tất.
9. **“Callback không thể sửa state khi callback được gọi dưới lock.”** Sai: callback cùng thread có thể tái nhập.
10. **“Reentrant đồng nghĩa thread-safe cho mọi dữ liệu.”** Sai: tính đúng còn phụ thuộc invariant, phạm vi khóa và công bố dữ liệu.

## 11. Checklist lựa chọn và sử dụng

1. Xác định **đúng đối tượng khóa**: monitor `this`, `Class` object, private mutex hay `ReentrantLock`.
2. Xác định **owner thread**: chỉ thread đã giữ **cùng khóa** mới tái nhập.
3. Phân tích các lời gọi lồng nhau: helper, đệ quy, superclass method có sử dụng cùng khóa không?
4. Với `ReentrantLock`, mỗi `lock()` thành công phải có `unlock()` tương ứng trong `finally`.
5. Bảo vệ **toàn bộ invariant**: lock lồng nhau không tự sửa được giao thức check–then–act bị chia nhỏ.
6. Tránh vòng phụ thuộc nhiều khóa; quy định thứ tự lấy lock ổn định; không chờ worker đang cần khóa mình giữ.
7. Xem xét timeout, interrupt và lỗi khi chờ khóa; chỉ unlock nếu đã acquire thành công.
8. Không cho callback ngoài kiểm soát tùy ý thay đổi state trung gian; xem xét nguy cơ tái nhập bất ngờ.
9. Kiểm thử nhiều thread, đường exception và lộ lock; không dựa vào thứ tự scheduler.
10. Chỉ chọn `ReentrantLock` khi cần khả năng bổ sung; `synchronized` đủ cho nhiều vùng critical section đơn giản.

**Ghi nhớ:** đồng bộ tái nhập giúp **cùng thread lấy lại cùng khóa** để gọi phương thức lồng nhau hoặc đệ quy mà không tự chặn, trong khi vẫn loại trừ thread khác. Java `synchronized` tự quản lý các tầng monitor; `ReentrantLock` theo dõi hold count và đòi unlock cân bằng. Đây là tính chất của khóa, còn thread safety phụ thuộc vào thiết kế invariant và giao thức truy cập trạng thái.