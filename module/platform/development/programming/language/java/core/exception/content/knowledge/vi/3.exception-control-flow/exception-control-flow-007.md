# Ngoại lệ chưa được bắt và việc kết thúc luồng hiện tại trong Java

Một ngoại lệ (exception) được xem là **chưa được bắt** (*uncaught exception*) đối với một luồng thực thi khi nó lan truyền qua toàn bộ các lời gọi đang hoạt động của luồng mà **không gặp một `catch` phù hợp**. Trong một `Thread` Java thông thường, ngoại lệ thoát khỏi điểm bắt đầu thực thi của thread sẽ kích hoạt cơ chế báo lỗi chưa được bắt và **thread đó kết thúc**.

Điểm cốt lõi phải phân biệt:

- **Ngoại lệ chưa được bắt trong một thread** có thể chấm dứt **thread đang chạy**.
- **Kết thúc một thread** không đồng nghĩa với việc **mọi thread khác** hoặc **toàn bộ tiến trình JVM** lập tức dừng.
- **Nơi kết thúc thread** khác với **nơi báo lỗi**: một `UncaughtExceptionHandler` có thể ghi nhận sự cố, nhưng nó không đưa thread quay lại câu lệnh đã thất bại.
- Với `ExecutorService.submit()`, ngoại lệ của tác vụ có thể được **lưu trong `Future`** và được báo về người gọi qua `Future.get()`. Vì thế không được suy diễn rằng mọi ngoại lệ phát sinh trong tác vụ luôn thoát tới uncaught handler của thread.

Bài học này giải thích đường đi của ngoại lệ, thời điểm kết thúc luồng, cơ chế handler, ảnh hưởng tới ứng dụng và cách chủ động đặt ranh giới xử lý đúng.

## 1. Thế nào là “chưa được bắt”?

Xét một lời gọi:

```java
static int parseAge(String raw) {
    return Integer.parseInt(raw);
}

static void process(String raw) {
    int age = parseAge(raw);
    System.out.println("Tuổi: " + age);
}
```

Đây là **hai phương thức minh họa**, cần đặt trong một lớp Java. Nếu gọi `process("abc")`, `Integer.parseInt` ném `NumberFormatException`. Phương thức `parseAge` không có handler phù hợp nên ngoại lệ truyền ra `process`. `process` cũng không có handler nên dòng `println` không chạy. Ngoại lệ tiếp tục đi lên những lời gọi còn hoạt động.

Có hai khả năng:

1. Một caller bao quanh lời gọi bằng `try-catch` tương thích, ví dụ `catch (NumberFormatException ex)`. Ngoại lệ được bắt ở đó và chương trình có thể thực hiện chính sách phục hồi hay phản hồi lỗi.
2. Không có handler phù hợp nào trên đường thực thi. Ngoại lệ thoát ra khỏi điểm bắt đầu của thread; đây là **uncaught exception** đối với thread đó.

Không nên gọi một ngoại lệ là “uncaught” chỉ vì phương thức phát sinh không có `catch`. Nó vẫn có thể được caller ở tầng trên bắt; lúc ấy nó **đã được xử lý**, không dẫn đến kết thúc thread vì chính ngoại lệ đó.

### Đường lan truyền trên ngăn xếp gọi

```text
Thread đang chạy
  run() hoặc main()
    └── handleRequest()
          └── execute()
                └── parse()
                      └── throw NumberFormatException
                             ↓
                   parse() không có catch
                             ↓
                   execute() không có catch
                             ↓
                   handleRequest() không có catch
                             ↓
             run()/main() không có catch phù hợp
                             ↓
                Uncaught exception
                             ↓
               Thread kết thúc
```

Khi lan truyền, các lời gọi đang hoạt động bị **kết thúc bất thường** (*abrupt completion*). Các câu lệnh nằm sau điểm gọi thất bại không tự chạy tiếp. JVM thực hiện các bước tháo ngăn xếp (*stack unwinding*), trong đó những khối `finally` có hiệu lực và thao tác dọn tài nguyên theo `try-with-resources` được thực hiện theo quy tắc Java.

## 2. Thread nào kết thúc khi không có `catch`?

Mỗi `Thread` có ngăn xếp lời gọi riêng. Một ngoại lệ chưa được bắt sẽ kết thúc **thread mà lỗi thoát ra**, chứ không tự động truyền sang ngăn xếp gọi của thread khác.

Ví dụ:

- Nếu `main` gọi trực tiếp một phương thức ném ngoại lệ mà không bắt, ngoại lệ có thể thoát khỏi **main thread**.
- Nếu một `Thread` tự tạo thực thi `Runnable.run()` và lỗi thoát khỏi `run()`, **worker thread đó** kết thúc.
- Nếu thread A đã gọi `worker.start()` để tạo thread B, ngoại lệ xảy ra ở B **không tự động bị ném ngược vào A**. `start()` chỉ khởi động công việc; nó không biến B thành một lời gọi đồng bộ trong stack của A.
- Nếu A gọi `worker.join()` để đợi B kết thúc, `join()` **không tự ném lại ngoại lệ đã làm B chết**. `join()` có thể ném `InterruptedException` khi chính A bị ngắt trong lúc chờ, nhưng đó là một cơ chế khác.

Đối với một `Thread` đã kết thúc, trạng thái cuối cùng là `Thread.State.TERMINATED`. Bạn **không thể gọi `start()` lần thứ hai trên cùng đối tượng `Thread`**; hành vi đó gây `IllegalThreadStateException`. Muốn chạy công việc lại, cần tạo một thread/tác vụ mới hoặc thiết kế cơ chế retry rõ ràng.

### JVM có dừng khi main thread chết?

**Không phải lúc nào cũng vậy.** Trong một chương trình Java thông thường, JVM sẽ kết thúc khi không còn thread **non-daemon** nào đang sống (bên cạnh các cách dừng tiến trình khác như `System.exit`). Vì vậy:

- Nếu main thread có ngoại lệ chưa bắt và **không còn non-daemon thread khác**, tiến trình thường kết thúc.
- Nếu một non-daemon worker khác vẫn đang chạy, việc main thread kết thúc **không tự động làm worker đó chết**. Tiến trình có thể còn tiếp tục.
- Daemon thread **không tự giữ JVM tiếp tục chạy** khi mọi non-daemon thread đã kết thúc. Vì thế không nên dựa vào daemon thread để hoàn thành công việc quan trọng lúc ứng dụng đóng.

Cần tách ba khái niệm: **thất bại của một tác vụ**, **kết thúc một thread**, và **kết thúc JVM/process**. Chúng có thể liên quan nhưng không đồng nhất.

## 3. Ví dụ Java 17+: worker lỗi, main vẫn tiếp tục

Để quan sát kết quả một cách **ổn định, không phụ thuộc định dạng stack trace của JVM**, ta gắn một `UncaughtExceptionHandler` cho worker. Handler chỉ in thông tin xác định rồi để thread kết thúc.

Lưu toàn bộ chương trình thành **`UncaughtThreadDemo.java`**:

```java
public class UncaughtThreadDemo {

    static void doWork() {
        System.out.println("worker: bắt đầu");
        throw new IllegalStateException("không xử lý được dữ liệu");
    }

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
                UncaughtThreadDemo::doWork, "job-worker");

        worker.setUncaughtExceptionHandler((thread, error) -> {
            System.out.println(
                    "handler: " + thread.getName()
                    + " -> " + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
        });

        System.out.println("main: khởi động worker");
        worker.start();
        worker.join();

        System.out.println("main: worker còn sống = " + worker.isAlive());
        System.out.println("main: tiếp tục sau join");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 UncaughtThreadDemo.java
java UncaughtThreadDemo
```

**Stdout chính xác trong lần chạy bình thường, không có thread khác ngắt main:**

```text
main: khởi động worker
worker: bắt đầu
handler: job-worker -> IllegalStateException: không xử lý được dữ liệu
main: worker còn sống = false
main: tiếp tục sau join
```

### Diễn biến từng bước

1. Main thread tạo một đối tượng `Thread` có tên `job-worker` và gắn handler riêng bằng `setUncaughtExceptionHandler`.
2. Main in `"main: khởi động worker"` **trước** khi gọi `worker.start()`. Vì thế dòng đó xuất hiện trước dòng đầu tiên của worker.
3. Worker bắt đầu thực thi `doWork()`, in `"worker: bắt đầu"` rồi ném `IllegalStateException`.
4. Không có `catch` nào trên đường thoát của worker, nên cơ chế uncaught-exception gọi handler được gắn với thread này. Handler chạy **trong chính worker đang gặp sự cố**, in tên thread, tên lớp ngoại lệ và thông điệp.
5. Sau khi quá trình kết thúc của worker hoàn tất, `worker.join()` ở main trả về. Lúc ấy `worker.isAlive()` là `false`.
6. Main vẫn tiếp tục in dòng cuối: lỗi của worker không tự động nhảy vào `main` thành một ngoại lệ mới.

Handler **không sửa được stack đang thất bại**: sau khi handler chạy xong, worker không quay lại `doWork()` để chạy câu lệnh tiếp theo. Nếu cần thử lại, hãy đặt logic retry tại tầng điều phối và tạo nhiệm vụ mới với giới hạn/sự kiểm soát phù hợp.

## 4. Khi không gắn handler riêng: mặc định điều gì xảy ra?

Mỗi thread có thể có `Thread.UncaughtExceptionHandler` riêng. Khi một thread chuẩn bị kết thúc vì ngoại lệ chưa bắt, JVM chuyển thông tin thread và `Throwable` cho handler được xác định theo cơ chế của `Thread`.

Có ba cách thường gặp:

- **Handler riêng của thread:** đặt bằng `thread.setUncaughtExceptionHandler(handler)`.
- **Handler mặc định cấp ứng dụng:** đặt bằng `Thread.setDefaultUncaughtExceptionHandler(handler)`, có tác dụng như một điểm quan sát chung khi được cơ chế lựa chọn handler sử dụng.
- **`ThreadGroup` / hành vi mặc định:** nếu thread không có handler riêng, nhóm thread thực hiện cơ chế ủy quyền; khi không có default handler khác, triển khai Java chuẩn thường báo ngoại lệ và stack trace lên `System.err` (trừ trường hợp đặc biệt như `ThreadDeath`).

Trong môi trường phát triển phổ biến, nếu main thread ném một `IllegalStateException` không được bắt, stderr có dạng:

```text
Exception in thread "main" java.lang.IllegalStateException: ...
    at Example.someMethod(Example.java:...)
    at Example.main(Example.java:...)
```

Đây là **mẫu minh họa**, không phải output cố định: tên file, số dòng, stack trace, định dạng và nội dung thông điệp phụ thuộc mã thực tế và môi trường. Có handler tùy chỉnh thì đầu ra cũng có thể khác hoàn toàn.

### Cách đọc phần thông báo mặc định

- `Exception in thread "main"`: tên thread có ngoại lệ thoát ra.
- `java.lang.IllegalStateException`: **kiểu thực tế** của ngoại lệ.
- Phần sau dấu hai chấm: thông điệp nếu có.
- Các dòng `at ...`: đường gọi tại thời điểm stack trace được ghi; chúng gợi ý điểm phát sinh và các caller.
- Các đoạn `Caused by: ...` (nếu có): chuỗi nguyên nhân được truyền bằng `Throwable.getCause()` hoặc constructor nhận `cause`.

**Stack trace giúp chẩn đoán, nhưng không phải một API phân loại lỗi ổn định bằng chuỗi.** Không nên xây logic nghiệp vụ dựa trên việc tìm tên phương thức hoặc thông điệp trong stderr.

## 5. `UncaughtExceptionHandler` có thể và không thể làm gì?

Một handler được đăng ký bằng:

```java
thread.setUncaughtExceptionHandler((currentThread, error) -> {
    // Ghi log, đếm số tác vụ thất bại, gửi tín hiệu nội bộ...
});
```

Đây là **đoạn minh họa**; biến `thread` phải là một đối tượng `Thread` đã được tạo.

Handler nhận:

- `currentThread`: thread đang kết thúc vì lỗi.
- `error`: đối tượng `Throwable` chưa được bắt, có kiểu, message, cause và stack trace để chẩn đoán.

Những việc thường thích hợp:

1. Ghi nhận tên thread, loại ngoại lệ, nguyên nhân và ID tác vụ không nhạy cảm.
2. Thông báo một cơ chế giám sát hoặc điều phối rằng **tác vụ/thread thất bại**.
3. Quyết định ở **một tầng khác** có cần khởi chạy tác vụ mới, báo lỗi yêu cầu hoặc dừng dịch vụ có kiểm soát.
4. Giữ đủ ngữ cảnh để điều tra nhưng tránh ghi token, mật khẩu hay dữ liệu cá nhân nhạy cảm vào log.

Những giả định **không đúng**:

- Handler không phải một khối `catch` cho phép thread trở về điểm `throw`.
- Handler không tự khởi chạy lại `Runnable` đã chết.
- Handler không tự khôi phục giao dịch, hoàn tác thay đổi file hay trả tài nguyên đã rò rỉ.
- Handler không bảo đảm thông tin đã được gửi đến nơi giám sát nếu chính cơ chế log/transport thất bại.
- Không nên dựa vào việc handler ném tiếp ngoại lệ để xử lý lại: theo hợp đồng Java, ngoại lệ do `uncaughtException` tự ném ra không được biến thành cơ chế phục hồi thread đáng tin cậy.

Đặc biệt, callback được gọi trong **ngữ cảnh thread đang lỗi**. Nếu handler thực hiện một thao tác có thể bị chặn lâu, tiến trình kết thúc của thread và người gọi đang `join()` có thể bị kéo dài. Giữ handler ngắn gọn, an toàn, tránh deadlock và suy nghĩ cẩn thận về xử lý lỗi ngay trong handler.

### Handler mặc định là phạm vi rộng

`Thread.setDefaultUncaughtExceptionHandler` thay đổi chính sách báo lỗi ở cấp JVM, nên có thể ảnh hưởng tới các thread không do một module trực tiếp quản lý. Với thư viện dùng chung, thường nên để ứng dụng quyết định handler mặc định thay vì tự thay đổi chính sách toàn cục.

## 6. Bắt lỗi tại ranh giới `run()` để ứng dụng chủ động phục hồi

Nếu muốn một worker không kết thúc bất ngờ khi một thao tác nghiệp vụ thất bại, hãy thiết kế một ranh giới xử lý trong `run()` hoặc ngay quanh phần thao tác có thể lỗi:

```java
Runnable task = () -> {
    try {
        processOneMessage();
    } catch (IllegalArgumentException ex) {
        System.out.println("Bỏ qua thông điệp sai định dạng");
    }
};
```

Đây là **đoạn mã minh họa**, cần đặt trong phương thức có `processOneMessage()` và các import/phụ thuộc phù hợp. Cách này có thể giữ worker sống nếu vòng lặp xử lý các thông điệp khác được thiết kế tiếp tục chạy.

Chỉ bắt những ngoại lệ bạn **thực sự có phương án xử lý**:

- Sai dữ liệu một bản tin: ghi nhận lỗi và bỏ qua bản tin theo chính sách có thể hợp lý.
- Hết kết nối cơ sở dữ liệu: có thể thử lại theo giới hạn, chuyển tác vụ sang hàng chờ, hoặc báo trạng thái thất bại.
- Vi phạm invariant nội bộ không thể phục hồi: cố tiếp tục có thể nguy hiểm hơn kết thúc và để tầng điều phối nhận biết.
- `OutOfMemoryError`, `StackOverflowError` và các loại `Error` khác: không nên coi chúng như lỗi nghiệp vụ thông thường rồi `catch (Throwable)` để chạy tiếp.

Với `Runnable.run()` thông thường, chữ ký không cho phép khai báo `throws` một checked exception rộng như `IOException`. Vì vậy phải **bắt checked exception bên trong**, chuyển nó một cách có chủ đích sang unchecked exception, hoặc dùng API tác vụ như `Callable<V>` khi cần hợp đồng khai báo checked exception.

Ví dụ ranh giới làm việc độc lập, cần có phần dọn dẹp trước khi thread kết thúc:

```java
static void runJob() {
    try {
        performJob();
    } catch (IllegalArgumentException ex) {
        reportBadInput(ex);
    } finally {
        releaseJobResources();
    }
}
```

Đây là **khung thiết kế**, không phải chương trình độc lập; `performJob`, `reportBadInput` và `releaseJobResources` phải được định nghĩa. `finally` thường được chạy khi rời `try` dù có lỗi hay không. Tuy nhiên, `finally` cũng có thể ném ngoại lệ và làm che khuất nguyên nhân ban đầu; đóng tài nguyên `AutoCloseable` thường nên sử dụng `try-with-resources`.

## 7. `ExecutorService`: lỗi tác vụ không luôn là uncaught exception của worker thread

Trong ứng dụng đồng thời, nhiều tác vụ được giao cho một thread pool qua `ExecutorService`. Cần phân biệt **thất bại của công việc** với **ngoại lệ thoát khỏi chính vòng chạy worker thread**.

Với `executor.submit(Callable)` hoặc `submit(Runnable)`, executor trả về một `Future`. Nếu phần thân tác vụ ném ngoại lệ, quá trình thực thi tác vụ được đánh dấu thất bại; việc gọi `future.get()` báo về bằng `ExecutionException`, trong đó `getCause()` chứa nguyên nhân tác vụ.

### Ví dụ Java 17+ hoàn chỉnh: lỗi được truyền qua `Future`

Lưu tên **`FutureFailureDemo.java`**:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureFailureDemo {

    public static void main(String[] args) throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Integer> result = pool.submit(() -> {
                System.out.println("task: bắt đầu");
                throw new IllegalStateException("không thể tính kết quả");
            });

            try {
                int value = result.get();
                System.out.println("result: " + value);
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println(
                        "main: task thất bại vì "
                        + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
            }

            System.out.println("main: vẫn hoạt động");
        } finally {
            pool.shutdown();
        }
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac -encoding UTF-8 FutureFailureDemo.java
java FutureFailureDemo
```

Stdout trong điều kiện chạy bình thường:

```text
task: bắt đầu
main: task thất bại vì IllegalStateException: không thể tính kết quả
main: vẫn hoạt động
```

**Giải thích:**

- `submit` trả về `Future<Integer>` đại diện cho **kết quả của tác vụ**, không phải một tham chiếu trực tiếp tới `Thread`.
- Lambda của tác vụ ném `IllegalStateException`. Trong cơ chế `Future` của executor chuẩn, lỗi được ghi nhận là kết quả thất bại của tác vụ.
- `result.get()` chờ tác vụ hoàn thành rồi ném `ExecutionException`; `getCause()` là `IllegalStateException` gốc.
- Dòng `result: ...` không chạy vì `get()` không trả về `int`.
- Main vẫn tiếp tục sau `catch`. `pool.shutdown()` yêu cầu executor dừng nhận tác vụ mới và kết thúc sau các tác vụ đã nhận. Trong ví dụ, tác vụ đã kết thúc khi `get()` trả về/ném.

Một ngoại lệ đã được **framework bắt và đưa vào `Future`** không phải là “uncaught exception thoát khỏi worker thread” chỉ vì mã trong lambda không có `catch`. Do đó handler ở cấp thread có thể không được gọi cho thất bại này.

### `execute`, `submit` và tác vụ bất đồng bộ khác

Với `Executor.execute(Runnable)`, cách ngoại lệ tác vụ thoát ra có thể khác `submit`, vì không có `Future` kết quả được trả về. Ví dụ trong `ThreadPoolExecutor` chuẩn, một ngoại lệ unchecked thoát khỏi `Runnable` được `execute` chuyển vào quá trình thất bại của worker và có thể dẫn đến handler của thread, sau đó executor có thể bố trí worker thay thế khi cần. Chi tiết đó thuộc cơ chế executor và cấu hình triển khai, **không nên đồng nhất mọi loại executor**.

Với `CompletableFuture`, lỗi có thể được quan sát bằng `get()` (bọc trong `ExecutionException`) hoặc `join()` (thường ném `CompletionException`). Hãy chọn nơi quan sát kết quả và chính sách xử lý của API đang dùng.

Điểm cần nhớ: muốn biết lỗi có trở thành **uncaught exception của thread** hay không, phải xét **ai đứng ở ranh giới thực thi** và liệu framework có bắt/lưu lỗi trước khi nó thoát khỏi thread hay không.

## 8. `try-catch` và `finally` ở đâu trong quá trình kết thúc thread?

Khi ngoại lệ chưa được bắt đang đi ngược qua stack, các khối `finally` được thực thi theo quy tắc ngôn ngữ. Ví dụ:

```java
static void job() {
    try {
        System.out.println("đang xử lý");
        throw new IllegalStateException("thất bại");
    } finally {
        System.out.println("dọn dẹp");
    }
}
```

Đây là **phương thức minh họa**. Nếu caller không bắt lỗi, phương thức in:

```text
đang xử lý
dọn dẹp
```

sau đó `IllegalStateException` tiếp tục lan lên. Không có dòng “đã thành công” nào tự xuất hiện.

### `try-with-resources` nên được ưu tiên cho tài nguyên

Nếu tài nguyên triển khai `AutoCloseable`, dùng cấu trúc:

```java
static String read(java.nio.file.Path path)
        throws java.io.IOException {
    try (var reader = java.nio.file.Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

Đây là **phương thức minh họa**; tệp thật phải được chỉ định khi sử dụng. Reader được đóng khi rời `try` dù thao tác đọc ném `IOException`. Nếu lỗi xuất hiện cả trong thân `try` lẫn lúc đóng, Java có thể lưu lỗi đóng dưới dạng **suppressed exception** để giữ ngoại lệ chính.

Không nên dựa hoàn toàn vào uncaught handler để đóng connection, stream hoặc lock. Handler chỉ nhận lỗi khi quá trình thất bại đã lan tới điểm kết thúc thread; vòng đời tài nguyên phải được quản lý **ngay tại nơi cấp phát/sử dụng**. Lưu ý một khối `finally` không đảm bảo chạy nếu tiến trình bị dừng bất thường, chẳng hạn `Runtime.halt()` hoặc bị hệ điều hành kết thúc cưỡng bức.

## 9. `InterruptedException` không đồng nghĩa với uncaught exception

Khi một thread đang `sleep()`, `wait()` hoặc `join()` bị ngắt, các phương thức có thể ném **`InterruptedException`**. Đây là một **checked exception**; nó báo tình huống yêu cầu ngắt/chấm dứt chờ, không mặc nhiên có nghĩa một lỗi unchecked đã thoát khỏi thread.

Trong `Runnable.run()`, ví dụ xử lý hủy có thể là:

```java
@Override
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            doOneStep();
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    } finally {
        closeResources();
    }
}
```

Đây là **khung phương thức minh họa**, giả sử lớp đang triển khai `Runnable`, `doOneStep()` có thể ném `InterruptedException` và `closeResources()` đã được định nghĩa. Gọi lại `interrupt()` giúp khôi phục cờ ngắt (các phương thức như `sleep()` thường xóa cờ khi ném `InterruptedException`), để tầng điều phối có thể quan sát trạng thái thích hợp. Trong ví dụ, `run()` sau đó kết thúc có kiểm soát; đây không phải một `InterruptedException` uncaught.

Nếu nghiệp vụ cần tiếp tục thay vì kết thúc sau khi bị ngắt, phải có chính sách rõ ràng. Không bắt `InterruptedException` rồi lặng lẽ bỏ qua vì điều đó có thể làm cơ chế hủy không hoạt động như dự định.

## 10. Nên xử lý lỗi tại điểm nào?

| Ranh giới | Mục tiêu xử lý | Gợi ý |
| --- | --- | --- |
| Trong hàm nghiệp vụ | Phát hiện lỗi, giữ ý nghĩa nguyên nhân | `throw` ngoại lệ cụ thể khi vi phạm hợp đồng |
| Tầng gọi có khả năng phục hồi | Thử lại, sửa đầu vào hoặc chuyển thành trạng thái nghiệp vụ | `catch` loại phù hợp, hạn chế retry và giữ `cause` |
| Biên `run()` / vòng xử lý tác vụ | Quyết định tác vụ thất bại có làm dừng vòng lặp hay không | Bắt lỗi có thể xử lý; đóng tài nguyên đúng phạm vi |
| `Thread.UncaughtExceptionHandler` | Ghi nhận một thread đã thất bại ngoài ý muốn | Log/giám sát ngắn gọn; không coi là nơi phục hồi stack |
| Người gọi `Future.get()` | Quan sát thành công/thất bại của tác vụ được submit | Bắt `ExecutionException`, xem `getCause()` |
| Tầng điều phối ứng dụng | Quyết định retry, cảnh báo, dừng dịch vụ hoặc phản hồi người dùng | Dựa vào chính sách và khả năng hệ thống còn an toàn |

Ví dụ, một consumer đọc thông điệp có thể xử lý lỗi định dạng ở từng thông điệp và tiếp tục với thông điệp tiếp theo. Nhưng nếu lỗi làm hỏng trạng thái nội bộ không thể khôi phục, giữ thread sống bằng cách bỏ qua ngoại lệ có thể khiến dữ liệu sai lan rộng. Không nên gộp hai tình huống này vào một `catch (Exception ignored)`.

## 11. Sai lầm thường gặp

### “Worker lỗi thì main tự nhận được lỗi”

Không đúng. `Thread.start()` tạo một luồng thực thi độc lập; `join()` chỉ chờ thread hoàn thành. Nếu cần truyền kết quả hoặc lỗi về caller, nên dùng `Future`, `CompletableFuture`, hàng đợi thông điệp, trạng thái được đồng bộ hóa đúng cách hoặc một cơ chế báo cáo được thiết kế rõ.

### “Main thread chết thì toàn bộ ứng dụng dừng ngay”

Không đúng trong mọi trường hợp. Các non-daemon thread khác có thể tiếp tục giữ JVM hoạt động. Ngược lại, ứng dụng cũng có thể kết thúc sau lỗi worker nếu không còn non-daemon thread nào giữ JVM chạy. Cần xét vòng đời thực tế của thread/process.

### “Có uncaught handler là đã bắt và phục hồi lỗi”

Handler **nhận thông báo khi thread đang kết thúc**. Nó không tương đương với `try-catch` nằm trước điểm thoát lỗi và không tự tiếp tục stack đã bị tháo. Muốn phục hồi, hãy đặt logic ở nơi có thể chủ động xử lý hoặc điều phối tác vụ mới.

### “Để `catch (Throwable)` giữ cho thread sống là an toàn”

Bắt `Throwable` có thể ôm cả các `Error` nghiêm trọng như `OutOfMemoryError`. Nhiều trường hợp ứng dụng không đủ điều kiện để tiếp tục đúng đắn. Nên chọn đúng kiểu lỗi và xác định chính sách kết thúc an toàn thay vì trả trạng thái thành công giả.

### “`finally` đảm bảo mọi sự cố đều được dọn sạch”

`finally` giúp dọn dẹp khi rời vùng `try` theo quy tắc Java nhưng không thay thế quản lý tài nguyên, không rollback mọi thay đổi và không phải cam kết trong mọi kiểu kết thúc JVM bất thường. Việc `finally` ném lỗi khác còn có thể che mất nguyên nhân ban đầu.

### “`submit` ném lỗi trong worker nên sẽ luôn in stack trace”

Không nhất thiết. Với `submit` của executor chuẩn, lỗi tác vụ thường được ghi vào `Future` và chỉ xuất hiện khi được quan sát/ghi nhận. Nếu không đọc `Future` hoặc giám sát kết quả, lỗi có nguy cơ bị bỏ quên. Vì thế cần tiêu chuẩn quan sát thành công/thất bại của từng tác vụ.

### “`join()` thành công nghĩa là tác vụ thành công”

Không đúng. `join()` chỉ cho biết thread đã kết thúc (khi trả về bình thường). Thread có thể kết thúc vì hoàn thành công việc hoặc vì ngoại lệ chưa bắt. Trạng thái `TERMINATED` không chứa kết quả nghiệp vụ; phải có kênh báo cáo riêng.

### “Có thể `start()` lại thread đã `TERMINATED`”

Không đúng. Một đối tượng `Thread` chỉ có thể `start()` một lần. Tác vụ muốn retry phải được thực thi trong một luồng mới hoặc được quản lý bởi một executor phù hợp.

## 12. Tình huống luyện tập và kết luận

**Tình huống 1:** Worker B ném `IllegalArgumentException`, không có `catch` và không có handler tùy chỉnh; main A đang đợi B bằng `join()`. Điều gì xảy ra?

B kết thúc vì ngoại lệ chưa bắt và cơ chế báo lỗi mặc định có thể in stack trace lên stderr. `join()` ở A trả về sau khi B kết thúc, trừ khi A bị ngắt. Ngoại lệ của B **không tự động bị ném lại từ `join()`**; A cần kênh khác nếu muốn biết lý do thất bại.

**Tình huống 2:** Một tác vụ được gửi bằng `ExecutorService.submit()` ném `IllegalStateException`. Có thể dùng `Future.get()` để biết lỗi không?

Có. `get()` có thể ném `ExecutionException`; `getCause()` cho biết ngoại lệ của tác vụ. Bản thân việc lỗi được lưu vào `Future` không đồng nghĩa worker thread đã chết.

**Tình huống 3:** Một worker có `try { ... } finally { ... }` nhưng không `catch`; trong `try` có ngoại lệ unchecked. Worker có tiếp tục sau `finally` không?

Nếu không có handler phù hợp ở tầng khác của thread, ngoại lệ vẫn lan lên và thread kết thúc. `finally` thường chạy khi đang tháo stack, nhưng nó **không tự nuốt ngoại lệ**.

**Tình huống 4:** Một non-daemon worker đang thực hiện vòng lặp. Main thread ném ngoại lệ chưa bắt. JVM có chắc dừng ngay không?

Không. Nếu worker vẫn sống, non-daemon worker có thể giữ JVM tiếp tục hoạt động. Ứng dụng cần chính sách kết thúc/điều phối của riêng mình.

**Tình huống 5:** Gắn `UncaughtExceptionHandler` cho worker, sau đó handler ghi log. Có thể dùng chính đối tượng `Thread` đó và gọi `start()` để retry không?

Không. Thread đã chấm dứt không thể được khởi động lại; tạo một thread mới hoặc gửi lại tác vụ qua executor.

**Điểm cần nhớ:** một ngoại lệ chỉ thực sự **uncaught đối với thread** khi nó thoát qua mọi handler còn hiệu lực đến ranh giới kết thúc thread. Khi đó thread kết thúc, handler có thể báo lỗi và thread khác có thể vẫn sống. Trong mã có executor, cần quan sát lỗi của **tác vụ** qua kết quả như `Future`; còn nơi cần phục hồi nên là ranh giới có khả năng xử lý thực tế, không phải một uncaught handler dùng thay cho `try-catch`.