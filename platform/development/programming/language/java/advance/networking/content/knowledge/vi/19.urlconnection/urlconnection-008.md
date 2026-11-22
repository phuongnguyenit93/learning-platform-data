# ResponseCache, CookieHandler và các cấu hình chia sẻ toàn tiến trình trong URLConnection (Java 17+)

Trong Java Networking, `java.net.URLConnection` và lớp con `HttpURLConnection` cung cấp các API cũ nhưng vẫn xuất hiện trong nhiều hệ thống để mở URL, gửi HTTP request và đọc response. Một điểm đặc biệt của nhóm API này: ngoài những thuộc tính **thuộc từng đối tượng URLConnection**, JDK còn có một số **bộ xử lý mặc định toàn tiến trình JVM**. Ví dụ `ResponseCache.setDefault(...)` đăng ký một cache hook dùng chung, `CookieHandler.setDefault(...)` đăng ký bộ xử lý cookie dùng chung. Những cài đặt mặc định này có thể ảnh hưởng **nhiều thư viện và nhiều phần của cùng ứng dụng**, kể cả nơi không trực tiếp gọi method cấu hình.

Bài học tập trung vào:

1. **`ResponseCache`**: callback tìm cache hit/miss và ghi response; vai trò của `CacheResponse`, `CacheRequest`, `URLConnection.setUseCaches(...)`.
2. **`CookieHandler` / `CookieManager`**: chính sách giữ/gửi HTTP cookies, `CookieStore` và phạm vi phiên; khác biệt với `HttpClient.Builder.cookieHandler(...)`.
3. **Các default toàn JVM**: `ProxySelector`, `Authenticator`, flags của `URLConnection`/`HttpURLConnection`, redirect behavior và những API factory một-lần; thời điểm các mặc định được lấy, cách cấu hình từng connection.
4. **Giới hạn và an toàn**: không chia sẻ cookie/session của nhiều users, không lưu nhầm private responses vào cache chung, không thay static defaults giữa lúc requests đang chạy.
5. **Thực hành Java 17+**: ba class độc lập, hai class dùng HTTP server loopback để kiểm chứng caching/cookies và một class chỉ tạo URLConnection objects, **không kết nối mạng**.

**Ý chính:** `setDefault(...)` là **cài đặt dùng chung**, không phải một property của request hiện tại. `setUseCaches(...)` là **điều khiển từng URLConnection**, còn `HttpClient` hiện đại có builder và hành vi khác; không được gộp mọi API Java HTTP vào một hệ thống cấu hình thống nhất khi Javadoc không hứa như vậy.

## 1. URLConnection có những trạng thái nào?

Một vòng đời thông thường:

~~~text
URL url = ...
      |
      v
URLConnection conn = url.openConnection()
      |               -> tạo object, lấy một số default vào object
      |
      +--> conn.setUseCaches(...)
      +--> conn.setConnectTimeout(...)
      +--> conn.setReadTimeout(...)
      +--> conn.setRequestProperty(...)
      |
      v
conn.connect() hoặc getInputStream()/getHeaderFields()
      |
      +--> protocol handler có thể hỏi ResponseCache.get(...)
      +--> HTTP handler có thể hỏi CookieHandler.get(...)
      |
      v
HTTP response
      |
      +--> CookieHandler.put(...) với response headers
      +--> ResponseCache.put(...) + CacheRequest.getBody()
      |    (nếu caching được phép và triển khai có hỗ trợ)
      |
      v
Đọc body tới EOF, đóng stream, disconnect khi cần
~~~

**Lưu ý:** sơ đồ diễn tả callback ở mức khái niệm, không phải thứ tự nội bộ bắt buộc ở mọi protocol handler. Một handler tùy biến hoặc API HTTP khác có thể không dùng những callback này. Gọi `openConnection()` **chỉ tạo URLConnection object**, chưa nhất thiết mở TCP; lần I/O đầu tiên mới khiến kết nối diễn ra.

### 1.1. Per-connection khác process-wide

| API | Phạm vi | Ghi nhớ |
| --- | --- | --- |
| `conn.setUseCaches(false)` | Một `URLConnection` | Đặt trước khi connection đã connected |
| `conn.setConnectTimeout(3000)` | Một `URLConnection` | Connect timeout, đơn vị milliseconds |
| `conn.setReadTimeout(3000)` | Một `URLConnection` | Timeout chờ đọc, không phải total deadline |
| `conn.setRequestProperty("Accept", ...)` | Một connection/request | Không chỉnh sau khi đã connected |
| `http.setInstanceFollowRedirects(false)` | Một `HttpURLConnection` | Override global redirect default |
| `ResponseCache.setDefault(cache)` | Toàn JVM (default ResponseCache) | Các URL protocol handlers phù hợp có thể dùng cùng cache |
| `CookieHandler.setDefault(handler)` | Toàn JVM (default CookieHandler) | Các HTTP URL handlers phù hợp có thể dùng cùng cookie store |
| `ProxySelector.setDefault(selector)` | Toàn JVM (proxy selector mặc định) | Cấu hình route chung, override được qua API hỗ trợ |
| `Authenticator.setDefault(authenticator)` | Toàn JVM (default authenticator) | Rủi ro dùng credential sai phạm vi nếu thiết kế kém |
| `URLConnection.setDefaultUseCaches("http",false)` | Static mặc định cho protocol HTTP | Tác động các connection được tạo sau |
| `HttpURLConnection.setFollowRedirects(false)` | Static redirect default | Connection mới lấy default, có thể override instance |

Một **JVM** có thể chạy nhiều tenants, plugins, modules, concurrent threads và nhiều HTTP clients. Nếu module A gọi `CookieHandler.setDefault(tenantACookies)`, module B đang chạy URLConnection có thể vô tình sử dụng cookie policy của A. Đó là **shared mutable global state**, không phải dependency injection an toàn.

## 2. ResponseCache: thiết kế bộ nhớ đệm thông qua protocol handler

### 2.1. Vai trò và vòng đời

Theo [Java 17 ResponseCache Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ResponseCache.html), `ResponseCache` là lớp trừu tượng cho các cache implementations của `URLConnection`. Khi được đăng ký:

~~~java
ResponseCache previous = ResponseCache.getDefault();
ResponseCache.setDefault(myCache);
try {
    // Các HTTP URLConnection phù hợp được phép dùng cache.
} finally {
    ResponseCache.setDefault(previous);
}
~~~

Đây là **đoạn minh họa không độc lập** vì `myCache` chưa được khai báo. `getDefault()` trả cache dùng chung hoặc `null`, `setDefault(null)` bỏ đăng ký global cache. **Non-standard URL protocol handlers có thể bỏ qua ResponseCache**, và đăng ký hook không tự biến `java.net.http.HttpClient` thành một caching client.

Hai callback chính:

~~~java
abstract CacheResponse get(
        URI uri,
        String requestMethod,
        Map<String, List<String>> requestHeaders)
        throws IOException;

abstract CacheRequest put(
        URI uri, URLConnection connection)
        throws IOException;
~~~

- `get(...)`: hỏi liệu có thể phục vụ request từ cache. **Trả `CacheResponse`** nếu có bản phù hợp, hoặc **`null`** để protocol handler thực hiện đường network thông thường. `get` được gọi với URI, method và request headers; một cache an toàn **không thể chỉ nhìn URL** nếu response phụ thuộc request headers, credentials, ngôn ngữ, Accept-Encoding hoặc cookie.
- `put(...)`: sau khi handler lấy response từ nguồn, hỏi cache có muốn lưu nó không. **Trả `CacheRequest`** để nhận response bytes hoặc `null` nếu không lưu. Một cache implementation phải tự quyết định có đủ điều kiện lưu dựa trên method, status, Cache-Control, authorization, cookies, Vary, expiry và policy.
- `CacheResponse.getHeaders()` và `CacheResponse.getBody()`: cung cấp metadata và input stream của bản cache hit.
- `CacheRequest.getBody()`: output stream để protocol handler viết response bytes cho bản ghi cache.
- `CacheRequest.abort()`: báo phần ghi không thành công; **phải bỏ bản chưa hoàn chỉnh**, không được phục vụ partial response như bản đầy đủ.

### 2.2. `useCaches` là quyền sử dụng cache, không phải cache object

Với từng URLConnection:

~~~java
HttpURLConnection conn =
        (HttpURLConnection) url.openConnection();

conn.setUseCaches(false);  // gọi trước khi kết nối
conn.setConnectTimeout(3000);
conn.setReadTimeout(3000);

try (InputStream body = conn.getInputStream()) {
    // đọc body
} finally {
    conn.disconnect();
}
~~~

Đây là **đoạn minh họa** với `url` đã tồn tại, import `java.net.*` và `java.io.*`. Nếu `conn.getUseCaches()==true`, protocol handler **được phép** hỏi cache; điều này **không cam kết** response sẽ lấy từ cache. Nó có thể miss, hết hạn, `no-store`, không cache được hoặc không có cache được đăng ký. Nếu `setUseCaches(false)`, handler phải bỏ qua cache theo contract của flag. Thay đổi `setUseCaches` sau khi đã connected có thể ném `IllegalStateException`.

Hai ngộ nhận:

- **`ResponseCache.setDefault(cache)` không tự động tạo cache được cấu hình đầy đủ.** Java chỉ cung cấp hook/abstract classes; bạn hoặc thư viện triển khai chính sách cache.
- **`conn.setUseCaches(true)` không bật một bộ nhớ đệm thần kỳ.** Cần handler/cache thực sự tồn tại và request/response đủ điều kiện.

### 2.3. Cache key, freshness và HTTP semantics

Một cache HTTP dùng cho production phải xét tối thiểu:

| Yếu tố | Hậu quả nếu bỏ qua |
| --- | --- |
| HTTP method | Có thể trả response GET cho request POST sai semantics |
| URI gồm scheme, host, port, path, query | Có thể trộn nội dung của hai origins/resources |
| `Cache-Control: no-store` | Vô tình lưu dữ liệu bị cấm cache |
| `Cache-Control: private` | Lưu dữ liệu cá nhân vào cache chia sẻ |
| `Authorization` hoặc `Cookie` | Rò session/user data giữa các requests |
| `Vary`, ví dụ `Accept-Language`/`Accept-Encoding` | Trả body/encoding sai cho client khác |
| `max-age`/`Expires`/`Age`/date | Trả dữ liệu cũ sau khi đã hết freshness |
| `ETag`/`Last-Modified` và conditional GET | Không revalidate đúng hoặc trả sai 304 |
| Redirects và `Cache-Control` response | Cache nhầm response 3xx/4xx/5xx |
| Interrupted/partial body | Phục vụ response bị cắt |
| Dung lượng/eviction | Memory/disk tăng vô giới hạn |
| Invalidations sau write methods | Cache dữ liệu cũ sau PUT/DELETE |
| Concurrent readers/writers | Race, entry dở, use-after-close |

Các quy tắc HTTP caching hiện đại nằm trong **RFC 9111**. Chỉ nhìn `Cache-Control: public, max-age=60` rồi lưu byte array theo URI chưa phải cache production: còn cần clock/freshness, revalidation, Vary, header updates, validation, eviction, response metadata và security.

### 2.4. Chú ý thread-safety

`ResponseCache.getDefault()` trả cùng một object mà nhiều HTTP calls/threads có thể dùng. Vì vậy implementation phải quản lý concurrent maps, ownership của byte buffers, commit atomic, eviction, lifecycle của files, I/O failures và memory quota. Khi `get` trả `CacheResponse`, mỗi caller cần **InputStream riêng** hoặc dữ liệu immutable để nhiều readers không tranh nhau `position`. Khi `put` đang ghi, **không publish entry chưa đóng stream/hoàn tất**; `abort` phải xóa partial. Cũng không dùng object `URLConnection` trong callback `put` để vô tình mở lại cùng URL và gây recursion.

## 3. CookieHandler: quản lý session state của HTTP URL handler

### 3.1. CookieHandler không tự mang cookie jar

`CookieHandler` là lớp abstract với callbacks:

~~~java
abstract Map<String, List<String>> get(
        URI uri,
        Map<String, List<String>> requestHeaders)
        throws IOException;

abstract void put(
        URI uri,
        Map<String, List<String>> responseHeaders)
        throws IOException;
~~~

- `get(...)` được HTTP protocol handler sử dụng để lấy các cookie headers phù hợp với URI trước khi gửi request.
- `put(...)` đưa response headers (ví dụ `Set-Cookie`) vào policy/store.
- `CookieHandler.getDefault()` trả handler mặc định toàn JVM hoặc `null`.
- `CookieHandler.setDefault(handler)` đổi mặc định toàn JVM; `setDefault(null)` bỏ handler.
- Non-standard handlers/libraries có thể **bỏ qua** global handler.

Một **`CookieManager`** là implementation sẵn có kết hợp **`CookieStore`** và **`CookiePolicy`**. Ví dụ:

~~~java
CookieManager jar = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
CookieHandler previous = CookieHandler.getDefault();
CookieHandler.setDefault(jar);
try {
    // HttpURLConnection ở phần HTTP URL handler có thể chia sẻ jar.
} finally {
    CookieHandler.setDefault(previous);
}
~~~

Đây là **đoạn minh họa**, không phải cách cấu hình cho nhiều tenants đang chạy đồng thời. `null` ở tham số `store` khiến JDK tạo store mặc định **in-memory**; cookie manager không tự ghi ra disk và không hứa browser-like persistent session. `CookiePolicy.ACCEPT_ORIGINAL_SERVER` là policy mặc định của `CookieManager` nếu không chỉ định policy; ngoài ra có `ACCEPT_ALL` và `ACCEPT_NONE`. Dùng `ACCEPT_ALL` cho tất cả external origins có thể nới quyền quá mức. Cookie policy, cookie attributes và origin validation vẫn cần threat model/kiểm tra.

### 3.2. Cookie nhận và gửi theo URI, không gửi mù toàn bộ jar

Server trả:

~~~http
HTTP/1.1 200 OK
Set-Cookie: sid=abc123; Path=/; HttpOnly; Secure
~~~

Với cookie `Secure`, browser/JDK cookie handling phải xét secure transport; không gửi giá trị như thế qua HTTP plaintext chỉ vì same hostname. `Path`, `Domain`, `Max-Age`/`Expires` và host/path matching ảnh hưởng cookie được gắn vào request nào. Cookie xử lý bởi JDK không hoàn toàn tương đương browser hiện đại cho mọi attribute mới (ví dụ SameSite rules), và **không nên dùng nó như một browser security engine không cần kiểm thử**.

`CookieHandler.get(URI,requestHeaders)` có URI chứa scheme/host cụ thể; `CookieManager` quyết định cookie áp dụng. `HttpCookie` đại diện một cookie; `CookieStore` cho phép kiểm tra/xóa `getCookies()`/`remove`/`removeAll`. Giá trị cookie có thể là **session token**, không log raw values, không đưa vào cache key dạng plaintext hoặc metrics labels.

### 3.3. Phạm vi và vòng đời của cookie jar

Một `CookieManager` dùng chung có thể có lợi cho **một phiên HTTP logic** cần:
1. GET hoặc POST login nhận `Set-Cookie`.
2. HTTP request sau gửi `Cookie` cho cùng origin/path.
3. Server nhận session cookie và xử lý theo trạng thái đăng nhập.
4. Logout/xóa cookie, expiry/policy làm session kết thúc.

Nhưng nếu một JVM chạy nhiều customer sessions, dùng cùng một cookie jar là **rủi ro cross-tenant/cross-user leakage**. `CookieStore` phải được cô lập theo logical tenant/session. Chỉ vì hai API cùng kiểu `CookieHandler` không có nghĩa share jar giữa các user là đúng. Với request chứa credentials, dùng cookie manager riêng, cookie policy đúng, giới hạn age và xóa store khi session logout.

### 3.4. Global cookie default phải được cấu hình ổn định

Không làm:

~~~java
// ANTI-PATTERN: mỗi request thay global state
CookieHandler.setDefault(cookieJarUserA);
doRequestA();
CookieHandler.setDefault(cookieJarUserB);
doRequestB();
~~~

Đây là **pseudocode sai**: `doRequestA`/`doRequestB` không độc lập, và ở ứng dụng concurrency, request A có thể đang gửi headers đúng lúc thread B đổi default. Không có dynamic-scoping đảm bảo “thời gian trong try chỉ có thread này dùng handler”.

Đặt global `CookieHandler` một lần trong giai đoạn bootstrap cho một service chỉ có **một cookie policy thống nhất** nếu thực sự cần API cũ. Muốn nhiều policies, ưu tiên client-specific dependency injection hoặc thư viện hỗ trợ per-client jar.

## 4. Những gì không tự chia sẻ với java.net.http.HttpClient

Java 11+ có API hiện đại `java.net.http.HttpClient`, **không phải là lớp con của `URLConnection`**. Sự khác biệt với global hooks rất quan trọng:

| Tính năng | URLConnection / HttpURLConnection | java.net.http.HttpClient (Java 17) |
| --- | --- | --- |
| Cookie mặc định | HTTP URL handler có thể dùng `CookieHandler.getDefault()` | **Không tự dùng global CookieHandler** nếu builder không đặt `cookieHandler(...)` |
| Cookie per client | Global URL handler nên khó cô lập theo instance | `HttpClient.newBuilder().cookieHandler(manager)` |
| ResponseCache | HTTP URL handler dùng `ResponseCache.getDefault()` nếu thích hợp | **Không có bảo đảm sử dụng ResponseCache global**, không có builder ResponseCache |
| Proxy | Protocol handler có thể dùng JVM default `ProxySelector` và system properties | Builder `proxy(...)` có thể override, nếu bỏ trống thường dùng default selector |
| Authenticator | Có legacy global `Authenticator.setDefault(...)` | Builder `authenticator(...)` cho HTTP client cụ thể |
| Redirects | `HttpURLConnection.setFollowRedirects(boolean)` static default và `setInstanceFollowRedirects` | Builder `followRedirects(HttpClient.Redirect)` per client |
| Protocol version | HTTP/1.1 legacy handler | `Version.HTTP_1_1`/`HTTP_2` preference, actual response version riêng |
| Timeouts | `URLConnection.setConnectTimeout`/`setReadTimeout` | `HttpClient.Builder.connectTimeout` và `HttpRequest.Builder.timeout` |
| Body/resource lifecycle | `getInputStream`, error stream, `disconnect` | `BodyHandlers`, futures, streams/subscribers theo API |

**`HttpClient.Builder.cookieHandler(...)` là explicit opt-in.** Nếu không gọi method đó, Java 17 client **không dùng cookie handler**. Chỉ gọi `CookieHandler.setDefault(jar)` và sau đó `HttpClient.newHttpClient()` không nên được xem là kích hoạt cookies. Ví dụ số 2 sẽ chứng minh bằng server loopback.

Cách cô lập cookies theo logical session:

~~~java
CookieManager alice = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
CookieManager bob = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);

HttpClient aliceClient = HttpClient.newBuilder()
        .cookieHandler(alice)
        .build();
HttpClient bobClient = HttpClient.newBuilder()
        .cookieHandler(bob)
        .build();
~~~

Đây là **đoạn minh họa** với import `java.net.*` và `java.net.http.*`. Hai clients có `CookieStore` riêng nhưng vẫn cần kiểm soát cùng-origin, session expiry, credential handling và không vô tình share singleton khác. Đừng tái sử dụng cùng CookieManager object cho hai user nếu yêu cầu phân tách nghiêm ngặt.

**ResponseCache không phải HTTP caching API của HttpClient.** Nếu cần caching cho modern HttpClient, hãy dùng HTTP caching layer/library chuyên dụng hoặc code kiến trúc riêng, tuân thủ RFC 9111; không kỳ vọng `ResponseCache.setDefault(...)` làm cho `HttpClient.send(...)` trả cache hits.

## 5. Ví dụ Java 17+ số 1: ResponseCache thật, cache-hit và bypass

Ví dụ này là **demo cache rất nhỏ**, cố ý chỉ cache một URL path `/public` của **HTTP server loopback do chương trình tạo**. Server trả payload tăng dần `origin-1`, `origin-2`... và header `Cache-Control: public, max-age=60`. `SmallPublicCache`:

- `get(...)` tìm entry cho GET `/public`; trả `CacheResponse` khi có.
- `put(...)` chỉ lưu HTTP 200 với đúng Cache-Control test; trả `CacheRequest` và commit khi output stream đóng.
- Giới hạn tối đa **16.384 bytes** per entry để tránh demo giữ body vô hạn.
- `ResponseCache.setDefault(cache)` chỉ có hiệu lực trong vùng demo; `finally` khôi phục mặc định cũ.
- `fetch(url,true)` cho phép cache, `fetch(url,false)` bỏ qua cache.

**Giới hạn bảo mật:** implementation cache mẫu **KHÔNG** hỗ trợ expiration, Vary, conditional requests, Authorization/cookies, revalidation, status variants, eviction hoặc robust concurrency/cancellation. Nó **chỉ được dùng cho resource public do test server kiểm soát**, tuyệt đối không dùng làm HTTP cache production hoặc với response người dùng thật.

Tạo file **`UrlResponseCacheDemo.java`**:

~~~java
import com.sun.net.httpserver.*;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class UrlResponseCacheDemo {
    static final class SmallPublicCache extends ResponseCache {
        record Entry(byte[] data,
                     Map<String, List<String>> headers) {}

        private final ConcurrentMap<URI, Entry> entries =
                new ConcurrentHashMap<>();
        final AtomicInteger lookups = new AtomicInteger();
        final AtomicInteger hits = new AtomicInteger();
        final AtomicInteger stores = new AtomicInteger();

        @Override
        public CacheResponse get(
                URI uri, String method,
                Map<String, List<String>> requestHeaders) {
            lookups.incrementAndGet();
            if (!"GET".equals(method)
                    || !"/public".equals(uri.getPath())) {
                return null;
            }
            Entry entry = entries.get(uri);
            if (entry == null) return null;
            hits.incrementAndGet();
            return new CacheResponse() {
                @Override
                public Map<String, List<String>> getHeaders() {
                    return entry.headers();
                }

                @Override
                public InputStream getBody() {
                    return new ByteArrayInputStream(entry.data());
                }
            };
        }

        @Override
        public CacheRequest put(
                URI uri, URLConnection connection)
                throws IOException {
            if (!(connection instanceof HttpURLConnection http)
                    || !"/public".equals(uri.getPath())
                    || http.getResponseCode() != 200
                    || !"public, max-age=60".equalsIgnoreCase(
                        http.getHeaderField("Cache-Control"))) {
                return null;
            }

            Map<String, List<String>> headers =
                    new LinkedHashMap<>();
            http.getHeaderFields().forEach((key, values) ->
                    headers.put(key, List.copyOf(values)));

            return new CacheRequest() {
                private final ByteArrayOutputStream buffer =
                        new ByteArrayOutputStream();
                private boolean aborted;

                @Override
                public OutputStream getBody() {
                    return new OutputStream() {
                        @Override
                        public void write(int b) throws IOException {
                            if (buffer.size() >= 16384) {
                                throw new IOException("Too large");
                            }
                            buffer.write(b);
                        }

                        @Override
                        public void write(
                                byte[] b, int off, int len)
                                throws IOException {
                            if (len > 16384 - buffer.size()) {
                                throw new IOException("Too large");
                            }
                            buffer.write(b, off, len);
                        }

                        @Override
                        public void close() throws IOException {
                            if (!aborted) {
                                entries.put(uri, new Entry(
                                        buffer.toByteArray(), headers));
                                stores.incrementAndGet();
                            }
                        }
                    };
                }

                @Override
                public void abort() {
                    aborted = true;
                }
            };
        }
    }

    private static String fetch(
            URL url, boolean useCaches) throws Exception {
        HttpURLConnection connection =
                (HttpURLConnection) url.openConnection(
                        Proxy.NO_PROXY);
        connection.setConnectTimeout(3000);
        connection.setReadTimeout(3000);
        connection.setUseCaches(useCaches);

        try (InputStream in = connection.getInputStream()) {
            return new String(
                    in.readAllBytes(), StandardCharsets.UTF_8);
        } finally {
            connection.disconnect();
        }
    }

    public static void main(String[] args)
            throws Exception {
        ResponseCache original = ResponseCache.getDefault();
        InetAddress loopback =
                InetAddress.getLoopbackAddress();
        AtomicInteger originCalls = new AtomicInteger();

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext("/public", ex -> {
            byte[] body = (
                    "origin-" + originCalls.incrementAndGet())
                    .getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().set(
                    "Cache-Control", "public, max-age=60");
            ex.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            ex.sendResponseHeaders(200, body.length);
            try (OutputStream out = ex.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();

        try {
            SmallPublicCache cache = new SmallPublicCache();
            ResponseCache.setDefault(cache);
            URL url = new URI(
                    "http", null, loopback.getHostAddress(),
                    server.getAddress().getPort(),
                    "/public", null, null).toURL();

            System.out.println(
                    "first: " + fetch(url, true));
            System.out.println(
                    "second: " + fetch(url, true));
            System.out.println(
                    "bypass: " + fetch(url, false));
            System.out.println(
                    "origin calls: " + originCalls.get());
            System.out.println(
                    "cache hits: " + cache.hits.get());
            System.out.println(
                    "cache stores: " + cache.stores.get());
        } finally {
            ResponseCache.setDefault(original);
            server.stop(0);
        }
    }
}
~~~

Biên dịch/chạy trên JDK 17+ (có module `jdk.httpserver`):

~~~bash
javac --release 17 UrlResponseCacheDemo.java
java UrlResponseCacheDemo
~~~

Stdout **đã kiểm tra trên JDK cục bộ**:

~~~text
first: origin-1
second: origin-1
bypass: origin-2
origin calls: 2
cache hits: 1
cache stores: 1
~~~

Giải thích chính xác:

1. Request đầu `setUseCaches(true)`: `cache.get` không có entry nên protocol handler đi tới loopback origin, nhận `origin-1`; `cache.put` nhận bytes và lưu sau khi hoàn tất.
2. Request thứ hai đến **cùng URI**, cho phép cache: `get` trả `CacheResponse` với body `origin-1`, **origin không được gọi lần hai**.
3. Request thứ ba `setUseCaches(false)`: bỏ qua global cache hook, đi tới origin và lấy `origin-2`.
4. `origin calls: 2` là số lần handler origin thực được gọi trong bài test, không phải số lần URLConnection được tạo (ba).
5. `cache hits: 1` và `cache stores: 1` minh họa cache lookup/put thành công; biến `lookups` còn dùng để debug nhưng không in để khỏi nhầm với hits.
6. `CacheResponse.getBody()` tạo **mỗi lần một ByteArrayInputStream mới**, tránh nhiều readers tranh nhau vị trí đọc của một stream mutable.
7. `CacheRequest.getBody().close()` mới commit dữ liệu. `abort()` không đưa entry lỗi vào map.
8. Trong demo, `get` bỏ qua requestHeaders và không kiểm tra expiry, nên **không dùng code này cho bất kỳ response có tính cá nhân, thay đổi theo headers hoặc Internet thật**.

Chú ý: `CacheRequest.getBody()` chỉ cần triển khai buffer/stream vì protocol handler sẽ ghi bytes. **Không phải `ResponseCache.put` tự gọi `conn.getInputStream()` để tải response lần thứ hai**. Việc tự read lại trong `put` có thể gây re-entry/redundant I/O hoặc deadlock.

## 6. Ví dụ Java 17+ số 2: CookieHandler global và HttpClient explicit

Bài test tiếp theo cho thấy cùng một `CookieManager` được dùng như **global CookieHandler** bởi `HttpURLConnection`, nhưng **java.net.http.HttpClient không tự dùng nó khi builder không có `cookieHandler(...)`**.

Loopback server có:
- `/login`: gửi header `Set-Cookie: sid=demo123; Path=/; HttpOnly`.
- `/whoami`: kiểm tra có request cookie đó hay không và chỉ trả chuỗi `true` hoặc `false`, **không echo secret**.

Tạo file **`UrlCookieHandlerDemo.java`**:

~~~java
import com.sun.net.httpserver.*;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class UrlCookieHandlerDemo {
    private static String fetchOld(URL url)
            throws Exception {
        HttpURLConnection c =
                (HttpURLConnection) url.openConnection(
                        Proxy.NO_PROXY);
        c.setConnectTimeout(3000);
        c.setReadTimeout(3000);
        c.setUseCaches(false);
        try (InputStream body = c.getInputStream()) {
            return new String(
                    body.readAllBytes(),
                    StandardCharsets.UTF_8);
        } finally {
            c.disconnect();
        }
    }

    private static String fetchNew(
            HttpClient client, URI uri) throws Exception {
        HttpRequest req = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET().build();
        return client.send(
                req, HttpResponse.BodyHandlers.ofString())
                .body();
    }

    public static void main(String[] args)
            throws Exception {
        CookieHandler previous =
                CookieHandler.getDefault();
        InetAddress loopback =
                InetAddress.getLoopbackAddress();

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);

        server.createContext("/login", exchange -> {
            exchange.getResponseHeaders().add(
                    "Set-Cookie",
                    "sid=demo123; Path=/; HttpOnly");
            byte[] bytes = "set".getBytes(
                    StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(
                    200, bytes.length);
            try (OutputStream out =
                    exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.createContext("/whoami", exchange -> {
            String incoming =
                    exchange.getRequestHeaders()
                            .getFirst("Cookie");
            byte[] bytes = String.valueOf(
                    incoming != null &&
                            incoming.contains("sid=demo123"))
                    .getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(
                    200, bytes.length);
            try (OutputStream out =
                    exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.start();
        try {
            CookieManager jar = new CookieManager(
                    null,
                    CookiePolicy.ACCEPT_ORIGINAL_SERVER);
            CookieHandler.setDefault(jar);

            URI base = new URI(
                    "http", null, loopback.getHostAddress(),
                    server.getAddress().getPort(),
                    "/", null, null);

            fetchOld(base.resolve("login").toURL());
            System.out.println(
                    "legacy sends cookie: " +
                    fetchOld(base.resolve("whoami").toURL()));
            System.out.println(
                    "stored cookies: " +
                    jar.getCookieStore().getCookies().size());

            HttpClient without = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .build();
            System.out.println(
                    "new client default cookie: " +
                    fetchNew(without,
                            base.resolve("whoami")));

            HttpClient withJar = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .cookieHandler(jar)
                    .build();
            System.out.println(
                    "new client explicit cookie: " +
                    fetchNew(withJar,
                            base.resolve("whoami")));
        } finally {
            CookieHandler.setDefault(previous);
            server.stop(0);
        }
    }
}
~~~

~~~bash
javac --release 17 UrlCookieHandlerDemo.java
java UrlCookieHandlerDemo
~~~

Stdout **đã kiểm tra trên JDK cục bộ**:

~~~text
legacy sends cookie: true
stored cookies: 1
new client default cookie: false
new client explicit cookie: true
~~~

Đọc output theo từng bước:

1. `CookieHandler.setDefault(jar)` giúp HTTP URL handler gọi `CookieManager.put` khi `/login` trả Set-Cookie, nên jar chứa một cookie.
2. `HttpURLConnection` thứ hai gọi `CookieManager.get` và gửi cookie phù hợp tới `/whoami`: server báo `true`.
3. `HttpClient.newBuilder()` **không gọi `cookieHandler(...)`** không tự sử dụng jar global: server báo `false`, dù `CookieHandler.getDefault()==jar` trong lúc test.
4. `HttpClient.newBuilder().cookieHandler(jar)` dùng chính jar đó theo **explicit per-client dependency**: server báo `true`.
5. `CookieHandler.setDefault(previous)` ở `finally` đảm bảo bài test không bỏ lại global cookie manager của demo sau khi kết thúc bình thường hoặc ném exception; **cơ chế này không biến global mutation thành thread-local an toàn** nếu có HTTP requests khác chạy đồng thời.
6. `CookiePolicy.ACCEPT_ORIGINAL_SERVER` phù hợp để minh họa first-party Set-Cookie; JDK cookie policy vẫn cần kiểm tra với host, domain/path và các attributes yêu cầu bởi sản phẩm.
7. `HttpClient.Builder.NO_PROXY` chỉ định direct cho demo, tránh việc environment default proxy làm thay đổi đường đi; không phải một phần của CookieManager.

Không dùng cookie `sid=demo123` làm credential thật. Khi làm production, không in cookie values hoặc gửi session token tới host khác. Với cookie secure/session cần HTTPS, CSRF strategy, SameSite/server validation và các chính sách bảo mật khác.

## 7. Default useCaches và redirect có thể ảnh hưởng connection mới

### 7.1. URLConnection.setDefaultUseCaches(String,boolean)

Trong Java 17, có API static:

~~~java
URLConnection.setDefaultUseCaches(
        "http", false);
boolean value =
        URLConnection.getDefaultUseCaches("http");
~~~

Nó đặt default `useCaches` cho **các future URLConnection objects của protocol HTTP**. `"http"` case-insensitive theo Javadoc. Không nhầm với method instance `conn.setDefaultUseCaches(boolean)` (legacy method thay default theo hành vi Javadoc) hoặc `conn.setUseCaches(boolean)` (chỉ connection đó).

Dùng tên method **đúng overload**: `setDefaultUseCaches(String,boolean)` là **static** (từ Java 9), còn `setDefaultUseCaches(boolean)` là **instance method** ở URLConnection với ngữ nghĩa thay default. Tương tự `getDefaultUseCaches(String)` là static; `getDefaultUseCaches()` là instance. Đừng gọi instance method mà tưởng đã thay flag duy nhất của một connection.

Từng connection lấy giá trị default tại thời điểm tạo, sau đó có thể override:

~~~java
URLConnection.setDefaultUseCaches("http", false);
URLConnection first = someHttpUrl.openConnection();
// first.getUseCaches() thường là false.

URLConnection.setDefaultUseCaches("http", true);
URLConnection second = someHttpUrl.openConnection();
// second.getUseCaches() thường là true.
// first vẫn giữ giá trị đã khởi tạo.

first.setUseCaches(true);  // override riêng first, trước connect.
~~~

Đây là **mã minh họa**, `someHttpUrl` phải có trước. Thay default không cập nhật mọi URLConnection object đã được tạo.

### 7.2. HttpURLConnection.setFollowRedirects static và instance

~~~java
HttpURLConnection.setFollowRedirects(false);
boolean global = HttpURLConnection.getFollowRedirects();

HttpURLConnection conn = (HttpURLConnection)
        someHttpUrl.openConnection();
boolean perInstance = conn.getInstanceFollowRedirects();
conn.setInstanceFollowRedirects(true);
~~~

Lệnh static `setFollowRedirects` thay **global default** cho các `HttpURLConnection` được tạo sau; `setInstanceFollowRedirects` điều chỉnh **instance**. Đây là chính sách redirect ở legacy HTTP stack, **không** phải `HttpClient.Builder.followRedirects(...)`. Cả security và performance đều bị ảnh hưởng nếu redirect bất ngờ tới origin khác, port khác, endpoint nội bộ hoặc URI chứa token.

### 7.3. Ví dụ Java 17+ số 3: kiểm tra snapshot default, không mở network

Tạo file **`UrlGlobalDefaultsDemo.java`**. Ví dụ chỉ tạo URL tới loopback port 1 (không gọi `connect`/`getInputStream`), nên không có network request thật.

~~~java
import java.net.*;

public final class UrlGlobalDefaultsDemo {
    public static void main(String[] args)
            throws Exception {
        boolean previousCache =
                URLConnection.getDefaultUseCaches("http");
        boolean previousRedirect =
                HttpURLConnection.getFollowRedirects();

        try {
            URL url = new URI(
                    "http://127.0.0.1:1/not-connected")
                    .toURL();

            URLConnection.setDefaultUseCaches(
                    "http", false);
            HttpURLConnection a =
                    (HttpURLConnection) url.openConnection(
                            Proxy.NO_PROXY);
            System.out.println(
                    "a default cache: " + a.getUseCaches());

            URLConnection.setDefaultUseCaches(
                    "http", true);
            HttpURLConnection b =
                    (HttpURLConnection) url.openConnection(
                            Proxy.NO_PROXY);
            System.out.println(
                    "a existing cache: " + a.getUseCaches());
            System.out.println(
                    "b new cache: " + b.getUseCaches());

            a.setUseCaches(true);
            System.out.println(
                    "a instance cache override: " +
                    a.getUseCaches());

            HttpURLConnection.setFollowRedirects(false);
            HttpURLConnection c =
                    (HttpURLConnection) url.openConnection(
                            Proxy.NO_PROXY);
            System.out.println(
                    "c default redirects: " +
                    c.getInstanceFollowRedirects());

            c.setInstanceFollowRedirects(true);
            System.out.println(
                    "c instance redirects override: " +
                    c.getInstanceFollowRedirects());
            System.out.println(
                    "global redirect default: " +
                    HttpURLConnection.getFollowRedirects());
        } finally {
            URLConnection.setDefaultUseCaches(
                    "http", previousCache);
            HttpURLConnection.setFollowRedirects(
                    previousRedirect);
        }
    }
}
~~~

~~~bash
javac --release 17 UrlGlobalDefaultsDemo.java
java UrlGlobalDefaultsDemo
~~~

Stdout **ổn định, đã chạy trên JDK cục bộ**:

~~~text
a default cache: false
a existing cache: false
b new cache: true
a instance cache override: true
c default redirects: false
c instance redirects override: true
global redirect default: false
~~~

Điều đáng chú ý:

- `a` được tạo khi default HTTP cache flag là `false`, nên sau khi static default đổi thành `true`, `a.getUseCaches()` **vẫn false**.
- `b` được tạo sau khi đổi default thành true, nên có `useCaches=true`.
- `a.setUseCaches(true)` chỉ đổi instance `a`, không ảnh hưởng `b` hay static default.
- `HttpURLConnection.setFollowRedirects(false)` làm connection mới `c` có redirect flag false, nhưng `c.setInstanceFollowRedirects(true)` override instance và **global vẫn false**.
- `finally` khôi phục values trước thử nghiệm; **không giữ global defaults của demo cho những đoạn code khác**.
- Các flags này không phải bằng chứng HTTP request đã được gửi; tất cả connections trong ví dụ **chưa connected**.

## 8. Các cấu hình mặc định khác dễ “tràn” giữa modules

Ngoài ResponseCache/CookieHandler, Java Networking có các hook toàn JVM khác:

| Global API | Ý nghĩa | Nguy cơ khi module tự ý đổi |
| --- | --- | --- |
| `ProxySelector.setDefault(...)` | Selector route mặc định cho các APIs dùng nó | Traffic đi sai proxy, bypass egress hoặc lỗi routes |
| `Authenticator.setDefault(...)` | Callback auth mặc định | Trả nhầm credential sang origin/proxy không mong muốn |
| `CookieHandler.setDefault(...)` | Default cookie handler | Cookie/session leakage giữa users/modules |
| `ResponseCache.setDefault(...)` | Cache hook mặc định | Phục vụ stale/private responses cho caller khác |
| `URLConnection.setDefaultUseCaches("http", ...)` | Cache flag mặc định cho protocol | Chỗ này disable cache, chỗ khác kỳ vọng cache |
| `URLConnection.setDefaultAllowUserInteraction(...)` | Default permission tương tác | Thay đổi behavior URLConnection objects mới |
| `HttpURLConnection.setFollowRedirects(...)` | Redirect default | Client không follow như dự kiến hoặc redirect ngoài policy |
| `URLConnection.setFileNameMap(...)` | Mapping file extension → MIME | Mapping MIME/conversion thay đổi xuyên module |
| `URLConnection.setContentHandlerFactory(...)` | Cài factory content handlers | Cấu hình một lần; plugin thứ hai có thể không cài được |
| `URL.setURLStreamHandlerFactory(...)` | Cài factory cho URL protocols | Cấu hình một lần trong VM; đổi muộn có thể lỗi |
| System properties `http.proxyHost`, `https.proxyHost` | Một số URL handlers/default selectors dùng | Thay egress toàn process, không bao trùm mọi library |
| `java.net.useSystemProxies` | Dùng OS proxy settings khi được hỗ trợ | Thường đọc lúc JVM startup; thay runtime có thể không tác động |

Không phải mọi hook ảnh hưởng **tất cả libraries** hay tất cả protocols. `ProxySelector` áp cho những clients chủ động sử dụng selector, `ResponseCache` chủ yếu là URLConnection cache hook, `CookieHandler` liên quan HTTP URL handler và clients được gắn explicit. **“Default toàn JVM” = shared state nếu API dùng default đó**, không có nghĩa mọi library tự động tra cùng object.

### 8.1. Authenticator: scope credential phải thật chặt

Một custom `Authenticator` có thể nhận challenge từ origin hoặc HTTP proxy. Nếu dùng `Authenticator.setDefault(...)`, nó có khả năng được gọi cho **nhiều destinations** trong JVM. Phải phân biệt:
- `RequestorType.SERVER` và `RequestorType.PROXY`.
- Requested host/port/protocol và realm/auth scheme.
- Credential store đúng tenant/service.
- Không ghi raw password trong log hoặc literal source code.
- Không trả private-origin secrets cho proxy challenge và ngược lại.

Một `HttpClient` tạo bởi `HttpClient.newBuilder().authenticator(myAuthenticator)` có explicit per-client dependency, dễ audit hơn global singleton. Tuy nhiên cùng một authenticator object vẫn có thể chứa shared state; per-client builder không tự tạo isolation nếu application cố tình share secrets object.

### 8.2. ProxySelector: toàn JVM, nhưng request route vẫn phải test

`ProxySelector.setDefault(...)` thay selector mặc định. Trong code multi-tenant, thay default theo request rất nguy hiểm. Nếu dùng `HttpClient.Builder.proxy(selector)`, mỗi client có thể chọn selector riêng; nếu muốn force direct thì `HttpClient.Builder.NO_PROXY` (Java 17). Với URLConnection legacy, `url.openConnection(Proxy.NO_PROXY)` chỉ định direct cho connection đó, không phụ thuộc default proxy selector. Tránh fail-open DIRECT sau proxy error nếu egress policy cấm.

Các JVM system properties như `http.proxyHost`/`http.nonProxyHosts` hay `socksProxyHost` không tự tác động mọi HTTP library/custom clients. Kiểm tra proxy side logs hoặc permitted network tracing để biết route thật. Mặc định không phải một authorization boundary; proxy vẫn phải bảo vệ allowed destinations.

### 8.3. “Chỉ cài một lần” không giống “thay default tùy ý”

`URL.setURLStreamHandlerFactory(...)` và `URLConnection.setContentHandlerFactory(...)` là các extension mechanisms cho URL scheme/content types, có giới hạn việc cài factory. Theo Javadoc, một factory của `URL` chỉ được đặt **một lần cho VM**, gọi tiếp có thể ném `Error`; `URLConnection.setContentHandlerFactory(...)` cũng chỉ được đặt một lần, gọi tiếp có thể ném `Error`. Không đề xuất “khôi phục factory cũ trong finally” như cache/cookie defaults. Library tự ý gọi các setters này có thể chiếm quyền cấu hình của application server và xung đột với plugin container.

`URLConnection.setDefaultRequestProperty(key,value)` đã **deprecated**; Javadoc khuyên dùng `conn.setRequestProperty(...)` trên từng instance. Đừng dùng default request property để phát tán `Authorization` hay session headers toàn JVM.

## 9. Những gì thay đổi ngay, những gì đã được chụp ở thời điểm tạo

Có hai nhóm tác dụng cần phân biệt:

### 9.1. Static default được chụp khi tạo object

`URLConnection.setDefaultUseCaches("http", false)` thay giá trị mà **future HTTP URLConnections** sẽ dùng làm default. Connection được tạo trước đó có `useCaches` của chính nó và **không tự đổi** khi static default đổi. Tương tự, `HttpURLConnection.setFollowRedirects(false)` đặt static default cho các **HttpURLConnection instances mới**. Ví dụ 3 kiểm chứng điều này.

### 9.2. Handler global được tham chiếu tại I/O time theo implementation

`ResponseCache.setDefault(cache)` và `CookieHandler.setDefault(handler)` đăng ký singleton handler được HTTP URL protocol implementation có thể tham chiếu trong quá trình request/response. **Không được xem một `URL.openConnection()` là một “snapshot” bất biến của toàn bộ các handler global**. Việc đổi `CookieHandler.setDefault(...)` hoặc `ResponseCache.setDefault(...)` trong lúc nhiều requests đang hoạt động có thể khiến behavior giữa các phases khác nhau tùy implementation, thời điểm callback và protocol handler. Vì vậy không dùng global swap như dynamic request scope.

Bài test dùng `try/finally` chỉ để **khôi phục trạng thái khi chạy độc lập**, không phải mẫu thread-safe trong một server có concurrent requests. Để tránh race:
1. Set globals một lần ở bootstrap nếu toàn ứng dụng thật sự đồng nhất.
2. Tốt hơn, truyền dependencies qua constructors/builders riêng cho từng client/session.
3. Thiết kế integration tests chạy trong process/isolated JVM riêng khi cần sửa static defaults.
4. Không mutate global defaults của một JVM đang phục vụ traffic thật.

## 10. Khi nào cần ResponseCache và CookieHandler cùng lúc?

Một Java HTTP workflow có thể:
1. `CookieManager` nhận `Set-Cookie: sid=...` khi login.
2. Request sau gắn `Cookie: sid=...` dựa vào URI/path/secure policy.
3. `ResponseCache` kiểm tra resource có thể lấy từ local cache thay vì network.
4. Server có thể trả private content tùy session cookie.

Đây cũng là **điểm nguy hiểm nhất**: nếu cache key chỉ gồm URI, response `/account/profile` của user A có thể được lấy lại cho user B. Không thể “bật ResponseCache + CookieHandler” rồi tin rằng tự động tránh cross-user data leak. Cache application cần:
- Mặc định **không cache authenticated/private responses** ở shared cache.
- Nếu cache user-specific, partition theo tenant/session an toàn, tuân thủ `Cache-Control`/`Vary` và tránh ghi secrets vào key/log.
- Cân nhắc no-store cho `Set-Cookie` responses, tokens, sensitive endpoints theo policy.
- Không lấy cookie store của tenant A truyền vào `HttpClient` của tenant B.
- Không dùng cache lookup để bypass authorization; permission phải được bảo đảm cả trên cache hit.
- Đảm bảo logout/revocation/session expiry có cache invalidation tương thích.

Ví dụ 1 **chỉ cache `/public`** với body không chứa dữ liệu session, và ví dụ 2 **tắt cache** trên các legacy URLConnections mang cookie. Đây là cách cố ý tách hai khái niệm trong bài học, không phải một HTTP caching policy đầy đủ.

## 11. Caching, cookies và redirects phối hợp như thế nào?

Giả sử URL `https://service.example.test/start` trả HTTP 302 tới `/login` rồi nhận `Set-Cookie` ở bước sau. Một client có thể:
- Follow redirect theo chính sách `HttpURLConnection.setInstanceFollowRedirects` / global static default.
- Dùng CookieHandler để nhận cookie của endpoint trả Set-Cookie.
- Cho phép cache một số responses nếu cache policy xác nhận hợp lệ.

Nhưng không có bảo đảm “redirect 302 luôn được cache” hoặc “CookieManager chắc chắn gửi cookie cho mọi host redirect”. Redirect có thể đổi hostname/path/scheme; mỗi step phải xét cookie `Domain`, `Path`, `Secure` và security. Cache hit có thể trả response mà không liên hệ network; nếu handler không mô phỏng đúng response metadata/session policy, application có thể không nhận headers hoặc side effects như khi lấy origin.

Không đồng nhất:
- `HttpURLConnection.setFollowRedirects(...)`: static default redirect policy của legacy stack.
- `HttpURLConnection.setInstanceFollowRedirects(...)`: per-connection.
- `HttpClient.Builder.followRedirects(HttpClient.Redirect.NORMAL/ALWAYS/NEVER)`: per modern client.

Với request có authorization header, redirects sang origin khác có thể tạo security boundary mới. Không cấp credential tự động mà không xét host/trust, không follow HTTP→HTTPS hoặc HTTPS→HTTP một cách mù quáng. Với cookie, avoid HTTP plaintext nếu cookie Secure/phiên nhạy cảm.

## 12. URLConnection và HTTP response-body resource lifecycle

`HttpURLConnection` instance thường gắn với **một HTTP request**, nhưng underlying persistent TCP connection có thể được chia sẻ giữa nhiều instances theo Javadoc. Để đọc body:

~~~java
HttpURLConnection connection =
        (HttpURLConnection) url.openConnection();

connection.setConnectTimeout(5000);
connection.setReadTimeout(5000);
connection.setUseCaches(false);

try {
    int status = connection.getResponseCode();
    InputStream source = status >= 400
            ? connection.getErrorStream()
            : connection.getInputStream();

    if (source != null) {
        try (InputStream body = source) {
            consumeBodyWithLimit(body);
        }
    }
} finally {
    connection.disconnect();
}
~~~

Đây là **mã minh họa không độc lập**: `url` và `consumeBodyWithLimit` phải được application cung cấp, cùng import `java.io.*` và `java.net.*`. Với HTTP error, `getErrorStream()` có thể trả `null`; status code không đồng nghĩa với có error body. `disconnect()` có thể đóng underlying socket nếu persistent connection đang idle, nhưng không được xem là hàm chắc chắn phá mọi shared connection.

**Trước khi tích cache**, phải tính rõ streaming: một `CacheRequest` có thể bị `abort()` nếu response read lỗi hoặc không hoàn tất. Không bao giờ phát lại bản cache incomplete. Với modern HttpClient streaming body, ownership được mô tả bởi `BodyHandler`/`BodySubscriber`, không liên quan trực tiếp tới `ResponseCache` global.

## 13. Sự thật về “cache ẩn” trong ứng dụng Java

Một ứng dụng Java có thể có **nhiều lớp cache**:

~~~text
business cache (per tenant / feature)
        │
HTTP library cache (nếu cấu hình)
        │
URLConnection ResponseCache hook (legacy URL handler)
        │
HTTP proxy / CDN cache (ngoài process)
        │
server/application cache
        │
database cache
~~~

`URLConnection.setUseCaches(false)` điều khiển **khả năng dùng cache tại URLConnection protocol handler**, không có phép màu vô hiệu hóa CDN cache, proxy cache, DNS cache, application cache hoặc cache của một HTTP library khác. Header `Cache-Control: no-cache` **không đồng nghĩa “không được lưu”**; theo HTTP caching semantics nó chủ yếu yêu cầu validation trước reuse. `no-store` mới là directive liên quan cấm lưu theo RFC 9111.

Ngoài ra, `CookieHandler` cũng không đảm bảo cookie persistence trên disk, cũng không tự xử lý session rotation/revocation hay CSRF. Đừng dùng khái niệm “stateful HTTP session” để suy rằng TCP connection và cookie session là cùng một thứ. Cookies sống qua nhiều HTTP requests, có thể qua nhiều TCP connections; ResponseCache cache resources theo semantics riêng.

## 14. Testing strategy: cô lập global state và test nhánh miss/hit/deny

Nếu bạn viết một cache hoặc cookie integration, hãy thiết kế test:

**ResponseCache**
- GET public cacheable → miss rồi put, GET lần sau → hit.
- `setUseCaches(false)` → bypass.
- `no-store` → không put.
- `private` / `Authorization` / `Cookie` → không cache shared response.
- Request headers khác `Vary` → không reuse sai representation.
- Entry hết hạn → revalidation hoặc network.
- Write body lỗi giữa chừng → `CacheRequest.abort()`, không serve partial.
- Hai concurrent misses cùng URI → xử lý race/duplicate downloads theo policy.
- Cache size cap/eviction, crash recovery, update sau write methods.
- Vary status/headers/content-type không bị mất trên hit.

**CookieHandler**
- `ACCEPT_NONE`: Set-Cookie không được lưu.
- `ACCEPT_ORIGINAL_SERVER`: first-party cookie đúng host/path.
- `Secure`: không gửi qua plain HTTP.
- Domain/path matching, expiry, cookie deletion.
- Không share session giữa users/tenants.
- `HttpURLConnection` dùng global jar đã được cài; `HttpClient` chỉ dùng jar explicit.
- Header fields không phân biệt hoa/thường đúng HTTP semantics; không log cookie values.

**Global defaults**
- Create connection A trước static default change, B sau; quan sát `getUseCaches` / `getInstanceFollowRedirects`.
- Instance setter override thành công khi chưa connected.
- Thay setter sau connected bị từ chối theo API tương ứng.
- Test riêng process nếu cần thay global factories một-lần.
- Khi integration tests chạy song song, tránh dùng chung JVM static setters hoặc dùng sandbox/isolated subprocess.
- Đọc/ghi default ở startup, ghi rõ system properties và target JDK build.

**Không gọi external URLs trái phép** khi test. Ba ví dụ của bài dùng loopback/không network để có kết quả ổn định và tránh ảnh hưởng server ngoài.

## 15. Troubleshooting: tìm nguyên nhân đúng tầng

| Triệu chứng | Khả năng | Kiểm tra |
| --- | --- | --- |
| Request GET thứ hai vẫn gọi origin | Cache miss, no handler, useCaches=false, response không cacheable | `ResponseCache.getDefault()`, `conn.getUseCaches()`, cache counters, response headers |
| Lấy dữ liệu cũ trong khi muốn fresh | Cache chưa invalidated, TTL/revalidation sai, proxy/CDN cache | Response headers, `Age`, network trace có quyền, cache policy |
| Cache trả dữ liệu user khác | Cache key thiếu tenant/session, không tuân `private`/`Vary` | Disable affected cache, security incident review, partition/cache invalidation |
| Cookie không được gửi trong URLConnection | Default CookieHandler null, policy reject, scope domain/path/secure sai | `CookieHandler.getDefault()`, CookieStore, request URI, Set-Cookie |
| Cookie có trong CookieStore nhưng modern HttpClient không gửi | Builder không có `cookieHandler(...)` | `client.cookieHandler()`, builder wiring |
| Login thành công nhưng request kế tiếp mất phiên | Cookie expiry/path/domain/scheme, different jars hoặc redirects | Cookie flags, URI, handler instance, tenant isolation |
| Chạy unit test riêng PASS, chạy suite song song FAIL | Test khác thay global defaults | Isolate process/serial test, restore state, tránh global mutation |
| `setUseCaches` ném IllegalStateException | Setter gọi sau connection đã established | Đặt trước `connect/getInputStream/getHeaderFields` |
| `HttpClient` vẫn tải từ origin dù ResponseCache có entry | Modern HttpClient không dựa vào ResponseCache global | Dùng cache layer riêng cho client |
| Redirect behavior khác nhau giữa modules | Global `setFollowRedirects` thay ở runtime | `getInstanceFollowRedirects()` và thời điểm tạo connection |
| CookieManager tăng memory lâu dài | In-memory store giữ cookies, session lifecycle không cleanup | Expiry, removeAll/logout, monitoring |
| Không thấy cache put commit | Body chưa đọc EOF/stream chưa đóng, CacheRequest aborted | I/O lifecycle, getBody close/abort, counters |
| Proxy route lạ | ProxySelector default/global hoặc environment | `ProxySelector.getDefault()`, per-client overrides |
| SecurityException khi setDefault | Security manager/permission policy cản theo JDK target | Permission contract; không tự bypass policy |
| Một custom URL handler không dùng cookie/cache globals | Handler không hỗ trợ | Kiểm tra handler documentation, không giả định mọi URL scheme giống HTTP |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Gọi `ResponseCache.setDefault(cache)` có tự bật caching toàn bộ request của `HttpClient.newHttpClient()` không?  
**Đáp án:** Không. ResponseCache là URLConnection/protocol-handler hook; modern HttpClient không tự dùng global cache đó.

**Câu 2.** `conn.setUseCaches(true)` có đảm bảo cache hit?  
**Đáp án:** Không. Chỉ cho phép handler dùng cache khi có implementation/entry đúng chính sách.

**Câu 3.** Cache key chỉ gồm URI có an toàn với response khác nhau theo Cookie/User?  
**Đáp án:** Không. Shared cache có thể làm rò session/private data; phải tuân `Cache-Control`/`Vary`, partition hoặc không cache authenticated responses.

**Câu 4.** `ResponseCache.get(...)` trả `null` nghĩa là gì?  
**Đáp án:** Cache miss/không dùng entry; protocol handler tiếp tục lấy resource từ nguồn theo contract.

**Câu 5.** `CacheRequest.abort()` có được giữ lại bản body đã ghi một nửa không?  
**Đáp án:** Không. Bản chưa hoàn chỉnh phải bị loại bỏ, không serve như đầy đủ.

**Câu 6.** `CookieHandler.setDefault(jar)` có khiến modern `HttpClient.newHttpClient()` tự gửi cookie trong jar không?  
**Đáp án:** Không. Cần `HttpClient.Builder.cookieHandler(jar)` explicit.

**Câu 7.** `CookieManager(null, ACCEPT_ORIGINAL_SERVER)` có tự persist cookie trên disk không?  
**Đáp án:** Không. Store mặc định là in-memory.

**Câu 8.** Hai users dùng cùng `CookieManager` có thể gặp vấn đề gì?  
**Đáp án:** Rò cookie/session giữa contexts, vi phạm isolation; cần jar tách theo tenant/session.

**Câu 9.** Sau `URLConnection.setDefaultUseCaches("http",false)`, connection đã tạo trước có tự đổi `getUseCaches()` không?  
**Đáp án:** Không. Setting default ảnh hưởng future connections; instance có flag riêng.

**Câu 10.** `HttpURLConnection.setFollowRedirects(false)` và `setInstanceFollowRedirects(false)` có cùng scope?  
**Đáp án:** Không. Một cái static default cho connections mới, cái kia cho một instance.

**Câu 11.** `URLConnection.setDefaultUseCaches(boolean)` là static method phải gọi bằng class?  
**Đáp án:** Không. Overload một boolean là instance method; overload `(String,boolean)` là static Java 9+.

**Câu 12.** Có nên mỗi thread tự gọi `CookieHandler.setDefault(ownJar)` trước khi request rồi restore ngay sau đó?  
**Đáp án:** Không. Không có per-thread isolation; concurrent request có thể gặp handler của thread khác.

**Câu 13.** Tại sao `Cache-Control: no-cache` và `no-store` không giống nhau?  
**Đáp án:** `no-cache` chủ yếu yêu cầu revalidation trước reuse, `no-store` liên quan cấm lưu response theo RFC 9111.

**Câu 14.** Cookies là một phần của TCP connection?  
**Đáp án:** Không. Cookies là HTTP state qua nhiều requests/connections; phạm vi do URI/cookie attributes quyết định.

**Câu 15.** Có thể sửa `URL.setURLStreamHandlerFactory(...)` vài lần rồi restore old factory trong finally không?  
**Đáp án:** Không. Đây là API factory một-lần cho VM theo Javadoc, gọi tiếp có thể lỗi.

**Câu 16.** Vì sao demo 1 cho `first=origin-1`, `second=origin-1`, `bypass=origin-2`?  
**Đáp án:** Lần đầu miss+store, lần hai cache hit, lần ba per-connection `useCaches=false` nên fetch origin mới.

**Câu 17.** `HttpClient.Builder.cookieHandler(jar)` có làm các legacy URLConnections dùng jar đó không?  
**Đáp án:** Không tự động; chỉ client builder đó dùng jar, legacy URL handler vẫn tùy default CookieHandler.

**Câu 18.** Trong server nhiều tenants, cách tốt nhất để xử lý cookie/cache/redirect options là gì?  
**Đáp án:** Đặt dependencies/scope riêng per client/session, ưu tiên explicit builder/instance settings; tránh mutate global JVM state lúc đang phục vụ traffic.

## 17. Checklist trước khi đưa vào ứng dụng

1. Phân biệt **per-instance URLConnection setters** và **system-wide/default setters**.
2. `ResponseCache` chỉ là **cache hook**; có implementation và chính sách RFC 9111 hợp lệ trước khi dùng với dữ liệu thật.
3. `CookieHandler` chỉ là **session policy hook**; xác định `CookieManager`/`CookieStore`/`CookiePolicy` rõ ràng.
4. Không lưu response `private`/`no-store` hoặc authenticated content vào shared cache; xử lý `Vary`/TTL/revalidation/partial writes.
5. Không chia sẻ cookie jar giữa tenants; xóa cookie khi logout, bảo vệ values khỏi log.
6. Dùng `URLConnection.setUseCaches(false)` trước network I/O khi cần bypass URL handler cache.
7. Coi global handlers/static flags là **shared mutable state**, không dùng để định tuyến policy theo từng thread/request.
8. Với `java.net.http.HttpClient`, cấu hình `cookieHandler(...)` explicit; đừng kỳ vọng global `CookieHandler` hoặc `ResponseCache` tự được dùng.
9. Phân biệt `HttpURLConnection.setFollowRedirects(...)` static và `setInstanceFollowRedirects(...)` per-connection.
10. Đặt timeout/connect/read, cleanup body/error streams, và `disconnect` theo HTTP handler lifecycle.
11. Test cache hit/miss/no-store, cookie domains/paths/secure, redirects, concurrency và default isolation.
12. Tách global integration tests vào process riêng; restore state trong `finally` chỉ là cleanup sau test, **không** giải quyết race khi concurrency.
13. Không cài lại `URLStreamHandlerFactory` / `ContentHandlerFactory` vì chỉ hỗ trợ một lần cài.
14. Kiểm soát proxy/authentication/redirect cùng chính sách security, không nới policy để fix lỗi.
15. Theo dõi metrics: cache hit/miss/size, cookie counts, session-jar ownership, URLConnection errors, redirection và timeout.
16. Khi không cần backward compatibility, cân nhắc modern HTTP client với explicit builder/lifecycle phù hợp thay vì global legacy hooks.

## Tài liệu chính thức

- [Java SE 17 — ResponseCache](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ResponseCache.html): global default, get/put callbacks, URLConnection cache flag.
- [Java SE 17 — CacheRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CacheRequest.html): getBody/abort, xử lý partial cache writes.
- [Java SE 17 — CacheResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CacheResponse.html): cached headers và body input stream.
- [Java SE 17 — CookieHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieHandler.html): global default và cookie get/put.
- [Java SE 17 — CookieManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html): CookieStore, CookiePolicy, cookie acceptance.
- [Java SE 17 — CookieStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieStore.html): add/get/removeAll và scope.
- [Java SE 17 — URLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): per-instance options, static protocol defaults, content handler factory.
- [Java SE 17 — HttpURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): global/instance redirect flags, input/error streams, disconnect/persistent connections.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): explicit `cookieHandler`, `authenticator`, `proxy` và `followRedirects`.
- [Java SE 17 — ProxySelector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html) và [Authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Authenticator.html): system-wide routing và credentials callbacks.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html): freshness, validation, Vary và private/shared caching rules.
- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265.html): Cookie/Set-Cookie, Domain/Path/Secure/HttpOnly và lifetime.

**Tư duy cốt lõi:** `ResponseCache` và `CookieHandler` trong `URLConnection` cung cấp những hook rất mạnh nhưng **mang tính toàn JVM khi đăng ký qua `setDefault`**. Chỉ chia sẻ khi policy, users và lifecycle thực sự cho phép; còn với đa tenant/session hoặc modern HTTP client, ưu tiên **per-client dependencies và per-connection configuration**, xác nhận hành vi bằng test thay vì dựa vào tên method.
