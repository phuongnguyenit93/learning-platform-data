# Hợp đồng ngoại lệ của `main` và giới hạn khi đẩy lỗi lên trên cùng

## 1. Mục tiêu và vấn đề cần giải quyết

Trong ứng dụng Java chạy từ dòng lệnh, `main` là điểm bắt đầu quen thuộc. Khi những phương thức phía dưới có thể ném checked exception, lập trình viên có thể tiếp tục khai báo `throws` dọc theo chuỗi lời gọi:

```text
Java launcher
    |
    v
main(String[] args) throws IOException
    |
    v
loadConfig() throws IOException
    |
    v
readFile() throws IOException
```

Điều này giúp **biên dịch** và truyền ngoại lệ ra khỏi `main`, nhưng tạo ra câu hỏi quan trọng: **Khi ngoại lệ đã đi ra khỏi `main`, ai xử lý nó?** Câu trả lời không phải “JVM sẽ tự phục hồi”. Ngoại lệ không được bắt có thể kết thúc luồng ban đầu, kích hoạt cơ chế thông báo lỗi không bắt và khiến ứng dụng dòng lệnh kết thúc không thành công. Cách JVM launcher trình bày lỗi và mã thoát cụ thể phụ thuộc môi trường thực thi.

Bài này giúp bạn:

- Hiểu cú pháp và tác dụng của `throws` ở phương thức `main`.
- Phân biệt **hợp đồng checked exception tại biên dịch** với **chính sách xử lý lỗi ở ranh giới ứng dụng**.
- Biết chuyện gì xảy ra khi một checked hoặc unchecked exception thoát khỏi `main`.
- Chọn hợp lý giữa `try/catch`, ném tiếp, dọn dẹp, báo thất bại và kết thúc tiến trình.
- Tránh giả định rằng lỗi ở một luồng worker hoặc tác vụ bất đồng bộ sẽ tự lan đến `main`.
- Nhận diện giới hạn của `throws Exception`, `throws Throwable` và cơ chế xử lý ở cấp cao nhất.

Các ví dụ dùng Java 17+; phần có ghi `javac`/`java` là chương trình độc lập chạy được.

## 2. Chữ ký `main` và mệnh đề `throws`

Với chương trình Java SE 17 thông thường, entry point phổ biến là:

```java
public static void main(String[] args) {
    // Nội dung chương trình.
}
```

Đây là **mảnh khai báo phương thức** để minh họa chữ ký; khi chạy thật, phải đặt trong một lớp Java hợp lệ.

Có thể thêm `throws` sau danh sách tham số:

```java
public static void main(String[] args)
        throws java.io.IOException {
    // Những lời gọi có thể truyền IOException ra ngoài.
}
```

Có thể khai báo **nhiều kiểu**:

```java
public static void main(String[] args)
        throws java.io.IOException, java.text.ParseException {
    // Có thể truyền một trong các nhóm checked exception này.
}
```

Và cú pháp `public static void main(String... args)` sử dụng varargs cũng tương ứng với tham số mảng `String[]` khi biên dịch.

Điều cần nhớ:

1. `throws` là **phần khai báo kiểu ngoại lệ**, không phải lệnh ném một đối tượng.
2. Câu lệnh `throw` hoặc thao tác/lời gọi thất bại mới thực sự phát sinh ngoại lệ.
3. `main throws IOException` không có nghĩa mọi lần chạy đều ném `IOException`.
4. `main throws IOException, ParseException` liệt kê **những khả năng khác nhau**, không yêu cầu cùng một lần lỗi ném hai đối tượng.
5. Các kiểu liệt kê phải phù hợp quy tắc ngôn ngữ và được ngăn cách bằng dấu phẩy, không dùng dấu `|` của multi-catch.
6. Không thể dựa vào mệnh đề `throws` để mong hệ điều hành, launcher hay người dùng tự cung cấp phương án phục hồi.

Trong Java 17, phương thức `main` chuẩn có kiểu trả về `void`. Không thể đổi thành `int main(...)` để trực tiếp trả mã trạng thái như một số ngôn ngữ khác.

### Tại sao `main` được khai báo checked exception?

Giả sử `main` gọi phương thức có hợp đồng `throws IOException`. Quy tắc checked exception của Java buộc bên gọi phải **bắt** hoặc **khai báo tiếp** ngoại lệ tương thích. `main` vẫn là phương thức Java thông thường trong việc kiểm tra ngoại lệ, nên lựa chọn `throws IOException` là hợp lệ.

Điểm đặc biệt là phía trên `main` thường không còn **một phương thức ứng dụng do bạn viết** có cơ hội bắt ngoại lệ. Việc khởi động lớp và gọi entry point thuộc cơ chế launcher/runtime. Vì vậy, đẩy checked exception tới `main` giải quyết nghĩa vụ biên dịch của mã nguồn, nhưng **không tự giải quyết cách phản hồi với người dùng hoặc hệ thống giám sát**.

## 3. Ví dụ chạy được: `main throws IOException`

Tạo tệp **`MainThrowsDemo.java`**:

```java
import java.io.IOException;

public class MainThrowsDemo {
    private static String loadConfig(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("demo read failed");
        }
        return "ready";
    }

    public static void main(String[] args) throws IOException {
        boolean fail = args.length > 0 && args[0].equals("fail");
        System.out.println(loadConfig(fail));
        System.out.println("main completed");
    }
}
```

Biên dịch và chạy đường thành công:

```bash
javac MainThrowsDemo.java
java MainThrowsDemo
```

Kết quả `stdout` chính xác:

```text
ready
main completed
```

Trong đường này, `loadConfig(false)` trả về chuỗi `ready`; **không hề có ngoại lệ**, dù `loadConfig` và `main` đều khai báo `throws IOException`.

Thử đường lỗi:

```bash
java MainThrowsDemo fail
```

Luồng thực thi khi đó:

1. `loadConfig(true)` thực thi `throw new IOException("demo read failed")`.
2. `loadConfig` kết thúc đột ngột; ngoại lệ đi lên lời gọi trong `main`.
3. `main` không có `catch` phù hợp, nên không in được dòng `main completed`.
4. Ngoại lệ đi ra khỏi `main` và trở thành ngoại lệ không được ứng dụng bắt tại luồng ban đầu.

Trên launcher Java thông dụng, bạn sẽ thấy thông tin kiểu `java.io.IOException`, thông điệp `demo read failed` và stack trace trên `stderr`. Vị trí file, số dòng, văn bản bổ sung và mã thoát không nên được giả định cố định trong tài liệu hoặc unit test có mục tiêu chạy đa môi trường.

**Không nhầm lẫn:** `throws IOException` trên `main` không có nghĩa JVM gọi lại `loadConfig`, cấp phát thêm tài nguyên, tự tạo fallback hoặc đổi ngoại lệ thành thông báo nghiệp vụ. Nó chỉ cho phép đường checked exception này đi ra khỏi phương thức theo quy tắc Java.

## 4. Khai báo nhiều kiểu trên `main`

Khi một ứng dụng đọc đầu vào và phân tích định dạng, nó có thể phân biệt hai kiểu checked exception. Ví dụ tệp **`MainMultipleThrowsDemo.java`**:

```java
import java.io.IOException;
import java.text.ParseException;

public class MainMultipleThrowsDemo {
    private static int parse(String input)
            throws IOException, ParseException {
        if (input == null) {
            throw new IOException("input unavailable");
        }

        try {
            return Integer.parseInt(input);
        } catch (NumberFormatException failure) {
            ParseException parsed =
                    new ParseException("not an integer", 0);
            parsed.initCause(failure);
            throw parsed;
        }
    }

    public static void main(String[] args)
            throws IOException, ParseException {
        System.out.println("value=" + parse("42"));
    }
}
```

```bash
javac MainMultipleThrowsDemo.java
java MainMultipleThrowsDemo
```

`stdout`:

```text
value=42
```

`main` hợp lệ khi khai báo nhiều kiểu `throws IOException, ParseException`. Nếu đầu vào không hợp lệ và ngoại lệ thực sự đi lên, đường gọi tương ứng sẽ kết thúc đột ngột. Việc giữ `NumberFormatException` làm `cause` trong `ParseException` giúp bảo toàn nguồn lỗi khi ứng dụng hoặc hệ thống giám sát đọc stack trace.

### `throws Exception` và `throws Throwable` có hợp lệ không?

Về mặt cú pháp, bạn có thể viết:

```java
public static void main(String[] args) throws Exception {
    // ...
}
```

Hoặc thậm chí `throws Throwable`. Tuy nhiên, đây là khai báo **rộng**:

- `throws Exception` bao phủ nhiều checked exception thuộc nhánh `Exception` và vẫn không bao phủ `Error` theo quan hệ kế thừa.
- `throws Throwable` bao phủ cả `Exception` và `Error` ở cấp kiểu, nhưng **không làm trạng thái JVM được phục hồi** nếu lỗi nghiêm trọng xuất hiện.
- Trong bài tập nhỏ hoặc công cụ thử nghiệm, `main throws Exception` là cách ngắn gọn để tập trung vào API đang học.
- Trong ứng dụng dòng lệnh cần thông báo lỗi rõ ràng, mã thoát có ý nghĩa, dọn dẹp tài nguyên và khả năng quan sát, chỉ thêm `throws Exception` thường không đủ.

Khai báo cụ thể như `IOException` và `ParseException` hữu ích cho tài liệu và bảo trì; còn **việc ứng dụng quyết định sẽ làm gì khi lỗi xảy ra** nên được thể hiện ở ranh giới thích hợp.

## 5. Khi ngoại lệ không được bắt đi ra khỏi `main`

Với một ngoại lệ thực sự thoát khỏi lời gọi `main` và không được ứng dụng bắt, quá trình xử lý tuân theo cơ chế ngoại lệ không được bắt của luồng. Về mặt hành vi thông thường:

```text
main gọi tác vụ
      |
      v
tác vụ ném Throwable
      |
      v
không có catch phù hợp trong chuỗi gọi
      |
      v
thoát khỏi main
      |
      v
cơ chế uncaught exception của luồng
      |
      v
luồng main kết thúc
```

Điều này cần hiểu chính xác:

- Một lỗi thoát khỏi `main` **không được tự động chuyển thành một giá trị trả về**, vì `main` trả về `void`.
- Trên môi trường launcher Java thông thường, nếu không thiết lập handler riêng, có thể quan sát stack trace trên `stderr`. Nội dung/định dạng của thông báo không phải hợp đồng để mã ứng dụng phụ thuộc tuyệt đối.
- Nếu các luồng non-daemon khác vẫn đang hoạt động, JVM có thể **vẫn tiếp tục chạy** sau khi luồng `main` kết thúc. “Luồng main đã kết thúc” và “tiến trình JVM đã kết thúc” là hai mệnh đề khác nhau.
- Nếu JVM/tiến trình kết thúc, hệ điều hành nhìn thấy một trạng thái hoàn tất tiến trình; quy ước `0` thành công và giá trị khác `0` báo thất bại thường được sử dụng trong CLI, nhưng đừng hứa một **mã lỗi cụ thể** cho mọi launcher/JVM khi một ngoại lệ không được bắt xuất hiện.
- `throws` không tự gửi phản hồi HTTP, tự rollback transaction, hủy tác vụ đang chạy hoặc thông báo lỗi theo định dạng mà người dùng mong đợi.

Trong mã thư viện, đừng cố dựa vào việc “ngoại lệ đã đến `main`” để thiết kế hành vi. Lập trình viên có thể gọi cùng thư viện từ unit test, ứng dụng GUI, dịch vụ, worker thread, scheduler hoặc entry point khác.

### `finally` và đóng tài nguyên

Khi stack bị tháo gỡ theo cơ chế ngoại lệ thông thường, các khối `finally` tương ứng sẽ được thực thi. `try-with-resources` cũng đóng tài nguyên theo quy tắc ngôn ngữ. Nhưng điều này **không bảo đảm** dọn dẹp xong nếu tiến trình/VM bị kết thúc cưỡng bức, gặp sự cố nghiêm trọng hoặc bị gọi `Runtime.halt(...)`.

Vì vậy, hãy đặt dọn dẹp ở đúng phạm vi tài nguyên và không coi `main throws ...` là cơ chế quản lý tài nguyên.

## 6. Bắt lỗi ở ranh giới `main` khi cần chính sách rõ ràng

Khi ứng dụng dòng lệnh cần chuyển lỗi kỹ thuật thành thông điệp dễ hiểu, `main` có thể là nơi xử lý lỗi cuối cùng của **luồng khởi chạy**:

```java
try {
    initialize();
    execute();
} catch (IOException failure) {
    System.err.println("Cannot start: " + failure.getMessage());
}
```

Đây là **đoạn mã minh họa**, cần khai báo `initialize()` và `execute()` trong ứng dụng thực. Mẫu này xử lý được lỗi I/O theo hợp đồng nhưng chưa nói gì về chính sách kết thúc và mã thoát; ứng dụng cần quyết định điều đó.

### Ví dụ chạy được: bắt lỗi rồi thực hiện dọn dẹp

Tạo tệp **`MainCatchDemo.java`**:

```java
import java.io.IOException;

public class MainCatchDemo {
    private static void initialize() throws IOException {
        throw new IOException("config missing");
    }

    public static void main(String[] args) {
        try {
            initialize();
            System.out.println("initialized");
        } catch (IOException failure) {
            System.out.println("startup failed: "
                    + failure.getMessage());
        } finally {
            System.out.println("startup cleanup");
        }

        System.out.println("main reached end");
    }
}
```

```bash
javac MainCatchDemo.java
java MainCatchDemo
```

Kết quả `stdout`:

```text
startup failed: config missing
startup cleanup
main reached end
```

Giải thích:

1. `initialize()` ném `IOException` và bỏ qua lệnh in `initialized`.
2. Handler của `main` chuyển thất bại thành thông tin đầu ra có chủ đích.
3. `finally` chạy để thực hiện thao tác dọn dẹp tương ứng; trong ví dụ là in một dòng.
4. Sau `try/catch/finally`, chương trình vẫn chạy tiếp và in `main reached end`.

Điểm cuối cùng đặc biệt quan trọng: **bắt rồi in một dòng chưa chắc là chính sách thất bại đúng**. Nếu cấu hình bắt buộc không được nạp, ứng dụng thực có thể cần dừng khởi động, báo trạng thái thất bại và tránh tiếp tục chạy như thể đã sẵn sàng.

### Không nuốt lỗi rồi báo thành công

Ví dụ sau dễ gây hiểu lầm đối với hệ thống gọi ứng dụng:

```java
try {
    startRequiredService();
} catch (Exception failure) {
    System.err.println(failure.getMessage());
}
System.out.println("ready"); // Có thể sai: dịch vụ chưa khởi động.
```

Đây là **đoạn mã sai về mặt thiết kế để minh họa**, giả định `startRequiredService()` có tồn tại. Nếu không thể chạy dịch vụ, không nên in `ready`, trả kết quả thành công hoặc tiếp tục các bước phụ thuộc vào khởi tạo đã thất bại.

Một phương thức phụ trợ có thể bắt ngoại lệ **để thêm ngữ cảnh rồi ném tiếp**, nhưng nên giữ `cause`:

```java
try {
    loadSettings();
} catch (IOException failure) {
    throw new IllegalStateException("Startup configuration failed",
            failure);
}
```

Đây là mảnh mã minh họa trong một phương thức, cần có `loadSettings()` khai báo checked exception. Việc bọc lỗi thành `IllegalStateException` giúp biểu đạt bối cảnh mới, đồng thời vẫn giữ lỗi gốc để truy vết. Không bọc lỗi nhiều tầng chỉ để đổi tên mà không thêm thông tin hữu ích.

## 7. Trả kết quả thành công/thất bại và mã thoát của CLI

`public static void main(String[] args)` trả về `void`, vì vậy một ứng dụng dòng lệnh thường tách logic thành một phương thức trả mã trạng thái:

```java
static int run(String[] args) {
    // 0 = thành công; giá trị khác 0 = thất bại theo quy ước của ứng dụng.
    return 0;
}
```

Đây là **mảnh minh họa**, chưa phải chương trình thực thi độc lập. Thiết kế hữu ích là cho `run` trả về trạng thái hoặc ném ngoại lệ theo hợp đồng, còn `main` là nơi quyết định cách kết thúc ứng dụng.

Ví dụ **`CliExitPolicyDemo.java`**, không cần thật sự gọi `System.exit` để học cách ánh xạ lỗi:

```java
import java.io.IOException;

public class CliExitPolicyDemo {
    private static void execute(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("input unavailable");
        }
    }

    private static int run(String[] args) {
        boolean fail = args.length > 0 && args[0].equals("fail");
        try {
            execute(fail);
            return 0;
        } catch (IOException failure) {
            System.out.println("error: " + failure.getMessage());
            return 2;
        }
    }

    public static void main(String[] args) {
        int status = run(args);
        System.out.println("status=" + status);
    }
}
```

```bash
javac CliExitPolicyDemo.java
java CliExitPolicyDemo
java CliExitPolicyDemo fail
```

Hai lần chạy độc lập tạo `stdout` lần lượt:

```text
status=0
```

```text
error: input unavailable
status=2
```

Ở đây mã `2` chỉ là **giá trị trạng thái logic được in ra**, không phải mã thoát thực tế của tiến trình Java. Vì `main` kết thúc bình thường, không thể kết luận hệ điều hành đã nhận exit code `2`.

Trong ứng dụng CLI thật cần báo trạng thái ra hệ điều hành, người viết entry point có thể dùng `System.exit(status)` theo chính sách cụ thể. Tuy nhiên:

- `System.exit` yêu cầu JVM bắt đầu quá trình shutdown; nó ảnh hưởng **toàn bộ tiến trình** và mọi luồng, không chỉ một lời gọi.
- `System.exit` không phải thao tác nên gọi tùy tiện trong thư viện, method nghiệp vụ hoặc unit test.
- Việc gọi `System.exit` bên trong `try` không phải một cách tin cậy để ép `finally` cùng luồng hoàn thành như đường thoát bình thường.
- Không nên lấy một **exit code cố định** từ ví dụ ngoại lệ không bắt được để tạo quy tắc cho tất cả JVM. Hãy định nghĩa và kiểm tra mã thoát tại ranh giới CLI mình quản lý.
- Nếu ứng dụng được framework, IDE, test runner hoặc máy chủ quản lý, cần theo cơ chế lifecycle của môi trường đó; không mặc nhiên gọi `System.exit`.

## 8. `main throws InterruptedException` và vấn đề ngắt luồng

`main` cũng có thể khai báo:

```java
public static void main(String[] args)
        throws InterruptedException {
    Thread.sleep(100);
}
```

Đây là mảnh phương thức hợp lệ trong lớp Java. `Thread.sleep` khai báo `InterruptedException`; `throws InterruptedException` cho phép thông báo ngắt đi ra khỏi `main` mà không phải viết `catch`.

Nhưng trong ứng dụng thật, yêu cầu ngắt có thể là tín hiệu hủy công việc/đóng ứng dụng. Nếu bạn bắt `InterruptedException` mà chưa xử lý trọn việc hủy, thường cần đặt lại cờ interrupt bằng `Thread.currentThread().interrupt()`, rồi kết thúc công việc theo hợp đồng.

Ví dụ mảnh mã:

```java
try {
    Thread.sleep(100);
} catch (InterruptedException failure) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là đoạn dành cho **phương thức trả về `void`** (chẳng hạn `main`). Không phải mọi handler đều phải đặt lại cờ: nếu chủ động truyền tiếp chính `InterruptedException` ra ngoài bằng `throws`, điều đó đã giữ tín hiệu bằng kiểu ngoại lệ. Chính sách còn phụ thuộc framework và cấu trúc hủy tác vụ.

## 9. Giới hạn quan trọng: ngoại lệ của luồng khác không tự bay lên `main`

Một quan niệm sai phổ biến: “`main throws Exception` sẽ nhận mọi ngoại lệ của chương trình”.

Điều này không đúng. Ngoại lệ lan truyền **theo stack của luồng đang thực thi**. Khi một luồng worker có stack riêng ném ngoại lệ không được bắt, ngoại lệ đó không tự di chuyển ngược sang stack của luồng `main`.

Tạo tệp **`WorkerFailureDemo.java`**:

```java
public class WorkerFailureDemo {
    public static void main(String[] args)
            throws InterruptedException {
        Thread worker = new Thread(
                () -> { throw new IllegalStateException("child failed"); },
                "worker"
        );

        worker.setUncaughtExceptionHandler((thread, failure) ->
                System.out.println("worker error: "
                        + failure.getMessage()));

        worker.start();
        worker.join();
        System.out.println("main completed");
    }
}
```

```bash
javac WorkerFailureDemo.java
java WorkerFailureDemo
```

`stdout`:

```text
worker error: child failed
main completed
```

`Thread.join()` chỉ chờ worker kết thúc; bản thân nó **không ném lại `IllegalStateException` của worker cho `main`**. Ví dụ cài `UncaughtExceptionHandler` trên worker để kiểm soát phần báo lỗi; nhờ có `join()`, thứ tự hai dòng in xác định.

Nếu không có handler cục bộ, cơ chế xử lý ngoại lệ không được bắt của luồng sẽ được áp dụng, thường in stack trace. Điều này không làm `main throws ...` trở thành “handler toàn cục”.

### `setDefaultUncaughtExceptionHandler` có thay thế `try/catch` không?

Không. Handler mặc định được gọi trong tình huống ngoại lệ sắp kết thúc một luồng mà không được bắt. Nó phù hợp để ghi nhận lỗi cuối cùng, nhưng không thể quay lại điểm ném để tiếp tục phần thân phương thức đã thất bại. Nếu bản thân handler cần cấp phát, ghi file hoặc gửi thông báo, những thao tác này cũng có thể thất bại khi môi trường đang gặp sự cố tài nguyên.

Trong sản phẩm thật, giữ nội dung handler tối thiểu, tránh coi handler là cơ chế đảm bảo phục hồi.

## 10. Giới hạn khác: tác vụ qua `ExecutorService` và `Future`

Khác với việc tạo `Thread` trực tiếp, một tác vụ được gửi qua `ExecutorService.submit(...)` thường được bọc để ngoại lệ nằm trong trạng thái hoàn tất của `Future`. Bên gọi có thể quan sát lỗi khi gọi `Future.get()`; lỗi của tác vụ xuất hiện dưới dạng **`ExecutionException`** với nguyên nhân thật ở `getCause()`.

Tạo tệp **`FutureFailureDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureFailureDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Callable<String> task = () -> {
                throw new IOException("worker IO failed");
            };

            Future<String> future = pool.submit(task);
            try {
                System.out.println(future.get());
            } catch (ExecutionException failure) {
                System.out.println("task cause: "
                        + failure.getCause().getClass().getSimpleName());
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("main completed");
    }
}
```

```bash
javac FutureFailureDemo.java
java FutureFailureDemo
```

Kết quả:

```text
task cause: IOException
main completed
```

Giải thích:

- `Callable<String>` cho phép tác vụ ném checked exception; ở đây là `IOException`.
- `submit` trả về một `Future<String>`. Lỗi do tác vụ ném không tự động trở thành `IOException` tại dòng `submit` trên luồng `main`.
- `future.get()` báo `ExecutionException` khi tác vụ kết thúc thất bại. `getCause()` chỉ đến `IOException` ban đầu.
- `main` khai báo `throws InterruptedException` cho việc chờ có thể bị ngắt; `ExecutionException` được bắt và xử lý riêng.
- `shutdown()` ngừng nhận thêm tác vụ mới; đây không phải lệnh ép dừng tức thì các tác vụ đang chạy. Trong ví dụ, `future.get()` đã chờ tác vụ cụ thể hoàn tất, nên output xác định.

Muốn đẩy lỗi đến ranh giới ứng dụng, bạn phải **chủ động thu thập và xử lý kết quả Future** hoặc dùng cơ chế phối hợp tác vụ phù hợp. Với `CompletableFuture`, cơ chế báo lỗi khác về wrapper và API (chẳng hạn `CompletionException` hoặc `ExecutionException` tùy cách chờ), nhưng nguyên tắc vẫn là: **ngoại lệ không tự nhảy qua ranh giới luồng**.

## 11. Những lỗi nằm ngoài khả năng xử lý bằng `main throws`

### 11.1. Lỗi trước khi vào thân `main`

Một số lỗi có thể xuất hiện trong quá trình nạp lớp, liên kết hoặc khởi tạo lớp bắt buộc trước lúc JVM thực thi những dòng đầu tiên của `main`. Chẳng hạn, lỗi khởi tạo tĩnh có thể biểu hiện thành `ExceptionInInitializerError`. Vì thân `main` còn chưa bắt đầu, một `try/catch` đặt **bên trong thân `main`** không thể bao quanh và bắt được tất cả lỗi của toàn bộ giai đoạn khởi động bên ngoài nó.

Không nên hứa rằng `main throws Throwable` sẽ thu nhận mọi lỗi khởi động của JVM hoặc launcher.

### 11.2. Lỗi nghiêm trọng thuộc nhánh `Error`

`OutOfMemoryError` hoặc `StackOverflowError` là `Error`, không phải `Exception`. `catch (Exception e)` không bắt các đối tượng này; `throws Exception` cũng không phải cơ chế quản lý chúng.

Ngay cả khi có thể bắt một số `Error` về mặt kiểu, tiếp tục chạy sau lỗi nghiêm trọng có thể nguy hiểm do thiếu tài nguyên hoặc trạng thái hỏng. Không tự tạo lỗi thiếu bộ nhớ hoặc tràn stack để kiểm thử entry point trên ứng dụng thật.

### 11.3. Mất tiến trình và shutdown cưỡng bức

Tín hiệu hệ điều hành, lỗi native, mất điện, `Runtime.halt(...)` hay các sự kiện dừng cưỡng bức có thể ngăn chương trình thực thi trọn đường xử lý ngoại lệ, `finally` và shutdown hook. `throws` không cung cấp bảo đảm “luôn có một handler cuối cùng chạy được”.

### 11.4. Lỗi đã được framework hoặc task runner hấp thụ

Trong một ứng dụng có scheduler, event loop, message consumer hoặc hệ quản lý worker riêng, lỗi có thể được framework bắt, lưu, retry hoặc chuyển đến callback. Không thể suy luận rằng mọi lỗi đều đến `main` chỉ vì `main` là điểm khởi động chương trình.

Mô tả và thử nghiệm chính sách lỗi cần xét **ranh giới thực thi thật**: thread, task, Future, callback, service container hoặc request handler.

## 12. Chọn chiến lược xử lý ở tầng nào?

Không phải lỗi nào cũng nên xử lý tại `main`; cũng không nên ném mọi thứ lên trên cùng.

| Loại sự cố | Tầng thường có đủ ngữ cảnh | Hướng xử lý |
| --- | --- | --- |
| Dữ liệu đầu vào CLI sai | Biên nhận tham số | Báo cách dùng/giá trị sai; mã trạng thái ứng dụng có chủ đích |
| Tệp cấu hình bắt buộc không mở được | Khởi động ứng dụng | Thông báo nguồn lỗi, dừng khởi động, tránh báo “ready” |
| Một bản ghi dữ liệu không hợp lệ nhưng có thể bỏ qua | Tầng xử lý bản ghi | Ghi nhận và tiếp tục nếu hợp đồng cho phép |
| Lỗi hệ thống tạm thời có thể retry an toàn | Tầng I/O có biết idempotency và giới hạn retry | Retry có giới hạn hoặc truyền lỗi lên ranh giới điều phối |
| Lỗi lập trình `NullPointerException` | Nơi tạo trạng thái/tham chiếu sai | Sửa nguyên nhân; không dùng `catch` rộng để che giấu bug |
| Lỗi trong một worker bất đồng bộ | Biên kết quả của task/worker | Quan sát `Future`/callback/handler, quyết định hủy hoặc báo thất bại |
| `OutOfMemoryError`/lỗi runtime nghiêm trọng | Vận hành và quản lý tiến trình | Thu thập bằng chứng nếu khả thi, cách ly và khắc phục nguyên nhân |

Một cách tổ chức hữu ích cho CLI là:

```text
main                -> nhận args, chính sách thông báo lỗi/mã thoát
  |
  +-- application    -> điều phối, quy tắc nghiệp vụ
         |
         +-- IO/API   -> khai báo checked exception theo hợp đồng
```

Lớp dưới ném kiểu ngoại lệ có ý nghĩa. Lớp trên xử lý ở nơi **có thể quyết định hành động đúng**. `main` nên tập trung vào chính sách ranh giới tiến trình; không đặt logic nghiệp vụ và quá nhiều `catch` trùng lặp trong đó.

### Khi nào có thể để `main throws Exception`?

- Ví dụ học tập, chương trình thử nhanh, công cụ nội bộ nhỏ mà stack trace trực tiếp là đủ.
- Khi không có nhu cầu định dạng lỗi, cleanup riêng, mã thoát được quy ước, hay trạng thái phục vụ dài hạn.
- Khi hành vi thất bại mặc định của launcher được chấp nhận và đã được kiểm tra trong môi trường chạy.

### Khi nào nên có handler rõ ràng ở `main`?

- CLI được gọi từ shell script/CI và cần phân loại lỗi ổn định.
- Ứng dụng chạy dài hạn cần quyết định startup đã thành công hay không.
- Ứng dụng có tài nguyên cần đóng theo vòng đời rõ ràng.
- Hệ thống cần log có ngữ cảnh, không in stack trace nhạy cảm cho người dùng cuối.
- Ứng dụng phối hợp nhiều worker và phải đánh dấu job thất bại nếu một task bắt buộc thất bại.

Trong mọi trường hợp, handler cấp cao chỉ có thể quản lý **những ngoại lệ thực sự đi đến nó** và phải xem xét trạng thái tiến trình trước khi quyết định tiếp tục.

## 13. Lỗi hiểu nhầm thường gặp

**“`throws Exception` ở `main` nghĩa là đã xử lý mọi lỗi.”** Sai. Nó chỉ công bố các kiểu checked exception ở mức chữ ký; không tạo handler, phục hồi hay kết quả lỗi có cấu trúc.

**“`throws IOException` bắt JVM phải in IOException nếu lỗi phát sinh.”** Không chính xác. Một handler bên trong, một lớp bọc hoặc runtime khác có thể thay đổi cách báo lỗi. `throws` không kiểm soát định dạng output.

**“Vì `main` là điểm vào, mọi worker exception sẽ tự đi đến nó.”** Sai. Mỗi thread có call stack riêng; `Future` hoặc cơ chế trao đổi lỗi phải được xử lý rõ ràng.

**“`Thread.join()` ném lại lỗi mà worker đã ném.”** Sai. `join()` chờ kết thúc, không phải kênh chuyển ngoại lệ worker. Nó có thể ném `InterruptedException` nếu luồng đang chờ bị ngắt.

**“`System.out.println(status)` làm hệ điều hành nhận đúng exit code đó.”** Sai. In chuỗi và kết thúc tiến trình là hai việc khác nhau.

**“Một `catch (Exception)` ở `main` bao phủ `Error` và lỗi trước khi `main` chạy.”** Sai. `Error` ở nhánh khác, còn lỗi phát sinh trước khi thân `main` bắt đầu thì `catch` bên trong thân không bao quanh được.

**“Có `finally` thì dọn dẹp luôn chạy dù process bị kill.”** Sai. Bảo đảm trong ngữ nghĩa Java có điều kiện về việc VM còn thực thi được đường thoát đó.

**“Nếu lỗi đã bị bắt ở `main` thì tiến trình mặc nhiên được đánh dấu thất bại.”** Sai. Bắt lỗi và tiếp tục kết thúc bình thường có thể được xem là thành công bởi môi trường chạy. Chính sách mã thoát cần được lập trình riêng khi cần.

**“Khai báo càng rộng càng an toàn.”** Sai. `throws Throwable` thường làm mất ý nghĩa API và không cải thiện khả năng phục hồi.

## 14. Câu hỏi tự kiểm tra

1. **`public static void main(String[] args) throws IOException` có hợp lệ với Java 17 không?** Có.
2. **`throws IOException` trong `main` có bảo đảm chương trình luôn ném lỗi?** Không, nó mô tả khả năng phát sinh.
3. **Nếu lời gọi ném checked exception không được bắt trong `main`, trình biên dịch yêu cầu gì?** `main` phải khai báo kiểu phù hợp trong `throws` hoặc bắt nó.
4. **Khi checked exception không được bắt thoát khỏi `main`, JVM có tự retry không?** Không có bảo đảm hay quy tắc retry tự động từ `throws`.
5. **Một worker ném `IllegalStateException`; `main throws Exception` có bắt được lỗi đó không?** Không, vì lỗi không tự lan giữa các thread.
6. **`Future.get()` thường báo lỗi tác vụ bằng loại nào?** `ExecutionException` với nguyên nhân ở `getCause()`.
7. **Mã `return 2;` có hợp lệ trực tiếp trong `public static void main` chuẩn không?** Không, vì `main` trả về `void`.
8. **Bắt lỗi tại `main` rồi in `ready` có thể gây vấn đề gì?** Ứng dụng báo trạng thái thành công dù khởi tạo thực tế thất bại.
9. **Nếu lớp khởi tạo lỗi trước khi vào thân `main`, handler đặt trong `main` có thể bắt nó không?** Không bắt được lỗi xảy ra trước khi handler tồn tại trên đường thực thi.
10. **`main throws Throwable` có khiến JVM luôn chạy `finally` khi mất điện không?** Không.
11. **Khi nào nên để ngoại lệ đi ra khỏi `main`?** Khi chấp nhận cơ chế báo lỗi mặc định của môi trường chạy và không cần một chính sách xử lý/lifecycle khác.
12. **Khi nào nên xử lý tại ranh giới `main`?** Khi cần thông báo, dọn dẹp, mã trạng thái hoặc quyết định dừng/tiếp tục có ngữ nghĩa ứng dụng rõ ràng.

## 15. Tài liệu tham khảo

- [Java Language Specification 17 — §8.4.6 Method Throws](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6): ý nghĩa mệnh đề `throws`.
- [Java Language Specification 17 — §11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): quy tắc checked exception.
- [Java Language Specification 17 — §11.3 Run-Time Handling of an Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.3): xử lý và lan truyền ngoại lệ.
- [Java SE 17 API — Thread.UncaughtExceptionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html): xử lý ngoại lệ không được bắt ở ranh giới luồng.
- [Java SE 17 API — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html) và [ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html): nhận thất bại của tác vụ bất đồng bộ.
- [Java SE 17 API — System.exit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#exit(int)): yêu cầu kết thúc JVM theo trạng thái.
- [Java SE 17 API — Thread.join](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#join()): chờ một luồng kết thúc.

**Ghi nhớ:** `throws` trên `main` là hợp đồng ngoại lệ ở mức ngôn ngữ, cho phép checked exception truyền ra biên chương trình. Muốn phản hồi đúng khi thất bại, ứng dụng phải định nghĩa rõ **handler, cách dọn dẹp, ranh giới luồng/tác vụ và chính sách kết thúc**; những điều đó không được sinh ra chỉ bằng cách thêm `throws Exception`.
