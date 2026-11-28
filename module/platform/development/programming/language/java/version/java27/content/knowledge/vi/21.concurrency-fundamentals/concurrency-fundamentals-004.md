# Volatile, atomic và cập nhật không khóa trong Java 27

Trong chương trình Java đồng thời, nhiều thread có thể cùng đọc và sửa dữ liệu. Nếu không có cơ chế phối hợp, một thread có thể **không nhìn thấy thay đổi đúng thời điểm**, hai thread có thể **ghi đè kết quả của nhau**, hoặc một đối tượng có thể lộ ra với trạng thái chưa được công bố an toàn.

Ba khái niệm thường xuất hiện cùng nhau nhưng không thể thay thế cho nhau:

- **`volatile`**: thiết lập các bảo đảm về khả năng nhìn thấy dữ liệu và thứ tự bộ nhớ cho một biến; các lần đọc/ghi volatile riêng lẻ có ngữ nghĩa đặc biệt trong Java Memory Model.
- **Atomic operation**: một thao tác được xem như một bước không thể chia nhỏ theo hợp đồng của API; ví dụ `AtomicInteger.incrementAndGet()` cập nhật số đếm theo cách nguyên tử.
- **Cập nhật không khóa (non-blocking/lock-free)**: xây dựng thuật toán cạnh tranh dựa trên các primitive như *compare-and-set* (CAS), không phải bằng cách tự động thay mọi `synchronized` bằng `volatile`.

Bài thuộc chương **Nền tảng lập trình đồng thời** của module **Java 27 và các kiến thức liên quan**. Các ví dụ sử dụng Java Memory Model, `java.util.concurrent.atomic`, `VarHandle`, các cấu trúc đồng thời và tiện ích thread đã được chuẩn hóa; không yêu cầu bật preview hay dùng API nội bộ/legacy.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **visibility**, **atomicity** và **ordering** trong xử lý đồng thời.
2. Giải thích `happens-before` và vai trò của một lần ghi/đọc `volatile`.
3. Nêu lý do `volatile int counter` vẫn **không an toàn** khi gọi `counter++` từ nhiều thread.
4. Dùng `AtomicInteger`, `AtomicLong`, `AtomicBoolean` và `AtomicReference` đúng hợp đồng.
5. Hiểu thao tác CAS, xây vòng lặp cập nhật trạng thái bất biến và nhận diện rủi ro lặp lại tính toán.
6. Biết khi nào dùng `LongAdder`, `VarHandle` và `AtomicStampedReference`.
7. Phân biệt *lock-free*, *wait-free*, *blocking* và hiện tượng tranh chấp/starvation.
8. Chọn giải pháp phù hợp cho cờ dừng, số đếm, trạng thái gồm nhiều trường và dữ liệu chia sẻ.

## 2. Ba vấn đề khác nhau: visibility, atomicity, ordering

Giả sử hai thread cùng truy cập dữ liệu:

```java
class Shared {
    int data;
    boolean ready;
}
```

Thread A:

```java
shared.data = 42;
shared.ready = true;
```

Thread B:

```java
while (!shared.ready) {
    // Chờ.
}
System.out.println(shared.data);
```

**Đây là ví dụ không đồng bộ hóa, không phải mã nên chạy trong production.** Nếu không có một quan hệ đồng bộ phù hợp, các lần truy cập này tạo *data race*. Java không hứa rằng B sẽ sớm nhìn thấy `ready == true`, và cũng không hứa rằng khi nhìn thấy cờ đó thì B sẽ nhìn thấy `data == 42`.

| Vấn đề | Câu hỏi | Biện pháp thường dùng |
|---|---|---|
| **Visibility** | Thread B có nhìn thấy giá trị A đã công bố không? | `volatile`, lock, atomic/đồng bộ hóa có contract phù hợp |
| **Atomicity** | Hai thread có thể xen kẽ làm mất một lần cập nhật không? | `AtomicInteger`, CAS, `synchronized`, `Lock` |
| **Ordering** | Các thao tác trước/sau điểm công bố có được quan sát theo thứ tự được bảo đảm không? | `happens-before`, acquire/release, lock, volatile |

Một kỹ thuật có thể giải quyết một số vấn đề mà **không giải quyết tất cả**. Ví dụ `volatile` giúp công bố một cờ và dữ liệu được ghi trước cờ, nhưng **không làm cho chuỗi đọc–tính–ghi của `++` trở thành một thao tác nguyên tử**.

## 3. Java Memory Model và happens-before

**Java Memory Model (JMM)** quy định những giá trị mà một lần đọc có thể quan sát trong chương trình nhiều thread và những quan hệ thứ tự cần được tôn trọng.

Quan hệ **happens-before** (HB) là công cụ thiết yếu: nếu hành động A happens-before hành động B, các hiệu ứng bộ nhớ cần thiết từ A được bảo đảm hiển thị cho B theo các quy tắc của JMM.

Một số nguồn tạo quan hệ happens-before quan trọng:

| Quan hệ | Ý nghĩa |
|---|---|
| **Program order** | Trong một thread, hành động trước HB hành động sau theo thứ tự chương trình |
| **Volatile write/read** | Một lần ghi volatile HB mọi lần đọc tiếp theo của cùng field volatile theo *synchronization order* |
| **Monitor unlock/lock** | Thoát monitor (`unlock`) HB một lần vào cùng monitor (`lock`) sau đó |
| **Thread.start()** | Lời gọi `start()` trên một thread HB các hành động bên trong thread đó |
| **Thread termination/join** | Các hành động của thread hoàn tất HB thread khác phát hiện sự kết thúc qua cơ chế như `join()` thành công |
| **Transitivity** | Nếu A HB B và B HB C, thì A HB C |

Không nên nhầm happens-before với đồng hồ vật lý hoặc giả định một thread phải chạy xong hoàn toàn trước thread khác. Đây là **quan hệ bảo đảm về quan sát bộ nhớ**, không phải lịch chạy do hệ điều hành cung cấp.

### 3.1. Lý do println hoặc sleep không sửa race

`System.out.println` có thể dùng cơ chế đồng bộ nội bộ trong một số triển khai, khiến chương trình lỗi vô tình thay đổi hành vi khi thêm log. Nhưng việc in log không phải cách định nghĩa quan hệ đồng bộ cho trạng thái nghiệp vụ.

`Thread.sleep(...)` trì hoãn thread, **không tạo quan hệ happens-before** với một lần ghi tùy ý từ thread khác. Vì thế không thể sửa data race bằng cách "chờ lâu hơn".

## 4. Volatile: ý nghĩa và bảo đảm

Khai báo:

```java
class WorkerState {
    volatile boolean stopRequested;
}
```

Lần ghi:

```java
state.stopRequested = true;
```

Và lần đọc:

```java
if (state.stopRequested) {
    // Đã thấy yêu cầu dừng.
}
```

`volatile` đảm bảo truy cập tới field có những hiệu ứng bộ nhớ theo JMM:

- Một **volatile write** có hiệu ứng công bố (*release-like*) đối với những thao tác trước nó.
- Một **volatile read** có hiệu ứng tiếp nhận (*acquire-like*) đối với thao tác sau nó.
- Volatile read/write tham gia các quy tắc về synchronization order; không được coi là truy cập biến thông thường.
- Các lần đọc/ghi riêng lẻ đối với biến volatile, kể cả `long` và `double`, có tính nguyên tử theo bảo đảm của JMM đối với truy cập đó.

Điều đó **không** làm mọi biểu thức sử dụng field volatile thành nguyên tử và không bảo đảm rằng một thread đang chạy sẽ được scheduler cho chạy ngay để thấy thay đổi.

### 4.1. Safe publication bằng cờ volatile

Ví dụ:

```java
final class MessageSlot {
    private String text;
    private volatile boolean ready;

    void publish(String value) {
        text = value;
        ready = true;
    }

    String awaitMessage() {
        while (!ready) {
            Thread.onSpinWait();
        }
        return text;
    }
}
```

Giả sử **chỉ có một publisher**, không ghi lại `text` sau khi publish và consumer đọc cờ như trên:

1. Publisher gán `text = value`.
2. Publisher ghi `ready = true` với volatile write.
3. Consumer đọc `ready == true` qua volatile read.
4. Do quan hệ happens-before bắc cầu, consumer có thể dựa vào giá trị `text` đã được ghi **trước** khi cờ được công bố.

`text` không cần tự là volatile trong mẫu **công bố một lần** này. Nhưng nếu sau đó nhiều thread tiếp tục sửa `text` độc lập, cờ `ready` không còn đủ để bảo vệ các cập nhật mới.

**Quan trọng:** `while (!ready) Thread.onSpinWait()` là *busy waiting*, có thể tốn CPU và không có giới hạn chờ. Ví dụ chỉ để giải thích quan hệ bộ nhớ. Với chờ sự kiện thông thường, ưu tiên `CountDownLatch`, `BlockingQueue`, `Future`, `Condition` hoặc cơ chế chờ phù hợp; không mặc định spin.

### 4.2. Volatile không phải giải pháp cho mọi trạng thái mutable

Khai báo:

```java
volatile java.util.List<String> names = new java.util.ArrayList<>();
```

chỉ làm **tham chiếu `names`** có ngữ nghĩa volatile. Nó không tự khiến những thao tác nội bộ của `ArrayList` (như `add` hoặc `remove`) an toàn khi nhiều thread cùng sửa.

Tương tự:

```java
volatile int[] counts = new int[10];
```

không biến `counts[0]++` thành atomic operation. Từ khóa volatile áp dụng cho **field tham chiếu**, không tự áp dụng cho từng phần tử mảng.

## 5. Tại sao volatileCounter++ vẫn bị mất cập nhật?

Xét:

```java
class Counter {
    volatile int value;

    void increment() {
        value++;
    }
}
```

Biểu thức `value++` bao gồm các bước logic:

1. Đọc `value`.
2. Tính `old + 1`.
3. Ghi kết quả trở lại `value`.

Ngay cả khi mỗi lần đọc/ghi có ngữ nghĩa volatile, **chuỗi ba bước không phải một giao dịch nguyên tử**.

Ví dụ interleaving:

| Thời điểm | Thread A | Thread B | value |
|---|---|---|---|
| Ban đầu | | | 0 |
| 1 | Đọc 0 | | 0 |
| 2 | | Đọc 0 | 0 |
| 3 | Tính 1, ghi 1 | | 1 |
| 4 | | Tính 1, ghi 1 | 1 |

Có **hai** lần gọi `increment()` nhưng kết quả chỉ tăng **một**: đây là *lost update*. `volatile` không ngăn hai thread cùng đọc một giá trị cũ.

Các thao tác sau cũng là read-modify-write và không được `volatile` tự làm nguyên tử:

```java
counter += 10;
counter--;
counter = Math.max(counter, newValue);
```

Khi cần cập nhật nguyên tử, chọn API atomic hoặc khóa phù hợp.

## 6. AtomicInteger và AtomicLong: số đếm cập nhật an toàn

`java.util.concurrent.atomic.AtomicInteger` cung cấp các thao tác nguyên tử trên một giá trị `int`:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger counter = new AtomicInteger(0);

counter.incrementAndGet(); // Tăng và trả giá trị mới.
counter.getAndIncrement(); // Trả giá trị cũ rồi tăng.
counter.addAndGet(5);      // Cộng 5, trả giá trị mới.

System.out.println(counter.get()); // 7
```

Phân tích:

- Khởi tạo 0.
- `incrementAndGet()` trả 1, giá trị hiện tại 1.
- `getAndIncrement()` trả 1, giá trị hiện tại 2.
- `addAndGet(5)` trả 7, giá trị hiện tại 7.

### 6.1. Một số phương thức quan trọng

| Phương thức | Hành vi |
|---|---|
| `get()` | Đọc giá trị với hiệu ứng bộ nhớ volatile theo API |
| `set(value)` | Ghi giá trị với hiệu ứng bộ nhớ volatile theo API |
| `incrementAndGet()` | Cập nhật `+1` nguyên tử, trả giá trị mới |
| `getAndIncrement()` | Cập nhật `+1` nguyên tử, trả giá trị cũ |
| `addAndGet(delta)` | Cộng nguyên tử, trả giá trị mới |
| `getAndAdd(delta)` | Cộng nguyên tử, trả giá trị cũ |
| `compareAndSet(expect, update)` | Thử cập nhật nếu giá trị hiện tại bằng `expect`, trả kết quả boolean |
| `compareAndExchange(expect, update)` | Trả giá trị đã quan sát ở vị trí cập nhật, đổi khi khớp kỳ vọng |
| `updateAndGet(operator)` | Cập nhật bằng hàm và trả giá trị mới |
| `accumulateAndGet(x, operator)` | Kết hợp giá trị hiện tại với `x`, trả kết quả mới |

`AtomicLong` có nhóm thao tác tương ứng trên `long`. `AtomicBoolean` thường dùng cho trạng thái bật/tắt và `compareAndSet` trên boolean.

### 6.2. AtomicInteger không tự kiểm tra tràn số

`incrementAndGet()` và `addAndGet()` thực hiện phép tính theo ngữ nghĩa `int`, trong đó tràn số nguyên có thể quay vòng. Nếu nghiệp vụ **không cho phép overflow**, cần đặt chính sách kiểm tra trong thao tác atomic:

```java
AtomicInteger count = new AtomicInteger(0);

int updated = count.updateAndGet(
        old -> Math.addExact(old, 1)
);
```

Nếu đang ở `Integer.MAX_VALUE`, `Math.addExact` ném `ArithmeticException` thay vì cho kết quả tràn. Hàm cập nhật phải không có side effect không an toàn vì có thể được đánh giá lại khi CAS thất bại.

## 7. Ví dụ hoàn chỉnh: volatile và AtomicInteger dưới cạnh tranh

Tạo file `AtomicCounterDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public class AtomicCounterDemo {

    private static final int THREADS = 8;
    private static final int INCREMENTS_PER_THREAD = 20_000;

    private static final class Counters {
        volatile int volatileCount = 0;
        final AtomicInteger atomicCount = new AtomicInteger();
        final LongAdder adder = new LongAdder();
    }

    public static void main(String[] args) throws InterruptedException {
        Counters counters = new Counters();
        CountDownLatch start = new CountDownLatch(1);
        Thread[] workers = new Thread[THREADS];

        for (int i = 0; i < THREADS; i++) {
            workers[i] = new Thread(() -> {
                try {
                    start.await();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    return;
                }

                for (int n = 0; n < INCREMENTS_PER_THREAD; n++) {
                    counters.volatileCount++;
                    counters.atomicCount.incrementAndGet();
                    counters.adder.increment();
                }
            });

            workers[i].start();
        }

        start.countDown();

        for (Thread worker : workers) {
            worker.join();
        }

        int expected = THREADS * INCREMENTS_PER_THREAD;

        System.out.println("Expected: " + expected);
        System.out.println("Volatile ++: " + counters.volatileCount);
        System.out.println("AtomicInteger: " + counters.atomicCount.get());
        System.out.println("LongAdder: " + counters.adder.sum());
    }
}
```

Biên dịch và chạy:

```bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
```

Hai giá trị được bảo đảm khi **mọi worker đã chạy trọn vòng lặp và kết thúc bình thường**:

```text
Expected: 160000
AtomicInteger: 160000
LongAdder: 160000
```

Giá trị `Volatile ++` **không có kết quả cố định**: nó có thể thấp hơn 160000 do mất cập nhật, thậm chí đôi khi bằng 160000 ở một lần chạy. Nếu một lần chạy tình cờ cho kết quả đúng thì **không chứng minh** `volatileCount++` an toàn.

`CountDownLatch` chỉ giúp các worker bắt đầu gần nhau hơn; nó không làm `volatileCount++` trở thành nguyên tử. `Thread.join()` giúp main chờ các worker hoàn tất và quan sát kết quả sau khi chúng kết thúc.

### 7.1. Giới hạn của thử nghiệm đồng thời

Không nên kết luận tính đúng đắn của một thuật toán từ việc chạy một ví dụ 100 lần không thấy lỗi. Lịch chạy thread thay đổi theo máy, JVM và tải hệ thống. Để kiểm tra các bảo đảm của JMM, cần kết hợp lập luận dựa trên hợp đồng, code review và kiểm thử stress phù hợp.

## 8. Compare-and-set (CAS) hoạt động thế nào?

**CAS** so sánh giá trị hiện tại với giá trị kỳ vọng, rồi cập nhật thành giá trị mới **nếu điều kiện khớp**, như một phép thao tác nguyên tử.

```java
AtomicInteger state = new AtomicInteger(10);

boolean first = state.compareAndSet(10, 20);  // true
boolean second = state.compareAndSet(10, 30); // false

System.out.println(first);      // true
System.out.println(second);     // false
System.out.println(state.get()); // 20
```

Lần đầu thành công vì giá trị hiện tại là 10; lần sau thất bại vì giá trị đã là 20.

### 8.1. CAS loop cho read-modify-write có điều kiện

Ví dụ chỉ tăng nếu chưa đạt giới hạn:

```java
static boolean tryIncrement(
        AtomicInteger counter,
        int max
) {
    while (true) {
        int current = counter.get();

        if (current >= max) {
            return false;
        }

        if (counter.compareAndSet(current, current + 1)) {
            return true;
        }
    }
}
```

Hàm trên có ba bước trong vòng lặp:

1. Lấy một snapshot `current`.
2. Kiểm tra điều kiện `current < max`.
3. Chỉ ghi `current + 1` nếu chưa có thread khác làm thay đổi giá trị quan sát.

Nếu CAS thất bại, method đọc lại và kiểm tra điều kiện từ đầu. Nó **không** được phép tính một lần rồi `set` đè lên giá trị mới của thread khác.

Ví dụ giả định `max` không vượt phạm vi có thể khiến `current + 1` tràn; trong triển khai nghiêm ngặt có thể dùng `Math.addExact` hoặc kiểm tra giới hạn đầu vào.

### 8.2. compareAndExchange và compareAndSet

- `compareAndSet` trả `true` nếu cập nhật thành công.
- `compareAndExchange` trả về **giá trị đã quan sát** tại vị trí so sánh; khi bằng expected thì mới cập nhật.

Không được hiểu giá trị trả về của `compareAndExchange` là "giá trị mới". Dùng API theo điều kiện mà thuật toán thực sự cần.

### 8.3. CAS thất bại không nhất thiết là lỗi nghiệp vụ

Trong tình huống nhiều thread tranh chấp, một CAS thất bại có thể chỉ có nghĩa **thread khác đã cập nhật trước**. Đây là tín hiệu để retry hoặc trả "không thực hiện" theo hợp đồng, không phải lúc nào cũng là exception cần log.

## 9. AtomicReference<T>: cập nhật một tham chiếu

`AtomicReference<T>` cung cấp các thao tác nguyên tử đối với **tham chiếu** tới một đối tượng kiểu `T`:

```java
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<String> status =
        new AtomicReference<>("NEW");

boolean claimed = status.compareAndSet("NEW", "PROCESSING");

System.out.println(claimed);    // true
System.out.println(status.get()); // PROCESSING
```

Với tham chiếu đối tượng, `compareAndSet(expected, update)` so sánh **identity của tham chiếu**, không tự gọi `equals`. Trong ví dụ trên dùng cùng literal String (được intern) để minh họa, nhưng trong mã nghiệp vụ nên dùng enum cho trạng thái hữu hạn hoặc giữ đúng snapshot tham chiếu đã đọc, tránh dựa vào giá trị bằng nhau theo `equals`.

### 9.1. AtomicReference không biến đối tượng bên trong thành immutable

```java
AtomicReference<java.util.List<String>> reference =
        new AtomicReference<>(new java.util.ArrayList<>());
```

Lời gọi `reference.set(newList)` cập nhật **tham chiếu** nguyên tử. Nhưng thao tác sau không được tự bảo vệ:

```java
reference.get().add("data");
```

Nếu nhiều thread cùng sửa `ArrayList` được tham chiếu, chúng vẫn có thể đụng độ dữ liệu. Atomic reference không làm các field hay collection mutable bên trong đối tượng tự động thread-safe.

Để quản lý một trạng thái gồm nhiều trường, mẫu phổ biến là **đối tượng bất biến + CAS thay toàn bộ tham chiếu**.

## 10. Trạng thái nhiều trường bằng immutable record và CAS

Giả sử một tài khoản có:

- `revision`: số phiên bản thay đổi.
- `balanceVnd`: số dư tiền Việt Nam đồng.

Nếu lưu thành hai field atomic độc lập, client có thể thấy `revision` mới nhưng `balanceVnd` cũ (hoặc ngược lại). Nếu hai giá trị phải **nhất quán với nhau**, hãy lưu chúng trong một snapshot bất biến và cập nhật cả snapshot bằng một CAS.

### 10.1. Ví dụ hoàn chỉnh: LedgerCASDemo.java

```java
import java.util.concurrent.atomic.AtomicReference;

public class LedgerCASDemo {

    record Balance(long revision, long balanceVnd) {
        Balance {
            if (revision < 0 || balanceVnd < 0) {
                throw new IllegalArgumentException("Negative state");
            }
        }
    }

    static final class Ledger {
        private final AtomicReference<Balance> state =
                new AtomicReference<>(new Balance(0L, 0L));

        void deposit(long amountVnd) {
            if (amountVnd < 0) {
                throw new IllegalArgumentException("Negative deposit");
            }

            while (true) {
                Balance current = state.get();

                Balance next = new Balance(
                        Math.incrementExact(current.revision()),
                        Math.addExact(current.balanceVnd(), amountVnd)
                );

                if (state.compareAndSet(current, next)) {
                    return;
                }
            }
        }

        Balance snapshot() {
            return state.get();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        Ledger ledger = new Ledger();

        Thread first = new Thread(() -> {
            for (int i = 0; i < 10_000; i++) {
                ledger.deposit(10L);
            }
        });

        Thread second = new Thread(() -> {
            for (int i = 0; i < 10_000; i++) {
                ledger.deposit(10L);
            }
        });

        first.start();
        second.start();

        first.join();
        second.join();

        Balance finalState = ledger.snapshot();

        System.out.println("Revision: " + finalState.revision());
        System.out.println("Balance: " + finalState.balanceVnd());
    }
}
```

Biên dịch và chạy:

```bash
javac LedgerCASDemo.java
java LedgerCASDemo
```

Kết quả nếu các thread hoàn tất thành công:

```text
Revision: 20000
Balance: 200000
```

### 10.2. Tại sao ví dụ không bị lost update?

Mỗi thread:

1. Đọc một đối tượng `Balance` hiện tại.
2. Tính một bản ghi `Balance` mới.
3. Thử CAS để thay **cả snapshot**.
4. Nếu thread khác đã thay snapshot trước, CAS thất bại và thread tính lại với giá trị mới.

Hai số luôn được đọc từ **cùng một record bất biến**. Khi CAS thành công, cặp `revision` và `balanceVnd` trở thành trạng thái mới trong một bước thay tham chiếu nguyên tử.

### 10.3. Lưu ý về record và tính bất biến

Record chứa các field `long` nguyên thủy như trên có cấu trúc bất biến phù hợp cho snapshot. Nhưng nếu record chứa một `List` mutable, record **không tự bảo đảm deep immutability**:

```java
record State(java.util.List<String> items) {}
```

Nếu object bên trong có thể bị sửa qua alias, việc dùng `AtomicReference<State>` không cứu được bất biến dữ liệu. Khi cần, dùng defensive copy và các kiểu collection không cho sửa phù hợp.

## 11. Hàm cập nhật AtomicInteger/AtomicReference phải thuần nếu có thể

Các method như:

- `AtomicInteger.updateAndGet(IntUnaryOperator)`,
- `AtomicInteger.getAndUpdate(IntUnaryOperator)`,
- `AtomicReference.updateAndGet(UnaryOperator<T>)`,
- `AtomicReference.getAndUpdate(UnaryOperator<T>)`

có thể cần áp dụng lại hàm cập nhật khi CAS thất bại do tranh chấp. Vì thế, **không đặt side effect cần thực hiện đúng một lần** vào trong hàm cập nhật.

### 11.1. Ví dụ dễ sai

```java
AtomicInteger counter = new AtomicInteger();

counter.updateAndGet(current -> {
    // KHÔNG nên gửi email, trừ tiền, ghi audit log tại đây:
    // hàm có thể được gọi nhiều lần.
    System.out.println("Calculating next value");
    return current + 1;
});
```

Lệnh `println` có thể chạy nhiều lần cho một lời gọi `updateAndGet` dưới cạnh tranh. Tương tự, một lời gọi I/O hoặc tăng bộ đếm ngoài có side effect có thể bị lặp lại mà không tương ứng với một cập nhật thành công.

### 11.2. Cách viết nên ưu tiên

```java
int newValue = counter.updateAndGet(
        current -> Math.addExact(current, 1)
);

// Chỉ thực hiện hành động sau khi cập nhật hoàn tất.
System.out.println("Committed value: " + newValue);
```

Đoạn code này tránh side effect bên trong hàm retry. Tuy nhiên, sau khi CAS thành công, thread khác **vẫn có thể cập nhật tiếp** trước khi bạn log. Vì vậy, log chỉ mô tả giá trị do lời gọi đã trả về, không phải đảm bảo đây là giá trị hiện tại tại thời điểm log.

Nếu thao tác nghiệp vụ cần transaction đồng bộ với database hoặc external API, một CAS trên bộ nhớ **không tự bảo đảm exactly-once** cho phần bên ngoài.

## 12. AtomicBoolean và cờ dừng: phải phân biệt với interruption

Một cờ dừng do ứng dụng sở hữu có thể dùng `volatile boolean` hoặc `AtomicBoolean`:

```java
import java.util.concurrent.atomic.AtomicBoolean;

AtomicBoolean running = new AtomicBoolean(true);

running.set(false); // Yêu cầu dừng.
```

Nếu chỉ có **một thread ghi cờ** và các thread khác đọc, `volatile` thường đủ. Nếu cần chuyển trạng thái đúng một lần theo điều kiện (ví dụ chỉ một thread được quyền khởi động quá trình đóng), `AtomicBoolean.compareAndSet` có ích:

```java
AtomicBoolean closing = new AtomicBoolean(false);

if (closing.compareAndSet(false, true)) {
    System.out.println("Thread này nhận trách nhiệm đóng");
}
```

Chỉ một thread có thể chuyển trạng thái từ `false` sang `true` thành công trong một lần chuyển không quay lại trạng thái cũ.

### 12.1. Volatile không đánh thức một thao tác đang block

Nếu worker đang bị chặn ở `BlockingQueue.take()`, `Thread.sleep()` hoặc một I/O có semantics chặn, việc thread khác đặt `stopRequested = true` **không tự động làm worker thức dậy**.

Trong nhiều thiết kế, ngắt thread bằng `interrupt()` hoặc cơ chế shutdown của executor/queue là lựa chọn phù hợp hơn. Khi bắt `InterruptedException` mà không thể tiếp tục ném ra, code thường nên khôi phục cờ interruption:

```java
try {
    Thread.sleep(1_000L);
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    return;
}
```

Interruption là **tín hiệu hợp tác**, không phải cơ chế cưỡng chế dừng bất kỳ code nào. Phải kiểm tra hợp đồng của thao tác có thể block.

### 12.2. Virtual thread không đổi quy tắc volatile/atomic

Trong Java hiện hành, **virtual thread** và platform thread đều chịu các quy tắc JMM tương ứng. Virtual thread không làm `counter++` an toàn hay biến field thường thành volatile. Khác biệt về scheduling và chi phí thread không thay thế được đồng bộ hóa trạng thái dùng chung.

## 13. LongAdder: số đếm cạnh tranh cao

`LongAdder` được thiết kế để tối ưu hoạt động cộng dồn khi nhiều thread cập nhật cùng một bộ đếm:

```java
import java.util.concurrent.atomic.LongAdder;

LongAdder requests = new LongAdder();

requests.increment();
requests.add(5L);

System.out.println(requests.sum()); // 6
```

### 13.1. LongAdder khác AtomicLong ở đâu?

| Yêu cầu | `AtomicLong` | `LongAdder` |
|---|---|---|
| Cập nhật cộng dồn nguyên tử ở một giá trị | Có | `add`/`increment` thiết kế cho cộng dồn cạnh tranh |
| Đọc một giá trị đồng nhất với cập nhật (atomic snapshot) | `get()` cho giá trị atomic theo contract | `sum()` **không phải** atomic snapshot khi có cập nhật đồng thời |
| CAS theo giá trị hiện tại | Có `compareAndSet` | Không cung cấp CAS trên tổng |
| Bộ đếm metrics có tần suất cập nhật rất cao | Dùng được | Thường là lựa chọn đáng cân nhắc |
| Ràng buộc với một giá trị hoặc điều kiện cập nhật | Phù hợp hơn | Không phù hợp |

`LongAdder.sum()` cộng các thành phần nội bộ. Nếu cập nhật vẫn xảy ra trong lúc `sum()` thực thi, kết quả **có thể không phản ánh một snapshot nguyên tử của tất cả cập nhật**. Sau khi các worker đã hoàn tất và không còn ghi, `sum()` phản ánh tổng các cập nhật đã được ghi nhận.

### 13.2. sumThenReset không phải transaction với mọi writer

`sumThenReset()` lấy tổng rồi đưa các thành phần về trạng thái ban đầu, nhưng không nên coi lời gọi này là một phép "lấy và reset" nguyên tử đối với mọi update đang diễn ra đồng thời. Nếu yêu cầu chốt sổ chính xác theo từng ranh giới thời gian, cần thiết kế khác.

### 13.3. DoubleAdder

`DoubleAdder` hỗ trợ cộng dồn kiểu `double` ở mức tương tự, nhưng phép cộng dấu phẩy động có tính chất số học và thứ tự tính khác số nguyên. Khi dùng metrics liên quan đến độ chính xác tài chính, không nên mặc định chọn `DoubleAdder` như biểu diễn tiền tệ.

## 14. VarHandle: điều khiển chế độ truy cập bộ nhớ

`java.lang.invoke.VarHandle` là API chuẩn để truy cập biến và phần tử mảng với những chế độ bộ nhớ khác nhau. Nó hữu ích khi xây dựng thư viện đồng thời cấp thấp mà một `AtomicInteger` hoặc `volatile` đơn giản không thể diễn đạt chính xác yêu cầu.

Một số access mode hiện hành:

| Chế độ | Ví dụ | Ý nghĩa tổng quát |
|---|---|---|
| Plain | `get` / `set` | Truy cập plain, không bổ sung bảo đảm đồng bộ như volatile |
| Opaque | `getOpaque` / `setOpaque` | Tính nhất quán hạn chế, không mang đầy đủ acquire/release |
| Acquire | `getAcquire` | Đọc với hiệu ứng acquire |
| Release | `setRelease` | Ghi với hiệu ứng release |
| Volatile | `getVolatile` / `setVolatile` | Ngữ nghĩa truy cập volatile |
| Atomic update | `compareAndSet`, `getAndAdd` khi kiểu biến hỗ trợ | Thao tác atomic theo access mode tương ứng |

Không nên tự thay `getVolatile` bằng `getOpaque` hoặc `getAcquire` chỉ vì "nhẹ hơn": các chế độ có **mức bảo đảm khác nhau**, nên thuật toán phải được chứng minh theo JMM và tài liệu `VarHandle`.

### 14.1. Ví dụ getAcquire/setRelease

Tạo file `VarHandlePublicationDemo.java`:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class VarHandlePublicationDemo {

    private static final VarHandle READY;

    static {
        try {
            READY = MethodHandles.lookup().findVarHandle(
                    VarHandlePublicationDemo.class,
                    "ready",
                    boolean.class
            );
        } catch (ReflectiveOperationException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    private String message;
    private boolean ready;

    void publish(String value) {
        message = value;
        READY.setRelease(this, true);
    }

    String await() {
        while (!(boolean) READY.getAcquire(this)) {
            Thread.onSpinWait();
        }
        return message;
    }

    public static void main(String[] args)
            throws InterruptedException {

        VarHandlePublicationDemo slot =
                new VarHandlePublicationDemo();

        Thread reader = new Thread(() ->
                System.out.println(slot.await()));

        reader.start();
        slot.publish("Dữ liệu đã công bố");
        reader.join();
    }
}
```

Kết quả:

```text
Dữ liệu đã công bố
```

Ví dụ dùng một writer công bố đúng một lần. `setRelease` và `getAcquire` thiết lập quan hệ công bố/tiếp nhận phù hợp khi consumer quan sát giá trị cờ do publisher ghi, để consumer đọc `message` đã được đặt trước cờ.

Đây là minh họa mức thấp, **không khuyến nghị busy-wait trong ứng dụng thông thường**. Với sự kiện đồng bộ một lần, `CountDownLatch` thường dễ dùng và có contract rõ hơn.

### 14.2. Khi nào dùng Atomic* thay vì VarHandle?

Nếu chỉ cần cộng số đếm, CAS tham chiếu, cờ boolean hoặc thao tác nguyên tử đơn giản, `AtomicInteger`, `AtomicLong`, `AtomicBoolean` hay `AtomicReference` thường có API dễ đọc và an toàn về ý định hơn.

`VarHandle` có giá trị khi thiết kế framework/concurrent data structure đặc biệt, nhưng yêu cầu review kỹ hơn về access modes, thứ tự bộ nhớ và khả năng tương thích của kiểu biến.

## 15. ABA problem: giá trị quay về A không có nghĩa không đổi

CAS thông thường chỉ so sánh **giá trị hoặc tham chiếu ở thời điểm kiểm tra** với kỳ vọng hiện tại.

Tưởng tượng:

1. Thread A đọc trạng thái `A`.
2. Thread B đổi `A -> B`.
3. Thread B lại đổi `B -> A`.
4. Thread A thực hiện CAS, thấy `A` nên cho rằng trạng thái "không thay đổi".

Nếu thuật toán cần phát hiện **bất kỳ lần thay đổi nào** kể từ snapshot cũ, CAS trên giá trị hiện tại là chưa đủ. Đó là **ABA problem**.

### 15.1. Ví dụ với AtomicStampedReference

`AtomicStampedReference<T>` lưu một cặp **tham chiếu và dấu phiên bản** (*stamp*), cho phép CAS dựa trên cả hai.

Tạo `ABADemo.java`:

```java
import java.util.concurrent.atomic.AtomicStampedReference;

public class ABADemo {

    enum State {
        A, B, C
    }

    public static void main(String[] args) {
        AtomicStampedReference<State> ref =
                new AtomicStampedReference<>(State.A, 0);

        int[] observedStamp = new int[1];

        State observed = ref.get(observedStamp);
        int oldStamp = observedStamp[0];

        // Minh họa một lịch xen kẽ:
        // Thread khác thay A -> B -> A, mỗi lần tăng stamp.
        boolean first = ref.compareAndSet(State.A, State.B, 0, 1);
        boolean second = ref.compareAndSet(State.B, State.A, 1, 2);

        // Thao tác dùng snapshot đã cũ: A với stamp 0.
        boolean stale = ref.compareAndSet(
                observed,
                State.C,
                oldStamp,
                oldStamp + 1
        );

        System.out.println("A to B: " + first);
        System.out.println("B to A: " + second);
        System.out.println("Stale CAS: " + stale);
        System.out.println("Current stamp: " + ref.getStamp());
    }
}
```

Kết quả:

```text
A to B: true
B to A: true
Stale CAS: false
Current stamp: 2
```

Mặc dù trạng thái hiện tại lại là `A`, stamp đã khác 0 nên CAS dùng snapshot cũ thất bại.

### 15.2. ABA không phải vấn đề ở mọi ứng dụng

Nếu nghiệp vụ chỉ quan tâm **giá trị hiện tại**, A->B->A có thể hoàn toàn hợp lệ. ABA đáng lo khi thuật toán dựa trên giả định "nếu giá trị vẫn như cũ thì cấu trúc không bị thay đổi", thường gặp ở một số data structure không khóa.

Stamp có thể tràn số sau rất nhiều lần tăng; giải pháp dùng stamp cũng phải phù hợp với quy mô, vòng đời và bảo đảm cần thiết. Không nên áp dụng `AtomicStampedReference` cho mọi boolean hoặc số đếm chỉ vì nó có thêm thông tin phiên bản.

## 16. Lock-free, wait-free và blocking khác nhau thế nào?

Thuật ngữ "*không khóa*" dễ bị sử dụng quá rộng.

| Thuật ngữ | Ý nghĩa thực hành |
|---|---|
| **Blocking** | Thread có thể phải chờ lock/monitor hoặc điều kiện để tiếp tục |
| **Lock-free** | Thuật toán có bảo đảm tiến triển toàn cục: nếu các thread tiếp tục thực thi, hệ thống vẫn có tiến triển, dù một thread riêng có thể bị lặp lại thất bại |
| **Wait-free** | Mỗi thao tác của một thread hoàn thành sau số bước hữu hạn có giới hạn phù hợp, không phụ thuộc tiến triển của thread khác |
| **Obstruction-free** | Một thao tác có thể hoàn tất nếu chạy riêng đủ lâu, không bị thread khác cản trở |

Một vòng lặp CAS có thể liên tục thất bại cho **một thread** dưới tranh chấp. Vì vậy **lock-free không đồng nghĩa không bao giờ phải chờ**, và cũng không tự động bảo đảm fairness hoặc latency theo từng thread.

### 16.1. Có CAS không có nghĩa mọi thuật toán đều lock-free

Để khẳng định một cấu trúc dữ liệu là lock-free, cần lập luận về **toàn bộ thuật toán**: đường đi xử lý, quản lý bộ nhớ, retry, điều kiện chờ và sự phụ thuộc vào thành phần khác.

Ví dụ, đặt `synchronized` quanh một thao tác `compareAndSet` không biến method tổng thể thành lock-free. Tương tự, một vòng lặp CAS có thể chờ một cờ do thread khác chỉ cập nhật khi nhận lock; lúc đó progress guarantee cần được xem xét lại.

### 16.2. Không dùng spin loop cho mọi nhu cầu chờ

`Thread.onSpinWait()` chỉ là một *hint* cho runtime/processor khi ứng dụng chủ động spin. Nó không nhường quyền điều khiển một cách chắc chắn, không ngủ và không bảo đảm tiến triển.

Khi thread phải chờ hàng mili giây, giây hoặc chờ I/O, các cơ chế blocking/parking hợp lý thường tiết kiệm CPU hơn spin. Virtual threads hiện hành giúp giảm chi phí thread ở một số mô hình blocking, nhưng không thay đổi các quy tắc JMM.

## 17. Atomic operation và linearizability

Một số API atomic cung cấp hành vi có thể xem như thao tác xảy ra tại **một điểm logic** trong khoảng thực thi lời gọi (*linearization point*). Đây là nền tảng để lập luận về thứ tự quan sát của các thao tác trên cùng một biến atomic.

Ví dụ:

```java
AtomicInteger counter = new AtomicInteger();

int a = counter.incrementAndGet();
int b = counter.incrementAndGet();
```

Với hai thread, thứ tự ai nhận giá trị 1 hoặc 2 phụ thuộc lịch chạy, nhưng hai lần tăng thành công trên cùng biến atomic không bị mất cập nhật.

**Không nên suy rộng**: hai biến atomic riêng biệt không tự trở thành **một transaction**.

```java
AtomicInteger width = new AtomicInteger(10);
AtomicInteger height = new AtomicInteger(20);

width.set(30);
height.set(40);
```

Một reader khác có thể thấy cặp `(30, 20)` ở giữa hai lần cập nhật, dù mỗi `set` riêng lẻ có ngữ nghĩa atomic.

Nếu cần cập nhật cặp dữ liệu một cách nhất quán, cân nhắc **immutable snapshot + AtomicReference CAS** (mục 10) hoặc `synchronized`/`Lock` theo đúng bất biến nghiệp vụ.

## 18. Khi nào chọn volatile, atomic, lock hoặc concurrent collection?

| Bài toán | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Một thread công bố cờ, các thread khác quan sát | `volatile boolean` | Visibility/order với một trạng thái đơn giản |
| Nhiều thread cần tranh quyền thay đổi cờ một lần | `AtomicBoolean.compareAndSet` | Chuyển trạng thái theo điều kiện, nguyên tử |
| Số đếm có cập nhật cần kết quả chính xác | `AtomicInteger` / `AtomicLong` | Increment/CAS nguyên tử |
| Số đếm metrics tần suất cập nhật cao | `LongAdder` | Tối ưu tranh chấp, chấp nhận sum không atomic snapshot |
| Nhiều trường phải giữ bất biến đồng thời | `AtomicReference<ImmutableState>` hoặc lock | Thay toàn bộ trạng thái trong một bước |
| Nhiều thao tác cần rollback/điều kiện phức tạp | `synchronized` hoặc `Lock` | Vùng critical section rõ ràng |
| Bản đồ dùng chung nhiều thread | `ConcurrentHashMap` | Cung cấp thao tác/contract concurrent theo key |
| Hàng đợi công việc giữa producer/consumer | `BlockingQueue` hoặc queue concurrent phù hợp | Thể hiện cơ chế giao tiếp và chờ đợi |
| Cấu trúc dữ liệu low-level với memory ordering chuyên biệt | `VarHandle` | Cần kiểm soát access modes, review chặt |

**Ưu tiên abstraction cao nhất mô tả đúng contract.** Không nên tự viết một queue dùng CAS chỉ để tránh `synchronized` trong khi JDK đã có cấu trúc đồng thời phù hợp.

## 19. Vì sao lock đôi khi đúng hơn CAS?

CAS hiệu quả cho một trạng thái có thể biểu diễn bằng một giá trị hoặc một snapshot bất biến. Nhưng khi transaction cần:

- Cập nhật nhiều đối tượng khác nhau.
- Kiểm soát tài nguyên bên ngoài (file, database, HTTP).
- Tính toán nhiều bước có thể ném lỗi cần rollback.
- Thiết lập invariant phức tạp trên nhiều cấu trúc mutable.
- Áp dụng điều kiện chờ rõ nghĩa thay vì retry liên tục.

... thì một vùng critical section hoặc thiết kế giao dịch có thể **dễ chứng minh đúng và dễ bảo trì hơn**.

Ví dụ một critical section ngắn:

```java
final class TwoBalances {
    private long first = 100;
    private long second = 200;

    synchronized void transfer(long amount) {
        if (amount < 0 || amount > first) {
            throw new IllegalArgumentException("Invalid amount");
        }

        long nextFirst = Math.subtractExact(first, amount);
        long nextSecond = Math.addExact(second, amount);

        first = nextFirst;
        second = nextSecond;
    }

    synchronized long total() {
        return Math.addExact(first, second);
    }
}
```

Với mọi truy cập đến các field này được bảo vệ bởi **cùng monitor**, hai giá trị được cập nhật nhất quán. Ví dụ cho thấy "có khóa" không phải anti-pattern; điều quan trọng là phạm vi khóa hợp lý và contract rõ ràng.

Trong thực tế cần tránh giữ lock khi gọi network hoặc thực hiện tác vụ chậm không kiểm soát, và phải quan tâm thứ tự khóa để giảm nguy cơ deadlock.

## 20. Contention, retry và những giới hạn hiệu năng

**Contention** xảy ra khi nhiều thread tranh cùng một vùng trạng thái. Với CAS:

1. Nhiều thread đọc cùng snapshot.
2. Một thread cập nhật thành công.
3. Các thread khác thử cập nhật với snapshot cũ, CAS thất bại.
4. Những thread đó phải đọc lại và tính lại.

Nếu tranh chấp cao, rất nhiều vòng retry có thể làm giảm throughput. Atomic không tự động nhanh hơn lock ở mọi trường hợp.

### 20.1. False sharing

Hai biến độc lập có thể nằm gần nhau trên cùng cache line, khiến các core thường xuyên làm mất hiệu lực dữ liệu cache của nhau dù các thread không cùng sửa một biến logic. Hiện tượng này được gọi là **false sharing**.

Không nên dùng tùy chọn JVM nội bộ hoặc annotation không được hỗ trợ công khai như một cách tối ưu mặc định. Trước tiên hãy đo workload và chọn cấu trúc dữ liệu/partitioning phù hợp.

### 20.2. Khi LongAdder có thể tốt hơn

Với counter dùng cho thống kê:

```java
LongAdder processed = new LongAdder();

processed.increment();
```

Nhiều thread có thể giảm mức tranh chấp trên một điểm chung nhờ cách `LongAdder` phân bổ việc cộng dồn. Nhưng nếu cần CAS để giới hạn số request đang chạy không vượt 100, `AtomicInteger` hoặc semaphore phù hợp hơn vì `LongAdder.sum()` không tạo một snapshot nguyên tử đủ để quyết định điều kiện tranh quyền.

### 20.3. Đừng benchmark bằng một lần chạy

Kết quả có thể phụ thuộc số core, số thread, JIT, garbage collector, phân phối contention và thời gian warm-up. Khi hiệu suất quan trọng, sử dụng benchmark có thiết kế phù hợp, ví dụ JMH, và đo với workload đại diện.

## 21. Kiểm thử concurrent code

### 21.1. Kiểm tra bất biến, không chỉ kiểm tra log

Với `AtomicCounterDemo`, điều quan trọng là invariant sau khi tất cả thread đã hoàn tất:

```java
int expected = THREADS * INCREMENTS_PER_THREAD;

if (counters.atomicCount.get() != expected) {
    throw new AssertionError("Atomic counter lost updates");
}
```

Còn `volatileCount == expected` ở một lần chạy không chứng minh an toàn.

### 21.2. CountDownLatch thay cho sleep để điều phối thử nghiệm

`CountDownLatch` cho phép các worker chờ chung một điểm xuất phát. Nó không tạo ra mọi lịch xen kẽ có thể xảy ra, nhưng thường tốt hơn đặt `Thread.sleep` với hy vọng race sẽ lộ ra.

### 21.3. Thử tình huống lỗi và contention

Bộ kiểm thử có thể bao gồm:

- Nhiều worker cập nhật cùng atomic counter.
- `CAS` thất bại do cập nhật cạnh tranh.
- Kiểm tra giới hạn/overflow khi cộng.
- Thử immutable state với nhiều thread và xác minh invariant.
- Kiểm tra hành vi khi thread bị interrupt trong phần chờ.
- Kiểm thử trạng thái ABA nếu thuật toán yêu cầu nhận diện thay đổi trung gian.
- Đánh giá throughput/latency dưới mức contention thấp và cao.

### 21.4. Stress test không thay thế lập luận JMM

Ngay cả khi chạy hàng triệu lần mà không thấy data race, điều đó không chứng minh chương trình đúng trên mọi JVM/hardware. Với cấu trúc lock-free tinh vi, nên sử dụng công cụ kiểm thử chuyên biệt cho các kết quả bộ nhớ hợp lệ (ví dụ JCStress) và kiểm tra lại các quy tắc JMM, đồng thời review thuật toán.

Bài này chỉ cung cấp nền tảng và ví dụ; không thực hiện vòng Content QA/refactor chuyên môn của các bước khác trong quy trình nội dung.

## 22. Các lỗi phổ biến cần tránh

| Hiểu lầm hoặc lỗi | Vấn đề | Cách xử lý |
|---|---|---|
| `volatile int count; count++;` an toàn | `++` là read-modify-write, có thể mất cập nhật | `AtomicInteger.incrementAndGet()` hoặc lock |
| `volatile List<T>` làm List thread-safe | Chỉ tham chiếu là volatile | Concurrent collection, lock hoặc immutable state |
| Hai biến atomic tạo thành một transaction | Reader vẫn có thể thấy cặp giá trị trung gian | AtomicReference của snapshot hoặc lock |
| Dùng `sleep()` để công bố dữ liệu | Sleep không tạo HB cần thiết | Volatile/lock/latch/queue đúng contract |
| Dùng `ready()` hoặc busy-wait vô hạn cho mọi tình huống | Tiêu thụ CPU hoặc treo không có timeout | Blocking primitive/cancellation |
| Ghi email/log trong `updateAndGet` | Function có thể được thực thi lại sau CAS thất bại | Để function thuần, side effect sau commit |
| `AtomicReference<List>` bảo vệ mọi `add` | Nội dung List mutable vẫn bị race | Immutable copy hoặc concurrent collection |
| So sánh `AtomicReference.compareAndSet` theo `equals` | CAS dùng so sánh identity tham chiếu | Dùng snapshot tham chiếu thật hoặc loại trạng thái phù hợp |
| `LongAdder.sum()` là atomic snapshot khi đang ghi | Có thể không phản ánh toàn bộ updates đồng thời | AtomicLong hoặc cơ chế snapshot |
| `LongAdder.sumThenReset()` chốt sổ nguyên tử với writer | Không cung cấp transaction reset toàn cục khi đang cập nhật | Phối hợp writers hoặc thiết kế khác |
| Gắn nhãn mọi vòng CAS là wait-free | Có thể retry không giới hạn | Đánh giá progress guarantee toàn thuật toán |
| `Thread.onSpinWait()` đồng nghĩa thread sẽ ngủ | Chỉ là hint, không bảo đảm nhường CPU | Dùng cơ chế chờ hợp lý |
| CAS thành công nghĩa không từng có thay đổi trung gian | ABA có thể xảy ra | Dùng stamp/version khi contract cần |
| `AtomicInteger` tự báo integer overflow | Các phép số học có thể wrap | `Math.addExact` bên trong cập nhật |
| Chọn VarHandle opaque/acquire theo cảm tính | Mỗi mode có bảo đảm bộ nhớ khác nhau | Dùng atomic/volatile mặc định, review JMM trước khi tối ưu |
| Virtual thread tự loại bỏ data race | Cùng các quy tắc đồng bộ dữ liệu chia sẻ | Thiết kế thread-safety như thường |
| Chỉ thử nghiệm một lần thấy đúng là đủ | Race có thể không tái hiện | Invariants, stress, JCStress, reasoning |

## 23. Bài tập thực hành

### Bài 1. Phân biệt visibility và atomicity

Viết class chứa `volatile int count` và 4 thread, mỗi thread tăng 10.000 lần. In kết quả sau khi `join` và giải thích tại sao phép tăng có thể thất bại dù mọi lần đọc/ghi đều là volatile.

### Bài 2. Safe publication bằng volatile

Viết một publisher gán `message` rồi đặt `volatile boolean ready = true`. Viết consumer đợi cờ và đọc message. Xác định quan hệ happens-before chính, rồi thay busy loop bằng `CountDownLatch` để tránh dùng CPU liên tục.

### Bài 3. AtomicInteger có giới hạn

Tạo một counter tối đa 100. Viết `tryIncrement()` bằng CAS loop và bảo đảm không bao giờ vượt 100 khi 10 thread cùng gọi. Kiểm tra invariant và giải thích vì sao không dùng `if (counter.get() < 100) counter.incrementAndGet()`.

### Bài 4. AtomicReference với record bất biến

Thiết kế record `Inventory(int version, int available)`, cập nhật qua `AtomicReference` sao cho không thể trừ kho quá số lượng còn lại. Dùng CAS để toàn bộ snapshot được thay nguyên tử. Kiểm tra nhiều thread cùng đặt hàng.

### Bài 5. Side effect trong updateAndGet

Viết một `AtomicInteger.updateAndGet` trong đó lambda tăng một counter bên ngoài. Giải thích vì sao count side effect không nhất thiết tương ứng với số lần CAS thành công và sửa lại theo cách an toàn hơn.

### Bài 6. LongAdder hay AtomicLong?

Chọn kiểu phù hợp cho hai tình huống: bộ đếm page view cho dashboard có cập nhật rất nhiều, và counter giới hạn tối đa 500 công việc đang chạy. Nêu hạn chế của `sum` khi có cập nhật đồng thời.

### Bài 7. ABA

Dùng enum `A, B, C` và `AtomicStampedReference` để minh họa lịch `A -> B -> A`, sau đó thử CAS với stamp cũ. Giải thích khi nào cần stamp và khi nào nó chỉ làm phức tạp không cần thiết.

### Bài 8. VarHandle

Tạo class dùng `VarHandle` cho `ready` và `payload`. Viết publisher theo thứ tự gán payload trước, `setRelease` cho ready sau; consumer dùng `getAcquire`. So sánh cách này với `volatile` và mô tả rủi ro nếu đọc cờ bằng chế độ plain mà không có đồng bộ khác.

### Bài 9. Phân tích thuật toán lock-free

Cho một CAS loop cập nhật counter, xác định lý do retry có thể nhiều lần. Tìm điều kiện để nói về progress toàn hệ thống và giải thích vì sao không thể mặc nhiên khẳng định *wait-free*.

### Bài 10. Lựa chọn thiết kế

Bạn xây hệ thống xử lý thanh toán với nhiều field: trạng thái, số tiền, mã giao dịch, thời gian xác nhận. Có nên đặt tất cả các field thành atomic riêng? Đề xuất immutable snapshot/CAS, lock hoặc transaction database phù hợp; giải thích ranh giới giữa bảo đảm trong RAM và bảo đảm của hệ thống bên ngoài.

## 24. Tóm tắt

**`volatile`** là công cụ cho visibility và ordering. Khi một thread công bố dữ liệu trước volatile write và thread khác quan sát volatile read tương ứng, JMM cung cấp quan hệ happens-before cần thiết. Nhưng `volatile` không biến `counter++` hoặc chuỗi nhiều thao tác thành cập nhật nguyên tử.

**`AtomicInteger`, `AtomicLong`, `AtomicBoolean` và `AtomicReference`** cung cấp các phép đọc/ghi/cập nhật nguyên tử theo hợp đồng. CAS cho phép thử cập nhật có điều kiện và retry khi có tranh chấp. Với trạng thái nhiều trường, nên thay một snapshot bất biến bằng `AtomicReference` hoặc dùng lock khi tính nhất quán đòi hỏi.

**`LongAdder`** phù hợp với bộ đếm thống kê có tranh chấp cao nhưng `sum()` không phải atomic snapshot khi đang cập nhật. **`VarHandle`** cung cấp các access mode cấp thấp; chỉ nên dùng khi hiểu rõ các bảo đảm bộ nhớ. **ABA** nhắc rằng giá trị quay về như cũ không nhất thiết có nghĩa chưa từng thay đổi.

Lập trình không khóa không tự động nhanh hơn, dễ bảo trì hơn hoặc bảo đảm từng thread sẽ hoàn thành trong thời gian hữu hạn. Trong Java 27, hãy **chọn primitive phù hợp với invariant và mục tiêu tiến triển**, ưu tiên cấu trúc đồng thời đã được JDK cung cấp, kiểm thử và lập luận dựa trên Java Memory Model thay vì hy vọng race sẽ không xuất hiện.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — Section 17.4: Memory Model](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-17.html#jls-17.4)
- [Java SE 27 API — java.util.concurrent.atomic package](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/package-summary.html)
- [Java SE 27 API — AtomicInteger](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)
- [Java SE 27 API — AtomicReference](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html)
- [Java SE 27 API — AtomicBoolean](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html)
- [Java SE 27 API — LongAdder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html)
- [Java SE 27 API — AtomicStampedReference](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html)
- [Java SE 27 API — VarHandle](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Java SE 27 API — CountDownLatch](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java SE 27 API — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
