# Giữ trạng thái phiên có chủ đích giữa các yêu cầu HTTP và cách cô lập người dùng

HTTP về mặt giao thức **không yêu cầu mỗi request phải mang theo trạng thái ứng dụng của request trước**. Tuy nhiên, sản phẩm thực tế thường cần duy trì **phiên (session)** để server biết các thao tác liên tiếp thuộc về người dùng đã đăng nhập, cùng một giỏ hàng hoặc một giao dịch. Trong Java, `HttpClient` có thể gửi nhiều `HttpRequest` trên những kết nối tái sử dụng; nếu cấu hình `CookieManager`, client còn có thể lưu cookie từ response và gửi lại cookie hợp lệ trong request tiếp theo.

Điểm mấu chốt là **duy trì trạng thái chỉ khi có chủ đích và cô lập nó theo danh tính/tenant**. Hai người dùng A và B có thể gọi chung một API hostname nhưng **tuyệt đối không được vô tình dùng chung cookie phiên, bearer token, proxy credentials hoặc thông tin xác thực của nhau**. Tách `HttpClient` instance nhưng vẫn chia sẻ cùng một `CookieManager` cũng **không cô lập phiên**.

Bài Knowledge này thuộc **Java Advance - networking → Proxy và phiên HTTP**. Nội dung tập trung vào Java 17+, giải thích ranh giới HTTP session/cookie, cache trạng thái và kết nối, một số cách quản lý theo từng người dùng, nguy cơ chia sẻ cấu hình qua proxy/redirect/authenticator, vòng đời login–logout, các kiểm thử cô lập và hai chương trình Java chạy độc lập trên localhost.

**Sau bài học, bạn có thể:**
- Phân biệt state server-side và state nằm ở client.
- Biết trường hợp nào nên dùng **cookie store riêng theo phiên/người dùng** và trường hợp nào nên dùng **một stateless HttpClient chung, token nằm riêng trên từng HttpRequest**.
- Hiểu vì sao `CookieManager` phân vùng theo **URI/domain/path**, không theo user ID.
- Không trộn authentication/session của nhiều tenant khi xử lý requests đồng thời.
- Thiết kế logout, token rotation, session expiry, redirect/proxy isolation và cleanup.
- Chạy hai ví dụ Java 17+ để quan sát **đúng cô lập** và **lỗi rò cookie do dùng chung store**.

## 1. HTTP stateless nhưng ứng dụng có thể duy trì session

Xét ba requests liên tiếp:

~~~http
GET /cart HTTP/1.1
Host: shop.example

GET /cart HTTP/1.1
Host: shop.example

POST /checkout HTTP/1.1
Host: shop.example
Content-Type: application/json

{"confirm":true}
~~~

Nhìn các HTTP messages này, **không có gì tự động nói rằng chúng thuộc cùng một người dùng**. Nếu server muốn lưu giỏ hàng theo người dùng, nó cần nhận ra danh tính/session trong từng request: cookie phiên, bearer token, hoặc cơ chế xác thực khác.

Một quy trình cookie-backed session thường như sau:

~~~text
                    LOGIN
Client A                         Server
  | POST /login (credentials)      |
  |------------------------------->|
  |                     validate credentials
  |                     create random session ID
  |                     store session ID -> user A
  |<-------------------------------|
  | 200 OK                         |
  | Set-Cookie: sid=...; Path=/; HttpOnly; Secure; SameSite=Lax
  |                                |
                    NEXT REQUEST
  | GET /me                        |
  | Cookie: sid=...                |
  |------------------------------->|
  |                     lookup sid -> user A
  |<-------------------------------|
  | 200 OK, user=A                 |
  |                                |
                     LOGOUT
  | POST /logout                   |
  | Cookie: sid=...                |
  |------------------------------->|
  |                      invalidate server session
  |<-------------------------------|
  | Set-Cookie: sid=; Max-Age=0; ... 
~~~

Trong sơ đồ, cookie ID chỉ là **chỉ dấu** dùng để tìm session. Mọi quyết định bảo mật vẫn phải được kiểm tra **phía server**; cookie được client gửi không tự chứng minh người dùng có quyền truy cập một tài nguyên.

**Quan trọng:** HTTP stateless **khác** TCP connection stateless. Java `HttpClient` có thể giữ TCP connection, TLS session hoặc HTTP/2 streams để tối ưu hiệu năng. Điều đó **không phải** bằng chứng hai HTTP requests có cùng user identity. Ngược lại, hai requests gửi trên hai kết nối khác nhau **vẫn** có thể thuộc cùng session khi mang đúng cookie/token.

## 2. Ba lớp trạng thái dễ bị nhầm

| Lớp | Ví dụ | Ai quản lý? | Có phải ranh giới danh tính người dùng không? |
| --- | --- | --- | --- |
| **Application session** | Server map `sessionId → userId`, quyền, expiry | Server / session store | Có, nhưng phải xác thực và phân quyền đúng |
| **Client credential state** | Cookie store, access token, Authenticator, proxy credentials | Ứng dụng Java/HttpClient | Có thể mang danh tính; phải cô lập chủ đích |
| **Network connection state** | Keep-alive TCP, TLS session, HTTP/2 streams, connection pool | HttpClient/provider/OS | **Không**, tự nó không phân biệt user |

Đừng viết logic “request này dùng lại connection cũ nên vẫn là Alice”. Authentication thuộc thông tin request và session được xác minh, **không nên dựa vào socket đã tái sử dụng**. Trên HTTP/2, nhiều luồng logic có thể cùng dùng một kết nối; chia sẻ connection càng không đồng nghĩa chia sẻ quyền.

Tương tự, “Java HTTP client đã build immutable” chỉ nói rằng **cấu hình của đối tượng client không thay đổi qua builder sau khi build**. Nó không có nghĩa các thành phần được tham chiếu như `CookieManager` hay custom `Authenticator` là immutable, hoặc không thể lưu trạng thái mới trong những HTTP exchanges sau này.

## 3. Cookie là gì và session cookie được gửi lại ra sao?

Server có thể gửi header:

~~~http
HTTP/1.1 200 OK
Set-Cookie: sid=SESSION_TOKEN; Path=/; HttpOnly; Secure; SameSite=Lax
Cache-Control: no-store
~~~

`sid` ở đây là một **tên cookie ví dụ**, không phải tên chuẩn của JDK. Các framework Servlet hay dùng `JSESSIONID`; framework khác có tên riêng. Giá trị thực tế phải đủ ngẫu nhiên, khó đoán, có thời hạn và được server ràng buộc với session/auth policy.

Các thuộc tính phổ biến:

| Thuộc tính | Mục đích | Lưu ý |
| --- | --- | --- |
| `Path=/` | Giới hạn đường dẫn mà cookie được gửi | Path không thay thế authorization; nhiều app chung host/path có thể đụng scope |
| `Domain=...` | Cho phép cookie trong phạm vi domain hợp lệ | Domain rộng có thể chia sẻ cookie giữa subdomains ngoài ý muốn |
| `Secure` | Chỉ gửi cookie qua kênh secure theo client policy | Cần cho session cookie dùng HTTPS; demo HTTP localhost không đặt Secure |
| `HttpOnly` | Yêu cầu trình duyệt không cung cấp cookie cho JavaScript phía trang | Không biến cookie thành bí mật trước chính ứng dụng Java đang sở hữu CookieStore |
| `SameSite=Lax/Strict/None` | Gợi ý ràng buộc cookies theo cross-site browser context | **Không được giả định** Java CookieManager thực thi đầy đủ chính sách SameSite như trình duyệt |
| `Max-Age` hoặc `Expires` | Thời gian tồn tại cookie | Không tự thay server-side idle/absolute session expiration |
| `sid=; Max-Age=0` | Yêu cầu user agent xóa cookie tương ứng | Phải khớp scope/path/domain và **vẫn phải** invalidate session phía server |

**Cookie scope không phải user scope.** Cookie policy thông thường quan tâm scheme, domain/host, path, Secure, expiry; **không tự gắn cookie với Alice hay Bob**. Cookie cùng tên/domain/path thường được cập nhật/thay thế, ngay cả khi ứng dụng nghĩ hai phiên HTTP thuộc hai đối tượng Java khác nhau. HTTP cookies cũng không cung cấp cơ chế cô lập danh tính theo TCP port như một security boundary.

Trong Java JDK, `CookieManager` và `CookieStore` là nơi lưu/áp dụng cookie policy ở client; server-side session store là thứ hoàn toàn khác. Bạn không nên lưu user-specific permissions chỉ trong cookie có thể do client sửa; nếu phải lưu claims ở client (ví dụ signed token), server phải xác minh chữ ký, expiry, audience, scope và revocation policy.

## 4. java.net.CookieManager, CookieStore và HttpClient.cookieHandler

Java 17 có `java.net.CookieManager` để kết nối cookie acceptance policy với kho lưu `CookieStore`. Một manager riêng theo phiên:

~~~java
CookieManager cookies = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookies)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
~~~

Đây là **snippet** cần imports `java.net.CookieManager`, `java.net.CookiePolicy` và `java.net.http.HttpClient`. Khi constructor nhận store `null`, nó dùng kho in-memory mặc định; policy `ACCEPT_ORIGINAL_SERVER` chỉ nhận cookie theo quy tắc origin được JDK hỗ trợ. Policy đó **không** giúp phân biệt hai user trên cùng hostname.

Hoạt động dự kiến:

~~~text
Server response: Set-Cookie: sid=token-A; Path=/
       |
       v
CookieManager.put(responseUri, headers)
       |
       v
CookieStore giữ cookie ứng với URI/scope
       |
     Request tiếp theo tới URI phù hợp
       |
       v
CookieManager.get(requestUri, headers)
       |
       v
Header Cookie: sid=token-A
~~~

Ứng dụng **không phải** tự gọi `put/get` cho luồng HTTP client bình thường nếu đã gắn manager bằng `HttpClient.Builder.cookieHandler(...)`. CookieHandler được client dùng trong quá trình gửi/nhận.

### Mặc định của HttpClient có tự giữ cookie không?

Theo Java 17 `HttpClient.cookieHandler()`, nếu builder **không** đặt `cookieHandler(...)`, method trả `Optional.empty()`. Không tự suy đoán rằng client mới sẽ lưu mọi `Set-Cookie` như một trình duyệt. Nếu muốn duy trì session bằng cookie một cách có chủ đích, **cấu hình rõ manager**; nếu muốn stateless, **không gắn cookie handler có trạng thái**.

JDK cũng có `CookieHandler.setDefault(...)` là API cấu hình **mức tiến trình** cho các consumer dùng default handler. Không dùng một manager toàn cục làm “phiên chung” trong backend đa người dùng. Với `HttpClient`, cấu hình `cookieHandler(...)` ở builder là cách làm ranh giới rõ hơn.

### CookieStore có thể bị chia sẻ ngầm như thế nào?

~~~java
CookieManager sharedCookies = new CookieManager();

HttpClient userA = HttpClient.newBuilder()
        .cookieHandler(sharedCookies).build();

HttpClient userB = HttpClient.newBuilder()
        .cookieHandler(sharedCookies).build();
~~~

**Đây là phản ví dụ khi hai client đại diện cho hai người dùng khác nhau.** Mặc dù `userA != userB`, cả hai đều dùng **cùng đối tượng CookieManager và CookieStore**. Nếu họ gọi cùng một hostname, cookie cùng tên/path có thể ghi đè trạng thái nhau. Hai client instances **không** tự tách cookie state khi được truyền cùng store.

**Bất biến an toàn hơn:** Với cookie-backed identity, một logical session/tenant isolation boundary phải sở hữu **CookieManager/CookieStore riêng**, không được leak reference cho session của người khác.

## 5. Hai mô hình chủ đạo: cookie-backed session và stateless per-request credentials

| Câu hỏi thiết kế | Cookie-backed user session | Stateless/per-request token |
| --- | --- | --- |
| Danh tính được mang đi bằng gì? | `Cookie: sid=...` do CookieManager gửi | `Authorization: Bearer ...` hoặc header xác thực từng request |
| Trạng thái client cần giữ | CookieStore riêng cho từng session | Token được cung cấp từ request context/credential provider |
| Có nên dùng một HttpClient cho mọi user? | **Không** nếu dùng chung cookie/auth state; thông thường tạo client+manager riêng theo user | **Có thể**, nếu client không có cookie/auth/proxy state riêng user và headers tách theo request |
| Cơ chế logout | Invalidate server session và hết hạn cookie | Revoke/expire token theo chính sách; ngừng dùng token ở client |
| Nguy cơ cross-user | Dùng chung CookieManager/Authenticator hoặc cookie scope | Dùng mutable global `currentToken` hoặc gắn header của user trước vào request sau |
| Yêu cầu bảo mật | HTTPS, cookie flags, CSRF policy, session rotation | HTTPS, token validation/expiry/rotation, không log secrets |
| Trường hợp phù hợp | Web-like session, API cần cookies, legacy app | Backend fan-out, service-to-service API, mỗi call mang credential rõ ràng |

**Không có đáp án duy nhất “tạo mới HttpClient trên mọi request”.** Mục tiêu là **tách state chứa danh tính**, không nhất thiết tách vật lý TCP connection cho mọi request. Tạo quá nhiều clients có thể tốn resources và giảm tái sử dụng connection; dùng chung client sai cách lại rò phiên. Cần chọn mô hình theo việc client có nắm state cá nhân hay không.

## 6. Thiết kế cookie session riêng theo người dùng

Một công thức dễ kiểm toán:

~~~text
User A session context:
  CookieManager A -> CookieStore A
  HttpClient A    -> cookieHandler(A)
  A auth/session lifecycle
  A request/response metadata

User B session context:
  CookieManager B -> CookieStore B
  HttpClient B    -> cookieHandler(B)
  B auth/session lifecycle
  B request/response metadata

A và B có thể gọi cùng https://api.example.com/
nhưng cookies không nằm trong cùng một kho.
~~~

Ví dụ factory (snippet độc lập về mặt cú pháp, chưa có main):

~~~java
static HttpClient newSessionClient() {
    CookieManager cookies = new CookieManager(
            null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
    return HttpClient.newBuilder()
            .cookieHandler(cookies)
            .followRedirects(HttpClient.Redirect.NEVER)
            .connectTimeout(Duration.ofSeconds(3))
            .build();
}
~~~

Mỗi lời gọi factory tạo **manager mới** và **client mới**. Ưu điểm: loại bỏ chia sẻ CookieStore vô tình. Nhưng vẫn cần phân quyền ở server; một client riêng không cứu được tình huống developer vô tình copy header `Authorization` của Alice sang request của Bob.

**Đặc biệt với multi-tenant backend:**
- Tenant ID lấy từ authenticated request context, **không** tin hoàn toàn tham số `tenantId` do caller cung cấp.
- Ánh xạ rõ `tenant/user session key → session context`; không dùng một biến static giữ client đang đăng nhập gần nhất.
- Chặn một user tìm/truy cập session context của user khác (authorization phía application).
- Nếu cache context, dùng expiry, giới hạn tổng số session/clients và dọn reference/credentials khi hết hạn.
- Không lưu plain-text token hoặc cookie trong log, metrics labels hay exception message.
- Tách cache kết quả ứng dụng có chứa dữ liệu cá nhân theo user/tenant; chỉ tách cookies là chưa đủ.

## 7. Ví dụ Java 17+ hoàn chỉnh: hai user, hai CookieManager, login và logout

Chương trình **`SessionIsolationDemo.java`** gồm một HTTP server thử nghiệm chạy trên `127.0.0.1`, cổng do OS tự chọn, và ba `HttpClient` riêng. Server:
- Nhận `POST /login` với body `"alice"` hoặc `"bob"`.
- Tạo mã session ngẫu nhiên 256-bit bằng `SecureRandom` và `Base64 URL-safe`; lưu `sessionToken → username` trong `ConcurrentHashMap`.
- Gửi `Set-Cookie: sid=...; Path=/; HttpOnly; SameSite=Lax` cho client. Demo dùng **HTTP localhost** nên cố ý **không** thêm `Secure`; production session cookie qua HTTPS **phải** dùng Secure phù hợp.
- `GET /whoami` đọc cookie và tra server-side map để xác định user.
- `POST /logout` xóa session khỏi map và gửi cookie `Max-Age=0`.

Đây là **mô phỏng quản lý session**, không phải hệ thống đăng nhập thật: server chỉ nhận username trong body để dễ chứng minh state, **không xác thực password/OAuth và không có CSRF middleware**. Trong production, không bao giờ cho phép bất cứ ai tuyên bố “alice” rồi tạo phiên Alice như fixture này.

Sau khi chạy luồng **an toàn**, chương trình cố tình tạo **hai HttpClient khác nhau nhưng gắn chung CookieManager** để quan sát lỗi: người dùng thứ hai login Bob và cookie `sid` trong kho chung thay thế cookie của Alice; gọi tiếp từ `unsafeOne` nhìn thấy danh tính Bob.

Tạo file **`SessionIsolationDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class SessionIsolationDemo {
    static final Map<String, String> sessions =
            new ConcurrentHashMap<>();
    static final SecureRandom random = new SecureRandom();

    static String randomToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding().encodeToString(bytes);
    }

    static String sessionCookie(HttpExchange ex) {
        String header = ex.getRequestHeaders().getFirst("Cookie");
        if (header == null) return null;

        for (String entry : header.split(";")) {
            String part = entry.trim();
            if (part.startsWith("sid=")) {
                return part.substring(4);
            }
        }
        return null;
    }

    static void reply(
            HttpExchange ex, int status, String body, String cookie)
            throws IOException {

        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        ex.getResponseHeaders().set("Cache-Control", "no-store");

        if (cookie != null) {
            ex.getResponseHeaders().set("Set-Cookie", cookie);
        }

        ex.sendResponseHeaders(status, data.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(data);
        }
    }

    static void handle(HttpExchange ex) throws IOException {
        String path = ex.getRequestURI().getPath();
        String method = ex.getRequestMethod();

        if (path.equals("/login") && method.equals("POST")) {
            String name = new String(
                    ex.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8);

            if (!name.equals("alice") && !name.equals("bob")) {
                reply(ex, 400, "unknown-user", null);
                return;
            }

            String sid = randomToken();
            sessions.put(sid, name);
            reply(ex, 200, "logged-in",
                    "sid=" + sid + "; Path=/; HttpOnly; SameSite=Lax");

        } else if (path.equals("/whoami") && method.equals("GET")) {
            String sid = sessionCookie(ex);
            String name = sid == null ? null : sessions.get(sid);
            reply(ex, 200, name == null ? "anonymous" : name, null);

        } else if (path.equals("/logout") && method.equals("POST")) {
            String sid = sessionCookie(ex);
            if (sid != null) sessions.remove(sid);

            reply(ex, 200, "logged-out",
                    "sid=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax");

        } else {
            reply(ex, 404, "not-found", null);
        }
    }

    static HttpClient isolatedClient() {
        CookieManager cookies = new CookieManager(
                null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

        return HttpClient.newBuilder()
                .cookieHandler(cookies)
                .followRedirects(HttpClient.Redirect.NEVER)
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    static String get(HttpClient client, URI root, String path)
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                        root.resolve(path))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        if (response.statusCode() != 200) {
            throw new IOException("GET status: " + response.statusCode());
        }
        return response.body();
    }

    static void post(
            HttpClient client, URI root, String path, String body)
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                        root.resolve(path))
                .timeout(Duration.ofSeconds(3))
                .POST(HttpRequest.BodyPublishers.ofString(
                        body, StandardCharsets.UTF_8))
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());

        if (response.statusCode() != 200) {
            throw new IOException("POST status: "
                    + response.statusCode());
        }
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
            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());

            HttpClient alice = isolatedClient();
            HttpClient bob = isolatedClient();
            HttpClient fresh = isolatedClient();

            System.out.println("Alice before login: "
                    + get(alice, root, "/whoami"));

            post(alice, root, "/login", "alice");
            System.out.println("Alice after login: "
                    + get(alice, root, "/whoami"));

            System.out.println("Bob before login: "
                    + get(bob, root, "/whoami"));

            post(bob, root, "/login", "bob");
            System.out.println("Bob after login: "
                    + get(bob, root, "/whoami"));

            System.out.println("Alice after Bob login: "
                    + get(alice, root, "/whoami"));

            System.out.println("Fresh client: "
                    + get(fresh, root, "/whoami"));

            post(alice, root, "/logout", "");
            System.out.println("Alice after logout: "
                    + get(alice, root, "/whoami"));

            System.out.println("Bob after Alice logout: "
                    + get(bob, root, "/whoami"));

            // PHẢN VÍ DỤ: Hai client khác nhau dùng CHUNG CookieManager.
            CookieManager sharedCookies = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

            HttpClient unsafeOne = HttpClient.newBuilder()
                    .cookieHandler(sharedCookies).build();
            HttpClient unsafeTwo = HttpClient.newBuilder()
                    .cookieHandler(sharedCookies).build();

            post(unsafeOne, root, "/login", "alice");
            post(unsafeTwo, root, "/login", "bob");

            System.out.println("Shared CookieManager leak: "
                    + get(unsafeOne, root, "/whoami"));
        } finally {
            server.stop(0);
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SessionIsolationDemo.java
java SessionIsolationDemo
~~~

**Kết quả thực thi đã kiểm tra bằng Java 17-compatible API trên loopback:**

~~~text
Alice before login: anonymous
Alice after login: alice
Bob before login: anonymous
Bob after login: bob
Alice after Bob login: alice
Fresh client: anonymous
Alice after logout: anonymous
Bob after Alice logout: bob
Shared CookieManager leak: bob
~~~

### Phân tích: vì sao Alice không bị ảnh hưởng trong luồng đúng?

- `alice = isolatedClient()` tạo `CookieManager A`, `bob = isolatedClient()` tạo `CookieManager B`, `fresh` tạo store C rỗng.
- Khi Alice login, cookie có `sid=tokenAlice` chỉ vào **store A**; Bob login được `tokenBob` chỉ vào **store B**.
- Request `get(alice, "/whoami")` tiếp theo gửi `tokenAlice`, còn `bob` gửi `tokenBob`. Cùng server, URI và đường dẫn nhưng khác user identity.
- Client mới không có cookie và server trả `anonymous`. Điều đó chứng minh **không có phiên ngầm được kế thừa chỉ vì cùng JVM hoặc host**.
- Logout Alice invalidates session token phía server và gửi cookie hết hạn; client Alice trở về anonymous, Bob vẫn còn đăng nhập.
- Trong **phần sai**, `unsafeOne` và `unsafeTwo` cùng giữ `sharedCookies`. Sau login Bob, cookie trong store chung cho cùng hostname/path là Bob; vì thế `unsafeOne` quan sát thấy Bob. Đây là lỗi cross-user state leakage, **không** phải lỗi TLS hoặc HTTP connection pool.

Mã này **không xuất session token ra stdout**: chỉ in kết quả danh tính được server trả về. Ở sản phẩm thật, cũng tránh log raw cookie, Authorization header, session ID và thông tin nhạy cảm.

### Những thứ fixture đã lược giản

- Login ở đây chỉ đọc username, **không xác minh mật khẩu/tài khoản**. Production phải xác thực credentials thực.
- Server lưu session map trong RAM, **không có expiration, replication, idle timeout, session rotation sau đổi quyền**, chống replay hay CSRF middleware; production phải bổ sung.
- Server parse `Cookie` bằng cách tách `;` chỉ vì fixture dùng tên cookie đơn giản, không phải cookie parser chuẩn đầy đủ.
- Cookie không có `Secure` vì request ở `http://127.0.0.1`; không dùng cách đó cho session cookie qua Internet.
- Demo chỉ có hai tên `alice/bob` và không có dữ liệu người dùng thật.
- Java 17 không có API `HttpClient.close()`; ví dụ dừng server bằng `server.stop(0)`. Với ứng dụng lâu dài, cần lifecycle cho client/session contexts theo runtime/framework.

## 8. Session lifecycle: login, refresh, logout và hết hạn

Giữ session không đồng nghĩa giữ mã cookie mãi mãi. Thiết kế cần mô tả **vòng đời**:

~~~text
[anonymous]
     |
     | successful authentication
     v
[active session] -- reissue/rotate --> [active new session]
     |                                    |
     | logout / revocation / expiry       | timeout
     v                                    v
[revoked / expired]                 [expired]
     |
     +--> request có token cũ = unauthorized
~~~

**Khi login:**
- Server xác thực credentials đúng.
- Tạo session ID ngẫu nhiên có đủ entropy, không tin session ID do caller tự chọn.
- **Rotate** session token khi chuyển anonymous → authenticated để giảm nguy cơ session fixation.
- Đặt idle timeout và absolute timeout server-side.
- Chỉ lưu thông tin tối thiểu; session store nên quản lý TTL, audit và revocation.

**Khi phiên đang hoạt động:**
- Mỗi request được server xác định lại bằng cookie/token.
- Chỉ cho phép tài nguyên theo **authenticated principal** và quyền/tenant đã được xác minh.
- Nếu quyền/tài khoản đổi, cập nhật/revoke session theo policy; không chỉ đổi text hiển thị ở client.
- Nếu có CSRF threat model, bảo vệ các thao tác thay đổi trạng thái bằng CSRF token, Origin checks và/hoặc SameSite policy phù hợp; đừng dựa vào một thuộc tính duy nhất.

**Khi logout:**
- Server invalidate session token **ngay cả khi browser/Java client vẫn giữ cookie cũ**.
- Gửi `Set-Cookie` với `Max-Age=0` cùng scope/domain/path phù hợp để yêu cầu xóa cookie.
- Xóa token khỏi user credential store, clear phiên và vô hiệu hóa hoạt động tiếp theo của session khi có thể.
- Nếu app có nhiều phiên trên nhiều thiết bị, phân biệt “logout phiên hiện tại” và “logout mọi phiên”.

**Không dùng `CookieStore.removeAll()` thay thế server-side revocation.** Xóa cookie ở client chỉ ngăn client đó tự gửi lại token; một kẻ khác đã sao chép token vẫn có thể dùng nó nếu server chưa hết hạn/revoke.

## 9. Khi nào phải tách một HttpClient theo session?

**Tách HttpClient + CookieManager** thường phù hợp khi:
- Ứng dụng đóng vai một người dùng trong suốt một session.
- Server legacy dùng session cookie tự động, nhiều requests phải liên tục gửi đúng cookie.
- Người dùng/tenant có cấu hình `Authenticator`, proxy credentials hoặc client TLS identity riêng.
- Bạn muốn ranh giới implementation đơn giản, dễ kiểm thử, ít khả năng share state sai.

Mẫu conceptual:

~~~text
Map<AuthenticatedSessionKey, SessionClientContext>

SessionClientContext {
    HttpClient client;
    CookieManager cookieManager;
    auth/proxy configuration;
    session expiry + lifecycle policy;
}
~~~

Đây là **sơ đồ cấu trúc**, không phải Java class hoàn chỉnh. Trong sản phẩm, cần đảm bảo context map có bounded capacity, TTL/eviction và session keys không chứa raw bearer tokens. Dữ liệu context không được trả trực tiếp cho tenant khác.

Nhưng tách một client **cho mỗi incoming HTTP request** là cực đoan không cần thiết, có thể giảm connection reuse. Một context theo user-session có thể phục vụ **nhiều requests** trong thời gian phiên còn hợp lệ.

**Tách CookieManager quan trọng hơn tên của client.** Dùng hai clients khác nhau nhưng cùng `CookieStore` là lỗi; dùng một client không giữ user state và tự thêm token riêng vào request đôi khi an toàn và tiết kiệm hơn.

## 10. Mô hình stateless: một HttpClient dùng chung, Authorization nằm ở mỗi request

Với API xác thực theo bearer token hoặc một cơ chế xác thực khác gắn trên **mỗi request**, bạn có thể tạo một `HttpClient` không cấu hình cookie handler hoặc user-specific authenticator:

~~~java
HttpClient shared = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest aliceRequest = HttpRequest.newBuilder(uri)
        .header("Authorization", "Bearer " + aliceToken)
        .GET()
        .build();

HttpRequest bobRequest = HttpRequest.newBuilder(uri)
        .header("Authorization", "Bearer " + bobToken)
        .GET()
        .build();
~~~

Đây là **snippet** với các token giả định được lấy qua credential provider an toàn, không được hard-code vào source. `HttpRequest` được build bất biến, nên khi gửi đồng thời, thông tin xác thực nằm trên **request tương ứng**, không nằm trong một biến `currentToken` thay đổi liên tục.

**Mẫu sai hay gặp:**

~~~java
// PHẢN VÍ DỤ: Không dùng biến global mutable cho danh tính.
static String currentToken;

// Thread A đặt Alice token; thread B đổi sang Bob token;
// thread A xây request sau đó có thể vô tình lấy Bob token.
~~~

**Không phụ thuộc hoàn toàn vào `ThreadLocal`** để mang danh tính qua callbacks của `CompletableFuture` hoặc executor: các completion callbacks có thể chạy trên thread khác thread đã nhận request. Hãy truyền authenticated principal/credential reference rõ ràng trong immutable per-request context và tránh capture tham chiếu tới mutable global state.

**Không chia sẻ một `Authenticator` có lưu user/password động** giữa các tenants trên cùng client. Nếu HTTP authentication challenge hoặc proxy authentication dùng thông tin tùy user, cần thiết kế tenant-aware implementation được kiểm toán hoặc client/context riêng.

## 11. Ví dụ Java 17+ hoàn chỉnh: cùng HttpClient, token riêng theo từng HttpRequest

Ví dụ **`RequestIdentityIsolationDemo.java`** sử dụng một HTTP server giả lập:
- Header `Authorization: Bearer demo-key-a` được fixture ánh xạ tới `alice`.
- Header `Authorization: Bearer demo-key-b` được fixture ánh xạ tới `bob`.
- Không có header hoặc giá trị không hợp lệ → `anonymous`.
- Cả Alice, Bob và request anonymous được gửi **gần như đồng thời** bằng một `HttpClient.sendAsync` chung.
- Mỗi lời gọi tạo một `HttpRequest` mới; **không có CookieManager** hoặc mutable current user token.
- Output in theo thứ tự `Future.get` được gọi, **không** chứng minh thứ tự response hoàn thành.

**Các chuỗi demo-key-a/demo-key-b là khóa giả để thử phần routing**, không phải access token an toàn. Server production phải xác minh chữ ký/expiry/audience hoặc introspect token thực và chỉ chạy qua HTTPS.

Tạo file **`RequestIdentityIsolationDemo.java`**:

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
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class RequestIdentityIsolationDemo {
    static void handle(HttpExchange ex) throws IOException {
        String auth = ex.getRequestHeaders().getFirst("Authorization");

        String body =
                "Bearer demo-key-a".equals(auth) ? "alice" :
                "Bearer demo-key-b".equals(auth) ? "bob" : "anonymous";

        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Cache-Control", "no-store");
        ex.sendResponseHeaders(200, data.length);

        try (OutputStream out = ex.getResponseBody()) {
            out.write(data);
        }
    }

    static HttpRequest request(URI uri, String demoToken) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .GET();

        if (demoToken != null) {
            builder.header("Authorization", "Bearer " + demoToken);
        }
        return builder.build();
    }

    static String body(
            CompletableFuture<HttpResponse<String>> future)
            throws Exception {

        HttpResponse<String> response =
                future.get(3, TimeUnit.SECONDS);

        if (response.statusCode() != 200) {
            throw new IOException("HTTP " + response.statusCode());
        }
        return response.body();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/me", ex -> {
            try {
                handle(ex);
            } catch (IOException error) {
                ex.close();
            }
        });
        server.start();

        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/me");

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            var handler = HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8);

            CompletableFuture<HttpResponse<String>> a =
                    client.sendAsync(request(uri, "demo-key-a"), handler);
            CompletableFuture<HttpResponse<String>> b =
                    client.sendAsync(request(uri, "demo-key-b"), handler);
            CompletableFuture<HttpResponse<String>> none =
                    client.sendAsync(request(uri, null), handler);

            System.out.println("Alice: " + body(a));
            System.out.println("Bob: " + body(b));
            System.out.println("Anonymous: " + body(none));

            System.out.println("Alice again: " + body(
                    client.sendAsync(
                            request(uri, "demo-key-a"), handler)));

            System.out.println("Client cookie handler absent: "
                    + client.cookieHandler().isEmpty());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RequestIdentityIsolationDemo.java
java RequestIdentityIsolationDemo
~~~

**Kết quả đã chạy trên loopback:**

~~~text
Alice: alice
Bob: bob
Anonymous: anonymous
Alice again: alice
Client cookie handler absent: true
~~~

### Vì sao một HttpClient vẫn có thể an toàn ở đây?

- `HttpClient` không có cookie handler nên không giữ session cookie riêng của Alice/Bob.
- Mỗi `HttpRequest` mang **token giả lập riêng** và request object đã build là immutable.
- Sender không dùng một mutable global credential biến đổi giữa các lời gọi đồng thời.
- Server fixture xác định danh tính **từ header của từng request**, không từ socket cũ.
- Lời gọi A lần thứ hai vẫn là Alice vì request mới cũng chỉ mang Alice token, không kế thừa Bob token.
- `client.cookieHandler().isEmpty() == true` xác nhận không cấu hình CookieHandler trên client.

Điều này **không** có nghĩa dùng chung client là an toàn bất kể cấu hình: nếu bạn thêm shared cookie handler, user-dependent authenticator, proxy credentials hoặc header injection sai, ranh giới lại thay đổi. Quyết định phải dựa trên **state thực sự gắn vào client** và contract xác thực của downstream.

## 12. Authorization, Cookie và Authenticator không giống nhau

Các cơ chế mang danh tính:

| Cơ chế | Cấp độ phổ biến | Rủi ro chia sẻ |
| --- | --- | --- |
| Header `Cookie` chứa session ID | Từng HTTP request, được client cookie manager gắn tự động | Shared CookieStore khiến user sau ghi đè session trước |
| Header `Authorization: Bearer ...` | Từng HTTP request | Global mutable token/request-builder reuse hoặc retry sang URL sai |
| `HttpClient.Builder.authenticator(...)` | Cấu hình của HttpClient cho HTTP auth challenges | Authenticator có thể nắm credentials/cache, không được share user context tùy tiện |
| Proxy credentials (ví dụ 407 challenge) | Proxy/network access layer | Một proxy account hoặc credential cache dùng lẫn giữa tenants |
| mTLS client certificate/private key | TLS connection/client SSLContext | Chứng chỉ client đại diện danh tính khác; phải tách TLS security context khi cần |
| Server session cache / app result cache | Server/business layer | Key thiếu tenant/user ID dẫn tới data leakage dù cookies tách đúng |

**Cookie** và **Authorization** có thể cùng hiện diện trên một request. Khi cả hai có danh tính khác nhau, server phải định nghĩa chính sách rõ ràng (từ chối/mismatch), thay vì ngẫu nhiên chọn một. Một header `Authorization` mới trên request không tự xóa cookie session mà CookieManager sẽ gắn thêm.

**Authenticator** trong Java là cơ chế phản hồi authentication challenge (thường HTTP Basic/Digest hoặc proxy), không phải nơi bạn tự động đặt OAuth bearer token cho mọi request. Với OAuth2 access token, thông thường ứng dụng cấp header trên từng request hoặc dùng interceptors/middleware có context isolation đã kiểm toán.

**Không xem IP/proxy IP là định danh người dùng:** Nhiều người dùng có thể đi qua một NAT/proxy; một người dùng có thể đổi IP giữa requests. Cần danh tính đã xác thực và session/token phù hợp.

## 13. Proxy và session: thay mạng không được thay danh tính

Trong chủ đề **Proxy và phiên HTTP**, thường gặp cấu hình:

~~~java
HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.example", 8080)))
        .build();
~~~

Đây là snippet với hostname/cổng minh họa, không phải proxy thật. `ProxySelector` chọn đường đi network, **không phân vùng session/cookie theo người dùng**. Cookie vẫn được chọn dựa trên URI và cookie policy; cùng một proxy có thể phục vụ nhiều user nhưng không nên trộn credentials.

Các nguyên tắc:
1. **Proxy cho outbound route** và **user session cho HTTP authentication** là hai bài toán riêng.
2. Nếu proxy cần per-tenant account/password, gắn authenticator hoặc client context riêng cho tenant; đừng thay đổi shared global default password authenticator trên nhiều threads.
3. Với HTTP CONNECT để đi HTTPS, app vẫn phải xác minh hostname/certificate ở TLS endpoint. Việc dùng proxy không tạo sẵn trust boundary cho credentials.
4. Không gửi `Authorization` của website tới proxy như thể nó là `Proxy-Authorization`, và không gửi proxy credentials tới upstream API không phù hợp.
5. Nếu hệ thống tuân thủ outbound proxy và có allowlist, không cho untrusted URL/redirect đưa request tới host/private address trái policy.
6. Proxy/connection pool có thể giữ state ở tầng kết nối theo provider, nhưng **không được dựa vào connection reuse để quyết định user principal**.

**Redirect đặc biệt nguy hiểm:** Nếu một API trả `3xx Location` sang host khác, client có thể follow theo `HttpClient.Redirect` policy. Chính sách nên cấm hoặc tái thẩm định redirects qua trust boundary, nhất là khi cookie, bearer token hay credentials có thể bị gửi/sao chép ngoài ý muốn. Trong hai demo đặt `Redirect.NEVER` hoặc không sử dụng redirect để giữ ví dụ rõ ràng.

## 14. Cookie domain/path và các ranh giới bị hiểu nhầm

Giả sử có ba ứng dụng cùng hostname:

~~~text
https://app.example.com/admin
https://app.example.com/shop
https://app.example.com/api
~~~

Nếu mỗi ứng dụng đều dùng `sid` với `Path=/`, có nguy cơ cookie names/scope chồng chéo hoặc server dùng nhầm session token, tùy cách set-cookie và client jar hoạt động.

Điểm cần nhớ:
- `Domain` và `Path` hỗ trợ **routing cookie**, không phải authorization/tenant isolation.
- Không có trường `userId` bên trong cookie scope để JDK CookieManager tự biết Alice/Bob.
- Cookie tên giống nhau trên cùng host/path có thể **thay thế** nhau, như chương trình đầu chứng minh.
- Cookie từ subdomain/domain rộng có thể tạo tác động ở ứng dụng cùng scope; cần kiểm soát nơi được phép phát cookies.
- Không giả định HTTP cookies phân vùng độc lập theo port hoặc theo đối tượng HttpClient nếu chúng **dùng cùng CookieManager**.
- Ưu tiên domain/path hẹp theo nhu cầu, tránh đặt `Domain` rộng nếu không cần.
- Khi cần isolation mạnh giữa các ứng dụng không tin cậy, dùng hostnames/security origins tách rõ ràng và authorization server-side; không chỉ phụ thuộc cookie Path.

**Gợi ý bảo mật cho browser cookie:** Prefix `__Host-` với điều kiện Secure, Path=/, không có Domain có thể tăng chặt chẽ host-bound semantics trên các user agents hỗ trợ. Nhưng JDK CookieManager không nên được mặc nhiên xem là trình duyệt thực thi mọi cơ chế prefix/SameSite hiện đại. Luôn kiểm tra contract của client và kiểm soát logic server.

## 15. Logout, xóa cookie và dọn dữ liệu khi session kết thúc

Với session do bạn sở hữu, **đúng nghĩa logout** cần kết hợp server-side và client-side:

~~~text
Application signals logout
        |
        v
Server invalidates / revokes session ID
        |
        v
Server returns expired Set-Cookie for matching scope
        |
        v
Client's CookieManager updates its store
        |
        v
App evicts user session context and other sensitive caches
        |
        v
Further requests must not use old user identity
~~~

Có thể xóa toàn bộ cookie store của **một** logical session khi không muốn tái sử dụng:

~~~java
CookieManager manager = /* manager RIÊNG cho session này */;
manager.getCookieStore().removeAll();
~~~

Đây là snippet: thực tế lấy `manager` từ context được kiểm toán, không duyệt global shared cookie store. **Không gọi `removeAll()` trên manager dùng chung** trong hệ thống đa người dùng vì sẽ phá session của tất cả.

Còn những thứ cần clear ngoài cookie:
- OAuth access/refresh tokens và credential handles.
- Session-scoped authorization context, response cache, temporary file/downloads.
- Queued HTTP jobs còn gắn token cũ.
- HTTP headers/client context nắm private data qua references.
- Observability tags chứa user data nhạy cảm.
- Session-associated resources khi tenant bị xóa/thu hồi.

**Xóa cookie local không thay session invalidation**. Nếu server chưa revoke, token cũ bị đánh cắp vẫn hợp lệ đến khi expiry. Logout ở server phải là authoritative, đồng thời invalidate/rotate refresh tokens theo nhu cầu.

## 16. Session fixation, hijacking, CSRF và quyền truy cập

Những mối đe dọa liên quan đến giữ session:

**Session fixation:** Trước login client có cookie do attacker kiểm soát; nếu server tiếp tục dùng ID đó sau authentication, attacker có thể biết ID phiên đã được nâng quyền. **Đổi session ID khi login hoặc thay đổi privilege**; không nâng quyền cho một session ID do client đề xuất.

**Session hijacking:** Kẻ tấn công lấy được bearer cookie/token. Bảo vệ bằng HTTPS, `Secure`/`HttpOnly` cho browser cookies, không log secrets, expiration, short-lived tokens và revocation. `HttpOnly` không bảo vệ cookie khỏi code Java ở backend đọc CookieStore; nó là giới hạn với JavaScript trong browser.

**CSRF:** Trình duyệt có thể tự gắn cookies vào requests trong một số ngữ cảnh; bảo vệ thao tác thay đổi trạng thái bằng CSRF token, SameSite cookie policy và/hoặc kiểm tra Origin/Referer thích hợp. **Không giả định Java HttpClient hỗ trợ đầy đủ hành vi browser SameSite** hay các cơ chế cookie partitioning hiện đại.

**Horizontal privilege escalation / IDOR:** Dù session hợp lệ của Alice, endpoint `GET /users/bob/orders` vẫn phải kiểm tra Alice có được phép xem Bob hay không. Cookie isolation **không thay** resource-level authorization.

**SSRF:** Trong backend proxy request từ dữ liệu người dùng, không cho caller chọn URI tùy ý rồi vô tình gửi cookies/tokens tới nội bộ hoặc host ngoài trust boundary. Allowlist host/service, kiểm tra redirect target, DNS/IP ranges và outbound network rules.

**Multi-tenant caches:** Dùng cache key chỉ bằng `GET /profile` có thể khiến data Alice trả cho Bob. Cache key cần chứa authenticated tenant/user scope hoặc không cache dữ liệu riêng nếu không đảm bảo isolation.

## 17. Đồng thời: request context, callbacks và race conditions

Khi nhiều requests chạy cùng lúc, kể cả với `CompletableFuture`:

~~~text
Thread A (request của Alice) ---> token Alice
Thread B (request của Bob)   ---> token Bob
                   |
                   v
           shared HTTP client
                   |
           sendAsync(reqA, ...)
           sendAsync(reqB, ...)
                   |
            callbacks có thể chạy
              ở thread khác
~~~

**Không dùng một biến static mutable `currentUser` hoặc `currentToken`** mà cả hai threads cập nhật. Nếu A set token, B set token, A xây `HttpRequest` sau đó, request của A có thể mang token B.

Cách an toàn:
- Nhận authenticated principal/tenant ID từ request entrypoint.
- Tạo một **immutable request context** riêng (requestId, tenantId, credential reference).
- Xây `HttpRequest` riêng, đặt `Authorization` header cho đúng credential; không reuse một `HttpRequest.Builder` đang bị threads khác sửa.
- Nếu cookie-backed session, lấy đúng SessionClientContext đã map tới principal đó, và tránh cho tenant khác tham chiếu tới context.
- Truyền correlation context vào callbacks một cách rõ ràng; **không giả định ThreadLocal tự truyền qua executors**.
- Kiểm tra cùng userID/tenantID khi phản hồi cập nhật cache, DB hoặc data sink; đừng chỉ tin vào thứ tự completion.

Bản thân `HttpClient` hỗ trợ gửi requests từ nhiều threads. Điều này **không biến mutable CookieStore, custom Authenticator, application cache hay user session map thành thứ tự phân quyền tự động**.

## 18. Có nên lưu session trên máy chủ hay trong token?

Hai mô hình có trade-offs:

| Mô hình | State cần ở server | Ưu điểm | Điều phải quản lý |
| --- | --- | --- | --- |
| Random opaque session ID + server session store | Có: ID → user, TTL, permissions | Dễ revoke/session rotation tập trung, client chỉ giữ opaque ID | Store availability, replication, expiry, fixation protection |
| Signed self-contained access token | Có thể không cần state cho mỗi access token | Dễ xác minh phân tán và gửi trong Authorization | Signature, audience, scopes, expiry, key rotation và revocation strategy |
| Cookie chứa signed token | Không nhất thiết có map riêng | Browser-friendly cơ chế chuyển token | Các vấn đề cookie/CSRF và kiểm chứng token trên mỗi request |

**Đừng đồng nhất “stateless server JWT” với “client không có state”.** Client vẫn phải có chỗ lấy token cho từng request, biết refresh/expiry và cách tránh trộn identity. Ngược lại, dùng server-side session store không có nghĩa socket hay CookieManager phải giữ một đối tượng Java toàn cục.

**Cookie** là cách chuyển credential qua HTTP; **session** là khái niệm nghiệp vụ/xác thực. Có thể đưa token vào cookie, hoặc đặt token trong Authorization header. Bảo mật phụ thuộc verification và ranh giới state, không phải chỉ vị trí của token.

## 19. Tránh memory/resource leak khi tạo client theo người dùng

Một vấn đề kiến trúc: nếu backend tạo `HttpClient` và `CookieManager` mới cho từng user nhưng **không bao giờ dọn**, số lượng clients và session stores có thể tăng vô hạn.

Thiết kế session-context cache nên có:
- Giới hạn số contexts tối đa và admission control.
- TTL/idle timeout tương ứng server session.
- Logout/revocation xóa cache và cookies.
- Quyền lấy context được kiểm tra theo authenticated principal.
- Quota memory/connection/downstream riêng khi tenants nhiều.
- Không lưu credential quá lâu hơn nhu cầu.
- Không truyền session context references qua các thread/queues mà không kiểm soát vòng đời.
- Ghi metrics theo nhóm/tenant an toàn, không dùng session token làm label.

**JDK version nuance:** Java 17 `HttpClient` chưa có vòng đời `AutoCloseable/close()` như những API xuất hiện trong JDK mới hơn. Đừng viết `try (HttpClient client = ...)` và kỳ vọng nó biên dịch trên Java 17. Với JDK hiện đại, kiểm tra đúng API lifecycle theo phiên bản, nhưng việc xóa session context/cookie/credential ở tầng ứng dụng vẫn là trách nhiệm riêng.

Với mô hình **per-request Authorization** và một client stateless chung, có thể giảm số HttpClient instances, nhưng vẫn cần quản lý token cache theo user/tenant và clear/revoke khi login/logout.

## 20. Checklist thiết kế hệ thống đa người dùng

| Câu hỏi kiểm tra | Mục tiêu |
| --- | --- |
| Ai sở hữu cookie jar? | Per-session manager, không có shared CookieManager giữa users |
| Có dùng default/global CookieHandler không? | Không vô tình tạo global shared session |
| HttpClient có Authenticator không? | Nếu có, credentials thuộc đúng user/tenant |
| Proxy credentials thuộc ai? | Không lẫn proxy user với HTTP app principal |
| Client có tự follow redirects không? | Không gửi credentials qua trust boundary không được phép |
| Cookie Domain/Path/Secure/HttpOnly/SameSite thế nào? | Scope tối thiểu, HTTPS, server policy phù hợp |
| Login có rotate session ID không? | Chống session fixation |
| Logout có invalidate server session không? | Chặn replay token cũ |
| Mọi endpoint có kiểm tra authorization không? | Chống IDOR/cross-tenant access |
| Cache có key theo tenant/user không? | Chống data leakage từ cached responses |
| HTTP calls đồng thời có immutable per-request identity không? | Không có global currentToken race |
| Callbacks có giữ đúng request context không? | Không dựa vào ThreadLocal truyền ngầm |
| Có cap session contexts và TTL không? | Không giữ vô hạn clients/cookies/credentials |
| Log có ghi cookies/token/Authorization không? | Không làm lộ secrets |
| Test có gồm A/B concurrent và logout isolation không? | Phát hiện cả rò state và dọn phiên sai |

## 21. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tưởng HTTP keep-alive đồng nghĩa cùng phiên | Gắn identity sai theo connection | Dùng cookie/token đã xác thực trên từng request |
| Tạo hai HttpClient nhưng truyền cùng CookieManager | User B ghi đè cookie của A | CookieManager/CookieStore riêng theo session |
| Dùng `CookieHandler.setDefault` toàn cục cho nhiều tenants | Cross-user state leak ở code sử dụng default | Cấu hình cookie handler tường minh và scoped |
| Tin `CookiePolicy.ACCEPT_ORIGINAL_SERVER` tách users | Vẫn rò cookie trên cùng hostname/path | Tenant isolation ở tầng app, per-user jar |
| Dùng global `currentToken` trong concurrent requests | Request A mang token B | Immutable request context + per-request header |
| Reuse HttpRequest.Builder từ nhiều threads | Races/misplaced headers | Tạo builder/request riêng cho mỗi call |
| Tin ThreadLocal tự đi qua CompletableFuture callbacks | Sai user context trong callbacks | Capture/truyền context rõ ràng |
| Chỉ xóa cookie local khi logout | Token cũ vẫn dùng được ở nơi khác | Server-side session revocation |
| Không rotate session ID khi login | Session fixation | Regenerate session ID sau authenticate |
| Tin cookie HttpOnly làm Java backend không thể đọc | Hiểu sai threat model | HttpOnly dành cho browser JavaScript access |
| Tin SameSite được mọi Java HTTP client tự enforce | Thiếu CSRF protection | Phân tích threat model và implement server checks |
| Cookie Path/Domain rộng không cần thiết | Đụng session giữa apps | Scope tối thiểu, tách hostname khi cần |
| Shared proxy Authenticator giữ mật khẩu user trước | Dùng lẫn credentials | Tenant-specific auth/proxy configuration |
| Tự động follow redirect đến host bất kỳ | Nguy cơ lộ credentials/SSRF | Redirect.NEVER hoặc validate từng destination |
| Cache response chỉ theo URL | Trả dữ liệu A cho B | Key cache kèm tenant/principal hoặc không cache |
| Tạo HttpClient cho mỗi request | Tốn resources, khó reuse | Reuse theo session nếu có cookies, hoặc stateless client chung |
| Tạo HttpClient theo user và không expire | Memory/resource leak | TTL/eviction/bounded context count |
| Đọc session ID từ log khi debug | Lộ bearer secret | Hash/redact/correlate bằng request ID không nhạy cảm |
| Tin login fixture username là authentication thật | Bất kỳ người dùng nào claim được account | Validate credentials và authorization server-side |

## 22. Bài tập tự kiểm tra

**1.** Tại sao cùng một `HttpClient` có thể gửi nhiều HTTP requests mà không có nghĩa tất cả thuộc cùng user?  
**Đáp án:** Client có thể reuse connection/transport, còn user identity phải được truyền/xác minh qua cookie/token/authentication riêng trên từng request.

**2.** Hai HttpClient khác nhau có cùng `CookieManager` thì đã cô lập session chưa?  
**Đáp án:** **Chưa.** Cùng CookieStore sẽ lưu/gửi cookies cho cùng URI scope; một user có thể ghi đè session của user khác.

**3.** Cookie `sid` do server đặt có chứng minh user được phép đọc tài nguyên Bob không?  
**Đáp án:** Không. Server vẫn phải xác định principal và kiểm tra authorization với tài nguyên.

**4.** Khi nào nên tạo một CookieManager cho mỗi người dùng/phiên?  
**Đáp án:** Khi mỗi user/session cần giữ cookies tự động tới cùng hoặc nhiều HTTP endpoints; cookie state không được chia sẻ qua các user.

**5.** Một `HttpClient` chung có thể dùng cho Alice/Bob không?  
**Đáp án:** Có thể nếu client không giữ user-specific cookie/auth/proxy state và mỗi HttpRequest mang credential riêng có ranh giới rõ, như ví dụ 2.

**6.** `CookiePolicy.ACCEPT_ORIGINAL_SERVER` có hiểu tenant ID trong ứng dụng không?  
**Đáp án:** Không. Nó là cookie acceptance policy theo origin, không phải user identity policy.

**7.** `HttpOnly` có ngăn Java CookieManager đọc cookie không?  
**Đáp án:** Không. Thuộc tính này nhằm giới hạn JavaScript phía trình duyệt, không ngăn chính ứng dụng Java đang quản lý cookie.

**8.** Xóa local CookieStore có đủ để logout an toàn không?  
**Đáp án:** Không. Phải invalidate/revoke session phía server vì token đã bị copy vẫn có thể được dùng.

**9.** Tại sao phải rotate session ID khi login?  
**Đáp án:** Để tránh tiếp tục sử dụng một session ID bị attacker biết/đặt trước khi chuyển sang authenticated state (session fixation).

**10.** Vì sao một proxy dùng chung không nên được coi là cơ chế phân biệt user?  
**Đáp án:** Proxy IP/network route không mang principal đã xác thực; nhiều users chia sẻ cùng proxy, nên auth/session vẫn phải tách.

**11.** `CompletableFuture` callback có tự thấy ThreadLocal principal từ thread gửi request không?  
**Đáp án:** Không được giả định; callback có thể chạy trên thread khác, cần capture/truyền context tường minh.

**12.** Cookie `SameSite=Lax` có nghĩa Java HttpClient chắc chắn cư xử như Chrome không?  
**Đáp án:** Không. SameSite là cơ chế bảo vệ ở user-agent/browser context; JDK CookieManager không được xem là browser policy engine.

**13.** Trong ví dụ 1, sau khi Bob login, Alice còn thấy `alice` vì sao?  
**Đáp án:** Vì cookie managers và stores của A/B độc lập; chỉ trong phản ví dụ dùng chung CookieManager mới quan sát nhầm Bob.

**14.** Trong ví dụ 2, vì sao gọi `request(uri, "demo-key-a")` lần nữa vẫn được `alice`?  
**Đáp án:** Token được gắn vào đúng HttpRequest mới, không bị Bob request ghi đè global state.

**15.** Cần test những gì để chắc cross-user isolation?  
**Đáp án:** Hai users gọi cùng endpoint và đồng thời; login user B không ảnh hưởng A; logout A không ảnh hưởng B; fresh client anonymous; redirects/proxy/authenticator và cache không đưa credentials/data qua user boundary.

## Tài liệu tham khảo chính thức

- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client-level configuration, cookieHandler, authenticator, proxy, redirects, transport reuse và sendAsync.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `cookieHandler(...)`, `proxy(...)`, `authenticator(...)` và `followRedirects(...)`.
- [Java SE 17 — CookieManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html): policy, cookie store, mặc định `ACCEPT_ORIGINAL_SERVER`.
- [Java SE 17 — CookieStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieStore.html): lưu, tra và xóa cookies.
- [Java SE 17 — HttpCookie](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpCookie.html): cookie properties như Secure/HttpOnly/Path/Domain.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): immutable requests, request-specific headers và timeout.
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): callbacks, execution context và completion.
- [Java SE 17 — HttpServer (jdk.httpserver)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): HTTP server fixture trong hai ví dụ.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): cookies, Domain/Path, Set-Cookie/Cookie và scope.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session ID, rotation, expiration, logout/revocation, cookie security và threat model.
