# Chuyển thông tin thất bại qua ranh giới luồng bằng kết quả có quản lý

## 1. Vì sao ứng dụng đa luồng cần một kết quả có quản lý?

Khi một phương thức gọi trực tiếp phương thức khác trên **cùng luồng**, ngoại lệ có thể lan theo call stack đến `catch` của người gọi. Nhưng khi công việc được giao sang luồng khác, mỗi luồng có call stack riêng: một exception ném trong worker **không tự động được ném vào `try-catch` đang bao quanh thao tác gửi việc** ở luồng điều phối.

Vì vậy, nếu người gọi cần biết công việc cuối cùng thành công hay thất bại, hệ thống phải có **kênh chuyển thông tin giữa các luồng**. Trong Java Core, hai công cụ thường dùng là:

- **`Future<T>`**: một tay nắm (*handle*) đại diện cho kết quả của công việc chưa chắc hoàn tất. `Future.get()` chờ và thu giá trị hoặc báo thất bại.
- **`CompletableFuture<T>`**: một future có thể hoàn thành từ code và có thể nối thành nhiều giai đoạn bất đồng bộ; cung cấp cách xử lý, biến đổi và tổng hợp cả kết quả lẫn thất bại.

Một kết quả có quản lý thường cần thể hiện ba lớp thông tin riêng:

1. **Trạng thái vòng đời**: đang chờ, đang chạy, đã hoàn thành, hoàn thành lỗi, hay bị hủy.
2. **Kết quả nghiệp vụ**: tìm thấy/không tìm thấy; được chấp nhận/từ chối; các trạng thái mà ứng dụng *dự kiến*.
3. **Lỗi thực thi**: `IOException`, exception bất thường do lập trình, timeout, mất kết nối hoặc lỗi tài nguyên khiến việc tính toán không hoàn tất như kế hoạch.

Không nên đánh đồng “`Future.isDone() == true`” với “đã thành công”; không nên coi mọi exception là một giá trị nghiệp vụ “không tìm thấy”; cũng không nên hiểu “caller đã catch lỗi từ Future” là mọi tác động của worker tự hoàn tác.

Mục tiêu của bài là thiết kế một đường đi rõ ràng: **gửi công việc → nhận handle → hoàn thành thành công hoặc thất bại → quan sát kết quả ở ranh giới luồng → ra quyết định**.

## 2. Ranh giới luồng thay đổi đường đi của exception

Sơ đồ:

~~~text
Luồng điều phối A                         Luồng worker B
--------------------------               --------------------------
try {                                    chạy task
    future = executor.submit(task);  ->       xử lý dữ liệu
    // submit trả về handle                    throw IOException
} catch (...) {                               |
    // lỗi của thao tác submit                 v
}                                          Future ghi nhận failure
           |
           v
future.get()  <-----------------------   task hoàn tất
    |
    +-- trả T
    +-- ExecutionException(cause)
    +-- InterruptedException
    +-- CancellationException
~~~

`submit` nhận việc và có thể trả trước khi worker bắt đầu. `catch` quanh `submit` có thể bắt lỗi phát sinh **ngay tại lệnh gửi việc**, như `RejectedExecutionException` nếu executor từ chối; nó không tự nhận exception phát sinh **sau này trong task**.

Khi dùng `ExecutorService.submit(Callable<T>)`, exception thoát khỏi `call()` thường được ghi lại trong đối tượng `Future`. Người gọi lấy được nó khi gọi `get()`: Java bọc nguyên nhân của task trong `ExecutionException`. Đây chính là cách chuyển lỗi **qua ranh giới luồng bằng một đối tượng có quản lý**, thay vì cố ném ngược qua call stack không còn liên quan.

### 2.1. `Thread.join()` không thay `Future.get()`

`Thread.join()` chỉ đợi thread kết thúc. Nó không có kết quả trả về của `Runnable.run()` và không ném lại exception không được bắt của worker. Khi cần lấy kết quả hoặc lỗi có kiểu, `Future` thường phù hợp hơn một `Thread` tự tạo.

Một thread con có thể được cài `UncaughtExceptionHandler` để ghi nhận lỗi không bắt được, nhưng handler phục vụ cơ chế xử lý lỗi của chính thread đó. Handler không tự gửi giá trị thành công về caller, không cung cấp trạng thái cancellation/timeout như Future và không được xem là một lời hứa “task thành công” hay “task đã rollback”.

## 3. Phân biệt kết quả nghiệp vụ, exception và trạng thái điều phối

Ba nhóm này dẫn tới hành động khác nhau:

| Tình huống | Bản chất | Biểu diễn thường hợp lý | Hành động caller |
| --- | --- | --- | --- |
| Có dữ liệu | Thành công nghiệp vụ | `Found(value)` | Dùng giá trị |
| Mã hợp lệ nhưng không có dữ liệu | Kết cục bình thường được dự kiến | `Absent(id)` hoặc `Optional<T>` bên trong `Future` | Hiển thị không tìm thấy |
| Quy tắc nghiệp vụ từ chối | Kết cục dự kiến với nguyên nhân có kiểu | `Rejected(code, details)` | Yêu cầu sửa dữ liệu/quy trình |
| Lỗi I/O mà API dự kiến báo có cấu trúc | Thất bại thực thi đã được phân loại | `Failed(code, cause)` trong một result type | Retry/ghi nhận/báo lỗi theo code |
| Worker ném exception không xử lý | Thất bại bất thường của tác vụ | `ExecutionException` hoặc completion ngoại lệ | Xem `cause`, không giả thành vắng mặt |
| Caller hết thời gian đợi | Trạng thái điều phối: chưa có kết quả trong hạn | `TimeoutException` từ `get(timeout, ...)` | Xác định tiếp tục chờ/hủy/tra trạng thái |
| Task bị hủy | Trạng thái vòng đời | `CancellationException`, `isCancelled()` | Chấp nhận hủy theo chính sách |
| Luồng đang đợi bị interrupt | Tín hiệu điều phối nhắm vào luồng chờ | `InterruptedException` | Truyền tiếp hoặc khôi phục cờ interrupt |

Bởi vậy, chữ ký `Future<Optional<Product>>` có thể hợp lý khi tìm kiếm có thể trả về rỗng nhưng vẫn muốn exception thật truyền qua `get()`. Nếu có nhiều trạng thái nghiệp vụ, `Future<SearchResult>` với sealed result type thường dễ diễn đạt hơn. Nếu muốn **chuyển lỗi I/O thành giá trị có kiểu**, một nhánh `Failed` có thể lưu mã lỗi ổn định và nguyên nhân; tuy nhiên code phải chuyển đổi **có chủ đích**, không dùng `catch (Throwable)` để nuốt mọi lỗi của JVM.

Quy tắc quan trọng: **`Future<T>` quản lý việc hoàn thành; `T` nói lên dữ liệu thành công hoặc các kết cục nghiệp vụ của thao tác.** Thực hiện phân loại ở đúng tầng giúp caller biết phải làm gì.

## 4. `Callable<T>` và `Future<T>`: nền tảng của kết quả có quản lý

`Runnable.run()` không có giá trị trả về và không khai báo checked exception. `Callable<T>.call()` trả về `T` và có thể khai báo `throws Exception`. Do đó, khi công việc cần trả kết quả hoặc báo lỗi, `Callable` kết hợp `submit` là một lựa chọn tự nhiên.

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();

try {
    Future<Integer> future = executor.submit(() -> 20 + 22);
    System.out.println(future.get());
} finally {
    executor.shutdown();
}
~~~

Đây là **fragment minh họa**, giả định đã import `ExecutorService`, `Executors`, `Future` và phương thức chứa đoạn mã khai báo hoặc xử lý `InterruptedException`, `ExecutionException`. Khi chạy trong môi trường phù hợp, giá trị từ `get()` là `42`. `submit` chỉ trả handle; `get` mới chờ và thu kết quả. `finally` ở đây có nhiệm vụ gọi `shutdown()` để không tiếp tục nhận việc mới; nếu chương trình yêu cầu chờ toàn bộ task kết thúc thì cần thêm chiến lược chờ và dọn riêng.

### 4.1. Những trạng thái quan trọng của Future

| API | Ý nghĩa chính | Điều không nên suy diễn |
| --- | --- | --- |
| `get()` | Đợi đến khi có kết quả, task lỗi hoặc bị hủy; có thể bị interrupt | Không phải lời hứa task sẽ không bao giờ treo |
| `get(timeout, unit)` | Đợi có giới hạn rồi có thể ném `TimeoutException` | Hết hạn không đồng nghĩa task đã dừng |
| `isDone()` | Task hoàn tất theo trạng thái Future, kể cả lỗi/hủy | `true` không đồng nghĩa thành công |
| `isCancelled()` | Future đã bị hủy | Không bảo đảm mọi side effect đã được hoàn tác |
| `cancel(false)` | Cố hủy; không yêu cầu interrupt nếu đang chạy | Không cam kết chặn task đang thực thi |
| `cancel(true)` | Cố hủy, có thể yêu cầu interrupt worker đang chạy | Không ép tác vụ không hợp tác phải dừng ngay |

`ExecutionException` là **vỏ bọc**, không phải nguyên nhân gốc: `getCause()` thường trả exception được worker ném ra. `InterruptedException` lại thuộc **luồng đang đợi**. Khi nhận nó, hãy chọn một chính sách rõ: truyền tiếp hoặc gọi lại `Thread.currentThread().interrupt()` nếu không thể truyền checked exception lên tầng trên. Không xử lý nó giống như `ExecutionException` của worker.

`get(timeout, unit)` có thể làm caller trả về nhanh, nhưng job vẫn có thể tiếp tục ghi dữ liệu. Nếu timeout dẫn đến retry một thao tác có side effect, hệ thống phải suy xét idempotency hoặc truy vấn trạng thái. Không biến timeout thành “task chắc chắn thất bại và không làm gì”.

### 4.2. Thông tin lỗi cần đi kèm nguyên nhân

Bắt exception để chuyển sang trạng thái có kiểu:

~~~java
Callable<SearchResult> task = () -> {
    try {
        return readFromRepository();
    } catch (IOException e) {
        return new Failed("P01", FailureCode.STORAGE, e);
    }
};
~~~

Đây là **mã minh họa không độc lập**, vì `SearchResult`, `Failed`, `FailureCode` và `readFromRepository` chưa được định nghĩa trong fragment. Chủ ý là phân loại `IOException` thành mã ổn định `STORAGE` và giữ `cause` để chẩn đoán. Tránh bắt mọi `Throwable` rồi trả `Failed("UNKNOWN")`, bởi hành động đó có thể che lỗi nghiêm trọng, làm hỏng trạng thái hoặc khiến caller tưởng một lỗi lập trình là lỗi nghiệp vụ đã được lường trước.

Nếu chính API quyết định rằng lỗi đọc dữ liệu phải được lan qua `ExecutionException`, không cần catch `IOException` trong Callable: cứ để `call() throws Exception` phát sinh lỗi. Cả hai cách đều khả thi; quan trọng là hợp đồng phải **nhất quán và rõ cho caller**.

## 5. Ví dụ Java 17 hoàn chỉnh: quản lý kết quả từ nhiều worker

Chương trình sau dùng một `ExecutorService` hai thread. Bốn tác vụ được gửi cùng lúc:

- `A` trả dữ liệu thành công.
- `N` được tra cứu hợp lệ nhưng không tồn tại.
- `IO` gây `IOException` và được adapter công việc chuyển thành `Failed(STORAGE)`.
- `BUG` mô phỏng invariant bị phá vỡ và được giữ ở kênh exceptional completion của `Future`, không bị giả thành mã “không có dữ liệu”.

Sau đó một `CompletableFuture` minh họa cách **chuyển completion ngoại lệ thành một giá trị `Failed` có kiểu** tại ranh giới `handle`.

Lưu toàn bộ mã bên dưới thành **`ManagedThreadResultDemo.java`**:

~~~java
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ManagedThreadResultDemo {
    sealed interface SearchResult permits Found, Absent, Failed {}

    record Found(String id, String value) implements SearchResult {}
    record Absent(String id) implements SearchResult {}
    record Failed(String id, FailureCode code, Throwable cause)
            implements SearchResult {}

    enum FailureCode { STORAGE, UNEXPECTED }

    static SearchResult lookup(String id) throws IOException {
        return switch (id) {
            case "A" -> new Found(id, "alpha");
            case "N" -> new Absent(id);
            case "IO" -> throw new IOException("storage unavailable");
            case "BUG" -> throw new IllegalStateException("broken invariant");
            default -> new Absent(id);
        };
    }

    static Callable<SearchResult> managed(String id) {
        return () -> {
            try {
                return lookup(id);
            } catch (IOException e) {
                return new Failed(id, FailureCode.STORAGE, e);
            }
        };
    }

    static Throwable unwrapCompletion(Throwable error) {
        while (error instanceof CompletionException && error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }

    static String display(SearchResult result) {
        if (result instanceof Found found) {
            return "FOUND " + found.id() + "=" + found.value();
        }
        if (result instanceof Absent absent) {
            return "ABSENT " + absent.id();
        }
        if (result instanceof Failed failed) {
            return "FAILED " + failed.id() + "=" + failed.code();
        }
        throw new IllegalStateException("Unknown result");
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Future<SearchResult>> futures = new ArrayList<>();
            for (String id : List.of("A", "N", "IO", "BUG")) {
                futures.add(pool.submit(managed(id)));
            }
            for (int i = 0; i < futures.size(); i++) {
                try {
                    System.out.println(display(futures.get(i).get()));
                } catch (ExecutionException e) {
                    System.out.println("UNEXPECTED " + e.getCause()
                            .getClass().getSimpleName());
                }
            }

            CompletableFuture<SearchResult> async =
                    CompletableFuture.<SearchResult>supplyAsync(() -> {
                        throw new IllegalArgumentException("async defect");
                    }, pool).handle((value, error) -> {
                        if (error == null) {
                            return value;
                        }
                        return new Failed("ASYNC", FailureCode.UNEXPECTED,
                                unwrapCompletion(error));
                    });
            System.out.println(display(async.join()));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Dùng JDK 17 trở lên, đứng trong thư mục chứa file:

~~~bash
javac --release 17 ManagedThreadResultDemo.java
java ManagedThreadResultDemo
~~~

**Stdout chính xác:**

~~~text
FOUND A=alpha
ABSENT N
FAILED IO=STORAGE
UNEXPECTED IllegalStateException
FAILED ASYNC=UNEXPECTED
~~~

### 5.1. Giải thích vì sao output có thứ tự cố định

Các task trong nhóm đầu có thể **thực thi và hoàn tất theo thứ tự bất kỳ** trên hai worker. Nhưng vòng lặp duyệt `List<Future<SearchResult>>` theo thứ tự đã gửi và gọi `get()` từng future, vì vậy **thứ tự các dòng in** là A, N, IO, BUG dù thời điểm thực thi thực tế khác nhau. Nếu thay bằng callback in trực tiếp trên từng worker, thứ tự in có thể khác. Sau vòng lặp, chương trình mới tạo stage `CompletableFuture` và đợi `join()` trước khi in dòng cuối.

- `Found A=alpha`: task trả `Found` bình thường; `Future.get()` trả `SearchResult`.
- `Absent N`: tra cứu trả `Absent`, là một **kết cục thành công về mặt thực thi** nhưng không có bản ghi.
- `Failed IO=STORAGE`: task bắt chính xác `IOException`, giữ exception gốc trong `cause` và trả một kết quả đã phân loại. `get()` không ném `ExecutionException` vì Callable đã hoàn thành bằng việc **trả giá trị**.
- `UNEXPECTED IllegalStateException`: `managed` không bắt `IllegalStateException` của `lookup("BUG")`. Future hoàn thành lỗi; `get()` ném `ExecutionException` và caller đọc `getCause()`.
- `Failed ASYNC=UNEXPECTED`: `CompletableFuture.supplyAsync` hoàn thành ngoại lệ, `handle` tạo `Failed` chứa mã lỗi và nguyên nhân đã tháo lớp bọc `CompletionException`. Stage **mới** vì thế hoàn thành bình thường với đối tượng `Failed`.

Ví dụ giữ `Throwable cause` **trong kiểu kết quả nội bộ** để tiện chẩn đoán; khi chuyển thành REST response, log sự kiện hay thông báo người dùng, cần cung cấp **mã lỗi an toàn**, tránh tuần tự hóa stack trace, file path hoặc thông tin nhạy cảm ra ngoài. Mã `STORAGE` và `UNEXPECTED` là minh họa chính sách; ứng dụng thực có thể dùng enum chi tiết hơn, ví dụ `TEMPORARY_UNAVAILABLE`, `PERMISSION_DENIED` hay `NOT_RECOVERABLE` nếu caller thực sự cần phân biệt.

### 5.2. Vì sao không bắt mọi exception để luôn trả `Failed`?

Ta có thể thiết kế một `Result<T,E>` gom tất cả exception ứng dụng vào nhánh lỗi, nhưng phải xét nguyên nhân và ranh giới. Trong ví dụ, lỗi I/O dự kiến được chuyển thành `Failed(STORAGE)`, trong khi `IllegalStateException` mô phỏng invariant bị phá vỡ được giữ là exceptional completion để không bị che giấu.

Ở ranh giới **điều phối công việc** hoặc **giao tiếp ngoài hệ thống**, có thể cần chuyển một số exception chưa xử lý thành kết quả có kiểu để trả lời caller. Khi đó phải phân loại, log và giữ nguyên nhân phù hợp, không lặng lẽ biến thành “không tìm thấy” hoặc “thành công”. Java không bắt buộc mọi kiểu lỗi phải đi theo cùng một kênh.

### 5.3. Vì sao kết quả dùng `sealed interface` và `record`?

`sealed interface SearchResult` liệt kê những kiểu triển khai được cho phép: `Found`, `Absent`, `Failed`. Mỗi `record` mang trường riêng: giá trị khi tìm thấy, khóa không tìm thấy, hoặc mã và nguyên nhân lỗi khi thất bại. Đây là các tính năng ổn định trong Java 17.

`display` dùng `instanceof` pattern matching để đọc dữ liệu của từng loại. `switch` pattern matching trên sealed type là preview ở Java 17, do đó ví dụ không cần bật tính năng preview khi biên dịch. Chữ ký `Future<SearchResult>` cho phép caller xử lý các kết quả có cấu trúc, nhưng **không miễn trừ** `ExecutionException` hoặc cancellation ở lớp Future.

## 6. Chọn nơi chuyển exception thành dữ liệu

Có hai hợp đồng phổ biến:

**Hợp đồng A — lỗi thực thi vẫn là exceptional completion:**

~~~java
Future<String> future = executor.submit(() -> remoteRead());
String value = future.get(); // Có thể ném ExecutionException.
~~~

Đoạn minh họa giả định `executor`, `remoteRead()` và các checked exception đã được khai báo/bắt. Cách này phù hợp khi exception thực thi là một phần kênh lỗi tiêu chuẩn, và tầng gọi có chính sách xử lý thống nhất.

**Hợp đồng B — một số kết cục được chuyển thành `Result` có kiểu:**

~~~java
Future<LoadResult> future = executor.submit(() -> {
    try {
        return new Loaded(remoteRead());
    } catch (IOException e) {
        return new LoadFailed("STORAGE", e);
    }
});
~~~

Fragment giả định `LoadResult`, `Loaded`, `LoadFailed`, `remoteRead` và `executor` đã tồn tại. Ở đây `get()` có thể trả `LoadFailed` bình thường; các exception không được catch vẫn có thể dẫn tới `ExecutionException`.

Cần phân biệt **hoàn thành bình thường của Future** với **thành công nghiệp vụ**: một `Future<Result>` trả về `Failure` không phải exception ở kênh Future, nhưng nghiệp vụ vẫn thất bại và phải được caller xử lý. Nếu monitoring chỉ đếm số task hoàn thành ngoại lệ, nó có thể bỏ qua rất nhiều result mang `Failure`; phải thiết kế metric theo cả hai lớp trạng thái.

Đừng vô ý dùng hai cách biểu diễn **cùng một lỗi** ở những API ngang cấp mà không có quy tắc, vì caller sẽ không biết khi nào đọc nhánh `Failed` và khi nào bắt `ExecutionException`.

## 7. `CompletableFuture`: quản lý cả chuỗi bất đồng bộ

`CompletableFuture<T>` mở rộng ý tưởng handle: thay vì chỉ chờ kết quả cuối, caller có thể định nghĩa các stage kế tiếp.

| API | Ý nghĩa khi upstream thành công | Khi upstream thất bại |
| --- | --- | --- |
| `thenApply(fn)` | Áp dụng chuyển đổi đồng bộ theo cơ chế completion stage | Không gọi `fn`; stage kết quả thất bại |
| `thenCompose(fn)` | Nối stage phụ thuộc khác, tránh lồng `CompletableFuture<CompletableFuture<T>>` | Không gọi `fn`; lỗi được truyền |
| `thenCombine(other, fn)` | Kết hợp giá trị từ hai stage đã hoàn thành bình thường | Nếu một stage thất bại, kết quả có thể hoàn thành ngoại lệ |
| `exceptionally(fn)` | Giữ giá trị gốc | Cho phép tạo giá trị thay thế từ lỗi |
| `handle((value,error) -> result)` | Thấy giá trị và có thể biến đổi | Thấy lỗi và có thể biến đổi thành giá trị |
| `whenComplete((value,error) -> action)` | Thực hiện hành động quan sát | Thấy lỗi; tự nó không phải cơ chế bảo đảm phục hồi |
| `get()` | Trả giá trị khi hoàn thành | Checked `ExecutionException` (hoặc cancellation), có thể bị interrupt |
| `join()` | Trả giá trị khi hoàn thành | Unchecked `CompletionException` (hoặc cancellation) |

Một stage có thể được hoàn thành bởi worker, bởi thread thực hiện completion của stage trước hoặc bởi executor được truyền rõ ràng, tùy API. **Không giả định callback luôn chạy trên thread đã tạo CompletableFuture.** Đối với các biến thể `...Async` không có executor tường minh, Java sử dụng cơ chế executor mặc định được mô tả bởi API; trong hệ thống cần quản lý tài nguyên, nên truyền executor thích hợp và nêu rõ người sở hữu việc shutdown.

### 7.1. `handle` là chuyển đổi có chủ đích, không phải phép chữa lỗi tự động

Ví dụ:

~~~java
CompletableFuture<String> raw = CompletableFuture.supplyAsync(
        () -> {
            throw new IllegalStateException("remote request failed");
        });

CompletableFuture<String> recovered =
        raw.exceptionally(error -> "fallback");
~~~

Fragment có thể đặt trong phương thức đã import `CompletableFuture`. `raw` hoàn thành ngoại lệ; `recovered` là stage mới có thể hoàn thành bình thường với chuỗi `fallback`. Chỉ dùng fallback nếu nghiệp vụ thật sự cho phép. Với dữ liệu quan trọng, chuyển lỗi thành một giá trị giả “thành công” có thể che việc chưa thực hiện được tác vụ.

Một cách khác là chuyển thành result có kiểu:

~~~java
CompletableFuture<Outcome> observed =
        raw.handle((value, error) ->
                error == null
                        ? new Success(value)
                        : new FailedOutcome(error));
~~~

Đây là fragment minh họa, giả định `Outcome`, `Success` và `FailedOutcome` được định nghĩa; các nhánh này cần có chung kiểu phù hợp. `handle` quan sát cả hai trạng thái và tạo kết quả tường minh, thay vì phải phân tích chuỗi thông báo để xem có lỗi hay không.

### 7.2. `whenComplete` dành cho quan sát, cần giữ lỗi

`whenComplete` thường phù hợp để ghi metric, log hoặc cleanup có kiểm soát:

~~~java
CompletableFuture<String> withObservation =
        raw.whenComplete((value, error) -> {
            if (error != null) {
                recordFailure(error);
            }
        });
~~~

Fragment giả định `recordFailure`. Stage `withObservation` vẫn mang kết quả/lỗi theo quy tắc `whenComplete`; callback này **không mặc định biến lỗi thành thành công**. Không dùng `whenComplete` rồi bỏ qua future kết quả nếu caller còn cần bảo đảm thất bại đã được xử lý.

Đặc biệt, callback quan sát có thể ném exception của chính nó. Nếu upstream đã lỗi, hành vi chọn exception nào được truyền sẽ theo hợp đồng CompletionStage; vì vậy callback ghi log/metric nên gọn, không tạo thêm tác động phụ nguy hiểm và không thay thế quy trình xử lý kết quả chính.

### 7.3. Ghép nhiều stage và kết quả tổng hợp

`CompletableFuture.allOf(f1, f2, ...)` trả `CompletableFuture<Void>` hoàn thành sau khi các future thành phần hoàn thành. Nếu có stage thất bại, `allOf` hoàn thành ngoại lệ; nó **không trả danh sách giá trị**, cũng không tự tạo báo cáo tổng hợp đầy đủ của từng future. Nếu cần phân biệt lỗi của từng task, phải quan sát từng future hoặc chuyển từng stage sang một giá trị `Outcome` trước khi tổng hợp.

`CompletableFuture.anyOf(...)` hoàn thành theo một stage thành phần hoàn tất, kể cả hoàn thành ngoại lệ; không đồng nghĩa chọn “stage thành công đầu tiên”. Chỉ dùng khi đó đúng là hợp đồng cần thiết.

Ví dụ phân loại từng stage trước `allOf`:

~~~java
CompletableFuture<Outcome> a = serviceA()
        .handle((value, error) -> classify("A", value, error));
CompletableFuture<Outcome> b = serviceB()
        .handle((value, error) -> classify("B", value, error));

CompletableFuture<Void> all = CompletableFuture.allOf(a, b);
all.join();
Outcome first = a.join();
Outcome second = b.join();
~~~

Đây là **pseudocode gần Java**, các hàm `serviceA`, `serviceB`, `classify` và `Outcome` chưa khai báo, đồng thời kiểu generic cần được thống nhất trong code thật. Ý tưởng là mỗi stage có một kênh trạng thái có kiểu, sau đó tổng hợp sau điểm đồng bộ. Không nên chỉ gọi `all.join()` rồi suy ra tất cả đã thành công về mặt nghiệp vụ.

## 8. Hoàn thành ngoại lệ và bóc lớp nguyên nhân

Trong `CompletableFuture`, các cách kích hoạt/quan sát lỗi gồm:

- Worker hoặc callback ném exception: stage có thể hoàn thành ngoại lệ.
- Code chủ động gọi `completeExceptionally(error)`: thử hoàn thành một CompletableFuture đang chưa được hoàn thành bằng lỗi đã cho.
- `join()`: thông thường báo exceptional completion qua unchecked `CompletionException`; hủy có thể qua `CancellationException`.
- `get()`: báo thất bại qua checked `ExecutionException`; caller còn cần xử lý `InterruptedException`.
- `isCompletedExceptionally()`: kiểm tra future đã hoàn thành ngoại lệ, nhưng không trả nguyên nhân cụ thể.

Một future không thể hoàn thành thành công và thất bại cùng lúc; chỉ một trạng thái terminal thắng cuộc cạnh tranh hoàn thành. `complete(value)` và `completeExceptionally(error)` trả boolean chỉ việc lời gọi có làm future chuyển sang hoàn tất thành công hay không. Không dùng hai lệnh này như cách “ghi đè” kết quả đã hoàn thành.

### 8.1. Không dựa vào đúng một lớp `CompletionException`

Trong callback, đối số lỗi có thể đã được bọc bằng `CompletionException` hoặc kiểu khác tùy cách kết thúc stage. Đừng gọi `error.getCause().getMessage()` vô điều kiện, vì `getCause()` có thể `null`. Khi cần chuẩn hóa exception ở tầng nội bộ, có thể tháo các lớp bọc được biết trước và giữ reference tới lỗi gốc.

~~~java
static Throwable unwrapCompletion(Throwable error) {
    while (error instanceof CompletionException && error.getCause() != null) {
        error = error.getCause();
    }
    return error;
}
~~~

Phương thức minh họa này chính là hàm đã dùng trong `ManagedThreadResultDemo`. Nó chỉ tháo `CompletionException` và tránh mất cause khi cause là `null`. Không nên tháo mọi wrapper theo một quy tắc mù quáng: một exception bọc có thể mang thông tin ngữ cảnh quan trọng. Khi log, thường cần cả thông tin ngữ cảnh của wrapper và chuỗi cause gốc.

### 8.2. Exception gốc và lỗi nghiệp vụ có cấu trúc là hai lớp khác nhau

Một result có kiểu nên chứa **mã lỗi ổn định** cho quyết định của caller. `cause` nên phục vụ phân tích và log nội bộ, không phải API để client phân tích chuỗi `getMessage()`. Ví dụ mã `STORAGE_UNAVAILABLE` cho phép chọn retry theo chính sách; thông điệp chi tiết “connection refused” không phải hợp đồng lâu dài.

Khi nhiều tác vụ lỗi, cần gắn **taskId/correlationId** trước khi tổng hợp để biết lỗi thuộc tác vụ nào; nếu chỉ giữ một `Throwable` cuối cùng, các lỗi trước có thể bị mất. Đối với API bên ngoài, tránh lộ stack trace, đường dẫn file, thông tin người dùng hay token trong result.

## 9. Timeout, interruption và cancellation phải được báo đúng

Các trạng thái này thường bị trộn lẫn với “worker đã ném exception”. Thực tế:

| Tín hiệu | Phát sinh tại | Kết luận đúng |
| --- | --- | --- |
| `ExecutionException` | `Future.get()` của caller | Task hoàn thành bằng exception; xét `getCause()` |
| `CompletionException` | `CompletableFuture.join()` hoặc stage | Stage hoàn thành ngoại lệ; xét cause |
| `TimeoutException` | `Future.get(timeout, unit)` hoặc thao tác chờ giới hạn khác | Caller chưa có kết quả trong thời hạn |
| `InterruptedException` | Thread đang chờ trên `get`, `join` của Thread hay blocking API phù hợp | Luồng chờ bị interrupt; không kết luận worker thất bại |
| `CancellationException` | Gọi lấy kết quả một future đã hủy | Công việc ở trạng thái hủy theo hợp đồng Future |
| `RejectedExecutionException` | Lệnh gửi việc tới executor không chấp nhận | Công việc chưa được chấp nhận tại lời gọi gửi đó |

Mẫu xử lý một `Future` có timeout:

~~~java
try {
    Outcome result = future.get(2, TimeUnit.SECONDS);
    handleResult(result);
} catch (TimeoutException e) {
    reportStillPending();
    future.cancel(true); // Chỉ nếu chính sách cho phép yêu cầu hủy.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException e) {
    reportFailure(e.getCause());
} catch (CancellationException e) {
    reportCancelled();
}
~~~

Đây là **fragment minh họa**, giả định `future`, `Outcome`, các hàm xử lý, import tương ứng, và phương thức bên ngoài trả `void`. `cancel(true)` chỉ yêu cầu hủy/có thể interrupt worker theo trạng thái task; task không hợp tác có thể tiếp tục tác động bên ngoài. Nếu caller không sở hữu task, **không tự ý cancel** công việc dùng chung khi chỉ một người gọi hết thời gian chờ.

Một `CompletableFuture.orTimeout(...)` có thể hoàn thành chính CompletableFuture ngoại lệ với `TimeoutException` sau thời hạn, nhưng **không tự chứng minh công việc nguồn đã dừng**. `completeOnTimeout(value, ...)` đặt giá trị dự phòng nếu chưa hoàn tất kịp, cũng không tự hủy hoạt động bên ngoài đang chạy. Vì các phương thức này có thể hoàn thành trên future nhận lệnh, cần suy nghĩ kỹ trước khi áp dụng lên future dùng chung ở nhiều caller.

### 9.1. Xử lý `InterruptedException` đúng cách

Nhiều blocking API xóa cờ interrupt khi ném `InterruptedException`. Nếu bạn bắt và không thể ném tiếp, thông thường gọi `Thread.currentThread().interrupt()` rồi kết thúc/trao quyền cho tầng trên. **Không** làm:

~~~java
try {
    future.get();
} catch (InterruptedException ignored) {
    // Nuốt yêu cầu ngắt, tiếp tục vô hạn.
}
~~~

Fragment này cố tình là anti-pattern và chưa xử lý checked exception khác từ `get()`. Nếu cứ nuốt interrupt, quy trình shutdown/hủy có thể không hoạt động như kỳ vọng.

Nếu task phải dừng khi bị interrupt, code task cũng phải **hợp tác**: kiểm tra `Thread.currentThread().isInterrupted()` ở các vòng lặp dài, xử lý `InterruptedException` từ chờ/sleep phù hợp và không âm thầm tiếp tục làm việc sau yêu cầu hủy.

## 10. Quyền sở hữu executor và kết quả: ai đảm bảo task được quan sát?

Giao việc bất đồng bộ tạo ra trách nhiệm quản lý. Nếu hệ thống dùng `ExecutorService`, cần xác định rõ **ai tạo executor, ai shutdown, ai chờ, ai chịu trách nhiệm xử lý thất bại**.

Một quy trình có thể như sau:

~~~text
Request/Coordinator
    |
    +-- cấp taskId và correlationId
    |
    +-- submit -> nhận Future<T>
    |
    +-- lưu/giữ handle đến khi có người xử lý
    |
    +-- get()/callback/tổng hợp kết quả
    |        |
    |        +-- Success
    |        +-- Business outcome
    |        +-- Execution failure
    |        +-- Cancel/timeout
    |
    +-- ghi nhận trạng thái và phản hồi phù hợp
    |
    +-- release handle và tài nguyên theo chính sách
~~~

Không được **fire-and-forget** một task quan trọng rồi coi như thành công nếu không có cơ chế ghi nhận. Ví dụ:

~~~java
executor.submit(() -> sendNotification(orderId));
return "sent";
~~~

Fragment giả định `executor`, `sendNotification`, `orderId` tồn tại. Nó chỉ chứng minh việc `submit` đã được gọi và không ném ngay; không chứng minh thông báo đã gửi. Một `Future` bị vứt bỏ có thể chứa exception không được đọc. Nếu muốn phản hồi ngay, trạng thái nên là “đã tiếp nhận” hoặc “đang xử lý”, đi kèm job ID và phương thức tra kết quả về sau.

### 10.1. `shutdown()` không giống “đã xong hết”

`ExecutorService.shutdown()` bắt đầu đóng executor theo trình tự: không nhận task mới, các task đã gửi vẫn có thể đang chạy. `shutdownNow()` cố dừng task đang hoạt động và trả danh sách task đang đợi, nhưng không bảo đảm chúng đều đã dừng. `awaitTermination(timeout, unit)` chờ executor chấm dứt trong giới hạn; nó không khẳng định mỗi task thành công.

Java 17 `ExecutorService` chưa có cơ chế `close()` như các phiên bản Java mới hơn; sử dụng `shutdown` và các phương thức chờ/hủy theo vòng đời ứng dụng là mẫu phù hợp. Trong ví dụ chạy độc lập, tất cả future đã được `get/join` trước `shutdown`, nên không còn task nào đang chạy khi tới cuối đường thành công. Trong ứng dụng server, executor thường được sở hữu ở tầng dài hạn và shutdown khi ứng dụng dừng, thay vì tạo/đóng cho từng request.

### 10.2. `Future` không phải storage bền vững

`Future` và `CompletableFuture` là những đối tượng trong bộ nhớ tiến trình JVM. Nếu process chết, object Future biến mất; nó **không phải hàng đợi bền vững** và không cung cấp khả năng phục hồi sau crash. Công việc có hậu quả kinh doanh cần sống qua restart có thể cần trạng thái job lưu DB, hàng đợi bền vững, outbox, mã idempotency và quy trình retry/đối soát tùy yêu cầu.

“Có một handle Future” chỉ giải quyết cách quan sát **khi process và đối tượng còn sống**. Nó không biến nhiều side effect thành một transaction. Task có thể đã ghi file hoặc gửi HTTP request rồi mới hoàn thành lỗi; kể cả caller đã nhận `ExecutionException` hoặc `Failed` thì những tác động trước đó vẫn có thể tồn tại.

## 11. Khi nào chuyển thành Result, khi nào giữ exception?

Một hợp đồng API dễ dùng thường phân nhóm:

- **Trạng thái nghiệp vụ dự kiến:** trả result có kiểu như `Found`, `Absent`, `Rejected` với thông tin đủ để caller xử lý. Những nhánh này có thể là một phần `T` của `Future<T>`.
- **Lỗi kỹ thuật được API có chủ đích phân loại:** chuyển thành `Failed(ErrorCode, cause)` nếu tầng gọi cần quyết định retry, báo lỗi, thống kê hoặc phục hồi dựa trên mã.
- **Lỗi bất thường/invariant hỏng:** có thể để task hoàn thành ngoại lệ và báo điều phối; không tự động biến mọi loại lỗi thành giá trị dữ liệu thông thường.
- **Timeout/cancellation/interruption:** thuộc **hợp đồng điều phối** và cần xử lý tách biệt với các nhánh nghiệp vụ.
- **Hệ thống dừng/crash:** có thể không nhận được kết quả của Future; cần quản lý trạng thái bền vững nếu tính năng yêu cầu.

Tùy API, một kiểu `Result<T, E>` tổng quát cũng có thể hữu ích. `E` nên là enum/record/sealed hierarchy có cấu trúc, tránh một chuỗi thông điệp tự do khiến caller phải `contains("timeout")` hoặc `contains("database")` để quyết định. Không cần đưa `Future<Result<Optional<T>>>` vào mọi chỗ nếu chính nghiệp vụ chỉ có hai trạng thái đơn giản và caller đã có kênh exceptional completion.

### 11.1. Quyết định ở ranh giới lớp

| Tầng | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Task/worker | Làm công việc, xử lý lỗi có thể khôi phục tại chỗ | Bắt một lỗi I/O cụ thể, có chính sách retry hữu hạn |
| Adapter gửi việc | Tạo task, gắn mã, chọn executor, quản lý handle | `submit(Callable<Result>)` |
| Coordinator | Đợi/tổng hợp/đọc kết quả, phân biệt trạng thái, quyết định hủy | `get()` / callback `handle` |
| API boundary | Ánh xạ trạng thái sang giao diện/HTTP/message, bảo vệ thông tin lỗi | Trả mã lỗi có kiểu, không lộ stack trace |
| Hạ tầng bền vững khi cần | Lưu trạng thái job, retry và chống lặp qua process restart | Database/outbox/job store |

Không nhất thiết mỗi ứng dụng có tất cả các tầng. Điều cần có là một **chủ sở hữu rõ ràng** của kết quả cuối, để thất bại không biến thành một stack trace bị bỏ qua.

## 12. Quan sát nhiều kết quả: đủ lỗi, đúng thứ tự và không rò task

Khi gửi nhiều việc, một lỗi ở một task **không tự hủy những task còn lại**. Nếu các task độc lập, có thể chờ tất cả rồi tổng hợp mọi `Outcome`. Nếu task thất bại khiến kết quả chung vô nghĩa, coordinator có thể hủy task còn lại theo chính sách; cần hiểu mức độ hợp tác của cancellation và những side effect đã xảy ra.

Các điểm quan trọng:
1. **Thứ tự hoàn tất khác thứ tự nộp việc.** Duyệt danh sách Future rồi `get()` theo thứ tự gửi tạo thứ tự đọc có dự đoán được, nhưng có thể chặn trên task đầu dù task sau xong sớm.
2. **Một task lỗi không chứng minh task khác chưa chạy.** Nếu task khác đã gửi email, việc thu lỗi không thu hồi email.
3. **`Future.isDone()` không đủ để phân loại.** Muốn biết kết cục, gọi `get`/đọc result. Nếu future bị hủy thì cần xử lý riêng.
4. **Một stage `allOf` lỗi không cung cấp toàn bộ lỗi theo dạng danh sách.** Muốn báo cáo từng task thì biến từng stage thành `Outcome` hoặc truy vấn từng future.
5. **Thời hạn phải có ý nghĩa ở cấp công việc chung.** Nếu mỗi `get` dùng timeout 5 giây cho 20 task theo thứ tự, thời gian tổng có thể vượt quá deadline mong muốn; thiết kế một deadline tổng thay vì dùng timeout rời rạc khi yêu cầu chung là “kết thúc trong 5 giây”.
6. **Khả năng quan sát:** ghi metric số tác vụ thành công, vắng mặt, thất bại nghiệp vụ, exception, timeout, bị hủy một cách tách biệt.

Nếu ứng dụng phải thu **tất cả** thất bại, không bỏ qua Future còn lại chỉ vì `get` của Future đầu tiên ném `ExecutionException`; hãy tạo báo cáo tổng hợp theo chính sách, đồng thời giới hạn thời gian và tài nguyên hợp lý.

## 13. Lỗi thiết kế thường gặp

### 13.1. `try-catch` chỉ bao quanh `submit`

~~~java
try {
    executor.submit(() -> failingOperation());
} catch (Exception e) {
    logError(e);
}
~~~

Đây là fragment giả định các biến/hàm đã tồn tại. `catch` này có thể nhận lỗi xảy ra trực tiếp khi gửi task, chứ **không tự bắt exception phát sinh sau đó trong worker**. Nếu muốn quan sát task, giữ Future và đọc `get()` hoặc đăng ký stage callback phù hợp.

### 13.2. Bỏ Future và trả thông điệp thành công

~~~java
executor.submit(() -> writeImportantFile());
return true;
~~~

Fragment giả định một phương thức trả boolean và các hàm liên quan. `true` này chỉ là kết luận thiếu chứng cứ: công việc có thể chưa chạy. Trả một job handle/trạng thái accepted; hoặc chờ/nhận kết quả rồi mới xác nhận thực sự thành công.

### 13.3. Trả `Optional.empty()` cho mọi exception

~~~java
try {
    return repository.findById(id);
} catch (RuntimeException ignored) {
    return Optional.empty();
}
~~~

Fragment giả định repository trả Optional. Việc không có bản ghi hoàn toàn khác với việc **không biết kết quả vì truy vấn thất bại**. Cần truyền exceptional completion hoặc một nhánh lỗi có kiểu, giữ cause.

### 13.4. Biến mọi `Failed` thành thành công sau `handle`

Nếu `handle` luôn trả `"ok"` sau một exception, stage kết quả có thể hoàn thành bình thường và metric ở Future chỉ nhìn thấy success. Chính sách recovery phải được định nghĩa; giá trị `Failed(code)` vẫn cần được thống kê là thất bại nghiệp vụ/kỹ thuật.

### 13.5. Bắt `InterruptedException` rồi im lặng

Nuốt interrupt khiến hủy/shutdown khó hoạt động. Truyền tiếp hoặc khôi phục cờ interrupt và kết thúc xử lý theo hợp đồng. `InterruptedException` của caller không thay thế việc kiểm tra task có thật sự dừng hay chưa.

### 13.6. Dùng `getCause()` mà không bảo vệ giả định

Với lỗi từ hệ thống khác nhau, wrapper/cause có thể không có cấu trúc như kỳ vọng. Đừng gọi `cause.getMessage()` khi cause có thể `null`; ghi nhận loại wrapper và fallback phù hợp. Không bịa loại lỗi hoặc coi message text là mã lỗi ổn định.

### 13.7. Không có chính sách kết thúc executor

Một pool tạo ra rồi bị quên có thể giữ thread sống và tiêu thụ tài nguyên. Một executor dùng chung bị shutdown bởi code của một request lại có thể làm hỏng những request khác. Ranh giới sở hữu executor cần được xác định khi thiết kế, không chỉ khi test.

## 14. Kiểm thử đường đi của kết quả qua ranh giới luồng

Một bộ test đáng tin cần kiểm thử **cả kết quả trả về và các trạng thái điều phối**, thay vì chỉ bắt đúng một exception:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Callable trả `Found` | `get()` trả giá trị chính xác |
| Callable trả `Absent` | Future hoàn thành bình thường; caller phân loại vắng mặt |
| Callable bắt `IOException` và trả `Failed` | `get()` trả `Failed(STORAGE)`, cause được lưu nội bộ |
| Callable để lọt `IllegalStateException` | `get()` ném `ExecutionException`, cause đúng loại |
| Stage `CompletableFuture` thất bại | `join()` ném `CompletionException` khi chưa phục hồi |
| Stage `handle` chuyển lỗi thành `Failed` | `join()` trả result có kiểu, mã lỗi và cause phù hợp |
| Future chưa xong đến deadline | `get(timeout, ...)` ném `TimeoutException`; task không bị mặc định coi là đã dừng |
| Caller đang chờ bị interrupt | Chính sách phục hồi cờ/lan truyền interrupt đúng |
| Future đã bị hủy | `isCancelled()` đúng, `get()` có thể ném `CancellationException` |
| Nhiều Future có một task lỗi | Không bỏ mất trạng thái/lỗi của các task khác |
| Executor shutdown trong lúc có công việc | Không gửi việc mới; xử lý việc đã chấp nhận theo hợp đồng |
| Worker có side effect rồi lỗi | Kết quả báo thất bại đúng, nhưng không giả định side effect đã rollback |

Để test concurrency ổn định, dùng `CountDownLatch` hoặc future có timeout để điều phối các điểm mốc. Đừng dựa vào `Thread.sleep(100)` rồi đoán task chắc chắn đã hoàn thành. Với kiểm thử lỗi, có thể dùng dependency giả ném exception trước/sau khi ghi state; từ đó khẳng định chính xác điều hệ thống đã làm.

Nếu kiểm thử dùng executor riêng, giải phóng executor sau test; nếu task bị hủy và không hợp tác interrupt, cần thiết kế test có thể kết thúc mà không rò thread. Các bài test về retry hoặc side effect phải kiểm tra tình huống **server đã xử lý nhưng phản hồi bị mất**, không chỉ server từ chối ngay.

## 15. Checklist khi phát triển API bất đồng bộ có quản lý

- [ ] Công việc được gửi qua API rõ ràng; caller biết khi nào chỉ là **accepted** và khi nào là **completed**.
- [ ] Có handle/kênh thông báo kết quả; không mặc định `try-catch` quanh `submit` bắt lỗi worker.
- [ ] Kết quả nghiệp vụ dự kiến có kiểu rõ ràng, không trộn với exceptional completion.
- [ ] Lỗi I/O/technical được phân loại theo hợp đồng; không đổi lỗi thành `Optional.empty()`.
- [ ] `ExecutionException` và `CompletionException` được xử lý qua cause; không suy đoán chỉ từ message.
- [ ] `TimeoutException`, `InterruptedException` và `CancellationException` có chính sách riêng.
- [ ] Callback `handle`/`exceptionally` chỉ chuyển lỗi thành giá trị khi có quyết định recovery rõ ràng.
- [ ] Mọi Future quan trọng được quan sát hoặc có người sở hữu xử lý; không bỏ qua lỗi bị lưu trong Future.
- [ ] Executor có vòng đời và người sở hữu việc shutdown.
- [ ] Thống kê failure bao gồm cả `Result.Failed` lẫn exceptional completion.
- [ ] Side effect đã phát sinh trước thất bại được quản lý bằng transaction/idempotency hoặc quy trình phục hồi khi cần.
- [ ] Kiểm thử thành công, thất bại nghiệp vụ, lỗi bất thường, timeout, hủy và interruption trong môi trường có điều phối.

### Bài tập thực hành

Thiết kế API `loadProfiles(List<String> ids)` dùng `ExecutorService` để xử lý nhiều mã người dùng. Với mỗi mã, thao tác có thể trả: dữ liệu hồ sơ, không tìm thấy, hoặc lỗi I/O có thể thử lại. Một mã khác cố tình gây `IllegalStateException`.

1. Định nghĩa kiểu kết quả cho dữ liệu đã đọc, vắng mặt và thất bại có mã lỗi; quyết định exception nào nên tiếp tục truyền qua `Future.get()`.
2. Gửi bốn task song song rồi tổng hợp mọi kết quả theo thứ tự đầu vào. Không bỏ những Future chưa quan sát chỉ vì một task thất bại.
3. Áp dụng một deadline chung cho toàn bộ công việc; chỉ hủy khi chính sách và quyền sở hữu cho phép.
4. Viết lại dùng `CompletableFuture`; chuyển mỗi stage sang kết quả có kiểu trước khi tổng hợp bằng `allOf`.
5. Tạo test mô phỏng task ghi một phần dữ liệu rồi ném exception. Giải thích vì sao thu được `Failed` hoặc `ExecutionException` vẫn **không tự hoàn tác** tác động trước lỗi.

**Kết luận kỹ thuật:** ranh giới luồng tách rời call stack; để chuyển thất bại, caller cần một giao thức kết quả có quản lý. `Future`/`CompletableFuture` mang trạng thái hoàn thành và lỗi xuyên các luồng, còn kiểu kết quả của ứng dụng làm rõ những kết cục nghiệp vụ. Hai lớp đó phải được xử lý tường minh và nhất quán.