# Giữ nguyên cơ chế suppressed exception trong Java

## Mục tiêu

Trong Java, một thao tác có thể phát sinh nhiều exception liên quan đến cùng một lần xử lý tài nguyên. Ví dụ: phần thân `try` gặp lỗi khi đọc dữ liệu, sau đó `close()` của tài nguyên cũng gặp lỗi. Cần giữ lại cả hai thông tin để chẩn đoán: lỗi trong phần thân là exception chính, còn lỗi khi đóng tài nguyên được ghi nhận dưới dạng *suppressed exception*.

Cơ chế này được tích hợp trong `try-with-resources` và vẫn là cách quản lý tài nguyên chuẩn trong các phiên bản Java hiện hành. Các API cần biết là `Throwable.addSuppressed(Throwable)` và `Throwable.getSuppressed()`.

## Suppressed exception là gì?

Một `Throwable` có thể giữ:

- **Cause**: nguyên nhân mà exception hiện tại bọc lại, truy cập bằng `getCause()`.
- **Suppressed exceptions**: các lỗi phụ phát sinh trong quá trình xử lý hoặc dọn dẹp, được gắn vào exception chính và truy cập bằng `getSuppressed()`.

Hai quan hệ này khác nhau. Suppressed exception không tự động trở thành cause. Khi đọc log hoặc xử lý exception, cần xem cả exception chính, cause và danh sách suppressed nếu tình huống có thể phát sinh nhiều lỗi.

## Cách `try-with-resources` giữ lỗi khi đóng tài nguyên

`try-with-resources` tự gọi `close()` cho từng tài nguyên sau khi phần thân `try` kết thúc. Những tài nguyên được khai báo sau sẽ được đóng trước.

Hành vi phụ thuộc vào việc phần thân `try` có ném exception hay không:

1. **Phần thân `try` ném exception và `close()` cũng ném exception:** exception từ phần thân được giữ làm exception chính. Exception phát sinh trong từng lần `close()` được thêm vào danh sách suppressed của exception chính.
2. **Phần thân `try` kết thúc bình thường nhưng `close()` ném exception:** exception đầu tiên phát sinh khi đóng tài nguyên trở thành exception chính. Nếu những lần đóng tiếp theo cũng lỗi, các lỗi sau được thêm vào danh sách suppressed của exception chính đó.
3. **Có nhiều tài nguyên:** Java đóng chúng theo thứ tự ngược với thứ tự khai báo. Vì vậy thứ tự các suppressed exception phản ánh thứ tự lỗi xuất hiện trong quá trình đóng.

Cơ chế này cũng áp dụng khi việc khởi tạo một tài nguyên phía sau thất bại: những tài nguyên đã khởi tạo thành công trước đó vẫn được đóng, và lỗi khi đóng được giữ cùng exception gây ra việc khởi tạo thất bại.

## Dùng biến tài nguyên có sẵn từ Java 9

Từ Java 9, `try-with-resources` cho phép tham chiếu một biến tài nguyên đã được khai báo bên ngoài, miễn là biến đó là `final` hoặc *effectively final* (không bị gán lại sau khi khởi tạo):

```java
DemoResource resource = new DemoResource("existing");

try (resource) {
    // Sử dụng resource trong phạm vi này.
}
```

Java vẫn tự gọi `close()` khi rời khỏi khối. Quy tắc giữ exception chính và gắn lỗi đóng tài nguyên vào `getSuppressed()` không thay đổi.

## Ví dụ chạy được

Ví dụ dưới đây tạo hai tài nguyên. Phần thân `try` ném `IOException`; cả hai lần `close()` cũng ném `IOException`. Chương trình in exception chính và các suppressed exception để thấy rõ thứ tự.

**Tệp `SuppressedExceptionDemo.java`:**

```java
import java.io.IOException;

public class SuppressedExceptionDemo {
    private static final class DemoResource implements AutoCloseable {
        private final String name;

        private DemoResource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("close " + name);
            throw new IOException("close " + name);
        }
    }

    public static void main(String[] args) {
        try (DemoResource first = new DemoResource("first");
             DemoResource second = new DemoResource("second")) {
            System.out.println("body");
            throw new IOException("body failed");
        } catch (IOException primary) {
            System.out.println("primary: " + primary.getMessage());

            for (Throwable suppressed : primary.getSuppressed()) {
                System.out.println("suppressed: " + suppressed.getMessage());
            }
        }
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```bash
javac SuppressedExceptionDemo.java
java SuppressedExceptionDemo
```

**Kết quả chuẩn:**

```text
body
close second
close first
primary: body failed
suppressed: close second
suppressed: close first
```

`second` được khai báo sau nên được đóng trước. Lỗi `body failed` vẫn là exception chính; hai lỗi từ `close()` được giữ theo thứ tự phát sinh trong danh sách suppressed. Không có lỗi nào bị âm thầm thay thế lỗi ban đầu.

## Đọc và xử lý suppressed exception

Dùng `getSuppressed()` trên exception chính để lấy các lỗi phụ:

```java
try {
    process();
} catch (Exception primary) {
    for (Throwable suppressed : primary.getSuppressed()) {
        System.err.println("Lỗi khi dọn dẹp: " + suppressed);
    }
    throw primary;
}
```

Đoạn trên minh họa cách quan sát suppressed exception; trong mã ứng dụng, chỉ bắt exception khi có xử lý phù hợp. Nếu chỉ cần ghi log, có thể truyền exception đầy đủ cho logger hoặc ghi stack trace. Stack trace do `Throwable.printStackTrace()` tạo ra hiển thị các suppressed exception bằng dòng `Suppressed:`.

`getSuppressed()` trả về mảng các exception đã được gắn vào exception hiện tại. Nó không tự đi sâu vào cause. Nếu exception được bọc trong một exception khác, hãy kiểm tra cause tương ứng:

```java
Throwable original = wrapper.getCause();

if (original != null) {
    for (Throwable suppressed : original.getSuppressed()) {
        System.err.println("Lỗi phụ: " + suppressed);
    }
}
```

## Giữ suppressed exception khi bọc exception

Khi chuyển một exception sang loại exception khác, hãy giữ exception gốc làm cause:

```java
final class DataAccessException extends RuntimeException {
    DataAccessException(String message, Throwable cause) {
        super(message, cause);
    }
}

DataAccessException translate(IOException original) {
    return new DataAccessException("Không thể truy cập dữ liệu", original);
}
```

Nếu `original` có suppressed exception, chúng vẫn nằm trên `original` và có thể được truy cập qua `translated.getCause().getSuppressed()`. Chúng không tự chuyển lên `translated.getSuppressed()` vì quan hệ cause và suppressed là hai danh sách riêng.

Không tạo exception mới chỉ với message khi cần giữ nguyên thông tin lỗi. Cách đó làm mất liên kết tới exception gốc và các suppressed exception của nó. Nếu có thể truyền exception gốc trực tiếp, hãy ném lại chính exception đó; nếu cần chuyển loại, hãy truyền nó vào constructor làm cause.

## Lưu ý với exception tự định nghĩa

Các constructor thông dụng như `Exception(String, Throwable)` và `RuntimeException(String, Throwable)` bật cơ chế suppression theo mặc định. `Throwable` cũng có constructor protected cho phép lớp con chủ động cấu hình suppression và stack trace.

Nếu một lớp exception tự định nghĩa tắt suppression, các lỗi phụ không được lưu như mong đợi. Vì vậy, exception dùng làm exception chính trong luồng quản lý tài nguyên nên giữ suppression được bật, trừ khi có lý do thiết kế cụ thể để tắt nó.

`addSuppressed()` dùng để gắn thủ công một lỗi phụ khi tự xây dựng cơ chế tổng hợp lỗi. Với `try-with-resources`, Java đã thực hiện việc này tự động; thông thường không cần gọi thêm. Không truyền `null` và không thêm chính exception đó vào nó, vì thao tác tự suppress sẽ gây `IllegalArgumentException`.

## Thực hành tốt

- Dùng `try-with-resources` cho đối tượng triển khai `AutoCloseable`; để Java quản lý việc đóng và ghi nhận lỗi.
- Khai báo các tài nguyên trong cùng câu lệnh `try` khi chúng thuộc cùng một phạm vi sử dụng. Java sẽ đóng chúng theo thứ tự ngược khi rời khỏi khối.
- Để `close()` báo lỗi có ý nghĩa khi việc giải phóng tài nguyên thất bại; tránh nuốt exception khiến thông tin dọn dẹp biến mất.
- Khi bắt rồi chuyển exception sang loại khác, luôn giữ exception gốc làm cause.
- Khi điều tra lỗi, kiểm tra `getSuppressed()` của exception chính và của cause liên quan. Chỉ đọc `getMessage()` có thể bỏ sót chi tiết quan trọng.
- Viết kiểm thử cho trường hợp phần thân và `close()` cùng lỗi, đồng thời xác nhận exception chính và danh sách suppressed đúng thứ tự.

## Ghi nhớ

Suppressed exception giúp Java giữ lại lỗi phát sinh trong quá trình đóng tài nguyên mà không làm mất exception đã khiến thao tác chính thất bại. Với `try-with-resources`, hãy để cơ chế ngôn ngữ thực hiện việc đóng theo thứ tự ngược và gắn các lỗi phụ. Khi bắt hoặc bọc exception, giữ nguyên exception gốc để toàn bộ thông tin suppressed vẫn có thể truy cập được.