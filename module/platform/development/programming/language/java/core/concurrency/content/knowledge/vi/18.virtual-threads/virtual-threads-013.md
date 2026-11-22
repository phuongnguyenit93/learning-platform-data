# Structured Concurrency (preview ở Java 21): vai trò và giới hạn

## 1. Vấn đề: tác vụ cha phải chịu trách nhiệm về các tác vụ con

Giả sử một thao tác xử lý cần đồng thời lấy **thông tin người dùng** và **điểm thưởng**, sau đó ghép thành một kết quả. Hai việc độc lập nên có thể chạy song song. Nhưng nếu người dùng hủy thao tác, một tác vụ thất bại, hoặc hết hạn chờ, điều gì xảy ra với tác vụ còn lại?

Cách viết bất đồng bộ thiếu cấu trúc thường có các vấn đề:

- **Vòng đời rời rạc:** tác vụ con vẫn chạy sau khi phương thức tạo ra nó đã thoát, vì không có nơi duy nhất chịu trách nhiệm chờ và dọn dẹp.
- **Lỗi bị thất lạc:** một future thất bại nhưng không được lấy kết quả, dẫn tới lỗi không được xử lý trong luồng nghiệp vụ.
- **Hủy chưa đồng bộ:** tác vụ cha biết không cần kết quả nữa nhưng các tác vụ con khác vẫn tiếp tục chiếm tài nguyên.
- **Khó quan sát:** khi điều tra sự cố, khó nhìn thấy những thread nào thuộc cùng một thao tác cha.

**Structured Concurrency** tổ chức các tác vụ con thành **một nhóm có phạm vi sống rõ ràng**. Trong Java 21, API preview `StructuredTaskScope` cho phép bắt đầu các subtask trong cùng một scope, chờ chúng, áp dụng chính sách khi thành công/thất bại, và đóng scope khi hoàn tất.

Ý tưởng cốt lõi: **code tạo và sở hữu công việc con có trách nhiệm kết thúc phạm vi công việc ấy**. Việc mở scope, `fork`, `join` rồi `close` giống một khối có điểm vào/ra có thể theo dõi. Nó giúp quản lý nhóm tác vụ an toàn và dễ đọc hơn, nhưng vẫn cần xử lý riêng tài nguyên ngoài JVM và những thao tác không hợp tác với hủy.

Bài này tập trung **Java 21 / JEP 453**, trong ngữ cảnh Virtual Threads của Java. Structured Concurrency ở Java 21 là **preview API**, chưa phải hợp đồng API ổn định để mang nguyên mã nguồn sang mọi bản JDK mới.

## 2. Mô hình một scope: `fork → join → result → close`

Trong Java 21, class chính là `java.util.concurrent.StructuredTaskScope<T>`. Một vòng đời thông thường:

~~~text
Thread gọi (owner)
│
├─ Mở StructuredTaskScope bằng try-with-resources
│   ├─ fork(task A) → thread con A ───────┐
│   ├─ fork(task B) → thread con B ───────┤ chạy đồng thời
│   ├─ join()/joinUntil(...) ◀───────────┘
│   ├─ xem kết quả / xử lý lỗi
│   └─ close() khi ra khỏi try
└─ Tiếp tục sau khi scope được đóng
~~~

Các bước và ý nghĩa:

1. **Mở scope:** tạo một đối tượng scope ở thread gọi, gọi là *owner*. Trong Java 21, constructor mặc định tạo **virtual thread** cho mỗi subtask.
2. **`fork(Callable)`:** chạy subtask trong thread riêng, trả về đối tượng `Subtask` (một số ví dụ dùng kiểu `Supplier<T>` vì `Subtask<T>` cũng cung cấp `get()`). Sau `fork`, hai công việc có thể tiến triển đồng thời.
3. **`join()` / `joinUntil(Instant)`:** owner chờ kết quả theo chính sách của scope. `joinUntil` áp dụng một hạn chờ tuyệt đối và có thể ném `TimeoutException`.
4. **Xem kết quả và lỗi:** với chính sách yêu cầu tất cả thành công, `throwIfFailed()` giúp không đọc kết quả như thể mọi thứ đều ổn khi có task thất bại.
5. **`close()`:** `try-with-resources` đóng scope, chờ các thread con còn sống kết thúc khi cần. Không được hiểu `close` là hủy cưỡng chế một tác vụ không chịu kết thúc.

Code khung cho Java 21:

~~~java
try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
    var first = scope.fork(() -> loadFirst());
    var second = scope.fork(() -> loadSecond());

    scope.join().throwIfFailed();

    return combine(first.get(), second.get());
}
~~~

Đoạn trên **chỉ minh họa**: `loadFirst()`, `loadSecond()` và `combine(...)` là các hàm của ứng dụng, chưa được định nghĩa trong đoạn mã. Phần 4 có chương trình Java 21 độc lập và stdout được xác định.

Khác với việc gọi `Thread.startVirtualThread(...)` trực tiếp rồi bỏ tham chiếu thread, scope thiết lập mối quan hệ cha/con và điểm chờ chung. Khác với một lệnh gọi tuần tự, các subtask trong scope vẫn có thể chạy song song với nhau.

### Scope là phạm vi sở hữu, không chỉ là danh sách thread

- Thread tạo scope được gọi là **owner**; các thao tác điều phối như `join` và `close` phải do owner thực hiện.
- Scope có thể **lồng nhau**: subtask của scope cha có thể mở scope con, tạo cấu trúc công việc dạng cây.
- Nếu scope được dùng với `try-with-resources`, khi rời khối do thành công hoặc exception, `close` vẫn được gọi.
- Sau khi `join` thành công và xử lý các kết quả cần thiết, không còn lý do nghiệp vụ để giữ scope sống.
- Việc đóng scope giúp không bỏ quên các thread thuộc phạm vi, nhưng chỉ có thể hoàn tất nhanh nếu các tác vụ con phản hồi với gián đoạn/hủy.

## 3. Hai chính sách quan trọng của Java 21

Java 21 cung cấp hai subclass preview để mô tả quy tắc kết thúc nhóm công việc.

| Khía cạnh | `ShutdownOnFailure` | `ShutdownOnSuccess<T>` |
|---|---|---|
| Bài toán thích hợp | **Cần tất cả kết quả**; một task lỗi làm cả thao tác thất bại | **Chỉ cần một kết quả thành công** từ nhiều phương án |
| Khi nào short-circuit | Khi có subtask đầu tiên thất bại | Khi có subtask đầu tiên thành công |
| Hành vi với các subtask còn lại | Yêu cầu shutdown, **interrupt** thread chưa xong | Yêu cầu shutdown, **interrupt** thread chưa xong |
| `join()` | Chờ tất cả hoàn tất hoặc có thất bại khiến scope shutdown | Chờ một subtask thành công hoặc tất cả đều hoàn tất |
| Lấy kết quả | Sau `join().throwIfFailed()`, đọc `Supplier.get()` của từng subtask | Sau `join()`, gọi `scope.result()` |
| Mọi subtask đều thất bại | `throwIfFailed()` ném lỗi | `result()` ném lỗi vì không có kết quả thành công |
| Hợp đồng ý nghĩa | Các thành phần kết quả phải nhất quán, thiếu một thành phần là lỗi | Những lời giải thay thế; một lời giải đủ đáp ứng |

### Khi phải nhận đủ kết quả: `ShutdownOnFailure`

Ví dụ tạo hồ sơ gồm tên và điểm. Nếu truy vấn tên thất bại, việc dùng điểm đơn lẻ không tạo được hồ sơ hợp lệ. `ShutdownOnFailure` chủ động báo thất bại và yêu cầu dừng công việc còn lại.

~~~java
try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
    var name = scope.fork(() -> "Lan");
    var points = scope.fork(() -> 120);

    scope.join().throwIfFailed();
    String summary = name.get() + ": " + points.get();
    System.out.println(summary);
}
~~~

Sau `join().throwIfFailed()`, hai subtask đã thành công thì mới dùng `get()`. Với API Java 21, `throwIfFailed()` ném `ExecutionException` khi có subtask thất bại; thông tin gốc thường nằm trong `getCause()`. Trái lại, bản `throwIfFailed(Function<Throwable, ? extends X>)` cho phép tự tạo exception để thích hợp với hợp đồng ứng dụng.

### Khi chỉ cần một kết quả tốt: `ShutdownOnSuccess<T>`

Ví dụ đọc dữ liệu tương đương từ cache và nguồn dự phòng:

~~~java
try (var scope = new StructuredTaskScope.ShutdownOnSuccess<String>()) {
    scope.fork(() -> readCache());
    scope.fork(() -> readReplica());

    scope.join();
    return scope.result();
}
~~~

`readCache()` và `readReplica()` ở đây là các hàm minh họa đã có trong ứng dụng. Kết quả là **tác vụ hoàn thành thành công đầu tiên**, không có nghĩa là tác vụ được `fork` đầu tiên, cũng không phải tác vụ *kết thúc đầu tiên nếu nó thất bại*. Nếu một task lỗi trước, scope tiếp tục chờ cơ hội thành công ở task còn lại. Nếu tất cả đều thất bại, `scope.result()` ném `ExecutionException`. Những lời gọi đọc khác bị yêu cầu dừng khi một lời gọi thành công, nhưng không có đảm bảo chúng ngừng tức thời.

**Chọn policy theo nghiệp vụ trước khi chọn cách chạy thread.** Đối với một yêu cầu cần cả A và B, dùng `ShutdownOnSuccess` là sai nghĩa; với hai nguồn thay thế chỉ cần một, `ShutdownOnFailure` có thể thất bại quá sớm khi nguồn còn lại vẫn hoạt động.

## 4. Chương trình Java 21 độc lập, có kiểm chứng

Tạo file **`StructuredConcurrencyDemo.java`**:

~~~java
import java.time.Instant;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

public class StructuredConcurrencyDemo {
    static String combine() throws InterruptedException, ExecutionException {
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            Supplier<String> name = scope.fork(() -> "Lan");
            Supplier<Integer> points = scope.fork(() -> 120);
            scope.join().throwIfFailed();
            return name.get() + ": " + points.get();
        }
    }

    static String firstSuccess() throws InterruptedException, ExecutionException {
        try (var scope = new StructuredTaskScope.ShutdownOnSuccess<String>()) {
            scope.fork(() -> "cache");
            scope.fork(() -> {
                Thread.sleep(1000);
                return "remote";
            });
            scope.join();
            return scope.result();
        }
    }

    static String firstFailure() throws InterruptedException {
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            scope.fork(() -> { throw new IllegalStateException("bad data"); });
            scope.fork(() -> {
                Thread.sleep(1000);
                return "slow";
            });
            try {
                scope.join().throwIfFailed();
                return "unexpected";
            } catch (ExecutionException ex) {
                return ex.getCause().getClass().getSimpleName();
            }
        }
    }

    static String timeout() throws InterruptedException, ExecutionException {
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            Supplier<String> slow = scope.fork(() -> {
                Thread.sleep(500);
                return "late";
            });
            try {
                scope.joinUntil(Instant.now().plusMillis(20));
                scope.throwIfFailed();
                return slow.get();
            } catch (TimeoutException ex) {
                scope.shutdown();
                scope.join();
                return "timeout";
            }
        }
    }

    static boolean usesVirtualThread() throws InterruptedException, ExecutionException {
        try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
            Supplier<Boolean> child = scope.fork(
                    () -> Thread.currentThread().isVirtual());
            scope.join().throwIfFailed();
            return child.get();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(combine());
        System.out.println(firstSuccess());
        System.out.println(firstFailure());
        System.out.println(timeout());
        System.out.println(usesVirtualThread());
    }
}
~~~

Dùng **JDK 21 thực sự** để biên dịch và chạy preview API:

~~~bash
javac --enable-preview --release 21 -encoding UTF-8 StructuredConcurrencyDemo.java
java --enable-preview StructuredConcurrencyDemo
~~~

**stdout** của chương trình:

~~~text
Lan: 120
cache
IllegalStateException
timeout
true
~~~

Trình biên dịch Java 21 có thể in thêm thông báo `Note: ... uses preview features of Java SE 21` ra kênh thông báo; đó không phải stdout của chương trình.

Đọc lần lượt năm tình huống:

1. **`combine()`**: hai callable cùng hoàn thành thành công; kết quả được ghép sau `join().throwIfFailed()`, in `Lan: 120`.
2. **`firstSuccess()`**: callable cache trả về tức thì, callable kia ngủ 1 giây; kết quả thắng là `cache`, callable chậm nhận tín hiệu interrupt khi scope shutdown.
3. **`firstFailure()`**: một callable ném `IllegalStateException`; `throwIfFailed()` ném `ExecutionException` có `cause` tương ứng; kết quả in tên exception gốc.
4. **`timeout()`**: chờ đến một `Instant` cách thời điểm gọi khoảng 20 ms, trong khi task ngủ 500 ms. Khi hết hạn, code gọi `shutdown()`, `join()` để bảo đảm đường đóng scope rồi trả `timeout`.
5. **`usesVirtualThread()`**: thread được scope Java 21 tạo theo mặc định là virtual thread; vì vậy in `true`.

Để stdout ổn định, chương trình không in từ các subtask và không phụ thuộc vào thứ tự completion của hai kết quả khác nhau. `Thread.sleep` phản hồi với interrupt, nên nhánh short-circuit và đóng scope hoàn tất bình thường. Trong thực tế, một tác vụ I/O không phản hồi hủy có thể khiến việc đóng scope tốn nhiều thời gian hơn.

**Không biên dịch đoạn này bằng JDK 17:** cả virtual threads (`Thread.isVirtual()`) và Structured Concurrency preview của Java 21 đều chưa có ở đó. Lệnh `--enable-preview --release 21` cũng cần chạy với trình biên dịch **JDK 21**; không thể yêu cầu javac ở một JDK mới biên dịch preview của bản 21 bằng cách thay riêng `--release`.

## 5. `join`, ngoại lệ và tính đúng đắn

### `join()` không có nghĩa là mọi task thành công

Mục đích của `join()` là đưa owner tới điểm đồng bộ của scope. Với `ShutdownOnFailure`, nó có thể kết thúc khi một tác vụ thất bại, trước khi các tác vụ khác đã thực sự ngừng hoạt động. Vì vậy gọi `scope.join()` rồi lấy tất cả `get()` ngay mà không kiểm tra chính sách lỗi có thể dẫn tới suy luận sai.

Mẫu đúng cho trường hợp “cần tất cả” là:

~~~java
scope.join().throwIfFailed();
var a = first.get();
var b = second.get();
~~~

`throwIfFailed()` kiểm tra lỗi mà policy đã ghi nhận. Khi nó ném exception, code phía sau không chạy. Lỗi trong callable vẫn là lỗi nghiệp vụ thực tế; structured concurrency giúp truyền và nhóm hóa theo vòng đời, không tự sửa lỗi hay đưa ra fallback.

### `joinUntil(Instant)` chỉ giới hạn thời gian chờ

~~~java
try {
    scope.joinUntil(Instant.now().plusSeconds(2));
    scope.throwIfFailed();
} catch (TimeoutException ex) {
    scope.shutdown();
    scope.join();
    throw ex;
}
~~~

Đoạn này minh họa bên trong một `try` đã mở `ShutdownOnFailure scope`, là mã **không độc lập**. `joinUntil` nhận **thời điểm tuyệt đối** `Instant`, không nhận thời lượng `Duration`. Nếu hết hạn, nó ném `TimeoutException`, và ứng dụng cần quyết định chính sách hủy/dọn dẹp. `scope.shutdown()` yêu cầu interrupt các thread chưa hoàn thành, còn `scope.join()` giúp owner đáp ứng trình tự điều phối trước khi đóng scope.

Hạn chờ **không phải lời hứa** phương thức cha luôn trả trong đúng hai giây: `close()` vẫn chờ các task sống kết thúc, kể cả task không phản hồi interrupt. Với các giao tiếp I/O bên ngoài, nên thiết lập deadline/timeout riêng ở client hoặc API thao tác thật sự.

### `InterruptedException` là tín hiệu điều khiển

`join()`, `joinUntil(...)` và các hoạt động chờ có thể ném `InterruptedException`. Nếu thread owner bị interrupt, một `try-with-resources` vẫn gọi `close` để kết thúc phạm vi. Nếu mã bắt `InterruptedException` mà không truyền tiếp, cần khôi phục interrupt flag khi phù hợp:

~~~java
try {
    doInterruptibleWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đoạn này chỉ minh họa cách xử lý khi `doInterruptibleWork()` là tác vụ hỗ trợ interrupt trong một phương thức trả `void`. Nếu method có thể khai báo `throws InterruptedException`, thường nên truyền exception lên caller. Đừng nuốt interrupt rồi tiếp tục một vòng lặp vô hạn; các scope đang yêu cầu shutdown sẽ phải đợi lâu hoặc không bao giờ kết thúc.

### Owner và thứ tự thao tác

Các phương thức `join`/`joinUntil`/`close` dành cho thread owner. Một số lời gọi vào scope từ thread không hợp lệ có thể bị từ chối. Không chuyển đối tượng scope cho một request độc lập rồi cố đóng từ thread khác. Các thao tác dùng `Subtask.get()` và `Subtask.exception()` cũng có quy tắc kiểm tra trạng thái/owner; trong ví dụ thông thường, hãy đợi `join` và xác thực thành công trước khi đọc kết quả.

Nếu fork rồi thoát `try` mà bỏ qua `join`, đó không phải cách dùng đúng: Java 21 áp dụng kiểm tra cấu trúc và `close()` có thể báo `IllegalStateException`. Tổ chức code sao cho mọi nhánh bình thường đều tới bước join, còn nhánh lỗi/hết hạn xử lý shutdown và cleanup rõ ràng.

## 6. Hủy trong scope: hợp tác, không phải cưỡng bức

`StructuredTaskScope.shutdown()` được thiết kế để:

1. Ngăn việc khởi động các task mới trong scope đã shutdown.
2. Gửi **interrupt** đến các thread con đang chạy và chưa kết thúc (trừ thread hiện tại trong các trường hợp thích hợp).
3. Đánh thức owner đang đợi trong `join`/`joinUntil` để xử lý trạng thái nhóm.

**Interrupt là yêu cầu hợp tác.** Nếu subtask gọi `Thread.sleep`, `BlockingQueue.take` hoặc API hỗ trợ interrupt, nó thường có thể thoát nhanh. Nếu subtask đang thực hiện code bỏ qua interrupt, vòng lặp không kiểm tra cờ interrupt, hoặc I/O không có cơ chế hủy hữu hiệu, thread có thể tiếp tục chạy. Khi đó `close()` phải đợi.

Ví dụ một subtask được thiết kế hợp tác với hủy:

~~~java
static long countUntilInterrupted() {
    long count = 0;
    while (!Thread.currentThread().isInterrupted()) {
        count++;
        // Trong thực tế, xen kẽ công việc hữu ích và kiểm tra hủy.
    }
    return count;
}
~~~

Hàm này chạy độc lập như một phương thức static nhưng **không có điểm dừng tự động**; nó chỉ thoát khi thread thực sự bị interrupt. Không dùng vòng lặp CPU như vậy trong ứng dụng thật để chờ điều kiện; ở đây nó chỉ cho thấy cờ `isInterrupted()`. Tác vụ thật phải tránh busy-wait và đảm bảo dọn tài nguyên trong `finally` hoặc `try-with-resources` của chính nó.

Giả sử một callable đã gửi yêu cầu ghi dữ liệu sang dịch vụ khác. Sau khi sibling thất bại, scope có thể interrupt callable đang đợi phản hồi nhưng **không rollback giao dịch bên ngoài**. Hủy thread Java cũng không đồng nghĩa phía xa ngừng xử lý. Vì vậy, với thao tác có side effect, cần cơ chế nghiệp vụ phù hợp: idempotency, transaction, deadline ở I/O, hoặc trạng thái bù trừ.

## 7. Quan hệ với Virtual Threads và các API concurrency khác

**Virtual Threads** và **Structured Concurrency** giải quyết hai vấn đề khác nhau:

- **Virtual thread:** cung cấp thread nhẹ hơn nhiều thread hệ điều hành trong các workload blocking I/O phù hợp; giúp có thể tạo rất nhiều thread với phong cách đồng bộ.
- **Structured Concurrency:** quản lý **quan hệ vòng đời, kết quả, lỗi và hủy** giữa một nhóm subtask. Nó có thể dùng virtual thread mặc định nhưng ý tưởng cấu trúc không phụ thuộc riêng vào virtual thread.

Trong Java 21, constructor mặc định của `StructuredTaskScope` sử dụng virtual thread. Constructor nhận `ThreadFactory` cho phép chọn kiểu thread theo nhu cầu. Tuy nhiên, `Thread.ofVirtual()` tự nó **không** cung cấp scope, không gom lỗi hay đợi các thread con một cách có cấu trúc.

| Công cụ | Chức năng chính | Điều cần tự quản lý |
|---|---|---|
| `Thread.startVirtualThread(...)` | Bắt đầu một virtual thread | Chờ thread, truyền lỗi, hủy và ownership giữa parent/child |
| `Executors.newVirtualThreadPerTaskExecutor()` | Thực thi các task, một virtual thread mỗi task | Quy ước nhóm tác vụ, chọn kết quả, xử lý lỗi và hủy siblings |
| `CompletableFuture` | Biểu diễn và ghép pipeline bất đồng bộ, callback, exception | Quan hệ lexical giữa task cha/con, hủy thực thi nền, ownership |
| `StructuredTaskScope` (Java 21 preview) | Gom các subtask liên quan thành scope với chính sách join/shutdown | Logic nghiệp vụ, timeout I/O, giới hạn tải và tác dụng phụ |

Có thể dùng `CompletableFuture` cho pipeline/đồ thị phụ thuộc dài, phản hồi async qua nhiều lớp, hoặc callback trên những sự kiện bên ngoài. Structured Concurrency hữu ích nhất khi một thao tác **chia thành nhiều công việc con rồi phải tập hợp lại trước khi kết thúc phạm vi**. Không cần chuyển mọi future và executor thành scope; chọn cấu trúc có thể diễn đạt hợp đồng vòng đời rõ nhất.

### Structured Concurrency không phải cơ chế hạn chế đồng thời

Việc fork hàng nghìn subtask bằng virtual thread không có nghĩa database hoặc API ngoài có thể xử lý hàng nghìn truy vấn đồng thời. **Giới hạn kết nối, quota, pool, rate limit và backpressure** vẫn là trách nhiệm thiết kế. Scope tổ chức các task, không tự quyết định số lượng truy vấn đồng thời an toàn. Với fan-out rất lớn, cần cơ chế giới hạn tải bên cạnh scope.

### Quan hệ với Scoped Values

Cấu trúc cha/con cho phép các virtual thread con nhận ngữ cảnh `ScopedValue` được bind tại điểm tạo scope theo quy tắc Java 21. `ScopedValue` cũng là API preview ở Java 21; có ích khi truyền dữ liệu immutable theo phạm vi gọi. Đây không phải cơ chế chia sẻ biến mutable tự động, và cũng không thay thế việc đồng bộ hóa trạng thái chung giữa các subtask.

## 8. Giới hạn cụ thể của Structured Concurrency preview ở Java 21

### 8.1. API vẫn đang thử nghiệm

- Java 21 giới thiệu preview theo **JEP 453**. Muốn sử dụng, mã nguồn cần biên dịch và chương trình cần chạy với `--enable-preview` tương ứng.
- Preview có thể đổi API, điều kiện sử dụng hoặc bị rút ở bản sau. Một ứng dụng dùng API preview phải được kiểm tra lại khi nâng cấp JDK.
- Đừng viết tài liệu hướng dẫn người học Java 21 bằng chữ ký API của JDK mới. Chẳng hạn, JDK 25 có giao diện preview `StructuredTaskScope<T,R>` và phương thức `StructuredTaskScope.open(...)`; trong khi ví dụ **JDK 21** ở bài này dùng `new StructuredTaskScope.ShutdownOnFailure()` và `new StructuredTaskScope.ShutdownOnSuccess<T>()`. Chúng thuộc các phiên bản API khác nhau.
- Chạy `java -version` và `javac -version` để chắc chắn trình chạy và trình biên dịch phù hợp với cú pháp preview đang dùng.

### 8.2. Hủy không bảo đảm tức thời

`shutdown()` chủ yếu interrupt thread con. `close()` có thể chờ code chưa hợp tác với interrupt. Không có API nào trong scope bảo đảm giết an toàn một lệnh ghi ngoài hệ thống, dừng native call, hay hoàn nguyên side effect.

### 8.3. Không có “fire-and-forget” theo thiết kế

Nếu một công việc cần tiếp tục sống độc lập sau khi thao tác cha trả về, đừng cố giữ nó bên trong một scope rồi bỏ qua join. Đây không phải bài toán structured fan-out/fan-in. Hãy dùng một thành phần có vòng đời rõ ràng hơn (ví dụ executor/service quản lý riêng), cùng chính sách shutdown/monitoring phù hợp.

### 8.4. Không tự thay thế tất cả cơ chế điều phối

Scope không là bộ điều độ hàng đợi, không giới hạn băng thông, không retry tự động, không đảm bảo thứ tự hoàn thành, không biến các callable thành transaction phân tán. Nó cũng không làm CPU-bound task chạy nhanh hơn số core; mức song song thực tế còn phụ thuộc CPU, I/O và tài nguyên ngoài JVM.

### 8.5. Không tự bảo đảm an toàn dữ liệu chia sẻ

Hai subtask ghi vào cùng mutable object vẫn có thể race condition. Dùng immutable data, đồng bộ hóa, concurrent collection hoặc cơ chế chia sẻ trạng thái khác khi cần. `join` giúp xác định điểm hoàn tất và quan hệ happens-before; nó không biến thao tác update không an toàn thành atomic.

### 8.6. Scope không là API portable giữa mọi bản JDK

Đối với thư viện cần hỗ trợ nhiều bản Java, nhất là dự án có baseline thấp hơn Java 21, phụ thuộc vào preview có chi phí rõ ràng. Cần quyết định version support trước khi chọn API. Nếu không chấp nhận preview trong sản phẩm, có thể dùng `ExecutorService`, `Future`, `CompletableFuture` hoặc nền tảng tương thích và tự quản lý vòng đời, tuy nhiều bước hơn.

## 9. Cách áp dụng có kiểm soát

Một quy trình thiết kế thực tế:

1. **Xác định unit of work:** ví dụ một lần dựng báo cáo, một lượt tổng hợp kết quả; xác định đúng task cha và các subtask phải sống cùng nó.
2. **Chọn chính sách:** tất cả kết quả đều bắt buộc (failure làm cả yêu cầu thất bại), hay chỉ cần một nguồn thành công.
3. **Dự trù deadline:** xác định tổng ngân sách thời gian, và timeout của các tài nguyên I/O. `joinUntil` giúp giới hạn chờ, nhưng tính cả thời gian cleanup.
4. **Thiết kế hủy hợp tác:** callable phải phản hồi interrupt, có `try/finally` để đóng tài nguyên, không che nguyên nhân lỗi.
5. **Giới hạn fan-out:** khi số task lớn hoặc nguồn có quota thấp, đặt thêm giới hạn đồng thời thay vì fork không kiểm soát.
6. **Chỉ trả kết quả sau khi có trạng thái hợp lệ:** `join` rồi `throwIfFailed` hoặc `result` tùy policy; không dùng một giá trị chưa chắc thành công.
7. **Quan sát hoạt động:** ghi thời gian của thao tác cha, số task lỗi/hủy, nguồn dữ liệu; có thể dùng thông tin cây thread trong thread dump của JDK để tìm các nhóm subtask đang chạy.
8. **Kiểm tra đúng JDK:** xác minh source Java 21 preview bằng JDK 21 khi build, rồi kiểm tra lại trong kế hoạch nâng cấp phiên bản.

Với scope lồng nhau, yêu cầu hủy từ ancestor có thể lan xuống các subtask thông qua interruption và cấu trúc scope; nhưng **thời gian kết thúc phụ thuộc subtask có phản hồi với hủy hay không**. Thiết kế mỗi tầng như một owner có trách nhiệm, tránh để scope con giữ các thao tác sống quá thời gian mong muốn.

### Các lỗi dễ gặp

- **Gọi `fork` nhưng không `join`:** sai vòng đời, có thể gây exception khi đóng scope.
- **Dùng `ShutdownOnSuccess` cho kết quả cần đủ các thành phần:** cho phép trả sớm với dữ liệu không đầy đủ.
- **Quên `throwIfFailed`:** bỏ qua lỗi trong một task đã fork, sau đó vẫn coi aggregate thành công.
- **Giả định `close()` luôn trả tức thời:** task không hợp tác interrupt có thể làm kẹt thao tác đóng.
- **Bắt và nuốt `InterruptedException`:** khiến hủy chậm hoặc không hoạt động.
- **Chạy preview Java 21 trên compiler/runtime khác release:** gặp lỗi thiếu API hoặc cú pháp không khớp.
- **Tưởng virtual threads loại bỏ race condition:** virtual thread vẫn truy cập memory chung theo quy tắc Java Memory Model.
- **Fork quá nhiều truy vấn mà không giới hạn:** dễ làm cạn connection pool hoặc vượt quota nguồn.
- **Nhầm timeout với rollback:** deadline không hoàn nguyên ghi dữ liệu đã thực hiện ở hệ thống ngoài.

## 10. Câu hỏi tự kiểm tra

**1. Hai tác vụ A, B đều bắt buộc để tạo kết quả, B thất bại. Dùng policy nào?**  
`ShutdownOnFailure`, vì thao tác cần cả hai; lỗi ở B khiến yêu cầu dừng công việc A không còn cần thiết và báo thất bại. A có thể cần thời gian để phản hồi interrupt.

**2. Ba máy chủ trả cùng dữ liệu, chỉ cần một phản hồi thành công. Nếu máy thứ nhất thất bại nhưng máy thứ hai thành công thì sao?**  
`ShutdownOnSuccess` tiếp tục chờ cho tới khi có một thành công; `result()` trả kết quả thắng. Lỗi của máy thứ nhất không mặc nhiên khiến scope thất bại.

**3. `joinUntil` ném `TimeoutException` có đảm bảo tất cả task đã ngừng?**  
Không. Owner cần quyết định `shutdown` và hoàn tất cleanup. `close` vẫn có thể phải đợi task không chịu dừng.

**4. Dùng `Thread.startVirtualThread` có tự tạo structured concurrency không?**  
Không. Virtual thread là loại thread; structured concurrency cung cấp ràng buộc vòng đời và chính sách cho nhóm task.

**5. Có thể copy nguyên ví dụ dùng constructor Java 21 sang Java 25 rồi bật preview là chạy được không?**  
Không nên giả định như vậy: API preview đã thay đổi. Phải tham khảo đúng Java API Specification và JEP của phiên bản đang dùng, sửa code và chạy kiểm thử.

## 11. Tài liệu gốc để đối chiếu phiên bản

- [Oracle Java 21 — Structured Concurrency](https://docs.oracle.com/en/java/javase/21/core/structured-concurrency.html): hướng dẫn mô hình `fork`, `join`, `close` và chính sách kết thúc.
- [Java 21 API — StructuredTaskScope](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): chữ ký và semantics của API preview đúng Java 21.
- [OpenJDK JEP 453 — Structured Concurrency (Preview)](https://openjdk.org/jeps/453): bối cảnh và mục tiêu thiết kế Java 21.
- [Java 25 API — StructuredTaskScope](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): đọc khi so sánh quá trình thay đổi API qua phiên bản.

Structured Concurrency làm rõ **ai sở hữu các task, khi nào kết quả được dùng, ai chịu trách nhiệm khi lỗi hoặc bị hủy**. Sức mạnh chính của nó là phạm vi vòng đời có cấu trúc; tính đúng đắn tổng thể vẫn phụ thuộc vào policy phù hợp, hủy hợp tác, giới hạn tài nguyên và những ràng buộc nghiệp vụ thực tế.
