# `Throwable` — gốc của hệ phân cấp ngoại lệ trong Java

Trong Java, `java.lang.Throwable` là **lớp gốc chung của mọi đối tượng có thể được ném bằng `throw` và bắt bằng `catch`**. Hai nhánh trực tiếp của nó là `Error` và `Exception`. Hiểu vị trí của `Throwable` giúp phân biệt lỗi do ứng dụng cần xử lý, lỗi nghiêm trọng của môi trường thực thi, quy tắc kiểm tra ngoại lệ của trình biên dịch và cách Java giữ thông tin chẩn đoán.

## 1. Nhìn hệ phân cấp từ gốc

```text
java.lang.Object
└── java.lang.Throwable
    ├── java.lang.Error
    │   ├── OutOfMemoryError
    │   └── LinkageError
    │       └── NoClassDefFoundError
    └── java.lang.Exception
        ├── IOException
        ├── SQLException
        └── RuntimeException
            ├── NullPointerException
            ├── IllegalArgumentException
            └── IndexOutOfBoundsException
```

Đây là **một phần tiêu biểu** của cây kế thừa, không phải danh sách đầy đủ mọi lớp ngoại lệ. Trong Java, `Throwable` kế thừa `Object` và triển khai `Serializable`. Mỗi lớp ở phía dưới cũng là một `Throwable` theo quan hệ *is-a*: một `IllegalArgumentException` vừa là `RuntimeException`, `Exception`, vừa là `Throwable`.

| Kiểu | Đặc điểm | Cách ứng xử thông thường |
| --- | --- | --- |
| `Throwable` | Gốc chung; chứa thông điệp, nguyên nhân, stack trace và ngoại lệ bị đính kèm. | Làm nền tảng cho cơ chế ngoại lệ; hiếm khi tự tạo hoặc khai báo trực tiếp trong API ứng dụng. |
| `Error` | Biểu thị các sự cố nghiêm trọng hoặc bất thường mà ứng dụng thường không thể khắc phục cục bộ. | Thông thường để lan truyền và điều tra nguyên nhân; không bắt hàng loạt để giả vờ phục hồi. |
| `Exception` (không thuộc `RuntimeException`) | Thường đại diện tình huống có thể dự kiến và xử lý, ví dụ lỗi I/O. | Phải `catch` hoặc khai báo `throws` nếu phát sinh từ phương thức. |
| `RuntimeException` | Thường gắn với tham số không hợp lệ, trạng thái sai hoặc lỗi lập trình. | Không bị buộc `catch`/`throws`; xử lý ở ranh giới có đủ ngữ cảnh hoặc sửa nguyên nhân. |

**Checked và unchecked được quyết định bởi kiểu kế thừa, không phải mức độ nghiêm trọng hay tên lớp:**

- **Unchecked:** `RuntimeException` và các lớp con; `Error` và các lớp con.
- **Checked:** các lớp kế thừa `Throwable` còn lại, bao gồm chính `Throwable`, `Exception` và những lớp con của `Exception` nằm ngoài nhánh `RuntimeException`.

Ví dụ `IOException` là checked, còn `IllegalArgumentException` và `OutOfMemoryError` là unchecked. Việc `Error` là unchecked **không** có nghĩa có thể bỏ qua tác động thực tế của nó.

## 2. `throw`, `throws` và `catch` liên hệ thế nào với `Throwable`?

`throw` ném **một đối tượng** thuộc `Throwable` hoặc lớp con. `throws` đặt trên khai báo phương thức để mô tả **kiểu ngoại lệ** có thể truyền ra. `catch` nhận đối tượng ném ra ở vị trí xử lý tương ứng.

```java
import java.io.IOException;

class Example {
    static void readConfig(boolean missing) throws IOException {
        if (missing) {
            throw new IOException("Không tìm thấy cấu hình");
        }
    }

    public static void main(String[] args) {
        try {
            readConfig(true);
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Lưu thành `Example.java` rồi chạy:

```bash
javac -encoding UTF-8 Example.java
java Example
```

Kết quả:

```text
Không tìm thấy cấu hình
```

Vì `IOException` là checked, bỏ cả phần `catch` lẫn khai báo `throws IOException` ở một phương thức gọi có thể khiến mã **không biên dịch**. Ngược lại, ném `IllegalArgumentException` không bắt buộc khai báo `throws`.

Một đối tượng `new Throwable("lỗi")` hoàn toàn có thể được tạo và ném, nhưng bản thân `Throwable` cũng là **checked**. Việc khai báo `throws Throwable` cho một API công khai thường quá rộng: nó đẩy trách nhiệm xử lý cả những kiểu lỗi mà bên gọi không nên cố gắng phục hồi.

Khi có nhiều nhánh `catch`, đặt nhánh **cụ thể trước nhánh tổng quát**. Chẳng hạn `catch (IOException ex)` phải đứng trước `catch (Exception ex)` nếu cùng xử lý một `try`; làm ngược lại khiến nhánh `IOException` không thể được truy cập và trình biên dịch báo lỗi. `catch (Throwable ex)` về mặt cú pháp có thể bắt cả `Exception` và `Error`, nhưng thường quá bao quát cho xử lý nghiệp vụ.

## 3. Một `Throwable` lưu những thông tin gì?

Một đối tượng `Throwable` không chỉ là thông báo lỗi. Nó có thông tin phục vụ truy nguyên đường đi của sự cố.

| Thành phần / API | Ý nghĩa và lưu ý |
| --- | --- |
| `getClass()` | Kiểu lỗi thực tế, ví dụ `IllegalArgumentException`. |
| `getMessage()` | Thông điệp do người tạo ngoại lệ truyền vào; có thể là `null`. |
| `getLocalizedMessage()` | Mặc định trả về `getMessage()`; lớp con có thể ghi đè để bản địa hóa. |
| `getCause()` | Nguyên nhân gốc được liên kết qua constructor hoặc `initCause()`; có thể là `null`. |
| `getStackTrace()` | Mảng `StackTraceElement` biểu diễn đường gọi được ghi nhận; phần tử đầu thường là vị trí tạo/ghi nhận lỗi. |
| `printStackTrace()` | In ngoại lệ, call stack, nguyên nhân và suppressed exceptions; mặc định ra luồng lỗi chuẩn `System.err`. |
| `getSuppressed()` | Các ngoại lệ phụ bị đính kèm, đặc biệt từ thao tác đóng tài nguyên trong `try-with-resources`. |
| `toString()` | Mặc định ghép tên lớp với thông điệp (nếu có). |
| `fillInStackTrace()` | Cập nhật thông tin stack trace tại thời điểm gọi; chủ yếu phục vụ trường hợp chuyên biệt. |

**Stack trace** ghi lại chuỗi lời gọi tại thời điểm Throwable ghi nhận stack của nó, không phải lịch sử mọi thao tác trước đó. Dòng đầu của trace thường chỉ ra nơi tạo ngoại lệ; các dòng tiếp theo cho biết ai đã gọi phương thức đó. Vị trí và số dòng có thể thay đổi khi sửa hoặc biên dịch mã, nên không nên dùng nguyên văn stack trace làm đầu ra cố định của bài kiểm thử.

`Throwable` cung cấp các constructor như `Throwable()`, `Throwable(String message)`, `Throwable(String message, Throwable cause)` và `Throwable(Throwable cause)`. Nó còn có constructor `protected` cho phép cấu hình việc thu thập suppressed exceptions và stack trace; chủ yếu dành cho lớp con có nhu cầu đặc biệt.

Lỗi phổ biến là chỉ lưu `ex.getMessage()` rồi ném lỗi mới, làm mất **kiểu gốc, stack trace và cause**. Nên giữ quan hệ nguyên nhân khi chuyển lớp biểu diễn lỗi.

## 4. Ví dụ chạy được: kiểm tra quan hệ kế thừa và nguyên nhân

Tệp `ThrowableDemo.java`:

```java
public class ThrowableDemo {
    public static void main(String[] args) {
        System.out.println("Exception là Throwable: "
                + Throwable.class.isAssignableFrom(Exception.class));
        System.out.println("Error là Throwable: "
                + Throwable.class.isAssignableFrom(Error.class));
        System.out.println("IllegalArgumentException là RuntimeException: "
                + RuntimeException.class.isAssignableFrom(IllegalArgumentException.class));

        try {
            parsePort("abc");
        } catch (IllegalArgumentException ex) {
            System.out.println("Kiểu: " + ex.getClass().getSimpleName());
            System.out.println("Thông điệp: " + ex.getMessage());
            System.out.println("Nguyên nhân: " + ex.getCause().getClass().getSimpleName());
            System.out.println("Phương thức tại frame đầu: "
                    + ex.getStackTrace()[0].getMethodName());
        }
    }

    static int parsePort(String text) {
        final int port;
        try {
            port = Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Port phải là số nguyên: " + text, ex);
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Port phải nằm trong 1..65535");
        }
        return port;
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac -encoding UTF-8 ThrowableDemo.java
java ThrowableDemo
```

Kết quả:

```text
Exception là Throwable: true
Error là Throwable: true
IllegalArgumentException là RuntimeException: true
Kiểu: IllegalArgumentException
Thông điệp: Port phải là số nguyên: abc
Nguyên nhân: NumberFormatException
Phương thức tại frame đầu: parsePort
```

Điều đáng chú ý: `Integer.parseInt("abc")` ném `NumberFormatException`. Hàm `parsePort` cung cấp thông điệp có ngữ cảnh ứng dụng bằng `IllegalArgumentException` **và giữ ngoại lệ ban đầu làm cause**. Khi điều tra lỗi, vẫn có thể lần về thao tác phân tích số. Việc kiểm tra khoảng cổng được đặt ngoài `try` bắt `NumberFormatException` để tránh vô tình gói sai lỗi kiểm tra phạm vi.

`Class.isAssignableFrom(...)` là cách kiểm tra quan hệ kiểu ở thời điểm chạy: `A.class.isAssignableFrom(B.class)` trả `true` nếu giá trị thuộc kiểu `B` có thể gán vào biến kiểu `A` theo quan hệ kiểu Java. Nó không tự tạo hay ném ngoại lệ.

## 5. Cause và suppressed exception là hai quan hệ khác nhau

**Cause** trả lời “lỗi này phát sinh từ lỗi nào?”. Constructor có tham số `cause` là cách thông thường để gắn chuỗi nguyên nhân:

```java
throw new IllegalStateException("Không thể nạp cấu hình", originalException);
```

Đây là đoạn minh họa nằm trong một phương thức đang có biến `originalException` kiểu `Throwable` phù hợp; không phải chương trình độc lập. `initCause(cause)` chỉ dùng khi nguyên nhân chưa được thiết lập; không thể đặt lại tùy ý, và không thể tự đặt chính ngoại lệ đó làm nguyên nhân của nó. Ưu tiên constructor nhận `cause` vì diễn đạt ý định ngay lúc tạo đối tượng.

**Suppressed exceptions** trả lời “trong lúc xử lý sự cố này còn lỗi phụ nào khác?”. Trường hợp tiêu biểu là khối `try-with-resources`: mã trong `try` ném một lỗi, và thao tác `close()` cũng ném lỗi. Java giữ lỗi từ phần thân `try` làm ngoại lệ chính, đính lỗi đóng tài nguyên vào `getSuppressed()`.

Tệp `SuppressedDemo.java`:

```java
public class SuppressedDemo {
    static class BrokenResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource resource = new BrokenResource()) {
            throw new IllegalArgumentException("work failed");
        } catch (Exception ex) {
            System.out.println("Lỗi chính: " + ex.getMessage());
            System.out.println("Số lỗi phụ: " + ex.getSuppressed().length);
            System.out.println("Lỗi phụ: " + ex.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac -encoding UTF-8 SuppressedDemo.java
java SuppressedDemo
```

Kết quả:

```text
Lỗi chính: work failed
Số lỗi phụ: 1
Lỗi phụ: close failed
```

`getCause()` và `getSuppressed()` **không thể thay thế nhau**. Trong ví dụ trên, `getCause()` của lỗi chính là `null`, còn `getSuppressed()` chứa lỗi của `close()`. `Throwable.addSuppressed(...)` có thể dùng để đính kèm thủ công khi thực sự cần; phương thức từ chối tự suppress chính đối tượng và tham số `null`.

## 6. Có nên bắt `Throwable`?

Xét khối sau:

```java
try {
    performWork();
} catch (Throwable ex) {
    System.out.println("Có lỗi: " + ex.getMessage());
}
```

Đây là **đoạn minh họa**, giả định `performWork()` đã được định nghĩa. Nó sẽ bắt cả `IOException`, `RuntimeException` lẫn `OutOfMemoryError` nếu những lỗi đó được ném trong khối `try`. Việc in một dòng rồi chạy tiếp không bảo đảm trạng thái ứng dụng còn hợp lệ. Thực tế, cách này có thể che dấu lỗi nghiêm trọng; với `InterruptedException` (một checked `Exception`) thì bắt quá rộng và không xử lý đúng cũng có thể phá vỡ cơ chế hủy tác vụ.

Lựa chọn hợp lý hơn:

1. Bắt **kiểu cụ thể có thể xử lý được** ngay tại nơi có ngữ cảnh, ví dụ `IOException` khi quyết định có thử lại thao tác I/O hay không.
2. Nếu không thể phục hồi ở tầng hiện tại, cho lỗi lan truyền hoặc **bọc lỗi với cause** để bổ sung ý nghĩa nghiệp vụ.
3. Đặt xử lý lỗi tập trung ở ranh giới ứng dụng (ví dụ tầng API hoặc vòng lặp tác vụ) bằng cơ chế phù hợp; việc ghi log không đồng nghĩa đã khắc phục được lỗi.
4. Thường để `Error` lan truyền. Chỉ bắt loại `Error` cụ thể khi có lý do kỹ thuật rõ ràng và biết chắc cách xử lý an toàn; `Error` không phải mọi trường hợp đều có cùng mức nghiêm trọng.
5. Không dùng `throws Throwable` trong hợp đồng API thông thường nếu có thể khai báo kiểu checked cụ thể hơn.

`catch (Exception ex)` cũng không phải cơ chế bắt toàn bộ: nó không bắt những lỗi chỉ thuộc nhánh `Error`. Trong các đoạn mã đòi hỏi thao tác dọn dẹp bất kể kết quả, `finally` hoặc `try-with-resources` thường thích hợp hơn so với cố bắt `Throwable` chỉ để chạy logic dọn dẹp.

## 7. Ghi log, diễn giải stack trace và các lỗi thường gặp

- **Giữ nguyên đối tượng ngoại lệ khi log:** một logger hỗ trợ tham số exception sẽ ghi cả stack trace và chuỗi cause. Chỉ ghi `getMessage()` có thể làm mất dữ kiện điều tra.
- **Không lạm dụng `printStackTrace()` trong ứng dụng triển khai thực tế:** hàm này in trực tiếp ra stream, thường thiếu ngữ cảnh và cách quản lý log. Với ví dụ học tập nhỏ, nó vẫn hữu ích để quan sát cấu trúc `Throwable`.
- **Đừng giả định `getMessage()`, `getCause()` hay `getStackTrace()[0]` luôn tồn tại:** message/cause có thể `null`; stack trace có thể rỗng nếu đối tượng được cấu hình không ghi trace hoặc trace bị điều chỉnh.
- **Tránh `throw ex;` sau khi chỉ log mà không có mục đích rõ ràng:** khi bắt rồi ném lại, thông tin stack gốc của cùng đối tượng vẫn được giữ, nhưng nếu nhiều tầng cùng log, một lỗi có thể xuất hiện lặp lại. Quyết định tầng nào chịu trách nhiệm ghi log.
- **Không thay ngoại lệ bằng `new RuntimeException(ex.getMessage())`:** câu lệnh này đánh mất liên kết cause. Nếu phải bọc, dùng `new RuntimeException("Ngữ cảnh", ex)`.
- **Không tùy tiện gọi `fillInStackTrace()` hoặc `setStackTrace(...)`:** chúng thay đổi thông tin chẩn đoán. Việc tạo/ghi stack trace cũng có chi phí; tối ưu đặc biệt cho hệ thống tải cao cần có bằng chứng đo lường trước khi đánh đổi khả năng gỡ lỗi.

## 8. Tự kiểm tra hiểu bài

**Câu 1.** `throw new String("lỗi");` có hợp lệ không? **Không.** `String` không kế thừa `Throwable`; chỉ đối tượng kiểu `Throwable` hoặc lớp con mới có thể được ném.

**Câu 2.** `RuntimeException` nằm ngoài `Exception`? **Không.** Nó là lớp con trực tiếp của `Exception`; quy tắc unchecked là một quy tắc ngôn ngữ dựa trên nhánh kế thừa.

**Câu 3.** `catch (Exception ex)` bắt mọi `Error`? **Không.** `Error` và `Exception` là hai nhánh riêng dưới `Throwable`.

**Câu 4.** `Throwable` bản thân có phải checked exception? **Có.** Nó không thuộc nhánh `RuntimeException` hoặc `Error`.

**Câu 5.** Lỗi đóng tài nguyên trong `try-with-resources` có luôn thay lỗi đã xảy ra trong thân `try`? **Không.** Nếu cả hai nơi đều ném lỗi, lỗi từ thân `try` thường là lỗi chính, lỗi đóng tài nguyên được giữ ở `getSuppressed()`.

**Ghi nhớ:** `Throwable` định nghĩa nền tảng cho cơ chế ném, bắt và truy nguyên ngoại lệ của Java. Nhánh kế thừa quyết định quy tắc checked/unchecked; `message` giải thích sự cố, `stack trace` chỉ ra đường gọi, `cause` lưu chuỗi nguyên nhân và `suppressed` lưu lỗi phụ. Khi viết chương trình, hãy bắt đúng kiểu có khả năng xử lý và giữ đủ thông tin khi truyền lỗi giữa các tầng.
