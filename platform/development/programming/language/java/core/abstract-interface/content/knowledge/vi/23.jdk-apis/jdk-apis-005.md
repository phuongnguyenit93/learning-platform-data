# AutoCloseable và Closeable trong try-with-resources

## Mục tiêu

Java cung cấp hai interface quan trọng để biểu diễn đối tượng cần giải phóng tài nguyên: `AutoCloseable` và `Closeable`. Cả hai kết hợp với cú pháp `try-with-resources` để tự động gọi `close()` khi khối `try` kết thúc, kể cả khi có ngoại lệ.

Sau bài này, bạn sẽ biết mối quan hệ giữa hai interface, cách chọn loại phù hợp, thứ tự đóng tài nguyên và cách Java xử lý ngoại lệ phát sinh trong lúc đóng.

## 1. AutoCloseable là gì?

`AutoCloseable` thuộc gói `java.lang` và có từ Java 7. Đây là hợp đồng tổng quát cho đối tượng có thể được đóng hoặc giải phóng tài nguyên. Interface khai báo phương thức:

~~~java
public interface AutoCloseable {
    void close() throws Exception;
}
~~~

Đây là chữ ký khái quát của interface. Một lớp triển khai có thể khai báo `close()` không ném ngoại lệ checked nào, hoặc ném một loại ngoại lệ hẹp hơn `Exception`. Ví dụ, lớp quản lý kết nối cơ sở dữ liệu có thể ném `SQLException`, còn lớp quản lý tài nguyên I/O có thể ném `IOException`.

`AutoCloseable` được dùng bởi nhiều API cần dọn dẹp tài nguyên, chẳng hạn tài nguyên cơ sở dữ liệu, giao dịch, bộ đọc/ghi hoặc tài nguyên do ứng dụng tự định nghĩa. Nó cho phép `try-with-resources` xử lý việc gọi `close()` theo cùng một cơ chế mà không cần biết chi tiết tài nguyên bên trong.

## 2. Closeable là gì và khác ở đâu?

`Closeable` thuộc gói `java.io`, có từ Java 5 và mở rộng `AutoCloseable`. Nó được thiết kế cho tài nguyên I/O:

~~~java
public interface Closeable extends AutoCloseable {
    void close() throws IOException;
}
~~~

Vì `Closeable` là một `AutoCloseable`, mọi đối tượng triển khai `Closeable` cũng có thể được sử dụng trong `try-with-resources`.

| Đặc điểm | `AutoCloseable` | `Closeable` |
|---|---|---|
| Gói | `java.lang` | `java.io` |
| Có từ | Java 7 | Java 5 |
| Phạm vi | Hợp đồng đóng tài nguyên tổng quát | Tập trung vào tài nguyên I/O |
| Chữ ký `close()` | `throws Exception` | `throws IOException` |
| Quan hệ kế thừa | Interface gốc của hợp đồng này | Mở rộng `AutoCloseable` |
| Đóng nhiều lần | Không bắt buộc phải an toàn khi gọi nhiều lần; nên thiết kế có tính lặp an toàn khi phù hợp | Hợp đồng quy định gọi `close()` khi đã đóng không có tác dụng |

Điểm khác biệt đáng chú ý là loại ngoại lệ và hợp đồng khi đóng lặp lại. `Closeable.close()` chỉ khai báo `IOException`, phù hợp với các thao tác I/O. `AutoCloseable.close()` có chữ ký tổng quát hơn nên có thể ném `Exception`; khi triển khai thực tế, nên khai báo loại ngoại lệ cụ thể nhất có thể.

Khi ghi đè một phương thức, Java không cho phép phương thức ghi đè mở rộng danh sách checked exception vượt quá hợp đồng của phương thức gốc. Vì vậy, lớp triển khai `Closeable` không thể khai báo `close() throws Exception`; nó phải tuân thủ chữ ký tương thích, chẳng hạn `throws IOException` hoặc không khai báo checked exception.

## 3. try-with-resources tự động đóng tài nguyên

Cú pháp `try-with-resources` được giới thiệu trong Java 7. Mỗi tài nguyên khai báo trong cặp ngoặc tròn phải triển khai `AutoCloseable` (bao gồm cả `Closeable`):

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
~~~

Ví dụ trên minh họa cú pháp; để chạy độc lập, chương trình cần khai báo biến `path` và xử lý `IOException`. Khi khối `try` kết thúc bình thường hoặc do ngoại lệ, Java tự động gọi `reader.close()`. Không cần tự viết khối `finally` chỉ để đóng reader.

Có thể khai báo nhiều tài nguyên, phân cách bằng dấu chấm phẩy:

~~~java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(destination)) {
    input.transferTo(output);
}
~~~

Tài nguyên được khởi tạo theo thứ tự từ trái sang phải và được đóng theo thứ tự ngược lại, tức tài nguyên được mở sau sẽ được đóng trước. Thứ tự này hữu ích khi một tài nguyên phụ thuộc vào tài nguyên khác.

Từ Java 9, có thể dùng một biến đã được khai báo bên ngoài nếu biến đó là `final` hoặc effectively final:

~~~java
BufferedReader reader = Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
~~~

Trong Java 7 và Java 8, phần khai báo tài nguyên trong `try-with-resources` phải tạo biến tài nguyên ngay trong cặp ngoặc. Ví dụ dùng biến đã khai báo trước như trên cần Java 9 trở lên.

## 4. Ngoại lệ khi đóng tài nguyên

Cách xử lý ngoại lệ là một lý do quan trọng để ưu tiên `try-with-resources`.

- Nếu thân `try` kết thúc bình thường và `close()` ném ngoại lệ, ngoại lệ từ `close()` sẽ được truyền ra ngoài.
- Nếu thân `try` đã ném ngoại lệ và `close()` cũng ném ngoại lệ, ngoại lệ từ thân `try` vẫn là ngoại lệ chính. Ngoại lệ khi đóng được gắn vào danh sách suppressed exceptions.
- Nếu có nhiều tài nguyên và nhiều lần đóng cùng ném ngoại lệ, Java vẫn đóng các tài nguyên đã khởi tạo thành công. Khi thân `try` đã có ngoại lệ chính, các ngoại lệ từ thao tác đóng được thêm vào ngoại lệ chính theo thứ tự đóng.
- Nếu việc khởi tạo một tài nguyên về sau thất bại, các tài nguyên đã khởi tạo thành công trước đó vẫn được đóng theo thứ tự ngược.

Có thể đọc các ngoại lệ bị suppressed bằng `Throwable.getSuppressed()`. Điều này giúp giữ lại lỗi ban đầu, đồng thời không làm mất thông tin về lỗi dọn dẹp tài nguyên.

Đây là ưu điểm so với cách đóng thủ công trong `finally`: nếu việc đóng trong `finally` ném ngoại lệ, nó có thể che mất ngoại lệ quan trọng phát sinh từ phần xử lý chính nếu mã không quản lý cả hai trường hợp một cách cẩn thận.

## 5. Ví dụ hoàn chỉnh: thứ tự đóng và suppressed exceptions

Lưu chương trình sau vào tệp `Main.java`. Lớp `DemoResource` triển khai `Closeable`, do đó cũng đáp ứng `AutoCloseable`. Nó in tên khi đóng và cố ý ném `IOException` để minh họa cách Java lưu ngoại lệ phụ.

~~~java
import java.io.Closeable;
import java.io.IOException;

final class DemoResource implements Closeable {
    private final String name;
    private final boolean failOnClose;

    DemoResource(String name, boolean failOnClose) {
        this.name = name;
        this.failOnClose = failOnClose;
    }

    @Override
    public void close() throws IOException {
        System.out.println("close " + name);
        if (failOnClose) {
            throw new IOException("close-" + name);
        }
    }
}

public class Main {
    public static void main(String[] args) {
        try (DemoResource first = new DemoResource("first", true);
             DemoResource second = new DemoResource("second", true)) {
            System.out.println("body");
            throw new IllegalStateException("body-failed");
        } catch (Exception e) {
            System.out.println("primary: " + e.getMessage());
            for (Throwable suppressed : e.getSuppressed()) {
                System.out.println("suppressed: " + suppressed.getMessage());
            }
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~text
javac Main.java
java Main
~~~

Đầu ra chuẩn chính xác:

~~~text
body
close second
close first
primary: body-failed
suppressed: close-second
suppressed: close-first
~~~

Giải thích:

1. Thân `try` in `body` rồi ném `IllegalStateException` với thông điệp `body-failed`. Đây là ngoại lệ chính.
2. Java đóng `second` trước vì nó được khai báo sau `first`. Phương thức `close()` in tên rồi ném `IOException`; ngoại lệ đó được lưu dưới dạng suppressed.
3. Java tiếp tục đóng `first` và cũng lưu ngoại lệ từ thao tác đóng này dưới dạng suppressed.
4. Khối `catch` nhận ngoại lệ chính và in từng ngoại lệ từ `getSuppressed()`.

Trong ví dụ này, cả hai thao tác đóng đều thất bại nhưng việc đóng tài nguyên còn lại vẫn được thực hiện. Ngoại lệ ban đầu từ thân `try` không bị thay thế bởi các ngoại lệ đóng.

## 6. Ví dụ sử dụng API I/O thật

Các lớp như `BufferedReader`, `InputStream` và `OutputStream` triển khai hợp đồng đóng phù hợp với I/O. Khi đọc tệp văn bản, có thể dùng `Files.newBufferedReader`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadFirstLine {
    public static void main(String[] args) {
        Path path = Path.of("input.txt");
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            System.out.println(reader.readLine());
        } catch (IOException e) {
            System.err.println("Không thể đọc tệp: " + e.getMessage());
        }
    }
}
~~~

Lưu đoạn mã vào `ReadFirstLine.java`, tạo tệp `input.txt` trong thư mục chạy với nội dung mong muốn, rồi biên dịch bằng `javac ReadFirstLine.java` và chạy bằng `java ReadFirstLine`. Chương trình in dòng đầu tiên của tệp; nếu tệp rỗng, `readLine()` trả về `null`. Nếu việc mở, đọc hoặc đóng tệp phát sinh `IOException`, khối `catch` xử lý lỗi.

## 7. Lỗi thường gặp và cách tránh

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Đối tượng không dùng được trong `try-with-resources` | Lớp không triển khai `AutoCloseable` hoặc một interface con như `Closeable` | Triển khai hợp đồng đóng tài nguyên phù hợp |
| Lớp triển khai `Closeable` khai báo `close() throws Exception` | Checked exception rộng hơn `IOException` không tương thích với hợp đồng | Dùng `IOException` hoặc loại hẹp hơn |
| Giả định tài nguyên được đóng theo thứ tự khai báo | Java đóng theo thứ tự ngược | Tài nguyên khởi tạo cuối cùng được đóng trước |
| Chỉ kiểm tra ngoại lệ chính | Lỗi trong `close()` có thể được lưu thành suppressed exception | Khi cần chẩn đoán, kiểm tra `getSuppressed()` |
| Đóng thủ công lần nữa mà không hiểu hợp đồng | Không phải mọi `AutoCloseable` đều bắt buộc an toàn khi đóng nhiều lần | Thiết kế quyền sở hữu rõ ràng; tuân thủ hợp đồng của từng lớp |
| Bỏ qua ngoại lệ đóng | Việc giải phóng tài nguyên có thể thất bại | Ghi log hoặc xử lý ngoại lệ theo chính sách của ứng dụng khi cần |

## 8. Quy trình áp dụng

1. Xác định tài nguyên nào cần được giải phóng và xem lớp đó có triển khai `AutoCloseable` hoặc `Closeable` hay không.
2. Chọn `try-with-resources` để bảo đảm tài nguyên đã khởi tạo được đóng tự động.
3. Khai báo tài nguyên theo thứ tự phù hợp với quan hệ phụ thuộc; Java sẽ đóng theo thứ tự ngược.
4. Xử lý loại ngoại lệ được khai báo bởi API. Với tài nguyên I/O, thường là `IOException`; API khác có thể dùng loại ngoại lệ chuyên biệt.
5. Khi cần phân tích lỗi, giữ lại ngoại lệ chính và xem cả suppressed exceptions.
6. Chỉ tự quản lý vòng đời bằng cơ chế khác khi có yêu cầu rõ ràng về quyền sở hữu hoặc thời điểm đóng.

## Ghi nhớ

`AutoCloseable` là hợp đồng tổng quát cho tài nguyên có thể đóng; `Closeable` mở rộng nó và tập trung vào I/O với `IOException`. `try-with-resources` gọi `close()` tự động, đóng tài nguyên theo thứ tự ngược với lúc khởi tạo và giữ lại lỗi đóng dưới dạng suppressed khi thân `try` đã ném ngoại lệ.