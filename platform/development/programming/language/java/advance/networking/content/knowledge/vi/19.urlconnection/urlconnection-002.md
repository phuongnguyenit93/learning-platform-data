# Đặt timeout, request property và hướng vào/ra trước khi kết nối URLConnection trong Java

**`java.net.URLConnection` có hai giai đoạn: tạo đối tượng kết nối rồi cấu hình, sau đó mới thiết lập liên lạc và thực hiện I/O.** Với Java 17+, bạn nên đặt **connect timeout**, **read timeout**, **request properties (đặc biệt HTTP headers)** và **hướng vào/ra** trên đối tượng URLConnection **trước khi gọi bất kỳ phương thức nào có thể kích hoạt kết nối**.

Thứ tự an toàn cho một HTTP GET thông thường:

~~~java
URL url = new URL("https://example.com/data"); // URL minh họa
URLConnection conn = url.openConnection();       // Chưa chủ động gửi request

conn.setConnectTimeout(2_000);                  // 2 giây
conn.setReadTimeout(3_000);                     // 3 giây
conn.setDoInput(true);
conn.setDoOutput(false);
conn.setRequestProperty("Accept", "text/plain");

// getInputStream() có thể tự kết nối nếu chưa kết nối.
try (InputStream in = conn.getInputStream()) {
    byte[] content = in.readAllBytes();
    // Xử lý content; cần giới hạn kích thước trên production.
}
~~~

Đây là **snippet**, cần các imports `java.net.*`, `java.io.*` và xử lý `IOException`. URL mẫu cần Internet nên không phải bài chạy offline. Hai chương trình đầy đủ bên dưới dùng HTTP server tại `127.0.0.1`, cổng động, để kiểm chứng trình tự mà không cần mạng bên ngoài.

**Điểm dễ nhầm nhất:** `getInputStream()`, `getOutputStream()`, `getResponseCode()` (với `HttpURLConnection`), `getContent()` hoặc truy vấn một số response headers có thể **ngầm thực hiện connect**. Không cần gọi `connect()` tường minh thì kết nối vẫn có thể xảy ra. Kể từ thời điểm đó, đổi nhiều thuộc tính như `setDoInput`, `setDoOutput` hay `setRequestProperty` sẽ dẫn đến `IllegalStateException`.

Bài Knowledge này thuộc chủ đề **URLConnection** trong Java Advance - networking, tập trung vào chính xác bốn nhóm thiết lập trước kết nối, cách dùng với `HttpURLConnection`, hậu quả khi làm sai thứ tự, cách xử lý HTTP errors và thực hành Java 17+.

## 1. Lifecycle của URLConnection: configure → connect → use → cleanup

Theo API Java, việc lấy đối tượng bằng `URL.openConnection()` **không đồng nghĩa đã mở network connection tới remote**. Luồng logic:

~~~text
                URL / URI
                   |
                   v
            url.openConnection()
                   |
                   v
         [NEW / chưa connected]
                   |
      +------------+-------------+
      |                          |
 setConnectTimeout()        setReadTimeout()
 setDoInput()               setDoOutput()
 setRequestProperty()       setUseCaches()
 setRequestMethod() (*)     setInstanceFollowRedirects() (*)
 setFixedLengthStreamingMode() (*)
      |                          |
      +------------+-------------+
                   |
          đã cấu hình xong
                   |
          +--------+-------------+
          |                      |
      conn.connect()       I/O operation tự gọi connect
          |                      |
          +-----------+----------+
                      |
                [CONNECTED]
                      |
            send / receive bytes
            response code / headers
                      |
                close streams
                disconnect (*) / cleanup
~~~

Các API đánh dấu `(*)` chỉ có trên `HttpURLConnection` hoặc class HTTP cụ thể. `URLConnection` là lớp cha, không phải mọi protocol đều có HTTP method hay status.

**Hai giai đoạn là bất biến quan trọng:**
1. **Setup:** Cấu hình object trước khi nó được sử dụng. Những thuộc tính như `doInput/doOutput`, request headers và HTTP method phải được xác định trước khi kết nối.
2. **Connected/I/O:** Bắt đầu truyền dữ liệu và đọc response. Không kỳ vọng việc thay đổi cấu hình request muộn có thể chỉnh lại bytes đã gửi.

Cách tránh lỗi: đặt toàn bộ thiết lập trong một đoạn code liền mạch ngay sau `openConnection()`, trước mọi `connect()`, `getInputStream()` hay `getOutputStream()`.

## 2. Những thiết lập nào cần đặt trước?

| Thiết lập | API | Mục đích | Ràng buộc / mặc định |
| --- | --- | --- | --- |
| **Connect timeout** | `setConnectTimeout(int milliseconds)` | Giới hạn thời gian thiết lập liên lạc đến URL | Giá trị 0 = không đặt giới hạn; số âm → `IllegalArgumentException` |
| **Read timeout** | `setReadTimeout(int milliseconds)` | Giới hạn thời gian một thao tác đọc đợi có dữ liệu | Giá trị 0 = không đặt giới hạn; số âm → `IllegalArgumentException` |
| **Request property** | `setRequestProperty(key,value)` | Đặt header/thuộc tính request cụ thể | Sau khi kết nối → `IllegalStateException` |
| **Thêm request property** | `addRequestProperty(key,value)` | Thêm một giá trị cho key thay vì thay thế | Cũng phải trước kết nối |
| **Cho phép đọc** | `setDoInput(true/false)` | Ứng dụng muốn lấy `InputStream` | Mặc định `true`; sau kết nối → `IllegalStateException` |
| **Cho phép ghi** | `setDoOutput(true/false)` | Ứng dụng muốn lấy `OutputStream` | Mặc định `false`; sau kết nối → `IllegalStateException` |
| **HTTP method** | `HttpURLConnection.setRequestMethod("POST")` | Chọn GET/POST/PUT/DELETE… theo API hỗ trợ | Phải trước kết nối; không có trên URLConnection chung |
| **Body streaming mode** | `setFixedLengthStreamingMode(...)` hoặc `setChunkedStreamingMode(...)` | Quy định cách gửi request body không cần buffer nội bộ toàn bộ | Chỉ HttpURLConnection; phải đặt trước kết nối |
| **HTTP redirects** | `setInstanceFollowRedirects(false)` | Chọn chính sách follow redirect theo đối tượng | Nên đặt trước khi gửi request |
| **Sử dụng cache** | `setUseCaches(false)` | Kiểm soát cache được protocol handler hỗ trợ | Không phải cách kiểm soát HTTP response cache ở mọi tầng |

**Về timeout setters:** Javadoc `setConnectTimeout` và `setReadTimeout` mô tả cách đặt giá trị và kiểm tra số âm, **không cam kết tất cả provider ném `IllegalStateException` nếu gọi muộn**. Nhưng gọi chúng trước kết nối/đọc vẫn là quy tắc triển khai đúng, vì thay đổi sau khi I/O đã bắt đầu không phải cách đáng tin để áp timeout hồi tố.

**Về giá trị mặc định:** `doInput` mặc định true và `doOutput` mặc định false theo Java 17. Không tự động suy luận rằng `setDoOutput(true)` tương đương việc chọn HTTP method POST; hãy chỉ định `setRequestMethod("POST")` khi cần POST.

## 3. Connect timeout và read timeout là hai loại giới hạn khác nhau

### 3.1. setConnectTimeout — chờ tạo communications link

~~~java
conn.setConnectTimeout(2_000); // milliseconds
~~~

Giá trị `2_000` có nghĩa **2.000 ms = 2 giây**, không phải 2.000 giây. Nếu provider chuẩn không thể thiết lập kết nối trong thời gian này, nó có thể ném `java.net.SocketTimeoutException`.

Giới hạn này **không** tự bảo vệ toàn bộ quá trình xử lý HTTP. Khi TCP connection đã có mà server chậm tạo response, connect timeout không còn là giới hạn phù hợp.

### 3.2. setReadTimeout — chờ bytes ở thao tác read

~~~java
conn.setReadTimeout(3_000); // milliseconds
~~~

Nếu một thao tác `InputStream.read(...)` chờ dữ liệu quá lâu, provider thường ném `SocketTimeoutException`. Với HTTP, sự chờ này có thể xuất hiện khi đọc response headers hoặc response body tùy implementation.

**Read timeout không phải “deadline toàn request”.** Một response truyền dữ liệu nhỏ đều đặn trước mỗi lần hết hạn có thể kéo dài rất lâu. Nếu nghiệp vụ yêu cầu tổng thời gian tối đa 10 giây cho toàn hoạt động, cần tự tổ chức **deadline/cancellation** và cleanup; chỉ hai socket timeouts không tự đảm bảo wall-clock deadline cho DNS, redirects, upload, download và xử lý application.

### 3.3. Số 0 và số âm

| Gọi | Ý nghĩa |
| --- | --- |
| `setConnectTimeout(0)` | Không giới hạn connect timeout theo option này |
| `setReadTimeout(0)` | Không giới hạn thời gian chờ dữ liệu theo option này |
| `setConnectTimeout(-1)` | `IllegalArgumentException` |
| `setReadTimeout(-5)` | `IllegalArgumentException` |

Một số implementation không chuẩn có thể bỏ qua timeout settings; `getConnectTimeout()` và `getReadTimeout()` cho biết giá trị đã cấu hình trên đối tượng, **không chứng minh được toàn bộ network operation có SLA đúng bằng con số ấy**.

**Khuyến nghị thực hành:** Chọn timeout dương có căn cứ theo API/SLA, không để 0 ngoài ý muốn. Log kiểu timeout và giai đoạn bị lỗi; không retry vô hạn, nhất là POST có side effects.

## 4. Request property: thiết lập HTTP headers trước connect

Trong `URLConnection`, “request property” là cơ chế chung để cung cấp các thuộc tính truyền đi; đối với HTTP, nhiều property tương ứng với **request headers**.

~~~java
URLConnection conn = url.openConnection();
conn.setRequestProperty("Accept", "application/json");
conn.setRequestProperty("User-Agent", "JavaNetworkLesson/1.0");
conn.setRequestProperty("X-Trace-Id", "request-123");
~~~

Đây là snippet: `url` phải được khai báo, `setRequestProperty` phải được gọi **trước khi kết nối**.

Có hai method dễ nhầm:

~~~java
conn.setRequestProperty("Accept", "text/plain");
// Ghi đè giá trị key nếu key đã có trước đó.

conn.addRequestProperty("Accept", "application/json");
// Bổ sung một giá trị cho cùng key thay vì ghi đè.
~~~

Với HTTP, không phải header nào cũng cho phép nhiều instances tùy ý; chuẩn HTTP thường dùng danh sách phân tách dấu phẩy cho những header hỗ trợ nhiều giá trị. Không lạm dụng `addRequestProperty` để thêm nhiều `Authorization`, `Content-Length` hoặc `Host`.

**Đừng trộn request headers với response headers:**
- Trước kết nối, dùng `setRequestProperty("Accept", ...)` hoặc `addRequestProperty(...)`.
- Sau khi nhận response, dùng `getHeaderField("Content-Type")`, `getHeaderFields()`, `getContentType()`.
- `getRequestProperty(...)` và `getRequestProperties()` cũng là API đọc **cấu hình request trước kết nối**; theo Javadoc chúng ném `IllegalStateException` nếu đã connected.
- `getHeaderField("Content-Type")` không phải là cách đọc lại request property.

Một điểm an toàn: header name không được `null`; `setRequestProperty(null, ...)` gây `NullPointerException`. Các protocol handlers có thể từ chối hoặc quản lý riêng những headers bị hạn chế. Không tin dữ liệu input chưa kiểm soát khi ghép header, tránh CR/LF injection và rò credentials.

### Content-Type so với Accept

| Header | Thường diễn tả | Ví dụ |
| --- | --- | --- |
| `Accept` | Client muốn nhận response representation nào | `application/json` |
| `Content-Type` | Kiểu dữ liệu **request body** khi đang gửi | `application/json; charset=utf-8` |
| `Authorization` | Credentials gắn vào request | `Bearer …`, cần giữ kín |
| `If-None-Match` | Conditional GET qua ETag | `"etag-value"` |
| `User-Agent` | Metadata của client | `JavaNetworkLesson/1.0` |

Không tự đặt `Content-Length` bằng số ký tự String; khi gửi UTF-8 có dấu, byte length có thể dài hơn String length. Nếu dùng `HttpURLConnection.setFixedLengthStreamingMode(...)`, phải truyền **số bytes** thực tế.

## 5. Hướng vào/ra: setDoInput và setDoOutput

**`setDoInput(boolean)`** nói rằng ứng dụng muốn đọc từ URL connection qua `getInputStream()`. **`setDoOutput(boolean)`** nói rằng ứng dụng muốn ghi dữ liệu qua `getOutputStream()`.

| Tình huống | doInput | doOutput | Ý nghĩa |
| --- | --- | --- | --- |
| HTTP GET đọc response | true | false | Mặc định thường phù hợp |
| HTTP POST có request body và đọc response | true | true | Vừa gửi request body vừa nhận response |
| Gửi data mà không cần đọc response | false hoặc true theo protocol | true | HTTP vẫn cần hiểu status/cleanup; thường nên đọc response |
| Không đọc và không ghi body | false | false | Chỉ có ý nghĩa cho một số protocol/operation riêng; không phải GET thông thường |

**Hai hướng không phải HTTP method.** Ví dụ:

~~~java
HttpURLConnection http =
        (HttpURLConnection) url.openConnection();

http.setRequestMethod("POST");
http.setDoOutput(true);
http.setDoInput(true);
~~~

Đây là snippet cho URL `http/https`; `HttpURLConnection` là subclass của `URLConnection`. `setDoOutput(true)` **không tự gửi body** và không đảm bảo mọi `URLConnection` hiểu POST. Bạn còn phải gọi `getOutputStream()` và ghi bytes.

**Mặc định trong URLConnection:**
- `getDoInput()` → true.
- `getDoOutput()` → false.
- Nếu gọi `getOutputStream()` với output chưa được cho phép, provider có thể báo lỗi; đừng trông chờ flag tự bật.
- Nếu set input false, không cố đọc response qua `getInputStream()` rồi dự đoán hành vi thành công.

**Không đặt `setDoInput(false)` chỉ vì “tôi gửi POST”.** HTTP POST thường vẫn cần đọc mã trạng thái, headers và response/error body. Với chương trình client thông dụng, doInput nên true.

## 6. connect() tường minh và implicit connect khác nhau ở đâu?

Sau khi tạo `URLConnection`, có thể gọi:

~~~java
conn.connect();
~~~

để mở communication link nếu chưa kết nối. Nhưng bạn **không bắt buộc** gọi method này:

~~~java
try (InputStream input = conn.getInputStream()) {
    // Lấy dữ liệu: implementation kết nối ngầm nếu cần.
}
~~~

Tương tự, `getOutputStream()` để ghi request body có thể bắt đầu kết nối; `HttpURLConnection.getResponseCode()` cần HTTP response nên có thể kích hoạt việc gửi request và đọc status. Một số operations đọc response metadata trên `URLConnection` cũng có thể implicit connect, ví dụ `getContentLength()`, `getContentType()` hoặc `getHeaderField()`.

Vậy thứ tự **sai**:

~~~java
URLConnection conn = url.openConnection();
InputStream in = conn.getInputStream();   // Đã có thể connected.
conn.setRequestProperty("Accept", "application/json"); // Quá muộn!
~~~

Theo Java 17, `setRequestProperty` khi connected sẽ ném `IllegalStateException`. Tương tự, `setDoInput(...)` và `setDoOutput(...)` sau khi connected gây lỗi.

**Vấn đề không nằm ở việc có viết `connect()` hay không.** Nó nằm ở mốc **I/O đầu tiên có thể kết nối**. Đừng chia setup và I/O ra nhiều method rồi không biết một helper `getResponseCode` đã chạy trước.

### Một trường hợp tưởng vô hại

~~~java
URLConnection conn = url.openConnection();
String type = conn.getContentType(); // Có thể làm kết nối ngầm.
conn.setDoOutput(true);              // Quá muộn!
~~~

`getContentType()` phục vụ response metadata nên có thể trigger connect. Nếu chưa chắc một method có implicit I/O hay không, hãy hoàn tất **mọi setup trước khi gọi nó**.

## 7. Ví dụ đầy đủ 1 — GET với timeout, headers, input/output flags

Chương trình sau cho thấy:
1. `openConnection()` tạo URLConnection.
2. Trước khi kết nối, in mặc định `doInput=true` và `doOutput=false`.
3. Đặt connect timeout 2000 ms, read timeout 3000 ms, `Accept` và `X-Trace`.
4. Không gọi `connect()` tường minh; `getInputStream()` nhận HTTP response từ server local.
5. Sau khi đọc response, thử đổi request header và hướng output; cả hai bị từ chối bằng `IllegalStateException`.

Fixture `com.sun.net.httpserver.HttpServer` chỉ nhận `GET /inspect` và trả chuỗi cấu trúc `GET|text/plain|lesson-231`. Đầu ra cố định, không phụ thuộc cổng được OS chọn.

Tạo file **`PreConnectGetDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URL;
import java.net.URLConnection;
import java.nio.charset.StandardCharsets;

public class PreConnectGetDemo {
    static void respond(HttpExchange ex) throws IOException {
        String method = ex.getRequestMethod();
        String accept = ex.getRequestHeaders().getFirst("Accept");
        String trace = ex.getRequestHeaders().getFirst("X-Trace");

        byte[] body = (method + "|" + accept + "|" + trace)
                .getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        ex.sendResponseHeaders(200, body.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(body);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/inspect", ex -> {
            try {
                respond(ex);
            } catch (IOException error) {
                ex.close();
            }
        });
        server.start();

        try {
            URL url = new URL("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/inspect");
            URLConnection connection = url.openConnection();

            System.out.println("Initial doInput/doOutput: "
                    + connection.getDoInput()
                    + "/" + connection.getDoOutput());

            // Toàn bộ cấu hình phải được thực hiện ngay lúc này.
            connection.setConnectTimeout(2000);
            connection.setReadTimeout(3000);
            connection.setDoInput(true);
            connection.setDoOutput(false);
            connection.setRequestProperty("Accept", "text/plain");
            connection.setRequestProperty("X-Trace", "lesson-231");

            System.out.println("Configured connect/read: "
                    + connection.getConnectTimeout() + "/"
                    + connection.getReadTimeout() + " ms");

            // Không gọi connect() tường minh, getInputStream
            // tự kích hoạt kết nối nếu cần.
            try (InputStream in = connection.getInputStream()) {
                System.out.println("Response: " + new String(
                        in.readAllBytes(), StandardCharsets.UTF_8));
            }

            boolean propRejected = false;
            try {
                connection.setRequestProperty("X-Trace", "late");
            } catch (IllegalStateException expected) {
                propRejected = true;
            }

            boolean directionRejected = false;
            try {
                connection.setDoOutput(true);
            } catch (IllegalStateException expected) {
                directionRejected = true;
            }

            System.out.println("Late request property rejected: "
                    + propRejected);
            System.out.println("Late direction change rejected: "
                    + directionRejected);
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 PreConnectGetDemo.java
java PreConnectGetDemo
~~~

**Đầu ra thực thi đã kiểm chứng trên JVM với HTTP handler chuẩn:**

~~~text
Initial doInput/doOutput: true/false
Configured connect/read: 2000/3000 ms
Response: GET|text/plain|lesson-231
Late request property rejected: true
Late direction change rejected: true
~~~

### Phân tích từng kết quả

- Dòng 1 chứng minh mặc định `doInput=true, doOutput=false`.
- Dòng 2 chỉ ra timeout được lưu đúng theo **milliseconds**, không phải seconds.
- Response có ba phần được server đọc từ **HTTP request thực**; như vậy `setRequestProperty` trước connect đã phát huy tác dụng.
- Chương trình không gọi `connection.connect()`: `getInputStream()` tự thực hiện giai đoạn I/O cần thiết.
- Hai dòng `true` cuối chứng minh lúc này connection đã chuyển sang trạng thái connected và các setter tương ứng không còn hợp lệ.

**Không diễn giải demo này là một phép đo timeout:** Server local trả lời rất nhanh. Việc thấy giá trị 2000/3000 chỉ chứng minh cấu hình đã được đặt; cần một server/network bị trì hoãn có kiểm soát nếu muốn thử `SocketTimeoutException`.

**Lưu ý ví dụ học tập:** `InputStream.readAllBytes()` được dùng vì response local rất nhỏ. Trên production, hãy đọc theo chunks và giới hạn tổng số byte để tránh làm cạn bộ nhớ với body do peer kiểm soát.

## 8. HTTP POST: đặt method, hướng ghi, Content-Type, body length trước kết nối

Với HTTP POST có request body, nên cấu hình theo thứ tự:

~~~java
HttpURLConnection conn =
        (HttpURLConnection) url.openConnection();

conn.setConnectTimeout(2000);
conn.setReadTimeout(3000);
conn.setRequestMethod("POST");
conn.setDoOutput(true);
conn.setDoInput(true);
conn.setRequestProperty(
        "Content-Type", "application/json; charset=utf-8");

byte[] payload = json.getBytes(StandardCharsets.UTF_8);
conn.setFixedLengthStreamingMode(payload.length);

// Đây mới là lúc lấy stream để gửi bytes.
try (OutputStream out = conn.getOutputStream()) {
    out.write(payload);
}

int code = conn.getResponseCode();
// Sau đó đọc input/error stream theo status.
~~~

**Đây là snippet**, cần khai báo `url/json`, imports và error cleanup. Nó không phải một runnable class riêng. Dùng `setRequestMethod("POST")` tường minh để tránh dựa vào hành vi implementation có thể tự thay đổi GET thành POST khi bạn yêu cầu output.

**Thứ tự quan trọng:**
1. Tạo HTTP-specific connection instance.
2. Đặt timeout/method/input-output/request headers.
3. Nếu stream body lớn hoặc muốn không buffer nội bộ, đặt body streaming mode.
4. **Sau cùng mới** gọi `getOutputStream()` và ghi bytes.
5. Đóng/flush output stream trước khi chờ response để server biết request body kết thúc theo framing.
6. Gọi `getResponseCode()`, sau đó đọc response stream thích hợp.
7. Đóng streams và `disconnect()` trong `finally`.

**Nếu đặt `setDoOutput(true)` sau `getOutputStream()`:** Bạn đã yêu cầu output stream trong khi output flag chưa bật; thường gặp lỗi I/O/protocol. Nếu chỉ đặt request header sau khi đã lấy output stream, header có thể bị từ chối do kết nối đã bắt đầu.

## 9. setFixedLengthStreamingMode và setChunkedStreamingMode

Khi gửi HTTP request body, `HttpURLConnection` có các cơ chế buffering/streaming đặc thù.

### 9.1. Body có kích thước biết trước

~~~java
byte[] body = "hello-java".getBytes(StandardCharsets.UTF_8);
conn.setFixedLengthStreamingMode(body.length);
~~~

`body.length` là **số byte**. Khi bật fixed-length streaming, bạn phải ghi **đúng** số byte đã khai báo. Ghi nhiều hơn hoặc đóng stream trước khi ghi đủ có thể gây exception. Với nội dung UTF-8 có chữ tiếng Việt, không dùng `String.length()` làm `Content-Length`.

### 9.2. Body chưa biết trước kích thước

~~~java
conn.setChunkedStreamingMode(8192);
~~~

Khi phù hợp, HTTP/1.1 request body có thể được gửi theo chunked transfer encoding, không cần buffer toàn bộ payload. Tuy nhiên:
- Một số server/proxy không xử lý tốt chunked request body.
- Không bật cả fixed-length và chunked streaming modes trên cùng connection.
- Các method này phải gọi trước kết nối.
- Theo Javadoc `HttpURLConnection`, khi output streaming mode được bật, **authentication và redirects có thể không tự được xử lý**, và `HttpRetryException` có thể xuất hiện khi đọc response nếu cần retry do authentication/redirect.
- Không tự implement multipart/form-data chỉ bằng `setChunkedStreamingMode`: content format ở tầng ứng dụng vẫn phải đúng.

### 9.3. Vì sao có thể cần streaming?

Nếu gửi một tệp lớn, buffering toàn bộ request body trong bộ nhớ gây áp lực heap. Streaming mode cho phép truyền dữ liệu từng phần. Nhưng nếu request không idempotent và gặp lỗi giữa chừng, bạn **không thể** giả định server chưa xử lý gì; cần retry policy/idempotency ở tầng nghiệp vụ.

Ví dụ POST local ở phần sau chọn fixed-length streaming vì body chỉ 10 bytes và nội dung xác định.

## 10. getResponseCode, getInputStream và getErrorStream

`URLConnection` chung có các method stream và metadata, nhưng HTTP-specific status/error methods nằm ở `HttpURLConnection`.

| Cần lấy | API | Lưu ý |
| --- | --- | --- |
| Status HTTP | `HttpURLConnection.getResponseCode()` | Có thể trigger I/O/implicit connect |
| Response thành công | `conn.getInputStream()` | Đọc body; với 4xx/5xx có thể ném `IOException` |
| Response lỗi HTTP | `conn.getErrorStream()` | Có thể `null` nếu không có error body hoặc chưa có response |
| Response content type | `conn.getContentType()` | Response metadata, không phải request header |
| HTTP response headers | `conn.getHeaderFields()` | Có thể trigger implicit connect |
| Đóng đường truyền logical | `conn.disconnect()` | HTTP-specific; không phải method chung của URLConnection |

Ví dụ xử lý:

~~~java
int status = conn.getResponseCode();
InputStream responseStream =
        status >= 400 ? conn.getErrorStream() : conn.getInputStream();

if (responseStream != null) {
    try (InputStream in = responseStream) {
        byte[] response = in.readAllBytes();
        // Chỉ readAllBytes khi chắc chắn body nhỏ; production cần giới hạn.
    }
}

conn.disconnect();
~~~

Đây là **snippet**, cần `conn` là `HttpURLConnection`. Không đồng nhất HTTP error status 422 với lỗi kết nối: server đã gửi một HTTP response hợp lệ. Dùng `getErrorStream()` để đọc body chứa thông tin lỗi nếu có, nhưng luôn kiểm tra `null`.

HTTP redirects có thể khiến URL handler thực hiện thêm network I/O nếu cho phép. Không cho rằng `setConnectTimeout` là giới hạn tổng cho mọi redirect hoặc mọi lần retry.

## 11. Ví dụ đầy đủ 2 — POST có body, sau đó đọc HTTP error body

Chương trình **`PreConnectPostDemo.java`** dùng HTTP server local với hai endpoint:
- `POST /echo` nhận body text và trả HTTP 201 kèm `METHOD|CONTENT_TYPE|BODY`.
- `GET /reject` trả HTTP 422 và body `invalid-request`.

Client tạo **một HttpURLConnection mới cho mỗi HTTP request**, cấu hình toàn bộ trước khi mở I/O, dùng `setFixedLengthStreamingMode` cho POST và đọc lỗi bằng `getErrorStream()`.

Tạo file **`PreConnectPostDemo.java`**:

~~~java
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

public class PreConnectPostDemo {
    static void reply(
            HttpExchange ex, int status, String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    static void handle(HttpExchange ex) throws IOException {
        if (ex.getRequestURI().getPath().equals("/echo")) {
            String method = ex.getRequestMethod();
            String type = ex.getRequestHeaders()
                    .getFirst("Content-Type");
            String body = new String(
                    ex.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8);
            reply(ex, 201, method + "|" + type + "|" + body);
        } else {
            reply(ex, 422, "invalid-request");
        }
    }

    static HttpURLConnection open(URL url, String method)
            throws IOException {
        HttpURLConnection conn =
                (HttpURLConnection) url.openConnection();

        // Cấu hình TRƯỚC getOutputStream/getResponseCode/connect.
        conn.setConnectTimeout(2000);
        conn.setReadTimeout(3000);
        conn.setInstanceFollowRedirects(false);
        conn.setRequestMethod(method);
        conn.setDoInput(true);
        return conn;
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/", ex -> {
            try {
                handle(ex);
            } catch (IOException error) {
                ex.close();
            }
        });
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpURLConnection post =
                    open(new URL(base + "/echo"), "POST");

            try {
                post.setDoOutput(true);
                post.setRequestProperty(
                        "Content-Type", "text/plain; charset=utf-8");

                byte[] payload = "hello-java"
                        .getBytes(StandardCharsets.UTF_8);
                post.setFixedLengthStreamingMode(payload.length);

                try (OutputStream out = post.getOutputStream()) {
                    out.write(payload);
                }

                System.out.println(
                        "POST status: " + post.getResponseCode());

                try (InputStream in = post.getInputStream()) {
                    System.out.println("POST body: " + new String(
                            in.readAllBytes(), StandardCharsets.UTF_8));
                }
            } finally {
                post.disconnect();
            }

            HttpURLConnection err =
                    open(new URL(base + "/reject"), "GET");

            try {
                System.out.println(
                        "Error status: " + err.getResponseCode());

                InputStream stream = err.getErrorStream();
                if (stream != null) {
                    try (InputStream in = stream) {
                        System.out.println("Error body: " + new String(
                                in.readAllBytes(),
                                StandardCharsets.UTF_8));
                    }
                } else {
                    System.out.println("Error body: (none)");
                }
            } finally {
                err.disconnect();
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Chạy với Java 17+:

~~~bash
javac -encoding UTF-8 PreConnectPostDemo.java
java PreConnectPostDemo
~~~

**Đầu ra khi HTTP fixture trả đúng như thiết kế:**

~~~text
POST status: 201
POST body: POST|text/plain; charset=utf-8|hello-java
Error status: 422
Error body: invalid-request
~~~

### Phân tích

1. `open(url,method)` tạo đối tượng mới và đặt connect/read timeout, redirect policy, HTTP method và doInput **trước** mọi I/O.
2. Với POST, method `setDoOutput(true)` được gọi **trước** `getOutputStream()`.
3. `Content-Type` được đặt khi request chưa connected; server nhận được header đúng.
4. `payload.length` truyền cho fixed-length streaming mode là 10 bytes ASCII. Nếu payload có Unicode, số bytes phải lấy từ mảng sau UTF-8 encoding.
5. `getOutputStream()` khởi tạo việc gửi body; sau khi đóng output, `getResponseCode()` nhận HTTP 201 và `getInputStream()` đọc thành công.
6. Request khác tới `/reject` nhận HTTP 422. Chương trình dùng `getErrorStream()` thay vì cố đọc body lỗi qua `getInputStream()`.
7. Mỗi HttpURLConnection có một lifecycle request riêng; `disconnect()` trong `finally` là thao tác cleanup cho HTTP-specific connection object.

HTTP server được dựng bằng `jdk.httpserver` chỉ để kiểm thử; đây không phải framework server production. Nó đọc toàn bộ request body do test kiểm soát. Server public phải giới hạn kích thước body và xử lý tình huống input độc hại.

## 12. Các chuỗi thao tác sai thường gặp

### Sai 1: đặt header sau getInputStream

~~~java
URLConnection conn = url.openConnection();
InputStream in = conn.getInputStream();
conn.setRequestProperty("Accept", "application/json");
~~~

**Vì sao sai:** `getInputStream()` có thể kết nối ngầm. Lời gọi `setRequestProperty` phía sau bị `IllegalStateException`.

**Sửa:** Đặt request headers trước `getInputStream()`.

### Sai 2: gọi connect() rồi mới đổi hướng

~~~java
URLConnection conn = url.openConnection();
conn.connect();
conn.setDoOutput(true);
~~~

**Vì sao sai:** `setDoOutput` thuộc cấu hình pre-connect. Đổi sau `connect` bị từ chối.

**Sửa:** Xác định muốn ghi body hay không và set flag trước khi connect.

### Sai 3: không bật output trước khi lấy output stream

~~~java
HttpURLConnection conn =
        (HttpURLConnection) url.openConnection();
conn.setRequestMethod("POST");
// Chưa conn.setDoOutput(true)
try (OutputStream out = conn.getOutputStream()) {
    out.write(payload);
}
~~~

**Vì sao sai:** `doOutput` mặc định false; request body cần output được cho phép. Đặt `setDoOutput(true)` trước khi `getOutputStream()`.

### Sai 4: setDoOutput(true) và tưởng method tự thành POST

~~~java
HttpURLConnection conn =
        (HttpURLConnection) url.openConnection();
conn.setDoOutput(true);
~~~

Điều này **chỉ thay đổi hướng I/O**, không phải cách API chung công bố lựa chọn HTTP method. Một số HTTP handler có thể tự đổi GET sang POST khi output được yêu cầu, nhưng dựa vào điều đó làm code khó hiểu và phụ thuộc implementation. **Sửa:** `conn.setRequestMethod("POST")` tường minh trước I/O.

### Sai 5: đảo thứ tự gọi đọc và ghi ở POST

~~~java
HttpURLConnection conn = ...; // đã cấu hình POST/doOutput
int status = conn.getResponseCode();
try (OutputStream out = conn.getOutputStream()) {
    out.write(payload);
}
~~~

**Vì sao sai:** `getResponseCode()` có thể khởi động/gửi HTTP request trong khi body chưa được cung cấp, khiến thao tác ghi sau quá muộn. **Sửa:** Ghi/đóng output stream trước khi đọc status và response.

### Sai 6: quên read timeout

~~~java
conn.setConnectTimeout(1000);
// Không đặt read timeout.
~~~

**Vì sao sai:** TCP có thể kết nối nhanh nhưng server không trả bytes; thread vẫn chờ ở read. **Sửa:** Đặt cả hai loại timeout theo latency budget.

### Sai 7: dùng nhầm String.length() làm Content-Length

~~~java
String body = "Tiếng Việt";
conn.setFixedLengthStreamingMode(body.length()); // Có thể sai!
~~~

**Vì sao sai:** Java String length không phải số byte UTF-8. **Sửa:**

~~~java
byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
conn.setFixedLengthStreamingMode(bytes.length);
~~~

### Sai 8: bỏ qua getErrorStream

~~~java
int status = conn.getResponseCode();
try (InputStream in = conn.getInputStream()) {
    // Với status 4xx, implementation có thể throw IOException.
}
~~~

**Sửa:** Với HTTP error status, đọc `getErrorStream()` nếu khác null; vẫn phân biệt lỗi HTTP hợp lệ với lỗi network.

Các đoạn trong mục này là **mã minh họa lỗi/cách sửa**, không phải chương trình độc lập; không copy nguyên phản ví dụ vào production.

## 13. Lỗi và ngoại lệ cần xử lý

| Exception/tình huống | Thường gặp khi | Hướng xử lý |
| --- | --- | --- |
| `IllegalStateException` | Đặt `doInput/doOutput` hoặc request header sau connect; đặt streaming mode quá muộn | Sửa thứ tự setup, tạo đối tượng kết nối mới |
| `IllegalArgumentException` | Timeout âm hoặc fixed-length body length âm | Validate cấu hình đầu vào trước khi tạo request |
| `SocketTimeoutException` | Timeout khi mở link hoặc chờ bytes trong read | Phân loại giai đoạn, đóng/dọn stream, retry theo policy |
| `UnknownHostException` | DNS không phân giải được host | Kiểm tra tên host, DNS/network; không retry vô hạn |
| `ConnectException` | Không thể thiết lập TCP connection | Kiểm tra service/port/network; backoff phù hợp |
| `ProtocolException` | HTTP method không hợp lệ/không được hỗ trợ hoặc không thể thay method | Dùng method phù hợp và đặt trước I/O |
| `HttpRetryException` | Output streaming mode mà redirect/authentication cần retry | Xử lý có chủ đích; không giả định handler tự replay body |
| `IOException` khi đọc normal body trên HTTP 4xx/5xx | Server trả HTTP error response | Kiểm tra status, `getErrorStream` có thể chứa body |
| `IOException` khi ghi/đọc | Peer đóng connection, connection reset, stream lỗi | Cleanup, không tự khẳng định server chưa xử lý request |
| HTTP 404/422/500 hợp lệ | Server trả response với mã status lỗi | Không nhầm là `connect timeout`; xử lý nghiệp vụ |

**Không nuốt ngoại lệ rồi tiếp tục dùng cùng `HttpURLConnection` cho một request khác.** Một `HttpURLConnection` đại diện một request; tạo instance mới cho lần gửi khác. Underlying TCP connection có thể được implementation tái sử dụng, nhưng đó là việc của protocol handler.

**Đừng retry POST ngay sau timeout mà không hiểu idempotency.** Server có thể đã nhận và xử lý body dù client chưa đọc được response. Với operations có side effects, sử dụng idempotency key hoặc cơ chế phía server hỗ trợ để tránh xử lý trùng.

## 14. Resource lifecycle: stream, disconnect và connection reuse

Khi dùng URLConnection/HttpURLConnection:

- Đóng `InputStream` sau khi đọc hoặc khi lỗi.
- Đóng `OutputStream` sau khi đã ghi xong body, trước khi đọc response theo HTTP flow.
- Với HttpURLConnection, gọi `disconnect()` ở `finally` nếu muốn giải phóng logical connection context.
- Không mặc định `disconnect()` luôn đóng socket vật lý ngay lập tức: Java HTTP handler có thể dùng keep-alive/persistent connection pool; Javadoc mô tả `disconnect()` có thể đóng underlying socket nếu nó đang idle.
- Không tạo lại `HttpURLConnection` cho request mới bằng cách đổi header/method trên object đã kết nối. Tạo `openConnection()` mới.

Ví dụ pattern (snippet):

~~~java
HttpURLConnection conn =
        (HttpURLConnection) url.openConnection();
try {
    conn.setConnectTimeout(2000);
    conn.setReadTimeout(3000);
    conn.setRequestMethod("GET");
    conn.setDoInput(true);

    int status = conn.getResponseCode();
    InputStream selected = status >= 400
            ? conn.getErrorStream() : conn.getInputStream();

    if (selected != null) {
        try (InputStream in = selected) {
            // Xử lý dữ liệu có giới hạn.
        }
    }
} finally {
    conn.disconnect();
}
~~~

Với `URLConnection` chung không có method `disconnect()`; đó là API của HttpURLConnection và một số subclasses. Nếu dùng `file:` URL hoặc protocol khác, cleanup phụ thuộc cách implementation cấp stream.

### Không dùng readAllBytes cho dữ liệu lớn không tin cậy

Trong hai chương trình local, response nhỏ cố định. Trong thực tế, nếu response body có thể lớn, hãy dùng buffer và giới hạn:

~~~java
byte[] buffer = new byte[8192];
long total = 0;
int n;
while ((n = in.read(buffer)) != -1) {
    total += n;
    if (total > MAX_BYTES) {
        throw new IOException("Body too large");
    }
    // Tiêu thụ buffer[0..n) từng chunk.
}
~~~

Đây là snippet; cần khai báo `in`, `MAX_BYTES` và xử lý output. Việc chọn timeout cho phép đo *thời gian chờ dữ liệu* không thay thế **giới hạn tổng bytes** để chống OOM/disk exhaustion.

## 15. Proxy, redirect, HTTPS và bảo mật request properties

`URLConnection` thường được dùng để gọi HTTP/HTTPS endpoints, nên có một số ranh giới cần nhớ.

**Proxy:** Có thể dùng `URL.openConnection(Proxy)` nếu muốn quy định đường đi cho request đó thay vì thay đổi proxy configuration toàn JVM. Proxy có thể cần authentication hoặc có khả năng chuyển request đến host khác. **Không dùng một proxy không tin cậy để chuyển credentials nhạy cảm** mà chưa đánh giá threat model.

**Redirects:** `HttpURLConnection.setInstanceFollowRedirects(false)` giúp ứng dụng kiểm soát việc tự động chuyển host/path. Nếu cho phép redirect, một request có thể đi đến URL khác và cần xác minh destination/credentials/SSRF policy. Tránh dùng static `HttpURLConnection.setFollowRedirects(...)` để “đổi tạm” chính sách trên hệ thống đa luồng vì đó là thiết lập lớp, ảnh hưởng rộng.

**HTTPS:** Với `https:`, handler thường là `HttpsURLConnection`. Nó triển khai TLS theo cấu hình trust/hostname verification; không bỏ xác thực chứng chỉ hoặc hostname chỉ để tránh lỗi. `setConnectTimeout` và `setReadTimeout` **không tạo** một deadline tổng đảm bảo cho DNS + proxy + TLS + upload + response.

**Authorization và Cookie:** Nếu cần gửi:

~~~java
conn.setRequestProperty(
        "Authorization", "Bearer " + token);
~~~

đây là snippet, chỉ dùng khi token được lấy từ nguồn an toàn. Header này chứa secret và phải được đặt **trước kết nối**. Không log nguyên header, không dùng biến global mutable chứa token của user hiện tại để chia sẻ cho nhiều HTTP requests đồng thời. Cookie và Authorization có thể gắn danh tính người dùng; tạo URLConnection riêng từng request và giữ ranh giới tenant rõ ràng.

**SSRF:** Nếu `URL` đến từ dữ liệu không tin cậy, backend có thể bị ép gửi request tới localhost, cloud metadata service hoặc mạng riêng. Kiểm tra scheme (http/https), allowlist host, DNS/IP/private ranges, proxy path và destinations sau redirect. Không dựa vào timeout để coi việc fetch URL tùy ý là an toàn.

**Header injection:** Không ghép giá trị header chưa kiểm tra chứa CR/LF hoặc ký tự điều khiển; API implementation có thể từ chối một số dạng sai nhưng không thay thế validation ở tầng application.

## 16. URLConnection và HttpURLConnection: phạm vi API khác nhau

`URLConnection` là **lớp cha trừu tượng** cho liên lạc với tài nguyên theo URL. `URL.openConnection()` có thể trả subclass tùy scheme/provider. Với HTTP/HTTPS, bạn thường làm việc với `HttpURLConnection` / `HttpsURLConnection`.

| API | URLConnection | HttpURLConnection |
| --- | --- | --- |
| Timeouts `setConnectTimeout/setReadTimeout` | Có | Kế thừa |
| Hướng `setDoInput/setDoOutput` | Có | Kế thừa |
| Request properties | Có | Kế thừa, HTTP headers theo implementation |
| `connect/getInputStream/getOutputStream` | Có | Kế thừa |
| `setRequestMethod` | Không | Có |
| `getResponseCode` | Không | Có |
| `getErrorStream` | Không | Có |
| `disconnect` | Không | Có |
| Streaming modes | Không | Có |

Không ép kiểu mọi `URLConnection` thành `HttpURLConnection`:

~~~java
URLConnection conn = url.openConnection();

if (conn instanceof HttpURLConnection http) {
    http.setRequestMethod("GET");
}
~~~

Đây là snippet Java 17 dùng pattern matching cho `instanceof`. Với URL `file:` hay `jar:`, cast trực tiếp có thể gây `ClassCastException`. Bài tập chọn HTTP endpoints thì có thể cast sau khi xác minh scheme/handler, nhưng viết thư viện chung nên kiểm tra.

### Caching và doInput/doOutput không phải những thứ tương đương

`setUseCaches(boolean)` chỉ cho protocol handler biết có thể dùng cơ chế cache nó hỗ trợ hay không. Nó không có nghĩa `GET` là request idempotent, không thay `Cache-Control` server directives, và không phân biệt người dùng trong cache application.

`setDoInput/DoOutput` chỉ nói nhu cầu đọc/ghi stream. HTTP methods vẫn là GET/POST/PUT/DELETE theo giao thức. Đừng dùng `setDoOutput(true)` để “chọn method” hoặc `setDoInput(false)` để “tự động bỏ qua status”.

## 17. Khi nào nên dùng java.net.http.HttpClient thay cho URLConnection?

Nếu làm HTTP client mới trên Java 11+ / Java 17+, module **`java.net.http`** thường tiện hơn:
- `HttpClient` có API builder, timeout kết nối, redirect policy và HTTP/2 preference.
- `HttpRequest` mô tả URI, method, request headers, body publisher và timeout riêng.
- `HttpResponse<T>` có typed BodyHandler để đọc String, bytes, file hoặc discard.
- `sendAsync` trả `CompletableFuture` cho điều phối bất đồng bộ.

Ví dụ:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

Đây là snippet với imports từ `java.net.http.*` và `java.time.Duration`. **Không nhầm**:
- `HttpClient.Builder.connectTimeout(...)` với `URLConnection.setConnectTimeout(int)`.
- `HttpRequest.Builder.timeout(Duration)` với `URLConnection.setReadTimeout(int)`: ngữ nghĩa không hoàn toàn tương đương.
- `HttpRequest.Builder.header(...)` với `URLConnection.setRequestProperty(...)`.
- `HttpRequest.BodyPublisher` với `URLConnection.setDoOutput(true)`.
- `HttpClient.send/sendAsync` với I/O chủ động qua `getInputStream/getOutputStream`.

**Tuy nhiên, URLConnection vẫn đáng học** vì có trong code Java lâu năm, hỗ trợ một số protocol ngoài HTTP và giúp hiểu rõ **pre-connect configuration** cùng lifecycle I/O. Khi bảo trì các hệ thống legacy, lỗi thứ tự setter là nguyên nhân trực tiếp của những lỗi runtime khó phát hiện.

## 18. Checklist code review trước khi gọi connect/getInputStream/getOutputStream

| Câu hỏi | Trạng thái cần xác nhận |
| --- | --- |
| Đối tượng được tạo từ URL đúng scheme/host chưa? | Không bị SSRF hoặc cast sai protocol |
| Có đặt `setConnectTimeout(ms)` dương chưa? | Có giới hạn việc thiết lập link |
| Có đặt `setReadTimeout(ms)` dương chưa? | Có giới hạn mỗi lần chờ bytes |
| Request header đã đặt hết chưa? | `Accept`, `Content-Type`, auth, trace ID hợp lệ |
| Có dùng `setRequestProperty` đúng với header không? | Set thay giá trị; add chỉ khi header cho phép |
| Có quyết định `doInput/doOutput` chưa? | GET input, POST body output+input |
| Có đặt `setRequestMethod` tường minh chưa? | POST/PUT/DELETE theo API hỗ trợ |
| Body bytes đã encode đúng chưa? | Byte length, charset và content type khớp |
| Có đặt fixed-length/chunked mode trước connect? | Không thay đổi sau khi lấy output stream |
| Có gọi ngầm một API trước cấu hình không? | Không có `getResponseCode/getContentType/getInputStream` sớm |
| Có phân loại HTTP error status chưa? | `getErrorStream` có thể null |
| Stream có được đóng không? | Try-with-resources, cleanup trong finally |
| HTTP-specific object có được disconnect? | Không tái sử dụng instance như request mới |
| Đã giới hạn body size/retry/redirect? | Không gây OOM/SSRF/retry storm |
| Secrets trong request property có được bảo vệ? | Không log credential, không trộn tenant |

## 19. Các lỗi phổ biến và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `IllegalStateException` ở `setRequestProperty` | Gọi sau khi connected | Đặt request properties trước mọi I/O |
| `IllegalStateException` ở `setDoOutput` | `connect()` hoặc implicit connect đã xảy ra | Đặt output flag ngay sau `openConnection()` |
| `getOutputStream()` thất bại | Chưa bật doOutput | `setDoOutput(true)` trước |
| HTTP POST gửi sai method | Chỉ dựa vào `setDoOutput(true)` | `setRequestMethod("POST")` rõ ràng |
| Server nhận sai Content-Type | Đặt header quá muộn hoặc khai báo sai charset | Set trước connect; đồng bộ encoding và header |
| POST body bị thiếu/hỏng | Fixed-length khai báo sai hoặc chưa đóng stream | Dùng `payload.length`, ghi đủ rồi close |
| Connection thành công nhưng read treo | Chỉ có connect timeout | Thêm read timeout |
| Hiểu `readTimeout` như tổng request time | Server gửi dữ liệu từng ít một nên request kéo dài | Thiết kế tổng deadline riêng |
| Timeout 0 nhưng nghĩ là “tức thì” | Giá trị 0 là vô hạn | Dùng số ms dương |
| `SocketTimeoutException` rồi retry POST mù quáng | Không biết server đã xử lý hay chưa | Idempotency/retry policy |
| HTTP 422 nhưng `getInputStream()` lỗi | Error body nằm ở error stream | Đọc response code, `getErrorStream()` nếu có |
| Gọi `getRequestProperty` sau connect | API chỉ cho pre-connect | Lưu metadata cần thiết trước khi kết nối |
| Dùng HTTP method trên URLConnection không phải HTTP | Cast sai subclass | Kiểm tra scheme/type |
| Dùng static follow-redirects cho một request | Đổi hành vi các request khác | `setInstanceFollowRedirects(...)` |
| Giữ một HttpURLConnection để gửi nhiều requests | Mutating connected state không hợp lệ | Một connection instance cho một HTTP request |
| Không đóng input/error/output stream | Rò tài nguyên/giữ connection | Try-with-resources và disconnect |
| Dùng `readAllBytes()` cho response không giới hạn | OOM | Bounded streaming và size limits |
| Log `Authorization`/Cookie | Lộ secrets | Mask/redact, tách user context |
| Cho URL untrusted fetch tự do | SSRF, truy cập mạng nội bộ | Allowlist, kiểm tra redirect và outbound policy |

## 20. Câu hỏi tự kiểm tra

**1.** `URL.openConnection()` có đồng nghĩa đã kết nối tới server HTTP chưa?  
**Đáp án:** Chưa. Nó tạo đối tượng URLConnection để cấu hình. Sau đó `connect()` hoặc I/O có thể thực hiện kết nối.

**2.** Vì sao phải đặt request properties trước `getInputStream()`?  
**Đáp án:** Vì `getInputStream()` có thể implicit connect; sau đó `setRequestProperty` có thể ném `IllegalStateException`.

**3.** `setConnectTimeout(2000)` là 2000 giây hay 2000 ms?  
**Đáp án:** **2000 milliseconds = 2 giây**.

**4.** Kết nối TCP đã thành công nhưng server không gửi bytes. Connect timeout giúp gì?  
**Đáp án:** Không giới hạn giai đoạn đọc; cần `setReadTimeout` để hạn chế thời gian chờ có dữ liệu.

**5.** `setReadTimeout(3000)` bảo đảm toàn bộ response xong trong ba giây không?  
**Đáp án:** Không. Đây là timeout cho thao tác đọc chờ bytes, không phải tổng deadline request.

**6.** Giá trị timeout 0 có nghĩa timeout ngay lập tức không?  
**Đáp án:** Không, Javadoc hiểu 0 là thời gian chờ vô hạn cho option tương ứng.

**7.** Mặc định doInput/doOutput của URLConnection là gì?  
**Đáp án:** `doInput=true`, `doOutput=false`.

**8.** Để POST có body và đọc response, cần những setting nào?  
**Đáp án:** `HttpURLConnection.setRequestMethod("POST")`, `setDoOutput(true)`, `setDoInput(true)`, timeout và request headers trước khi lấy output stream; ghi/đóng body rồi đọc status/response.

**9.** `setRequestProperty` và `addRequestProperty` khác nhau?  
**Đáp án:** Set ghi đè key đã có; add bổ sung giá trị. Đừng dùng add tùy ý với headers không cho phép nhiều giá trị.

**10.** `setFixedLengthStreamingMode(...)` nhận số Java chars hay UTF-8 bytes?  
**Đáp án:** Số **bytes** phải gửi; lấy từ mảng bytes sau encoding.

**11.** Nếu server trả HTTP 422, đọc error body ở đâu?  
**Đáp án:** Với HttpURLConnection, đọc `getErrorStream()` nếu khác null sau khi biết status.

**12.** `getContentType()` gọi trước setting headers có thể gây gì?  
**Đáp án:** Nó có thể trigger implicit connect, khiến việc đổi request properties/hướng I/O sau đó quá muộn.

**13.** `URLConnection` có `getResponseCode()` và `disconnect()` không?  
**Đáp án:** Không. Đây là các method HTTP-specific của `HttpURLConnection`.

**14.** `setDoOutput(true)` có phải luôn là POST không?  
**Đáp án:** Không được coi đó là định nghĩa HTTP method; nên gọi `setRequestMethod("POST")` tường minh.

**15.** Tại sao không dùng một HttpURLConnection để gửi ba requests bằng cách đổi header ba lần?  
**Đáp án:** Object đã connected không được đổi setup cho request tiếp; tạo instance mới mỗi request.

**16.** Sự khác biệt quan trọng khi chuyển sang `java.net.http.HttpClient` là gì?  
**Đáp án:** HttpClient/HttpRequest dùng builder, body publisher và send/sendAsync; URLConnection dùng mutable pre-connect configuration và trực tiếp quản lý input/output streams.

## Tài liệu tham khảo chính thức

- [Java SE 17 — URLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): hai giai đoạn setup/connect, `setConnectTimeout`, `setReadTimeout`, `setDoInput/Output`, `setRequestProperty`, implicit connect và streams.
- [Java SE 17 — HttpURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): HTTP method, response status, error stream, disconnect, streaming modes và redirect policy.
- [Java SE 17 — HttpsURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): HTTPS/TLS subclass, SSL socket factory và hostname verification.
- [Java SE 17 — SocketTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html): lỗi timeout khi xử lý socket I/O.
- [Java SE 17 — HttpRetryException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpRetryException.html): trường hợp không thể retry tự động sau streaming request body.
- [Java SE 17 — URL](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html): tạo URL/openConnection và protocol handlers.
- [Java SE 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html) và [OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): I/O stream lifecycle, close, read/write.
- [Java SE 17 — HttpClient (java.net.http)](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client API hiện đại, dùng khi cần sendAsync/HTTP/2.
- [Java SE 17 — jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): `HttpServer` làm fixture localhost trong hai chương trình.
