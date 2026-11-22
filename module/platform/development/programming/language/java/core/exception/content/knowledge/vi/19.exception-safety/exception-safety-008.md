# Phân biệt giải phóng khóa `synchronized` với bảo đảm bất biến dữ liệu trong Java

> **Phạm vi:** Java Core → Exception → Bảo toàn trạng thái. Bài học giải thích vì sao một ngoại lệ có thể khiến khối `synchronized` kết thúc và monitor được giải phóng đúng cách, trong khi dữ liệu mà đoạn mã đã sửa vẫn ở trạng thái không hợp lệ. Mục tiêu là phân biệt trách nhiệm của cơ chế khóa với trách nhiệm thiết kế thao tác cập nhật an toàn khi thất bại.

## 1. Hai khái niệm khác nhau

Trong Java, `synchronized` giúp các luồng phối hợp quyền truy cập vào một **monitor** gắn với một đối tượng. Khi luồng vào một khối/phương thức `synchronized`, nó phải giữ monitor tương ứng; khi luồng thoát khỏi vùng đó theo cách thông thường hoặc do ngoại lệ, JVM giải phóng monitor do lần vào vùng đồng bộ đó nắm giữ.

**Bất biến dữ liệu (data invariant)** là điều kiện phải đúng đối với trạng thái mà hệ thống cho phép quan sát. Ví dụ:

- Số dư tài khoản không âm.
- Khi chuyển tiền trong nội bộ hai tài khoản, tổng tiền không đổi nếu không có phí hoặc dòng tiền bên ngoài.
- `size` phải khớp với số phần tử lưu thực tế.
- Một đơn hàng `PAID` phải có thông tin thanh toán tương ứng.
- Các trường `start`, `end` phải thỏa `start <= end` theo hợp đồng của đối tượng.

Monitor đảm bảo **quyền truy cập/đồng bộ hóa**; nó không biết số dư, hóa đơn, tồn kho hoặc invariant miền nghiệp vụ. Khi một phương thức ném ngoại lệ sau khi đã sửa một trường, JVM không ghi nhớ giá trị cũ của trường để tự khôi phục.

> **Mấu chốt:** “Khóa được nhả” là một quy tắc của `synchronized`. “Trạng thái còn hợp lệ sau lỗi” là một cam kết mà **mã ứng dụng phải tự thiết kế và kiểm chứng**.

## 2. Điều gì xảy ra khi `synchronized` gặp ngoại lệ?

Một khối đồng bộ có dạng:

~~~java
// Mã minh họa bên trong một phương thức đã có biến lock.
synchronized (lock) {
    changeState();
}
~~~

Các tình huống có liên quan:

1. Luồng gọi phải lấy monitor của `lock` trước khi chạy phần thân.
2. Nếu `changeState()` hoàn tất, luồng ra khỏi khối và nhả monitor của lần vào đó.
3. Nếu `changeState()` ném ngoại lệ chưa bị xử lý trong khối, ngoại lệ lan ra, khối kết thúc bất thường và monitor vẫn được nhả.
4. Nếu có `catch` **bên trong** khối, việc bắt lỗi không đồng nghĩa đã thoát khối; monitor tiếp tục được giữ cho đến lúc thực sự ra khỏi vùng `synchronized`.
5. Nếu ngoại lệ được bắt ở **bên ngoài** khối, luồng đã rời vùng đồng bộ trước khi chạy handler ngoài.

Tương tự, một phương thức instance `synchronized` dùng monitor của `this`; phương thức `static synchronized` dùng monitor của đối tượng `Class` tương ứng. Chúng có thể là **những monitor khác nhau**, vì vậy chỉ khai báo `synchronized` cho mọi phương thức chưa đủ nếu mỗi phương thức bảo vệ trạng thái bằng một khóa khác.

### Khi nào khóa chưa được nhả?

- Khối còn đang chạy, kể cả đang thực hiện lệnh trong `catch` hoặc `finally` nằm **bên trong** khối.
- Một luồng đang giữ nhiều monitor: rời một khối chỉ nhả monitor tương ứng; các monitor của vùng đồng bộ bao ngoài vẫn có thể được giữ.
- Java cho phép **reentrant synchronization**: cùng luồng có thể vào lại monitor đang giữ; mỗi lần vào cần một lần thoát tương ứng trước khi monitor hoàn toàn được giải phóng cho luồng khác.
- `Object.wait()` có hành vi đặc biệt: khi được gọi đúng trên monitor đang giữ, nó tạm nhả monitor của **đối tượng được wait** trong lúc chờ và phải lấy lại monitor ấy trước khi quay về; nó không tự nhả mọi monitor khác mà luồng giữ.
- `Thread.sleep()` không tự nhả monitor đang giữ. `notify()`/`notifyAll()` cũng không làm luồng gọi nhả monitor ngay lập tức.

Quy tắc tự động nhả khóa của `synchronized` nói về **việc đi vào/ra monitor**, không hứa tiến độ trong các trường hợp deadlock, vòng lặp không kết thúc hoặc JVM bị dừng. Không nên diễn đạt rằng mọi lời gọi `synchronized` đều chắc chắn sẽ “cuối cùng nhả khóa” bất kể chương trình có thoát vùng đồng bộ hay không.

## 3. Vì sao monitor được nhả vẫn để lại dữ liệu lỗi?

Xét thao tác chuyển 30 đơn vị từ tài khoản A sang B, ban đầu:

~~~text
A = 100
B = 50
Tổng = 150
~~~

Một phương thức có thể làm như sau:

~~~java
// Mã minh họa nằm trong lớp có trường a và b.
public synchronized void transfer(long amount) {
    a -= amount;                 // A thành 70
    callRiskyOperation();       // Ném exception
    b += amount;                 // Không được thực hiện
}
~~~

Khi `callRiskyOperation()` ném ngoại lệ, luồng rời phương thức; monitor của `this` được nhả. Nhưng lúc đó A bằng 70 và B vẫn bằng 50, tổng còn 120. Bất biến “tổng tiền không đổi” bị phá hủy mặc dù không còn luồng nào giữ khóa.

Một luồng khác đến sau, lấy **cùng monitor** và đọc trạng thái có thể thấy chính xác cặp giá trị sai này. Khóa giúp nó thấy cập nhật đã công bố đúng quy tắc bộ nhớ; khóa không biến giá trị đó thành hợp lệ.

Có hai cấp độ cần phân biệt:

| Câu hỏi | `synchronized` làm được gì? | Điều vẫn phải thiết kế |
|---|---|---|
| Hai luồng có đồng thời chạy mã được bảo vệ bởi **cùng monitor** không? | Ngăn chặn thực thi đồng thời trong các vùng bảo vệ bằng monitor đó | Mọi lối truy cập liên quan phải dùng cùng quy tắc khóa |
| Sau khi luồng trước thoát, luồng sau có thấy các ghi xảy ra trước lúc nhả monitor không? | Quy tắc *happens-before* của unlock → lock tiếp theo trên cùng monitor hỗ trợ tính nhìn thấy/thứ tự | Dữ liệu được nhìn thấy phải đúng theo invariant |
| Ngoại lệ thoát khỏi vùng đồng bộ có làm monitor bị kẹt mãi không? | JVM nhả monitor của vùng đồng bộ đã thoát | Không gọi nhầm `Lock.lock()` thủ công rồi quên `unlock()` |
| Những phép gán đã xảy ra có tự rollback không? | **Không** | Chuẩn bị trước, commit an toàn, rollback có kiểm soát hoặc transaction |
| Nhiều trường có tự cập nhật kiểu all-or-nothing không? | **Không mặc định** | Thiết kế điểm commit, bảo vệ mọi reader, hoặc dùng một snapshot bất biến |
| Ngoài tiến trình/JVM có thể đã chịu tác dụng phụ chưa? | Monitor Java không kiểm soát I/O hay dịch vụ bên ngoài | Transaction, idempotency, outbox hoặc cơ chế phối hợp |

## 4. Chương trình Java 17 chạy được: khóa được nhả nhưng invariant có thể hỏng

Ví dụ sau tạo hai sổ số dư độc lập. Phiên bản `unsafeTransfer` trừ tài khoản A rồi cố tình ném ngoại lệ trước khi cộng B. Phiên bản `safeTransfer` chuẩn bị giá trị mới và kiểm tra lỗi **trước khi** thay hai trường. Luồng quan sát khác được khởi động sau khi lời gọi thất bại và gọi `snapshot()` (cũng là `synchronized`), chứng minh nó vẫn lấy được monitor đã giải phóng.

Lưu thành tệp **`SynchronizedInvariantDemo.java`**:

~~~java
public class SynchronizedInvariantDemo {
    record Snapshot(long a, long b) {
        @Override
        public String toString() {
            return "A=" + a + ", B=" + b + ", total=" + (a + b);
        }
    }

    static final class Ledger {
        private long a;
        private long b;

        Ledger(long a, long b) {
            if (a < 0 || b < 0) {
                throw new IllegalArgumentException("negative initial balance");
            }
            this.a = a;
            this.b = b;
        }

        public synchronized void unsafeTransfer(long amount, boolean simulateFailure) {
            if (amount <= 0 || amount > a) {
                throw new IllegalArgumentException("invalid transfer amount");
            }

            a -= amount; // Trạng thái thật đã thay đổi.
            if (simulateFailure) {
                throw new IllegalStateException("simulated failure");
            }
            b = Math.addExact(b, amount); // Có thể lỗi sau khi A đã giảm.
        }

        public synchronized void safeTransfer(long amount, boolean simulateFailure) {
            if (amount <= 0 || amount > a) {
                throw new IllegalArgumentException("invalid transfer amount");
            }

            long nextA = Math.subtractExact(a, amount);
            long nextB = Math.addExact(b, amount);

            // Mọi nhánh ném lỗi dự kiến đều chạy trước khi commit.
            if (simulateFailure) {
                throw new IllegalStateException("simulated failure");
            }

            a = nextA;
            b = nextB;
        }

        public synchronized Snapshot snapshot() {
            return new Snapshot(a, b);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger unsafe = new Ledger(100, 50);
        try {
            unsafe.unsafeTransfer(30, true);
        } catch (IllegalStateException ex) {
            System.out.println("Unsafe rejected: " + ex.getMessage());
        }

        Thread firstObserver = new Thread(
                () -> System.out.println("Unsafe observer: " + unsafe.snapshot()));
        firstObserver.start();
        firstObserver.join();

        Ledger safe = new Ledger(100, 50);
        try {
            safe.safeTransfer(30, true);
        } catch (IllegalStateException ex) {
            System.out.println("Safe rejected: " + ex.getMessage());
        }

        Thread secondObserver = new Thread(
                () -> System.out.println("Safe observer: " + safe.snapshot()));
        secondObserver.start();
        secondObserver.join();

        safe.safeTransfer(30, false);
        System.out.println("After safe success: " + safe.snapshot());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac SynchronizedInvariantDemo.java
java SynchronizedInvariantDemo
~~~

Kết quả stdout:

~~~text
Unsafe rejected: simulated failure
Unsafe observer: A=70, B=50, total=120
Safe rejected: simulated failure
Safe observer: A=100, B=50, total=150
After safe success: A=70, B=80, total=150
~~~

**Giải thích kết quả:**

- `unsafeTransfer` đi ra do `IllegalStateException`; nếu monitor không được nhả, luồng `firstObserver` sẽ không thể vào `snapshot()` rồi hoàn tất `join()`. Nhưng monitor đã được nhả và observer đọc được A=70/B=50, tức **một trạng thái có thể nhìn thấy nhưng vi phạm bất biến**.
- `safeTransfer` ném cùng loại ngoại lệ trước bất cứ phép gán nào vào `a`/`b`. Luồng khác vào `snapshot()` vẫn đọc 100/50.
- Lần `safeTransfer(30, false)` hoàn thành, số dư trở thành 70/80 với tổng 150.
- `Math.addExact` phát hiện tràn số `long` thay vì cho phép số học vòng âm thầm; vì phép tính xảy ra trước commit trong bản safe, lỗi tràn cũng không làm A bị trừ dở.
- Việc observer dùng một luồng khác và `join()` giúp đầu ra có thứ tự xác định. Đây là chương trình minh họa **sự khác biệt về ngữ nghĩa**, không phải công cụ chứng minh mọi lịch trình luồng trong chương trình thực tế.

**Giới hạn của mẫu `safeTransfer`:** hai phép gán `a = nextA` và `b = nextB` vẫn là hai câu lệnh. Trong mẫu đã cho, không có lời gọi mã người dùng hoặc phép tính có khả năng ném exception nằm giữa hai phép gán, và mọi lối đọc công khai qua `snapshot()` dùng cùng monitor. Để có bảo đảm trạng thái nhất quán mạnh hơn trong thiết kế phức tạp, nên biểu diễn cặp số dư bằng một snapshot bất biến và commit bằng một lần thay tham chiếu (xem phần 7).

## 5. Java Memory Model: thấy dữ liệu mới không đồng nghĩa dữ liệu đúng

Theo quy tắc *happens-before* của Java Memory Model, một thao tác **unlock** trên monitor xảy ra trước một thao tác **lock tiếp theo** trên cùng monitor. Các thao tác ghi trước unlock được công bố thích hợp tới luồng vào sau nếu chương trình tuân theo quy tắc đồng bộ.

Điều này giải quyết bài toán **visibility** và hỗ trợ suy luận về thứ tự thực thi. Nhưng JVM không kiểm tra bất biến nghiệp vụ:

~~~text
Thread 1                            Thread 2
--------                            --------
lock(this)
a = 70
throw exception
unlock(this)
                                    lock(this)
                                    read a = 70
                                    read b = 50
                                    unlock(this)
~~~

Luồng 2 có thể nhận được **một ảnh chụp nhất quán về mặt bộ nhớ** của trạng thái mà luồng 1 để lại, trong khi trạng thái đó **sai về mặt nghiệp vụ**. `volatile`, memory barrier hoặc cơ chế khóa không tự cung cấp tính rollback.

Đừng lẫn ba mục tiêu:

1. **Mutual exclusion:** các vùng dùng cùng monitor không cùng chạy tại một thời điểm.
2. **Visibility/order:** các luồng phối hợp nhìn thấy thay đổi theo quy tắc mô hình bộ nhớ.
3. **Logical atomicity / invariant preservation:** thao tác nghiệp vụ chỉ công bố trạng thái hợp lệ theo hợp đồng, kể cả nếu thất bại.

`synchronized` đóng góp trực tiếp cho hai mục đầu. Mục thứ ba phụ thuộc **thuật toán và ranh giới cập nhật**; khóa có thể là một phần của giải pháp nhưng không thay thế giải pháp đó.

## 6. Ba mức bảo đảm khi có ngoại lệ

| Mức bảo đảm | Trạng thái sau khi thao tác thất bại | Liên quan tới `synchronized` |
|---|---|---|
| **Không có bảo đảm hữu ích** | Có thể đã vi phạm invariant, cần sửa chữa hoặc bỏ đối tượng | Khóa vẫn có thể đã nhả đúng; `unsafeTransfer` là ví dụ |
| **Basic exception safety** | Đối tượng vẫn hợp lệ, không rò rỉ tài nguyên, nhưng có thể đã thay đổi một phần theo hợp đồng | Cần đảm bảo mọi điểm dừng do lỗi vẫn giữ invariant; mutex chỉ bảo vệ quyền truy cập |
| **Strong exception safety** | Thao tác thất bại để lại trạng thái quan sát được như trước (*commit toàn bộ hoặc không commit*) | Thường dùng validate → prepare → commit, snapshot bất biến, rollback/transaction |

Cụm “không ném ngoại lệ” là một mục tiêu khác và phải nêu rõ phạm vi, vì lỗi hạ tầng nghiêm trọng hay tiến trình bị dừng có thể nằm ngoài bảo đảm hợp lý của API. Một phương thức `synchronized` không mặc nhiên đạt cả **basic guarantee**. Nếu nó để invariant sai sau khi lỗi, mức basic cũng thất bại dù khóa đã được giải phóng.

## 7. Thiết kế an toàn hơn: validate → prepare → commit

Để giữ invariant, hãy sắp xếp các thao tác theo ba pha:

- **Validate:** kiểm tra tham số, trạng thái hiện tại và các ràng buộc; thất bại trước khi thay đổi dữ liệu live.
- **Prepare:** tính toàn bộ giá trị dự kiến, kiểm tra tràn số, xây dựng snapshot mới trong biến cục bộ; nếu thất bại, bản đang sử dụng không đổi.
- **Commit:** công bố trạng thái mới qua thao tác càng đơn giản càng tốt và không gọi callback hoặc I/O có thể lỗi ở giữa.

Một lớp cặp số dư có thể sử dụng một `record` bất biến:

~~~java
// Trích đoạn khai báo trong một lớp, không phải chương trình Java độc lập.
record Balances(long a, long b) {}

private Balances balances = new Balances(100, 50);

public synchronized void transfer(long amount) {
    Balances current = balances;
    if (amount <= 0 || amount > current.a()) {
        throw new IllegalArgumentException("invalid transfer amount");
    }

    long nextA = Math.subtractExact(current.a(), amount);
    long nextB = Math.addExact(current.b(), amount);
    Balances next = new Balances(nextA, nextB);

    balances = next; // Một điểm công bố snapshot mới.
}

public synchronized Balances snapshot() {
    return balances;
}
~~~

Trong đoạn này, cặp `a`/`b` được chuẩn bị hoàn toàn trước khi công bố. Nếu kiểm tra, số học hoặc tạo snapshot ném ngoại lệ, `balances` vẫn giữ tham chiếu cũ. `Balances` chỉ chứa hai giá trị nguyên thủy nên không làm lộ dữ liệu mutable bên trong; nếu record chứa `List`, `Map` hoặc array có thể thay đổi, cần tiếp tục thiết kế bất biến sâu/sao chép phòng vệ.

**Vì sao vẫn dùng `synchronized`?** Để các writer không cùng đọc một snapshot cũ rồi lần lượt ghi đè lẫn nhau (*lost update*), và để reader thấy cập nhật theo cùng cơ chế khóa. Một phép gán tham chiếu đơn lẻ không tự giải quyết việc nhiều luồng cùng tranh chấp hoặc việc công bố an toàn khi reader bỏ qua khóa.

Nếu cần không dùng monitor, có thể biểu diễn trạng thái bất biến bằng `AtomicReference<Balances>` và vòng lặp `compareAndSet` cho các cập nhật tranh chấp. Điều kiện và dữ liệu mới phải được tính từ snapshot đọc được trong từng lượt CAS; khi CAS thất bại phải đọc lại và kiểm tra lại. Đây là một lựa chọn thiết kế concurrency, không phải biện pháp tự rollback cho side effect bên ngoài.

## 8. Đặt vị trí bắt exception ở đâu?

### 8.1. `catch` ở bên ngoài khối đồng bộ

~~~java
// Mã minh họa; lock và doWork() được khai báo ở nơi khác.
try {
    synchronized (lock) {
        doWork();
    }
} catch (RuntimeException ex) {
    reportFailure(ex);
}
~~~

Nếu `doWork()` ném lỗi, khối `synchronized` đã thoát và monitor của lần vào đó đã được nhả trước khi `reportFailure` chạy. Tuy nhiên, việc catch nằm ngoài **không khôi phục** các trường mà `doWork` đã chỉnh sửa.

### 8.2. `catch` ở bên trong khối đồng bộ

~~~java
synchronized (lock) {
    try {
        doWork();
    } catch (RuntimeException ex) {
        repairIfPossible(ex);
    }
    // Vẫn đang giữ monitor lock ở vị trí này.
}
~~~

Handler chạy khi monitor vẫn được giữ (trừ hành vi đặc biệt của các thao tác như `wait` nếu bản thân handler gọi). Điều này có thể hữu ích nếu có thể phục hồi invariant **ngay dưới cùng khóa** trước khi luồng khác được phép đọc. Nhưng rollback phải thực sự chính xác; nuốt ngoại lệ rồi tiếp tục với trạng thái chưa khôi phục có thể gây lỗi kín đáo hơn.

Nếu `repairIfPossible` tự ném ngoại lệ, JVM vẫn nhả monitor khi thoát khối, nhưng trạng thái có thể dở dang. Mọi con đường ném lỗi, kể cả đường khắc phục lỗi, phải được xét.

### 8.3. `finally` và bảo toàn trạng thái

`finally` thường được dùng cho cleanup, nhưng `synchronized` **không cần một `finally` thủ công để nhả monitor**. Ví dụ:

~~~java
synchronized (lock) {
    try {
        performWork();
    } finally {
        closeTemporaryResource();
    }
}
~~~

Dù `performWork()` ném lỗi, `finally` được thực hiện trước khi khối đồng bộ kết thúc bình thường hoặc bất thường. Nếu `closeTemporaryResource()` cũng ném lỗi, nó có thể thay thế ngoại lệ ban đầu nếu không được xử lý thích hợp; hãy thiết kế cleanup và báo lỗi có chủ đích. Việc cleanup/rollback tài nguyên là **trách nhiệm khác** với nhả monitor.

## 9. Phân biệt `synchronized` với `Lock` dùng thủ công

`synchronized` được ngôn ngữ và JVM bảo đảm giải phóng monitor khi thoát vùng đồng bộ. `ReentrantLock` và các `Lock` khác cung cấp API lấy/nhả khóa **tường minh**; ứng dụng phải gọi `unlock()` đúng cách.

Mẫu phổ biến với `ReentrantLock`:

~~~java
// Trích đoạn trong lớp có:
 // private final java.util.concurrent.locks.ReentrantLock lock =
 //         new java.util.concurrent.locks.ReentrantLock();
lock.lock();
try {
    validateAndUpdate();
} finally {
    lock.unlock();
}
~~~

Nếu `validateAndUpdate()` ném ngoại lệ, `finally` bảo đảm lời gọi `unlock()` được thực hiện trên đường thoát này. Nhưng `unlock()` cũng chỉ nhả khóa, **không hoàn tác** những gì `validateAndUpdate()` đã ghi.

Nếu lấy khóa bằng `lockInterruptibly()` hoặc `tryLock()`, chỉ gọi `unlock()` khi đã thực sự lấy được khóa. `ReentrantLock` có thêm tính năng so với `synchronized` (ví dụ thử lấy khóa, chờ có thể bị ngắt, `Condition`), nhưng không cung cấp transaction miền nghiệp vụ tự động.

## 10. Những nơi có thể làm thất bại khi đã cầm khóa

Không nên chỉ tìm câu lệnh `throw` viết sẵn trong phương thức; ngoại lệ có thể phát sinh tại:

| Vị trí | Khả năng lỗi | Hướng giảm rủi ro |
|---|---|---|
| Gọi `Math.addExact`/`subtractExact` | `ArithmeticException` do overflow | Tính trước vào biến cục bộ |
| Thao tác với collection | `NullPointerException`, `IllegalArgumentException`, thay đổi cấu trúc hoặc lỗi cấp phát | Sao chép dữ liệu, xác thực toàn bộ, áp dụng vào bản tạm |
| `new`, tạo cấu trúc dữ liệu | Lỗi cấp phát, constructor ném exception | Chuẩn bị đối tượng mới trước khi thay tham chiếu live |
| Setter, listener hoặc callback | Có thể ném ngoại lệ hay sửa ngược trạng thái | Giảm callback trong vùng commit; xác định rõ trạng thái khi callback lỗi |
| Ghi file/cơ sở dữ liệu/network | IOException, timeout, lỗi dịch vụ; có thể có side effect | Phân biệt transaction và thao tác ngoài; xác định cơ chế bù hoặc idempotency |
| Ghi log, thông báo sự kiện | Logger/appender/listener có thể lỗi | Không để lỗi phụ che mất lỗi chính hoặc làm mơ hồ tình trạng commit |
| Cơ chế retry | Có thể thực hiện lại phần công việc đã hoàn tất | Thiết kế idempotency và đánh dấu tiến độ theo hợp đồng |

Nếu một phương thức viết:

~~~java
synchronized (lock) {
    decrementInventory();
    sendPaymentRequest();
    saveOrder();
}
~~~

thì khóa chỉ điều phối luồng Java dùng monitor `lock`. Nó **không** biến ba lời gọi thành một transaction và không làm bên thanh toán hoàn tiền nếu `saveOrder()` thất bại. Trong phần lỗi liên hệ dịch vụ ngoài, ngay cả câu hỏi “bên kia đã xử lý chưa?” đôi khi không thể trả lời chỉ bằng exception do client nhận được.

## 11. `wait`, `notify` và invariant tạm thời

Đây là trường hợp quan trọng vì quy tắc “đang trong `synchronized` thì luôn giữ khóa cho đến cuối khối” có ngoại lệ về **`Object.wait()`**.

Ví dụ một phương thức chờ điều kiện:

~~~java
// Trích đoạn dùng lock, ready và currentValue đã khai báo ở nơi khác.
synchronized (lock) {
    while (!ready) {
        lock.wait(); // Nhả monitor lock tạm thời khi chờ.
    }
    use(currentValue);
}
~~~

`wait()` chỉ được gọi khi luồng đang giữ monitor của `lock`; nếu không, `IllegalMonitorStateException` có thể xảy ra. Trong lúc chờ, luồng đã nhả monitor tương ứng để luồng khác có thể cập nhật `ready` rồi thông báo. Trước khi `wait()` trả về (kể cả khi bị ngắt và ném `InterruptedException`), luồng phải lấy lại monitor đó.

Vì một luồng khác có thể thay đổi điều kiện, luôn kiểm tra lại điều kiện trong **vòng `while`**, không giả định cứ được đánh thức là dữ liệu đủ điều kiện. Java cho phép *spurious wakeup*; `notify` cũng không bảo đảm điều kiện nghiệp vụ trở thành đúng.

**Liên hệ bất biến:** trước khi thực sự vào trạng thái chờ và nhả monitor, cấu trúc dữ liệu chia sẻ phải nằm ở trạng thái các luồng khác được phép nhìn thấy. Nếu bạn chỉnh một nửa cấu trúc rồi gọi `wait()`, luồng khác có thể lấy monitor và thấy dữ liệu dở dang. Cũng cần tránh giữ các monitor khác vô tình gây deadlock khi chờ.

## 12. Bảo đảm bất biến khi có nhiều đối tượng hoặc nhiều khóa

Ví dụ có hai `Account` khác nhau:

~~~java
// Mã minh họa về điều kiện chưa đủ để an toàn.
synchronized (source) {
    source.debit(amount);
}
synchronized (destination) {
    destination.credit(amount);
}
~~~

Hai khối sử dụng hai monitor khác nhau và có một khoảng trống giữa chúng. Nếu phần ghi tài khoản đích lỗi, phần ghi nguồn vẫn tồn tại. Ngay cả khi lồng hai khóa:

~~~java
// Mã minh họa: chỉ cho thấy cùng giữ khóa, chưa bảo đảm rollback.
synchronized (source) {
    synchronized (destination) {
        source.debit(amount);
        destination.credit(amount);
    }
}
~~~

một exception từ `credit` vẫn có thể khiến nguồn đã bị trừ. Ngoài ra, nếu luồng khác khóa `destination` rồi `source`, chương trình có nguy cơ deadlock do thứ tự khóa đảo ngược.

Để thiết kế một thao tác chuyển tiền đáng tin cậy cần xem xét đồng thời:

1. Khóa/transaction bao phủ **tất cả** phần trạng thái phải thay đổi cùng nhau.
2. Kiểm tra đủ tiền và điều kiện của tài khoản đích dưới cùng cơ chế bảo vệ trạng thái.
3. Tính trước kết quả, kiểm tra overflow và mọi lỗi dự kiến trước commit.
4. Chọn điểm commit hoặc cơ chế rollback mà reader không thể thấy trạng thái trung gian ngoài hợp đồng.
5. Định nghĩa thứ tự lấy khóa ổn định nếu phải lấy nhiều lock; cân nhắc transaction DB cho dữ liệu lưu bền vững.
6. Không giả định hệ thống ngoài JVM hoặc ngoài transaction địa phương chịu sự kiểm soát của monitor Java.

Lưu ý: nguyên tắc **bảo vệ cùng monitor** chỉ có hiệu quả khi toàn bộ đường truy cập và thay đổi trạng thái liên quan đều tuân thủ. Một getter không đồng bộ hoặc trả trực tiếp danh sách nội bộ mutable có thể làm lộ trạng thái trung gian; `synchronized` ở writer không tự khóa getter đó.

## 13. Thiết kế API exception và rollback đúng mức

Tài liệu API nên nói rõ cả **điều kiện ném ngoại lệ** và **trạng thái sau thất bại**. Những cách diễn đạt có ý nghĩa khác nhau:

- “Nếu `amount` không hợp lệ, ném `IllegalArgumentException` và không thay đổi số dư”: cam kết rõ cho lỗi kiểm tra đầu vào.
- “Nếu thao tác thất bại, đối tượng vẫn thỏa mọi invariant nhưng các phần cập nhật trước đó có thể còn hiệu lực”: basic guarantee.
- “Nếu thao tác thất bại trước commit, không có thay đổi trạng thái nào được công bố”: cam kết strong trong phạm vi trước commit.
- “Nếu gửi yêu cầu thanh toán thất bại, trạng thái xử lý thanh toán có thể cần tra soát”: tránh hứa rollback khi lỗi mạng không xác định trạng thái hệ thống ngoài.

Nếu chủ động rollback trong `catch`, phải tính đến khả năng rollback cũng thất bại. Ví dụ rollback “cộng lại số tiền đã trừ” không phải lúc nào cũng đảo ngược chính xác các cập nhật khác hoặc tương tác song song. Cần tính toán sự toàn vẹn qua nhiều loại ngoại lệ, kể cả ngoại lệ từ cleanup. `try-with-resources` có cơ chế ghi nhận một số lỗi đóng tài nguyên qua `getSuppressed()`, nhưng nó không tự rollback dữ liệu nghiệp vụ.

Với `InterruptedException`, không được tùy tiện nuốt tín hiệu hủy tác vụ chỉ để “đi đến cuối `synchronized`”. Nếu cần truyền tiếp, khai báo `throws InterruptedException`; nếu bắt và chuyển sang unchecked trong tình huống phù hợp, cân nhắc khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()` và giữ `cause`. Dù lựa chọn nào, invariant cần được duy trì trên đường thoát đó.

## 14. Những hiểu lầm phổ biến và cách sửa

1. **“Có `synchronized` thì lỗi sẽ tự rollback.”** Sai: khóa quản lý monitor. Khắc phục bằng thiết kế validate → prepare → commit, snapshot bất biến hoặc transaction.
2. **“Ném exception trong `synchronized` sẽ làm khóa bị kẹt.”** Sai khi ngoại lệ khiến vùng đồng bộ kết thúc; JVM nhả monitor. Kẹt thật có thể do deadlock, vòng lặp chờ vô hạn hoặc code chưa thoát vùng đồng bộ.
3. **“Nếu luồng sau lấy được khóa thì dữ liệu chắc chắn đúng.”** Sai: luồng sau có thể đọc một trạng thái sai được công bố đầy đủ.
4. **“Chỉ cần `catch` và `return` là đã khôi phục.”** Sai: phải xác minh mọi bất biến sau nhánh xử lý lỗi.
5. **“Đặt `finally` trong `synchronized` thì tự rollback.”** Sai: `finally` chạy mã đã viết; nếu không có rollback hoặc cleanup đúng, nó không tự hoàn tác.
6. **“Hai phép gán trong một method `synchronized` luôn nguyên tử với mọi reader.”** Chỉ đúng theo nghĩa reader phối hợp qua **cùng monitor** không chen vào vùng đồng bộ; đường đọc không hợp tác vẫn có thể quan sát dữ liệu khác biệt.
7. **“`volatile` thay được `synchronized` để cập nhật nhiều trường.”** Sai: visibility của trường không biến nhiều phép gán thành một transaction.
8. **“`wait()` cứ ở trong `synchronized` nên các luồng khác không thể vào.”** Sai: `wait()` tạm nhả monitor của đối tượng được chờ.
9. **“Một transaction DB đồng nghĩa mọi email/thanh toán đi kèm cũng rollback.”** Sai: side effect ngoài ranh giới transaction cần cơ chế riêng.
10. **“Mọi lỗi đều khôi phục được bằng phép gán ngược.”** Sai khi có side effect, callback, dữ liệu biến đổi cạnh tranh, hoặc bản gốc không còn đầy đủ.

## 15. Kiểm thử đúng cả quyền truy cập và bất biến

Một bộ kiểm thử tốt phải kiểm tra **hai nhóm độc lập**, vì thành công ở một nhóm không kéo theo nhóm còn lại.

| Nhóm | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Monitor | Phương thức `synchronized` ném `RuntimeException`, một luồng khác gọi phương thức cùng monitor sau đó | Luồng sau vào được vùng đồng bộ, không bị khóa kẹt do ngoại lệ |
| Invariant | Ngoại lệ phát sinh sau phép cập nhật đầu tiên | Đánh giá có vi phạm invariant không; với hợp đồng strong, trạng thái phải nguyên vẹn |
| Input | Số tiền âm, quá số dư, tham số null | Ném đúng loại lỗi trước khi thay đổi |
| Overflow | Tổng tiền hoặc chỉ số phiên bản vượt giới hạn `long`/`int` | Không commit giá trị sai; exception được truyền đúng |
| Snapshot | Lỗi khi dựng trạng thái đề xuất | Bản trạng thái đang sử dụng không đổi |
| Concurrency | Hai luồng cùng yêu cầu thay đổi, có cùng cơ chế lock/CAS | Không mất cập nhật, không phá invariant |
| Visibility | Reader được/không được đồng bộ theo hợp đồng | Đánh giá trường hợp đọc trạng thái trung gian |
| Wait | Điều kiện chờ thay đổi hoặc đánh thức giả | `while` kiểm tra lại điều kiện; invariant vẫn đúng |
| Side effect | I/O, DB hoặc callback thất bại sau một bước thành công | Tài liệu và hành vi thống nhất về việc có rollback được không |

Trong ví dụ `SynchronizedInvariantDemo`, đầu ra “Unsafe observer” vừa chứng minh được **monitor được nhả**, vừa cho thấy **invariant bị phá**. Một test chỉ kiểm tra `assertThrows` hoặc chỉ kiểm tra luồng quan sát không bị treo sẽ bỏ sót vấn đề dữ liệu.

Lưu ý một test concurrency chạy thành công một vài lần không phải chứng minh đầy đủ không có race/deadlock. Cần lập luận về monitor được giữ, thời điểm lấy/nhả, mọi đường đọc/ghi, point of commit và các đường ngoại lệ; test giúp xác nhận những lập luận đó bằng tình huống thực tế.

## 16. Quy trình rà soát một phương thức `synchronized`

Khi đọc mã có trạng thái mutable và xử lý exception, áp dụng lần lượt các câu hỏi sau:

1. **Monitor nào được lấy?** `this`, `Class` hay một object lock riêng? Các phương thức liên quan có dùng cùng monitor không?
2. **Invariant là gì?** Viết thành mệnh đề cụ thể: tổng, miền giá trị, quan hệ giữa các trường, điều kiện đối tượng hợp lệ.
3. **Điểm đầu tiên sửa trạng thái live nằm ở đâu?** Đánh dấu từng phép gán, sửa collection hoặc side effect.
4. **Sau mỗi điểm sửa, câu lệnh nào có thể ném ngoại lệ?** Tính toán, callback, I/O, cấp phát, logging và các lần gọi phụ.
5. **Nếu thoát ngay tại điểm đó, invariant còn đúng không?** Nếu không, cần đổi thứ tự thao tác hoặc chuẩn bị trạng thái mới trước khi commit.
6. **Reader có thể thấy trạng thái trung gian không?** Xét cùng monitor, reader không hợp tác, snapshot mutable, `wait()` và những tài nguyên khác.
7. **Khả năng rollback thực sự đến đâu?** Đối tượng JVM khác với DB transaction và lệnh mạng; định nghĩa rõ đường không thể hoàn tác.
8. **Hợp đồng thất bại được ghi trong API chưa?** Loại exception, `cause`, mức bảo đảm khi thất bại và cách caller khôi phục.
9. **Test đã gây lỗi ở đúng bước nhạy cảm chưa?** Bố trí thử lỗi trước commit, trong lúc chuẩn bị và sau side effect; kiểm tra cả state lẫn khả năng lấy monitor tiếp theo.

## 17. Tổng kết kiến thức

- `synchronized` khiến JVM tự giải phóng monitor khi thoát vùng đồng bộ bình thường hoặc bất thường do ngoại lệ. Quy tắc này **không tự hoàn tác phép gán hoặc side effect**.
- Việc giải phóng monitor cung cấp điểm phối hợp và *happens-before* cho luồng khác lấy cùng monitor; luồng đó vẫn có thể nhìn thấy dữ liệu sai nếu luồng trước bỏ lại invariant bị phá.
- Giữ dữ liệu hợp lệ sau khi thao tác thất bại phải được thiết kế bằng kiểm tra điều kiện trước, chuẩn bị dữ liệu mới, xác định commit point, đồng bộ đúng phạm vi và transaction/rollback khi cần.
- `catch`/`finally` thay đổi luồng xử lý lỗi; chúng không thay thế bằng chứng rằng mọi nhánh thoát đều bảo toàn trạng thái.
- Khi đánh giá một phương thức, luôn hỏi **hai câu riêng**: “Ngoại lệ có giải phóng khóa không?” và “Dữ liệu mà luồng sau đọc được còn hợp lệ không?”

### Tham khảo chuẩn Java

- [JLS §14.19 — The synchronized Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.19)
- [JLS §17.1 — Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1)
- [JLS §17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5)
- [Java SE 17 — `Object.wait()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#wait())
- [Java SE 17 — `ReentrantLock`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)
