# ThreadLocal: set(), get(), remove() trong Java

`ThreadLocal<T>` (gói `java.lang`) cho phép **cùng một biến ThreadLocal được các thread truy cập nhưng mỗi thread có một giá trị riêng**. Ba thao tác quan trọng nhất là `set(T value)` để đặt giá trị, `get()` để đọc giá trị và `remove()` để xóa giá trị **của thread hiện tại**. Đây là công cụ quản lý **ngữ cảnh luồng** trong Java concurrency, ví dụ correlation ID của lời gọi đồng bộ; bài này tập trung vào Java chuẩn, không đi vào các tính năng riêng của Spring.

## 1. Vấn đề mà ThreadLocal giải quyết

Giả sử hai thread xử lý hai công việc độc lập và mỗi thread cần mang một mã để log. Nếu lưu mã vào một biến `static String requestId` dùng chung, lệnh ghi ở thread A có thể ghi đè dữ liệu của B. Thêm `volatile` chỉ tăng bảo đảm nhìn thấy giá trị dùng chung, chứ **không tạo ra các giá trị độc lập theo thread**. Nếu mọi hàm đều nhận tham số `requestId` thì rất tường minh; tuy nhiên trong một số chuỗi lời gọi đồng bộ sâu, ThreadLocal giúp truyền ngữ cảnh **ngầm định trên cùng thread**.

```text
               Cùng một đối tượng ThreadLocal<String>
                       /                    \
                  Thread A                 Thread B
               set("A-100")             set("B-200")
                  get() -> A-100           get() -> B-200
```

Bản chất là mỗi thread có ánh xạ từ **đối tượng ThreadLocal** tới **giá trị của thread đó**. ThreadLocal không làm các tác vụ tự động an toàn; nó giúp tránh tranh chấp **vì từng thread đọc/ghi slot của chính mình**.

**Giới hạn:** Hai thread có thể cố ý hoặc vô tình `set()` cùng **một tham chiếu đến đối tượng mutable**. Khi đó dữ liệu bên trong đối tượng vẫn có thể bị truy cập đồng thời; ThreadLocal không tạo bản sao sâu và không thay thế khóa hay các kiểu atomic.

## 2. Khởi tạo và vòng đời

Hai cách khai báo phổ biến:

```java
private static final ThreadLocal<String> CURRENT_ID =
        new ThreadLocal<>();

private static final ThreadLocal<String> CURRENT_ID_WITH_DEFAULT =
        ThreadLocal.withInitial(() -> "UNKNOWN");
```

- Với `new ThreadLocal<>()`, phương thức `initialValue()` mặc định trả về `null`.
- `withInitial(Supplier)` cung cấp giá trị khởi tạo khi **một thread gọi `get()` lần đầu trong khi chưa có ánh xạ**.
- Có thể dùng `private static final` cho tham chiếu ThreadLocal chung của ứng dụng: `static final` giữ ổn định **khóa ThreadLocal**, không làm cho các giá trị của các thread trở thành một giá trị toàn cục.
- Mỗi thread giữ ánh xạ riêng cho đến khi thay bằng `set()`, xóa bằng `remove()` hoặc thread kết thúc (và dữ liệu không còn tham chiếu khác). Với worker thread sống lâu, ánh xạ có thể tồn tại qua nhiều tác vụ.

### `set(T value)`

```java
CURRENT_ID.set("request-1");
CURRENT_ID.set("request-2");
```

Lệnh `set()` sau ghi đè giá trị trước **trong thread đang thực thi**. Nếu thread chưa từng gọi `get()`, `set()` trực tiếp đặt giá trị, không cần gọi supplier khởi tạo. `set(null)` là lời gọi hợp lệ: ánh xạ vẫn có, nhưng giá trị được lưu là `null`.

### `get()`

`get()` trả về giá trị đã đặt qua `set()` hoặc giá trị đã được khởi tạo cho thread. Nếu chưa có ánh xạ, nó gọi `initialValue()` của ThreadLocal, lưu kết quả rồi trả về kết quả. Supplier của `withInitial` thường chỉ chạy khi cần khởi tạo một ánh xạ mới, **không chạy lại ở mỗi lần `get()`**.

Điều kiện `get() == null` không giúp xác định chính xác trạng thái của slot: đó có thể là giá trị khởi tạo mặc định `null`, hoặc giá trị được đặt rõ ràng bởi `set(null)`.

### `remove()`

```java
CURRENT_ID.remove();
```

`remove()` xóa ánh xạ của ThreadLocal **trên thread đang gọi**, không xóa slot của thread khác. Sau đó, `get()` ở thread đó có thể khởi tạo giá trị **lần nữa** theo `initialValue()` hoặc supplier của `withInitial`.

Điểm khác biệt cần nhớ:

| Thao tác | Ánh xạ trên thread hiện tại | Lần `get()` tiếp theo |
| --- | --- | --- |
| `set("A")` | Có, giá trị `"A"` | Trả `"A"` |
| `set(null)` | Có, giá trị `null` | Trả `null`, không khởi tạo lại |
| `remove()` | Không còn ánh xạ | Tạo ánh xạ mới từ `initialValue()` |
| `get()` khi chưa có ánh xạ | Sẽ có ánh xạ sau khi khởi tạo thành công | Trả giá trị đã khởi tạo |

Với `ThreadLocal.withInitial(() -> "UNKNOWN")`, chuỗi `get() -> set(null) -> get() -> remove() -> get()` lần lượt cho `"UNKNOWN"`, `null` rồi `"UNKNOWN"` ở các lời gọi `get()` tương ứng. Nếu supplier ném exception, việc khởi tạo không hoàn thành bình thường; lần đọc sau có thể thử lại.

## 3. Ví dụ chạy được với Java 17+: độc lập theo thread và nguy cơ rò ngữ cảnh

Ví dụ dưới dùng **một worker được tái sử dụng** để cho thấy lỗi thường gặp khi quên `remove()`. Task thứ nhất **cố ý** để lại dữ liệu; task thứ hai không đặt ID mà vẫn thấy ID cũ. Task thứ ba dọn và đọc lại giá trị mặc định. Main thread vẫn giữ một giá trị độc lập.

Tạo tệp `ThreadLocalDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadLocalDemo {
    private static final ThreadLocal<String> CONTEXT =
            ThreadLocal.withInitial(() -> "NONE");

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            System.out.println("main-initial=" + CONTEXT.get());
            CONTEXT.set("MAIN");
            System.out.println("main-set=" + CONTEXT.get());

            Future<String> first = executor.submit(() -> {
                CONTEXT.set("REQUEST-A");
                // Cố ý không remove để mô phỏng một lỗi.
                return CONTEXT.get();
            });
            System.out.println("worker-first=" + first.get());

            Future<String> leaked = executor.submit(CONTEXT::get);
            System.out.println("worker-leaked=" + leaked.get());

            Future<String> cleaned = executor.submit(() -> {
                CONTEXT.remove();
                return CONTEXT.get();
            });
            System.out.println("worker-after-remove=" + cleaned.get());
            System.out.println("main-still=" + CONTEXT.get());
        } finally {
            CONTEXT.remove();
            executor.shutdown();
        }

        System.out.println("main-after-remove=" + CONTEXT.get());
        CONTEXT.remove();
    }
}
```

Biên dịch và chạy:

```bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
```

Kết quả chuẩn:

```text
main-initial=NONE
main-set=MAIN
worker-first=REQUEST-A
worker-leaked=REQUEST-A
worker-after-remove=NONE
main-still=MAIN
main-after-remove=NONE
```

Giải thích theo thứ tự:

1. Main gọi `get()` khi chưa có dữ liệu, nhận `NONE`; sau `set("MAIN")` thì đọc thấy `MAIN`.
2. Worker thứ nhất trong executor nhận `REQUEST-A`. `Future.get()` chờ hoàn thành trước khi tác vụ kế tiếp được submit.
3. `newSingleThreadExecutor()` tái sử dụng cùng worker bình thường, nên tác vụ thứ hai đọc thấy `REQUEST-A` mặc dù nó là công việc mới. Đây là **rò rỉ ngữ cảnh giữa các tác vụ**, không phải trường hợp ThreadLocal tự chia sẻ giá trị giữa hai thread.
4. Tác vụ thứ ba gọi `remove()` rồi `get()`: supplier chạy lại và trả `NONE`.
5. Main vẫn giữ `MAIN`, vì thao tác trên worker không đụng tới slot main. Cuối chương trình main cũng `remove()`, nên lần `get()` kế tiếp lại nhận `NONE`.

Không dùng cách để sót dữ liệu ở task thứ nhất trong mã sản xuất; ví dụ chỉ dùng để **tái hiện và quan sát lỗi**.

## 4. Mẫu đúng: đặt ngữ cảnh, xử lý, dọn trong finally

Khi có một phạm vi đồng bộ rõ ràng, dùng `try/finally`:

```java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

static void runWithRequestId(String id) {
    REQUEST_ID.set(id);
    try {
        process();
    } finally {
        REQUEST_ID.remove();
    }
}

static void process() {
    System.out.println("id=" + REQUEST_ID.get());
}
```

Đây là **đoạn mã minh họa phải đặt trong một class**, không phải tệp chương trình có `main` độc lập. Khi `process()` ném exception hoặc có `return`, `finally` vẫn thực hiện dọn slot. Nơi tạo và **sở hữu phạm vi ngữ cảnh** nên chịu trách nhiệm dọn sau khi tất cả code cần ngữ cảnh đã xử lý xong.

Cần thiết kế đặc biệt nếu có **ngữ cảnh lồng nhau**. Ví dụ hàm A `set("outer")`, sau đó hàm B `set("inner")` trên cùng thread và gọi `remove()`; khi trở về A, `"outer"` **không tự phục hồi**. Nếu cần hỗ trợ nesting, hãy lưu giá trị cũ và khôi phục đúng hợp đồng, hoặc truyền context bằng tham số. Không dùng `remove()` ở mọi cấp rồi giả định nó hoạt động như stack.

Một lưu ý tương tự: `remove()` chỉ xóa tham chiếu trong ThreadLocal; nếu giá trị là connection, file, buffer hoặc đối tượng `AutoCloseable`, nó **không tự đóng tài nguyên**. Tài nguyên có vòng đời riêng, phải được đóng đúng nơi sở hữu.

## 5. ThreadLocal theo thread, không theo request hay task

Thread pool thường dùng lại cùng platform thread cho nhiều `Runnable`/`Callable`. Nếu `set()` mà quên `remove()`, dữ liệu cũ có thể bị đọc bởi tác vụ kế tiếp:

```text
Worker-1:
  Task A: set("Alice") -> dùng -> quên remove
  Task B: get() -> "Alice" [sai]
  Task B: remove()
  Task C: get() -> giá trị khởi tạo
```

Hậu quả có thể là correlation ID trong log sai, hành vi dựa vào danh tính/ngữ cảnh cũ, lộ dữ liệu qua công việc khác, hoặc giữ tham chiếu tới đối tượng lớn lâu hơn cần thiết. Vì thế, trong xử lý có executor, phải đặt và dọn ngữ cảnh **theo từng lần xử lý công việc**, kể cả khi task thất bại.

Một thread mới không mặc nhiên nhận giá trị ThreadLocal thường từ thread gửi task. Cụ thể:

```java
ThreadLocal<String> local = new ThreadLocal<>();
local.set("main");
Thread worker = new Thread(() -> {
    System.out.println(local.get()); // null trên thread mới
});
worker.start();
worker.join();
local.remove();
```

Đoạn trên **minh họa trong một phương thức có xử lý `InterruptedException`**, không phải chương trình đứng riêng. Nó in `null` vì `new ThreadLocal<>()` chưa có giá trị ở worker. Tương tự, các tác vụ chuyển qua một executor khác, `CompletableFuture` hoặc callback bất đồng bộ có thể chạy trên thread khác; **không thể giả định context tự đi theo tác vụ**.

Nếu cần truyền context, hãy ưu tiên truyền tham số rõ ràng. Trường hợp có yêu cầu thiết lập context trên worker, cần tạo wrapper đặt giá trị ngay trước phần xử lý, rồi xóa/khôi phục trong `finally`, đồng thời cân nhắc ngữ cảnh lồng nhau.

## 6. Phân biệt với InheritableThreadLocal

`InheritableThreadLocal` là một lớp con của ThreadLocal có cơ chế cho phép thread con nhận giá trị ban đầu từ thread cha **khi thread con được tạo**, theo cấu hình và ngữ nghĩa kế thừa của thread. Điều này không đồng nghĩa với chuyện mỗi task được submit sau này sẽ tự nhận đúng context của thread submit:

- Worker trong thread pool có thể đã được tạo trước khi yêu cầu hiện tại xuất hiện.
- Giá trị được kế thừa khi tạo thread không tự cập nhật theo các lần `set()` mới ở thread cha.
- Truyền cả đối tượng mutable theo tham chiếu có thể tạo thêm vấn đề chia sẻ dữ liệu.
- Với dữ liệu nhạy cảm, cần chủ động kiểm soát có cho phép thread con kế thừa hay không.

Vì thế, `InheritableThreadLocal` không phải giải pháp chung để truyền context theo từng task qua thread pool.

## 7. Bộ nhớ: tại sao remove() quan trọng?

Trên các triển khai OpenJDK thông dụng, cấu trúc nội bộ `ThreadLocalMap` dùng tham chiếu yếu đến **khóa ThreadLocal** và tham chiếu mạnh đến **giá trị**. Nếu đối tượng ThreadLocal không còn được tham chiếu mạnh, khóa có thể bị thu gom, nhưng giá trị trong entry cũ **có thể vẫn được giữ** cho đến khi cấu trúc map dọn entry hoặc thread kết thúc. Đây là một nguy cơ giữ bộ nhớ, không phải tuyên bố rằng quên `remove()` luôn tạo rò rỉ vĩnh viễn.

Nếu `ThreadLocal` là một trường `static final`, khóa còn tồn tại; song các **giá trị per-thread** của worker lâu sống cũng có thể tồn tại quá phạm vi của request/task. `remove()` trên chính thread đang giữ slot làm ngắn vòng đời tham chiếu đó. Nó không xóa slot ở thread khác, cũng không bảo đảm đối tượng bị GC ngay nếu còn tham chiếu ở nơi khác.

Một số thực hành giúp giảm rủi ro:

- Giữ dữ liệu ThreadLocal nhỏ, đúng mục đích (ví dụ chuỗi correlation ID); tránh giữ cả request object, cache lớn hoặc đồ thị đối tượng không cần thiết.
- Đặt `remove()` ở `finally` của ranh giới công việc, thay vì chờ executor shutdown.
- Đừng làm cache đối tượng mutable/đắt tiền theo thread nếu có số lượng thread lớn mà không đo bộ nhớ và lợi ích.
- Dùng profiler/heap dump khi nghi ngờ giữ bộ nhớ; chỉ quan sát tăng RAM chưa đủ để kết luận ThreadLocal là nguyên nhân.

## 8. ThreadLocal trên virtual threads

Java 21 giới thiệu virtual threads như tính năng chính thức. Virtual threads vẫn là `Thread`, nên `ThreadLocal` và ba phương thức `set()`, `get()`, `remove()` vẫn hoạt động. **Giá trị thuộc virtual thread**, không thuộc carrier platform thread; đổi carrier không làm context nhảy sang virtual thread khác.

Mô hình thường gặp là một virtual thread cho mỗi tác vụ. Vì có thể đồng thời có rất nhiều virtual threads, việc dùng ThreadLocal để **cache một đối tượng nặng cho từng thread** có thể tiêu tốn bộ nhớ lớn mà ít cơ hội tái sử dụng. Với ngữ cảnh nhỏ và vòng đời rõ ràng, nó vẫn có thể hữu ích. Luôn xem xét chi phí cấp phát, số lượng task và phương thức truyền context thích hợp với ứng dụng.

Không nên dùng ThreadLocal như cơ chế truyền context "xuyên" mọi bước bất đồng bộ: nếu code chuyển sang thread khác, vẫn cần phân tích ranh giới thực thi.

## 9. So sánh với các lựa chọn khác

| Yêu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Mang ID qua các lời gọi đồng bộ cùng thread | Tham số, hoặc ThreadLocal khi có lý do rõ | Tận dụng context của thread hiện tại; dọn sau công việc |
| Chia sẻ một bộ đếm giữa nhiều thread | `AtomicInteger`, khóa hoặc bộ đếm concurrent | ThreadLocal tạo bộ đếm riêng, không tự tổng hợp |
| Đặt dữ liệu riêng cho nhiều task dùng chung một worker | Truyền tham số hoặc đặt/dọn ThreadLocal từng task | Worker có thể tái sử dụng, nên context cũ có thể sót |
| Chuyển context từ thread submit sang task trên executor | Truyền context rõ ràng | ThreadLocal thường không tự lan truyền |
| Quản lý vòng đời connection, transaction, file | API quản lý tài nguyên chuyên biệt | ThreadLocal chỉ giữ tham chiếu; remove không thay close |
| Giữ cache lớn trong hàng triệu virtual threads | Thường tránh, cân nhắc thiết kế lại | Tạo nhiều bản sao và tăng tải bộ nhớ |

## 10. Những lỗi dễ mắc và checklist kiểm tra

1. **Quên `remove()`:** context của task trước có thể xuất hiện ở task sau trên cùng worker.
2. **Dùng `set(null)` thay `remove()`:** slot vẫn tồn tại; supplier của `withInitial` không được gọi lại.
3. **Cho rằng trường `static final` là một giá trị chung:** thực tế trường đó là **khóa chung** cho nhiều giá trị per-thread.
4. **Cho rằng ThreadLocal bảo vệ đối tượng mutable được chia sẻ:** nhiều thread vẫn có thể cùng giữ một tham chiếu và gây data race.
5. **Dựa vào context tự lan sang executor:** thread đích không mặc nhiên có slot cùng giá trị của thread nguồn.
6. **Gọi `remove()` ở cấp lồng nhau mà không khôi phục:** làm mất ngữ cảnh của người gọi bên ngoài.
7. **Chỉ thử với một task:** rất dễ bỏ qua lỗi vì cần task khác tái sử dụng đúng worker mới quan sát được.
8. **Dùng remove để thay đóng tài nguyên:** tham chiếu bị xóa nhưng tài nguyên không tự giải phóng.

Trước khi dùng ThreadLocal, hãy trả lời: **giá trị thuộc thread nào, ai đặt, ai dọn, thread có được tái sử dụng không, và có ranh giới bất đồng bộ hay ngữ cảnh lồng nhau không?**

Ghi nhớ: `set()` lưu cho **thread hiện tại**, `get()` đọc/khởi tạo cho **thread hiện tại**, `remove()` xóa ánh xạ của **thread hiện tại**. ThreadLocal thuận tiện cho một số ngữ cảnh đồng bộ, nhưng vòng đời theo **thread** đòi hỏi dọn dẹp cẩn thận khi xử lý nhiều tác vụ.

## Tài liệu tham khảo

- [Java SE 21 API: ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html) — đặc tả `get()`, `set()`, `remove()`, `withInitial()` và `initialValue()`.
- [Java SE 21 API: InheritableThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html) — ngữ nghĩa kế thừa giá trị khi tạo thread con.
- [Oracle Java 21 Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) — ThreadLocal với virtual threads và lưu ý về cache theo thread.
