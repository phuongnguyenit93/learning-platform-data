# Thực hành tài liệu hóa bộ đọc UTF-8 và máy chủ fixture bằng snippet được kiểm thử

## 1. Mục tiêu: ví dụ trong Javadoc phải khớp hành vi chạy thật

Tài liệu API thường chứa ví dụ đọc file, xử lý dữ liệu hoặc khởi động một dịch vụ nhỏ. Ví dụ có thể nhìn đúng nhưng vẫn lỗi khi sao chép vì thiếu import, dùng API không tồn tại ở JDK mục tiêu, quên đóng tài nguyên hoặc dựa vào charset mặc định của máy.

Java 18 bổ sung hai khả năng hữu ích cho quy trình tài liệu hóa:

- **JEP 413 — Code Snippets in Java API Documentation:** Standard Doclet hỗ trợ tag `{@snippet}` để trình bày đoạn mã có cấu trúc, lấy từ comment hoặc file nguồn bên ngoài.
- **JEP 408 — Simple Web Server:** JDK có `SimpleFileServer` và công cụ `jwebserver` để phục vụ file tĩnh, hữu ích khi tạo fixture cho kiểm thử HTTP.

Bài này kết hợp chúng thành một quy trình có thể lặp lại:

1. Xây dựng API đọc UTF-8 với hợp đồng rõ ràng.
2. Viết ví dụ sử dụng trong file nguồn độc lập.
3. Đưa một vùng mã từ file đó vào Javadoc bằng `{@snippet}`.
4. Biên dịch và chạy test cho chính file ví dụ.
5. Khởi động máy chủ fixture trên loopback và kiểm tra response bằng HTTP client.
6. Sinh Javadoc và xem HTML kết quả để xác nhận snippet được lấy đúng.

`javadoc` hiển thị và xử lý tag snippet, nhưng **không tự biên dịch hoặc chạy mã trong snippet**. Việc kiểm thử phải được thực hiện bằng compiler, test framework hoặc công cụ riêng.

## 2. Phân biệt ba bước: viết mã, kiểm thử và trình bày

Một quy trình tài liệu tốt giữ ba hoạt động liên kết nhưng độc lập:

| Hoạt động | Công cụ | Điều cần xác nhận |
| --- | --- | --- |
| Viết mã mẫu | Java source và Javadoc comment | Ví dụ đúng ngữ cảnh, có import và hợp đồng |
| Kiểm thử mã mẫu | `javac`, JUnit hoặc test runner | Mã biên dịch, chạy và cho kết quả mong đợi |
| Sinh tài liệu | `javadoc` Standard Doclet | Snippet được tìm thấy, định dạng và liên kết đúng |

```text
Utf8Text.java + Utf8TextExample.java
              |
              +----> javac / test compile
              |              |
              |              v
              |        JUnit kiểm thử
              |
              +----> javadoc --snippet-path
                             |
                             v
                      HTML API docs
                             |
                             v
                  Review snippet được render
```

Không nên coi việc Javadoc sinh HTML thành công là bằng chứng đoạn mã chạy được. Ngược lại, test pass cũng không chứng minh Javadoc tìm đúng file, đúng region hoặc hiển thị như mong đợi. Cần kiểm tra cả hai.

## 3. Hợp đồng của bộ đọc UTF-8

Trước khi viết snippet, xác định hành vi mà API công bố. Một bộ đọc file UTF-8 đơn giản có thể cam kết:

- File được decode bằng UTF-8 tường minh.
- Byte sequence malformed hoặc unmappable gây `IOException` khi đọc.
- Nội dung và line separator được giữ nguyên nếu đọc toàn bộ thành `String`.
- BOM UTF-8, nếu có, được decode thành ký tự `U+FEFF`; API không tự ý xóa BOM.
- Nếu trả `Reader` cho caller, caller chịu trách nhiệm đóng reader.
- Nếu trả `String`, toàn bộ nội dung được giữ trong bộ nhớ; không dùng cho file rất lớn.

Từ Java 18, default charset thông thường của JVM là UTF-8 theo JEP 400. Tuy vậy, API nên nêu rõ UTF-8 trong hợp đồng và gọi `Files.newBufferedReader(path, StandardCharsets.UTF_8)`. Điều này giúp code giữ đúng định dạng ngay cả khi chạy ở chế độ tương thích hoặc khi default charset của tiến trình được cấu hình khác.

## 4. Cài đặt API mở Reader UTF-8

Một API nhỏ có thể cung cấp hai phương thức: mở reader để xử lý streaming, và đọc toàn bộ file khi kích thước phù hợp.

```java
package com.example.docs;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Utf8Text {
    private Utf8Text() {
    }

    public static BufferedReader open(Path path) throws IOException {
        return Files.newBufferedReader(path, StandardCharsets.UTF_8);
    }

    public static String read(Path path) throws IOException {
        try (BufferedReader reader = open(path)) {
            StringWriter result = new StringWriter();
            reader.transferTo(result);
            return result.toString();
        }
    }
}
```

`Files.newBufferedReader(path, charset)` trả về `BufferedReader` và dùng charset được truyền vào. Các thao tác đọc báo `IOException` nếu gặp byte sequence malformed hoặc unmappable.

`Reader.transferTo(Writer)` có từ Java 10. Nó chuyển toàn bộ ký tự còn lại sang writer đích, không loại bỏ `\n`, `\r\n` hay line terminator ở cuối file. Vì vậy, phương thức `read` không có hành vi chuẩn hóa newline ngoài ý muốn.

### 4.1. Vì sao cần cả open và read?

`open(Path)` phù hợp khi caller muốn đọc từng dòng hoặc xử lý file lớn mà không giữ toàn bộ nội dung trong heap:

```java
try (BufferedReader reader = Utf8Text.open(path)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
```

`read(Path)` tiện lợi khi file nhỏ, ví dụ fixture hoặc file cấu hình ngắn. Nó tạo `String` chứa toàn bộ nội dung, do đó bộ nhớ cần thiết tăng theo kích thước file.

Không dùng `read(Path)` cho file không giới hạn kích thước hoặc file lớn đến mức không phù hợp với một `String`.

### 4.2. Chính sách BOM phải được ghi rõ

UTF-8 không yêu cầu BOM. Nếu file bắt đầu bằng byte `EF BB BF`, UTF-8 decoder thông thường giải mã ba byte đó thành `U+FEFF` ở đầu `String`. `Files.newBufferedReader` không phải API tự động loại bỏ BOM.

Nếu định dạng fixture cho phép và yêu cầu bỏ BOM, hãy thêm bước xử lý có chủ đích ở tầng byte hoặc ký tự, rồi kiểm thử riêng. Không âm thầm xóa `U+FEFF` khỏi mọi nội dung vì ký tự này cũng có thể là dữ liệu thực.

## 5. Viết Javadoc bằng snippet tag

JEP 413 bổ sung `{@snippet}` cho Standard Doclet từ Java 18. Với ví dụ ngắn, có thể đặt mã ngay trong comment. Đặt tag sau đây bên trong Javadoc comment của method:

```java
{@snippet lang="java" :
try (BufferedReader reader = Utf8Text.open(path)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
}
```

`lang="java"` giúp Standard Doclet và công cụ khác biết loại nội dung đang được trình bày. Snippet inline phù hợp với ví dụ nhỏ, nhưng có một số giới hạn:

- Không được chứa closing delimiter của Java comment.
- Dấu ngoặc nhọn phải cân bằng và lồng đúng thứ tự.
- Unicode escape trong source comment được Java xử lý trước khi Javadoc đọc nội dung.
- Snippet chỉ được hiển thị; nó không tự có import, biến hoặc method context nếu đoạn mã không cung cấp chúng.

Với ví dụ dài hoặc cần kiểm thử, nên đặt code trong file nguồn bên ngoài rồi trích một region.

## 6. External snippet và named region

External snippet cho phép Javadoc lấy nội dung từ file nguồn riêng. Có thể đặt file trong `snippet-files` cạnh package hoặc dùng `--snippet-path` để chỉ định thư mục gốc chứa snippet.

Ví dụ cấu trúc dự án:

```text
project/
├── src/
│   ├── main/
│   │   └── java/
│   │       └── com/example/docs/
│   │           └── Utf8Text.java
│   └── test/
│       └── java/
│           └── com/example/docs/
│               ├── Utf8TextExample.java
│               └── Utf8TextTest.java
└── target/
```

Trong Javadoc của `Utf8Text.open`, tham chiếu một region bằng tag sau:

```java
{@snippet file="com/example/docs/Utf8TextExample.java"
          region="read-with-reader"}
```

File `Utf8TextExample.java` chứa mã đầy đủ và đánh dấu region:

```java
package com.example.docs;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringWriter;
import java.nio.file.Path;

public final class Utf8TextExample {
    private Utf8TextExample() {
    }

    public static String read(Path path) throws IOException {
        // @start region=read-with-reader
        try (BufferedReader reader = Utf8Text.open(path)) {
            StringWriter result = new StringWriter();
            reader.transferTo(result);
            return result.toString();
        }
        // @end region=read-with-reader
    }
}
```

Các dòng `@start region=...` và `@end region=...` là markup comment dành cho snippet. Standard Doclet lấy phần nằm giữa hai marker, không hiển thị marker trong đoạn mã được render.

Vì file ví dụ nằm trong test source, build có thể biên dịch nó cùng test. Javadoc có thể đọc nó qua `--snippet-path src/test/java`.

### 6.1. Region phải ổn định và đủ ngữ cảnh

Một region nên chứa một ví dụ có ý nghĩa độc lập. Nếu region chỉ chứa một dòng như `Utf8Text.open(path)`, người đọc có thể không biết phải đóng reader ở đâu.

Đối với resource có vòng đời, hãy đưa try-with-resources vào region. Với ví dụ cần import, đặt import trong file external snippet để file nguồn có thể biên dịch; phần import không nhất thiết phải được trích vào HTML nếu Javadoc chỉ lấy region method body.

Đặt tên region theo hành vi, chẳng hạn `read-with-reader`, `read-malformed-input` hoặc `start-fixture-server`. Tên ổn định giúp test và tài liệu tham chiếu cùng một đoạn mã.

## 7. Biên dịch snippet như mã nguồn bình thường

`javadoc` không biên dịch snippet. Một cách đơn giản để xác minh external snippet là giữ file đó trong source set test để `javac` và test runner biên dịch nó.

Ví dụ lệnh biên dịch minh họa:

```bash
javac -d target/classes \
  src/main/java/com/example/docs/Utf8Text.java

javac --add-modules jdk.httpserver -cp "target/classes:${TEST_CLASSPATH}" \
  -d target/test-classes \
  src/test/java/com/example/docs/Utf8TextExample.java \
  src/test/java/com/example/docs/Utf8TextTest.java \
  src/test/java/com/example/docs/FixtureServerExample.java \
  src/test/java/com/example/docs/FixtureServerTest.java
```

Ví dụ lệnh trên dùng cú pháp biến môi trường của POSIX shell; `TEST_CLASSPATH` phải chứa các JUnit/test dependency. Trên Windows, dấu phân cách classpath là `;` và cú pháp biến môi trường phụ thuộc shell. Với Maven hoặc Gradle, để source example trong `src/test/java` thường giúp build tool tự quản lý classpath và test dependency.

Nếu snippet chỉ là fragment chứ không phải file Java hoàn chỉnh, tạo test harness bao quanh fragment hoặc trích code vào method có signature cụ thể. Mục tiêu là kiểm tra đúng nội dung được hiển thị, không duy trì một bản sao khác đã bị sửa độc lập.

## 8. Kiểm thử bộ đọc UTF-8 với JUnit

Test nên xác minh cả byte fixture, nội dung Unicode và lỗi malformed. Ví dụ:

```java
package com.example.docs;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class Utf8TextTest {
    @TempDir
    Path tempDir;

    @Test
    void readsUtf8AndPreservesLineTerminators() throws Exception {
        Path file = tempDir.resolve("greeting.txt");
        byte[] expectedBytes =
                "Tiếng Việt 🌍\r\nSecond line\n".getBytes(StandardCharsets.UTF_8);
        Files.write(file, expectedBytes);

        assertArrayEquals(expectedBytes, Files.readAllBytes(file));
        assertEquals(
                "Tiếng Việt 🌍\r\nSecond line\n",
                Utf8Text.read(file));
        assertEquals(
                "Tiếng Việt 🌍\r\nSecond line\n",
                Utf8TextExample.read(file));
    }

    @Test
    void rejectsMalformedUtf8() throws Exception {
        Path file = tempDir.resolve("malformed.txt");
        Files.write(file, new byte[] {(byte) 0xC3, 0x28});

        assertThrows(IOException.class, () -> Utf8Text.read(file));
    }

    @Test
    void preservesUtf8BomAsCharacter() throws Exception {
        Path file = tempDir.resolve("with-bom.txt");
        Files.write(file, new byte[] {
                (byte) 0xEF, (byte) 0xBB, (byte) 0xBF, 0x41
        });

        assertTrue(Utf8Text.read(file).startsWith("\uFEFF"));
    }
}
```

Các test này chứng minh các hợp đồng khác nhau:

- Byte UTF-8 hợp lệ được decode thành đúng Unicode.
- Line terminator được giữ nguyên khi đọc toàn bộ file.
- Byte malformed gây lỗi thay vì bị thay thế âm thầm.
- BOM được giữ lại theo chính sách của API mẫu.

Không chỉ dùng `assertEquals` trên chuỗi được encode và decode bằng cùng default charset. Expected bytes nên được cố định theo fixture hoặc được kiểm tra độc lập.

## 9. Javadoc build với --snippet-path

Khi dùng external snippet, chỉ rõ thư mục chứa snippet trong lệnh `javadoc`:

```bash
javadoc \
  --snippet-path src/test/java \
  -d target/apidocs \
  -sourcepath src/main/java \
  com.example.docs
```

Nếu source package hoặc build layout khác, điều chỉnh `-sourcepath` và package tương ứng. Đường dẫn trong `file="..."` được phân giải tương đối với snippet path.

Sau khi chạy, kiểm tra trang HTML của `Utf8Text`:

- Snippet có xuất hiện đúng nội dung region không?
- Marker `@start`/`@end` có bị lộ ra HTML không?
- Thụt lề và highlighting có dễ đọc không?
- Link `{@link ...}` có trỏ đúng API không?
- Có warning do Javadoc comment, tag hoặc reference sai không?

Có thể dùng `-Xdoclint:all` để bật kiểm tra tài liệu mạnh hơn. Doclint kiểm tra tài liệu và tham chiếu; nó không thay thế compile/test cho snippet.

## 10. SimpleFileServer trong Java 18

JEP 408 bổ sung Simple Web Server vào JDK 18 trong module `jdk.httpserver`. API `com.sun.net.httpserver.SimpleFileServer` tạo một HTTP server nhỏ phục vụ file tĩnh từ một thư mục.

Ba factory method chính:

| Method | Mục đích |
| --- | --- |
| `createFileServer(addr, root, outputLevel)` | Tạo `HttpServer` có handler phục vụ file |
| `createFileHandler(root)` | Tạo `HttpHandler` phục vụ file và directory listing |
| `createOutputFilter(out, outputLevel)` | Tạo filter ghi log cho HTTP exchange |

`createFileServer` trả về server chưa được start. Ứng dụng gọi `start()` để bắt đầu nhận request. `rootDirectory` phải là đường dẫn tuyệt đối, tồn tại, là thư mục và có thể đọc được.

Ví dụ tối thiểu:

```java
import com.sun.net.httpserver.SimpleFileServer;
import java.net.InetSocketAddress;
import java.nio.file.Path;

var server = SimpleFileServer.createFileServer(
        new InetSocketAddress("127.0.0.1", 8000),
        Path.of("build/fixtures").toAbsolutePath(),
        SimpleFileServer.OutputLevel.INFO);

server.start();
```

Binding `127.0.0.1` giới hạn server ở loopback trên IPv4. Port `8000` là ví dụ; khi kiểm thử tự động, nên dùng port `0` để hệ điều hành cấp cổng trống.

### 10.1. Công cụ dòng lệnh jwebserver

JDK cũng cung cấp `jwebserver` để phục vụ thư mục mà không cần viết class Java:

```bash
jwebserver --bind-address 127.0.0.1 \
           --port 8000 \
           --directory build/fixtures \
           --output info
```

Có thể xem các tùy chọn bằng:

```bash
jwebserver --help
```

Công cụ phù hợp khi cần mở nhanh fixture hoặc file tĩnh trong lúc phát triển. API `SimpleFileServer` phù hợp khi test cần khởi động và dừng server ngay trong test lifecycle.

## 11. Máy chủ fixture nên chỉ phục vụ thư mục tạm

Fixture server trong test nên có root riêng, chứa đúng file cần công bố. Không trỏ root vào thư mục home, workspace repository hoặc thư mục có secret.

Một test có thể tạo file UTF-8 trong `@TempDir`, khởi động server trên loopback và dùng `HttpClient` đọc lại response:

```java
package com.example.docs;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.sun.net.httpserver.HttpServer;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FixtureServerTest {
    @TempDir
    Path tempDir;

    @Test
    void servesUtf8FixtureBytesOverHttp() throws Exception {
        Path root = Files.createDirectory(tempDir.resolve("fixtures"));
        byte[] expected =
                "fixture: Tiếng Việt 🌍\n".getBytes(StandardCharsets.UTF_8);
        Files.write(root.resolve("greeting.txt"), expected);

        HttpServer server = FixtureServerExample.create(root);

        try {
            URI uri = URI.create(
                    "http://127.0.0.1:"
                    + server.getAddress().getPort()
                    + "/greeting.txt");

            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<byte[]> response = HttpClient.newHttpClient().send(
                    request,
                    HttpResponse.BodyHandlers.ofByteArray());

            assertEquals(200, response.statusCode());
            assertArrayEquals(expected, response.body());
            assertEquals(
                    "fixture: Tiếng Việt 🌍\n",
                    new String(response.body(), StandardCharsets.UTF_8));
        } finally {
            server.stop(0);
        }
    }
}
```

Test xác nhận byte response giống fixture ban đầu. Sau đó, test decode byte bằng UTF-8 theo hợp đồng đã định. Cách này không phụ thuộc charset mặc định của terminal hoặc charset mà HTTP client có thể suy ra từ header.

### 11.1. Vì sao dùng port 0?

Port `0` yêu cầu hệ điều hành cấp một cổng khả dụng khi server bind. Sau khi start, lấy cổng thực tế bằng `server.getAddress().getPort()`.

Không hard-code port dùng chung trong test suite. Test chạy song song có thể tranh chấp port; port `0` giảm khả năng va chạm và giúp test chạy ổn định trên CI.

### 11.2. Dọn server bằng finally

Server phải được dừng kể cả khi request thất bại hoặc assertion không đúng. `finally` bảo đảm `server.stop(0)` được gọi sau khi test hoàn tất.

Nếu server được quản lý bởi một fixture JUnit mở rộng, có thể đặt việc start/stop vào lifecycle callback. Dù chọn cách nào, tài nguyên mạng không nên tồn tại sau test.

## 12. Giới hạn của SimpleFileServer

SimpleFileServer được thiết kế cho testing, development và debugging. Nó phục vụ file tĩnh trong một cây thư mục và hỗ trợ request `GET`/`HEAD`; directory có thể trả về danh sách file nếu không có index file.

Không dùng nó như web server production. Nó không cung cấp đầy đủ các tính năng thường cần cho ứng dụng triển khai như xác thực người dùng, phân quyền nghiệp vụ, TLS/HTTPS được cấu hình cho production, routing động, giới hạn request theo nghiệp vụ hoặc cơ chế triển khai có giám sát.

Các nguyên tắc an toàn cho fixture server:

- Bind vào `127.0.0.1` hoặc loopback tương ứng.
- Chỉ phục vụ một thư mục fixture tạm, không dùng thư mục nhạy cảm.
- Dùng `OutputLevel.NONE` khi test không cần log.
- Dừng server trong `finally` hoặc lifecycle callback.
- Không dùng directory listing làm API ứng dụng.
- Không mở server ra `0.0.0.0` trong test thông thường.

## 13. Module và classpath

`SimpleFileServer` nằm trong module `jdk.httpserver`. Khi project dùng named module, khai báo dependency:

```java
module com.example.docs {
    requires jdk.httpserver;
    requires java.net.http;
}
```

`java.net.http` cần cho test dùng `HttpClient`; nếu production module không dùng HTTP client, có thể đặt yêu cầu module đó trong cấu hình test phù hợp thay vì thêm dependency không cần thiết vào module sản phẩm.

Với ứng dụng trên classpath, có thể cần thêm module JDK khi biên dịch hoặc chạy:

```bash
javac --add-modules jdk.httpserver -d target/classes ...
java --add-modules jdk.httpserver -cp target/classes ...
```

Khi chạy test framework, bảo đảm JVM test cũng resolve `jdk.httpserver`. Nếu compile thành công nhưng runtime báo `NoClassDefFoundError` hoặc `ClassNotFoundException` cho `com.sun.net.httpserver`, kiểm tra module path và `--add-modules`.

## 14. Kiểm thử cả nội dung và header HTTP

SimpleFileServer chọn `Content-Type` theo MIME table có sẵn và tên file. Không nên giả định mọi response text luôn có tham số `charset=UTF-8`. Để xác nhận encoding của fixture, test byte body độc lập với header:

```java
assertArrayEquals(expectedUtf8Bytes, response.body());

String text = new String(response.body(), StandardCharsets.UTF_8);
assertEquals(expectedText, text);
```

Nếu ứng dụng cần kiểm thử hợp đồng HTTP header riêng, hãy cấu hình server/handler theo đúng hợp đồng ứng dụng và kiểm tra header đó như một assertion độc lập. Đừng để test charset phụ thuộc vào một MIME guess không được cam kết.

Đối với response JSON, XML hoặc một định dạng có encoding quy định riêng, test cần kiểm tra media type, metadata và byte body theo đặc tả của định dạng đó.

## 15. Đưa server fixture vào tài liệu Javadoc

Có thể viết ví dụ server trong file external snippet để vừa trích vào Javadoc vừa biên dịch trong test source.

Ví dụ region `start-fixture-server` trong `FixtureServerExample.java`:

```java
package com.example.docs;

import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.SimpleFileServer;
import java.net.InetSocketAddress;
import java.nio.file.Path;

public final class FixtureServerExample {
    private FixtureServerExample() {
    }

    public static HttpServer create(Path fixtureRoot) {
        // @start region=start-fixture-server
        HttpServer server = SimpleFileServer.createFileServer(
                new InetSocketAddress("127.0.0.1", 0),
                fixtureRoot.toAbsolutePath(),
                SimpleFileServer.OutputLevel.NONE);
        server.start();
        // @end region=start-fixture-server
        return server;
    }
}
```

Javadoc có thể tham chiếu region:

```java
{@snippet file="com/example/docs/FixtureServerExample.java"
          region="start-fixture-server"}
```

Region ở đây chỉ tạo server; caller vẫn phải gọi `stop(0)` khi xong. Trong tài liệu API, ghi rõ quyền sở hữu server và vòng đời của nó. Với ví dụ ngắn hơn, có thể đưa cả `try/finally` vào region để người đọc thấy cách dọn tài nguyên.

## 16. Kiểm thử snippet server thay vì chỉ kiểm tra nó hiển thị

External snippet file có thể được biên dịch cùng test source. Test `FixtureServerTest` ở mục 11 gọi trực tiếp `FixtureServerExample.create(root)`, sau đó gửi HTTP request và kiểm tra byte response. Như vậy, file nguồn chứa region được Javadoc trích cũng chính là code được biên dịch và chạy trong test.

Một quy trình có thể dùng:

1. Lưu ví dụ đầy đủ trong `src/test/java`.
2. Đánh dấu named region bằng `// @start region=...` và `// @end region=...`.
3. Dùng `{@snippet file=... region=...}` để trích region.
4. Biên dịch file ví dụ cùng test source.
5. Gọi method ví dụ trong JUnit, kiểm tra response và đóng server.
6. Chạy Javadoc với `--snippet-path`.
7. Mở HTML và xác nhận đúng region được hiển thị.

Nếu cần đảm bảo file snippet luôn là source được kiểm thử, không tạo một bản copy độc lập chỉ để đưa vào Javadoc. Một file nguồn chung làm giảm nguy cơ tài liệu và test lệch nhau.

## 17. Kiểm tra nội dung Javadoc sinh ra

Sau khi chạy `javadoc`, review HTML chứ không chỉ xem lệnh có exit code 0.

Các lỗi có thể gặp:

- `file` path sai so với `--snippet-path`.
- Tên region không khớp giữa Javadoc tag và marker.
- Marker bị đặt sai vị trí hoặc thiếu `@end`.
- Snippet chứa import/context không có trong phần được trích.
- Snippet có thể biên dịch nhưng không giải thích đúng hợp đồng API.
- Snippet được hiển thị đúng nhưng file nguồn chưa nằm trong test source set.

Khi snippet có markup như `@highlight`, `@replace` hoặc `@link`, kiểm tra HTML để chắc rằng nội dung được nhấn mạnh, thay thế và liên kết đúng như ý định. Không dùng markup chỉ để trang trí nếu nó làm người đọc hiểu sai code thực thi.

## 18. Lỗi thường gặp và cách khắc phục

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tiếng Việt bị mojibake khi đọc fixture | Dùng default charset hoặc charset không khớp | Dùng UTF-8 theo hợp đồng và fixture byte độc lập |
| Reader không báo lỗi malformed | Dùng API thay thế byte lỗi hoặc test không đọc hết input | Dùng `Files.newBufferedReader(..., UTF_8)` và đọc hết nội dung trong test |
| File lớn gây tăng heap | Đọc toàn bộ vào `String` | Dùng `open(Path)` và xử lý theo dòng/khối |
| Javadoc không tìm snippet | Sai `--snippet-path` hoặc file path | Kiểm tra path tương đối và tên file |
| Region không xuất hiện | Tên `region` không khớp marker | Đồng bộ `region=...`, `@start` và `@end` |
| Snippet render nhưng code không chạy | Javadoc không biên dịch snippet | Đặt external source trong test source set và chạy compiler/JUnit |
| Test server chiếm port | Port bị hard-code | Dùng port `0`, lấy port thực sau start |
| Test treo hoặc để lại server | Không dừng server khi assertion fail | Dùng `finally` hoặc test lifecycle |
| HTTP body hiển thị sai | Decode body bằng charset đoán từ terminal/header | So sánh byte và decode theo hợp đồng |
| File fixture bị lộ ngoài máy local | Bind mọi network interface hoặc root quá rộng | Bind loopback và dùng thư mục tạm |

## 19. Checklist trước khi merge tài liệu

- [ ] Charset của file fixture được nêu rõ trong API và ví dụ.
- [ ] Bộ đọc UTF-8 dùng charset tường minh.
- [ ] Hợp đồng malformed/unmappable input được mô tả đúng.
- [ ] Quy tắc BOM và newline được công bố.
- [ ] Reader trả về có hướng dẫn caller đóng.
- [ ] File ví dụ external snippet có thể biên dịch.
- [ ] Named region có cặp marker và tên khớp Javadoc.
- [ ] Test xác nhận byte fixture và nội dung Unicode.
- [ ] Test có byte UTF-8 malformed.
- [ ] Test server dùng `@TempDir`, loopback và port `0`.
- [ ] HTTP response được kiểm tra bằng status và byte body.
- [ ] Server luôn được dừng dù test thất bại.
- [ ] Javadoc được sinh với `--snippet-path`.
- [ ] HTML đã được review; không coi Javadoc build là test runtime.
- [ ] Build chạy trên JDK mục tiêu và module `jdk.httpserver` được resolve.

## 20. Những nhận định dễ nhầm

- **“Javadoc `{@snippet}` tự biên dịch code.”** Sai. Standard Doclet trích và render; compiler hoặc test runner phải kiểm tra code.
- **“JEP 413 có từ Java 18 nên mọi JDK cũ đều hiểu `{@snippet}`.”** Sai. Cần JDK 18+ Standard Doclet hoặc doclet hỗ trợ tag tương ứng.
- **“`Files.newBufferedReader(path, UTF_8)` thay BOM tự động.”** Sai. BOM UTF-8 có thể trở thành `U+FEFF`; ứng dụng quyết định có bỏ hay giữ theo định dạng.
- **“JEP 400 khiến mọi file tự động là UTF-8.”** Sai. Default charset của JVM không thay hợp đồng encoding riêng của file hoặc giao thức.
- **“SimpleFileServer là server production gọn nhẹ.”** Sai. Nó được thiết kế cho testing, development và debugging.
- **“Server fixture nên bind `0.0.0.0` để test dễ truy cập.”** Không cần thiết trong test local. Bind loopback để giới hạn phạm vi truy cập.
- **“Port cố định giúp test dễ dự đoán.”** Sai. Test song song có thể tranh chấp; dùng port `0`.
- **“Kiểm tra `Content-Type` là đủ để chứng minh byte UTF-8.”** Sai. So sánh byte body và decode theo charset hợp đồng.
- **“Một đoạn code hiển thị đúng trong Javadoc là ví dụ đã được kiểm thử.”** Sai. Hãy biên dịch và chạy chính file external snippet.

## 21. Tài liệu tham khảo chính thức

- [Programmer's Guide to Snippets — JDK 18](https://docs.oracle.com/en/java/javase/18/code-snippet/index.html): inline snippet, external snippet, region, `--snippet-path` và testing snippets.
- [JEP 413 — Code Snippets in Java API Documentation](https://openjdk.org/jeps/413): bổ sung `{@snippet}` cho Standard Doclet từ Java 18.
- [SimpleFileServer — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): factory methods, file handler và output filter.
- [SimpleFileServer — Java SE 18](https://docs.oracle.com/en/java/javase/18/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): API được bổ sung trong JDK 18.
- [JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): mục đích và phạm vi của simple file server.
- [The jwebserver Command — JDK 18](https://docs.oracle.com/en/java/javase/18/docs/specs/man/jwebserver.html): tùy chọn bind address, port, directory và output.
- [Files — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): `newBufferedReader`, UTF-8, malformed input và `readString`.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): phạm vi default charset từ Java 18.

