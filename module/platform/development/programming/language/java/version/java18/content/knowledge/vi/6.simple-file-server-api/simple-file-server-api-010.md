# `createOutputFilter()`: xuất log UTF-8 đến OutputStream và quản lý vòng đời luồng đích

> **Chương:** API SimpleFileServer  
> **Module học:** JAVA_VERSION_JAVA18 — SimpleFileServer được bổ sung từ Java 18 và vẫn có trong JDK hiện đại.  
> **Mục tiêu:** Tạo output filter, hiểu dữ liệu log được ghi bằng UTF-8 vào OutputStream, chọn mức log hợp lệ và quản lý stream đúng thứ tự với vòng đời HttpServer.

## 1. createOutputFilter() trả về gì?

`SimpleFileServer.createOutputFilter(OutputStream out, OutputLevel outputLevel)` là static factory method trả về một **Filter hậu xử lý** (*post-processing filter*). Filter ghi thông tin log liên quan đến các HTTP exchange đã được xử lý qua chuỗi handler của context.

Chữ ký API:

~~~java
public static Filter createOutputFilter(
        OutputStream out,
        SimpleFileServer.OutputLevel outputLevel)
~~~

Hai tham số:

| Tham số | Vai trò |
| --- | --- |
| `out` | Luồng byte nhận dữ liệu log. Có thể là `System.out`, file stream, `ByteArrayOutputStream` hoặc OutputStream do ứng dụng quản lý. |
| `outputLevel` | Mức chi tiết log: `INFO` hoặc `VERBOSE`. `NONE` không hợp lệ với factory này. |

Kết quả là một `Filter` có thể gắn vào `HttpContext.getFilters()`. Filter không tự tạo server, không tự tạo context và không tự quyết định địa chỉ/cổng. Ứng dụng phải tạo server, gắn filter vào đúng context và gọi `start()`.

## 2. Hợp đồng UTF-8: OutputStream nhận byte, không nhận ký tự

Javadoc quy định log được ghi vào OutputStream được truyền vào bằng **UTF-8**. Đây là điểm quan trọng vì `OutputStream` làm việc với byte; bản thân stream không mang thông tin charset như một Reader/Writer.

Luồng dữ liệu:

~~~text
HTTP exchange
     |
     v
Filter hậu xử lý của SimpleFileServer
     |
     v
Mã hóa nội dung log thành UTF-8
     |
     v
OutputStream out
     |
     +----> terminal (System.out)
     |
     +----> file
     |
     +----> bộ nhớ (ByteArrayOutputStream)
     |
     +----> đích ghi do ứng dụng tự cung cấp
~~~

Khi đọc lại log, phải giải mã byte bằng UTF-8 để khôi phục văn bản chính xác:

~~~java
String text = Files.readString(logPath, StandardCharsets.UTF_8);
~~~

Với byte đang nằm trong bộ nhớ:

~~~java
String text = new String(
        byteArrayOutputStream.toByteArray(),
        StandardCharsets.UTF_8);
~~~

Không dùng charset mặc định của máy để đọc file log nếu muốn kết quả nhất quán giữa Windows, Linux và macOS. Mặc dù JDK hiện đại mặc định charset của nhiều API đã chuyển sang UTF-8, việc chỉ định UTF-8 tại điểm đọc vẫn làm hợp đồng dữ liệu rõ ràng và tránh phụ thuộc môi trường.

### Không bọc stream bằng Writer để tự mã hóa lần nữa

Factory nhận OutputStream và tự ghi log theo UTF-8. Không cần bọc OutputStream bằng `OutputStreamWriter` hoặc tự tạo `PrintWriter` để chuyển đổi charset trước khi truyền vào. Hãy truyền stream byte trực tiếp:

~~~java
OutputStream out = Files.newOutputStream(logPath);
Filter filter = SimpleFileServer.createOutputFilter(
        out, SimpleFileServer.OutputLevel.INFO);
~~~

Khi đọc file, chỉ định `StandardCharsets.UTF_8`. Không chuyển byte UTF-8 thành chuỗi bằng charset khác rồi ghi lại, vì thao tác đó có thể làm sai ký tự.

Với `System.out`, output filter vẫn ghi byte UTF-8. Nếu terminal hiển thị sai ký tự, hãy kiểm tra encoding mà terminal dùng để giải mã byte; điều đó không có nghĩa filter đã ghi bằng charset mặc định khác.

## 3. Chọn OutputLevel hợp lệ

Factory `createOutputFilter` nhận:

| Giá trị | Hợp lệ? | Nội dung |
| --- | --- | --- |
| `OutputLevel.INFO` | Có | Log thông tin cơ bản theo Common Logfile Format. |
| `OutputLevel.VERBOSE` | Có | Log chi tiết hơn, gồm request/response headers và đường dẫn tuyệt đối của tài nguyên. |
| `OutputLevel.NONE` | **Không** | Factory ném `IllegalArgumentException`. |

Nếu không muốn ghi log, **không gắn output filter** vào context. Đây là khuyến nghị được ghi trong API Note của Javadoc. Không truyền `NONE` rồi mong filter tự bỏ qua mọi exchange.

Các trường hợp ngoại lệ:

- `out == null`: ném `NullPointerException`.
- `outputLevel == null`: ném `NullPointerException`.
- `outputLevel == OutputLevel.NONE`: ném `IllegalArgumentException`.

Mức log càng chi tiết, dữ liệu có thể lộ ra càng nhiều. Đặc biệt, `VERBOSE` có thể ghi các header như `Authorization`, `Cookie`, `Set-Cookie` hoặc header tùy biến chứa token. Chỉ bật khi cần chẩn đoán và dùng dữ liệu thử nghiệm không nhạy cảm.

## 4. Gắn output filter vào HttpContext

Output filter được gắn theo **context**, không mặc nhiên áp dụng cho mọi route của một HttpServer:

~~~java
HttpServer server = HttpServer.create(address, 0);
HttpContext files = server.createContext(
        "/files/", SimpleFileServer.createFileHandler(root));

Filter logFilter = SimpleFileServer.createOutputFilter(
        System.out, OutputLevel.INFO);
files.getFilters().add(logFilter);

server.start();
~~~

Trong ví dụ:

1. Ứng dụng tạo HttpServer.
2. File handler được gắn vào context `/files/`.
3. Output filter được thêm vào danh sách filter của context `files`.
4. Khi request được định tuyến vào context này, filter ghi log sau khi handler xử lý exchange.

Nếu server có thêm context `/health/`, filter trên không tự động ghi log cho context đó. Muốn log health endpoint, phải gắn filter vào context tương ứng hoặc dùng một cơ chế logging chung do ứng dụng quản lý.

## 5. Ai sở hữu và đóng OutputStream?

Đây là phần quan trọng khi dùng `createOutputFilter` trong một server chạy lâu dài.

Javadoc quy định factory ghi log vào OutputStream được truyền vào, nhưng không mô tả rằng quyền sở hữu stream được chuyển cho Filter, cũng không cam kết Filter tự đóng stream khi server dừng. Vì vậy, thiết kế an toàn là **ứng dụng cung cấp stream thì ứng dụng quản lý vòng đời stream**:

1. Mở OutputStream trước khi server nhận request.
2. Tạo filter bằng stream đó và gắn vào context.
3. Giữ stream mở trong toàn bộ thời gian server có thể xử lý exchange.
4. Dừng server trước để ngừng nhận request và cho exchange đang xử lý cơ hội hoàn tất theo thời gian chờ đã chọn.
5. Sau đó mới flush/close stream do ứng dụng sở hữu.

Không đóng stream khi server vẫn đang chạy. Filter là post-processing filter, nên việc ghi log xảy ra sau khi handler xử lý exchange. Nếu ứng dụng đóng stream quá sớm, request đang hoàn tất có thể cần ghi vào một stream đã đóng.

### Quy tắc theo loại stream

| Stream truyền vào | Ai quản lý? | Cách kết thúc |
| --- | --- | --- |
| `System.out` | JVM/tiến trình quản lý | Không đóng. Không bọc `System.out` trong try-with-resources để rồi đóng nó. |
| `Files.newOutputStream(...)` | Ứng dụng | Dừng server, sau đó đóng stream bằng try-with-resources hoặc finally. |
| `FileOutputStream` do ứng dụng mở | Ứng dụng | Dừng server, flush nếu cần, rồi close. |
| `ByteArrayOutputStream` dùng để test | Ứng dụng | Đọc `toByteArray()` sau khi exchange đã xử lý; close không giải phóng tài nguyên hệ điều hành nhưng vẫn nên giữ lifecycle rõ ràng. |
| Stream tùy biến hoặc stream mạng | Ứng dụng/đơn vị tạo stream | Tuân thủ hợp đồng riêng của stream; dừng server trước khi đóng đích ghi. |

### Vì sao phải stop server trước close stream?

Giả sử một request đang xử lý:

~~~text
Client request
     |
     v
HttpHandler xử lý file
     |
     v
Handler hoàn tất
     |
     v
Output filter ghi log vào out
~~~

Nếu ứng dụng đóng `out` trước khi chuỗi xử lý kết thúc, bước ghi log có thể gặp IOException. Trình tự phù hợp:

~~~text
server.stop(delay)
        |
        v
Ngừng nhận request mới / chờ exchange trong giới hạn delay
        |
        v
Đóng OutputStream do ứng dụng sở hữu
~~~

`stop(delay)` có giới hạn thời gian chờ. Nếu delay hết trước khi exchange hoàn tất, không nên giả định mọi request đã hoàn thành thành công. Với ứng dụng cần shutdown có kiểm soát, chọn delay phù hợp và thiết kế xử lý request đang chạy theo yêu cầu của hệ thống.

Javadoc của `createOutputFilter` không cam kết chính sách flush/close của stream. Nếu cần đọc log ngay sau khi server dừng, ứng dụng nên flush hoặc close stream theo quyền sở hữu của mình trước khi đọc lại file.

## 6. Ví dụ hoàn chỉnh: ghi log UTF-8 vào file

Ví dụ sau:

- Tạo thư mục tạm chứa file được phục vụ.
- Tạo file log riêng nằm ngoài thư mục gốc.
- Mở OutputStream ở chế độ append.
- Gắn `createOutputFilter(..., INFO)` vào file context.
- Chạy request bằng HttpClient.
- Dừng server trước khi đóng log stream.
- Đọc log bằng UTF-8.

Lưu thành `OutputFilterFileDemo.java`:

~~~java
import com.sun.net.httpserver.Filter;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import com.sun.net.httpserver.SimpleFileServer.OutputLevel;

import java.io.OutputStream;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Comparator;

public class OutputFilterFileDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("file-server-root-");
        Path logFile = Files.createTempFile("file-server-log-", ".txt");

        try {
            Files.writeString(
                    root.resolve("hello.txt"),
                    "Xin chào từ SimpleFileServer",
                    StandardCharsets.UTF_8);

            // Ứng dụng mở và sở hữu stream; log file nằm ngoài root được phục vụ.
            try (OutputStream logOut = Files.newOutputStream(
                    logFile,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.APPEND)) {

                HttpServer server = HttpServer.create(
                        new InetSocketAddress(
                                InetAddress.getLoopbackAddress(), 0),
                        0);

                HttpContext files = server.createContext(
                        "/",
                        SimpleFileServer.createFileHandler(root));

                Filter output = SimpleFileServer.createOutputFilter(
                        logOut, OutputLevel.INFO);
                files.getFilters().add(output);

                server.start();
                try {
                    InetSocketAddress bound = server.getAddress();
                    InetAddress boundIp = bound.getAddress();
                    String host = boundIp.getHostAddress();
                    if (boundIp instanceof Inet6Address) {
                        host = "[" + host + "]";
                    }
                    URI uri = URI.create(
                            "http://" + host + ":" + bound.getPort()
                                    + "/hello.txt");
                    HttpRequest request = HttpRequest.newBuilder(uri)
                            .GET()
                            .build();
                    HttpResponse<String> response =
                            HttpClient.newHttpClient().send(
                                    request,
                                    HttpResponse.BodyHandlers.ofString(
                                            StandardCharsets.UTF_8));

                    if (response.statusCode() != 200) {
                        throw new AssertionError(
                                "Unexpected HTTP status: "
                                        + response.statusCode());
                    }
                    System.out.println("HTTP " + response.statusCode());
                    System.out.println("Body: " + response.body());
                } finally {
                    // Phải dừng server trước khi try-with-resources đóng logOut.
                    server.stop(1);
                }
            }

            // Đọc log sau khi stream đã được đóng và flush.
            String logText = Files.readString(
                    logFile, StandardCharsets.UTF_8);
            System.out.println("Log UTF-8:");
            System.out.println(logText);
        } finally {
            try (var paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
            Files.deleteIfExists(logFile);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 18 trở lên:

~~~bash
javac OutputFilterFileDemo.java
java OutputFilterFileDemo
~~~

Ví dụ dùng địa chỉ loopback và cổng `0`, nên không cần giả định cổng cố định. URL được dựng từ địa chỉ thực tế mà server đã bind; nếu JDK chọn IPv6 loopback, host được đặt trong dấu ngoặc vuông theo cú pháp URL.

File log được tạo ngoài `root`, vì vậy file handler không công khai log đó. Sau khi response hoàn tất, server dừng; try-with-resources đóng stream và flush dữ liệu trước khi chương trình đọc log.

## 7. Ví dụ kiểm thử trong bộ nhớ bằng ByteArrayOutputStream

Trong unit test hoặc ví dụ học tập, không nhất thiết phải tạo file log. `ByteArrayOutputStream` cho phép giữ byte log trong bộ nhớ:

~~~java
ByteArrayOutputStream captured = new ByteArrayOutputStream();
Filter filter = SimpleFileServer.createOutputFilter(
        captured, SimpleFileServer.OutputLevel.INFO);

context.getFilters().add(filter);
~~~

Sau khi gửi request và bảo đảm exchange đã được xử lý:

~~~java
String logText = new String(
        captured.toByteArray(), StandardCharsets.UTF_8);
~~~

Ưu điểm:

- Test không phải tạo và xóa log file.
- Có thể kiểm tra log chứa request path hoặc status mong đợi.
- Không phụ thuộc charset mặc định của máy.

Không nên assert toàn bộ dòng log với thời gian, địa chỉ client hoặc định dạng phụ thuộc runtime nếu test không có mục tiêu kiểm tra các trường đó. Hãy kiểm tra phần ổn định mà bài test thực sự cần, chẳng hạn request method/path hoặc status code.

## 8. System.out và OutputStream file: khác nhau ở quyền sở hữu

### Dùng System.out

~~~java
Filter filter = SimpleFileServer.createOutputFilter(
        System.out, OutputLevel.INFO);
context.getFilters().add(filter);
~~~

`System.out` là stream dùng chung của tiến trình. Ứng dụng không nên đóng nó sau khi server dừng; chỉ dừng server là đủ. Nếu dùng `System.out` cho nhiều thành phần, log có thể xen kẽ với thông báo khác của ứng dụng.

### Dùng file stream

~~~java
try (OutputStream out = Files.newOutputStream(
        logFile,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND)) {
    Filter filter = SimpleFileServer.createOutputFilter(out, OutputLevel.INFO);
    context.getFilters().add(filter);
    // Giữ out mở trong suốt thời gian server có thể ghi log.
}
~~~

Đoạn trên chỉ minh họa cách mở stream và tạo filter; trong chương trình chạy thật, phải gọi `server.stop(delay)` **trước khi thoát khỏi try-with-resources**. Nếu thoát khỏi block khi server còn chạy, stream sẽ bị đóng trong lúc filter vẫn có thể được gọi.

Với file log dài hạn, cần tự thiết kế thêm chính sách:

- Đặt log ở thư mục riêng, ngoài root đang phục vụ.
- Kiểm soát quyền đọc/ghi file log.
- Xoay vòng file và giới hạn dung lượng nếu cần.
- Xác định thời gian lưu và cách xóa log.
- Che dữ liệu nhạy cảm trước khi ghi nếu nghiệp vụ yêu cầu.

`createOutputFilter` chỉ nhận một OutputStream; nó không cung cấp tham số cấu hình rotation, retention hoặc redaction.

## 9. Lỗi thường gặp khi quản lý stream

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `IllegalArgumentException` khi tạo filter | Truyền `OutputLevel.NONE`. | Không gắn filter nếu không cần log. |
| `NullPointerException` | `out` hoặc `outputLevel` là null. | Truyền stream và mức log hợp lệ. |
| Log có ký tự lỗi khi đọc file trên máy khác | Đọc bằng charset không phải UTF-8. | Dùng `Files.readString(path, UTF_8)` hoặc `new String(bytes, UTF_8)`. |
| Không thấy nội dung log ngay khi đọc | Stream còn mở hoặc dữ liệu đang được buffer. | Dừng server rồi flush/close stream trước khi đọc. |
| IOException khi ghi log | Stream đã đóng, đích ghi gặp lỗi hoặc không còn khả dụng. | Giữ stream mở trong thời gian server chạy; kiểm tra quyền và dung lượng đích ghi. |
| Server vẫn xử lý request nhưng log không được ghi | Filter không gắn vào context đã xử lý request hoặc filter được thêm quá muộn. | Gắn filter trước `start()` vào đúng context. |
| Đóng System.out làm các log khác biến mất | Đóng stream dùng chung của tiến trình. | Không đóng System.out. |
| File log có thể tải qua HTTP | Log nằm trong root directory đang phục vụ. | Đặt log ngoài root và giới hạn quyền file. |
| Nhiều request ghi vào stream tùy biến gây lỗi | Stream tự viết không hỗ trợ ghi đồng thời an toàn. | Dùng stream phù hợp hoặc đồng bộ thao tác ghi theo hợp đồng stream. |

## 10. Quy trình lifecycle nên áp dụng

Với stream do ứng dụng sở hữu, giữ thứ tự sau:

~~~text
1. Mở OutputStream
       |
       v
2. Tạo createOutputFilter(out, INFO/VERBOSE)
       |
       v
3. Gắn Filter vào HttpContext
       |
       v
4. server.start()
       |
       v
5. Xử lý HTTP exchanges và ghi log
       |
       v
6. server.stop(delay)
       |
       v
7. flush/close OutputStream
       |
       v
8. Đọc, lưu trữ hoặc xoay vòng log
~~~

Nếu stream là `System.out`, bỏ bước close. Nếu stream là file hoặc resource do ứng dụng mở, dùng try-with-resources để đóng tự động sau khi server đã dừng. Nếu nhiều server/context dùng chung một stream, chỉ đóng sau khi **tất cả** server có thể ghi vào stream đó đã dừng.

## 11. Câu hỏi tự kiểm tra

1. `createOutputFilter(out, level)` trả về kiểu gì và filter chạy ở giai đoạn nào của exchange?
2. Vì sao log được ghi vào OutputStream theo UTF-8 dù OutputStream chỉ xử lý byte?
3. Những giá trị OutputLevel nào hợp lệ với factory này? Vì sao NONE không hợp lệ?
4. Ai nên sở hữu và đóng file OutputStream được truyền vào filter?
5. Vì sao phải dừng server trước khi đóng stream log?
6. Khác biệt lifecycle giữa System.out và FileOutputStream do ứng dụng mở là gì?
7. Khi đọc log file, vì sao cần chỉ định StandardCharsets.UTF_8?
8. Vì sao không nên đặt file log bên trong rootDirectory của SimpleFileServer?
9. Nếu nhiều context dùng cùng filter/stream, khi nào mới được đóng stream?
10. createOutputFilter có tự cung cấp rotation, retention hoặc redaction không?

**Bài thực hành:** chạy `OutputFilterFileDemo`, kiểm tra log được tạo và đọc bằng UTF-8. Thay `INFO` bằng `VERBOSE` trên dữ liệu giả lập để so sánh mức chi tiết. Sau đó thử cố ý đóng log stream trước khi gửi request để hiểu vì sao lifecycle sai có thể làm lỗi bước ghi log; khôi phục thứ tự stop server rồi close stream.

## Tài liệu tham khảo chính thức

- [Oracle JDK 27 — `SimpleFileServer.createOutputFilter`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): hợp đồng OutputStream, UTF-8, post-processing filter, OutputLevel.NONE và ngoại lệ.
- [Oracle JDK 27 — `Filter`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/Filter.html): cách filter tham gia chuỗi xử lý HTTP exchange.
- [Oracle JDK 27 — `HttpContext`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): danh sách filter gắn theo context.
- [Oracle JDK 27 — `HttpServer.stop(int)`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): dừng server và thời gian chờ xử lý exchange.
- [Oracle JDK 27 — `OutputStream`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/OutputStream.html): hợp đồng ghi, flush và close stream byte.
- [Oracle JDK 18 — `SimpleFileServer`](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): API được giới thiệu từ Java 18.
