# Minh họa lỗi race condition bằng test điều phối thời điểm thực thi trong Java

Race condition là lỗi mà kết quả của chương trình phụ thuộc vào thứ tự và thời điểm các thao tác đồng thời xen kẽ nhau. Vì hệ điều hành và JVM có quyền lên lịch thread theo nhiều cách, một đoạn code sai có thể chạy đúng hàng nghìn lần rồi mới lỗi. **Một test “chạy nhiều thread rồi hy vọng đụng nhau” không đủ để chứng minh hoặc tái hiện một race cụ thể.** Ta có thể chủ động tạo ra lịch thực thi nguy hiểm bằng công cụ đồng bộ để chứng minh một invariant bị vi phạm, rồi chạy cùng tình huống trên thiết kế đã sửa.

Bài học tập trung vào **Java concurrency thuần** và các công cụ có sẵn trong `java.util.concurrent`. Mục tiêu là biết cách viết **test điều phối interleaving**, giải thích từng điểm chờ, quan sát lỗi một cách có kiểm soát, đặt timeout tránh treo suite test, chuyển lỗi từ worker về test runner và hiểu giới hạn của loại test này. Đây không phải bài hướng dẫn một framework cụ thể.

## 1. Vì sao race condition khó tái hiện?

Giả sử hai thread cùng tăng một biến:

```java
class UnsafeCounter {
    int count;

    void increment() {
        count++;
    }
}
```

Đây là **đoạn minh họa**, chưa có `main`. `count++` là thao tác read–modify–write về mặt logic: đọc giá trị cũ, cộng một, ghi kết quả mới. Nó **không nguyên tử** đối với các thread khác nếu chỉ là field `int` thông thường. Nếu A và B đều đọc giá trị `0` trước khi một trong hai ghi, cả hai có thể ghi lại `1`; sau hai lần gọi `increment()`, tổng chỉ là `1` thay vì `2`.

| Thời điểm logic | Worker A | Worker B | `count` |
| --- | --- | --- | --- |
| Ban đầu | | | `0` |
| 1 | Đọc `0` | | `0` |
| 2 | | Đọc `0` | `0` |
| 3 | Ghi `0 + 1` | | `1` |
| 4 | | Ghi `0 + 1` | `1` |

Đây là **lost update**: một lần cập nhật về nghiệp vụ không được tính vào trạng thái cuối. Bảng mô tả các bước ở cấp logic, không khẳng định JIT phải tạo đúng ba lệnh CPU cho phép `count++`.

Khi viết test thông thường:

```java
Thread a = new Thread(counter::increment);
Thread b = new Thread(counter::increment);
a.start();
b.start();
a.join();
b.join();
```

test có thể thấy `2` vì A kết thúc trước B bắt đầu, hoặc các bước không chồng lên nhau. Thêm vòng lặp hàng triệu lần làm tăng cơ hội gặp lỗi nhưng **không đảm bảo** cùng một interleaving sẽ xuất hiện. `Thread.sleep(1)` cũng không áp đặt thứ tự cần thiết: scheduler không bảo đảm thread nào chạy ngay khi thời gian ngủ kết thúc.

**Cách kiểm thử tốt hơn cho một lịch lỗi đã biết:** chia thao tác logic thành các bước có thể kiểm soát; đặt *rendezvous* (điểm gặp) sau khi cả hai worker đọc trạng thái và trước khi cả hai ghi. Khi điều kiện gặp đã thỏa, cho phép chúng tiếp tục. Test sẽ lặp lại đúng loại lịch nguy hiểm mà ta muốn minh họa.

## 2. Xác định invariant trước khi dựng test

Một test race có giá trị khi nêu rõ điều kiện đúng cần được bảo toàn:

| Nghiệp vụ | Invariant cần giữ | Race có thể tạo |
| --- | --- | --- |
| Hai lần tăng counter | Sau hai increment thành công, giá trị tăng đúng `2` | Lost update, kết quả chỉ tăng `1` |
| Một ghế chỉ bán một lần | Có tối đa một xác nhận đặt chỗ thành công | Hai người cùng thấy còn ghế và được xác nhận |
| Trừ hàng tồn kho | Không bán quá số lượng tồn thực tế | Nhiều thread cùng qua kiểm tra tồn kho |
| Chỉ khởi tạo cache entry một lần | Một key không có hai lần khởi tạo nghiệp vụ gây side effect | Hai thread cùng check rồi cùng create |
| Cập nhật hai trường liên quan | Reader quan sát một snapshot thỏa bất biến | Reader thấy dữ liệu của hai phiên bản |
| Quản lý vòng đời | Sau khi shutdown, không nhận công việc mới trái hợp đồng | Check trạng thái rồi submit bị xen vào bởi shutdown |

**Phân biệt:** *data race* là khái niệm của Java Memory Model khi có các truy cập xung đột mà không có quan hệ happens-before thích hợp. *Race condition* rộng hơn, bao gồm lỗi nghiệp vụ do các **thao tác đơn lẻ đều thread-safe nhưng tổ hợp của chúng không atomic**. Test điều phối có thể làm lộ lỗi check–then–act ngay cả khi từng bước đã dùng cấu trúc đồng bộ.

Đừng chỉ assert “không ném exception”. Với race, nhiều kết quả sai vẫn trả về thành công; test phải xác minh số lượng cập nhật, số xác nhận, số dư hoặc invariant cụ thể.

## 3. Bộ công cụ Java để điều phối thời điểm

| Công cụ | Vai trò khi test | Điểm cần nhớ |
| --- | --- | --- |
| `CountDownLatch(n)` | Chờ đủ `n` sự kiện rồi mới mở một giai đoạn | Bộ đếm chỉ giảm, **không reset**; thích hợp cổng bắt đầu/kết thúc một lần |
| `CyclicBarrier(n)` | Buộc `n` participant tới cùng điểm trước khi ai tiếp tục | Tái sử dụng qua nhiều vòng; nếu một participant timeout/interrupt, barrier có thể bị **broken** |
| `Phaser` | Điều phối nhiều pha, số participant có thể thay đổi | Linh hoạt hơn, nhưng phức tạp hơn latch/barrier |
| `Thread.join()` | Chờ một thread kết thúc | Không bảo đảm thread đã đi qua checkpoint mong muốn trước khi kết thúc |
| `Future.get(timeout, unit)` | Nhận kết quả/exception của worker và có deadline | Timeout khi đợi không tự đồng nghĩa worker đã bị hủy |
| `ExecutorService` với số worker đủ | Chạy các participant | Pool có ít worker hơn số task cùng đợi barrier có thể tự gây deadlock |
| `AtomicInteger`/`AtomicBoolean` | Ghi nhận kết quả hoặc tín hiệu từ nhiều worker an toàn | Không tự khiến một workflow gồm nhiều bước trở thành atomic |
| `Semaphore` | Giới hạn số worker được phép đi qua một vùng | Không tạo rendezvous toàn bộ participant như barrier |

Một cách biểu diễn lịch bằng barrier:

```text
Worker A: READ count=0 -----> [barrier] -----> WRITE 1
Worker B: READ count=0 -----> [barrier] -----> WRITE 1
                                  |
                            đủ 2 participant
                                  |
                         cả hai được tiếp tục
```

Khi A đến điểm gặp trước, nó phải đợi B; khi B đến, cả hai được phép tiếp tục. **Điểm quan trọng là tất cả READ đã xong trước khi bất kỳ WRITE nào bắt đầu.** Ta không cần và không thể quyết định chính xác worker nào chạy trước sau khi barrier mở; trong ví dụ này cả hai đều ghi cùng giá trị `1` nên kết quả vẫn xác định.

### Khác nhau giữa điều phối test và sửa production

- **Điều phối test** tạo một lịch thực thi có chủ đích để khám phá hoặc chứng minh lỗi. Nó *có thể tạo thêm happens-before* và ảnh hưởng những interleaving khác.
- **Sửa production** bảo đảm thao tác nghiệp vụ đúng trước **mọi interleaving được hợp đồng cho phép**, bằng mutual exclusion, CAS, atomic API, immutable state, message passing hoặc thiết kế ownership phù hợp.
- Nếu test ép cả hai worker đọc một snapshot cũ rồi vẫn được quyền ghi dựa trên snapshot ấy, đó là lỗi **giao thức read–modify–write**, nhưng không thể suy diễn máy móc rằng test này chứng minh mọi truy cập là *data race hình thức* theo JMM. Latch/barrier tự chúng là primitive đồng bộ và thiết lập những quan hệ happens-before.

## 4. Ví dụ Java 17 hoàn chỉnh: ba phép thử điều phối

Chúng ta sẽ chạy ba tình huống trong cùng một chương trình Java 17:

1. **Lost update bị ép xuất hiện:** hai worker đọc chung giá trị `0`, cùng chờ barrier rồi ghi `1`; test kiểm tra rằng hai lần tăng chỉ tạo `1`, tức invariant đúng `2` bị vi phạm.
2. **Đặt chỗ trùng:** hai worker cùng kiểm tra “chưa có ai đặt” trước barrier, sau đó mỗi worker xác nhận một chỗ; số xác nhận thành công thành `2`, vượt quá giới hạn `1`.
3. **Sửa bằng critical section:** dùng `synchronized` để gộp check–then–set thành một thao tác. Hai worker vẫn thử đặt, nhưng chỉ một worker được xác nhận.

Tạo tệp **`CoordinatedRaceTest.java`**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CoordinatedRaceTest {
    private static final int TIMEOUT_SECONDS = 5;

    static class Counter {
        int value = 0;
    }

    static class UnsafeSeat {
        boolean booked = false;
    }

    static class SafeSeat {
        private boolean booked = false;

        synchronized boolean bookOnce() {
            if (booked) {
                return false;
            }
            booked = true;
            return true;
        }
    }

    private static void assertEquals(int expected, int actual, String name) {
        if (actual != expected) {
            throw new AssertionError(
                    name + ": expected=" + expected + ", actual=" + actual);
        }
    }

    private static void runTwo(Callable<Void> task) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Void> first = pool.submit(task);
            Future<Void> second = pool.submit(task);

            first.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
            second.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } finally {
            pool.shutdownNow();
        }
    }

    private static void reproduceLostUpdate() throws Exception {
        Counter counter = new Counter();
        CyclicBarrier bothRead = new CyclicBarrier(2);

        runTwo(() -> {
            int snapshot = counter.value; // Cả hai đọc 0
            bothRead.await(TIMEOUT_SECONDS, TimeUnit.SECONDS);
            counter.value = snapshot + 1;
            return null;
        });

        // Chủ động xác nhận lịch lỗi đã được tái hiện.
        assertEquals(1, counter.value, "lost update");
        System.out.println("lost update: actual=1, correct=2");
    }

    private static void reproduceDoubleBooking() throws Exception {
        UnsafeSeat seat = new UnsafeSeat();
        AtomicInteger confirmations = new AtomicInteger();
        CyclicBarrier bothChecked = new CyclicBarrier(2);

        runTwo(() -> {
            boolean available = !seat.booked; // Cả hai thấy còn chỗ
            bothChecked.await(TIMEOUT_SECONDS, TimeUnit.SECONDS);

            if (available) {
                seat.booked = true;
                confirmations.incrementAndGet();
            }
            return null;
        });

        assertEquals(2, confirmations.get(), "double booking");
        System.out.println("double booking: actual=2, allowed=1");
    }

    private static void verifyFixedBooking() throws Exception {
        SafeSeat seat = new SafeSeat();
        AtomicInteger confirmations = new AtomicInteger();

        runTwo(() -> {
            if (seat.bookOnce()) {
                confirmations.incrementAndGet();
            }
            return null;
        });

        // Đây là invariant nghiệp vụ cần bảo toàn.
        assertEquals(1, confirmations.get(), "fixed booking");
        System.out.println("fixed booking: actual=1, allowed=1");
    }

    public static void main(String[] args) throws Exception {
        reproduceLostUpdate();
        reproduceDoubleBooking();
        verifyFixedBooking();
    }
}
```

Biên dịch và chạy:

```bash
javac CoordinatedRaceTest.java
java CoordinatedRaceTest
```

**Stdout chính xác khi chương trình hoàn thành bình thường:**

```text
lost update: actual=1, correct=2
double booking: actual=2, allowed=1
fixed booking: actual=1, allowed=1
```

Nếu môi trường không chạy được đủ participant hoặc task bị interrupt/timeout, phép thử **thất bại bằng exception** thay vì in kết quả sai lệch như thể thành công. Lý do có `Future.get(timeout)` và `CyclicBarrier.await(timeout)` là bảo vệ test khỏi chờ vô hạn, không phải xác lập một khoảng ngủ dùng để gây race.

### Phân tích từng phép thử

**Phép 1 — lost update**

- `counter` là một instance chung cho hai worker.
- `snapshot` là biến local riêng của từng lần chạy `Callable`.
- Mỗi worker đọc `counter.value` trước khi đến `bothRead.await(...)`.
- Barrier mở khi hai worker đều đến, nên tại thời điểm đọc không ai đã ghi.
- Cả hai có `snapshot == 0`, đều ghi `1`; trạng thái cuối `1`, dù có hai lần tăng về nghiệp vụ.

Đoạn code cố tình biến `counter.value++` thành read và write riêng để **đặt checkpoint giữa hai bước**. Đó là một *test harness* mô phỏng thao tác không atomic; nó không có nghĩa trong production phải viết phép tăng thành hai dòng để mới sinh race. Với `counter.value++` thực, lịch đọc chồng lên nhau vẫn có thể xảy ra khi thiếu đồng bộ.

**Phép 2 — check–then–act**

- `seat.booked` là cờ dùng chung ban đầu `false`.
- Cả hai lấy `available = !seat.booked` trước barrier và đều được `true`.
- Sau barrier, mỗi worker tin thông tin cũ vẫn đúng; hai worker cùng xác nhận đặt chỗ.
- Dùng `AtomicInteger confirmations` chỉ để **đo chính xác hai xác nhận**, tránh chính biến đếm trong test bị lost update che mất lỗi. `AtomicInteger` ở đây **không làm cờ `booked` an toàn**.

Race nghiệp vụ xảy ra vì “kiểm tra còn chỗ” và “đặt chỗ” là hai bước không nguyên tử. Nó khác lỗi tăng counter nhưng cùng bản chất: **quyết định dựa trên snapshot đã bị các thread khác làm thay đổi**.

**Phép 3 — gộp thao tác thành một critical section**

- `SafeSeat.bookOnce()` bảo vệ cả hai bước `if (booked)` và `booked = true` bằng **monitor của cùng một instance `seat`**.
- Một worker vào trước thấy `false`, đổi sang `true` và trả `true`.
- Worker còn lại chỉ vào sau khi monitor được nhả, nhìn thấy `true` và trả `false`.
- Bất kể thứ tự worker, đúng một xác nhận được tăng.

**Vì sao test sửa lỗi không đặt barrier trong `bookOnce()`?** Nếu một worker đã lấy monitor rồi chờ `CyclicBarrier(2)` ngay **bên trong** method `synchronized`, worker thứ hai không thể vào method để tới barrier. Test sẽ tự gây deadlock/timeout, không phải do code production sai. Điều phối trước khi tranh khóa hoặc quan sát kết quả sau khi cả hai hoàn tất, **không đặt rendezvous trong critical section được thực thi độc quyền**.

### Vì sao không dùng `assert` mặc định của Java?

Java `assert` có thể bị vô hiệu khi không bật tùy chọn JVM `-ea`. Hàm `assertEquals` riêng ở trên ném `AssertionError` vô điều kiện khi khác giá trị mong đợi, nên test không bị “vô hiệu hóa” vì thiếu tham số chạy. Khi đưa sang JUnit, có thể dùng `org.junit.jupiter.api.Assertions.assertEquals`; ví dụ hiện tại **không cần thư viện test ngoài JDK**.

## 5. Hai kiểu điều phối quan trọng: rendezvous và cổng một chiều

### 5.1. `CyclicBarrier`: mọi người đều tới checkpoint

Dùng barrier khi muốn bảo đảm hai hay nhiều thread đều đã hoàn thành một pha trước khi bất kỳ thread nào bước sang pha tiếp theo:

```java
CyclicBarrier barrier = new CyclicBarrier(2);

Runnable action = () -> {
    try {
        // Pha A: đọc hoặc quan sát trạng thái
        barrier.await(5, TimeUnit.SECONDS);
        // Pha B: cập nhật dựa trên trạng thái đã đọc
    } catch (Exception e) {
        throw new RuntimeException(e);
    }
};
```

Đoạn trên chỉ là **snippet**, chưa có `main` hay worker. `await(timeout)` có thể ném `InterruptedException`, `BrokenBarrierException` hoặc `TimeoutException`; ví dụ gộp vào một nhánh lỗi để minh họa cấu trúc, nhưng trong ứng dụng thật cần xử lý interrupt phù hợp.

- `CyclicBarrier(2)` đòi **hai lần gọi `await` trong cùng một thế hệ (generation)**, không phải chỉ một worker.
- Nếu chỉ có một worker trong pool và task thứ nhất đợi barrier, task thứ hai đang chờ trong queue không bao giờ đến barrier; có timeout thì test thất bại nhanh hơn, nhưng vẫn là lỗi điều phối.
- Barrier có thể tái sử dụng nhiều vòng. Nếu một participant lỗi, thoát sớm hoặc timeout, barrier bị broken; cần xử lý tình trạng ấy trước khi reuse.
- Hợp đồng memory consistency của `CyclicBarrier` hỗ trợ chuyển giao dữ liệu giữa các pha; do đó **không dùng barrier để chứng minh thiếu visibility tự phát trên một field**.

### 5.2. `CountDownLatch`: main điều khiển khi nào mở cổng

Một lịch test thường gặp gồm ba mốc: hai task đã sẵn sàng → main ra lệnh bắt đầu → main đợi cả hai kết thúc. Ví dụ độc lập Java 17:

Tệp `StartGateExample.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class StartGateExample {
    public static void main(String[] args) throws Exception {
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(2);
        AtomicInteger completed = new AtomicInteger();

        Runnable task = () -> {
            try {
                ready.countDown();
                start.await();
                completed.incrementAndGet();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                done.countDown();
            }
        };

        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.start();
        second.start();

        if (!ready.await(5, TimeUnit.SECONDS)) {
            start.countDown();
            throw new IllegalStateException("Workers not ready");
        }
        start.countDown();

        if (!done.await(5, TimeUnit.SECONDS)) {
            first.interrupt();
            second.interrupt();
            throw new IllegalStateException("Workers not finished");
        }

        first.join();
        second.join();
        System.out.println("completed=" + completed.get());
    }
}
```

```bash
javac StartGateExample.java
java StartGateExample
```

Stdout khi hoàn thành bình thường:

```text
completed=2
```

**Vai trò của từng latch:**

- `ready`: mỗi worker báo đã đến checkpoint trước khi main mở cổng.
- `start`: main quyết định khi nào các worker được tiếp tục. Một `countDown()` mở cổng cho **tất cả** waiter.
- `done`: đếm worker đã đi qua khối `finally` để main không kết luận sớm.
- `AtomicInteger`: ghi số task hoàn thành không bị lost update.

Ví dụ dùng `start.await()` không timeout ở worker để minh họa cổng, nhưng main **chắc chắn mở cổng trên đường thành công hoặc khi `ready` timeout**; khi dùng trong test suite phức tạp, có thể thay bằng timed await và quản lý việc hủy để hạn chế thread còn sống sau thất bại. `CountDownLatch` dùng một lần; muốn tổ chức giai đoạn tiếp theo, tạo latch mới hoặc chọn `Phaser`.

**Khác biệt chính:** `CyclicBarrier` tự mở khi đủ participant; `CountDownLatch` cho phép một hoặc nhiều thread bên ngoài mở cổng chủ động. Với race cần ép cả hai *đã đọc xong* trước khi ghi, barrier thường trực tiếp hơn; với test cần main giữ tất cả worker tại start gate, latch phù hợp hơn.

## 6. Kiểm soát checkpoint đúng vị trí

Để tái hiện race đã nghi ngờ, cần phân rã thao tác ở đúng ranh giới:

| Race muốn kiểm tra | Điểm dừng phù hợp | Điều quan sát sau khi mở |
| --- | --- | --- |
| Lost update | Sau khi mỗi worker đọc counter, trước khi ghi | Counter tăng thiếu |
| Double booking | Sau khi cả hai đọc `available=true`, trước khi đặt | Có hơn một confirmation |
| Cache init trùng | Sau khi cả hai xác định cache miss, trước khi put/create | Create chạy nhiều lần |
| Stock oversell | Sau khi hai worker thấy còn hàng, trước khi trừ | Đã bán vượt tồn |
| Shutdown vs submit | Sau khi caller đọc trạng thái hoạt động, trước khi submit | Operation có thể vượt quy tắc vòng đời |
| Snapshot nhiều field | Giữa bước cập nhật field A và field B | Reader thấy invariant bị phá vỡ |

**Điều phối không đồng nghĩa với việc can thiệp vào tất cả mã production.** Trong test có thể đưa logic gây nghi ngờ vào một class nhỏ có hook/checkpoint hoặc test harness tái tạo thuật toán với cùng các bước. Tuy nhiên, test có hook chỉ chứng minh hành vi trên đường đi đã được dựng. Với module thực tế cần bổ sung integration test trên đúng implementation đang chạy để tránh test chỉ kiểm tra một bản sao thuật toán.

Ví dụ một thiết kế test seam rõ ràng có thể tách `readSnapshot`, `applyUpdate` hoặc dùng interface callback do test cung cấp **giữa hai thao tác vốn chưa được đồng bộ**. Cẩn thận: nếu thêm callback hoặc barrier **bên trong một critical section đúng** để ép hai thread gặp nhau, test có thể tự làm deadlock; test phải tôn trọng locking contract.

## 7. Thiết kế test không flaky: kiểm soát lỗi và kết thúc worker

### 7.1. Vì sao cần đưa exception từ worker về main?

Exception xảy ra trong `Runnable` có thể chỉ xuất hiện ở stderr của thread đó. Nếu test runner không chờ/thu kết quả đúng cách, test có thể thông báo pass dù worker thất bại. Với `ExecutorService.submit` và `Future.get()`, lỗi từ `Callable` được chuyển thành `ExecutionException` ở bên gọi, giúp case test fail thay vì im lặng.

`Future.get(timeout)` còn ngăn main đợi vô hạn. Khi timeout, phải xử lý hậu quả: hủy task, interrupt nếu thích hợp, đóng executor, và điều tra xem worker có đang giữ lock hoặc chờ một barrier không thể đủ participant. **Timeout chỉ giới hạn thời gian caller chờ, không tự động làm task ngừng chạy.** `shutdownNow()` cố gắng interrupt các task còn chạy; nó không bảo đảm mọi task hợp tác dừng ngay.

### 7.2. Luôn đặt deadline cho rendezvous có nguy cơ thiếu participant

Có thể dùng:

```java
barrier.await(5, TimeUnit.SECONDS);
```

hoặc:

```java
if (!ready.await(5, TimeUnit.SECONDS)) {
    throw new AssertionError("Missing worker");
}
```

Đây là hai **snippet**, giả sử `barrier` và `ready` đã được khởi tạo phù hợp. Deadline giúp test **thất bại có tín hiệu rõ ràng** nếu worker không tới checkpoint. Chọn timeout đủ cho máy CI chậm và báo lỗi chính xác; đừng dùng timeout nhỏ tới mức tạo lỗi ngẫu nhiên chỉ vì scheduler.

### 7.3. Chỉ assert sau khi tác vụ liên quan đã hoàn tất

Đọc một counter khi hai worker còn đang ghi có thể tạo thêm race ngay trong test. Hãy chờ `Future.get()` hoặc `Thread.join()` hoàn tất rồi mới kiểm tra kết quả. Các API này cũng có memory-consistency guarantees hỗ trợ quan sát thay đổi của worker theo hợp đồng Java.

### 7.4. Không để `Thread.sleep` điều khiển thứ tự

`sleep` làm thread tạm ngừng một khoảng tối thiểu tùy scheduler; nó không nói “thread B chắc chắn đã đọc state” hay “thread A đã qua checkpoint”. Nếu test cần chứng minh hai worker đều sẵn sàng, dùng latch/barrier. Có thể dùng `sleep` để mô phỏng I/O trong test hiệu năng, nhưng **không dùng nó thay chứng cứ đồng bộ**.

### 7.5. Đặt cổng với số participant chính xác

Một `CyclicBarrier(3)` nhưng chỉ có hai worker gọi `await` sẽ không mở. Nếu main cũng gọi `await` thì tính main là participant thứ ba; nếu main không gọi thì chỉ đặt `2`. Nếu pool có một worker trong khi hai task phải gặp cùng barrier, task thứ nhất chiếm worker rồi đợi task thứ hai mãi. Trong chương trình chính, `newFixedThreadPool(2)` đảm bảo có đủ worker cho hai participant cùng chờ.

### 7.6. Kiểm soát interruption

`InterruptedException` là tín hiệu ngắt cần được chuyển tiếp hoặc được tôn trọng. Nếu không thể ném tiếp trong `Runnable`, khôi phục `Thread.currentThread().interrupt()` và thoát. Nếu ignore interrupt trong vòng đợi vô hạn, `shutdownNow` có thể không giúp test đóng hết worker. Với `CyclicBarrier`, thread bị interrupt có thể làm barrier bị broken; test nên thất bại rõ ràng thay vì giả định mọi participant đã tiếp tục.

## 8. Tại sao kết quả test ở ví dụ là xác định?

Ba phép thử trong `CoordinatedRaceTest` không dùng timing ngẫu nhiên để áp đặt thứ tự. Độ chắc chắn dựa vào:

1. Cả hai worker được submit vào pool hai thread.
2. Cả hai worker **đọc giá trị cần dùng trước khi gọi `barrier.await()`**.
3. Không worker nào ghi vào state liên quan trước khi cả hai đã tới barrier.
4. Sau khi barrier mở, thứ tự ghi có thể khác nhau nhưng ở tình huống lỗi cả hai đều ghi cùng giá trị (counter `1`, seat `true`).
5. `Future.get()` trả về sau khi cả hai task hoàn tất; main mới kiểm tra và in.
6. `AtomicInteger confirmations` ngăn chính công cụ đo số xác nhận bị race.

Ví dụ giả định không có interrupt ngoài ý muốn, không hết deadline và máy đủ tài nguyên hoàn thành task. Nếu một điều kiện vận hành đó không được đáp ứng, test có thể fail/timeout. **Không nên biến cam kết “cùng một lịch logic” thành cam kết JVM sẽ luôn hoàn thành trong chính xác 5 giây** ở mọi môi trường.

Đối với counter, barrier tạo ra thứ tự mà các lần đọc xảy ra trước các lần ghi. Vì vậy test này đặc biệt tốt để chứng minh **sự thiếu atomicity của cả workflow**, nhưng không mô phỏng đầy đủ tập hợp interleaving và tái sắp xếp mà JMM cho phép khi hoàn toàn thiếu đồng bộ. Không dùng nó để chứng minh visibility bug hoặc reorder bug chỉ bằng một kết quả.

## 9. Viết một test phải FAIL với code lỗi rồi PASS sau khi sửa

Trong ví dụ đầu, `assertEquals(1, counter.value)` xác nhận **test harness đã tái hiện lỗi**, nên bản thân chương trình vẫn in kết quả và không fail. Khi biến tình huống thành regression test, **điều kiện kỳ vọng phải là invariant đúng của nghiệp vụ**:

```java
// Trong một regression test dành cho counter đúng:
if (counter.value != 2) {
    throw new AssertionError(
            "Lost update: expected=2, actual=" + counter.value);
}
```

Đây là snippet đặt sau khi đã đợi mọi worker hoàn thành. Với implementation lỗi, assertion này fail có chủ đích; sau khi sửa thao tác increment bằng `synchronized` hoặc `AtomicInteger.incrementAndGet()`, test tương ứng phải pass.

**Không nên chỉ thay một câu lệnh ghi trong test đã dựng lịch lỗi rồi kỳ vọng kết quả tự đổi.** Một test được thiết kế để **cả hai cố ý đọc trước và sau đó ghi snapshot cũ** sẽ vẫn tạo lost update ngay cả nếu từng lần đọc/ghi là atomic. Phải thay **đơn vị thao tác nghiệp vụ** thành thao tác atomic, chẳng hạn thay cả cặp “đọc snapshot → ghi snapshot+1” bằng `AtomicInteger.incrementAndGet()`, hoặc bảo vệ toàn bộ chuỗi read–modify–write bằng cùng monitor. Nếu cố chèn `CyclicBarrier(2)` **bên trong** `synchronized` bao toàn bộ read–modify–write, test sẽ deadlock vì worker thứ hai không thể vào critical section.

Một chiến lược test gọn:

- **Reproduction test:** dựng interleaving làm lỗi xuất hiện trên phiên bản không an toàn; chứng minh hiểu chính xác cửa sổ race.
- **Regression test:** tạo nhiều worker thử **operation thật**; assert invariant đúng trên phiên bản đã sửa. Có thể dùng start gate để chúng bắt đầu gần nhau, nhưng không chèn barrier giữa các bước của thao tác đã được sửa thành atomic.
- **Stress/integration test:** chạy nhiều lịch hơn trên code thực tế để tăng độ bao phủ; dùng timeout và reporting tốt.
- **Code review/JMM reasoning:** xác nhận tính đúng đắn của cơ chế đồng bộ. Một số lịch test pass không chứng minh mọi lịch đều an toàn.

## 10. Race từ hai thao tác riêng đều thread-safe

Điều phối rất hữu ích khi phát hiện race ở cấp nghiệp vụ dù từng method an toàn.

Giả sử một map thread-safe:

```java
// Snippet minh họa, giả định map là ConcurrentHashMap<Key, Value>.
if (!map.containsKey(key)) {
    map.put(key, createValue());
}
```

`containsKey` và `put` có các bảo đảm thread-safety riêng, nhưng hai thread có thể cùng quan sát key chưa tồn tại rồi cùng gọi `createValue()`. Cả hai có thể gây side effect (ghi file, gọi dịch vụ, phát sự kiện) dù map cuối cùng chỉ giữ một value.

Test điều phối phù hợp: cho hai thread cùng hoàn tất `containsKey` với kết quả false, cho chúng đợi barrier, sau đó thả để gọi `createValue`. Dùng `AtomicInteger` bên trong test để đếm số lần khởi tạo; invariant có thể là “side effect tạo mới chỉ xảy ra một lần”. Nếu yêu cầu chỉ là tính và chèn value khi vắng mặt, `ConcurrentHashMap.computeIfAbsent` có thể giải quyết một phần bài toán theo hợp đồng API. Tuy nhiên side effect bên ngoài cần xem xét retry, thất bại, idempotency và khóa giữa nhiều hệ thống.

Đặt barrier sau `containsKey` **mô phỏng** interleaving; không dùng barrier làm cách sửa race trong code nghiệp vụ. Với invariant nhiều resource, sửa có thể đòi transaction thay vì một operation atomic trên collection.

## 11. Phân biệt test lịch lỗi và test visibility/JMM

Không phải mọi lỗi concurrency đều có thể tái hiện xác định bằng một barrier:

- **Lost update/check–then–act:** có thể điều phối hai worker cùng đọc trạng thái cũ trước khi ghi, nên lịch sai dễ tạo xác định.
- **Visibility:** ví dụ một thread quay vòng đọc field thường trong khi thread khác ghi. Thêm latch/barrier giữa lần ghi và lần đọc có thể tạo happens-before rồi **che đi đúng vấn đề cần test**.
- **Reordering/unsafe publication:** nhiều kết quả phụ thuộc tối ưu JIT, kiến trúc CPU và JMM. Thêm `println`, `sleep`, logging, debugger hoặc khóa thường làm thay đổi thời điểm và kết quả.
- **Deadlock:** có thể dựng test với hai monitor và checkpoint để minh họa chu trình chờ, nhưng không nên để test suite thật treo vĩnh viễn. Dùng deadline, thread daemon/isolation phù hợp và quan sát `ThreadMXBean` khi cần.

Với các câu hỏi tinh vi về JMM như “hai phép đọc có thể thấy cặp giá trị nào?”, “một field không `volatile` có thể đọc stale value ra sao?”, test cần nhiều lịch cùng mô hình đánh giá kết quả hợp lệ, thường gọi là *litmus test*. Công cụ chuyên biệt như **OpenJDK jcstress** giúp kiểm tra nhiều outcome trên các runtime/kiến trúc, nhưng cũng không biến việc không thấy một outcome thành chứng minh nó bất khả thi. Không dùng kết quả của một máy làm định nghĩa JMM.

**Điểm khác nhau quan trọng:** *coordinated test* thường chứng minh một **lịch logic cụ thể đủ làm lộ bug**; *stress/litmus test* khám phá thêm lịch và outcome có thể xuất hiện. Để kết luận code an toàn, cần lập luận atomicity, happens-before và invariant, không chỉ dựa vào thống kê pass.

## 12. Kiểm thử đa giai đoạn với `Phaser` khi nào?

Một race phức tạp có nhiều pha: chuẩn bị dữ liệu → các worker cùng đọc → các worker áp dụng cập nhật → main kiểm tra. `Phaser` có thể điều phối nhiều vòng, cho phép đăng ký/hủy participant động và đợi tiến sang phase tiếp theo. Ví dụ ý tưởng:

```java
Phaser phaser = new Phaser(2);

// Cả hai worker hoàn thành giai đoạn chuẩn bị.
phaser.arriveAndAwaitAdvance();

// Cả hai worker hoàn thành giai đoạn đọc.
phaser.arriveAndAwaitAdvance();

// Sau đó mới sang giai đoạn ghi/cập nhật.
```

Đoạn này là **snippet** (cần import `java.util.concurrent.Phaser`, tạo participant đúng và chạy từ hai worker). `arriveAndAwaitAdvance()` chờ toàn bộ parties; nếu một worker không tới, test có thể kẹt. Với test nhỏ có một checkpoint, `CyclicBarrier` hoặc `CountDownLatch` thường dễ hiểu hơn. Chỉ tăng độ phức tạp khi số pha hoặc số participant thực sự cần.

## 13. Các lỗi thường gặp trong chính test concurrency

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `Thread.sleep(10)` để “chắc” worker kia chạy | Flaky vì scheduler không có hợp đồng thứ tự | Dùng latch/barrier với checkpoint cụ thể |
| Chạy hai task trên pool một worker nhưng đợi barrier hai parties | Task đầu giữ worker, task sau không được chạy | Cấp đủ worker hoặc đổi thiết kế đồng bộ |
| Đặt rendezvous trong `synchronized`/lock cần cho worker khác | Tự gây deadlock | Đặt checkpoint ngoài critical section |
| Chỉ quan sát stdout, không assert invariant | Có lỗi vẫn thông báo pass | Assert giá trị đúng sau `join/get` |
| Assert giá trị ngay sau `start()` | Main đọc quá sớm; còn data race trong test | Đợi worker kết thúc hoặc checkpoint đủ |
| Worker ném exception nhưng main không thu về | Test runner có thể bỏ qua lỗi | `Future.get`/cơ chế gom lỗi và fail test |
| Barrier không timeout | Test có thể treo mãi khi thiếu participant | Timed await, thông báo nguyên nhân rõ |
| Timed get nhưng không xử lý cleanup | Worker lỗi còn sống, làm ô nhiễm test khác | Cancel/interrupt, đóng executor, lifecycle hợp lý |
| Đếm confirmation bằng `int++` không đồng bộ | Chính biến đo cũng mất update | `AtomicInteger`/khóa cho công cụ đo |
| Hai worker thực ra dùng hai instance state riêng | Test không hề thử shared state | Truyền đúng **cùng** instance cho các task |
| Chỉ test phiên bản mô phỏng thuật toán | Production có code khác, lỗi chưa được sửa | Tăng kiểm thử trên operation thật |
| Gán “pass trên CI” là an toàn theo JMM | Một tập lịch hữu hạn không chứng minh mọi lịch | Dùng reasoning về đồng bộ và invariant |
| Thêm barrier để thử visibility | Barrier có thể tạo happens-before, che bug | Dùng litmus/stress phù hợp, review JMM |
| Dùng `assert` mà không bật `-ea` | Assertion có thể không chạy | JUnit assertion hoặc throw `AssertionError` trực tiếp |
| Phụ thuộc thứ tự hai dòng log của worker | Output thay đổi hợp lệ giữa các lần chạy | Gom kết quả, in từ main sau khi `Future.get` |

## 14. Quy trình thiết kế một test điều phối hữu ích

1. **Chọn một invariant cụ thể**: “chỉ một người được đặt một ghế”, “2 increment tạo ra 2”, “không có âm kho”.
2. **Chỉ ra state và operation thật**: object nào chia sẻ giữa threads? Đường đọc, kiểm tra và ghi nằm ở đâu?
3. **Vẽ một lịch thực thi gây sai** trên giấy (A đọc → B đọc → A ghi → B ghi). Nếu không vẽ được, cần điều tra logic trước.
4. **Đặt checkpoint tối thiểu** ngay tại ranh giới quyết định outcome. Dùng barrier nếu cần tất cả worker hoàn thành cùng một pha; latch khi cần main mở cổng.
5. **Cấp đủ participant và worker**; tránh checkpoint nằm trong lock cần cho người đến sau.
6. **Chọn kết quả quan sát an toàn**: dùng `AtomicInteger` cho số lần event, hoặc thu `Future` và assert sau khi hoàn thành. Không để instrumentation tạo thêm lost update.
7. **Đặt deadline và cleanup**: timed `await`, timed `get`, cleanup executor, báo lỗi chi tiết khi barrier broken hoặc timeout.
8. **Tái hiện lỗi với test reproduction**, phân biệt “test cố tình xác nhận bug” với “regression test phải pass khi code đúng”.
9. **Sửa đúng đơn vị atomicity**: đọc–sửa–ghi cùng lock, atomic operation, transaction hoặc tách ownership. Đừng sửa bằng delay hay tăng thread.
10. **Chạy regression và stress trên implementation thật**, review happens-before, visibility và trạng thái shared khác còn sót.
11. **Giữ test độc lập**: không tái sử dụng barrier bị broken, counter hoặc mutable static state giữa các case nếu không reset đúng cách.
12. **Ghi rõ khả năng của test**: nó chứng minh một interleaving cụ thể và expected outcome, không bảo đảm mọi lịch trên mọi CPU/JVM.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao 100.000 lần chạy `count++` trên nhiều thread đều cho kết quả đúng vẫn chưa chứng minh thread-safe?** Vì test chỉ thực hiện một tập lịch hạn chế; không có happens-before bảo vệ phép read–modify–write, nên lost update vẫn có thể xuất hiện dưới interleaving khác.

**2. Muốn cả hai thread đọc `count=0` trước khi ghi, chọn gì?** `CyclicBarrier(2)` đặt sau bước đọc và trước bước ghi, hoặc hai latch để main đợi đủ hai tín hiệu đã đọc rồi mở cổng ghi.

**3. Vì sao không đặt `barrier.await()` trong method `synchronized` mà cả hai thread phải vào?** Thread đầu sở hữu monitor và chờ người thứ hai; người thứ hai chờ chính monitor đó nên không thể tới barrier. Test tự deadlock.

**4. Nếu dùng `volatile int count`, có hết lost update không?** Không. `volatile` bảo đảm visibility/ordering của từng truy cập, không làm chuỗi đọc–cộng–ghi trở thành một operation atomic.

**5. Vì sao cần dùng `AtomicInteger` đếm số lần xác nhận đặt ghế trong test?** Để phép đo không tự mất cập nhật. Nếu dùng `int confirmations++` không đồng bộ, chính số xác nhận có thể bị báo thiếu khiến race nghiệp vụ bị che khuất.

**6. `Future.get(timeout)` ném `TimeoutException` nghĩa là task đã dừng chưa?** Chưa chắc. Chỉ caller hết thời gian chờ; cần hủy/interrupt và quản lý lifecycle task, còn các I/O không nhất thiết đáp ứng interrupt ngay.

**7. Hai lần gọi `ConcurrentHashMap.containsKey` rồi `put` có an toàn cho invariant “chỉ tạo một lần” không?** Không nhất thiết. Các operation riêng thread-safe nhưng check–then–act chưa atomic; dùng API atomic phù hợp hoặc thiết kế tránh side effect lặp.

**8. Có thể dùng barrier để chứng minh một bug visibility do field thiếu `volatile` không?** Cẩn thận: bản thân barrier tạo đồng bộ/happens-before nên có thể che đúng lỗi muốn thử. Với JMM memory-ordering, cần thiết kế litmus test phù hợp.

## 16. Tổng kết áp dụng

Một test race tốt có **ba phần tách bạch**: (1) *invariant* mô tả điều đúng, (2) *interleaving* mô tả một đường đi cụ thể có thể phá điều đúng, và (3) *orchestration* khiến đường đi ấy xảy ra có kiểm soát. `CountDownLatch` và `CyclicBarrier` là công cụ test giúp quan sát hoặc ép các checkpoint; chúng không tự sửa logic production.

Đối với lỗi read–modify–write và check–then–act, điều phối từng bước cho phép tái hiện lost update/double booking gần như ngay lập tức trên một ví dụ chạy được, thay vì lặp may rủi hàng nghìn lần. Sau khi thấy lỗi, phải đưa **toàn bộ invariant** vào cùng cơ chế nguyên tử (`synchronized`, `Lock`, CAS/atomic operation hoặc ownership phù hợp), rồi kiểm tra lại trên operation thực. Race condition có thể được **phát hiện** nhờ test; tính đúng đắn lâu dài cần được **giải thích** bằng hợp đồng đồng bộ và Java Memory Model.