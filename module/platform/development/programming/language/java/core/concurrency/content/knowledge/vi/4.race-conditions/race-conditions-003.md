# Lost update trong thao tác tăng biến đếm — Java Concurrency

## 1. Mục tiêu bài học

Giả sử hai luồng cùng tăng biến đếm chung một lần. Ta kỳ vọng biến tăng từ 0 lên 2. Tuy nhiên, có lúc kết quả chỉ là 1. Một thao tác tăng đã bị **mất** vì hai luồng đọc cùng giá trị cũ và lần ghi sau ghi đè kết quả của lần ghi trước. Hiện tượng này gọi là **lost update**, một loại **race condition** rất phổ biến.

Sau bài này, bạn sẽ:

- Giải thích vì sao \`count++\` gồm nhiều bước logic và không bảo đảm atomicity giữa các thread.
- Vẽ được interleaving gây mất cập nhật, phân biệt tính nguyên tử, visibility và ordering trong Java Memory Model.
- Tái hiện lost update **một cách có kiểm soát** bằng chương trình Java 17+ với kết quả dự đoán chính xác.
- Sửa bằng \`synchronized\`, \`Lock\`, \`AtomicInteger\`/CAS và \`LongAdder\`, lựa chọn giải pháp theo yêu cầu đọc/ghi.
- Nhận diện các bẫy như \`volatile int count\`, \`get()+incrementAndGet()\`, khóa sai đối tượng, tăng trong nhiều executor và đọc kết quả khi tác vụ chưa hoàn tất.

**Phạm vi:** Java SE, Java Memory Model và API đồng bộ hóa của JDK. Các ví dụ chạy độc lập bằng Java 17 trở lên.

## 2. Từ một dòng mã tới ba bước read–modify–write

Xét ví dụ:

~~~java
class Counter {
    int count = 0;

    void increment() {
        count++;
    }
}
~~~

\`count++\` tương đương về **ngữ nghĩa tính toán** với:

~~~java
int oldValue = count;   // (1) đọc
int newValue = oldValue + 1; // (2) tính giá trị mới
count = newValue;       // (3) ghi
~~~

Ba bước này chỉ là **mô hình để giải thích**, không khẳng định máy ảo phải phát ra đúng ba lệnh máy hoặc không thể tối ưu. Điều quan trọng là toàn bộ thao tác read–modify–write **không tự động trở thành một hành động nguyên tử** khi nhiều thread cùng truy cập trạng thái chia sẻ.

Với nhiều thread, mỗi thread có thể đọc trước khi thread kia ghi. Kết quả sau cùng phụ thuộc thứ tự xen kẽ (interleaving) và các ràng buộc đồng bộ. Java bảo đảm tính nguyên tử của một lần đọc hoặc ghi \`int\` thông thường, nhưng **không** bảo đảm atomicity cho toàn bộ biểu thức \`count++\`.

### Interleaving gây mất một lần tăng

Ban đầu \`count = 10\`; hai thread T1 và T2 cùng thực hiện một lần tăng:

| Bước | Thread T1 | Thread T2 | Biến chung |
|---|---|---|---|
| 1 | Đọc \`count = 10\` vào biến tạm | — | 10 |
| 2 | — | Đọc \`count = 10\` vào biến tạm | 10 |
| 3 | Tính \`10 + 1 = 11\` | — | 10 |
| 4 | — | Tính \`10 + 1 = 11\` | 10 |
| 5 | Ghi \`count = 11\` | — | 11 |
| 6 | — | Ghi \`count = 11\` | 11 |

Kết quả mong đợi: **12**. Kết quả trong lịch chạy này: **11**. Hai thao tác được gọi, nhưng chỉ có một đơn vị tăng được phản ánh trong trạng thái cuối.

~~~text
                  T1                           T2
                  │                            │
             read count=10                     │
                  │                       read count=10
            compute 10+1                       │
                  │                       compute 10+1
             write count=11                    │
                  │                       write count=11
                  └─────────────┬──────────────┘
                                ▼
                         count cuối = 11
                     (mong đợi là 12)
~~~

Không phải mọi lần chạy đều mất cập nhật: nếu T1 hoàn tất toàn bộ quá trình tăng trước khi T2 đọc thì \`count\` có thể là 12. Vì vậy race condition không đồng nghĩa lỗi xảy ra ở mỗi lần thực thi.

## 3. Lost update, data race và Java Memory Model

**Race condition** là kết quả không mong muốn do thứ tự/tương tác giữa các thực thi đồng thời. **Data race** theo Java Memory Model là một cặp truy cập xung đột tới cùng biến, từ các thread khác nhau, có ít nhất một thao tác ghi, nhưng không được sắp xếp bởi quan hệ happens-before. Một chương trình có thể có race condition gây lỗi logic ngay cả khi các truy cập riêng lẻ được đồng bộ đúng cách nhưng **chuỗi hành động** không được bảo vệ như một thao tác toàn vẹn.

Ba khái niệm cần phân biệt:

| Thuộc tính | Câu hỏi | \`count++\` thường thiếu gì? |
|---|---|---|
| **Atomicity (tính nguyên tử)** | Toàn bộ cập nhật có diễn ra như một bước không thể chen ngang? | Không. Hai thread có thể đọc cùng giá trị và ghi đè nhau. |
| **Visibility (khả năng nhìn thấy)** | Giá trị được ghi bởi thread này có xuất hiện đúng lúc ở thread khác? | Với trường không đồng bộ, không có bảo đảm nhìn thấy cập nhật đúng lúc. |
| **Ordering (thứ tự bộ nhớ)** | Những thao tác nào phải được quan sát theo quan hệ happens-before? | Không có quan hệ đồng bộ cần thiết giữa các lần tăng racy. |

Việc một lần đọc/ghi \`int\` riêng lẻ là atomic **không kéo theo** toàn bộ biểu thức \`count++\` là atomic. Việc bảo đảm visibility cũng **không tự động** đảm bảo atomicity.

### Vì sao \`volatile\` không sửa được lost update?

~~~java
class VolatileCounter {
    volatile int count;

    void increment() {
        count++; // VẪN có lost update
    }
}
~~~

\`volatile\` cung cấp ngữ nghĩa visibility và ordering: ghi volatile và đọc volatile tương ứng tạo các quan hệ happens-before theo quy tắc của Java Memory Model. Nhưng hai thread vẫn có thể đọc cùng giá trị (dù là giá trị mới nhất tại lần đọc), cùng tính \`+1\` và cùng ghi đè lên biến. Không có khóa hoặc thao tác read–modify–write nguyên tử để loại bỏ xen kẽ đó.

Ví dụ:

~~~text
volatile count = 7
T1: read 7
T2: read 7
T1: write 8
T2: write 8
=> count = 8, mất một update
~~~

Ghi nhớ: \`volatile\` phù hợp trong một số trường hợp cờ trạng thái độc lập như \`stopRequested\`; nó không thay thế \`synchronized\` hoặc atomic API cho phép tăng biến đếm chính xác.

### Tại sao sleep(), yield() hay việc chạy nhanh/chậm không bảo vệ được?

\`Thread.sleep(...)\` chỉ yêu cầu thread ngủ một khoảng thời gian; \`Thread.yield()\` là gợi ý cho scheduler. Không lời gọi nào biến \`count++\` thành thao tác atomic hoặc tạo critical section. Thêm \`sleep\` có thể làm lỗi dễ quan sát hơn trong một bài thử, nhưng **không chứng minh** cách sửa đúng. CPU nhiều core, JIT, cache và tải máy làm lịch chạy thay đổi; “đã chạy 1.000 lần không lỗi” vẫn không đủ để khẳng định thread-safe.

## 4. Ví dụ tái hiện lỗi với kết quả xác định

Cách thử \`2 thread × 100_000 lần count++\` thường gặp có thể cho kết quả thấp hơn 200.000, nhưng **không ổn định**: nhiều lần chạy vẫn ra 200.000. Để hiểu chính xác một lost update, ta chủ động cho cả hai thread **đọc biến trước**, sau đó mới mở cổng cho cả hai ghi.

Lưu tệp **LostUpdateDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class LostUpdateDemo {
    private static int count = 0;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothHaveRead = new CountDownLatch(2);
        CountDownLatch allowWriting = new CountDownLatch(1);

        Runnable increment = () -> {
            int snapshot = count;
            bothHaveRead.countDown(); // báo đã đọc count

            try {
                allowWriting.await(); // chưa được ghi khi thread kia chưa đọc
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            count = snapshot + 1; // ghi dựa trên snapshot cũ
        };

        Thread first = new Thread(increment, "first");
        Thread second = new Thread(increment, "second");

        first.start();
        second.start();

        bothHaveRead.await(); // bảo đảm cả hai đã đọc count = 0
        allowWriting.countDown(); // mở cổng ghi
        first.join();
        second.join();

        System.out.println("expected=2");
        System.out.println("actual=" + count);
        System.out.println("lost=" + (2 - count));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LostUpdateDemo.java
java LostUpdateDemo
~~~

Output trong điều kiện bình thường, không có tác động interrupt từ bên ngoài:

~~~text
expected=2
actual=1
lost=1
~~~

**Giải thích tại sao đây là kết quả xác định:**

1. \`bothHaveRead\` bắt đầu tại 2. Mỗi worker đọc \`count\` vào một **biến cục bộ riêng**, rồi đếm xuống.
2. Main chỉ mở \`allowWriting\` sau khi biết **cả hai lần đọc đã xong**. Trước thời điểm đó, không worker nào được ghi \`count\`.
3. Vì \`count\` ban đầu là 0 và chưa có thread nào ghi, cả hai snapshot là 0.
4. Sau khi cổng mở, mỗi worker chỉ ghi \`0 + 1 = 1\`. Dù ai ghi trước, giá trị cuối đều là 1.
5. \`join()\` chờ hai worker kết thúc trước khi main đọc kết quả. \`join\` cũng tạo quan hệ happens-before từ các hành động của worker tới thread chờ hoàn tất.

**Điểm rất quan trọng:** CountDownLatch ở ví dụ này **dùng để dàn dựng một interleaving gây lỗi**, không dùng để sửa lỗi. Việc chờ cả hai thread đọc xong rồi mới cho ghi làm mất update trở nên chắc chắn. Muốn sửa phải bảo vệ thao tác **đọc + tính + ghi** trong một atomic operation hoặc critical section chung.

## 5. Cách sửa thứ nhất: dùng synchronized

Một monitor lock chung có thể bảo đảm chỉ một thread tại một thời điểm chạy toàn bộ phần read–modify–write.

~~~java
class SynchronizedCounter {
    private int count;

    public synchronized void increment() {
        count++;
    }

    public synchronized int get() {
        return count;
    }
}
~~~

\`synchronized\` trên một instance method dùng monitor của chính đối tượng (\`this\`). Khi T1 giữ monitor, T2 muốn vào \`increment()\` trên **cùng instance** phải đợi. Khi T1 rời critical section, T2 mới đọc giá trị đã cập nhật. Unlock của monitor và lock kế tiếp trên cùng monitor thiết lập happens-before, hỗ trợ cả mutual exclusion lẫn visibility.

**Điều kiện:** Mọi truy cập liên quan phải tuân theo giao thức đồng bộ đúng. Nếu có phương thức khác vẫn ghi trực tiếp vào \`count\` mà không giữ cùng monitor, giao thức không còn bảo đảm.

### Khóa riêng (private lock) nếu cần tách khỏi monitor đối tượng

~~~java
class LockedCounter {
    private final Object lock = new Object();
    private int count;

    void increment() {
        synchronized (lock) {
            count++;
        }
    }

    int get() {
        synchronized (lock) {
            return count;
        }
    }
}
~~~

Dùng \`private final Object lock\` ngăn code ngoài vô tình khóa cùng monitor do \`synchronized(this)\`. Các phương thức \`increment\` và \`get\` phải dùng **cùng đối tượng lock**.

Sai lầm thường thấy:

~~~java
void brokenIncrement() {
    synchronized (new Object()) { // mỗi lần gọi tạo một lock riêng
        count++;
    }
}
~~~

Đoạn mã trên là **minh họa lỗi** bên trong một class có trường \`count\`; nó không giải quyết race giữa những lời gọi khác nhau. Thread nào cũng giữ monitor mới của chính nó nên không có mutual exclusion trên biến chung.

### Dùng ReentrantLock khi cần kiểm soát rõ hơn

~~~java
import java.util.concurrent.locks.ReentrantLock;

class ReentrantCounter {
    private final ReentrantLock lock = new ReentrantLock();
    private int count;

    void increment() {
        lock.lock();
        try {
            count++;
        } finally {
            lock.unlock();
        }
    }

    int get() {
        lock.lock();
        try {
            return count;
        } finally {
            lock.unlock();
        }
    }
}
~~~

\`ReentrantLock\` cho phép các khả năng như \`tryLock()\`, \`lockInterruptibly()\` và các \`Condition\` khi có nhu cầu cụ thể. Cần luôn đặt \`unlock()\` trong \`finally\` sau khi lấy lock thành công. Với một biến đếm đơn giản, \`synchronized\` thường rõ ràng và ít lỗi hơn.

## 6. Cách sửa thứ hai: AtomicInteger và atomic read–modify–write

Java cung cấp \`java.util.concurrent.atomic.AtomicInteger\` cho một giá trị \`int\` cần cập nhật nguyên tử mà không phải viết monitor lock cho từng lần tăng.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger();

    void increment() {
        count.incrementAndGet();
    }

    int get() {
        return count.get();
    }
}
~~~

\`incrementAndGet()\` thực hiện một thao tác tăng nguyên tử với ngữ nghĩa memory visibility phù hợp. Mỗi cập nhật thành công có một **linearization point**: các lần tăng có thể được hiểu như có thứ tự tuần tự hợp lệ dù nhiều thread gọi đồng thời.

Các API thường gặp:

| Phương thức | Ý nghĩa |
|---|---|
| \`get()\` | Lấy giá trị hiện tại với ngữ nghĩa đọc volatile của API atomic. |
| \`set(v)\` | Ghi giá trị với ngữ nghĩa ghi volatile. |
| \`getAndIncrement()\` | Tăng 1 nguyên tử; **trả về giá trị cũ**. |
| \`incrementAndGet()\` | Tăng 1 nguyên tử; **trả về giá trị mới**. |
| \`addAndGet(delta)\` | Cộng \`delta\` nguyên tử; trả về giá trị mới. |
| \`getAndAdd(delta)\` | Cộng \`delta\` nguyên tử; trả về giá trị cũ. |
| \`compareAndSet(expected, update)\` | Nếu giá trị còn bằng \`expected\`, thử đổi thành \`update\` nguyên tử; trả boolean thành công/thất bại. |

Việc triển khai thường dựa trên cơ chế atomic/CAS do JVM và phần cứng hỗ trợ. CAS có thể phải thử lại dưới contention. Không suy diễn từ tên phương thức rằng mỗi lần tăng luôn hoàn thành trong thời gian cố định hoặc hoàn toàn không có chi phí.

**Không làm thế này để tăng atomic counter:**

~~~java
AtomicInteger count = new AtomicInteger();
int old = count.get();
count.set(old + 1); // hai lệnh atomic riêng nhưng tổ hợp KHÔNG atomic
~~~

Hai thread vẫn có thể \`get() = 0\`, rồi cùng \`set(1)\`. Dù từng lời gọi \`get\` và \`set\` có memory semantics đúng, chuỗi read–modify–write tổng thể vẫn không được bảo vệ. Phải dùng \`incrementAndGet()\`, \`getAndIncrement()\`, \`addAndGet()\` hoặc một vòng CAS đúng.

## 7. Cách sửa thứ ba: LongAdder khi nhiều thread tranh cùng counter

\`LongAdder\` tối ưu trường hợp **rất nhiều thread thường xuyên cộng dồn** cùng một chỉ số. Thay vì luôn cập nhật một vị trí đơn lẻ như \`AtomicLong\`, cách triển khai có thể chia các cập nhật ra nhiều ô nội bộ để giảm contention, rồi tổng hợp khi đọc.

~~~java
import java.util.concurrent.atomic.LongAdder;

class MetricsCounter {
    private final LongAdder requests = new LongAdder();

    void recordRequest() {
        requests.increment();
    }

    long total() {
        return requests.sum();
    }
}
~~~

Lợi thế và giới hạn:

- \`increment()\`/ \`add(n)\` phù hợp cho chỉ số như tổng số request, số sự kiện, số lượt truy cập có tần suất cao.
- \`sum()\` **không phải atomic snapshot** khi các thread khác vẫn đang cập nhật: giá trị đọc có thể không bao gồm các cập nhật xảy ra đồng thời.
- \`sumThenReset()\` cũng không phải lựa chọn an toàn để thu thập số liệu chính xác khi các thao tác cập nhật vẫn diễn ra đồng thời; tài liệu lưu ý chỉ dùng khi chắc chắn không có cập nhật đồng thời nếu cần giá trị đầy đủ.
- \`LongAdder\` không cung cấp \`compareAndSet\` trên tổng; vì thế không phù hợp nếu cần quy tắc “chỉ tăng khi giá trị chưa đạt giới hạn”.
- Lợi ích hiệu năng phụ thuộc workload, độ contention, số core, memory và JDK; không khẳng định luôn nhanh hơn \`AtomicLong\`.

**Chọn cách nào?**

| Yêu cầu | Lựa chọn thường hợp lý | Lý do |
|---|---|---|
| Một counter chính xác, cập nhật và đọc liên tục | \`AtomicInteger\`/\`AtomicLong\` | Atomic increment, API đơn giản, cung cấp CAS. |
| Nhiều trường dữ liệu phải giữ một bất biến chung | \`synchronized\`/\`Lock\` | Bảo vệ toàn bộ thao tác nhiều bước dưới cùng critical section. |
| Counter thống kê có nhiều writer, chỉ cần tổng hợp theo thời điểm | \`LongAdder\` | Giảm contention, chấp nhận \`sum()\` không phải snapshot nguyên tử khi đang ghi. |
| Cần thao tác có điều kiện như \`count < limit\` rồi tăng | CAS loop hoặc lock | Kiểm tra và cập nhật phải là một hành động logic nguyên tử. |
| Tình huống đơn luồng không chia sẻ biến | \`int\`/\`long\` thường | Không cần trả chi phí đồng bộ khi thực sự không có truy cập đồng thời. |

## 8. Ví dụ độc lập: so sánh ba cách tăng biến đếm an toàn

Chương trình dưới đây dùng hai thread, mỗi thread tăng 100.000 lần. Nó không dựa vào may rủi race để thành công: cả ba bộ đếm đều bảo vệ update. \`join()\` đảm bảo đã hoàn tất tất cả lần tăng trước khi đọc kết quả.

Lưu tệp **SafeCountersDemo.java**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public class SafeCountersDemo {
    interface Counter {
        void increment();
        long value();
    }

    static class SynchronizedCounter implements Counter {
        private long count;

        @Override
        public synchronized void increment() {
            count++;
        }

        @Override
        public synchronized long value() {
            return count;
        }
    }

    static class AtomicCounter implements Counter {
        private final AtomicInteger count = new AtomicInteger();

        @Override
        public void increment() {
            count.incrementAndGet();
        }

        @Override
        public long value() {
            return count.get();
        }
    }

    static class AdderCounter implements Counter {
        private final LongAdder count = new LongAdder();

        @Override
        public void increment() {
            count.increment();
        }

        @Override
        public long value() {
            return count.sum();
        }
    }

    static void repeat(Counter counter) {
        for (int i = 0; i < 100_000; i++) {
            counter.increment();
        }
    }

    static long run(Counter counter) throws InterruptedException {
        Thread t1 = new Thread(() -> repeat(counter), "worker-1");
        Thread t2 = new Thread(() -> repeat(counter), "worker-2");
        t1.start();
        t2.start();
        t1.join();
        t2.join();
        return counter.value();
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("synchronized=" + run(new SynchronizedCounter()));
        System.out.println("atomic=" + run(new AtomicCounter()));
        System.out.println("longAdder=" + run(new AdderCounter()));
    }
}
~~~

Biên dịch, chạy:

~~~bash
javac SafeCountersDemo.java
java SafeCountersDemo
~~~

Output:

~~~text
synchronized=200000
atomic=200000
longAdder=200000
~~~

Tại sao \`LongAdder.sum()\` ở đây cho kết quả đầy đủ dù không phải atomic snapshot? Vì main đợi cả hai thread kết thúc qua \`join()\`; khi gọi \`sum()\` **không còn writer nào đang cập nhật**. Trong chương trình khác, nếu đọc \`sum()\` khi worker vẫn chạy, kết quả là tổng quan sát được tại một khoảng thời gian và có thể khác tổng tức thời.

**Không coi ba lượt đo này là benchmark.** Thứ tự chạy, warmup JIT, biến động OS và kích cỡ workload có thể làm thời gian thay đổi. Mục đích ví dụ là chứng minh tính đúng đắn, không chứng minh \`LongAdder\` nhanh hơn bao nhiêu phần trăm.

## 9. Lưu ý nâng cao: một chuỗi nhiều API atomic vẫn có thể sai

Một thiết kế dễ gặp là giới hạn số lượt đặt chỗ:

~~~java
AtomicInteger booked = new AtomicInteger();
int capacity = 10;

if (booked.get() < capacity) {
    booked.incrementAndGet(); // SAI nếu hai thread cùng vào nhánh if
}
~~~

Mặc dù \`get()\` và \`incrementAndGet()\` mỗi cái đều atomic, **phép kiểm tra điều kiện + tăng** không atomic. Khi \`booked=9\`, hai thread đều thấy \`9<10\` và đều tăng: cuối cùng có thể thành **11**, vi phạm sức chứa 10.

### Sửa bằng vòng compareAndSet

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class CapacityCounter {
    private final AtomicInteger booked = new AtomicInteger();

    public boolean tryBook(int capacity) {
        if (capacity < 0) {
            throw new IllegalArgumentException("capacity must be >= 0");
        }
        while (true) {
            int current = booked.get();
            if (current >= capacity) {
                return false;
            }
            if (booked.compareAndSet(current, current + 1)) {
                return true;
            }
            // Có cập nhật cạnh tranh: đọc lại trạng thái mới rồi thử lại.
        }
    }

    public int count() {
        return booked.get();
    }

    public static void main(String[] args) {
        CapacityCounter counter = new CapacityCounter();
        System.out.println(counter.tryBook(1));
        System.out.println(counter.tryBook(1));
        System.out.println(counter.count());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CapacityCounter.java
java CapacityCounter
~~~

Output:

~~~text
true
false
1
~~~

CAS thành công chỉ khi giá trị vẫn là \`current\` tại bước cập nhật; nếu thread khác đã thay đổi giá trị, lời gọi thất bại và vòng lặp thử lại dựa trên trạng thái mới. Mẫu này bảo vệ bất biến \`count <= capacity\` khi tất cả thay đổi có liên quan đi qua cùng giao thức, biến \`capacity\` được truyền nhất quán và không có cập nhật bên ngoài. Ví dụ xử lý một bộ đếm in-memory trong một JVM; nó không tự đồng bộ dữ liệu với hệ thống ngoài hoặc nhiều process.

**Một caution về nhiều trạng thái:** Một số bất biến liên quan tới nhiều biến, nhiều object hoặc tài nguyên bên ngoài không thể sửa bằng một \`AtomicInteger\`. Khi kiểm tra và cập nhật nhiều trường phải nhất quán, hãy thiết kế critical section chung, state bất biến thay thế bằng CAS, hoặc cơ chế phối hợp thích hợp cho phạm vi tài nguyên đó.

## 10. Lock, atomic và volatile dưới góc nhìn happens-before

### synchronized

Một thread rời monitor (\`unlock\`) happens-before một thread khác vào lại (\`lock\`) **chính monitor đó**. Trong cùng critical section, mutual exclusion giúp không bị hai thread cùng read–modify–write trên biến đếm. Đọc/ghi ngoài lock, hoặc dùng hai đối tượng lock khác nhau, làm mất bảo đảm đồng bộ này.

### AtomicInteger

Các thao tác \`get()\`, \`set()\` và atomic update có memory effect được định nghĩa; \`incrementAndGet()\` là một update nguyên tử. Dùng nhiều lời gọi tách rời như \`get()\` rồi \`set(...)\` sẽ tạo khoảng chen ngang. Do vậy cần chọn thao tác cập nhật phù hợp với yêu cầu **của cả hành động nghiệp vụ**.

### volatile

Visibility và ordering của volatile giúp thread quan sát cập nhật theo quy tắc happens-before nhưng không cấp mutual exclusion cho read–modify–write. \`volatile int count++\` vẫn racy. Ngược lại, một cờ \`volatile boolean running\` chỉ cần đọc/ghi trạng thái độc lập có thể phù hợp nếu không có bất biến phức tạp.

### join(), CountDownLatch và Future.get()

Đây là công cụ **phối hợp vòng đời và đồng bộ quan sát**, không tự bảo vệ phần tăng sai:

- Sau khi một thread kết thúc thành công và thread khác \`join()\` vào nó, các hành động của thread hoàn tất happens-before các hành động sau \`join()\` của thread chờ.
- \`CountDownLatch\` cung cấp quan hệ happens-before qua \`countDown()\` và \`await()\` theo hợp đồng API; latch thường giúp xác định thời điểm bắt đầu, hoàn tất hoặc dàn dựng thứ tự.
- Với \`Future\`, các hành động của tác vụ bất đồng bộ happens-before những hành động sau \`Future.get()\` tương ứng. Nhưng \`Future.get()\` không làm cho biến đếm đã được tăng bởi nhiều worker tự nhiên trở thành atomic.

Chỉ \`join()\` sau khi **tất cả việc ghi đã hoàn thành** giúp main đọc kết quả cuối có cơ sở. Nếu không chờ, việc in biến đếm có thể thiếu cả những lần tăng mà worker còn chưa chạy xong — đây là vấn đề thời điểm quan sát bên cạnh lost update.

## 11. Các lỗi phổ biến và cách nhận diện

### Lỗi 1: Biến chung là static nên được “bảo vệ”

\`static\` chỉ làm trường thuộc class, nghĩa là nhiều instance có thể cùng chia sẻ giá trị. Nó **không** có thuộc tính atomic hoặc synchronized. \`final\` trên tham chiếu counter cũng không làm các thao tác thay đổi trạng thái bên trong counter trở nên thread-safe.

### Lỗi 2: Mỗi thread giữ một Counter khác nhau

Nếu mỗi thread tăng instance riêng, bạn không còn thử nghiệm lost update trên cùng một biến. Khi thiết kế dự kiến tổng chung, cần đúng một shared counter được truyền cho các worker. Đồng thời nếu dùng \`synchronized\`, tất cả các worker cần đồng bộ trên cùng instance/monitor.

### Lỗi 3: synchronized đúng phương thức nhưng các đường truy cập khác bỏ khóa

Một phương thức synchronized không cứu được những lời ghi trực tiếp đến trường không được bảo vệ. Khuyến nghị \`private\` field và API cập nhật nhất quán. Tránh để lộ tham chiếu mutable state rồi thay đổi nó từ nơi khác mà không giữ lock.

### Lỗi 4: Dùng volatile cho phép tăng hoặc kiểm tra-điều kiện-rồi-tăng

\`volatile\` không cung cấp atomic read–modify–write; \`AtomicInteger.get()\` cộng với \`AtomicInteger.set()\` cũng không. Chọn \`incrementAndGet\`, CAS hoặc lock bao toàn thao tác.

### Lỗi 5: Hai thread tự start mà không join nhưng đã kiểm tra count

\`start()\` chỉ yêu cầu chạy, không chờ kết thúc. Nếu main in kết quả ngay sau khi start, giá trị có thể nhỏ vì chưa chạy xong, dù đã dùng counter atomic. Đợi \`join()\`, \`Future.get()\`, \`CountDownLatch\` theo đúng semantics của bài.

### Lỗi 6: Dùng int cho tổng lớn bất chấp overflow

\`int\` có phạm vi -2^31 tới 2^31-1. Khi vượt phạm vi, phép cộng số nguyên Java overflow theo quy tắc số nguyên 32-bit; counter có thể thành số âm dù mọi update đã atomic. \`AtomicInteger\` **không tránh overflow**. Chọn \`long\`, \`AtomicLong\`, \`LongAdder\` hoặc thiết kế giới hạn/overflow policy theo yêu cầu.

### Lỗi 7: Dùng LongAdder như số dư chính xác tức thời

\`LongAdder.sum()\` khi writer vẫn chạy không phải snapshot nguyên tử. Với metric cộng dồn, đây là tradeoff hợp lý; với một invariant cần quyết định “nếu còn chỗ thì tăng”, phải dùng atomic CAS hoặc lock.

### Lỗi 8: Cho rằng race chỉ có trên nhiều CPU core

Ngay cả trên một core, scheduler vẫn có thể chuyển thread giữa các bước. Nhiều core tăng khả năng chạy đồng thời nhưng không phải điều kiện bắt buộc cho lost update. Thread scheduling và Java Memory Model đều là phần của bài toán.

### Lỗi 9: Nhầm mất cập nhật với vấn đề thứ tự log

Log in ra theo thứ tự bất định giữa các thread không nhất thiết là lost update. Hãy kiểm tra **trạng thái/invariant** của shared counter sau khi các task hoàn tất. Phải có một kỳ vọng chính xác: N worker × M lần tăng thì giá trị cần đạt N×M nếu không có overflow và không bỏ/cancel task.

### Lỗi 10: Dùng benchmark nhanh để kết luận giải pháp “tốt nhất”

\`synchronized\` có thể rất phù hợp vì đơn giản, \`AtomicInteger\` phù hợp thao tác một counter, \`LongAdder\` phù hợp metric nhiều writer. Chi phí thực tế thay đổi theo contention, số core, runtime và tỷ lệ đọc/ghi; kiểm tra correctness trước, benchmark đúng workload sau.

## 12. Hướng dẫn thử nghiệm và chẩn đoán

Một chiến lược kiểm tra bài bản gồm hai lớp:

**Lớp 1 — thử nghiệm interleaving có điều khiển:** Dùng \`CountDownLatch\` như ví dụ đầu để chứng minh hai thread thật sự có thể đọc cùng snapshot và ghi đè nhau. Đây là **minh chứng logic xác định**, không chỉ chờ scheduler tạo may rủi.

**Lớp 2 — thử nghiệm dưới tải:** Chạy nhiều task cùng tăng một counter chung, start đồng thời bằng barrier/latch, sau đó join hoặc đợi Future. Đối chiếu với \`expected = threads × incrementsPerThread\`. Lặp trên nhiều cấu hình. Kết quả đúng của một lần stress **không chứng minh** mã không có race; kết quả sai là bằng chứng có vấn đề. Khi viết test đồng thời cần bảo đảm task không bị cancel/interrupt ngoài dự kiến và phép tính expected không overflow.

Để đi sâu hơn, có thể dùng công cụ chuyên biệt như **OpenJDK jcstress** nhằm kiểm tra các kết quả quan sát được dưới nhiều interleaving/JMM, hoặc xem thread dump/JFR khi nghi ngờ contention/blocked threads. Thread dump chủ yếu cho biết trạng thái đang chờ; nó không tự chứng minh \`count++\` atomic. Trong mã production, luôn xem cả dữ liệu counter, tỷ lệ lỗi, logic retry và các cập nhật bị bỏ.

### Checklist review code

- **Một giá trị chia sẻ?** Xác nhận tất cả worker dùng cùng counter, không clone biến hoặc tự tạo counter riêng.
- **Có read–modify–write?** \`++\`, \`--\`, \`x += n\`, \`map.put(key, map.get(key)+1)\` đều cần đánh giá tính nguyên tử.
- **Có conditional update?** \`if (count < limit) count++\` cần atomicity cả kiểm tra lẫn cập nhật.
- **Đồng bộ ở đâu?** Cùng monitor, cùng Lock, atomic API hoặc một giao thức thread confinement đúng.
- **Đọc kết quả lúc nào?** Chờ công việc xong; phân biệt đọc snapshot trong lúc có writer với đọc tổng cuối.
- **Kiểu dữ liệu có đủ rộng?** Kiểm tra overflow, giới hạn nghiệp vụ và yêu cầu metric.
- **Có cập nhật nhiều trường?** Một atomic counter không tự giữ tính nhất quán của mọi trường liên quan.

## 13. Bài tập tự kiểm tra

**Câu 1.** Hai thread mỗi thread tăng \`count\` 10.000 lần với \`volatile int count\`. Giá trị có chắc bằng 20.000 không?

**Đáp án:** Không. \`volatile\` giúp visibility và ordering nhưng không làm \`++\` atomic; interleaving có thể gây mất update.

**Câu 2.** Một thread sử dụng \`counter.incrementAndGet()\`, thread khác dùng \`counter.get(); counter.set(old + 1)\` trên cùng \`AtomicInteger\`. Có thread-safe không?

**Đáp án:** Không. Đường \`get()+set()\` vẫn là compound update không atomic; mọi writer phải tuân theo cùng giao thức cập nhật đúng.

**Câu 3.** \`synchronized\` trên hai instance khác nhau có bảo vệ cùng một biến \`static\` không?

**Đáp án:** Không, nếu mỗi instance dùng monitor \`this\` riêng. Phải dùng **chung một lock** cho biến \`static\`, hoặc atomic field phù hợp.

**Câu 4.** \`LongAdder.sum()\` có phải snapshot chính xác trong lúc nhiều worker đang gọi \`increment()\`?

**Đáp án:** Không. Nó phù hợp tổng metric có cập nhật đồng thời, nhưng không bảo đảm snapshot atomic. Sau khi mọi worker kết thúc và đã join, sum phản ánh các lần tăng đã hoàn thành.

**Câu 5.** Vì sao \`Future.get()\` không đủ để tránh lost update?

**Đáp án:** \`get()\` giúp đợi task và quan sát kết quả/ngoại lệ với memory consistency tương ứng; nếu chính tác vụ đã làm sai \`count++\` song song, chờ hoàn tất không khôi phục cập nhật đã mất.

## 14. Kết luận và tài liệu tra cứu

Một biến đếm chung cần đáp ứng **hai điều kiện độc lập**: cập nhật phải nguyên tử nếu nhiều thread cùng tăng; kết quả phải được quan sát khi đã có quan hệ đồng bộ và tại đúng thời điểm. \`count++\` thông thường thiếu tính nguyên tử. \`volatile\` chỉ giải quyết phần visibility/ordering, không khóa ba bước đọc–tính–ghi. Chọn \`synchronized\`/\`Lock\` khi thao tác nhiều bước cần bất biến chung, \`AtomicInteger\` hoặc \`AtomicLong\` khi cập nhật một counter cần chính xác và có thể CAS, \`LongAdder\` cho metric tăng nhiều với chấp nhận snapshot không nguyên tử trong lúc còn writer.

Tài liệu API chuẩn:

- Java Language Specification §17 — Threads and Locks: https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html
- \`AtomicInteger\`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- \`LongAdder\`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- \`CountDownLatch\`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
- \`ReentrantLock\`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html

**Ghi nhớ cốt lõi:** *Một thao tác đọc nguyên tử cộng với một thao tác ghi nguyên tử không tự tạo thành một phép tăng nguyên tử.* Khi sửa lost update, phải bảo vệ toàn bộ read–modify–write — và bảo vệ cả điều kiện liên quan nếu có.
