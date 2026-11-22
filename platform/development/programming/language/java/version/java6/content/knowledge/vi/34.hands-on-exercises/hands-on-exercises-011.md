# Thực hành Java 17+: Máy chủ kiểm thử HTTP và quản lý cookie theo phiên

## 1. Giới thiệu và mục tiêu

HTTP là giao thức **không lưu trạng thái giữa các request**; máy chủ không tự nhớ một request `GET /me` sau `POST /login` thuộc cùng client. Trong ứng dụng thực tế, **session cookie** thường mang một **session ID vô nghĩa, khó đoán**. Client giữ ID trong cookie và tự gửi lại qua header `Cookie`; server dùng ID để tra một **bản ghi phiên ở phía máy chủ**, kiểm tra hạn sử dụng và trạng thái hiệu lực. Chính bản ghi server mới quyết định request có được chấp nhận hay không.

Bài thực hành thuộc chủ đề **Thực hành**, đề mục **“Máy chủ kiểm thử HTTP và quản lý cookie theo phiên”**. Ta tự dựng một **HTTP server nhỏ, chạy cục bộ trên `127.0.0.1` và cổng ngẫu nhiên**, dùng `com.sun.net.httpserver.HttpServer` có sẵn trong JDK; tạo các `java.net.http.HttpClient` dùng `CookieManager` riêng biệt để kiểm tra vòng đời phiên.

Kết quả đạt được:

1. Tạo **máy chủ HTTP loopback-only** bằng `HttpServer.create(new InetSocketAddress(..., 0), backlog)` và đóng nó qua `stop(0)`.
2. Định nghĩa bốn endpoint: `GET /health`, `POST /login`, `GET /me`, `POST /logout`; nhận diện `200`, `401`, `404` và `405`.
3. Tạo token phiên bằng `SecureRandom` 32 bytes (256-bit random input), encode Base64URL không padding, dài **43 ký tự**; chỉ trả token trong `Set-Cookie`, không đưa nó vào response body hoặc logs.
4. Đặt cookie `DEMO_SESSION` với `Path=/`, `HttpOnly`, `SameSite=Lax`, `Max-Age=120`. Giải thích vì sao ví dụ HTTP loopback **không** đặt `Secure`, nhưng HTTPS production **phải** đặt `Secure`.
5. Dùng `HttpClient.Builder.cookieHandler(CookieManager)`, `CookiePolicy.ACCEPT_ORIGINAL_SERVER` và `CookieStore` để mô phỏng hai cookie jars độc lập.
6. Kiểm chứng request kế tiếp mang cookie trở lại, và client chưa đăng nhập vẫn nhận `401`.
7. **Xoay session ID khi đăng nhập lại** và thu hồi ID cũ ở phía server; không chấp nhận ID do client tự bịa ra.
8. `POST /logout` **thu hồi bản ghi server** và trả cookie xóa với `Max-Age=0`; chỉ xóa cookie phía client là **chưa đủ**.
9. Phân biệt **thời hạn cookie trong client** với **thời gian hiệu lực session ở server**; dùng đồng hồ giả để kiểm thử `120s` mà không ngủ hai phút.
10. Hiểu cách Java `CookieManager` có thể gửi cookie dạng `DEMO_SESSION="..."` kèm metadata `$Version`/`$Path`; parser kiểm thử nhận cả dạng quoted/unquoted, vẫn xác nhận ID nghiêm ngặt.
11. Có chế độ chạy **automated test** và chế độ **`serve` thủ công** để thử bằng `curl`; chế độ serve dùng đồng hồ thực, automated test dùng đồng hồ giả có thể advance.
12. Biết giới hạn bảo mật: đây **không phải** hệ thống xác thực thật; không có password validation/CSRF protection/TLS/rate limiting/distributed session store. Chỉ sử dụng trong phòng thí nghiệm.

**Special Note áp dụng nguyên văn:** “Note : Hãy chỉ lấy các kiến thức vẫn còn áp dụng đến hiện giờ, không lấy các kiến thức lỗi thời hoặc đã legacy hiện nay”. Các APIs `HttpServer` (`jdk.httpserver`), `HttpClient` (`java.net.http`), `CookieManager`, `CookieStore`, `HttpCookie`, `SecureRandom`, Java records và `ConcurrentHashMap` đều là APIs hiện hành, đối chiếu Javadoc **Java SE/JDK 26**. Toàn bộ chương trình biên dịch với **`javac --release 17`** và đã chạy thành công trên Windows OpenJDK 24. Không dùng `sun.net.httpserver.*`, `HttpSession` của một servlet container không tồn tại trong bài hoặc API lỗi thời.

## 2. Kiến trúc bài thực hành

```text
+-----------------------------+     HTTP trên 127.0.0.1:<port>
| Client A                    | -------------------------------+
| HttpClient + CookieManager A|                                |
| CookieStore A               |                                v
+-----------------------------+          +-------------------------+
                                         | HttpServer              |
+-----------------------------+          | /health GET             |
| Client B                    | -------> | /login  POST            |
| HttpClient + CookieManager B|          | /me     GET             |
| CookieStore B               |          | /logout POST            |
+-----------------------------+          +-------------------------+
                                                   |
                                                   v
                                        ConcurrentHashMap<String, Session>
                                        token  -> (user, expiresAt)
                                        SecureRandom + server-time
```

Điểm phân vai:

- **Server** quyết định ID nào hợp lệ, quyền truy cập và hạn sử dụng, không tin dữ liệu user do client tự ghi vào cookie.
- **Client** giữ ID và tự gắn header `Cookie` khi gửi request tiếp theo, theo cookie policy/path/host.
- **`CookieManager`** quản lý cookie cho Java HTTP client; **nó không thay thế** session store hoặc logic xác thực phía server.
- Hai `CookieManager` riêng biệt không chia sẻ cookie jars. Không gọi `CookieHandler.setDefault(...)` toàn JVM trong ví dụ vì điều đó dễ vô tình chia sẻ cookie state.
- **Chỉ bind 127.0.0.1**: không lắng nghe `0.0.0.0` hay public interface. Port `0` yêu cầu OS gán một cổng còn rảnh; sau `HttpServer.create` đọc số cổng thật từ `server.getAddress().getPort()`.

### 2.1. Mọi HTTP request có ngữ cảnh riêng

`HttpExchange` đại diện cho một request/response. Handler gọi `getRequestMethod()`, `getRequestURI()`, `getRequestHeaders()`; đặt `Set-Cookie`/`Content-Type` trong `getResponseHeaders()`, sau đó gọi `sendResponseHeaders(status, bodyLength)` và ghi bytes qua `getResponseBody()`. Phải đóng response body stream; ví dụ dùng `try (OutputStream out = ...)`.

**Không** giữ một `HttpExchange` để dùng lại cho request tiếp theo; nó thuộc về đúng một exchange. Session store nằm ngoài các exchanges.

### 2.2. Vì sao chỉ tạo một HttpContext("/")?

`HttpServer` chọn context theo longest matching path prefix. Nếu chỉ có context `"/"` mà handler không kiểm tra path đầy đủ, một đường dẫn không dự định có thể bị xử lý nhầm. Ví dụ dùng `server.createContext("/", this::handle)` và trong handler **so sánh exact** `"/health"`, `"/login"`, `"/me"`, `"/logout"`; mọi path khác trả `404`. Khi phát triển ứng dụng lớn, nên tách handlers/context/middleware rõ ràng và có test router.

## 3. HTTP contract của server

| Endpoint | Method | Có cần phiên? | Trả về khi thành công | Lỗi/đặc biệt |
| --- | --- | --- | --- | --- |
| `/health` | `GET` | Không | `200` và body `ok` | Method khác → `405` |
| `/login` | `POST` | Không | `200`, body `logged-in`, header `Set-Cookie` | Luôn cấp phiên demo, **không kiểm tra credentials** |
| `/me` | `GET` | Có | `200`, body `user=student` | Không có, giả, bị thu hồi hoặc hết hạn → `401` |
| `/logout` | `POST` | Không bắt buộc | `200`, body `logged-out`, header xóa cookie | Xóa bản ghi server nếu có; lặp lại vẫn `200` |
| Mọi path khác | Bất kỳ | — | — | `404` body `not-found` |

Sai HTTP method trên endpoint có khai báo nhận `405 Method Not Allowed`, header `Allow` tương ứng. Request path được kiểm tra **chính xác**, không dựa vào prefix tùy tiện. Server luôn trả `Content-Type: text/plain; charset=utf-8`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` trong fixture.

### 3.1. Luồng khởi tạo phiên

```http
POST /login HTTP/1.1
Host: 127.0.0.1:<port>

HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8
Cache-Control: no-store
Set-Cookie: DEMO_SESSION=<random-token>; Path=/; HttpOnly; SameSite=Lax; Max-Age=120

logged-in
```

Ví dụ trên **minh họa protocol**; `<port>` và `<random-token>` là ký hiệu phải thay bằng giá trị thực, không phải output cố định. Token thực được random và **không nên in trong báo cáo/logs**.

Khi `POST /login` tới:
1. Đọc cookie phiên cũ **nếu có**, thu hồi token đó ở server store. Đây là rotation khi chuyển sang một phiên đăng nhập mới; không tái sử dụng token do client đưa.
2. Sinh **32 bytes** với `SecureRandom.nextBytes`; Base64URL without padding cho chuỗi token 43 chars.
3. Lưu `token -> Session("student", expiresAt = now + 120s)` trong `ConcurrentHashMap`.
4. Trả `Set-Cookie` trên HTTP response; body chỉ là `logged-in`, không có token.
5. `CookieManager` của client, nếu policy chấp nhận, lưu cookie theo URI/Path và gửi lại trên request sau.

`POST /login` trong bài **không thực hiện authentication**, mục tiêu là test cookie/session lifecycle. Trên server thực, chỉ cấp phiên **sau khi** xác minh credentials/identity, có rate limiting, chống credential stuffing và step-up auth khi cần.

### 3.2. Luồng request được xác thực bằng phiên

```http
GET /me HTTP/1.1
Host: 127.0.0.1:<port>
Cookie: DEMO_SESSION=<random-token>

HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8
Cache-Control: no-store

user=student
```

Server:
- Trích token từ header `Cookie`, không lấy từ URL query, fragment hay response body.
- Từ chối token thiếu, trùng tên, format không hợp lệ hoặc không tồn tại trong store.
- Từ chối token có `currentTime >= expiresAt` và xóa bản ghi khi phát hiện.
- Chỉ trả user nếu bản ghi server tồn tại và chưa hết hạn.

Không được tin một cookie chứa trực tiếp `user=admin` hay `role=owner` khi dữ liệu đó chưa được ký/xác minh phù hợp. Bài dùng **opaque session ID**; vai trò/người dùng nằm trong `Session` phía server.

### 3.3. Luồng logout

```http
POST /logout HTTP/1.1
Host: 127.0.0.1:<port>
Cookie: DEMO_SESSION=<random-token>

HTTP/1.1 200 OK
Set-Cookie: DEMO_SESSION=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0

logged-out
```

`Max-Age=0` yêu cầu client **xóa cookie**, còn `sessions.remove(token)` **thu hồi quyền** ngay từ phía server (trong giới hạn concurrent requests của fixture). Nếu chỉ yêu cầu trình duyệt xóa cookie mà không thu hồi server record, bản sao ID bị đánh cắp vẫn có thể sử dụng. Test có bước tái phát lại token cũ và khẳng định `401`.

## 4. Cookie không đồng nghĩa với bản ghi phiên

| Thành phần | Lưu ở đâu? | Ai chịu trách nhiệm? | Điều kiện hết hiệu lực |
| --- | --- | --- | --- |
| Header `Set-Cookie` | Response của server | Server tạo cookie instruction | Browser/client áp dụng nếu chấp nhận |
| Header `Cookie` | Request từ client | Client gửi theo cookie store/policy | Phụ thuộc client |
| `HttpCookie` | `CookieStore` của Java client | `CookieManager` | `Max-Age`/`Expires`/policy theo client clock |
| `Session` | `ConcurrentHashMap` của server thử nghiệm | Server | `expiresAt`, logout, rotation, process shutdown |
| Session ID | Trong cookie và key của server session map | Sinh phía server; client chỉ giữ và gửi | Thu hồi/xóa/expire, không được suy đoán từ username |

**Hai bộ đếm giờ độc lập:** Trong automated test, `now` của server có thể nhảy từ `2026-01-01T00:00:00Z` sang `00:02:01Z` ngay lập tức; `HttpCookie` của client vẫn dùng **đồng hồ thật của JVM** và có thể chưa đánh dấu cookie hết hạn. Dù client vẫn gửi ID đó, server **phải trả `401`** vì server-side TTL đã hết.

**Không đợi 120 giây trong unit/integration test:** dùng đồng hồ giả điều khiển được để test nhanh và ổn định. Ngược lại, chế độ `serve` thủ công của ví dụ dùng `Instant.now()` thật, do đó TTL của server cũng trôi theo thời gian thực. Không để một server thử tay dùng đồng hồ cố định — điều đó sẽ khiến session không bao giờ hết hạn ở phía server.

### 4.1. Cookie trình duyệt theo phiên và session ID là hai khái niệm

- **Session cookie của browser** thường nghĩa là cookie **không có `Max-Age`/`Expires`**; browser giữ theo lifecycle phiên của nó (có thể được khôi phục bằng session restore, không phải ranh giới bảo mật đáng tin).
- **Cookie chứa session ID** chỉ nói nó mang ID tham chiếu đến phiên server; nó **có thể** có `Max-Age`.
- Ví dụ dùng `Max-Age=120` để kiểm chứng client expiry header, nên đó là một cookie có **hạn lưu trữ 120 giây**, nhưng nội dung vẫn là session ID.
- Server phải có TTL độc lập. Không ủy quyền xác định session validity hoàn toàn cho browser cookie deletion.

Nếu muốn browser-session cookie, có thể **bỏ `Max-Age`/`Expires` khỏi Set-Cookie**, nhưng vẫn phải áp server-side expiration/revocation. Chỉ xóa browser cookie không thay thế logout server.

### 4.2. Cookie host và path

Bài **không ghi `Domain`** vào `Set-Cookie`, vì muốn host-only cookie. Cookie scope theo host/path; **port không tạo một ranh giới cách ly cookie như origin**, nên dùng chung host với hai service ở ports khác nhau có thể gây va chạm tên cookie. Trong test chỉ có một server loopback, cần mỗi client có CookieManager riêng.

`Path=/` giúp cookie được gửi tới cả `/me` và `/logout`. Đây là routing scope **không phải** authorization mechanism: không dùng Path để ngăn JavaScript ở các đường dẫn khác đánh cắp cookie. Trong production, dùng `Domain` và `Path` càng hẹp càng tốt mà không phá luồng ứng dụng; ưu tiên cookie name prefix `__Host-` trên HTTPS khi phù hợp.

### 4.3. HttpOnly, SameSite, Secure

| Thuộc tính | Tác dụng chính | Giới hạn cần nhớ |
| --- | --- | --- |
| `HttpOnly` | Browser không cho script đọc giá trị qua `document.cookie` | Không ngăn XSS gửi các request kèm cookie |
| `SameSite=Lax` | Browser hạn chế gửi cookie trong một số cross-site requests | Chỉ phòng thủ bổ trợ chống CSRF; không thay CSRF token/Origin validation |
| `Secure` | Chỉ gửi cookie qua HTTPS (có ngoại lệ đặc biệt của browser cho localhost) | Không bảo vệ khi server không dùng TLS hoặc token bị đánh cắp từ nơi khác |
| `Path=/` | Client gửi cookie tới các paths phù hợp | Không phải cơ chế access control |
| Không có `Domain` | Host-only cookie | Cookie còn có thể áp dụng giữa các ports cùng host |
| `Max-Age=120` | Client được yêu cầu hết hạn sau 120 giây | Không thay thế server TTL |
| `Max-Age=0` | Client được yêu cầu xóa cookie | Không hủy session server nếu server không revoke |

**Quan trọng:** Ví dụ chỉ chạy HTTP trên loopback nên **không** đặt `Secure`, để Java HttpClient gửi cookie được khi dùng `http://127.0.0.1`. **Tuyệt đối không sao chép cấu hình không có Secure sang production**: triển khai HTTPS và dùng `Secure; HttpOnly; SameSite=Strict/Lax` theo yêu cầu ứng dụng. Có thể dùng cookie `__Host-SESSION` trên HTTPS với `Secure; Path=/` và không có Domain. Không dùng tên `__Host-` cho cookie HTTP không có Secure — không đáp ứng ràng buộc tên prefix ở browser.

### 4.4. Java HttpCookie không phải trình duyệt web

`java.net.HttpCookie` trong JDK cung cấp hỗ trợ **một phần** cho RFC 6265 và các cookie specs cũ; `CookieManager` quản lý `CookieStore`/policy, **không** triển khai đầy đủ các chính sách browser hiện đại như SameSite theo top-level-site context. Trong fixture:
- Header `Set-Cookie` **chứa** `SameSite=Lax` (được test bằng text trên response).
- `HttpCookie.isHttpOnly()`, `getPath()` và `getMaxAge()` được kiểm chứng trong Java CookieStore.
- **Không** dùng `CookieManager` test làm bằng chứng browser thực sẽ áp dụng SameSite/CSRF như thế nào. Muốn xác minh behavior browser, chạy browser integration tests riêng.

## 5. Java CookieManager và tình huống Cookie header có dấu ngoặc kép

### 5.1. Cấu hình client đúng cách

```java
CookieManager manager = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
HttpClient client = HttpClient.newBuilder()
        .cookieHandler(manager)
        .connectTimeout(Duration.ofSeconds(3))
        .build();
```

Đây là **snippet**, đầy đủ import/context ở file mã mục 8. `CookieManager(null, ...)` tạo in-memory CookieStore; `CookiePolicy.ACCEPT_ORIGINAL_SERVER` chỉ nhận cookie theo policy origin server. Không bắt buộc phải gọi global `CookieHandler.setDefault`. Khi cần hai người dùng tách biệt, tạo **hai CookieManagers và hai HttpClients** khác nhau.

Các loại:
- `java.net.CookieHandler`: abstraction cho cookie request/response handling.
- `java.net.CookieManager`: implementation phối hợp policy và store.
- `java.net.CookieStore`: lưu, liệt kê, xóa cookies; `getCookies()` không phải “toàn bộ session server”.
- `java.net.HttpCookie`: object mô tả name/value/domain/path/max-age/HttpOnly/Secure/version.
- `java.net.http.HttpClient`: JDK client hiện đại, gắn CookieHandler thông qua builder.
- `CookiePolicy.ACCEPT_NONE`: chủ động từ chối tất cả cookies nhận được; login response có thể `200` nhưng request sau không giữ được session.

### 5.2. Khác biệt thực đã gặp trong kiểm thử

Lúc đầu server chỉ kiểm tra regex trên cookie value raw và bị `401` sau khi client đã nhận cookie. Nguyên nhân: trên JVM thử nghiệm, Java `CookieManager` gửi dạng **versioned/quoted**:

```text
Cookie: $Version="1"
Cookie: DEMO_SESSION="<base64url-value>";$Path="/";$Domain="127.0.0.1"
```

Đây là **minh họa cú pháp**, Java HTTP API có thể kết hợp/sắp xếp các Cookie headers khác nhau, không cam kết byte-for-byte như hai dòng trên. `<base64url-value>` là token placeholder, không phải secret thật. `$Version`, `$Path` và `$Domain` trong output này là metadata theo cách Java cookie client biểu diễn; **không nên coi chúng là session cookie mới**.

Server lab:
1. Đọc **tất cả** Cookie header values.
2. Tách các pairs theo `;`, chỉ tìm tên `DEMO_SESSION` chính xác.
3. Cho phép giá trị unquoted hoặc có **một cặp dấu `"..."` ở hai đầu**.
4. Bỏ dấu `"` nếu hợp lệ, rồi **yêu cầu chính xác 43 ký tự Base64URL**.
5. Nếu có **hai cookies cùng tên** hoặc token không hợp lệ, trả unauthenticated, không đoán cái nào ưu tiên.

Parser này được viết **giới hạn cho ID format của bài lab**, không phải một RFC 6265 parser tổng quát. Trong production, nên dùng HTTP framework/cookie library có parser được kiểm thử toàn diện, bảo vệ khỏi duplicate cookie names, malformed quoting/attributes và header injection.

### 5.3. Không tin Cookie header là các thuộc tính của Set-Cookie

Request header `Cookie` thường chỉ chứa `name=value`. `HttpOnly`, `Secure`, `SameSite`, `Path` và `Max-Age` là **thuộc tính hướng dẫn client khi nhận `Set-Cookie`**, không phải flags do server đọc được từ request để quyết định ủy quyền. Nếu client tự gửi một token hợp lệ từ nơi khác, các flags không chứng minh nó là request an toàn. Server phải xác thực session record và origin/CSRF requirements riêng.

## 6. Thiết kế server session: phát hành, giữ, xoay và thu hồi

### 6.1. Random session identifier

```java
byte[] bytes = new byte[32];
new SecureRandom().nextBytes(bytes);
String token = Base64.getUrlEncoder()
        .withoutPadding().encodeToString(bytes);
```

Đây là snippet độc lập về token. Mỗi token có **32 random bytes** (nếu CSPRNG nguồn entropy tốt) và Base64URL without padding dài **43 ký tự**; không cần cho token chứa username, role, password hay một chuỗi đếm tăng dần. Không dùng `Random` hoặc `Math.random()` làm nguồn ID phiên bảo mật.

JDK `SecureRandom` cung cấp CSPRNG được thiết kế cho trường hợp này, nhưng production còn cần key/storage lifecycle/availability, không chỉ RNG.

### 6.2. Server-side store

Mỗi bản ghi `Session` là một Java record bất biến:

```java
private record Session(String user, Instant expiresAt) {}
private final Map<String, Session> sessions = new ConcurrentHashMap<>();
```

Đây là snippet trong `TestServer`. Token là **key** của map; user + expiresAt nằm ở server. `ConcurrentHashMap` hỗ trợ truy cập từ các HTTP worker threads khác nhau, nhưng đây chỉ là **in-memory store của một process**, mất hết khi JVM dừng; không có persistence/distributed coordination, quotas, background purge hoặc authentication middleware. Dùng Redis/DB/session module của framework đã được kiểm chứng cho production.

**Lưu ý race:** `ConcurrentHashMap` không tự khiến tổ hợp `get -> check expiry -> respond` thành transaction với logout. Một request có thể đã đọc session trước lúc concurrent logout thu hồi. Bài kiểm thử tuần tự cho correctness cơ bản, **không** chứng minh strong revocation semantics trong mọi race. Production cần thiết kế chính sách concurrency và authorization recheck phù hợp.

### 6.3. Rotation và session fixation

Ở `POST /login`:
- Nếu client có **token cũ đã phát hành**, server remove record đó.
- Server **luôn sinh token mới** bằng CSPRNG rồi lưu record.
- Không dùng token do client tự bịa để “tạo session tương ứng”.
- Token cũ không còn hợp lệ, ngay cả khi một client khác cố gửi lại.

Điều này thực hành phần quan trọng của phòng chống **session fixation**. Trong production phải rotate session **sau một lần xác thực hoặc thay đổi quyền thực tế**, không chỉ mỗi request login giả lập.

### 6.4. Logout là server revocation, không chỉ cookie deletion

Khi logout, thu hồi key ở `sessions` và gửi `Set-Cookie` xóa; trong test, client có token cũ nhưng server không còn session record nên `GET /me` trả `401`. Không để dữ liệu người dùng nhạy cảm được cache bởi intermediary; ví dụ đặt `Cache-Control: no-store`. Session tokens không nên nằm trong URL, request logs hoặc analytics tags.

### 6.5. Expiry: check server ở mỗi protected request

`Session` chứa `expiresAt`. Khi protected request đến:
- Chỉ cho phép khi `currentTime().isBefore(session.expiresAt())`.
- `now == expiresAt` đã là **hết hạn**, không dùng `<=` sai biên.
- Dùng `sessions.remove(token, session)` để tránh xóa bản ghi khác bị thay thế đồng thời khi phát hiện expiry.
- Trong fixture, record hết hạn chỉ được dọn khi bị truy cập, không có background job. Vì vậy với nhiều phiên không bao giờ được truy cập lại, map có thể lớn lên. Production cần TTL store và cơ chế eviction/cleanup có giới hạn.

**Server test clock** là `AtomicReference<Instant>` giả lập; **serve clock** dùng `Instant.now()` thật. Đây là cách tách **test determinism** và **đúng semantics khi thử thủ công**.

## 7. Chạy chương trình và chuẩn bị môi trường

### 7.1. Yêu cầu

- **JDK 17+** có module `jdk.httpserver` (có trên các OpenJDK/JDK builds thông thường, nhưng có thể không có trong custom `jlink` runtime image).
- Terminal PowerShell/cmd/POSIX shell và quyền bind loopback port.
- Không cần Gradle/Maven/Spring, cơ sở dữ liệu, Internet, proxy, chứng chỉ TLS hay dependencies bên thứ ba.
- Chạy từ một **thư mục thử nghiệm riêng**. Không bind public interface hoặc dùng sample này làm service xác thực.

Các Java packages được dùng:
- `com.sun.net.httpserver.HttpServer`/`HttpExchange` trong **module `jdk.httpserver`** (đây là *supported documented JDK-specific API*, khác các internal `sun.*` packages).
- `java.net.http.HttpClient`/`HttpRequest`/`HttpResponse` trong `java.net.http`.
- `java.net.CookieManager`/`CookiePolicy`/`HttpCookie` trong `java.base`.
- `java.security.SecureRandom`, `java.time.Instant`, `java.util.concurrent.*` trong các standard JDK modules.

### 7.2. Tên source file và lệnh biên dịch

Lưu toàn bộ mã mục 8 vào file tên **`SessionHttpDemo.java`**. Từ terminal ở đúng thư mục:

```bash
javac --release 17 --add-modules jdk.httpserver SessionHttpDemo.java
java --add-modules jdk.httpserver SessionHttpDemo
```

Lệnh trên đã **biên dịch và chạy thành công trên OpenJDK 24 Windows**; `--release 17` yêu cầu Java source/API compatibility với Java 17. Nếu toolchain thực sự là JDK 17, lệnh tương tự vẫn hợp lệ.

Với một project named module, module descriptor cần `requires jdk.httpserver;` và `requires java.net.http;` khi code gọi trực tiếp các APIs đó:

```java
module demo.httpsessions {
    requires jdk.httpserver;
    requires java.net.http;
}
```

`module-info.java` ở đây là **snippet dành cho project modular**, không đặt cùng file source đơn của bài và không phải điều kiện cần cho classpath example.

### 7.3. Chế độ tự kiểm thử và chế độ serve

Không truyền arguments: chương trình mở server trên cổng tự gán, thực hiện tất cả checks, in kết quả rồi **stop server** tự động.

Truyền `serve`:
 
```bash
java --add-modules jdk.httpserver SessionHttpDemo serve
```

Stdout có dạng:

```text
server=http://127.0.0.1:<ephemeral-port>
stop=press-enter
```

Số cổng thật khác mỗi lần chạy. Giữ terminal server đang mở, dùng **một terminal thứ hai** để gửi HTTP requests. Bấm Enter vào terminal server để dừng (`System.in.read()`); trong môi trường stdin đã đóng, serve mode sẽ kết thúc ngay, vì vậy nên dùng terminal tương tác.

**Serve mode dùng đồng hồ thật** nên session server hết hạn sau khoảng 120 giây thực kể từ khi phát hành, còn automated test không phải chờ. Nếu máy đổi giờ đột ngột, `Instant.now()` cũng thay đổi; production có thể cần chính sách time synchronization và monotonic elapsed time cho idle timeout.

## 8. Source hoàn chỉnh `SessionHttpDemo.java` — đã QA

Chương trình tự chứa một class public, một Java record private, một HTTP test server, một HttpClient test wrapper và toàn bộ assertions. Các tên `alice` và `bob` chỉ là hai **cookie jars giả lập**, không đại diện người dùng được xác thực thật.

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpCookie;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

public final class SessionHttpDemo {
    private static final String COOKIE = "DEMO_SESSION";
    private static final long SESSION_SECONDS = 120;
    private static int passed = 0;

    private record Session(String user, Instant expiresAt) {}

    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        passed++;
        System.out.println(name + "=true");
    }

    private static final class TestServer implements AutoCloseable {
        private final AtomicReference<Instant> now =
                new AtomicReference<>(Instant.parse("2026-01-01T00:00:00Z"));
        private final boolean realTime;
        private final Map<String, Session> sessions = new ConcurrentHashMap<>();
        private final SecureRandom random = new SecureRandom();
        private final ExecutorService workers = Executors.newFixedThreadPool(4);
        private final HttpServer server;
        private final URI base;

        TestServer(boolean realTime) throws IOException {
            this.realTime = realTime;
            server = HttpServer.create(new InetSocketAddress(
                    InetAddress.getByName("127.0.0.1"), 0), 16);
            server.createContext("/", this::handle);
            server.setExecutor(workers);
            base = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
            server.start();
        }

        private Instant currentTime() {
            return realTime ? Instant.now() : now.get();
        }

        URI url(String path) {
            return base.resolve(path);
        }

        void advanceSeconds(long seconds) {
            if (realTime) throw new IllegalStateException("real-time mode");
            now.updateAndGet(x -> x.plusSeconds(seconds));
        }

        private String newToken() {
            byte[] bytes = new byte[32];
            random.nextBytes(bytes);
            return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        }

        private String findSessionCookie(HttpExchange exchange) {
            List<String> headers = exchange.getRequestHeaders().get("Cookie");
            if (headers == null) return null;
            String result = null;
            int found = 0;
            for (String header : headers) {
                for (String piece : header.split(";")) {
                    String entry = piece.trim();
                    int eq = entry.indexOf('=');
                    if (eq < 1) continue;
                    if (!entry.substring(0, eq).trim().equals(COOKIE)) continue;
                    String value = entry.substring(eq + 1).trim();
                    if (value.length() >= 2 && value.startsWith("\"")
                            && value.endsWith("\"")) {
                        value = value.substring(1, value.length() - 1);
                    }
                    result = value;
                    found++;
                }
            }
            if (found != 1 || result == null ||
                    !result.matches("[A-Za-z0-9_-]{43}")) return null;
            return result;
        }

        private void handle(HttpExchange exchange) throws IOException {
            String path = exchange.getRequestURI().getPath();
            String method = exchange.getRequestMethod();
            if (path.equals("/health")) {
                if (!method.equals("GET")) {
                    notAllowed(exchange, "GET");
                    return;
                }
                respond(exchange, 200, "ok");
            } else if (path.equals("/login")) {
                if (!method.equals("POST")) {
                    notAllowed(exchange, "POST");
                    return;
                }
                String previous = findSessionCookie(exchange);
                if (previous != null) sessions.remove(previous);
                String token = newToken();
                sessions.put(token, new Session("student",
                        currentTime().plusSeconds(SESSION_SECONDS)));
                exchange.getResponseHeaders().set("Set-Cookie",
                        COOKIE + "=" + token
                        + "; Path=/; HttpOnly; SameSite=Lax; Max-Age="
                        + SESSION_SECONDS);
                respond(exchange, 200, "logged-in");
            } else if (path.equals("/me")) {
                if (!method.equals("GET")) {
                    notAllowed(exchange, "GET");
                    return;
                }
                String token = findSessionCookie(exchange);
                Session session = token == null ? null : sessions.get(token);
                if (session == null) {
                    respond(exchange, 401, "unauthorized");
                    return;
                }
                if (!currentTime().isBefore(session.expiresAt())) {
                    sessions.remove(token, session);
                    respond(exchange, 401, "unauthorized");
                    return;
                }
                respond(exchange, 200, "user=" + session.user());
            } else if (path.equals("/logout")) {
                if (!method.equals("POST")) {
                    notAllowed(exchange, "POST");
                    return;
                }
                String token = findSessionCookie(exchange);
                if (token != null) sessions.remove(token);
                exchange.getResponseHeaders().set("Set-Cookie",
                        COOKIE + "=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0");
                respond(exchange, 200, "logged-out");
            } else {
                respond(exchange, 404, "not-found");
            }
        }

        private void notAllowed(HttpExchange exchange, String allowed)
                throws IOException {
            exchange.getResponseHeaders().set("Allow", allowed);
            respond(exchange, 405, "method-not-allowed");
        }

        private void respond(HttpExchange exchange, int code, String message)
                throws IOException {
            byte[] body = message.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type",
                    "text/plain; charset=utf-8");
            exchange.getResponseHeaders().set("Cache-Control", "no-store");
            exchange.getResponseHeaders().set("X-Content-Type-Options", "nosniff");
            exchange.sendResponseHeaders(code, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        }

        @Override
        public void close() {
            server.stop(0);
            workers.shutdownNow();
            sessions.clear();
        }
    }

    private static final class TestClient {
        final CookieManager cookies;
        final HttpClient http;
        TestClient(CookiePolicy policy) {
            cookies = new CookieManager(null, policy);
            http = HttpClient.newBuilder()
                    .cookieHandler(cookies)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
        }
        HttpResponse<String> get(URI url) throws Exception {
            return http.send(HttpRequest.newBuilder(url)
                    .timeout(Duration.ofSeconds(5)).GET().build(),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        }
        HttpResponse<String> post(URI url) throws Exception {
            return http.send(HttpRequest.newBuilder(url)
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.noBody()).build(),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        }
    }

    private static String token(TestClient client) {
        return client.cookies.getCookieStore().getCookies().stream()
                .filter(c -> c.getName().equals(COOKIE))
                .findFirst().orElseThrow().getValue();
    }

    private static TestClient replayClient(URI uri, String token) {
        TestClient client = new TestClient(CookiePolicy.ACCEPT_ORIGINAL_SERVER);
        HttpCookie cookie = new HttpCookie(COOKIE, token);
        cookie.setPath("/");
        client.cookies.getCookieStore().add(uri, cookie);
        return client;
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("serve")) {
            try (TestServer server = new TestServer(true)) {
                System.out.println("server=" + server.base);
                System.out.println("stop=press-enter");
                System.in.read();
            }
            return;
        }
        if (args.length != 0)
            throw new IllegalArgumentException("Usage: SessionHttpDemo [serve]");

        try (TestServer server = new TestServer(false)) {
            TestClient alice = new TestClient(CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            TestClient bob = new TestClient(CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            check("loopbackBound",
                    server.server.getAddress().getAddress().isLoopbackAddress());
            check("ephemeralPortAssigned", server.server.getAddress().getPort() > 0);
            check("healthOk", alice.get(server.url("/health")).statusCode() == 200);
            check("healthBody", alice.get(server.url("/health")).body().equals("ok"));
            check("anonymousUnauthorized",
                    alice.get(server.url("/me")).statusCode() == 401);
            check("bobInitiallyUnauthorized",
                    bob.get(server.url("/me")).statusCode() == 401);
            check("loginRequiresPost",
                    alice.get(server.url("/login")).statusCode() == 405);
            check("meRequiresGet",
                    alice.post(server.url("/me")).statusCode() == 405);
            check("unknownRoute404",
                    alice.get(server.url("/unknown")).statusCode() == 404);

            HttpResponse<String> first = alice.post(server.url("/login"));
            check("loginStatus200", first.statusCode() == 200);
            check("loginBody", first.body().equals("logged-in"));
            String setCookie = first.headers().firstValue("set-cookie")
                    .orElseThrow();
            check("responseHasSessionCookie",
                    setCookie.startsWith(COOKIE + "="));
            check("cookiePathRoot", setCookie.contains("; Path=/"));
            check("cookieHttpOnly", setCookie.contains("; HttpOnly"));
            check("cookieSameSiteLax", setCookie.contains("; SameSite=Lax"));
            check("cookieMaxAge", setCookie.contains("; Max-Age=120"));
            check("noSecureOnHttpDemo", !setCookie.contains("; Secure"));
            check("responseNoStore",
                    first.headers().firstValue("Cache-Control")
                            .orElseThrow().equals("no-store"));
            List<HttpCookie> stored = alice.cookies.getCookieStore().getCookies();
            check("cookieManagerStoredExactlyOne", stored.size() == 1);
            check("cookieManagerHttpOnly", stored.get(0).isHttpOnly());
            check("cookieManagerPath", "/".equals(stored.get(0).getPath()));
            check("cookieManagerMaxAge", stored.get(0).getMaxAge() == 120);
            String firstToken = token(alice);
            check("secureRandomTokenLength", firstToken.length() == 43);
            check("tokenBase64Url", firstToken.matches("[A-Za-z0-9_-]{43}"));
            check("serverHasSession", server.sessions.containsKey(firstToken));

            HttpResponse<String> me = alice.get(server.url("/me"));
            check("aliceAuthenticated", me.statusCode() == 200);
            check("aliceResponseBody", me.body().equals("user=student"));
            check("bobStillUnauthenticated",
                    bob.get(server.url("/me")).statusCode() == 401);

            TestClient invented = replayClient(server.url("/"), "Z".repeat(43));
            check("inventedSessionDenied",
                    invented.get(server.url("/me")).statusCode() == 401);
            HttpResponse<String> second = alice.post(server.url("/login"));
            String secondToken = token(alice);
            check("secondLoginStatus", second.statusCode() == 200);
            check("sessionRotated", !secondToken.equals(firstToken));
            check("oldSessionRevoked", !server.sessions.containsKey(firstToken));
            check("newSessionExists", server.sessions.containsKey(secondToken));
            TestClient oldCopy = replayClient(server.url("/"), firstToken);
            check("replayedOldTokenDenied",
                    oldCopy.get(server.url("/me")).statusCode() == 401);
            check("newTokenAccepted",
                    alice.get(server.url("/me")).statusCode() == 200);

            check("bobLoginStatus",
                    bob.post(server.url("/login")).statusCode() == 200);
            String bobToken = token(bob);
            check("clientsHaveDifferentTokens", !bobToken.equals(secondToken));
            check("bobAuthenticated",
                    bob.get(server.url("/me")).statusCode() == 200);

            HttpResponse<String> logout = alice.post(server.url("/logout"));
            check("logoutStatus200", logout.statusCode() == 200);
            check("logoutBody", logout.body().equals("logged-out"));
            String deletingCookie = logout.headers()
                    .firstValue("set-cookie").orElseThrow();
            check("logoutExpiresCookie",
                    deletingCookie.contains("Max-Age=0"));
            check("logoutRevokesServerRecord",
                    !server.sessions.containsKey(secondToken));
            check("aliceUnauthorizedAfterLogout",
                    alice.get(server.url("/me")).statusCode() == 401);
            check("bobUnaffectedByAliceLogout",
                    bob.get(server.url("/me")).statusCode() == 200);
            TestClient leakedCopy = replayClient(server.url("/"), secondToken);
            check("revokedTokenReplayDenied",
                    leakedCopy.get(server.url("/me")).statusCode() == 401);

            TestClient noCookies = new TestClient(CookiePolicy.ACCEPT_NONE);
            check("acceptNoneLoginStatus",
                    noCookies.post(server.url("/login")).statusCode() == 200);
            check("acceptNoneStoresNothing",
                    noCookies.cookies.getCookieStore().getCookies().isEmpty());
            check("acceptNoneCannotAuthenticate",
                    noCookies.get(server.url("/me")).statusCode() == 401);

            TestClient lateReplay = replayClient(server.url("/"), bobToken);
            server.advanceSeconds(SESSION_SECONDS + 1);
            check("clockAdvancedDeterministically",
                    server.now.get().equals(
                            Instant.parse("2026-01-01T00:02:01Z")));
            check("expiredTokenRejectedByServer",
                    lateReplay.get(server.url("/me")).statusCode() == 401);
            check("expiredServerRecordRemoved",
                    !server.sessions.containsKey(bobToken));
            check("expiredClientCannotAuthenticate",
                    bob.get(server.url("/me")).statusCode() == 401);
            check("clientClockNotAdvanced",
                    !bob.cookies.getCookieStore().getCookies().isEmpty());
            check("logoutIdempotent",
                    alice.post(server.url("/logout")).statusCode() == 200);

            System.out.println("scenario=isolation,rotation,logout,expiry");
            System.out.println("checksPassed=" + passed);
        }
    }
}
```

### 8.1. Điểm cần đọc trong mã

- **TestServer** khởi tạo `HttpServer` trên `127.0.0.1` port `0`, dùng `Executors.newFixedThreadPool(4)` và dọn bằng `server.stop(0)` + `workers.shutdownNow()` khi đóng.
- **findSessionCookie** đọc header thực; trim quotes nếu cả hai đầu có dấu kép, từ chối duplicate/malformed token, không lấy tên metadata `$Path` làm session.
- **handle** dispatch exact methods/paths, trả HTTP statuses, không dùng business framework.
- **Session** là record immutable `(user, expiresAt)`; `ConcurrentHashMap` là session store trong process.
- **SecureRandom** tạo token mới cho mỗi lần login; `sessions.remove(previous)` thực hiện rotation.
- **currentTime()** dùng đồng hồ giả khi automated test, đồng hồ `Instant.now()` thật khi `serve`. Đây là một khác biệt chủ động.
- **TestClient** tạo CookieManager riêng gắn với một HttpClient; không phụ thuộc global default.
- **replayClient** được dùng **chỉ trong test** để mô phỏng việc một client giữ một ID được cung cấp (bịa, cũ hoặc hết hạn). Đây không phải hướng dẫn thu thập session IDs của người khác.
- **check** ném `AssertionError` nếu sai và tăng bộ đếm nếu đúng. Vì vậy `name=true` chỉ được in khi check đó PASS.
- **main** với không arguments chạy 54 assertions; có `serve` mở HTTP server tương tác để thử thủ công rồi thoát khi Enter.

### 8.2. Bản đồ trách nhiệm

| Class/method | Trách nhiệm | Sai lầm cần tránh |
| --- | --- | --- |
| `TestServer.newToken()` | Sinh random opaque ID | Dùng username/time như token |
| `TestServer.findSessionCookie()` | Parse đúng tên cookie và validate shape | Tin Cookie header luôn unquoted |
| `TestServer.handle()` | Định tuyến/HTTP response | Dùng GET cho logout và thay đổi state |
| `TestServer.currentTime()` | Tách server TTL test và real time | Dùng đồng hồ cố định trong server phục vụ thủ công |
| `TestServer.close()` | Đóng socket, executor, store | Để server process leak |
| `TestClient` | Giữ cookies theo từng client | Share một CookieManager cho các “user” |
| `CookieStore.getCookies()` | Xem cookie client | Nhầm với session data đã lưu server |
| `replayClient` | Test ID chưa từng sinh hoặc đã thu hồi | Chấp nhận arbitrary ID làm session mới |
| `check(...)` | Fail test tức thì và in chứng cứ PASS | Dựa vào log “thành công” không có assertion |

## 9. Kết quả thực tế: 54/54 assertions

Khi chạy không arguments, stdout **chính xác** trên Windows OpenJDK 24 sau `javac --release 17` như sau (không in token hoặc cổng ngẫu nhiên):

```text
loopbackBound=true
ephemeralPortAssigned=true
healthOk=true
healthBody=true
anonymousUnauthorized=true
bobInitiallyUnauthorized=true
loginRequiresPost=true
meRequiresGet=true
unknownRoute404=true
loginStatus200=true
loginBody=true
responseHasSessionCookie=true
cookiePathRoot=true
cookieHttpOnly=true
cookieSameSiteLax=true
cookieMaxAge=true
noSecureOnHttpDemo=true
responseNoStore=true
cookieManagerStoredExactlyOne=true
cookieManagerHttpOnly=true
cookieManagerPath=true
cookieManagerMaxAge=true
secureRandomTokenLength=true
tokenBase64Url=true
serverHasSession=true
aliceAuthenticated=true
aliceResponseBody=true
bobStillUnauthenticated=true
inventedSessionDenied=true
secondLoginStatus=true
sessionRotated=true
oldSessionRevoked=true
newSessionExists=true
replayedOldTokenDenied=true
newTokenAccepted=true
bobLoginStatus=true
clientsHaveDifferentTokens=true
bobAuthenticated=true
logoutStatus200=true
logoutBody=true
logoutExpiresCookie=true
logoutRevokesServerRecord=true
aliceUnauthorizedAfterLogout=true
bobUnaffectedByAliceLogout=true
revokedTokenReplayDenied=true
acceptNoneLoginStatus=true
acceptNoneStoresNothing=true
acceptNoneCannotAuthenticate=true
clockAdvancedDeterministically=true
expiredTokenRejectedByServer=true
expiredServerRecordRemoved=true
expiredClientCannotAuthenticate=true
clientClockNotAdvanced=true
logoutIdempotent=true
scenario=isolation,rotation,logout,expiry
checksPassed=54
```

**54/54 assertions PASS**, chương trình thoát mã `0`, server và executor được đóng. Ngoài ra, `java --add-modules jdk.httpserver SessionHttpDemo serve` đã được smoke-tested: in URI loopback/cổng thực và dòng `stop=press-enter`, rồi kết thúc sạch sau khi stdin được đóng trong thử nghiệm. Lượt QA chỉ tạo files `.java/.class` trong một thư mục TEMP riêng và dọn sạch; không chỉnh sửa project.

### 9.1. Nhóm kiểm thử

| Nhóm | Checks đại diện | Ý nghĩa |
| --- | --- | --- |
| Server | `loopbackBound`, `ephemeralPortAssigned` | Không mở public interface, OS gán port |
| Routes | `healthOk`, `unknownRoute404`, `loginRequiresPost` | HTTP method/path/status |
| Unauthorized | `anonymousUnauthorized`, `bobInitiallyUnauthorized` | Không mặc định có phiên |
| Set-Cookie | `cookiePathRoot`, `cookieHttpOnly`, `cookieSameSiteLax`, `cookieMaxAge` | Server phát đủ attributes cho lab |
| Token | `secureRandomTokenLength`, `tokenBase64Url` | 32 random bytes → 43-char base64url |
| Client | `cookieManagerStoredExactlyOne`, `cookieManagerHttpOnly` | HttpClient CookieManager tự lưu cookie |
| Isolation | `bobStillUnauthenticated`, `clientsHaveDifferentTokens` | Hai cookie stores riêng |
| Strict session | `inventedSessionDenied` | Server không chấp nhận token tự nghĩ |
| Rotation | `sessionRotated`, `oldSessionRevoked`, `replayedOldTokenDenied` | Login mới không tái sử dụng ID cũ |
| Logout | `logoutRevokesServerRecord`, `revokedTokenReplayDenied` | Xóa phía server, không chỉ phía client |
| Policy | `acceptNoneStoresNothing`, `acceptNoneCannotAuthenticate` | Client không nhận cookie thì không giữ phiên |
| Time | `expiredTokenRejectedByServer`, `clientClockNotAdvanced` | Server TTL tách biệt cookie TTL |
| Cleanup | `logoutIdempotent` | Logout lặp lại không cần giữ phiên |

### 9.2. Tại sao stdout cố định không chứa session ID thật?

Session token và port được tạo mới mỗi lần chạy. In token thật vào stdout/screenshot/CI logs có thể lộ một bearer credential trong khi phiên còn hiệu lực, dù đây chỉ là lab. Vì vậy ví dụ kiểm tra **độ dài, charset, trạng thái trong store và kết quả HTTP**, không công bố token. Port cũng chỉ kiểm tra `> 0` trong automated test; manual serve mới in local endpoint để người học kết nối.

### 9.3. Nhiều client cùng user nhưng phiên riêng

Hai clients trong test đều nhận `user=student` vì login không có credentials; nhưng **session ID khác nhau** và logout A không thu hồi session B. Đây là demo **isolation theo cookie/session**, không phải phân quyền user. Một hệ thống sản phẩm cần định nghĩa rõ logout một thiết bị hay tất cả thiết bị, chính sách session per-user và revocation scope.

## 10. Chạy thử thủ công với curl

### 10.1. Mở máy chủ

Terminal 1:

```bash
java --add-modules jdk.httpserver SessionHttpDemo serve
```

Chương trình in `server=http://127.0.0.1:<port>` với số cổng thật. Giả sử **chỉ để minh họa** nó là **`49152`**. Trong các lệnh bên dưới, hãy **thay `49152` bằng số cổng từ terminal 1**, không giả định mọi lần cùng cổng.

### 10.2. Kiểm tra chưa đăng nhập

Terminal 2:

```bash
curl -i http://127.0.0.1:49152/health
curl -i http://127.0.0.1:49152/me
```

Kỳ vọng `/health` trả `200` body `ok`, `/me` trả `401` body `unauthorized`. Lệnh `curl -i` in headers nên status là từ server thực; exact thứ tự headers có thể khác.

### 10.3. Đăng nhập thử và lưu cookie jar

```bash
curl -i -c session.cookies -X POST http://127.0.0.1:49152/login
curl -i -b session.cookies http://127.0.0.1:49152/me
```

- `-c session.cookies` yêu cầu curl **ghi cookie jar ra file local** sau response.
- `-b session.cookies` yêu cầu curl **gửi lại cookies** từ file khi request `/me`.
- Nếu chưa quá 120 giây, `/me` trả `200` body `user=student`.
- File `session.cookies` chứa **session token nhạy cảm** khi phiên còn hiệu lực, dù đây là lab. Chạy trong thư mục thử nghiệm cá nhân, không commit file, không chia sẻ logs/cookie jar, xóa khi xong. Trên Windows PowerShell dùng `curl.exe` thay `curl` nếu `curl` là alias của `Invoke-WebRequest`.

### 10.4. Logout và kiểm tra thu hồi

```bash
curl -i -b session.cookies -c session.cookies -X POST http://127.0.0.1:49152/logout
curl -i -b session.cookies http://127.0.0.1:49152/me
```

Kỳ vọng logout trả `200`, `Set-Cookie` với `Max-Age=0`; request `/me` sau đó trả `401`. Trong lệnh logout, thêm `-c session.cookies` để curl cập nhật cookie jar theo response; nếu không ghi lại jar thì file cũ còn lưu token, **server vẫn phải từ chối** vì đã revoke record.

Bấm Enter vào Terminal 1 để dừng máy chủ. Xóa `session.cookies` theo file-management policy của môi trường thử nghiệm; không lưu token lâu hoặc đẩy lên Git.

### 10.5. Test rotation bằng curl

Với cùng `session.cookies`, gửi `POST /login` lần hai và ghi lại jar. Cả hai responses đều có token mới; token trước phải bị thu hồi. Để kiểm chứng token cũ không còn hiệu lực, dùng **bản sao cookie jar chỉ trong môi trường test** và thử `GET /me` bằng bản cũ; server phải trả `401`, trong khi jar mới trả `200`. Không ghi các token raw ra bug reports.

### 10.6. Test hai trình duyệt/clients riêng biệt

Tạo hai files riêng `alice.cookies` và `bob.cookies` nếu muốn dùng curl minh họa isolation. Đăng nhập mỗi file, xác minh `/me` của từng file, rồi logout chỉ một file. **Không dùng chung `session.cookies`** khi đang muốn test hai clients độc lập. Với Java HttpClient, điều tương ứng là hai `CookieManager` khác nhau.

## 11. Phân tích chi tiết các trường hợp an toàn

### 11.1. Session ID do attacker tự chọn

Server chỉ chấp nhận ID **nó đã sinh và lưu**. Nếu client tự gửi `DEMO_SESSION=ZZZ...` đúng 43 ký tự nhưng không có record, `/me` trả `401`. **Regex đúng không biến token thành hợp lệ**; nó chỉ lọc shape trước khi lookup.

### 11.2. Session fixation và rotation

Nếu server chấp nhận ID tùy ý từ browser rồi “gắn quyền” vào nó khi login, attacker có thể cố định trước ID mà nạn nhân sẽ dùng. Lab thay thế ID cũ bằng token mới và thu hồi record cũ khi login. Production còn cần rotate sau privilege change, reauthentication và logout-all policy.

### 11.3. Replay token sau logout

Thậm chí nếu client giữ một bản sao cookie cũ, `sessions.remove(token)` khiến server không nhận ID đó nữa. Trong test, `replayClient(..., secondToken)` sau logout nhận `401`. **Đừng giới hạn logic logout ở việc gửi `Max-Age=0`**.

### 11.4. Không nhận cookie bằng CookiePolicy.ACCEPT_NONE

`POST /login` vẫn trả `200` và `Set-Cookie`, nhưng Java CookieManager cấu hình `ACCEPT_NONE` không lưu nó. Request tiếp theo thiếu ID và `/me` trả `401`. Đây là khác biệt giữa “server đã phát cookie” và “client đã chấp nhận cookie”.

### 11.5. Hết hạn tại server dù client còn cookie

Lab đặt server `expiresAt` và kiểm tra khi `GET /me`. Sau khi test clock nhảy `121` giây, bản ghi bị coi hết hạn và bị xóa khi truy cập. CookieStore của Bob vẫn dùng thời gian thật nên có thể vẫn lưu ID đó; **server vẫn trả `401`**. Điều này quan trọng trong các trường hợp clock skew, bị mất/không nhận Set-Cookie xóa, browser session restore hoặc client cố tình giữ ID.

### 11.6. Duplicate cookies cùng tên

Cookie có thể bị duplicate bởi Domain/Path variants; server không nên tùy tiện chọn “đầu” hoặc “cuối”. Parser của bài đếm tên `DEMO_SESSION` và trả null nếu thấy hơn một, thay vì vô tình chấp nhận ID không mong muốn. Đây là một quy tắc lab đơn giản; production parser và session-cookie policy cần xử lý đầy đủ cookie standards.

### 11.7. Không gửi session ID qua URL

Không thiết kế endpoint `/me?sessionId=...` hoặc `/login?token=...`. URL có thể đi vào logs, browser history, Referer, analytics và bị chia sẻ. Dùng cookie có thuộc tính an toàn và server-side validation. Với APIs, cân nhắc token-based schemes có bảo mật tương đương khi không dùng browser cookies, nhưng đó là một thiết kế khác.

## 12. Giới hạn bảo mật — vì sao không deploy server này lên Internet

**Đây là một laboratory HTTP server để học và test. Không sử dụng nó làm production authentication backend.** Cụ thể:

1. **Không xác thực người dùng:** `POST /login` cấp `student` cho bất kỳ caller nào. Hoàn toàn không có passwords, identity provider, MFA hay authorization logic.
2. **Không có TLS:** cookie không có `Secure` để hoạt động trên HTTP loopback. Trên production **phải dùng HTTPS end-to-end** và `Secure`, có thể HSTS và `__Host-` prefix.
3. **Không có bảo vệ CSRF hoàn chỉnh:** `SameSite=Lax` chỉ hỗ trợ defense-in-depth. Cần anti-CSRF token/Origin/Fetch Metadata validation phù hợp cho các state-changing requests như login/logout.
4. **Không có chống XSS:** `HttpOnly` giảm nguy cơ JS đọc ID, nhưng XSS vẫn có thể gửi request bằng phiên victim; cần output encoding/CSP/input validation khi dùng UI web thật.
5. **In-memory map không tự dọn mọi session hết hạn:** lazy removal chỉ xảy ra khi truy cập. Production cần TTL eviction/capacity quotas/abuse protection.
6. **Không có distributed session store:** restart làm mất sessions, multi-instance không share state. Production cân nhắc Redis/DB/framework session management và consistent revocation.
7. **Không có idle timeout/absolute+renewal policies đầy đủ:** chỉ một absolute expiration `120s`; không xử lý sliding idle expiration, refresh hoặc forced reauthentication.
8. **Không có quota/rate limiting:** caller có thể gọi `/login` nhiều lần tạo nhiều records cho đến hết bộ nhớ; chỉ bind loopback để giới hạn exposure, nhưng không thay resource limits.
9. **Không có giao dịch thu hồi tức thì xuyên requests đồng thời:** `ConcurrentHashMap` thread-safe không tạo linearizable policy “logout ngay lập tức hủy mọi request đã tiến vào handler”. Với nghiệp vụ nhạy cảm cần authorization revalidation và state coordination.
10. **Parser Cookie thủ công chỉ nhận một subset:** không đầy đủ RFC 6265, không xử lý mọi encoding, escaping, duplicate-header edge case của clients khác. Production dùng framework/library được duy trì.
11. **Không có cấu hình reverse proxy/Host/Origin trust:** đừng bind `0.0.0.0`, copy handler ra Internet hay tin `X-Forwarded-Proto` từ client không được xác thực.
12. **Không có audit/observability cho security events:** production cần log có redaction, metrics, alerting, anomaly detection và incident response.
13. **Session key lưu raw trong process memory:** production cân nhắc chỉ lưu verifier hashes trong data store, mã hóa backups và giới hạn quyền đọc dumps.
14. **Không có kiểm soát secret trên command line/logs:** demo tránh in random token, nhưng `curl -i`/cookie files có thể chứa ID; phải xóa và không gửi chúng lên ticket/CI.
15. **Không có kiểm thử browser cross-site thực:** Java `HttpClient` không mô phỏng hoàn hảo browser cookie policies; cần browser automation tests cho SameSite, Secure, CORS, CSRF.
16. **Không có size limits đầy đủ cho request bodies, concurrency/backpressure:** handler đơn giản cho request body rỗng; production phải kiểm soát body size/content type/timeouts/sockets/queues và graceful shutdown.

Nếu cần tính năng phiên đăng nhập production, ưu tiên framework/service đã được bảo trì và kiểm thử như Spring Security, Servlet container session management, hoặc session middleware tương ứng với stack của bạn. `HttpServer` trong `jdk.httpserver` được tài liệu hóa nhưng chủ yếu thích hợp cho các use cases gọn, ví dụ local testing, demos hoặc tooling được kiểm soát, không mặc định là authentication server sản xuất.

## 13. Các lỗi phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `module not found: jdk.httpserver` | Custom JDK image thiếu module | Kiểm tra `java --list-modules`, sử dụng JDK có `jdk.httpserver` |
| `Could not find or load main class` | Sai tên file, directory hoặc classpath | File `SessionHttpDemo.java`, compile từ đúng thư mục |
| `BindException` | Port cố định bị chiếm | Dùng port `0` để OS chọn; không đoán số cổng |
| Không truy cập được server | `serve` đã tự thoát vì stdin đóng | Dùng terminal tương tác, giữ server mở |
| HTTP 404 | URL path không đúng | Dùng đúng `/health`, `/login`, `/me`, `/logout` |
| HTTP 405 | Sai method | `POST` cho login/logout; `GET` cho health/me |
| Login 200 nhưng /me 401 | Cookie không được lưu/gửi | Kiểm tra CookieManager và cookie policy |
| Java client nhận cookie nhưng server vẫn 401 | Header Cookie được quote hoặc chứa version metadata | Parser lab xử lý quotes có kiểm soát, validate ID |
| `CookieManager.getCookieStore()` rỗng | `ACCEPT_NONE` hoặc cookie không được chấp nhận | Dùng `ACCEPT_ORIGINAL_SERVER`, kiểm tra domain/path/expiry |
| Có cookie nhưng vẫn 401 | ID sai, hết hạn, đã thu hồi hoặc không có record | Kiểm tra server session lifecycle, không chỉ header |
| Logout rồi cookie jar vẫn có ID | Client không ghi lại Set-Cookie xóa | Dùng `curl -c`; server vẫn phải revoke |
| Bob bị logout khi Alice logout | Shared CookieManager hoặc session store logic lỗi | Tạo CookieManager riêng cho mỗi client |
| Token chứa dấu `=` cuối | Base64 encoder có padding | Dùng `withoutPadding()` nếu muốn đúng 43 chars |
| Token dài không đúng 43 | Sinh không phải 32 bytes hoặc encoder khác | Kiểm tra `new byte[32]` + Base64URL |
| Hết hạn ngay sau test advance | Expected | Server test clock đã nhảy 121 giây |
| Cookie vẫn trong store sau server expiry | Expected: client real clock độc lập | Server phải từ chối expired token dù client còn giữ |
| `HttpOnly` cookie vẫn xuất hiện trong Java CookieStore | Expected | HttpOnly hạn chế browser script, không ẩn khỏi Java code có quyền |
| `SameSite=Lax` không được test bởi HttpCookie | Java cookie support không đầy đủ browser | Dùng browser security tests |
| `Secure` làm HTTP lab không mang cookie | Secure cookie thường chỉ qua HTTPS | Giữ lab HTTP loopback riêng; production dùng HTTPS+Secure |
| Cookie gửi qua port khác cùng host | Cookie scope không isolate theo port | Đặt host/name/context cô lập cho tests |
| CORS error khi dùng web frontend | Cross-origin browser policy | Không bật `Access-Control-Allow-Origin:*` cho credentialed session; thiết kế CORS/CSRF riêng |
| Timer test lúc đúng boundary thất bại | So sánh thời gian sai | Hết hạn khi `!now.isBefore(expiresAt)` |
| Test đôi lúc fail vì sleep/timing | Dựa vào `Thread.sleep(120000)` | Dùng injectable clock/AtomicReference như fixture |
| HTTP handler leaks threads | Không đóng server/executor | `try(TestServer ...)` và `close()` |
| Response bị treo | Không đóng response body hoặc length sai | Dùng `sendResponseHeaders` + try-with-resources |
| Server mất phiên sau restart | Store chỉ trong RAM | Expected của lab; production cần storage/session policy |
| Quá nhiều sessions trong map | Không có sweep/quota | Production có eviction, limits, rate limiting |
| Duplicate Cookie header | Nhiều scope trùng tên | Từ chối ambiguity; framework parser đúng chuẩn |
| Cấu hình HTTP server thành public | Bind sai interface | Giữ `127.0.0.1`, đừng expose qua port forwarding |
| `curl` trong PowerShell không hoạt động như mong đợi | Alias Windows PowerShell | Dùng `curl.exe` |
| Token xuất hiện trong log | `curl -i`/proxy/debug | Redact, không commit cookie jars/logs |

## 14. Các bài tập mở rộng

**Bài 1 — Thêm request header:** Lấy `User-Agent` từ `exchange.getRequestHeaders()` và log **không kèm session ID**. Phân biệt diagnostic info và credential.

**Bài 2 — Kiểm tra expiration boundary:** Advance exactly 119 seconds rồi GET `/me` phải 200; advance thêm 1 second thì 401. Viết assertion rõ về boundary `now == expiresAt`.

**Bài 3 — Kiểm thử logout idempotency:** Gọi `POST /logout` hai lần cùng CookieManager. Vì sao cả hai trả 200 nhưng session record đã mất từ lần đầu?

**Bài 4 — Two client jars:** Dùng CookieManager riêng, đăng nhập cả hai, logout A, xác nhận B còn authorized. Sau đó tạo client C `ACCEPT_NONE` để quan sát failure.

**Bài 5 — Cookie policy:** Thay `CookiePolicy.ACCEPT_ORIGINAL_SERVER` bằng `ACCEPT_NONE` rồi thử `POST /login`. Giải thích vì sao response thành công nhưng session không được duy trì.

**Bài 6 — Cookie rotation:** Đăng nhập lại từ Alice, lưu cả hai ID chỉ trong code test và xác nhận ID cũ bị thu hồi. Không log các raw tokens.

**Bài 7 — Tạo token giả:** Với client giả lập có token đúng 43 characters nhưng chưa được server tạo, xác minh `401`. Vì sao regex check là cần nhưng chưa đủ?

**Bài 8 — Malformed/duplicate cookie:** Gửi hai cookies cùng tên `DEMO_SESSION` trong request test; server phải từ chối ambiguity. Nếu cần parse phức tạp hơn, tích hợp thư viện được duy trì thay vì tự thêm ad hoc branches.

**Bài 9 — Browser behavior:** Dựng HTTPS test environment riêng, kiểm tra `Secure`/`__Host-` và SameSite với browser automation. Không dùng kết quả Java CookieManager thay thế.

**Bài 10 — Server-side idle timeout:** Lưu `lastSeenAt` và absolute `expiresAt` riêng, giới hạn race và không kéo dài phiên vĩnh viễn chỉ vì request đều đặn.

**Bài 11 — Session quota:** Giới hạn số phiên per-user hoặc per-test-instance; bổ sung eviction/sweeper có cleanup khi server đóng.

**Bài 12 — CSRF defense:** Thêm CSRF token hoặc Origin/Fetch Metadata validation cho POST endpoints trong môi trường giả lập browser. Đừng coi SameSite là giải pháp duy nhất.

**Bài 13 — HTTPS:** Đổi sang `HttpsServer` hoặc đặt server sau reverse proxy TLS được tin cậy; sử dụng `Secure`. Test client SSLContext/hostname verification đúng, không vô hiệu hóa TLS verification để qua test.

**Bài 14 — Async HttpClient:** Chuyển một số requests sang `HttpClient.sendAsync`; dùng `CompletableFuture` hoàn thành và assert cookies gửi đúng theo thời điểm. Đảm bảo không share CookieManager giữa users.

**Bài 15 — Graceful shutdown:** Dùng executor quản lý rõ, chờ in-flight tasks hợp lý và đảm bảo clients kết thúc trước khi server stop.

**Bài 16 — Tách application code khỏi test harness:** Tạo class `LocalSessionServer` dùng `Clock` injectable và test JUnit 5 ở project thực, tránh port cố định và phụ thuộc Internet. Test vẫn chạy loopback.

## 15. Câu hỏi tự kiểm tra

**1. HTTP có tự nhớ user giữa hai requests không?** Không; phải mang thông tin trạng thái và xác minh phía server.

**2. Cookie `DEMO_SESSION` nên chứa gì?** Một ID vô nghĩa, khó đoán, không phải username/password/role.

**3. Trong lab, ai lưu `Session("student", expiresAt)`?** Server, trong `ConcurrentHashMap`.

**4. Port `0` nghĩa gì?** OS chọn một ephemeral TCP port còn rảnh.

**5. Server bind địa chỉ nào?** `127.0.0.1`, không mở public interface.

**6. API nào tạo HTTP server?** `com.sun.net.httpserver.HttpServer` trong `jdk.httpserver`.

**7. API nào gắn cookie handler vào HTTP client?** `HttpClient.Builder.cookieHandler(...)`.

**8. CookieManager có phải session store server không?** Không, nó nằm ở client.

**9. Mỗi client có nên chung CookieManager khi giả lập người dùng độc lập?** Không.

**10. Login response có header nào đặt cookie?** `Set-Cookie`.

**11. Request gửi lại cookie qua header nào?** `Cookie`.

**12. Trong lab, login dùng method gì?** `POST`.

**13. `/me` không có phiên trả gì?** `401 unauthorized`.

**14. Endpoint không tồn tại trả gì?** `404 not-found`.

**15. Sai method trên endpoint trả gì?** `405 method-not-allowed`.

**16. Session token sinh từ nguồn nào?** `SecureRandom.nextBytes` với 32 bytes.

**17. Vì sao token 43 ký tự?** 32 bytes Base64URL without padding.

**18. Có thể chấp nhận cookie do client tự bịa nhưng đúng format không?** Không, còn phải có record server hợp lệ.

**19. Vì sao rotate token lúc đăng nhập lại?** Giảm nguy cơ session fixation, không tiếp tục ID cũ.

**20. Logout chỉ xóa browser cookie là đủ?** Không; phải revoke session server.

**21. Server TTL và cookie Max-Age có tự đồng bộ không?** Không, hai bên tự quản lý thời gian.

**22. Client còn cookie sau server expiry thì được truy cập không?** Không; server phải trả 401.

**23. `HttpOnly` có ngăn mọi kiểu XSS không?** Không; chỉ giúp chặn script browser đọc cookie trực tiếp.

**24. `SameSite=Lax` có thay CSRF defense không?** Không.

**25. Production session cookie có cần `Secure` không?** Có, với HTTPS.

**26. Vì sao lab không đặt `Secure`?** Nó chạy `http://127.0.0.1`, tập trung vào transport cookie trên local HTTP; không áp dụng ngoài lab.

**27. Cookie có scope theo port không?** Không dùng port làm ranh giới cookie giữa services cùng host.

**28. `HttpCookie` có bảo đảm mô phỏng toàn bộ browser SameSite không?** Không, hỗ trợ RFC 6265 một phần.

**29. Vì sao server parser có thể thấy value có dấu kép?** Java CookieManager/legacy cookie versioned representation.

**30. Test 54/54 có chứng minh production-ready không?** Không; chỉ kiểm tra các tình huống session/cookie của fixture.

## 16. Tài liệu hiện hành và tiêu chuẩn tham khảo

- [Oracle Java SE 26 — HttpServer](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): bind, context matching, executor, start/stop, port.
- [Oracle Java SE 26 — HttpExchange](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): request/response headers và response body.
- [Oracle Java SE 26 — Headers](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): HTTP header getFirst/set/add.
- [Oracle Java SE 26 — module jdk.httpserver](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/module-summary.html): lightweight HTTP server API.
- [Oracle Java SE 26 — HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): JDK HTTP client, sync/async calls.
- [Oracle Java SE 26 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): cookieHandler, connectTimeout.
- [Oracle Java SE 26 — HttpRequest](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpRequest.html): build GET/POST, timeouts.
- [Oracle Java SE 26 — HttpResponse](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpResponse.html): statusCode, headers, body.
- [Oracle Java SE 26 — CookieManager](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieManager.html): CookieHandler implementation, CookiePolicy.
- [Oracle Java SE 26 — CookiePolicy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookiePolicy.html): ACCEPT_ORIGINAL_SERVER / ACCEPT_NONE.
- [Oracle Java SE 26 — CookieStore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieStore.html): lưu và tra cookies phía client.
- [Oracle Java SE 26 — HttpCookie](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/HttpCookie.html): HttpOnly, Secure, Path, Max-Age, partial RFC6265.
- [Oracle Java SE 26 — SecureRandom](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/SecureRandom.html): cryptographic random bytes.
- [Oracle Java SE 26 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): concurrent store.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Secure, HttpOnly, SameSite, Path, Domain, Max-Age và host-only cookies.
- [MDN — Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cookie): request cookie headers và duplicate cookie names.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet): entropy, secure cookie flags, session fixation, revocation, absolute timeout.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF protections ngoài SameSite.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): HTTPS/TLS settings khi vận hành sản phẩm.

## 17. Kết luận

**Một cookie không phải là một phiên đăng nhập được chứng minh hợp lệ.** Nó chỉ mang một ID và các client-side attributes. Server cần sinh ID không dự đoán được, giữ record phía server, validate mọi request, thay ID sau login/privilege changes, thu hồi ở logout, kiểm tra TTL và ngăn client tự “cấp” ID chưa tồn tại. `HttpClient` cộng `CookieManager` là công cụ kiểm thử tốt cho cookie jars của Java, nhưng không thay thế việc kiểm thử chính sách cookie bằng browser thật.

Bài cung cấp **`SessionHttpDemo.java` hoàn chỉnh tương thích Java 17+**, chạy HTTP server chỉ trên `127.0.0.1`, cổng `0`, bốn endpoints và hai clients có CookieManager riêng. **54/54 checks thực đã PASS** trên OpenJDK 24, bao gồm login, format/attributes của Set-Cookie, isolation, rotation, ID giả, replay sau logout, ACCEPT_NONE và expiration server dù client còn giữ ID. Chế độ `serve` cho phép thử thủ công bằng curl và dùng đồng hồ thật; chế độ automated test dùng đồng hồ giả để chạy nhanh. **Đây chỉ là môi trường thực hành** — không bỏ qua HTTPS, Secure cookie, CSRF protection và hệ thống xác thực/authorization trước khi xây production service.
