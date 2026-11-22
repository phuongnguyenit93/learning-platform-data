# Giải phóng monitor khi rời synchronized do ngoại lệ

## 1. Mục tiêu học tập

Trong Java, `synchronized` giúp nhiều luồng phối hợp truy cập trạng thái dùng chung bằng *monitor lock* của một đối tượng. Khi một lệnh trong khối hoặc phương thức `synchronized` ném ngoại lệ, chương trình có thể thoát khỏi phần mã đang giữ monitor theo cách đột ngột. Java bảo đảm **giải phóng monitor tương ứng khi thực sự rời khỏi phạm vi `synchronized`**, kể cả khi việc rời khỏi đó do ngoại lệ.

Sau bài này, bạn sẽ giải thích và kiểm chứng được:

- Monitor nào được lấy khi dùng khối `synchronized (lock)`, phương thức `synchronized` của đối tượng và phương thức `static synchronized`.
- Lý do monitor được nhả khi khối/phương thức hoàn thành đột ngột (*abrupt completion*) do `throw` hoặc do ngoại lệ từ lời gọi bên trong.
- Khác biệt giữa `catch` **bên trong** và **bên ngoài** phạm vi giữ monitor.
- Cách hoạt động của khóa *reentrant* khi cùng luồng đi vào `synchronized` trên cùng đối tượng nhiều lần.
- Vì sao “đã nhả khóa” không đồng nghĩa “trạng thái dữ liệu đã nhất quán”, cũng không bảo đảm luồng khác được chạy ngay.
- Cách đối chiếu hành vi với `Object.wait()`, `Thread.sleep()` và `ReentrantLock`.

Phạm vi bài là **luồng thực thi và giải phóng monitor khi ngoại lệ xuất hiện**. Ví dụ dùng Java 17 trở lên và chỉ tạo ngoại lệ thông thường có kiểm soát.

## 2. Monitor và vùng `synchronized`

Mỗi đối tượng Java có một monitor mà các luồng có thể dùng để đồng bộ hóa. Một luồng muốn đi vào `synchronized (lock)` phải lấy monitor gắn với đúng tham chiếu `lock`. Trong khi luồng đó còn sở hữu monitor, một luồng khác muốn lấy **cùng monitor** phải chờ; mã không đồng bộ hóa với monitor đó không tự động bị khóa.

```java
Object lock = new Object();

synchronized (lock) {
    // Luồng hiện tại đang giữ monitor của đối tượng lock.
    doWork();
}
// Sau khi thực sự rời khối, monitor của lock được nhả.
```

Đây là đoạn minh họa; `doWork()` phải được định nghĩa trong chương trình thực tế.

Các dạng khóa:

| Cấu trúc | Monitor được lấy | Khi nào monitor được nhả? |
| --- | --- | --- |
| `synchronized (lock) { ... }` | Đối tượng mà biểu thức `lock` đánh giá ra | Khi khối `synchronized` đó hoàn thành, bình thường hoặc đột ngột |
| `synchronized void update() { ... }` | `this`, tức đối tượng nhận lời gọi | Khi phương thức `update` hoàn thành |
| `static synchronized void update() { ... }` | Đối tượng `Class` biểu diễn lớp khai báo phương thức | Khi phương thức static hoàn thành |

**Chú ý:** hai đối tượng khóa khác nhau đại diện cho hai monitor khác nhau, dù các phương thức có cùng tên. Một phương thức instance `synchronized` không tự đồng bộ với phương thức `static synchronized` của cùng lớp: một bên dùng `this`, một bên dùng đối tượng `Class`.

### 2.1. Quy tắc cốt lõi khi xuất hiện ngoại lệ

Theo Java Language Specification §14.19, với khối `synchronized (expression) { body }`:

1. Java đánh giá biểu thức lấy đối tượng khóa.
2. Nếu việc đánh giá thất bại bằng ngoại lệ, khối không lấy monitor.
3. Nếu kết quả là `null`, Java ném `NullPointerException` và cũng chưa lấy monitor.
4. Nếu có đối tượng hợp lệ, luồng hiện tại lấy monitor rồi thực thi phần thân.
5. Nếu phần thân kết thúc bình thường, Java nhả monitor trước khi đi tiếp.
6. Nếu phần thân **kết thúc đột ngột vì bất kỳ lý do nào**, bao gồm ném ngoại lệ, Java nhả monitor rồi tiếp tục lan truyền lý do thoát đó.

Ví dụ về điểm phát sinh ngoại lệ:

```java
synchronized (lock) {
    operationA();
    operationB(); // Có thể ném ngoại lệ.
    operationC(); // Bị bỏ qua nếu operationB() ném ngoại lệ.
}
```

Đây là mã minh họa trong một phương thức, với `lock` và các phương thức `operationA/B/C` giả định đã được khai báo. Nếu `operationB()` ném ngoại lệ không bị bắt ở bên trong, phần thân `synchronized` sẽ thoát; Java nhả đúng monitor của `lock` trước khi ngoại lệ tiếp tục đi tới handler ở ngoài.

Quy tắc đó áp dụng cho checked exception, `RuntimeException` và các đối tượng `Error` khi việc hoàn thành đột ngột của khối còn được JVM xử lý. Tuy nhiên, không thể dùng quy tắc này để bảo đảm dọn dẹp hoàn tất trong mọi trường hợp tiến trình/JVM bị kết thúc bất thường.

## 3. Ví dụ hoàn chỉnh: ngoại lệ thoát ra ngoài khối thì monitor được nhả

Tạo file **`MonitorReleaseDemo.java`**:

```java
public class MonitorReleaseDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) throws InterruptedException {
        try {
            synchronized (LOCK) {
                System.out.println("inside: " + Thread.holdsLock(LOCK));
                throw new IllegalStateException("boom");
            }
        } catch (IllegalStateException failure) {
            System.out.println("caught: " + failure.getMessage());
            System.out.println("after catch: " + Thread.holdsLock(LOCK));
        }

        Thread worker = new Thread(() -> {
            synchronized (LOCK) {
                System.out.println("worker acquired: "
                        + Thread.holdsLock(LOCK));
            }
        });

        worker.start();
        worker.join();
        System.out.println("done");
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac MonitorReleaseDemo.java
java MonitorReleaseDemo
```

Kết quả `stdout`:

```text
inside: true
caught: boom
after catch: false
worker acquired: true
done
```

**Giải thích từng bước:**

1. Luồng `main` lấy monitor của `LOCK` và vào khối. `Thread.holdsLock(LOCK)` trả về `true` cho **luồng đang gọi phương thức**.
2. `throw new IllegalStateException("boom")` làm khối hoàn thành đột ngột. Java nhả monitor trước khi đi vào `catch` ở ngoài.
3. `catch` vẫn chạy trên luồng `main` nhưng lúc này luồng đó không còn giữ monitor, nên dòng `after catch: false` là chính xác.
4. Sau khi `catch` xong, chương trình khởi tạo luồng `worker`. Luồng này đi vào khối đồng bộ với cùng `LOCK` và in `true`.
5. `worker.join()` buộc `main` chờ đến khi worker kết thúc, vì vậy dòng `done` luôn in sau dòng `worker acquired: true`.

Ví dụ này cho thấy monitor được nhả khi thoát phạm vi `synchronized`. `Thread.holdsLock(object)` chỉ cho biết **luồng hiện tại** có đang giữ monitor của đối tượng đó hay không; giá trị `false` **không** có nghĩa chắc chắn không có luồng nào khác đang giữ khóa.

## 4. `catch` đặt ở đâu quyết định thời điểm nhả monitor

Hai tình huống dưới đây trông tương tự nhưng khác nhau về thứ tự thực thi.

### 4.1. `catch` nằm ngoài `synchronized`

```java
try {
    synchronized (lock) {
        riskyOperation();
    }
} catch (RuntimeException failure) {
    // Nếu không còn vùng synchronized bao ngoài giữ cùng lock,
    // luồng đã nhả monitor của khối vừa thoát.
    recover(failure);
}
```

Đây là đoạn minh họa. Khi `riskyOperation()` ném `RuntimeException`, khối `synchronized` bị thoát và nhả monitor; sau đó handler bên ngoài mới xử lý. Ngoại lệ vẫn được bắt, nhưng **việc bắt ngoại lệ không phải nguyên nhân nhả khóa**. Khóa được nhả vì luồng rời khỏi phạm vi đồng bộ hóa.

### 4.2. `catch` nằm bên trong `synchronized`

```java
synchronized (lock) {
    try {
        riskyOperation();
    } catch (RuntimeException failure) {
        // Luồng VẪN giữ lock vì chưa rời khối synchronized.
        recover(failure);
    }
    // Luồng vẫn giữ lock tại đây.
}
// Monitor được nhả khi luồng ra khỏi khối ngoài cùng này.
```

Đây cũng là đoạn minh họa. Vì lỗi đã được xử lý ngay trong phần thân, khối `synchronized` vẫn đang thực thi. Monitor không được tự động nhả tại thời điểm `catch` bắt được lỗi.

**Hệ quả thực tế:** nếu `recover(failure)` là tác vụ chậm (I/O, gọi mạng hoặc retry nhiều lần), các luồng khác cần cùng monitor có thể bị chặn lâu. Khi có thể, thu thập trạng thái cần thiết trong vùng khóa và chuyển việc xử lý tốn thời gian ra ngoài.

## 5. Ví dụ chạy được: khóa reentrant và `catch` bên trong vùng khóa

Monitor Java có tính **reentrant**: một luồng đã giữ một monitor có thể lấy lại chính monitor đó trong vùng gọi lồng nhau. Mỗi lần vào tương ứng với một lần thoát; chỉ khi không còn lần sở hữu nào của luồng đó thì monitor mới thật sự được giải phóng.

Tạo file **`NestedMonitorDemo.java`**:

```java
public class NestedMonitorDemo {
    private static final Object LOCK = new Object();

    public static void main(String[] args) {
        synchronized (LOCK) {
            try {
                synchronized (LOCK) {
                    System.out.println("inner entered: "
                            + Thread.holdsLock(LOCK));
                    throw new IllegalStateException("inner failed");
                }
            } catch (IllegalStateException failure) {
                System.out.println("catch in outer: "
                        + Thread.holdsLock(LOCK));
            }

            System.out.println("before outer exit: "
                    + Thread.holdsLock(LOCK));
        }

        System.out.println("after outer exit: "
                + Thread.holdsLock(LOCK));
    }
}
```

```bash
javac NestedMonitorDemo.java
java NestedMonitorDemo
```

Kết quả:

```text
inner entered: true
catch in outer: true
before outer exit: true
after outer exit: false
```

Quá trình xảy ra như sau:

- Khối **ngoài** lấy monitor của `LOCK` lần thứ nhất.
- Khối **trong** lấy lại cùng monitor lần thứ hai trên cùng luồng.
- Ngoại lệ khiến khối trong thoát và hoàn trả lần lấy khóa của **khối trong**.
- `catch` thuộc khối ngoài nhận ngoại lệ; lần lấy khóa của **khối ngoài** vẫn còn, nên `Thread.holdsLock(LOCK)` vẫn là `true`.
- Khi chương trình rời khối ngoài, lần lấy khóa còn lại được giải phóng; sau đó `Thread.holdsLock(LOCK)` là `false`.

Quy tắc đúng là **mỗi phạm vi `synchronized` đã thoát nhả phần sở hữu monitor tương ứng**. Không thể suy ra “ném một ngoại lệ sẽ thả tất cả monitor mà luồng đang giữ”. Nếu một luồng nắm nhiều khóa, những phạm vi vẫn còn đang thực thi vẫn giữ khóa của chúng.

## 6. Phương thức `synchronized` cũng tự nhả monitor nếu ném ngoại lệ

Đối với phương thức instance có từ khóa `synchronized`, monitor thuộc về `this`. Việc vào và ra monitor gắn với lời gọi phương thức, kể cả khi phương thức ném ngoại lệ.

Tạo file **`SynchronizedMethodDemo.java`**:

```java
public class SynchronizedMethodDemo {
    private synchronized void fail() {
        System.out.println("inside method: " + Thread.holdsLock(this));
        throw new IllegalArgumentException("invalid input");
    }

    public static void main(String[] args) {
        SynchronizedMethodDemo demo = new SynchronizedMethodDemo();

        try {
            demo.fail();
        } catch (IllegalArgumentException failure) {
            System.out.println("caught: " + failure.getMessage());
            System.out.println("after method: " + Thread.holdsLock(demo));
        }
    }
}
```

```bash
javac SynchronizedMethodDemo.java
java SynchronizedMethodDemo
```

Kết quả:

```text
inside method: true
caught: invalid input
after method: false
```

Khi `fail()` ném lỗi, lời gọi phương thức kết thúc đột ngột và monitor của đối tượng `demo` được nhả trước khi handler bên ngoài nhận lỗi.

Với `static synchronized`, monitor được lấy từ đối tượng `SynchronizedMethodDemo.class` (nếu phương thức được khai báo ở lớp này), **không phải** một instance của lớp.

### 6.1. Khác biệt trong JVM bytecode

Ở mức JVM, khối `synchronized (lock)` thường được biên dịch bằng chỉ thị `monitorenter` và `monitorexit`, bao gồm đường thoát ngoại lệ để nhả monitor.

Một phương thức `synchronized` thông thường lại được đánh dấu bằng cờ `ACC_SYNCHRONIZED` trong thông tin phương thức; JVM điều phối lấy và nhả monitor khi gọi và hoàn thành phương thức. Do đó, **không nên khẳng định mọi phương thức `synchronized` đều có cặp lệnh `monitorenter`/`monitorexit` trong phần thân bytecode**.

Có thể tự kiểm tra cấu trúc bằng:

```bash
javac SynchronizedMethodDemo.java
javap -c -v SynchronizedMethodDemo
```

Tìm phần khai báo `fail()` và cờ `ACC_SYNCHRONIZED`. Đầu ra chi tiết của `javap -v` phụ thuộc trình biên dịch và thông tin classfile; vì vậy bài không giả định một bản dump bytecode cố định.

## 7. Liên hệ với `finally`

Tư duy hữu ích là vùng `synchronized` có cơ chế **tự dọn khóa trên cả đường thành công và đường lỗi**. Điều này gần với ý tưởng sử dụng `finally`, nhưng giải phóng monitor của ngôn ngữ/JVM không phụ thuộc lập trình viên có viết khối `finally` hay không.

```java
synchronized (lock) {
    try {
        operation();
    } finally {
        // Dọn tài nguyên ứng dụng trong vùng khóa, nếu phù hợp.
        // Tại thời điểm này luồng VẪN giữ monitor lock.
        cleanup();
    }
}
// Khi thoát synchronized, monitor được nhả.
```

Đây là mảnh mã minh họa; `operation()`, `cleanup()` và `lock` cần được định nghĩa. Nếu `operation()` ném ngoại lệ, `finally` nội bộ chạy khi vẫn đang giữ monitor. Khi khối đồng bộ kết thúc, monitor được nhả.

**Lưu ý về ngoại lệ mới từ `finally`:** nếu `cleanup()` cũng ném lỗi, ngoại lệ đó có thể thay thế ngoại lệ đang lan truyền. Monitor vẫn được nhả khi rời khối `synchronized`, nhưng thông tin nguyên nhân ban đầu có thể bị che mất. Hãy thiết kế thao tác dọn dẹp sao cho không làm mất lỗi chính.

Việc nhả monitor không phụ thuộc `catch` có bắt ngoại lệ hay không:

| Đường thoát | Monitor của phạm vi đã thoát |
| --- | --- |
| Chạy hết khối | Được nhả |
| `return` từ bên trong khối | Được nhả trước khi hoàn thành việc trả về |
| `break` / `continue` làm thoát phạm vi đó | Được nhả |
| `throw` hoặc lời gọi ném ngoại lệ vượt ra khỏi khối | Được nhả |
| Ngoại lệ bị `catch` ngay trong khối, vẫn tiếp tục ở trong đó | Vẫn được giữ cho đến khi rời khối |
| Ngoại lệ xảy ra khi đánh giá biểu thức khóa hoặc biểu thức khóa bằng `null` | Chưa lấy monitor nên không có monitor mới để nhả |

Không đánh đồng bảo đảm thực thi ngữ nghĩa Java với trường hợp tiến trình bị kết thúc cưỡng bức, VM bị crash hoặc mất điện.

## 8. `Object.wait()`, `Thread.sleep()` và các kiểu khóa khác

Có những trường hợp luồng **tạm thời nhả monitor khi vẫn còn trong khối `synchronized`**, khác với tình huống thoát vì ngoại lệ. Quan trọng nhất là `Object.wait()`.

### 8.1. `wait()` tạm nhả monitor của đối tượng chờ

`Object.wait()` yêu cầu luồng hiện tại đang sở hữu monitor của **đúng đối tượng gọi `wait()`**. Khi luồng gọi `lock.wait()` hợp lệ, nó đi vào trạng thái chờ và tạm thời nhả **mọi lần sở hữu monitor của `lock`**. Sau khi được đánh thức, bị ngắt hoặc kết thúc chờ theo điều kiện phù hợp, luồng phải lấy lại monitor của `lock` trước khi `wait()` trả về bình thường hoặc ném `InterruptedException`.

```java
synchronized (lock) {
    while (!conditionReady()) {
        lock.wait(); // Tạm nhả monitor của lock khi đang chờ.
    }
    consume();
}
```

Đây là **mảnh mã minh họa**, cần nằm trong phương thức xử lý/khai báo `InterruptedException` và định nghĩa `conditionReady()`, `consume()`. Dùng `while` để kiểm tra lại điều kiện vì có thể có đánh thức không báo trước (*spurious wakeup*) hoặc điều kiện đã thay đổi.

Khi `wait()` bị ngắt và ném `InterruptedException`, luồng đã lấy lại monitor trước khi ném. Nếu ngoại lệ đó **thoát tiếp ra ngoài khối `synchronized`**, cơ chế thoát khối sẽ nhả monitor sau đó. Nếu được `catch` **ngay trong khối**, luồng vẫn giữ monitor sau khi `wait()` ném.

`notify()` hoặc `notifyAll()` đánh thức luồng đang chờ nhưng **không nhả monitor ngay tại lệnh gọi**. Luồng chờ chỉ có thể tiếp tục sau khi lấy được monitor trở lại.

### 8.2. `sleep()` không nhả monitor

Nếu một luồng gọi `Thread.sleep(...)` trong vùng `synchronized`, nó **tiếp tục giữ** các monitor đang sở hữu trong lúc ngủ. Vì thế, ngủ hoặc chờ I/O dài bên trong vùng khóa có thể làm các luồng khác chậm đáng kể.

### 8.3. `ReentrantLock` không có quy tắc tự nhả như `synchronized`

`java.util.concurrent.locks.ReentrantLock` là API khóa tường minh. Nếu lấy khóa bằng `lock()` thì bạn phải gọi `unlock()` một cách cân bằng, thông thường trong `finally`. Nếu không, một ngoại lệ ở giữa có thể khiến khóa **bị giữ lại**.

```java
java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

lock.lock();
try {
    performOperation();
} finally {
    lock.unlock();
}
```

Đây là mảnh minh họa, cần định nghĩa `performOperation()`. Chỉ đặt `unlock()` trong `finally` sau khi đã lấy khóa thành công. Phân biệt khóa tường minh này với monitor nội tại do `synchronized` quản lý.

## 9. Đã nhả monitor chưa có nghĩa dữ liệu đã an toàn

`synchronized` cung cấp loại trừ lẫn nhau giữa những luồng đồng bộ trên **cùng monitor** và tạo quan hệ về thứ tự nhìn thấy bộ nhớ (*happens-before*) khi một luồng unlock monitor, sau đó luồng khác lock cùng monitor. Vì vậy, các ghi trước khi nhả khóa có thể được luồng lấy khóa sau nhìn thấy theo quy tắc Java Memory Model.

Nhưng Java **không hoàn tác các thay đổi trên đối tượng** khi khối `synchronized` kết thúc đột ngột. Nếu một luồng đã cập nhật một nửa trạng thái rồi ném lỗi, luồng kế tiếp có thể đọc trạng thái sai, dù monitor đã được giải phóng đúng cách.

Ví dụ thiết kế chưa an toàn:

```java
synchronized (lock) {
    available -= amount;      // Thay đổi một phần trạng thái.
    saveToExternalSystem();   // Có thể ném ngoại lệ.
    reserved += amount;       // Không chạy nếu lời gọi trên thất bại.
}
```

Đây là **đoạn minh họa**, giả định `lock`, `available`, `reserved`, `amount` và `saveToExternalSystem()` đã được định nghĩa. Nếu ứng dụng yêu cầu `available + reserved` không đổi, lỗi giữa hai phép cập nhật có thể phá vỡ bất biến. Khóa được nhả nhưng trạng thái không tự rollback.

Một hướng sửa cho trường hợp cập nhật **chỉ trong bộ nhớ** là kiểm tra và tính giá trị mới trước các thay đổi trạng thái, đưa hoạt động có khả năng thất bại lên trước phần commit, rồi áp dụng các phép gán dưới cùng monitor:

```java
synchronized (lock) {
    validate(amount);
    int newAvailable = available - amount;
    int newReserved = reserved + amount;
    operationThatMayFail();

    available = newAvailable;
    reserved = newReserved;
}
```

Đây cũng là **mảnh mã minh họa**; các phương thức và biến liên quan cần được định nghĩa. Mẫu này giả định phần commit chỉ gồm các phép gán nội bộ không chủ động ném lỗi, và mọi truy cập trạng thái liên quan đều tuân theo cùng cơ chế khóa. Đối với nhiều tài nguyên, giao dịch cơ sở dữ liệu, mạng hoặc những hiệu ứng bên ngoài khác, cần cơ chế transaction/compensation phù hợp; `synchronized` không biến một chuỗi thao tác thành giao dịch có rollback.

### Ví dụ chạy được: đảm bảo bất biến trước khi nhận lỗi

Tạo file **`InvariantSafetyDemo.java`**:

```java
public class InvariantSafetyDemo {
    private static class Counters {
        private int available = 10;
        private int reserved = 0;

        synchronized void reserve(int amount, boolean fail) {
            if (amount <= 0 || amount > available) {
                throw new IllegalArgumentException("invalid amount");
            }

            int nextAvailable = available - amount;
            int nextReserved = reserved + amount;

            if (fail) {
                throw new IllegalStateException("simulated failure");
            }

            available = nextAvailable;
            reserved = nextReserved;
        }

        synchronized String snapshot() {
            return available + "," + reserved;
        }
    }

    public static void main(String[] args) {
        Counters counters = new Counters();

        try {
            counters.reserve(4, true);
        } catch (IllegalStateException failure) {
            System.out.println("operation failed");
        }

        System.out.println(counters.snapshot());
        counters.reserve(4, false);
        System.out.println(counters.snapshot());
    }
}
```

```bash
javac InvariantSafetyDemo.java
java InvariantSafetyDemo
```

Kết quả:

```text
operation failed
10,0
6,4
```

Lần đầu, ngoại lệ được ném **trước khi cập nhật** hai trường, và phương thức `synchronized` tự nhả monitor. Giá trị đọc sau đó vẫn là `10,0`. Lần thứ hai không lỗi nên hai trường được cập nhật thành `6,4`. Mẫu này minh họa cách bảo toàn bất biến trong bộ nhớ đối với đường lỗi đã dự kiến; nó không phải bảo đảm phục hồi sau mọi `Error` hoặc sự cố bên ngoài.

## 10. Những hệ quả dễ bỏ sót

### 10.1. Giải phóng khóa không ép luồng khác chạy ngay

Khi một luồng nhả monitor, các luồng đang chờ có thể cạnh tranh lấy monitor đó, nhưng **không có bảo đảm thứ tự FIFO** hoặc bảo đảm một luồng cụ thể được chạy ngay. Lịch trình thực tế phụ thuộc hệ thống và các luồng đang hoạt động.

### 10.2. Việc nhả một monitor không mở mọi đường truy cập

Một luồng khác chỉ phải chờ monitor nếu nó đi vào vùng đồng bộ hóa **trên cùng đối tượng khóa**. Nếu một số phương thức đọc/ghi chung dữ liệu mà không dùng đúng khóa hoặc cơ chế đồng bộ hợp lệ khác, chúng vẫn có thể truy cập dữ liệu không nhất quán.

### 10.3. Deadlock có thể vẫn xảy ra

Nếu hai luồng lần lượt giữ monitor A và B, rồi chờ monitor còn lại, chúng có thể deadlock. Tự nhả monitor khi **rời** `synchronized` không giúp một luồng đang bị kẹt vĩnh viễn bên trong vùng khóa thoát ra. Giảm nested locking, cố định thứ tự lấy khóa và dùng công cụ thread dump khi chẩn đoán.

### 10.4. Không được dùng lỗi JVM nghiêm trọng làm kiểm thử đồng bộ thông thường

Quy tắc thoát monitor áp dụng khi việc hoàn thành đột ngột được Java/JVM xử lý. Tuy nhiên, việc cố tạo `OutOfMemoryError` hoặc `StackOverflowError` có thể khiến hệ thống không còn tài nguyên để in log, tạo đối tượng, điều phối công việc hay khởi động phục hồi. Hãy dùng `IllegalStateException` trong ví dụ thử nghiệm bình thường.

## 11. Tóm tắt sai lầm phổ biến

| Nhận định | Đánh giá chính xác |
| --- | --- |
| “Cứ ném ngoại lệ là giải phóng tất cả khóa của luồng.” | **Sai.** Mỗi phạm vi đã thoát nhả phần sở hữu của chính nó; phạm vi bao ngoài còn hiệu lực tiếp tục giữ monitor. |
| “`catch` bên trong `synchronized` làm khóa được nhả.” | **Sai.** Khóa vẫn giữ cho đến khi thực sự rời khối/phương thức đồng bộ. |
| “Phải viết `finally { unlock(); }` cho `synchronized`.” | **Sai.** Monitor nội tại được JVM quản lý. `unlock()` trong `finally` là cách dùng `Lock` tường minh. |
| “Khi exception đã được bắt ở ngoài, monitor của khối vừa thoát vẫn giữ đến hết handler.” | **Sai** nếu không còn vùng đồng bộ hóa bao ngoài giữ cùng khóa. Khối đã nhả monitor trước khi handler ngoài chạy. |
| “`wait()` ném `InterruptedException` khi chưa lấy lại monitor.” | **Sai.** Với `Object.wait()`, luồng lấy lại monitor trước khi phương thức trả về hoặc ném `InterruptedException`. |
| “`Thread.sleep()` giải phóng monitor giống `wait()`.” | **Sai.** `sleep()` giữ nguyên các monitor đang sở hữu. |
| “Monitor nhả nghĩa là thao tác dở dang được rollback.” | **Sai.** Những thay đổi đã thực hiện không tự hoàn tác. |
| “Nhả monitor sẽ đánh thức đúng luồng đang đợi theo FIFO.” | **Sai.** Không có bảo đảm FIFO của monitor nội tại. |

## 12. Tự kiểm tra

1. Một lời gọi trong `synchronized(lock)` ném `IOException` và không được bắt trong khối. Monitor có được nhả không? **Có**, khi quá trình hoàn thành đột ngột rời khối đó.
2. Nếu `catch (IOException e)` đặt *bên trong* cùng khối `synchronized` thì sao? **Vẫn giữ monitor** trong handler và những câu lệnh tiếp theo bên trong khối.
3. Khi cùng luồng đang giữ monitor hai lần do nested `synchronized(lock)`, thoát khối trong bằng ngoại lệ đã làm monitor hoàn toàn rảnh chưa? **Chưa**, khối ngoài vẫn giữ một lần sở hữu.
4. Nếu `synchronized(null)` ném `NullPointerException` thì phải nhả khóa nào? **Không có monitor nào vừa được lấy**, vì biểu thức khóa là `null`.
5. Nếu một phương thức instance `synchronized` ném `RuntimeException` ra bên ngoài, monitor của đối tượng nhận lời gọi được xử lý ra sao? **Được nhả** trong quá trình phương thức kết thúc đột ngột.
6. Nếu `wait()` bị interrupt, tại thời điểm nhận `InterruptedException` ở handler nằm trong khối đồng bộ, luồng có giữ lại monitor không? **Có**; nó đã lấy lại monitor trước khi `wait()` ném lỗi.
7. Vì sao phải kiểm tra bất biến sau một lỗi trong vùng đồng bộ hóa? Vì **giải phóng khóa không thực hiện rollback các phép gán đã diễn ra**.

## 13. Tài liệu chuẩn

- [Java Language Specification 17 — §14.19, The synchronized Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.19): ngữ nghĩa lấy và nhả monitor khi khối kết thúc bình thường hoặc đột ngột.
- [Java Language Specification 17 — §17.1, Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1): reentrant monitor, synchronized methods và unlock tự động khi thoát.
- [Java Language Specification 17 — §17.4.5, Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5): quan hệ unlock/lock và visibility giữa các luồng.
- [Java Virtual Machine Specification 17 — §2.11.10, Synchronization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.10): monitorenter, monitorexit và cờ ACC_SYNCHRONIZED.
- [Java SE 17 API — Thread.holdsLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#holdsLock(java.lang.Object)): kiểm tra quyền sở hữu monitor của luồng hiện tại.
- [Java SE 17 API — Object.wait](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#wait()): nhả tạm monitor và lấy lại trước khi trở về.
- [Java SE 17 API — ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): sự khác biệt của khóa tường minh.

**Nguyên tắc trọng tâm:** Khi luồng thực sự rời khỏi phạm vi `synchronized` vì một ngoại lệ, Java nhả monitor của phạm vi đã thoát. Hãy xét vị trí `catch`, những vùng khóa bao ngoài và tính nhất quán của dữ liệu để suy luận đầy đủ về hành vi đa luồng.
