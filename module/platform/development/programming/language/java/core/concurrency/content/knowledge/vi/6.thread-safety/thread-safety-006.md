# Safe publication qua final, volatile và khóa trong Java

> **Mục tiêu:** Biết khi nào một đối tượng đã khởi tạo được **công bố an toàn** để thread khác đọc được trạng thái của nó; phân biệt bảo đảm đặc biệt của `final` với bảo đảm *happens-before* của `volatile` và khóa; chọn đúng cách chia sẻ **immutable snapshot** hoặc bảo vệ **mutable state** trong Java.

Bài thuộc nhóm **Thread Safety**, sử dụng Java SE và Java Memory Model (JMM). Các ví dụ chạy với Java 17+, không phụ thuộc vào Spring hoặc cơ chế lifecycle/DI của framework.

## 1. Safe publication là một yêu cầu của thread safety

Giả sử thread A dựng một object rồi thread B bắt đầu sử dụng. Trong A, constructor ghi các field theo thứ tự nguồn; nhưng **thứ tự chạy theo đồng hồ không tự tạo quan hệ quan sát bộ nhớ** giữa hai thread nếu mã thiếu đồng bộ.

Một đối tượng được **safely published** khi đường truyền tham chiếu từ thread tạo sang thread sử dụng có cơ chế bảo đảm những hành động khởi tạo cần thiết được quan sát theo quan hệ *happens-before* phù hợp. Safe publication giúp tránh tình trạng consumer thấy một tham chiếu nhưng không có bảo đảm nhìn thấy những giá trị mà producer đã ghi trong construction.

~~~text
Thread A                                   Thread B
--------                                   --------
new Config(...)       (1) construction
... writes fields
publish reference     (2) publication  ---> receive reference
                                           read initialized fields
                                           (3) subsequent use
~~~

Cần tách ba giai đoạn:

1. **Construction:** thiết lập invariant bên trong object, ví dụ `host != null` và `timeout > 0`.
2. **Publication:** truyền tham chiếu qua một giao thức có bảo đảm Java Memory Model.
3. **Subsequent mutation:** nếu object còn thay đổi sau khi đã được công bố, cần cơ chế riêng để tránh data race, lost update hoặc snapshot không nhất quán.

**Safe publication không đồng nghĩa object bất biến, và cũng không tự biến mọi thao tác tương lai trên object thành thread-safe.** Nó chủ yếu nói về việc consumer có thể tin vào các ghi đã thực hiện **trước thời điểm publication** được đồng bộ.

### Vì sao `ref != null` chưa phải bằng chứng?

Hãy xét đoạn cố ý thiếu đồng bộ (mã minh họa, không phải chương trình độc lập):

~~~java
class Holder {
    static Settings shared; // Field thường; không volatile, không khóa.

    static void create() {
        shared = new Settings("service-a", 30);
    }

    static void consume() {
        Settings local = shared;
        if (local != null) {
            use(local.host, local.timeoutSeconds);
        }
    }
}
~~~

Nếu hai phương thức ở hai thread khác nhau và không có cạnh đồng bộ nào khác, việc đọc `shared` là một truy cập racy với ghi `shared`. Thấy reference khác null không làm cho các ghi field thông thường trong constructor tự động *happens-before* consumer. Producer hoàn thành constructor trước theo thời gian thực **không đủ** để chứng minh consumer luôn thấy đầy đủ state.

Đừng yêu cầu đoạn racy trên phải in một kết quả “sai” cụ thể: máy/JVM thường có thể tình cờ quan sát đúng rất nhiều lần. Phép thử thành công không thay thế quy tắc JMM.

## 2. Bảng so sánh ba cơ chế

| Cơ chế | Điều nó thực sự bảo đảm | Phạm vi phù hợp | Điều **không** được suy ra |
| --- | --- | --- | --- |
| `final` field | Bảo đảm **final-field semantics** sau khi object được dựng đúng cách; các final field có giá trị đã gán trong constructor dù có một số kiểu publication không đồng bộ | Value object và immutable snapshot | Không tạo khóa, không bảo vệ mutation của object bên trong field final, không sửa `this` escape |
| `volatile` reference | Ghi volatile và lần đọc volatile tương ứng tạo ordering/visibility, nhờ đó publish các ghi trước lần ghi volatile | Công bố/thay thế snapshot bất biến, cờ trạng thái đơn giản | Không khiến các field thường trong object luôn thread-safe; không atomic cho chuỗi read-modify-write |
| `synchronized` / `Lock` | Critical section loại trừ lẫn nhau và cạnh *happens-before* giữa release/acquire cùng cơ chế khóa | Dữ liệu mutable, nhiều field phải cập nhật/đọc đồng bộ; chuyển giao reference qua khóa | Không bảo vệ reader/writer nào bỏ qua khóa hoặc khóa một object khác |

Trong thực tế, các cơ chế thường **phối hợp**: object có final fields để giữ immutable state, được công bố qua volatile reference; hoặc object mutable được tạo và đọc/sửa dưới cùng một lock.

## 3. Nền tảng: happens-before quan trọng hơn “chạy trước”

JMM mô tả các quan hệ *synchronizes-with* và *happens-before* (HB). Khi **một ghi cần thiết HB một lần đọc** ở thread khác, mô hình có căn cứ về visibility/order của ghi đó. HB có tính bắc cầu: nếu A HB B và B HB C, thì A HB C.

Các cạnh thường dùng:

- **Program order:** thao tác trước trong một thread HB thao tác sau trong cùng thread.
- **Monitor:** unlock của `synchronized(lock)` HB lần lock tiếp theo trên **cùng monitor**.
- **Volatile:** ghi volatile HB các lần đọc volatile tiếp theo của cùng biến theo synchronization order.
- **`Thread.start()`:** hành động trước `start()` HB hành động của thread mới.
- **`Thread.join()`:** hành động trong thread đã kết thúc HB hành động sau `join()` hoàn thành thành công của thread đợi.
- **Concurrent utilities:** các API như `BlockingQueue`, `ExecutorService.submit`/`Future.get` có quy tắc memory-consistency riêng.
- **Class initialization:** JVM bảo đảm khởi tạo lớp được điều phối để thread sử dụng class đã khởi tạo theo đúng đặc tả.

**Không có cạnh HB chỉ vì có `sleep()`, log “thread A trước thread B”, đọc đồng hồ, đặt priority cao, hoặc gọi `System.out.println()` rồi suy luận dữ liệu ngoài luồng.** Một thư viện I/O có thể dùng khóa nội bộ để in, nhưng đó không phải hợp đồng đồng bộ cho state nghiệp vụ của ta.

Sơ đồ publication bằng volatile:

~~~text
A: tạo Config -> ghi các field -> volatile WRITE ref
                                         |
                                synchronizes-with
                                         v
B:                               volatile READ ref -> đọc field
~~~

Nếu consumer dùng tham chiếu nhận qua cạnh đồng bộ ấy, các ghi tạo state trong A được công bố đến B. Nếu consumer lấy cùng object qua một **đường rò rỉ khác**, phải xét đường đó riêng.

## 4. `final`: giá trị ổn định và quy tắc *freeze*

Một field `final` chỉ được gán theo những quy tắc khởi tạo của Java. JMM có **final-field semantics**: đối với một object được **constructed correctly**, khi constructor kết thúc có hành động *freeze* liên quan đến final fields. Các thread khác được bảo đảm quan sát giá trị mà constructor đã gán cho các final fields theo quy định ở JLS `17.5, ngay cả trong một số tình huống reference được chia sẻ qua data race.

~~~java
// Một class minh họa cho immutable value object.
final class Endpoint {
    final String host;
    final int port;

    Endpoint(String host, int port) {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("host");
        }
        if (port <= 0 || port > 65535) {
            throw new IllegalArgumentException("port");
        }
        this.host = host;
        this.port = port;
    }
}
~~~

Ở đây các thành phần `String` và `int` không mang mutable state nội bộ do caller sửa; class không thể subclass và reference không được công bố trong constructor. Một instance đã dựng xong là value object có trạng thái ổn định.

### “Constructed correctly” gồm những gì?

**Không cho `this` thoát khỏi constructor trước khi construction hoàn tất.** Các hành vi đáng ngờ:

- Đưa `this` vào static field/registry mà thread khác có thể đọc.
- Truyền `this` tới listener/callback có thể chạy ngay.
- Gửi lambda capture `this` đến executor ngay trong constructor.
- `new Thread(() -> use(this)).start()` trước khi các field khác được gán.
- Gọi phương thức overridable trong constructor; subclass có thể được gọi khi field của subclass chưa dựng xong.

Nếu một thread đọc object **trước constructor hoàn thành**, bảo đảm final-field sau freeze không thể sửa những lần đọc đã xảy ra trước đó. Ngay cả khi field là final, đừng cho consumer chạm vào object khi constructor đang chạy.

### `final` không có nghĩa bất biến sâu (*deeply immutable*)

~~~java
final class Names {
    final java.util.List<String> values;

    Names(java.util.List<String> values) {
        this.values = values; // Vẫn giữ list của caller!
    }
}
~~~

Field `values` không được gán lại, nhưng một thread khác có thể sửa `ArrayList` được tham chiếu, làm rối cấu trúc hoặc gây data race. An toàn hơn khi cần snapshot chỉ đọc:

~~~java
final class Names {
    final java.util.List<String> values;

    Names(java.util.List<String> source) {
        this.values = java.util.List.copyOf(source);
    }
}
~~~

`List.copyOf` tạo list không cho mutate qua API thường, đồng thời tách cấu trúc list khỏi mutable list nguồn. Tuy nhiên, nếu phần tử là các object mutable, `List.copyOf` **không tự copy sâu từng phần tử**. Cần cân nhắc copy/thiết kế immutable cả cây dữ liệu hoặc áp dụng synchronization phù hợp.

### `final` giúp visibility; không thay thế cả một giao thức chia sẻ

Bảo đảm đặc biệt cho final field **không đồng nghĩa** mọi ordinary field khác của object được publish an toàn. Nó cũng không tạo cơ chế chờ một tham chiếu xuất hiện, không cung cấp ordering cho các mutation sau constructor và không làm chuỗi thao tác trên nhiều object trở thành atomic.

**Thói quen tốt:** dùng final fields để biểu đạt state không đổi, và vẫn chọn một **publication path rõ ràng** như volatile, khóa, class initialization hoặc concurrent queue.

## 5. Ví dụ Java 17: value object có final field được công bố trước `Thread.start()`

Tạo tệp `FinalConfigDemo.java`:

~~~java
public class FinalConfigDemo {
    private static final class Config {
        final String host;
        final int timeoutSeconds;

        Config(String host, int timeoutSeconds) {
            this.host = host;
            this.timeoutSeconds = timeoutSeconds;
        }

        String describe() {
            return host + ":" + timeoutSeconds;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Config config = new Config("api.internal", 15);

        Thread reader = new Thread(
                () -> System.out.println("config = " + config.describe()));

        reader.start();
        reader.join();
    }
}
~~~

Chạy:

~~~bash
javac FinalConfigDemo.java
java FinalConfigDemo
~~~

Stdout:

~~~text
config = api.internal:15
~~~

Mã này có **hai điểm tốt**: `Config` đã hoàn tất construction, có final fields; hơn nữa, các ghi chuẩn bị object trước `reader.start()` HB các hành động của thread reader. Do đó **không dùng kết quả ví dụ để chứng minh final một mình đã thay thế mọi kỹ thuật publication**. Đây là mẫu thực tế dễ đọc, tránh thử nghiệm unsafe publication vốn không có stdout xác định.

Việc `reader.join()` cũng bảo đảm main đợi reader kết thúc trước khi thoát, nhưng nó không phải cơ chế publication từ main sang reader; hướng publication ở đây đến từ `start()`.

## 6. `volatile`: công bố an toàn một reference sau construction

Khi producer xây xong object, sau đó ghi reference vào field `volatile`, reader đọc chính volatile field đó sẽ tham gia cơ chế đồng bộ. Những ghi trước lần volatile write của producer được quan sát qua volatile read phù hợp của consumer.

Ví dụ:

~~~java
// Dạng cấu trúc minh họa; các field và method ở cùng class.
private static volatile Config latest;

static void replaceConfig() {
    Config complete = new Config("primary", 20);
    latest = complete; // Volatile WRITE sau construction.
}

static Config currentConfig() {
    return latest; // Volatile READ.
}
~~~

Nếu `Config` là immutable snapshot, reader có thể lấy `Config local = currentConfig()` một lần rồi sử dụng nhiều field nhất quán của **cùng snapshot**. Khi nhà xuất bản thay `latest` bằng snapshot mới, reader khác có thể bắt gặp bản cũ hoặc mới tùy lần đọc, nhưng không thấy “một nửa” của phép gán reference và không phải xử lý object đang được mutate từng field.

### Ví dụ Java 17: thay snapshot qua volatile

Tạo `VolatileSnapshotDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;

public class VolatileSnapshotDemo {
    private record Settings(String host, int retries) {}

    private static volatile Settings current;
    private static final CountDownLatch readerStarted =
            new CountDownLatch(1);

    public static void main(String[] args) throws InterruptedException {
        Thread reader = new Thread(() -> {
            readerStarted.countDown();
            Settings snapshot;
            while ((snapshot = current) == null) {
                Thread.onSpinWait();
            }
            System.out.println(
                    snapshot.host() + " / retries=" + snapshot.retries());
        }, "reader");

        reader.start();
        readerStarted.await();

        Settings built = new Settings("primary", 3);
        current = built; // Ghi volatile SAU khi khởi tạo.
        reader.join();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac VolatileSnapshotDemo.java
java VolatileSnapshotDemo
~~~

Đầu ra khi thực thi bình thường:

~~~text
primary / retries=3
~~~

`readerStarted` chỉ điều phối điểm reader đã bắt đầu để minh họa có hai thread. Consumer lặp lại thao tác **volatile read** cho tới khi thấy reference. Khi nhận được `current`, giá trị từ `built` đã được dựng xong được công bố qua volatile write/read và có thể đọc đúng.

**Vòng spin chỉ dùng trong demo.** Trong ứng dụng cần chờ có timeout/cancel/không đốt CPU, dùng `BlockingQueue`, `CountDownLatch`, `Condition`, `Future` hoặc tiện ích tương tự thay vì quay vô hạn. JMM cung cấp các bảo đảm visibility; thời gian thread được OS lập lịch và tiến triển không phải hard real-time guarantee.

### `volatile` không làm toàn bộ object tự động thread-safe

~~~java
// Minh họa lỗi logic, không phải chương trình độc lập.
class MutableState {
    int count;
}
volatile MutableState state = new MutableState();

void increment() {
    state.count++; // Vẫn là read-modify-write trên ordinary int.
}
~~~

Mỗi lần đọc field `state` có ngữ nghĩa volatile reference, nhưng phép `count++` trên object đang được chia sẻ không tự atomic. Hai writer vẫn có thể lost update. Ghi volatile vào **reference** không biến mọi field của referent thành volatile hoặc atomic, và không khóa các thao tác sau publication.

Nếu state phải thay đổi, hãy **thay thế toàn bộ immutable snapshot** qua volatile write, hoặc bảo vệ các field mutable bằng lock/atomic thích hợp.

### Hai writer: volatile replacement chưa bảo đảm read-modify-write

~~~java
// Mã minh họa sai nếu nhiều writer làm đồng thời.
Settings old = current;
current = new Settings(old.host(), old.retries() + 1);
~~~

Dù `current` là volatile, hai writer có thể cùng đọc một snapshot cũ rồi cùng ghi snapshot mới, mất một cập nhật. Muốn bảo đảm update theo state hiện tại, dùng cùng lock hoặc `AtomicReference<Settings>.updateAndGet(...)`/CAS với hàm update thuần. **Publication của snapshot mới** và **atomicity của việc tạo snapshot từ state hiện tại** là hai yêu cầu khác nhau.

## 7. `synchronized`: publication và truy cập state qua cùng monitor

`synchronized` không chỉ ngăn hai thread đi qua cùng monitor một lúc; **unlock** của producer có cạnh HB với **lock** tiếp theo của consumer trên chính monitor ấy. Những ghi vào ordinary fields bên trong critical section được reader quan sát đúng khi reader tuân theo cùng protocol.

Tạo `MonitorPublicationDemo.java`:

~~~java
public class MonitorPublicationDemo {
    private static final Object LOCK = new Object();
    private static Profile shared; // Field ordinary, không volatile.

    private record Profile(String name, int level) {}

    private static void publish(Profile ready) {
        synchronized (LOCK) {
            shared = ready;
            LOCK.notifyAll();
        }
    }

    private static Profile awaitProfile() throws InterruptedException {
        synchronized (LOCK) {
            while (shared == null) {
                LOCK.wait();
            }
            return shared;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Thread consumer = new Thread(() -> {
            try {
                Profile local = awaitProfile();
                System.out.println(local.name() + " level " + local.level());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        publish(new Profile("Ada", 7));
        consumer.join();
    }
}
~~~

Chạy:

~~~bash
javac MonitorPublicationDemo.java
java MonitorPublicationDemo
~~~

Đầu ra trong luồng chạy bình thường:

~~~text
Ada level 7
~~~

`publish` và `awaitProfile` đều dùng **cùng `LOCK`**. Producer công bố `Profile` sau constructor, consumer chờ condition trong monitor đó. `notifyAll()` đánh thức các thread đang chờ; **vòng `while` là bắt buộc về mặt pattern**, vì `Object.wait()` có thể thức dậy tự phát hoặc bị đánh thức khi điều kiện chưa thỏa.

Để ý: consumer có thể lock trước producer hoặc ngược lại; hai thứ tự đều đúng. Không cần `Thread.sleep` để tạo ra kết quả.

### Khi nào thêm `volatile` vào `shared`?

**Không cần** nếu *mọi đường đọc/ghi tham chiếu* đều được đồng bộ đúng theo cùng lock. Việc thêm volatile không sửa một đường đọc bên ngoài lock dùng sai protocol hoặc thiếu mutual exclusion cho nhiều field phải được đọc cùng nhau.

Nếu consumer giữ một reference tới object **mutable** rồi đọc nó ngoài lock trong khi producer tiếp tục sửa, phải bảo vệ việc sử dụng state đó hoặc chuyển sang immutable snapshot. Mẫu trên an toàn, thuận tiện vì `Profile` có state bất biến.

## 8. `ReentrantLock`: bản chất HB tương tự lock/unlock

`ReentrantLock` là lựa chọn khác khi cần `tryLock()`, lock interruptible, timeout hoặc `Condition`. Những lần `unlock()`/`lock()` trên cùng một lock cung cấp hiệu ứng đồng bộ tương đương monitor phù hợp.

~~~java
// Đoạn minh họa phương thức, không phải chương trình độc lập.
// LOCK là một ReentrantLock được chia sẻ bởi cả writer và reader.
LOCK.lock();
try {
    shared = new Profile("Ada", 7);
} finally {
    LOCK.unlock();
}
~~~

Reader cũng cần:

~~~java
LOCK.lock();
try {
    Profile snapshot = shared;
    // Chỉ dùng snapshot ngoài lock nếu nó bất biến hoặc có protocol riêng.
} finally {
    LOCK.unlock();
}
~~~

**Lock không có tác dụng nếu mỗi thread tạo một `new ReentrantLock()` riêng**, hoặc một đường đọc/ghi khác bỏ qua khóa. Đọc state đã được copy immutable ra khỏi vùng lock có thể an toàn nếu snapshot đã được khởi tạo đúng, nhưng việc tiếp tục mutation trên object chung thì vẫn cần protection.

Sử dụng `finally` để giải phóng khóa trong mọi đường trả về hoặc ném exception.

## 9. So sánh bằng tình huống: final, volatile hay khóa?

| Tình huống | Lựa chọn nên cân nhắc | Vì sao |
| --- | --- | --- |
| Value object không đổi sau constructor | `final` fields, class/record immutable; công bố qua HB | Giá trị rõ ràng và dễ chia sẻ |
| Cấu hình có nhiều field, thay bản mới theo từng đợt, reader chủ yếu đọc | `volatile` reference đến immutable snapshot | Reader lấy một snapshot rồi đọc nhất quán |
| Một biến stop flag do một writer cập nhật, reader kiểm tra | `volatile boolean`, hoặc `AtomicBoolean` nếu cần RMW | Publication/visibility cho một tín hiệu |
| Nhiều thread phải sửa nhiều field mutable đồng bộ | `synchronized` hoặc `ReentrantLock` trên cùng state | Lock giữ invariant trong critical section |
| Phải tính snapshot mới từ snapshot hiện tại với nhiều writer | Lock hoặc CAS qua `AtomicReference<ImmutableState>` | Chặn lost update |
| Task producer truyền object sang consumer | `BlockingQueue`, executor/Future theo hợp đồng | Vừa có luồng giao nhận vừa có HB |
| Singleton Java khởi tạo lười, không framework | Initialization-on-demand holder | JVM đảm bảo class initialization an toàn |
| Nested object có mutable fields | Defensive copy, confinement, lock/atomic cho mutation | `final` reference không đủ |
| Constructor có callback hoặc start thread | Refactor để không làm `this` escape | Publication trước freeze/hoàn thành construction nguy hiểm |

**Chọn cơ chế từ invariant và đường truy cập thực tế**, không chọn dựa vào “field được đọc nhiều nên thêm volatile cho yên tâm”.

## 10. Ví dụ về *constructor escape*: final cũng có giới hạn

Hãy tưởng tượng constructor này:

~~~java
// Mã minh họa phản-pattern; không phải chương trình độc lập.
class BadStart {
    final int number;

    BadStart() {
        new Thread(() -> consume(number)).start();
        number = 42;
    }
}
~~~

Đừng sử dụng pattern này. Việc khởi động thread có thể khiến `this` bị lộ cho consumer **trước khi constructor hoàn tất và trước khi final field có giá trị dự định**. Hơn nữa, với khai báo Java như trên, compiler có thể từ chối tham chiếu tới blank final field từ lambda trước khi field được definite-assigned; để trình bày lỗi ở mức nguyên lý, ví dụ chuẩn hơn là có một **method instance** đọc field, và thread gọi method ấy:

~~~java
// Mã minh họa nguy cơ về lifecycle, không yêu cầu chạy.
class UnsafeStarter {
    final int number;

    UnsafeStarter() {
        new Thread(this::inspect).start(); // Rò rỉ this quá sớm.
        number = 42;
    }

    void inspect() {
        consume(number);
    }

    void consume(int value) {
        // Consumer có thể quan sát số chưa được khởi tạo.
    }
}
~~~

Ngay cả khi tham chiếu `this` được truyền tới thread mới bằng `start()`, HB của `start()` chỉ bao phủ các hành động **trước** lời gọi start, không tự bao gồm phép gán `number = 42` xảy ra **sau**. Đọc giá trị mặc định do khởi tạo chưa hoàn tất là một rủi ro thực tế; không được yêu cầu stdout cụ thể hay đếm xác suất vì phụ thuộc scheduling.

### Thiết kế đúng: tạo xong rồi mới kích hoạt

~~~java
// Cấu trúc minh họa, không phải chương trình độc lập.
final class ReadyService {
    final int number;

    ReadyService() {
        number = 42;
    }

    void inspect() {
        System.out.println(number);
    }
}

// Bên ngoài constructor:
ReadyService service = new ReadyService();
new Thread(service::inspect).start();
~~~

Ở đây object hoàn tất construction trước khi thread mới bắt đầu; những hành động chuẩn bị trước `start` HB hành động của thread đó. Với API đăng ký callback/listener, tương tự: tạo object xong rồi mới đăng ký qua một protocol được đồng bộ.

**Ngoài early escape, gọi phương thức overridable trong constructor cũng có thể phơi trạng thái subclass chưa khởi tạo xong**; ưu tiên class `final` cho immutable value object hoặc tránh gọi hành vi overridable từ constructor.

## 11. Một phương án khác: class initialization công bố singleton

Java class initialization tự có quy tắc đồng bộ. Có thể tận dụng *initialization-on-demand holder* mà không tự viết DCL:

~~~java
// HolderPublicationDemo.java — Java 17+
public class HolderPublicationDemo {
    static final class Service {
        final String endpoint;

        Service(String endpoint) {
            this.endpoint = endpoint;
        }
    }

    private static final class Holder {
        static final Service INSTANCE = new Service("local");
    }

    static Service service() {
        return Holder.INSTANCE;
    }

    public static void main(String[] args) {
        Service a = service();
        Service b = service();
        System.out.println("same = " + (a == b));
        System.out.println("endpoint = " + b.endpoint);
    }
}
~~~

Chạy:

~~~bash
javac HolderPublicationDemo.java
java HolderPublicationDemo
~~~

Stdout:

~~~text
same = true
endpoint = local
~~~

Mã trên dựa vào class initialization của JVM để tạo singleton an toàn và chỉ một lần, miễn constructor không làm `this` escape. Đây là lựa chọn gọn khi cần một singleton immutable Java thuần.

**Static `final` không tự khiến referent thread-safe:** nếu `INSTANCE` là một mutable service có method sửa state, các method đó vẫn cần thiết kế concurrency đúng, mặc dù reference đã công bố an toàn.

## 12. Double-checked locking: tại sao reference phải volatile?

Lazy initialization thường được viết kiểu:

~~~java
// KHÔNG an toàn nếu instance được đọc ngoài lock mà không volatile.
private static Service instance;

static Service instance() {
    if (instance == null) {
        synchronized (LOCK) {
            if (instance == null) {
                instance = new Service();
            }
        }
    }
    return instance;
}
~~~

Reader ở phép kiểm tra đầu tiên **không lấy lock**; nếu `instance` là field ordinary, nó thiếu cạnh HB với thread đã ghi trong synchronized. Lỗi này không được sửa bằng cách “constructor chắc đã xong theo thời gian thực”.

Đối với Java 5+, một dạng DCL an toàn là (ví dụ cấu trúc class, không phải tệp độc lập):

~~~java
private static volatile Service instance;
private static final Object LOCK = new Object();

static Service instance() {
    Service local = instance;
    if (local == null) {
        synchronized (LOCK) {
            local = instance;
            if (local == null) {
                local = new Service();
                instance = local; // Volatile write sau construction.
            }
        }
    }
    return local;
}
~~~

Nhờ `volatile`, phép đọc ngoài lock có quan hệ memory visibility thích hợp với phép ghi publication, đồng thời chỉ một thread đi qua critical section khởi tạo khi instance còn null. `local` tránh đọc field volatile lại không cần thiết ở đường nhanh. **Điều kiện:** constructor không rò rỉ `this`, mọi đường khởi tạo phải tuân theo protocol này và các thao tác mutable của service sau khởi tạo vẫn được bảo vệ riêng.

Nếu không cần tối ưu lazy singleton theo pattern này, dùng holder ở phần trước thường dễ kiểm tra hơn.

## 13. Publication qua API concurrency đã có sẵn

Không phải lần chuyển tham chiếu nào cũng cần tự tạo `volatile` field. Một số API tiêu chuẩn đưa ra memory consistency rõ ràng.

- **`BlockingQueue`:** các hành động của producer **trước khi đặt** phần tử vào queue HB các hành động của consumer **sau khi lấy** phần tử đó.
- **`ExecutorService.submit` → task → `Future.get()`:** những hành động trước khi submit HB các hành động của task; các hành động của task HB những hành động sau khi thread khác lấy kết quả bằng `Future.get()`.
- **`Thread.start`/`Thread.join`:** cung cấp các cạnh HB đúng hướng cho các dữ liệu được chuẩn bị trước start hoặc sản sinh bởi thread trước khi join hoàn tất.
- **`ConcurrentHashMap`:** các thao tác trên mapping cung cấp memory-consistency và khả năng cập nhật nguyên tử theo hợp đồng; không có nghĩa cả chuỗi thao tác nhiều key là một transaction.

### Ví dụ Java 17: chuyển snapshot qua `BlockingQueue`

Tạo `QueueHandoffDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class QueueHandoffDemo {
    private record Message(String title, int version) {}

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(1);

        Thread consumer = new Thread(() -> {
            try {
                Message message = queue.take();
                System.out.println(message.title() + " v" + message.version());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        consumer.start();
        Message ready = new Message("config", 2);
        queue.put(ready);
        consumer.join();
    }
}
~~~

Chạy:

~~~bash
javac QueueHandoffDemo.java
java QueueHandoffDemo
~~~

Stdout:

~~~text
config v2
~~~

Queue vừa là kênh giao nhận có điều phối, vừa có bảo đảm HB. Không cần một volatile reference riêng chỉ để chuyển message này. Nhưng nếu producer tiếp tục **sửa nội dung mutable** của message sau `put`, sự sửa ấy không tự được bảo vệ bởi queue; nên dùng immutable message hoặc chuyển quyền sở hữu rõ ràng.

## 14. Safe publication khác thread safety của toàn bộ đối tượng

Xem ba thiết kế:

**Thiết kế A — immutable object được publish:** 

~~~java
record Snapshot(String host, int port) {}
volatile Snapshot current;
~~~

Reader lấy local snapshot và chỉ đọc các field bất biến. Nếu producer thay reference bằng snapshot mới, reader đã giữ snapshot cũ có thể tiếp tục sử dụng nhất quán. Tuy nhiên, nếu nhiều writer tính snapshot mới từ snapshot cũ, cần lock/CAS để tránh mất cập nhật.

**Thiết kế B — mutable object publish qua volatile rồi sửa thường:**

~~~java
final class MutableCounter {
    int value;
}
volatile MutableCounter counter;
~~~

Publication an toàn của reference chỉ bảo đảm quan sát các ghi trước publication. `counter.value++` ở nhiều thread vẫn là race. Thêm `volatile` vào `value` cũng không làm `++` atomic; dùng `AtomicInteger.incrementAndGet()` hoặc lock cho đúng.

**Thiết kế C — mutable object dùng chung qua một monitor:**

~~~java
// Minh họa protocol: tất cả truy cập vào state đều dùng LOCK.
synchronized (LOCK) {
    state.balance += amount;
    state.version++;
}
~~~

Nếu invariant yêu cầu `balance` và `version` được cập nhật/đọc cùng nhau, monitor bảo vệ toàn bộ tổ hợp. Cần reader đọc **cả hai** dưới cùng lock, hoặc lấy một immutable snapshot dưới lock rồi sử dụng ngoài lock.

Đừng dùng `final` trên **reference** rồi nghĩ state mutable của referent trở thành một immutable snapshot. Safe publication chỉ là *bước đầu* của thread safety khi có trạng thái chung thay đổi.

## 15. Lưu ý về `final`, record, defensive copy và object graph

Đối với object graph có nhiều tầng, câu hỏi không chỉ là object ngoài cùng có field final hay không:

~~~java
record Team(java.util.List<Member> members) {}
// Nếu Member có mutable field hoặc caller còn sửa list,
// riêng cú pháp record không chứng minh cả graph immutable.
~~~

Các quy tắc cần nhớ:

1. `record` tạo các component field là final nhưng một component tham chiếu object mutable vẫn có thể bị sửa.
2. Bản sao shallow của collection chỉ bảo vệ **cấu trúc collection**, không sao chép sâu mọi phần tử.
3. Với object bất biến thật sự, chọn value types bất biến, thực hiện defensive copy khi xây dựng và không expose mutable internals qua getters.
4. `final` phù hợp để giữ invariant sau construction, nhưng **đừng cho `this` thoát sớm**.
5. Các mutation sau publication cần khóa/atomic/ownership dù các tham chiếu dẫn tới state đó là final.
6. Nếu dùng nhiều trường thay đổi cùng nhau, việc volatile riêng từng field không tự bảo đảm một snapshot nhất quán của toàn bộ nhóm.

Một API rõ ràng thường nhận immutable input, dựng một snapshot mới, và publish snapshot qua một điểm đồng bộ duy nhất.

## 16. Cách suy luận và kiểm tra một đường publication

Khi review code có object chia sẻ giữa thread, hãy làm theo thứ tự:

1. **Vẽ đường reference:** object được tạo ở đâu, constructor làm gì, field/listener/queue nào chuyển tham chiếu cho reader?
2. **Kiểm tra construction:** invariant đã sẵn sàng trước khi reference thoát chưa? Có `this` escape, start thread trong constructor, callback, overridable method?
3. **Phân loại state:** field nào `final`; phần nào mutable; có nested mutable object, collection, array hay cache?
4. **Tìm cạnh HB:** volatile write/read cùng biến, unlock/lock cùng monitor, queue handoff, submit/get, start/join hay class init? Chỉ ra cụ thể trước/sau của cạnh.
5. **Kiểm tra tất cả reader và writer:** có đường bypass lock/volatile không? Có thread giữ direct reference từ registry không đồng bộ?
6. **Kiểm tra sau publication:** object có bị sửa tiếp không? Có compound action cần atomicity hoặc invariant nhiều field không?
7. **Chọn giải pháp nhỏ, rõ:** immutable snapshot + volatile cho read-mostly; monitor/Lock cho mutable invariant; concurrent utility cho giao nhận; atomic/CAS cho state cập nhật độc lập.
8. **Xác minh correctness trước hiệu năng:** lập luận theo JMM và invariant; test có latch để điều khiển interleaving nếu cần; đừng kết luận an toàn từ stress test pass.

### Lỗi thường gặp

- **“Constructor chạy xong theo đồng hồ là đủ.”** Không: reader phải có cơ sở publication/happens-before thích hợp.
- **“`final` làm object graph bất biến sâu.”** Không: final field có thể tham chiếu mutable collection/object.
- **“`volatile` reference làm mọi field thường đều volatile.”** Không: nó publish các ghi đã xảy ra trước; mutation sau đó phải được bảo vệ.
- **“Một `counter++` trên volatile state là atomic.”** Không: read-modify-write cần atomic API hoặc khóa.
- **“`synchronized` ở hai nơi là đủ dù khác monitor.”** Không: HB thông qua monitor phải dùng cùng khóa.
- **“Publish trước constructor xong vẫn ổn nếu reference volatile.”** Không: volatile không publish những ghi chưa xảy ra.
- **“DCL thiếu volatile nhưng bên writer dùng lock rồi.”** Không: reader fast path ngoài lock không đồng bộ với writer.
- **“`Thread.sleep` chờ đủ lâu là publication an toàn.”** Không: ngủ không tạo HB cho các field.
- **“Concurrent queue đảm bảo object mutable an toàn mãi về sau.”** Không: cần quy tắc mutation/ownership sau handoff.
- **“Safe publication đã giải quyết race trên mọi operation.”** Không: phải kiểm tra thread safety của cả API sau khi object được chia sẻ.

## 17. Câu hỏi tự kiểm tra

**Câu 1:** `final Config config` được gán đúng trong constructor, nhưng `Config` chứa `ArrayList` mutable. Có thể để nhiều thread thêm phần tử không khóa chỉ vì field `config` là final không?  
**Đáp án:** Không. Final cố định reference, không làm mutation của `ArrayList` thread-safe.

**Câu 2:** Producer xây `Config` rồi ghi vào `volatile Config current`; consumer đọc `current` vào một biến local rồi đọc các field immutable. Vì sao consumer thấy state đúng?  
**Đáp án:** Publication đi qua volatile write/read, tạo cạnh HB phù hợp giữa các ghi constructor và các lần đọc field trong consumer.

**Câu 3:** Dùng `volatile MutableState state` rồi nhiều thread gọi `state.count++`. Có tránh lost update không?  
**Đáp án:** Không. Volatile ở reference không biến RMW trên field `count` thành atomic.

**Câu 4:** Producer ghi `shared` trong `synchronized(lockA)`, consumer đọc trong `synchronized(lockB)`. Có đủ không?  
**Đáp án:** Không, nếu lockA và lockB khác nhau và không có cơ chế HB khác.

**Câu 5:** `this` được đưa ra registry ở đầu constructor rồi cuối constructor mới gán final fields. Final-field semantics có bảo vệ những lần đọc xảy ra khi constructor đang chạy không?  
**Đáp án:** Không. Những lần đọc có thể xảy ra **trước khi gán giá trị/freeze**; cần tránh early escape.

**Câu 6:** Khi đổi một cấu hình gồm ba trường, reader cần một snapshot có ba giá trị cùng phiên bản. Nên publish từng field volatile riêng hay một immutable object qua một volatile reference?  
**Đáp án:** Thường ưu tiên một immutable snapshot được publish bằng một volatile reference, để reader giữ và đọc cùng một phiên bản.

**Câu 7:** Một worker xử lý message nhận từ `BlockingQueue`. Producer phải tự thêm volatile cho từng field của message immutable chỉ để consumer thấy những ghi trước `put` không?  
**Đáp án:** Không; queue cung cấp memory-consistency cho thao tác giao nhận theo hợp đồng. Mutation sau `put` là chuyện khác.

**Câu 8:** Khi nào nên dùng monitor thay vì chỉ volatile?  
**Đáp án:** Khi có mutable shared state hoặc nhiều hành động/field cần được bảo vệ như **một invariant**, hoặc nhiều writer phải thực hiện compound operation nguyên tử.

## Tài liệu API và đặc tả chính thức

- [Java Language Specification `17.4 — Memory Model, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4): synchronization actions, happens-before, data race.
- [Java Language Specification `17.5 — final Field Semantics, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): freeze và điều kiện correctly constructed.
- [Java Language Specification `12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): khởi tạo class.
- [`Thread` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start()` và `join()`.
- [`BlockingQueue` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): memory consistency cho producer–consumer.
- [`ExecutorService` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), [`Future` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): giao nhận và kết quả task.
- [`AtomicReference` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): atomic replacement và CAS.

**Ghi nhớ:** `final` bảo vệ những giá trị được khởi tạo đúng cách theo final-field semantics; `volatile` công bố state trước write cho reader đồng bộ; khóa bảo vệ cả publication lẫn truy cập mutable state khi các thread dùng chung protocol. Luôn hoàn tất **construction trước publication**, rồi quyết định riêng cách bảo vệ **mutation sau publication**.