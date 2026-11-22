# Bài tập thực tế: Xây counter bị race và lần lượt sửa bằng lock, atomic

## 1. Mục tiêu và kết quả cần đạt

Bài tập đặt ra một bộ đếm dùng chung trong chương trình Java: nhiều thread cùng gọi **increment()**, mỗi lời gọi phải làm tổng tăng đúng một đơn vị. Ta sẽ chủ động xây phiên bản sai với phép **value++**, tái hiện mất lượt tăng (*lost update*), rồi sửa lần lượt bằng **ReentrantLock** và **AtomicInteger**. Cuối cùng chạy các thread thật trên ExecutorService và tự kiểm tra giá trị mong đợi.

Sau bài này, bạn cần tự giải thích và kiểm chứng được:

1. Vì sao increment trên trường **int** thông thường không an toàn khi nhiều thread cùng ghi.
2. Vì sao tăng số thread hoặc chèn Thread.sleep không phải cách chứng minh race chắc chắn.
3. Khóa phải bảo vệ **trọn chuỗi đọc → tính → ghi**, không chỉ một phần.
4. AtomicInteger cung cấp thao tác tăng nguyên tử; khi nào nó phù hợp hơn lock.
5. Cách tạo test có **kết quả rõ ràng**, timeout và kiểm tra exception của worker.
6. Cách chọn giữa lock và atomic khi dữ liệu gồm một bộ đếm hay nhiều trạng thái phải thay đổi cùng nhau.

Đây là bài thực hành concurrency trong **Java nói chung**, dùng các API thuộc JDK 17+. Không cần Spring hoặc framework kiểm thử.

## 2. Thiết kế Counter và điều kiện đúng

Giả sử có 4 worker, mỗi worker thực hiện 25.000 lần tăng. Nếu ban đầu counter = 0 và không có lời gọi thất bại, kết quả phải là:

~~~text
4 worker × 25.000 lần/worker = 100.000 lần tăng
Expected final counter = 100000
~~~

Ta định nghĩa hợp đồng nhỏ:

~~~java
interface Counter {
    void increment();
    int value();
}
~~~

Đây là đoạn mã tích hợp vào chương trình đầy đủ ở mục 4. **Invariant** cần giữ: khi tất cả increment đã hoàn thành bình thường, giá trị đọc được bằng tổng số increment đã thực hiện. Nếu một counter bị race, giá trị có thể nhỏ hơn tổng số lượt do hai thread ghi đè kết quả của nhau.

Về mặt thời gian, một lần **value++** tương đương về ý nghĩa với việc:

~~~java
int old = value;
int next = old + 1;
value = next;
~~~

Ba dòng minh họa một thao tác có nhiều giai đoạn; không khẳng định JVM bắt buộc biên dịch phép ++ thành đúng ba instruction. Các bước đọc/tính/ghi có thể xen kẽ với thread khác.

### Lịch thực thi gây lost update

| Thời điểm | Worker A | Worker B | Giá trị chung |
| --- | --- | --- | ---: |
| 0 | — | — | 0 |
| 1 | Đọc 0 | — | 0 |
| 2 | — | Đọc 0 | 0 |
| 3 | Tính 0 + 1 | — | 0 |
| 4 | — | Tính 0 + 1 | 0 |
| 5 | Ghi 1 | — | 1 |
| 6 | — | Ghi 1 | 1 |

Hai lần tăng đã được yêu cầu nhưng kết quả chỉ là 1. Nếu A chạy hết trước khi B đọc, kết quả có thể là 2. **Việc đôi khi nhận đúng kết quả không chứng minh mã an toàn**.

Lỗi ở đây gồm vấn đề **tính nguyên tử** và việc truy cập trường chia sẻ thiếu đồng bộ. Đánh dấu **volatile** có thể cải thiện visibility, nhưng không biến chuỗi read-modify-write thành một phép tăng nguyên tử; hai thread vẫn có thể cùng đọc 0 và cùng ghi 1.

## 3. Ba phiên bản cần xây

### Phiên bản 1 — UnsafeCounter

~~~java
private int value;

public void increment() {
    value++; // read-modify-write không nguyên tử
}

public int value() {
    return value;
}
~~~

Đây là phần thân của một class, chưa phải chương trình độc lập. Tất cả thread dùng **cùng một instance** của counter. Nếu mỗi thread tự tạo counter riêng thì sẽ không có tranh chấp và test không kiểm tra được lỗi chia sẻ dữ liệu.

### Phiên bản 2 — LockCounter

~~~java
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

public int value() {
    lock.lock();
    try {
        return value;
    } finally {
        lock.unlock();
    }
}
~~~

Một thread giữ lock thì thread khác không thể đồng thời bước vào vùng increment được bảo vệ bằng **cùng khóa**. Phần đọc trong value() cũng dùng khóa đó để bảo đảm nhất quán khi đọc lúc còn writer.

**finally** là bắt buộc trong mẫu sử dụng lock thủ công: nếu thân khối ném exception, lock vẫn được thả. Không để return, exception hoặc một nhánh điều kiện làm bỏ qua unlock.

### Phiên bản 3 — AtomicCounter

~~~java
private final AtomicInteger value = new AtomicInteger();

public void increment() {
    value.incrementAndGet();
}

public int value() {
    return value.get();
}
~~~

AtomicInteger.incrementAndGet cung cấp phép cập nhật nguyên tử trên **một biến**, nên không mất lượt tăng. Java thực thi cơ chế cập nhật nguyên tử thích hợp trên JVM/nền tảng; không cần tự viết vòng compare-and-set cho bài toán cộng một.

Ba đoạn trên được ghép thành ba class hoàn chỉnh trong ví dụ tiếp theo. Không kết hợp hai loại đồng bộ chỉ để sửa một biến đếm đơn lẻ khi không có yêu cầu thêm.

## 4. Chương trình Java 17 hoàn chỉnh, chạy được

Chương trình tạo hai loại thí nghiệm:

- **Thí nghiệm tái hiện có kiểm soát**: hai worker cùng đọc giá trị cũ trước khi ghi để chắc chắn tạo lost update. Đây là cách trực quan hóa lỗi của read-modify-write; điểm đồng bộ là dụng cụ của bài test, không phải code sản xuất.
- **Thí nghiệm tải đồng thời**: 4 worker, mỗi worker thực sự gọi increment() 25.000 lần trên counter dùng lock và counter atomic. Sau khi mọi Future hoàn thành, kết quả phải là 100.000.

**Tạo tệp CounterExercise.java:**

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.ReentrantLock;

public final class CounterExercise {

    private static final int WORKERS = 4;
    private static final int INCREMENTS_PER_WORKER = 25_000;

    interface Counter {
        void increment();
        int value();
    }

    static final class UnsafeCounter implements Counter {
        private int value;

        @Override
        public void increment() {
            value++;
        }

        @Override
        public int value() {
            return value;
        }

        // Chỉ được harness dùng để ép lịch read rồi write gây lost update.
        int snapshot() {
            return value;
        }

        void store(int updated) {
            value = updated;
        }
    }

    static final class LockCounter implements Counter {
        private final ReentrantLock lock = new ReentrantLock();
        private int value;

        @Override
        public void increment() {
            lock.lock();
            try {
                value++;
            } finally {
                lock.unlock();
            }
        }

        @Override
        public int value() {
            lock.lock();
            try {
                return value;
            } finally {
                lock.unlock();
            }
        }
    }

    static final class AtomicCounter implements Counter {
        private final AtomicInteger value = new AtomicInteger();

        @Override
        public void increment() {
            value.incrementAndGet();
        }

        @Override
        public int value() {
            return value.get();
        }
    }

    static int forceLostUpdate() throws Exception {
        UnsafeCounter counter = new UnsafeCounter();
        CyclicBarrier bothRead = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        Future<Void> first = null;
        Future<Void> second = null;

        try {
            Callable<Void> unsafeReadModifyWrite = () -> {
                int seen = counter.snapshot();

                // Mỗi worker phải đọc xong trước khi một worker ghi.
                bothRead.await(5, TimeUnit.SECONDS);

                counter.store(seen + 1);
                return null;
            };

            first = pool.submit(unsafeReadModifyWrite);
            second = pool.submit(unsafeReadModifyWrite);

            first.get(10, TimeUnit.SECONDS);
            second.get(10, TimeUnit.SECONDS);
            return counter.value();
        } finally {
            if (first != null) first.cancel(true);
            if (second != null) second.cancel(true);
            pool.shutdownNow();
        }
    }

    static int runConcurrentLoad(Counter counter) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(WORKERS);
        CountDownLatch ready = new CountDownLatch(WORKERS);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Void>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < WORKERS; i++) {
                Future<Void> future = pool.submit(() -> {
                    ready.countDown();

                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new TimeoutException("Start gate timed out");
                    }

                    for (int j = 0; j < INCREMENTS_PER_WORKER; j++) {
                        if (Thread.currentThread().isInterrupted()) {
                            throw new InterruptedException("Worker cancelled");
                        }
                        counter.increment();
                    }
                    return null;
                });
                futures.add(future);
            }

            if (!ready.await(5, TimeUnit.SECONDS)) {
                throw new TimeoutException("Workers were not ready");
            }

            start.countDown();

            // Lấy exception của worker, đồng thời chờ tất cả hoàn thành.
            for (Future<Void> future : futures) {
                future.get(10, TimeUnit.SECONDS);
            }
            return counter.value();
        } finally {
            start.countDown(); // Giải phóng worker nếu main lỗi sớm.
            for (Future<Void> future : futures) {
                future.cancel(true);
            }
            pool.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        int expected = WORKERS * INCREMENTS_PER_WORKER;

        int lostUpdate = forceLostUpdate();
        int locked = runConcurrentLoad(new LockCounter());
        int atomic = runConcurrentLoad(new AtomicCounter());

        System.out.println("Forced lost update: " + lostUpdate + " / 2");
        System.out.println("ReentrantLock: " + locked + " / " + expected);
        System.out.println("AtomicInteger: " + atomic + " / " + expected);

        if (lostUpdate != 1 || locked != expected || atomic != expected) {
            throw new AssertionError("Counter invariant failed");
        }
    }
}
~~~

Dùng JDK 17 hoặc mới hơn:

~~~bash
javac CounterExercise.java
java CounterExercise
~~~

**Stdout khi chương trình chạy thành công:**

~~~text
Forced lost update: 1 / 2
ReentrantLock: 100000 / 100000
AtomicInteger: 100000 / 100000
~~~

Nếu môi trường quá chậm hoặc worker lỗi, chương trình có thể ném exception thay vì in ba dòng trên. Các timeout 5 và 10 giây là **hạn bảo vệ bài thực hành**, không phải cam kết hiệu năng cho ứng dụng thực tế.

### Vì sao kết quả có thể kiểm chứng?

**forceLostUpdate():** Mỗi worker đọc giá trị ban đầu 0. Barrier bắt buộc cả hai hoàn tất việc đọc mới được ghi. Do đó cả hai store(1), kết quả cuối luôn là 1 khi barrier kết thúc bình thường. Việc truy cập này cố tình không đồng bộ để phơi bày lost update; phương thức snapshot()/store() chỉ phục vụ harness. Trong code sản xuất sai, cùng vấn đề nằm bên trong phép value++.

**runConcurrentLoad():** Mỗi worker báo ready, sau đó đợi cổng start. Main chỉ mở cổng khi cả bốn worker đã tới điểm sẵn sàng; điều này giúp tăng cơ hội cạnh tranh, nhưng **không bảo đảm** phát hiện race nếu truyền UnsafeCounter vào bài tải. Test mẫu dành cho hai bản sửa, kết quả luôn đúng theo hợp đồng của lock/atomic nếu các worker hoàn thành bình thường.

**Future.get():** Main đợi từng worker hoàn thành và nhận exception của worker qua ExecutionException. Khi tất cả Future.get() thành công, các hành động trong task happens-before phần xử lý tiếp theo của main, nên phép đọc giá trị sau đó có điểm đồng bộ thích hợp.

**Kiểm tra invariant:** Main xác nhận lostUpdate = 1 cho **phiên bản sai được dàn dựng**, và locked = atomic = 100.000 cho **hai bản sửa**. Đây là hai loại oracle khác nhau; không được mang expected = 1 sang test của bản sửa.

## 5. Tự làm từ phiên bản sai đến hai bản sửa

Nếu muốn thực hành theo từng commit hoặc từng lần sửa, hãy làm theo trình tự sau mà vẫn dùng cùng bài toán Counter.

### Bước A — Tạo lỗi thật với value++

Bắt đầu bằng UnsafeCounter. Viết các worker cùng giữ một tham chiếu tới nó. Mỗi worker gọi increment() trong vòng lặp; sau khi hoàn thành, đọc counter.value().

Nếu muốn chạy phiên bản tải trên counter lỗi, thêm tạm thời đoạn sau vào main:

~~~java
int observedUnsafe = runConcurrentLoad(new UnsafeCounter());
System.out.println("Unsafe stress: " + observedUnsafe + " / " + expected);
~~~

Đây là **đoạn thay đổi main**, không phải tệp độc lập. Giá trị observedUnsafe **không được dự đoán chính xác**: có thể nhỏ hơn 100.000, nhưng đôi khi vẫn bằng 100.000. Không dùng assert observedUnsafe != expected để chứng minh lỗi, vì một lần không xuất hiện lỗi sẽ khiến test sai mục đích. Dùng forceLostUpdate() để chứng minh một lịch gây mất cập nhật.

Thử tăng số worker hoặc số vòng và quan sát mức độ biến động, nhưng không rút ra kết luận “không còn race” từ bất kỳ lần chạy thành công riêng lẻ nào.

### Bước B — Thay bằng lock

Tạo LockCounter, giữ nguyên giao diện Counter. Đặt lock.lock() trước khi đọc/tăng/ghi; unlock trong finally. Đặt phép đọc value() dưới **cùng lock**. Chạy lại runConcurrentLoad và kiểm tra đúng 100.000.

Có thể tự viết phiên bản synchronized tương đương:

~~~java
static final class SynchronizedCounter implements Counter {
    private int value;

    @Override
    public synchronized void increment() {
        value++;
    }

    @Override
    public synchronized int value() {
        return value;
    }
}
~~~

Đây là một class tích hợp trong CounterExercise.java, dùng chung interface Counter ở ví dụ chính. Bản synchronized chọn monitor của instance làm khóa. Không cần dùng ReentrantLock chỉ vì tên “lock”; chọn công cụ dựa trên nhu cầu kiểm soát acquisition, Condition, tryLock hay timeout.

### Bước C — Thay bằng atomic

Tạo AtomicCounter, dùng incrementAndGet() và get() trên **một AtomicInteger dùng chung**. Không sao chép giá trị int ra biến chia sẻ mới rồi tự tăng; chính phép cập nhật phải được thực hiện trên đối tượng atomic.

Chạy lại runConcurrentLoad, assert 100.000. Bỏ code khóa thủ công nếu bài toán chỉ còn một counter nguyên tử.

### Bước D — Bảo vệ cả test và tài nguyên

Đặt timeout cho các điểm chờ, bảo đảm exception trong worker được truyền ra main, và dùng finally để đóng executor. Nếu test timeout:

- Xác minh pool có đủ thread cho các bên đang chờ CyclicBarrier; hai party với pool một thread sẽ không thể cùng qua barrier.
- Xác minh số lần countDown và thời điểm mở start.
- Xác minh worker không ném lỗi trước khi đến barrier hoặc vòng lặp.
- Không coi timeout ở barrier hay Future.get là bằng chứng của lost update.

Sửa harness khi điều kiện thử không được thỏa, sau đó mới đánh giá bất biến nghiệp vụ.

## 6. Vì sao lock sửa được lỗi?

Với LockCounter, phép tăng được bảo vệ như một **critical section**:

~~~text
Thread A: lock → read 0 → compute 1 → write 1 → unlock
Thread B:                                        lock → read 1 → compute 2 → write 2 → unlock
~~~

Trong khi A giữ lock, B không thể thực hiện đoạn increment dùng cùng lock. B chỉ đọc sau khi A đã thả khóa. ReentrantLock thiết lập quan hệ đồng bộ tương ứng giữa unlock và lock tiếp theo; việc khóa cả value() còn giúp reader quan sát trạng thái đúng theo cùng giao thức đồng bộ.

Những lỗi thường gặp:

1. Dùng **hai đối tượng lock riêng** cho hai worker: không bảo vệ shared counter.
2. Khóa chỉ ở thao tác đọc rồi mở khóa trước thao tác ghi: hai worker vẫn có thể cùng chụp giá trị cũ.
3. Chỉ khóa increment nhưng một đường ghi khác trực tiếp sửa value: invariant vẫn có thể hỏng.
4. Quên unlock trong finally: lỗi giữa critical section có thể giữ khóa khiến worker khác kẹt.
5. Giữ khóa khi làm I/O chặn lâu: tăng cạnh tranh, latency và nguy cơ deadlock.
6. Thử thay lock bằng volatile: visibility không giải quyết được tính nguyên tử của value++.

**ReentrantLock là reentrant**: cùng thread đang giữ lock có thể lấy lại lock đó, nhưng phải unlock tương ứng số lần đã lấy. Tính năng này không thay thế việc thiết kế ranh giới critical section rõ ràng.

Nếu dùng lock.lockInterruptibly() hoặc tryLock(timeout, unit), có thể phản ứng tốt hơn khi bị hủy hoặc quá hạn trong lúc chờ khóa. Tuy nhiên, bài counter cơ bản chỉ cần lock(), try và finally.

## 7. Vì sao AtomicInteger sửa được lỗi?

AtomicInteger là bộ chứa giá trị int có các thao tác đọc/ghi và cập nhật với ngữ nghĩa đồng bộ được định nghĩa. incrementAndGet() là một **lần tăng nguyên tử**, không cho hai worker cùng “commit” một giá trị mới dựa trên cùng snapshot cũ như value++ không đồng bộ.

AtomicInteger hỗ trợ những thao tác hữu ích:

| API | Ý nghĩa |
| --- | --- |
| get() | Đọc giá trị hiện tại theo ngữ nghĩa atomic |
| set(v) | Đặt giá trị mới |
| incrementAndGet() | Tăng 1 và trả về giá trị mới |
| getAndIncrement() | Trả về giá trị cũ, sau đó tăng 1 |
| addAndGet(delta) | Cộng delta và trả về giá trị mới |
| compareAndSet(expect, update) | Chỉ cập nhật khi giá trị hiện tại bằng expect; trả boolean |

Khi bài toán có điều kiện cập nhật dựa trên giá trị cũ, dùng một thao tác nguyên tử thích hợp hoặc vòng compare-and-set. Ví dụ chỉ tăng nếu chưa đạt giới hạn, viết bằng updateAndGet:

~~~java
AtomicInteger quota = new AtomicInteger(3);
int remaining = quota.updateAndGet(
        current -> current > 0 ? current - 1 : current);
~~~

Đoạn trên cần import java.util.concurrent.atomic.AtomicInteger. Nó chỉ biểu diễn một **state transition nguyên tử của một biến**, không tự bảo đảm hành động nghiệp vụ bên ngoài diễn ra đúng một lần.

Quan trọng: Hàm cập nhật truyền vào updateAndGet có thể được gọi lại do cạnh tranh. Không đặt thao tác ghi database, gửi email, tăng biến ngoài hoặc side effect không thể lặp lại trong hàm lambda cập nhật. Với nhiều điều kiện, nhiều thuộc tính hay side effect phải đồng bộ cùng lúc, lock hoặc một mô hình trạng thái/giao dịch phù hợp có thể rõ ràng hơn.

AtomicInteger cũng có **giới hạn kiểu int**: nếu cộng vượt Integer.MAX_VALUE, giá trị sẽ tràn theo arithmetic của int. Chọn AtomicLong hoặc kiểm tra overflow khi miền giá trị yêu cầu. Tính nguyên tử không làm cho giá trị vô hạn.

## 8. Lock và AtomicInteger: chọn cái nào?

| Tiêu chí | ReentrantLock | AtomicInteger |
| --- | --- | --- |
| Phạm vi bảo vệ | Một vùng mã, có thể gồm nhiều biến | Một giá trị int và thao tác cập nhật nguyên tử trên nó |
| Cách dùng | lock → try → finally unlock | incrementAndGet/get/addAndGet/CAS |
| Khi tăng 1 | An toàn nếu mọi truy cập tuân thủ cùng lock | An toàn trực tiếp qua incrementAndGet |
| Khi có invariant nhiều trường | Thường thuận tiện vì có thể bảo vệ cả cụm | Một AtomicInteger riêng lẻ thường không đủ |
| Khả năng chờ | Có thể block khi chờ lock; có tryLock, interruptible acquire | Không giữ khóa do ứng dụng quản lý cho mỗi increment |
| Lỗi dễ gặp | Quên unlock, sai lock, deadlock, critical section dài | Ghép hai lệnh atomic rồi tưởng cả cặp là nguyên tử |
| Cần thử hiệu năng? | Có, với workload thật và mức contention thực | Có, không mặc định luôn nhanh hơn ở mọi tình huống |

Ví dụ trạng thái có **balance** và **transactionCount** phải cùng được cập nhật, dùng hai AtomicInteger riêng biệt chỉ cho mỗi biến tính nguyên tử; reader vẫn có thể thấy balance đã đổi nhưng count chưa đổi. Nếu cần invariant liên trường, bảo vệ cả cặp bằng một lock hoặc đại diện bất biến bằng một state object cập nhật nguyên tử (ví dụ AtomicReference tới state immutable) khi phù hợp.

Nếu nhu cầu chỉ là thống kê có số lần cập nhật rất cao và phép đọc tổng không cần một snapshot tuyến tính hóa với các cập nhật đang diễn ra, LongAdder có thể giảm contention trong một số tải. Tuy nhiên sum() của LongAdder **không phải snapshot nguyên tử** khi các luồng vẫn đang cập nhật; không thay thế AtomicInteger cho sequence number hoặc điều kiện ngưỡng cần đọc/ghi chính xác.

## 9. Kết nối kết quả thử với Java Memory Model

Một số quan hệ happens-before quan trọng:

- Các hành động trước unlock trên cùng một khóa happens-before các hành động sau lần lock tương ứng của thread tiếp theo.
- Các phương thức AtomicInteger có ngữ nghĩa memory consistency theo API atomic của Java.
- Hành động trước khi gọi ExecutorService.submit xảy ra trước hành động của task theo hợp đồng memory consistency của ExecutorService.
- Hành động trong task happens-before hành động sau khi lấy kết quả của nó bằng Future.get() thành công.
- countDown() của CountDownLatch xảy ra trước những hành động sau await() trở về thành công nhờ bộ đếm về 0.

Nhờ Future.get() thành công cho cả bốn worker, main có thể kiểm tra kết quả sau khi công việc đã hoàn tất. Nhưng Future.get **không làm cho những lần increment không đồng bộ bên trong worker trở thành nguyên tử**: nó chỉ thiết lập điểm hoàn tất/quan sát, không sửa cuộc đua giữa các worker trong quá trình chạy.

Tương tự, CountDownLatch ở đầu bài tải chỉ giúp worker bắt đầu gần nhau; nó không bảo vệ shared value. CyclicBarrier trong forceLostUpdate **được đặt giữa read và write** để chủ động khóa một interleaving gây sai, không phải lời khuyên đặt barrier vào logic increment thực tế.

Không dùng synchronized trên một object bất kỳ rồi mong toàn bộ trường chia sẻ tự an toàn. Các thread phải đồng thuận về **cùng giao thức đồng bộ** tại đúng dữ liệu và đúng phạm vi thao tác.

## 10. Thiết kế phép kiểm thử đúng thay vì nhìn output may rủi

Có ba tầng kiểm tra hữu ích:

**Tầng 1 — Reproduction có lịch dàn dựng.** forceLostUpdate bắt cả hai worker đọc cùng snapshot trước khi ghi. Với hai yêu cầu tăng, expected là 1 trong **demo cố tình sai**, để thấy một lịch làm hỏng invariant. Không dùng expected = 1 làm oracle cho counter đã sửa.

**Tầng 2 — Kiểm tra chức năng của bản sửa.** runConcurrentLoad trên LockCounter và AtomicCounter, sau khi mọi worker thành công, kết quả phải bằng WORKERS × INCREMENTS_PER_WORKER. Khi kết quả khác expected hoặc có exception, test phải thất bại.

**Tầng 3 — Stress test bổ sung.** Thay đổi số thread, số lượt tăng, môi trường chạy, nhiều lần lặp, tranh chấp trên cùng counter và tình huống hủy/timeout. Stress test có thể phát hiện thêm lỗi, nhưng việc vượt qua nhiều lượt stress **không chứng minh hết mọi race có thể xảy ra**.

Nếu chạy JUnit ở dự án Java hiện có, assertion có thể nằm trong test thay cho if/throw AssertionError trong main. Ví dụ main của bài này vẫn độc lập với thư viện test để người học có thể chạy trực tiếp với JDK 17. Điều quan trọng là kiểm tra invariant và lỗi worker, không phụ thuộc vào tên framework.

### Những trường hợp cần chủ động thử thêm

- **0 increment:** Giá trị phải giữ nguyên, không phát sinh side effect.
- **1 worker:** UnsafeCounter có thể cho kết quả đúng vì không có thread khác tranh chấp; không chứng minh thread-safety.
- **N worker:** Hai bản sửa cho kết quả đúng bằng N × số lần tăng khi không bị tràn int và mọi task hoàn thành.
- **Worker ném exception:** Future.get phải báo lỗi; không được mặc nhiên khẳng định toàn bộ số lượt đã chạy.
- **Timeout/interrupt:** Test phải dừng có kiểm soát và không kẹt vô hạn ở latch/barrier.
- **Cập nhật cùng lúc với đọc:** LockCounter.value() tuân thủ cùng khóa; AtomicCounter.value() đọc atomically. Đọc counter trong khi các worker đang chạy có thể cho giá trị trung gian hợp lệ, không buộc phải bằng tổng cuối.

## 11. Lỗi phổ biến khi thực hiện bài tập

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Mỗi thread tạo một Counter riêng | Không còn shared state cần kiểm tra | Tất cả worker nhận cùng instance |
| Dùng value++ trên int hoặc volatile int | Lost update trong read-modify-write | Lock cả cụm hoặc dùng atomic increment |
| Khóa riêng từng thread | Không phối hợp được giữa worker | Dùng cùng object lock của shared counter |
| Đọc dưới lock, ghi ngoài lock | Đường cập nhật không còn được bảo vệ | Mọi truy cập liên quan tuân thủ cùng lock |
| Quên unlock trong finally | Có thể giữ lock vĩnh viễn khi lỗi | try/finally |
| Dùng sleep để “chờ hai thread đụng nhau” | Lịch chạy không được bảo đảm | Điểm phối hợp có kiểm soát cho reproduction |
| Cho barrier 2 parties nhưng pool 1 worker | Worker bị kẹt chờ party còn lại | Pool đủ worker và timeout |
| Không chờ Future.get | Main đọc khi worker còn tăng | Đợi toàn bộ Future hoàn thành |
| Worker lỗi nhưng test vẫn PASS | Kết quả được đo trên số thao tác thiếu | Lấy exception của Future và fail test |
| Test unsafe ngẫu nhiên có đúng kết quả rồi kết luận hết race | False negative | Reproduction cưỡng bức lịch sai + review |
| Ghép nhiều thao tác atomic rồi coi cả chuỗi atomic | Invariant nhiều bước vẫn hỏng | Mở rộng vùng khóa hoặc cập nhật một state nguyên tử |
| Đặt side effect vào lambda updateAndGet | Lambda có thể được gọi lại | Dùng hàm cập nhật thuần |
| So sánh hiệu năng trong một lần chạy ngắn | JIT, warm-up, scheduler làm méo kết quả | Benchmark chuẩn với workload đại diện |

## 12. Bài tập mở rộng và câu hỏi tự kiểm tra

**Bài 1 — Tự viết SynchronizedCounter.** Dùng synchronized bảo vệ increment() và value(); truyền class đó vào runConcurrentLoad. Giải thích vì sao kết quả đúng, khóa monitor là đối tượng nào, và tại sao hai instance khác nhau không khóa lẫn nhau.

**Bài 2 — Thêm điều kiện giới hạn.** Counter không được vượt 10.000. So sánh mẫu sai if (counter.value() < 10_000) counter.increment() với bản dùng một lock cho cả check-and-increment. Nêu lý do vì sao tách hai lời gọi thread-safe chưa đủ để bảo toàn invariant.

**Bài 3 — Viết compare-and-set.** Dùng AtomicInteger để tăng chỉ khi chưa đạt giới hạn, theo vòng lặp: đọc current → nếu đạt ngưỡng thì trả false → thử compareAndSet(current, current + 1) → retry khi CAS thất bại. Phân biệt retry do contention với retry của nghiệp vụ bên ngoài.

**Bài 4 — Đo và giải thích contention.** So sánh lock, atomic và LongAdder khi số worker tăng, nhưng thiết lập benchmark đúng cách. Không suy ra kết luận từ chỉ một lần chạy javac/java; cần warm-up, workload phù hợp, đo đủ lần và công cụ benchmark như JMH khi cần đánh giá nghiêm túc.

**Bài 5 — Kiểm tra hủy tác vụ.** Cho worker cố tình đợi một cổng không bao giờ mở; xác minh timeout khiến bài test thất bại rõ ràng, futures bị cancel, executor được shutdown và không báo rằng đã tìm thấy lost update chỉ vì thiếu worker.

Tự trả lời trước khi hoàn tất:

1. Nếu dùng volatile int thay cho int, tại sao vẫn có thể mất increment?
2. Vì sao Future.get() đảm bảo main đọc sau khi worker hoàn thành nhưng không sửa race trong worker?
3. Khi một bất biến phụ thuộc cả count và balance, hai AtomicInteger riêng lẻ đã đủ chưa?
4. Có thể gọi lock.unlock() ở cuối try mà không có finally không?
5. Vì sao kết quả UnsafeCounter bằng expected ở một lần chạy stress chưa chứng minh an toàn?

## 13. Checklist hoàn thành

- [ ] Có một Counter dùng chung được nhiều worker gọi increment.
- [ ] Giải thích được read-modify-write của phép value++ và một interleaving gây lost update.
- [ ] Tái hiện được forced lost update = 1 sau **hai** lần tăng bằng harness.
- [ ] Viết được LockCounter giữ **cùng lock** cho increment và value, dùng finally.
- [ ] Viết được AtomicCounter với incrementAndGet và get.
- [ ] Chạy thành công CounterExercise.java bằng javac và java 17+; hai bản sửa cho 100.000/100.000.
- [ ] Worker exception, timeout và shutdown được xử lý; không đánh giá thành công khi test chưa hoàn tất.
- [ ] Phân biệt được phép tăng một biến với invariant nhiều biến; chọn lock/atomic theo đúng phạm vi nghiệp vụ.

**Kết quả học tập:** Cách sửa race condition không nằm ở việc tăng thời gian chờ hay làm các worker “ít đụng nhau” hơn. Hãy chỉ rõ shared state và invariant, biến chuỗi cập nhật thành một đơn vị nguyên tử bằng **lock** hoặc **AtomicInteger** phù hợp, rồi kiểm tra bằng một lịch tái hiện lỗi và một phép đo hồi quy có điều kiện hoàn tất rõ ràng.
