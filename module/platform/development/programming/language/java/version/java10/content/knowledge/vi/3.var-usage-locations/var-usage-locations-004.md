# `var` trong khai báo tài nguyên của `try-with-resources` (Java 10+)

## 1. Hiểu đúng mục đích của bài

Từ Java 10, bạn có thể dùng `var` khi **khai báo tài nguyên trực tiếp trong dấu ngoặc của `try-with-resources`**. Trình biên dịch suy ra kiểu tĩnh của biến tài nguyên từ biểu thức khởi tạo; cơ chế đóng tài nguyên tự động vẫn là cơ chế `try-with-resources` vốn có của Java.

Bài này giúp bạn:
- Viết đúng cú pháp `try (var resource = ...)` và biết khi nào `var` được chấp nhận.
- Giải thích kiểu tài nguyên suy ra tại compile time và điều kiện phải tương thích `AutoCloseable`.
- Hiểu thời điểm đóng, thứ tự đóng nhiều tài nguyên và xử lý ngoại lệ khi đóng.
- Phân biệt khai báo `var` ngay trong `try` với việc sử dụng biến đã có từ bên ngoài.
- Áp dụng cho đọc tệp và `Files.lines(...)` theo cách còn phù hợp với Java hiện đại.

**Phạm vi phiên bản:** `try-with-resources` có từ Java 7; Java 9 cho phép dùng một biến tài nguyên đã có nếu biến đó `final` hoặc *effectively final*; **Java 10** bổ sung suy luận kiểu `var` cho khai báo biến cục bộ, bao gồm khai báo tài nguyên trong `try`. Tất cả ví dụ chạy độc lập ở đây dùng cú pháp phù hợp JDK 17+.

## 2. Cú pháp và quy tắc suy luận kiểu

Khai báo kiểu tường minh:

~~~java
try (java.io.BufferedReader reader = java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
~~~

Viết tương đương với `var`:

~~~java
try (var reader = java.nio.file.Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
~~~

*Hai đoạn trên là ví dụ ở bên trong phương thức đã có biến `path` kiểu `Path`; phần 3 có chương trình chạy độc lập.*

Ở đoạn thứ hai:
1. `Files.newBufferedReader(path)` được khai báo trả về `BufferedReader`.
2. Trình biên dịch suy ra kiểu **`BufferedReader`** cho `reader`.
3. `BufferedReader` triển khai `Closeable`, mà `Closeable` mở rộng `AutoCloseable`; do đó đây là kiểu tài nguyên hợp lệ.
4. Sau khi khối `try` kết thúc theo luồng thực thi thông thường (kể cả ném ngoại lệ), Java tự gọi `close()` cho tài nguyên đã khởi tạo thành công.

`var` là cú pháp **suy luận kiểu tĩnh**, không phải kiểu động, không bỏ qua trình kiểm tra kiểu và không thay thế điều kiện `AutoCloseable`.

Ví dụ `try (var reader = ...)` tương ứng với khai báo `BufferedReader reader` trong phạm vi tài nguyên. Bạn có thể gọi `reader.readLine()` vì phương thức đó thuộc kiểu tĩnh được suy ra.

**Quy tắc cần nhớ:** mỗi khai báo `var` cần một biểu thức khởi tạo phù hợp; kiểu được suy ra từ **kiểu biểu thức khi biên dịch**, không dựa vào lớp của đối tượng lúc chạy.

## 3. Ví dụ hoàn chỉnh: đọc tệp UTF-8 với `var`

Tạo tệp **VarTryWithResourcesDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class VarTryWithResourcesDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("java-var-resource-", ".txt");

        try {
            Files.writeString(
                    path,
                    "Java 10\nJava 17\n",
                    StandardCharsets.UTF_8
            );

            try (var reader = Files.newBufferedReader(
                    path, StandardCharsets.UTF_8)) {

                String line;
                while ((line = reader.readLine()) != null) {
                    System.out.println(line);
                }
            }

            System.out.println("Da dong reader tu dong");
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac VarTryWithResourcesDemo.java
java VarTryWithResourcesDemo
~~~

**Đầu ra khi đọc/ghi tệp thành công:**

~~~text
Java 10
Java 17
Da dong reader tu dong
~~~

Giải thích từng bước:
- `Files.createTempFile(...)` tạo một tệp tạm để ví dụ không phụ thuộc vào tệp có sẵn trên máy. `Files.writeString(..., UTF_8)` ghi hai dòng.
- `Files.newBufferedReader(path, UTF_8)` mở tài nguyên đọc và trả về `BufferedReader`; `var reader` được suy ra đúng kiểu này.
- Vòng `while` đọc đến khi `readLine()` trả về `null`; điều đó biểu thị hết dữ liệu, **không** có nghĩa trình đọc đã đóng.
- Ngay khi thoát khỏi khối `try (var reader = ...)`, Java tự đóng `reader` trước khi in thông báo kế tiếp. Không cần `reader.close()` thủ công trong khối.
- Khối `finally` bên ngoài dùng để xóa **tệp tạm** do ví dụ tạo ra; đây là một việc khác với đóng `BufferedReader`.
- `throws IOException` ở `main` cho phép ví dụ tập trung vào `try-with-resources`; trong ứng dụng thực tế, cân nhắc `catch`, ghi log hoặc trả lỗi phù hợp.

Cả việc mở, đọc và đóng reader đều có thể phát sinh `IOException`; **dùng `var` không làm mất yêu cầu xử lý checked exception**.

## 4. Tài nguyên nào dùng được và tài nguyên nào không?

Điều kiện của khai báo tài nguyên trong `try-with-resources`: **kiểu tĩnh được khai báo hoặc được suy ra phải là kiểu con của `AutoCloseable`**.

Những dạng thường gặp:

| Biểu thức khởi tạo | Kiểu suy ra bằng `var` | Hợp lệ trong `try-with-resources`? | Lý do |
| --- | --- | --- | --- |
| `Files.newBufferedReader(path)` | `BufferedReader` | Có | Implements `Closeable` |
| `Files.newInputStream(path)` | `InputStream` | Có | `InputStream` implements `Closeable` |
| `Files.lines(path)` | `Stream<String>` | Có | `Stream` kế thừa `BaseStream`, có `close()` thông qua `AutoCloseable` |
| `new StringBuilder()` | `StringBuilder` | Không | Không implements `AutoCloseable` |
| `"hello"` | `String` | Không | `String` không implements `AutoCloseable` |
| `null` | Không suy ra được kiểu | Không | `var` không suy ra kiểu chỉ từ `null` |

Ví dụ **cố ý không biên dịch**:

~~~java
try (var text = "hello") {
    System.out.println(text);
}
// error: String is not a subtype of AutoCloseable
~~~

Ví dụ khác (**cố ý không biên dịch**):

~~~java
try (var reader = null) {
    // ...
}
// error: cannot infer type for local variable reader
~~~

Vì điều kiện `AutoCloseable` được kiểm tra bằng kiểu tĩnh, kiểu **trả về được khai báo** của factory method rất quan trọng. Chẳng hạn, nếu `open()` được khai báo trả về `AutoCloseable` thì `var resource = open()` suy ra `AutoCloseable`, ngay cả khi đối tượng thực tế là `BufferedReader`. Bạn sẽ không gọi trực tiếp được `resource.readLine()` bởi `AutoCloseable` không có phương thức đó.

`AutoCloseable.close()` khai báo `throws Exception`; các kiểu cụ thể như `Closeable` giới hạn ngoại lệ ở mức `IOException`. Nếu biến suy ra là `AutoCloseable`, việc xử lý checked exception lúc đóng có thể rộng hơn so với kiểu `BufferedReader`.

## 5. Cơ chế tự đóng và thứ tự đóng nhiều tài nguyên

Khi có nhiều tài nguyên, ngăn cách **các khai báo trong ngoặc `try` bằng dấu chấm phẩy**. Java khởi tạo từ trái sang phải và tự đóng theo **thứ tự ngược lại**.

Tạo tệp **VarCloseOrderDemo.java**:

~~~java
public class VarCloseOrderDemo {
    static final class TrackedResource implements AutoCloseable {
        private final String name;

        TrackedResource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (var first = new TrackedResource("A");
             var second = new TrackedResource("B")) {
            System.out.println("body");
        }
    }
}
~~~

Chạy:

~~~bash
javac VarCloseOrderDemo.java
java VarCloseOrderDemo
~~~

Kết quả:

~~~text
open A
open B
body
close B
close A
~~~

Điều này còn đúng khi:
- Khối `try` kết thúc bằng `return`, `break` hoặc `continue` (trong ngữ cảnh tương ứng).
- Khối `try` ném ngoại lệ: các tài nguyên đã mở vẫn được đóng theo thứ tự ngược.
- Tài nguyên thứ hai không khởi tạo thành công: tài nguyên thứ nhất đã mở trước đó vẫn được đóng; tài nguyên thứ hai chưa được khởi tạo thành công thì không có giá trị để đóng.

Nếu tài nguyên khởi tạo trả về `null`, cơ chế đóng tự động bỏ qua giá trị `null`; tuy nhiên truy cập tài nguyên đó trong thân `try` vẫn có thể gây `NullPointerException`. Thiết kế factory để trả về tài nguyên hợp lệ hoặc thất bại rõ ràng thường dễ kiểm soát hơn.

**Lưu ý phạm vi:** các biến `first`, `second` của khai báo trong ngoặc `try` chỉ tồn tại trong phạm vi của câu lệnh `try-with-resources`. Chúng không dùng được sau câu lệnh `try`.

## 6. Ngoại lệ khi đóng tài nguyên: suppressed exceptions

Giả sử thân `try` ném một ngoại lệ, rồi `close()` cũng ném ngoại lệ. Java giữ ngoại lệ từ thân `try` làm **ngoại lệ chính**; ngoại lệ từ `close()` được đính kèm vào danh sách **suppressed**. Bạn truy xuất bằng `Throwable.getSuppressed()`.

Tạo tệp **VarSuppressedDemo.java**:

~~~java
public class VarSuppressedDemo {
    static final class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            throw new Exception("close failed");
        }
    }

    public static void main(String[] args) {
        try (var resource = new BrokenResource()) {
            throw new IllegalStateException("body failed");
        } catch (Exception ex) {
            System.out.println("primary: " + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed: " + suppressed.getMessage());
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac VarSuppressedDemo.java
java VarSuppressedDemo
~~~

Đầu ra:

~~~text
primary: body failed
suppressed: close failed
~~~

Trong tình huống **thân `try` không ném ngoại lệ**, nếu `close()` ném ngoại lệ thì ngoại lệ đóng có thể trở thành ngoại lệ được truyền ra. Nếu nhiều `close()` cùng thất bại, cách lưu các lỗi đóng phụ thuộc vào thứ tự đóng và ngoại lệ chính tại thời điểm đó; khi điều tra sự cố I/O, cần kiểm tra cả `getSuppressed()`.

Đây là cơ chế của `try-with-resources` nói chung; **`var` không thay đổi cách xử lý ngoại lệ**. Với `Files.newBufferedReader(...)`, chỉ cần xử lý `IOException` theo đúng hợp đồng API; không thêm `catch` rộng chỉ vì chọn `var`.

## 7. Phân biệt hai cách dùng `var` với tài nguyên

### Cách A: khai báo ngay trong ngoặc `try` (điểm chính của Java 10)

~~~java
try (var reader = Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
// reader ở trên không còn trong phạm vi sử dụng.
~~~

Cách này gom **khai báo, sở hữu và đóng** tài nguyên vào một phạm vi nhỏ; dễ thấy tài nguyên được giải phóng khi nào.

### Cách B: biến khai báo trước `try`, rồi truyền biến vào `try`

~~~java
var reader = Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
// Biến reader vẫn nằm trong scope, nhưng tài nguyên đã đóng.
~~~

Hai đoạn trên là **mã minh họa bên trong một phương thức có `Path path` và khai báo/import `Files`**, không phải các tệp độc lập.

Ở cách B, `var` nằm trong một khai báo biến cục bộ thông thường; phần `try (reader)` sử dụng **biến đã tồn tại**, là cú pháp hỗ trợ từ Java 9. Biến đó phải là `final` hoặc **effectively final**: sau khi nhận giá trị ban đầu, không được gán lại nó nếu muốn dùng trong `try (reader)`.

Cả hai đều đóng tài nguyên tự động, nhưng cách B khiến biến vẫn tồn tại sau `try`. Cần tránh tái sử dụng reader sau khi đã đóng; vì thế với tài nguyên mới tạo riêng để dùng trong một khối, cách A thường rõ ràng hơn.

**Ghi chú:** khai báo tài nguyên trong ngoặc `try` (dùng `var` hay kiểu tường minh) là biến không được gán lại. Điều này phục vụ quy tắc quản lý tài nguyên, không phải vì mọi biến cục bộ khai báo `var` đều bất biến. Biến `var` bình thường ngoài `try` vẫn được phép gán lại nếu tương thích kiểu.

## 8. Ứng dụng thực tế: đóng `Stream` từ `Files.lines()`

`Files.lines(path)` mở tệp và trả về một `Stream<String>` có tài nguyên I/O bên dưới. Với trường hợp này, bạn nên đóng stream sau khi duyệt xong:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class VarFilesLinesDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("java-lines-", ".txt");

        try {
            Files.writeString(
                    path,
                    "Java\n\nSpring\n",
                    StandardCharsets.UTF_8
            );

            try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
                lines.filter(line -> !line.isBlank())
                     .forEach(System.out::println);
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

Tạo tệp **VarFilesLinesDemo.java**, rồi chạy:

~~~bash
javac VarFilesLinesDemo.java
java VarFilesLinesDemo
~~~

Kết quả:

~~~text
Java
Spring
~~~

`lines` được suy ra là `Stream<String>`. Dữ liệu chỉ được đọc khi duyệt pipeline, và `close()` giải phóng tài nguyên mở bởi `Files.lines(...)`. Một điểm quan trọng: không phải mọi stream đều nắm giữ tài nguyên I/O; stream thuần trong bộ nhớ như `List.of(...).stream()` không cần dùng `try-with-resources` chỉ để đóng.

Nếu cần xử lý cả tệp nhưng không muốn giữ toàn bộ nội dung trong bộ nhớ, `Files.lines(...)` hoặc `BufferedReader` theo `try-with-resources` là những cách đọc phổ biến. Chọn cách phù hợp với yêu cầu xử lý dòng, quản lý lỗi và lượng dữ liệu.

## 9. Các lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai hoặc dễ gây lỗi | Cách viết phù hợp |
| --- | --- | --- |
| `try (var resource)` với biến chưa tồn tại | `var` đòi hỏi khai báo kèm initializer; không phải tên kiểu hay biến đã có | `try (var resource = open())` khi `open()` trả về `AutoCloseable` |
| `try (var reader = null)` | Không suy ra được kiểu từ `null` | Khởi tạo từ factory có kiểu tài nguyên cụ thể |
| `try (var text = "hello")` | Kiểu suy ra `String` không thực thi `AutoCloseable` | Chỉ dùng với tài nguyên thực sự đóng được |
| Viết hai khai báo tài nguyên bằng dấu phẩy | Cú pháp danh sách tài nguyên dùng dấu chấm phẩy | `try (var a = openA(); var b = openB())` |
| Gán lại biến tài nguyên trong thân `try` | Biến tài nguyên khai báo trong ngoặc `try` không được gán lại | Dùng biến khác cho dữ liệu xử lý |
| Gọi `reader.readLine()` sau khi đóng | Biến có thể còn trong scope nếu khai báo ngoài, nhưng tài nguyên đã đóng | Chỉ đọc trong khối `try` |
| Quên checked exception khi mở/đọc/đóng | `var` không miễn trừ `IOException` | `catch (IOException e)` hoặc khai báo `throws IOException` khi phù hợp |
| Bắt lỗi nhưng bỏ qua suppressed | Mất thông tin lỗi phát sinh lúc đóng nếu thân `try` cũng thất bại | Kiểm tra `getSuppressed()` khi điều tra lỗi |
| Dùng `var` cho kết quả factory có kiểu quá rộng | Kiểu suy ra quá rộng, không gọi được API đặc thù của đối tượng runtime | Thiết kế/chọn API trả về kiểu đủ cụ thể hoặc dùng kiểu tường minh thích hợp |

`try-with-resources` không phải công cụ quản lý **mọi** loại đối tượng; nó được thiết kế cho những tài nguyên có hành vi `close()`. Không cần cố gắng biến `String`, `ArrayList` hoặc đối tượng không quản lý tài nguyên thành `AutoCloseable` để dùng cú pháp này.

**Một vấn đề riêng về ownership:** khi `try-with-resources` kết thúc, tài nguyên đưa vào sẽ bị đóng. Tránh đưa một tài nguyên còn được thành phần khác sử dụng vào `try` nếu code của bạn không chịu trách nhiệm đóng nó; dùng ranh giới sở hữu rõ ràng để tránh đóng sớm.

## 10. Câu hỏi tự kiểm tra

**1. `try (var r = Files.newBufferedReader(path))` suy ra kiểu nào?**  
`BufferedReader`, dựa trên kiểu trả về được khai báo của `Files.newBufferedReader`, không dựa vào nội dung tệp.

**2. `var` có cho phép `String` trở thành resource không?**  
Không. Tài nguyên vẫn phải có kiểu tĩnh tương thích `AutoCloseable`.

**3. Hai tài nguyên A và B được khai báo theo thứ tự A rồi B thì đóng theo thứ tự nào?**  
B trước, A sau.

**4. Khi thân `try` và `close()` đều ném ngoại lệ, kiểm tra lỗi đóng ở đâu?**  
Trong các ngoại lệ bị suppressed của ngoại lệ chính, dùng `getSuppressed()`.

**5. `try (reader)` khác gì `try (var reader = ...)`?**  
`try (reader)` sử dụng biến đã khai báo trước đó và biến này phải final/effectively final. `try (var reader = ...)` khai báo, suy ra kiểu và quản lý biến tài nguyên ngay trong ngoặc `try`.

**6. Có cần `try-with-resources` cho `List.of("A").stream()` không?**  
Thông thường không: stream đó không nắm giữ tài nguyên I/O cần giải phóng. Với `Files.lines(path)`, nên sử dụng vì stream có tài nguyên tệp bên dưới.

## 11. Ghi nhớ trọng tâm

`try (var resource = expression)` là cách viết ngắn gọn của một khai báo tài nguyên có **kiểu tĩnh suy ra được**. Điều kiện `AutoCloseable`, thứ tự đóng, xử lý `IOException` và suppressed exceptions đều **không thay đổi** vì `var`. Hãy chọn `var` khi kiểu hiển nhiên từ factory và phạm vi tài nguyên đủ hẹp để người đọc thấy rõ ai mở, ai dùng và ai đóng tài nguyên.
