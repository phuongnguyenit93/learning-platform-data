# Check-then-act và lỗi kiểm tra rồi thao tác trong Java Concurrency

**Check-then-act** là mẫu mã “kiểm tra điều kiện, rồi thực hiện hành động dựa trên kết quả kiểm tra”. Trong chương trình chạy một luồng, hai bước thường được hiểu là nối tiếp. Trong chương trình nhiều luồng, một luồng khác có thể **thay đổi trạng thái dùng làm điều kiện ngay sau bước kiểm tra và trước bước thao tác**. Khi đó hành động được thực hiện dựa trên thông tin đã lỗi thời, tạo thành một dạng **race condition**.

Ví dụ tưởng như hợp lý:

```java
// Trích đoạn minh họa, giả định 'cache' đã được khai báo.
if (!cache.containsKey("config")) {    // Check
    cache.put("config", loadConfig());   // Act
}
```

Nếu hai thread đều thấy key chưa tồn tại, **cả hai có thể chạy `loadConfig()` và ghi kết quả**. Ngay cả khi bản thân `containsKey()` và `put()` đều thread-safe, cặp thao tác này vẫn chưa chắc là một giao dịch nguyên tử (*atomic operation*). Mục tiêu là nhận diện đúng khoảng thời gian nguy hiểm đó, hiểu vì sao các giải pháp “kiểm tra rồi ghi” đơn thuần thất bại, và chọn cơ chế Java thích hợp để gộp kiểm tra với hành động.

## 1. Check-then-act là gì?

Một điều kiện có thể kiểm tra trạng thái rồi quyết định thực hiện hành động:

- “Nếu chưa có cấu hình trong cache thì tạo cấu hình.”
- “Nếu còn một suất thì đặt chỗ và giảm số suất.”
- “Nếu số lượng nhỏ hơn giới hạn thì tăng số lượng.”
- “Nếu tài nguyên chưa được khởi tạo thì khởi tạo nó.”

Vấn đề nằm ở **tính toàn vẹn của cả chuỗi** `check → act`, không nhất thiết nằm ở từng lệnh riêng lẻ. Mỗi lệnh có thể hợp lệ khi chạy độc lập, nhưng việc xen kẽ giữa các thread phá vỡ điều kiện mà hành động đang giả định.

Giả sử một tài nguyên chỉ được phép tạo **một lần**:

| Thời điểm | Thread A | Thread B | Trạng thái chung |
|---|---|---|---|
| T0 |  |  | Chưa có tài nguyên. |
| T1 | Đọc: chưa có. |  | Chưa có. |
| T2 |  | Đọc: chưa có. | Chưa có. |
| T3 | Tạo tài nguyên A. |  | Đã tạo A. |
| T4 |  | Tạo tài nguyên B. | Đã tạo thêm B. |
| T5 | Ghi A vào cache. |  | Cache chứa A. |
| T6 |  | Ghi B vào cache. | Cache chứa B; A bị ghi đè. |

Sau cùng cache có thể chỉ chứa một giá trị, nhưng điều đó **không chứng minh việc khởi tạo chỉ diễn ra một lần**. Nếu việc tạo có tác dụng phụ (kết nối, ghi dữ liệu, phát sự kiện, cấp tài nguyên), tác dụng phụ có thể xảy ra hai lần.

Tên kỹ thuật *TOCTOU* (*time of check to time of use*) cũng diễn tả kiểu lỗi này: trạng thái được xác minh tại một thời điểm nhưng được sử dụng tại thời điểm khác, khi sự thật có thể đã thay đổi.

## 2. Những thuộc tính cần phân biệt

**Atomicity (tính nguyên tử):** tập thao tác quan trọng được thực hiện như một đơn vị đối với các luồng cùng cạnh tranh, không cho một luồng khác quan sát hoặc can thiệp vào trạng thái trung gian theo cách phá vỡ bất biến. Với check-then-act, cần bảo đảm **kiểm tra và cập nhật** thuộc cùng cơ chế phối hợp.

**Visibility (tính hiển thị):** giá trị do luồng này ghi được luồng khác nhìn thấy theo các quan hệ đồng bộ hóa trong Java Memory Model. `volatile` hoặc `AtomicInteger.get()` có thể giúp việc đọc thấy giá trị mới, **nhưng không tự biến hai hành động tách rời thành một thao tác nguyên tử**.

**Ordering (thứ tự):** `happens-before` ràng buộc khả năng quan sát và thứ tự bộ nhớ giữa các thao tác liên quan. Có `happens-before` đúng cho một phép ghi/đọc vẫn không làm cho `if (condition) act()` tự động an toàn nếu không có cách bảo vệ toàn bộ quyết định.

**Invariant (bất biến):** quy tắc luôn phải đúng, chẳng hạn `available >= 0`, một mã chỉ được cấp một lần, hoặc `available + reserved == capacity`. Cách sửa phải bảo vệ **bất biến**, chứ không chỉ sửa một dòng code trông có vẻ nguy hiểm.

Cần tách hai loại lỗi thường đi cùng nhau: *data race* theo Java Memory Model là truy cập xung đột tới cùng biến thiếu đồng bộ hóa/happens-before; còn *race condition* là kết quả phụ thuộc vào lịch xen kẽ không mong muốn. Ví dụ hai thao tác riêng lẻ trên `ConcurrentHashMap` có thể không tạo data race trong cấu trúc nội bộ, nhưng vẫn tạo **race condition ở cấp logic** nếu điều kiện và hành động không được gộp.

## 3. Ví dụ tái hiện lỗi với ConcurrentHashMap

Dùng `ConcurrentHashMap` để **loại bỏ lỗi truy cập cấu trúc dữ liệu không an toàn** và cô lập đúng lỗi check-then-act: `get()` và `put()` đều thread-safe riêng lẻ, nhưng hai lệnh không tự gộp thành một hành động. Hai `CountDownLatch` không cần thiết; chỉ một latch đếm hai lượt kiểm tra đã đủ để cố tình tạo lịch xen kẽ sai.

Tạo tệp **`CheckThenActRace.java`**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class CheckThenActRace {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, String> cache = new ConcurrentHashMap<>();
        AtomicInteger initializations = new AtomicInteger();
        CountDownLatch bothSawMissing = new CountDownLatch(2);

        Runnable worker = () -> {
            if (cache.get("config") == null) {
                bothSawMissing.countDown();

                try {
                    bothSawMissing.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }

                int attempt = initializations.incrementAndGet();
                cache.put("config", "created-" + attempt);
            }
        };

        Thread first = new Thread(worker, "first");
        Thread second = new Thread(worker, "second");

        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Initializations: " + initializations.get());
        System.out.println("Cache entries: " + cache.size());
    }
}
```

Chạy với JDK 17+:

```bash
javac CheckThenActRace.java
java CheckThenActRace
```

Kết quả:

```text
Initializations: 2
Cache entries: 1
```

Ở đây cả hai thread cùng đọc `null`, sau đó mỗi thread giảm `bothSawMissing` rồi chờ cho tới khi **cả hai đã đi qua bước kiểm tra**. Vì không thread nào ghi vào cache trước thời điểm đó, cả hai đều đi vào nhánh tạo giá trị. `AtomicInteger` chỉ bảo đảm phép đếm `initializations` an toàn, **không** bảo vệ điều kiện `get() == null`. Hai lần `put()` có thể diễn ra theo thứ tự khác nhau, nên ví dụ không in giá trị cuối cùng (giá trị đó không cố định).

Bài học quan trọng: thay `HashMap` bằng `ConcurrentHashMap` giải quyết an toàn truy cập map, **không tự sửa** chuỗi `get() → if → put()` ở tầng nghiệp vụ.

## 4. Sửa lỗi khởi tạo cache bằng một thao tác nguyên tử

Với `ConcurrentHashMap`, `computeIfAbsent(key, mappingFunction)` cung cấp thao tác nguyên tử cho trường hợp “nếu key chưa có giá trị thì tính và gắn giá trị”. Trong cùng một thời kỳ key chưa được gắn và không bị xóa/chỉnh từ nơi khác, các thread cạnh tranh sẽ chia sẻ kết quả khởi tạo thay vì mỗi thread tự chạy hàm tính.

Tạo tệp **`AtomicCacheInitialization.java`**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCacheInitialization {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, String> cache = new ConcurrentHashMap<>();
        AtomicInteger initializations = new AtomicInteger();
        CountDownLatch startTogether = new CountDownLatch(1);

        Runnable worker = () -> {
            try {
                startTogether.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }

            cache.computeIfAbsent("config", key -> {
                initializations.incrementAndGet();
                return "created";
            });
        };

        Thread first = new Thread(worker, "first");
        Thread second = new Thread(worker, "second");
        first.start();
        second.start();

        startTogether.countDown();
        first.join();
        second.join();

        System.out.println("Initializations: " + initializations.get());
        System.out.println("Cache entries: " + cache.size());
        System.out.println("Config: " + cache.get("config"));
    }
}
```

```bash
javac AtomicCacheInitialization.java
java AtomicCacheInitialization
```

Kết quả:

```text
Initializations: 1
Cache entries: 1
Config: created
```

Khác ví dụ lỗi, phép “kiểm tra key có mặt chưa và tính giá trị nếu thiếu” nằm trong **một phương thức có hợp đồng nguyên tử**. Với `ConcurrentHashMap.computeIfAbsent`, hàm ánh xạ được áp dụng tối đa một lần cho mỗi lời gọi cần tạo mapping theo hợp đồng của map; các lời gọi đồng thời vào cùng key không tạo nhiều giá trị thành công cho cùng đợt thiếu key như ví dụ trên.

**Các điều kiện không được bỏ qua:**

- `mappingFunction` nên ngắn gọn, không gây chặn kéo dài và không được sửa chính map đang được tính mapping. Các cập nhật khác có thể bị chặn trong quá trình tính.
- Nếu hàm trả về `null` hoặc ném ngoại lệ, mapping mới sẽ không được thiết lập; lời gọi tương lai có thể tính lại. Nếu mapping bị xóa sau khi tạo, lần gọi sau cũng có thể tạo lại.
- Hợp đồng giữa các kiểu `Map` không hoàn toàn giống nhau: `Map.computeIfAbsent` mặc định **không tự bảo đảm đồng bộ hóa/nguyên tử**. Khi dựa vào tính nguyên tử, hãy dùng và đọc hợp đồng của triển khai đồng thời cụ thể, như `ConcurrentHashMap`.
- `putIfAbsent(key, value)` cũng có thể đặt giá trị một cách nguyên tử nếu key vắng mặt, nhưng khi viết `putIfAbsent(key, expensiveCreate())`, biểu thức `expensiveCreate()` được đánh giá **trước khi** gọi phương thức; nhiều thread vẫn có thể tạo giá trị thừa. Chọn `computeIfAbsent` khi cần tránh tính toán dư và có thể đáp ứng các giới hạn của mapping function.

## 5. Lỗi “kiểm tra giới hạn rồi tăng”: AtomicInteger không tự sửa hai lệnh

Xét yêu cầu “chỉ có tối đa một suất”. Đoạn sau có thể sai ngay cả khi `booked` là `AtomicInteger`:

```java
// Mã minh họa KHÔNG an toàn khi nhiều thread cạnh tranh.
if (booked.get() < 1) {
    booked.incrementAndGet();
}
```

Hai thread có thể đều đọc `0 < 1`, rồi đều tăng. `incrementAndGet()` là nguyên tử cho **một phép tăng**, nhưng toàn bộ “đọc để kiểm tra → tăng” thì chưa. Không có chuyện `AtomicInteger` tự khóa toàn bộ mọi đoạn mã xung quanh nó.

Một cách đúng với **một biến trạng thái** là vòng lặp compare-and-set (CAS): lấy giá trị cũ, kiểm tra điều kiện, rồi chỉ ghi giá trị mới nếu giá trị vẫn đúng bằng giá trị đã đọc. Nếu CAS thất bại do thread khác thắng trước, đọc lại và kiểm tra lại.

Tạo tệp **`AtomicReservation.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicReservation {
    private static boolean reserveOne(AtomicInteger available) {
        while (true) {
            int current = available.get();

            if (current <= 0) {
                return false;
            }

            if (available.compareAndSet(current, current - 1)) {
                return true;
            }
            // Giá trị đã đổi: đọc lại, kiểm tra lại bất biến.
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicInteger available = new AtomicInteger(1);
        AtomicInteger accepted = new AtomicInteger();

        Runnable request = () -> {
            if (reserveOne(available)) {
                accepted.incrementAndGet();
            }
        };

        Thread first = new Thread(request);
        Thread second = new Thread(request);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Accepted: " + accepted.get());
        System.out.println("Available: " + available.get());
    }
}
```

```bash
javac AtomicReservation.java
java AtomicReservation
```

Kết quả:

```text
Accepted: 1
Available: 0
```

Dù thứ tự thread nào thắng không xác định, kết quả tổng luôn đúng: chỉ một CAS có thể đổi `1 → 0`; thread còn lại đọc `0` hoặc CAS thất bại và đọc lại, nên không giảm dưới 0. Đây là cách kết hợp **check + act** tại cùng một điểm nguyên tử cho một biến.

Có thể cân nhắc `AtomicInteger.updateAndGet` hoặc `getAndUpdate` nếu biểu thức cập nhật đủ rõ, nhưng hàm truyền vào **có thể được gọi lại** khi CAS tranh chấp: không đặt hiệu ứng phụ như gửi email, ghi file hay tăng một counter độc lập bên trong lambda cập nhật. Mã CAS ở ví dụ đặt việc tăng `accepted` chỉ sau khi CAS thực sự thành công.

## 6. Với nhiều biến liên quan, dùng cùng một vùng bảo vệ

CAS trên một `AtomicInteger` không tự bảo vệ bất biến có **nhiều trường**. Ví dụ, hệ thống theo dõi `available` và `reserved`, cần duy trì `available + reserved == capacity`. Nếu cập nhật một biến rồi thread khác đọc biến còn lại giữa chừng, nó có thể thấy trạng thái tạm thời không hợp lệ.

Một cách đơn giản là đưa cả điều kiện lẫn các thay đổi liên quan vào cùng một vùng `synchronized` trên **cùng đối tượng khóa**.

Tạo tệp **`SynchronizedReservation.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class SynchronizedReservation {
    static final class Inventory {
        private int available = 1;
        private int reserved = 0;

        synchronized boolean reserve() {
            if (available == 0) {
                return false;
            }

            available--;
            reserved++;
            return true;
        }

        synchronized String snapshot() {
            return "Available: " + available
                    + ", Reserved: " + reserved;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Inventory inventory = new Inventory();
        AtomicInteger accepted = new AtomicInteger();

        Runnable request = () -> {
            if (inventory.reserve()) {
                accepted.incrementAndGet();
            }
        };

        Thread first = new Thread(request);
        Thread second = new Thread(request);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Accepted: " + accepted.get());
        System.out.println(inventory.snapshot());
    }
}
```

```bash
javac SynchronizedReservation.java
java SynchronizedReservation
```

Kết quả:

```text
Accepted: 1
Available: 0, Reserved: 1
```

Cả hai thread dùng cùng đối tượng `inventory`. Chỉ một thread được thực thi `reserve()` trong monitor của đối tượng tại một thời điểm. Vì kiểm tra và cả hai phép cập nhật ở **cùng vùng bảo vệ**, thread thứ hai sẽ thấy số suất đã giảm và không thể đặt vượt giới hạn. Phương thức `snapshot()` cũng dùng monitor đó để quan sát hai trường nhất quán.

Trong code thật, **mọi đường đọc/ghi cùng bất biến** đều phải tuân theo cơ chế bảo vệ. Hai vùng `synchronized` dùng hai object khóa khác nhau không bảo vệ nhau. Nếu có nhu cầu `tryLock`, timeout hoặc khóa ngắt được, `ReentrantLock` là lựa chọn; luôn gọi `unlock()` trong `finally`:

```java
lock.lock();
try {
    // Kiểm tra điều kiện và cập nhật trạng thái được bảo vệ.
} finally {
    lock.unlock();
}
```

Đây là trích đoạn minh họa, giả định `lock` là `ReentrantLock` đã được tạo. Tránh thực hiện thao tác I/O hay chờ không kiểm soát trong critical section khi không cần thiết, vì giữ khóa lâu sẽ làm giảm khả năng tiến triển và có thể gây deadlock nếu phối hợp khóa sai thứ tự.

## 7. Chọn công cụ phù hợp cho từng bất biến

| Yêu cầu check-then-act | Công cụ Java thường phù hợp | Chú ý |
|---|---|---|
| Tăng một bộ đếm không có điều kiện | `AtomicInteger.incrementAndGet()` | Đây đã là một phép tăng nguyên tử; không cần tự `get() + set()`. |
| Giảm quota nếu còn số dư | Vòng CAS với `compareAndSet`, hoặc một phép update nguyên tử phù hợp | Kiểm tra lại điều kiện sau CAS thất bại; không chạy side effect trước khi thắng CAS. |
| Khởi tạo key vắng mặt trong map đồng thời | `ConcurrentHashMap.computeIfAbsent()` | Mapping function ngắn, không sửa cùng map, xử lý null/exception. |
| Chỉ chèn nếu key vắng mặt và đã có sẵn giá trị | `ConcurrentHashMap.putIfAbsent()` | Chèn nguyên tử, nhưng xây dựng tham số trước lời gọi có thể bị lặp. |
| Đọc/sửa nhiều trường phải nhất quán | `synchronized` hoặc `ReentrantLock` cho toàn bộ giao dịch nội bộ | Cùng khóa, cùng đối tượng trạng thái, mọi đường truy cập tuân thủ. |
| Tạo tài nguyên thuộc hệ thống bên ngoài (file/database) | Thao tác nguyên tử hoặc ràng buộc giao dịch do **hệ thống đó** cung cấp | Khóa trong JVM không bảo vệ các tiến trình/JVM khác. |

**“Thread-safe collection” không tương đương “thread-safe business operation”.** Với `ConcurrentHashMap`, từng phương thức có thể thread-safe nhưng chuỗi `containsKey() → put()` vẫn lỗi; với `Collections.synchronizedMap`, muốn thực hiện hành động hợp thành phải giữ đúng monitor bao trùm toàn bộ chuỗi theo hợp đồng và mọi code truy cập liên quan phải phối hợp.

## 8. TOCTOU ngoài bộ nhớ JVM

Check-then-act cũng xảy ra với file và hệ thống ngoài tiến trình:

```java
// Không an toàn nếu dùng để tự bảo đảm rằng file còn vắng mặt.
if (!Files.exists(path)) {
    Files.createFile(path);
}
```

Đây là trích đoạn minh họa; giả định đã có `Path path` và import thích hợp. Một tiến trình khác có thể tạo file sau `exists()` nhưng trước `createFile()`. `Files.createFile(path)` **tự thực hiện bước kiểm tra và tạo một cách nguyên tử với các hoạt động filesystem khác ảnh hưởng thư mục**, theo hợp đồng của API; nếu file đã tồn tại, API có thể ném `FileAlreadyExistsException`. Vì vậy với yêu cầu “chỉ tạo nếu chưa có”, hãy gọi trực tiếp thao tác nguyên tử và xử lý kết quả:

```java
try {
    Files.createFile(path);
    // Tạo file thành công.
} catch (FileAlreadyExistsException e) {
    // File đã có: xử lý theo nghiệp vụ.
}
```

Trích đoạn này cần `import java.nio.file.Files;`, `import java.nio.file.FileAlreadyExistsException;`, và `Path path` phù hợp; trong phương thức thực tế còn cần xử lý `IOException`.

Đối với dữ liệu trong database, “SELECT để xem mã có tồn tại không, sau đó INSERT” có cùng khoảng đua. Một khóa `synchronized` ở **một JVM** không thể ngăn một ứng dụng hoặc JVM khác chèn cùng mã. Bất biến cần được thực thi tại nơi sở hữu dữ liệu bằng unique constraint, transaction, hoặc thao tác upsert/conditional write có tính nguyên tử theo hợp đồng hệ thống đó. Đây là nguyên tắc phối hợp xuyên tiến trình, không yêu cầu dùng framework Java cụ thể.

## 9. Các giải pháp tưởng đúng nhưng chưa đủ

**Thêm `volatile` cho một cờ kiểm tra rồi đặt cờ:**

```java
// Chỉ minh họa ý tưởng; 'initialized' là một biến volatile.
if (!initialized) {
    initialized = true;
    initialize();
}
```

Hai thread vẫn có thể cùng đọc `false` rồi cùng chạy `initialize()`; `volatile` chỉ cung cấp quy tắc hiển thị/thứ tự cho truy cập cờ, **không gộp check và act**. Thậm chí nếu cờ đã thành `true` trước khi `initialize()` hoàn tất, thread khác có thể lầm tưởng đối tượng đã sẵn sàng. Cần cơ chế khởi tạo đúng hợp đồng, chẳng hạn synchronization, holder idiom hoặc công cụ concurrent phù hợp.

**Dùng `Thread.sleep()` để “giảm xác suất” race:** thay đổi lịch chạy chỉ có thể che lỗi; không bảo đảm kết quả đúng. Race có thể xuất hiện trở lại khi tải tăng, chạy trên máy khác hoặc JVM lập lịch khác.

**Chỉ khóa một đoạn:** nếu code khóa khi ghi nhưng bước kiểm tra ở ngoài, giữa hai bước vẫn có khoảng đua. Cần bảo vệ toàn bộ `if (condition) update()` khi điều kiện và cập nhật phụ thuộc nhau.

**Khóa ở hai nơi khác nhau:** `synchronized(lockA)` không ngăn thread khác đi vào `synchronized(lockB)`. Các thao tác trên một bất biến phải cùng tuân thủ một giao thức đồng bộ rõ ràng.

**Đưa tác dụng phụ vào phép thử lại CAS:** nếu phép tính bị thực hiện nhiều lần khi tranh chấp, các tác dụng phụ như gửi yêu cầu HTTP, ghi log nghiệp vụ, tạo đơn hàng có thể lặp. Hãy tách việc quyết định thành công của cập nhật trạng thái với việc thực hiện tác dụng phụ, và thiết kế idempotency hoặc giao dịch nếu cần độ tin cậy xuyên hệ thống.

**Chỉ kiểm tra kích thước map cuối:** kích thước bằng 1 không chứng minh chỉ một lần khởi tạo như ví dụ đầu; cần đo cả số lần tạo hoặc tác dụng phụ quan trọng.

## 10. Kiểm thử và chẩn đoán race condition

Race phụ thuộc lịch thực thi; việc chạy thử “một nghìn lần không lỗi” không chứng minh logic đúng. Cách kiểm thử hiệu quả là:

1. **Xác định bất biến** phải được giữ: số lượng không âm, một key có một giá trị khởi tạo, hoặc số lần thực hiện tác dụng phụ được phép.
2. **Điều khiển lịch chạy tại điểm nguy hiểm** bằng `CountDownLatch`, `CyclicBarrier` hoặc cơ chế phối hợp rõ ràng. Ví dụ đầu cố ý buộc cả hai thread nhìn thấy giá trị thiếu trước khi cho ghi.
3. **Chờ hoàn tất** bằng `join()` hay một primitive phù hợp, rồi kiểm tra bất biến và số lần tác dụng phụ xảy ra. Đừng dựa vào `sleep()` để giả định worker đã xong.
4. **Thử tải và nhiều lịch chạy** để bổ trợ, không thay thế phân tích tính nguyên tử. Sử dụng thread dump/profiler khi nghi có lock contention hoặc deadlock.
5. **Kiểm tra tất cả đường cập nhật**, kể cả code khác gọi trực tiếp setter, cập nhật map, xóa key hoặc sửa trường ngoài khóa.

Khi mô tả lỗi, hãy ghi rõ: trạng thái ban đầu, hai phép kiểm tra độc lập, thời điểm xen kẽ, bất biến bị vi phạm, và **điểm nguyên tử** mà cách sửa cung cấp. Đây là bằng chứng rõ hơn việc chỉ nói “thêm synchronized sẽ hết lỗi”.

## 11. Tự kiểm tra kiến thức

1. **Vì sao `ConcurrentHashMap.get()` và `put()` đều an toàn mà đoạn `if (get == null) put` vẫn lỗi?** Vì cặp thao tác riêng rẽ không nguyên tử: giá trị có thể đổi giữa lúc đọc và lúc ghi.
2. **`volatile` sửa được check-then-act không?** Không, nếu phải kết hợp nhiều bước; nó không tự tạo một giao dịch nguyên tử.
3. **Có phải `AtomicInteger.incrementAndGet()` luôn đủ khi yêu cầu “chỉ tăng nếu còn dưới giới hạn”?** Không; phải thực hiện kiểm tra điều kiện và cập nhật trong một cơ chế nguyên tử như CAS loop hoặc khóa.
4. **Vì sao `computeIfAbsent()` thường phù hợp hơn `putIfAbsent(key, expensiveCreate())` cho lazy initialization?** Vì `expensiveCreate()` được tính trước lời gọi `putIfAbsent`, còn hàm mapping của `ConcurrentHashMap.computeIfAbsent` được phối hợp trong thao tác nguyên tử.
5. **Khi cập nhật hai trường có chung bất biến, một `AtomicInteger` bảo vệ được cả hai không?** Không; cần biểu diễn trạng thái nguyên tử thích hợp hoặc bảo vệ cùng một vùng cập nhật bằng khóa/chế độ phối hợp chung.
6. **Một khóa Java có ngăn JVM khác tạo trùng file hoặc bản ghi database không?** Không. Bất biến phải được bảo đảm bởi thao tác nguyên tử/ràng buộc của tài nguyên chung.
7. **Vì sao kết quả cuối cache có một phần tử chưa đủ chứng minh chương trình đúng?** Vì hai lần tạo/ghi vẫn có thể xảy ra, gây tác dụng phụ thừa trước khi map chỉ giữ lại một giá trị.

**Ghi nhớ:** check-then-act chỉ đúng khi **điều kiện và hành động phụ thuộc điều kiện được bảo vệ trong cùng một thao tác nguyên tử** theo phạm vi sở hữu dữ liệu. Chọn API atomic cho một biến, thao tác nguyên tử của concurrent collection cho một key, khóa nhất quán cho nhiều trường, và cơ chế nguyên tử của hệ thống ngoài JVM khi tài nguyên nằm bên ngoài tiến trình.
