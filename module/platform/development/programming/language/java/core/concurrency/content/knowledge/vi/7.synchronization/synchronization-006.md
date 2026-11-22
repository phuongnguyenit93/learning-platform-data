# Thiết kế critical section đủ nhỏ và dễ kiểm chứng trong Java

> **Mục tiêu:** Nhận diện chính xác dữ liệu và invariant cần bảo vệ; thiết kế một critical section đủ **lớn để đúng**, nhưng đủ **nhỏ để giảm tranh chấp và dễ kiểm chứng**; biết chuyển các thao tác độc lập ra ngoài khóa, tránh gọi code không kiểm soát khi đang giữ lock, và giữ các thay đổi cần nguyên tử trong cùng một ranh giới đồng bộ.

Bài thuộc nhóm **Synchronization** của Java concurrency nói chung. Các ví dụ dùng Java SE 17+ với `synchronized`, `ReentrantLock` và một số công cụ `java.util.concurrent`. Không dùng cơ chế của Spring.

## 1. Critical section là gì?

Một **critical section** là đoạn mã cần được thực thi theo một cơ chế phối hợp nhằm bảo vệ dữ liệu hoặc invariant mà nhiều thread có thể cùng truy cập. Với mutual exclusion bằng một lock, tại một thời điểm chỉ một thread được ở trong những critical section dùng **cùng lock ấy**.

Ví dụ đơn giản:

~~~java
// Minh họa, không phải chương trình độc lập.
private final Object lock = new Object();
private int count;

void increment() {
    synchronized (lock) {
        count++;
    }
}
~~~

`count++` là read-modify-write, gồm đọc giá trị cũ, cộng và ghi. Khi các thread đều thực hiện cập nhật qua **cùng `lock`**, toàn bộ cập nhật này nằm trong vùng loại trừ lẫn nhau. Khóa giúp chống lost update; đồng thời `unlock` và `lock` tiếp theo trên cùng monitor còn tạo quan hệ *happens-before* để quan sát dữ liệu.

Đừng đồng nhất “critical section nhỏ” với “có ít dòng mã”. Một khối một dòng có thể chứa lệnh I/O rất lâu hoặc callback gọi ngược vào hệ thống. Ngược lại, một khối có nhiều dòng kiểm tra và cập nhật có thể là **đơn vị atomic nhỏ nhất đúng với invariant**.

### Ba tiêu chí để đánh giá

1. **Correctness:** Không có thread khác chen giữa những bước cần cùng một invariant; mọi đường truy cập state dùng cùng protocol đồng bộ.
2. **Reviewability:** Người đọc nhìn vào đoạn mã biết ngay object nào được khóa, state nào được bảo vệ và trạng thái hợp lệ trước/sau đoạn mã.
3. **Contention:** Khóa được giữ trong thời gian hợp lý; mã tốn thời gian hoặc không phụ thuộc vào state được đưa ra ngoài nếu việc đó **không phá invariant**.

Thứ tự ưu tiên là **đúng trước, đơn giản dễ kiểm chứng sau, rồi mới tối ưu contention dựa trên đo lường**. Thu hẹp khóa bằng cách tách đôi một thao tác phải atomic làm chương trình nhanh hơn trên benchmark đôi khi, nhưng không còn đúng.

## 2. Bắt đầu từ invariant, không bắt đầu từ dòng `synchronized`

Một **invariant** là điều kiện phải luôn đúng ở những điểm các thread khác được phép quan sát state. Chẳng hạn kho hàng:

- `available >= 0`: tồn kho không âm.
- Chỉ duyệt tối đa số sản phẩm còn có thể đặt.
- Một đơn hàng chỉ được chấp nhận nếu kiểm tra và trừ tồn kho thuộc **cùng một lần quyết định**.

Cách tổ chức sai (minh họa):

~~~java
if (inventory.available() > 0) { // Đọc có khóa hoặc atomic.
    inventory.decrement();        // Ghi có khóa hoặc atomic riêng.
}
~~~

Ngay cả khi mỗi method tự synchronized, một thread khác có thể lấy sản phẩm cuối **giữa hai lời gọi**. Kiểm tra-để-rồi-hành-động (*check-then-act*) là compound action; đúng hay sai phụ thuộc cả ranh giới của hai bước.

Thiết kế tốt hơn là đưa **điều kiện và chuyển trạng thái** vào cùng một method:

~~~java
boolean reserveOne() {
    synchronized (lock) {
        if (available == 0) {
            return false;
        }
        available--;
        return true;
    }
}
~~~

Đây là một critical section đủ nhỏ: trong lock chỉ làm điều thực sự phụ thuộc vào `available`; method trả boolean thay vì buộc caller tự kiểm tra rồi cập nhật ở hai thời điểm.

### Định nghĩa ownership ngay ở API

Tốt hơn nên để shared state là `private`, không cung cấp setter/getter tùy ý phá quy tắc đồng bộ. API như `reserveOne()`, `snapshot()`, `transfer()` hoặc `submit(...)` nói rõ **một thao tác nghiệp vụ nguyên tử**.

Một getter trả `available` có thể hợp lệ để hiển thị thống kê, nhưng không nên dùng giá trị đó làm giấy phép thực hiện một cập nhật ở thời điểm sau. Giá trị getter là snapshot đã có thể cũ ngay khi ra khỏi lock.

## 3. Ví dụ 1 — test được tính đúng của vùng kiểm tra và giảm tồn kho

Tạo `InventoryDemo.java` (Java 17+):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class InventoryDemo {
    private static final class Inventory {
        private final Object lock = new Object();
        private int available = 1;

        boolean reserveOne() {
            synchronized (lock) {
                if (available == 0) {
                    return false;
                }
                available--;
                return true;
            }
        }

        int remaining() {
            synchronized (lock) {
                return available;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Inventory inventory = new Inventory();
        AtomicInteger approved = new AtomicInteger();
        CountDownLatch start = new CountDownLatch(1);

        Runnable task = () -> {
            try {
                start.await();
                if (inventory.reserveOne()) {
                    approved.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(task, "a");
        Thread b = new Thread(task, "b");
        a.start();
        b.start();
        start.countDown();
        a.join();
        b.join();

        System.out.println("approved = " + approved.get());
        System.out.println("remaining = " + inventory.remaining());
    }
}
~~~

Chạy:

~~~bash
javac InventoryDemo.java
java InventoryDemo
~~~

Stdout khi không bị ngắt bên ngoài:

~~~text
approved = 1
remaining = 0
~~~

Hai thread cùng có thể cạnh tranh ở `reserveOne()`, nhưng **chỉ một thread** được đi qua phần kiểm tra/cập nhật tại một thời điểm. Với `available = 1`, người vào lock trước giảm về `0`; người còn lại nhận `false`. Kết quả luôn duyệt đúng một lần.

`CountDownLatch` chỉ giúp hai task bắt đầu gần nhau để minh họa tranh chấp; tính đúng đến từ monitor, không đến từ việc các thread có chạy cùng lúc hay không. `approved` dùng `AtomicInteger` để kết quả của hai thread không tạo một race thứ hai trong ví dụ.

**Ranh giới cần nhớ:** Không đưa `available == 0` ra ngoài lock rồi chỉ khóa `available--`. Điều kiện và state transition thuộc **cùng một quyết định atomic**.

## 4. Quy trình xác định ranh giới của critical section

Trước khi thêm `synchronized` hay `lock.lock()`, hãy lập một “bản đồ state”:

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Dữ liệu nào được chia sẻ? | Các field mutable, reference, collection, object graph mà nhiều thread chạm tới |
| Invariant là gì? | Ví dụ số dư không âm, mỗi ID duy nhất, tổng hai tài khoản bảo toàn |
| Thao tác nào đọc state để quyết định ghi? | Check-then-act, read-modify-write, lặp qua cấu trúc rồi cập nhật |
| Ai được quyền sửa? | Một writer, nhiều writer, hay chuyển quyền sở hữu state |
| Cần atomicity đến đâu? | Một biến, một bản ghi, một nhóm field hay nhiều object |
| Khóa nào sở hữu invariant? | Một private monitor/`ReentrantLock` thống nhất; có thứ tự nếu nhiều khóa |
| Điều gì có thể làm ngoài lock? | Tính toán độc lập, parse input, tạo immutable object, I/O hoặc thông báo không cần giữ invariant |
| Việc gì không thể tách? | Kiểm tra state hiện tại và cập nhật dựa vào nó; đọc nhiều field thành một snapshot nhất quán |

### Phân loại thao tác theo *dependency*

**Independent work** là công việc dùng input cục bộ/bất biến và không cần state đang được bảo vệ. Ví dụ parse một chuỗi request, kiểm tra định dạng, tạo một immutable DTO. Thường có thể thực hiện trước lock.

**State-dependent work** cần đọc shared state để đưa ra quyết định, như “nếu đủ tiền thì trừ tiền” hoặc “nếu key chưa tồn tại thì insert”. Phải thực hiện dưới lock, hoặc dùng primitive atomic chuyên dụng.

**External side effect** là I/O, gửi message, log network, callback, hoặc gọi API tùy độ trễ. Thường nên nằm **sau khi thả lock**, nhưng phải thiết kế rõ state transition và thất bại ở bước này. Không thể cứ dời side effect ra ngoài rồi mặc định nghiệp vụ vẫn nguyên tử.

## 5. Ví dụ 2 — tính toán độc lập bên ngoài, commit ngắn bên trong

Tạo `ShortCriticalSectionDemo.java` (Java 17+):

~~~java
public class ShortCriticalSectionDemo {
    private static final class Total {
        private final Object lock = new Object();
        private long cents;

        void addTextAmount(String input) {
            // Đọc, parse và validate input bất biến ở ngoài lock.
            long delta = Long.parseLong(input);
            if (delta <= 0) {
                throw new IllegalArgumentException("positive amount required");
            }

            // Chỉ cập nhật state chia sẻ khi đã có delta hợp lệ.
            synchronized (lock) {
                cents = Math.addExact(cents, delta);
            }
        }

        long snapshot() {
            synchronized (lock) {
                return cents;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Total total = new Total();
        Runnable work = () -> {
            for (int i = 0; i < 1_000; i++) {
                total.addTextAmount("1");
            }
        };

        Thread a = new Thread(work);
        Thread b = new Thread(work);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("total = " + total.snapshot());
    }
}
~~~

Chạy:

~~~bash
javac ShortCriticalSectionDemo.java
java ShortCriticalSectionDemo
~~~

Stdout:

~~~text
total = 2000
~~~

Ở ví dụ, `Long.parseLong(input)` và kiểm tra `delta` không phụ thuộc shared `cents` nên có thể làm ngoài lock. Nhưng **đọc `cents`, cộng và ghi lại** phải cùng critical section. `Math.addExact` ném `ArithmeticException` khi overflow, và do RHS được đánh giá trước phép gán nên một lần overflow sẽ không gán giá trị tràn vào `cents`.

**Cẩn thận:** Nếu tính toán bên ngoài dựa trên `cents` đã đọc trước đó, kết quả có thể bị lỗi stale snapshot. Chỉ tách những phần **thực sự độc lập**. Nếu phải tính ngoài lock từ snapshot rồi commit, cần kiểm tra lại version/CAS hoặc một protocol optimistic rõ ràng (xem phần 10).

## 6. Vùng khóa nhỏ không được phá invariant nhiều field

Giả sử một ledger có `total` và `version`. Invariant nghiệp vụ là **mỗi lần tăng total thành công phải tăng version đúng một lần**. Đây là code sai:

~~~java
// Sai: hai cập nhật không được bảo vệ như một tổ hợp.
synchronized (lock) {
    total += delta;
}
// Một reader có thể chen vào giữa.
synchronized (lock) {
    version++;
}
~~~

Dù mỗi phần riêng lẻ nằm trong lock, người đọc `total` và `version` có thể nhận một snapshot thuộc **hai phiên bản khác nhau** nếu nó lấy lock ở giữa. Bảo vệ một method cập nhật và một method snapshot:

~~~java
void add(long delta) {
    synchronized (lock) {
        total += delta;
        version++;
    }
}

Snapshot snapshot() {
    synchronized (lock) {
        return new Snapshot(total, version);
    }
}
~~~

Khóa phải bao cả các field cần nhất quán. Reader cũng phải lấy **cùng lock** khi đọc snapshot; nếu chỉ writer khóa còn reader đọc trần, vẫn có thể sai.

### Ví dụ 3 — snapshot nhất quán từ nhiều field

Tạo `ConsistentSnapshotDemo.java`:

~~~java
public class ConsistentSnapshotDemo {
    private record Snapshot(long total, long version) {}

    private static final class Ledger {
        private final Object lock = new Object();
        private long total;
        private long version;

        void addOne() {
            synchronized (lock) {
                total++;
                version++;
            }
        }

        Snapshot snapshot() {
            synchronized (lock) {
                return new Snapshot(total, version);
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Ledger ledger = new Ledger();

        Runnable work = () -> {
            for (int i = 0; i < 10_000; i++) {
                ledger.addOne();
            }
        };

        Thread first = new Thread(work);
        Thread second = new Thread(work);
        first.start();
        second.start();
        first.join();
        second.join();

        Snapshot result = ledger.snapshot();
        System.out.println("total = " + result.total());
        System.out.println("version = " + result.version());
        System.out.println("consistent = "
                + (result.total() == result.version()));
    }
}
~~~

Chạy:

~~~bash
javac ConsistentSnapshotDemo.java
java ConsistentSnapshotDemo
~~~

Stdout:

~~~text
total = 20000
version = 20000
consistent = true
~~~

`snapshot()` trả về một immutable record tạo **trong critical section**, nên cặp field thể hiện một trạng thái nhất quán của ledger. Người gọi có thể xử lý snapshot ngoài lock mà không cần tiếp tục giữ monitor, vì đây là dữ liệu bất biến gồm hai số.

Không nên trả trực tiếp một mutable internal object cho caller rồi tuyên bố snapshot thread-safe; khi state còn được mutate bởi worker khác, caller cần bản copy hoặc giao thức đồng bộ tương ứng.

## 7. Giảm thời gian giữ lock bằng cách không thực hiện I/O dưới lock

Các thao tác có thời gian khó dự báo thường không nên được đặt dưới một khóa dữ liệu chung:

- Đọc/ghi file, database hoặc mạng.
- Gọi HTTP, RPC, queue client hay dịch vụ bên ngoài.
- Ghi log tới logger đồng bộ hoặc sink có thể chờ I/O.
- `Thread.sleep`, đợi `Future.get`, `BlockingQueue.take`, chờ latch khi các thread khác cần cùng lock để hoàn thành.
- Tính toán rất nặng nhưng không cần state mutable được bảo vệ.
- Gọi code của plugin, callback, listener hoặc method override mà ta không kiểm soát.

Nếu thread A giữ lock khi chờ I/O, các thread B/C cần lock phải đợi cả thời gian I/O, dù thao tác bảo vệ state chỉ cần vài micro/millisecond. Vấn đề còn nghiêm trọng hơn nếu I/O phụ thuộc một worker đang cố lấy chính lock ấy: ta có thể tự tạo deadlock.

Mẫu khuyến nghị:

~~~text
1. Xử lý input độc lập ở ngoài lock
2. Lấy lock
3. Kiểm tra invariant hiện tại và chuyển state tối thiểu
4. Tạo snapshot/result hoặc một ý định side effect bất biến
5. Thả lock
6. Thực thi I/O/callback/notification dựa trên result
7. Nếu cần, ghi nhận trạng thái thành công/thất bại bằng một bước được thiết kế riêng
~~~

**Giới hạn:** Nếu side effect phải xảy ra “nguyên tử” với state trong bộ nhớ hoặc hệ thống ngoài tiến trình, chỉ dời side effect ra ngoài lock **không tạo transaction phân tán**. Cần thiết kế idempotency key, state machine, outbox, retry/compensation hoặc cơ chế giao dịch thích hợp tùy hệ thống. Khóa JVM không bảo đảm atomicity giữa memory và database/mạng.

### Ví dụ side effect không nên được giữ dưới khóa

Sai:

~~~java
synchronized (lock) {
    state = State.READY;
    remoteNotifier.send(event); // Có thể block, throw hoặc gọi lại.
}
~~~

Một lựa chọn dễ kiểm chứng hơn nếu nghĩa nghiệp vụ cho phép:

~~~java
Event event;
synchronized (lock) {
    state = State.READY;
    event = new Event(state);
}
remoteNotifier.send(event); // Đã thả lock, xử lý lỗi riêng.
~~~

Hai đoạn là **minh họa cấu trúc**, không phải chương trình độc lập (các kiểu `State`, `Event` và `remoteNotifier` cần tự định nghĩa). Nếu gửi event thất bại, state đã là READY; nghiệp vụ phải định nghĩa cách retry/ghi nhận lỗi. Không được giả định rằng thao tác đã trở thành một transaction nhờ dời lời gọi ra ngoài khóa.

## 8. Tránh gọi code không kiểm soát khi giữ khóa (*open calls*)

Một callback có thể làm bất cứ điều gì: tốn thời gian, ném exception, gọi ngược vào object hiện tại, gọi object khác đang giữ lock, hoặc block chờ một thread khác. Khi gọi callback bên trong lock, ta ngầm mở rộng critical section sang code không kiểm soát.

Ví dụ không nên làm:

~~~java
synchronized (lock) {
    for (Runnable listener : listeners) {
        listener.run(); // Callback có thể reenter, chậm hoặc chờ.
    }
}
~~~

Giải pháp là **chụp danh sách callback dưới lock rồi gọi ngoài lock** nếu semantics cho phép. Snapshot này cũng tránh thay đổi `listeners` giữa lúc lặp qua chính danh sách nội bộ.

### Ví dụ 4 — chụp danh sách listener rồi gọi ngoài lock

Tạo `OpenCallDemo.java` (Java 17+):

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class OpenCallDemo {
    private static final class EventSource {
        private final Object lock = new Object();
        private final List<Runnable> listeners = new ArrayList<>();

        void subscribe(Runnable listener) {
            Objects.requireNonNull(listener);
            synchronized (lock) {
                listeners.add(listener);
            }
        }

        void fire() {
            List<Runnable> snapshot;
            synchronized (lock) {
                snapshot = List.copyOf(listeners);
            }

            for (Runnable listener : snapshot) {
                listener.run(); // Không giữ lock nội bộ.
            }
        }
    }

    public static void main(String[] args) {
        EventSource source = new EventSource();
        source.subscribe(() -> System.out.println("listener A"));
        source.subscribe(() -> System.out.println("listener B"));
        source.fire();
    }
}
~~~

Chạy:

~~~bash
javac OpenCallDemo.java
java OpenCallDemo
~~~

Stdout:

~~~text
listener A
listener B
~~~

`List.copyOf` tạo snapshot cấu trúc danh sách listener tại thời điểm lấy lock, và `fire()` gọi callback **sau khi lock đã được thả**. Nếu listener đăng ký thêm listener trong callback, thay đổi ấy có thể áp dụng ở lượt `fire()` tiếp theo; nó không làm thay đổi snapshot của lượt hiện tại.

Lưu ý: `listener.run()` có thể ném exception, khiến vòng lặp dừng trước các listener còn lại; nếu yêu cầu “thông báo tất cả bất kể một listener lỗi”, phải có chính sách bắt lỗi riêng, báo cáo và retry. Snapshot chỉ giải quyết lock ownership, không giải quyết mọi semantics của hệ thống event.

Một số ứng dụng cần snapshot toàn bộ **nội dung event** cùng danh sách listener; để listener đọc mutable state sau unlock có thể lại gặp inconsistent state. Hãy tạo immutable event snapshot trong critical section nếu đó là dữ liệu listener cần quan sát.

## 9. Không phải thao tác blocking nào cũng nguy hiểm như nhau

Một lời gọi chờ **không tự động deadlock**. Nguy cơ xuất hiện khi ta giữ khóa mà thread khác cần để tạo tiến triển.

Ví dụ:

~~~text
Thread A:
    lock(L)
    wait(Future completed by B)  <-- A vẫn giữ L

Thread B:
    lock(L)                      <-- B cần L mới hoàn tất Future
    complete Future
~~~

A đợi B, B đợi A thả L: đây là chu trình chờ và có thể deadlock.

Cách sửa là thay đổi giao thức để A **không giữ L khi chờ công việc đòi hỏi L**, hoặc chuyển công việc sang một mô hình event/state machine không tạo vòng chờ. Chỉ thêm timeout có thể giảm thời gian treo nhưng không sửa invariant hay dependency cycle.

Trong Java, `Object.wait()` khi được gọi đúng trong một khối synchronized sẽ **nhả monitor của chính object được wait** trong lúc chờ, rồi lấy lại trước khi trả về. Đây là ngoại lệ quan trọng so với `Thread.sleep()`, vốn **không nhả monitor đang giữ**. Tuy vậy, dùng `wait/notify` vẫn phải có vòng `while` kiểm tra predicate và một protocol rõ ràng.

Ví dụ monitor condition:

~~~java
synchronized (lock) {
    while (!condition) {
        lock.wait();
    }
    // Kiểm tra/làm việc theo condition dưới lock.
}
~~~

Đoạn minh họa này chỉ có nghĩa khi thread khác thay đổi `condition` dưới cùng lock và gọi `notifyAll`/`notify` phù hợp; nếu không, thread có thể chờ mãi. Thực tế thường ưu tiên `BlockingQueue`, `CountDownLatch`, `Condition` hoặc concurrent utilities khi đúng bài toán.

## 10. Khi muốn tính ngoài lock từ một snapshot: vấn đề stale data

Có những phép tính tốn thời gian **phụ thuộc state hiện tại**, ví dụ tính giá từ tồn kho, dựng một immutable cấu hình mới, hoặc lập lịch dựa trên số slot còn trống. Đọc state dưới lock, thả lock để tính, rồi quay lại cập nhật **không an toàn nếu không kiểm tra rằng state chưa đổi**.

Mẫu có nguy cơ:

~~~java
Snapshot old;
synchronized (lock) {
    old = snapshotOfState();
}
Proposal proposal = expensiveCalculation(old);
synchronized (lock) {
    apply(proposal); // Sai nếu state đổi và proposal phụ thuộc old.
}
~~~

Một phương án *optimistic* có thể dùng **version**:

~~~java
// Mã giả mô tả protocol, không phải chương trình độc lập.
while (true) {
    Snapshot base;
    synchronized (lock) {
        base = snapshotWithVersion();
    }

    Proposal proposal = expensiveCalculation(base); // Ngoài lock.

    synchronized (lock) {
        if (currentVersion != base.version()) {
            continue; // State đổi; bỏ đề xuất cũ và thử lại.
        }
        apply(proposal);
        currentVersion++;
        break;
    }
}
~~~

Điều kiện để đúng:

1. Mọi writer ảnh hưởng state cần thiết đều cập nhật cùng **version** theo protocol.
2. `snapshotWithVersion()` phải lấy một snapshot nhất quán dưới lock.
3. `apply(proposal)` và việc tăng version phải chung critical section.
4. Tính toán bên ngoài không tạo side effect không thể rollback vì nó có thể phải **lặp lại**.
5. Nên có chính sách retry/backoff hoặc giới hạn xung đột; dưới tải cao, optimistic retry có thể tốn hơn việc giữ lock ngắn.

Đây là một thiết kế khác, **không phải lý do tự ý tách mọi critical section**. Với tính toán nhanh và contention thấp, giữ tính toán ngắn trong lock thường đơn giản, dễ chứng minh hơn.

## 11. Khi cần nhiều khóa: thứ tự khóa cố định

Một critical section có thể cần bảo vệ trạng thái của **nhiều đối tượng**. Ví dụ chuyển tiền giữa hai tài khoản phải kiểm tra số dư, trừ tiền ở nguồn và cộng tiền ở đích trong một thao tác logic nhất quán. Nếu hai thread lấy hai khóa theo hai thứ tự đối nghịch, chúng có thể rơi vào deadlock:

~~~text
Thread A: giữ lock(account1), chờ lock(account2)
Thread B: giữ lock(account2), chờ lock(account1)
~~~

Giải pháp là xác định **thứ tự khóa tổng, ổn định** (chẳng hạn ID duy nhất, bất biến) và mọi đường code đều lấy nhiều khóa theo cùng thứ tự, độc lập với thứ tự tham số. Không được nhả khóa tài khoản nguồn trước khi giữ khóa tài khoản đích nếu invariant yêu cầu cả chuyển khoản là atomic.

Ở bài này, điều quan trọng là **ranh giới critical section phải bao trọn invariant xuyên nhiều object**. Bài **Lock ordering để ngăn deadlock** tiếp tục bằng mã chuyển khoản đầy đủ, cách đặt thứ hạng, xử lý khóa trùng và kiểm thử vòng chờ.

## 12. `ReentrantLock`: rõ ràng acquire/release và cleanup

`synchronized` tự giải phóng monitor khi rời block, kể cả khi ném exception. `ReentrantLock` cần `unlock()` rõ ràng, thông thường trong `finally`:

~~~java
// Minh họa method trong class có một ReentrantLock dùng chung.
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

private int value;

void increment() {
    lock.lock();
    try {
        value++;
    } finally {
        lock.unlock();
    }
}
~~~

`ReentrantLock` hữu ích khi cần:

- `tryLock()` để tránh chờ vô hạn hoặc có fallback.
- `tryLock(timeout, unit)` để giới hạn thời gian **chờ lấy lock**.
- `lockInterruptibly()` để có thể hủy việc đợi lock.
- `Condition` để chờ một predicate với protocol tương ứng.
- Tùy chọn fairness cho lock nếu ứng dụng có nhu cầu và chấp nhận tradeoff; fairness của lock không đồng nghĩa scheduler OS luôn công bằng.

**Tránh các lỗi:**

- `lock()` rồi `return` hoặc throw trước khi vào `try/finally`.
- Gọi `unlock()` từ thread không sở hữu lock.
- Lấy nhiều ReentrantLock theo thứ tự không nhất quán.
- Giả định `tryLock() == false` có nghĩa trạng thái nghiệp vụ đã sai; nó chỉ nói thread chưa lấy được lock.
- Giữ lock trong khi chờ I/O hoặc task khác phụ thuộc lock.

Nếu chỉ cần một critical section đơn giản, `synchronized` thường dễ kiểm chứng hơn vì cấu trúc lexical của lock rõ ràng và việc release được JVM thực hiện tự động.

## 13. Chọn atomic primitive thay vì lock khi đúng phạm vi

Đối với **một counter độc lập**, `AtomicInteger.incrementAndGet()` biểu đạt phép read-modify-write atomic mà không cần khóa monitor do bạn quản lý:

~~~java
private final java.util.concurrent.atomic.AtomicInteger count =
        new java.util.concurrent.atomic.AtomicInteger();

void increment() {
    count.incrementAndGet();
}
~~~

Nhưng không được tự chia `count.get()` và `count.set(old + 1)` rồi cho là atomic. Với nhiều field cùng invariant, hai `AtomicInteger` riêng lẻ cũng không cung cấp transaction chung.

`ConcurrentHashMap.compute/merge` có thể thực hiện cập nhật nguyên tử theo key; song chuỗi `map.get(k)` rồi `map.put(k, value)` vẫn là check-then-act không atomic ở cấp operation kết hợp. `LongAdder` tốt cho một số workload thống kê nhiều writer, nhưng `sum()` khi có cập nhật đồng thời không phải snapshot atomic.

**Định nghĩa phạm vi** trước khi chọn primitive. “Không có synchronized” không tự nghĩa là tối ưu hơn hay đúng hơn. Một lock gọn, bao đúng invariant đa field có thể đơn giản và an toàn hơn kết hợp nhiều atomic variables thiếu protocol.

## 14. Tối ưu thời gian giữ khóa: đừng đổi correctness lấy throughput

Có hai chi phí khác nhau:

- **Thời gian thực thi bên trong lock**: tính toán, cấp phát, kiểm tra điều kiện, thao tác memory/I/O.
- **Thời gian chờ để lấy lock** (*contention / blocked time*): phụ thuộc tần suất cạnh tranh, số thread, scheduling, độ dài critical section và thiết kế lock.

Để cải thiện:

1. **Loại I/O/callback có thể block** khỏi lock khi semantics cho phép.
2. **Tính trước dữ liệu độc lập** như parse, validate input immutable, tạo DTO bất biến.
3. **Chụp immutable snapshot trong lock**, xử lý/report bên ngoài.
4. **Giảm shared mutable state**: thread confinement, message passing, immutable values, queue.
5. **Giảm tần suất khóa** khi có thể batch cập nhật dưới cùng lock mà vẫn giữ latency phù hợp.
6. **Tách lock theo dữ liệu độc lập** khi không có invariant chéo; tránh lock striping tùy tiện nếu nhiều field phụ thuộc nhau.
7. **Đo lường trước/sau** bằng workload đại diện: throughput, p95/p99 latency, block/wait time, queue length và hot lock.

Một critical section nhỏ về số dòng nhưng gọi thuật toán chậm vẫn là vùng khóa dài. Một critical section “rất ngắn” được thực hiện hàng triệu lần cũng có thể gây contention lớn. Đo đạc mới cho biết bottleneck thật.

### Lưu ý về granularity khi tách lock

Giả sử tài khoản A và B không bao giờ tương tác, mỗi tài khoản một lock có thể tăng concurrency. Nhưng khi có thao tác chuyển khoản, invariant của cả A và B cần đồng bộ theo protocol **nhiều khóa** hoặc một lock chung. Tách khóa mà không phân tích dữ liệu phụ thuộc làm code khó kiểm chứng hơn và tạo nguy cơ deadlock.

Khóa quá rộng làm chậm tiến triển của các công việc không liên quan; khóa quá hẹp phá atomicity. **Phạm vi đúng** là phạm vi tối thiểu bao trọn invariant và các điều kiện quyết định thay đổi nó.

## 15. Xác minh tính đúng: review bằng invariant và phép xen kẽ

### A. Viết một bảng “ai giữ lock khi nào”

Ví dụ cho `reserveOne()`:

| Trạng thái | Thread A | Thread B |
| --- | --- | --- |
| `available = 1` | Lấy lock và đọc 1 | Chờ lock |
| Trong critical section | Ghi `available = 0`, trả true | Vẫn chờ |
| Sau unlock | Hoàn tất reserve | Lấy lock, đọc 0, trả false |

Bảng này cho thấy B không thể xen vào giữa thao tác kiểm tra và ghi của A, vì chúng dùng một lock và đều truy cập state qua `reserveOne()`. Có thể viết kiểu bảng tương tự cho mọi invariant quan trọng để review.

### B. Tìm những lối đi bỏ qua lock

Câu hỏi cần kiểm tra trong code review:

- Shared field có `private` không? Caller có giữ tham chiếu tới một collection nội bộ rồi sửa trực tiếp?
- Constructor/initializer có làm rò rỉ `this` trước khi state sẵn sàng không?
- Mọi reader **và** writer có dùng cùng lock hoặc protocol visibility không?
- Có đường “fast path” đọc state không lock dù writer dùng lock?
- Có copy/snapshot nào được tạo **sau khi** thả lock nên có thể nhận nhiều phiên bản không?
- Method gọi callback khi giữ lock có thể gọi ngược vào object khác và tạo vòng chờ?
- Có multiple locks nào bị lấy theo thứ tự trái ngược?
- Có blocking operation chỉ có thể hoàn thành nhờ một thread đang chờ lock ấy không?

### C. Thử dưới cạnh tranh có kiểm soát

`CountDownLatch` hoặc `CyclicBarrier` có thể giúp điều khiển hai thread cùng bắt đầu để kiểm chứng invariant, thay vì dựa vào `Thread.sleep`. Test nên:

- Chờ tất cả worker bằng `join()`/`Future.get()`, không kiểm tra kết quả sớm.
- Xác minh một **kết quả bất biến**, ví dụ approved count không vượt stock, tổng tiền bảo toàn, version tương ứng số update.
- Lặp với số worker/tải khác nhau khi cần; song một stress test pass không phải chứng minh hình thức.
- Dùng timeout để tránh test treo vĩnh viễn khi xuất hiện deadlock, kèm thread dump/stack trace.
- Đo correctness riêng khỏi hiệu năng để tránh chấp nhận race vì nhanh hơn trong một lần chạy.

### D. Phân biệt deadlock, starvation và contention

| Hiện tượng | Dấu hiệu | Cách suy luận |
| --- | --- | --- |
| **Contention** | Nhiều thread mất thời gian chờ cùng lock | Giảm work độc lập trong lock, giảm shared state, đo blocked time |
| **Deadlock** | Các thread tạo chu trình chờ khóa/tài nguyên và không tiến triển | Phân tích lock order, chờ callback/`Future` dưới lock, lấy thread dump |
| **Starvation** | Một công việc có thể chờ rất lâu vì không có cơ hội được phục vụ | Xem queue, scheduling, fairness policy và load |
| **Race condition** | Kết quả sai tùy xen kẽ thao tác | Tìm compound action không được bảo vệ, invariant thiếu HB/atomicity |

Chỉ “thêm khóa lớn quanh mọi thứ” có thể làm race biến mất nhưng tạo contention hoặc deadlock. Giải pháp lâu dài là thiết kế lock ownership và boundary rõ ràng.

## 16. Một số phản-pattern và cách sửa

| Phản-pattern | Vì sao nguy hiểm | Hướng sửa |
| --- | --- | --- |
| Khóa riêng từng `get` và `set` trong một compound action | Thread khác chen vào giữa | Tạo một API atomic bao cả check/modify/write |
| Đọc field trần ngoài lock vì “chỉ đọc” | Thiếu visibility hoặc snapshot nhất quán | Đọc dưới cùng lock; immutable/volatile snapshot nếu phù hợp |
| Lấy snapshot của hai field bằng hai lock riêng | Có thể pha phiên bản | Chụp cặp dữ liệu dưới cùng critical section |
| Gọi HTTP/DB/file dưới monitor dữ liệu | Giữ lock qua latency không dự báo | Thiết kế state transition + side effect sau unlock |
| Gọi listener trong synchronized | Callback có thể block, reenter hoặc gây lock cycle | Copy listener/event snapshot, gọi ngoài lock |
| Tính kết quả từ snapshot cũ rồi commit không kiểm tra | Lost update hoặc vi phạm invariant | Lock cả decision hoặc version/CAS retry |
| Lấy A rồi B ở thread này, B rồi A ở thread khác | Deadlock | Áp dụng lock ordering thống nhất |
| Dùng `Thread.sleep` để tạo thứ tự | Không có hợp đồng đồng bộ | Dùng latch, condition, queue, future |
| Nhả lock mà không dùng `finally` với `ReentrantLock` | Dễ kẹt lock sau exception | `try/finally` |
| Tách lock quá sớm để tối ưu | Invariant chéo dễ bị bỏ sót | Kiểm chứng invariant rồi mới cân nhắc chia lock |
| Giữ lock qua `Future.get()` phụ thuộc worker cũng cần lock | Chu trình chờ | Thay protocol hoặc chờ ngoài lock |
| Chỉ thử trên một máy rồi kết luận an toàn | Race hiếm có thể không tái hiện | Lập luận JMM, invariant và kiểm thử cạnh tranh |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Hai thread cùng làm `if (stock > 0) stock--`. Nếu `if` và `stock--` nằm trong **hai** khối synchronized riêng, có đủ không?  
**Đáp án:** Không. Thread khác có thể thay đổi stock giữa kiểm tra và cập nhật. Phải giữ chúng trong cùng critical section hoặc dùng một atomic operation biểu đạt đầy đủ điều kiện.

**Câu 2.** Parse chuỗi số dương từ input immutable có phụ thuộc balance hiện tại không?  
**Đáp án:** Không. Có thể parse/validate định dạng ngoài lock. Nhưng việc kiểm tra có đủ balance và thay đổi balance phải được bảo vệ cùng nhau.

**Câu 3.** Writer thay đổi `total` và `version` dưới hai lock khác nhau, reader đọc từng field dưới hai lock khác nhau. Snapshot có đảm bảo nhất quán không?  
**Đáp án:** Không. Invariant cặp field cần một giao thức đồng bộ thống nhất để đọc/ghi như một đơn vị logic.

**Câu 4.** Gọi một listener chậm dưới `synchronized` có thể làm hỏng correctness dù listener chỉ in log không?  
**Đáp án:** Có thể làm các thread khác chờ lâu; nếu listener gọi ngược hoặc đợi một thread cần cùng lock, có thể tạo chu trình chờ. Nên lấy snapshot và gọi ngoài lock khi semantics cho phép.

**Câu 5.** Có thể chụp state ở thời điểm t1, tính ngoài lock, rồi ghi ở t2 mà không so sánh version không?  
**Đáp án:** Chỉ nếu phép tính không phụ thuộc state có thể thay đổi hoặc có protocol khác bảo đảm. Nếu phụ thuộc snapshot t1, phải revalidate/CAS hay tính trong lock.

**Câu 6.** Hai thread chuyển khoản A→B và B→A, mỗi thread khóa nguồn trước rồi khóa đích. Nguy cơ gì?  
**Đáp án:** Deadlock do khóa ngược thứ tự. Cần thứ tự khóa toàn cục hoặc thiết kế khác có invariant rõ.

**Câu 7.** `volatile long balance` có thay cho một critical section kiểm tra đủ tiền và trừ tiền không?  
**Đáp án:** Không. `volatile` tạo visibility/order cho từng access, không biến check-then-act thành atomic.

**Câu 8.** Critical section tối ưu nhất là ít dòng nhất phải không?  
**Đáp án:** Không. Đúng phạm vi invariant mới là tiêu chí đầu tiên; sau đó mới loại những việc độc lập hoặc kéo dài thời gian giữ khóa.

## Tài liệu tham khảo Java SE

- [Java Language Specification `17 — Threads and Locks (Java SE 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): monitor, synchronization, happens-before và data races.
- [`Object` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): `wait()`, `notify()`, `notifyAll()` và monitor.
- [`ReentrantLock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock/unlock, tryLock, fairness và interruption.
- [`Lock` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html): hợp đồng synchronization.
- [`CountDownLatch` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối test cạnh tranh.
- [`AtomicInteger` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): atomic single-variable update.
- [`ConcurrentHashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): cập nhật atomic theo key.

**Ghi nhớ:** Một critical section tốt phải **bao trọn quyết định dựa trên shared state**, sử dụng **một lock/protocol nhất quán**, và tránh giữ khóa qua công việc độc lập hay có thời gian không kiểm soát. Chọn ranh giới từ invariant, không chọn ranh giới từ số dòng mã.