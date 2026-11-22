# Tra cứu JLS, `Throwable` Javadoc và hợp đồng ngoại lệ của từng API trong Java

Khi đọc hoặc viết mã Java, một câu hỏi thường gặp là: **phương thức này có thể ném ngoại lệ gì, ngoại lệ đó được bắt hay lan truyền như thế nào, và tài liệu nào là căn cứ đáng tin?** Không thể trả lời chính xác chỉ từ tên ngoại lệ, một đoạn code trên diễn đàn hoặc thử chạy một lần. Java có nhiều cấp tài liệu với phạm vi trách nhiệm khác nhau:

1. **Java Language Specification (JLS):** đặc tả các quy tắc của ngôn ngữ, như `throw`, `throws`, kiểm tra checked exception, chọn nhánh `catch`, cách `finally` và `try-with-resources` kết thúc.
2. **Javadoc của `Throwable`:** hợp đồng các thành phần và thao tác trên đối tượng lỗi: message, cause, stack trace, suppressed exceptions, constructor và `initCause`.
3. **Javadoc của API cụ thể:** một phương thức như `Files.readString`, `Thread.sleep`, `Future.get` hoặc `CompletableFuture.join` khai báo ngoại lệ nào, lỗi nào thuộc điều kiện nào, lúc nào lệnh trả về và có tác dụng phụ gì.

Cách học đúng là **đọc cả ba nơi khi cần**, đối chiếu **đúng phiên bản Java đang sử dụng**, rồi viết một ví dụ nhỏ để kiểm chứng cách hiểu. Bài này dùng **JLS Java SE 17 và Javadoc Java 17** làm mốc thống nhất; những tính năng hoặc chữ ký của các bản Java khác phải được tra cứu trên tài liệu tương ứng.

## 1. Bản đồ nguồn tài liệu: hỏi gì, đọc ở đâu?

| Câu hỏi | Nguồn chính | Điều tìm trong tài liệu |
| --- | --- | --- |
| Vì sao `IOException` phải được bắt hoặc khai báo? | JLS §11.1–§11.2 | Checked/unchecked, compile-time checking |
| `throw` và `throws` khác nhau thế nào? | JLS §14.18, §8.4.6 | Câu lệnh ném lỗi và mệnh đề trong chữ ký |
| `catch (Exception e)` xử lý những loại nào? | JLS §11.2–§11.3, §14.20 | Kiểu bắt, thứ tự handler, exception analysis |
| `finally` có thể ghi đè `return` hoặc lỗi gốc không? | JLS §14.20.2 | Quy tắc hoàn tất bình thường/bất thường |
| Lỗi `close()` nằm ở đâu khi thân `try` cũng lỗi? | JLS §14.20.3 và `Throwable` Javadoc | `try-with-resources`, suppressed exceptions |
| Vì sao `new Wrapper(message, cause)` khác `new Wrapper(message)`? | `Throwable` Javadoc | `getCause`, constructor và cause chain |
| `initCause()` được gọi nhiều lần không? | `Throwable` Javadoc | Khởi tạo cause một lần và lỗi khi gọi sai |
| `getStackTrace()` cho biết gì? | `Throwable` Javadoc | Stack trace, `fillInStackTrace`, dữ liệu có thể rỗng |
| `Files.readString(path)` có `throws IOException` không? | `Files.readString` Javadoc | Chữ ký, phần `Throws`, ý nghĩa điều kiện |
| `Thread.sleep(...)` có thể nhận interrupt không? | `Thread.sleep` Javadoc | `InterruptedException`, xử lý interrupted status |
| `join()` và `get()` báo lỗi khác nhau thế nào? | `CompletableFuture`, `Future` Javadoc | `CompletionException`, `ExecutionException`, hủy, ngắt |
| Hành vi có thay đổi ở JDK khác không? | JLS/Javadoc **đúng phiên bản** | `Since`, ghi chú implementation, deprecation |

Không nên nhầm **quy tắc chung của ngôn ngữ** với **lời hứa của một phương thức cụ thể**. JLS xác định khi nào chương trình biên dịch và luồng điều khiển khi ném lỗi. Nó không thể thay thế bản mô tả rằng `readString` đọc UTF-8 hay một deadline của `Future.get` có thể ném `TimeoutException`.

### Ba liên kết khởi đầu

- JLS 17, Chương 11 — Exceptions: https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html
- JLS 17, Chương 14 — Statements (`throw`, `try`, `catch`, `finally`, `try-with-resources`): https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html
- Java 17, `Throwable` Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html

Tất cả ví dụ trong bài sử dụng **đặc tả Java 17**. Khi dự án dùng Java 21 hoặc một phiên bản khác, hãy đổi cả hai bộ tài liệu theo phiên bản trước khi áp dụng kết luận về API mới.

## 2. Cách đọc JLS theo đúng vấn đề

JLS không phải danh sách mẹo lập trình. Nó trình bày các **quy tắc chuẩn tắc** của ngôn ngữ Java. Khi tra cứu, đọc đúng section và cả những điều kiện, ngoại lệ trong quy tắc.

### 2.1. JLS §11 — Các loại ngoại lệ và kiểm tra lúc biên dịch

JLS phân biệt:

- **Checked exception:** các lớp thuộc `Throwable` nhưng **không** nằm trong nhánh `RuntimeException` hoặc `Error`. Thường gặp `IOException`, `SQLException`, `InterruptedException`.
- **Unchecked exception:** `RuntimeException` và các lớp con, `Error` và các lớp con. Lập trình viên không bắt buộc khai báo những loại này bằng `throws`.
- **Compile-time exception checking:** nếu một lời gọi, câu lệnh hoặc thân phương thức có thể ném checked exception theo phân tích của compiler, nó phải được bắt thích hợp hoặc có khai báo `throws` tương thích.

Đọc mục **§11.2.1** và **§11.2.2** khi câu hỏi là “trình biên dịch xác định những ngoại lệ *có thể ném* như thế nào?”. Đọc **§11.2.3** khi thấy lỗi biên dịch kiểu *unreported exception; must be caught or declared to be thrown*.

Ví dụ **cố ý không biên dịch**, dùng để tra lỗi checked exception:

```java
import java.io.IOException;

class IncorrectCheckedHandling {
    static void read() throws IOException {
        throw new IOException("read failed");
    }

    static void run() {
        read(); // Lỗi biên dịch: không bắt hoặc khai báo IOException.
    }
}
```

Không có lệnh chạy chương trình trên vì code này **được viết có chủ đích để compiler từ chối**. Khắc phục bằng cách khai báo `static void run() throws IOException`, hoặc bắt `IOException` và xử lý đúng ở đây. Không chuyển bừa thành `catch (Exception ignored) {}` chỉ để hết lỗi compiler.

**Lưu ý:** compiler kiểm tra **các checked exception có thể phát sinh theo phép phân tích tĩnh**, không bảo đảm ở runtime sẽ không có unchecked exception khác. Java cũng không buộc Javadoc liệt kê mọi tình huống như `NullPointerException` do bug trong code người gọi.

### 2.2. JLS §8.4.6 — Mệnh đề `throws`

Ví dụ:

```java
static String load() throws java.io.IOException {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.txt"));
}
```

Đây là một **phương thức minh họa**, cần đặt trong lớp Java; chương trình không có file `config.txt` vẫn có thể biên dịch nhưng có thể thất bại lúc chạy. `throws IOException` nói phương thức có thể **để checked exception này thoát ra**, không có nghĩa mọi lời gọi chắc chắn ném lỗi hoặc nó đã được xử lý.

Mệnh đề `throws` còn là một phần của hợp đồng override: một phương thức override không được tự mở rộng tập checked exceptions vượt quá hợp đồng phương thức cha/interface theo quy tắc JLS. Đừng đổi method signature chỉ vì một lời gọi tầng thấp nay dùng thư viện khác; cân nhắc dịch ngoại lệ ở ranh giới thích hợp mà **giữ cause**.

### 2.3. JLS §14.18 — Câu lệnh `throw`

`throw expression;` thực sự chuyển luồng điều khiển bằng một đối tượng `Throwable` hoặc lớp con. Ngược lại, `throws X` nằm trong **khai báo** phương thức hoặc constructor. JLS giải thích cả vấn đề kiểu tĩnh của biểu thức ném, xử lý `throw null` và trường hợp biểu thức tạo exception cũng có thể lỗi.

Không dùng `throw` để diễn đạt trạng thái thành công thông thường nếu kiểu kết quả có thể biểu diễn rõ ràng hơn. Tuy vậy, ngoại lệ vẫn là cách hợp lệ để báo điều kiện đặc biệt mà người gọi phải xử lý.

### 2.4. JLS §14.20 — `try`–`catch`–`finally`

Đây là nơi phải đọc khi cần biết:

- `catch` nào có thể bắt ngoại lệ và vì sao thứ tự các `catch` quan trọng.
- Vì sao `finally` vẫn chạy trên đường `return` hoặc `throw`.
- Điều gì xảy ra khi chính `finally` trả về hoặc ném lỗi mới.
- Ngoại lệ nào là **primary** khi cả thân `try-with-resources` và `close()` cùng thất bại.

Ví dụ:

```java
static int masked() {
    try {
        throw new IllegalStateException("origin");
    } finally {
        return 10;
    }
}
```

Đây là một **phương thức minh họa**. Nó hoàn tất bình thường bằng `10`; câu lệnh `return` trong `finally` thay việc hoàn tất bất thường từ `try`. Code hợp lệ về mặt ngôn ngữ nhưng là mẫu cần tránh vì che nguyên nhân thất bại.

**Không suy diễn** rằng `finally` luôn hoàn tất thành công, luôn bảo toàn lỗi gốc hoặc luôn chạy khi cả tiến trình JVM bị chấm dứt đột ngột. JLS quy định hành vi của luồng thực thi Java trong điều kiện áp dụng, không phải cam kết phục hồi dữ liệu sau khi hệ điều hành tắt tiến trình.

## 3. Cách đọc `Throwable` Javadoc: đối tượng lỗi mang dữ liệu gì?

`Throwable` là lớp gốc của `Exception` và `Error`, định nghĩa phần lớn cơ chế chẩn đoán:

| Thành phần | Phương thức | Điều không nên hiểu nhầm |
| --- | --- | --- |
| Detail message | `getMessage()` | Có thể `null`; không phải stack trace hoặc cause |
| Cause | `getCause()` | Có thể `null`; không tự được gắn khi chỉ truyền message |
| Suppressed exceptions | `getSuppressed()`, `addSuppressed(...)` | Là lỗi phụ, không phải nguyên nhân chính |
| Stack trace | `getStackTrace()`, `printStackTrace(...)` | Có thể rỗng nếu bị vô hiệu hóa hay thiếu dữ liệu |
| Ghi lại stack | `fillInStackTrace()` | Chủ động cập nhật thông tin stack của chính object |
| Chỉnh stack | `setStackTrace(...)` | Không nên dùng để làm giả vị trí lỗi |
| Gắn cause sau tạo | `initCause(...)` | Chỉ được khởi tạo một lần khi cause chưa khởi tạo |

### 3.1. Message không bằng cause

So sánh:

```java
Throwable root = new java.io.IOException("disk unavailable");

RuntimeException lost =
        new IllegalStateException("load failed: " + root.getMessage());

RuntimeException preserved =
        new IllegalStateException("load failed", root);
```

Đây là đoạn minh họa bên trong một phương thức. `lost.getCause()` là `null`, còn `preserved.getCause() == root` là `true`. Khi formatter in stack của `preserved`, người điều tra có thể xem chuỗi **`Caused by:`** và nguyên nhân gốc. Khi chỉ giữ message, logger không thể tái tạo các khung stack từ `root`.

### 3.2. Constructor với cause và `initCause()`

Một constructor nhận `(String message, Throwable cause)` thường là cách rõ ràng nhất để bọc lỗi. `initCause(...)` tồn tại để hỗ trợ các ngoại lệ đã được tạo mà chưa khởi tạo nguyên nhân, nhưng không phải setter có thể thay đổi tùy ý: gọi lại sau khi đã gán cause gây `IllegalStateException`; tự đặt object làm cause của chính nó cũng không hợp lệ.

Đặc biệt, constructor đã **khởi tạo cause thành `null`** khác với một constructor để cause ở trạng thái *chưa khởi tạo*. `getCause() == null` tự nó không bảo đảm được phép gọi `initCause(...)`; phải xem constructor đã dùng.

### 3.3. Suppressed exception và `try-with-resources`

Giả sử `read()` ném `IOException("read failed")` rồi `close()` cũng ném `IOException("close failed")`. Với `try-with-resources`, thông thường:

```text
IOException: read failed      <-- ngoại lệ chính
  Suppressed: IOException: close failed
```

Đây là sơ đồ về cấu trúc lỗi, không phải stdout có số dòng xác định. Lỗi đóng tài nguyên nằm trong `getSuppressed()` của ngoại lệ chính; **không** phải là `getCause()` chỉ vì nó xảy ra sau. Nếu dùng `finally` thủ công và `close()` ném lỗi, hành vi có thể khác và lỗi cleanup có thể che lỗi nguồn.

### 3.4. Stack trace không phải một bản ghi bất biến vĩnh viễn

Constructor `Throwable` thông thường ghi nhận ngăn xếp khi đối tượng được tạo (theo các điều kiện API). Ném lại **cùng đối tượng** không bắt buộc tạo dấu vết mới. `fillInStackTrace()` có thể cập nhật dấu vết. Constructor `protected` với `writableStackTrace=false` cho phép tắt việc ghi stack, và `getStackTrace()` khi ấy rỗng.

Một ngoại lệ dùng chung giữa nhiều request có thể mang stack/cause/suppressed không phù hợp với từng sự cố. Khi điều tra hiệu năng hoặc lỗi đồng thời, cần lưu ý quyền sở hữu object, nhưng không hy sinh stack trace của lỗi bất ngờ chỉ vì muốn tiết kiệm cấp phát.

## 4. Cách đọc trang Javadoc của một API

Tìm đúng class hoặc interface, rồi định vị **đúng overload** của phương thức. Đối với mỗi phương thức, đọc theo trình tự:

1. **Module/package/class:** ví dụ `java.base` → `java.nio.file` → `Files`.
2. **Method signature:** tên, kiểu tham số, generic type, `static`/instance, kiểu trả về và `throws` có trong chữ ký.
3. **Mô tả chính:** điều kiện thành công, điều kiện biên, hành vi xử lý tài nguyên, thứ tự tác dụng phụ.
4. **Parameters / Returns / Throws:** điều kiện cụ thể ứng với mỗi ngoại lệ được tài liệu hóa.
5. **`Since`, `@Deprecated`, `See Also`, implementation notes:** dùng để xác định phiên bản hoặc giới hạn bảo đảm.
6. **Trang của loại ngoại lệ được liệt kê:** nếu cần hiểu `TimeoutException`, `ExecutionException` hay `CancellationException` thì đọc tiếp Javadoc của lớp đó.
7. **Liên kết tới JLS hoặc interface cha:** khi hợp đồng bị ràng buộc bởi ngôn ngữ hay một phương thức được override.

Đừng chỉ đọc một dòng `throws IOException` rồi ngừng. Ví dụ `Files.readString` còn có vấn đề về giải mã ký tự, dữ liệu lớn và việc đóng file. Phần `Throws` có thể ghi nhận cả unchecked exceptions đặc biệt được tài liệu hóa. **Không được kết luận “trang Throws không liệt kê `NullPointerException` thì nó tuyệt đối không thể xảy ra”.** Các unchecked exception do lỗi lập trình hoặc do đối tượng đầu vào vẫn có thể xuất hiện theo ngữ nghĩa chung.

### 4.1. Đúng overload và kiểu tham số

Một lớp có thể có nhiều phương thức cùng tên. `Future.get()` khác `Future.get(long timeout, TimeUnit unit)`: overload thứ hai có thể ném thêm `TimeoutException`. `Files.readString(Path)` và `Files.readString(Path, Charset)` có các tham số khác nhau, dù đều có thể ném `IOException`.

Cũng cần phân biệt `Thread.sleep(long)` với các overload khác và các phiên bản API mới hơn. Nếu copy nhầm link tới overload khác, có thể trả lời sai ngay cả khi cùng class.

### 4.2. `Throws` không tự nói cách xử lý

Nếu Javadoc nói `IOException` khi đọc file thất bại, điều đó **không có nghĩa** repository phải bắt và trả chuỗi rỗng. Chính sách xử lý thuộc tầng ứng dụng: truyền lỗi, thử lại khi an toàn, trả dữ liệu cache hay báo thất bại. API contract mô tả điều gì xảy ra; **nghiệp vụ quyết định phản ứng**.

### 4.3. Kiểm tra `Since` và phiên bản dự án

`CompletableFuture.failedFuture(...)` có từ Java 9. Các API hoặc overload khác có thể xuất hiện ở phiên bản mới hơn. Khi ứng dụng target Java 17, tra tài liệu Java 17 và kiểm thử với `javac --release 17` để phát hiện việc vô tình sử dụng chữ ký có ở JDK mới nhưng **không nằm trong API của bản mục tiêu**.

Javadoc không phải chính sách của mọi framework: một thư viện JDBC, Spring hoặc HTTP client có thể bọc/đổi ngoại lệ. Phải đọc **API thực sự được gọi**, gồm các lớp trung gian khi có, chứ không giả định hợp đồng của một class JDK áp dụng nguyên xi qua framework wrapper.

## 5. Case study: `Files.readString(Path)` và `Integer.parseInt(String)`

Đây là hai ví dụ hữu ích vì một phương thức có checked exception, còn phương thức kia thường báo lỗi đầu vào bằng unchecked exception.

### `Files.readString(Path)`

Javadoc Java 17 của `java.nio.file.Files.readString(Path)` nêu kiểu trả về `String` và `throws IOException`. Nó đọc nội dung tệp theo UTF-8 (ở overload một tham số), và mô tả các trường hợp lỗi I/O hoặc chuỗi byte không giải mã được. Khi gọi:

```java
static String readConfig(java.nio.file.Path path)
        throws java.io.IOException {
    return java.nio.file.Files.readString(path);
}
```

Đây là **phương thức minh họa**, đặt trong một lớp Java. Compiler buộc xử lý đúng `IOException` vì checked; caller có thể bắt ở tầng thích hợp. Nếu muốn cấu hình mặc định, quyết định fallback phải được hợp đồng ứng dụng cho phép.

Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html

### `Integer.parseInt(String)`

`Integer.parseInt` có thể ném `NumberFormatException` khi chuỗi không phải dạng số hợp lệ. Đây là subclass của `IllegalArgumentException`/`RuntimeException`, nên caller **không bị compiler buộc** khai báo `throws NumberFormatException`.

```java
static int parseQuantity(String input) {
    return Integer.parseInt(input);
}
```

Đây là phương thức minh họa, không bao gồm bước validation toàn bộ dữ liệu nghiệp vụ. Khi input đến từ người dùng, sai định dạng thường là tình huống dự kiến cần trả lỗi kiểm tra đầu vào. Nếu code nội bộ luôn truyền một literal hợp lệ mà bất ngờ sai, đó có thể là bug khác. **Tên class ngoại lệ không quyết định duy nhất chính sách phục hồi.**

Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html

## 6. Case study: `Thread.sleep` và `InterruptedException`

Javadoc Java 17 của `Thread.sleep(...)` khai báo `InterruptedException` khi luồng đang ngủ bị ngắt. Khi ngoại lệ được ném, interrupted status của luồng được xóa theo hợp đồng `sleep`.

Một phương thức có thể **truyền ngắt**:

```java
static void pause() throws InterruptedException {
    Thread.sleep(100);
}
```

Nếu phương thức không thể khai báo `InterruptedException`, ví dụ `Runnable.run()`, có thể cần **bắt, khôi phục cờ và kết thúc**:

```java
try {
    Thread.sleep(100);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là mảnh code minh họa bên trong một phương thức trả `void`. Nó **không** có nghĩa luôn phải nuốt hoặc luôn phải khôi phục mọi yêu cầu ngắt: hãy dựa vào hợp đồng thành phần đang thực thi. Điểm quan trọng là không biến tín hiệu ngắt thành thành công giả bằng cách tiếp tục một vòng lặp bất tận.

Đừng đồng nhất `InterruptedException` của **luồng chờ** với ngoại lệ do tác vụ bất đồng bộ ở thread khác ném. Việc đó đặc biệt quan trọng khi đọc `Future.get()`.

Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html

## 7. Case study: `Future.get` và `CompletableFuture.join`

Hai API có quan hệ gần nhau nhưng hợp đồng quan sát lỗi khác nhau.

| Lời gọi | Ngoại lệ cần chú ý | Ý nghĩa |
| --- | --- | --- |
| `Future.get()` | `InterruptedException` | Luồng đang chờ bị ngắt |
| `Future.get()` | `ExecutionException` | Tác vụ được đợi đã hoàn tất thất bại; dùng `getCause()` |
| `Future.get()` | `CancellationException` | Future bị hủy (unchecked) |
| `Future.get(timeout, unit)` | Thêm `TimeoutException` | **Lần chờ** hết hạn, không tự làm future lỗi |
| `CompletableFuture.join()` | `CompletionException` | Stage hoàn tất lỗi, thường bọc nguyên nhân |
| `CompletableFuture.join()` | `CancellationException` | Có thể ném trực tiếp nếu chính future bị hủy |
| `CompletableFuture.get()` | `InterruptedException`, `ExecutionException` | Hợp đồng tương thích `Future.get()` |
| `CompletableFuture.orTimeout(...)` | Future bị hoàn tất lỗi với `TimeoutException` nếu deadline thắng | Khác với timeout của riêng một lần `get(timeout, unit)` |
| `CompletableFuture.completeOnTimeout(v, ...)` | Future hoàn tất bình thường bằng `v` nếu deadline thắng | Có thể che sự khác biệt giữa fallback và kết quả thật |

`join()` không khai báo `InterruptedException` và `ExecutionException`, nhưng **không vì thế mà mọi lỗi trở thành giá trị trả về**. Nó báo thất bại thông qua đường unchecked. Nếu `CompletableFuture` đã chứa một `CompletionException`, `get()` có cách trình bày cause riêng; không suy đoán rằng mọi đường đi nhất thiết luôn có cùng số wrapper.

Javadoc:

- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html

**Mẹo tra cứu:** khi có một exception nhìn thấy ở controller, hãy xác định xem nó phát sinh **trong supplier**, trong **callback `thenApply`/`handle`**, hay ở **lời gọi chờ `get()`**. Hai vị trí lỗi khác nhau có thể dẫn đến lớp wrapper giống nhau. `getCause()` và stack trace giúp truy đúng nơi phát sinh.

## 8. Ví dụ Java 17+ độc lập: kiểm chứng các hợp đồng đã tra

Tạo tệp **`ApiExceptionContractDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public class ApiExceptionContractDemo {
    static String parseStatus(String text) {
        try {
            return "value=" + Integer.parseInt(text);
        } catch (NumberFormatException invalid) {
            return "invalid number";
        }
    }

    static void checkedReadFailure() throws IOException {
        throw new IOException("disk offline");
    }

    static void preciseRethrow() throws IOException {
        try {
            checkedReadFailure();
        } catch (Exception original) {
            throw original;
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("parseGood=" + parseStatus("25"));
        System.out.println("parseBad=" + parseStatus("abc"));

        try {
            preciseRethrow();
        } catch (IOException failure) {
            System.out.println("checked=" + failure.getMessage());
        }

        Thread.currentThread().interrupt();
        try {
            Thread.sleep(1000);
        } catch (InterruptedException interrupted) {
            System.out.println("sleepInterrupted="
                    + interrupted.getClass().getSimpleName());
            System.out.println("flagAfterSleepThrows="
                    + Thread.currentThread().isInterrupted());
            Thread.currentThread().interrupt();
            System.out.println("flagRestored="
                    + Thread.currentThread().isInterrupted());
        } finally {
            Thread.interrupted(); // Xóa cờ để ví dụ sau không bị ảnh hưởng.
        }

        CompletableFuture<String> failure =
                CompletableFuture.failedFuture(
                        new IOException("async disk offline"));

        try {
            failure.join();
        } catch (CompletionException wrapper) {
            System.out.println("joinWrapper="
                    + wrapper.getClass().getSimpleName());
            System.out.println("joinCause="
                    + wrapper.getCause().getClass().getSimpleName());
        }

        try {
            failure.get();
        } catch (ExecutionException wrapper) {
            System.out.println("getWrapper="
                    + wrapper.getClass().getSimpleName());
            System.out.println("getCause="
                    + wrapper.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ApiExceptionContractDemo.java
java ApiExceptionContractDemo
```

Đầu ra:

```text
parseGood=value=25
parseBad=invalid number
checked=disk offline
sleepInterrupted=InterruptedException
flagAfterSleepThrows=false
flagRestored=true
joinWrapper=CompletionException
joinCause=IOException
getWrapper=ExecutionException
getCause=IOException
```

Những điểm test này chứng minh:

- `Integer.parseInt` ném `NumberFormatException` cho `"abc"`; nhánh `catch` đã chủ động chuyển lỗi nhập liệu thành một chuỗi trạng thái.
- `checkedReadFailure()` ném checked `IOException`. `preciseRethrow()` dùng `catch (Exception original) { throw original; }` nhưng vẫn được compiler cho phép chữ ký `throws IOException` vì biến catch **effectively final** và phân tích chính xác các checked exception có thể thoát ra theo JLS §11.2.2. Nếu gán lại biến catch hoặc thêm các checked exception khác trong `try`, kết luận có thể thay đổi.
- `Thread.sleep` gặp trạng thái interrupted và ném `InterruptedException`; lúc bắt, cờ đã được xóa. Ví dụ khôi phục cờ có chủ đích, rồi xóa ở cuối **chỉ để cô lập chương trình trình diễn**; mã nghiệp vụ thật không nên xóa yêu cầu ngắt tùy tiện.
- Cùng một `CompletableFuture.failedFuture(IOException)`, `join()` báo qua `CompletionException`, còn `get()` báo qua `ExecutionException`; cả hai có `IOException` làm cause.

Kết quả đã chọn các đầu vào được kiểm soát, không phụ thuộc vào file thật hoặc cuộc đua thread, nên có thể kiểm thử chính xác stdout.

## 9. Ví dụ Java 17+ độc lập: `Throwable`, cause và lỗi cleanup

Tạo tệp **`ThrowableDocumentationDemo.java`**:

```java
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;

public class ThrowableDocumentationDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void read() throws IOException {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("read failed");
        }
    }

    public static void main(String[] args) {
        try {
            read();
        } catch (IOException original) {
            IllegalStateException wrapper =
                    new IllegalStateException("import failed", original);

            System.out.println("outer=" + wrapper.getMessage());
            System.out.println("causeType="
                    + wrapper.getCause().getClass().getSimpleName());
            System.out.println("causeMessage="
                    + wrapper.getCause().getMessage());
            System.out.println("suppressedCount="
                    + original.getSuppressed().length);
            System.out.println("suppressedMessage="
                    + original.getSuppressed()[0].getMessage());

            StringWriter output = new StringWriter();
            wrapper.printStackTrace(new PrintWriter(output));
            String trace = output.toString();
            System.out.println("containsCause="
                    + trace.contains("Caused by: java.io.IOException: read failed"));
            System.out.println("containsSuppressed="
                    + trace.contains(
                            "Suppressed: java.io.IOException: close failed"));
        }

        Exception legacy = new Exception("legacy");
        legacy.initCause(new IOException("first cause"));
        boolean secondRejected = false;

        try {
            legacy.initCause(new IOException("second cause"));
        } catch (IllegalStateException expected) {
            secondRejected = true;
        }

        System.out.println("initCauseOnce=" + secondRejected);
        System.out.println("causeStill="
                + legacy.getCause().getMessage());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ThrowableDocumentationDemo.java
java ThrowableDocumentationDemo
```

Đầu ra:

```text
outer=import failed
causeType=IOException
causeMessage=read failed
suppressedCount=1
suppressedMessage=close failed
containsCause=true
containsSuppressed=true
initCauseOnce=true
causeStill=first cause
```

**Phân tích:**

1. `read()` ném `IOException("read failed")` từ thân `try`.
2. `FailingResource.close()` cũng ném `IOException("close failed")`.
3. Theo hợp đồng `try-with-resources`, ngoại lệ đọc là chính và lỗi đóng được ghi trong suppressed của nó.
4. Wrapper `IllegalStateException("import failed", original)` **giữ cả đối tượng gốc**, nhờ vậy người đọc vẫn truy được lỗi chính và lỗi phụ.
5. `printStackTrace` có thể trình bày `Caused by:` và `Suppressed:`; ví dụ dùng phép kiểm tra chuỗi ổn định thay vì in số dòng cụ thể của stack.
6. `initCause` thành công lần đầu trên một `Exception` được tạo bằng constructor chỉ có message; lần thứ hai bị từ chối và cause đã gán không đổi.

Một constructor khác đã khởi tạo cause (kể cả `null`) có thể không cho dùng `initCause` nữa. Khi tự thiết kế lớp exception, hãy ưu tiên constructor có `cause` hơn là tạo đối tượng rồi cố đặt cause ở một chỗ khác.

## 10. Hiểu cách JLS và Javadoc bổ sung cho nhau

Xét cùng một đoạn mã:

```java
static String read(Path path) throws IOException {
    return Files.readString(path);
}
```

Đây là đoạn minh họa cần import `Path`, `Files`, `IOException`. Cần phân biệt ba nhận định:

- **Javadoc `Files.readString`:** mô tả thao tác đọc và ngoại lệ có thể phát sinh theo hợp đồng API.
- **JLS §11.2:** giải thích tại sao checked `IOException` phải được xử lý hoặc cho phép thoát ra bằng mệnh đề `throws` của phương thức.
- **`Throwable` Javadoc:** giải thích cách kiểm tra cause, message, stack và suppressed nếu người gọi bắt hoặc bọc lỗi.

Chỉ đọc JLS không cho biết chi tiết UTF-8 của `Files.readString`. Chỉ đọc Javadoc `Files` không giải thích đầy đủ tại sao compiler từ chối một phương thức thiếu `throws`. Chỉ đọc `Throwable` không cho biết phương thức nào tạo lỗi.

### Quy trình 7 bước khi gặp ngoại lệ chưa biết

1. **Xác định API và phiên bản đang chạy/build.** Ghi package, class, method, overload, kiểu tham số và Java release.
2. **Đọc chữ ký Javadoc.** Chú ý checked exceptions xuất hiện trong `throws`, interface gốc và biến thể overload.
3. **Đọc phần `Throws` và mô tả phương thức.** Ghi chính xác điều kiện gây lỗi và có thay đổi trạng thái/tài nguyên trước khi ném không.
4. **Đối chiếu JLS khi câu hỏi liên quan đến compiler hoặc điều khiển luồng.** Chọn §11.2 cho checked exceptions, §14.18 cho `throw`, §14.20 cho `catch`/`finally`/resources.
5. **Đọc `Throwable` nếu có wrapper/cause/suppressed.** Xác định nguyên nhân ở đâu, ngoại lệ phụ có bị mất hay không.
6. **Chạy một chương trình tối thiểu có đầu vào xác định.** Biên dịch bằng `javac --release` đúng bản mục tiêu. Đừng dùng một lần chạy thành công để khẳng định mọi trường hợp không thể lỗi.
7. **Ghi rõ kết luận và giới hạn.** Tách “JLS bảo đảm”, “Javadoc API bảo đảm”, “chỉ là hành vi quan sát ở JVM cụ thể” và “quyết định nghiệp vụ của ứng dụng”.

## 11. Đọc stack trace và cause để lần ngược hợp đồng bị vi phạm

Nếu log có dạng:

```text
java.util.concurrent.CompletionException: java.io.IOException: disk offline
    at ...
Caused by: java.io.IOException: disk offline
    at ...
```

Đây là **minh họa**, không phải stdout hoàn chỉnh. Cần phân biệt:

- `CompletionException`: lớp bọc giúp mô tả thất bại của một stage bất đồng bộ.
- `IOException`: loại ngoại lệ nguyên nhân, có thể do thao tác I/O ở bên trong.
- Các khung stack: vị trí tạo/điền stack của exception và đường đi; không nhất thiết chứa toàn bộ lịch sử request qua nhiều thread.
- `getCause()`: liên kết cause để truy lỗi bên dưới; không phải luôn chỉ có một tầng.
- `getSuppressed()`: lỗi phụ, không đồng nghĩa cause.

Một logger nhận cả `Throwable` thường giúp giữ các thông tin đó hơn là chỉ ghi `getMessage()`. Nhưng formatter/backend có thể được cấu hình lược bớt stack, nên phải kiểm tra hệ thống ghi log thực tế.

Để phân loại ở tầng xử lý lỗi, có thể gỡ các wrapper kỹ thuật đã biết như `CompletionException` và `ExecutionException`, nhưng không nên tự động bỏ mọi wrapper: ngoại lệ nghiệp vụ có thể mang thông tin quan trọng về thao tác đã thất bại. Khi log, giữ đủ chuỗi để chẩn đoán.

## 12. Phân biệt hợp đồng API và chi tiết triển khai

Javadoc đôi khi có đoạn **implementation note** hoặc mô tả riêng cho một triển khai. Hãy hiểu đúng cấp bảo đảm:

- **Đặc tả JLS** là quy tắc của ngôn ngữ; code Java hợp lệ phải tuân thủ các yêu cầu ấy.
- **Hợp đồng API Javadoc** mô tả hành vi được cam kết cho class/method, bao gồm các điều kiện `Throws` đã nêu.
- **Implementation note** có thể giải thích chiến lược trong bản triển khai, không nhất thiết là bảo đảm của mọi implementation cùng interface.
- **Quan sát runtime** như số khung stack hoặc thứ tự callback giữa các thread không tự trở thành bảo đảm ngôn ngữ.

Ví dụ, `CompletableFuture.cancel(boolean)` có ghi chú về đối số `mayInterruptIfRunning` đối với triển khai `CompletableFuture`: nó không được dùng để ngắt computation theo cách `FutureTask` có thể làm. Vì thế không suy ra từ tên `cancel(true)` rằng supplier luôn bị interrupt.

Ví dụ khác: `AutoCloseable.close()` có chữ ký cho phép `throws Exception`, nhưng lớp con như `Closeable` thu hẹp checked exception. Không thể chỉ nhìn interface rộng rồi kết luận mọi `close()` cụ thể đều khai báo `throws Exception`.

Đối với phương thức API của bên thứ ba, hãy kiểm tra phiên bản dependency. Một thay đổi thư viện có thể làm khác loại wrapper hoặc thời điểm ném lỗi mà không thay đổi các quy tắc JLS.

## 13. Một số bẫy khi tra cứu ngoại lệ

| Bẫy | Vì sao dễ sai | Cách kiểm tra |
| --- | --- | --- |
| Dùng Javadoc Java mới cho dự án Java 17 | API/overload có thể chưa tồn tại trong Java 17 | Chọn đúng trang `/java/javase/17/` và thử `javac --release 17` |
| Chỉ nhìn tên phương thức | Không biết overload đang gọi | So khớp đủ tên, tham số và kiểu trả về |
| Tưởng danh sách `Throws` liệt kê mọi lỗi runtime có thể xảy ra | Unchecked exceptions do code hoặc trạng thái có thể không được liệt kê hết | Kết hợp JLS, ngữ nghĩa phương thức và đầu vào thực |
| Tưởng `throws` là câu lệnh xử lý lỗi | Nó chỉ là khai báo | Xem §8.4.6 và §11.2 |
| Tưởng checked exception chắc chắn phục hồi được | Cơ chế compiler khác chính sách nghiệp vụ | Đọc điều kiện lỗi và thiết kế ranh giới xử lý |
| Tưởng unchecked không cần quan tâm | Có thể là bug hoặc input dự kiến | Xem hợp đồng và xử lý đúng |
| Tưởng mọi `Exception` đều thuộc nhóm checked | `RuntimeException` là unchecked | Xem phân loại JLS §11.1 |
| Tưởng `getMessage()` là cause | Message chỉ là chuỗi | Dùng `getCause()` và `printStackTrace()` |
| Tưởng `finally` luôn giữ lỗi cũ | Return/throw trong finally có thể che lỗi | Đọc JLS §14.20, test cả lỗi kép |
| Tưởng `getSuppressed()` chứa mọi cause | Suppressed và cause có nghĩa khác nhau | Đọc `Throwable`, thử `try-with-resources` |
| Tưởng `Future.get(timeout)` timeout nghĩa là công việc bị hủy | Lời gọi chờ hết hạn không tự hủy future | Đọc đúng overload và chính sách cancel |
| Tưởng `join()` với `get()` cùng loại exception | Một bên unchecked, một bên có `ExecutionException` checked | Đọc cả `Future` và `CompletableFuture` |
| Copy code chạy trên JDK mới rồi coi là hợp lệ với Java 17 | Dễ dùng API chưa có ở release mục tiêu | Biên dịch với `--release 17` |
| Chỉ dựa vào một câu trả lời trên mạng | Có thể thiếu phiên bản hoặc điều kiện biên | Đối chiếu nguồn chuẩn và thử nghiệm tối thiểu |

## 14. Bài tập tra cứu và tự kiểm tra

**Câu 1.** Muốn biết `catch(IOException e)` có bắt `FileNotFoundException` không, tra đâu?  
**Trả lời:** JLS về kiểu ngoại lệ và chọn handler; `FileNotFoundException` là subclass của `IOException`, nên handler `IOException` có thể bắt nó nếu exception đi tới đây.

**Câu 2.** Muốn biết `Thread.sleep` có xóa interrupted status khi ném `InterruptedException` không, tra đâu?  
**Trả lời:** Javadoc của `Thread.sleep` đúng overload/phiên bản. Không kết luận chỉ từ tên lớp `InterruptedException`.

**Câu 3.** `throw new IOException(...)` không biên dịch trong một phương thức `void run()` không có catch/throws. Tra đâu?  
**Trả lời:** JLS §11.2 (kiểm tra checked exceptions), §14.18 (`throw`) và §8.4.6 (`throws`).

**Câu 4.** `new RuntimeException("failed")` có tự có cause không?  
**Trả lời:** Không có đối tượng cause được gắn chỉ vì có message. Muốn giữ ngoại lệ gốc, sử dụng constructor nhận `Throwable` khi phù hợp.

**Câu 5.** Trong `try-with-resources`, thân `try` và `close()` cùng lỗi. Tra đâu?  
**Trả lời:** JLS §14.20.3 về tài nguyên và `Throwable` Javadoc về `getSuppressed()`.

**Câu 6.** Có thể gọi `initCause` hai lần để thay nguyên nhân không?  
**Trả lời:** Không. Phải đọc hợp đồng `Throwable.initCause` và ưu tiên tạo wrapper với cause từ đầu.

**Câu 7.** `CompletableFuture.join()` có buộc caller `catch (ExecutionException)` không?  
**Trả lời:** Không. `join` có đường lỗi unchecked như `CompletionException`, khác `get()`.

**Câu 8.** Gọi `future.get(100, MILLISECONDS)` bị timeout, nhưng công việc vẫn chạy. Có mâu thuẫn với Javadoc không?  
**Trả lời:** Không. Timeout ở đây giới hạn một lần chờ; không tự chứng minh future đã bị hủy.

**Câu 9.** Trong Javadoc chỉ thấy `throws IOException`, có thể khẳng định chắc chắn không bao giờ có `NullPointerException` không?  
**Trả lời:** Không. Danh sách ngoại lệ được tài liệu hóa không phải chứng minh không có mọi unchecked exception trong mọi tình huống.

**Câu 10.** `throws IOException` có tự rollback mọi thay đổi trước lỗi không?  
**Trả lời:** Không. JLS xử lý việc lan truyền exception; rollback hay bù trừ thuộc hợp đồng transaction/nghiệp vụ.

**Câu 11.** Một `Error` có bị bắt bởi `catch (Exception e)` không?  
**Trả lời:** Không theo quan hệ kế thừa thông thường: `Error` và `Exception` là hai nhánh riêng dưới `Throwable`. Tránh bắt `Throwable` rộng để làm ứng dụng “không bao giờ lỗi”.

**Câu 12.** Nếu API kế thừa phương thức từ interface khác, tài liệu nào đáng xem?  
**Trả lời:** Javadoc class triển khai, Javadoc interface gốc và quy tắc override/checked exceptions của JLS. Cần phân biệt hợp đồng chung và hành vi riêng.

## 15. Checklist cho code review và điều tra production

Khi gặp một exception khó hiểu trong pull request hoặc production:

1. Ghi lại **JDK target** và JDK đang chạy; không tra cứu mơ hồ “Java hiện tại”.
2. Xác định method signature và **đúng overload** được gọi.
3. Phân loại checked/unchecked bằng quy tắc JLS, không đoán từ tên.
4. Đọc phần `Throws` và điều kiện cụ thể trong Javadoc.
5. Phân biệt lỗi **phát sinh trong tác vụ** với lỗi **khi quan sát/chờ kết quả**.
6. Đọc `getCause()` và `getSuppressed()` nếu có wrapper hoặc lỗi đóng tài nguyên.
7. Kiểm tra `finally` và `try-with-resources` có bảo toàn lỗi chính không.
8. Kiểm tra trạng thái tài nguyên/dữ liệu sau thất bại; `throws` không tự rollback.
9. Nếu dùng wrapper mới, giữ nguyên nhân bằng constructor có cause.
10. Dùng `javac --release` và một ví dụ xác định để kiểm chứng đúng API của phiên bản mục tiêu.
11. Tách rõ kết luận **được đặc tả** khỏi nhận xét “đã thấy chạy như vậy”.
12. Trích đúng đường dẫn tài liệu JLS/Javadoc trong ghi chú kỹ thuật, tránh dùng bản API khác với bản phát hành.

## 16. Danh mục tài liệu chuẩn để mở lại

| Chủ đề | Tài liệu chính thức |
| --- | --- |
| JLS: exception kinds, checked exceptions, handlers | https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html |
| JLS: method `throws` | https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.6 |
| JLS: `throw` statement | https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.18 |
| JLS: `try`, `catch`, `finally`, `try-with-resources` | https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20 |
| `Throwable` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html |
| `AutoCloseable` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html |
| `Files` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html |
| `Integer` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html |
| `Thread` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html |
| `Future` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html |
| `CompletableFuture` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html |
| `CompletionException` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html |
| `ExecutionException` | https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html |

**Kết luận:** JLS trả lời **ngôn ngữ Java xử lý ngoại lệ theo quy tắc nào**. `Throwable` Javadoc trả lời **một đối tượng lỗi lưu và trình bày dữ liệu chẩn đoán ra sao**. Javadoc của **chính phương thức API** trả lời **khi nào phương thức có thể thất bại và điều gì được cam kết**. Dùng cả ba nguồn, chọn đúng phiên bản và kiểm chứng bằng test Java tối thiểu là cách đáng tin để xử lý một câu hỏi về ngoại lệ.