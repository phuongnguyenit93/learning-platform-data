# Phạm vi phiên và tránh chia sẻ cookie sai người dùng trong Java

HTTP là một giao thức mà mỗi request tự nó không mang lịch sử những request trước đó. Để duy trì đăng nhập hoặc một luồng làm việc, server thường cấp **session token** qua header `Set-Cookie`, còn client gửi lại token trong header `Cookie` ở những request kế tiếp. Trong Java, có thể xử lý cookie với `java.net.CookieManager`, `CookieStore`, `CookiePolicy`, `CookieHandler`, và gắn một cookie manager vào `java.net.http.HttpClient` bằng `HttpClient.Builder.cookieHandler(...)`.

**Sai lầm gây hậu quả nghiêm trọng:** nếu một service Java phục vụ nhiều người dùng mà dùng chung **một `CookieManager` hoặc một `CookieStore`** cho tất cả, các HTTP requests tới cùng origin/path có thể mang **cookie đăng nhập của người khác**. Đây là lỗi **chia sẻ trạng thái phiên giữa các danh tính**, không được giải quyết bằng `CookiePolicy.ACCEPT_ORIGINAL_SERVER`, `HttpOnly`, `SameSite`, hay việc cùng chạy trên HTTPS. Chúng áp những quy tắc khác, **không tạo ranh giới người dùng**.

Bài này thuộc nhóm **Cookie và mạng**, tập trung cụ thể vào **phạm vi phiên và tránh chia sẻ cookie sai người dùng**. Nội dung chỉ dùng các nguyên tắc và API còn áp dụng trên **Java 17+ và Java SE 26**: client-side cookie jars, HTTP cookie scope, server-side session binding, logout/revocation, session fixation, multi-user/multi-tenant isolation và bảo mật trình duyệt. Các điểm liên quan RFC 6265bis được ghi rõ là **bản dự thảo HTTPWG hiện hành**, không đánh đồng draft với một RFC đã phát hành.

Có hai chương trình hoàn chỉnh Java 17+ đã biên dịch bằng `javac --release 17` và chạy trên **JDK 24**: `CookieSessionIsolationDemo.java` (18/18 kiểm tra), và `CookieScopeRulesDemo.java` (12/12 kiểm tra). Chúng không kết nối Internet: bài thứ nhất dùng server **loopback** trong cùng tiến trình, bài thứ hai gọi trực tiếp `CookieManager.put/get` với URIs giả và không mở socket.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài, bạn sẽ:

1. Phân biệt cookie, cookie jar, session token, session record và business principal.
2. Hiểu `CookieManager` kết hợp `CookieStore` và `CookiePolicy` ra sao.
3. Biết `HttpClient.Builder.cookieHandler` gắn cookie state **cho client cụ thể**, thay vì dùng `CookieHandler.setDefault` toàn JVM.
4. Giải thích vì sao hai `HttpClient` **vẫn có thể dùng chung cookie** nếu cùng được gắn **một CookieManager**.
5. Thiết kế **mỗi người dùng/logical session một cookie jar riêng** trong ứng dụng đa user.
6. Phân biệt browser cookie rules với Java HTTP client, nhất là `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite` và cookie prefixes.
7. Hiểu host-only cookie, rộng phạm vi qua `Domain`, path matching và vì sao **port không tạo cookie security boundary**.
8. Thiết kế server-side mapping token → **user, tenant, expiration, revoked state**, thay vì coi giá trị cookie là danh tính tự xác thực.
9. Đổi session ID khi đăng nhập/nâng quyền, tránh session fixation và chấm dứt phiên khi logout.
10. Biết cookie expiration trong client không thay thế server-side idle/absolute timeout hoặc token revocation.
11. Tránh lộ session qua logs, HTTP response caches, redirects, proxy, subdomains hoặc đồng thời nhiều tasks.
12. Kiểm chứng isolation bằng 18 integration checks và 12 scope checks chạy trên Java 17+.

## 2. Ba ranh giới khác nhau phải tách bạch

Một phiên có tối thiểu ba phạm vi:

| Ranh giới | Câu hỏi cần trả lời | Cơ chế liên quan | Không tự bảo vệ được |
| --- | --- | --- | --- |
| **HTTP cookie scope** | Cookie này được **gửi tới host/path/scheme nào**? | `Domain`, `Path`, `Secure`, expiry và browser policies. | Ai là người dùng hợp lệ của request. |
| **Client cookie jar scope** | Cookie của các requests **nằm trong object/store nào**? | `CookieManager`, `CookieStore`, `HttpClient.cookieHandler`, browser profile. | Tránh lẫn user nếu bạn chủ động dùng chung jar. |
| **Server session principal scope** | Token này đại diện **user/tenant/session nào**, còn hợp lệ không? | Session registry, token lookup, authentication, authorization, timeout/revocation. | Không thể thay bằng so khớp URL/domain/path. |

Một request có thể thỏa cookie Domain/Path/Secure nhưng **vẫn mang cookie của người dùng khác** vì client đã chọn nhầm jar. Một token cũng có thể được gửi tới đúng host nhưng đã hết hạn hoặc bị server thu hồi. Ngược lại, cookie jar tách biệt nhưng server xác thực tenant sai vẫn có thể gây lộ dữ liệu.

```text
Java multi-user application
  |
  +-- logical user Alice
  |     +-- CookieManager A / CookieStore A
  |     +-- HttpClient A -> Cookie: sid=token-A
  |
  +-- logical user Bob
        +-- CookieManager B / CookieStore B
        +-- HttpClient B -> Cookie: sid=token-B

                 HTTPS service
                       |
              validate opaque token
                       |
               server session store
                 token-A -> Alice/tenant-X
                 token-B -> Bob/tenant-Y
                       |
             authorize resource per user/tenant
```

Nguyên tắc: **cookie scope định tuyến credential; cookie jar giữ credential; server kiểm tra credential và quyền**. Cả ba phải đúng.

## 3. Cookie không đồng nghĩa session

Một cookie là một cặp tên–giá trị cùng attributes do server gửi đến user agent:

```http
HTTP/1.1 200 OK
Set-Cookie: sid=RANDOM_TOKEN; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
```

Đây là **sơ đồ header**, `RANDOM_TOKEN` là ký hiệu cho token khó đoán do server sinh, **không phải credential thực**. Một request kế tiếp có thể gửi:

```http
GET /account HTTP/1.1
Host: app.example.test
Cookie: sid=RANDOM_TOKEN
```

`Cookie` request header chỉ gửi cặp **name=value**; không lặp lại attributes `Secure/HttpOnly/Path`. Những attributes do user agent dùng khi **lưu/gửi** cookie, không phải “bằng chứng an toàn” do client phải gửi kèm trên mỗi request.

Server phải đọc token, tìm session record trong hệ thống tin cậy, kiểm tra tuổi phiên, trạng thái thu hồi, tenant, principal và authorization; không thể chỉ kiểm tra có header `Cookie`.

### 3.1. Session token là bearer credential

Ai có được một session token hợp lệ có thể thử gửi nó thay cho chủ sở hữu. Vì vậy:

- Server sinh token ngẫu nhiên bằng **CSPRNG**, không dùng `Math.random()`, timestamp, email, IP hoặc ID tăng dần.
- Token nên có **ít nhất 128 bit entropy** theo khuyến nghị thực tế; trong demo dùng 24 bytes từ `SecureRandom` (192 bit) rồi Base64URL không padding.
- Token nên **opaque**, không chứa tên, email, role, tenant hoặc dữ liệu nhạy cảm dưới dạng có thể đọc được.
- Không đặt token trong URL/query/path, bởi browser history, logs, referrer và caches có thể làm rò rỉ.
- Dùng HTTPS cho toàn bộ authenticated session, không chỉ trang login.
- Server thực thi idle timeout, absolute timeout, logout/revocation và rotation khi auth/privilege thay đổi.
- Không ghi raw token vào logs, metrics, traces hoặc exception messages.

**Cookie attribute không biến một bearer token bị đánh cắp thành an toàn.** Chống XSS, CSRF, network interception, unsafe logging và server-side authorization vẫn cần thiết.

### 3.2. Cookie persistence khác session validity

`Max-Age` hoặc `Expires` điều khiển user agent **giữ cookie bao lâu**. Nếu không có, cookie thường được xem là session cookie theo quy tắc user agent; một số browsers có session restore nên nó có thể tồn tại qua thao tác đóng/mở browser. Điều này **không** thay thế server-side validity.

Một token đã bị server thu hồi phải vô hiệu **ngay cả khi bản sao cũ vẫn còn** và attacker gửi trực tiếp bằng custom HTTP client. Ngược lại, khi browser xóa cookie nhưng server không revoke session token thì bản sao đã bị lấy cắp vẫn có thể dùng được.

## 4. CookieManager, CookieStore và CookiePolicy trong Java

`CookieManager` là concrete implementation của `CookieHandler`. Theo Oracle Java SE 26:

- `CookieManager` quyết định chấp nhận/reject cookies thông qua một `CookiePolicy`.
- Cookies được nhận được lưu trong `CookieStore`.
- Khi tạo `new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER)`, Java dùng **in-memory CookieStore** do JDK cung cấp.
- Mặc định constructor `new CookieManager()` dùng policy `ACCEPT_ORIGINAL_SERVER`.
- `CookieStore` cung cấp `get(URI)`, `getCookies()`, `getURIs()`, `remove(...)` và `removeAll()`.
- `CookiePolicy` có `ACCEPT_ALL`, `ACCEPT_NONE`, `ACCEPT_ORIGINAL_SERVER` hoặc policy riêng do ứng dụng triển khai.

Ví dụ:

```java
CookieManager jar =
        new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
HttpClient client = HttpClient.newBuilder()
        .cookieHandler(jar)
        .build();
```

Đây là mảnh code cần các imports và không tạo một HTTP request. Quan trọng: **CookieManager gắn với object `client` trên**, không tự sinh thêm user identity.

### 4.1. CookiePolicy kiểm soát nhận cookie, không kiểm soát user

| Policy | Vai trò | Điều không bảo đảm |
| --- | --- | --- |
| `ACCEPT_ALL` | Chấp nhận cookies theo logic JDK policy. | Không nên dùng mặc định cho client nhận HTTP từ nguồn không tin cậy. |
| `ACCEPT_NONE` | Không chấp nhận cookies được response gửi đến. | Không phải server logout/revoke. |
| `ACCEPT_ORIGINAL_SERVER` | Chấp nhận cookies thuộc phạm vi original server theo Java implementation. | Không phân biệt Alice/Bob nếu cùng URL. |
| Custom `CookiePolicy` | Áp acceptance rules đặc thù. | Không thay thế cookie jar isolation hoặc business authorization. |

Nếu Alice và Bob truy cập **cùng `https://api.example.test`**, cả hai cookie session đều có cùng host/path. `ACCEPT_ORIGINAL_SERVER` có thể chấp nhận **cả hai**, vì nó **không nhận biết user**. Nếu cùng một store và cùng tên cookie, lần đặt gần nhất có thể ghi đè cookie trước: đây là một cách cụ thể làm lẫn phiên.

### 4.2. CookieStore là nơi giữ credential

`CookieStore.getCookies()` có thể trả về các `HttpCookie` chứa session token values. Dù danh sách trả về không cho chỉnh sửa theo một số phương thức, nội dung vẫn **nhạy cảm**; không in danh sách/cookie values trong logs production.

`removeAll()` xóa **các cookie của một store**. Nó chỉ xóa state phía client:

- Không tự gọi endpoint logout.
- Không hủy session token trên server.
- Nếu store bị dùng chung, thao tác này **xóa state của mọi logical user cùng dùng jar**.
- Nếu token được sao chép ra nơi khác, vẫn có thể replay đến khi server revoke hoặc expire.

Vì vậy, hãy có **ownership rõ ràng** cho mỗi store/session lifecycle. Khi chấm dứt một user session, invalidate token **tại server**, sau đó clear jar của user đó hoặc thay jar/client tương ứng.

### 4.3. HttpCookie hiện hành không hoàn toàn là browser cookie model

Oracle Java SE 26 mô tả `HttpCookie` có **partial RFC 6265 support** và một số logic legacy từ RFC 2965. `HttpCookie` có `getSecure()`, `isHttpOnly()`, `getDomain()`, `getPath()`, `getMaxAge()` nhưng API không cung cấp các property kiểu `getSameSite()` hoặc `getPartitioned()` tương đương đầy đủ với hành vi browser hiện đại.

**Không giả định:** JDK `CookieManager` là một trình duyệt đầy đủ với mọi thuật toán SameSite, `__Host-`, `Partitioned`/CHIPS hoặc cookie prefix enforcement như Chrome/Firefox/Safari. Nếu cần mô phỏng browser chính xác, dùng browser integration tests hoặc một cookie implementation được đánh giá đúng use case.

## 5. System-wide CookieHandler và HttpClient-specific cookieHandler

Đây là phân biệt cực kỳ quan trọng trong Java:

**`CookieHandler.setDefault(handler)`** thiết lập cookie handler **toàn JVM** cho Java HTTP URL stream protocol handlers, thường liên quan `HttpURLConnection`. Nó không gắn với user hiện tại và **không phù hợp** nếu một server process đang thực hiện requests thay mặt nhiều người dùng.

```java
// Không dùng làm thiết kế multi-user cookie isolation.
CookieHandler.setDefault(new CookieManager());
```

Đây là đoạn anti-pattern **minh họa**, không phải ví dụ khuyên chạy trong ứng dụng nhiều người dùng.

**`HttpClient.Builder.cookieHandler(handler)`** (Java 11+) cho phép gắn handler cụ thể vào một `HttpClient`:

```java
CookieManager aliceJar =
        new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
CookieManager bobJar =
        new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient aliceClient = HttpClient.newBuilder()
        .cookieHandler(aliceJar)
        .build();
HttpClient bobClient = HttpClient.newBuilder()
        .cookieHandler(bobJar)
        .build();
```

Lúc này **hai cookie stores thực sự khác nhau**. Nếu bạn tạo hai clients nhưng truyền **cùng biến `sharedJar`**, hai clients vẫn dùng **một kho cookies**, và rủi ro lẫn người dùng vẫn còn.

**Lưu ý thêm:** `HttpClient.newHttpClient()` hoặc builder không được cấu hình `cookieHandler` **không tự lấy một `CookieHandler.setDefault` thành cookie store riêng**. Theo `HttpClient.cookieHandler()`, nếu builder không gắn handler, `Optional` trả về rỗng. Không suy đoán mọi HTTP API Java có cùng phạm vi global.

### 5.1. Thiết kế ownership tốt

```text
UserSessionContext (Alice)
  -> HttpClient Alice
     -> CookieManager Alice
        -> CookieStore Alice

UserSessionContext (Bob)
  -> HttpClient Bob
     -> CookieManager Bob
        -> CookieStore Bob

Không:
  static CookieManager GLOBAL_JAR
      -> tất cả HttpClient/user sessions cùng trỏ vào.
```

Đừng dùng một `ThreadLocal<CookieManager>` làm giải pháp mặc định cho async tasks: session logic có thể chạy qua thread pools, virtual threads, callbacks và retries ở các threads khác nhau. **Session context phải truyền tường minh theo logical request/user ownership**. Nếu dùng object pool, bảo đảm không tái sử dụng một jar chứa token của user trước cho user kế tiếp.

### 5.2. Kết nối TCP có thể được chia sẻ không?

Tách cookie jar không nhất thiết có nghĩa mọi kết nối mạng phải có socket riêng mãi mãi; nhưng khi dùng `HttpClient` riêng, connection management thường thuộc từng client. Đừng đánh đổi **cookie credential isolation** để cố chia sẻ connection pool khi chưa có một thiết kế transport/client library hỗ trợ tách security context.

Cookie state, `Authorization` header, proxy authentication, TLS client certificates, caches và redirects đều cần được xem xét cùng **principal ownership**; chỉ đổi cookie jar mà vẫn dùng một static bearer header sẽ không giải quyết lẫn danh tính.

## 6. Vì sao same host + same path không phân biệt người dùng?

Cookie matching của user agent chủ yếu xem **URL scope**, không xem người đang đăng nhập ở tầng business:

```text
Alice:
  GET https://api.example.test/me
  Cookie: sid=TOKEN_A

Bob:
  GET https://api.example.test/me
  Cookie: sid=TOKEN_B

Cả hai:
  scheme=https
  host=api.example.test
  path=/me

Nếu cùng CookieStore:
  Set-Cookie: sid=TOKEN_A; Path=/
  sau đó Set-Cookie: sid=TOKEN_B; Path=/
  -> request tiếp theo có thể mang TOKEN_B,
     kể cả khi code tưởng đang gọi cho Alice.
```

`Domain`, `Path` và `Secure` **không có chiều “userId”**. Một host có thể phục vụ hàng triệu users; nếu Java server outbound client dùng cookie jar toàn cục, host matching đúng vẫn có thể **gửi sai token hợp lệ**.

### 6.1. Một số lỗi thường gặp

```java
// Anti-pattern: một jar static được gắn vào mọi client.
static final CookieManager SHARED =
        new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

// Mỗi request/user tạo client mới nhưng VẪN dùng chung jar.
HttpClient clientForAnyUser = HttpClient.newBuilder()
        .cookieHandler(SHARED).build();
```

Mã trên minh họa vấn đề, không phải chương trình hoàn chỉnh. Không có `synchronized` nào giải quyết được **sai ownership**: cho dù store thread-safe, nó vẫn chứa credential của các danh tính khác nhau. Đồng bộ chỉ xử lý data races, không tự phân biệt sessions.

## 7. Browser cookie scope: Domain, Path, Secure, HttpOnly, SameSite

Các thuộc tính dưới đây quan trọng nhưng giải quyết **các vấn đề khác nhau**:

| Attribute/quy tắc | Mục tiêu | Không bảo đảm |
| --- | --- | --- |
| Không đặt `Domain` | Browser tạo **host-only cookie**, không trải tới subdomains. | Không tách hai users cùng host/profile. |
| `Domain=example.test` | Cho phép cookie áp cho domain và các subdomains phù hợp. | Không chứng minh subdomain đáng tin, có thể mở rộng attack surface. |
| `Path=/app` | Giới hạn request paths được gửi cookie theo path-match. | Không phải security boundary giữa apps cùng host. |
| `Secure` | Browser gửi cookie qua HTTPS/secure channel theo policy. | Không chống XSS/CSRF/token bị lấy cắp từ nơi khác. |
| `HttpOnly` | Ngăn `document.cookie` đọc cookie qua browser JavaScript. | Không chặn script độc hại thực hiện authenticated actions qua browser. |
| `SameSite=Strict/Lax/None` | Giới hạn cookie trong các bối cảnh cross-site browser requests. | Không thay authentication/authorization hoặc CSRF tokens. |
| `Max-Age`/`Expires` | TTL/persistence phía user agent. | Không tự revoke token phía server. |
| `__Host-` prefix | Browser hỗ trợ sẽ yêu cầu Secure, Path=/, không Domain, secure origin. | Không phân biệt người dùng cùng host/browser profile hoặc tạo TLS tự động. |
| `Partitioned` | Cơ chế browser partitioned cookies trong ngữ cảnh third-party theo hỗ trợ. | Không phải cơ chế per-user isolation cho Java CookieManager. |

**Cookie “session” trong browser** thường được chia sẻ giữa các tabs cùng browser profile, không tự tách cho tab A/user A và tab B/user B. Nếu thật sự cần đăng nhập hai danh tính độc lập vào cùng website, hãy dùng **browser profiles/containers khác nhau** hoặc cơ chế application isolation được thiết kế riêng; `Path` không giải quyết user isolation đáng tin cậy.

### 7.1. Domain: host-only và subdomain

Với trình duyệt hiện đại, không đặt `Domain` thường tạo cookie **host-only** (chỉ đúng host đã set). Có `Domain=example.test` thì cookie có thể gửi tới `api.example.test`, `shop.example.test` và các subdomains phù hợp — nếu được browser chấp nhận theo public-suffix/host rules.

**Khuyến nghị:** session auth cookie nên **không đặt Domain** nếu không có yêu cầu sharing giữa subdomains. Nếu nhiều apps cùng parent domain ở các mức tin cậy khác nhau, hạn chế Domain rộng để tránh cookie tossing/subdomain fixation.

**Không nhầm với `java.net.HttpCookie`:** implementation JDK 24/26 hỗ trợ RFC 6265 **một phần** và `HttpCookie.domainMatches` còn mô tả matching theo quy tắc lịch sử RFC 2965. Trong test JDK 24, `Domain=.example.test` được cookie manager chấp nhận và chuyển qua subdomain, còn `Domain=example.test` bị `ACCEPT_ORIGINAL_SERVER` từ chối trong cùng tình huống. **Đừng mang hành vi này thành quy tắc bắt buộc cho browser hiện đại**. Đó là bằng chứng cần test đúng HTTP client/provider nếu ứng dụng dựa vào cookie-domain behavior.

### 7.2. Port không cách ly cookie

Theo cookie protocol, port không phải một thành phần ranh giới bảo mật như nhiều người tưởng:

```text
https://api.example.test:443/account
https://api.example.test:8443/account
```

Cookie có thể được gửi tới **cùng host ở cổng khác**, tùy thuộc scheme/path/attributes và user agent. Đừng giả định chạy nhiều ứng dụng khác user ở các ports khác nhau trên cùng host sẽ tự tách auth cookies.

Trong `CookieScopeRulesDemo`, test `portNotAnIsolationBoundary=PASS` chứng minh trên JDK24 rằng một cookie Secure phù hợp domain/path vẫn được chọn cho URI cùng host ở port 8443.

### 7.3. Path không phải authorization boundary

`Path=/portal` thường giới hạn việc **tự gửi** cookie tới `/portal` và các subpaths. Nhưng trên cùng host, apps có thể tạo/ghi cookies ở những paths khác; JavaScript khả năng truy cập giữa paths cũng không phải một cơ chế bảo mật theo user. Các ứng dụng thuộc mức tin cậy khác nhau nên ưu tiên **host separation** và auth design rõ ràng thay vì tưởng `Path` là sandbox.

### 7.4. Secure và HTTPS

Một session auth cookie production nên có `Secure` và được gửi qua HTTPS suốt toàn session. `Secure` bảo vệ quy tắc truyền qua channel an toàn, nhưng nếu TLS termination/proxy forwarding sai hoặc server có endpoint HTTP công khai không được chặn, vẫn có thể gặp rủi ro.

**Trong demo loopback HTTP**, `Set-Cookie` cố ý **không có Secure** để `HttpClient` Java có thể gửi token qua `http://localhost` và kiểm thử. Đây là **ngoại lệ phục vụ thử nghiệm nội bộ**, không phải mẫu cấu hình cho sản phẩm Internet.

### 7.5. SameSite và CSRF

- `SameSite=Strict` phù hợp khi application không cần cross-site navigation/flows có cookie.
- `SameSite=Lax` thường hỗ trợ top-level navigations an toàn, nhưng không đồng nghĩa chống tất cả CSRF.
- `SameSite=None` dùng cho trường hợp cross-site thực sự cần và theo browser rules phải kết hợp `Secure`.
- Không dựa vào browser default SameSite: policy thực tế khác nhau theo môi trường.
- Với các request thay đổi trạng thái, cân nhắc CSRF token, Origin/Referer validation và custom headers theo threat model.

**`SameSite` là một quy tắc browser, không là bằng chứng user authentication và không buộc Java CookieManager phải mô phỏng mọi điều kiện same-site của browser.** CORS cũng không phải authentication.

### 7.6. __Host- cookie prefix

Một cấu hình browser cookie auth thường dùng:

```http
Set-Cookie: __Host-sid=RANDOM_TOKEN; Path=/; Secure; HttpOnly; SameSite=Lax
```

Theo browser prefix rules, `__Host-` yêu cầu Secure, không có Domain, Path=/ và secure origin. Điều này giảm rủi ro cookie bị subdomain ghi đè. Tuy nhiên:

- Không tự buộc token có entropy cao.
- Không tự chấm dứt session trên server.
- Không thay thế per-user jar isolation trong Java backend.
- Port vẫn không phải cookie isolation boundary.
- Không nên giả định `HttpCookie` Java có đầy đủ browser prefix validation.

Ví dụ header này dành cho **HTTPS production conceptual policy**, không dùng nguyên với HTTP localhost demo.

## 8. Server-side session store và user/tenant binding

Phía server nên lưu session record mô tả danh tính và vòng đời. Mô hình:

```text
token verifier -> SessionRecord {
    userId
    tenantId
    authenticationLevel
    createdAt
    lastActivityAt
    absoluteExpiresAt
    revoked
    device / session metadata
}
```

Đây là mô hình dữ liệu, không phải một object từ JDK. Server phải **xác minh record ở mỗi authenticated request** và kiểm tra authorization của resource cần dùng. Một cookie tên `sid` chỉ định danh một record khi token chưa bị thu hồi; giá trị token **không phải userId**.

### 8.1. Không tin userId nhận từ query/header sau khi thấy cookie

Sai về ranh giới:

```text
GET /orders?userId=alice
Cookie: sid=TOKEN_BOB

Ứng dụng:
  "Có sid cookie, vậy dùng userId=alice trong query"
  -> lỗi kiểm soát truy cập nếu Bob xem được dữ liệu Alice.
```

Đúng: lấy **authenticated principal từ server-side token lookup**, rồi kiểm tra resource thuộc user/tenant đúng theo policy. UserId trong query/path có thể là dữ liệu đầu vào **để chọn resource**, nhưng **không tự có quyền**. Đây là lớp chống broken object-level authorization/IDOR, độc lập với cookie manager.

### 8.2. Session fixation và rotation

Khi user từ anonymous → authenticated, hoặc khi nâng quyền, server nên **phát hành session ID mới**, vô hiệu ID cũ theo chính sách. Không tái sử dụng một ID do client cung cấp rồi gán quyền đăng nhập cho ID ấy.

Trong demo, mỗi lần `POST /login` sinh token mới bằng `SecureRandom` (mô phỏng cấp session). **Demo không xác minh mật khẩu và không phải một hệ thống authentication production**; nó chỉ tạo các fake user labels `alice`/`bob` để chứng minh cookie jar isolation.

### 8.3. Idle/absolute timeout, revocation, logout

- **Idle timeout:** không có hoạt động trong khoảng chính sách thì session không hợp lệ.
- **Absolute timeout:** hết thời hạn tổng ngay cả khi có hoạt động.
- **Logout:** revoke session record phía server và gửi cookie deletion phù hợp `Path/Domain`.
- **Reauthentication:** có thể bắt buộc khi thao tác nhạy cảm hoặc có tín hiệu rủi ro.
- **Rotation:** phát hành token mới với cơ chế chống replay/race theo policy.

Gửi `Set-Cookie: sid=; Max-Age=0; Path=/` chỉ **xóa cookie ở user agent**. **Bắt buộc revoke session server-side**, vì bản sao của session token đã bị đánh cắp vẫn có thể được gửi từ một HTTP client khác.

### 8.4. Lưu session phân tán

Demo dùng `ConcurrentHashMap` in-memory để ngắn gọn. Production nhiều replicas thường cần session store tập trung/replicated hoặc thiết kế token/state khác được đánh giá kỹ. Phải xét:

- Atomic revoke/rotation.
- TTL consistency và clock handling.
- Race giữa logout/retry/parallel requests.
- Hash/verifier storage nếu threat model bao gồm read-only leak của store.
- Tenant separation, access control của data store.
- At-rest encryption và backup protection.
- Eviction/cleanup, metrics, audit và incident response.

Không dùng một static map đơn giản rồi kết luận phiên bền vững qua restart/horizontal scaling.

## 9. Thiết kế per-user/per-session CookieManager

Một service Java thay mặt nhiều users gọi một upstream service nên có **session context có ownership rõ ràng**:

```text
Incoming request (verified principal = Alice)
    |
resolve logical outbound-session key:
  tenant=X + user=Alice + upstream-account=A
    |
lookup/create CookieManager scoped for this identity
    |
invoke upstream via HttpClient tied to that cookie jar
    |
response goes back only to Alice's request context
```

Quy tắc:

1. Không dùng một jar singleton cho mọi người dùng.
2. Không tạo jar mới trên **mỗi request** nếu cần duy trì phiên giữa requests; tạo trên **logical session/login**.
3. Key isolation context bằng **verified principal/tenant/account**, không lấy userId tùy tiện từ HTTP header chưa xác thực.
4. Một user có nhiều tài khoản upstream có thể cần **nhiều jar riêng** ngay cả khi userId giống.
5. Không dùng `ThreadLocal` làm ranh giới session với asynchronous callbacks/retries; truyền context tường minh.
6. Có lifecycle: create, use, rotate, logout/revoke, expire, clear/dispose.
7. Nếu dùng retry/redirect, đánh giá host/credentials và liệu cookie có thể được gửi sai server không.
8. Với shared `HttpClient` ở system level, đừng gắn một CookieManager dùng chung để gửi authenticated cookies của nhiều users.
9. Có **cache isolation**: user-specific HTTP response không được lưu dưới một cache key chỉ theo URL.
10. Không dùng `CookieStore.getCookies()` để log debug; đó có thể là bearer tokens.

### 9.1. Khi nào dùng một CookieManager chung?

Một **một-user desktop app** hoặc một **single service account** chỉ có một principal và một upstream session có thể dùng một CookieManager lâu dài. Nhưng khi một process chứa nhiều logical identities, shared jar có thể làm lẫn phiên. “Mọi request vào cùng domain” là dấu hiệu cần **tách jar hơn**, không phải dấu hiệu nên gom jar.

## 10. Chương trình hoàn chỉnh 1 — CookieSessionIsolationDemo.java

Chương trình này **không sử dụng tài khoản thật**. Nó tạo một `HttpServer` trên loopback với ba routes:

- `POST /login`: nhận nhãn fake `alice` hoặc `bob` để **mô phỏng** tạo phiên, sinh token 192-bit với `SecureRandom`, lưu mapping trong server, trả `Set-Cookie`.
- `GET /me`: đọc cookie `sid`, tra session store rồi trả `user:alice` hoặc `user:bob` nếu token còn hợp lệ, nếu không trả 401.
- `POST /logout`: xóa token khỏi session store và gửi cookie `Max-Age=0`.

Chương trình tạo các `HttpClient` dùng **CookieManager riêng** cho Alice/Bob, rồi cố tình tạo hai clients dùng chung **một `CookieManager`** trong phần **negative test**. Nó chứng minh:

- Với jar riêng: Alice chỉ nhận Alice, Bob chỉ nhận Bob.
- Với jar chung: client được tưởng là Bob có thể thấy cookie phiên Alice, rồi client được tưởng là Alice có thể thấy cookie phiên Bob. Đây là **lỗi kiến trúc được minh họa trong môi trường không dữ liệu thật**, không phải cách triển khai nên dùng.
- Xóa jar không có nghĩa server token tự bị revoke.
- Logout Alice làm token Alice cũ không còn dùng được, Bob không bị ảnh hưởng.
- Cookie policy `ACCEPT_NONE` không tạo ra authenticated session sau một response đặt cookie, và `HttpClient` không có cookie jar mặc định không tự nhớ session.

**Không yêu cầu kết nối Internet, database, Maven/Gradle hoặc external libraries.**

### 10.1. Source đầy đủ

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
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
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class CookieSessionIsolationDemo {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Map<String, String> SESSIONS = new ConcurrentHashMap<>();
    private static final Set<String> DEMO_USERS = Set.of("alice", "bob");

    static String newToken() {
        byte[] bytes = new byte[24];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    static String cookieValue(HttpExchange e) {
        for (String header : e.getRequestHeaders().getOrDefault(
                "Cookie", java.util.List.of())) {
            for (String piece : header.split(";")) {
                String item = piece.trim();
                if (item.startsWith("sid=")) {
                    return item.substring(4).replace("\"", "");
                }
            }
        }
        return null;
    }

    static void respond(HttpExchange e, int status, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        e.getResponseHeaders().set("Content-Type",
                "text/plain; charset=utf-8");
        e.getResponseHeaders().set("Cache-Control", "no-store");
        e.sendResponseHeaders(status, bytes.length);
        try (var out = e.getResponseBody()) {
            out.write(bytes);
        }
    }

    static boolean method(HttpExchange e, String wanted)
            throws IOException {
        if (wanted.equals(e.getRequestMethod())) return true;
        e.getResponseHeaders().set("Allow", wanted);
        respond(e, 405, "method-not-allowed");
        return false;
    }

    static void login(HttpExchange e) throws IOException {
        try (e) {
            if (!method(e, "POST")) return;
            byte[] bytes;
            try (var input = e.getRequestBody()) {
                bytes = input.readNBytes(16);
            }
            String user = new String(bytes, StandardCharsets.UTF_8);
            if (!DEMO_USERS.contains(user)) {
                respond(e, 400, "demo-user-unknown");
                return;
            }
            String token = newToken();
            SESSIONS.put(token, user);
            // LOCAL HTTP DEMO ONLY: production requires HTTPS and Secure.
            e.getResponseHeaders().add("Set-Cookie",
                    "sid=" + token + "; Path=/; HttpOnly; SameSite=Lax");
            respond(e, 200, "session-created");
        }
    }

    static void me(HttpExchange e) throws IOException {
        try (e) {
            if (!method(e, "GET")) return;
            String token = cookieValue(e);
            String user = token == null ? null : SESSIONS.get(token);
            if (user == null) {
                respond(e, 401, "anonymous");
            } else {
                respond(e, 200, "user:" + user);
            }
        }
    }

    static void logout(HttpExchange e) throws IOException {
        try (e) {
            if (!method(e, "POST")) return;
            String token = cookieValue(e);
            if (token != null) SESSIONS.remove(token);
            e.getResponseHeaders().add("Set-Cookie",
                    "sid=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax");
            respond(e, 200, "logged-out");
        }
    }

    static HttpClient client(CookieManager jar) {
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .cookieHandler(jar)
                .build();
    }

    static HttpResponse<String> call(HttpClient client,
            URI base, String path, String body) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(
                base.resolve(path)).timeout(Duration.ofSeconds(5));
        if (body == null) builder.GET();
        else builder.POST(HttpRequest.BodyPublishers.ofString(
                body, StandardCharsets.UTF_8));
        return client.send(builder.build(),
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    static void check(String name, HttpResponse<String> actual,
                      int status, String body) {
        if (actual.statusCode() != status || !body.equals(actual.body())) {
            throw new AssertionError(name + ": expected " + status + "/"
                    + body + ", got " + actual.statusCode() + "/"
                    + actual.body());
        }
        System.out.println(name + "=PASS");
    }

    static void yes(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=PASS");
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        server.setExecutor(pool);
        server.createContext("/login", CookieSessionIsolationDemo::login);
        server.createContext("/me", CookieSessionIsolationDemo::me);
        server.createContext("/logout", CookieSessionIsolationDemo::logout);
        try {
            server.start();
            URI base = URI.create(
                    "http://localhost:" + server.getAddress().getPort() + "/");
            CookieManager aliceJar = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            CookieManager bobJar = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            HttpClient alice = client(aliceJar);
            HttpClient bob = client(bobJar);

            check("freshAliceAnonymous",
                    call(alice, base, "/me", null), 401, "anonymous");
            check("aliceLogin",
                    call(alice, base, "/login", "alice"),
                    200, "session-created");
            check("bobLogin",
                    call(bob, base, "/login", "bob"),
                    200, "session-created");
            check("aliceIsolated",
                    call(alice, base, "/me", null),
                    200, "user:alice");
            check("bobIsolated",
                    call(bob, base, "/me", null),
                    200, "user:bob");
            yes("isolatedJarsSeparate", aliceJar != bobJar
                    && aliceJar.getCookieStore().getCookies().size() == 1
                    && bobJar.getCookieStore().getCookies().size() == 1);

            String aliceOld = aliceJar.getCookieStore().getCookies()
                    .stream().filter(c -> "sid".equals(c.getName()))
                    .findFirst().orElseThrow().getValue();

            CookieManager sharedJar = new CookieManager(
                    null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            HttpClient sharedOne = client(sharedJar);
            HttpClient sharedTwo = client(sharedJar);
            check("sharedDemoLoginAlice",
                    call(sharedOne, base, "/login", "alice"),
                    200, "session-created");
            check("sharedJarAliceSeenByBob",
                    call(sharedTwo, base, "/me", null),
                    200, "user:alice");
            check("sharedDemoLoginBob",
                    call(sharedTwo, base, "/login", "bob"),
                    200, "session-created");
            check("sharedJarBobSeenByAlice",
                    call(sharedOne, base, "/me", null),
                    200, "user:bob");
            sharedJar.getCookieStore().removeAll();
            check("sharedJarCleared",
                    call(sharedOne, base, "/me", null),
                    401, "anonymous");

            check("logoutAlice",
                    call(alice, base, "/logout", ""),
                    200, "logged-out");
            check("aliceInvalidated",
                    call(alice, base, "/me", null),
                    401, "anonymous");
            check("bobUnaffected",
                    call(bob, base, "/me", null),
                    200, "user:bob");

            HttpClient noJar = HttpClient.newHttpClient();
            HttpRequest replay = HttpRequest.newBuilder(base.resolve("/me"))
                    .timeout(Duration.ofSeconds(5))
                    .header("Cookie", "sid=" + aliceOld)
                    .GET().build();
            check("replayedOldTokenRejected",
                    noJar.send(replay, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8)),
                    401, "anonymous");
            check("noCookieClientAnonymous",
                    call(noJar, base, "/me", null),
                    401, "anonymous");

            CookieManager reject =
                    new CookieManager(null, CookiePolicy.ACCEPT_NONE);
            HttpClient noCookies = client(reject);
            check("noCookieAcceptPolicyLogin",
                    call(noCookies, base, "/login", "alice"),
                    200, "session-created");
            check("acceptNoneDoesNotPersist",
                    call(noCookies, base, "/me", null),
                    401, "anonymous");
            System.out.println("checks=18/18");
        } finally {
            server.stop(0);
            pool.shutdownNow();
            pool.awaitTermination(5, TimeUnit.SECONDS);
            SESSIONS.clear();
        }
    }
}
```

### 10.2. Biên dịch và chạy

Lưu source UTF-8 đúng tên `CookieSessionIsolationDemo.java` rồi chạy:

```bash
javac --release 17 -encoding UTF-8 CookieSessionIsolationDemo.java
java CookieSessionIsolationDemo
```

`jdk.httpserver` cung cấp `HttpServer`, `java.net.http` cung cấp `HttpClient` và `java.base` chứa `CookieManager`. Với Java 17+ và code classpath như demo, chúng được JDK giải quyết khi compile. Nếu dùng named `module-info.java`, khai báo `requires jdk.httpserver;` và `requires java.net.http;`. Không cần external JAR. Server bind loopback/port do OS chọn và dừng trong `finally`.

### 10.3. Stdout chính xác đã kiểm chứng trên JDK 24

```text
freshAliceAnonymous=PASS
aliceLogin=PASS
bobLogin=PASS
aliceIsolated=PASS
bobIsolated=PASS
isolatedJarsSeparate=PASS
sharedDemoLoginAlice=PASS
sharedJarAliceSeenByBob=PASS
sharedDemoLoginBob=PASS
sharedJarBobSeenByAlice=PASS
sharedJarCleared=PASS
logoutAlice=PASS
aliceInvalidated=PASS
bobUnaffected=PASS
replayedOldTokenRejected=PASS
noCookieClientAnonymous=PASS
noCookieAcceptPolicyLogin=PASS
acceptNoneDoesNotPersist=PASS
checks=18/18
```

Có **18 kiểm tra PASS** và một dòng tổng kết. Không có token ngẫu nhiên nào được in ra. Các kết quả không phụ thuộc vào giá trị token cụ thể vì test chỉ so status/body an toàn.

### 10.4. Đọc từng nhóm kết quả

**`freshAliceAnonymous`:** một client chưa login không có `sid`, server trả 401. Handler `me` chủ động xử lý `token == null`, không gọi `ConcurrentHashMap.get(null)`.

**`aliceLogin/bobLogin`:** hai HTTP clients với hai cookie jars riêng nhận `Set-Cookie` riêng. Các nhãn user chỉ dùng để mô phỏng, không kiểm tra password hay danh tính thực.

**`aliceIsolated/bobIsolated/isolatedJarsSeparate`:** requests tiếp theo tự mang cookie tương ứng; `CookieStore` của Alice và Bob là những object độc lập.

**`sharedDemoLoginAlice` rồi `sharedJarAliceSeenByBob`:** client thứ nhất ghi Alice token vào một `sharedJar`; client thứ hai, dù được gọi là “Bob client” theo logic, lại tự gửi token Alice. Test cố ý xác nhận `user:alice` để phơi bày nguy cơ.

**`sharedDemoLoginBob` rồi `sharedJarBobSeenByAlice`:** login Bob ghi cookie `sid` mới vào **cùng jar**, khiến client thứ nhất sau đó nhìn thấy phiên Bob. Đây là **negative test cảnh báo**, không phải “hành vi đúng” cho sản phẩm.

**`sharedJarCleared`:** gọi `removeAll()` trên shared store khiến client không còn tự gửi cookie. Nhưng token đã phát hành trên server không tự bị revoke chỉ vì client xóa jar.

**`logoutAlice/aliceInvalidated`:** handler `/logout` xóa mapping token Alice khỏi `SESSIONS`. Sau đó Alice không được xác thực.

**`bobUnaffected`:** Bob dùng jar riêng và vẫn có session hợp lệ; logout Alice không làm mất phiên Bob.

**`replayedOldTokenRejected`:** một client không có jar cố ý gửi lại token Alice cũ; server vẫn trả 401 vì record đã bị hủy. Đây là bằng chứng **server-side revocation**, khác với việc xóa cookie ở client.

**`noCookieClientAnonymous`:** `HttpClient.newHttpClient()` không gắn cookie handler không tự duy trì session cookie cho test này.

**`noCookieAcceptPolicyLogin` rồi `acceptNoneDoesNotPersist`:** `ACCEPT_NONE` có thể nhận HTTP response “session-created”, nhưng không lưu cookie, nên request kế tiếp không được xác thực.

### 10.5. Giới hạn demo — không copy thẳng vào production

- Endpoint `POST /login` chỉ nhận fake label `alice`/`bob`, **không có mật khẩu**, OAuth2/OIDC hoặc credential validation. Đây là cách tạo dữ liệu giả để test cookie isolation, **không phải authentication implementation**.
- `sid` trên localhost HTTP **không có Secure** để demo chạy. Trên HTTPS production phải đặt `Secure`, `HttpOnly`, `SameSite` phù hợp; cân nhắc prefix `__Host-`.
- `ConcurrentHashMap` không có session idle/absolute timeout, persistence, distributed storage, authZ/tenant binding.
- `cookieValue` là parser nhỏ dành cho một cookie đơn giản; không phải parser đầy đủ cho untrusted raw Cookie headers, duplicate cookie names, quoting và profile edge cases.
- `readNBytes(16)` là toy input limit, không phải API login production.
- Không có CSRF token/referer/origin checking; login/logout routes không phục vụ browser Internet.
- Không xử lý network failures, redirects, retries hoặc real identity provider.
- Mục đích bài là **scope của cookie jars và server revocation**, không cung cấp một bộ session framework bảo mật trọn vẹn.
- Test không chạy trên browser; `HttpClient` và `CookieManager` có behavior khác browser về SameSite/prefixes.

## 11. Chương trình hoàn chỉnh 2 — CookieScopeRulesDemo.java

Bài kiểm tra thứ hai không dùng network. Nó gọi trực tiếp:

```java
CookieManager.put(URI responseUri,
                  Map<String, List<String>> responseHeaders);
CookieManager.get(URI requestUri,
                  Map<String, List<String>> requestHeaders);
```

Đây là chữ ký ý tưởng của phương thức, không phải code độc lập khi thiếu manager instance/arguments thực. `put` ghi cookies từ `Set-Cookie`, `get` tạo các header cookies phù hợp với URI theo Java implementation.

### 11.1. Những điều kiểm chứng

- HTTPS + đúng path trả cookie Secure.
- HTTP không gửi cookie có `Secure`.
- Cookie preferences không Secure vẫn có thể được gửi qua HTTP; đừng dùng loại cookie này cho session auth.
- Path `/account` không được áp cho `/public`.
- Host-only cookies không được gửi sang một host khác.
- Port khác nhưng cùng host/scheme/path **không tạo ranh giới cách ly**.
- Explicit `Domain=.example.test` trên JDK test có thể cho subdomains nhận cookie.
- `Max-Age=0` không còn xuất hiện khi lấy cookies.
- `CookieStore.removeAll` xóa cookie state client.

### 11.2. Source đầy đủ

```java
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.util.List;
import java.util.Map;

public final class CookieScopeRulesDemo {
    private static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        System.out.println(name + "=PASS");
    }

    private static String cookies(CookieManager manager, String uri)
            throws Exception {
        return manager.get(URI.create(uri), Map.of())
                .getOrDefault("Cookie", List.of()).toString();
    }

    public static void main(String[] args) throws Exception {
        CookieManager jar = new CookieManager(
                null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
        URI host = URI.create("https://api.example.test/login");
        jar.put(host, Map.of("Set-Cookie", List.of(
                "sid=abc123; Path=/account; Secure; HttpOnly",
                "prefs=vi; Path=/; Max-Age=3600")));

        String sameHttps = cookies(jar,
                "https://api.example.test/account/profile");
        check("httpsAccountSendsSid",
                sameHttps.contains("sid=abc123"));
        check("httpsAccountSendsPrefs",
                sameHttps.contains("prefs="));

        String http = cookies(jar,
                "http://api.example.test/account/profile");
        check("httpBlocksSecureSid",
                !http.contains("sid=abc123"));
        check("httpAllowsNonSecurePrefs",
                http.contains("prefs="));

        String otherPath = cookies(jar,
                "https://api.example.test/public");
        check("pathLimitsSid",
                !otherPath.contains("sid=abc123"));
        check("pathAllowsPrefs",
                otherPath.contains("prefs="));

        String otherHost = cookies(jar,
                "https://untrusted.example.test/account/profile");
        check("hostOnlyLimitsSid",
                !otherHost.contains("sid=abc123"));
        check("hostOnlyLimitsPrefs",
                !otherHost.contains("prefs="));

        String otherPort = cookies(jar,
                "https://api.example.test:8443/account/profile");
        check("portNotAnIsolationBoundary",
                otherPort.contains("sid=abc123"));

        // JDK HttpCookie has partial RFC 6265 support;
        // historical domain matcher expects leading dot here.
        jar.put(host, Map.of("Set-Cookie", List.of(
                "team=shared; Domain=.example.test; Path=/; Secure")));
        check("domainCookieReachesSubdomain",
                cookies(jar,
                        "https://sub.example.test/").contains("team="));

        jar.put(host, Map.of("Set-Cookie", List.of(
                "short=later; Path=/; Max-Age=0")));
        check("expiredCookieNotSent",
                !cookies(jar,
                        "https://api.example.test/").contains("short="));

        jar.getCookieStore().removeAll();
        check("removeAllClearsJar",
                cookies(jar,
                        "https://api.example.test/account/profile")
                        .equals("[]"));
        System.out.println("scopeChecks=12/12");
    }
}
```

### 11.3. Biên dịch, kết quả và giải thích khác biệt định dạng

```bash
javac --release 17 -encoding UTF-8 CookieScopeRulesDemo.java
java CookieScopeRulesDemo
```

**Stdout đã kiểm chứng JDK 24:**

```text
httpsAccountSendsSid=PASS
httpsAccountSendsPrefs=PASS
httpBlocksSecureSid=PASS
httpAllowsNonSecurePrefs=PASS
pathLimitsSid=PASS
pathAllowsPrefs=PASS
hostOnlyLimitsSid=PASS
hostOnlyLimitsPrefs=PASS
portNotAnIsolationBoundary=PASS
domainCookieReachesSubdomain=PASS
expiredCookieNotSent=PASS
removeAllClearsJar=PASS
scopeChecks=12/12
```

Có **12 kiểm tra PASS** và một dòng tổng kết. Các URIs `example.test` chỉ là chuỗi dùng cho `CookieManager.get/put`; chương trình **không tạo HTTP connection đến những tên miền đó**.

Một chi tiết API hữu ích: JDK có thể serialize cookie `prefs` dạng `prefs="vi";$Path="/";...` thay vì literal `prefs=vi`. Vì vậy phép thử kiểm tra `contains("prefs=")`, không dựa vào một định dạng header version-specific. Nếu ứng dụng cần phân tích header chuẩn, dùng parser phù hợp thay vì gọi `String.contains` như authorization logic. **Code này chỉ là test cookie-selection behavior**, không phải cách đọc quyền truy cập production.

### 11.4. Không hiểu sai kết quả Domain

Java SE 26 `HttpCookie` ghi rõ **partial support for RFC 6265**. Trong JDK24 dùng cho kiểm thử, `CookieManager` với `CookiePolicy.ACCEPT_ORIGINAL_SERVER` chấp nhận `Domain=.example.test` cho subdomain, nhưng **không chấp nhận `Domain=example.test`** trong scenario tương ứng. Điều này liên quan historical domain matcher của Java.

Trong **browser cookie rules hiện đại**, dấu chấm đầu của Domain có thể được bỏ qua theo semantics tương ứng. **Không dùng quirks của JDK để thiết kế browser security policy**, và không dùng browser assumptions để đoán kết quả `CookieManager` mà không kiểm thử.

## 12. Cách tránh rò cookie khi xử lý nhiều users song song

Một service Java thường có request handlers chạy đồng thời. Các lỗi về session scope không nhất thiết cần race:

```text
t=1 Alice request -> sharedJar nhận sid=A
t=2 Bob request   -> sharedJar gửi sid=A -> sai user
t=3 Bob login     -> sharedJar nhận sid=B (thay A)
t=4 Alice request -> sharedJar gửi sid=B -> sai user
```

Đây là lỗi **ownership** có thể tái hiện tuần tự; tăng synchronized/locks trên cookie manager **không làm đúng danh tính**.

### 12.1. Multi-tenancy

Trong hệ thống đa tenant, không dùng một key jar chung theo `host` hoặc `serviceName` khi nhiều tenants/users truy cập chung upstream origin. Một partition key thích hợp có thể cần:

```text
(tenantId, verifiedUserId, upstreamAccountId, authSessionId)
```

Chỉ dùng key đã được xác thực/kiểm soát. Tùy use case, cùng user có thể có nhiều session ở thiết bị khác nhau hoặc nhiều upstream accounts — mỗi credentials context cần isolation riêng.

### 12.2. Background jobs và async callbacks

Khi hàng nghìn tasks chạy đồng thời:

- Truyền một `UserSessionContext` tường minh vào task.
- Không dựa vào mutable static variable `currentUser`.
- Không dựa vào `ThreadLocal` mà không bảo toàn context qua async boundaries.
- Không tái sử dụng một global `HttpClient` với global cookie jar cho nhiều tenants.
- Trước mỗi request đi tới upstream, xác nhận session ownership vẫn hợp lệ.
- Khi user logout, hủy queue jobs hoặc ngăn jobs tiếp tục dùng credential đã thu hồi.
- Nếu cookie jar có TTL, resource cleanup phải theo logical session lifecycle.

### 12.3. Redirects và same-origin assumptions

Một HTTP client có redirect policy riêng. Khi request có session cookie và server trả redirect, hãy đánh giá:

- Redirect target host có được trust/allowlist không?
- Cookie/domain/path matching theo client có thể gửi cookie ở đâu?
- Có custom headers `Authorization` được copy sang redirect target không?
- Có downgrade HTTPS→HTTP không?
- Có chuyển từ tenant A host sang tenant B host không?

Không mở `followRedirects(ALWAYS)` cho một application outbound client chứa credentials mạnh mà chưa có chính sách URI và kiểm thử.

## 13. Shared response caches cũng có thể lẫn user

Ngay cả khi cookie jar tách đúng, một tầng cache có thể trả dữ liệu của user khác nếu cache key chỉ có URL:

```text
GET /account -> cache key "/account"
Alice -> response "balance Alice" được cache
Bob   -> cache hit "/account" => nhận "balance Alice"
```

Với nội dung session-sensitive, nên dùng chính sách cache phù hợp như:

```http
Cache-Control: no-store
```

Đây là một **mẫu header**; production cần đánh giá browser/private/shared caches và CDN behavior. Một số tình huống cho phép `private` caching có kiểm soát, nhưng **không mặc định dùng shared cache cho authenticated content**. `Vary: Cookie` không phải giải pháp chung để an toàn với mọi proxy/CDN; phải hiểu cache key và bypass rules thực tế.

Tương tự, không đưa session token vào `ETag`, URL, analytics event hoặc logs. Với OAuth bearer tokens và cookies, credential nào cũng cần ranh giới truy cập rõ.

## 14. Test matrix để không chia sẻ cookie sai người dùng

| Test | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Alice và Bob độc lập | Hai CookieManager, cùng URL. | Alice→Alice, Bob→Bob. |
| Jar dùng chung | Hai HttpClient trỏ một CookieManager. | Negative test phát hiện session crossover. |
| Policy ACCEPT_ORIGINAL_SERVER | Một jar chung cùng host. | Policy không tự tách users. |
| User mới chưa login | Jar trống. | 401/anonymous. |
| Client không cookie handler | `HttpClient.newHttpClient()`. | Không tự replay session từ một jar user khác. |
| ACCEPT_NONE | Không nhận Set-Cookie. | Request sau vẫn anonymous. |
| Logout | Revoke server session + expire cookie. | Token cũ không hợp lệ. |
| Replay token đã logout | Custom request có token cũ. | 401; server-side revocation hoạt động. |
| Bob khi Alice logout | Hai jars độc lập. | Bob vẫn authenticated. |
| Cùng host, khác port | Cookie scope cùng host. | Không giả định port tạo isolation. |
| Secure cookie qua HTTP | HTTP URL. | Cookie Secure không được gửi theo policy. |
| Host-only cookie sang subdomain | Một host khác. | Không được gửi theo host-only rule. |
| Domain rộng | Parent domain cookie. | Nhận diện khả năng bị share giữa subdomains. |
| Path restriction | `/account` vs `/public`. | Scope khác nhau theo path, không phải authZ. |
| Cookie quá hạn | `Max-Age=0`. | Không được gửi lại. |
| Duplicate cookie names | Hai names/scopes/path. | Parser/server có policy xác định, không chọn ngẫu nhiên. |
| Multi-thread/async | Hai users chạy song song. | Không có cross-session state. |
| Multi-tenant | Cùng host và user labels khác tenant. | Token được bind đúng tenant và kiểm tra resource authZ. |
| Browser tabs | Hai tabs cùng profile. | Không kỳ vọng cookie tự cách ly theo tab. |
| Login privilege upgrade | ID cũ và ID mới. | Token cũ bị vô hiệu khi rotation. |
| Cache isolation | `GET /me` /account. | Không phục vụ cross-user cached response. |
| Redirect | 3xx từ upstream. | Không lộ cookie/token cho host không được phép. |

**Test đừng in raw cookie values.** Thay bằng kiểm tra status/body giả lập, session identifier hash chỉ trong môi trường kiểm soát, hoặc thống kê count của jar; không ghi secrets vào CI logs.

## 15. Những anti-pattern phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| Một `static CookieManager` cho mọi user. | Gửi nhầm session cookie cùng origin. | Mỗi logical user/session một jar. |
| Hai HttpClient nhưng cùng `CookieManager`. | Vẫn chia cùng store. | Hai CookieManager + stores độc lập. |
| `CookieHandler.setDefault` trong service multi-user. | Global cookie state không có user identity. | Per-client handler và ownership tường minh. |
| Dùng `ThreadLocal` làm user scope duy nhất. | Async/pooled threads có thể lệch session. | Truyền verified session context. |
| `CookiePolicy.ACCEPT_ORIGINAL_SERVER` = per-user policy. | Chỉ xét server/domain rules, không nhận biết principal. | Tách jars và kiểm tra authZ. |
| `Domain=example.test` cho session không cần subdomains. | Cookie lan tới subdomains không đáng tin. | Host-only, không đặt Domain. |
| Dùng `Path` để cách ly hai tenants. | Path không phải security boundary. | Tenant authorization và jar isolation. |
| Cho rằng port khác là user khác. | Cookie scope không giới hạn theo port. | Host separation + principal binding. |
| Cho rằng `HttpOnly` ngăn mọi XSS abuse. | Script vẫn có thể thực hiện actions với browser credentials. | Chống XSS, CSRF và authZ. |
| Cho rằng `SameSite` là authentication. | Chỉ là browser cross-site delivery control. | AuthN/authZ và CSRF defense. |
| Gửi session token trong URL. | Rò qua history/log/referrer. | HttpOnly Secure cookie hoặc cơ chế được đánh giá. |
| Token là email/userId/timestamp. | Dễ đoán/tiết lộ PII. | Opaque CSPRNG token. |
| Chỉ xóa cookie khi logout. | Server session vẫn hợp lệ nếu token bị replay. | Server-side revoke + cookie expire. |
| Tin browser close là logout. | Session restore và copies còn tồn tại. | Idle/absolute timeout server-side. |
| Dùng JDK CookieManager như Chrome. | HttpCookie chỉ partial RFC 6265, không đầy đủ SameSite/CHIPS. | Test client implementation thực. |
| Print `CookieStore.getCookies()` khi debug. | Lộ bearer credentials. | Redact/hash, không log raw secrets. |
| Shared HTTP response cache chỉ key URL. | Trả data Alice cho Bob. | Cache isolation/no-store cho data nhạy cảm. |
| Chọn account từ input query sau khi có sid. | IDOR/tenant breakout. | Lấy verified principal từ token. |
| Log out Alice bằng sharedJar.removeAll(). | Có thể xóa cookie Bob, không revoke server tokens. | Jar ownership + server revoke riêng. |
| Dùng một test jar cho nhiều test users. | CI lẫn state, tests flakey/có leakage. | Setup/teardown jar riêng mỗi test. |

## 16. Checklist triển khai production

- [ ] Đã phân biệt cookie scope, client jar ownership và server principal scope?
- [ ] Mỗi user/tenant/upstream login có CookieManager độc lập khi cần?
- [ ] Không có global CookieHandler hoặc static cookie jar chứa sessions đa user?
- [ ] HttpClient được tạo/gắn đúng cookieHandler theo logical session?
- [ ] Không share cùng CookieStore qua nhiều managers được cho là độc lập?
- [ ] Không dùng ThreadLocal như nguồn danh tính duy nhất qua async workers?
- [ ] Khi login, server phát hành token mới từ CSPRNG đủ entropy?
- [ ] Token opaque, không có PII/userId/role readable và không ở URL?
- [ ] Production auth cookie có Secure, HttpOnly, SameSite phù hợp trên HTTPS?
- [ ] Có xem xét __Host- prefix, host-only cookie và Path=/?
- [ ] Không đặt Domain rộng nếu không thật sự có subdomain-sharing requirement?
- [ ] Không dựa vào Path/port để phân lập tenants hay người dùng?
- [ ] Có hiểu browser cookie rules khác Java CookieManager partial RFC6265?
- [ ] Session record trên server bind userId, tenantId, expiration, revoked state?
- [ ] Mọi endpoint kiểm tra resource-level authorization bằng verified principal?
- [ ] Có rotate ID khi login/privilege change và chặn session fixation?
- [ ] Có idle và absolute timeout, logout revocation và replay tests?
- [ ] Xóa cookie của đúng jar khi kết thúc phiên, không clear jar người khác?
- [ ] Có secrets/log redaction và `Cache-Control: no-store` cho dữ liệu nhạy cảm?
- [ ] Có kiểm soát redirect/proxy/Authorization headers trong outbound clients?
- [ ] Có kiểm tra same host different port, Domain/Path, Secure, expiry với JDK thực?
- [ ] Có tests đồng thời hai users, cùng host, cùng cookie name?
- [ ] Có đánh giá retries, background tasks, multi-replica session storage?
- [ ] Có không trộn fake login demo với production authentication implementation?

## 17. Bài tập thực hành

**A — Hai users, một host.** Chạy `CookieSessionIsolationDemo` và giải thích vì sao `aliceIsolated` và `bobIsolated` PASS khi có hai jars khác nhau.

**B — Shared jar.** Thay hai jars bằng một jar và quan sát `sharedJarAliceSeenByBob` cùng `sharedJarBobSeenByAlice`. Không sử dụng user/token thật trong test.

**C — ACCEPT_ORIGINAL_SERVER.** Nêu lý do policy acceptance vẫn không tách Alice/Bob: cả hai có cùng scheme, host và path.

**D — No cookies.** Tạo `HttpClient.newHttpClient()` rồi gọi `/me`. So sánh với client có per-session cookie handler và với `CookiePolicy.ACCEPT_NONE`.

**E — Logout/replay.** Lưu token Alice trong test memory, logout Alice, gửi lại token bằng request thủ công. Giải thích vì sao server phải từ chối dù token string còn tồn tại.

**F — Không làm logout giả.** Thử chỉ `getCookieStore().removeAll()` mà không gọi server logout. Giải thích vì sao nó không vô hiệu hóa một bản sao token đã bị lấy cắp.

**G — Domain/path.** Chạy `CookieScopeRulesDemo`, thay `Path=/account` thành `Path=/` và xem cookie được gửi sang URL nào.

**H — Same host different ports.** So sánh `:443` với `:8443`. Tại sao không thể dùng port làm user security boundary?

**I — Browser policy.** Thiết kế browser-based integration tests cho `SameSite=Strict`, `Lax` và `None; Secure`, không dùng Java CookieManager để khẳng định tất cả browser behavior.

**J — __Host- prefix.** Trình bày điều kiện để browser chấp nhận `__Host-sid` và lý do nên tránh Domain attribute. Nêu giới hạn: hai người cùng browser profile vẫn chia cookie jar.

**K — Multi-tenant.** Xây fake SessionRecord có userId/tenantId; thử một user ở tenant X truy cập resource tenant Y. Session valid không có nghĩa được phép truy cập.

**L — Session fixation.** Mô phỏng anonymous session và login; yêu cầu server phát hành ID mới và reject ID cũ khi đã nâng quyền.

**M — Async context.** Cho hai tasks chạy qua cùng thread pool. Thiết kế explicit `UserSessionContext` thay cho một global currentUser hoặc ThreadLocal thiếu propagation.

**N — Cache test.** Đặt cache key chỉ theo `/me`, mô phỏng Bob nhận body Alice rồi sửa bằng cache isolation/no-store. Phân biệt cookie jar leak và response cache leak.

**O — Observability.** Viết event log chỉ chứa code `SESSION_REVOKED`, user/session correlation ID giả/hashed và kết quả; không ghi raw `sid`.

**P — Production plan.** Soạn checklist CSPRNG, trust boundary, session timeout, logout, TLS, SameSite, CSRF, user/tenant authorization, cache isolation và cookie scope JDK/browser compatibility trước khi ra Internet.

## 18. Câu hỏi tự kiểm tra

**1. Một cookie và một phiên đăng nhập có giống nhau không?** — Không. Cookie có thể mang opaque session token; phiên được xác thực/quản lý bằng server state và business principal.

**2. CookiePolicy.ACCEPT_ORIGINAL_SERVER có tách Alice/Bob không?** — Không, nó xét chính sách nhận cookies từ server, không nhận biết người dùng.

**3. Hai HttpClient khác nhau đã đủ cách ly chưa?** — Chưa, nếu cả hai dùng chung CookieManager/CookieStore.

**4. CookieHandler.setDefault dùng phạm vi nào?** — System-wide cho Java HTTP URL protocol handler, không phải một logical user session.

**5. Cách gắn jar riêng cho HttpClient là gì?** — `HttpClient.newBuilder().cookieHandler(jar).build()` với jar thuộc đúng user/session.

**6. Vì sao không dùng ThreadLocal làm session scope mặc định?** — Async tasks/pooled threads có thể chạy trên thread khác; cần ownership/context propagation tường minh.

**7. Không có Domain có ý nghĩa gì với browser cookie?** — Host-only cookie; không tự trải qua mọi subdomains.

**8. Domain và Path có phân tách users không?** — Không, chúng định tuyến cookie theo URL.

**9. Cổng 443 và 8443 có cách ly cookie mặc định không?** — Không; cùng host khác port không tạo security boundary cho cookies.

**10. Secure bảo vệ điều gì?** — Cookie được gửi qua secure transport theo user-agent policy; vẫn cần HTTPS thật và phòng vệ khác.

**11. HttpOnly có xóa hết nguy cơ CSRF không?** — Không, browser vẫn có thể tự gửi cookie trong requests; HttpOnly chủ yếu chống JavaScript đọc cookie.

**12. SameSite thay authorization được không?** — Không. Nó là cơ chế browser cross-site cookie delivery, không xác minh principal hay quyền resource.

**13. __Host- prefix yêu cầu gì?** — Secure, Path=/, không Domain, secure origin với browser hỗ trợ.

**14. CookieStore.removeAll có thu hồi token trên server không?** — Không. Phải revoke token/session record phía server.

**15. Browser close có luôn kết thúc phiên không?** — Không. Có session restore; server phải thực thi timeout/revocation.

**16. Vì sao cần session ID mới sau login/nâng quyền?** — Giảm session fixation và đảm bảo binding với mức xác thực mới.

**17. Java HttpCookie có đầy đủ SameSite/Partitioned browser semantics không?** — Không nên giả định; Java SE 26 mô tả partial RFC 6265 support và không có các API property tương đương đầy đủ.

**18. Demo đã kiểm thử bao nhiêu trường hợp?** — `CookieSessionIsolationDemo`: 18/18; `CookieScopeRulesDemo`: 12/12, biên dịch Java 17 và chạy JDK 24. Tổng cộng 30 kiểm tra có kết quả đã đối chiếu, không dùng account/token thật.

## 19. Tài liệu chính thức và hướng dẫn hiện hành

- [Oracle Java SE 26 — CookieManager](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieManager.html): cơ chế CookieHandler/CookiePolicy/CookieStore; mặc định ACCEPT_ORIGINAL_SERVER và store trong RAM.
- [Oracle Java SE 26 — CookieStore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieStore.html): add/get/getCookies/remove/removeAll và expiration.
- [Oracle Java SE 26 — CookieHandler](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieHandler.html): callback và `setDefault/getDefault` system-wide.
- [Oracle Java SE 26 — CookiePolicy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookiePolicy.html): ACCEPT_ALL/ACCEPT_NONE/ACCEPT_ORIGINAL_SERVER.
- [Oracle Java SE 26 — HttpCookie](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/HttpCookie.html): Domain/Path/Secure/HttpOnly/Max-Age, partial RFC 6265 support và legacy domainMatches.
- [Oracle Java SE 26 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `cookieHandler` cấu hình riêng theo client.
- [Oracle Java SE 26 — HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): `cookieHandler()` Optional; default client không được gắn handler nếu builder không đặt.
- [Oracle Java SE 17 — CookieManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html): tương thích API dùng trong demo `--release 17`.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): entropy, session lifecycle, Session Fixation, Secure/HttpOnly/SameSite, host-only/prefixes, logout và server timeouts.
- [HTTPWG — draft-ietf-httpbis-rfc6265bis](https://httpwg.org/http-extensions/draft-ietf-httpbis-rfc6265bis.html): bản **draft** cập nhật về browser cookie storage, scope, SameSite và `__Host-`; không mô tả như RFC đã phát hành.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): các quy tắc cookie Domain, Path và security caveats có nền tảng tiêu chuẩn.

**Kết luận:** Phạm vi **Domain/Path/Secure** trả lời “cookie được gửi tới URL nào”, còn **CookieManager/CookieStore** quyết định “cookie của user nào đang được giữ”. Trong Java multi-user service, **không dùng chung cookie jar giữa logical sessions**. Trên server, opaque session token chỉ hữu ích khi được xác minh, ràng buộc đúng user/tenant, có timeout và revoke. Kết hợp per-user jar isolation, HTTPS/Secure/HttpOnly/SameSite đúng ngữ cảnh browser, CSRF protection, server-side authorization, no-store cache policy và kiểm thử negative cross-user/cross-tenant để ngăn lẫn phiên.
