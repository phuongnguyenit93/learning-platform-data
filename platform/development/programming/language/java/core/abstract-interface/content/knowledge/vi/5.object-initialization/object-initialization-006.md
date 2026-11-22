# Tránh để this thoát ra khi đối tượng chưa khởi tạo xong trong Java

**This escape** xảy ra khi tham chiếu đến đối tượng đang xây dựng được đưa cho mã khác trước khi quá trình khởi tạo hoàn tất. Mã nhận tham chiếu có thể gọi phương thức hoặc đọc trường khi đối tượng còn ở trạng thái trung gian.

Đây là lỗi khác với việc một constructor gọi phương thức override: hai rủi ro có thể cùng xuất hiện, nhưng **gọi override sớm không tự động chứng minh rằng this đã thoát ra ngoài**. Bài này tập trung vào callback, listener, registry, thread/task và bảo đảm an toàn khi công bố đối tượng giữa các luồng.

## 1. Thời điểm khởi tạo có ý nghĩa gì?

Khi cấp phát một đối tượng, các trường instance ban đầu có giá trị mặc định: tham chiếu là null, số là 0, boolean là false. Sau đó chạy chuỗi constructor và initializer theo quy tắc Java. Một trường final cũng chỉ nhận giá trị được gán khi phép gán tương ứng thực thi.

~~~java
final class Settings {
    private final String endpoint;
    private int retryCount = 3;

    Settings(String endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

Trước khi dòng gán endpoint chạy, trường đó vẫn có giá trị mặc định null. Constructor có nhiệm vụ kiểm tra dữ liệu và đưa đối tượng đến trạng thái hợp lệ **trước khi cho mã bên ngoài sử dụng nó**.

## 2. Những đường thoát phổ biến

| Mẫu trong constructor | Vì sao cần kiểm tra |
| --- | --- |
| `registry.register(this)` | Registry có thể giữ tham chiếu hoặc gọi đối tượng ngay. |
| `eventBus.subscribe(this::onEvent)` | Method reference giữ receiver là this; callback có thể chạy trước khi các trường sẵn sàng. |
| `eventBus.subscribe(e -> this.handle(e))` | Lambda cũng có thể đóng trên this. |
| `new Thread(this::run).start()` | Luồng mới có thể đọc trạng thái khi constructor chưa xong. |
| `executor.execute(this::run)` | Executor có thể thực thi ngay hoặc chuyển việc sang luồng khác. |
| Gán this vào biến static hoặc collection dùng chung | Mã ngoài có thể tìm thấy đối tượng chưa hoàn chỉnh. |
| Truyền this cho dependency khác | Dependency có thể lưu tham chiếu hoặc kích hoạt callback. |

Không phải mọi lần viết this trong constructor đều là escape. `this.endpoint = endpoint` hoặc một helper private chỉ xử lý trường cục bộ, không công bố tham chiếu, là các thao tác bình thường. Ngược lại, lambda không viết chữ this vẫn có thể giữ tham chiếu nếu nó gọi phương thức hoặc đọc trường instance.

## 3. Ví dụ chạy được: callback nhìn thấy trạng thái chưa hoàn tất

Lưu vào **EscapeDemo.java**:

~~~java
import java.util.Objects;
import java.util.function.Consumer;

public class EscapeDemo {
    static final class CallbackBus {
        private Consumer<String> listener;

        void subscribe(Consumer<String> callback) {
            listener = Objects.requireNonNull(callback);
            listener.accept("subscribed");
        }
    }

    static final class UnsafeObserver {
        private String label;

        UnsafeObserver(CallbackBus bus) {
            bus.subscribe(this::onMessage);
            label = "ready";
        }

        private void onMessage(String event) {
            System.out.println(
                    "unsafe: label=" + label + ", event=" + event);
        }
    }

    static final class SafeObserver {
        private final String label;

        private SafeObserver(String label) {
            this.label = Objects.requireNonNull(label);
        }

        static SafeObserver create(CallbackBus bus, String label) {
            Objects.requireNonNull(bus);
            SafeObserver ready = new SafeObserver(label);
            bus.subscribe(ready::onMessage);
            return ready;
        }

        private void onMessage(String event) {
            System.out.println(
                    "safe: label=" + label + ", event=" + event);
        }
    }

    static class Base {
        Base() {
            System.out.println("override: " + describe());
        }

        String describe() {
            return "base";
        }
    }

    static final class Derived extends Base {
        private final String detail;

        Derived() {
            detail = "ready";
        }

        @Override
        String describe() {
            return detail;
        }
    }

    public static void main(String[] args) {
        new UnsafeObserver(new CallbackBus());
        SafeObserver.create(new CallbackBus(), "ready");
        new Derived();
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 EscapeDemo.java
java EscapeDemo
~~~

Kết quả xác định:

~~~text
unsafe: label=null, event=subscribed
safe: label=ready, event=subscribed
override: null
~~~

- **unsafe:** constructor đăng ký callback giữ tham chiếu đến đối tượng. CallbackBus gọi callback đồng bộ ngay trong subscribe, trước khi label = "ready" chạy, nên callback đọc null.
- **safe:** factory hoàn tất constructor SafeObserver rồi mới đăng ký callback. Callback gọi ngay vẫn thấy label đã sẵn sàng.
- **override:** Base() gọi describe(), Java dispatch đến Derived.describe() trước khi trường detail được gán. Đây là nguy cơ gọi override trong constructor; đoạn này không cho thấy tham chiếu đã được công bố ra registry hay luồng khác, nên cần phân biệt với this escape.

CallbackBus chỉ mô phỏng callback đồng bộ, không phải event bus đa luồng. Đầu ra xác định vì listener được gọi ngay trong subscribe.

## 4. Khác biệt giữa this escape và gọi override sớm

Gọi phương thức overridable từ constructor có thể chạy logic của lớp con khi trường lớp con còn mặc định. This escape xảy ra khi tham chiếu được đưa ra khỏi quá trình khởi tạo và mã khác có thể giữ hoặc dùng nó. Một tình huống có thể bao gồm cả hai, nhưng cần xác định đường đi thực tế.

Ví dụ, `System.out.println(this)` hoặc nối chuỗi với this có thể gọi toString() đã bị override; đây là lời gọi phương thức đáng kiểm tra. Để khẳng định escape, hãy xem đối tượng có được đưa cho logger/formatter hay dependency ngoài có thể giữ hoặc sử dụng nó hay không. Cách sửa cốt lõi là tránh hook đa hình sớm và tránh công bố tham chiếu trước khi invariant sẵn sàng.

## 5. Không khởi chạy thread hoặc task từ constructor

Đoạn sau minh họa một thiết kế nguy hiểm:

~~~java
final class UnsafeWorker {
    private String configuration;

    UnsafeWorker(java.util.concurrent.Executor executor) {
        executor.execute(() -> process(configuration));
        configuration = "loaded";
    }

    private void process(String value) {
        System.out.println("configuration=" + value);
    }
}
~~~

Nếu executor chạy tác vụ đồng bộ như direct executor, process nhận null chắc chắn. Với thread pool, kết quả còn phụ thuộc lịch thực thi và cơ chế đồng bộ; không được dựa vào giả định “task chắc chạy sau constructor”. Không dùng Thread.sleep để che vấn đề, vì chờ một khoảng thời gian không tạo ra invariant hoặc quan hệ happens-before đúng.

## 6. Cách an toàn: tạo xong rồi mới start

Lưu chương trình sau vào **SafeThreadDemo.java**:

~~~java
import java.util.Objects;

public class SafeThreadDemo {
    static final class Worker {
        private final String configuration;

        private Worker(String configuration) {
            this.configuration =
                    Objects.requireNonNull(configuration, "configuration");
        }

        static Thread start(String configuration) {
            Worker ready = new Worker(configuration);
            Thread thread = new Thread(ready::runJob, "worker");
            thread.start();
            return thread;
        }

        private void runJob() {
            System.out.println("Worker config=" + configuration);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Thread worker = Worker.start("loaded");
        worker.join();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SafeThreadDemo.java
java SafeThreadDemo
~~~

Stdout:

~~~text
Worker config=loaded
~~~

Factory chỉ gọi Thread.start() sau khi constructor Worker hoàn tất. Theo Java Memory Model, hành động của luồng tạo trước Thread.start() happens-before hành động của luồng mới. Thread.join() cũng giúp main đợi worker kết thúc. Điều này bảo đảm trạng thái được gán trước start có thể được nhìn thấy theo hợp đồng của start; nó **không** khiến mọi thao tác mutable về sau tự thread-safe.

Mẫu tương tự áp dụng cho listener: tạo đối tượng xong, sau đó mới đăng ký callback. Nếu đăng ký thất bại, xác định cách xử lý lỗi và dọn tài nguyên; nếu listener giữ tham chiếu lâu dài, cung cấp cách unregister khi đối tượng dừng hoạt động.

## 7. final field, safe publication và giới hạn của chúng

Java có các bảo đảm đặc biệt cho final field khi đối tượng được xây dựng đúng cách và this không thoát ra trong lúc xây dựng. Tuy nhiên, các bảo đảm này không sửa được callback đọc trường trước khi phép gán xảy ra, và cũng không biến mọi trạng thái mutable thành thread-safe.

| Nhận định | Đánh giá |
| --- | --- |
| final String name luôn có giá trị cuối cùng ở mọi thời điểm constructor | Sai: trước phép gán, lời gọi sớm vẫn có thể thấy giá trị mặc định. |
| final khiến publish this từ constructor luôn an toàn | Sai: tránh escape sớm vẫn là điều kiện quan trọng. |
| final List&lt;String&gt; làm nội dung list bất biến | Sai: final ngăn gán lại tham chiếu, không tự ngăn sửa list. |
| volatile trên một trường làm cả đối tượng thread-safe | Sai: invariant nhiều trường và thao tác cần thiết kế đồng bộ phù hợp. |
| Xây xong rồi publish qua Thread.start(), lock hoặc cơ chế đồng bộ thích hợp | Cung cấp quan hệ visibility theo hợp đồng của cơ chế đó. |

Safe publication là đưa tham chiếu đã khởi tạo hoàn chỉnh sang mã khác qua cơ chế có bảo đảm visibility, chẳng hạn Thread.start(), khóa dùng nhất quán, volatile reference hoặc concurrent collection phù hợp. Sau khi publish, các truy cập mutable về sau vẫn phải được đồng bộ nếu nhiều luồng cùng sử dụng.

## 8. Callback, lambda và vòng đời đối tượng

Các biểu thức `this::onMessage` và `event -> onMessage(event)` có thể giữ receiver là đối tượng hiện tại. Lambda chỉ dùng biến cục bộ độc lập thì không nhất thiết capture this, nhưng dependency mà lambda gọi vẫn có thể có vấn đề vòng đời hoặc đồng bộ.

Với đối tượng cần đăng ký listener, mở socket hoặc khởi động tác vụ, có thể tách hai pha:

~~~text
constructor
   ↓
gán trường và kiểm tra invariant
   ↓
constructor hoàn tất
   ↓
register / start / publish
   ↓
active
   ↓
unregister / stop / close
~~~

Static factory có thể tập trung thứ tự này để caller không quên bước khởi chạy. Chỉ dùng mô hình start/stop khi đối tượng thực sự có vòng đời cần quản lý; không cần ép mọi đối tượng dữ liệu vào mô hình đó.

## 9. Checklist review và bài tập

Khi review constructor, hãy lần lượt hỏi:

1. Trạng thái nào phải đúng khi đối tượng sẵn sàng?
2. Có truyền this, this::method, lambda instance, listener hoặc đối tượng vào registry không?
3. Dependency có thể gọi callback đồng bộ ngay lúc đăng ký không?
4. Có thread/task nào bắt đầu trước khi constructor hoàn tất không?
5. Nếu có nhiều luồng, cơ chế nào cung cấp happens-before và bảo vệ các cập nhật sau đó?
6. Test có thể buộc callback chạy ngay để tái hiện lỗi một cách xác định không?
7. Có cần unregister hoặc dọn tài nguyên khi đối tượng dừng không?

**Tình huống A.** Constructor đăng ký `eventBus.register(this::onEvent)` trước khi gán handler, còn event bus gọi callback đồng bộ. Kết luận: callback có thể đọc handler null; chuyển đăng ký sang sau khi constructor hoàn tất.

**Tình huống B.** Constructor lớp cha gọi toString() bị lớp con override. Kết luận: có nguy cơ gọi override sớm; để kết luận this escape, cần xem tham chiếu có được đưa cho mã ngoài giữ hoặc sử dụng không.

**Tình huống C.** Factory tạo Worker, rồi mới gọi Thread.start(). Kết luận: các hành động trước start happens-before hành động trong luồng mới; điều đó không thay thế đồng bộ cho những thay đổi sau này.

**Ghi nhớ:** constructor chuẩn bị trạng thái; callback, listener, registry và thread/task chỉ nên nhận đối tượng sau khi toàn bộ constructor hoàn tất. Với nhiều luồng, đi cùng safe publication và cơ chế đồng bộ đúng cho các cập nhật về sau.