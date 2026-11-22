# Chuyển hướng sang máy đích khác và giới hạn chia sẻ thông tin xác thực

## 1. Vấn đề cốt lõi: chuyển hướng HTTP có thể đổi người nhận bí mật

Một Java HTTP client gọi `https://api.example.com/v1/orders` và kèm `Authorization: Bearer ...`, cookie phiên đăng nhập hoặc header chứa API key. Server trả `302 Location: https://files.example.net/new-path`. Nếu client tự chuyển hướng, **request tiếp theo có thể đến một máy chủ khác**, sử dụng hostname, port, chứng chỉ TLS và phạm vi xác thực khác. Việc máy chủ thứ nhất đã được tin cậy **không tự cấp quyền** cho máy chủ mới được nhận token của máy chủ thứ nhất.

Bài học thuộc nhóm **Proxy và phiên HTTP**: cần phân biệt ba loại danh tính — **origin server**, **proxy** và **phiên/cookie của người dùng** — rồi giới hạn việc chia sẻ thông tin xác thực theo đúng đối tượng. Java `java.net.http.HttpClient` có chính sách chuyển hướng `NEVER`, `NORMAL`, `ALWAYS`, nhưng **đó không phải toàn bộ cơ chế kiểm soát bí mật**.

Sau bài học, bạn phải:
1. Giải thích chuyển hướng sang hostname khác, port khác hoặc scheme khác làm thay đổi **origin** và có thể làm thay đổi **protection space**.
2. Phân biệt header `Authorization`, `Proxy-Authorization`, `Cookie` và các header tùy biến như `X-Api-Key`.
3. Biết Java 17 `HttpClient.Redirect.NORMAL` chặn HTTPS → HTTP nhưng **không phải allowlist hostname**.
4. Hiểu vì sao không nên mặc định tin client sẽ tự loại mọi header chứa bí mật khi theo `Location`.
5. Dùng `Redirect.NEVER` và kiểm tra URI trước khi tạo request tiếp theo, chỉ thêm credential khi đích được phép.
6. Nhận diện rủi ro cross-host redirect, SSRF, cross-origin auth leaks, replay POST body và session confusion.
7. Tự chạy hai chương trình Java 17+ trên loopback: một chương trình **quan sát behavior tự động** và một chương trình **ngăn gửi token sang origin khác**.

**Nguyên tắc cốt lõi:** Chỉ gửi credential cho **đích mà credential đó được cấp quyền sử dụng**. Redirect từ một server không phải sự đồng ý của chủ sở hữu token để chuyển token sang server khác.

## 2. Một chuỗi chuyển hướng có thể thay đổi cả host, port và scheme

Ví dụ:

```http
GET /account HTTP/1.1
Host: api.example.com
Authorization: Bearer <token-for-api.example.com>

HTTP/1.1 302 Found
Location: https://partner.example.net/account
```

Nếu tự follow, request tiếp theo có thể đến:

```http
GET /account HTTP/1.1
Host: partner.example.net
```

Dòng `Authorization` **không nên** được tự động sao chép chỉ vì request đầu có nó; token ban đầu có thể được cấp riêng cho `api.example.com`. Trong ví dụ, giá trị góc nhọn là placeholder mang tính giải thích, không phải token thật.

Các kiểu chuyển hướng:

| Source → Target | Thay đổi đáng chú ý | Kết luận về quyền chia sẻ token |
| --- | --- | --- |
| `https://api.example.com/a` → `https://api.example.com/b` | Cùng scheme, host, port mặc định | Có thể cùng origin, nhưng còn phạm vi realm/path/ứng dụng |
| `https://api.example.com/a` → `https://cdn.example.com/b` | Đổi hostname | Khác origin, **không tự chuyển token origin A** |
| `https://api.example.com/a` → `https://api.example.com:8443/b` | Đổi port | Khác origin, không coi credential mặc định dùng chung |
| `https://api.example.com/a` → `http://api.example.com/b` | Hạ HTTPS → HTTP | Mất TLS bảo vệ trên hop mới, **không gửi secrets** |
| `http://api.example.com/a` → `https://api.example.com/b` | Nâng HTTP → HTTPS | Vẫn đổi origin; HTTPS mới không tự cho phép gửi lại token |
| `https://api.example.com/a` → `https://api.example.com.evil.test/b` | Host khác dù có prefix tương tự | Không tin theo prefix string |
| `https://api.example.com/a` → `https://user@api.example.com/b` | Có URI userinfo | Cần từ chối/có chính sách rõ, tránh nhầm host/credential |

Điều kiện “cùng hostname” yếu hơn “cùng origin”, và **cùng origin** lại không đồng nghĩa “mọi credential được phép dùng cho mọi tài nguyên”. Authentication realm, endpoint permissions, resource scope và token audience còn là các lớp chính sách độc lập.

## 3. Origin gồm scheme + host + port

Trong HTTP, **origin** thường được xác định bởi bộ:

```text
origin = (scheme, host, effective port)

https://api.example.com/v1      => (https, api.example.com, 443)
https://api.example.com:443/v2  => (https, api.example.com, 443)
https://api.example.com:8443/v2 => (https, api.example.com, 8443)
http://api.example.com/v2       => (http, api.example.com, 80)
https://files.example.com/v2    => (https, files.example.com, 443)
```

Ở đây **effective port** là port khai báo, nếu URI không ghi port thì mặc định là 443 cho HTTPS và 80 cho HTTP. Phần path, query và fragment **không tạo origin mới**, nhưng vẫn có ý nghĩa cho **resource-level authorization**.

Vì sao port quan trọng? Hai dịch vụ cùng host trên 443 và 8443 có thể do hai team khác nhau quản lý. Việc DNS trả về cùng IP cũng không khiến hai URL trở thành một origin. Trái lại, `localhost` và `127.0.0.1` có thể trỏ về cùng máy nhưng **khác hostname** khi so sánh origin.

Để làm bài kiểm thử offline, chương trình ở phần sau dùng hai server loopback và địa chỉ nguồn `127.0.0.1`, đích `localhost`. **Không gọi môi trường đó là hai máy vật lý khác nhau**: đây là hai **hostname/origin khác nhau** mô phỏng redirect cross-host mà không gửi token ra Internet.

### Origin khác protection space

HTTP Basic/Digest authentication có khái niệm **protection space**: phạm vi thường kết hợp **origin** với **realm**, có thể còn quy tắc chi tiết của từng authentication scheme. Token OAuth/Bearer còn có audience, scope, expiration và resource server policy.

Vì vậy:
- Cùng origin nhưng đổi realm hoặc endpoint có thể không được dùng lại credential.
- Khác origin phải được xem là đích mới, trừ khi issuer/ứng dụng thiết kế rõ credential hợp lệ cho cả hai.
- **Không** quyết định reuse token bằng cách so sánh host prefix hoặc DNS IP trùng nhau.

## 4. Chuyển hướng hoạt động ra sao trong Java HttpClient?

Java SE 17 `HttpClient.Redirect` có ba lựa chọn:

| Policy | Automatic follow | HTTPS → HTTP | Có kiểm tra host allowlist không? |
| --- | --- | --- | --- |
| `NEVER` | Không | Không tự theo | **Không**, nhưng app được quyền kiểm tra thủ công |
| `NORMAL` | Có thể theo 3xx hợp lệ | **Không** | **Không tự biến thành allowlist** |
| `ALWAYS` | Có thể theo 3xx hợp lệ | Có thể theo | **Không** |

`HttpClient.newHttpClient()` mặc định là `Redirect.NEVER`. Chọn `NORMAL` khi muốn auto-follow mà tránh một dạng downgrade. Tuy nhiên `NORMAL` **có thể đi từ HTTPS hostname A sang HTTPS hostname B**, khi response `Location` hợp lệ và client quyết định follow. Dùng TLS hợp lệ với hostname B **không** chứng minh token được cấp cho A có quyền xuất hiện tại B.

Ví dụ cấu hình:

```java
HttpClient automatic = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

HttpClient controlled = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

Đây là **mảnh code**, import `java.net.http.HttpClient`. `NORMAL` chỉ nêu cách follow về cơ bản. `NEVER` phù hợp khi ứng dụng cần kiểm tra toàn bộ chuỗi redirect **trước khi** gửi byte tiếp theo.

### Không nhầm redirect với proxy forwarding

Một client có thể sử dụng **proxy** cho kết nối tới origin; response `302` vẫn có ý nghĩa chuyển URI đích của logical HTTP request. Proxy routing, proxy authentication và origin authentication là ba việc cần xem riêng. Một `ProxySelector` có thể chọn proxy khác cho target URI mới. Không lấy proxy credential dành cho proxy P1 để gửi thẳng tới origin B hoặc proxy P2.

## 5. Các loại bí mật không được coi là một

| Header/dữ liệu | Người nhận hợp lệ | Quy tắc cần nhớ |
| --- | --- | --- |
| `Authorization: Bearer ...` | **Origin resource server** đúng audience/scope | Không copy sang origin khác nếu chưa có quyết định bảo mật |
| `Authorization: Basic ...` | Protection space/realm tương ứng của origin | Basic chỉ mã hóa Base64, cần TLS và đúng scope |
| `Proxy-Authorization: ...` | **Proxy** mà client đang xác thực | Không gửi như origin credential, không đưa sang proxy lạ |
| `Cookie: session=...` | Các request khớp domain/path/secure policy của cookie jar | Cookie scope khác origin; cần CookieHandler/cookie policy đúng |
| `X-Api-Key: ...` | API/service được cấp key | **Chỉ là header tùy biến** đối với generic HTTP implementation |
| `X-Auth-Token: ...` | Service được phép | Không giả định thư viện biết đây là bí mật |
| URL query như `?token=...` | Nếu thiết kế cho phép, chỉ endpoint chính xác | Dễ rò qua logs/redirect/history; tránh đặt token trong URL |
| mTLS client certificate/private key | TLS endpoint/service được cấu hình rõ | Không xem mTLS là quyền chia sẻ Bearer token với mọi host |

**Điểm thực hành quan trọng:** Thư viện HTTP có thể có quy tắc nội bộ xử lý các header chuẩn như `Authorization` và `Cookie`, nhưng nó **không thể biết** tên `X-Api-Key` hoặc `X-Internal-Secret` mang giá trị nhạy cảm theo nghiệp vụ. Đừng dùng “header không tên Authorization” để lách chính sách; nó có thể bị tự chuyển tiếp.

Ngay cả khi đã xóa `Authorization`, còn cần xem các loại bí mật khác: cookie được tái phát từ cookie jar, custom API key, signed query strings, body của POST và application-generated headers.

## 6. RFC 9110 khuyến nghị điều gì khi tự redirect?

RFC 9110, mục về **redirection**, nêu những thay đổi user agent nên thực hiện khi tự gửi request mới theo `Location`:

1. Thay target URI bằng URI từ `Location` sau khi resolve tương đối với request URI trước đó.
2. Xóa/điều chỉnh các header do **implementation tự sinh** và có thể không còn phù hợp ở đích mới: connection-specific headers, proxy-specific headers (ví dụ `Proxy-Authorization`), origin-specific headers (ví dụ `Host`), cache validators và resource-specific headers (ví dụ `Authorization`/`Cookie` khi tự sinh).
3. **Cân nhắc xóa cả các header do caller chủ động thêm** nếu có rủi ro bảo mật, gồm `Authorization` và `Cookie`.
4. Điều chỉnh method khi status redirect yêu cầu; nếu đổi sang GET/HEAD, bỏ các content-specific headers không còn phù hợp.
5. Phát hiện vòng lặp redirect và can thiệp thay vì follow vô hạn.

Ở đây **SHOULD** là mức khuyến nghị trong chuẩn, **không phải cam kết** mọi thư viện/JDK sẽ xóa mọi custom header cho mọi đường redirect. Chuẩn không định nghĩa ý nghĩa của `X-Api-Key` như một phần bắt buộc phải tự loại.

**Hậu quả bảo mật:** App phải **tự thiết lập chính sách chia sẻ credential**. Auto-follow tiện lợi nhưng không phải ranh giới tin cậy đầy đủ. Một policy an toàn có thể là: mặc định **không theo cross-origin redirect**, hoặc chỉ theo sau khi đích nằm trong allowlist và cấp **credential dành riêng cho đích đó**.

## 7. Java 17 test: quan sát header nào đi theo redirect sang hostname khác

Chương trình đầu tiên tạo hai HTTP server **chỉ trên loopback**:
- Server nguồn nhận `/jump` ở `127.0.0.1:<port A>`.
- Nó trả `302 Location: http://localhost:<port B>/receive`.
- Server đích nhận request và chỉ trả về **cờ có/không có header**, không in giá trị bí mật.
- Request ban đầu có các giá trị giả `Bearer fake-example-only`, `sid=fake`, `X-Api-Key: fake-key`.
- Client `NEVER` và `NORMAL` được chạy riêng để so sánh.

Lưu vào file **`CrossHostRedirectObservation.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

public class CrossHostRedirectObservation {
    private static void respond(HttpExchange e, int code, String body)
            throws IOException {
        byte[] b = body.getBytes(StandardCharsets.UTF_8);
        e.sendResponseHeaders(code, b.length);
        try (var out = e.getResponseBody()) { out.write(b); }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer target = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        AtomicInteger targetHits = new AtomicInteger();
        target.createContext("/receive", e -> {
            targetHits.incrementAndGet();
            respond(e, 200, "auth=" + (e.getRequestHeaders().getFirst("Authorization") != null)
                    + ",cookie=" + (e.getRequestHeaders().getFirst("Cookie") != null)
                    + ",apiKey=" + (e.getRequestHeaders().getFirst("X-Api-Key") != null));
        });
        target.start();

        HttpServer source = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        int targetPort = target.getAddress().getPort();
        source.createContext("/jump", e -> {
            e.getResponseHeaders().add(
                    "Location", "http://localhost:" + targetPort + "/receive");
            respond(e, 302, "Moved");
        });
        source.start();

        try {
            URI from = URI.create("http://127.0.0.1:"
                    + source.getAddress().getPort() + "/jump");
            HttpRequest request = HttpRequest.newBuilder(from)
                    .header("Authorization", "Bearer fake-example-only")
                    .header("Cookie", "sid=fake")
                    .header("X-Api-Key", "fake-key").GET().build();
            HttpResponse<String> never = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NEVER).build()
                    .send(request, HttpResponse.BodyHandlers.ofString());
            System.out.println("NEVER status=" + never.statusCode()
                    + " targetHits=" + targetHits.get());
            HttpResponse<String> normal = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NORMAL).build()
                    .send(request, HttpResponse.BodyHandlers.ofString());
            System.out.println("NORMAL status=" + normal.statusCode()
                    + " finalHost=" + normal.uri().getHost()
                    + " body=" + normal.body());
            System.out.println("targetHits=" + targetHits.get());
        } finally {
            source.stop(0);
            target.stop(0);
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac CrossHostRedirectObservation.java
java CrossHostRedirectObservation
```

**Stdout đã kiểm chứng trên môi trường JDK 17 API của bài:**

```text
NEVER status=302 targetHits=0
NORMAL status=200 finalHost=localhost body=auth=false,cookie=false,apiKey=true
targetHits=1
```

### Đọc kết quả mà không suy diễn sai

- `NEVER status=302 targetHits=0`: không có request follow tự động tới target.
- `NORMAL status=200 finalHost=localhost`: client đã tự theo `Location` sang hostname khác và nhận response thành công.
- `auth=false,cookie=false`: trong **implementation/JDK build được kiểm thử**, `Authorization` và `Cookie` tự thêm từ request **không được gửi sang đích cross-host**.
- `apiKey=true`: trong cùng bài kiểm thử, **custom header `X-Api-Key` vẫn xuất hiện ở đích mới**.
- `targetHits=1`: đích nhận một request sau khi chạy `NORMAL`.

**Giới hạn phải nhớ:** Đây là **kết quả quan sát một phiên bản/implementation cụ thể**, không phải API contract bảo đảm mọi JDK/HTTP library sẽ xóa chính xác các header ấy ở mọi tình huống. Việc auth/cookie đã bị loại trong test **không tạo cơ sở** để cho phép tự redirect mọi URL chứa secret. Custom header được phát hiện đi theo request là đủ để chứng minh một giả định “client tự biết loại mọi bí mật” không an toàn.

**Đừng chạy ví dụ với credential thật.** Nó cố tình gửi dummy `X-Api-Key` đến hostname khác để kiểm thử. Toàn bộ server đều bind local loopback; không có Internet. Địa chỉ `localhost` phải resolve về IPv4 `127.0.0.1` trong môi trường thử nghiệm; nếu hệ thống ưu tiên IPv6 `::1` mà listener chỉ bind IPv4, kết nối có thể không thành công. Khi cần test độc lập IPv6, hãy cấu hình hostname/address phù hợp.

## 8. Vì sao custom header nguy hiểm hơn tên chuẩn?

HttpClient nhìn thấy header:
- `Authorization` có semantics rõ trong HTTP authentication.
- `Cookie` được biết là cơ chế phiên HTTP, nhiều clients có chính sách riêng.
- `X-Api-Key` chỉ là một chuỗi tên header theo extension; API không thể biết nó là bí mật nếu không có cấu hình nghiệp vụ.

Một hệ thống có thể dùng:
- `X-Api-Key` cho REST API key.
- `X-Session-Token` cho bearer token riêng.
- `X-Internal-Signature` cho chữ ký theo request.
- `X-Tenant-Secret` cho secret đa tenant.
- `X-User-JWT` cho JWT.
- `X-Correlation-ID` cho ID không nhạy cảm.

Không thể suy rằng mọi header bắt đầu bằng `X-` đều phải xóa: có những header chỉ mang metadata công khai. Nhưng **default bảo thủ** khi đổi origin là **không sao chép bất kỳ caller-provided header nào** trừ danh sách đã phân loại và được phép gửi cho đích mới. Cần đánh giá riêng `Accept`/`User-Agent` (thường ít nhạy cảm) và các header có thể tiết lộ tenant, user identity, địa chỉ nội bộ hoặc dữ liệu bí mật.

Một whitelist header để sao chép, xây dựng **ở application layer**, an toàn hơn blacklist chỉ gồm `Authorization`/`Cookie` vì blacklist dễ bỏ sót tên custom secret mới được bổ sung sau này.

## 9. Quy tắc cùng origin chưa đủ cho mọi authentication scheme

Giả sử cùng origin `https://api.example.com`:
- `/public` cho phép anonymous.
- `/admin` cần credential có role quản trị.
- `/billing` cần token audience/scope hóa đơn.
- `/tenant/A` và `/tenant/B` có thể bị tách tenant.

Một token truy cập `/billing` **không đương nhiên hợp lệ** để gửi tới `/admin`, dù cùng scheme/host/port. HTTP `realm` hoặc OAuth token audience/scope phải được áp dụng. **Origin comparison** chỉ là một ranh giới tối thiểu hữu ích cho redirect, không phải **authorization decision** đầy đủ.

Với Basic auth: server có thể gửi `401 WWW-Authenticate: Basic realm="zone-a"`. Những tài nguyên khác trong realm có thể chia sẻ credential theo luật của authentication scheme. Nếu chuyển host hoặc realm mới, client không được tự suy rằng username/password ban đầu luôn đúng hoặc được phép dùng.

Với OAuth 2.0/Bearer: cấp **access token cho resource server đúng audience**; kiểm tra scope/permissions, expiration và token binding nếu có. Không tái sử dụng token của service A cho service B chỉ vì hai service cùng thuộc một tổ chức.

## 10. Tách 401 của origin khỏi 407 của proxy

Trong kiến trúc có HTTP proxy:

```text
Java HttpClient
   │
   │  Credentials dành cho proxy P nếu P yêu cầu
   ▼
Proxy P ──────────────────► Origin A
   │                            │
   │                            ├── 401 WWW-Authenticate
   │                            │      client -> Authorization tới origin A
   │                            │
   └── 407 Proxy-Authenticate
          client -> Proxy-Authorization tới proxy P
```

| Thành phần | Thách thức | Header credential | Giới hạn chia sẻ |
| --- | --- | --- | --- |
| **Origin server** | `401 Unauthorized` + `WWW-Authenticate` | `Authorization` | Theo origin, realm và authentication policy |
| **HTTP proxy** | `407 Proxy Authentication Required` + `Proxy-Authenticate` | `Proxy-Authorization` | Theo proxy/protection space của proxy |
| **Cookie session** | `Set-Cookie` từ origin; client gửi lại `Cookie` khi phù hợp | `Cookie` | Theo cookie domain/path/Secure và cookie policy |

**Không bao giờ** lấy credential trả `407` cho proxy rồi chèn vào `Authorization` gửi tới origin. Cũng không copy bearer token của origin vào `Proxy-Authorization`. Hai loại thông tin xác thực có người nhận khác nhau.

Trong Java, `HttpClient.Builder.proxy(ProxySelector)` chọn cách sử dụng proxy, còn `HttpClient.Builder.authenticator(Authenticator)` có thể cung cấp credential cho challenge phù hợp. Việc chọn proxy có thể thay đổi giữa các target URIs sau redirect; ứng dụng không được **gắn cứng** một proxy password cho mọi kết nối sau khi origin thay đổi.

### HTTPS qua proxy

Với HTTP proxy và HTTPS target, client thường dùng `CONNECT` để tạo tunnel tới origin rồi thực hiện TLS tới origin qua tunnel. Proxy credential xác thực proxy; TLS certificate của origin vẫn phải được kiểm tra theo đúng hostname đích. Proxy có thể quan sát đích CONNECT và metadata mạng; nếu môi trường có TLS inspection do tổ chức cấu hình, khả năng quan sát có thể khác. Không coi proxy là một origin được phép đọc token ứng dụng chỉ vì nó chuyển tiếp request.

## 11. Cookie phiên có phạm vi riêng, không đồng nhất với origin

Cookie có cấu trúc thường gặp:

```http
Set-Cookie: sid=example-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

Các thuộc tính:
- **Domain**: nếu không khai báo, cookie thường host-only; nếu có `Domain=example.com`, có thể áp dụng tới những subdomains phù hợp theo cookie rules.
- **Path**: giới hạn những request paths đủ điều kiện nhận cookie; không phải biện pháp cô lập bảo mật mạnh bằng origin.
- **Secure**: yêu cầu gửi cookie qua secure transport phù hợp; không có nghĩa được gửi tới mọi HTTPS hostname.
- **HttpOnly**: hạn chế việc truy cập cookie qua scripting APIs trong môi trường hỗ trợ; không chặn HTTP client gửi cookie khi hợp lệ.
- **SameSite**: thuộc tính quan trọng cho browser cross-site request context; **đừng giả định** Java `CookieManager` thực thi toàn bộ cùng bộ quy tắc như browser hiện đại.

**Cookie scope có thể rộng hơn origin về port/subdomain.** Ví dụ cookie cho `example.com` có thể được gửi tới dịch vụ khác thuộc subdomain phù hợp dù origin không trùng. Cookie domain/path/Secure vì thế phải được xem xét riêng khi client theo redirect.

### Java CookieHandler

`HttpClient.Builder.cookieHandler(CookieHandler)` cho phép dùng một cookie handler, thường là `CookieManager` để lưu `Set-Cookie` và cung cấp cookie cho các request phù hợp với policy. Khi có redirect, cookie jar có thể quyết định **cookie nào đúng phạm vi của đích mới**, không nhất thiết chuyển y nguyên header `Cookie` do caller tự thêm.

Ví dụ tạo cookie manager, **mảnh code không độc lập**:

```java
CookieManager cookies = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookies)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

Imports `java.net.CookieManager`, `CookiePolicy` và `java.net.http.HttpClient`. Policy `ACCEPT_ORIGINAL_SERVER` không thay cho việc review session design; đặc biệt khi nhiều tenants/auth contexts dùng chung client/cookie jar, phải tách cookie stores hoặc quản lý scope rõ.

**Không đặt cùng một shared CookieManager cho người dùng độc lập** nếu cookie sessions cần tách biệt. Pool/concurrency tái sử dụng connections không tương đương phép dùng chung user session.

## 12. Một đích HTTPS khác vẫn có thể nhận dữ liệu sai

Câu nói “chuyển sang HTTPS thì vẫn an toàn” là thiếu điều kiện.

```text
https://api.example.com/private
       │ 302 Location
       ▼
https://evil.example/collect
```

Certificate của `evil.example` có thể hoàn toàn hợp lệ cho chính hostname ấy. TLS bảo vệ **kết nối tới evil.example**, không xác nhận rằng **evil.example được cấp quyền nhận token của api.example.com**.

Phải tách:
1. **Transport authentication:** TLS đã xác thực server đúng với **tên host mà client định kết nối**.
2. **Application authorization:** Server đó có được nhận credential, dữ liệu, request body và hành động của user **hay không**?

TLS thành công chỉ giải quyết một phần thứ nhất. Khi redirect chuyển host, phải kiểm tra chính sách thứ hai bằng allowlist và token scoping.

### HTTPS → HTTP downgrade

`Redirect.NORMAL` chặn automatic redirect từ HTTPS sang HTTP; `Redirect.ALWAYS` không chặn theo policy đó. Gửi Authorization, cookies hoặc body nhạy cảm qua HTTP plaintext có thể tiết lộ chúng trên đường truyền. Với các API có secrets, **cấm downgrade** ngay cả khi đang làm manual redirect, trừ khi có yêu cầu đặc biệt được kiểm soát và không có dữ liệu nhạy cảm.

## 13. Redirect có thể chuyển POST body và method

Không chỉ headers có thể rò rỉ; một request mang **body chứa PII, dữ liệu tài chính, key, upload** cũng có nguy cơ được gửi tới đích mới.

| Status | Ngữ nghĩa thường gặp | Rủi ro cần kiểm tra |
| --- | --- | --- |
| `301 Moved Permanently` | Redirect dài hạn | Java HttpClient có thể đổi POST → GET; URL/headers vẫn cần kiểm soát |
| `302 Found` | Redirect tạm theo lịch sử | Java HttpClient có thể đổi POST → GET; đích có thể đổi host |
| `303 See Other` | Đọc kết quả từ URI khác (thường GET) | Có thể chuyển method, không nên copy content headers vô ý |
| `307 Temporary Redirect` | Giữ method và body semantics | **POST/upload body có thể bị gửi lại sang host khác** |
| `308 Permanent Redirect` | Giữ method và body semantics | **Body được replay**, cần kiểm tra idempotency và quyền đích |

Trong Java 17, `HttpClient.Redirect` nêu rõ 301/302 làm POST chuyển thành GET khi auto-follow. Còn 307/308 có mục đích bảo toàn method; nếu body publisher không phát lại được, operation có thể lỗi. Không dựa vào bảng này để suy rằng mọi HTTP library đều xử lý giống nhau trong mọi tình huống.

Khi làm manual redirect với request có side effects:
- Không tự replay `POST` sang target khác chỉ vì status là 307/308.
- Kiểm tra token/audience, body replayability và quyền của destination.
- Dùng idempotency key và retry policy nếu server hỗ trợ.
- Nếu không có yêu cầu rõ, từ chối cross-origin redirect đối với write operations.

## 14. Ví dụ Java 17+ an toàn: chỉ theo redirect khi cùng origin

Chương trình thứ hai mô phỏng:
- Server **origin A** ở `127.0.0.1:<port A>`.
- `/to-same` trả `302 Location: /same`; URI mới có **cùng origin**. Client tái cấp một dummy token cho request mới sau khi validate.
- `/to-other` trả `302 Location: http://localhost:<port B>/landing`; URI mới có **khác host/port**. Client **không gửi request** tới server B.
- `HttpClient` sử dụng `Redirect.NEVER`, nên **không có automatic follow** ngoài quyền kiểm soát của ứng dụng.

Chương trình chỉ thực hiện **một redirect hop** và không cho phép gửi ra Internet. Giá trị token là dummy, không chứa secret thật.

Lưu đúng file **`ScopedRedirectDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

public class ScopedRedirectDemo {
    private static void reply(HttpExchange e, int code, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        e.sendResponseHeaders(code, bytes.length);
        try (var out = e.getResponseBody()) { out.write(bytes); }
    }

    private static int effectivePort(URI uri) {
        if (uri.getPort() >= 0) return uri.getPort();
        if ("https".equalsIgnoreCase(uri.getScheme())) return 443;
        if ("http".equalsIgnoreCase(uri.getScheme())) return 80;
        return -1;
    }

    private static boolean sameOrigin(URI a, URI b) {
        return a.getHost() != null && b.getHost() != null
                && a.getScheme() != null && b.getScheme() != null
                && a.getScheme().equalsIgnoreCase(b.getScheme())
                && a.getHost().equalsIgnoreCase(b.getHost())
                && effectivePort(a) == effectivePort(b)
                && b.getRawUserInfo() == null
                && b.getRawFragment() == null;
    }

    private static HttpResponse<String> oneHop(
            HttpClient client, URI from, String token) throws Exception {
        HttpRequest first = HttpRequest.newBuilder(from)
                .header("Authorization", "Bearer " + token)
                .timeout(Duration.ofSeconds(5)).GET().build();
        HttpResponse<Void> initial = client.send(first,
                HttpResponse.BodyHandlers.discarding());
        if (initial.statusCode() != 302) {
            throw new IOException("Expected a 302 for this demo");
        }
        String location = initial.headers().firstValue("Location")
                .orElseThrow(() -> new IOException("No Location"));
        URI next = initial.uri().resolve(location);
        if (!sameOrigin(from, next)) {
            System.out.println("cross-target-allowed=false");
            return null;
        }
        System.out.println("same-target=" + next.getPath());
        HttpRequest second = HttpRequest.newBuilder(next)
                .header("Authorization", "Bearer " + token)
                .timeout(Duration.ofSeconds(5)).GET().build();
        return client.send(second, HttpResponse.BodyHandlers.ofString());
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        AtomicInteger targetHits = new AtomicInteger();
        HttpServer external = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        external.createContext("/landing", e -> {
            targetHits.incrementAndGet();
            reply(e, 200, "external");
        });
        external.start();
        HttpServer origin = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        origin.createContext("/to-same", e -> {
            e.getResponseHeaders().add("Location", "/same");
            reply(e, 302, "redirect");
        });
        origin.createContext("/same", e -> reply(e, 200,
                "auth=" + (e.getRequestHeaders().getFirst("Authorization") != null)));
        origin.createContext("/to-other", e -> {
            e.getResponseHeaders().add("Location", "http://localhost:"
                    + external.getAddress().getPort() + "/landing");
            reply(e, 302, "redirect");
        });
        origin.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();
            URI base = URI.create("http://127.0.0.1:"
                    + origin.getAddress().getPort());
            HttpResponse<String> same = oneHop(
                    client, base.resolve("/to-same"), "fake-local-only");
            System.out.println("same-response=" + same.statusCode()
                    + "," + same.body());
            oneHop(client, base.resolve("/to-other"), "fake-local-only");
            System.out.println("target-hits=" + targetHits.get());
        } finally {
            origin.stop(0);
            external.stop(0);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ScopedRedirectDemo.java
java ScopedRedirectDemo
```

Stdout đã kiểm chứng với Java 17:

```text
same-target=/same
same-response=200,auth=true
cross-target-allowed=false
target-hits=0
```

### Giải thích từng bước

1. `HttpClient.Redirect.NEVER` đảm bảo lần `send` đầu **không auto-follow**; trả `302` để ứng dụng kiểm tra.
2. `Location` được resolve tương đối với `initial.uri()`. Ví dụ `/same` nằm cùng origin.
3. `sameOrigin(...)` so sánh **scheme, hostname, effective port**, đồng thời reject URI có userinfo hoặc fragment. Dùng `equalsIgnoreCase` cho hostname/scheme theo semantics phổ biến.
4. Nếu cùng origin, chương trình **tự tạo request thứ hai** và **tự thêm** dummy Authorization cho origin đã được xác nhận, không copy toàn bộ headers.
5. Với `Location` tới `localhost:<port B>`, `sameOrigin(...)` trả false vì hostname/port khác. Chương trình không gọi `send` lần thứ hai, nên server B có `target-hits=0`.
6. Hai server được bind loopback và dừng trong `finally`.

### Đây chưa phải bộ chống SSRF production hoàn chỉnh

Hàm `sameOrigin` trong demo là **một điều kiện tối thiểu cho bài tập**. Để triển khai network client có thể nhận URL tùy ý từ bên ngoài, cần bổ sung:
- Bắt buộc HTTPS và valid certificate/hostname cho production.
- Allowlist hostname/port/service ID có quản trị; so sánh với **origin ban đầu được phép**, không chỉ origin của hop trước.
- Định nghĩa credential đúng realm/audience/path; cùng origin chưa đủ.
- Kiểm soát DNS resolution, IP range/egress, chống DNS rebinding/TOCTOU bằng network-level policy.
- Giới hạn số hop, tổng thời gian, kích thước response, request methods và request bodies.
- Quản lý origin khác được chấp thuận với **token riêng cho origin đó**.
- Tách proxy credentials/cookie jars của các phiên/tenants khác nhau.

Mã demo **không** chặn mọi đường khai thác URL trong môi trường Internet phức tạp; nó minh họa rõ nơi **phải đặt quyết định** trước khi chuyển credentials sang đích khác.

## 15. Manual redirect với nhiều hop: kiểm tra mọi bước

Một server có thể trả:

```text
api.example.com/old
   └─ 302 → api.example.com/current
               └─ 307 → partner.example.net/upload
                           └─ 200
```

Nếu chỉ kiểm tra hop đầu rồi bật auto-follow cho request kế tiếp, app vẫn có thể đến partner. Cần kiểm tra **từng redirect hop**.

Quy trình khái niệm:

```text
originalAllowedOrigin = origin mà ứng dụng được phép gọi
currentUri = initialUri
redirectCount = 0

loop:
  validate currentUri, network destination, scheme và policy
  choose credentials *for currentUri*, not for the previous host
  send exactly one HTTP request using Redirect.NEVER
  if response không phải redirect được hỗ trợ:
      return response
  extract Location; reject nếu thiếu hoặc sai cú pháp
  nextUri = response.uri().resolve(Location)
  validate nextUri AGAIN against originalAllowedOrigin/allowlist
  decide method/body replay and safe headers for next hop
  if redirectCount exceeds max: abort
  currentUri = nextUri
```

Đây là **pseudocode**, không phải Java hoàn chỉnh. Điểm thiết kế:
- `Redirect.NEVER` giữ quyền quyết định ở application.
- Chỉ tạo request tiếp theo sau khi URI đã được **resolve và validate**.
- Không lấy toàn bộ headers từ initiating request rồi áp cho mọi hop.
- Mỗi hop có timeout, deadline và audit metadata.
- Nếu cần chuyển từ A sang B mà cả hai đều được cho phép, cấp **credentials được phê duyệt riêng cho B**, không tái dùng A theo suy đoán.
- Đối với POST/PUT/PATCH, kiểm tra request body và idempotency trước resend.

**Không** chỉ kiểm tra target hostname bằng `endsWith("example.com")`: `notexample.com` và các biến thể internationalized domain/punycode, trailing dots và host normalization có thể khiến kiểm tra chuỗi đơn giản sai. Dùng parse URI chuẩn và allowlist dữ liệu chuẩn hóa, kết hợp các ràng buộc mạng.

## 16. Vì sao so sánh host không đủ để ngăn SSRF?

Open redirect có thể được dùng để khiến server-side Java client gọi tới:
- `127.0.0.1`/`localhost`, các dịch vụ quản trị cục bộ.
- Dải RFC 1918/private IPv4, unique-local IPv6.
- Link-local `169.254.0.0/16` hoặc `fe80::/10`.
- Cloud instance metadata endpoints.
- Nội bộ Kubernetes/service mesh mà ứng dụng không được phép truy cập.
- Một domain do attacker điều khiển và trỏ về IP nội bộ sau DNS rebinding.

Nếu Java process có network access rộng, redirect từ một URL công khai có thể trở thành **SSRF** dù body không mang token. Với token/headers, SSRF còn có nguy cơ làm lộ credential.

Lớp bảo vệ:
1. Không follow redirects tự động khi đầu vào URL không tin cậy.
2. Allowlist scheme, hostname, port và protocol; reject userinfo/fragment khi không cần.
3. Resolve DNS qua cơ chế được kiểm soát và đảm bảo **địa chỉ thực sự được kết nối** không vượt policy. Chỉ gọi `InetAddress.getAllByName()` trước `HttpClient.send` chưa giải quyết hoàn toàn DNS rebinding/time-of-check/time-of-use.
4. Dùng egress firewall, service identity/mTLS và proxy rules ở tầng hạ tầng.
5. Phân tách quyền network và credential theo service/tenant.
6. Giới hạn redirects, timeout, response bytes và connection count.

**Cấm chuyển credential sang origin không được phép** chỉ là một lớp; còn phải chặn việc **gửi request đến đích nội bộ không được phép** ngay cả khi request không kèm bí mật.

## 17. ProxySelector, Authenticator và token scope

Java `HttpClient.Builder` có các cấu hình:

```java
HttpClient client = HttpClient.newBuilder()
        .proxy(proxySelector)
        .authenticator(authenticator)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

Đây là **mảnh code**, cần cung cấp `ProxySelector proxySelector` và `Authenticator authenticator` cùng imports. `ProxySelector` quyết định proxy cho các URIs theo chính sách; `Authenticator` trả credential theo challenge/context (ví dụ requestor type PROXY hoặc SERVER). Không nên có một `Authenticator` trả cùng username/password cho **mọi hostname và mọi loại requestor**.

Khi implement `Authenticator`:
- Kiểm tra `getRequestorType()` để phân biệt `PROXY` với `SERVER`.
- Đối với `SERVER`, kiểm tra protocol/host/port/realm/authentication scheme đúng allowlist; không trả password của service A khi service B yêu cầu `401`.
- Đối với `PROXY`, xác nhận proxy address/port/realm đúng thiết lập; không đưa proxy credential cho server origin.
- Không lưu mật khẩu trong string literal/log/source repository.
- Không suy rằng mọi dạng Bearer token sẽ được `Authenticator` tự quản lý. `HttpClient` built-in của Java có các giới hạn authentication scheme; ứng dụng dùng custom Bearer header cần policy riêng.

Một số cấu hình bảo mật của JDK có thể hạn chế Basic authentication qua proxy tunnel theo properties. Đừng gỡ bỏ policy nhằm gửi password qua nơi chưa được bảo vệ; cấu hình proxy và scheme phải được xác minh qua tài liệu runtime thực dùng.

### Tại sao proxy auth có thể thay đổi sau redirect?

Target URL mới có thể có scheme, hostname, port khác; `ProxySelector` có thể chọn **proxy khác hoặc kết nối trực tiếp**. Nếu app tùy tiện sao chép `Proxy-Authorization` từ request cũ sang request mới, nó có thể đưa credential proxy P1 tới sai đối tượng. Hãy để framework xử lý challenge/proxy state và kiểm tra cấu hình `Authenticator` đúng scope.

## 18. Cookie/session fixation và phân tách người dùng

Một `HttpClient` có thể tái sử dụng giữa nhiều request, nhưng nếu chứa chung `CookieManager` của **nhiều người dùng độc lập** thì cookie của user A có thể đi cùng request của user B khi host/path trùng phạm vi. Redirect có thể làm lỗi đó rõ hơn khi chuyển qua một origin có cookie jar chung.

Đối với ứng dụng đa tenant:
- Có **cookie jar riêng theo user/session/security principal** hoặc chọn kiến trúc không dùng cookie tự động trong backend.
- Không đưa cookie session của user A vào request do user B khởi tạo.
- Phân biệt application session ID với HTTP connection reuse; hai khái niệm **không đồng nhất**.
- Cookie `Domain` quá rộng có thể giúp subdomain không tin cậy nhận cookie. Đánh giá các miền có khả năng kiểm soát độc lập.
- Đặt `Secure`/`HttpOnly`/`SameSite` hợp lý ở phía web, nhưng **không** giả định Java CookieManager y hệt trình duyệt.

Một chủ đề liên quan là **session fixation**: nếu một origin không đáng tin có thể điều khiển session identifier được client sử dụng, ứng dụng có thể bị ràng buộc vào phiên không mong muốn. Việc giới hạn redirect và chia sẻ cookie theo phạm vi đúng làm giảm một số đường tấn công, nhưng vẫn cần server-side session rotation, binding và authorization checks.

## 19. Location không phải bằng chứng đích được tin

`Location` là **dữ liệu do response server cung cấp**. Nó có thể là:

```http
Location: /new
Location: https://cdn.example.net/file
Location: //partner.example.org/upload
Location: https://api.example.com:8443/next
Location: http://127.0.0.1:8080/admin
```

Các dạng này không tương đương nhau:
- `/new` là absolute path, khi resolve thông thường vẫn cùng origin.
- `https://cdn.example.net/file` đổi hostname.
- `//partner.example.org/upload` thừa hưởng scheme nhưng **đổi authority/host**.
- `:8443` đổi port, làm origin thay đổi.
- `http://127.0.0.1:8080` có thể dẫn tới đích cục bộ không được phép.

Với manual redirect, dùng `response.uri().resolve(location)` rồi kiểm tra URI đã resolve. **Không nối URL bằng string**; không lấy `Location` làm chuỗi “đáng tin” vì nó xuất hiện trong một TLS-authenticated response. TLS chỉ xác thực source server, không biến mọi đường dẫn source đề xuất thành destination được phép nhận dữ liệu.

### Query strings và fragments

Query có thể chứa mã truy cập/signed URLs; redirect có thể gây rò qua log hoặc đích khác. Fragment thường không được gửi tới origin trong HTTP request-target, nhưng có ý nghĩa trong việc resolve URI và chính sách ứng dụng. Demo reject `getRawFragment()!=null` để scope đơn giản. Trong production, quyết định fragment policy theo protocol nhưng không sử dụng fragments như cơ chế giữ bí mật.

## 20. Không tự sao chép mọi header khi xây redirected request

Cách **không nên** làm:

```java
HttpRequest.Builder next = HttpRequest.newBuilder(targetUri);
// SAI về thiết kế: copy tất cả headers từ request cũ,
// rồi tiếp tục gửi mà không thẩm định scope từng header.
originalRequest.headers().map().forEach(
        (name, values) -> values.forEach(
                value -> next.header(name, value)));
```

Đây là **mảnh code phản ví dụ**, phụ thuộc `targetUri`, `originalRequest` và imports, **không chạy độc lập**. Nó có thể chép Authorization, Cookie, X-Api-Key, X-Tenant, signed authorization hoặc các headers đặc thù tới origin khác. Một số header bị Java HTTP implementation hạn chế cũng có thể khiến chương trình lỗi.

Một policy an toàn hơn:

```text
Target được allowlist và đúng identity?
  Không -> reject, không send

Nếu được phép:
  - Xây một HttpRequest mới từ URI đã kiểm tra.
  - Chỉ thêm header thực sự cần và được phép cho target.
  - Chọn đúng credential cấp cho target, không copy token cũ theo mặc định.
  - Chọn method/body theo status semantics và replay policy.
  - Dùng cookie store đúng user + scope, không copy Cookie thủ công.
  - Không copy Proxy-Authorization; để proxy/auth framework quản lý.
```

**Chiến lược tốt:** **rebuild from minimal trusted inputs** thay vì **copy then delete secrets**. Blacklist có thể bỏ sót một tên header bí mật do team khác thêm sau này.

## 21. Quy tắc tự động của client khác quy tắc bảo mật ứng dụng

Các thư viện HTTP có thể chọn xóa hoặc giữ headers theo nhiều điều kiện:
- Đổi hostname.
- Đổi port.
- HTTPS → HTTP.
- Có `Authenticator` hoặc `CookieHandler`.
- Header được sinh bởi client hay **do application tự set**.
- Authentication challenge `401/407`, proxy routing.
- Version của JDK và implementation.

Vì vậy tránh hai khẳng định quá mức:
- **“Java HttpClient luôn copy Authorization khi redirect sang host khác.”** Không đúng với môi trường Java 17 đã kiểm chứng.
- **“Java HttpClient luôn loại mọi thông tin xác thực khi redirect.”** Cũng không đúng; custom `X-Api-Key` trong thử nghiệm vẫn được chuyển.

Kết luận đúng: **application không được xem chính sách header forwarding ngầm định của HTTP library là giới hạn bảo mật đầy đủ**. Cần kiểm thử implementation cụ thể và áp dụng guardrail ở app/network.

Nếu framework khác như Apache HttpClient, OkHttp, curl, browser hoặc một phiên bản JDK mới được sử dụng, phải kiểm tra semantics của **client đó**. Kết quả local Java 17 trong bài không tự suy sang client khác.

## 22. Chuyển hướng cùng host nhưng khác port vẫn có vấn đề

Ví dụ:

```text
https://api.example.com/v1
    -> 302 Location: https://api.example.com:8443/admin
```

Vẫn là hostname `api.example.com`, nhưng đích mới có **port khác**, nên là **origin khác**. Có thể cổng 8443 là admin service do bộ phận khác vận hành. Đừng dùng điều kiện:

```java
boolean allowed = from.getHost().equalsIgnoreCase(next.getHost());
```

để quyết định cấp lại Authorization; điều kiện đó bỏ qua scheme/port. Demo `sameOrigin` ở mục 14 kiểm tra đủ ba thành phần.

Trong trường hợp cookie, các thuộc tính domain/path thường **không cô lập theo port**; đây là một lý do khác không nên coi cookie scope giống origin boundary. Nếu nhiều dịch vụ bảo mật khác nhau ở các port trên cùng host, cần thiết kế session/cookie scoping rất cẩn thận.

## 23. Chuyển hướng tới một proxy hoặc proxy mới không phải chuyển credential tùy ý

Một redirect thông thường chuyển **target URI**, không trực tiếp nói “gửi Proxy-Authorization đến proxy X”. Quyết định proxy được đưa ra bởi `ProxySelector` hoặc network configuration cho từng request. Sau redirect:
1. Target URI mới được resolve.
2. Client/proxy configuration chọn routing phù hợp.
3. Nếu proxy đòi xác thực, xử lý `407` và credential đúng proxy đó.
4. Nếu origin đòi xác thực, xử lý `401` và credential đúng origin.
5. Credential không được tái dùng ngang các protection spaces nếu không có policy hợp lệ.

Ví dụ:
- Request đầu `https://internal.example` đi qua proxy nội bộ P1.
- Redirect sang `https://partner.example.net` đi qua proxy P2 theo routing policy.
- Password dùng cho P1 **không** phải password mặc định cho P2 hoặc partner.

**Proxy-Authorization khác Authorization** cả về vị trí sử dụng lẫn đối tượng được cấp quyền. Khi dùng proxy authentication qua `Authenticator`, hãy xác định `RequestorType.PROXY` và các thuộc tính proxy được yêu cầu, không trả cùng password cho mọi challenge.

## 24. Logging và quan sát mà không lộ token

Khi điều tra redirect cross-host, nên log:
- Correlation/request ID (không chứa bí mật).
- Initial origin đã được chuẩn hóa, **không log userinfo/token**.
- Destination origin của từng hop.
- Status code của redirect và số hop.
- Policy (NEVER/NORMAL/ALWAYS hoặc manual).
- Quyết định allow/deny và lý do ở mức metadata.
- Có đổi scheme, hostname, port, proxy hay realm không.
- Chỉ tên category header cần quan sát, **không log giá trị** `Authorization`, `Cookie`, `X-Api-Key`.
- Timeout/network/cert/error metrics.

Ví dụ log an toàn:

```text
requestId=abc-123
hop=1
fromOrigin=https://api.example.com:443
toOrigin=https://cdn.example.net:443
redirectStatus=302
decision=DENY_CROSS_ORIGIN
credentialReused=false
```

Không log full URL nếu query/path có thông tin nhạy cảm, không ghi raw response headers có `Set-Cookie`/signed URLs, và không in API key vào stdout trong test. Hai chương trình demo chỉ trả cờ true/false nhằm minh họa tình trạng forwarding mà không tiết lộ dummy secret.

### Kiểm thử thực tế cần bảo vệ log

Nếu bật HTTP client debug logs hoặc dùng packet capture, hãy dùng môi trường test với dummy token. Cần nhớ HTTPS trên origin có thể bảo vệ dữ liệu giữa client và origin, nhưng proxy TLS inspection/CDN/edge có thể có khả năng xem request ở điểm terminate TLS hợp pháp. Đừng dùng credential production cho bài kiểm thử.

## 25. Kiểm thử regression cho an toàn redirect

| Kịch bản | Kỳ vọng bảo mật |
| --- | --- |
| Redirect same-origin/path hợp lệ | Có thể follow sau khi xác nhận resource-level credential scope |
| Redirect tới hostname khác chưa allowlist | **Không gửi request**, hoặc dừng trước khi cấp credential |
| Redirect cùng hostname nhưng port khác | Không mặc định chia sẻ token |
| HTTPS → HTTP | Không chuyển secrets, thông thường reject |
| HTTP → HTTPS host mới | Không mặc định chia sẻ token dù có TLS |
| `Location: //evil.example/path` | Resolve thành hostname khác rồi reject theo policy |
| `Location` bị thiếu/invalid | Không tự đoán target; báo lỗi |
| Cross-host response tiếp tục 302 về origin cũ | Không coi history an toàn nếu đã có hop chưa được phép |
| 307/308 với POST body nhạy cảm | Không tự replay sang đích không được phép |
| 302 POST → GET | Không chuyển các content-specific headers không phù hợp |
| Custom `X-Api-Key` trên original request | Không tự copy sang cross-origin; test chứng minh rule |
| Cookie jar chung của hai người dùng | Không chia sẻ session cookie giữa user contexts |
| Proxy thay đổi sau redirect | Không chuyển proxy credential của proxy cũ sang proxy mới |
| 401 origin vs 407 proxy | Credential đến đúng đối tượng, không hoán đổi headers |
| Host trỏ tới IP private/link-local | Policy egress chặn nếu app chỉ được truy cập public Internet |
| DNS rebinding giữa validation và connection | Network-level controls phải chặn connect trái phép |
| Redirect loop hàng trăm hop | Max redirects/deadline, không treo vô hạn |

Đối với mỗi test, kiểm tra **server đích có thực sự nhận request hay không**, không chỉ check final HTTP status. Trong bài demo manual, `target-hits=0` là bằng chứng thực tế rằng request tới origin không được phép **không được gửi**.

## 26. Lỗi phổ biến và cách sửa

1. **Chỉ kiểm tra scheme HTTPS.** TLS không quyết định resource server có quyền nhận token. Kiểm tra cả allowlist/credential audience.
2. **Chỉ so sánh hostname.** Bỏ sót đổi scheme và port; so sánh origin chuẩn hóa.
3. **Tin rằng `Redirect.NORMAL` ngăn cross-host.** NORMAL chủ yếu loại HTTPS → HTTP downgrade, **không** là danh sách máy đích được phép.
4. **Tin rằng `Redirect.ALWAYS` “bảo đảm kết nối thành công”.** Vẫn có các giới hạn/certificate errors và có thể downgrade nguy hiểm.
5. **Dùng một custom header `X-Api-Key` cho mọi request.** Header nghiệp vụ có thể được tự chuyển đến origin mới; gắn theo target.
6. **Copy mọi header bằng vòng lặp.** Có thể mang theo Authorization/Cookie/proxy token; rebuild từ whitelist.
7. **Tái dùng token OAuth của A cho B.** Audience/scope/issuer policies có thể không cho phép.
8. **Xem Basic realm là global credential.** Protection space có origin/realm; không áp password cho mọi server.
9. **Copy `Proxy-Authorization` khi follow.** Credential proxy không phải credential của origin.
10. **Dùng cùng CookieManager cho mọi user.** Có thể trộn session giữa tenants; cô lập cookie jar.
11. **Cho rằng cookies không liên quan vì Authorization đã bị xóa.** CookieHandler có thể tạo cookie riêng phù hợp với target.
12. **Bỏ qua 307/308.** Body POST có thể được gửi lại, không chỉ headers.
13. **Cho rằng 302 chỉ đổi path.** `Location` có thể là absolute URI, đổi host/port/scheme.
14. **Dùng host `endsWith(...)` không chuẩn hóa.** Dễ sai với domain suffix, IDN/punycode và tên tương tự.
15. **Chỉ validate DNS một lần.** DNS rebinding hoặc connection resolution khác validation gây TOCTOU; cần egress controls.
16. **Không giới hạn redirects.** Có thể loop, SSRF nhiều hop hoặc exhaustion.
17. **Không xem credential source.** Header do application tự thêm và header do client/authenticator tạo có thể được xử lý khác nhau.
18. **Log token để debug.** Dễ rò qua logs/APM/tracing; chỉ log thông tin allow/deny và status.
19. **Đặt token vào URI.** Query/userinfo có thể đi theo redirects, logs hoặc browser history.
20. **Thấy test Java17 loại Authorization rồi kết luận an toàn chung.** Implementation/headers khác có hành vi khác; bài test X-Api-Key cho thấy cần guardrail.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** `https://api.example.com/a` redirect sang `https://cdn.example.com/b`. Cùng HTTPS có nghĩa token được dùng lại không?  
**Đáp án:** Không. Hai URL khác hostname/origin. TLS certificate của CDN không chứng minh CDN có quyền nhận Bearer token cho API.

**Câu 2.** `https://api.example.com:443` và `https://api.example.com` có cùng origin không?  
**Đáp án:** Có, nếu hostname/scheme giống nhau, port explicit 443 và port HTTPS mặc định 443 tương đương. Vẫn phải kiểm tra realm/resource scope.

**Câu 3.** `https://api.example.com` redirect sang `https://api.example.com:8443`. Có thể mặc định chia sẻ Authorization không?  
**Đáp án:** Không; khác effective port nên khác origin.

**Câu 4.** `HttpClient.Redirect.NORMAL` chặn loại redirect nào rõ ràng trong Java 17 API?  
**Đáp án:** HTTPS → HTTP downgrade. Nó không ngăn mọi redirect cross-host.

**Câu 5.** Nếu test thấy `Authorization` bị loại trên cross-host, còn `X-Api-Key` thì sao?  
**Đáp án:** Không có bảo đảm thư viện biết tên header custom này chứa secret; bài test Java17 cho thấy nó đã được chuyển sang target.

**Câu 6.** `Proxy-Authorization` có cùng mục đích với `Authorization` không?  
**Đáp án:** Không. Proxy-Authorization dành cho proxy (thường sau 407); Authorization dành cho origin server (thường sau 401).

**Câu 7.** Cookie có được scoped chính xác theo origin tuple không?  
**Đáp án:** Không hoàn toàn. Cookie scope chủ yếu theo domain/path/Secure và rules khác; port không tạo cookie isolation giống origin, Java CookieManager có semantics riêng.

**Câu 8.** Vì sao `Redirect.NEVER` hữu ích cho bảo mật?  
**Đáp án:** Nó trả 3xx để app resolve/validate từng Location trước khi tạo request mới và quyết định credentials theo target.

**Câu 9.** `Location: //other.example.com/x` có thể bị hiểu nhầm là path cùng host?  
**Đáp án:** Có. Nó là network-path reference, có thể đổi hostname khi resolve.

**Câu 10.** Demo `ScopedRedirectDemo` kiểm tra đích khác origin thế nào?  
**Đáp án:** Nó so sánh scheme/host/effective port, không gửi request follow khi không khớp. `target-hits=0` chứng minh target không nhận request.

**Câu 11.** Dùng `X-Tenant-Id` chung cho nhiều tenants có thể rò trong redirect không?  
**Đáp án:** Có thể. Dù không phải credential chuẩn, nó vẫn có thể tiết lộ tenant hoặc điều khiển quyền truy cập; cần phân loại header và whitelist theo đích.

**Câu 12.** Nếu một server trả 307 sang storage host mới, có nên gửi lại POST body chứa tài liệu nội bộ?  
**Đáp án:** Chỉ khi storage target đã được cho phép, body/credential chính xác cho target và replay policy được phê duyệt. Mặc định an toàn là từ chối.

**Câu 13.** Dùng `InetAddress.getAllByName` để lọc IP rồi gọi `HttpClient.send` có hoàn toàn chặn SSRF không?  
**Đáp án:** Không. Resolution khi kết nối có thể khác lần kiểm tra; cần egress controls và cơ chế ràng buộc destination phù hợp.

**Câu 14.** HTTP 401 và 407 nên dẫn đến cấp credential cho ai?  
**Đáp án:** 401 + WWW-Authenticate là origin; 407 + Proxy-Authenticate là proxy; không hoán đổi.

**Câu 15.** Tại sao không dùng cùng cookie jar cho nhiều user sessions trong một Java backend?  
**Đáp án:** Cookie tự động có thể bị chia sẻ giữa các requests của người dùng khác nhau, gây session confusion và rò quyền.

## 28. Checklist vận hành

Khi thiết kế Java HTTP client có xác thực và khả năng redirect:
1. Dùng HTTPS đúng certificate/hostname cho toàn bộ destinations.
2. Xác định **origin và protection space** mà từng token/cookie/password thuộc về.
3. Chọn `Redirect.NEVER` nếu có yêu cầu cross-host/SSRF/credential scoping chặt.
4. Resolve và validate **từng Location** so với original allowlist.
5. Cấm HTTPS → HTTP downgrade với dữ liệu nhạy cảm.
6. Dùng cookie jar đúng user/session, không tự copy `Cookie` từ request cũ.
7. Tách proxy authentication khỏi origin authentication; `Authenticator` trả credential đúng requestor/realm.
8. Không copy `Authorization`/`X-Api-Key`/custom auth headers sang đích mới.
9. Nếu target được cho phép nhưng khác origin, cấp credential dành riêng cho target.
10. Kiểm tra POST/307/308 và replay/idempotency trước gửi lại body.
11. Áp deadline/max hops/max response size, chống redirect loop.
12. Dùng network egress rules để chặn địa chỉ nội bộ/metadata ngoài phạm vi.
13. Test auto-follow behavior của runtime thực dùng, nhưng **không dựa vào sự may mắn** của một implementation.
14. Log decisions/status/host đã sanitize, không log secrets.
15. Kiểm thử sau mỗi nâng cấp JDK, HTTP library, proxy, cookie handler hoặc auth scheme.

**Kết luận:** Redirect có thể đổi hostname, port, scheme và thậm chí proxy được chọn. Mỗi đích có ranh giới tin cậy riêng. Giới hạn chia sẻ thông tin xác thực phải được quyết định **ở tầng ứng dụng và hạ tầng**; chính sách auto-follow của `HttpClient` là một phần tiện ích, không phải cơ chế bảo vệ toàn diện cho mọi credential tùy biến.

## 29. Tài liệu chính thức và đối chiếu

- RFC 9110 — HTTP Semantics; redirection `15.4`, header handling và origin/protection space `11.5`, 401/407: https://www.rfc-editor.org/rfc/rfc9110
- Java SE 17 `HttpClient` — default Redirect.NEVER, send/sendAsync, proxy/authenticator integration: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17 `HttpClient.Redirect` — NEVER, NORMAL, ALWAYS: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html
- Java SE 17 `HttpClient.Builder` — followRedirects, proxy, authenticator, cookieHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- Java SE 17 `HttpResponse` — status, URI, headers và previousResponse: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Java SE 17 `ProxySelector` — cách lựa chọn proxy theo URI: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html
- Java SE 17 `Authenticator` — RequestorType PROXY/SERVER và credential challenge: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Authenticator.html
- Java SE 17 `CookieManager` và `CookiePolicy` — cookie store và acceptance policy: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html
- RFC 6265 — HTTP State Management Mechanism; cookie scope và attributes: https://www.rfc-editor.org/rfc/rfc6265
- OWASP — SSRF Prevention Cheat Sheet, redirect/DNS/egress validation: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
