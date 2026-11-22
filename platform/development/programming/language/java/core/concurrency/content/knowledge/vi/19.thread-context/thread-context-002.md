# Khởi tạo giá trị với ThreadLocal.withInitial() trong Java

## 1. ThreadLocal.withInitial() giải quyết vấn đề gì?

`ThreadLocal<T>` là một cơ chế lưu **giá trị gắn với từng thread**. Mỗi thread truy cập cùng một đối tượng `ThreadLocal` nhưng nhìn thấy giá trị riêng của mình. Nó hữu ích khi một thao tác chạy chủ yếu trên một thread và cần trạng thái cục bộ như bộ đệm tạm, bộ đếm, hoặc ngữ cảnh phục vụ một tác vụ. Giá trị không tự truyền sang thread khác và `ThreadLocal` không thay thế cơ chế đồng bộ khi dữ liệu thực sự được chia sẻ.

Khi chỉ tạo:

~~~java
ThreadLocal<StringBuilder> buffer = new ThreadLocal<>();
~~~

lần gọi `buffer.get()` đầu tiên của mỗi thread trả về `null`, trừ khi thread đã `set()` giá trị. Nếu cần mỗi thread tự có một `StringBuilder` riêng khi dùng lần đầu, có thể viết:

~~~java
ThreadLocal<StringBuilder> buffer =
    ThreadLocal.withInitial(StringBuilder::new);
~~~

Bây giờ, **mỗi thread sẽ nhận một `StringBuilder` mới khi chính thread đó gọi `get()` lần đầu**, và tiếp tục lấy lại cùng đối tượng trong các lần `get()` sau cho đến khi thay bằng `set()` hoặc bỏ bằng `remove()`.

`withInitial()` có hai lợi ích: xác định giá trị ban đầu rõ ràng và tránh lặp logic kiểu “nếu `get() == null` thì tạo mới”. Tuy nhiên, giá trị ban đầu **không được tạo ngay lúc gọi `withInitial()`**.

### Mục tiêu sau bài học

- Hiểu chính xác tính lazy và per-thread của hàm khởi tạo.
- Phân biệt `get()`, `set()`, `remove()` và `set(null)`.
- Khởi tạo đúng đối tượng mutable riêng cho từng thread.
- Sử dụng trong `ExecutorService`/thread pool mà không giữ trạng thái của tác vụ trước.
- Biết giới hạn của `ThreadLocal` khi công việc chuyển thread, chạy bất đồng bộ hoặc có vòng đời dài.

Bài viết chỉ dùng Java concurrency chuẩn, độc lập với các framework.

## 2. API, kiểu dữ liệu và thời điểm gọi Supplier

Trong JDK, phương thức tĩnh có dạng:

~~~java
public static <S> ThreadLocal<S> withInitial(
    java.util.function.Supplier<? extends S> supplier)
~~~

`Supplier<? extends S>` là hàm không nhận tham số và trả về một giá trị phù hợp với `S`. Có thể dùng lambda hoặc method reference:

~~~java
ThreadLocal<Integer> sequence = ThreadLocal.withInitial(() -> 0);
ThreadLocal<StringBuilder> builder = ThreadLocal.withInitial(StringBuilder::new);
ThreadLocal<java.util.ArrayList<String>> items =
    ThreadLocal.withInitial(java.util.ArrayList::new);
~~~

Các ví dụ này **khai báo ba ThreadLocal**, chưa buộc thread hiện tại tạo giá trị nào. Lời gọi `get()` trên thread chưa có giá trị mới kích hoạt supplier tương ứng. Nếu dùng `withInitial(null)` thì lời gọi khởi tạo `ThreadLocal` bị từ chối bằng `NullPointerException` vì supplier không được phép là `null`; điều này khác với supplier hợp lệ trả về `null`.

Với một đối tượng `ThreadLocal` cụ thể, trạng thái của **mỗi thread** vận hành như sau:

| Hành động trong thread | Giá trị quan sát được | Supplier có chạy không? |
| --- | --- | --- |
| Mới tạo `ThreadLocal.withInitial(factory)` | Thread chưa có giá trị | Chưa |
| `get()` lần đầu, chưa từng `set()` | Giá trị do `factory.get()` tạo | Có, trong thread gọi `get()` |
| `get()` tiếp theo | Chính giá trị đã lưu | Không |
| `set(custom)` trước `get()` lần đầu | Lấy `custom` khi `get()` | Không |
| `set(custom)` sau `get()` | Thay giá trị hiện tại bằng `custom` | Không |
| `set(null)` | `get()` trả `null` đã lưu | Không khởi tạo lại |
| `remove()` rồi `get()` | Giá trị được tạo lại | Có, ở lần `get()` sau đó |

Hai điều dễ nhầm:

1. **Giá trị riêng theo thread, không riêng theo lần gọi phương thức.** Nếu hai request chạy nối tiếp trên cùng một thread trong pool, cả hai có thể thấy *cùng giá trị cũ* nếu không làm sạch.
2. **Supplier có thể chạy nhiều lần trên cùng một thread.** Mỗi lần `remove()` xoá mapping, lần `get()` kế tiếp có thể gọi supplier lại. Vì vậy không nên xem supplier là bộ khởi tạo “chỉ chạy một lần trong cả ứng dụng”.

Khi supplier trả về `null`, `null` vẫn là một giá trị được ghi nhận cho thread. `get()` tiếp theo không tự gọi supplier lại chỉ vì nhận `null`.

## 3. Ví dụ Java 17 chạy được: lazy initialization, set và remove

Ví dụ tạo một danh sách sự kiện cho từng thread. Một `newSingleThreadExecutor()` cho phép chạy hai tác vụ **trên cùng worker thread**, để thấy vì sao cần `remove()` ở cuối từng tác vụ. `AtomicInteger` chỉ dùng đo số lần supplier được chạy và an toàn nếu demo mở rộng sang nhiều thread.

Tạo tệp `ThreadLocalWithInitialDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class ThreadLocalWithInitialDemo {
    private static final AtomicInteger creations = new AtomicInteger();

    private static final ThreadLocal<List<String>> events =
        ThreadLocal.withInitial(() -> {
            creations.incrementAndGet();
            return new ArrayList<>();
        });

    private static String handle(String requestId) {
        List<String> localEvents = events.get();

        try {
            localEvents.add(requestId);
            return String.join(", ", localEvents);
        } finally {
            // Xoá trạng thái tác vụ khỏi thread được tái sử dụng.
            events.remove();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Trước get: " + creations.get());

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<String> first =
                executor.submit(() -> handle("A"));
            System.out.println("Lượt 1: " + first.get());

            Future<String> second =
                executor.submit(() -> handle("B"));
            System.out.println("Lượt 2: " + second.get());
        } finally {
            executor.shutdown();
        }

        System.out.println("Số lần tạo: " + creations.get());

        AtomicInteger initCalls = new AtomicInteger();
        ThreadLocal<String> label = ThreadLocal.withInitial(() -> {
            initCalls.incrementAndGet();
            return "initial";
        });

        label.set("manual"); // set trước get: chưa gọi supplier.
        System.out.println("set trước get: " +
            label.get() + ", init=" + initCalls.get());

        label.remove(); // get tiếp theo sẽ gọi supplier.
        System.out.println("sau remove: " +
            label.get() + ", init=" + initCalls.get());

        label.set(null); // null là giá trị đang được lưu.
        System.out.println("set(null): " +
            (label.get() == null) + ", init=" + initCalls.get());

        label.remove();
    }
}
~~~

Biên dịch, chạy trên JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 ThreadLocalWithInitialDemo.java
java ThreadLocalWithInitialDemo
~~~

Stdout:

~~~text
Trước get: 0
Lượt 1: A
Lượt 2: B
Số lần tạo: 2
set trước get: manual, init=0
sau remove: initial, init=1
set(null): true, init=1
~~~

**Vì sao output có tính xác định?**

- Tạo `events` không gọi supplier, nên dòng đầu có `0`.
- `newSingleThreadExecutor` chạy cả hai nhiệm vụ trên một worker, và `first.get()` hoàn tất trước khi gửi nhiệm vụ thứ hai. Mỗi nhiệm vụ gọi `get()` khi mapping vừa bị `remove()` ở nhiệm vụ trước; supplier chạy hai lần.
- Danh sách của nhiệm vụ B không giữ phần tử A do khối `finally` đã xoá mapping. Nếu bỏ `events.remove()`, dòng thứ hai sẽ thành `Lượt 2: A, B` và tổng số lần tạo chỉ là `1`.
- `label.set("manual")` tạo mapping trước khi `label.get()`, nên supplier của `label` chưa chạy. `remove()` buộc `get()` kế tiếp khởi tạo lại.
- `label.set(null)` lưu `null`; `get()` không khởi tạo thêm. `label.remove()` cuối cùng giải phóng mapping của thread chính.

Với ví dụ này, đối tượng `ArrayList` được dùng trong đúng một worker thread tại từng thời điểm. `ArrayList` không tự trở thành thread-safe nhờ đưa vào `ThreadLocal`; điều kiện an toàn là không chuyển tham chiếu danh sách đó cho thread khác để cùng chỉnh sửa.

## 4. Supplier đúng: tạo đối tượng riêng thay vì trả về đối tượng dùng chung

Mẫu khởi tạo một giá trị mutable nên **tạo mới bên trong supplier**:

~~~java
ThreadLocal<StringBuilder> correct =
    ThreadLocal.withInitial(StringBuilder::new);
~~~

Sai về mục tiêu cô lập dữ liệu:

~~~java
StringBuilder shared = new StringBuilder();
ThreadLocal<StringBuilder> incorrect =
    ThreadLocal.withInitial(() -> shared);
~~~

Trong đoạn sai, mỗi thread có một *mapping* riêng, nhưng tất cả mapping lại giữ **cùng tham chiếu `shared`**. Nhiều thread cùng sửa `shared` sẽ tranh chấp dữ liệu. `ThreadLocal` không sao chép đối tượng cho bạn.

Các kiểu giá trị có thể dùng:

- **Immutable:** Ví dụ mã nhận dạng hoặc cấu hình không thay đổi; cách khởi tạo có thể trả về cùng đối tượng nếu chia sẻ là có chủ đích.
- **Mutable riêng cho thread:** Ví dụ `StringBuilder`, `ArrayList`, parser hoặc bộ xử lý có state; supplier phải tạo instance thích hợp và không để tham chiếu thoát ra ngoài thread.
- **Đối tượng đắt tiền:** Chỉ dùng `ThreadLocal` nếu lợi ích tái sử dụng lớn hơn chi phí mỗi thread giữ một bản, và đã có chính sách dọn tài nguyên.

Chú ý **supplier là một đối tượng hàm có thể được nhiều thread cùng gọi**. Lambda có capture mutable state bên ngoài, ví dụ tăng một `int` nằm trong object dùng chung mà không đồng bộ, vẫn có data race. Trong ví dụ runnable, `AtomicInteger` bảo vệ việc đếm lần tạo; nó không phải cơ chế của `ThreadLocal`.

Tránh tạo `ThreadLocal` mới trong mỗi lần cần lấy trạng thái:

~~~java
// Sai mục đích: mỗi lời gọi tạo một key ThreadLocal khác.
static StringBuilder newUnrelatedBuffer() {
    return ThreadLocal.withInitial(StringBuilder::new).get();
}
~~~

Nếu ý định là truy cập trạng thái có vòng đời của thread, hãy dùng **cùng một key `ThreadLocal`** được giữ trong field (thường `private static final` hoặc instance field có lifecycle rõ ràng). Các thành phần không liên quan không nên dùng chung key chỉ vì cùng kiểu giá trị.

## 5. withInitial() và override initialValue(): tương đương ở ý tưởng nào?

Trước Java 8, một cách phổ biến là subclass ẩn danh:

~~~java
ThreadLocal<StringBuilder> oldStyle = new ThreadLocal<>() {
    @Override
    protected StringBuilder initialValue() {
        return new StringBuilder();
    }
};
~~~

Với Java 8+, cách tương ứng gọn hơn:

~~~java
ThreadLocal<StringBuilder> modern =
    ThreadLocal.withInitial(StringBuilder::new);
~~~

Cả hai có cùng ý tưởng: khi `get()` gặp thread chưa có mapping, gọi logic khởi tạo rồi lưu giá trị để dùng lại trong thread đó. `withInitial` không tạo thread hay lên lịch tác vụ, cũng không đổi nguyên tắc `set`/`remove`.

Dùng `withInitial` khi factory có thể diễn tả rõ bằng `Supplier`. Override `initialValue()` vẫn hợp lệ khi cần subclass hoặc logic riêng, nhưng không cần tạo subclass chỉ để trả về một giá trị.

Nếu factory ném `RuntimeException` trong `get()` đầu tiên, exception xuất hiện tại **lời gọi `get()` đó**; giá trị cho thread chưa được thiết lập thành công. Lần `get()` sau có thể thử factory lại. `Supplier.get()` không khai báo checked exception; nếu khởi tạo có checked exception thì phải chọn cách xử lý/đóng gói rõ ràng, không thể đơn giản ném checked exception từ lambda của `Supplier`.

## 6. Thread pool: khởi tạo theo thread, không theo request

Hãy tưởng tượng một `ExecutorService` có 4 worker nhưng ứng dụng xử lý 10.000 yêu cầu. Nếu dùng:

~~~java
private static final ThreadLocal<String> CURRENT_REQUEST =
    ThreadLocal.withInitial(() -> "unassigned");
~~~

thì mỗi worker có thể khởi tạo giá trị `"unassigned"` ở lần `get()` đầu tiên, sau đó được gán request thực bằng `set()`. Khi worker kết thúc request, **thread không biến mất** mà tiếp tục nhận yêu cầu mới. Vì thế, việc có supplier mặc định **không bảo đảm** trạng thái được đặt lại ở ranh giới request.

Một mẫu xử lý tác vụ cấp Java chuẩn:

~~~java
static String processOne(String requestId) {
    CURRENT_REQUEST.set(requestId);
    try {
        return "Handling " + CURRENT_REQUEST.get();
    } finally {
        CURRENT_REQUEST.remove();
    }
}
~~~

Đây là đoạn minh hoạ được đặt cùng class với field `CURRENT_REQUEST` ở trên. Dùng `finally` để dọn cả khi công việc ném exception hoặc trả về sớm. Không đặt `remove()` chỉ ở nhánh thành công.

Trong trường hợp caller **đã có một ngữ cảnh ngoài đang hoạt động** và muốn tạm thay giá trị trong một lời gọi lồng nhau, `remove()` ngay sau lời gọi trong có thể xoá mất ngữ cảnh ngoài. Có thể lưu và phục hồi giá trị cũ:

~~~java
// Minh hoạ một scope lồng trong scope ngoài đã có CURRENT_REQUEST.
String previous = CURRENT_REQUEST.get();
CURRENT_REQUEST.set("nested-request");
try {
    // Gọi công việc lồng nhau ở đây.
} finally {
    CURRENT_REQUEST.set(previous);
}
~~~

Cách này chủ động gọi `get()` và vì vậy có thể tạo giá trị mặc định nếu thread trước đó chưa có mapping. Muốn phân biệt chính xác trạng thái “chưa hề có mapping” với “đã lưu null”, cần thiết kế scope/ownership riêng; API công khai của `ThreadLocal` không có phương thức kiểm tra sự tồn tại của mapping mà không khởi tạo. Ở **ranh giới tác vụ ngoài cùng**, chủ sở hữu vẫn phải xác định rõ thời điểm `remove()`.

## 7. ThreadLocal không tự lan qua các tác vụ bất đồng bộ

Một lưu ý cốt lõi: `ThreadLocal` đi theo **thread đang chạy**, không đi theo đối tượng request hay chuỗi lời gọi logic.

~~~java
// Minh hoạ: trong một class có field CURRENT_REQUEST.
// executor là ExecutorService đã tạo và được quản lý vòng đời.
CURRENT_REQUEST.set("req-42");

java.util.concurrent.CompletableFuture<String> result =
    java.util.concurrent.CompletableFuture.supplyAsync(
        () -> CURRENT_REQUEST.get(), executor);
~~~

Không thể mong `result` nhận `"req-42"`. Tác vụ bất đồng bộ chạy ở thread của `executor`, nơi mapping `CURRENT_REQUEST` có thể chưa có hoặc còn trạng thái khác nếu code trước đó quản lý sai. Chính sách ngữ cảnh cần được xác định khi bàn giao tác vụ.

Với dữ liệu nhỏ, cách rõ ràng nhất là **truyền tham số**:

~~~java
String requestId = CURRENT_REQUEST.get();
java.util.concurrent.CompletableFuture<String> result =
    java.util.concurrent.CompletableFuture.supplyAsync(
        () -> "Handling " + requestId, executor);
~~~

Nếu thư viện bên dưới bắt buộc đọc `ThreadLocal`, có thể capture giá trị tại thread gọi, rồi `set/remove` trong chính worker:

~~~java
String requestId = CURRENT_REQUEST.get();
java.util.concurrent.CompletableFuture<String> result =
    java.util.concurrent.CompletableFuture.supplyAsync(() -> {
        CURRENT_REQUEST.set(requestId);
        try {
            return "Handling " + CURRENT_REQUEST.get();
        } finally {
            CURRENT_REQUEST.remove();
        }
    }, executor);
~~~

Ba đoạn trên là **minh hoạ độc lập về luồng ngữ cảnh**, giả định `executor` và `CURRENT_REQUEST` đã được khai báo và caller chịu trách nhiệm đóng executor, dọn ngữ cảnh trên thread gọi. Không dùng `ThreadLocal` như cơ chế ẩn để truyền dữ liệu giữa thread.

`InheritableThreadLocal` là API khác dành cho một số tình huống thread con kế thừa giá trị khi tạo thread; nó không làm việc chuyển ngữ cảnh qua thread pool trở nên tự động hay đáng tin cậy. Cũng không nên suy ra các continuation của `CompletableFuture` sẽ luôn chạy ở cùng thread với phần trước: các stage khác nhau có thể chạy trên các thread khác nhau tùy cách hoàn tất và executor.

## 8. Vòng đời, bộ nhớ và hiệu năng

`ThreadLocal` sử dụng cấu trúc lưu giá trị liên quan đến từng thread. Có thể hình dung:

~~~text
Thread A -> ThreadLocal key -> value A
Thread B -> ThreadLocal key -> value B
Thread C -> ThreadLocal key -> value C
~~~

Sơ đồ biểu diễn logic quan sát; chi tiết triển khai là mỗi `Thread` có vùng lưu trữ mapping theo key `ThreadLocal`. Một `ThreadLocal` được khai báo `static final` giữ key tồn tại lâu; nếu thread của pool cũng sống lâu, giá trị lớn có thể bị giữ lâu ngoài ý muốn. Với key không còn tham chiếu mạnh, việc key được quản lý bằng tham chiếu yếu trong `ThreadLocalMap` không bảo đảm value được thu hồi tức thì: value có thể tồn tại tới khi map dọn entry cũ hoặc thread kết thúc. Đừng dựa vào GC thay cho việc `remove()` đúng thời điểm.

Quy tắc thực tế:

- Đừng giữ cả object graph lớn, request body, session hoặc tài nguyên cần đóng trong `ThreadLocal` lâu hơn yêu cầu.
- `remove()` xoá mapping; **nó không tự gọi `close()`** trên value. Nếu value sở hữu file, socket hoặc tài nguyên đóng được, hãy đóng trong `finally` theo lifecycle trước khi bỏ mapping.
- `withInitial(StringBuilder::new)` có thể giúp tái sử dụng bộ đệm trên worker, nhưng nội dung cũ vẫn còn nếu không `setLength(0)` hoặc `remove()`. Giữ bộ đệm quá lớn có thể gây giữ bộ nhớ lâu.
- Mỗi thread cần value riêng có thể làm tăng chi phí theo số thread. Không dùng `ThreadLocal` cho mọi đối tượng chỉ để tránh truyền tham số.
- Khi sử dụng virtual threads trên Java 21+, `ThreadLocal` vẫn có thể hoạt động, nhưng mẫu “giữ cache cho mỗi thread” thường không phù hợp với số lượng virtual thread rất lớn. Cân nhắc thiết kế truyền dữ liệu và vòng đời tác vụ thay vì mặc định giữ state per-thread.

Với giá trị immutable hoặc rẻ và thread-safe, truyền trực tiếp qua tham số thường đơn giản hơn. `ThreadLocal.withInitial` có giá trị khi việc gắn trạng thái vào *thread hiện tại* là quyết định có chủ đích.

## 9. Các lỗi phổ biến và cách kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `get()` trả `null` dù dùng `withInitial` | Supplier thật sự trả `null` hoặc đã `set(null)` | Xác định contract: giá trị `null` có hợp lệ không; không coi `null` luôn là “chưa khởi tạo” |
| Hai request thấy cùng dữ liệu | Pool tái sử dụng thread; không xoá mapping giữa request | `set` theo đầu tác vụ, `remove` trong `finally` |
| Hai thread cùng sửa một đối tượng | Supplier trả về tham chiếu mutable dùng chung | Tạo instance mới bên trong supplier |
| Supplier không chạy ở lần `get()` đầu như mong đợi | Thread đã `set()` trước `get()` | Kiểm tra trình tự `set/get/remove` |
| Supplier chạy lại | Thread gọi `remove()` hoặc lần `get()` trước khởi tạo lỗi | Hiểu khởi tạo xảy ra theo mapping hiện tại |
| Context biến mất sau `supplyAsync` | Công việc chuyển sang thread khác | Truyền tham số hoặc capture/set/cleanup ở worker |
| Bộ nhớ tăng trên pool dài hạn | Value lớn sống cùng worker hoặc entry cũ chưa được dọn | Giới hạn value, thiết kế lifecycle, `remove()` |
| Dữ liệu bị mất khi lồng scope | Scope bên trong gọi `remove()` làm mất trạng thái scope ngoài | Lưu/phục hồi trạng thái ngoài hoặc thiết kế ownership theo scope |

Tự kiểm chứng bằng cách sửa ví dụ mục 3:

1. Bỏ `events.remove()`, quan sát lượt 2 thấy cả `A` và `B`. Đây là minh chứng trực tiếp cho **state leak** giữa hai tác vụ trên một worker.
2. Khôi phục `remove()`, thử gọi `events.get()` hai lần trong cùng tác vụ và so sánh bằng `==`: cả hai tham chiếu tới cùng danh sách trước khi `remove()`.
3. Đổi supplier thành `() -> null`: `get()` liên tiếp đều trả `null` nhưng mapping không tự khởi tạo lại.
4. Tạo hai thread riêng, mỗi thread lấy `events.get()`. Các thread nhận danh sách khác nhau nếu supplier tạo `new ArrayList<>()` và không chia sẻ tham chiếu ra ngoài.
5. Cho công việc ném exception bên trong `try` của `handle()`; `finally` vẫn chạy và dọn giá trị. Trong môi trường thật, cũng cần kiểm tra nhánh bị huỷ/ngắt theo contract của tác vụ.

## 10. Khi nào nên dùng và điều cần ghi nhớ

Chọn `ThreadLocal.withInitial(factory)` khi một giá trị **cần thuộc về từng thread**, có cách khởi tạo rõ ràng và có vòng đời dọn dẹp xác định. `withInitial` chạy **lười (lazy)** tại `get()` đầu tiên chưa có mapping; `set()` ghi đè, `set(null)` là một giá trị hợp lệ, còn `remove()` xóa mapping để lần `get()` sau khởi tạo lại.

Điều quan trọng nhất trong Java concurrency là nhận ra hai ranh giới khác nhau: **thread** và **tác vụ logic**. Trên thread pool, nhiều tác vụ dùng cùng một thread; với API bất đồng bộ, một tác vụ có thể đi qua nhiều thread. Vì vậy hãy dùng `try/finally` và `remove()` khi sở hữu ngữ cảnh cấp tác vụ, truyền dữ liệu tường minh khi chuyển thread, và không giả định supplier tạo dữ liệu mới cho mỗi request.