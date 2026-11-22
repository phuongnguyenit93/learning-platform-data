# Data race và hành vi quan sát khó dự đoán trong Java Memory Model

## 1. Vấn đề: vì sao kết quả đa luồng không giống cách đọc mã tuần tự?

Trong chương trình Java đa luồng, hai thread có thể chạy xen kẽ hoặc song song và truy cập cùng dữ liệu tại các thời điểm không đoán trước. Một thread cũng không nhất thiết quan sát ngay các ghi từ thread khác. Nếu thiếu **quan hệ đồng bộ phù hợp**, chương trình có thể mất cập nhật, nhìn thấy giá trị cũ, quan sát trạng thái không nhất quán hoặc chờ mãi một tín hiệu đã được phát ra.

Cần xét hai khía cạnh khác nhau:

- **Scheduling:** khi nào các thread có cơ hội thực thi; thứ tự này phụ thuộc JVM, OS và tình trạng máy.
- **Java Memory Model (JMM):** quy tắc cho biết những giá trị nào một phép đọc được phép quan sát; quan hệ **happens-before** giúp bảo đảm visibility và ordering giữa các thread.

Không phải thứ tự log thay đổi là một lỗi. Nếu hai nhiệm vụ độc lập in hai dòng, cả hai thứ tự có thể đúng. Vấn đề xuất hiện khi tính đúng đắn dựa vào một thứ tự hoặc một quan sát mà JMM **không bảo đảm**.

## 2. Data race theo định nghĩa JMM

Hai hành động truy cập một biến được gọi là **conflicting** khi cùng động đến một biến và ít nhất một hành động là ghi. Một chương trình có **data race** nếu tồn tại hai hành động conflicting mà **không có quan hệ happens-before sắp thứ tự giữa chúng**.

Ví dụ ở mức minh họa, với một trường `int value` dùng chung:

```java
// Thread A:
shared.value = 1;

// Thread B:
int observed = shared.value;
```

Đoạn trên chỉ minh họa hai đoạn mã của hai thread, **không phải file Java độc lập**. Nếu không có synchronized, volatile, thread start/join hoặc đồng bộ khác thiết lập happens-before thích hợp, không được dựa vào việc A “thường chạy trước” để kết luận B sẽ quan sát 1.

### Phân biệt các khái niệm dễ lẫn

| Khái niệm | Vấn đề | Ví dụ |
| --- | --- | --- |
| **Data race** | Truy cập xung đột cùng biến không được sắp thứ tự bằng happens-before | Một thread ghi trường thường, thread khác đọc nó không đồng bộ |
| **Race condition** | Tính đúng đắn phụ thuộc vào timing hoặc thứ tự xen kẽ | Hai yêu cầu cùng thấy còn một đơn vị hàng và đều bán |
| **Atomicity violation** | Một chuỗi thao tác cần xem như một bước logic nhưng bị chen ngang | Hai thread chạy `counter++` và mất cập nhật |
| **Visibility problem** | Không có bảo đảm thread khác thấy thay đổi | Vòng chờ cờ `done` thường không kết thúc |
| **Ordering problem** | Các hành động được quan sát không như suy luận dựa trên mã nguồn | Thread thấy cờ sẵn sàng nhưng chưa thấy dữ liệu tương ứng |

**Data race và race condition không đồng nhất.** Hai thread cùng thực hiện `volatileCounter++` trên trường `volatile int` có thể mất cập nhật dù các truy cập volatile riêng lẻ là synchronization actions. Đây là **race condition về nguyên tử tính**, không cần có data race theo định nghĩa JMM.

Ngược lại, data race không đồng nghĩa mọi lần chạy đều tạo ra kết quả sai; nó cho phép những quan sát mà chương trình không nên dựa vào.

## 3. Ba nhóm hành vi quan sát khó đoán

### 3.1. Lost update: một phép tăng không phải một bước nguyên tử

Giả sử hai thread cùng chạy `count++`. Ý nghĩa logic của phép tăng là:

```text
old = count
newValue = old + 1
count = newValue
```

Nếu cả hai đọc `old = 0` trước khi ghi, cả hai cùng ghi 1 và mất một lần tăng. Với trường `int` thường, các truy cập này có thể tạo data race; với trường `volatile int`, phép đọc và ghi riêng vẫn không hợp thành thao tác tăng nguyên tử.

### 3.2. Visibility: cờ hoàn tất không phải lúc nào cũng được nhìn thấy

```java
// Minh họa: finished là trường boolean thường được chia sẻ.
while (!finished) {
    // spin
}
```

Writer có thể đã đặt `finished = true`, nhưng nếu không có happens-before, JMM không cam kết reader sẽ thấy thay đổi. JVM có thể tối ưu hóa vòng lặp và thread có thể tiếp tục đọc giá trị cũ. `Thread.sleep()` hoặc `Thread.yield()` không bổ sung bảo đảm công bố dữ liệu.

`boolean` được đọc/ghi nguyên tử theo kiểu dữ liệu vẫn không có nghĩa **visibility** được bảo đảm giữa các thread.

### 3.3. Ordering: thấy tín hiệu chưa chắc thấy nội dung

```java
// Writer, chỉ là đoạn minh họa:
payload = 42;
ready = true;

// Reader, chỉ là đoạn minh họa:
if (ready) {
    System.out.println(payload);
}
```

Nếu cả `payload` và `ready` là trường thường, truy cập không được đồng bộ và hai đoạn chạy trên hai thread, không thể kết luận “đọc ready là true ⇒ chắc chắn đọc payload là 42”. Thứ tự chương trình của writer **không tự tạo** quan hệ happens-before từ writer sang reader.

Có thể sửa bằng giao thức xuất bản: writer ghi payload trước, sau đó ghi **volatile** ready; reader đọc ready volatile rồi mới dùng payload. Với giao thức nhiều producer hoặc nhiều lần cập nhật, cần xem xét thêm khả năng thay đổi sau xuất bản và tính nguyên tử của cả trạng thái.

## 4. Java 17+: ví dụ lost update tái hiện có kiểm soát

Tạo file `ForcedLostUpdate.java`:

```java
import java.util.concurrent.CountDownLatch;

public class ForcedLostUpdate {
    private static final class Box {
        int count;
    }

    public static void main(String[] args) throws InterruptedException {
        Box box = new Box();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch mayWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            int old = box.count;
            bothRead.countDown();
            try {
                mayWrite.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
            box.count = old + 1;
        };

        Thread a = new Thread(increment, "A");
        Thread b = new Thread(increment, "B");
        a.start();
        b.start();

        bothRead.await();
        mayWrite.countDown();
        a.join();
        b.join();

        System.out.println("Correct total: 2");
        System.out.println("Actual total: " + box.count);
    }
}
```

Biên dịch và chạy:

```bash
javac ForcedLostUpdate.java
java ForcedLostUpdate
```

Đầu ra khi chạy hoàn tất bình thường:

```text
Correct total: 2
Actual total: 1
```

Cả hai worker đọc 0 **trước** khi gọi `bothRead.countDown()`. Main chỉ mở `mayWrite` sau khi cả hai đã đến mốc này. Do đó hai worker đều ghi `old + 1` tức 1, bất kể ai ghi trước. Hai lần ghi cùng biến thường không được sắp thứ tự happens-before với nhau, nên có data race; `join()` chỉ bảo đảm main chờ và thấy các tác dụng của worker sau khi chúng kết thúc. Kết quả 1 ở đây là do thiết kế lịch xen kẽ có kiểm soát, không phải lời hứa rằng mọi chương trình dùng `count++` đều trả 1.

**Bài học:** dùng latch để tái hiện lịch xen kẽ là công cụ kiểm thử tốt, nhưng bản thân latch trong ví dụ cố ý **không** bảo vệ phép tăng; tất cả thread đã qua rào mới cùng ghi giá trị cũ.

## 5. Java 17+: sửa bằng phép tăng atomic

Tạo file `AtomicCounterDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger count = new AtomicInteger();

        Runnable increment = () -> {
            for (int i = 0; i < 10_000; i++) {
                count.incrementAndGet();
            }
        };

        Thread a = new Thread(increment, "A");
        Thread b = new Thread(increment, "B");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Final count: " + count.get());
    }
}
```

Chạy:

```bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
```

Đầu ra:

```text
Final count: 20000
```

`AtomicInteger.incrementAndGet()` là phép tăng nguyên tử: không thể có hai lần cập nhật thành công dựa trên cùng trạng thái cũ theo cách làm mất lượt tăng. Hai thread vẫn chạy theo thứ tự tùy scheduler, nhưng kết quả cuối được bảo đảm. `join()` giúp main chỉ đọc sau khi cả hai hoàn tất.

Nếu nhiều trường phải thay đổi cùng nhau theo một bất biến (ví dụ số lượng và trạng thái đơn hàng), nhiều `AtomicInteger` riêng lẻ **không** tự tạo transaction. Khi đó cần lock chung, CAS trên một đối tượng trạng thái bất biến hoặc giao thức khác bao phủ toàn bộ bất biến.

### Khi dùng `synchronized`?

```java
final class SafeCounter {
    private int value;

    public synchronized void increment() {
        value++;
    }

    public synchronized int get() {
        return value;
    }
}
```

Đây là class phụ trợ **không có main độc lập**. Các lời gọi sử dụng cùng monitor của đối tượng `SafeCounter`, nên không có hai thread đồng thời thực hiện phần tăng trên cùng đối tượng. `get()` cũng dùng monitor đó, đảm bảo quan hệ happens-before qua mở/đóng khóa. Nếu code bên ngoài có đường đọc/ghi không tuân theo cùng khóa, thiết kế vẫn có lỗ hổng.

## 6. Happens-before là nền tảng của visibility và ordering

JMM dùng **happens-before (HB)** để chỉ quan hệ thứ tự một phần giữa các hành động. Một số quy tắc quan trọng:

| Nguồn quan hệ | Bảo đảm chính |
| --- | --- |
| **Program order** | Trong một thread, hành động trước trong thứ tự chương trình HB hành động sau |
| `Thread.start()` | Lời gọi start trên thread HB hành động trong thread mới |
| `Thread.join()` thành công | Hành động của worker HB việc thread khác phát hiện worker đã kết thúc |
| Monitor `synchronized` | Unlock một monitor HB lần lock tiếp theo trên **cùng monitor** |
| Trường `volatile` | Ghi volatile HB lần đọc volatile tiếp theo của **cùng trường** theo synchronization order |
| `CountDownLatch` | Các hành động trước `countDown()` HB hành động sau `await()` thành công |
| Thư viện concurrent | `BlockingQueue`, `Future`, `Executor` và các primitive khác có memory-consistency guarantees trong hợp đồng API |

Quan hệ HB có **tính bắc cầu**. Nếu A HB B và B HB C thì A HB C; nhờ vậy ghi dữ liệu thường trước một tín hiệu volatile có thể được công bố tới reader sau khi reader đọc tín hiệu thích hợp.

HB là quan hệ về ngữ nghĩa quan sát, **không đơn thuần** là “A được CPU chạy vật lý trước B”. Khi main gọi `a.start(); b.start();`, không có bảo đảm mọi hành động của A sẽ xảy ra trước mọi hành động của B. Khi main lần lượt `a.join(); b.join();`, main có thể thấy kết quả của cả hai, nhưng việc join **không tự sắp thứ tự toàn bộ thao tác giữa A và B**.

**Lưu ý:** `Thread.sleep()`, `Thread.yield()`, `setPriority()` và việc in log không nên dùng như primitive đồng bộ dữ liệu. Chúng có thể thay đổi timing, nhưng không thay thế quan hệ HB cần thiết.

## 7. Java 17+: công bố an toàn một kết quả chưa volatile

Nếu một thread chỉ cần thông báo đã tạo xong kết quả, `CountDownLatch` diễn đạt sự kiện tốt hơn vòng spin tự viết.

Tạo file `SafePublicationDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class SafePublicationDemo {
    private static int result;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread producer = new Thread(() -> {
            result = 42;
            ready.countDown();
        }, "producer");

        producer.start();
        ready.await();
        System.out.println("Result: " + result);
        producer.join();
    }
}
```

Chạy:

```bash
javac SafePublicationDemo.java
java SafePublicationDemo
```

Đầu ra:

```text
Result: 42
```

Writer ghi `result = 42` trước `countDown()`. Khi `ready.await()` trở về thành công, các hành động trước `countDown()` happens-before những hành động sau `await()`. Vì thế main nhìn thấy 42 ngay sau await dù `result` là trường thường. `join()` cuối cùng nhằm xác nhận vòng đời producer đã kết thúc, không phải điều kiện duy nhất tạo visibility trong ví dụ.

Có thể dùng một cờ `volatile boolean ready` cho giao thức single-writer công bố một lần:

```java
// Ý tưởng về hai trường của cùng đối tượng:
private int payload;
private volatile boolean ready;

// Writer: payload = 42; ready = true;
// Reader: if (ready) System.out.println(payload);
```

Đây là **snippet ý tưởng**, không phải file Java độc lập. Nếu reader quan sát ghi volatile `ready = true` phù hợp, những ghi trước đó trong writer có quan hệ HB với đọc sau cờ của reader. Nhưng volatile không làm các thao tác cập nhật nhiều trường thành atomic, và không nên lạm dụng busy-wait nếu có thể dùng latch hoặc queue.

## 8. Kết quả cả hai thread cùng đọc 0: ví dụ store buffering

Xét hai trường `int x = 0` và `int y = 0`, không đồng bộ:

```text
Thread A              Thread B
--------              --------
x = 1                 y = 1
r1 = y                r2 = x
```

Nếu cố áp đặt một thứ tự xen kẽ tuần tự duy nhất cho bốn thao tác, không thể có đồng thời `r1 == 0` và `r2 == 0`: để A đọc y bằng 0 thì A phải đọc trước khi B ghi y; để B đọc x bằng 0 thì B phải đọc trước khi A ghi x, tạo vòng mâu thuẫn với thứ tự lệnh nội bộ mỗi thread.

Nhưng trong chương trình **có data race**, JMM cho phép kết quả `r1 == 0, r2 == 0` của bài toán store buffering này. Do đó không thể phân tích mọi chương trình racy bằng cách chỉ hoán vị những dòng mã nguồn thành một lịch tuần tự trực giác. Trình biên dịch, JIT, cache và phần cứng có thể áp dụng tối ưu hóa trong giới hạn đặc tả.

Đây là ví dụ **về kết quả được phép**, không phải kết quả đảm bảo xuất hiện trên một JVM, máy hoặc một lần chạy cụ thể. Nếu cả x và y là volatile, kết quả “cả hai đọc 0” bị loại bởi thứ tự đồng bộ nhất quán dành cho các truy cập volatile trong tình huống này. Điều đó **không** có nghĩa bất kỳ thuật toán nào có nhiều trường volatile cũng tạo thành transaction.

## 9. Java data race không tương đương hoàn toàn với undefined behavior của C/C++

Không nên dùng một câu “mọi thứ đều có thể xảy ra” để mô tả JMM. Java vẫn có các quy tắc ràng buộc giá trị mà phép đọc được phép quan sát, kể cả trong chương trình có data race. Tuy nhiên, **tập kết quả hợp lệ rộng hơn** và có thể rất khác với cách lập trình viên suy luận theo một lịch xen kẽ đơn giản. Vì vậy chương trình racy vẫn không đáng tin cậy.

Một nguyên tắc quan trọng là **data-race-free ⇒ sequentially consistent** trong phạm vi các điều kiện của JMM: khi truy cập dữ liệu được đồng bộ đúng, người lập trình có thể suy luận thuận tiện hơn theo một lịch xen kẽ tuần tự. Nhưng **sequential consistency không làm tất cả thao tác nhiều bước trở thành atomic**: thuật toán vẫn phải bảo vệ từng bất biến riêng.

### Trường `long` và `double` không volatile

Đặc tả Java cho phép một số triển khai coi đọc/ghi các trường `long` hoặc `double` không volatile theo hai nửa 32-bit, có khả năng quan sát giá trị **torn** khi truy cập chia sẻ không đồng bộ. Nhiều JVM hiện đại cung cấp tính atomic trong thực tế, nhưng code cần tính portable không nên dựa vào tình cờ đó. `volatile long`/`volatile double` có bảo đảm atomic cho từng thao tác đọc/ghi, còn `AtomicLong` phù hợp cho tăng/cập nhật nguyên tử.

Tính atomic của **một phép đọc hoặc ghi** không tương đương tính nguyên tử của **toàn bộ thuật toán**.

## 10. Final, immutable data và safe publication

Giảm shared mutable state là cách hữu ích để giảm nguy cơ race. Trường `final` được gán trong quá trình khởi tạo đúng có những bảo đảm đặc biệt của JMM, đặc biệt khi `this` không thoát ra cho thread khác trước khi constructor kết thúc.

```java
final class Snapshot {
    final int id;
    final String label;

    Snapshot(int id, String label) {
        this.id = id;
        this.label = label;
    }
}
```

Đây là class phụ trợ, không có main. `String` là immutable, nên một snapshot gồm các giá trị như trên dễ chia sẻ hơn đối tượng liên tục đổi trạng thái. Nhưng `final` không biến những object mutable được một trường tham chiếu đến thành bất biến; cũng không thay thế việc xuất bản tham chiếu bằng giao thức phù hợp.

Các cách công bố phổ biến là đặt tham chiếu qua `volatile` field, `AtomicReference`, `BlockingQueue`, `synchronized` hoặc tạo thread sau khi object đã được xây dựng xong. Tránh khởi động thread bên trong constructor rồi để `this` lọt ra trong khi trạng thái chưa đầy đủ.

## 11. Chọn cơ chế đồng bộ theo mục tiêu

| Nhu cầu | Công cụ Java phù hợp | Điều cần lưu ý |
| --- | --- | --- |
| Chờ thread khác kết thúc | `Thread.join()` | Join có timeout có thể trở về khi thread chưa kết thúc |
| Công bố một tín hiệu hoàn tất | `CountDownLatch`, `Future` | Cần xử lý interrupt, timeout, lỗi task |
| Cờ chia sẻ đơn giản theo giao thức rõ | `volatile boolean` | Visibility/ordering, không thay thế nguyên tử tính |
| Bộ đếm cần tăng đúng | `AtomicInteger` | `counter++` trên volatile vẫn có thể mất cập nhật |
| Nhiều trường cùng một bất biến | `synchronized`, `Lock` | Toàn bộ đường đọc/ghi liên quan phải dùng cùng giao thức |
| Chuyển dữ liệu giữa producer/consumer | `BlockingQueue` | Truyền quyền sở hữu và memory-consistency effects |
| Trạng thái theo key | `ConcurrentHashMap` | Phân biệt thao tác atomic của API và chuỗi nhiều lời gọi |
| Snapshot chỉ đọc | Immutable object + safe publication | Không sửa object sau khi công bố; tránh constructor escape |

API chỉ an toàn trong phạm vi **hợp đồng cụ thể**. Ví dụ `ConcurrentHashMap.containsKey()` rồi `put()` là hai thao tác riêng; nếu cần “chưa có thì đặt” nguyên tử, dùng `putIfAbsent()` hoặc API phù hợp thay vì tách check–act.

## 12. Kiểm thử và chẩn đoán

1. **Liệt kê shared mutable state:** trường instance/static, mảng, collection, object được nhiều thread tham chiếu.
2. **Tìm conflicting accesses:** có ít nhất một writer không, và đọc/ghi từ thread khác có được sắp thứ tự HB không?
3. **Nêu bất biến cần giữ:** không mất cập nhật, không đọc dữ liệu trước khi công bố, không để kết quả trung gian bị dùng.
4. **Tạo interleaving trong test:** `CountDownLatch` hoặc `CyclicBarrier` buộc các worker tới cùng một mốc để tái hiện race; không dùng sleep tùy ý làm “bản sửa”.
5. **Stress test ở nhiều mức tải:** tăng số worker, dữ liệu và thay đổi môi trường. Không lỗi trong 10.000 lượt **không chứng minh** chương trình không có data race.
6. **Dùng công cụ đúng việc:** jcstress (OpenJDK) có thể kiểm tra tập kết quả của những litmus test concurrency; JFR, thread dump và profiler có ích cho lock contention và trạng thái runtime. Các công cụ không thay việc phân tích theo JMM.
7. **Đánh giá cả đường lỗi:** một thread chết trước khi `countDown()` có thể khiến thread khác đợi vô hạn; thiết kế timeout, interrupt và xử lý lỗi đúng với nghiệp vụ.

## 13. Các hiểu nhầm thường gặp

- **“Một lần chạy đúng chứng minh không có data race.”** Sai; lỗi phụ thuộc lịch chạy và hành vi quan sát có thể rất hiếm.
- **“Volatile giải quyết mọi race.”** Sai; `counter++` vẫn là read–modify–write.
- **“`sleep(100)` bảo đảm worker đã ghi xong.”** Sai; sleep không đợi điều kiện thật và không tạo happens-before.
- **“Một thread start trước nên ghi của nó chắc chắn xuất hiện trước thread start sau.”** Sai; start chỉ xác định quan hệ từ thread gọi tới thread mới, không sắp thứ tự toàn bộ hành động của hai worker.
- **“Atomic từng trường đồng nghĩa atomic một transaction nhiều trường.”** Sai; cần bảo vệ toàn bộ bất biến.
- **“Đặt lock ở writer là đủ.”** Sai nếu reader còn đọc không đồng bộ và không có cơ chế publication/visibility phù hợp.
- **“Data race lúc nào cũng cho giá trị ngẫu nhiên bất kỳ.”** Sai; JMM ràng buộc các quan sát hợp lệ, dù tập kết quả rộng và khó suy luận.
- **“Không còn data race thì mọi logic concurrent đều đúng.”** Sai; lỗi check-then-act nhiều bước vẫn có thể xảy ra khi mỗi truy cập riêng đều atomic.

## 14. Checklist thực hành

Trước khi chấp nhận mã chia sẻ dữ liệu giữa các thread, hãy tự hỏi:

1. Biến nào mutable, biến nào được chia sẻ và thread nào đọc/ghi?
2. Có cặp truy cập xung đột không được thứ tự hóa bởi happens-before?
3. Yêu cầu là nhìn thấy dữ liệu đã publish, hay thực hiện cả chuỗi cập nhật nguyên tử?
4. Đã chọn đúng primitive: volatile, atomic, latch, lock, queue, Future hoặc immutable snapshot?
5. Mọi đường ghi/đọc liên quan có tuân thủ cùng giao thức?
6. Timeout, interrupt và lỗi task có làm thiếu tín hiệu hay đọc trạng thái dở dang không?
7. Kết quả được cam kết có đúng dưới **mọi lịch chạy và quan sát hợp lệ** của JMM?

**Ghi nhớ:** data race là các truy cập xung đột không có thứ tự happens-before phù hợp; nó cho phép những hành vi quan sát khác với trực giác đọc mã tuần tự. Hãy thiết kế quan hệ đồng bộ rõ ràng và bảo vệ tính nguyên tử của bất biến, thay vì kỳ vọng scheduler sẽ chạy các thread theo thứ tự mong muốn.