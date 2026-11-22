# 19.6 Điều tra exception tại nơi phát sinh và phân biệt exception đã được xử lý

## Mục tiêu và tình huống

Khi debug ứng dụng Java, một IDE có thể dừng ở dòng `throw` hoặc constructor của exception, dù request vẫn thành công, chương trình vẫn chạy tiếp và không có error log. Ngược lại, một exception thật sự làm thất bại công việc có thể bị framework, `Future` hoặc thread pool giữ lại và chỉ xuất hiện dưới dạng wrapper exception ở một vị trí khác.

Vì vậy **“exception đã được tạo hoặc ném” không tương đương với “lỗi chưa được xử lý”**, và **“được catch” không luôn có nghĩa “đã khôi phục thành công”**.

Bài học này hướng dẫn cách truy vết **nơi phát sinh**, **đường lan truyền**, **nơi xử lý cuối cùng** và **tác động thực tế** của exception bằng Java debugger, stack trace, cause chain, logging và JFR (Java Flight Recorder). Mục tiêu là chẩn đoán chính xác, giảm nhiễu bởi exception bình thường và không vô tình che lỗi nghiêm trọng.

Sau bài học, bạn có thể:

- Phân biệt exception được **tạo**, **ném**, **bắt**, **xử lý bằng fallback**, **bọc lại**, **ném tiếp**, **được giữ trong future**, **thoát khỏi thread** và **được log**.
- Đặt **exception breakpoint** đúng loại trên IDE hoặc dùng `jdb` để dừng gần nơi ném, kiểm tra local variables, thread và call stack.
- Đọc `Throwable.getStackTrace()`, `getCause()` và `getSuppressed()` để tìm nguyên nhân gốc mà không nhầm stack của wrapper với nơi bắt đầu sự cố.
- Kiểm tra JFR `jdk.JavaExceptionThrow` một cách thận trọng: một event không chứng minh exception chưa được xử lý, thậm chí trên HotSpot có thể được ghi khi tạo exception **mà không thực sự ném**.
- Phân biệt lỗi đã khôi phục với lỗi bị “nuốt”, lỗi đã chuyển thành kết quả thất bại và lỗi uncaught có thể chỉ kết thúc một thread.
- Thực hành trên Java 17+ bằng các chương trình biên dịch/chạy được và output đã được kiểm chứng.

**Phạm vi:** Java SE 17+; các ví dụ JFR, `jdb` và JDWP dùng HotSpot/OpenJDK. Giao diện IntelliJ IDEA, Eclipse hay công cụ khác có thể gọi chức năng break-on-throw bằng những tên khác nhau. Các số sự kiện JFR, line number, stack frames và hành vi framework tùy JVM/phiên bản, không phải stdout cố định của bài.

## 1. Vòng đời một exception: tạo, ném, bắt và kết quả

Xét chuỗi xử lý:

~~~text
Input không hợp lệ
       |
       v
new NumberFormatException(...)        [TẠO đối tượng]
       |
       v
throw exception                        [NÉM]
       |
       v
exception đi ngược call stack
       |
       +--> catch gần nguồn?
       |       |
       |       +--> fallback hợp lệ   [ĐÃ XỬ LÝ VÀ KHÔI PHỤC]
       |       +--> log rồi rethrow   [CHƯA XỬ LÝ XONG]
       |       +--> bọc nguyên nhân   [ĐỔI KIỂU/NGỮ CẢNH]
       |       +--> nuốt rồi trả sai  [CÓ THỂ LÀ BUG]
       |
       +--> tầng boundary/framework?
       |       |
       |       +--> HTTP 4xx/5xx, failed future,
       |            retry hoặc message NACK  [ĐÃ BẮT, NHƯNG CÔNG VIỆC THẤT BẠI]
       |
       +--> thoát khỏi Thread.run()
               |
               v
          UncaughtExceptionHandler     [THREAD BỊ KẾT THÚC]
~~~

Điểm quan trọng: Java `Throwable` là **đối tượng**. Có thể tạo một exception object mà không bao giờ `throw` nó:

~~~java
new IllegalArgumentException("created but not thrown");
~~~

Dòng trên là một Java statement hợp lệ nhưng **không làm luồng điều khiển nhảy vào catch**. Một debugger đặt breakpoint theo sự kiện ném thường nhằm dừng tại thời điểm exception được ném; các công cụ ghi sự kiện khác có thể có nghĩa rộng hơn.

### 1.1 Định nghĩa từng trạng thái thực dụng

| Khái niệm | Dấu hiệu trong code | Tác động |
| --- | --- | --- |
| **Constructed** | `new IOException("...")` | Có object, chưa chắc đã throw |
| **Thrown / raised** | `throw ex;` hoặc một API ném thay bạn | Luồng thực thi bình thường bị gián đoạn để tìm handler phù hợp |
| **Caught** | `catch (X ex) { ... }` | Handler được chọn; chưa rõ đã giải quyết hay chỉ rethrow |
| **Recovered / handled** | `catch` xác định fallback an toàn, trả kết quả hợp lệ | Công việc có thể tiếp tục bình thường theo chính sách |
| **Translated / wrapped** | `throw new ServiceException("...", ex);` | Exception mới lan truyền; cause giữ nguyên nhân cũ |
| **Rethrown** | `throw ex;` | Cùng object tiếp tục lan truyền |
| **Swallowed** | `catch` rỗng hoặc trả giá trị “thành công” giả | Exception biến mất khỏi log nhưng bug có thể còn |
| **Captured in async result** | `CompletableFuture`/`Future` kết thúc exceptionally | Chưa nhất thiết thoát khỏi worker thread; lỗi có thể chỉ lộ khi quan sát future |
| **Uncaught at thread boundary** | Exception thoát khỏi `Thread.run()` | Thread đó kết thúc; JVM/process không nhất thiết kết thúc |
| **Logged** | Logger ghi message/stack | Chỉ là quan sát; log không chứng minh đã xử lý hay chưa |

**Không đánh đồng** “caught” và “successful”. Ví dụ HTTP controller `catch` một exception rồi trả `500 Internal Server Error`: exception đã được *bắt*, nhưng request vẫn *thất bại*. Hoặc framework chuyển exception thành HTTP 404/400 có chủ đích: có thể là kết quả nghiệp vụ hợp lệ, tùy contract.

## 2. Exception khác Error, checked khác unchecked, nhưng cả hai đều cần xác minh tác động

- **Checked exception**: các subtype của `Exception` trừ `RuntimeException` phải được khai báo/handled theo luật Java (ví dụ `IOException`). “Checked” không có nghĩa lỗi nghiêm trọng hơn.
- **Unchecked exception**: `RuntimeException` và `Error` (ví dụ `IllegalArgumentException`, `NullPointerException`, `OutOfMemoryError`). Compiler không bắt buộc khai báo trong `throws`.
- **`Error`** thường chỉ vấn đề runtime/VM nặng, không nên dùng `catch (Throwable)` như một cơ chế “khôi phục mọi lỗi” mặc định. Ví dụ `OutOfMemoryError` có thể khiến chính code logging hoặc fallback thất bại.
- **Exception dự kiến** có thể dùng làm tín hiệu điều khiển của thư viện, nhưng tạo/thu stack trace lặp với tần suất cao vẫn có thể tốn chi phí CPU/memory. Thay đổi mã nên dựa trên profile và contract, không vì một debugger dừng nhiều lần.

Tên class đơn lẻ như `IllegalStateException` không cho biết đây là bug hay response được dự kiến. Cần biết **input, code path, handler, outcome**.

## 3. Đặt exception breakpoint để dừng tại lúc ném

### 3.1 Khác line breakpoint thông thường như thế nào?

Line breakpoint chỉ dừng khi một vị trí source được chạy. Nếu bạn biết “request thất bại” nhưng không biết exception được tạo ở tầng JDBC, cache, validation hay application code, line breakpoint buộc phải đoán điểm dừng.

**Exception breakpoint** dùng cơ chế debug của JVM để yêu cầu dừng khi exception thuộc một loại nhất định được ném, thường cho phép:

- Bật **caught exceptions** (exception có handler khả dĩ) và/hoặc **uncaught exceptions** (exception không có handler phù hợp theo cách debugger/JDWP xác định).
- Chỉ dừng cho một loại như `java.lang.NumberFormatException` hoặc subtype, thay vì mọi `Throwable`.
- Đặt filter theo package/class, condition, thread và suspend policy tùy IDE để giảm số lần dừng.
- Xem thread hiện tại, nơi ném theo sự kiện debugger, stack frames và local variables ở thời điểm trước khi unwind.

**Tên tùy chọn và tiêu chí phân loại caught/uncaught khác nhau tùy IDE và debug engine.** Vì vậy sau khi debugger dừng, vẫn phải kiểm chứng handler và kết quả thực thi. Đặc biệt, một handler ở tầng framework có thể khiến IDE coi exception “caught” dù request trả lỗi.

### 3.2 Quy trình với IDE (IntelliJ IDEA/Eclipse hoặc IDE hỗ trợ JDWP)

1. Chạy chương trình bằng **Debug** với debug symbols và source khớp binary đang chạy. Nếu source không khớp JAR thực tế, line number có thể dẫn sai.
2. Mở phần **Breakpoints → Java Exception Breakpoint** (tên tương đương trong IDE), chọn exception class cụ thể thay vì `java.lang.Throwable` nếu có thể.
3. Khi chưa rõ đã có handler hay chưa, bật chế độ theo dõi **caught + uncaught** trong một cửa sổ ngắn. Nếu IDE liên tục dừng ở exception bình thường của thư viện, dùng class filters, condition và tắt caught tạm thời để tập trung vào lỗi nghiêm trọng; đừng nhầm “không còn dừng” với “không còn throw”.
4. Gây lại vấn đề bằng **input và điều kiện tái hiện cố định**; ghi request ID, thread, timestamp và outcome.
5. Khi dừng, quan sát exception type/message, **top application frame**, local variables/arguments, state không hợp lệ và thứ tự caller frames. Với stack nằm trong mã thư viện, di chuyển dọc stack đến ứng dụng để tìm tham số mà app truyền vào.
6. Tiếp tục stepping hoặc đặt line breakpoint tại `catch`/handler tương ứng. Xem handler **return fallback, retry, wrap, rethrow hay trả failure response**.
7. Xác minh kết quả cuối: HTTP status/body, future result, transaction rollback/commit, message ACK/NACK, metrics và log. Chỉ lúc đó mới phân loại đã xử lý thành công, xử lý thành lỗi có chủ đích, hay còn uncaught.

**Cẩn trọng:** “Resume” sau khi debugger tạm dừng không giống “ignore” exception ở chương trình. Nó chỉ tiếp tục luồng JVM như bình thường; exception vẫn có thể truyền đến handler hoặc thoát thread.

### 3.3 Bước nhanh bằng `jdb`

Java có công cụ dòng lệnh `jdb` (JDK) dùng Java Platform Debugger Architecture. Ví dụ chạy ứng dụng `ExceptionPathsDemo` trong JDB:

~~~sh
jdb ExceptionPathsDemo
~~~

Trong prompt `jdb`, có thể đặt exception breakpoint rồi chạy chương trình theo trợ giúp của phiên bản:

~~~text
catch java.lang.NumberFormatException
run
~~~

`catch` là **lệnh của debugger**, không phải từ khóa `catch` trong source; nó làm debugger dừng tại lần exception đó được ném. Dùng `help`, `where`, `up`, `down`, `locals`, `cont` và `ignore` tương ứng để phân tích/tiếp tục. Một số phiên bản `jdb` cung cấp chế độ `catch caught|uncaught|all <exception-class>`; kiểm tra `help catch` trên bản đang dùng thay vì giả định cú pháp mọi bản đều giống nhau.

Khi muốn attach debugger vào JVM đang chạy, JDWP có thể được bật lúc khởi động. Ví dụ chỉ **bind loopback cho môi trường lab**:

~~~sh
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 ExceptionPathsDemo
jdb -attach 127.0.0.1:5005
~~~

Lệnh thứ nhất chạy **ở terminal A và chờ debugger** vì `suspend=y`; lệnh thứ hai chạy **ở terminal B**. Trong IDE, có thể dùng tính năng Remote Debug cùng địa chỉ. **Không mở JDWP ra Internet, không bind `0.0.0.0` trên production mà thiếu kênh bảo mật và quyền truy cập nghiêm ngặt**: debugger có quyền can thiệp sâu vào tiến trình và dữ liệu của ứng dụng. Attach/stop-the-world còn gây ảnh hưởng latency; chỉ dùng khi được phép.

## 4. Bốn câu hỏi tại điểm exception phát sinh

Khi debugger dừng, trước khi thay đổi code, hãy trả lời lần lượt:

1. **Điều gì thật sự sai?** Ví dụ `Integer.parseInt("abc")` thất bại do input vi phạm contract, hay caller đáng ra phải validate? Ghi loại exception và chính xác input (loại bỏ bí mật).
2. **Vị trí nào tạo/throw?** Lần theo stack đến ứng dụng; từ đó xem những caller nào truyền dữ liệu hoặc state.
3. **Handler ở đâu?** Kiểm tra catch ngay tại tầng hiện tại, catch ở boundary, async wrapper hay default uncaught handler. Đừng dừng điều tra chỉ vì đã thấy một `catch`.
4. **Outcome là gì?** Hệ thống dùng fallback hợp lệ, trả validation error, retry, rollback, đánh dấu job failed, hay thực sự làm rơi request/thread? So sánh với contract.

Đây là điểm khác biệt giữa **exception event** và **incident**. Một hệ thống có thể ném nhiều `NumberFormatException` cho những input sai rồi xử lý thành 400, hoàn toàn phù hợp contract; ngược lại chỉ một `IOException` được “nuốt” có thể khiến dữ liệu ghi thiếu mà không có error log.

## 5. Stack trace: nơi tạo Throwable không phải lúc nào cũng là lần throw hiện tại

### 5.1 Xem stack và cause đúng cách

Trên các `Throwable` thông thường, stack trace được thu khi đối tượng được tạo hoặc lúc gọi `fillInStackTrace()`. Vì thế một stack từ `printStackTrace()` có thể chỉ đến **nơi exception được khởi tạo** chứ không phải mọi lệnh `throw`/`rethrow` mà nó đã đi qua. JVM/debugger có thể cung cấp vị trí ném thực qua breakpoint, khác với stack lưu trong object.

~~~java
IllegalStateException ex = new IllegalStateException("reused");
throw ex; // Object được tạo trước đó; trace lưu trong ex có thể bắt đầu ở dòng tạo.
~~~

Đây là **snippet không độc lập**. Không nên tạo exception rồi tái sử dụng rộng rãi vì còn làm phức tạp chẩn đoán, đặc biệt khi chạy nhiều thread. Khi `throw ex` cùng object, đừng mong có stack mới tự động tại mỗi lần ném; khi `throw new ...`, wrapper mới có stack của nó và có thể giữ cause cũ.

### 5.2 Wrapper và cause chain

~~~java
try {
    readConfig();
} catch (IOException original) {
    throw new IllegalArgumentException("startup failed", original);
}
~~~

Đây là snippet thuộc phương thức có `readConfig()` phù hợp, ví dụ hoàn chỉnh ở phần 8. Nó tạo exception mới với stack bắt đầu ở dòng wrap, còn `getCause()` vẫn là `IOException("config missing")` và giữ trace gốc.

Để đọc chain:

~~~java
Throwable cursor = error;
while (cursor != null) {
    System.out.println(cursor.getClass().getSimpleName()
            + ": " + cursor.getMessage());
    cursor = cursor.getCause();
}
~~~

Đây là **snippet** với biến `error` có kiểu `Throwable`. Thực tế nên giới hạn độ dài chain, ngăn vòng lặp bất thường và dùng structured logging; không hiển thị message chứa token/PII. Không mặc định cause cuối cùng là nguyên nhân duy nhất: cùng một transaction có thể có nhiều lỗi, và root cause chỉ là một manh mối.

Các wrapper hay gặp:

| Lớp/nguồn | Nguyên tắc điều tra |
| --- | --- |
| `CompletionException` khi `CompletableFuture.join()` | Xem `getCause()` để tìm lỗi trong stage; future có thể đã failed mà thread vẫn chạy bình thường |
| `ExecutionException` khi `Future.get()` | Xem `getCause()`; executor có thể giữ exception để caller nhận sau |
| `InvocationTargetException` khi reflective `Method.invoke(...)` | Xem `getCause()` hoặc `getTargetException()` để đến exception do method được gọi ném |
| `ExceptionInInitializerError` | Xem nguyên nhân trong static initializer; không chỉ sửa nơi caller lần đầu truy cập lớp |
| `UndeclaredThrowableException` trong dynamic proxy | Xem cause/undeclared throwable và contract của invoked method |
| Framework-specific wrapper | Đọc cause chain cùng boundary mapping (ví dụ trả 4xx/5xx), không chỉ lấy wrapper top frame |

### 5.3 Suppressed exceptions: lỗi bị che bởi một lỗi khác

Trong `try-with-resources`, nếu phần thân ném exception, sau đó `close()` cũng ném, exception ở `close()` thường được **thêm vào `getSuppressed()` của lỗi chính**, thay vì trở thành cause. Không chỉ kiểm `getCause()` khi nghi lỗi đóng tài nguyên.

Lưu **SuppressedDemo.java**:

~~~java
import java.io.IOException;

public final class SuppressedDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new IOException("read failed");
        } catch (IOException ex) {
            System.out.println("PRIMARY: " + ex.getMessage());
            System.out.println("SUPPRESSED: "
                    + ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

Chạy:

~~~sh
javac --release 17 SuppressedDemo.java
java SuppressedDemo
~~~

Stdout chính xác:

~~~text
PRIMARY: read failed
SUPPRESSED: close failed
~~~

Chương trình đã được biên dịch với `--release 17` và chạy kiểm tra. Kết luận: `getSuppressed()` chứa “close failed” nhưng lỗi “read failed” vẫn là exception chính. Nếu chỉ đọc root cause hoặc message top-level, bạn có thể bỏ qua lỗi cleanup quan trọng.

## 6. “Đã catch” có ba kết cục rất khác

### 6.1 Phục hồi hợp lệ

~~~java
try {
    return Integer.parseInt(value);
} catch (NumberFormatException ex) {
    return 8080; // Chỉ hợp lệ nếu 8080 là fallback đã được thiết kế.
}
~~~

Snippet trên thuộc một phương thức trả `int` có biến `value`. Việc fallback có đúng hay không phụ thuộc yêu cầu nghiệp vụ. Với tham số cấu hình tùy chọn, dùng giá trị default có thể hợp lý. Với số tiền thanh toán hoặc ID bảo mật, việc tự động thay giá trị như vậy có thể tạo lỗi nghiêm trọng; nên báo invalid input.

### 6.2 Bắt rồi chuyển thành kết quả thất bại

~~~java
try {
    service.execute();
} catch (IllegalStateException ex) {
    // Trả response lỗi hoặc đánh dấu job FAILED (tùy framework).
}
~~~

Đây là **pseudo-snippet** với API `service.execute()` không được định nghĩa độc lập; nó minh họa một exception được **catch** nhưng **operation thất bại**. Một exception-handling middleware có thể chủ động chuyển thành HTTP 500, một message consumer có thể NACK để retry, một transaction boundary có thể rollback. Đừng ghi “handled = success” trên dashboard nếu chỉ phát hiện rằng có catch.

### 6.3 Nuốt lỗi hoặc log rồi ném tiếp

~~~java
try {
    updateLedger();
} catch (Exception ignored) {
    // Không làm gì cả; đây có thể là bug nghiêm trọng.
}
~~~

Đoạn trên là pseudo-snippet. Việc trả thành công sau khi bỏ qua exception có thể gây **silent data corruption**, dù người dùng không thấy stack trace. Ngược lại:

~~~java
try {
    updateLedger();
} catch (Exception ex) {
    logger.error("Update failed", ex);
    throw ex;
}
~~~

Đây cũng là pseudo-snippet (cần `logger` và `updateLedger()` thực tế). Nó **đã bắt** nhưng **chưa giải quyết**, exception vẫn truyền lên caller. Nếu mọi tầng đều `log + throw`, một lỗi có thể xuất hiện ba, bốn bản stack trace và làm tăng false alert. Thực tế nên log đầy đủ ở **boundary chịu trách nhiệm ra quyết định**, kết hợp correlation ID, error type/cause và outcome; tầng dưới có thể thêm context bằng exception wrapping nhưng giữ nguyên cause.

**Đừng catch rộng `Throwable` hoặc `Exception` một cách máy móc.** Catch đủ cụ thể theo tình huống, không che `InterruptedException`: nếu không tiếp tục throw, thường cần khôi phục cờ ngắt với `Thread.currentThread().interrupt()` và dừng công việc theo contract.

## 7. Asynchronous exception: worker không chết nhưng tác vụ vẫn thất bại

Một lỗi phát sinh trong stage của `CompletableFuture` thường được **lưu trong kết quả future** thay vì thoát thẳng khỏi worker dưới dạng exception uncaught. Khi gọi:

~~~java
CompletableFuture<Void> job =
        CompletableFuture.runAsync(() -> {
            throw new UnsupportedOperationException("async failure");
        });

try {
    job.join();
} catch (CompletionException ex) {
    System.out.println(ex.getCause().getMessage());
}
~~~

Đây là snippet trong phương thức Java có import `CompletableFuture` và `CompletionException`. `join()` thường ném `CompletionException` (unchecked) bao lấy nguyên nhân trong stage; `get()` dùng `ExecutionException` (checked) khi completion thất bại. Nếu caller **không bao giờ quan sát future**, ứng dụng có thể thiếu log và metric cho tác vụ lỗi, dù worker thread của pool vẫn tiếp tục xử lý công việc khác.

Tương tự, `ExecutorService.submit(...)` lưu lỗi trong `Future` để `get()` báo; điều này khác với một `Thread.run()` tự tạo ném exception uncaught. Hãy debug tại **lambda/task throw site**, xem stage/future nào giữ lỗi và có callback `handle`/`exceptionally`/`whenComplete`/`get`/`join` để xử lý đúng chính sách hay không.

Một callback `exceptionally(ex -> fallback)` có thể chuyển future sang kết quả bình thường **nếu thực sự khôi phục được**. Một callback `whenComplete` chỉ để log không tự bảo đảm future chuyển từ exceptional sang success: kết quả phụ thuộc logic và semantics của stage.

### 7.1 Uncaught ở thread không đồng nghĩa toàn bộ JVM chết

Lưu file **UncaughtThreadDemo.java**:

~~~java
public final class UncaughtThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            throw new IllegalStateException("job failed");
        }, "worker-1");
        worker.setUncaughtExceptionHandler((thread, error) ->
                System.out.println("UNCAUGHT: " + thread.getName()
                        + " -> " + error.getMessage()));
        worker.start();
        worker.join();
        System.out.println("MAIN_STILL_RUNNING");
    }
}
~~~

Chạy:

~~~sh
javac --release 17 UncaughtThreadDemo.java
java UncaughtThreadDemo
~~~

Stdout chính xác:

~~~text
UNCAUGHT: worker-1 -> job failed
MAIN_STILL_RUNNING
~~~

Trong lần chạy đã kiểm thử, mã thoát là **0**, vì main hoàn tất bình thường mặc dù worker ném exception uncaught. `UncaughtExceptionHandler` nhận thông báo **sau khi exception thoát khỏi run**, không “tua lại” tác vụ đã thất bại. Chương trình thực tế có thể cần đánh dấu job failed, restart worker hoặc chuyển sự cố vào hệ thống giám sát. Không suy từ process còn sống rằng không có uncaught exception trong các thread khác.

## 8. Thực hành tổng hợp Java 17+: exception được ném, bắt và bọc lại

Chương trình sau cố ý mô phỏng bốn đường đi khác nhau:

1. Input không hợp lệ, ứng dụng có **fallback được định nghĩa**.
2. Service phát sinh lỗi và **boundary catch** để thông báo thất bại cục bộ.
3. `IOException` được **wrap** thành `IllegalArgumentException`, giữ `cause`.
4. Stage bất đồng bộ thất bại, `CompletableFuture` chứa lỗi; `join()` phát `CompletionException` và caller quan sát nguyên nhân.

Lưu file **ExceptionPathsDemo.java**:

~~~java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public final class ExceptionPathsDemo {
    private static int parsePort(String input) {
        try {
            return Integer.parseInt(input);
        } catch (NumberFormatException ex) {
            System.out.println("RECOVERED: port=8080");
            return 8080;
        }
    }

    private static void repository() {
        throw new IllegalStateException("database unavailable");
    }

    private static void requestBoundary() {
        try {
            repository();
        } catch (IllegalStateException ex) {
            System.out.println("BOUNDARY_HANDLED: " + ex.getMessage());
        }
    }

    private static void readConfig() throws IOException {
        throw new IOException("config missing");
    }

    private static void loadConfig() {
        try {
            readConfig();
        } catch (IOException ex) {
            throw new IllegalArgumentException("startup failed", ex);
        }
    }

    private static void asyncTask() {
        CompletableFuture<Void> job = CompletableFuture.runAsync(() -> {
            throw new UnsupportedOperationException("async failure");
        });
        try {
            job.join();
        } catch (CompletionException ex) {
            System.out.println("FUTURE_HANDLED: " + ex.getCause().getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("START");
        System.out.println("PORT=" + parsePort("not-a-number"));
        requestBoundary();
        try {
            loadConfig();
        } catch (IllegalArgumentException ex) {
            System.out.println("WRAPPED: " + ex.getMessage());
            System.out.println("ROOT_CAUSE: " + ex.getCause().getMessage());
        }
        asyncTask();
        System.out.println("END");
    }
}
~~~

Biên dịch và chạy:

~~~sh
javac --release 17 ExceptionPathsDemo.java
java ExceptionPathsDemo
~~~

Stdout chính xác của chương trình:

~~~text
START
RECOVERED: port=8080
PORT=8080
BOUNDARY_HANDLED: database unavailable
WRAPPED: startup failed
ROOT_CAUSE: config missing
FUTURE_HANDLED: async failure
END
~~~

Đã kiểm thử với `javac --release 17` và HotSpot JDK 24. Dù có nhiều exceptions phát sinh, chương trình **không in stack trace ra stderr**, vì những đường đi trên đều có handler phù hợp. Tuy nhiên, điều đó **không chứng minh mọi thao tác nghiệp vụ thành công**: case `repository()` báo unavailable, và `asyncTask()` đã thất bại nhưng lỗi được quan sát.

### 8.1 Dùng exception breakpoints để theo dõi chương trình này

Bật caught + uncaught cho các loại:

- `NumberFormatException` → dừng ở tình huống parsePort; sau resume, `catch` trả 8080. Có thể coi là khôi phục theo contract của lab.
- `IllegalStateException` → dừng ở `repository()`; sau resume, `requestBoundary()` catch và in dòng báo lỗi. Đây là **xử lý tại boundary**, không phải kết quả service thành công.
- `IOException` → dừng ở `readConfig()`; `loadConfig()` wrap sang `IllegalArgumentException`, sau đó main catch. Kiểm tra `getCause()` của wrapper.
- `UnsupportedOperationException` → dừng trong lambda chạy ở worker; tương lai `job.join()` có thể ném `CompletionException` ở thread main. Xem cả worker thread và main.
- `CompletionException` → lưu ý đây là lỗi wrapper do cơ chế `CompletableFuture`, không phải nguyên nhân đầu tiên “async failure”.

Đặt line breakpoint ở **`catch`** của từng case rồi so sánh với exception breakpoints ở thời điểm ném. Hai điểm dừng trả lời hai câu hỏi khác nhau: **“ở đâu phát sinh?”** và **“ai quyết định cách xử lý?”**.

### 8.2 Checklist thông tin khi debugger dừng

Ghi một phiếu điều tra nhỏ, không log dữ liệu bí mật:

~~~text
Timestamp / request ID / thread:
Exception class / message:
Creation site (Throwable stack) / actual throw site (debugger):
First relevant application frame:
Input/state causing the exception:
Catch / wrapper / handler chain:
Result: fallback | validation failure | retry | 5xx | failed future | uncaught
Evidence: test output / response code / metrics / logs:
Proposed fix and retest criteria:
~~~

Đây là mẫu text có thể điền trong công cụ theo dõi sự cố, không phải Java code. Các mốc thời gian từ debugger/JFR/log phải được đối chiếu timezone và clock giữa process/host/container.

## 9. JFR: có event `jdk.JavaExceptionThrow` chưa chắc exception được throw hoặc uncaught

Đây là **bẫy quan trọng**, đặc biệt khi bài toán yêu cầu “phân biệt exception đã được xử lý”.

JFR có những event tùy JDK như:

- `jdk.JavaExceptionThrow`: thông tin liên quan quá trình JVM tạo/phát sinh exception, gồm kiểu, message, thread, stack khi event được ghi.
- `jdk.JavaErrorThrow`: tương tự cho `Error` tùy template.
- `jdk.ExceptionStatistics`: số liệu thống kê tổng hợp/định kỳ tùy JDK và cấu hình; không dùng nó để xác định một request cụ thể đã thất bại.

**Cẩn trọng về semantics thực tế trên HotSpot:** trong kiểm thử JDK 24, `jdk.JavaExceptionThrow` đã được ghi **ngay cả khi code chỉ tạo `new IllegalArgumentException(...)` mà không thực hiện `throw`**. Event stack bắt đầu trong constructor `Throwable`; vì vậy tên event chứa chữ “Throw” **không bảo đảm đã thực thi biểu thức `throw`, càng không chứng minh exception không được catch**. Hãy dùng debugger/JDWP hoặc code/control-flow để xác minh việc ném và đường đi đến handler.

### 9.1 Bật event có chủ đích, không giả định default ghi hết

Với JDK hỗ trợ `jfr configure`, tạo một template riêng từ `default.jfc`:

~~~sh
jfr configure --input default.jfc --output throws.jfc 'jdk.JavaExceptionThrow#enabled=true' 'jdk.JavaExceptionThrow#stackTrace=true'
~~~

Chạy demo và ghi ngắn vào file:

~~~sh
java '-XX:StartFlightRecording=settings=throws.jfc,filename=throws.jfr,dumponexit=true' ExceptionPathsDemo
jfr summary throws.jfr
jfr print --events jdk.JavaExceptionThrow --stack-depth 12 throws.jfr
~~~

`jfr summary` cho biết số event đã thực sự được ghi trong file; `jfr print` có thể hiện `thrownClass`, `message`, `eventThread` và `stackTrace`. Một lần chạy thử HotSpot JDK 24 với custom template này có **6 event `jdk.JavaExceptionThrow`**, bao gồm `NumberFormatException`, `IllegalStateException`, `IOException`, `IllegalArgumentException`, `UnsupportedOperationException` và `CompletionException`. Đây là **số liệu thí nghiệm**, không phải số phải thấy ở mọi JDK, vì nội bộ JVM và template có thể sinh khác số event.

Trong cùng môi trường, nếu chạy `settings=default` mà không tùy chỉnh, file thử nghiệm **không có event `jdk.JavaExceptionThrow`**. Suy ra: **file không có event không chứng minh không có exception**; phải xác minh setting `enabled`, khoảng thời gian ghi và output.

Đừng tùy tiện bật event exception với stack cho toàn bộ traffic production: nếu ứng dụng sử dụng exception như control flow ở tần suất cao, lượng dữ liệu và overhead có thể tăng mạnh. Một số JDK hỗ trợ các cơ chế giảm tần suất/giới hạn ghi, nhưng **không giả định setting `throttle` tồn tại cho mọi event/JDK**. Trong môi trường kiểm thử JDK 24, yêu cầu `jdk.JavaExceptionThrow#throttle=10000/s` cho `jfr configure` bị từ chối. Chỉ dùng những event settings được JVM thực tế hỗ trợ; ưu tiên **cửa sổ thu ngắn, workload đại diện, kiểm tra file size và chi phí**, hoặc bộ đếm ứng dụng đã tổng hợp khi chỉ cần rate.

### 9.2 Thí nghiệm phân biệt tạo exception và throw

Lưu **ExceptionConstructedDemo.java**:

~~~java
public final class ExceptionConstructedDemo {
    public static void main(String[] args) {
        new IllegalArgumentException("constructed but not thrown");
        System.out.println("NO_THROW_REACHED");
    }
}
~~~

Chạy trong thư mục có `throws.jfc` ở trên:

~~~sh
javac --release 17 ExceptionConstructedDemo.java
java '-XX:StartFlightRecording=settings=throws.jfc,filename=constructed.jfr,dumponexit=true' ExceptionConstructedDemo
jfr print --events jdk.JavaExceptionThrow --stack-depth 8 constructed.jfr
~~~

Stdout **do chính Java demo in** là:

~~~text
NO_THROW_REACHED
~~~

Nhưng trong một lần chạy HotSpot JDK 24, file `constructed.jfr` **vẫn có một event `jdk.JavaExceptionThrow`** với:

~~~text
message = "constructed but not thrown"
thrownClass = java.lang.IllegalArgumentException
stackTrace includes ExceptionConstructedDemo.main(...)
~~~

Đây là **trích đoạn minh họa đã lược bớt** các trường như timestamp, thread và frame constructor; nội dung đầy đủ tùy JVM. Chương trình thực tế không ném exception này và vẫn thoát mã 0. Đó là lý do **JFR exception event không thay thế được exception breakpoint hoặc phân tích handler**.

### 9.3 JFR kết hợp với debugger và log

JFR thích hợp để nhìn **xu hướng, loại exception, thread và call sites** trong khoảng thu không thể ngồi debug từng request. Khi thấy event tăng:

1. Đọc cấu hình JFR thực tế, loại event, thời gian, stack, thread và context hệ thống.
2. Lọc các lớp exception liên quan application code; phân biệt thông điệp wrapper và nguyên nhân sâu nhất.
3. Tái hiện một trường hợp nhỏ với exception breakpoint để xem **nơi ném thật** và **handler**.
4. Đối chiếu các metrics kết quả thật: request failure ratio, retry rate, DLQ, timeout, job failure, fallback rate.
5. Chỉ gọi là incident/bug khi có bằng chứng hành vi không đạt contract, không chỉ vì event count tăng.

## 10. Log thông minh: nơi nào nên ghi và ghi gì?

Lỗi phổ biến là log toàn bộ stack ở mọi tầng, rồi lại ném lên, khiến cùng một exception xuất hiện như nhiều lỗi. Thay vào đó:

| Tầng | Nên làm gì | Vì sao |
| --- | --- | --- |
| Thư viện/parser nhỏ | Ném kiểu có ý nghĩa; có thể thêm context mà **giữ cause** | Để caller quyết định có fallback hay báo lỗi |
| Service | Handle khi biết cách khôi phục an toàn; nếu không thì rethrow/wrap với context | Không tạo false success hoặc che nguyên nhân |
| HTTP boundary/job scheduler/message consumer | Ghi error outcome đúng một lần kèm correlation ID, trạng thái, operation, root cause | Có thông tin nghiệp vụ và quyết định cuối |
| Metrics | Đếm recovered failures, validation errors, retry, hard failures theo loại | Không nhầm thrown count với failed request |
| APM/JFR | Thu data hỗ trợ chẩn đoán ở cửa sổ phù hợp | Có stack/timeline bổ sung mà không cần log tất cả |

Không nên ghi password, token, raw payload nhạy cảm hoặc toàn bộ HTTP headers trong exception log. `ex.getMessage()` cũng có thể chứa dữ liệu đầu vào, nên cần sanitization. Với log aggregation, lưu correlation ID và consistent error code để nối các tầng; giữ stack đầy đủ ở điểm đáng tin, tránh log duplicate.

**Quan trọng:** một exception được catch để trả response lỗi vẫn nên có metric thất bại tương ứng; “caught” chỉ là chi tiết triển khai, không phải chuẩn đo chất lượng service.

## 11. Debug những ngoại lệ khó thấy trong ứng dụng đa tầng

### 11.1 Framework tự bắt exception

Trong Spring MVC/Jakarta Servlet hoặc HTTP middleware, exception từ controller có thể được bắt ở tầng handler/resolver/filter và chuyển thành response. Từ góc nhìn IDE, exception có thể là **caught**, nhưng request vẫn 500. Cần xem đường mapping type → status, body, transaction và whether log once. Không đánh đồng “uncaught in user code” với “uncaught at thread boundary”.

### 11.2 Retry che đi nỗ lực thất bại

Một client có thể throw timeout lần thứ nhất, framework catch và retry thành công lần thứ hai. JFR/exception breakpoint thấy timeout nhưng request cuối thành công. Vẫn cần xem retry rate, backoff, idempotency và SLO: nhiều lỗi được retry có thể gây latency và tăng tải. Ngược lại, lỗi đã retry hết và ném ra caller mới là thất bại cuối cùng.

### 11.3 Transaction rollback dù exception được catch

Một transaction có thể đã bị đánh dấu rollback-only ở tầng dưới, trong khi outer code catch exception và nghĩ mọi việc ổn. Tùy framework, commit có thể thất bại sau đó. Xem transaction state/rollback marker, không dựa vào việc không có exception ra ngoài `catch` hiện tại.

### 11.4 Logging sai luồng hoặc sai thời điểm

Trong async code, nơi exception phát sinh có thể ở worker, nơi `get()`/`join()` báo lại ở request thread. Hai stack khác nhau là bình thường. Đặt debugger ở cả source task và boundary future; ghi request context được truyền qua async boundaries, không trông chờ thread-local tự xuyên qua mọi executor.

### 11.5 Exception bị thay thế hoặc mất cause

~~~java
catch (IOException ex) {
    throw new RuntimeException("Operation failed"); // Đã đánh mất cause.
}
~~~

Pseudo-snippet này cần đặt trong ngữ cảnh phương thức có IOException. Dạng nên ưu tiên khi chuyển mức abstraction:

~~~java
catch (IOException ex) {
    throw new RuntimeException("Operation failed", ex);
}
~~~

Giữ nguyên nhân ban đầu cho debugger/log/APM. Tránh `throw new RuntimeException(ex.getMessage())` vì thường mất trace nguyên thủy và không thêm context.

## 12. Quy trình điều tra một sự cố thật từ đầu đến cuối

**Ví dụ:** user báo “thỉnh thoảng thao tác tạo hóa đơn trả 500”, trong log có vài `IllegalArgumentException` và JFR phát sinh rất nhiều `NumberFormatException`.

1. **Khóa phạm vi:** lấy 1–3 request IDs có lỗi, endpoint, payload đã ẩn dữ liệu, response status, thời gian và bản build. Xác định có thực sự 500 hay chỉ validation 400.
2. **Lập timeline:** nối access logs, error logs, tracing, thread/request context và JFR cùng khoảng thời gian; kiểm clock/timezone.
3. **Phân loại ban đầu:** `NumberFormatException` có thể phát sinh khi parser thử format rồi fallback, trong khi `IllegalArgumentException` ở service có thể là wrapper của `IOException`. Không chọn nguyên nhân từ tên nổi bật nhất.
4. **Reproduce:** tạo test input đã biết, dùng debugger với exception breakpoint loại liên quan. Ghi input/state tại điểm throw và caller path.
5. **Theo dấu handler:** kiểm tra catch parser có hợp lệ theo contract không; xem wrapper giữ cause không; xem controller/error handler map status thế nào; kiểm retry/transaction/future.
6. **Chỉ ra lỗi gốc cụ thể:** ví dụ “invoiceId không hợp lệ nhưng validator bỏ qua và repository nhận giá trị null; service wrap lỗi rồi handler trả 500” — có stack, line, input và đường lan truyền hỗ trợ.
7. **Sửa ở đúng tầng:** validation ở boundary để trả 400; không dùng catch-all trả 200; giữ cause/metric/log ở boundary. Tách các exception dự kiến khỏi hard failures nếu có thể.
8. **Kiểm thử hồi quy:** cùng input trước/sau, unit/integration test, response status đúng, không có silent success, retry/rollback đúng; kiểm log/metrics và overhead chẩn đoán.

### Bảng bằng chứng trước khi kết luận

| Quan sát | Có thể nói | Chưa thể nói |
| --- | --- | --- |
| Debugger dừng tại `throw` | Exception đã được ném ở code path đó | Request chắc chắn thất bại |
| Có `catch` cho exception | Exception có handler nào đó | Handler đã khôi phục thành công |
| Java stdout không có stack trace | Không có stack trace được in ở stdout/stderr quan sát | Không hề có exception |
| JFR có `jdk.JavaExceptionThrow` | Có event do cơ chế này ghi trên JVM đó | Throwable chắc chắn đã được ném thật hoặc chưa được catch |
| `CompletableFuture` hoàn thành exceptionally | Async operation thất bại theo contract future | Worker thread bị uncaught/tiến trình chết |
| Thread uncaught handler được gọi | Exception thoát khỏi `run` của thread | Toàn bộ JVM chắc chắn dừng |
| HTTP trả 200 sau một exception | API cuối cùng trả 200 | Internal work đã đúng và dữ liệu không hỏng |
| HTTP trả 500 nhưng exception được framework catch | Boundary đã tạo response lỗi | Không còn lỗi vì IDE đánh dấu caught |

## 13. Những sai lầm cần tránh

1. **Dừng ở mọi thrown exception rồi coi tất cả là bug.** Hãy xem handler và outcome; parser, framework, retry có thể dùng exceptions dự kiến.
2. **Cho rằng caught nghĩa là xử lý thành công.** Handler có thể rethrow, wrap, trả 500 hoặc rollback.
3. **Cho rằng uncaught luôn làm toàn bộ JVM exit.** Uncaught có thể chỉ kết thúc một thread; main và các thread khác vẫn chạy.
4. **Chỉ nhìn stack của wrapper.** Dò `getCause()` và `getSuppressed()`; root cause có thể nằm ở async/reflective tầng dưới.
5. **Nhầm creation stack với throw site.** `Throwable` thường giữ trace lúc tạo; JFR trên HotSpot có thể ghi event ngay lúc tạo mà chưa throw.
6. **Lấy số event JFR làm số request lỗi.** Một request có thể phát sinh nhiều exception; cả exception dự kiến và wrapper cũng có thể được ghi.
7. **Tin rằng `default.jfc` luôn bật JavaExceptionThrow.** Kiểm tra settings thực tế; nhiều preset mặc định không thu event tần suất cao.
8. **Bật exception tracing chi tiết toàn production vô thời hạn.** Nó có thể gây overhead CPU/file và lộ dữ liệu.
9. **Log rồi rethrow ở mọi tầng.** Tạo nhiều bản log cùng lỗi; chọn boundary phù hợp, giữ cause và correlation ID.
10. **Swallow exception và trả success để “giảm lỗi”.** Che mất bug, có thể gây dữ liệu sai hoặc mất transaction.
11. **Catch `Throwable` rồi bỏ qua `Error`.** Có thể giấu tình trạng runtime nặng và khiến hệ thống không còn an toàn.
12. **Bỏ `InterruptedException` mà không xử lý contract.** Có thể phá cơ chế hủy tác vụ/đóng ứng dụng.
13. **Mở remote debugger không kiểm soát.** JDWP có quyền truy cập cao; không expose cổng ra Internet.
14. **Đặt breakpoint trên mã không khớp build/source.** Stepping có thể dẫn đến sai line và kết luận sai.
15. **Không tái hiện với cùng request/build.** Exception type có thể giống nhưng nguyên nhân hoặc đường xử lý khác.
16. **Quên future.** Không gọi `get/join` hoặc không có callback quan sát có thể khiến job failed mà không có log rõ ràng.

## 14. Bài tập có đáp án

**Bài A.** `Integer.parseInt("x")` ném `NumberFormatException`; một `catch` trả fallback 8080, request vẫn thành công theo yêu cầu cấu hình tùy chọn. Bạn thấy breakpoint ở `parseInt`. Có phải incident không?

**Đáp án:** Chưa có bằng chứng incident. Đây có thể là một exception được xử lý bằng fallback hợp lệ. Cần kiểm contract (port tùy chọn thật hay không), kiểm rate nếu ảnh hưởng hiệu năng; không xóa handler chỉ vì debugger dừng.

**Bài B.** Controller throw `IllegalStateException`, middleware catch và trả HTTP 500. IDE ghi “caught”. Request đã thành công?

**Đáp án:** Không. Exception được bắt ở boundary để tạo response lỗi, nhưng request thất bại theo HTTP contract. Cần sửa nguyên nhân gốc hoặc map lỗi đúng, đồng thời metric 5xx phải phản ánh.

**Bài C.** JFR có event `jdk.JavaExceptionThrow` với message “constructed but not thrown”; code chỉ gọi `new IllegalArgumentException(...)`. Có chứng minh code đã ném exception?

**Đáp án:** Không. Trên HotSpot kiểm thử, event có thể phát sinh lúc tạo `Throwable`; cần debugger hoặc kiểm code path để xác minh `throw` thực tế.

**Bài D.** `CompletableFuture.runAsync` ném `UnsupportedOperationException`, main không gọi `get`/`join`. Không có stderr. Công việc thành công?

**Đáp án:** Không thể kết luận thành công; future có thể completed exceptionally. Quan sát future result và bảo đảm lỗi được ghi nhận/handle theo contract.

**Bài E.** `new RuntimeException("failed", cause)` xuất hiện trong stack, nhưng cause là `IOException("config missing")`. Nên debug vị trí nào?

**Đáp án:** Kiểm cả chỗ wrap và nguyên nhân sâu hơn tại `readConfig`, xem input/cấu hình/quyền filesystem; không chỉ sửa nơi tạo wrapper.

**Bài F.** Một thread tự tạo ném `IllegalStateException` ra khỏi `run()`. Uncaught handler đã ghi nhận, main vẫn chạy. Có mâu thuẫn?

**Đáp án:** Không. Uncaught là tương đối theo thread; nó không đảm bảo JVM phải dừng. Phải đánh dấu tác vụ thất bại và quyết định recovery/restart theo nghiệp vụ.

**Bài G.** Trong try-with-resources, `read` ném `IOException("read failed")` và `close` ném `IOException("close failed")`. Tìm lỗi thứ hai ở đâu?

**Đáp án:** Trong `getSuppressed()` của lỗi chính, không mặc định ở `getCause()`. `printStackTrace()` thường hiển thị suppressed; không quên kiểm nguồn lỗi cleanup.

**Bài H.** Bạn tắt caught exceptions trong IDE và debugger không dừng nữa, trong khi logs cho thấy retry rate tăng. Có thể khẳng định không có throw?

**Đáp án:** Không. Bạn chỉ đổi **bộ lọc debugger**. Các exceptions được bắt để retry có thể vẫn liên tục xảy ra; cần xem runtime metrics, logs hoặc cấu hình breakpoint phù hợp.

## Ghi nhớ

- **Exception xuất hiện ở đâu?** Dùng exception breakpoint, local variables, stack và code path để tìm nơi ném; trace lưu trong `Throwable` đôi khi phản ánh nơi tạo.
- **Đi đâu sau khi ném?** Theo dõi handler, rethrow, wrapper/cause, asynchronous future và thread boundary.
- **Kết cục nào là đúng?** Xác minh fallback hợp lệ, HTTP/job result, retry/rollback, logging và test. **Caught không bằng success; thrown không bằng incident**.
- **JFR có bằng chứng gì?** Nó ghi sự kiện theo template và semantics của HotSpot/JDK, nhưng không tự cung cấp trạng thái “handled/unhandled”. Event `jdk.JavaExceptionThrow` thậm chí có thể xuất hiện khi chỉ khởi tạo exception.
- **Điều tra có giới hạn và có thể tái hiện**: lọc loại exception, thu dữ liệu ngắn/đúng thời điểm, giữ cause, không tạo duplicate logs, bảo vệ quyền debugger và dữ liệu nhạy cảm.

### Tài liệu tham khảo

- Oracle Java 21, `jdb` / Exceptions: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdb.html
- Oracle Java 21, `Throwable` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html
- Oracle Java 21, `CompletableFuture` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Oracle Java 21, `CompletionException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionException.html
- Oracle Java 21, `Thread.UncaughtExceptionHandler`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html
- Oracle Java 21, `jdk.jfr` event configuration: https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html
- Oracle Java 21, `jfr` command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html
