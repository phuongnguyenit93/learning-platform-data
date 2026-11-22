# Nhiều tài nguyên trong try-with-resources và thứ tự đóng ngược

Khi một thao tác cần nhiều tài nguyên như file, stream, reader, writer hoặc kết nối cơ sở dữ liệu, Java có thể quản lý chúng trong cùng một câu lệnh **try-with-resources**. Khi khối try kết thúc, Java tự gọi phương thức **close()** cho từng tài nguyên theo thứ tự ngược với thứ tự khai báo. Quy tắc này giúp giải phóng đúng các tài nguyên có quan hệ phụ thuộc.

## 1. Điều kiện để một đối tượng trở thành resource

Đối tượng được đưa vào try-with-resources phải triển khai **AutoCloseable**. Interface này định nghĩa phương thức close(). **Closeable** kế thừa AutoCloseable và thường được dùng cho tài nguyên I/O có thể phát sinh IOException khi đóng.

Ví dụ các kiểu thường gặp triển khai AutoCloseable gồm InputStream, OutputStream, Reader, Writer, BufferedReader, Connection, Statement và ResultSet. Khi rời khỏi khối try, Java chịu trách nhiệm gọi close; thông thường không cần gọi close thủ công trong thân khối.

## 2. Khai báo nhiều resource và thứ tự đóng

Có thể khai báo nhiều resource trong cùng phần đầu của try, ngăn cách bằng dấu chấm phẩy:

~~~java
try (ResourceA first = openFirst();
     ResourceB second = openSecond();
     ResourceC third = openThird()) {
    use(first, second, third);
}
~~~

Java xử lý chúng theo hai chiều:

1. **Khởi tạo từ trái sang phải:** first được tạo trước, sau đó second, rồi third.
2. **Đóng từ phải sang trái:** khi thoát khỏi try, Java đóng third trước, rồi second, cuối cùng first.

Với ba resource, thứ tự luôn là:

~~~text
Mở:  first -> second -> third
Đóng: third -> second -> first
~~~

Thứ tự đóng ngược đặc biệt hữu ích khi một tài nguyên phụ thuộc vào tài nguyên được tạo trước nó. Ví dụ, một ResultSet phụ thuộc vào Statement, còn Statement phụ thuộc vào Connection. Khai báo Connection trước, Statement sau và ResultSet cuối cùng sẽ khiến Java đóng ResultSet, Statement rồi Connection.

Nếu quá trình khởi tạo một resource ở giữa bị lỗi, thân try không chạy. Những resource đã khởi tạo thành công trước đó vẫn được đóng theo thứ tự ngược.

## 3. Ví dụ chạy được: quan sát thứ tự đóng

Lưu chương trình dưới tên **ResourceCloseOrderDemo.java**. Ví dụ dùng Java 17 trở lên và chỉ ghi lại sự kiện để quan sát thứ tự; nó không phụ thuộc vào file hay dịch vụ bên ngoài.

~~~java
import java.util.ArrayList;
import java.util.List;

public class ResourceCloseOrderDemo {

    private static final class TrackedResource implements AutoCloseable {
        private final String name;
        private final List<String> events;

        TrackedResource(String name, List<String> events) {
            this.name = name;
            this.events = events;
            events.add("open " + name);
        }

        @Override
        public void close() {
            events.add("close " + name);
        }
    }

    public static void main(String[] args) {
        List<String> events = new ArrayList<>();

        try (TrackedResource first = new TrackedResource("first", events);
             TrackedResource second = new TrackedResource("second", events);
             TrackedResource third = new TrackedResource("third", events)) {

            events.add("body");
        }

        events.forEach(System.out::println);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ResourceCloseOrderDemo.java
java ResourceCloseOrderDemo
~~~

Kết quả stdout:

~~~text
open first
open second
open third
body
close third
close second
close first
~~~

Ba resource được tạo theo thứ tự first, second, third. Sau khi thân try hoàn tất, Java đóng third, second, first. Bạn có thể thay thứ tự khai báo để thay đổi thứ tự đóng; thứ tự này được xác định bởi vị trí khai báo trong phần resource, không phụ thuộc vào tên biến.

## 4. Cú pháp Java 9: dùng biến resource đã khai báo

Từ Java 9, phần resource có thể tham chiếu đến biến đã được khai báo trước đó nếu biến đó là **final hoặc effectively final** (không bị gán lại sau khi khởi tạo). Điều này hữu ích khi một phương thức nhận quyền sở hữu các resource đã được mở ở nơi gọi hoặc khi cần dùng biến có sẵn trong try-with-resources.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public class CopyStreams {

    public static void copy(InputStream input, OutputStream output)
            throws IOException {
        try (input; output) {
            input.transferTo(output);
        }
    }
}
~~~

Đây là một lớp tiện ích biên dịch được bằng Java 9 trở lên. Hai tham số input và output không bị gán lại nên là effectively final, do đó có thể dùng trực tiếp trong phần resource. Khi phương thức kết thúc, Java đóng output trước rồi đóng input. Phương thức InputStream.transferTo(OutputStream) cũng có từ Java 9.

Phương thức trên nhận trách nhiệm đóng cả hai stream. Bên gọi cần chuyển quyền sở hữu vòng đời của chúng cho phương thức và không tiếp tục sử dụng chúng sau khi gọi. Khi tự mở nhiều resource trong cùng một phương thức, cách đơn giản và an toàn là khai báo trực tiếp trong phần đầu try:

~~~java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(target)) {
    input.transferTo(output);
}
~~~

Nếu một biến bị gán lại sau khi khởi tạo, biến đó không còn effectively final và không thể được dùng theo cú pháp try (variable). Khi cần thay đổi biến, hãy khai báo resource trực tiếp trong phần đầu try hoặc dùng một biến final/effectively final riêng.

## 5. Ngoại lệ khi đóng nhiều resource

Try-with-resources xác định rõ ngoại lệ chính và các ngoại lệ phát sinh trong lúc đóng:

- **Thân try ném ngoại lệ:** ngoại lệ từ thân try được giữ làm ngoại lệ chính. Java vẫn đóng mọi resource đã khởi tạo. Ngoại lệ từ close() được gắn vào ngoại lệ chính dưới dạng *suppressed exception*.
- **Thân try kết thúc bình thường nhưng close() lỗi:** ngoại lệ từ lần đóng đầu tiên bị lỗi trở thành ngoại lệ được ném ra. Nếu những lần đóng tiếp theo cũng lỗi, các ngoại lệ đó được thêm vào danh sách suppressed của ngoại lệ chính.
- **Khởi tạo resource lỗi:** những resource đã khởi tạo thành công trước thời điểm lỗi vẫn được đóng. Nếu việc đóng chúng cũng lỗi, các lỗi đóng được giữ dưới dạng suppressed trên ngoại lệ khởi tạo.

Có thể xem các ngoại lệ bị suppressed bằng Throwable.getSuppressed(). Điều này giúp giữ lại lỗi gốc mà không làm mất các lỗi phát sinh trong quá trình dọn dẹp.

Ví dụ sau cho thấy ngoại lệ của thân try vẫn là ngoại lệ chính, còn lỗi khi đóng được giữ lại theo đúng thứ tự đóng:

~~~java
import java.io.IOException;

public class SuppressedCloseDemo {

    private static final class FailingResource implements AutoCloseable {
        private final String name;

        FailingResource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            throw new IOException("close " + name);
        }
    }

    public static void main(String[] args) {
        try (FailingResource first = new FailingResource("first");
             FailingResource second = new FailingResource("second")) {

            throw new IOException("body");
        } catch (IOException exception) {
            System.out.println("primary: " + exception.getMessage());

            for (Throwable suppressed : exception.getSuppressed()) {
                System.out.println("suppressed: " + suppressed.getMessage());
            }
        }
    }
}
~~~

Kết quả stdout:

~~~text
primary: body
suppressed: close second
suppressed: close first
~~~

Thân try ném lỗi body. Java đóng second trước nên lỗi close second được thêm trước; tiếp đó đóng first và thêm lỗi close first. Cả hai lỗi đóng đều được giữ lại, trong khi lỗi body vẫn là ngoại lệ chính.

## 6. Chọn thứ tự khai báo đúng trong thực tế

Khi sắp xếp nhiều resource, hãy xác định quan hệ phụ thuộc và khai báo theo thứ tự từ tài nguyên nền tảng đến tài nguyên phụ thuộc:

- Với JDBC, khai báo Connection trước, PreparedStatement sau và ResultSet cuối cùng. Thứ tự đóng sẽ là ResultSet, PreparedStatement, Connection.
- Với các resource độc lập, chọn thứ tự khai báo rõ ràng và dễ đọc; Java vẫn đóng chúng theo chiều ngược.
- Nếu một wrapper tự đóng tài nguyên bên dưới của nó, hãy hiểu rõ hợp đồng close() của wrapper trước khi đăng ký cả wrapper và tài nguyên bên dưới thành hai resource riêng. Tránh đóng lặp khi API không bảo đảm thao tác đó an toàn.

Một số nguyên tắc thực hành:

1. Dùng try-with-resources cho mọi tài nguyên có vòng đời cần kết thúc bằng close().
2. Đặt resource phụ thuộc sau resource mà nó cần, để nó được đóng trước.
3. Không gọi close() thủ công trong thân try trừ khi API yêu cầu kết thúc sớm một cách rõ ràng; nếu đóng sớm, cần hiểu rằng Java vẫn sẽ gọi close() khi thoát khỏi try.
4. Khi xử lý lỗi, kiểm tra getSuppressed() nếu cần tìm nguyên nhân phát sinh trong quá trình đóng.
5. Chỉ đưa vào phần resource những đối tượng có triển khai AutoCloseable và có quyền sở hữu vòng đời mà khối try cần quản lý.

## 7. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ rằng resource đóng theo thứ tự khai báo | Tài nguyên phụ thuộc có thể bị đóng quá muộn hoặc tài nguyên nền tảng bị đóng trước | Nhớ quy tắc đóng từ phải sang trái |
| Khai báo resource phụ thuộc trước resource nền tảng | Thứ tự đóng có thể đi ngược quan hệ phụ thuộc | Khai báo resource nền tảng trước |
| Dùng biến đã bị gán lại trong cú pháp Java 9 try (variable) | Lỗi biên dịch vì biến không còn effectively final | Không gán lại biến hoặc khai báo resource trong phần đầu try |
| Chỉ xem ngoại lệ chính và bỏ qua suppressed | Bỏ sót lỗi phát sinh khi đóng resource | Kiểm tra Throwable.getSuppressed() khi chẩn đoán |
| Đăng ký cả wrapper và đối tượng bên dưới mà không kiểm tra hợp đồng đóng | Có thể gọi close() nhiều lần trên cùng tài nguyên | Kiểm tra tài liệu API và quyền sở hữu resource |

## 8. Ghi nhớ

- Nhiều resource có thể nằm trong một try-with-resources, phân tách bằng dấu chấm phẩy.
- Java khởi tạo resource từ trái sang phải và đóng chúng từ phải sang trái.
- Resource khai báo sau được đóng trước; hãy dùng quy tắc này để xử lý đúng quan hệ phụ thuộc.
- Java 9 cho phép dùng biến resource đã khai báo nếu biến là final hoặc effectively final.
- Ngoại lệ từ thân try được ưu tiên làm ngoại lệ chính; lỗi khi đóng được giữ trong getSuppressed().
- Cơ chế này áp dụng cho các kiểu triển khai AutoCloseable và vẫn là cách quản lý vòng đời tài nguyên hiện hành trong Java.
