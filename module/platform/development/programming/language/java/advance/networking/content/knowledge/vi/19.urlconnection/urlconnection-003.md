# Đọc metadata và stream của tài nguyên với đóng tài nguyên rõ ràng

## 1. Mục tiêu: đọc đúng thông tin, đọc đủ dữ liệu, luôn giải phóng tài nguyên

Trong Java Networking, `java.net.URLConnection` là lớp trừu tượng biểu diễn **một liên kết tới tài nguyên được định vị bởi URL**. Một tài nguyên có thể đến từ `http:`, `https:`, `file:` hoặc một protocol handler khác mà môi trường Java hỗ trợ. Tài nguyên không chỉ có **nội dung bytes**: kết nối còn có thể cung cấp **metadata** như content type, content length, content encoding, last-modified và các response headers.

Khi dùng URLConnection, có ba việc cần làm tách bạch:

1. **Cấu hình trước kết nối:** timeouts, request headers, caching, method và redirect policy nếu là HTTP.
2. **Đọc metadata và stream đúng thời điểm:** kết nối có thể được tạo lazy; metadata có thể vắng mặt, và HTTP error response khác với success response.
3. **Đóng tài nguyên rõ ràng:** đặt `InputStream`/`OutputStream` trong `try-with-resources`, có `finally` khi phải gọi `HttpURLConnection.disconnect()`, và dọn file tạm nếu tải xuống thất bại.

Một ví dụ ngắn về ý đồ:

```java
URLConnection connection = url.openConnection();
connection.setConnectTimeout(3000);
connection.setReadTimeout(3000);

String type = connection.getContentType();
long size = connection.getContentLengthLong();

try (InputStream input = connection.getInputStream()) {
    // Đọc và xử lý bytes; giới hạn kích thước nếu URL không đáng tin.
}
// input được close ở đây kể cả khi xảy ra exception trong block.
```

Đây là **mảnh code minh họa**, cần `java.net.URL`, `java.net.URLConnection`, `java.io.InputStream` và một biến `URL url` hợp lệ. Phương thức `getContentType()` hoặc `getInputStream()` có thể gây network I/O; không hiểu chúng như chỉ đọc một object đã có dữ liệu trong bộ nhớ.

Sau bài học, bạn cần:
- Giải thích được quan hệ `URL.openConnection()` → cấu hình → kết nối → metadata → stream.
- Dùng đúng `getContentType()`, `getContentLengthLong()`, `getHeaderField()`, `getHeaderFields()`, `getLastModified()` và các getters liên quan.
- Hiểu giá trị `-1` (content length không biết) và `null`/`0` (metadata chưa có).
- Phân biệt `HttpURLConnection.getInputStream()` và `getErrorStream()` khi HTTP trả mã lỗi.
- Đọc stream theo vòng lặp, biết ranh giới giữa **byte count** với **ký tự UTF-8**.
- Đặt các thao tác close/disconnect/file cleanup trong cấu trúc không bị bỏ qua khi có lỗi.
- Chạy được hai chương trình **Java 17+** dùng HTTP loopback và file tạm, không cần Internet.
- Tránh bẫy memory, timeout, redirect, nén nội dung và các URL không đáng tin.

## 2. URL, URLConnection và HttpURLConnection không phải cùng một đối tượng

Bản đồ kiến trúc:

```text
String URL hoặc URI (địa chỉ tài nguyên)
        │
        ▼
    URL object
        │ url.openConnection()
        ▼
  URLConnection object ── cấu hình trước connect:
        │                   timeouts, headers, cache, ...
        │
        ├─ nếu URL là http:/https: thường hỗ trợ HttpURLConnection
        │      │
        │      ├─ getResponseCode()       HTTP status
        │      ├─ getInputStream()        body thành công
        │      ├─ getErrorStream()        body lỗi nếu có
        │      └─ disconnect()            kết thúc sử dụng connection instance
        │
        └─ nếu URL là file:
               metadata và InputStream của tài nguyên file
        │
        ▼
  bytes tài nguyên + metadata liên quan
```

Điểm quan trọng:
- **`URL`** mô tả vị trí tài nguyên, nhưng chỉ tạo `URL` chưa đọc dữ liệu.
- **`URLConnection`** là lớp trừu tượng; `openConnection()` tạo một object connection nhưng **không bắt buộc mở kết nối ngay lúc gọi**.
- **`HttpURLConnection`** là subclass dành cho HTTP; trong HTTPS thường dùng subclass `HttpsURLConnection` của nó. Nó có HTTP status, method, redirect control và error stream.
- **`InputStream`** là tài nguyên đọc byte thực tế; nó **không đóng tự động** chỉ vì biến connection ra khỏi scope.
- **`HttpURLConnection` không implement `AutoCloseable`**, nên không dùng `try (HttpURLConnection connection = ...)`. Thay vào đó close stream và gọi `disconnect()` trong `finally` nếu phù hợp.

Với file URL, không nên cast connection sang `HttpURLConnection`; hãy dùng các API chung của `URLConnection`. Trái lại, khi cần phân biệt HTTP 200 và 404, chỉ làm việc qua `URLConnection.getInputStream()` sẽ bỏ mất API HTTP đặc thù; nên cast khi đã biết URL scheme và kiểm tra kiểu.

## 3. Vòng đời kết nối: cấu hình trước, I/O sau

Tài liệu Java 17 mô tả quá trình khái quát:

```text
1. URL url = ...
2. URLConnection c = url.openConnection()
3. c.setConnectTimeout(...), c.setReadTimeout(...),
   c.setRequestProperty(...), c.setUseCaches(...)
4. c.connect() hoặc một thao tác đọc metadata/stream tự kích hoạt connect
5. c.getHeaderField(...), c.getContentType(), c.getInputStream()
6. Đọc/ghi nội dung, đóng streams; nếu HTTP, disconnect khi kết thúc
```

`connect()` có thể gọi tường minh, nhưng thông thường không bắt buộc vì một số phương thức như `getInputStream()` sẽ tự kết nối nếu cần. Điểm **bắt buộc về logic** là **đặt cấu hình trước thao tác có thể kết nối**.

Ví dụ sai:

```java
URLConnection c = url.openConnection();
InputStream stream = c.getInputStream(); // có thể đã connect
c.setRequestProperty("Accept", "application/json"); // quá muộn
```

Ví dụ đúng:

```java
URLConnection c = url.openConnection();
c.setConnectTimeout(3000);
c.setReadTimeout(5000);
c.setRequestProperty("Accept", "application/json");
try (InputStream stream = c.getInputStream()) {
    // đọc body
}
```

Hai đoạn này là **mảnh code** không tự chạy vì cần biến `url` và imports. Với `URLConnection`, nhiều setter sẽ ném `IllegalStateException` nếu đã kết nối; ngay cả khi không ném, đừng trông chờ cấu hình mới sửa được request đã gửi.

### connectTimeout và readTimeout

| API | Tác dụng chính | Đơn vị |
| --- | --- | --- |
| `setConnectTimeout(int)` | Giới hạn thời gian chờ **thiết lập** kết nối | Milliseconds; `0` là vô hạn |
| `setReadTimeout(int)` | Giới hạn thời gian **chờ dữ liệu khi đọc** từ kết nối | Milliseconds; `0` là vô hạn |
| Deadline tổng thể của ứng dụng | Giới hạn toàn bộ thao tác, gồm redirects, nhiều lần read, parse và lưu file | Do ứng dụng tự quản lý |

Một read timeout **không phải deadline tải toàn bộ file**: server gửi mỗi lần một chút trước khi timeout có thể giữ stream lâu hơn dự kiến. Khi tải dữ liệu từ URL không đáng tin, nên có thêm **giới hạn tổng thời gian, số byte và số redirect hops**.

## 4. Metadata quan trọng của URLConnection

`URLConnection` có các accessor phổ biến:

| Phương thức | Dữ liệu nhận được | Khi không biết |
| --- | --- | --- |
| `getContentType()` | MIME type, có thể kèm charset, ví dụ `text/plain; charset=UTF-8` | `null` |
| `getContentLengthLong()` | Content length dưới dạng `long` | `-1` |
| `getContentLength()` | Content length dưới dạng `int` | `-1` nếu không biết hoặc quá `Integer.MAX_VALUE` |
| `getContentEncoding()` | Content coding như `gzip` nếu server khai báo | `null` |
| `getDate()` | Thời gian `Date` của response, milliseconds từ Unix epoch | `0` |
| `getLastModified()` | Thời gian `Last-Modified`, milliseconds từ Unix epoch | `0` |
| `getExpiration()` | Thời gian `Expires`, milliseconds từ Unix epoch | `0` |
| `getHeaderField("ETag")` | Giá trị header tương ứng | `null` |
| `getHeaderFieldDate(name, defaultValue)` | Parse header ngày thành epoch millis nếu hỗ trợ | Giá trị default truyền vào |
| `getHeaderFields()` | Map các response headers và danh sách giá trị | Có thể thiếu header cần tìm, tùy protocol |
| `getURL()` | URL được gắn với connection object | Không phải một “final response URI” API chuyên dụng |

Metadata **có thể cần kết nối thật** để có được header. Do đó, gọi `getContentType()` không tương đương lấy dữ liệu tĩnh không có network I/O.

### Vì sao ưu tiên getContentLengthLong?

`getContentLengthLong()` dùng `long`, hỗ trợ giá trị lớn hơn 2 GiB. `getContentLength()` dùng `int` và có thể trả `-1` nếu kích thước lớn hơn `Integer.MAX_VALUE`. Với file/download, dùng `long` cho số byte nhưng **vẫn áp giới hạn tải thực tế** theo nghiệp vụ.

Ví dụ:

```java
long declaredLength = connection.getContentLengthLong();
if (declaredLength >= 0) {
    System.out.println("Declared length: " + declaredLength);
} else {
    System.out.println("Length unknown; read until EOF, with a size limit.");
}
```

Đây là mảnh code, biến `connection` phải đã được khởi tạo. `-1` **không có nghĩa tài nguyên rỗng**. Nó chỉ nói metadata không cung cấp kích thước đáng tin tại thời điểm truy vấn.

## 5. Metadata không phải sự thật tuyệt đối về nội dung

Với tài nguyên lấy từ network:
- `Content-Type` do server/handler khai báo, có thể sai hoặc thiếu. Không dựa duy nhất vào MIME type để quyết định chạy/chấp nhận file không tin cậy.
- `Content-Length` thể hiện độ dài **bytes** được khai báo cho representation/message theo semantics HTTP, không phải số ký tự Unicode. Nó có thể thiếu nếu response dùng chunked encoding hoặc HTTP framing khác.
- `Content-Length` có thể sai trong response không hợp lệ. Code phải xử lý stream kết thúc sớm, nhiều byte hơn dự kiến và lỗi I/O.
- `Last-Modified` do server công bố; không tự chứng minh nội dung có tính toàn vẹn hoặc nguồn đáng tin.
- `ETag` là HTTP validator, không phải chữ ký mật mã chống sửa file.
- `Content-Encoding: gzip` liên quan tới content coding; **không đồng nghĩa** `charset=UTF-8`. Hai khái niệm là nén bytes và giải mã ký tự.

Phân biệt:

```text
HTTP response:
Content-Type: text/plain; charset=UTF-8
Content-Encoding: gzip
Content-Length: 128

=> Content-Type nói loại media và mã ký tự dự kiến.
=> Content-Encoding nói representation bytes đang bị nén gzip.
=> Content-Length là độ dài byte của representation theo framing,
   không trực tiếp là số ký tự Unicode sau giải mã.
```

Khi giải mã, hãy theo protocol/content-coding và charset đã được kiểm tra, không gọi `new String(rawBytes)` với charset mặc định rồi kỳ vọng mọi máy đọc đúng tiếng Việt.

## 6. HTTP status và metadata: dùng HttpURLConnection đúng lúc

Với URL `http:` hoặc `https:`, thông tin status code và response message nằm trên `HttpURLConnection`:

```java
HttpURLConnection c = (HttpURLConnection) url.openConnection();
c.setConnectTimeout(3000);
c.setReadTimeout(3000);
c.setInstanceFollowRedirects(false);
try {
    int code = c.getResponseCode(); // có thể kết nối và đọc status/headers
    System.out.println("HTTP status = " + code);
    System.out.println("Content type = " + c.getContentType());
} finally {
    c.disconnect();
}
```

Đây là mảnh code, giả định `url` là HTTP/HTTPS URL. Với `file:`, cast này **không hợp lệ**.

`getResponseCode()` có thể trả `-1` nếu response không phải HTTP hợp lệ hoặc ném `IOException` khi I/O thất bại. Các status `404`/`500` vẫn là response HTTP có ý nghĩa, không giống việc không tạo được TCP connection.

Một chương trình tải dữ liệu **không nên** chỉ nhìn `getContentLengthLong()` rồi gọi `getInputStream()` mà bỏ qua status code. Nếu server trả 404, người dùng cần thông báo **HTTP 404**, và đôi khi có một error body hữu ích.

## 7. Success stream và error stream là hai đường xử lý

`HttpURLConnection` cung cấp:
- **`getInputStream()`:** luồng dữ liệu thông thường của tài nguyên, thường dùng khi status thành công.
- **`getErrorStream()`:** luồng nội dung lỗi **nếu có**. Ví dụ server trả 404 kèm một trang mô tả lỗi.
- **`getResponseCode()`:** status để ứng dụng chọn đúng đường.

Với 404, `getInputStream()` có thể ném `FileNotFoundException` hoặc `IOException` thay vì trả error body. Đừng dùng exception đó làm lý do bỏ qua body hữu ích; trước đó lấy status và thử `getErrorStream()`.

Ví dụ khái quát:

```java
int status = c.getResponseCode();
if (status >= 200 && status < 300) {
    try (InputStream body = c.getInputStream()) {
        // consume success body
    }
} else {
    InputStream error = c.getErrorStream();
    if (error != null) {
        try (InputStream body = error) {
            // đọc error body tối đa một hạn mức an toàn
        }
    }
    // Quyết định retry, báo lỗi hoặc xử lý status nghiệp vụ.
}
```

Đây là **mảnh code**; `c` là `HttpURLConnection` đã cấu hình, các hàm xử lý body do ứng dụng cung cấp. Một số response như 204 hoặc 304 **không có response body**, và `getErrorStream()` được phép trả `null`. Không giả định mọi 4xx/5xx luôn có JSON error payload.

**Quan trọng:** `getErrorStream()` **không tự khởi tạo kết nối** nếu connection chưa được kết nối. Gọi nó trước `getResponseCode()` rồi thấy `null` không chứng minh server không gửi body. Cần xem response code/headers và trạng thái kết nối phù hợp.

## 8. Cách đọc HTTP headers đúng và không làm lộ metadata nhạy cảm

Những cách đọc phổ biến:

```java
String type = c.getHeaderField("Content-Type");
String etag = c.getHeaderField("ETag");
String modified = c.getHeaderField("Last-Modified");

Map<String, List<String>> headers = c.getHeaderFields();
headers.forEach((name, values) -> {
    // Chỉ log tên header được allowlist và giá trị không nhạy cảm.
});
```

Đây là mảnh code, cần `java.util.Map`, `java.util.List` và biến `c` là connection có thể truy cập headers. `getHeaderFields()` trả một map không thể sửa và các danh sách values không thể sửa theo Java SE 17 API. Trong HTTP implementations, có thể có entry tên `null` biểu diễn status line; code lặp phải xử lý key `null` thay vì gọi `name.toLowerCase()` vô điều kiện.

Một header có thể xuất hiện nhiều lần. `getHeaderField(String)` trả một giá trị (Java docs mô tả giá trị cuối khi header có nhiều giá trị); `getHeaderFields()` cho bạn danh sách, phù hợp hơn với `Set-Cookie` và những headers cần phân biệt nhiều occurrences.

Tuy nhiên **không log nguyên map headers** trong production: `Set-Cookie`, `WWW-Authenticate`, bearer token trong custom headers, signed Location và dữ liệu cá nhân có thể bị rò ra logs.

### Header names không nhạy chữ hoa/thường theo HTTP

Khi đọc theo tên, `Content-Type` và `content-type` về mặt HTTP là cùng field name. `HttpURLConnection.getHeaderField("Content-Type")` dùng protocol handler để tra cứu; không tự triển khai một parser chuỗi HTTP header text nếu không cần.

Nếu server trả header thiếu hoặc sai:
- `getHeaderField(...)` có thể trả `null`.
- `getContentType()` có thể `null`.
- `getContentLengthLong()` có thể `-1`.
- Ứng dụng vẫn có thể đọc stream nếu protocol/status cho phép.

## 9. Java 17+ runnable: đọc metadata và stream từ HTTP/file

Ví dụ đầy đủ đầu tiên tạo HTTP server trên **127.0.0.1** ở port ngẫu nhiên, với ba endpoints:
- `/ok`: status 200, body `hello-connection`, metadata Content-Type, Last-Modified, X-Demo và Content-Length.
- `/missing`: status 404 và error body `not-found`.
- `/chunked`: status 200 và body `chunk-body`, nhưng không có Content-Length xác định trước (chunked response).
- Ngoài HTTP, chương trình tạo file tạm với body `file-data`, mở `file:` URL, đọc qua `URLConnection` và xóa file.

Để tránh test phụ thuộc Internet hoặc một server công khai thay đổi, mọi dữ liệu đều được sinh trong process. Chương trình đóng mọi `InputStream` bằng `try-with-resources`, gọi `disconnect()` trên HTTP connection trong `finally`, dừng server trong `finally` và xóa file tạm.

Lưu đúng file **`URLConnectionMetadataDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URL;
import java.net.URLConnection;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class URLConnectionMetadataDemo {
    private static void serve(HttpExchange exchange, int code,
                              String text, boolean knownLength)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type",
                "text/plain; charset=UTF-8");
        exchange.getResponseHeaders().set("Last-Modified",
                "Wed, 21 Oct 2015 07:28:00 GMT");
        exchange.getResponseHeaders().set("X-Demo", "metadata");
        exchange.sendResponseHeaders(code, knownLength ? data.length : 0);
        try (var out = exchange.getResponseBody()) {
            out.write(data);
        }
    }

    private static HttpURLConnection openHttp(URL url) throws IOException {
        HttpURLConnection c = (HttpURLConnection) url.openConnection();
        c.setConnectTimeout(3000);
        c.setReadTimeout(3000);
        c.setUseCaches(false);
        c.setRequestProperty("Accept", "text/plain");
        c.setInstanceFollowRedirects(false);
        return c;
    }

    private static void readOk(URL url) throws IOException {
        HttpURLConnection c = openHttp(url);
        try {
            int status = c.getResponseCode();
            String type = c.getContentType();
            long length = c.getContentLengthLong();
            String demo = c.getHeaderField("X-Demo");
            String modified = c.getHeaderField("Last-Modified");
            String body;
            try (InputStream in = c.getInputStream()) {
                body = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            }
            System.out.println("status=" + status);
            System.out.println("content-type=" + type);
            System.out.println("content-length=" + length);
            System.out.println("x-demo=" + demo);
            System.out.println("last-modified=" + modified);
            System.out.println("body=" + body);
        } finally {
            c.disconnect();
        }
    }

    private static void readMissing(URL url) throws IOException {
        HttpURLConnection c = openHttp(url);
        try {
            System.out.println("404-status=" + c.getResponseCode());
            try (InputStream err = c.getErrorStream()) {
                String body = err == null ? "(no body)"
                        : new String(err.readAllBytes(),
                                     StandardCharsets.UTF_8);
                System.out.println("404-error=" + body);
            }
        } finally {
            c.disconnect();
        }
    }

    private static void readChunked(URL url) throws IOException {
        HttpURLConnection c = openHttp(url);
        try {
            System.out.println("chunk-status=" + c.getResponseCode());
            System.out.println("chunk-length=" + c.getContentLengthLong());
            try (InputStream in = c.getInputStream()) {
                System.out.println("chunk-body=" + new String(
                        in.readAllBytes(), StandardCharsets.UTF_8));
            }
        } finally {
            c.disconnect();
        }
    }

    private static void readFile() throws IOException {
        Path path = Files.createTempFile("urlconnection-", ".txt");
        try {
            Files.writeString(path, "file-data", StandardCharsets.UTF_8);
            URLConnection c = path.toUri().toURL().openConnection();
            try (InputStream in = c.getInputStream()) {
                System.out.println("file-body=" + new String(
                        in.readAllBytes(), StandardCharsets.UTF_8));
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext("/ok", e ->
                serve(e, 200, "hello-connection", true));
        server.createContext("/missing", e ->
                serve(e, 404, "not-found", true));
        server.createContext("/chunked", e ->
                serve(e, 200, "chunk-body", false));
        server.start();
        try {
            String base = "http://127.0.0.1:" +
                    server.getAddress().getPort();
            readOk(new URL(base + "/ok"));
            readMissing(new URL(base + "/missing"));
            readChunked(new URL(base + "/chunked"));
            readFile();
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac URLConnectionMetadataDemo.java
java URLConnectionMetadataDemo
```

**Stdout đã kiểm chứng bằng `javac --release 17` và chạy local:**

```text
status=200
content-type=text/plain; charset=UTF-8
content-length=16
x-demo=metadata
last-modified=Wed, 21 Oct 2015 07:28:00 GMT
body=hello-connection
404-status=404
404-error=not-found
chunk-status=200
chunk-length=-1
chunk-body=chunk-body
file-body=file-data
```

### Tại sao Content-Length bằng 16?

`hello-connection` là chuỗi ASCII dài 16 byte trong UTF-8, và server gọi `sendResponseHeaders(200, data.length)`. `getContentLengthLong()` phản ánh header Content-Length do server cung cấp. Trong response chunked, chương trình gọi `sendResponseHeaders(200, 0)` theo contract của `HttpServer` để sử dụng chunked transfer, nên `getContentLengthLong()` trả `-1`.

Đừng suy ra server trên Internet sẽ dùng chunked khi truyền cùng body. HTTP/2 không dùng `Transfer-Encoding: chunked` như HTTP/1.1; cách framing có thể khác. `-1` vẫn có ý nghĩa “không biết độ dài qua metadata”, không phải “không có body”.

### Tại sao try-with-resources cho error stream được phép null?

Trong Java, resource expression như `try (InputStream err = c.getErrorStream())` có thể nhận `null`; cấu trúc try-with-resources không gọi `close()` trên resource null. Code vẫn chủ động kiểm tra `err == null` trước khi đọc. Dù trong demo server có error body, một server khác hoàn toàn có thể không có.

### Vì sao file URL không gọi disconnect?

`URLConnection` chung không có `disconnect()`. File URL sử dụng protocol handler riêng; đóng `InputStream` là việc quan trọng. Chương trình còn dùng `Files.deleteIfExists(path)` trong `finally` để xóa file tạm **sau khi stream đã đóng** — đặc biệt cần thiết trên hệ điều hành không cho xóa file đang mở.

### Giới hạn của code ví dụ

`readAllBytes()` được dùng với **response nhỏ do chính test server tạo**. Với URL người dùng nhập hoặc server không đáng tin, không được gọi `readAllBytes()` vô giới hạn: có thể gây dùng quá nhiều heap. Ví dụ thứ hai ở mục 12 trình bày cách đọc theo chunks và **giới hạn tổng số byte**.

## 10. Đọc stream: read() không đảm bảo trả đầy buffer

`InputStream.read(byte[])` trả số bytes đã đọc, có thể nhỏ hơn dung lượng buffer; `-1` nghĩa là EOF. Code đúng phải tiếp tục cho tới EOF hoặc đủ số bytes theo framing riêng.

```java
try (InputStream in = connection.getInputStream()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        processBytes(buffer, 0, n);
    }
}
```

Đây là **mảnh code**; `processBytes(...)` là hàm ứng dụng phải định nghĩa và `connection` đã được kết nối/cấu hình. Phải xử lý chính xác `n` bytes, không đưa cả `buffer.length` byte cho consumer vì phần còn lại có thể là dữ liệu cũ.

Với `readNBytes(n)` hoặc `readAllBytes()`:
- Chúng giúp code ngắn cho dữ liệu **nhỏ và có giới hạn**.
- Chúng **không tự tạo memory limit an toàn** cho response không tin cậy.
- Dùng `readAllBytes()` trên endpoint streaming vô hạn hoặc file nhiều gigabyte là thiết kế nguy hiểm.
- Dùng `BufferedInputStream` có thể giảm overhead khi đọc từng lượng nhỏ, nhưng không thay thế size limit hay timeout.

**Body response** là luồng bytes. Không coi một lần `InputStream.read` là một HTTP message mới, và không suy ra boundary HTTP/TCP từ mỗi lần read.

## 11. Đóng tài nguyên: try-with-resources và finally

Mẫu tối thiểu cho HTTP:

```java
HttpURLConnection c = (HttpURLConnection) url.openConnection();
c.setConnectTimeout(3000);
c.setReadTimeout(5000);
try {
    try (InputStream in = c.getInputStream()) {
        // consume
    }
} finally {
    c.disconnect();
}
```

Đây là mảnh code, còn phải kiểm tra status/error stream ở các trường hợp production. Lợi ích:
- Nếu quá trình parse/đọc ném exception, `InputStream.close()` vẫn được gọi.
- Nếu close xong hoặc setup/read bị lỗi, `disconnect()` vẫn được gọi trong `finally`.
- Không phải viết `in.close()` ở tất cả return/throw paths.
- Các exceptions phát sinh khi close có thể được giữ ở dạng suppressed exceptions, hỗ trợ debug.

### close stream và disconnect khác nhau

Theo Java SE 17:
- Gọi `close()` trên `InputStream` hoặc `OutputStream` của `URLConnection` **có thể** giải phóng network resources tùy protocol.
- Mỗi instance `HttpURLConnection` đại diện cho một HTTP request; underlying persistent TCP connection **có thể được chia sẻ/tái sử dụng** qua những instances khác.
- `disconnect()` báo rằng ứng dụng sẽ không dùng kết nối này nữa; nó **có thể đóng socket nền** nếu persistent connection đang idle, nhưng **không bảo đảm** mọi TCP resource bị đóng tức khắc.
- `disconnect()` **không** cho phép tái sử dụng chính instance `HttpURLConnection` đó để gửi request mới.

Vì thế **không thay `try-with-resources` bằng mỗi `disconnect()`**. Với streaming/large response, phải đóng stream để giải phóng tài nguyên liên quan đúng cách.

### Đóng tài nguyên ngay cả khi body không đọc hết

Một số application chỉ cần metadata hoặc một phần body. Nếu đã mở input stream mà không cần phần còn lại, vẫn nên đóng stream. Với HTTP keep-alive, việc đóng sớm có thể làm connection không tái sử dụng được hoặc thúc đẩy đóng socket; đó là đánh đổi đúng nếu app không muốn tiêu thụ dữ liệu còn lại. Đừng giữ stream treo chỉ để “hy vọng connection pool tái sử dụng tốt hơn”.

## 12. Java 17+ runnable: tải theo chunk, giới hạn byte và xóa file tạm

Metadata `Content-Length` chỉ là một **hint** và có thể thiếu. Muốn giới hạn file tải từ URL, cần **hai kiểm tra**:
1. Nếu `getContentLengthLong() > MAX_BYTES` thì từ chối sớm để đỡ phí.
2. Khi thực sự đọc, cộng **số byte nhận thật**. Nếu vượt hạn mức thì dừng và xóa file tạm.

Chương trình sau dùng server loopback có hai endpoints:
- `/small` body `ABCDEF` = 6 bytes.
- `/large` body `ABCDEFGHIJKL` = 12 bytes.
- Client đặt `maxBytes = 8` và chỉ nhận nội dung nhỏ.

Code có `try-with-resources` cho **cả InputStream và OutputStream**, dọn temp file và disconnect trong `finally`.

Lưu file **`BoundedDownloadDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class BoundedDownloadDemo {
    private static void serve(HttpExchange exchange, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, data.length);
        try (var out = exchange.getResponseBody()) {
            out.write(data);
        }
    }

    private static long receive(URL url, long maxBytes) throws IOException {
        if (maxBytes < 0) throw new IllegalArgumentException("negative limit");
        HttpURLConnection c = (HttpURLConnection) url.openConnection();
        c.setConnectTimeout(3000);
        c.setReadTimeout(3000);
        c.setInstanceFollowRedirects(false);
        Path temporary = null;
        try {
            if (c.getResponseCode() != 200) {
                throw new IOException("Unexpected HTTP status");
            }
            long declared = c.getContentLengthLong();
            if (declared > maxBytes) {
                throw new IOException("Declared body exceeds limit");
            }
            temporary = Files.createTempFile("bounded-download-", ".part");
            long bytes = 0;
            try (InputStream in = c.getInputStream();
                 OutputStream out = Files.newOutputStream(temporary)) {
                byte[] buffer = new byte[4096];
                int n;
                while ((n = in.read(buffer)) != -1) {
                    if (n > maxBytes - bytes) {
                        throw new IOException("Actual body exceeds limit");
                    }
                    out.write(buffer, 0, n);
                    bytes += n;
                }
            }
            return bytes;
        } finally {
            if (temporary != null) Files.deleteIfExists(temporary);
            c.disconnect();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/small", e -> serve(e, "ABCDEF"));
        server.createContext("/large", e -> serve(e, "ABCDEFGHIJKL"));
        server.start();
        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            System.out.println("small-bytes=" +
                    receive(new URL(base + "/small"), 8));
            try {
                receive(new URL(base + "/large"), 8);
                System.out.println("large-rejected=false");
            } catch (IOException expected) {
                System.out.println("large-rejected=true");
            }
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac BoundedDownloadDemo.java
java BoundedDownloadDemo
```

Stdout đã kiểm chứng:

```text
small-bytes=6
large-rejected=true
```

### Vì sao code dùng maxBytes - bytes?

`if (n > maxBytes - bytes)` tránh **tràn số khi cộng** trong trường hợp dữ liệu lớn: việc so sánh phần dung lượng còn lại an toàn hơn cộng `bytes + n` rồi mới so. `bytes` chỉ tăng sau khi đã xác nhận lượng nhận không vượt `maxBytes`.

### Vì sao tạo file tạm rồi xóa?

Ví dụ chỉ cần chứng minh giới hạn và cleanup nên xóa file tạm **cả khi thành công lẫn thất bại**. Trong ứng dụng download thật, có thể:
1. Tạo file tạm bên cạnh thư mục đích.
2. Ghi toàn bộ và xác minh size/hash/content-type/signature theo policy.
3. Flush và đóng stream.
4. Chuyển file tạm sang vị trí chính thức bằng một bước rename/move an toàn, nếu hệ thống file cho phép.
5. Xóa file tạm nếu bị lỗi hoặc vượt giới hạn.

**Không** để một file tải dở bị coi là artifact hoàn chỉnh. Với filesystem khác nhau, `ATOMIC_MOVE` có thể không được hỗ trợ; thiết kế xử lý fallback/rollback rõ ràng.

### Nếu Content-Length = -1 thì sao?

Khi metadata không biết size, code **không từ chối ngay** chỉ vì `-1`. Vòng đọc vẫn giám sát **bytes nhận thật**, nên một response chunked cũng bị chặn khi vượt 8 bytes. Đây là điểm quan trọng hơn việc chỉ dựa vào Content-Length để quyết định cấp phát.

## 13. Đọc văn bản: charset phải rõ ràng

InputStream cung cấp bytes. Để đọc tiếng Việt, phải chọn charset đúng, thường là UTF-8.

```java
try (InputStream in = connection.getInputStream();
     InputStreamReader decoder =
             new InputStreamReader(in, StandardCharsets.UTF_8);
     BufferedReader reader = new BufferedReader(decoder)) {
    String line;
    while ((line = reader.readLine()) != null) {
        processLine(line);
    }
}
```

Đây là mảnh code với `processLine` là hàm ứng dụng. Có thể đơn giản hơn với `new BufferedReader(new InputStreamReader(in, UTF_8))`. Đừng dùng `new InputStreamReader(in)` mà không chỉ rõ charset nếu protocol chưa quy định và bạn muốn hành vi ổn định giữa các runtime/locale.

### Content-Type và charset

Ví dụ metadata:

```http
Content-Type: text/plain; charset=UTF-8
```

Server khai báo text là UTF-8. Với HTTP response thực, nên parse `charset` theo MIME rules hoặc dùng thư viện phù hợp, có fallback theo protocol; không dùng `String.split(";")` quá đơn giản với mọi cú pháp content-type. Nếu header bị thiếu, lựa chọn charset **phụ thuộc application protocol**, không có một quy tắc mặc định an toàn cho mọi file.

`Content-Encoding` như `gzip` là **lớp nén**, phải giải nén (nếu client chưa tự xử lý theo handler) trước khi decode ký tự. Không truyền gzip bytes thẳng vào UTF-8 decoder rồi kết luận file hỏng.

## 14. Trường hợp HTTP không có Content-Length: chunked và streaming

Đối với HTTP/1.1:
- Server có thể gửi body bằng `Transfer-Encoding: chunked` khi không biết trước size.
- Khi đó `Content-Length` thường không có, và `URLConnection.getContentLengthLong()` trả `-1`.
- Mã client vẫn **đọc qua InputStream** như bình thường; HTTP protocol handler xử lý chunk framing.
- App không phải tự parse chunk lengths từ stream mà `HttpURLConnection.getInputStream()` trả ra.

```text
HTTP response (wire, khái niệm):
HTTP/1.1 200 OK
Transfer-Encoding: chunked

5\r\nHello\r\n0\r\n\r\n

InputStream ở tầng ứng dụng đọc:
Hello

getContentLengthLong() = -1
```

Đây là mô tả giản lược; actual chunk framing có thể gồm nhiều chunks/trailers. Không đưa `\r\n` chunk delimiters vào parser payload khi dùng `HttpURLConnection`, vì protocol handler đã giải mã HTTP transfer framing.

**Không nhầm** chunked transfer encoding với `Content-Encoding: gzip`. Chunked giúp truyền message qua connection với length chưa biết, còn gzip nén representation bytes. Một response có thể có các lớp mã hóa tương ứng; code phải biết tầng nào tự được HTTP implementation xử lý.

## 15. HEAD request: hỏi metadata mà không tải body, với những giới hạn

Đối với HTTP, phương thức `HEAD` yêu cầu server cung cấp response headers gần tương đương `GET` mà **không gửi response body**. Đây là cách hữu ích khi cần content type, last-modified, etag hoặc kích thước ước lượng trước khi quyết định tải.

```java
HttpURLConnection head = (HttpURLConnection) url.openConnection();
head.setRequestMethod("HEAD");
head.setConnectTimeout(3000);
head.setReadTimeout(3000);
try {
    int status = head.getResponseCode();
    long length = head.getContentLengthLong();
    String type = head.getContentType();
    // Sử dụng status, length và type theo ứng dụng.
} finally {
    head.disconnect();
}
```

Đây là mảnh code, giả định `url` là HTTP(S) URL và cần imports. **Phải đặt `setRequestMethod("HEAD")` trước kết nối**.

Hạn chế:
- Server có thể không hỗ trợ HEAD đúng; có thể trả 405 hoặc metadata khác.
- `Content-Length` của HEAD thường là kích thước representation tương ứng với GET, không phải số byte body được truyền trong HEAD response.
- Metadata có thể thay đổi giữa HEAD và GET do tài nguyên biến động, cache hoặc content negotiation.
- HEAD **không thay** size limit trong vòng đọc của GET.
- Không mọi URL/protocol đều hỗ trợ HEAD; đây là hành vi HTTP-specific của `HttpURLConnection`.

Nếu chỉ muốn metadata cho file local, dùng `Files.size(path)` và `Files.getLastModifiedTime(path)` có thể đơn giản/rõ hơn `file:` URLConnection; URLConnection vẫn hữu ích khi cùng một abstraction xử lý nhiều schemes.

## 16. Caching và conditional requests: ETag, Last-Modified, 304

Một số metadata giúp tránh tải lại tài nguyên không đổi:
- `ETag`: validator do server cung cấp.
- `Last-Modified`: thời điểm sửa cuối theo server.
- `If-None-Match`/`If-Modified-Since`: client hỏi server có thay đổi không.
- `304 Not Modified`: server báo representation chưa đổi theo điều kiện; **thường không có response body**.

Ví dụ:

```java
URLConnection c = url.openConnection();
c.setIfModifiedSince(lastSeenMillis);
try (InputStream in = c.getInputStream()) {
    // Đọc khi protocol/status cho phép.
}
```

Đây là mảnh code; `lastSeenMillis` do ứng dụng lưu từ lần đọc trước. Với HTTP, nên kiểm tra cụ thể `HttpURLConnection.getResponseCode()` trước khi mở body, vì 304 có semantics khác 200. `setIfModifiedSince(long)` chỉ đặt conditional semantics theo handler; **không** biến server response thành bản cache sẵn có của ứng dụng.

Một mô hình lưu cache:
1. Lưu representation cũ kèm ETag/Last-Modified đã xác minh.
2. Gửi conditional GET.
3. Nếu `200`, đọc body, xác minh và cập nhật cache/metadata.
4. Nếu `304`, dùng **body cũ đang lưu trong cache của bạn**, không cố đọc body mới.
5. Nếu status lỗi, xử lý theo policy thay vì âm thầm coi là 304.

Cache validators không phải chữ ký chống giả mạo. Với nội dung nhạy cảm/an toàn cao, kiểm tra TLS, integrity hashes/signatures và quyền truy cập theo yêu cầu nghiệp vụ.

## 17. HeaderFieldDate và thời gian từ server

`getLastModified()` và `getDate()` trả `long` theo milliseconds Unix epoch, hoặc `0` nếu không biết. Muốn parse một header date khác:

```java
long fallback = -1;
long expires = connection.getHeaderFieldDate("Expires", fallback);
if (expires != fallback) {
    Instant when = Instant.ofEpochMilli(expires);
    System.out.println(when);
}
```

Đây là mảnh code, cần import `java.time.Instant` và biến `connection`. Trong production, `-1` là sentinel ứng dụng chọn; tránh coi ngày tháng server trả về là đồng hồ chuẩn hay dữ liệu tuyệt đối đáng tin.

**Lưu ý timezone:** Header HTTP date sử dụng định dạng ngày chuẩn theo GMT/UTC; milliseconds epoch không mang timezone display. Khi hiển thị, chuyển `Instant` sang timezone được chọn một cách tường minh; không dùng string parsing tùy locale mà không kiểm tra định dạng.

Một header có thể hoàn toàn không tồn tại. Đối với `getLastModified()`, `0` theo API có nghĩa “không biết”, nhưng về mặt giá trị epoch cũng là một thời điểm cụ thể; đừng thiết kế logic nghiệp vụ dựa vào việc `0` luôn là timestamp có ý nghĩa.

## 18. Redirect và metadata: kiểm tra resource cuối cùng nào đang được đọc

`HttpURLConnection` có cơ chế tự theo HTTP redirects tùy cấu hình. Trong Java 17, `getInstanceFollowRedirects()` của một connection mới nhận mặc định từ giá trị static `getFollowRedirects()`; mặc định static này thường **true**, khác với `java.net.http.HttpClient` có redirect default **NEVER**.

Nếu một URL trả 302 tới host khác:
- `getContentType()`/`getContentLengthLong()` sau auto-follow có thể phản ánh tài nguyên **đích sau redirect**.
- Mọi request headers/credentials có thể chịu quy tắc forwarding riêng.
- App tải URL từ người dùng có thể bị dẫn tới internal IP/metadata service (SSRF).
- Không nên giả định một `URL` ban đầu an toàn thì mọi Location về sau đều an toàn.

Bật kiểm soát thủ công cho connection cụ thể:

```java
HttpURLConnection c = (HttpURLConnection) url.openConnection();
c.setInstanceFollowRedirects(false);
c.setConnectTimeout(3000);
c.setReadTimeout(3000);
int status = c.getResponseCode();
// Nếu 3xx, đọc Location và tự đánh giá trước khi gửi request mới.
```

Đây là mảnh code không có cleanup hoàn chỉnh; trong production đặt `try/finally` và `disconnect()`, xử lý error streams. Chỉ kiểm tra một URL ban đầu rồi bật follow có thể để server chuyển sang host khác chưa được cấp phép.

**Chính sách an toàn:** Với URL untrusted, giới hạn scheme tới HTTPS khi phù hợp, whitelist hostname/port, kiểm tra DNS/egress policy và validate **mọi redirect hop**. Không gửi Authorization, Cookie hoặc custom API key sang đích khác chỉ vì `Location` đề nghị vậy. Đừng tự vô hiệu hóa HTTPS certificate/hostname verification để “tải file cho qua”.

## 19. InputStream là tài nguyên có ownership và vòng đời

Khi một hàm trả `InputStream` cho caller, phải quyết định **ai chịu trách nhiệm đóng**. Một ví dụ API không lý tưởng:

```java
InputStream openRemoteStream(URL url) throws IOException {
    URLConnection c = url.openConnection();
    return c.getInputStream();
}
```

Đây là mảnh code; nó đẩy nghĩa vụ `close()` sang caller mà không thể hiện rõ; nếu caller bỏ quên, tài nguyên có thể bị giữ. Còn nếu function đã tạo `HttpURLConnection`, function không thể tự gọi `disconnect()` trong `finally` ngay trước khi caller đọc stream vì sẽ phá lifecycle.

Thiết kế tốt hơn:
1. **Xử lý stream hoàn toàn bên trong method** với `try-with-resources`, trả model/data đã parse.
2. Nếu cần streaming API, **trả một resource owner rõ ràng** có phương thức `close()` đóng stream và network state, hoặc tài liệu API yêu cầu caller close stream.
3. Với streaming nhiều thread, bảo đảm parser/stream không bị close bởi thread khác trước khi consumer xong, trừ khi cancellation policy cho phép.
4. Với file download, tránh đưa `Path` tới file chưa tải đủ; chỉ công bố file đích sau khi write/verify hoàn tất.

Ví dụ method đọc chuỗi ngắn và tự đóng:

```java
static String fetchSmallText(URLConnection c) throws IOException {
    try (InputStream in = c.getInputStream()) {
        byte[] bytes = in.readNBytes(4097);
        if (bytes.length > 4096) {
            throw new IOException("Too much data");
        }
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
```

Đây là **mảnh code**; `readNBytes(4097)` chặn memory ở mức được chọn cho **phần đọc**, nhưng cần thêm deadline/network error handling, và nếu dùng HTTP cần status/error stream trước đó. `readNBytes(4097)` trả tối đa 4097 bytes, không phải vô hạn. Đọc vượt một byte để phát hiện kích thước quá hạn là kỹ thuật đơn giản cho payload nhỏ.

## 20. Sai lầm thường gặp khi close

| Cách làm | Vấn đề | Cách sửa |
| --- | --- | --- |
| Gọi `connection.getInputStream().readAllBytes()` mà không close | Stream có thể giữ tài nguyên | `try (InputStream in = ...)` |
| Chỉ gọi `disconnect()` | Không thay thế nghĩa vụ close stream; không luôn đóng socket tức khắc | Close stream và disconnect ở finally |
| Dùng `try (HttpURLConnection c = ...)` | `HttpURLConnection` không AutoCloseable | Try-with-resources cho stream, finally cho connection |
| Return sớm khi thấy status 404, không xem error stream | Bỏ thông tin lỗi và tài nguyên response | Đọc/đóng `getErrorStream()` nếu có, theo policy |
| Xóa file tạm trước khi đóng OutputStream | Có thể lỗi trên Windows và giữ file handle | Close streams trước; delete trong finally |
| Close một stream đang được worker khác đọc | Race hoặc dữ liệu bị cắt | Ràng buộc ownership/lifecycle |
| Tin close đảm bảo mọi byte đã được ghi ra đích | Có thể IOException hoặc lỗi storage | Kiểm tra errors, flush/close, atomic publish, checksum |
| Để file download dở ở path chính thức | Consumer có thể coi dữ liệu thiếu là hoàn chỉnh | Tải vào temp, verify rồi move |
| Không đóng error stream trong HTTP 500 | Connection resources/response body có thể còn pending | Close error body sau khi xử lý |
| Dùng một connection object cho nhiều HTTP requests | `HttpURLConnection` không dành để tái sử dụng instance request | Mỗi request một instance; underlying keepalive do handler quản lý |

`try-with-resources` bảo đảm gọi close theo thứ tự ngược chiều tạo resource khi kết thúc block, ngay cả khi có exception. Nhưng close **cũng có thể ném IOException**, nên ứng dụng vẫn phải xử lý/rethrow/log phù hợp; không được nuốt exception một cách im lặng rồi báo tải file thành công.

## 21. Lỗi và timeout: phản hồi HTTP khác với lỗi I/O

Các tình huống:
- HTTP 404/500: server đã phản hồi hợp lệ, `getResponseCode()` cho status; có thể có error body.
- `UnknownHostException`: DNS không resolve được tên.
- `ConnectException`: kết nối TCP bị từ chối/không thể thiết lập.
- `SocketTimeoutException`: hết thời gian connect hoặc read theo timeout đã cấu hình.
- `SSLHandshakeException`: TLS certificate/protocol/handshake không hợp lệ trên HTTPS.
- `EOFException` hoặc dữ liệu thiếu: body bị cắt so với framing mà ứng dụng kỳ vọng.
- `IOException` khi đọc stream/ghi disk/đóng tài nguyên.

Không viết:

```java
try (InputStream in = url.openStream()) {
    return new String(in.readAllBytes(), StandardCharsets.UTF_8);
} catch (IOException e) {
    return "";
}
```

như một chiến lược production chung. Đoạn này là **phản ví dụ**: nó đánh đồng lỗi network với tài nguyên hợp lệ rỗng, không nêu status, không giới hạn size. Thay bằng result/exception rõ ràng và observability có kiểm soát.

Khi gặp lỗi, cần log hostname/scheme/status/duration đã sanitize; không log Bearer tokens, cookies, signed query strings hay raw body nhạy cảm.

## 22. File URL và ranh giới bảo mật filesystem

`Path.toUri().toURL().openConnection()` cho phép mở `file:` URL với `URLConnection`, nhưng nếu nguồn URL đến từ user, **không** cho phép tùy tiện truy cập filesystem bằng cách nhận một URL bất kỳ.

Rủi ro:
- `file:///etc/passwd` hoặc file local nhạy cảm.
- Path traversal qua URL/URI được resolve không đúng.
- Windows drive/UNC path và network shares có semantics riêng.
- Symlink dẫn tới file ngoài thư mục được phép.
- TOCTOU giữa kiểm tra path và mở file.

Nếu ứng dụng chỉ muốn đọc file trong một thư mục, dùng `java.nio.file.Path` + canonical/real-path containment + file permissions/policy phù hợp, và cân nhắc race/symlink. Không dùng `new URL(userInput).openStream()` cho một dịch vụ backend có quyền đọc filesystem/network rộng.

**Không nhầm URLConnection file handler với đọc an toàn:** cùng API có thể mở nguồn remote lẫn local; security policy phải áp cho từng scheme và đích.

## 23. Hiệu năng và bộ nhớ khi đọc tài nguyên lớn

Một stream lớn có thể tiêu thụ:
- Network bandwidth.
- Heap nếu toàn bộ body được gom `byte[]`.
- File descriptors/socket handles.
- Disk nếu ghi file.
- CPU khi decompression, transcoding, parse.
- Threads nếu mỗi lượt tải blocking dài.

Kỹ thuật:
- Dùng buffer kích thước hợp lý (ví dụ 8 KiB, 16 KiB), không tăng buffer vô hạn theo remote Content-Length.
- Áp **max bytes** ngay cả khi header thiếu/sai.
- Dùng streaming parser thay vì giữ toàn bộ text khi dữ liệu lớn.
- Giới hạn concurrent downloads, kết nối đến cùng host và thời gian chờ.
- Xác minh content type/extension/signature theo mục đích tiêu thụ, không tin header tuyệt đối.
- Nếu tính hash nội dung, cập nhật `MessageDigest` từng chunk trong lúc đọc, tránh đọc toàn bộ vào heap.
- Khi download nhiều file, không để task thất bại giữ temp files hoặc streams mở.

Một mẫu streaming hash, **mảnh code**:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
try (InputStream in = c.getInputStream()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        digest.update(buffer, 0, n);
    }
}
byte[] hash = digest.digest();
```

Cần import `java.security.MessageDigest`, `java.io.InputStream` và cung cấp `HttpURLConnection c` đã xác nhận status. Hash SHA-256 giúp so sánh integrity với **digest tin cậy** lấy từ kênh độc lập; **hash do cùng server không đáng tin cung cấp** không tự chứng minh authenticity.

## 24. Khi nào nên chọn Java 17 HttpClient thay vì URLConnection?

`URLConnection/HttpURLConnection` là API lâu đời, phù hợp khi:
- Đọc một URL đơn giản hoặc legacy code đã dựa trên API này.
- Cần thao tác với nhiều protocol handlers như `file:` trong cùng interface.
- Muốn hiểu rõ kết nối, headers, stream và lifecycle.
- Không cần pipeline bất đồng bộ hay HTTP/2 features hiện đại.

`java.net.http.HttpClient` (Java 11+) phù hợp khi:
- Cần gửi HTTP request đồng bộ/bất đồng bộ với `send`/`sendAsync`.
- Cần HTTP/2 khi endpoint hỗ trợ.
- Muốn API `HttpRequest`/`HttpResponse` và `BodyHandler` rõ ràng.
- Cần composition với `CompletableFuture`, nhiều requests và deadline policies.

```java
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/resource")).GET().build();
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());
try (InputStream body = response.body()) {
    // consume stream; không bỏ nghĩa vụ close
}
```

Đây là mảnh code, cần import `java.net.URI`, `java.net.http.*`, `java.io.InputStream` và xử lý checked exceptions. **HttpClient không tự khiến nghĩa vụ đóng streaming body biến mất**; `BodyHandlers.ofInputStream()` trả body dạng stream mà caller vẫn phải đọc/đóng.

Bài này tập trung vào `URLConnection`, không biến thành hướng dẫn HttpClient đầy đủ. Cần lưu ý hai API có chính sách redirect/timeout/resource khác nhau; đừng suy một behavior từ API này sang API kia.

## 25. Kiểm thử theo tình huống và bất biến tài nguyên

Các test nên có:

| Tình huống | Kỳ vọng |
| --- | --- |
| HTTP 200, Content-Type và Content-Length hợp lệ | Đọc metadata đúng, body byte count đúng |
| HTTP 200 thiếu Content-Length/chunked | `getContentLengthLong() == -1` và vẫn đọc stream tới EOF |
| HTTP 404 với error body | `getResponseCode()==404`, xử lý `getErrorStream()` có thể đọc được |
| HTTP 404 không có body | `getErrorStream()` có thể null; code không NPE |
| Server close sớm | Không coi partial data là thành công nếu protocol yêu cầu độ dài hoàn chỉnh |
| Server chậm không gửi byte | Read timeout phát sinh, close stream/connection |
| Header Content-Length quá max | Từ chối sớm, không cấp phát theo header |
| Không có Content-Length, body vượt max | Vòng read vẫn chặn và dọn temp |
| File URL tồn tại | InputStream đọc đúng, đóng trước khi xóa file tạm |
| File URL không tồn tại | Exception xử lý đúng, không để resource leak |
| Charset UTF-8 có ký tự nhiều byte | Decode đúng bytes sau khi nhận đầy đủ |
| Content-Encoding gzip | Giải nén phù hợp rồi decode charset |
| Redirect cross-host | Không tự gửi secrets tới host không allowlist |
| Nhiều request liên tiếp | Mỗi HttpURLConnection dùng một request instance, mọi stream đều close |
| Tải file rồi lỗi ghi disk | Temp file được xóa, không publish file dở |
| Đọc xong nhưng close ném IOException | Không báo thành công sai, xử lý suppressed errors |
| URL do user nhập có file/internal IP | Reject theo scheme/host/egress policy |
| Metadata Date/Last-Modified vắng | Code xử lý sentinel `0` hoặc `null` |

Dùng server loopback có port `0` giúp kiểm soát output không phụ thuộc dịch vụ công khai. Để test close, có thể dùng stream wrapper ghi nhận số lần `close()` được gọi; để test timeout, server cố tình không gửi response cho tới khi deadline hết. Không dùng `Thread.sleep()` vô cớ làm kết quả phụ thuộc scheduler nếu có thể dùng latch/barrier.

## 26. Những hiểu lầm phổ biến

1. **“`openConnection()` tải luôn body.”** Không; thường chỉ tạo connection object, thao tác I/O có thể lazy.
2. **“Có thể set request header sau `getInputStream()`.”** Thường quá muộn vì connection đã thực hiện I/O.
3. **“`getContentLengthLong() == -1` nghĩa body rỗng.”** Không, length không được biết.
4. **“Content-Length là số ký tự Java String.”** Không; nó là thông tin byte length theo HTTP representation/framing.
5. **“Content-Type luôn đúng.”** Không; header do server công bố, có thể thiếu/sai.
6. **“Read stream một lần là lấy hết body.”** Không; `read` có thể trả một phần; phải loop.
7. **“`HttpURLConnection.getInputStream()` luôn đọc cả 404 JSON.”** Không; lỗi có thể cần `getErrorStream()`.
8. **“`getErrorStream()` luôn trả non-null.”** Không; nó có thể null và không tự connect.
9. **“Đóng connection bằng `disconnect()` là đủ.”** Không thay nghĩa vụ close stream và cleanup.
10. **“HttpURLConnection implement AutoCloseable.”** Không; đặt try-with-resources cho input/output streams.
11. **“Mọi URLConnection đều có `getResponseCode()`.”** Không; đó là HTTP-specific API.
12. **“`file:` URLConnection phải gọi `disconnect()`.”** Không có phương thức chung này; close file stream.
13. **“Chunked body cần tự parse `\r\n` chunk frame.”** Không khi đã dùng HTTP InputStream do HttpURLConnection trả.
14. **“Content-Encoding gzip và charset=UTF-8 giống nhau.”** Không; gzip là compression, UTF-8 là text decoding.
15. **“HEAD response luôn phản ánh chính xác GET sau đó.”** Không; metadata có thể đổi, server có thể không hỗ trợ HEAD đúng.
16. **“`getLastModified()==0` là file bị sửa vào epoch.”** API dùng 0 khi không biết.
17. **“URLConnection metadata là nguồn bảo mật đáng tin.”** Không; cần validate origin, certificate và integrity/authorization.
18. **“`readAllBytes()` trên Internet an toàn vì có Content-Length.”** Không; body có thể không giới hạn hoặc header sai.
19. **“HttpURLConnection auto redirect mặc định giống HttpClient.”** Không; hai API có defaults khác nhau.
20. **“Một HttpURLConnection có thể reuse cho nhiều requests.”** Mỗi instance là một request; underlying TCP pooling không đổi điều đó.
21. **“Tải dở nhưng đã tạo file thì có thể đưa ra cho consumer.”** Không; cần verify, close, publish atomic khi phù hợp.
22. **“Có HTTPS thì URL từ user không thể SSRF.”** Không; redirect/destination network vẫn cần policy.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `getContentLengthLong()` tốt hơn `getContentLength()` khi đọc tài nguyên lớn?  
**Đáp án:** Dùng `long` nên biểu diễn được độ dài hơn giới hạn `int`; cả hai vẫn có thể báo unknown.

**Câu 2.** HTTP response chunked có `getContentLengthLong() == -1` thì làm sao lấy body?  
**Đáp án:** Đọc `getInputStream()` tới EOF (với size/time limit); HTTP protocol handler xử lý transfer framing.

**Câu 3.** `getContentType()` trả `text/plain; charset=UTF-8`. Có thể dùng `new String(bytes, UTF_8)` luôn không?  
**Đáp án:** Chỉ sau khi đã xử lý đúng content encoding và xác nhận content type/charset hợp lệ cho protocol; server header có thể thiếu/sai.

**Câu 4.** Khi nào gọi `setConnectTimeout`/`setReadTimeout`?  
**Đáp án:** Sau `openConnection` nhưng trước mọi thao tác có thể connect/read.

**Câu 5.** HTTP trả `404` và có HTML error body. Vì sao `getInputStream` có thể không đọc được?  
**Đáp án:** `HttpURLConnection` phân biệt response lỗi; `getInputStream` có thể ném IOException, dùng `getResponseCode` và `getErrorStream` nếu có.

**Câu 6.** `getErrorStream()` trả null có nghĩa server không tồn tại?  
**Đáp án:** Không; null có thể vì chưa kết nối, không có error data hoặc không phải error response.

**Câu 7.** Có nên gọi `disconnect()` mà không đóng `InputStream`?  
**Đáp án:** Không; đóng stream rõ ràng bằng try-with-resources, rồi disconnect theo lifecycle.

**Câu 8.** Vì sao không dùng `try (HttpURLConnection c = ...)`?  
**Đáp án:** `HttpURLConnection` không phải `AutoCloseable`, nhưng InputStream/OutputStream là Closeable.

**Câu 9.** Một file được tải theo chunks vượt giới hạn khi Content-Length thiếu. Kiểm tra ở đâu?  
**Đáp án:** Trong vòng read, theo bytes thật cộng dồn; dừng trước khi ghi vượt quota và xóa file tạm.

**Câu 10.** Sự khác nhau giữa Content-Encoding và charset là gì?  
**Đáp án:** Content-Encoding là cách biểu diễn/nén bytes (ví dụ gzip), charset là quy tắc chuyển bytes thành characters (ví dụ UTF-8).

**Câu 11.** `HEAD` có thay thế kiểm tra size của `GET` không?  
**Đáp án:** Không; HEAD metadata có thể thiếu/thay đổi, còn body GET vẫn phải được kiểm tra giới hạn thực.

**Câu 12.** `URLConnection` chung có `disconnect()` không?  
**Đáp án:** Không; đây là API của `HttpURLConnection`. Với file URL, close InputStream.

**Câu 13.** Tại sao `HttpURLConnection` mỗi instance chỉ dùng cho một request dù TCP connection có thể keep-alive?  
**Đáp án:** Request state ở instance; underlying socket pooling là một lớp riêng được HTTP handler quản lý.

**Câu 14.** Khi user cung cấp URL `file:` hoặc redirect sang 127.0.0.1, cần làm gì?  
**Đáp án:** Kiểm tra scheme/destination/allowlist và network/file policy; không dùng openStream trực tiếp trên URL không đáng tin.

**Câu 15.** Stream đã đọc đủ nhưng ghi file lỗi giữa chừng, có nên giữ file đích?  
**Đáp án:** Không công bố file không hoàn chỉnh; cleanup temp, xử lý lỗi và chỉ publish khi ghi/verify thành công.

## 28. Checklist triển khai

**Trước khi đọc:**
- Xác nhận URL scheme, hostname/path/port và policy cho phép.
- Tạo mới URLConnection cho logical request, không tái dùng instance HTTP cũ.
- Đặt connect/read timeout, headers, cache và redirects **trước I/O**.
- Với HTTP, kiểm tra status code, tránh auto-follow URL không đáng tin.

**Trong khi đọc metadata và stream:**
- Xử lý `Content-Type` null, `Content-Length` -1, date metadata thiếu.
- Giải quyết HTTP success/error stream riêng, kiểm tra null ở error stream.
- Decode text bằng charset phù hợp; tách content encoding khỏi charset.
- Đọc trong vòng lặp và xử lý đúng n bytes, không phụ thuộc một read.
- Giới hạn bytes thật nhận được, total deadline và concurrency.
- Không dùng header remote làm authority quyết định security policy.

**Khi kết thúc:**
- Đóng mọi InputStream/OutputStream bằng try-with-resources.
- Với HTTP, dùng `finally` gọi `disconnect()` nếu hợp lý; không xem nó là thay thế close.
- Xóa file tạm khi lỗi/quota exceeded, chỉ publish file sau verify.
- Log status/metadata đã sanitize; không ghi credentials, cookies, signed URLs.
- Test 200, 404, unknown length, oversized body, connection timeout, failure cleanup.

**Ghi nhớ:** URLConnection cung cấp **metadata + stream**, nhưng API không tự thực hiện toàn bộ trách nhiệm **validation, giới hạn tải và đóng tài nguyên** thay ứng dụng. Thiết kế đúng phải giữ rõ **thứ tự cấu hình/kết nối/đọc/đóng**, xử lý metadata thiếu và bảo đảm mọi path thành công hoặc thất bại đều giải phóng tài nguyên.

## 29. Tài liệu tham khảo

- Java SE 17 `URLConnection` — lifecycle, metadata methods, streams, timeouts và close: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html
- Java SE 17 `HttpURLConnection` — status code, getErrorStream, redirect policy và disconnect: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html
- Java SE 17 `HttpsURLConnection` — HTTPS-specific behaviors: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html
- Java SE 17 `URL` — openConnection/openStream: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html
- Java SE 17 `InputStream` — read, readAllBytes, readNBytes và close: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html
- Java SE 17 `Files` — temporary files, streams và move: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17 `HttpServer` — local HTTP test server: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Java SE 17 `HttpResponse.BodyHandlers` — streaming alternatives trên HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- RFC 9110 — HTTP Semantics (media type, Content-Length, validators, HEAD, status codes): https://www.rfc-editor.org/rfc/rfc9110
- RFC 9112 — HTTP/1.1 message framing, Transfer-Encoding: https://www.rfc-editor.org/rfc/rfc9112
