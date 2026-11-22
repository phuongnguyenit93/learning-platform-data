# CookieHandler, CookieManager, CookieStore và chính sách nhận cookie trong Java HTTP

## 1. Bài toán: HTTP stateless nhưng phiên ứng dụng lại có trạng thái

HTTP không tự buộc mọi request của cùng người dùng phải mang một "phiên" cố định. Với ứng dụng đăng nhập, server có thể tạo session và gửi **cookie** để client mang một định danh ở những request sau:

```text
Java HttpClient                                HTTP Server
      |                                              |
      |--- GET /login ------------------------------>|
      |<-- 200 OK, Set-Cookie: sid=abc; Path=/ -------|
      |                                              |
      |   CookieHandler/CookieManager nhận phản hồi   |
      |   -> CookiePolicy xét có nhận cookie không    |
      |   -> CookieStore lưu sid                     |
      |                                              |
      |--- GET /profile; Cookie: sid=abc ----------->|
      |<-- 200 OK, profile data ----------------------|
```

Ở đây có **hai hành động khác nhau**:

1. Server gửi `Set-Cookie` để **đề nghị client lưu một cookie** với các thuộc tính như `Domain`, `Path`, `Secure`, `HttpOnly`, `Max-Age`.
2. Trong request tới URI phù hợp, client có thể gửi `Cookie` header chứa tên/giá trị của những cookie **được phép gửi**.

Java cung cấp nhóm API `java.net.CookieHandler`, `CookieManager`, `CookieStore`, `CookiePolicy` và `HttpCookie`. Khi dùng `java.net.http.HttpClient` (Java 11+, ví dụ Java 17), bạn cấu hình một `CookieHandler` trên **HttpClient builder** để việc gửi/nhận cookie tự động hoạt động cho các request của client.

**Điểm cốt lõi:** lưu cookie không đồng nghĩa xác thực người dùng thành công; cookie có thể chứa **session identifier** và server phải kiểm tra phiên, quyền truy cập, thời hạn và trạng thái thu hồi. Đa số cookie session là **bearer token**: ai lấy được giá trị hợp lệ có thể mạo danh phiên nếu server không có cơ chế phòng vệ bổ sung.

## 2. Vai trò chính xác của năm API

| API | Vai trò | Khi nào dùng |
| --- | --- | --- |
| `CookieHandler` | Lớp trừu tượng để đọc cookie cho request (`get`) và tiếp nhận cookie từ response (`put`) | Điểm nối giữa HTTP stack và cơ chế cookie |
| `CookieManager` | Triển khai `CookieHandler`, kết hợp nơi lưu và chính sách nhận | Lựa chọn mặc định khi muốn HTTP client quản lý cookie |
| `CookieStore` | Nơi lưu/truy xuất/xóa các đối tượng `HttpCookie` | Xem cookie đã nhận, xóa phiên, thay implementation lưu trữ |
| `CookiePolicy` | Quyết định **có chấp nhận cookie mới từ response hay không** | `ACCEPT_ORIGINAL_SERVER`, `ACCEPT_NONE`, `ACCEPT_ALL` hoặc policy tùy chỉnh |
| `HttpCookie` | Đại diện tên, giá trị và metadata cookie (domain, path, secure, max-age, HTTP-only...) | Kiểm tra cookie hoặc thao tác store tường minh |

Đường đi khái niệm:

```text
                  OUTGOING HTTP REQUEST
                      |
                      v
            CookieHandler.get(uri, headers)
                      |
                CookieManager
                      |
              CookieStore.get(uri)
                      |
       domain/path/secure/expiry filtering
                      |
                      v
         Cookie header attached to request
                      |
                      v
                   HTTP server
                      |
             response Set-Cookie
                      |
                      v
          CookieHandler.put(uri, headers)
                      |
                CookieManager
                      |
            CookiePolicy.shouldAccept
                 /             \
             reject          accept
               |                |
              stop        CookieStore.add
```

Sơ đồ mô tả ý tưởng API. Trong triển khai thực, việc kiểm tra phạm vi cookie có thể được thực hiện một phần ở `CookieStore` và một phần ở `CookieManager.get`. **Đừng tự lặp lại việc xét cookie bằng cách lấy mọi phần tử trong `getCookies()` rồi nối thẳng thành header**, vì có thể bỏ qua các điều kiện như `Secure`, `Path` và domain.

## 3. Khởi tạo CookieManager cho Java 17 HttpClient

Cấu hình trực tiếp, độc lập với trạng thái global của tiến trình:

```java
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.http.HttpClient;

CookieManager manager =
        new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(manager)
        .build();
```

Đoạn này là **mảnh mã** trong phạm vi lớp/phương thức có import tương ứng; không phải tệp standalone. Ý nghĩa:

- Đối số `null` đầu tiên yêu cầu `CookieManager` dùng **CookieStore in-memory mặc định** của JDK.
- `CookiePolicy.ACCEPT_ORIGINAL_SERVER` chỉ nhận cookie do server gốc được coi là có quyền đặt theo chính sách domain của implementation.
- `client.cookieHandler()` trả một `Optional<CookieHandler>`; nếu không đặt qua builder, Optional có thể rỗng.
- `HttpClient` giữ tham chiếu đến handler đã cấu hình và dùng nó khi gửi/nhận HTTP, kể cả khi có nhiều connection trong connection pool. **Cookie không phải thuộc tính cố định của một TCP connection**.
- Java 17 `HttpClient` **không phải `AutoCloseable`**; không dùng `try (HttpClient client = ...)` với `javac --release 17`.

Có thể viết `CookieManager manager = new CookieManager();` để dùng default store và policy. Trong Java 17, default accept policy là **`ACCEPT_ORIGINAL_SERVER`**, nhưng việc ghi rõ chính sách giúp người đọc hiểu quyết định.

### `CookieHandler.setDefault(...)` khác với `HttpClient.Builder.cookieHandler(...)`

API cũ có thể dùng:

```java
CookieHandler.setDefault(new CookieManager());
```

Đây là cấu hình **system-wide** được thiết kế cho **HTTP URL stream protocol handler**, chẳng hạn các luồng xử lý dựa trên `HttpURLConnection`. Nó ảnh hưởng các phần khác của tiến trình và không phải cách tốt để tách cookie jar cho từng HTTP client hiện đại.

Với `java.net.http.HttpClient`, hãy **cấu hình trực tiếp**:

```java
HttpClient client = HttpClient.newBuilder()
        .cookieHandler(manager)
        .build();
```

Đừng suy rằng đặt handler toàn cục sẽ tự động cấp cùng cookie manager cho mọi instance `HttpClient`. Cũng đừng thay handler toàn cục để "đổi phiên" của một người dùng trong ứng dụng multi-user: làm vậy dễ trộn trạng thái giữa các request.

## 4. `CookiePolicy`: chọn cookie nào được **nhận vào store**

Java 17 định nghĩa ba policy dựng sẵn:

| Policy | Hành vi nhận cookie mới | Phù hợp khi nào |
| --- | --- | --- |
| `ACCEPT_ORIGINAL_SERVER` | Chỉ nhận cookie được xem là hợp lệ với origin theo quy tắc domain của Java | Lựa chọn mặc định hợp lý cho client quản lý phiên |
| `ACCEPT_ALL` | Chấp nhận mọi cookie mà parser/store xử lý được, không áp điều kiện original-server ở policy | Chỉ cho tình huống đặc biệt có kiểm soát; không mặc định production |
| `ACCEPT_NONE` | Từ chối tất cả cookie **mới** qua cơ chế xử lý `Set-Cookie` | Client stateless/không cần cookie |

API:

```java
CookieManager normal = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

CookieManager all = new CookieManager(
        null, CookiePolicy.ACCEPT_ALL);

CookieManager none = new CookieManager(
        null, CookiePolicy.ACCEPT_NONE);
```

**Lưu ý bảo mật:** tên `ACCEPT_ORIGINAL_SERVER` trong `java.net` là chính sách nhận cookie dựa trên quan hệ domain do Java hỗ trợ. Nó **không đồng nghĩa** trình duyệt web hiện đại có đầy đủ `SameSite`, public-suffix list, partitioning, tracking prevention hoặc các quy tắc site/origin nghiêm ngặt. Tài liệu Java SE 17 của `CookieManager` dẫn chiếu đặc tả cookie lịch sử RFC 2965; các ứng dụng cần độ tương thích cookie trình duyệt cao phải đánh giá implementation, test và bổ sung policy cần thiết.

### Điểm hay bị hiểu sai: `ACCEPT_NONE` không tự xóa cookie đã lưu

`CookiePolicy` được dùng trong đường xử lý **cookie vừa nhận** qua `CookieManager.put(...)`. Nếu bạn đang có một store với cookie hợp lệ rồi gọi:

```java
manager.setCookiePolicy(CookiePolicy.ACCEPT_NONE);
```

thì đó là **chặn việc nhận cookie mới**, không bảo đảm cookie cũ biến mất hay ngừng được gửi ngay. Với Java 17, demo ở mục 10 chứng minh cookie cũ **vẫn được gửi** sau khi đổi policy.

Nếu muốn xóa trạng thái cookie đã lưu:

```java
boolean changed = manager.getCookieStore().removeAll();
```

Lưu ý `removeAll()` làm trống **toàn bộ CookieStore** liên kết với manager, không chỉ cookie của một endpoint. Trong ứng dụng nhiều tài khoản/tenant, việc gọi này trên store dùng chung có thể xóa phiên của người khác. Đừng dùng làm cơ chế logout nhiều người dùng nếu không có phân vùng trạng thái.

### `ACCEPT_ALL` không đồng nghĩa "gửi cookie đó đến mọi host"

Một response từ `127.0.0.1` có thể cố đặt cookie:

```http
Set-Cookie: foreign=other; Domain=evil.example; Path=/; Max-Age=300
```

Trong test Java 17, `ACCEPT_ORIGINAL_SERVER` từ chối, còn `ACCEPT_ALL` **lưu** cookie đó. Nhưng việc cookie được lưu trong jar **không đảm bảo nó sẽ được gửi lại cho `127.0.0.1`**: chiều gửi vẫn xét phạm vi domain/path/secure.

Kết luận: acceptance policy chỉ là một phần của kiểm soát. Không đặt `ACCEPT_ALL` cho client truy cập nhiều nguồn không đáng tin, vì điều đó cho phép store lưu nhiều state không cần thiết, làm tăng bề mặt rủi ro và độ phức tạp của session.

## 5. Viết CookiePolicy tùy chỉnh cho nguồn được phép

Khi ứng dụng **chỉ** muốn nhận cookie phiên từ một host HTTPS đã biết, có thể kết hợp giới hạn scheme, hostname và chính sách original-server:

```java
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.util.Set;

Set<String> allowedNames = Set.of("SESSION");

CookiePolicy policy = (uri, cookie) ->
        "https".equalsIgnoreCase(uri.getScheme())
        && "api.example.com".equalsIgnoreCase(uri.getHost())
        && allowedNames.contains(cookie.getName())
        && CookiePolicy.ACCEPT_ORIGINAL_SERVER
                .shouldAccept(uri, cookie);

CookieManager manager = new CookieManager(null, policy);
```

*Đoạn này là mảnh code cấu hình; chưa có HTTP server/client runnable.* Các tên/host ở đây chỉ là ví dụ. Policy chỉ cho nhận cookie có tên `SESSION` đến từ `https://api.example.com` theo domain matching gốc. Trong production còn cân nhắc cookie phải có `Secure`/`HttpOnly` và giới hạn tuổi thọ nếu là session token:

```java
CookiePolicy strict = (uri, cookie) ->
        "https".equalsIgnoreCase(uri.getScheme())
        && "api.example.com".equalsIgnoreCase(uri.getHost())
        && "SESSION".equals(cookie.getName())
        && cookie.getSecure()
        && cookie.isHttpOnly()
        && CookiePolicy.ACCEPT_ORIGINAL_SERVER
                .shouldAccept(uri, cookie);
```

**Nhưng đừng ngộ nhận:** policy chỉ chạy khi **nhận**. Nó không tự chặn outbound HTTP requests, không ngăn gửi cookie đã tồn tại sang URL phù hợp scope, không chống redirect/SSRF và không thay server-side session validation. Với các hành vi HTTP redirect, cần kiểm soát request/target origin ở tầng ứng dụng; với HTTPS cần trust store và hostname verification đúng.

Nếu ứng dụng cho phép tải từ nhiều domain, không nên viết một policy tùy tiện cho rằng cookie từ một domain mẹ là hợp lệ ở mọi subdomain. Một cookie `Domain` quá rộng có thể gây chia sẻ state ngoài ý muốn.

## 6. CookieStore: dữ liệu được lưu ở đâu và quản lý thế nào?

Khi tạo `new CookieManager(null, ...)`, JDK dùng **CookieStore in-memory** mặc định: cookie chỉ tồn tại trong bộ nhớ tiến trình, **không tự lưu ra file/DB** để dùng sau khi JVM kết thúc.

Truy cập store:

```java
CookieStore store = manager.getCookieStore();

List<HttpCookie> allActive = store.getCookies();
List<HttpCookie> byUri =
        store.get(URI.create("https://api.example.com/account"));
List<URI> recordedUris = store.getURIs();

boolean removed = store.remove(uri, cookie);
boolean cleared = store.removeAll();
```

*Mảnh code; giả định đã có `manager`, `uri`, `cookie` cùng import `CookieStore`, `HttpCookie`, `URI` và `List`.*

Các phương thức quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `add(URI, HttpCookie)` | Thêm/cập nhật cookie vào store |
| `get(URI)` | Lấy cookie liên quan tới URI, kể cả điều kiện domain trong store |
| `getCookies()` | Liệt kê cookie **chưa hết hạn** trong store |
| `getURIs()` | Liệt kê URI liên kết với cookie |
| `remove(URI, HttpCookie)` | Xóa một cookie theo đối tượng/URI tương ứng |
| `removeAll()` | Xóa tất cả cookie, trả boolean store có thay đổi không |

Oracle Java 17 nói các danh sách trả về từ `get(uri)` và `getCookies()` là **immutable**. Muốn xóa, gọi API `remove`/`removeAll`, không sửa trực tiếp danh sách.

**Cảnh báo đặc biệt:** `CookieStore.add(...)` là thao tác lưu trực tiếp. Nếu code của bạn tự tạo và thêm một `HttpCookie` vào store, đường đó **không đồng nghĩa** gọi `CookieManager.put(...)` và không tự áp đầy đủ `CookiePolicy.shouldAccept(...)` cho dữ liệu vừa được thêm. Đừng dùng `store.add` với Set-Cookie từ nguồn không tin cậy rồi giả định CookiePolicy đã lọc.

`CookieStore.get(URI)` là API lưu trữ; khi cần lập outbound headers cho HTTP, để **CookieHandler.get(...)** làm việc, tránh tự gửi mọi cookie trong `getCookies()` vì sẽ làm lộ cookie sang sai URI.

### CookieStore riêng và persistent cookie jar

Một ứng dụng có thể tự triển khai `CookieStore` để lưu cookie lâu dài, nhưng phải giải quyết:

- Mã hóa dữ liệu cookie khi lưu nếu là session token, quyền truy cập file/DB và quản lý secret.
- Quản lý `Expires`/`Max-Age` và không khôi phục cookie đã hết hạn.
- Đồng bộ thao tác đọc/ghi trong nhiều thread; không giả định mọi `CookieStore` tự viết đều thread-safe.
- Xác minh domain/path/secure và cookie policy ở tầng manager **sau khi reload**; không nhập cookie không rõ nguồn.
- Phân vùng cookie theo người dùng, tenant, môi trường và tài khoản; không dùng một jar chung toàn ứng dụng.
- Xử lý logout/đăng xuất, rotating session ID và xóa session ở server, không chỉ remove phía client.

Cookie jar persistent không phải database của server session. Một browser/Java client lưu `sid`, còn server quản lý cookie đó có còn quyền truy cập hay đã bị thu hồi.

## 7. Phạm vi gửi cookie: Domain, Path, Secure, HttpOnly, Max-Age

Các thuộc tính của `Set-Cookie` ảnh hưởng **có nhận và khi nào gửi**:

| Thuộc tính | Ý nghĩa điển hình | Lỗi thường gặp |
| --- | --- | --- |
| `Domain` | Host/domain mà cookie có thể áp dụng | Cho phạm vi quá rộng hoặc chấp nhận domain không thuộc origin |
| `Path` | Đường dẫn URL mà cookie được gửi theo path matching | Tưởng Path là ranh giới bảo mật mạnh giữa các ứng dụng |
| `Secure` | Chỉ gửi cookie trên giao thức được coi là bảo mật, thường HTTPS | Gửi session token không có Secure trên HTTP |
| `HttpOnly` | Trên trình duyệt, ngăn JavaScript đọc qua `document.cookie` | Tưởng Java code không thể đọc `HttpCookie.getValue()` |
| `Max-Age` | Tuổi thọ cookie tính bằng giây | Quên rằng cookie vẫn có thể tồn tại khi server session đã hết hạn |
| `Expires` | Mốc thời gian hết hạn khi được hỗ trợ | Không xử lý session expiry độc lập ở server |
| `SameSite` | Hạn chế gửi cookie theo ngữ cảnh site trong browser hiện đại | Cho rằng Java 17 CookieManager tự có đầy đủ browser SameSite behavior |

Ví dụ server đặt cookie phiên cho HTTPS:

```http
Set-Cookie: sid=opaque-token; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
```

Đây là **mẫu header để thảo luận bảo mật**, không phải mã server runnable. Trong sản phẩm thực, `opaque-token` phải được sinh ngẫu nhiên khó đoán; server cần bảo vệ, ràng buộc vòng đời và xác thực phiên. `SameSite` giúp giảm một số rủi ro CSRF trong browser, nhưng **không thay thế CSRF defense** khi cần thiết, và Java 17 `CookieManager` không nên được coi là trình duyệt hiện đại hỗ trợ đầy đủ SameSite/Partitioned/public-suffix semantics.

### 7.1. Domain: cookie host-only và Domain attribute

Khi response **không có `Domain`**, cookie thông thường được coi là gắn với host đã gửi (host-only theo quy tắc trình duyệt). Khi có `Domain=example.com`, cookie có thể áp dụng cho các subdomain được phép theo tiêu chuẩn và policy của user agent.

Với Java 17, `CookiePolicy.ACCEPT_ORIGINAL_SERVER` kiểm soát việc nhận bằng logic original-server/domain của JDK. Không giả định chính sách này hoàn toàn trùng với thuật toán RFC 6265 hiện đại. Từ góc nhìn an toàn, ưu tiên **host tối thiểu đủ dùng**, tránh cho một subdomain ít đáng tin đặt cookie cho toàn bộ parent domain.

**Port thường không phải biên giới bảo mật của cookie trong mô hình phổ biến.** Hai ứng dụng ở cùng host nhưng cổng khác có thể dùng chung phạm vi domain/path của cookie; đừng dựa vào port khác nhau để cô lập phiên. `HttpCookie` còn có thuộc tính `Port` lịch sử riêng, nhưng không nên xem đó là cơ chế thay thế tách origin của ứng dụng.

### 7.2. Path: khi nào cookie được gửi

`Set-Cookie: scope=private; Path=/private` giới hạn gửi theo path. Trong demo:

- `GET /echo` không có cookie `scope`.
- `GET /private/echo` có cookie `scope`.

`Path` là **routing hint**, không phải access-control boundary tuyệt đối; một số script/server trong cùng site có thể ảnh hưởng các path khác. Phân quyền phải nằm ở backend.

### 7.3. Secure: lưu được nhưng không gửi qua HTTP plaintext

Trong demo HTTP localhost, server thử gửi:

```http
Set-Cookie: secureSid=secret; Path=/; Secure; Max-Age=300
```

Trên JDK 17 được thử nghiệm, cookie `secureSid` **được lưu** trong CookieStore, nhưng **không xuất hiện trên request `http://`**. Đây là lý do không dùng `getCookies()` để quyết định trực tiếp cookie nào được gửi. Dù vậy, server production không nên thiết lập auth cookie qua HTTP plaintext: hãy dùng HTTPS ngay từ đầu, bật Secure và cấu hình HSTS phù hợp cho các web origin công khai.

### 7.4. HttpOnly: khác quyền truy cập trong JVM

`HttpOnly` chủ yếu ngăn **JavaScript trong browser** đọc cookie qua `document.cookie`, nhằm giảm khả năng script phía client lấy session token. Nó **không** làm cookie biến mất khỏi mã backend Java của bạn. `HttpCookie.isHttpOnly()` có thể trả `true` và ứng dụng Java vẫn có thể truy cập `HttpCookie.getValue()` nếu giữ tham chiếu tới cookie. Do đó không in token ra log, kể cả cookie có HttpOnly.

### 7.5. Max-Age, cookie hết hạn và session hết hạn

- `Max-Age=300`: yêu cầu thời hạn khoảng 300 giây kể từ khi cookie được nhận, theo quy tắc cookie tương ứng.
- `Max-Age=0`: thường có tác dụng xóa/expire cookie cùng tên, Domain và Path theo quy tắc của user agent.
- Không có Max-Age/Expires: nhiều user agent coi là cookie phiên, nhưng tuổi thọ thực còn phụ thuộc implementation; default in-memory store của Java không tự persist qua JVM restart.
- `HttpCookie.hasExpired()` báo trạng thái hết hạn của đối tượng; `CookieStore.getCookies()` trả cookie chưa hết hạn.

**Hết hạn phía client không phải toàn bộ hệ thống auth.** Server phải tự giới hạn thời hạn, vô hiệu hóa token khi logout và xoay session ID sau đăng nhập/đổi quyền. Chỉ xóa cookie trên client không chắc chắn đã vô hiệu hóa session còn hoạt động trên server.

## 8. Cookie và HTTP proxy/redirect: ai là đích thực sự?

Vì bài nằm trong ngữ cảnh **Proxy và phiên HTTP**, cần tách hai lớp:

```text
Java HttpClient (CookieManager)
      |
      | request URI: https://api.example.com/profile
      | Cookie policy xét URI/hostname đích ứng dụng
      v
Corporate forward proxy (có thể qua HTTP CONNECT)
      |
      | đường truyền tới origin theo chính sách proxy
      v
Origin server api.example.com
```

**Cookie gửi cho origin** không giống **proxy authentication**:

- `Cookie` mang trạng thái của HTTP origin theo domain/path/scheme và jar.
- `Proxy-Authorization` thuộc cơ chế xác thực với proxy, không nên được lưu như cookie của origin.
- Với HTTPS qua CONNECT và TLS end-to-end (không TLS interception), proxy thông thường không thấy HTTP Cookie header nằm trong TLS. Với HTTP plaintext, proxy trung gian có thể quan sát nội dung cookie.
- Nếu proxy có hành vi chặn/ghi lại/sửa HTTP hoặc TLS interception, quy tắc tin cậy của môi trường thay đổi; cần quản trị CA, logging và chính sách bảo mật riêng.

**Redirect cũng quan trọng:** URL ban đầu có thể hợp lệ nhưng response dẫn đến hostname khác. CookieManager sẽ xử lý scope dựa trên URI được request, tuy nhiên người dùng không nên dựa vào đó làm toàn bộ biện pháp ngăn SSRF, chuyển HTTPS→HTTP hoặc gửi credentials sang origin khác. Demo để `Redirect.NEVER` để giảm biến số. Production nên allowlist host, kiểm tra target từng hop, hạn chế egress và không dùng jar đa-tenant.

Không tùy tiện copy header `Cookie` thủ công từ request A sang request B ở domain khác. Cách đó **vượt qua logic cookie jar**, có thể làm lộ session token cho bên thứ ba dù CookieManager đúng.

## 9. HttpCookie: quan sát metadata mà không rò rỉ secret

Các thuộc tính Java 17 thường dùng:

```java
HttpCookie c = ...; // Đối tượng lấy từ CookieStore hoặc parser.

String name = c.getName();
String domain = c.getDomain();
String path = c.getPath();
boolean secure = c.getSecure();
boolean httpOnly = c.isHttpOnly();
long maxAgeSeconds = c.getMaxAge();
boolean expired = c.hasExpired();
```

*Mảnh code dùng trong ngữ cảnh có `HttpCookie`; không phải tệp standalone.*

**Không log trực tiếp `c.getValue()` hoặc `c.toString()`**, vì giá trị có thể là token xác thực và `toString()` có thể chứa cả value. Nếu cần metric, log tên thuộc tính và trạng thái (ví dụ count, secure flag) sau khi kiểm soát độ nhạy. Nếu có nhiều cookie cùng tên nhưng khác domain/path, cần kiểm tra đúng tuple để xóa/thay thế; không giả định tên duy nhất toàn jar.

### Tại sao request Cookie header trong Java có thể khác ví dụ trình duyệt?

Trên Java 17, `HttpCookie` và `CookieManager` có lịch sử hỗ trợ RFC 2965. Trong một số trường hợp, request Cookie header có thể chứa các thành phần như:

```http
Cookie: $Version="1"; sid="demo123";$Path="/";$Domain="127.0.0.1"
```

Vì vậy **đừng viết server authentication bằng `cookieHeader.equals("sid=demo123")`**. HTTP server chuyên dụng phải parse cookie header đúng đặc tả/library, kiểm tra session ID ngẫu nhiên và backend session store, không tin một phép `contains("sid=")` đơn giản. Demo dùng `contains` **chỉ để minh họa sự có mặt của cookie**, không phải ví dụ parser hay authorization an toàn.

## 10. Chương trình Java 17 hoàn chỉnh: kiểm thử CookieManager và ba policy

Chương trình cục bộ sau tạo một HTTP server trên loopback và các HttpClient có cookie jar tách biệt. Nó dùng **HTTP không TLS chỉ trong test**, vì kiểm tra riêng việc `Secure` **không được gửi qua HTTP**.

Các nhánh chính:

1. `/login` trả `Set-Cookie: sid=demo123; Path=/; HttpOnly; Max-Age=300`.
2. `/secure` trả `Set-Cookie: secureSid=secret; Path=/; Secure`.
3. `/scope` trả `Set-Cookie: scope=private; Path=/private`.
4. `/foreign` cố đặt cookie có `Domain=evil.example` dù response đến từ `127.0.0.1`.
5. `/echo` và `/private/echo` kiểm tra **sự hiện diện** của tên cookie trong request; kết quả in boolean, không log giá trị.
6. Dùng ba `CookieManager` độc lập cho `ACCEPT_ORIGINAL_SERVER`, `ACCEPT_ALL`, `ACCEPT_NONE`.
7. Thử đổi policy sau khi cookie đã lưu, sau đó xóa toàn jar bằng `CookieStore.removeAll()`.

**Tệp: `CookieManagerDemo.java`**

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
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

public final class CookieManagerDemo {
    static void respond(HttpExchange exchange, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        try (exchange) {
            exchange.getResponseHeaders().set("Content-Type",
                    "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
        }
    }

    static void echo(HttpExchange exchange) throws IOException {
        String cookie = exchange.getRequestHeaders().getFirst("Cookie");
        String value = cookie == null ? "" : cookie;
        respond(exchange, "sid=" + value.contains("sid=")
                + ", secureSid=" + value.contains("secureSid=")
                + ", scope=" + value.contains("scope="));
    }

    static HttpClient newClient(CookieManager manager) {
        return HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .cookieHandler(manager)
                .followRedirects(HttpClient.Redirect.NEVER)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    static String get(HttpClient client, URI root, String path)
            throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(root.resolve(path))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        HttpResponse<String> response = client.send(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
        if (response.statusCode() != 200) {
            throw new IOException("Unexpected HTTP status");
        }
        return response.body();
    }

    static boolean hasCookie(CookieManager manager, String name) {
        return manager.getCookieStore().getCookies().stream()
                .anyMatch(c -> c.getName().equals(name));
    }

    static boolean isHttpOnly(CookieManager manager, String name) {
        return manager.getCookieStore().getCookies().stream()
                .filter(c -> c.getName().equals(name))
                .findFirst().map(HttpCookie::isHttpOnly).orElse(false);
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/login", exchange -> {
            exchange.getResponseHeaders().add("Set-Cookie",
                    "sid=demo123; Path=/; HttpOnly; Max-Age=300");
            respond(exchange, "OK");
        });
        server.createContext("/secure", exchange -> {
            exchange.getResponseHeaders().add("Set-Cookie",
                    "secureSid=secret; Path=/; Secure; Max-Age=300");
            respond(exchange, "OK");
        });
        server.createContext("/scope", exchange -> {
            exchange.getResponseHeaders().add("Set-Cookie",
                    "scope=private; Path=/private; Max-Age=300");
            respond(exchange, "OK");
        });
        server.createContext("/foreign", exchange -> {
            exchange.getResponseHeaders().add("Set-Cookie",
                    "foreign=other; Domain=evil.example; Path=/; Max-Age=300");
            respond(exchange, "OK");
        });
        server.createContext("/echo", CookieManagerDemo::echo);
        server.createContext("/private/echo", CookieManagerDemo::echo);
        server.start();
        try {
            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            CookieManager manager = new CookieManager(null,
                    CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            HttpClient client = newClient(manager);

            System.out.println("before: "
                    + get(client, root, "/echo"));
            get(client, root, "/login");
            System.out.println("after login: "
                    + get(client, root, "/echo"));
            System.out.println("stored HttpOnly: "
                    + isHttpOnly(manager, "sid"));
            get(client, root, "/secure");
            get(client, root, "/scope");
            System.out.println("stored Secure: "
                    + hasCookie(manager, "secureSid"));
            System.out.println("public path: "
                    + get(client, root, "/echo"));
            System.out.println("private path: "
                    + get(client, root, "/private/echo"));
            get(client, root, "/foreign");
            System.out.println("original policy foreign: "
                    + hasCookie(manager, "foreign"));

            CookieManager acceptAll = new CookieManager(null,
                    CookiePolicy.ACCEPT_ALL);
            get(newClient(acceptAll), root, "/foreign");
            System.out.println("accept-all foreign stored: "
                    + hasCookie(acceptAll, "foreign"));

            CookieManager none = new CookieManager(null,
                    CookiePolicy.ACCEPT_NONE);
            HttpClient noneClient = newClient(none);
            get(noneClient, root, "/login");
            System.out.println("accept-none count: "
                    + none.getCookieStore().getCookies().size());
            System.out.println("accept-none echo: "
                    + get(noneClient, root, "/echo"));

            manager.setCookiePolicy(CookiePolicy.ACCEPT_NONE);
            System.out.println("switch policy: "
                    + get(client, root, "/echo"));
            System.out.println("removeAll: "
                    + manager.getCookieStore().removeAll());
            System.out.println("after clear: "
                    + get(client, root, "/echo"));
        } finally {
            server.stop(0);
        }
    }
}
```

Biên dịch/chạy với JDK 17 (module `jdk.httpserver` cung cấp HTTP server cục bộ):

```bash
javac --release 17 --add-modules jdk.httpserver CookieManagerDemo.java
java --add-modules jdk.httpserver CookieManagerDemo
```

**Stdout thực tế đã kiểm thử**:

```text
before: sid=false, secureSid=false, scope=false
after login: sid=true, secureSid=false, scope=false
stored HttpOnly: true
stored Secure: true
public path: sid=true, secureSid=false, scope=false
private path: sid=true, secureSid=false, scope=true
original policy foreign: false
accept-all foreign stored: true
accept-none count: 0
accept-none echo: sid=false, secureSid=false, scope=false
switch policy: sid=true, secureSid=false, scope=false
removeAll: true
after clear: sid=false, secureSid=false, scope=false
```

### 10.1. Giải nghĩa kết quả

- **Before login:** chưa có sid nên server không thấy cookie phiên.
- **After login:** CookieManager nhận và lưu `sid`; request tiếp theo tự có Cookie header thích hợp.
- **Stored HttpOnly true:** phía Java vẫn quan sát metadata `HttpOnly`, dù browser JavaScript có giới hạn truy cập.
- **Stored Secure true nhưng public path secureSid=false:** cookie Secure được lưu nhưng **không gửi qua HTTP plaintext**.
- **Private path scope=true:** cookie đặt Path `/private` được gửi tại `/private/echo`, không gửi tại `/echo`.
- **Original policy foreign=false:** `ACCEPT_ORIGINAL_SERVER` bác cookie tự khai `Domain=evil.example` từ response localhost.
- **Accept-all foreign stored=true:** `ACCEPT_ALL` đưa cookie đó vào store; điều này **không tự chứng minh** nó có thể được gửi đến một host khác.
- **Accept-none count=0:** manager riêng dùng `ACCEPT_NONE` không lưu Set-Cookie mới của `/login`.
- **Switch policy vẫn sid=true:** đổi policy sau khi đã lưu cookie **không xóa và không chặn gửi cookie cũ**. Vì vậy không dùng `ACCEPT_NONE` như lệnh logout.
- **RemoveAll true và after clear sid=false:** `CookieStore.removeAll()` xóa jar của manager; request tiếp theo không gửi cookie cũ. Server session có thể vẫn còn sống; muốn logout thực sự cần request/server-side invalidation.

### 10.2. Những giới hạn chủ đích của demo

Đây là **bài kiểm thử giao thức**, không phải hệ thống xác thực production:

- Dùng HTTP localhost để quan sát Secure filtering; **không dùng HTTP plaintext để truyền session token thật**.
- Dùng session ID hằng `demo123` và server chỉ kiểm tra chuỗi cookie; **không phải cơ chế auth an toàn**. Trong production cần parser cookie chuẩn, session ID bí mật, session store, expiry, CSRF controls và authorization.
- Dùng `value.contains("sid=")` để hiển thị sự có mặt trong demo; chuỗi này **không chứng minh cookie hợp lệ**, không xử lý đầy đủ tên trùng/escape và không dùng để cấp quyền.
- `CookieManager` và in-memory CookieStore chỉ phục vụ test; không có cookie persistence sau JVM shutdown, không có phân vùng user-level tự động.
- `CookiePolicy.ACCEPT_ALL` là nhánh cố ý minh họa rủi ro; không cấu hình mặc định như vậy cho client production.
- Server không dùng HTTPS/certificate; không chạy lại demo công khai trên Internet và không dùng `Set-Cookie: sid=demo123` cho tài khoản thật.
- Thời hạn `Max-Age=300` giữ cookie đủ lâu cho test; khi chạy các bước và thời gian thay đổi rất lớn, các kết quả về expiry sẽ phụ thuộc timing.

## 11. Logout: xóa cookie client và hủy phiên server là hai việc khác nhau

Giả sử server tạo một session ID khi đăng nhập:

```text
session "abc":
  userId = 100
  expiresAt = ...
  revoked = false
```

Client lưu token dạng cookie. Khi logout:

1. Server **thu hồi session ID** hoặc vô hiệu hóa token tương ứng.
2. Server có thể gửi `Set-Cookie` xóa cookie, với tên/domain/path trùng cookie cũ và `Max-Age=0`.
3. Client có thể loại cookie khỏi jar (bằng policy ứng dụng hoặc API store) nếu cần.
4. Không coi việc client chỉ xóa cookie là bằng chứng server session đã mất quyền; một token từng bị sao chép có thể vẫn được dùng cho đến khi server thu hồi hoặc hết hạn.
5. Nếu chia sẻ CookieStore giữa nhiều profile/tenant, xóa tất cả có thể phá các phiên còn lại. **Phân vùng theo principal** thay vì xóa jar global.

Cookie cũng không thay bảo mật truyền tải: mã hóa HTTPS, chống XSS, CSRF, session fixation, token rotation, audit và rate limits còn quan trọng.

## 12. Tạo một cookie thủ công: được, nhưng nhớ phạm vi

Trong trường hợp test hoặc hệ thống tự xây cookie store:

```java
import java.net.HttpCookie;
import java.net.URI;

HttpCookie theme = new HttpCookie("theme", "dark");
theme.setPath("/");
theme.setMaxAge(3600);
manager.getCookieStore().add(
        URI.create("https://example.com"), theme);
```

*Mảnh code; giả định `manager` đã được khởi tạo.* Cần hiểu:

- Thêm trực tiếp qua `CookieStore.add` **không** phải thao tác nhận HTTP response và có thể không đi qua `CookiePolicy`.
- Java `HttpCookie` tạo cookie với các quy ước/version của API, không đảm bảo mọi header tương đương hành vi trình duyệt hiện đại.
- Trước khi gửi, đường `CookieHandler.get` còn xử lý các thuộc tính và URI; đừng tự lấy theme từ mọi URL rồi thêm vào request.
- Không tự tạo cookie có giá trị session ID bằng string đoán được hoặc lưu credential plaintext lâu dài.
- Nếu muốn test cookie có `Secure`/`HttpOnly`, có setter `setSecure(true)`, `setHttpOnly(true)`, nhưng chúng không thay thế HTTPS hoặc authentication server-side.

## 13. Thiết kế cookie jar cho ứng dụng nhiều người dùng hoặc nhiều môi trường

Một lỗi kiến trúc nghiêm trọng là dùng **một CookieManager singleton** cho các user/tenant khác nhau:

```text
Client A (user Alice) --\
                         -> Shared CookieStore -> sid=Alice or sid=Bob
Client B (user Bob) ----/
```

Nếu cả hai đăng nhập cùng host/path, cookie mới có thể thay cookie cũ; request của Alice có nguy cơ chạy với phiên Bob hoặc ngược lại. Domain/path policy không giải quyết vấn đề **tenant isolation**, vì mỗi người dùng hợp lệ có cùng origin.

Chiến lược:

- Dành mỗi **ngữ cảnh phiên** một CookieManager/CookieStore hoặc cấu trúc phân vùng rõ ràng.
- Không tạo CookieManager mới cho **mỗi request** trong cùng phiên, vì sẽ mất cookie được set ở request trước.
- Tái sử dụng `HttpClient` trong cùng phiên khi phù hợp để dùng connection pooling, nhưng cân nhắc tách lifecycle/secret giữa tenants.
- Với service-to-service auth, cân nhắc cơ chế token/header chuẩn của giao thức ứng dụng thay vì âm thầm chia sẻ cookie jar.
- Tránh lưu cookie chứa session token trong logging, tracing, crash dumps không bảo vệ.
- Nếu cần persistence, mã hóa và đặt TTL; khi logout/disable user, xóa store và thu hồi server-side.
- Nếu client dùng proxy/redirect, revalidate đích trước khi cho cookie jar gửi state tới origin khác.

Đừng cho cookie jar vượt quyền truy cập: một người dùng không thể thấy dữ liệu cookie của người dùng khác qua log hoặc API quản trị.

## 14. Sự khác biệt với trình duyệt: SameSite, CORS, XSS và CSRF

Khi mang kiến thức cookie từ browser sang Java HTTP client, dễ gặp bốn nhầm lẫn:

**(1) `HttpOnly` không khóa ứng dụng Java:** trình duyệt JS bị hạn chế truy cập `document.cookie`, nhưng Java server-side process có thể đọc `HttpCookie.getValue()` nếu mã giữ cookie.

**(2) `SameSite` là chính sách browser/site:** Java SE 17 `CookieManager` không nên được mặc định coi là triển khai đầy đủ thuật toán SameSite, cookie partitioning và hiện trạng chính sách trình duyệt. Nếu server trông cậy SameSite để giảm CSRF cho browser, đó là thuộc tính của browser user agent, **không tự xảy ra y hệt trong Java client tùy chỉnh**.

**(3) CORS không phải quyền gửi request của Java HttpClient:** CORS là cơ chế trình duyệt kiểm soát quyền script đọc response cross-origin. Java service có thể gửi request theo policy mạng riêng. Do đó dùng `CookiePolicy` và allowlist địa chỉ/redirect ở tầng backend, không trông vào CORS.

**(4) Path/Domain không thay authorization:** cookie đúng scope có thể được server nhận, nhưng server vẫn phải xác thực user và kiểm tra quyền đối với mỗi tài nguyên. Một server bị SSRF hoặc trust nhầm domain có thể gửi hoặc nhận cookie không mong muốn.

Ứng dụng thao tác dữ liệu nhạy cảm nên kiểm thử với cả trình duyệt thực và client Java nếu hai loại tác nhân đều được dùng; chúng có thể xử lý thuộc tính cookie khác nhau.

## 15. Các lỗi phổ biến và cách khắc phục

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Tạo `HttpClient` không cấu hình cookie handler nhưng mong giữ phiên | Response Set-Cookie không được quản lý qua jar mong đợi | Dùng `builder.cookieHandler(manager)` |
| Set `CookieHandler.setDefault` rồi tưởng mọi HttpClient tự dùng | Quản lý global và client-specific bị nhầm | Cấu hình rõ từng HttpClient |
| Nhầm `CookiePolicy` với nơi lưu | Tưởng ACCEPT_NONE xóa cookie | CookiePolicy lọc nhận mới, `CookieStore.removeAll` xóa state cũ |
| Dùng `ACCEPT_ALL` cho mọi nguồn | Nhận cookie do host khác tự khai domain | Dùng original-server hoặc policy chặt hơn |
| Tưởng cookie trong `getCookies()` luôn được gửi tới mọi URI | Lộ cookie nếu tự gắn header | Để CookieManager lọc outbound theo URI |
| Không giới hạn domain/path khi thiết kế auth cookie | Cookie bị chia sẻ quá rộng | Phạm vi hẹp nhất cần thiết |
| Gửi session token trên HTTP không TLS | Bị nghe lén, giả mạo | HTTPS + Secure; bảo vệ cert/hostname |
| Tưởng HttpOnly làm Java không đọc được cookie | Lộ secret khi log getValue/toString | Không log giá trị |
| Thấy `isHttpOnly()==true` nên bỏ CSRF/XSS/authorization | Phòng thủ thiếu lớp | Auth server-side + phòng thủ web thích hợp |
| Dùng `SameSite` như lý do tin Java CookieManager là browser | Chính sách sai | Test/cấu hình theo loại user agent |
| Dùng một jar toàn ứng dụng multi-tenant | Trộn session của nhiều user | Phân vùng theo phiên/user |
| Logout chỉ gọi `removeAll()` | Server session vẫn có thể hợp lệ | Thu hồi session trên server |
| Dựa vào port để cô lập cookie | Host/domain/path có thể cùng phạm vi | Tách hostname/jar và quyền truy cập |
| Tin rằng phiên cookie đồng nghĩa giữ nguyên TCP connection | Phụ thuộc connection pool, retry/redirect khác nhau | Cookie nằm ở client store, không phải socket |
| Tự set Cookie header raw vượt qua jar | Dễ gửi sai origin/path | Dùng CookieManager |
| Không kiểm soát redirect qua proxy | Có thể gửi state sai đích hoặc SSRF | Allowlist host và revalidate redirects |
| Bỏ qua expiry/Max-Age, chỉ dựa vào cookie tồn tại | Session stale hoặc replay | TTL cả client/server; invalidation |
| Tự thêm cookie vào CookieStore từ nguồn không tin | Bypass acceptance policy | Nhận qua CookieManager.put và validate |
| Dùng HttpCookie.toString() để log | Có thể lộ token | Chỉ log tên/metadata không nhạy cảm |

## 16. Checklist thực hành khi tích hợp với proxy và phiên HTTP

1. Chọn có cần cookie không. Nếu dịch vụ stateless/bearer token độc lập, có thể không bật cookie manager.
2. Nếu cần cookie, tạo `CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER)` hoặc policy hạn chế hơn.
3. Gắn qua `HttpClient.newBuilder().cookieHandler(manager)`; không dựa vào global default.
4. Xác định **đơn vị phiên**: một manager cho một user/session context, không chia giữa tenants.
5. Dùng HTTPS cho session thật, server bật `Secure`/`HttpOnly`, scope Domain/Path tối thiểu, TTL phù hợp.
6. Kiểm tra redirect/ProxySelector: URI nào thật sự được request, hop nào có thể quan sát cookie, có TLS downgrade không.
7. Quan sát phản hồi `Set-Cookie` bằng HTTP debug có kiểm soát, không in giá trị session.
8. Khi lỗi "cookie không gửi", kiểm tra URL scheme, host, path, secure flag, expiry, policy, cookie handler đã gắn, và tên/Domain của cookie.
9. Khi logout, thu hồi session server-side và xóa cookie theo phạm vi đúng, không xóa jar của người dùng khác.
10. Nếu muốn lưu cookie qua restart, thiết kế `CookieStore` persistent có encryption, locking, expiry, partitioning và kiểm thử.
11. Test không chỉ đường thành công: domain sai, Path khác, HTTP/HTTPS, expired, ACCEPT_NONE, ACCEPT_ALL và cookie jar chia sẻ.
12. Với yêu cầu cookie như browser hiện đại, đánh giá giới hạn implementation Java 17 và bổ sung policy/HTTP client phù hợp.

## 17. Bài tập và đáp án

**Bài 1.** Vì sao `CookieManager` không chỉ là một `CookieStore`? Chỉ ra vai trò của `CookiePolicy` trong đường nhận response.

**Bài 2.** Một client đã có `sid` lưu trong CookieStore. Sau đó gọi `manager.setCookiePolicy(ACCEPT_NONE)`. Nó có chắc chắn ngừng gửi `sid` chưa? Muốn ngừng sử dụng state cũ cần làm gì?

**Bài 3.** Server `api.example.com` trả `Set-Cookie: sid=...; Path=/; Secure; HttpOnly`. Request tới `http://api.example.com` có nên gửi `sid`? Java code có thể đọc giá trị `HttpOnly` không?

**Bài 4.** Một cookie có `Path=/private`. Tại sao server nhận cookie tại `/private/profile` mà không nhận tại `/public`? Có thể dùng Path thay phân quyền không?

**Bài 5.** Hai user cùng truy cập `https://service.example.com` nhưng ứng dụng cho họ dùng chung CookieManager. Vì sao đây là bug bảo mật dù `ACCEPT_ORIGINAL_SERVER` được bật?

**Bài 6.** Client dùng proxy tới origin HTTPS. Cookie và `Proxy-Authorization` có cùng ý nghĩa không? Cookie thuộc phạm vi proxy hay origin?

**Bài 7.** `ACCEPT_ALL` lưu một cookie khai `Domain=evil.example` được gửi từ localhost. Điều đó có đồng nghĩa sẽ gửi cookie đó lại cho localhost? Có thể kiểm tra việc thực sự gửi bằng cách nào?

**Bài 8.** User logout và client gọi `getCookieStore().removeAll()`. Server có chắc chắn đã vô hiệu hóa session ID chưa? Cần quy trình nào?

**Bài 9.** Vì sao không nên tự lấy `getCookies()` rồi tạo header `Cookie` cho mọi request?

**Bài 10.** Trình duyệt tự áp dụng SameSite cho một cookie. Có thể giả định Java 17 CookieManager cũng tự áp dụng đầy đủ cùng quy tắc khi gọi API cross-origin không?

**Đáp án gợi ý:**

1. `CookieManager` là CookieHandler phối hợp **policy + store**. `CookiePolicy.shouldAccept` quyết định cookie từ response có được lưu không; `CookieStore` lưu/trả/xóa cookie.
2. Không. Policy lọc cookie mới; cookie cũ vẫn có thể gửi. Cần loại khỏi CookieStore/đổi jar, đồng thời logout bằng server-side invalidation.
3. Không gửi Secure qua HTTP plaintext. Java code có thể đọc `HttpCookie.getValue()` dù HttpOnly; không log.
4. Path-match. Nhưng Path không phải boundary authorization; server vẫn phải xác thực/quyền.
5. Cookie từ user B có thể ghi đè/trộn state của user A vì cùng origin. Phải phân vùng CookieManager/Store theo user/session.
6. Không. Proxy-Authorization xác thực proxy; cookie ứng dụng thuộc origin URI và phải chịu scope. Với HTTPS CONNECT, proxy thông thường không thấy cookie bên trong TLS.
7. Không. Chỉ chứng minh acceptance vào store; cần quan sát outbound request hoặc `CookieHandler.get(...)` theo URI để biết thực tế.
8. Không. Phải vô hiệu hóa session ID/token phía server và gửi Set-Cookie expiry/clear theo chính sách.
9. Vì thiếu lọc Domain/Path/Secure/expiry và dễ gửi token sai đích. Để CookieHandler quản lý.
10. Không. Java 17 CookieManager không được coi là browser engine hiện đại đầy đủ SameSite/partitioning/PSL.

## Tài liệu tham khảo chính thức

- [Java SE 17 — CookieHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieHandler.html): `get`, `put`, global default handler.
- [Java SE 17 — CookieManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html): kết hợp store và policy, default in-memory store, cơ chế accept.
- [Java SE 17 — CookiePolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookiePolicy.html): `ACCEPT_ALL`, `ACCEPT_NONE`, `ACCEPT_ORIGINAL_SERVER`, `shouldAccept`.
- [Java SE 17 — CookieStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieStore.html): `add`, `get`, `getCookies`, `remove`, `removeAll`.
- [Java SE 17 — HttpCookie](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpCookie.html): Domain, Path, Secure, HttpOnly, Max-Age và expiry.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `cookieHandler(CookieHandler)`, redirect/proxy.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `cookieHandler()` trả Optional, các HTTP request/response.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server HTTP loopback trong bài test.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265.html): mô hình Set-Cookie/Cookie, Domain, Path, Secure; cần phân biệt với implementation Java dựa trên đặc tả lịch sử.
