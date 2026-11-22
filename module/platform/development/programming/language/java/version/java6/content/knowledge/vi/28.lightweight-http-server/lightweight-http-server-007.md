# Authenticator và quản lý danh tính theo nhu cầu với HTTP server gọn trong Java 17+

## 1. Vấn đề: endpoint nào cần xác thực, ai được làm gì?

Một ứng dụng Java nhỏ có thể dùng `com.sun.net.httpserver.HttpServer` để phục vụ endpoint kiểm tra sức khỏe, chạy công cụ nội bộ, nhận callbacks hoặc cung cấp API cho một nhóm dịch vụ. Không phải mọi endpoint có cùng chính sách truy cập:

- `/public` có thể công khai: không yêu cầu đăng nhập.
- `/me` cần biết người dùng đã xác thực: yêu cầu credentials hoặc token hợp lệ.
- `/admin` chỉ dành cho một nhóm người dùng có vai trò quản trị.
- `/token` có thể yêu cầu Bearer token thay vì HTTP Basic.
- Một tài khoản có thể bị khóa, bị thu hồi vai trò hoặc bị thu hồi token **sau khi server đã chạy**.

Java SE cung cấp API **`Authenticator`** và **`BasicAuthenticator`** trong module **`jdk.httpserver`**, package **`com.sun.net.httpserver`**. Đây là API công khai và vẫn được hỗ trợ trong JDK 17+ và Java SE 25, mặc dù tên package bắt đầu bằng `com.sun`. Nó **không phải** `java.net.Authenticator` dùng cho các kết nối HTTP **phía client**. Hai loại Authenticator có trách nhiệm khác nhau và không thay thế nhau.

**Chủ đề chính** của bài là **“Authenticator và quản lý danh tính theo nhu cầu”**: gắn bộ xác thực theo `HttpContext`, tạo `HttpPrincipal` đáng tin sau xác thực, giữ thông tin người dùng/vai trò ở một nguồn riêng, và áp dụng chính sách theo từng request.

Ba khái niệm cần tách rời:

1. **Authentication (xác thực):** thông tin đăng nhập/token có thuộc về một danh tính đã biết và đang hoạt động không?
2. **Identity (danh tính):** principal ổn định đại diện tài khoản nào? Tài khoản có bị vô hiệu hóa, xoay khóa, đổi tenant hay không?
3. **Authorization (phân quyền):** principal ấy được phép thực hiện hành động cụ thể trên tài nguyên này không?

Một server trả `200` chỉ vì username/password đúng là **chưa đủ** nếu endpoint yêu cầu role `admin`. Trái lại, tự đọc header `X-User: admin` từ client rồi tin rằng đó là danh tính đã xác thực là một lỗi nghiêm trọng: HTTP request header thông thường do client kiểm soát.

## 2. Vị trí API trong Java hiện đại

| API | Thuộc module | Vai trò |
| --- | --- | --- |
| `HttpServer` | `jdk.httpserver` | Khởi tạo, bind địa chỉ/port, lắng nghe HTTP |
| `HttpsServer` / `HttpsConfigurator` | `jdk.httpserver` | Phục vụ HTTPS nếu cấu hình TLS/SSLContext phù hợp |
| `HttpContext` | `jdk.httpserver` | Mapping đường dẫn tới handler, filters và authenticator |
| `HttpHandler` | `jdk.httpserver` | Xử lý request đã được context định tuyến |
| `HttpExchange` | `jdk.httpserver` | Request/response headers, body, method, URI, `getPrincipal()` |
| `Authenticator` | `jdk.httpserver` | Base class để kiểm tra thông tin xác thực của incoming requests |
| `BasicAuthenticator` | `jdk.httpserver` | HTTP Basic; override `checkCredentials` |
| `Authenticator.Success` | `jdk.httpserver` | Xác thực thành công kèm `HttpPrincipal` |
| `Authenticator.Retry` | `jdk.httpserver` | Cần client gửi credentials/challenge ở một request mới |
| `Authenticator.Failure` | `jdk.httpserver` | Thử xác thực đã thất bại |
| `HttpPrincipal` | `jdk.httpserver` | Danh tính dạng username và realm do Authenticator cấp |
| `HttpClient` | `java.net.http` | HTTP client chuẩn của Java để kiểm thử server |
| `SecretKeyFactory` | `java.base` | Ví dụ tạo password verifier PBKDF2 để không lưu plaintext |

`jdk.httpserver` là **JDK-specific module**, phù hợp server nhúng quy mô gọn, automation cục bộ và môi trường phát triển. Tài liệu Java SE 25 mô tả implementation mặc định là HTTP server **đơn giản**, không hướng tới full-featured/high-performance internet-facing platform. Không nên dùng một ví dụ auth 200 dòng như bộ thay thế mặc định cho identity provider, API gateway và application security của hệ thống lớn.

Nếu dùng JPMS module descriptor cho application riêng:

~~~java
module example.smallhttp {
    requires jdk.httpserver;
    requires java.net.http;
}
~~~

Đoạn `module-info.java` này chỉ minh họa dependencies của một **named module** có cả server và HTTP client. Chương trình hoàn chỉnh phía dưới chạy ở **classpath**, không cần module-info; lệnh `--add-modules jdk.httpserver` được ghi tường minh để làm rõ phụ thuộc server module.

### Không nhầm ba cơ chế auth

| Cơ chế | Dữ liệu nhận từ client | Ai kiểm tra? | Khi nên chọn |
| --- | --- | --- | --- |
| HTTP Basic | `Authorization: Basic ...` (Base64 username:password) | `BasicAuthenticator.checkCredentials` | Nội bộ/test hoặc một môi trường có TLS + policy quản lý mật khẩu |
| Opaque Bearer token | `Authorization: Bearer ...` | Custom `Authenticator` + trusted token store/introspection | API nhỏ, token ngẫu nhiên, có expiry/revocation |
| OAuth 2.0 / OIDC access token | Bearer token từ IdP, thường JWT hoặc opaque | Verified issuer/audience/signature/scopes/expiry từ gateway/SDK/IdP | Hệ thống nhiều dịch vụ, user federation/SSO, production |

**Không coi Base64 là mã hóa.** HTTP Basic gửi lại password ở mỗi request và phải chạy qua **HTTPS/TLS** khi truy cập bên ngoài một môi trường kiểm thử loopback được kiểm soát. Bearer token cũng là một bí mật: ai giữ token thường có thể sử dụng nó cho tới khi hết hạn/bị thu hồi; HTTPS, lưu trữ an toàn và scope giới hạn vẫn cần thiết.

## 3. `HttpContext.setAuthenticator`: bật auth theo tuyến

Một `HttpServer` có thể có nhiều contexts:

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 0), 0);

server.createContext("/public", publicHandler);

HttpContext me = server.createContext("/me", meHandler);
me.setAuthenticator(basicAuthenticator);

HttpContext admin = server.createContext("/admin", adminHandler);
admin.setAuthenticator(basicAuthenticator);

HttpContext token = server.createContext("/token", tokenHandler);
token.setAuthenticator(bearerAuthenticator);
~~~

Đây là đoạn **minh họa trong method**, cần handlers, authenticators, imports và `server.start()`/`stop()`; không phải file Java chạy độc lập. **`setAuthenticator` áp dụng cho một context**, không phải bật yêu cầu đăng nhập toàn server. Nếu một context không gắn authenticator, server không tự yêu cầu xác thực cho nó.

`HttpContext.setAuthenticator(auth)` trả về authenticator cũ. Đặt `null` sẽ bỏ cơ chế xác thực khỏi context — điều này có thể vô tình khiến endpoint thành **public**, nên cần kiểm tra khi sửa routing hoặc hot-reload cấu hình. Trên hệ thống thật, cấu hình endpoint/permission nên là **deny-by-default** và được audit/code-review.

### Prefix matching không phải exact route matching

`HttpServer` tìm context theo **longest matching prefix** của request URI path, không phải một router REST tự động chỉ match đường dẫn đầy đủ. Vì thế context `/admin` có thể nhận request `/admin-extra`.

Nếu handler chỉ dựa vào việc đã được chọn bởi context, application có thể xử lý sai route. Trong demo, handler xác nhận thêm:

~~~java
if (!"/admin".equals(exchange.getRequestURI().getPath())) {
    respond(exchange, 404, "Not found");
    return;
}
~~~

Đây là snippet trong handler, cần `respond` có sẵn. Nếu có route con `/admin/users`, hãy xây router có policy rõ cho các route con; đừng áp exact-match này một cách máy móc rồi chặn hết chức năng hợp lệ. Cần xét percent-encoding, path normalization, trailing slash và URL rewriting ở reverse proxy để tránh bypass, đặc biệt khi giao thức có path tương đương nhưng biểu diễn khác.

**Khi auth gắn vào context**, việc xác thực thường diễn ra trước khi handler của context được gọi. Vì vậy handler có thể đọc `HttpExchange.getPrincipal()` và áp authorization, nhưng không được bỏ kiểm tra nếu principal `null` hoặc tài khoản đã bị vô hiệu hóa.

## 4. Hợp đồng `Authenticator.authenticate(HttpExchange)`

Một custom Authenticator override:

~~~java
@Override
public Authenticator.Result authenticate(HttpExchange exchange) {
    // Kiểm tra thông tin xác thực; trả đúng loại Result.
}
~~~

Ba loại kết quả chính:

| Result | Diễn giải | Ví dụ |
| --- | --- | --- |
| `new Authenticator.Success(principal)` | Đã xác thực; đưa `HttpPrincipal` vào exchange cho handler | Token/credentials hợp lệ |
| `new Authenticator.Retry(401)` | Client cần gửi thông tin để thử lại; cần đặt response challenge headers thích hợp | Không có Authorization, trả `WWW-Authenticate` |
| `new Authenticator.Failure(401)` | Credentials được đưa ra nhưng không đạt kiểm tra | Token sai, password sai, account invalid |

Javadoc `Authenticator` phân biệt `Retry` với `Failure`. `Retry` không phải logic “server tự lặp request”: nó báo client cần một **HTTP exchange khác**, với status/header phù hợp đã được authenticator đặt vào `HttpExchange`. `Failure` thể hiện quá trình xác thực đã thất bại. Không trả `Success` cho anonymous user rồi kỳ vọng handler tự phân quyền đúng nếu security model không thiết kế anonymous identity tường minh.

### Phân biệt HTTP 401 và 403

| HTTP status | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **200 OK** | Authn và authz thành công, handler xử lý | User `linh` xem `/me` |
| **401 Unauthorized** | Chưa xác thực hoặc credential không hợp lệ, thường kèm `WWW-Authenticate` | Thiếu Basic, password sai, token bị thu hồi |
| **403 Forbidden** | Đã xác thực nhưng không có quyền thực hiện thao tác | User `minh` có role reader nhưng vào `/admin` |
| **404 Not Found** | Không có resource/route hợp lệ trong policy hiện tại | `/admin-extra` không phải endpoint được hỗ trợ |
| **405 Method Not Allowed** | Endpoint có nhưng HTTP method không hỗ trợ | POST đến endpoint chỉ nhận GET |
| **429 Too Many Requests** | Vượt giới hạn tốc độ hoặc số lần thử | Rate limit login/token validation theo policy |
| **503 Service Unavailable** | Nguồn xác thực/IdP bị lỗi hoặc không sẵn sàng | Fail closed, không cấp quyền theo fallback insecure |

HTTP `401 Unauthorized` có tên hơi dễ gây hiểu nhầm: trong mô hình bảo mật web nó liên quan **authentication challenge**, còn `403` liên quan **authorization denial**. Đừng gửi `403` cho mọi password sai và `401` cho một tài khoản đã đăng nhập nhưng không được phép admin khi không có lý do giao thức cụ thể.

### `HttpPrincipal` là dữ liệu đã được authenticator cấp

Sau thành công:

~~~java
HttpPrincipal principal = exchange.getPrincipal();
if (principal == null) {
    respond(exchange, 403, "No authenticated principal");
    return;
}
String username = principal.getUsername();
String realm = principal.getRealm();
~~~

Đây là snippet trong handler. `HttpPrincipal` chứa **username và realm**, không phải đối tượng chứa sẵn roles/scopes/tenant/user profile. `getPrincipal()` có thể trả `null` nếu context không có authenticator; do đó **không tự cho rằng mọi request đều được xác thực**.

**Không làm:**

~~~java
// Sai: client tự đặt được header này.
String user = exchange.getRequestHeaders().getFirst("X-User");
// Sai: dùng ngay user làm danh tính đã xác thực.
~~~

Nếu dùng một reverse proxy cung cấp header danh tính đã được kiểm chứng, cần **trusted proxy boundary** rất chặt: strip header từ client, giới hạn kết nối từ proxy, xác thực proxy→backend, và map claims an toàn. Không lấy ví dụ proxy tin cậy làm lý do chấp nhận bất kỳ `X-User` nào từ internet.

## 5. `BasicAuthenticator`: trường hợp đơn giản và các giới hạn

`BasicAuthenticator` là class abstract đã biết cú pháp HTTP Basic và challenge. Bạn chỉ cần override:

~~~java
BasicAuthenticator auth = new BasicAuthenticator(
        "internal-tools", StandardCharsets.UTF_8) {
    @Override
    public boolean checkCredentials(String username, String password) {
        return identities.checkPassword(username, password);
    }
};
~~~

Đây là snippet trong method, `identities` phải là một **credential verifier** thực sự và có imports. `BasicAuthenticator` được cung cấp từ Java 6; overload chọn `Charset` (như UTF-8) được hỗ trợ từ Java 14, phù hợp Java 17+. Javadoc hiện hành **khuyến nghị UTF-8** và có cơ chế thông báo charset cho client; tránh dùng platform-default charset để diễn giải username/password Unicode khi có thể chọn tường minh.

Client gửi:

~~~http
GET /me HTTP/1.1
Host: example.invalid
Authorization: Basic <base64(username:password)>
~~~

Đây chỉ là **sơ đồ HTTP request** để đọc cấu trúc; dấu `<base64(username:password)>` là placeholder biểu diễn giá trị chứ không phải credentials thật. Header Basic là bí mật; **đừng ghi raw Authorization vào log/tracing** hoặc đưa nó vào URL/query params.

### Realm dùng để làm gì?

`BasicAuthenticator("internal-tools", UTF_8)` dùng realm để hiển thị phạm vi bảo vệ và challenge, ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="internal-tools", charset="UTF-8"
~~~

Đây là dạng response minh họa theo Basic challenge; header cụ thể do server/provider tạo, không phải stdout của chương trình bên dưới. **Realm không phải một role** và không tự chứng minh tài khoản thuộc tenant hoặc được phép admin. Realm được trả về trong `HttpPrincipal.getRealm()`, nên không sử dụng thông tin realm do client tự tạo thay cho trust policy.

### Password validation không nên chỉ so plaintext

Đoạn:

~~~java
return "secret123".equals(password);
~~~

là **anti-pattern**, không phải cách lưu password production. Hệ thống cần lưu **password verifier có salt riêng theo user**, không lưu plaintext. Trong chương trình self-contained, ta dùng `PBKDF2WithHmacSHA256` của Java chuẩn, `SecureRandom` tạo salt và `MessageDigest.isEqual` so digest. **210.000 iterations trong demo chỉ để có thử nghiệm đủ rõ**, không phải con số chuẩn bảo mật hay cấu hình tối ưu hiện tại. Production cần áp work-factor được cập nhật theo threat model/OWASP và chi phí server, có thể ưu tiên **Argon2id** với thư viện được đánh giá nếu môi trường cho phép.

`checkCredentials(String, String)` nhận password đã là Java `String` do API xác định, nên **không thể xóa hoàn toàn bản gốc trong memory**; code chuyển sang `char[]` cho bước derivation rồi xóa bản tạm. Không được tuyên bố đây là cơ chế xóa sạch mọi bản sao secret. Cần TLS, rate limiting, credential rotation và bảo vệ bộ nhớ/logs ở mức hệ thống.

### Credentials được xác minh theo từng incoming request

`BasicAuthenticator` gọi `checkCredentials` cho request cần xác thực. Nó không tự biến HTTP Basic thành session lifecycle hoặc identity cache. Nếu muốn caching credential verification, ứng dụng phải tự thiết kế cache với lifetime/revocation và rủi ro bảo mật; thông thường không nên cache password plaintext, không giữ thông tin auth lâu hơn mức cần thiết. Password hashing đắt nhưng với traffic lớn cần chuyển sang **sessions hoặc scoped access tokens** do identity provider quản lý, thay vì PBKDF2 cho mọi API request.

## 6. Quản lý danh tính theo nhu cầu: user store, roles, disable và revoke

**IdentityStore** trong demo là một cấu trúc bất biến theo mỗi `Account` và dùng `ConcurrentHashMap` cho các cập nhật diễn ra khi server đang chạy:

~~~text
users["linh"] -> Account(
    salt, PBKDF2 password hash,
    roles = {"reader", "admin"},
    enabled = true
)

users["minh"] -> Account(
    salt, PBKDF2 password hash,
    roles = {"reader"},
    enabled = true
)
~~~

Tên và mật khẩu trong demo chỉ là test fixtures, **không phải một hệ thống account production**. Những thao tác quan trọng:

- `register`: tạo tài khoản test và password verifier.
- `checkPassword`: kiểm tra Basic credential + trạng thái enabled.
- `active`: kiểm tra tài khoản vẫn tồn tại/hoạt động.
- `hasRole`: kiểm tra role **tại thời điểm request**.
- `revokeRole`: cập nhật role set; request tiếp theo phải thấy quyền mới.
- `disable`: đánh dấu tài khoản disabled; Basic password dù đúng cũng không còn được chấp nhận.

Trong production, username hiển thị khác **account ID ổn định**; nên tránh collisions do Unicode normalization, case folding và đổi tên tài khoản. Với đa tenant, identity key thường là **(tenantId, subjectId)** hoặc một global opaque ID thay vì tên hiển thị `linh`. Nên kiểm tra vai trò theo **resource/tenant/action**, không phải chỉ một role toàn cục.

### Authentication khác Authorization trong handler

~~~java
HttpPrincipal p = exchange.getPrincipal();
if (p == null || !identities.active(p.getUsername())) {
    respond(exchange, 403, "Account inactive");
    return;
}
if (!identities.hasRole(p.getUsername(), "admin")) {
    respond(exchange, 403, "Forbidden");
    return;
}
respond(exchange, 200, "Allowed");
~~~

Đoạn này **nằm trong handler**, cần các helpers. Trong đường bình thường, disabled Basic user bị chặn **ở Authenticator** bằng `401`; kiểm tra `active` trong handler là defense in depth với **race** khi tài khoản bị disable ngay sau khi authn thành công nhưng trước khi handler chạy.

**Không** lấy role/permissions từ một custom header do client tự gửi. Nếu token chứa roles/scopes, phải verify chữ ký, issuer, audience, expiry và các điều kiện trust **trước** khi dùng claims. Nếu role bị thu hồi mà token còn hạn, ứng dụng cần trade-off rõ giữa claims snapshot và real-time authorization lookup.

### Vì sao `ConcurrentHashMap.computeIfPresent` phù hợp?

Trong demo, ta không sửa trực tiếp một `HashSet` roles được dùng đồng thời bởi nhiều handler threads. Thay vào đó tạo `Set.copyOf` mới và thay `Account` immutable bằng `computeIfPresent`. Điều này giúp không xuất hiện trạng thái danh sách role chỉ cập nhật một phần. **Không có nghĩa mọi yêu cầu đang xử lý bị hủy tức thời**: một request vừa pass authorization ngay trước khi role bị thu hồi vẫn có thể hoàn tất. Nếu quyền admin có độ nhạy cao, cần transaction/race-control hoặc policy tại thời điểm commit.

## 7. Custom `Authenticator` cho token ngẫu nhiên (opaque Bearer)

`Authenticator` là extension point. Nếu API dùng `Authorization: Bearer TOKEN`, ta có thể triển khai:

~~~java
@Override
public Authenticator.Result authenticate(HttpExchange exchange) {
    String header = exchange.getRequestHeaders().getFirst("Authorization");
    if (header == null) {
        exchange.getResponseHeaders().set(
                "WWW-Authenticate", "Bearer realm=\"my-api\"");
        return new Authenticator.Retry(401);
    }
    // Xác thực token theo token store / IdP / JWT validation policy.
    // Khi hợp lệ, trả Success(new HttpPrincipal(subject, realm)).
    return new Authenticator.Failure(401);
}
~~~

Đây là **skeleton minh họa, cố ý không xác thực token**, không được dùng trực tiếp ở production. Dòng `Failure(401)` chỉ thể hiện nhánh từ chối mặc định; chương trình chạy tiếp theo có implementation thật ở mức **token ngẫu nhiên nội bộ phục vụ test**.

Khi viết custom Authenticator, phân biệt:
- **`Retry(401)`:** thiếu Authorization, trả challenge.
- **`Failure(401)`:** token malformed/sai/hết hạn/thu hồi.
- **`Success(new HttpPrincipal(...))`:** chỉ sau khi token được kiểm chứng qua một **nguồn tin cậy**, có thể lấy danh tính.
- **`WWW-Authenticate`:** gửi khi cần challenge; không gửi nguyên token hoặc thông tin nhạy cảm trong header chẩn đoán.
- **Token expiry/revocation:** người phát hành/quản lý token phải kiểm soát, Authenticator không tự triển khai.
- **Scopes/audience:** chỉ được cấp access token phù hợp endpoint; principal không thay permission checks.

Demo tạo token bằng `SecureRandom` 32 bytes, Base64URL để vận chuyển, chỉ lưu **SHA-256 digest** phía server và so bằng `MessageDigest.isEqual`. Token raw không được in ra và có thể bị thu hồi bằng cách xóa token verifier. **Cách này vẫn chỉ là mô hình một token một user không có expiry/rotation/persistence**, không phải giải pháp identity production.

### Opaque token khác JWT

| Thuộc tính | Opaque token | JWT access token |
| --- | --- | --- |
| Dữ liệu token | Giá trị ngẫu nhiên khó đoán | Claims có cấu trúc và signature |
| Kiểm tra | Trusted token store/introspection; hashed token có thể so | Verify signature, issuer, audience, expiry, nbf, algorithm, key ID/JWKS |
| Thu hồi | Xóa/đánh dấu revoked server-side | Phụ thuộc expiry, denylist/introspection/token lifecycle |
| Vai trò quyền | Server-side lookup hoặc introspection claims | Claims có thể stale cho đến hết hạn |
| Rủi ro | Lộ token, token store compromise | Lộ token, accepting wrong issuer/audience/alg/key |
| Code demo | Token ngẫu nhiên với digest + revoke | **Không triển khai JWT validator** |

Nếu production cần OAuth 2.0/OIDC, dùng IdP/gateway và thư viện JWT/OIDC được kiểm định, tránh tự xây signature verification/JWK fetching từ đầu chỉ dựa vào parsing chuỗi JWT. Không trộn **ID token** với **access token**: một ID token đúng cho client đăng nhập **không tự là token được phép gọi một resource server khác**.

## 8. Chương trình Java 17+ hoàn chỉnh: endpoint công khai, Basic, Bearer, vai trò động

Ví dụ **`HttpIdentityDemo.java`** dùng **JDK chuẩn** với các module `jdk.httpserver` và `java.net.http`, không cần Maven, database, TLS certificate, Redis hay internet. Nó mở HTTP server **chỉ trên `127.0.0.1`**, chọn port khả dụng bằng `port=0`, dùng HttpClient cùng tiến trình để gửi requests.

**Phạm vi và cảnh báo:** Đây là test trên loopback, có hai mật khẩu test-only ghi trong source và HTTP plaintext loopback. **Không** bind `0.0.0.0` rồi đưa ví dụ này lên internet, không dùng credential literals thật và không dùng HTTP Basic không mã hóa qua mạng. Hệ thống thật cần TLS tại server hoặc reverse proxy trusted, quản lý secret/hardening và IdP/token service phù hợp.

Chương trình thực hiện:
1. Tạo hai account `linh` và `minh` với verifier PBKDF2 có salt.
2. Gắn cùng `BasicAuthenticator` vào contexts `/me` và `/admin`.
3. Tạo custom `BearerAuthenticator` cho `/token`, dùng token ngẫu nhiên hashed và có thể revoke.
4. Để `/public` không có authenticator.
5. Trong handlers, lấy `exchange.getPrincipal()` và tra role/state trong `IdentityStore`.
6. Gửi request test thiếu/sai Basic, role denied, role revoked, token thiếu/hợp lệ/đã thu hồi, tài khoản disabled và path không khớp.
7. Dừng server/executor trong `finally` để không giữ thread và socket sau test.

Tạo file **`HttpIdentityDemo.java`**:

~~~java
import com.sun.net.httpserver.Authenticator;
import com.sun.net.httpserver.BasicAuthenticator;
import com.sun.net.httpserver.HttpContext;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpPrincipal;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.Arrays;
import java.util.Base64;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

public final class HttpIdentityDemo {
    private static final int WORK_FACTOR = 210_000;
    private static final SecureRandom RANDOM = new SecureRandom();

    record Account(byte[] salt, byte[] passwordHash,
                   Set<String> roles, boolean enabled) { }

    static byte[] derive(char[] password, byte[] salt) throws Exception {
        PBEKeySpec spec = new PBEKeySpec(password, salt, WORK_FACTOR, 256);
        try {
            return SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
                    .generateSecret(spec).getEncoded();
        } finally {
            spec.clearPassword();
        }
    }

    static final class IdentityStore {
        private final ConcurrentHashMap<String, Account> users =
                new ConcurrentHashMap<>();

        void register(String username, String password, Set<String> roles)
                throws Exception {
            byte[] salt = new byte[16];
            RANDOM.nextBytes(salt);
            char[] chars = password.toCharArray();
            byte[] digest;
            try {
                digest = derive(chars, salt);
            } finally {
                Arrays.fill(chars, '\0');
            }
            users.put(username, new Account(salt, digest,
                    Set.copyOf(roles), true));
        }

        boolean checkPassword(String username, String candidate) {
            Account account = users.get(username);
            if (account == null || !account.enabled()) return false;
            char[] chars = candidate.toCharArray();
            try {
                byte[] digest = derive(chars, account.salt());
                try {
                    return MessageDigest.isEqual(account.passwordHash(), digest);
                } finally {
                    Arrays.fill(digest, (byte) 0);
                }
            } catch (Exception ex) {
                throw new IllegalStateException("Credential service unavailable", ex);
            } finally {
                Arrays.fill(chars, '\0');
            }
        }

        boolean active(String username) {
            Account account = users.get(username);
            return account != null && account.enabled();
        }

        boolean hasRole(String username, String role) {
            Account account = users.get(username);
            return account != null && account.enabled()
                    && account.roles().contains(role);
        }

        void revokeRole(String username, String role) {
            users.computeIfPresent(username, (name, previous) -> {
                Set<String> updated = new java.util.HashSet<>(previous.roles());
                updated.remove(role);
                return new Account(previous.salt(), previous.passwordHash(),
                        Set.copyOf(updated), previous.enabled());
            });
        }

        void disable(String username) {
            users.computeIfPresent(username, (name, previous) ->
                    new Account(previous.salt(), previous.passwordHash(),
                            previous.roles(), false));
        }
    }

    static final class BearerAuthenticator extends Authenticator {
        private final IdentityStore identities;
        private final AtomicReference<byte[]> activeTokenHash;

        BearerAuthenticator(IdentityStore identities, byte[] hash) {
            this.identities = identities;
            this.activeTokenHash = new AtomicReference<>(hash);
        }

        void revoke() {
            activeTokenHash.set(null);
        }

        private Result deny(HttpExchange exchange, boolean missing) {
            exchange.getResponseHeaders().set(
                    "WWW-Authenticate", "Bearer realm=\"local-demo\"");
            exchange.getResponseHeaders().set("Cache-Control", "no-store");
            return missing ? new Retry(401) : new Failure(401);
        }

        @Override public Result authenticate(HttpExchange exchange) {
            String value = exchange.getRequestHeaders().getFirst("Authorization");
            if (value == null) return deny(exchange, true);
            if (!value.startsWith("Bearer ")) return deny(exchange, false);
            String encoded = value.substring("Bearer ".length());
            if (encoded.length() > 100) return deny(exchange, false);
            byte[] candidate;
            try {
                candidate = Base64.getUrlDecoder().decode(encoded);
            } catch (IllegalArgumentException invalid) {
                return deny(exchange, false);
            }
            if (candidate.length != 32) {
                Arrays.fill(candidate, (byte) 0);
                return deny(exchange, false);
            }
            byte[] expected = activeTokenHash.get();
            if (expected == null || !identities.active("linh")) {
                Arrays.fill(candidate, (byte) 0);
                return deny(exchange, false);
            }
            byte[] digest;
            try {
                digest = MessageDigest.getInstance("SHA-256").digest(candidate);
            } catch (Exception unexpected) {
                throw new IllegalStateException(unexpected);
            } finally {
                Arrays.fill(candidate, (byte) 0);
            }
            boolean valid = MessageDigest.isEqual(expected, digest);
            Arrays.fill(digest, (byte) 0);
            if (!valid) return deny(exchange, false);
            return new Success(new HttpPrincipal("linh", "local-demo"));
        }
    }

    static void respond(HttpExchange exchange, int code, String body)
            throws IOException {
        byte[] content = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.getResponseHeaders().set("X-Content-Type-Options", "nosniff");
        exchange.sendResponseHeaders(code, content.length);
        try (var response = exchange.getResponseBody()) {
            response.write(content);
        }
    }

    static void handle(HttpExchange exchange, String exactPath,
                       IdentityStore users, String requiredRole)
            throws IOException {
        try {
            if (!exactPath.equals(exchange.getRequestURI().getPath())) {
                respond(exchange, 404, "Not found");
                return;
            }
            if (!"GET".equals(exchange.getRequestMethod())) {
                exchange.getResponseHeaders().set("Allow", "GET");
                respond(exchange, 405, "Method not allowed");
                return;
            }
            HttpPrincipal principal = exchange.getPrincipal();
            if (principal == null || !users.active(principal.getUsername())) {
                respond(exchange, 403, "Account not active");
                return;
            }
            if (requiredRole != null
                    && !users.hasRole(principal.getUsername(), requiredRole)) {
                respond(exchange, 403, "Forbidden");
                return;
            }
            respond(exchange, 200, "Hello, " + principal.getUsername());
        } finally {
            exchange.close();
        }
    }

    static String basic(String username, String password) {
        String encoded = Base64.getEncoder().encodeToString(
                (username + ":" + password).getBytes(StandardCharsets.UTF_8));
        return "Basic " + encoded;
    }

    static int request(HttpClient client, URI base, String path,
                       String authorization, String claimedUser)
            throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(base.resolve(path))
                .timeout(Duration.ofSeconds(5)).GET();
        if (authorization != null) builder.header("Authorization", authorization);
        if (claimedUser != null) builder.header("X-User", claimedUser);
        return client.send(builder.build(),
                HttpResponse.BodyHandlers.discarding()).statusCode();
    }

    public static void main(String[] args) throws Exception {
        IdentityStore identities = new IdentityStore();
        // Test-only passwords. Never copy into production or expose over HTTP.
        identities.register("linh", "demo-linh", Set.of("admin", "reader"));
        identities.register("minh", "demo-minh", Set.of("reader"));

        BasicAuthenticator basic = new BasicAuthenticator(
                "local-demo", StandardCharsets.UTF_8) {
            @Override public boolean checkCredentials(String user, String password) {
                return identities.checkPassword(user, password);
            }
        };

        byte[] opaque = new byte[32];
        RANDOM.nextBytes(opaque);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(opaque);
        byte[] tokenHash = MessageDigest.getInstance("SHA-256").digest(opaque);
        Arrays.fill(opaque, (byte) 0);
        BearerAuthenticator bearer = new BearerAuthenticator(identities, tokenHash);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        server.setExecutor(pool);

        server.createContext("/public", exchange -> {
            try {
                if (!"/public".equals(exchange.getRequestURI().getPath())) {
                    respond(exchange, 404, "Not found");
                } else {
                    respond(exchange, 200, "Public");
                }
            } finally {
                exchange.close();
            }
        });
        HttpContext me = server.createContext("/me",
                ex -> handle(ex, "/me", identities, null));
        me.setAuthenticator(basic);
        HttpContext admin = server.createContext("/admin",
                ex -> handle(ex, "/admin", identities, "admin"));
        admin.setAuthenticator(basic);
        HttpContext tokenContext = server.createContext("/token",
                ex -> handle(ex, "/token", identities, "reader"));
        tokenContext.setAuthenticator(bearer);

        server.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3)).build();
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            System.out.println("public: "
                    + request(client, base, "/public", null, null));
            System.out.println("missing Basic: "
                    + request(client, base, "/me", null, null));
            System.out.println("wrong password: "
                    + request(client, base, "/me",
                            basic("linh", "incorrect"), null));
            System.out.println("valid Basic: "
                    + request(client, base, "/me",
                            basic("linh", "demo-linh"), null));
            System.out.println("role denied: "
                    + request(client, base, "/admin",
                            basic("minh", "demo-minh"), "linh"));
            System.out.println("admin allowed: "
                    + request(client, base, "/admin",
                            basic("linh", "demo-linh"), null));
            identities.revokeRole("linh", "admin");
            System.out.println("admin role revoked: "
                    + request(client, base, "/admin",
                            basic("linh", "demo-linh"), null));
            System.out.println("missing Bearer: "
                    + request(client, base, "/token", null, null));
            System.out.println("valid Bearer: "
                    + request(client, base, "/token",
                            "Bearer " + token, null));
            bearer.revoke();
            System.out.println("revoked Bearer: "
                    + request(client, base, "/token",
                            "Bearer " + token, null));
            identities.disable("minh");
            System.out.println("disabled account: "
                    + request(client, base, "/me",
                            basic("minh", "demo-minh"), null));
            System.out.println("exact-path enforcement: "
                    + request(client, base, "/admin-extra",
                            basic("linh", "demo-linh"), null));
        } finally {
            server.stop(0);
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa `HttpIdentityDemo.java`, với JDK 17 trở lên:

~~~bash
javac --release 17 --add-modules jdk.httpserver HttpIdentityDemo.java
java --add-modules jdk.httpserver HttpIdentityDemo
~~~

**Stdout kỳ vọng**, không phụ thuộc port ngẫu nhiên hay token vì chương trình chỉ in mã HTTP:

~~~text
public: 200
missing Basic: 401
wrong password: 401
valid Basic: 200
role denied: 403
admin allowed: 200
admin role revoked: 403
missing Bearer: 401
valid Bearer: 200
revoked Bearer: 401
disabled account: 401
exact-path enforcement: 404
~~~

### Cách đọc các kết quả

- `public: 200`: `/public` không gắn authenticator, có thể truy cập không có Authorization header.
- `missing Basic: 401`: `BasicAuthenticator` yêu cầu thông tin Basic; server trả challenge.
- `wrong password: 401`: tên user `linh` tồn tại nhưng verifier không khớp.
- `valid Basic: 200`: authenticator cấp `HttpPrincipal("linh", "local-demo")`, handler xác nhận account active.
- `role denied: 403`: `minh` có credentials đúng nhưng thiếu admin role. Request còn cố tình gửi `X-User: linh`; handler **bỏ qua header giả mạo** và tin `HttpPrincipal` do Authenticator cấp.
- `admin allowed: 200`: `linh` ban đầu có role admin.
- `admin role revoked: 403`: sau khi `revokeRole("linh", "admin")`, Basic authentication vẫn đúng nhưng authorization ở request tiếp theo không còn cho phép admin.
- `missing Bearer: 401`: custom authenticator yêu cầu token với `WWW-Authenticate: Bearer...`.
- `valid Bearer: 200`: token ngẫu nhiên có digest khớp, principal được tạo.
- `revoked Bearer: 401`: token verifier bị hủy; cùng token không được xác thực nữa.
- `disabled account: 401`: `minh` bị disable trong IdentityStore, password dù đúng không tạo principal.
- `exact-path enforcement: 404`: `/admin-extra` có thể được context `/admin` nhận do prefix matching; handler từ chối vì không phải route chính xác.

**Tất cả giá trị 401/403/200 nêu ở đây là logic của bộ test**, không có lời hứa rằng một ứng dụng khác với framework/session/cookie/OAuth sẽ trả đúng cùng trạng thái trong mọi giao thức. Khi triển khai, hãy tuân thủ RFC 9110, RFC 7617 và RFC 6750 theo scheme đang dùng.

## 9. Chi tiết thiết kế trong chương trình

### 9.1. PBKDF2 có salt: chỉ là ví dụ verifier nội bộ

`register` tạo 16 bytes random salt cho mỗi user, tính verifier:

~~~java
PBEKeySpec spec = new PBEKeySpec(password, salt, 210_000, 256);
byte[] derived = SecretKeyFactory
        .getInstance("PBKDF2WithHmacSHA256")
        .generateSecret(spec).getEncoded();
spec.clearPassword();
~~~

Đoạn này minh họa cách tạo verifier bằng Java SE; trong chương trình đầy đủ dùng `try/finally` để đảm bảo cleanup. Trong production hãy dùng password-hashing service/library phù hợp, config riêng cho cost/rotation, có defense against credential stuffing và constant-time checks. **Không** lưu mật khẩu gốc, không log username/password pairs, không đưa secrets qua URL query. Khi tài khoản không tồn tại, nên có chiến lược tránh account enumeration/timing information leakage và response text đồng nhất khi cần.

### 9.2. `HttpPrincipal` không chứa roles

`BasicAuthenticator` tạo principal từ username đã xác minh. Custom Bearer authenticator cũng tạo principal sau khi token match. Role `admin` chỉ được đọc ở **handler**, từ `IdentityStore` hiện hành, không copy từ request header. Đây là cách tách verification và authorization.

Tuy nhiên, `HttpPrincipal("linh", "local-demo")` không chứa một global immutable subject ID. Ứng dụng nhiều tenant nên có tầng identity mapping phù hợp với subject id, tenant id, issuer và assurance level. Không dùng username hiển thị làm khóa cross-tenant nếu các tenants có thể trùng user names.

### 9.3. Token ngẫu nhiên và revocation

`SecureRandom` sinh 32 bytes, `Base64.getUrlEncoder().withoutPadding()` tạo chuỗi dùng trong `Authorization: Bearer`. Server chỉ giữ `SHA-256` digest và dùng `MessageDigest.isEqual` để so. Token hash khác password hash: token có entropy cao ngẫu nhiên, nên SHA-256 digest có thể dùng làm verifier cho opaque token trong mô hình này; **password của con người** entropy thấp cần password hashing chậm có salt như PBKDF2/Argon2id.

Đừng coi việc gọi `BearerAuthenticator.revoke()` là cách chuẩn cho token store đa người dùng. Demo có **một token duy nhất**, không có database, token ID, tenant, expiry, rotation hoặc introspection API. Production phải có token store/key management, expiry/revocation, scopes, owner binding, audit và các tác vụ kiểm tra token phù hợp.

### 9.4. Một request đang chạy có thể kết thúc sau khi role bị thu hồi

Với concurrency, có thể xảy ra:
1. Authenticator xác nhận người dùng.
2. Handler kiểm tra `hasRole("linh", "admin")`: true.
3. Admin role bị thu hồi bởi request khác.
4. Handler vẫn hoàn thành tác vụ dựa trên kết quả trước đó.

Một role revocation mới có tác dụng với **các lần kiểm tra sau**, không có nghĩa tự động rollback mọi công việc đang thực thi. Với nghiệp vụ quan trọng (chuyển tiền, sửa quyền hệ thống), cần kiểm quyền **gần lúc commit** hoặc có transaction/authorization version checks. Đừng hứa revoke là tức thời toàn hệ thống chỉ vì dùng `ConcurrentHashMap`.

### 9.5. HTTP response và đóng resource

`respond(...)` mã hóa `String` thành UTF-8 bytes, đặt `Content-Type: text/plain; charset=UTF-8` và `Cache-Control: no-store`, gọi `sendResponseHeaders` với độ dài bytes rồi ghi `getResponseBody()`. Dùng try-with-resources để đóng stream response và `exchange.close()` để dọn exchange.

Chương trình dừng `HttpServer` và `ExecutorService` trong `finally`. Ở server production, shutdown cần cơ chế graceful drain, request deadlines và lifecycle management; `server.stop(0)` của demo là ngừng ngay cho test, không phải chiến lược draining cho hàng nghìn requests.

## 10. Lựa chọn mô hình xác thực theo yêu cầu

Không phải ứng dụng nào cũng cần tự quản lý user/password:

| Bối cảnh | Cách tiếp cận | Trade-off |
| --- | --- | --- |
| Chương trình developer trên localhost | Loopback-only HTTP, Basic/test token cho test | Không để lộ ra mạng, không dùng credential thật |
| Tool nội bộ chỉ có một vài người dùng | Basic **chỉ qua TLS** hoặc bảo vệ ở reverse proxy trusted | Quản lý password, rotation, rate limit |
| Internal service-to-service | mTLS hoặc OAuth2 client-credentials access token | Trust chain, rotation và identity giữa các services |
| Web app có người dùng | OIDC login qua IdP + cookie session bảo vệ | Cần CSRF/Cookie flags/session lifecycle |
| Public API | OAuth2 access token hoặc API key/token quản lý qua gateway | Audience, scope, expiry, quota, revocation |
| Hệ thống có nhiều roles/tenants | IdP + authorization policy engine/RBAC/ABAC | Phải tránh cross-tenant access |
| Nhu cầu audit/compliance cao | Gateway/IdP trung tâm với policy, logs, key rotation | Phức tạp triển khai tăng nhưng an toàn/nhất quán hơn |

**Authenticator ở HTTP server gọn là điểm gắn kết cơ chế kiểm tra credentials, không tự cung cấp IAM.** Tùy quy mô, tổ chức nên dùng IdP/SSO, dedicated auth service, policy engine, API gateway và application-framework security thay vì tự quản lý mọi khía cạnh trong một method `authenticate()`.

### Basic và Bearer trong thực tế

Basic có thể đủ cho thử nghiệm cục bộ, nhưng password đi cùng gần như mọi request và browsers có thể cache credentials. Muốn đăng xuất/thu hồi, cần đổi password, khóa account hoặc thay chính sách server; không coi HTTP Basic là session logout an toàn như cơ chế session management chuyên dụng.

Bearer thuận lợi cho API nhưng bất kỳ token bị lộ cũng có thể bị replay trước khi hết hạn. Token cần entropy mạnh, expiry, audience/scope, transport TLS, rotation/revocation và lưu trữ an toàn. Với JWT, không dùng `Base64.getDecoder` rồi tin claims mà **chưa** verify cryptographic signature và issuer/audience/alg/exp/nbf. Với OAuth2/OIDC, dùng provider/SDK theo tiêu chuẩn cập nhật, không dùng thông điệp JWT ngẫu nhiên tự chế thay token chuẩn.

### Tích hợp TLS

`HttpsServer` là subclass của `HttpServer`; cần `SSLContext`, certificate và cipher/protocol configuration đúng. Hoặc đặt HTTP service phía sau reverse proxy có TLS **với backend network isolation/authentication**. Chỉ ghi “đã có HTTPS ở reverse proxy” không đủ nếu client ngoài vẫn có thể kết nối trực tiếp tới HTTP backend qua một public port.

**Ví dụ phần 8 cố ý chỉ bind `127.0.0.1`**. Nếu sửa thành `0.0.0.0` mà giữ Basic trên HTTP plaintext, password sẽ dễ bị thu thập trên mạng. Hãy coi đó là thay đổi security boundary lớn cần đánh giá, không phải thay đổi cấu hình nhỏ.

## 11. Permission model: RBAC, ABAC và object-level authorization

Ví dụ `role="admin"` thể hiện **Role-Based Access Control (RBAC)**, nhưng ở một ứng dụng thật:

- `viewer` có thể đọc tài nguyên của chính tenant.
- `editor` có thể sửa resource khi cùng team và còn active.
- `admin` có thể quản lý users **trong tenant được cấp quyền**, không phải tự động mọi tenant.
- Chủ sở hữu resource có thể khác người có role cao.
- Một admin bị revoke không được dùng token cũ để sửa role của chính mình.

Vì vậy hệ thống thường cần **ABAC (Attribute-Based Access Control)** hoặc object-level checks:

~~~text
authorize(
    principal: subjectId, tenantId, roles,
    action: "invoice:update",
    resource: invoiceId, tenantId, ownerId,
    context: time, current account state, authentication assurance
)
    -> ALLOW / DENY
~~~

Đây là **pseudocode**, không phải API JDK. Kết quả authorization nên đi cùng audit trail và policy version, nhất là khi nghiệp vụ có compliance. Không chỉ kiểm role trong bước routing mà bỏ qua dữ liệu nghiệp vụ object; nếu user đoán được `/invoices/{id}` của tenant khác, một role `reader` không được trở thành quyền đọc tài liệu bất kỳ.

**Default deny:** mọi endpoint mới phải có chính sách authentication/authorization rõ ràng. Dùng `server.createContext` không gắn authenticator cho endpoint admin có thể vô tình cho public access; ở hệ thống lớn, dùng routing/security policy có kiểm thử tự động thay vì gắn thủ công rải rác.

### Authorization theo thời gian

- Account **disabled**: Basic/password và token validation phải nhìn thấy trạng thái disabled.
- Role **revoked**: permission check ở handler/policy engine cần đọc roles hiện hành hoặc token version.
- Password **rotated**: old password phải bị loại; session/token có cần revoke không là một policy riêng.
- Account **deleted**: danh tính cũ có thể cần retained audit record; không reuse ID gây confusion.
- Key **rotated**: client credentials/certificates cần cơ chế overlap và cutoff có kiểm soát.
- Tenant **suspended**: ngay cả user password đúng cũng không nên thao tác trên tenant inactive.

Sự thay đổi phải có cơ chế nhất quán giữa các worker instances. `ConcurrentHashMap` của demo chỉ nằm trong một process: không phải identity repository dùng chung nhiều replicas.

## 12. Vòng đời authenticator và quản lý trạng thái

### Mỗi request phải được đánh giá như một request độc lập

`Authenticator` được gọi cho request đi qua context bảo vệ. Nó có thể phục vụ nhiều kết nối đồng thời; không lưu `currentUsername` trong field mutable dùng chung:

~~~java
// Sai: mutable shared field trên authenticator singleton.
String currentUsername;

@Override
public Result authenticate(HttpExchange exchange) {
    // currentUsername = ...; // request khác có thể ghi đè
    return new Failure(401);
}
~~~

Đây là anti-pattern; không phải implementation usable. Mọi thông tin per-request nên nằm trong biến cục bộ, `HttpExchange` hoặc `HttpPrincipal`; những maps shared cần thread-safety. Nếu dùng cache token introspection, đặt TTL/revocation/maximum entries và tránh cache data chứa secrets vô thời hạn.

### Việc xác thực có thể đắt

PBKDF2/scrypt/Argon2id cố ý tốn CPU/RAM để chống brute-force. Khi dùng HTTP Basic cho nhiều requests, việc gọi hash cho mỗi request có thể tạo overhead đáng kể. Đừng đáp lại bằng cách hạ work factor xuống mức dễ bị brute force. Thay vào đó cân nhắc:
- dùng session hoặc short-lived access token sau login;
- rate limit theo account/IP/tenant, exponential backoff có giới hạn;
- giảm exposure của Basic trên các endpoints traffic cao;
- dùng connection pooling/timeout có kiểm soát tới identity service;
- đo PBKDF2 latency, executor saturation và requests/second.

### Tài nguyên thread và DoS

`HttpServer.setExecutor(Executor)` cho phép chọn executor. Demo dùng fixed thread pool 4 vì request nhỏ và yêu cầu test đơn giản. Trong production cần:
- giới hạn concurrency/queues, request body sizes, header sizes, timeouts, keep-alive;
- deadline cho password/IdP/token checks;
- bảo vệ khỏi credential stuffing và malformed Authorization headers;
- không chạy blocking external IdP call vô thời hạn trong request thread;
- có circuit breaker/fail-closed strategy nếu AuthN backend outage;
- tách metrics `401` (auth fail) và `403` (authorization deny);
- giới hạn CPU/memory để các request bất thường không làm mọi request khác không được xử lý.

JDK `jdk.httpserver` có một số system properties về timeouts và tối đa connections trong implementation, nhưng default không phải một gói security policy production đầy đủ. Xem JDK version/provider thực tế; không coi số liệu của demo là capacity benchmark.

## 13. Những lỗi phổ biến dễ gặp

| Sai lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| Nhầm `java.net.Authenticator` với `com.sun.net.httpserver.Authenticator` | Cấu hình nhầm auth phía client | Dùng đúng `jdk.httpserver` cho inbound server |
| Tạo context admin không gắn authenticator | Endpoint trở thành public | Gắn auth explicit và test security routes |
| `setAuthenticator(null)` khi update config | Vô tình xóa yêu cầu xác thực | Chỉ thay auth trong quy trình được kiểm soát |
| Tin `X-User` do client tự gửi | Impersonation | Dùng `exchange.getPrincipal()` từ trusted authenticator |
| Xem `HttpPrincipal` đã có roles | Bỏ qua nguồn quyền mới nhất | Tra IdentityStore/policy engine |
| Password đúng là được phép admin | AuthN ≠ AuthZ | Kiểm role, tenant, action, resource |
| Trả `200` cho account disabled | Dùng credentials cũ | Recheck account state/expiry/revocation |
| Dùng `403` cho mọi password sai | Không có challenge theo scheme | Dùng `401`/`WWW-Authenticate` phù hợp |
| Trả `Success` khi token chỉ parse được | Chấp nhận unverified/expired token | Verify issuer/alg/audience/expiry/revocation |
| Tin payload JWT chỉ sau Base64 decode | Có thể giả claims | Verify signature + trust policy trước |
| Basic chạy qua HTTP công khai | Lộ username/password | Bắt buộc HTTPS/TLS |
| Nghĩ Base64 là encryption | Credentials lộ nếu bị chặn | TLS và secret hygiene |
| Hardcode password trong code production | Secret exposure | Vault/IdP, hash salted, rotation |
| So plaintext password bằng `String.equals` | Lưu plaintext, side-channel | Password verifier với salt/cost và compare |
| Coi 210.000 PBKDF2 iterations là tiêu chuẩn cố định | Không cập nhật security cost | Tuning và khuyến nghị hiện hành |
| Token đơn giản nhưng không có expiry/revoke | Token bị lộ tồn tại mãi | Token lifecycle/rotation/expiry |
| Một `AtomicReference` token dùng cho nhiều users | Trộn danh tính | Token store gắn subject/tenant/audience |
| Chỉ kiểm role toàn cục, không check tenant | Cross-tenant data breach | Object-level authorization |
| Context path `/admin` mặc định exact | Request `/admin-extra` có thể map nhầm | Exact handler path/router canonicalization |
| Revoke role nhưng không recheck | User giữ quyền sau cập nhật | Server-side authorization per request |
| Tin upstream header mà không có proxy trust boundary | Header spoofing | Strip headers, proxy mTLS/ACL, trusted forwarding |
| Log Authorization hoặc token trong tracing | Lộ credentials | Redact secrets, sanitization |
| Cache Basic password plaintext | Leak/khó revoke | Token/session hoặc bounded verified cache |
| Dùng HTTP server gọn như full IdP | Thiếu bảo mật, audit, PKI, scaling | IdP/gateway/framework chuyên dụng |
| Quên đóng HttpExchange/response body | Giữ socket/tài nguyên | try-with-resources + finally |
| Không giới hạn login attempts | Brute-force/credential stuffing | Rate limit, lockout policy, monitoring |
| Coi user ID hiển thị là globally unique | Collision/rename/tenant confusion | Opaque subject ID + tenant/issuer |
| Test chỉ có request thành công | Không phát hiện bypass | Negative auth/authz tests |

## 14. Bộ kiểm thử nên có trước khi bật Authenticator

| Tình huống | Kỳ vọng |
| --- | --- |
| Public context không có Authorization | `200` nếu đúng route |
| Protected Basic thiếu header | `401`, Basic challenge |
| Basic password sai | `401` |
| Basic username không tồn tại | `401`, không tiết lộ chi tiết account |
| Basic Unicode username/password | Đúng theo charset policy, chỉ dùng TLS |
| Basic hợp lệ đến `/me` | `200` và principal đúng user |
| User role reader đến `/admin` | `403` |
| User role admin đến `/admin` | `200` |
| User reader giả `X-User: admin` | Vẫn `403`, không spoof |
| Admin role revoked sau request thành công | Request sau `403` |
| Account disabled sau khi đã dùng Basic | Request sau `401` |
| Bearer thiếu token | `401`, Bearer challenge |
| Bearer token malformed/unknown | `401`, không exception 500 |
| Bearer token hợp lệ | `200` với đúng principal |
| Bearer token revoked/expired | `401` |
| Bearer token subject bị disabled | `401` hoặc theo scheme/profile đã định |
| Bearer role không đủ | `403` |
| `/admin-extra` không phải route | `404`, không xử lý như admin |
| POST đến GET-only route sau auth | `405` + `Allow: GET` |
| Quá nhiều lần sai mật khẩu | `429`/throttling theo policy |
| IdP/credential backend lỗi | Fail closed, `503`/appropriate error không cấp quyền |
| JWT sai issuer/audience/alg/expiry | Reject, không tin claims |
| Các users có cùng username ở hai tenants | Không lẫn danh tính |
| Reverse proxy forwarded user header giả | Bị strip hoặc reject |
| Truy cập resource tenant khác | `403`/404 theo policy không lộ existence |
| Burst concurrent credentials | Không trộn principals và không phá memory quotas |
| Shutdown server khi requests đang chạy | Không leak threads/sockets, graceful policy |

**Hãy kiểm tra status code và cả business effect**. Một endpoint trả `403` nhưng đã ghi dữ liệu vào database trước bước kiểm quyền vẫn là lỗ hổng. Authorization phải xảy ra trước side effect không thể rollback, hoặc được bảo vệ bằng transaction/policy ở gần thời điểm commit.

### Ví dụ kiểm tra thủ công bằng curl trên HTTPS thật

~~~bash
# Chỉ dùng endpoint HTTPS đã được cấu hình bằng certificate tin cậy.
curl -i https://service.example.invalid/me
curl -i -u 'user:password' https://service.example.invalid/me
curl -i -H "Authorization: Bearer <access-token>" \
  https://service.example.invalid/token
~~~

Các lệnh này chỉ là **minh họa**, hostname `example.invalid` không phải server đang chạy và `<access-token>` là placeholder. **Không** đặt mật khẩu thật trong terminal history hoặc CI logs, không dùng `curl -k` bỏ kiểm TLS certificate. Với Basic, `curl -u` có thể làm lộ secret qua process arguments và shell history; dùng phương án nhập secret an toàn của môi trường đang triển khai.

## 15. Câu hỏi tự kiểm tra

1. **Authenticator của HTTP server JDK nằm ở đâu?** `com.sun.net.httpserver.Authenticator` trong `jdk.httpserver`.
2. **Có phải `java.net.Authenticator` không?** Không, lớp `java.net` là cơ chế khác cho client-side auth.
3. **Làm sao bật auth chỉ cho `/admin`?** Tạo `HttpContext` cho route, gọi `setAuthenticator` trên context ấy.
4. **Có cần auth toàn bộ HttpServer khi chỉ một context riêng cần không?** Không, cấu hình từng context; kiểm tra policy mặc định.
5. **`BasicAuthenticator` cần override gì?** `checkCredentials(String,String)`.
6. **Tại sao dùng `BasicAuthenticator(realm, UTF_8)`?** Charset explicit phù hợp Unicode, hỗ trợ từ Java 14.
7. **Base64 trong HTTP Basic có mã hóa bí mật không?** Không, cần TLS.
8. **`Retry(401)` thường biểu thị điều gì?** Client chưa cung cấp auth hoặc cần challenge và request khác.
9. **`Failure(401)` khác Retry thế nào?** Đã thử kiểm credentials nhưng thất bại.
10. **`Success` mang đối tượng gì?** `HttpPrincipal` của danh tính đã xác thực.
11. **Handler lấy principal bằng API nào?** `exchange.getPrincipal()`.
12. **`HttpPrincipal` tự chứa role admin không?** Không, chỉ username/realm.
13. **Một user đúng password nhưng thiếu role trả gì?** Thông thường `403`.
14. **Thiếu hoặc sai password trả gì?** `401` kèm Basic challenge phù hợp.
15. **Tại sao không tin `X-User` do request tự mang?** Client giả được thông tin danh tính.
16. **Tại sao kiểm tra exact path với `/admin`?** HttpServer dùng longest-prefix matching, có thể chọn context cho `/admin-extra`.
17. **Tại sao hash password với salt riêng?** Không lưu plaintext và tăng chi phí tấn công offline.
18. **PBKDF2 work factor trong demo có phải cấu hình production chuẩn không?** Không.
19. **Bearer token có phải bí mật không?** Có, phải dùng TLS, expiry, revocation và scope.
20. **Làm sao thu hồi opaque token đơn giản trong demo?** `activeTokenHash.set(null)`.
21. **Thu hồi role có tự hủy mọi request đã pass authz không?** Không, request in-flight có race.
22. **Khác biệt role và identity?** Identity là subject; role là một đầu vào cho authorization.
23. **Dùng JWT có thể chỉ Base64-decode claims rồi tin không?** Không, phải verify chữ ký/trust/claims.
24. **Một endpoint admin thiếu setAuthenticator có an toàn không?** Không nếu không có lớp bảo vệ khác.
25. **Có nên bind demo Basic server lên `0.0.0.0` không?** Không, code chỉ intended loopback.
26. **Dùng Basic trên internet cần gì?** HTTPS/TLS, credential lifecycle, rate limit, audit và policy.
27. **Nếu IdP không trả lời, có nên mặc định Success không?** Không, fail closed.
28. **Tại sao dùng `ConcurrentHashMap` và immutable role sets?** Hạn chế race và trạng thái thay đổi giữa các handler threads.
29. **Tại sao trong demo `minh` gửi `X-User: linh` vẫn 403?** User thực được lấy từ HttpPrincipal chứ không lấy spoofed header.
30. **Nếu nhiều tenants có username “linh” giống nhau, dùng tên làm global ID có được không?** Không; dùng stable subject ID và tenant/issuer.
31. **Endpoint thêm mới nên có auth mặc định gì?** Deny by default cho route protected, explicit policy từng endpoint.
32. **JDK HTTP server gọn có tự thay OAuth2/OIDC provider không?** Không, chỉ cung cấp primitive nhận và xử lý requests.
33. **Vì sao 403 khác 401 dù cả hai ngăn request?** 401 liên quan xác thực, 403 là quyền sau xác thực.
34. **Làm sao tránh leak token/password trong log?** Redact Authorization, không log query secrets, kiểm soát tracing.
35. **Một custom Authenticator có nên lưu currentUsername trong field shared không?** Không; dùng local request state và principal.
36. **Sau khi authn/authz pass có thể bỏ qua kiểm object tenant không?** Không, cần resource-level authorization.

## 16. Tài liệu chính thức đang áp dụng

- [Java SE 25 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/module-summary.html): HTTP server API gọn, limitations và module.
- [Java SE 25 — HttpServer](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): khởi tạo context, longest-prefix path routing, executor, lifecycle.
- [Java SE 25 — HttpContext](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): `setAuthenticator`, handler, filters và context attributes.
- [Java SE 25 — Authenticator](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/Authenticator.html): `authenticate` và ba kết quả `Success/Retry/Failure`.
- [Java SE 25 — BasicAuthenticator](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/BasicAuthenticator.html): HTTP Basic, `checkCredentials`, realm và overload charset UTF-8.
- [Java SE 25 — HttpPrincipal](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpPrincipal.html): username, realm.
- [Java SE 25 — HttpExchange](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): `getPrincipal`, request/response headers, status/stream lifecycle.
- [Java SE 25 — HttpsServer](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): embedded HTTPS khi có SSLContext/TLS config.
- [Java SE 25 — HttpClient](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.html): kiểm thử HTTP client trong JDK.
- [Java SE 25 — PBEKeySpec](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/crypto/spec/PBEKeySpec.html): password-derived key parameters và clearPassword.
- [Java SE 25 — MessageDigest](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/MessageDigest.html): `isEqual` khi so verifier/token digest.
- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): HTTP Basic và Base64 credential handling.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer Authorization, WWW-Authenticate và bảo mật bearer tokens.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP status 401, 403, 404, 405 và challenge semantics.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): login throttling, password policies, account lifecycle và defensive design.
- [OWASP — Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html): modern password hashing, salt và cost tuning.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): default deny, least privilege và object-level authorization.

**Kết luận:** `HttpContext.setAuthenticator` cho phép HTTP server gọn yêu cầu **xác thực theo endpoint**, `BasicAuthenticator` phù hợp khi chọn Basic qua transport an toàn, còn custom `Authenticator` có thể kiểm tra Bearer token theo trusted issuer/store. Sau khi `Success` tạo `HttpPrincipal`, ứng dụng vẫn phải kiểm tra **role, account state, tenant, resource và action** ở authorization layer. **401 và 403 là hai loại thất bại khác nhau**. Khi yêu cầu tăng lên (nhiều users, OIDC/SSO, lifecycle tokens, audit, cross-service trust), hãy để IdP/gateway/security framework quản lý danh tính, thay vì biến primitive `jdk.httpserver` thành một hệ thống IAM tự chế.