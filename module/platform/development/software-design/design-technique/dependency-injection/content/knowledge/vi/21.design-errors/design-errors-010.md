# Khởi tạo với tác dụng phụ khó kiểm soát hoặc làm rò rỉ `this`

## 1. Constructor nên thiết lập trạng thái hợp lệ, không âm thầm vận hành hệ thống

Trong **Dependency Injection (DI)**, các phụ thuộc được cung cấp cho đối tượng từ bên ngoài, thường qua **constructor injection**. **Composition root** là nơi chọn implementation, tạo và nối object graph, xác định scope và quản lý tài nguyên. Cách làm này thể hiện **Inversion of Control (IoC)**: tách trách nhiệm *sử dụng* collaborator khỏi việc *tạo và lắp ghép* nó.

Một lỗi thiết kế quan trọng xuất hiện khi **constructor thực hiện tác dụng phụ khó kiểm soát**, hoặc **đưa tham chiếu `this` ra ngoài trước khi khởi tạo xong**. Ví dụ:

- Tự kết nối database, gọi HTTP, ghi file, gửi email ngay trong constructor.
- Tự đăng ký listener với event bus toàn cục.
- Khởi động thread, lịch chạy job hoặc bất đồng bộ xử lý rồi truyền `this` vào callback.
- Gọi phương thức có thể bị lớp con override trong constructor.
- Đưa `this` vào registry, static field, collection được chia sẻ hoặc collaborator đang hoạt động.
- Xuất bản sự kiện khiến callback quay lại chính đối tượng còn đang khởi tạo.

Các hành vi này có thể khiến instance được sử dụng **khi trạng thái chưa hoàn tất**, tạo tài nguyên không rõ chủ sở hữu, làm lỗi xảy ra giữa chừng và khó kiểm thử.

Điều cần nhớ không phải “constructor tuyệt đối không được gọi phương thức nào hoặc dùng `new`”. Constructor vẫn cần **kiểm tra tham số**, tính toán giá trị, thiết lập bất biến, sao chép phòng vệ và có thể tạo đối tượng dữ liệu nội bộ. Lỗi nằm ở việc đưa **tác động bên ngoài** hoặc **quyền điều khiển chưa kiểm soát** vào giai đoạn đối tượng chưa sẵn sàng.

**Sau bài học, bạn có thể:**

1. Phân biệt khởi tạo trạng thái thuần túy với khởi tạo có tác dụng phụ ngoài phạm vi đối tượng.
2. Giải thích `this escape`, kể cả trường hợp callback đồng bộ chưa cần nhiều thread.
3. Nhận diện việc gọi phương thức override từ constructor và rủi ro quan sát trạng thái chưa hoàn chỉnh.
4. Tách **construct → assemble → start/subscribe → serve → stop/close** bằng Java thuần.
5. Viết test với fake để phát hiện callback đến sớm, registration bị giữ lại và lỗi startup không được rollback.
6. Xác định giới hạn về thread safety, safe publication, scope và lifecycle trước khi dùng DI container.

## 2. Những tác dụng phụ nào nên tránh trong constructor?

### 2.1. Phân loại theo mức độ ảnh hưởng

| Hành động | Trong constructor có hợp lý không? | Lý do |
| --- | --- | --- |
| Gán trường `final`, `Objects.requireNonNull`, kiểm tra invariant | **Thường hợp lý** | Thiết lập trạng thái hợp lệ, không chuyển quyền điều khiển cho hệ thống ngoài. |
| Sao chép `List` đầu vào, tạo value object, tạo collection nội bộ | **Thường hợp lý** | Dữ liệu do chính đối tượng quản lý; cần kiểm tra chi phí và độ lớn. |
| Đọc cấu hình đã được truyền sẵn, tính giá trị dẫn xuất | **Thường hợp lý** nếu không có side effect | Không làm constructor phụ thuộc vào dịch vụ ngoài khi không cần. |
| Mở socket, kết nối DB, gọi REST API, tải secret từ mạng | **Cần cân nhắc mạnh** | Có thể chậm, lỗi giữa chừng, có retry/timeout và tài nguyên phải được đóng. |
| Gửi email, thanh toán, ghi audit hoặc cập nhật trạng thái ngoài | **Thường không phù hợp** | Hành vi nghiệp vụ có side effect xảy ra chỉ vì gọi `new`. |
| Đăng ký event listener, timer hoặc shutdown hook | **Rủi ro** | Công bố `this`, tạo subscription tồn tại ngoài constructor. |
| Gọi `Thread.start()` hoặc submit task bắt `this` | **Rủi ro cao** | Thread/callback có thể chạy trước khi mọi field được khởi tạo. |
| Gọi phương thức có thể bị override trong constructor | **Rủi ro cao** | Lớp con chưa chạy initializer/constructor khi override được gọi. |

**Ngoại lệ có chủ đích:** một kiểu đại diện trực tiếp cho tài nguyên, như một stream hoặc client có constructor mở resource theo API thư viện, có thể cấp phát trong quá trình tạo. Khi đó **composition root hoặc factory phải quản lý ownership**, và chính constructor/factory phải xử lý tài nguyên đã cấp phát nếu khởi tạo thất bại. Không nên suy từ đó rằng mọi lớp nghiệp vụ được phép mở tài nguyên ngầm.

### 2.2. Ba loại chi phí bị giấu

1. **Chi phí thời gian:** `new Service(...)` có thể bất ngờ chờ kết nối hoặc timeout; thời gian startup/test phụ thuộc mạng.
2. **Chi phí tài nguyên:** constructor có thể mở thread pool, socket, listener hoặc file handle; lỗi giữa chừng làm mất chỗ gọi `close()`.
3. **Chi phí hành vi:** đăng ký sự kiện hoặc chạy job là một hành vi quan sát được; test tạo object để kiểm tra một phương thức đơn giản lại vô tình kích hoạt hệ thống khác.

Constructor injection giúp đưa việc **chọn dependency** ra khỏi lớp sử dụng. Tuy nhiên, nếu implementation của dependency tự khởi động thread hoặc đăng ký callback trong constructor, DI **không tự sửa lỗi vòng đời đó**. Cần kiểm tra cả cách tạo adapter cụ thể và chính sách bootstrap.

## 3. `this escape` thực chất là gì?

**`this escape`** xảy ra khi **tham chiếu tới đối tượng đang được xây dựng** trở nên khả dụng cho code bên ngoài trước khi constructor hoàn tất. “Bên ngoài” không nhất thiết phải là thread khác; một collaborator có thể gọi callback **đồng bộ ngay trong lúc đăng ký**, làm đối tượng bị sử dụng quá sớm.

Ví dụ nguy hiểm:

```java
final class PriceListener implements EventListener {
    private final String label;

    PriceListener(EventBus bus) {
        bus.subscribe(this);       // Đưa this ra ngoài quá sớm.
        this.label = "READY";      // Field chưa được gán lúc subscribe.
    }

    @Override
    public void onEvent(String event) {
        System.out.println(label); // Có thể quan sát null.
    }
}
```

`EventBus` và `EventListener` ở đây là các hợp đồng minh họa; phiên bản đầy đủ sẽ có ở mục 5. Nếu `subscribe` gọi `onEvent` trước khi trả về, `label` **chưa được gán** và callback nhìn thấy giá trị mặc định `null`. Java không cấm việc gọi method của instance từ constructor, vì vậy code vẫn có thể biên dịch dù gây lỗi runtime.

### 3.1. Những đường thoát tham chiếu phổ biến

```java
// Ví dụ độc lập về ý tưởng, không phải file chạy hoàn chỉnh.

// 1. Chèn vào registry được nơi khác truy cập.
globalRegistry.add(this);

// 2. Đăng ký callback tham chiếu trực tiếp đến đối tượng.
eventBus.subscribe(this);

// 3. Lambda chụp this gián tiếp qua instance method.
executor.execute(() -> this.process());

// 4. Cho thread truy cập this trước khi constructor kết thúc.
new Thread(this::runLoop).start();

// 5. Truyền this vào collaborator có thể lưu lại hoặc gọi ngược.
otherComponent.bind(this);
```

Các ví dụ trên có mức rủi ro khác nhau tùy collaborator có lưu tham chiếu hay gọi callback ngay. Tuy nhiên, **constructor không kiểm soát được tất cả hành vi của code nhận `this`**, nhất là khi collaborator có thread hoặc queue riêng.

Một lambda không nhất thiết chứa chữ `this` vẫn có thể capture instance:

```java
executor.execute(() -> handleEvent());
```

Khi `handleEvent()` là instance method, lambda cần tham chiếu tới đối tượng hiện tại. Việc trì hoãn chạy lambda **không bảo đảm** nó sẽ chạy sau constructor: executor có thể lập lịch ngay.

### 3.2. Đây không chỉ là vấn đề đa luồng

Giả sử event bus cho phép subscriber nhận một sự kiện `SUBSCRIBED` **ngay khi đăng ký**. Dòng thời gian:

```text
new Listener(bus)
     |
     v
constructor bắt đầu
     |
     v
bus.subscribe(this) ------> bus gọi onEvent("SUBSCRIBED")
     |                               |
     |                               v
     |                       đọc field chưa gán
     |
     v
gán field còn lại
     |
     v
constructor trả về
```

Sự cố xảy ra ngay trên **cùng một thread**. Không cần race condition để thấy trạng thái `null` hoặc invariant chưa được thiết lập.

### 3.3. Trên nhiều thread: liên hệ với Java Memory Model

Khi `this` thoát ra trước khi đối tượng được xây dựng hoàn chỉnh, thread khác có thể quan sát trạng thái chưa khởi tạo, dữ liệu cũ hoặc việc công bố không có đồng bộ đúng. Những bảo đảm đặc biệt của trường `final` gắn với **đối tượng được xây dựng đúng cách** (không để tham chiếu thoát trong quá trình xây dựng). Nếu `this` thoát sớm, không nên dựa vào các bảo đảm đó để coi đối tượng đã được công bố an toàn.

Không phải mọi lần rò `this` đều chắc chắn gây bug; điều nguy hiểm là **hợp đồng khởi tạo và tính an toàn khi công bố không còn được bảo đảm**. Đổi field thành `volatile` hay thêm `synchronized` ở một nơi không tự giải quyết việc callback được gọi trước khi dữ liệu hợp lệ tồn tại.

## 4. Gọi phương thức overridable trong constructor: một rủi ro liên quan

Một dạng khác không nhất thiết làm `this` thoát ra registry nhưng cũng **cho phép logic của đối tượng chưa hoàn chỉnh chạy quá sớm** là gọi phương thức có thể bị override từ constructor lớp cha.

```java
import java.util.ArrayList;
import java.util.List;

abstract class BaseWorker {
    BaseWorker() {
        onReady(); // Virtual dispatch đến override của lớp con.
    }

    abstract void onReady();
}

final class ChildWorker extends BaseWorker {
    private final List<String> messages = new ArrayList<>();

    @Override
    void onReady() {
        // Trong constructor BaseWorker, initializer của ChildWorker
        // chưa chạy, nên messages vẫn có thể bằng null.
        System.out.println(messages == null ? "NOT_READY" : "READY");
    }
}
```

Nếu chạy `new ChildWorker()`, ví dụ in `NOT_READY`. Thứ tự khởi tạo ở đây có ý nghĩa: constructor của superclass chạy trước phần khởi tạo instance fields và constructor body của subclass.

**Cách tránh:** constructor không gọi method overridable để “hoàn tất cấu hình” hoặc “thông báo đã sẵn sàng”. Giữ các bước thiết lập invariant trong method `private`/`final` phù hợp hoặc constructor; chuyển phần mở rộng hành vi sang bước `start()` do composition root gọi **sau khi** object graph đã xây xong.

Cần phân biệt rõ: **gọi method overridable trong constructor** là lỗi về dispatch tới subclass chưa khởi tạo; **`this escape`** là xuất bản tham chiếu đối tượng chưa hoàn chỉnh. Hai lỗi có liên quan nhưng không hoàn toàn đồng nhất.

## 5. Ví dụ chạy được: listener bị đăng ký khi constructor chưa xong

Để quan sát sự cố có tính xác định, ta tạo một event bus **giả lập, đồng bộ**, có hành vi gọi listener ngay khi `subscribe`. Sau đó so sánh:

- **`UnsafeReceiver`** tự đăng ký `this` bên trong constructor, trước khi gán `name`.
- **`SafeReceiver`** chỉ nhận dependency và hoàn tất trạng thái trong constructor.
- **`SafeAssembly`** thuộc vùng lắp ghép: tạo receiver, đăng ký **sau khi constructor trả về**, giữ token đăng ký và đóng ở cuối scope.

Lưu tất cả vào `ConstructorEscapeDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

interface EventListener {
    void onEvent(String event);
}

interface Registration extends AutoCloseable {
    @Override
    void close();
}

// Bus giả lập: subscribe gọi callback đồng bộ với event "SUBSCRIBED".
// Chỉ dùng tuần tự; không phải bus thread-safe cho production.
final class DemoEventBus {
    private final List<EventListener> listeners = new ArrayList<>();

    Registration subscribe(EventListener listener) {
        Objects.requireNonNull(listener, "listener");
        listeners.add(listener);

        try {
            // Callback có thể chạy trước khi subscribe trả về.
            listener.onEvent("SUBSCRIBED");
        } catch (RuntimeException | Error failure) {
            listeners.remove(listener);
            throw failure;
        }

        // Một registration token sở hữu quyền hủy đúng lần đăng ký này.
        return new Registration() {
            private boolean closed;

            @Override
            public void close() {
                if (!closed) {
                    closed = true;
                    listeners.remove(listener);
                }
            }
        };
    }

    void publish(String event) {
        Objects.requireNonNull(event, "event");
        // Snapshot giúp ví dụ không phụ thuộc sửa List trong callback.
        for (EventListener listener : new ArrayList<>(listeners)) {
            listener.onEvent(event);
        }
    }

    int listenerCount() {
        return listeners.size();
    }
}

// Hợp đồng ghi nhận để dễ thay bằng fake trong test.
interface EventRecorder {
    void record(String entry);
}

final class ListEventRecorder implements EventRecorder {
    private final List<String> events = new ArrayList<>();

    @Override
    public void record(String entry) {
        events.add(entry);
    }

    List<String> snapshot() {
        return new ArrayList<>(events);
    }
}

// PHẢN VÍ DỤ: constructor đăng ký this trước khi gán name.
// Ngoài ra nó không giữ registration token để có thể hủy.
final class UnsafeReceiver implements EventListener {
    private final EventRecorder recorder;
    private final String name;

    UnsafeReceiver(DemoEventBus bus, EventRecorder recorder) {
        this.recorder = Objects.requireNonNull(recorder, "recorder");
        Objects.requireNonNull(bus, "bus").subscribe(this);
        this.name = "UNSAFE";
    }

    @Override
    public void onEvent(String event) {
        recorder.record(String.valueOf(name) + ":" + event);
    }
}

// ĐÚNG HƯỚNG: constructor chỉ nhận dependency và dựng invariant.
final class SafeReceiver implements EventListener {
    private final String name;
    private final EventRecorder recorder;

    SafeReceiver(String name, EventRecorder recorder) {
        if (name == null || name.trim().isEmpty()) {
            throw new IllegalArgumentException("INVALID_NAME");
        }
        this.name = name;
        this.recorder = Objects.requireNonNull(recorder, "recorder");
    }

    @Override
    public void onEvent(String event) {
        recorder.record(name + ":" + event);
    }
}

// Vùng lắp ghép/lifecycle: chỉ công bố receiver sau khi new kết thúc.
final class SafeAssembly implements AutoCloseable {
    private final DemoEventBus bus;
    private final Registration registration;
    private boolean closed;

    private SafeAssembly(DemoEventBus bus, Registration registration) {
        this.bus = bus;
        this.registration = registration;
    }

    static SafeAssembly start(DemoEventBus bus, EventRecorder recorder,
                              String name) {
        Objects.requireNonNull(bus, "bus");
        SafeReceiver receiver = new SafeReceiver(name, recorder);
        Registration registration = bus.subscribe(receiver);
        return new SafeAssembly(bus, registration);
    }

    void publish(String event) {
        if (closed) {
            throw new IllegalStateException("APP_ALREADY_STOPPED");
        }
        bus.publish(event);
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            registration.close();
        }
    }
}

public class ConstructorEscapeDemo {
    public static void main(String[] args) {
        DemoEventBus unsafeBus = new DemoEventBus();
        ListEventRecorder unsafeEvents = new ListEventRecorder();

        new UnsafeReceiver(unsafeBus, unsafeEvents);
        unsafeBus.publish("RUN");

        System.out.println("UNSAFE=" + unsafeEvents.snapshot());
        System.out.println("UNSAFE_LISTENERS="
                + unsafeBus.listenerCount());

        DemoEventBus safeBus = new DemoEventBus();
        ListEventRecorder safeEvents = new ListEventRecorder();

        try (SafeAssembly app =
                     SafeAssembly.start(safeBus, safeEvents, "SAFE")) {
            app.publish("RUN");
        }

        // Sau khi đóng registration, callback không còn nhận event.
        safeBus.publish("AFTER_CLOSE");

        System.out.println("SAFE=" + safeEvents.snapshot());
        System.out.println("SAFE_LISTENERS=" + safeBus.listenerCount());
    }
}
```

Biên dịch và chạy:

```bash
javac ConstructorEscapeDemo.java
java ConstructorEscapeDemo
```

Đầu ra dự kiến:

```text
UNSAFE=[null:SUBSCRIBED, UNSAFE:RUN]
UNSAFE_LISTENERS=1
SAFE=[SAFE:SUBSCRIBED, SAFE:RUN]
SAFE_LISTENERS=0
```

### 5.1. Vì sao nhánh `UNSAFE` in `null`?

Khi constructor `UnsafeReceiver` gọi `bus.subscribe(this)`, event bus gọi `onEvent("SUBSCRIBED")` **ngay lập tức**. Trường `recorder` đã được gán, nhưng trường `name` **chưa được gán**. Vì vậy `String.valueOf(name)` ghi `"null"` vào log.

Sau khi constructor kết thúc, `name` là `"UNSAFE"`; event `RUN` được xử lý như bình thường. Điều này làm lỗi khó phát hiện: các lần gọi về sau có thể đều đúng, chỉ callback đến sớm tạo dấu vết sai.

`UNSAFE_LISTENERS=1` còn chỉ ra một vấn đề riêng: constructor **bỏ qua registration token** nên caller không có chỗ rõ ràng để hủy đăng ký. Bus tiếp tục giữ listener và mọi dependency mà listener tham chiếu.

### 5.2. Vì sao nhánh `SAFE` đúng hơn?

`SafeReceiver` được khởi tạo **hoàn chỉnh** trước khi `bus.subscribe(receiver)` diễn ra. Vì thế ngay cả callback đồng bộ `SUBSCRIBED` cũng nhìn thấy `name` hợp lệ. `SafeAssembly` giữ registration token và hủy bằng `close()`; sau khi đóng, bus không còn giữ listener.

`SafeAssembly` thể hiện một dạng **composition/lifecycle boundary**. Trong ứng dụng thực, composition root có thể tự quản lý các token đăng ký hoặc dùng một lớp bootstrap khác; tên lớp không phải phần quan trọng. Quan trọng là **quyền đăng ký, bắt đầu phục vụ và hủy đăng ký nằm ngoài constructor của đối tượng nghiệp vụ**.

### 5.3. Những giới hạn cố ý của ví dụ

- Bus và `SafeAssembly` **không thread-safe**; cờ `closed`, `ArrayList` và các callback được dùng tuần tự.
- `DemoEventBus.subscribe` chủ động rollback việc thêm listener nếu callback ném `RuntimeException` hoặc `Error`. Đây là **hợp đồng của bus giả lập**, không phải bảo đảm của mọi event bus.
- Sau khi một subscriber được hủy, một callback đã bắt đầu chạy trên thread khác (trong hệ thống thực) vẫn có thể tiếp tục. `unsubscribe` không tự đồng nghĩa với **drain toàn bộ callback đang chạy**.
- Bus giả lập không xử lý duplicate registration, retry, queue, timeout hay durability như hạ tầng production.
- Ví dụ minh họa sai lầm của constructor; không nên sao chép `UnsafeReceiver` vào mã sản phẩm.

## 6. Kiểm thử bằng fake: callback đến sớm, rollback và cleanup

Không cần framework mock hoặc DI container để bắt lỗi `this escape`. Ta dùng event bus có hành vi đồng bộ đã biết và recorder trong bộ nhớ để xác minh **thứ tự khởi tạo và đăng ký**.

Lưu `ConstructorEscapeTest.java` cạnh file demo:

```java
import java.util.Arrays;
import java.util.List;

public class ConstructorEscapeTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void checkEvents(List<String> actual, String... expected) {
        if (!actual.equals(Arrays.asList(expected))) {
            throw new AssertionError("Events: " + actual);
        }
    }

    public static void main(String[] args) {
        // Phản ví dụ: listener nhận callback trước khi name được gán.
        DemoEventBus badBus = new DemoEventBus();
        ListEventRecorder badLog = new ListEventRecorder();

        new UnsafeReceiver(badBus, badLog);

        checkEvents(badLog.snapshot(), "null:SUBSCRIBED");
        check(badBus.listenerCount() == 1,
                "Phản ví dụ chưa cho thấy đăng ký bị giữ lại");

        // Phiên bản sửa: new hoàn tất rồi mới subscribe.
        DemoEventBus bus = new DemoEventBus();
        ListEventRecorder log = new ListEventRecorder();
        SafeAssembly app = SafeAssembly.start(bus, log, "GOOD");

        checkEvents(log.snapshot(), "GOOD:SUBSCRIBED");
        check(bus.listenerCount() == 1, "Chưa đăng ký subscriber");

        app.publish("NEXT");
        checkEvents(log.snapshot(),
                "GOOD:SUBSCRIBED", "GOOD:NEXT");

        app.close();
        app.close(); // Theo hợp đồng ví dụ, close không lặp tác dụng phụ.

        check(bus.listenerCount() == 0, "Chưa hủy registration");
        bus.publish("AFTER");
        checkEvents(log.snapshot(),
                "GOOD:SUBSCRIBED", "GOOD:NEXT");

        boolean rejectedAfterStop = false;
        try {
            app.publish("LATE");
        } catch (IllegalStateException expected) {
            rejectedAfterStop = true;
        }
        check(rejectedAfterStop, "Đã dừng nhưng vẫn phục vụ");

        // Constructor sai tham số phải lỗi trước bước đăng ký.
        DemoEventBus invalidBus = new DemoEventBus();
        boolean invalidRejected = false;
        try {
            SafeAssembly.start(invalidBus, new ListEventRecorder(), " ");
        } catch (IllegalArgumentException expected) {
            invalidRejected = true;
        }
        check(invalidRejected && invalidBus.listenerCount() == 0,
                "Khởi tạo sai vẫn giữ registration");

        // subscribe gọi callback đồng bộ; nếu callback lỗi,
        // bus demo phải rollback phần đăng ký đã thực hiện.
        DemoEventBus failingBus = new DemoEventBus();
        EventRecorder failingRecorder = entry -> {
            throw new IllegalStateException("SIMULATED_FAILURE");
        };

        boolean callbackFailureObserved = false;
        try {
            SafeAssembly.start(failingBus, failingRecorder, "GOOD");
        } catch (IllegalStateException expected) {
            callbackFailureObserved = true;
        }
        check(callbackFailureObserved, "Đã nuốt lỗi callback");
        check(failingBus.listenerCount() == 0,
                "Startup lỗi nhưng bus còn giữ listener");

        System.out.println("PASS");
    }
}
```

Chạy:

```bash
javac ConstructorEscapeDemo.java ConstructorEscapeTest.java
java ConstructorEscapeTest
```

Kết quả mong đợi: `PASS`.

Bài test này xác minh:

1. Callback `SUBSCRIBED` của bus chạy **ngay trong constructor** ở nhánh sai và đọc được `name == null`.
2. Cấu hình đúng công bố receiver sau khi constructor hoàn tất.
3. `close()` hủy registration, không để callback mới nhận event sau khi đóng trong mô hình tuần tự.
4. Lỗi tham số được phát hiện trước khi có bất kỳ đăng ký nào.
5. Khi callback ném exception trong `subscribe`, bus giả lập rollback registration thay vì giữ một listener mà root không sở hữu được.

Bài test **không chứng minh** thread safety, shutdown đúng khi callback đang chạy trên nhiều thread, hay hành vi của event bus production. Muốn xác minh các đặc tính đó cần **integration/concurrency test** theo contract của thư viện sự kiện thực.

## 7. Tách `construct`, `start` và `close` như thế nào?

Một hướng thiết kế có thể biểu diễn thành:

```text
              COMPOSITION ROOT
                    |
                    v
            Construct dependencies
                    |
                    v
           Construct application
             services/handlers
                    |
                    v
            Connect listeners
             and start worker
                    |
                    v
               Mark READY
                    |
                    v
                Serve work
                    |
                    v
           Stop accepting work
                    |
                    v
             Drain/cancel work
                    |
                    v
           Close registrations
             and resources
```

**Bước khởi tạo thuần túy** đặt các invariant vào trạng thái hợp lệ. **Bước start/registration** tác động tới hạ tầng sau khi graph đã hoàn chỉnh. **Bước close/stop** giải phóng các thứ được đăng ký hoặc tạo bởi vùng lắp ghép.

Không nhất thiết mọi lớp đều cần `start()` và `close()`. Những lớp chỉ tính toán, không sở hữu resource hay callback, thường chỉ cần constructor và phương thức nghiệp vụ. Chỉ các thành phần **thực sự có vòng đời** mới nên mang API lifecycle tương ứng.

### 7.1. Nếu một service cần `start()`

Có thể thiết kế một vòng đời có kiểm soát:

```java
// Pseudocode minh họa, không phải file độc lập.
final class MessagePoller implements AutoCloseable {
    private State state = State.NEW;

    MessagePoller(Client client, Handler handler) {
        this.client = Objects.requireNonNull(client);
        this.handler = Objects.requireNonNull(handler);
    }

    void start() {
        // Chỉ NEW -> STARTING -> READY khi mở listener thành công.
        // Rollback registration nếu bước mở thất bại.
    }

    @Override
    public void close() {
        // Ngừng nhận việc -> drain -> đóng tài nguyên do lớp sở hữu.
    }
}
```

`State`, `Client` và `Handler` được lược bỏ vì đoạn này chỉ giới thiệu cấu trúc. Khi triển khai thật, phải quy định **có cho gọi `start` hai lần không**, **close khi chưa start làm gì**, **close khi đang start làm gì**, và **lỗi cleanup được báo thế nào**.

Việc có method `start()` **không tự tạo thread safety**. Một state machine đúng cần đồng bộ hóa hoặc cơ chế phối hợp phù hợp khi nhiều thread có thể đồng thời gọi start/stop.

### 7.2. Không công bố READY quá sớm

Việc mọi constructor trả về **chưa chứng minh** database, listener, queue hay HTTP client đã sẵn sàng. Nếu bootstrap yêu cầu các dependency hoạt động, root có thể thực hiện readiness checks sau khi lắp graph, rồi mới cho nhận traffic.

Nếu `start()` kích hoạt callback ngay lập tức, receiver cần đã hoàn chỉnh; nếu callback xử lý yêu cầu thật, cần đảm bảo những dependency khác của graph cũng sẵn sàng. **Ready là một điều kiện vận hành được xác định**, không chỉ một nhãn gắn sau `new`.

## 8. Tác dụng phụ trong constructor và khởi động thất bại giữa chừng

Xét một lớp tự mở kết nối rồi đăng ký listener:

```java
// Anti-pattern minh họa; các lớp không phải API Java thực.
final class UnsafePaymentWatcher {
    UnsafePaymentWatcher(Config config, EventBus bus) {
        Connection connection = connect(config);
        bus.subscribe(this);
        // Nếu subscribe ném exception, ai đóng connection?
    }
}
```

Nếu constructor ném lỗi sau khi mở connection, **caller không nhận được instance** để đóng. Constructor/factory phải tự cleanup phần tài nguyên đã tạo, hoặc tốt hơn chuyển việc tạo và đăng ký về một composition root/lifecycle manager có khả năng rollback rõ ràng.

### 8.1. Khởi động có rollback tại composition root

```java
// Mã minh họa có cấu trúc Java thuần;
// các type ManagedClient, EventBus, Handler, Registration là giả định.
try (ManagedClient client = createClient(config)) {
    Handler handler = new Handler(client);  // Chỉ gán dependency.

    try (Registration listener = bus.subscribe(handler)) {
        // Chỉ phục vụ khi cả client và registration hợp lệ.
        runApplication(handler);
    } // Đóng listener trước khi đóng client.
} // Đóng client ngay cả khi subscribe/runApplication lỗi.
```

Nếu `subscribe` ném exception, `ManagedClient` vẫn được đóng nhờ `try-with-resources`. Nếu `subscribe` tự đăng ký một phần trước khi ném lỗi, **chính API subscribe phải có chính sách rollback**, vì caller chưa có registration token để đóng. Ở ví dụ mục 5, `DemoEventBus` chủ động xóa listener khi callback ném exception.

**Lưu ý:** `try-with-resources` chỉ áp dụng trực tiếp cho kiểu `AutoCloseable`/`Closeable`; nó không tự đóng mọi resource tùy ý. Cũng không bảo đảm các callback bất đồng bộ đã hoàn tất. Hệ thống đồng thời phải **stop/drain** trước khi đóng client mà callback vẫn đang sử dụng.

### 8.2. Vì sao constructor có side effect làm khó rollback?

| Tình huống | Khi side effect nằm trong constructor | Khi quản lý tại bootstrap/lifecycle |
| --- | --- | --- |
| Mở resource A thành công, tạo B thất bại | Caller có thể chưa nhận instance sở hữu A. | Root lưu quyền sở hữu A, có thể đóng A khi B lỗi. |
| Đăng ký event listener | Khó biết ai giữ token, có thể bị callback ngay. | Root đăng ký sau khi receiver hoàn chỉnh và giữ token. |
| Bắt đầu thread | Thread có thể sử dụng trường chưa gán; khó dừng nếu constructor lỗi. | Root khởi động sau khi wiring hoàn thành và định nghĩa stop/join. |
| Khởi tạo trong unit test | Tạo object có thể chạm mạng, gửi event, làm test chậm. | Test tạo object thuần, inject fake; chủ động quyết định start hay không. |
| Shutdown | Không rõ ai phải hủy listener/resource. | Owner rõ ràng đóng theo thứ tự hợp đồng. |

Mấu chốt là **ownership gắn với quá trình tạo và đăng ký**, không được ẩn bên trong một constructor của service chỉ nên dùng dependency.

## 9. Các kiểu rò `this` phức tạp hơn trong hệ thống thực

### 9.1. Đăng ký với global registry hoặc event dispatcher

Một registry/static collection có thể giữ listener sống lâu hơn request hoặc component. Nếu listener giữ reference đến user/session context, lỗi còn có thể khiến dữ liệu của request trước còn tồn tại sau khi request kết thúc.

Cần định nghĩa **scope của subscription**: application, request, session hay task. Khi scope kết thúc, owner phải unsubscribe; có thể cần dừng những callback đang chạy trước khi giải phóng dependency.

### 9.2. `Thread.start()` và executor trong constructor

```java
// Anti-pattern: worker có thể gọi run() khi constructor chưa xong.
final class UnsafeWorker implements Runnable {
    private final String workerId;

    UnsafeWorker() {
        new Thread(this).start();
        workerId = loadWorkerId();
    }

    @Override
    public void run() {
        // workerId chưa chắc đã được gán khi chạy tới đây.
    }
}
```

`loadWorkerId()` là hàm minh họa. Thread có thể bắt đầu sau constructor trong nhiều lần chạy và khiến bug khó tái hiện, nhưng **không có bảo đảm** về thứ tự đó. Hơn nữa, thread được tạo ngầm không có owner rõ để shutdown, join hay xử lý exception.

Hướng sửa là tạo worker hoàn chỉnh rồi để composition root/executor có quản lý lifecycle chủ động chạy nó. Nếu task cần state theo request, hãy truyền dữ liệu cần thiết và snapshot có kiểm soát; không capture nguyên `RequestContext` của request sắp kết thúc.

### 9.3. Đăng ký callback trong superclass constructor

Nếu lớp cha đăng ký `this` trước khi constructor lớp con chạy, callback có thể gọi override của lớp con lúc trạng thái lớp con còn mặc định. Cách tránh là **không công bố `this` trong constructor lớp cha** và tránh virtual method dispatch trong quá trình khởi tạo.

### 9.4. Đưa `this` qua factory/collaborator không rõ semantics

Một constructor có thể gọi `factory.attach(this)`. Dù factory tên là “factory”, nếu nó lưu object vào cache toàn cục hoặc đăng ký callback, tham chiếu đã thoát. **Tên interface không chứng minh API là an toàn**; cần đọc contract về việc collaborator có giữ hay sử dụng tham chiếu ngay không.

### 9.5. Cẩn thận với lifecycle hook của DI container

DI container có thể cung cấp post-construction callback, bean lifecycle hook hoặc cơ chế publish event. Chúng hỗ trợ chuyển side effect khỏi constructor, nhưng vẫn cần kiểm tra **thời điểm hook chạy so với toàn graph, thứ tự start, scope, callback đồng thời và destroy hook**.

Nếu một hook bắt đầu nhận request trước khi các dependency cần thiết sẵn sàng, vẫn có lỗi vòng đời dù đã bỏ `this` khỏi constructor. Container không tự bảo đảm việc tắt có drain đúng, hay một resource do ứng dụng tự tạo sẽ được đóng nếu không khai báo ownership.

## 10. Khi nào có thể có công việc đáng kể trong constructor?

Cần phân biệt **tính toán nội bộ** với **tác dụng phụ bên ngoài** và cân nhắc chi phí:

- Tạo defensive copy của `List`, chuẩn hóa cấu hình thuần túy, dựng giá trị bất biến hoặc kiểm tra tham số thường hợp lý.
- Khởi tạo bảng tra nội bộ lớn có thể tốn CPU/bộ nhớ nhưng chưa chắc có side effect ngoài; hãy đo chi phí khởi động và cân nhắc factory/lazy nếu cần.
- Constructor của một adapter resource có thể mở kết nối nếu đó là contract công khai, nhưng phải có cách dọn tài nguyên khi constructor thất bại và chủ sở hữu rõ ràng.
- Một cache in-memory nội bộ có thể được tạo trong constructor; điều quan trọng là nó không công bố `this`, không chạy thread ngầm và có chính sách size/scope phù hợp.
- Nếu thao tác phụ thuộc thời gian, mạng, filesystem, scheduler hoặc hệ thống bên ngoài, cân nhắc **tách thành bước start/open** để caller kiểm soát lỗi và ownership.

Một nguyên tắc thực tế: **constructor nên làm rõ trạng thái tối thiểu để đối tượng hợp lệ; các hành động có thể kích hoạt bên ngoài nên có entry point và lifecycle có tên rõ ràng**.

## 11. Checklist rà soát lỗi thiết kế

| Câu hỏi khi review | Cách kiểm tra |
| --- | --- |
| Constructor có gọi API mạng, file, queue hoặc database không? | Tách việc mở tài nguyên về factory/root khi phù hợp; xác định rollback khi lỗi giữa chừng. |
| Có `register(this)`, `bind(this)`, `addListener(this)` không? | Kiểm tra callback có thể chạy ngay; chuyển đăng ký sau constructor và giữ token. |
| Có lambda/method reference capture instance trong constructor? | Kiểm tra executor có thể chạy ngay và callback có thể quan sát field chưa gán. |
| Constructor lớp cha có gọi method overridable? | Tránh virtual dispatch trước khi subclass hoàn tất khởi tạo. |
| Nếu constructor lỗi giữa chừng, tài nguyên nào đã được tạo? | Viết startup failure test, kiểm tra rollback/close. |
| Ai sở hữu subscription, thread, timer và client? | Bảo đảm có chủ sở hữu cụ thể, scope đúng và cleanup trong `close`/lifecycle. |
| Có cho xử lý request trước trạng thái READY không? | Định nghĩa readiness sau khi wiring/start thành công. |
| `close` có thể chạy đồng thời với callback đang xử lý không? | Thiết kế stop/drain, đồng bộ và timeout theo yêu cầu. |
| Test có phát hiện callback sớm và đăng ký còn sót không? | Dùng fake gọi callback **ngay lúc subscribe**, ghi sự kiện và đếm listener. |
| Có dùng `final` để ngầm kết luận đã an toàn đa luồng? | Kiểm tra object có thoát trong constructor không và cách công bố an toàn. |

## 12. Bài tập thực hành: refactor một worker nhận sự kiện

**Bối cảnh:** một ứng dụng đặt hàng có `ShipmentListener`, `ShipmentService` và `MessageConsumer`. Constructor hiện tại tự tạo client, đăng ký callback và khởi động worker:

```java
// Pseudocode anti-pattern: những lớp phụ thuộc chưa được định nghĩa.
final class UnsafeShipmentListener {
    private final ShipmentService service;
    private final MessageConsumer consumer;

    UnsafeShipmentListener(Config config) {
        consumer = new MessageConsumer(config);
        consumer.onMessage(msg -> handle(msg)); // Lambda capture this.
        consumer.start();
        service = new ShipmentService();       // Gán sau khi start!
    }

    void handle(Message message) {
        service.process(message); // Có thể chưa được gán.
    }
}
```

Hãy hoàn thành:

1. **Nhận diện side effect:** nêu những thao tác trong constructor có thể gây I/O hoặc chuyển quyền điều khiển ra bên ngoài.
2. **Phân tích `this escape`:** lambda nào capture instance, callback có thể đến khi `service` ở trạng thái nào, và vì sao không cần nhiều thread vẫn có thể lỗi nếu `onMessage` gọi callback đồng bộ?
3. **Thiết kế dependency tường minh:** viết `ShipmentListener(ShipmentService service)` hoặc một handler thuần chỉ nhận service; không tự tạo consumer hoặc client trong nghiệp vụ.
4. **Viết composition root:** tạo `ShipmentService` và các adapter cần thiết, rồi tạo listener; sau đó đăng ký callback và gọi `start()` của consumer khi graph sẵn sàng.
5. **Thiết kế ownership:** ai giữ registration token, ai đóng `MessageConsumer`, ai dừng worker khi ứng dụng shutdown?
6. **Xử lý lỗi startup:** nếu consumer khởi động lỗi sau khi client đã mở, hãy nêu thứ tự rollback, giữ lỗi gốc và cleanup những resource đã tạo.
7. **Viết fake test đồng bộ:** ngay khi đăng ký, consumer giả gửi một message thử; kiểm tra handler đã có service hợp lệ và không ném lỗi do field chưa gán.
8. **Kiểm thử đóng:** sau khi hủy registration/stop, consumer không gọi handler mới; nếu callback đã bắt đầu xử lý, cần thêm bảo đảm nào để shutdown không đóng dependency quá sớm?
9. **Phân tích scope:** một handler dùng chung có nên giữ `RequestContext` của request đã tạo job không? Đề xuất payload dành riêng cho task và cách tạo task graph.
10. **Chuyển sang DI container:** sẽ xác minh lifecycle hook, thứ tự READY và quyền sở hữu consumer như thế nào thay vì giả định framework làm đúng?

**Gợi ý tự đối chiếu:** service và handler cần được khởi tạo hoàn chỉnh trước khi callback có thể thấy chúng; việc tạo client, đăng ký, start và close nên do composition root/lifecycle manager kiểm soát. Test giả gọi callback ngay khi subscribe sẽ phơi bày lỗi mà test chỉ gửi event sau constructor thường bỏ sót. Bảo vệ `this` trong constructor không thay thế test đồng thời, xử lý in-flight và shutdown đúng trong hệ thống thật.

**Điểm cần nhớ:** Constructor injection làm dependency rõ ràng, nhưng **constructor có side effect hoặc để `this` thoát sớm vẫn có thể tạo object graph không an toàn**. Hãy giữ constructor tập trung vào invariant, công bố đối tượng sau khi hoàn chỉnh, đăng ký/start ở ranh giới lifecycle có owner và rollback, rồi kiểm thử thứ tự bằng Java thuần. Đây là nền tảng trước khi giao việc wiring và quản lý vòng đời cho DI container.
