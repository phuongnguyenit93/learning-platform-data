# Rò rỉ context khi tái sử dụng thread pool

Trong ứng dụng Java chạy đồng thời, **context của một tác vụ** có thể gồm mã người dùng, tenant, correlation ID, trace ID, locale hoặc trạng thái phục vụ một lần xử lý. Nếu ứng dụng lưu những thông tin này vào `ThreadLocal` nhưng không xóa sau tác vụ, một thread trong pool có thể mang context của **tác vụ trước** sang tác vụ tiếp theo. Đây là lỗi *rò rỉ context* (context leakage), thường dẫn đến log sai, hành vi sai hoặc thậm chí lộ dữ liệu giữa các yêu cầu.

Bài này tập trung vào **Java concurrency thuần**: `ThreadLocal`, `InheritableThreadLocal`, `ExecutorService`, `Future` và cách thiết kế điểm bắt đầu/kết thúc context. Không cần framework để hiểu, tái hiện hay sửa lỗi.

## 1. Context gắn với tác vụ khác với context gắn với thread

*Context của tác vụ* là dữ liệu chỉ có ý nghĩa trong phạm vi một công việc cụ thể, ví dụ:

- `userId` / `tenantId`: ai hoặc đơn vị nào đang được xử lý.
- `requestId` / `traceId`: liên kết log của một chuỗi công việc.
- `locale`: ngôn ngữ yêu cầu.
- Một cờ, cấu hình hoặc metadata tạm thời có vòng đời bằng một tác vụ.

`ThreadLocal<T>` lại lưu **một giá trị cho mỗi thread**, không lưu một giá trị cho mỗi tác vụ. Hai tác vụ chạy trên cùng worker sẽ đọc **cùng slot ThreadLocal của worker đó** nếu tác vụ trước đã `set()` và chưa `remove()`.

Tính chất quan trọng:

- `ThreadLocal.set(value)` ghi giá trị trong **thread đang gọi**.
- `ThreadLocal.get()` đọc giá trị thuộc **thread đang gọi**, không tự biết request/task.
- `ThreadLocal.remove()` xóa giá trị của ThreadLocal đó trên **thread đang gọi**.
- Một ThreadLocal instance có thể được chia sẻ bằng field `static final`; giá trị trong các thread khác nhau vẫn độc lập.
- `ThreadLocal` **không tự truyền context** từ thread gọi `submit()` sang worker của `ExecutorService`.

Điểm dễ sai là giả định “mỗi tác vụ có một thread riêng”. Với thread pool, worker tồn tại lâu hơn task và thường được tái sử dụng.

```text
Thread gọi submit:           submit(A)         submit(B)
                                 |                 |
ExecutorService queue:           A ----->          B
                                 |                 |
Worker-1:                    set user=alice     get user?
                              xử lý A xong        |
                              KHÔNG remove        v
                                               "alice" cũ
```

Tác vụ B có thể không hề nhận `userId` nhưng vẫn đọc được giá trị từ A. Đó là lỗi dù hai tác vụ **không chạy cùng lúc**: chúng dùng chung worker ở hai thời điểm khác nhau.

## 2. Vì sao thread pool làm lỗi khó phát hiện?

`Executors.newFixedThreadPool(n)` giữ các worker để xử lý nhiều công việc theo thời gian; `newSingleThreadExecutor()` là tình huống đơn giản nhất để tái hiện cùng một worker. Với nhiều worker, tác vụ B chỉ thấy context cũ nếu nó được lập lịch lên worker từng chạy A (và slot đó chưa được dọn). Do đó lỗi có thể xuất hiện ngẫu nhiên theo tải và thứ tự scheduling.

Chuỗi sự kiện điển hình:

1. Tác vụ A chạy trên worker W, gọi `USER.set("alice")`.
2. A hoàn thành hoặc ném ngoại lệ nhưng không dọn `USER`.
3. W được trả về trạng thái rảnh, **thread vẫn sống**.
4. Tác vụ B chạy trên W; do một nhánh code bỏ qua `set()`, B gọi `USER.get()`.
5. B nhận `alice` dù đó là context của A.

Nếu B được chuyển sang worker khác, lỗi có thể tạm biến mất. Tăng số worker có thể đổi tần suất nhưng không giải quyết nguyên nhân. Tắt/khởi động lại pool có thể làm dấu hiệu biến mất vì worker cũ chết, nhưng không phải biện pháp sửa.

**Hậu quả cần phân biệt:**

| Loại rò rỉ | Điều thực sự xảy ra | Tác động |
|---|---|---|
| **Rò rỉ giá trị/ngữ cảnh** | Tác vụ sau đọc context của tác vụ trước | Sai log, gắn nhầm tenant, xử lý nhầm dữ liệu |
| **Rò rỉ tham chiếu/bộ nhớ** | Worker sống lâu vẫn giữ đối tượng do ThreadLocal tham chiếu | Heap tăng, đối tượng không được GC như mong đợi |
| **Truyền context thiếu** | Tác vụ khác chạy trên worker chưa được cài context | `get()` trả `null` hoặc mặc định sai |
| **Context bị thay đổi ngoài ý muốn** | Các phần code trong cùng worker chỉnh ThreadLocal mà không khôi phục | Caller sau lời gọi lồng nhau đọc giá trị sai |

Các tình huống trên cùng liên quan thread context nhưng **không đồng nghĩa** nhau. Muốn sửa đúng phải biết context đang bị giữ lại, bị thiếu hay bị ghi đè.

## 3. Ví dụ Java: tái hiện rò rỉ context một cách xác định

Ví dụ dùng executor một worker để ép hai tác vụ lần lượt chạy trên cùng platform thread. Lưu tên tệp **`ContextLeakDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ContextLeakDemo {
    private static final ThreadLocal<String> USER = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            pool.submit(() -> {
                USER.set("alice");
                System.out.println("A user=" + USER.get());
                // BUG: thiếu USER.remove().
            }).get();

            pool.submit(() -> System.out.println("B user=" + USER.get())).get();
        } finally {
            pool.shutdown();
        }
    }
}
```

Chạy với **JDK 17+**:

```bash
javac ContextLeakDemo.java
java ContextLeakDemo
```

Kết quả:

```text
A user=alice
B user=alice
```

**Giải thích từng bước:**

- `USER` là một đối tượng ThreadLocal dùng chung, nhưng giá trị `alice` được đặt trong worker khi A chạy.
- `Future.get()` đầu tiên chờ A kết thúc trước khi B được gửi. B chắc chắn chạy sau A.
- `newSingleThreadExecutor()` dùng một worker để tuần tự xử lý hai tác vụ trong ví dụ bình thường này; không có lỗi khiến worker bị thay thế.
- B **không hề set USER**, nhưng đọc được giá trị do A để lại. `USER` trên main thread vẫn là một slot khác; điều kiện rò rỉ nằm ở worker.
- Lỗi không cần `data race`, hai threads viết đồng thời hay biến static thông thường. Nó là sai vòng đời của **trạng thái gắn với thread**.

Nếu đổi pool thành nhiều workers, đừng viết bài kiểm tra “B luôn nhận alice” vì scheduling có thể đưa B sang thread khác. Một worker là cách minh họa quyết định được thứ tự và tái sử dụng.

## 4. Sửa căn bản: đóng vòng đời context bằng `try/finally`

Quy tắc chính: **ai cài đặt context phải có trách nhiệm kết thúc phạm vi đó**. Với điểm vào của một tác vụ trên worker, cài context đầu tác vụ và `remove()` trong `finally`. `finally` vẫn chạy khi code xử lý ném ngoại lệ thông thường, nên cleanup không phụ thuộc nhánh thành công.

Lưu thành **`ContextCleanupDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ContextCleanupDemo {
    private static final ThreadLocal<String> USER = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            pool.submit(() -> {
                USER.set("alice");
                try {
                    System.out.println("A user=" + USER.get());
                } finally {
                    USER.remove();
                }
            }).get();

            pool.submit(() -> System.out.println("B user=" + USER.get())).get();
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ContextCleanupDemo.java
java ContextCleanupDemo
```

Kết quả:

```text
A user=alice
B user=null
```

B không còn nhìn thấy Alice vì A xóa context trên chính worker mà A chạy. Trên ThreadLocal thông thường, `get()` trả `null` khi chưa có giá trị. Với `ThreadLocal.withInitial(...)`, sau `remove()`, lần `get()` tiếp theo **có thể gọi lại supplier để tạo giá trị mặc định**; vì vậy không được coi mọi `get() == null` là bằng chứng đã dọn sạch mọi loại ThreadLocal.

**Sai lầm thường gặp:**

```java
USER.set("alice");
performTask();
USER.remove();  // Bị bỏ qua khi performTask() ném exception.
```

Đoạn minh họa này không phải chương trình độc lập; `performTask()` là phương thức giả định. Dùng `try/finally`, và khi có nhiều ThreadLocals (USER, TENANT, TRACE), dọn **tất cả** những biến đã cài. `remove()` khác `set(null)`: `remove()` xóa mapping của thread hiện tại; `set(null)` vẫn là một phép gán với giá trị null và có thể ảnh hưởng hành vi `initialValue()` về sau.

**Có nên dọn đầu tác vụ?** Ở ranh giới worker không có ngữ cảnh hợp lệ cần giữ, dọn đầu tác vụ là *defense in depth* hữu ích để loại giá trị sót từ code cũ. Tuy nhiên nó không thay thế cleanup cuối tác vụ; chỉ xóa đầu mỗi job mà không dọn cuối sẽ giữ đối tượng trong khoảng worker rảnh, và những nhánh ngoài wrapper vẫn có thể bị ảnh hưởng.

## 5. Truyền context qua executor đúng cách

Dọn binding trên worker là một phần của giải pháp; **ThreadLocal của caller không tự truyền sang thread thực thi**. Khi cần ngữ cảnh ngầm trên executor, phải **capture một snapshot trước khi submit**, cài binding ở đầu task, sau đó cleanup hoặc restore trong **finally**.

~~~java
// Snippet minh họa: context đã được capture trên caller.
// CURRENT là ThreadLocal không có initializer.
Context previous = CURRENT.get();
CURRENT.set(snapshot);
try {
    work();
} finally {
    if (previous == null) CURRENT.remove();
    else CURRENT.set(previous);
}
~~~

Cách xử lý này đặc biệt quan trọng khi scope có thể lồng nhau: **remove** mọi lúc có thể làm mất binding bên ngoài. Nếu worker không có previous context hợp lệ, kết thúc task phải để lại worker sạch. Cần kiểm thử cả lỗi, hủy và nhiều task trên cùng worker để phát hiện rò rỉ.

Đoạn minh họa giả định **Context**, **CURRENT**, **snapshot**, **work()** thuộc ứng dụng; không phải chương trình Java độc lập. Thiết kế wrapper Runnable/Callable đầy đủ, phân biệt capture time và executor decoration được giảng ở bài **Truyền context qua Runnable, Callable và executor**.

## 6. Ngoại lệ, hủy tác vụ và tác vụ định kỳ

Rò rỉ thường xảy ra ở đường đi hiếm gặp:

- Code `return` sớm trước câu lệnh `remove()`.
- Lời gọi HTTP/database ném exception.
- `Future.get()` nhận `ExecutionException`, nhưng code task đã bỏ qua cleanup.
- Task bị interrupt khi đang blocking.
- Tác vụ hẹn giờ chạy đi chạy lại trên worker cũ.
- Pipeline tạo nhiều `Runnable`/`Callable` qua các lớp wrapper khác nhau và có lớp không dọn context.

Đặt cleanup ngay trong **`finally` của phần chạy trên worker**, không đặt ở caller sau `Future.get()`; caller và worker có hai slot ThreadLocal khác nhau. `ExecutorService.shutdown()` không tự xóa context của từng task trong suốt thời gian pool còn sống. Thread kết thúc thường cho phép các giá trị ThreadLocal được GC nếu không có reference khác, nhưng chờ thread kết thúc không thay thế cleanup.

Với tác vụ định kỳ (`ScheduledExecutorService.scheduleAtFixedRate` hoặc `scheduleWithFixedDelay`), mỗi lần callback được chạy phải bắt đầu trong context mong muốn và kết thúc bằng cleanup. Nếu một callback để lại trace ID, callback kế tiếp có thể ghi log vào trace cũ.

Với `CompletableFuture.supplyAsync` và các stage bất đồng bộ, không giả định chúng chạy trên caller thread hoặc giữ ThreadLocal của caller. Khi không truyền executor, stage async thường dùng `ForkJoinPool.commonPool()` theo hợp đồng Java trong điều kiện thích hợp; việc lựa chọn và tái sử dụng worker cũng làm context ngầm không đáng tin. Muốn truyền context cần ranh giới/cơ chế rõ ràng theo nơi stage thực thi.

## 7. `InheritableThreadLocal` không sửa được lỗi của thread pool

`InheritableThreadLocal<T>` chuyển giá trị khởi tạo từ parent thread sang child thread **lúc child thread được tạo**, không truyền giá trị theo mỗi lần `submit()`. Với pool, workers có thể được tạo sớm rồi xử lý vô số tasks về sau.

Ví dụ về mặt thời gian:

```text
Caller có context tenant=A
    → tạo worker W
    → W có thể kế thừa tenant=A

Caller chuyển context tenant=B
    → submit(B) cho worker W đã có sẵn
    → W KHÔNG tự kế thừa lại tenant=B
    → W có nguy cơ giữ tenant=A nếu chưa dọn
```

Ngoài ra, với mặc định `childValue`, child có thể nhận **cùng tham chiếu đối tượng** như parent. Nếu giá trị là object mutable, hai thread có thể thấy thay đổi qua cùng object. Dùng `InheritableThreadLocal` để “truyền request context tự động” qua executor là sai mô hình.

`ThreadLocal` thường không tự được kế thừa khi tạo thread. Còn `InheritableThreadLocal` vẫn phải có cleanup và kiểm soát thời điểm tạo thread. Đặc biệt không trộn cơ chế inheritance với bảo đảm nghiệp vụ “mỗi task nhận đúng context” nếu không xác minh rõ vòng đời worker.

## 8. Rò rỉ context và rò rỉ bộ nhớ: quan hệ nhưng khác nhau

Một `ThreadLocal` thường có thể được khai báo:

```java
private static final ThreadLocal<LargeContext> CONTEXT = new ThreadLocal<>();
```

Đây là khai báo minh họa; `LargeContext` cần được định nghĩa. Field static giữ `ThreadLocal` sống lâu. Nếu worker pool giữ `LargeContext` (ví dụ có bộ nhớ đệm lớn hoặc đồ thị object chứa request), context có thể sống lâu bằng worker nếu không `remove()`. Không có request nào sử dụng nó nữa cũng không có nghĩa GC thu hồi được.

Trong triển khai OpenJDK, `ThreadLocalMap` gắn với `Thread` dùng khóa tham chiếu yếu đến `ThreadLocal` nhưng giữ **tham chiếu mạnh đến giá trị**. Nếu code tạo nhiều ThreadLocal động rồi bỏ tham chiếu đến chính các key, một số entry với key đã bị GC có thể còn giữ value cho đến khi map thực hiện dọn entry tương ứng hoặc thread kết thúc. Không nên dựa vào GC hay cơ chế dọn nội bộ như cam kết tự động giải phóng đúng lúc. Chi tiết `ThreadLocalMap` thuộc triển khai JDK, không phải lời hứa API cho mọi JVM.

**Phân biệt rõ:**
- Một `ThreadLocal` static còn được tham chiếu và chứa value trên worker **không nhất thiết là memory leak vô hạn**; value vẫn giữ bộ nhớ ngoài ý muốn nếu không được xóa.
- Mỗi request tạo `new ThreadLocal<>()` động và quên dọn trên pool sống lâu có thể tạo áp lực bộ nhớ khó chẩn đoán hơn.
- Context leakage có thể gây lỗi bảo mật ngay cả với giá trị rất nhỏ (ví dụ chuỗi tenant ID), không cần tăng heap.

Do đó, biện pháp trực tiếp là quản lý vòng đời và giảm trạng thái ngầm; heap dump chỉ giúp tìm biểu hiện bộ nhớ, không thay thế kiểm tra logic context.

## 9. Kiểm thử lỗi và kiểm thử bản sửa

Test concurrency phải **đảm bảo tái sử dụng worker**, không dùng `Thread.sleep()` để “hy vọng” task A chạy trước task B. Một kịch bản kiểm thử quyết định được:

1. Tạo `Executors.newSingleThreadExecutor()`.
2. Submit A: cài `ThreadLocal`, chạy code cần kiểm thử.
3. `futureA.get()`: đợi A hoàn tất.
4. Submit B: không cấp context và đọc `ThreadLocal.get()`.
5. `futureB.get()`: xác nhận B thấy `null` (hoặc context mặc định hợp lệ), không thấy giá trị từ A.
6. Thử lại khi A ném exception để kiểm chứng `finally`.
7. Dừng pool trong `finally`; giữ các task được chờ rõ ràng.

Thử bổ sung khi có nhiều context fields (user/tenant/trace), khi request bị interrupt, khi có lời gọi lồng nhau, khi cùng executor chạy tasks được gửi từ hai caller khác nhau và khi context thật sự cần được propagate.

**Các assert quan trọng:** B không đọc dữ liệu của A; mọi nhánh lỗi đều dọn; thông tin truyền sang worker đúng snapshot; cleanup của worker không ảnh hưởng slot caller; thông tin phân quyền được kiểm chứng từ nguồn có thẩm quyền.

### Dấu hiệu khi vận hành

- Log của hai requests khác nhau xuất hiện cùng request ID/trace ID dù không liên quan.
- Một task không có user context lại ghi log hoặc lấy cấu hình theo user trước.
- Giá trị tenant hoặc locale “đổi” không giải thích được sau khi tăng tải.
- Số objects giữ bởi `ThreadLocalMap` của worker tăng trong heap dump.
- Lỗi chỉ xuất hiện trên một số worker và biến mất khi pool được tái tạo.

Khi điều tra, ghi nhận **thread name**, task ID và request ID bằng dữ liệu tối thiểu được phép log; không ghi credential hay dữ liệu nhạy cảm để chẩn đoán. Dùng `jcmd`, heap dump/Java Flight Recorder khi nghi vấn bộ nhớ, và thêm kiểm thử tuần tự trên cùng worker để xác định lỗi logic. Không kết luận từ thread name đơn lẻ rằng một context đã được propagate đúng.

## 10. Lưu ý về virtual threads

Từ Java 21, `Executors.newVirtualThreadPerTaskExecutor()` thường tạo **virtual thread mới cho mỗi task**, vì vậy kịch bản “hai tasks độc lập nối tiếp trên *cùng một virtual thread được pool tái sử dụng*” không xảy ra trong cách dùng đó. Tuy nhiên:

- `ThreadLocal` vẫn gắn với **virtual thread hiện tại** và vẫn cần vòng đời rõ ràng nếu task gọi code lồng nhau.
- ThreadLocal của caller không tự biến thành context của task đang chạy trên thread khác chỉ vì đó là virtual thread.
- Việc giữ dữ liệu lớn trong ThreadLocal của số lượng rất lớn virtual threads vẫn tiêu tốn bộ nhớ.
- Không chuyển sang virtual threads chỉ để che lỗi cleanup của code đang dùng pool, vì cả context lifecycle và cơ chế propagation vẫn cần được thiết kế đúng.

Bài học chính không phụ thuộc loại thread: **context dành cho một task phải được sở hữu và giải phóng theo vòng đời task**.

## 11. Checklist thiết kế để không rò rỉ context

| Câu hỏi | Quy tắc |
|---|---|
| Context thuộc request/task hay thread suốt đời? | Nếu thuộc task, không để giá trị tiếp tục sống trên worker khi task xong |
| Ai cài `ThreadLocal.set`? | Thành phần đó cần cleanup trong `finally` |
| Có task chạy trên thread khác? | Truyền context tường minh hoặc capture/install/cleanup đúng ranh giới |
| Có ngoại lệ, cancellation, timeout? | Kiểm thử đường lỗi và interruption; không bỏ qua `finally` |
| Có gọi lồng nhau tạm thay context? | Khôi phục giá trị của scope ngoài; phân biệt với cleanup ở điểm kết thúc task |
| Có nhiều `ThreadLocal`? | Cleanup tất cả slot đã thay đổi |
| Có `InheritableThreadLocal` trong pool? | Kiểm tra vì inheritance chỉ tại lúc thread được tạo |
| Giá trị context có mutable hoặc nặng? | Ưu tiên snapshot bất biến, không giữ object lớn qua vòng đời worker |
| Context được dùng để xác thực/phân quyền? | Kiểm tra quyền bằng dữ liệu có thẩm quyền; context không thay thế cơ chế authorization |
| Test có dựa vào may rủi scheduler? | Dùng một worker và `Future.get()` để chứng minh leak/cleanup xác định |

**Kết luận kỹ thuật:** `ThreadLocal` cung cấp trạng thái riêng cho *thread*, trong khi `ExecutorService` có thể dùng một *thread* chạy nhiều *task*. Nếu đồng nhất hai vòng đời, context của task A sẽ tồn tại khi task B bắt đầu. Cách khắc phục bền vững là chọn tham số tường minh khi khả thi, hoặc bao mỗi tác vụ bằng thao tác **capture → install → execute → cleanup** với `try/finally`; nơi có scope lồng nhau thì khôi phục context của scope ngoài một cách có chủ đích.

### Tự kiểm tra

1. Vì sao `newSingleThreadExecutor()` là cách hữu ích để tái hiện leak?
2. `ThreadLocal` có truyền `userId` từ thread submit sang worker không?
3. Hai requests chạy tuần tự trên cùng worker có thể bị context leakage mà không có data race không?
4. Vì sao đặt `remove()` sau lời gọi có thể ném exception vẫn chưa an toàn?
5. `InheritableThreadLocal` kế thừa lúc thread được tạo hay lúc mỗi task được submit?
6. Vì sao `remove()` khác `set(null)` khi dùng `withInitial(...)`?
7. Khi nào phải restore previous context thay vì remove?

**Đáp án định hướng:** (1) bảo đảm một worker được tái sử dụng; (2) không; (3) có; (4) exception bỏ qua cleanup; (5) lúc tạo thread; (6) remove làm lần get sau khởi tạo lại từ supplier; (7) lời gọi lồng nhau cần trở lại scope ngoài còn hợp lệ.

### Tài liệu tham khảo

- [Java SE 21 — `ThreadLocal` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html) — `get`, `set`, `remove`, `withInitial` và thời gian sống của giá trị.
- [Java SE 21 — `InheritableThreadLocal` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html) — kế thừa giá trị khi tạo child thread.
- [Java SE 21 — `Executors` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html) — tạo single/fixed thread pools và executor tương ứng.
- [Java SE 21 — `ExecutorService` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html) — quản lý nộp, chờ và kết thúc tác vụ.