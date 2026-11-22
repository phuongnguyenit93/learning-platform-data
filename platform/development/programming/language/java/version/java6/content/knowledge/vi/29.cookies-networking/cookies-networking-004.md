# Cookie và mạng: CookieHandler và tích hợp với HTTP client hiện đại

## Mục tiêu học tập

HTTP là giao thức theo từng request/response; bản thân giao thức không tự biến hai requests thành một **phiên đăng nhập**. Khi server cần duy trì một trạng thái như session, lựa chọn ngôn ngữ, giỏ hàng hoặc thông tin xác thực, nó có thể gửi **`Set-Cookie`** trong response. Ở request tiếp theo phù hợp, client gửi **`Cookie`** để server nhận diện trạng thái đó.

Trong Java, các API **`java.net.CookieHandler`**, **`CookieManager`**, **`CookieStore`**, **`CookiePolicy`**, **`HttpCookie`** vẫn còn được hỗ trợ. Với client HTTP hiện đại **`java.net.http.HttpClient`** (có từ Java 11), tích hợp cookie được thực hiện **tường minh qua `HttpClient.newBuilder().cookieHandler(...)`**, không cần tự nối header Cookie và không nên phụ thuộc vào một biến cấu hình toàn JVM.

Bài học tập trung vào **cơ chế quản lý cookies, cách tích hợp với HttpClient, tính cô lập trạng thái, phạm vi gửi cookie, vòng đời session, bảo mật và hạn chế hiện hành**. Sau bài, bạn có thể:

1. Phân biệt header response **`Set-Cookie`** với header request **`Cookie`**.
2. Giải thích vai trò của `CookieHandler.get(...)` và `CookieHandler.put(...)`: lấy cookie cho một URI và ghi nhận cookie từ response.
3. Hiểu `CookieManager` kết hợp **`CookieStore`** (nơi lưu) và **`CookiePolicy`** (quy tắc nhận/từ chối).
4. Dùng **`CookiePolicy.ACCEPT_ORIGINAL_SERVER`**, `ACCEPT_NONE` và biết khi nào không nên chọn `ACCEPT_ALL`.
5. Tạo **một HttpClient có cookie state riêng** bằng builder; không nhầm với `CookieHandler.setDefault()`.
6. Chia sẻ state **có chủ đích** khi hai `HttpClient` cùng dùng một CookieManager; tách state khi khác user/tenant.
7. Theo dõi `HttpCookie.getName/getPath/isHttpOnly/getSecure/getMaxAge/hasExpired` và xoá state qua `CookieStore.remove/removeAll`.
8. Hiểu **Domain, Path, Max-Age, Expires, Secure, HttpOnly, SameSite**, và biết thuộc tính nào **không được Java CookieManager bảo đảm xử lý như browser**.
9. Không dựa vào biểu diễn chuỗi raw `Cookie` cố định giữa JDK/providers — có thể xuất hiện những trường như `$Version`, `$Path`, `$Domain`.
10. Chạy ví dụ **Java 17+** dùng server loopback tự tạo và nhiều HttpClients để kiểm chứng login, path scope, shared manager, no-cookie client, accept-none và logout.
11. Tránh làm lộ session cookies qua logs, redirect không kiểm soát, nhầm cookie với authorization hoặc dùng chung session store giữa người dùng.
12. Thiết kế test cho cookie expiration, cleanup, TLS, concurrency, redirects và CSRF/cross-site semantics.

**Phạm vi phiên bản:** Bài dùng những API hiện hành trong `java.base`, `java.net.http`, `jdk.httpserver`; chương trình được **biên dịch bằng `javac --release 17` và chạy trên OpenJDK 24.0.2**. Đối với hành vi có thay đổi giữa các JDK, bài nói rõ điều cần kiểm thử thay vì suy từ một runtime sang mọi runtime. Không dựa vào giao thức/kiến thức đã legacy làm hướng triển khai.

---

## 1. Cookie là gì và HTTP client cần làm gì?

Một ví dụ trao đổi đơn giản:

~~~http
GET /login HTTP/1.1
Host: example.test
~~~

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SID=opaque-session-id; Path=/api; Max-Age=600; Secure; HttpOnly; SameSite=Lax
Content-Type: text/plain; charset=UTF-8

login-ok
~~~

Khi gửi request tiếp theo tới URL phù hợp về scheme, host/domain, path và các điều kiện khác, client có thể thêm:

~~~http
GET /api/profile HTTP/1.1
Host: example.test
Cookie: SID=opaque-session-id
~~~

**Ví dụ trên minh họa HTTP với cookie Secure; muốn gửi cookie Secure, URI request thực tế phải dùng HTTPS.** Header `SID=...` chỉ là một ví dụ định dạng hiện đại: implementation Java có thể thêm các trường mang phong cách giao thức cookie khác tùy cookie version và provider. **Không so sánh nguyên văn raw Cookie header** nếu business chỉ cần biết session có được gửi đúng phạm vi hay không.

### 1.1. Phân biệt `Set-Cookie` và `Cookie`

| Header | Bên gửi | Vai trò |
| --- | --- | --- |
| **`Set-Cookie`** | Server → client | Yêu cầu client lưu/thay/xoá một cookie theo thuộc tính |
| **`Cookie`** | Client → server | Gửi những cặp tên/giá trị cookie áp dụng cho request |
| `Authorization` | Client → server | Một cơ chế xác thực khác, không đồng nghĩa cookie |
| `Set-Cookie` lặp nhiều lần | Server → client | Có thể đặt nhiều cookies riêng biệt |
| `Cookie` trên request | Client → server | Có thể mang nhiều cookies |

**`Set-Cookie` không phải header để client dùng nguyên xi làm request.** Những thuộc tính như `Path`, `HttpOnly`, `Secure`, `Max-Age` là metadata của việc lưu/gửi, không phải các cặp session values thường được gửi lại dưới dạng đơn giản.

### 1.2. Cookie value không tự chứng minh identity

Một cookie session thường chứa **một opaque token**, ánh xạ đến session được server xác thực và quản lý. Server phải:

- Kiểm tra token hợp lệ/chưa hết hạn/chưa bị thu hồi.
- Ánh xạ token tới user/tenant/session phù hợp.
- Kiểm tra quyền truy cập resource ở từng request.
- Bảo vệ session khỏi fixation, hijacking, replay, CSRF theo mô hình ứng dụng.
- Không dùng việc client có `Cookie: SID=...` làm bằng chứng tuyệt đối rằng client có quyền thực hiện mọi thao tác.

Cookie chỉ là phương tiện truyền trạng thái; **authentication và authorization vẫn là nghiệp vụ bảo mật của server**.

---

## 2. Kiến trúc Java: `CookieHandler` → `CookieManager` → `CookieStore/Policy`

~~~text
                    HttpClient
           (java.net.http, Java 11+)
                         │
       Builder.cookieHandler(handler)
                         │
                         ▼
                CookieHandler
                  get() / put()
                         ▲
                         │ extends
                         │
                   CookieManager
                    │        │
                    ▼        ▼
               CookieStore  CookiePolicy
                   │          │
                   ▼          ▼
               HttpCookie   ACCEPT_ORIGINAL_SERVER
               + URI          ACCEPT_NONE
               + expiry       ACCEPT_ALL
                               custom policy
~~~

### 2.1. `CookieHandler` là interface hành vi qua abstract class

~~~java
import java.net.CookieHandler;
~~~

`CookieHandler` là **abstract class**; provider cần triển khai hai methods:

~~~java
// CHỮ KÝ API MINH HỌA, không phải class độc lập.
Map<String, List<String>> get(
        URI uri,
        Map<String, List<String>> requestHeaders) throws IOException;

void put(
        URI uri,
        Map<String, List<String>> responseHeaders) throws IOException;
~~~

- **`get(uri, requestHeaders)`**: được gọi khi client muốn lấy các cookie headers áp dụng cho URI.
- **`put(uri, responseHeaders)`**: được gọi để xử lý response headers như `Set-Cookie` và cập nhật cookie store.

Một implementation cần bảo đảm các rules về scope, expiration, header handling và concurrency. Trong đa số ứng dụng, hãy dùng `CookieManager` thay vì tự xây một handler từ đầu.

### 2.2. `CookieManager` có hai phần không nên nhầm

~~~java
CookieManager manager = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
~~~

Khi `CookieStore` là `null`, `CookieManager` sử dụng **default in-memory store** của JDK. Khi `CookiePolicy` là `null`, default là `ACCEPT_ORIGINAL_SERVER`.

**CookieStore lưu những cookies đã chấp nhận. CookiePolicy quyết định có nhận cookie được trả về từ server hay không.** Policy nhận cookie không thay cho các điều kiện chọn cookie khi gửi request.

~~~java
CookieManager noCookies = new CookieManager(
        null, CookiePolicy.ACCEPT_NONE);
~~~

Trong demo, `ACCEPT_NONE` giúp quan sát rằng response vẫn đến nhưng cookie không được lưu cho các requests sau.

### 2.3. `CookiePolicy` và mức độ tin tưởng

| Policy | Ý nghĩa | Khi nào |
| --- | --- | --- |
| `ACCEPT_ORIGINAL_SERVER` | Chỉ nhận cookies từ original server theo rule JDK | Lựa chọn cơ bản, vẫn cần security policy khác |
| `ACCEPT_NONE` | Từ chối cookies | Client stateless hoặc endpoint không cần cookies |
| `ACCEPT_ALL` | Chấp nhận mọi cookie theo hook policy | Cần cân nhắc mạnh về privacy/security; không dùng mặc định |
| Custom CookiePolicy | Có thể kiểm tra URI, domain, tên, v.v. | Có contract cụ thể và test kỹ |

`ACCEPT_ORIGINAL_SERVER` **không đồng nghĩa một browser hiện đại với đầy đủ Public Suffix List, SameSite, cookie prefixes và toàn bộ RFC 6265bis rules**. JDK docs của `HttpCookie` ghi nhận chỉ hỗ trợ RFC 6265 **một phần**. Đừng coi đây là một browser cookie engine có mọi giới hạn cross-site.

### 2.4. `CookieStore` không tự là database bền vững

~~~java
CookieStore store = manager.getCookieStore();
List<HttpCookie> entries = store.getCookies();
~~~

`getCookies()` trả những cookies **chưa hết hạn**. Default store là **in-memory**, không tự lưu file, không tự đồng bộ với browser profile, không survive process restart. Nếu cần persistence phải cung cấp **custom CookieStore** với cơ chế bảo vệ/serialization/expiry/locking và chính sách dọn dẹp.

Thao tác:

~~~java
// MẢNH MINH HỌA với manager đã tạo.
CookieStore store = manager.getCookieStore();
store.getCookies();  // Đọc danh sách cookie chưa hết hạn.
store.get(URI.create("https://api.example.test/orders"));
store.removeAll();   // Xoá toàn bộ cookies trong store này.
~~~

**Không sửa trực tiếp list do `getCookies()`/`get(URI)` trả về.** JDK 26 làm rõ các danh sách từ in-memory store là immutable. Để xoá, dùng `CookieStore.remove(uri, cookie)` hoặc `removeAll()`. Ngay cả trên runtime khác, cũng nên dùng API mutation thay vì tin một list view có thể chỉnh sửa.

### 2.5. `HttpCookie` là cookie object, không phải JWT/session validator

~~~java
// MẢNH MINH HỌA.
HttpCookie cookie = new HttpCookie("SID", "opaque-token");
cookie.setPath("/api");
cookie.setSecure(true);
cookie.setHttpOnly(true);
cookie.setMaxAge(600);

String name = cookie.getName();
boolean secure = cookie.getSecure();
boolean httpOnly = cookie.isHttpOnly();
boolean expired = cookie.hasExpired();
~~~

`HttpCookie` có API cho **name, value, domain, path, secure, httpOnly, maxAge, discard, version**. Nó không tự xác minh một cookie value có hợp lệ hay token bên trong đã bị thu hồi chưa.

---

## 3. Tích hợp với `java.net.http.HttpClient` hiện đại

### 3.1. Đường đi nên dùng: cấu hình per client

~~~java
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.http.HttpClient;

CookieManager cookieManager = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookieManager)
        .build();
~~~

`HttpClient.Builder.cookieHandler(CookieHandler)` cung cấp handler cho client cụ thể. Khi client xử lý response, cookie handler có thể lưu `Set-Cookie`; khi gửi request khác, nó có thể chọn cookie phù hợp và thêm request cookie headers.

**Cần tái sử dụng HttpClient** cho các requests của cùng một service/session scope, thay vì tạo client mới mỗi request, vì HttpClient quản lý connection reuse/resources của riêng nó.

### 3.2. Có cấu hình handler hay không?

~~~java
boolean configured = client.cookieHandler().isPresent();
~~~

`HttpClient.cookieHandler()` trả `Optional<CookieHandler>`. Nếu builder **không gọi `.cookieHandler(...)`**, optional này **rỗng**. `HttpClient.newHttpClient()` đơn thuần không tự động mang CookieManager mà bạn vừa tạo ở một biến bất kỳ.

Đây là cách kiểm tra khả năng cookie state của client, **không khẳng định một cookie cụ thể đã được gửi**. Để xác minh cookie thực tế, cần test response `Set-Cookie` và request tiếp theo, hoặc kiểm tra behavior an toàn của server.

### 3.3. Không tự gắn raw Cookie header nếu muốn manager điều khiển

Một cách dễ sai:

~~~java
// MẢNH MINH HỌA PHẢN VÍ DỤ; không dùng cho session cookie bình thường.
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Cookie", "SID=hardcoded")
        .GET()
        .build();
~~~

Gắn raw header thủ công dễ làm:

- Bỏ qua domain/path/secure/expiry rules.
- Trộn session cookie của tenant A sang request của tenant B.
- Dùng token cũ sau logout.
- Gửi cookie tới redirect destination ngoài ý muốn.
- Tạo sự xung đột với CookieManager đang cấu hình.
- Log/hardcode secrets.

Nếu thật sự phải gửi cookie do protocol quy định, hãy có một chính sách rõ và kiểm thử; không xem `Cookie` như một string tùy ý có thể copy qua mọi request.

### 3.4. `HttpClient` có thể chia sẻ CookieManager

~~~java
CookieManager shared = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient clientA = HttpClient.newBuilder()
        .cookieHandler(shared).build();
HttpClient clientB = HttpClient.newBuilder()
        .cookieHandler(shared).build();
~~~

**Hai clients trên dùng cùng cookie store**. Nếu client A login, client B có thể gửi session cookie được lưu chung tới URI phù hợp. Điều này có thể được chủ động dùng cho hai HTTP clients thuộc **cùng một session/account**, nhưng là **lỗi bảo mật nghiêm trọng** nếu client A và B thuộc hai users/tenants khác nhau.

### 3.5. Cô lập session theo user/tenant

~~~java
// MẢNH MINH HỌA: mỗi tenant/identity có manager riêng.
CookieManager tenantAManager = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
CookieManager tenantBManager = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient tenantA = HttpClient.newBuilder()
        .cookieHandler(tenantAManager).build();
HttpClient tenantB = HttpClient.newBuilder()
        .cookieHandler(tenantBManager).build();
~~~

**Không đặt một CookieManager toàn cục cho nhiều users** chỉ vì muốn tiết kiệm connections. Trong backend multi-tenant, một pool/HttpClient shared có cookie manager global có thể **trộn session state**. Nếu cần stateless service-to-service auth, có thể không dùng cookies, mà dùng auth tokens có scope rõ cho từng request, theo kiến trúc.

### 3.6. `CookieHandler.setDefault()` khác `.cookieHandler(manager)`

~~~java
// MẢNH MINH HỌA của API toàn JVM:
CookieHandler.setDefault(manager);
CookieHandler current = CookieHandler.getDefault();
~~~

`setDefault()` thiết lập **CookieHandler mặc định toàn process**, được tài liệu Java gắn với các HTTP URL stream protocol handlers như `HttpURLConnection`. Đó **không phải cách được khuyên dùng để gắn cookie vào mọi `java.net.http.HttpClient`**.

Với `java.net.http.HttpClient` hãy **cấu hình tường minh bằng builder**. Không nên đổi process-wide default trong một library, test chạy song song hoặc ứng dụng nhiều tenants: có thể ảnh hưởng các thành phần khác mà bạn không biết.

---

## 4. Phạm vi gửi cookie: Domain, Path, Secure và thời gian sống

### 4.1. `Path` hạn chế những URL nào nhận cookie

Server có thể trả:

~~~http
Set-Cookie: SID=opaque-value; Path=/api; Max-Age=600; HttpOnly
~~~

Những requests đến cùng origin:

| Đường dẫn request | Cookie `Path=/api` có thể được gửi? |
| --- | --- |
| `/api/orders` | **Có** |
| `/api/profile` | **Có** |
| `/api` | **Có** |
| `/outside` | **Không** |
| `/apiother` | **Không** theo path-matching semantics mong đợi |
| `/` | **Không** |

JDK `CookieManager` sử dụng path/cookie semantics của implementation. Đối với edge cases và những yêu cầu bắt buộc tương thích browser, hãy test runtime/protocol thực tế. **Path không phải security boundary để cô lập dữ liệu giữa các endpoints của cùng origin**: cookies vẫn được gửi và server cần xác thực/authorization đúng.

### 4.2. Domain/Host và nguy cơ truyền nhầm

Khi không có `Domain`, cookie thường gắn với host đã đặt. Khi có `Domain`, behavior sẽ phụ thuộc các luật domain matching và policy. Không cho một third-party origin tự do áp Domain rồi tin nó sẽ được giới hạn theo browser policy nếu thư viện Java chưa hỗ trợ đầy đủ.

**Cookie scope không dựa vào TCP port như session isolation**. Hai services khác port nhưng cùng hostname có thể dùng chung cookie domain/path rules. Vì vậy:

~~~text
http://127.0.0.1:9001/api
http://127.0.0.1:9002/api

Không tự suy "khác port => cookie không bao giờ chia sẻ".
~~~

Nếu hai services cần tách session, dùng **separate cookie managers**, tên/path/domain có chủ đích và server-side session policy; không dựa vào port.

### 4.3. `Secure` và HTTP/HTTPS

~~~http
Set-Cookie: SID=opaque; Path=/; Secure; HttpOnly
~~~

`Secure` có nghĩa cookie nên chỉ được gửi qua một protocol an toàn như HTTPS. Với Java `HttpCookie.getSecure()` bạn có thể kiểm tra cờ này. **Đừng tạo test cookie `Secure` rồi mong nó được gửi trên HTTP loopback**. Ví dụ chính dùng plain HTTP localhost cho đơn giản nên cố ý **không đặt `Secure`**; đó là một ngoại lệ chỉ dành cho demo.

Hệ thống thật nên sử dụng HTTPS, đúng redirect/TLS policy, tránh gửi session cookie ở plain HTTP, không đặt credentials trong URLs hoặc logs.

### 4.4. `HttpOnly` không chặn code Java đọc store

`HttpOnly` là một attribute hướng tới user agents/browser: **không cho scripting engine như JavaScript truy cập cookie**. Java `HttpCookie.isHttpOnly()` cho bạn quan sát cờ, nhưng ứng dụng Java có quyền truy cập `CookieStore` vẫn có thể đọc `HttpCookie.getValue()`.

Vì vậy **không coi HttpOnly là ranh giới cô lập secrets trong JVM**. Nếu code Java trong cùng process không đáng tin, việc dùng chung CookieManager vẫn có thể lộ session. Không log/serialize cookie values hoặc đưa CookieStore vào diagnostics công khai.

### 4.5. `SameSite` là browser/cross-site policy, không mặc nhiên có trong JDK CookieManager

Trong browser, `SameSite=Strict/Lax/None` được dùng để giới hạn gửi cookies trong những ngữ cảnh cross-site. Nhưng **`java.net.HttpCookie` chỉ hỗ trợ RFC 6265 một phần**, và public API chuẩn không cung cấp một bộ kiểm tra **SameSite/browser navigation context** như browser.

`java.net.http.HttpClient` là một programmatic HTTP client, không có đầy đủ khái niệm top-level browser navigation, initiator site và browser-origin context. Vì vậy **không dựa vào Java CookieManager để thực thi SameSite/CSRF semantics tương đương Chrome/Firefox**.

Nếu Java backend có hành vi cross-origin sensitive, phải chủ động định nghĩa cookie sending policy/redirect allowlist, và **server phải dùng CSRF protection thích hợp** với browser clients. `SameSite` cũng không thay thế authn/authz.

### 4.6. `Max-Age`, `Expires` và logout

~~~http
Set-Cookie: SID=opaque; Path=/api; Max-Age=600
~~~

`Max-Age=600` cho phép cookie sống tối đa khoảng 600 giây theo clock/lifetime. `Max-Age=0` thường được dùng để xoá cookie:

~~~http
Set-Cookie: SID=; Path=/api; Max-Age=0
~~~

**Muốn xoá đúng cookie, server cần đồng bộ tên, Path và Domain scope phù hợp.** Một response logout có thể làm cookie store bỏ entry, nhưng server vẫn phải **thu hồi session/token phía backend**: client-side deletion không đủ để làm token bị đánh cắp mất hiệu lực.

**JDK 26 có sửa xử lý trường hợp cookie chứa cả `Max-Age` và `Expires`: `Max-Age` phải được ưu tiên theo RFC 6265.** Nếu cần hỗ trợ nhiều JDKs, hãy kiểm thử behavior deployed runtime và tránh dữ liệu mâu thuẫn. Demo chỉ dùng Max-Age để không phụ thuộc behavior trước/sau thay đổi.

### 4.7. Session cookie không tự được lưu qua restart

`HttpCookie.getMaxAge() < 0` thường biểu diễn cookie không có lifetime được chỉ định, mang nghĩa session cookie. Nhưng với default CookieManager in-memory, **toàn bộ store** mất khi process kết thúc, kể cả cookie có `Max-Age` dài.

Không nhầm **cookie expiry** với **persistence**:
- Expiry trả lời “cookie còn hiệu lực theo clock không?”
- Persistence trả lời “store có sống qua application restart không?”
- Server session validity trả lời “token này có còn được server chấp nhận không?”

Đây là ba câu hỏi độc lập.

---

## 5. Demo Java 17+ hoàn chỉnh: `HttpClient` và `CookieManager`

### 5.1. Kịch bản kiểm thử

Chương trình **`CookieHandlerModernClientDemo.java`**:

1. Tạo **loopback `HttpServer`** trên `127.0.0.1`, port `0` để OS chọn một port rảnh.
2. `/login` trả `Set-Cookie: SID=local-demo-123; Path=/api; Max-Age=600; HttpOnly`.
3. `/api/echo` và `/outside` kiểm tra liệu request có chứa demo cookie hay không rồi trả `cookieSeen=true/false`.
4. `/api/logout` đặt `SID=; Path=/api; Max-Age=0` để xóa cookie.
5. Tạo một `CookieManager` với **ACCEPT_ORIGINAL_SERVER** và hai `HttpClient` chia sẻ manager này.
6. Tạo `HttpClient.newHttpClient()` **không cấu hình cookieHandler**, và một client khác có manager với **ACCEPT_NONE**.
7. Gửi requests tuần tự để chứng minh cookie được lưu, giới hạn Path, chia sẻ manager có chủ đích, client không handler thì không gửi, reject policy không lưu, logout xóa session cookie.
8. In **19 dòng deterministic**; không in raw session cookie value hoặc tin một định dạng raw Cookie header cố định.
9. Đóng `HttpExchange`, dừng server, shutdown executor và xóa demo cookie stores.

**Cảnh báo an toàn:** Demo có một giá trị cookie cố định và HTTP plaintext chỉ vì chạy trên loopback trong test, không phải session ID/authentication thật. Phương thức `echoCookie` chỉ xác nhận token giả đã xuất hiện trong header, **không phải một phương thức xác thực an toàn**. Trong thực tế, server phải parse/validate cookie đúng chuẩn và xác nhận session trong trusted session store.

### 5.2. File duy nhất: `CookieHandlerModernClientDemo.java`

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.HttpCookie;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class CookieHandlerModernClientDemo {
    private static final String DEMO_COOKIE = "SID=local-demo-123";

    private static void respond(HttpExchange exchange, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        try (exchange) {
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream output = exchange.getResponseBody()) {
                output.write(bytes);
            }
        }
    }

    private static void echoCookie(HttpExchange exchange) throws IOException {
        String cookie = exchange.getRequestHeaders().getFirst("Cookie");
        // Demo assertion only, NOT a production session-authentication method.
        boolean seen = cookie != null
                && cookie.contains("SID")
                && cookie.contains("local-demo-123");
        respond(exchange, "cookieSeen=" + seen);
    }

    private static String get(HttpClient client, String base, String path)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(URI.create(base + path))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
        if (response.statusCode() != 200) {
            throw new AssertionError("Unexpected status "
                    + response.statusCode());
        }
        return response.body();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        server.setExecutor(executor);
        try {
            server.createContext("/login", exchange -> {
                exchange.getResponseHeaders().add("Set-Cookie",
                        DEMO_COOKIE + "; Path=/api; Max-Age=600; HttpOnly");
                respond(exchange, "login-ok");
            });
            server.createContext("/api/echo",
                    CookieHandlerModernClientDemo::echoCookie);
            server.createContext("/outside",
                    CookieHandlerModernClientDemo::echoCookie);
            server.createContext("/api/logout", exchange -> {
                exchange.getResponseHeaders().add("Set-Cookie",
                        "SID=; Path=/api; Max-Age=0; HttpOnly");
                respond(exchange, "logout-ok");
            });
            server.start();

            String base = "http://127.0.0.1:" + server.getAddress().getPort();
            CookieManager store = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            CookieManager rejectStore = new CookieManager(
                    null, CookiePolicy.ACCEPT_NONE);
            HttpClient client = HttpClient.newBuilder()
                    .cookieHandler(store)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpClient shared = HttpClient.newBuilder()
                    .cookieHandler(store).build();
            HttpClient noCookies = HttpClient.newHttpClient();
            HttpClient rejected = HttpClient.newBuilder()
                    .cookieHandler(rejectStore).build();

            System.out.println("configuredHandler="
                    + client.cookieHandler().isPresent());
            System.out.println("unconfiguredHandler="
                    + noCookies.cookieHandler().isPresent());
            System.out.println("beforeLogin="
                    + get(client, base, "/api/echo"));
            System.out.println("login="
                    + get(client, base, "/login"));
            List<HttpCookie> cookies = store.getCookieStore().getCookies();
            System.out.println("storedCount=" + cookies.size());
            System.out.println("storedName=" + cookies.get(0).getName());
            System.out.println("storedPath=" + cookies.get(0).getPath());
            System.out.println("storedHttpOnly=" + cookies.get(0).isHttpOnly());
            System.out.println("withinPath="
                    + get(client, base, "/api/echo"));
            System.out.println("outsidePath="
                    + get(client, base, "/outside"));
            System.out.println("sharedManager="
                    + get(shared, base, "/api/echo"));
            System.out.println("noHandler="
                    + get(noCookies, base, "/api/echo"));
            System.out.println("rejectLogin="
                    + get(rejected, base, "/login"));
            System.out.println("rejectStoreCount="
                    + rejectStore.getCookieStore().getCookies().size());
            System.out.println("rejectRequest="
                    + get(rejected, base, "/api/echo"));
            System.out.println("logout="
                    + get(client, base, "/api/logout"));
            System.out.println("afterLogoutCount="
                    + store.getCookieStore().getCookies().size());
            System.out.println("afterLogout="
                    + get(shared, base, "/api/echo"));
            System.out.println("modifiedGlobalCookieHandler=false");
            store.getCookieStore().removeAll();
            rejectStore.getCookieStore().removeAll();
        } finally {
            server.stop(0);
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

### 5.3. Biên dịch và chạy

Lưu source là **`CookieHandlerModernClientDemo.java`**. Dùng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 --release 17 --add-modules jdk.httpserver,java.net.http CookieHandlerModernClientDemo.java
java --add-modules jdk.httpserver,java.net.http CookieHandlerModernClientDemo
~~~

Cả **`jdk.httpserver`** và **`java.net.http`** là modules đi cùng JDK; không cần Maven, Gradle hoặc HTTP library bên ngoài. Các clients trong demo đều kết nối **cùng loopback server**, không truy cập internet.

Chương trình dùng đúng standard Java 17 API, nên không gọi `HttpClient.close()` trong source để giữ khả năng biên dịch trên Java 17. Với **Java 21+**, `HttpClient` hỗ trợ `AutoCloseable`, `close`, `shutdown`, `awaitTermination`; ứng dụng có thể chủ động quản lý client lifecycle trên những runtime đó. Với responses dùng streaming body subscribers, phải consume/cancel/close stream theo contract để không giữ requests/connection resources vô thời hạn.

### 5.4. Stdout chính xác đã kiểm chứng

~~~text
configuredHandler=true
unconfiguredHandler=false
beforeLogin=cookieSeen=false
login=login-ok
storedCount=1
storedName=SID
storedPath=/api
storedHttpOnly=true
withinPath=cookieSeen=true
outsidePath=cookieSeen=false
sharedManager=cookieSeen=true
noHandler=cookieSeen=false
rejectLogin=login-ok
rejectStoreCount=0
rejectRequest=cookieSeen=false
logout=logout-ok
afterLogoutCount=0
afterLogout=cookieSeen=false
modifiedGlobalCookieHandler=false
~~~

**Đã biên dịch bằng `javac --release 17` và chạy thành công trên OpenJDK 24.0.2, kiểm tra đúng 19 dòng stdout.** Port ngẫu nhiên không xuất hiện trong output. Các clients gửi requests tuần tự nên behavior deterministic trong môi trường test.

### 5.5. Ý nghĩa từng nhóm kết quả

**Trước login:**
- `configuredHandler=true`: `HttpClient.Builder.cookieHandler(...)` đã gắn một CookieManager.
- `unconfiguredHandler=false`: client được tạo bằng `newHttpClient()` chưa có handler.
- `beforeLogin=cookieSeen=false`: manager còn trống, không có SID gửi lên.

**Sau login:**
- `storedCount=1`: CookieManager nhận `Set-Cookie` theo policy.
- `storedName=SID` và `storedPath=/api`: cookie được parse thành HttpCookie và giữ scope path.
- `storedHttpOnly=true`: flag được lưu trong metadata của HttpCookie.

**Gửi lại requests:**
- `withinPath=cookieSeen=true`: URL `/api/echo` nhận cookie.
- `outsidePath=cookieSeen=false`: URL `/outside` không nhận cookie do Path không match.
- `sharedManager=cookieSeen=true`: một HttpClient khác dùng **cùng manager** chia sẻ cookie.
- `noHandler=cookieSeen=false`: client không được cấu hình CookieHandler không tự lấy session của client kia.

**Chính sách và logout:**
- `rejectStoreCount=0` và `rejectRequest=cookieSeen=false`: `ACCEPT_NONE` từ chối cookie nên không gửi khi gọi API.
- `afterLogoutCount=0`: Set-Cookie Max-Age=0 xóa cookie tương ứng.
- `afterLogout=cookieSeen=false`: shared client cũng không còn gửi session đó.
- `modifiedGlobalCookieHandler=false`: chương trình chỉ dùng per-client builder; không gọi CookieHandler.setDefault.

### 5.6. Vì sao không in raw Cookie header?

Trong một lượt thử ban đầu trên OpenJDK 24.0.2, JDK có thể serialize versioned-cookie header với các thành phần kiểu:

~~~text
$Version="1"; SID="local-demo-123";$Path="/api";$Domain="127.0.0.1"
~~~

Một triển khai/phiên bản khác có thể cho biểu diễn khác. Vì vậy demo in `cookieSeen=true/false` thay vì đòi chuỗi raw đúng bằng `SID=local-demo-123`.

**Quan trọng:** Server production vẫn phải parse cookie đúng spec, không dùng `contains("SID")` như phương pháp xác thực. Hàm echoCookie chỉ có mục đích quan sát có gửi cookie giả; nó không phải ví dụ về session token parsing/validation an toàn.

---

## 6. `CookieHandler` callbacks và vòng đời request

### 6.1. Cơ chế đi-về

~~~text
Ứng dụng tạo HttpRequest cho URI
          │
          ▼
HttpClient gọi CookieHandler.get(uri, requestHeaders)
          │
          ▼
CookieManager hỏi CookieStore / scope / expiry
          │
          ▼
Request đi qua network (có thể mang Cookie)
          │
          ▼
Server trả response (có thể có Set-Cookie)
          │
          ▼
HttpClient gọi CookieHandler.put(uri, responseHeaders)
          │
          ▼
CookieManager áp CookiePolicy rồi lưu trong CookieStore
          │
          ▼
Request tiếp theo có thể dùng state mới
~~~

Đây là sơ đồ logic; thời điểm callback và concurrency có thể khác khi client dùng `sendAsync`, redirects hoặc nhiều requests cùng lúc. Do đó custom CookieHandler/CookieStore cần **thread-safety**, không được giả định mọi callbacks chạy trên một thread duy nhất.

### 6.2. `get()` phải tôn trọng request URI và header context

`CookieHandler.get(URI, headers)` nhận URI và request headers, trả **immutable map** cookie-related headers như Cookie/Cookie2. Kết quả không nên rò cookie của host/path khác. Nếu tự implement get, cần:

- Xử lý scheme `http`/`https` đúng.
- Domain/host/path matching theo contract.
- Expires/Max-Age và Secure.
- Không tự gửi secret tới một URI không được phép.
- Trả cấu trúc headers hợp lệ, không injection CRLF.
- Cô lập sessions/tenants.
- Tránh side effects không cần thiết khi nhiều requests đồng thời.

Nếu không thật sự cần custom behavior, dùng CookieManager đã được kiểm thử thay vì tự viết toàn bộ cookie parser.

### 6.3. `put()` xử lý response từ server

`CookieHandler.put(URI, responseHeaders)` được gọi với headers của response. CookieManager parse Set-Cookie, kiểm tra CookiePolicy và thêm những cookies phù hợp vào store. **Không mặc định mọi Set-Cookie đều được chấp nhận.**

Cần chú ý nhiều `Set-Cookie` headers, attribute casing, nhiều cookies trùng tên nhưng khác Domain/Path và việc xoá bằng Max-Age=0. Khi logout, không chỉ xóa client state mà còn thu hồi session server-side.

### 6.4. Thread safety và request ordering

Nếu hai requests đồng thời:

~~~text
Request A: /login → Set-Cookie: SID=tokenA
Request B: /login → Set-Cookie: SID=tokenB
~~~

Cùng CookieManager/cùng cookie name/scope, trạng thái cuối cùng có thể phụ thuộc response callback ordering. **Đừng dùng một shared cookie store cho nhiều phiên đăng nhập độc lập** rồi mong library tự phân biệt user.

Nếu một user đăng xuất trong khi request khác đã gửi cookie cũ, cần thiết kế **server-side token revocation** và request consistency; việc xóa client cookie store không thu hồi bytes đã rời khỏi client.

---

## 7. Lưu trữ, dọn dẹp và session lifecycle

### 7.1. `getCookies`, `get(URI)`, `remove`, `removeAll`

~~~java
// MẢNH MINH HỌA với CookieManager manager.
CookieStore store = manager.getCookieStore();
List<HttpCookie> cookies = store.getCookies();

for (HttpCookie cookie : cookies) {
    System.out.println(cookie.getName()); // Không in value.
}

store.removeAll(); // Xóa toàn bộ state thuộc manager này.
~~~

Nếu chỉ logout một user, đừng gọi `removeAll` trên manager mà nhiều users đang chia sẻ (đúng ra không nên chia sẻ như vậy). Nếu chỉ muốn xóa một cookie cụ thể:

~~~java
// MẢNH MINH HỌA: uri được định nghĩa và cookie đã tìm thấy.
boolean removed = store.remove(uri, cookie);
~~~

Việc `remove` yêu cầu URI/cookie phù hợp theo `CookieStore` implementation. Tốt nhất ứng dụng tự biết **owner và scope** của store, rồi xóa đúng session jar.

### 7.2. Max-Age không bảo đảm server session còn hiệu lực

Một cookie có `Max-Age=600` có thể:

- Bị server revoke sau 20 giây.
- Hết hiệu lực do user đổi password.
- Bị mất vì process restart.
- Còn trong CookieStore nhưng server trả 401.
- Bị thay thế do login khác.
- Được gửi qua một request đã bắt đầu trước logout.

Vì vậy không dùng `HttpCookie.hasExpired() == false` làm bằng chứng session đã authenticated/authorized. Server quyết định token validity.

### 7.3. Persistence cần encryption và lifecycle

Custom persistent CookieStore có thể gây lộ session token nếu ghi plaintext file. Nếu cần persistence:

- Có lý do nghiệp vụ cụ thể.
- Mã hóa secrets at rest và giới hạn filesystem permissions.
- Tách cookie jars theo tenant/user/profile.
- Không đồng bộ bừa bãi cookies sang các machines.
- Tôn trọng expiry, session-only semantics và logout.
- Ghi audit mà không log raw tokens.
- Áp size/count quotas, eviction và chống unbounded growth.
- Thiết kế thread safety, atomic writes và recovery khi crash.
- Có quy trình rotation/revocation.

Default JDK in-memory store không giải quyết những yêu cầu persistent cookie jar nâng cao này.

### 7.4. Resource lifecycle của HttpClient

`CookieManager` mặc định không có hàm close, vì in-memory CookieStore là state giữ trong JVM và được GC khi không còn tham chiếu. Nếu custom CookieStore mở file/database, phải quản lý resource riêng trong application lifecycle.

`HttpClient` ở Java 17 chưa expose `close()`/`shutdown()` như Java 21+, nên code Java 17 thường tái sử dụng client và đảm bảo response bodies được consume/cancel phù hợp. Trên Java 21+ có thể dùng try-with-resources cho clients có scope rõ:

~~~java
// MẢNH MINH HỌA CHỈ BIÊN DỊCH TRÊN JAVA 21+:
try (HttpClient client = HttpClient.newBuilder()
        .cookieHandler(manager)
        .build()) {
    // send requests và consume response bodies.
}
~~~

Không đặt đoạn Java 21+ này vào file demo được biên dịch `--release 17`. Khi dùng BodyHandlers.ofInputStream/ofPublisher, việc giữ body chưa tiêu thụ có thể làm client shutdown/connection release bị treo hoặc chậm. Demo chính dùng BodyHandlers.ofString để consume đầy đủ body.

---

## 8. Bảo mật: cookies không phải một chiếc hộp đen an toàn

### 8.1. Không trộn session giữa tenants

**Anti-pattern:** `static CookieManager GLOBAL = new CookieManager()` rồi cấu hình cho mọi requests của nhiều users. Mọi user có thể có cookie name `SID` cùng domain/path, dẫn đến session overwrite/hijacking hoặc gửi sai cookie.

**Thiết kế thay thế:** một cookie jar per session/account/tenant, hoặc không dùng cookie nếu giao thức service-to-service của bạn dùng tokens per request. Luôn có rõ **lifecycle login → requests → logout → destroy state**.

### 8.2. `CookiePolicy.ACCEPT_ORIGINAL_SERVER` chỉ là một lớp

Không dùng `ACCEPT_ALL` chỉ vì “server trả gì thì lưu nấy”. Nhưng ngay cả `ACCEPT_ORIGINAL_SERVER` cũng không có đầy đủ browser security checks. Nếu client gửi requests tới arbitrary URLs:

- Validate/allowlist target hostnames và schemes.
- Chặn SSRF tới local/private/link-local/metadata endpoints theo threat model.
- Giới hạn redirects và kiểm tra đích chuyển hướng.
- Không chia sẻ manager giữa các origins không liên quan.
- Dùng HTTPS cho session cookies.
- Thực hiện login/logout và token rotation đúng policy.

**Domain/Path/Max-Age** là cookie protocol scope, không thay thế network allowlist hoặc identity isolation.

### 8.3. `SameSite` không tự biến Java client thành browser

Một số servers dựa vào browser SameSite để giảm CSRF. Nhưng HttpClient Java là một non-browser client: nó không tự mang đủ browser origin/site context. Nếu Java client nhận và gửi cookie tới một destination khác ngữ cảnh browser, **đừng suy rằng browser cookie restrictions tự động bảo vệ request đó**.

Ở phía server, nếu dùng cookie-based auth trong browser applications, cần CSRF defenses phù hợp (tokens, Origin/Referer validation theo chính sách, Fetch Metadata headers khi phù hợp, SameSite cookie settings và kiểm thử browser). Ở phía Java client, route allowlist và per-session state ownership là các biện pháp trọng yếu.

### 8.4. `HttpOnly` không cấm Java code đọc cookie value

Cookie trong `CookieStore` là dữ liệu trong process. Bất cứ component có reference tới manager/store đều có thể gọi `HttpCookie.getValue()`; HttpOnly chỉ diễn đạt một browser scripting policy. Không expose manager như một singleton công khai cho modules/tenants khác.

### 8.5. `Secure` không thay cho TLS verification

Cookie Secure yêu cầu kênh secure khi gửi, nhưng **vẫn phải xác thực certificate và hostname** của HTTPS server theo policy. Không tắt hostname verification/trust validation để “sửa lỗi kết nối” rồi tin rằng Secure cookie vẫn bảo vệ token.

### 8.6. Không log cookies

Vì cookie session có thể là bearer credential, tránh:

~~~text
DEBUG raw request headers: Cookie: SID=...
DEBUG raw response headers: Set-Cookie: SID=...
DEBUG CookieStore.getCookies() value=...
~~~

Ưu tiên log metadata không nhạy cảm, ví dụ cookie name/scope hoặc number of accepted cookies, theo privacy policy. Khi cần audit auth, dùng session ID hash/correlation ID đã thiết kế, không log nguyên token.

### 8.7. Token rotation, session fixation và logout

Sau login hoặc privilege elevation, server nên tạo/rotate session token và vô hiệu hóa token cũ theo chính sách. Khi logout, client xóa cookie nhưng server phải revoke session. Trong multi-device sessions, server phải có cơ chế quản lý các phiên đang hoạt động.

Nếu HTTP client chỉ biết `CookieStore.removeAll()` mà server không revoke session, token bị đánh cắp vẫn có thể tái sử dụng trong khoảng thời gian còn hiệu lực.

---

## 9. Kiểm thử `CookieHandler` và hành vi đa runtime

### 9.1. Test theo chức năng

| Trường hợp | Cách kiểm tra |
| --- | --- |
| Client không gắn handler | `.cookieHandler().isEmpty()` |
| CookieManager mới chưa có cookie | Request đầu tiên không gửi SID |
| Nhận Set-Cookie theo policy | `CookieStore.getCookies()` tăng đúng số |
| Cookie name/path | `HttpCookie.getName/getPath` đúng |
| Cookie HttpOnly | `HttpCookie.isHttpOnly()` phản ánh flag |
| Request trong Path | Server thấy session cookie |
| Request ngoài Path | Server không thấy cookie |
| Hai clients cùng manager | Có cùng state khi URI phù hợp |
| Clients khác manager | Không chia sẻ state |
| Policy ACCEPT_NONE | Không lưu Set-Cookie |
| Cookie Max-Age=0 | Xóa đúng cookie scope |
| Session revoked server-side | Server từ chối token cũ |
| Secure cookie trên HTTP | Cookie không được gửi theo secure policy |
| Secure cookie trên HTTPS | Truyền khi TLS/cert được xác minh |
| Domain và subdomains | Kiểm tra policy, không gửi sai hosts |
| Host giống nhưng khác port | Không giả định cookie isolation chỉ vì port |
| Redirect sang origin khác | Không gửi session ngoài scope/allowlist |
| Cùng tên khác Path | Gửi đúng theo path rules |
| Cookie expired | `hasExpired()`/store behavior phù hợp |
| Multiple Set-Cookie | Lưu các cookies được phép |
| Cookie malformed | Không phá client, fail theo policy |
| Concurrency login/logout | Không trộn cookies giữa users |
| Unicode/UTF-8 body | Response body được decode đúng |
| Java 17/21/26 | API compatible, behavior đổi phải test |
| Store cleanup | `removeAll()` và logout thu hồi state |
| HttpClient streaming body | Consume/cancel/close đúng lifecycle |

### 9.2. Đừng hardcode raw Cookie header

Test chỉ cần kiểm tra **behavior**: cookie đã/không được gửi cho URI phù hợp. Nguyên văn header có thể phụ thuộc `HttpCookie` version và provider, có thể có quotes, path/domain fragments. Nếu bắt buộc kiểm tra HTTP wire compatibility với đối tác, dùng integration test đúng phiên bản JDK và một server parser chuẩn, **không dùng string comparison đơn giản làm auth**.

### 9.3. Test những khác biệt JDK hiện hành

JDK 26 có thay đổi đáng chú ý liên quan cookies: xử lý **Max-Age ưu tiên Expires** khi cả hai attribute xuất hiện, và một số method `CookieStore` in-memory trả **immutable lists** theo API contract. Không nên dựa vào việc một JDK cũ vô tình trả mutable list hoặc giải quyết xung đột Max-Age/Expires khác.

Điều này là ví dụ về lý do cần:

- Tập trung vào API contract hiện hành.
- Kiểm thử trên runtime production.
- Không điều khiển store bằng cách chỉnh sửa trực tiếp returned list.
- Không phát Set-Cookie mâu thuẫn.
- Có integration tests với expired cookies/redirects/secure flags.

### 9.4. Concurrency tests

Gửi các requests song song tới cùng manager, kiểm tra:

- Không crash/race trong store implementation.
- Cùng một cookie scope thay thế đúng theo policy.
- Không rò credentials giữa users/tenants.
- Callback get/put của custom store thread-safe.
- Không tạo CookieManager mới cho mỗi request nếu cần session reuse.
- CookieStore clear/remove đúng trong logout giữa requests.
- Server-side session revocation có hiệu lực.

Nếu cần stress test, dùng dữ liệu giả và server loopback; không gửi session tokens production vào test logs.

---

## 10. Lỗi phổ biến và hướng khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Login 200 nhưng request sau không mang cookie | Không `.cookieHandler(manager)` | Gắn manager vào HttpClient.Builder |
| `.cookieHandler().isEmpty()` | Builder không cấu hình handler | Tạo client có CookieHandler |
| Store rỗng sau Set-Cookie | CookiePolicy từ chối, header không hợp lệ | Kiểm tra policy, path/domain, Set-Cookie |
| Cookie được lưu nhưng không gửi `/outside` | Path=/api | Đây có thể là behavior đúng |
| Cookie Secure không gửi trên HTTP | Chỉ gửi kênh secure | Test qua HTTPS đúng policy |
| Two clients dùng chung session bất ngờ | Cùng CookieManager | Tách manager theo user/tenant |
| Không chia sẻ session dù cùng user | Dùng hai managers khác nhau | Chia sẻ một manager có chủ đích |
| Đổi CookieHandler.setDefault không ảnh hưởng HttpClient | HttpClient có per-client builder config | Dùng `.cookieHandler(...)` |
| Logout nhưng session vẫn được chấp nhận | Server chưa revoke token | Revoke server-side, không chỉ xóa cookie |
| Raw Cookie header không đúng chuỗi mong đợi | Version/quoting/serialization differences | Kiểm tra semantics, parser chuẩn |
| SameSite không cản Java HTTP client | Java không phải browser engine | Server CSRF policy + explicit client allowlist |
| `HttpOnly` nhưng Java vẫn đọc value | HttpOnly chỉ hạn chế browser script | Không chia sẻ store/không log tokens |
| CookieStore không persist qua restart | Default store là in-memory | Custom persistent store nếu thật sự cần |
| Cookie còn trong store nhưng server 401 | Token expired/revoked server-side | Login lại/token renewal theo contract |
| `Max-Age` khác `Expires` | Attribute conflict/runtime version | Tránh conflict, kiểm thử JDK |
| `getCookies()` list không sửa được | JDK trả immutable list | `CookieStore.remove/removeAll` |
| Performance giảm khi tạo mới client mỗi request | Không reuse connections/session | Reuse HttpClient theo scope |
| Memory tăng theo cookies | Không giới hạn cookie count/size | Quota, eviction, cleanup |
| Cookie bị gửi sai host/redirect | Redirect/policy/destination unsafe | Origin/host allowlist, TLS, per-tenant store |
| Cookie plaintext trong log | Logging raw headers/store | Redact và mã hóa logs khi cần |
| Client shutdown treo trên JDK 21+ | Streaming body chưa consume/close | Close/cancel response body, lifecycle tests |
| Bị 403 dù cookie hợp lệ | Cookie khác authorization | Kiểm tra permissions/resource policy |

---

## 11. Checklist production

- [ ] Client thực sự cần cookies hay có thể dùng stateless authentication.
- [ ] Dùng `HttpClient.newBuilder().cookieHandler(manager)` thay vì dựa vào global default.
- [ ] Tái sử dụng HttpClient đúng lifecycle, không tạo mới mỗi request không cần thiết.
- [ ] Cấu hình CookieManager với CookiePolicy phù hợp; không dùng ACCEPT_ALL một cách vô thức.
- [ ] Default in-memory CookieStore phù hợp với session scope hoặc custom store được bảo vệ.
- [ ] Có owner rõ cho mỗi CookieManager/session.
- [ ] Không share cookie jar giữa users/tenants độc lập.
- [ ] Có login/logout và server-side token revocation/rotation policy.
- [ ] Có rules cho cookie Domain, Path, Secure, HttpOnly, Max-Age, Expires.
- [ ] Không coi Path hay port là session security boundary.
- [ ] HTTPS/TLS verification chính xác trước khi gửi credential cookies.
- [ ] Không nhầm HttpOnly của browser với Java memory isolation.
- [ ] Không dựa vào Java CookieManager để tự thực thi SameSite/browser CSRF policy.
- [ ] Có redirect/origin allowlists, tránh SSRF và cookie leakage.
- [ ] Không log Cookie/Set-Cookie header values hoặc HttpCookie.getValue.
- [ ] Có response timeouts và resource closure cho body subscribers.
- [ ] Custom CookieStore/Policy thread-safe nếu dùng với concurrent HttpClient.
- [ ] Không sửa list getCookies/get trực tiếp; dùng remove/removeAll.
- [ ] Có expiry/quota/eviction và cleanup policy.
- [ ] Không tin CookieStore cookie còn hạn là server session hợp lệ.
- [ ] Test multiple Set-Cookie, same-name different Path, invalid headers.
- [ ] Test Secure over HTTPS và không gửi trên HTTP.
- [ ] Test behavior path/domain, host khác, redirect, concurrent login/logout.
- [ ] Test isolation giữa users/tenants, cả khi một client shared pool.
- [ ] Test JDK runtime thực tế vì RFC 6265 support của HttpCookie chỉ một phần.
- [ ] Tránh `setDefault()` process-wide trong libraries và multi-tenant server.
- [ ] Dùng Java APIs còn được duy trì trong các JDK hỗ trợ hiện hành.

## 12. Bài tập tự luyện

1. Chạy demo, giải thích sự khác nhau giữa `configuredHandler=true` và `unconfiguredHandler=false`.
2. Thêm một cookie `LANG=vi; Path=/`, kiểm tra requests trong và ngoài `/api`.
3. Đổi Path từ `/api` thành `/api/profile`, quan sát scope của `/api/echo`.
4. Tạo một `CookieManager` thứ ba để mô phỏng tenant B; chứng minh không nhận SID của tenant A.
5. Dùng chung CookieManager cho hai HttpClients và chứng minh session state chia sẻ.
6. Thử `CookiePolicy.ACCEPT_NONE`, xác nhận server login vẫn trả 200.
7. Đổi `Max-Age=600` thành `Max-Age=0`, quan sát cookie bị xoá ngay.
8. Thêm cookie `Secure`, kiểm tra không gửi trên HTTP loopback; thiết kế test HTTPS riêng.
9. Thêm `HttpOnly` và xem Java vẫn có thể đọc metadata/value trong CookieStore — phân tích security implication.
10. Kiểm tra behavior khi login lại tạo SID mới cùng Path/Domain.
11. Thêm Set-Cookie có `Expires` nhưng không có Max-Age; chạy trên JDK được sử dụng.
12. Thử Set-Cookie có cả `Max-Age` và `Expires`, so sánh JDK17/26 trên sandbox.
13. In raw Cookie header ở test nội bộ bằng token giả để quan sát versioned formatting, không dùng làm auth.
14. Tạo custom CookiePolicy chỉ nhận cookie name SID từ một origin allowlist.
15. Cài custom CookieStore có giới hạn số cookies/bytes và test thread-safety.
16. Kiểm tra `CookieStore.removeAll()` chỉ ảnh hưởng manager tương ứng.
17. Thử setDefault toàn JVM trong một test cô lập; giải thích tại sao không nên dùng trong library.
18. Thử `HttpURLConnection` với CookieHandler mặc định và so sánh cách cấu hình với HttpClient.
19. Thêm HttpClient redirects, kiểm tra cookie không bị gửi sai sang origin ngoài allowlist.
20. Tạo server-side session validation giả và chứng minh clear client cookie không revoke stolen token.
21. Sử dụng BodyHandlers.ofInputStream và test phải close stream trước khi kết thúc client.
22. Thêm một endpoint dùng OAuth bearer auth thay cookies và so sánh threat model.
23. Thiết kế bộ test session fixation/replay/cross-tenant cookie leakage.
24. Thử requests song song trên shared CookieManager, phân tích response ordering.
25. Soạn một báo cáo compatibility của Java CookieManager với browser SameSite expectations.

## Kết luận

**`CookieHandler`** là lớp trừu tượng để HTTP stack hỏi **cookie nào được gửi** và **cookie nào nên lưu**. **`CookieManager`** hiện thực cơ chế này bằng **CookieStore** cùng **CookiePolicy**. Với **`java.net.http.HttpClient` hiện đại**, cách cấu hình rõ ràng là **`.cookieHandler(cookieManager)` trên builder của mỗi client**, không phải thay đổi process-wide CookieHandler rồi kỳ vọng mọi client sẽ dùng.

Những cookies được lưu và gửi theo scope như Domain/Path/Secure/expiry, nhưng **cookie scope không thay thế authentication, authorization hay session isolation**. Khi hai clients dùng cùng manager, chúng có thể chia sẻ session; khi khác user/tenant, cần tách cookie jars. `HttpOnly` là hạn chế của browser scripting, không giấu token khỏi Java code; `SameSite` của browser không được Java CookieManager tự mô phỏng hoàn toàn. Default store lưu trong memory, không có persistence qua restart.

Ví dụ Java 17+ đã chứng minh việc nhận, lưu, gửi đúng Path, chia sẻ có chủ đích, từ chối và xoá cookie bằng 19 dòng output đã kiểm chứng. Trong production, hãy bổ sung HTTPS, origin/redirect allowlist, session revocation, tránh logging credentials, kiểm thử đa JDK và quản lý tài nguyên HttpClient đúng.

**Tài liệu tham khảo hiện hành:**

- [CookieHandler — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieHandler.html)
- [CookieManager — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieManager.html)
- [CookieStore — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieStore.html)
- [HttpCookie — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/HttpCookie.html)
- [CookiePolicy — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookiePolicy.html)
- [HttpClient.Builder — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [HttpClient — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpClient — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpServer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [Oracle JDK 26 Release Notes — HttpCookie and CookieStore updates](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265)