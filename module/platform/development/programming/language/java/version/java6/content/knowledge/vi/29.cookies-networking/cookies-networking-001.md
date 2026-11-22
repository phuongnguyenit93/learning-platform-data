# CookieManager và tách chính sách chấp nhận khỏi lưu trữ trong Java

## 1. Vì sao cần tách chính sách và lưu trữ cookie?

HTTP về nguyên tắc là một giao thức giao tiếp request/response. Để giữ session, ngôn ngữ, giỏ hàng, hoặc một trạng thái nhẹ giữa các lần gọi, server có thể gửi header **`Set-Cookie`**; client quyết định nhận cookie đó hay không, lưu nó nếu được chấp nhận và gửi lại header **`Cookie`** cho những request phù hợp.

Trong Java, `java.net.CookieManager` là implementation của `CookieHandler` giúp quản lý quy trình này. Thiết kế nổi bật của nó là **tách hai trách nhiệm độc lập**:

- **`CookiePolicy`** quyết định *cookie từ response có được chấp nhận để lưu không*.
- **`CookieStore`** quyết định *lưu cookie đã chấp nhận ở đâu, tra cứu thế nào, khi nào hết hạn và xóa ra sao*.

CookieManager phối hợp hai trách nhiệm, còn `HttpCookie` mô hình hóa từng cookie.

Bài **“CookieManager và tách chính sách chấp nhận khỏi lưu trữ”** thuộc **Cookie và mạng**. Sau khi học, bạn có thể:

1. Mô tả luồng `Set-Cookie` → `CookieManager.put` → `CookiePolicy.shouldAccept` → `CookieStore.add`.
2. Mô tả luồng `CookieManager.get` → `CookieStore.get` → kiểm tra điều kiện gửi → `Cookie` request header.
3. Hiểu ba chính sách `ACCEPT_ALL`, `ACCEPT_NONE` và `ACCEPT_ORIGINAL_SERVER`, bao gồm default thực tế.
4. Viết custom CookiePolicy mà **không cần tự viết bộ lưu trữ**.
5. Inject custom CookieStore cho quan sát/persistence/quota nếu thực sự cần, không biến store thành chỗ quyết định tất cả security rules.
6. Giải thích tại sao thay `setCookiePolicy` **không xóa** những cookie đã được nhận trước đó.
7. Chỉ ra rằng `CookieStore.add` được gọi trực tiếp **không đi qua** acceptance policy của CookieManager.
8. Tổ chức **cookie jar riêng cho mỗi `HttpClient` / session / tenant**, tránh chia sẻ dữ liệu qua một global CookieHandler.
9. Đọc đúng `Domain`, `Path`, `Secure`, `HttpOnly`, `Max-Age`, `Expires` và giới hạn hỗ trợ `SameSite` trong JDK.
10. Thực hành với một chương trình Java 17+ và **46 phép kiểm tra chạy thật**, có cả server HTTP loopback và hai HTTP clients độc lập.

**Phạm vi kiến thức:** Các API `java.net.CookieManager`, `CookiePolicy`, `CookieStore` và `HttpCookie` vẫn được tài liệu hóa trong Java SE 26, module `java.base`. `java.net.http.HttpClient.Builder.cookieHandler` vẫn được hỗ trợ trong module `java.net.http`. Bài dùng code biên dịch `--release 17`, chạy thành công trên OpenJDK 24. Không giả định Java CookieManager là một trình duyệt hiện đại hoàn chỉnh, cũng không sử dụng API lỗi thời làm giải pháp mới.

## 2. Mô hình kiến trúc

```text
             HTTP response
     Set-Cookie: session=abc; Secure; ...
                     |
                     v
           CookieHandler.put(...)
                     |
                     v
              CookieManager
                     |
                     +---> CookiePolicy.shouldAccept(uri, cookie)
                     |             |
                     |     ACCEPT / REJECT
                     |             |
                     +---- ACCEPT -+
                     |             |
                     v             v
                  CookieStore.add(uri, cookie)
                             |
                             v
                   CookieStore (cookie jar)
                             |
       Request URI           |
             |               |
             v               v
         CookieManager.get(uri, requestHeaders)
                     |
                     +---> CookieStore.get(uri)
                     +---> match expiry, scheme, domain,
                           path, port/other supported attrs
                     |
                     v
          Cookie: session=abc
                     |
                     v
                  HTTP request
```

Sơ đồ trên mô tả cách phân chia trách nhiệm, **không** cam kết CookieManager có đủ mọi quy tắc của các browser hiện đại.

### 2.1. Bốn khối dữ liệu và interface

| Thành phần | Vai trò chính | API thường dùng |
| --- | --- | --- |
| `CookieHandler` | Abstraction cho HTTP state-management callbacks | `get(URI,headers)`, `put(URI,headers)`, `getDefault()`, `setDefault()` |
| `CookieManager` | Điều phối policy, store và tạo request headers | `CookieManager(...)`, `setCookiePolicy(...)`, `getCookieStore()` |
| `CookiePolicy` | Quyết định accept/reject cookie đầu vào | `shouldAccept(URI,HttpCookie)` |
| `CookieStore` | Lưu/tra, expiry, xóa cookie | `add`, `get`, `getCookies`, `getURIs`, `remove`, `removeAll` |
| `HttpCookie` | Giá trị và thuộc tính của một cookie | `getName`, `getDomain`, `getPath`, `getSecure`, `isHttpOnly`, `getMaxAge` |

**Một CookieManager có một policy hiện hành và một store được tham chiếu.** Tại thời điểm nhận cookie mới, `put` tham vấn policy, rồi chỉ lưu cookie được phép. Khi gửi request, `get` dùng store và các điều kiện thuộc tính cookie, **không gọi lại custom acceptance policy như một cổng phân quyền gửi cookie tổng quát**.

## 3. Chọn constructor và hiểu default

### 3.1. Cách tối giản

```java
CookieManager manager = new CookieManager();
```

Cách này tạo:
- Cookie store **in-memory** nội bộ của JDK.
- Cookie acceptance policy mặc định **`CookiePolicy.ACCEPT_ORIGINAL_SERVER`**.

Constructor `new CookieManager(null, null)` có ý nghĩa tương đương:

```java
CookieManager manager = new CookieManager(null, null);
```

Hai tham số null **không có nghĩa không lưu cookie**, cũng **không có nghĩa nhận mọi cookie**:
- `store == null` → tạo default in-memory CookieStore.
- `policy == null` → dùng `ACCEPT_ORIGINAL_SERVER`.

Các mặc định này được nêu trong Javadoc Java SE 26 và đã được kiểm chứng trong chương trình thực hành.

### 3.2. Inject policy nhưng giữ store mặc định

```java
CookieManager rejectNewCookies =
        new CookieManager(null, CookiePolicy.ACCEPT_NONE);
```

Đoạn trên vẫn có store in-memory nhưng sẽ không chấp nhận cookie từ responses được xử lý qua `CookieManager.put`. Dùng nó khi một HTTP client không được phép lưu trạng thái HTTP cookie trong bối cảnh tương ứng.

### 3.3. Inject store và policy riêng

```java
CookieStore store = new CookieManager().getCookieStore();

CookiePolicy policy = (uri, cookie) -> {
    return "https".equalsIgnoreCase(uri.getScheme())
            && "service.example".equalsIgnoreCase(uri.getHost())
            && "session".equals(cookie.getName())
            && cookie.getSecure()
            && cookie.isHttpOnly();
};

CookieManager manager = new CookieManager(store, policy);
```

Đây là **snippet trong method**, cần các imports `java.net.CookieStore`, `CookiePolicy`, `CookieManager`. Nó minh họa trách nhiệm: policy kiểm tra origin/loại cookie, còn store giữ trạng thái. Sử dụng store của một CookieManager khác chỉ để tiện cho demo; production nên quản lý dependency/lifecycle rõ ràng.

**Quan trọng:** Đây là một policy nghiệp vụ minh họa, **không phải một cookie security implementation toàn diện**; nó chưa kiểm soát public suffix, strict domain rules, SameSite, maximum cookie counts hay browser rules.

## 4. `CookiePolicy`: điều kiện nhận cookie đầu vào

Interface `java.net.CookiePolicy` chỉ có một abstract method:

```java
boolean shouldAccept(URI uri, HttpCookie cookie);
```

Tham số `uri` là nguồn response đang đặt cookie; `cookie` chứa parsed attributes. Callback quyết định có chấp nhận **cookie này** không.

### 4.1. Ba predefined policies

| Policy | Hành vi | Khi nào cân nhắc |
| --- | --- | --- |
| `CookiePolicy.ACCEPT_ALL` | Chấp nhận mọi cookie theo acceptance policy | Chỉ cho môi trường test/trust đã đánh giá; không là bảo đảm an toàn |
| `CookiePolicy.ACCEPT_NONE` | Từ chối mọi cookie mới qua CookieManager | Stateless client, privacy/test scenario |
| `CookiePolicy.ACCEPT_ORIGINAL_SERVER` | Chấp nhận cookie thuộc original server | Default hợp lý để bắt đầu nhưng **không** là anti-CSRF/SameSite policy đầy đủ |

Ví dụ một custom policy:

```java
CookiePolicy onlySecureSession = (uri, cookie) ->
        "https".equalsIgnoreCase(uri.getScheme())
        && "session".equals(cookie.getName())
        && cookie.getSecure();

CookieManager manager =
        new CookieManager(null, onlySecureSession);
```

Nó chỉ đánh giá cookie đầu vào. Không nên giải thích rằng `shouldAccept` kiểm tra mọi request trước khi gửi, hoặc nó là một firewall chặn hết SSRF/XSS/CSRF. Nó không quyết định những request nào HTTP client được phép gửi, và không xác thực server identity/TLS certificate thay cho TLS stack.

### 4.2. Vì sao `ACCEPT_ORIGINAL_SERVER` trực tiếp có thể từ chối cookie mới chưa gắn Domain?

Khi gọi trực tiếp:

```java
URI uri = URI.create("https://service.example/path");
HttpCookie c = new HttpCookie("a", "1");

boolean direct = CookiePolicy.ACCEPT_ORIGINAL_SERVER
        .shouldAccept(uri, c);
```

Trong JDK đã kiểm thử, `direct` là `false` vì cookie vừa tạo **chưa có Domain**. Sau `c.setDomain("service.example")`, callback này trả `true`.

Trong luồng HTTP chuẩn của `CookieManager.put`, manager có URI nguồn và có thể gán domain nguồn cho cookie được parse từ `Set-Cookie` trước khi kiểm tra policy. Vì vậy demo cũng chứng minh `CookieManager(null,null)` nhận cookie host-only từ chính server.

**Bài học:** Đừng viết một unit test so sánh trực tiếp `shouldAccept` với một `HttpCookie` tự tạo thiếu các thuộc tính mà CookieManager sẽ suy ra từ response source, rồi kết luận default manager không nhận cookie đúng origin. Kiểm thử cả **luồng thực tế `put`**.

### 4.3. Policy không retroactive

Đây là điểm dễ làm sai:

```java
CookieManager manager =
        new CookieManager(null, CookiePolicy.ACCEPT_ALL);

manager.put(uri, responseHeaders); // Cookie đã được lưu.
manager.setCookiePolicy(CookiePolicy.ACCEPT_NONE);

// Cookie trước đó KHÔNG tự biến mất.
```

`setCookiePolicy` thay đổi quyết định với **cookie mới**, chứ không gọi `getCookieStore().removeAll()`. Trên các request sau, cookie cũ vẫn có thể được gửi nếu URI và cookie attributes phù hợp. Đây là hành vi đã được xác minh bằng test thực.

Nếu muốn **thu hồi session/cookie đã nhận**, phải chủ động xóa:
- `manager.getCookieStore().remove(uri, cookie)`; hoặc
- `manager.getCookieStore().removeAll()`; hoặc
- Thay cả CookieManager bằng jar mới cô lập cho session mới.

Không dùng `ACCEPT_NONE` như một “nút xóa cookies cũ”.

### 4.4. Store có thể bị thay đổi từ ngoài manager

`CookieManager.getCookieStore()` trả store hiện hành. Code có reference tới store có thể gọi:

```java
store.add(origin, new HttpCookie("manual", "value"));
```

Lệnh **không thông qua `CookieManager.put`**, nên **không kích hoạt `CookiePolicy.shouldAccept`**. Nếu application chia sẻ store cho các modules không tin cậy, chúng có thể inject cookie trực tiếp và làm vô hiệu hóa chính sách accept trên đường input mà bạn nghĩ đã bảo vệ.

Để giữ trust boundary:
- Không public mutable CookieStore ra các thành phần không được phép thay đổi state.
- Nếu cần enforce invariants với mọi đường ghi, custom store phải tự áp giới hạn/quy tắc liên quan hoặc giới hạn quyền gọi `add`.
- Không tin rằng injection of custom CookiePolicy kiểm soát tất cả access paths vào store.
- Xóa/rotate jar khi session boundary thay đổi.

## 5. `CookieStore`: kho và vòng đời

Interface `java.net.CookieStore` có sáu method:

```java
void add(URI uri, HttpCookie cookie);
List<HttpCookie> get(URI uri);
List<HttpCookie> getCookies();
List<URI> getURIs();
boolean remove(URI uri, HttpCookie cookie);
boolean removeAll();
```

Các hàm này không phải HTTP layer; một custom store có thể dùng RAM, database hay encrypted persistence tùy kiến trúc, nhưng **phải giữ đúng semantics**.

### 5.1. `add` và `get`

`add(uri,cookie)` lưu cookie vào kho; `uri` có thể được dùng làm nguồn association nếu cookie chưa có Domain/Path. `get(uri)` lấy cookie có thể áp dụng cho URI hoặc domain, không trả cookies đã hết hạn. Java SE 26 `CookieStore` tài liệu hóa rằng `CookieManager` dùng `add` cho incoming responses và `get` cho outgoing requests.

Những hàm store khác:
- `getCookies()`: danh sách cookies chưa hết hạn trong kho.
- `getURIs()`: những URIs có cookie được liên kết.
- `remove(uri,cookie)`: xóa một cookie.
- `removeAll()`: xóa toàn bộ jar; trả `true` khi store thay đổi.

Khi tự viết CookieStore, phải xử lý:
1. Cookies bị trùng danh tính theo semantics tên/domain/path.
2. Expiration/Max-Age, không trả cookies đã hết hạn.
3. URI association và domain matching đúng.
4. Thread safety khi nhiều requests dùng chung client/jar.
5. Quota số cookie, kích thước, TTL và eviction policy.
6. Persistence/encryption/permissions khi thật sự muốn lưu giữa các lần chạy.
7. Không log raw authentication cookies.
8. `get`/`getCookies` phải trả dữ liệu không cho caller tùy tiện phá invariants; Javadoc nêu danh sách trả về là immutable.

**Không đặt** một backing HashMap đồng thời được mutate bởi nhiều threads mà không có synchronization/concurrency-safe design.

### 5.2. Cookie store mặc định là in-memory

`new CookieManager()` dùng implementation nội bộ của JDK lưu trong RAM. **Nó không tự ghi cookie xuống disk để giữ qua lần restart process**. Nếu ứng dụng cần persistence (ví dụ một HTTP client ứng dụng desktop có lựa chọn “remember session”), bạn phải triển khai hoặc chọn một CookieStore có persistence đủ an toàn.

Ngược lại, với backend services hay isolated requests, RAM-only cookie jar có thể là ưu điểm: không vô tình lưu credentials qua deploy/restart. Vẫn cần xóa state đúng lúc và giới hạn lifetime.

### 5.3. Expiration và cleanup

`HttpCookie.setMaxAge` dùng **seconds**:
- `>0`: tuổi thọ tính từ lúc cookie tạo/parse, không phải absolute timestamp.
- `0`: cookie nên bị loại bỏ ngay.
- `<0`: biểu thị session cookie theo cookie semantics; trong Java app không có browser shutdown event như trình duyệt.

`CookieStore` có trách nhiệm loại bỏ cookie đã hết hạn. Fixture dùng `new HttpCookie("expired","old"); expired.setMaxAge(0)`, thêm vào store rồi kiểm tra nó không còn trong danh sách cookies hợp lệ.

**Đừng** đoán giá trị `getMaxAge()` luôn giảm dần mỗi giây: Java class mô tả tuổi thọ được xác định lúc tạo/parse, khác “thời gian còn lại” động. Muốn kiểm tra hết hạn, dùng `hasExpired()` hoặc quy tắc store.

### 5.4. Khi thay policy và muốn xóa sạch

```java
manager.setCookiePolicy(CookiePolicy.ACCEPT_NONE);
manager.getCookieStore().removeAll();
```

Đây là cách minh bạch để ngừng nhận **mới** và xóa **đã lưu**. Trong hệ thống đa tenant, cần xóa đúng jar của tenant; không gọi `removeAll` trên một jar global dùng chung nếu muốn tránh ảnh hưởng sessions khác.

## 6. `HttpCookie`: các thuộc tính ảnh hưởng việc gửi

`HttpCookie` là class chứa state của một cookie. Ví dụ parser:

```java
HttpCookie session = HttpCookie.parse(
        "Set-Cookie: session=ok; Path=/api; Max-Age=3600; "
        + "Secure; HttpOnly"
).get(0);
```

| Thuộc tính/API | Ý nghĩa | Rủi ro nếu hiểu sai |
| --- | --- | --- |
| `getName()`, `getValue()` | Tên/giá trị cookie | Cookie có thể chứa session/token; không log tùy tiện |
| `getDomain()` | Domain có thể gửi cookie | Không coi một Domain không hợp lệ là trusted; tránh cross-tenant leaks |
| `getPath()` | Path scope được khai báo | Path **không** là authorization/security isolation boundary |
| `getSecure()` | Chỉ gửi qua secure protocol như HTTPS | Không đồng nghĩa server đã kiểm soát mọi lỗ hổng TLS |
| `isHttpOnly()` | Có thuộc tính HttpOnly | Java networking client **không phải browser JS sandbox** |
| `getMaxAge()` | Tuổi thọ tính theo giây | Không nhầm giây với milliseconds |
| `hasExpired()` | Cookie có hết hạn không | Không chỉ dựa vào kích thước danh sách cũ |
| `getVersion()` | Version trong mô hình cookie của Java | Header versioned có thể được quote/đính `$Version` |
| `getPortlist()` | Optional port-list constraint | Hành vi có thể khác browser hiện đại |
| `getDiscard()` | Discard/session policy | Không thay lifecycle thủ công khi dùng custom store |

### 6.1. `Secure` không phải thay HTTPS requirement

Với cookie `Secure`, CookieManager không nên gửi nó qua URI `http:` thường. Fixture kiểm tra:
- `https://service.example/api/items`: nhận cookie secure đã lưu.
- `http://service.example/api/items`: cookie secure **không** được đưa ra.

Tuy nhiên:
- Nếu ứng dụng **chỉ dùng HTTP plaintext**, đừng dựa vào CookieManager để biến kết nối thành bảo mật.
- Cookie mang secrets phải truyền qua HTTPS hợp lệ, không được tắt certificate verification.
- Trên local loopback, fixture dùng một cookie **không có Secure** chỉ để chứng minh cơ chế lưu/gửi HTTP. Đừng copy config loopback này thành production login flow.

### 6.2. `HttpOnly` trong Java client khác browser

Trong browser, `HttpOnly` được định nghĩa để hạn chế truy cập cookie từ JavaScript phía trang web. Nhưng `java.net.HttpCookie` là object do **Java code** sở hữu; chương trình Java vẫn có thể đọc `cookie.getValue()` hoặc `CookieStore.getCookies()`.

Vì vậy **không coi `isHttpOnly()==true` là cơ chế giấu token khỏi tất cả code Java**. Nó chỉ biểu diễn thuộc tính cookie của HTTP protocol. Process ownership, secrets management, logging và code access vẫn phải được kiểm soát.

### 6.3. `SameSite`: khác biệt quan trọng với browser hiện đại

**Java SE 26 `java.net.HttpCookie` không có getter/setter `SameSite` chuẩn** trong API public được tài liệu hóa. Class chỉ hỗ trợ **một phần RFC 6265** và vẫn mang nhiều thuộc tính từ những phiên bản cookie RFC cũ.

Điều này có nghĩa:
- Không thể mặc nhiên mong `CookieManager` có behavior browser-grade về `SameSite=Lax/Strict/None`.
- Không coi `CookiePolicy.ACCEPT_ORIGINAL_SERVER` như một thay thế cho SameSite/CSRF protection.
- Không tự phát minh `cookie.getSameSite()` rồi đưa vào code target Java17/26.
- Nếu sản phẩm cần strict RFC 6265bis/modern browser semantics, đánh giá chuyên biệt thư viện/policy layer phù hợp và test thực tế trên đúng JDK/provider.

Tương tự, API JDK không phải cookie browser jar đầy đủ về public suffix list, cross-site partitioning hoặc mọi `__Host-` / `__Secure-` prefix rule. Đây là những yêu cầu nếu thiết kế HTTP client chạy với nội dung không tin cậy và nhiều origins/tenants.

### 6.4. `Path` không thay authorization

Cookie với `Path=/api` chỉ định khu vực gửi theo URI path. Nó **không** ngăn một handler khác trong cùng origin đọc state trong backend, và không bảo vệ dữ liệu nếu server có lỗ hổng XSS/CSRF. Hạn chế path giúp giảm phạm vi gửi cookie, không phải security boundary giữa microservices/tenants tự động.

## 7. Hai method callback quan trọng: `put` và `get`

### 7.1. Nhận `Set-Cookie` qua `put`

```java
CookieManager manager = new CookieManager();

URI responseOrigin =
        URI.create("https://app.example/auth/login");

Map<String, List<String>> responseHeaders = Map.of(
        "Set-Cookie",
        List.of("sid=abc; Path=/; Secure; HttpOnly; Max-Age=300")
);

manager.put(responseOrigin, responseHeaders);
```

Ở đây:
- URI phản ánh **server đã trả response**.
- Map phản ánh **headers của response**.
- Manager parse từng `Set-Cookie` và gọi policy.
- Cookie được chấp nhận mới đi vào store.

Đây là **snippet**, cần imports `java.net.*` và `java.util.*`. Với HTTPS URI chỉ là đối tượng dữ liệu, code chưa tự thiết lập TLS connection; việc xác minh certificate thuộc tầng HTTP/TLS client đang gửi request thật.

### 7.2. Sinh `Cookie` request header qua `get`

```java
Map<String, List<String>> nextHeaders = manager.get(
        URI.create("https://app.example/account"),
        Map.of()
);

List<String> cookieValues =
        nextHeaders.getOrDefault("Cookie", List.of());
```

Map header đầu ra có thể chứa `Cookie` và/hoặc `Cookie2` theo implementation/versions. Javadoc gọi nó là immutable result map. **Không** tự gửi `Set-Cookie` làm request header: `Set-Cookie` là response header, còn `Cookie` là request header.

Trong integration test dùng `HttpClient.Builder.cookieHandler(manager)`, HTTP client sẽ gọi handler ở các thời điểm thích hợp. Bạn **không cần** gọi `put/get` thủ công cho mỗi HTTP request.

### 7.3. Header Cookie có thể khác format text đơn giản

CookieManager mặc định có cơ chế biểu diễn cookie versioned. Với JDK đã kiểm thử, header có thể chứa:

```http
Cookie: $Version="1"; session="ok";$Path="/api";$Domain="service.example"
```

Không nên hardcode rằng header **luôn** có chuỗi `session=ok` (không dấu ngoặc kép). Trong unit test, có thể kiểm tra tên/giá trị cookie ở model hoặc chấp nhận cả dạng quoted và unquoted. Một test sai vì format header không phải dấu hiệu cookie bị từ chối.

Cookie `Set-Cookie` có thể có các thuộc tính `Expires`, `Max-Age`, `Domain`, `Path`, `Secure`, `HttpOnly`; không có nghĩa tất cả các thuộc tính sẽ được gửi lại trong mỗi `Cookie` request header dưới cùng tên.

## 8. `CookieHandler.setDefault` hay `HttpClient.Builder.cookieHandler`?

### 8.1. Global handler cho `HttpURLConnection`

`CookieHandler.setDefault(...)` đăng ký system-wide cookie handler cho HTTP URL stream handler như `HttpURLConnection`.

```java
CookieHandler.setDefault(
        new CookieManager(null, CookiePolicy.ACCEPT_ORIGINAL_SERVER)
);
```

Đây là **global mutable state** trong JVM. Một thay đổi có thể ảnh hưởng nhiều chỗ cùng dùng URLConnection, gây:
- Cross-service/tenant cookie leakage.
- Tests ảnh hưởng nhau.
- Khó xác định ai có quyền xóa cookie hoặc thay policy.
- Mất khả năng cô lập user sessions.

Không nên đổi global handler trong từng request. Nếu ứng dụng bắt buộc dùng global handler, cấu hình một lần lúc startup với lifecycle được quản trị.

### 8.2. Per-client cookie manager cho Java 11+ `HttpClient`

Cách rõ ràng hơn khi dùng modern HTTP client:

```java
CookieManager sessionCookies = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(sessionCookies)
        .connectTimeout(Duration.ofSeconds(5))
        .build();
```

`HttpClient.Builder.cookieHandler(CookieHandler)` chọn handler **cho client được tạo ra**; không cần sửa `CookieHandler.getDefault()`. Mỗi tenant hoặc logical session có thể có CookieManager riêng để tránh chia sẻ state.

**Quan trọng:** Không phải HTTP client nào cũng tự dùng global `CookieHandler.setDefault`. Đối với `java.net.http.HttpClient`, hãy cấu hình qua builder nếu cần cookies; đừng giả định global setting của URLConnection sẽ được áp dụng tự động cho mọi client.

### 8.3. Hai clients cùng host nhưng khác cookie jars

```text
HttpClient A --cookieHandler--> CookieManager A --> CookieStore A
       |                                       [sid=alpha]
       +------ GET /echo ------> same host

HttpClient B --cookieHandler--> CookieManager B --> CookieStore B
       |                                       [empty]
       +------ GET /echo ------> same host
```

Nếu server trả `Set-Cookie: sid=alpha` cho Client A, **Client B không có cookie đó** khi nó có CookieManager riêng. Bài thực hành kiểm tra điều này bằng loopback HTTP server và hai clients thật.

### 8.4. Redirects, proxies và privacy

Cookie jar được gắn với client có thể nhận cookies từ nhiều hosts mà client truy cập (kể cả redirects theo followRedirects policy). Không để một jar làm nơi dùng chung credentials của nhiều khách hàng trên backend multi-tenant. Nếu client truy cập URL do user cung cấp, cần SSRF prevention, TLS hostname validation, redirect policy và origin allowlist **riêng** với cookie acceptance policy.

## 9. Tạo `CountingStore` để nhìn rõ boundary

Một kỹ thuật học tập hiệu quả là **wrap** store mặc định trong lớp `CountingStore implements CookieStore` và đếm:
- Số lần manager gọi `add`.
- Số lần manager gọi `get`.

Ví dụ:

```java
final class CountingStore implements CookieStore {
    private final CookieStore delegate =
            new CookieManager().getCookieStore();
    private final AtomicInteger additions = new AtomicInteger();

    @Override
    public void add(URI uri, HttpCookie cookie) {
        additions.incrementAndGet();
        delegate.add(uri, cookie);
    }

    // Các method get/getCookies/getURIs/remove/removeAll
    // phải delegate đúng contract và xuất hiện đầy đủ trong
    // chương trình runnable bên dưới.
}
```

Đoạn trên là **snippet rút gọn, không biên dịch độc lập** do chưa override hết các method của interface. Đầy đủ có trong file thực hành.

Khi `CookieManager.put` nhận một cookie nhưng policy trả false, `CountingStore.add` không được gọi. Khi `CookieManager.get` lấy headers outgoing, `CountingStore.get` được gọi. Nhờ đó ta quan sát được **chiều điều khiển** thay vì đoán dựa vào số cookie sau cùng.

## 10. Demo Java 17+ có HTTP thực: 46 kiểm thử

Chương trình `CookiePolicyStoreDemo.java` thực hiện hai lớp kiểm thử:

**Lớp A — chính sách và store thuần Java:**
- Default `CookieManager(null,null)` có memory store và default original-server acceptance.
- `ACCEPT_ALL`, `ACCEPT_NONE` và `ACCEPT_ORIGINAL_SERVER`.
- Custom policy nhận **chỉ secure, HttpOnly, session cookie** từ một HTTPS host dự kiến.
- CountingStore theo dõi `add`/`get`.
- Cookie đã lưu được gửi đúng host/path/scheme; Secure không gửi qua HTTP.
- Cookies bị từ chối không được `store.add`.
- Đổi sang `ACCEPT_NONE` không xóa cookie cũ, không cấm gửi cookie cũ.
- Thêm trực tiếp vào store có thể bỏ qua accept policy.
- Xóa một cookie, xóa toàn bộ, cookie `Max-Age=0` bị loại bỏ.
- Quan sát cookie header có thể quoted.

**Lớp B — integration HTTP loopback:**
- Java `HttpServer` mở listener trên loopback và port ngẫu nhiên.
- Endpoint `/login` trả `Set-Cookie`.
- Endpoint `/echo` trả nguyên `Cookie` request header hoặc `(none)`.
- Hai `HttpClient` với hai `CookieManager` khác nhau.
- A login, A tự gửi cookie trong request sau; B vẫn không có cookie.
- Xóa jar A, request A sau đó không còn cookie.
- `CookieHandler.getDefault()` vẫn giữ nguyên, không có mutation global.
- Cuối cùng stop HTTP server và shutdown executor.

**Bảo mật của fixture:** HTTP plaintext chỉ chạy **localhost** để kiểm tra trạng thái cookie. Không sử dụng mật khẩu thật, không kết nối external network, không lưu cookies vào disk. Các URIs `service.example/app.example/other.example` trong lớp test thuần Java **không được gọi HTTP thật**. Chúng chỉ làm đầu vào cho `CookieManager.put/get`.

### 10.1. File `CookiePolicyStoreDemo.java`

Lưu toàn bộ mã sau thành file có đúng tên `CookiePolicyStoreDemo.java`.


```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.CookieHandler;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.CookieStore;
import java.net.HttpCookie;
import java.net.InetAddress;
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
import java.util.concurrent.atomic.AtomicInteger;

public final class CookiePolicyStoreDemo {
    private static int passed;
    static void check(String title, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + title);
        System.out.println("PASS " + title);
        passed++;
    }

    static final class CountingStore implements CookieStore {
        final CookieStore delegate = new CookieManager().getCookieStore();
        final AtomicInteger additions = new AtomicInteger();
        final AtomicInteger lookups = new AtomicInteger();

        @Override public void add(URI uri, HttpCookie cookie) {
            additions.incrementAndGet();
            delegate.add(uri, cookie);
        }
        @Override public List<HttpCookie> get(URI uri) {
            lookups.incrementAndGet();
            return delegate.get(uri);
        }
        @Override public List<HttpCookie> getCookies() {
            return delegate.getCookies();
        }
        @Override public List<URI> getURIs() {
            return delegate.getURIs();
        }
        @Override public boolean remove(URI uri, HttpCookie cookie) {
            return delegate.remove(uri, cookie);
        }
        @Override public boolean removeAll() {
            return delegate.removeAll();
        }
    }

    static final class RecordingPolicy implements CookiePolicy {
        final AtomicInteger inspected = new AtomicInteger();
        @Override public boolean shouldAccept(URI uri, HttpCookie cookie) {
            inspected.incrementAndGet();
            return "https".equalsIgnoreCase(uri.getScheme())
                    && "service.example".equalsIgnoreCase(uri.getHost())
                    && "session".equals(cookie.getName())
                    && cookie.getSecure() && cookie.isHttpOnly();
        }
    }

    static String cookieHeader(CookieManager manager, URI uri)
            throws IOException {
        Map<String, List<String>> headers = manager.get(uri, Map.of());
        return String.join("; ", headers.getOrDefault("Cookie", List.of()));
    }

    static boolean hasCookie(CookieManager manager, URI uri,
                             String name, String value) throws IOException {
        String header = cookieHeader(manager, uri);
        return header.contains(name + "=" + value)
                || header.contains(name + "=\"" + value + "\"");
    }

    static void reply(HttpExchange ex, int status, String value)
            throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        try (ex) {
            ex.getResponseHeaders().set("Content-Type",
                    "text/plain; charset=utf-8");
            ex.sendResponseHeaders(status, bytes.length);
            try (OutputStream out = ex.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    static HttpResponse<String> get(HttpClient client, URI url)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(5))
                .GET().build();
        return client.send(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        URI origin = URI.create("https://service.example/api/login");
        URI samePath = URI.create("https://service.example/api/items");
        URI plainHttp = URI.create("http://service.example/api/items");
        URI otherPath = URI.create("https://service.example/public");
        URI anotherHost = URI.create("https://other.example/api/items");

        CookieManager defaults = new CookieManager(null, null);
        check("default-memory-store-present",
                defaults.getCookieStore() != null);
        check("initial-default-store-empty",
                defaults.getCookieStore().getCookies().isEmpty());

        defaults.put(URI.create("https://app.example/login"),
                Map.of("Set-Cookie",
                        List.of("id=first; Path=/; Max-Age=3600")));
        check("default-original-server-accepts",
                defaults.getCookieStore().getCookies().size() == 1);

        defaults.put(URI.create("https://app.example/login"),
                Map.of("Set-Cookie", List.of(
                        "cross=bad; Domain=other.example; Path=/")));
        check("default-original-server-rejects-foreign-domain",
                defaults.getCookieStore().getCookies().size() == 1);

        check("builtin-accept-all",
                CookiePolicy.ACCEPT_ALL.shouldAccept(origin,
                        new HttpCookie("x", "1")));
        check("builtin-accept-none",
                !CookiePolicy.ACCEPT_NONE.shouldAccept(origin,
                        new HttpCookie("x", "1")));
        HttpCookie matching = new HttpCookie("x", "1");
        matching.setDomain("service.example");
        check("builtin-original-server-accepts-domain",
                CookiePolicy.ACCEPT_ORIGINAL_SERVER.shouldAccept(
                        origin, matching));
        HttpCookie foreign = new HttpCookie("x", "1");
        foreign.setDomain("other.example");
        check("builtin-original-server-rejects-foreign",
                !CookiePolicy.ACCEPT_ORIGINAL_SERVER
                        .shouldAccept(origin, foreign));

        CountingStore store = new CountingStore();
        RecordingPolicy policy = new RecordingPolicy();
        CookieManager manager = new CookieManager(store, policy);
        check("injected-store-is-used",
                manager.getCookieStore() == store);

        manager.put(origin, Map.of("Set-Cookie",
                List.of("session=ok; Path=/api; Max-Age=3600; "
                        + "Secure; HttpOnly")));
        check("custom-policy-invoked-for-put",
                policy.inspected.get() == 1);
        check("accepted-cookie-reaches-store",
                store.additions.get() == 1
                        && store.getCookies().size() == 1);
        HttpCookie accepted = store.getCookies().get(0);
        check("parsed-secure-attribute", accepted.getSecure());
        check("parsed-httponly-attribute", accepted.isHttpOnly());
        check("parsed-path-attribute",
                "/api".equals(accepted.getPath()));
        check("parsed-positive-max-age", accepted.getMaxAge() > 0);
        check("allowed-request-sends-cookie",
                hasCookie(manager, samePath, "session", "ok"));
        check("secure-cookie-not-on-http",
                !hasCookie(manager, plainHttp, "session", "ok"));
        check("path-restricts-cookie",
                !hasCookie(manager, otherPath, "session", "ok"));
        check("other-host-does-not-receive-cookie",
                !hasCookie(manager, anotherHost, "session", "ok"));
        check("store-get-used-by-manager",
                store.lookups.get() >= 4);

        manager.put(origin, Map.of("Set-Cookie",
                List.of("tracking=bad; Path=/api; Secure; HttpOnly")));
        check("custom-policy-rejects-tracking-cookie",
                policy.inspected.get() == 2
                        && store.additions.get() == 1);
        manager.put(URI.create("http://service.example/api/login"),
                Map.of("Set-Cookie",
                        List.of("session=plain; Path=/api")));
        check("custom-policy-rejects-insecure-origin",
                policy.inspected.get() == 3
                        && store.additions.get() == 1);

        manager.setCookiePolicy(CookiePolicy.ACCEPT_NONE);
        check("changed-policy-does-not-purge-old-store",
                store.getCookies().size() == 1);
        check("accepted-cookie-still-sent-after-policy-change",
                hasCookie(manager, samePath, "session", "ok"));
        manager.put(origin, Map.of("Set-Cookie",
                List.of("fresh=reject; Path=/api; Max-Age=3600")));
        check("accept-none-rejects-new-cookie",
                store.getCookies().size() == 1
                        && store.additions.get() == 1);

        HttpCookie manual = new HttpCookie("manual", "added");
        manual.setPath("/api");
        manual.setSecure(true);
        store.add(origin, manual);
        check("direct-store-add-bypasses-put-policy",
                store.getCookies().size() == 2);
        check("manually-added-cookie-sent-despite-accept-none",
                hasCookie(manager, samePath, "manual", "added"));
        check("store-remove-one",
                store.remove(origin, manual));
        check("manual-cookie-no-longer-sent",
                !hasCookie(manager, samePath, "manual", "added"));

        manager.setCookiePolicy(CookiePolicy.ACCEPT_ALL);
        manager.put(origin, Map.of("Set-Cookie",
                List.of("tracking=accepted; Path=/api; Max-Age=3600")));
        check("accept-all-admits-new-cookie",
                store.getCookies().size() == 2
                        && cookieHeader(manager, samePath)
                                .contains("tracking=\"accepted\""));

        HttpCookie expired = new HttpCookie("expired", "old");
        expired.setMaxAge(0);
        store.add(origin, expired);
        check("expired-cookie-not-retained",
                store.getCookies().stream().noneMatch(HttpCookie::hasExpired));
        check("stored-uri-list-available",
                !store.getURIs().isEmpty());
        check("remove-all-changes-store",
                store.removeAll());
        check("store-empty-after-clear",
                store.getCookies().isEmpty());
        check("clear-stops-cookie-header",
                !hasCookie(manager, samePath, "session", "ok"));

        CookieHandler priorGlobal = CookieHandler.getDefault();
        ExecutorService workers = Executors.newFixedThreadPool(3);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0),
                8);
        server.setExecutor(workers);
        server.createContext("/login", ex -> {
            ex.getResponseHeaders().add("Set-Cookie",
                    "sid=local-value; Path=/; Max-Age=300; HttpOnly");
            reply(ex, 200, "logged-in");
        });
        server.createContext("/echo", ex -> {
            String cookie = ex.getRequestHeaders().getFirst("Cookie");
            reply(ex, 200, cookie == null ? "(none)" : cookie);
        });
        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());
            CookieManager jarA = new CookieManager();
            CookieManager jarB = new CookieManager();
            HttpClient a = HttpClient.newBuilder()
                    .cookieHandler(jarA)
                    .connectTimeout(Duration.ofSeconds(5))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();
            HttpClient b = HttpClient.newBuilder()
                    .cookieHandler(jarB)
                    .connectTimeout(Duration.ofSeconds(5))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            check("client-a-no-cookie-before-login",
                    "(none)".equals(get(a, base.resolve("/echo")).body()));
            check("client-b-no-cookie-before-login",
                    "(none)".equals(get(b, base.resolve("/echo")).body()));
            check("login-sets-cookie",
                    get(a, base.resolve("/login")).statusCode() == 200);
            check("client-a-cookie-stored",
                    jarA.getCookieStore().getCookies().size() == 1);
            check("client-a-sends-cookie",
                    get(a, base.resolve("/echo")).body()
                            .contains("local-value"));
            check("client-b-still-isolated",
                    "(none)".equals(get(b, base.resolve("/echo")).body()));
            check("client-b-store-remains-empty",
                    jarB.getCookieStore().getCookies().isEmpty());
            check("per-client-builder-no-global-mutation",
                    CookieHandler.getDefault() == priorGlobal);
            check("client-a-remove-all",
                    jarA.getCookieStore().removeAll());
            check("client-a-after-clear-no-cookie",
                    "(none)".equals(get(a, base.resolve("/echo")).body()));
            check("real-http-loopback-only",
                    server.getAddress().getAddress().isLoopbackAddress());
        } finally {
            server.stop(1);
            workers.shutdownNow();
        }
        System.out.println("passed=" + passed);
    }
}
```

### 10.2. Biên dịch và chạy

Trong thư mục chứa `CookiePolicyStoreDemo.java`, dùng JDK 17+:

```bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 CookiePolicyStoreDemo.java
java --add-modules jdk.httpserver CookiePolicyStoreDemo
```

`jdk.httpserver` chỉ phục vụ **endpoint test loopback** trong phần integration; các class CookieManager/CookiePolicy/CookieStore/HttpCookie nằm trong `java.base`, còn `HttpClient` nằm trong `java.net.http`. Với project JPMS có named module và code dùng cả ba nhóm, `module-info.java` cần:

```java
module example.cookies {
    requires jdk.httpserver;
    requires java.net.http;
}
```

Đây là **snippet khai báo module**, không phải một chương trình khác. File example chính không khai báo package/module để chạy đơn giản bằng classpath; nếu chuyển sang named module, đặt class vào package và build theo module layout.

### 10.3. Stdout đã xác minh trên OpenJDK 24

```text
PASS default-memory-store-present
PASS initial-default-store-empty
PASS default-original-server-accepts
PASS default-original-server-rejects-foreign-domain
PASS builtin-accept-all
PASS builtin-accept-none
PASS builtin-original-server-accepts-domain
PASS builtin-original-server-rejects-foreign
PASS injected-store-is-used
PASS custom-policy-invoked-for-put
PASS accepted-cookie-reaches-store
PASS parsed-secure-attribute
PASS parsed-httponly-attribute
PASS parsed-path-attribute
PASS parsed-positive-max-age
PASS allowed-request-sends-cookie
PASS secure-cookie-not-on-http
PASS path-restricts-cookie
PASS other-host-does-not-receive-cookie
PASS store-get-used-by-manager
PASS custom-policy-rejects-tracking-cookie
PASS custom-policy-rejects-insecure-origin
PASS changed-policy-does-not-purge-old-store
PASS accepted-cookie-still-sent-after-policy-change
PASS accept-none-rejects-new-cookie
PASS direct-store-add-bypasses-put-policy
PASS manually-added-cookie-sent-despite-accept-none
PASS store-remove-one
PASS manual-cookie-no-longer-sent
PASS accept-all-admits-new-cookie
PASS expired-cookie-not-retained
PASS stored-uri-list-available
PASS remove-all-changes-store
PASS store-empty-after-clear
PASS clear-stops-cookie-header
PASS client-a-no-cookie-before-login
PASS client-b-no-cookie-before-login
PASS login-sets-cookie
PASS client-a-cookie-stored
PASS client-a-sends-cookie
PASS client-b-still-isolated
PASS client-b-store-remains-empty
PASS per-client-builder-no-global-mutation
PASS client-a-remove-all
PASS client-a-after-clear-no-cookie
PASS real-http-loopback-only
passed=46
```

**Kết quả thực tế:** Biên dịch với `javac --release 17 --add-modules jdk.httpserver` trên OpenJDK 24: PASS. Thực thi với `java --add-modules jdk.httpserver`: **46/46 checks PASS**. Các test dùng những tên cố định, không in port ngẫu nhiên hay thời gian để output ổn định.

### 10.4. Giải thích 46 kết quả theo nhóm

| Nhóm | Assertions tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Mặc định | `default-memory-store-present`, `default-original-server-accepts` | CookieManager không cần custom store; policy mặc định chỉ nhận origin phù hợp |
| Domain rejection | `default-original-server-rejects-foreign-domain` | Không lưu cookie có Domain từ host khác khi dùng original-server |
| Built-ins | `builtin-accept-*` | Chính sách nhận và từ chối tách khỏi nơi lưu |
| Custom policy | `custom-policy-invoked-for-put` | Callback được gọi khi xử lý `Set-Cookie` |
| Store delegation | `accepted-cookie-reaches-store`, `store-get-used-by-manager` | Store chỉ lưu accepted cookies, tham gia outgoing lookup |
| Cookie attributes | `parsed-secure-attribute`, `parsed-httponly-attribute`, `parsed-path-attribute` | Parser đưa thuộc tính vào HttpCookie |
| Outbound | `allowed-request-sends-cookie`, `secure-cookie-not-on-http` | Gửi cookie tùy URI/protocol |
| Scoping | `path-restricts-cookie`, `other-host-does-not-receive-cookie` | Không gửi cookie bừa mọi host/path |
| Rejection | `custom-policy-rejects-*` | Cookie không đạt policy không đi vào store |
| Policy change | `changed-policy-does-not-purge-old-store` | Thay policy không phải remove cookies |
| Stored-cookie replay | `accepted-cookie-still-sent-after-policy-change` | Cookie cũ vẫn được gửi nếu còn hợp lệ |
| Bypass trực tiếp store | `direct-store-add-bypasses-put-policy` | Store mutable phải có ownership/trust boundary |
| Cleanup | `store-remove-one`, `remove-all-changes-store` | Xóa state rõ ràng |
| Expiration | `expired-cookie-not-retained` | Max-Age=0 không được giữ trong danh sách active |
| HTTP integration | `login-sets-cookie`, `client-a-sends-cookie` | CookieHandler được HttpClient gọi tự động |
| Jar isolation | `client-b-still-isolated`, `client-b-store-remains-empty` | Hai clients không chia sẻ session |
| Global scope | `per-client-builder-no-global-mutation` | Không phải thay process-wide CookieHandler |
| Resource management | `real-http-loopback-only` | HTTP test không expose Internet; server stop trong finally |

**Một sắc thái kiểm thử:** `CookiePolicy.ACCEPT_ORIGINAL_SERVER.shouldAccept(uri, cookie)` khi gọi trực tiếp với `HttpCookie` thiếu Domain có thể trả false; khi test luồng `CookieManager.put` với một `Set-Cookie` host-only đúng nguồn thì manager chấp nhận. Đây là lý do không đưa ra assertion sai về default policy từ một cookie object chưa hoàn chỉnh.

## 11. Lựa chọn policy cho các trường hợp ứng dụng

### 11.1. Stateless API client

Nếu ứng dụng sử dụng token `Authorization: Bearer ...` hoặc xác thực rõ mỗi request và không cần cookies:

```java
CookieManager noCookieJar =
        new CookieManager(null, CookiePolicy.ACCEPT_NONE);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(noCookieJar)
        .build();
```

Hoặc không cấu hình cookie handler cho client khi protocol không cần cookie. `ACCEPT_NONE` làm rõ ý định không lưu cookies mới; nếu jar đã từng có dữ liệu, vẫn phải xóa state.

### 11.2. Client dành riêng cho một đối tác HTTPS

Custom `CookiePolicy` có thể giới hạn:
- Scheme HTTPS.
- Host exact/allowlist đã xác thực.
- Cookie name cho phép.
- Những attributes bắt buộc như `Secure`, `HttpOnly`.
- Path phù hợp với ứng dụng.

Nhưng phải **giữ policy và request routing riêng**: policy nhận cookie không phải cách chặn client gửi HTTP request đến host lạ. Dùng expected endpoint config, hostname validation, SSRF protection, redirect policy và TLS certificate validation ở HTTP layer.

### 11.3. Multi-tenant backend

Không dùng **một** singleton CookieManager cho tất cả người dùng của một service nếu cookies chứa user sessions. Thay vào đó:
- Một jar cho một logical session, tenant hoặc authenticated context, tùy mô hình.
- Scope lifecycle rõ và xóa khi logout/session expiry.
- Không log raw cookie values, kể cả trong HTTP client DEBUG logs.
- Không để retry/replay request với cookies từ một người khác.
- Đo số cookie/total bytes/expiry và có quota.
- Tách staging/production và host allowlists.

### 11.4. Desktop client cần persistence

Bạn có thể cần custom CookieStore lưu vào disk, nhưng đừng tự viết persistence ngây thơ:
- Encrypt at rest nếu cookies có bearer tokens, với secrets nằm ngoài file.
- Set restrictive file permissions.
- Handle corruption và version migration.
- Respect domain/path/secure/maxAge/expiry semantics khi reload.
- Dùng bounded retention và user-initiated clear.
- Đồng bộ truy cập khi app có nhiều HTTP requests đồng thời.
- Không load cookie không có origin/trust context từ file không tin cậy.

Đặc biệt, một cookie lưu từ trước có thể không còn hợp lệ sau khi user logout hoặc rotate credentials. Persistence không đồng nghĩa quyền sử dụng session vĩnh viễn.

## 12. Các lưu ý bảo mật hiện hành

### 12.1. Cookie session có thể bị lộ dù HttpOnly=true trong model

`HttpOnly` giúp browser ngăn JavaScript truy xuất cookie, nhưng ở Java client code, bất kỳ thành phần nào giữ `CookieManager.getCookieStore()` vẫn có thể đọc value. Vì thế:
- Quản lý access tới cookie jar.
- Tránh logging HTTP `Cookie`/`Set-Cookie` raw.
- Không đưa cookie value vào exception messages hoặc telemetry.
- Dùng HTTPS và đúng endpoint trust.
- Không dùng cookie làm bằng chứng duy nhất cho một request authorization nếu session server chưa xác minh.

### 12.2. CookiePolicy không phải SameSite/CSRF engine

Browser `SameSite` phục vụ ngữ cảnh cross-site navigation/requests. `CookiePolicy.shouldAccept` chỉ xét URI response và `HttpCookie`; đây không phải một browser-origin security model toàn diện.

Với web app cần chống CSRF, vẫn cần:
- CSRF tokens/Origin validation hoặc cơ chế tương đương phù hợp.
- SameSite cookie ở tầng server/browser theo policy.
- XSS prevention và secure session handling.
- Không tin CORS là thay thế CSRF protection trong mọi tình huống.

Nếu Java HTTP client vận hành thay browser, bạn phải tự định nghĩa security policy cần thiết; đừng mặc định cookie jar Java xử lý mọi trường hợp như Chrome/Firefox.

### 12.3. Domain và public suffix

Một client hiện đại cần tránh nhận cookie đặt cho public suffix hoặc domain không thuộc bên phát hành. `ACCEPT_ORIGINAL_SERVER` là kiểm tra gắn cookie với origin/domain ở mức Java API, nhưng không nên mặc định nó thực thi toàn bộ Public Suffix List và browser-grade RFC6265bis rules.

Với một hệ thống nhiều tổ chức/hosts:
- Chỉ connect host nằm trong allowed destinations.
- Không nhận custom arbitrary Domain từ nguồn lạ.
- Không lấy hostname từ untrusted input rồi dùng nó để mở quyền nhận cookies.
- Kiểm tra DNS rebinding/redirect/URL parsing nếu client đi tới URLs do người dùng gửi.
- Gắn cookie jars với tenant/request context; đừng dùng shared singleton.

### 12.4. Các cookie prefix trong hệ sinh thái web

Web cookies có conventions như `__Host-` và `__Secure-`, kèm yêu cầu Secure/Path/Domain ở browser và server. `HttpCookie` của JDK không có API riêng bảo đảm mọi prefix rules, nên custom Java client cần test hoặc enforce rules đúng khi protocol dựa vào chúng.

Đừng giả định vì cookie tên `__Host-session` thì Java tự chứng minh nó do đúng HTTPS origin phát hành.

### 12.5. Header injection và invalid cookies

Không tự ghép `Cookie: ` + raw user input, không dùng `Set-Cookie` value như raw log field, không chấp nhận newline/header injection trong network boundaries. Dùng `HttpCookie.parse` và `CookieManager` nhưng vẫn kiểm thử input bất thường, số lượng headers, sizes và error handling. `HttpCookie.parse` có thể ném `IllegalArgumentException` với cookie sai cú pháp.

### 12.6. Thay đổi policy và concurrent requests

`setCookiePolicy` không phải transaction có khả năng rollback mọi in-flight requests. Nếu ứng dụng đang gửi requests song song:
- Một response có thể đã được `put` trước khi policy được thay đổi.
- CookieStore có thể được truy cập/ghi bởi nhiều threads.
- Việc xóa store có thể race với request đã được tạo headers.
- Logout yêu cầu vô hiệu hóa **session phía server**, không chỉ xóa cookie client.

Vì vậy thay đổi policy động cần lifecycle/synchronization phù hợp; tốt hơn là tạo **client mới với CookieManager mới** cho phiên/boundary mới.

## 13. Thiết kế custom CookieStore đúng trách nhiệm

Nếu cần implementation riêng, lưu ý interface:

```java
public interface CookieStore {
    void add(URI uri, HttpCookie cookie);
    List<HttpCookie> get(URI uri);
    List<HttpCookie> getCookies();
    List<URI> getURIs();
    boolean remove(URI uri, HttpCookie cookie);
    boolean removeAll();
}
```

Đây là bản tóm tắt **chữ ký API**, không phải một class thực thi. Ngoài việc implement đủ method:

**Dữ liệu lưu trữ**
- Cookie key cần thống nhất theo domain/path/name (theo rules của store dùng).
- Lưu creation/expiry metadata chính xác.
- Tránh lỗi serialization khiến cookie biến thành persistent trái ý định.
- Không coi URI association là cách duy nhất để quyết định domain/host matching.

**Khả năng đồng thời**
- Đảm bảo thread-safe giữa `add/get/remove/removeAll`.
- Không trả mutable live list để caller sửa không qua API.
- Nếu trả `HttpCookie` object mutable, cân nhắc defensive copies để tránh shared mutation làm thay đổi policy/data.
- Có quota, cleanup và bảo vệ backend storage nếu có untrusted host gửi nhiều Set-Cookie headers.

**Quan sát**
- Đếm accepted/rejected cookie **names/count** thay vì log values.
- Log policy version, tenant scope, callback duration.
- Không log session IDs.
- Test với path/host/secure/expiry và malformed attributes.

**Quyền truy cập**
- Chỉ các components tin cậy được lấy direct reference tới CookieStore mutable.
- Policy là một lớp **trước khi lưu**; nếu store bị gọi trực tiếp, không có cơ chế tự động gọi policy trừ khi store tự implement.

## 14. Lỗi phổ biến cần tránh

**1. Cho rằng CookiePolicy quyết định mọi lần gửi cookie.**  
Sai: `CookieManager.put` dùng policy để nhận cookie; `get` đọc store và áp cookie attributes.

**2. Gọi `setCookiePolicy(ACCEPT_NONE)` để logout.**  
Nó không tự xóa cookies cũ. Dùng `removeAll` và invalidate session phía server.

**3. Dùng `ACCEPT_ALL` cho tất cả nguồn internet không phân biệt.**  
Policy quá rộng; cần trust-boundary/domain/HTTPS rules và quotas.

**4. Hiểu `new CookieManager(null, null)` là không lưu gì.**  
Nó dùng in-memory store và default original-server policy.

**5. Tự thêm cookie bằng `getCookieStore().add` rồi trông đợi acceptance policy được gọi.**  
Không. Direct store write bypasses `CookieManager.put`.

**6. Chia sẻ một CookieManager global giữa các user sessions.**  
Rủi ro cross-user cookie leakage.

**7. Tin `CookieHandler.setDefault` tự áp dụng mọi Java HTTP client.**  
`HttpClient` có builder `cookieHandler` riêng; phải cấu hình tường minh khi cần.

**8. Mặc định mỗi HttpClient đều có cookie jar persistent.**  
Cookie handler không được cấu hình thì đừng giả định client sẽ giữ cookies như browser.

**9. Lấy cookie names/values từ `Set-Cookie` rồi gửi lại nguyên header đó.**  
Response dùng `Set-Cookie`, request dùng `Cookie`; để handler làm đúng giao thức.

**10. So khớp literal `session=abc` trong header versioned.**  
Có thể được quote như `session="abc"` cùng `$Version`/`$Path`.

**11. Cho rằng cookie có `Secure` sẽ tự chuyển HTTP sang HTTPS.**  
Không. CookieSecure ảnh hưởng gửi cookie, TLS vẫn là trách nhiệm HTTP connection.

**12. Cho rằng `HttpOnly` che giá trị khỏi code Java.**  
Không. Java code giữ cookie jar vẫn đọc `HttpCookie.getValue()`.

**13. Dùng `Path` như access-control boundary.**  
Path scope không thay authorization trên server.

**14. Mong `HttpCookie.getSameSite()` tồn tại trong Java 17/26.**  
Không có method public như vậy trong API hiện hành.

**15. Coi CookieManager là browser-grade RFC6265bis SameSite/PSL/partitioned cookie engine.**  
JDK docs nói `HttpCookie` hỗ trợ một phần RFC6265; cần policy bổ sung nếu có yêu cầu.

**16. Không quản lý Max-Age/Expires/expiry.**  
Expired cookies không nên được trả; custom store phải implement đúng.

**17. Nhầm `Max-Age` giây với milliseconds.**  
Làm sessions sống quá dài hoặc hết hạn sớm.

**18. Lưu cookie vào file plaintext.**  
Session token có thể là bearer credential; encryption/permission/retention matters.

**19. Return mutable backing List trực tiếp từ CookieStore.**  
Vi phạm contract và gây data races/sửa state trái phép.

**20. Dùng một HashMap không đồng bộ với HttpClient đa luồng.**  
Có thể mất cookies, corrupt state hoặc leak.

**21. Đặt nhiều tenants chung jar nhưng chỉ cố phân tách bằng cookie Path.**  
Path không phải tenant identity; dùng separate jars.

**22. Cho phép redirects tới hosts không đáng tin rồi vẫn dùng cookies rộng.**  
Cần HTTP redirect/origin policy riêng.

**23. Không test host/path/scheme khi verify cookie.**  
Chỉ nhìn store size không đủ xác minh cookie không bị gửi sai.

**24. Không test việc đổi policy giữa hai requests.**  
Có thể nhầm policy thay đổi làm cookies cũ biến mất.

**25. Không test logout/clear cookie store.**  
Có thể tiếp tục gửi credential đã cũ.

**26. Chỉ mock CookieManager mà không test HTTP integration.**  
Dễ bỏ sót tự động handling giữa Set-Cookie và Cookie.

**27. Gọi `shouldAccept` trực tiếp với HttpCookie thiếu Domain rồi kết luận behavior của `put` tương đương.**  
CookieManager có thêm ngữ cảnh URI và xử lý cookie header.

**28. Kiểm tra cookie Java như thể đang chạy JavaScript trong browser.**  
Khác security model và SameSite/HttpOnly boundaries.

**29. Log toàn bộ request headers khi có `Cookie`/`Authorization`.**  
Dễ lộ session hoặc access tokens.

**30. Cho rằng policy ACCEPT_ORIGINAL_SERVER tự làm CSRF/XSS protection.**  
Không. Đây là acceptance rule, không phải browser security engine.

## 15. Checklist áp dụng cho dự án

- [ ] Xác định cookie có cần thiết không; bỏ qua cookie handler nếu stateless.
- [ ] Tạo CookieManager riêng theo authenticated session/tenant khi cần.
- [ ] Chọn CookiePolicy rõ ràng, không dùng ACCEPT_ALL chỉ vì tiện.
- [ ] Xem HTTPS/host/name/attributes trong custom acceptance policy.
- [ ] Không coi policy là outbound firewall.
- [ ] Lưu in-memory trừ khi thật sự có nhu cầu persistence.
- [ ] Nếu custom store, implement expiration, matching, quotas, thread safety.
- [ ] Không public direct mutable store cho code không tin cậy.
- [ ] Dùng `HttpClient.Builder.cookieHandler(...)` để isolate clients.
- [ ] Không thay `CookieHandler.setDefault` theo từng user/request.
- [ ] Gắn request timeout/redirect/SSRF and TLS policies riêng.
- [ ] Dùng `remove/removeAll` và invalidate server session khi logout.
- [ ] Test cookie Secure không đi qua HTTP và Path/Domain restrictions.
- [ ] Test `Set-Cookie` và `Cookie` end-to-end trên loopback.
- [ ] Test cookie jar A không bị nhìn thấy bởi client B.
- [ ] Test đổi policy sang ACCEPT_NONE không tự purge state cũ.
- [ ] Hiểu Java `HttpCookie` không cung cấp đầy đủ browser SameSite policy.
- [ ] Không log raw Cookie/Set-Cookie headers hoặc cookie values.
- [ ] Khi nâng cấp JDK, chạy integration tests đúng production runtime/provider.

## 16. Câu hỏi tự kiểm tra

**1. `CookieManager` tách trách nhiệm nào?**  
`CookiePolicy` quyết định nhận cookie, `CookieStore` lưu/tra/xóa cookie.

**2. CookiePolicy callback được gọi ở phía nào của giao tiếp?**  
Thông thường khi `CookieManager.put` xử lý `Set-Cookie` nhận từ **response**.

**3. Nếu policy trả false thì chuyện gì xảy ra?**  
Cookie đó không được `CookieManager` đưa vào `CookieStore.add` qua luồng put.

**4. `CookieManager.get` làm gì?**  
Tạo outgoing cookie-related request headers dựa trên store và URI phù hợp.

**5. Mặc định của `new CookieManager()` là gì?**  
In-memory CookieStore và `ACCEPT_ORIGINAL_SERVER`.

**6. `new CookieManager(null,null)` có nghĩa “không lưu” không?**  
Không; tương đương default manager.

**7. `setCookiePolicy(ACCEPT_NONE)` có xóa cookie cũ không?**  
Không.

**8. Muốn xóa mọi cookie cũ thì gọi gì?**  
`manager.getCookieStore().removeAll()`; nếu là logout còn phải invalidate server session.

**9. Gọi `store.add` trực tiếp có kiểm tra CookiePolicy không?**  
Không tự động.

**10. Tại sao không so raw Cookie header bằng một chuỗi duy nhất?**  
Cookie versioned có thể có quotes hoặc metadata như `$Version`.

**11. Cookie Secure có được gửi qua URI http không?**  
Theo policy secure transport phải không; fixture xác minh không gửi trong test.

**12. `HttpOnly` có chặn Java code đọc cookie value không?**  
Không.

**13. `SameSite` có setter/getter public trên `java.net.HttpCookie` hiện hành không?**  
Không.

**14. Dùng gì để cấu hình cookies trên modern Java HttpClient?**  
`HttpClient.newBuilder().cookieHandler(manager)`.

**15. Có nên dùng một CookieManager cho mọi tenants không?**  
Không nếu cookies mang session/identity; cần isolation.

**16. CookieStore.getCookies() có nên trả expired cookies không?**  
Không. Contract nói danh sách cookies chưa hết hạn.

**17. Một CookiePolicy strict có thay thế hostname verification của TLS không?**  
Không; hai lớp bảo vệ hoàn toàn khác.

**18. Một cookie Path có thay authorization không?**  
Không.

**19. Nếu muốn persist cookies qua restart JVM, built-in memory store đã đủ chưa?**  
Chưa. Cần store hỗ trợ persistence và security.

**20. Vì sao test real HttpClient và HttpServer có giá trị?**  
Nó xác minh tự động luồng `Set-Cookie` → jar A → `Cookie` request tiếp theo, cùng sự cô lập jar B.

**21. 46/46 PASS chứng minh mọi browser cookie semantics không?**  
Không; nó kiểm thử JDK 24 trên các input đã chọn. Application vẫn phải quản lý security/modern cookie rules riêng.

## 17. Tài liệu hiện hành Java SE 26

- [Java SE 26 — `CookieManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieManager.html): tách CookiePolicy và CookieStore, constructors, `get`/`put`, policy mặc định.
- [Java SE 26 — `CookiePolicy`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookiePolicy.html): `shouldAccept`, `ACCEPT_ALL`, `ACCEPT_NONE`, `ACCEPT_ORIGINAL_SERVER`.
- [Java SE 26 — `CookieStore`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieStore.html): lưu/tra/xóa, expired cookie handling, contract cho custom store.
- [Java SE 26 — `HttpCookie`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/HttpCookie.html): domain/path/secure/HttpOnly/maxAge/version, partial RFC6265 support.
- [Java SE 26 — `CookieHandler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/CookieHandler.html): callback get/put và global default cho URL protocol handler.
- [Java SE 26 — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `cookieHandler(CookieHandler)` theo client.
- [Java SE 26 — `HttpServer`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback integration test server.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265): chuẩn cookie mà Java `HttpCookie` công bố chỉ hỗ trợ một phần.

**Tổng kết:** Trong Java, **`CookieManager` kết nối hai khái niệm khác nhau**: `CookiePolicy` quyết định cookie **có được nhận lúc put hay không**, còn `CookieStore` lưu và cung cấp cookies cho các request tiếp theo. **Thay policy không xóa cookies cũ**, còn **ghi trực tiếp vào store không đi qua policy**. Dùng cookie jar riêng cho mỗi HTTP client/session, áp TLS và host policy riêng, quản lý cleanup/expiry và không nhầm Java networking cookie model với browser-grade SameSite/CSRF security.
