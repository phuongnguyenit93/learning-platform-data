# Java 11+ — Cấu hình HTTP: `ProxySelector` và lựa chọn proxy

## 1. Mục tiêu và mô hình hoạt động

Khi một ứng dụng Java gửi HTTP request, kết nối có thể đi **trực tiếp đến máy chủ đích** hoặc đi **qua một proxy** theo chính sách mạng. Proxy là một điểm trung gian có thể giúp tổ chức quản lý đường ra, phân quyền, ghi nhận truy cập hoặc áp dụng quy tắc hạ tầng. Không phải mọi kết nối đều được phép đi qua cùng proxy, và một số đích nội bộ có thể phải kết nối trực tiếp.

Từ **Java 11**, `java.net.http.HttpClient` chuẩn hỗ trợ cấu hình proxy bằng `java.net.ProxySelector`:

```java
HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.example.com", 8080)))
        .build();
```

Đoạn trên là minh họa cấu hình, **không tự gửi request**. Cần import `java.net.http.HttpClient`, `java.net.ProxySelector` và `java.net.InetSocketAddress`. Host `proxy.example.com` chỉ là tên ví dụ, cần thay bằng proxy được cấp phép thực sự khi triển khai.

Cơ chế căn bản:

1. Ứng dụng tạo `HttpClient`, có thể cung cấp một `ProxySelector` qua `HttpClient.Builder.proxy(...)`.
2. Trước khi thiết lập kết nối phù hợp, client dùng chính sách proxy để xác định tuyến đi đến URI đích.
3. `ProxySelector.select(URI)` trả danh sách `Proxy` ứng viên theo thứ tự ưu tiên; phần tử `Proxy.NO_PROXY` biểu diễn **kết nối trực tiếp**.
4. HttpClient tiến hành kết nối theo khả năng và quy tắc triển khai. Việc chọn proxy không đồng nghĩa proxy chắc chắn kết nối được hoặc request đã thành công.
5. Khi không thiết lập được kết nối đến proxy, `connectFailed(...)` là callback để thông báo lỗi cho selector, giúp chính sách có thể điều chỉnh danh sách lựa chọn.

**`ProxySelector` chọn tuyến kết nối; nó không phải HTTP response handler, HTTP authenticator, DNS resolver hay một proxy server.** Việc tự tạo `ProxySelector` không tự động tạo một máy chủ proxy, không chuyển hướng byte đi đâu nếu chưa có client sử dụng và không bảo đảm HTTP request thành công.

## 2. Ba cách cấu hình proxy thông dụng trên Java 11+

| Cách cấu hình `HttpClient` | Hành vi mong muốn | Khi nào phù hợp |
| --- | --- | --- |
| Không gọi `Builder.proxy(...)` | Client sử dụng **default proxy selector** theo cấu hình/JDK, theo hợp đồng API. | Ứng dụng muốn tôn trọng cấu hình proxy chung của môi trường. |
| `.proxy(ProxySelector.of(address))` | Một **HTTP proxy cố định** dùng cho URI `http` và `https` theo factory. | Dịch vụ có một proxy đầu ra được cấp phép và không cần tuyến khác nhau theo đích. |
| `.proxy(HttpClient.Builder.NO_PROXY)` | **Không dùng proxy**, kết nối trực tiếp. | Ứng dụng có yêu cầu rõ ràng là bỏ qua cấu hình proxy mặc định. |
| `.proxy(customSelector)` | Quy tắc chọn dựa trên URI/hostname/scheme/policy ứng dụng. | Cần phân biệt đích nội bộ, đích qua proxy và các tuyến riêng. |

### 2.1. Proxy theo cấu hình mặc định

```java
HttpClient client = HttpClient.newHttpClient();
ProxySelector systemSelector = ProxySelector.getDefault();
```

`ProxySelector.getDefault()` trả selector được đăng ký ở mức JVM, có thể chịu ảnh hưởng bởi **system properties** và cấu hình môi trường. Nếu ứng dụng không chỉ định proxy trong builder, HttpClient dùng selector mặc định theo quy định API. Trong thực tế các biến và cấu hình hệ điều hành có thể khác nhau; không giả định ứng dụng luôn dùng proxy hoặc luôn đi trực tiếp.

**Bẫy quan trọng:** `client.proxy()` có thể trả `Optional.empty()` khi **không có selector được chỉ định trực tiếp trong builder**, dù client vẫn có thể sử dụng một selector mặc định **không được phơi bày**. Vì vậy:

```java
boolean explicit = client.proxy().isPresent();
```

`explicit == false` chỉ có nghĩa “không cấu hình selector tường minh trong builder”, **không phải** bằng chứng rằng request sẽ bypass proxy. Muốn thực sự tắt proxy, cung cấp `HttpClient.Builder.NO_PROXY`.

Không nên thay `ProxySelector.setDefault(...)` ở mọi nơi chỉ để đổi một client; đây là thay đổi **toàn JVM**, dễ ảnh hưởng thư viện khác và các client được tạo về sau. Ưu tiên cấu hình cục bộ trên builder.

### 2.2. Proxy cố định với `ProxySelector.of`

```java
InetSocketAddress proxyAddress =
        new InetSocketAddress("proxy.example.com", 8080);

HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.of(proxyAddress))
        .build();
```

`ProxySelector.of(InetSocketAddress)` có từ **Java 9**, tiếp tục sử dụng tốt trên Java 11 và các bản sau. Theo Java API, factory trả một selector dùng proxy được cung cấp cho các request `http` và `https`. `InetSocketAddress` chỉ giữ host và port của **proxy**, không phải URL của server đích và không phải chuỗi `"http://user:password@proxy:port"`.

Một chi tiết thường ít được biết: `ProxySelector.of(null)` là factory hợp lệ dùng để **tắt proxy**, nhưng trong code dùng HttpClient nên `HttpClient.Builder.NO_PROXY` biểu đạt ý định kết nối trực tiếp rõ ràng hơn:

```java
ProxySelector directSelector = ProxySelector.of(null);
HttpClient directClient = HttpClient.newBuilder()
        .proxy(HttpClient.Builder.NO_PROXY)
        .build();
```

Không sử dụng `null` để biểu thị “không có proxy” ở mọi nơi tùy tiện: `ProxySelector.of(null)` có hợp đồng riêng, khác với việc truyền `null` vào các API khác.

## 3. Hiểu `ProxySelector.select(URI)` và giá trị trả về

API trọng tâm:

```java
public abstract List<Proxy> select(URI uri);
```

Tham số `uri` là **URI của tài nguyên đích**, chẳng hạn `http://service.example.invalid/report` hoặc `https://api.example.invalid/v1/items`. Nó **không phải** URI của máy chủ proxy.

Một selector tùy chỉnh có thể trả:

```java
return List.of(new Proxy(
        Proxy.Type.HTTP, new InetSocketAddress("proxy.example.com", 8080)));
```

Hoặc trả kết nối trực tiếp:

```java
return List.of(Proxy.NO_PROXY);
```

Các đoạn code này là thân hàm minh họa, không chạy độc lập. Cần `java.net.Proxy`, `java.net.InetSocketAddress` và `java.util.List`.

Theo hợp đồng `ProxySelector`, danh sách biểu diễn các **lựa chọn tuyến theo thứ tự ưu tiên**. Khi không muốn dùng proxy, hãy trả danh sách chứa **`Proxy.NO_PROXY`**, không trả `null` hoặc danh sách rỗng. Một selector có thể cung cấp nhiều proxy để cho phép client thử các cách kết nối khi thích hợp; **không** suy luận rằng mọi `HttpClient` đều buộc phải thử hết danh sách theo đúng thuật toán tự nghĩ, vì kết quả và việc fallback phụ thuộc giao thức và triển khai.

Các loại `Proxy.Type` của Java gồm `DIRECT`, `HTTP` và `SOCKS`. `Proxy.NO_PROXY` là lựa chọn direct chuẩn. Với Java `HttpClient`, trường hợp được tài liệu hóa rõ ràng nhất là **HTTP proxy** dùng với `http` và `https`. Không tự kết luận rằng custom selector trả `Proxy.Type.SOCKS` chắc chắn được HttpClient hỗ trợ mọi trường hợp; phải kiểm tra JDK, protocol và môi trường thực tế nếu mạng của bạn cần SOCKS.

### Chọn dựa trên gì?

- **Scheme:** `http` hoặc `https`; không giả định mọi scheme khác được HttpClient hỗ trợ.
- **Hostname:** đích nội bộ/loopback, nhóm domain công ty, đích bắt buộc đi qua egress gateway.
- **Port:** nếu chính sách phân biệt đích theo port; `uri.getPort()` có thể là `-1` nếu URI không ghi port rõ ràng.
- **Đặc thù bảo mật:** đích bắt buộc qua proxy không nên tự động bypass khi proxy hỏng nếu policy không cho phép.

Khi so sánh hostname, nên thống nhất chữ hoa/thường (DNS host không phân biệt case), xác định cách xử lý subdomain và tránh `String.contains("example.com")` để quyết định cho phép/không cho phép. Chuỗi `"evil-example.com"` chứa `"example.com"` nhưng không phải subdomain của `example.com`.

## 4. Selector tùy chỉnh: `select` và `connectFailed`

Muốn chọn proxy tùy URI, kế thừa `ProxySelector` và triển khai **cả hai** phương thức trừu tượng:

```java
@Override
public List<Proxy> select(URI uri) {
    // Trả danh sách Proxy, có thể chứa Proxy.NO_PROXY.
}

@Override
public void connectFailed(URI uri, SocketAddress address, IOException error) {
    // Ghi nhận lỗi thiết lập kết nối với proxy (không log credential).
}
```

Các dòng trên là khung minh họa, không phải class đầy đủ. Mục 6 có ví dụ chạy độc lập.

`connectFailed(URI uri, SocketAddress sa, IOException ioe)` **không phải callback cho mọi HTTP status không thành công**. Nó thông báo một **kết nối tới proxy** (hoặc proxy/SOCKS tùy API và caller) không thiết lập được. HTTP `404`/`422` từ ứng dụng đích hay HTTP `407 Proxy Authentication Required` sau khi kết nối proxy được thiết lập là những tình huống khác và phải xử lý qua giao thức, status, authentication hoặc lỗi tương ứng.

Selector tùy chỉnh có thể dùng `connectFailed` để ghi metric, đánh dấu proxy hỏng tạm thời và điều chỉnh ưu tiên. Không nên để callback này tự động bỏ proxy rồi gửi request quan trọng **trực tiếp** ra Internet nếu quy định doanh nghiệp bắt buộc qua proxy.

**Đồng thời:** một `HttpClient` được chia sẻ để gửi nhiều request, nên một selector có trạng thái mutable cần thiết kế thread-safe. Đừng dùng `ArrayList` hay `HashMap` mutable mà không có đồng bộ để ghi trạng thái proxy từ nhiều callback. `AtomicInteger`, cấu trúc concurrent hoặc trạng thái bất biến là lựa chọn thích hợp theo nhu cầu.

## 5. Luồng logic khi lựa chọn proxy

```text
URI của HTTP request
         |
         v
HttpClient có ProxySelector?
         |
         +-- Selector tường minh ----------+
         |                                  |
         +-- Không cấu hình: default -------+
                                            |
                                            v
                                 ProxySelector.select(URI)
                                            |
                        +-------------------+------------------+
                        |                                      |
                   Proxy.NO_PROXY                          Proxy.Type.HTTP
                        |                                      |
                        v                                      v
                 Kết nối trực tiếp                  Kết nối đến proxy
                        |                                      |
                        +-------------------+------------------+
                                            |
                                   Trao đổi HTTP/TLS
                                            |
                                            v
                            HttpResponse hoặc lỗi I/O
```

Đây là sơ đồ khái niệm, không phải bảo đảm mọi client đều gọi `select` đúng một lần/request. Redirect, kết nối được tái sử dụng, proxy fallback, các phiên bản HTTP và cấu hình hệ thống có thể làm luồng thực tế phức tạp hơn.

Với `HTTP` qua HTTP proxy, request HTTP có thể được chuyển cho proxy theo cách diễn đạt URL đích. Với `HTTPS` qua HTTP proxy, giao thức thường dùng **CONNECT tunnel** trước khi thực hiện TLS tới máy chủ đích. Việc selector chọn HTTP proxy cho URI `https` **không** chứng minh tunnel, chứng chỉ TLS hoặc proxy authentication đã thành công. Vì vậy ví dụ dưới đây **chỉ gửi HTTP** tới proxy giả lập; phần lựa chọn cho HTTPS được kiểm tra riêng, không thực hiện kết nối HTTPS.

## 6. Ví dụ Java 11+ độc lập: proxy cho đích từ xa, direct cho loopback

Chương trình sử dụng hai `HttpServer` được JDK cung cấp trong module `jdk.httpserver`:

- `origin` giả lập server đích ở `127.0.0.1`, trả `via-origin`.
- `proxy` giả lập HTTP proxy ở `127.0.0.1`, trả `via-proxy`. Proxy giả lập **không forward request** đến server cuối; mục tiêu là chứng minh HttpClient đã kết nối đến proxy được chọn.
- `RoutingPolicy` chọn `Proxy.Type.HTTP` khi URI có hostname `service.example.invalid`, nhưng chọn `Proxy.NO_PROXY` khi URI trỏ tới `127.0.0.1` hoặc `localhost`. Với các host khác, chính sách minh họa này trả direct; **production phải thay chính sách đó theo yêu cầu an ninh của tổ chức**.
- `client.send(...)` gửi một request với hostname mẫu `service.example.invalid`: vì proxy có sẵn ở loopback, chương trình **không cần DNS/Internet tới hostname mẫu**. Một request khác tới `127.0.0.1` được gửi trực tiếp tới origin.
- Kiểm tra thêm selector với URI HTTPS **chỉ ở mức chọn tuyến**, factory `ProxySelector.of(null)` và `HttpClient.Builder.NO_PROXY`.

Lưu vào **`ProxySelectorDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.SocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public final class ProxySelectorDemo {
    static final class RoutingPolicy extends ProxySelector {
        private final Proxy httpProxy;
        private final AtomicInteger failures = new AtomicInteger();

        RoutingPolicy(InetSocketAddress proxyAddress) {
            this.httpProxy = new Proxy(Proxy.Type.HTTP, proxyAddress);
        }

        @Override
        public List<Proxy> select(URI uri) {
            Objects.requireNonNull(uri, "uri");
            String scheme = uri.getScheme();
            String host = uri.getHost();
            if (scheme == null || host == null) {
                throw new IllegalArgumentException("Absolute URI with host required");
            }
            if (!"http".equalsIgnoreCase(scheme) && !"https".equalsIgnoreCase(scheme)) {
                return List.of(Proxy.NO_PROXY);
            }
            String normalizedHost = host.toLowerCase(Locale.ROOT);
            if ("127.0.0.1".equals(normalizedHost) || "localhost".equals(normalizedHost)) {
                return List.of(Proxy.NO_PROXY);
            }
            if ("service.example.invalid".equals(normalizedHost)) {
                return List.of(httpProxy);
            }
            return List.of(Proxy.NO_PROXY);
        }

        @Override
        public void connectFailed(URI uri, SocketAddress address, IOException error) {
            Objects.requireNonNull(uri, "uri");
            Objects.requireNonNull(address, "address");
            Objects.requireNonNull(error, "error");
            failures.incrementAndGet();
        }
    }

    static void reply(HttpExchange exchange, String text) throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(200, data.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(data);
        }
    }

    static HttpRequest request(URI uri) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer origin = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        HttpServer proxy = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        origin.createContext("/", exchange -> reply(exchange, "via-origin"));
        proxy.createContext("/", exchange -> reply(exchange, "via-proxy"));
        origin.start();
        proxy.start();
        try {
            RoutingPolicy policy = new RoutingPolicy(
                    new InetSocketAddress(loopback, proxy.getAddress().getPort()));
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .proxy(policy)
                    .build();

            URI remote = URI.create("http://service.example.invalid/report");
            URI local = URI.create(
                    "http://127.0.0.1:" + origin.getAddress().getPort() + "/direct");
            URI secureRemote = URI.create("https://service.example.invalid/secure");

            System.out.println("remote-is-http-proxy=" +
                    (policy.select(remote).get(0).type() == Proxy.Type.HTTP));
            System.out.println("https-is-http-proxy=" +
                    (policy.select(secureRemote).get(0).type() == Proxy.Type.HTTP));
            System.out.println("local-is-direct=" +
                    (policy.select(local).get(0) == Proxy.NO_PROXY));
            System.out.println("client-explicit-selector=" + client.proxy().isPresent());

            HttpResponse<String> proxied = client.send(request(remote),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            System.out.println("proxied-status=" + proxied.statusCode());
            System.out.println("proxied-body=" + proxied.body());

            HttpResponse<String> direct = client.send(request(local),
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            System.out.println("direct-status=" + direct.statusCode());
            System.out.println("direct-body=" + direct.body());

            System.out.println("factory-null-direct=" +
                    (ProxySelector.of(null).select(remote).get(0) == Proxy.NO_PROXY));
            System.out.println("builder-no-proxy=" +
                    (HttpClient.Builder.NO_PROXY.select(remote).get(0) == Proxy.NO_PROXY));
            System.out.println("connection-failures=" + policy.failures.get());
        } finally {
            origin.stop(0);
            proxy.stop(0);
        }
    }
}
```

Biên dịch bằng **JDK 11 trở lên**; `--release 11` xác minh ví dụ không sử dụng API sau Java 11:

```bash
javac -encoding UTF-8 --release 11 --add-modules jdk.httpserver ProxySelectorDemo.java
java --add-modules jdk.httpserver ProxySelectorDemo
```

**Stdout đã kiểm chứng:**

```text
remote-is-http-proxy=true
https-is-http-proxy=true
local-is-direct=true
client-explicit-selector=true
proxied-status=200
proxied-body=via-proxy
direct-status=200
direct-body=via-origin
factory-null-direct=true
builder-no-proxy=true
connection-failures=0
```

Giải thích các kết quả:

1. `remote-is-http-proxy=true`: policy chọn HTTP proxy cho URI `http://service.example.invalid/report`.
2. `https-is-http-proxy=true`: chính sách **cũng chọn HTTP proxy** cho URI HTTPS. Đây chỉ kiểm tra danh sách lựa chọn, **không** gửi HTTPS hay xác minh CONNECT/tunnel.
3. `local-is-direct=true`: URI loopback sử dụng `Proxy.NO_PROXY`, nên yêu cầu không đi qua proxy giả lập.
4. `client-explicit-selector=true`: client được tạo bằng `.proxy(policy)`, vì thế `HttpClient.proxy()` có `Optional` chứa selector đã cung cấp.
5. `proxied-status=200` và `proxied-body=via-proxy`: client đã kết nối tới proxy giả lập ở loopback cho URI mẫu; proxy giả lập trả kết quả mà **không forward**.
6. `direct-status=200` và `direct-body=via-origin`: cùng client đã gọi trực tiếp tới HTTP server origin ở loopback.
7. `factory-null-direct=true` và `builder-no-proxy=true` xác minh hai cách tạo selector direct.
8. `connection-failures=0`: cả hai kết nối trong ví dụ thành công nên không có lỗi thiết lập proxy được ghi nhận. **Không** coi số 0 này là bảo đảm rằng mọi callback `connectFailed` đều luôn được gọi với mọi loại lỗi; đây chỉ là fixture thành công.
9. `finally` dừng cả hai server, tránh để lại dịch vụ nền. Port được hệ điều hành tự chọn thay vì hard-code.

Một môi trường sandbox có chính sách cấm loopback socket có thể từ chối chạy server. Khi đó vẫn có thể unit-test riêng `RoutingPolicy.select(URI)` không cần networking, sau đó integration-test HTTP khi môi trường cho phép.

## 7. Cấu hình hệ thống và phạm vi của selector

`ProxySelector.getDefault()` phản ánh selector JVM mặc định; cấu hình proxy của JDK có thể lấy từ một số system properties về mạng. Khi triển khai cần tham khảo tài liệu `java.net` tương ứng với phiên bản JDK:

- `http.proxyHost` / `http.proxyPort` cho HTTP khi chính sách hệ thống tương ứng được dùng.
- `https.proxyHost` / `https.proxyPort` cho HTTPS khi thích hợp.
- `http.nonProxyHosts` được tài liệu hóa như danh sách host bypass theo quy tắc property; đừng suy đoán tên property tương tự cho mọi scheme.
- `java.net.useSystemProxies` có ý nghĩa theo chính sách đọc proxy hệ thống lúc khởi tạo của JDK; không phải một biến tự động được mọi thư viện HTTP xử lý giống nhau.

Đây là **cấu hình phụ thuộc môi trường**, không có bảo đảm rằng OS, JVM, container, CI và ứng dụng đều dùng một selector đồng nhất. Nếu cung cấp **custom selector** qua `Builder.proxy(custom)`, không nên mặc nhiên kỳ vọng custom selector tự áp dụng các property bypass của selector mặc định: chính bạn phải triển khai policy hoặc ủy quyền cho selector mặc định khi cần.

**Thời điểm áp dụng:** HttpClient được xây dựng với cấu hình per-client và thường tái sử dụng kết nối. Không nên thay proxy hệ thống sau khi đã build client rồi mong mọi kết nối đang có lập tức đổi tuyến. Nếu thay chính sách egress hoặc thông tin proxy, cần kế hoạch tạo client mới hoặc làm mới tài nguyên phù hợp với yêu cầu runtime.

**`HttpClient.proxy()` là công cụ quan sát cấu hình tường minh, không phải phép đo đường đi thực tế.** Muốn xác thực traffic có đi qua proxy không, test qua proxy có quan sát được ở môi trường kiểm soát hoặc dùng log/metric mạng đã được cấp quyền.

## 8. Proxy authentication và HTTPS CONNECT

### 8.1. Proxy có yêu cầu xác thực

Proxy doanh nghiệp có thể trả `407 Proxy Authentication Required`. Đây là **status HTTP ở proxy**, khác với HTTP `401 Unauthorized` từ tài nguyên đích. Có thể cấu hình `Authenticator` cho client:

```java
// Đoạn minh họa khái niệm, cần Authenticator do ứng dụng triển khai.
// Authenticator phải cung cấp credential phù hợp yêu cầu proxy.
HttpClient client = HttpClient.newBuilder()
        .proxy(ProxySelector.of(proxyAddress))
        .authenticator(proxyAuthenticator)
        .build();
```

Trong đó `proxyAddress` và `proxyAuthenticator` phải được khởi tạo bởi môi trường ứng dụng; không dùng `"username:password"` trong URL đích hay in credential ra log. Các cơ chế proxy authentication và hạn chế cho HTTPS tunnel phụ thuộc JDK/triển khai; ví dụ proxy Basic authentication có thể bị chính sách bảo mật của JDK hạn chế với CONNECT. Hãy kiểm tra proxy server, TLS và cấu hình xác thực một cách minh bạch, thay vì tắt cơ chế bảo vệ chỉ để qua bài test.

`Authenticator` có thể phân biệt requestor là proxy hay server bằng loại yêu cầu xác thực. Không gửi credential nội bộ đến host lạ hoặc một proxy không được cấp phép. Dùng bí mật từ cấu hình bảo mật/chương trình quản lý secrets; không hard-code mật khẩu.

### 8.2. HTTPS proxy/tunnel

Đối với HTTPS qua **HTTP proxy**, client thường tạo đường hầm `CONNECT` và sau đó bắt tay TLS với **đích HTTPS**, không tự chuyển dữ liệu HTTPS thành plaintext cho proxy chỉ vì proxy được chọn. Một proxy doanh nghiệp có khả năng TLS inspection là một cấu hình bảo mật riêng; client cần trust store và quy định chứng chỉ phù hợp.

Lưu ý:

- `ProxySelector.select(httpsUri)` trả `Proxy.Type.HTTP` chỉ thể hiện **chính sách chọn proxy**, chưa chứng minh TLS thành công.
- Proxy hoặc mạng có thể chặn `CONNECT`, yêu cầu xác thực hoặc giới hạn cổng.
- HTTP/2 có thể chịu ràng buộc từ proxy và client có thể dùng HTTP/1.1 tùy môi trường/triển khai. Đừng suy ra protocol thực tế chỉ từ `client.version()` hoặc ý muốn trên builder.
- Không tắt kiểm tra chứng chỉ hostname hay tin cậy certificate tùy tiện để “sửa lỗi proxy”. Phải xác định cấu hình TLS/tunnel đúng theo chính sách tổ chức.

## 9. Lỗi thường gặp khi kết nối qua proxy

| Triệu chứng | Nhóm nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| `ConnectException`/`IOException` khi liên lạc proxy | Proxy sai host/port, không thể mở TCP, firewall/network. | Kiểm tra proxy address, DNS, quyền mạng, logs có kiểm soát và timeout. |
| HTTP `407` | Proxy yêu cầu xác thực, credential sai hoặc phương thức auth bị hạn chế. | Kiểm tra `Authenticator` và policy của proxy/JDK, không nhầm với `401` từ origin. |
| HTTP `502`/`504` qua proxy | Proxy/gateway không tới được đích hoặc upstream timeout. | Phân biệt kết nối tới proxy với kết nối proxy tới origin. |
| Host nội bộ đáng lẽ direct nhưng lại qua proxy | Selector không có bypass rule, custom selector bỏ qua default nonProxyHosts, hostname normalization sai. | Unit-test `select(uri)` cho local/internal targets. |
| Host bắt buộc qua proxy nhưng đi direct | Selector trả `NO_PROXY` trong nhánh không phù hợp, fallback không an toàn hoặc client khác cấu hình. | Kiểm tra policy fail-closed, môi trường thực và client instance. |
| `client.proxy().isEmpty()` nhưng request vẫn qua proxy | Client không có selector tường minh nhưng dùng selector mặc định. | Xem `ProxySelector.getDefault()` và thực tế runtime; không lấy Optional.empty làm “direct”. |
| HTTPS proxy đã được chọn nhưng TLS thất bại | CONNECT, certificate/trust store, hostname validation, auth hoặc protocol limitation. | Phân biệt bước chọn, kết nối proxy, tunnel và TLS. |
| Thay `ProxySelector.setDefault` mà request không đổi đường | Client/connection đã được tạo trước, cấu hình per-client hoặc connection reuse. | Xác định vòng đời client và tạo mới theo chính sách nếu cần. |
| Test đi đến proxy thật ngoài ý muốn | Test kế thừa default selector của máy/CI. | Dùng selector tường minh (`NO_PROXY` hoặc local fixture) trong test. |

Không xử lý mọi loại lỗi bằng một nhánh `catch (IOException e) { useDirectConnection(); }`. Với đích bắt buộc đi qua proxy vì kiểm soát an toàn, **fallback direct có thể vi phạm chính sách egress hoặc làm lộ dữ liệu**. Khi proxy là yêu cầu bắt buộc, từ chối kết nối và báo lỗi cụ thể thường đúng hơn.

## 10. Thiết kế chính sách lựa chọn proxy an toàn

Một custom selector tốt cần phản ánh quy tắc mạng, không chỉ là ví dụ `if (host.startsWith(...))`:

1. **Phân nhóm đích:** danh sách domain/host/cổng được duyệt cho đi direct, danh sách bắt buộc proxy và các đích không được phép.
2. **So sánh host chính xác:** chuẩn hóa hostname theo quy tắc ứng dụng. Nếu cần hỗ trợ subdomain, dùng so sánh `host.equals("example.com") || host.endsWith(".example.com")` chứ không dùng `host.contains("example.com")`.
3. **Chú ý DNS và địa chỉ nội bộ:** hostname có thể phân giải sang private IP, loopback hoặc địa chỉ khác sau khi selector đã quyết định. Nếu chính sách là chống SSRF/khống chế egress, riêng việc kiểm tra chuỗi hostname **chưa đủ**; còn cần kiểm soát DNS, mạng và các redirect.
4. **Fail closed nếu proxy là bắt buộc:** lỗi proxy không tự chuyển thành `NO_PROXY` trừ khi chính sách cho phép một con đường khác.
5. **Không bịa/probe credential:** xác thực proxy độc lập với lựa chọn proxy; secret cần được quản lý tập trung và giới hạn phạm vi.
6. **Tính đến redirect:** URI sau redirect có thể khác host/scheme. Đừng mặc định một policy cho request ban đầu đủ bảo vệ mọi destination mới.
7. **Thread-safe:** selector có thể được sử dụng khi nhiều HTTP request thực hiện đồng thời. Dùng trạng thái bất biến, atomic hoặc đồng bộ thích hợp.
8. **Quan sát có kiểm soát:** metric cho tuyến được chọn, thất bại kết nối, 407, latency, nhưng không log token, cookie, credential hay toàn bộ URI có query chứa dữ liệu nhạy cảm.
9. **Kiểm thử định kỳ:** khi nâng cấp JDK hoặc đổi proxy môi trường, chạy lại unit/integration tests cho các nhóm URI, HTTPS và nhánh lỗi.

## 11. Chiến lược kiểm thử `ProxySelector`

Chia kiểm thử làm hai lớp để không phụ thuộc Internet:

### 11.1. Unit test selector (không network)

Kiểm tra trực tiếp `select(URI)`:

| URI đầu vào | Chính sách ví dụ | Kết quả cần khẳng định |
| --- | --- | --- |
| `http://service.example.invalid/report` | Host được gắn proxy HTTP. | Phần tử đầu tiên có `type() == Proxy.Type.HTTP` và address đúng. |
| `https://service.example.invalid/secure` | Cùng host qua HTTPS. | Cũng chọn HTTP proxy **ở mức policy**, chưa kiểm chứng CONNECT. |
| `http://127.0.0.1:8080/health` | Loopback bypass. | `Proxy.NO_PROXY`. |
| `http://localhost:8080/health` | Host loopback bypass. | `Proxy.NO_PROXY`. |
| `http://other.example.invalid/resource` | Theo chính sách demo trả direct. | `Proxy.NO_PROXY`; production có thể cần fail closed. |

Test thêm URI không có hostname hợp lệ, scheme không được hỗ trợ, chữ hoa/thường, domain tương tự gây nhầm, cổng không mặc định, proxy address sai và policy bypass. Đừng phụ thuộc `ProxySelector.getDefault()` trong unit test vì trạng thái JVM/CI khác nhau.

### 11.2. Integration test có proxy giả lập

Chạy một fake proxy trên loopback để nhận request HTTP và trả chuỗi xác định; origin server khác trả chuỗi khác. Dùng client có `.proxy(customSelector)` và gửi hai yêu cầu:

- `remote` được proxy giả lập trả `via-proxy`.
- `local` được origin trả `via-origin`.

Đây là cách kiểm chứng **client sử dụng tuyến** mà selector đã chọn, chứ không chỉ kiểm tra kết quả của `select(URI)`. Nhưng fake proxy trong mục 6 **không** thử forward, 407 auth hay CONNECT HTTPS, do đó không dùng kết quả này để khẳng định một proxy production hỗ trợ HTTPS hoặc xác thực.

Kiểm thử các trường hợp thất bại riêng: proxy không mở cổng, timeout, proxy trả 407, route yêu cầu direct, route bắt buộc proxy, và server đích trả HTTP lỗi. Những case có thể cần thêm fixture riêng; đừng gộp “connect failed” với HTTP status error.

## 12. Những hiểu lầm phổ biến

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Không gọi `Builder.proxy` là chắc chắn đi direct.” | Client có thể dùng **default ProxySelector**. |
| “`client.proxy() == Optional.empty()` nghĩa là tắt proxy.” | Chỉ nghĩa là không có selector tường minh; default selector vẫn có thể được dùng. |
| “`ProxySelector.of` chỉ dùng cho HTTP mà không dùng HTTPS.” | Factory được tài liệu hóa cho **HTTP và HTTPS** với một HTTP proxy. |
| “`ProxySelector.of(null)` ném lỗi vì null.” | API này dùng `null` để **tắt proxy** theo hợp đồng factory. |
| “`Proxy.NO_PROXY` là một proxy server không cần xác thực.” | Đây là chỉ thị **kết nối trực tiếp**, không có máy chủ proxy. |
| “`select(URI)` nhận URL của proxy.” | Nó nhận URI **đích được truy cập**, rồi trả tuyến thích hợp. |
| “Callback `connectFailed` được gọi cho mọi HTTP 4xx/5xx.” | Đây là thông báo lỗi **kết nối proxy**, không phải handler status. |
| “Trả `List.of()` là cách biểu diễn direct.” | Trả danh sách chứa `Proxy.NO_PROXY`. |
| “HTTP proxy được chọn tức HTTPS chắc chắn thành công.” | CONNECT, TLS/certificate và auth còn phải hoạt động. |
| “SOCKS selector chắc chắn hoạt động với mọi HttpClient.” | Không nên giả định hỗ trợ SOCKS nếu chưa kiểm chứng JDK và implementation. |
| “Custom selector tự áp dụng `http.nonProxyHosts`.” | Chỉ khi bạn lập trình/ủy quyền điều đó; selector của bạn chịu trách nhiệm policy. |
| “Proxy lỗi thì cứ gửi direct để đảm bảo dịch vụ luôn hoạt động.” | Có thể vi phạm yêu cầu bảo mật; fail closed khi proxy bắt buộc. |
| “Đổi `setDefault` là toàn bộ client đang chạy đổi proxy ngay.” | Có vòng đời client, cấu hình đã build và các kết nối có thể tái sử dụng. |
| “Chọn host với `contains("example.com")` là đủ an toàn.” | Dễ match sai domain; cần policy chính xác và kiểm soát DNS/network bổ sung. |

## 13. Checklist triển khai Java 11+

1. **Chọn chiến lược:** dùng default selector nếu tin môi trường; dùng `ProxySelector.of(proxyAddress)` khi một HTTP proxy cố định; dùng custom selector khi cần định tuyến theo URI.
2. **Nếu muốn direct chắc chắn:** cấu hình `.proxy(HttpClient.Builder.NO_PROXY)`; không suy ra từ `client.proxy().isEmpty()`.
3. **Sử dụng đúng địa chỉ proxy:** `InetSocketAddress(host, port)`; không trộn host đích với host proxy, không chèn credential vào URI.
4. **Triển khai custom selector đúng hợp đồng:** `select(URI)` trả danh sách proxy không rỗng theo priority; direct dùng `Proxy.NO_PROXY`; triển khai `connectFailed(...)` để ghi nhận lỗi kết nối nếu cần.
5. **Kiểm soát route:** xác định hostname/scheme/port, bypass host nội bộ chính xác, chính sách cho các đích lạ và trường hợp proxy bắt buộc.
6. **Xử lý HTTPS độc lập:** selection không đảm bảo CONNECT/TLS/auth; test end-to-end ở môi trường kiểm soát.
7. **Bảo vệ thông tin xác thực:** quản lý `Authenticator` và secrets riêng, không log password, token hoặc query nhạy cảm.
8. **Phân biệt lỗi:** I/O tới proxy, 407 từ proxy, 401 từ origin, 5xx, timeout và TLS lỗi có hướng xử lý khác nhau.
9. **Không tự động fallback direct trái policy:** proxy bắt buộc phải fail closed nếu không có tuyến được duyệt.
10. **Tận dụng client theo vòng đời:** `HttpClient` cấu hình một lần, dùng lại giữa nhiều request; khi đổi chính sách proxy cần quản lý lifecycle rõ.
11. **Test cả policy và traffic:** unit test `select(URI)`, integration test bằng proxy/origin loopback, test auth/TLS riêng.
12. **Chỉ lấy kiến thức vẫn áp dụng:** Java 11 chuẩn `HttpClient`, `ProxySelector`, `ProxySelector.of`, `HttpClient.Builder.NO_PROXY` và các API chính thức vẫn được hỗ trợ trong JDK hiện đại.

### Tài liệu chính thức

- [Oracle Java SE 11 — `HttpClient.Builder.proxy(ProxySelector)` và `NO_PROXY`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Oracle Java SE 11 — `HttpClient.proxy()` và client proxy mặc định](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 11 — `ProxySelector`, `of`, `getDefault`, `select` và `connectFailed`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/ProxySelector.html)
- [Oracle Java SE 11 — `Proxy`, `Proxy.Type` và `Proxy.NO_PROXY`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/Proxy.html)
- [Oracle Java SE 25 — `HttpClient.Builder`: API proxy vẫn tồn tại](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Oracle Java SE 25 — `ProxySelector`: hợp đồng hiện hành](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/ProxySelector.html)
- [Oracle Java SE 11 — Java networking system properties](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/net/doc-files/net-properties.html)
