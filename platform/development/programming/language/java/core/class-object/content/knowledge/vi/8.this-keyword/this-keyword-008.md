# Rủi ro để `this` thoát ra khi khởi tạo chưa hoàn tất trong Java

Một đối tượng Java không trở nên “sẵn sàng sử dụng” ngay tại thời điểm bộ nhớ được cấp phát. Khi thực thi constructor, các trường đang được gán giá trị, các lớp cha và lớp con đang lần lượt khởi tạo, và các **bất biến của đối tượng** (*object invariants*) có thể chưa được thiết lập đầy đủ. Nếu tham chiếu **`this`** bị đưa tới mã bên ngoài quá sớm, mã ấy có thể quan sát hoặc gọi phương thức trên một **đối tượng khởi tạo dở dang**.

Hiện tượng này thường được gọi là **`this` escape trong constructor** hoặc **premature publication**. Đây không chỉ là vấn đề đa luồng: một listener được gọi **ngay trong cùng luồng** cũng có thể nhìn thấy trường chưa được gán. Trong môi trường nhiều luồng, nó còn gây rủi ro về *visibility*, *data race* và phá vỡ bảo đảm an toàn khởi tạo của các trường `final`.

Bài học tập trung vào Java Core — class/object, từ khóa `this`, trình bày cơ chế, tình huống nguy hiểm, cách sửa và giới hạn từng biện pháp. Các ví dụ hoàn chỉnh sử dụng **Java 17+**.

## 1. `this` escape nghĩa là gì?

Trong một constructor hoặc phương thức instance, `this` tham chiếu tới **đối tượng hiện tại**. **Escape** xảy ra khi tham chiếu tới đối tượng đang được tạo trở nên truy cập được ở bên ngoài quá trình khởi tạo trước khi quá trình ấy kết thúc.

Ví dụ thường gặp:

~~~java
class Example {
    Example(EventBus bus) {
        bus.register(this); // Minh họa: đưa object đang tạo cho đối tượng khác.
    }
}
~~~

Đoạn này là **mã minh họa**, chưa biên dịch độc lập vì không định nghĩa `EventBus`. Nguy cơ phụ thuộc `register` làm gì: nó có thể **lưu** tham chiếu vào danh sách dùng chung, **gọi lại** ngay một phương thức trên object, hoặc cho một luồng khác truy cập vào object đó.

Một số biểu hiện:

- Gán `this` vào trường `static` hoặc một kho lưu trữ dùng chung ngay trong constructor.
- Đăng ký `this` làm **listener/observer** trước khi khởi tạo xong.
- Truyền `this` vào một API có thể giữ tham chiếu hoặc gọi callback ngay.
- Khởi động thread/task trong constructor, với lambda hoặc method reference **bắt giữ `this`**.
- Gọi phương thức **có thể bị override** trong constructor; phiên bản lớp con có thể chạy trước khi trường lớp con được khởi tạo. Đây là một nguy cơ liên quan tới *partial initialization*, dù lời gọi ấy không nhất thiết công bố object ra ngoài.

**Không phải cứ viết `this` là escape.** Câu `this.name = name;` chỉ gán một trường trên đối tượng hiện tại; nó không tự chuyển tham chiếu cho bên ngoài.

## 2. Đối tượng ở trạng thái nào trong constructor?

Với một lớp thông thường, các trường instance ban đầu có **giá trị mặc định** như `0`, `false` và `null`. Sau đó Java tiến hành chuỗi khởi tạo lớp cha/con, field initializer, instance initializer và thân constructor theo quy tắc của ngôn ngữ. Trong quá trình này, một thời điểm trung gian có thể thấy:

~~~text
Đối tượng đang khởi tạo
  id        = "ORD-01"   (đã gán)
  owner     = null       (chưa gán)
  quantity  = 0          (mặc định, chưa kiểm tra)
  ready     = false      (chưa hoàn tất)
~~~

Đây chỉ là **sơ đồ giả định**, không phải một đối tượng có thể chạy độc lập. Nếu hợp đồng yêu cầu `owner` luôn không rỗng và `quantity > 0` sau khi tạo thành công, các điều kiện đó chưa chắc đúng ở giữa constructor.

Phân biệt ba thời điểm:

| Thời điểm | Trạng thái |
| --- | --- |
| Ngay sau cấp phát bộ nhớ | Các instance fields có giá trị mặc định |
| Đang thực thi chuỗi khởi tạo | Có trường đã gán, có trường chưa gán; invariant có thể chưa đúng |
| Constructor hoàn thành bình thường | Đối tượng phải thỏa những invariant mà tác giả lớp đã thiết kế |

Java không tự kiểm tra mọi invariant nghiệp vụ. **Lớp phải chủ động kiểm tra và thiết lập chúng**, trước khi trao cho bên ngoài khả năng sử dụng object.

## 3. Vì sao `this` escape nguy hiểm kể cả khi không có thread?

Nhiều người nghĩ lỗi chỉ xảy ra khi constructor khởi động thread. Thực tế, **đồng bộ hay không đồng bộ đều không sửa được việc gọi callback trước lúc gán field**. Hãy hình dung:

~~~text
Constructor bắt đầu
  |
  +--> đăng ký listener: this::onEvent
  |
  +--> bộ phát sự kiện gọi listener NGAY LẬP TỨC
  |      |
  |      +--> onEvent đọc field còn null
  |
  +--> constructor mới gán field = "READY"
  |
Constructor hoàn tất
~~~

Không có tranh chấp lịch chạy ở sơ đồ trên. Callback chạy trên cùng call stack và đọc trạng thái **trước** khi field được gán. Dù đưa `synchronized` vào một vài phương thức, gọi lại quá sớm trong cùng luồng vẫn có thể quan sát trạng thái chưa hoàn chỉnh; hơn nữa Java monitor là **reentrant**.

**Chốt nguyên nhân:** không phải `null` là lỗi của Java. Trường chưa được gán có giá trị mặc định đúng theo ngôn ngữ; lỗi thiết kế là **cho phép sử dụng object khi hợp đồng của nó chưa đúng**.

## 4. Ví dụ chạy được: listener đọc trường `null` giữa constructor

Tạo một tệp **`ThisEscapeDemo.java`** như sau. Chương trình chỉ dùng một luồng, vì vậy output có thể dự đoán chính xác.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

class EventBus {
    private final List<Runnable> listeners = new ArrayList<>();

    synchronized void register(Runnable listener) {
        listeners.add(Objects.requireNonNull(listener));
    }

    void fireAll() {
        List<Runnable> snapshot;
        synchronized (this) {
            snapshot = List.copyOf(listeners);
        }
        for (Runnable listener : snapshot) {
            listener.run();
        }
    }
}

class EarlySubscriber {
    private String status;

    EarlySubscriber(EventBus bus) {
        bus.register(this::onEvent);
        bus.fireAll();          // Callback chạy trước khi status được gán.
        this.status = "READY";
    }

    private void onEvent() {
        System.out.println("early=" + status);
    }
}

class SafeSubscriber {
    private final String status;

    private SafeSubscriber(String status) {
        this.status = Objects.requireNonNull(status);
    }

    static SafeSubscriber create(EventBus bus, String status) {
        Objects.requireNonNull(bus);
        SafeSubscriber result = new SafeSubscriber(status);
        bus.register(result::onEvent);
        return result;
    }

    private void onEvent() {
        System.out.println("safe=" + status);
    }

    String status() {
        return status;
    }
}

public class ThisEscapeDemo {
    public static void main(String[] args) {
        EventBus firstBus = new EventBus();
        new EarlySubscriber(firstBus);
        firstBus.fireAll();

        EventBus secondBus = new EventBus();
        SafeSubscriber ready = SafeSubscriber.create(secondBus, "READY");
        secondBus.fireAll();
        System.out.println("value=" + ready.status());
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ThisEscapeDemo.java
java ThisEscapeDemo
~~~

**Stdout chính xác:**

~~~text
early=null
early=READY
safe=READY
value=READY
~~~

### Tại sao `early=null` xuất hiện?

1. `new EarlySubscriber(firstBus)` tạo đối tượng; trường `status` ban đầu là `null`.
2. Constructor gọi `bus.register(this::onEvent)`. Method reference **ràng buộc receiver hiện tại**, tức object đang được tạo, rồi trao callback cho `EventBus`.
3. `bus.fireAll()` chạy callback **ngay trong constructor**. `onEvent()` đọc `status`, lúc này vẫn là `null`, nên in `early=null`.
4. Constructor tiếp tục gán `this.status = "READY";`, rồi kết thúc.
5. Lần `firstBus.fireAll()` bên ngoài constructor in `early=READY`.

Đây là lỗi có thể tái hiện **chắc chắn** trong chương trình, không dựa vào việc thread nào chạy trước. `this::onEvent` không hiện ra chữ `this` trong phần thân callback, nhưng chính việc đăng ký method reference đó đã đưa tham chiếu tới object ra bên ngoài.

### Vì sao `SafeSubscriber` tránh được lỗi trên?

Constructor `SafeSubscriber(String)` chỉ làm việc nội bộ, hoàn tất gán trường `final status` trước khi trả về. Factory `create(...)` thực hiện theo thứ tự:

~~~text
new SafeSubscriber(status)
           |
           v
   constructor HOÀN TẤT
           |
           v
   bus.register(result::onEvent)
           |
           v
        return result
~~~

Vì đăng ký chỉ xảy ra **sau** khi constructor hoàn tất, callback do bus kích hoạt sẽ không bắt gặp đối tượng đang tạo dở trong con đường thiết kế này.

`EventBus.register` và phần chụp listener ở `fireAll` dùng **cùng monitor**, nên có cả một đường truyền *happens-before* thích hợp giữa việc đăng ký và luồng khác lấy snapshot bằng monitor ấy. Việc copy danh sách rồi chạy callback **ngoài** khối `synchronized` còn tránh giữ khóa trong lúc thực thi mã listener. Ví dụ minh họa cơ chế đăng ký đơn giản, chưa phải event bus sản xuất có cơ chế hủy đăng ký, backpressure hoặc quản lý lỗi callback.

**Điểm cần nhớ:** thay đổi thứ tự thành **khởi tạo đầy đủ trước, đăng ký sau** quan trọng hơn việc chỉ thêm modifier `final` hay `synchronized` mà vẫn đăng ký quá sớm.

## 5. Rủi ro khi khởi động thread trong constructor

Ví dụ phổ biến khác là để task chạy khi các trường của object chưa được thiết lập:

~~~java
class UnsafeWorker {
    private int expected;

    UnsafeWorker() {
        new Thread(() -> System.out.println(expected)).start();
        expected = 42;
    }
}
~~~

Đây là **lớp minh họa**, không có `main` hay output được cam kết. Lambda tham chiếu đến `expected`, tức trường instance của `this`. Nó được truyền cho thread mới trước khi câu lệnh `expected = 42` chạy.

**Một lần chạy có thể in `0` hoặc `42`**, và không nên thiết kế dựa vào bất kỳ một kết quả nào. Thread mới có thể được lập lịch trước khi phép gán xảy ra. Kể cả khi thread được lập lịch sau, nếu không thiết lập quan hệ đồng bộ phù hợp cho những truy cập chia sẻ, chương trình còn có thể gặp vấn đề visibility theo Java Memory Model.

`Thread.start()` tạo quan hệ *happens-before* từ **những hành động xảy ra trước lời gọi `start()`** tới các hành động trong thread được khởi động. Nó **không tự bảo đảm** những phép gán thực hiện **sau** lời gọi `start()` đã được thread mới nhìn thấy.

Vì vậy code sau sai về thứ tự:

~~~java
new Thread(this::runTask).start();
this.expected = 42; // Quá muộn để làm tiền điều kiện cho task.
~~~

Đây cũng là **đoạn minh họa**, không phải mã hoàn chỉnh. Vấn đề không chỉ nằm ở `new Thread`: đưa callback giữ `this` cho `ExecutorService.submit`, `CompletableFuture.runAsync` hoặc scheduler trong constructor có rủi ro tương tự nếu task bắt đầu quá sớm.

## 6. Cách làm tốt hơn khi object cần tự chạy task

Tách **khởi tạo trạng thái** khỏi **bắt đầu hoạt động**. Ví dụ tệp độc lập **`SafeWorkerDemo.java`**:

~~~java
import java.util.Objects;

final class Worker {
    private final String taskName;
    private final int expected;

    private Worker(String taskName, int expected) {
        this.taskName = Objects.requireNonNull(taskName);
        if (taskName.isBlank()) {
            throw new IllegalArgumentException("taskName rỗng");
        }
        if (expected < 0) {
            throw new IllegalArgumentException("expected âm");
        }
        this.expected = expected;
    }

    static Worker create(String taskName, int expected) {
        return new Worker(taskName, expected);
    }

    Thread startAsync() {
        Thread thread = new Thread(
                () -> System.out.println(taskName + "=" + expected));
        thread.start();
        return thread;
    }
}

public class SafeWorkerDemo {
    public static void main(String[] args) throws InterruptedException {
        Worker worker = Worker.create("job", 42);
        Thread running = worker.startAsync();
        running.join();
        System.out.println("done");
    }
}
~~~

Lệnh chạy:

~~~bash
javac -encoding UTF-8 SafeWorkerDemo.java
java SafeWorkerDemo
~~~

**Stdout:**

~~~text
job=42
done
~~~

Ở đây:

- `Worker.create` hoàn tất constructor trước khi trả về instance.
- Bên gọi chỉ thực hiện `startAsync()` **sau khi đã có đối tượng hợp lệ**.
- `taskName` và `expected` được gán trước `thread.start()`; quy tắc *happens-before* của `Thread.start()` giúp thread mới nhìn thấy trạng thái trước đó.
- `join()` ở `main` bảo đảm thread đã kết thúc trước khi in `done`, vì vậy thứ tự hai dòng output ổn định.

**Giới hạn:** ví dụ cố ý chỉ cho chạy một tác vụ. API thực tế phải quyết định có cho gọi `startAsync()` nhiều lần hay không, ai quản lý thread, hủy tác vụ, lỗi và tài nguyên. Nếu muốn thao tác start một lần, cần thêm cơ chế quản lý trạng thái và đồng bộ thích hợp; bản thân mẫu “start sau constructor” không giải quyết mọi vấn đề concurrent lifecycle.

## 7. Các cách `this` thường bị công bố quá sớm

| Tình huống trong constructor | Vì sao có thể escape? | Cách xử lý thường tốt hơn |
| --- | --- | --- |
| `Global.current = this;` | Một mã khác có thể đọc trường dùng chung | Công bố sau khi hoàn tất khởi tạo, dùng safe publication |
| `listeners.add(this);` | Listener registry giữ object và có thể callback | Đăng ký sau constructor, qua factory hoặc bước activate |
| `eventBus.register(this::handle)` | Method reference giữ receiver `this` | Đăng ký sau khi object hoàn thành |
| `executor.submit(() -> useField())` | Lambda ngầm bắt giữ `this` | Submit sau khởi tạo, khi state đã hợp lệ |
| `new Thread(this::run).start()` | Thread khác có thể đọc object ngay | Bắt đầu trong method riêng sau khi khởi tạo |
| `external.attach(this)` | API ngoài có thể lưu hoặc gọi lại object | Nghiên cứu hợp đồng API, di chuyển attach ra ngoài ctor |
| Đăng ký callback qua anonymous inner class | Lớp trong có thể giữ tham chiếu tới instance ngoài | Chỉ chuyển callback ra ngoài sau khi đối tượng hoàn tất |
| Constructor gọi method có thể override | Method lớp con đọc field chưa khởi tạo | Không gọi phương thức overridable từ constructor |

**Không nên suy đoán** rằng mọi method nhận `this` đều nhất định lưu nó. Nếu một phương thức chỉ đọc ngay một vài trường đã ổn định, rủi ro có thể khác. Tuy nhiên constructor không nên phụ thuộc vào hành vi không công bố của API bên ngoài khi điều đó có thể tạo đường truy cập đến object chưa hoàn thiện.

### Escape không nhất thiết phải viết `this` một cách tường minh

Các dạng có thể **bắt giữ receiver**:

~~~java
register(this::handle);
register(() -> handle());
executor.execute(() -> System.out.println(this.state));
~~~

Đây là các **dòng minh họa**, phụ thuộc vào các định nghĩa `register`, `executor`, `handle` và `state` phù hợp. `handle()` trong lambda cuối cùng vẫn là lời gọi instance method trên object bao ngoài. Vì vậy tìm mỗi chuỗi ký tự `register(this)` trong code không đủ để phát hiện mọi trường hợp escape.

## 8. Constructor gọi method có thể override: một lỗi liên quan

Một nguy cơ khác xảy ra **không cần chia sẻ object cho thread khác**: constructor của superclass gọi phương thức instance có thể được subclass override. Java vẫn **dynamic dispatch** tới implementation của subclass, dù phần khởi tạo subclass chưa chạy xong.

Tạo tệp độc lập **`OverridableConstructorDemo.java`**:

~~~java
class BaseView {
    BaseView() {
        show();
    }

    void show() {
        System.out.println("base");
    }
}

class ChildView extends BaseView {
    private String label = "READY";

    @Override
    void show() {
        System.out.println("child=" + label);
    }
}

public class OverridableConstructorDemo {
    public static void main(String[] args) {
        ChildView child = new ChildView();
        child.show();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac OverridableConstructorDemo.java
java OverridableConstructorDemo
~~~

Stdout:

~~~text
child=null
child=READY
~~~

**Tại sao?**

1. `new ChildView()` bắt đầu khởi tạo, gọi `BaseView()` như một phần của chuỗi constructor.
2. Trong constructor `BaseView()`, lời gọi `show()` là **virtual call**. Vì object thực tế là `ChildView`, implementation `ChildView.show()` được chạy.
3. Vào thời điểm đó, field initializer `label = "READY"` của lớp con **chưa chạy**, nên `label` đang có giá trị mặc định `null`.
4. Sau khi constructor superclass hoàn tất, field initializer của `ChildView` gán `"READY"`.
5. Lời gọi `child.show()` từ `main` sau đó in `child=READY`.

Đây là lỗi **đối tượng bị dùng trước khi khởi tạo hoàn chỉnh**, không nhất thiết là “escape ra một object bên ngoài”. Nhưng nó có bản chất tương tự: code đang thực thi đã dựa vào invariant của phần đối tượng chưa hoàn tất.

**Cách thiết kế tốt:** constructor chỉ gọi các thao tác an toàn trong giai đoạn khởi tạo, tránh gọi phương thức có thể override. Nếu cần helper, cân nhắc helper `private`, `static` phù hợp, hoặc phương thức `final` có trách nhiệm giới hạn ở trạng thái đã chắc chắn khởi tạo. Không nên gọi phương thức lớp con phụ thuộc field của lớp con từ constructor superclass.

## 9. `final` field không tự giải quyết `this` escape

Java Memory Model đưa ra những bảo đảm đặc biệt cho các **trường `final`** khi đối tượng được **khởi tạo đúng cách** (*properly constructed*) và tham chiếu không thoát ra trước khi constructor hoàn tất.

Ví dụ ý tưởng:

~~~java
final class Config {
    private final int port;

    Config(int port) {
        this.port = port;
    }

    int port() {
        return port;
    }
}
~~~

Đây là định nghĩa lớp minh họa, không có `main`. Khi object được khởi tạo đúng cách, ngữ nghĩa `final` có thể giúp luồng khác quan sát giá trị được thiết lập trong constructor theo những quy tắc đặc biệt, kể cả trong một số trường hợp không có đồng bộ hóa công bố đối tượng bằng cơ chế khác.

**Nhưng nếu `this` thoát ra trong constructor**, điều kiện quan trọng đó bị phá vỡ: luồng khác có thể đọc một field trước khi phép gán diễn ra, và không thể viện dẫn bảo đảm khởi tạo đúng để giả định mọi trường chắc chắn đã có giá trị cuối.

Không nên kết luận quá mức rằng `final` giải quyết tất cả publication:

- `final` không khiến toàn bộ object có thể thay đổi khác trở nên thread-safe.
- Một `final List<T>` ngăn gán lại **tham chiếu field**, không làm list mutable tự bất biến.
- Các field **không final** vẫn cần quan tâm tới đồng bộ và visibility nếu bị chia sẻ giữa các luồng.
- Một trường `final` có thể được gán tại cuối constructor, nhưng callback **chạy trước phép gán** vẫn không thể kỳ vọng đọc được giá trị đó.

**Nguyên tắc an toàn:** tránh `this` escape trước khi constructor hoàn thành **và** thiết kế đường công bố đối tượng giữa các luồng phù hợp với Java Memory Model.

## 10. Safe publication khác gì khởi tạo đầy đủ?

Đây là hai vấn đề liên quan nhưng khác nhau:

1. **Đúng trạng thái trước khi công bố:** object phải được xây dựng xong, các precondition và invariant cần thiết đã được thiết lập.
2. **Đường công bố an toàn giữa các luồng (*safe publication*):** khi một luồng truyền tham chiếu tới luồng khác, cần quan hệ visibility/happens-before thích hợp để luồng nhận thấy dữ liệu đã ghi.

Một số cơ chế thường tạo đường đồng bộ phù hợp gồm:

- Ghi tham chiếu vào một trường `volatile` và đọc lại bằng cơ chế `volatile` tương ứng.
- Đăng ký/lấy tham chiếu dưới cùng một monitor `synchronized` đúng cách.
- Sử dụng những cấu trúc concurrent có hợp đồng an toàn phù hợp như `BlockingQueue`, hoặc cơ chế thực thi tác vụ mà tài liệu quy định memory-consistency effects.
- Khởi tạo object hoàn chỉnh rồi cho thread mới sử dụng thông qua `Thread.start()`, với các hành động trước `start()` *happens-before* hành động của thread ấy.
- Dùng trạng thái static được khởi tạo an toàn qua cơ chế class initialization khi phù hợp.

Không cơ chế nào trong danh sách biến **một callback đã chạy quá sớm** thành hành vi đúng. Nếu gọi `onEvent()` ngay trước `status = "READY"`, callback vẫn quan sát trạng thái trước cập nhật, bất kể cùng luồng có khóa hay không.

Bảng đối chiếu:

| Khởi tạo hoàn tất trước khi lộ tham chiếu? | Publication giữa luồng có đồng bộ phù hợp? | Đánh giá |
| --- | --- | --- |
| Không | Không | Có rủi ro cả khởi tạo dở và visibility |
| Không | Có | Vẫn có thể quan sát object dở dang |
| Có | Không | Tránh callback sớm, nhưng chưa đủ cho mọi dữ liệu mutable/visibility đa luồng |
| Có | Có | Nền tảng tốt hơn; vẫn phải đồng bộ những thay đổi trạng thái **sau** publication nếu chia sẻ mutable state |

Các bảo đảm riêng của `final` field có những ngoại lệ và chi tiết đặc biệt; bảng này là hướng dẫn thiết kế hệ thống, không thay thế những quy tắc chặt chẽ trong JLS §17.

## 11. Static factory: tạo xong mới đăng ký

Một mẫu API rõ ràng là **constructor private + static factory**:

~~~java
final class RegisteredService {
    private final String id;

    private RegisteredService(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id không hợp lệ");
        }
        this.id = id;
    }

    static RegisteredService create(Registry registry, String id) {
        RegisteredService service = new RegisteredService(id);
        registry.add(service);
        return service;
    }

    String id() {
        return id;
    }
}
~~~

Đây là **đoạn minh họa**, chưa độc lập vì `Registry` chưa được định nghĩa. Ý chính: `new RegisteredService(id)` phải **hoàn tất** trước `registry.add(service)`.

Factory làm cho thứ tự xử lý trở nên tập trung và dễ kiểm tra hơn so với constructor đăng ký `this` ngay. Tuy nhiên, để bảo đảm an toàn **đa luồng**, `Registry` phải có quy tắc publication/visibility thích hợp; chuyển đăng ký ra factory mà sử dụng một global `ArrayList` chia sẻ không đồng bộ vẫn có thể dẫn tới data race.

### Tại sao không đơn giản đăng ký ở cuối constructor?

Ví dụ:

~~~java
Service(Registry registry) {
    this.id = "READY";
    registry.add(this);
}
~~~

Đăng ký ở **dòng cuối** thường tốt hơn đăng ký trước khi gán field, nhưng vẫn xảy ra **trước khi constructor hoàn tất** theo nghĩa chặt chẽ. Nếu registry gọi lại object đồng bộ, callback thực thi trong constructor; nếu subclass còn phải khởi tạo các trường, chúng chắc chắn có thể chưa hoàn tất. Vì vậy, với lớp có thể kế thừa hoặc hợp đồng lifecycle phức tạp, **không nên coi “dòng cuối constructor” tương đương “sau khởi tạo”**.

Factory hoặc bước activate được bên gọi thực hiện sau khi lệnh `new` hoàn tất sẽ có ranh giới lifecycle rõ ràng hơn.

## 12. Hai giai đoạn create–start: trách nhiệm của caller

Một cách khác là yêu cầu code bên ngoài tạo object rồi mới chủ động kích hoạt:

~~~java
Worker worker = new Worker(configuration);
worker.start();
~~~

Đây là **sơ đồ lời gọi**, không phải chương trình độc lập. Constructor thiết lập dữ liệu. `start()` mới đăng ký listener, bắt đầu thread hoặc kết nối tới tài nguyên bên ngoài.

Ưu điểm:

- Phân biệt đối tượng **được tạo xong** và đối tượng **đang hoạt động**.
- Cho caller cấu hình và kiểm tra trước khi có callback hay công việc nền.
- Dễ ghi tài liệu và kiểm thử riêng giai đoạn tạo/khởi động.

Nhược điểm:

- Caller có thể **quên gọi `start()`** hoặc gọi nhiều lần.
- Phải định nghĩa trạng thái như `NEW`, `RUNNING`, `CLOSED` và hành vi khi gọi sai thứ tự.
- Nếu nhiều luồng có thể gọi `start()`, cần đồng bộ việc chuyển trạng thái và đăng ký; kiểm tra một cờ boolean thông thường không tự đủ an toàn.

Nếu cần khởi tạo và đăng ký thành một API duy nhất cho caller, **factory nội bộ tạo xong rồi mới đăng ký** có thể giảm lỗi quên start. Không có một lựa chọn tốt nhất cho mọi hệ thống; điều bắt buộc là **không cho mã khác quan sát object khi invariant chưa được bảo đảm**.

## 13. Tình huống listener và framework

Rủi ro this escape đặc biệt hay xảy ra trong kiến trúc event-driven:

~~~java
class Handler {
    private String token;

    Handler(EventSource source) {
        source.addListener(this::handle);
        token = loadToken();
    }

    private void handle() {
        useToken(token);
    }
}
~~~

Đoạn này **chỉ minh họa**, vì chưa có định nghĩa `EventSource`, `loadToken` và `useToken`. Constructor công bố callback trước khi `token` được thiết lập. Framework có thể gọi listener ngay khi đăng ký hoặc từ thread khác, khiến `handle()` đọc `token == null`.

Một biến thể còn khó nhận diện hơn:

~~~java
Handler(EventSource source) {
    source.addListener(event -> this.handle(event));
    configure();
}
~~~

Lambda vẫn giữ `this`; cú pháp dài hơn không thay đổi vấn đề.

Khi tích hợp framework, nên hỏi:

1. `addListener` có thể gọi callback **ngay trong khi đăng ký** không?
2. Nó có lưu callback để một thread khác gọi không?
3. Nó có hợp đồng về **thread confinement** và memory visibility không?
4. Lúc hủy đối tượng, phải **unsubscribe** ở đâu?
5. Callback có thể chạy đồng thời với `close()` hay không?

Không nên suy đoán từ tên API rằng `addListener` chỉ lưu tham chiếu rồi sẽ không gọi ngay. Hành vi chính xác phụ thuộc tài liệu hoặc code của framework.

## 14. Có thể tránh escape chỉ bằng cách dùng `private` hay `synchronized`?

**Không.** Các modifier có ý nghĩa riêng:

| Biện pháp | Có giúp gì? | Có tự sửa this escape? |
| --- | --- | --- |
| `private field` | Ngăn mã ngoài truy cập trực tiếp field | Không: callback trong class vẫn có thể đọc field sớm |
| `final field` | Hạn chế gán lại, có ngữ nghĩa visibility đặc biệt khi khởi tạo đúng | Không: không bảo vệ callback chạy trước khi gán |
| `synchronized` | Hỗ trợ mutual exclusion/visibility khi cùng dùng monitor đúng cách | Không: một callback đồng bộ quá sớm vẫn thấy state chưa xong |
| `volatile` | Tạo các quan hệ visibility/ordering theo JMM cho truy cập volatile | Không: không biến giá trị chưa gán thành giá trị đã gán |
| `Thread.sleep(...)` | Thay đổi thời điểm lịch chạy theo cách không bảo đảm | Không; không phải cơ chế đồng bộ tin cậy |
| Factory tạo xong rồi mới đăng ký | Tránh công bố object trước lúc ctor kết thúc | Có ích trực tiếp, nhưng phải bảo đảm publication đa luồng |
| Không gọi overridable method trong ctor | Tránh dynamic dispatch sớm tới subclass | Có ích cho rủi ro dùng field lớp con chưa khởi tạo |

Một lỗi thiết kế khác là gắn `synchronized` lên constructor: trong Java không có cú pháp khai báo **`synchronized` constructor** như với method. Việc constructor tự đi vào một khối `synchronized` cũng không giải quyết mọi đường callback sớm.

## 15. Kiểm thử và phát hiện this escape

Một số lỗi có thể kiểm thử **deterministic**, như `ThisEscapeDemo`: event bus gọi callback ngay khi constructor chưa gán xong. Với lỗi race khi start thread trong constructor, một lần chạy “đúng” không chứng minh code an toàn.

Các phép kiểm tra hữu ích:

- **Mô phỏng callback tức thì:** stub/mock registry gọi listener ngay lúc đăng ký, rồi kiểm tra object không xuất hiện trạng thái chưa hợp lệ.
- **Mô phỏng concurrent activation:** dùng `CountDownLatch` hoặc `Phaser` để điều phối thread trong bài kiểm thử; tránh phụ thuộc `Thread.sleep` để tạo race. Nếu muốn chứng minh một race cụ thể, thiết kế các mốc đồng bộ rõ ràng.
- **Đọc lại invariant sau factory:** khi factory trả về, xác nhận mọi trường bắt buộc đã hợp lệ.
- **Rà soát constructor:** tìm `this` được gán vào registry/static field, callback, thread, executor, hoặc được truyền vào API bên ngoài.
- **Rà soát method overridable:** tìm constructor gọi `init()`, `notifyListeners()`, `toString()`, `hashCode()` hoặc method instance khác có thể override và phụ thuộc trạng thái lớp con.
- **Kiểm tra JMM:** với object được chuyển giữa thread, xác định mối quan hệ *happens-before* và cơ chế bảo vệ mutable state.

**Ghi chú:** mã xử lý lỗi theo timing có thể vượt qua hàng triệu lần test mà vẫn sai. Static analysis, code review và thiết kế lifecycle rõ ràng thường quan trọng hơn việc chỉ cố tái hiện lỗi bằng chạy lặp.

### Ví dụ về test hợp đồng thay vì test lịch chạy

Với factory `SafeSubscriber.create(bus, "READY")`, điều cần kiểm chứng là callback, kể cả khi bus kích hoạt ngay sau đăng ký, **không bao giờ quan sát trạng thái chưa gán trong con đường được định nghĩa**. Với constructor đăng ký listener, một giả lập registry cho callback trong lúc đăng ký sẽ phát hiện lỗi tức thì.

Nên kiểm tra cả hành vi **thất bại**: nếu constructor ném ngoại lệ, registry không được giữ một listener trỏ tới object khởi tạo dở. Factory dễ giúp duy trì quy tắc này vì đăng ký chỉ được thực hiện **sau khi `new` kết thúc bình thường**.

## 16. Quy trình review constructor từng bước

Khi đánh giá một constructor mới, hãy thực hiện:

1. **Liệt kê invariant:** các trường nào phải không null, các số nào phải trong miền hợp lệ, tài nguyên nào phải sẵn sàng?
2. **Xác định thời điểm hoàn tất:** các field initializer, constructor lớp cha/con và phần thân constructor đã thực sự hoàn tất chưa?
3. **Tìm đường công bố receiver:** `this`, method reference `this::m`, lambda bắt giữ field hoặc gọi instance method, listener, thread, static registry.
4. **Kiểm tra callback đồng bộ:** API được gọi có thể lập tức chạy lại phương thức trên object không?
5. **Kiểm tra thread mới:** có bất kỳ tác vụ nào chạy trước các phép gán field cuối cùng không? Đã có *happens-before* thích hợp chưa?
6. **Tránh virtual call trong constructor:** đặc biệt với lớp có thể kế thừa và override.
7. **Tách activation khỏi construction:** chuyển đăng ký/start vào factory hoặc method được gọi sau constructor.
8. **Bảo đảm safe publication:** nếu object chia sẻ nhiều luồng, dùng cơ chế đồng bộ phù hợp lúc bàn giao.
9. **Duy trì bảo vệ sau khởi tạo:** publication tốt không thay thế đồng bộ cho những field mutable tiếp tục được sửa.
10. **Tạo kiểm thử ác ý:** callback tức thì, dữ liệu biên, ngoại lệ constructor, start đồng thời, lifecycle stop/start.

Trong nhiều trường hợp, quy trình này phát hiện được rủi ro ngay từ việc **đọc thứ tự dòng**, trước khi chương trình được chạy.

## 17. Sai lầm thường gặp

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “`this` chỉ thoát khi viết `register(this)`” | Lambda hoặc `this::method` cũng có thể giữ receiver | Rà soát cả callback, anonymous class và method reference |
| “Chạy trên một thread thì an toàn” | Callback đồng bộ có thể chạy giữa constructor | Không công bố object trước khi state sẵn sàng |
| “Thread thường chạy chậm hơn constructor” | Không có thứ tự thực thi được bảo đảm như vậy | Bắt đầu task sau constructor; dùng JMM đúng |
| “Gán trường `final` là đủ” | Có thể đọc trước khi gán; escape làm mất điều kiện proper construction | Tránh escape và thiết kế publication an toàn |
| “`synchronized` sẽ sửa mọi lỗi” | Không ngăn callback gọi sớm, monitor reentrant | Điều chỉnh lifecycle và thứ tự công bố |
| “Đăng ký ở dòng cuối constructor là hoàn toàn an toàn” | Object chưa rời constructor; subclass có thể chưa khởi tạo | Đăng ký sau `new` thành công |
| “Constructor lớp cha có thể thoải mái gọi method override” | Override của lớp con chạy khi field con còn mặc định | Không gọi overridable method trong ctor |
| “Không tái hiện race tức là không có race” | Scheduling không xác định và visibility có thể che lỗi | Review, test có điều phối và xác định happens-before |
| “Một static factory tự làm mọi thứ thread-safe” | Registry chia sẻ không đồng bộ vẫn có data race | Factory + cơ chế publication phù hợp |
| “Object có `private` fields thì không thể bị quan sát sớm” | Public callback của chính object có thể đọc và lộ các giá trị | Không đưa receiver tới bên ngoài quá sớm |

## 18. Bài tập tự luyện

**Bài 1.** Trong constructor `Listener(EventBus bus)`, code gọi `bus.register(this::onEvent)` rồi mới gán `token = "OK"`. Nếu bus gọi callback ngay, `onEvent` có thể nhìn thấy giá trị nào? Vì sao?

**Bài 2.** Lời gọi `this.name = name;` trong constructor có phải this escape không? Còn `registry.put(id, this)` thì sao?

**Bài 3.** Vì sao `new Thread(() -> System.out.println(value)).start(); value = 42;` trong constructor không bảo đảm thread mới in 42?

**Bài 4.** Một factory tạo `new Service(settings)` rồi `registry.add(service)`. Nó khắc phục rủi ro nào? Khi registry được sử dụng giữa nhiều thread, cần quan tâm thêm điều gì?

**Bài 5.** Superclass constructor gọi `render()`, subclass override `render()` và đọc field initializer `String label = "READY"`. Tại sao có thể thấy `null`?

**Bài 6.** Với class có nhiều field `final`, có thể suy ra an toàn hoàn toàn nếu constructor đã lộ `this` cho một thread khác từ đầu không? Giải thích.

**Bài 7.** Cho một event bus có thể gọi listener tức thì trong `register`. Hãy đề xuất thiết kế để listener được đăng ký khi object đã hoàn chỉnh mà caller vẫn chỉ gọi một API tạo object.

**Bài 8.** Nếu constructor đã hoàn thành rồi nhưng hai thread cập nhật cùng một `ArrayList` bên trong object không đồng bộ, việc tránh this escape có tự giải quyết lỗi không?

### Đáp án tham khảo

1. Có thể đọc `null` vì field chưa được gán, dù callback chạy cùng thread với constructor; đây là lỗi về **thứ tự khởi tạo**.
2. `this.name = name;` chỉ gán field, không công bố receiver. Đưa `this` vào registry có thể làm object truy cập được từ bên ngoài nên là rủi ro escape.
3. `Thread.start()` không bảo đảm phép gán **sau** lời gọi start xảy ra trước thao tác của thread mới; ngoài ra có thể thiếu visibility phù hợp.
4. Đăng ký xảy ra sau constructor, tránh công bố object khởi tạo dở; registry cần **safe publication/synchronization** thích hợp khi các thread chia sẻ nó.
5. Dynamic dispatch chọn override ở subclass khi superclass constructor đang chạy, trước field initializer của subclass; trường vẫn có giá trị mặc định `null`.
6. Không. Bảo đảm đặc biệt của `final` dựa trên proper construction; công bố sớm phá điều kiện cần để dựa vào bảo đảm ấy.
7. Dùng **constructor private + static factory**: tạo và xác thực object xong, rồi register callback, rồi trả instance; đảm bảo registry dùng đồng bộ phù hợp.
8. Không. Tránh escape chỉ giải quyết lỗi công bố sớm; mutable state vẫn cần thiết kế đồng thời riêng.

## 19. Tài liệu đối chiếu

- [Java Language Specification 17, §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): thứ tự và ngữ nghĩa khởi tạo đối tượng.
- [Java Language Specification 17, §15.8.3 — `this`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.3): ngữ nghĩa biểu thức `this`.
- [Java Language Specification 17, §17.4.5 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5): quan hệ happens-before của Java Memory Model.
- [Java Language Specification 17, §17.5 — `final` Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): bảo đảm đặc biệt với trường final và điều kiện khởi tạo đúng.
- [Oracle Java SE 17 API — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start`, `join` và vòng đời thread.

**Ghi nhớ:** `this` escape nguy hiểm khi **object đang khởi tạo đã bị công bố cho mã khác**, đặc biệt qua listener, callback, thread hoặc registry. Cách phòng ngừa quan trọng nhất là **hoàn tất constructor và invariant trước khi đăng ký/bắt đầu hoạt động**, tránh gọi method có thể override trong constructor, và bảo đảm *safe publication* nếu các thread cùng sử dụng object. `final`, `volatile` hay `synchronized` không thể thay thế cho đúng thứ tự lifecycle.
