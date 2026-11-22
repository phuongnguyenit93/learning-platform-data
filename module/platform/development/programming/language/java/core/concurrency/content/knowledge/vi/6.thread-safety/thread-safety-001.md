# Thế nào là một class thread-safe?

Một **class thread-safe** (lớp an toàn luồng) là lớp có các đối tượng vẫn thực hiện **đúng hợp đồng đã công bố** khi nhiều thread truy cập đồng thời, với mọi cách xen kẽ thực thi hợp lệ, mà người gọi **không phải tự thêm đồng bộ hóa bên ngoài** cho những thao tác được lớp cam kết an toàn.

Điều kiện “đúng” không chỉ là không ném exception: dữ liệu phải giữ được bất biến, những cập nhật không được mất, và các kết quả phải tuân theo quy tắc hiển thị bộ nhớ của **Java Memory Model (JMM)**. Không nhất thiết mọi thread thấy kết quả theo một thứ tự cố định; hợp đồng có thể cho phép thứ tự không xác định, snapshot nhất quán hoặc trạng thái nhất quán cuối cùng. Điều quan trọng là mọi quan sát vẫn **phù hợp với hợp đồng**.

Ví dụ: một class cho phép tối đa hai lượt đặt chỗ có thể để bất kỳ hai trong ba thread giành được suất. Nhưng bất biến `used <= 2` phải luôn đúng. Nếu đôi khi cả ba đều thành công, class đã vi phạm thread safety.

## 1. Bắt đầu từ trạng thái, bất biến và ranh giới thao tác

Trước khi chọn `synchronized` hay `AtomicInteger`, cần nhận diện:

- **Mutable shared state:** trường nào có thể thay đổi và được nhiều thread dùng? Có biến `static`, object được truyền vào, collection hay dependency bên ngoài?
- **Invariant:** những quan hệ nào phải luôn đúng? Ví dụ `0 <= used <= limit` hoặc `available + reserved == total`.
- **Atomic operation:** thao tác nào phải thực hiện như một đơn vị không thể chen ngang về mặt logic? “Kiểm tra còn suất rồi đặt” là một thao tác, dù mã có nhiều câu lệnh.
- **Publication:** đối tượng và kết quả được công bố cho thread khác bằng cách nào? Việc xây dựng hoàn tất chưa, có quan hệ *happens-before* hợp lệ chưa?
- **Encapsulation:** caller có thể lấy tham chiếu tới collection/array mutable nội bộ và sửa ngoài vùng bảo vệ không?

Class an toàn cần giữ đúng bất biến **trên tất cả đường đọc/ghi có liên quan**, bao gồm public method, callback, thao tác khởi tạo và đối tượng được chia sẻ cho bên ngoài.

| Hiện tượng | Vì sao nguy hiểm? |
|---|---|
| *Lost update* | Hai thread cùng đọc giá trị cũ và cùng ghi, làm mất một lượt cập nhật. |
| *Check-then-act race* | Hai thread thấy cùng điều kiện đúng rồi cùng thực hiện hành động chỉ cho phép một lần. |
| *Stale read* | Thread đọc dữ liệu mà không có quan hệ đồng bộ bảo đảm thấy cập nhật cần thiết. |
| *Inconsistent snapshot* | Đọc nhiều trường giữa lúc thread khác đang cập nhật, tạo tổ hợp không hợp lệ. |
| *Representation exposure* | Caller được sửa trực tiếp state nội bộ, vượt qua khóa/bất biến của class. |

**Thread-safe không phải một modifier đặc biệt.** `final`, `volatile` hoặc `synchronized` trên vài thành phần chưa đủ để chứng minh toàn bộ class an toàn.

## 2. Những chiến lược chính

### Stateless: không có mutable state chia sẻ

```java
public final class StatelessFormatter {
    public String greet(String name) {
        return "Hello, " + name.trim();
    }
}
```

Đây là class hợp lệ nhưng chỉ là đoạn minh họa (không có `main`). Mỗi lần gọi sử dụng tham số và biến tạm trên stack của lần gọi. `String` immutable; class không giữ field thay đổi. Nhiều thread có thể gọi `greet` đồng thời.

**Ngoại lệ:** “không có field instance” chưa đủ nếu phương thức bí mật dùng một `static HashMap` mutable, bộ đếm toàn cục hoặc dependency không an toàn. Stateless thật sự phải không phụ thuộc vào shared mutable state thiếu phối hợp.

### Immutable: trạng thái không thể bị sửa sau construction

Immutable object thường là lựa chọn rất mạnh để chia sẻ: dữ liệu được xây dựng hoàn chỉnh, không có setter hoặc đường tham chiếu cho phép sửa sâu, và được công bố theo quy tắc JMM. `final` trên một field tham chiếu chỉ cố định **tham chiếu**, không làm đối tượng đằng sau nó bất biến.

Một `record` có `List<String>` chưa tự trở thành immutable nếu giữ nguyên một `ArrayList` caller truyền vào. Cần sao chép phòng vệ, và nếu phần tử mutable thì còn cần sao chép/thiết kế sâu hơn. Ví dụ chạy được ở mục 5.

### Mutable nhưng được phối hợp đúng

Một mutable class vẫn có thể thread-safe nếu toàn bộ state chung được truy cập theo một giao thức nhất quán, chẳng hạn:

- `synchronized` hoặc `ReentrantLock` bao trùm một vùng găng (*critical section*) bảo vệ invariant;
- `AtomicInteger` / `AtomicReference` / compare-and-set (CAS) để cập nhật trạng thái nguyên tử phù hợp;
- collection concurrent với các phép thao tác nguyên tử **đúng hợp đồng cụ thể**;
- thay toàn bộ immutable snapshot qua một tham chiếu được công bố/cập nhật nguyên tử.

Không có một cơ chế tối ưu cho mọi tình huống; điều cần bảo vệ là **thao tác logic** và những quan sát do API công bố.

## 3. Visibility không đồng nghĩa atomicity: volatile vẫn có thể lỗi

`volatile` cung cấp quy tắc hiển thị/thứ tự đọc ghi cho biến đó. Nhưng `count++` không phải một phép cập nhật nguyên tử; nó gồm đọc, tính, ghi. Nếu hai thread đều đọc `0` rồi cùng ghi `1`, một lần tăng bị mất.

Ví dụ sau dùng latch để buộc hai thread cùng đọc giá trị trước khi ghi, khiến lỗi dễ tái hiện hơn ví dụ chỉ chạy hàng triệu vòng.

Tạo tệp **`VolatileCounterRace.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class VolatileCounterRace {
    static final class Counter {
        private volatile int value;
        private final CountDownLatch bothRead = new CountDownLatch(2);

        void increment() throws InterruptedException {
            int oldValue = value;
            bothRead.countDown();
            bothRead.await();
            value = oldValue + 1;
        }

        int get() {
            return value;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Counter counter = new Counter();
        Runnable task = () -> {
            try {
                counter.increment();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("Expected increments: 2");
        System.out.println("Actual value: " + counter.get());
    }
}
```

```bash
javac VolatileCounterRace.java
java VolatileCounterRace
```

Đầu ra trong lần chạy bình thường, không bị interrupt:

```text
Expected increments: 2
Actual value: 1
```

Hai thread cùng đọc `0` trước khi latch mở; sau đó cả hai ghi `1`. `volatile` không gộp hai bước đọc–sửa–ghi. Latch chỉ phục vụ thí nghiệm để tạo lịch xen kẽ; class `Counter` vẫn không phải bộ đếm thread-safe. Khi chỉ cần tăng một biến, `AtomicInteger.incrementAndGet()` hoặc một vùng `synchronized` phù hợp có thể giải quyết.

## 4. Mutable class an toàn: khóa toàn bộ check-then-act

Giả sử class giới hạn số lượt được cấp: `0 <= used <= limit`. Cần kiểm tra còn suất và tăng used trong cùng một thao tác nguyên tử về mặt logic.

Tạo tệp **`SafeQuota.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class SafeQuota {
    private final int limit;
    private int used;

    public SafeQuota(int limit) {
        if (limit < 0) {
            throw new IllegalArgumentException("limit must be >= 0");
        }
        this.limit = limit;
    }

    public synchronized boolean tryAcquire() {
        if (used >= limit) {
            return false;
        }
        used++;
        return true;
    }

    public synchronized int used() {
        return used;
    }

    public int limit() {
        return limit;
    }

    public static void main(String[] args) throws InterruptedException {
        SafeQuota quota = new SafeQuota(2);
        AtomicInteger accepted = new AtomicInteger();

        Runnable task = () -> {
            if (quota.tryAcquire()) {
                accepted.incrementAndGet();
            }
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);
        Thread c = new Thread(task);
        a.start();
        b.start();
        c.start();
        a.join();
        b.join();
        c.join();

        System.out.println("Accepted: " + accepted.get());
        System.out.println("Used: " + quota.used());
        System.out.println("Limit: " + quota.limit());
    }
}
```

```bash
javac SafeQuota.java
java SafeQuota
```

Kết quả:

```text
Accepted: 2
Used: 2
Limit: 2
```

**Điều tạo ra bảo đảm:** `used` là `private`; mọi đường đọc/ghi `used` sử dụng monitor của cùng đối tượng `quota`. Bên trong `tryAcquire()`, không thread nào có thể chen giữa phép kiểm tra `used >= limit` và `used++`. `used()` cũng sử dụng monitor để đọc trạng thái nhất quán. `limit` không đổi sau constructor và đã được kiểm tra hợp lệ.

Ba thread cạnh tranh nên không bảo đảm thread nào thắng. Tuy nhiên, đúng hai lời gọi nhận `true`. `accepted` là `AtomicInteger` để chương trình demo đếm lượt thành công, và `join()` bảo đảm main chỉ đọc khi cả ba thread hoàn tất.

`synchronized` trong instance method khóa **chính instance đó**. Hai đối tượng `SafeQuota` khác nhau có monitor và trạng thái riêng: chúng không tự phối hợp thành một hạn mức toàn cục. Nếu một invariant là chung của nhiều đối tượng/JVM, phải thiết kế điểm sở hữu/trọng tài chung tương ứng.

## 5. Immutable class và defensive copy

Tạo tệp **`ImmutableSettings.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ImmutableSettings {
    public record Settings(List<String> roles) {
        public Settings {
            roles = List.copyOf(roles);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("reader");

        Settings settings = new Settings(source);
        source.add("writer");

        System.out.println("Roles: " + settings.roles());
        try {
            settings.roles().add("admin");
        } catch (UnsupportedOperationException e) {
            System.out.println("External modification rejected");
        }
    }
}
```

```bash
javac ImmutableSettings.java
java ImmutableSettings
```

Kết quả:

```text
Roles: [reader]
External modification rejected
```

Compact constructor của record thay tham số `roles` bằng danh sách do `List.copyOf` tạo ra. Caller sửa `source` không ảnh hưởng trạng thái record; accessor `roles()` không cung cấp một list có thể thêm phần tử. Vì các phần tử là `String` immutable, dữ liệu có thể được đọc đồng thời an toàn sau khi tạo và công bố đúng cách.

**Đừng tổng quát hóa quá mức:** `List.copyOf` không sao chép sâu phần tử. Với `List<MutableOrder>`, thread khác vẫn có thể sửa trường trong từng `MutableOrder` nếu còn tham chiếu. `Collections.unmodifiableList(original)` chỉ là view không cho sửa qua view; nếu `original` thay đổi, view có thể quan sát thay đổi đó. Immutable phải xét **toàn bộ đồ thị trạng thái có thể truy cập**.

## 6. AtomicInteger: thread-safe cho phép cập nhật đơn

Tạo tệp **`AtomicCounter.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class AtomicCounter {
    private final AtomicInteger count = new AtomicInteger();

    public int increment() {
        return count.incrementAndGet();
    }

    public int value() {
        return count.get();
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicCounter counter = new AtomicCounter();
        Runnable task = () -> {
            for (int i = 0; i < 1000; i++) {
                counter.increment();
            }
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Value: " + counter.value());
    }
}
```

```bash
javac AtomicCounter.java
java AtomicCounter
```

Kết quả:

```text
Value: 2000
```

`incrementAndGet()` là một phép tăng nguyên tử; sau hai lần `join()`, main quan sát đúng 2.000 lần cập nhật. Nhưng mã `if (counter.value() < max) counter.increment()` bên phía caller vẫn **không nguyên tử như một thao tác hợp thành**. Hai thread có thể cùng kiểm tra thành công rồi cùng tăng.

Khi chỉ có một biến chứa toàn bộ invariant, CAS loop với `compareAndSet(old, new)` có thể kết hợp kiểm tra và cập nhật: nếu thread khác đổi giá trị giữa chừng, CAS thất bại và phải **đọc lại, kiểm tra lại điều kiện**. Với `AtomicReference.updateAndGet`, hàm update có thể được gọi lại khi tranh chấp nên phải tránh side effect như gửi dữ liệu, tạo hóa đơn hay thao tác ngoài JVM trong lambda.

## 7. Thread-safe từng method không bảo đảm thao tác của client

Xét class có `get()` và `increment()` đều synchronized. Đoạn phía client dưới đây vẫn sai nếu muốn giới hạn số lần tăng:

```java
// Mã minh họa KHÔNG an toàn; counter/limit được giả định đã khai báo.
if (counter.get() < limit) {
    counter.increment();
}
```

Hai thread có thể đều hoàn thành `get()` và cùng thấy “chưa tới giới hạn” trước khi bất kỳ thread nào gọi `increment()`. Từng method an toàn, nhưng **chuỗi check → act không phải một transaction nguyên tử**. Thiết kế API nên đưa trọn quyết định vào method như `SafeQuota.tryAcquire()`, đồng thời nói rõ những gì class cam kết.

Ví dụ tương tự với concurrent collection:

```java
// Mã minh họa, cache là ConcurrentHashMap<String, String>.
if (!cache.containsKey("key")) {
    cache.put("key", expensiveCreate());
}
```

`containsKey` và `put` đều có bảo đảm thread safety riêng, nhưng hai thread có thể cùng không thấy key rồi cùng gọi `expensiveCreate()`. Trong `ConcurrentHashMap`, `computeIfAbsent(key, mappingFunction)` có hợp đồng nguyên tử phù hợp cho **tính giá trị nếu key chưa có**. Hàm mapping nên ngắn, không tự thay đổi chính map đang tính và không dùng tác dụng phụ không thể lặp lại trong trường hợp ràng buộc nghiệp vụ yêu cầu hơn một thao tác map.

`putIfAbsent(key, expensiveCreate())` cũng cần thận trọng: Java đánh giá `expensiveCreate()` **trước khi** gọi `putIfAbsent`, nên việc tạo tài nguyên có thể lặp dù phép gắn giá trị là nguyên tử.

## 8. Bất biến nhiều field cần một giao thức nhất quán

Giả sử có `available` và `reserved`, bất biến:

```text
available >= 0
reserved >= 0
available + reserved == total
```

Nếu thread giảm `available` trước rồi mới tăng `reserved`, thread khác đọc giữa hai phép gán có thể thấy tổng sai. Dùng hai `AtomicInteger` cho hai field **không tự tạo một snapshot nguyên tử cho cả hai**.

Một giải pháp đơn giản là bảo vệ mọi cập nhật và phép đọc trạng thái ghép bằng cùng monitor:

```java
// Trích đoạn method trong một class, không độc lập.
private int available = 10;
private int reserved;

public synchronized boolean reserve() {
    if (available == 0) {
        return false;
    }
    available--;
    reserved++;
    return true;
}

public synchronized String snapshot() {
    return "available=" + available + ", reserved=" + reserved;
}
```

`snapshot()` và `reserve()` dùng cùng khóa instance, nên không thể quan sát trạng thái đang cập nhật dở. Một phương án khác là đóng gói **tất cả** trường liên quan vào một object immutable rồi cập nhật toàn bộ tham chiếu qua `AtomicReference.compareAndSet` (thay cả snapshot tại một thời điểm). Chọn cách phù hợp độ phức tạp và tải thực tế.

Với `ReentrantLock`, luôn giải phóng khóa trong `finally`:

```java
lock.lock();
try {
    // Kiểm tra và cập nhật cùng invariant dưới một lock.
} finally {
    lock.unlock();
}
```

Đây là trích đoạn minh họa, giả định `lock` là một `ReentrantLock` đã khởi tạo. Hai thao tác bảo vệ bằng **hai khóa khác nhau** không loại trừ nhau. Không gọi code ngoài không kiểm soát hoặc làm I/O lâu trong vùng khóa nếu không cần thiết: việc giữ khóa có thể làm tăng contention hoặc deadlock.

## 9. Safe publication theo Java Memory Model

Bản thân object được xây dựng đúng vẫn cần được **công bố** cho thread khác qua một đường có bảo đảm bộ nhớ phù hợp. Các cơ chế thường gặp:

- Khởi tạo static của class theo hợp đồng JVM;
- ghi/đọc `volatile` hoặc `AtomicReference`;
- giải phóng/chiếm lại cùng monitor hoặc lock;
- truyền object cho thread mới sau khi đã tạo hoàn chỉnh: các thao tác trước `Thread.start()` happens-before các thao tác bên trong thread mới;
- trao đổi qua cấu trúc concurrent có hợp đồng đồng bộ như `BlockingQueue`.

Các trường `final` còn có bảo đảm khởi tạo đặc biệt khi object **được xây dựng đúng cách**. Tránh để `this` thoát khỏi constructor:

```java
// Đoạn minh họa NGUY HIỂM trong constructor.
public SomeClass() {
    new Thread(() -> useFieldsOfThis()).start();
    importantField = 42;
}
```

Worker có thể truy cập `importantField` trước khi constructor gán giá trị. Quan hệ từ `start()` chỉ bao trùm những hành động **trước** lời gọi start, không bảo vệ phép gán sau đó. Hãy xây dựng đầy đủ object trước khi công bố và khởi động thread dùng nó.

Đừng hiểu `final` trên một tham chiếu là “mọi dữ liệu phía sau tham chiếu đều bất biến”; `volatile` trên tham chiếu cũng không làm các thay đổi sâu trong object thành một phép cập nhật nguyên tử.

## 10. Encapsulation: không lộ collection mutable

Một thiết kế nhìn như dùng khóa đầy đủ có thể bị phá vỡ bằng getter trả về tham chiếu mutable thật:

```java
// Trích đoạn minh họa KHÔNG an toàn.
private final List<String> tasks = new ArrayList<>();

public List<String> tasks() {
    return tasks; // Caller có thể tự add/remove không theo giao thức khóa.
}
```

Nếu muốn xuất một snapshot độc lập khi mọi mutation đang được bảo vệ bằng monitor instance, có thể làm:

```java
public synchronized List<String> tasksSnapshot() {
    return List.copyOf(tasks);
}
```

Hai trích đoạn này cần import `java.util.List` và `java.util.ArrayList`; ví dụ chỉ dùng phần tử `String` immutable. Nếu phần tử mutable thì còn phải tránh lộ tham chiếu tới chính phần tử đó.

Tương tự, `Collections.synchronizedList` đồng bộ các method riêng nhưng một **lượt duyệt/iteration** cần được phối hợp theo hợp đồng collection. `CopyOnWriteArrayList` lại có iterator snapshot, đổi chi phí ghi để có lượt duyệt ổn định. Đừng suy một cách chung chung rằng “mọi thao tác trên mọi concurrent collection đều nguyên tử như một giao dịch”.

## 11. Phân biệt các thuộc tính concurrency

| Thuộc tính | Ý nghĩa | Điều cần nhớ |
|---|---|---|
| **Thread safety** | Truy cập concurrent vẫn đúng contract và invariant. | Mục tiêu tổng thể của class. |
| Atomicity | Một thao tác không bị xen ngang theo nghĩa logic được cam kết. | Cần cho phép cập nhật nhiều bước. |
| Visibility | Thread khác thấy hiệu ứng bộ nhớ theo JMM. | Cần nhưng chưa đủ cho check-then-act. |
| Immutability | Không sửa được trạng thái sau khi tạo. | Một chiến lược chia sẻ an toàn khi xây dựng/công bố đúng. |
| Linearizability | Mỗi thao tác có thể coi như xảy ra tại một điểm giữa lời gọi và trả về. | Hợp đồng mạnh hữu ích, nhưng không bắt buộc mọi API concurrent đều có. |
| Liveness | Hệ thống/thread có tiến triển, tránh chờ vô hạn. | Khác với safety; khóa có thể bảo vệ dữ liệu nhưng gây deadlock. |
| Lock-free | Hợp đồng tiến triển không phụ thuộc một khóa loại trừ truyền thống. | Không phải từ đồng nghĩa của thread-safe. |
| Reentrancy | Có thể gọi vào lại hàm trong những điều kiện nhất định. | Không mặc nhiên chứng minh an toàn dữ liệu shared. |

Một class có thể thread-safe mà **thứ tự kết quả không cố định**; ví dụ không biết thread nào lấy được suất, nhưng không ai được vượt hạn mức. Ngược lại, code có lịch chạy luôn giống nhau trong vài phép thử vẫn có thể race khi tải hoặc lịch chạy thay đổi.

## 12. Những lỗi khiến class không an toàn dù “có khóa”

1. Khóa setter nhưng getter đọc field không đồng bộ.
2. Mỗi method dùng một object khóa khác nhau; `synchronized(new Object())` mỗi lần gọi không phối hợp giữa các thread.
3. Tách kiểm tra và cập nhật thành hai public method cho caller tự ghép.
4. Trả mutable list/array/map nội bộ cho caller; caller sửa ngoài khóa.
5. Để `this` thoát trong constructor trước khi state hoàn chỉnh.
6. Cho phép subclass override các method bảo vệ invariant mà không xác định rõ contract kế thừa.
7. Gọi callback không kiểm soát khi đang giữ khóa, có thể tạo vòng phụ thuộc khóa.
8. Giả định `volatile` làm nguyên tử nhiều field hoặc `AtomicInteger` bảo vệ cả một transaction nhiều trạng thái.
9. Nghĩ mọi dependency cũng thread-safe chỉ vì lớp bao bên ngoài có khóa.
10. Dựa vào thứ tự `Thread.start()` hoặc `Thread.sleep()` để giả định kết quả theo một thứ tự cố định.

Đối với class có `static` shared mutable state, hãy xét thêm **phạm vi nhiều instance**. Hai instance của class có hai monitor `this` khác nhau; chúng không bảo vệ được cùng một trường `static` nếu chỉ khóa theo instance. Dùng một chiến lược thích hợp cho state thực sự chung hoặc loại bỏ shared global state.

## 13. Quy trình thiết kế và kiểm thử class thread-safe

**Thiết kế:** trước hết ghi ra invariant và những method public cam kết. Xác định state mutable, ai có thể giữ alias và mọi đường đọc/ghi. Nếu có thể, ưu tiên stateless hoặc immutable. Nếu phải mutable, chọn một cơ chế bảo vệ tương ứng phạm vi invariant. Đưa trọn quyết định nghiệp vụ vào một method như `tryAcquire()`, bảo vệ cả đọc/ghi liên quan, công bố object theo JMM và nói rõ semantics của API khi concurrent.

**Kiểm thử:** xây dựng những lịch xen kẽ có chủ đích bằng `CountDownLatch` hoặc `CyclicBarrier`, chờ mọi worker bằng `join()` hay primitive thích hợp rồi kiểm tra invariant và số tác dụng phụ. Lặp dưới tải khác nhau để tăng độ bao phủ. Một test chạy hàng nghìn lần không thấy lỗi **không thể tự chứng minh** class thread-safe; kết luận dựa vào cả thiết kế/happens-before và chứng cứ kiểm thử.

Đừng dùng `Thread.sleep()` để tự “chứng minh” hai công việc đã xong hay giả định race không thể xảy ra. Nếu nghi deadlock hoặc contention, xem thread dump và phân tích lock acquisition. Một class có safety vẫn có thể gặp vấn đề liveness; cần đánh giá thời hạn chờ, interrupt/cancellation và thứ tự chiếm khóa.

**Giới hạn phạm vi:** một monitor trong một JVM không khóa được file hay database đang được JVM khác ghi. Bất biến xuyên tiến trình cần thao tác nguyên tử, transaction hoặc unique constraint của hệ thống sở hữu tài nguyên đó. Việc đồng bộ đúng trong Java chỉ là một phần nếu dữ liệu còn được sửa bên ngoài tiến trình.

## 14. Câu hỏi tự kiểm tra

1. **`private volatile int count` với `count++` có thread-safe không?** Không. `volatile` không biến đọc–sửa–ghi thành nguyên tử.
2. **Vì sao `SafeQuota.tryAcquire()` an toàn?** Vì kiểm tra và tăng `used` được thực hiện dưới cùng monitor; mọi đường truy cập `used` cần tuân thủ giao thức đó.
3. **Nếu hai method đều synchronized, việc gọi `get()` rồi `increment()` có nguyên tử không?** Không. Thread khác có thể chen giữa hai lần gọi.
4. **Class không có field instance có chắc an toàn không?** Không, nếu nó sử dụng static mutable state hoặc dependency không an toàn.
5. **`final List<String>` có luôn immutable không?** Không; danh sách phía sau tham chiếu vẫn có thể mutable hoặc bị thay đổi qua alias khác.
6. **`List.copyOf` có sao chép sâu object trong danh sách không?** Không. Với phần tử mutable cần chiến lược thêm.
7. **Hai `AtomicInteger` có tự bảo vệ invariant liên quan cả hai trường không?** Không; từng phép cập nhật nguyên tử nhưng toàn bộ trạng thái ghép chưa chắc nhất quán.
8. **Một class thread-safe có thể deadlock không?** Có. Safety về dữ liệu và liveness là hai thuộc tính khác nhau.
9. **`ConcurrentHashMap` có biến mọi đoạn nhiều lời gọi lên map thành transaction không?** Không; cần chọn thao tác nguyên tử theo hợp đồng, chẳng hạn `computeIfAbsent` cho trường hợp thích hợp.
10. **Khi nào caller phải dùng khóa ngoài một class?** Khi cần phối hợp một chuỗi thao tác vượt phạm vi atomicity mà class cam kết và hợp đồng có cách hỗ trợ; tốt hơn nên cân nhắc API hợp thành có bảo vệ invariant ngay trong class.

**Ghi nhớ:** class thread-safe **giữ đúng hợp đồng khi nhiều thread truy cập đồng thời**. Hãy xác định trạng thái và invariant, bảo vệ toàn bộ thao tác logic, đóng gói mutable state, công bố dữ liệu an toàn theo JMM, và phân biệt tính an toàn của *mỗi method* với tính nguyên tử của *chuỗi thao tác do caller tự ghép*.
