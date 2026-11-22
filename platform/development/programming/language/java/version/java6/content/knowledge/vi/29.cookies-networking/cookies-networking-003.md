# CookiePolicy, CookieStore và kho lưu tùy biến trong Java 17+

## 1. Bài toán: khi nào nhận cookie, lưu ở đâu và gửi cho ai?

Một ứng dụng Java đóng vai **HTTP client** thường gọi dịch vụ có phiên đăng nhập, dashboard nội bộ, API hoặc trang quản trị. Server gửi header `Set-Cookie`; client cần quyết định **có lưu cookie hay không**, **lưu bao lâu**, và **được phép gửi lại cookie nào** khi gọi URL tiếp theo. Nếu ứng dụng nhiều tài khoản hoặc tenants dùng chung cookie jar, cookies phiên đăng nhập có thể bị gửi sang sai người dùng hoặc sai dịch vụ.

Bốn API Java vẫn còn hiện hành trong **Java 17+ và JDK 25**:

- `java.net.CookiePolicy`: kiểm tra **cookie mới được nhận** có được chấp nhận hay không.
- `java.net.CookieStore`: lưu trữ, tìm kiếm, thay thế, hết hạn và xóa `HttpCookie`.
- `java.net.CookieManager`: phối hợp policy với store, chuyển `Set-Cookie` response thành cookies được lưu và tạo `Cookie` request.
- `java.net.http.HttpClient.Builder.cookieHandler(...)`: gắn một `CookieManager` riêng cho một HTTP client hiện đại.

Điểm cốt lõi: **nhận, lưu và gửi lại là ba quyết định khác nhau**. Thay `CookiePolicy` thành `ACCEPT_NONE` ngừng nhận cookie **tương lai**, nhưng **không xóa những cookie đã được lưu**. Một custom `CookieStore` không tự thay logic chấp nhận ban đầu của `CookiePolicy`. Và `HttpClient` chỉ dùng jar mong muốn khi bạn gắn đúng handler.

~~~text
Server HTTP response
    Set-Cookie: session=...; Path=/private; Secure; HttpOnly; Max-Age=120
                         |
                         v
                  CookieManager.put
                         |
                 CookiePolicy.shouldAccept
                   /               \
                accept            reject
                  |                 |
            CookieStore.add      không lưu
                  |
              in-memory jar
                  |
      HttpClient request to matching URI
                  |
             CookieManager.get
                  |
             CookieStore.get
                  |
        Domain/Path/Secure/expiry filtering
                  |
                  v
           Cookie: session=...
~~~

`CookiePolicy` **không phải** là lớp kiểm tra quyền truy cập ở server; cookie chỉ là vật mang trạng thái. Server vẫn phải xác thực session token và áp authorization độc lập.

## 2. Bản đồ lớp và phạm vi module

| Lớp/Interface | Module | Vai trò |
| --- | --- | --- |
| `CookieHandler` | `java.base` | API xử lý cookie ở ranh giới HTTP headers |
| `CookieManager` | `java.base` | Implementation `CookieHandler` phối hợp policy/store |
| `CookiePolicy` | `java.base` | Quyết định accept/reject cookie đến |
| `CookieStore` | `java.base` | Kho HTTP cookies và vòng đời |
| `HttpCookie` | `java.base` | Cookie name/value, domain/path, flags và max-age |
| `HttpClient` | `java.net.http` | HTTP client Java 11+ có `Builder.cookieHandler` |
| `HttpURLConnection` | `java.base` | HTTP client cũ vẫn dùng được; có liên quan global `CookieHandler` |
| `HttpServer` | `jdk.httpserver` | Server nhúng dùng trong integration test loopback |

`java.net.CookiePolicy` không liên quan `java.security.Policy` hoặc cookie policy của trình duyệt JavaScript. API server `com.sun.net.httpserver.HttpServer` là thành phần khác: nó trả `Set-Cookie`, còn `CookieManager` trong bài chạy ở **phía client**.

Dùng `CookieManager` đúng chỗ giúp giảm state management thủ công:

~~~java
CookieManager manager = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(manager)
        .build();
~~~

Đoạn này hợp lệ trong method có imports phù hợp. `store=null` yêu cầu JDK tạo default **in-memory CookieStore**. Nếu `policy=null`, policy mặc định cũng là `ACCEPT_ORIGINAL_SERVER`. `CookieManager()` tương đương constructor với hai tham số `null`.

**Không** lạm dụng `CookieHandler.setDefault(...)` để quản lý phiên nhiều users, bởi nó thay default handler cho những thành phần dùng global state trong JVM. Trong Java 17+, ưu tiên `HttpClient.Builder.cookieHandler(manager)` để xây jar riêng cho client/tenant/session.

## 3. Set-Cookie khác Cookie, và vì sao có attributes

Server có thể gửi:

~~~http
HTTP/1.1 200 OK
Set-Cookie: sid=abc123; Path=/account; Max-Age=1800; Secure; HttpOnly
Content-Type: text/plain; charset=UTF-8

OK
~~~

Sau khi policy chấp nhận, một request HTTPS tới đúng phạm vi có thể gửi:

~~~http
GET /account/me HTTP/1.1
Host: api.example.test
Cookie: sid=abc123
~~~

`Set-Cookie` chứa chỉ thị lưu trữ và scope, còn `Cookie` thông thường chứa name=value cần gửi lại. Client không gửi các thuộc tính `Secure`, `Path`, `HttpOnly` như một bằng chứng xác thực. Các thuộc tính này cần được áp tại client/browser khi quyết định gửi cookie.

| Thuộc tính | Ý nghĩa | Điều cần tránh |
| --- | --- | --- |
| `Name=Value` | Dữ liệu trạng thái | Chứa password hoặc credential trong log |
| `Domain` | Phạm vi domain/subdomain | Chấp nhận domain quá rộng |
| `Path` | Phạm vi đường dẫn gửi cookie | Coi Path là cơ chế phân quyền |
| `Secure` | Giới hạn gửi qua kết nối secure, thông thường HTTPS | Coi Secure thay TLS certificate validation |
| `HttpOnly` | Với browser, cấm một số non-HTTP APIs đọc cookie | Nghĩ rằng code Java không đọc được cookie jar |
| `Max-Age` | Thời hạn tương đối (giây), 0 để hết hạn, -1 thường là session | Coi số này là timestamp tuyệt đối |
| `Expires` | Mốc thời gian hết hạn trong header | Bỏ qua khác biệt với Max-Age |
| `SameSite` | Hạn chế request cross-site trong browser | Cho rằng Java CookieManager thực thi như Chrome |
| `Partitioned` | Tách cookie theo partitioning context | Giả định Java HttpCookie có partition key đầy đủ |

Khi gửi nhiều cookies, dùng **nhiều header `Set-Cookie` riêng**, không tùy tiện gộp chúng bằng dấu phẩy, đặc biệt nếu có `Expires` chứa dấu phẩy:

~~~http
Set-Cookie: sid=...; Path=/; Secure; HttpOnly
Set-Cookie: lang=vi; Path=/; Secure
~~~

Mẫu này có tính minh họa, không chứa token thật.

## 4. `CookiePolicy`: ba chính sách có sẵn

`CookiePolicy` là functional interface có method:

~~~java
boolean shouldAccept(URI uri, HttpCookie cookie);
~~~

Ba lựa chọn public:

~~~java
CookiePolicy.ACCEPT_ALL
CookiePolicy.ACCEPT_NONE
CookiePolicy.ACCEPT_ORIGINAL_SERVER
~~~

| Chính sách | Hành vi chính | Khi phù hợp |
| --- | --- | --- |
| `ACCEPT_ALL` | Cho phép nhận mọi cookies được đưa cho callback | Chỉ khi nguồn đã được kiểm soát; không là default bảo mật |
| `ACCEPT_NONE` | Không lưu cookies mới | Client stateless hoặc chủ động từ chối cookies |
| `ACCEPT_ORIGINAL_SERVER` | Chỉ chấp nhận cookies từ server gốc theo JDK implementation | Baseline hữu ích, không thay security profile cookie browser hiện đại |

`CookiePolicy.ACCEPT_ORIGINAL_SERVER` **không tự kiểm tra certificate/TLS chain, SameSite, public suffix hay partitioning như browser**. Với dịch vụ nhạy cảm, nên viết custom policy chặt hơn, ví dụ:

~~~java
CookiePolicy strict = (uri, cookie) ->
        "https".equalsIgnoreCase(uri.getScheme())
        && "api.example.test".equalsIgnoreCase(uri.getHost())
        && cookie.getSecure()
        && cookie.isHttpOnly()
        && cookie.getMaxAge() > 0
        && cookie.getMaxAge() <= 3600
        && CookiePolicy.ACCEPT_ORIGINAL_SERVER.shouldAccept(uri, cookie);
~~~

Đây là đoạn trích từ chương trình ở phần 8. Nó **cố ý** chỉ nhận cookies Secure+HttpOnly có thời gian tồn tại 1–3600 giây từ đúng HTTPS host. Chính sách này **từ chối session cookie có Max-Age=-1**, phù hợp một demo strict nhưng không phải quy tắc áp dụng cho mọi app. Nếu nghiệp vụ cần session cookies, thay đổi điều kiện Max-Age theo policy đã được duyệt.

Các tiêu chí cần cân nhắc cho custom policy:
1. Cho phép những schemes nào: HTTPS mới hay có exception loopback?
2. Host/origin nào nằm trong allowlist? Có canonicalize IDN/IPv6 không?
3. Cookie có `Domain` quá rộng không? Host-only, subdomain policy và PSL?
4. Có yêu cầu `Secure`, `HttpOnly` và TTL tối đa với session token?
5. Có chấp nhận session cookies không có Max-Age không?
6. Token/personal information có bị gửi sang endpoint không liên quan không?

**Cảnh báo quan trọng:** `CookiePolicy` quyết định lúc `CookieManager.put(...)`, tức **nhận** Set-Cookie; nó không được gọi như một authorization callback cho mỗi request đi ra. Cookie đã được lưu vẫn có thể xuất hiện trong `CookieManager.get(...)` sau khi policy thay đổi.

~~~java
manager.setCookiePolicy(CookiePolicy.ACCEPT_NONE);
// Chặn cookie mới; cookie cũ vẫn lưu.
boolean cleared = manager.getCookieStore().removeAll();
~~~

`setCookiePolicy(null)` theo Javadoc không thay chính sách cũ; đừng coi nó là “reset to default”.

## 5. `CookieStore`: đủ sáu operations

Interface lưu trữ có contract:

~~~java
void add(URI uri, HttpCookie cookie);
List<HttpCookie> get(URI uri);
List<HttpCookie> getCookies();
List<URI> getURIs();
boolean remove(URI uri, HttpCookie cookie);
boolean removeAll();
~~~

**`add`:** nhận một cookie, có thể gắn với một `URI` hoặc `uri=null` nếu cookie tự có Domain/Path. Khi cookie tương ứng đã tồn tại, store nên thay thế theo semantics identity. `HttpCookie.equals` xét name/domain/path; cookie cùng name ở hai domain/path có thể cùng tồn tại. Đừng dùng một `Map<String, String>` chỉ key theo name.

**`get(uri)`:** trả cookies còn hiệu lực liên quan URI/domain theo store contract. `CookieManager.get(uri, requestHeaders)` còn chuyển thành request headers và xử lý thêm scope như Path/Secure theo implementation. Hai methods **không giống nhau** và không trả cùng kiểu dữ liệu.

**`getCookies()`:** trả toàn bộ cookies chưa hết hạn. Javadoc mô tả list trả về không được sửa. Nhưng `HttpCookie` là **mutable**; nếu một store đưa thẳng đối tượng nội bộ ra ngoài, code khác có thể gọi `setValue`, `setPath` làm hỏng state. Custom store trong bài trả snapshot clones.

**`getURIs()`:** liệt kê các URI đã liên kết cookies, không phải một danh sách mọi host có thể match Domain. Với `add(null, cookie)`, một cookie có thể không có URI association.

**`remove(uri,cookie)`:** xóa cookie tương ứng, trả true nếu đã có và bị xóa. Với cookie liên kết URI cần truyền URI phù hợp; dùng một URI bất kỳ không bảo đảm xóa đúng.

**`removeAll()`:** clear toàn jar, trả true khi có thay đổi. Đây là một hành động **local client-side**, không có chức năng revoke server session/token.

**Hết hạn:** store chịu trách nhiệm không trả cookies đã expired. `HttpCookie.hasExpired()` và `getMaxAge()` hỗ trợ kiểm tra; một persistent store cần tuyệt đối cẩn thận khi chuyển Max-Age thành thời điểm hết hạn sau restart. Không khôi phục Max-Age cũ như một thời gian sống mới vô hạn.

## 6. Vì sao nên dùng composition để viết kho tùy biến?

Để custom một cookie jar đầy đủ từ đầu, bạn phải triển khai cả Domain/Path matching, expiry, Host-only, Secure, cookie prefixes, public suffix, nhiều cookies trùng name nhưng khác scope, thread-safety, TTL và cleanup. Rất dễ viết một Map sai khiến session cookie bị gửi sang domain khác.

Bài dùng **composition**: tự viết `BoundedCookieStore implements CookieStore` nhưng **ủy quyền các thao tác matching cơ bản** cho in-memory CookieStore được tạo bởi `new CookieManager().getCookieStore()`:

~~~text
CookieManager
    |
    +-- CookiePolicy: nhận/từ chối cookies mới
    |
    +-- BoundedCookieStore implements CookieStore
             |
             +-- delegate JDK in-memory CookieStore
             +-- quota số cookie còn hiệu lực
             +-- quota độ dài name+value
             +-- clone object khi add và get
             +-- synchronized operations
             +-- remove, removeAll, expire qua delegate
~~~

Các giới hạn quan trọng:
- Quota `maxChars` đếm **Java UTF-16 code units** của name+value; không phải giới hạn bytes đầy đủ của HTTP header, không tính Domain/Path và overhead.
- Quota số lượng từ chối cookie mới khi đầy. Với session thực, một số server cần refresh; may mắn là code cho phép **thay thế cookie cùng identity** ngay cả khi jar đầy.
- Không có eviction strategy (LRU) hay per-domain quota; production nên thiết kế rõ thay vì âm thầm mất cookies.
- JDK delegate có semantics của CookieManager JDK, không tự là browser jar hiện đại về SameSite/partitioned/public suffix.
- Không có persistence, encryption, backup, key rotation hoặc token revocation; đây là ví dụ **in-memory**.

### Defensive copying

~~~java
private static List<HttpCookie> snapshot(List<HttpCookie> cookies) {
    return cookies.stream().map(c -> (HttpCookie) c.clone()).toList();
}
~~~

Java `Stream.toList()` (Java 16+) trả unmodifiable list, còn mỗi `HttpCookie.clone()` tách đối tượng mutable. Nhưng **value vẫn là secret có thể đọc từ clone**, nên đừng cung cấp snapshot cho thành phần không được tin hoặc in cả danh sách ra logs.

### Thread-safety

Code dùng `synchronized` cho mọi method store vì check `getCookies().size()` rồi `add(...)` phải atomic trong cùng lock. Nếu chỉ dùng `ConcurrentHashMap` mà thực hiện check-then-act qua nhiều operations, hai requests đồng thời có thể cùng thấy capacity chưa đầy rồi làm vượt quota. Trong production cần đo lock contention và lựa chọn jar per session thay vì một jar toàn bộ tenants.

## 7. HttpClient riêng hay CookieHandler mặc định toàn JVM?

Đối với Java 17+:

~~~java
CookieManager privateManager =
        new CookieManager(new BoundedCookieStore(100, 4096),
                CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient client = HttpClient.newBuilder()
        .cookieHandler(privateManager)
        .build();
~~~

Đây là đoạn ví dụ trong class có `BoundedCookieStore` từ phần 8. Mỗi tenant/session dùng một manager khác nhau nếu không được phép chia sẻ cookies. Không tạo một jar static global rồi dùng giữa Alice và Bob.

Mặc dù có API:

~~~java
CookieHandler.setDefault(new CookieManager());
~~~

đây là một **điều chỉnh global** cho các clients biết dùng default `CookieHandler`, bao gồm các đường `HttpURLConnection`. Không nên chọn cách này để làm ranh giới giữa tenants. `HttpClient.newBuilder().cookieHandler(manager)` rõ ràng hơn và test dễ hơn.

`HttpClient.Builder.authenticator(...)` (với `java.net.Authenticator`) là một cơ chế HTTP authentication **khác**; nó không tự thay vai trò cookie jar hoặc lưu mọi `Set-Cookie`.

## 8. Mã Java 17+ hoàn chỉnh và có kiểm thử thực tế

Chương trình **`CookiePolicyStoreDemo.java`** thực hiện hai nhóm test:

1. **Không cần network:** gọi `CookieManager.put/get` với URI HTTPS giả `api.example.test`; chứng minh strict accept, Path, Secure, HttpOnly, replacement, capacity, ACCEPT_NONE và removeAll.
2. **Loopback HTTP integration:** chạy `HttpServer` trên `127.0.0.1` và port ngẫu nhiên; `HttpClient` có cookieHandler nhận `Set-Cookie` từ `/app/start`, gửi lại tới `/app/check` nhưng không gửi tới `/outside`. Một HttpClient khác không gắn handler không chia sẻ jar; sau `removeAll` cũng không gửi lại cookie.

**Bảo mật:** HTTP plaintext chỉ dùng ở loopback với dữ liệu giả `sid=demo`. Không dùng cookie đăng nhập thật trên HTTP công khai, không bind server lên `0.0.0.0`. Đối với client/servers thật cần HTTPS/TLS và kiểm tra certificates.

Tạo file `CookiePolicyStoreDemo.java` với nội dung:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.CookieStore;
import java.net.HttpCookie;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class CookiePolicyStoreDemo {
    static final class BoundedCookieStore implements CookieStore {
        private final CookieStore delegate = new CookieManager().getCookieStore();
        private final int capacity;
        private final int maxChars;
        private int dropped;

        BoundedCookieStore(int capacity, int maxChars) {
            if (capacity < 1 || maxChars < 1) throw new IllegalArgumentException();
            this.capacity = capacity;
            this.maxChars = maxChars;
        }

        @Override public synchronized void add(URI uri, HttpCookie cookie) {
            Objects.requireNonNull(cookie, "cookie");
            // Let the JDK store process a Max-Age=0 deletion/replacement.
            if (cookie.hasExpired() || cookie.getMaxAge() == 0) {
                delegate.add(uri, (HttpCookie) cookie.clone());
                return;
            }
            int chars = cookie.getName().length()
                    + (cookie.getValue() == null ? 0 : cookie.getValue().length());
            if (chars > maxChars) {
                dropped++;
                return;
            }
            boolean replacing = delegate.getCookies().stream()
                    .anyMatch(saved -> saved.equals(cookie));
            if (!replacing && delegate.getCookies().size() >= capacity) {
                dropped++;
                return;
            }
            delegate.add(uri, (HttpCookie) cookie.clone());
        }

        private static List<HttpCookie> snapshot(List<HttpCookie> cookies) {
            return cookies.stream().map(c -> (HttpCookie) c.clone()).toList();
        }

        @Override public synchronized List<HttpCookie> get(URI uri) {
            Objects.requireNonNull(uri, "uri");
            return snapshot(delegate.get(uri));
        }

        @Override public synchronized List<HttpCookie> getCookies() {
            return snapshot(delegate.getCookies());
        }

        @Override public synchronized List<URI> getURIs() {
            return List.copyOf(delegate.getURIs());
        }

        @Override public synchronized boolean remove(URI uri, HttpCookie cookie) {
            Objects.requireNonNull(cookie, "cookie");
            return delegate.remove(uri, cookie);
        }

        @Override public synchronized boolean removeAll() {
            return delegate.removeAll();
        }

        synchronized int droppedCount() { return dropped; }
    }

    static boolean hasCookie(Map<String, List<String>> headers, String name) {
        return headers.entrySet().stream()
                .filter(e -> e.getKey().equalsIgnoreCase("Cookie"))
                .flatMap(e -> e.getValue().stream())
                .anyMatch(line -> line.contains(name + "="));
    }

    static boolean hasCookie(HttpExchange exchange, String name) {
        return exchange.getRequestHeaders().getOrDefault("Cookie", List.of())
                .stream().anyMatch(line -> line.contains(name + "="));
    }

    static void respond(HttpExchange exchange, int status, String text)
            throws IOException {
        byte[] content = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(status, content.length);
        try (var output = exchange.getResponseBody()) {
            output.write(content);
        }
    }

    static String get(HttpClient client, URI base, String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(base.resolve(path))
                .timeout(Duration.ofSeconds(5)).GET().build();
        return client.send(request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)).body();
    }

    public static void main(String[] args) throws Exception {
        BoundedCookieStore store = new BoundedCookieStore(2, 128);
        CookiePolicy strict = (uri, cookie) ->
                "https".equalsIgnoreCase(uri.getScheme())
                && "api.example.test".equalsIgnoreCase(uri.getHost())
                && cookie.getSecure()
                && cookie.isHttpOnly()
                && cookie.getMaxAge() > 0
                && cookie.getMaxAge() <= 3600
                && CookiePolicy.ACCEPT_ORIGINAL_SERVER.shouldAccept(uri, cookie);
        CookieManager manager = new CookieManager(store, strict);
        URI origin = URI.create("https://api.example.test/secure/login");
        manager.put(origin, Map.of("Set-Cookie", List.of(
                "sid=alpha; Path=/secure; Secure; HttpOnly; Max-Age=120")));
        System.out.println("strict accepted: " + store.getCookies().size());
        System.out.println("secure path sent: " + hasCookie(manager.get(
                URI.create("https://api.example.test/secure/home"), Map.of()), "sid"));
        System.out.println("other path sent: " + hasCookie(manager.get(
                URI.create("https://api.example.test/outside"), Map.of()), "sid"));
        System.out.println("plain HTTP sent: " + hasCookie(manager.get(
                URI.create("http://api.example.test/secure/home"), Map.of()), "sid"));

        manager.put(origin, Map.of("Set-Cookie", List.of(
                "analytics=one; Path=/secure; Secure; Max-Age=120")));
        System.out.println("no HttpOnly rejected: " + (store.getCookies().size() == 1));

        manager.put(origin, Map.of("Set-Cookie", List.of(
                "sid=beta; Path=/secure; Secure; HttpOnly; Max-Age=120")));
        System.out.println("same identity replaced: " + (store.getCookies().size() == 1
                && store.getCookies().get(0).getValue().equals("beta")));

        manager.put(origin, Map.of("Set-Cookie", List.of(
                "pref=ok; Path=/secure; Secure; HttpOnly; Max-Age=120")));
        manager.put(origin, Map.of("Set-Cookie", List.of(
                "extra=overflow; Path=/secure; Secure; HttpOnly; Max-Age=120")));
        System.out.println("bounded cookie count: " + store.getCookies().size());
        System.out.println("capacity rejection counted: " + store.droppedCount());

        manager.setCookiePolicy(CookiePolicy.ACCEPT_NONE);
        manager.put(origin, Map.of("Set-Cookie", List.of(
                "new=blocked; Path=/secure; Secure; HttpOnly; Max-Age=120")));
        System.out.println("policy changes future acceptance only: "
                + (store.getCookies().size() == 2));
        System.out.println("removeAll cleared: "
                + (store.removeAll() && store.getCookies().isEmpty()));

        BoundedCookieStore localStore = new BoundedCookieStore(3, 128);
        CookieManager localManager =
                new CookieManager(localStore, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        server.setExecutor(workers);
        server.createContext("/app", exchange -> {
            try {
                String path = exchange.getRequestURI().getPath();
                if (path.equals("/app/start")) {
                    exchange.getResponseHeaders().add("Set-Cookie",
                            "sid=demo; Path=/app; HttpOnly; Max-Age=120");
                    respond(exchange, 200, "issued");
                } else if (path.equals("/app/check")) {
                    respond(exchange, 200,
                            Boolean.toString(hasCookie(exchange, "sid")));
                } else {
                    respond(exchange, 404, "not found");
                }
            } finally {
                exchange.close();
            }
        });
        server.createContext("/outside", exchange -> {
            try {
                respond(exchange, 200,
                        Boolean.toString(hasCookie(exchange, "sid")));
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient withCookies = HttpClient.newBuilder()
                    .cookieHandler(localManager)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpClient isolated = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            System.out.println("local first response: "
                    + get(withCookies, base, "/app/start"));
            System.out.println("local replay: "
                    + get(withCookies, base, "/app/check"));
            System.out.println("local outside path: "
                    + get(withCookies, base, "/outside"));
            System.out.println("separate client without handler: "
                    + get(isolated, base, "/app/check"));
            System.out.println("local store count: "
                    + localStore.getCookies().size());
            System.out.println("local removeAll: " + localStore.removeAll());
            System.out.println("local after logout: "
                    + get(withCookies, base, "/app/check"));
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

Chạy từ thư mục chứa file, với JDK 17 trở lên:

~~~bash
javac --release 17 --add-modules jdk.httpserver CookiePolicyStoreDemo.java
java --add-modules jdk.httpserver CookiePolicyStoreDemo
~~~

**Stdout chính xác** đã biên dịch và chạy trên OpenJDK 24.0.2, target Java 17:

~~~text
strict accepted: 1
secure path sent: true
other path sent: false
plain HTTP sent: false
no HttpOnly rejected: true
same identity replaced: true
bounded cookie count: 2
capacity rejection counted: 1
policy changes future acceptance only: true
removeAll cleared: true
local first response: issued
local replay: true
local outside path: false
separate client without handler: false
local store count: 1
local removeAll: true
local after logout: false
~~~

### Phân tích kết quả

- `strict accepted: 1`: Strict CookiePolicy nhận cookie `sid` từ đúng HTTPS host, có Secure+HttpOnly, Max-Age 120.
- `secure path sent: true`: `CookieManager.get` trả Cookie header cho `/secure/home`.
- `other path sent: false` và `plain HTTP sent: false`: không gửi vượt Path hoặc chuyển sang HTTP plaintext.
- `no HttpOnly rejected: true`: strict policy từ chối một cookie khác thiếu HttpOnly.
- `same identity replaced: true`: `sid=beta` thay `sid=alpha`, vẫn chỉ có một cookie identity tương ứng.
- `bounded cookie count: 2`: chỉ `sid` và `pref` được lưu. `extra` bị từ chối vì jar đã đạt capacity.
- `capacity rejection counted: 1`: counter đo số cookie bị chặn do quota, không in value.
- `policy changes future acceptance only: true`: chuyển sang ACCEPT_NONE ngăn nhận `new` nhưng không xóa hai cookie cũ.
- `removeAll cleared: true`: jar đầu đã rỗng.
- `local first response: issued`: server loopback trả Set-Cookie.
- `local replay: true`: HttpClient đã gắn handler tự gửi lại `sid=demo` tới `/app/check`.
- `local outside path: false`: đúng Path=/app, /outside không có cookie ấy.
- `separate client without handler: false`: client độc lập không nhận jar của client thứ nhất.
- `local store count: 1`: store gắn với HttpClient có một cookie sau response đầu.
- `local removeAll: true` và `local after logout: false`: xóa jar khiến request sau không gửi sid.

**Phạm vi kiểm chứng:** demo không có TLS thật, không dùng hostname thật, không chứng minh browser-grade SameSite/partitioned-cookie semantics, và không đảm bảo mọi provider/JDK sẽ luôn xử lý từng trường hợp giống hệt. Nó chứng minh đầy đủ đường phối hợp CookiePolicy–CookieManager–CookieStore–HttpClient trong một JDK đã thử nghiệm.

## 9. Giải thích những đoạn thiết kế đáng chú ý

### 9.1. Cho phép replacement khi store đầy

~~~java
boolean replacing = delegate.getCookies().stream()
        .anyMatch(saved -> saved.equals(cookie));
if (!replacing && delegate.getCookies().size() >= capacity) {
    dropped++;
    return;
}
delegate.add(uri, (HttpCookie) cookie.clone());
~~~

Không nên từ chối refresh cookie cùng identity chỉ vì đạt capacity. Nhưng `HttpCookie.equals` chỉ một phần của mô hình identity; với các yêu cầu partitioning/portlist/protocol đặc biệt, cần tiêu chuẩn và tests riêng.

### 9.2. Expired và Max-Age=0

~~~java
if (cookie.hasExpired() || cookie.getMaxAge() == 0) {
    delegate.add(uri, (HttpCookie) cookie.clone());
    return;
}
~~~

Đoạn này để delegate xử lý cookie expired/deletion, thay vì để check quota ngăn đường xóa cookie. Tuy nhiên một custom store phải kiểm tra riêng behavior `Max-Age=0` theo implementation. Nếu muốn xóa đúng một cookie, `CookieStore.remove(uri,cookie)` là API trực tiếp; cần đúng URI association và identity.

### 9.3. Immutable list không đồng nghĩa immutable cookie

`getCookies()` trả list không sửa được, nhưng `HttpCookie` có setters. Wrapper trả clones để caller không đổi trực tiếp cookie nội bộ. Điều này chỉ bảo vệ state, **không bảo mật giá trị cookie** trước Java code được nhận snapshot.

### 9.4. Synchronized chỉ trong store

`synchronized` khiến operation quota atomic, nhưng `CookiePolicy` có mutable state riêng vẫn cần thread safety. Đừng dùng một `CookieManager` toàn cục cho các tenants rồi tin rằng lock bảo vệ được phân tách session. Bảo mật ranh giới bằng cách tạo jar riêng, policy riêng và kiểm soát caller.

### 9.5. Đừng dùng counter như một log session

In `droppedCount`, `getCookies().size()` có thể hữu ích; in raw `HttpCookie.toString()` hay `Cookie` header có thể làm rò rỉ session. Log lỗi policy bằng mã lý do và correlation ID đã sanitize, tránh cookie value, Set-Cookie, Authorization và raw URLs chứa secrets.

## 10. Domain, Path, Secure, HttpOnly và browser semantics

### Domain và host-only

Với header:

~~~http
Set-Cookie: sid=example; Path=/; Secure; HttpOnly
~~~

browser profile thường xem cookie không có Domain là **host-only**. Khi thêm `Domain=example.test`, cookie có thể áp dụng cho subdomains phù hợp, làm tăng rủi ro session fixation hoặc cross-subdomain trust boundary. `CookiePolicy.ACCEPT_ORIGINAL_SERVER` của JDK không thay thế public-suffix validation/browser rules. Nếu ứng dụng bảo mật đòi exact hostname, phải có policy/implementation rõ, không chỉ dùng default.

### Path không phải authorization

Cookie có `Path=/secure` không tự khiến `/secure` được bảo vệ bằng quyền truy cập. Nó chỉ ảnh hưởng cookie được gửi ở URI nào. HTTP server phải kiểm tra session, quyền, tenant và CSRF policy riêng. Test prefix matching và URL encoding để tránh rò rỉ sang đường dẫn không mong muốn.

### Secure không thay thế TLS

`Secure` chỉ là một flag hạn chế gửi cookie trên URL không secure. Nó không chứng minh certificate hợp lệ, không mã hóa payload và không ngăn active attacker trong mọi trường hợp. Dùng HTTPS/TLS với xác thực hostname/certificate, tránh redirect downgrade và không ghi tokens vào logs.

### HttpOnly khác với bảo mật trong Java

`HttpOnly` giúp hạn chế JavaScript/browser APIs đọc cookie. Nó không ngăn `java.net.HttpCookie.getValue()` khi Java code được trao CookieStore. Đừng nhầm browser controls với Java process isolation.

### SameSite và Partitioned

`SameSite=Strict/Lax/None` phụ thuộc vào top-level site, loại navigation, phương thức và cross-site context của **browser**. `Partitioned` yêu cầu partition key theo mô hình website. Java `HttpCookie` hiện hành không cung cấp một mô hình đầy đủ cho SameSite hoặc partition key như trình duyệt. **Không** lấy kết quả của `CookieManager.get` rồi kết luận browser sẽ gửi cùng cookie trong một tình huống CSRF/OAuth login.

Đối với web app **server-side**, cấu hình attributes đúng trong `Set-Cookie` của HTTP response và dùng các CSRF defenses độc lập. Với browser automation, dùng browser cookie APIs thay cho JDK cookie jar nếu cần mô phỏng SameSite/partitioning.

### Port không phải ranh giới cookie tin cậy

Cookies theo HTTP state rules không cô lập theo port như ranh giới same-origin gồm scheme/host/port. Hai dịch vụ khác port nhưng cùng hostname có thể tương tác với cookies trong những điều kiện nhất định. Nếu hai tenants hoặc hai trust zones cùng hostname nhưng khác port, **không** dựa vào cookie scope như một hàng rào cách ly chắc chắn; cần separation bằng hostnames, keys và server-side identity.

## 11. Thời hạn và logout

`Max-Age > 0`: cookie có lifetime tương đối theo giây. `Max-Age = 0`: cơ chế xóa/expire cùng identity. `Max-Age = -1` trên `HttpCookie` thường là session cookie không có thời hạn cụ thể. CookieStore phải loại expired cookies.

Logout nên gồm hai phía:

~~~text
Client:
  CookieStore.remove hoặc removeAll
  không tái sử dụng client/session jar cũ
  cleanup các resources và private session state

Server:
  invalidate/revoke session hoặc refresh token
  phát Set-Cookie với Max-Age=0 đúng Name/Domain/Path
  kiểm tra expiry, replay, token rotation
~~~

Chỉ gọi `removeAll()` ở client **không** thu hồi cookie đã bị sao chép bởi attacker hoặc một process khác. Server-side revocation vẫn cần khi logout có ý nghĩa bảo mật.

Thay cookie cùng tên nhưng khác Domain/Path có thể tạo identity khác. Vì vậy header hết hạn cần đúng Path/Domain của cookie gốc. Nếu không, app tưởng đã logout nhưng cookie cũ có thể vẫn tồn tại trong jar.

## 12. Khi nào cần persistent CookieStore?

JDK in-memory store phù hợp HTTP client dùng trong một process. Nếu CLI/app cần giữ phiên qua restart, có thể cần custom persistent store, nhưng đó là nhiệm vụ bảo mật riêng:

| Vấn đề | Yêu cầu |
| --- | --- |
| Metadata | Name/value/domain/path/secure/httpOnly/creation/expiry/portlist |
| Lifetime | Lưu absolute expiry và tính lại đúng sau restart; không reset Max-Age |
| Security | Encrypt-at-rest, file permissions, secret key management |
| Identity | Per user/tenant/store isolation, không trộn cookies |
| Atomicity | Ghi file atomic, chống corruption khi crash |
| Concurrency | Multiple threads/processes, lock/versioning |
| Quota | Per-host/per-session count, size, TTL, cleanup |
| Logout | Purge local store và revoke remote session |
| Migration | Format version và encrypted-key rotation |
| Compliance | Data retention và credential deletion |

**Không serialize chỉ bằng `HttpCookie.toString()` để dựng persistent jar**: header value không bảo đảm lưu đủ metadata và original creation/expiry semantics. Nếu restore bằng cách khởi tạo `HttpCookie` mới có `Max-Age` cũ, lifetime có thể bị kéo dài sai.

Đối với hệ thống nhiều users, nên cân nhắc IdP/SDK/session management chuyên dụng thay vì tự lưu plaintext session cookies trên disk. Persistent jar không có encryption, rotation và audit thường rủi ro hơn một lần đăng nhập lại.

## 13. Limits, concurrency và privacy

Server độc hại hoặc một endpoint sai cấu hình có thể trả hàng nghìn cookies, cookie values lớn hoặc cookies hết hạn liên tục. `BoundedCookieStore` chỉ có hai quotas cơ bản. Production cần thêm:
- **Giới hạn total header bytes** trước/ở HTTP layer; quota name+value của demo không thay thế bước này.
- Số cookies **per host, per registrable domain, per tenant**.
- Kích thước cookie value/name/attributes, giới hạn redirects và deadline.
- Policy cho session vs persistent cookies, refresh, eviction, duplicate identity và expired cleanup.
- Synchronization, monitoring capacity rejection, nhưng **không** log session values.
- Thread isolation với multiple HttpClients; bounded queuing để tránh memory pressure.

Một lock `synchronized` đảm bảo một instance store không race giữa `add/get/remove`, nhưng không tự khiến application security toàn hệ thống thread-safe. Nếu mỗi user có jar riêng, việc tách ownership vừa giúp security vừa giảm contention.

## 14. Troubleshooting và những lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Có Set-Cookie nhưng jar trống | CookiePolicy reject, invalid parsing, quota | Test `manager.put` với header và URI chính xác |
| Jar có cookie nhưng request không gửi | Domain/Path/Secure/expiry không match | Test `manager.get` với URI request cuối |
| Cookie Secure không gửi qua HTTP | Đúng flag Secure | Dùng HTTPS thật, không bỏ Secure ở production |
| Cookie HttpOnly vẫn gửi request | Đúng: HttpOnly không cấm HTTP transport | Phân biệt browser script access |
| Đổi policy sang ACCEPT_NONE nhưng vẫn có cookie cũ | Policy chỉ tác động tương lai | Xóa jar khi logout |
| Cookie mới cùng name làm jar count không tăng | Replacement cùng name/domain/path | Kiểm đúng identity và path |
| Hai cookies cùng name cùng tồn tại | Domain hoặc path khác | Không key theo name đơn thuần |
| Cookie quá lớn bị từ chối | maxChars quota | Kiểm mức quota, không tắt tùy tiện |
| Cookie mới bị bỏ khi jar đầy | Quota reject | Có eviction policy, kiểm số dropped |
| Cookie tồn tại lâu sau restart | Persistent store phục hồi Max-Age sai | Lưu absolute expiry |
| Hai người dùng chia sẻ cookie | Dùng default global jar/manager chung | Per-user/tenant jar và lifecycle |
| Client khác không có cookies | Chưa gắn cookieHandler | Dùng builder.cookieHandler |
| Session server còn valid sau clear jar | Chưa revoke phía server | Invalidate session remotely |
| SameSite behavior khác browser | JDK CookieManager không mô phỏng browser | Dùng browser-grade implementation |
| Path matching sai với encoded URL | URL normalization hoặc scope policy | Test đúng URLs, routing và proxy path |
| Cookie values rò trong logs | In Cookie/Set-Cookie raw headers | Redact và hạn chế diagnostics |

**Anti-pattern:**

~~~java
// Không dùng trong production: có thể in session secrets.
System.out.println(manager.getCookieStore().getCookies());
~~~

Thay vì in cookie jar, chỉ log số lượng, rejection reason và correlation ID đã sanitize.

## 15. Bảng kiểm thử nên có

| Case | Kỳ vọng |
| --- | --- |
| Cookie từ HTTPS host allowlisted | Accepted theo strict policy |
| Host hoặc scheme khác | Rejected |
| Cookie thiếu Secure | Rejected theo strict policy |
| Cookie thiếu HttpOnly | Rejected theo strict policy |
| Cookie session Max-Age=-1 | Rejected nếu policy đòi positive TTL |
| Max-Age vượt quota | Rejected |
| Path=/secure và request /secure/home | Sent |
| Path=/secure và request /outside | Not sent |
| Secure cookie qua HTTP | Not sent |
| Thay cookie cùng identity | Cookie count không tăng |
| Thêm cookie thứ N+1 trong quota N | Rejected hoặc evicted theo policy |
| Name/value quá maxChars | Rejected |
| Cookie expired | Không trả từ get/getCookies |
| Max-Age=0 | Được xử lý xóa/expire đúng scope |
| remove(uri,cookie) | Chỉ cookie tương ứng bị xóa |
| removeAll | Jar rỗng |
| setCookiePolicy ACCEPT_NONE | Chặn cookie mới, cookie cũ vẫn còn |
| Hai HttpClient có hai managers | Không rò cookie qua jar kia |
| HttpClient không gắn handler | Không tự gửi jar của client khác |
| HTTP loopback Set-Cookie + Cookie | Gửi lại đúng path |
| Test redirect khác origin | Không gửi cookie vượt scope |
| Cookie Domain rộng hoặc public suffix | Reject nếu profile cấm |
| Cookie prefixes __Host-/__Secure- | Test bằng implementation thực nếu cần |
| Concurrency add/get/remove | Không vượt quota hoặc corrupt state |
| Malformed hoặc rất nhiều Set-Cookie | Không crash/DoS, áp quotas |
| Persistent restore | Metadata/absolute expiry/tenant đúng |
| Server revoked session | Cookie cũ không còn cấp quyền |
| Browser SameSite/Partitioned | Không suy diễn từ kết quả JDK CookieManager |

Những test bổ sung cần tách khỏi chương trình minh họa gồm HTTPS certificate verification, Unicode/IDN/IPv6 host normalization, port boundaries, public suffix policy, CSRF, redirects, clock manipulation, disk encryption, multi-process persistence và benchmark tải cao.

## 16. Câu hỏi tự kiểm tra

1. **CookiePolicy làm gì?** Quyết định nhận cookie mới qua shouldAccept.
2. **CookieStore làm gì?** Lưu, tra cứu, loại expired, xóa cookie.
3. **CookieManager làm gì?** Kết hợp CookiePolicy/CookieStore với HTTP headers.
4. **Policy mặc định CookieManager?** ACCEPT_ORIGINAL_SERVER.
5. **Store mặc định CookieManager?** In-memory.
6. **Gắn manager với HttpClient hiện đại bằng gì?** Builder.cookieHandler.
7. **Đổi ACCEPT_NONE có xóa cookie cũ không?** Không.
8. **Dùng ACCEPT_ALL mặc định có tốt không?** Không với nguồn không tin cậy.
9. **HttpCookie.getSecure() chứng minh TLS certificate tin cậy không?** Không.
10. **HttpOnly ngăn Java code đọc value không?** Không.
11. **Cookie Path bảo vệ dữ liệu bằng authorization không?** Không.
12. **Max-Age=0 dùng làm gì?** Xóa hoặc làm hết hạn cookie.
13. **Max-Age=-1 là gì?** Thường là session cookie.
14. **Có thể có hai cookies cùng name không?** Có, khác domain/path.
15. **Tại sao không tự làm Map<URI,String> cho cookie?** Matching/expiry/scope phức tạp.
16. **Vì sao getCookies() unmodifiable vẫn chưa đủ?** HttpCookie elements mutable.
17. **Vì sao clone trong custom store?** Tránh caller sửa state nội bộ.
18. **Vì sao synchronized các operations?** Đảm bảo check-then-add quota atomic.
19. **BoundedCookieStore có persistent storage không?** Không.
20. **Quota maxChars có là HTTP header byte quota không?** Không.
21. **Xóa local jar có revoke server session không?** Không.
22. **CookieStore.getURIs là toàn bộ hosts match Domain?** Không.
23. **Dùng CookieHandler.setDefault cho nhiều tenants có nên không?** Tránh; tách client-level jars.
24. **HttpClient không gắn cookieHandler có dùng jar client khác không?** Không trong demo, vì không chia sẻ manager.
25. **Java CookieManager có mô phỏng browser SameSite đầy đủ không?** Không.
26. **Cookie Secure có được gửi tới HTTPS sai host không?** Vẫn chịu Domain/Path/host policy, không tự cho phép.
27. **Cách nhận cookie từ một host duy nhất?** Custom CookiePolicy kiểm scheme, host, attributes và original-server.
28. **Logout chắc chắn cần gì phía server?** Invalidate/revoke session/token khi cần.
29. **Nếu cookie jar dùng nhiều threads, cần gì?** Thread-safe store và ownership isolation.
30. **Dùng browser automation để test SameSite, có nên thay bằng CookieManager không?** Không, phải dùng browser semantics.
31. **Có nên log raw cookie?** Không với credentials/session thật.
32. **Nếu phải persist cookie, làm sao bảo mật?** Encrypt-at-rest, file ACL, key rotation, absolute expiry và per-user isolation.

## 17. Tài liệu chính thức và đang áp dụng

- [Java SE 25 — CookiePolicy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/CookiePolicy.html): `shouldAccept` và ba predefined policies.
- [Java SE 25 — CookieStore](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/CookieStore.html): sáu operations, immutable list và expired cookie lifecycle.
- [Java SE 25 — CookieManager](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/CookieManager.html): store/policy, `get`/`put`, default in-memory và `setCookiePolicy`.
- [Java SE 25 — CookieHandler](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/CookieHandler.html): interface và global `getDefault`/`setDefault`.
- [Java SE 25 — HttpCookie](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/HttpCookie.html): các attributes Domain/Path/Secure/HttpOnly/Max-Age, equals và mutable setters.
- [Java SE 25 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `cookieHandler` riêng từng HTTP client.
- [Java SE 25 — HttpServer](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): server loopback trong integration test.
- [IETF — Draft cập nhật HTTP cookies (6265bis)](https://datatracker.ietf.org/doc/draft-ietf-httpbis-rfc6265bis/): những yêu cầu cookie browser hiện đại, SameSite, Prefix và Public Suffix considerations; trạng thái đang trong quy trình xuất bản vào cuối 2026.
- [IETF — RFC 6265](https://www.rfc-editor.org/rfc/rfc6265): chuẩn HTTP state management đã xuất bản trước bản cập nhật; đối chiếu lịch sử khi cần.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): cookie attributes, browser behavior và security limitations.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifetime, cookie security, logout, token rotation.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): SameSite và CSRF defense-in-depth.

**Kết luận:** `CookiePolicy` quyết định **nhận cookie nào**, `CookieStore` quản lý **trạng thái cookie đã nhận**, còn `CookieManager` kết nối hai thành phần với HTTP. Trong Java 17+, hãy dùng `HttpClient.Builder.cookieHandler` để gắn jar riêng cho từng client hoặc security context; tránh cookie jar global không kiểm soát. Khi cần custom store, ưu tiên composition, quota, defensive copying, expiry, thread safety và test host/path/scheme/ownership. Đừng coi JDK `CookieManager` là browser cookie engine đầy đủ, và đừng nhầm việc xóa local cookies với revoke session ở phía server.