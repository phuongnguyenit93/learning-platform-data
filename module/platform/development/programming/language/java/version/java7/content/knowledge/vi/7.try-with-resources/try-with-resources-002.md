# Khai báo tài nguyên trong phần mở đầu `try` — Java 7 và Java hiện hành

## 1. Mục tiêu học tập

`try-with-resources` là cú pháp quản lý vòng đời tài nguyên có từ Java 7 và **vẫn là cách làm được khuyến nghị** khi làm việc với file, luồng I/O, kết nối JDBC, socket và các đối tượng cần đóng. Thay vì nhớ gọi `close()` ở nhiều nhánh thành công/lỗi, chương trình khai báo tài nguyên trong phần mở đầu `try (...)`; Java sẽ đóng chúng khi kết thúc câu lệnh `try-with-resources` theo ngữ nghĩa được đặc tả.

Bài này tập trung vào **cách khai báo tài nguyên trong phần mở đầu `try`**. Sau khi học, bạn có thể:

- Viết đúng dạng `try (ResourceType name = initializer) { ... }` và khai báo nhiều resource bằng dấu chấm phẩy.
- Xác định loại đối tượng hợp lệ: phải triển khai `AutoCloseable`; phân biệt nó với biến, dữ liệu hoặc đường dẫn không cần đóng.
- Giải thích **initializer bắt buộc**, biến resource `final` ngầm, phạm vi biến và lý do không được gán lại.
- Phân biệt cách **khai báo mới trong header** (Java 7+) với cách **tham chiếu biến đã có** nhưng `final`/effectively final (Java 9+), và cách dùng `var` (Java 10+).
- Dự đoán thứ tự **khởi tạo trái → phải**, **đóng phải → trái**, kể cả khi một initializer lỗi; hiểu cách exception phát sinh khi đóng.
- Viết và chạy ví dụ Java 17+ độc lập, phân biệt với những đoạn mã **cố ý sai cú pháp/không thể biên dịch**.

**Phạm vi hiện hành:** Java 7 được dùng làm mốc ra đời của tính năng. Hợp đồng thực tế đối chiếu với [Java Language Specification (JLS) Java SE 26 §14.20.3](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.20.3). Không áp dụng máy móc các giới hạn cú pháp cũ cho mã đang chạy Java 17/21/25/26.

## 2. Cấu trúc phần mở đầu `try`

Mẫu một tài nguyên:

~~~java
try (BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    // Sử dụng reader tại đây.
}
~~~

Đây là **đoạn minh họa bên trong phương thức**, với `path` đã được khai báo và các lớp được import. Dòng trong dấu ngoặc tròn gồm:

1. **Kiểu tài nguyên** `BufferedReader`: class này thực thi `Closeable`, mà `Closeable` mở rộng `AutoCloseable`.
2. **Tên biến** `reader`: có thể truy cập trong phần còn lại của header và thân `try`.
3. Dấu `=` và **biểu thức khởi tạo**: `Files.newBufferedReader(...)` tạo/mở resource trước khi phần thân `try` chạy.
4. **Dấu ngoặc tròn** sau `try`: chỉ phần quản lý resource; nó khác `try { ... } catch (...)` thông thường.
5. **Thân `{ ... }`**: nơi dùng resource. Khi thoát thân này bằng đường bình thường, `return` hay exception, Java vẫn chạy bước đóng resource.

Cách trình bày nhiều resource:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
}
~~~

Đây là đoạn mã **trong một phương thức** với `source`/`target` kiểu `Path`, có import `java.io.*` và `java.nio.file.*`, dùng Java 17+. Hai tài nguyên được phân tách bằng **dấu `;`**, mỗi tài nguyên có **kiểu, tên và initializer riêng**. Dấu `;` cuối cùng trước `)` là tùy chọn:

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target);) {
    in.transferTo(out);
}
~~~

Hai mẫu trên tương đương về khai báo tài nguyên. Không thay dấu `;` bằng dấu phẩy giữa hai declarator. `transferTo` là phương thức của `InputStream` có từ Java 9, được dùng ở đây vì code mẫu nhắm Java 17+, **không phải cú pháp Java 7**.

Một `try-with-resources` cần **ít nhất một resource** trong header. Với dạng cơ bản, có thể không cần `catch` hoặc `finally`; phải xử lý/khai báo các checked exception còn khả năng phát sinh theo quy tắc thông thường của Java.

## 3. Điều kiện để một khai báo resource hợp lệ

JLS hiện hành §14.20.3 quy định một khai báo resource phải thỏa các điểm chính sau:

| Điều kiện | Hợp lệ | Không hợp lệ và lý do |
| --- | --- | --- |
| Kiểu resource là subtype của `AutoCloseable` | `BufferedReader`, `InputStream`, `Connection`, class tự viết có `implements AutoCloseable` | `String`, `Path`, `List<String>`: bản thân những kiểu này không triển khai `AutoCloseable` |
| Một khai báo resource có initializer | `BufferedReader r = Files.newBufferedReader(path)` | `BufferedReader r`: thiếu initializer trong khai báo header |
| Một resource là một declarator riêng | `Reader a = ...; Reader b = ...` | `Reader a = ..., b = ...`: không hợp lệ với quy tắc một declarator trong mỗi khai báo resource |
| Biến được khai báo là `final` ngầm | `try (Reader r = ...) { r.read(); }` | `r = anotherReader;` trong thân `try`: không được gán lại |
| Tên trong các khai báo không xung đột | `Reader first = ...; Reader second = ...` | Khai báo hai resource trùng tên trong cùng header |
| Có nguồn để quản lý vòng đời | Luồng file/reader/connection cần đóng | Dùng `try-with-resources` chỉ để bọc chuỗi hoặc giá trị thuần không cần đóng |

**Vì sao cần `AutoCloseable`?** Bởi Java cần gọi phương thức `close()` theo một hợp đồng chung. Một class có phương thức tên `close()` nhưng **không implement `AutoCloseable`** vẫn không đủ điều kiện: yêu cầu được kiểm tra theo kiểu tĩnh của biến. `Closeable` là một giao diện con của `AutoCloseable`, thường gặp trong I/O; nó không phải là yêu cầu bắt buộc riêng của câu lệnh `try`.

Nếu một initializer trả về `null`, resource có thể được gán `null`, nhưng Java **bỏ qua lời gọi `close()`** với giá trị này. Điều đó không làm `null` trở thành resource hữu ích; việc mở resource thành công và kiểm tra giá trị vẫn là trách nhiệm API/ứng dụng.

### 3.1. Biến resource là `final` ngầm

Các khai báo sau có cùng quy tắc không gán lại biến:

~~~java
try (BufferedReader r = Files.newBufferedReader(path)) {
    System.out.println(r.readLine());
}
~~~

~~~java
try (final BufferedReader r = Files.newBufferedReader(path)) {
    System.out.println(r.readLine());
}
~~~

Đây là **hai đoạn minh họa độc lập** bên trong phương thức có thể ném `IOException`, với `path` kiểu `Path`. Viết `final` tường minh là tùy chọn, bởi compiler đã coi resource khai báo trong header là `final`.

Mẫu sai:

~~~java
try (BufferedReader r = Files.newBufferedReader(path)) {
    r = Files.newBufferedReader(otherPath); // LỖI COMPILE
}
~~~

Dòng gán lại bị từ chối. Nếu muốn sử dụng hai resource, **khai báo hai biến** với tên khác nhau, hoặc mở một `try-with-resources` mới cho tài nguyên mới. Không coi `final` là “đối tượng bất biến”: bản thân reader vẫn có trạng thái đọc; `final` chỉ ngăn biến tham chiếu sang đối tượng khác.

### 3.2. Phạm vi biến trong header và thân `try`

Một resource được **khai báo** trong header có phạm vi từ khai báo của nó, qua các khai báo phía sau trong header, đến hết **thân `try`**. Nó không là biến có phạm vi trực tiếp trong `catch`/`finally` cùng cấp, và cũng không truy cập được sau toàn bộ câu lệnh này.

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    System.out.println(reader.readLine()); // Hợp lệ
} catch (IOException ex) {
    System.out.println(ex.getMessage());   // Hợp lệ
    // reader.readLine();                   // LỖI: reader ngoài phạm vi
}
// reader.readLine();                       // LỖI: ngoài phạm vi
~~~

Đây là đoạn minh họa với `path` và imports đã có. Nếu cần metadata của lỗi trong `catch`, hãy truyền dữ liệu phù hợp ra ngoài hoặc sử dụng ngoại lệ; **không cố lấy lại resource đã đóng**.

Resource khai báo ở đầu header có thể được dùng khi khởi tạo resource ở bên phải, với điều kiện API cho phép. Ví dụ ý tưởng (đây là đoạn trong phương thức):

~~~java
try (InputStream source = Files.newInputStream(path);
     BufferedInputStream buffer = new BufferedInputStream(source)) {
    System.out.println(buffer.read());
}
~~~

Ở đây `source` có thể tham chiếu từ initializer của `buffer`. Khi đóng, Java đóng `buffer` trước rồi đóng `source`; có thể xảy ra lời gọi đóng lặp ở tầng wrapper, do `BufferedInputStream.close()` thường đã đóng stream nền. Trong thực tế, khi **wrapper sở hữu stream nền**, thường chỉ cần khai báo wrapper là resource quản lý chính để giảm số lần đóng không cần thiết:

~~~java
try (BufferedInputStream buffer =
         new BufferedInputStream(Files.newInputStream(path))) {
    System.out.println(buffer.read());
}
~~~

Việc sở hữu và đóng stream nền vẫn cần được xác nhận theo hợp đồng của wrapper cụ thể. Không mặc định mọi wrapper hay thư viện tùy biến đều sở hữu resource được truyền vào.

## 4. Ví dụ Java 17+: thứ tự khởi tạo và đóng nhiều resource

Tạo file `ResourceHeaderDemo.java`:

~~~java
public class ResourceHeaderDemo {
    static final class Trace implements AutoCloseable {
        private final String name;

        Trace(String name) {
            this.name = name;
            System.out.println("open:" + name);
        }

        void use() {
            System.out.println("use:" + name);
        }

        @Override
        public void close() {
            System.out.println("close:" + name);
        }
    }

    public static void main(String[] args) {
        try (Trace left = new Trace("A");
             Trace right = new Trace("B");) {
            left.use();
            right.use();
        }
        System.out.println("after");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ResourceHeaderDemo.java
java ResourceHeaderDemo
~~~

Stdout:

~~~text
open:A
open:B
use:A
use:B
close:B
close:A
after
~~~

Giải thích chính xác:

- Hai initializer được đánh giá **từ trái sang phải**: `left` mở trước `right`.
- Thân `try` chỉ bắt đầu khi cả hai đã khởi tạo thành công; nó sử dụng `left` rồi `right` theo thứ tự code viết.
- Java đóng các resource được quản lý **theo thứ tự ngược lại**: `right.close()` trước, `left.close()` sau.
- Dòng `after` chỉ được thực thi **sau khi các thao tác đóng hoàn tất**. Việc dùng dấu `;` cuối header không ảnh hưởng thứ tự.
- `Trace implements AutoCloseable` có `close()` không khai báo checked exception, nên ví dụ không phải bắt hoặc khai báo `Exception`.

Quy tắc đóng ngược thứ tự rất hữu ích khi resource thứ hai **phụ thuộc** tài nguyên thứ nhất: đối tượng phụ thuộc được đóng trước khi đối tượng nền được đóng.

## 5. Nếu initializer giữa chừng thất bại

Khởi tạo resource thứ hai có thể ném ngoại lệ. Lúc đó **thân `try` không chạy**, nhưng Java vẫn đóng các resource đã được khởi tạo thành công ở phía trước. Resource chưa khởi tạo thành công không được đóng bằng một tham chiếu mà nó chưa nhận được.

Tạo file `InitFailureDemo.java`:

~~~java
import java.io.IOException;

public class InitFailureDemo {
    static final class Resource implements AutoCloseable {
        final String name;

        Resource(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            System.out.println("close:" + name);
        }
    }

    static Resource open(String name, boolean fail) throws IOException {
        System.out.println("init:" + name);
        if (fail) {
            throw new IOException("init failed:" + name);
        }
        return new Resource(name);
    }

    public static void main(String[] args) {
        try (Resource first = open("one", false);
             Resource second = open("two", true)) {
            System.out.println("body");
        } catch (IOException ex) {
            System.out.println("caught:" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 InitFailureDemo.java
java InitFailureDemo
~~~

Stdout:

~~~text
init:one
init:two
close:one
caught:init failed:two
~~~

- `first` đã được khởi tạo trước.
- `open("two", true)` ném `IOException`, nên lệnh `System.out.println("body")` không chạy.
- Trước khi chuyển tới `catch`, Java tự gọi `first.close()`. Không có resource thứ hai để đóng vì initializer thứ hai chưa trả về đối tượng.
- `catch (IOException)` nhận lỗi từ **initializer**, cho thấy ngoại lệ ở phần mở đầu `try` thuộc phạm vi xử lý của các `catch` đi kèm.

Nếu bước mở resource có thể **mở một tài nguyên rồi ném lỗi trước khi trả về tham chiếu**, chính hàm mở cần có chính sách dọn dẹp phần mở dở. `try-with-resources` chỉ tự đóng các resource đã khởi tạo thành công và được đăng ký theo ngữ nghĩa header, không sửa được mọi lỗi quản lý tài nguyên **bên trong initializer tùy biến**.

## 6. Tài nguyên khai báo trước `try`: mở rộng từ Java 9

Cú pháp **ban đầu ở Java 7** yêu cầu *khai báo biến resource ngay trong header*:

~~~java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    System.out.println(reader.readLine());
}
~~~

Từ **Java 9**, một biến đã có bên ngoài cũng có thể xuất hiện trực tiếp trong header nếu biến đó đã được gán trước và là **`final` hoặc effectively final**:

~~~java
BufferedReader reader = Files.newBufferedReader(path);
try (reader) {
    System.out.println(reader.readLine());
}
~~~

Đây đều là **đoạn mã trong một phương thức**, không phải các class tự chạy độc lập. Dạng thứ hai vẫn phù hợp với Java 17+; cần nhớ:

- `reader` trong `try (reader)` phải là một biến được phép tham chiếu theo quy tắc hiện hành, có kiểu con của `AutoCloseable` và **definitely assigned** trước khi vào `try`.
- *Effectively final* nghĩa là biến không được gán lại sau khi khởi tạo, dù không viết từ khóa `final`.
- Biến tồn tại ở phạm vi bên ngoài, nên vẫn **có tên** sau câu lệnh `try`, nhưng đối tượng đã bị đóng. **Không sử dụng lại một reader/stream đã đóng** chỉ vì biến còn trong scope.
- Nếu biến có thể bị gán lại, compiler từ chối dùng biến đó bằng cú pháp `try (reader)`. Nếu muốn mỗi lần dùng một resource mới, hãy khai báo trong header hoặc tổ chức lại vòng đời.
- `try (reader)` không gọi lại initializer; nó sử dụng **tham chiếu đã có** để quản lý đóng.

### Ví dụ Java 17+ với biến effectively final

Lưu file `ExistingResourceDemo.java`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ExistingResourceDemo {
    static String firstLine() throws IOException {
        BufferedReader reader =
                new BufferedReader(new StringReader("hello\nworld"));
        try (reader) {
            return reader.readLine();
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.println(firstLine());
    }
}
~~~

~~~bash
javac --release 17 ExistingResourceDemo.java
java ExistingResourceDemo
~~~

Stdout:

~~~text
hello
~~~

Dòng `return reader.readLine()` không bỏ qua bước đóng: Java tự đóng resource **trước khi phương thức trả kết quả** cho caller. Biến `reader` không bị gán lại nên hợp lệ khi tham chiếu trực tiếp trong header.

### `var` trong header chỉ có từ Java 10

Từ Java 10, compiler có thể suy luận kiểu **biến resource khai báo mới** bằng `var`:

~~~java
try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
~~~

Đây là đoạn minh họa **Java 10+** trong phương thức có `path`. Nó vẫn tạo một **biến resource mới**, khác với `try (reader)` tham chiếu biến có sẵn. `var` chỉ rút gọn cách viết kiểu, không miễn các điều kiện `AutoCloseable`, initializer và `final` ngầm.

Khi phải hỗ trợ mã nguồn ở mức Java 7/8, không viết `try (reader)` và không dùng `var`. Với Java 17+, cả ba dạng **khai báo có kiểu**, **tham chiếu biến effectively final** và **khai báo bằng `var`** đều hợp lệ; chọn một dạng rõ quyền sở hữu tài nguyên nhất cho người đọc.

## 7. Ví dụ gần thực tế: đọc file bằng resource khai báo trong header

Tạo file `FileReadDemo.java`:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileReadDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("twr-demo-", ".txt");
        try {
            Files.writeString(file, "alpha\nbeta\n", StandardCharsets.UTF_8);
            try (BufferedReader reader = Files.newBufferedReader(
                    file, StandardCharsets.UTF_8)) {
                System.out.println("first:" + reader.readLine());
                System.out.println("second:" + reader.readLine());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac --release 17 FileReadDemo.java
java FileReadDemo
~~~

Stdout trong môi trường có quyền truy cập thư mục tạm:

~~~text
first:alpha
second:beta
~~~

**Giải thích ranh giới tài nguyên:**

- `Files.createTempFile` trả về một **`Path`**, không phải đối tượng `AutoCloseable`. Vì thế `file` nằm ở biến thông thường, **không khai báo là resource trong header**.
- `Files.writeString` tự mở, ghi và đóng tài nguyên nội bộ theo hợp đồng API; đây là một API có từ Java 11, dùng trong ví dụ Java 17+.
- `Files.newBufferedReader` trả về `BufferedReader` cần đóng; vì vậy khai báo nó ở header `try (...)` là phù hợp.
- `reader` chỉ được dùng trong thân `try-with-resources`; Java tự đóng reader sau hai lần đọc. Khối `finally` bên ngoài xóa **file tạm**, là trách nhiệm khác với việc đóng reader.
- Việc dùng `UTF_8` tường minh giúp mã có hợp đồng giải mã cụ thể; không giả định một encoding mặc định tùy môi trường.
- Nếu thao tác mở/đọc file ném `IOException`, resource đã mở thành công vẫn được đóng theo quy tắc; `main` ở đây khai báo `throws IOException` để giữ chương trình mẫu ngắn.

Với file lớn, reader cho phép đọc theo luồng, không bắt buộc gom toàn bộ file vào bộ nhớ. Vẫn cần giới hạn kích thước dòng, thiết kế xử lý lỗi I/O và phân quyền file tùy ứng dụng.

## 8. Lỗi khi đóng và suppressed exception

`try-with-resources` bảo đảm **nỗ lực gọi `close()`** đúng quy tắc. Nó không bảo đảm bản thân `close()` luôn thành công.

- Nếu thân `try` chạy bình thường nhưng `close()` ném exception, exception đóng có thể truyền ra `catch`/caller.
- Nếu thân `try` **đã ném exception** và `close()` lại ném exception, exception từ thân `try` thường giữ vai trò **primary**, lỗi đóng trở thành **suppressed exception** để không mất thông tin. Có thể đọc qua `getSuppressed()`.
- Với nhiều resource, lỗi đóng resource bên phải **không ngăn** Java cố đóng những resource còn lại bên trái.
- `catch` và `finally` đi kèm được thực thi theo ngữ nghĩa đã bao gồm bước khởi tạo và đóng resource; khi vào `finally`, Java đã hoàn tất các nỗ lực đóng theo đặc tả.

Chương trình `SuppressionDemo.java`:

~~~java
public class SuppressionDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close-failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            throw new IllegalArgumentException("body-failed");
        } catch (RuntimeException ex) {
            System.out.println("primary:" + ex.getMessage());
            System.out.println("suppressed:" + ex.getSuppressed()[0].getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 SuppressionDemo.java
java SuppressionDemo
~~~

Stdout:

~~~text
primary:body-failed
suppressed:close-failed
~~~

Hàm `close()` ném lỗi **có chủ đích để minh họa**, không phải cách hiện thực resource trong ứng dụng. Hãy ghi log hoặc truyền lỗi theo chính sách nghiệp vụ, giữ nguyên suppressed exceptions khi phân tích sự cố. Không dùng cách gọi `close()` thủ công trong `finally` thay cho cú pháp này nếu resource đã tuân thủ `AutoCloseable`.

### Lưu ý về chữ ký `close()` và checked exception

`AutoCloseable.close()` được khai báo có thể ném `Exception`. Một subtype như `BufferedReader` có thể khai báo phạm vi checked exception **hẹp hơn**. Vì vậy cách khai báo kiểu resource trong header còn ảnh hưởng đến kiểm tra checked exception:

~~~java
try (AutoCloseable item = obtainResource()) {
    use(item);
}
~~~

Đây là đoạn minh họa có hàm `obtainResource()`/`use(...)` tự định nghĩa. Nếu không bắt, phương thức chứa `try` có thể phải khai báo `throws Exception` do **kiểu tĩnh `AutoCloseable`** có `close() throws Exception`, ngay cả khi implementation cụ thể thường không ném. Ưu tiên kiểu cụ thể có hợp đồng phù hợp hoặc xử lý exception có chủ đích, không bắt rộng chỉ để làm mất cảnh báo.

## 9. Các lỗi biên dịch thường gặp trong phần mở đầu

### 9.1. Loại không triển khai `AutoCloseable`

File `NonClosableResource.java` — **cố ý không biên dịch**:

~~~java
public class NonClosableResource {
    public static void main(String[] args) {
        try (String text = "hello") {
            System.out.println(text);
        }
    }
}
~~~

~~~bash
javac --release 17 NonClosableResource.java
~~~

Compiler từ chối vì `String` không thể dùng làm `AutoCloseable`. **Cách sửa:** chỉ đưa đối tượng thực sự cần đóng (reader/stream/connection) vào header. Dữ liệu `String` là kết quả dùng trong thân `try`, không phải resource.

### 9.2. Ngăn cách các resource bằng dấu phẩy

File `CommaResources.java` — **cố ý không biên dịch**:

~~~java
import java.io.StringReader;

public class CommaResources {
    public static void main(String[] args) {
        try (StringReader first = new StringReader("A"),
             second = new StringReader("B")) {
            System.out.println(first.read());
        }
    }
}
~~~

~~~bash
javac --release 17 CommaResources.java
~~~

Compiler báo lỗi cú pháp; trong header, **phải viết một khai báo tài nguyên cho mỗi mục và phân cách bằng `;`**. Dù khai báo local thông thường có thể viết `int a = 1, b = 2;`, không mang quy tắc dấu phẩy đó vào resource specification.

### 9.3. Gán lại biến resource

File `ReassignResource.java` — **cố ý không biên dịch**:

~~~java
import java.io.StringReader;

public class ReassignResource {
    public static void main(String[] args) {
        try (StringReader reader = new StringReader("A")) {
            reader = new StringReader("B");
        }
    }
}
~~~

~~~bash
javac --release 17 ReassignResource.java
~~~

Biến `reader` trong header là `final` ngầm. **Cách sửa:** quản lý thêm resource bằng một khai báo khác hoặc một khối `try-with-resources` riêng; không gán lại biến.

### 9.4. Thiếu initializer, thiếu điều kiện effectively final

Những dòng dưới đây **chỉ minh họa lỗi**, không phải chương trình độc lập:

~~~java
// Sai: khai báo trong header thiếu initializer.
try (BufferedReader reader) {
    // ...
}

// Sai từ Java 9+: reader là biến có thể đã bị gán lại.
BufferedReader reader = Files.newBufferedReader(firstPath);
reader = Files.newBufferedReader(secondPath);
try (reader) {
    // ...
}
~~~

Trong ví dụ thứ hai, cần quản lý vòng đời của reader cũ để tránh rò rỉ ngay từ lúc gán lại, thay vì chỉ sửa cú pháp. Nếu đã có biến effectively final hợp lệ, `try (reader)` dùng được; nếu mở resource mới, đặt ngay biểu thức khởi tạo ở header.

## 10. Checklist chọn cách khai báo resource khi review code

1. **Đúng đối tượng?** Resource có thực sự cần đóng và có implement `AutoCloseable` không? Một `Path` hoặc `String` không cần được đưa vào header.
2. **Đúng vòng đời?** Tạo càng gần nơi sử dụng càng tốt; đối tượng mà header quản lý sẽ bị đóng khi thoát khỏi câu lệnh. Không dùng lại reference sau khi đóng.
3. **Đúng initializer?** Mỗi khai báo header phải khởi tạo đúng một resource, với tên riêng và biểu thức hợp lệ. Dùng `;` phân cách, có thể kết thúc bằng `;`.
4. **Đúng kiểu ngoại lệ?** Xem `close()` theo **kiểu tĩnh** của resource và các exception từ constructor/initializer/body, rồi bắt hoặc khai báo phù hợp.
5. **Đúng quyền sở hữu?** Nếu object wrapper tự quản lý object nền, tránh đóng trùng không cần thiết; kiểm tra hợp đồng từng thư viện.
6. **Đúng thứ tự?** Nếu các resource phụ thuộc nhau, khai báo resource nền trước, resource phụ thuộc sau, để đóng theo thứ tự ngược.
7. **Đúng phiên bản?** Java 7+ dùng khai báo trong header; Java 9+ có thể tham chiếu biến `final`/effectively final đã tồn tại; Java 10+ cho phép `var`. Biên dịch theo release dự án thực sự hỗ trợ.
8. **Đúng tình huống lỗi?** Hãy nhớ initializer thứ hai lỗi vẫn đóng resource đầu; `close()` lỗi có thể truyền ra hoặc được suppressed; không bỏ sót thông tin điều tra.
9. **Đúng scope?** Biến khai báo trong header chỉ dùng trong phần còn lại của header và thân `try`; `catch`/`finally` không dùng tên biến đó trực tiếp.
10. **Đúng hành vi của thư viện?** `AutoCloseable` bảo đảm có phương thức `close()`, nhưng việc đóng thực sự giải phóng điều gì, có thể gọi lại hay không, và ngoại lệ nào có thể ném phụ thuộc hợp đồng class cụ thể.

## 11. Tự kiểm tra

**Câu 1.** Có thể viết `try (String name = "a")` nếu chỉ muốn giới hạn phạm vi biến không?  
**Đáp án:** Không. `String` không implement `AutoCloseable`. Dùng biến trong block thông thường.

**Câu 2.** `try (Reader a = createA(), b = createB())` có hợp lệ vì cả hai cùng kiểu không?  
**Đáp án:** Không. Mỗi khai báo resource chỉ có **một declarator**. Viết `try (Reader a = createA(); Reader b = createB())`.

**Câu 3.** Resource trong header được khởi tạo và đóng theo thứ tự nào?  
**Đáp án:** Khởi tạo **trái sang phải**, đóng **phải sang trái**.

**Câu 4.** Nếu initializer thứ hai ném ngoại lệ, resource thứ nhất có được đóng không?  
**Đáp án:** Có, nếu resource thứ nhất đã khởi tạo thành công. Thân `try` không chạy.

**Câu 5.** Có được gán lại `reader` trong `try (BufferedReader reader = ...)` không?  
**Đáp án:** Không. Biến khai báo resource là `final` ngầm.

**Câu 6.** `BufferedReader reader = ...; try (reader)` là cú pháp từ Java 7?  
**Đáp án:** Không. Đây là dạng tham chiếu biến có sẵn được bổ sung từ **Java 9**; biến phải `final`/effectively final và đã được gán.

**Câu 7.** Sau `try (reader) { ... }`, tên `reader` có thể vẫn trong scope; vậy reader có còn mở không?  
**Đáp án:** Không. Tên biến còn trong scope không có nghĩa tài nguyên còn mở; `close()` đã được gọi theo ngữ nghĩa `try-with-resources`.

**Câu 8.** Vì sao khối `try-with-resources` có thể cần `catch` dù thân `try` không ném checked exception?  
**Đáp án:** Initializer và `close()` của resource cũng có thể ném checked exception; compiler xét toàn bộ cấu trúc.

**Câu 9.** `try (var reader = ...)` đã có từ Java 7?  
**Đáp án:** Không. `var` được đưa vào Java 10. Với minimum Java 17+, cú pháp vẫn hợp lệ.

## Nguồn chính thức

- [JLS Java SE 26 — §14.20.3, try-with-resources](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.20.3): cú pháp resource specification, khai báo một declarator có initializer, `AutoCloseable`, `final`, biến có sẵn, thứ tự init/close và suppressed exceptions.
- [JLS Java SE 26 — §6.3, Scope of a Declaration](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-6.html#jls-6.3): phạm vi resource khai báo trong header.
- [JLS Java SE 7 — §14.20.3](https://docs.oracle.com/javase/specs/jls/se7/html/jls-14.html#jls-14.20.3): bằng chứng lịch sử về dạng khai báo resource có initializer ngay trong header khi Java 7 phát hành.
- [Dev.java — Catching and Handling Exceptions](https://dev.java/learn/catching-and-handling-exceptions/): hướng dẫn hiện hành về `AutoCloseable` và quản lý ngoại lệ.
- [Java SE 26 API — AutoCloseable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng method `close()` và các lưu ý khi triển khai resource.
- [Java SE 26 API — Files](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): các phương thức mở reader, stream; đọc hợp đồng riêng của mỗi API trước khi sử dụng.
- [JEP 213 — Milling Project Coin](https://openjdk.org/jeps/213): ghi nhận cải tiến dùng biến `final`/effectively final có sẵn trong `try-with-resources` từ Java 9.
- [JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): nguồn về `var` từ Java 10, có thể dùng với khai báo resource hiện đại.

**Ghi nhớ:** Phần mở đầu `try (...)` mô tả **tài nguyên nào thuộc vòng đời của `try`**. Khai báo mới phải có **kiểu đóng được + tên + initializer**, nhiều resource cách nhau bằng `;` và tự đóng theo thứ tự ngược. Dùng đúng cú pháp cho phiên bản Java mục tiêu giúp code an toàn và dễ kiểm tra, kể cả khi thân `try` lỗi hoặc kết thúc sớm.