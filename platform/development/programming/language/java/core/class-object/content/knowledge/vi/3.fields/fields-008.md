# Vai trò của `volatile` và `transient` khi khai báo trường trong Java

Khi khai báo **field (trường dữ liệu)** của một class Java, hai modifier `volatile` và `transient` đều có thể xuất hiện trước tên kiểu, nhưng giải quyết **hai bài toán hoàn toàn khác nhau**:

- **`volatile`** liên quan đến **mô hình bộ nhớ khi nhiều thread đọc/ghi cùng một field**. Nó mang bảo đảm về khả năng nhìn thấy (*visibility*) và thứ tự thao tác (*ordering*) được định nghĩa bởi *Java Memory Model* (JMM).
- **`transient`** liên quan đến **Java Object Serialization**. Với cơ chế tuần tự hóa mặc định của Java, một instance field được đánh dấu `transient` sẽ **không được lưu vào biểu diễn tuần tự hóa**, nên khi khôi phục đối tượng, field này có giá trị mặc định của kiểu, trừ khi code khôi phục xử lý nó theo cách riêng.

Điểm quan trọng: `volatile` **không có nghĩa “không lưu xuống đĩa”**, `transient` **không có nghĩa “an toàn giữa nhiều luồng”**, và cả hai đều không tự tạo ra một thiết kế hoàn chỉnh nếu vấn đề thực tế phức tạp hơn.

Bài này dùng Java 17+ và tập trung vào ý nghĩa của hai modifier **khi khai báo field**, cách vận dụng, giới hạn và lỗi thường gặp.

## 1. Bảng đối chiếu nhanh

| Tiêu chí | `volatile` | `transient` |
| --- | --- | --- |
| Mục đích chính | Kiểm soát visibility và ordering của thao tác đọc/ghi field trong môi trường đa luồng | Loại field khỏi quá trình tuần tự hóa mặc định bằng `ObjectOutputStream` |
| Lĩnh vực | Đồng thời (*concurrency*), Java Memory Model | Lưu/khôi phục trạng thái (*Java Object Serialization*) |
| Áp dụng cho | Field của class, có thể là instance hoặc static | Field của class, chủ yếu hữu ích với instance field |
| Giá trị trong RAM | Vẫn là field bình thường, có thể đọc/ghi | Vẫn là field bình thường, có thể đọc/ghi |
| Khi nhiều thread truy cập | Đọc/ghi volatile có ràng buộc đồng bộ bộ nhớ theo JMM | Không tự tạo visibility, atomicity hay synchronization |
| Khi tuần tự hóa mặc định | Vẫn được tuần tự hóa nếu là instance field không `transient` và trạng thái serializable | Không được tuần tự hóa mặc định |
| Bảo đảm `counter++` nguyên tử? | **Không** | **Không** |
| Có thể kết hợp? | Có thể khai báo `transient volatile` (hoặc `volatile transient`) | Có thể kết hợp, hai vai trò độc lập |

Ví dụ khai báo:

~~~java
import java.io.Serializable;

class TaskState implements Serializable {
    private static final long serialVersionUID = 1L;

    private volatile boolean running = true;
    private transient String temporaryToken;
    private transient volatile Object cachedSnapshot;
}
~~~

Đây là **đoạn minh họa**, không phải chương trình chạy độc lập. `running` là instance field có semantics volatile; vì không transient, field này vẫn thuộc trạng thái được lưu bởi Java Serialization mặc định. `temporaryToken` không được lưu mặc định, nhưng không có đảm bảo đồng bộ bộ nhớ. `cachedSnapshot` kết hợp cả hai: tham chiếu được truy cập theo volatile semantics khi chương trình chạy và bị bỏ qua khi tuần tự hóa mặc định.

Lưu ý: nếu field transient cần tái tạo sau khi đọc object, có thể thiết kế bước khởi tạo lại; riêng `transient` không tự làm việc này.

## 2. Vì sao cần `volatile`?

Hai thread có thể truy cập cùng một biến trạng thái. Nếu một thread liên tục kiểm tra cờ `running` và thread khác sửa cờ, chương trình phải có **quan hệ đồng bộ hợp lệ** để đảm bảo thread kiểm tra nhận thấy thay đổi theo quy tắc JMM.

Ví dụ đoạn mã cố ý thiếu đồng bộ:

~~~java
class UnsafeStopFlag {
    private boolean running = true;

    void work() {
        while (running) {
            // Thực hiện công việc hoặc chờ
        }
    }

    void stop() {
        running = false;
    }
}
~~~

Nếu một thread gọi `work()` và thread khác gọi `stop()`, đây là **data race** trên `running`. Không thể dựa vào việc “hai thread cùng ở trên một máy” để khẳng định vòng lặp sẽ nhận thấy thay đổi. JVM/JIT và CPU được phép tối ưu trong giới hạn JMM; thiếu đồng bộ làm chương trình không có bảo đảm visibility cần thiết.

Một sửa đổi cho trường hợp **cờ đơn**:

~~~java
class StopFlag {
    private volatile boolean running = true;

    void work() {
        while (running) {
            Thread.onSpinWait();
        }
    }

    void stop() {
        running = false;
    }
}
~~~

`volatile` khiến thao tác ghi `running = false` và lần đọc volatile tiếp theo chịu các quy tắc đồng bộ bộ nhớ. Tuy nhiên, code chỉ minh họa việc truyền tín hiệu: đây **không phải worker loop hiệu quả** cho ứng dụng thực tế vì vòng lặp bận có thể tiêu tốn CPU. Nếu cần chờ hoặc đánh thức thread, cân nhắc `interrupt`, `BlockingQueue`, `CountDownLatch`, `Condition` hoặc API cao hơn tùy bài toán.

**Không hiểu `volatile` là “bắt buộc CPU luôn đọc trực tiếp RAM”**. Đây là một khái niệm trong Java Memory Model; JVM có thể thực hiện bằng các cơ chế phần cứng và tối ưu hợp lệ, miễn giữ đúng ngữ nghĩa JMM. Không cần dựa vào mô hình “cache thread” quá đơn giản để giải thích correctness.

## 3. Ba tính chất quan trọng của `volatile`

### 3.1. Visibility: nhìn thấy lần ghi được đồng bộ

Một thao tác **ghi** vào volatile field và thao tác **đọc** volatile field có các ràng buộc về visibility. Nếu thread xuất bản một giá trị trước khi ghi cờ volatile, và thread khác quan sát tín hiệu qua lần đọc volatile tương ứng, các thao tác trước lúc xuất bản cũng được bảo đảm thấy theo quan hệ *happens-before*.

### 3.2. Ordering và `happens-before`

Theo Java Memory Model, một **lần ghi volatile** *synchronizes-with* các lần **đọc sau đó** của cùng field theo thứ tự đồng bộ; quan hệ này góp phần tạo ra *happens-before*. Trong một thread, các hành động đi trước trong thứ tự chương trình cũng có quan hệ *happens-before* với hành động đi sau.

Ví dụ:

~~~java
class MessageBox {
    int message;
    volatile boolean ready;
}
~~~

Thread gửi thực hiện theo thứ tự:

~~~java
box.message = 42;
box.ready = true;
~~~

Thread nhận thực hiện:

~~~java
if (box.ready) {
    System.out.println(box.message);
}
~~~

Đây là các **mảnh code minh họa trong ngữ cảnh đã có `box`**, chưa phải chương trình độc lập. Khi thread nhận đọc được `ready == true` được xuất bản từ thread gửi và không có các ghi tranh chấp khác làm thay đổi điều kiện, việc ghi `message = 42` trước thao tác ghi volatile có quan hệ *happens-before* với lần đọc `message` của thread nhận. Vì vậy trường `message` **không cần tự là volatile** cho lần truyền một chiều này.

Sơ đồ:

~~~text
Thread gửi                         Thread nhận
-----------                        --------------------
message = 42
    |
    v  program order
ready = true  -- volatile -->   đọc ready == true
                                        |
                                        v program order
                                    đọc message
                                    (nhận 42)
~~~

Tuy nhiên:

- Nếu thread gửi đặt `ready = true` **trước** khi ghi `message = 42`, lần đọc cờ không tự bảo đảm thấy phép ghi dữ liệu xảy ra sau đó.
- Nếu sau khi xuất bản vẫn có các thread tiếp tục ghi `message` mà thiếu đồng bộ, code có thể lại chứa race. Cờ volatile đơn lẻ không biến mọi truy cập dữ liệu khác thành thread-safe.
- Nếu một field đại diện cho **nhiều phiên bản dữ liệu thay đổi liên tục**, chỉ một cờ volatile có thể không đủ làm giao thức. Có thể dùng immutable snapshot được thay thế qua volatile reference hoặc công cụ đồng bộ thích hợp.

### 3.3. Đọc/ghi một giá trị volatile có tính atomic

Mỗi thao tác **đọc hoặc ghi một volatile field** là atomic theo quy tắc tương ứng của Java, kể cả khi field là `long` hoặc `double`. Với tham chiếu volatile, giá trị tham chiếu được đọc/ghi nguyên vẹn.

Nhưng một **biểu thức nhiều bước** không tự động trở thành một thao tác atomic. Đặc biệt:

~~~java
class Counters {
    volatile int count;

    void increment() {
        count++; // ĐỌC -> CỘNG 1 -> GHI: không atomic như một tổng thể
    }
}
~~~

Đây là đoạn minh họa. Hai thread cùng gọi `increment()` có thể cùng đọc một giá trị rồi cùng ghi kết quả giống nhau, dẫn đến **lost update**. `volatile` có visibility/order semantics nhưng không đủ để thực hiện phép cộng đồng thời không mất dữ liệu.

## 4. Ví dụ chạy được: xuất bản dữ liệu bằng `volatile`

Lưu nội dung sau thành **`VolatileVisibilityDemo.java`**:

~~~java
public class VolatileVisibilityDemo {
    static final class MessageBox {
        int message;
        volatile boolean ready;
    }

    public static void main(String[] args) throws InterruptedException {
        MessageBox box = new MessageBox();

        Thread reader = new Thread(() -> {
            while (!box.ready) {
                Thread.onSpinWait();
            }
            System.out.println("message = " + box.message);
        });

        Thread writer = new Thread(() -> {
            box.message = 42;
            box.ready = true;
        });

        reader.start();
        writer.start();

        writer.join();
        reader.join();
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac VolatileVisibilityDemo.java
java VolatileVisibilityDemo
~~~

**Stdout mong đợi khi cả hai thread được thực thi bình thường:**

~~~text
message = 42
~~~

Giải thích:

1. `ready` là boolean instance field, mặc định `false`; `message` mặc định `0`.
2. Thread đọc liên tục đọc volatile field `ready` cho tới khi thấy `true`. `Thread.onSpinWait()` là gợi ý hiệu năng cho JVM/CPU, không phải phép đồng bộ hay lời hứa nhường CPU.
3. Thread ghi đặt `message = 42` rồi ghi volatile `ready = true`.
4. Khi reader đọc thấy `ready == true`, các ghi đi trước phép ghi volatile ở thread writer có quan hệ *happens-before* tới thao tác sau lần đọc volatile ở reader. Vì vậy reader in `42`.
5. `join()` giúp main chờ hai thread kết thúc. Trong thực tế, **không nên dùng busy-spin kéo dài** chỉ để đợi tín hiệu; ví dụ được chọn để cô lập quy tắc volatile.

Thứ tự thread chạy do scheduler quyết định; JMM đảm bảo giá trị dữ liệu khi reader quan sát tín hiệu hợp lệ, nhưng không bảo đảm lịch thực thi hoặc thời gian hoàn thành theo đồng hồ.

## 5. `volatile` không thay thế `synchronized` hoặc atomic class

Cân nhắc phép tăng bộ đếm:

~~~java
class UnsafeCounter {
    volatile int count;

    void increment() {
        count++;
    }
}
~~~

Nếu hai thread bắt đầu cùng giá trị 5, chúng có thể cùng đọc 5, cùng tính 6 và cùng ghi 6. Kết quả cuối 6 thay vì 7. Không nên viết bài kiểm thử rồi kết luận “đôi khi ra đúng thì mã là thread-safe”.

Khi cần atomic read-modify-write của một bộ đếm đơn giản, có thể dùng `AtomicInteger`:

**Tệp `AtomicCounterDemo.java`:**

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    private static final AtomicInteger COUNT = new AtomicInteger();

    public static void main(String[] args) throws InterruptedException {
        Runnable job = () -> {
            for (int i = 0; i < 1_000; i++) {
                COUNT.incrementAndGet();
            }
        };

        Thread first = new Thread(job);
        Thread second = new Thread(job);

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("count = " + COUNT.get());
    }
}
~~~

Chạy:

~~~bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
~~~

Stdout:

~~~text
count = 2000
~~~

`incrementAndGet()` thực hiện cập nhật atomically, nên hai thread tăng tổng cộng 2000 lần mà không mất cập nhật. Một trường `AtomicInteger` có thể khai báo là `final` vì giữ nguyên **tham chiếu** tới đối tượng atomic; giá trị bên trong AtomicInteger vẫn có thể đổi.

**Chọn công cụ phù hợp:**

| Nhu cầu | Công cụ thường phù hợp |
| --- | --- |
| Cờ kết thúc, trạng thái boolean đơn lẻ được chia sẻ | `volatile boolean`, nếu giao thức đủ đơn giản |
| Xuất bản một tham chiếu snapshot immutable đã xây dựng hoàn chỉnh | `volatile` reference hoặc `AtomicReference` tùy thao tác cần |
| Bộ đếm có nhiều thread tăng/giảm | `AtomicInteger`, `AtomicLong` hoặc cơ chế đồng bộ phù hợp |
| Cập nhật nhiều field liên quan như một giao dịch logic | `synchronized`, lock hoặc cấu trúc đồng bộ thích hợp |
| Chờ điều kiện thay đổi mà không quay CPU | `BlockingQueue`, `Condition`, `CountDownLatch`, các utility tương ứng |
| Thao tác nhiều bước cần kiểm tra rồi cập nhật không bị race | Lock hoặc compare-and-set loop phù hợp, không chỉ `volatile` |

`synchronized` vừa cung cấp mutual exclusion vừa tạo quan hệ visibility/order; `volatile` không khóa khu vực code và không ngăn hai thread đồng thời đi vào một method.

## 6. Những giới hạn quan trọng của `volatile`

### 6.1. Volatile reference không làm object con trở nên thread-safe

~~~java
class Inventory {
    int amount;
}

class Holder {
    volatile Inventory inventory = new Inventory();
}
~~~

Đây là đoạn minh họa. Field `inventory` được đọc/ghi theo volatile semantics, nhưng `inventory.amount++` **không trở thành atomic**. Nếu nhiều thread sửa cùng object `Inventory`, vẫn phải xử lý tranh chấp.

Tương tự:

~~~java
class Metrics {
    volatile int[] totals = new int[2];

    void incrementFirst() {
        totals[0]++; // không phải phép tăng volatile/atomic
    }
}
~~~

`volatile` áp dụng cho **field tham chiếu mảng `totals`**, **không tự áp dụng cho phần tử `totals[0]`**. Mỗi phần tử mảng không thể được khai báo `volatile` trực tiếp bằng cú pháp tương đương. Nếu cần primitive array với thao tác atomic theo chỉ số, có thể tìm hiểu `AtomicIntegerArray`.

### 6.2. Các thao tác ghép cần nhất quán nhiều field

Giả sử trạng thái có `int width` và `int height`, và nhiều thread liên tục cập nhật cả hai. Một reader đọc từng field, kể cả mỗi field volatile, vẫn có thể lấy một giá trị từ phiên bản cũ và giá trị kia từ phiên bản mới.

Một cách mô hình hóa hợp lý khi dữ liệu ít thay đổi là **xuất bản snapshot bất biến qua một volatile reference**:

~~~java
record Size(int width, int height) { }

class ScreenState {
    private volatile Size current = new Size(800, 600);

    void resize(int width, int height) {
        current = new Size(width, height);
    }

    Size snapshot() {
        return current;
    }
}
~~~

Đây là đoạn minh họa, không có `main`. `record Size` chứa hai `int` và không có mutable nested data nên thể hiện snapshot bất biến hữu ích. Mỗi lần đọc `snapshot()` nhận **một tham chiếu snapshot** đã được xuất bản; code sử dụng `size.width()` và `size.height()` từ **cùng giá trị `size`** sẽ có cặp nhất quán của cùng phiên bản. Ngược lại, nếu hai lần gọi `snapshot()` khác nhau, hai kết quả có thể thuộc hai phiên bản.

Nếu cần cập nhật có điều kiện như “chỉ đổi nếu snapshot hiện tại vẫn là A”, phép gán volatile thường chưa đủ; cân nhắc `AtomicReference.compareAndSet` hoặc lock.

### 6.3. Double-checked locking

`volatile` cũng là thành phần cần thiết trong pattern **double-checked locking** tạo instance lười trên Java 5+:

~~~java
class ServiceRegistry {
    private static volatile Service instance;

    static Service getInstance() {
        Service local = instance;
        if (local == null) {
            synchronized (ServiceRegistry.class) {
                local = instance;
                if (local == null) {
                    local = new Service();
                    instance = local;
                }
            }
        }
        return local;
    }

    private static final class Service {
    }
}
~~~

Đây là đoạn minh họa. Field `instance` volatile giúp xuất bản object đã được khởi tạo đúng theo mô hình bộ nhớ hiện đại; `synchronized` đảm bảo hai thread không đồng thời tạo các instance ở đoạn critical section. **Chỉ thêm `volatile` mà bỏ lock không đảm bảo chỉ một instance**, vì check rồi tạo là nhiều bước.

Trong nhiều ứng dụng, cách đơn giản hơn là initialization-on-demand holder, enum singleton hoặc dependency injection. Không cần chọn double-checked locking nếu bài toán không đòi hỏi.

## 7. `transient`: bỏ qua field trong Java Object Serialization mặc định

Java có cơ chế tuần tự hóa đối tượng với `java.io.Serializable` và `ObjectOutputStream` / `ObjectInputStream`. Với một đối tượng Serializable thông thường, cơ chế **default serialization** ghi trạng thái của các instance field **không static và không transient** đủ điều kiện. Field transient không được đưa vào phần dữ liệu field mặc định.

~~~java
import java.io.Serializable;

class LoginSession implements Serializable {
    private static final long serialVersionUID = 1L;

    String username;                 // được lưu theo mặc định
    int loginCount;                  // được lưu theo mặc định
    transient String sessionToken;   // bị bỏ qua theo mặc định
    transient int cachedRiskScore;  // bị bỏ qua theo mặc định
}
~~~

Đây là đoạn khai báo, chưa phải chương trình chạy riêng.

**Những lưu ý về phạm vi:**

- `transient` có ý nghĩa thực tế ở **instance field** của đối tượng được xử lý bởi Java Serialization.
- **Static field không thuộc trạng thái riêng của object nên không được serial hóa mặc định**, dù có hoặc không có `transient`. Viết `static transient` thường thừa.
- Một field `volatile` **vẫn được serial hóa mặc định** nếu đó là instance field không transient của object Serializable. Tính volatile độc lập với việc lưu trạng thái.
- Nếu class **không tham gia** cơ chế Java Serialization, chỉ thêm `transient` không làm Java tự ghi/lưu bất kỳ dữ liệu nào. Modifier này vẫn hợp lệ ở field nhưng chưa tạo hiệu ứng thực tế trong một thao tác serialize không tồn tại.
- Nếu một thư viện JSON, ORM hoặc công cụ persistence dùng quy tắc ánh xạ khác, hãy kiểm tra API/annotation của **chính thư viện đó**. Không được suy diễn rằng mọi framework luôn bỏ qua `transient` y như `ObjectOutputStream`.

### 7.1. Sau khi deserialize, field transient nhận giá trị nào?

Với default serialization, field transient không có dữ liệu khôi phục, nên mang **giá trị mặc định** của kiểu:

| Field transient | Giá trị sau default deserialization |
| --- | --- |
| `transient int count` | `0` |
| `transient long id` | `0L` |
| `transient boolean active` | `false` |
| `transient double rate` | `0.0` |
| `transient String token` | `null` |
| `transient int[] buffer` | `null` |
| `transient SomeClass object` | `null` |

Quan trọng: khi deserializing một class Serializable thông thường, **constructor và instance field initializer của chính class Serializable đó không chạy như khi `new` một đối tượng**. Việc khôi phục field tuân theo cơ chế serialization. Constructor không tham số của **superclass gần nhất không Serializable** được gọi theo quy tắc deserialization; đây là một lý do không nên dựa vào initializer của field transient để tự khởi tạo lại.

Ví dụ `transient java.util.List<String> cache = new ArrayList<>();` có thể là danh sách khác null khi tạo bằng `new`, nhưng sau **default deserialization** vào lớp Serializable như vậy nó có thể là `null`. Muốn sử dụng tiếp cache, cần tái tạo phù hợp.

## 8. Ví dụ Java 17+ chạy được: field transient trước/sau serialize

Lưu toàn bộ chương trình vào **`TransientSerializationDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

public class TransientSerializationDemo {
    static final class Session implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        String username;
        int loginCount;
        transient String accessToken;
        transient int cachedScore;

        Session(String username, int loginCount,
                String accessToken, int cachedScore) {
            this.username = username;
            this.loginCount = loginCount;
            this.accessToken = accessToken;
            this.cachedScore = cachedScore;
        }
    }

    public static void main(String[] args) throws Exception {
        Session original = new Session("Lan", 3, "temporary-token", 100);

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ObjectOutputStream output =
                     new ObjectOutputStream(buffer)) {
            output.writeObject(original);
        }

        Session restored;
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(buffer.toByteArray()))) {
            restored = (Session) input.readObject();
        }

        System.out.println("username = " + restored.username);
        System.out.println("loginCount = " + restored.loginCount);
        System.out.println("accessToken = " + restored.accessToken);
        System.out.println("cachedScore = " + restored.cachedScore);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 TransientSerializationDemo.java
java TransientSerializationDemo
~~~

**Stdout chính xác:**

~~~text
username = Lan
loginCount = 3
accessToken = null
cachedScore = 0
~~~

**Giải thích từng bước:**

1. Class lồng `Session` triển khai `Serializable` để tham gia Java Object Serialization. `serialVersionUID` định danh phiên bản dùng cho cơ chế tương thích serialization; `@Serial` là annotation có trong Java 17 hỗ trợ compiler kiểm tra khai báo thành viên liên quan.
2. Đối tượng `original` có `username = "Lan"`, `loginCount = 3`, `accessToken = "temporary-token"` và `cachedScore = 100`.
3. `ObjectOutputStream.writeObject(original)` ghi object graph vào `ByteArrayOutputStream`. Hai instance field **không transient** là `username` và `loginCount` được xử lý theo mặc định; các field `accessToken` và `cachedScore` bị bỏ qua.
4. `ObjectInputStream.readObject()` tạo object khôi phục. Hai field không transient lấy giá trị tương ứng từ stream; `String accessToken` nhận mặc định `null` và `int cachedScore` nhận mặc định `0`.
5. Chương trình in các giá trị sau khi khôi phục. Không có file thực tế được tạo trên đĩa, vì ví dụ dùng byte array trong bộ nhớ.

Không sử dụng `ObjectInputStream` để deserialize dữ liệu tùy ý từ nguồn không tin cậy: Java native deserialization có bề mặt tấn công đáng kể, kể cả khi một số field là transient. Với dữ liệu trao đổi qua mạng hoặc lưu dài hạn, hãy chọn định dạng và cơ chế deserialize có kiểm soát, xác thực và giới hạn phù hợp.

## 9. Khi nào nên dùng transient?

### 9.1. Cache hoặc dữ liệu tính toán lại được

~~~java
import java.io.Serializable;

class PriceQuote implements Serializable {
    private static final long serialVersionUID = 1L;

    long basePrice;
    long tax;
    transient Long cachedTotal;

    long total() {
        if (cachedTotal == null) {
            cachedTotal = Math.addExact(basePrice, tax);
        }
        return cachedTotal;
    }
}
~~~

Đây là đoạn minh họa. `cachedTotal` là dữ liệu suy ra từ hai giá trị gốc nên không cần lưu cùng object. Sau deserialize, `cachedTotal == null` và lần gọi `total()` sẽ tính lại giá trị.

Ví dụ này giả định object không bị nhiều thread đồng thời thay đổi `basePrice`/`tax`. Nếu cache được truy cập hoặc dữ liệu gốc được cập nhật đồng thời, cần bổ sung chiến lược synchronization/invalidation tương ứng. Chỉ thêm transient không cung cấp tính đúng đắn cho cache đa luồng.

### 9.2. Thành phần runtime không thể hoặc không nên serialize

Các object như connection đang mở, socket, executor, thread hoặc các resource handle thường không thích hợp để tuần tự hóa trực tiếp. Có thể đánh dấu field tương ứng transient, rồi **tái tạo hoặc cung cấp lại** khi object trở về trạng thái hoạt động. Ví dụ kết nối database cần được lấy lại từ pool; không nên kỳ vọng một serialized object mang theo kết nối sống hợp lệ.

### 9.3. Trạng thái tạm thời không thuộc dữ liệu lâu dài

Các field như cache hiển thị, bộ đệm phục vụ thao tác, kết quả tính toán phụ hoặc dữ liệu yêu cầu xác thực lại đôi khi không nên xuất hiện trong object stream. Tuy nhiên, `transient` **không phải cơ chế mã hóa hoặc chính sách bảo mật hoàn chỉnh**: custom serialization có thể ghi field transient bằng tay; dữ liệu có thể xuất hiện trong field khác hoặc trong log; công cụ khác có thể dùng quy tắc serialize riêng.

Nếu một token không nên được lưu, ngoài `transient` còn phải thiết kế vòng đời token, phạm vi lưu, logging, quyền truy cập và quy tắc tái cấp phát.

## 10. Tái khởi tạo transient field sau khi deserialize

Vì instance field initializer của class Serializable không chạy khi khôi phục bình thường, một field như sau có nguy cơ trở thành `null` sau khi deserialize:

~~~java
transient java.util.Map<String, String> cache =
        new java.util.HashMap<>();
~~~

Đây chỉ là mảnh khai báo field. Nếu class hỗ trợ Java Serialization và muốn tạo lại cache, có thể dùng custom `readObject`:

~~~java
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.Serial;
import java.io.Serializable;
import java.util.HashMap;
import java.util.Map;

class Catalog implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String catalogName;
    private transient Map<String, String> cache = new HashMap<>();

    @Serial
    private void readObject(ObjectInputStream input)
            throws IOException, ClassNotFoundException {
        input.defaultReadObject();
        cache = new HashMap<>();
    }
}
~~~

Đây là **đoạn minh họa khai báo**, không có `main`. `input.defaultReadObject()` khôi phục các field mặc định từ stream. Sau đó `cache = new HashMap<>()` tạo một cache mới để object hoạt động bình thường.

Trong thực tế, custom deserialization cần chú ý validate invariant, không để object ở trạng thái lỗi sau khi đọc dữ liệu không đáng tin, và tránh gọi logic phức tạp trên object chưa được khôi phục hoàn chỉnh. Method `readObject` không bắt buộc cho mọi class Serializable; chỉ thêm nếu thật sự cần kiểm soát quá trình khôi phục.

**Đừng nhầm:** viết custom `writeObject` có thể ghi dữ liệu tùy ý vào stream, kể cả giá trị của field transient nếu lập trình viên chủ động ghi nó. Vì vậy phát biểu đúng là “transient bị bỏ qua **trong biểu diễn field mặc định**”, không phải “Java không bao giờ có thể ghi giá trị transient”.

## 11. Có thể kết hợp `volatile` và `transient`?

Có. Hai modifier cùng khai báo trên một field vì chúng điều chỉnh **hai khía cạnh khác nhau**:

~~~java
import java.io.Serializable;

class SharedSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private transient volatile String cachedResult;

    String getCachedResult() {
        return cachedResult;
    }

    void refresh(String value) {
        cachedResult = value;
    }
}
~~~

Đây là đoạn minh họa. `volatile` giúp các thread quan sát việc thay đổi **tham chiếu** của `cachedResult` theo JMM. `transient` làm cho field bị bỏ qua khi `SharedSnapshot` được serial hóa mặc định. Khi khôi phục object, `cachedResult` sẽ là `null` cho tới khi được thiết lập lại.

Việc field là `volatile` không khiến toàn bộ logic cache tự động thread-safe. Nếu `refresh` hoặc getter phải đảm bảo thêm một điều kiện nhiều bước, cần công cụ đồng bộ phù hợp.

**Các tổ hợp modifier cần phân biệt:**

| Khai báo | Hợp lệ? | Ghi chú |
| --- | --- | --- |
| `volatile int count;` | Có | Read/write volatile; `count++` vẫn không atomic |
| `transient String token;` | Có | Bỏ qua trong default Java Serialization |
| `transient volatile Object cache;` | Có | Cả hai semantics |
| `private static volatile boolean stopped;` | Có | Static volatile field dùng chung ở cấp class |
| `private static transient int value;` | Có về cú pháp | `transient` thừa vì static field không được serialize mặc định |
| `final transient int version = 1;` | Có về cú pháp | Final và transient có thể đi cùng nhau; có thể không khôi phục giá trị 1 sau deserialization |
| `final volatile int value = 1;` | **Không** | Java không cho một field vừa `final` vừa `volatile` |
| `volatile` trên biến cục bộ hoặc tham số | **Không** | `volatile` là modifier của field |
| `transient` trên biến cục bộ hoặc method | **Không** | `transient` là modifier của field |

Với `final transient`, vì giá trị bị bỏ qua khi serialization mặc định và constructor/initializer Serializable class không chạy khi khôi phục, field có thể nhận giá trị mặc định khác giá trị đã khai báo ban đầu. Đây thường là lựa chọn khó bảo trì; chỉ sử dụng khi hiểu rõ các quy tắc serialization và invariant.

## 12. Những hiểu lầm phổ biến

1. **“`volatile` khiến `count++` atomic.”** Sai. `++` cần đọc, tính toán và ghi; `volatile` không bảo vệ toàn bộ chuỗi thao tác. Hãy dùng atomic variable hoặc lock tùy bài toán.
2. **“`volatile` nghĩa là luôn đọc trực tiếp từ RAM.”** Diễn giải cơ học này không phải hợp đồng của Java. Hợp đồng đúng là visibility, ordering và atomicity của từng truy cập volatile theo Java Memory Model.
3. **“Volatile reference làm các field của object con cũng volatile.”** Sai. Nó áp dụng cho **field tham chiếu**, không tự lan sang `obj.field` hoặc `array[i]`.
4. **“Mọi field trong class đều nên volatile để an toàn đa luồng.”** Sai. Thiết kế đồng bộ còn bao gồm invariant, compound action, atomic snapshot, trách nhiệm sở hữu và lifecycle.
5. **“`transient` xóa giá trị field ngay khi chạy.”** Sai. Object sống bình thường vẫn giữ và đọc/ghi field; transient ảnh hưởng tới default serialization, không xóa bộ nhớ runtime.
6. **“Transient field tự tái khởi tạo bằng field initializer sau deserialize.”** Sai đối với class Serializable được khôi phục theo cơ chế thông thường. Hãy xử lý khởi tạo lại khi cần.
7. **“`transient` bảo vệ bí mật bất kể định dạng serialization.”** Sai. Các thư viện ngoài Java native serialization có thể áp dụng quy tắc riêng; custom writeObject có thể ghi giá trị bất kỳ, và dữ liệu vẫn có thể xuất hiện ở kênh khác.
8. **“`volatile` tự bỏ field khỏi serialization.”** Sai. Volatile instance field không transient vẫn được serialize mặc định nếu thỏa điều kiện serializable.
9. **“Static field cần transient để không lưu.”** Không cần với default object serialization; static field không thuộc trạng thái của từng object.
10. **“`transient` giúp object thread-safe.”** Sai. Transient không sinh ra memory barrier, lock hay atomic operation.
11. **“Mọi loại dữ liệu đều có thể ghi bằng `Serializable` nếu thêm transient tùy ý.”** Sai. Các field object không transient phải chứa trạng thái có thể serialize theo object graph hoặc có custom xử lý hợp lệ; nếu không, `ObjectOutputStream` có thể ném `NotSerializableException`.
12. **“Nếu ví dụ đồng thời chạy đúng vài lần, thiếu đồng bộ cũng không sao.”** Sai. Thread scheduling và tối ưu có thể khác ở môi trường khác; correctness cần dựa trên hợp đồng JMM, không dựa trên output tình cờ.

## 13. Cách chọn modifier trong tình huống thực tế

| Tình huống | Khai báo hoặc hướng xử lý | Vì sao |
| --- | --- | --- |
| Một cờ dừng được một thread ghi, thread khác đọc | `volatile boolean stopped` | Cần visibility giữa thread; không có cập nhật nhiều bước |
| Bộ đếm nhiều thread cùng tăng | `AtomicInteger` hoặc lock | Cần atomic read-modify-write; volatile đơn lẻ không đủ |
| Cấu hình bất biến cần thay mới trong lúc chương trình chạy | `volatile Config current` với `Config` immutable | Xuất bản snapshot mới an toàn theo JMM |
| Hai trường `balance` và `status` phải thay cùng lúc | Lock hoặc immutable aggregate | Cần invariant nguyên vẹn, không chỉ visibility của từng field |
| Token phiên đang chạy không muốn lưu vào Java serialized object | `transient String token` | Bỏ qua giá trị trong default Java Serialization |
| Cache có thể dựng lại sau deserialize | `transient Cache cache`, thêm logic tái tạo | Tránh serialize trạng thái dư thừa |
| Cache vừa chia sẻ giữa thread vừa không lưu khi serialize | `transient volatile Cache cache` trong trường hợp publish reference đơn giản | Dùng riêng từng semantics theo đúng mục đích |
| Dữ liệu đưa qua JSON framework | Quy tắc serialization riêng của framework | `transient` có thể có hành vi khác, cần kiểm tra cấu hình/library |

Một field **có thể vừa cần concurrency correctness vừa cần serialization policy**, nhưng nên xét riêng hai câu hỏi: “Các thread đọc/ghi trạng thái này theo quan hệ đồng bộ nào?” và “Nếu object được serialize, trạng thái này có cần khôi phục không?”.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Field `private volatile int count;` có thể được hai thread tăng bằng `count++` mà không mất cập nhật không?

**Đáp án:** Không. Volatile không làm nguyên tử một phép đọc–sửa–ghi. Cần `AtomicInteger` hoặc cách đồng bộ khác.

**Câu 2.** Một writer chạy `data = 42; ready = true;` với `ready` là volatile; reader chỉ dùng `data` sau khi đọc thấy `ready == true`. Trong kịch bản một lần publish, không có ghi khác cạnh tranh vào `data`, reader có được đảm bảo nhìn thấy `42` không?

**Đáp án:** Có. Phép ghi `data` trước phép ghi volatile `ready` có quan hệ *happens-before* đến thao tác sau lần đọc volatile quan sát tín hiệu, do đó dữ liệu được publish an toàn.

**Câu 3.** `volatile int[] numbers;` có biến `numbers[0]++` thành atomic không?

**Đáp án:** Không. Chỉ field tham chiếu mảng `numbers` là volatile. Phần tử và phép tăng không được tự bảo vệ.

**Câu 4.** Object có `String name = "Lan"` và `transient int cached = 99`, được lưu bằng default `ObjectOutputStream` rồi khôi phục. Giá trị `cached` thông thường là gì?

**Đáp án:** `0` vì `cached` là primitive `int` transient; initializer của class Serializable không tự chạy lại trong quá trình khôi phục object theo cách mặc định.

**Câu 5.** `volatile String sessionToken` có tự ngăn giá trị token được Java Serialization lưu lại không?

**Đáp án:** Không. Nếu đó là instance field không transient của Serializable object, nó vẫn thuộc trạng thái mặc định được serialize. Nếu chính sách yêu cầu bỏ qua, dùng `transient` và các biện pháp xử lý dữ liệu nhạy cảm khác phù hợp.

**Câu 6.** Có thể khai báo `transient volatile String cache;` không?

**Đáp án:** Có. Modifier volatile cung cấp memory semantics khi các thread truy cập field, còn transient loại field khỏi trạng thái instance được tuần tự hóa mặc định.

**Câu 7.** Khi nào `transient` không ảnh hưởng đến dữ liệu đã được lưu?

**Đáp án:** Khi dùng cách lưu khác Java native serialization và công cụ đó không diễn giải `transient` theo cùng quy tắc, hoặc code custom serialization chủ động ghi dữ liệu bị transient. Phải kiểm tra cơ chế serialize/persistence đang thực sự dùng.

### Ghi nhớ để áp dụng

Khi nhìn thấy `volatile`, hãy tìm **thread nào ghi, thread nào đọc, và thao tác có phải compound action không**. Khi nhìn thấy `transient`, hãy tìm **đường serialize/deserialize nào đang được dùng và sau khôi phục field được tạo lại ra sao**. Chọn modifier theo hai câu hỏi đó giúp tránh nhầm lẫn giữa **đồng bộ bộ nhớ** và **vòng đời dữ liệu lưu trữ**.
