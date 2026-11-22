# Chuyển hướng, HTTP keep-alive và ý nghĩa của disconnect trong URLConnection

## Mục tiêu

Trong Java, đoạn mã `(HttpURLConnection) url.openConnection()` tạo một **đối tượng quản lý một HTTP request**, chứ không đồng nghĩa nó đã mở một TCP socket mới. `HttpURLConnection` có thể **tự đi theo HTTP redirect** nếu chính sách cho phép. Một HTTP request có thể đi qua `302 Location: /new` trước khi nhận `200 OK`; cùng lúc, nhiều đối tượng `HttpURLConnection` khác nhau có thể **tái sử dụng một TCP connection** nếu server/client hỗ trợ HTTP/1.1 keep-alive. Do đó, gọi `disconnect()` trên một đối tượng không được hiểu là câu lệnh “đóng chắc chắn mọi TCP socket liên quan và xóa pool”.

Bài học đặt ba câu hỏi vào đúng tầng:

1. **Chuyển hướng (redirect)**: server trả mã 3xx và `Location`; Java tự theo khi nào, cách tắt tự theo cho từng connection, ảnh hưởng tới URL đích, HTTP method và request body, đặc biệt khi bật streaming mode?
2. **HTTP keep-alive/persistence**: HTTP/1.1 có thể gửi nhiều request trên một TCP connection, nhưng tại sao một đối tượng `HttpURLConnection` vẫn **chỉ đại diện một lần gọi HTTP**? Điều kiện để một connection thật sự được dùng lại là gì?
3. **`disconnect()`**: phương thức này thực sự cam kết điều gì, nó khác `InputStream.close()`, `Connection: close` và TCP FIN/RST ra sao? Vì sao gọi `disconnect()` không phải bằng chứng có một socket mới ở request sau?

Bạn sẽ thực hành **ba chương trình Java 17+ độc lập**, chạy trên HTTP loopback không cần Internet: (1) follow và no-follow redirect, (2) POST streaming gặp 307 và `HttpRetryException`, (3) quan sát TCP reuse cả trước và sau một lần `disconnect()`. Tất cả đều được biên dịch bằng `javac --release 17` và chạy trên JDK tương thích Java 17. Phần cuối có checklist xử lý HTTP errors, redirects bảo mật, resource cleanup và bài tập.

## 1. URLConnection và HttpURLConnection có vai trò gì?

`java.net.URLConnection` là lớp trừu tượng cho một liên kết tới URL, không chỉ riêng HTTP. `java.net.HttpURLConnection` mở rộng nó với các phương thức đặc thù HTTP, ví dụ `getResponseCode()`, `setRequestMethod(...)`, `setInstanceFollowRedirects(...)`, `setFixedLengthStreamingMode(...)` và `disconnect()`. `HttpsURLConnection` là nhánh hỗ trợ HTTPS/TLS.

Một quy trình GET thường có các bước:

```text
1. URL/URI của tài nguyên
      │
      ▼
2. URL.openConnection()
   → Đối tượng URLConnection / HttpURLConnection
      │
      ▼
3. Cấu hình TRƯỚC khi connect:
   request method, request headers, connect timeout,
   read timeout, follow-redirect policy
      │
      ▼
4. getResponseCode(), getInputStream(), getOutputStream()
   → Kết nối thực sự có thể được mở ngầm
   → HTTP request được gửi
      │
      ▼
5. Đọc response status/headers/body
   → Có thể đã theo 3xx redirect trước khi thấy kết quả cuối
      │
      ▼
6. Đọc hết và close response stream, cleanup
   → TCP connection có thể được giữ lại trong keep-alive cache
      │
      ▼
7. Request khác tạo HttpURLConnection KHÁC
   → Có thể dùng lại TCP connection cũ nếu thích hợp
```

**Phân biệt ba loại “connection”:**

| Tên gọi | Bản chất | Có bằng chứng TCP socket mới? |
|---|---|---|
| Một `HttpURLConnection` object | Đối tượng Java cho **một logical HTTP request** | **Không** |
| Một HTTP/1.1 persistent connection | Kênh vận chuyển cho nhiều request–response | Có thể được chia sẻ giữa các instance |
| Một TCP socket | OS transport endpoint gồm IP/port và trạng thái TCP | Mở/đóng theo runtime, protocol, server và pool |

Javadoc Java 17 nói rõ: **mỗi instance `HttpURLConnection` dùng cho một request**, nhưng **underlying network connection** có thể được chia sẻ trong suốt quá trình hoạt động giữa các instance khác nhau. Một redirect tự động có thể làm **một logical API request** dẫn đến **nhiều HTTP requests trên mạng**, không biến object thành trình điều phối tùy ý nhiều nghiệp vụ.

### Một lời gọi `openConnection()` có connect ngay không?

Không mặc định. `URL.openConnection()` thường **tạo đối tượng** và cho phép đặt thuộc tính. Một lệnh như `getResponseCode()`, `getInputStream()` hoặc `getOutputStream()` có thể khiến implementation kết nối/gửi request nếu chưa kết nối.

```java
// Đoạn minh họa; chưa phải chương trình độc lập.
HttpURLConnection connection =
        (HttpURLConnection) URI.create(
                "http://127.0.0.1:8080/resource").toURL().openConnection();

connection.setRequestMethod("GET");
connection.setConnectTimeout(3000);
connection.setReadTimeout(3000);
connection.setInstanceFollowRedirects(false);

// getResponseCode() có thể thực hiện connect/request ngầm.
int code = connection.getResponseCode();
```

Điểm thực hành: cấu hình `setRequestMethod`, `setRequestProperty`, `setInstanceFollowRedirects`, streaming mode và thời hạn chờ **trước khi** lần đầu trigger network I/O. Đừng coi `connect()` là bước bắt buộc phải gọi tường minh; các getter I/O có thể tự connect.

## 2. Redirect là một HTTP response, không phải một TCP instruction

Server dùng status 3xx và thường kèm `Location` để báo client có thể cần request một URI khác:

```http
HTTP/1.1 302 Found
Location: /new-location
Content-Length: 0

```

`/new-location` là relative reference được giải quyết dựa trên URI ban đầu. Khi client chọn follow:

```text
Logical GET /old
    |
    |  Server: 302 Found + Location: /new
    ▼
GET /new
    |
    |  Server: 200 OK
    ▼
Caller thấy final result 200
```

**Status 302 không phải TCP redirect.** TCP không tự chuyển socket từ server A sang server B chỉ vì status 302. HTTP client phải diễn giải `Location`, kiểm tra chính sách, rồi phát một **HTTP request kế tiếp**; nó có thể dùng lại connection nếu cùng endpoint và đáp ứng điều kiện, hoặc phải mở connection mới nếu host, port, proxy, TLS context hoặc connection health thay đổi.

### Các status redirect quan trọng

| Status | Diễn giải phổ biến | Method/body khi follow |
|---|---|---|
| `301 Moved Permanently` | URI mới mang tính lâu dài | HTTP semantics cho phép user agent đổi POST→GET; không suy luận request body được giữ |
| `302 Found` | Chuyển tạm thời | Cũng có lịch sử đổi POST→GET; cần biết implementation |
| `303 See Other` | Xem tài nguyên kết quả qua URI khác | Với POST, thường chuyển sang GET, không phát lại body POST |
| `307 Temporary Redirect` | Chuyển tạm nhưng giữ method | Nếu follow, **không đổi method**; body cũ có thể phải phát lại |
| `308 Permanent Redirect` | Chuyển vĩnh viễn nhưng giữ method | Nếu follow, **không đổi method**; body cũ có thể phải phát lại |

Không đồng nhất “RFC mô tả ý nghĩa status” với “`HttpURLConnection` của mọi JDK sẽ tự động follow mọi status này”. `HttpURLConnection` có lịch sử implementation lâu đời, quy tắc thực tế về phương thức, streaming, protocol/scheme và số redirects chịu ảnh hưởng JDK, version và cấu hình. Với request có side effect hoặc auth phức tạp, **không đoán hành vi tự động** mà hãy kiểm thử đúng runtime hoặc xử lý chuyển hướng thủ công.

### Location có thể thay đổi các yếu tố an toàn

Một `Location` có thể là:

- Đường dẫn cùng origin, ví dụ `/v2/items`.
- URI tuyệt đối cùng scheme/host/port.
- URI khác host hoặc port.
- URI đổi giữa HTTP và HTTPS.
- URI trỏ tới dịch vụ bên ngoài, IP nội bộ hoặc địa chỉ nhạy cảm nếu server bị thao túng.

Với ứng dụng nhận URL đầu vào từ người dùng hoặc tự động follow Location không tin cậy, cần **allowlist origin/host**, chặn DNS/IP riêng nếu nghiệp vụ yêu cầu, hạn chế redirect chain, xác minh TLS và tránh đưa `Authorization`/cookies/body nhạy cảm tới điểm đích không được phép. Không copy thủ công credentials sang origin mới chỉ vì đã có header ở request gốc.

## 3. Điều khiển chuyển hướng trong HttpURLConnection

Javadoc Java 17 có hai mức cấu hình:

- **Toàn cục/class:** `HttpURLConnection.setFollowRedirects(boolean)` và `HttpURLConnection.getFollowRedirects()`. **Mặc định true** theo Javadoc; đây là cài đặt **static**, không nên thay đổi tùy tiện khi nhiều module trong một JVM cùng chạy.
- **Từng instance:** `connection.setInstanceFollowRedirects(boolean)` và `connection.getInstanceFollowRedirects()`. Giá trị mặc định của instance lấy từ **static setting tại thời điểm khởi tạo đối tượng**; đổi một instance không thay tất cả.
- Nếu muốn quan sát status 3xx và tự quyết định, đặt **`setInstanceFollowRedirects(false)` trước khi connect**.
- Nếu muốn theo redirect tự động theo khả năng runtime và chính sách cho phép, dùng **`setInstanceFollowRedirects(true)`**; không đồng nghĩa redirect luôn thành công hoặc mọi host/credential đều an toàn.

Ví dụ:

```java
// Đoạn minh họa; biến URL "url" phải có sẵn.
HttpURLConnection c = (HttpURLConnection) url.openConnection();
c.setInstanceFollowRedirects(false);
c.setConnectTimeout(3000);
c.setReadTimeout(3000);
int status = c.getResponseCode();

if (status >= 300 && status < 400) {
    String location = c.getHeaderField("Location");
    // Validate Location, target scheme/host, method, replayability
    // trước khi tạo một HttpURLConnection MỚI.
}
```

Đây là **snippet minh họa**, không phải chương trình Java hoàn chỉnh. Không mặc định mọi status 300–399 đều có `Location`; một số như `304 Not Modified` có ngữ nghĩa cache validation, **không phải** lời mời redirect cần follow. Phải xem đúng status và Location, không chỉ kiểm tra một khoảng số.

### `getURL()` sau redirect

Trong implementation đã thử nghiệm, khi `HttpURLConnection` tự follow từ `/start` tới `/final`, `getURL().getPath()` trả `/final`. Đây là thông tin hữu ích để log **effective URL**. Tuy nhiên mỗi hop vẫn cần kiểm tra an toàn; đừng lấy final URL làm bằng chứng không có hop trung gian tới origin không được phép.

### Vì sao nên tránh static setting?

`HttpURLConnection.setFollowRedirects(false)` ảnh hưởng **những instance được tạo sau đó** trong cùng JVM (trừ khi chúng tự override). Trong ứng dụng server nhiều thư viện, thay đổi static toàn cục có thể tạo hành vi bất ngờ. Ưu tiên setting **per-instance** cho một request cụ thể.

## 4. Java 17+: follow vs no-follow Redirect 302 trên localhost

Chương trình sau dùng `com.sun.net.httpserver.HttpServer` để tạo hai endpoint:

- `/start` trả `302 Found` và `Location: /final`, không gửi body.
- `/final` trả `200 OK` với body `DESTINATION` và tăng counter.

Client tạo **hai đối tượng `HttpURLConnection` khác nhau** cùng xuất phát từ `/start`:

1. Instance đầu bật follow và nhận final response 200.
2. Instance thứ hai tắt follow nên thấy status 302 và Location thô.
3. Server `/final` chỉ được gọi **một lần** trong đường thử này.

**Tệp `RedirectPolicyDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

public class RedirectPolicyDemo {
    private static String read(HttpURLConnection c) throws IOException {
        try (InputStream in = c.getInputStream()) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        } finally {
            c.disconnect();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        AtomicInteger finalHits = new AtomicInteger();
        server.createContext("/start", ex -> {
            try (ex) {
                ex.getResponseHeaders().set("Location", "/final");
                ex.sendResponseHeaders(302, -1);
            }
        });
        server.createContext("/final", ex -> {
            try (ex) {
                finalHits.incrementAndGet();
                byte[] bytes = "DESTINATION".getBytes(StandardCharsets.UTF_8);
                ex.sendResponseHeaders(200, bytes.length);
                try (OutputStream out = ex.getResponseBody()) {
                    out.write(bytes);
                }
            }
        });
        try {
            server.start();
            URL url = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/start").toURL();

            HttpURLConnection follow = (HttpURLConnection) url.openConnection();
            follow.setInstanceFollowRedirects(true);
            follow.setConnectTimeout(3000);
            follow.setReadTimeout(3000);
            int followedStatus = follow.getResponseCode();
            String followedPath = follow.getURL().getPath();
            String followedBody = read(follow);

            HttpURLConnection noFollow = (HttpURLConnection) url.openConnection();
            noFollow.setInstanceFollowRedirects(false);
            noFollow.setConnectTimeout(3000);
            noFollow.setReadTimeout(3000);
            int rawStatus = noFollow.getResponseCode();
            String location = noFollow.getHeaderField("Location");
            noFollow.disconnect();

            System.out.println("Follow status: " + followedStatus);
            System.out.println("Follow final path: " + followedPath);
            System.out.println("Follow body: " + followedBody);
            System.out.println("No-follow status: " + rawStatus);
            System.out.println("No-follow Location: " + location);
            System.out.println("Destination requests: " + finalHits.get());
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch/chạy JDK 17+:

```bash
javac --release 17 -encoding UTF-8 RedirectPolicyDemo.java
java RedirectPolicyDemo
```

**Stdout đã kiểm chứng trên JDK hỗ trợ Java 17+:**

```text
Follow status: 200
Follow final path: /final
Follow body: DESTINATION
No-follow status: 302
No-follow Location: /final
Destination requests: 1
```

**Giải thích có hệ thống:**

- `url.openConnection()` tạo đối tượng mới, chưa có nghĩa mở ngay socket; `getResponseCode()` kích hoạt request.
- Với `follow.setInstanceFollowRedirects(true)`, kết quả caller nhìn thấy là final **200**, không phải intermediate **302**. Điều này hữu ích khi muốn tải tài nguyên, nhưng có thể che thông tin về intermediate redirect nếu application cần audit từng hop.
- `follow.getURL().getPath()` phản ánh `/final` trong runtime đã chạy; nếu cần quyết định an toàn cho từng Location, đừng chỉ kiểm tra URL lúc đầu.
- Với `noFollow`, caller nhìn thấy **302** và `Location: /final`. Không có request thứ hai tới `/final` từ instance này.
- Counter `finalHits=1` xác minh chỉ instance follow đến đích. Đây là thử nghiệm **same-origin trên localhost**, không đại diện cho policy cross-origin hoặc HTTPS downgrade.
- `read(follow)` dùng try-with-resources cho `InputStream`, rồi `disconnect()` trong finally. Điều này **không** chứng minh `disconnect()` luôn đóng một TCP socket vật lý — phần sau giải thích.
- Nếu bạn thay `302` bằng `307` hoặc `308` trong một ứng dụng POST, phải xem method/body và khả năng phát lại, không lấy kết quả GET này để khẳng định các method khác.

## 5. Với POST, redirect còn liên quan request method và body

Một redirect GET có thể dễ xử lý: gửi GET tới URI mới. Với POST/PUT/upload, client có thể đã **gửi body** trước khi nhận response 3xx, và việc gửi lại yêu cầu body **có thể phát lại**.

```text
Client                              Server
 POST /upload + body bytes ───────► 307 Location: /new-upload
        │
        └── Nếu tự follow 307:
            phải giữ method POST
            và có lại body cho request kế tiếp
```

Tuy nhiên “có thể tạo lại cùng bytes” chưa nói gì về **idempotency nghiệp vụ**. Server có thể đã nhận và xử lý POST đầu trước khi trả 3xx hoặc trước khi client timeout. Gửi POST một lần nữa có thể tạo side effect trùng nếu không có request ID/dedup hoặc thiết kế transaction phù hợp.

### 5.1. Khi nào redirect chuyển method?

Theo HTTP semantics (RFC 9110):

- `301`/`302` có lịch sử cho phép user agent chuyển **POST→GET** khi follow.
- `303` thường dùng **GET** để xem kết quả của một POST, không gửi lại POST body.
- `307`/`308` chỉ dùng để chuyển URI **không đổi HTTP method** khi follow. Đó là lựa chọn thích hợp nếu server muốn bảo toàn POST/PUT theo semantics redirect.

Với legacy `HttpURLConnection`, **không giả định mọi kiểu redirect đều có cùng chính sách với `java.net.http.HttpClient` hiện đại**. Kiểm chứng method cuối bằng server test và xem tài liệu runtime, đặc biệt khi dùng streaming mode.

### 5.2. Location không tự cấp quyền gửi dữ liệu

Một `Location` mới có thể đổi host. Với POST kèm cookie, bearer token hoặc file nội bộ, không tự động forward mọi credentials/header/body tới host mới. Nếu endpoint API có side effect, nên xem xét **tắt automatic redirects**, kiểm tra allowlist, TLS, target URI và business contract, rồi mới quyết định gửi request tiếp theo.

## 6. Fixed-length và chunked streaming mode gây hạn chế redirect

`HttpURLConnection` có hai phương thức quan trọng để **stream request body mà không buffer toàn bộ bên trong handler**:

- `setFixedLengthStreamingMode(int)` và `setFixedLengthStreamingMode(long)`: đã biết số bytes request body; **phải ghi đúng số bytes** trước khi đóng output. Với dữ liệu lớn, overload `long` tránh giới hạn int.
- `setChunkedStreamingMode(int chunklen)`: số bytes chưa biết trước; dùng **HTTP chunked transfer encoding**. Không phải mọi HTTP server đều hỗ trợ chế độ này như mong đợi.

**Gọi các phương thức trên trước khi URLConnection được kết nối**. Cần `setDoOutput(true)`, chọn method thích hợp (thường POST/PUT) và lấy `getOutputStream()` để gửi body.

Javadoc Java 17 nói rõ: **khi bật output streaming, HTTP authentication và redirection không thể được xử lý tự động** như chế độ request thông thường. Khi server yêu cầu authentication hoặc redirect và application đọc response, một `HttpRetryException` có thể được ném.

### Vì sao đây không phải “bug Java”?

Khi body đã stream trực tiếp qua socket mà handler **không lưu bản copy đầy đủ**, việc request mới tới URI khác đòi hỏi **gửi lại body**. Nhưng Java handler không thể tự dựng lại một live stream chỉ đọc một lần. Thay vì âm thầm thay đổi request semantics hoặc gửi body rỗng, API báo cần ứng dụng quản lý retry.

Đây là **giới hạn có chủ đích** của streaming mode. Không sửa bằng cách bắt `HttpRetryException` rồi gọi `getInputStream()` lần nữa trên cùng `HttpURLConnection` đã dùng; phải quyết định có tạo request mới hay không, có nguồn body ổn định và chính sách retry/redirect an toàn hay không.

### `HttpRetryException` cung cấp gì?

`java.net.HttpRetryException` cho phép lấy:

- `responseCode()`: HTTP status dẫn tới nhu cầu retry/redirect, ví dụ 307.
- `getLocation()`: Location string từ response, nếu có.
- `getReason()`: lý do failure theo API, không thay source of truth nghiệp vụ.

Nếu muốn tự follow, kiểm tra target URI bằng `URI.resolve(...)`/`URL` theo API an toàn, xác thực origin, kiểm soát method/body replay, giới hạn số hop và request ID. **Không** tự động gửi tiếp mọi POST/PUT chỉ vì exception có Location.

## 7. Java 17+: POST streaming gặp 307 và HttpRetryException

Ví dụ loopback này chứng minh tình huống rất dễ bị hiểu sai:

1. Client POST `HELLO` với `setFixedLengthStreamingMode(5)`, bật `setInstanceFollowRedirects(true)`.
2. Server `/moved` **nhận và đọc toàn bộ body**, rồi trả `307 Temporary Redirect` tới `/destination`.
3. Khi client gọi `getInputStream()` để lấy response, handler báo `HttpRetryException`; nó **không tự tạo POST mới** ở URI đích trong chế độ streaming.
4. Server đích `/destination` chưa thấy request nào.

**Tệp `StreamingRedirectDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.*;

public class StreamingRedirectDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        AtomicReference<String> firstBody = new AtomicReference<>("");
        AtomicInteger destinationHits = new AtomicInteger();

        server.createContext("/moved", ex -> {
            try (ex) {
                firstBody.set(new String(ex.getRequestBody().readAllBytes(),
                        StandardCharsets.UTF_8));
                ex.getResponseHeaders().set("Location", "/destination");
                ex.sendResponseHeaders(307, -1);
            }
        });
        server.createContext("/destination", ex -> {
            try (ex) {
                destinationHits.incrementAndGet();
                ex.getRequestBody().readAllBytes();
                ex.sendResponseHeaders(204, -1);
            }
        });

        try {
            server.start();
            URL url = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/moved").toURL();
            HttpURLConnection c = (HttpURLConnection) url.openConnection();
            try {
                c.setInstanceFollowRedirects(true);
                c.setRequestMethod("POST");
                c.setDoOutput(true);
                c.setConnectTimeout(3000);
                c.setReadTimeout(3000);
                byte[] body = "HELLO".getBytes(StandardCharsets.UTF_8);
                c.setFixedLengthStreamingMode(body.length);
                try (OutputStream out = c.getOutputStream()) {
                    out.write(body);
                }

                boolean retryRequired = false;
                int redirectCode = -1;
                String destination = "";
                try (InputStream in = c.getInputStream()) {
                    in.readAllBytes();
                } catch (HttpRetryException expected) {
                    retryRequired = true;
                    redirectCode = expected.responseCode();
                    destination = expected.getLocation();
                }
                System.out.println("HttpRetryException: " + retryRequired);
                System.out.println("Redirect response: " + redirectCode);
                System.out.println("Redirect Location: " + destination);
                System.out.println("First server body: " + firstBody.get());
                System.out.println("Destination requests: " + destinationHits.get());
            } finally {
                c.disconnect();
            }
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 StreamingRedirectDemo.java
java StreamingRedirectDemo
```

**Stdout đã kiểm chứng:**

```text
HttpRetryException: true
Redirect response: 307
Redirect Location: /destination
First server body: HELLO
Destination requests: 0
```

**Ý nghĩa của từng dòng:**

- `HttpRetryException: true` là minh chứng **automatic redirect không được xử lý** khi output streaming đã bật. Đây không phải `SocketTimeoutException` hay lỗi DNS.
- `Redirect response: 307` chỉ status cần lưu ý, không phải final 200. `307` bảo toàn method theo RFC nếu ứng dụng quyết định tự follow.
- `Redirect Location: /destination` là **relative reference**; phải resolve theo URI của response phù hợp, không dùng nguyên relative string như một URL tuyệt đối.
- `First server body: HELLO` xác minh POST ban đầu **đã gửi đủ body tới server**, dù client không follow thành công.
- `Destination requests: 0` nghĩa HTTP handler trong test **không tự phát lại POST**. Nếu ứng dụng cần follow, phải khởi tạo **request mới** với body có thể phát lại và chính sách an toàn.
- Server đầu đã nhận body nên **không có cơ sở** tuyên bố operation đầu “chắc chắn chưa xử lý nghiệp vụ”. Demo không tạo side effect thật, nhưng server production có thể làm.
- `disconnect()` trong `finally` là một phần cleanup, không phải lệnh “undo POST”.

**Giới hạn:** Ví dụ chủ động dùng `setFixedLengthStreamingMode`, không kiểm thử `setChunkedStreamingMode`; Javadoc mô tả cùng hạn chế automatic auth/redirect khi output streaming được bật. Số hop, method và body do ứng dụng quyết định nếu xử lý thủ công.

## 8. HTTP/1.1 keep-alive: một TCP connection, nhiều request

Theo RFC 9112 `9.3, HTTP/1.1 mặc định cho phép **persistent connections** trừ khi có `Connection: close` hoặc điều kiện khiến connection không tiếp tục dùng được. Một TCP byte stream có thể tuần tự mang nhiều request/response nếu các message có **ranh giới tự xác định**.

```text
TCP connection #A
  │
  ├── GET /a HTTP/1.1        ──► server
  │◄─ HTTP/1.1 200 OK        (Content-Length: 2, body OK)
  │
  ├── GET /b HTTP/1.1        ──► server
  │◄─ HTTP/1.1 200 OK        (Content-Length: 3, body YES)
  │
  ├── GET /c HTTP/1.1        ──► server
  │◄─ HTTP/1.1 200 OK        (Content-Length: 1, body 1)
  │
  └── idle timeout, Connection: close, error, policy ... → TCP closes
```

**Có thể ba đối tượng `HttpURLConnection` khác nhau cùng chia sẻ TCP connection #A**. Mỗi object vẫn chỉ đại diện cho một HTTP request về mặt API; JDK quản lý kết nối vật lý ở tầng bên dưới.

### Điều kiện để reuse an toàn

- HTTP response phải được xác định kết thúc, ví dụ `Content-Length`, `Transfer-Encoding: chunked` hoặc no-body theo status/method. Response close-delimited cần EOF nên **không reuse được cùng connection ấy**.
- Client phải tiêu thụ hết response body nếu muốn reuse. Trong Java, **đọc tới hết InputStream do `HttpURLConnection` cung cấp và đóng stream** là mẫu thực tế; HTTP implementation biết framing riêng, không nhầm với raw `Socket InputStream`.
- Server phải đọc hết request body hoặc đóng connection sau response; nếu không, bytes request còn sót có thể làm request kế tiếp mất đồng bộ.
- Connection còn hợp lệ, chưa bị peer đóng/idle timeout, không có `Connection: close`, không bị lỗi I/O, và runtime pool quyết định có reuse được.
- Cùng origin/endpoint/proxy/TLS context theo chính sách pool. Đổi host/port/proxy không thể mặc định dùng cùng TCP socket.
- Bên nào cũng có quyền đóng connection khi cần; keep-alive **không phải cam kết socket sống mãi**.

### Vì sao `Connection: keep-alive` không bắt buộc với HTTP/1.1?

HTTP/1.1 **mặc định persistent**, nên header `Connection: keep-alive` thường không cần để bật chức năng. Một số cơ chế cũ trong HTTP/1.0 dùng explicit keep-alive negotiation, nhưng không được áp nó làm điều kiện bắt buộc cho HTTP/1.1.

### `Connection: close` là tín hiệu ở tầng HTTP

Nếu request hoặc response có token `close` trong header `Connection`, hai bên phải tuân thủ semantics đóng connection sau final response tương ứng. Đây là **ý định protocol có trên wire**. Nó khác lệnh Java `connection.disconnect()`, vốn không phải header tự động đảm bảo peer nhìn thấy `Connection: close` trong mọi tình huống.

## 9. Chuyện gì xảy ra ở TCP sau HTTP keep-alive?

Sau khi một response hoàn chỉnh được đọc, JDK HTTP handler có thể đặt một TCP socket đã idle vào bộ nhớ đệm kết nối để phục vụ request khác. Lần `URL.openConnection()` tiếp theo tạo **object mới**, nhưng nếu được pool chọn, network stack có thể dùng **socket cũ** thay vì TCP three-way handshake mới.

```text
HttpURLConnection instance A
  GET /first  ───────► [TCP socket #17] ─► server
  response ◄───────── [TCP socket #17]
  response stream close()
                             │
                             ▼
                        idle/keepalive pool
                             │
                             ▼
HttpURLConnection instance B
  GET /second ───────► [TCP socket #17] ─► server
  response ◄───────── [TCP socket #17]
```

Đây là **mô hình có thể xảy ra**, không phải cam kết về socket ID. Trong thực tế, JVM có thể mở mới vì server đóng, timeout, parallel requests, proxy, HTTP headers, thiếu connection đủ điều kiện, policy pooling hoặc lỗi.

### Đọc hết response body trước khi reuse

Đặc biệt tránh:

```java
// ANTI-PATTERN: không tiêu thụ hoặc đóng response body.
HttpURLConnection c = (HttpURLConnection) url.openConnection();
int code = c.getResponseCode();
// Bỏ đi, không close InputStream/ErrorStream và không cleanup.
```

Đoạn này là **anti-pattern minh họa**. Không chắc application đã giải phóng tài nguyên request; HTTP handler có thể chưa đưa socket vào trạng thái rảnh để reuse. Với body lớn, không nhất thiết nên gọi `readAllBytes()` vì có thể tốn RAM; hãy xử lý theo chunks rồi đóng stream và điều chỉnh chính sách khi muốn abort body.

**Khác biệt quan trọng:** `InputStream.readAllBytes()` trên **stream trả về bởi `HttpURLConnection`** đọc đến kết thúc entity theo HTTP implementation. Còn `readAllBytes()` trên **raw Socket.getInputStream()` chờ TCP EOF và có thể treo khi keep-alive đang mở. Không đánh đồng hai loại stream.

### `setUseCaches(false)` có tắt keep-alive không?

`URLConnection.setUseCaches(boolean)` là tham số **content caching/protocol-specific cache behavior**, không phải nút điều khiển trực tiếp vòng đời TCP keep-alive pool. Không dùng `setUseCaches(false)` để khẳng định mọi HTTP request sẽ có socket mới.

### `SO_KEEPALIVE` cũng không phải HTTP keep-alive

TCP `SO_KEEPALIVE` là cơ chế transport có thể gửi probes trên connection idle theo cấu hình hệ điều hành. HTTP keep-alive/persistent là **khả năng mang nhiều HTTP messages trên cùng connection**. Chúng khác chức năng, thời gian và API; tránh gọi cùng tên rồi kết luận sai.

## 10. `disconnect()` thực sự làm gì?

Đây là điểm quan trọng nhất của đề bài. Javadoc Java 17 mô tả `HttpURLConnection.disconnect()` bằng ý nghĩa:

> Báo rằng những request khác tới server có lẽ sẽ không sớm xảy ra.

Javadoc cũng giải thích:

- Mỗi `HttpURLConnection` instance phục vụ **một request**.
- TCP connection bên dưới **có thể được chia sẻ** bởi instance khác.
- Đóng `InputStream` hoặc `OutputStream` sau request có thể giải phóng tài nguyên của **instance**, nhưng **không ảnh hưởng tới bất kỳ persistent connection dùng chung nào** theo hợp đồng.
- Gọi `disconnect()` **có thể đóng socket bên dưới nếu persistent connection đang idle** tại thời điểm đó.
- **Không được suy ra gọi `disconnect()` sẽ khiến cùng instance dùng lại được cho một request khác.**

Từ khóa cần nhớ là **“may” — có thể**, không phải **“must” — chắc chắn**. Không có hợp đồng “một lời gọi `disconnect()` luôn sinh một TCP FIN ngay” và cũng không có hợp đồng “gọi `disconnect()` luôn giữ socket để reuse”.

### Tách bốn hành động thường bị nhầm

| Hành động | Điều bạn biết chắc | Điều không được tự suy ra |
|---|---|---|
| `responseStream.close()` | Đóng stream của request theo API | Không có gì chứng minh mọi shared keep-alive socket đóng |
| `connection.disconnect()` | Thông báo handler rằng không dự kiến request khác sớm; có thể đóng idle socket | Không chắc socket đóng ngay, không reuse được cùng object |
| `Connection: close` trên HTTP message | Đưa ra protocol directive không tiếp tục reuse connection này sau response | Không thay thế việc close Java resources một cách an toàn |
| TCP `FIN`/`RST` | Transport connection đóng/đứt | Không phải business cancellation hoặc rollback của request server |

### `disconnect()` có thể thực sự đóng socket khi nào?

Nếu persistent connection đang **idle** và implementation chọn đóng thay vì giữ cache, `disconnect()` có thể khiến socket bị đóng. Nhưng nếu server/handler vẫn đang sử dụng resource hoặc underlying connection được chia sẻ, cách hành xử khác nhau theo implementation/runtime; không nên dùng thử nghiệm của một JDK làm lời hứa cho mọi môi trường.

**Không dùng `disconnect()` như công cụ quản lý pool chính xác theo số lượng socket** hoặc cách “reset” HTTP client; nếu cần kiểm soát connection lifecycle cấp hệ thống, hãy dùng HTTP client có API lifecycle rõ ràng và đo network metrics.

### `disconnect()` có hủy một request đang xử lý trên server không?

Không có hợp đồng đó. Server có thể đã nhận request, ghi dữ liệu hoặc commit transaction. Việc client ngừng đọc/đóng connection không rollback side effect phía server; muốn cancel nghiệp vụ phải có API riêng và phản hồi đáng tin.

## 11. Java 17+: quan sát TCP reuse và `disconnect()`

Để nhìn thấy reuse thật, ví dụ này tạo server HTTP trên loopback. Trong mỗi request, server ghi nhận **remote TCP port của client**. Khi các request tuần tự từ cùng `127.0.0.1` và cùng server thấy cùng remote port, đó là một dấu hiệu hữu ích về connection reuse trong test này.

Bốn lần gọi `fetch(...)` đều tạo **một đối tượng `HttpURLConnection` mới**. Chúng đọc hết/đóng response stream. Chỉ lần thứ **ba** gọi `disconnect()` sau khi đã đóng stream; lần thứ **tư** đo xem runtime có tiếp tục dùng cùng TCP connection được hay không.

**Tệp `KeepAliveDisconnectDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

public class KeepAliveDisconnectDemo {
    private static String fetch(URL url, boolean callDisconnect) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(3000);
        connection.setReadTimeout(3000);
        try {
            if (connection.getResponseCode() != 200)
                throw new IOException("Unexpected HTTP status");
            try (InputStream input = connection.getInputStream()) {
                return new String(input.readAllBytes(), StandardCharsets.UTF_8);
            }
        } finally {
            if (callDisconnect) connection.disconnect();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        List<Integer> remotePorts = Collections.synchronizedList(new ArrayList<>());
        AtomicInteger requests = new AtomicInteger();
        server.createContext("/value", ex -> {
            try (ex) {
                remotePorts.add(ex.getRemoteAddress().getPort());
                int request = requests.incrementAndGet();
                byte[] bytes = ("R" + request).getBytes(StandardCharsets.UTF_8);
                ex.sendResponseHeaders(200, bytes.length);
                try (OutputStream output = ex.getResponseBody()) {
                    output.write(bytes);
                }
            }
        });
        try {
            server.start();
            URL url = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/value").toURL();

            String first = fetch(url, false);
            String second = fetch(url, false);
            String third = fetch(url, true);
            String fourth = fetch(url, false);

            System.out.println("Responses: " + first + "," + second
                    + "," + third + "," + fourth);
            System.out.println("Server request count: " + requests.get());
            System.out.println("First two reused TCP: "
                    + remotePorts.get(0).equals(remotePorts.get(1)));
            System.out.println("Third reused same TCP: "
                    + remotePorts.get(1).equals(remotePorts.get(2)));
            System.out.println("Fourth reused after disconnect: "
                    + remotePorts.get(2).equals(remotePorts.get(3)));
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -encoding UTF-8 KeepAliveDisconnectDemo.java
java KeepAliveDisconnectDemo
```

**Stdout đã quan sát khi chạy hai lần trên JDK thử nghiệm:**

```text
Responses: R1,R2,R3,R4
Server request count: 4
First two reused TCP: true
Third reused same TCP: true
Fourth reused after disconnect: true
```

**Đây là kết quả QUAN SÁT, KHÔNG phải cam kết đầu ra bất biến giữa hệ điều hành và JDK.** Các dòng chứa `reused TCP` có thể là `false` trong môi trường khác do runtime, thời điểm server đóng idle socket hoặc chính sách pool. Hai điều ổn định về ý nghĩa:

1. **Bốn request HTTP khác nhau** (`R1` tới `R4`) được tạo bằng **bốn đối tượng `HttpURLConnection` khác nhau**.
2. Connection reuse **có thể xảy ra** ngay cả khi mọi object chỉ phục vụ một request; và trong lần thử cụ thể này, calling `disconnect()` sau request thứ ba **không dẫn tới bằng chứng socket mới** ở request thứ tư.

### Phân tích không được suy diễn quá mức

- Cặp `getRemoteAddress().getPort()` từ cùng loopback server là dấu hiệu tốt trong test. Nhưng số port **không phải mã nhận diện socket bất biến cho mọi hoàn cảnh**: hệ điều hành có thể tái sử dụng ephemeral port sau một connection khác (hiếm trong test nhanh), proxy/NAT có thể che endpoint trong môi trường thực.
- `First two reused TCP: true` cho thấy handler đã sử dụng lại connection sau khi response #1 được đọc hết và stream đóng. Không có `Connection: keep-alive` đặc biệt trong source; HTTP/1.1 mặc định cho phép persistence.
- `Third reused same TCP: true` cho thấy connection từ request #2 còn phù hợp cho #3.
- `Fourth reused after disconnect: true` là điều người học thường bất ngờ. `disconnect()` **có thể** đóng idle socket, nhưng không có lời hứa bắt buộc trong Javadoc. Thử nghiệm này quan sát việc runtime tiếp tục reuse; môi trường khác có thể khác.
- Không có lý do gọi `disconnect()` rồi **gửi thêm request trên chính object đó**; mỗi request mới vẫn phải tạo `openConnection()` mới.
- Server test trả response `Content-Length` rõ qua `sendResponseHeaders(200, bytes.length)` và client đọc hết body. Đây là điều kiện thuận lợi cho persistent reuse.
- Không dùng `getRemoteAddress()` hoặc số port của proxy làm thước đo chắc chắn trong ứng dụng cloud; muốn đo connection pooling production, nên dùng HTTP client metrics, tracing, server connection IDs hoặc network captures được phép.

### Cleanup đúng có phải luôn gọi `disconnect()`?

Không có quy tắc “luôn phải gọi `disconnect()` sau mọi GET” mới đúng. Đọc/đóng stream là phần quan trọng cho resource lifecycle; gọi `disconnect()` có thể phù hợp khi ứng dụng muốn báo ngừng dùng endpoint/giải phóng resource, nhưng nó có thể làm giảm cơ hội reuse theo một số implementation. Mục tiêu sử dụng lâu dài và hiệu năng quyết định có gọi hay không. Ngược lại, **không bao giờ bỏ quên stream** khi đã mở.

## 12. So sánh `disconnect()`, `Connection: close` và stream close

Cả ba đều liên quan đến việc “đóng”, nhưng mỗi cái hoạt động ở một tầng.

### 12.1. `InputStream.close()`

`HttpURLConnection.getInputStream()` trả một stream cho response entity. Dùng try-with-resources để đóng nó, kể cả khi parser/consumer ném exception:

```java
// Trích đoạn: connection và expectedStatus là biến của application.
try (InputStream body = connection.getInputStream()) {
    byte[] bytes = body.readAllBytes();
    processBytes(bytes);
}
```

Đây là snippet minh họa, không phải class hoàn chỉnh; với body lớn nên xử lý streaming để tránh cấp phát mảng lớn. Đóng stream có thể giải phóng những tài nguyên gắn với **lần request đó**, nhưng không tự động có nghĩa phải đóng shared persistent socket.

### 12.2. `HttpURLConnection.disconnect()`

`disconnect()` là API local của Java HTTP handler. Nó **không phải một HTTP method gửi lên server**. Nó báo không dự kiến thêm request sớm và có thể đóng socket đang idle. Việc tương tác chính xác với keep-alive implementation là chi tiết không nên giả định cố định.

### 12.3. `Connection: close`

Đây là một header HTTP có ý nghĩa protocol:

```http
GET /last HTTP/1.1
Host: example.test
Connection: close

```

Client gửi `Connection: close` nghĩa đây là request cuối trên connection ấy và phải đóng sau khi đọc final response. Server cũng có thể gửi `Connection: close` để báo không duy trì connection sau response. Header này có thể quan sát trên wire; `disconnect()` không đồng nghĩa bắt buộc gửi header đó.

### 12.4. TCP close/FIN/RST

TCP `FIN` kết thúc một chiều gửi có thứ tự; `RST` có thể biểu thị reset/abort. Đó là sự kiện transport. Nếu server đã commit một POST trước khi connection đóng, client gọi `disconnect` hoặc thấy FIN/RST **không hoàn tác** commit.

```text
close InputStream
    → resource scope của response tại client
    → có thể giữ TCP idle/pool

HttpURLConnection.disconnect()
    → gợi ý local handler: không định dùng server sớm
    → idle socket có thể được đóng

HTTP Connection: close
    → protocol directive gửi/nhận với peer
    → không tiếp tục reuse connection sau response

TCP FIN/RST
    → sự kiện đóng/reset transport
    → không phải rollback business operation
```

## 13. Redirect và keep-alive có thể phối hợp như thế nào?

Giả sử một Java client tải `http://a.example.test/old`, nhận `302 Location: /new`, rồi `200`. Có hai biến cố khác nhau:

1. **Redirect** quyết định có gửi thêm HTTP request tới **URI mới** không.
2. **Connection persistence** quyết định request mới đó có dùng lại **TCP socket** đã mở được không.

Nếu Location vẫn cùng scheme/host/port và connection cũ còn đủ điều kiện idle, reuse có thể xảy ra. Nếu redirect sang host khác, port khác hoặc thay protocol/TLS, cần kết nối phù hợp với destination; không phải socket cũ “biến hình”. Proxy có thể tạo các mô hình khác ở từng hop; không đơn giản đếm số `HttpURLConnection` object để suy ra số TCP sockets.

### Ví dụ tình huống

| Trường hợp | Redirect? | TCP socket mới? |
|---|---|---|
| GET `/old` → 302 `/new` cùng host | Có, nếu follow | **Có thể reuse** nếu đủ điều kiện |
| GET `/old` → 302 sang host khác | Có, nếu follow | Không được mặc định chia sẻ cùng endpoint socket |
| GET `/old` → no-follow trả 302 | Không có request tới URL mới từ object này | Không có network request tiếp theo do follow |
| Server trả 200 `Connection: close` | Không liên quan redirect | Connection hiện tại không tiếp tục reuse |
| Gọi `disconnect()` sau response | Không phải redirect | Socket idle **có thể** đóng hoặc vẫn reusable tùy runtime |
| Đọc dở response rồi bỏ stream | Không nhất thiết redirect | Không đủ điều kiện reuse an toàn theo RFC nếu body chưa tiêu thụ |
| POST streaming nhận 307 | Cần đánh giá thủ công | `HttpRetryException`, không tự resend body |

Đừng dùng redirect loop để “refresh socket” hoặc dựa vào keep-alive để kết luận mọi redirect rẻ về chi phí mạng. Nếu đổi origin, TLS, proxy, authentication hoặc DNS, độ trễ và rủi ro bảo mật có thể thay đổi.

## 14. Xử lý lỗi HTTP và tài nguyên trong ứng dụng thật

`getInputStream()` có thể ném `IOException` với status lỗi (thường 4xx/5xx). `HttpURLConnection` cung cấp `getErrorStream()` để ứng dụng đọc response body lỗi **nếu có**. Đừng chỉ catch `IOException` rồi bỏ response body; nó có thể chứa một thông điệp JSON hữu ích nhưng cần xử lý giới hạn kích thước/định dạng.

### Mẫu có kiểm soát

```java
// Trích đoạn minh họa, không độc lập; URL 'url' được xác minh trước.
HttpURLConnection c = (HttpURLConnection) url.openConnection();
c.setInstanceFollowRedirects(false);
c.setConnectTimeout(3000);
c.setReadTimeout(5000);
try {
    int status = c.getResponseCode();
    InputStream selected = status >= 400
            ? c.getErrorStream()
            : c.getInputStream();

    if (selected != null) {
        try (InputStream body = selected) {
            // Stream theo chunks, không nhất thiết readAllBytes cho body lớn.
            byte[] buffer = new byte[8192];
            while (body.read(buffer) != -1) {
                // Decode/consume bytes có giới hạn, không bỏ qua lỗi.
            }
        }
    }
} finally {
    c.disconnect();
}
```

Đây là **mẫu minh họa không phải class standalone**. Việc cố tình `disconnect()` sau every request là một policy cleanup đơn giản trong mẫu; nếu bạn tối ưu pooling, có thể ưu tiên đọc hết và đóng stream, quản lý connection lifecycle theo client library/documentation. Đừng gọi `getErrorStream()` khi chưa có error và mặc định nó luôn trả stream: Javadoc cho phép trả `null`.

### Connect timeout và read timeout

- `setConnectTimeout(ms)` đặt thời gian chờ **thiết lập kết nối** (giá trị 0 thường là vô hạn theo contract Java).
- `setReadTimeout(ms)` đặt thời gian chờ **đọc dữ liệu** trên connection; nếu không có dữ liệu đủ thời gian có thể ném `SocketTimeoutException`.
- **Chúng không phải** một tổng deadline end-to-end chặt chẽ cho toàn bộ redirect chain, body streaming hay business transaction. Có thể cần deadline tổng do application tự quản lý.
- Nếu redirect qua nhiều hops, mỗi hop có thể có connection và I/O riêng; không xem một `readTimeout(3000)` là “toàn bộ chuỗi chuyển hướng chắc không quá 3 giây”.
- Nếu caller timeout/connection đứt sau một POST, không tự retry với request ID mới vì **server có thể đã xử lý side effect**.

### Khi nào cần đóng request output stream?

Với POST/PUT có body, dùng try-with-resources cho `getOutputStream()` để đảm bảo bytes còn buffered được flush theo contract stream, hoặc để phát hiện lỗi ghi. **Đóng output stream không phải business ACK.** Sau đó đọc response status/body, vì server có thể trả 4xx/5xx hay 3xx; không coi “write không ném exception” là request thành công.

## 15. Những sai lầm hay gặp

| Sai lầm | Hậu quả hoặc hiểu sai | Cách sửa |
|---|---|---|
| `openConnection()` = TCP connect mới ngay | Đếm sai số socket/chi phí | Phân biệt Java object và network I/O trigger |
| Một `HttpURLConnection` dùng lại cho nhiều requests | Vi phạm mô hình one-request-per-instance | Mỗi request tạo connection object mới |
| `setFollowRedirects(false)` trong library dùng chung JVM | Thay đổi static behavior của module khác | `setInstanceFollowRedirects(false)` cho từng request |
| Bật follow rồi coi final 200 là không hề qua 302 | Mất thông tin audit redirect | Tắt auto-follow nếu cần kiểm tra từng hop |
| Tự follow mọi `Location` mà không validate | SSRF, lộ credentials/file nội bộ | Allowlist scheme/host/port, TLS, hop limit |
| Dùng redirect GET để suy ra POST 307 tự resend được | Mất/sai request body | Xét method, streaming mode, replayability |
| POST streaming nhận `HttpRetryException` rồi cứ retry vô hạn | Trùng side effect, lộ dữ liệu | Có policy, request ID/idempotency và explicit resend |
| `setChunkedStreamingMode` nhưng server không hỗ trợ chunked | 411/400/connection failure | Kiểm tra server, fallback protocol phù hợp |
| `getResponseCode()==200` rồi bỏ response stream | Leak, giảm khả năng reuse | Đọc đủ/đóng stream hoặc abort theo policy |
| Gọi `disconnect()` nghĩa socket chắc chắn đóng | Suy diễn sai; test có thể vẫn reuse | Dùng network metrics, hiểu Javadoc “may” |
| Gọi `disconnect()` để reset object cho request mới | Dùng sai API lifecycle | Mở `HttpURLConnection` mới |
| Không dùng `Connection: close` nhưng vẫn yêu cầu cấm reuse tuyệt đối | Không có protocol signal | Cấu hình client/server/proxy theo hợp đồng |
| `setUseCaches(false)` = tắt keep-alive | Nhầm HTTP caching với connection reuse | Phân biệt hai loại cache |
| TCP SO_KEEPALIVE = HTTP/1.1 persistence | Nhầm transport probes với reuse | Quản lý ở đúng tầng |
| `readAllBytes` trên raw TCP socket | Có thể chờ EOF vô hạn khi keep-alive | Dùng HTTP parser/library framing |
| Chỉ dùng `getInputStream()` cho 404/500 | IOException, mất body lỗi | `getErrorStream()` khi có response error |
| Không giới hạn redirect hops | Vòng lặp, SSRF, tốn tài nguyên | Hop count, visited URLs, deadline tổng |
| Bỏ qua cross-origin auth | Credential leakage | Không copy Authorization/Cookie tùy tiện |
| Tin status/network failure nghĩa POST chắc chưa commit | Retry có thể tạo dữ liệu trùng | Business ID, dedup/idempotency, status query |
| Bật `disconnect` trên mọi GET để “tăng hiệu năng” | Có thể làm giảm reuse trong một số runtimes | Đóng response đúng cách, benchmark policy |

### Sự khác nhau giữa lỗi HTTP và lỗi transport

- HTTP `404/500` là **response có status HTTP**, server có thể trả error body.
- `SocketTimeoutException` là **I/O timeout**, không phải HTTP status `408`.
- `HttpRetryException` của streaming redirect/auth nói **handler không tự resend**, không chứng minh server chưa nhận body.
- `IOException`/`ConnectException` khi không kết nối được khác với server đã trả `503`.
- `disconnect()` không tạo một HTTP status nào; nó là lời gọi local và có thể ảnh hưởng network resource theo implementation.

## 16. Khi nào dùng HttpClient hiện đại thay cho HttpURLConnection?

Từ Java 11, module `java.net.http` cung cấp `HttpClient` cho workflow HTTP mới, hỗ trợ `HttpRequest`/`HttpResponse`, `sendAsync` với `CompletableFuture`, HTTP/2 theo điều kiện, response body handlers và chính sách redirect rõ ràng.

Ví dụ cấu hình:

```java
// Snippet minh họa, không phải chương trình độc lập.
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.test/resource"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> result = client.send(
        request, HttpResponse.BodyHandlers.ofString());
```

Chú ý: đoạn trên cần imports từ `java.net.http.*`, `java.net.URI` và `java.time.Duration`; URI `example.test` là minh họa. Với Java 17 **`HttpClient.Redirect.NEVER` là default**, khác với **`HttpURLConnection` static follow redirects mặc định true**. Không tự mang assumptions từ API này sang API kia.

`HttpClient` hiện đại thường thích hợp khi cần async requests, explicit redirect policy, HTTP/2, body publisher và khả năng quản lý request phức tạp. Nhưng **không nên nhầm một loại client “mới” tự đảm bảo retry idempotent, cross-origin authorization hay business transaction đúng**: mọi ranh giới bảo mật vẫn cần policy của ứng dụng.

### Không đổi API chỉ để “chắc chắn disconnect đóng TCP”

Mục tiêu của HTTP connection pooling là **tái sử dụng kết nối an toàn và giảm overhead**. Chuyển sang `HttpClient` không có nghĩa mỗi request dùng một socket mới. Nếu yêu cầu đặc biệt cần cắt kết nối ngay, thiết kế phải xét đúng lifecycle API, server và proxy; không có nút đơn giản nào thay cho hiểu connection pooling.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `url.openConnection()` trả một `HttpURLConnection`. Có chắc TCP socket vừa được mở không?  
**Đáp án:** Không. Nó có thể chỉ tạo object chưa connect; `getResponseCode` hoặc I/O getter mới kích hoạt connect/request.

**Câu 2.** `HttpURLConnection` có được dùng cùng object để gửi GET tới hai path khác nhau?  
**Đáp án:** Không theo mô hình API; một instance đại diện một request. Hãy tạo object mới cho request mới. Auto redirect có thể tạo thêm network hop trong cùng logical request.

**Câu 3.** HTTP/1.1 mặc định giữ connection persistent hay đóng sau mỗi response?  
**Đáp án:** Persistent nếu không có điều kiện đóng. Reuse thực tế còn phụ thuộc message framing, server policy và pool.

**Câu 4.** Khi bật `setInstanceFollowRedirects(true)` và server trả 302→200, `getResponseCode()` thường thấy status nào?  
**Đáp án:** Final 200 nếu follow thành công như demo, không phải intermediate 302.

**Câu 5.** Muốn kiểm tra `Location` trước khi quyết định follow, cấu hình gì?  
**Đáp án:** `setInstanceFollowRedirects(false)` trước connect, rồi đọc `getResponseCode/getHeaderField("Location")` và validate URI.

**Câu 6.** `HttpURLConnection.setFollowRedirects(false)` có khác `setInstanceFollowRedirects(false)`?  
**Đáp án:** Có. Phương thức đầu là static/class-wide, phương thức sau áp dụng cho object cụ thể.

**Câu 7.** Server trả 307 sau một POST streaming fixed-length. Có đảm bảo handler tự phát lại body?  
**Đáp án:** Không. Javadoc nói streaming mode không thể tự xử lý redirect/auth, có thể ném `HttpRetryException` khi đọc response.

**Câu 8.** `HttpRetryException.responseCode()` là 307, và `getLocation()` là `/new`. Có nên gửi POST tiếp ngay?  
**Đáp án:** Chỉ khi đã validate target, method/body replayability, bảo mật và idempotency; server đầu có thể đã xử lý side effect.

**Câu 9.** Gọi `disconnect()` sau GET có nghĩa JDK chắc chắn đóng TCP socket idle và request sau phải mở socket mới?  
**Đáp án:** Không. Javadoc nói **may close**, không phải **must close**. Demo có runtime vẫn reuse sau disconnect.

**Câu 10.** `InputStream.close()` của response và `Connection: close` khác gì?  
**Đáp án:** Stream close là API cleanup local; `Connection: close` là signal HTTP trên wire yêu cầu chấm dứt persistence sau response.

**Câu 11.** `setUseCaches(false)` có phải cách đúng để tắt TCP keep-alive?  
**Đáp án:** Không. Nó liên quan resource caching, không phải một nút quản lý socket persistence.

**Câu 12.** Client không đọc hết response body nhưng muốn dùng lại cùng connection. Có an toàn?  
**Đáp án:** Không được giả định; RFC 9112 yêu cầu đọc toàn bộ response body nếu muốn tái sử dụng cùng connection, hoặc không reuse/đóng theo policy.

**Câu 13.** `getInputStream()` ném lỗi khi status 404. Làm sao đọc body lỗi nếu server gửi?  
**Đáp án:** `getErrorStream()` có thể trả body; kiểm tra null và đóng sau khi đọc.

**Câu 14.** Dòng `Fourth reused after disconnect: true` của demo chứng minh mọi JDK luôn reuse sau disconnect?  
**Đáp án:** Không. Đó chỉ là quan sát trên runtime thử nghiệm; môi trường khác có thể trả false.

**Câu 15.** Dùng `Connection: keep-alive` có cần thiết trong mọi request HTTP/1.1 không?  
**Đáp án:** Không. HTTP/1.1 mặc định persistent nếu chưa có điều kiện đóng.

**Câu 16.** `disconnect()` sau một POST đã gửi body có tự hoàn tác database transaction ở server không?  
**Đáp án:** Không. Cần giao thức/transaction cancellation riêng hoặc xác minh trạng thái nghiệp vụ.

**Câu 17.** Có nên tự động follow redirect sang host mới với `Authorization` và body chứa dữ liệu cá nhân không?  
**Đáp án:** Không mặc định. Cần kiểm tra origin, scheme/TLS, allowlist, quyền gửi body và bảo vệ credentials.

**Câu 18.** Cấu hình redirect mặc định của `HttpURLConnection` và `java.net.http.HttpClient` Java 17 có giống nhau?  
**Đáp án:** Không. `HttpURLConnection` class setting mặc định true, còn `HttpClient.Redirect` mặc định `NEVER`.

**Câu 19.** Muốn giới hạn toàn bộ redirect chain dưới 5 giây, chỉ `setReadTimeout(5000)` có đủ không?  
**Đáp án:** Không chắc. Read timeout không phải deadline tổng cho mọi hop; cần coordinator deadline riêng.

**Câu 20.** Nếu TCP keep-alive probe được bật, có nghĩa mọi HTTP request dùng lại cùng socket?  
**Đáp án:** Không. TCP keepalive kiểm tra/duy trì connection idle ở transport; HTTP reuse còn phụ thuộc protocol framing và runtime policy.

## 18. Checklist và tóm tắt

- [ ] Mỗi **`HttpURLConnection` object** là một logical HTTP request; transport có thể chia sẻ giữa objects.
- [ ] HTTP redirect là **response 3xx + Location**; việc follow có thể tạo thêm request và thay URI/method/body theo policy.
- [ ] Dùng **`setInstanceFollowRedirects(false)`** nếu cần xem Location và xác nhận target trước khi follow; tránh sửa static global không cần thiết.
- [ ] `HttpURLConnection` mặc định follow redirects theo Javadoc Java 17, nhưng **không giả định mọi status/method/scheme được follow**.
- [ ] Với POST/PUT, kiểm tra method preservation, khả năng **replay body** và business idempotency trước resend.
- [ ] Với `setFixedLengthStreamingMode` hoặc `setChunkedStreamingMode`, hiểu giới hạn **không tự follow/auth resend**; xử lý `HttpRetryException` có chủ đích.
- [ ] HTTP/1.1 persistent không đòi `Connection: keep-alive` trong mọi message; **`Connection: close`** có semantics chấm dứt persistence.
- [ ] Đọc **đúng và đủ** response body, đóng InputStream/ErrorStream khi sử dụng; không đọc raw TCP đến EOF để tìm message length trên persistent connection.
- [ ] `disconnect()` **không** phải “đóng ngay mọi socket”, không phải reset instance, không phải rollback server; Javadoc nói socket idle **có thể** được đóng.
- [ ] Không đồng nhất HTTP keep-alive với TCP `SO_KEEPALIVE` hay HTTP content caching.
- [ ] Sử dụng `setConnectTimeout` và `setReadTimeout` nhưng bổ sung deadline tổng/chính sách retry nếu nghiệp vụ yêu cầu.
- [ ] Không để redirect tới host không tin cậy tự nhận credentials hoặc body nhạy cảm; kiểm tra allowlist, TLS, hop count và observability.
- [ ] Khi cần HTTP/2, async và redirect policy có cấu hình rõ, cân nhắc **`java.net.http.HttpClient`**, không mang assumptions của `HttpURLConnection` sang API mới.

**Kết luận then chốt:** redirect quyết định **URI/method/request tiếp theo**; keep-alive quyết định liệu **TCP socket có thể dùng lại**; `disconnect()` chỉ là **một lời gọi local về việc không dự kiến request mới sớm và có thể đóng idle socket**. Cả ba liên quan nhưng không đồng nhất. Hiểu rõ ranh giới này giúp tránh request mất dữ liệu, redirect nguy hiểm, rò rỉ streams và những nhận định sai khi đo số TCP connections.

### Tài liệu chính thức

- [Java 17 `HttpURLConnection` — one-request-per-instance, redirects, streaming, disconnect](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html)
- [Java 17 `URLConnection` — lifecycle, connect, input/output streams, timeouts](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html)
- [Java 17 `HttpRetryException` — response code, Location, reason](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpRetryException.html)
- [Java 17 `HttpsURLConnection` — HTTPS over TLS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html)
- [RFC 9112 `9.3–9.6 — HTTP/1.1 persistence and close](https://www.rfc-editor.org/rfc/rfc9112.html#section-9.3)
- [RFC 9110 `15.4 — HTTP redirect semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.4)
- [Java 17 `HttpClient.Redirect` — HTTP client modern redirect policy](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html)
