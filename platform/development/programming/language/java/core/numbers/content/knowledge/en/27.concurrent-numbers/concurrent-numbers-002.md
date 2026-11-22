# volatile không làm phép tăng trở thành nguyên tử

## 1. Tình huống: hai luồng cùng tăng một biến đếm

Một ứng dụng Java có nhiều luồng cùng ghi nhận sự kiện. Ta dùng một biến đếm:

~~~java
class Counter {
    volatile int value = 0;

    void increment() {
        value++;
    }
}
~~~

Nhiều người cho rằng thêm `volatile` khiến mọi luồng “luôn thấy giá trị mới nhất”, nên hai luồng mỗi luồng gọi `increment()` một lần thì chắc chắn `value == 2`. Kết luận đó **sai**.

`volatile` giải quyết các vấn đề nhất định về **khả năng nhìn thấy thay đổi giữa các luồng (visibility)** và **thứ tự bộ nhớ (ordering)** theo Java Memory Model. Nó **không biến một chuỗi đọc – tính toán – ghi thành một thao tác nguyên tử (atomic read-modify-write)**.

Nếu hai luồng cùng đọc `value == 0` trước khi luồng nào ghi lại, cả hai đều có thể tính ra `1` rồi cùng ghi `1`. Sau hai lần “tăng”, kết quả vẫn là `1`: một lần cập nhật đã bị mất (**lost update**).

Bài học này tập trung vào cách phân biệt visibility và atomicity, nhận ra lỗi trong `++`/`+=`, tái hiện lỗi có kiểm soát, chọn `AtomicInteger`, `synchronized` hoặc `Lock`, và kiểm thử đúng hợp đồng đồng thời.

## 2. volatile thực sự bảo đảm điều gì?

Trong Java, một trường được khai báo:

~~~java
private volatile int count;
~~~

có các đặc tính quan trọng:

1. **Visibility:** các thao tác đọc/ghi `volatile` tuân theo quan hệ đồng bộ của Java Memory Model. Một lần ghi volatile *happens-before* các lần đọc tiếp theo của **cùng biến volatile** trong thứ tự đồng bộ. Nhờ đó, thông tin được công bố đúng cách có thể được nhìn thấy bởi luồng đọc.
2. **Ordering:** thao tác volatile thiết lập những ràng buộc sắp xếp cần thiết đối với các thao tác bộ nhớ liên quan. Ví dụ, khi một luồng ghi dữ liệu thông thường rồi ghi một cờ volatile, luồng khác đọc được giá trị cờ đã công bố có thể nhìn thấy những ghi dữ liệu trước đó theo quan hệ happens-before.
3. **Từng lần truy cập volatile là một thao tác đọc hoặc ghi với ngữ nghĩa đồng bộ:** truy cập riêng lẻ tới một biến `volatile int`/`volatile long` không bị “xé” thành hai nửa. Nhưng **toàn bộ biểu thức `count++`** vẫn có nhiều bước.

Cụm “luôn thấy giá trị mới nhất” chỉ là cách nói trực giác, dễ gây hiểu lầm. Một luồng đọc tại một thời điểm vẫn có thể đọc giá trị trước khi luồng khác thực hiện lần ghi kế tiếp. `volatile` **không bắt các luồng chờ nhau** và không đảm bảo rằng giá trị đọc sẽ không đổi trước khi luồng đọc ghi ngược trở lại.

### Happens-before không đồng nghĩa atomic transaction

Giả sử luồng A ghi `data = 42` rồi `ready = true` (trường `ready` khai báo volatile). Luồng B đọc `ready == true` theo đúng giao thức công bố, rồi đọc `data`: các ghi trước lần công bố volatile của A được đặt trước các thao tác sau lần đọc tương ứng của B theo quan hệ happens-before.

Điều này rất hữu ích cho **cờ trạng thái** hoặc **công bố trạng thái đã hoàn tất**. Nhưng nếu hai luồng cùng viết `data = data + 1`, thì điều kiện cập nhật dựa trên giá trị cũ cần **atomicity** riêng. Cờ volatile không tự bảo vệ phép tính đó.

| Nhu cầu | volatile đơn thuần đáp ứng? | Vì sao |
|---|---|---|
| Một luồng ghi cờ dừng, luồng khác đọc cờ | Có thể phù hợp | Giao thức một cờ đơn giản, đọc/ghi độc lập |
| Nhiều luồng cùng gọi `counter++`, không mất cập nhật | **Không** | Đọc và ghi tách rời, có thể xen kẽ |
| Ghi một tham chiếu tới cấu hình bất biến đã xây dựng xong | Có thể phù hợp | Công bố tham chiếu qua volatile tạo quan hệ visibility |
| Nhiều luồng cập nhật từng trường của đối tượng do tham chiếu volatile trỏ tới | **Không tự động** | volatile trên tham chiếu không khóa các trường bên trong |
| Chuyển tiền: kiểm tra số dư rồi trừ tiền như một hành động | **Không** | Điều kiện và thay đổi phải cùng được bảo vệ |
| Đọc snapshot nhất quán của nhiều biến | **Không tự động** | Từng lần đọc độc lập có thể thuộc các thời điểm khác nhau |

## 3. Vì sao count++ là ba bước logic?

Biểu thức:

~~~java
count++;
~~~

về mặt logic thực hiện:

~~~text
1. Đọc giá trị hiện tại của count.
2. Tính giá trị mới = giá trị đã đọc + 1.
3. Ghi giá trị mới trở lại count.
~~~

Đây là mô hình logic của biểu thức, **không phải cam kết ba lệnh máy hoặc ba bytecode cố định**. Compiler và JVM có thể tối ưu nhưng vẫn phải tôn trọng Java Memory Model; việc có hai thao tác truy cập volatile trong một read-modify-write không tạo ra một transaction không thể bị xen vào.

Một interleaving hợp lệ:

| Thứ tự | Luồng A | Luồng B | Giá trị lưu trong count |
|---|---|---|---|
| 0 | — | — | 0 |
| 1 | Đọc 0 | — | 0 |
| 2 | — | Đọc 0 | 0 |
| 3 | Tính 1 | — | 0 |
| 4 | — | Tính 1 | 0 |
| 5 | Ghi 1 | — | 1 |
| 6 | — | Ghi 1 | 1 |

Cả hai lần đọc đều hợp lệ, vì tại thời điểm đó chưa có luồng nào ghi 1. Không có vấn đề “không nhìn thấy cập nhật” xảy ra; **cập nhật bị mất do hai lần tính độc lập cùng dựa trên trạng thái cũ**.

Những biểu thức sau cũng là thao tác ghép và **không trở thành atomic chỉ nhờ volatile**:

~~~java
counter = counter + 1;
counter += 1;
counter++;
++counter;
if (counter == 0) {
    counter = 1;
}
~~~

Đoạn trên chỉ minh họa các cách cập nhật trên biến `counter` có thể được khai báo trong phương thức/lớp; những biểu thức này không tự bảo vệ toàn bộ quan hệ đọc–kiểm tra–ghi. Với phép gán có điều kiện, hai luồng có thể cùng thấy 0 và cùng gán 1. Nếu phép tính phụ thuộc trạng thái hiện tại, hãy xem nó là một thao tác cần phân tích tính nguyên tử.

## 4. Chương trình Java 17+ tái hiện lost update có kiểm soát

Các bài thử đơn giản tạo 100 luồng rồi gọi `counter++` nhiều lần **có thể** tình cờ ra kết quả đúng, bởi lịch chạy luồng không được bảo đảm. Để chứng minh vấn đề mà không phụ thuộc vào may rủi, ví dụ sau dùng hai latch:

- Cả hai luồng **phải đọc giá trị cũ** rồi mới báo đã đọc.
- Chỉ khi cả hai đã đọc xong, luồng chính mới cho phép hai luồng ghi.
- Mỗi luồng ghi đúng `snapshot + 1`, nên hai lần tăng dựa trên cùng `snapshot == 0` và chỉ còn 1.
- Phần đối chiếu dùng thao tác `AtomicInteger.incrementAndGet()` cho kết quả 2.

Lưu trong **`VolatileLostUpdateDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class VolatileLostUpdateDemo {
    static final class VolatileCounter {
        volatile int value;
    }

    public static void main(String[] args) throws InterruptedException {
        VolatileCounter counter = new VolatileCounter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch releaseWrites = new CountDownLatch(1);

        Runnable nonAtomicIncrement = () -> {
            int snapshot = counter.value;
            bothRead.countDown();
            try {
                releaseWrites.await();
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                return;
            }
            counter.value = snapshot + 1;
        };

        Thread first = new Thread(nonAtomicIncrement);
        Thread second = new Thread(nonAtomicIncrement);
        first.start();
        second.start();
        bothRead.await();
        releaseWrites.countDown();
        first.join();
        second.join();

        System.out.println("volatile count = " + counter.value);

        AtomicInteger atomicCounter = new AtomicInteger();
        Thread third = new Thread(atomicCounter::incrementAndGet);
        Thread fourth = new Thread(atomicCounter::incrementAndGet);
        third.start();
        fourth.start();
        third.join();
        fourth.join();

        System.out.println("atomic count   = " + atomicCounter.get());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac VolatileLostUpdateDemo.java
java VolatileLostUpdateDemo
~~~

Kết quả chính xác:

~~~text
volatile count = 1
atomic count   = 2
~~~

Lưu ý: hai latch không phải thủ thuật để “làm cho volatile hỏng”; chúng chỉ ép một **interleaving hợp lệ** mà chương trình concurrent thực sự có thể gặp. `bothRead.await()` bảo đảm cả hai lần đọc đã diễn ra; `releaseWrites.countDown()` cho phép hai lần ghi tiếp tục. Không có lần ghi nào trước khi cả hai đã đọc, nên cả hai giữ `snapshot == 0`. Từng write vẫn là write volatile hợp lệ, nhưng không có cơ chế giải quyết lost update.

Khi dùng `AtomicInteger.incrementAndGet()`, mỗi lần tăng là một read-modify-write nguyên tử; hai lần tăng thành công từ 0 cho kết quả 2. `join()` chờ luồng hoàn thành và bảo đảm luồng chính đọc kết quả sau khi các thao tác trong luồng đã kết thúc theo quan hệ happens-before.

**Không dùng `Thread.sleep()` để khẳng định tái hiện race condition.** Sleep chỉ gợi ý thời gian, không ép thứ tự xảy ra. Cũng không kết luận `volatile++` an toàn vì một lần chạy 1 triệu phép tăng tình cờ cho đúng tổng.

## 5. Phân biệt visibility, atomicity và mutual exclusion

Ba khái niệm liên quan nhưng không thay thế được nhau:

- **Visibility:** một luồng nhìn thấy thông tin được luồng khác công bố đúng quan hệ bộ nhớ. `volatile`, monitor lock, các lớp atomic và nhiều primitive đồng bộ giúp thiết lập visibility.
- **Atomicity:** một hành động quan sát/cập nhật cần diễn ra như một đơn vị không bị xen giữa tại mức trừu tượng đang xét. `AtomicInteger.incrementAndGet()` bảo đảm cho **một biến atomic**; `synchronized` có thể bảo vệ một vùng logic lớn hơn.
- **Mutual exclusion:** tại một thời điểm chỉ một luồng giữ lock cần thiết để thực hiện vùng thao tác. `synchronized` hoặc `ReentrantLock` có thể bảo vệ cả chuỗi check-then-act trên nhiều biến nếu **mọi đường đọc/ghi liên quan tuân theo cùng lock**.

`volatile` cung cấp những quan hệ memory-order cần thiết nhưng **không cấp khóa**. `AtomicInteger` thực hiện một số thao tác nguyên tử trên một trạng thái, thường không cần monitor; tuy vậy **nhiều thao tác atomic nối nhau vẫn chưa chắc tạo thành một transaction**. Ví dụ `balance.get() >= amount` rồi `balance.addAndGet(-amount)` có thể bị luồng khác xen vào nếu logic yêu cầu thao tác kiểm tra và trừ phải đi cùng nhau.

## 6. Giải pháp khi cần tăng số đếm không mất cập nhật

### 6.1. AtomicInteger và AtomicLong

Khi nhiều luồng cập nhật **một bộ đếm nguyên** độc lập, chọn `AtomicInteger` (int) hoặc `AtomicLong` (long):

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger(0);
int after = counter.incrementAndGet();  // tăng nguyên tử, trả giá trị mới
int before = counter.getAndIncrement(); // tăng nguyên tử, trả giá trị trước tăng
int current = counter.get();           // đọc trạng thái atomic
~~~

Đây là đoạn minh họa đặt trong phương thức. Lưu ý hai hàm trả giá trị khác nhau, dù cả hai đều tăng đúng một đơn vị:

| Thao tác trên counter = 5 | Giá trị trả về | Giá trị lưu sau thao tác |
|---|---:|---:|
| `incrementAndGet()` | 6 | 6 |
| `getAndIncrement()` | 5 | 6 |
| `addAndGet(3)` | 8 | 8 |
| `getAndAdd(3)` | 5 | 8 |

Bảng xét từng thao tác **độc lập**, bắt đầu từ cùng giá trị 5. Những lần tăng này dùng thao tác nguyên tử (trong triển khai thường thông qua CAS hoặc intrinsic phù hợp), không chỉ thêm từ khóa volatile vào một `int`.

Nếu đếm dài hạn có thể vượt giới hạn `int`, dùng `AtomicLong`, nhưng kiểu `long` cũng hữu hạn. `AtomicInteger.incrementAndGet()` **vẫn có thể overflow và wrap** tại `Integer.MAX_VALUE`; nó chỉ bảo đảm atomicity, không tự kiểm tra điều kiện toán học. Nếu phải từ chối overflow, có thể dùng:

~~~java
counter.updateAndGet(Math::incrementExact);
~~~

`updateAndGet` áp dụng hàm tới giá trị trước đó và thử cập nhật nguyên tử; hàm có thể được JVM gọi lại khi cạnh tranh, nên phải **thuần (side-effect-free)**. `Math.incrementExact` ném `ArithmeticException` nếu cộng 1 vượt giới hạn int; không sinh side effect ngoài phép tính.

### 6.2. synchronized cho chuỗi thao tác

Khi muốn toàn bộ read-modify-write đi cùng nhau, một monitor bảo vệ cả phép tăng:

~~~java
public final class SynchronizedCounter {
    private int value;

    public synchronized void increment() {
        value++;
    }

    public synchronized int get() {
        return value;
    }
}
~~~

Đây là lớp có thể biên dịch độc lập trong file `SynchronizedCounter.java`, nhưng không có `main`. Hai phương thức `synchronized` instance sử dụng cùng monitor của **một instance**. Nếu mọi truy cập đến `value` đều thông qua các phương thức đồng bộ đúng quy tắc, `volatile` trên `value` là **không cần thiết**: monitor cung cấp cả mutual exclusion và quan hệ visibility.

Nếu viết `synchronized void increment()` nhưng ở chỗ khác vẫn trực tiếp đọc/ghi `value` mà không cùng lock, thiết kế có thể còn race hoặc thiếu visibility. Cần kiểm soát mọi đường truy cập, không chỉ một method.

### 6.3. ReentrantLock khi cần điều khiển lock tường minh

~~~java
import java.util.concurrent.locks.ReentrantLock;

public final class LockedCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int value;

    public void increment() {
        lock.lock();
        try {
            value++;
        } finally {
            lock.unlock();
        }
    }

    public int get() {
        lock.lock();
        try {
            return value;
        } finally {
            lock.unlock();
        }
    }
}
~~~

Lưu thành `LockedCounter.java` nếu muốn biên dịch lớp này riêng. Mẫu `try/finally` là cần thiết để luôn unlock khi phép tính ném exception. Mọi đường truy cập state phải dùng **cùng lock**. `ReentrantLock` hữu ích khi cần `tryLock`, timeout, interruptible locking hoặc `Condition`; đừng tự tăng độ phức tạp nếu `synchronized` đã đủ.

### 6.4. LongAdder cho bộ đếm thống kê tranh chấp cao

`LongAdder` thường có throughput tốt cho nhiều luồng cùng cộng vào **metric/counter**:

~~~java
import java.util.concurrent.atomic.LongAdder;

LongAdder requests = new LongAdder();
requests.increment();
requests.add(4L);
long observed = requests.sum();
~~~

Mã trên là ví dụ đặt trong một method. `sum()` có thể không phải **snapshot nguyên tử** khi các luồng khác vẫn cập nhật; một phép `sum` đồng thời với nhiều phép tăng không phù hợp nếu bạn cần số thứ tự duy nhất, giới hạn quota cứng hoặc quyết định phải chính xác tại một thời điểm. Nếu cần giá trị nguyên tử của một bộ đếm, ưu tiên `AtomicLong`; nếu cần nhất quán nhiều điều kiện, chọn cơ chế đồng bộ logic phù hợp.

## 7. CAS là gì? Vì sao compareAndSet hữu ích?

**Compare-and-set (CAS)** diễn đạt yêu cầu: “chỉ cập nhật thành giá trị mới nếu giá trị hiện tại vẫn là giá trị mình mong đợi”. Với `AtomicInteger`:

~~~java
AtomicInteger state = new AtomicInteger(0);

boolean success1 = state.compareAndSet(0, 1); // true
boolean success2 = state.compareAndSet(0, 2); // false
System.out.println(state.get());              // 1
~~~

Đoạn này nằm trong method có import `java.util.concurrent.atomic.AtomicInteger`. Lần thứ nhất thấy 0 và đặt thành 1 nguyên tử. Lần thứ hai kỳ vọng 0 nhưng trạng thái đã là 1, nên thất bại mà không ghi. CAS không thể bỏ qua bước xác minh trạng thái nếu yêu cầu là update điều kiện.

Vòng lặp CAS thường có dạng:

~~~java
int observed;
int updated;
do {
    observed = state.get();
    updated = Math.incrementExact(observed);
} while (!state.compareAndSet(observed, updated));
~~~

Giả sử `state` là `AtomicInteger` đã được khởi tạo. Nếu luồng khác cập nhật giữa `get` và `compareAndSet`, CAS thất bại, vòng lặp đọc lại và tính lại. Không phải phép cộng tự nhiên đã atomic: **thao tác commit có điều kiện** mới giúp ngăn mất cập nhật.

Có thể dùng `incrementAndGet` thay vòng lặp trên khi không cần chính sách riêng; triển khai của lớp atomic đã cung cấp thao tác phù hợp. Vòng lặp CAS có thể lặp nhiều lần khi tranh chấp cao, nên tránh gọi API có side effect, gửi email, ghi log nghiệp vụ hoặc trừ số dư ngoài hệ thống từ bên trong hàm có thể bị tính lại.

**Chú ý phạm vi:** CAS của một `AtomicInteger` chỉ cập nhật nguyên tử một giá trị đó. Nếu cần đồng bộ số dư và một lịch sử giao dịch, phải có cơ chế phối hợp toàn bộ state; CAS một bộ đếm không tự trở thành database transaction.

## 8. Khi nào volatile một mình là hợp lý?

`volatile` vẫn quan trọng và hữu dụng. Ví dụ một luồng phụ thực hiện công việc theo cờ dừng được điều khiển bởi luồng khác:

~~~java
public final class StopFlag {
    private volatile boolean stopped;

    public void requestStop() {
        stopped = true;
    }

    public boolean shouldStop() {
        return stopped;
    }
}
~~~

Đây là lớp có thể biên dịch trong `StopFlag.java`. Với mô hình **một cờ điều khiển đơn giản**, ghi `true` và đọc cờ là các truy cập độc lập; không có việc nhiều writer cần phối hợp cộng dồn. Luồng thực hiện công việc phải kiểm tra `shouldStop()` theo chu kỳ và biết cách kết thúc. Trong tác vụ có blocking I/O/sleep/wait, `Thread.interrupt()` hoặc cơ chế hủy cấp cao có thể cần thiết; một cờ không tự đánh thức luồng đang chờ.

Một trường hợp khác là **công bố tham chiếu cấu hình bất biến**: tạo đầy đủ đối tượng immutable rồi ghi tham chiếu vào trường volatile; các reader đọc tham chiếu đó có thể thấy trạng thái đã được công bố. Tuy nhiên, nếu bên trong đối tượng có `ArrayList` mutable và các luồng thay đổi danh sách mà không đồng bộ, `volatile` trên tham chiếu không bảo vệ những lần thay đổi đó.

### volatile trên tham chiếu, mảng, wrapper và số 64 bit

- `volatile int[] numbers` làm lần đọc/ghi **tham chiếu mảng** có ngữ nghĩa volatile; nó **không khiến `numbers[0]++` atomic**. Khi cần atomic cho từng phần tử, xem `AtomicIntegerArray` hoặc lock.
- `volatile Integer count` cũng không biến `count++` thành atomic; mỗi lần tăng còn có unboxing/boxing và thay tham chiếu. Nếu giá trị có thể null, unboxing còn có thể ném `NullPointerException`.
- `volatile long value` bảo đảm một lần đọc/ghi biến long là atomic theo Java Memory Model; nhưng `value++` vẫn không atomic. Đừng nhầm atomic access tới 64 bit với atomic read-modify-write.
- `volatile` không bảo đảm thứ tự xử lý logic trên **nhiều biến**. Hai field volatile riêng không tạo ra snapshot nhất quán nếu writer cập nhật chúng từng bước.

## 9. Check-then-act và nhiều biến: lỗi khó hơn counter++

Lỗi mất cập nhật chỉ là ví dụ đơn giản. Xét một quy tắc nghiệp vụ:

~~~java
if (availableSeats > 0) {
    availableSeats--;
    reserveSeat();
}
~~~

Đây là pseudocode Java nằm trong method có các biến/phương thức tương ứng. Ngay cả khi `availableSeats` là volatile, **hai luồng có thể cùng thấy 1, cùng đi vào nhánh, và cùng gọi `reserveSeat()`**. Kết quả có thể là hai lượt đặt chỗ dù chỉ còn một ghế. `availableSeats--` bị race, và gọi `reserveSeat()` còn là side effect cần bảo vệ.

Nếu chỉ cần giảm một biến nguyên với điều kiện lớn hơn 0, có thể viết một vòng CAS để đọc điều kiện và cập nhật cùng nhau. Nhưng nếu `reserveSeat()` cần lưu dữ liệu qua DB, gọi dịch vụ ngoài hoặc phối hợp nhiều biến, còn cần transaction/lock/idempotency thích hợp ở đúng hệ thống giữ state. Một `AtomicInteger` trong JVM **không bảo vệ dữ liệu trên nhiều tiến trình hoặc nhiều instance dịch vụ**.

Tương tự, công thức `if (balance.get() >= withdrawal) balance.addAndGet(-withdrawal)` không phải hành động nguyên tử chỉ vì `balance` là `AtomicInteger`: check và update tách rời. Phải đặt điều kiện và update trong một CAS loop hoặc cùng critical section; khi có nhiều nguồn dữ liệu phải mở rộng giải pháp cho toàn bộ invariant.

## 10. Kiểm thử race condition đúng cách

Đừng dùng sự ngẫu nhiên của thread scheduler làm điều kiện thành công của test. Một chương trình chạy 1.000.000 vòng có thể **không gặp interleaving lỗi trên máy hiện tại**, nhưng không chứng minh an toàn. Lệnh `Thread.sleep(100)` chỉ gây trễ; nó không cung cấp hợp đồng bảo đảm một luồng đã đọc trước khi luồng khác ghi.

Cách kiểm thử hữu ích:

1. **Tái hiện lịch chạy có chủ đích:** như hai `CountDownLatch` trong `VolatileLostUpdateDemo`, ép cả hai đọc cùng trạng thái cũ rồi cùng ghi.
2. **Khẳng định bất biến:** với n luồng, mỗi luồng tăng m lần bằng phương thức atomic/lock đúng, sau `join` giá trị mong đợi là `n × m` nếu không overflow và không lần nào thất bại.
3. **Kiểm thử trạng thái biên:** counter gần `Integer.MAX_VALUE`, giá trị âm, overflow, thao tác reset đồng thời với tăng, lỗi interrupt hoặc exception.
4. **Kiểm thử toàn bộ state:** nếu nghiệp vụ có điều kiện check-then-act hoặc nhiều trường, test phải bao quát điều kiện và hành động, không chỉ tăng số nguyên.
5. **Quan sát và kiểm toán:** đối với tác vụ bất đồng bộ, dùng latch, barrier, executor và timeout hợp lý để tránh test treo; ghi nhận lỗi từ thread con thay vì để thread chết mà test không biết.
6. **Phân biệt kiểm thử chức năng và stress:** stress test hữu ích để tìm lỗi nhưng không thay cho phân tích happens-before và tính nguyên tử của giao thức.

### Ví dụ đối chiếu giá trị mong đợi

Khi dùng `AtomicInteger`:

~~~java
AtomicInteger safe = new AtomicInteger();
safe.incrementAndGet();
safe.incrementAndGet();

if (safe.get() != 2) {
    throw new AssertionError("Lost atomic increments");
}
~~~

Đây là đoạn minh họa đặt trong một method có import `AtomicInteger`. Để kiểm chứng trong đa luồng, cần tạo/đồng bộ thread và chờ tất cả hoàn tất trước assertion, tương tự ví dụ chạy được ở phần 4. `get()` trong lúc các luồng còn chạy cho kết quả tại thời điểm đọc, không tự mang nghĩa “tổng cuối”.

### Không nhầm visibility sau join với tính nguyên tử

Sau khi gọi `thread.join()` thành công, luồng đang chờ có quan hệ happens-before cần thiết với các thao tác luồng vừa kết thúc; nhưng điều đó **không phục hồi cập nhật đã mất** trước khi join. Trong ví dụ hai luồng ghi cùng 1, main thấy 1 chính xác và đầy đủ sau join. Vấn đề nằm ở việc **hai luồng đã thực hiện hai read-modify-write không nguyên tử**, không phải lỗi đọc kết quả cuối.

## 11. Chọn cơ chế theo yêu cầu

| Nhu cầu | Lựa chọn thường phù hợp | Giới hạn cần nhớ |
|---|---|---|
| Một cờ dừng/công bố trạng thái với giao thức đơn giản | `volatile boolean`/tham chiếu volatile | Không đồng bộ side effect phức tạp hoặc nhiều trạng thái |
| Nhiều luồng tăng một số nguyên chính xác | `AtomicInteger`/`AtomicLong` | Có thể overflow; một thao tác atomic không thay transaction |
| Nhiều luồng cộng số metric với mức tranh chấp cao | `LongAdder` | `sum()` không phải snapshot atomic khi có cập nhật |
| Cập nhật điều kiện một trường nguyên | CAS hoặc `updateAndGet` với hàm thuần | Cần xử lý retry và cạnh tranh |
| Cần bảo vệ một chuỗi thao tác hoặc nhiều trường | `synchronized` hoặc `ReentrantLock` | Mọi đường truy cập phải dùng cùng lock |
| Cần nhất quán trạng thái của DB/đa tiến trình | Transaction, lock/atomic update cấp lưu trữ | Bộ nhớ atomic trong một JVM không đủ |

Không có từ khóa nào thay cho việc xác định **đơn vị nguyên tử của bài toán**. Nếu đơn vị đó chỉ là một lần tăng, một thao tác `AtomicInteger` có thể là đủ. Nếu đơn vị là “kiểm tra hạn mức, tạo hóa đơn, trừ hạn mức và ghi lịch sử”, cần giải pháp bảo vệ cả quy trình ở phạm vi chia sẻ state thực tế.

## 12. Lỗi phổ biến

- **Cho rằng volatile khiến ++ atomic:** một lần đọc volatile và một lần ghi volatile vẫn bị các luồng khác xen giữa.
- **Đổi `volatile int` thành `volatile long` để “an toàn hơn”:** mở rộng miền giá trị nhưng không sửa lost update.
- **Dùng `AtomicInteger.get()` rồi `set(get() + 1)`:** hai lệnh atomic riêng lẻ vẫn **không phải atomic increment**. Dùng `incrementAndGet` hoặc CAS đúng.
- **Cho rằng `synchronized` trên một method là đủ dù các nơi khác ghi không lock:** mọi đường truy cập tới invariant phải thống nhất.
- **Dùng `LongAdder` để cấp ID duy nhất hoặc xử lý hạn mức cứng:** `sum` không cung cấp snapshot tuyến tính hóa theo cách đó.
- **Đọc hai field volatile rồi tin snapshot nhất quán:** mỗi field có thể đến từ một giai đoạn cập nhật khác nhau.
- **Chỉ chạy thử nhiều vòng rồi kết luận không có race:** race là vấn đề tính đúng với mọi lịch chạy cho phép, không được chứng minh bằng một vài lần chạy.
- **Giải quyết bằng `sleep`, `yield` hoặc `Thread.onSpinWait`:** chúng có thể tác động lịch chạy/hiệu năng nhưng không biến read-modify-write thành atomic.
- **Đổi counter sang atomic nhưng vẫn có những chỗ gán thẳng/reset không phối hợp:** tất cả phép thay đổi trạng thái phải tuân theo cùng contract.
- **Bỏ qua overflow:** atomic increment của int không đồng nghĩa tăng chính xác trên tập số nguyên toán học không giới hạn.

## 13. Bài tập tự luyện và đáp án

**Bài 1.** Hai thread cùng thực hiện `volatileCounter++` khi giá trị ban đầu bằng 5. Kết quả có thể là bao nhiêu nếu mỗi thread chạy một lần và cả hai đã hoàn tất? Giải thích lịch chạy gây mất cập nhật.

**Bài 2.** Thay `counter++` bằng `atomicCounter.set(atomicCounter.get() + 1)` có giải quyết race không? Nếu không, phải sửa thế nào?

**Bài 3.** Hãy giải thích vì sao `volatile boolean stop` có thể phù hợp cho một cờ dừng đơn giản nhưng `volatile int soldTickets` không đủ cho thao tác “nếu còn vé thì bán một vé”.

**Bài 4.** Một collector dùng `LongAdder` để đếm request và cần hiển thị tổng gần thời gian thực. Nếu ở thời điểm xuất báo cáo phải có tổng chính xác, nhất quán với danh sách request cùng một thời điểm, chỉ gọi `sum()` có đủ không?

**Bài 5.** Vì sao assertion sau `join` vẫn có thể quan sát `1` trong ví dụ hai increment? `join` đã bảo đảm visibility hay chưa?

**Gợi ý đáp án:**

1. Có thể là **6 hoặc 7**: hai luồng đều đọc 5, đều ghi 6 dẫn tới 6; hoặc một luồng hoàn tất trước khi luồng kia đọc thì có 7. Với đúng hai lần tăng từ 5, không có reset/overflow, không hợp lý để lấy 8.
2. Không; `get` và `set` tách rời. Dùng `incrementAndGet` hoặc vòng CAS; nếu cần điều kiện/side effect thì bảo vệ toàn bộ logic.
3. Cờ dừng là thông điệp độc lập, còn bán vé là chuỗi kiểm tra số lượng rồi trừ/ghi nhận; nhiều thread có thể cùng vượt qua kiểm tra.
4. Không đủ nếu yêu cầu snapshot nhất quán nhiều cấu trúc đang cập nhật; cần cơ chế snapshot/transaction/synchronization đáp ứng invariant.
5. `join` đã cung cấp quan hệ happens-before giữa hoạt động thread kết thúc và luồng chờ; main thấy kết quả lưu cuối là 1, nhưng bản thân hai phép tính trước đó đã mất một lượt tăng.

## Tài liệu tham khảo Java SE 17

- [Java Language Specification §17.4 — Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4)
- `AtomicInteger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- `LongAdder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- `ReentrantLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html

**Điểm cần nhớ:** `volatile` giúp xác lập visibility và ordering theo Java Memory Model; `counter++` vẫn là read-modify-write nhiều bước. Nếu cần bảo toàn mọi lần tăng, dùng thao tác atomic thực sự hoặc bảo vệ toàn bộ phép cập nhật bằng lock.