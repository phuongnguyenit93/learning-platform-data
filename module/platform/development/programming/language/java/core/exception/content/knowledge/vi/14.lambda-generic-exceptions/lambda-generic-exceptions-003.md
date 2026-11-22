# Runnable, Callable và khác biệt về khai báo ngoại lệ trong Java

> **Java Core – Exception** · Nhóm: **Lambda và generic** · Trọng tâm: hợp đồng `throws` của hàm mục tiêu, cách lambda xử lý checked exception, và cách exception truyền từ tác vụ sang caller qua `Future`. Nội dung áp dụng cho Java 17+.

## 1. Câu trả lời cốt lõi

`Runnable` và `Callable<V>` đều là **functional interface**, vì vậy có thể tạo implementation bằng lambda. Nhưng hai interface có chữ ký khác nhau:

~~~java
// Hợp đồng cốt lõi của java.lang.Runnable:
void run();

// Hợp đồng cốt lõi của java.util.concurrent.Callable<V>:
V call() throws Exception;
~~~

Đây là **hai khai báo chữ ký minh họa**, không phải một file Java độc lập.

Chúng khác nhau ở **hai khía cạnh độc lập**:

1. **Kết quả:** `Runnable.run()` trả `void`; `Callable<V>.call()` trả giá trị kiểu `V`.
2. **Checked exception:** `Runnable.run()` **không khai báo checked exception**; `Callable<V>.call()` khai báo `throws Exception`. Một lambda hoặc implementation của `Callable<V>` có thể để checked exception phù hợp thoát ra từ `call()`; lambda/implementation của `Runnable` phải **tự xử lý** checked exception không được phép khai báo trong hợp đồng `run()`.

**Cực kỳ quan trọng:** `Runnable` vẫn có thể ném **unchecked exception** như `IllegalStateException` hoặc `UncheckedIOException`. Không có `throws` **không có nghĩa là không bao giờ phát sinh lỗi**.

Đồng thời, `Callable.call() throws Exception` không có nghĩa nó **luôn ném exception**. Nó có thể trả kết quả bình thường; nó cũng có thể ném unchecked exception. Mệnh đề `throws` nêu giới hạn checked exception mà phương thức có thể truyền ra theo hệ thống kiểu Java, không phải mô tả một sự kiện chắc chắn xảy ra.

### So sánh nhanh

| Đặc điểm | `Runnable` | `Callable<V>` |
| --- | --- | --- |
| Functional method | `void run()` | `V call() throws Exception` |
| Giá trị trả về | Không có | Có kiểu `V`, ví dụ `String`, `Integer` |
| Cho phép checked exception thoát ra trực tiếp? | Không, do chữ ký `run()` | Có, trong giới hạn `throws Exception` |
| Có thể ném unchecked exception? | Có | Có |
| Dùng trực tiếp với `new Thread(...)`? | Có | Không; cần chuyển thành `Runnable` hoặc dùng cơ chế khác |
| Gửi đến `ExecutorService.submit`? | Có | Có |
| `submit` trả về | `Future<?>`; `get()` thành công trả `null` | `Future<V>`; `get()` thành công trả giá trị `V` |
| Lỗi của task khi truy qua `Future.get()` | Thường nằm trong `ExecutionException.getCause()` | Cũng nằm trong `ExecutionException.getCause()` |

Bảng về `Future` áp dụng cho các tác vụ gửi bằng overload `submit(Runnable)` và `submit(Callable<T>)`, **không áp dụng nguyên xi cho việc gọi `run()` hay `call()` trực tiếp**.

## 2. Tại sao lambda còn phải quan tâm tới throws?

Một biểu thức lambda trong Java không có kiểu “tự tồn tại” độc lập. Nó được **target-typed** theo functional interface ở vị trí được sử dụng. Chính chữ ký của **functional method** quyết định kiểu tham số, kiểu kết quả và các checked exception mà body của lambda được phép để thoát ra.

Ví dụ:

~~~java
import java.io.IOException;
import java.util.concurrent.Callable;

class Illustrations {
    static String read() throws IOException {
        throw new IOException("unavailable");
    }

    static void example() {
        Callable<String> task = () -> read(); // Hợp lệ.
    }
}
~~~

Đây là một class minh họa hợp lệ. Lambda có target type `Callable<String>`, nên body gọi `read()` có thể ném `IOException`; `call()` cho phép `Exception`, là lớp cha của `IOException`.

Ngược lại:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH; đặt trong ngữ cảnh có read() throws IOException:
Runnable task = () -> {
    read(); // Unhandled exception type IOException.
};
~~~

Target type lúc này là `Runnable`. Phương thức chức năng `run()` **không có checked throws**, nên body lambda không được để `IOException` thoát ra. Việc `Runnable` có thể chạy trên thread riêng **không làm compiler miễn trừ quy tắc**.

Đây không phải hạn chế riêng của lambda. Một class implements Runnable cũng chịu quy tắc override tương tự:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
class BadTask implements Runnable {
    @Override
    public void run() throws java.io.IOException {
        throw new java.io.IOException("failed");
    }
}
~~~

Lý do: override không được thêm checked exception mới vượt quá hợp đồng `Runnable.run()`.

**Kết luận:** quyết định có thể để checked exception thoát ra phải dựa vào **kiểu phương thức được triển khai**, không phải lambda có dấu ngoặc, không phải nó có chạy bất đồng bộ hay không.

## 3. Phân biệt checked với unchecked khi đọc API

Theo [JLS Java 17 chương 11](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html), checked exception phải được bắt hoặc khai báo thích hợp; unchecked exception không phải chịu nghĩa vụ khai báo tại compile time.

~~~text
Throwable
├── Error                         → unchecked
└── Exception
    ├── IOException               → checked
    ├── InterruptedException      → checked
    ├── ExecutionException        → checked
    └── RuntimeException          → unchecked
        ├── IllegalStateException
        ├── IllegalArgumentException
        └── UncheckedIOException
~~~

Đây là **cây rút gọn** chỉ những lớp liên quan; không phải toàn bộ hierarchy.

Ví dụ phương thức:

~~~java
static String load() throws java.io.IOException {
    throw new java.io.IOException("I/O failed");
}
~~~

Trong lambda `Callable<String>`, có thể gọi `load()` và để IOException thoát ra. Trong lambda `Runnable`, cần bắt, xử lý hoặc chuyển đổi nó sang unchecked exception **có chủ đích**.

Một `RuntimeException` có thể xuất hiện từ cả hai loại lambda dù không có mệnh đề `throws` tường minh. Không nên gán nhãn “Runnable không thể throw” chỉ vì nhìn thấy `void run()`.

## 4. Lựa chọn Runnable hay Callable theo hợp đồng tác vụ

Nên chọn dựa trên **nhu cầu của caller**, không chỉ dựa trên việc viết được lambda ngắn hơn.

### Chọn Runnable khi

- Tác vụ **không cần trả kết quả** qua functional method.
- Các checked exception phát sinh bên trong có thể được **xử lý tại chỗ**, hoặc có chính sách chuyển sang unchecked phù hợp.
- Chỉ cần gọi trực tiếp `run()`, dùng `Thread`, `Executor.execute` hoặc `ExecutorService.submit(Runnable)`.

Ví dụ:

~~~java
Runnable announce = () -> System.out.println("Task completed");
announce.run();
~~~

Output:

~~~text
Task completed
~~~

Ví dụ này **chạy đồng bộ** trong thread gọi khi sử dụng `announce.run()`. Bản thân đối tượng Runnable không tự tạo thread mới. Muốn lập lịch hoặc chạy thread riêng phải dùng một cơ chế như `new Thread(announce).start()` hoặc executor.

### Chọn Callable khi

- Tác vụ cần **trả về một giá trị** có kiểu.
- Body có thể để **checked exception** thoát ra theo hợp đồng `call() throws Exception`.
- Caller có kế hoạch nhận kết quả bằng `Future<V>`, hoặc gọi `call()` trực tiếp trong ngữ cảnh xử lý `Exception`.

Ví dụ:

~~~java
Callable<Integer> count = () -> 42;
~~~

Đoạn minh họa cần import `java.util.concurrent.Callable`. Kiểu generic `Integer` được dùng làm giá trị trả về của `call()`. Compiler không yêu cầu lambda có một checked exception cụ thể; nó chỉ **cho phép** kiểu phù hợp nếu có.

### Callable<Void> có phải tương đương hoàn toàn với Runnable?

Không. Khi không cần kết quả nhưng muốn giữ hợp đồng checked exception, có thể dùng:

~~~java
Callable<Void> task = () -> {
    performWork();
    return null;
};
~~~

Đây là đoạn minh họa, cần có `performWork()` phù hợp và import Callable. Nó trả về `null` vì kiểu `Void` không đại diện một giá trị kết quả thông thường. Tuy nhiên **chữ ký của functional method vẫn là `call() throws Exception`**, khác `Runnable.run()`. Do đó hai interface không hoàn toàn tương đương chỉ vì kết quả có thể là null.

## 5. Ví dụ Java 17 hoàn chỉnh: năm tình huống phân biệt

Tạo file **`RunnableCallableExceptionDemo.java`**. Chương trình minh họa cả Runnable, Callable, checked exception, cách bọc IOException thành unchecked và trường hợp `Callable<Void>`.

Dùng một `ExecutorService` có **một worker thread** và chờ từng Future trước khi chuyển sang bước tiếp theo, để output dễ kiểm chứng, không phụ thuộc thứ tự tranh chấp giữa nhiều task.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RunnableCallableExceptionDemo {
    private static String read(String key) throws IOException {
        if ("fail".equals(key)) {
            throw new IOException("file unavailable");
        }
        return "DATA:" + key;
    }

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        Runnable plain = () -> System.out.println("runnable=done");

        Callable<String> successful = () -> read("ok");
        Callable<String> checkedFailure = () -> read("fail");

        Runnable adapted = () -> {
            try {
                read("fail");
            } catch (IOException ex) {
                throw new UncheckedIOException("runnable I/O failure", ex);
            }
        };

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            System.out.println("== successful jobs ==");
            Future<?> plainFuture = executor.submit(plain);
            System.out.println("runnable-result=" + plainFuture.get());

            Future<String> callFuture = executor.submit(successful);
            System.out.println("callable-result=" + callFuture.get());

            System.out.println("== checked exception from Callable ==");
            Future<String> checkedFuture = executor.submit(checkedFailure);
            try {
                checkedFuture.get();
            } catch (ExecutionException ex) {
                System.out.println("wrapper=" + ex.getClass().getSimpleName());
                Throwable cause = ex.getCause();
                System.out.println("cause=" + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
            }

            System.out.println("== checked exception adapted to Runnable ==");
            Future<?> adaptedFuture = executor.submit(adapted);
            try {
                adaptedFuture.get();
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println("cause=" + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
                System.out.println("root="
                        + cause.getCause().getClass().getSimpleName()
                        + ": " + cause.getCause().getMessage());
            }

            System.out.println("== Callable<Void> ==");
            Callable<Void> noValue = () -> {
                System.out.println("callable-void=done");
                return null;
            };
            System.out.println("void-result=" + executor.submit(noValue).get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

### Biên dịch và chạy

Sử dụng JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 RunnableCallableExceptionDemo.java
java RunnableCallableExceptionDemo
~~~

**Stdout chính xác, đã chạy và đối chiếu:**

~~~text
== successful jobs ==
runnable=done
runnable-result=null
callable-result=DATA:ok
== checked exception from Callable ==
wrapper=ExecutionException
cause=IOException: file unavailable
== checked exception adapted to Runnable ==
cause=UncheckedIOException: runnable I/O failure
root=IOException: file unavailable
== Callable<Void> ==
callable-void=done
void-result=null
~~~

Ví dụ **đã được biên dịch bằng `javac --release 17` và thực thi thành công**. Nó không cần file thực hoặc mạng; method `read()` mô phỏng thành công/thất bại với message cố định. Để dễ theo dõi, các tác vụ được gửi và chờ kết quả theo từng bước; output không dựa trên tên thread hoặc thứ tự scheduling ngẫu nhiên.

**Chú ý môi trường Java 17:** `ExecutorService` trong ví dụ được đóng lịch làm việc bằng `shutdown()` trong `finally`. Đừng tự dùng `try (ExecutorService ...)` nếu đang yêu cầu mã biên dịch theo Java 17; việc hỗ trợ `AutoCloseable` trên interface này ở các phiên bản Java mới hơn không thay đổi tương thích nguồn của Java 17.

## 6. Phân tích stdout: thành công với Runnable và Callable

### 6.1. Runnable không trả giá trị, nhưng Future.get() vẫn tồn tại

Phần:

~~~java
Runnable plain = () -> System.out.println("runnable=done");
Future<?> plainFuture = executor.submit(plain);
System.out.println("runnable-result=" + plainFuture.get());
~~~

Có hai tầng hành vi khác nhau:

- `Runnable.run()` bản thân có kiểu trả về `void`, không tạo một đối tượng kết quả.
- `ExecutorService.submit(Runnable)` **trả về `Future<?>` để theo dõi trạng thái hoàn thành**; nếu tác vụ hoàn thành bình thường, `get()` trả `null`.

Khi chạy, task in `runnable=done` trước. Sau khi `plainFuture.get()` trả về, caller in `runnable-result=null`.

**Không nên nhầm:** không phải lambda Runnable “trả về null”; giá trị `null` là **kết quả do overload submit(Runnable) quy định cho Future**, còn functional method vẫn là `void run()`.

### 6.2. Callable<String> trả String qua Future<String>

Phần:

~~~java
Callable<String> successful = () -> read("ok");
Future<String> callFuture = executor.submit(successful);
System.out.println("callable-result=" + callFuture.get());
~~~

Ở thời điểm thực thi, `read("ok")` trả `"DATA:ok"`. Vì callable thành công, `Future.get()` trả chính chuỗi này. Lúc biên dịch, generic `String` giúp caller biết kết quả có kiểu chuỗi, không phải `Object` phải ép kiểu thủ công.

Tham số kiểu `V` của `Callable<V>` mô tả **kiểu giá trị trả về**; nó **không phải** tham số generic mô tả kiểu exception. Chữ ký của `call()` vẫn khai báo `throws Exception` bất kể V là `String`, `Integer` hay `Void`.

## 7. Callable ném IOException: Future.get() truyền lỗi thế nào?

Phần:

~~~java
Callable<String> checkedFailure = () -> read("fail");
Future<String> checkedFuture = executor.submit(checkedFailure);
try {
    checkedFuture.get();
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    System.out.println(cause.getClass().getSimpleName());
}
~~~

Phân tích từng bước:

1. Body lambda có target type `Callable<String>`, nên lệnh gọi `read("fail")` được phép để `IOException` thoát ra khỏi `call()`.
2. Executor chạy callable trong worker thread.
3. `read("fail")` ném `IOException("file unavailable")`.
4. Tác vụ hoàn thành **thất bại**. Khi caller gọi `Future.get()`, API ném `ExecutionException`, với **cause là Throwable gốc** từ tác vụ.
5. Caller đọc `ex.getCause()` để biết nguyên nhân chính xác; trong chương trình là `IOException`.

Stdout có:

~~~text
wrapper=ExecutionException
cause=IOException: file unavailable
~~~

**Đây không phải lỗi Java tự biến `IOException` thành `ExecutionException` lúc lời gọi `call()` được khai báo.** Việc bọc xảy ra ở **ranh giới lấy kết quả thông qua Future**. Nếu bạn gọi trực tiếp `checkedFailure.call()` trong cùng thread, ngoại lệ gốc có thể được ném thẳng ra caller của `call()` và phải xử lý theo chữ ký `throws Exception`; không có quy tắc tự động bọc qua `ExecutionException` chỉ vì đối tượng là Callable.

### Caller cần bắt những checked exception nào tại get()?

Chữ ký quan trọng của `Future.get()`:

~~~java
V get() throws InterruptedException, ExecutionException;
~~~

Đây là chữ ký rút gọn theo kiểu V của Future, không phải file độc lập.

- `InterruptedException`: **thread đang chờ get** bị interrupt trong khi chờ. Không nhất thiết là lỗi từ body callable.
- `ExecutionException`: **task thất bại**; xem `getCause()` để biết Throwable do task ném.
- `CancellationException`: unchecked, có thể xảy ra nếu Future đã bị hủy.
- `get()` có thể chặn đến khi task hoàn thành; overload có timeout còn có thể ném `TimeoutException`.

Đừng viết `catch (IOException)` trực tiếp quanh `future.get()` với kỳ vọng nó nhận IOException từ callable. Bên ngoài Future, API chuyển thất bại của task qua `ExecutionException`.

## 8. Runnable gặp IOException: phải xử lý tại lambda

Ví dụ chương trình chính:

~~~java
Runnable adapted = () -> {
    try {
        read("fail");
    } catch (IOException ex) {
        throw new UncheckedIOException("runnable I/O failure", ex);
    }
};
~~~

Tại sao phải bắt `IOException`? Vì `Runnable.run()` không cho checked `IOException` thoát ra. Tại sao có thể `throw new UncheckedIOException(...)`? Vì `UncheckedIOException extends RuntimeException`, thuộc nhóm unchecked.

Việc chọn wrapper cần rõ ràng:

- Nó **không hề làm thao tác đọc thành công**; lỗi vẫn lan ra.
- Nó thay đổi **hợp đồng truyền lỗi từ checked sang unchecked**.
- Constructor nhận cause giúp giữ `IOException` ban đầu cho chẩn đoán.
- Nếu một hệ thống có khả năng phục hồi lỗi I/O ngay bên trong task, có thể **xử lý tại chỗ** thay vì wrap.
- Không nên “bắt IOException rồi bỏ qua” chỉ để Runnable biên dịch; làm như vậy có thể gây thành công giả.

Khi gửi Runnable lỗi bằng `executor.submit(adapted)`, worker thread ném `UncheckedIOException`. Khi caller gọi `Future.get()`, nó nhận `ExecutionException` với cause là `UncheckedIOException` và **cause của UncheckedIOException** là `IOException` gốc.

~~~text
ExecutionException
  └── UncheckedIOException("runnable I/O failure")
        └── IOException("file unavailable")
~~~

Đó là lý do stdout phân biệt hai dòng:

~~~text
cause=UncheckedIOException: runnable I/O failure
root=IOException: file unavailable
~~~

### Tại sao không ném trực tiếp IOException từ Runnable bằng casts?

Không nên sử dụng “sneaky throw”, generic casting đánh lừa compiler, reflection hay các thủ thuật bypass checked exception chỉ để truyền IOException ra ngoài `Runnable.run()`. Chúng làm chữ ký công khai không phản ánh kỳ vọng của caller và khiến code khó hiểu/khó bảo trì.

Khi có một tác vụ thực sự cần ném checked exception, **sử dụng Callable hoặc functional interface tự định nghĩa với throws phù hợp** là lựa chọn rõ ràng hơn. Nếu framework bắt buộc Runnable, hãy chọn policy xử lý hoặc wrapper unchecked có nguyên nhân rõ.

## 9. Callable<Void> khi cần throws nhưng không cần dữ liệu trả về

Chữ ký Callable luôn trả kiểu V. Nếu chỉ cần khai báo nghĩa vụ checked exception mà không có kết quả hữu ích, dùng `Callable<Void>`:

~~~java
Callable<Void> task = () -> {
    saveDocument();
    return null;
};
~~~

Đây là **đoạn minh họa**; cần import Callable và định nghĩa `saveDocument()`. Lambda phải có nhánh `return null;` cho đường hoàn thành bình thường. Vì target type là `Callable<Void>`, phương thức `saveDocument()` có thể ném checked exception phù hợp.

Trong chương trình runnable, task được khai báo:

~~~java
Callable<Void> noValue = () -> {
    System.out.println("callable-void=done");
    return null;
};
System.out.println("void-result=" + executor.submit(noValue).get());
~~~

Khi hoàn thành bình thường, Future trả `null`. So với Runnable:

- Hai loại đều có thể tạo Future với kết quả null.
- Nhưng **chữ ký chức năng** khác nhau: `Callable<Void>.call() throws Exception` so với `Runnable.run()` không checked throws.
- Callback API yêu cầu Runnable **không tự động nhận Callable<Void>**. Cần adapter hoặc đổi overload phù hợp.

## 10. Khác biệt giữa gọi trực tiếp và gửi qua executor

Cần phân biệt **ba ngữ cảnh**:

| Cách thực thi | Chạy ở đâu | Nhận kết quả | Ngoại lệ |
| --- | --- | --- | --- |
| `runnable.run()` | Thread hiện tại | Không có | Unchecked lan trực tiếp nếu không bắt |
| `callable.call()` | Thread hiện tại | Giá trị V trực tiếp | Có thể lan checked `Exception` theo chữ ký |
| `executor.submit(runnable)` | Thread do executor quản lý | `Future<?>` trả null khi thành công | Thất bại phản ánh qua `ExecutionException` khi `get()` |
| `executor.submit(callable)` | Thread do executor quản lý | `Future<V>` | Thất bại phản ánh qua `ExecutionException` khi `get()` |
| `executor.execute(runnable)` | Theo executor | Không có Future | Xử lý unchecked tùy implementation/uncaught handling; không có `Future.get()` để quan sát |
| `new Thread(runnable).start()` | Thread mới | Không có Future | Uncaught exception của thread theo cơ chế handler của Thread/JVM |

Điểm dễ nhầm: **`executor.execute(runnable)` và `executor.submit(runnable)` không cung cấp cùng cơ chế quan sát exception.** Với `submit`, executor trả Future; lỗi task được truy xuất khi gọi `get()`. Với `execute`, caller không nhận Future từ API đó, nên không thể dựa trên `get()` để biết tác vụ thất bại.

Ngoài ra, `new Thread(callable)` không phải overload chuẩn nhận Callable. Muốn chạy Callable bằng Thread trực tiếp, có thể dùng `FutureTask<V>` (vừa Runnable vừa Future) hoặc đơn giản hơn là sử dụng ExecutorService nếu mục tiêu là nộp task và nhận kết quả.

### Thread và runnable có khác biệt về checked exception không?

Không: `Runnable.run()` **vẫn là cùng một chữ ký** dù chạy trực tiếp, trên Thread hay trong executor. Lập lịch trên thread khác không cho phép lambda Runnable tự nhiên ném checked IOException mà không xử lý.

### Callable không đồng nghĩa bất đồng bộ

`callable.call()` là lời gọi bình thường, chạy ở thread hiện tại nếu được gọi trực tiếp. Chỉ khi gửi cho executor hoặc cơ chế khác mới có thực thi do framework/lịch trình kiểm soát. Tương tự `runnable.run()` chỉ là gọi method bình thường.

## 11. Generics đóng vai trò gì trong Callable<V>?

Xét:

~~~java
Callable<String> textTask = () -> "hello";
Callable<Integer> numberTask = () -> 123;
Callable<Void> actionTask = () -> {
    System.out.println("done");
    return null;
};
~~~

Đây là **đoạn minh họa**, cần import Callable. Kết quả của `call()` lần lượt là String, Integer, Void; Java compiler kiểm tra kiểu return trong lambda theo target type.

Tuy nhiên, mọi bản thể hóa vẫn dùng functional method có khai báo `throws Exception`. Không có tham số generic kiểu `E extends Exception` được Callable chuẩn dùng để chỉ loại checked exception cụ thể.

Nếu cần contract hẹp hơn, bạn có thể tự định nghĩa:

~~~java
@FunctionalInterface
interface IoTask<T> {
    T execute() throws java.io.IOException;
}
~~~

Đây là định nghĩa interface hợp lệ, có thể đặt trong class hoặc file riêng. Lambda gán cho `IoTask<String>` được phép ném IOException, nhưng **không được tùy tiện ném SQLException checked** vì hợp đồng chỉ cho IOException.

Chú ý rằng `IoTask<T>` **không phải Callable<T>** chỉ vì có chữ ký gần giống. Muốn dùng API nhận Callable, cần chuyển đổi:

~~~java
IoTask<String> io = () -> readData();
Callable<String> callable = io::execute;
~~~

Đoạn minh họa này cần `readData()` phù hợp và import Callable. Method reference `io::execute` có checked IOException nhưng Callable cho phép Exception nên hợp lệ.

**Nguyên tắc chung:** Checked-exception compatibility được compiler phân tích tại **functional target** của lambda hoặc method reference; generics xác định kiểu dữ liệu, không tự “xóa” giới hạn `throws`.

## 12. Adapter từ functional interface cho phép checked exception sang Runnable

Nếu một API thực sự chỉ chấp nhận `Runnable`, có thể viết adapter tập trung thay vì lặp `try/catch` trong từng lambda.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;

@FunctionalInterface
interface IoAction {
    void run() throws IOException;
}

class Adapters {
    static Runnable asRunnable(IoAction action) {
        return () -> {
            try {
                action.run();
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }
}
~~~

Đây là **đoạn Java hợp lệ để minh họa**, chưa có main. Cách sử dụng ở nơi có phương thức ném IOException:

~~~java
Runnable task = Adapters.asRunnable(() -> readInput());
~~~

Tên `readInput()` cần được định nghĩa. Adapter chỉ thay đổi cách exception được trình bày qua `Runnable.run()`, **không biến một IOException thành kết quả thành công**.

Rủi ro cần cân nhắc:

- Caller của Runnable có thể không biết về wrapper nếu API không được tài liệu hóa.
- Nếu lỗi có thể xử lý tại nơi tạo task, bắt và phục hồi có thể hợp lý hơn bọc rồi lan.
- Với `InterruptedException` không nên wrap mù mà bỏ qua trạng thái interrupt; xem phần 14.
- Nếu nghiệp vụ cần dữ liệu trả về hoặc muốn giữ checked exception dưới dạng gốc, Callable thường đơn giản hơn adapter.

## 13. Cẩn thận khi dùng lambda trong overload nhận Runnable/Callable

Một API có thể có các overload như:

~~~java
Future<?> submit(Runnable task);
<T> Future<T> submit(Callable<T> task);
~~~

Đây là **hai chữ ký API rút gọn** của ExecutorService. Java dùng target typing và quy tắc overload resolution để quyết định lambda ứng với functional interface nào.

Ví dụ có kiểu khai báo tường minh:

~~~java
Runnable r = () -> process();
Callable<String> c = () -> load();
~~~

Hai lời gọi `process()` và `load()` là tên tượng trưng. Với target được chỉ rõ, compiler biết `r` là Runnable (không cho checked throws) và `c` là Callable<String> (cho Exception).

Nếu đưa lambda trực tiếp vào một phương thức overloaded và compiler báo **ambiguous** hoặc lỗi tương thích throws/return type, đừng cố giải bằng cách “bỏ checked exception” từ body. Hãy đặt biến có kiểu `Runnable` / `Callable<T>` hoặc cast lambda về target phù hợp:

~~~java
executor.submit((Callable<String>) () -> load());
~~~

Đoạn này minh họa; `executor` và `load()` cần khai báo. Việc chọn target type cũng chọn luôn **hợp đồng checked exception** mà body có thể để thoát ra.

**Không dùng việc ép target type chỉ để lừa caller**: kiểm tra kỹ liệu tác vụ phải có kết quả, có checked exception và cách xử lý failure sau khi chạy.

## 14. InterruptedException khi đợi Future không phải IOException từ task

`Future.get()` có thể ném `InterruptedException` khi **thread đang chờ kết quả** bị interrupt. Đây là checked exception riêng với exception do callable ném.

Một cách xử lý phù hợp tại nơi không thể truyền tiếp `InterruptedException`:

~~~java
try {
    String value = future.get();
    use(value);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Dừng hoặc báo hủy phù hợp với luồng điều khiển ứng dụng.
    return;
} catch (ExecutionException ex) {
    handleTaskFailure(ex.getCause());
}
~~~

Đây là **đoạn minh họa**, đặt trong method có kiểu return phù hợp với `return;` và có định nghĩa `future/use/handleTaskFailure`, import tương ứng.

**Vì sao gọi `Thread.currentThread().interrupt()`?** Khi thao tác chờ phát sinh InterruptedException, cờ interrupt thường bị xóa khi exception được ném. Nếu method không thể khai báo/lan truyền InterruptedException, việc phục hồi cờ cho tầng trên biết yêu cầu ngắt là một chính sách phổ biến. Sau đó nên **dừng công việc đang làm**, tránh tiếp tục xử lý như thể không có gì xảy ra.

Nếu method có thể khai báo `throws InterruptedException` và trách nhiệm được giao cho caller, **truyền tiếp checked exception** thường rõ ràng hơn việc bắt rồi bỏ qua.

Không nên viết:

~~~java
// MẪU XẤU: nuốt yêu cầu interrupt.
try {
    future.get();
} catch (InterruptedException ex) {
    // Bỏ qua, tiếp tục bình thường.
}
~~~

Đây là đoạn minh họa anti-pattern, chưa xử lý ExecutionException nên không phải chương trình độc lập. Ý chính là **không âm thầm bỏ qua interrupt** trong môi trường concurrency.

## 15. Timeout và hủy task không làm thay đổi throws của Runnable/Callable

`Future.get(timeout, unit)` còn có thể ném `TimeoutException` nếu hết thời gian chờ mà task chưa hoàn tất. **Timeout khi chờ** không tự đồng nghĩa task đã bị dừng.

Nếu ứng dụng quyết định hủy:

~~~java
future.cancel(true);
~~~

thì đây là một **yêu cầu hủy**, có thể interrupt thread đang chạy nếu task cho phép và backend hỗ trợ. Không có bảo đảm rằng mọi thao tác I/O/CPU sẽ dừng lập tức. Task cần hợp tác với interruption/cancellation khi thiết kế.

Các ngoại lệ tại boundary này cần phân biệt:

- `ExecutionException`: task đã hoàn thành thất bại, xem cause.
- `InterruptedException`: thread chờ bị interrupt.
- `TimeoutException`: chưa lấy được kết quả trong khoảng thời gian quy định.
- `CancellationException`: Future bị hủy.
- Unchecked exception từ chính task: nhìn từ `Future.get()` của task submit, thường được bọc trong ExecutionException, không tự xuất hiện trực tiếp như lời gọi method.

Đừng suy rằng khai báo `Callable.call() throws Exception` là nguyên nhân khiến `Future.get()` có thể ném InterruptedException hoặc TimeoutException. Chúng đến từ **cơ chế chờ và quản lý task**, không phải yêu cầu riêng của business method.

## 16. Lập lịch, shutdown và quan sát ngoại lệ

Một ví dụ task có thể chạy đúng nhưng chương trình vẫn quản lý executor sai nếu quên shutdown. Với Java 17:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    Future<String> result = executor.submit((Callable<String>) () -> "done");
    System.out.println(result.get());
} finally {
    executor.shutdown();
}
~~~

Đây là **đoạn minh họa** trong method có xử lý/khai báo `InterruptedException` và `ExecutionException`, import các API concurrency. `shutdown()` báo executor ngừng nhận công việc mới và tiếp tục xử lý các task đã được nhận theo chính sách của executor; **nó không bắt buộc chờ mọi task hoàn thành**. Nếu ứng dụng cần đợi tài nguyên thực sự dừng, phải có chính sách `awaitTermination(...)`, timeout và xử lý interrupt thích hợp.

Trong chương trình chính, mọi Future đã được `get()` xử lý trước `shutdown()`, nên các tác vụ ví dụ đã hoàn tất và output rõ ràng.

Với ứng dụng dài hạn, cân nhắc thêm monitoring, bounded queue, chính sách từ chối task, cancellation, timeout và cách log Throwable. Các yêu cầu đó là **thiết kế concurrency cấp ứng dụng**, không thay đổi chữ ký `Runnable.run()` hoặc `Callable.call()`.

## 17. Những hiểu nhầm phổ biến

1. **“Runnable không bao giờ ném exception.”** Sai: có thể ném unchecked exception; không được tự để checked exception mới thoát ra.
2. **“Callable bắt buộc phải ném checked exception.”** Sai: `throws Exception` là khả năng, không phải nghĩa vụ luôn ném.
3. **“Chỉ có task chạy trên thread mới chịu quy tắc checked exception.”** Sai: compiler kiểm tra lambda/override bất kể chạy trực tiếp hay bất đồng bộ.
4. **“Gán cùng lambda cho Runnable hoặc Callable không liên quan tới throws.”** Sai: target type quyết định hợp đồng checked throws.
5. **“Runnable.run trả null.”** Sai: `run()` là void; `Future.get()` của `submit(Runnable)` thành công trả null.
6. **“Callable<Void> và Runnable là một interface.”** Sai: functional method và checked throws khác nhau.
7. **“Callable<String> nghĩa là chỉ ném StringException.”** Sai: generic String là **kiểu kết quả**, không phải kiểu exception.
8. **“IOException từ callable sẽ bị bắt trực tiếp bởi catch IOException quanh Future.get().”** Sai: Future.get báo task failure bằng `ExecutionException`; xem `getCause()`.
9. **“Nếu Future báo ExecutionException thì chính get() gây IOException trong worker.”** Sai: lỗi gốc phát sinh ở task, còn Future báo lỗi tại boundary chờ kết quả.
10. **“Bọc IOException thành UncheckedIOException làm biến mất nguyên nhân.”** Sai nếu constructor được truyền cause.
11. **“Bọc checked thành unchecked luôn là cách hay.”** Sai: phải xét chính sách caller và không nuốt lỗi.
12. **“Executor.execute và submit giống nhau về cách lấy exception.”** Sai: execute không trả Future.
13. **“new Thread(callable) là overload nhận Callable chuẩn.”** Sai: Thread nhận Runnable trong cách dùng này; cần adapter hoặc FutureTask.
14. **“InterruptedException từ get là exception từ nội dung Callable.”** Không nhất thiết; nó phản ánh thread chờ bị ngắt.
15. **“Bắt InterruptedException rồi bỏ qua là vô hại.”** Sai: có thể làm hỏng chính sách dừng/hủy tác vụ.
16. **“Future.get có timeout nghĩa là task đã tự bị hủy khi hết thời gian.”** Sai: timeout ở thao tác chờ không tự dừng task.
17. **“Runnable không cần shutdown executor.”** Sai: việc quản lý executor độc lập với loại task.
18. **“Cứ catch Exception trong Runnable là đủ.”** Bắt rộng có thể che bug; nên bắt đúng checked exception và có chính sách lỗi rõ.
19. **“Một exception xảy ra trong thread khác sẽ tự ném ở thread gọi submit.”** Sai: cần quan sát qua Future, handler hoặc cơ chế phù hợp.
20. **“Đổi target type sau này không ảnh hưởng source compatibility.”** Có thể ảnh hưởng, vì kiểu return và checked throws của functional method khác nhau.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `Runnable r = () -> Files.readString(path);` có thể gây lỗi compile-time?

*Đáp án:* `Files.readString` có thể ném checked IOException. Khi target type là Runnable, `run()` không khai báo checked exception nên phải xử lý lỗi tại lambda hoặc dùng target phù hợp.

**Câu 2.** Nếu đổi target thành `Callable<String>` thì lời gọi `Files.readString(path)` có thể hợp lệ không?

*Đáp án:* Có, vì functional method `call() throws Exception` cho phép IOException thoát ra, miễn các chi tiết kiểu kết quả và context khác hợp lệ.

**Câu 3.** Gọi `r.run()` có tự tạo thread mới không?

*Đáp án:* Không. Đây là method call bình thường trên thread đang gọi.

**Câu 4.** Kết quả `Future.get()` sau khi `submit(Runnable)` chạy bình thường là gì?

*Đáp án:* Null, với overload không chỉ định kết quả trả về của Runnable.

**Câu 5.** Nếu một callable ném IOException khi chạy trong executor, `Future.get()` ném gì?

*Đáp án:* `ExecutionException`, trong đó `getCause()` chứa IOException gốc.

**Câu 6.** Nếu một Runnable bắt IOException rồi ném UncheckedIOException, `Future.get()` của submit(Runnable) cho cause gì?

*Đáp án:* Cause trực tiếp của ExecutionException là UncheckedIOException; cause của UncheckedIOException là IOException đã được bọc.

**Câu 7.** Tại sao `Callable<Void>` vẫn cần `return null;` trên đường hoàn thành bình thường?

*Đáp án:* Functional method `call()` có kiểu trả về V; khi V là Void, lambda vẫn phải trả một giá trị tương thích (thường null) nếu có đường hoàn thành bình thường.

**Câu 8.** Một task hoàn thành thất bại có làm mọi lệnh `submit` trước đó ném trực tiếp lỗi gốc không?

*Đáp án:* Không. Nộp task và nhận kết quả là hai bước; phải quan sát Future/handler theo API.

**Câu 9.** InterruptedException từ `get()` nên được xử lý thế nào?

*Đáp án:* Lan truyền nếu contract cho phép, hoặc khôi phục cờ interrupt và dừng/thoát theo chính sách; không im lặng nuốt yêu cầu ngắt.

**Câu 10.** Một generic Callable<V> có tham số generic kiểu exception không?

*Đáp án:* Không. V mô tả kiểu kết quả; chữ ký checked throws là Exception không phụ thuộc V.

**Câu 11.** Khi API chỉ nhận Runnable nhưng việc xử lý cần ném IOException, có những lựa chọn nào?

*Đáp án:* Bắt và phục hồi hợp lệ, hoặc bọc vào một unchecked exception có cause rõ; nếu thay đổi được API, Callable hoặc custom throwing functional interface có thể tự nhiên hơn.

**Câu 12.** `executor.shutdown()` có tự đợi tất cả task kết thúc trước khi trả về không?

*Đáp án:* Không có bảo đảm chờ như vậy; để chờ cần thêm cơ chế thích hợp như `awaitTermination()` hoặc đợi Future, kèm chính sách timeout/interrupt.

## 19. Tài liệu chính thức Java 17

- [API Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): chữ ký `run()`, contract nhiệm vụ không có giá trị trả về.
- [API Callable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html): chữ ký `V call() throws Exception`.
- [API ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): các overload `submit`, quản lý vòng đời executor.
- [API Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get()`, `cancel()`, timeout và ngoại lệ khi chờ.
- [API ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): exception từ task được báo qua Future.
- [API UncheckedIOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html): wrapper unchecked dành cho IOException.
- [API Executors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): các utility factory và adapter giữa Runnable/Callable.
- [JLS Java 17 mục 15.27.3 – Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.3): tương thích lambda với function type, bao gồm checked exception.
- [JLS Java 17 mục 11.2 – Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): nguyên tắc phân tích checked exception.

**Ghi nhớ cuối:** `Runnable.run()` **không có checked throws**, nhưng vẫn có thể ném unchecked; `Callable<V>.call() throws Exception` có thể **truyền checked exception** và trả kết quả kiểu V. Lambda chịu hợp đồng của functional interface mục tiêu. Khi chạy qua `ExecutorService.submit`, lỗi của cả hai loại task được quan sát qua **`Future.get() → ExecutionException → getCause()`**. Chọn Runnable hay Callable dựa vào **kết quả, khả năng ném checked exception và chính sách xử lý của caller**, không chỉ vì tên interface.