# Đọc method, URI, header và request body

## 1. HttpExchange: điểm vào của một request trong HTTP server JDK

Module **jdk.httpserver** của Java 17 cung cấp **HttpServer, HttpContext, HttpHandler, HttpExchange** và **Headers** trong package **com.sun.net.httpserver**. Với một server chạy HTTP/1.1, khi request đến, server chọn HttpContext phù hợp và gọi handler theo giao diện:

~~~java
// Snippet: đã đăng ký một HttpContext.
void handle(HttpExchange exchange) throws IOException {
    String method = exchange.getRequestMethod();
    URI uri = exchange.getRequestURI();
    Headers requestHeaders = exchange.getRequestHeaders();
    InputStream requestBody = exchange.getRequestBody();
    // Kiểm tra request, tạo response rồi đóng exchange.
}
~~~

**HttpExchange** bao trùm một yêu cầu và phản hồi tương ứng. Không nên coi nó là đối tượng session dùng lại cho nhiều request.

Luồng tổng quát:

~~~text
Client gửi HTTP request
       |
       v
HttpServer lắng nghe socket và parse HTTP framing
       |
       v
Chọn HttpContext theo path prefix
       |
       v
HttpHandler.handle(exchange)
       |
       +-- exchange.getRequestMethod()   -> GET/POST/...
       +-- exchange.getRequestURI()      -> URI path, query...
       +-- exchange.getRequestHeaders()  -> Headers (read-only)
       +-- exchange.getRequestBody()     -> InputStream bytes
       |
       v
Validate method, path, query, header, body size, charset
       |
       +-- responseHeaders.set(...)
       +-- sendResponseHeaders(status, byteLength)
       +-- getResponseBody().write(bytes)
       |
       v
Đóng response stream và HttpExchange
~~~

Điểm mấu chốt của bài là **metadata request khác body bytes**: method không nằm trong query, URI không tự là JSON, header Content-Type chỉ mô tả nội dung chứ không tự parse, và InputStream không tự chuyển thành String hay đối tượng Java.

### Một HTTP request minh họa

~~~http
POST /inspect?name=Lan+Anh HTTP/1.1
Host: 127.0.0.1:12345
X-Trace-Id: p-1
Content-Type: text/plain; charset=UTF-8
Content-Length: 15

Xin chào Java!
~~~

Handler sẽ thấy method **POST**, raw query **name=Lan+Anh**, Content-Type chỉ rõ text/plain UTF-8, và **15 bytes UTF-8** trong request body. Do ký tự tiếng Việt chiếm nhiều hơn một byte UTF-8, **số byte không đồng nghĩa String.length()**.

**Phạm vi của JDK HttpServer:** phù hợp học tập, kiểm thử và endpoint có phạm vi kiểm soát; không tự là một framework production cung cấp đầy đủ JSON validation, database pooling, authentication, CSRF, CORS, uploads, DoS protection, TLS reverse proxy và rate limiting.

## 2. Các API và trách nhiệm

| API | Trách nhiệm | Điều cần tránh |
| --- | --- | --- |
| **HttpServer.create(address, backlog)** | Tạo server; có thể bind loopback và port 0 cho test | Không vô tình bind dịch vụ test lên mạng công khai |
| **HttpServer.createContext(path, handler)** | Đăng ký context với path matching theo prefix | Đừng nghĩ đây là exact routing |
| **HttpServer.setExecutor(executor)** | Chọn executor xử lý request callbacks | Không chạy blocking vô hạn trong pool nhỏ |
| **HttpHandler.handle(exchange)** | Phân tích request và gửi response | Phải dọn exchange ngay cả khi lỗi |
| **HttpExchange.getRequestMethod()** | Trả method String | Không tự quy đổi mọi method thành GET |
| **HttpExchange.getRequestURI()** | Trả java.net.URI | Không tự split chuỗi URL khi có percent-encoding |
| **HttpExchange.getRequestHeaders()** | Trả Headers chỉ đọc | Không sửa request header bằng set(...) |
| **HttpExchange.getRequestBody()** | Trả InputStream request payload | Không đọc vô hạn vào RAM |
| **HttpExchange.getResponseHeaders()** | Map có thể chỉnh để thêm response headers | Đặt trước khi sendResponseHeaders |
| **HttpExchange.sendResponseHeaders(...)** | Gửi status và xác định response body framing | Phân biệt length >0, 0 và -1 |
| **HttpExchange.getResponseBody()** | OutputStream của response | Ghi đúng byte count và đóng stream |
| **HttpExchange.close()** | Kết thúc request/response streams | Không bỏ qua cleanup |

**HttpsServer** là biến thể cho HTTPS, được cấu hình cùng SSL/TLS policy; không mặc nhiên có HTTPS khi tạo **HttpServer** plaintext. Nếu cần xác thực người dùng, có API Authenticator/HttpPrincipal nhưng phải chủ động cấu hình; chỉ có Authorization header không có nghĩa người gửi đã được xác minh.

## 3. Đọc method đúng cách

~~~java
String method = exchange.getRequestMethod();

if ("GET".equals(method)) {
    // Xử lý truy vấn đọc.
} else if ("POST".equals(method)) {
    // Xác minh body và thực hiện nghiệp vụ.
} else {
    exchange.getResponseHeaders().set("Allow", "GET, POST");
    // Trả 405 Method Not Allowed cho route này.
}
~~~

HTTP method **phân biệt chữ hoa/thường**. Các method tiêu biểu và contract:

| Method | Mục đích phổ biến | Chú ý |
| --- | --- | --- |
| **GET** | Đọc tài nguyên | Không dùng GET cho hành động có side-effect nguy hiểm; content của GET không có semantics chung được bảo đảm |
| **POST** | Gửi dữ liệu tạo/xử lý | Validate media type, byte length, dữ liệu và quyền |
| **PUT** | Cập nhật/thay resource theo contract | Kiểm tra idempotency và authorization |
| **PATCH** | Cập nhật một phần | Validate patch representation |
| **DELETE** | Xóa resource | Authorization và bảo vệ CSRF tùy cơ chế xác thực |
| **HEAD** | Headers tương ứng GET, không gửi response content | Phải bảo đảm no-response-body |
| **OPTIONS** | Khả năng của route, có thể phục vụ CORS preflight | Không cho phép origin/method tùy ý chỉ vì có OPTIONS |

**405 Method Not Allowed** là status hợp lý khi route tồn tại nhưng không cho phép một method; response nên có **Allow** liệt kê các method của route. **501 Not Implemented** có ý nghĩa khác: chức năng HTTP method không được server hỗ trợ nói chung.

**Có body hay không không được suy ra tuyệt đối chỉ từ method.** Client có thể gửi POST rỗng, GET có body, hoặc gửi POST qua transfer-encoding chunked. Nếu route GET quy định không có body, có thể từ chối GET body theo contract, như chương trình chạy được ở phần 8.

## 4. Phân tích URI: path, raw path, query và encoding

~~~java
URI uri = exchange.getRequestURI();
String rawPath = uri.getRawPath();
String path = uri.getPath();
String rawQuery = uri.getRawQuery();
String decodedQuery = uri.getQuery();
~~~

Ví dụ request target:

~~~text
/inspect?name=Ada%20Lovelace&tag=red&tag=blue
~~~

**getRawPath()** giữ encoding như %2F; **getPath()** diễn giải percent escapes; **getRawQuery()** giữ các ký tự %xx để ứng dụng quyết định cách decode; **getQuery()** đã được Java URI percent-decode, nhưng không đồng nghĩa toàn bộ quy tắc form decoding.

### Query parameters lặp

Trong chuỗi trên, **tag** xuất hiện hai lần. Không nên dùng Map<String,String> nếu muốn giữ cả hai giá trị. Một thiết kế:

~~~java
Map<String, List<String>> query = parseQuery(uri.getRawQuery());
List<String> names = query.getOrDefault("name", List.of());
List<String> tags = query.getOrDefault("tag", List.of());
~~~

Nếu một trường bắt buộc chỉ có một giá trị (như name), nên **reject khi names.size()!=1** thay vì tùy tiện chọn giá trị đầu hoặc cuối. Cũng cần giới hạn độ dài raw query, số lượng keys và độ dài từng value.

### URLDecoder và dấu cộng

**java.net.URLDecoder** là decoder cho **application/x-www-form-urlencoded**. Trong format này, dấu **+** mang nghĩa dấu cách, **%2B** là dấu cộng thật:

~~~java
String a = URLDecoder.decode(
        "Lan+Anh", StandardCharsets.UTF_8); // "Lan Anh"
String b = URLDecoder.decode(
        "C%2B%2B", StandardCharsets.UTF_8); // "C++"
~~~

**Một URI query bất kỳ không mặc định có nghĩa form-urlencoded**, và URI.getQuery() không tự thay dấu + thành dấu cách. Chỉ áp **URLDecoder** khi API contract dùng form-query semantics. **Đừng percent-decode hai lần:** ví dụ %252F có thể bị biến thành dấu / nếu code decode lặp, gây path/query confusion.

### HttpContext là longest-prefix routing

Theo Javadoc **HttpServer**, request chọn context dựa trên **longest matching literal path prefix**, so sánh phân biệt chữ hoa/thường. Nếu đăng ký:

~~~java
server.createContext("/inspect", handler);
~~~

request **/inspect-other** vẫn có thể đi đến handler vì prefix **/inspect** trùng. Nếu route chỉ nhận chính xác **/inspect**, phải kiểm tra:

~~~java
if (!"/inspect".equals(exchange.getRequestURI().getRawPath())) {
    // Trả 404 Not Found.
}
~~~

Tránh tự biến path prefix thành phân quyền. Với path variables và encoded slash, chọn router và normalization có quy tắc rõ; kiểm thử **/users**, **/users-admin**, **/users/42**, **/Users**, %2F và double encoding. Không cho client làm thay đổi đường dẫn dữ liệu bằng chuỗi ../ chưa được validate.

### Query và body hoàn toàn có thể cùng tồn tại

Request **POST /inspect?name=Lan+Anh** có name trong URI và một body riêng. Không tự gộp query và body thành cùng map nếu có khả năng trùng key; contract phải quy định nguồn nào có thẩm quyền cho từng trường, nhất là các trường user ID, role, token hoặc resource identifier.

## 5. Headers: case-insensitive, đa trị, read-only

~~~java
Headers headers = exchange.getRequestHeaders();
String trace = headers.getFirst("x-trace-id");
String contentType = headers.getFirst("Content-Type");
List<String> tags = headers.get("X-Tag");
~~~

**Headers** là **Map<String,List<String>>**, key **case-insensitive**. **X-Trace-Id**, **x-trace-id** và **X-TRACE-ID** là một header name theo semantics HTTP. Nếu một header được gửi nhiều lần, danh sách có thể có nhiều phần tử.

| Lời gọi | Kết quả |
| --- | --- |
| **getFirst("Content-Type")** | Giá trị đầu nếu có, hoặc null |
| **get("Accept")** | Danh sách các values nếu có |
| **getRequestHeaders()** | Request metadata dạng map chỉ đọc |
| **getResponseHeaders()** | Response headers map mutable để đặt trước khi gửi |
| **Headers.set(name,value)** | Ghi một giá trị duy nhất, thay thế các values cũ ở response |
| **Headers.add(name,value)** | Thêm giá trị cho response header |

**Không gọi set(...) trên getRequestHeaders()**: Javadoc định nghĩa nó là read-only. Muốn set **Content-Type** của response, gọi **getResponseHeaders().set(...)**.

### Khi nào getFirst chưa đủ?

Với những header liên quan **authentication, message framing, routing và chữ ký request**, nhiều giá trị trùng hoặc không nhất quán cần policy rõ. Chỉ lấy getFirst rồi bỏ những giá trị còn lại có thể tạo ambiguity khi reverse proxy và backend diễn giải khác nhau. Cần kiểm tra toàn bộ danh sách hoặc để HTTP parser/gateway từ chối request không hợp lệ.

**Không tự split mọi header bằng dấu phẩy**: grammar của Cookie, Set-Cookie, Authorization, Accept hay Cache-Control khác nhau. Chỉ parse đúng grammar của từng header.

### Content-Type, Accept, Content-Length, Transfer-Encoding

- **Content-Type**: media type của request body, ví dụ text/plain; charset=UTF-8 hoặc application/json.
- **Accept**: định dạng response mà client muốn nhận, không tự là Content-Type request.
- **Content-Length**: thông tin framing/body length tính theo **bytes**, không phải Java char.
- **Transfer-Encoding: chunked**: truyền body HTTP/1.1 thành các chunks; handler nhận body payload qua InputStream, không tự đọc chunk markers.
- **Content-Encoding: gzip**: encoding của representation; nếu app hỗ trợ giải nén, phải giới hạn cả kích thước **sau giải nén**.

**Mọi request header là dữ liệu do đối tác gửi, không phải bằng chứng an toàn.** Header **X-Trace-Id** trong ví dụ chỉ được chấp nhận khi khớp **[A-Za-z0-9-]{1,32}**, để tránh phản chiếu ký tự điều khiển. Nó không thay authentication. Với Authorization/Cookie, tuyệt đối không ghi log nguyên token/phiên.

### Content-Type phải được kiểm tra trước khi parse

Nếu endpoint chỉ nhận **text/plain; charset=UTF-8**, server có thể trả **415 Unsupported Media Type** cho POST application/json. Trong demo, so sánh **chuỗi Content-Type exact (không phân biệt case)** để code gọn và có test xác định. Đây là **format rất hẹp của bài lab**, không phải một MIME parser tổng quát; service thực tế nên parse media type/parameters chuẩn hóa và quyết định những charset nào được hỗ trợ.

## 6. Request body: một InputStream, cần byte cap và charset

~~~java
InputStream body = exchange.getRequestBody();
~~~

Theo Javadoc **HttpExchange**, nhiều lần gọi **getRequestBody()** trả **cùng một InputStream**; các bytes đã tiêu thụ không tự quay lại. Ví dụ:

~~~java
byte[] one = exchange.getRequestBody().readAllBytes();
byte[] two = exchange.getRequestBody().readAllBytes();
// two thường là 0 bytes vì stream đã bị đọc đến EOF.
~~~

Đoạn trên là minh họa về trạng thái stream, **không phải mẫu xử lý body từ client không tin cậy**: **readAllBytes() không giới hạn** có thể gây OOM khi client gửi payload lớn.

### Giới hạn bytes thực tế

Trong ví dụ, **MAX_BODY = 32** byte để kiểm thử; handler đọc tối đa 33 byte rồi trả **413** nếu quá giới hạn:

~~~java
static byte[] readLimited(InputStream input, int max)
        throws IOException {
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    byte[] block = new byte[16];

    while (out.size() <= max) {
        int allowed = Math.min(
                block.length, max + 1 - out.size());
        int n = input.read(block, 0, allowed);
        if (n == -1) return out.toByteArray();
        if (n == 0) continue;
        out.write(block, 0, n);
    }
    return null; // Body quá max.
}
~~~

**Không tin Content-Length là giới hạn duy nhất**: request có thể dùng chunked và không khai báo Content-Length. Phải **đếm bytes thực sự đọc được**. Nếu Content-Length đã được gateway/server validate và quá quota, có thể từ chối sớm, nhưng vẫn cần streaming cap và **timeout**.

**Byte cap không chống slow client**: một client gửi từng byte rất chậm vẫn giữ handler chờ. Với hệ thống công khai, cần giới hạn thời gian đọc, số kết nối, concurrency, rate limit và chính sách từ chối ở edge/gateway.

### UTF-8 có nhiều byte cho một ký tự

Body ví dụ **Xin chào Java!** có **15 bytes UTF-8**. Không tính Content-Length bằng String.length() hoặc số Unicode code point. Khi phải decode UTF-8 nghiêm ngặt, dùng:

~~~java
String text = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(bytes)).toString();
~~~

Nếu bytes UTF-8 lỗi, có thể trả **400 Bad Request**. **new String(bytes, UTF_8)** có thể thay dữ liệu không hợp lệ bằng replacement character, không phải lúc nào thích hợp cho protocol đòi hỏi strict validation. Không dùng charset mặc định của host.

### Body có thể là chunked

Với HTTP/1.1, client có thể stream request body mà không biết trước độ dài. Trong test:

~~~java
HttpRequest.BodyPublishers.ofInputStream(
        () -> new ByteArrayInputStream(
                "Hi".getBytes(StandardCharsets.UTF_8)))
~~~

Publisher của HttpClient không biết trước độ dài có thể sử dụng chunked transfer encoding trên HTTP/1.1. **HttpServer đã xử lý framing**, getRequestBody() cho handler đọc đúng bytes **Hi**. Handler **không tự parse Transfer-Encoding chunk sizes**, nhưng vẫn phải giới hạn bytes, charset và xác minh Content-Type như với fixed-length body.

### Trường hợp body không hợp lệ

| Lỗi | Hướng xử lý |
| --- | --- |
| **Body vượt quota** | 413, dọn exchange/connection theo policy |
| **Content-Type không hỗ trợ** | 415, không tự parse như kiểu được hỗ trợ |
| **UTF-8 malformed** | 400 theo contract strict |
| **JSON sai schema** | 400 hoặc status nghiệp vụ thích hợp; parser JSON cần được cấu hình riêng |
| **Client ngắt kết nối khi đang đọc** | IOException, dọn resources, không gửi response thành công giả |
| **Gzip quá lớn sau giải nén** | Chặn bằng decompression limit, không chỉ compressed length |
| **Content-Length/Transfer-Encoding mơ hồ** | Để HTTP parser/edge áp quy tắc framing thống nhất, tránh request smuggling |

## 7. Gửi response và đóng HttpExchange đúng vòng đời

Trình tự chuẩn theo Javadoc:

1. Đọc **getRequestMethod**, **getRequestURI**, **getRequestHeaders**.
2. Đọc **getRequestBody** khi contract cần; xử lý body bằng parser có giới hạn.
3. Đặt **getResponseHeaders().set(...)** trước khi gửi.
4. Gọi **sendResponseHeaders(status, responseLength)**.
5. Gọi **getResponseBody()**, ghi response bytes nếu có.
6. Đóng response OutputStream và **HttpExchange**.

**sendResponseHeaders** có ba quy tắc đặc thù của JDK17:

| responseLength | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| **> 0** | Có đúng từng ấy **bytes** trong body | Ghi đúng số bytes đã khai báo |
| **0** | Dùng **chunked transfer encoding** cho response body | Ghi bao nhiêu tùy ý rồi đóng stream |
| **-1** | **Không có response body** | Với 204, 304 hoặc nhánh no-body theo contract |

**Đừng xem 0 là cách viết Content-Length: 0**. Trong API **HttpExchange**, 0 chọn chunked encoding. Đối với payload có nội dung, tính chiều dài từ **byte[]**:

~~~java
byte[] bytes = responseText.getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(200, bytes.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(bytes);
}
~~~

Ghi **ít hoặc nhiều bytes** hơn responseLength cố định có thể gây IOException và abort exchange. Vì vậy không dùng String.length() để xác định fixed-length HTTP response có Unicode.

### Close streams và exchange

**HttpExchange implements AutoCloseable**. Code Java17 có thể dùng:

~~~java
static void handle(HttpExchange exchange) throws IOException {
    try (exchange) {
        // Request -> response -> đóng streams/exchange.
    }
}
~~~

Khi đóng exchange, JDK đóng request InputStream và response OutputStream theo lifecycle. Nếu input chưa đọc hết, implementation có thể drain/bỏ một lượng byte còn lại để thử reuse TCP; nếu không được thì connection có thể bị đóng. **Không giả định exchange.close sẽ drain vô hạn mà không tốn tài nguyên**. Khi từ chối body lớn, cần có body cap, timeout và connection-close policy.

**Quên close** có thể khiến client chờ, resource không được giải phóng hoặc connection không reuse đúng. Khi một handler ném exception trước khi response gửi, không nên cố gửi 500 nếu headers đã commit; cần log và đóng exchange, tránh double-response.

## 8. Ví dụ hoàn chỉnh Java 17: GET/POST, URI, headers, body và lỗi

**JdkHttpRequestDemo.java** tạo một HttpServer trên **127.0.0.1**, port do hệ điều hành chọn, rồi tạo HttpClient Java17 để thực hiện test trực tiếp trong cùng JVM. Không cần Internet, Maven, JSON framework hay chứng chỉ HTTPS.

Chức năng của handler:

- Đọc method, raw path, raw query và Headers.
- Chỉ chấp nhận đường dẫn chính xác **/inspect** dù HttpContext prefix rộng hơn.
- Chỉ cho GET/POST, trả **405 + Allow** với method khác.
- Kiểm tra header **X-Trace-Id** dạng chữ/số/dấu gạch, không quá 32 ký tự.
- Giải mã query form-style; **name** phải đúng một lần, **tag** có thể lặp (tối đa bốn).
- POST chỉ nhận **text/plain; charset=UTF-8**.
- Đọc tối đa 32 bytes thực tế, trả 413 nếu vượt giới hạn.
- POST decode UTF-8 nghiêm ngặt, trả 400 nếu byte sequence không hợp lệ.
- Đặt response headers, gửi byte length chính xác, dọn exchange.

Bảy test lần lượt: GET query có tag lặp; POST text Unicode; POST streaming unknown-length (chunked trên HTTP/1.1); sai Content-Type 415; body quá dài 413; PUT 405; path prefix nhưng không exact 404. Không xử lý client authentication trong demo; nếu dùng thực tế phải bổ sung bảo vệ riêng.

### Tệp JdkHttpRequestDemo.java

~~~java
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLDecoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class JdkHttpRequestDemo {
    static final int MAX_BODY = 32;

    static Map<String, List<String>> parseQuery(String raw) {
        Map<String, List<String>> parameters = new LinkedHashMap<>();
        if (raw == null || raw.isEmpty()) return parameters;
        if (raw.length() > 256)
            throw new IllegalArgumentException("Query too long");

        for (String part : raw.split("&", -1)) {
            int i = part.indexOf('=');
            String key = URLDecoder.decode(
                    i < 0 ? part : part.substring(0, i),
                    StandardCharsets.UTF_8);
            String value = URLDecoder.decode(
                    i < 0 ? "" : part.substring(i + 1),
                    StandardCharsets.UTF_8);
            parameters.computeIfAbsent(
                    key, unused -> new ArrayList<>()).add(value);
        }
        return parameters;
    }

    static byte[] readLimited(InputStream input, int max)
            throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] block = new byte[16];

        while (out.size() <= max) {
            int allowed = Math.min(
                    block.length, max + 1 - out.size());
            int n = input.read(block, 0, allowed);
            if (n == -1) return out.toByteArray();
            if (n == 0) continue;
            out.write(block, 0, n);
        }
        return null;
    }

    static void respond(HttpExchange exchange, int code, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.getResponseHeaders().set(
                "Cache-Control", "no-store");
        exchange.sendResponseHeaders(code, bytes.length);

        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    static void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            String method = exchange.getRequestMethod();
            URI uri = exchange.getRequestURI();
            Headers headers = exchange.getRequestHeaders();

            if (!"/inspect".equals(uri.getRawPath())) {
                respond(exchange, 404, "Not Found");
                return;
            }

            if (!"GET".equals(method) && !"POST".equals(method)) {
                exchange.getResponseHeaders().set(
                        "Allow", "GET, POST");
                respond(exchange, 405, "Method Not Allowed");
                return;
            }

            String trace = headers.getFirst("x-trace-id");
            if (trace == null ||
                    !trace.matches("[A-Za-z0-9-]{1,32}")) {
                respond(exchange, 400, "Invalid X-Trace-Id");
                return;
            }

            Map<String, List<String>> query;
            try {
                query = parseQuery(uri.getRawQuery());
            } catch (IllegalArgumentException invalidQuery) {
                respond(exchange, 400, "Invalid query");
                return;
            }

            List<String> names =
                    query.getOrDefault("name", List.of());
            List<String> tags =
                    query.getOrDefault("tag", List.of());

            if (names.size() != 1 ||
                    !names.get(0).matches("[A-Za-z ]{1,40}") ||
                    tags.size() > 4 ||
                    tags.stream().anyMatch(
                            t -> !t.matches("[a-z]{1,10}"))) {
                respond(exchange, 400, "Invalid parameters");
                return;
            }

            if ("POST".equals(method)) {
                String type = headers.getFirst("Content-Type");
                if (!"text/plain; charset=UTF-8".equalsIgnoreCase(
                        type == null ? "" : type.trim())) {
                    respond(exchange, 415,
                            "Unsupported Content-Type");
                    return;
                }
            }

            byte[] bytes = readLimited(
                    exchange.getRequestBody(), MAX_BODY);

            if (bytes == null) {
                exchange.getResponseHeaders().set(
                        "Connection", "close");
                respond(exchange, 413, "Request body too large");
                return;
            }

            if ("GET".equals(method) && bytes.length != 0) {
                respond(exchange, 400, "GET body not supported");
                return;
            }

            String bodyText = "";
            if ("POST".equals(method)) {
                try {
                    bodyText = StandardCharsets.UTF_8.newDecoder()
                            .onMalformedInput(
                                    CodingErrorAction.REPORT)
                            .onUnmappableCharacter(
                                    CodingErrorAction.REPORT)
                            .decode(ByteBuffer.wrap(bytes))
                            .toString();
                } catch (CharacterCodingException invalid) {
                    respond(exchange, 400, "Invalid UTF-8 body");
                    return;
                }
            }

            String message = method +
                    " name=" + names.get(0) +
                    " tags=" + String.join(",", tags) +
                    " trace=" + trace +
                    " bytes=" + bytes.length;
            if ("POST".equals(method)) {
                message += " text=" + bodyText;
            }

            respond(exchange, 200, message);
        }
    }

    static HttpResponse<String> request(
            HttpClient client, URI base, String path,
            String method, HttpRequest.BodyPublisher body,
            String trace, String contentType) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(
                URI.create(base.toString() + path))
                .timeout(Duration.ofSeconds(5));

        if (trace != null) request.header("X-Trace-Id", trace);
        if (contentType != null)
            request.header("Content-Type", contentType);
        request.method(method, body);

        return client.send(
                request.build(),
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    static void expect(
            String label, HttpResponse<String> actual,
            int expectedCode, String expectedBody) {
        if (actual.statusCode() != expectedCode ||
                !expectedBody.equals(actual.body())) {
            throw new AssertionError(
                    label + ": expected " +
                    expectedCode + "/" + expectedBody +
                    ", actual " +
                    actual.statusCode() + "/" + actual.body());
        }
        System.out.println(
                label + " status=" + expectedCode +
                " body=" + expectedBody);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService workers =
                Executors.newFixedThreadPool(3);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext(
                "/inspect", JdkHttpRequestDemo::handle);
        server.setExecutor(workers);

        try {
            server.start();
            URI base = URI.create(
                    "http://127.0.0.1:" +
                    server.getAddress().getPort());

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            expect("GET", request(client, base,
                    "/inspect?name=Ada%20Lovelace&tag=red&tag=blue",
                    "GET",
                    HttpRequest.BodyPublishers.noBody(),
                    "g-1", null),
                    200, "GET name=Ada Lovelace " +
                            "tags=red,blue trace=g-1 bytes=0");

            byte[] vietnamese = "Xin chào Java!".getBytes(
                    StandardCharsets.UTF_8);

            expect("POST", request(client, base,
                    "/inspect?name=Lan+Anh",
                    "POST",
                    HttpRequest.BodyPublishers.ofByteArray(
                            vietnamese),
                    "p-1", "text/plain; charset=UTF-8"),
                    200, "POST name=Lan Anh " +
                            "tags= trace=p-1 bytes=" +
                            vietnamese.length +
                            " text=Xin chào Java!");

            expect("CHUNKED", request(client, base,
                    "/inspect?name=Kim",
                    "POST",
                    HttpRequest.BodyPublishers.ofInputStream(
                            () -> new ByteArrayInputStream(
                                    "Hi".getBytes(
                                            StandardCharsets.UTF_8))),
                    "c-1", "text/plain; charset=UTF-8"),
                    200, "POST name=Kim tags= " +
                            "trace=c-1 bytes=2 text=Hi");

            expect("BAD_TYPE", request(client, base,
                    "/inspect?name=Kim",
                    "POST",
                    HttpRequest.BodyPublishers.ofString("{}"),
                    "m-1", "application/json"),
                    415, "Unsupported Content-Type");

            expect("TOO_LARGE", request(client, base,
                    "/inspect?name=Kim",
                    "POST",
                    HttpRequest.BodyPublishers.ofString(
                            "0123456789012345678901234567890123456789"),
                    "l-1", "text/plain; charset=UTF-8"),
                    413, "Request body too large");

            HttpResponse<String> unsupported = request(
                    client, base, "/inspect?name=Kim",
                    "PUT",
                    HttpRequest.BodyPublishers.noBody(),
                    "u-1", null);

            expect("BAD_METHOD", unsupported,
                    405, "Method Not Allowed");
            String allow = unsupported.headers()
                    .firstValue("Allow").orElse("");
            if (!"GET, POST".equals(allow)) {
                throw new AssertionError(
                        "Invalid Allow header: " + allow);
            }
            System.out.println("Allow: " + allow);

            expect("BAD_PATH", request(client, base,
                    "/inspect-other?name=Kim",
                    "GET",
                    HttpRequest.BodyPublishers.noBody(),
                    "n-1", null),
                    404, "Not Found");
        } finally {
            server.stop(0);
            workers.shutdown();
            if (!workers.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                workers.shutdownNow();
                if (!workers.awaitTermination(
                        5, TimeUnit.SECONDS)) {
                    throw new AssertionError(
                            "Workers did not terminate");
                }
            }
        }

        if (!workers.isTerminated()) {
            throw new AssertionError(
                    "Executor not terminated");
        }
        System.out.println("Executor terminated: true");
    }
}
~~~

### Biên dịch và chạy

Lưu file **JdkHttpRequestDemo.java**, dùng **JDK 17 trở lên**:

~~~bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 JdkHttpRequestDemo.java
java --add-modules jdk.httpserver JdkHttpRequestDemo
~~~

**Stdout đã kiểm thử thành công trên JVM bằng Java 17-compatible source:**

~~~text
GET status=200 body=GET name=Ada Lovelace tags=red,blue trace=g-1 bytes=0
POST status=200 body=POST name=Lan Anh tags= trace=p-1 bytes=15 text=Xin chào Java!
CHUNKED status=200 body=POST name=Kim tags= trace=c-1 bytes=2 text=Hi
BAD_TYPE status=415 body=Unsupported Content-Type
TOO_LARGE status=413 body=Request body too large
BAD_METHOD status=405 body=Method Not Allowed
Allow: GET, POST
BAD_PATH status=404 body=Not Found
Executor terminated: true
~~~

**Vì sao kết quả đáng tin?** Test không dùng Internet, chỉ giao tiếp qua **127.0.0.1** và port 0 do hệ điều hành cấp. Mỗi response được assert **status code và body string trước khi in**, nên không in PASS giả chỉ vì server đã trả nội dung nào đó. Cuối test, server.stop(0), pool.shutdown/awaitTermination và isTerminated xác nhận executor đã kết thúc.

**Giới hạn:** Source được đơn giản hóa để dạy HttpExchange, không có authentication, uploads, JSON schema, file streaming hay TLS. Giới hạn 32 byte và quy tắc name ASCII chỉ dùng trong test; dịch vụ thật cần byte quota, charset/name validation, timeout, memory policy và concurrency chính xác theo nghiệp vụ. Nếu cần HTTPS, dùng **HttpsServer** với certificate/trust policy hoặc reverse proxy có quản trị; không coi local HTTP test đã chứng minh server bảo mật khi chạy công khai.

### 8.1. Diễn giải lần lượt 9 dòng stdout

| Dòng | Ý nghĩa được kiểm tra |
| --- | --- |
| **GET status=200** | GET đọc URI raw query name=Ada%20Lovelace, tag lặp; case-insensitive X-Trace-Id; không có body |
| **POST status=200** | POST nhận UTF-8 text/plain, decode strict, báo đúng **15 bytes** của Xin chào Java! |
| **CHUNKED status=200** | Request body unknown-length vẫn được đọc từ InputStream thành **Hi** |
| **BAD_TYPE status=415** | Media type không được endpoint hỗ trợ |
| **TOO_LARGE status=413** | Request vượt 32 bytes bị từ chối khi đọc đến byte thứ 33 |
| **BAD_METHOD status=405** | PUT không phải GET/POST, route trả Method Not Allowed |
| **Allow: GET, POST** | Header Allow đi cùng 405 được test riêng |
| **BAD_PATH status=404** | /inspect-other không bị coi là /inspect dù context prefix match |
| **Executor terminated: true** | Server worker pool được dọn sau test |

### Ghi chú về early rejection

Khi handler từ chối request **trước khi đọc hết body** (ví dụ content type sai hoặc body quá lớn), HttpExchange.close() có thể khiến JDK cố **drain một phần unread bytes**. Không suy ra connection chắc chắn sẽ reuse hoặc server chắc chắn không tốn thêm I/O. Trong tình huống body quá lớn, demo đặt Connection: close và trả 413; với môi trường thực tế phải dùng edge limits và timeout để chống Slowloris/DoS.

## 9. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| **Tưởng method là enum** | Mapping sai hoặc ép kiểu không hợp lệ | getRequestMethod trả String, so sánh rõ |
| **Tưởng Context path là exact-match** | /inspect-other đi vào handler /inspect | Kiểm tra rawPath chính xác |
| **Dùng getQuery rồi URLDecoder lần nữa** | Double decode, có thể bị bypass path/query | Decode raw components đúng một lần |
| **Làm mất query param lặp** | Thông tin bị ghi đè | Map<String,List<String>> |
| **Chỉ dùng getFirst cho header nhạy cảm** | Bỏ qua các value mâu thuẫn | Kiểm tra full list hoặc từ chối duplicate |
| **Gọi set trên request Headers** | Read-only, runtime error | Chỉ sửa response Headers |
| **Xem Content-Type là parser** | Giải mã sai/parse body sai | Kiểm tra media type rồi parse bằng thư viện phù hợp |
| **Dùng readAllBytes vô hạn** | OOM/DoS | Body cap streaming + timeout |
| **Tin Content-Length luôn hiện diện** | Bỏ sót chunked transfer | Đếm số bytes thực sự đọc |
| **Tính Content-Length bằng String.length()** | Sai với UTF-8 Unicode | Dùng byte[].length |
| **Không phân biệt 0 và -1 ở InputStream.read** | Vòng lặp sai/đọc thiếu dữ liệu | -1 mới là EOF |
| **Bỏ qua malformed charset** | Data corruption hoặc parser confusion | CharsetDecoder.REPORT nếu strict |
| **Trả 200 khi Content-Type không hỗ trợ** | Parser lỗi/nghiệp vụ không rõ | 415 |
| **Trả 200 với PUT sai route** | Không đúng contract | 405 + Allow |
| **Dùng sendResponseHeaders(code,0) để no-body** | JDK dùng response chunked | -1 cho no-body |
| **Không đóng OutputStream/exchange** | Client chờ, tài nguyên không được giải phóng | try-with-resources/finally |
| **Ghi thiếu bytes khi fixed response length** | IOException/abort exchange | Ghi đúng byte count |
| **Đọc/đổ toàn body vào logs** | Lộ token/PII | Redact, giới hạn metadata |
| **Cho client tự nhận vai trò qua X-Forwarded headers** | Spoof danh tính/network route | Chỉ trust proxy được quản trị |
| **Chỉ giới hạn bytes nhưng không giới hạn thời gian** | Worker bị giữ bởi slow client | Request timeout, limits ở ingress/server |
| **Dùng ThreadPool không kiểm soát tải** | Starvation/memory pressure | Bounded queue và concurrency policy |

## 10. Bảo mật và vận hành

### 10.1. Input từ HTTP client luôn là untrusted

- **Method:** chỉ nhận những method route hỗ trợ.
- **URI/path:** kiểm tra path segments, encoding, query length và normalization; tránh **../**, encoded-slash và double decoding mơ hồ.
- **Query:** validate key, value, duplicates, số lượng và độ dài; không tin role hoặc ID lấy thẳng từ query.
- **Headers:** giới hạn số lượng/kích thước, phát hiện duplicate headers nhạy cảm và không log secrets.
- **Body:** giới hạn byte count, thời gian nhận, media type, charset, parser depth, size sau giải nén.
- **Response:** escape/encode theo content type, không đưa untrusted CRLF vào header, chọn status phù hợp.

**getRemoteAddress() chỉ là địa chỉ peer mạng mà HttpServer thấy**, có thể là reverse proxy thay vì end-user. Forwarded/X-Forwarded-For là dữ liệu cần xác thực từ proxy tin cậy, không tin từ request bất kỳ.

### 10.2. Request smuggling, Content-Length và Transfer-Encoding

Khi một HTTP request đi qua **reverse proxy/gateway và backend**, nếu hai phía diễn giải framing khác nhau (đặc biệt các trường **Content-Length** và **Transfer-Encoding** xung đột), có thể có **HTTP request smuggling/desynchronization**. Không cố “sửa” bằng cách tự parse raw HTTP frames từ **getRequestBody()**; HttpServer đã xử lý framing trước khi tạo InputStream.

Giải pháp cần thống nhất rule tại các thành phần, reject request malformed/ambiguous, cập nhật server/gateway, giới hạn connection reuse khi phù hợp và kiểm thử proxy/backend cùng nhau. JDK HttpServer là HTTP server gọn nhẹ, không thay một ingress được cấu hình/hardening đầy đủ cho workload untrusted.

### 10.3. Chậm mà nhỏ vẫn nguy hiểm

Body cap 32 bytes không giúp chống client gửi từng byte mỗi phút. Với server công khai, nên có:

- Connection limits và giới hạn số request đồng thời.
- Giới hạn số header fields, header bytes, URI length và payload bytes.
- Request receive timeout/idle timeout có chính sách rõ.
- ThreadPoolExecutor với bounded queue và overload policy.
- TLS/HTTPS, auth, audit, logging redaction, rate limiting.
- Reverse proxy/gateway bảo vệ HTTP parser và các request không hợp lệ.

JDK có các **implementation-specific system properties** cho HttpServer ở một số phiên bản như **sun.net.httpserver.maxReqHeaders**, **sun.net.httpserver.maxReqHeaderSize**, **sun.net.httpserver.maxReqTime**, **sun.net.httpserver.drainAmount** và **jdk.httpserver.maxConnections**. **Không hardcode giá trị mặc định** mà chưa xem tài liệu tương ứng JDK vendor/patch. Những property đó không thay hoàn toàn edge/server application-level size/time budget.

### 10.4. Request authorization và session

Headers **Authorization** hoặc **Cookie** là dữ liệu do client gửi, không phải bằng chứng đã xác thực. Nếu dùng HttpContext Authenticator, **getPrincipal()** có thể trả principal phù hợp sau khi auth; nếu không có Authenticator thì không được giả định principal đã có. Với cookie-based authentication, còn cần CSRF defense, session expiration/revocation và authorization ở từng route.

### 10.5. Executor lifecycle

Demo gọi **setExecutor(Executors.newFixedThreadPool(3))** để kiểm thử ngắn. Trong Java 17, newFixedThreadPool có queue không giới hạn mặc định, nên không dùng nguyên cấu hình đó cho endpoint công khai có thể nhận rất nhiều request. Trong production, cần quản lý threads, queue, shutdown và xử lý overload.

Đóng HttpExchange và shutdown executor là hai hành động khác nhau: close exchange dọn response/request một request; server.stop và executor.shutdown quản lý vòng đời dịch vụ.

## 11. Bài tập và ma trận kiểm thử

| Test | Request | Expected |
| --- | --- | --- |
| **GET hợp lệ** | /inspect?name=Ada%20Lovelace&tag=red&tag=blue, X-Trace-Id g-1 | 200, giữ tag lặp, zero body |
| **POST UTF-8** | name=Lan+Anh, text/plain UTF-8, body Xin chào Java! | 200, 15 bytes, decode đúng dấu |
| **POST streaming/chunked** | BodyPublisher.ofInputStream với bytes Hi | 200, đọc 2 bytes từ InputStream |
| **Media type sai** | POST Content-Type application/json | 415 |
| **Body quá dài** | POST 40 bytes khi MAX_BODY=32 | 413 |
| **Method không được phép** | PUT /inspect | 405 + Allow GET, POST |
| **Path prefix không exact** | GET /inspect-other | 404 |
| **Header thiếu/không hợp lệ** | X-Trace-Id có ký tự điều khiển hoặc vắng mặt | 400 hoặc HTTP parser reject trước |
| **Query key name lặp** | name=Ada&name=Lan | 400 |
| **Query encoded** | name=Lan+Anh, name=C%2B%2B | Decode một lần, validation theo contract |
| **Invalid UTF-8** | POST body có byte sequence lỗi | 400 |
| **No response body** | Route trả 204 | sendResponseHeaders(204,-1), không ghi body |
| **Header name case** | x-trace-id/X-TRACE-ID | Đọc cùng field |
| **Slow client** | Gửi body từng byte trong thời gian dài | Request timeout/ingress limit, không giữ worker vô hạn |
| **Duplicate framing** | CL/TE mâu thuẫn qua proxy | Rejection theo policy nhất quán, không parser confusion |

Đối với test extension, đừng thử những request có hình thức tấn công hoặc gửi payload quá lớn vào hệ thống bên thứ ba không được phép kiểm thử. Dùng local lab/fixture do bạn kiểm soát.

## 12. Câu hỏi tự kiểm tra

**1. getRequestMethod trả gì?**  
Trả String ví dụ GET, POST. Handler tự quyết định method được cho phép.

**2. Vì sao getRequestURI không nên chỉ chuyển thành String rồi split bằng dấu hỏi?**  
Vì URI có raw/decoded components, percent-encoding và query grammar cần parse chính xác.

**3. URI.getRawQuery và URI.getQuery có giống nhau?**  
Không. Raw giữ escapes; decoded query đã percent-decode theo URI semantics.

**4. Vì sao URLDecoder biến Lan+Anh thành Lan Anh?**  
Vì URLDecoder có form-urlencoded semantics, dấu + là space. Muốn dấu cộng thật, mã hóa %2B.

**5. Query có tag=red&tag=blue thì chọn giá trị nào?**  
Nếu API cho phép lặp, giữ cả hai trong List; không tự ghi đè.

**6. HttpContext("/inspect") có luôn là exact route?**  
Không. Nó match theo prefix; /inspect-other có thể vào handler đó.

**7. Headers.getFirst có đọc được content-type nếu client gửi Content-Type?**  
Có, tên header case-insensitive.

**8. Vì sao getFirst không phù hợp với mọi header nhạy cảm?**  
Một số header có nhiều values/duplicates; chỉ lấy đầu tiên có thể tạo ambiguity.

**9. getRequestHeaders là mutable?**  
Không, theo HttpExchange là read-only. getResponseHeaders mutable.

**10. Body UTF-8 15 bytes có chắc 15 Java char?**  
Không. Unicode có thể có nhiều byte UTF-8 cho một char/code point.

**11. getRequestBody có trả chuỗi JSON đã parse?**  
Không. Trả InputStream bytes; ứng dụng phải decode/parse theo Content-Type.

**12. Gọi getRequestBody hai lần có tạo hai stream mới?**  
Không. Đây là cùng stream, dữ liệu đã đọc không tự replay.

**13. Content-Length không có là body rỗng?**  
Không. HTTP/1.1 chunked có thể gửi body mà không có Content-Length.

**14. Vì sao readAllBytes trên request không tin cậy có nguy cơ?**  
Nó có thể cấp phát nhiều RAM theo body không giới hạn, gây DoS.

**15. Hàm readLimited của demo đọc tối đa bao nhiêu bytes trước khi xác định vượt 32?**  
Tối đa 33 bytes, tức MAX_BODY+1 để phát hiện vượt ngưỡng.

**16. Vì sao dùng CharsetDecoder.REPORT?**  
Để từ chối UTF-8 malformed thay vì lặng lẽ thay bằng ký tự thay thế.

**17. POST Content-Type application/json khi route chỉ nhận text/plain nên trả gì?**  
415 Unsupported Media Type.

**18. PUT vào route chỉ hỗ trợ GET/POST nên trả gì?**  
405 Method Not Allowed kèm Allow: GET, POST.

**19. sendResponseHeaders(status,0) có nghĩa không body?**  
Không. JDK HttpExchange dùng 0 cho chunked response; -1 cho no-body.

**20. Khi response length fixed nhưng ghi không đủ bytes thì sao?**  
Có thể IOException/abort exchange, làm underlying connection đóng.

**21. Đóng exchange khi request chưa đọc hết có bảo đảm TCP được tái sử dụng?**  
Không. JDK có thể drain một phần unread bytes, nhưng nếu không đủ có thể đóng connection.

**22. Khi server ở sau proxy, getRemoteAddress có luôn là IP client gốc?**  
Không. Có thể là proxy; forwarded headers chỉ tin từ proxy được kiểm soát.

**23. Byte cap bảo vệ hoàn toàn trước slow clients?**  
Không. Cần request/read deadline, concurrency và connection limits.

**24. Demo này có kiểm chứng HTTPS production không?**  
Không. Demo HTTP/1.1 loopback, dùng để kiểm tra method, URI, header và body lifecycle trên JDK.

## Kết luận

Để đọc HTTP request trong **JDK HttpServer**, dùng **HttpExchange.getRequestMethod()** cho method, **getRequestURI()** cho path/query, **getRequestHeaders()** cho headers đa trị case-insensitive, và **getRequestBody()** cho body dạng **InputStream bytes**. Cần tách bạch metadata và payload, decode query/UTF-8 đúng format, không tin Content-Length là giới hạn duy nhất, và không coi HttpContext prefix là exact routing.

Một handler an toàn phải **validate method, path, header, media type và bytes**, dùng status phù hợp (400/404/405/413/415), đặt response headers, **sendResponseHeaders với đúng byte count**, rồi đóng OutputStream và HttpExchange. Khi phục vụ lưu lượng thật, bổ sung authentication, TLS, timeouts, rate limits và hardening ở proxy/gateway.

### Tài liệu tham khảo

- [Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request method/URI/headers/body, response length và close.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): createContext, literal-prefix routing, executor.
- [Java SE 17 — Headers](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): case-insensitive multi-valued request/response headers.
- [Java SE 17 — HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): handle(HttpExchange).
- [Java SE 17 — HttpContext](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): context path, Filters, Authenticator.
- [Java SE 17 — URI](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html): raw path, raw query, URI decoding.
- [Java SE 17 — URLDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLDecoder.html): form-style percent-decoding.
- [Java SE 17 — CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): strict UTF-8.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): local integration test client.
- [Java SE 17 — HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): HTTPS variant.
- [Java 17 Networking Properties](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): giới hạn kết nối/headers/request của JDK HttpServer implementation.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): methods, status codes, media types.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html): Content-Length, chunked và request framing.
- [OWASP — HTTP Request Smuggling](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/07-Injection/16-HTTP_Request_Smuggling/): rủi ro frontend/backend parsing khác nhau.
