# Thực hành dựng máy chủ fixture độc lập với thư mục tạm, cổng động và cleanup xác định

## 1. Mục tiêu và phạm vi

Trong module **JAVA_VERSION_JAVA18**, API `com.sun.net.httpserver.SimpleFileServer` được giới thiệu từ Java 18 (JEP 408) và vẫn có ích trên các JDK hiện đại để phục vụ file tĩnh trong **test, phát triển và gỡ lỗi**. Ở chương **API SimpleFileServer**, bài này tập trung vào việc dựng một fixture HTTP có vòng đời rõ ràng, để mỗi test sở hữu dữ liệu và tài nguyên mạng của chính nó.

Sau bài này, bạn sẽ biết cách:

1. Tạo một **thư mục tạm riêng** cho từng fixture, ghi vào đó các file cần phục vụ.
2. Chỉ bind server vào **địa chỉ loopback** và yêu cầu hệ điều hành cấp **cổng động** bằng port `0`.
3. Lấy cổng thật sau khi server được bind, tạo URI để client gửi request, không hard-code `8080` hay một cổng cố định.
4. Xác minh response bằng status HTTP và **byte chính xác** của payload, bao gồm cả UTF-8 và dữ liệu nhị phân.
5. Dừng server và xóa toàn bộ thư mục tạm qua `try-with-resources`, kể cả khi assertion ném exception.
6. Chạy hai fixture đồng thời mà không dùng chung thư mục, cổng hay dữ liệu.

**Phạm vi:** bài dùng HTTP trong máy cục bộ. `SimpleFileServer` không cung cấp các tính năng cần cho máy chủ công khai như xác thực, phân quyền hay cấu hình bảo mật sản xuất; sử dụng nó đúng mục đích fixture/test theo hợp đồng API còn được hỗ trợ.

## 2. Ba nguồn gây thiếu ổn định trong test HTTP

Một test dùng file server thường gặp ba vấn đề:

| Nguồn gây lỗi | Ví dụ không ổn định | Cách xử lý trong bài |
| --- | --- | --- |
| **Trùng cổng** | Nhiều test cùng dùng port `8080`, gây `BindException` khi chạy song song | Bind port `0`; lấy cổng thực tế từ `server.getAddress().getPort()` |
| **Trùng dữ liệu** | Các test cùng dùng một thư mục `fixtures/` và ghi đè `sample.txt` | Mỗi fixture có `Files.createTempDirectory(...)` riêng |
| **Rò rỉ tài nguyên** | Assertion thất bại làm server còn chạy, file tạm còn trên đĩa | Fixture `AutoCloseable`; đóng server trước, xóa cây thư mục sau |

Không thử “giữ chỗ” một cổng bằng `ServerSocket(0)`, đóng socket đó rồi bind server vào cổng vừa lấy. Có khoảng trống thời gian để tiến trình khác chiếm cổng (race condition). Hãy để **chính `SimpleFileServer`** bind trực tiếp vào port `0`, sau đó đọc cổng đã được cấp.

Tương tự, `File.deleteOnExit()` chỉ chạy khi JVM kết thúc và không cung cấp một thời điểm cleanup xác định cho từng test. Với fixture độc lập, giải phóng tài nguyên ngay khi ra khỏi phạm vi `try-with-resources`.

## 3. API cần dùng trên JDK hiện đại

### 3.1. `SimpleFileServer.createFileServer`

Phương thức:

```java
HttpServer server = SimpleFileServer.createFileServer(
        address,
        absoluteRootDirectory,
        SimpleFileServer.OutputLevel.NONE
);
```

- `address` là `InetSocketAddress` dùng để bind. Port `0` có nghĩa hệ điều hành chọn cổng đang rảnh.
- `absoluteRootDirectory` phải là **đường dẫn tuyệt đối**, tồn tại, là thư mục và có thể đọc. Nếu không đạt, phương thức báo lỗi.
- `OutputLevel.NONE` tắt log HTTP của simple file server trong test, giúp output ít nhiễu. Có thể dùng `INFO` hoặc `VERBOSE` khi điều tra lỗi.
- Phương thức trả về `HttpServer` **chưa được start**, nhưng đã bind địa chỉ. Gọi `start()` để bắt đầu xử lý request; đọc `getAddress().getPort()` để lấy cổng được cấp.

`SimpleFileServer` mặc định tạo handler phục vụ file và thư mục con từ gốc. Handler của nó xử lý `GET`/`HEAD`, trả `405` cho phương thức khác; file không tồn tại thường trả `404`. Đừng khẳng định nội dung HTML directory listing hay header `Content-Type` phải giống hệt trên mọi hệ điều hành: việc nhận diện MIME có thể dựa vào bảng MIME của môi trường.

### 3.2. Bind vào loopback thay vì mọi interface

Trong ví dụ, dùng:

```java
InetSocketAddress address = new InetSocketAddress("127.0.0.1", 0);
```

`127.0.0.1` giới hạn việc lắng nghe vào IPv4 loopback cục bộ; port `0` để OS cấp cổng. Đây là lựa chọn đơn giản cho máy Windows/Linux thông dụng. Trong môi trường IPv6-only, có thể thay bằng địa chỉ loopback IPv6 và tạo URI với host IPv6 đúng cú pháp.

Tránh `new InetSocketAddress(0)` trong fixture nếu mục tiêu là chỉ cho client trên cùng máy truy cập: địa chỉ wildcard có thể lắng nghe trên nhiều interface. Một server phục vụ file tạm dùng cho test nên giới hạn phạm vi truy cập ngay khi bind.

### 3.3. Dừng server

`HttpServer.stop(int delay)` ngừng nhận request mới, chờ các exchange đang xử lý hoàn thành hoặc đến giới hạn thời gian `delay` tính bằng giây, rồi đóng connection và kết thúc luồng server. `stop(0)` phù hợp sau khi test đã nhận trọn response. Một `HttpServer` đã stop không thể start lại; fixture mới cần server mới.

Dùng `try-with-resources` bằng cách bọc `HttpServer` trong một lớp fixture tự triển khai `AutoCloseable`. Việc dừng server phải xảy ra **trước khi xóa file tạm**, đặc biệt trên Windows nơi một file còn được server sử dụng có thể chưa xóa được.

## 4. Vòng đời fixture cần kiểm soát

```text
Mỗi lần chạy test
       |
       v
createTempDirectory()  -> thư mục fixture riêng
       |
       v
Ghi file text UTF-8 + file nhị phân
       |
       v
createFileServer(loopback, port 0, root, NONE)
       |
       v
server.start() -> lấy server.getAddress().getPort()
       |
       v
HTTP client: GET, so status/byte, kiểm tra 404/405
       |
       v
finally / try-with-resources
       |
       v
server.stop(0) -> đóng trao đổi HTTP
       |
       v
Files.walk(root) -> xóa con trước, xóa root sau
       |
       v
Không còn thư mục/cổng do fixture giữ
```

Với hai fixture đồng thời, thứ tự trên được thực hiện cho từng fixture; dữ liệu của A không được ghi vào root của B. Khi test lỗi giữa chừng, cleanup vẫn được gọi. Nếu cleanup thất bại, test phải nhìn thấy lỗi đó để không che giấu rò rỉ tài nguyên.

## 5. Chương trình hoàn chỉnh: hai fixture độc lập

Lưu nội dung sau thành `SimpleFileServerFixtureLab.java` bằng UTF-8. Chương trình dùng API có từ Java 18 và kiểm tra cả file văn bản lẫn dữ liệu nhị phân.

```java
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;

public final class SimpleFileServerFixtureLab {
    private static final String A = "Fixture A | Xin chào 🚀\n";
    private static final String B = "Fixture B | Nội dung khác\n";
    private static final byte[] BINARY = {
            0x00, 0x01, (byte) 0x80, (byte) 0xFF
    };

    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        Path oldRootA = null;
        Path oldRootB = null;

        try (Fixture first = Fixture.start(A);
             Fixture second = Fixture.start(B)) {
            oldRootA = first.root();
            oldRootB = second.root();

            check(!oldRootA.equals(oldRootB), "Fixture trùng thư mục");
            check(first.port() != second.port(), "Fixture trùng cổng");
            check(first.port() > 0 && second.port() > 0, "Cổng không hợp lệ");

            assertGetBytes(client, first.uri("message.txt"),
                    A.getBytes(StandardCharsets.UTF_8));
            assertGetBytes(client, second.uri("message.txt"),
                    B.getBytes(StandardCharsets.UTF_8));
            assertGetBytes(client, first.uri("assets/raw.bin"), BINARY);

            HttpResponse<byte[]> missing = client.send(
                    HttpRequest.newBuilder(first.uri("missing.txt"))
                            .timeout(Duration.ofSeconds(5))
                            .GET().build(),
                    HttpResponse.BodyHandlers.ofByteArray());
            check(missing.statusCode() == 404, "File thiếu phải trả 404");

            HttpResponse<byte[]> post = client.send(
                    HttpRequest.newBuilder(first.uri("message.txt"))
                            .timeout(Duration.ofSeconds(5))
                            .POST(HttpRequest.BodyPublishers.noBody()).build(),
                    HttpResponse.BodyHandlers.ofByteArray());
            check(post.statusCode() == 405, "File handler chỉ nhận GET/HEAD");

            System.out.println("FIXTURE_A=" + first.baseUri());
            System.out.println("FIXTURE_B=" + second.baseUri());
            System.out.println("HTTP_ASSERTIONS=PASS");
        } // Tự đóng second, rồi first, kể cả khi assertion thất bại.

        check(oldRootA != null && Files.notExists(oldRootA),
                "Thư mục fixture A còn tồn tại");
        check(oldRootB != null && Files.notExists(oldRootB),
                "Thư mục fixture B còn tồn tại");
        System.out.println("CLEANUP=PASS");
    }

    private static void assertGetBytes(
            HttpClient client, URI uri, byte[] expected) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5)).GET().build();
        HttpResponse<byte[]> response = client.send(
                request, HttpResponse.BodyHandlers.ofByteArray());

        check(response.statusCode() == 200,
                "GET " + uri + " trả " + response.statusCode());
        check(Arrays.equals(expected, response.body()),
                "Nội dung byte không khớp: " + uri);
    }

    private static void check(boolean valid, String message) {
        if (!valid) throw new AssertionError(message);
    }

    // Mỗi instance sở hữu riêng root, HttpServer và cổng động.
    private static final class Fixture implements AutoCloseable {
        private final Path root;
        private final HttpServer server;
        private final URI baseUri;
        private boolean closed;

        private Fixture(Path root, HttpServer server, URI baseUri) {
            this.root = root;
            this.server = server;
            this.baseUri = baseUri;
        }

        static Fixture start(String content) throws IOException {
            Path root = Files.createTempDirectory("sfs-fixture-")
                    .toAbsolutePath().normalize();
            HttpServer server = null;
            try {
                Files.writeString(root.resolve("message.txt"),
                        content, StandardCharsets.UTF_8);
                Path assets = Files.createDirectories(root.resolve("assets"));
                Files.write(assets.resolve("raw.bin"), BINARY);

                // Port 0: để chính server bind vào cổng do OS cấp.
                InetSocketAddress address =
                        new InetSocketAddress("127.0.0.1", 0);
                server = SimpleFileServer.createFileServer(
                        address, root, SimpleFileServer.OutputLevel.NONE);
                server.start();

                int port = server.getAddress().getPort();
                if (port <= 0) {
                    throw new IllegalStateException("Không lấy được cổng");
                }
                URI base = URI.create("http://127.0.0.1:" + port + "/");
                return new Fixture(root, server, base);
            } catch (IOException | RuntimeException failure) {
                // Khởi tạo thất bại vẫn không được để lại file/socket.
                if (server != null) server.stop(0);
                try {
                    deleteTree(root);
                } catch (IOException cleanup) {
                    failure.addSuppressed(cleanup);
                }
                throw failure;
            }
        }

        Path root() {
            return root;
        }

        int port() {
            return server.getAddress().getPort();
        }

        URI baseUri() {
            return baseUri;
        }

        URI uri(String relativePath) {
            return baseUri.resolve(relativePath);
        }

        @Override
        public synchronized void close() throws IOException {
            if (closed) return;
            closed = true;
            server.stop(0);
            deleteTree(root);
        }

        private static void deleteTree(Path root) throws IOException {
            if (Files.notExists(root)) return;

            List<Path> paths;
            // Files.walk mặc định không đi theo symbolic link.
            try (Stream<Path> stream = Files.walk(root)) {
                paths = stream.sorted(Comparator.reverseOrder()).toList();
            }

            IOException first = null;
            for (Path path : paths) {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException e) {
                    if (first == null) first = e;
                    else first.addSuppressed(e);
                }
            }
            if (first != null) throw first;
        }
    }
}
```

### 5.1. Biên dịch và chạy trên JDK 18+

```bash
javac -encoding UTF-8 --add-modules jdk.httpserver SimpleFileServerFixtureLab.java
java --add-modules jdk.httpserver SimpleFileServerFixtureLab
```

Ví dụ dùng classpath; tùy chọn `--add-modules jdk.httpserver` thể hiện rõ phụ thuộc tới module chứa `SimpleFileServer`. Nếu ứng dụng là named module, khai báo `requires jdk.httpserver;` trong `module-info.java`. Các lệnh trên cũng chạy trong PowerShell/Command Prompt có JDK trong `PATH`.

Output minh họa (cổng được OS chọn, không cố định):

```text
FIXTURE_A=http://127.0.0.1:51841/
FIXTURE_B=http://127.0.0.1:51842/
HTTP_ASSERTIONS=PASS
CLEANUP=PASS
```

Không assert số cổng cụ thể, thứ tự số cổng hay số cổng phải liên tiếp. Test chỉ cần biết URI thực do fixture cung cấp và kiểm chứng hai server hoạt động độc lập.

### 5.2. Tại sao các assertion này có giá trị?

- `first` và `second` có root riêng dù đều phục vụ endpoint `/message.txt`. Mỗi GET được so với **byte UTF-8** của nội dung riêng; điều này phát hiện dùng nhầm dữ liệu fixture.
- File `assets/raw.bin` được đối chiếu bằng `Arrays.equals(byte[], byte[])`, không qua decoder văn bản; byte `80` và `FF` có thể không là UTF-8 hợp lệ nhưng là dữ liệu nhị phân hợp lệ.
- Test `404` chỉ dựa vào status khi file không tồn tại. Test `405` dựa vào hợp đồng handler chỉ nhận `GET`/`HEAD`. Tránh so sánh nguyên văn HTML body của error hoặc directory listing.
- `HttpClient.send` và `BodyHandlers.ofByteArray()` đảm bảo response body đã được nhận trước khi đóng server. Timeout kết nối và request giúp sự cố mạng báo lỗi có giới hạn.
- Khi ra khỏi `try-with-resources`, Java đóng B rồi A. Nếu assertion ném lỗi, `close()` vẫn được gọi; nếu cleanup cũng lỗi, Java giữ lỗi cleanup dưới dạng exception bị suppressed.

Chương trình không dùng `Thread.sleep()` để đoán server đã khởi động. `createFileServer` đã bind cổng trước `start()`; sau `start()` client dùng đúng URI đã công bố. Không dùng cú pháp `try (HttpClient client = ...)` để giữ tương thích với API của Java 18: khả năng đóng `HttpClient` qua `AutoCloseable` được bổ sung ở các JDK sau đó.

## 6. Cleanup có thể dự đoán: cả đường thành công lẫn đường lỗi

Cleanup “xác định” nghĩa là test có một **điểm kết thúc vòng đời được lập trình rõ ràng**, không phụ thuộc garbage collector hoặc thời điểm JVM thoát.

### 6.1. Ba đường kết thúc quan trọng

| Tình huống | Ai cleanup? | Điều cần xác minh |
| --- | --- | --- |
| Tạo server và chạy test thành công | `Fixture.close()` khi rời `try-with-resources` | Server ngừng nhận request, thư mục tạm được xóa |
| Tạo fixture thành công nhưng assertion thất bại | `try-with-resources` vẫn gọi `close()` | Lỗi assertion được giữ; không rò rỉ server/root |
| Tạo root xong, ghi file hoặc start server thất bại | `catch` trong `Fixture.start()` | Nếu đã có server thì stop; xóa root; giữ nguyên lỗi gốc và đính kèm lỗi cleanup |

Trong đường thành công, `Files.notExists(root)` sau khi rời block cho bằng chứng thư mục đã biến mất. Trong đường lỗi, Java không thực thi các câu lệnh sau block nếu exception chưa được xử lý, nhưng lời gọi `close` vẫn diễn ra.

Nếu muốn kiểm tra cleanup của một test dự kiến thất bại, hãy lưu path rồi kiểm tra trong một block `finally` của test harness. Không cần tạo thêm một “cleanup hook” toàn cục khi mỗi fixture đã quản lý được tài nguyên của mình.

### 6.2. Vì sao stop server trước khi delete?

Server có thể đang giữ socket HTTP hoặc đọc file để gửi response. Khi dùng `stop(0)` sau khi client đã đọc hết body, server ngừng nhận request mới; sau đó xóa file tạm và thư mục gốc. Trên Windows, việc xóa file đang có handle còn mở có thể thất bại; vì vậy thứ tự cleanup phải thể hiện rõ.

Không dùng `Thread.sleep` trong `close` để “chờ thêm một chút”. Thay vào đó, dùng các request đồng bộ đã hoàn tất và gọi `stop`. Nếu test có request bất đồng bộ, phải đợi `CompletableFuture` hoặc exchange kết thúc trước khi cleanup. `stop(0)` không phải cơ chế đợi vô hạn để mọi tác vụ nền hoàn thành.

### 6.3. Tại sao xóa file con trước thư mục cha?

`Files.delete(root)` sẽ lỗi nếu thư mục chưa rỗng. Ví dụ thu thập đường dẫn bằng `Files.walk(root)` rồi sắp xếp theo thứ tự ngược sẽ xóa các file và thư mục con trước `root`. `Files.walk` mặc định không theo symbolic link, nên một link nằm trong fixture không làm phép duyệt đi ra ngoài gốc.

Không chuyển cấu hình sang `FOLLOW_LINKS` chỉ để “dọn sạch hơn”; điều đó có thể dẫn tới duyệt ra ngoài thư mục fixture. Đồng thời, chỉ xóa chính `root` mà test đã tạo, không dùng thư mục làm việc của dự án hoặc một đường dẫn do người dùng nhập để chạy cleanup đệ quy.

### 6.4. Không nuốt lỗi cleanup

Nếu không xóa được file tạm, `close()` nên báo `IOException`. Nếu assertion cũng thất bại, cơ chế `try-with-resources` lưu lỗi cleanup dưới dạng suppressed exception; như vậy người sửa test có đủ thông tin về cả lỗi chính lẫn tài nguyên còn sót.

Tránh `catch (Exception ignored) {}` trong đường cleanup. Các lỗi quyền file, file còn mở hoặc antivirus đang quét có thể giải thích vì sao test chỉ thất bại trên một hệ điều hành.

## 7. Tích hợp vào JUnit hoặc test runner

Trong bộ test lớn, bạn có thể chuyển lớp `Fixture` thành một helper dùng chung trong source set test. Mỗi test tạo fixture mới; khi dùng JUnit Jupiter, đặt fixture trong `try-with-resources` ngay trong test method:

```java
@Test
void shouldServeFixtureFile() throws Exception {
    try (Fixture fixture = Fixture.start("Nội dung của test này\n")) {
        URI target = fixture.uri("message.txt");
        // Gửi GET, xác nhận status 200 và body byte chính xác.
    }
} // Fixture.close() được gọi kể cả khi assertion thất bại.
```

Đây là minh họa vị trí sử dụng helper; cần import `org.junit.jupiter.api.Test` khi đặt trong một dự án có JUnit. Nếu không có JUnit, chương trình độc lập ở mục 5 là đủ để thực hành.

Có thể dùng `@TempDir` của JUnit để tạo thư mục tạm và để JUnit tự dọn, nhưng hãy chọn **một chủ sở hữu rõ ràng** cho vòng đời thư mục. Khi helper tự tạo temp root và thực hiện cleanup như ví dụ, không cần để JUnit xóa lần thứ hai. Test runner nào cũng phải đảm bảo server được stop trước khi thư mục bị xóa.

### 7.1. Khi chạy test song song

Hai fixture được phép sống đồng thời:

- Root được tạo bằng `Files.createTempDirectory`, có đường dẫn riêng.
- Mỗi `SimpleFileServer` bind port `0` ngay trong quá trình tạo server; OS cấp cổng đang khả dụng.
- URI được lấy từ chính instance fixture, không dùng biến môi trường “global test port” hoặc trường `static` mutable dùng chung.
- File name trùng nhau không phải vấn đề vì các root tách biệt.
- Mỗi test đóng fixture của chính mình ở cuối test, không dùng một phép cleanup toàn cục xóa nhầm root của test khác.

Nếu cần fixture dùng chung cho cả một test class, cấu hình lifecycle theo test framework và đảm bảo mọi request hoàn tất trước khi teardown. Tuy nhiên, với bài tập xác minh sự độc lập, mỗi test sở hữu một fixture mới giúp giảm dữ liệu bị chia sẻ ngoài ý muốn.

## 8. Các lỗi thường gặp khi xây fixture

| Biểu hiện | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `BindException: Address already in use` | Dùng cổng cố định, hoặc bind wildcard trùng server khác | Dùng loopback và port `0` |
| Client gửi request vào cổng `0` hoặc `8080` | Không lấy cổng thật từ `server.getAddress()` | Tạo URI từ cổng bound của server |
| `IllegalArgumentException` khi tạo server | Root không tồn tại, không tuyệt đối, không phải thư mục, hoặc không đọc được | Tạo root bằng `Files.createTempDirectory` trước |
| `404` cho file đáng lẽ có | File ghi vào thư mục khác hoặc URI sai | Kiểm tra `root.resolve(relativePath)` và `fixture.uri(relativePath)` |
| GET trả đúng chữ nhưng test sai | Khác newline, UTF-8 hoặc byte ký tự | So sánh `byte[]` thay vì chỉ nhìn terminal |
| Test chỉ lỗi trên Windows khi xóa file | Client/server còn mở file hoặc đường xử lý chưa hoàn thành | Đọc trọn response, `server.stop(0)` trước khi xóa |
| Test song song ảnh hưởng nhau | Dùng root chung hoặc cổng cấu hình chung | Mỗi test một fixture instance |
| Assertion thất bại khiến file tạm còn | Cleanup ở cuối method, không trong `finally`/`close` | Bọc fixture bằng `try-with-resources` |
| Test đúng ở một máy, sai Content-Type | MIME được nhận diện theo môi trường | Kiểm tra status và byte theo hợp đồng; không cố định MIME nếu không cần |

### 8.1. Khi nào không nên dùng SimpleFileServer?

Simple file server phù hợp test tài nguyên tĩnh: HTML, JSON fixture, file tải xuống nhỏ, ảnh hoặc byte nhị phân. Nếu test cần endpoint thay đổi trạng thái, xác thực, multipart upload, streaming có điều kiện hoặc phản hồi tùy biến, hãy dùng `HttpServer` với `HttpHandler` phù hợp hoặc một mock server chuyên dụng.

Không đưa thư mục chứa thông tin nhạy cảm vào root, kể cả khi bind loopback. API này được thiết kế cho testing/development, không phải máy chủ web công khai.

## 9. Checklist trước khi chốt một fixture

1. Root được tạo tạm, là đường dẫn tuyệt đối và chỉ chứa dữ liệu test.
2. Server bind vào loopback với port `0`; URI dùng cổng trả về từ `getAddress()`.
3. Không sử dụng port cố định, `Thread.sleep` để đợi server, hoặc biến trạng thái mutable dùng chung.
4. Dữ liệu test ghi rõ charset, ví dụ `Files.writeString(..., StandardCharsets.UTF_8)`.
5. Client có connect timeout và request timeout; đọc trọn body trước teardown.
6. Assertion so status và byte; tránh phụ thuộc listing HTML hoặc MIME đoán theo môi trường.
7. `close()` stop server trước rồi xóa thư mục con → thư mục cha.
8. Cleanup chạy cả khi setup thất bại hoặc assertion thất bại.
9. Lỗi cleanup được báo lại, không bị im lặng bỏ qua.
10. Chạy hai fixture song song để chứng minh tách biệt root, port, nội dung.

## 10. Bài thực hành mở rộng

**Bài A — độc lập dữ liệu:** đổi nội dung fixture A thành `"Đơn hàng A"` và B thành `"Đơn hàng B"`. Cùng GET `/message.txt` ở hai URI, xác nhận byte trả về không lẫn nhau.

**Bài B — kiểm tra lỗi có chủ đích:** sửa một assertion để kỳ vọng sai. Xác nhận test thất bại và quan sát cleanup vẫn diễn ra; khôi phục assertion đúng sau khi thực hành.

**Bài C — dữ liệu nhị phân:** thêm `assets/payload.bin` chứa toàn bộ byte từ `00` đến `FF`. Gửi GET và so bằng `Arrays.equals`; đừng chuyển byte nhị phân thành String để kiểm tra.

**Bài D — dọn dẹp trên Windows/Linux:** chạy chương trình liên tiếp nhiều lần và kiểm tra không còn thư mục tạm `sfs-fixture-*` mới hoặc server cũ giữ cổng. Vì cổng là động, hai lần chạy không cần nhận cùng số cổng.

**Bài E — teardown khi setup lỗi:** gây lỗi tạo file hoặc root không đọc được trong bản sao chương trình thử nghiệm. Đối chiếu exception ban đầu và exception cleanup (nếu có), xác nhận không có server bị bỏ quên.

**Tiêu chí hoàn thành:** có thể tạo fixture độc lập, cấp phát cổng động đúng cách, lấy URI từ server đã bind, kiểm thử HTTP bằng byte và status, và thu hồi server + thư mục tạm theo một vòng đời rõ ràng kể cả khi test thất bại.

### Tài liệu tham khảo

- [JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): mục tiêu và phạm vi API từ JDK 18.
- [SimpleFileServer — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): `createFileServer`, `OutputLevel`, GET/HEAD, phục vụ file/directory.
- [HttpServer — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `getAddress()`, `start()`, `stop(int)`.
- [Files — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html): `createTempDirectory`, `walk`, `deleteIfExists`.
- [HttpClient — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client và `BodyHandlers`.
