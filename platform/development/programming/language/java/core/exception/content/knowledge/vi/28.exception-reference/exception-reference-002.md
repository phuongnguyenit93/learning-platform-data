# Bảng checked, unchecked, Exception và Error trong Java

## 1. Mục đích của bảng tra cứu

Java dùng hệ thống kiểu `Throwable` để biểu diễn những tình huống khiến luồng xử lý bình thường bị gián đoạn. Khi đọc một chữ ký như `void read() throws IOException`, thấy `NullPointerException` trong log hoặc gặp `NoClassDefFoundError` khi khởi động, cần phân biệt hai câu hỏi:

1. **Kiểu đó nằm ở đâu trong cây kế thừa?** `Throwable`, `Exception`, `RuntimeException` hay `Error`?
2. **Trình biên dịch có bắt buộc caller phải bắt hoặc khai báo không?** Đây mới là ranh giới giữa **checked** và **unchecked**.

Bảng dưới đây dùng Java 17+, gồm cây phân cấp, ngoại lệ thường gặp, quy tắc `try/catch/throws`, ví dụ biên dịch/chạy được, các trường hợp đồng thời/bất đồng bộ và nguyên tắc thiết kế API. Nó là tài liệu **tra cứu và giải thích**, không phải lời khuyên “catch mọi lỗi” hoặc ép mọi phương thức ném checked exception.

### 1.1. Ba khái niệm cần phân biệt ngay

- **`Exception` là một lớp trong Java**, không đồng nghĩa với tất cả những thứ có thể bị `throw`. `Error` không kế thừa `Exception`.
- **Checked/unchecked là quy tắc kiểm tra tĩnh của compiler**, không phải thước đo chắc chắn về độ nặng, khả năng phục hồi hoặc nguồn gốc lỗi.
- **`RuntimeException` thuộc `Exception` nhưng là unchecked**; đây là chi tiết người mới học thường nhầm nhất.

Trong Java, `Throwable` là lớp cha chung của hai nhánh chính `Exception` và `Error`. Theo phân loại checked-exception của ngôn ngữ, một kiểu `Throwable` là **unchecked** nếu nó là `RuntimeException`, `Error` hoặc lớp con của chúng; các kiểu `Throwable` còn lại là **checked**. Do đó bản thân `Exception` là checked, còn `RuntimeException` dù là lớp con của `Exception` lại unchecked.

## 2. Cây phân cấp tổng quan

~~~text
java.lang.Object
    |
    +-- java.lang.Throwable                     checked
          |
          +-- java.lang.Exception                checked
          |     |
          |     +-- IOException                  checked
          |     |     +-- FileNotFoundException
          |     |     +-- ...
          |     +-- SQLException                  checked
          |     +-- ParseException                checked
          |     +-- InterruptedException          checked
          |     +-- ClassNotFoundException        checked
          |     +-- ExecutionException            checked
          |     +-- TimeoutException              checked
          |     |
          |     +-- RuntimeException              UNCHECKED
          |           |
          |           +-- IllegalArgumentException
          |           |     +-- NumberFormatException
          |           +-- IllegalStateException
          |           +-- NullPointerException
          |           +-- IndexOutOfBoundsException
          |           +-- ArithmeticException
          |           +-- CompletionException
          |           +-- CancellationException
          |           +-- UncheckedIOException
          |           +-- ...
          |
          +-- java.lang.Error                     UNCHECKED
                |
                +-- AssertionError
                +-- VirtualMachineError
                |     +-- OutOfMemoryError
                |     +-- StackOverflowError
                +-- LinkageError
                |     +-- NoClassDefFoundError
                |     +-- NoSuchMethodError
                |     +-- ExceptionInInitializerError
                +-- ...
~~~

Cây được **lược bớt** để dễ tra cứu, không liệt kê mọi lớp JDK. Các tên không có package trong cây thuộc nhiều package khác nhau; chẳng hạn `IOException` thuộc `java.io`, `SQLException` thuộc `java.sql`, `ExecutionException` và `TimeoutException` thuộc `java.util.concurrent`.

Một lớp tự định nghĩa cũng có thể kế thừa trực tiếp `Throwable`. Trường hợp đó vẫn là **checked**, miễn không nằm dưới `RuntimeException` hoặc `Error`. Tuy nhiên trong API ứng dụng thông thường, nên kế thừa `Exception` hoặc `RuntimeException` đúng ngữ nghĩa thay vì kế thừa trực tiếp `Throwable`.

## 3. Bảng chính: checked, unchecked, Exception và Error

| Khái niệm | Quan hệ kế thừa | Compiler buộc catch/declare? | Ý nghĩa thường gặp |
| --- | --- | --- | --- |
| `Throwable` | Cha của `Exception` và `Error` | **Có** khi trực tiếp ném một `Throwable` không thuộc nhánh unchecked | Nền tảng biểu diễn thứ có thể được ném |
| `Exception` | `extends Throwable` | **Có** với chính `Exception` và các subclass checked | Lỗi/điều kiện cần truyền qua API theo chính sách |
| Checked exception | `Throwable` trừ nhánh `RuntimeException`/`Error` | **Có**, khi có thể thoát khỏi code và thuộc kiểm tra compile-time | Nhiều lỗi I/O, parsing, điều phối |
| `RuntimeException` | `extends Exception` | **Không** | Sai argument/state, lỗi lập trình hoặc trạng thái runtime theo thiết kế API |
| Unchecked exception | `RuntimeException` hoặc `Error` và các subclass | **Không** | Lỗi/điều kiện không cần khai báo bắt buộc |
| `Error` | `extends Throwable`, **không** kế thừa `Exception` | **Không** | Lỗi JVM/linkage, assertion hoặc điều kiện nghiêm trọng khác |

**Câu nhớ nhanh:** `Exception` không đồng nghĩa “checked”, bởi `RuntimeException` là một `Exception` nhưng unchecked. Ngược lại, không phải mọi `Throwable` đều là `Exception`, vì `Error` là nhánh độc lập.

### 3.1. Công thức phân loại theo kiểu

Với một kiểu `T` kế thừa `Throwable`:

~~~text
Nếu T extends RuntimeException  -> unchecked
Nếu T extends Error             -> unchecked
Nếu T extends Throwable nhưng
  không thuộc hai nhánh trên    -> checked
~~~

Dùng chữ “`extends`” ở đây theo nghĩa **quan hệ subtype kế thừa bắc cầu**, không nhất thiết câu lệnh trực tiếp trong source. Chẳng hạn `NumberFormatException` extends `IllegalArgumentException` extends `RuntimeException`, vì vậy là unchecked. `NoClassDefFoundError` nằm dưới `LinkageError` extends `Error` nên unchecked.

### 3.2. Checked không có nghĩa lỗi nhẹ, unchecked không có nghĩa lỗi nặng

`IOException` do filesystem không ghi được có thể làm thất bại thao tác quan trọng. `IllegalArgumentException` có thể là điều kiện validation dễ khắc phục. `AssertionError` đôi khi là một assertion không thỏa trong test, không nhất thiết mọi lần đều khiến JVM lập tức tắt.

Vì thế chọn cách xử lý dựa vào **hợp đồng và trạng thái hệ thống**, không chỉ nhìn checked/unchecked:
- Có thể phục hồi thật không?
- Có side effect nào đã xảy ra trước khi lỗi ném?
- Caller có đủ thông tin và quyền retry không?
- Có cần shutdown/restart hay đối soát dữ liệu không?
- Có thể bảo đảm invariant sau khi catch không?

## 4. Bảng checked exception thường gặp

| Kiểu | Package / nguồn phổ biến | Khi nào gặp? | Điểm cần nhớ |
| --- | --- | --- | --- |
| `IOException` | `java.io` | Đọc/ghi file, stream, I/O | Checked; nhiều subtype |
| `FileNotFoundException` | `java.io` | Mở file không tìm thấy/không mở được theo API | Subclass của IOException |
| `NoSuchFileException` | `java.nio.file` | Đường dẫn không tồn tại trong NIO | Subclass checked của IOException qua FileSystemException |
| `EOFException` | `java.io` | Hết dữ liệu bất ngờ ở một số API stream | Checked |
| `SQLException` | `java.sql` | JDBC/SQL/driver/database error | Checked; trạng thái transaction cần xem riêng |
| `SQLTimeoutException` | `java.sql` | JDBC thao tác timeout theo driver | Checked; không mặc định rollback mọi side effect |
| `ParseException` | `java.text` | Phân tích chuỗi ngày/text theo API liên quan | Checked |
| `URISyntaxException` | `java.net` | Chuỗi URI không đúng cú pháp theo `new URI(String)` | Checked |
| `ClassNotFoundException` | `java.lang` | API tải class theo tên không tìm thấy class | Checked |
| `InterruptedException` | `java.lang` | Thread đang chờ bị interrupt tại API hỗ trợ | Checked; giữ/lan truyền yêu cầu ngắt |
| `ExecutionException` | `java.util.concurrent` | `Future.get()` quan sát task lỗi | Checked; nguyên nhân ở `getCause()` |
| `TimeoutException` | `java.util.concurrent` | `Future.get(timeout)` hết hạn chờ | Checked; không tự hủy task |
| `ReflectiveOperationException` | `java.lang` | Một số thao tác reflection | Checked |
| `GeneralSecurityException` | `java.security` | Một số API mật mã/chứng thư | Checked |
| `CloneNotSupportedException` | `java.lang` | Lời gọi `Object.clone()` không được hỗ trợ | Checked |

Bảng không có ý nói mọi thao tác I/O đều ném `IOException` hoặc mọi timeout đều là `TimeoutException`. **Loại exception phụ thuộc API cụ thể**: HTTP client, JDBC, CompletableFuture, socket và thư viện có thể dùng các kiểu khác nhau.

### 4.1. Checked có thể nằm ngoài `Exception` không?

Có: một subclass trực tiếp của `Throwable` mà **không** nằm dưới `RuntimeException`/`Error` cũng checked. Ví dụ:

~~~java
class DirectThrowable extends Throwable {
    DirectThrowable(String message) {
        super(message);
    }
}
~~~

Đây là fragment lớp có thể đặt trong một file nguồn Java phù hợp. Một phương thức ném `new DirectThrowable("...")` thông thường phải bắt hoặc khai báo `throws DirectThrowable`.

Tuy nhiên **không nên thiết kế business exception bằng cách extends Throwable trực tiếp** nếu không có lý do đặc biệt: phần lớn code ứng dụng bắt `Exception` sẽ không bắt được nó, gây hành vi dễ nhầm. Thực tế thường sử dụng `extends Exception` cho checked domain failure hoặc `extends RuntimeException` cho unchecked domain failure theo contract.

## 5. Bảng unchecked RuntimeException thường gặp

| Kiểu | Tình huống điển hình | Cách điều tra/thiết kế |
| --- | --- | --- |
| `IllegalArgumentException` | Tham số không thỏa tiền điều kiện | Kiểm tra input contract/validation |
| `NumberFormatException` | Không parse được số với `Integer.parseInt` và API tương tự | Subclass của IllegalArgumentException |
| `IllegalStateException` | Object hoặc hệ thống không ở trạng thái cho phép | Kiểm tra state transition và tiền điều kiện |
| `NullPointerException` | Truy cập qua null hoặc API yêu cầu non-null | Xem nguồn null và ngữ cảnh dòng |
| `IndexOutOfBoundsException` | Index ngoài phạm vi collection/array theo API | Kiểm tra size/index |
| `ArrayIndexOutOfBoundsException` | Index sai trong array | Subclass của IndexOutOfBoundsException |
| `ArithmeticException` | Ví dụ phép chia nguyên cho zero | Không phải mọi phép toán floating-point cho hành vi tương tự |
| `ClassCastException` | Ép kiểu runtime không tương thích | Kiểm tra type và classloader |
| `UnsupportedOperationException` | Operation không được hỗ trợ, ví dụ collection immutable | Đọc contract của object |
| `ConcurrentModificationException` | Một số iterator phát hiện sửa collection sai contract | Fail-fast thường best effort; không dùng như cơ chế đồng bộ |
| `IllegalMonitorStateException` | `wait/notify` hoặc monitor operation sai ownership | Kiểm tra synchronized/lock |
| `SecurityException` | API từ chối do cơ chế security tương ứng | Có thể do policy/config, không chỉ bug |
| `CompletionException` | CompletionStage/`CompletableFuture.join()` báo lỗi nguồn | Đọc `getCause()` |
| `CancellationException` | `Future.get()`/`join()` trên future đã hủy | Hủy không đồng nghĩa công việc dưới đã dừng |
| `UncheckedIOException` | Wrapper unchecked chứa IOException | Đọc `getCause()` |
| `DateTimeException` | API `java.time` từ chối dữ liệu ngày giờ | Unchecked trong `java.time` |

**RuntimeException không đồng nghĩa với “lỗi do JVM tự tạo”.** Developer có thể chủ động `throw new IllegalArgumentException(...)`, framework có thể ném exception unchecked của riêng mình, và một `RuntimeException` có thể biểu thị lỗi hạ tầng đã được wrapper. Phải xem type, cause và hợp đồng cụ thể.

### 5.1. Khi nào dùng RuntimeException do ứng dụng tự tạo?

Ví dụ một bất biến của service bị vi phạm:

~~~java
if (amount.signum() < 0) {
    throw new IllegalArgumentException("amount must be non-negative");
}
~~~

Đây là fragment giả định `amount` là `BigDecimal`. Việc dùng unchecked giúp chữ ký API gọn khi tiền điều kiện đã được mô tả, nhưng không miễn nghĩa vụ kiểm tra dữ liệu từ nguồn không tin cậy. Nếu một tình huống là kết quả nghiệp vụ dự kiến (ví dụ từ chối hạn mức), ứng dụng có thể chọn result type hoặc domain exception theo convention.

Đừng lạm dụng `RuntimeException` chung với message mơ hồ ở mọi tầng; custom subtype hoặc mã lỗi ổn định có thể giúp caller phân loại.

## 6. Bảng `Error` thường gặp

| Kiểu | Nhánh | Nguyên nhân/thông điệp thông thường | Hướng xử lý |
| --- | --- | --- | --- |
| `AssertionError` | `Error` | Assertion thất bại hoặc code chủ động ném | Sửa invariant/test hoặc điều kiện assert |
| `OutOfMemoryError` | `VirtualMachineError` | JVM không thể cấp đủ tài nguyên bộ nhớ cho thao tác | Điều tra heap/native resources, tải và môi trường; không giả định catch an toàn |
| `StackOverflowError` | `VirtualMachineError` | Call stack vượt khả năng | Tìm recursion/vòng gọi bất thường |
| `NoClassDefFoundError` | `LinkageError` | Không thể định nghĩa/tìm class cần khi linking hoặc class init trước đó lỗi | Kiểm tra dependency/classpath/cause/init |
| `NoSuchMethodError` | `IncompatibleClassChangeError` thuộc `LinkageError` | Binary caller tham chiếu method không có ở runtime binary | Kiểm tra phiên bản thư viện/descriptor |
| `NoSuchFieldError` | `IncompatibleClassChangeError` | Runtime class thiếu field mà bytecode tham chiếu | Kiểm tra ABI/JAR/runtime |
| `UnsupportedClassVersionError` | `ClassFormatError` thuộc `LinkageError` | Class file version không được runtime hỗ trợ | So compiler target và runtime JDK |
| `ExceptionInInitializerError` | `LinkageError` | Static initializer ném exception không được xử lý | Xem `<clinit>` và `getCause()` |
| `LinkageError` | `Error` | Vấn đề linking/loading binary | Xác minh artifact, dependency/module/classloader |
| `InternalError` | `VirtualMachineError` | Điều kiện lỗi nội bộ JVM | Thu bằng chứng runtime/JDK, tránh tiếp tục mù quáng |

**`Error` không phải “một Exception checked nặng hơn”.** Nó là nhánh riêng dưới `Throwable` và unchecked. Các `Error` liên quan JVM/resource/linkage thường không phù hợp để catch rồi chạy tiếp như một lỗi nghiệp vụ thông thường.

### 6.1. `AssertionError` là một trường hợp cần hiểu đúng

`AssertionError` có thể sinh ra từ cú pháp `assert` khi assertions được bật, hoặc do code/test framework tạo ra. Java mặc định thường **không bật assertions** khi chạy không có `-ea`; đừng xây nghiệp vụ bảo mật hay validation bắt buộc chỉ bằng `assert`.

~~~java
assert amount >= 0 : "amount must be non-negative";
~~~

Đây là fragment với biến `amount` đã khai báo. Khi assertions bật và điều kiện sai, `AssertionError` có thể xuất hiện; khi assertions tắt, biểu thức assert không có tác dụng như một validation thông thường. Dùng exception/kiểm tra tham số rõ ràng cho các invariant phải luôn được thực thi.

### 6.2. Có phải mọi Error đều làm JVM tự thoát ngay?

Không có một quy tắc tuyệt đối như vậy. `AssertionError` có thể được test framework bắt để báo test fail; một thread có thể kết thúc vì uncaught `Error` nhưng các thread khác vẫn tồn tại. Tuy nhiên **không nên dựa vào khả năng catch Error để tiếp tục an toàn** sau `OutOfMemoryError` hoặc lỗi nghiêm trọng khác: trạng thái JVM/tài nguyên có thể không còn đáp ứng giả định.

Việc xử lý lỗi nghiêm trọng thuộc phạm vi runtime supervision, restart, telemetry và chiến lược phục hồi hệ thống. Một khối `catch (Throwable t) { return defaultValue; }` ở tầng nghiệp vụ thường phá vỡ khả năng nhận biết điều kiện nguy hiểm.

## 7. Chương trình Java 17 phân loại Throwable — biên dịch và chạy được

Chương trình sau chủ động tạo những object thuộc bốn nhóm để kiểm tra quan hệ kế thừa bằng `instanceof`. Nó còn cho thấy cách bắt checked `IOException` và unchecked `IllegalArgumentException`.

Lưu thành **`ThrowableClassificationDemo.java`**:

~~~java
import java.io.IOException;

public class ThrowableClassificationDemo {
    static class CustomChecked extends Exception {}
    static class CustomUnchecked extends RuntimeException {}

    static String classify(Throwable t) {
        if (t instanceof Error) return "unchecked Error";
        if (t instanceof RuntimeException) return "unchecked RuntimeException";
        if (t instanceof Exception) return "checked Exception";
        return "checked Throwable";
    }

    static void read() throws IOException {
        throw new IOException("io problem");
    }

    static void validate(int x) {
        if (x < 0) throw new IllegalArgumentException("negative");
    }

    public static void main(String[] args) {
        Throwable[] samples = {
            new IOException(),
            new CustomChecked(),
            new IllegalArgumentException(),
            new CustomUnchecked(),
            new AssertionError(),
            new Throwable()
        };

        for (Throwable t : samples) {
            System.out.println(t.getClass().getSimpleName()
                    + " -> " + classify(t));
        }

        try {
            read();
        } catch (IOException e) {
            System.out.println("caught checked: " + e.getMessage());
        }

        try {
            validate(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("caught unchecked: " + e.getMessage());
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 ThrowableClassificationDemo.java
java ThrowableClassificationDemo
~~~

**Stdout đã được kiểm chứng khi chạy chương trình:**

~~~text
IOException -> checked Exception
CustomChecked -> checked Exception
IllegalArgumentException -> unchecked RuntimeException
CustomUnchecked -> unchecked RuntimeException
AssertionError -> unchecked Error
Throwable -> checked Throwable
caught checked: io problem
caught unchecked: negative
~~~

### 7.1. Tại sao chương trình phân loại đúng?

Thứ tự các nhánh trong `classify` là chủ đích:
1. `Error` trước: thuộc nhánh Error, không phải Exception.
2. `RuntimeException` kế tiếp: là subclass `Exception` nhưng phải nhận nhãn **unchecked**.
3. `Exception` còn lại: checked.
4. Những `Throwable` còn lại: trong ví dụ là một `new Throwable()` trực tiếp, checked.

Nếu đảo hai điều kiện `if (t instanceof Exception)` và `if (t instanceof RuntimeException)`, mọi RuntimeException sẽ bị nhận nhầm là checked Exception, vì `RuntimeException extends Exception`. Đây là lỗi logic phân loại dễ gặp khi tự viết một báo cáo thống kê throwable.

Chương trình tạo `AssertionError` như một **đối tượng dùng để phân loại**, không ném nó. Điều đó cho phép minh họa cây kế thừa mà không khuyến khích catch `Error` để phục hồi nghiệp vụ.

### 7.2. Những điều ví dụ không ngụ ý

- Không phải mọi `Error` đều có chung chiến lược xử lý.
- Không phải mọi checked exception đều nên catch ngay tại nơi phát sinh.
- Không phải RuntimeException nào cũng là bug lập trình; có runtime wrapper cho lỗi I/O/async.
- Biên dịch chạy thành công ví dụ này không chứng minh code business nào cũng nên `catch (IOException)`. Hợp đồng API phải dẫn dắt lựa chọn.
- `new Throwable()` trực tiếp được dùng cho mục đích giáo dục, không phải khuyến nghị tạo lớp domain extends Throwable.

## 8. Checked exception: compiler yêu cầu catch hoặc declare

Xem phương thức:

~~~java
static String readFirstLine(Path path) throws IOException {
    return Files.readAllLines(path).get(0);
}
~~~

Đây là **fragment Java**, cần import `java.nio.file.Path`, `java.nio.file.Files`, `java.io.IOException`. `Files.readAllLines` có thể ném `IOException` checked. Ngoài ra, `get(0)` có thể ném `IndexOutOfBoundsException` unchecked nếu file rỗng; `throws IOException` không ngăn lỗi unchecked đó.

Khi caller gọi:

~~~java
String line = readFirstLine(path);
~~~

Nếu lời gọi có thể ném checked `IOException`, caller phải:
- **Bắt lỗi** bằng một `catch` phù hợp, hoặc
- **Khai báo `throws IOException`** (hay một supertype hợp lệ) để truyền tiếp.

Ví dụ catch:

~~~java
try {
    String line = readFirstLine(path);
    use(line);
} catch (IOException e) {
    handleIoFailure(e);
}
~~~

Ví dụ truyền tiếp:

~~~java
static void process(Path path) throws IOException {
    String line = readFirstLine(path);
    use(line);
}
~~~

Đây đều là **fragments**, những hàm `use`/`handleIoFailure` là giả định. Chỉ có một `throws` trong chữ ký **không có nghĩa JVM tự bắt exception**; nó nói với compiler/caller về khả năng exception checked có thể đi ra. Nếu không ai bắt cuối cùng, exception vẫn có thể lên tới thread boundary/uncaught handler.

### 8.1. Compile error khi bỏ catch/throws

Giả định có:

~~~java
static void readFile() throws IOException {
    throw new IOException("disk error");
}

static void caller() {
    readFile();
}
~~~

Đây là fragment cố tình **không biên dịch**: `caller` không xử lý checked exception do `readFile` khai báo. Compiler thường báo nội dung tương đương “unreported exception IOException; must be caught or declared to be thrown”. Đây là diagnostic minh họa, chữ cụ thể có thể khác compiler/phiên bản.

Hai cách sửa:

~~~java
static void caller() throws IOException {
    readFile();
}
~~~

Hoặc:

~~~java
static void caller() {
    try {
        readFile();
    } catch (IOException e) {
        report(e);
    }
}
~~~

Đây là hai **phương án fragment độc lập** cho cùng method; không đặt cả hai phương thức cùng chữ ký trong một class rồi biên dịch cùng lúc. `report` cần được định nghĩa. Nếu chỉ catch rồi bỏ qua, compiler hài lòng nhưng chương trình **chưa chắc đúng nghiệp vụ**. Compiler chỉ kiểm tra được **hợp đồng type**, không chứng minh recovery thành công.

### 8.2. Chữ ký `throws Exception` hợp lệ nhưng thường quá rộng

Một phương thức khai báo:

~~~java
void execute() throws Exception {
    readFile();
}
~~~

có thể truyền `IOException` ra ngoài qua supertype `Exception`. Nhưng caller mất độ cụ thể: không biết loại checked nào thực sự được API công khai. Trong API ổn định, ưu tiên các kiểu checked đủ cụ thể hoặc một domain exception có cause. Với framework/callback có quy ước `throws Exception`, vẫn có thể dùng theo contract.

**`throws Exception` không giới hạn chỉ các Exception có thể thoát:** RuntimeException và Error vẫn có thể phát sinh mà không cần khai báo. Đồng thời `throws Exception` cũng không có nghĩa phương thức luôn ném exception.

## 9. Unchecked exception: compiler không buộc khai báo nhưng vẫn có thể lan ra

~~~java
static int parseCount(String raw) {
    return Integer.parseInt(raw);
}
~~~

Đây là fragment. Nếu `raw` không hợp lệ, `Integer.parseInt` có thể ném `NumberFormatException` unchecked; compiler không yêu cầu `parseCount` khai báo `throws NumberFormatException`. Caller có thể catch nếu có recovery phù hợp, nhưng không bị bắt buộc.

Một developer **có thể** viết:

~~~java
static int parseCount(String raw) throws NumberFormatException {
    return Integer.parseInt(raw);
}
~~~

Dù `throws` này không bắt buộc, nó có thể được dùng để nhấn mạnh contract. Với public API, Javadoc thường là nơi mô tả điều kiện ném unchecked exception; chỉ dựa vào compiler sẽ không đủ.

### 9.1. Unchecked không có nghĩa nên luôn để crash

Nếu input người dùng sai format, tầng HTTP có thể bắt `NumberFormatException` ở ranh giới validation và trả thông báo lỗi 400 phù hợp. Nhưng catch nên:
- chỉ bắt type dự kiến;
- biết input nào lỗi;
- không che `NullPointerException` bất ngờ;
- không biến lỗi thành một kết quả “thành công” giả.

Ví dụ `Integer.parseInt("abc")` ném `NumberFormatException`; đó là loại unchecked, nhưng một controller có thể chuyển nó thành validation error **theo hợp đồng**. Không có mâu thuẫn giữa “unchecked” và “có thể xử lý được”.

## 10. `catch (Exception)` bắt được gì?

| Catch clause | Checked Exception subclass | RuntimeException subclass | Error subclass | Throwable trực tiếp |
| --- | --- | --- | --- | --- |
| `catch (IOException e)` | Chỉ IOException và subclass | Không, trừ khi một kiểu có quan hệ subtype phù hợp — không có RuntimeException subclass của IOException trong cây JDK | Không | Không |
| `catch (Exception e)` | **Có** | **Có** | **Không** | Không |
| `catch (RuntimeException e)` | Không | **Có** | Không | Không |
| `catch (Error e)` | Không | Không | **Có** | Không |
| `catch (Throwable t)` | **Có** | **Có** | **Có** | **Có** |

Bảng nói về **type matching khi một throwable đã được ném**. Nó không có nghĩa catch mọi kiểu đều là chính sách tốt. `catch (Exception)` sẽ bắt `IllegalArgumentException` và `NullPointerException`, do đó có thể che bug nếu trả fallback không phân loại. Nhưng `catch (Exception)` không bắt `OutOfMemoryError` hoặc `NoSuchMethodError`.

### 10.1. Thứ tự catch từ cụ thể đến tổng quát

~~~java
try {
    read();
} catch (IOException e) {
    handleIo(e);
} catch (Exception e) {
    handleOther(e);
}
~~~

Đây là fragment với `read`/`handleIo`/`handleOther` giả định. Nếu một exception thuộc IOException, nhánh đầu xử lý. Nếu đặt `catch (Exception)` trước `catch (IOException)`, nhánh thứ hai **không thể tới được** vì IOException là subtype của Exception, dẫn tới compile error.

Đừng viết `catch (RuntimeException)` trước `catch (IllegalArgumentException)` vì IllegalArgumentException là subtype của RuntimeException, tình huống tương tự.

### 10.2. Có nên `catch (Throwable)` để “không bị crash”?

Ở tầng nghiệp vụ thông thường, **không**. Catch Throwable có thể nuốt cả `OutOfMemoryError`, `StackOverflowError` hoặc `LinkageError` rồi chạy tiếp trên trạng thái không tin cậy. Ở một số ranh giới nền tảng đặc biệt (ví dụ framework thực thi task, test runner) có thể cần catch rộng để ghi nhận/truyền lại/giám sát, nhưng không nên chuyển toàn bộ Throwable thành `null` hoặc kết quả thành công.

Một số `Error` có thể là assertion có chủ đích. Bắt nó trong **test framework** để báo test failure khác với bắt nó trong code lưu dữ liệu rồi nói “đã lưu”.

## 11. `throw` và `throws` không giống nhau

- `throw expression;` là lệnh **ném một đối tượng Throwable** tại runtime.
- `throws Type1, Type2` là **khai báo chữ ký** về khả năng exception có thể lan ra, đặc biệt quan trọng với checked exception.

Ví dụ:

~~~java
static void openFile() throws IOException {
    throw new IOException("unavailable");
}
~~~

Đây là fragment hợp lệ trong class Java sau khi import `IOException`. `throws IOException` không tạo lỗi; `throw new IOException(...)` mới thực sự ném khi code chạy.

Với unchecked:

~~~java
static void requirePositive(int count) {
    if (count <= 0) {
        throw new IllegalArgumentException("count must be positive");
    }
}
~~~

Không bắt buộc khai báo `throws IllegalArgumentException`, dù phương thức có thể ném nó.

### 11.1. Java có cho `throw` một giá trị không phải Throwable không?

Không: `throw "error";` không hợp lệ, vì chuỗi String không phải subtype của Throwable. Java kiểm tra kiểu của expression được throw. Không có phép đổi mọi object sang exception tự động.

Với exception do ứng dụng tự định nghĩa:

~~~java
class InvalidDocumentException extends Exception {
    InvalidDocumentException(String message) {
        super(message);
    }
}
~~~

Đây là fragment checked. Nếu đổi `extends Exception` thành `extends RuntimeException`, compiler không còn yêu cầu caller catch/declare. Quyết định này **thay đổi hợp đồng compile-time** của API, không chỉ thay tên class.

## 12. Cách thiết kế custom exception checked và unchecked

Hai ví dụ:

~~~java
public final class StorageUnavailableException extends Exception {
    public StorageUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
public final class InvalidRequestException extends RuntimeException {
    public InvalidRequestException(String message) {
        super(message);
    }
}
~~~

Đây là **hai fragment lớp public độc lập**, cần lưu trong các file `StorageUnavailableException.java` và `InvalidRequestException.java` nếu biên dịch riêng ở package thích hợp. Lớp đầu checked, lớp sau unchecked.

### 12.1. Tiêu chí chọn

**Checked phù hợp khi:**
- Lỗi là một phần contract cần caller xác nhận đã xử lý hoặc tuyên bố truyền tiếp.
- Caller thường có hành động nghiệp vụ ý nghĩa (retry, đổi nguồn, báo lỗi rõ, cleanup).
- Module chấp nhận tăng chữ ký `throws` và propagation qua các tầng.

**Unchecked phù hợp khi:**
- Vi phạm tiền điều kiện hoặc invariant mà code phải sửa/validate.
- Lỗi không có recovery hợp lý ở mỗi tầng trung gian.
- API/framework/functional interface dùng convention unchecked.
- Một lỗi hạ tầng được wrap có chủ đích (ví dụ `UncheckedIOException`), đồng thời **giữ cause** và mô tả hợp đồng.

Những tiêu chí này là **heuristic**, không có luật “I/O luôn checked và validation luôn unchecked” cho mọi library. Một domain “không đủ hạn mức” có thể dùng Result, checked exception hoặc unchecked domain exception tùy cách tổ chức API.

### 12.2. Giữ cause khi bọc

~~~java
try {
    writeToDisk();
} catch (IOException e) {
    throw new UncheckedIOException("Write failed", e);
}
~~~

Đây là fragment với `writeToDisk` giả định và import `java.io.UncheckedIOException`. `UncheckedIOException` là subclass của RuntimeException, cho phép truyền lỗi I/O qua một boundary không cho khai báo checked; **cause vẫn là IOException**, có thể đọc bằng `getCause()`.

Không dùng `new RuntimeException(e.getMessage())` nếu cần giữ stack/cause từ I/O, vì message không chứa toàn bộ thông tin nguyên nhân.

## 13. Ngoại lệ checked với `try-with-resources`

`AutoCloseable.close()` được khai báo có thể ném `Exception`. Khi dùng một resource mà static type chỉ là `AutoCloseable`, compiler có thể yêu cầu xử lý `Exception` từ việc close, ngay cả khi phần thân không ném gì.

~~~java
static void use(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("using");
    }
}
~~~

Đây là fragment Java 9+ (hoạt động trên Java 17): resource parameter phải là biến cuối cùng hiệu lực (*effectively final*) khi sử dụng cú pháp `try (resource)`. Vì static type của `close` là `throws Exception`, chữ ký bên ngoài thường phải khai báo/bắt exception phù hợp.

Nếu static type là `java.io.Closeable`, `close()` khai báo `throws IOException` hẹp hơn. Đây là lý do **type của resource** ảnh hưởng checked exceptions từ cleanup.

### 13.1. Primary và suppressed

Nếu thân try ném A và resource.close() ném B, try-with-resources giữ A làm primary, B trong `A.getSuppressed()`. Nếu body hoàn tất bình thường nhưng close ném B, B có thể thành primary. Với nhiều resource, Java đóng theo thứ tự ngược và có thể có nhiều suppressed.

Điều đó không đổi checked/unchecked của các exception: một `IOException` từ close vẫn checked khi API cần catch/declare; một `RuntimeException` từ close vẫn unchecked. Suppressed là **quan hệ giữa object Throwable**, không phải nhóm phân loại mới.

## 14. `InterruptedException`: checked đặc biệt liên quan điều phối

`InterruptedException` là checked exception, xuất hiện ở những API blocking hỗ trợ interruption như `Thread.sleep`, `BlockingQueue.take` hoặc `Future.get` khi thread đang chờ bị interrupt.

~~~java
try {
    Thread.sleep(100);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đây là fragment bên trong một phương thức `void`/lambda thích hợp. Nếu không truyền tiếp được, thường khôi phục interrupt flag và kết thúc công việc hợp tác. Nếu phương thức cho phép `throws InterruptedException`, có thể truyền tiếp cho caller.

**Không nuốt `InterruptedException` rồi tiếp tục vô hạn**: nó có thể là yêu cầu hủy/shutdown. Nhưng cũng không coi mọi interrupt là lỗi nghiệp vụ do một task khác ném; nó là tín hiệu tác động lên thread đang chờ.

### 14.1. `CancellationException` lại là unchecked

`Future.cancel(...)` có thể làm `Future.get()` ném `CancellationException`; nó kế thừa RuntimeException nên unchecked. Hai kiểu này thể hiện hai sự kiện khác nhau:
- `InterruptedException`: **thread đang chờ** bị interrupt.
- `CancellationException`: Future được quan sát ở trạng thái canceled.

Neither guarantees the underlying remote side effect rolled back. Khi caller hủy sau timeout, task có thể vẫn chạy nếu không hợp tác. Đừng catch cả hai và tự trả “đã thành công”.

## 15. `Future` và `CompletableFuture`: bảng đối chiếu exception

| API / tình huống | Exception caller quan sát | Checked? | Ghi chú |
| --- | --- | --- | --- |
| `Future.get()` khi task thất bại | `ExecutionException` | **Có** | Lỗi task nằm ở `getCause()` |
| `Future.get()` khi thread chờ bị interrupt | `InterruptedException` | **Có** | Task không nhất thiết đã dừng |
| `Future.get(timeout, unit)` khi quá hạn | `TimeoutException` | **Có** | Không tự hủy task |
| `Future.get()` sau khi future bị hủy | `CancellationException` | Không | Subclass của RuntimeException |
| `CompletableFuture.join()` khi stage thất bại | Thường `CompletionException` | Không | Cause giữ lỗi từ stage nguồn |
| `CompletableFuture.join()` trên future canceled | `CancellationException` có thể ném trực tiếp | Không | Cancellation không tự interrupt supplier |
| `CompletableFuture.get()` khi stage thất bại | `ExecutionException` | **Có** | `get()` tuân hợp đồng Future |
| `CompletableFuture.orTimeout(...)` khi stage quá hạn | Future hoàn thành ngoại lệ bằng `TimeoutException` | Kiểu TimeoutException là checked | `join()` thường bọc nó bằng unchecked `CompletionException` |
| Callback `whenComplete` tự ném RuntimeException | Stage phụ thuộc có thể thất bại | Không đối với RuntimeException | Nếu upstream đã lỗi, lỗi upstream được ưu tiên theo hợp đồng whenComplete |

**Điểm dễ nhầm:** cùng một `TimeoutException` là **checked type**, nhưng nếu được bọc trong `CompletionException` rồi đi qua `join()` thì caller nhận **unchecked wrapper**. Kiểu gốc không đổi, chỉ kênh biểu diễn lỗi ở boundary thay đổi.

### 15.1. `CompletableFuture.cancel(true)` không giống mọi `FutureTask.cancel(true)`

`CompletableFuture` triển khai Future nhưng tham số `mayInterruptIfRunning` trong `CompletableFuture.cancel(boolean)` không được dùng để điều khiển interrupt supplier. Nó có thể hoàn thành future bằng `CancellationException` mà phép tính đang chạy vẫn tiếp tục. Ngay cả với `FutureTask`, interruption là cơ chế hợp tác, không phải cưỡng chế rollback công việc.

Vì thế một phân loại “unchecked CancellationException” không nói gì chắc chắn về trạng thái side effect bên ngoài.

## 16. Reflection và binary compatibility: checked khác Error

Hai tên dễ nhầm:

| Kiểu | Checked? | Nghĩa |
| --- | --- | --- |
| `ClassNotFoundException` | Có | Một lời gọi API tìm class theo tên không tìm thấy class (ví dụ `Class.forName`) |
| `NoClassDefFoundError` | Không, thuộc Error | JVM không thể dùng/định nghĩa class cần thiết tại linking/initialization; nguyên nhân có thể là class thiếu hoặc init lỗi |

Tương tự:
- `InvocationTargetException` (checked, reflection) có thể bọc throwable do method được gọi ném.
- `ExceptionInInitializerError` (Error unchecked) thường liên quan static initialization thất bại.
- `NoSuchMethodException` (checked, reflection khi tra cứu method) khác `NoSuchMethodError` (Error unchecked, binary không tương thích lúc linking).

Đừng xử lý `NoSuchMethodError` bằng cách trả default như một phản hồi business bình thường. Nó thường đòi đối chiếu **class/JAR thực được JVM nạp, method descriptor, dependency versions và build/deploy artifact**. `ClassNotFoundException` cũng cần xác minh classloader/module path phù hợp, nhưng nguyên tắc catch/declare compile-time của nó khác.

### 16.1. Lỗi khi khởi tạo class có thể sinh chuỗi triệu chứng

Một static initializer ném exception có thể dẫn đến `ExceptionInInitializerError` ở lần truy cập đầu. Các lần truy cập sau vào class bị đánh dấu erroneous có thể dẫn đến `NoClassDefFoundError`. Đọc **cause và log gốc tại lần đầu** thay vì chỉ xem một lỗi về sau.

Không có nguyên tắc “NoClassDefFoundError luôn là thiếu JAR”; đôi khi class tồn tại nhưng initialization trước đó đã thất bại.

## 17. Checked exception và overriding

Quy tắc quan trọng khi override một instance method:
- Implementation **không được khai báo checked exception mới hoặc rộng hơn** những gì chữ ký method bị override cho phép.
- Có thể **khai báo checked exception hẹp hơn** hoặc không khai báo nữa.
- Unchecked exception không chịu giới hạn checked tương tự; vẫn phải tuân thủ contract và Liskov/thiết kế API ở mức ngữ nghĩa.

Ví dụ:

~~~java
interface Reader {
    String read() throws IOException;
}

final class FileReaderImpl implements Reader {
    @Override
    public String read() throws java.io.FileNotFoundException {
        throw new java.io.FileNotFoundException("missing");
    }
}
~~~

Đây là fragment, cần import `IOException` hoặc qualified name. `FileNotFoundException` là subclass của IOException, nên override hợp lệ. Nếu implementation thay bằng `throws SQLException` thì **không hợp lệ** vì SQLException là checked không nằm trong giới hạn của `Reader.read()`.

Việc implementation **không** khai báo `throws` được phép, nhưng caller thông qua reference `Reader` vẫn nhìn thấy contract `throws IOException` của interface khi compile.

### 17.1. Tại sao rule này tồn tại?

Nếu một API đã hứa chỉ ném checked IOException, một implementation khác không thể bất ngờ bắt caller phải xử lý checked SQLException theo signature mới mà không thay đổi type contract. Điều đó giúp tính thay thế giữa interface/base class và implementation.

Không nên dùng `throws Exception` ở interface chỉ để mọi implementation sau này tự do ném checked exception bất kỳ, trừ khi API thật sự cần hợp đồng rộng đó.

## 18. Checked exception trong lambda và method reference

Một lambda phải tương thích với chữ ký của **functional interface**. `java.util.function.Function<T,R>` chỉ có `R apply(T t)` và không khai báo checked exception. Do đó:

~~~java
Function<Path, String> loader = path -> Files.readString(path);
~~~

Đây là fragment **cố tình không biên dịch** (giả định imports), vì `Files.readString` có thể ném checked `IOException` nhưng `Function.apply` không cho `throws IOException`.

Một số hướng xử lý đúng:
1. Dùng interface tự định nghĩa `ThrowingFunction<T,R>` có `throws IOException` khi API kiểm soát được interface.
2. Bắt IOException bên trong lambda rồi chuyển thành `UncheckedIOException` **kèm cause**, nếu hợp đồng pipeline chấp nhận unchecked.
3. Trả result có kiểu `Found/Failed` thay vì chỉ giá trị thành công.
4. Đổi thiết kế để I/O thực hiện ở tầng đã có quyền xử lý checked exception.

Ví dụ fragment có wrapper:

~~~java
Function<Path, String> loader = path -> {
    try {
        return Files.readString(path);
    } catch (IOException e) {
        throw new UncheckedIOException("Cannot load " + path, e);
    }
};
~~~

Đây là fragment, cần import `Function`, `Path`, `Files`, `IOException`, `UncheckedIOException`. Bọc có cause giữ thông tin nguồn; không catch rồi trả chuỗi rỗng nếu chuỗi rỗng cũng là dữ liệu hợp lệ.

### 18.1. Streams không tự hiểu checked exception

`stream.map(...)` nhận Function, không tự thêm checked `throws IOException` vào chữ ký lambda. Không nên dùng một “sneaky throws” không rõ hợp đồng chỉ để vượt compiler, nhất là trong thư viện dùng chung. Chọn một adapter/wrapper/result có chính sách công khai.

## 19. Multi-catch và type chung

Java hỗ trợ bắt nhiều loại ngoại lệ không có quan hệ subclass trực tiếp:

~~~java
try {
    performIoAndDbOperation();
} catch (IOException | SQLException e) {
    report(e);
}
~~~

Đây là fragment với các hàm giả định; cả hai checked exception phải là loại có thể được phát sinh theo phân tích compile-time của khối try (và phải có import). Multi-catch chỉ hợp lệ khi các lựa chọn không có quan hệ cha–con bị cấm. `catch (IOException | FileNotFoundException e)` không hợp lệ vì FileNotFoundException là subclass của IOException.

Trong một multi-catch, biến `e` có các quy tắc typing riêng và là effectively final; cần dùng các thao tác có mặt trên kiểu chung thích hợp (ví dụ `Throwable.getMessage()`), không giả định e luôn là IOException.

Nếu `IOException` cần retry còn `SQLException` cần rollback theo những bước khác nhau, **đừng gộp** chỉ để giảm dòng code. Multi-catch phù hợp khi chính sách xử lý thực sự giống nhau.

## 20. Những lối hiểu sai phổ biến

### Sai 1 — “Mọi `Exception` đều checked”

Sai vì `RuntimeException extends Exception` nhưng unchecked. Hãy hỏi kiểu đó có nằm dưới RuntimeException hay Error không.

### Sai 2 — “`Error` là subclass của `Exception`”

Sai. Hai lớp là **hai nhánh dưới Throwable**. `catch (Exception)` không bắt Error.

### Sai 3 — “Checked là lỗi an toàn để phục hồi; unchecked là lỗi không phục hồi được”

Sai. Checked/unchecked là lựa chọn type contract của compiler, không chứng minh transactional/side effect safety. Một `IOException` có thể xảy ra sau khi file đã ghi một phần; một `NumberFormatException` có thể được chuyển thành lỗi validation an toàn.

### Sai 4 — “`throws` đã xử lý lỗi”

Sai. `throws` chỉ khai báo đường lan lỗi, không catch, rollback hay log.

### Sai 5 — “Catch rộng làm hệ thống ổn định”

`catch (Exception)` có thể che RuntimeException do bug. `catch (Throwable)` còn có thể che Error. Nếu không có recovery thật và trạng thái lỗi rõ, việc catch chỉ làm sai kết quả.

### Sai 6 — “`RuntimeException` không bao giờ cần ghi vào tài liệu API”

Compiler không bắt buộc khai báo, nhưng public API vẫn cần Javadoc/contract cho những điều kiện như invalid argument, illegal state hoặc timeout wrapper mà caller phải biết.

### Sai 7 — “`Error` luôn khiến cả JVM dừng ngay”

Không tuyệt đối. Ví dụ assertion có thể bị test framework bắt. Nhưng khả năng bắt không đồng nghĩa có thể tiếp tục an toàn sau lỗi nghiêm trọng.

### Sai 8 — “`Exception.getCause()` luôn khác null”

Không. Nhiều exception được tạo không có cause. Trước khi dereference `getCause()`, hãy kiểm tra, nhất là trong code log/unwrap tổng quát.

### Sai 9 — “Checked exception làm tất cả caller khó chịu, cứ chuyển mọi lỗi thành RuntimeException”

Bọc một checked exception thành unchecked có thể cần thiết ở ranh giới không hỗ trợ checked, nhưng **phải giữ cause và ngữ nghĩa**. Chuyển toàn bộ lỗi thành `RuntimeException("failed")` làm mất khả năng phân loại nghiệp vụ.

### Sai 10 — “Dùng `Optional.empty()` sau catch là đã xử lý checked IOException”

Compiler chấp nhận nhưng caller không còn phân biệt “không tìm thấy” với “storage lỗi” nếu empty là giá trị hợp lệ. Hãy giữ exception hoặc trả result `Failed`.

### Sai 11 — “`CancellationException` là checked như `InterruptedException`”

Không. `CancellationException` extends IllegalStateException/RuntimeException, unchecked; `InterruptedException` checked.

### Sai 12 — “`CompletionException` và `ExecutionException` giống nhau”

Hai kiểu đều có thể bọc nguyên nhân từ task, nhưng `CompletionException` là unchecked, `ExecutionException` là checked. Đọc boundary `join` vs `get` để hiểu vì sao.

### Sai 13 — “`NoClassDefFoundError` = `ClassNotFoundException`”

Không. Chúng có cây kế thừa khác, thời điểm phát sinh và ngữ nghĩa API/runtime khác. Đọc classloader, dependency và cause cụ thể.

### Sai 14 — “`Error` trong mã Java là mức log ERROR”

Không. `java.lang.Error` là lớp Throwable; log severity `ERROR` là khái niệm do logging framework quy định. Một `IOException` có thể được log ở mức ERROR mà **không trở thành `java.lang.Error`**.

## 21. Thực hành kiểm thử compiler và runtime

Ngoài chương trình runnable ở mục 7, hãy tự làm ba thí nghiệm ngắn.

### Thí nghiệm A — Compiler buộc xử lý checked

~~~java
import java.io.IOException;

public class CheckedCompileTest {
    static void fail() throws IOException {
        throw new IOException("read failed");
    }

    public static void main(String[] args) {
        fail(); // Cố ý lỗi compile: thiếu catch hoặc throws.
    }
}
~~~

Đây là **file Java cố tình không biên dịch**. Chạy `javac CheckedCompileTest.java` và xác nhận diagnostic liên quan unreported checked exception. Sau đó thêm `throws IOException` vào `main` **hoặc** bọc `fail()` trong `try/catch` rồi compile lại. Khi để `throws IOException` trên main và chạy mà không có catch, chương trình sẽ ném IOException lên ranh giới main; đây là behavior khác với compile-time success.

### Thí nghiệm B — Unchecked không cần khai báo

~~~java
public class UncheckedCompileTest {
    static void fail() {
        throw new IllegalArgumentException("invalid");
    }

    public static void main(String[] args) {
        fail();
    }
}
~~~

File Java này **biên dịch được**; khi chạy thì ném IllegalArgumentException và nếu không được catch, thread main sẽ kết thúc với stack trace. Đừng nhầm “biên dịch được” với “runtime thành công”.

### Thí nghiệm C — `catch (Exception)` không bắt `AssertionError`

~~~java
public class ErrorCatchTest {
    public static void main(String[] args) {
        try {
            throw new AssertionError("assertion failed");
        } catch (Exception e) {
            System.out.println("caught Exception");
        }
    }
}
~~~

File Java này có thể **biên dịch**, nhưng khi chạy, `AssertionError` không đi vào `catch (Exception)` vì Error không phải Exception. Đây là một thí nghiệm ngắn trong môi trường học tập, **không** phải khuyến nghị làm ứng dụng production chủ động throw Error để điều khiển nghiệp vụ.

Nếu muốn ghi nhận assertion failure có kiểm soát trong test, dùng test framework; đừng thêm `catch (Throwable)` để chương trình “luôn in thành công”.

## 22. Bảng quyết định khi đọc một exception trong log

~~~text
Gặp một Throwable trong Java
|
+-- Thuộc Error hoặc subclass?
|      +-- Có -> unchecked; xem VM/linkage/assertion/runtime
|      +-- Không
|
+-- Thuộc RuntimeException hoặc subclass?
|      +-- Có -> unchecked; xem cause, input, invariant, wrapper
|      +-- Không
|
+-- Thuộc Exception hoặc subclass?
|      +-- Có -> checked; caller phải catch/declare theo quy tắc Java
|      +-- Không -> Throwable trực tiếp/nhánh khác: checked
|
+-- Xử lý thế nào?
       +-- Có recovery thật -> catch chính xác và xác minh kết quả
       +-- Không có recovery -> propagate/wrap giữ cause
       +-- Có side effect -> xác minh trạng thái, không giả rollback
       +-- Qua async -> đọc ExecutionException/CompletionException cause
~~~

Cây phân loại giúp hiểu **kiểu và compiler obligations**, nhưng quyết định **cách phục hồi** vẫn phụ thuộc vào business contract. Không có nhánh mặc định “checked → retry” hoặc “unchecked → bỏ qua”.

## 23. Checklist khi thiết kế hoặc review xử lý ngoại lệ

- [ ] Biết rõ exception thuộc `Throwable`, `Exception`, `RuntimeException` hay `Error`.
- [ ] Không gọi mọi subclass của `Exception` là checked.
- [ ] Không giả định `catch (Exception)` sẽ bắt `Error`.
- [ ] Hiểu checked yêu cầu `catch` hoặc `throws` ở những điểm có thể lan ra.
- [ ] Chọn loại custom exception có chủ đích, tránh kế thừa Throwable trực tiếp khi không cần.
- [ ] Nếu API public ném unchecked theo tiền điều kiện, đã có tài liệu và test.
- [ ] Không dùng `catch (Throwable)` để che lỗi rồi trả mặc định.
- [ ] Không log rồi rethrow ở mọi tầng gây duplicate; giữ cause khi wrap.
- [ ] Không nuốt `InterruptedException`; propagate hoặc restore status phù hợp.
- [ ] Phân biệt `ExecutionException` checked với `CompletionException` unchecked.
- [ ] Phân biệt `ClassNotFoundException` với `NoClassDefFoundError` và `NoSuchMethodException` với `NoSuchMethodError`.
- [ ] Biết `try-with-resources` có thể ném checked từ `close()` và giữ suppressed errors.
- [ ] Không dùng `Optional.empty()`, `null` hoặc `false` để che lỗi mà contract không nói rõ.
- [ ] Nếu exception đến sau side effect hoặc timeout, không tự tuyên bố rollback.
- [ ] Nếu lỗi liên quan runtime JAR/linkage, xác minh binary được nạp thay vì chỉ sửa source line.
- [ ] Test cả trường hợp compile-time của checked và đường runtime của unchecked.
- [ ] Chọn Error handling phù hợp mức độ nghiêm trọng, không cố tiếp tục trong trạng thái không đáng tin.

## 24. Bài tập củng cố

### Bài 1 — Phân loại chính xác

Với từng kiểu sau, ghi: **cha gần nhất trong cây quan trọng**, **checked/unchecked**, và **compiler có buộc catch/declare không**:

~~~text
IOException
NumberFormatException
RuntimeException
SQLException
CancellationException
InterruptedException
CompletionException
ExecutionException
AssertionError
OutOfMemoryError
ClassNotFoundException
NoClassDefFoundError
Throwable
Exception
Error
UncheckedIOException
TimeoutException
~~~

Đáp án định hướng: mọi lớp con của RuntimeException hoặc Error là unchecked. IOException/SQLException/InterruptedException/ExecutionException/TimeoutException/ClassNotFoundException là checked. Bản thân Throwable và Exception là checked. UncheckedIOException và CompletionException thuộc RuntimeException; AssertionError và OutOfMemoryError thuộc Error.

### Bài 2 — Sửa lỗi compile

Cho phương thức `load() throws IOException` và một caller không khai báo throws, không catch. Hãy viết **hai** cách sửa. Giải thích vì sao một cách để caller cấp cao hơn chịu trách nhiệm và cách còn lại có thể phục hồi ngay trong phương thức hiện tại.

### Bài 3 — Phân biệt catch

Cho đoạn code có `catch (Exception e)`. Hãy dự đoán nó có bắt được `NullPointerException`, `IOException` và `StackOverflowError` hay không. Đáp án lần lượt: **có**, **có**, **không**; sau đó chứng minh bằng cây kế thừa, không đoán theo tên.

### Bài 4 — Lỗi API và binary

Một ứng dụng compile theo library có `Client.send(String)` nhưng runtime chạy bản JAR thiếu method này. Exception `NoSuchMethodError` thuộc nhóm nào? Nó có thể được khắc phục bằng cách thêm `throws IOException` vào method gọi không? Hướng sửa nên tập trung vào **phiên bản JAR/ABI được nạp ở runtime**.

### Bài 5 — Async và timeout

Một task ném `IOException`, caller A lấy qua `Future.get()`, caller B lấy qua `CompletableFuture.join()`, caller C gọi `Future.get(timeout)` rồi hết hạn. Hãy nêu wrapper hoặc lỗi quan sát thích hợp và giải thích tại sao **hết hạn chờ** không chứng minh task đã dừng.

### Bài 6 — Checked exception trong lambda

Thử dùng `Files.readString(path)` trong `Stream.map`. Compiler báo điều gì? Hãy thiết kế một cách giữ `cause` bằng `UncheckedIOException` hoặc trả typed Result, và test rằng lỗi đọc không bị chuyển thành chuỗi rỗng giả.

### Bài 7 — Không đánh đồng lỗi với kết quả nghiệp vụ

Một method tìm user trả `Optional.empty()` khi không tồn tại. Nếu database ném checked `SQLException`, có nên catch và trả Optional rỗng không? Trả lời dựa vào hợp đồng absence vs failure, nguy cơ negative caching và hành vi caller.

## 25. Tóm tắt

**Bốn sự thật cần nhớ:**

1. `Throwable` là gốc của nhánh những object được phép ném trong Java. `Exception` và `Error` là hai nhánh riêng.
2. **Checked** = subtype của Throwable **không thuộc** nhánh RuntimeException hoặc Error; compiler thường bắt buộc bắt/khai báo khi có thể lan ra.
3. **Unchecked** = RuntimeException, Error và mọi subclass của chúng. `RuntimeException` **đồng thời là Exception**; `Error` **không phải Exception**.
4. Compiler kiểm tra kiểu, **không chứng minh** chương trình đã phục hồi đúng, không rollback tự động và không bảo đảm lỗi nghiêm trọng có thể tiếp tục chạy an toàn.

Khi thiết kế API, hãy dùng bảng phân loại để hiểu nghĩa vụ compiler; sau đó quyết định `catch`, `throws`, wrapper, typed result và monitoring theo **hợp đồng nghiệp vụ và trạng thái thực sự của công việc**.