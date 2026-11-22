# Bảng phân biệt cause, suppressed và stack trace trong Java

> **Chủ đề:** Java Core → Exception → Tra cứu. Tài liệu này là bảng tham chiếu thực hành về ba loại thông tin của `Throwable`: **cause** (lỗi nguyên nhân), **suppressed exceptions** (ngoại lệ phụ được đính kèm) và **stack trace** (dấu vết lời gọi). Nội dung dùng ngữ nghĩa Java 17+, ví dụ `try-with-resources` chạy độc lập, cách đọc log, xử lý wrapper và những nhầm lẫn dễ gây mất dữ liệu chẩn đoán.

## 1. Bảng phân biệt nhanh

| Tiêu chí | Cause | Suppressed exceptions | Stack trace |
|---|---|---|---|
| Câu hỏi trả lời | **Lỗi nào dẫn tới ngoại lệ hiện tại?** | **Những lỗi phụ nào được giữ trong khi xử lý lỗi chính?** | **Throwable này có dấu vết frame gọi như thế nào?** |
| Kiểu dữ liệu | Một tham chiếu `Throwable` hoặc `null` | Mảng `Throwable[]`, có thể rỗng | Mảng `StackTraceElement[]`, có thể rỗng |
| API đọc | `getCause()` | `getSuppressed()` | `getStackTrace()` |
| API ghi/phát sinh | Constructor nhận `cause` hoặc `initCause()` | `addSuppressed(Throwable)`; được Java tự thêm trong `try-with-resources` khi phù hợp | `fillInStackTrace()`, `setStackTrace(...)`; thường chụp ở lúc khởi tạo Throwable |
| Quan hệ với lỗi hiện tại | Mối quan hệ *nguyên nhân/chuyển tầng* | Lỗi đi kèm, **không tự trở thành nguyên nhân chính** | Thông tin về các frame thực thi, **không phải Throwable khác** |
| Số lượng trực tiếp | Tối đa một cause trực tiếp; cause có thể có cause tiếp | Có thể nhiều suppressed trực tiếp | Có thể nhiều frame trong một trace |
| Có tự động lan qua wrapper? | Khi wrapper được tạo với cause | **Không tự chuyển** suppressed của cause sang wrapper | Wrapper và cause thường có stack trace **riêng** |
| Khi dùng | Bọc lỗi kỹ thuật thành lỗi domain; `ExecutionException` chứa lỗi task | Lỗi khi đóng resource, cleanup, compensation phụ | Điều tra vị trí tạo/ném, đường đi mã, các tầng gọi |
| Kiểm tra trong test | `assertSame(expected, ex.getCause())` hoặc kiểm tra type | `ex.getSuppressed().length`, type/message của phần tử | Top method/class khi ổn định; thường **không** cố định line number |
| Có nên xóa cho log gọn? | Không: có thể mất nguyên nhân gốc | Không: có thể mất lỗi cleanup quan trọng | Không tùy tiện: có thể mất vị trí và đường gọi của lỗi |
| Có thể không có? | Có, nếu không khai báo hoặc không gắn cause | Có: mảng rỗng là bình thường | Có: stack có thể bị tắt hoặc rỗng vì triển khai/điều kiện |
| Dạng hiển thị phổ biến trong `printStackTrace()` | Dòng `Caused by: ...` | Dòng `Suppressed: ...` | Các dòng bắt đầu bằng `at ...` |

**Ghi nhớ:** *cause* và *suppressed* đều tham chiếu tới **Throwable**, còn *stack trace* chứa các **StackTraceElement**. Một đối tượng Throwable có thể đồng thời có một cause, nhiều suppressed và stack trace của chính nó; các Throwable ở cause/suppressed cũng có metadata riêng.

## 2. Mô hình quan hệ trên một Throwable

~~~text
IllegalStateException("order processing failed")  <-- outer Throwable
  |
  +-- cause --> IOException("read failed")
  |               |
  |               +-- suppressed[0] --> IOException("close failed")
  |               |                      +-- stack trace riêng
  |               +-- stack trace riêng
  |
  +-- suppressed[] = rỗng
  +-- stack trace = frames khi tạo outer Throwable
~~~

Sơ đồ thể hiện **hai dạng liên kết lỗi độc lập** và một dấu vết riêng cho từng Throwable:

1. Service bắt `IOException("read failed")` rồi bọc thành `IllegalStateException("order processing failed", cause)`.
2. Trong `try-with-resources`, lỗi `close()` được thêm vào **IOException do thân try ném**, dưới dạng suppressed.
3. Wrapper ở service có cause là IOException. `wrapper.getSuppressed()` vẫn có thể rỗng; muốn xem lỗi đóng tài nguyên phải đi tới `wrapper.getCause().getSuppressed()`.
4. Wrapper, cause và suppressed Throwable đều có thể có stack trace riêng, được chụp tại những vị trí khác nhau.

Không coi hệ thống này là một cây ngữ nghĩa tuyệt đối của nghiệp vụ. Nó là đồ thị tham chiếu Throwable; ứng dụng có thể tạo quan hệ không chuẩn, chain dài, hoặc wrapper dùng lại. Khi duyệt thủ công, tránh giả định mọi throwable đều chỉ có một chuỗi cause đơn giản.

## 3. Cause: nguyên nhân được giữ khi chuyển abstraction

Một cause là Throwable mà exception hiện tại xem như **lỗi nguyên nhân**. API đọc:

~~~java
Throwable cause = exception.getCause();
~~~

Nếu không có cause, giá trị thường là `null`. Một constructor có cause:

~~~java
// Trích đoạn trong một phương thức.
java.io.IOException original =
        new java.io.IOException("database response unavailable");

IllegalStateException wrapper =
        new IllegalStateException("cannot load order", original);

System.out.println(wrapper.getCause() == original); // true
~~~

Ở ví dụ này `IllegalStateException` là lỗi tại abstraction bên ngoài; `IOException` là nguyên nhân kỹ thuật. Việc bọc không làm IOException trở thành suppressed. Cause và suppressed là **hai quan hệ khác nhau**.

### Khi nào dùng cause?

- Repository chuyển lỗi driver/I/O sang exception lưu trữ.
- Service chuyển lỗi lưu trữ sang exception domain mà caller có thể hiểu.
- Executor lưu lỗi thực thi trong `ExecutionException` mà thread gọi `Future.get()` nhận được.
- CompletableFuture báo exceptional completion qua `CompletionException` khi gọi `join()`.
- Một phép xử lý cần bổ sung ngữ cảnh, nhưng vẫn cho người điều tra xem nguyên nhân gốc.

Constructor đúng khi bọc lỗi:

~~~java
catch (java.io.IOException ex) {
    throw new IllegalStateException("could not load profile", ex);
}
~~~

Không nên:

~~~java
catch (java.io.IOException ex) {
    throw new IllegalStateException(ex.getMessage());
}
~~~

Cách thứ hai **không giữ cause**; caller có thể mất stack của IOException và thông tin nguyên nhân. Nếu chỉ muốn truyền lỗi đúng hợp đồng, dùng `throw ex;` khi có thể — không phải cứ có catch là phải tạo wrapper.

### getCause() và initCause()

`Throwable.initCause(Throwable)` có thể đặt cause **một lần** nếu Throwable chưa được khởi tạo cause theo thiết kế constructor. Nó trả về chính Throwable nhận lời gọi. Thử thay cause đã khởi tạo sẽ gây `IllegalStateException`; đặt Throwable làm cause của chính nó là không hợp lệ.

~~~java
// Hợp lệ trong một phương thức.
Exception outer = new Exception("outer");
IOException cause = new IOException("inner");
outer.initCause(cause);
~~~

Đoạn này cần import `java.io.IOException` nếu dùng tên ngắn. **Ưu tiên constructor nhận cause** khi thư viện cung cấp, vì ngắn, rõ và giữ trạng thái đúng ngay từ đầu. Đừng dựa vào `initCause()` để thay đổi một error chain đã được công bố cho các thread khác.

Một số Throwable có constructor đã khởi tạo cause (kể cả khi giá trị là `null`), nên không thể gọi `initCause` nữa; hãy đọc Javadoc của constructor đang dùng.

## 4. Suppressed exceptions: giữ lỗi phụ mà không che lỗi chính

`Throwable.addSuppressed(Throwable)` gắn thêm một ngoại lệ phụ vào Throwable hiện tại. `getSuppressed()` trả một mảng của các Throwable đã được gắn, hoặc mảng rỗng nếu không có. Đừng hiểu suppressed là lỗi không quan trọng: lỗi khi đóng file, hoàn tất transaction hoặc dọn resource có thể giúp xác định vì sao trạng thái cuối không như kỳ vọng.

Ví dụ thao tác thủ công:

~~~java
// Trích đoạn trong một phương thức.
IllegalStateException primary =
        new IllegalStateException("primary failure");

primary.addSuppressed(new IOException("cleanup also failed"));

System.out.println(primary.getSuppressed().length); // 1
~~~

Đoạn này cần import `java.io.IOException`. `addSuppressed(null)` ném `NullPointerException`; thêm chính Throwable đó làm suppressed của nó ném `IllegalArgumentException`. `getSuppressed()` trả một mảng để đọc; sửa phần tử mảng trả về không phải cách cập nhật danh sách suppressed nội bộ.

### Suppressed có giống cause không?

Không:

- `cause` thể hiện quan hệ “ngoại lệ A do B gây ra” hoặc “A bọc B”.
- `suppressed` giúp giữ “ngoài A, còn có lỗi C phát sinh trong xử lý/cleanup”.
- `getCause()` không trả suppressed; `getSuppressed()` không trả cause.
- `printStackTrace()` có thể hiển thị cả hai theo cấu trúc của Throwable.

Không nên biến mọi lỗi phụ thành cause hoặc ngược lại chỉ để ghi log trông ngắn hơn. Cần giữ **lỗi nào quyết định kết quả thất bại chính** và **lỗi nào đi kèm**.

## 5. Try-with-resources: nơi suppressed xuất hiện thường gặp nhất

`try-with-resources` tự gọi `close()` cho resource ở cuối scope. Giả sử thân `try` đã ném ngoại lệ A, và `close()` cũng ném ngoại lệ B. Java giữ A làm **exception chính**, đồng thời gắn B vào `A.getSuppressed()`.

~~~java
try (SomeResource resource = openResource()) {
    throw new IOException("body failed");
    // Khi rời scope, close() vẫn được gọi.
}
~~~

Đây là đoạn minh họa, cần định nghĩa `SomeResource` và `openResource()`. Nếu `close()` ném IOException thứ hai, exception đó thường nằm trong suppressed của lỗi ở thân `try`.

Các trường hợp quan trọng:

| Thân try | close() | Kết quả |
|---|---|---|
| Thành công | Thành công | Không có lỗi từ hai nguồn này |
| Thất bại A | Thành công | Ném A |
| Thành công | Thất bại B | Ném B làm lỗi chính |
| Thất bại A | Thất bại B | Ném A; B được suppress vào A |
| Nhiều resource, body thất bại | Nhiều close thất bại | Các close failure có thể được gắn suppressed lên lỗi chính |
| Không có lỗi ở body, nhiều close thất bại | Close lỗi ở một hoặc nhiều resource | Lỗi của lần close thất bại đầu tiên khi đóng theo thứ tự ngược được ném chính; các lỗi close sau có thể bị suppress |

Java đóng resource theo **thứ tự ngược với thứ tự khai báo**. Nếu mở `A` rồi `B`, Java gọi `B.close()` trước `A.close()`. Đừng suy đoán suppressed exception nào thuộc resource nào chỉ từ vị trí mảng nếu bạn chưa xác định thứ tự đóng và các điểm ném.

### So với finally tự viết

Mã thủ công sau có thể làm lỗi close **che** lỗi ban đầu:

~~~java
// Phản ví dụ. closeResource() có thể ném.
try {
    readData();             // Ném lỗi chính.
} finally {
    closeResource();        // Nếu cũng ném, có thể thay lỗi đang lan truyền.
}
~~~

`try-with-resources` tự xử lý suppression để bảo toàn lỗi thân `try` khi cả hai đường đều thất bại. Với cleanup thủ công, nếu cần bảo tồn nhiều lỗi, phải thiết kế cơ chế kết hợp/`addSuppressed` phù hợp; không chỉ gọi `close` trong `finally` rồi mặc định tất cả nguyên nhân đều được giữ.

## 6. Stack trace: dấu vết thực thi gắn với Throwable

`Throwable.getStackTrace()` trả mảng `StackTraceElement[]`. Một phần tử cung cấp thông tin như tên lớp, phương thức, tệp nguồn, số dòng (nếu có) hoặc metadata khác của frame.

~~~java
// Trích đoạn trong phương thức; exception đã được tạo.
StackTraceElement[] frames = exception.getStackTrace();
if (frames.length > 0) {
    System.out.println(frames[0].getClassName());
    System.out.println(frames[0].getMethodName());
}
~~~

Stack trace thường được ghi nhận **khi đối tượng Throwable được khởi tạo** qua `fillInStackTrace()`, không phải lúc bất kỳ caller nào nhìn thấy exception. Điều này rất quan trọng khi:

- Tạo exception trước rồi `throw` sau: stack có thể chỉ nơi tạo.
- Bắt rồi `throw ex;`: ném lại cùng object thường **không tự chụp stack mới**.
- Bắt rồi `throw new WrapperException(..., ex);`: wrapper có trace tại nơi tạo wrapper; cause giữ trace riêng ở nơi tạo cause.
- Exception đi từ worker qua `Future.get()`: wrapper ở thread chờ và lỗi task có thể có **trace ở hai thread khác nhau**.
- JVM/Throwable có thể tối ưu hoặc vô hiệu hóa stack trace; mảng có thể rỗng, nên không giả định `frames[0]` luôn tồn tại.

`getStackTrace()` không trả danh sách lỗi khác. Một frame không phải cause và không phải suppressed Throwable; frame mô tả một điểm trong chuỗi lời gọi.

### printStackTrace là bản in có cấu trúc rộng hơn

`Throwable.printStackTrace()` có thể in ra:

~~~text
java.lang.IllegalStateException: operation failed
    at Example.execute(Example.java:...)
Caused by: java.io.IOException: read failed
    at Example.read(Example.java:...)
    Suppressed: java.io.IOException: close failed
        at Example$Resource.close(Example.java:...)
~~~

Đây là **sơ đồ định dạng tham khảo**, không phải output chính xác của code ở phần 7. Trong thực tế, vị trí và thụt lề có thể khác; các frame chung có thể được rút gọn thành `... N more`. Đừng xây parser nghiệp vụ dựa trên text của `printStackTrace()`.

Dùng `logger.error("operation failed", ex)` hoặc API logger tương đương có hỗ trợ Throwable trong production, thay vì chỉ `logger.error(ex.getMessage())` làm mất cause/suppressed/frames.

## 7. Chương trình Java 17 độc lập minh họa cả ba

Chương trình này cố tình tạo lỗi trong thân `try` và lỗi lúc `close`, sau đó bọc lỗi lên tầng ứng dụng. Các assertion quan trọng dựa vào **kiểu, message, số lượng và tên phương thức đầu stack**, không phụ thuộc số dòng.

Lưu tên **`ThrowableRelationsDemo.java`**:

~~~java
import java.io.IOException;

public class ThrowableRelationsDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static void read() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("read failed");
        }
    }

    static void execute() {
        try {
            read();
        } catch (IOException cause) {
            throw new IllegalStateException("operation failed", cause);
        }
    }

    public static void main(String[] args) {
        try {
            execute();
        } catch (IllegalStateException outer) {
            Throwable cause = outer.getCause();
            Throwable[] suppressed = cause.getSuppressed();

            System.out.println("outer: " + outer.getMessage());
            System.out.println("cause: "
                    + cause.getClass().getSimpleName()
                    + ": " + cause.getMessage());
            System.out.println("outer suppressed: "
                    + outer.getSuppressed().length);
            System.out.println("cause suppressed: " + suppressed.length);
            System.out.println("suppressed[0]: "
                    + suppressed[0].getClass().getSimpleName()
                    + ": " + suppressed[0].getMessage());

            System.out.println("outer top method: "
                    + outer.getStackTrace()[0].getMethodName());
            System.out.println("cause top method: "
                    + cause.getStackTrace()[0].getMethodName());
            System.out.println("suppressed top method: "
                    + suppressed[0].getStackTrace()[0].getMethodName());
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac ThrowableRelationsDemo.java
java ThrowableRelationsDemo
~~~

**Stdout chính xác của ví dụ khi chạy trên JDK thông thường với stack trace được bật:**

~~~text
outer: operation failed
cause: IOException: read failed
outer suppressed: 0
cause suppressed: 1
suppressed[0]: IOException: close failed
outer top method: execute
cause top method: read
suppressed top method: close
~~~

### Đọc kết quả

1. `Resource.close()` ném `IOException("close failed")`.
2. `read()` ném `IOException("read failed")` **trước** khi close, do đó lỗi body là lỗi chính; Java tự đính lỗi close vào mảng suppressed của **lỗi read**.
3. `execute()` bắt IOException và tạo `IllegalStateException("operation failed", cause)`. Wrapper có cause là IOException, nhưng **không tự nhận suppressed của cause**. Vì vậy outer suppressed = 0, cause suppressed = 1.
4. Trace của outer bắt đầu tại `execute`, của IOException lỗi body tại `read`, và của IOException lỗi close tại `close`. Đây là ba đối tượng Throwable và ba stack trace có vị trí phát sinh khác nhau.
5. Không cần in `printStackTrace()` để xác minh quan hệ. Nếu in, stack sẽ có đường `Caused by` và `Suppressed` cùng file/line, phần đó phụ thuộc bố trí source.
6. Ví dụ không dùng thread, network, đồng hồ hay hệ thống file; dữ liệu và thứ tự ổn định. Trong các runtime tùy biến có stack trace bị vô hiệu hóa, assertion trực tiếp vào `[0]` cần được điều chỉnh.

## 8. Một bảng tra cứu API Throwable quan trọng

| API | Đọc/ghi | Kết quả hoặc lưu ý |
|---|---|---|
| `getCause()` | Đọc | Trả cause trực tiếp hoặc `null` |
| `initCause(cause)` | Ghi một lần khi được phép | Đặt cause; không thay thế tùy tiện cause đã khởi tạo |
| `getSuppressed()` | Đọc | Trả mảng suppressed; mảng rỗng nếu không có |
| `addSuppressed(error)` | Ghi | Gắn Throwable phụ; cấm `null` và tự suppress |
| `getStackTrace()` | Đọc | Trả bản sao mảng các frame; có thể rỗng |
| `setStackTrace(frames)` | Ghi | Thay stack trace được trình bày khi writable; dùng thận trọng |
| `fillInStackTrace()` | Ghi | Làm mới trace theo stack hiện tại nếu writable; có thể thay bằng chứng gốc |
| `printStackTrace()` | Hiển thị | In trace của exception cùng cause/suppressed theo format chẩn đoán |
| `getMessage()` | Đọc | Message cho con người; không là error code có hợp đồng mặc định |
| `getLocalizedMessage()` | Đọc | Có thể được bản địa hóa; không làm dữ liệu máy đọc |
| `toString()` | Đọc | Thường kết hợp tên lớp và message; không thay thế full stack trace |

### Có thể chỉnh stack trace không?

`setStackTrace(StackTraceElement[])` cho phép thay thế dấu vết được trình bày trong những Throwable hỗ trợ writable stack trace. `fillInStackTrace()` chụp lại tình huống hiện tại. Cả hai hiếm khi là cách đúng để “sửa” lỗi nghiệp vụ: nếu thao tác mù quáng, bạn có thể xóa vị trí tạo lỗi ban đầu, gây khó điều tra.

`getStackTrace()` trả một mảng không nên được xem là state mutable chung. Thay một phần tử của mảng vừa nhận không phải cách cập nhật stack trace của Throwable; nếu thực sự cần đặt trace, phải gọi API có chủ đích và hiểu hậu quả.

## 9. Cause chain khác suppressed list và trace frames

Ba thao tác truy vấn thường có hình dạng khác nhau.

**Duyệt cause chain:**

~~~java
// Trích đoạn minh họa, exception đã tồn tại.
Throwable current = exception;
while (current != null) {
    System.out.println(current.getClass().getSimpleName());
    current = current.getCause();
}
~~~

**Đọc suppressed của một Throwable cụ thể:**

~~~java
for (Throwable extra : exception.getSuppressed()) {
    System.out.println("additional: " + extra.getMessage());
}
~~~

**Đọc các frame của một Throwable cụ thể:**

~~~java
for (StackTraceElement frame : exception.getStackTrace()) {
    System.out.println(frame.getClassName() + "."
            + frame.getMethodName());
}
~~~

Các đoạn là minh họa, không phải chương trình độc lập; cần biến `exception` và import thích hợp. Nếu bạn chỉ duyệt `getCause()`, bạn có thể bỏ qua suppressed. Nếu chỉ gọi `getSuppressed()` trên outer wrapper, bạn có thể bỏ qua suppressed **trên cause**. Nếu chỉ lấy trace ngoài cùng, bạn có thể nhìn thấy nơi wrapper được tạo nhưng không biết lỗi kỹ thuật gốc phát sinh ở đâu.

Trong code production có exception structure bất thường hoặc vòng tham chiếu do tích hợp, khi viết utility duyệt đồ thị hãy dùng tập danh tính đã thăm (ví dụ `IdentityHashMap`) và giới hạn độ sâu/số node; đừng dùng một vòng lặp không giới hạn từ input không đáng tin.

## 10. Kịch bản 1 — chỉ có cause, không có suppressed

Ví dụ:

~~~java
IOException io = new IOException("file not found");
RuntimeException application =
        new IllegalStateException("cannot import", io);
~~~

Trường hợp này:

- `application.getCause() == io` là true.
- `application.getSuppressed().length` thường bằng 0.
- `io.getSuppressed().length` cũng thường bằng 0 nếu không ai gắn thêm.
- `application.getStackTrace()` là trace khi wrapper được tạo.
- `io.getStackTrace()` là trace khi IOException được tạo.

Nếu log chỉ ngoại lệ ngoài cùng dưới dạng `application.getMessage()`, bạn sẽ mất thông tin `"file not found"` và stack của IOException. Nên truyền Throwable đầy đủ cho logger.

## 11. Kịch bản 2 — có suppressed nhưng không có cause

~~~java
IllegalStateException primary =
        new IllegalStateException("commit failed");
primary.addSuppressed(new IOException("rollback failed"));
~~~

Ở đây:

- Cause của `primary` có thể là `null`.
- Suppressed gồm `IOException("rollback failed")`.
- `rollback failed` không tự trở thành nguyên nhân gốc của lỗi commit; đây là **lỗi phụ** cần lưu vết.
- Đừng đổi `primary` thành `new RuntimeException("rollback failed")` mà vứt đi lỗi commit.

Ví dụ dùng `IOException` nên cần import trong phương thức/lớp. Khi xử lý giao dịch thật, nghiệp vụ phải thiết kế chính sách compensation/rollback riêng; suppressed chỉ lưu thông tin lỗi, không tự sửa dữ liệu.

## 12. Kịch bản 3 — wrapper với cause có suppressed

Đây là đúng tình huống `ThrowableRelationsDemo`:

~~~text
outer IllegalStateException
  cause -> body IOException
           suppressed[0] -> close IOException
~~~

**Hai truy vấn cho kết quả khác nhau:**

~~~java
outer.getSuppressed();             // Mảng rỗng.
outer.getCause().getSuppressed();  // Chứa IOException từ close.
~~~

Đoạn minh họa cần biến `outer` như trong chương trình đầy đủ. Đừng copy suppressed lên outer nếu không có lý do rõ ràng: như vậy một lỗi close có thể bị xuất hiện **hai lần** khi logger duyệt cả outer và cause. Việc wrapper giữ nguyên reference `cause` đã đủ để preserved metadata bên dưới.

Trong log, `printStackTrace()` duyệt cả cause và suppressed của cause. Các logger phổ biến có hỗ trợ Throwable thường cũng hiển thị cây lỗi; cần xác nhận cấu hình cụ thể của backend nếu output không có thông tin suppressed.

## 13. Kịch bản 4 — nhiều resource đóng theo thứ tự ngược

Với:

~~~java
try (ResourceA a = new ResourceA();
     ResourceB b = new ResourceB()) {
    doWork();
}
~~~

Java đóng `b` trước `a`. Nếu `doWork()` ném A và `b.close()` ném B, `a.close()` ném C:

~~~text
Primary: A (doWork)
  suppressed[0]: B (b.close)
  suppressed[1]: C (a.close)
~~~

Đây là mô hình logic với giả định cả hai close ném. Không dựa vào thứ tự suppressed để suy ra quan hệ nhân quả giữa B và C; thứ tự phản ánh việc Java đóng resource.

Nếu body không ném và `b.close()` ném B, lỗi B có thể là primary; lỗi từ `a.close()` được suppress vào B. Thứ tự khai báo resource khác có thể đổi thứ tự close, nhưng không nên thay tài nguyên chỉ để làm đẹp exception output.

### Giữ riêng lỗi mở resource

Nếu constructor hoặc biểu thức khởi tạo một resource trong danh sách khai báo ném lỗi, Java vẫn phải đóng các resource **đã mở thành công trước đó** theo quy tắc try-with-resources. Lỗi close khi cleanup các resource ấy có thể được suppress vào exception khởi tạo ban đầu. Đây cũng là lý do test cleanup cần cover cả lỗi ở quá trình mở và ở thân try.

## 14. Kịch bản 5 — ngoại lệ đi qua Future, CompletableFuture

Một worker ném lỗi và caller nhận exception wrapper:

~~~java
// Trích đoạn; pool là ExecutorService.
Future<String> future = pool.submit(() -> {
    throw new IOException("read failed");
});

try {
    future.get();
} catch (ExecutionException ex) {
    Throwable original = ex.getCause();
}
~~~

Đoạn này cần imports và xử lý `InterruptedException`, hoặc đặt trong method khai báo `throws InterruptedException`. `ExecutionException` có vai trò **wrapper**, giữ exception từ task làm cause. Lỗi worker không tự “được ném” trên call stack của thread đợi; caller nhận kênh lỗi qua `Future.get()`.

Với `CompletableFuture.join()`:

~~~java
// Trích đoạn:
CompletableFuture<String> failed =
        CompletableFuture.failedFuture(new IOException("disk failed"));

try {
    failed.join();
} catch (CompletionException ex) {
    Throwable cause = ex.getCause();
}
~~~

Trong hoàn tất bất thường thông thường, `join()` báo `CompletionException` chứa cause; một future bị hủy có thể ném `CancellationException` trực tiếp. Đừng coi wrapper mới là lỗi kỹ thuật ban đầu hoặc tự suy ra suppressed trên wrapper.

Khi một task có suppressed resource-close exception trước khi bị bọc, hãy kiểm tra suppressed **ở Throwable phát sinh trong task**, tức ở cause hoặc một cause sâu hơn. Không xem stack trace của `ExecutionException` ở caller như bằng chứng lỗi I/O xảy ra trên thread đang chờ.

## 15. Kịch bản 6 — log và serialization làm mất metadata

Một anti-pattern:

~~~java
catch (Exception ex) {
    logger.error(ex.getMessage());
    throw new IllegalStateException("failed");
}
~~~

Đoạn này chỉ minh họa; `logger` là logger của ứng dụng. Tại đây:

- Logger có thể chỉ ghi text, không có stack/cause/suppressed.
- Wrapper mới không giữ ex làm cause.
- Điều tra viên không thể tìm lại lỗi đóng resource hoặc vị trí lỗi gốc chỉ từ string `"failed"`.

Cách giữ metadata:

~~~java
catch (Exception ex) {
    throw new IllegalStateException("operation failed", ex);
}
~~~

Nếu tầng này chỉ ném tiếp, không nhất thiết log tại đây. Ghi lỗi một lần ở ranh giới chịu trách nhiệm, dùng logger API nhận cả `Throwable` và ngữ cảnh như operation/request ID. Tránh in nguyên message có bí mật hoặc dữ liệu cá nhân vào response public.

### Dữ liệu log dạng JSON không tự giữ cây Throwable

Một JSON event dạng:

~~~json
{
  "exceptionType": "IllegalStateException",
  "message": "operation failed",
  "requestId": "req-15"
}
~~~

là log minh họa **chưa** chứa cause, suppressed và stack frames. Nếu hệ thống cần điều tra, logger/serializer phải chủ động có field/renderer cho các cấu trúc ấy, hoặc lưu trace id liên kết tới lỗi đầy đủ. Đừng khẳng định “đã log Throwable” nếu thực tế chỉ serialize `getMessage()`.

## 16. Kiểm thử ba quan hệ riêng biệt

Bộ test cần xác minh:

| Mục tiêu | Assertion nên dùng | Điều tránh |
|---|---|---|
| Wrapper có cause đúng | `assertSame(original, wrapper.getCause())` | Chỉ so sánh message |
| Cause không bị mất khi đổi tầng | `assertInstanceOf(IOException.class, wrapper.getCause())` | Bọc rồi bỏ cause |
| Suppressed của lỗi thân try | `assertEquals(1, cause.getSuppressed().length)` | Nhìn suppressed trên wrapper và tưởng không có |
| Loại lỗi close | `assertInstanceOf(IOException.class, suppressed[0])` | Parse `printStackTrace()` để lấy subtype |
| Stack trace có frame | Kiểm tra mảng không rỗng khi môi trường test cam kết hỗ trợ | Hard-code số dòng source |
| Trace của wrapper và cause khác nhau | Xác nhận method đầu như `execute` và `read` trong demo | Coi stack chỉ là chain cause |
| Nhiều close failure | Kiểm tra thứ tự và số lượng suppressed tương ứng | Đếm lỗi suppressed như hai operation thất bại độc lập |
| Rethrow cùng Throwable | Kiểm tra identity/cause theo contract | Mong stack tự động cập nhật tại mỗi `throw` |
| Lỗi chỉ xảy ra trong close | `getSuppressed()` có thể rỗng; close failure là primary | Mặc định mọi close failure là suppressed |
| Logger | Bảo đảm render cause và suppressed theo backend | Test logic bằng regex trên text log động |

### Test JUnit 5 mẫu

JUnit 5 cần dependency bên ngoài JDK. Ví dụ sau có thể đặt cùng default package với `ThrowableRelationsDemo` trong dự án test:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.io.IOException;
import org.junit.jupiter.api.Test;

class ThrowableRelationsDemoTest {
    @Test
    void causeHoldsBodyFailureAndSuppressedHoldsCloseFailure() {
        IllegalStateException outer = assertThrows(
                IllegalStateException.class,
                ThrowableRelationsDemo::execute);

        Throwable cause = outer.getCause();
        assertInstanceOf(IOException.class, cause);
        assertEquals("read failed", cause.getMessage());

        assertEquals(0, outer.getSuppressed().length);
        assertEquals(1, cause.getSuppressed().length);
        assertInstanceOf(IOException.class, cause.getSuppressed()[0]);
        assertEquals("close failed",
                cause.getSuppressed()[0].getMessage());

        assertEquals("execute",
                outer.getStackTrace()[0].getMethodName());
        assertEquals("read",
                cause.getStackTrace()[0].getMethodName());
        assertEquals("close",
                cause.getSuppressed()[0].getStackTrace()[0].getMethodName());
    }
}
~~~

**Điều kiện test stack trace:** ví dụ này dùng Throwable mặc định với writable stack trace trên JVM thông thường. Nếu framework cấu hình tắt stack trace hoặc tái sử dụng stackless exceptions, đừng dùng assertion cứng vào `getStackTrace()[0]` ở mọi trường hợp; test metadata nguyên nhân và suppressed vẫn có thể độc lập với trace.

## 17. Những câu hỏi dễ nhầm — giải đáp nhanh

**Q1. Cause có phải là lỗi xuất hiện đầu tiên theo thời gian không?** Không nhất thiết. Cause là quan hệ do API/lập trình viên thiết lập để diễn đạt nguyên nhân/chuyển tầng; thứ tự thời gian chỉ là một yếu tố.

**Q2. Suppressed có phải là một kiểu Exception riêng?** Không. Đây là các đối tượng `Throwable` được gắn vào một Throwable khác; subtype của chúng vẫn có thể là IOException, SQLException, RuntimeException hoặc loại khác.

**Q3. Một Throwable có được có cả cause và suppressed không?** Có. Ba nhóm metadata cùng tồn tại độc lập.

**Q4. `throw ex;` có tự tạo stack trace mới không?** Thông thường không. Nó ném lại cùng object; trace đã được ghi nhận khi object được tạo hoặc gọi `fillInStackTrace()`.

**Q5. `getCause() == null` có nghĩa lỗi không có nguyên nhân?** Chỉ có nghĩa không có cause được gắn để caller đọc. Không thể suy ra nguyên nhân thực tế trong hệ thống không tồn tại.

**Q6. `getSuppressed().length == 0` có nghĩa không có lỗi cleanup?** Không chắc. Có thể cleanup thành công, lỗi đã bị bỏ/che, suppression bị vô hiệu hóa hoặc lỗi nằm ở Throwable khác trong cause chain.

**Q7. `getStackTrace().length == 0` có nghĩa exception không thật?** Không. Stack trace có thể rỗng/tắt vì cấu hình, constructor hoặc đặc thù runtime.

**Q8. Có thể dựa vào số dòng trong stack trace làm test không?** Không nên. Refactor thêm vài dòng cũng khiến số dòng đổi; kiểm tra loại lỗi, cause/suppressed và frame có nghĩa nếu cần.

**Q9. `printStackTrace()` có hiển thị suppressed không?** Với `Throwable` chuẩn, có, bao gồm nhánh suppressed và cause. Logger custom/JSON serializer có thể trình bày khác hoặc bỏ qua nếu chưa cấu hình đúng.

**Q10. Một IOException close bị suppressed có cần xử lý không?** Có thể rất quan trọng, nhất là nếu close flush dữ liệu hoặc commit buffer. Suppressed không đồng nghĩa được phép bỏ qua.

**Q11. Nếu bọc cause mới thì có cần sao chép mọi suppressed vào wrapper?** Thường không. Cause giữ suppressed của nó; sao chép có thể tạo báo cáo trùng.

**Q12. Một lỗi trong finally có được tự động suppressed không?** Không mặc định. `try-with-resources` có quy tắc suppression đặc biệt; `finally` thủ công có thể làm lỗi trước bị thay thế nếu chính nó ném.

## 18. Sai lầm phổ biến và cách sửa

1. **Chỉ ghi `ex.getMessage()`:** mất stack/cause/suppressed. → Truyền Throwable tới logger.
2. **Bọc lỗi không có cause:** tạo exception mới nhưng không có `ex`. → Dùng constructor nhận `Throwable cause`.
3. **Đồng nhất suppressed với cause:** tưởng close failure là lỗi gốc. → Xem mối quan hệ primary/secondary.
4. **Chỉ gọi `outer.getSuppressed()`:** bỏ qua suppressed trên cause. → Kiểm tra đúng node Throwable.
5. **Phân tích text `printStackTrace()` làm dữ liệu nghiệp vụ:** phụ thuộc format động. → Dùng các API có kiểu và error code.
6. **Cho rằng `throw ex;` ghi thêm frame mới:** nhầm vị trí tạo và vị trí ném lại. → Hiểu vòng đời Throwable.
7. **Tạo exception sớm rồi dùng lại khắp nơi:** trace/context có thể lỗi thời. → Tạo lỗi tại vị trí có ý nghĩa, không reuse tùy tiện.
8. **Gọi `fillInStackTrace()` để “cập nhật” mọi rethrow:** có thể làm mất bằng chứng nơi lỗi gốc. → Chỉ dùng nếu có yêu cầu kỹ thuật rõ.
9. **Dùng `finally` ném lỗi close không giữ lỗi body:** làm che failure chính. → Dùng try-with-resources hoặc thiết kế suppression thủ công.
10. **Bỏ suppressed của resource:** lỗi cleanup bị vô hình. → Test thất bại cả body lẫn close.
11. **Gom mọi Throwable thành root cause duy nhất:** mất wrapper chứa context/domain. → Giữ toàn bộ chain.
12. **Log cùng exception nhiều tầng rồi ném tiếp:** nhân bản một sự cố thành nhiều ERROR. → Đặt logging boundary có trách nhiệm.
13. **Giả định future wrapper có trace worker:** trace wrapper và cause phát sinh ở ngữ cảnh khác. → Đọc cause/stack đúng node.
14. **Gắn suppressed vào exception không liên quan:** làm sai quan hệ nguyên nhân. → Chỉ gắn lỗi phụ của cùng thao tác/cleanup.
15. **Không xử lý null/empty trong utility đọc Throwable:** `getCause()` có thể null, mảng suppressed/trace có thể rỗng. → Kiểm tra và giới hạn traversal.
16. **Biến stack trace thành thông tin trả công khai:** có thể lộ code, đường dẫn, thư viện và thông tin nhạy cảm. → Trả error code/request ID an toàn; giữ trace trong kênh nội bộ.

## 19. Checklist khi điều tra exception Java

Khi mở một sự kiện log hoặc lỗi được báo từ thread/future:

1. Xác định **Throwable ngoài cùng** và operation/request/task liên quan.
2. Ghi nhận exception type và message nhưng không lấy message làm error code tự động.
3. Đọc `getCause()` để biết lỗi nào được bọc; lặp theo chain **có kiểm soát** nếu cần.
4. Ở **mỗi Throwable**, kiểm tra `getSuppressed()` — không chỉ ở wrapper.
5. Ở mỗi node quan trọng, xem `getStackTrace()` để định vị nơi Throwable được tạo.
6. Phân biệt **thất bại thân try** và **thất bại close/cleanup**.
7. Nếu lỗi đi qua `Future.get()`/`join()`, tách wrapper của completion khỏi lỗi task.
8. Nếu thấy nhiều suppressed, kiểm tra số resource, thứ tự close và operation phụ đã thất bại.
9. Kiểm tra contract exception qua tầng ứng dụng: có bị đổi kiểu, bỏ cause hoặc copy message không?
10. Không kết luận rollback hay resource cleanup hoàn tất chỉ vì exception được ném và suppressed.
11. Khi cần log, giữ Throwable đầy đủ, bổ sung operation, error code và request/business ID được phép ghi.
12. Kiểm thử đúng type/cause/suppressed, không hard-code text stack trace hay line number.

## 20. Kết luận

Bảng phân biệt **cause, suppressed và stack trace** tóm gọn trong ba câu:

- **Cause** (`getCause()`): *Lỗi nào được gắn làm nguyên nhân của lỗi hiện tại?*
- **Suppressed** (`getSuppressed()`): *Những lỗi phụ nào được giữ lại cùng lỗi chính, đặc biệt khi cleanup/close thất bại?*
- **Stack trace** (`getStackTrace()`): *Dấu vết những lời gọi được ghi nhận cho chính đối tượng Throwable này là gì?*

Ba thông tin không thay thế lẫn nhau. Một outer exception có thể có cause, cause ấy có suppressed, và cả ba Throwable đều có stack trace riêng. Viết Java đúng là **bảo toàn cause khi bọc lỗi, tôn trọng suppression trong try-with-resources, và dùng stack trace để điều tra chứ không làm dữ liệu nghiệp vụ**.

### Tài liệu tham khảo

- [Java SE 17 — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 17 — StackTraceElement](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackTraceElement.html)
- [Java Language Specification `14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3)
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java SE 17 — ExecutionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutionException.html)
- [Java SE 17 — CompletionException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionException.html)
