# HttpCookie, domain, path, secure và thời hạn

## 1. Tổng quan: Cookie trong Java hiện đại

HTTP là giao thức có các yêu cầu độc lập. Để một trình duyệt hoặc HTTP client mang trạng thái giữa các yêu cầu, server có thể trả về **`Set-Cookie`**; client lưu trạng thái đó theo chính sách của mình và gửi các cặp `name=value` trong header **`Cookie`** ở các yêu cầu tiếp theo.

Java SE cung cấp **`java.net.HttpCookie`, `CookieHandler`, `CookieManager`, `CookiePolicy`, `CookieStore`** từ Java 6; chúng **vẫn còn áp dụng trong Java SE 26**. Mục tiêu bài này là cách dùng chúng với các quy tắc HTTP cookie **hiện nay**, không đề xuất các cơ chế Version/Port/Set-Cookie2 thuộc RFC 2965 như một chuẩn mới. Đối với Java 11+ HTTP client, `HttpClient.Builder.cookieHandler(...)` tích hợp cookie manager vào client một cách tường minh.

Một session cookie có thể được phát bằng response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=opaque_token; Path=/; Max-Age=900; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json
~~~

Browser nhận response, lưu cookie nếu hợp lệ và sau đó có thể gửi:

~~~http
GET /account/profile HTTP/1.1
Host: shop.example.com
Cookie: __Host-session=opaque_token
~~~

**Lưu ý:** header `Cookie` **không gửi lại** các cờ `Domain`, `Path`, `Secure`, `HttpOnly`, `Max-Age` hay `SameSite`. Server không thể dựa riêng vào request Cookie để biết client có thực sự giữ cookie đúng chính sách hay không; server vẫn cần session store, xác thực và phân quyền.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt header `Set-Cookie` ở response, `Cookie` ở request và object `HttpCookie` trong Java.
2. Hiểu **host-only cookie** khi không có Domain, **domain-scoped cookie** khi đặt Domain và rủi ro subdomain.
3. Giải thích cách `Path`/default path hoạt động, segment-boundary matching và giới hạn bảo mật của Path.
4. Cấu hình `Secure`, `HttpOnly`; hiểu SameSite, tiền tố `__Host-` và những thuộc tính trình duyệt không được `HttpCookie` mô hình hóa.
5. So sánh `Max-Age`, `Expires`, session cookie; biết `getMaxAge()`, `setMaxAge()`, `hasExpired()`.
6. Tránh dùng `HttpCookie.toString()` như một `Set-Cookie` response header.
7. Sử dụng `CookieManager` và `CookieStore` với `CookiePolicy.ACCEPT_ORIGINAL_SERVER`, gắn `CookieHandler` vào Java HttpClient.
8. Kiểm thử hoạt động cookie bằng hai chương trình Java 17+ đã biên dịch/chạy thực tế, có output đối chiếu được.
9. Thiết kế session cookie cho HTTPS, tránh session fixation, CSRF, XSS và dữ liệu nhạy cảm bị lộ.

## 2. Trình duyệt, Java client và server có trách nhiệm khác nhau

~~~text
Server                         Browser / Java HTTP client
  |                                      |
  | <------- GET /login ---------------- |
  |                                      |
  | -- Set-Cookie: sid=...; ... -------->|
  |                                      |
  |                             Cookie jar checks:
  |                             domain / path / expiry
  |                             secure / policy / SameSite
  |                                      |
  | <--- GET /account; Cookie: sid=... --|
  |                                      |
  | -- Response after session check --->|
~~~

- **Server** phát `Set-Cookie` với scope/expiration và lưu session state nếu cần. Server tự quyết định giá trị token có hợp lệ và user có quyền hay không.
- **Browser** thực thi domain/path/secure/SameSite/third-party/eviction policies của trình duyệt đó.
- **Java HttpClient với CookieManager** có cookie jar và policy riêng, nhưng không phải một trình duyệt. Đặc biệt **SameSite**, **Partitioned/CHIPS** và third-party tracking controls không thể được mô phỏng đầy đủ chỉ từ `java.net.HttpCookie`.

Một cookie value là **dữ liệu do client gửi trở lại**, không phải bằng chứng xác thực. Khi có session token, server nên tra token trong storage, kiểm tra TTL/revocation/authorization và không chấp nhận role/price/tenant ID trong cookie chỉ vì chúng xuất hiện ở đó.

### 2.1. Multiple Set-Cookie không phải một Cookie header

Có thể phát nhiều `Set-Cookie` **độc lập**:

~~~http
Set-Cookie: __Host-session=opaque; Path=/; Max-Age=900; Secure; HttpOnly; SameSite=Lax
Set-Cookie: locale=vi; Path=/; Max-Age=86400; Secure; SameSite=Lax
~~~

Đừng tùy tiện nối chúng bằng dấu phẩy; `Expires` chứa dấu phẩy trong HTTP date, và parser có thể xử lý sai. Dùng API server hỗ trợ nhiều giá trị của response header, chẳng hạn `Headers.add("Set-Cookie", value)`.

### 2.2. Các thuộc tính không phải một cơ chế mã hóa

`Secure` chỉ hạn chế kênh gửi lại, `HttpOnly` chỉ hạn chế API đọc cookie từ script của browser. Cả hai **không mã hóa** cookie trong server logs, memory, storage, response dump hoặc backup. Session token phải đủ ngẫu nhiên, ngắn hạn, được quản lý ở server, không xuất hiện trong URL hay logs.

## 3. Domain: không khai báo là host-only

### 3.1. Host-only cookie

Giả sử server trên `https://shop.example.com` trả:

~~~http
Set-Cookie: session=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Vì **không có Domain**, browser tạo cookie gắn với **chính xác host `shop.example.com`**. Nó không tự gửi đến `api.shop.example.com` hoặc `example.com`. Đây là phạm vi nên ưu tiên cho session không cần chia sẻ giữa subdomains.

### 3.2. Domain-scoped cookie

~~~http
Set-Cookie: locale=vi; Domain=example.com; Path=/; Secure; SameSite=Lax
~~~

Nếu origin được phép đặt Domain đó và browser chấp nhận, cookie có thể được gửi cho `example.com` và các subdomains như `shop.example.com`, `api.example.com`. Điều này tăng **attack surface** nếu một subdomain bị compromise. Hãy bỏ Domain khi không cần chia sẻ trạng thái.

Một server ở `shop.example.com` không được đặt cookie cho `unrelated.example.net`. Browser hiện đại thường từ chối Domain là **public suffix** như `com` và `co.uk`. `Domain=*` không phải cookie wildcard hợp lệ. Dấu chấm đầu của `Domain=.example.com` bị bỏ qua trong quy tắc hiện đại; nên viết `Domain=example.com` rõ ràng.

### 3.3. Cookie không cô lập theo port

Cookie scope về cơ bản dựa trên hostname, path, scheme-related policy, **không dùng TCP port làm boundary**. Hai ứng dụng khác port trên cùng hostname vẫn có thể tác động cookie scope theo tình huống; không coi việc đổi port là security boundary.

### 3.4. HttpCookie.setDomain và getDomain

~~~java
HttpCookie cookie = new HttpCookie("locale", "vi");
cookie.setDomain("example.com");
System.out.println(cookie.getDomain());
~~~

Đây là **đoạn mã minh họa**, không phải file độc lập; kết quả accessor là `example.com`. Nó chỉ thiết lập thuộc tính của **object Java**, không tự tạo HTTP response hay buộc browser chấp nhận Domain.

`HttpCookie.domainMatches(...)` vẫn tồn tại nhưng Java Javadoc mô tả các quy tắc lịch sử liên quan RFC 2965. Không dùng helper này như một bản triển khai đầy đủ quy tắc browser hiện đại, public-suffix checks, host-only flag, third-party policies. Khi `CookieManager` lưu cookie, nó liên kết cookie với origin URI theo cơ chế nội bộ; một trường `getDomain()==null` ở object tự tạo **không** thay toàn bộ kiểm chứng browser.

## 4. Path: segment boundary, không phải phân quyền

Cookie với:

~~~http
Set-Cookie: preference=blue; Path=/account; Secure; Max-Age=120
~~~

sẽ có thể được gửi đến `/account`, `/account/profile`, `/account/orders/1`, nhưng không đến `/outside`, `/catalog` hay `/accountant`. Quy tắc path-match trong RFC 6265 **không** đơn giản là `requestPath.startsWith(cookiePath)`: `/accountant` không có dấu phân cách `/` sau `/account`.

### 4.1. Default Path

Nếu response đến từ `https://example.com/docs/Web/HTTP/index.html` và thiếu `Path`, browser tính default path theo directory, ví dụ `/docs/Web/HTTP/`, **không mặc định luôn /**. Vì vậy cookie đăng nhập muốn có hiệu lực trên toàn host thường phải ghi rõ `Path=/`.

### 4.2. Path không bảo vệ dữ liệu

`Path=/admin` **không** thay thế authorization của endpoint `/admin`. Các ứng dụng trong cùng origin có thể chia sẻ security context theo cách khác, và script độc hại có thể gây request. Luôn kiểm tra user identity, role và permission ở server.

### 4.3. HttpCookie.setPath/getPath

~~~java
HttpCookie cookie = new HttpCookie("pref", "blue");
cookie.setPath("/account");
boolean expectedPath = "/account".equals(cookie.getPath());
~~~

Đây là đoạn trích: nó **chưa gửi** cookie đi đâu. Cookie handler/browser là thành phần chọn cookie nào cho mỗi request. Chương trình integration test phần 10 dùng Java CookieManager thật để xác nhận `/account/profile` nhận cookie và `/outside` không nhận.

## 5. Secure và HttpOnly

### 5.1. Secure

`Secure` hướng dẫn user agent chỉ gửi cookie qua kênh an toàn, thường là HTTPS, để tránh gửi secret trong request HTTP không mã hóa.

~~~java
HttpCookie cookie = new HttpCookie("sid", "opaque");
cookie.setSecure(true);
boolean secure = cookie.getSecure();
~~~

Đoạn trích trên chỉ thiết lập `Secure` trong object. Nó **không bật TLS**, không thay `http://` thành `https://`, không bảo mật storage/logs và không xác thực session. Trên production, phát session cookies bằng HTTPS và có HSTS/TLS/proxy setup thích hợp. Một số browser có ngoại lệ cho `localhost`, **không áp dụng** điều đó cho public hosts.

### 5.2. HttpOnly

~~~java
HttpCookie cookie = new HttpCookie("sid", "opaque");
cookie.setHttpOnly(true);
boolean httpOnly = cookie.isHttpOnly();
~~~

`HttpOnly` ngăn JavaScript trong trang truy cập cookie bằng `document.cookie`, giảm khả năng đánh cắp session token khi có XSS. Nhưng JavaScript **vẫn có thể gửi HTTP request** và browser tự mang cookie theo credentials/cookie policy. Vì thế HttpOnly không thay **XSS prevention, CSRF tokens, Origin checks hoặc authorization**.

API `setHttpOnly/isHttpOnly` còn có trong Java 17/26; đây là bổ sung sau Java 6 gốc, nên không khẳng định mọi method hiện nay đều đã xuất hiện trong JDK 6. Bài tập dùng Java 17+ để giữ ví dụ runnable.

### 5.3. So sánh

| Attribute | Kiểm soát | Không đảm bảo |
| --- | --- | --- |
| `Secure` | Cookie chỉ được gửi qua secure scheme theo user-agent policy | Không mã hóa server storage/logs, không tự có HTTPS |
| `HttpOnly` | Script browser không được đọc qua document.cookie | Script vẫn gửi requests, không chống mọi XSS/CSRF |
| `Path` | Giới hạn request URI paths | Không có authorization/isolation thực sự |
| `Domain` | Giới hạn/cho phép hosts và subdomains | Không xác thực danh tính host của request ở server |
| `Max-Age/Expires` | Thời gian lưu ở client | Không thay server-side expiry/revocation |
| `SameSite` | Điều kiện gửi trong cross-site context | Không bảo đảm CSRF prevention toàn phần |

## 6. SameSite, __Host- và những tính năng browser không có setter trong HttpCookie

### 6.1. SameSite

- `SameSite=Strict`: hạn chế gửi cookie ở cross-site requests tối đa.
- `SameSite=Lax`: phù hợp nhiều website vì có thể cho phép một số top-level safe navigations, nhưng hạn chế phần lớn cross-site background requests.
- `SameSite=None`: dành cho trường hợp cần cross-site cookie; **phải đi kèm `Secure`** theo browser policy.

SameSite giúp chống CSRF nhưng không thay CSRF token, Origin/Referer validation và bảo vệ chống XSS.

**API thực tế:** `java.net.HttpCookie` trong Java SE 26 **không cung cấp `setSameSite(...)`**. Đừng tự bịa method đó. Để phát SameSite cho browser, dùng web framework có API riêng hoặc tự dựng **`Set-Cookie` header được validate**. Tương tự, `HttpCookie` không có setter `setPartitioned(...)` cho cookie partitioned/CHIPS hiện đại.

### 6.2. Prefix __Host-

Với session chỉ có hiệu lực trên đúng hostname, browser hỗ trợ prefix `__Host-` yêu cầu:

1. Được thiết lập từ origin bảo mật (HTTPS);
2. Có cờ `Secure`;
3. **Không có `Domain`**;
4. `Path=/`.

~~~http
Set-Cookie: __Host-session=opaque; Path=/; Max-Age=900; Secure; HttpOnly; SameSite=Lax
~~~

Prefix `__Secure-` yêu cầu secure origin + Secure nhưng có thể có Domain nếu business thật sự cần. MDN còn mô tả prefix `__Http-`/`__Host-Http-` với HttpOnly; phải đánh giá compatibility của browsers mục tiêu. Tên cookie Java bắt đầu bằng `__Host-` **không tự thực thi** các quy tắc browser khi gọi `new HttpCookie(...)`.

### 6.3. Cookie Partitioned/CHIPS

Browser hiện đại có `Partitioned` để phân vùng storage theo top-level site và yêu cầu Secure. Đây là browser policy **không được Java CookieManager tái hiện đầy đủ**. Một Java HTTP client không có thông tin navigation frame/site giống browser. Khi hệ thống dựa vào cross-site/iframe cookies, hãy test với browsers thực tế.

## 7. Thời hạn: Max-Age, Expires và deletion

### 7.1. Max-Age tính theo giây

~~~http
Set-Cookie: session=opaque; Path=/; Max-Age=1800; Secure; HttpOnly
~~~

`Max-Age=1800` là thời hạn tối đa **1800 giây**, không phải phút, giờ hay ngày. Lưu ý `setMaxAge(long)` cũng nhận **giây**, không nhận milliseconds.

### 7.2. Expires là ngày giờ tuyệt đối

~~~http
Set-Cookie: session=opaque; Path=/; Expires=Wed, 01 Jan 2031 00:00:00 GMT; Secure; HttpOnly
~~~

`Expires` là HTTP-date UTC/GMT. Nếu có đồng thời `Max-Age` và `Expires`, **Max-Age ưu tiên**, theo RFC 6265 và Java SE 26 `HttpCookie.getMaxAge()`. Browser có thể xử lý clock skew và có quyền evict cookie trước hạn do privacy/memory constraints.

### 7.3. Session cookies

~~~http
Set-Cookie: session=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Không có Max-Age/Expires thì thường là **session cookie**. Nhưng browser có thể **restore phiên** sau khi đóng/mở lại, nên đừng dựa vào việc đóng tab/browser là đăng xuất chắc chắn. Server phải có **absolute TTL, idle timeout và revocation**.

### 7.4. HttpCookie.getMaxAge và setMaxAge

~~~java
HttpCookie cookie = new HttpCookie("session", "opaque");
cookie.setMaxAge(900L);
long maxAgeSeconds = cookie.getMaxAge(); // 900.
boolean expired = cookie.hasExpired();
~~~

Theo Oracle Java SE 26:

| Giá trị | Ý nghĩa |
| --- | --- |
| `getMaxAge()==-1` mặc định | Không có expiry fixed; session-style |
| `setMaxAge(900)` | Thời hạn tối đa 900 giây kể từ lúc tạo |
| `setMaxAge(0)` | Hết hạn tức thì / yêu cầu xóa |
| `hasExpired()` | Kiểm tra tuổi cookie object với Max-Age của nó |

`getMaxAge()` trả **thời hạn** đã đặt/tính, không phải đồng hồ đếm ngược còn bao nhiêu giây ở thời điểm gọi. Nếu cần dùng expiration server-side, phải có `Instant expiresAt` trong session store chứ không chỉ nhìn cookie từ client.

### 7.5. Max-Age và Expires khi HttpCookie.parse()

Javadoc `getMaxAge()` mô tả thứ tự:

1. Nếu ứng dụng gọi `setMaxAge(...)`, dùng giá trị đó;
2. nếu chưa, dùng `Max-Age` đã parse;
3. nếu không có Max-Age, dùng số giây tính từ `Expires` đã parse;
4. nếu không có hai thuộc tính, trả `-1`.

Ví dụ chương trình phần 9 parse cả `Max-Age=120` và `Expires=2031`, nhận kết quả `120`.

### 7.6. Deletion/logout

~~~http
Set-Cookie: __Host-session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Muốn browser xóa cookie gốc, phải dùng **cùng tên và Domain/Path scope tương ứng**. Ví dụ cookie ban đầu có `Path=/account`, logout gửi `Path=/` có thể tạo/loại bỏ entry khác mà cookie cũ vẫn còn. Đồng thời **revoke session server-side**: client có thể tự giữ/copy/replay giá trị cũ dù browser đã xóa.

## 8. HttpCookie.parse(), toString() và nguy cơ header injection

### 8.1. Các method cần nhớ

| API | Vai trò hiện hành |
| --- | --- |
| `new HttpCookie(name,value)` | Tạo cookie model Java |
| `HttpCookie.parse(header)` | Parse Set-Cookie header string thành danh sách cookies |
| `getDomain()/setDomain()` | Domain attribute |
| `getPath()/setPath()` | Path attribute |
| `getSecure()/setSecure()` | Secure flag |
| `isHttpOnly()/setHttpOnly()` | HttpOnly flag |
| `getMaxAge()/setMaxAge()` | Thời hạn tính bằng giây |
| `hasExpired()` | Kiểm tra đã hết hạn |
| `getName()/getValue()/setValue()` | Cookie name/value |
| `toString()` | Representation cho **Cookie request header**, không phải Set-Cookie response |

`HttpCookie` có các methods lịch sử `setVersion`, `setPortlist`, `setComment` cho hỗ trợ cookie specifications cũ, nhưng không nên hướng dẫn ứng dụng mới phụ thuộc `Set-Cookie2` hoặc Version/Port cookies.

### 8.2. Parse Set-Cookie

~~~java
List<HttpCookie> cookies = HttpCookie.parse(
    "Set-Cookie: theme=blue; Domain=shop.example.com"
  + "; Path=/account; Max-Age=120; Secure; HttpOnly");
HttpCookie first = cookies.get(0);
~~~

Đây là **đoạn trích**. Thực tế phải kiểm tra list, name, attributes, origin và policy. `parse` có thể trả nhiều entries hoặc ném `IllegalArgumentException` khi cú pháp sai; không có nghĩa browser sẽ chấp nhận domain/public suffix/prefix. Đừng trộn nhiều dòng `Set-Cookie` vào một chuỗi có dấu phẩy.

### 8.3. toString() không dựng response header

`HttpCookie.toString()` theo Javadoc là biểu diễn của **cookie request header value**. Nó **không** được dùng để phát response `Set-Cookie` đầy đủ:

~~~java
// Sai: thiếu policy về Secure, Path, Max-Age và SameSite.
responseHeaders.add("Set-Cookie", cookie.toString());
~~~

Thay bằng framework cookie-builder hoặc builder có policy chặt. Khi nối thủ công, cookie name/value phải được validate để không chứa `;`, CR/LF hay control characters, tránh header injection. Với session token, tạo bytes từ `SecureRandom` rồi mã hóa Base64URL không padding:

~~~java
byte[] random = new byte[32]; // 256 bit.
new java.security.SecureRandom().nextBytes(random);
String token = java.util.Base64.getUrlEncoder()
        .withoutPadding().encodeToString(random);
~~~

**Đoạn trích**, chưa có session storage/HTTPS. Không dùng `Random` hoặc timestamp làm session secrets; không log tokens.

## 9. Java 17+ runnable: HttpCookie, domain/path/secure/expiration

Chương trình `HttpCookieAttributesDemo.java` đã được chạy thực tế với OpenJDK 24 và `--release 17`. Nó:

- Tạo cookie tên `__Host-session` có **ý định host-only** (Domain null), `Path=/`, `Secure`, `HttpOnly`, `Max-Age=1800`.
- Dùng builder chỉ chấp nhận name/value ASCII URL-safe, policy Secure/HttpOnly/Path/no Domain và SameSite Lax/Strict.
- Kiểm chứng `HttpCookie.toString()` khác `Set-Cookie` đã được dựng.
- Parse `Domain=shop.example.com`, `Path=/account`, `Max-Age=120` và `Expires=2031`, xác nhận Max-Age ưu tiên.
- Xác nhận default Max-Age `-1` và `Max-Age=0` đã expired.

Đây là ví dụ học API, **token cố định không đủ an toàn cho production**. Builder không kiểm tra TLS termination; ứng dụng phải phát cookie qua HTTPS.

### 9.1. File HttpCookieAttributesDemo.java

~~~java
import java.net.HttpCookie;
import java.util.List;

public final class HttpCookieAttributesDemo {
    private static void check(boolean test, String why) {
        if (!test) throw new AssertionError(why);
    }

    private static String setCookieHeader(HttpCookie cookie, String sameSite) {
        // Static application policy: only URL-safe ASCII opaque tokens.
        if (!cookie.getName().matches("[A-Za-z0-9_\\-]+")
                || !cookie.getValue().matches("[A-Za-z0-9_\\-]+")) {
            throw new IllegalArgumentException("Unsafe cookie name/value");
        }
        if (!"/".equals(cookie.getPath()) || cookie.getDomain() != null
                || !cookie.getSecure() || !cookie.isHttpOnly()
                || cookie.getMaxAge() < 0) {
            throw new IllegalArgumentException("Invalid __Host- session policy");
        }
        if (!"Lax".equals(sameSite) && !"Strict".equals(sameSite)) {
            throw new IllegalArgumentException("SameSite must be allowlisted");
        }
        return cookie.getName() + "=" + cookie.getValue()
                + "; Path=/; Max-Age=" + cookie.getMaxAge()
                + "; Secure; HttpOnly; SameSite=" + sameSite;
    }

    public static void main(String[] args) {
        HttpCookie session = new HttpCookie("__Host-session", "opaque_token_42");
        session.setPath("/");
        session.setSecure(true);
        session.setHttpOnly(true);
        session.setMaxAge(1800L);
        check(session.getDomain() == null, "host-only intent");
        check(session.getSecure() && session.isHttpOnly(), "security flags");
        check("/".equals(session.getPath()), "path");
        check(session.getMaxAge() == 1800, "age");
        String header = setCookieHeader(session, "Lax");
        check(header.equals("__Host-session=opaque_token_42"
                + "; Path=/; Max-Age=1800; Secure; HttpOnly; SameSite=Lax"),
                "header");
        System.out.println("host-only-intent=true");
        System.out.println("path=" + session.getPath());
        System.out.println("secure=" + session.getSecure());
        System.out.println("http-only=" + session.isHttpOnly());
        System.out.println("max-age-seconds=" + session.getMaxAge());
        System.out.println("samesite-in-set-cookie=" + header.contains("; SameSite=Lax"));
        System.out.println("toString-is-set-cookie="
                + session.toString().equals(header));

        List<HttpCookie> parsed = HttpCookie.parse(
                "Set-Cookie: preference=blue; Domain=shop.example.com"
                + "; Path=/account; Max-Age=120"
                + "; Expires=Wed, 01 Jan 2031 00:00:00 GMT"
                + "; Secure; HttpOnly");
        check(parsed.size() == 1, "one cookie");
        HttpCookie preference = parsed.get(0);
        check("shop.example.com".equals(preference.getDomain()), "domain");
        check("/account".equals(preference.getPath()), "path");
        check(preference.getMaxAge() == 120, "Max-Age precedence");
        check(preference.getSecure() && preference.isHttpOnly(), "attributes");
        System.out.println("parsed-domain=" + preference.getDomain());
        System.out.println("parsed-path=" + preference.getPath());
        System.out.println("max-age-precedence=" + preference.getMaxAge());

        HttpCookie sessionOnly = new HttpCookie("temporary", "t");
        check(sessionOnly.getMaxAge() == -1, "session age");
        System.out.println("default-max-age=" + sessionOnly.getMaxAge());

        HttpCookie deletion = new HttpCookie("temporary", "x");
        deletion.setMaxAge(0);
        check(deletion.hasExpired(), "zero age expiry");
        System.out.println("zero-max-age-expired=" + deletion.hasExpired());
        System.out.println("tests=PASS");
    }
}
~~~

### 9.2. Biên dịch và stdout

~~~bash
javac -encoding UTF-8 --release 17 HttpCookieAttributesDemo.java
java HttpCookieAttributesDemo
~~~

Stdout **chính xác**, đã kiểm thử:

~~~text
host-only-intent=true
path=/
secure=true
http-only=true
max-age-seconds=1800
samesite-in-set-cookie=true
toString-is-set-cookie=false
parsed-domain=shop.example.com
parsed-path=/account
max-age-precedence=120
default-max-age=-1
zero-max-age-expired=true
tests=PASS
~~~

**Giải thích:** `host-only-intent=true` là ý định cấu hình **không Domain**, để browser có host-only behavior phải thực sự bỏ Domain khi phát `Set-Cookie` qua HTTPS. `toString-is-set-cookie=false` xác nhận object serialization không thay response builder. `max-age-precedence=120` đúng Javadoc, `zero-max-age-expired=true` là trạng thái xóa ngay. Không suy từ fixture rằng trình duyệt nào cũng dùng cookie prefix/SameSite giống Java object.

## 10. CookieManager, CookieStore, CookiePolicy và HttpClient

### 10.1. Vai trò các lớp

- `CookieHandler` định nghĩa `get(uri,requestHeaders)` để sinh cookies cho outgoing request và `put(uri,responseHeaders)` để nhận cookies từ response.
- `CookieManager` là implementation có `CookieStore` và `CookiePolicy`.
- `CookieStore` lưu `HttpCookie`, lấy cookies cho URI và dọn expired entries.
- `CookiePolicy.ACCEPT_ORIGINAL_SERVER` là policy mặc định, hạn chế acceptance theo original server. `ACCEPT_ALL` không phù hợp nếu không có lý do rất rõ và kiểm soát trust; `ACCEPT_NONE` từ chối mọi cookies.

Với Java 11+ HttpClient, dùng instance riêng:

~~~java
CookieManager manager =
        new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
HttpClient client = HttpClient.newBuilder()
        .cookieHandler(manager)
        .build();
~~~

Đây là đoạn trích. Nó tốt hơn việc tự ý gọi `CookieHandler.setDefault(...)` cho cả JVM khi nhiều thư viện đang sử dụng chung process. CookieManager default dùng **in-memory store**, không tự cung cấp persistent browser profile hoặc server-side session management.

### 10.2. Những gì CookieManager KHÔNG đảm bảo

- Không mô phỏng đầy đủ **SameSite, third-party cookies, CHIPS/Partitioned, browser storage eviction**.
- Không thay browser security test khi làm web login, OAuth redirect, iframe hay CSRF.
- Không đánh giá role/authorization cho server.
- Không đảm bảo persistence qua JVM restart nếu dùng in-memory store.
- Không thay giới hạn memory/TTL cleanup, kiểm soát redirects và proxy settings.
- Không tự thêm các response attributes như SameSite vào `HttpCookie`.

Cookie jar có thể chứa credentials; tránh dump `manager.getCookieStore().getCookies()` vào application logs.

## 11. Java 17+ runnable: client/server loopback và phạm vi cookie

Chương trình `CookieManagerHttpClientDemo.java` thực thi integration flow không dùng Internet:

1. Tạo JDK `HttpServer` trên `127.0.0.1` port `0`.
2. `GET /login` trả `Set-Cookie: preference=blue; Path=/account; Max-Age=120; HttpOnly`.
3. Java `HttpClient.cookieHandler(manager)` tự lưu cookie.
4. `GET /account/profile` gửi lại cookie trong scope Path.
5. `GET /outside` không gửi cookie ngoài scope.
6. Tạo riêng một `Secure` cookie cho logical `https://api.example.com` qua `CookieManager.put`, kiểm tra `get(HTTPS)` cho cookie và `get(HTTP)` không cho cookie, **không kết nối Internet**.
7. Shutdown server và executor trong finally.

Cookie `preference` ở loopback HTTP chỉ nhằm kiểm thử Path, **không phải session/login production**. Không dùng một session secret thật qua HTTP.

### 11.1. File CookieManagerHttpClientDemo.java

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public final class CookieManagerHttpClientDemo {
    static void send(HttpExchange ex, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        ex.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    static boolean present(String name, Map<String, List<String>> headers) {
        return headers.getOrDefault("Cookie", List.of()).stream()
                .anyMatch(value -> value.contains(name + "="));
    }

    static void check(boolean test, String why) {
        if (!test) throw new AssertionError(why);
    }

    public static void main(String[] args) throws Exception {
        CookieManager manager = new CookieManager(
                null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 16);
        server.createContext("/login", ex -> {
            try (ex) {
                ex.getResponseHeaders().add("Set-Cookie",
                        "preference=blue; Path=/account; Max-Age=120; HttpOnly");
                send(ex, "created");
            }
        });
        server.createContext("/account", ex -> {
            try (ex) {
                send(ex, ex.getRequestHeaders()
                        .getFirst("Cookie") == null ? "missing" : "received");
            }
        });
        server.createContext("/outside", ex -> {
            try (ex) {
                send(ex, ex.getRequestHeaders()
                        .getFirst("Cookie") == null ? "missing" : "received");
            }
        });
        server.setExecutor(workers);
        server.start();
        try {
            String origin = "http://127.0.0.1:" + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .cookieHandler(manager)
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();
            HttpResponse<String> login = client.send(
                    HttpRequest.newBuilder(URI.create(origin + "/login"))
                            .timeout(Duration.ofSeconds(5)).GET().build(),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            check(login.statusCode() == 200, "login");
            check(manager.getCookieStore().getCookies().size() == 1, "stored");

            HttpResponse<String> inScope = client.send(
                    HttpRequest.newBuilder(URI.create(origin + "/account/profile"))
                            .timeout(Duration.ofSeconds(5)).GET().build(),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            HttpResponse<String> outside = client.send(
                    HttpRequest.newBuilder(URI.create(origin + "/outside"))
                            .timeout(Duration.ofSeconds(5)).GET().build(),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            check("received".equals(inScope.body()), "in-scope cookie");
            check("missing".equals(outside.body()), "out-of-scope cookie");

            manager.put(URI.create("https://api.example.com/login"),
                    Map.of("Set-Cookie", List.of(
                            "session=secret; Path=/; Max-Age=120; Secure; HttpOnly")));
            check(present("session", manager.get(
                    URI.create("https://api.example.com/account"), Map.of())),
                    "HTTPS secure cookie");
            check(!present("session", manager.get(
                    URI.create("http://api.example.com/account"), Map.of())),
                    "HTTP must not receive Secure cookie");

            System.out.println("cookie-stored=" + (manager.getCookieStore().getCookies().size() == 2));
            System.out.println("account-path-received=" + inScope.body().equals("received"));
            System.out.println("other-path-received=" + outside.body().equals("received"));
            System.out.println("secure-over-https=true");
            System.out.println("secure-over-http=false");
            System.out.println("tests=PASS");
        } finally {
            server.stop(1);
            workers.shutdown();
            if (!workers.awaitTermination(5, TimeUnit.SECONDS)) workers.shutdownNow();
        }
    }
}
~~~

### 11.2. Biên dịch/chạy

Vì chương trình dùng `com.sun.net.httpserver.HttpServer`, dùng module `jdk.httpserver`:

~~~bash
javac -encoding UTF-8 --release 17 --add-modules jdk.httpserver CookieManagerHttpClientDemo.java
java --add-modules jdk.httpserver CookieManagerHttpClientDemo
~~~

Stdout **chính xác**, chạy thành công trên OpenJDK 24:

~~~text
cookie-stored=true
account-path-received=true
other-path-received=false
secure-over-https=true
secure-over-http=false
tests=PASS
~~~

**Diễn giải:** CookieManager đã lưu hai cookies của hai origins trong fixture; `/account/profile` được gửi preference cookie, `/outside` không nhận; cookie Secure chỉ được `CookieManager.get` chọn cho URI HTTPS. Test HTTPS chỉ thực thi cookie-filter trong memory, **không gửi request ra api.example.com**. Không dùng kết quả này thay browser SameSite/third-party tests.

### 11.3. HttpServer cần phát Set-Cookie, không phải Cookie

Response ở `/login` dùng `ex.getResponseHeaders().add("Set-Cookie", "...")`. Với hai cookie values, phải `add` hai lần thay vì `set` đè lẫn nhau. Không đưa string từ request không tin cậy vào header. Với dữ liệu nhạy cảm, HTTPS là bắt buộc; demo localhost HTTP chỉ học phương thức truyền/nhận cookies.

## 12. Quy trình session an toàn trong ứng dụng thật

### 12.1. Login

Một ứng dụng web dùng cookie session thường:

1. Nhận login qua HTTPS, xác thực user/MFA theo policy.
2. Sinh session token bằng `SecureRandom` với đủ entropy, mã hóa an toàn trong cookie value.
3. Lưu session server-side (user ID, issuedAt, expiresAt, idle timeout, revokedAt, scopes).
4. Phát `Set-Cookie` với tên/prefix phù hợp, **không Domain** nếu không cần subdomains, `Path=/` cho host-level session, **Secure**, **HttpOnly**, **SameSite=Lax/Strict**, `Max-Age` có giới hạn.
5. Rotate token sau login, privilege elevation, password reset hoặc các event nhạy cảm để giảm session fixation.
6. Không log token hoặc đặt trong URL, metrics labels, browser-accessible content.
7. Kết hợp TLS/HSTS, CSRF protection, XSS prevention và authorization từng request.

### 12.2. Mỗi request

- Đọc cookie value, nhưng coi nó là dữ liệu client-controlled.
- Tra trong session store, xác minh not-expired, not-revoked, đúng tenant/user.
- Kiểm tra quyền trên action/resource cụ thể; token hợp lệ **không** tự có mọi quyền.
- Gia hạn session có kiểm soát nếu dùng sliding expiration, vẫn có absolute expiry.
- Giám sát credential stuffing/replay/rate limits và bảo vệ logs.
- Nếu cookie thiếu hoặc sai, trả status auth phù hợp; đừng trả các thông tin nhạy cảm.

### 12.3. Logout

- Revoke session token trên server.
- Phát deletion Set-Cookie có **cùng name, Domain và Path scope** cùng `Max-Age=0`.
- Nếu có nhiều cookies cùng tên khác path/domain, xử lý tất cả bằng chính sách rõ.
- Test rằng token cũ bị từ chối **dù client vẫn cố gửi Cookie header**.
- Quản lý logout toàn thiết bị, refresh token families và credential rotation nếu business yêu cầu.

### 12.4. Có cần stateless cookie/JWT không?

Một signed/encrypted stateless cookie cần các biện pháp riêng về key rotation, replay, issuer/audience, expiration, revocation, size limits và thuật toán ký. **HttpCookie chỉ biểu diễn metadata HTTP**, không ký hoặc mã hóa giá trị. Không tự biến name=value thành authorization vì client có thể sửa nó.

## 13. Các lỗi phổ biến

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `HttpCookie.toString()` như Set-Cookie | Mất Secure/Path/Max-Age/SameSite | Dùng builder có policy |
| Đặt Domain cho mọi session | Chia sẻ rộng với subdomains | Host-only khi có thể |
| Dùng `Domain=*` | Không phải wildcard hợp lệ | Domain cụ thể, nhỏ nhất |
| Coi `Path` là quyền truy cập | Dẫn đến authorization bugs | Validate quyền ở backend |
| `Path=/account` và logout `Path=/` | Có thể còn cookie cũ | Match đúng scope |
| Đặt Secure nhưng server dùng HTTP | Không bảo mật traffic/logic | HTTPS bắt buộc |
| Quên Secure cho session | Có thể gửi credentials qua HTTP | Secure + TLS/HSTS |
| Quên HttpOnly cho token | JavaScript có thể đọc token | HttpOnly + XSS defenses |
| Coi HttpOnly là CSRF defense | JS vẫn có thể gửi requests | CSRF tokens/Origin |
| SameSite=None thiếu Secure | Browser từ chối hoặc không dùng | SameSite=None; Secure |
| Viết `cookie.setSameSite(...)` | HttpCookie không có method | Framework Set-Cookie |
| Coi Max-Age là milliseconds | Expiry sai nghiêm trọng | Max-Age tính **giây** |
| Coi getMaxAge là số giây còn lại | Logic TTL sai | Server `expiresAt` |
| Tin browser session close luôn xóa cookie | Session restore có thể giữ | Server expiry/revocation |
| Chỉ xóa client cookie khi logout | Token cũ còn valid | Revoke ở server |
| Ghép nhiều Set-Cookie bởi dấu phẩy | Expires parse sai | Header riêng từng cookie |
| Cho user input vào header | Header injection | ASCII allowlist/escaping |
| Token từ timestamp/Random | Dễ đoán | SecureRandom đủ entropy |
| Log Cookie header | Lộ session | Redaction/omit |
| Dùng CookiePolicy.ACCEPT_ALL mặc định | Nhận cookies quá rộng | ACCEPT_ORIGINAL_SERVER |
| Tin CookieManager y hệt browser | SameSite/Partitioned khác | Browser integration tests |
| Cookie jar ghi ra disk plaintext | Credential disclosure | Secure storage/retention |
| Cookie duplicate same name different scope | Server chọn sai session | Đặt naming/scope rõ |

## 14. Checklist kiểm thử

| Tình huống | Kỳ vọng |
| --- | --- |
| Host-only cookie | Không bị gửi tới subdomain khác |
| Domain=example.com | Có thể được gửi tới subdomains hợp lệ |
| Domain không phù hợp origin | Bị browser từ chối |
| Domain là public suffix | Bị browser từ chối theo policy |
| Path=/account | Match /account/profile |
| Path=/account | Không match /accountant hoặc /outside |
| Path omitted | Browser dùng default directory |
| Secure trên HTTPS | Được gửi nếu các ràng buộc khác phù hợp |
| Secure trên HTTP | Không gửi, ngoại trừ local browser exceptions riêng |
| HttpOnly | Không đọc được qua document.cookie |
| SameSite Lax/Strict/None | Behavior đúng cross-site context |
| SameSite=None thiếu Secure | Bị browser từ chối |
| __Host- thiếu Secure/Path=/ | Bị browser hỗ trợ prefix từ chối |
| __Host- khai báo Domain | Bị browser từ chối |
| Max-Age và Expires cùng có | Max-Age được ưu tiên |
| Max-Age=0 | Cookie đúng scope bị xóa |
| Không Max-Age/Expires | Session cookie, server TTL vẫn áp dụng |
| Session restore | Không bỏ qua server expiration |
| CookieManager+HttpClient | Cookie jar tự attach scope phù hợp |
| Header injection | Name/value không an toàn bị từ chối |
| Multiple Set-Cookie | Không mất cookie nào |
| Logout | Server revoke và client deletion |
| Expired/revoked session manual replay | Backend vẫn từ chối |
| Java JDK upgrade | Behavior parser/policy đúng test |
| Browser differences | Test Chromium/Firefox/WebKit thực tế |
| Logs | Cookie/token không bị ghi ra |

### 14.1. Không coi bài test Java là browser conformance suite

CookieManager là một HTTP cookie handler của Java, không phải full browser. Khi làm ứng dụng web, phải kiểm thử thực tế `SameSite`, public-suffix, cookie prefixes, partitioning, third-party flows, OAuth redirects, logout và mobile webviews. Những browser behaviors có thể đổi theo version/feature flags; kiểm tra theo môi trường deploy hiện tại.

### 14.2. Cookie an toàn không có nghĩa session an toàn

Ngay cả Set-Cookie đúng Secure/HttpOnly/SameSite vẫn cần **server-side TTL, identity/session fixation prevention, CSRF, XSS controls và authorization**. Bảo mật không chỉ nằm ở những chuỗi trong HTTP header.

## 15. Câu hỏi tự đánh giá

**1.** `Set-Cookie` khác `Cookie` thế nào?

**Đáp án:** Set-Cookie ở response và chứa attributes; Cookie ở request chứa các cặp name=value.

**2.** Cookie không có Domain có được gửi cho mọi subdomain?

**Đáp án:** Không, browser dùng host-only scope.

**3.** `Domain=example.com` có nguy cơ gì?

**Đáp án:** Phạm vi mở rộng tới subdomains phù hợp, tăng attack surface nếu một subdomain không tin cậy.

**4.** `Path=/account` có match `/accountant` không?

**Đáp án:** Không, vì ranh giới path segments.

**5.** Path có thay authorization không?

**Đáp án:** Không, server phải kiểm tra identity và quyền.

**6.** Secure có tự tạo HTTPS không?

**Đáp án:** Không. Nó là attribute về cookie sending; backend phải cung cấp TLS đúng.

**7.** HttpOnly có ngăn mọi request JavaScript không?

**Đáp án:** Không, nó ngăn JS đọc cookie trực tiếp, không ngăn browser gửi cookie theo request policy.

**8.** SameSite=None phải kèm gì?

**Đáp án:** Secure và HTTPS thực tế.

**9.** HttpCookie có setSameSite và setPartitioned không?

**Đáp án:** Không có các setters đó trong Java SE 26.

**10.** `Max-Age=60` có nghĩa một phút hay 60 ngày?

**Đáp án:** 60 giây.

**11.** Khi có Max-Age và Expires, cái nào ưu tiên?

**Đáp án:** Max-Age.

**12.** getMaxAge() có đếm ngược không?

**Đáp án:** Không, trả giá trị lifetime đã đặt/tính.

**13.** Max-Age=-1 mặc định có bảo đảm user đóng tab là logout?

**Đáp án:** Không; browser session restore và server policy độc lập.

**14.** Tại sao không dùng HttpCookie.toString để tạo Set-Cookie?

**Đáp án:** Theo Javadoc đó là cookie header representation, không phải response header chứa đầy đủ attributes.

**15.** CookieManager có thay server-side session store không?

**Đáp án:** Không. Nó chỉ quản lý cookies trong Java client.

**16.** Cookie bị xóa ở client, server có cần revoke token không?

**Đáp án:** Có, nếu token có thể còn bị replay/đánh cắp.

### Bài tập

1. Chạy cả hai Java programs; đối chiếu stdout thực tế.
2. Thay `Max-Age=120` thành 3600 trong parse header, xác nhận precedence với Expires.
3. Đổi `setMaxAge(1800)` thành 0 rồi gọi `hasExpired()`.
4. Thay `Domain=shop.example.com` bằng một parent domain, giải thích browser scope khác nhau.
5. Đổi `Path=/account` thành `/` trong CookieManager demo và dự đoán `/outside`.
6. Thử `/accountant` để tìm hiểu path segment boundary và test thêm với browser.
7. Thêm kiểm tra token name/value có CR/LF/semicolon, phải bị builder từ chối.
8. Tạo session token bằng SecureRandom+Base64URL và không in nó ra log.
9. Thêm Set-Cookie thứ hai trên HTTP server; kiểm tra CookieStore.
10. Thêm logout endpoint xóa đúng cookie name/path với Max-Age=0 và revoke server state.
11. Xây bộ integration tests HTTPS thật cho Secure và __Host- prefix.
12. Kiểm thử SameSite=Lax/Strict/None qua browser cross-site flows.
13. Viết backend session store có idle timeout và absolute expiry.
14. Thử client gửi Cookie header chứa token đã revoke; đảm bảo backend trả 401/403 phù hợp.
15. Thử Java CookieManager qua HTTP redirects với policy chặt, không dùng ACCEPT_ALL.
16. Benchmark CookieStore lớn và đo cleanup/memory.
17. So sánh Java17/Java26 Javadoc và browser hiện hành để tránh thiết kế dựa vào RFC 2965 cũ.

## 16. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — HttpCookie](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/HttpCookie.html): constructors, parse, domain/path/secure, HttpOnly, Max-Age/Expires/hasExpired và toString.
- [Oracle Java SE 26 — CookieManager](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieManager.html): client cookie management.
- [Oracle Java SE 26 — CookieStore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieStore.html): lưu và lấy cookies, expired cookies.
- [Oracle Java SE 26 — CookiePolicy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookiePolicy.html): ACCEPT_ORIGINAL_SERVER, ACCEPT_NONE, ACCEPT_ALL.
- [Oracle Java SE 26 — CookieHandler](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieHandler.html): get/put hooks.
- [Oracle Java SE 26 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `cookieHandler` per-client.
- [Oracle Java SE 26 — HttpServer](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): JDK HTTP server demo.
- [Oracle Java SE 26 — HttpExchange](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): response headers.
- [Oracle Java SE 26 — SecureRandom](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/SecureRandom.html): tạo session token.
- [Oracle Java SE 26 — Base64](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Base64.html): URL-safe encoding.
- [Oracle Java SE 17 — HttpCookie](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpCookie.html): target Java17.
- [IETF RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265.html): domain/path/Max-Age/Expires/Secure và HTTP cookie semantics.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): SameSite, __Host- prefix, Partitioned.
- [MDN — Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies): browser cookie behavior.
- [MDN — Secure cookie configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies): cookie security recommendations.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): server session security.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): state-changing requests.

**Ghi nhớ:** `HttpCookie` của Java **vẫn hiện hành** nhưng không phải một browser. **Không Domain** là hướng host-only; **Path** là scope gửi, không phải authorization; **Secure** cần HTTPS thực tế; **HttpOnly** giảm nguy cơ script đọc token; **SameSite** phải được thêm qua framework/header builder, không phải bằng method `HttpCookie.setSameSite`. **Max-Age được ưu tiên hơn Expires**, `getMaxAge()` không đếm ngược, `Max-Age=0` xóa cookie đúng scope. `HttpCookie.toString()` **không phải đầy đủ Set-Cookie**, và client cookie lifetime **không thay thế server-side session expiration/revocation**.
