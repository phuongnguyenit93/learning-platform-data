# BodyHandlers.ofLines và vòng đời Stream khi đọc HTTP response (Java 11+)

## 1. Vì sao cần đọc HTTP response theo từng dòng?

Khi HTTP server trả về một đoạn văn bản dài, log, báo cáo dạng dòng, dữ liệu dòng liên tiếp hoặc một nội dung có thể xử lý từng phần, việc **đọc toàn bộ body thành một `String`** không phải lúc nào cũng phù hợp. Ta có thể muốn xử lý từng dòng ngay khi dữ liệu tới thay vì chờ tải hết hoặc giữ toàn bộ văn bản trong RAM.

Từ **Java 11**, HTTP Client chuẩn trong module `java.net.http` có factory:

```java
HttpResponse.BodyHandlers.ofLines()
```

Nó tạo một `BodyHandler<Stream<String>>`. Khi dùng để gửi request:

```java
HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());
```

`response.body()` lúc này là **`java.util.stream.Stream<String>`**, trong đó mỗi phần tử là một dòng văn bản của HTTP response. Đây là **stream có nguồn I/O**, không phải một `List<String>` đã nạp sẵn.

**Ba quy tắc quan trọng nhất:**

1. `send(..., ofLines())` có thể trả `HttpResponse` **trước khi toàn bộ body được nhận**. Việc nhận/giải mã dòng còn có thể tiếp tục khi ứng dụng duyệt stream.
2. **Một `Stream` chỉ tiêu thụ một lần.** Không duyệt, `count`, rồi dùng lại cùng stream để `forEach`.
3. **Phải đọc hết hoặc đóng stream khi không còn dùng.** Dùng `try-with-resources` quanh `response.body()` để đảm bảo giải phóng tài nguyên cả khi dừng sớm hoặc lỗi.

Bài tập trung vào *body streaming* và vòng đời `Stream` trong Java 11+, đồng thời trình bày charset, dấu kết thúc dòng, lỗi I/O, xử lý mã HTTP và giới hạn dữ liệu không tin cậy.

## 2. Kiểu dữ liệu, cơ chế và các đối tượng liên quan

### 2.1. Chữ ký và chu trình

`HttpResponse.BodyHandlers.ofLines()` trả:

```java
HttpResponse.BodyHandler<Stream<String>>
```

Kiểu kết quả từ `HttpClient`:

```java
HttpResponse<Stream<String>>
```

Sơ đồ luồng:

```text
HttpRequest
    |
    v
HttpClient.send(request, BodyHandlers.ofLines())
    |
    | Đọc HTTP response headers; body có thể vẫn đang đến
    v
HttpResponse<Stream<String>>
    |
    | response.statusCode(), headers(), uri(), version()
    |
    v
response.body(): Stream<String>
    |
    | Đọc byte từ kết nối khi cần
    | Giải mã byte -> ký tự theo charset
    | Tách thành các dòng
    v
Stream operations: filter / map / limit / forEach / count
    |
    v
Đọc đến hết (EOF) HOẶC stream.close() nếu dừng sớm
    |
    v
Giải phóng tài nguyên gắn với HTTP exchange
```

Khác với `BodyHandlers.ofString()` (tích lũy body thành `String` trước khi trả response), `ofLines()` cho ứng dụng **tiêu thụ dần** các dòng.

### 2.2. Stream của HTTP không phải collection

`Stream<String>` không phải `List<String>`; nó hỗ trợ các thao tác *pipeline*:

- `filter(predicate)`: chỉ giữ các dòng thỏa điều kiện.
- `map(function)`: biến đổi từng dòng.
- `limit(n)`: tiêu thụ nhiều nhất `n` phần tử từ pipeline này.
- `forEachOrdered(action)`: thực hiện hành động theo thứ tự phần tử của stream có thứ tự.
- `count()`: duyệt để đếm số phần tử.
- `findFirst()`: tìm phần tử đầu tiên; có thể dừng sớm.
- `anyMatch(predicate)`: kiểm tra điều kiện và có thể dừng sớm.

Các thao tác như `filter` và `map` là **trung gian, lười thực hiện**. Khi có thao tác kết thúc (`forEachOrdered`, `count`, `findFirst`...), stream mới được duyệt. Việc một lệnh `filter` trả một `Stream` mới **không** có nghĩa đã đọc xong response.

Không mặc định stream đang dựa trên dữ liệu tĩnh; khi lấy từ mạng, việc duyệt có thể phải **đợi server gửi byte tiếp theo**.

## 3. Vòng đời của Stream: sở hữu, tiêu thụ và đóng

### 3.1. Mẫu cơ bản nên sử dụng

```java
HttpResponse<Stream<String>> response =
        client.send(request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    lines.forEachOrdered(System.out::println);
}
```

Đây là **mảnh mã minh họa** trong phương thức có `client`, `request` và import `java.util.stream.Stream`; `client.send` có thể ném `IOException` và `InterruptedException`.

Vì `Stream` triển khai `AutoCloseable`, `try-with-resources` đảm bảo gọi `lines.close()` khi rời khối. Điều này quan trọng với nguồn I/O, kể cả khi:
- Pipeline chạy hoàn tất.
- Code gọi `limit(10)` rồi dừng.
- Code tìm được phần tử đầu tiên bằng `findFirst()`.
- Xảy ra lỗi khi xử lý từng dòng.
- Caller quyết định không đọc body do status HTTP không hợp lệ.

**Lưu ý:** với stream có nguồn I/O, gọi `close()` là nghĩa vụ quản lý tài nguyên. Không suy rộng từ những stream thuần bộ nhớ như `List.stream()` thường không cần đóng.

### 3.2. Đọc hết hay đóng sớm?

API của `HttpResponse.BodySubscribers.ofLines(Charset)` mô tả hai cách đảm bảo giải phóng tài nguyên:

1. **Đọc hết tất cả dòng cho đến hết stream**.
2. Nếu không muốn/không thể đọc hết, **gọi `BaseStream.close()`**.

Trong mã ứng dụng, dùng `try-with-resources` ngay cả khi dự kiến đọc hết là cách phòng lỗi tốt.

Khi **đóng stream trước khi đọc hết body**, HTTP Client có thể đóng kết nối HTTP bên dưới, khiến kết nối **không được tái sử dụng** cho request tiếp theo. Đây là hệ quả hiệu năng có thể có, không phải lý do để giữ stream mở mãi. Đóng sớm đúng lúc quan trọng hơn việc cố giữ kết nối đã không còn cần.

**Đừng giả định** chỉ gọi `limit(2)` thì dữ liệu còn lại tự được giải phóng. `limit` chỉ giới hạn số **phần tử stream được yêu cầu**, không thay thế `close`.

### 3.3. Mẫu dừng sớm đúng

```java
HttpResponse<Stream<String>> response =
        client.send(request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    lines.limit(2).forEachOrdered(System.out::println);
}
// Kết thúc try: close() được gọi, kể cả khi body còn nhiều dòng.
```

Đoạn này là **mã minh họa**, cần đặt trong phương thức có xử lý ngoại lệ từ `send`.

### 3.4. Không dùng lại một Stream đã tiêu thụ

**Sai:**

```java
Stream<String> lines = response.body();
long n = lines.count();
lines.forEach(System.out::println); // Không được duyệt lần hai.
```

Đây là **phản ví dụ**, có thể ném `IllegalStateException` vì stream đã bị thao tác kết thúc. Không nên viết như vậy cho cả stream HTTP lẫn stream thông thường.

**Đúng khi muốn đếm và xử lý cùng lúc:**

```java
AtomicInteger seen = new AtomicInteger();
try (Stream<String> lines = response.body()) {
    lines.forEachOrdered(line -> {
        System.out.println(line);
        seen.incrementAndGet();
    });
}
System.out.println("Đã đọc " + seen.get() + " dòng");
```

Đoạn minh họa cần import `java.util.concurrent.atomic.AtomicInteger`. Không phải luôn cần `AtomicInteger`; một biến đếm được quản lý trong vòng lặp tuần tự cũng phù hợp. Điều chính là **đếm và xử lý trong cùng một lượt duyệt**.

Muốn đọc lại body từ đầu, phải có nguồn có thể đọc lại (ví dụ body đã được lưu lại ở nơi phù hợp) hoặc gửi request khác khi nghiệp vụ cho phép. **Không dùng lại stream cũ**.

### 3.5. Không trả Stream ra khỏi phạm vi đã đóng

**Sai về vòng đời:**

```java
Stream<String> loadLines() throws Exception {
    HttpResponse<Stream<String>> response =
            client.send(request, HttpResponse.BodyHandlers.ofLines());
    try (Stream<String> lines = response.body()) {
        return lines; // Trả về đối tượng vừa bị đóng khi thoát try.
    }
}
```

Đây là **phản ví dụ** trong một lớp có `client` và `request`. Caller nhận stream đã đóng nên không còn dùng hợp lệ.

Thay vì trả một stream mà quyền đóng không rõ ràng, hãy:
- Xử lý stream **bên trong** phương thức rồi trả kết quả đã tính.
- Hoặc định nghĩa rõ hợp đồng chuyển **quyền sở hữu stream** cho caller; caller bắt buộc đóng đúng cách.

Khi có thể, ưu tiên cách thứ nhất để tránh rò rỉ tài nguyên.

## 4. Cách ofLines tách dòng: CR, LF, CRLF và dòng trống

`BodyHandlers.ofLines()` nhận byte, giải mã thành ký tự rồi tách theo quy tắc giống `BufferedReader.readLine()`.

Các dấu kết thúc dòng được hỗ trợ:
- `\n` (*line feed*, LF).
- `\r` (*carriage return*, CR).
- `\r\n` (CR ngay trước LF).

Dấu kết thúc dòng **không nằm trong `String` kết quả**. Nếu có nhiều dấu kết thúc dòng liên tiếp, có thể có dòng rỗng. Nếu body **kết thúc bằng một dấu xuống dòng**, không tự thêm một dòng rỗng thừa sau dấu cuối.

Ví dụ body đã giải mã:

```text
first\r\nViệt Nam\n\nlast\r
```

Đó là **biểu diễn escape** để giải thích dấu xuống dòng, không phải văn bản hiển thị nguyên vẹn. Stream tạo bốn phần tử theo thứ tự:

```text
[first]
[Việt Nam]
[]
[last]
```

Dòng thứ ba là chuỗi rỗng `""`, vì có hai dấu xuống dòng liên tiếp. Ví dụ đầy đủ ở mục 8 kiểm tra đúng dữ liệu này.

**Không nhầm đơn vị đếm:**
- `count()` đếm **số dòng**.
- `String.length()` của từng dòng đếm **đơn vị UTF-16**.
- Số byte đã tải qua HTTP phụ thuộc charset, content coding và lớp giao thức.

Nếu ứng dụng thực sự cần **giữ nguyên byte gốc, dấu `\r/\n` chính xác hoặc vị trí byte**, `ofLines()` không phải công cụ phù hợp vì nó đã giải mã và loại dấu kết thúc dòng. Hãy dùng `BodyHandlers.ofInputStream()` hoặc body handler byte phù hợp.

## 5. Charset: response Content-Type quyết định cách giải mã

`BodyHandlers.ofLines()` tự chọn charset theo **`Content-Type` của HTTP response**, theo quy tắc như `BodyHandlers.ofString()`:

- Nếu response khai báo một charset **được Java hỗ trợ**, Java dùng charset đó để biến byte thành ký tự.
- Nếu `Content-Type` thiếu hoặc không có charset dùng được, API mặc định dùng **UTF-8**.
- Chọn charset không đúng với byte server thực gửi có thể làm văn bản bị sai dấu (*mojibake*) hoặc xuất hiện ký tự thay thế.

Ví dụ response:

```http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=ISO-8859-1
```

Server gửi byte biểu diễn `"café\nfinal"` theo ISO-8859-1. `ofLines()` sẽ cho các dòng `"café"` và `"final"` khi dữ liệu và metadata nhất quán.

### 5.1. ofLines không có overload truyền Charset trực tiếp

Trong Java 11, factory tiện dụng là:

```java
HttpResponse.BodyHandlers.ofLines()
```

Không viết `BodyHandlers.ofLines(StandardCharsets.UTF_8)` vì overload đó **không tồn tại**.

Nếu giao thức riêng yêu cầu **chọn tường minh một charset bất chấp header**, có thể tạo `BodyHandler` bằng lambda trả về `BodySubscribers.ofLines(Charset)`:

```java
HttpResponse.BodyHandler<Stream<String>> utf8LineHandler =
        responseInfo ->
                HttpResponse.BodySubscribers.ofLines(StandardCharsets.UTF_8);
```

Đây là đoạn minh họa trong phạm vi có import các kiểu HTTP, `Stream` và `StandardCharsets`. Nó là kiến thức bổ trợ: nếu server tuân thủ `Content-Type`, `BodyHandlers.ofLines()` thường đơn giản và phù hợp hơn. Đừng ép UTF-8 đối với body thực sự được mã hóa ISO-8859-1 rồi cho rằng server sai.

**Quan trọng:** `Content-Type` không tự biến JSON thành đối tượng Java. Nếu server gửi **NDJSON/JSON Lines** (mỗi dòng là một JSON value), `ofLines()` chỉ tạo **chuỗi của từng dòng**. Ứng dụng vẫn phải parse JSON và xác thực schema bằng thư viện phù hợp. Không giả định mọi văn bản nhiều dòng đều là NDJSON hợp lệ.

### 5.2. Charset khác Content-Encoding

`Content-Type: text/plain; charset=utf-8` mô tả **văn bản và charset**; `Content-Encoding: gzip` là **cách mã hóa nén representation**. Chúng là hai lớp khác nhau.

Không giả định chỉ gọi `ofLines()` sẽ tự xử lý mọi body nén từ server. Nếu response có content coding cần giải mã riêng, phải áp dụng cơ chế phù hợp trước bước tách dòng. Với dữ liệu phải bảo toàn byte chính xác hoặc có định dạng nhị phân, ưu tiên đọc byte và giải mã có kiểm soát.

## 6. Xử lý status trước khi tiêu thụ stream

Một phản hồi HTTP `404` hoặc `500` **vẫn có thể có body** và vẫn có thể trả `HttpResponse<Stream<String>>` bình thường. `BodyHandlers.ofLines()` không tự ném exception chỉ vì status thuộc nhóm 4xx/5xx; body handler mặc định nhận cả body lỗi.

Ví dụ:

```java
HttpResponse<Stream<String>> response =
        client.send(request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    if (response.statusCode() >= 200 && response.statusCode() < 300) {
        lines.forEachOrdered(System.out::println);
    } else {
        // Không cần body lỗi: để try-with-resources đóng stream.
        System.err.println("HTTP " + response.statusCode());
    }
}
```

Đây là **mảnh mã minh họa** trong phương thức có xử lý ngoại lệ. Nếu nghiệp vụ cần nội dung lỗi để chẩn đoán, có thể đọc **một số dòng đã giới hạn hợp lý** trong try rồi đóng stream, tránh log dữ liệu nhạy cảm hoặc nội dung khổng lồ.

Đặc biệt, nếu code kiểm tra `statusCode()` rồi `return` ngay mà **không đóng body stream**, tài nguyên có thể còn bị giữ.

Đối với endpoint chỉ cần mã trạng thái và **không cần body nào**, có thể chọn từ đầu `BodyHandlers.discarding()` thay cho `ofLines()`. Khi đó kiểu body response là `Void`; HTTP client chủ động bỏ nội dung body theo handler. Nếu cần thay đổi handler **tùy status/headers** trước khi nhận body, có thể triển khai `BodyHandler` tùy chỉnh, nhưng chỉ làm khi có yêu cầu rõ.

## 7. Đọc tới cuối không đồng nghĩa dữ liệu nghiệp vụ đã hợp lệ

Giả sử server gửi 100.000 dòng. Code chỉ đọc 10 dòng đầu bằng `limit(10)` rồi đóng stream. Điều đó có nghĩa:

- Chương trình đã **xử lý tối đa 10 dòng** (tùy pipeline và dữ liệu).
- Chương trình **chưa** xác minh tất cả dòng còn lại.
- Kết nối có thể không tái sử dụng nếu bị đóng trước khi body tải hết.
- Không thể kết luận toàn bộ phản hồi là JSON Lines/CSV hợp lệ, hoặc báo cáo đã tải đầy đủ.

Nếu chức năng cần **toàn bộ dữ liệu**, hãy duyệt đến hết, theo dõi lỗi và chỉ đánh dấu hoàn tất sau khi xử lý thành công. Nếu chỉ cần **một mẫu** hoặc **dòng đầu tiên**, đóng sớm là đúng, nhưng cần ghi rõ kết quả là một phần.

Stream có tính *lazy*: `lines.filter(...)` không đọc mọi dòng ngay. Một chương trình có thể nhận response header 200 rồi bắt đầu xử lý dòng; lỗi network xuất hiện **sau đó** khi duyệt stream. `statusCode() == 200` không bảo đảm mọi byte body đã tới hoặc đã được parse thành công.

## 8. Chương trình Java 11+ hoàn chỉnh, có HTTP server cục bộ

Ví dụ sau dùng `HttpClient` chuẩn để gọi một **HTTP server chỉ lắng nghe `127.0.0.1`**, do chính chương trình tạo. Server fixture giúp minh họa dữ liệu dòng, charset, HTTP 404 và `sendAsync` **không cần Internet bên ngoài**.

Chương trình dùng:
- `/lines`: văn bản UTF-8 với `\r\n`, `\n`, dòng trống và `\r`.
- `/latin`: văn bản ISO-8859-1 có chữ `é`.
- `/missing`: response 404, vẫn phải đóng body stream dù không sử dụng.
- `limit(2)`: dừng sớm và đóng bằng `try-with-resources`.
- `sendAsync`: đếm dòng không rỗng bên trong callback rồi trả kết quả đã hoàn tất.

Lưu thành **`HttpLinesDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public class HttpLinesDemo {
    private static void reply(HttpExchange exchange, int status,
                              String type, byte[] bytes) throws IOException {
        try {
            exchange.getResponseHeaders().set("Content-Type", type);
            exchange.sendResponseHeaders(status, bytes.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(bytes);
            }
        } finally {
            exchange.close();
        }
    }

    private static HttpRequest get(URI uri) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/lines", exchange ->
                reply(exchange, 200, "text/plain; charset=utf-8",
                        "first\r\nViệt Nam\n\nlast\r"
                            .getBytes(StandardCharsets.UTF_8)));
        server.createContext("/latin", exchange ->
                reply(exchange, 200, "text/plain; charset=ISO-8859-1",
                        "café\nfinal".getBytes(StandardCharsets.ISO_8859_1)));
        server.createContext("/missing", exchange ->
                reply(exchange, 404, "text/plain; charset=utf-8",
                        "not found\n".getBytes(StandardCharsets.UTF_8)));
        server.start();

        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpResponse<Stream<String>> response = client.send(
                    get(base.resolve("/lines")),
                    HttpResponse.BodyHandlers.ofLines());
            System.out.println("status=" + response.statusCode());
            AtomicInteger count = new AtomicInteger();
            try (Stream<String> lines = response.body()) {
                lines.forEachOrdered(line -> {
                    System.out.println("line=[" + line + "]");
                    count.incrementAndGet();
                });
            }
            System.out.println("lineCount=" + count.get());

            HttpResponse<Stream<String>> shortResponse = client.send(
                    get(base.resolve("/lines")),
                    HttpResponse.BodyHandlers.ofLines());
            try (Stream<String> lines = shortResponse.body()) {
                lines.limit(2).forEachOrdered(
                        line -> System.out.println("firstTwo=[" + line + "]"));
            }
            System.out.println("shortClosed=true");

            HttpResponse<Stream<String>> latin = client.send(
                    get(base.resolve("/latin")),
                    HttpResponse.BodyHandlers.ofLines());
            try (Stream<String> lines = latin.body()) {
                lines.forEachOrdered(
                        line -> System.out.println("latin=[" + line + "]"));
            }

            HttpResponse<Stream<String>> missing = client.send(
                    get(base.resolve("/missing")),
                    HttpResponse.BodyHandlers.ofLines());
            System.out.println("missingStatus=" + missing.statusCode());
            try (Stream<String> unused = missing.body()) {
                // Từ chối 404: không đọc body, nhưng vẫn đóng stream.
            }
            System.out.println("errorStreamClosed=true");

            CompletableFuture<Long> async = client.sendAsync(
                    get(base.resolve("/lines")),
                    HttpResponse.BodyHandlers.ofLines()
            ).thenApply(res -> {
                try (Stream<String> lines = res.body()) {
                    return lines.filter(line -> !line.isEmpty()).count();
                }
            });
            System.out.println("asyncNonEmpty=" + async.join());
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch bằng compiler hỗ trợ mức Java 11 và chạy:

```bash
javac -encoding UTF-8 --release 11 HttpLinesDemo.java
java HttpLinesDemo
```

**Đầu ra đã kiểm chứng trên JDK 24 khi biên dịch bằng `--release 11`:**

```text
status=200
line=[first]
line=[Việt Nam]
line=[]
line=[last]
lineCount=4
firstTwo=[first]
firstTwo=[Việt Nam]
shortClosed=true
latin=[café]
latin=[final]
missingStatus=404
errorStreamClosed=true
asyncNonEmpty=3
```

### 8.1. Giải thích kết quả

- `status=200` là metadata HTTP. Khi code nhận được response, body có thể chưa tải hết; các dòng được lấy khi duyệt `response.body()`.
- `line=[first]` và `line=[Việt Nam]`: stream đã tách `\r\n` và `\n`, không giữ ký tự xuống dòng.
- `line=[]`: có **một dòng rỗng** giữa hai dấu xuống dòng liên tiếp.
- `line=[last]`: `\r` cuối cùng kết thúc dòng, không tạo thêm dòng rỗng.
- `lineCount=4`: đã duyệt đủ bốn dòng theo thứ tự.
- `firstTwo=[...]` và `shortClosed=true`: `limit(2)` chỉ yêu cầu hai dòng, sau đó `try-with-resources` đóng stream; chuỗi `shortClosed=true` là thông báo sau khi thoát khối try, **không** đo xem kết nối bên dưới có được tái sử dụng không.
- `latin=[café]` chứng minh `ofLines()` sử dụng charset ISO-8859-1 từ `Content-Type` của response, thay vì luôn ép UTF-8.
- `missingStatus=404` nhưng `send` vẫn trả `HttpResponse`. Vì app không cần body lỗi, stream được đóng ngay.
- `asyncNonEmpty=3`: có ba dòng không rỗng (`first`, `Việt Nam`, `last`). Callback bất đồng bộ tự duyệt và đóng stream rồi `join()` chờ kết quả đã xử lý.

Ví dụ dùng HTTP trên **loopback để kiểm thử**, không khuyến nghị gửi dữ liệu nhạy cảm không mã hóa trên mạng thật. Module `com.sun.net.httpserver` được dùng làm **fixture server** (thuộc `jdk.httpserver`); trong dự án chỉ làm client, bạn không cần dùng module server này. Nếu tổ chức source theo `module-info.java`, cần khai báo `requires java.net.http;` cho client và thêm `requires jdk.httpserver;` chỉ khi dùng fixture server. Lệnh trên chạy bằng **classpath**, không yêu cầu tệp module-info.

## 9. sendAsync + ofLines: Future có thể hoàn thành trước khi body xong

Cách đơn giản:

```java
CompletableFuture<HttpResponse<Stream<String>>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofLines());
```

Với body handler này, future chứa response có thể hoàn thành **khi đã có headers và stream để đọc**, chứ không nhất thiết sau khi mọi dòng đã được tiêu thụ.

**Đừng viết:**

```java
HttpResponse<Stream<String>> response = future.join();
System.out.println("Download completed");
// Nếu chưa duyệt/đóng response.body(), kết luận trên có thể sai.
```

`future.join()` chỉ chờ **future của response**. Nó không tự động làm một dòng response body dạng stream được duyệt đến EOF.

### 9.1. Ghép việc duyệt và đóng vào CompletableFuture

```java
CompletableFuture<Long> processed = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofLines()
).thenApply(response -> {
    try (Stream<String> lines = response.body()) {
        return lines.filter(s -> !s.isEmpty()).count();
    }
});

long nonEmptyLineCount = processed.join();
```

Đây là **mảnh mã minh họa** trong phạm vi có `client`, `request`, `Stream` và `CompletableFuture`. Ở đây `processed` chỉ hoàn thành thành công sau khi callback đã **đếm hết dòng** và đóng stream. Cách này hợp lý khi caller thật sự cần kết quả đếm.

**Cảnh báo về blocking:** duyệt `Stream<String>` đọc từ network có thể **chờ dữ liệu tiếp theo**. Khi gọi `thenApply`, phần xử lý này có thể chạy trên luồng hoàn thành future (tùy cơ chế thực thi); đừng gắn công việc đọc dài/CPU lớn vào một luồng quan trọng mà không có chiến lược executor phù hợp. Có thể cân nhắc `thenApplyAsync(..., executor)` và cơ chế giới hạn tài nguyên/hủy tác vụ trong hệ thống có nhiều request.

### 9.2. Xử lý exception của Future

Lỗi mạng có thể khiến future `sendAsync` hoàn thành thất bại. Lỗi phát sinh khi duyệt stream trong callback cũng có thể khiến `processed` hoàn thành thất bại; khi `join()`, lỗi thường được bao trong `CompletionException`.

Không coi một future **thành công** là đủ để kết luận status thuộc nhóm 2xx. Ngay cả trong pipeline bất đồng bộ, phải kiểm tra `response.statusCode()`; phản hồi 404 vẫn có thể hoàn thành bình thường.

Nếu xử lý lỗi bằng `handle` hoặc `exceptionally`, hãy **không nuốt lỗi** rồi trả kết quả rỗng như thể đã tải đầy đủ. Ghi rõ trạng thái thất bại với các ràng buộc nghiệp vụ phù hợp và đảm bảo stream được đóng sau khi đã có `HttpResponse`.

## 10. Lỗi I/O trong khi duyệt Stream

Ở chế độ đọc toàn bộ bằng `BodyHandlers.ofString()`, lỗi đọc body thường phát sinh ngay trong giai đoạn `send`/future của request. Với **streaming body**, việc nhận response thành công không chứng minh những dòng chưa đọc sau đó sẽ đến đầy đủ.

Có ít nhất ba thời điểm cần nghĩ tới:

| Thời điểm | Dấu hiệu có thể gặp | Điều cần làm |
| --- | --- | --- |
| Trước khi nhận response | Kết nối lỗi, timeout, TLS thất bại; `send` ném `IOException`/`InterruptedException`. | Xử lý ở tầng gọi HTTP; không giả tạo status 500 khi không có response. |
| Sau khi có response, lúc duyệt lines | Kết nối bị cắt, byte không hợp lệ hoặc đọc body lỗi; có thể thấy `UncheckedIOException` khi stream pipeline truy cập I/O. | Đảm bảo đóng stream, đánh dấu xử lý thất bại, không dùng kết quả từng phần như hoàn chỉnh. |
| Trong logic xử lý từng dòng | Parser, validator hay callback ném exception. | Để try-with-resources đóng stream; phân biệt lỗi nghiệp vụ với lỗi network. |

`Stream` API không cho phép hầu hết thao tác pipeline ném checked `IOException` trực tiếp; lỗi I/O khi duyệt nguồn có thể được báo qua **`java.io.UncheckedIOException`**. Vì vậy `catch(IOException)` chỉ bao quanh `client.send(...)` **không bao phủ chắc chắn mọi lỗi xảy ra ở terminal operation của stream**.

Đoạn xử lý minh họa:

```java
HttpResponse<Stream<String>> response =
        client.send(request, HttpResponse.BodyHandlers.ofLines());
try (Stream<String> lines = response.body()) {
    lines.forEachOrdered(this::handleLine);
} catch (java.io.UncheckedIOException ex) {
    // Lỗi I/O trong lúc duyệt nguồn stream.
    throw ex;
}
```

Đây là **mã minh họa bên trong lớp**, giả định có phương thức `handleLine(String)`, các import và phương thức bao ngoài xử lý exception của `send`. Trong ứng dụng thật, nhánh catch cần thực hiện chính sách phục hồi/ghi nhận lỗi phù hợp, không chỉ ném lại cho có. Không log nguyên dữ liệu nhạy cảm hoặc stack trace ra response công khai.

**Khi nguồn bị cắt:** một số dòng đầu có thể đã được xử lý trước khi lỗi xuất hiện. Nếu tính toàn vẹn quan trọng, cần tổ chức xử lý theo cơ chế tạm thời/transaction, chỉ xác nhận hoàn thành khi đến EOF hợp lệ, không công bố kết quả dở dang như thành công.

## 11. Giới hạn dữ liệu: streaming không bảo đảm bộ nhớ vô hạn an toàn

Dùng `ofLines()` có thể tiết kiệm bộ nhớ so với nạp toàn bộ body, vì không cần tạo một `String` chứa tất cả nội dung trước khi xử lý. Nhưng **không đồng nghĩa rằng mọi phản hồi lớn đều an toàn**.

### 11.1. Một dòng có thể rất lớn

Nếu server gửi body có hàng trăm MB **không có `\n` hoặc `\r`**, thư viện cần tìm ra ranh giới dòng; nội dung của một dòng có thể trở thành một `String` rất lớn. `ofLines()` **không cung cấp tham số giới hạn độ dài tối đa của từng dòng**.

Hơn nữa:
- `lines.collect(Collectors.toList())` lại tích lũy **mọi dòng trong RAM**, mất lợi ích xử lý từng phần.
- `lines.count()` cần duyệt toàn bộ nguồn, có thể chạy lâu.
- `lines.limit(100)` chỉ giới hạn **số dòng**, không giới hạn **byte đầu vào** hoặc **độ dài một dòng**.
- `Content-Length` có thể không có hoặc không phản ánh byte sau giải nén; đừng chỉ dựa vào header làm giới hạn duy nhất.

Nếu hệ thống nhận nội dung không tin cậy và cần **giới hạn cứng theo byte hoặc từng dòng**, có thể chọn `BodyHandlers.ofInputStream()` với bộ đếm byte, reader/decoder và parser giới hạn kích thước từng dòng, hoặc tự xây dựng body subscriber phù hợp. Luôn xem xét thêm deadline/timeouts, cancellation, số request đồng thời và điều kiện giải nén.

### 11.2. Tách khái niệm số dòng, số byte và thời gian

| Giới hạn | `ofLines()` có tự bảo đảm không? | Gợi ý |
| --- | --- | --- |
| Số dòng **được xử lý** | Có thể dùng pipeline `limit(n)`. | Vẫn phải đóng stream sau khi dừng. |
| Số **byte đã tải** | Không có tham số giới hạn trực tiếp trên `ofLines()`. | Cân nhắc nguồn byte giới hạn trước khi decode/tách dòng. |
| Kích thước **một dòng** | Không có tham số trực tiếp. | Dùng parser có ngưỡng mỗi dòng nếu nguồn không tin cậy. |
| Thời gian chờ toàn tác vụ | Không tự phát sinh từ kiểu `Stream`. | Thiết lập request timeout và cơ chế giám sát/hủy phù hợp. |
| Số body stream đồng thời | Không tự giới hạn theo nghiệp vụ. | Dùng giới hạn concurrency và quản lý đóng nguồn. |

Với endpoint trả nội dung **lớn nhưng gồm các dòng hợp lệ kích thước vừa phải**, xử lý theo stream vẫn là lựa chọn rất hữu ích.

## 12. So sánh với các BodyHandler khác

| BodyHandler | Kiểu `HttpResponse<T>` | Khi nào chọn |
| --- | --- | --- |
| `BodyHandlers.ofLines()` | `HttpResponse<Stream<String>>` | Text chia dòng; xử lý dần bằng Stream pipeline. |
| `BodyHandlers.ofString()` | `HttpResponse<String>` | Text/JSON nhỏ, muốn có trọn body trước khi xử lý. |
| `BodyHandlers.ofString(charset)` | `HttpResponse<String>` | Text nhỏ, caller muốn chỉ định charset rõ ràng. |
| `BodyHandlers.ofInputStream()` | `HttpResponse<InputStream>` | Cần kiểm soát byte, parser tùy biến hoặc tự giải mã. |
| `BodyHandlers.ofByteArray()` | `HttpResponse<byte[]>` | Byte nhỏ/vừa, cần giữ nguyên byte trong bộ nhớ. |
| `BodyHandlers.ofFile(path)` | `HttpResponse<Path>` | Lưu body vào file; cần giới hạn và chính sách file. |
| `BodyHandlers.discarding()` | `HttpResponse<Void>` | Không cần nội dung body. |

**Không nhầm `ofLines()` với `BodySubscribers.ofLines(Charset)`:**
- `BodyHandlers.ofLines()` là **factory cấp cao**, chọn charset theo response headers.
- `BodySubscribers.ofLines(Charset)` là **factory cấp subscriber**, yêu cầu caller cung cấp charset; dùng trong handler tùy chỉnh nếu thật sự cần.
- Với các body handler khác, `BodyHandlers.ofString(Charset)` **có** overload charset, nhưng `BodyHandlers.ofLines(Charset)` **không có** trong Java 11.

Nếu cần xử lý từng dòng bằng `Flow.Subscriber` thay vì `Stream`, bộ API Java 11 còn có `BodyHandlers.fromLineSubscriber(...)`. Đây là phương án dành cho mô hình subscriber và quản lý backpressure/đồng thời tương ứng, **không cần thay thế `ofLines()` khi bài toán đơn giản chỉ duyệt từng dòng**.

## 13. Những lỗi thường gặp khi dùng ofLines và cách sửa

| Lỗi | Vì sao không đúng | Cách làm |
| --- | --- | --- |
| Gọi `response.body().forEach(...)` rồi không đóng stream. | Nếu dừng sớm hoặc lỗi, tài nguyên HTTP có thể còn bị giữ. | Dùng `try (Stream<String> lines = response.body()) { ... }`. |
| Nghĩ `send(...ofLines())` đồng nghĩa toàn bộ body đã tải. | Response có thể trả trước khi nhận xong body. | Duyệt đến EOF hoặc đóng stream nếu bỏ qua. |
| Dùng `limit(5)` nhưng không đóng. | Giới hạn phần tử không phải giải phóng resource. | Đóng stream trong `finally`/try-with-resources. |
| `count()` xong gọi `forEach` trên cùng stream. | Một stream chỉ dùng một lần. | Đếm và xử lý trong một lượt, hoặc tạo request khác khi hợp lệ. |
| Lưu stream rồi dùng sau khi phương thức đã đóng nó. | Stream không còn hợp lệ sau `close()`. | Xử lý trong phạm vi try hoặc chuyển quyền sở hữu rõ ràng. |
| Giả định ofLines luôn UTF-8. | Charset được chọn từ Content-Type khi có giá trị hỗ trợ. | Kiểm tra header và thiết kế encoding nhất quán. |
| Gọi `BodyHandlers.ofLines(UTF_8)`. | Không tồn tại overload này trong Java 11. | Dùng `ofLines()` hoặc custom handler với `BodySubscribers.ofLines(Charset)`. |
| Nghĩ dấu `\n` nằm trong chuỗi dòng. | ofLines bỏ ký tự phân cách dòng. | Dùng nguồn byte nếu cần giữ nguyên dấu newline. |
| HTTP 404 thì không cần đóng stream. | Body handler vẫn có thể cung cấp nguồn dữ liệu. | Đóng stream dù bỏ body lỗi. |
| Dùng `catch(IOException)` quanh send rồi coi như bắt mọi lỗi body. | Lỗi I/O trong lúc duyệt có thể thành `UncheckedIOException`. | Xử lý lỗi cả khi terminal operation chạy. |
| Tưởng `limit(100)` phòng được body cực lớn. | Một dòng có thể dài vô hạn theo nghiệp vụ. | Giới hạn byte/từng dòng với parser phù hợp. |
| Đưa toàn bộ dòng vào `Collectors.toList()` không giới hạn. | Dù có stream, toàn bộ kết quả lại nằm trong RAM. | Xử lý từng dòng hoặc thu thập có ngưỡng rõ. |
| Tưởng HTTP 200 chứng minh toàn bộ NDJSON hợp lệ. | Chưa đọc/parse mọi dòng và xử lý lỗi. | Chỉ xác nhận hoàn tất sau khi đến EOF, kiểm tra schema. |
| Dùng `parallel()` tùy tiện để đọc HTTP stream. | Nguồn I/O tuần tự, xử lý song song có thể tăng phức tạp và mất thứ tự hành động. | Mặc định xử lý tuần tự, chỉ dùng concurrency theo thiết kế rõ. |

## 14. Tình huống thực tế: xử lý dòng theo từng nhiệm vụ

### 14.1. Đọc log dạng dòng từ HTTP

Giả sử endpoint trả log dạng text với một record trên mỗi dòng. Ta có thể xử lý từng record trong pipeline:

```java
HttpResponse<Stream<String>> response =
        client.send(request, HttpResponse.BodyHandlers.ofLines());
try (Stream<String> lines = response.body()) {
    if (response.statusCode() != 200) {
        throw new IllegalStateException(
                "Unexpected HTTP status: " + response.statusCode());
    }
    lines.filter(s -> !s.isBlank())
         .forEachOrdered(this::processRecord);
}
```

Đây là **mảnh mã minh họa trong một lớp**, `processRecord(String)` do ứng dụng cung cấp. `String.isBlank()` có từ Java 11. Cần import/ngoại lệ của `send` đúng cách. Phương pháp này chỉ phù hợp nếu dữ liệu được quy ước **mỗi record trên một dòng**, không tự áp dụng cho CSV có trường quoted chứa newline hoặc JSON thông thường được pretty-print nhiều dòng.

Nếu parser có thể ném lỗi, `try-with-resources` vẫn đóng stream; ứng dụng cần xác định có rollback kết quả từng dòng đã xử lý hay không.

### 14.2. Lấy hai dòng đầu để xem trước

```java
try (Stream<String> lines = response.body()) {
    lines.limit(2).forEachOrdered(System.out::println);
}
```

Đây là kết quả **preview**, không phải body hoàn chỉnh. Vì đóng sớm, kết nối có thể không được tái sử dụng; chấp nhận hệ quả đó nếu nghiệp vụ chủ động chỉ cần hai dòng.

### 14.3. Đếm dòng từ một endpoint

```java
long total;
try (Stream<String> lines = response.body()) {
    total = lines.count();
}
```

`count()` chỉ hoàn tất khi nguồn hết. Nếu server gửi dữ liệu liên tục hoặc rất chậm, xử lý có thể chờ lâu. Đối với dòng dữ liệu vô hạn, phải có điều kiện dừng và cơ chế đóng/hủy hợp lý.

## 15. Bài tập tự kiểm tra và đáp án

**Câu 1.** `BodyHandlers.ofLines()` trả `BodyHandler<String>` hay `BodyHandler<Stream<String>>`?

**Đáp án:** `BodyHandler<Stream<String>>`. `HttpResponse.body()` có kiểu `Stream<String>` nếu gọi với handler đó.

**Câu 2.** Khi `client.send(request, BodyHandlers.ofLines())` trả response, có thể khẳng định mọi byte đã tải xong chưa?

**Đáp án:** Không. Response có thể sẵn sàng khi đã đọc headers, body vẫn đang đến và sẽ được đọc khi duyệt stream.

**Câu 3.** Dùng `lines.limit(2).forEachOrdered(...)` có cần `lines.close()` không?

**Đáp án:** Có. `limit` dừng sớm; bao `lines` trong `try-with-resources` để đóng nguồn I/O khi kết thúc.

**Câu 4.** Body `"a\n\nb\n"` tạo bao nhiêu phần tử dòng?

**Đáp án:** Ba: `"a"`, `""`, `"b"`. Dấu xuống dòng cuối không tự tạo thêm một phần tử rỗng sau cùng.

**Câu 5.** Hai dấu `\r\n` trong HTTP body có được giữ lại trong `String` của mỗi dòng không?

**Đáp án:** Không. Chúng là ký tự phân cách dòng và bị loại khỏi chuỗi dòng trả về.

**Câu 6.** Response có `Content-Type: text/plain; charset=ISO-8859-1`. `ofLines()` luôn decode UTF-8 chứ?

**Đáp án:** Không. Nó dùng charset được xác định từ response Content-Type theo hợp đồng, fallback UTF-8 khi không có/không hỗ trợ.

**Câu 7.** Có thể gọi `BodyHandlers.ofLines(StandardCharsets.UTF_8)` với Java 11 không?

**Đáp án:** Không có overload đó. Nếu cần chỉ định charset, có thể tạo handler tùy chỉnh dùng `BodySubscribers.ofLines(Charset)`.

**Câu 8.** Status 404 và app không muốn đọc body; nên làm gì?

**Đáp án:** Vẫn phải **đóng stream** nếu đã chọn `ofLines()`. Nếu ngay từ đầu không cần body, có thể dùng `BodyHandlers.discarding()`.

**Câu 9.** Tại sao `client.sendAsync(...ofLines()).join()` không nhất thiết có nghĩa toàn bộ body đã được xử lý?

**Đáp án:** Future của response có thể hoàn tất sớm. Phải duyệt stream đến hết hoặc chờ future **chứa công việc tiêu thụ body** như `thenApply` trong ví dụ.

**Câu 10.** `lines.count()` chạy xong, có thể gọi tiếp `lines.forEach(...)` không?

**Đáp án:** Không. Stream chỉ tiêu thụ một lượt; thao tác thứ hai là sử dụng sai vòng đời.

**Câu 11.** `limit(100)` có đảm bảo không cần quá nhiều bộ nhớ khi server gửi một dòng dài 2 GB không?

**Đáp án:** Không. `limit` giới hạn **số dòng**, không giới hạn **độ dài mỗi dòng hoặc tổng byte nhận**. Cần parser/byte stream có giới hạn cứng nếu nguồn không tin cậy.

**Câu 12.** Sau khi nhận status 200, kết nối đứt ở dòng thứ 50 thì có được coi 49 dòng đầu là toàn bộ dữ liệu hợp lệ không?

**Đáp án:** Không, trừ khi nghiệp vụ chủ động chỉ yêu cầu một phần. Lỗi khi duyệt có thể báo bằng runtime exception như `UncheckedIOException`; cần đóng stream và đánh dấu giao dịch không hoàn tất.

## 16. Kết luận và tài liệu tham khảo chính thức

- **`BodyHandlers.ofLines()` có từ Java 11**, nhận HTTP response body dưới dạng `Stream<String>` các dòng đã giải mã.
- Với handler này, `HttpResponse` có thể xuất hiện **trước khi body nhận hoàn chỉnh**. `Stream` chứa công việc đọc dữ liệu tiếp theo, không phải collection đã tải hết.
- Stream là **one-shot** và là **tài nguyên I/O cần đóng**. Dùng `try-with-resources` quanh `response.body()`; `limit`/`findFirst` không thay thế `close`.
- Nếu dừng sớm, việc đóng stream có thể khiến HTTP connection không được tái sử dụng — điều đó chấp nhận được để giải phóng tài nguyên.
- Dòng được phân cách theo quy tắc `BufferedReader.readLine()` với LF, CR và CRLF; dấu phân cách không đi vào `String` kết quả.
- Charset được chọn từ response `Content-Type` theo quy tắc của `ofString()`, fallback UTF-8; không có overload `BodyHandlers.ofLines(Charset)` trên Java 11.
- **HTTP status 404/500 không tự là lỗi I/O**; với `ofLines` vẫn phải đóng stream dù không đọc body lỗi.
- Với `sendAsync`, future của response có thể hoàn thành trước việc duyệt body; cần điều phối completion của **công việc xử lý stream**.
- Streaming giúp giảm tích lũy body, nhưng **không tự giới hạn kích thước một dòng hoặc số byte**; thiết kế phòng vệ phù hợp với dữ liệu không tin cậy.
- Nếu cần giữ byte nguyên bản hoặc áp dụng giới hạn cứng ở mức byte, chọn `ofInputStream()` hoặc subscriber/decoder tùy chỉnh thay vì mặc định `ofLines()`.

Tài liệu API chính thức vẫn còn áp dụng:
- [Java SE 11 — HttpResponse.BodyHandlers.ofLines()](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html#ofLines()).
- [Java SE 11 — HttpResponse.BodySubscribers.ofLines(Charset) và quy tắc giải phóng stream](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html#ofLines(java.nio.charset.Charset)).
- [Java SE 11 — Stream<T> và close/one-shot](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/stream/Stream.html).
- [Java SE 11 — BufferedReader.readLine()](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/BufferedReader.html#readLine()).
- [Java SE 11 — HttpResponse](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html).
- [Java SE 11 — HttpClient](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).