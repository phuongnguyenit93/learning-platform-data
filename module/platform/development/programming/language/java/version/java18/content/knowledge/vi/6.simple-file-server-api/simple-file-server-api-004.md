# Điều kiện `rootDirectory` phải tuyệt đối, tồn tại, là thư mục và đọc được

> **Chương:** API SimpleFileServer  
> **Module học:** `JAVA_VERSION_JAVA18` — tìm hiểu các API được bổ sung từ Java 18 còn hữu ích trên JDK hiện đại.  
> **Trọng tâm:** Hợp đồng đầu vào của `SimpleFileServer.createFileServer(...)` và `SimpleFileServer.createFileHandler(...)`, cách dùng `Path`/`Files` để chuẩn bị thư mục, cách nhận biết lỗi và giới hạn bảo mật. Nội dung dựa trên API còn được hỗ trợ trong JDK 27.

## 1. `rootDirectory` có vai trò gì?

Từ Java 18, `SimpleFileServer` trong package `com.sun.net.httpserver`, module `jdk.httpserver`, cung cấp cách phục vụ tệp qua HTTP bằng JDK. Khác với một `HttpHandler` tự viết, file handler có sẵn nhận một **thư mục gốc** (`rootDirectory`) để biết tệp nào thuộc vùng nội dung được phục vụ.

```java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;
import java.net.InetSocketAddress;
import java.nio.file.Path;

// Đoạn trong main; thư mục public cần tồn tại và đọc được:
Path rootDirectory = Path.of("public").toAbsolutePath().normalize();
InetSocketAddress address = new InetSocketAddress("127.0.0.1", 8000);
HttpServer server = SimpleFileServer.createFileServer(
        address, rootDirectory, OutputLevel.INFO);
server.start();
```

`rootDirectory` là **đường dẫn trong hệ thống tệp của máy chạy JVM**, ví dụ thư mục `public` chứa HTML, CSS, ảnh hoặc tệp thử nghiệm. Nó **không phải** URL path: URL `/hello.txt` có thể ánh xạ đến một tệp `hello.txt` dưới `rootDirectory`.

Hai factory method liên quan cùng áp dụng hợp đồng này:

```java
// Đã khai báo address và rootDirectory như đoạn ở trên:
// Tạo HttpServer có sẵn context "/" với file handler:
HttpServer server = SimpleFileServer.createFileServer(
        address, rootDirectory, SimpleFileServer.OutputLevel.INFO);

// Hoặc chỉ tạo handler để gắn vào một HttpContext khác:
HttpHandler handler = SimpleFileServer.createFileHandler(rootDirectory);
```

Đây là **hai cách dùng lựa chọn** của factory, không phải hai lệnh cần viết nối tiếp trong cùng phương thức (vì lệnh đầu đã tạo server). `createFileServer` trả `HttpServer`; `createFileHandler` trả `HttpHandler`. Ví dụ đầy đủ chạy được nằm ở phần 4.

## 2. Bốn điều kiện bắt buộc của `rootDirectory`

Theo Javadoc của cả hai factory method, đối số `rootDirectory` phải đồng thời đáp ứng:

| Điều kiện | Ý nghĩa | Kiểm tra hoặc chuẩn bị bằng Java |
| --- | --- | --- |
| **1. Tuyệt đối** (*absolute*) | Tên đường dẫn xác định vị trí dựa trên gốc hệ thống tệp thay vì phụ thuộc thư mục làm việc hiện tại. | `root.isAbsolute()` và `root.toAbsolutePath()`. |
| **2. Tồn tại** | Tài nguyên phải có trên hệ thống tệp lúc factory kiểm tra; API **không tự tạo thư mục**. | `Files.exists(root)`. |
| **3. Là thư mục** | Tệp đơn lẻ (`hello.txt`) không thể đóng vai trò thư mục gốc; cần thư mục chứa các tài nguyên được phục vụ. | `Files.isDirectory(root)`. |
| **4. Đọc được** | JVM đang chạy cần có quyền truy cập đọc đối với thư mục gốc. | `Files.isReadable(root)`. |

Khi vi phạm **bất kỳ điều kiện nào** trong bốn điều kiện, `createFileServer(...)` và `createFileHandler(...)` đều có thể ném `IllegalArgumentException`. Với đối số `rootDirectory = null`, lỗi là `NullPointerException`. Chưa nên suy luận rằng lỗi là `403` hoặc `404`: đây là **ngoại lệ lúc cấu hình handler/server**, trước khi có một HTTP response.

### 2.1. Đường dẫn tuyệt đối: `isAbsolute()`

```java
import java.nio.file.Path;

Path relative = Path.of("public");
System.out.println(relative.isAbsolute()); // Thông thường: false

Path absolute = relative.toAbsolutePath().normalize();
System.out.println(absolute.isAbsolute()); // true
System.out.println(absolute);             // Phụ thuộc working directory
```

`Path.of("public")` thường là **tương đối**. Nó chỉ trở thành tuyệt đối sau khi thêm vị trí làm việc của tiến trình bằng `toAbsolutePath()`. `normalize()` loại bỏ các thành phần thừa như `.` và `..` theo **cú pháp đường dẫn**.

Ví dụ, nếu ứng dụng chạy với working directory `C:/dev/demo` trên Windows, đường dẫn `Path.of("public").toAbsolutePath().normalize()` có dạng `C:\dev\demo\public`. Trên Linux/macOS, nếu working directory là `/home/dev/demo`, kết quả sẽ có dạng `/home/dev/demo/public`. Đây chỉ là ví dụ minh họa vị trí, không phải những đường dẫn bắt buộc phải có.

**Nhớ:** `toAbsolutePath().normalize()` chỉ chuẩn hóa **tên đường dẫn**. Nó không bảo đảm rằng thư mục đã tồn tại, đọc được hoặc không đi qua symbolic link. Cần kiểm tra ba điều kiện còn lại riêng.

### 2.2. Tồn tại: `Files.exists(root)`

```java
Path root = Path.of("public").toAbsolutePath().normalize();
if (!Files.exists(root)) {
    throw new IllegalArgumentException("Không tìm thấy thư mục: " + root);
}
```

Nếu thư mục chưa được tạo, factory không tạo nó hộ bạn. Đối với **thư mục thử nghiệm mới do ứng dụng chủ động sở hữu**, có thể tạo trước:

```java
Path root = Path.of("public").toAbsolutePath().normalize();
java.nio.file.Files.createDirectories(root); // Có thể ném IOException.
```

`Files.createDirectories(...)` tạo những thư mục cha còn thiếu khi có quyền; nếu đường dẫn đã tồn tại là tệp thường, thao tác cũng không biến nó thành thư mục. Với đường dẫn do người dùng cung cấp hoặc một vị trí không rõ nguồn gốc, nên **xác minh lựa chọn** thay vì âm thầm tạo một thư mục ngoài ý muốn.

### 2.3. Là thư mục: `Files.isDirectory(root)`

```java
Path root = Path.of("hello.txt").toAbsolutePath();
System.out.println(Files.isDirectory(root)); // false nếu là tệp thường
```

Một tệp đơn lẻ dù tồn tại và có thể đọc cũng **không** đáp ứng hợp đồng. Chỉ định thư mục cha chứa những tệp được phép phục vụ, ví dụ `public/`, thay vì đường dẫn trực tiếp tới `public/hello.txt`.

`Files.isDirectory(path)` mặc định **theo symbolic link** khi xác định kiểu tệp. Do đó, một symbolic link trỏ tới thư mục có thể trả `true`; điều đó chưa nói gì về việc chọn liên kết ấy có phù hợp với phạm vi dữ liệu muốn công khai hay không. Với thư mục do người khác kiểm soát, cần xem xét **đường dẫn thực** và chính sách truy cập trước khi đưa nó lên HTTP.

### 2.4. Đọc được: `Files.isReadable(root)`

```java
Path root = Path.of("public").toAbsolutePath().normalize();
if (!Files.isReadable(root)) {
    throw new IllegalArgumentException(
            "JVM không đọc được thư mục: " + root);
}
```

`Files.isReadable` kiểm tra khả năng đọc **theo quyền của chính tiến trình JVM**; kiểm tra chỉ nhìn vào quyền và trạng thái ở **thời điểm gọi**. Trên Windows có thể liên quan đến ACL; trên các hệ điều hành khác có thể phụ thuộc quyền của user/group và quyền truy cập các thư mục cha. Việc user đang mở được tệp bằng phần mềm khác không bảo đảm JVM chạy dưới tài khoản khác có cùng quyền.

Javadoc của `Files.isReadable` còn cảnh báo kết quả kiểm tra có thể **hết hiệu lực ngay sau đó**: quyền, liên kết hoặc đối tượng thực tế có thể thay đổi trước lúc mở tệp. Vì vậy, **preflight bằng `Files` giúp báo lỗi rõ ràng nhưng không thay thế xử lý ngoại lệ của factory** và cũng không đảm bảo mọi tệp con đều đọc được trong suốt thời gian server chạy.

## 3. Từ `Path.of(...)` tới một `rootDirectory` hợp lệ

Trình tự thường dùng:

```text
Đường dẫn cấu hình, ví dụ "public"
             |
             v
Path.of("public")                  -> tương đối
             |
             v
.toAbsolutePath().normalize()     -> tuyệt đối, gọn về cú pháp
             |
             v
Files.exists(root)?               -> có thư mục trên đĩa?
             |
             v
Files.isDirectory(root)?          -> có đúng kiểu thư mục?
             |
             v
Files.isReadable(root)?           -> JVM có quyền đọc?
             |
             v
createFileServer(..., root, ...)  -> factory kiểm tra hợp đồng
             |
             v
server.start()                    -> bắt đầu phục vụ HTTP
```

Thứ tự kiểm tra riêng `exists`, `isDirectory`, `isReadable` rất hữu ích khi muốn **thông báo lỗi cụ thể**; về mặt kỹ thuật, `Files.isDirectory(root) == true` cũng hàm ý đã xác định đó là một thư mục đang tồn tại tại thời điểm kiểm tra. Đừng dùng bảng kiểm tra này như một bước kiểm soát an ninh duy nhất nếu hệ thống tệp có thể thay đổi đồng thời.

### `toAbsolutePath()`, `normalize()` và `toRealPath()` khác nhau

| API của `Path` | Có truy cập hệ thống tệp để xác minh? | Mục đích |
| --- | --- | --- |
| `toAbsolutePath()` | Không bắt buộc xác minh đối tượng tồn tại | Đưa path tương đối về vị trí tuyệt đối theo file system/working directory. |
| `normalize()` | Không; thao tác chủ yếu trên thành phần tên | Loại bỏ những thành phần `.` và `..` thừa theo cú pháp. |
| `toRealPath()` | **Có**; thông thường yêu cầu đối tượng tồn tại và có thể ném `IOException` | Xác định đường dẫn thực, mặc định phân giải symbolic link và trả path tuyệt đối đã chuẩn hóa. |

Ví dụ khi muốn biết **thư mục thực sự được chọn**:

```java
Path configured = Path.of("public").toAbsolutePath().normalize();
Path actual = configured.toRealPath(); // throws IOException nếu không xác định được
System.out.println("Configured: " + configured);
System.out.println("Actual: " + actual);
```

Không cần gọi `toRealPath()` chỉ để đáp ứng yêu cầu `isAbsolute()`: `toAbsolutePath()` đã làm được điều này. Nhưng `toRealPath()` có ích khi kiểm tra symbolic link hoặc vị trí sau khi chuẩn hóa. Nếu đường dẫn thực không nằm trong vùng dữ liệu bạn định chia sẻ, cần **dừng** và chọn thư mục khác; việc biết đường dẫn thực không tự động tạo cơ chế phân quyền an toàn.

## 4. Ví dụ Java đầy đủ: kiểm tra `rootDirectory` trước khi start

Ví dụ này chủ động nhận thư mục từ tham số dòng lệnh, mặc định là `public`, và báo rõ khi thiếu một trong bốn điều kiện. Nó bind vào `127.0.0.1` với cổng `0` để hệ điều hành chọn cổng khả dụng, rồi in cổng thực tế. Chạy trong terminal có stdin tương tác vì chương trình đợi Enter để dừng.

Lưu thành `RootDirectoryDemo.java`:

```java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;

public class RootDirectoryDemo {
    private static Path checkedRoot(String configured) {
        // Phần mềm có thể nhận chuỗi "public" từ cấu hình; phải chuẩn hóa.
        Path root = Path.of(configured).toAbsolutePath().normalize();

        if (!root.isAbsolute()) {
            throw new IllegalArgumentException(
                    "rootDirectory phải là đường dẫn tuyệt đối: " + root);
        }
        if (!Files.exists(root)) {
            throw new IllegalArgumentException(
                    "rootDirectory không tồn tại: " + root);
        }
        if (!Files.isDirectory(root)) {
            throw new IllegalArgumentException(
                    "rootDirectory không phải thư mục: " + root);
        }
        if (!Files.isReadable(root)) {
            throw new IllegalArgumentException(
                    "rootDirectory không đọc được: " + root);
        }
        return root;
    }

    public static void main(String[] args) throws IOException {
        String configured = args.length > 0 ? args[0] : "public";
        Path root = checkedRoot(configured);
        InetSocketAddress address = new InetSocketAddress("127.0.0.1", 0);

        // Factory vẫn kiểm tra lại các điều kiện; server chưa được start.
        HttpServer server = SimpleFileServer.createFileServer(
                address, root, OutputLevel.INFO);

        server.start();
        int port = server.getAddress().getPort();
        System.out.println("Thư mục phục vụ: " + root);
        System.out.println("Địa chỉ: http://127.0.0.1:" + port + "/");
        System.out.println("Nhấn Enter để dừng...");

        try {
            System.in.read();
        } finally {
            server.stop(0);
        }
    }
}
```

### Chuẩn bị và chạy

Tạo một thư mục `public` chứa `hello.txt` trong **working directory**. Nếu đang viết một chương trình demo chủ động tạo dữ liệu thử nghiệm, có thể tạo thư mục/tệp bằng Java:

```java
Path root = Files.createDirectories(Path.of("public"));
Files.writeString(root.resolve("hello.txt"), "Hello from Java!");
```

Đây là **đoạn chuẩn bị độc lập**; tạo thư mục và tệp trước khi chạy `RootDirectoryDemo`. Không đặt đoạn này vào `checkedRoot`, bởi vì `checkedRoot` có nhiệm vụ phát hiện và thông báo khi đường dẫn cấu hình sai.

Biên dịch và chạy trên JDK 18 trở lên:

```bash
javac RootDirectoryDemo.java
java RootDirectoryDemo
```

Với một đường dẫn khác, có thể truyền vào chương trình:

```bash
java RootDirectoryDemo public
```

Ví dụ cổng được in ra là `51234` (giá trị thực tế do hệ điều hành chọn, có thể khác), dùng:

```bash
curl -i http://127.0.0.1:51234/hello.txt
curl -I http://127.0.0.1:51234/hello.txt
```

`GET` đọc nội dung file; `HEAD` trả header mà không gửi body. Khi đường dẫn URL trỏ tới thư mục, handler có thể xuất danh sách thư mục dưới dạng HTML. Với những phương thức ngoài `GET` và `HEAD`, file handler trả `405 Method Not Allowed`. Nhấn Enter ở terminal Java để chạy `server.stop(0)`. Nếu stdin đã đóng sẵn (như một số trình chạy tự động), chương trình có thể dừng ngay; khi viết test tự động hãy dùng cơ chế điều khiển vòng đời khác.

Ở đây có hai lớp kiểm tra: `checkedRoot` báo thông điệp dễ hiểu, còn `SimpleFileServer.createFileServer` thực hiện kiểm tra hợp đồng tại thời điểm factory tạo server. Không thể thay thế phần kiểm tra thứ hai.

## 5. Chẩn đoán lỗi `rootDirectory` theo triệu chứng

| Đầu vào hoặc hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Path.of("public")` truyền thẳng vào factory | Đây thường là **relative path**. | Dùng `toAbsolutePath().normalize()` và kiểm tra vị trí kết quả. |
| `Path.of("missing").toAbsolutePath()` | Path tuyệt đối nhưng thư mục chưa tồn tại. | Tạo thư mục thử nghiệm đúng nơi hoặc sửa giá trị cấu hình; không giả định factory sẽ tạo hộ. |
| `Path.of("hello.txt").toAbsolutePath()` | Path tồn tại nhưng là tệp thường. | Chọn thư mục cha chứa tệp được phục vụ. |
| Thư mục có trên đĩa nhưng `Files.isReadable(root) == false` | Tiến trình JVM không có quyền đọc, hoặc không thể xác định quyền truy cập. | Xác minh account đang chạy Java, ACL/permission và quyền trên thư mục cha. |
| `rootDirectory == null` | Sai hợp đồng không-null. | Cấu hình giá trị thực; factory ném `NullPointerException`. |
| Thư mục hợp lệ nhưng `createFileServer(...)` lỗi bind cổng | Lỗi I/O khi khởi tạo HTTP server, không phải lỗi đường dẫn. | Xem `UncheckedIOException` và nguyên nhân gốc; chọn cổng còn trống, ví dụ `0`. |
| Khởi tạo server thành công nhưng `GET /hello.txt` không đọc được | Tệp con thiếu/quyền đọc đã thay đổi, URL không trỏ đúng tệp hoặc trạng thái hệ thống tệp thay đổi. | Kiểm tra nội dung thực tế dưới root và quyền truy cập tại thời điểm request. |

Javadoc nêu rõ `IllegalArgumentException` cho **bốn điều kiện của thư mục**, `NullPointerException` khi đối số null; riêng `createFileServer(...)` còn có thể ném `UncheckedIOException` khi xảy ra lỗi I/O. Không nên bắt tất cả lỗi và in chung thông báo “thư mục không hợp lệ”, vì như vậy sẽ che mất nguyên nhân cổng hoặc tài nguyên mạng.

### Bẫy của working directory

Giả sử file `hello.txt` thực tế nằm trong `D:/project/site/public`, nhưng chương trình Java được chạy từ `D:/project`. Khi viết:

```java
Path root = Path.of("public").toAbsolutePath().normalize();
```

kết quả là `D:/project/public`, **không phải** `D:/project/site/public`. Nếu ứng dụng chạy từ IDE, thư mục làm việc có thể do cấu hình Run/Debug quyết định.

Để biết JVM đang dùng thư mục nào, trong ứng dụng có thể in:

```java
System.out.println("Working directory = " + Path.of("").toAbsolutePath());
System.out.println("Configured root    = " + root);
```

Đừng sửa bằng cách thêm bừa `../` cho đến khi chạy được. Hãy xác nhận working directory rồi chọn đường dẫn rõ ràng hoặc dùng cấu hình đường dẫn dành riêng cho môi trường chạy.

## 6. Quy tắc an toàn khi chọn thư mục gốc

`SimpleFileServer` được thiết kế **chỉ để thử nghiệm, phát triển và gỡ lỗi**. Bốn điều kiện root là yêu cầu API để khởi tạo, **không phải kiểm tra rằng dữ liệu đó an toàn để công khai**. Một thư mục tuyệt đối, tồn tại, đọc được vẫn có thể chứa tài liệu riêng.

1. **Chỉ chọn thư mục chuyên phục vụ nội dung thử nghiệm**, ví dụ `public` chứa vài tệp mẫu. Tránh chọn thư mục home, gốc ổ đĩa, source code, file cấu hình, khóa riêng, token hoặc dữ liệu khách hàng.
2. **Giới hạn bind vào loopback** như `127.0.0.1` khi chỉ cần chạy trên máy cá nhân. Bind `0.0.0.0` có thể cho phép các máy khác kết nối nếu mạng và firewall cho phép.
3. **Xem xét symbolic link, junction hoặc mount point** nếu thư mục có thể do người khác kiểm soát. `toAbsolutePath().normalize()` không xác minh đích thật; có thể kiểm tra `toRealPath()` và đánh giá vùng dữ liệu được trỏ tới. Không giả định chuỗi đường dẫn đẹp đồng nghĩa dữ liệu an toàn.
4. **Dữ liệu và quyền truy cập có thể đổi trong lúc server chạy.** Kiểm tra `Files.exists`/`Files.isReadable` chỉ có giá trị ở thời điểm gọi. Đừng dùng kết quả đó làm bằng chứng bảo mật lâu dài hoặc quyền truy cập vĩnh viễn.
5. **Phân biệt đọc thư mục với đọc từng tệp:** việc root đọc được không bảo đảm mọi tệp con đều đọc được; khi thử nghiệm, kiểm tra cả các request thực tế cần phục vụ.

Với chương trình cần HTTPS, xác thực, phân quyền và vận hành production, cần thiết kế HTTP server phù hợp và kiểm soát quyền truy cập ở tầng ứng dụng/hệ thống. `SimpleFileServer` là công cụ tối giản để chia sẻ tệp tĩnh trong môi trường có kiểm soát.

## 7. Bài tập thực hành và câu hỏi tự kiểm tra

**Thực hành:** tạo thư mục `public` và một tệp `public/hello.txt`, sau đó thử lần lượt những đường dẫn sau trong `RootDirectoryDemo`. Quan sát xem `checkedRoot` chặn lỗi ở bước nào và vì sao.

| Thử nghiệm | Giá trị cấu hình | Kết quả dự đoán |
| --- | --- | --- |
| A | `public` khi thư mục tồn tại, đọc được | Chuyển thành path tuyệt đối, tạo server và chạy. |
| B | `missing` khi thư mục chưa tồn tại | Báo không tồn tại. |
| C | `public/hello.txt` | Báo không phải thư mục. |
| D | `public/./sub/..` khi `public` tồn tại | `normalize()` đưa về path của `public` về mặt cú pháp. |
| E | Một thư mục cố ý bị từ chối quyền đọc với JVM | Báo không đọc được khi kiểm tra phát hiện; mức quyền phụ thuộc hệ điều hành và tài khoản chạy. |

Sau đó thử cố tình truyền `Path.of("public")` **trực tiếp** vào `SimpleFileServer.createFileHandler(...)` trong một đoạn mã độc lập; so sánh ngoại lệ với trường hợp truyền `Path.of("public").toAbsolutePath().normalize()` khi thư mục hợp lệ. Chỉ dùng thư mục và tệp thử nghiệm, không sửa quyền của thư mục quan trọng trên máy.

Câu hỏi:

1. Vì sao `Path.of("public")` chưa đủ điều kiện để truyền thẳng vào `createFileServer()`?
2. `isAbsolute()` và `Files.exists()` kiểm tra hai điều kiện nào khác nhau?
3. Nếu đường dẫn trỏ tới một tệp thường có quyền đọc, factory có chấp nhận không? Vì sao?
4. Vì sao `Files.isReadable(root) == true` không đảm bảo request HTTP trong tương lai luôn thành công?
5. `toAbsolutePath().normalize()` có làm thư mục xuất hiện trên đĩa không? `toRealPath()` khác ở đâu?
6. Cùng một chuỗi cấu hình `public`, vì sao chạy chương trình từ IDE và terminal có thể chọn hai thư mục khác nhau?
7. Những ngoại lệ nào được công bố cho root không hợp lệ, đối số null và lỗi I/O lúc tạo server?
8. Tại sao chọn thư mục đọc được vẫn chưa đủ để đánh giá tính an toàn khi chia sẻ qua HTTP?

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): hai factory method dùng `rootDirectory`, bốn điều kiện, ngoại lệ và phạm vi phục vụ tệp.
- [Oracle JDK 27 — `Path`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Path.html): `isAbsolute`, `toAbsolutePath`, `normalize`, `toRealPath`.
- [Oracle JDK 27 — `Files`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html): `exists`, `isDirectory`, `isReadable`, `createDirectories` và giới hạn của việc kiểm tra quyền.
- [Oracle JDK 27 — `HttpServer`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): địa chỉ, cổng, start/stop và cấu hình server.
- [Oracle JDK 18 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): so sánh hợp đồng gốc của API được giới thiệu từ Java 18.
