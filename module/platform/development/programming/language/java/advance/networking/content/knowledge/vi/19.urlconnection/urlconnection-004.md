# HttpURLConnection: method, mã trạng thái và error stream

*Java Advance – networking · Nhóm URLConnection · Dùng Java 17+*

## 1. Điều cốt lõi cần nắm

`java.net.HttpURLConnection` là API HTTP truyền thống trong JDK, kế thừa `java.net.URLConnection`. Nó giúp tạo HTTP request, đặt method và headers, đọc HTTP status code, đọc response body, đồng thời cung cấp `getErrorStream()` cho **nội dung phản hồi lỗi mà server gửi**.

**Sai lầm rất phổ biến:** gọi `getInputStream()` cho mọi response, gặp HTTP 404/500 thì `IOException`, rồi kết luận rằng server **không gửi body**. Trên thực tế server có thể gửi một JSON/HTML chứa thông tin lỗi. Trong `HttpURLConnection`, body của HTTP error response thường được truy cập qua **`getErrorStream()`**, không phải `getInputStream()`.

Ba câu hỏi phải được xử lý **riêng**:

1. **HTTP method:** ứng dụng gửi `GET`, `POST`, `PUT`, `DELETE`, `HEAD`… gì? Có request body không?
2. **HTTP status:** server đã trả `200`, `201`, `204`, `302`, `400`, `404`, `500`… hay chưa? `getResponseCode()` có đọc được status không?
3. **Response body stream:** nếu thành công, đọc `getInputStream()`; nếu HTTP lỗi, kiểm tra `getErrorStream()`, **có thể là `null`**; nếu gặp lỗi mạng trước HTTP response, có thể **không có status lẫn body**.

~~~text
             URL.openConnection()
                     |
                     v
              HttpURLConnection
                     |
      set method / headers / timeouts
      setDoOutput / write request body
                     |
                     v
        connect / getOutputStream /
            getResponseCode
                     |
             HTTP response?
            /               \
           v                 v
   Có status code        Lỗi DNS/TCP/TLS/
   ví dụ 200/404          timeout trước headers
           |                 |
           v                 +--> IOException
   getResponseCode               thường không có status
           |                      hoặc error body
      +----+----+
      |         |
  2xx / ok     >=400
      |         |
getInputStream  getErrorStream()
      |         |  (có thể null)
      +----+----+
           |
  consume/close stream
           |
       disconnect()
~~~

Đây là sơ đồ **quy trình thường gặp**, không phải quy tắc tất cả HTTP 3xx luôn có body thành công hoặc tất cả status >=400 luôn có error body. Cần kiểm tra chính sách redirect và protocol cho từng trường hợp.

## 2. URLConnection và HttpURLConnection khác nhau

| Thành phần | Vai trò |
|---|---|
| `URL` / `URI` | Biểu diễn địa chỉ tài nguyên |
| `URL.openConnection()` | Tạo object `URLConnection`, chưa mặc định chứng minh đã kết nối mạng |
| `URLConnection` | Base API cho connection, request properties, timeouts, input/output |
| `HttpURLConnection` | HTTP-specific API: method, status, redirect, error stream, streaming request body |
| `HttpsURLConnection` | Subclass cho HTTPS, thêm APIs SSL/TLS liên quan |
| `java.net.http.HttpClient` | HTTP client hiện đại (Java 11+), API khác: `HttpRequest`, `HttpResponse`, `BodyHandlers`, hỗ trợ HTTP/2 |

~~~java
// Trích đoạn GET; chỉ nên cast khi biết URL dùng HTTP/HTTPS.
URL url = URI.create("http://127.0.0.1:8080/status").toURL();
URLConnection base = url.openConnection();
if (!(base instanceof HttpURLConnection conn)) {
    throw new IllegalArgumentException("Not an HTTP URL");
}
conn.setRequestMethod("GET");
~~~

`HttpURLConnection` được thiết kế cho **một logical HTTP request trên mỗi instance**, nhưng underlying HTTP persistent connection có thể được tái sử dụng giữa nhiều instance. **Không tạo một object rồi thay method để thực hiện request thứ hai trên cùng object**. Thay vào đó, tạo instance mới cho request khác.

Ví dụ trong bài dùng `HttpServer` trên loopback nên không cần Internet hoặc proxy. Khi sử dụng `https://`, implementer thường trả `HttpsURLConnection` và TLS phải được kiểm tra certificate/hostname đúng cách.

## 3. Vòng đời: cấu hình trước khi kết nối

Theo Javadoc `URLConnection`, quá trình điển hình:

1. Tạo connection object bằng `URL.openConnection()`.
2. Cấu hình `setRequestMethod`, `setRequestProperty`, `setDoOutput`, `setConnectTimeout`, `setReadTimeout`, redirect policy và streaming mode.
3. Kết nối được mở **khi một lời gọi yêu cầu I/O** như `connect()`, `getOutputStream()`, `getInputStream()` hoặc `getResponseCode()` cần kết nối.
4. Đọc status, response headers và body.
5. Đóng các streams và `disconnect()` trong `finally`.

~~~text
CREATED
  |
  +-- setRequestMethod(...)
  +-- setRequestProperty(...)
  +-- setConnectTimeout(...) / setReadTimeout(...)
  +-- setInstanceFollowRedirects(...)
  +-- setDoOutput(...) / setFixedLengthStreamingMode(...)
  |
  v
CONNECTED (implicit or explicit)
  |
  +-- getResponseCode() / getResponseMessage()
  +-- getHeaderField(...)
  +-- getInputStream() or getErrorStream()
  |
  v
CONSUMED / CLOSED / DISCONNECTED
~~~

Nhiều setter **không được gọi sau khi connection đã established**: tùy setter có thể ném `IllegalStateException`, `ProtocolException` hoặc không còn tác dụng theo contract. Do đó cấu hình **tất cả trước I/O**. Đặc biệt, `setRequestMethod(...)` không phải API để đổi method trên một request đã gửi.

**`connect()` không bắt buộc luôn phải gọi tường minh**. Các phương thức I/O sẽ chủ động mở connection nếu cần. Lệnh `openConnection()` chỉ tạo object và **không đồng nghĩa server đã nhận request**.

## 4. HTTP method và setRequestMethod

### 4.1. Method mặc định và danh sách API chấp nhận

`HttpURLConnection` có method mặc định **GET**. Java SE 17 `setRequestMethod(String)` hỗ trợ những method sau, phụ thuộc protocol restrictions:

| Method | Tính chất phổ biến | Lưu ý |
|---|---|---|
| `GET` | Đọc tài nguyên | Thường không gửi request body |
| `POST` | Gửi dữ liệu/tạo hành động | Dùng `setDoOutput(true)` và `getOutputStream()` khi có body |
| `HEAD` | Giống GET về metadata, không có response body | Đừng cố đọc nội dung body |
| `OPTIONS` | Hỏi thông tin lựa chọn/giao thức | Hạn chế thực thi tùy server |
| `PUT` | Đặt/thay thế tài nguyên | Có thể gửi body |
| `DELETE` | Yêu cầu xóa tài nguyên | Không suy ra đã xóa thành công nếu chưa xem status |
| `TRACE` | Diagnostic trace | Thường bị tắt vì security policy |
| `PATCH` | Method HTTP hợp lệ theo chuẩn hiện đại | **Không nằm trong danh sách setRequestMethod của Java 17 HttpURLConnection**, thường ném `ProtocolException` |

**Quan trọng:** HTTP protocol có thể hỗ trợ nhiều method hơn class `HttpURLConnection`. Java 17 legacy API **không nhận PATCH thông qua `setRequestMethod("PATCH")`** theo danh sách chính thức. Khi cần PATCH, custom method hoặc API hiện đại, nên dùng:

~~~java
// Trích đoạn Java 17; cần import HttpClient, HttpRequest, URI.
HttpRequest patch = HttpRequest.newBuilder(
        URI.create("https://api.example.test/items/7"))
    .method("PATCH", HttpRequest.BodyPublishers.ofString(
            "{\"name\":\"new\"}"))
    .header("Content-Type", "application/json")
    .build();
~~~

Đây là trích đoạn **chưa gửi request thật**. `java.net.http.HttpRequest.Builder.method` chấp nhận method tùy chỉnh phù hợp contract. Đừng dùng reflection/hack đổi field `method` nội bộ của `HttpURLConnection` để “ép PATCH”, vì dễ lỗi với JDK mới và không có tính portable.

### 4.2. setRequestMethod phải gọi trước khi kết nối

~~~java
// Trích đoạn, c là HttpURLConnection vừa tạo và chưa connected.
c.setRequestMethod("GET");
c.setRequestProperty("Accept", "application/json");
c.setConnectTimeout(3000);
c.setReadTimeout(3000);
int status = c.getResponseCode(); // Có thể khởi tạo I/O.
~~~

Sau khi đã đọc status hoặc body, không dùng lại `c.setRequestMethod("POST")` để biến thành request thứ hai. **Một instance – một request**; tạo connection mới.

`getRequestMethod()` trả tên method đã đặt, không phải bằng chứng server đã xử lý logic tương ứng. Muốn biết server có chấp nhận method hay không, xem `getResponseCode()`, ví dụ `405 Method Not Allowed`, `501 Not Implemented` hoặc status theo API.

## 5. Gửi POST body: setDoOutput và getOutputStream

Một POST có body thường thực hiện:

~~~java
// Trích đoạn, c vừa open, còn chưa connected.
byte[] payload = "ping".getBytes(StandardCharsets.UTF_8);
c.setRequestMethod("POST");
c.setDoOutput(true);
c.setRequestProperty("Content-Type", "text/plain; charset=UTF-8");
c.setFixedLengthStreamingMode(payload.length);
try (OutputStream output = c.getOutputStream()) {
    output.write(payload);
}
int status = c.getResponseCode();
~~~

**Lưu ý cần thuộc:**

- `setDoOutput(true)` bật quyền ghi request body; mặc định `URLConnection.doOutput` là **false**.
- **Nên gọi `setRequestMethod("POST")` tường minh**. Một số implementation legacy có hành vi đổi default GET sang POST khi request output, nhưng dựa vào side effect ấy là không rõ ràng, không nên dùng làm giao diện lập trình.
- `Content-Type` mô tả representation (`application/json`, `text/plain`…), không có nghĩa body đã đúng schema.
- `payload.length` là **số byte**, không phải `String.length()` đếm UTF-16 code unit. Với tiếng Việt/emoji, hai giá trị có thể khác đáng kể.
- `getOutputStream()` có thể **kích hoạt kết nối**. Phải hoàn tất cấu hình method, headers, timeouts và streaming mode **trước** lời gọi này.
- Đóng `OutputStream` giúp hoàn tất phần ghi request body theo contract; sau đó mới đọc status/response body.

### 5.1. Fixed-length và chunked streaming mode

`HttpURLConnection` có:

| API | Khi nào dùng? | Cạm bẫy |
|---|---|---|
| `setFixedLengthStreamingMode(int)` | Biết chính xác số byte request body, kích thước vừa kiểu int | Viết thiếu/thừa lượng byte đã khai báo sẽ lỗi |
| `setFixedLengthStreamingMode(long)` | Biết độ dài lớn, tránh giới hạn int | Độ dài phải chính xác theo byte |
| `setChunkedStreamingMode(int)` | Chưa biết độ dài body hoặc muốn streaming | Một số server/proxy không chấp nhận request chunked |
| Không bật streaming mode | Implementation có thể buffer request body trước khi gửi | Có thể tốn nhiều memory, không thích hợp payload lớn |

**Javadoc Java 17 cảnh báo:** khi output streaming mode đã bật, **authentication và redirection không thể được xử lý tự động** như trong chế độ buffering; nếu cần chúng, việc đọc response có thể ném `HttpRetryException`. Đây **không phải** một HTTP 4xx body thông thường và cần xử lý theo hợp đồng API. Không retry mù quáng POST vì server có thể đã nhận một phần hoặc toàn bộ body.

`setFixedLengthStreamingMode` và `setChunkedStreamingMode` cần được gọi **trước khi kết nối**. Nếu ứng dụng vừa đặt fixed-length vừa đặt chunked mode, có thể gặp `IllegalStateException`.

## 6. Mã trạng thái: getResponseCode và getResponseMessage

### 6.1. getResponseCode là tín hiệu chính

~~~java
int code = c.getResponseCode();
~~~

Javadoc `HttpURLConnection`: `getResponseCode()` trả status code từ HTTP response; ví dụ `200`, `401`, `404`, `500`. **Có thể trả `-1` nếu không phân tích được status hợp lệ**, và có thể ném `IOException` nếu lỗi khi kết nối/nhận response.

**Đừng dùng `getInputStream()` để đoán status.** Hãy lấy `code`, phân loại status, rồi quyết định dùng stream nào. Status HTTP lỗi và `IOException` do mạng là **hai loại sự kiện khác nhau**.

### 6.2. getResponseMessage chỉ là thông tin phụ

~~~java
int code = c.getResponseCode();
String reason = c.getResponseMessage();  // "OK", "Not Found" hoặc null.
~~~

`getResponseMessage()` cung cấp reason phrase **nếu có thể phân tích được**, có thể trả `null`. Không dùng nội dung reason phrase để phân nhánh business logic: server/proxy có thể thay wording hoặc language, và các HTTP version hiện đại không có reason phrase theo cách HTTP/1.1 truyền thống.

**Dùng integer status code**, không dùng `reason.equals("OK")`.

### 6.3. Các nhóm HTTP status

| Nhóm | Ví dụ | Cách hiểu |
|---|---|---|
| **1xx** | `100 Continue`, `101 Switching Protocols` | Thông tin về giao thức/tiến trình; không coi mọi 1xx là final response |
| **2xx** | `200 OK`, `201 Created`, `202 Accepted`, `204 No Content` | Request thành công theo semantics HTTP; cần xem body rules |
| **3xx** | `301`, `302`, `303`, `307`, `308`, `304` | Redirect/caching; đừng cho mọi 3xx vào error stream |
| **4xx** | `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `429 Too Many Requests` | Client/application request error, có thể có body chứa chi tiết |
| **5xx** | `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable` | Server/proxy error, có thể có body và Retry-After |

**`404` hoặc `500` không có nghĩa socket bị lỗi.** Đây là **response HTTP hợp lệ về mặt giao thức** với status cho biết request không thành công ở tầng ứng dụng hoặc server.

### 6.4. Một số status không có response body

- `204 No Content`: response thành công nhưng **không có body**.
- `304 Not Modified`: caching semantics; **không phải response body mới**.
- `HEAD` request: response chỉ có metadata tương ứng, **không có message body**.
- `202 Accepted`: server đã nhận yêu cầu xử lý theo semantics, **không bảo đảm tác vụ đã hoàn tất nghiệp vụ**.

Đừng gọi `getErrorStream()` chỉ vì không có body ở 204/304. Cũng đừng mặc định `getInputStream()` luôn đọc được text vì status là 2xx; 204 có thể cho stream rỗng, và một số status/semantics không có payload.

## 7. getInputStream và getErrorStream: chọn đúng nguồn body

### 7.1. Nhận body thành công

~~~java
int status = c.getResponseCode();
if (status >= 200 && status < 300) {
    try (InputStream in = c.getInputStream()) {
        // Đọc body nếu status/method cho phép có nội dung.
    }
}
~~~

`getInputStream()` từ `URLConnection` trả stream đọc response body; stream có thể block khi chờ dữ liệu và có thể ném `IOException`. Thường dùng cho response 2xx có body.

**Không bảo đảm mọi status dưới 400 đều hợp lệ để đọc như thành công.** Với 3xx, một số implementation cho đọc body của redirect, nhưng cách xử lý đúng phụ thuộc redirect policy và status. Với 204/HEAD không có body theo HTTP semantics.

### 7.2. Nhận body lỗi

~~~java
int status = c.getResponseCode();
if (status >= 400) {
    InputStream error = c.getErrorStream();
    if (error != null) {
        try (InputStream in = error) {
            byte[] bytes = in.readAllBytes();
            // Giải mã/parse có giới hạn theo Content-Type và nhu cầu.
        }
    }
}
~~~

`getErrorStream()` là **stream chứa response error body khi server có gửi dữ liệu hữu ích**. Nó **không trả exception object**; không tự đóng; có thể là `null`. Tài liệu Java 17 nêu ví dụ 404 thường làm `getInputStream()` ném `FileNotFoundException`, trong khi server vẫn có một trang HTML lỗi để đọc qua `getErrorStream()`.

**Hai quy tắc rất quan trọng:**

1. `getErrorStream()` **không tự khởi tạo connection**. Nếu gọi khi chưa connected, thường nhận `null` dù server **sẽ trả lỗi về sau**.
2. Ngay cả khi status là 404/500, **`getErrorStream()` vẫn có thể là `null`** nếu server không gửi error data hoặc connection chưa tới tình trạng có stream. Phải kiểm tra null, không làm `c.getErrorStream().readAllBytes()` trực tiếp.

### 7.3. Vì sao không dựa vào getInputStream cho mọi status?

Với một GET tới endpoint không tồn tại:

~~~text
Server:
HTTP/1.1 404 Not Found
Content-Type: application/json

{"error":"item_not_found"}

Client HttpURLConnection:
getResponseCode() -> 404
getInputStream()  -> có thể ném IOException / FileNotFoundException
getErrorStream()  -> stream JSON lỗi (nếu body đã sẵn)
~~~

Nếu ứng dụng làm như sau sẽ dễ mất thông tin:

~~~java
// SAI về handling: có thể bỏ mất response error body.
try (InputStream in = c.getInputStream()) {
    parseJson(in);
} catch (IOException ex) {
    log(ex.getMessage());
}
~~~

Mẫu hợp lý là **đọc status trước, chọn response stream, đóng stream, và phân biệt HTTP error với transport error**.

## 8. Một mẫu xử lý response có nhánh success/error rõ ràng

~~~java
// Trích đoạn: c đã được cấu hình method, headers, timeout.
// Không phải chương trình độc lập: readLimited là hàm application tự viết.
try {
    int status = c.getResponseCode();
    InputStream body = status >= 400
            ? c.getErrorStream()
            : c.getInputStream();

    if (body != null) {
        try (InputStream in = body) {
            byte[] bytes = readLimited(in, 1024 * 1024);
            // Chỉ parse và lưu những dữ liệu được policy cho phép.
        }
    }

    if (status < 200 || status >= 300) {
        // Phân loại status 3xx/4xx/5xx; không coi là business success.
    }
} finally {
    c.disconnect();
}
~~~

**Giới hạn mẫu:** 3xx có thể là redirect/304 với quy tắc body đặc biệt; trong chương trình thực tế nên xử lý 3xx riêng. `getInputStream()` trong một số trường hợp có thể ném IOException không phải vì 4xx; phải có đường catch/log lỗi transport ngoài đoạn này nếu cần. `readLimited` chưa được định nghĩa ở đây nên mã này là **trích đoạn minh họa**, không chạy độc lập.

Mẫu thực tế cho API JSON nên phân loại:

~~~text
getResponseCode
  ├── 2xx -> status success -> đọc body nếu có -> parse/validate
  ├── 3xx -> redirect/cache policy -> kiểm tra Location
  ├── 4xx -> có thể đọc error stream -> phân loại lỗi client
  ├── 5xx -> có thể đọc error stream -> phân loại lỗi server
  └── IOException trước status -> lỗi DNS/connect/TLS/timeout
~~~

Không nên viết `if (status == 200) success else networkError`: 201/204 có thể thành công; 404/500 là HTTP responses; còn IOException có thể xảy ra ở tầng I/O.

## 9. Ví dụ Java 17+ chạy hoàn chỉnh trên loopback

Chương trình sau dùng `com.sun.net.httpserver.HttpServer` (module có sẵn trong JDK: `jdk.httpserver`) tạo HTTP server tại **127.0.0.1 trên cổng động**. Không cần Internet và không sử dụng credential thật.

Nó mô phỏng:

1. **GET /ok** trả `200 READY`.
2. **POST /create** nhận request body `ping` rồi trả `201 CREATED:ping`.
3. **GET /missing** trả `404 NOT_FOUND`; chứng minh error stream **null trước khi connect**, `getInputStream()` ném IOException ở runtime thử nghiệm, nhưng `getErrorStream()` vẫn đọc được nội dung lỗi.
4. **GET /fail** trả `500 SERVER_ERROR`, đọc qua error stream.
5. **GET /empty** trả `204`, không có body và error stream null.
6. **GET /redirect** trả `302 Location: /ok`; client tắt follow redirect để nhìn thấy status và header gốc.
7. **PATCH** bị `setRequestMethod` từ chối bằng `ProtocolException` trong Java 17, dù HTTP protocol có PATCH.

**File: `HttpUrlConnectionDemo.java`**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ProtocolException;
import java.net.URI;
import java.nio.charset.StandardCharsets;

public class HttpUrlConnectionDemo {
    private static void reply(HttpExchange ex, int status, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "text/plain; charset=UTF-8");
        if (status == 302) {
            ex.getResponseHeaders().set("Location", "/ok");
        }
        if (status == 204 || status == 302) {
            ex.sendResponseHeaders(status, -1);
            ex.close();
            return;
        }
        ex.sendResponseHeaders(status, data.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(data);
        }
    }

    private static HttpURLConnection open(URI base, String path, String method)
            throws Exception {
        HttpURLConnection conn = (HttpURLConnection)
                base.resolve(path).toURL().openConnection();
        conn.setConnectTimeout(3000);
        conn.setReadTimeout(3000);
        conn.setInstanceFollowRedirects(false);
        conn.setRequestMethod(method);
        return conn;
    }

    private static String read(InputStream in) throws IOException {
        if (in == null) return "<none>";
        try (in) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/ok", ex -> reply(ex, 200, "READY"));
        server.createContext("/create", ex -> {
            String input = new String(ex.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8);
            reply(ex, 201, "CREATED:" + input);
        });
        server.createContext("/missing", ex -> reply(ex, 404, "NOT_FOUND"));
        server.createContext("/fail", ex -> reply(ex, 500, "SERVER_ERROR"));
        server.createContext("/empty", ex -> reply(ex, 204, ""));
        server.createContext("/redirect", ex -> reply(ex, 302, ""));
        server.start();
        try {
            URI base = new URI("http", null, "127.0.0.1",
                    server.getAddress().getPort(), "/", null, null);

            HttpURLConnection get = open(base, "ok", "GET");
            try {
                int code = get.getResponseCode();
                System.out.println("GET status=" + code
                        + " body=" + read(get.getInputStream())
                        + " method=" + get.getRequestMethod());
            } finally {
                get.disconnect();
            }

            HttpURLConnection post = open(base, "create", "POST");
            try {
                byte[] payload = "ping".getBytes(StandardCharsets.UTF_8);
                post.setDoOutput(true);
                post.setRequestProperty("Content-Type",
                        "text/plain; charset=UTF-8");
                post.setFixedLengthStreamingMode(payload.length);
                try (OutputStream out = post.getOutputStream()) {
                    out.write(payload);
                }
                int code = post.getResponseCode();
                System.out.println("POST status=" + code
                        + " body=" + read(post.getInputStream())
                        + " method=" + post.getRequestMethod());
            } finally {
                post.disconnect();
            }

            HttpURLConnection missing = open(base, "missing", "GET");
            try {
                boolean wasNull = missing.getErrorStream() == null;
                int code = missing.getResponseCode();
                boolean inputThrew = false;
                try (InputStream ignored = missing.getInputStream()) {
                    ignored.readAllBytes();
                } catch (IOException expected) {
                    inputThrew = true;
                }
                System.out.println("404 status=" + code
                        + " error=" + read(missing.getErrorStream()));
                System.out.println("404 errorBeforeConnectNull=" + wasNull
                        + " inputStreamThrows=" + inputThrew);
            } finally {
                missing.disconnect();
            }

            HttpURLConnection fail = open(base, "fail", "GET");
            try {
                System.out.println("500 status=" + fail.getResponseCode()
                        + " error=" + read(fail.getErrorStream()));
            } finally {
                fail.disconnect();
            }

            HttpURLConnection empty = open(base, "empty", "GET");
            try {
                int code = empty.getResponseCode();
                boolean errorNull = empty.getErrorStream() == null;
                int count;
                try (InputStream in = empty.getInputStream()) {
                    count = in.readAllBytes().length;
                }
                System.out.println("204 status=" + code
                        + " errorStreamNull=" + errorNull
                        + " bodyBytes=" + count);
            } finally {
                empty.disconnect();
            }

            HttpURLConnection redirect = open(base, "redirect", "GET");
            try {
                System.out.println("302 status=" + redirect.getResponseCode()
                        + " location=" + redirect.getHeaderField("Location")
                        + " autoRedirect="
                        + redirect.getInstanceFollowRedirects());
            } finally {
                redirect.disconnect();
            }

            HttpURLConnection invalid = open(base, "ok", "GET");
            try {
                boolean rejected = false;
                try {
                    invalid.setRequestMethod("PATCH");
                } catch (ProtocolException expected) {
                    rejected = true;
                }
                System.out.println("PATCH rejected=" + rejected);
            } finally {
                invalid.disconnect();
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch và chạy trên **JDK 17+**. Vì demo dùng `HttpServer`, cung cấp module `jdk.httpserver`:

~~~bash
javac --release 17 --add-modules jdk.httpserver HttpUrlConnectionDemo.java
java --add-modules jdk.httpserver HttpUrlConnectionDemo
~~~

**Stdout đã kiểm chứng khi biên dịch `--release 17` và chạy trên OpenJDK 24:**

~~~text
GET status=200 body=READY method=GET
POST status=201 body=CREATED:ping method=POST
404 status=404 error=NOT_FOUND
404 errorBeforeConnectNull=true inputStreamThrows=true
500 status=500 error=SERVER_ERROR
204 status=204 errorStreamNull=true bodyBytes=0
302 status=302 location=/ok autoRedirect=false
PATCH rejected=true
~~~

### 9.1. Phân tích output

| Dòng output | Điều chứng minh |
|---|---|
| `GET status=200 body=READY method=GET` | GET thành công, body lấy từ `getInputStream()` |
| `POST status=201 body=CREATED:ping method=POST` | POST có body được server đọc, response 201 được lấy bằng input stream |
| `404 status=404 error=NOT_FOUND` | HTTP 404 **có body lỗi**, đọc bằng `getErrorStream()` |
| `404 errorBeforeConnectNull=true inputStreamThrows=true` | `getErrorStream` không tự kết nối; `getInputStream` có thể ném IOException cho HTTP 404 |
| `500 status=500 error=SERVER_ERROR` | Status 5xx vẫn là response HTTP có body lỗi |
| `204 status=204 errorStreamNull=true bodyBytes=0` | Response không có nội dung; error stream nullable |
| `302 status=302 location=/ok autoRedirect=false` | Tắt redirect per instance giúp đọc status và Location của response ban đầu |
| `PATCH rejected=true` | API legacy `setRequestMethod` không chấp nhận PATCH theo danh sách Java 17 |

**Cần hiểu phạm vi thí nghiệm:** số dòng và nội dung body được cố định bởi local server. Việc `getInputStream()` ném IOException với HTTP 404 được xác minh trên JDK dùng để thử, nhưng **không nên dựa vào tên exception cụ thể như một API phân loại HTTP status**: luôn lấy `getResponseCode()`. Server demo chỉ làm HTTP loopback, không mô phỏng TLS, Internet, authentication, error JSON schema hay proxy.

## 10. getErrorStream() là nullable và không tự mở kết nối

Theo Java SE 17 Javadoc, `getErrorStream()`:

- Trả **InputStream của error response**, nếu connection đã có lỗi HTTP nhưng server vẫn gửi dữ liệu hữu ích.
- **Không khởi tạo kết nối** nếu chưa connected.
- Trả **`null`** nếu connection chưa được thiết lập, không có lỗi, hoặc server không gửi error data.
- Không phải API tạo exception, và không phải tín hiệu đảm bảo server đã gửi một body lỗi hợp lệ.

Bởi vậy, đoạn sau dễ gây `NullPointerException`:

~~~java
// SAI: error stream có thể null, kể cả với 4xx/5xx.
String error = new String(
        connection.getErrorStream().readAllBytes(),
        StandardCharsets.UTF_8);
~~~

Thay bằng:

~~~java
InputStream error = connection.getErrorStream();
if (error == null) {
    // Ghi nhận "error response không cung cấp body" thay vì NPE.
} else {
    try (InputStream in = error) {
        // Giới hạn kích thước, giải mã theo Content-Type nếu cần.
    }
}
~~~

**Thứ tự có ý nghĩa:** nên gọi `getResponseCode()` trước để kết nối và xác định status, rồi mới lấy stream. `getErrorStream()` khi connection còn mới thường là null. Không viết business logic phụ thuộc `getErrorStream() != null` thay cho kiểm tra status code.

### 10.1. Có nên fallback từ error stream sang input stream?

Trong `HttpURLConnection` chuẩn, với status lỗi >=400, `getInputStream()` thường ném `IOException` thay vì cấp body lỗi. Nếu `getErrorStream() == null`, **không nên** gọi `getInputStream()` bất chấp để “cố đọc thông báo”: có thể chỉ nhận thêm exception. Hãy ghi nhận **status code** và body lỗi có thể vắng mặt; nếu API yêu cầu error JSON, xử lý tình huống empty/null có chủ đích.

Với 3xx, tùy policy redirect và status, `getInputStream()` có thể cho body của response, nhưng **Location + redirect policy** thường là dữ liệu quan trọng hơn. Với 204/HEAD, không cần cố parse một body không tồn tại.

### 10.2. Error stream có thể đọc lỗi lần nữa

Ngay cả khi đã có error stream object, `InputStream.read` vẫn có thể ném `IOException` do kết nối đứt, timeout đọc hoặc response malformed. Vì vậy:

~~~text
HTTP status = 500
errorStream != null
      |
      +-- read hoàn tất -> có thể parse error payload
      |
      +-- read thất bại -> đã biết HTTP 500 nhưng body lỗi chưa chắc đầy đủ
~~~

Không lấy status có sẵn làm bằng chứng tải body xong, và không nuốt IOException mà vẫn báo đã xử lý error response hoàn chỉnh.

## 11. HTTP error không giống IOException

| Tình huống | Có status HTTP? | Có stream? | Nhận định |
|---|---|---|---|
| Server trả `200` + body | Có | Thường `getInputStream` | HTTP success, vẫn cần validate body |
| Server trả `201` + body | Có | `getInputStream` | Request tạo tài nguyên thành công theo API |
| Server trả `204` | Có | Body rỗng | Không phải network failure |
| Server trả `404` + JSON | Có | Có thể có `getErrorStream` | HTTP client error, **không đồng nghĩa DNS/TCP lỗi** |
| Server trả `500` + HTML | Có | Có thể có `getErrorStream` | HTTP server error |
| Server trả `404` không body | Có | `getErrorStream == null` có thể xảy ra | HTTP error thiếu payload |
| Không resolve DNS / connect refused | Thường không | Không có HTTP response body | `UnknownHostException` / `ConnectException`… |
| TCP read timeout trước headers | Có thể không | Không | `SocketTimeoutException` |
| Body stream lỗi sau status | Status có thể đã biết | Stream lỗi khi đọc | Transport/body failure sau HTTP metadata |

`IOException` bao gồm nhiều trường hợp: kết nối mạng, TLS handshake, timeout, đọc stream lỗi và thậm chí hành vi mapping status của `getInputStream()` trên 404. **Không thể phân loại HTTP error chỉ bằng tên exception**; hãy kiểm tra status khi có thể và phân biệt khi hoàn toàn không có response.

### 11.1. Nếu getResponseCode ném IOException?

`getResponseCode()` có thể ném `IOException` nếu lỗi xảy ra khi kết nối/nhận status. Trong đường này:

- **Không giả định** status code luôn có giá trị đáng tin.
- Không gọi `getErrorStream()` rồi mặc định nó có body; phương thức có thể trả null vì không có HTTP response hợp lệ.
- Log loại lỗi, URI đã được sanitize, timeout phase và exception chain; không log credential hoặc full request body.
- Với idempotent request, retry chỉ khi policy cho phép; với POST, cần idempotency key/logic nghiệp vụ vì server có thể đã xử lý trước khi response thất lạc.

## 12. Redirect policy của HttpURLConnection và status 3xx

`HttpURLConnection` có:

| API | Phạm vi | Lưu ý |
|---|---|---|
| `HttpURLConnection.getFollowRedirects()` | Trạng thái mặc định tĩnh của class | Default **true** theo Java 17 |
| `HttpURLConnection.setFollowRedirects(boolean)` | Thay default redirect behavior ở cấp class/JVM | Không nên đổi giữa requests trong service nhiều thread |
| `connection.getInstanceFollowRedirects()` | Chính sách của instance | Mặc định nhận từ static policy lúc tạo connection |
| `connection.setInstanceFollowRedirects(boolean)` | Tắt/bật redirect cho instance trước I/O | Dùng false để tự xử lý Location |
| `connection.getHeaderField("Location")` | URL tiếp theo server đề xuất | Có thể relative, thiếu hoặc không đáng tin |

**Khác biệt so với Java 17 `java.net.http.HttpClient`:** `HttpURLConnection` mặc định **follow redirects = true**, còn `HttpClient` hiện đại mặc định `HttpClient.Redirect.NEVER`. Đừng chuyển code giữa hai API rồi giả định behavior giống nhau.

~~~java
HttpURLConnection c = (HttpURLConnection)
        URI.create("https://api.example.test/old").toURL().openConnection();

c.setInstanceFollowRedirects(false);
int code = c.getResponseCode();
String location = c.getHeaderField("Location");
~~~

Đây là trích đoạn HTTP client, **không phải demo có thể chạy offline**. Nếu status là 302, ứng dụng có thể muốn tự đánh giá destination trước khi tạo request khác. Không theo mù quáng `Location` sang host ngoài trust boundary cùng Authorization/Cookie/POST body. Phải kiểm tra scheme, origin, allowlist, số hop, phương thức và bảo mật HTTPS.

**Đặc biệt với request streaming body:** `setFixedLengthStreamingMode` / `setChunkedStreamingMode` có thể làm auto redirect/authentication không thực hiện được và dẫn tới `HttpRetryException`. Do đó không được đoán rằng mọi 3xx/401 sẽ được tự xử lý rồi ẩn khỏi caller.

## 13. Timeouts: connectTimeout khác readTimeout

`URLConnection` cung cấp:

| Thiết lập | Mục đích | Default |
|---|---|---|
| `setConnectTimeout(int millis)` | Thời gian tối đa cho giai đoạn mở liên kết network theo contract | `0` (không giới hạn bằng setting này) |
| `setReadTimeout(int millis)` | Giới hạn chờ dữ liệu tại thao tác đọc | `0` (không giới hạn bằng setting này) |

Ví dụ:

~~~java
connection.setConnectTimeout(3000);
connection.setReadTimeout(5000);
~~~

**Read timeout không đồng nghĩa tổng thời gian tải response.** Nếu server cứ gửi một ít byte trước mỗi thời hạn read, tổng thời gian có thể dài hơn nhiều. Với response lớn, cần thêm overall deadline, maximum body bytes, retry policy và cancellation phù hợp.

Thông thường `SocketTimeoutException` là subtype của `IOException` khi chờ vượt thời hạn. Nhưng status 504 **Gateway Timeout** là HTTP response do server/proxy trả; nó **không tương đương** với `SocketTimeoutException` phía Java client.

Không để `0` vô hạn trong production khi endpoint có thể bị treo. Đặt timeouts theo SLA và environment. Khi timeout xảy ra trong POST, server có thể vẫn đã nhận/thi hành request, vì thế không tự retry một cách mù quáng.

## 14. Headers, Content-Type và giải mã response body

`getHeaderField("Content-Type")` có thể trả:

~~~http
Content-Type: application/json; charset=UTF-8
~~~

Nhưng **`getInputStream()` và `getErrorStream()` trả byte stream**, không tự bảo đảm đúng charset JSON/text mà ứng dụng dùng. Trong demo body là ASCII/UTF-8, nên dùng:

~~~java
String body = new String(in.readAllBytes(), StandardCharsets.UTF_8);
~~~

Đây là cách tiện lợi **chỉ cho body nhỏ, có giới hạn**. Với response không đáng tin/đồ sộ:

- Kiểm tra `Content-Type` và charset đúng contract API.
- Giới hạn tổng số byte **khi đọc**, không chỉ tin `Content-Length` (có thể thiếu/sai).
- Tránh log toàn bộ HTML error page/JSON chứa PII/token.
- Phân biệt status 204/HEAD (không có body) với server trả `Content-Length: 0`.
- Nếu server nén body bằng `Content-Encoding`, ứng dụng cần xử lý encoding phù hợp; **không mặc định raw stream đã là chuỗi text**.
- Parse lỗi JSON là **application data error**, không nhất thiết là HTTP transport error.

### 14.1. Đọc stream theo block thay vì readAllBytes

~~~java
// Trích đoạn: in là InputStream có owner đúng.
// Đếm bytes đọc để chặn response lớn.
long maxBytes = 1_000_000;
long total = 0;
byte[] buffer = new byte[8192];
for (int n; (n = in.read(buffer)) != -1;) {
    total += n;
    if (total > maxBytes) {
        throw new IOException("Body too large");
    }
    // Chuyển đúng n byte sang parser, file hoặc bounded sink.
}
~~~

Đoạn này không tự giải quyết parser/sink; với response body lớn và dữ liệu nhạy cảm, cần quản lý memory, content compression, decoding và cleanup đầy đủ.

### 14.2. HTTP Content-Length khác String.length

`Content-Length` mô tả **số byte trong HTTP message representation** theo protocol, không phải số ký tự Java. Với UTF-8, chữ có dấu tiếng Việt hoặc emoji thường chiếm nhiều byte; dùng `payload.getBytes(StandardCharsets.UTF_8).length` để chọn `setFixedLengthStreamingMode` chính xác.

## 15. Đóng stream và disconnect() đúng cách

Theo Java 17 Javadoc, mỗi `HttpURLConnection` phục vụ một request, nhưng underlying persistent connection có thể được **chia sẻ** bởi nhiều connection instances.

- `InputStream.close()` / `OutputStream.close()` giải phóng resource thuộc stream và có thể hỗ trợ khả năng reuse network connection theo implementation.
- `HttpURLConnection.disconnect()` thông báo không mong đợi thêm request gần đó, có thể đóng socket nếu persistent connection đang idle.
- `disconnect()` **không làm HttpURLConnection instance trở nên tái sử dụng được**; instance đã dùng thì tạo instance mới cho request mới.
- **Không dùng `disconnect()` thay thế việc đóng stream bằng try-with-resources.** Hai thao tác có ý nghĩa khác nhau.

Mẫu:

~~~java
HttpURLConnection c = (HttpURLConnection) url.openConnection();
try {
    c.setConnectTimeout(3000);
    c.setReadTimeout(3000);
    int code = c.getResponseCode();
    InputStream candidate = code >= 400
            ? c.getErrorStream()
            : c.getInputStream();
    if (candidate != null) {
        try (InputStream in = candidate) {
            // Đọc body phù hợp status/method, có quota.
        }
    }
} finally {
    c.disconnect();
}
~~~

Đây là **trích đoạn** với `url` đã khai báo. Nếu muốn xử lý status 3xx/204/HEAD riêng, phải bổ sung rẽ nhánh; đừng biến mẫu thành một HTTP policy đầy đủ chỉ bằng hai nhánh status.

## 16. Những sai lầm thực tế và cách sửa

| Triệu chứng | Sai lầm thường gặp | Cách sửa |
|---|---|---|
| 404 có JSON lỗi nhưng app chỉ thấy FileNotFoundException | Gọi `getInputStream` cho mọi status | Lấy `getResponseCode` rồi thử `getErrorStream` |
| NPE khi đọc lỗi | Không kiểm tra `getErrorStream() == null` | Error stream nullable |
| getErrorStream null ngay sau openConnection | Nó không tự khởi tạo I/O | Lấy status bằng getResponseCode trước |
| POST lại gửi GET | Không đặt method tường minh, hiểu sai doOutput | `setRequestMethod("POST")` trước output |
| `PATCH` ném `ProtocolException` | Legacy HttpURLConnection không hỗ trợ PATCH trực tiếp | Dùng `java.net.http.HttpClient` |
| `setRequestMethod` lỗi sau khi gọi `getInputStream` | Connection đã khởi tạo | Đặt method/properties trước I/O |
| 204 làm parser JSON lỗi | 204 không có body | Bỏ qua parse body khi không có payload |
| 401 bị coi thành “Java mất mạng” | Nhầm HTTP auth status với IOException | Phân loại HTTP status và network error riêng |
| 302 bị tự chuyển sang URL khác | Redirect mặc định true | `setInstanceFollowRedirects(false)` khi cần kiểm soát |
| Fixed streaming POST gặp `HttpRetryException` | Auto auth/redirect không dùng được trong streaming mode | Thiết kế replay/auth/redirect có kiểm soát |
| `getResponseMessage` null hoặc khác wording | Reason phrase không ổn định | Dùng integer status code |
| Request treo | Không đặt connect/read timeout | Đặt cả hai + overall policy |
| Nạp response lớn làm OOM | `readAllBytes` không giới hạn | Bounded streaming/size limit |
| Nội dung Unicode sai | Dùng default charset | Đọc Content-Type, giải mã theo contract |
| Socket leak | Không close streams hoặc disconnect | try-with-resources và finally |
| Gọi lại cùng connection để gửi request thứ hai | Instance chỉ dùng cho một request | Mở HttpURLConnection mới |
| Log lộ token trong URL/body lỗi | Log raw body/header | Redact credentials, sanitize URI |
| HTTPS handshake bị bypass | Trust-all SSL manager để “sửa lỗi” | Sửa truststore/certificate, không bỏ TLS verification |

## 17. Checklist code review

**Trước I/O:** URL có scheme HTTP/HTTPS được phép? Có khả năng SSRF nếu URL do người dùng nhập? Method đã thiết lập tường minh? `setDoOutput`, `Content-Type`, Content-Length/streaming mode đúng chưa? Headers, connect/read timeouts và redirect policy đã đặt trước connection chưa?

**Khi nhận HTTP response:** `getResponseCode` trả status nào? 2xx có body hay không? 3xx có Location cần kiểm tra không? Với 4xx/5xx đã thử `getErrorStream` và xử lý null chưa? Có phân biệt `IOException` do mạng với status HTTP xấu không?

**Khi đọc body:** Có quota byte, encoding, compression và parser phù hợp không? Có log token/PII trong error body không? Nếu stream đang đọc mà bị timeout, trạng thái là body-failed hay app vẫn đánh dấu success?

**Khi kết thúc:** `InputStream`/`OutputStream` đã close chưa, `disconnect` ở finally chưa? Có chủ động không tái sử dụng cùng HttpURLConnection instance? POST không idempotent có bị retry trái phép không?

## 18. Câu hỏi tự kiểm tra

**1. Method mặc định của HttpURLConnection là gì?** `GET`.

**2. Đặt HTTP method ở thời điểm nào?** Trước connect/getInputStream/getOutputStream/getResponseCode.

**3. Java 17 HttpURLConnection có hỗ trợ `setRequestMethod("PATCH")` không?** Không trong danh sách legal methods chính thức; dùng `HttpClient` hiện đại nếu cần PATCH.

**4. `getResponseCode()` có trả `-1` không?** Có thể, khi không phân tích được status HTTP hợp lệ; cũng có thể ném IOException nếu kết nối lỗi.

**5. Có nên điều khiển logic bằng `getResponseMessage().equals("OK")` không?** Không, reason phrase không ổn định và có thể null.

**6. Server trả HTTP 404 và JSON lỗi. Đọc ở đâu?** `getErrorStream()`, sau khi xác định status/connection, nhớ kiểm tra null.

**7. `getErrorStream` có tự tạo network connection không?** Không; chưa connected thường trả null.

**8. Mọi 500 đều có getErrorStream khác null?** Không. Server có thể không gửi error body.

**9. Status 204 có nghĩa Java bị lỗi vì body rỗng?** Không, `204 No Content` là một HTTP success status.

**10. HTTP 504 và `SocketTimeoutException` có giống nhau?** Không: 504 là HTTP response từ server/proxy; exception là lỗi I/O phía client.

**11. `setDoOutput(true)` có tự đủ để thể hiện POST?** Nên đặt `setRequestMethod("POST")` tường minh.

**12. Fixed-length streaming tính length theo gì?** Theo số **byte** của payload, không phải String.length.

**13. Tại sao auth/redirect với streaming body có thể ném `HttpRetryException`?** Javadoc nói khi output streaming bật, auto replay cho authentication/redirection không thực hiện được.

**14. Vì sao redirect trong demo không tự follow?** Vì gọi `setInstanceFollowRedirects(false)` trước I/O.

**15. `disconnect` cho phép reuse cùng instance cho request khác không?** Không, mỗi HttpURLConnection instance dùng cho một request.

**16. `getInputStream()` ném IOException có luôn nghĩa HTTP 404 không?** Không. Có nhiều nguyên nhân network/transport; phải phân loại status khi có thể.

## 19. Tài liệu tham khảo

- [Java SE 17 – HttpURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): `setRequestMethod`, `getResponseCode`, `getResponseMessage`, `getErrorStream`, redirects, streaming mode, `disconnect`.
- [Java SE 17 – URLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): connection lifecycle, request properties, timeouts, input/output streams.
- [Java SE 17 – URL](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html): `openConnection` và `openStream`.
- [Java SE 17 – HttpsURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): TLS-specific HTTP URL connection API.
- [Java SE 17 – HttpRetryException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpRetryException.html): trường hợp không thể retry request với streaming output khi authentication/redirect.
- [Java SE 17 – java.net.http.HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client hiện đại thay cho nhiều nhu cầu legacy.
- [Java SE 17 – HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): custom methods và body publishers.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback server dùng trong demo.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP methods, status codes, redirect và content semantics.

**Kết luận:** Hãy **chỉ định method trước khi kết nối**, dùng **`getResponseCode()` làm nguồn chính để phân loại HTTP response**, rồi đọc **`getInputStream()` cho nội dung thành công** hoặc **`getErrorStream()` cho error body nếu có**. `getErrorStream()` **nullable và không tự kết nối**; HTTP 404/500 là status do server trả chứ không đồng nghĩa Java mất mạng. Luôn đóng streams, đặt timeouts, xử lý redirect/auth có kiểm soát và gọi `disconnect()` trong `finally` khi xong instance.
