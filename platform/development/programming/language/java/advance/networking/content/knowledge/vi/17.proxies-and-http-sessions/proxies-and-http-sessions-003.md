# Thuộc tính proxy toàn hệ thống và cấu hình riêng từng HttpClient

*Java Advance – networking | Chủ đề cha: Proxy và phiên HTTP | API Java 17+*

## 1. Vì sao cần phân biệt cấu hình proxy toàn JVM và riêng từng HttpClient?

Một HTTP request trong Java có thể được gửi **trực tiếp tới origin** hoặc **đi qua proxy**:

~~~text
DIRECT:
  Java HttpClient -----------------------> HTTP origin server

HTTP via proxy:
  Java HttpClient ----> HTTP proxy ------> HTTP origin server

HTTPS via HTTP proxy:
  Java HttpClient ----> HTTP proxy
                          |
                       CONNECT host:443
                          |
                       TLS tunnel ------> HTTPS origin server
~~~

Proxy có thể phục vụ outbound access control, firewall egress, caching, audit hoặc routing. Nhưng một service có thể vừa gọi một API Internet **qua proxy doanh nghiệp**, vừa gọi một API **trong mạng nội bộ trực tiếp**. Nếu dùng một cấu hình global cho mọi yêu cầu, dễ gặp lỗi mạng, gửi dữ liệu sai tuyến hoặc tạo race giữa các thread.

Java 17 hỗ trợ hai cách cấu hình chính:

- **Mặc định ở cấp JVM:** `System Properties` như `http.proxyHost`, `https.proxyHost`, `http.nonProxyHosts`, `java.net.useSystemProxies`; default `ProxySelector.getDefault()` quyết định proxy cho từng URI.
- **Riêng từng instance `HttpClient`:** `HttpClient.newBuilder().proxy(ProxySelector)` có thể gắn fixed proxy, custom routing hoặc `HttpClient.Builder.NO_PROXY` để bỏ qua proxy.

**Điểm quan trọng nhất:** đặt `-Dhttp.proxyHost=...` **không buộc mọi HttpClient** cùng đi qua proxy đó. Khi client có `ProxySelector` riêng, nó có thể chọn đường khác. Ngược lại, client không cấu hình `proxy(...)` thường sử dụng **default proxy selector của JVM**.

~~~text
JVM-wide default:
  -Dhttp.proxyHost=proxy-global.example
  -Dhttp.nonProxyHosts=localhost|127.*
                  |
                  v
        ProxySelector.getDefault()
                  |
            HttpClient A
         (không set proxy)

HttpClient B: builder.proxy(ProxySelector.of(proxy-special))
    -> proxy-special, selector riêng cho B

HttpClient C: builder.proxy(HttpClient.Builder.NO_PROXY)
    -> kết nối trực tiếp, bất kể default proxy
~~~

Không thay `System.setProperty(...)` trước từng request để bật/tắt proxy. Đây là **global state của tiến trình Java**, không phải option của một `HttpRequest`, nên các client/thư viện khác có thể bị tác động.

## 2. Bảng Java 17 System Properties liên quan proxy

Theo tài liệu *Networking Properties* của Oracle Java 17:

| Thuộc tính | Giá trị mặc định | Dùng để làm gì? |
|---|---|---|
| `http.proxyHost` | Không có | Chọn host HTTP proxy cho request `http://` |
| `http.proxyPort` | `80` | Cổng HTTP proxy |
| `https.proxyHost` | Không có | Chọn HTTP proxy cho request `https://` |
| `https.proxyPort` | `443` | Cổng proxy khi request HTTPS; nên ghi cổng thực tế |
| `http.nonProxyHosts` | `localhost\|127.*\|[::1]` | Pattern hostname được truy cập **direct** |
| `java.net.useSystemProxies` | `false` | Cho phép sử dụng proxy settings của OS trên nền tảng hỗ trợ |
| `socksProxyHost` | Không có | SOCKS proxy cho các networking APIs có hỗ trợ |
| `socksProxyPort` | `1080` | Cổng SOCKS mặc định |
| `socksProxyVersion` | `5` | SOCKS 4/5 theo khả năng triển khai |

Ba điểm cần nhớ:

1. **`http.nonProxyHosts` được dùng cho cả HTTP và HTTPS** trong default proxy selection của Java 17. Không có quy tắc chuẩn Java 17 rằng phải đặt `https.nonProxyHosts`.
2. **`https.proxyPort` mặc định 443** trong tài liệu, nhưng cổng thực tế của HTTP proxy doanh nghiệp có thể là 3128 hoặc 8080. Đây **không phải** cổng HTTPS origin bắt buộc phải giống cổng proxy.
3. `socksProxyHost` thuộc Java networking rộng hơn; không mặc định mọi implementation `java.net.http.HttpClient` xử lý SOCKS như một HTTP forward proxy. Hãy kiểm tra phiên bản JDK, loại proxy và API cụ thể.

### 2.1. Bypass host với http.nonProxyHosts

Ví dụ giá trị:

~~~text
localhost|127.*|[::1]|*.corp.example
~~~

`|` là ký tự **ngăn cách nhiều pattern**, và `*` là wildcard trong pattern. Nó không phải dấu phẩy, không phải regex đầy đủ và không phải cú pháp CIDR như `10.0.0.0/8`.

Khi ứng dụng đặt `http.nonProxyHosts` tường minh, cần liệt kê cả các mục localhost/loopback mà vẫn muốn bypass; đừng giả định mọi mục mặc định luôn được tự ghép thêm. Đặc biệt, Java 17 mặc định loại nhiều dạng loopback khỏi proxy; đây là lý do request tới `127.0.0.1` có thể direct dù `http.proxyHost` đang được cấu hình.

**Không dùng pattern bypass này làm bộ lọc SSRF.** DNS có thể phân giải hostname thành IP nội bộ, tên DNS có thể thay đổi, và một pattern hostname không đủ để chặn request do bên không tin cậy điều khiển. Security policy cần thêm network egress restrictions và kiểm tra destination phù hợp.

### 2.2. java.net.useSystemProxies được đọc lúc startup

`java.net.useSystemProxies=true` cho default proxy selector thử dùng cấu hình proxy từ OS trên nền tảng được Oracle mô tả, như Windows/macOS/GNOME. Theo tài liệu Java 17, property này **chỉ được kiểm tra một lần khi JVM khởi động**.

~~~bash
java -Djava.net.useSystemProxies=true -version
~~~

Lệnh trên chỉ kiểm tra Java runtime; với ứng dụng thực tế, truyền `-Djava.net.useSystemProxies=true` **khi chạy ứng dụng**, trước main class/`-jar`. Không trông chờ `System.setProperty("java.net.useSystemProxies", "true")` giữa chương trình sẽ làm Java tải lại OS proxy config.

Các Java property proxy cụ thể như `http.proxyHost` có **ưu tiên hơn OS proxy settings** khi cùng được cấu hình. Việc hệ điều hành dùng PAC, browser preference hoặc VPN không bảo đảm Java áp dụng y hệt trình duyệt.

### 2.3. System properties không phải environment variables

| Nguồn | Ví dụ | Có tự áp lên Java HttpClient? |
|---|---|---|
| JVM `-D` | `-Dhttp.proxyHost=proxy.corp.example` | Default proxy selector có thể sử dụng |
| Java runtime | `System.setProperty("http.proxyHost", "...")` | Global trong JVM, dễ ảnh hưởng nhiều client |
| Cài đặt OS | Proxy settings trong Windows/macOS | Tùy nền tảng, bật `java.net.useSystemProxies` từ startup |
| Shell environment | `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` | **Không có bảo đảm** Java 17 HttpClient mặc định tự đọc như curl |
| Builder riêng | `.proxy(ProxySelector.of(...))` | Áp cho **instance HttpClient ấy** |

Một framework hoặc thư viện có thể tự đọc environment variables rồi xây client riêng. Vì vậy cần đọc tài liệu của framework nếu có, không suy từ việc `curl` tôn trọng `HTTPS_PROXY` sang mọi Java client.

## 3. Cách truyền -D khi chạy JVM

Nếu proxy doanh nghiệp là `proxy.corp.example:3128`:

~~~bash
java \
  -Dhttp.proxyHost=proxy.corp.example \
  -Dhttp.proxyPort=3128 \
  -Dhttps.proxyHost=proxy.corp.example \
  -Dhttps.proxyPort=3128 \
  '-Dhttp.nonProxyHosts=localhost|127.*|[::1]|*.corp.example' \
  -version
~~~

Lệnh dùng `-version` để có thể thử mà **không cần artifact Java**. Khi chạy ứng dụng thật, thay `-version` bằng tham số khởi động thực tế. Các `-D` phải đến **trước** `-jar` hoặc tên main class. Cần quote `http.nonProxyHosts`: dấu `|` trong shell có thể bị hiểu là pipeline.

Trên Windows PowerShell, có thể dùng một dòng để tránh nhầm cú pháp tiếp dòng:

~~~powershell
java '-Dhttp.proxyHost=proxy.corp.example' '-Dhttp.proxyPort=3128' '-Dhttps.proxyHost=proxy.corp.example' '-Dhttps.proxyPort=3128' '-Dhttp.nonProxyHosts=localhost|127.*|[::1]|*.corp.example' -version
~~~

Nếu chạy trong IDE, application server, container hoặc build tool, hãy chắc chắn **VM options đến đúng JVM ứng dụng**, không chỉ JVM của công cụ build. Đặt proxy cho process Maven/Gradle không mặc định làm mọi process con/ứng dụng forked nhận được cùng settings.

### 3.1. Có nên gọi System.setProperty khi đang phục vụ request?

Java có thể đọc một số proxy properties trong quá trình sử dụng; tuy nhiên `System.setProperty` thay đổi **toàn JVM**, không có isolation theo client. Một default selector đang dùng property có thể quan sát giá trị mới; client khác hoặc thư viện khác có thể có cache/cấu hình được chụp tại thời điểm build.

Giải pháp cho multi-tenant/đa API là **cấu hình riêng từng HttpClient**, tạo client mới khi muốn đổi route. Đừng thực hiện:

~~~java
// Phản ví dụ: thay global state trước từng request.
System.setProperty("http.proxyHost", "proxy-A");
clientA.send(requestA, HttpResponse.BodyHandlers.discarding());
System.setProperty("http.proxyHost", "proxy-B");
clientB.send(requestB, HttpResponse.BodyHandlers.discarding());
~~~

Code này không an toàn khi có concurrency: request từ thread khác có thể bị route theo proxy vừa được thay. Ngoài ra việc default selector đã được client lưu và connection reuse khiến kết quả không đơn giản là “property ngay trước `send` quyết định toàn bộ”.

## 4. ProxySelector.getDefault() làm gì?

`java.net.ProxySelector` trả về các phương án connection cho một URI:

~~~java
// Trích đoạn, cần import ProxySelector, Proxy, List, URI.
ProxySelector selector = ProxySelector.getDefault();
List<Proxy> selected = selector.select(
        URI.create("https://service.example.test/resource"));

for (Proxy candidate : selected) {
    System.out.println(candidate.type());
}
~~~

Các API chính:

| API | Ý nghĩa |
|---|---|
| `ProxySelector.getDefault()` | Lấy default selector của JVM |
| `ProxySelector.setDefault(selector)` | Thay selector mặc định **toàn JVM** |
| `select(URI)` | Chọn danh sách proxy candidates/direct cho URI |
| `connectFailed(URI, SocketAddress, IOException)` | Callback khi caller báo không kết nối được proxy |
| `ProxySelector.of(InetSocketAddress)` | Proxy cố định cho HTTP/HTTPS |
| `Proxy.NO_PROXY` | Đại diện lựa chọn direct |
| `Proxy.Type.HTTP` | HTTP proxy |
| `Proxy.Type.SOCKS` | SOCKS proxy |
| `Proxy.Type.DIRECT` | Kết nối không qua proxy |

`ProxySelector.select` nói **selector muốn chọn đường nào**, không chứng minh kết nối thành công: DNS, firewall, TCP, proxy authentication, TLS đều có thể lỗi sau đó.

**Không lạm dụng `ProxySelector.setDefault` trong service có nhiều client**. Java 17 `HttpClient` lấy các system-wide defaults **lúc tạo instance**; thay default selector sau khi client đã build không làm client cũ tự đổi selector theo Javadoc. Điều đó không có nghĩa mọi giá trị property được snapshot mãi trong mọi implementation, nhưng đủ để cho thấy đổi global selector giữa requests là thiết kế không đáng tin cậy.

## 5. Không chỉ định builder.proxy: default selector vẫn có thể được dùng

~~~java
HttpClient a = HttpClient.newHttpClient();
HttpClient b = HttpClient.newBuilder().build();
~~~

Khi builder không gọi `proxy(...)`, các client mới dùng **default ProxySelector** của JVM theo Java 17 Javadoc. Default selector hiểu những `http.proxyHost`, `https.proxyHost`, `http.nonProxyHosts`... phù hợp.

Một cạm bẫy rất hay gặp:

~~~java
HttpClient client = HttpClient.newHttpClient();
boolean configuredExplicitly = client.proxy().isPresent();
~~~

`HttpClient.proxy()` trả `Optional` chứa **ProxySelector được cấp tường minh cho builder**. Nếu builder không được cấp selector, Optional có thể **empty**, **nhưng client vẫn có default proxy selector ẩn đang được dùng**. Vì vậy:

~~~text
client.proxy().isEmpty() != "client chắc chắn đi DIRECT"
~~~

Muốn biết tuyến thật, phải xác định đúng selector của client, URI đang dùng, policy bypass và kết quả kết nối. Không dùng Optional này làm cờ xác nhận không qua proxy.

## 6. Gắn proxy riêng cho mỗi HttpClient

### 6.1. Cố định một HTTP proxy

~~~java
// Trích đoạn; import HttpClient, ProxySelector, InetSocketAddress.
HttpClient throughProxy = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.corp.example", 3128)))
        .build();
~~~

`ProxySelector.of(address)` theo Java 17 Javadoc trả selector dùng địa chỉ đó cho HTTP và HTTPS requests. **Đây không phải default selector**: đừng mặc định nó sẽ áp dụng `http.nonProxyHosts`. Nếu cần bypass localhost/nội bộ riêng cho client, hãy viết custom selector.

### 6.2. Buộc đi thẳng bằng NO_PROXY

~~~java
HttpClient direct = HttpClient.newBuilder()
        .proxy(HttpClient.Builder.NO_PROXY)
        .build();
~~~

`HttpClient.Builder.NO_PROXY` là constant Java 17 để chọn `Proxy.NO_PROXY`, tức kết nối trực tiếp. Nó **không** xóa `http.proxyHost` của JVM và **không** thay đổi client khác. Javadoc `ProxySelector.of(null)` cũng có thể tạo selector vô hiệu proxy, nhưng `NO_PROXY` rõ ý hơn trong builder.

### 6.3. Client có vòng đời cấu hình riêng

`HttpClient` sau `build()` là object cấu hình bất biến, có thể dùng cho nhiều request và có khả năng chia sẻ network resources/connection pools. Không có `HttpRequest.Builder.proxy(...)` chuẩn trong Java 17 để đổi tuyến theo từng request.

Muốn API A đi proxy 1 và API B đi direct, dùng **hai client**. Muốn nhiều URI trong cùng một client có routing phức tạp, dùng một **custom ProxySelector**. Khi proxy config thay đổi trong runtime, tạo client mới và chuyển traffic một cách thread-safe thay vì đổi global JVM properties.

## 7. Custom ProxySelector cho routing theo URI

Khi cần bypass host nội bộ, có thể viết selector riêng:

~~~java
// Trích đoạn, không phải chương trình độc lập.
ProxySelector policy = new ProxySelector() {
    @Override
    public List<Proxy> select(URI uri) {
        String host = uri.getHost();
        if (host == null) {
            throw new IllegalArgumentException("URI must have a host");
        }
        if ("localhost".equalsIgnoreCase(host)
                || "127.0.0.1".equals(host)) {
            return List.of(Proxy.NO_PROXY);
        }
        return List.of(new Proxy(Proxy.Type.HTTP,
                new InetSocketAddress("proxy.corp.example", 3128)));
    }

    @Override
    public void connectFailed(
            URI uri, SocketAddress address, IOException reason) {
        // Log/metric đã lọc thông tin; có thể cập nhật trạng thái proxy.
    }
};

HttpClient selectiveClient = HttpClient.newBuilder()
        .proxy(policy).build();
~~~

Đoạn trên cần các import `ProxySelector`, `Proxy`, `URI`, `List`, `InetSocketAddress`, `SocketAddress`, `IOException` và `HttpClient`. Nó chỉ bypass hai hostname cụ thể: **không phải giải pháp SSRF đầy đủ** cho private IP ranges, IPv6, hostname alias, DNS rebinding hay encoded hostnames.

`select` và state của custom selector phải **thread-safe** khi `HttpClient` dùng chung giữa nhiều request/thread. `connectFailed` có thể dùng để ghi nhận proxy connection failures, nhưng không mặc định được gọi cho mọi HTTP status 407/502, lỗi TLS hoặc lỗi đọc body.

## 8. Phân biệt HTTP proxy và HTTPS CONNECT

### 8.1. HTTP qua forward proxy

Khi HTTP client gọi một URL `http://origin.example.test/route` qua HTTP proxy, request HTTP/1.1 gửi tới proxy thường có **absolute-form request-target**:

~~~http
GET http://origin.example.test/route HTTP/1.1
Host: origin.example.test
~~~

Proxy có thể nhìn thấy URL, headers và body plaintext HTTP. Nó có thể forward, cache, chặn hoặc yêu cầu xác thực. **HTTP không mã hóa dữ liệu trên đường truyền**, nên phải cân nhắc TLS hoặc network trust boundary trước khi đưa secrets vào request.

### 8.2. HTTPS qua HTTP proxy

Khi gọi URL `https://origin.example.test/route` qua HTTP proxy, client thường yêu cầu tunnel:

~~~http
CONNECT origin.example.test:443 HTTP/1.1
Host: origin.example.test:443
~~~

Nếu proxy cho phép, TLS handshake tới origin diễn ra qua tunnel. Proxy thông thường thấy hostname/cổng CONNECT và metadata kết nối, nhưng không đọc nội dung HTTPS trong tunnel **khi TLS kết thúc tại origin và certificate/hostname được xác minh đúng**.

Không kết luận proxy luôn không đọc được HTTPS: corporate proxy có thể triển khai TLS interception và phát hành certificate qua CA được client tin. Khi đó proxy là một điểm kết thúc TLS trung gian có thể truy cập nội dung theo chính sách. **Không tắt hostname/certificate verification** chỉ để “sửa lỗi qua proxy”.

### 8.3. Proxy port khác cổng origin

`https.proxyPort` mô tả **cổng để kết nối tới proxy** theo Java property. Nó không bắt buộc bằng 443 của origin, và cũng không khẳng định bản thân proxy connection được mã hóa TLS. Với HTTP forward proxy phục vụ HTTPS qua CONNECT, client dùng HTTP để thương lượng tunnel rồi TLS tới origin.

## 9. Proxy authentication và origin authentication

| Status/header | Bên nào sử dụng? |
|---|---|
| `407 Proxy Authentication Required` | HTTP proxy |
| `Proxy-Authenticate` | Proxy gửi challenge |
| `Proxy-Authorization` | Credentials cho proxy |
| `401 Unauthorized` | Origin server |
| `WWW-Authenticate` | Origin gửi challenge |
| `Authorization` | Credentials cho origin server |

**Không copy credentials của origin sang proxy hoặc ngược lại.** HTTP proxy và HTTPS origin có trust scopes khác nhau. `HttpClient.Builder.authenticator(...)` có thể cung cấp `java.net.Authenticator`; handler cần kiểm tra `RequestorType.PROXY` nếu credential chỉ dành cho proxy.

~~~java
// Trích đoạn: credentials lấy từ nơi lưu secret phù hợp, không hardcode.
Authenticator proxyAuthenticator = new Authenticator() {
    @Override
    protected PasswordAuthentication getPasswordAuthentication() {
        if (getRequestorType() != RequestorType.PROXY) {
            return null;
        }
        return new PasswordAuthentication(proxyUsername, proxyPassword);
    }
};

HttpClient proxyClient = HttpClient.newBuilder()
        .proxy(ProxySelector.of(
                new InetSocketAddress("proxy.corp.example", 3128)))
        .authenticator(proxyAuthenticator)
        .build();
~~~

Ở đây `proxyUsername`/`proxyPassword` là dữ liệu do ứng dụng cung cấp từ secret store, và cần kiểm tra proxy host/port cụ thể trước khi cấp. Các import gồm `java.net.Authenticator`, `PasswordAuthentication`, `InetSocketAddress`, `ProxySelector` và `HttpClient`.

Java 17 có chính sách `jdk.http.auth.tunneling.disabledSchemes`: theo Oracle, triển khai chuẩn mặc định **vô hiệu Basic** khi xác thực HTTP proxy tunnel qua CONNECT. `jdk.http.auth.proxying.disabledSchemes` điều khiển schemes khi proxying HTTP. HTTP Basic chỉ là Base64, **không mã hóa** credentials. Khi nhận 407, hãy kiểm tra proxy challenge, JDK policy, auth scope và kênh kết nối; **không vô hiệu chính sách bảo vệ một cách máy móc**.

## 10. Ví dụ Java 17+ chạy hoàn chỉnh: hai HttpClient với hai tuyến khác nhau

Chương trình dưới đây tạo **hai `HttpServer` trên 127.0.0.1**, không cần Internet:

- **Origin server** trả `ORIGIN`.
- **Fake proxy server** trả `PROXY` và ghi nhận HTTP request target là absolute URI. Đây **không phải một proxy chuyển tiếp hoàn chỉnh**, chỉ dùng để chứng minh route.
- `System.setProperty` ở đầu main tạo một default selector có `http.proxyHost` và `http.nonProxyHosts`. URI remote được **chỉ chọn proxy bằng `select`, không gửi request tới host Internet**.
- Một `HttpClient` dùng `ProxySelector.of(...)` trỏ đến fake proxy; dù URL target là loopback, client này đi qua proxy riêng.
- Một `HttpClient` dùng `HttpClient.Builder.NO_PROXY` gọi cùng URL nhưng đi **trực tiếp** tới origin.

Vì demo cần tự chạy trong một file, nó đặt system properties **trước khi tạo client**. Trong service thật, nên truyền `-D` khi JVM startup hoặc dùng per-client selector thay vì đổi global state.

**File: `ProxyConfigurationDemo.java`**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

public class ProxyConfigurationDemo {
    private static void reply(HttpExchange exchange, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.US_ASCII);
        exchange.sendResponseHeaders(200, bytes.length);
        try (var out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static String get(HttpClient client, URI uri) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3)).GET().build();
        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200) {
            throw new IOException("status " + response.statusCode());
        }
        return response.body();
    }

    public static void main(String[] args) throws Exception {
        // Demonstration only: set JVM-wide settings before creating clients.
        System.setProperty("http.proxyHost", "proxy.example.invalid");
        System.setProperty("http.proxyPort", "3128");
        System.setProperty("http.nonProxyHosts", "localhost|127.*|[::1]");
        ProxySelector defaultSelector = ProxySelector.getDefault();
        URI remote = URI.create("http://service.example.test/resource");
        URI bypass = URI.create("http://127.0.0.1/health");
        List<Proxy> systemSelection = defaultSelector.select(remote);
        List<Proxy> loopbackSelection = defaultSelector.select(bypass);
        System.out.println("defaultRemoteIsHttpProxy=" +
                (!systemSelection.isEmpty()
                        && systemSelection.get(0).type() == Proxy.Type.HTTP));
        System.out.println("defaultLoopbackIsDirect=" +
                (!loopbackSelection.isEmpty()
                        && loopbackSelection.get(0).type() == Proxy.Type.DIRECT));

        InetAddress host = InetAddress.getByName("127.0.0.1");
        HttpServer origin = HttpServer.create(new InetSocketAddress(host, 0), 0);
        HttpServer proxy = HttpServer.create(new InetSocketAddress(host, 0), 0);
        AtomicBoolean absoluteTarget = new AtomicBoolean(false);
        origin.createContext("/", ex -> reply(ex, "ORIGIN"));
        proxy.createContext("/", ex -> {
            absoluteTarget.set(ex.getRequestURI().isAbsolute());
            reply(ex, "PROXY");
        });
        origin.start();
        proxy.start();
        try {
            URI target = new URI("http", null, "127.0.0.1",
                    origin.getAddress().getPort(), "/data", null, null);
            ProxySelector fixedProxy = ProxySelector.of(
                    new InetSocketAddress(host, proxy.getAddress().getPort()));
            HttpClient viaProxy = HttpClient.newBuilder()
                    .proxy(fixedProxy)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpClient direct = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            System.out.println("viaProxyBody=" + get(viaProxy, target));
            System.out.println("directBody=" + get(direct, target));
            System.out.println("proxySawAbsoluteURI=" + absoluteTarget.get());
            System.out.println("clientsHaveExplicitSelectors=" +
                    (viaProxy.proxy().isPresent()
                            && direct.proxy().isPresent()));
        } finally {
            proxy.stop(0);
            origin.stop(0);
        }
    }
}
~~~

Biên dịch và chạy với **Java 17+**. `jdk.httpserver` là module JDK dùng cho local test:

~~~bash
javac --release 17 --add-modules jdk.httpserver ProxyConfigurationDemo.java
java --add-modules jdk.httpserver ProxyConfigurationDemo
~~~

**Stdout đã kiểm chứng với `javac --release 17` trên OpenJDK 24:**

~~~text
defaultRemoteIsHttpProxy=true
defaultLoopbackIsDirect=true
viaProxyBody=PROXY
directBody=ORIGIN
proxySawAbsoluteURI=true
clientsHaveExplicitSelectors=true
~~~

Ý nghĩa:

| Dòng stdout | Kết luận |
|---|---|
| `defaultRemoteIsHttpProxy=true` | Default selector chọn HTTP proxy cho URI remote theo system property |
| `defaultLoopbackIsDirect=true` | Default selector bypass 127.0.0.1 theo nonProxyHosts |
| `viaProxyBody=PROXY` | Per-client fixed proxy làm request đi tới fake proxy |
| `directBody=ORIGIN` | Per-client `NO_PROXY` đưa request trực tiếp tới origin |
| `proxySawAbsoluteURI=true` | Fake proxy nhận HTTP absolute-form request target |
| `clientsHaveExplicitSelectors=true` | Hai client test đều có selector cấp tường minh |

**Giới hạn của demo:** hai server đều local; proxy chỉ trả `PROXY`, không forward; không thực hiện HTTPS CONNECT, TLS interception hoặc proxy authentication. Host `proxy.example.invalid` và `service.example.test` **không nhận request mạng nào**; chỉ được dùng làm dữ liệu chọn proxy. Không triển khai fake proxy này lên production.

## 11. Redirect và proxy là hai quyết định tách biệt

Một request tới `https://api.example.test` có thể nhận redirect `302 Location: https://files.example.test/report`. Với custom ProxySelector, URL đầu và URL sau redirect có thể được chọn tuyến khác nhau.

~~~text
https://api.example.test/orders
     |
     +-- ProxySelector chọn proxy A
     |
     +-- HTTP 302 tới https://files.example.test/report
               |
               +-- ProxySelector có thể chọn proxy B hoặc DIRECT
               |
               +-- Authorization/Cookie cần xét lại scope
~~~

- `followRedirects(HttpClient.Redirect.NEVER/NORMAL/ALWAYS)` điều khiển quyết định tự follow redirect.
- `proxy(ProxySelector)` điều khiển tuyến tới từng URI.
- `Authorization`, `Cookie`, `Proxy-Authorization` hoặc `Authenticator` điều khiển thông tin xác thực theo đúng trust boundary.

**Không gửi lại token của API ban đầu sang host khác chỉ vì redirect đã chọn được một proxy hợp lệ.** Proxy policy không tự cung cấp authorization cho origin mới.

## 12. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân thường thấy | Hướng kiểm tra |
|---|---|---|
| Đặt `http.proxyHost` nhưng request vẫn direct | Client có `NO_PROXY`/custom selector hoặc host được bypass | Xem đúng instance HttpClient và selector |
| `client.proxy().isEmpty()` nhưng traffic qua proxy | Default selector được dùng ngầm | Đừng dùng Optional để suy luận route |
| 127.0.0.1 không đi proxy mặc định | Bypass loopback trong `http.nonProxyHosts` | Thường là đúng |
| Đặt `https.nonProxyHosts` nhưng không hiệu lực | HTTPS dùng `http.nonProxyHosts` theo Java 17 | Dùng đúng property/custom selector |
| Bypass host list dùng dấu phẩy | Java dùng dấu `|` | Sửa pattern và shell quoting |
| Bật `useSystemProxies` giữa runtime không hiệu lực | Thuộc tính được đọc lúc startup | Dùng `-Djava.net.useSystemProxies=true` |
| OS có `HTTPS_PROXY` nhưng Java không đi proxy | Env shell không tự là Java system property | Đặt `-D` hoặc builder.proxy |
| Kết nối proxy bị từ chối | Sai proxy host/port hoặc firewall | Kiểm tra TCP/DNS và proxy logs |
| Proxy trả 407 | Chưa auth hoặc scheme bị vô hiệu | Kiểm tra Authenticator, 407 và JDK policy |
| HTTPS qua proxy lỗi handshake | CONNECT, CA intercept, hostname/truststore | Sửa certificate/trust, đừng trust-all |
| Đổi `ProxySelector.setDefault` nhưng client cũ không đổi | Client đã lấy default selector khi build | Xây client mới |
| Fixed proxy vẫn nhận cả localhost | `ProxySelector.of` không phải default selector có bypass | Dùng custom selector nếu muốn bypass |
| `HttpClient` đã build không thể đổi proxy | Client config bất biến | Tạo instance mới |
| HTTP/2 không được thương lượng qua proxy | HTTP version/implementation constraints | Kiểm tra `HttpResponse.version()` |
| Custom selector sai dưới tải cao | Shared mutable state không thread-safe | Dùng immutable snapshot/đồng bộ |
| Request đi sai tuyến sau redirect | URI mới có policy khác | Xem từng redirect hop |

### 12.1. Checklist debug có hệ thống

1. Xác nhận JDK version, JVM `-D` arguments và source thiết lập cấu hình (không ghi secret).
2. Kiểm tra `http` hay `https`, hostname và port của URI đích.
3. Xác định client dùng **default**, **fixed**, **NO_PROXY** hay **custom** selector.
4. Nếu default, kiểm tra `http.proxyHost`, `https.proxyHost`, `http.nonProxyHosts` và `java.net.useSystemProxies`.
5. Nếu custom, test `select(uri)` trên từng hostname; không mặc định selector tự dùng Java properties.
6. Quan sát lỗi TCP tới proxy, HTTP 407 và HTTPS CONNECT/TLS riêng biệt.
7. Kiểm tra redirect policy và credentials từng hop.
8. Tránh thay JVM global state trong lúc phân tích một request đang chạy; tạo thử client/selector riêng để tái hiện.

## 13. Câu hỏi tự kiểm tra

**1. `-Dhttp.proxyHost=...` có bắt mọi HttpClient đi qua proxy không?** Không; builder có thể cung cấp selector riêng.

**2. Không set `builder.proxy(...)` thì Java 17 HttpClient dùng gì?** Default ProxySelector của JVM.

**3. `HttpClient.proxy().isEmpty()` nghĩa direct?** Không; có thể dùng default selector ẩn.

**4. Dùng API nào để client luôn direct?** `builder.proxy(HttpClient.Builder.NO_PROXY)`.

**5. Dùng API nào cho một fixed HTTP proxy?** `builder.proxy(ProxySelector.of(new InetSocketAddress(host,port)))`.

**6. `ProxySelector.of(...)` có tự tuân `http.nonProxyHosts`?** Không nên giả định; là selector fixed, khác default selector.

**7. Property bypass HTTPS theo Java 17 là gì?** `http.nonProxyHosts` cũng được dùng cho HTTPS.

**8. `java.net.useSystemProxies` phải đặt khi nào?** Tại JVM startup.

**9. `HTTPS_PROXY` của shell có đảm bảo Java 17 HttpClient dùng?** Không mặc định.

**10. `http.nonProxyHosts` dùng ký tự phân tách gì?** `|`, với wildcard `*`.

**11. HTTPS qua HTTP proxy thường dùng gì để thiết lập tunnel?** `CONNECT host:443`, sau đó TLS tới origin.

**12. 407 khác 401 thế nào?** 407 là proxy authentication, 401 là origin server authentication.

**13. Vì sao Basic có thể bị từ chối với HTTPS CONNECT?** Chính sách `jdk.http.auth.tunneling.disabledSchemes` của JDK 17 mặc định chặn Basic.

**14. Đổi default selector sau khi tạo client có chắc client cũ đổi route không?** Không; system-wide defaults được lấy lúc client tạo.

**15. Vì sao cùng target mà demo in `PROXY` và `ORIGIN`?** Hai HttpClient có selectors khác nhau; một client đi fake proxy, một client đi trực tiếp.

## 14. Tài liệu chính thức

- [Java SE 17 – Networking Properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/doc-files/net-properties.html): proxyHost/Port, nonProxyHosts, SOCKS và useSystemProxies.
- [Java SE 17 – Java Networking](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): Java proxy properties, OS settings và proxy auth policies.
- [Java SE 17 – HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `proxy(ProxySelector)`, `NO_PROXY`, `authenticator`.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): default selector, `proxy()` Optional, immutable configuration.
- [Java SE 17 – ProxySelector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html): `getDefault`, `setDefault`, `select`, `connectFailed`, `of`.
- [Java SE 17 – Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Proxy.html): `Proxy.NO_PROXY` và proxy types.
- [Java SE 17 – Authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Authenticator.html): phân biệt proxy/origin authentication.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): local demo.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): CONNECT, 401 và 407.
- [RFC 9112 – HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request-target dạng absolute-form khi đi qua proxy.

**Ghi nhớ:** Java proxy properties và `ProxySelector.getDefault()` xác định **tuyến mặc định trong JVM**. `HttpClient.Builder.proxy(...)` quyết định **tuyến riêng của client**: `ProxySelector.of` cho fixed proxy, `NO_PROXY` cho direct, custom selector cho routing theo URI. Với HTTPS cần hiểu CONNECT/TLS; với credentials cần phân biệt 407/proxy auth khỏi 401/origin auth. Không đổi global JVM properties trước mỗi request; kiểm chứng chính policy của client thực sự gửi HTTP.
