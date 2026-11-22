# So sánh bộ đếm thường, atomic và adder trong Java

## 1. Vấn đề cần giải quyết

Giả sử ứng dụng có bốn luồng, mỗi luồng xử lý 100.000 sự kiện và phải tăng một bộ đếm chung. **Giá trị mong đợi là 400.000**, bất kể lịch chạy các luồng. Ba cách tiếp cận thường gặp là:

- **Bộ đếm thường:** biến `int` hoặc `long` được cập nhật bằng `count++`. Đơn giản và phù hợp khi chỉ một luồng sở hữu dữ liệu, nhưng **không an toàn** nếu nhiều luồng cùng tăng mà không đồng bộ.
- **Bộ đếm atomic:** `AtomicInteger` hoặc `AtomicLong`. Cung cấp thao tác đọc, tăng, cộng và so sánh-đổi có tính nguyên tử đối với một giá trị chung.
- **Bộ đếm adder:** `LongAdder`. Cho phép nhiều luồng cộng vào bộ đếm, có thể phân tán cập nhật trên nhiều ô để giảm contention; tổng được tính khi cần quan sát.

Một đối chứng rất quan trọng là **bộ đếm thường được bảo vệ bằng `synchronized`**. Đây vẫn là bộ đếm primitive nhưng có một khóa bảo vệ mọi truy cập phù hợp, nên có thể hoàn toàn đúng. Sự khác biệt là *plain unprotected* so với *plain protected*, không phải cứ dùng primitive thì luôn sai.

Cần trả lời cả ba câu hỏi: **Kết quả có đúng khi chạy đồng thời? Mỗi lần đọc có yêu cầu là snapshot nguyên tử không? Và hiệu năng có thật sự tốt hơn trên workload thực?**

## 2. Tại sao count++ có thể làm mất lượt tăng?

~~~java
class Counter {
    long count;

    void increment() {
        count++; // KHÔNG atomic khi nhiều luồng cùng ghi
    }
}
~~~

`count++` là một biểu thức ngắn, nhưng về ngữ nghĩa nó gồm:

1. Đọc giá trị cũ.
2. Tính giá trị cũ cộng 1.
3. Ghi giá trị mới trở lại.

Khi hai luồng cùng thấy `count == 5`, cả hai tính 6 và cả hai ghi 6, tổng chỉ tăng một lần thay vì hai. Đây là *lost update*, một dạng **race condition**.

| Thời điểm | Luồng A | Luồng B | Giá trị lưu |
| --- | --- | --- | ---: |
| 0 | — | — | 5 |
| 1 | Đọc 5 | — | 5 |
| 2 | — | Đọc 5 | 5 |
| 3 | Tính 6 | — | 5 |
| 4 | — | Tính 6 | 5 |
| 5 | Ghi 6 | — | 6 |
| 6 | — | Ghi 6 | 6 |

Đoạn chương trình thực tế có thể luôn in ra số mong đợi trong một vài lượt thử, nhưng điều đó **không chứng minh thread safety**. Lịch xen kẽ khác, số lõi khác hoặc tối ưu JVM khác có thể bộc lộ race.

### Volatile không sửa được ++

~~~java
class Counter {
    volatile long count;

    void increment() {
        count++; // vẫn có thể lost update
    }
}
~~~

`volatile` cung cấp ngữ nghĩa visibility và ordering cho các thao tác trên biến theo Java Memory Model. Nó **không gộp đọc–cộng–ghi thành một thao tác nguyên tử**. Hai luồng vẫn có thể đọc cùng giá trị rồi ghi cùng kết quả. Không dùng `Thread.sleep` hay thêm độ trễ để sửa race: chúng chỉ thay đổi timing.

Nếu bộ đếm **hoàn toàn thuộc về một luồng**, biến thường là lựa chọn tốt; không phải mọi biến đếm đều cần atomic.

## 3. Bảng so sánh hành vi

| Tiêu chí | `long count++` không đồng bộ | `AtomicLong` | `LongAdder` |
| --- | --- | --- | --- |
| Tăng từ nhiều luồng mà không mất lượt? | **Không** | Có | Có |
| Giá trị đọc tức thời có ngữ nghĩa atomic? | Không đảm bảo | `get()` có | `sum()` không phải snapshot atomic |
| Lấy giá trị trước/sau mỗi lượt tăng? | Không an toàn nếu chia sẻ | Có: `getAndIncrement`, `incrementAndGet` | Không |
| So sánh-và-đổi một giá trị? | Không | Có: `compareAndSet` | Không |
| Khi contention tăng cao | Sai về logic | Cạnh tranh cập nhật cùng một trạng thái | Có thể phân tán cập nhật để tăng throughput |
| Chi phí bộ nhớ | Rất nhỏ | Đối tượng chứa trạng thái atomic | Có thể lớn hơn vì các ô phụ |
| Trường hợp thường phù hợp | Single-thread hoặc đồng bộ từ bên ngoài | Cần linearizable operation/CAS/ID | Metrics, nhiều updates, ít đọc chính xác tức thời |

**Không suy từ bảng thành thứ tự tốc độ cố định.** `AtomicLong` có thể nhanh hơn hoặc tương đương `LongAdder` ở contention thấp; `synchronized` cũng có thể đủ nhanh. Chỉ benchmark đúng workload mới kết luận được.

## 4. AtomicInteger và AtomicLong

### 4.1. Phương thức cơ bản

~~~java
import java.util.concurrent.atomic.AtomicLong;

AtomicLong count = new AtomicLong(0);

long afterFirst = count.incrementAndGet(); // 1
long beforeSecond = count.getAndIncrement(); // 1
long current = count.get(); // 2
long afterAdd = count.addAndGet(10); // 12
~~~

Tên phương thức thể hiện giá trị trả về:

- `incrementAndGet()`: tăng, sau đó trả giá trị mới.
- `getAndIncrement()`: trả giá trị cũ, sau đó tăng.
- `addAndGet(delta)`: cộng, sau đó trả giá trị mới.
- `getAndAdd(delta)`: trả giá trị cũ, sau đó cộng.
- `get()` và `set(...)`: đọc/ghi một giá trị chung.
- `compareAndSet(expected, update)`: cập nhật chỉ nếu giá trị hiện tại bằng expected, trả `true` khi thành công.

`AtomicInteger` cung cấp biến thể 32 bit với tên phương thức tương tự. `AtomicLong` dùng 64 bit, phù hợp bộ đếm có thể vượt `Integer.MAX_VALUE`.

### 4.2. Vì sao không mất update?

Các phép tăng atomic được đồng bộ bởi cơ chế mà JVM/phần cứng cung cấp, thường dựa trên **CAS (compare-and-swap)** hoặc một thao tác phần cứng tương đương. Khi hai luồng cùng tăng từ 5, chỉ một luồng có thể cập nhật thành 6 trước; luồng còn lại phải làm việc với trạng thái mới và cập nhật thành 7.

Về hợp đồng, mỗi thao tác atomic có thể được hiểu như xảy ra ở **một điểm nguyên tử** (*linearization point*) đối với biến. Về hiệu năng, nhiều luồng cùng cạnh tranh một trạng thái có thể khiến các thao tác CAS phải thử lại; bởi vậy contention có thể gây chi phí.

Không nên mặc định mọi JDK hay CPU chạy cùng một chuỗi lệnh máy; người lập trình dựa vào hợp đồng API, không dựa vào giả định cách triển khai cụ thể.

### 4.3. Một phép get và một phép increment không tạo giao dịch

~~~java
if (count.get() < 100) {
    count.incrementAndGet();
}
~~~

Dù hai lời gọi **đều atomic riêng lẻ**, toàn bộ cặp “kiểm tra rồi tăng” **không atomic**. Hai luồng có thể cùng đọc 99, cùng thấy điều kiện đúng rồi đưa kết quả thành 101.

Muốn giới hạn chặt, dùng một vòng lặp CAS:

~~~java
static boolean tryIncrementBelow(
        AtomicLong counter, long limit) {
    while (true) {
        long current = counter.get();
        if (current >= limit) {
            return false;
        }
        long next = current + 1;
        if (counter.compareAndSet(current, next)) {
            return true;
        }
    }
}
~~~

Đây là phương thức minh họa đặt trong một lớp có import `AtomicLong`. Nếu `current < limit` và `limit` là giá trị long hợp lệ, `current + 1` không tràn. Để giữ invariant, các luồng sửa cùng bộ đếm phải tuân thủ giao thức cập nhật tương thích.

`AtomicLong.updateAndGet(fn)` cũng hỗ trợ hàm cập nhật, nhưng hàm có thể chạy lại khi CAS thất bại: **không đặt side effect** như ghi cơ sở dữ liệu hoặc gửi thông báo trong `fn`.

### 4.4. Khi nào chọn Atomic?

- Cần phát hành số thứ tự theo từng increment, ví dụ `getAndIncrement()` trong phạm vi không tràn.
- Cần giá trị snapshot tại một thời điểm logic cho **một biến**.
- Cần CAS, cập nhật có điều kiện, `getAndSet` hoặc quản lý trạng thái có mối liên hệ chặt với từng thao tác.
- Contention không quá cao hoặc đã đo thấy atomic đạt yêu cầu.

Atomic cho một biến không tự bảo vệ invariant trải trên **nhiều biến độc lập**. Nếu hai trường phải đổi cùng lúc như một giao dịch, cần đồng bộ phù hợp hoặc đóng gói toàn bộ trạng thái thành một đối tượng immutable được cập nhật qua một `AtomicReference`.

## 5. LongAdder: giảm tranh chấp cập nhật

### 5.1. Cách dùng

~~~java
import java.util.concurrent.atomic.LongAdder;

LongAdder requests = new LongAdder();

requests.increment(); // +1
requests.add(5);      // +5
requests.decrement(); // -1

long total = requests.sum(); // 5 nếu không có update đồng thời khác
~~~

`LongAdder` duy trì giá trị logic như một tổng, nhưng có thể sử dụng nhiều **ô đếm nội bộ**. Dưới contention, các luồng không nhất thiết đều cập nhật cùng một ô. Điều này có thể tăng throughput cho metric dạng “chỉ cần ghi rất nhiều, đọc thỉnh thoảng”.

Nó không thay thế mọi vai trò của atomic vì đánh đổi cơ chế quan sát giá trị.

### 5.2. sum() không phải snapshot nguyên tử khi đang cập nhật

Khi gọi `sum()`, LongAdder tính tổng các ô. Nếu luồng khác vẫn đang tăng, những ô khác nhau có thể được đọc ở **những thời điểm khác nhau**. Vì vậy:

- `sum()` hữu ích cho metric gần thời gian thực.
- `sum()` **không linearizable** như `AtomicLong.get()`.
- Không dùng một phép `sum()` để thực thi giới hạn quota cần kiểm tra–cập nhật nguyên tử.
- Khi **mọi cập nhật đã kết thúc** và được đồng bộ đúng, `sum()` trả tổng cuối chính xác.

Trong chương trình phần 7, tất cả thread đã được `join()` trước khi gọi `sum()`.

### 5.3. Không dùng adder để cấp ID

Đoạn sau **sai về tính duy nhất**:

~~~java
long id = requests.sum();
requests.increment();
~~~

Hai thread có thể cùng đọc tổng trước khi tăng và nhận cùng id. LongAdder đảm bảo không mất phép cộng, **không cung cấp số trước/sau từng phép tăng**. Dùng `AtomicLong.getAndIncrement()` khi cần cấp số dựa trên một trạng thái trong JVM, đồng thời quản lý overflow và yêu cầu phối hợp giữa nhiều JVM.

### 5.4. reset và sumThenReset

~~~java
long sinceLastCheck = requests.sumThenReset();
~~~

`sumThenReset()` hữu ích cho thu số liệu từng giai đoạn khi đã bảo đảm **không có update đồng thời**. Đây không phải snapshot-và-reset nguyên tử với các increment đang tiếp tục. Nếu reset trong lúc các luồng tăng, một số cập nhật có thể không được phân vào các kỳ thống kê như mong đợi.

Khi cần phân kỳ chính xác, thiết kế giao thức dừng/giao nhận update, khóa, hai bucket được chuyển đổi có đồng bộ, hoặc ghi sự kiện theo timestamp phù hợp. Không coi `sumThenReset()` là phép “chốt sổ” an toàn cho mọi concurrency.

### 5.5. Các biến thể liên quan

`DoubleAdder` hỗ trợ cộng các giá trị `double` nhưng vẫn có các vấn đề làm tròn nhị phân; không dùng nó thay `BigDecimal` khi tiền phải chính xác theo quy tắc decimal. `LongAccumulator` áp một hàm kết hợp với identity cho một số phép tổng hợp khác ngoài cộng.

## 6. Bộ đếm synchronized: một đối chứng an toàn

~~~java
class LockedCounter {
    private long count;

    synchronized void increment() {
        count++;
    }

    synchronized long get() {
        return count;
    }
}
~~~

`synchronized` bảo đảm chỉ một thread tại một thời điểm thực thi critical section dưới cùng monitor. Lời gọi `get()` cũng dùng monitor ấy, nên có cơ chế visibility phù hợp.

Cách này có thể tốt khi cần:

- Mã đơn giản, dễ chứng minh tính đúng đắn.
- Một nhóm trường chung cần giữ invariant.
- Logic cập nhật gồm nhiều bước, không chỉ phép cộng.
- Contention thấp hoặc chưa phải bottleneck sau khi đo.

Không nên bảo vệ `increment()` bằng khóa nhưng lại để một đường đọc/ghi khác truy cập `count` không có đồng bộ tương ứng. Khi có nhiều đường cập nhật, tất cả phải theo cùng giao thức bảo vệ.

## 7. Ví dụ Java 17+ có kết quả xác định

Ở một stress test thuần túy, `count++` có thể sai hoặc tình cờ đúng tùy lịch thread, khiến stdout không cố định. Vì vậy phần đầu chương trình **cố ý tách đọc và ghi** và cho cả hai thread đọc `0` trước khi ghi. Điều này mô phỏng đúng cơ chế mất update của `count++`, đồng thời cho kết quả chắc chắn.

Phần thứ hai có bốn thread, mỗi thread tăng ba counter an toàn 100.000 lần. Chỉ sau khi các thread hoàn thành, main mới đọc tổng.

Tạo file **`CounterComparisonDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public class CounterComparisonDemo {
    static class PlainCounter {
        int count;
    }

    static class LockedCounter {
        private long count;

        synchronized void increment() {
            count++;
        }

        synchronized long get() {
            return count;
        }
    }

    static int forcedLostUpdate() throws InterruptedException {
        PlainCounter counter = new PlainCounter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch go = new CountDownLatch(1);

        Runnable task = () -> {
            int snapshot = counter.count;
            bothRead.countDown();

            try {
                go.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return;
            }

            counter.count = snapshot + 1;
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);
        a.start();
        b.start();

        bothRead.await();
        go.countDown();

        a.join();
        b.join();
        return counter.count;
    }

    public static void main(String[] args)
            throws InterruptedException {
        System.out.println("plain forced collision: "
                + forcedLostUpdate() + " (expected 2)");

        final int threads = 4;
        final int repeats = 100_000;

        AtomicLong atomic = new AtomicLong();
        LongAdder adder = new LongAdder();
        LockedCounter locked = new LockedCounter();

        Thread[] workers = new Thread[threads];
        CountDownLatch start = new CountDownLatch(1);

        for (int i = 0; i < threads; i++) {
            workers[i] = new Thread(() -> {
                try {
                    start.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }

                for (int n = 0; n < repeats; n++) {
                    atomic.incrementAndGet();
                    adder.increment();
                    locked.increment();
                }
            });
            workers[i].start();
        }

        start.countDown();

        for (Thread worker : workers) {
            worker.join();
        }

        long expected = (long) threads * repeats;
        System.out.println("expected: " + expected);
        System.out.println("atomic after join: " + atomic.get());
        System.out.println("adder after join: " + adder.sum());
        System.out.println("locked after join: " + locked.get());
        System.out.println("all safe counters exact: "
                + (atomic.get() == expected
                && adder.sum() == expected
                && locked.get() == expected));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CounterComparisonDemo.java
java CounterComparisonDemo
~~~

Stdout (đã đối chiếu với Java):

~~~text
plain forced collision: 1 (expected 2)
expected: 400000
atomic after join: 400000
adder after join: 400000
locked after join: 400000
all safe counters exact: true
~~~

**Cách giải thích:** `CountDownLatch` trong `forcedLostUpdate` chỉ điều phối hai thread để cả hai cùng đọc trước khi được phép ghi; nó không giúp bộ đếm nguyên tử. Vì cả hai snapshot đều bằng 0, cả hai cùng ghi 1, và kết quả là 1 thay vì 2. Chương trình minh họa *lost update* có thể tái lập; nếu thay bằng `count++` tự do, việc lỗi có xuất hiện ở lần chạy cụ thể không thể cam kết.

Ba bộ đếm còn lại hoàn tất 400.000 increments chính xác. `join()` bảo đảm luồng đã kết thúc trước khi kiểm tổng. Việc đặt cùng ba counter trong một vòng lặp **chỉ để kiểm đúng/sai**, không phải một benchmark tốc độ, vì sự hiện diện của synchronized và các primitive đồng bộ ảnh hưởng scheduling và tương tác CPU.

## 8. Atomic và Adder không ngăn tràn kiểu số

Thread-safe nghĩa là các lượt cập nhật không mất vì race, **không có nghĩa kết quả nằm trong phạm vi kiểu**.

~~~java
AtomicLong atomic = new AtomicLong(Long.MAX_VALUE);
long wrapped = atomic.incrementAndGet();
// Long.MIN_VALUE do tràn long
~~~

`AtomicInteger` cũng có thể tràn `int`. `LongAdder` dùng giá trị long, nên vẫn cần chính sách riêng khi tổng có thể vượt phạm vi long.

Nếu tràn là lỗi, một hướng trên AtomicLong:

~~~java
AtomicLong safe = new AtomicLong(Long.MAX_VALUE - 1);

long max = safe.updateAndGet(Math::incrementExact);
// Long.MAX_VALUE

// Lần tiếp theo ném ArithmeticException:
// safe.updateAndGet(Math::incrementExact);
~~~

`Math.incrementExact` sẽ ném lỗi thay vì wrap. Hàm cập nhật phải **không có side effect**, vì `updateAndGet` có thể gọi lại khi CAS không thành công. Đây là một cơ chế phù hợp cho tính đúng đắn khi workload/contract cho phép, không phải tuyên bố rằng mọi bộ đếm cần dùng chính xác mẫu này.

Nếu giá trị hợp lệ có thể lớn hơn `Long.MAX_VALUE`, cân nhắc mô hình dùng `BigInteger` với cơ chế đồng bộ được thiết kế rõ; `LongAdder` không phải dạng arbitrary-precision.

## 9. Snapshot và ranh giới quan sát

### 9.1. AtomicLong.get()

`AtomicLong.get()` đọc một giá trị atomic, có ngữ nghĩa linearizable đối với trạng thái của biến đó. Tuy nhiên:

~~~java
long first = atomic.get();
long second = atomic.get();
~~~

hai lần đọc có thể khác nhau vì thread khác tăng ở giữa. **Một thao tác atomic không tự biến mọi chuỗi thao tác liên tiếp thành giao dịch**.

### 9.2. LongAdder.sum()

`sum()` có thể đọc những ô nội bộ tại các thời điểm khác nhau khi updates còn diễn ra. Nó phù hợp metric gần thời gian thực, nhưng không phù hợp cho kiểm tra quota cần chính xác nguyên tử.

Khi các worker đã kết thúc, `join()` và cơ chế đồng bộ tương ứng đảm bảo thay đổi của chúng được quan sát đúng, và `sum()` cho tổng cuối. Đây là điều kiện quan trọng để viết test chính xác cho LongAdder.

### 9.3. Một JVM khác nhiều JVM

`AtomicLong` hoặc `LongAdder` chỉ đồng bộ trạng thái trong **cùng một object/JVM**. Nếu ứng dụng có ba instance trên ba server, mỗi instance có counter riêng; không tự có một bộ đếm toàn cục. Cần thiết kế hệ thống phân tán, cơ sở dữ liệu, event stream hay dịch vụ cấp ID theo yêu cầu nếu phải thống nhất liên node.

## 10. Hiệu năng: đừng chỉ đo thời gian một vòng lặp

Các yếu tố cần quan sát:

- **Contention:** nhiều luồng cùng muốn cập nhật.
- **Throughput:** lượt increment mỗi giây.
- **Latency:** độ trễ mỗi thao tác và phân phối đuôi.
- **Memory footprint:** AtomicLong thường gọn hơn LongAdder đã phải mở rộng nhiều ô.
- **Read frequency:** với LongAdder, việc gọi `sum()` thường xuyên làm thay đổi tỷ lệ chi phí đọc/ghi.
- **Thread scheduling, JIT, GC, CPU topology:** ảnh hưởng lớn đến microbenchmark.

Không có công thức “LongAdder luôn nhanh gấp N lần AtomicLong”. Dưới contention cao và đọc ít, LongAdder thường có ưu thế throughput. Với ít luồng, chi phí phân tán/thu tổng có thể không đáng, AtomicLong đơn giản hơn. Khi cần invariant phức tạp, `synchronized` có thể là thiết kế đúng ngay cả khi thao tác khóa có chi phí.

### 10.1. Cách benchmark bằng JMH

**JMH (Java Microbenchmark Harness)** phù hợp hơn một phép đo `System.nanoTime()` duy nhất. Một benchmark có ý nghĩa cần:

1. Tách riêng ba benchmark `plain/AtomicLong/LongAdder` hoặc `synchronized` theo mục tiêu, không cập nhật tất cả trong cùng một vòng.
2. Thử nhiều số lượng thread: 1, 2, 4, 8... theo tải thực tế.
3. Bảo đảm counter thực sự chia sẻ giữa các thread trong bài test contention.
4. Dùng warmup, nhiều iteration/fork và tiêu thụ kết quả để tránh tối ưu bỏ mã.
5. So cùng số lượng thao tác, cùng mô hình dữ liệu và cùng tần suất đọc.
6. Đo cả throughput, latency và footprint/GC nếu relevant.
7. Phân tích tính đúng đắn trước khi xem kết quả tốc độ.

Nếu một bộ đếm thường không đồng bộ cho throughput lớn vì bỏ mất update, nó **không phải giải pháp tương đương chức năng** để đem ra so tốc độ công bằng.

Ví dụ phần 7 cố ý chạy cùng ba phương án để kiểm chúng trả đúng tổng, **không dùng output đó làm kết luận phương án nào nhanh hơn**.

## 11. Kiểm thử đúng ngữ nghĩa

### 11.1. Test đơn luồng

~~~java
AtomicLong counter = new AtomicLong();

counter.incrementAndGet();
counter.addAndGet(4);
counter.decrementAndGet();
// counter.get() == 4
~~~

Đây là test chức năng cơ bản, **không đủ** xác nhận tính đúng khi nhiều thread cùng cập nhật.

### 11.2. Test đa luồng

Khởi tạo N thread, mỗi thread tăng M lần, chờ `join()` hoặc `Future.get()`, rồi so tổng:

\[
\text{expected}=N\times M.
\]

Đặt phép nhân kỳ vọng trong phạm vi đủ rộng:

~~~java
long expected = (long) threadCount * incrementsPerThread;
~~~

Nếu nhân hai biến int trước khi cast, kỳ vọng của test có thể tự tràn và gây kết luận sai. Với tập dữ liệu rất lớn, phải xét cả nguy cơ tràn long.

### 11.3. Stress test và lost update

Một stress test chạy hàng nghìn lần và chưa thấy lỗi **không chứng minh** `count++` an toàn. Có thể thêm test điều phối hai luồng như chương trình đã cho, hoặc dùng công cụ chuyên kiểm tra tương tác luồng (ví dụ jcstress) nếu bài toán phức tạp.

Với LongAdder, test nên yêu cầu **tổng chính xác sau khi tất cả updates kết thúc**, không yêu cầu `sum()` đang chạy đồng thời là một snapshot nguyên tử. Nếu hợp đồng cần reset từng kỳ chính xác, test phải kiểm cả ranh giới chuyển kỳ và updates đồng thời.

### 11.4. Test trường hợp nghiệp vụ đặc biệt

Kiểm tra thêm:

- Giá trị bắt đầu không phải 0.
- Increment và decrement, giá trị âm hợp lệ hay không.
- Tràn `Integer.MAX_VALUE`/`Long.MAX_VALUE` và chính sách lỗi.
- CAS thất bại khi có cạnh tranh, tính đúng của vòng retry.
- Điều kiện quota/giới hạn không bị vượt.
- Đọc đang diễn ra cùng cập nhật; phân biệt yêu cầu snapshot nguyên tử với metric gần đúng.
- Dừng worker, timeout và lỗi thread; không giả định mọi worker luôn hoàn thành trọn số lượt nếu có exception hoặc interruption.

## 12. Chọn phương án theo tình huống

| Yêu cầu chính | Gợi ý | Cần tránh |
| --- | --- | --- |
| Chỉ một thread hoặc dữ liệu local | `long` bình thường | Thêm đồng bộ không cần thiết |
| Nhiều thread, cần số trước/sau từng lượt | `AtomicLong` | Dùng `LongAdder.sum()` để cấp ID |
| Nhiều thread ghi metric, thỉnh thoảng đọc | `LongAdder` | Coi `sum()` là snapshot atomic |
| Kiểm tra ngưỡng cùng lúc với tăng | CAS loop hoặc khóa chung | `if(get < limit) increment()` |
| Nhiều trường cùng invariant | `synchronized`/lock hoặc mô hình trạng thái atomic đúng | Nghĩ atomic riêng lẻ tạo giao dịch |
| Cần reset đúng một ranh giới khi cập nhật liên tục | Protocol phân kỳ có đồng bộ | `sumThenReset()` không phối hợp |
| Cần phát hiện overflow | Exact arithmetic/policy giới hạn | Nghĩ atomic hoặc adder tự ngăn tràn |
| Nhiều server | Bộ đếm phân tán/DB/service thích hợp | Nghĩ atomic instance là global counter |

## 13. Các lỗi thường gặp

1. **Tin `count++` là nguyên tử vì chỉ một câu lệnh.** Nó có thể lost update.
2. **Thêm `volatile` rồi coi như đã thread-safe.** Volatile không tạo atomic read-modify-write.
3. **Dùng LongAdder để phát ID.** `sum()` và `increment()` không thành một giao dịch.
4. **Tin `LongAdder.sum()` là snapshot nguyên tử.** Khi updates đồng thời, tổng có thể không tương ứng một điểm quan sát.
5. **Dùng `sumThenReset()` khi threads còn cập nhật nhưng đòi chia kỳ tuyệt đối.** Cần protocol chính xác.
6. **Dùng `AtomicLong.get()` rồi cập nhật ở lời gọi riêng để kiểm quota.** Có thể race giữa hai bước.
7. **Cho rằng AtomicLong luôn nhanh hơn synchronized.** Cần đo; yêu cầu nhiều trường cũng quan trọng.
8. **Cho rằng LongAdder luôn nhanh hơn AtomicLong.** Có thể không đúng với ít contention hoặc đọc dày.
9. **Quên overflow.** Thread-safe không thay miền kiểu long/int.
10. **Đọc plain counter bằng đường không đồng bộ trong khi ghi dùng khóa.** Mọi truy cập phải tuân thủ cùng cơ chế.
11. **Cho side effect vào lambda `updateAndGet`.** Có thể chạy lại trong quá trình CAS.
12. **Benchmark khi các phương án cùng được cập nhật trong một vòng.** Không cô lập overhead.
13. **Lấy kết quả một lần stress test làm chứng cứ thread safety.** Race phụ thuộc scheduling.
14. **Tưởng một AtomicLong điều phối nhiều JVM.** Nó chỉ thuộc một đối tượng trong một process.
15. **Kiểm tra kết quả khi thread chưa join.** Khi đó kết quả chưa phải tổng cuối.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Hai luồng cùng thực hiện `count++`. Có luôn tăng đúng 2 không?  
**Đáp án:** Không, có thể lost update do hai luồng đọc cùng giá trị cũ.

**Câu 2.** `volatile long count; count++;` đã an toàn chưa?  
**Đáp án:** Chưa. Volatile không khiến thao tác đọc–tính–ghi trở thành atomic.

**Câu 3.** Bộ đếm request có rất nhiều luồng cùng increment và chỉ xuất báo cáo mỗi 10 giây. Nên cân nhắc gì?  
**Đáp án:** `LongAdder`, nếu yêu cầu chấp nhận tổng không phải snapshot nguyên tử khi đang cập nhật. Vẫn benchmark theo workload thực.

**Câu 4.** Cần ID khác nhau sau mỗi phép tăng trong một JVM, nên dùng gì?  
**Đáp án:** `AtomicLong.getAndIncrement()` hoặc tương đương, với chính sách overflow và các đường cấp số nhất quán.

**Câu 5.** LongAdder có chính xác sau khi join mọi worker không?  
**Đáp án:** Có nếu không còn update đồng thời và worker hoàn thành đúng; `sum()` là kết quả tổng sau thời điểm quiescent.

**Câu 6.** Bộ đếm primitive được bảo vệ bằng synchronized còn lost update không?  
**Đáp án:** Không nếu mọi lần cập nhật đều dùng cùng monitor và đường đọc tuân thủ đồng bộ; vẫn phải kiểm vấn đề overflow.

**Câu 7.** `new AtomicLong(Long.MAX_VALUE).incrementAndGet()` có ném exception vì tràn không?  
**Đáp án:** Không, kết quả wrap thành `Long.MIN_VALUE`. Cần cơ chế phát hiện tràn nếu nghiệp vụ yêu cầu.

**Câu 8.** `if (atomic.get() < 100) atomic.incrementAndGet();` có luôn giới hạn đúng 100 khi có nhiều thread không?  
**Đáp án:** Không, điều kiện và increment không nguyên tử như một nhóm; nên dùng CAS loop hoặc đồng bộ.

**Câu 9.** Một lần chạy plain counter nhanh và trả số đúng có chứng minh nó thread-safe không?  
**Đáp án:** Không. Cần lý luận Java Memory Model và kiểm thử concurrency phù hợp, không dựa vào một lịch chạy.

**Câu 10.** Khi hai phương án đều đúng, làm sao chọn cái nhanh hơn?  
**Đáp án:** Đo bằng JMH với mức contention, số threads, tần suất đọc, memory và thời gian warmup tương ứng workload thật.

## 15. Tài liệu Java chính thức

- [`AtomicLong` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): `get`, `getAndIncrement`, `compareAndSet` và cập nhật nguyên tử.
- [`AtomicInteger` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): bộ đếm int với API atomic.
- [`LongAdder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): `increment`, `sum`, `sumThenReset` và giới hạn snapshot.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối thread.
- [`Math` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `incrementExact` để phát hiện tràn.
- [Java Language Specification 17, Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): happens-before, visibility và data races.

**Ghi nhớ:** Bộ đếm primitive không đồng bộ có thể mất update; `AtomicLong` cung cấp read/update atomic, CAS và giá trị cho mỗi lần tăng; `LongAdder` thích hợp cho cập nhật metric nhiều dưới contention nhưng `sum()` không phải snapshot nguyên tử. Ưu tiên hợp đồng chính xác trước, sau đó mới đo hiệu năng.
