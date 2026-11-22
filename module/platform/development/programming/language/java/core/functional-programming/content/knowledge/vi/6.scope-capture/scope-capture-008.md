# Rủi ro bắt giữ đối tượng lớn hoặc trạng thái có thể thay đổi trong Java

Khi viết lambda, method reference hoặc callback trong Java, **biến được bắt giữ (captured)** có thể kéo dài vòng đời của một đối tượng, hoặc khiến nhiều đoạn mã cùng quan sát và thay đổi một trạng thái. Hai vấn đề thường bị nhầm với nhau là **giữ tham chiếu quá lâu gây áp lực bộ nhớ** và **chia sẻ trạng thái mutable gây kết quả sai hoặc lỗi đồng thời**.

Bài này tập trung vào các rủi ro đó, cách nhận biết qua ví dụ Java 17+, và cách thiết kế closure an toàn trong stream, listener, tác vụ bất đồng bộ và các API nhận hàm.

## 1. Java thực sự bắt giữ điều gì?

Lambda có thể sử dụng biến cục bộ thuộc phạm vi bao quanh nếu biến đó là `final` hoặc **effectively final** (chỉ được gán một lần). Ràng buộc này áp dụng cho **biến/tham chiếu cục bộ**, không buộc đối tượng mà biến trỏ tới phải bất biến.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

class CaptureBasics {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("An");

        Supplier<Integer> count = () -> names.size();
        names.add("Bình"); // Được phép: thay đổi nội dung đối tượng.
        System.out.println(count.get()); // 2
    }
}
~~~

Chạy bằng `javac CaptureBasics.java` và `java CaptureBasics`. Kết quả:

~~~text
2
~~~

Trong ví dụ này, tham chiếu cục bộ `names` không bị gán lại nên hợp lệ cho lambda, nhưng danh sách vẫn thay đổi. Nếu cố viết `names = new ArrayList<>();` sau khi tạo lambda, mã không biên dịch vì `names` không còn effectively final.

Cần phân biệt ba kiểu dữ liệu khi bắt giữ:

- **Primitive cục bộ**: lambda dùng giá trị của biến tại thời điểm tạo closure; không có đối tượng mutable nằm sau giá trị primitive đó.
- **Tham chiếu cục bộ**: lambda giữ giá trị tham chiếu tới cùng đối tượng; thao tác trên đối tượng đó vẫn có thể xuất hiện khi lambda được chạy.
- **Trường của đối tượng / `this`**: lambda hoặc method reference gắn với instance có thể giữ instance nhận lời gọi, và theo đó giữ các trường lớn nằm trong instance.

Chi tiết cách JVM biểu diễn một lambda là đặc điểm triển khai; khi thiết kế, hãy dựa trên **khả năng truy cập đối tượng và vòng đời tham chiếu**, không dựa trên giả định rằng mọi lambda luôn tạo một class hay một allocation mới.

## 2. Rủi ro giữ đối tượng lớn trong bộ nhớ

Một đối tượng có thể được garbage collector thu hồi khi nó không còn reachable từ các gốc truy cập (GC roots), theo ngữ nghĩa và tối ưu hóa của JVM. Nếu callback còn được một nơi sống lâu giữ, các đối tượng callback cần để thực thi cũng có thể tiếp tục reachable. Ví dụ:

~~~text
GC root
  → singleton / event bus / executor / cache
  → callback (lambda hoặc method reference)
  → đối tượng bị bắt giữ
  → byte[], danh sách, cache, đồ thị đối tượng...
~~~

Đây là **retention**: không nhất thiết là lỗi cấp phát, nhưng bộ nhớ tiếp tục bị giữ lâu hơn nhu cầu nghiệp vụ. Một callback nhỏ về kích thước có thể giữ cả một đồ thị đối tượng lớn. Nếu chủ thể đăng ký không xóa callback khi kết thúc vòng đời, retention có thể trở thành memory leak.

Các tình huống phổ biến:

- Lambda chứa trong `static` collection, cache, singleton hoặc biến cấu hình sống suốt ứng dụng.
- Event listener, subscription hoặc callback được đăng ký mà không được hủy.
- Tác vụ trì hoãn trong hàng đợi hoặc `ScheduledExecutorService` giữ payload trong thời gian chờ; tác vụ lặp lại có thể được giữ rất lâu.
- Callback dùng `this`, `this::handle` hoặc đọc một trường instance, vô tình kéo theo toàn bộ instance và những dữ liệu mà nó tham chiếu.
- Closure trả về từ một phương thức giữ một object phục vụ tạm thời, dù phương thức đã kết thúc.
- Bộ nhớ ngoài heap hoặc tài nguyên như file/socket có vòng đời riêng: một callback giữ wrapper có thể trì hoãn giải phóng, nhưng **GC không thay thế việc `close()` tài nguyên**.

### Ví dụ 1: Giữ cả mảng lớn khi chỉ cần một giá trị

Tạo file `LargeCaptureDemo.java`:

~~~java
public class LargeCaptureDemo {
    static Runnable captureLargeArray() {
        byte[] payload = new byte[8 * 1024 * 1024];
        payload[0] = 7;
        return () -> System.out.println("value=" + payload[0]);
    }

    static Runnable captureOnlyNeededValue() {
        byte[] payload = new byte[8 * 1024 * 1024];
        payload[0] = 7;
        int firstByte = payload[0];
        return () -> System.out.println("value=" + firstByte);
    }

    public static void main(String[] args) {
        Runnable keepsArray = captureLargeArray();
        Runnable keepsValue = captureOnlyNeededValue();
        keepsArray.run();
        keepsValue.run();
    }
}
~~~

~~~bash
javac LargeCaptureDemo.java
java LargeCaptureDemo
~~~

Kết quả:

~~~text
value=7
value=7
~~~

Hai callback có cùng hành vi nhìn thấy được, nhưng nhu cầu bắt giữ khác nhau. `keepsArray` cần truy cập `payload[0]` khi thực thi nên có thể giữ tham chiếu đến mảng khoảng 8 MiB; `keepsValue` chỉ cần `int firstByte`, không cần giữ mảng ban đầu. Ví dụ **minh họa quan hệ tham chiếu**, không đo hay bảo đảm một thời điểm GC cụ thể: JIT có thể tối ưu hóa khác nhau, và việc một biến hết scope không đồng nghĩa bộ nhớ được thu hồi ngay.

**Nguyên tắc:** tính toán hoặc trích xuất giá trị nhỏ, độc lập trước khi tạo callback, rồi chỉ bắt giữ giá trị đó. Nếu cần toàn bộ dữ liệu, hãy đặt vòng đời callback ngắn, có cơ chế hủy, và cân nhắc truyền dữ liệu tại thời điểm gọi thay vì lưu sẵn trong closure.

## 3. `final` không làm cho trạng thái đối tượng bất biến

Rủi ro thứ hai không đòi hỏi nhiều bộ nhớ. Một lambda giữ tham chiếu tới `List`, `Map`, đối tượng nghiệp vụ hoặc một đối tượng `AtomicInteger`; dữ liệu có thể thay đổi giữa lúc tạo lambda và lúc chạy lambda.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public class MutableCaptureDemo {
    static Supplier<String> liveView(List<String> values) {
        return () -> String.join(", ", values);
    }

    static Supplier<String> snapshotView(List<String> values) {
        List<String> snapshot = List.copyOf(values);
        return () -> String.join(", ", snapshot);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("An", "Bình"));
        Supplier<String> live = liveView(names);
        Supplier<String> frozen = snapshotView(names);

        names.add("Chi");
        System.out.println("live=" + live.get());
        System.out.println("snapshot=" + frozen.get());
    }
}
~~~

~~~bash
javac MutableCaptureDemo.java
java MutableCaptureDemo
~~~

Kết quả xác định (các thao tác diễn ra tuần tự trên một thread):

~~~text
live=An, Bình, Chi
snapshot=An, Bình
~~~

`liveView` cố ý quan sát **trạng thái hiện tại**; `snapshotView` cố ý giữ **ảnh chụp tại lúc tạo**. Cả hai đều hợp lệ khi đúng yêu cầu nghiệp vụ. Sai lầm xuất hiện khi mong chờ snapshot nhưng lại giữ tham chiếu tới đối tượng có thể thay đổi.

Lưu ý:

- `List.copyOf(values)` cho một danh sách không sửa được qua API của danh sách và độc lập với việc thêm/xóa phần tử trong danh sách nguồn. Phép sao chép này **nông (shallow)**: nếu phần tử là đối tượng mutable thì dữ liệu bên trong phần tử vẫn có thể thay đổi.
- `Collections.unmodifiableList(values)` chỉ tạo một **view không cho sửa qua view**; nếu nguồn `values` thay đổi, view vẫn phản ánh thay đổi đó. Nó không phải snapshot độc lập.
- `final List<Order> orders` không biến `Order` hoặc các phần tử bên trong thành immutable.
- `AtomicInteger` giúp thực hiện những phép cập nhật nguyên tử nhất định, nhưng bản thân nó vẫn là trạng thái mutable; không làm toàn bộ thao tác nghiệp vụ trở thành atomic.

Nếu cần snapshot thật sự ổn định, dùng DTO/record immutable, sao chép các trường cần thiết (kể cả thành phần lồng nhau có thể thay đổi), hoặc xây dựng một biểu diễn giá trị bất biến rõ ràng.

## 4. Shared mutable state và lỗi đồng thời

Khi callback chạy trên thread khác, sự thay đổi dữ liệu có thể dẫn đến hai nhóm lỗi:

1. **Race condition / lost update:** hai tác vụ cùng đọc, tính và ghi một biến; một cập nhật ghi đè cập nhật khác.
2. **Visibility / ordering:** khi không có quan hệ happens-before thích hợp, một thread không có bảo đảm quan sát cập nhật của thread khác vào thời điểm mong muốn.

~~~java
// Đoạn minh họa LỖI; không phải một chương trình Java độc lập.
int[] total = {0};
Runnable unsafe = () -> total[0]++; // Đọc rồi ghi: không atomic.
// Chạy unsafe đồng thời trên nhiều thread có thể bị mất lượt tăng.
~~~

Mảng `total` được lambda bắt giữ hợp lệ vì tham chiếu không bị gán lại; điều này **không làm `total[0]++` an toàn**. Ngay cả `volatile int` cũng không biến phép tăng `x++` thành nguyên tử, bởi đây là chuỗi đọc–tính–ghi.

Ví dụ đúng cho nhu cầu đếm độc lập, dùng `AtomicInteger` và chờ các tác vụ hoàn tất. Tạo file `ConcurrentCounterDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ConcurrentCounterDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger counter = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            Future<?>[] tasks = new Future<?>[1_000];
            for (int i = 0; i < tasks.length; i++) {
                tasks[i] = pool.submit(() -> {
                    counter.incrementAndGet();
                });
            }
            for (Future<?> task : tasks) {
                task.get();
            }
            System.out.println("count=" + counter.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac ConcurrentCounterDemo.java
java ConcurrentCounterDemo
~~~

Kết quả:

~~~text
count=1000
~~~

`incrementAndGet()` thực hiện cập nhật nguyên tử; `Future.get()` đợi tác vụ tương ứng hoàn tất và thiết lập quan hệ happens-before cần thiết đối với các hành động trong tác vụ. `shutdown()` ngăn nhận thêm tác vụ mới; ví dụ đã chờ đủ tất cả `Future` trước khi in kết quả.

Chọn giải pháp theo mục tiêu:

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Mỗi task chỉ cần một giá trị tại lúc submit | Tạo biến local snapshot riêng cho mỗi lần submit. |
| Các task chỉ cần đọc dữ liệu không đổi | Chia sẻ immutable value/DTO hoặc snapshot độc lập. |
| Đếm/tăng một biến dùng chung | `AtomicInteger`, `AtomicLong`, hoặc `LongAdder` theo nhu cầu. |
| Nhiều trường phải thay đổi nhất quán | Khóa (`synchronized`/`Lock`) hoặc cô lập trạng thái trong một owner/thread. |
| Thu thập kết quả từ parallel stream | Ưu tiên `collect`/reduction thay vì side effect lên `ArrayList` dùng chung. |
| Cần chuyển trạng thái giữa thread | Dùng công cụ đồng bộ hóa phù hợp như `Future`, queue thread-safe, lock hoặc `volatile` cho trường hợp chỉ cần visibility. |

Tránh giả định rằng closure sẽ chạy ngay, chạy đúng một lần hoặc luôn trên thread gọi. Chính API nhận callback mới quy định lịch thực thi, bảo đảm đồng bộ và chính sách hủy.

## 5. Vì sao listener và callback dài hạn dễ gây retention?

Xét một thành phần UI, service, bộ xử lý sự kiện hoặc đối tượng mô phỏng `EventBus`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListenerLifecycleDemo {
    static final class EventBus {
        private final List<Runnable> listeners = new ArrayList<>();

        AutoCloseable register(Runnable listener) {
            listeners.add(listener);
            return () -> {
                listeners.remove(listener);
            };
        }

        void fire() {
            for (Runnable listener : List.copyOf(listeners)) {
                listener.run();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        EventBus bus = new EventBus();
        byte[] large = new byte[4 * 1024 * 1024];
        large[0] = 9;

        try (AutoCloseable registration =
                 bus.register(() -> System.out.println("event=" + large[0]))) {
            bus.fire();
        } // close() gỡ listener khỏi bus.
    }
}
~~~

~~~bash
javac ListenerLifecycleDemo.java
java ListenerLifecycleDemo
~~~

Kết quả:

~~~text
event=9
~~~

Khi listener còn trong `bus.listeners`, callback cần truy cập `large` và vì vậy có thể giữ mảng lớn reachable. Khối `try` tạo điểm kết thúc rõ ràng cho registration, giúp tránh giữ listener vô hạn. Với framework thực tế, cơ chế tương ứng có thể là `removeListener`, `dispose`, `unsubscribe`, `cancel` hoặc `close`.

Không nên suy luận rằng **hủy tác vụ** luôn đồng nghĩa loại bỏ ngay mọi tham chiếu: một future, queue, timer hoặc callback đang chạy có thể còn giữ đối tượng cho đến khi vòng đời thực tế kết thúc. Kiểm tra tài liệu API và trạng thái sau khi hủy.

Đặc biệt chú ý method reference như `component::refresh`: nếu method reference gắn với instance, nó giữ receiver `component` khi cần gọi phương thức; từ receiver có thể đi tới nhiều trường dữ liệu khác. Khi chỉ cần một giá trị, truyền đúng dữ liệu nhỏ thay vì giữ toàn bộ receiver.

## 6. Trường hợp bắt giữ sai trong vòng lặp

Biến cục bộ dùng bởi lambda phải effectively final. Vì vậy, mã sau **không biên dịch**:

~~~java
// Đoạn mã cố ý sai, chỉ để giải thích lỗi biên dịch.
for (int i = 0; i < 3; i++) {
    // Runnable task = () -> System.out.println(i);
    // 'i' thay đổi bởi i++ nên không effectively final.
}
~~~

Cách đúng là tạo bản sao cho từng lần lặp:

~~~java
public class LoopCaptureDemo {
    public static void main(String[] args) {
        java.util.List<Runnable> tasks = new java.util.ArrayList<>();
        for (int i = 0; i < 3; i++) {
            int index = i;
            tasks.add(() -> System.out.println(index));
        }
        tasks.forEach(Runnable::run);
    }
}
~~~

~~~bash
javac LoopCaptureDemo.java
java LoopCaptureDemo
~~~

Kết quả:

~~~text
0
1
2
~~~

Bản sao `index` còn giúp thể hiện ý nghĩa “giá trị tại thời điểm tạo task”. Ngược lại, nếu mỗi callback giữ một đối tượng dùng chung có thể đổi trạng thái thì các callback vẫn có thể nhìn thấy giá trị khác nhau khi chạy.

## 7. Thiết kế API để giảm rủi ro

Nên phân biệt từ lúc thiết kế hai kiểu hợp đồng:

- **Snapshot callback:** cần dữ liệu tại thời điểm đăng ký/submission. Chụp giá trị, giảm kích thước dữ liệu, ưu tiên kiểu bất biến. Ví dụ một mã đơn hàng `long orderId` hoặc DTO chứa vài trường cần thiết thay vì toàn bộ entity graph.
- **Live callback:** chủ ý đọc trạng thái mới nhất. Đảm bảo truy cập thread-safe hoặc xác định owner thread; mô tả rõ ai cập nhật, callback được gọi lúc nào, và khi nào phải hủy.
  
Đối với dữ liệu rất lớn hoặc tài nguyên có vòng đời quản lý, cân nhắc phương thức nhận tham số tại lúc chạy:

~~~java
// Phác thảo API: callback nhận dữ liệu lúc thực thi,
// không phải lưu một mảng lớn vào closure từ trước.
java.util.function.Consumer<byte[]> processor = bytes -> {
    System.out.println("received=" + bytes.length);
};
~~~

Việc này chỉ chuyển trách nhiệm giữ tham chiếu sang nơi gọi; vẫn phải giới hạn hàng đợi và thời gian sống dữ liệu. Nếu dùng message queue hoặc executor có backlog, lượng payload đang chờ vẫn có thể rất lớn.

Không coi `WeakReference` là cách sửa mặc định. Weak reference có thể mất đối tượng ngay khi không còn strong reference, khiến callback không còn dữ liệu để chạy; nó không đảm bảo cleanup listener, không giải quyết race condition và không thay cho quản lý vòng đời.

## 8. Dấu hiệu chẩn đoán và cách kiểm tra

**Khi nghi có retention:** quan sát heap sử dụng sau chu kỳ tải, số listener/subscription/task đang chờ, số đối tượng còn sống; so sánh heap dump qua các giai đoạn. Trong heap analyzer, tìm **GC roots**, **retaining path**, **dominator tree** và **retained size**. Ví dụ một lambda được singleton giữ rồi trỏ đến `byte[]` lớn là đường tham chiếu đáng khảo sát. `shallow size` của lambda nhỏ không phản ánh toàn bộ dữ liệu mà nó giữ.

**Khi nghi có lỗi mutable/concurrency:** lập test lặp lại hoặc stress test có điểm đồng bộ rõ ràng; xác định thread nào đọc/ghi, thời điểm đăng ký/chạy, và primitive đồng bộ hóa nào thiết lập happens-before. Đừng xem việc “chạy 100 lần chưa lỗi” là chứng minh thread-safe.

**Khi cần tái hiện:** lập một trường hợp nhỏ có thể chạy bằng Java 17+, tách riêng thời điểm tạo callback, thời điểm thay đổi state, thời điểm thực thi và lúc tháo đăng ký. Với sự cố bộ nhớ thực tế, xác minh bằng profiling/heap dump; không khẳng định leak chỉ dựa vào một ảnh chụp mức sử dụng RAM hoặc lời gọi `System.gc()`.

## 9. Các lỗi hiểu sai thường gặp

1. **“Biến local là final nên object cũng immutable.”** Sai: final/effectively final ngăn gán lại biến tham chiếu, không ngăn đột biến nội dung đối tượng.
2. **“Lambda ra khỏi phương thức tạo nên object sẽ được GC.”** Sai: callback trả về hoặc đã đăng ký có thể giữ object sau khi phương thức kết thúc.
3. **“Lambda nhỏ thì không tốn nhiều bộ nhớ.”** Chưa đủ: retaining path có thể giữ hàng MiB hoặc GiB gián tiếp.
4. **“Dùng `volatile` là đủ cho `count++`.”** Sai: visibility không biến phép cập nhật ghép thành atomic.
5. **“`Collections.unmodifiableList` tạo snapshot.”** Sai: nó là read-only view của danh sách nguồn; nguồn đổi thì view thấy đổi.
6. **“Dùng parallel stream thì mọi side effect đều được bảo vệ.”** Sai: lambda có side effect lên cấu trúc chia sẻ vẫn cần đồng bộ; ưu tiên phép reduction và collector đúng hợp đồng.
7. **“GC sẽ tự đóng file/socket khi callback không dùng nữa.”** Sai: quản lý tài nguyên bằng `try-with-resources` hoặc hợp đồng close cụ thể.
8. **“Gọi cancel là đã loại bỏ mọi retention.”** Không bảo đảm: còn phụ thuộc queue, task đang chạy, future, listener và cơ chế dọn dẹp của từng API.

## 10. Checklist trước khi đưa lambda/callback vào production

- Callback này được **ai giữ**, sống bao lâu, có thể bị gọi trên thread nào và bao nhiêu lần?
- Lambda đã bắt giữ `this`, container, request, buffer, collection, entity graph hoặc resource có kích thước lớn chưa?
- Callback cần **giá trị cố định** hay **trạng thái mới nhất**? Nếu cố định, đã tạo snapshot đúng độ sâu chưa?
- Nếu cùng đọc/ghi mutable state, có chiến lược ownership, atomicity, visibility và synchronization rõ ràng chưa?
- API có thao tác `close/remove/unsubscribe/cancel` phù hợp không? Ai chịu trách nhiệm gọi khi kết thúc vòng đời?
- Nếu queue/task chậm, đã giới hạn số lượng callback/payload tồn đọng chưa?
- Có thể truyền tham số cần thiết tại lúc gọi hoặc giảm dữ liệu bắt giữ xuống immutable ID/value/DTO không?

**Ghi nhớ:** lambda không tự gây memory leak và việc bắt giữ mutable object không mặc nhiên là lỗi. Rủi ro phát sinh khi **vòng đời callback dài hơn vòng đời dữ liệu dự kiến**, hoặc khi **nhiều nơi dùng trạng thái mutable mà thiếu hợp đồng đồng bộ nhất quán**. Thiết kế vòng đời, phạm vi dữ liệu và cơ chế đồng bộ rõ ràng là biện pháp phòng ngừa chính.