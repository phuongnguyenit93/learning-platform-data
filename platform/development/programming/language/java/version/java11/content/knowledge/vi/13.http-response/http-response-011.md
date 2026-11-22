# Java 11+ — HTTP Response: Kiểm thử lỗi mã hóa, response rỗng và dữ liệu sai cấu trúc

## 1. Mục tiêu và ba nhóm lỗi phải phân biệt

Java 11 đưa `java.net.http.HttpClient` và `HttpResponse` vào API chuẩn. Một response có ít nhất ba lớp thông tin cần kiểm thử độc lập:

1. **Giao thức HTTP:** `statusCode()` và headers cho biết phía server trả trạng thái gì; mã `2xx`, `4xx` hay `5xx` không nói đầy đủ nội dung body có hợp lệ với nghiệp vụ hay không.
2. **Byte và charset:** body đến từ mạng là **byte**. Nếu chọn `BodyHandlers.ofString(...)`, Java phải giải mã byte thành `String` theo charset. Byte sai hoặc charset khai báo sai có thể tạo ký tự không mong muốn, trong khi việc nhận HTTP vẫn thành công.
3. **Cấu trúc dữ liệu ứng dụng:** một chuỗi có thể giải mã UTF-8 hoàn toàn hợp lệ nhưng **không tuân thủ format/schema**, chẳng hạn thiếu trường bắt buộc, sai kiểu, thiếu dấu phân cách, giá trị quá giới hạn hoặc không phải JSON hợp lệ.

Ngoài ra, response có **body rỗng** có thể hoàn toàn hợp lệ (ví dụ HTTP `204 No Content`), hoặc là lỗi nghiệp vụ (ví dụ endpoint bắt buộc trả tài liệu). Vì vậy đừng coi tất cả response rỗng, tất cả body có dấu lỗi mã hóa và tất cả status lỗi là cùng một loại ngoại lệ.

Bài này dùng API còn phù hợp với Java hiện đại: `HttpClient`, `HttpRequest`, `HttpResponse.BodyHandlers`, `StandardCharsets`, `CharsetDecoder` và kiểm thử bằng HTTP server chạy cục bộ. Chương trình chính tương thích **Java 11**; không cần thư viện bên thứ ba, Internet hay một dịch vụ production.

## 2. `BodyHandler` quyết định cách nhận response body

Một request thực tế thường được gửi như sau:

```java
// Minh họa trong phương thức đã khai báo/khởi tạo client, request.
// Cần bắt hoặc khai báo IOException và InterruptedException.
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

int status = response.statusCode();
String body = response.body();
```

`HttpResponse.BodyHandlers` cung cấp những cách nhận body có mục đích khác nhau:

| BodyHandler | Kiểu trả về | Dùng khi nào? |
| --- | --- | --- |
| `BodyHandlers.ofString()` | `HttpResponse<String>` | Response văn bản; dùng charset khai báo trong `Content-Type` nếu hỗ trợ, nếu vắng hoặc không hỗ trợ thì dùng UTF-8. |
| `BodyHandlers.ofString(StandardCharsets.UTF_8)` | `HttpResponse<String>` | Giao thức phía ứng dụng **quy định** response là UTF-8; không dựa vào charset từ header. |
| `BodyHandlers.ofByteArray()` | `HttpResponse<byte[]>` | Cần kiểm tra **byte chính xác**, phân tích lỗi giải mã nghiêm ngặt hoặc lưu fixture nhị phân. |
| `BodyHandlers.discarding()` | `HttpResponse<Void>` | Chủ động bỏ body; không thể xác nhận nội dung sau khi bỏ. |
| `BodyHandlers.ofInputStream()` | `HttpResponse<InputStream>` | Đọc body theo luồng khi không muốn giữ toàn bộ trong RAM; người gọi phải đọc/đóng stream. |

**Điểm quan trọng:** các predefined body handler thông thường **không tự bác response chỉ vì status là 4xx/5xx**. Một `HttpResponse<String>` có thể chứa HTTP `422` và body mô tả lỗi; tự kiểm tra `statusCode()` mới là trách nhiệm của code ứng dụng. Đây là điều quan trọng khi viết test: đừng chỉ `assertDoesNotThrow(client.send(...))` rồi cho là yêu cầu thành công.

## 3. Kiểm thử lỗi mã hóa: khai báo charset và byte thật

### 3.1. `ofString()` và `ofString(Charset)` khác nhau

Theo Javadoc Java 11:

- `BodyHandlers.ofString()` chọn charset từ `Content-Type` của response. Nếu không có header phù hợp hoặc charset không được hỗ trợ, mặc định là **UTF-8**.
- `BodyHandlers.ofString(StandardCharsets.UTF_8)` dùng charset **tường minh do caller chỉ định**, ngay cả khi server khai báo charset khác.
- `BodyHandlers.ofByteArray()` **không giải mã**; byte vẫn nguyên vẹn để ứng dụng kiểm tra sau.

Ví dụ server thực sự phát `Café` theo ISO-8859-1: chữ `é` có byte `E9`, nhưng trong UTF-8 phải là `C3 A9`. Nếu header là `Content-Type: text/plain; charset=ISO-8859-1`, `ofString()` có thể giải mã đúng, còn ép UTF-8 sẽ xem byte `E9` không hợp lệ và có thể tạo ký tự thay thế `U+FFFD`.

```java
HttpResponse<String> fromHeader = client.send(
        request, HttpResponse.BodyHandlers.ofString());

HttpResponse<String> forcedUtf8 = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
```

Hai dòng chỉ là **minh họa cú pháp**; `client`/`request` phải được định nghĩa, và mỗi lời gọi tạo một HTTP request riêng. Nếu nghiệp vụ quy định “mọi response đều UTF-8” thì **ép UTF-8 và kiểm tra tính hợp lệ** thường tốt hơn việc tự tin rằng header không thể sai.

**Không tin charset header một cách mù quáng:** header nói định dạng *được khai báo*, chưa chứng minh byte thật khớp. Cũng không tự suy đoán bảng mã từ ngôn ngữ hiển thị, tên tệp hoặc kết quả “trông có vẻ đúng”.

### 3.2. Byte UTF-8 bị cắt/hỏng có thể được thay bằng `U+FFFD`

Ví dụ hai byte `C3 28` **không phải UTF-8 hợp lệ**: sau `C3` phải là một continuation byte, nhưng `28` không thỏa điều kiện. Khi dùng `ofString()` trong JDK, quá trình giải mã có thể **thay byte lỗi bằng ký tự `U+FFFD`** để hoàn thành `String`; nó không nhất thiết ném `MalformedInputException` đến caller.

Vì thế các phép kiểm tra sau có ý nghĩa khác nhau:

- `response.statusCode() == 200`: server đã gửi status 200.
- `response.body().contains("\uFFFD")`: chuỗi **có ký tự replacement** — một dấu hiệu đáng kiểm tra; nhưng cũng có thể `U+FFFD` được gửi hợp lệ như một ký tự Unicode thật.
- **Giải mã nghiêm ngặt các byte gốc:** xác nhận bytes có/không tuân thủ charset bằng `CharsetDecoder` cấu hình `CodingErrorAction.REPORT`.

Nếu phải phát hiện **chắc chắn byte UTF-8 không hợp lệ**, đừng chỉ tìm `U+FFFD` sau khi đã giải mã. Hãy nhận `byte[]` và dùng decoder strict:

```java
// Đoạn mã minh họa trong phương thức có throws IOException/InterruptedException.
HttpResponse<byte[]> raw = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray());

String text;
try {
    text = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(raw.body()))
            .toString();
} catch (CharacterCodingException ex) {
    // Lỗi giải mã: phản hồi không phải UTF-8 hợp lệ theo hợp đồng.
    throw new IllegalArgumentException("Invalid UTF-8 response", ex);
}
```

Các import cần thiết gồm `java.nio.ByteBuffer`, `java.nio.charset.StandardCharsets`, `CodingErrorAction` và `CharacterCodingException`. Đoạn mã trên không phải chương trình hoàn chỉnh, nhưng chương trình mục 7 triển khai chính xác cùng quy tắc.

**Không nhầm lỗi network với lỗi charset:** khi kết nối đứt hoặc HTTP bị lỗi trong lúc nhận body, `HttpClient.send` có thể ném `IOException`. Một `CharacterCodingException` sinh ra khi bạn chủ động decode bytes theo charset nghiêm ngặt là lỗi **nội dung**; chúng cần thông báo và cách xử lý khác nhau.

### 3.3. Header charset không hỗ trợ

`BodyHandlers.ofString()` được tài liệu Java 11 quy định dùng UTF-8 khi charset từ `Content-Type` **vắng hoặc không được hỗ trợ**. Điều này hữu ích để có mặc định nhất quán nhưng **không có nghĩa response đã thỏa hợp đồng**.

Nếu API bắt buộc `application/json; charset=UTF-8` mà server trả `charset=not-a-real-charset`, test nên phát hiện sai header/contract chứ không chỉ nhìn chuỗi UTF-8 đã được giải mã. Ngoài charset, cũng kiểm tra **media type** nếu giao thức yêu cầu JSON hoặc định dạng khác.

## 4. Response rỗng: phân biệt status, số byte và quy tắc nghiệp vụ

Một response có body rỗng không nhất thiết là bất thường:

| Tình huống | Ý nghĩa thường gặp | Cần test gì? |
| --- | --- | --- |
| HTTP `204 No Content` | Phản hồi thành công **không có body** theo ngữ nghĩa HTTP. | `statusCode() == 204`, body rỗng; client không cố parse dữ liệu. |
| HTTP `200 OK` với body 0 byte | Kết nối thành công nhưng nội dung rỗng. | Chấp nhận hay báo lỗi tùy **contract endpoint**; không đánh đồng với `204`. |
| HTTP `200` với `""` hợp lệ | Endpoint có thể cho phép chuỗi rỗng. | Kiểm tra điều kiện nghiệp vụ, không tự ép dữ liệu rỗng thành lỗi. |
| HTTP `200` với JSON bắt buộc | 0 byte thường **không** phải một JSON document hợp lệ. | Parse/validate báo thiếu dữ liệu, không coi `""` là object hoặc `null`. |
| HTTP `404` hoặc `422` với error body | Body chứa mô tả lỗi, có thể rỗng hoặc không. | Kiểm tra status và schema của **error payload**, không parse như success payload. |

Với `BodyHandlers.ofString()`, body rỗng bình thường là `""`, nên có thể kiểm tra `response.body().isEmpty()`. Với `BodyHandlers.ofByteArray()`, kiểm tra `response.body().length == 0`. Với `BodyHandlers.discarding()`, body là kiểu `Void` (thường trả `null`), không phải bằng chứng server phát 0 byte vì **caller đã chủ động bỏ body**.

Không dùng `trim().isEmpty()` hoặc `strip().isEmpty()` nếu giao thức phân biệt **0 byte** với chuỗi chứa spaces/newline. Một body `"   "` có ba ký tự dù `strip()` cho chuỗi rỗng.

Đối với `HEAD` và một số status không mang nội dung như `204`, cần áp dụng quy tắc HTTP cụ thể. **`Content-Length: 0` và body thực sự có 0 byte không phải lúc nào cùng mang một ý nghĩa** đối với tất cả phương thức/status. Vì vậy kiểm thử response phải phối hợp status, headers, bytes nhận được và contract.

## 5. Dữ liệu sai cấu trúc: decode thành công chưa đồng nghĩa hợp lệ

Giả sử endpoint trả định dạng văn bản rất đơn giản:

```text
count=42
```

Ứng dụng yêu cầu **chính xác** `count=` theo sau bởi một số nguyên không âm nằm trong giới hạn `int`, không có ký tự thừa. Các response sau không hợp lệ theo contract minh họa:

```text
count=abc
```

```text
count=-1
```

```text
count=999999999999999999999999
```

Đây là **lỗi cấu trúc hoặc giá trị**, không phải lỗi charset: những chuỗi này đều có thể là UTF-8 hoàn toàn hợp lệ. Một parser cho *định dạng minh họa chính xác này* có thể dùng `Pattern` và `Integer.parseInt`:

```java
private static final Pattern COUNT = Pattern.compile("count=([0-9]+)");

static int parseCount(String text) {
    Matcher match = COUNT.matcher(text);
    if (!match.matches()) {
        throw new IllegalArgumentException("Invalid count format");
    }
    try {
        return Integer.parseInt(match.group(1));
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Count out of range", ex);
    }
}
```

Đoạn này cần `java.util.regex.Pattern` và `Matcher`, phải đặt trong một lớp. `matches()` buộc **toàn chuỗi** phù hợp; nhánh `parseInt` từ chối số vượt miền `int`. Nó chỉ là parser của giao thức một trường `count=...`, **không phải JSON parser**.

Với dữ liệu JSON thật, không thay việc parse bằng regex/`contains`/`startsWith("{")`. Hãy dùng thư viện JSON hiện đại được dự án quản lý (ví dụ Jackson hoặc JSON-B) để parse, sau đó validate **schema và nghiệp vụ**:

- JSON cú pháp hỏng: thiếu dấu ngoặc, dấu phẩy thừa, escape sai.
- Đúng cú pháp nhưng sai schema: `{"count":"42"}` khi contract đòi **số**, không phải chuỗi; trường bắt buộc bị thiếu.
- Đúng schema hình thức nhưng giá trị không hợp lệ: số ngoài phạm vi, trạng thái không được hỗ trợ, dữ liệu vô lý.
- Status lỗi trả JSON với schema **error** khác schema **success**.

Ví dụ fixtures minh họa (không phải output của chương trình chạy bên dưới):

```json
{"count":42}
{"count":"not-a-number"}
{"count":
```

Đây là ba mẫu rời: mẫu thứ nhất có thể hợp lệ, mẫu thứ hai sai kiểu theo contract `count` là số, mẫu thứ ba lỗi cú pháp JSON. Test cần khẳng định **đúng loại lỗi** và nội dung lỗi hữu ích, không chỉ khẳng định parser “ném exception nào đó”.

## 6. Phân tầng kiểm tra response một cách có kiểm soát

Một pipeline validation dễ kiểm thử nên giữ trình tự:

1. **Kiểm tra vận chuyển:** `client.send(...)` trả response hay ném `IOException`/`InterruptedException`? Nếu request thất bại trước khi có response, đừng giả lập HTTP `500`.
2. **Kiểm tra status:** nếu mã không thuộc nhóm thành công được endpoint chấp nhận, xử lý như error response. Không tự parse error body bằng success schema.
3. **Kiểm tra Content-Type và charset contract:** nếu yêu cầu văn bản UTF-8, biết rõ charset phải là gì; không mặc định mọi binary body có thể dùng `ofString()`.
4. **Đọc byte hoặc giải mã strict:** khi cần từ chối byte sai, dùng `ofByteArray()` rồi `CharsetDecoder` có `REPORT`; nếu chính sách cho phép replacement, dùng chuỗi với đánh giá phù hợp.
5. **Kiểm tra body rỗng:** áp dụng riêng cho `204`, `200` hoặc endpoint cụ thể; quyết định `""` có hợp lệ không.
6. **Parse đúng định dạng:** JSON/XML/CSV/Protobuf có parser tương ứng; minh họa tại mục 5 chỉ áp dụng giao thức `count=...`.
7. **Validate schema và giá trị:** bắt buộc các trường quan trọng, đúng kiểu, đúng phạm vi, đúng quan hệ.
8. **Chuyển thành kết quả có kiểu:** ứng dụng có thể trả `Success<T>` / `DomainError` hoặc ném ngoại lệ domain có cấu trúc; không dùng chuỗi lỗi mơ hồ làm dữ liệu thành công.

Cách phân tầng giúp unit/integration test chỉ ra **đang sai ở đâu**: HTTP status, encoding, empty body, syntax, schema hay dữ liệu nghiệp vụ.

## 7. Chương trình Java 11 hoàn chỉnh: mô phỏng response qua HTTP server cục bộ

Chương trình sau dùng `com.sun.net.httpserver.HttpServer` trong module JDK `jdk.httpserver` để tạo **server trên loopback** với cổng được hệ điều hành cấp phát. Nó không truy cập Internet hay API bên ngoài. Client gửi request HTTP thật đến các endpoint thử nghiệm, bao gồm:

- Header ISO-8859-1 khớp byte;
- Ép sai charset UTF-8;
- Byte UTF-8 không hợp lệ, giải mã mặc định và giải mã strict;
- Response `204` rỗng và `200` rỗng;
- Payload `count=42` hợp lệ và `count=abc` sai format;
- HTTP `422` có error body.

Lưu thành **`HttpResponseEdgeCasesDemo.java`**:

```java
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
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class HttpResponseEdgeCasesDemo {
    private static final Pattern COUNT = Pattern.compile("count=([0-9]+)");

    static void respond(HttpExchange exchange, int status, String contentType, byte[] bytes)
            throws IOException {
        exchange.getResponseHeaders().set("Content-Type", contentType);
        if (bytes.length == 0 || status == 204) {
            exchange.sendResponseHeaders(status, -1);
            exchange.close();
            return;
        }
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    static HttpRequest get(URI base, String path) {
        return HttpRequest.newBuilder(base.resolve(path)).GET().build();
    }

    static int parseCount(String text) {
        Matcher match = COUNT.matcher(text);
        if (!match.matches()) {
            throw new IllegalArgumentException("Invalid count format");
        }
        try {
            return Integer.parseInt(match.group(1));
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Count out of range", ex);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.createContext("/latin1", exchange -> respond(exchange, 200,
                "text/plain; charset=ISO-8859-1",
                "Caf\u00E9".getBytes(StandardCharsets.ISO_8859_1)));
        server.createContext("/bad-utf8", exchange -> respond(exchange, 200,
                "text/plain; charset=UTF-8",
                new byte[]{(byte) 0xC3, (byte) 0x28}));
        server.createContext("/no-content", exchange -> respond(exchange, 204,
                "text/plain; charset=UTF-8", new byte[0]));
        server.createContext("/ok-empty", exchange -> respond(exchange, 200,
                "text/plain; charset=UTF-8", new byte[0]));
        server.createContext("/valid", exchange -> respond(exchange, 200,
                "text/plain; charset=UTF-8",
                "count=42".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/bad-structure", exchange -> respond(exchange, 200,
                "text/plain; charset=UTF-8",
                "count=abc".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/http-error", exchange -> respond(exchange, 422,
                "text/plain; charset=UTF-8",
                "invalid payload".getBytes(StandardCharsets.UTF_8)));

        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
            HttpClient client = HttpClient.newHttpClient();

            HttpResponse<String> latin1 = client.send(get(base, "/latin1"),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("declared-charset-correct=" +
                    latin1.body().equals("Caf\u00E9"));

            HttpResponse<String> forcedUtf8 = client.send(get(base, "/latin1"),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            System.out.println("wrong-charset-replacement=" +
                    forcedUtf8.body().contains("\uFFFD"));

            HttpResponse<String> defaultDecoded = client.send(get(base, "/bad-utf8"),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("malformed-default-replacement=" +
                    defaultDecoded.body().contains("\uFFFD"));

            HttpResponse<byte[]> raw = client.send(get(base, "/bad-utf8"),
                    HttpResponse.BodyHandlers.ofByteArray());
            try {
                StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(raw.body()));
                System.out.println("strict-utf8=unexpected-success");
            } catch (CharacterCodingException ex) {
                System.out.println("strict-utf8=CharacterCodingException");
            }

            HttpResponse<String> noContent = client.send(get(base, "/no-content"),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("204-empty=" +
                    (noContent.statusCode() == 204 && noContent.body().isEmpty()));

            HttpResponse<String> okEmpty = client.send(get(base, "/ok-empty"),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("200-empty=" +
                    (okEmpty.statusCode() == 200 && okEmpty.body().isEmpty()));

            HttpResponse<String> good = client.send(get(base, "/valid"),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            System.out.println("parsed-count=" + parseCount(good.body()));

            HttpResponse<String> bad = client.send(get(base, "/bad-structure"),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            try {
                parseCount(bad.body());
                System.out.println("bad-structure=unexpected-success");
            } catch (IllegalArgumentException ex) {
                System.out.println("bad-structure=IllegalArgumentException");
            }

            HttpResponse<String> failure = client.send(get(base, "/http-error"),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("http-error-status=" + failure.statusCode());
            System.out.println("http-error-body-nonempty=" + !failure.body().isEmpty());
        } finally {
            server.stop(0);
        }
    }
}
```

Chương trình dùng **module `jdk.httpserver`** để tạo fixture; cần JDK có module này. Biên dịch và chạy:

```bash
javac --release 11 --add-modules jdk.httpserver HttpResponseEdgeCasesDemo.java
java --add-modules jdk.httpserver HttpResponseEdgeCasesDemo
```

**Stdout đã kiểm chứng:**

```text
declared-charset-correct=true
wrong-charset-replacement=true
malformed-default-replacement=true
strict-utf8=CharacterCodingException
204-empty=true
200-empty=true
parsed-count=42
bad-structure=IllegalArgumentException
http-error-status=422
http-error-body-nonempty=true
```

Giải thích:

- Hai dòng đầu so sánh giải mã theo `Content-Type` và cố tình ép charset sai, cho thấy việc nhận HTTP thành công không chứng minh chuỗi đã được giải mã đúng.
- `malformed-default-replacement=true` là biểu hiện của byte `C3 28` sai UTF-8 khi giải mã thành `String`.
- `strict-utf8=CharacterCodingException` là phép xác nhận **byte nguyên bản không hợp lệ**, không dựa vào việc chuỗi có `U+FFFD`.
- `204-empty=true` và `200-empty=true` đều cho body rỗng nhưng mang **status khác nhau**; nghiệp vụ phải quyết định phản hồi 200 rỗng có hợp lệ không.
- `parsed-count=42` và `bad-structure=IllegalArgumentException` xác minh cả trường hợp format hợp lệ và sai cấu trúc sau khi decode.
- `http-error-status=422` và `http-error-body-nonempty=true` chứng minh `BodyHandlers.ofString()` vẫn nhận error body; chỉ đọc `body()` là chưa đủ để biết request thành công.
- Server chỉ nghe trên loopback và `server.stop(0)` trong `finally` giải phóng server sau kiểm thử. Cổng được chọn tự động, tránh hard-code port thường đã có ứng dụng khác sử dụng.

Nếu chạy trong môi trường sandbox chặn socket loopback, chương trình có thể gặp lỗi mở server/kết nối **do môi trường**, không phải do cú pháp Java; khi đó nên tách kiểm thử byte/parser hoặc dùng mock HTTP client được dự án hỗ trợ. Chương trình không kết nối Internet.

## 8. Thiết kế test: khẳng định điều gì và không khẳng định điều gì?

Có thể chia bộ test theo từng tầng:

| Test | Fixture | Assertion nên có |
| --- | --- | --- |
| **Charset đúng** | Byte ISO-8859-1 và header phù hợp | Chuỗi kết quả bằng giá trị mong đợi, không chỉ kiểm tra status 200. |
| **Charset khai báo sai** | Header không đúng byte thực | Phát hiện sai theo hợp đồng format; không tin việc không ném exception. |
| **UTF-8 malformed** | Byte `C3 28` | Decoder strict ném `CharacterCodingException`; lưu byte gốc để phân tích. |
| **UTF-8 rỗng** | Body 0 byte | String rỗng hoặc byte[] dài 0 theo handler; quyết định status cho phép. |
| **`204 No Content`** | Server trả 204 không body | Status 204 và body rỗng; không gọi parser thành công vô điều kiện. |
| **`200` rỗng nhưng bắt buộc payload** | Server trả 200 và 0 byte | Báo lỗi thiếu payload theo nghiệp vụ; không trả object giả. |
| **Sai cấu trúc** | Chuỗi giải mã đúng, `count=abc` | Validator/parser báo sai format/type; không quy thành lỗi charset. |
| **Sai giới hạn dữ liệu** | Chuỗi `count=999999999999999` | Parse số báo giá trị ngoài miền; không cắt bớt mặc định. |
| **HTTP error với body** | `422` và thông điệp lỗi | Client vẫn cung cấp status và body; xử lý theo error contract. |
| **Binary payload bị đọc thành String** | Byte ngẫu nhiên/một file ảnh | Chọn `ofByteArray`; không coi một chuỗi có replacement là dữ liệu chính xác. |

Đối với test thực tế, **assert kết quả/exception cụ thể**, không chỉ in dòng. Ví dụ với JUnit 5, có thể dùng `assertEquals`, `assertThrows`, `assertArrayEquals`. Các ví dụ ở mục 7 dùng `System.out.println` để người học chạy bằng Java 11 nguyên bản, không cần thiết lập dependency. Khi triển khai CI, chuyển kết quả kiểm tra thành assertion để test **thất bại thật sự** khi điều kiện không đúng.

Nếu test dữ liệu JSON, hãy thêm ca thiếu field, field sai kiểu, JSON hỏng cú pháp, `null` JSON (khác body rỗng), object rỗng `{}`, array thay vì object, encoding sai và response có error schema. Đừng dùng một kết quả `isEmpty()` cho tất cả các trường hợp đó.

## 9. Những lưu ý khi dùng `sendAsync` và HTTP lỗi

Khi gọi `HttpClient.sendAsync(...)`, bạn nhận `CompletableFuture<HttpResponse<T>>`. Lỗi network hoặc body subscriber có thể khiến future **hoàn tất ngoại lệ**, còn status HTTP `422` hay `500` vẫn là response bình thường ở mức HTTP:

```java
// Đoạn minh họa, cần client và request.
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

future.thenApply(response -> {
    if (response.statusCode() / 100 != 2) {
        throw new IllegalStateException(
                "HTTP status " + response.statusCode());
    }
    return response.body();
});
```

Cần import `java.util.concurrent.CompletableFuture`. Đoạn trên minh họa **chuyển HTTP status thất bại thành lỗi ứng dụng**, chứ `sendAsync` tự nó **không** làm việc này. Đối với pipeline bất đồng bộ thực tế, cần giữ tham chiếu future kết quả, xử lý completion exception, timeout/cancellation và tránh để exception bị bỏ qua.

Đừng retry vô hạn chỉ vì gặp exception: retry phụ thuộc việc request có idempotent không, liệu server đã nhận body chưa, mã trạng thái, chính sách backoff và hạn mức retry. Lỗi **parse schema** thường không được chữa bằng retry ngay lập tức; cần sửa data contract hoặc đối tác cung cấp.

## 10. Bộ quy tắc lỗi trong ứng dụng production

Một mô hình phân loại dễ giám sát có thể gồm:

- `TRANSPORT_ERROR` — DNS, connection reset, timeout hoặc lỗi nhận body; thường gắn với `IOException`/future failure.
- `HTTP_STATUS_ERROR` — nhận được response nhưng status ngoài chính sách chấp nhận.
- `UNSUPPORTED_MEDIA_TYPE` hoặc `CHARSET_CONTRACT_ERROR` — header/format không đúng hợp đồng.
- `INVALID_ENCODING` — byte không giải mã được theo charset bắt buộc với decoder strict.
- `EMPTY_BODY_ERROR` — body rỗng nhưng endpoint phải có payload.
- `SYNTAX_ERROR` — văn bản giải mã được nhưng định dạng (ví dụ JSON) không parse được.
- `SCHEMA_ERROR` — parse thành công nhưng thiếu field/sai kiểu/sai quan hệ.
- `DOMAIN_VALIDATION_ERROR` — đúng cấu trúc nhưng giá trị không hợp lệ theo nghiệp vụ.

Các nhãn trên chỉ là **đề xuất thiết kế ứng dụng**, không phải tên exception chính thức của Java HttpClient. Mỗi nhóm nên có thông điệp chẩn đoán và dữ liệu quan sát phù hợp, nhưng **không ghi nguyên body chứa token, mật khẩu hay thông tin cá nhân vào log**. Có thể log status, endpoint đã làm sạch, media type, số byte, loại lỗi, trace ID và mẫu dữ liệu đã được kiểm soát, tùy chính sách bảo mật.

Với body rất lớn, `BodyHandlers.ofByteArray()` và `ofString()` có thể giữ toàn bộ trong RAM. Đối với payload không tin cậy hoặc kích thước quá lớn, dùng `BodyHandlers.ofInputStream()` hoặc cách đọc theo luồng khác và thiết lập giới hạn byte/thời gian. Nhớ đóng `InputStream` nếu dùng handler này; `Content-Length` có thể không hiện diện hoặc không đúng thực tế, vì vậy không dùng header như bảo đảm duy nhất về kích thước an toàn.

## 11. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Status 200 nghĩa là body đã giải mã đúng và hợp schema.” | Không: status, encoding và schema cần kiểm tra độc lập. |
| “`ofString()` luôn dùng UTF-8 dù server khai báo charset.” | Không: overload mặc định lấy charset trong `Content-Type` nếu hỗ trợ, rồi mới fallback UTF-8. |
| “`ofString(StandardCharsets.UTF_8)` nghe theo `Content-Type`.” | Không: overload này dùng charset đã chỉ định. |
| “Byte UTF-8 hỏng luôn ném exception từ `client.send(... ofString())`.” | Không chắc: chuỗi có thể chứa `U+FFFD` do replacement. |
| “Chuỗi có `U+FFFD` chắc chắn là byte hỏng.” | Không chắc: ký tự này có thể xuất hiện hợp lệ; decoder `REPORT` mới kiểm chứng byte. |
| “Body rỗng và lỗi mạng cùng là `null`.” | Không: body rỗng có thể là `""`/mảng rỗng; lỗi mạng được báo qua ngoại lệ/future. |
| “`204` và `200` rỗng tương đương hoàn toàn.” | Không: status mang ngữ nghĩa HTTP khác nhau; contract quyết định xử lý. |
| “`BodyHandlers.discarding()` trả `null` nghĩa là server không gửi byte.” | Không: chính client đã bỏ body nên không còn nội dung để xác minh. |
| “Body là chuỗi UTF-8 hợp lệ tức là JSON hợp lệ.” | Không: cần parse cú pháp JSON. |
| “JSON đúng cú pháp nghĩa là mọi trường đúng kiểu và giá trị.” | Không: cần schema + domain validation. |
| “Có thể dùng regex `count` làm JSON parser.” | Không: regex ở mục 5 dành cho giao thức ví dụ một trường, không áp dụng JSON tổng quát. |
| “`HttpClient.send` tự ném exception cho mọi HTTP 4xx/5xx.” | Không: thường nhận `HttpResponse` cùng status và body. |
| “Header `Content-Length` bảo đảm kích thước body tuyệt đối.” | Không: nguồn không tin cậy có thể thiếu/sai header, cần giới hạn byte thực sự. |
| “Test tích hợp cần gọi API production.” | Không: local fixture server với payload xác định trước thường đủ và ít rủi ro hơn. |

## 12. Checklist thực hành

1. **Khẳng định status trước:** xác định endpoint chấp nhận `200`, `201`, `204` hay mã nào; error body có schema riêng.
2. **Chọn body handler đúng:** văn bản thường dùng `ofString`, byte cần chính xác dùng `ofByteArray`, payload lớn dùng streaming.
3. **Xác nhận charset contract:** header `Content-Type` có thể sai; nếu bắt buộc UTF-8, giải mã strict khi cần từ chối byte không hợp lệ.
4. **Phân biệt body rỗng:** `204` hợp lệ theo HTTP; `200` rỗng có thể hợp lệ hoặc là lỗi tùy API. Không coi `""` và JSON `null` tương đương.
5. **Parse bằng parser phù hợp:** JSON cần thư viện JSON, không dùng `contains`/regex để “kiểm chứng” JSON.
6. **Validate schema và nghiệp vụ:** kiểm tra field bắt buộc, type, range, giá trị hợp lệ và error schema.
7. **Test cả positive và negative:** byte charset chuẩn/sai, malformed UTF-8, empty 200/204, invalid syntax/schema và HTTP 4xx có body.
8. **Không rò dữ liệu nhạy cảm trong log:** ghi loại lỗi và metadata có kiểm soát, tránh ghi nguyên payload.
9. **Giới hạn tài nguyên:** với response lớn dùng streaming, kích thước tối đa và timeout; không tin Content-Length làm quota.
10. **Tách mã production và test fixture:** dùng HTTP server cục bộ hoặc mock phù hợp để test ổn định mà không phụ thuộc Internet.

### Tài liệu chính thức và hiện hành

- [Oracle Java SE 11 — `HttpResponse.BodyHandlers`: `ofString`, `ofByteArray`, `discarding` và charset](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Oracle Java SE 25 — `HttpResponse.BodyHandlers`: hợp đồng vẫn được duy trì](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Oracle Java SE 11 — `HttpResponse.BodyHandler` và `ResponseInfo`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html)
- [Oracle Java SE 11 — `CharsetDecoder` và `CodingErrorAction.REPORT`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/CharsetDecoder.html)
- [Oracle Java SE 11 — `HttpClient`: `send` và `sendAsync`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 11 — `HttpServer` dùng cho HTTP fixture cục bộ](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
