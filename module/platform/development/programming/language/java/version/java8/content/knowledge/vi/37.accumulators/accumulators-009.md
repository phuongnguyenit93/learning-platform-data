# Không dùng bộ đếm thống kê thay cho điều kiện kiểm soát chính xác

**Chủ đề cha:** Biến tích lũy trong lập trình đồng thời Java. **Vấn đề trọng tâm:** Vì sao `LongAdder`, `DoubleAdder` và `LongAccumulator` phù hợp để thu thập thống kê dưới tranh chấp nhưng **không được dùng kết quả tổng hợp đang thay đổi làm điều kiện quyết định chính xác** như giới hạn quota, số ghế còn lại, tồn kho, số phiên kết nối tối đa, số lần được cấp quyền hoặc kiểm tra điều kiện chỉ cho một thread đi tiếp.

**Phạm vi phiên bản:** Các lớp tích lũy trong `java.util.concurrent.atomic`, `AtomicLong`, `AtomicInteger`, `AtomicReference`, `Semaphore`, `CountDownLatch` và `Future` đều còn là API Java SE hiện hành. Những ví dụ có cú pháp hoàn chỉnh dùng **Java 17+**, với lệnh biên dịch/chạy và stdout xác định. Một vài code sample dùng `record` của Java 17; không khẳng định `record` thuộc Java 8.

> **Tư tưởng:** Bộ đếm thống kê cho biết **đã quan sát bao nhiêu**; cơ chế điều phối quyết định **có được phép thực hiện hành động kế tiếp hay không**. Với thống kê, một phép `sum()` không đại diện cho snapshot nguyên tử trong lúc nhiều thread cập nhật có thể chấp nhận được. Với quyết định "không cho vượt quá 100", kiểm tra điều kiện và thay đổi trạng thái phải thuộc **cùng một thao tác đồng bộ nguyên tử**. Ngay cả khi đọc bằng `AtomicLong.get()` là nguyên tử, chuỗi `if (count.get() < limit) count.incrementAndGet()` vẫn là *check-then-act race*.

## 1. Hai loại yêu cầu tưởng giống nhau nhưng hợp đồng khác nhau

Ví dụ một ứng dụng có hai mục tiêu:

1. **Thống kê:** "Đã nhận bao nhiêu request trong khoảng thời gian này?" Cần tăng nhanh dưới tải cao và xuất báo cáo định kỳ; khi đọc trong lúc ghi, một số cập nhật mới nhất có thể chưa xuất hiện trong kết quả tổng hợp.
2. **Điều kiện kiểm soát:** "Chỉ 100 request đầu tiên được cấp một suất; request thứ 101 phải từ chối." **Không được cấp 101 suất**, kể cả hai thread đồng thời nhìn thấy 99.

Hai yêu cầu dùng hai ngữ nghĩa khác nhau:

| Tình huống | Dữ liệu đang đọc | Tính đúng đắn cần đạt | Công cụ phù hợp |
| --- | --- | --- | --- |
| Đếm request để hiển thị dashboard | Thống kê quan sát | Tổng sau khi yên cập nhật phải đúng; đọc trực tiếp trong lúc cập nhật có thể không là snapshot | `LongAdder` |
| Tổng hợp lượng dữ liệu đo bằng số thực | Thống kê quan sát | Chấp nhận sai số làm tròn và thứ tự cộng không cố định | `DoubleAdder` |
| Đo max latency hoặc min sample | Giá trị tích lũy | Đọc đồng thời có thể không là snapshot, nhưng kết quả cuối sau khi dừng cập nhật đúng theo hàm tích lũy | `LongAccumulator` / `DoubleAccumulator` |
| Cấp tối đa N lượt vĩnh viễn | State kiểm soát | Mỗi lượt chấp thuận và tăng quota phải có một điểm nguyên tử | `AtomicInteger/AtomicLong` CAS hoặc atomic update |
| Chỉ cho N tác vụ **đồng thời** | Giấy phép đang sử dụng | Không cho số tác vụ giữ permit vượt N | `Semaphore`, release trong `finally` |
| Đặt tối đa N món hàng theo một SKU | Trạng thái có bất biến | Không oversell, cập nhật cùng điều kiện với phép trừ hàng | CAS trên immutable state hoặc `ConcurrentHashMap.compute` |
| Giới hạn toàn hệ thống nhiều server | State dùng chung | Không được vượt quota dù nhiều process cùng xử lý | Transaction/cơ chế nguyên tử tại shared store |
| Hiển thị biểu đồ lỗi/thành công | Metrics độc lập | Có thể quan sát các counter ở thời điểm khác nhau | `LongAdder` thích hợp nếu không dùng chúng để cấp quyền |

### 1.1. Phân biệt "chính xác sau khi dừng cập nhật" với "snapshot tức thời"

`LongAdder.sum()` trả tổng chính xác khi **không có cập nhật đồng thời**; ví dụ sau `Future.get()` chờ tất cả worker hoàn tất và không có thread khác tăng/reset, kết quả đúng với tổng các lần `increment()` đã diễn ra. Điều đó **không mâu thuẫn** với cảnh báo Javadoc: khi `sum()` chạy **đồng thời** với các update, nó **không tạo atomic snapshot**, và một số update xảy ra trong lúc tổng hợp có thể chưa được phản ánh.

Dùng `LongAdder` để đo số sự kiện **không làm mất các lần increment** chỉ vì nhiều thread cùng tăng nó, nhưng lời đọc `sum` đang diễn ra không đủ làm ranh giới quyết định kiểu "còn đúng một suất".

### 1.2. Tính nguyên tử của phép đọc không đủ

So sánh:

```java
if (accepted.get() < limit) {
    accepted.incrementAndGet();
}
```

Đây là **phản ví dụ đặt trong một phương thức** với `accepted` kiểu `AtomicLong` và `limit` là một số dương. `get` nguyên tử và `incrementAndGet` nguyên tử **riêng**, nhưng toàn bộ **kiểm tra rồi tăng không nguyên tử**. Hai thread có thể cùng đọc 99, cả hai cùng tăng, kết quả 101. Thay LongAdder bằng AtomicLong **chỉ đúng khi đổi cả thuật toán**, không phải đổi tên class.

## 2. LongAdder là gì và vì sao hợp với thống kê?

`LongAdder` duy trì một tổng `long` qua một hoặc nhiều biến nội bộ. Khi nhiều thread tranh chấp, implementation có thể phân tán cập nhật để giảm contention. Theo Javadoc, nó thường phù hợp hơn `AtomicLong` cho thống kê/counter được cập nhật rất thường xuyên, chứ **không** cho kiểm soát đồng bộ ở mức chi tiết.

Các API phổ biến:

```java
LongAdder requests = new LongAdder();

requests.increment(); // +1
requests.add(5);      // +5
requests.decrement(); // -1

long observed = requests.sum();
```

Đây là **mã trong phương thức**, import `java.util.concurrent.atomic.LongAdder`. Nếu không có cập nhật đồng thời, `observed` sau ba phép trên là 5. `increment()` và `decrement()` là viết gọn của `add(1)` và `add(-1)`.

**Javadoc nêu rõ:** Kết quả `sum()` **không phải một atomic snapshot**. Nếu thread khác đang tăng/giảm, các thay đổi xảy ra khi phép tính tổng đang thực hiện có thể chưa được đưa vào kết quả.

### 2.1. `LongAdder.sum()` không phải một phiên bản mạnh hơn của AtomicLong.get()

`AtomicLong.get()` đọc **một biến nguyên tử**, có ràng buộc bộ nhớ/linearization của một phép đọc atomic theo hợp đồng. `LongAdder.sum()` phải kết hợp các phần đóng góp từ cấu trúc tích lũy, không có điểm snapshot nguyên tử chung bảo đảm mọi cập nhật thấy cùng một thời điểm.

Vì thế:

- `LongAdder`: rất tốt cho số request, số lỗi, số byte, sự kiện/metric "hot".
- `AtomicLong`: phù hợp hơn khi **phép đọc, điều kiện và cập nhật phải phối hợp** thông qua CAS hoặc các phương thức update nguyên tử.
- `Semaphore`: phù hợp khi điều kiện là số **tác vụ/connection đang chiếm chỗ**, có vòng đời lấy–trả permit.
- Một phép kiểm tra nhiều counter/keys: cả `AtomicLong` và `Semaphore` riêng lẻ chưa đủ cho **giao dịch xuyên nhiều biến**.

Không có kết luận tốc độ tuyệt đối `LongAdder` luôn nhanh hơn trên mọi tải. Dưới tranh chấp ít, hiệu quả có thể gần nhau; dùng benchmark/profiler thực tế để quyết định cấu trúc.

### 2.2. `LongAdder.longValue()` có chính xác hơn `sum()`?

Không. Javadoc mô tả `longValue()` tương đương `sum()`. Ép LongAdder sang `Number` và gọi `longValue()` **không biến tổng thành atomic snapshot**.

### 2.3. Vấn đề với `sumThenReset()` và `reset()`

`LongAdder.reset()` và `sumThenReset()` hữu ích cho một số thống kê ở **thời điểm quiescent**, tức biết chắc không thread nào đang cập nhật. Khi update diễn ra đồng thời, reset và sum-then-reset có thể làm kết quả thống kê bị phân phối/lỡ nhịp theo cách không phù hợp với kế toán chính xác.

Do vậy không dùng:

```java
if (adder.sumThenReset() < quota) {
    // Cấp quyền sử dụng tài nguyên...
}
```

Đây là **phản ví dụ**, không phải bộ đếm quota an toàn. Việc reset các ô tích lũy không phải một transaction "đọc quota và cấp suất" với tất cả thread khác.

## 3. Một lỗi có thể tái hiện: Hai thread cùng đọc 0 rồi cùng được cấp suất

Giả sử yêu cầu nghiệp vụ: **limit = 1**. Người lập trình viết:

```java
if (used.sum() < 1) {
    used.increment();
    // Cho phép thực hiện request.
}
```

Đây là **mã sai để minh họa**. Hai thread có thể cùng quan sát tổng bằng 0, cả hai quyết định đi tiếp, rồi mỗi thread tăng một đơn vị. Tổng thành 2 dù giới hạn là 1.

**Chú ý:** Sai không chỉ do `LongAdder.sum` không phải snapshot nguyên tử. **Ngay cả `AtomicLong.get` rồi `incrementAndGet`** cũng có cùng race nếu kiểm tra và tăng nằm ở hai thao tác.

### 3.1. Java 17+ runnable: Cố tình tạo race, không phụ thuộc Thread.sleep

Tạo file **`NaiveLimitRaceDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.LongAdder;

public class NaiveLimitRaceDemo {
    static boolean incorrectlyAdmit(
            LongAdder used,
            int limit,
            CountDownLatch bothRead,
            CountDownLatch release
    ) throws InterruptedException {
        long seen = used.sum();
        bothRead.countDown();
        release.await();

        if (seen >= limit) {
            return false;
        }
        used.increment();
        return true;
    }

    public static void main(String[] args) throws Exception {
        LongAdder used = new LongAdder();
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Boolean> first = pool.submit(
                    () -> incorrectlyAdmit(
                            used, 1, bothRead, release));
            Future<Boolean> second = pool.submit(
                    () -> incorrectlyAdmit(
                            used, 1, bothRead, release));

            bothRead.await();
            release.countDown();

            int admitted = (first.get() ? 1 : 0)
                    + (second.get() ? 1 : 0);

            System.out.println("Limit: 1");
            System.out.println("Admitted: " + admitted);
            System.out.println("Count: " + used.sum());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 NaiveLimitRaceDemo.java
java NaiveLimitRaceDemo
```

**Stdout (lỗi được tái hiện có chủ đích):**

```text
Limit: 1
Admitted: 2
Count: 2
```

### 3.2. Vì sao test này xác định?

1. Hai worker đều được gửi vào pool có **hai thread**.
2. Mỗi worker **đọc** `used.sum()` trước, sau đó giảm `bothRead`.
3. Cả hai worker phải **chờ `release.await()`** trước khi tăng. Thread main chỉ mở latch sau khi **cả hai đã đọc xong**.
4. Vì chưa ai tăng trước khi latch mở, cả hai cùng giữ bản ghi cục bộ `seen == 0`.
5. Cả hai đều đáp ứng `seen < limit` và cùng `increment()`. Sau khi cả hai `Future.get()` hoàn tất, `sum() == 2`.
6. Test không suy đoán lịch lên thread, cũng không dựa vào `Thread.sleep`. Nó chứng minh một **interleaving hợp lệ làm sai yêu cầu**, nên thuật toán check-then-act không an toàn.

Để test không bị hiểu nhầm, tên phương thức là `incorrectlyAdmit` và output báo rõ giới hạn bị vi phạm. **Không dùng logic đó trong production.**

## 4. AtomicLong + compareAndSet: Chấp nhận và cập nhật tại một điểm nguyên tử

Khi cần cấp tối đa N lượt **tích lũy trong một tiến trình** mà không có phép giải phóng quota, `AtomicLong` với vòng **compare-and-set (CAS)** diễn đạt điều kiện và cập nhật cùng một thao tác:

```java
static boolean tryAccept(AtomicLong accepted, long limit) {
    if (limit <= 0) {
        throw new IllegalArgumentException(
                "limit must be positive");
    }

    for (;;) {
        long current = accepted.get();

        if (current >= limit) {
            return false;
        }

        if (accepted.compareAndSet(current, current + 1)) {
            return true;
        }

        // Thread khác đã thay số đếm: đọc lại và thử tiếp.
    }
}
```

Đây là **method trong một class**, cần import `java.util.concurrent.atomic.AtomicLong`. Thông số `accepted` phải bắt đầu từ giá trị **không âm** và mọi update của bộ đếm quota phải tuân thủ cùng một giao thức; `limit` là số dương hợp lệ và được giữ cố định trong quy trình này.

### 4.1. Chính xác điều gì là nguyên tử?

`compareAndSet(expected, update)` chỉ thay giá trị nếu giá trị hiện tại vẫn bằng expected. Với limit = 1:

- Thread A và B cùng đọc 0.
- A CAS(0,1) thành công: **được cấp quyền**.
- B CAS(0,1) thất bại vì state đã là 1, **không** cấp quyền.
- B đọc lại 1, thấy đã đạt limit, trả false.

Mỗi lời gọi chỉ trả true **sau khi CAS thành công**. Việc quyết định có suất và tăng counter đi kèm nhau. Hai thread không thể cùng CAS thành công từ **một giá trị cũ duy nhất**.

### 4.2. Vòng CAS có thể thử lại, đừng làm side effect trong vòng

Under contention, một lần `compareAndSet` có thể thất bại. Điều này không phải lỗi hệ thống; đó là tín hiệu đọc lại và quyết định từ state mới. **Không gửi email, ghi DB, trừ tiền, sinh đơn hàng** trước khi biết CAS đã thành công. Nếu làm side effect trên mỗi lần loop, retries có thể khiến hành động bị lặp.

Sau khi CAS thành công, nếu hành động nghiệp vụ có thể thất bại (ví dụ thanh toán/ghi DB), cần có chính sách bù, timeout và idempotency. AtomicLong chỉ bảo vệ counter trong bộ nhớ, **không** tạo transaction với các tác dụng bên ngoài.

### 4.3. Cần xét overflow

`AtomicLong.incrementAndGet()` và cộng số `long` thông thường **không tự từ chối overflow**. Trong mẫu trên, nếu `limit` là một số dương không vượt `Long.MAX_VALUE`, current không âm và nhánh `current >= limit` từ chối trước khi cộng ở giới hạn, phép `current + 1` không vượt Long.MAX_VALUE. Nhưng nếu các thread khác có thể sửa counter về số âm, reset không phối hợp hoặc giới hạn thay đổi tùy lúc, bất biến này không còn đúng.

Hãy validate giá trị khởi tạo, limit và **tập API có quyền sửa cùng counter**. Dùng `Math.addExact` khi nghiệp vụ cần phát hiện overflow cho một phép cộng tổng quát ngoài mẫu quota đơn vị này.

## 5. Java 17+ runnable: 4.000 yêu cầu tranh 1.000 suất

Tạo file **`AtomicQuotaDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

public class AtomicQuotaDemo {
    static boolean tryAccept(AtomicLong accepted, long limit) {
        if (limit <= 0) {
            throw new IllegalArgumentException(
                    "limit must be positive");
        }

        for (;;) {
            long current = accepted.get();
            if (current >= limit) {
                return false;
            }
            if (accepted.compareAndSet(current, current + 1)) {
                return true;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        final int workers = 8;
        final int requestsPerWorker = 500;
        final long limit = 1_000;

        AtomicLong accepted = new AtomicLong();
        LongAdder attempts = new LongAdder();
        LongAdder rejected = new LongAdder();

        ExecutorService pool =
                Executors.newFixedThreadPool(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int w = 0; w < workers; w++) {
                futures.add(pool.submit(() -> {
                    start.await();

                    for (int i = 0; i < requestsPerWorker; i++) {
                        attempts.increment();

                        if (!tryAccept(accepted, limit)) {
                            rejected.increment();
                        }
                    }
                    return null;
                }));
            }

            start.countDown();
            for (Future<?> task : futures) {
                task.get();
            }

            System.out.println("Attempted: " + attempts.sum());
            System.out.println("Accepted: " + accepted.get());
            System.out.println("Rejected: " + rejected.sum());
            System.out.println("Limit respected: "
                    + (accepted.get() <= limit));
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac --release 17 AtomicQuotaDemo.java
java AtomicQuotaDemo
```

**Stdout:**

```text
Attempted: 4000
Accepted: 1000
Rejected: 3000
Limit respected: true
```

**Đọc kết quả đúng:**

- `accepted` là **biến quyết định**; `compareAndSet` bảo đảm mỗi lần nhận suất tăng đúng 1.
- `attempts` và `rejected` là **bộ đếm thống kê**; chúng không được tham gia điều kiện cấp suất.
- 8 × 500 = 4.000 lần thử. Vì mỗi lần thử chỉ được chấp nhận khi chưa đủ 1.000, kết quả 1.000 được chấp nhận, 3.000 bị từ chối.
- Main chỉ gọi `attempts.sum()` và `rejected.sum()` sau `Future.get()` cho mọi worker, khi không còn cập nhật, nên số liệu cuối là chính xác.
- `Future.get` đưa exception từ worker về main; nếu worker lỗi, chương trình không tự in một báo cáo thành công giả.
- `shutdownNow` trong `finally` chỉ phục vụ dọn pool demo; trong ứng dụng thật chọn `shutdown`, `awaitTermination` và chính sách ngừng nhận request có tổ chức.

**Giới hạn:** Mẫu này không tự áp cho cluster gồm nhiều JVM hoặc một bộ đếm bị reset cạnh tranh với các request đang chạy. Mọi thread cấp quyền phải chia sẻ **cùng một AtomicLong trong cùng tiến trình**, không ghi đè state qua con đường khác.

## 6. `getAndUpdate`: Có thể viết ngắn hơn CAS loop

`AtomicInteger.getAndUpdate` / `AtomicLong.getAndUpdate` nhận một hàm cập nhật và trả **giá trị cũ** tại điểm cập nhật nguyên tử. Với quota:

```java
static boolean tryAccept(AtomicInteger used, int limit) {
    int previous = used.getAndUpdate(
            value -> value < limit ? value + 1 : value);
    return previous < limit;
}
```

Đây là **method minh họa trong class**, import `AtomicInteger`. Nếu used=2, limit=3: hàm đổi 2 thành 3 và trả previous=2, nên quyết định true. Nếu used=3: hàm giữ 3, trả previous=3, nên false.

**Tại sao trả previous là quan trọng?** `updateAndGet` trả **giá trị mới**. Với phép cập nhật bão hòa tại limit, kết quả mới bằng limit trong **cả** trường hợp vừa nhận suất cuối và trường hợp bị từ chối — không đủ để suy ra chính xác hành động vừa được cấp hay không. `getAndUpdate` trả giá trị trước đó, phân biệt hai tình huống.

### 6.1. Callback của getAndUpdate phải thuần

Javadoc nói rõ hàm update có thể được **gọi lại** khi CAS nội bộ thất bại vì cạnh tranh. Do đó callback:

```java
value -> value < limit ? value + 1 : value
```

phải không có side effect. Không tăng metric, ghi DB hoặc gửi thông điệp **bên trong lambda** theo giả định nó chạy đúng một lần. Nếu cần ghi thống kê "được chấp nhận", hãy làm **sau khi phương thức trả** và quyết định true, hoặc đưa event vào transaction nghiệp vụ được kiểm soát.

### 6.2. Java 17+ runnable: getAndUpdate để quyết định

Tạo file **`AtomicUpdateDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;

public class AtomicUpdateDemo {
    static boolean tryAccept(AtomicInteger used, int limit) {
        int previous = used.getAndUpdate(
                value -> value < limit ? value + 1 : value);
        return previous < limit;
    }

    public static void main(String[] args) throws Exception {
        final int limit = 3;
        AtomicInteger used = new AtomicInteger();
        LongAdder acceptedStats = new LongAdder();

        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int i = 0; i < 8; i++) {
                tasks.add(pool.submit(() -> {
                    start.await();

                    if (tryAccept(used, limit)) {
                        acceptedStats.increment();
                    }
                    return null;
                }));
            }

            start.countDown();
            for (Future<?> task : tasks) {
                task.get();
            }

            System.out.println("Accepted: "
                    + acceptedStats.sum());
            System.out.println("Used: " + used.get());
            System.out.println("Rejected: "
                    + (8 - acceptedStats.sum()));
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac --release 17 AtomicUpdateDemo.java
java AtomicUpdateDemo
```

**Stdout:**

```text
Accepted: 3
Used: 3
Rejected: 5
```

Lúc quyết định, `used` là state nguyên tử của quota; `acceptedStats` chỉ là dữ liệu giám sát, được đọc sau khi mọi request hoàn tất. Callback bão hòa khi đủ giới hạn và trả về **giá trị cũ**, tránh cấp suất quá hạn mức.

**Lưu ý API công khai:** Trong method production nên validate `limit > 0` và trạng thái khởi tạo `used >= 0`; demo dùng hằng `limit = 3` và counter mới tạo 0. Nếu các phần khác có thể `set`/`decrement` cùng counter không theo một giao thức thống nhất, chứng minh quota có thể bị phá vỡ dù method này đúng độc lập.

## 7. Kiểm soát số việc đang chạy: Semaphore phù hợp hơn bộ đếm sự kiện

"Cho phép tối đa ba task **đang thực thi đồng thời**" khác "chỉ cấp ba lượt **trong cả đời ứng dụng**".

Một `AtomicLong` tăng mãi phù hợp với quota tích lũy. Nhưng với **tài nguyên hữu hạn có thể trả lại** (connection, slot xử lý, tài nguyên mở file), `Semaphore` diễn đạt đúng ý nghĩa lấy một permit trước khi vào và trả permit sau khi rời.

```java
Semaphore permits = new Semaphore(3);

permits.acquire();
try {
    performWork();
} finally {
    permits.release();
}
```

Đây là **mẫu minh họa trong một phương thức**, chưa khai báo `performWork`; import `java.util.concurrent.Semaphore`. `acquire()` có thể chặn tới khi permit còn trống. `tryAcquire()` có thể từ chối ngay; overload có timeout có thể đợi có hạn.

**Không sử dụng `LongAdder.sum() < 3` để quyết định vào khu vực hạn chế rồi mới tăng/giảm counter**. Hai thread có thể cùng thấy còn một suất như lỗi quota ở ví dụ trước. Ngoài ra, khi xử lý exception, quên giảm counter dễ làm state bị kẹt; `Semaphore` với `finally` làm ranh giới ownership của permit rõ ràng hơn.

### 7.1. Vì sao phải release trong finally?

Nếu một task chiếm permit, sau đó HTTP call/JDBC query ném exception và không release, số permit còn lại sẽ bị giảm vĩnh viễn cho tới khi ứng dụng reset. Cũng phải tránh `release()` nếu **chưa acquire thành công**, vì Semaphore không theo dõi "chủ sở hữu" của permit theo từng thread; release thừa làm số permit tăng quá giới hạn dự định.

Chuẩn:

```java
boolean acquired = permits.tryAcquire();

if (!acquired) {
    // Từ chối hoặc trả quá tải.
} else {
    try {
        performWork();
    } finally {
        permits.release();
    }
}
```

Đây là đoạn minh họa. Nếu `acquire()` bị `InterruptedException` trước khi lấy permit, không được release như thể đã lấy.

### 7.2. Semaphore không phải số lượng giao dịch đã được cấp trong lịch sử

Permit được **trả lại** khi task kết thúc, nên Semaphore đáp ứng limit đồng thời chứ không giữ quota tổng vĩnh viễn. Khi cần giới hạn "tối đa 100 đơn hàng trong chiến dịch", hãy dùng bộ đếm/cơ chế lưu số đã cấp chính xác, **không** dùng Semaphore 100 permits rồi release sau mỗi đơn hàng.

Khi cần giới hạn cả **số đang chạy** và **tổng quota**, có thể cần cả Semaphore và một bộ đếm quota/transaction. Hai cơ chế cần được phối hợp với chính sách hoàn trả rõ: nếu hết quota thì release permit; nếu đã giữ quota nhưng tác vụ thất bại thì có hoàn trả lượt không, hoàn trả thế nào để không làm mất nhất quán?

## 8. Java 17+ runnable: Tối đa ba tác vụ cùng chiếm permit

Tạo file **`SemaphoreCapacityDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreCapacityDemo {
    public static void main(String[] args) throws Exception {
        final int limit = 3;

        Semaphore permits = new Semaphore(limit);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maxActive = new AtomicInteger();
        AtomicInteger completed = new AtomicInteger();

        CountDownLatch reachedLimit = new CountDownLatch(limit);
        CountDownLatch release = new CountDownLatch(1);

        ExecutorService pool = Executors.newFixedThreadPool(8);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < 8; i++) {
                futures.add(pool.submit(() -> {
                    permits.acquire();

                    try {
                        int now = active.incrementAndGet();
                        maxActive.accumulateAndGet(now, Math::max);
                        reachedLimit.countDown();

                        // Giữ ba task đầu ở bên trong vùng bảo vệ.
                        release.await();
                        completed.incrementAndGet();
                    } finally {
                        active.decrementAndGet();
                        permits.release();
                    }
                    return null;
                }));
            }

            reachedLimit.await();
            System.out.println("Active before release: "
                    + active.get());
            release.countDown();

            for (Future<?> future : futures) {
                future.get();
            }

            System.out.println("Peak active: "
                    + maxActive.get());
            System.out.println("Completed: "
                    + completed.get());
            System.out.println("Active after finish: "
                    + active.get());
            System.out.println("Permits restored: "
                    + permits.availablePermits());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac --release 17 SemaphoreCapacityDemo.java
java SemaphoreCapacityDemo
```

**Stdout:**

```text
Active before release: 3
Peak active: 3
Completed: 8
Active after finish: 0
Permits restored: 3
```

**Tính xác định:**

1. Pool có tám worker nhưng Semaphore chỉ cấp **ba permit**.
2. Ba task đầu tăng `active`, cập nhật `maxActive` và đợi latch `release`, khiến phép in "Active before release" chắc chắn là 3.
3. Các task còn lại phải đợi đến khi permit được trả; ở mọi thời điểm `maxActive <= 3`.
4. `finally` giảm biến đo `active` rồi trả permit. Sau `Future.get()` của tất cả worker, số task đã hoàn thành là 8, active=0, số permit phục hồi thành 3.
5. `active` và `maxActive` là **biến quan sát để kiểm chứng**, không phải thứ cho phép task đi qua rào kiểm soát. **Semaphore mới là cơ chế kiểm soát.**
6. Nếu code thật dùng `tryAcquire`, có thể trả kết quả quá tải thay vì đợi. Nếu dùng permit fairness, hãy đọc contract của các overload `tryAcquire`: không phải overload nào cũng tôn trọng chính sách công bằng theo cùng cách.

Đừng biến test này thành benchmark hiệu năng của Semaphore. Nó chỉ kiểm tra **bất biến số concurrent owners không vượt limit** trong một kịch bản được kiểm soát.

## 9. LongAccumulator, DoubleAdder và DoubleAccumulator: Cũng thuộc phía thống kê

Nhóm "Biến tích lũy" không chỉ có `LongAdder`:

| Loại | Phép cập nhật | Cách đọc | Phạm vi dùng phù hợp |
| --- | --- | --- | --- |
| `LongAdder` | `add` / `increment` | `sum()` | Counter/statistics nhiều thread |
| `DoubleAdder` | `add(double)` | `sum()` | Thống kê số thực, tổng đo lường |
| `LongAccumulator` | `accumulate(long)` với hàm gộp | `get()` | Max/min/aggregate dạng long |
| `DoubleAccumulator` | `accumulate(double)` với hàm gộp | `get()` | Max/min/aggregate số thực |
| `AtomicLong` | `compareAndSet`, `getAndUpdate`, `addAndGet` | `get()` | Cần thao tác nguyên tử trên **một state** |
| `AtomicReference<T>` | `compareAndSet` của reference | `get()` | Điều chỉnh value bất biến chứa nhiều field |
| `Semaphore` | `acquire/tryAcquire/release` | `availablePermits()` chủ yếu quan sát | Kiểm soát số suất **đang được giữ** |

### 9.1. LongAccumulator.get cũng không phải snapshot nguyên tử

`LongAccumulator` tích lũy theo hàm được cấu hình, ví dụ:

```java
LongAccumulator peak =
        new LongAccumulator(Long::max, Long.MIN_VALUE);

peak.accumulate(5);
peak.accumulate(8);
peak.accumulate(2);

long max = peak.get(); // 8, khi không có update đồng thời
```

Đây là đoạn trong phương thức, import `java.util.concurrent.atomic.LongAccumulator`. `get()` không là atomic snapshot trong lúc nhiều thread gọi `accumulate()`. Nếu muốn áp dụng quy tắc "chỉ nhận giá trị khi max chưa vượt ngưỡng", đọc `get` rồi act cũng không an toàn.

Javadoc yêu cầu hàm accumulator **không có side effect** vì có thể được áp dụng lại dưới tranh chấp; để kết quả dự đoán được khi thứ tự tích lũy khác nhau, nên dùng hàm **kết hợp và giao hoán**, với identity phù hợp. `Long::max` có identity `Long.MIN_VALUE`.

### 9.2. DoubleAdder và độ chính xác số học

`DoubleAdder.sum()` cũng không phải snapshot nguyên tử trong lúc có cập nhật. Ngoài ra, phép cộng floating point có thể phụ thuộc vào thứ tự cộng do rounding theo IEEE 754. Khi thay đổi thứ tự thread, kết quả double của tổng đo có thể khác một lượng rất nhỏ.

**Không dùng DoubleAdder làm sổ tiền hoặc quota tài chính chính xác.** Với giá trị tiền cần chính xác, có thể dùng đơn vị nguyên nhỏ nhất trong `long` với guard overflow, `BigDecimal` với đồng bộ/transaction phù hợp, hoặc cơ chế DB transaction theo domain. Bản thân `BigDecimal` bất biến **không làm read-check-update trên shared reference trở thành nguyên tử**; vẫn cần CAS/lock hoặc hệ thống transaction thích hợp.

### 9.3. Reset thống kê trong lúc cập nhật

`LongAccumulator.reset` và `getThenReset` có giới hạn tương tự `LongAdder.reset` và `sumThenReset`: các lần update đồng thời có thể khiến kết quả không phải một ranh giới sự kiện chính xác. Dùng reset khi biết không có writer đang chạy, hoặc dùng mô hình metric theo cửa sổ thời gian/epoch phù hợp.

**Kết luận của nhóm:** Chúng giúp **giảm contention khi tích lũy thống kê**, không phải primitive admission dành cho quyết định "chỉ một request tiếp theo được phép".

## 10. Java 17+ runnable: Đo LongAdder, DoubleAdder và LongAccumulator

Tạo file **`TelemetryAccumulatorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.DoubleAdder;
import java.util.concurrent.atomic.LongAccumulator;
import java.util.concurrent.atomic.LongAdder;

public class TelemetryAccumulatorDemo {
    public static void main(String[] args) throws Exception {
        LongAdder requests = new LongAdder();
        DoubleAdder latency = new DoubleAdder();
        LongAccumulator peak =
                new LongAccumulator(Long::max, Long.MIN_VALUE);

        ExecutorService pool = Executors.newFixedThreadPool(4);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int t = 0; t < 4; t++) {
                futures.add(pool.submit(() -> {
                    for (int i = 0; i < 2_500; i++) {
                        requests.increment();
                        latency.add(0.5);
                        peak.accumulate(i % 17);
                    }
                    return null;
                }));
            }

            for (Future<?> future : futures) {
                future.get();
            }

            System.out.println("Requests: "
                    + requests.sum());
            System.out.println("Total latency units: "
                    + latency.sum());
            System.out.println("Peak sample: "
                    + peak.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac --release 17 TelemetryAccumulatorDemo.java
java TelemetryAccumulatorDemo
```

**Stdout:**

```text
Requests: 10000
Total latency units: 5000.0
Peak sample: 16
```

**Đọc kết quả:**

- Có 4 × 2.500 = 10.000 sự kiện; sau khi `Future.get` hoàn tất, `LongAdder.sum()` cho 10.000.
- Cộng 0.5 đúng 10.000 lần cho 5.000.0; số 0.5 biểu diễn chính xác ở dạng binary floating point nên không tạo khác biệt rounding trong dữ liệu demo này.
- `i % 17` lấy các giá trị từ 0 đến 16, nên giá trị lớn nhất là 16.
- Thứ tự lên lịch các cập nhật **không được dựa vào** trong stdout; phép tính cuối được thực hiện sau khi cả bốn worker hoàn tất.
- Đừng suy ra từ demo rằng `DoubleAdder` bảo đảm mọi phép cộng số thực có kết quả hoàn toàn độc lập với thứ tự chạy, hay rằng `get()` có thể dùng ngay trong khi nhiều thread đang cập nhật để làm admission decision.

Trong ứng dụng dashboard, bạn có thể quan sát `sum` theo chu kỳ và gắn nhãn metrics là số liệu được **lấy mẫu**, không là transaction. Nếu sản phẩm phải thanh toán chính xác cho từng request, hãy dùng state/transaction riêng.

## 11. State gồm nhiều field: Một AtomicLong không đủ nếu điều kiện liên quan cả hai

Một quota đôi khi có nhiều biến liên quan: `available` và `reserved`, số suất còn lại và đã giữ. Nếu dùng hai `AtomicInteger` và cập nhật từng cái một:

```java
if (available.get() > 0) {
    available.decrementAndGet();
    reserved.incrementAndGet();
}
```

Đây là **phản ví dụ**. Không chỉ check-then-act của available có race: hai phép update **trên hai AtomicInteger riêng** còn không tạo transaction giữ bất biến `available + reserved == initialTotal` tại mọi điểm đọc.

Một cách đúng cho **state một tiến trình** là lưu state **bất biến** vào một `AtomicReference` rồi CAS **toàn bộ reference**:

```java
record Stock(int available, int reserved) {}

AtomicReference<Stock> state =
        new AtomicReference<>(new Stock(3, 0));
```

Mỗi lần reserve, đọc old Stock, tính Stock mới, CAS reference. Nếu một thread khác thắng trước thì lặp từ state mới. Như vậy, `available` và `reserved` được **công bố cùng lúc** trong một value immutable.

### 11.1. Không mutate object cũ

`AtomicReference<MutableStock>` kết hợp với thao tác `old.available--` **không đủ**. CAS chỉ so/thay **reference**, không bao vệ những field bên trong object bị sửa ngoài protocol.

Dùng `record Stock` với các thành phần primitive (bất biến), tạo `new Stock(...)` trong mỗi lần tính, không sửa object cũ. Nếu value chứa list/map mutable, cần sao chép phòng vệ hoặc dùng cấu trúc state bất biến thực sự.

## 12. Java 17+: Giữ bất biến available + reserved bằng AtomicReference

Tạo file **`AtomicStateDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.LongAdder;

public class AtomicStateDemo {
    record Stock(int available, int reserved) {}

    static boolean reserve(AtomicReference<Stock> slot) {
        for (;;) {
            Stock old = slot.get();

            if (old.available() == 0) {
                return false;
            }

            Stock next = new Stock(
                    old.available() - 1,
                    old.reserved() + 1);

            if (slot.compareAndSet(old, next)) {
                return true;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicReference<Stock> slot =
                new AtomicReference<>(new Stock(3, 0));
        LongAdder successful = new LongAdder();

        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> tasks = new ArrayList<>();

        try {
            for (int i = 0; i < 8; i++) {
                tasks.add(pool.submit(() -> {
                    start.await();
                    if (reserve(slot)) {
                        successful.increment();
                    }
                    return null;
                }));
            }

            start.countDown();
            for (Future<?> task : tasks) {
                task.get();
            }

            Stock end = slot.get();
            System.out.println("Successful reservations: "
                    + successful.sum());
            System.out.println("Available: "
                    + end.available());
            System.out.println("Reserved: "
                    + end.reserved());
            System.out.println("Invariant: "
                    + (end.available() + end.reserved() == 3));
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
javac --release 17 AtomicStateDemo.java
java AtomicStateDemo
```

**Stdout:**

```text
Successful reservations: 3
Available: 0
Reserved: 3
Invariant: true
```

**Giải thích:** Có tám thread tranh ba suất. Chỉ ba CAS thành công thay một state có `available > 0`; state cuối luôn giữ `available=0`, `reserved=3`. Thống kê `successful` được tăng **sau khi quyết định** và chỉ đọc khi mọi thread đã kết thúc; nó không phải biến dùng kiểm tra còn hàng.

**Giới hạn rất quan trọng:** Đây là atomic state trong **một JVM** với một `AtomicReference` được chia sẻ. Nó không thay thế transaction hoặc khóa phân tán nếu nhiều server cùng ghi tồn kho tại database. Nếu cần lưu đơn hàng và trừ kho đồng thời, phải bảo vệ bất biến tại nơi chứa dữ liệu dùng chung, không chỉ tại bộ nhớ của một ứng dụng.

### 12.1. Vấn đề ABA và reset state

Một CAS trên reference kiểm tra **cùng object reference**, không phải lịch sử mọi trạng thái đã đi qua. Nếu một thread khác thay state A→B→A theo chính cùng reference, thuật toán tổng quát có thể gặp vấn đề ABA. Với ví dụ tạo **record mới mỗi lần** và chỉ tiêu thụ một chiều trong mô hình nhỏ, đó không phải lỗi của thuật toán minh họa.

Trong hệ thống có **huỷ/hoàn trả/reset**, thêm version hoặc dùng một object state bất biến chứa version để quyết định CAS theo một generation, đảm bảo request cũ không thay nhầm quota của chu kỳ mới. Không chỉ gọi `AtomicLong.set(0)` rồi giữ các request cũ vẫn chạy và mong giới hạn cửa sổ mới đúng.

## 13. Bộ đếm theo khóa: ConcurrentHashMap.computeIfAbsent là bước khởi tạo, không phải toàn giao dịch

Có thể tạo một bộ đếm nguyên tử cho từng tenant/key:

```java
ConcurrentHashMap<String, AtomicInteger> perTenant =
        new ConcurrentHashMap<>();

AtomicInteger counter = perTenant.computeIfAbsent(
        tenantId, key -> new AtomicInteger());

boolean granted = tryAccept(counter, tenantLimit);
```

Đây là **mã trong phương thức**: `tenantId`, `tenantLimit` và `tryAccept` là tham số/helper thuộc ứng dụng. `computeIfAbsent` bảo đảm **khởi tạo mapping theo khóa** một cách nguyên tử cho CHM; `tryAccept` vẫn phải làm CAS trên AtomicInteger để cấp suất.

Nếu `AtomicInteger` được giữ cố định trong map và mọi tác vụ dùng cùng instance/limit, cách này có thể bảo vệ quota **theo một khóa trong một JVM**. Nhưng phải xét:

1. Nếu một thread giữ `counter` rồi thread khác `perTenant.remove(tenantId)`, thread thứ nhất có thể cập nhật **counter đã bị tách khỏi map**. Counter mới cho cùng tenant có thể bắt đầu từ 0 và tạo over-admission.
2. Nếu nhiều tenant đồng thời chia sẻ **một giới hạn tổng**, kiểm tra riêng từng per-key counter không bảo đảm tổng toàn hệ thống.
3. Nếu limit của tenant thay đổi trong lúc đang xử lý, trạng thái giới hạn cần đi cùng version hoặc một policy cập nhật có đồng bộ.
4. Nếu nhiều pod có những map khác nhau, không có một counter dùng chung; quota tổng không thể được bảo đảm bằng CHM cục bộ.

Đừng thay `AtomicInteger` ở value bằng `LongAdder` rồi gọi `adder.sum()` trong điều kiện quota: lại quay về check-then-act race.

### 13.1. Nếu cần atomic theo một khóa với value phức tạp

`ConcurrentHashMap.compute(key, (k, old) -> newState)` có thể cập nhật **mapping của một khóa** nguyên tử theo contract CHM khi callback ngắn và không sửa chính map. Đây là công cụ phù hợp nếu state một khóa chứa quota và version. Nhưng việc quyết định kết quả request còn cần được thiết kế đúng: không làm side effect ngoài map trong callback rồi hy vọng callback/transaction tự rollback.

Khi logic liên quan nhiều khóa, dùng transaction/điều phối thích hợp. Một lần `compute` trên khóa A và một lần trên khóa B **không tạo transaction hai khóa**.

## 14. Cơ chế chính xác ở nhiều tiến trình: Đưa quyết định đến nguồn trạng thái dùng chung

`AtomicLong` và `Semaphore` chỉ bảo vệ những thread có **cùng object trong cùng JVM**. Khi ứng dụng chạy nhiều instance hoặc Kubernetes pods, mỗi process có counter cục bộ; hai pod cùng còn một suất nếu chỉ tự đọc counter của mình.

Một số hướng triển khai **tại shared storage**:

- **Database transaction:** đọc/kiểm tra/cập nhật quota trong một transaction có isolation/locking phù hợp, hoặc dùng câu lệnh update có điều kiện với kiểm tra số hàng bị sửa.
- **Optimistic concurrency/versioning:** cập nhật nếu version còn đúng; nếu thất bại thì đọc lại và quyết định từ trạng thái mới.
- **Distributed atomic operation:** nếu lưu quota ở một hệ thống key-value có primitive/scripting transaction nguyên tử theo contract, dùng primitive đó. Phép cộng rồi đọc/hoàn trả ở nhiều lệnh rời **không mặc nhiên là một giao dịch**.
- **Reservation có định danh và idempotency:** một request có thể bị retry sau timeout; cần tránh mỗi retry cấp thêm suất cho cùng một hành động.
- **Unique constraints/transaction trên dữ liệu nghiệp vụ:** khi mục tiêu là số ghế/tồn kho đã đặt, điều kiện và bản ghi đặt chỗ nên được bảo vệ cùng nguồn dữ liệu, không chỉ bằng metric đếm request trên app server.

Ví dụ ý tưởng SQL có điều kiện (tùy RDBMS/driver, **không phải Java chạy độc lập**):

```sql
UPDATE quotas
SET used = used + 1
WHERE quota_id = ?
  AND used < quota_limit;
```

Sau đó kiểm tra **số dòng được cập nhật**: một dòng nghĩa là có thể đã cấp suất ở bước update; không dòng có thể là quota hết hoặc ID không tồn tại, cần xử lý theo yêu cầu. Bảo đảm concurrency của phương pháp này phụ thuộc RDBMS, transaction/isolation, kiểu dữ liệu và cách thức lưu quota; trong hệ thống có thêm booking/ledger phải bảo đảm các thao tác liên quan nằm trong ranh giới transaction phù hợp.

### 14.1. Không lấy metrics làm source of truth

Giả sử app gửi một `LongAdder` local đi tới Prometheus/metrics backend mỗi vài giây. Metric có độ trễ, khả năng sampling, thay đổi topology, restart hay mất một lần scrape. Nó **không thể** là nguồn duy nhất cho yêu cầu "chỉ còn đúng một suất" trong cluster.

Metrics để **quan sát**; admission state/transaction để **quyết định**. Có thể xuất số được cấp thành công từ source of truth sang metrics sau đó, nhưng đừng suy diễn metrics có tính tuyến tính hóa.

### 14.2. Phân biệt eventual consistency với strict bound

Một số sản phẩm cố ý chấp nhận giới hạn gần đúng: ví dụ soft rate limit nhằm giảm tải khi traffic cao, vượt 1–2% trong vài giây có thể chấp nhận được. Khi đó bộ đếm quan sát hoặc token bucket phân tán gần đúng có thể hữu ích. Nhưng nếu yêu cầu là **không bán dư một vé**, **không cho hơn N phiên**, **không vượt số tiền đã cấp phép**, thì phải thiết kế **strict invariant**, không dùng cách gần đúng vì đơn giản hơn.

Viết rõ trong yêu cầu: "hard cap" hay "soft cap", giới hạn theo user/tenant/global, theo thời gian hoặc đồng thời, và hệ thống chấp nhận thế nào khi backend không khả dụng.

## 15. Đọc nhiều biến nguyên tử riêng không thành một snapshot nhất quán

Giả sử ứng dụng có:

```java
AtomicLong accepted = new AtomicLong();
AtomicLong rejected = new AtomicLong();
AtomicLong attempts = new AtomicLong();
```

Mỗi phép `get` có ngữ nghĩa atomic cho **biến riêng**, nhưng đọc liên tiếp:

```java
long a = accepted.get();
long r = rejected.get();
long total = attempts.get();
```

**không tạo một snapshot nguyên tử của cả ba biến**. Một thread có thể tăng attempts, sau đó quyết định accepted/rejected; phép đọc liên tiếp có thể thấy một trạng thái ở **giữa** các bước hoặc từ các thời điểm khác nhau.

Điều này có thể hoàn toàn chấp nhận được trên dashboard. Nhưng nếu yêu cầu kiểm tra một bất biến như `accepted + rejected == attempts` ngay ở mọi thời điểm đọc, cần thiết kế một trạng thái tổng hợp có cơ chế snapshot/transaction đúng phạm vi, ví dụ một object bất biến công bố nguyên tử qua `AtomicReference` hoặc thực hiện kiểm tra tại điểm quiescent.

**Không nhầm:**
- Một biến AtomicLong: thao tác atomic cho **một biến**.
- Nhiều biến AtomicLong: từng biến atomic, **không có transaction nhóm**.
- LongAdder: cập nhật thread-safe, nhưng `sum` không atomic snapshot.
- LongAdder + `if` + `increment`: không có atomic admission.

## 16. Những kiểu reset/quota theo cửa sổ thời gian dễ sai

Giới hạn "1.000 lần mỗi ngày" hoặc "100 lần mỗi phút" không chỉ có một số counter; nó có **biên thời gian, chính sách refresh và request trễ**.

### 16.1. Reset về 0 trong khi request đang chạy

Nếu có thread đọc counter phiên bản cũ, sau đó một scheduler gọi `counter.set(0)` và thread cũ tiếp tục CAS/increment, thuật toán có thể cộng request cũ vào chu kỳ mới, hoặc cấp suất theo giới hạn cũ. Chỉ riêng AtomicLong không mô tả version cửa sổ.

Cách thiết kế rõ ràng hơn là state chứa **(windowId, used, limit)** và thay nguyên tử toàn state (hoặc lưu ở transactional backend), đồng thời quy định request được tính vào cửa sổ nào. Nếu có nhiều process, state phải được phối hợp ở shared store.

### 16.2. Không dùng LongAdder.sumThenReset để "chốt kế toán"

`sumThenReset` chỉ hữu ích khi ứng dụng chấp nhận cách sampling/reset tương ứng và biết giới hạn dưới cập nhật đồng thời. Nó **không** thay thế một cửa sổ quota strict với reset nguyên tử và version. Đặc biệt, nếu request được chấp nhận dựa trên sum snapshot racy rồi reset song song, rất khó chứng minh không vượt giới hạn.

### 16.3. Chính xác theo khoảng thời gian vật lý hay calendar?

Nếu yêu cầu "mỗi ngày theo giờ địa phương", ngày có thể thay đổi độ dài khi đổi DST, và ranh giới phải dựa trên `ZoneId` vùng. Nếu yêu cầu "trong 24 giờ gần nhất" hoặc sliding window, đó là một thuật toán **khác** với fixed daily quota. Đừng chỉ thêm `Thread.sleep(24h)` hoặc reset theo giờ UTC khi hợp đồng là ngày địa phương ở một vùng.

Điều này không làm `LongAdder` phù hợp hơn cho admission; nó cho thấy bản thân **định nghĩa cửa sổ và transaction** mới là phần quan trọng của quota.

## 17. Side effects và retry: Phải có đúng một ranh giới quyết định

Một vấn đề khác ngoài bộ đếm là **hành động thực tế**. Giả sử ứng dụng CAS thành công, rồi gọi API thanh toán. Nếu API timeout, không rõ charge đã xảy ra hay chưa, và có thể retry.

- **AtomicLong CAS** chỉ xác nhận đã lấy một suất ở local memory. Nó không rollback charge/booking nếu request thất bại sau đó.
- Nếu **trả quota** khi downstream báo lỗi, phải tránh trả hai lần cho cùng request; cần idempotency hoặc trạng thái reservation được theo dõi.
- Nếu backend trả thành công nhưng client không nhận phản hồi, retry phải nhận biết request ID để không cấp suất hai lần.
- Trong ứng dụng nhiều server, không dùng AtomicLong cục bộ để quyết định một booking được xác nhận tại database.

Đừng đặt side effect trong callback của `AtomicLong.updateAndGet` hoặc `AtomicReference.updateAndGet`: hàm có thể được đánh giá lại khi tranh chấp. Tương tự, callback `ConcurrentHashMap.compute` nên ngắn và không chứa hành vi cập nhật map đệ quy hay I/O blocking lâu.

**Mẫu tư duy:** Tách "quyết định chấp nhận" (state có tính nguyên tử đúng phạm vi), "thực thi side effect" (idempotent/transaction) và "thống kê đã xử lý" (LongAdder/metrics). Ba phần có thể cần phối hợp, nhưng không thể thay thế nhau.

## 18. Kiểm thử concurrent đúng cách

Một test đơn luồng:

```java
LongAdder adder = new LongAdder();

if (adder.sum() < 1) {
    adder.increment();
}

System.out.println(adder.sum()); // 1 trong chạy đơn luồng
```

không chứng minh thuật toán quota an toàn; nó chỉ cho biết một interleaving thuận lợi. Test concurrency cần xét **ít nhất hai request cùng bước qua ranh giới còn một suất**.

### 18.1. Nên kiểm tra những bất biến nào?

| Yêu cầu | Bất biến / điều cần assert |
| --- | --- |
| Quota tích lũy N | `accepted <= N` sau mọi execution; không có request được đánh dấu accepted khi quota đã hết |
| Quota cuối sau 4.000 request | `accepted == min(totalAttempts,N)` khi mỗi request thử đúng một lần và không có lỗi khác |
| Tổng thống kê sau khi dừng writer | `attempts.sum() == số lần increment thực sự` |
| Số tác vụ đang chạy N | `active <= N` suốt thời gian test, không chỉ khi hoàn tất |
| Semaphore cleanup | Sau tất cả tasks, `active == 0`, permits trở về capacity |
| Value gồm nhiều field | `available >= 0`, `reserved >= 0`, `available + reserved == initial` theo mô hình |
| Reset/rotation | Request cũ không được cấp suất ở generation mới ngoài policy |
| Shared store nhiều process | Hard limit đúng khi nhiều instance cùng cập nhật |
| Exception/timeout | Không bị rò permit hoặc mất/đúp reservation |
| Metrics sampling | Đọc trong lúc update không được dùng như assertion snapshot |

### 18.2. Dùng latch thay sleep

`CountDownLatch` giúp dựng chính xác thời điểm hai thread đã đọc trước khi cùng update — như `NaiveLimitRaceDemo`. `Thread.sleep` không đủ bảo đảm thứ tự, có thể làm test flaky.

Dùng `Future.get()` trước khi đọc kết quả cuối:

- Chờ tác vụ hoàn tất.
- Propagate exception từ worker.
- Tạo quan hệ happens-before phù hợp để main quan sát các cập nhật đã hoàn thành.

Sau khi `Future.get` của tất cả task và biết không còn update/reset, tổng từ LongAdder là **kết quả cuối đáng tin**. Nếu còn một background thread tăng, kết luận này không áp dụng.

### 18.3. Đừng chỉ kiểm tra kết quả cuối nếu cần ngăn oversell tức thời

Một hệ thống có thể tạm thời cho 101 request qua, rồi giảm counter về 100 sau đó. Test cuối chỉ thấy 100 nhưng **đã có hành động được phép thực hiện quá ngưỡng**. Với hard cap, phải đo **số request đã thực sự được cấp quyền và thực thi**, cùng cách quyết định/permit theo thời điểm, không chỉ counter cuối sau các phép rollback.

Đó là lý do mẫu `AtomicQuotaDemo` chỉ trả true sau khi CAS tăng state thành công, còn `SemaphoreCapacityDemo` bảo vệ đoạn thực thi bằng permit.

## 19. Những lỗi thường gặp cần tránh

1. **Dùng `LongAdder.sum() < limit` rồi `increment()` để cấp quyền:** đọc không phải snapshot nguyên tử, và check-then-act không nguyên tử.
2. **Thay LongAdder bằng AtomicLong nhưng giữ `if(get)<limit; increment`:** vẫn race giữa hai lời gọi atomic.
3. **Dùng `LongAccumulator.get()` làm điều kiện quota:** get không phải atomic snapshot khi đang accumulate.
4. **Dùng `DoubleAdder` làm sổ tiền chính xác:** float rounding và việc tổng hợp không atomic snapshot không phù hợp.
5. **Tưởng LongAdder có thể mất increment vì contention:** các update của nó thread-safe; vấn đề là cách đọc khi đồng thời, không phải tự mất mọi cập nhật.
6. **Đọc `LongAdder.sum()` trong lúc ghi rồi khẳng định đó là một điểm chính xác trên timeline:** Javadoc không bảo đảm snapshot.
7. **Đọc `sum()` sau khi worker hoàn tất rồi vẫn cho là "luôn gần đúng":** khi không còn update, tổng phản ánh các cập nhật đã hoàn tất.
8. **Dùng `sumThenReset` để chốt quota strict khi writer vẫn chạy:** reset không là transaction với các request khác.
9. **Cho rằng `longValue()` của LongAdder là atomic hơn `sum()`:** hai method tương đương.
10. **Dùng `AtomicLong.getAndIncrement` không kèm điều kiện quota:** tăng nguyên tử nhưng vẫn có thể vượt hạn mức nếu không kiểm tra.
11. **Dùng `AtomicLong.getAndUpdate` với lambda có side effect:** callback có thể được áp dụng lại trong contention.
12. **Dùng `updateAndGet` trên phép bão hòa rồi kết luận từ giá trị mới rằng lần này đã được chấp nhận:** kết quả limit có thể là vừa nhận suất cuối hoặc bị từ chối.
13. **Trả true trước khi CAS thành công:** retry có thể đã mất quyền, khiến kết quả khác trạng thái.
14. **Làm side effect DB trong vòng CAS:** mỗi lần retry có thể tạo hành động trùng lặp.
15. **Không kiểm tra overflow số đếm:** AtomicLong không tự ném khi increment tràn long.
16. **Gọi Semaphore.release khi chưa acquire thành công:** release thừa tăng permit, phá giới hạn.
17. **Quên release trong finally sau lỗi:** rò permit, làm hệ thống bị kẹt.
18. **Dùng Semaphore cho quota cả đời nhưng lại release sau mỗi request:** đó là giới hạn concurrent, không phải tổng số lượt.
19. **Coi `Semaphore.availablePermits()` + if + acquire là một transaction:** nên dùng `tryAcquire`/`acquire` trực tiếp.
20. **Đọc ba AtomicLong và nghĩ có snapshot nguyên tử cả ba:** chỉ mỗi biến có đọc riêng.
21. **Sửa hai field mutable độc lập và nghĩ AtomicReference tự bảo vệ chúng:** CAS reference không tự đồng bộ object mutable.
22. **Sửa `record` state mới rồi quên CAS:** tính được state mới không có nghĩa đã công bố nguyên tử.
23. **Dùng bộ đếm cục bộ để áp limit trên nhiều pod:** mỗi pod có state riêng, không có giới hạn toàn cục.
24. **Dùng số liệu metrics backend/scrape làm nguồn sự thật của booking:** metrics có delay, restart, sampling và không tuyến tính hóa.
25. **Reset AtomicLong theo timer mà không version cửa sổ:** request cũ có thể cập nhật quota mới.
26. **Coi quota trên từng khóa đồng nghĩa quota toàn map:** tổng nhiều khóa cần cơ chế khác.
27. **Gỡ mapping `ConcurrentHashMap<K,AtomicInteger>` khi còn thread giữ reference:** update có thể diễn ra trên counter đã bị tách khỏi map.
28. **Thêm permit khi rollback hai lần do retry:** phải theo dõi ownership/idempotency.
29. **Đánh giá "không oversell" chỉ bằng counter cuối:** có thể đã thả quá nhiều request rồi trừ/điều chỉnh.
30. **Benchmark bằng một lần chạy rồi kết luận LongAdder luôn nhanh hơn AtomicLong:** phụ thuộc contention và workload.
31. **Quên phạm vi process** khi dùng AtomicLong, AtomicReference, Semaphore hoặc ConcurrentHashMap.
32. **Cho rằng LongAccumulator dùng hàm bất kỳ đều có kết quả thứ tự xác định:** cần hàm phù hợp và không có side effects.
33. **Gộp counter thống kê và state điều khiển thành một đối tượng rồi reset cho dashboard:** reset metrics có thể phá điều kiện admission.
34. **Đặt callback kéo dài nhiều giây để gọi mạng trong một phép cập nhật atomic theo khóa:** có thể chặn writer khác và khó kiểm soát thời gian xử lý.
35. **Dùng Optional/Boolean kết quả nhưng không gắn với thời điểm quyết định nguyên tử:** kết quả "accepted" có thể không còn phản ánh state thật.

## 20. Checklist thiết kế điều kiện kiểm soát chính xác

Trước khi hoàn thành một tính năng quota, rate limit, tồn kho hoặc giới hạn tác vụ:

- [ ] Yêu cầu là **thống kê** hay **hard limit**?
- [ ] Giới hạn là **tổng lượt tích lũy**, **số đang chạy**, **theo khóa**, **theo cửa sổ thời gian** hay **toàn cluster**?
- [ ] Giá trị đọc có phải một snapshot nguyên tử cần thiết không, hay sampling thống kê là đủ?
- [ ] Đã tránh chuỗi `if (counter.sum()/get() < limit)` rồi cập nhật tách rời?
- [ ] Nếu là hard cap trong JVM, có CAS loop hoặc một atomic update trả kết quả đúng hay không?
- [ ] Callback của `getAndUpdate` / CAS có **side-effect-free** và an toàn khi retry?
- [ ] Nếu kiểm soát tác vụ đang chạy, có dùng `Semaphore` với acquire/release trong ranh giới đúng?
- [ ] Có tránh release thừa hoặc quên release khi exception/interrupt?
- [ ] Nếu nhiều field phải nhất quán, có một immutable state được CAS hoặc transaction phù hợp?
- [ ] Nếu nhiều keys/processes cùng tham gia, cơ chế thực sự có tính nguyên tử ở **shared source of truth**?
- [ ] Có xử lý việc reset/cửa sổ quota bằng generation/version/idempotency?
- [ ] Có tách thống kê `LongAdder` ra khỏi biến quyết định, và chỉ dùng sum để quan sát?
- [ ] Có hiểu `sumThenReset/getThenReset` không phải transaction khi concurrent writes?
- [ ] Có xét overflow, limit thay đổi, request bị retry và cleanup khi lỗi?
- [ ] Có test điều kiện còn đúng một suất bằng latch, không chỉ chạy tuần tự?
- [ ] Có assert cả số suất thật sự đã cấp và số tác vụ active cực đại, không chỉ counter cuối?
- [ ] Có đọc kết quả thống kê cuối sau khi mọi task hoàn tất qua `Future.get()`?
- [ ] Có benchmark/tuning riêng khi mục tiêu là throughput, không dùng thiết kế metrics để đánh đổi bất biến nghiệp vụ?

## 21. Câu hỏi tự kiểm tra

1. `LongAdder.sum()` có bảo đảm snapshot nguyên tử khi nhiều thread đang `increment()` không?
2. Nếu hai thread cùng thấy `sum() == 9` với giới hạn 10 rồi cùng tăng, điều gì có thể xảy ra?
3. Thay `LongAdder` bằng `AtomicLong` và vẫn tách `get` với `incrementAndGet` có giải quyết race không?
4. Vì sao `compareAndSet` có thể cấp đúng một suất cuối cùng cho hai thread cùng cạnh tranh?
5. Khi CAS thất bại do contention, caller nên làm gì? Có nên đã gửi email trong vòng lặp trước khi CAS thành công?
6. `getAndUpdate` trả giá trị trước hay sau? Vì sao hữu ích cho quyết định quota bão hòa?
7. Vì sao lambda của `getAndUpdate` phải thuần?
8. `LongAdder.sum()` có thể cho kết quả cuối chính xác sau khi mọi worker đã `Future.get()` không?
9. `LongAccumulator.get()` có là snapshot nguyên tử trong lúc accumulate không?
10. `DoubleAdder` có phù hợp để kiểm soát số tiền tối đa chính xác đến từng đơn vị nhỏ nhất không?
11. Muốn tối đa ba HTTP call blocking đang chạy cùng lúc trong một JVM, nên dùng LongAdder hay Semaphore?
12. Tại sao phải `release()` trong finally và chỉ sau khi lấy permit thành công?
13. Semaphore giới hạn **đồng thời** hay **tổng số lượt trong đời ứng dụng** nếu luôn trả permit?
14. Hai `AtomicInteger` cho `available` và `reserved` có tạo atomic snapshot của cả hai field không?
15. `AtomicReference<ImmutableState>` giúp giữ bất biến hai field như thế nào?
16. Vì sao counter quota trong một JVM không bảo đảm quota toàn cụm nhiều server?
17. `LongAdder.sumThenReset()` có thể thay transaction reset quota theo cửa sổ thời gian không?
18. Vì sao một test "kết thúc còn đúng 100 suất đã cấp" không luôn chứng minh chưa bao giờ cấp vượt rồi rollback?
19. Nếu ứng dụng có hai quota A và B cần cấp cùng một giao dịch, một CAS trên mỗi counter riêng có bảo đảm cả hai cùng thành công/thất bại không?
20. Metric và nguồn dữ liệu nghiệp vụ có nên bị gộp thành cùng một biến chỉ vì cùng có tên `count` không?

**Đáp án gợi ý:**
1. Không; `sum` không phải atomic snapshot khi đang update.
2. Có thể cả hai được cấp, tổng tăng thành 11.
3. Không; check-then-act vẫn là hai thao tác.
4. Chỉ một thread có thể CAS thành công từ cùng giá trị expected; thread còn lại đọc lại và thấy hết suất.
5. Đọc lại/retry theo state mới; không làm side effect trước khi CAS thành công.
6. Giá trị cũ, nên phân biệt vừa nhận suất cuối với đã đầy từ trước.
7. Hàm có thể được gọi lại khi tranh chấp.
8. Có, nếu không còn writer/reset và toàn bộ increment đã hoàn tất.
9. Không.
10. Không; floating point và snapshot không phù hợp cho strict financial accounting.
11. Semaphore.
12. Để không rò permit hoặc làm sai số permit khi exception.
13. Đồng thời.
14. Không.
15. CAS thay cả immutable value như một state duy nhất.
16. Các JVM khác nhau không chia sẻ cùng AtomicLong/AtomicReference.
17. Không khi writer vẫn chạy.
18. Có thể đã cấp vượt rồi giảm state; hành động thật đã diễn ra.
19. Không; cần transaction/coordinator phù hợp.
20. Không; metrics để quan sát, state/transaction để quyết định.

**Kết luận:** `LongAdder`, `DoubleAdder` và các `Accumulator` là công cụ rất tốt cho **thu thập thống kê đồng thời**, nhưng **không được dùng phép tổng hợp `sum/get` của chúng làm điều kiện kiểm soát chính xác**. Khi cần hard quota, kết hợp kiểm tra và cấp suất tại một atomic decision qua `AtomicLong/AtomicInteger.compareAndSet` hoặc `getAndUpdate`; khi giới hạn số tác vụ đang hoạt động, dùng `Semaphore` với quản lý permit đúng; khi nhiều field tham gia, CAS immutable state; khi nhiều process và dữ liệu nghiệp vụ tham gia, dùng transaction/primitive nguyên tử của shared store. Tách **metrics quan sát** khỏi **state cấp quyền**, kiểm thử các interleaving nguy hiểm và xác định rõ phạm vi đồng bộ để tránh oversell, vượt quota hoặc phát sinh hành động trùng.

## Tài liệu chính thức — các API Java còn áp dụng

- `LongAdder` — thống kê dưới contention, `sum()` không là atomic snapshot, `sumThenReset()` và ứng dụng với `ConcurrentHashMap`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html
- `DoubleAdder` — tổng số thực và kết quả đọc khi cập nhật đồng thời: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/DoubleAdder.html
- `LongAccumulator` — hàm tích lũy, identity và giới hạn của `get()`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAccumulator.html
- `DoubleAccumulator` — tích lũy số thực theo hàm: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/DoubleAccumulator.html
- `AtomicLong` — `compareAndSet`, `getAndUpdate`, `incrementAndGet`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html
- `AtomicInteger` — giới hạn integer và update atomic: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html
- `AtomicReference` — CAS trên object reference: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html
- `Semaphore` — permits, acquire/release và kiểm soát số tác vụ đồng thời: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Semaphore.html
- `ConcurrentHashMap` — frequency map, tính nguyên tử theo khóa và giới hạn của cập nhật nhiều khóa: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- `CountDownLatch` / `Future` — phối hợp và đợi tác vụ trong unit test concurrency: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountDownLatch.html và https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Future.html
