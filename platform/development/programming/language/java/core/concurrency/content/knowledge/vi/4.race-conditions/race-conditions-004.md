# Read-modify-write không phải một thao tác atomic trong Java

> **Ý chính:** Các biểu thức `counter++`, `counter += 1` hay `counter = counter + 1` trông như một câu lệnh nhưng thực chất cần **đọc giá trị hiện tại → tính giá trị mới → ghi trả lại**. Khi nhiều thread cùng cập nhật một trạng thái chia sẻ mà không bảo vệ **toàn bộ chuỗi thao tác**, một cập nhật có thể bị mất (*lost update*). `volatile` giúp về visibility và ordering, nhưng **không biến phép tăng gồm nhiều bước thành atomic**.

Bài học thuộc nhóm **Race Conditions** trong Java concurrency nói chung. Các ví dụ sử dụng Java SE (Java 17+), `Thread`, `synchronized` và `java.util.concurrent`; không xét cơ chế của Spring.

## 1. Atomic nghĩa là gì trong tình huống này?

Một thao tác atomic, đối với các thread cùng quan sát trạng thái liên quan, có hiệu ứng như thể nó diễn ra **trọn vẹn ở một thời điểm logic**; các thread khác không quan sát trạng thái trung gian của chính thao tác đó. Khi nói một cập nhật kiểu read-modify-write (RMW) là atomic, ta muốn việc **đọc và ghi dựa trên giá trị đã đọc** là một đơn vị không thể bị một phép cập nhật cạnh tranh chen vào làm mất hiệu lực.

Ví dụ cần tăng biến đếm chung từ `7` lên `8`:

~~~text
1. READ:   old = counter    // old = 7
2. MODIFY: next = old + 1   // next = 8
3. WRITE:  counter = next   // counter = 8
~~~

Một thread đơn lẻ có thể làm đúng. Nhưng hai thread cùng làm những bước này mà không có đồng bộ thì lịch xen kẽ có thể khiến **cả hai đọc cùng một giá trị cũ** và cùng ghi kết quả giống nhau.

Phân biệt những điều thường bị gộp nhầm:

| Thuộc tính | Câu hỏi | Có bảo đảm RMW atomic không? |
| --- | --- | --- |
| **Atomic read/write riêng lẻ** | Một lần đọc/ghi một giá trị có bị đọc nửa chừng không? | **Không đủ.** Đọc và ghi vẫn là hai thời điểm. |
| **Visibility** | Thread khác có thấy thay đổi đã được công bố không? | **Không đủ.** Thấy giá trị mới không ngăn hai thread cùng đọc giá trị cũ. |
| **Ordering / happens-before** | Những hành động nào phải được quan sát theo trật tự nhất định? | **Không tự bảo đảm** toàn bộ phép RMW là một khối duy nhất. |
| **Atomic RMW** | Một cập nhật cạnh tranh có thể chen giữa phần đọc và phần ghi không? | **Có**, đây chính là bảo đảm cần để tránh lost update đối với một counter. |
| **Transaction nhiều biến** | Nhiều trường có được cập nhật như một invariant duy nhất không? | Một atomic counter **không đủ**; phải bảo vệ toàn bộ invariant. |

Từ “atomic” luôn phải đi kèm **phạm vi**: atomic cho một biến, một entry map, hay một cập nhật trên nhiều trường? Một thao tác có thể atomic trong phạm vi hẹp nhưng không atomic đối với logic nghiệp vụ lớn hơn.

## 2. Race condition và lost update diễn ra như thế nào?

Giả sử `counter = 7`, hai thread A và B đồng thời thực hiện `counter++`:

| Bước thời gian | Thread A | Thread B | Giá trị chung |
| --- | --- | --- | --- |
| 1 | Đọc `counter`, nhận `7` | | `7` |
| 2 | | Đọc `counter`, nhận `7` | `7` |
| 3 | Tính `7 + 1 = 8` | | `7` |
| 4 | | Tính `7 + 1 = 8` | `7` |
| 5 | Ghi `8` | | `8` |
| 6 | | Ghi `8` | `8` |

Sau **hai lần tăng**, kết quả mong đợi là `9` nhưng thực tế có thể là `8`. Một cập nhật đã bị mất: lần ghi sau dựa trên một snapshot cũ và không tính đến cập nhật đã xảy ra.

Đây là **lost-update race** trên dữ liệu dùng chung, không phải lỗi do thread nào “chạy quá nhanh”, cũng không liên quan đến thứ tự ưu tiên scheduling. Thêm `Thread.sleep` chỉ thay đổi cơ hội xen kẽ; không chữa nguyên nhân.

Các biểu thức dưới đây đều là read-modify-write đối với biến `int` chia sẻ:

~~~java
counter++;
++counter;
counter += 1;
counter = counter + 1;
~~~

Với `counter++` và `++counter`, giá trị trả về của biểu thức khác nhau (giá trị cũ so với giá trị mới), **nhưng cả hai đều cần RMW**. Trong mã Java, “một câu lệnh”, “một toán tử” hay “một dòng source” không đồng nghĩa “một thao tác atomic”. Bytecode, JIT và CPU có thể triển khai khác nhau; điều phải dựa vào là **hợp đồng Java Memory Model/API**, không phải suy luận máy móc từ số lệnh assembly hay bytecode.

### Race condition khác data race như thế nào?

- **Race condition**: kết quả hoặc tính đúng đắn phụ thuộc vào cách các sự kiện đồng thời xen kẽ; lost update là ví dụ điển hình.
- **Data race** trong ngôn ngữ Java Memory Model nói về các truy cập xung đột trên cùng biến mà không được sắp xếp bằng quan hệ *happens-before* thích hợp, khi ít nhất một truy cập là ghi và các truy cập không thuộc loại được đồng bộ như `volatile`. 
- Một thiết kế có thể mắc **race condition logic dù không có data race trên từng truy cập**. Ví dụ dùng `volatile int` khiến các lần đọc/ghi riêng lẻ có ngữ nghĩa đồng bộ, nhưng việc tách đọc rồi ghi vẫn cho phép lost update. Vì thế “đã hết data race” và “thuật toán đúng” là hai nhận định khác nhau.

## 3. Ví dụ 1 — tái hiện lost update một cách xác định

Thay vì chạy vòng lặp tăng counter hàng triệu lần rồi hy vọng race xuất hiện, ta **chủ động đồng bộ điểm xen kẽ** để cả hai thread đều đọc giá trị cũ trước khi một trong hai được phép ghi.

Tạo tệp `LostUpdate.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;

public class LostUpdate {
    private static volatile int counter = 0;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothHaveRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            int oldValue = counter;  // READ: cả hai sẽ đọc 0.
            bothHaveRead.countDown();

            try {
                allowWrite.await();  // Đợi đến khi cả hai đã đọc.
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            counter = oldValue + 1;  // WRITE: cả hai ghi 1.
        };

        Thread first = new Thread(increment, "first");
        Thread second = new Thread(increment, "second");

        first.start();
        second.start();

        bothHaveRead.await();  // Chắc chắn cả hai đã lấy snapshot.
        allowWrite.countDown();

        first.join();
        second.join();

        System.out.println("expected = 2");
        System.out.println("actual = " + counter);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LostUpdate.java
java LostUpdate
~~~

Kết quả khi không có interruption bên ngoài:

~~~text
expected = 2
actual = 1
~~~

**Giải thích bảo đảm:**

1. Mỗi worker đọc `counter` vào biến local `oldValue`, rồi giảm latch `bothHaveRead`.
2. Main đợi `bothHaveRead.await()` hoàn tất, tức cả hai đã đọc trước khi main gọi `allowWrite.countDown()`.
3. Khi được phép ghi, mỗi worker đều ghi `0 + 1`. Hai lần ghi cùng giá trị khiến kết quả cuối là `1`, bất kể thứ tự hai lần ghi.
4. Main `join()` cả hai thread trước khi in, bảo đảm các phép ghi đã hoàn tất và các hiệu ứng từ worker có quan hệ *happens-before* thích hợp với phần quan sát sau `join()`.

Việc đặt `volatile` ở `counter` là **cố ý**: ngay cả khi mỗi lần đọc/ghi có ngữ nghĩa visibility phù hợp của volatile, hai bước `READ` và `WRITE` vẫn tách biệt, không tạo một cập nhật atomic. Bản thân `CountDownLatch` ở ví dụ dùng để **ép lịch xen kẽ nhằm chứng minh lỗi**, không tự sửa lost update. Trong phiên bản thực tế khi muốn tăng nguyên tử, đừng tách một phép tính thành hai thời điểm mà không bảo vệ chúng.

## 4. `volatile` bảo đảm gì, và không bảo đảm gì?

Trong Java, `volatile` tạo ra các bảo đảm về **visibility và ordering** cho truy cập đến biến được khai báo volatile. Đặc biệt, một lần ghi volatile có quan hệ *synchronizes-with* các lần đọc tiếp theo của cùng biến volatile theo quy tắc Java Memory Model. Các lần truy cập volatile được xét trong trật tự đồng bộ phù hợp, và những read/write volatile riêng lẻ có ngữ nghĩa atomic trên giá trị được truy cập.

Tuy nhiên:

~~~java
// Minh họa lỗi logic, không phải chương trình độc lập.
private static volatile int counter = 0;

static void increment() {
    counter++; // Đọc volatile -> cộng 1 -> ghi volatile.
}
~~~

Đoạn này **vẫn có thể lost update**. `volatile` không khóa các thread khác trong khoảng giữa đọc và ghi, không thay cho `synchronized`, `Lock` hoặc phương thức atomic RMW như `AtomicInteger.incrementAndGet()`.

Đừng nhầm những trường hợp khác:

- `volatile boolean stopped` có thể là cờ báo dừng đơn giản khi một thread ghi và các thread khác đọc, nếu logic chỉ yêu cầu publish/observe cờ.
- `volatile int counter` với **nhiều writer** dùng `counter++` không bảo vệ đủ cập nhật.
- Đọc một `volatile long` là atomic ở mức **một lần read**; vẫn không khiến `value++` atomic.
- `final` và khả năng công bố an toàn đối tượng thuộc cơ chế khác; chúng không tự biến phép tăng trên trạng thái mutable thành atomic.

Khi phân tích concurrency, hỏi hai câu riêng: “Thread có thấy giá trị đúng/được công bố chưa?” và “Có thể ai đó cập nhật ở giữa read và write không?”. `volatile` giải quyết được một số vấn đề của câu thứ nhất, không giải quyết câu thứ hai.

## 5. Cách sửa 1 — khóa toàn bộ read-modify-write bằng `synchronized`

Một monitor lock chung giúp chỉ một thread tại một thời điểm đi qua critical section được bảo vệ bởi **cùng khóa**. Với counter, đặt phép đọc, tính và ghi trong cùng một khối khóa.

Tạo `SynchronizedCounter.java` (Java 17+):

~~~java
public class SynchronizedCounter {
    private static final Object LOCK = new Object();
    private static int counter = 0;

    private static void increment() {
        synchronized (LOCK) {
            counter++;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Runnable work = () -> {
            for (int i = 0; i < 100_000; i++) {
                increment();
            }
        };

        Thread first = new Thread(work, "first");
        Thread second = new Thread(work, "second");
        first.start();
        second.start();

        first.join();
        second.join();
        System.out.println("counter = " + counter);
    }
}
~~~

Chạy:

~~~bash
javac SynchronizedCounter.java
java SynchronizedCounter
~~~

Kết quả:

~~~text
counter = 200000
~~~

Lý do đúng:

- Mỗi lần `increment()` lấy **cùng** `LOCK` nên hai thread không thể cùng thực hiện phần RMW tại một thời điểm.
- Monitor unlock có quan hệ *happens-before* với lần lock tiếp theo cùng monitor, cho phép thread vào sau quan sát cập nhật từ thread trước.
- `join()` bảo đảm main đợi đủ 200.000 lần gọi `increment()` trước khi đọc/in kết quả.
- Biến `counter` không bắt buộc là `volatile` nếu **mọi truy cập cạnh tranh** đều theo cùng nguyên tắc đồng bộ và đọc kết quả được điều phối đúng như ở đây.

Dùng **khóa đúng và nhất quán** rất quan trọng. Khóa ở từng thread bằng một `new Object()` khác nhau là vô ích. Nếu một đoạn ghi sử dụng `synchronized(LOCK)` nhưng đoạn đọc/ghi cạnh tranh khác truy cập trần vào `counter`, thiết kế vẫn có thể sai. Nên để trường chia sẻ là `private` và đóng gói đường cập nhật trong một API rõ ràng.

### Khi nào dùng `ReentrantLock`?

`java.util.concurrent.locks.ReentrantLock` cũng có thể bảo vệ toàn bộ RMW, hữu ích nếu cần `tryLock`, khóa có timeout, interruptible lock acquisition hoặc điều kiện `Condition`. Mẫu đúng:

~~~java
// Ví dụ minh họa; lock là một ReentrantLock dùng chung.
lock.lock();
try {
    counter++;
} finally {
    lock.unlock();
}
~~~

Không chỉ khóa phần `counter = ...` sau khi đã đọc outside lock; **đọc để tính giá trị mới cũng phải nằm trong cùng critical section**. `finally` bảo đảm release lock ngay cả khi công việc bên trong ném exception.

## 6. Cách sửa 2 — dùng atomic read-modify-write từ `AtomicInteger`

Khi chỉ cần thao tác atomic trên **một biến đếm**, `AtomicInteger` thường diễn đạt ý định rõ ràng hơn so với một monitor dành riêng cho counter. Các phương thức quan trọng:

| API | Hiệu ứng atomic | Giá trị trả về |
| --- | --- | --- |
| `getAndIncrement()` | Tăng 1 | Giá trị **trước khi** tăng |
| `incrementAndGet()` | Tăng 1 | Giá trị **sau khi** tăng |
| `getAndAdd(delta)` | Cộng `delta` | Giá trị cũ |
| `addAndGet(delta)` | Cộng `delta` | Giá trị mới |
| `compareAndSet(expected, update)` | Chỉ ghi `update` nếu giá trị hiện tại bằng `expected` | `true` khi cập nhật thành công |
| `updateAndGet(operator)` | Dùng hàm biến đổi, tự thử lại nếu có cạnh tranh | Giá trị mới |

Tạo `AtomicCounter.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounter {
    private static final AtomicInteger counter = new AtomicInteger();

    public static void main(String[] args) throws InterruptedException {
        Runnable work = () -> {
            for (int i = 0; i < 100_000; i++) {
                counter.incrementAndGet();
            }
        };

        Thread first = new Thread(work, "first");
        Thread second = new Thread(work, "second");
        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("counter = " + counter.get());
    }
}
~~~

Chạy:

~~~bash
javac AtomicCounter.java
java AtomicCounter
~~~

Kết quả:

~~~text
counter = 200000
~~~

`incrementAndGet()` bảo vệ một cập nhật RMW trên **chính giá trị của đối tượng atomic đó**. Khi nhiều thread gọi, cập nhật trên biến atomic không bị ghi đè mất theo tình huống cả hai cùng lấy một snapshot cũ rồi ghi lại thiếu kiểm tra.

**Điểm dễ sai:** đọc bằng `counter.get()` rồi tự tính và gọi `counter.set(...)` là **hai operation riêng**, không phải RMW atomic:

~~~java
// Sai nếu nhiều writer cạnh tranh:
int oldValue = counter.get();
counter.set(oldValue + 1);
~~~

Dù `get()` và `set()` từng cái có ngữ nghĩa thread-safe, tổ hợp trên vẫn có cửa sổ giữa chúng. Phải dùng **đúng phương thức atomic RMW**, chẳng hạn `incrementAndGet()` hoặc `compareAndSet(...)` trong vòng lặp phù hợp.

## 7. CAS: làm rõ cách atomic cập nhật khi giá trị có thể thay đổi

**Compare-and-set (CAS)** kiểm tra một giá trị kỳ vọng và chỉ thay đổi khi nó vẫn khớp, trong một thao tác atomic. Mô hình:

~~~text
current = atomic.get()
next    = f(current)
if atomic.compareAndSet(current, next):
    cập nhật thành công
else:
    giá trị đã thay đổi hoặc phép CAS thất bại
    -> đọc lại và thử tính từ trạng thái mới
~~~

Tạo `CasCounter.java` (Java 17+):

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class CasCounter {
    private static final AtomicInteger counter = new AtomicInteger();

    private static void incrementWithCas() {
        while (true) {
            int previous = counter.get();
            int updated = previous + 1;
            if (counter.compareAndSet(previous, updated)) {
                return;
            }
            // Có cạnh tranh: thử lại với giá trị hiện thời.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Runnable work = () -> {
            for (int i = 0; i < 100_000; i++) {
                incrementWithCas();
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("counter = " + counter.get());
    }
}
~~~

Chạy:

~~~bash
javac CasCounter.java
java CasCounter
~~~

Kết quả:

~~~text
counter = 200000
~~~

Phương thức `compareAndSet(previous, updated)` không cho phép ghi dựa trên một giá trị đã cũ mà không kiểm tra lại. Khi một thread khác thay đổi counter giữa `get` và CAS, CAS thất bại và vòng lặp phải tính lại từ trạng thái hiện thời. Kết quả chính xác kể cả khi lịch chạy xen kẽ bất kỳ, miễn các thread hoàn thành.

### Lưu ý khi dùng `updateAndGet()` hoặc CAS loop

~~~java
int newValue = counter.updateAndGet(current -> current + 1);
~~~

Đây là cách ngắn gọn để diễn đạt biến đổi atomic. Tuy nhiên, hàm update **có thể được áp dụng nhiều lần** vì thư viện phải retry khi bị cạnh tranh. Do đó:

- Hàm update nên **thuần (pure)**, không tạo side effect bên ngoài như ghi cơ sở dữ liệu, gửi thông báo, cộng một counter khác hay ghi log mà bạn kỳ vọng chỉ thực hiện đúng một lần.
- Không đọc trạng thái mutable bên ngoài mà thiếu nhất quán rồi kỳ vọng CAS trên một biến bảo vệ luôn dữ liệu ngoài biến đó.
- Không biến một vòng CAS có thể retry thành giao thức nhiều tài nguyên khi chưa thiết kế cơ chế đồng bộ chung.
- Nếu có yêu cầu tuyệt đối về thứ tự hoạt động bên ngoài, cần điều phối riêng; atomic trên một biến không tự đảm bảo *exactly-once* cho các side effect.

**CAS không đồng nghĩa mọi thuật toán CAS đều đơn giản hoặc hoàn toàn không có vấn đề cạnh tranh.** Với các cấu trúc trạng thái phức tạp, còn có vấn đề như ABA (giá trị đi A → B → A khiến CAS đơn thuần không nhận biết sự thay đổi trung gian), retry nhiều dưới contention, starvation và yêu cầu công bố trạng thái đúng. Với phép tăng counter `int` đơn giản, `AtomicInteger.incrementAndGet()` thường là lựa chọn dễ đọc hơn tự viết loop.

## 8. Atomic một biến không đủ cho invariant nhiều biến

Giả sử tài khoản có hai số `debit` và `credit` cần được cập nhật cùng nhau để bảo đảm invariant tổng số bằng 0. Dùng hai `AtomicInteger` riêng rồi làm:

~~~java
// Chỉ minh họa tình huống sai về tính nguyên tử của invariant.
debit.addAndGet(10);
credit.addAndGet(-10);
~~~

Từng phép cập nhật có thể atomic riêng, nhưng thread khác vẫn có thể quan sát trạng thái **ở giữa hai phép**. Nếu logic yêu cầu cả hai thay đổi như **một transaction nhất quán**, hãy bảo vệ bằng cùng một `synchronized`/`Lock`, hoặc biểu diễn toàn bộ trạng thái bằng một đối tượng immutable và thay thế thông qua `AtomicReference<State>` với CAS toàn bộ state.

Ví dụ nếu muốn giữ invariant `debit + credit == 0` trong một snapshot:

~~~java
// Minh họa kiểu dữ liệu cho một state bất biến.
record BalanceState(int debit, int credit) {}
~~~

Một `AtomicReference<BalanceState>` có thể giữ một phiên bản trạng thái nhất quán và cập nhật cả hai trường trong một CAS nếu tính toán đúng và retry từ state mới. Không đủ nếu các nguồn sự thật còn nằm ngoài đối tượng state đó; atomicity chỉ áp dụng đúng vùng đã được thiết kế.

Câu hỏi đúng không phải “dùng lớp `Atomic*` chưa?”, mà là **tập dữ liệu cần cập nhật nhất quán có nằm trọn trong cùng một thao tác atomic không?**

## 9. RMW trên collection cũng có thể bị lost update

Sai lầm không chỉ có ở biến `int`. Với một map chia sẻ:

~~~java
// Minh họa lỗi logic, không phải chương trình độc lập.
// map là ConcurrentHashMap<String, Integer>.
Integer current = map.get("jobs");
int next = (current == null ? 0 : current) + 1;
map.put("jobs", next);
~~~

`ConcurrentHashMap.get()` và `put()` từng cái là thao tác concurrent-safe theo hợp đồng, nhưng **get → tính → put** không nhất thiết atomic khi thread khác cũng cập nhật cùng key. Hai thread có thể đọc cùng giá trị cũ và cuối cùng chỉ tăng 1 lần.

`ConcurrentHashMap.merge`/`compute` cung cấp thao tác cập nhật atomic cho một key theo API. Tạo `MapCounter.java` (Java 17+):

~~~java
import java.util.concurrent.ConcurrentHashMap;

public class MapCounter {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();

        Runnable work = () -> {
            for (int i = 0; i < 100_000; i++) {
                counts.merge("jobs", 1, Integer::sum);
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("jobs = " + counts.get("jobs"));
    }
}
~~~

Chạy:

~~~bash
javac MapCounter.java
java MapCounter
~~~

Kết quả:

~~~text
jobs = 200000
~~~

Ở đây `merge("jobs", 1, Integer::sum)` thực hiện cập nhật cho một key theo hợp đồng atomic của `ConcurrentHashMap`. Nếu key vắng mặt, giá trị ban đầu là `1`; khi tồn tại, hàm gộp cộng thêm 1. Hàm cập nhật nên ngắn gọn và không cố cập nhật đệ quy những mapping khác trong cùng map. Đừng lầm `ConcurrentHashMap` làm **mọi chuỗi thao tác** trên nhiều key tự động atomic.

Tương tự, ngay cả với `Collections.synchronizedMap(...)`, chỉ đồng bộ từng method call không tự bảo vệ **toàn bộ compound action** nếu bạn đọc rồi ghi ở hai lời gọi tách biệt. Cần một vùng khóa chung hoặc thao tác nguyên tử được API hỗ trợ.

## 10. Khi nào dùng `LongAdder` thay cho `AtomicLong`?

`LongAdder` được thiết kế để giảm contention khi **nhiều thread cập nhật một thống kê dạng tổng**. Ví dụ:

~~~java
// Minh họa, biến adder dùng chung.
java.util.concurrent.atomic.LongAdder adder =
        new java.util.concurrent.atomic.LongAdder();
adder.increment();
long snapshot = adder.sum();
~~~

`LongAdder.increment()` phù hợp cho các lần ghi thống kê cạnh tranh; nhưng `sum()` **không phải snapshot atomic** đối với một loạt cập nhật đang diễn ra đồng thời. Giá trị đọc có thể không bao gồm một số cập nhật đồng thời. Nếu một quyết định nghiệp vụ phụ thuộc vào *“giá trị counter chính xác tại một thời điểm tuyến tính hóa”*, hãy cân nhắc `AtomicLong` hoặc cơ chế đồng bộ rõ ràng.

| Nhu cầu | Công cụ thường phù hợp | Cần lưu ý |
| --- | --- | --- |
| Counter chính xác, phép tăng/giảm atomic trên một biến | `AtomicInteger` / `AtomicLong` | `get` rồi `set` vẫn không phải RMW atomic |
| Bảo vệ nhiều hành động hay nhiều trường thành một critical section | `synchronized` / `ReentrantLock` | Mọi đường truy cập cạnh tranh phải dùng cùng quy tắc khóa |
| Tăng tổng thống kê với nhiều writer và contention cao | `LongAdder` | `sum()` khi có cập nhật đồng thời không phải snapshot atomic |
| Cập nhật giá trị cho một key của concurrent map | `ConcurrentHashMap.merge/compute` | Atomic theo key; không tạo transaction nhiều key |
| Thay một state bất biến gồm nhiều trường bằng CAS | `AtomicReference<ImmutableState>` | Update function thuần; hiểu retry và invariant |
| Không có trạng thái chia sẻ | Biến local, immutable object, message passing | Đơn giản nhất; tránh đồng bộ không cần thiết |

Không nên mặc định `LongAdder` “nhanh hơn” cho mọi workload; kiểm tra contention, số luồng, tần suất đọc và yêu cầu consistency trước khi đổi.

## 11. Kết quả và độ đúng: cần kiểm chứng khác nhau

### Vì sao stress test một triệu lần có thể “pass”?

Một đoạn như sau có thể đôi lúc in đúng kết quả, dù logic không an toàn:

~~~java
// Minh họa lỗi: sharedCounter++ không được bảo vệ.
for (int i = 0; i < 1_000_000; i++) {
    sharedCounter++;
}
~~~

Nếu hai thread ít đụng nhau do scheduler hoặc JIT/CPU/tải tình cờ, lỗi không nhất thiết xuất hiện. Một kết quả đúng ở 100 hoặc 10.000 lần chạy **không chứng minh chương trình thread-safe**. Ngược lại, ví dụ `LostUpdate` ở phần 3 điều khiển lịch xen kẽ bằng latch để tạo một phản ví dụ xác định.

### Cách kiểm chứng một sửa lỗi RMW

1. **Viết invariant.** Ví dụ: sau khi hai thread mỗi thread tăng đúng 100.000 lần và đều kết thúc bình thường, counter phải là 200.000.
2. **Chỉ ra linearization point.** Trong `synchronized`, phép cập nhật diễn ra khi thread độc quyền lock; với `AtomicInteger.incrementAndGet()`, API đảm bảo phép tăng nguyên tử trên biến đó. Đừng coi `Thread.sleep()` là linearization point.
3. **Chờ đúng kết thúc.** Dùng `Thread.join()` hoặc `Future.get()`. Không đọc kết quả rồi đoán task chắc đã hoàn thành vì thời gian chờ đủ lâu.
4. **Thử xen kẽ có chủ đích.** `CountDownLatch`/`CyclicBarrier` giúp đồng bộ các pha; cần thiết kế test tránh timeout vô hạn khi test thất bại.
5. **Kiểm tra đường truy cập khác.** Một writer không dùng lock, hay một đoạn `get()+set()` còn sót, đủ làm invariant bị phá.
6. **Đánh giá hiệu năng riêng.** Khi đã đúng, mới đo throughput/latency và contention bằng benchmark phù hợp (ví dụ JMH). Không đánh đổi correctness lấy một lần benchmark thuận lợi.

### Một vài hiểu nhầm cần tránh

- **“`++` là một toán tử, nên atomic.”** Toán tử ở source không tạo hợp đồng atomic cho shared RMW.
- **“Đổi thành `volatile int` là xong.”** Visibility/order khác với atomic cho chuỗi đọc–tính–ghi.
- **“`AtomicInteger.get()` và `set()` đều atomic, nên cả tổ hợp cũng atomic.”** Không; cần `incrementAndGet()`, CAS hoặc phương thức RMW tương ứng.
- **“Mỗi thread lock một object cũng được.”** Không; phải đồng bộ qua cùng lock bảo vệ cùng state.
- **“HashMap/ConcurrentHashMap có get và put thread-safe thì chuỗi get–put chắc chắn atomic.”** Không; phải dùng `merge/compute` hoặc protocol thích hợp.
- **“Một atomic counter bảo vệ tất cả invariant trên hai biến.”** Không; phạm vi atomicity phải khớp phạm vi invariant.
- **“Dữ liệu sau `join()` đúng thì quá trình cập nhật chắc atomic.”** `join()` giúp chờ và thấy các ghi trước khi worker kết thúc; nó không sửa các lost update đã xảy ra giữa worker.
- **“CAS lambda chỉ chạy đúng một lần.”** Một phép update CAS có thể retry; lambda có side effect dễ bị thực hiện lặp.
- **“LongAdder.sum() luôn cho snapshot tức thì chính xác khi còn writer.”** Không; sum không phải atomic snapshot dưới concurrent updates.

## 12. Tự kiểm tra

**Câu 1.** Hai thread cùng dùng `volatile int x` và mỗi thread gọi `x++` 1.000 lần. Sau khi `join` cả hai, `x` có chắc bằng 2.000?  
**Đáp án:** Không. `volatile` bảo đảm ngữ nghĩa truy cập từng lần, nhưng `x++` vẫn là read-modify-write có thể chen giữa.

**Câu 2.** Có hai `AtomicInteger` là `a` và `b`. `a.incrementAndGet()` rồi `b.decrementAndGet()` có atomic đối với invariant `a + b` không?  
**Đáp án:** Không. Từng cập nhật atomic riêng, nhưng thread khác có thể quan sát trạng thái giữa hai lần cập nhật.

**Câu 3.** Đổi `counter++` thành `atomic.get(); atomic.set(old + 1);` có giải quyết lost update không?  
**Đáp án:** Không. Đây vẫn là hai phương thức độc lập; dùng `incrementAndGet()` hoặc CAS loop.

**Câu 4.** Với `ConcurrentHashMap<String,Integer>`, hai thread cùng `get("k")` rồi `put("k", old + 1)` có luôn đếm đủ không?  
**Đáp án:** Không. Dùng một `merge("k", 1, Integer::sum)` cho phép tăng theo hợp đồng cập nhật atomic một key.

**Câu 5.** Muốn đọc tổng thống kê approximate khi nhiều thread tăng, chọn `LongAdder` hợp lý không? Muốn snapshot chính xác cho quyết định nghiệp vụ có nên dựa mù vào `sum()` không?  
**Đáp án:** Có thể dùng `LongAdder` cho thống kê throughput cao, nhưng `sum()` dưới concurrent update không phải snapshot atomic.

**Câu 6.** Trong thí nghiệm `LostUpdate`, vì sao mọi lần chạy bình thường đều in `actual = 1`, dù scheduler khác nhau?  
**Đáp án:** Cả hai thread được buộc đọc 0 trước khi có bất kỳ ghi nào. Sau release, cả hai cùng ghi 1; thứ tự hai lần ghi không thay đổi kết quả.

## Tài liệu tham khảo chính thức

- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model, synchronization, happens-before và hành vi tranh chấp.
- [`AtomicInteger` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): các phép tăng và CAS nguyên tử.
- [`LongAdder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counter phân tán khi cạnh tranh cao và giới hạn của `sum()`.
- [`ConcurrentHashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): các cập nhật `compute`, `merge` theo key.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối các pha và memory consistency.
- [`ReentrantLock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): mutual exclusion, điều khiển lock nâng cao.

**Ghi nhớ:** Một lần đọc atomic + một phép tính + một lần ghi atomic **không tạo thành một read-modify-write atomic**. Với shared mutable state, hãy dùng đúng primitive bảo vệ **cả cập nhật** và đúng phạm vi invariant.