# Nhận nội dung HTTP bằng ofString, ofByteArray, ofFile và discarding trong Java

Khi Java gửi một `HttpRequest` bằng module `java.net.http`, **cách xử lý phần thân (response body) được quyết định bởi `HttpResponse.BodyHandler<T>`** mà ứng dụng truyền vào `HttpClient.send(...)` hoặc `sendAsync(...)`. Bốn lựa chọn phổ biến nhất:

- **`BodyHandlers.ofString(...)`**: giải mã response body thành **`String`** (dữ liệu văn bản).
- **`BodyHandlers.ofByteArray()`**: thu response body thành **`byte[]`** (giữ nguyên bytes).
- **`BodyHandlers.ofFile(path, ...)`**: ghi response body vào **tệp**, trả về **`Path`**.
- **`BodyHandlers.discarding()`**: **đọc và loại bỏ** phần thân, trả về body kiểu **`Void`** (giá trị thực tế `null`).

Chọn sai handler có thể khiến ứng dụng giải mã sai charset, dùng quá nhiều RAM, ghi đè tệp không chủ định hoặc tốn công xử lý một body không cần thiết. **HTTP status, headers và kiểu dữ liệu body là ba vấn đề khác nhau**: HTTP 404 vẫn có thể được xử lý bởi cả bốn handler; chúng **không tự động từ chối** response chỉ vì status là lỗi.

Bài này nằm trong chủ đề **Nội dung HTTP** của Java Advance - networking, tập trung vào cách nhận nội dung và vòng đời tài nguyên. Có hai chương trình **Java 17+ hoàn chỉnh, chạy localhost không cần Internet**, kèm lệnh `javac`/`java`, đầu ra xác định và phần giải thích về các giới hạn.

## 1. Vị trí của BodyHandler trong luồng HTTP

Trong Java HTTP Client:

~~~text
Ứng dụng                         HTTP server
    |                                  |
    | HttpRequest                      |
    | URI / method / headers / body    |
    +---------- request -------------> |
    |                                  |
    | <--- status + headers + bytes ---+
    |
    v
HttpClient.send(request, BodyHandler<T>)
    |
    +-- ofString(UTF_8)  --> HttpResponse<String>
    |
    +-- ofByteArray()    --> HttpResponse<byte[]>
    |
    +-- ofFile(path)     --> HttpResponse<Path>
    |
    +-- discarding()     --> HttpResponse<Void>
    |
    +-- tất cả đều có statusCode(), headers(), version(), uri()
~~~

`HttpClient` đảm nhận gửi HTTP request và nhận response; **`BodyHandler<T>` chọn cách tiếp nhận body**. Predefined handler thường tạo `BodySubscriber<T>` tương ứng. Subscriber xử lý dòng bytes từ transport và hoàn tất kết quả kiểu `T`.

Công thức đơn giản:

~~~java
HttpResponse<String> text = client.send(
        request, HttpResponse.BodyHandlers.ofString());

HttpResponse<byte[]> binary = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

HttpResponse<Path> saved = client.send(
        request, HttpResponse.BodyHandlers.ofFile(outputPath));

HttpResponse<Void> ignored = client.send(
        request, HttpResponse.BodyHandlers.discarding());
~~~

**Đây là snippet**, không phải một chương trình đầy đủ. Nó cần `client`, `request`, `outputPath`, imports và xử lý ngoại lệ. Bốn lệnh trên sẽ **gửi bốn HTTP requests riêng biệt**, không phải nhận một response rồi đổi handler. Không thử tuần tự kiểu này với POST tạo dữ liệu nếu không muốn thực hiện hành động bốn lần.

**Phân biệt với `BodyPublisher`:**
- `HttpRequest.BodyPublisher` phát dữ liệu **yêu cầu đi ra** (ví dụ `BodyPublishers.ofString(json)` trong POST).
- `HttpResponse.BodyHandler` xử lý dữ liệu **phản hồi đi về**.
- `HttpResponse<T>` là kết quả metadata + body được tạo theo handler đó.

## 2. Bảng so sánh nhanh bốn lựa chọn

| Handler | Kiểu `T` trong `HttpResponse<T>` | Body trả về | Khi phù hợp | Chi phí/rủi ro chính |
| --- | --- | --- | --- | --- |
| `ofString(charset)` | `String` | Text đã decode | JSON/text nhỏ, HTML, API error body vừa phải | Giữ toàn bộ body trong RAM; có thể sai charset |
| `ofByteArray()` | `byte[]` | Bytes nguyên bản | Hình ảnh/binary nhỏ, checksum, dữ liệu cần parser riêng | Giữ toàn bộ bytes trong RAM |
| `ofFile(path, options...)` | `Path` | Đường dẫn tệp đã được ghi | Tải nội dung lớn, file cần lưu | Quyền ghi, disk đầy, tệp lỗi/partial, ghi đè |
| `discarding()` | `Void` | `null` | Chỉ quan tâm status/headers, không cần body | Vẫn tốn xử lý/network để tiêu thụ body, không có dữ liệu để debug |

Một vài nguyên tắc:
1. **Biết trước text và charset**: `ofString(StandardCharsets.UTF_8)`.
2. **Muốn giữ bytes chính xác**: `ofByteArray()`, sau đó chủ động parse/decode.
3. **Cần lưu file thay vì giữ hết trong heap**: `ofFile(path, options)`, kiểm tra disk/size/status.
4. **Chỉ cần biết response đã đến và status**: `discarding()`.
5. **Body rất lớn nhưng không được phép ghi file**: có thể cân nhắc `ofInputStream()` hoặc Flow API; đây là API khác, cần chủ động đóng stream/thiết kế backpressure.

Không có một handler “tốt nhất” cho mọi API. Cùng endpoint trả video, JSON và lỗi text có thể cần chính sách body khác tùy status/Content-Type.

## 3. ofString(): giải mã thành String

Cú pháp:

~~~java
HttpResponse<String> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

String body = response.body();
int status = response.statusCode();
~~~

Đây là **snippet**, yêu cầu import `java.net.http.*` và `java.nio.charset.StandardCharsets`. Dùng khi response dự kiến là văn bản và không lớn, ví dụ JSON API, XML, thông báo text, HTML nhỏ.

`BodyHandlers.ofString(Charset)` **dùng đúng charset bạn cung cấp**. Với UTF-8:

~~~java
BodyHandlers.ofString(StandardCharsets.UTF_8)
~~~

nghĩa là chuyển bytes UTF-8 thành các ký tự Java. Nếu server gửi bytes theo charset khác, giải mã UTF-8 có thể tạo ký tự thay thế (`�`) hoặc ra text sai mà không nhất thiết ném exception.

### ofString() không tham số khác gì?

Theo Javadoc Java 17, `BodyHandlers.ofString()` **tìm charset từ header `Content-Type`** của response. Nếu header không có charset hoặc charset không được hỗ trợ, nó **dùng UTF-8**.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=ISO-8859-1

...
~~~

Với `ofString()`, handler có thể chọn ISO-8859-1 từ header. Với `ofString(StandardCharsets.UTF_8)`, ứng dụng đã **ấn định UTF-8**; đây là lựa chọn hữu ích khi API contract nói rõ response luôn UTF-8, nhưng sẽ không tự làm theo charset khác trong header.

Lưu ý:
- `Content-Type` là **header do server khai báo**; server có thể khai báo sai. Hãy xác minh API contract nếu dữ liệu quan trọng.
- `Content-Encoding: gzip` là **content coding**, không phải character encoding. Đổi charset không tự “giải nén” gzip. Không mặc định các handler giải quyết mọi biến thể compression; kiểm tra cấu hình client/headers và triển khai decoding cần thiết.
- `String.length()` đếm UTF-16 code units, không phải bytes trên dây. Một ký tự tiếng Việt UTF-8 có thể chiếm nhiều bytes nhưng chỉ một UTF-16 code unit.
- `ofString` thường giữ toàn bộ response body trong bộ nhớ trước khi `send` trả về kết quả text. Không phù hợp dữ liệu có thể vô hạn hoặc quá lớn.
- Với JSON, `ofString` chỉ **giải mã bytes thành text**; không tự parse JSON thành object Java.

**Dùng khi:** REST response nhỏ, text config, kết quả API ngắn, phần lỗi mà bạn muốn hiển thị/log có kiểm soát.

## 4. ofByteArray(): nhận nguyên bytes

Cú pháp:

~~~java
HttpResponse<byte[]> response = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

byte[] bytes = response.body();
System.out.println("Received bytes: " + bytes.length);
~~~

Đây là snippet. `ofByteArray()` **không diễn giải charset và không sửa nội dung theo encoding văn bản**; bạn nhận các bytes của body theo representation mà HTTP client chuyển tới handler. Muốn giải mã text, bạn quyết định charset sau:

~~~java
String text = new String(response.body(), StandardCharsets.UTF_8);
~~~

Chỉ làm vậy khi thực sự biết bytes là UTF-8. Nếu body là PNG, ZIP, PDF hoặc dữ liệu mã hóa nhị phân, dùng `new String(...)` sẽ làm mất ý nghĩa nhị phân.

### Byte trong Java là signed

`byte` Java có dải -128..127. Ví dụ body có byte giá trị unsigned `0xFF` sẽ xuất hiện là `-1` nếu nhìn qua `Arrays.toString(byteArray)`. Đó **không phải** do HTTP làm hỏng dữ liệu.

Chuyển một byte sang số unsigned:

~~~java
int unsigned = bytes[index] & 0xff;
~~~

Hoặc in bytes hex trên Java 17+:

~~~java
String hex = HexFormat.of().formatHex(bytes);
~~~

Cần `import java.util.HexFormat;`. Ví dụ các bytes `00 01 02 FF` in ra `000102ff`.

### Cẩn thận RAM

`ofByteArray()` phải giữ bytes cần cho kết quả mảng trong bộ nhớ. Response lớn có thể gây memory pressure/OOM, nhất là khi nhiều request cùng chạy. Nếu mục tiêu chỉ là lưu một file, `ofFile()` phù hợp hơn. Nếu cần parse streaming, `BodyHandlers.ofInputStream()` hoặc custom subscriber cho phép tiến trình khác — nhưng có nghĩa bạn phải chịu trách nhiệm lifecycle/limits.

**Dùng khi:** ảnh/file nhỏ, binary protocol, checksum, bytes cần đưa cho parser, signature verification, hoặc nội dung mà encoding chưa được quyết định.

## 5. ofFile(): ghi body ra tệp và trả về Path

Cú pháp:

~~~java
Path output = Path.of("download.bin");

HttpResponse<Path> response = client.send(
        request, HttpResponse.BodyHandlers.ofFile(
                output,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE));

Path saved = response.body();
long size = Files.size(saved);
~~~

Đây là snippet: cần imports `java.nio.file.*`, `java.net.http.*`. **`CREATE_NEW` đòi tệp đích chưa tồn tại** và làm operation thất bại nếu tệp có sẵn. Sử dụng chế độ này để tránh ghi đè không mong muốn.

Theo Javadoc, với `BodyHandlers.ofFile(...)`, khi `HttpResponse<Path>` trả về, **body đã được ghi xong vào tệp** nếu thao tác thành công. `response.body()` là `Path`, **không** phải bytes hoặc nội dung String.

**Ví dụ đường dẫn:**
- `Path.of("download.bin")` là relative path, được giải quyết theo working directory của JVM.
- `Path.of("/data/download.bin")` là đường dẫn tuyệt đối kiểu Unix; trên Windows có path syntax khác.
- `Files.createTempDirectory(...)` và `directory.resolve("payload.bin")` tạo đích tạm được kiểm soát, phù hợp bài test.

**Không dùng `ofFile` để mặc định tin vào filename từ server.** Trong API này, path là **bạn chọn trước**; khác với `BodyHandlers.ofFileDownload(directory, options...)` lấy tên từ `Content-Disposition`. Nếu dùng filename có nguồn bên ngoài, cần normalize, giới hạn directory, kiểm tra path traversal và tránh ghi đè.

### Bẫy quan trọng: ofFile(path) không mặc định truncate file cũ

Javadoc Java 17 ghi rõ:

~~~java
BodyHandlers.ofFile(path)
~~~

tương đương:

~~~java
BodyHandlers.ofFile(
        path, StandardOpenOption.CREATE, StandardOpenOption.WRITE)
~~~

**Không có `TRUNCATE_EXISTING` trong mặc định.** Khi ghi một response ngắn đè lên file **đã dài hơn**, dữ liệu cũ **có thể vẫn còn ở cuối file**. Điều này rất dễ bị nhầm với `Files.writeString(path, text)` — hai API có default open options khác nhau.

Chọn có chủ đích:

| Mục tiêu | Open options | Ý nghĩa |
| --- | --- | --- |
| Tạo tệp mới, không được trùng tên | `CREATE_NEW, WRITE` | Tránh overwrite; lỗi nếu đã tồn tại |
| Cho phép thay thế nội dung tệp đang có | `CREATE, WRITE, TRUNCATE_EXISTING` | Cắt ngắn file trước khi ghi |
| Dùng mặc định `ofFile(path)` | `CREATE, WRITE` | Có thể để lại bytes ở cuối file cũ dài hơn |
| Muốn tải vào temp rồi công bố sau khi kiểm tra | Temp file + verify + move | Giảm rủi ro đưa file lỗi/partial thành bản chính |

Các options này là `java.nio.file.StandardOpenOption` và phải hợp lệ theo Javadoc. Không ghép `APPEND` với `TRUNCATE_EXISTING` một cách tùy tiện.

### Tệp lỗi hoặc body HTTP lỗi

`BodyHandlers.ofFile(...)` **không tự loại bỏ body của response 404/500**. Ví dụ nếu server trả 404 với HTML error page, handler vẫn có thể ghi HTML đó vào `download.bin` và trả về `HttpResponse<Path>` với `statusCode()==404`.

Do đó:
1. Kiểm tra `statusCode()` sau khi nhận response.
2. Kiểm tra `Content-Type`, kích thước, checksum/chữ ký (nếu có) theo nghiệp vụ.
3. Nếu bất hợp lệ, **xóa/quarantine** file tạm; không đưa vào nơi phục vụ người dùng như file hợp lệ.
4. Nếu download được chấp nhận, move tệp tạm đến đích cuối với chính sách chống ghi đè thích hợp.

Nếu mạng bị ngắt, filesystem đầy hoặc quyền ghi bị từ chối, `send()/sendAsync()` có thể thất bại. Một file **đã được tạo nhưng ghi dở** có thể vẫn tồn tại; cần cleanup trong nhánh lỗi. Không phải lúc nào lỗi I/O cũng làm API tự xóa file.

**Dùng khi:** tải báo cáo, lưu ảnh hoặc tệp lớn, lưu backup/export, hoặc cần kết quả `Path` mà không giữ toàn bộ trong một `byte[]` Java.

## 6. discarding(): bỏ nội dung nhưng vẫn lấy metadata

Cú pháp:

~~~java
HttpResponse<Void> response = client.send(
        request, HttpResponse.BodyHandlers.discarding());

System.out.println(response.statusCode());
System.out.println(response.headers().firstValue("Content-Type"));
System.out.println(response.body() == null);
~~~

Đây là snippet, body sẽ là `null` đối với `Void`. **Không nhầm `body()==null` với server trả HTTP 204 No Content**: kể cả server trả HTTP 200/202 với body, discarding vẫn bỏ body đó.

`discarding()` hữu ích nếu:
- Chỉ cần mã status của endpoint sau khi gọi request.
- Không cần đọc error payload.
- Cần kiểm tra response headers và không quan tâm body.
- Muốn tránh giữ một body lớn trong RAM.

Nhưng nó **không** biến HTTP request thành “miễn phí”: transport vẫn phải xử lý/phân phối dữ liệu theo HTTP flow để hoàn tất response. Việc discard cũng **không thay GET bằng HEAD**; server đã có thể tạo body và truyền dữ liệu. Khi muốn chỉ lấy headers và server hỗ trợ, dùng HTTP `HEAD`:

~~~java
HttpRequest head = HttpRequest.newBuilder(uri)
        .method("HEAD", HttpRequest.BodyPublishers.noBody())
        .build();
~~~

Đây là snippet có biến `uri`. Dù HEAD thường không có message body, server có thể khác cấu hình; không nên dùng HEAD cho endpoint chỉ hỗ trợ GET/POST mà không kiểm tra contract.

**Lưu ý:** `discarding()` có thể khiến bạn mất thông tin lỗi từ response body, như JSON error detail. Nếu cần debug hoặc thông báo có ý nghĩa, chọn handler đọc body có giới hạn ở những request phù hợp.

## 7. Các predefined handlers không tự kiểm tra HTTP status

Javadoc `HttpResponse.BodyHandlers` nói rõ các predefined handlers **không kiểm tra status code**: chúng chấp nhận body bất kể status. Với một response HTTP hợp lệ:

| HTTP response | ofString | ofByteArray | ofFile | discarding |
| --- | --- | --- | --- | --- |
| 200 + text | Text | Bytes | Ghi text bytes vào file | Body=null |
| 200 + binary | Có thể decode thành ký tự sai | Bytes đúng | Ghi bytes vào file | Body=null |
| 404 + HTML error body | HTML error String | HTML bytes | Có thể ghi error page vào file | Body=null |
| 500 + JSON error body | JSON text | JSON bytes | Có thể ghi JSON vào file | Body=null |
| 204 No Content | String rỗng (tùy handler semantics) | Mảng rỗng | Tệp 0 bytes hoặc không có dữ liệu để ghi, tùy cấu hình path | Body=null |

**Không** đồng nhất `HTTP 404` với `IOException`. Một HTTP 404 là response bình thường về mặt giao thức, còn `IOException` thường biểu thị lỗi DNS, kết nối, TLS hoặc xử lý I/O. Kiểm tra status riêng:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));

if (response.statusCode() >= 200 && response.statusCode() < 300) {
    // Xử lý body trong trường hợp thành công.
} else {
    // Xử lý response lỗi, có thể log error body một cách an toàn.
}
~~~

Đây là snippet. Không mặc định mọi 3xx đều là lỗi: policy redirect của client có thể không follow hoặc follow theo cấu hình. Không mặc định mọi 2xx đều có non-empty body, vì 204 là response thành công không có content.

Một application muốn **lựa chọn handler theo status** có thể tạo custom `HttpResponse.BodyHandler<T>` dựa trên `HttpResponse.ResponseInfo.statusCode()` để chọn một `BodySubscriber<T>` thích hợp (phải thống nhất cùng kiểu `T`). Với trường hợp đơn giản, dùng `ofString()` cho lỗi có giới hạn hoặc tải vào temp rồi kiểm tra status có thể dễ bảo trì hơn.

## 8. Ví dụ Java 17+ hoàn chỉnh: cả bốn handlers trong một chương trình

Chương trình **`FourResponseHandlersDemo.java`** dựng một HTTP server local bằng `jdk.httpserver`:
- `/text` → HTTP 200, body `"hello"`.
- `/bytes` → HTTP 200, bốn bytes `00 01 02 FF`.
- `/file` → HTTP 200, body `"file=ready"`.
- `/ignore` → HTTP 202, body `"ignored-data"` (bị `discarding` loại bỏ).
- `/missing` → HTTP 404, body `"missing"` để chứng minh một error response vẫn có body.

Server bind vào `127.0.0.1:0`, dùng port do hệ điều hành cấp; không cần Internet, token, certificate hay DNS. Client chọn HTTP/1.1 cho môi trường test. Đường dẫn tệp được cấp riêng trong temp directory, không đụng dữ liệu ứng dụng.

Tạo file **`FourResponseHandlersDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
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
import java.time.Duration;
import java.util.HexFormat;

public class FourResponseHandlersDemo {
    static void reply(HttpExchange ex, int status,
                      byte[] data, String mime) throws IOException {
        ex.getResponseHeaders().set("Content-Type", mime);
        ex.sendResponseHeaders(status, data.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(data);
        }
    }

    static HttpRequest get(int port, String path) {
        return HttpRequest.newBuilder(URI.create(
                "http://127.0.0.1:" + port + path))
                .timeout(Duration.ofSeconds(3)).GET().build();
    }

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("http-body-demo-");
        Path target = directory.resolve("payload.bin");

        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/", ex -> {
            try {
                String path = ex.getRequestURI().getPath();
                if (path.equals("/text")) {
                    reply(ex, 200,
                            "hello".getBytes(StandardCharsets.UTF_8),
                            "text/plain; charset=utf-8");
                } else if (path.equals("/bytes")) {
                    reply(ex, 200,
                            new byte[]{0, 1, 2, (byte) 255},
                            "application/octet-stream");
                } else if (path.equals("/file")) {
                    reply(ex, 200,
                            "file=ready".getBytes(StandardCharsets.UTF_8),
                            "application/octet-stream");
                } else if (path.equals("/ignore")) {
                    reply(ex, 202,
                            "ignored-data".getBytes(StandardCharsets.UTF_8),
                            "text/plain");
                } else {
                    reply(ex, 404,
                            "missing".getBytes(StandardCharsets.UTF_8),
                            "text/plain; charset=utf-8");
                }
            } catch (IOException error) {
                ex.close();
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            // 1. Text => HttpResponse<String>.
            HttpResponse<String> text = client.send(
                    get(port, "/text"),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("String: " + text.statusCode()
                    + " | " + text.body());

            // 2. Binary => HttpResponse<byte[]>.
            HttpResponse<byte[]> bytes = client.send(
                    get(port, "/bytes"),
                    HttpResponse.BodyHandlers.ofByteArray());
            System.out.println("Bytes: " + bytes.statusCode()
                    + " | " + HexFormat.of().formatHex(bytes.body()));

            // 3. File => HttpResponse<Path>.
            // CREATE_NEW tránh ghi đè lên tệp đã tồn tại.
            HttpResponse<Path> file = client.send(
                    get(port, "/file"),
                    HttpResponse.BodyHandlers.ofFile(
                            target, StandardOpenOption.CREATE_NEW,
                            StandardOpenOption.WRITE));
            System.out.println("File: " + file.statusCode()
                    + " | " + Files.size(file.body()) + " bytes");
            System.out.println("File content: "
                    + Files.readString(
                            file.body(), StandardCharsets.UTF_8));

            // 4. Discard => HttpResponse<Void> và body() == null.
            HttpResponse<Void> ignored = client.send(
                    get(port, "/ignore"),
                    HttpResponse.BodyHandlers.discarding());
            System.out.println("Discard: " + ignored.statusCode()
                    + " | body == null: " + (ignored.body() == null));

            // 5. Error HTTP vẫn có thể là HttpResponse<String>.
            HttpResponse<String> error = client.send(
                    get(port, "/missing"),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println("Error: " + error.statusCode()
                    + " | " + error.body());
        } finally {
            server.stop(0);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 FourResponseHandlersDemo.java
java FourResponseHandlersDemo
~~~

**Kết quả đã chạy thử (không phụ thuộc cổng tạm được chọn):**

~~~text
String: 200 | hello
Bytes: 200 | 000102ff
File: 200 | 10 bytes
File content: file=ready
Discard: 202 | body == null: true
Error: 404 | missing
~~~

### Vì sao kết quả như vậy?

1. `BodyHandlers.ofString(UTF_8)` trả `HttpResponse<String>`, và body là chữ `"hello"`.
2. `BodyHandlers.ofByteArray()` giữ bốn bytes gốc; `HexFormat` in `000102ff`, kể cả byte signed `(byte) 255`.
3. `BodyHandlers.ofFile(target, CREATE_NEW, WRITE)` ghi 10 bytes `file=ready` vào tệp mới; response trả `Path` cho chính tệp đó.
4. `BodyHandlers.discarding()` bỏ `"ignored-data"` nhưng response vẫn có HTTP status `202`. `body() == null` là điều bình thường của `HttpResponse<Void>`.
5. Request `/missing` trả HTTP 404 và text `"missing"`; `client.send(...)` không ném exception chỉ vì status 404.
6. `Files.readString(file.body())` trong demo chỉ để kiểm tra **tệp 10 bytes**. Trong ứng dụng tải file lớn, không đọc cả file trở lại thành String, vì sẽ làm mất lợi ích streaming-to-disk.
7. `finally` dọn server và tệp temp. Nếu chương trình thất bại ở đoạn đầu có thể phát sinh tình huống cleanup bổ sung tùy thiết kế; đây là fixture minh họa, không phải download manager phục vụ người dùng.

**Module khác nhau:** Các lớp HTTP client thuộc module **`java.net.http`**; HTTP server test `com.sun.net.httpserver.HttpServer` thuộc module **`jdk.httpserver`**. Trong một dự án Java có `module-info.java` tường minh, cần `requires java.net.http;` và (chỉ khi dùng test fixture) `requires jdk.httpserver;`. Khi chạy classpath thông thường với JDK đầy đủ, các ví dụ này có thể chạy không cần file module descriptor.

## 9. Ví dụ Java 17+ thứ hai: file đã tồn tại và TRUNCATE_EXISTING

Đây là lỗi dễ bỏ sót trong hệ thống tải báo cáo: file `report.txt` đang có nội dung 26 bytes, response mới chỉ có 3 bytes. Gọi `BodyHandlers.ofFile(path)` mặc định **không cắt đuôi file cũ**.

Chương trình sau so sánh:
1. Ghi sẵn chuỗi `abcdefghijklmnopqrstuvwxyz` (26 bytes ASCII) vào tệp temp.
2. Dùng `ofFile(file)` để tải body mới `abc` (3 bytes).
3. Kiểm tra độ dài tệp sau lần đầu — vẫn 26 bytes trong môi trường kiểm thử.
4. Gửi lại cùng GET nhưng dùng `CREATE, WRITE, TRUNCATE_EXISTING` — độ dài tệp về đúng 3 bytes.

Tạo file **`OfFileOpenOptionsDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
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

public class OfFileOpenOptionsDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/", exchange -> {
            byte[] content = "abc".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, content.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(content);
            }
        });

        Path file = Files.createTempFile(
                "http-file-options-", ".txt");
        server.start();
        try {
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:"
                            + server.getAddress().getPort() + "/"))
                    .GET().build();

            Files.writeString(
                    file, "abcdefghijklmnopqrstuvwxyz",
                    StandardCharsets.UTF_8);

            // Mặc định chỉ CREATE + WRITE, không TRUNCATE.
            HttpResponse<Path> defaultSave = client.send(
                    request, HttpResponse.BodyHandlers.ofFile(file));

            System.out.println("Default length: "
                    + Files.size(defaultSave.body()));
            System.out.println("Default starts with abc: "
                    + Files.readString(file).startsWith("abc"));

            // Thay thế nội dung cũ một cách tường minh.
            HttpResponse<Path> truncatedSave = client.send(
                    request, HttpResponse.BodyHandlers.ofFile(
                            file, StandardOpenOption.CREATE,
                            StandardOpenOption.WRITE,
                            StandardOpenOption.TRUNCATE_EXISTING));

            System.out.println("Truncated length: "
                    + Files.size(truncatedSave.body()));
            System.out.println("Truncated content: "
                    + Files.readString(file));
        } finally {
            server.stop(0);
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 OfFileOpenOptionsDemo.java
java OfFileOpenOptionsDemo
~~~

**Đầu ra kiểm tra trên JDK có default filesystem provider thông thường:**

~~~text
Default length: 26
Default starts with abc: true
Truncated length: 3
Truncated content: abc
~~~

**Bài học từ demo:** Tên file tồn tại từ trước không đủ để chứng minh body download đã thay thế sạch sẽ. `ofFile(file)` không mặc định truncate. Nếu muốn cấm ghi đè, dùng `CREATE_NEW`. Nếu muốn thay thế, dùng `TRUNCATE_EXISTING` có chủ đích. Trong production, cách mạnh hơn là ghi vào **tệp temp riêng**, kiểm tra status/hash/size, sau đó chuyển tới đích bằng Files API với collision/atomicity policy phù hợp.

## 10. Cơ chế hoàn tất và BodySubscriber

Các handlers dựng một `BodySubscriber<T>` để xử lý dòng bytes response. Với bốn lựa chọn đơn giản:

~~~text
HTTP response headers ───> BodyHandler<T>
                                |
                                v
                         BodySubscriber<T>
                                |
                     các ByteBuffer chunks
                                |
             +------------------+------------------+
             |                  |                  |
       accumulate text    accumulate bytes    write file/discard
             |                  |                  |
             v                  v                  v
          String              byte[]            Path / Void
                                |
                                v
                         HttpResponse<T>
~~~

Đối với `ofString()`, `ofByteArray()`, `ofFile()` và `discarding()`, `send(...)` thông thường chỉ trả kết quả khi handler đã hoàn thành việc tiêu thụ body theo contract. Đặc biệt `ofFile()` đã ghi xong body vào file khi response trả về thành công. Điều này **khác** `BodyHandlers.ofInputStream()`, nơi response có thể trả về sau headers trong khi caller phải tiếp tục đọc/đóng `InputStream`.

**Không đồng nhất “body đã ghi xong file” với “nội dung an toàn/hợp lệ”:** HTTP 404, sai MIME, mã độc, checksum mismatch hoặc nội dung vượt hạn vẫn là những việc ứng dụng phải kiểm soát.

Với `sendAsync(...)`, phần thân vẫn được xử lý theo cùng handler, chỉ có cách nhận kết quả là `CompletableFuture<HttpResponse<T>>`:

~~~java
CompletableFuture<HttpResponse<Path>> future =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofFile(
                        path, StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE));

future.thenAccept(response -> {
    System.out.println(response.statusCode());
    System.out.println(response.body()); // Path.
});
~~~

Đây là snippet; phải khai báo path, client, request, imports và xử lý exceptional completion. Không thoát JVM trước khi Future hoàn tất nếu ứng dụng cần tệp. Một `HttpResponse<T>` vẫn mang đúng kiểu `T` đã chọn trong BodyHandler.

## 11. Chọn handler dựa vào nhu cầu và Content-Type

Một chiến lược thực tế:

| Bạn cần làm gì? | Handler ưu tiên | Kiểm tra bổ sung |
| --- | --- | --- |
| Đọc JSON nhỏ để parse | `ofString(UTF_8)` hoặc `ofByteArray()` | HTTP status, content-type, JSON schema, giới hạn bytes |
| Đọc text xác định charset | `ofString(charset)` | Header/content contract và decoding errors |
| Nhận binary nhỏ để xử lý trong bộ nhớ | `ofByteArray()` | Kích thước, MIME, magic bytes, checksum |
| Download report/file lớn | `ofFile(tempPath, options...)` | Status, filesize, checksum/signature, path/file permissions |
| Chỉ cần biết lệnh HTTP có thành công | `discarding()` | Status 2xx, headers, trace ID, retry policy |
| Xử lý dữ liệu khổng lồ không lưu file | `ofInputStream()` hoặc custom Flow subscriber | Giới hạn luồng, close/cancel, backpressure |

**Content-Type là gợi ý, không phải bằng chứng an toàn.** Server có thể khai báo `image/png` nhưng trả HTML error page; cũng có thể báo sai charset hoặc stream malformed. Khi xác định loại file phải kết hợp status, expected media type, magic bytes/checksum/signature hoặc parser phù hợp.

Có thể kiểm tra header:

~~~java
String contentType = response.headers()
        .firstValue("Content-Type")
        .orElse("");

if (!contentType.startsWith("application/json")) {
    // Không nên mặc định body là JSON của API.
}
~~~

Snippet này minh họa; giá trị header có thể khác chữ hoa/thường hoặc có tham số, nên production dùng cách parse media type đúng chuẩn thay vì chỉ `startsWith` phân biệt chữ hoa/thường. Header chỉ là một trong các bước validation.

## 12. Quản lý kích thước và tài nguyên

**`ofString` và `ofByteArray`** tiện nhưng có rủi ro khi response quá lớn:
- Response 100 MB có thể tạo nhiều allocation, cao hơn kích thước raw payload do String/byte arrays và trung gian.
- Nhiều requests đồng thời khiến tổng áp lực bộ nhớ tăng mạnh.
- `Content-Length` có thể không có, sai hoặc có thể không mô tả kích thước sau content coding; không dựa hoàn toàn vào một header để chặn dữ liệu độc hại.
- Khi cần giới hạn cứng tổng bytes, xem custom subscriber hoặc streaming với counter và cancel/close khi vượt ngưỡng.

**`ofFile`** giảm nhu cầu giữ toàn bộ body trong heap, nhưng không có nghĩa “miễn phí”:
- Disk có thể đầy, quota/permission có thể từ chối ghi.
- Đích do user cung cấp có thể ghi đè file nhạy cảm nếu không kiểm soát.
- File tạm có thể vẫn nằm lại khi request thất bại.
- Dùng đường dẫn có kiểm tra, giới hạn dung lượng/quota, và chỉ công bố file sau validation.
- Ghi vào tệp temp rồi rename/move theo policy sẽ tốt hơn ghi thẳng vào file có người dùng đang sử dụng.

**`discarding`** tránh materialize body trong object Java nhưng không tránh server/network cost. Nếu chỉ cần metadata và server cho phép, có thể dùng HEAD; nếu cần giá trị phản hồi, discarding là sai lựa chọn vì không còn body để parse.

**Mẹo observability:** log method, sanitized URI, status, content-type, duration, số byte và lựa chọn handler; tránh log plaintext body, tokens, Authorization header, Cookie và thông tin cá nhân không cần thiết.

## 13. Timeout, lỗi mạng và lỗi filesystem

Bốn handlers không thay thế chính sách timeout:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();
~~~

Đây là snippet. `connectTimeout` áp dụng cho kết nối mới; request timeout áp dụng cho request ở mức API. Nếu request thất bại sau khi server đã xử lý, không tự giả định retry an toàn, đặc biệt với POST không idempotent.

**Phân biệt nguyên nhân:**
- HTTP 404/500 hợp lệ → `HttpResponse<T>` với `statusCode()` tương ứng.
- DNS/connect/TLS/transport lỗi → `IOException` (hoặc exceptional completion trong `sendAsync`).
- Request timeout → `HttpTimeoutException`; connect timeout → `HttpConnectTimeoutException` khi phù hợp.
- Thread bị interrupt trong `send` → `InterruptedException`; khôi phục interrupt flag nếu xử lý trong method có policy như vậy.
- Đích file không ghi được/disk lỗi với `ofFile` → I/O failure, có thể còn file partial cần cleanup.

Không phải mọi `IOException` đều có nghĩa server chưa nhận request. Đặc biệt khi download hoặc request có side effects, hãy thiết kế retry/idempotency và cleanup rõ ràng.

## 14. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `ofString` cho hình ảnh/PDF/binary | Decode sai dữ liệu | `ofByteArray` hoặc `ofFile` |
| Dùng `ofByteArray` cho tệp hàng GB | Heap pressure/OOM | `ofFile` hoặc streaming |
| Nhầm `HttpResponse<String>` với `HttpResponse<byte[]>` | Compile/type mismatch | Kiểu `T` phải khớp handler |
| Tưởng `BodyPublisher` là handler response | Mã sai chiều | Publisher cho request, handler cho response |
| Quên đặt charset khi API quy định UTF-8 | Text lỗi ký tự trên một số server | `ofString(UTF_8)` hoặc xử lý header có chủ đích |
| Tin `ofString()` luôn dùng encoding hệ điều hành | Hiểu sai decoding | Java 17 dùng charset từ Content-Type, fallback UTF-8 |
| Gọi `new String(bytes)` mà không chọn charset | Text có thể không portable | Dùng `new String(bytes, UTF_8)` khi đúng contract |
| Tưởng `ofFile(path)` tự truncate file cũ | Trailing bytes cũ còn lại | Dùng `TRUNCATE_EXISTING` hoặc `CREATE_NEW` |
| Tưởng `ofFile` tự kiểm tra HTTP 2xx | Lưu HTML 404 như file thành công | Kiểm tra status/type/checksum trước khi công bố |
| Dùng path từ Content-Disposition không kiểm soát | Path traversal/ghi đè | Chọn path riêng, kiểm tra tên file, quarantine |
| Tưởng `discarding()` tương đương HEAD | Server vẫn có thể truyền body | Dùng HEAD khi API cho phép, hoặc discard có chủ đích |
| Tưởng `discarding()` nghĩa là HTTP 204 | Sai ngữ nghĩa | `HttpResponse<Void>.body()==null` do handler, không do status |
| Không cleanup file lỗi/partial | Rác disk hoặc phục vụ dữ liệu dở | Xóa temp, kiểm tra lỗi, atomic replace khi khả thi |
| Không giới hạn body input | DoS qua RAM/disk | Quota, size cap, streaming/custom handler |
| Tin mọi 404 phải ném IOException | Xử lý lỗi HTTP sai | Kiểm tra `statusCode()` |
| Bỏ qua Future exception ở `sendAsync` | Lỗi mạng/tệp bị nuốt | Handle exceptional completion và cleanup |
| Log toàn bộ response body | Lộ dữ liệu bí mật | Sanitized logging, giới hạn nội dung |
| Đọc ngược cả file lớn vào RAM sau `ofFile` | Mất lợi thế lưu file | Xử lý bằng streaming hoặc file APIs |

## 15. Bài tập tự kiểm tra

**1.** Bốn handler trả kiểu `HttpResponse<T>` nào?  
**Đáp án:** `ofString` → `HttpResponse<String>`; `ofByteArray` → `HttpResponse<byte[]>`; `ofFile` → `HttpResponse<Path>`; `discarding` → `HttpResponse<Void>`.

**2.** `ofString(StandardCharsets.UTF_8)` khác `ofString()` ở điểm nào?  
**Đáp án:** Bản có tham số dùng charset được chọn rõ ràng; bản không tham số đọc charset từ Content-Type nếu có/hỗ trợ, fallback UTF-8 theo Java 17.

**3.** Một byte FF xuất hiện là `-1` trong `byte[]`. Có lỗi mạng không?  
**Đáp án:** Không. Java byte là signed; dùng `bytes[i] & 0xff` để lấy giá trị unsigned.

**4.** Vì sao không dùng `ofByteArray()` tải file 5 GB?  
**Đáp án:** Nó tích lũy bytes trong heap, có thể OOM; lưu file/stream với quota phù hợp.

**5.** `BodyHandlers.ofFile(path)` có tự truncate file dài hơn trước đó không?  
**Đáp án:** Không. Mặc định tương đương `CREATE, WRITE`. Dùng `TRUNCATE_EXISTING` tường minh nếu muốn thay nội dung, hoặc `CREATE_NEW` nếu không cho ghi đè.

**6.** Nhận HTTP 404 với `ofFile(path)` có tự từ chối lưu không?  
**Đáp án:** Không. Handler được thiết kế nhận body bất kể status; ứng dụng kiểm tra response và có thể phải xóa file.

**7.** `discarding()` trả `body() == null` với HTTP 202 có bình thường không?  
**Đáp án:** Có. Kiểu body là `Void` và nội dung bị bỏ.

**8.** `discarding()` có giảm được mọi lưu lượng mạng của response không?  
**Đáp án:** Không. Server/client vẫn xử lý response trên wire; chỉ không giữ body làm kết quả.

**9.** `BodyHandlers.ofFile()` hoàn tất thành công thì `response.body()` là gì?  
**Đáp án:** `Path` chỉ tới tệp đã được ghi body theo contract.

**10.** `ofInputStream()` có cùng lifecycle với `ofString()` không?  
**Đáp án:** Không. Streaming handler có thể trả response trước khi body được đọc hết; caller phải đọc/đóng stream.

**11.** Vì sao `Content-Type: application/pdf` chưa đủ để tin tệp download là PDF hợp lệ?  
**Đáp án:** Header không phải bằng chứng; cần kiểm tra status, signature/magic bytes, size/hash hoặc parser tùy mức bảo mật.

**12.** Nếu `sendAsync(request, ofFile(path))` trả Future chưa completed, đã được công bố file chưa?  
**Đáp án:** Chưa nên. Chờ completion, kiểm tra response status và dữ liệu; file temp có thể đang được tạo/ghi.

## 16. Tài liệu tham khảo chính thức

- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): bốn factory methods, `ofFile` open options, charset mặc định, nguyên tắc không tự xét HTTP status.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): `HttpResponse<T>`, status, headers, body và response info.
- [Java SE 17 — HttpResponse.BodyHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): cách chọn subscriber dựa trên response metadata.
- [Java SE 17 — HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): body subscriber và completion semantics.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`, `sendAsync`, timeout và HTTP client lifecycle.
- [Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE`, `CREATE_NEW`, `WRITE`, `TRUNCATE_EXISTING`.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): tạo tệp temp, kiểm tra size, di chuyển/cleanup file.
- [Java SE 17 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): HTTP server nhỏ chỉ phục vụ các bài thử localhost.
