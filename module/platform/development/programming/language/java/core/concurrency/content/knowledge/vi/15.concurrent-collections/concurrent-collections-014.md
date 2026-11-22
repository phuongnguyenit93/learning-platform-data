# Giá trị mutable trong ConcurrentHashMap vẫn cần hợp đồng thread safety riêng

## 1. Mục tiêu bài học

Sau bài học này, bạn có thể:

- Giải thích **ConcurrentHashMap** bảo vệ **các thao tác trên cấu trúc ánh xạ key → value**, nhưng không tự bảo vệ những field hoặc collection mutable nằm bên trong value.
- Phân biệt **atomic map operation**, **an toàn của object được trả về từ get()**, **safe publication**, **visibility**, **atomicity của cập nhật nghiệp vụ**, và **snapshot nhất quán**.
- Phát hiện lỗi khi nhiều thread cùng dùng **map.get(key).count++**, **map.get(key).list.add(...)** hoặc chuỗi **get → mutate → put** mà không có đồng bộ hóa phù hợp.
- Chọn đúng giải pháp: **AtomicInteger / AtomicLong**, **LongAdder**, **synchronized value**, **immutable record + compute/merge**, **copy-on-write immutable collection**, hoặc thiết kế ownership.
- Phân tích các giới hạn của **computeIfAbsent**, **compute**, **computeIfPresent**, **merge**, **putIfAbsent** và **replace** khi value bị sửa từ những reference bên ngoài.
- Nhận biết các lỗi tinh vi: thay value trong lúc thread khác giữ reference cũ, **remove/reset race**, thay đổi object ảnh hưởng đến equals/hashCode, **compound invariant nhiều key**, và việc lầm tưởng weakly consistent iteration là snapshot.
- Viết và chạy Java 17+ với các bài kiểm thử có điều phối bằng CountDownLatch và kết quả đầu ra xác định; không dùng sleep để “làm race xuất hiện”.

Bài thuộc nhóm **Concurrent Collections**, phạm vi là **Java concurrency nói chung**. Những cấu hình hoặc thành phần liên quan riêng tới Spring được trình bày ở chương khác.

## 2. Tuyên bố quan trọng nhất

**ConcurrentHashMap<K,V> giúp nhiều thread thao tác trên map đồng thời, nhưng V không tự trở thành thread-safe chỉ vì được lưu trong ConcurrentHashMap.**

Ví dụ:

~~~java
// Đoạn minh họa; cần import các kiểu tương ứng.
ConcurrentHashMap<String, Counter> map =
        new ConcurrentHashMap<>();
map.put("orders", new Counter());

Counter c = map.get("orders");
c.count++;  // Không được bảo vệ bởi ConcurrentHashMap.
~~~

Đây không phải chương trình chạy độc lập: Counter là kiểu mutable giả định có field count.

Một thao tác **map.get("orders")** có thể lấy an toàn reference của Counter đã được publish. Nhưng sau khi lấy được reference, **c.count++** là một chuỗi **đọc → cộng → ghi** trên object Counter. Nếu nhiều thread cùng chạy, có nguy cơ **lost update** dù tất cả các lời gọi get() đều hợp lệ.

Hãy coi hai lớp bảo đảm là **hai hợp đồng khác nhau**:

| Tầng | Cái được bảo vệ | Cái không tự được bảo vệ |
| --- | --- | --- |
| ConcurrentHashMap | Quan hệ key → value và các thao tác đồng thời theo API của map | Các field và collection mutable bên trong V |
| Value object | Phụ thuộc thiết kế V: immutable, atomic, lock, confinement... | Không tự có bảo đảm chỉ vì reference nằm trong map |
| Quy trình nghiệp vụ | Phụ thuộc invariant và giao thức transaction/đồng bộ | Không tự được đảm bảo bởi một lời gọi get() hoặc put() |

**Slogan dễ nhớ:** *Thread-safe map không có nghĩa thread-safe object graph.*

## 3. ConcurrentHashMap thực sự đảm bảo những gì?

**ConcurrentHashMap** trong java.util.concurrent là một Map hỗ trợ truy cập đồng thời mà không khóa toàn bộ map cho mỗi thao tác. Các operation độc lập như **get**, **put**, **remove**, **putIfAbsent**, **replace**, **compute**, **merge** có hợp đồng tương ứng.

Một số tính chất cần nhớ:

- **get(key)** trả về value hiện tại hoặc null khi không có mapping; nó **không sao chép** value và không làm một mutable value bất biến.
- **put(key, value)** thay thế ánh xạ cho key, nhưng không biến các thao tác trước/sau trên chính value thành atomic.
- **putIfAbsent** có thể đặt value nếu key chưa có mapping; khác với get rồi put thủ công khi nhiều thread tranh cùng key.
- **replace(key, expected, newValue)** chỉ thay mapping khi điều kiện được đáp ứng; không tự “đóng băng” object mà các thread khác đã lấy reference.
- **compute/computeIfPresent/merge** cung cấp cách cập nhật mapping tương ứng một cách nguyên tử theo key khi dùng đúng hợp đồng.
- ConcurrentHashMap **không hỗ trợ key null hoặc value null**. Với những phương thức remapping, trả **null** thường mang ý nghĩa xóa/không tạo mapping theo API cụ thể.
- Các phép duyệt có tính chất **weakly consistent**, có thể phản ánh một phần thay đổi đồng thời và không tạo snapshot nhất quán tức thời của toàn map.
- Các phép size, mappingCount và thống kê trên map đang thay đổi phù hợp cho giám sát/ước lượng; không dùng chúng thay giao thức admission-control chính xác.

**Map-level atomicity** chỉ cho biết chuyện gì xảy ra với **mapping**. Nó không nói rằng object value bị khóa trong toàn bộ vòng đời kể từ lần get đầu tiên.

## 4. Safe publication không đồng nghĩa an toàn cho những lần sửa tiếp theo

Giả sử một thread xây dựng Counter rồi **put** vào ConcurrentHashMap. Thread khác sau đó **get** thấy Counter đó. Các memory consistency effects của concurrent collection giúp công bố trạng thái đã hoàn thành trước khi đưa object vào map theo hợp đồng API.

Điều này **khác hẳn** việc thread xây dựng tiếp tục sửa Counter sau khi put và thread đọc cũng sửa nó cùng lúc:

~~~text
Thread A                          Thread B
--------                          --------
Counter c = new Counter();
c.count = 10;
map.put("x", c);  --------->
                                  Counter ref = map.get("x");
c.count++;   (A)                  ref.count++;  (B)
        |                              |
        +------ Cùng object mutable ---+
                        |
              Không có atomic increment.
~~~

Publication chỉ giải quyết **khả năng quan sát dữ liệu đã được publish** ở một ranh giới đồng bộ; nó không tạo monitor vĩnh viễn quanh object hay một quan hệ happens-before giữa mọi sửa đổi về sau.

### Vì sao final field chưa đủ?

~~~java
final class Holder {
    final Counter counter = new Counter();
}
~~~

Dù field **counter** là final, object **Counter** vẫn có thể bị sửa. **Final reference** ngăn việc gán lại reference đó qua field của Holder sau khi xây dựng; nó không làm những field bên trong Counter thành final hoặc thread-safe.

Tương tự, **Collections.unmodifiableList** chỉ tạo view ngăn sửa thông qua view. Nếu còn reference tới list mutable gốc, thread khác vẫn có thể sửa nó. **List.copyOf** tạo một danh sách không sửa qua API, nhưng nếu phần tử của list là object mutable thì đây vẫn chỉ là **shallow immutability**.

## 5. Ví dụ 1: tái hiện lost update một cách xác định

Race condition không phải lúc nào xảy ra khi chạy thử. Để chứng minh lỗi mà **không dựa vào may mắn của scheduler**, hai thread cùng đọc count trước khi được phép ghi. Vì cả hai cùng đọc 0, cả hai cùng ghi 1.

Tệp **UnsafeMutableValueDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class UnsafeMutableValueDemo {
    static final class Counter {
        int value;
    }

    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, Counter> map =
                new ConcurrentHashMap<>();
        map.put("orders", new Counter());

        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Runnable increment = () -> {
            Counter counter = map.get("orders");
            int before = counter.value;

            bothRead.countDown();
            try {
                allowWrite.await();
                counter.value = before + 1;
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        };

        Thread first = new Thread(increment, "first");
        Thread second = new Thread(increment, "second");
        first.start();
        second.start();

        bothRead.await();
        allowWrite.countDown();
        first.join();
        second.join();

        System.out.println("expected = 2");
        System.out.println("actual = " + map.get("orders").value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 UnsafeMutableValueDemo.java
java UnsafeMutableValueDemo
~~~

Stdout:

~~~text
expected = 2
actual = 1
~~~

**Phân tích:**

1. Map publish một Counter ban đầu bằng 0.
2. Hai thread lấy **cùng reference Counter** qua get().
3. Mỗi thread đọc 0 vào biến cục bộ before, rồi báo bothRead.
4. Main chỉ mở allowWrite sau khi **cả hai thread đã đọc**.
5. Cả hai ghi **before + 1 = 1**; tổng cuối vẫn 1 thay vì 2.
6. **join()** cho main biết cả hai thread đã hoàn thành trước khi đọc.
7. Latch tạo một lịch xen kẽ có kiểm soát; không dựa vào Thread.sleep().

Đây là mô hình đơn giản của **lost update**. Trong ứng dụng thật, chỉ viết **counter.value++** có thể làm bug ít tái hiện hơn nhưng bản chất vẫn là read-modify-write không nguyên tử.

**Không sửa bằng cách gọi map.put("orders", counter) sau khi tăng**: nếu hai thread cùng sửa Counter trước put, thao tác put thread-safe không hồi phục được increment bị mất.

## 6. Giải pháp A: lưu giá trị atomic thay cho counter mutable thường

Khi mỗi key chỉ cần một phép tăng độc lập, đặt **AtomicInteger** hoặc **AtomicLong** làm value là lựa chọn trực tiếp.

~~~java
// Minh họa:
ConcurrentHashMap<String, AtomicInteger> counts =
        new ConcurrentHashMap<>();

counts.computeIfAbsent("orders", k -> new AtomicInteger())
      .incrementAndGet();
~~~

Hai bảo đảm khác nhau phối hợp:

- **computeIfAbsent** giúp có một mapping cho key, tránh get-null rồi put tự viết.
- **incrementAndGet()** bảo đảm phép tăng trên **AtomicInteger value** là nguyên tử.

Lưu ý **computeIfAbsent không làm incrementAndGet thành một phần của mapping operation**; sau khi lấy được AtomicInteger, thao tác tăng được thực hiện trên object value. Điều này vẫn đúng khi các thread chia sẻ **cùng AtomicInteger ổn định cho key đó**.

### Ví dụ 2: AtomicInteger cho từng key

Tệp **AtomicValueMapDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicValueMapDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, AtomicInteger> map =
                new ConcurrentHashMap<>();

        Runnable worker = () -> {
            for (int i = 0; i < 10_000; i++) {
                map.computeIfAbsent(
                        "orders", k -> new AtomicInteger()
                ).incrementAndGet();
            }
        };

        Thread first = new Thread(worker);
        Thread second = new Thread(worker);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("orders = " + map.get("orders").get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicValueMapDemo.java
java AtomicValueMapDemo
~~~

Stdout:

~~~text
orders = 20000
~~~

Hai thread cùng tăng một AtomicInteger dùng chung; mỗi increment không bị lost update. Nhưng ví dụ giả định **không có thread thứ ba remove hoặc replace mapping "orders" trong lúc tăng**.

### Bẫy remove và replace

Hình dung:

~~~text
T1: AtomicInteger old = map.get("orders");
T2: map.remove("orders");
T2: map.put("orders", new AtomicInteger());
T1: old.incrementAndGet();
~~~

T1 vừa tăng **old** sau khi nó đã bị gỡ khỏi map. Bản ghi trong map hiện tại không phản ánh increment ấy. Mỗi thao tác atomic vẫn đúng **trên object mà nó tác động**, nhưng nghiệp vụ kiểu “tổng tất cả orders bất kể reset” bị sai.

Nếu có yêu cầu **reset/removal đồng thời với increment**, phải định nghĩa rõ semantics (epoch, generation, version hoặc cập nhật mapping bằng compute cùng một giao thức), không chỉ thay value bằng atomic.

## 7. Giải pháp B: LongAdder cho thống kê tranh chấp cao

**LongAdder** là value phổ biến cho bộ đếm được nhiều thread tăng, đặc biệt khi contention cao. Mẫu thường gặp:

~~~java
// Minh họa: ConcurrentHashMap<String, LongAdder> frequencies
frequencies.computeIfAbsent(
        "java", k -> new LongAdder()
).increment();
~~~

**LongAdder.sum()** trả tổng quan sát được của các ô đếm bên trong. Khi **có cập nhật đồng thời**, sum() **không phải atomic snapshot**; có thể không phản ánh tất cả cập nhật đang xảy ra theo một thời điểm tuyến tính.

### Ví dụ 3: LongAdder sau khi hai worker hoàn tất

Tệp **LongAdderMapDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

public class LongAdderMapDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentHashMap<String, LongAdder> map =
                new ConcurrentHashMap<>();

        Runnable work = () -> {
            for (int i = 0; i < 5_000; i++) {
                map.computeIfAbsent(
                        "events", key -> new LongAdder()
                ).increment();
            }
        };

        Thread a = new Thread(work);
        Thread b = new Thread(work);
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("events = " + map.get("events").sum());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LongAdderMapDemo.java
java LongAdderMapDemo
~~~

Stdout:

~~~text
events = 10000
~~~

**sum() sau join** được gọi khi mọi cập nhật minh họa đã hoàn tất, nên kết quả xác định. Nếu main gọi sum() giữa lúc hai worker đang cập nhật, không được sử dụng số đó làm transaction quota chính xác.

| Công cụ | Ưu điểm | Điểm cần chú ý |
| --- | --- | --- |
| AtomicInteger | Increment, get, compareAndSet; thích hợp quyết định một biến | Contention nếu nhiều thread sửa cùng điểm |
| AtomicLong | Như AtomicInteger nhưng miền long | Vẫn chỉ bảo vệ một giá trị |
| LongAdder | Tăng throughput trong một số workload thống kê tranh chấp cao | sum() đang có update không phải snapshot nguyên tử |
| Plain int trong value | Đơn giản khi chỉ một thread sở hữu hoặc lock bao phủ | Không tự an toàn khi nhiều writer |

**Cùng bẫy remove/replace như AtomicInteger:** nếu thread giữ LongAdder cũ và increment sau khi mapping bị thay, cập nhật có thể không còn được phản ánh ở value mới. **sumThenReset()** cũng không phải transaction ngăn mọi concurrent increments; muốn chia epoch và reset chuẩn xác, cần giao thức riêng.

## 8. Giải pháp C: immutable value và cập nhật ánh xạ bằng compute

Với bất biến bao gồm **nhiều field**, có thể đặt **immutable record** làm value và dùng **compute** hoặc **computeIfPresent** để thay **toàn bộ mapping** theo key.

Ví dụ Inventory có hai số: available và reserved. Bất biến:

- available không âm;
- reserved không âm;
- **available + reserved** luôn bằng tổng ban đầu;
- một yêu cầu giữ chỗ chỉ thay hai số **cùng lúc**.

Nếu đặt hai AtomicInteger riêng trong value rồi cập nhật lần lượt, một reader có thể thấy trạng thái trung gian. Thay vào đó, mỗi lần update tạo một **record mới** và thay **một mapping** bằng compute.

### Ví dụ 4: immutable record + computeIfPresent

Tệp **ImmutableInventoryMapDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;

public class ImmutableInventoryMapDemo {
    record Inventory(int available, int reserved) {}

    static void reserveOne(
            ConcurrentHashMap<String, Inventory> inventory) {
        inventory.computeIfPresent("book", (key, old) -> {
            if (old.available() == 0) {
                return old;
            }
            return new Inventory(
                    old.available() - 1,
                    old.reserved() + 1
            );
        });
    }

    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<String, Inventory> map =
                new ConcurrentHashMap<>();
        map.put("book", new Inventory(100, 0));

        Runnable buyer = () -> {
            for (int i = 0; i < 50; i++) {
                reserveOne(map);
            }
        };

        Thread[] threads = new Thread[4];
        for (int i = 0; i < threads.length; i++) {
            threads[i] = new Thread(buyer);
            threads[i].start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        Inventory end = map.get("book");
        System.out.println("available = " + end.available());
        System.out.println("reserved = " + end.reserved());
        System.out.println(
                "total = " + (end.available() + end.reserved())
        );
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableInventoryMapDemo.java
java ImmutableInventoryMapDemo
~~~

Stdout:

~~~text
available = 0
reserved = 100
total = 100
~~~

**Vì sao đúng?**

1. Inventory chỉ chứa hai primitive int và là **immutable record** trong ví dụ.
2. Mọi phép reserveOne cho **cùng key "book"** đi qua computeIfPresent.
3. Hàm remapping dùng **snapshot old nhất quán của mapping đó**, tạo một Inventory mới hoặc giữ nguyên old nếu không còn vé.
4. Thay mapping được thực hiện theo ngữ nghĩa nguyên tử của computeIfPresent với key tương ứng; các thread không thể cùng commit hai cập nhật dựa trên cùng phiên bản cũ mà làm mất lượt.
5. Reader gọi **map.get("book") một lần**, rồi đọc cả available/reserved trên **cùng snapshot**.
6. Bốn worker thử tổng 200 lần, nhưng chỉ có 100 vé; kết quả cuối vẫn nhất quán.

**Điều kiện:** không được có đường khác sửa mutable state bên trong Inventory. Ở ví dụ này record chỉ có int nên không có reference mutable lộ ra. Nếu record chứa ArrayList có thể sửa từ bên ngoài, **record không tự tạo deep immutability**.

### Đọc hai lần không phải snapshot

~~~java
// Minh họa sai nếu cần dữ liệu cùng một version:
int available = map.get("book").available();
int reserved = map.get("book").reserved();
~~~

Giữa hai lần get, writer có thể thay mapping, khiến hai field được lấy từ **hai Inventory khác nhau**. Hãy:

~~~java
Inventory snapshot = map.get("book");
int available = snapshot.available();
int reserved = snapshot.reserved();
~~~

Mảnh mã trên giả định Inventory đã được khai báo và mapping không null. Một lần get lấy **một object snapshot**; nếu field của nó immutable, các getter sau đó cùng phản ánh phiên bản đó.

## 9. compute không tự khóa mọi object value

Một hiểu nhầm đặc biệt nguy hiểm:

~~~java
// Minh họa: nếu Counter là mutable,
map.compute("x", (key, counter) -> {
    counter.value++;
    return counter;
});
~~~

Bản thân remapping operation được phối hợp theo key. Nhưng nếu thread T2 đang giữ reference cũ:

~~~java
Counter same = map.get("x");
same.value++; // T2 sửa ngoài compute.
~~~

Thì T2 **không bị buộc phải lấy cùng khóa nội bộ** với compute của T1. Việc compute quản lý mapping không khiến mọi caller cầm Counter phải đồng bộ trên object đó.

**Không thiết kế quanh khóa nội bộ của ConcurrentHashMap như một lock công khai cho value.** Muốn mutation in-place an toàn, mọi đường truy cập đến value phải tham gia một giao thức đồng bộ **do ứng dụng định nghĩa và kiểm soát**.

### Remapping function nên ngắn và có kiểm soát

Các API compute/merge có thể phải khóa/điều phối những cập nhật khác trên cùng vùng map trong quá trình remapping. Vì vậy:

- Không gọi mạng hoặc blocking I/O dài bên trong remapping function.
- Không thực hiện side effect không thể retry/idempotent mà chưa xem xét hậu quả khi exception hoặc request gọi lại.
- Không dùng remapping function để cập nhật đệ quy các mapping của **chính map đó**; những thao tác recursive update bị cấm hoặc không có bảo đảm tiến triển và có thể gây IllegalStateException.
- Xử lý rõ ngoại lệ của remapping function: nếu function ném, mapping có thể giữ nguyên theo hợp đồng operation, nhưng side effect đã gây ra bên ngoài không tự rollback.
- **computeIfAbsent** phù hợp để xây value khi key chưa có mapping; sau khi tạo ra một mutable value, mọi lần sử dụng nó vẫn cần thread safety.

**Không coi compute là một giao dịch bao phủ database, external API hoặc nhiều key khác nhau.**

## 10. Giải pháp D: bảo vệ value bằng khóa riêng

Khi value có logic mutable phức tạp, một thiết kế hợp lệ là **value tự quản lý synchronized/lock** trong các method của nó. Tất cả reader/writer phải dùng **cùng protocol**.

~~~java
// Minh họa một value object:
final class SafeCounter {
    private int value;

    synchronized void increment() {
        value++;
    }

    synchronized int get() {
        return value;
    }
}
~~~

Mỗi method synchronized giữ monitor của SafeCounter, ngăn hai thread đồng thời sửa field value thông qua các method ấy; unlock/lock có quan hệ happens-before tương ứng.

**Những điều kiện quan trọng:**

- Field mutable phải **private** hoặc không thể sửa ngoài method được bảo vệ.
- Reader cũng phải dùng synchronized getter hoặc cơ chế visibility phù hợp, không đọc raw field ngoài khóa.
- Nếu một invariant bao trùm nhiều field, cần đặt **toàn bộ check–then–act trong một critical section**, không chỉ synchronized từng getter/setter rồi ghép ở caller.
- Nếu nhiều object value cùng tham gia một nghiệp vụ, một lock per-value có thể không bảo vệ invariant xuyên nhiều key.
- Nếu mapping có thể bị **remove/replace**, thread đang giữ reference value cũ vẫn có thể gọi method trên object cũ. Giao thức khóa của object cũ không tự đồng bộ với value mới.

### Ví dụ 5: value tự bảo vệ dữ liệu

Tệp **SynchronizedValueMapDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;

public class SynchronizedValueMapDemo {
    static final class SafeCounter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int snapshot() {
            return value;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<String, SafeCounter> map =
                new ConcurrentHashMap<>();

        map.put("jobs", new SafeCounter());

        Runnable worker = () -> {
            for (int i = 0; i < 10_000; i++) {
                map.get("jobs").increment();
            }
        };

        Thread first = new Thread(worker);
        Thread second = new Thread(worker);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println(
                "jobs = " + map.get("jobs").snapshot()
        );
    }
}
~~~

~~~bash
javac -encoding UTF-8 SynchronizedValueMapDemo.java
java SynchronizedValueMapDemo
~~~

Stdout:

~~~text
jobs = 20000
~~~

**Tại sao đúng?** Cả hai thread tăng một SafeCounter ổn định và cùng sử dụng monitor của object đó; main đọc qua synchronized snapshot() sau khi join.

**Giới hạn giả định:** mapping "jobs" không bị xóa hoặc thay trong lúc worker chạy. Nếu cần reset, hãy định nghĩa rõ reset đồng bộ với increment, chẳng hạn qua per-key mapping computation hoặc epoch/state object dùng chung theo lifetime thích hợp.

### Dùng ReentrantLock thay synchronized khi nào?

Nếu value cần **tryLock**, timeout, interruptible acquisition, Condition hoặc nhiều critical section có chính sách riêng, **ReentrantLock** có thể phù hợp. Mẫu là **lock.lock() → try → finally unlock()**. Không dùng lock khác nhau mỗi lần gọi; tất cả reader/writer liên quan phải tham gia cùng lock được giữ ổn định trong value.

Không khẳng định ReentrantLock luôn nhanh hơn synchronized. Hiệu quả phụ thuộc contention và workload; ưu tiên cách đơn giản đúng contract.

## 11. Giải pháp E: copy-on-write cho collection nằm trong value

Giả sử map lưu **List<String>** theo key:

~~~java
ConcurrentHashMap<String, java.util.List<String>> map =
        new ConcurrentHashMap<>();

map.put("logs", new java.util.ArrayList<>());
map.get("logs").add("A"); // Unsafe khi có nhiều writer đồng thời.
~~~

ConcurrentHashMap chỉ bảo vệ **reference List** được map giữ, không bảo vệ **ArrayList.add()**. Hai thread có thể tranh kích cỡ, dữ liệu bên trong ArrayList, gây mất phần tử hoặc lỗi cấu trúc.

Một giải pháp cho danh sách **không quá lớn, tần suất ghi thấp** là copy-on-write ở cấp mapping:

~~~java
// Minh họa một mapping mutation:
map.compute("logs", (key, oldList) -> {
    java.util.List<String> next = new java.util.ArrayList<>(
            oldList == null ? java.util.List.of() : oldList
    );
    next.add("new");
    return java.util.List.copyOf(next);
});
~~~

- Mỗi lần compute, code tạo list mới, không sửa list cũ.
- List được publish là **unmodifiable** và phần tử String là immutable.
- Reader có thể giữ reference list cũ như một **snapshot** không bị writer thay đổi.
- Những writer cùng key cập nhật mapping qua compute nên không mất phần tử do thao tác get–modify–put tách rời.
- Chi phí **O(n) copy mỗi lần thêm** có thể rất lớn khi danh sách dài hoặc ghi dày đặc; không coi đây là giải pháp hiệu năng chung.

### Ví dụ 6: thêm vào immutable list bằng compute

Tệp **ImmutableListMapDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

public class ImmutableListMapDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<String, List<String>> map =
                new ConcurrentHashMap<>();

        map.put("events", List.of());

        Runnable add = () -> {
            for (int i = 0; i < 100; i++) {
                map.compute("events", (key, old) -> {
                    List<String> next = new ArrayList<>(old);
                    next.add("e");
                    return List.copyOf(next);
                });
            }
        };

        Thread first = new Thread(add);
        Thread second = new Thread(add);
        first.start();
        second.start();
        first.join();
        second.join();

        List<String> result = map.get("events");
        System.out.println("size = " + result.size());
        System.out.println("immutable = " + rejectsMutation(result));
    }

    static boolean rejectsMutation(List<String> list) {
        try {
            list.add("unexpected");
            return false;
        } catch (UnsupportedOperationException ex) {
            return true;
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableListMapDemo.java
java ImmutableListMapDemo
~~~

Stdout:

~~~text
size = 200
immutable = true
~~~

**Vì sao đúng?** Mỗi phép compute cho cùng key đọc list hiện tại, sao chép, thêm một phần tử và publish list mới. Không writer nào sửa list đã publish. Hai thread chạy 100 lần, kết quả là 200 chuỗi e.

**Lưu ý:** “immutable = true” chỉ chứng minh list API không cho phép thêm; với các phần tử String thì nội dung cũng immutable. Nếu phần tử là một mutable Person/Address, **List.copyOf không deep-copy từng phần tử**. Reader vẫn có thể thấy những thay đổi ngoài ý muốn trên object phần tử.

### Có nên dùng CopyOnWriteArrayList?

**CopyOnWriteArrayList** là collection thread-safe riêng, có snapshot iterator và cơ chế copy khi sửa; có thể phù hợp khi **đọc rất nhiều và ghi ít**. Nếu value trực tiếp là CopyOnWriteArrayList, cập nhật list qua API của chính nó được đồng bộ theo hợp đồng. Nhưng chi phí copy khi ghi và khả năng remove/replace mapping vẫn cần được xét.

Không nhầm **copy-on-write list object** với **compute + thay immutable mapping**: hai kỹ thuật có ranh giới ownership và snapshot khác nhau.

## 12. Concurrent collection làm value cũng cần chọn đúng thao tác

Một số value vốn là concurrent collection:

- **ConcurrentLinkedQueue<E>** hỗ trợ thêm/lấy phần tử đồng thời.
- **ConcurrentHashMap<K2,V2>** lồng trong map có các thao tác thread-safe ở cấp nested map.
- **ConcurrentHashMap.newKeySet()** cung cấp set concurrent.
- **CopyOnWriteArrayList<E>** hữu ích khi đọc nhiều/ghi ít.
- **Collections.synchronizedList(list)** dùng một monitor bao quanh các method, nhưng **khi iterate** cần đồng bộ ngoài theo đúng hợp đồng wrapper.

Ngay cả với concurrent collection làm value, **chuỗi thao tác nhiều bước** vẫn có thể sai:

~~~java
// Minh họa logic race với concurrent collection:
if (!queue.isEmpty()) {
    Item first = queue.poll();
    // first vẫn có thể là null nếu thread khác lấy trước.
}
~~~

Đây là đoạn minh họa giả định queue và Item tồn tại. Để lấy phần tử nếu có, **poll() rồi kiểm tra null** là một operation phù hợp. Nếu cần chờ phần tử, dùng **BlockingQueue.take()** hoặc poll(timeout), không tự spin kiểm tra isEmpty().

**Atomic của từng method không suy ra atomic của toàn bộ workflow.**

## 13. putIfAbsent, computeIfAbsent và sự ổn định của value

Mẫu dễ mắc lỗi:

~~~java
// Minh họa có race khi nhiều thread cùng tạo Counter:
if (map.get(key) == null) {
    map.put(key, new Counter());
}
~~~

Hai thread có thể cùng thấy null rồi cùng put hai Counter khác nhau; thread thứ nhất có thể đã tăng Counter của mình nhưng mapping bị thread thứ hai thay thế. Đây là **lost reference/update do check–then–act**.

**putIfAbsent** cho phép đặt mapping khi chưa có và trả value cũ nếu đã tồn tại. **computeIfAbsent** cho phép tạo value khi thiếu dưới hợp đồng atomic của map cho key đó.

~~~java
// Minh họa:
AtomicInteger counter = map.computeIfAbsent(
        key, k -> new AtomicInteger()
);
counter.incrementAndGet();
~~~

Nếu các key **không bị xóa/thay thế đồng thời**, mọi thread nhận cùng value hiện diện ổn định và thực hiện atomic increment.

### Những quy tắc dành cho mapping function

- Không thực hiện I/O dài hoặc gọi dịch vụ khác bên trong mapping function, vì có thể chặn những update liên quan.
- Không sửa đệ quy mapping của cùng ConcurrentHashMap bên trong remapping callback; JDK có thể ném IllegalStateException khi phát hiện recursive update không thể hoàn tất.
- Không đặt side effect nghiệp vụ không idempotent vào callback mà không hiểu chính xác thời điểm commit và đường lỗi.
- Không trả null khi muốn giữ một value null; ConcurrentHashMap không hỗ trợ null mapping, và null có ý nghĩa bỏ/không tạo mapping tùy API.
- Khi **computeIfAbsent trả một value mutable**, nhiệm vụ bảo vệ field của value **chưa hoàn thành**; phải tiếp tục dùng atomic/lock/confinement.

## 14. Bẫy get → mutate → put và replace

Một anti-pattern:

~~~java
// Minh họa:
Counter c = map.get("x");
c.count++;
map.put("x", c);
~~~

**put() không làm c.count++ atomic.** Nếu hai thread cầm cùng c, phép tăng có thể mất như ví dụ 1. Nếu hai thread mỗi người tạo một bản sao Counter rồi put, người ghi sau có thể ghi đè kết quả người trước.

### Dùng replace có điều kiện

Có thể đọc một **immutable value**, tạo phiên bản mới, rồi gọi:

~~~java
// Minh họa với value immutable:
boolean swapped = map.replace(key, oldValue, newValue);
~~~

Nếu false, cần đọc lại và tính lại. Nhưng **replace(key, oldValue, newValue)** dựa trên điều kiện so sánh value theo hợp đồng Map/ConcurrentHashMap, không phải một CAS reference thuần khi equals khác danh tính. Nếu value dùng **equals trên mutable fields**, việc so sánh có thể có các vấn đề khi field thay đổi đồng thời.

Trong nhiều trường hợp **compute** cho cùng key diễn đạt dễ hiểu hơn một vòng optimistic replace. Nếu cần version/historical change detection, cân nhắc **version trong immutable value** và giao thức rõ ràng.

### equals/hashCode của mutable value

Hash key quan trọng vì map định vị mapping bằng key. **Mutable key** mà equals/hashCode thay đổi khi ở trong map có thể làm lookup khó hoặc sai. Với **value**, việc equals phụ thuộc mutable field có thể làm điều kiện remove(key, expected) và replace(key, expected, replacement) bất ổn dưới cập nhật đồng thời.

Nên dùng **immutable key có equals/hashCode ổn định**. Với conditional replace/remove, cũng nên hiểu rõ equality semantics của value và tránh mutation không đồng bộ.

## 15. Multi-key invariants không tự nguyên tử

ConcurrentHashMap hỗ trợ cập nhật **mapping một key** theo hợp đồng operation. Nhưng nghiệp vụ có thể cần thay hai key cùng lúc.

Ví dụ tài khoản A và B:

~~~text
balance[A] = 100
balance[B] = 200
Tổng tiền phải luôn = 300.

Chuyển 10 từ A sang B:
  A -> 90
  B -> 210
~~~

Nếu sử dụng hai compute độc lập:

~~~java
// Minh họa: hai bước tách rời, không là transaction nhiều key.
balances.compute("A", (k, old) -> old - 10);
balances.compute("B", (k, old) -> old + 10);
~~~

Một thread đọc trong khoảng giữa có thể thấy A=90 và B=200; tổng tạm là 290. Hai lời compute độc lập không tạo một **atomic multi-key transaction**.

Các lựa chọn:

- **Lock** bao phủ cả lần update và các lần đọc cần snapshot, với cùng giao thức cho mọi đường truy cập liên quan.
- Gói cả A/B vào **một immutable aggregate value** dưới **một key** và thay bằng compute/CAS phù hợp nếu bài toán cho phép.
- Thiết kế **owner thread** tuần tự hóa toàn bộ state của hệ thống nhỏ.
- Nếu trạng thái nằm ở **database** hoặc nhiều JVM, dùng transaction/conditional update/optimistic version ở kho dữ liệu có thẩm quyền.

### Atomic snapshot cho cả map không miễn phí

Một vòng lặp đọc hết ConcurrentHashMap đang thay đổi có thể thấy những mapping thuộc các mốc khác nhau. Weakly consistent iterator **không tạo snapshot giao dịch của toàn map**. Nếu cần một ảnh nhất quán trên nhiều key, cần giao thức snapshot riêng.

**Không dùng map.size() rồi so sánh quota** trong chuỗi get → check → put như thể đó là một transaction: nhiều thread có thể xen giữa các bước.

## 16. Stable value identity, reset và generation

Một lớp lỗi không xuất hiện trong ví dụ chỉ có increment là **reset**:

~~~text
Thread 1: lấy reference V1 từ map.get(key)
Thread 2: map.replace(key, V2)
Thread 1: tăng V1
Thread 3: đọc map.get(key) -> V2

Tăng của Thread 1 không còn hiển thị trong mapping hiện hành.
~~~

Trường hợp này không có nghĩa AtomicInteger bị lỗi. Nó cho thấy **atomic theo object** khác **atomic theo key qua các thế hệ value**.

Để thiết kế reset rõ ràng:

1. Định nghĩa **nghĩa của reset**: xóa mọi lượt cũ, bắt đầu thế hệ mới, hay lấy snapshot rồi tiếp tục đếm?
2. Chọn một **version/generation** bất biến cùng giá trị để thread cập nhật kiểm tra đúng đời.
3. Đưa **increment và reset** qua cùng một giao thức per-key mapping computation nếu cần linearizable semantics theo key.
4. Hoặc giữ value object cố định và làm reset/increment dưới cùng lock nếu contract cho phép.
5. Đảm bảo reader hiểu số đọc là của **phiên bản nào**.
6. Nếu có side effect ở DB hoặc nhiều JVM, Java map không tự tạo transaction xuyên process.

**Đừng hứa một bộ đếm phản ánh tất cả increment trong lịch sử** nếu hệ thống đồng thời cho phép remove/recreate cùng key mà không có quy tắc về increment đã cầm reference cũ.

## 17. Value object thoát ra ngoài và encapsulation

Giả sử class Cache giữ một ConcurrentHashMap và trả chính value mutable cho caller:

~~~java
// Minh họa class không nên trả reference trực tiếp:
public List<String> getEvents(String key) {
    return events.get(key); // Caller có thể add/remove.
}
~~~

Nếu caller nhận ArrayList và sửa trực tiếp, mọi invariant mà Cache tưởng chỉ được kiểm soát qua compute đã bị phá. Dù Cache writer khác dùng compute chuẩn, caller vẫn có thể mutate list nằm trong mapping hiện hành.

Các cách bảo vệ API:

- Trả **immutable snapshot** hoặc read-only DTO với phần tử immutable.
- Chỉ expose **operation có ngữ nghĩa** như addEvent(key, event), reserve(key), snapshot(key).
- Không đưa ra reference đến lock, collection mutable hay object nội bộ nếu caller có thể sửa ngoài giao thức.
- Nếu trả live concurrent collection, ghi rõ contract: caller được phép làm thao tác nào, phép duyệt và snapshot có consistency mức nào.
- Thiết kế **immutable value** từ đầu để giảm diện tích API phải đồng bộ hóa.

**Encapsulation là một phần của thread safety.** Không thể kiểm soát mọi mutation nếu bất kỳ caller nào cũng giữ reference mutable rồi ghi tùy ý.

## 18. Các lỗi với nested object graph

Đôi khi value bản thân là một object có field final nhưng trỏ tới object mutable:

~~~java
record UserStats(String user, List<Integer> values) {}
~~~

Record này không tự immutable sâu. Nếu values trỏ tới ArrayList được share và caller khác add vào, stats vẫn thay đổi một cách quan sát được dù field values là final.

Để có snapshot thực sự:

~~~java
record UserStats(String user, List<Integer> values) {
    UserStats {
        values = List.copyOf(values);
    }
}
~~~

Nếu Integer immutable, bản sao list là một tầng bất biến phù hợp. Nếu phần tử là mutable object, cần **defensive copy sâu hơn hoặc immutable element type** theo yêu cầu.

Các nested map/list tương tự: ConcurrentHashMap ở tầng ngoài không bảo vệ inner HashMap, ArrayList hoặc mutable element mà thread có thể chia sẻ.

### SynchronizedList là giải pháp đúng tới đâu?

**Collections.synchronizedList(list)** bảo vệ từng method được gọi trên wrapper. Nhưng khi duyệt:

~~~java
// Minh họa với synchronizedList đã tạo:
synchronized (synchronizedList) {
    for (String value : synchronizedList) {
        process(value);
    }
}
~~~

Cần giữ monitor tương ứng quanh iteration theo hợp đồng wrapper. Nếu caller giữ reference list gốc rồi sửa ngoài wrapper, vẫn phá giao thức đồng bộ hóa.

## 19. Chọn giải pháp theo invariant

| Nhu cầu | Lựa chọn khởi đầu | Giới hạn cần nhớ |
| --- | --- | --- |
| Tăng số lượt độc lập theo key | ConcurrentHashMap<String, AtomicInteger> | Remove/replace cùng lúc cần semantics riêng |
| Thống kê cộng nhiều dưới contention | ConcurrentHashMap<String, LongAdder> | sum() đang cập nhật không là atomic snapshot |
| Nhiều field phải đổi nguyên khối trong cùng key | Immutable record + compute/computeIfPresent | Không bao phủ nhiều key hoặc external side effect |
| Mutable object với critical section phức tạp | Synchronized method / ReentrantLock trong value | Mọi reader/writer phải dùng cùng giao thức |
| List nhỏ đọc nhiều, ghi ít | Immutable list + compute / CopyOnWriteArrayList | Copy mỗi lần ghi, shallow immutability |
| Queue nhận event nhiều thread | ConcurrentLinkedQueue / BlockingQueue | Chọn theo có cần blocking/backpressure |
| Cập nhật trạng thái của hai key cùng lúc | Lock cho aggregate hoặc transaction ở nơi lưu dữ liệu | compute từng key không là multi-key atomicity |
| Một owner xử lý mọi update | Single-thread executor/actor-style ownership | Caller không được mutate state trực tiếp |
| Đọc snapshot của toàn map đang thay đổi | Explicit snapshot protocol, lock/version/aggregate | Weakly consistent iteration không đủ |

**Mấu chốt chọn lựa:** xác định **đơn vị bất biến** cần bảo vệ. Nếu bất biến nằm hoàn toàn trong một AtomicInteger, chọn atomic. Nếu nằm trên hai field của một record, dùng immutable snapshot + compute hoặc lock. Nếu nằm trên nhiều key hoặc external system, cần giao thức cấp cao hơn.

## 20. Thread confinement vẫn là một lựa chọn

Thay vì nhiều thread trực tiếp sửa value trong map, có thể dùng **một worker sở hữu từng nhóm state**; các thread khác gửi command cho worker, sau đó đọc kết quả qua Future hoặc message.

Ưu điểm:

- Không có nhiều writer đồng thời trên cùng mutable object.
- Invariant nhiều bước có thể diễn đạt tuần tự.
- Giảm nhu cầu khóa fine-grained ở mỗi field.

Nhược điểm:

- Một worker có thể thành bottleneck nếu tải cao.
- Queue và shutdown cần kiểm soát để không mất request.
- Caller không được bypass owner bằng cách gọi value.setXXX trực tiếp.
- Nếu nhiều process/JVM cùng thao tác DB, owner trong một JVM không đủ.

**ConcurrentHashMap có thể vẫn dùng làm registry tra cứu owner**, nhưng correctness của mutable state do **ownership protocol** quyết định.

## 21. Performance: thread-safe không có nghĩa luôn nhanh

Có nhiều cách đúng đắn nhưng trade-off khác nhau:

- **AtomicInteger** có thể chịu contention khi mọi thread cùng tăng một key nóng.
- **LongAdder** thường cải thiện throughput cho thống kê hot key, đổi lại sum đang cập nhật không tuyến tính.
- **compute + immutable record** dễ giữ snapshot nhất quán nhưng tạo object mới và có thể làm nhiều update cùng key tuần tự.
- **synchronized value** đơn giản cho critical section rõ ràng, nhưng giữ khóa lâu gây contention.
- **Copy-on-write list** thuận tiện cho đọc nhiều, ghi ít; thêm một item vào list lớn có thể cần copy O(n).
- **Nested concurrent collections** có overhead riêng và không tự bảo vệ compound operation.

Khi benchmark:

1. Xác định invariant và kiểm chứng kết quả trước.
2. Đo trên cả **hot key** và **nhiều key phân tán**.
3. Tách CPU-bound operation khỏi blocking I/O.
4. Warm up JVM và chạy nhiều lần, tránh benchmark một lần.
5. Đo throughput, p95/p99 latency, contention, allocations/GC và memory.
6. Cân nhắc **JMH** cho microbenchmark quan trọng, tránh dead-code elimination.
7. Đánh giá độ phức tạp và khả năng review code, không chỉ tốc độ tối đa.

**Một giải pháp nhanh nhưng đọc snapshot sai vẫn không hợp lệ.**

## 22. Kiểm thử concurrency đúng cách

**Test logic, không test xác suất.**

### Dùng CountDownLatch để dàn lịch lost update

Ví dụ 1 đảm bảo cả hai thread đã đọc cùng giá trị cũ trước khi được phép ghi. Đây là phép chứng minh rõ ràng rằng map-level thread safety không giải quyết lost update.

### Dùng join/Future để kiểm tra kết quả cuối

Ví dụ 2–6 chỉ in sau khi toàn bộ writer kết thúc. Vì vậy stdout thể hiện một trạng thái terminal đã biết, tránh phỏng đoán thời điểm thread scheduler chạy.

### Stress test và model checking

Stress test với số luồng lớn, nhiều key và nhiều lần chạy có thể giúp phát hiện bug, nhưng **không chứng minh code luôn đúng**. Phải kết hợp lập luận theo:

- Mọi đường **read/write** đối với value.
- **Happens-before** và visibility của các update.
- Tính nguyên tử của **toàn bộ thao tác nghiệp vụ**.
- Trường hợp **remove/replace/reset** cùng lúc.
- Deep immutability và API value reference escaping.
- Quy tắc exception/retry/cancellation và tính idempotent của side effect.

### Các phép thử bổ sung nên có

- Hai thread cùng compute cho một key.
- Một thread đọc snapshot trong lúc một thread khác update.
- Một thread remove/replace trong lúc người khác giữ reference cũ.
- Nhiều thread vừa gọi computeIfAbsent vừa tăng counter.
- Duyệt map trong lúc writer thay mappings: chỉ assert contract weakly consistent, không assert snapshot ổn định.
- Nested list/map và phần tử mutable.
- Compound invariant nhiều key.
- ExecutionException/InterruptedException và cleanup trên đường lỗi nếu ứng dụng có task bất đồng bộ.

## 23. Anti-pattern tóm tắt

| Anti-pattern | Vì sao sai | Hướng khắc phục |
| --- | --- | --- |
| map.get(key).count++ | Field của V không atomic | AtomicInteger hoặc synchronized value |
| map.get(key).list.add(x) với ArrayList | ArrayList không thread-safe | Concurrent collection hoặc immutable copy-on-write |
| get → mutate → put | Mutation xảy ra ngoài map atomic operation | compute với immutable replacement hoặc lock phù hợp |
| get null → put(new Counter()) | Hai thread có thể tạo/hủy mất reference | computeIfAbsent/putIfAbsent |
| compute rồi mutate same value ngoài compute | Internal map synchronization không bảo vệ external references | Encapsulate mutation, immutable value, cùng lock |
| record chứa ArrayList thì cho là immutable | Record chỉ shallow immutable | Defensive copy và phần tử immutable |
| Map value là LongAdder thì reset an toàn tự động | Old reference có thể được tăng sau replace | Generation/epoch/reset protocol |
| size() rồi put để giới hạn quota | Chuỗi check–then–act không atomic | Admission control/permit riêng |
| Hai compute trên hai key là transaction | Có trạng thái trung gian nhiều key | Lock/aggregate/DB transaction |
| Iterator của CHM là snapshot giao dịch | Weakly consistent | Giao thức snapshot phù hợp |
| Trả mutable value trực tiếp cho caller | Caller có thể bypass mọi invariant | Trả snapshot/operation thay vì live mutable |
| equals của value dựa vào field sửa đồng thời | Điều kiện replace/remove khó bảo đảm | Immutable value, version và equality semantics ổn định |
| Tưởng volatile int++ an toàn | Visibility không tạo read-modify-write atomic | Atomic increment hoặc lock |
| Dùng synchronized getter rồi writer không khóa | Giao thức reader/writer không đồng nhất | Tất cả đường truy cập phải dùng cùng lock |
| Đổi mọi thứ sang concurrent collection | Compound invariant vẫn có thể sai | Chọn atomic unit đúng theo nghiệp vụ |

## 24. Checklist review code

**Trạng thái và ownership:**

- [ ] Value có immutable thật không hay chỉ final reference?
- [ ] Có nested object mutable nào lộ ra ngoài không?
- [ ] Caller có giữ reference live value và sửa trực tiếp không?
- [ ] Key có immutable equals/hashCode ổn định không?
- [ ] Mapping có thể remove/replace/reset trong lúc value đang được dùng không?

**Đồng bộ hóa:**

- [ ] Mỗi phép increment/check–then–act có đơn vị atomic đúng không?
- [ ] Có chuỗi thao tác trên nhiều field cần cùng critical section không?
- [ ] Nếu dùng synchronized/ReentrantLock, mọi reader/writer đều dùng cùng object lock?
- [ ] Nếu dùng compute, callback có ngắn, không recursive update hoặc I/O chờ dài?
- [ ] Nếu dùng LongAdder, caller có hiểu sum() đang cập nhật không phải snapshot nguyên tử?
- [ ] Nếu dùng immutable snapshot, reader chỉ get một reference cho các field cùng phiên bản?
- [ ] Nếu dùng collection thread-safe bên trong V, có compound operation nào vẫn cần khóa không?

**Nghiệp vụ và vận hành:**

- [ ] Có invariant trải nhiều key hoặc nhiều JVM/DB không?
- [ ] Có chính sách generation/version khi reset?
- [ ] Có phân biệt current mapping với old reference còn được người khác giữ?
- [ ] Có stress test, deterministic concurrency test và xử lý exception?
- [ ] Đã đo throughput và contention dưới workload hot-key thực tế?
- [ ] API không hứa điều gì CHM không cung cấp, chẳng hạn snapshot toàn map hay transaction nhiều key?

## 25. Câu hỏi tự kiểm tra

**1. ConcurrentHashMap<String, Counter> có làm Counter.count++ an toàn không?**  
Không. Map bảo vệ mapping; phép tăng trên field int mutable cần cơ chế riêng.

**2. Hai thread lấy cùng value rồi gọi AtomicInteger.incrementAndGet() có đúng không?**  
Có, nếu cùng AtomicInteger và chỉ cần increment nguyên tử trên object ấy. Nhưng remove/replace mapping có thể khiến increment trên old reference không còn được phản ánh ở map hiện hành.

**3. compute(key, ...) có bảo đảm mọi sửa đổi trên value object ngoài callback cũng được khóa không?**  
Không. Nó phối hợp mapping theo key trong lời gọi compute, không cưỡng chế những thread có reference value phải dùng cùng đồng bộ hóa.

**4. LongAdder.sum() có phải atomic snapshot lúc nhiều thread đang increment không?**  
Không. Đọc tổng sau khi các writer đã kết thúc thì phù hợp để lấy kết quả cuối.

**5. Với hai field available và reserved phải cùng thay đổi, có nên dùng hai AtomicInteger riêng không?**  
Nếu yêu cầu reader thấy invariant nhất quán, không nên cập nhật tách rời mà không có giao thức bổ sung. Dùng immutable record + compute hoặc lock bao phủ cả hai.

**6. List.copyOf(list) có làm object phần tử bên trong list immutable không?**  
Không. Nó không deep-copy mutable elements; cần immutable element hoặc defensive copy phù hợp.

**7. Vì sao đọc map.get(key) hai lần để lấy hai field có thể sai?**  
Mapping có thể bị thay giữa hai lần đọc, làm kết hợp hai phiên bản. Hãy lấy snapshot immutable một lần.

**8. Dùng computeIfAbsent rồi get() của AtomicInteger có giải quyết reset concurrent không?**  
Không tự động. Thread có thể cầm old value rồi cập nhật sau khi mapping thay thế.

**9. Hai compute cho hai key có tạo multi-key transaction không?**  
Không. Reader có thể thấy trạng thái trung gian; cần giao thức cấp cao hơn.

**10. SynchronizedList làm việc iterate hoàn toàn tự động thread-safe không?**  
Từng method được wrapper đồng bộ, nhưng iteration cần đồng bộ ngoài theo hợp đồng để tránh các cập nhật xen giữa.

**11. Đọc toàn bộ ConcurrentHashMap bằng forEach có phải ảnh chụp tại một thời điểm không?**  
Không. Duyệt là weakly consistent và có thể thấy một phần các cập nhật đồng thời.

**12. Khi nào nên ưu tiên immutable value?**  
Khi muốn readers lấy snapshot nhất quán dễ kiểm chứng và updates có thể diễn đạt bằng thay mapping nguyên khối qua compute/merge.

**13. Vì sao put sau khi mutate không làm mutation trở nên atomic?**  
Vì mutation đã xảy ra trên object trước put và có thể tranh với thread khác; put chỉ cập nhật mapping.

**14. Nếu một key có hot counter lớn, nên luôn dùng LongAdder không?**  
Không. Nếu cần CAS/check-quota/linearizable get-and-increment hoặc reset chính xác, AtomicLong hoặc giao thức khác có thể đúng hơn.

**15. Điều gì quan trọng hơn việc chọn class concurrent?**  
Xác định rõ bất biến, đơn vị atomic, quyền sở hữu mutable state, memory consistency và các đường đọc/ghi.

## 26. Tổng kết

**ConcurrentHashMap chỉ giải quyết thread safety ở cấp map/mapping**, không tự biến Counter, ArrayList, nested HashMap hay object graph đặt trong value thành thread-safe. Một lời gọi map.get có thể an toàn, nhưng code tiếp tục **sửa object trả về** vẫn cần hợp đồng riêng.

Các lựa chọn phổ biến:

1. **AtomicInteger/AtomicLong** cho một giá trị có read-modify-write nguyên tử.
2. **LongAdder** cho thống kê cập nhật nhiều, chấp nhận giới hạn snapshot.
3. **Immutable record + compute/merge** để cập nhật trọn invariant trong một key.
4. **synchronized/ReentrantLock** để bảo vệ mutable value theo cùng giao thức đọc/ghi.
5. **Immutable copy-on-write hoặc concurrent collection** cho nested collection, phù hợp với mẫu tải.
6. **Owner/transaction cấp cao hơn** khi invariant trải nhiều key hoặc nhiều process.

Hãy luôn kiểm tra **get → mutate → put**, object reference escaping, remove/replace/reset, shallow immutability, weakly consistent iteration và side effect bên ngoài. **Sự an toàn của collection bên ngoài không thể thay thế thiết kế đúng cho trạng thái mutable bên trong value.**
