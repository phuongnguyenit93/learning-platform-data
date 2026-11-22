# Program order và các quan hệ happens-before trong Java Memory Model

Khi hai thread cùng đọc và ghi dữ liệu, thứ tự nhìn thấy ở mã nguồn không đủ để khẳng định thread này sẽ thấy thay đổi của thread kia. Java Memory Model (JMM) xác định **những giá trị mà thao tác đọc được phép nhìn thấy** và các **bảo đảm về thứ tự, tính hiển thị** giữa những hành động đồng thời. Hai khái niệm cốt lõi là **program order** (thứ tự chương trình của một thread) và **happens-before** (quan hệ bảo đảm thứ tự ở mức bộ nhớ).

Bài học áp dụng cho Java concurrency nói chung (Java 17+), không phụ thuộc vào Spring.

Sau bài này, bạn sẽ biết:
- Hiểu “thứ tự trong cùng thread” khác “thứ tự được bảo đảm giữa các thread” như thế nào.
- Xây dựng một chuỗi happens-before bằng **program order**, **synchronizes-with** và tính **bắc cầu**.
- Nhận diện các cạnh happens-before đến từ `Thread.start()`, `join()`, monitor `synchronized`, `volatile` và API đồng thời trong JDK.
- Phân biệt **visibility**, **ordering**, **atomicity** và vấn đề **data race**.
- Kiểm tra một mẫu chia sẻ dữ liệu xem có thể lập luận được về kết quả hay không, thay vì dựa vào `sleep()` hoặc kết quả chạy thử.

## 1. JMM cần quy tắc thứ tự để làm gì?

CPU có cache, compiler/JIT tối ưu, các lõi xử lý thực thi song song và thread được lập lịch độc lập. JVM được phép thực hiện nhiều tối ưu miễn là vẫn tuân thủ JMM. Kết quả là:

- Trong **một thread**, hành vi phải tương thích với ngữ nghĩa chạy tuần tự của chính thread đó (*intra-thread semantics*).
- Giữa **hai thread**, việc thread A thực hiện lệnh ghi trước trên đồng hồ thực tế **không đủ** để kết luận thread B sẽ đọc được giá trị ghi mới hoặc nhìn thấy mọi thao tác trước đó của A.
- Cần một quan hệ đồng bộ được đặc tả để xác định ràng buộc bộ nhớ có thể dựa vào khi chứng minh tính đúng.

Ví dụ ý tưởng:

~~~java
// Biến chia sẻ giữa 2 thread:
int payload = 0;
boolean ready = false;

// Thread A:
payload = 42;
ready = true;

// Thread B:
if (ready) {
    System.out.println(payload);
}
~~~

Đây là **các đoạn minh họa, không phải một chương trình Java độc lập**. Khi `payload` và `ready` là biến thường, không có đồng bộ, không có bảo đảm rằng B sẽ luôn thấy `42` sau khi thấy `ready == true`. B cũng có thể không quan sát được trạng thái `ready` mà A đã ghi. Đoạn mã bị **data race** trên dữ liệu chia sẻ; thứ tự nguồn trong A chưa đủ tạo quan hệ happens-before từ A sang B.

Câu hỏi cần trả lời không phải chỉ là “dòng nào chạy trước?”, mà là: **Hành động ghi của A có happens-before hành động đọc tương ứng của B không?**

## 2. Program order: thứ tự hành động bên trong một thread

### 2.1. Định nghĩa

**Program order** là thứ tự giữa các hành động của **cùng một thread** như thể chúng thực thi theo ngữ nghĩa của chương trình trong thread đó. Theo quy tắc JMM, nếu hành động `x` đứng trước hành động `y` theo program order trong một thread, thì:

**`x happens-before y`.**

Ví dụ:

~~~java
int a = 10;       // A1
int b = a + 5;    // A2
System.out.println(b); // A3
~~~

Trong cùng thread, `A1 →po A2 →po A3`; vì vậy `A1 →hb A2 →hb A3`. Kết quả trong ngữ cảnh ví dụ là `15`, dù JVM có thể áp dụng tối ưu nội bộ. JMM yêu cầu hành vi được giữ đúng theo ngữ nghĩa trong thread; nó **không hứa CPU sẽ phát từng thao tác máy theo đúng thứ tự dòng mã nguồn**.

### 2.2. Program order không tự nối hai thread

Hai chuỗi:

~~~text
Thread A: A1 ->po A2 ->po A3
Thread B: B1 ->po B2 ->po B3
~~~

Cho ta các cạnh happens-before **trong từng thread**, nhưng không mặc nhiên có `A3 →hb B1` hay `B2 →hb A1`. Muốn nối hai chuỗi cần một quy tắc đồng bộ xuyên thread, thường gọi là **synchronizes-with**.

Các điểm thường nhầm:
- `A1` viết trước `A2` trong mã nguồn không có nghĩa mọi thread khác nhất thiết quan sát thấy hai giá trị theo cách mong muốn.
- “Thread A đã chạy xong dòng ghi” trên đồng hồ ngoài chương trình không phải một quy tắc JMM có thể dùng thay đồng bộ.
- Mỗi thread có program order riêng; program order không cung cấp một *total order* chung cho toàn bộ hành động thường trên mọi thread.

## 3. Happens-before: quan hệ bảo đảm về bộ nhớ

### 3.1. Định nghĩa và ba cách suy luận chính

Viết `A →hb B` khi hành động A **happens-before** hành động B.

Trong JMM, happens-before hình thành từ program order, các cạnh synchronizes-with và tính bắc cầu của chúng. Để lập luận thực hành, thường áp dụng ba quy tắc:

1. **Program order:** nếu A đứng trước B trong cùng thread theo program order, `A →hb B`.
2. **Synchronizes-with:** một số thao tác đồng bộ xác định tạo cạnh từ thread này sang thread khác, ví dụ monitor unlock đến một lần lock tiếp sau trên cùng monitor, hay ghi volatile đến đọc volatile tiếp sau theo synchronization order.
3. **Bắc cầu (transitivity):** nếu `A →hb B` và `B →hb C`, suy ra `A →hb C`.

Ví dụ:

~~~text
Thread A:
  data = 42       (A1)
  ready = true    (A2: volatile write)
                       |
                       | synchronizes-with
                       v
Thread B:
  read ready      (B1: volatile read thấy true)
  read data       (B2)

A1 ->po A2 ->sw B1 ->po B2
Suy ra A1 ->hb B2
~~~

Dấu `→po` là program order; `→sw` là synchronizes-with; `→hb` là happens-before. Nếu không có các ghi cạnh tranh khác vào `data`, B có thể dựa vào bảo đảm thấy `42` sau khi đọc `ready == true`.

Happens-before **không chỉ nói về “đã diễn ra trước trên đồng hồ”**; đây là quan hệ do JMM xác định để ràng buộc những kết quả quan sát được. Bất kỳ lời giải thích nào dựa riêng vào thời gian thực hoặc số mili giây đã chờ đều thiếu cơ sở đồng bộ.

### 3.2. Happens-before không đồng nghĩa “mỗi bước là nguyên tử”

Ví dụ `counter++` bao gồm đọc, tính toán và ghi lại. Hai thread đều dùng `volatile int counter` có visibility và quy tắc thứ tự của volatile, nhưng `counter++` **vẫn không phải** một phép tăng nguyên tử. Hai thread có thể đọc cùng giá trị rồi cùng ghi giá trị mới, làm mất một lần cập nhật.

Đối với phép cập nhật nguyên tử, hãy dùng:
- `AtomicInteger.incrementAndGet()`/`getAndIncrement()` cho bộ đếm;
- `synchronized` hoặc `Lock` khi cần bảo vệ toàn bộ bất biến gồm nhiều bước;
- Cấu trúc dữ liệu đồng thời và các phương thức nguyên tử được API cam kết khi thích hợp.

Ba thuộc tính liên quan nhưng khác nhau:

| Thuộc tính | Câu hỏi |
| --- | --- |
| **Visibility** | Khi thread B đọc, JMM có bảo đảm B thấy ghi của A không? |
| **Ordering** | Những thao tác nào được yêu cầu có trật tự có thể dựa vào giữa các thread? |
| **Atomicity** | Một nhóm bước có được quan sát/xử lý như một thao tác không thể bị xen kẽ không? |

Một chương trình cần xem xét cả ba khi bất biến đòi hỏi.

## 4. Synchronizes-with: những cạnh xuyên thread quan trọng

### 4.1. Monitor: synchronized unlock → subsequent lock

Một lần **unlock** trên monitor `m` synchronizes-with **mọi lần lock sau đó** trên cùng monitor `m` (theo synchronization order). Điều này cho phép thao tác ghi trong khối khóa trước được nhìn thấy khi thread khác vào khối khóa sau, nếu truy cập đúng cùng monitor.

~~~java
// Đoạn minh họa trong một class có 2 thread cùng tham chiếu object lock:
final Object lock = new Object();
int value = 0;

// Thread A:
synchronized (lock) {
    value = 42;
} // unlock(lock)

// Thread B, đi vào khối này sau khi A đã unlock:
synchronized (lock) { // lock(lock)
    System.out.println(value);
}
~~~

Đoạn mã không độc lập; ý nghĩa là cả hai thread **dùng cùng object `lock`**. Nếu B thực sự lấy khóa sau khi A nhả khóa và không có người ghi khác, in `42`. Nếu B vào trước A, kết quả có thể là `0`. `synchronized` tạo ràng buộc chính xác khi biết thứ tự lấy khóa; nó **không tự buộc thread A phải lấy khóa trước thread B**.

Đổi sang hai object lock khác nhau sẽ mất cạnh đồng bộ mong muốn, dù tên biến hoặc nội dung hai khối giống nhau.

Với `java.util.concurrent.locks.Lock` như `ReentrantLock`, việc lock/unlock được đặc tả có hiệu ứng bộ nhớ tương đương monitor để xây dựng lập luận tương ứng. Vẫn phải `unlock()` trong `finally` sau khi lấy khóa thành công.

### 4.2. Volatile write → subsequent volatile read

Một lần ghi vào biến `volatile` synchronizes-with các lần đọc biến đó **tiếp sau theo synchronization order**. Đối với ví dụ kiểu *publication flag*, thread đọc thấy `true` có thể dùng thứ tự này để truy cập dữ liệu mà writer đã chuẩn bị trước khi công bố flag.

Ví dụ độc lập (Java 17+):

~~~java
// VolatilePublicationDemo.java
public class VolatilePublicationDemo {
    private static int payload;
    private static volatile boolean ready;

    public static void main(String[] args) throws InterruptedException {
        Thread reader = new Thread(() -> {
            while (!ready) {
                Thread.onSpinWait();
            }
            System.out.println("Payload: " + payload);
        });

        reader.start();
        payload = 42;
        ready = true;
        reader.join();
    }
}
~~~

~~~bash
javac VolatilePublicationDemo.java
java VolatilePublicationDemo
~~~

Khi hai thread được lập lịch và chương trình hoàn thành bình thường, stdout:

~~~text
Payload: 42
~~~

Lập luận:
1. Trong main: `payload = 42 →po ready = true`.
2. Trong reader: lần đọc volatile quan sát `true` diễn ra sau lần ghi `ready = true` trong synchronization order; lần ghi này `→sw` lần đọc đó.
3. Trong reader: lần đọc thấy `true` `→po` lần đọc `payload`.
4. Theo bắc cầu, việc main ghi `payload = 42 →hb` việc reader đọc `payload`. Chỉ có một writer vào `payload` trong chương trình này.

`Thread.onSpinWait()` là gợi ý cho JVM/CPU trong vòng spin; **nó không phải thao tác đồng bộ**. Dùng spin chỉ để minh họa quan hệ volatile: trong ứng dụng thực tế, ưu tiên công cụ chờ phù hợp như `CountDownLatch`, `BlockingQueue` hoặc `Future` để tránh tốn CPU và có chính sách timeout/cancel.

Chú ý: tính liveness không suy ra từ riêng quan hệ happens-before. Nếu hệ điều hành không cấp thời gian chạy cho writer, reader có thể chưa thoát vòng chờ; JMM không cam kết lịch chạy công bằng.

### 4.3. Thread.start(): start → action đầu tiên của thread mới

Một lời gọi `thread.start()` synchronizes-with bất kỳ hành động nào trong thread vừa được start. Do đó dữ liệu được chuẩn bị **trước `start()`** có thể được thread mới nhìn thấy theo happens-before.

~~~java
// StartVisibilityDemo.java
public class StartVisibilityDemo {
    public static void main(String[] args) throws InterruptedException {
        int[] values = {0};
        values[0] = 42;

        Thread worker = new Thread(() ->
            System.out.println("Observed: " + values[0]));

        worker.start();
        worker.join();
    }
}
~~~

~~~bash
javac StartVisibilityDemo.java
java StartVisibilityDemo
~~~

Stdout:

~~~text
Observed: 42
~~~

`values[0] = 42 →po worker.start() →sw` các hành động của worker. Đây là cách chuyển thông tin khởi tạo từ thread tạo sang thread con. Nếu main **sửa tiếp `values[0]` sau `start()`** trong khi worker đọc mà không có đồng bộ bổ sung, thì cạnh `start()` không bảo vệ việc sửa sau đó.

### 4.4. Thread termination: hành động của worker → join thành công

Mọi hành động trong thread hoàn tất happens-before thread khác **phát hiện thread đó đã kết thúc**, chẳng hạn khi `join()` trả về bình thường hoặc `isAlive()` trả `false` do phát hiện kết thúc.

~~~java
// JoinVisibilityDemo.java
public class JoinVisibilityDemo {
    private static int result;

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> result = 42);
        worker.start();
        worker.join();
        System.out.println("Result: " + result);
    }
}
~~~

~~~bash
javac JoinVisibilityDemo.java
java JoinVisibilityDemo
~~~

Stdout:

~~~text
Result: 42
~~~

Lập luận: `result = 42` xảy ra trong worker; worker kết thúc, main trở về từ `join()`; main đọc `result` sau `join()`. Cạnh kết thúc thread cùng program order và bắc cầu đủ để main thấy cập nhật. Không cần biến `result` là volatile **trong tình huống chỉ một worker ghi và main chỉ đọc sau khi join thành công**. Nếu main đọc trước khi `join()`, không được tự suy ra bảo đảm đó.

`join()` có thể ném `InterruptedException` khi caller đang chờ bị interrupt; code phải xử lý trường hợp chờ chưa hoàn tất theo chính sách ứng dụng.

### 4.5. Interrupt và việc phát hiện interrupt

Một lời gọi `interrupt()` lên thread T synchronizes-with hành động **T phát hiện interrupt**, ví dụ kiểm tra `isInterrupted()`/`Thread.interrupted()` hoặc thao tác chặn ném `InterruptedException` do interrupt.

Cạnh này giúp truyền tín hiệu điều khiển, nhưng **interrupt không dừng cưỡng bức thread**, không buộc một tác vụ CPU-bound tự kiểm tra, và không thay thế giao thức chuyển dữ liệu giữa các thread. Đừng dùng interrupt như thông điệp “kết quả đã sẵn sàng” khi mục đích thật là công bố một giá trị.

### 4.6. Default initialization và final field

JMM còn có quy tắc đồng bộ cho **default initialization** của object trước các thao tác thông thường khác lên object đó. Với `final`, JMM định nghĩa các bảo đảm riêng khi object được xây dựng đúng cách, đặc biệt **không để `this` escape trong constructor**. Nhờ vậy các trường final có khả năng hiển thị khởi tạo đặc biệt, nhưng không nên suy diễn rằng mọi field mutable khác trong object tự nhiên an toàn khi chia sẻ.

Với các object có nhiều trạng thái mutable, hãy công bố chúng bằng các cơ chế happens-before rõ ràng như khóa, volatile reference hoặc handoff của concurrency API.

## 5. Transitivity: ghép các cạnh thành một bằng chứng

Giả sử:

~~~text
Thread A:       write(data=42) ─po─> volatile write(ready=true)
                                        |
                                        | sw
                                        v
Thread B:                              volatile read(ready)
                                        |
                                        | po
                                        v
                                      read(data)
~~~

Suy ra:

~~~text
write(data=42) →hb read(data)
~~~

Phải kiểm tra **đúng cặp thao tác** và **đúng đối tượng đồng bộ**. Một câu như “có dùng volatile ở đâu đó” không cung cấp bằng chứng rằng một ghi vào `data` được bảo đảm hiển thị ở nơi đọc.

### 5.1. Nhiều chặng chuyển giao

Quan hệ happens-before có thể đi qua nhiều thread. Ví dụ nếu:

~~~text
A: write X →po release(lock1)
                →sw B: acquire(lock1) →po release(lock2)
                                            →sw C: acquire(lock2) →po read X
~~~

thì từ bắc cầu ta có `A:write X →hb C:read X`. Các edge giữa A–B và B–C không cần dùng cùng monitor, miễn là từng cặp dùng đúng monitor của nó, có thứ tự unlock–lock phù hợp, và code thật sự nối được hai bước bằng program order.

### 5.2. Happens-before có hướng; không thể đảo chiều

Nếu `A →hb B`, không thể kết luận `B →hb A`. Nếu hai hành động nằm trong hai thread mà không có quan hệ happens-before theo cả hai hướng, chúng **không được sắp thứ tự bởi happens-before**. Đối với truy cập xung đột vào dữ liệu chia sẻ, cần xem xét data race và kết quả được JMM cho phép.

Không nên tự thêm edge chỉ vì:
- Cùng gọi một phương thức bình thường trên hai thread.
- Cùng nhìn vào một object nhưng mỗi thread khóa một monitor khác nhau.
- Đã gọi `Thread.sleep(100)` trước khi đọc.
- Khi debug, log thường hiển thị tác vụ ghi “có vẻ hoàn thành trước”.

## 6. Các API java.util.concurrent tạo bảo đảm bộ nhớ

Các công cụ chuẩn của JDK có **memory consistency effects** được công bố trong tài liệu API. Những bảo đảm này thường ngắn gọn và dễ dùng hơn việc tự dựng giao thức với nhiều biến thường.

| Cơ chế | Cạnh quan trọng để suy luận |
| --- | --- |
| `ExecutorService` | Hành động trước khi submit `Runnable`/`Callable` →hb hành động trong task; hành động task →hb việc caller lấy kết quả bằng `Future.get()` |
| `Future.get()` | Hành động trong phép tính bất đồng bộ →hb hành động tiếp theo sau khi `get()` trả kết quả thành công cho thread đợi |
| `CountDownLatch` | Hành động trước `countDown()` →hb hành động sau khi `await()` tương ứng trở về thành công |
| `BlockingQueue` | Hành động trước khi đặt phần tử vào queue →hb hành động sau khi thread khác lấy/nhận phần tử |
| `ConcurrentMap` và collection đồng thời | Dùng đúng hợp đồng *memory consistency* của API cho giao tiếp thông qua phần tử/entry và các thao tác được đặc tả |
| `Lock` (ví dụ `ReentrantLock`) | Thành công lock/unlock có hiệu ứng bộ nhớ của monitor tương ứng |

**Ví dụ dùng CountDownLatch**, stdout xác định mà không cần spin:

~~~java
// LatchHappensBeforeDemo.java
import java.util.concurrent.CountDownLatch;

public class LatchHappensBeforeDemo {
    private static int payload;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread reader = new Thread(() -> {
            try {
                ready.await();
                System.out.println("Payload: " + payload);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        reader.start();
        payload = 42;
        ready.countDown();
        reader.join();
    }
}
~~~

~~~bash
javac LatchHappensBeforeDemo.java
java LatchHappensBeforeDemo
~~~

Stdout:

~~~text
Payload: 42
~~~

Trong main: `payload = 42 →po ready.countDown()`. Theo hợp đồng `CountDownLatch`, những hành động trước `countDown()` happens-before những hành động sau khi `await()` trở về thành công ở reader. Kết hợp program order, reader thấy `42`. Việc `reader.join()` trong main chỉ nhằm chờ đọc/xuất hoàn tất trước khi kết thúc chương trình; **bảo đảm visibility từ main sang reader ở đây đến từ latch**.

**Ví dụ với ExecutorService + Future**, phân biệt hai chiều chuyển giao:

~~~java
// FutureHappensBeforeDemo.java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureHappensBeforeDemo {
    private static int base;
    private static int outcome;

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            base = 40;
            Future<Integer> task = executor.submit(() -> {
                outcome = base + 2;
                return outcome;
            });

            int received = task.get();
            System.out.println("Future: " + received);
            System.out.println("Shared: " + outcome);
        } finally {
            executor.shutdown();
        }
    }
}
~~~

~~~bash
javac FutureHappensBeforeDemo.java
java FutureHappensBeforeDemo
~~~

Stdout:

~~~text
Future: 42
Shared: 42
~~~

Giải thích hai chiều:

1. Main ghi `base = 40` **trước khi `submit`**; hành động này happens-before hành động của task, nên task thấy `base = 40`.
2. Task ghi `outcome = 42` và trả kết quả; các hành động trong task happens-before hành động của main **sau `task.get()` thành công**. Main có thể đọc `outcome` theo bảo đảm đó.
3. `ExecutorService.shutdown()` dừng nhận task mới; **không tự chờ** các task chạy xong. Trong ví dụ, main đã `get()` trước khi shutdown.

Bảo đảm này không có nghĩa mọi shared variable trong task tự động thread-safe nếu các thread khác vẫn sửa cùng biến mà không đồng bộ.

## 7. Data race, correctly synchronized và giới hạn lập luận

### 7.1. Data race là gì?

Ở mức căn bản, khi hai thread truy cập **cùng biến**, có ít nhất một lần **ghi**, và hai truy cập xung đột đó **không được sắp thứ tự bởi happens-before**, ta có tình huống data race theo định nghĩa của JMM. Vấn đề thường gặp nhất là các biến thường chia sẻ giữa thread nhưng không có bất kỳ giao thức đồng bộ nhất quán nào.

~~~java
// Đoạn minh họa, KHÔNG phải một chương trình hoàn chỉnh:
int counter = 0;

// T1 và T2 cùng thực hiện, không khóa:
counter++;
~~~

Phép tăng là chuỗi đọc, tính, ghi; có thể mất cập nhật. Data race và lost update có liên quan nhưng không nên xem mọi race condition là chỉ do visibility. Một phép tăng cần **atomicity**, do đó việc đổi `counter` sang `volatile` **không giải quyết** lost update.

Khi chương trình được **đồng bộ đúng** (các truy cập chia sẻ xung đột được điều phối phù hợp), JMM bảo đảm những hành vi nhất quán với mô hình tuần tự cho các chương trình được đồng bộ đúng (thường gọi là thuộc tính *sequential consistency for data-race-free programs*). Điều kiện tiên quyết là các thành phần đều tuân thủ giao thức đồng bộ.

### 7.2. Không có happens-before thì được phép đọc gì?

Không có cạnh happens-before giữa ghi và đọc **không đồng nghĩa** đọc chắc chắn thấy giá trị cũ; có lần chạy thấy mới và có lần không. JMM ràng buộc những kết quả được phép của một execution, chứ không tuyên bố “không đồng bộ thì luôn sai”.

Cũng không thể tự do giả định một thứ tự toàn cục cho mọi phép đọc/ghi thường. Một quy tắc kiểm tra thực tế là: xác định các ghi có thể tác động đến một lần đọc, kiểm tra những quan hệ happens-before bắt buộc, rồi xem API đồng bộ có đưa tới bảo đảm mong muốn không.

Lưu ý JMM có thêm các quy tắc về tính hợp lệ của phép đọc và thực thi; không nên biến ví dụ thành tuyên bố “đọc được bất kỳ giá trị nào tùy ý”. Trong thiết kế ứng dụng, mục tiêu thường là tạo **cạnh happens-before rõ ràng** để tránh phụ thuộc vào những khả năng quan sát khó đoán.

### 7.3. Happens-before chưa đủ cho thao tác ghép nhiều bước

~~~java
// Mã minh họa, không biên dịch độc lập:
volatile int counter = 0;

// Hai thread cùng gọi:
counter = counter + 1;
~~~

Mỗi lần đọc/ghi volatile có thứ tự/bảo đảm riêng, nhưng thao tác ghép vẫn có thể bị xen kẽ. Nếu bất biến là “mỗi yêu cầu phải tăng bộ đếm một lần”, sử dụng `AtomicInteger.incrementAndGet()` hoặc khóa bao toàn bộ cập nhật.

Ngược lại, khi thông tin chỉ **được công bố một lần** rồi **đọc sau ranh giới đồng bộ**, như các ví dụ `start()`, `join()` và latch, có thể không cần biến payload là volatile. Bắt buộc phân tích ai viết, khi nào viết, có ghi cạnh tranh hay không và điểm đồng bộ nào được sử dụng.

## 8. Cách kiểm tra một đoạn code theo đồ thị happens-before

Đọc code đồng thời bằng một sơ đồ hành động:

1. **Liệt kê biến chia sẻ:** ví dụ `payload`, `ready`, `counter`; chỉ ra thread nào đọc/ghi từng biến.
2. **Đánh dấu hành động:** `W(payload=42)`, `Wvolatile(ready=true)`, `Rvolatile(ready)`, `R(payload)`.
3. **Vẽ program order bên trong từng thread** (các cạnh `→po`).
4. **Tìm các cạnh synchronizes-with thực sự**: cùng monitor, cùng volatile field, `start`, phát hiện kết thúc bằng `join`, giao tiếp qua concurrency API.
5. **Lấy bắc cầu** để biết truy cập ghi mong muốn có happens-before lần đọc hay không.
6. **Kiểm tra writer cạnh tranh và thao tác phức hợp**: dù visibility được bảo đảm, phép cập nhật có đủ atomicity? Nếu nhiều writer, thứ tự tương quan đã được kiểm soát chưa?
7. **Đối chiếu với yêu cầu nghiệp vụ**: ràng buộc kết quả, xử lý timeout/interrupt, đóng executor, và khả năng tiến triển.

Ví dụ so sánh:

| Tình huống | Có đủ HB để công bố `payload`? | Lưu ý |
| --- | --- | --- |
| A ghi `payload` rồi `start()` worker B; B đọc | Có | Chỉ bảo đảm những thao tác trước `start()` |
| Worker A ghi `payload`; B là thread đã `join()` A thành công, rồi đọc | Có | B phải đợi thành công rồi mới đọc |
| A ghi `payload` trước volatile write flag; B đọc flag thấy true rồi đọc payload | Có | Không có ghi cạnh tranh khác vào payload |
| A ghi `payload` rồi `countDown()`; B `await()` thành công rồi đọc | Có | Dựa trên memory consistency của latch |
| A ghi `payload` rồi `sleep(100)`; B đọc | Không có HB chỉ từ sleep | Delay không tạo giao thức đồng bộ |
| A khóa `lockA`; B khóa object `lockB` khác | Không có HB từ cặp khóa đó | Tên biến giống nhau không làm hai monitor giống nhau |
| Hai thread cùng `volatileCounter++` | Có quy tắc volatile, nhưng **không đủ atomicity** | Dùng atomic increment/khóa |

### Những sai lầm thường gặp

- **“Mã trong cùng thread chạy theo thứ tự, vậy thread khác chắc chắn thấy đúng.”** Program order là cạnh nội bộ; cần nối bằng synchronizes-with.
- **“Volatile làm mọi biểu thức trên biến trở thành nguyên tử.”** Sai: volatile không gộp chuỗi đọc–sửa–ghi.
- **“`join()` làm cho mọi đọc trước `join()` thấy dữ liệu mới.”** Sai: chỉ có thể dùng bảo đảm cho hành động của caller **sau khi join thành công**.
- **“Bất kỳ hai khối synchronized nào cũng đồng bộ với nhau.”** Sai: phải cùng monitor và đúng thứ tự unlock/lock.
- **“`Thread.sleep` giúp JMM flush cache.”** Không có quy tắc happens-before như vậy; sleep chỉ ảnh hưởng lập lịch.
- **“Đọc `isDone() == true` là đã lấy đủ mọi dữ liệu tùy ý.”** Dựa vào hợp đồng memory consistency cụ thể của API, chẳng hạn `Future.get()`, thay vì phỏng đoán một phương thức kiểm tra trạng thái tương đương mọi điểm đồng bộ.
- **“Nếu test 10.000 lần đúng thì không có data race.”** Stress test có ích để phát hiện lỗi, nhưng không chứng minh đầy đủ các cạnh JMM cần thiết.
- **“Happens-before là đúng thứ tự thời gian CPU thực thi.”** Quan hệ này là một ràng buộc ngữ nghĩa; cách compiler/JIT/CPU hiện thực có thể khác, miễn tuân thủ JMM.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Thread A ghi `int data = 99` rồi gọi `t.start()`, B là thread `t` và chỉ đọc `data` sau khi bắt đầu. Nếu không có ghi cạnh tranh khác, có cần `volatile` chỉ để thấy giá trị 99 không?

**Đáp án:** Không. Cạnh program order trước `start()` và cạnh `start()` đến hành động trong B cho phép suy ra happens-before.

**Câu 2.** Worker ghi `result`, caller gọi `worker.join()` trả về thành công rồi mới đọc. Bảo đảm gì?

**Đáp án:** Hành động của worker happens-before các hành động tiếp sau việc caller phát hiện worker đã kết thúc; caller thấy giá trị của worker nếu không có writer cạnh tranh khác làm thay đổi nó.

**Câu 3.** A dùng `synchronized(lock1)`, B dùng `synchronized(lock2)`, trong đó `lock1 != lock2`. Có thể suy luận unlock–lock từ hai khối này không?

**Đáp án:** Không; phải khóa **cùng monitor**.

**Câu 4.** Một `volatile boolean ready` được ghi sau khi writer chuẩn bị payload. Reader thấy `ready == true` rồi đọc payload. Kể tên chuỗi cạnh.

**Đáp án:** `write(payload) →po writeVolatile(ready) →sw readVolatile(ready) →po read(payload)`; suy ra `write(payload) →hb read(payload)`.

**Câu 5.** Hai thread cùng tăng một `volatile int` bằng `++`. Có thể thiếu lần tăng không?

**Đáp án:** Có. Volatile không làm phép tăng nguyên tử; dùng `AtomicInteger` hoặc đoạn tới hạn phù hợp.

**Câu 6.** Người gọi submit `Callable<Integer>` rồi gọi `future.get()` thành công. Làm sao chứng minh có thể thấy các thay đổi trước khi task hoàn tất?

**Đáp án:** Các hành động trong task happens-before hành động của caller sau khi `Future.get()` trả kết quả thành công, theo memory consistency của executor/future.

**Câu 7.** Tại sao một lần ngủ `sleep(500)` sau ghi dữ liệu không đủ để cho reader dựa vào kết quả?

**Đáp án:** Thời gian chờ không tạo synchronizes-with. Phải dùng volatile, lock, latch, join, future hoặc cơ chế được đặc tả phù hợp với giao thức trao đổi dữ liệu.

**Ghi nhớ:** Program order cho quan hệ happens-before **bên trong thread**. Synchronizes-with nối các thread. Tính bắc cầu ghép những cạnh đó thành chứng minh visibility/ordering. Sau khi có happens-before, vẫn phải kiểm tra **atomicity**, các writer cạnh tranh và việc tuân thủ giao thức đồng bộ để khẳng định tính đúng của chương trình.

### Tài liệu tham khảo chuẩn

- Java Language Specification, `17.4 “Memory Model”, đặc biệt `17.4.4 “Synchronization Order” và `17.4.5 “Happens-before Order”: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- JDK 17 `java.util.concurrent` package documentation (memory consistency properties): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html
- JDK 17 `Thread` và `CountDownLatch` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html