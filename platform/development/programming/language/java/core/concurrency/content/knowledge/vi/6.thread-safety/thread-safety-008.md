# Giữ nhất quán invariant khi nhiều trường liên quan trong Java Concurrency

**Invariant** (bất biến trạng thái) là điều kiện phải luôn đúng ở những thời điểm trạng thái được phép quan sát hoặc sử dụng. Trong chương trình đa luồng, invariant thường liên quan **nhiều trường cùng lúc**: tổng tiền trong hai ví bằng 100, số chỗ còn trống cộng số chỗ đã đặt bằng sức chứa ban đầu, khoảng `start <= end`, hoặc một đơn hàng có trạng thái `PAID` thì phải có mã thanh toán tương ứng.

Nếu hai trường được cập nhật riêng rẽ, thread khác có thể nhìn thấy một **trạng thái trung gian không hợp lệ**, ngay cả khi từng phép đọc/ghi riêng lẻ là atomic hoặc các trường đều `volatile`. Điều kiện đúng ở đầu và cuối phương thức chưa đủ nếu thread khác được phép quan sát giữa chừng. Cần xác định **ranh giới của một chuyển trạng thái**, bảo vệ mọi dữ liệu tham gia invariant, và cung cấp cách đọc một snapshot nhất quán.

Bài học thuộc **Thread Safety của Java Concurrency nói chung**; tập trung vào đồng bộ trong bộ nhớ JVM, Java Memory Model, khóa, immutable state và atomic reference. Các tích hợp riêng với Spring không thuộc phạm vi.

## 1. Invariant khác điều kiện riêng lẻ của từng trường

Giả sử một kho phiếu có hai số đếm:

- `available`: số phiếu chưa giữ chỗ;
- `reserved`: số phiếu đã giữ chỗ.

Ban đầu `available = 100`, `reserved = 0`. Yêu cầu nghiệp vụ là:

~~~text
available >= 0
reserved >= 0
available + reserved == 100
~~~

Mỗi lần đặt chỗ thành công phải chuyển một phiếu từ `available` sang `reserved`. Trước và sau phép chuyển, tổng vẫn bằng 100:

~~~text
Trước:  available=100, reserved=0, tổng=100
Sau:    available=99,  reserved=1, tổng=100
~~~

Nhưng mã sau **không thực hiện một chuyển trạng thái nguyên tử**:

~~~java
if (available > 0) {
    available--;
    reserved++;
}
~~~

Có ít nhất ba rủi ro khác nhau:

1. **Check-then-act race:** hai thread cùng thấy `available > 0` rồi đều trừ; kết quả có thể âm hoặc số đặt vượt sức chứa.
2. **Intermediate state:** thread đọc có thể quan sát sau `available--` nhưng trước `reserved++`, thấy tổng 99 dù giá trị hợp lệ ở đầu/cuối đều là 100.
3. **Visibility/ordering:** nếu truy cập biến thường mà thiếu quan hệ happens-before, thread đọc còn có thể quan sát các cập nhật theo cách không đáp ứng hợp đồng mong muốn.

Cách sửa phải bao trùm **cả điều kiện, tất cả trường được thay đổi và cách quan sát các trường**. Chỉ bọc một phép tăng, chỉ thêm `volatile`, hoặc chỉ đồng bộ phần writer đều chưa đủ.

### 1.1 Invariant và giai đoạn được phép quan sát

Trong một critical section, mã có thể tạm thời đi qua trạng thái trung gian:

~~~java
available--;
reserved++;
~~~

Nếu **mọi thread khác chỉ có thể đọc cả hai trường khi giữ cùng lock**, không thread nào bên ngoài có thể nhìn thấy trạng thái trung gian đó; invariant được duy trì tại ranh giới public của operation. Nhưng nếu một getter đọc `available` hoặc `reserved` mà **không lấy lock**, nó có thể làm lộ intermediate state.

Điều này dẫn đến nguyên tắc:

> Một invariant liên quan nhiều trường cần được giữ đúng tại mọi điểm quan sát hợp lệ. Mỗi thao tác đọc/ghi có khả năng ảnh hưởng invariant phải tuân thủ **cùng giao thức đồng bộ**.

Không có nghĩa phải dùng một mutex toàn ứng dụng. Ta chỉ cần một **ranh giới sở hữu và đồng bộ chung cho cùng một invariant**.

## 2. Ví dụ xác định: hai volatile fields vẫn lộ trạng thái không nhất quán

`volatile` bảo đảm hiệu ứng visibility/ordering cho access đến trường volatile. Nó **không nhóm** hai trường thành một giao dịch nguyên tử.

Để tái hiện chính xác thời điểm trạng thái bị lệch mà không dựa vào may rủi scheduler, dùng hai `CountDownLatch` để tạm dừng writer sau lần trừ đầu tiên.

Tạo tệp `VolatilePairInvariantDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public final class VolatilePairInvariantDemo {
    private static final class Counters {
        volatile int available = 100;
        volatile int reserved = 0;
    }

    public static void main(String[] args) throws InterruptedException {
        Counters counters = new Counters();
        CountDownLatch debited = new CountDownLatch(1);
        CountDownLatch continueWriter = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            counters.available--;
            debited.countDown();

            try {
                continueWriter.await();
                counters.reserved++;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "writer");

        writer.start();
        debited.await();

        System.out.println("During update: "
                + (counters.available + counters.reserved));

        continueWriter.countDown();
        writer.join();

        System.out.println("After update: "
                + (counters.available + counters.reserved));
    }
}
~~~

Biên dịch và chạy trên JDK 17 trở lên:

~~~bash
javac VolatilePairInvariantDemo.java
java VolatilePairInvariantDemo
~~~

Trong lần chạy bình thường, không có external interruption:

~~~text
During update: 99
After update: 100
~~~

**Vì sao ví dụ xác định?** Writer trừ `available` rồi gọi `debited.countDown()`; main đợi `debited.await()` thành công rồi đọc hai trường, trong khi writer chưa thể tăng `reserved` vì đang đợi `continueWriter`. Main sau đó mở cổng và join writer. Latch chỉ tạo lịch xen kẽ xác định cho demo. **Lỗi thiết kế là hai lần cập nhật nằm trong hai bước mà reader có thể quan sát ở giữa.**

Ở đây mỗi field là volatile, nhưng tại điểm quan sát giữa hai bước, dữ liệu thật sự có trạng thái `available=99, reserved=0`. Đây không phải vấn đề “CPU chưa flush cache”; đây là **thiếu atomicity ở cấp nhóm trường**. Nếu chỉ sửa visibility mà không sửa ranh giới operation, invariant vẫn có thể bị phá.

**Giới hạn của demo:** khi có interruption ngoài làm writer thoát sớm, kết quả sau cùng có thể khác. Đoạn này nhằm giải thích atomicity, chưa phải giải pháp production. Một operation thật phải định nghĩa chính sách hủy, lỗi và rollback để không để trạng thái dở dang.

## 3. Xác định nhóm trường nào phải thay đổi cùng nhau

Trước khi chọn lock, hãy viết rõ các điều kiện bất biến của object hoặc subsystem:

| Ví dụ | Các trường liên quan | Điều kiện phải đúng |
| --- | --- | --- |
| Sức chứa | `available`, `reserved` | Cả hai không âm; tổng bằng capacity. |
| Tài khoản nội bộ | `checking`, `savings` | Tổng nội bộ bảo toàn khi chuyển tiền giữa ví; không âm. |
| Khoảng thời gian | `start`, `end` | `start <= end` trong mỗi snapshot được công bố. |
| Trạng thái thanh toán | `status`, `paymentId` | Khi `status == PAID`, ID thanh toán tồn tại. |
| Bộ đếm thống kê | `success`, `failure`, `processed` | Nếu số processed được cập nhật cùng một giao dịch logic thì `success + failure == processed` tại điểm quan sát. |
| Cấu hình | `host`, `port`, `version` | Mọi lần đọc lấy các giá trị thuộc **cùng một phiên bản**. |

Những ví dụ là **mô hình nghiệp vụ minh họa**: trong hệ thống thật, invariant có thể khác (chẳng hạn sự kiện hủy đặt chỗ làm thay đổi capacity, hoặc một giao dịch thanh toán đang ở trạng thái trung gian `PENDING` hợp lệ). Hãy xác định **trạng thái nào được phép tồn tại**, khi nào được phép publish, và trạng thái trung gian nào bị cấm quan sát.

Một quy trình tốt:

1. Liệt kê tất cả trường và object tham gia invariant.
2. Tìm **mọi điểm ghi**, kể cả constructor, setter, callback, thread nền, scheduler và hàm reset.
3. Tìm **mọi điểm đọc**: getter, report, logging, serializer, thuật toán khác.
4. Quy định một operation có hiệu lực cùng lúc ở đâu (điểm tuyến tính hóa nếu API cần linearizability).
5. Buộc mọi đường truy cập liên quan tuân thủ **một giao thức thống nhất**.
6. Kiểm tra lỗi, exception, interruption và các branch sớm vẫn bảo toàn invariant.

Không nên chỉ sửa phương thức writer được nhìn thấy đầu tiên rồi bỏ qua getter hoặc những đường đọc khác.

## 4. Giải pháp cơ bản: một lock bảo vệ toàn bộ invariant

`synchronized` là lựa chọn trực tiếp và dễ chứng minh khi nhiều trường của cùng một object phải cập nhật cùng nhau. Một lock riêng thuộc object bảo vệ **toàn bộ** state; caller chỉ sử dụng các method đã đồng bộ.

Tạo tệp `LockedInvariantDemo.java`:

~~~java
public final class LockedInvariantDemo {
    private static final class ReservationLedger {
        private final Object lock = new Object();
        private int available = 100;
        private int reserved;

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

        Snapshot snapshot() {
            synchronized (lock) {
                return new Snapshot(available, reserved);
            }
        }
    }

    private record Snapshot(int available, int reserved) {
        int total() {
            return available + reserved;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ReservationLedger ledger = new ReservationLedger();

        Runnable reserve = () -> {
            for (int i = 0; i < 100; i++) {
                ledger.reserveOne();
            }
        };

        Thread first = new Thread(reserve, "first");
        Thread second = new Thread(reserve, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        Snapshot result = ledger.snapshot();
        System.out.println("Available: " + result.available());
        System.out.println("Reserved: " + result.reserved());
        System.out.println("Total: " + result.total());
    }
}
~~~

Lệnh chạy Java 17+:

~~~bash
javac LockedInvariantDemo.java
java LockedInvariantDemo
~~~

Stdout:

~~~text
Available: 0
Reserved: 100
Total: 100
~~~

### 4.1 Vì sao bảo toàn invariant?

- Mỗi lời gọi `reserveOne()` giữ cùng monitor `lock` trong suốt **check + decrement + increment**. Không có hai lời gọi `reserveOne` nào chen vào giữa các bước của nhau.
- Khi không còn phiếu, method trả `false` mà không sửa state. Điều kiện `available >= 0` được giữ.
- Một lần reserve thành công biến trạng thái từ `(a, r)` sang `(a-1, r+1)`. Tổng không đổi: `(a-1)+(r+1)=a+r`.
- `snapshot()` lấy **chính lock đó**, tạo một cặp giá trị đồng thời được đọc ở ranh giới hợp lệ. Reader không thấy trạng thái sau trừ nhưng trước cộng.
- Hai worker mỗi worker thử đặt tối đa 100 lần; tổng thể có đúng 100 lượt thành công, bất kể thread nào được scheduler chọn trước. Sau `join()`, main thấy các cập nhật đã hoàn thành.
- `Snapshot` là một `record` bất biến gồm primitive components, nên có thể đọc bên ngoài lock sau khi được trả về mà không thấy hai trường bị thay đổi riêng rẽ.

### 4.2 Điểm tuyến tính hóa và cách đọc atomic

Với API `reserveOne()`, toàn bộ chuyển trạng thái được bảo vệ bởi lock. Có thể coi operation có hiệu lực tại một điểm bên trong critical section trước khi nhả lock. Cách quan sát kết quả qua `snapshot()` luôn tương ứng một trạng thái trước hoặc sau một operation hoàn chỉnh.

**Sai lầm phổ biến** là đồng bộ writer nhưng không đồng bộ reader:

~~~java
synchronized (lock) {
    available--;
    reserved++;
}

// Một getter ngoài lock ở thread khác:
int total = available + reserved; // Không có snapshot/đồng bộ đúng.
~~~

Đây là **mảnh code lỗi minh họa**. Dùng một getter `getAvailable()` có lock và một getter `getReserved()` cũng có lock **riêng từng lần** chưa đủ để ghép thành một snapshot: giữa hai lần gọi, writer vẫn có thể thực hiện operation mới. Cần một method `snapshot()` đọc **tất cả trường liên quan dưới cùng một lần lock**.

## 5. Encapsulation: sở hữu state quan trọng hơn từ khóa synchronized

Thread safety bị phá nếu caller có thể sửa một trong các trường mà không dùng cùng protocol.

Nên giữ state ở mức `private`, tránh trả trực tiếp mutable object tham gia invariant, và cung cấp operation ở cấp nghiệp vụ:

~~~java
final class Range {
    private final Object lock = new Object();
    private int start;
    private int end;

    Range(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
        this.start = start;
        this.end = end;
    }

    void move(int newStart, int newEnd) {
        if (newStart > newEnd) {
            throw new IllegalArgumentException("start > end");
        }
        synchronized (lock) {
            start = newStart;
            end = newEnd;
        }
    }

    Snapshot snapshot() {
        synchronized (lock) {
            return new Snapshot(start, end);
        }
    }

    record Snapshot(int start, int end) {}
}
~~~

Đây là **mảnh class minh họa**, không có `main`. Mặc dù bên trong `move` có khoảnh khắc `start` đổi trước `end`, code bên ngoài chỉ có thể quan sát qua `snapshot` dưới cùng lock. Việc kiểm tra `newStart <= newEnd` có thể đặt trước lock vì phụ thuộc **chỉ vào hai tham số immutable theo giá trị**, không phụ thuộc state đang thay đổi.

Ngược lại, điều kiện kiểu “nếu `start` hiện tại bằng X thì đổi `end`” phải được kiểm tra **bên trong cùng critical section** với phép cập nhật; kiểm tra trạng thái chia sẻ ngoài lock sẽ tạo *check-then-act race*.

### 5.1 Trả snapshot thay vì tham chiếu mutable

Nếu object quản lý `List<Order>` hoặc `Map<String, Item>`, một getter trả thẳng collection mutable có thể cho caller sửa trạng thái không qua lock. Chỉ bọc `synchronized` quanh getter không ngăn được sửa đổi sau khi reference được trả ra.

Đưa ra bản snapshot copy có chủ đích:

~~~java
List<String> snapshot() {
    synchronized (lock) {
        return List.copyOf(items);
    }
}
~~~

Mảnh minh họa giả định `items`, `lock` đã khai báo và items không chứa null (vì `List.copyOf` không chấp nhận phần tử null). Danh sách trả về không cho caller sửa cấu trúc danh sách, nhưng **nếu phần tử bên trong mutable**, copy này chỉ là copy *nông*. Muốn công bố snapshot bất biến sâu, cần phần tử immutable hoặc sao chép dữ liệu thành value objects phù hợp.

Không để `this` hoặc reference đến state còn đang xây dựng thoát khỏi constructor, vì thread khác có thể quan sát object khi invariant khởi tạo chưa hoàn tất.

## 6. ReentrantLock khi cần nhiều điều khiển hơn

`java.util.concurrent.locks.ReentrantLock` có các bảo đảm mutual exclusion và memory effect tương tự monitor khi lock/unlock đúng cách, đồng thời hỗ trợ timed acquisition, interruptible lock và điều kiện `Condition`.

Ví dụ mảnh class dùng `tryLock`, deadline chờ và `finally`:

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

final class TimedLedger {
    private final ReentrantLock lock = new ReentrantLock();
    private int available = 100;
    private int reserved;

    boolean reserveOne() throws InterruptedException {
        if (!lock.tryLock(200, TimeUnit.MILLISECONDS)) {
            return false; // Không lấy được lock trong khoảng chờ.
        }
        try {
            if (available == 0) {
                return false;
            }
            available--;
            reserved++;
            return true;
        } finally {
            lock.unlock();
        }
    }
}
~~~

Đây là **mảnh code minh họa không có main**, nhưng có thể biên dịch cùng import tương ứng. Cần phân biệt `false` vì hết hạn lấy lock với `false` vì hết quota nếu hợp đồng nghiệp vụ cần nêu rõ nguyên nhân.

Những nguyên tắc bắt buộc:

- Luôn nhả lock trong `finally` ngay sau khi đã acquire thành công.
- Mọi đường đọc state cũng phải dùng **cùng ReentrantLock**; một getter không lock có thể làm lộ trạng thái trung gian.
- `tryLock(timeout)` giới hạn thời gian **chờ lấy lock**, không giới hạn thời gian thực hiện critical section.
- Nếu `InterruptedException` xuất hiện trước khi lấy lock, không được gọi `unlock()` khi thread chưa sở hữu lock.
- Fair lock `new ReentrantLock(true)` có thể thay đổi thứ tự phục vụ khi tranh chấp, nhưng **không** bảo đảm thời hạn hoàn thành; fairness không sửa invariant sai.

Không nên chọn `ReentrantLock` chỉ vì tin rằng nó “thread-safe hơn synchronized”. Đầu tiên hãy thiết kế đúng ownership và invariant; chọn primitive dựa trên nhu cầu timeout, interruption, điều kiện đợi hoặc đo lường tải.

## 7. Immutable state và AtomicReference: cập nhật cả nhóm như một giá trị

Thay vì lưu hai biến mutable độc lập, có thể gom chúng vào một **value object bất biến**, rồi lưu duy nhất **reference** đến state hiện tại. Mọi lần cập nhật tạo ra một snapshot mới, sau đó thay reference bằng CAS.

Tạo `AtomicInvariantDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public final class AtomicInvariantDemo {
    private record State(int available, int reserved) {
        int total() {
            return available + reserved;
        }
    }

    private final AtomicReference<State> state =
            new AtomicReference<>(new State(100, 0));

    boolean reserveOne() {
        while (true) {
            State current = state.get();
            if (current.available() == 0) {
                return false;
            }

            State next = new State(
                    current.available() - 1,
                    current.reserved() + 1
            );
            if (state.compareAndSet(current, next)) {
                return true;
            }
            // Có contender thay state; đọc lại snapshot rồi thử CAS.
        }
    }

    State snapshot() {
        return state.get();
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInvariantDemo ledger = new AtomicInvariantDemo();

        Runnable reserve = () -> {
            for (int i = 0; i < 100; i++) {
                ledger.reserveOne();
            }
        };

        Thread first = new Thread(reserve, "first");
        Thread second = new Thread(reserve, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        State result = ledger.snapshot();
        System.out.println("Available: " + result.available());
        System.out.println("Reserved: " + result.reserved());
        System.out.println("Total: " + result.total());
    }
}
~~~

Lệnh chạy Java 17+:

~~~bash
javac AtomicInvariantDemo.java
java AtomicInvariantDemo
~~~

Stdout:

~~~text
Available: 0
Reserved: 100
Total: 100
~~~

### 7.1 Vì sao một AtomicReference giải quyết được nhiều trường?

- `State` là `record` bất biến chứa **cả hai** số đếm. Một reader gọi `state.get()` một lần sẽ giữ reference đến **một snapshot đầy đủ**.
- Writer tạo `next` dựa trên một snapshot hiện tại, giữ invariant trong chính snapshot mới.
- `compareAndSet(current, next)` chỉ thành công nếu reference vẫn là `current`. Một thread thành công là **điểm tuyến tính hóa** của operation thay state.
- Nếu contender đã thay state trước, CAS thất bại; writer bỏ candidate cũ, đọc lại và tính trạng thái mới. Vì thế không ghi đè một cập nhật hợp lệ của thread khác.
- Reader không thấy bước `available--` tách rời bước `reserved++`: các trường của state mới đã được tạo xong **trước khi** reference được công bố.
- Với giả định các giá trị nằm trong miền hợp lệ và không có writer ngoài protocol, invariant `available + reserved == 100` được giữ trong mọi `State` đã publish.

### 7.2 Giới hạn và trade-off của CAS

Một CAS loop không bảo đảm một thread cụ thể sẽ thành công trong số lần thử hữu hạn dưới tranh chấp lớn; có thể xảy ra **starvation** dù toàn hệ thống vẫn tiến triển. Không thực hiện I/O, gửi email, trừ tiền ngoài JVM hoặc side effect không thể lặp an toàn bên trong hàm tính `next`: CAS có thể thất bại và logic phải chạy lại.

Mỗi lần thành công tạo một `State` mới, gây allocation và áp lực GC. Với state nhỏ và read-heavy, immutable snapshot có thể rất phù hợp; với cập nhật cực nhiều hoặc state phức tạp, cần đo performance so với lock.

Không gọi hai lần `state.get()` rồi ghép một trường từ snapshot cũ với một trường từ snapshot mới:

~~~java
int a = state.get().available();
int b = state.get().reserved(); // Có thể thuộc phiên bản khác.
~~~

Đây là mảnh mã lỗi minh họa. Đúng là:

~~~java
State oneSnapshot = state.get();
int a = oneSnapshot.available();
int b = oneSnapshot.reserved();
~~~

Hai phép đọc từ cùng `oneSnapshot` giữ consistency của phiên bản đó. Với state chứa reference đến collection mutable, record không tự tạo bất biến sâu; cần đảm bảo state và object graph bên trong thực sự immutable theo hợp đồng.

### 7.3 ABA và thay đổi theo phiên bản

`compareAndSet` của `AtomicReference` so sánh reference hiện tại với expected reference. Khi tái dùng mutable object/reference hoặc state chuyển A→B→A, thuật toán phức tạp có thể gặp **ABA problem**: giá trị trông giống ban đầu nhưng lịch sử đã thay đổi. Ví dụ phía trên tạo mỗi `State` mới và không tái sử dụng các instance cũ, nên CAS của các thao tác này phân biệt những lần cập nhật theo identity một cách phù hợp.

Nếu nghiệp vụ yêu cầu biết **version** hoặc phát hiện bất kỳ thay đổi trung gian, có thể lưu version trong state mới và tăng cùng operation, hoặc dùng `AtomicStampedReference` khi đúng nhu cầu. Không thêm version chỉ vì “có concurrency”; đầu tiên xác định yêu cầu thông tin lịch sử.

## 8. Tại sao nhiều AtomicInteger độc lập chưa đủ?

Sai lầm thường gặp:

~~~java
AtomicInteger available = new AtomicInteger(100);
AtomicInteger reserved = new AtomicInteger();

if (available.get() > 0) {
    available.decrementAndGet();
    reserved.incrementAndGet();
}
~~~

Mỗi phép `get()`, `decrementAndGet()` và `incrementAndGet()` có atomicity theo **một biến**. Nhưng toàn bộ đoạn vẫn tồn tại:

- **Check-then-act race:** hai thread đều thấy `available > 0` và cùng giảm.
- **Snapshot torn:** reader có thể quan sát trạng thái sau khi available giảm nhưng trước khi reserved tăng.
- **Inconsistency khi lỗi:** nếu có exception hoặc hủy giữa hai bước, biến thứ hai có thể không được cập nhật.

Ngay cả sửa check-then-act bằng `available.updateAndGet(...)` hoặc vòng CAS riêng cho `available` cũng không khiến phép tăng `reserved` nằm trong cùng transaction. Muốn bảo vệ **invariant liên quan cả hai biến**, hãy dùng một critical section chung hoặc gói cả hai vào một immutable state dưới `AtomicReference<State>`.

Các bộ đếm **độc lập theo thiết kế** là trường hợp khác: ví dụ số request thành công và số request thất bại được dùng cho metrics cuối kỳ, và hệ thống chấp nhận snapshot tạm thời lệch khi cập nhật. Khi không có invariant phải đúng ở mọi điểm đọc, nhiều atomic counters có thể hợp lý. Điều này cần được nêu rõ trong hợp đồng quan sát, không thể mặc định.

## 9. Chọn synchronized, Lock, immutable snapshot hay atomic CAS

| Kỹ thuật | Điểm mạnh | Chi phí/hạn chế | Phù hợp khi |
| --- | --- | --- | --- |
| `synchronized` với private lock | Dễ hiểu, dễ chứng minh atomic chuyển trạng thái nhiều trường; memory visibility rõ. | Thread có thể block khi contention; cần tuân thủ lock ở mọi đường đọc/ghi. | State nhỏ/vừa, invariant phức tạp, cần correctness rõ ràng. |
| `ReentrantLock` | Timeout, interruptible acquisition, Condition, có thể đo contention. | Phải unlock chính xác trong finally; tăng số nhánh lỗi/lifecycle. | Cần policy lấy lock/timeout phức tạp. |
| Immutable snapshot + `volatile` reference | Reader lấy snapshot nhất quán mà không block trên lock đọc. | Nếu có nhiều writer thì phép thay reference đơn giản có thể mất cập nhật. | Một writer publish cấu hình/snapshot hoàn chỉnh, nhiều reader. |
| Immutable snapshot + `AtomicReference` CAS | Cập nhật **cả nhóm state** atomically bằng thay reference; reader đọc một snapshot. | Retry khi contention, allocation, phức tạp nếu có side effects. | State gọn, bất biến, optimistic update. |
| `ReadWriteLock` | Cho nhiều reader cùng đọc và writer cập nhật độc quyền theo policy. | Dễ có contention, writer starvation tùy policy, overhead cao hơn lock thường. | Đọc nhiều, write ít, vùng đọc đủ lớn để có lợi. |
| `StampedLock` | Có cơ chế optimistic read + validate phù hợp một số workload. | Protocol khó hơn, không reentrant; phải validate đúng, không dùng kết quả thiếu nhất quán trước validate. | Workload đo đạc chứng minh lợi ích và team hiểu protocol. |

`volatile` trên từng field không thay thế atomic snapshot. Với `StampedLock`, optimistic read có thể thấy trạng thái trung gian trong lúc writer thay đổi; chỉ dùng kết quả sau validation thành công, và không dereference/đưa ra side effect dựa trên dữ liệu có thể thiếu nhất quán trước validate. Đừng dùng optimistic read để thao tác trên object graph mutable nếu không hiểu rủi ro của việc quan sát dữ liệu đang thay đổi.

**Lựa chọn mặc định:** ưu tiên một private lock và API nghiệp vụ. Khi profiler cho thấy bottleneck cụ thể, cân nhắc immutable snapshot/atomic reference hoặc primitive khác theo mô hình tải. Một thiết kế dễ chứng minh đúng thường rẻ hơn chi phí sửa lỗi race khó tái hiện.

## 10. Bất biến liên quan nhiều object: lock ordering và transaction boundary

Khi invariant trải qua **hai object độc lập**, đồng bộ trong từng object riêng lẻ không bảo đảm một operation đi qua cả hai là atomic. Ví dụ chuyển tiền giữa account A và B phải:

1. Kiểm tra số dư A có đủ.
2. Trừ A.
3. Cộng B.
4. Cho reader quan sát một trạng thái nhất quán.

Nếu chỉ `synchronized` riêng trên `withdraw` của A và `deposit` của B, thread khác có thể đọc cặp tài khoản giữa hai bước hoặc có thể có update competing. Muốn atomic đối với cả hai, cần một **protocol sở hữu cả hai**.

### 10.1 Cùng một ledger lock

Nếu cùng một ledger quản lý cả A và B, giải pháp đơn giản là một lock ledger:

~~~java
final class TransferLedger {
    private final Object lock = new Object();
    private int accountA = 100;
    private int accountB = 100;

    boolean transferAToB(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        synchronized (lock) {
            if (accountA < amount) {
                return false;
            }
            accountA -= amount;
            accountB += amount;
            return true;
        }
    }

    int total() {
        synchronized (lock) {
            return accountA + accountB;
        }
    }
}
~~~

Đây là **mảnh class minh họa**, không có main. Nếu trạng thái ban đầu tổng 200, mọi lần chuyển hợp lệ giữ tổng 200; reader gọi `total()` theo cùng lock. Mỗi phép chuyển có hiệu lực như một operation đối với state nội bộ ledger.

### 10.2 Nếu phải lấy nhiều lock, cần thứ tự toàn cục

Giả sử thread T1 khóa account A rồi B, còn T2 khóa B rồi A: có thể **deadlock** nếu mỗi thread giữ một lock và chờ lock còn lại. Một quy tắc phổ biến là cấp **ID bất biến và duy nhất** cho account rồi luôn lấy lock theo thứ tự ID tăng, bất kể hướng chuyển tiền.

~~~java
Account first = from.id < to.id ? from : to;
Account second = from.id < to.id ? to : from;

synchronized (first.lock) {
    synchronized (second.lock) {
        // Kiểm tra from.balance và thực hiện cả hai cập nhật.
    }
}
~~~

Đây là **mảnh minh họa**; `Account` có `id` duy nhất, bất biến, `lock` và `balance`, và đoạn này chưa xử lý trường hợp `from == to`, validation hay mã runnable. Để an toàn, mọi operation có thể cùng lấy hai lock phải dùng **cùng thứ tự**, và tất cả đường đọc snapshot hai account cũng tuân thủ protocol. Nếu ID có thể trùng, cần tie-breaker nhất quán; không dựa vào thứ tự tham số truyền vào.

Không nên khóa object công khai có thể bị code khác `synchronized` tùy ý; private lock giúp tránh can thiệp ngoài mong muốn. Tránh thực hiện I/O hoặc gọi callback không kiểm soát được trong khi giữ nhiều lock.

### 10.3 Một JVM không thay thế giao dịch qua nhiều hệ thống

`synchronized`, `ReentrantLock` và `AtomicReference` chỉ phối hợp trạng thái trong **một JVM/object graph được chúng quản lý**. Nếu invariant gồm hàng trong database, message broker, file, nhiều process hoặc dịch vụ mạng, lock JVM **không** biến toàn bộ thao tác thành distributed transaction.

Các invariant liên hệ nhiều hệ thống cần cơ chế phù hợp cấp đó: transaction database, optimistic concurrency/versioning, idempotency, quy trình compensating action hoặc thiết kế eventual consistency có trạng thái trung gian được định nghĩa rõ. Đây là **giới hạn phạm vi** của kỹ thuật thread safety, không phải lý do đưa framework cụ thể vào bài này.

## 11. Exception safety: không publish trạng thái dở dang

Khóa giúp ngăn thread khác xen vào giữa các phép cập nhật, nhưng **không tự rollback** nếu mã bên trong critical section ném exception giữa chừng.

Ví dụ nguy hiểm:

~~~java
synchronized (lock) {
    available--;
    mayThrow();     // Nếu lỗi ở đây...
    reserved++;     // ... không bao giờ được thực thi.
}
~~~

Mảnh minh họa giả định biến và method đã khai báo. `synchronized` vẫn **nhả monitor** khi exception thoát, khiến thread khác có thể đọc một state đã lệch invariant.

Các hướng xử lý:

- **Validate trước khi mutate:** kiểm tra tham số, giới hạn số học, precondition trước cập nhật. Kiểm tra phụ thuộc state phải đặt trong lock hoặc trong CAS computation dựa trên snapshot.
- **Prepare then commit:** tính toán state mới trong biến local/value object, kiểm chứng invariant trước khi công bố. Dùng assignment một immutable reference hoặc CAS để commit.
- **Rollback trong lock khi thực sự cần:** nếu operation nhiều bước có thể lỗi, viết cleanup/rollback được kiểm chứng; đừng mặc định `finally` nhả lock nghĩa rollback đã xảy ra.
- **Không đặt side effect không thể đảo ngược** (gửi email, phát thông báo, thực hiện remote payment) giữa nhiều bước cập nhật state trong một CAS loop hoặc critical section rồi giả định có thể retry an toàn.
- **Định nghĩa cancellation:** thread bị interrupt giữa một operation phải rời đi ở điểm an toàn, hoặc hoàn thành/rollback đúng protocol. Không nuốt `InterruptedException` rồi bỏ state nửa chừng.

Ví dụ prepare-then-commit đơn giản:

~~~java
synchronized (lock) {
    if (available <= 0) {
        return false;
    }
    int nextAvailable = available - 1;
    int nextReserved = Math.addExact(reserved, 1);
    // Toàn bộ tính toán/validation hoàn tất trước khi sửa state.
    available = nextAvailable;
    reserved = nextReserved;
    return true;
}
~~~

Đây là mảnh minh họa bên trong method trả `boolean`. `Math.addExact` ném `ArithmeticException` khi overflow; vì exception xảy ra **trước** những assignment, state cũ được giữ. Khi đã bắt đầu commit, đảm bảo chỉ còn các phép gán primitive không ném exception và không có callback ngoài được gọi giữa chừng. Do lock bảo vệ reader, state dở dang nội bộ giữa hai phép gán không bị lộ ra ngoài.

Nếu có nhiều phép toán phức tạp hoặc object mutable liên quan, dùng **một immutable candidate state** để commit qua reference thường dễ kiểm tra exception safety hơn.

## 12. Integer overflow và miền hợp lệ của invariant

Khi điều kiện `a + b == total` dùng số nguyên Java, phải xét **overflow**. Với `int`, cộng hai số gần `Integer.MAX_VALUE` có thể wrap qua giá trị âm. Một invariant kiểm tra bằng `a+b` thông thường đôi khi đánh giá sai do overflow.

Các giải pháp:

- Xác định miền hợp lệ và biên dữ liệu rõ ràng.
- Dùng `Math.addExact` / `Math.subtractExact` khi muốn overflow gây exception.
- Chọn `long` nếu miền dữ liệu lớn; `long` cũng có giới hạn và có thể overflow.
- Trong bài toán tiền tệ, dùng đơn vị nhỏ nhất với `long` có miền kiểm tra, hoặc kiểu số thích hợp khi cần độ chính xác thập phân; không dùng `double` để đại diện tiền chính xác.
- Kiểm tra amount dương, không vượt hạn mức, cùng currency/đơn vị và mọi điều kiện business **trước khi commit**.

Lưu ý rằng thread safety và tính đúng của số học là hai chiều khác nhau. Một operation được đồng bộ hoàn hảo nhưng cho phép overflow vẫn có thể phá invariant.

## 13. Tránh deadlock, starvation và lock contention

Để giữ invariant, có thể cần khóa; nhưng một giao thức lock sai có thể khiến ứng dụng không hoàn tất:

- **Lock ordering:** lấy nhiều lock theo thứ tự toàn cục để giảm nguy cơ vòng chờ.
- **Lock scope:** chỉ giữ lock khi đọc/ghi shared state thật cần atomic; không giữ qua I/O không có timeout, callback người dùng hoặc chờ `Future.get()` dài.
- **No blocking self-dependency:** đừng gọi `Thread.join()` trong khi giữ lock mà worker cần để kết thúc.
- **Fairness:** fair lock có thể đổi cách phục vụ contender nhưng không tự bảo đảm tail latency hay hạn định thời gian của task.
- **Contention:** một lock duy nhất có thể thành điểm nghẽn khi rất nhiều thread cùng cập nhật. Trước khi tách lock, phải kiểm tra invariant còn nằm gọn trong từng phần không.
- **Deadlock detection:** thread dump và `ThreadMXBean` có thể hỗ trợ tìm deadlock; không phát hiện được không có nghĩa chương trình không có starvation, livelock hoặc chờ I/O.

Đặc biệt, **tách một lock thành hai lock riêng cho hai field** để tăng throughput có thể làm mất chính invariant đang bảo vệ. Khi một invariant buộc cập nhật nhiều field cùng lúc, sharding cần tái thiết kế ranh giới state chứ không chỉ đổi tên lock.

## 14. Đọc snapshot nhất quán và Linearizability

Trong một concurrent API, một snapshot nên đại diện **một trạng thái có thể tồn tại tại một thời điểm hợp lệ**. Nếu API cần *linearizability*, mỗi operation đã hoàn tất phải có thể được xem như có hiệu lực tại một điểm nằm giữa khi được gọi và khi trả về, đồng thời giữ thứ tự thực tế của các lời gọi không chồng lấn.

- Với `synchronized`, update và snapshot cùng lấy một lock nên có thể giải thích operation/snapshot trong thứ tự lock.
- Với `AtomicReference<State>`, CAS thành công là điểm tuyến tính hóa của update, còn một lần `get()` là điểm quan sát snapshot.
- Với hai getter riêng biệt, dù mỗi getter synchronized, cặp kết quả caller ghép có thể lấy từ **hai thời điểm khác nhau**.

Ví dụ lỗi:

~~~java
int available = ledger.getAvailable();  // Một lần khóa rồi mở.
int reserved = ledger.getReserved();    // Lần khóa khác.
int total = available + reserved;       // Có thể ghép hai version.
~~~

Hai getter tự bảo vệ từng biến chưa đủ cho **snapshot của cả nhóm**. API nên trả một `record Snapshot(int available, int reserved)` duy nhất dưới một lần lock, hoặc một immutable state được lấy từ một reference atomic.

### 14.1 Snapshot consistency khác metric eventually consistent

Không phải mọi cặp counter đều cần snapshot linearizable. Với telemetry/metrics, đọc hai bộ đếm độc lập hơi lệch tại thời điểm cập nhật có thể **được chấp nhận theo hợp đồng**. Trong kế toán số dư hoặc cấp phát quota, điều đó thường không được phép.

Trước khi tăng chi phí synchronization, đặt câu hỏi: “Có người dùng/operation nào dựa vào tổng này để đưa ra quyết định phải đúng ngay không?” Nếu có, bảo đảm atomic snapshot. Nếu chỉ là dashboard gần đúng, cần ghi rõ consistency model được phép.

## 15. Kiểm thử invariant đa trường có ý nghĩa

Test concurrency có giá trị khi nó kiểm tra **điều kiện nghiệp vụ** dưới các interleaving có chủ đích.

### 15.1 Kiểm tra sau cạnh tranh

Với ledger có 100 phiếu và 2 thread mỗi thread gọi `reserveOne()` 100 lần, sau `join()` cần assert:

~~~text
available >= 0
reserved >= 0
available + reserved == 100
reserved == 100
~~~

Cả hai ví dụ `LockedInvariantDemo` và `AtomicInvariantDemo` cho kết quả xác định này, bất kể thứ tự lịch chạy. Nếu chỉ assert “không có exception”, test sẽ bỏ sót oversubscription và lost update.

### 15.2 Kiểm tra trong khi writer hoạt động

Một lỗi phổ biến là chỉ kiểm tra state cuối. Nếu writer thực hiện `available--` rồi `reserved++` và reader lấy snapshot giữa chừng, kết quả cuối vẫn bằng 100 nhưng invariant của **mọi snapshot quan sát được** đã bị phá.

Dùng `CountDownLatch` hoặc barrier để buộc reader chạy đúng thời điểm nhạy cảm, giống `VolatilePairInvariantDemo`. Test đối với thiết kế đã sửa phải dùng **public snapshot API** và xác nhận reader không bao giờ nhận tổng 99. Test phải có cơ chế mở latch/giải phóng worker trong `finally` để không làm tiến trình test kẹt.

### 15.3 Kiểm tra exception và cancellation

Cần gây lỗi tại các bước có khả năng throw: validation, chuẩn bị candidate state, callback ngoài hoặc lúc chờ lock. Kết quả hợp lệ phải là:

- operation thành công và **toàn bộ state** được commit;
- hoặc operation thất bại và state vẫn nhất quán theo chính sách đã định.

Đừng chỉ assert exception được ném; hãy assert invariant **sau exception**, sau cancellation và sau timeout.

### 15.4 Kiểm tra interleaving và quan sát runtime

Chạy nhiều thread, tăng tranh chấp và lặp lại stress test; quan sát throughput, p95/p99 latency, queue depth và contention khi tải thực. Công cụ **jcstress** của OpenJDK có thể giúp xây dựng những thử nghiệm concurrency nhỏ và phân loại outcome cho phép/cấm.

Nhưng test pass không chứng minh không có race. Code review phải vẽ đúng những access và quan hệ happens-before; test là chứng cứ bổ trợ chứ không thay chứng minh về giao thức.

## 16. Những lỗi phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Mỗi field dùng `volatile` rồi update lần lượt. | Visibility không nhóm nhiều lần ghi thành một transaction. | Một lock chung hoặc immutable aggregate state. |
| Mỗi field dùng một `AtomicInteger`. | Atomic ở cấp biến, không ở cấp invariant đa trường. | AtomicReference của một state, hoặc lock toàn operation. |
| Chỉ synchronized setter, getter không lock. | Reader có thể thấy trạng thái trung gian và thiếu HB. | Đọc snapshot dưới cùng protocol. |
| Hai getter synchronized riêng rồi ghép kết quả. | Update có thể diễn ra giữa hai getter; snapshot bị trộn version. | Một getter snapshot trả cả nhóm. |
| Trả mutable collection từ getter có lock. | Caller sửa collection sau khi lock đã nhả. | Immutable/deep snapshot hoặc API cập nhật do owner quản lý. |
| Lấy hai lock theo thứ tự tham số truyền vào. | Hai thread truyền A,B và B,A có thể deadlock. | Thứ tự khóa toàn cục, tie-breaker khi cần. |
| Cho exception xảy ra giữa hai assignment rồi tự động nhả lock. | Nhả lock không rollback state dở dang. | Validate/prepare trước, commit an toàn, rollback khi cần. |
| Tính `int a+b` mà không xét overflow. | Wrap-around có thể phá invariant dù synchronization đúng. | Giới hạn miền hoặc số học checked. |
| Đưa side effect không idempotent trong vòng CAS. | CAS thất bại gây retry và side effect có thể lặp. | Tách chuẩn bị state và side effect; thiết kế idempotency. |
| Lock JVM để đồng bộ database/nhiều service. | Lock chỉ bảo vệ state và participants trong JVM. | Transaction/versioning/idempotency ở đúng cấp hệ thống. |
| Chỉ test state cuối cùng. | Có thể bỏ sót snapshot trung gian bị lệch. | Test cả snapshot khi đang cập nhật, dùng latch/barrier. |

## 17. Checklist thiết kế một object thread-safe nhiều trường

Trước khi công bố object cho nhiều thread, tự trả lời:

1. **Invariant:** các công thức/quan hệ nào giữa các field phải đúng tại ranh giới public?
2. **Ownership:** object/class nào sở hữu cả nhóm state và quyền sửa?
3. **Writers:** mọi phương thức và thread có thể thay state là gì? Có đường truy cập không qua protocol không?
4. **Readers:** reader có thể lấy một snapshot nhất quán không, hay ghép nhiều getter?
5. **Atomic boundary:** check, validate và tất cả assignment đã nằm chung một critical section/CAS candidate chưa?
6. **HB:** phép ghi công bố và lần đọc sau đó có quan hệ happens-before hợp lệ không?
7. **Failure:** exception, overflow, interruption, timeout và early return có giữ invariant không?
8. **Multiple objects:** có cần lock ordering, một ledger owner hoặc transaction cấp cao hơn không?
9. **Performance:** lock contention hoặc CAS retry có thực sự là bottleneck qua đo đạc không?
10. **Evidence:** có test cạnh tranh, test snapshot trung gian, test lỗi và review invariant không?

### Câu hỏi tự kiểm tra

**1.** Hai trường `available` và `reserved` đều volatile. Writer giảm available rồi tăng reserved. Reader có thể thấy tổng sai tạm thời không?  
**Có.** Hai volatile writes là hai hành động riêng, không thành một atomic transition.

**2.** Vì sao khóa mỗi phép setter riêng nhưng ghép hai getter vẫn sai?  
**Vì** một writer có thể cập nhật giữa hai lần getter. Muốn một snapshot, phải đọc cả hai dưới một critical section hoặc cùng immutable state.

**3.** Cùng một lock trong `reserveOne()` và `snapshot()` giải quyết hai vấn đề nào?  
**Mutual exclusion** cho cập nhật nguyên tử ở ranh giới method, và **happens-before** qua unlock→lock cho visibility.

**4.** Dùng hai `AtomicInteger`, mỗi thao tác atomically đúng, có bảo toàn invariant `a+b=100` tại mọi snapshot không?  
**Không.** Atomic ở cấp từng field; tổng là invariant liên biến.

**5.** Khi nào `AtomicReference<State>` phù hợp?  
Khi toàn bộ state có thể biểu diễn bằng snapshot immutable, mỗi update tạo candidate và công bố bằng một CAS; cần chấp nhận chi phí allocation/retry và tránh side effect trong vòng CAS.

**6.** Vì sao `finally { lock.unlock(); }` chưa đủ để xử lý exception safety?  
Nó nhả lock nhưng không tự hoàn tác phép ghi đã xảy ra trước exception. State dở dang có thể trở nên quan sát được sau khi unlock.

**7.** Hai account có lock riêng: thread A lấy lock 1→2, thread B lấy 2→1. Rủi ro gì?  
**Deadlock.** Dùng thứ tự lấy lock toàn cục hoặc một owner lock cho invariant.

**8.** Khi chuyển tiền giữa hai database ở hai process, `synchronized` trên một service có bảo đảm tổng tiền không đổi không?  
**Không.** Cần giao thức dữ liệu/transaction ở cấp hệ thống, vì monitor của một JVM không bao phủ các process khác.

**9.** Vì sao test chỉ kiểm tra số dư cuối có thể bỏ sót lỗi?  
Vì state tạm thời có thể bị lộ không nhất quán nhưng được phục hồi trước thời điểm test đọc. Phải kiểm tra snapshot trong lúc operation đang diễn ra.

**10.** Chọn phương pháp ban đầu nào cho invariant đa trường trong một object?  
Thường dùng **private lock và API nghiệp vụ** vì dễ chứng minh đúng. Chuyển sang immutable snapshot/CAS hoặc lock chuyên biệt khi có yêu cầu và bằng chứng hiệu năng.

**Ghi nhớ:** Giữ invariant đa trường là bài toán **thiết kế chuyển trạng thái nguyên tử và quan sát snapshot nhất quán**. Mọi writer và reader phải tuân thủ cùng ranh giới ownership và đồng bộ; `volatile` hay atomic trên từng field không thay thế được giao thức bảo vệ **toàn bộ quan hệ giữa chúng**.